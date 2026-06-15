#!/usr/bin/env python3
"""Phase A fly-in + fly-out — close-up framing matched to sitting crop.

Uses paired stills (empty desk ↔ Chipper) at the SAME crop/zoom so scale
matches the middle lipsync clip at xfade joins.

Outputs:
  Event_*/phase_a_flyin_closeup_match_<ts>.mp4
  Event_*/phase_a_flyout_closeup_match_<ts>.mp4

Pins filenames to production_state.json when --pin (default).
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.request
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

FLYIN_PROMPT = (
    "Smooth magical transition: empty wizard desk fills with warm firelight. "
    "Chipper the magpie materializes on the desk facing the camera, wings folded "
    "at his sides. Same medium close-up framing as the end frame. "
    "Beak closed, no dialogue. Background cozy study stays still."
)

FLYOUT_PROMPT = (
    "Chipper the magpie on the wizard desk gently lifts off, wings folded then "
    "spreading as he flies up and away. Same medium close-up framing as start. "
    "Desk returns to empty. Beak closed, no dialogue. Warm firelit study."
)

NEGATIVE = (
    RULE8_ANTI_LIPSYNC + ", "
    "teeth, fangs, human hands, wing gesticulation, extra wings, "
    "scale change, zoom in, camera move, wide shot, tiny bird, huge bird"
)

DURATION = 5


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


def _resolve_stills(event: Path) -> tuple[Path, Path]:
    """Prefer v3 paired crops; fall back to legacy wide stills."""
    chipper_v3 = event / "phase_a_chipper_closeup_crop_v3.png"
    empty_v3 = event / "phase_a_empty_desk_crop_v3.png"
    if chipper_v3.is_file() and empty_v3.is_file():
        return empty_v3, chipper_v3
    chipper = event / "phase_a_chipper_closeup_newstyle_v2.png"
    empty = event / "phase_a_empty_desk_v2.png"
    if not chipper.is_file():
        chipper = event / "phase_a_chipper_on_desk_wide.png"
    if not empty.is_file():
        empty = event / "phase_a_empty_desk.png"
    if not chipper.is_file() or not empty.is_file():
        raise FileNotFoundError(
            f"Need paired stills in {event} (v3 crops or legacy wide PNGs)"
        )
    return empty, chipper


def _encode(path: Path) -> str:
    raw = path.read_bytes()
    png, info, _ = ensure_min_dimensions(raw)
    log(f"  {path.name}: {info}")
    return f"data:image/png;base64,{base64.b64encode(png).decode('ascii')}"


def _download(url: str, dst: Path) -> None:
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                dst.write_bytes(r.read())
            log(f"  downloaded {dst.name} ({dst.stat().st_size / 1024 / 1024:.1f} MB)")
            return
        except Exception as exc:
            log(f"  dl attempt {attempt + 1}: {exc}")
            time.sleep(3 * (2 ** attempt))
    raise RuntimeError(f"download failed: {url}")


def _run_kling(
    tag: str,
    start: Path,
    end: Path,
    prompt: str,
    api_key: str,
    event: Path,
    element_entry: dict | None,
) -> Path:
    log(f"=== {tag.upper()} ===")
    log(f"  start: {start.name}")
    log(f"  end:   {end.name}")
    task_id = kling_startend_submit(
        _encode(start), _encode(end),
        prompt=prompt, negative_prompt=NEGATIVE,
        duration=DURATION, api_key=api_key,
        element_entry=element_entry,
    )
    log(f"  task_id: {task_id}")
    result = kling_poll_fresh(task_id, api_key, timeout_s=900)
    if (result.get("status") or "").lower() != "completed":
        raise RuntimeError(f"Kling {tag} failed: {result}")
    url = (result.get("outputs") or [None])[0]
    if not url:
        raise RuntimeError(f"no output url for {tag}")
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dst = event / f"phase_a_{tag}_closeup_match_{ts}.mp4"
    _download(url, dst)
    return dst


def _pin_state(event: Path, flyin: Path, flyout: Path) -> None:
    state_path = event / "production_state.json"
    if not state_path.is_file():
        log("  WARN: no production_state.json — skip pin")
        return
    state = json.loads(state_path.read_text())
    state["phase_a_flyin_file"] = flyin.name
    state["phase_a_flyout_file"] = flyout.name
    pa = state.setdefault("phase_a", {})
    if isinstance(pa, dict):
        pa["phase_a_flyin_file"] = flyin.name
        pa["phase_a_flyout_file"] = flyout.name
    state_path.write_text(json.dumps(state, indent=2))
    log(f"  pinned {flyin.name} {flyout.name}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--no-pin", action="store_true", help="Do not update production_state.json")
    p.add_argument("--no-element", action="store_true", help="Skip Kling Elements binding")
    args = p.parse_args()

    event = _event_dir()
    empty, chipper = _resolve_stills(event)
    log(f"Using empty desk still: {empty.name}")
    log(f"Using Chipper closeup still: {chipper.name}")

    keys = load_api_keys()
    element = None if args.no_element else _load_subject_element("Chipper")

    flyin = _run_kling("flyin", empty, chipper, FLYIN_PROMPT, keys["wavespeed"], event, element)
    flyout = _run_kling("flyout", chipper, empty, FLYOUT_PROMPT, keys["wavespeed"], event, element)

    if not args.no_pin:
        _pin_state(event, flyin, flyout)

    out = {
        "flyin_mp4": flyin.name,
        "flyout_mp4": flyout.name,
        "flyin_size_mb": round(flyin.stat().st_size / 1024 / 1024, 2),
        "flyout_size_mb": round(flyout.stat().st_size / 1024 / 1024, 2),
    }
    log("=== DONE ===")
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
