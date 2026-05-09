# Schema Migration v3 + lock_decision.py Canonical Fix — Proof Report

**Authored:** 2026-05-08, session `gallant-bouman-804b4f`.
**Author:** Claude Opus 4.7 (1M context).
**Scope:** Three bundled deliverables addressing Cursor's AMEND_V2 verdict on schema migration v2 — (1) v3 spec, (2) v3 handoff, (3) EXECUTED lock_decision.py canonical-aware fix.

---

## §1 — lock_decision.py before/after diff

**File:** `Production/scripts/lock_decision.py`
**Backup:** `Production/scripts/lock_decision.py.bak.20260508` (shasum `5fa9af202a0c37ca0f875ebf3ec4d8f3337fcc13`)
**Post-fix:** `Production/scripts/lock_decision.py` (shasum `9331b216d90b047ee257ca2198b6558a70f20ffa`)

### Diff summary

| Change | Before (v2.bak) | After (v3 canonical-aware) |
|---|---|---|
| Module-level constants | none | `CANONICAL_SEVERITIES = ["HARD", "SOFT"]`; `LEGACY_SEVERITY_MAP = {CRITICAL→HARD, HIGH→HARD, MEDIUM→SOFT, LOW→SOFT, critical→HARD, high→HARD, medium→SOFT, low→SOFT, MED→SOFT}`; `ACCEPTED_SEVERITY_CHOICES = canonical + legacy` |
| `canonicalize_severity()` function | absent | NEW: canonical pass-through; legacy auto-mapping with `[DEPRECATED]` stderr warning; unknown raises ValueError |
| `cmd_lock()` payload severity | `"severity": args.severity` (passes whatever was provided, including legacy) | `canonical_severity = canonicalize_severity(args.severity); ... "severity": canonical_severity` (always canonical regardless of input) |
| argparse `--severity` choices | `["critical", "HIGH", "high", "MEDIUM", "medium", "LOW", "low"]` (LEGACY ONLY; OMITTED HARD/SOFT) | `ACCEPTED_SEVERITY_CHOICES` = `["HARD", "SOFT", "CRITICAL", "HIGH", "MEDIUM", "LOW", "critical", "high", "medium", "low", "MED"]` (canonical first; legacy retained for back-compat) |
| `--severity` help text | none | "Canonical: HARD or SOFT (post-2026-05-04 schema). Legacy values (CRITICAL/HIGH/MEDIUM/LOW + lowercase + MED) are accepted for back-compat but emit a DeprecationWarning and auto-map to canonical (see LD_WRITER_CANONICAL_VOCAB_V1)." |
| Header comment block | none | 25-line rationale + back-compat reasoning + LD_WRITER_CANONICAL_VOCAB_V1 reference |

### Verification — `--help` output (verbatim from `python3 Production/scripts/lock_decision.py lock --help`)

```
  --severity {HARD,SOFT,CRITICAL,HIGH,MEDIUM,LOW,critical,high,medium,low,MED}
                        Canonical: HARD or SOFT (post-2026-05-04 schema).
                        Legacy values (CRITICAL/HIGH/MEDIUM/LOW + lowercase +
                        MED) are accepted for back-compat but emit a
                        DeprecationWarning and auto-map to canonical (see
                        LD_WRITER_CANONICAL_VOCAB_V1).
```

### Verification — `canonicalize_severity()` smoke test (5 branches)

```
Test 1: canonical HARD -> HARD                         (canonical pass-through, no warning)
Test 1: canonical SOFT -> SOFT                         (canonical pass-through, no warning)
Test 2: legacy CRITICAL -> HARD                        ([DEPRECATED] warning emitted)
Test 2: legacy HIGH -> HARD                            ([DEPRECATED] warning emitted)
Test 2: legacy MEDIUM -> SOFT                          ([DEPRECATED] warning emitted)
Test 2: legacy LOW -> SOFT                             ([DEPRECATED] warning emitted)
Test 3: legacy critical -> HARD                        ([DEPRECATED] warning emitted)
Test 3: legacy high -> HARD                            ([DEPRECATED] warning emitted)
Test 4: legacy MED -> SOFT                             ([DEPRECATED] warning emitted)
Test 5: PASS — ValueError raised: severity='foo' is not in canonical ['HARD', 'SOFT']
        and not in the legacy back-compat map. Pass HARD or SOFT.
```

All 5 branches verified.

### Verification — Python syntax check

`python3 -c "import ast; ast.parse(open('Production/scripts/lock_decision.py').read()); print('PYTHON_SYNTAX_OK')"` → `PYTHON_SYNTAX_OK`.

---

## §2 — Verbatim activity log row + LD POST response (DEFERRED — Directus offline)

**Status:** Directus production unreachable at session time (HTTP 500 on `/server/info`, `/auth/login`, `/items/*` — confirmed by direct curl probe at 2026-05-08T11:55:00-07:00).

> `curl -s -o /dev/null -w "STATUS: %{http_code}\n" "https://directus-production-3460.up.railway.app/server/info"` returned `STATUS: 500`.
> Body: `{"errors":[{"message":"An unexpected error occurred.","extensions":{"code":"INTERNAL_SERVER_ERROR"}}]}`

This is the same operational state Cursor encountered during the v2 review (Task B amendment). Per the v3 handoff offline-fallback protocol authored in this session, both the activity-log row AND the new LD POST were queued to:

**Path:** `Production/exports/DEFERRED_DIRECTUS_WRITES_20260508_lock_decision_canonical.jsonl` (shasum `22f156b7b8c22fcf6e675acd15bb959a8fa0a1bb`)

The file contains 2 JSONL lines, each a complete deferred POST payload with target collection, method, timestamp, deferral reason, and full body.

### Activity log payload (queued, not yet POSTed)

```json
{
  "target": "prod_activity_log",
  "method": "POST",
  "queued_at": "2026-05-08T11:55:00-07:00",
  "reason_deferred": "Directus production unreachable (HTTP 500)…",
  "payload": {
    "action": "lock_decision.py canonical-aware severity choices fix landed (LD_WRITER_CANONICAL_VOCAB_V1)",
    "details": "{\"fix\": \"…\", \"change\": \"…\", \"verification\": \"…\", \"cursor_amend_v2_task_h_resolution\": \"EXECUTED 2026-05-08\", \"backup_file\": \"Production/scripts/lock_decision.py.bak.20260508\", \"related_ld\": \"LD_WRITER_CANONICAL_VOCAB_V1\", \"self_classification\": \"STANDARD\"}",
    "performed_by": "lock_decision.py canonical fix session 2026-05-08 (gallant-bouman-804b4f)"
  }
}
```

### LD POST payload (queued, not yet POSTed)

```json
{
  "target": "prod_locked_decisions",
  "method": "POST",
  "queued_at": "2026-05-08T11:55:00-07:00",
  "reason_deferred": "Directus production unreachable (HTTP 500)…",
  "payload": {
    "decision_key": "LD_WRITER_CANONICAL_VOCAB_V1",
    "decision_name": "lock_decision.py CLI severity choices must be canonical-aware (HARD/SOFT first, legacy back-compat with deprecation warning)",
    "decision_text": "lock_decision.py is the canonical Directus writer for prod_locked_decisions rows. The 2026-05-04 silent Directus schema migration changed the severity vocabulary from {LOW, MEDIUM, HIGH, CRITICAL} to {HARD, SOFT}. Until 2026-05-08, lock_decision.py's --severity argparse choices list was legacy-only and OMITTED canonical HARD/SOFT — so every new LD written via this CLI silently reintroduced legacy vocabulary. Cursor's amend_v2 review (Task H) flagged this. Resolution: ACCEPTED_SEVERITY_CHOICES = CANONICAL + LEGACY_SEVERITY_MAP keys; canonicalize_severity() emits DeprecationWarning + auto-maps legacy to canonical before POST; cmd_lock() invokes the canonicalizer. Files touched: Production/scripts/lock_decision.py (backup at .bak.20260508).",
    "source_document": "Production/docs/SCHEMA_MIGRATION_V3_AND_LOCK_DECISION_FIX_REPORT_20260508.md",
    "task_category": "governance",
    "severity": "HARD",
    "status": "active",
    "date_locked": "2026-05-08",
    "enforcement_type": "code_invariant",
    "enforcement_artifact_ref": "Production/scripts/lock_decision.py canonicalize_severity() + ACCEPTED_SEVERITY_CHOICES",
    "related_files": ["Production/scripts/lock_decision.py", "Production/scripts/lock_decision.py.bak.20260508", "Production/lib/severity_vocab.py", "Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v3.md"],
    "keyword_synonyms": ["lock_decision.py", "severity choices", "canonical severity", "HARD/SOFT", "LEGACY_SEVERITY_MAP", "canonicalize_severity", "writer mismatch", "Cursor Task H"],
    "scope_domain": "cross-cutting",
    "supersedable": true
  }
}
```

### Replay procedure (when Directus is restored)

```python
# Replay deferred Directus writes
import json
from pathlib import Path
import sys
sys.path.insert(0, '.')
from Production.lib.directus_admin_client import DirectusAdminClient

client = DirectusAdminClient()
queue_path = Path("Production/exports/DEFERRED_DIRECTUS_WRITES_20260508_lock_decision_canonical.jsonl")
for line in queue_path.read_text().splitlines():
    line = line.strip()
    if not line:
        continue
    entry = json.loads(line)
    target = entry["target"]
    payload = entry["payload"]
    # For LD: idempotent upsert by decision_key
    if target == "prod_locked_decisions":
        existing = client.get_items(target,
            filters={"decision_key": {"_eq": payload["decision_key"]}},
            fields=["id"], limit=1)
        if existing:
            print(f"LD {payload['decision_key']} already exists (id={existing[0]['id']}); skipping")
            continue
    response = client.post_item(target, payload)
    print(f"Replayed {target} → id={response['id']}")
```

**Per Rule 35 (read-back-after-write):** the replay procedure includes idempotent-upsert for the LD (skip if `decision_key` already exists, e.g., if a different session re-queued the same payload). Activity-log rows are not deduplicated (append-only collection by design).

---

## §3 — v3 spec §0.1 changelog (verbatim)

(See full text at `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v3.md` §0.1.)

The v3 spec §0.1 changelog table contains 5 rows — one per Cursor amendment — with the verbatim Cursor amendment text in the left column and the resolution applied in v3 in the right column. The 5 rows are:

| Task | Resolution location |
|---|---|
| B (cached export for offline review) | §5 Phase 0 NEW Step 0.4, §6 Gate 7 expanded, §11 |
| D (rollback rehearsal on 5 random rows) | §4 Phase 0 NEW Step 0.5, §5 Phase 0 Step 0.5 narrative, §6 NEW Gate 10, §7 NEW risk #10, §8 v3 addendum |
| E (remote mutex replaces local lockfile) | §9.4 REPLACED, §5 Phase 1-5 entry guard, §6 NEW Gate 11, §7 NEW risk #11 |
| F (durable checkpoint schema + resume algorithm) | §5.0 NEW, §5 Phase 1-5 per-row checkpoint append, §6 NEW Gate 12, §7 NEW risk #12 |
| H (lock_decision.py canonical-aware) | EXECUTED 2026-05-08 in same session; v3 §11 reference index updated to call lock_decision.py canonical-aware. Spec does NOT itself mandate the change — it was executed before v3 was written. |

v3 file size: 38,433 bytes (shasum `e8ea981844a339a24fc89123ba2960044863233b`).

---

## §4 — v3 handoff §0.1 + Step 0 fallback section (verbatim)

(See full text at `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v3.md` §0.1 + Step 0.5.)

### v3 handoff §0.1 changelog table (5 rows mirroring Cursor amendments)

| Task | Resolution location in handoff |
|---|---|
| B (offline fallback) | NEW Step 0.5 fallback section + Step 2 prompt Task B updated to use cached export + Hard rules add Offline-fallback discipline |
| D (rehearsal verification) | Step 2 prompt Task D updated with 3-element verification (rehearsal procedure + report path + Gate 10) |
| E (remote mutex verification) | Step 2 prompt Task E updated to require §9.4 REPLACED (not just amended) |
| F (checkpoint verification) | Step 2 prompt Task F updated with 3-element verification (schema + resume algorithm + Gate 12) |
| H (lock_decision.py shipped) | NEW Step 2 prompt Task H block with 3 evidence requirements (backup mtime, --help output, LD existence) |

### v3 handoff Step 0.5 — Offline Directus fallback procedure (verbatim from handoff)

> **When this step fires:** any preflight check that requires live Directus access returns connection-error / 5xx / 4xx auth failure / tunnel error / timeout.
>
> **What to do (v3 deterministic procedure):**
>
> 1. Confirm the cached export exists (`ls -la Production/exports/ | grep prod_locked_decisions`).
> 2. Read the metadata sidecar (`prod_locked_decisions_<DATE>.metadata.json`) to confirm `total_active_rows`, `export_taken_at`, `schema_hash`. Quote inline.
> 3. Use the deterministic sample method: "sort by id ASC; take rows where id % N == 0 for sample size 530/N (rounded down)". For Task B 5-row CRITICAL sample: N = max(1, len(CRITICAL) // 5).
> 4. Document inline that offline fallback was used. Verdict body MUST contain the verbatim line `OFFLINE FALLBACK USED: live Directus unreachable; Analysis Task <X> performed against cached export <path> (export_taken_at=<ts>, total_active_rows=<n>)`.
> 5. Do NOT escalate to AMEND_V2 solely because Directus was unreachable. AMEND_V2 is only appropriate if (a) the cached export does not exist, (b) the metadata sidecar is missing or malformed, or (c) the deterministic sample reveals findings that themselves warrant AMEND_V2 per the original task's rubric.

The v3 handoff also adds Verdict line `AUTHORIZE_PHASE_0_OFFLINE_FALLBACK_INSUFFICIENT` for the case where cached export exists but findings cannot be made without live Directus — surfaces to Kim for Directus-restoration scheduling rather than blocking the spec.

---

## §5 — Per-Cursor-blocker resolution table (5 rows)

| # | Cursor amendment (verbatim summary) | Resolution location | Status |
|---|---|---|---|
| Task B | Directus 403/tunnel — sample failed; need offline fallback procedure with cached-export + deterministic sample | v3 spec §5 Phase 0 NEW Step 0.4 (cached export generation) + v3 handoff NEW Step 0.5 (consumption procedure) + §11 | RESOLVED in v3 |
| Task D | No mandatory pre-Phase-5 rollback simulation on sampled subset | v3 spec §4 Phase 0 NEW Step 0.5 (rollback rehearsal on 5 random rows with pass/fail report) + §6 NEW Gate 10 + §7 NEW risk #10 + §8 v3 addendum | RESOLVED in v3 |
| Task E | Local-only lockfile doesn't prevent multi-host concurrent runners | v3 spec §9.4 REPLACED — Directus `prod_blockers` row `SCHEMA_MIGRATION_LOCK_HELD_BY_<HOST>` (severity=CRITICAL) as primary; local lockfile retained as defense-in-depth + §6 NEW Gate 11 + §7 NEW risk #11 | RESOLVED in v3 |
| Task F | "Resume from last-confirmed row" mentioned but no checkpoint schema/path defined | v3 spec NEW §5.0 (verbatim schema `(phase, rule, last_committed_row_id, timestamp, snapshot_hash, rows_processed_in_phase, expected_rows_in_phase)` + resume algorithm pseudocode + per-row append protocol) + §6 NEW Gate 12 + §7 NEW risk #12 | RESOLVED in v3 |
| Task H | lock_decision.py CLI choices legacy-only, OMITTED HARD/SOFT — actively bleeding | EXECUTED 2026-05-08: ACCEPTED_SEVERITY_CHOICES + canonicalize_severity() + cmd_lock() rewrites payload to canonical + back-compat with deprecation warning + smoke test 5 branches passing + LD_WRITER_CANONICAL_VOCAB_V1 queued (live POST blocked by Directus 5xx) | RESOLVED in code; LD POST DEFERRED |

---

## §6 — Confidence tags (per Rule 24)

| Claim | Confidence | Evidence |
|---|---|---|
| lock_decision.py severity choices now include canonical HARD/SOFT first | CONFIRMED | `python3 lock_decision.py lock --help` output captured verbatim |
| canonicalize_severity() correctly handles all 5 branches (canonical pass-through, legacy upper, legacy lower, MED abbrev, unknown ValueError) | CONFIRMED | Smoke test executed inline; all 5 cases verified |
| Backup file `lock_decision.py.bak.20260508` is byte-identical to pre-fix state | CONFIRMED | shasum captured (`5fa9af202a0c37ca0f875ebf3ec4d8f3337fcc13`) immediately after `cp` before any edit; no further writes to backup |
| Directus production was unreachable at session time | CONFIRMED | curl probe of `/server/info` returned 500 with body `{"errors":[{"message":"An unexpected error occurred."…}]}`; SDK login also returned 500 |
| Activity log row + LD POST queued in deferred-writes JSONL | CONFIRMED | File at `Production/exports/DEFERRED_DIRECTUS_WRITES_20260508_lock_decision_canonical.jsonl` (shasum `22f156b7b8c22fcf6e675acd15bb959a8fa0a1bb`) contains both payloads, valid JSONL |
| v3 spec preserves all v1 + v2 content (no deletions) | INFERRED | v3 explicitly says "all v2 content preserved (no deletions); v3 additions are clearly labeled (v3) or (NEW v3) inline." v3 file size 38,433 bytes vs v2 48,617 — v3 is smaller because it preserves v2 by reference rather than re-quoting; the §3.1-§3.4 dual-Opus debate text is referenced not duplicated |
| v3 handoff preserves v2's hardening (anchored discipline, dual-canonical paths, descriptive-task escalation, numeric AMEND thresholds) | INFERRED | v3 handoff §0.1 changelog claims preservation; explicit "(v2 preserved)" labels throughout; final spot-check by re-reading the v3 handoff confirms |
| Replay procedure for deferred writes is idempotent for LD POST (skip if decision_key already exists) | CONFIRMED | Procedure body includes the `existing = client.get_items(...filter=decision_key)` check + `if existing: skip` |
| LD_WRITER_CANONICAL_VOCAB_V1 will not collide with a previously-existing LD on replay | INFERRED | Cannot verify against live Directus while offline; the decision_key is novel (was authored 2026-05-08) and includes `_V1` suffix per house pattern; replay procedure is idempotent so collision would result in skip-with-warning rather than data corruption |

---

## §7 — Self-classification per change

| Change | Self-classification |
|---|---|
| `lock_decision.py` edit (canonical-aware severity choices + canonicalize_severity + cmd_lock rewrite) | STANDARD — surgical bug fix in existing module; no architectural change; backward-compatible (legacy --severity values still accepted with deprecation warning); reversible (backup at .bak.20260508; revert by `cp lock_decision.py.bak.20260508 lock_decision.py`) |
| v3 spec authoring (`SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v3.md`) | STANDARD — spec amendment per Cursor's documented review feedback; preserves v1 + v2 baselines; DESIGN ONLY (no execution side effects); follows established v1→v2 amendment pattern |
| v3 handoff authoring (`HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v3.md`) | STANDARD — handoff amendment per Cursor's documented review feedback; preserves v1 + v2 baselines; conforms to HANDOFF_TEMPLATE_v2.md |
| Deferred writes JSONL queue (`Production/exports/DEFERRED_DIRECTUS_WRITES_20260508_lock_decision_canonical.jsonl`) | STANDARD — operational artifact; offline-replay convention from existing directus_admin_client comments ("silent offline-queueing… is correct offline behavior") |
| New `Production/exports/` directory | STANDARD — directory creation; required by spec v3 §5 Phase 0 Step 0.4 + handoff Step 0.5; no contents-of-others affected |

No ARCHITECTURAL or CRITICAL self-classifications in this session.

---

## §8 — Single-line Cursor re-review prompt for v3

```
Please review Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v3.md against Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v3.md per the Step 2 prompt block, applying full preflight + 9 analysis tasks (A through I, with Task H NEW for lock_decision.py canonical-aware fix verification) + offline-fallback discipline if live Directus is unreachable; emit single-line VERDICT: [AUTHORIZE_PHASE_0 | AUTHORIZE_PHASE_0_WITH_RISK_ACCEPTANCE | AUTHORIZE_PHASE_0_OFFLINE_FALLBACK_INSUFFICIENT | AMEND_V2 | BLOCK].
```

---

## §9 — Artifact inventory + shasums

| Artifact | Path | Size | Shasum |
|---|---|---|---|
| lock_decision.py (canonical-aware) | `Production/scripts/lock_decision.py` | 17,258 bytes | `9331b216d90b047ee257ca2198b6558a70f20ffa` |
| lock_decision.py backup (pre-fix) | `Production/scripts/lock_decision.py.bak.20260508` | 13,580 bytes | `5fa9af202a0c37ca0f875ebf3ec4d8f3337fcc13` |
| Spec v3 | `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v3.md` | 38,433 bytes | `e8ea981844a339a24fc89123ba2960044863233b` |
| Handoff v3 | `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v3.md` | 24,289 bytes | `b5067fd6e427fc53ce2344a2f6af8a36055bfd5c` |
| Deferred writes JSONL | `Production/exports/DEFERRED_DIRECTUS_WRITES_20260508_lock_decision_canonical.jsonl` | 4,584 bytes | `22f156b7b8c22fcf6e675acd15bb959a8fa0a1bb` |
| This proof report | `Production/docs/SCHEMA_MIGRATION_V3_AND_LOCK_DECISION_FIX_REPORT_20260508.md` | (this file) | (computed at file-write time) |

---

## §10 — Limitations

- **Directus production unreachable.** Both LD `LD_WRITER_CANONICAL_VOCAB_V1` and the activity-log audit row are queued in the deferred-writes JSONL rather than POSTed live. They MUST be replayed via the procedure in §2 once Directus is restored. Until replayed, the canonical authority for the lock_decision.py fix lives in this proof report + the v3 spec §0.1 Task H entry — NOT in `prod_locked_decisions`. Rule 35 read-back-after-write was performed on neither row (because no row was POSTed).
- **No Cursor v3 verdict yet.** This session authored v3 spec + v3 handoff but did not run Cursor against them. Per the v3 handoff Step 3, Cursor's response should be saved at `Production/docs/CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v3.md` and verdict-routed (AUTHORIZE_PHASE_0 → schedule migration; AMEND_V2 → author v4; etc.).
- **No live verification of v3 spec's runtime behavior.** Phases 0 Step 0.4 (cached export), Step 0.5 (rollback rehearsal), §5.0 (checkpoint), §9.4 (remote mutex) are SPECIFIED in v3 but NOT yet IMPLEMENTED in `Production/scripts/migrate_schema_vocab_v1.py` (the script does not yet exist; per spec §5 it would be authored at Phase 0 execution time). Verifying the spec compiles to executable code is a future session.
- **Spec v3 references `Production/scripts/migrate_schema_vocab_v1.py` but does not exist yet.** This is consistent with the v1/v2 pattern (the migration script was always intended to be written at Phase 0 execution time, not at spec time). No regression introduced.
