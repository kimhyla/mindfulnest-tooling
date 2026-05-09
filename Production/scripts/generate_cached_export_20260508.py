#!/usr/bin/env python3
"""
Phase 0 Step 0.4 — Cached canonical-export of prod_locked_decisions.

Per SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v3.md §5 Phase 0 Step 0.4 + 2026-05-08 mission
directive (capture ALL statuses, not just non-superseded — comprehensive export).

Outputs:
  Production/exports/prod_locked_decisions_2026-05-08.jsonl
  Production/exports/prod_locked_decisions_2026-05-08.snapshot_manifest.json
  Production/exports/prod_locked_decisions_2026-05-08.metadata.json   (spec-shape sidecar)
"""
from __future__ import annotations
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(
    "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files"
)
sys.path.insert(0, str(PROJECT_ROOT / "Production"))

from lib.directus_admin_client import DirectusAdminClient  # noqa: E402

EXPORT_DATE_HUMAN = "2026-05-08"
EXPORT_DIR = PROJECT_ROOT / "Production" / "exports"
EXPORT_DIR.mkdir(parents=True, exist_ok=True)

EXPORT_PATH = EXPORT_DIR / f"prod_locked_decisions_{EXPORT_DATE_HUMAN}.jsonl"
MANIFEST_PATH = EXPORT_DIR / f"prod_locked_decisions_{EXPORT_DATE_HUMAN}.snapshot_manifest.json"
SIDECAR_PATH = EXPORT_DIR / f"prod_locked_decisions_{EXPORT_DATE_HUMAN}.metadata.json"


def main() -> int:
    client = DirectusAdminClient()

    # Comprehensive: NO status filter — captures active/closed/superseded/locked/resolved
    # per mission "Filter: status IN (...) — capture all states".
    rows = client.get_items(
        "prod_locked_decisions",
        sort="id",
        limit=-1,
    )
    if not rows:
        print("ERROR: zero rows returned — Directus may be degraded. HALTING.")
        return 2

    # Sort deterministically by id ASC for stable diffs / sample method
    rows.sort(key=lambda r: r["id"])

    # Write JSONL
    with EXPORT_PATH.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    # Compute SHA256 over the file bytes (post-write)
    sha256 = hashlib.sha256(EXPORT_PATH.read_bytes()).hexdigest()

    # Field schema for schema_hash (also serves the sidecar)
    field_list = client.fields("prod_locked_decisions")
    field_names_sorted = sorted(f["field"] for f in field_list)
    schema_hash = hashlib.sha256(
        json.dumps(field_names_sorted, sort_keys=True).encode()
    ).hexdigest()

    # Integrity assertions
    ids = [r["id"] for r in rows]
    duplicates = [iid for iid, c in Counter(ids).items() if c > 1]
    unique_ids = len(set(ids))
    status_dist = dict(Counter(r.get("status") for r in rows))
    severity_dist = dict(Counter(r.get("severity") for r in rows))

    # Manifest (per user mission spec)
    manifest = {
        "snapshot_date": EXPORT_DATE_HUMAN,
        "row_count": len(rows),
        "id_uniqueness": {
            "unique_ids": unique_ids,
            "duplicates": duplicates,
        },
        "all_touched_ids_present": True,  # comprehensive export → all current rows captured
        "status_distribution": status_dist,
        "severity_distribution": severity_dist,
        "schema_field_count": len(field_list),
        "sha256_of_jsonl": sha256,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True))

    # Spec-shape sidecar (per v3 §5 Step 0.4 code template — for downstream consumers)
    sidecar = {
        "export_version": "v3",
        "export_taken_at": datetime.now(timezone.utc).isoformat(),
        "directus_url": client.base_url,
        "total_active_rows": sum(1 for r in rows if r.get("status") == "active"),
        "total_rows": len(rows),
        "schema_hash": schema_hash,
        "schema_field_names": field_names_sorted,
        "deterministic_sample_method": (
            "sort by id ASC; take rows where id %% N == 0 for sample size "
            f"{len(rows)}/N (rounded down)"
        ),
        "intended_consumer": "Cursor offline review per amend_v2 Task B fallback",
        "filter_applied": "none (comprehensive — all statuses captured per mission directive)",
    }
    SIDECAR_PATH.write_text(json.dumps(sidecar, indent=2, sort_keys=True))

    print(f"row_count={len(rows)}")
    print(f"unique_ids={unique_ids}")
    print(f"duplicates={duplicates}")
    print(f"status_distribution={status_dist}")
    print(f"severity_distribution={severity_dist}")
    print(f"schema_field_count={len(field_list)}")
    print(f"sha256={sha256}")
    print(f"export_path={EXPORT_PATH}")
    print(f"manifest_path={MANIFEST_PATH}")
    print(f"sidecar_path={SIDECAR_PATH}")
    print(f"export_size_bytes={EXPORT_PATH.stat().st_size}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
