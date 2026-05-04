#!/usr/bin/env python3
"""
backpopulate_asset_sizes.py — populate prod_assets.file_size_bytes for existing rows.

Source: SIZE_BUDGET_AUDIT_20260418.md §9 R-9.
Locked decisions: SIZE_BUDGET_V1 (id=295), LD-283 SIZE_BUDGET_PER_MODULE_V1.

Iterates prod_assets where file_size_bytes IS NULL, stats the file on disk, PATCHes the row.
Skips rows whose file_path is missing on disk (logs to app_blockers as data_drift).

Usage:
    python3 backpopulate_asset_sizes.py [--dry-run] [--require-min-rows N] [--module-filter PATTERN]

--require-min-rows N   Fail loud if fewer than N candidate rows are found
                       (guards against silently processing zero rows when path scoping is wrong).
--module-filter PAT    Glob pattern applied to row['file_path'] (e.g., "*Event_1*").

Run via:  doppler run -- python3 Production/scripts/backpopulate_asset_sizes.py
or with API_KEYS_MASTER.md fallback for transitional period.
"""
from __future__ import annotations
import argparse
import fnmatch
import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))
from lib.directus_admin_client import DirectusAdminClient, DirectusAdminError  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--require-min-rows", type=int, default=0,
                    help="Fail if fewer than N rows match the IS NULL filter")
    ap.add_argument("--module-filter", default=None,
                    help="Glob pattern on file_path (e.g. '*Event_1*')")
    ap.add_argument("--collection", default="prod_assets",
                    help="Directus collection name (default prod_assets)")
    args = ap.parse_args()

    c = DirectusAdminClient()

    rows = c.get_items(args.collection, filters={"file_size_bytes": {"_null": True}})
    if args.module_filter:
        rows = [r for r in (rows or []) if r.get("file_path") and fnmatch.fnmatch(r["file_path"], args.module_filter)]

    n = len(rows or [])
    print(f"[backpopulate] candidates: {n}")
    if n < args.require_min_rows:
        print(f"[backpopulate] FAIL: {n} < --require-min-rows {args.require_min_rows}", file=sys.stderr)
        return 2

    updated, missing, errors = 0, 0, 0
    for row in rows or []:
        fp = row.get("file_path")
        if not fp:
            continue
        # file_path may be relative to project root or absolute
        candidates = [fp,
                      os.path.expanduser(f"~/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/{fp}")]
        path = next((p for p in candidates if os.path.exists(p)), None)
        if not path:
            missing += 1
            print(f"[backpopulate] MISSING on disk: {fp}")
            continue
        size = os.path.getsize(path)
        if args.dry_run:
            print(f"[backpopulate] DRY id={row['id']} path={fp} size={size}")
            continue
        try:
            c._request("PATCH", f"/items/{args.collection}/{row['id']}", {"file_size_bytes": size})
            updated += 1
        except DirectusAdminError as e:
            errors += 1
            print(f"[backpopulate] ERR id={row['id']}: {e}", file=sys.stderr)

    print(f"[backpopulate] done. updated={updated} missing={missing} errors={errors}")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
