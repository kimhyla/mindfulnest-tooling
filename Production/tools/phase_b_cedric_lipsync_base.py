#!/usr/bin/env python3
"""Generate Phase B Cedric lipsync base clip from a wizard-desk still PNG.

Submits Kling single-image idle (no Cedric Element — human wizard not in registry),
normalizes to 1280×960, writes assets/lipsync_bases/<clip_id>.mp4.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from kling_startend_pipeline import (  # noqa: E402
    RULE8_ANTI_LIPSYNC,
    ensure_min_dimensions,
    kling_poll_fresh,
    kling_startend_submit,
    load_api_keys,
    log,
)

CEDRIC_STILL_PROMPT = (
    "Cedric the elderly wizard faces the camera at a wooden desk in a firelit cozy "
    "stone study. Deep green robe with gold embroidery, round glasses, long white curly "
    "beard and hair. Wooden mug in one hand, welcoming gesture. Books, herbs, fireplace "
    "glow. Mouth closed, lips sealed. "
    "STATIC CAMERA — locked frame, zero zoom, zero dolly, zero pan, zero Ken Burns. "
    "Only soft blinks and tiny breathing. No pacing, no large gestures."
)

NEGATIVE = (
    RULE8_ANTI_LIPSYNC + ", "
    "teeth, fangs, dental, bird, magpie, beak, wing, flapping, "
    "extra limbs, zoom in, camera move, pacing, walking, young face"
)

DEFAULT_CLIP_ID = "cedric_idle_newstyle_v3"
PHASE_B_BASE_CLIP_DURATION_S = 10
PHASE_B_BASE_DURATION_CHOICES = (5, 10, 15)


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
    _cred = HERE / "credentials_lib"
    if str(_cred) not in sys.path:
        sys.path.insert(0, str(_cred))
    from video_encode_policy import BASE_CLIP_FFMPEG_VIDEO_ARGS, VIDEO_QUALITY_GRADFUN_VF  # noqa: E402

    vf = (
        "scale=1280:960:force_original_aspect_ratio=decrease,"
        "pad=1280:960:(ow-iw)/2:(oh-ih)/2,setsar=1:1,fps=24,"
        + VIDEO_QUALITY_GRADFUN_VF
    )
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(src),
        "-vf", vf,
        *BASE_CLIP_FFMPEG_VIDEO_ARGS,
        "-c:a", "aac", "-ar", "44100", "-ac", "1", "-movflags", "+faststart",
        str(dst),
    ], check=True, timeout=180)


def _default_still_candidates(event: Path, prod: Path) -> list[Path]:
    return [
        prod / "NEW STYLE CHARACTERS" / "CEDRIC"
        / "ChatGPT Image Jun 21, 2026, 10_45_20 PM.png",
        event / "cedric_phase_b_canonical_still.png",
        event / "cedric_at_desk_phase_b_canonical_frame.png",
        prod / "NEW STYLE CHARACTERS" / "CEDRIC" / "CEDRIC.png",
    ]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--still", type=Path, help="Source PNG (default: canonical Cedric still)")
    p.add_argument("--clip-id", default=DEFAULT_CLIP_ID)
    p.add_argument(
        "--duration",
        type=int,
        default=PHASE_B_BASE_CLIP_DURATION_S,
        choices=PHASE_B_BASE_DURATION_CHOICES,
    )
    args = p.parse_args()

    event = _event_dir()
    prod = _prod_root(event)
    os.environ["MN_PROD_ROOT"] = str(prod)
    bases = prod / "assets" / "lipsync_bases"
    bases.mkdir(parents=True, exist_ok=True)

    still = args.still
    if still is None:
        for candidate in _default_still_candidates(event, prod):
            if candidate.is_file():
                still = candidate
                break
    if still is None or not still.expanduser().resolve().is_file():
        log(f"FATAL: no Cedric still found under {event} or Production/NEW STYLE CHARACTERS/CEDRIC")
        return 1
    still = still.expanduser().resolve()

    raw = still.read_bytes()
    png, info, _ = ensure_min_dimensions(raw)
    log(f"Start frame: {still.name} — {info}")
    start_uri = f"data:image/png;base64,{base64.b64encode(png).decode('ascii')}"

    keys = load_api_keys()
    log("Submitting Kling single-image idle (Cedric wizard desk, no element bind)")
    task_id = kling_startend_submit(
        start_uri, None,
        prompt=CEDRIC_STILL_PROMPT, negative_prompt=NEGATIVE,
        duration=args.duration, api_key=keys["wavespeed"],
        element_entry=None,
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
        "still": still.name,
        "size_mb": round(out.stat().st_size / 1024 / 1024, 1),
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
