#!/usr/bin/env python3
"""Logical Directus restore dry-run / apply via Phase 0 rsync backup comparison.

Per V59 spec §0 Phase 0 / Agent A amendment A4. Compares prod_modules and
prod_assets against ~/Backups/mindfulnest_phase0_start_* backup projection;
append-only collections are documented and skipped. Default is dry-run only.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(REPO_ROOT))

from Production.lib.directus import try_patch_or_queue, try_post_or_queue  # noqa: E402
from Production.lib.directus_admin_client import DirectusAdminClient  # noqa: E402

BACKUP_GLOB = "mindfulnest_phase0_start_*/event_state/production_state.json"
COMPARE_COLLECTIONS = ("prod_modules", "prod_assets")
SKIP_COLLECTIONS = ("prod_locked_decisions", "prod_activity_log")

# Scalar fields compared when present in both backup and current rows.
MODULE_COMPARE_FIELDS = (
    "m_number",
    "creature_name",
    "technique_name",
    "spell_name",
    "arc_number",
    "video_role",
    "stage_status",
    "current_stage",
)
ASSET_COMPARE_FIELDS = (
    "file_path",
    "asset_type",
    "status",
    "module_id",
    "beat_id",
    "event_id",
)


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "Z"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _find_backup_state(snapshot_ts: str) -> Path:
    backups_root = Path.home() / "Backups"
    if not backups_root.is_dir():
        raise FileNotFoundError(f"Backups directory not found: {backups_root}")

    # Prefer directory whose name embeds the snapshot timestamp.
    needle = snapshot_ts.replace("T", "").replace("Z", "")
    candidates = sorted(backups_root.glob(BACKUP_GLOB))
    if not candidates:
        raise FileNotFoundError(
            f"No backup matching {BACKUP_GLOB} under {backups_root}"
        )

    for path in candidates:
        if needle in str(path):
            return path

    # Fallback: newest phase0_start backup.
    return candidates[-1]


def _load_backup_projection(backup_state_path: Path) -> tuple[list[dict], list[dict]]:
    """Load prod_modules / prod_assets rows from backup tree."""
    backup_root = backup_state_path.parent.parent
    modules_path = backup_root / "prod_modules.json"
    assets_path = backup_root / "prod_assets.json"

    modules: list[dict] = []
    assets: list[dict] = []

    if modules_path.is_file():
        modules = json.loads(modules_path.read_text(encoding="utf-8"))
        if isinstance(modules, dict) and "data" in modules:
            modules = modules["data"]
    if assets_path.is_file():
        assets = json.loads(assets_path.read_text(encoding="utf-8"))
        if isinstance(assets, dict) and "data" in assets:
            assets = assets["data"]

    if not modules and not assets:
        state = json.loads(backup_state_path.read_text(encoding="utf-8"))
        if isinstance(state.get("prod_modules"), list):
            modules = state["prod_modules"]
        if isinstance(state.get("prod_assets"), list):
            assets = state["prod_assets"]

    if not isinstance(modules, list):
        modules = []
    if not isinstance(assets, list):
        assets = []

    return modules, assets


def _index_by_id(rows: list[dict]) -> dict[Any, dict]:
    out: dict[Any, dict] = {}
    for row in rows:
        rid = row.get("id")
        if rid is not None:
            out[rid] = row
    return out


def _compare_collection(
    collection: str,
    backup_rows: list[dict],
    current_rows: list[dict],
    fields: tuple[str, ...],
) -> list[dict]:
    mismatches: list[dict] = []
    backup_by_id = _index_by_id(backup_rows)
    current_by_id = _index_by_id(current_rows)

    for module_id, backup_row in backup_by_id.items():
        current_row = current_by_id.get(module_id)
        if current_row is None:
            mismatches.append(
                {
                    "collection": collection,
                    "module_id": module_id,
                    "field": "*",
                    "current": "<missing>",
                    "backup": "<present>",
                }
            )
            print(
                f"MISMATCH module_id={module_id} field=* "
                f"current=<missing> backup=<present>"
            )
            continue
        for field in fields:
            if field not in backup_row:
                continue
            bval = backup_row.get(field)
            cval = current_row.get(field)
            if bval != cval:
                mismatches.append(
                    {
                        "collection": collection,
                        "module_id": module_id,
                        "field": field,
                        "current": cval,
                        "backup": bval,
                    }
                )
                print(
                    f"MISMATCH module_id={module_id} field={field} "
                    f"current={cval!r} backup={bval!r}"
                )
    return mismatches


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Directus logical restore via backup comparison (dry-run default)"
    )
    parser.add_argument(
        "--snapshot-timestamp",
        required=True,
        help="Backup timestamp YYYYMMDDTHHMMSSZ",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="PATCH mismatched fields back to backup values (default: dry run)",
    )
    args = parser.parse_args()

    client = DirectusAdminClient()
    ts_label = _utc_stamp()

    for col in SKIP_COLLECTIONS + COMPARE_COLLECTIONS:
        try:
            rows = client.get_items(col, limit=-1) or []
            print(f"COUNT {col}={len(rows)}")
        except Exception as e:
            print(f"COUNT {col}=error ({type(e).__name__}: {e})", file=sys.stderr)

    print(
        f"SKIP append-only collections: {', '.join(SKIP_COLLECTIONS)} "
        "(no restore needed — audit trail preserved)"
    )

    backup_state = _find_backup_state(args.snapshot_timestamp)
    print(f"BACKUP_STATE={backup_state}")
    backup_modules, backup_assets = _load_backup_projection(backup_state)
    print(f"BACKUP_ROWS prod_modules={len(backup_modules)} prod_assets={len(backup_assets)}")

    current_modules = client.get_items("prod_modules", limit=-1) or []
    current_assets = client.get_items("prod_assets", limit=-1) or []

    all_mismatches: list[dict] = []
    all_mismatches.extend(
        _compare_collection(
            "prod_modules", backup_modules, current_modules, MODULE_COMPARE_FIELDS
        )
    )
    all_mismatches.extend(
        _compare_collection(
            "prod_assets", backup_assets, current_assets, ASSET_COMPARE_FIELDS
        )
    )

    action = f"DIRECTUS_RESTORE_DRY_RUN_{ts_label}"
    if args.apply:
        action = f"DIRECTUS_RESTORE_APPLIED_{ts_label}"
        patched = 0
        for m in all_mismatches:
            if m.get("field") == "*":
                continue
            col = m["collection"]
            row_id = m["module_id"]
            field = m["field"]
            patch = {field: m["backup"]}
            try_patch_or_queue(col, row_id, patch, client=client)
            patched += 1
        print(f"APPLY_PATCHES count={patched}")

    try_post_or_queue(
        "prod_activity_log",
        {
            "action": action,
            "details": {
                "snapshot_timestamp": args.snapshot_timestamp,
                "backup_state_path": str(backup_state),
                "mismatch_count": len(all_mismatches),
                "mismatches": all_mismatches,
                "apply": args.apply,
                "at": _now_iso(),
            },
            "performed_by": "restore_directus_snapshot",
        },
        client=client,
    )

    print(f"RESTORE_SUMMARY mismatches={len(all_mismatches)} apply={args.apply}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
