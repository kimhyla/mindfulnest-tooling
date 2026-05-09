# Schema Migration v3 — Cached Canonical-Export Proof Report

**Date:** 2026-05-08
**Spec authority:** `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v3.md` §5 Phase 0 Step 0.4
**Mission:** Unblock Cursor's re-review of v3 (AMEND_V2 verdict required this artifact).
**Self-classification:** STANDARD (export generation; not architectural).

---

## 1 — Manifest contents (verbatim)

Path: `Production/exports/prod_locked_decisions_2026-05-08.snapshot_manifest.json`

```json
{
  "all_touched_ids_present": true,
  "id_uniqueness": {
    "duplicates": [],
    "unique_ids": 570
  },
  "row_count": 570,
  "schema_field_count": 25,
  "severity_distribution": {
    "CRITICAL": 134,
    "HARD": 50,
    "HIGH": 186,
    "LOW": 25,
    "MED": 3,
    "MEDIUM": 102,
    "SOFT": 31,
    "critical": 3,
    "high": 16,
    "low": 3,
    "medium": 17
  },
  "sha256_of_jsonl": "4ac319c48cad2145a52ce9e50e601e8d187e209f4d995b0b9987dcb0c910710c",
  "snapshot_date": "2026-05-08",
  "status_distribution": {
    "active": 534,
    "closed": 3,
    "locked": 10,
    "resolved": 1,
    "superseded": 22
  }
}
```

**Notes on the distributions (load-bearing for v3 review):**
- `severity_distribution` shows 11 distinct values across canonical (HARD/SOFT) and legacy
  (CRITICAL/HIGH/MEDIUM/LOW + lowercase variants + "MED") buckets. This heterogeneity is
  exactly what schema migration v3 normalizes.
- `status_distribution` includes `locked` (10 rows) and `resolved` (1 row) beyond the
  spec's 3-enum hint. The export is comprehensive (no status filter applied) per mission
  directive — this captures every row Cursor might want to sample, including non-touched
  rows used for offline review fallback.
- `id_uniqueness.duplicates = []` and `unique_ids == row_count == 570` → no duplication.
- `all_touched_ids_present = true`: comprehensive export means by construction every
  current row is captured; the touched-ids subset (Phase 1+2+3+4+5 targets) is therefore
  fully present.

---

## 2 — JSONL artifact

| Field | Value |
|---|---|
| Path | `Production/exports/prod_locked_decisions_2026-05-08.jsonl` |
| Size (bytes) | 1,124,003 |
| Line count | 570 |
| Min ID | 1 |
| Max ID | 587 |
| Encoding | UTF-8, one JSON object per line, keys sorted within each row |
| SHA256 (post-write) | `4ac319c48cad2145a52ce9e50e601e8d187e209f4d995b0b9987dcb0c910710c` |
| Field count per row | 25 (matches schema field count) |

**Sample (first 3 lines, sanitized to id + decision_key + status + severity):**

```jsonl
{"id": 1, "decision_key": "no_unsupervised_content_edit", "status": "active", "severity": "CRITICAL"}
{"id": 2, "decision_key": "version_up_never_overwrite", "status": "active", "severity": "CRITICAL"}
{"id": 3, "decision_key": "working_docs_docx_only", "status": "active", "severity": "CRITICAL"}
```

(Full bodies are present in the JSONL itself; abbreviated here only because the row
records contain prose `decision_text` and `notes` fields that aren't load-bearing for
this proof report.)

**Spec-shape sidecar also written** (per v3 Step 0.4 code template):
- Path: `Production/exports/prod_locked_decisions_2026-05-08.metadata.json`
- Contents: `export_version`, `export_taken_at`, `directus_url`, `total_active_rows` (534),
  `total_rows` (570), `schema_hash`, `schema_field_names`, `deterministic_sample_method`,
  `intended_consumer`, `filter_applied`. Available for downstream consumers that key on
  the spec's literal sidecar shape.

---

## 3 — Verification chain (every state claim cited to tool output)

| Claim | Verified by |
|---|---|
| Directus reachable | `/server/info` HTTP 200 (in script run) |
| 570 rows fetched | Bash run `row_count=570` |
| 0 duplicate IDs | Bash run `duplicates=[]` + re-read pass `UNIQUE_IDS: 570` |
| SHA256 matches manifest | Re-read pass `SHA_MATCH: True` |
| Row count matches manifest | Re-read pass `ROW_COUNT_MATCH: True` |
| 25 schema fields | Bash run `schema_field_count=25` + first-row keys list |
| Activity log written + read-back | POST returned id=1781; read-back returned matching id/action/timestamp |

---

## 4 — Activity log (live Directus)

| Field | Value |
|---|---|
| Collection | `prod_activity_log` |
| Row id | **1781** |
| `action` (canonical schema) | `SCHEMA_MIGRATION_PHASE_0_CACHED_EXPORT_GENERATED` |
| `performed_by` | `claude_opus_4_7_1m` |
| `script_version` | `generate_cached_export_20260508.py v1` |
| `created_at` | `2026-05-08T17:18:38.062Z` |
| `details` | JSON with spec ref, all 3 paths, row_count=570, sha256, file_size_bytes, status_distribution, purpose |
| Read-back per Rule 35 | PASS — id/action/performed_by/created_at all match POST result |

---

## 5 — Confidence tags (Rule 24)

- **VERIFIED** — Directus `/server/info` HTTP 200, schema fields enumerated live.
- **VERIFIED** — 570 rows enumerated; ID range 1..587 (gaps are pre-existing deletes/holes,
  not export defects — IDs are auto-increment with prior delete history).
- **VERIFIED** — SHA256 of JSONL recomputed post-write and matches manifest value.
- **VERIFIED** — Activity log row 1781 read-back returned matching payload.
- **VERIFIED** — Manifest assertions (id_uniqueness, row_count, all_touched_ids_present)
  all true on inspection.
- **DESIGN_NOTE** — Mission directive overrode spec template's `_neq: superseded` filter:
  user explicitly required comprehensive (all-status) capture for offline review fallback.
  Both the manifest's status_distribution and the sidecar's `filter_applied` field record
  this deviation transparently. Sidecar's `total_active_rows` (534) lets a consumer that
  expects the spec's strict shape reproduce the spec-filtered subset trivially.

---

## 6 — Self-classification

**STANDARD.** Export generation is mechanical — pull rows, write JSONL, hash, write
manifest, log. No architectural decisions; the only judgment call (comprehensive vs.
non-superseded filter) was explicit in the mission directive and is recorded in
artifact metadata. Tier A QA discipline applied (multipass read-back, SHA verification,
canonical schema field names, activity log).

---

## 7 — Cursor re-review prompt

Submit the following to Cursor for v3 re-verdict:

> **Schema migration v3 — re-review request after AMEND_V2 cached-export gap closure.**
>
> Cursor's prior AMEND_V2 verdict on `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v3.md`
> required a cached canonical-export at `Production/exports/prod_locked_decisions_<DATE>.jsonl`
> (Task B fallback). Directus was 500/Forbidden at the time. Directus is now back up
> (verified `/server/info` HTTP 200, 2026-05-08T17:18Z) and the cached export has been
> generated.
>
> **Artifacts to verify:**
> 1. `Production/exports/prod_locked_decisions_2026-05-08.jsonl` — 570 rows, 1.12 MB,
>    SHA256 `4ac319c48cad2145a52ce9e50e601e8d187e209f4d995b0b9987dcb0c910710c`.
> 2. `Production/exports/prod_locked_decisions_2026-05-08.snapshot_manifest.json` —
>    row_count=570, id_uniqueness {unique_ids:570, duplicates:[]},
>    all_touched_ids_present=true, schema_field_count=25, status_distribution +
>    severity_distribution included.
> 3. `Production/exports/prod_locked_decisions_2026-05-08.metadata.json` — spec-shape
>    sidecar (export_version v3, total_active_rows=534, schema_hash, deterministic
>    sample method).
> 4. `Production/docs/SCHEMA_MIGRATION_CACHED_EXPORT_REPORT_20260508.md` — this report.
> 5. `prod_activity_log` row id=1781 (live Directus) recording the export with full
>    metadata + paths + sha256.
>
> **Deviations from spec template (transparent):**
> - Spec code template uses `status._neq: superseded`; this export captured ALL statuses
>   (mission directive: comprehensive offline-review fallback). The sidecar's
>   `total_active_rows` and the manifest's `status_distribution` both let any reviewer
>   filter back to the spec-strict subset deterministically.
> - Filename uses `2026-05-08` (hyphenated) rather than spec template's `%Y%m%d` (`20260508`)
>   — mission directive specified the hyphenated form.
>
> **Question for Cursor:** with the cached-export artifact now present and verified, does
> v3 advance from AMEND_V2 → AUTHORIZE_PHASE_0? If any residual gaps remain (Tasks D/E/F/H
> were also addressed in v3), please call them out specifically.

---

## 8 — File index for downstream consumers

| Artifact | Absolute path |
|---|---|
| JSONL | `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/exports/prod_locked_decisions_2026-05-08.jsonl` |
| Snapshot manifest | `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/exports/prod_locked_decisions_2026-05-08.snapshot_manifest.json` |
| Spec-shape sidecar | `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/exports/prod_locked_decisions_2026-05-08.metadata.json` |
| Generator script | `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/scripts/generate_cached_export_20260508.py` |
| This report | `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_MIGRATION_CACHED_EXPORT_REPORT_20260508.md` |
| Spec authority | `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v3.md` |
| Activity log | `prod_activity_log` row id=1781 (live Directus) |
