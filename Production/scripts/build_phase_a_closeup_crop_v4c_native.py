#!/usr/bin/env python3
"""Build phase_a_chipper_closeup_crop_v4c.png — native Kling desk, camera-forward (NO composite).

Fixes v4b gaze-at-hat failure: eyes/beak locked to lens, wings folded neutral.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROD = HERE.parent
EVENT = PROD / "Event_1"
TOOLS = PROD / "tools"

sys.path.insert(0, str(TOOLS))

from kling_startend_pipeline import (  # noqa: E402
    RULE8_ANTI_LIPSYNC,
    _load_subject_element,
    ensure_min_dimensions,
    kling_poll_fresh,
    kling_startend_submit,
    load_api_keys,
    log,
)

PROMPT = (
    "Chipper the magpie stands on the wizard desk in a firelit cozy study, "
    "body square to camera, eyes and beak looking DIRECTLY AT THE CAMERA LENS — "
    "NOT looking at the hat, NOT looking sideways. Medium close-up matching empty desk framing. "
    "Both wings folded still at his sides with hidden feather-tip wing ends only — "
    "no human fingers, no claws, no pointing, no wing gesticulation. "
    "TOOTH-FREE keratin beak, mouth closed. Same hat, bookshelf, chair as start frame. "
    "Fully integrated scene lighting — no cutout, no halo, no white fringe."
)

NEGATIVE = (
    RULE8_ANTI_LIPSYNC + ", "
    "looking at hat, looking down, profile view, three-quarter view, "
    "teeth, fangs, human hands, fingers, claws, pointing, presenting gesture, "
    "wing gesticulation, flapping, cutout, pasted, halo, white outline, composite, "
    "zoom, camera move, extra wings"
)


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--extract-at", type=float, default=1.0, help="Seconds into 5s clip for still")
    args = p.parse_args()

    env = os.environ.get("MN_EVENT_DIR", "").strip()
    event = Path(env).expanduser().resolve() if env else EVENT
    empty = event / "phase_a_empty_desk_crop_v3.png"
    out = event / "phase_a_chipper_closeup_crop_v4c.png"
    qa = event / "phase_a_hand_compare_20260608" / "V4C_NATIVE"
    qa.mkdir(parents=True, exist_ok=True)
    manifest_path = event / "phase_a_chipper_closeup_crop_v4c.manifest.json"

    if not empty.is_file():
        log(f"FATAL: missing {empty}")
        return 1

    raw = empty.read_bytes()
    png, info, _ = ensure_min_dimensions(raw)
    log(f"Empty desk start: {empty.name} — {info}")
    start_uri = f"data:image/png;base64,{base64.b64encode(png).decode('ascii')}"

    keys = load_api_keys()
    element = _load_subject_element("Chipper")
    if element:
        log(f"Element: {element['element_id']}")

    log("Submitting Kling single-image v4c camera-forward still (5s → extract frame)")
    task_id = kling_startend_submit(
        start_uri, None,
        prompt=PROMPT, negative_prompt=NEGATIVE,
        duration=5, api_key=keys["wavespeed"],
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

    staging_dir = qa / "_tmp_still"
    staging_dir.mkdir(parents=True, exist_ok=True)
    mp4 = staging_dir / f"kling_v4c_still_{task_id[:8]}.mp4"
    with urllib.request.urlopen(url, timeout=180) as r:
        mp4.write_bytes(r.read())
    log(f"Downloaded {mp4.name} ({mp4.stat().st_size / 1024 / 1024:.1f} MB)")

    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", str(args.extract_at), "-i", str(mp4),
        "-frames:v", "1", str(out),
    ], check=True)
    scaled = staging_dir / "_scaled.png"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(out),
        "-vf", "scale=800:600:force_original_aspect_ratio=increase,crop=800:600",
        str(scaled),
    ], check=True)
    subprocess.run(["cp", str(scaled), str(out)], check=True)

    manifest = {
        "artifact": out.name,
        "classification": "hidden_hands_desk_still_v4c_native_camera_forward",
        "method": "kling_single_image_on_empty_desk_crop_v3",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "kling_task_id": task_id,
        "element_id": element.get("element_id") if element else None,
        "empty_desk_md5": md5(empty),
        "output_md5": md5(out),
        "size": [800, 600],
        "extract_at_s": args.extract_at,
        "fixes": ["v4b_gaze_at_hat", "v4_composite_halo"],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
