"""
Stillgen Schema Migration — prod_visual_assets provenance fields (2026-04-21)

Adds 13 provenance fields needed for the stillgen Phase 1 endpoint (handoff §7).
Idempotent: existing fields are skipped. Additive-only (no drops, no renames, no type changes).

After schema adds, backfills is_current=true for all existing rows per Kim's explicit
migration instruction 2026-04-21.

Pre-migration duplicate scan flagged 5 groups with >1 row (see prod_activity_log
id 1108 / task_id scope-reversal-benson-back-20260421 era + newer scan in this
cascade). 4 of those 5 are parallel options (not supersession — peer candidates
pending Kim review). 1 of those 5 is a v1→v4 tool HTML sequence where only v4
is truly current. After the blanket is_current=true backfill, that sequence will
be flagged as a session_decision for Kim to PATCH correctly later — safer than
guessing supersession semantics without Kim's sign-off.

Usage:
    python3 Production/scripts/stillgen_schema_migration_20260421.py --dry-run
    python3 Production/scripts/stillgen_schema_migration_20260421.py --apply

Rule 19: Python urllib only (via lib.directus_admin_client). Two-Write Rule honored
(each field create + backfill paired with activity_log row).
Task id: stillgen-addon-phase0-resolutions-20260421
"""
from __future__ import annotations
import argparse, sys, json, time
sys.path.insert(0, "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production")
from lib.directus_admin_client import DirectusAdminClient

COLLECTION = "prod_visual_assets"
TASK_ID = "stillgen-addon-phase0-resolutions-20260421"

# Field definitions — per handoff §7 + Phase 0 findings
# Each entry: (name, directus_type, interface, default_value, is_nullable, note)
FIELDS = [
    ("character_id",             "string",    "input",         None,  True,  "Character this asset depicts (e.g., 'benson', 'tessa'). FK to prod_creatures.creature_id by convention."),
    ("is_current",               "boolean",   "boolean",       True,  False, "Is this the current live version of the asset? false = superseded."),
    ("superseded_by_id",         "integer",   "input",         None,  True,  "If is_current=false, which prod_visual_assets.id supersedes this one."),
    ("generated_by",             "string",    "input",         None,  True,  "Who/what generated: e.g., 'replicate:flux-2-pro', 'bfl:flux-kontext-pro', 'kim:manual', 'openai:gpt-image-1.5'."),
    ("flux_model",               "string",    "input",         None,  True,  "Specific model variant if FLUX family, e.g., 'flux-2-pro', 'flux-kontext-pro', 'flux-1.1-pro'."),
    ("hero_reference_asset_id",  "integer",   "input",         None,  True,  "If generated with a hero reference, the prod_visual_assets.id of that hero master. Distinct from source_asset_id (which may be a crop parent)."),
    ("file_size_bytes",          "integer",   "input",         None,  True,  "File size in bytes. Rule 23 SIZE_BUDGET_V1 enforcement expects this on all new writes."),
    ("role",                     "string",    "select-dropdown", None, True, "'master' | 'delivery' | 'intermediate'. Per Rule 6.1 masters/delivery split."),
    ("parent_asset_id",          "integer",   "input",         None,  True,  "If this is a derived asset (e.g., a crop from a master), the prod_visual_assets.id of the parent."),
    ("sha256",                   "string",    "input",         None,  True,  "SHA256 of the file contents (64 hex chars). Per-handoff-§7 counter-agent β integrity gate."),
    ("generated_at",             "timestamp", "datetime",      None,  True,  "UTC timestamp when the underlying generator produced the file (may precede Directus created_at)."),
    ("replicate_job_id",         "string",    "input",         None,  True,  "If generated via Replicate, the prediction id for traceability and cost reconciliation."),
    ("estimated_cost_usd",       "float",     "input",         None,  True,  "Per-generation cost estimate in USD (e.g., 0.08 for FLUX Kontext Pro)."),
]

INTERFACE_CHOICES = {
    "role": [
        {"text": "master", "value": "master"},
        {"text": "delivery", "value": "delivery"},
        {"text": "intermediate", "value": "intermediate"},
    ],
}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true", help="Actually execute the migration")
    p.add_argument("--dry-run", action="store_true", help="Preview only (default)")
    p.add_argument("--skip-backfill", action="store_true", help="Only add fields; skip is_current backfill")
    args = p.parse_args()
    apply = args.apply
    if not apply and not args.dry_run:
        print("Note: no flag given — defaulting to --dry-run. Pass --apply to execute.")

    c = DirectusAdminClient()

    # Read existing fields so we can skip what already exists
    existing = c.fields(COLLECTION)
    existing_names = {f.get("field") for f in existing}
    print(f"Existing fields in {COLLECTION}: {sorted(existing_names)}")
    print(f"\nPlanned additions: {len(FIELDS)}")

    # Log migration start
    if apply:
        c.post_item("prod_activity_log", {
            "action": "stillgen_schema_migration_start",
            "details": {"task_id": TASK_ID, "collection": COLLECTION, "planned_fields": [f[0] for f in FIELDS]},
            "performed_by": "claude",
        })

    added = []
    skipped = []
    failed = []
    for name, dtype, interface, default, nullable, note in FIELDS:
        if name in existing_names:
            print(f"  SKIP {name} (exists)")
            skipped.append(name)
            continue
        body = {
            "field": name,
            "type": dtype,
            "meta": {
                "collection": COLLECTION,
                "field": name,
                "interface": interface,
                "hidden": False,
                "readonly": False,
                "width": "full",
                "note": note,
            },
            "schema": {
                "name": name,
                "table": COLLECTION,
                "data_type": dtype,
                "is_nullable": nullable,
                "default_value": default,
            },
        }
        if name in INTERFACE_CHOICES:
            body["meta"]["options"] = {"choices": INTERFACE_CHOICES[name]}
        if apply:
            try:
                result = c._request("POST", f"/fields/{COLLECTION}", data=body)
                added.append(name)
                print(f"  ADD  {name}  type={dtype}  nullable={nullable}  default={default}")
                c.post_item("prod_activity_log", {
                    "action": "stillgen_schema_migration_field_added",
                    "details": {"task_id": TASK_ID, "collection": COLLECTION, "field": name,
                                "type": dtype, "nullable": nullable, "default": default},
                    "performed_by": "claude",
                })
            except Exception as e:
                failed.append((name, str(e)[:300]))
                print(f"  FAIL {name}: {e}")
        else:
            print(f"  DRY  {name}  type={dtype}  nullable={nullable}  default={default}")

    print(f"\nSchema summary: added={len(added)} skipped={len(skipped)} failed={len(failed)}")
    for n, msg in failed:
        print(f"  FAILED: {n} — {msg}")

    # Backfill is_current=true for all rows (if not skipped and not a dry run)
    backfill_info = {"skipped": True}
    if apply and not args.skip_backfill and "is_current" in added:
        print("\nBackfilling is_current=true for existing rows...")
        time.sleep(1.0)  # Let Directus finalize the column
        all_rows = c.get_items(COLLECTION, fields=["id"], limit=-1)
        total = len(all_rows)
        print(f"  {total} rows to update")
        # PATCH in chunks to avoid huge payloads
        CHUNK = 25
        updated = 0
        for i in range(0, total, CHUNK):
            chunk = [r["id"] for r in all_rows[i:i+CHUNK]]
            try:
                c.patch_items_bulk(COLLECTION, chunk, {"is_current": True})
                updated += len(chunk)
                print(f"    batch {i//CHUNK + 1}: {len(chunk)} rows → OK  (total {updated}/{total})")
            except Exception as e:
                print(f"    batch {i//CHUNK + 1} ERR: {str(e)[:200]}")
        backfill_info = {"skipped": False, "total": total, "updated": updated}
        c.post_item("prod_activity_log", {
            "action": "stillgen_schema_migration_backfill_complete",
            "details": {"task_id": TASK_ID, "collection": COLLECTION, **backfill_info},
            "performed_by": "claude",
        })

    # Final summary log
    if apply:
        c.post_item("prod_activity_log", {
            "action": "stillgen_schema_migration_complete",
            "details": {"task_id": TASK_ID, "collection": COLLECTION,
                        "added": added, "skipped": skipped, "failed": failed,
                        "backfill": backfill_info},
            "performed_by": "claude",
        })

    print("\nDone.")
    return added, skipped, failed, backfill_info


if __name__ == "__main__":
    main()
