#!/usr/bin/env python3
"""Create a durable production-state snapshot (Beat Gen + Stitcher + Phase A/B).

Examples:
  python3 Production/scripts/backup_production_snapshot.py
  python3 Production/scripts/backup_production_snapshot.py --archive-only
  python3 Production/scripts/backup_production_snapshot.py --prod-root ~/Dropbox/.../Production
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
    ap = argparse.ArgumentParser(description="Backup Beat Gen / Stitcher / Phase state")
    ap.add_argument(
        "--prod-root",
        type=Path,
        default=dropbox_root() / "Production",
        help="Production/ directory (default: Dropbox Production/)",
    )
    ap.add_argument(
        "--archive-only",
        action="store_true",
        help="Skip rolling latest; create timestamped archive only",
    )
    ap.add_argument("--label", default="", help="Optional label stored in manifest")
    args = ap.parse_args()

    prod = args.prod_root.resolve()
    if not prod.is_dir():
        print(f"FATAL: prod root missing: {prod}", file=sys.stderr)
        return 1

    if not args.archive_only:
        rolling = snap.create_snapshot(prod, source="cli_backup", label=args.label or "cli_rolling")
        print(json.dumps({
            "ok": True,
            "kind": "rolling",
            "snapshot_dir": str(rolling.snapshot_dir),
            "files_copied": rolling.files_copied,
            "created_at": rolling.manifest.get("created_at"),
        }, indent=2))

    archive = snap.maybe_create_archive_snapshot(prod, source="cli_backup", force=True)
    if archive:
        print(json.dumps({
            "ok": True,
            "kind": "archive",
            "snapshot_dir": str(archive.snapshot_dir),
            "files_copied": archive.files_copied,
            "created_at": archive.manifest.get("created_at"),
        }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
