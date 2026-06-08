#!/usr/bin/env python3
"""Generate Chipper Phase A lipsync base clip from a still PNG.

Submits Kling single-image idle with Chipper Elements binding when available,
normalizes to 1280×960, writes assets/lipsync_bases/<clip_id>.mp4.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from kling_startend_pipeline import (  # noqa: E402
    RULE8_ANTI_LIPSYNC,
    _load_subject_element,
    ensure_min_dimensions,
    kling_poll_fresh,
    kling_startend_submit,
    load_api_keys,
    log,
)

CHIPPER_STILL_PROMPT = (
    "Chipper the magpie faces the camera on a wizard desk, firelit cozy study. "
    "Both wings visible and folded at his sides — NOT tucked behind body. "
    "TOOTH-FREE keratin beak only, mouth closed. Camera locked, no zoom. "
    "Only soft blinks and tiny breathing. No pacing, no wing gesticulation."
)

NEGATIVE = (
    RULE8_ANTI_LIPSYNC + ", "
    "teeth, fangs, dental, human hands, fingers, wing gesticulation, "
    "flapping, extra wings, zoom in, camera move, pacing, walking"
)


def _event_dir() -> Path:
    env = os.environ.get("MN_EVENT_DIR", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    dropbox = (
        Path.home()
        / "Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production"
    )
    if (dropbox / "Event_1").is_dir():
        return dropbox / "Event_1"
    return HERE.parent / "Event_1"


def _prod_root(event: Path) -> Path:
    return event.parent


def _normalize(src: Path, dst: Path) -> None:
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(src),
        "-vf", "scale=1280:960:force_original_aspect_ratio=decrease,"
               "pad=1280:960:(ow-iw)/2:(oh-ih)/2,setsar=1:1,fps=24",
        "-c:v", "libx264", "-crf", "20", "-preset", "fast",
        "-c:a", "aac", "-ar", "44100", "-ac", "1", "-movflags", "+faststart",
        str(dst),
    ], check=True, timeout=180)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--still", type=Path, help="Source PNG (default: v3 crop or newstyle v2)")
    p.add_argument("--clip-id", default="chipper_idle_newstyle_v3")
    p.add_argument("--duration", type=int, default=10, choices=(5, 10))
    p.add_argument("--no-element", action="store_true")
    args = p.parse_args()

    event = _event_dir()
    prod = _prod_root(event)
    bases = prod / "assets" / "lipsync_bases"
    bases.mkdir(parents=True, exist_ok=True)

    still = args.still
    if still is None:
        for candidate in (
            event / "phase_a_chipper_closeup_crop_v3.png",
            event / "phase_a_chipper_closeup_newstyle_v2.png",
            event / "phase_a_chipper_closeup.png",
        ):
            if candidate.is_file():
                still = candidate
                break
    if still is None or not still.expanduser().resolve().is_file():
        log(f"FATAL: no Chipper still found under {event}")
        return 1
    still = still.expanduser().resolve()

    raw = still.read_bytes()
    png, info, _ = ensure_min_dimensions(raw)
    log(f"Start frame: {still.name} — {info}")
    start_uri = f"data:image/png;base64,{base64.b64encode(png).decode('ascii')}"

    keys = load_api_keys()
    element = None if args.no_element else _load_subject_element("Chipper")

    log("Submitting Kling single-image idle")
    task_id = kling_startend_submit(
        start_uri, None,
        prompt=CHIPPER_STILL_PROMPT, negative_prompt=NEGATIVE,
        duration=args.duration, api_key=keys["wavespeed"],
        element_entry=element,
    )
    log(f"task_id={task_id}")
    result = kling_poll_fresh(task_id, keys["wavespeed"], timeout_s=900)
    if result.get("status") != "completed":
        log(f"FATAL: {result}")
        return 1
    url = (result.get("outputs") or [None])[0]
    if not url:
        log("FATAL: no output url")
        return 1

    staging = bases / f"_tmp_{args.clip_id}.mp4"
    subprocess.run(["curl", "-sSL", "-o", str(staging), url], check=True, timeout=180)
    out = bases / f"{args.clip_id}.mp4"
    _normalize(staging, out)
    staging.unlink(missing_ok=True)
    log(f"✓ Saved {out} ({out.stat().st_size / 1024 / 1024:.1f} MB)")

    print(json.dumps({
        "clip_id": args.clip_id,
        "mp4": out.name,
        "size_mb": round(out.stat().st_size / 1024 / 1024, 1),
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
