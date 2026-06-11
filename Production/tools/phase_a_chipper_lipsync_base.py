#!/usr/bin/env python3
"""Generate Phase A lipsync base clip from an Arlo wizard-desk still PNG.

Submits Kling single-image idle with Arlo Elements binding when available,
normalizes to 1280×960, writes assets/lipsync_bases/<clip_id>.mp4.

Arlo migration (2026-06): replaces Chipper magpie desk base; fly-in/fly-out
bookends removed from stitch — Arlo is already on-screen in this still.
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
    ensure_min_dimensions,
    kling_poll_fresh,
    kling_startend_submit,
    load_api_keys,
    log,
)

ARLO_STILL_PROMPT = (
    "Arlo the red squirrel faces the camera at a wizard desk in a firelit cozy study. "
    "Blue scarf and green vest visible. Both paws resting on the desk — NOT tucked "
    "behind body. Mouth closed, tooth-free. Camera locked, no zoom. "
    "Only soft blinks and tiny breathing. No pacing, no tail swish gesticulation."
)

NEGATIVE = (
    RULE8_ANTI_LIPSYNC + ", "
    "teeth, fangs, dental, human hands, fingers, bird, magpie, beak, wing, "
    "flapping, extra limbs, zoom in, camera move, pacing, walking"
)

ARLO_ELEMENT_ID = "313106596591323"
DEFAULT_CLIP_ID = "arlo_idle_wizard_desk_v1"


def assert_arlo_element(prod: Path) -> dict:
    """Fail fast if character_subjects.json would bind a stale/non-Arlo element."""
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
    p.add_argument("--still", type=Path, help="Source PNG (default: Arlo wizard desk v1)")
    p.add_argument("--clip-id", default=DEFAULT_CLIP_ID)
    p.add_argument("--duration", type=int, default=10, choices=(5, 10))
    p.add_argument("--no-element", action="store_true")
    args = p.parse_args()

    event = _event_dir()
    prod = _prod_root(event)
    os.environ["MN_PROD_ROOT"] = str(prod)
    bases = prod / "assets" / "lipsync_bases"
    bases.mkdir(parents=True, exist_ok=True)

    still = args.still
    if still is None:
        for candidate in (
            event / "phase_a_arlo_wizard_desk_v1.png",
            prod / "Arlo" / "poses" / "arlo_wizard_room_desk_v1.png",
            prod / "Arlo" / "poses" / "arlo_wizard_room_neutral_vest.png",
            prod / "Arlo" / "poses" / "arlo_canonical_neutral_vest.png",
        ):
            if candidate.is_file():
                still = candidate
                break
    if still is None or not still.expanduser().resolve().is_file():
        log(f"FATAL: no Arlo wizard desk still found under {event} or Production/Arlo/poses")
        return 1
    still = still.expanduser().resolve()

    raw = still.read_bytes()
    png, info, _ = ensure_min_dimensions(raw)
    log(f"Start frame: {still.name} — {info}")
    start_uri = f"data:image/png;base64,{base64.b64encode(png).decode('ascii')}"

    keys = load_api_keys()
    element = None
    if not args.no_element:
        arlo = assert_arlo_element(prod)
        log(
            f"Arlo element OK: id={arlo['element_id']} "
            f"refers={arlo.get('refer_images')}"
        )
        element = {
            "element_id": str(arlo["element_id"]),
            "element_name": arlo.get("element_name", "Arlo"),
        }

    log("Submitting Kling single-image idle (Arlo wizard desk)")
    task_id = kling_startend_submit(
        start_uri, None,
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

    print(json.dumps({
        "clip_id": args.clip_id,
        "mp4": out.name,
        "still": still.name,
        "size_mb": round(out.stat().st_size / 1024 / 1024, 1),
    }))
    return 0


# Legacy import surface — old scripts/tests; Arlo is canonical for Phase A base.
CHIPPER_ELEMENT_ID = ARLO_ELEMENT_ID
STALE_CHIPPER_ELEMENT_IDS: frozenset[str] = frozenset()


def assert_chipper_feather_element(prod: Path) -> dict:
    """Deprecated alias — Phase A base generation uses Arlo element now."""
    return assert_arlo_element(prod)


if __name__ == "__main__":
    sys.exit(main())
