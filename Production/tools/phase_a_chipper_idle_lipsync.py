#!/usr/bin/env python3
"""Phase A Chipper lipsync — storyboard idle Kling pipeline (Kim 2026-06-08).

Default for POST /api/phase_a/lipsync:
  body plate → Kling idle → crossfade-loop base → silcomp+auto_preroll
  → Kling LipSync → pad video to audio → smooth zoom → trim preroll
  → phase_a_lipsync_*.mp4 → auto-stitch (1.0s fly-in xfade)

Post-process classification: see phase_a_av_post.py (stages A–D).
"""
from __future__ import annotations

import base64
import io
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from kling_startend_pipeline import (  # noqa: E402
    RULE8_ANTI_LIPSYNC,
    kling_poll_fresh,
    kling_startend_submit,
    load_api_keys,
)
from lipsync_sender import LipSyncClient  # noqa: E402
from phase_a_av_post import (  # noqa: E402
    DEFAULT_FPS,
    apply_smooth_zoom,
    av_duration_gap,
    crossfade_loop_video,
    pad_video_to_match_audio,
    trim_av_lead_in,
)
from production_server import (  # noqa: E402
    KLING_MAX_DURATION_SEC,
    KLING_MIN_DURATION_SEC,
    _AUDIO_SHORT_THRESHOLD_SEC,
    _VIDEO_TRIM_TAILROOM_TARGET_S,
    _ffprobe_duration,
    _silcomp_audio,
    _trim_video_to_audio,
)

BODY_PLATE_DEFAULT = "phase_a_chipper_on_desk_newstyle_v1.png"
IDLE_PROMPT = (
    "Subtle idle breathing animation, gentle head sway, "
    "beak closed, no speech, no lip movement, "
    "silent subtle idle movement only"
)

# Kim 2026-06-08: middle starts closer (body plate) but must keep full head in
# frame — subtle push-in only, anchored high so forehead is not cropped.
PHASE_A_ZOOM_END = 1.03
PHASE_A_ZOOM_RAMP_SEC = 18.0
PHASE_A_ZOOM_RAMP_DELAY_SEC = 1.5  # hold framing after wide→close xfade
PHASE_A_FOCAL_X = 0.5
PHASE_A_FOCAL_Y = 0.40


def log(msg: str) -> None:
    print(f"[phase_a_idle_lipsync] {msg}", flush=True)


def resolve_body_plate(event_dir: Path, state: dict | None = None) -> Path:
    state = state or {}
    nested = state.get("phase_a") if isinstance(state.get("phase_a"), dict) else {}
    name = (
        state.get("phase_a_chipper_body_plate_file")
        or (nested or {}).get("phase_a_chipper_body_plate_file")
        or BODY_PLATE_DEFAULT
    )
    plate = event_dir / name
    if not plate.is_file():
        raise FileNotFoundError(f"Chipper body plate missing: {plate}")
    return plate


def _still_to_b64_uri(still: Path) -> str:
    img_bytes = still.read_bytes()
    ext = still.suffix.lower()
    if ext in (".webp", ".jpg", ".jpeg"):
        from PIL import Image

        img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        img_bytes = buf.getvalue()
    return f"data:image/png;base64,{base64.b64encode(img_bytes).decode('ascii')}"


def _kling_idle_duration(audio_duration: float) -> int:
    if audio_duration <= _AUDIO_SHORT_THRESHOLD_SEC:
        return KLING_MIN_DURATION_SEC
    return KLING_MAX_DURATION_SEC


def _preroll_seconds(audio_proc_meta: dict) -> float:
    pr = audio_proc_meta.get("preroll_processing") or {}
    try:
        return float(pr.get("preroll_added_s") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def run_phase_a_chipper_idle_lipsync(
    still: Path,
    audio_raw: Path,
    out_path: Path,
    *,
    tmp_dir: Path | None = None,
    apply_zoom: bool = False,
    zoom_end: float = PHASE_A_ZOOM_END,
    zoom_ramp_sec: float = PHASE_A_ZOOM_RAMP_SEC,
    zoom_ramp_delay_sec: float = PHASE_A_ZOOM_RAMP_DELAY_SEC,
) -> dict:
    """Full idle Kling lipsync pipeline. Writes out_path."""
    still = still.expanduser().resolve()
    audio_raw = audio_raw.expanduser().resolve()
    out_path = out_path.expanduser().resolve()
    work = tmp_dir or (out_path.parent / "_tmp_phase_a_idle_lipsync")
    work.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    tag = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    log(f"still: {still.name}")
    log(f"audio: {audio_raw.name}")

    raw_dur = _ffprobe_duration(audio_raw)
    max_audio_s = raw_dur + 2.0

    log("Step 1: §8.4 silcomp + loudnorm + auto_preroll (storyboard lipsync path)")
    tmp_audio = work / f"idle_audio_{ts}.mp3"
    audio_for_lipsync, audio_proc_meta = _silcomp_audio(
        audio_raw,
        tmp_audio,
        loudnorm=True,
        auto_preroll=True,
        max_audio_s=max_audio_s,
    )
    preroll_s = _preroll_seconds(audio_proc_meta)
    audio_dur_actual = float(
        audio_proc_meta.get("compressed_duration_s") or _ffprobe_duration(audio_for_lipsync)
    )
    log(f"audio after prep: {audio_dur_actual:.2f}s (preroll +{preroll_s:.3f}s)")

    kling_duration = _kling_idle_duration(audio_dur_actual)
    keys = load_api_keys()
    api_key = keys["wavespeed"]
    img_b64_uri = _still_to_b64_uri(still)

    log(f"Step 2: Kling idle ({kling_duration}s, same start+end still)")
    task_id = kling_startend_submit(
        start_b64_uri=img_b64_uri,
        end_b64_uri=img_b64_uri,
        prompt=IDLE_PROMPT,
        negative_prompt=RULE8_ANTI_LIPSYNC,
        duration=kling_duration,
        api_key=api_key,
        element_entry=None,
    )
    result = kling_poll_fresh(task_id, api_key, timeout_s=900)
    if (result.get("status") or "").lower() != "completed":
        raise RuntimeError(f"Kling idle failed: {result}")
    kling_url = (result.get("outputs") or [None])[0]
    if not kling_url:
        raise RuntimeError("Kling idle returned no output URL")

    idle_clip = work / f"idle_kling_{ts}.mp4"
    subprocess.run(["curl", "-sSL", "-o", str(idle_clip), kling_url], check=True, timeout=180)
    log(f"idle clip: {idle_clip.name} ({idle_clip.stat().st_size:,}B)")

    target_s = audio_dur_actual + _VIDEO_TRIM_TAILROOM_TARGET_S
    looped = work / f"idle_xfade_{ts}.mp4"
    log("Step 3: crossfade-loop idle base (no hard concat)")
    crossfade_loop_video(idle_clip, looped, target_s, fps=DEFAULT_FPS)

    log("Step 4: trim looped idle to audio")
    tmp_video = work / f"idle_vtrim_{ts}.mp4"
    video_for_lipsync, trimmed_to, _, _ = _trim_video_to_audio(
        looped, tmp_video, audio_dur_actual, trim_start=0.0, trim_end=None,
    )
    log(f"trimmed video: {trimmed_to:.2f}s for audio {audio_dur_actual:.2f}s")

    log("Step 5: Kling LipSync")
    lipsync_client = LipSyncClient(api_key)
    ls_task_id = lipsync_client.submit(video_for_lipsync, audio_for_lipsync)
    ls_result = lipsync_client.poll_until_done(ls_task_id)
    ls_status = (ls_result.get("status") or "").lower()
    if not (ls_status == "completed" and ls_result.get("outputs")):
        raise RuntimeError(f"Kling LipSync failed: {ls_result}")

    ls_raw = work / f"lipsync_raw_{tag}.mp4"
    lipsync_client.download(ls_result["outputs"][0], ls_raw)
    v0, a0, gap0 = av_duration_gap(ls_raw)
    log(f"lipsync raw: {ls_raw.name} v={v0:.2f}s a={a0:.2f}s gap={gap0:.2f}s")

    log("Step 6: pad video to match audio (A/V repair)")
    padded = work / f"lipsync_padded_{tag}.mp4"
    _, pad_s = pad_video_to_match_audio(ls_raw, padded)

    working = padded
    if apply_zoom:
        log(
            f"Step 7: smooth zoom ({zoom_end:.2f}× ramp {zoom_ramp_sec:.0f}s "
            f"delay {zoom_ramp_delay_sec:.1f}s)"
        )
        zoomed = work / f"lipsync_zoom_{tag}.mp4"
        apply_smooth_zoom(
            working,
            zoomed,
            zoom_end=zoom_end,
            ramp_sec=zoom_ramp_sec,
            ramp_delay_sec=zoom_ramp_delay_sec,
            focal_x=PHASE_A_FOCAL_X,
            focal_y=PHASE_A_FOCAL_Y,
            fps=DEFAULT_FPS,
        )
        working = zoomed

    log(f"Step 8: trim preroll lead-in ({preroll_s:.3f}s) for stitch")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    trim_av_lead_in(working, out_path, preroll_s)

    v_final, a_final, gap_final = av_duration_gap(out_path)
    if gap_final > 0.08:
        log(f"WARN: residual A/V gap {gap_final:.3f}s after pad — re-pad")
        repad_tmp = work / f"lipsync_repad_{tag}.mp4"
        pad_video_to_match_audio(out_path, repad_tmp)
        repad_tmp.replace(out_path)
        v_final, a_final, gap_final = av_duration_gap(out_path)

    manifest = {
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pipeline": "phase_a_idle_kling_lipsync_v2",
        "still": still.name,
        "audio_source": audio_raw.name,
        "audio_duration_s": round(audio_dur_actual, 3),
        "preroll_added_s": round(preroll_s, 3),
        "preroll_trimmed_s": round(preroll_s, 3),
        "kling_idle_duration_s": kling_duration,
        "trimmed_video_s": round(trimmed_to, 3),
        "lipsync_av_gap_before_pad_s": round(gap0, 3),
        "video_pad_s": round(pad_s, 3),
        "final_video_s": round(v_final, 3),
        "final_audio_s": round(a_final, 3),
        "final_av_gap_s": round(gap_final, 3),
        "output": out_path.name,
        "size_bytes": out_path.stat().st_size,
        "method": "idle_kling_lipsync",
        "idle_loop": "crossfade",
        "zoom": apply_zoom,
        "zoom_end": zoom_end if apply_zoom else None,
        "zoom_ramp_sec": zoom_ramp_sec if apply_zoom else None,
        "zoom_ramp_delay_sec": zoom_ramp_delay_sec if apply_zoom else None,
    }
    sidecar = out_path.with_suffix(".json")
    sidecar.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    log(f"DONE → {out_path} (v={v_final:.2f}s a={a_final:.2f}s gap={gap_final:.3f}s)")
    return manifest


def main() -> int:
    import argparse

    dropbox = Path.home() / (
        "Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production"
    )
    event = dropbox / "Event_1"

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--still", type=Path, default=None)
    ap.add_argument("--audio", type=Path, default=None)
    ap.add_argument("-o", "--output", type=Path, default=None)
    ap.add_argument("--no-zoom", action="store_true")
    args = ap.parse_args()

    still = args.still or resolve_body_plate(event)
    if args.audio:
        audio = args.audio.expanduser().resolve()
    else:
        state_path = event / "production_state.json"
        state = json.loads(state_path.read_text()) if state_path.is_file() else {}
        audio_name = state.get("phase_a_voice_stem_file")
        if not audio_name:
            log("FATAL: phase_a_voice_stem_file unset")
            return 1
        audio = event / audio_name

    if not audio.is_file():
        log(f"FATAL: audio missing: {audio}")
        return 1

    if args.output:
        out = args.output.expanduser().resolve()
    else:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        out = event / f"phase_a_lipsync_{ts}.mp4"

    try:
        manifest = run_phase_a_chipper_idle_lipsync(
            still, audio, out, apply_zoom=not args.no_zoom,
        )
        print(json.dumps({"ok": True, **manifest}, indent=2))
        return 0
    except Exception as exc:
        import traceback

        traceback.print_exc()
        log(f"FATAL: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
