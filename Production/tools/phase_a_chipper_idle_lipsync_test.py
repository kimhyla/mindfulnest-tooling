#!/usr/bin/env python3
"""One-shot Phase A test: storyboard idle lipsync on Phase A still (no wiring).

Mirrors vendor_jobs.handle_lipsync_idle without beat state or Phase A API.
Use a short audio slice (~8s) to match storyboard beat duration limits.

Usage:
  python3 phase_a_chipper_idle_lipsync_test.py
  python3 phase_a_chipper_idle_lipsync_test.py --audio-slice-sec 8
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import subprocess
import sys
import time
import traceback
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
from production_server import (  # noqa: E402
    KLING_MAX_DURATION_SEC,
    KLING_MIN_DURATION_SEC,
    _AUDIO_SHORT_THRESHOLD_SEC,
    _ffprobe_duration,
    _silcomp_audio,
    _trim_video_to_audio,
)

DROPBOX_PROD = Path.home() / (
    "Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production"
)
IDLE_PROMPT = (
    "Subtle idle breathing animation, gentle head sway, "
    "beak closed, no speech, no lip movement, "
    "silent subtle idle movement only"
)


def log(msg: str) -> None:
    print(f"[phase_a_idle_test] {msg}", flush=True)


def _event_dir() -> Path:
    return DROPBOX_PROD / "Event_1"


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


def _slice_audio(src: Path, dst: Path, seconds: float) -> Path:
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(src),
            "-t", f"{seconds:.3f}",
            "-c:a", "libmp3lame", "-b:a", "128k",
            str(dst),
        ],
        check=True,
        capture_output=True,
        timeout=120,
    )
    return dst


def _kling_idle_duration(audio_duration: float) -> int:
    if audio_duration <= _AUDIO_SHORT_THRESHOLD_SEC:
        return KLING_MIN_DURATION_SEC
    return KLING_MAX_DURATION_SEC


def _tail_append_and_faststart(
    *,
    dest: Path,
    idle_clip: Path,
    trimmed_to: float,
    beat_key: str,
    ts: int,
    tmp_dir: Path,
) -> int:
    size = dest.stat().st_size
    try:
        raw_dur = _ffprobe_duration(str(idle_clip))
        tail_start_s = trimmed_to
        tail_avail_s = raw_dur - tail_start_s
        if tail_avail_s > 0.15:
            tail_tmp = tmp_dir / f"_tmp_{beat_key}_idle_tail_{ts}.mp4"
            concat_txt = tmp_dir / f"_tmp_{beat_key}_idle_clist_{ts}.txt"
            ls_ext = tmp_dir / f"_tmp_{beat_key}_idle_lsext_{ts}.mp4"
            try:
                probe = subprocess.run(
                    [
                        "ffprobe", "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=width,height,r_frame_rate",
                        "-of", "csv=p=0", str(dest),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                ls_w, ls_h, ls_fps_str = 720, 544, "25"
                parts = probe.stdout.strip().split(",")
                if len(parts) >= 3:
                    try:
                        ls_w = int(parts[0])
                        ls_h = int(parts[1])
                        fps_frac = parts[2].strip()
                        if "/" in fps_frac:
                            n, d = fps_frac.split("/", 1)
                            ls_fps_str = f"{int(n) / max(int(d), 1):.6f}"
                        else:
                            ls_fps_str = fps_frac
                    except (ValueError, ZeroDivisionError):
                        pass
                subprocess.run(
                    [
                        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-ss", f"{tail_start_s:.3f}",
                        "-i", str(idle_clip),
                        "-f", "lavfi", "-t", f"{tail_avail_s + 0.1:.3f}",
                        "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                        "-filter_complex",
                        f"[0:v]scale={ls_w}:{ls_h}:flags=lanczos,"
                        f"fps={ls_fps_str},format=yuv420p[vout]",
                        "-map", "[vout]", "-map", "1:a",
                        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                        "-c:a", "aac", "-b:a", "128k", "-ac", "2", "-ar", "44100",
                        "-shortest", str(tail_tmp),
                    ],
                    check=True,
                    capture_output=True,
                    timeout=60,
                )
                concat_txt.write_text(
                    f"file '{dest.resolve()}'\nfile '{tail_tmp.resolve()}'\n"
                )
                subprocess.run(
                    [
                        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-f", "concat", "-safe", "0", "-i", str(concat_txt),
                        "-c", "copy", str(ls_ext),
                    ],
                    check=True,
                    capture_output=True,
                    timeout=120,
                )
                ls_ext.replace(dest)
                size = dest.stat().st_size
                log(f"tail-append OK +{tail_avail_s:.2f}s → {size:,}B")
            finally:
                for tf in (tail_tmp, concat_txt, ls_ext):
                    try:
                        tf.unlink()
                    except (OSError, UnboundLocalError):
                        pass
    except Exception as exc:
        log(f"tail-append skipped (non-fatal): {exc!r}")

    faststart_tmp = tmp_dir / f"_tmp_{beat_key}_idle_fs_{ts}.mp4"
    try:
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-i", str(dest),
                "-c", "copy",
                "-movflags", "+faststart",
                str(faststart_tmp),
            ],
            check=True,
            capture_output=True,
            timeout=60,
        )
        faststart_tmp.replace(dest)
        size = dest.stat().st_size
        log(f"faststart OK → {size:,}B")
    except Exception as exc:
        log(f"faststart skipped (non-fatal): {exc!r}")
        try:
            faststart_tmp.unlink()
        except OSError:
            pass
    return size


def run_idle_lipsync_test(
    *,
    still: Path,
    audio: Path,
    out_dir: Path,
    audio_slice_sec: float | None,
    use_element: bool,
    slow_zoom: bool = False,
    zoom_ramp_sec: float = 14.0,
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = out_dir / "_tmp_idle_test"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    tag = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    source_audio = audio
    if audio_slice_sec is not None:
        sliced = tmp_dir / f"audio_slice_{ts}.mp3"
        source_audio = _slice_audio(audio, sliced, audio_slice_sec)
        log(f"audio slice: {audio_slice_sec}s → {source_audio.name}")

    audio_duration = _ffprobe_duration(source_audio)
    kling_duration = _kling_idle_duration(audio_duration)
    log(f"still: {still.name}")
    log(f"audio: {source_audio.name} ({audio_duration:.2f}s)")
    log(f"kling idle duration: {kling_duration}s")

    keys = load_api_keys()
    api_key = keys["wavespeed"]
    img_b64_uri = _still_to_b64_uri(still)

    element_entry = None
    if use_element:
        from kling_startend_pipeline import _load_subject_element

        element_entry = _load_subject_element("Chipper")
        log("Chipper element bound for idle Kling")

    log("Step 1: Kling idle (same start+end still)")
    task_id = kling_startend_submit(
        start_b64_uri=img_b64_uri,
        end_b64_uri=img_b64_uri,
        prompt=IDLE_PROMPT,
        negative_prompt=RULE8_ANTI_LIPSYNC,
        duration=kling_duration,
        api_key=api_key,
        element_entry=element_entry,
    )
    log(f"Kling task_id={task_id}")
    result = kling_poll_fresh(task_id, api_key, timeout_s=900)
    if (result.get("status") or "").lower() != "completed":
        raise RuntimeError(f"Kling idle failed: {result}")
    kling_url = (result.get("outputs") or [None])[0]
    if not kling_url:
        raise RuntimeError("Kling idle returned no output URL")

    idle_clip = tmp_dir / f"idle_kling_{ts}.mp4"
    subprocess.run(["curl", "-sSL", "-o", str(idle_clip), kling_url], check=True, timeout=180)
    log(f"idle clip: {idle_clip.name} ({idle_clip.stat().st_size:,}B)")

    log("Step 2: §8.4 silcomp + video trim")
    tmp_audio = tmp_dir / f"idle_audio_{ts}.mp3"
    tmp_video = tmp_dir / f"idle_vtrim_{ts}.mp4"
    audio_for_lipsync, audio_proc_meta = _silcomp_audio(
        source_audio, tmp_audio, loudnorm=True,
    )
    audio_dur_actual = float(audio_proc_meta.get("compressed_duration_s") or audio_duration)
    video_for_lipsync, trimmed_to, ts_used, te_used = _trim_video_to_audio(
        idle_clip, tmp_video, audio_dur_actual, trim_start=0.0, trim_end=None,
    )
    log(f"trimmed video: {trimmed_to:.2f}s for audio {audio_dur_actual:.2f}s")

    log("Step 3: Kling LipSync")
    lipsync_client = LipSyncClient(api_key)
    ls_task_id = lipsync_client.submit(video_for_lipsync, audio_for_lipsync)
    ls_result = lipsync_client.poll_until_done(ls_task_id)
    ls_status = (ls_result.get("status") or "").lower()
    if not (ls_status == "completed" and ls_result.get("outputs")):
        raise RuntimeError(f"Kling LipSync failed: {ls_result}")

    out_name = f"chipper_lipsync_idle_test_{tag}.mp4"
    dest = out_dir / out_name
    lipsync_client.download(ls_result["outputs"][0], dest)
    log(f"lipsync raw: {dest.name} ({dest.stat().st_size:,}B)")

    log("Step 4: tail-append + faststart")
    size = _tail_append_and_faststart(
        dest=dest,
        idle_clip=idle_clip,
        trimmed_to=trimmed_to,
        beat_key="phase_a_test",
        ts=ts,
        tmp_dir=tmp_dir,
    )

    slowzoom_name = None
    if slow_zoom:
        from phase_a_slow_zoom import apply_slow_zoom

        log("Step 5: slow zoom (post-process)")
        sz_dest = dest.with_name(f"{dest.stem}_slowzoom{dest.suffix}")
        apply_slow_zoom(dest, sz_dest, ramp_sec=zoom_ramp_sec)
        slowzoom_name = sz_dest.name
        size = sz_dest.stat().st_size

    manifest = {
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pipeline": "storyboard_idle_lipsync_test",
        "still": still.name,
        "audio_source": audio.name,
        "audio_slice_sec": audio_slice_sec,
        "audio_duration_s": round(audio_dur_actual, 3),
        "kling_idle_duration_s": kling_duration,
        "trimmed_video_s": round(trimmed_to, 3),
        "output": out_name,
        "slowzoom_output": slowzoom_name,
        "size_bytes": size,
        "method": "idle_kling_lipsync",
        "element_bound": bool(element_entry),
    }
    manifest_path = dest.with_suffix(".json")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    log(f"DONE → {dest}")
    log(f"manifest → {manifest_path.name}")
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--still",
        type=Path,
        default=_event_dir() / "phase_a_chipper_body_plate_v1.png",
    )
    ap.add_argument(
        "--audio",
        type=Path,
        default=None,
        help="Defaults to newest phase_a_voice_stem_*.mp3",
    )
    ap.add_argument(
        "--audio-slice-sec",
        type=float,
        default=8.0,
        help="Test with first N seconds only (storyboard-like duration). 0 = full audio.",
    )
    ap.add_argument("--out-dir", type=Path, default=_event_dir() / "phase_a_idle_candidates")
    ap.add_argument(
        "--with-element",
        action="store_true",
        help="Bind Chipper Kling Element (storyboard idle uses none; optional A/B)",
    )
    ap.add_argument(
        "--slow-zoom",
        action="store_true",
        help="Post-process subtle slow zoom (hat + chair stay in frame)",
    )
    ap.add_argument(
        "--zoom-ramp-sec",
        type=float,
        default=14.0,
        help="Seconds to reach max zoom during opening dialogue (default 14)",
    )
    args = ap.parse_args()

    still = args.still.expanduser().resolve()
    if not still.is_file():
        log(f"FATAL: still missing: {still}")
        return 1

    if args.audio:
        audio = args.audio.expanduser().resolve()
    else:
        stems = sorted(
            _event_dir().glob("phase_a_voice_stem_*.mp3"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not stems:
            log("FATAL: no phase_a_voice_stem_*.mp3")
            return 1
        audio = stems[0]

    if not audio.is_file():
        log(f"FATAL: audio missing: {audio}")
        return 1

    slice_sec = args.audio_slice_sec if args.audio_slice_sec > 0 else None

    try:
        manifest = run_idle_lipsync_test(
            still=still,
            audio=audio,
            out_dir=args.out_dir.expanduser().resolve(),
            audio_slice_sec=slice_sec,
            use_element=args.with_element,
            slow_zoom=args.slow_zoom,
            zoom_ramp_sec=args.zoom_ramp_sec,
        )
        print(json.dumps({"ok": True, **manifest}, indent=2))
        return 0
    except Exception as exc:
        traceback.print_exc()
        log(f"FATAL: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
