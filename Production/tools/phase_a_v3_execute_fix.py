#!/usr/bin/env python3
"""Phase A v3 Chipper lipsync + stitch CLI.

Canonical implementation: phase_a_chipper_idle_lipsync.run_phase_a_chipper_idle_lipsync
Locked playbook: Production/docs/PHASE_A_CHIPPER_PIPELINE_LOCKED_v1.md

Usage:
  python3 phase_a_v3_execute_fix.py --lipsync-only
  python3 phase_a_v3_execute_fix.py --stitch-only phase_a_lipsync_<ts>.mp4
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from phase_a_chipper_idle_lipsync import (  # noqa: E402
    log,
    resolve_body_plate,
    run_phase_a_chipper_idle_lipsync,
)

EVENT_DIR = Path(os.environ.get("MN_EVENT_DIR", HERE.parent / "Event_1"))
STATE_PATH = EVENT_DIR / "production_state.json"


def load_state() -> dict:
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def save_state(state: dict) -> None:
    state["updated_at"] = datetime.now().astimezone().isoformat()
    state["_module_version"] = int(state.get("_module_version", 0) or 0) + 1
    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def resolve_voice_stem(state: dict) -> Path:
    name = state.get("phase_a_voice_stem_file") or (
        (state.get("phase_a") or {}).get("phase_a_voice_stem_file")
    )
    if not name:
        sys.exit("phase_a_voice_stem_file not set in state")
    path = EVENT_DIR / name
    if not path.is_file():
        sys.exit(f"voice stem missing: {path}")
    return path


def resolve_base_clip(state: dict, clip_id: str | None) -> Path:
    bases = HERE.parent / "assets" / "lipsync_bases"
    cid = (
        clip_id
        or state.get("phase_a_chipper_sitting_clip_id")
        or state.get("phase_a_empty_desk_bg_id")
        or "chipper_idle_newstyle_v3"
    )
    for ext in ("", ".mp4", ".mov"):
        p = bases / f"{cid}{ext}" if ext else bases / cid
        if p.is_file():
            return p
    sys.exit(f"base clip not found for id={cid} under {bases}")


def update_lipsync_state(out_name: str, mtime: int, base_clip_id: str | None) -> None:
    state = load_state()
    pairs = (
        ("phase_a_lipsync_file", out_name),
        ("phase_a_lipsync_mtime", mtime),
        ("phase_a_lipsync_status", "done"),
        ("phase_a_lipsync_method", "idle_kling_lipsync"),
    )
    for key, val in pairs:
        state[key] = val
        nested = state.setdefault("phase_a", {})
        if isinstance(nested, dict):
            nested[key] = val
    if base_clip_id:
        state["phase_a_chipper_sitting_clip_id"] = base_clip_id
        nested = state.setdefault("phase_a", {})
        if isinstance(nested, dict):
            nested["phase_a_chipper_sitting_clip_id"] = base_clip_id
    state.pop("phase_a_lipsync_task_id", None)
    save_state(state)


def restitch_via_server() -> dict:
    import urllib.error
    import urllib.request

    server = os.environ.get("MN_SERVER", "http://127.0.0.1:5111")
    event = os.environ.get("MN_EVENT_ID", Path(EVENT_DIR).name)
    body = json.dumps({
        "event_id": event,
        "scope_video_role": "intro",
        "phase": "a",
    }).encode()
    req = urllib.request.Request(
        f"{server}/api/phase_a/restitch",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        print(exc.read().decode(), file=sys.stderr)
        sys.exit(f"restitch HTTP {exc.code}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lipsync-only", action="store_true")
    ap.add_argument("--stitch-only", metavar="LIPSYNC_MP4")
    ap.add_argument("--base-clip-id", default=None)
    args = ap.parse_args()

    state = load_state()

    if args.stitch_only:
        lipsync_path = EVENT_DIR / args.stitch_only
        if not lipsync_path.is_file():
            sys.exit(f"lipsync file not found: {lipsync_path}")
        update_lipsync_state(
            lipsync_path.name,
            int(os.path.getmtime(lipsync_path)),
            state.get("phase_a_empty_desk_bg_id") or "chipper_idle_newstyle_v3",
        )
        result = restitch_via_server()
        name = (result.get("canonical") or {}).get("file", "")
        print(f"\nSTITCH: http://127.0.0.1:5111/files?path=Production/Event_1/{name}")
        return 0

    audio_raw = resolve_voice_stem(state)
    still = resolve_body_plate(EVENT_DIR, state)
    base_id = state.get("phase_a_chipper_sitting_clip_id")
    log(f"voice stem: {audio_raw.name} still: {still.name}")

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_name = f"phase_a_lipsync_{ts}.mp4"
    out_path = EVENT_DIR / out_name
    tmp_dir = EVENT_DIR / "_tmp_phase_a_idle_lipsync"
    run_phase_a_chipper_idle_lipsync(still, audio_raw, out_path, tmp_dir=tmp_dir)
    update_lipsync_state(out_name, int(os.path.getmtime(out_path)), base_id)

    preview = f"http://127.0.0.1:5111/files?path=Production/Event_1/{out_name}"
    log(f"MIDDLE PREVIEW: {preview}")

    if args.lipsync_only:
        print(f"\nLipsync only — preview middle: {preview}")
        return 0

    result = restitch_via_server()
    stitched = (result.get("canonical") or {}).get("file", "")
    print(f"\n=== DONE ===\nmiddle:  {preview}")
    print(f"stitch:  http://127.0.0.1:5111/files?path=Production/Event_1/{stitched}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
