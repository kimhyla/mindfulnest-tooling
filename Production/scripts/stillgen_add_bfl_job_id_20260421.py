"""
Stillgen migration — add bfl_job_id field to prod_visual_assets (2026-04-22).

Additive: nullable string. Mirrors the LD-355 schema migration pattern exactly so
the Phase 1 endpoint can record BFL job ids alongside Replicate job ids.

Locks LD STILLGEN_BFL_JOB_ID_FIELD_V1 (MEDIUM) per activity_log 1145 design.
Idempotent — re-running with field already present is a no-op.

Usage:
    python Production/scripts/stillgen_add_bfl_job_id_20260421.py --dry-run
    python Production/scripts/stillgen_add_bfl_job_id_20260421.py --apply
"""
from __future__ import annotations
import argparse, os, sys

# Make project root importable from any cwd.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, os.pardir, os.pardir))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from Production.lib.directus_admin_client import DirectusAdminClient

COLLECTION = "prod_visual_assets"
FIELD = "bfl_job_id"
TASK_ID = "stillgen-phase1-endpoint-build-20260421"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    apply = args.apply
    if not apply and not args.dry_run:
        print("No flag given — defaulting to --dry-run. Pass --apply to execute.")

    c = DirectusAdminClient()
    existing = c.fields(COLLECTION)
    names = {f.get("field") for f in existing}

    if FIELD in names:
        print(f"Field {COLLECTION}.{FIELD} already exists — nothing to do.")
        return 0

    body = {
        "field": FIELD,
        "type": "string",
        "meta": {
            "collection": COLLECTION,
            "field": FIELD,
            "interface": "input",
            "hidden": False,
            "readonly": False,
            "width": "full",
            "note": "If generated via BFL (FLUX Kontext Pro), the BFL task id for traceability and cost reconciliation. Nullable.",
        },
        "schema": {
            "name": FIELD,
            "table": COLLECTION,
            "data_type": "string",
            "is_nullable": True,
            "default_value": None,
        },
    }

    if not apply:
        print(f"DRY RUN — would add {COLLECTION}.{FIELD} (nullable string).")
        return 0

    c._request("POST", f"/fields/{COLLECTION}", data=body)
    print(f"ADDED {COLLECTION}.{FIELD}")
    c.post_item("prod_activity_log", {
        "action": "stillgen_schema_migration_field_added",
        "details": {"task_id": TASK_ID, "collection": COLLECTION, "field": FIELD, "ld": "STILLGEN_BFL_JOB_ID_FIELD_V1"},
        "performed_by": "claude",
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
