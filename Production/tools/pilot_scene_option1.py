#!/usr/bin/env python3
"""Option 1 scene pilot — ElevenLabs TTS + silent O3 base + lipsync per speaker line.

One scene = multiple dialogue lines concatenated. No Beat Gen sidecar writes.
Output: Event_N/_pilot/scene_option1/scene_option1_pilot.mp4 + manifest.json

Resume: completed lines (delivery_trimmed.mp4 + line_meta.json) are skipped.
Partial resume: lipsync_input.mp4 + padded audio on disk skips TTS/O3.
"""
from __future__ import annotations

import json
import math
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DROPBOX_PROD = Path.home() / "Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production"
PROD = DROPBOX_PROD if DROPBOX_PROD.is_dir() else HERE.parent
# lib.* lives under PROD; production_server + credentials_lib live under tools/ (HERE).
# Always prepend HERE — when invoked as `python3 pilot_scene_option1.py`, Python
# already put tools/ on sys.path, but a later PROD insert(0) shadows tools/ with
# root production_server.py (no credentials_lib sibling).
if str(PROD) not in sys.path:
    sys.path.append(str(PROD))
sys.path.insert(0, str(HERE))

import arlo_o3_voice_pipeline as arlo  # noqa: E402
import production_server as ps  # noqa: E402
from kling_startend_pipeline import kling_poll_fresh, load_api_keys  # noqa: E402
from lipsync_sender import LipSyncClient, LipsyncHostingError  # noqa: E402
from video_delivery import encode_delivery_video, encode_lipsync_input  # noqa: E402


DEFAULT_BEAT_SUFFIXES = ("04", "05", "06", "08")
SCENE_ID = "scene_option1"
LINE_MAX_ATTEMPTS = 3
LINE_RETRY_SLEEP_S = 45


def _load_sidecar() -> dict:
    dropbox = Path.home() / "Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production"
    path = dropbox / "beat_generator_state.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _beat_by_suffix(sidecar: dict, suffix: str) -> dict:
    beats = sidecar["arcs"]["arc_1"]["segments"]["event_2_pre"]["beats"]
    return next(b for b in beats if b["beat_id"].endswith(f"_beat_{suffix}"))


def _ref_path(value) -> Path:
    if isinstance(value, dict):
        return Path(value.get("abs_path") or "")
    return Path(value or "")


def _tts_text(raw: str) -> str:
    return arlo._clean_bg_text(raw or "")


def _beat_num(beat_id: str) -> str:
    match = re.search(r"_beat_(\d+)", beat_id)
    return match.group(1) if match else "xx"


def _line_dir(out_dir: Path, line_index: int, beat_id: str) -> Path:
    return out_dir / f"line_{line_index:02d}_{beat_id.split('_')[-1]}"


def _audio_paths(*, event_dir: Path, beat_id: str, speaker: str) -> tuple[Path, Path]:
    audio_dir = event_dir / "story_scene_tts_v2/storyboard_v59_prod"
    beat_num = _beat_num(beat_id)
    audio = audio_dir / f"line_{beat_num}_{arlo._safe_slug(speaker)}_voice.mp3"
    lipsync_audio = audio.with_name(audio.stem + "_lipsync_padded.mp3")
    return audio, lipsync_audio


def _load_completed_line(line_dir: Path) -> dict | None:
    trimmed = line_dir / "delivery_trimmed.mp4"
    meta_path = line_dir / "line_meta.json"
    if not trimmed.is_file() or trimmed.stat().st_size < 10_000:
        return None
    if meta_path.is_file():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["video_path"] = str(trimmed)
        return meta
    return {
        "video_path": str(trimmed),
        "clip_duration_s": round(arlo._media_duration(trimmed), 3),
        "resumed": True,
    }


def _save_line_meta(line_dir: Path, meta: dict) -> None:
    (line_dir / "line_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")


def _submit_lipsync_with_fallback(
    client: LipSyncClient,
    *,
    lipsync_input: Path,
    lipsync_audio: Path,
    beat_id: str,
) -> tuple[str, str]:
    for index, transport in enumerate(("url", "data_uri")):
        try:
            print(json.dumps({
                "phase": "lipsync_submit",
                "beat_id": beat_id,
                "transport": transport,
            }), flush=True)
            task_id = client.submit(lipsync_input, lipsync_audio, transport=transport)
            return task_id, transport
        except LipsyncHostingError as exc:
            if transport == "url":
                print(json.dumps({
                    "phase": "lipsync_retry",
                    "beat_id": beat_id,
                    "from": "url",
                    "to": "data_uri",
                    "reason": str(exc),
                }), flush=True)
                continue
            raise
    raise RuntimeError(f"Lipsync submit exhausted transports for {beat_id}")


def _process_line(
    *,
    beat: dict,
    event_dir: Path,
    out_dir: Path,
    keys: dict,
    line_index: int,
    model: str = "pro",
) -> dict:
    beat_id = beat["beat_id"]
    speaker = (beat.get("speaker") or "").strip()
    spoken = _tts_text(beat.get("dialogue_text") or "")
    char = _ref_path(beat.get("reference_image"))
    bg = _ref_path(beat.get("bg_ref_image"))
    if not spoken:
        raise RuntimeError(f"{beat_id}: empty dialogue")
    if not char.is_file():
        raise RuntimeError(f"{beat_id}: missing char ref {char}")
    if not bg.is_file():
        raise RuntimeError(f"{beat_id}: missing bg ref {bg}")

    line_dir = _line_dir(out_dir, line_index, beat_id)
    line_dir.mkdir(parents=True, exist_ok=True)
    completed = _load_completed_line(line_dir)
    if completed:
        print(json.dumps({"phase": "line_skip", "reason": "complete", **completed}), flush=True)
        return completed

    t0 = time.time()
    print(json.dumps({"phase": "line_start", "index": line_index, "beat_id": beat_id, "speaker": speaker}), flush=True)

    lipsync_input = line_dir / "lipsync_input.mp4"
    audio, lipsync_audio = _audio_paths(event_dir=event_dir, beat_id=beat_id, speaker=speaker)
    resume_from_lipsync = lipsync_input.is_file() and lipsync_audio.is_file()

    if resume_from_lipsync:
        print(json.dumps({
            "phase": "line_resume",
            "beat_id": beat_id,
            "from": "lipsync",
            "lipsync_input": str(lipsync_input),
        }), flush=True)
        profile = ps._resolve_voice_profile(speaker) or {}
        voice_model = profile.get("model") or "eleven_v3"
        if audio.is_file():
            audio_dur = arlo._media_duration(audio)
            lipsync_audio, lipsync_padding = arlo._make_lipsync_padded_audio(audio, audio_dur=audio_dur)
        else:
            padded_dur = arlo._media_duration(lipsync_audio)
            tail_s = min(arlo.LIPSYNC_TAIL_PAD_S, max(0.0, arlo.LIPSYNC_MAX_PADDED_AUDIO_S - 3.0 - arlo.LIPSYNC_HEAD_PAD_S))
            audio_dur = max(0.5, padded_dur - arlo.LIPSYNC_HEAD_PAD_S - tail_s)
            lipsync_padding = {
                "head_pad_s": arlo.LIPSYNC_HEAD_PAD_S,
                "tail_pad_s": tail_s,
                "padded_audio_duration_s": padded_dur,
            }
        o3_task = "resumed"
    else:
        audio, profile, voice_model, audio_dur = arlo._write_elevenlabs_audio(
            event_dir=event_dir,
            beat_id=beat_id,
            speaker=speaker,
            text=spoken,
            keys=keys,
        )
        lipsync_audio, lipsync_padding = arlo._make_lipsync_padded_audio(audio, audio_dur=audio_dur)
        duration = max(5, min(12, math.ceil(float(lipsync_padding["padded_audio_duration_s"]) + 0.25)))

        prompt = arlo._visual_prompt(beat.get("kling_o3_prompt") or "", speaker=speaker)
        o3_task, _submit_body = arlo._submit_o3(
            api_key=keys["wavespeed"],
            model=model,
            character=char,
            background=bg,
            prompt=prompt,
            duration=duration,
        )
        print(json.dumps({"phase": "o3_poll", "beat_id": beat_id, "task_id": o3_task}), flush=True)
        o3_result = kling_poll_fresh(o3_task, keys["wavespeed"], timeout_s=900)
        if (o3_result.get("status") or "").lower() != "completed":
            raise RuntimeError(f"O3 failed for {beat_id}: {json.dumps(o3_result)[:800]}")

        client = LipSyncClient(keys["wavespeed"])
        base = line_dir / "o3_base.mp4"
        client.download((o3_result.get("outputs") or [None])[0], base)
        silent = line_dir / "o3_silent.mp4"
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(base), "-an", "-c:v", "copy", str(silent)],
            check=True,
            timeout=120,
        )
        encode_lipsync_input(silent, lipsync_input)

    client = LipSyncClient(keys["wavespeed"])
    lipsync_task, lipsync_transport = _submit_lipsync_with_fallback(
        client,
        lipsync_input=lipsync_input,
        lipsync_audio=lipsync_audio,
        beat_id=beat_id,
    )
    print(json.dumps({
        "phase": "lipsync_poll",
        "beat_id": beat_id,
        "task_id": lipsync_task,
        "transport": lipsync_transport,
    }), flush=True)
    lipsync_result = kling_poll_fresh(lipsync_task, keys["wavespeed"], timeout_s=900)
    if (lipsync_result.get("status") or "").lower() != "completed":
        raise RuntimeError(f"Lipsync failed for {beat_id}: {json.dumps(lipsync_result)[:800]}")

    lipsync_out = line_dir / "lipsync_raw.mp4"
    client.download((lipsync_result.get("outputs") or [None])[0], lipsync_out)
    lipsync_out, audio_check = arlo._ensure_lipsync_audio(lipsync_out, lipsync_audio)
    try:
        arlo._assert_lipsync_quality(lipsync_out)
    except Exception as exc:
        if lipsync_transport == "data_uri":
            print(json.dumps({"phase": "lipsync_quality_warn", "beat_id": beat_id, "warning": str(exc)}), flush=True)
        else:
            raise

    delivery = line_dir / "delivery.mp4"
    encode_delivery_video(
        lipsync_out,
        delivery,
        include_audio=True,
        sharpen=True,
        delivery_profile="voice_first_upscale",
    )

    speech_end = float(lipsync_padding["head_pad_s"]) + audio_dur + min(0.8, float(lipsync_padding["tail_pad_s"]))
    trimmed = line_dir / "delivery_trimmed.mp4"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(delivery),
        "-t", f"{speech_end:.3f}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(trimmed),
    ], check=True, timeout=180)

    dur = arlo._media_duration(trimmed)
    elapsed = round(time.time() - t0, 1)
    meta = {
        "line_index": line_index,
        "beat_id": beat_id,
        "speaker": speaker,
        "dialogue": spoken,
        "audio_duration_s": round(audio_dur, 3),
        "clip_duration_s": round(dur, 3),
        "wall_clock_s": elapsed,
        "video_path": str(trimmed),
        "voice_id": profile.get("voice_id"),
        "voice_model": voice_model,
        "o3_task_id": o3_task,
        "lipsync_task_id": lipsync_task,
        "lipsync_transport": lipsync_transport,
        "lipsync_padding": lipsync_padding,
        "lipsync_audio_check": audio_check,
    }
    _save_line_meta(line_dir, meta)
    print(json.dumps({"phase": "line_done", **meta}), flush=True)
    return meta


def _concat_scene(clips: list[Path], dest: Path) -> float:
    dest.parent.mkdir(parents=True, exist_ok=True)
    list_file = dest.with_suffix(".txt")
    list_file.write_text("".join(f"file '{p.resolve()}'\n" for p in clips), encoding="utf-8")
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "concat", "-safe", "0", "-i", str(list_file),
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(dest),
    ], check=True, timeout=600)
    return arlo._media_duration(dest)


def _ensure_voice_profiles() -> None:
    ps._VOICE_PROFILE_CACHE = None
    cache = ps._load_voice_profiles_from_directus(force_refresh=True)
    missing = [name for name in ("Tessa", "Lorelai", "Luna") if not ps._resolve_voice_profile(name)]
    if missing:
        raise RuntimeError(
            f"Voice profiles unavailable for {missing}. "
            f"Run from Production/tools with credentials_lib present; loaded={sorted(cache.keys())}"
        )


def _pilot_complete(manifest_path: Path, scene_mp4: Path, beat_suffixes: tuple[str, ...]) -> bool:
    if not manifest_path.is_file() or not scene_mp4.is_file():
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    expected = list(beat_suffixes)
    got = manifest.get("beat_suffixes") or []
    lines = manifest.get("lines") or []
    return got == expected and len(lines) == len(expected) and scene_mp4.stat().st_size > 50_000


def run_pilot(*, beat_suffixes: tuple[str, ...] = DEFAULT_BEAT_SUFFIXES, event_id: str = "Event_2") -> dict:
    started = time.time()
    scene_mp4 = PROD / event_id / "_pilot" / SCENE_ID / "scene_option1_pilot.mp4"
    manifest_path = PROD / event_id / "_pilot" / SCENE_ID / "scene_option1_manifest.json"
    if _pilot_complete(manifest_path, scene_mp4, beat_suffixes):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        print(json.dumps({"phase": "scene_skip", "reason": "already_complete", **manifest}), flush=True)
        return manifest

    sidecar = _load_sidecar()
    event_dir = PROD / event_id
    out_dir = event_dir / "_pilot" / SCENE_ID
    out_dir.mkdir(parents=True, exist_ok=True)
    keys = load_api_keys()
    _ensure_voice_profiles()

    lines: list[dict] = []
    clip_paths: list[Path] = []
    for i, suffix in enumerate(beat_suffixes):
        beat = _beat_by_suffix(sidecar, suffix)
        last_exc: Exception | None = None
        for attempt in range(1, LINE_MAX_ATTEMPTS + 1):
            try:
                meta = _process_line(
                    beat=beat,
                    event_dir=event_dir,
                    out_dir=out_dir,
                    keys=keys,
                    line_index=i,
                )
                lines.append(meta)
                clip_paths.append(Path(meta["video_path"]))
                last_exc = None
                break
            except Exception as exc:
                last_exc = exc
                print(json.dumps({
                    "phase": "line_error",
                    "beat_suffix": suffix,
                    "attempt": attempt,
                    "error": str(exc),
                }), flush=True)
                if attempt < LINE_MAX_ATTEMPTS:
                    time.sleep(LINE_RETRY_SLEEP_S * attempt)
        if last_exc is not None:
            raise last_exc

    total_dur = _concat_scene(clip_paths, scene_mp4)
    manifest = {
        "scene_id": SCENE_ID,
        "pipeline": "option1_tts_o3_silent_lipsync",
        "event_id": event_id,
        "beat_suffixes": list(beat_suffixes),
        "note": "Beat 03 skipped — dialogue too long for lipsync audio pad cap in v1 pilot.",
        "lines": lines,
        "scene_mp4": str(scene_mp4),
        "scene_duration_s": round(total_dur, 3),
        "wall_clock_s": round(time.time() - started, 1),
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"phase": "scene_done", "scene_mp4": str(scene_mp4), "manifest": str(manifest_path), **manifest}), flush=True)
    return manifest


def main() -> int:
    suffixes = tuple(s for s in (sys.argv[1:] or DEFAULT_BEAT_SUFFIXES) if re.fullmatch(r"\d+", s))
    if not suffixes:
        suffixes = DEFAULT_BEAT_SUFFIXES
    if "--autorun" in sys.argv:
        max_runs = 30
        for run in range(1, max_runs + 1):
            scene_mp4 = PROD / "Event_2" / "_pilot" / SCENE_ID / "scene_option1_pilot.mp4"
            manifest_path = PROD / "Event_2" / "_pilot" / SCENE_ID / "scene_option1_manifest.json"
            if _pilot_complete(manifest_path, scene_mp4, suffixes):
                print(json.dumps({"phase": "autorun_done", "run": run}), flush=True)
                return 0
            print(json.dumps({"phase": "autorun_start", "run": run, "max_runs": max_runs}), flush=True)
            try:
                run_pilot(beat_suffixes=suffixes)
            except Exception as exc:
                print(json.dumps({"phase": "autorun_error", "run": run, "error": str(exc)}), flush=True)
            if _pilot_complete(manifest_path, scene_mp4, suffixes):
                print(json.dumps({"phase": "autorun_done", "run": run}), flush=True)
                return 0
            sleep_s = min(300, 90 * run)
            print(json.dumps({"phase": "autorun_sleep", "seconds": sleep_s, "run": run}), flush=True)
            time.sleep(sleep_s)
        return 1
    run_pilot(beat_suffixes=suffixes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
