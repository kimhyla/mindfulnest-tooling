#!/usr/bin/env python3
"""Restore Beat Gen / Stitcher / Phase A/B state from durable snapshots.

When Kim says "restore the beats", run:
  python3 Production/scripts/restore_production_snapshot.py --latest

Examples:
  python3 Production/scripts/restore_production_snapshot.py --latest
  python3 Production/scripts/restore_production_snapshot.py --latest --event Event_2
  python3 Production/scripts/restore_production_snapshot.py --snapshot-id 20260616T141500Z
  python3 Production/scripts/restore_production_snapshot.py --latest --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve()
_LIB = _SCRIPT.parent.parent / "lib"
if str(_LIB.parent) not in sys.path:
    sys.path.insert(0, str(_LIB.parent))

from lib.paths import dropbox_root  # noqa: E402
from lib import production_snapshot as snap  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Restore production state snapshots")
    ap.add_argument(
        "--prod-root",
        type=Path,
        default=dropbox_root() / "Production",
        help="Production/ directory (default: Dropbox Production/)",
    )
    ap.add_argument("--latest", action="store_true", help="Restore rolling latest snapshot")
    ap.add_argument("--snapshot-id", default="", help="Restore named archive under .production_snapshots/archive/")
    ap.add_argument(
        "--event",
        action="append",
        default=[],
        help="Limit restore to Event_N (repeatable). Omit for all events.",
    )
    ap.add_argument("--dry-run", action="store_true", help="Show what would be restored")
    ap.add_argument(
        "--no-pre-backup",
        action="store_true",
        help="Skip pre-restore safety archive",
    )
    ap.add_argument("--list", action="store_true", help="List available archives and exit")
    args = ap.parse_args()

    prod = args.prod_root.resolve()
    if not prod.is_dir():
        print(f"FATAL: prod root missing: {prod}", file=sys.stderr)
        return 1

    if args.list:
        latest = snap.snapshot_root(prod) / snap.LATEST_DIR_NAME
        print(json.dumps({
            "latest": str(latest) if latest.is_dir() else None,
            "archives": snap.list_archives(prod),
        }, indent=2))
        return 0

    if not args.latest and not args.snapshot_id:
        print("FATAL: pass --latest or --snapshot-id (or --list)", file=sys.stderr)
        return 1

    try:
        result = snap.restore_snapshot(
            prod,
            latest=bool(args.latest),
            snapshot_id=args.snapshot_id or None,
            events=args.event or None,
            dry_run=args.dry_run,
            pre_restore_backup=not args.no_pre_backup,
        )
    except FileNotFoundError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    if not args.dry_run:
        print(
            "\nRestore complete. Restart affected event storyboard servers and hard-refresh "
            "Beat Generator / Stitcher / Phase tabs.",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
