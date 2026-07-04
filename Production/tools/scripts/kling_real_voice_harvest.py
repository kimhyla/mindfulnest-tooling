#!/usr/bin/env python3
"""KLING_REAL_VOICE_HARVEST_V1 — POV/TTS beats → Omni Element native voice on same visual.

When a beat uses ElevenLabs TTS muxed onto a motion/POV clip, harvest Kling Omni
Element native speech (throwaway speak render) and remux that audio onto the
approved visual so the character matches other Omni beats.

Audit: Event_N/_kling_real_voice_harvest.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parent
PROD = TOOLS.parent
for p in (str(TOOLS), str(PROD)):
    if p not in sys.path:
        sys.path.insert(0, p)

KLING_REAL_VOICE_HARVEST_V1 = "KLING_REAL_VOICE_HARVEST_V1"
SOURCE_TAG = "kling_real_voice_harvest"


def _heal_delivery_timeline_authority(delivery_mp4: Path) -> None:
    """STITCH_EXPORT_TIMELINE_AUTHORITY_V1 — harvest remux must pass stitch export gates."""
    from credentials_lib.ffmpeg_stitch import (
        STITCH_EXPORT_NORM_AV_MAX_DRIFT_S,
        av_duration_drift_s,
        remux_mp4_video_timeline_authority,
    )

    delivery_mp4 = delivery_mp4.resolve()
    drift = av_duration_drift_s(delivery_mp4)
    if drift <= STITCH_EXPORT_NORM_AV_MAX_DRIFT_S:
        return
    tmp = delivery_mp4.parent / f"{delivery_mp4.stem}.timeline.{os.getpid()}{delivery_mp4.suffix}"
    try:
        remux_mp4_video_timeline_authority(delivery_mp4, tmp, re_encode_video=False)
        os.replace(tmp, delivery_mp4)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def _audit(event_dir: Path, row: dict) -> None:
    row = {"code": KLING_REAL_VOICE_HARVEST_V1, "ts": datetime.now(timezone.utc).isoformat(), **row}
    line = json.dumps(row, default=str)
    print(f"[kling_real_voice_harvest] {line}", flush=True)
    log = event_dir / "_kling_real_voice_harvest.jsonl"
    try:
        with open(log, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def _ref_path(value) -> Path:
    if isinstance(value, dict):
        return Path(value.get("abs_path") or value.get("path") or value.get("local_path") or "")
    return Path(value or "")


def _extract_visual_frame0(visual_mp4: Path, dest_png: Path) -> Path:
    dest_png.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(visual_mp4.resolve()),
            "-frames:v", "1",
            str(dest_png),
        ],
        check=True,
        capture_output=True,
        timeout=120,
    )
    if not dest_png.is_file():
        raise RuntimeError(f"failed to extract frame0 from {visual_mp4}")
    return dest_png


def _resolve_bg_ref(
    beat: dict,
    *,
    fallback_beat: dict | None = None,
    visual_path: Path | None = None,
    work_dir: Path | None = None,
) -> Path:
    bg = _ref_path(beat.get("bg_ref_image"))
    if bg.is_file():
        return bg
    if fallback_beat:
        fb = _ref_path(fallback_beat.get("bg_ref_image"))
        if fb.is_file():
            return fb
    lib = _ref_path((beat.get("accepted_library_ref") or {}))
    if lib.is_file():
        return lib
    magic = str(beat.get("magic_video_path") or "").strip()
    if magic:
        event_dir_guess = _ref_path(beat.get("kling_o3_clips_dir")).parent
        magic_path = Path(magic)
        if not magic_path.is_file() and event_dir_guess.is_dir():
            magic_path = event_dir_guess / magic
        if magic_path.is_file() and work_dir is not None:
            return _extract_visual_frame0(magic_path, work_dir / "magic_frame0.png")
    if visual_path and visual_path.is_file() and work_dir is not None:
        return _extract_visual_frame0(visual_path, work_dir / "visual_frame0.png")
    raise RuntimeError(f"{beat.get('beat_id')} missing bg_ref_image for Omni harvest")


def _resolve_harvest_speaker(beat: dict) -> str:
    """Sidecar may tag POV creature VO as Voiceover — bind Omni harvest to the creature."""
    speaker = str(beat.get("speaker") or "").strip()
    if speaker and speaker.lower() != "voiceover":
        return speaker
    hay = " ".join(
        [str(beat.get("still_tts_source_text") or ""), str(beat.get("dialogue_text") or "")]
        + [
            str(o.get("label") or "")
            for o in (beat.get("kling_o3_options") or [])
            if isinstance(o, dict)
        ],
    ).lower()
    for creature in ("Ember", "Arlo", "Lorelai", "Tessa", "Willow", "Chipper", "Cedric"):
        if creature.lower() in hay:
            return creature
    return speaker or "Character"


def _scope_video_role_for_beat(beat_id: str) -> str | None:
    if "_post_" in beat_id:
        return "resolution"
    if "_pre_" in beat_id:
        return "intro"
    return None


def _needs_harvest(beat: dict) -> tuple[bool, str]:
    audio_file = str(beat.get("audio_file") or "").strip()
    active_src = ""
    active_label = ""
    contract = ""
    for opt in beat.get("kling_o3_options") or []:
        if opt.get("active"):
            active_src = str(opt.get("source") or "")
            active_label = str(opt.get("label") or "")
            contract = str(opt.get("audio_contract") or "")
            break
    if audio_file:
        return True, f"audio_file={audio_file}"
    if active_src in ("o3_pov_motion_i2v", "still_insert_kling_idle", "still_insert_ken_burns"):
        label_l = active_label.lower()
        if contract == "tts_muxed" or audio_file or " vo" in label_l or "tts" in label_l:
            return True, f"active_source={active_src}"
    if active_src and "tts" in str(beat.get("kling_o3_video_path") or "").lower():
        return True, "path hints tts_mux"
    return False, "already element_native active"


def remux_visual_with_harvest_audio(
    visual_mp4: Path,
    harvest_mp4: Path,
    dest_mp4: Path,
    *,
    timeout_s: int = 300,
) -> None:
    from credentials_lib.ffmpeg_stitch import ffprobe_duration

    dest_mp4.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest_mp4.parent / f"{dest_mp4.stem}.tmp.{os.getpid()}.mp4"
    v_dur = ffprobe_duration(visual_mp4)
    a_dur = ffprobe_duration(harvest_mp4)
    if v_dur <= 0 or a_dur <= 0:
        raise RuntimeError(f"invalid duration visual={v_dur} harvest={a_dur}")
    target = a_dur
    pad_s = max(0.0, target - v_dur)
    if pad_s > 0.05:
        # POV motion is often shorter than Omni harvest audio — hold last frame, keep full speech.
        vf = f"[0:v]tpad=stop_mode=clone:stop_duration={pad_s:.3f}[v]"
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(visual_mp4.resolve()),
            "-i", str(harvest_mp4.resolve()),
            "-filter_complex", vf,
            "-map", "[v]",
            "-map", "1:a:0",
            "-t", f"{target:.3f}",
            "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "1",
            "-movflags", "+faststart",
            str(tmp),
        ]
    else:
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(visual_mp4.resolve()),
            "-i", str(harvest_mp4.resolve()),
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-t", f"{target:.3f}",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "1",
            "-movflags", "+faststart",
            str(tmp),
        ]
    subprocess.run(cmd, check=True, capture_output=True, timeout=timeout_s)
    os.replace(tmp, dest_mp4)


def run_harvest_for_beat(
    beat_id: str,
    *,
    make_active: bool = True,
    slot_index: int = 2,
    dry_run: bool = False,
    skip_if_ok: bool = True,
    import_only_path: Path | None = None,
) -> dict:
    import beat_generator as bg
    from beatgen_scope import http_import_delivery_clip
    from kling_o3_element_beat_pipeline import _runtime_prod_root
    from o3_subprocess_bootstrap import load_o3_beat_context
    from tools.credentials_lib.credentials import load_credentials
    from tools import kling_character_registry as reg
    from tools import kling_o3_client as o3
    from video_delivery import encode_delivery_video

    beat, _seg, _sp, event_dir = load_o3_beat_context(beat_id)
    beat = dict(beat)
    if import_only_path is not None:
        remux_delivery = Path(import_only_path).expanduser().resolve()
        if not remux_delivery.is_file():
            raise RuntimeError(f"import-only delivery missing: {remux_delivery}")
        _heal_delivery_timeline_authority(remux_delivery)
        speaker = _resolve_harvest_speaker(beat)
        label = f"POV visual + Omni {speaker} voice (real-voice harvest)"
        payload = http_import_delivery_clip(
            beat_id=beat_id,
            delivery_mp4=remux_delivery,
            slot_index=slot_index,
            label=label,
            source=SOURCE_TAG,
            make_active=make_active,
            scope_video_role=_scope_video_role_for_beat(beat_id),
        )
        _audit(event_dir, {"event": "IMPORTED", "beat_id": beat_id, "import": payload, "import_only": True})
        return {"ok": True, "beat_id": beat_id, "remux_delivery": str(remux_delivery), "import": payload}

    needs, reason = _needs_harvest(beat)
    if skip_if_ok and not needs:
        _audit(event_dir, {"event": "SKIP", "beat_id": beat_id, "reason": reason})
        return {"ok": True, "skipped": True, "beat_id": beat_id, "reason": reason}

    visual_path = Path(str(beat.get("kling_o3_video_path") or ""))
    for opt in beat.get("kling_o3_options") or []:
        if not isinstance(opt, dict):
            continue
        contract = str(opt.get("audio_contract") or "")
        src = str(opt.get("source") or "")
        vp = str(opt.get("video_path") or "")
        if contract == "video_only" and vp:
            visual_path = Path(vp)
            break
        if src == "o3_pov_motion_i2v" and contract == "tts_muxed" and vp:
            # Approved POV motion + ElevenLabs — strip TTS, keep animation pixels.
            visual_path = Path(vp)
            break
    if not visual_path.is_file():
        raise RuntimeError(f"{beat_id} approved POV visual missing: {visual_path}")

    speaker = _resolve_harvest_speaker(beat)
    if not speaker or speaker.lower() == "voiceover":
        raise RuntimeError(f"{beat_id} could not resolve harvest speaker (sidecar={beat.get('speaker')!r})")

    prod_root = _runtime_prod_root()
    reg.set_prod_root(prod_root)
    if not reg.is_speaker_voice_ready(speaker):
        raise RuntimeError(f"{speaker} voice not ready — run setup_all_kling_character_voices.py")

    harvest_beat = dict(beat)
    harvest_beat["speaker"] = speaker
    char_path = _ref_path(harvest_beat.get("reference_image"))
    if not char_path.is_file():
        bg.ensure_beat_element_aligned_reference(harvest_beat)
        char_path = _ref_path(harvest_beat.get("reference_image"))
    if not char_path.is_file():
        raise RuntimeError(f"{beat_id} missing reference_image")

    prompt = bg.build_kling_o3_prompt(harvest_beat)
    prompt = bg.prepare_kling_o3_prompt_for_submit(harvest_beat, prompt)
    prompt = o3.ensure_kling_o3_speech_only_prompt(prompt)
    duration = int(bg.resolve_kling_o3_submit_duration(harvest_beat, prompt))
    element_entry = bg.resolve_o3_element_list_entry(harvest_beat, speaker)
    if not element_entry:
        raise RuntimeError(f"{beat_id} no element_list entry for {speaker}")

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    clips_dir = event_dir / "kling_o3_clips"
    work_dir = event_dir / "_kling_real_voice_harvest" / f"{beat_id}_{ts}"
    work_dir.mkdir(parents=True, exist_ok=True)

    fallback_beat = None
    if not _ref_path(harvest_beat.get("bg_ref_image")).is_file():
        _fb_id = "bg_arc1_event3_pre_beat_12" if "beat_11" in beat_id else None
        if _fb_id:
            _fb, _, _, _ = load_o3_beat_context(_fb_id)
            fallback_beat = _fb
    bg_path = _resolve_bg_ref(
        harvest_beat,
        fallback_beat=fallback_beat,
        visual_path=visual_path,
        work_dir=work_dir,
    )

    harvest_raw = work_dir / f"{beat_id}_harvest_{ts}_raw.mp4"
    harvest_delivery = work_dir / f"{beat_id}_harvest_{ts}_delivery.mp4"
    remux_raw = work_dir / f"{beat_id}_real_voice_remux_{ts}.mp4"
    remux_delivery = clips_dir / f"{beat_id}_real_voice_remux_{ts}_delivery.mp4"

    manifest = {
        "code": KLING_REAL_VOICE_HARVEST_V1,
        "beat_id": beat_id,
        "speaker": speaker,
        "visual_path": str(visual_path),
        "char_ref": str(char_path),
        "bg_ref": str(bg_path),
        "duration": duration,
        "prompt_excerpt": prompt[:400],
        "element_entry": element_entry,
    }
    (work_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    _audit(event_dir, {"event": "START", "beat_id": beat_id, "reason": reason, "work_dir": str(work_dir)})

    if dry_run:
        return {"ok": True, "dry_run": True, "beat_id": beat_id, "work_dir": str(work_dir)}

    creds = load_credentials()
    api_key = creds.get("wavespeed_key") or creds.get("wavespeed")
    if not api_key:
        raise RuntimeError("Missing wavespeed API key")

    _audit(event_dir, {"event": "O3_SUBMIT", "beat_id": beat_id, "duration": duration})
    gen_result = o3.run_beat_generation(
        api_key,
        prompt,
        char_path,
        bg_path,
        harvest_raw,
        duration=duration,
        speaker=speaker,
        element_entry=element_entry,
    )
    if not gen_result.get("ok"):
        _audit(event_dir, {"event": "O3_FAILED", "beat_id": beat_id, "result": gen_result})
        raise RuntimeError(f"O3 harvest failed: {gen_result}")

    encode_delivery_video(harvest_raw, harvest_delivery, delivery_profile="standard")
    _audit(event_dir, {
        "event": "HARVEST_DONE",
        "beat_id": beat_id,
        "harvest_delivery": str(harvest_delivery),
        "task_id": gen_result.get("task_id"),
    })

    remux_visual_with_harvest_audio(visual_path, harvest_delivery, remux_raw)
    encode_delivery_video(remux_raw, remux_delivery, delivery_profile="standard")
    _heal_delivery_timeline_authority(remux_delivery)
    _audit(event_dir, {
        "event": "REMUX_DONE",
        "beat_id": beat_id,
        "remux_delivery": str(remux_delivery),
    })

    label = f"POV visual + Omni {speaker} voice (real-voice harvest)"
    payload = http_import_delivery_clip(
        beat_id=beat_id,
        delivery_mp4=remux_delivery,
        slot_index=slot_index,
        label=label,
        source=SOURCE_TAG,
        make_active=make_active,
        scope_video_role=_scope_video_role_for_beat(beat_id),
    )
    _audit(event_dir, {"event": "IMPORTED", "beat_id": beat_id, "import": payload})
    return {
        "ok": True,
        "beat_id": beat_id,
        "harvest_delivery": str(harvest_delivery),
        "remux_delivery": str(remux_delivery),
        "import": payload,
        "work_dir": str(work_dir),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Harvest Omni Element voice onto POV/TTS beats")
    parser.add_argument("--beat-id", action="append", required=True)
    parser.add_argument("--make-active", action="store_true", default=True)
    parser.add_argument("--no-make-active", action="store_false", dest="make_active")
    parser.add_argument("--slot", type=int, default=2)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--import-only", metavar="DELIVERY_MP4", default=None,
                        help="Skip O3 harvest; import an existing remux delivery only")
    parser.add_argument("--force", action="store_true", help="Run even if beat looks element-native already")
    args = parser.parse_args()

    results = []
    for beat_id in args.beat_id:
        try:
            import_path = Path(args.import_only).expanduser() if args.import_only else None
            out = run_harvest_for_beat(
                beat_id,
                make_active=args.make_active,
                slot_index=args.slot,
                dry_run=args.dry_run,
                skip_if_ok=not args.force,
                import_only_path=import_path if args.import_only else None,
            )
            results.append(out)
            print(json.dumps(out, indent=2), flush=True)
        except Exception as exc:
            err = {"ok": False, "beat_id": beat_id, "error": str(exc)}
            results.append(err)
            print(json.dumps(err, indent=2), flush=True)
            return 1
    print(json.dumps({"ok": True, "results": results}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
