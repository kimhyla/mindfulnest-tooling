#!/usr/bin/env python3
"""Generate Phase A Arlo lipsync base clip from a wizard-desk still PNG.

Kling idle with Arlo Element binding when available. Default: start+end same still
(bookend lock). Locked camera; gentle fireplace fire/smoke + squirrel idle motion.
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
    ensure_min_dimensions,
    kling_poll_fresh,
    kling_startend_submit,
    load_api_keys,
    log,
)

ARLO_STILL_PROMPT = (
    "CLOSE MEDIUM SHOT — Arlo the squirrel is warm, smiling, maintains direct eye contact "
    "with the camera 80-90% of the time, friendly, affable, pleasant. "
    "LOCKED CAMERA — perfect static camera hold, absolutely zero zoom, zero pan, "
    "zero dolly, zero Ken Burns, zero camera motion of any kind. "
    "Gentle subtle animation only: soft fireplace fire flicker and delicate smoke wisps; "
    "Arlo breathes, blinks, and shows natural idle motion "
    "(small ear shifts, subtle posture, natural arms and hands). No pacing, no large gestures. "
    "Silent video — no background music, no soundtrack, no score."
)

NEGATIVE = (
    "camera zoom, pan, dolly, Ken Burns, human hands, fingers, "
    "bird, magpie, beak, wing, flapping, extra limbs, pacing, walking, "
    "music, soundtrack, score, dialogue audio"
)

ARLO_ELEMENT_ID = "313106596591323"
DEFAULT_CLIP_ID = "arlo_idle_wizard_desk_v8"
PHASE_A_BASE_CLIP_DURATION_S = 10
PHASE_A_BASE_DURATION_CHOICES = (5, 10, 15)


def assert_arlo_element(prod: Path) -> dict:
    path = prod / "character_subjects.json"
    if not path.is_file():
        raise RuntimeError(f"character_subjects.json missing: {path}")
    arlo = json.loads(path.read_text())["characters"]["Arlo"]
    eid = str(arlo.get("element_id", ""))
    if eid != ARLO_ELEMENT_ID:
        raise RuntimeError(
            f"Unexpected Arlo element_id={eid} in {path} — expected {ARLO_ELEMENT_ID}"
        )
    return arlo


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
        "scale=1280:720:force_original_aspect_ratio=decrease,"
        "pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1:1,fps=24,"
        + VIDEO_QUALITY_GRADFUN_VF
    )
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(src),
        "-vf", vf,
        *BASE_CLIP_FFMPEG_VIDEO_ARGS,
        "-an",
        "-movflags", "+faststart",
        str(dst),
    ], check=True, timeout=180)


def _write_clip_meta(
    bases: Path,
    clip_id: str,
    still: Path,
    *,
    prompt: str,
    negative_prompt: str,
    duration: int,
    kling_mode: str,
) -> None:
    meta = bases / f"{clip_id}.meta.json"
    meta.write_text(
        json.dumps({
            "clip_id": clip_id,
            "still_path": str(still),
            "still_name": still.name,
            "generator": "phase_a_arlo_lipsync_base.py",
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "duration_s": duration,
            "kling_mode": kling_mode,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--still", type=Path, help="Source PNG (default: canonical Arlo still)")
    p.add_argument("--clip-id", default=DEFAULT_CLIP_ID)
    p.add_argument(
        "--duration",
        type=int,
        default=PHASE_A_BASE_CLIP_DURATION_S,
        choices=PHASE_A_BASE_DURATION_CHOICES,
    )
    p.add_argument(
        "--single-image",
        action="store_true",
        help="Animate from start frame only (no end still bookend lock)",
    )
    p.add_argument("--no-element", action="store_true")
    args = p.parse_args()

    event = _event_dir()
    prod = _prod_root(event)
    os.environ["MN_PROD_ROOT"] = str(prod)
    bases = prod / "assets" / "lipsync_bases"
    bases.mkdir(parents=True, exist_ok=True)

    from phase_a_arlo_contract import resolve_phase_a_arlo_idle_still  # noqa: E402

    try:
        still = resolve_phase_a_arlo_idle_still(event, prod, args.still)
    except (FileNotFoundError, ValueError) as exc:
        log(f"FATAL: {exc}")
        return 1

    raw = still.read_bytes()
    png, info, _ = ensure_min_dimensions(raw)
    log(f"Start frame: {still.name} — {info}")
    start_uri = f"data:image/png;base64,{base64.b64encode(png).decode('ascii')}"
    end_uri = None if args.single_image else start_uri
    kling_mode = "single_image" if args.single_image else "start_end_same_still"

    keys = load_api_keys()
    element = None
    if not args.no_element:
        arlo = assert_arlo_element(prod)
        log(f"Arlo element OK: id={arlo['element_id']}")
        element = {
            "element_id": str(arlo["element_id"]),
            "element_name": arlo.get("element_name", "Arlo"),
        }

    log(f"Submitting Kling idle ({kling_mode}, {args.duration}s, locked camera)")
    task_id = kling_startend_submit(
        start_uri, end_uri,
        prompt=ARLO_STILL_PROMPT, negative_prompt=NEGATIVE,
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
    _write_clip_meta(
        bases, args.clip_id, still,
        prompt=ARLO_STILL_PROMPT,
        negative_prompt=NEGATIVE,
        duration=args.duration,
        kling_mode=kling_mode,
    )

    print(json.dumps({
        "clip_id": args.clip_id,
        "mp4": out.name,
        "still": still.name,
        "kling_mode": kling_mode,
        "size_mb": round(out.stat().st_size / 1024 / 1024, 1),
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
