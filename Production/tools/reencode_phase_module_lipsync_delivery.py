#!/usr/bin/env python3
"""Re-encode an existing phase module lipsync MP4 through voice_first_upscale (in-place).

Use when delivery encode was added after lipsync was already on disk — no new Kling job.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from phase_module_lipsync_delivery import (  # noqa: E402
    PHASE_MODULE_LIPSYNC_DELIVERY_RECIPE_CURRENT,
    finalize_phase_module_lipsync_delivery,
    resolve_module_lipsync_reencode_source,
)


def _event_dir(name: str) -> Path:
    dropbox = (
        Path.home()
        / "Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production"
    )
    path = dropbox / name
    if not path.is_dir():
        raise FileNotFoundError(f"event dir not found: {path}")
    return path


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--event", default="Event_2", help="Event folder name (default Event_2)")
    p.add_argument("--phase", default="b", choices=("a", "b"))
    p.add_argument(
        "--lipsync",
        type=Path,
        help="Explicit lipsync MP4 path (default: pinned phase_{phase}_lipsync_file from production_state)",
    )
    p.add_argument("--no-backup", action="store_true", help="Skip .bak copy before in-place encode")
    args = p.parse_args()

    event_dir = _event_dir(args.event)
    if args.lipsync:
        lipsync_path = args.lipsync.expanduser().resolve()
    else:
        state_path = event_dir / "production_state.json"
        if not state_path.is_file():
            print(f"FATAL: no production_state.json in {event_dir}", file=sys.stderr)
            return 1
        state = json.loads(state_path.read_text(encoding="utf-8"))
        name = (state.get(f"phase_{args.phase}_lipsync_file") or "").strip()
        if not name:
            print(f"FATAL: phase_{args.phase}_lipsync_file unset in production_state", file=sys.stderr)
            return 1
        try:
            lipsync_path = resolve_module_lipsync_reencode_source(event_dir, name)
        except FileNotFoundError:
            lipsync_path = (event_dir / name).resolve()

    out_name = lipsync_path.name.replace("_reframed", "")
    if out_name == lipsync_path.name and not out_name.endswith("_raw.mp4"):
        out_path = event_dir / out_name.replace(".mp4", "_v3_delivery.mp4")
    else:
        out_path = event_dir / out_name if out_name != lipsync_path.name else lipsync_path

    if not lipsync_path.is_file():
        print(f"FATAL: lipsync not found: {lipsync_path}", file=sys.stderr)
        return 1

    if out_path.resolve() == lipsync_path.resolve():
        if not args.no_backup:
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup = lipsync_path.with_suffix(lipsync_path.suffix + f".pre_delivery_{ts}.bak")
            shutil.copy2(lipsync_path, backup)
            print(f"backup: {backup}")
        meta = finalize_phase_module_lipsync_delivery(lipsync_path, sharpen=True)
    else:
        meta = finalize_phase_module_lipsync_delivery(
            lipsync_path, dest_path=out_path, sharpen=True,
        )
        print(f"output: {out_path}")
        print(f"recipe: {PHASE_MODULE_LIPSYNC_DELIVERY_RECIPE_CURRENT}")
    print(json.dumps(meta, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
