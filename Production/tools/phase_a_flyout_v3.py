#!/usr/bin/env python3
"""Phase A fly-out v3 — FLUX Kontext mid-flight end frame + Kling + fade.

Kim April 20 2026: fly-out v2 had Chipper do a mid-flight 180 (flies left,
turns around, exits right). Root cause: start-end Kling interpolation
between "on desk" and "empty desk" gave Kling too much freedom on exit
trajectory.

Fix:
  1. FLUX Kontext generates an intermediate end frame showing Chipper
     already mid-flight at the right edge of frame (wings spread, motion).
  2. Kling interpolates on_desk -> mid_exit_right (controlled trajectory).
  3. ffmpeg cross-fades the last 0.3s of Kling output to empty_desk.png
     so the bird fully clears frame.

Output: Production/Event_1/phase_a_flyout_v3_<ts>.mp4
"""
from __future__ import annotations

import base64
import json
import ssl
import subprocess
import sys
import time
import http.client
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from kling_startend_pipeline import (  # type: ignore
    load_api_keys,
    kling_startend_submit,
    kling_poll_fresh,
    ensure_min_dimensions,
    flux_kontext_generate_end_frame,
    RULE8_ANTI_LIPSYNC,
    log,
)

EVENT_DIR = HERE.parent / "Event_1"
CHIPPER_ON_DESK = EVENT_DIR / "phase_a_chipper_on_desk_wide.png"
EMPTY_DESK = EVENT_DIR / "phase_a_empty_desk.png"

KONTEXT_PROMPT = (
    "Same cartoon 3D art style, same warm firelit wizard office background, "
    "same camera angle, same lighting. The small bird from the previous frame "
    "is now in flight near the right edge of the frame, wings fully spread "
    "mid-flap, body angled toward the right as it heads out of view. Small "
    "subtle motion blur on the wings. The wooden desk is now empty — the bird "
    "has already left it. Beak closed."
)

KLING_PROMPT = (
    "A small cartoon bird takes off gently from the wooden desk and flies "
    "smoothly toward the right side of the frame in a single continuous "
    "motion, wings flapping naturally. Warm firelit wizard office, soft "
    "candlelight, cozy fireplace glow. Beak closed, no dialogue in video."
)

DURATION = 5
FADE_TAIL_S = 0.4


def png_to_data_uri(path_or_bytes) -> str:
    if isinstance(path_or_bytes, Path):
        raw = path_or_bytes.read_bytes()
        safe, info, _ = ensure_min_dimensions(raw)
        log(f"  {path_or_bytes.name}: {info}")
    else:
        raw = path_or_bytes
        safe, info, _ = ensure_min_dimensions(raw)
        log(f"  (inline bytes): {info}")
    return "data:image/png;base64," + base64.b64encode(safe).decode()


def download(url: str, dst: Path) -> None:
    from urllib.request import urlopen
    for a in range(3):
        try:
            with urlopen(url, timeout=120) as r:
                dst.write_bytes(r.read())
            log(f"  downloaded {dst.name} ({dst.stat().st_size/1024/1024:.1f} MB)")
            return
        except Exception as e:
            log(f"  dl attempt {a+1} failed: {e}")
            time.sleep(3 * (2 ** a))
    sys.exit(f"download failed: {url}")


def main() -> int:
    keys = load_api_keys()
    wavespeed_key = keys["wavespeed"]
    bfl_key = keys["bfl"]

    # 1. FLUX Kontext generates the mid-flight end frame
    log("=== Step 1: FLUX Kontext mid-flight end frame ===")
    start_bytes = CHIPPER_ON_DESK.read_bytes()
    end_img_bytes = flux_kontext_generate_end_frame(
        start_image_bytes=start_bytes,
        end_prompt=KONTEXT_PROMPT,
        api_key=bfl_key,
        aspect_ratio="3:2",  # 1536x1024 landscape
    )
    ts = datetime.now().strftime("%Y%m%dT%H%M%SZ")
    mid_exit_path = EVENT_DIR / f"phase_a_chipper_midexit_right_{ts}.png"
    mid_exit_path.write_bytes(end_img_bytes)
    log(f"  saved {mid_exit_path.name} ({len(end_img_bytes)/1024:.1f} KB)")

    # 2. Kling interpolate on_desk -> mid_exit_right
    log("=== Step 2: Kling start-end (5s) ===")
    start_uri = png_to_data_uri(CHIPPER_ON_DESK)
    end_uri = png_to_data_uri(end_img_bytes)
    task_id = kling_startend_submit(
        start_b64_uri=start_uri,
        end_b64_uri=end_uri,
        prompt=KLING_PROMPT,
        negative_prompt=RULE8_ANTI_LIPSYNC,
        duration=DURATION,
        api_key=wavespeed_key,
    )
    log(f"  task_id: {task_id}")
    result = kling_poll_fresh(task_id, wavespeed_key, timeout_s=900)
    status = (result.get("status") or "").lower()
    if status != "completed":
        sys.exit(f"kling failed: status={status} data={result}")
    video_url = (result.get("outputs") or [None])[0]
    if not video_url:
        sys.exit(f"no outputs: {result}")
    kling_raw = EVENT_DIR / f"phase_a_flyout_v3_kling_{ts}.mp4"
    download(video_url, kling_raw)

    # 3. ffmpeg fade tail to empty_desk.png
    log("=== Step 3: ffmpeg tail fade to empty_desk ===")
    final_path = EVENT_DIR / f"phase_a_flyout_v3_{ts}.mp4"
    # Build a still-image video matching Kling fps + duration for fade
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=r_frame_rate,width,height",
         "-of", "json", str(kling_raw)],
        capture_output=True, text=True, check=True,
    )
    info = json.loads(probe.stdout)["streams"][0]
    fps_num, fps_den = info["r_frame_rate"].split("/")
    fps = int(fps_num) / int(fps_den)
    w, h = info["width"], info["height"]
    log(f"  kling output: {w}x{h} @ {fps} fps")

    # Simple approach: use filter_complex to cross-fade the kling output
    # with a looped still of empty_desk. We dissolve over the last FADE_TAIL_S.
    kling_dur_probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(kling_raw)],
        capture_output=True, text=True, check=True,
    )
    kling_dur = float(kling_dur_probe.stdout.strip())
    fade_start = kling_dur - FADE_TAIL_S
    log(f"  kling dur: {kling_dur:.3f}s, fade start: {fade_start:.3f}s")

    cmd = [
        "ffmpeg", "-y",
        "-i", str(kling_raw),
        "-loop", "1", "-t", f"{FADE_TAIL_S + 0.05}",
        "-i", str(EMPTY_DESK),
        "-filter_complex",
        f"[1:v]scale={w}:{h},fps={fps}[bg];"
        f"[0:v][bg]xfade=transition=fade:duration={FADE_TAIL_S}:"
        f"offset={fade_start}[v]",
        "-map", "[v]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p",
        str(final_path),
    ]
    log(f"  ffmpeg: {' '.join(cmd[1:5])}...")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        log(f"ffmpeg failed:\n{r.stderr[-1500:]}")
        sys.exit(1)

    log("=== DONE ===")
    print(json.dumps({
        "mid_exit_png": str(mid_exit_path.relative_to(HERE.parent.parent)),
        "kling_raw_mp4": str(kling_raw.relative_to(HERE.parent.parent)),
        "final_mp4": str(final_path.relative_to(HERE.parent.parent)),
        "final_size_mb": round(final_path.stat().st_size / 1024 / 1024, 2),
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
