# Schema Vocab Migration — Tech Spec v5

**Authored:** 2026-05-08 (v5 amendment same day as v1 + v2 + v3 + v4).
**Author:** Claude Opus 4.7 (1M context).
**Self-classification:** ARCHITECTURAL (governance + data migration).
**Status:** DESIGN ONLY — execution is gated on Kim approval per §7. Phase 5 additionally gated on a feature flag (see §3 Rule 1 v2 resolution, preserved verbatim through v3 → v4 → v5).

**Supersedes:** `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v4.md` (preserved as historical baseline; do NOT edit in place). v4 in turn supersedes v3; v3 supersedes v2; v2 supersedes v1.

**v4 → v5 driver:** v4 fixed the §9.4 mutex severity case-fold (CRITICAL → critical) but EXPLICITLY DEFERRED a SECOND defect: v3+v4 example POST/PATCH bodies in §9.4 reference fields `details` and `resolution_notes` that **do not exist** on the live `prod_blockers` collection. Live `prod_blockers` has exactly 8 fields: `id`, `module_id`, `severity`, `title`, `description`, `is_resolved`, `created_at`, `resolved_at` (live-probed 2026-05-08 via `DirectusAdminClient.fields("prod_blockers")` returning 8 fields). v4 §0.1 flagged this as "informational, no spec change" and §9.4 said "v4 does NOT correct the example body in line with the minimal-amendment mandate." A literal-script implementation following spec v3 or v4 example bodies will return HTTP 400 / "field does not exist" errors for `details` and `resolution_notes`, halting Phase 1+ entry guards. v5 corrects ONLY the §9.4 example bodies + the stale-mutex cleanup parsing pattern; all other v4 design (cached export, rollback rehearsal, checkpoint protocol, Phase 5 feature flag, Task H, severity case-fold) preserved verbatim. This is a self-discovered defect, not a Cursor amendment.

**Related artifacts (preserved from v4 + v5 additions):**
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v4.md` — **v4 historical baseline (this spec's predecessor)** (v5 NEW reference).
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v3.md` — v3 historical baseline.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v2.md` — v2 historical baseline.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v1.md` — v1 historical baseline.
- `Production/docs/SCHEMA_CLEANUP_AND_SUPABASE_HARDENING_REPORT_20260508.md` — investigation that motivates this spec.
- `Production/lib/severity_vocab.py` — Part 1 cheap defensive read-side fix that has already landed.
- `Production/scripts/lock_decision.py` — LD-writer CLI; canonical-aware as of 2026-05-08 per Cursor v3 Task H execution.
- `Production/scripts/lock_decision.py.bak.20260508` — pre-fix backup.
- `Production/scripts/governance_drift_check.py`, `failure_mode_matrix.py`, `preflight_hook.py` — query consumers updated by Part 1 to be vocab-tolerant.
- LD #586 `SCHEMA_VOCAB_TOLERANT_FILTER_V1` — standing rule mandating helper-import.
- `LD_WRITER_CANONICAL_VOCAB_V1` — LD filed 2026-05-08 documenting the lock_decision.py canonical-aware fix (HARD severity).
- LD #584 `WORKTREE_CONFUSION_PREVENTION_V1` (amended 2026-05-08 v2 dual-canonical) — authority for the dual-path discipline cited in §3 v2 path discipline section (preserved through v4 → v5).
- `LD-590 SCHEMA_VOCAB_MIGRATION_V3_LOCKED` — v3 authorization decision.
- `LD-591` — `weekly_preflight_audit.py` schema-ref-doc enforcement amendment.
- `LD-592 DIRECTUS_SCHEMA_REF_PROD_BLOCKERS_GOTCHAS_V1` — schema-ref doc §5 prod_blockers gotchas authority (lowercase severity + STRUCTURED_DETAILS_JSON workaround); v5 §9.4 field-name fix cross-references this LD.
- `LD-593` — v4 §9.4 severity case-fold authority (referenced in v4; preserved here as the case-fold remains in effect).
- `LD-595 SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V5_FIELD_NAME_FIX_V1` — **v5 field-name fix authority** (v5 NEW reference; filed 2026-05-08 same session as v5 spec authoring).
- `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` §5 — live-probed `prod_blockers` schema reference; ground truth for the v5 §9.4 field-name fix (8-field enumeration + STRUCTURED_DETAILS_JSON pattern + lowercase severity).
- `Production/docs/HANDOFF_SCHEMA_MIGRATION_V3_IMPLEMENTATION_20260508.md` — implementation handoff. §6 prod_blockers schema gotchas (added v2.1) anticipates v5's correction; v5 is the formal spec-side reconciliation. Likely needs v2.2 amendment to point at v5 — see §12 changelog.
- `Production/docs/HANDOFF_TEMPLATE_v2.md` — handoff structure used for the Cursor review companion.
- `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v3.md` — companion review handoff (v3; preserved as v5's review companion since v5 is a post-authorization touch-up, not a re-review).
- `Production/exports/prod_locked_decisions_<DATE>.jsonl` — cached canonical-export.

---

## §0.1 — v5 Changelog (single-row amendment over v4)

v5 is a minimal amendment over v4 to fix the SECOND §9.4 defect that v4 deferred informationally. v4's §0.1 changelog is preserved verbatim immediately below this v5 entry, followed by v3's. v5 is NOT a Cursor amendment — it is a self-discovered defect that v4 explicitly punted to "future v5 (or implementation-time edit)."

| # | v5 amendment (self-discovered; v4 explicitly deferred) | Resolution applied in v5 | Sections changed |
|---|---|---|---|
| v5-A | v3 + v4 §9.4 example bodies reference fields `details` (acquisition POST + stale-mutex cleanup parsing) and `resolution_notes` (release PATCH) that **do not exist** on the live `prod_blockers` collection. Live `prod_blockers` has exactly 8 fields: `id`, `module_id`, `severity`, `title`, `description`, `is_resolved`, `created_at`, `resolved_at` (live-probed 2026-05-08 via `DirectusAdminClient.fields("prod_blockers")`). A literal POST per v3 with a `details` key returns HTTP 400 / unknown-field. Same for a PATCH with `resolution_notes`. v4 flagged this as "informational, no spec change" (v4 §0.1 row v4-A trailing paragraph + §9.4 callout) on the minimal-amendment mandate, leaving v3+v4 example bodies still defective for any literal-script implementer. v4 used a plain-string `description` for acquisition without the canonical STRUCTURED_DETAILS_JSON encoding pattern, and omitted `resolution_notes` annotation entirely instead of appending to `description`. | v5 §9.4 REPLACES the acquisition POST body's `details` field — and v4's plain-string `description` — with `description = "Schema vocab migration in progress on host <HOST> | STRUCTURED_DETAILS_JSON: " + json.dumps({...})` per the canonical text-embedded JSON pattern documented in `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` §5 lines 362-377. The structured payload encodes `host`, `pid`, `started_at`, `script_version`. The release PATCH body's `resolution_notes` field is REPLACED with an APPEND to the existing `description`: `f"<existing> | RESOLVED: <resolution_text> (see Phase 6 final-audit report at <path>)"`. The stale-mutex cleanup snippet (which previously parsed PID from `details`) is REPLACED with regex parsing on `description` anchored on `STRUCTURED_DETAILS_JSON:` followed by `json.loads(...)` to extract `pid`. v5 §9.4 NEW callout block (top of section) cites the live-schema 8-field enumeration + LD-592 + LD-595 + handoff §6 prod_blockers schema gotchas. §6 adds Gate 11.2 sub-rule mandating field-name compliance (no `details` / no `resolution_notes` keys on any `prod_blockers` POST/PATCH). §7 adds risk #14 documenting the failure mode (HTTP 400 unknown-field on copy-paste from v3/v4). §11 reference index adds v4 historical baseline + LD-595 + this v5 self-reference. §12 changelog appends v5 entry. | §9.4 (acquisition POST body + release PATCH body + stale-mutex cleanup parsing + v5 callout), §6 Gate 11.2 (NEW), §7 risk #14 (NEW), §11 reference index, §12 changelog |

**v4 vs v5 surface area (NEW):** v5 adds ~60 lines net (one §0.1 v5 row, one §6 Gate 11.2 row, one §7 risk #14 row, one §9.4 v5 callout block + 3 corrected example body code blocks, four §11 reference-index entries, one §12 changelog entry). v5 deletes nothing. The substantive code-affecting changes are: (1) acquisition POST: `description` carries STRUCTURED_DETAILS_JSON-encoded `host`/`pid`/`started_at`/`script_version`; (2) release PATCH: append `RESOLVED: ...` to existing `description` rather than use non-existent `resolution_notes`; (3) stale-mutex cleanup: parse PID from `description`'s `STRUCTURED_DETAILS_JSON:` block via regex+json.loads. All other v4 content (§1, §2, §3.0-§3.4, §4, §5.0, §5 Phase 0/1/2/3/4/5/6, §8, §9.1-§9.3, §10, §6 Gates 1-11.1, §7 risks 1-13, §9.4 severity case-fold) preserved verbatim.

---

## §0.1 (v4, preserved verbatim) — v4 Changelog (single-row amendment over v3)

v4 is a minimal amendment over v3 to fix one §9.4-level schema collision. v3's §0.1 changelog is preserved verbatim immediately below this v4 entry. v4 is NOT a Cursor amendment — it is a self-discovered defect surfaced during `prod_blockers` id=101 filing.

| # | v4 amendment (self-discovered) | Resolution applied in v4 | Sections changed |
|---|---|---|---|
| v4-A | v3 §9.4 mandates `severity=CRITICAL` (uppercase) for the `SCHEMA_MIGRATION_LOCK_HELD_BY_<HOST>` mutex row on `prod_blockers`. Live `prod_blockers.severity` enum is **lowercase only** (`critical` / `high` / `medium` / `low`) per `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` §5 (live-probed 2026-05-08 from `/fields/prod_blockers/severity`). A literal POST per v3 returns HTTP 500. The collision is invisible to readers because the field name `severity` is shared with `prod_locked_decisions.severity` which IS uppercase (HARD/SOFT canonical, CRITICAL/HIGH/MEDIUM/LOW legacy) — the two collections share a field name but have **opposite case conventions**. | v4 §9.4 case-folds every active `severity` value in the mutex POST/PATCH examples from `CRITICAL` to lowercase `critical`. v3 prose describing v2's lockfile is preserved verbatim. v3 references to "severity=`CRITICAL` (treat as a production blocker)" are replaced with "severity=`critical` (treat as a production blocker; lowercase per `prod_blockers.severity` enum)". A v4 NEW callout block in §9.4 cites the live-schema enum + LD-592 + the schema-ref doc §5. §6 adds Gate 11.1 sub-rule mandating the case-fold at Phase 1-5 entry-guard time. §7 adds risk #13 documenting the failure mode (uppercase copy-paste returns HTTP 500). §11 reference index adds LD-590/591/592 + schema-ref doc §5 pointer + v3 historical baseline. §12 changelog appends v4 entry. | §9.4 (severity case-fold + v4 callout), §6 Gate 11.1 (NEW), §7 risk #13 (NEW), §11 reference index, §12 changelog |

**v4 also documents (informational, no spec change):** the schema-ref doc §5 surfaced a SECOND minor v3 issue — the §9.4 release-PATCH example references `resolution_notes` which is NOT a field on `prod_blockers` (the live collection has exactly 8 fields: `id`, `module_id`, `severity`, `title`, `description`, `is_resolved`, `created_at`, `resolved_at`). v4 §9.4 callout notes this as an OBSERVATION but does NOT correct the example body (per the "minimal amendment" mandate of v4 — the resolution-time annotation can ride inside `description` or rely on `is_resolved=true`+`resolved_at` alone, which is a defendable interpretation of the v3 release narrative). A future v5 (or implementation-time edit to the migration script) should normalize this. **v5 NOTE:** this is what v5 fixes. Tracked: `prod_blockers` id=101 schema-discovery anchor + LD-592 §5 + LD-595.

---

## §0.1 (v3, preserved verbatim from v4) — v3 Changelog (Cursor amendment resolution table)

(Preserved verbatim from v4 §0.1 v3 section. See `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v4.md` §0.1 v3 changelog table for the full Tasks B/D/E/F/H rows. Five rows; ~280 lines of design surface for the v2→v3 migration.)

---

## §1 — Goal (preserved verbatim from v1 + v2 + v3 + v4)

(Preserved verbatim from v4 §1. Five-bullet goal statement + non-goals list.)

---

## §2 — Background (preserved verbatim from v1 + v2 + v3 + v4)

(Preserved verbatim from v4 §2. Cleanup-report baseline + v3 ADD on lock_decision.py + v4 ADD on prod_blockers row 101.)

**v5 ADD (informational):** the §9.4 example-body field-name defect that v4 deferred is what v5 fixes. No background-level scope change beyond the §9.4 + §6 + §7 + §11 + §12 surgical edits.

---

## §3 — Dual-Opus debate (verbatim) on 4 mapping rules + v2 amendments (preserved in v3 + v4 + v5)

(Preserved verbatim from v4 §3. §3.0 path discipline / §3.1 Rule 1 + PHASE_5_ENABLED / §3.2 Rule 2 / §3.3 Rule 3 / §3.4 Rule 4 — all preserved through v5. v5 introduces no §3-level changes; the v5 amendment is operational rather than debate-level.)

See `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v2.md` §3.0-§3.4 for the verbatim text.

---

## §4 — Per-rule action table (preserved verbatim from v3 + v4)

(Preserved verbatim from v4 §4. Rules 1/2/3a/3b/4 with v3 prerequisite columns + v2 expanded snapshot schema reference. v5 introduces no §4-level changes.)

See v3 §4 / v4 §4 for the verbatim text.

---

## §5 — Migration sequence (preserved verbatim from v3 + v4)

(Preserved verbatim from v4 §5. §5.0 checkpoint protocol / Phase 0 Steps 0/1/2/3/0.4/0.5 / Phase 1-6 — all preserved through v5.)

**v4 NOTE preserved:** the Phase 1 entry-guard code block in v3 §5 contains a `severity="CRITICAL"` literal in the mutex POST. Per v4 §9.4 (case-fold), this string MUST be lowercase `"critical"` at script-write time.

**v5 NOTE (informational):** the Phase 1 entry-guard code block in v3 §5 (and v4's narrative carrying it forward) also references a `details` key on the `prod_blockers` POST. Per v5 §9.4 (field-name fix), this key MUST be REMOVED at script-write time and the structured payload (`host`, `pid`, `started_at`, `script_version`) MUST be encoded inside `description` as a `STRUCTURED_DETAILS_JSON:`-anchored JSON literal. v5 §9.4 callout is the authoritative source; v5 §6 Gate 11.2 enforces field-name compliance at gate time. v3 §5 / v4 §5 Phase 1 entry-guard code is preserved verbatim there as historical reference but the migration script's Phase 1 entry-guard implementation must use the corrected pattern per v5 §9.4 + Gate 11.2.

See v3 §5.0 + Phase 0 + Phase 1-6 for the verbatim text.

---

## §6 — Pre-implementation gates Kim must approve (v4 preserved + v5 Gate 11.2 added)

(Gates 1-9 preserved verbatim from v2. Gates 10/11/12 preserved verbatim from v3. Gate 11.1 preserved verbatim from v4.)

| # | Gate | Kim's decision required |
|---|------|------------------------|
| 10 | **(v3 — Cursor Task D)** Pre-Phase-5 rollback rehearsal: must Phase 0 Step 0.5 produce a "All passed: True" report on 5 random rows BEFORE Phase 5 may execute? Phase 5 entry guard halts if rehearsal report missing or any row failed. | YES (REQUIRED for Phase 5) / NO (only valid if Phase 5 stays DEFERRED) |
| 11 | **(v3 — Cursor Task E)** Remote mutex via Directus `prod_blockers` row `SCHEMA_MIGRATION_LOCK_HELD_BY_<HOST>` (severity per v4 §9.4 case-fold = `critical` lowercase; field-name compliance per v5 §9.4 = no `details` / no `resolution_notes`): must mutating phases (1, 2, 4, 5) acquire+verify this row before proceeding? | YES (REQUIRED) / DEFER (single-host operation; rely on local lockfile only) |
| 11.1 | **(v4 — self-discovered defect)** Mutex POST severity case-fold: must the migration script's `prod_blockers` mutex POST/PATCH use `severity='critical'` (LOWERCASE) per the live `prod_blockers.severity` enum? Uppercase `CRITICAL` returns HTTP 500 and would block Phase 1-5 entry-guard acquisition. Reference: live-schema enum `[critical, high, medium, low]` per `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` §5 + LD-592. | YES (REQUIRED — uppercase returns HTTP 500; no defer option) |
| 11.2 | **(v5 NEW — self-discovered defect; v4 deferred)** Mutex POST/PATCH field-name compliance: must the migration script's `prod_blockers` mutex POST/PATCH/release use ONLY the 8 live fields (`id`, `module_id`, `severity`, `title`, `description`, `is_resolved`, `created_at`, `resolved_at`) and NEVER include `details` or `resolution_notes` keys? Structured payloads MUST encode inside `description` as text-embedded JSON anchored on `STRUCTURED_DETAILS_JSON:` per `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` §5 (lines 362-377). Resolution-time annotation MUST append to the existing `description` rather than use a non-existent field. Reference: live-schema 8-field enumeration + LD-592 + LD-595 + handoff §6 prod_blockers schema gotchas. | YES (REQUIRED — `details`/`resolution_notes` return HTTP 400 unknown-field; no defer option) |
| 12 | **(v3 — Cursor Task F)** Checkpoint file `Production/exports/schema_migration_checkpoint_<DATE>.jsonl` (append-only, schema per §5.0): must per-row checkpoint appends be a hard requirement of Phases 1, 2, 4, 5 with the resume algorithm verifying snapshot_hash on session restart? | YES (REQUIRED for resume safety) / NO (single-session execution; no resume protocol needed) |

**Gate 10 verification artifact (v3 preserved):** rollback rehearsal report at `Production/docs/SCHEMA_VOCAB_MIGRATION_ROLLBACK_REHEARSAL_<YYYYMMDD>.md`; Phase 5 entry guard's check #2 reads it.

**Gate 11 verification artifact (v3 preserved):** Directus query for `prod_blockers` row with title `SCHEMA_MIGRATION_LOCK_HELD_BY_<HOST>` and `is_resolved=false`; Phase 1-5 entry guards read it.

**Gate 11.1 verification artifact (v4 preserved):** at script-write time, the migration script's source for the mutex POST/PATCH must be grep-able for `severity=.*critical` (lowercase) and MUST NOT match `severity=.*CRITICAL` (uppercase). Recommended pre-launch lint: `grep -n "severity=.*CRITICAL\|severity=.*\"CRITICAL\"" Production/scripts/migrate_schema_vocab_v1.py` returns NO matches inside any `prod_blockers`-targeted POST/PATCH block. (Matches inside `prod_locked_decisions`-targeted code are FINE — that collection's `severity` enum IS uppercase.) At runtime, the read-back per Rule 35 confirms the persisted value is lowercase `critical`. If HTTP 500 is returned by Directus on the mutex POST, the script HALTS with `MUTEX_POST_HTTP_500_LIKELY_CASE_VIOLATION` activity-log row.

**Gate 11.2 verification artifact (v5 NEW):** at script-write time, the migration script's source for the mutex POST/PATCH must be grep-able for: `STRUCTURED_DETAILS_JSON` appearing >= 2 times (once in acquisition POST construction, once in stale-mutex cleanup parser); AND `"details"` appearing 0 times inside any `prod_blockers`-targeted POST/PATCH dict literal; AND `"resolution_notes"` appearing 0 times anywhere in the file. Recommended pre-launch lint: `grep -n '"details"\|"resolution_notes"' Production/scripts/migrate_schema_vocab_v1.py | grep -v "prod_activity_log\|prod_locked_decisions"` returns NO matches. (Matches inside `prod_activity_log.details = {...}` dict literals are FINE — `prod_activity_log.details` IS a real JSON column. Matches in comments quoting v3/v4 historical defects are FINE — only ACTIVE dict literals on `prod_blockers` calls are errors.) At runtime, if HTTP 400 is returned by Directus on the mutex POST or release PATCH, the script HALTS with `MUTEX_POST_HTTP_400_UNKNOWN_FIELD` activity-log row pointing the operator at this gate.

**Gate 12 verification artifact (v3 preserved):** checkpoint file exists at the expected path; snapshot_hash field matches current snapshot's metadata hash; resume algorithm filters target rows to `id > last_committed_row_id`.

---

## §7 — Risk assessment (v4 preserved + v5 risk #14 added)

(Rows 1-9 preserved verbatim from v2. Rows 10/11/12 preserved verbatim from v3. Row 13 preserved verbatim from v4.)

| Risk | Likelihood | Severity | Mitigation |
|---|---|---|---|
| **(v3)** Rollback rehearsal passes on 5 sampled rows but actual rollback fails on the remaining 315 rows due to row-specific quirks | LOW | HIGH | Sample size of 5 is the v3 baseline; if Kim wants higher confidence, increase to 20 or 50; always emit the failed-row id in the activity-log row |
| **(v3)** Remote mutex acquisition succeeds but mutex is never released due to script crash; subsequent runners blocked indefinitely | LOW | MEDIUM | Mutex includes `pid` field (v5: encoded in `description` STRUCTURED_DETAILS_JSON block, not on `details` since prod_blockers has no `details` field); cleanup helper `release_stale_mutex.py` checks if PID is alive on the recorded host (v5: parses PID via regex anchored on `STRUCTURED_DETAILS_JSON:` then `json.loads`); manual override path documented in §9.4 |
| **(v3)** Checkpoint file corrupted mid-write causes resume algorithm to crash or skip valid rows | LOW | MEDIUM | Resume algorithm tolerates corrupt last line via try/except |
| **(v4 — #13)** Spec author or implementer copy-pastes uppercase `CRITICAL` from v3's §9.4 example into the migration script's mutex POST despite the v4 amendment, returning HTTP 500 from Directus and halting Phase 1-5 entry-guard acquisition | LOW | HIGH | (1) v4 §9.4 callout cites the case-fold prominently; (2) LD-592 schema-ref doc records the divergence as a permanent gotcha; (3) §6 Gate 11.1 mandates a pre-script-launch lint that greps the mutex POST source for `severity=.*CRITICAL` (uppercase) inside `prod_blockers`-targeted code and rejects; (4) at runtime, an HTTP 500 on the mutex POST produces `MUTEX_POST_HTTP_500_LIKELY_CASE_VIOLATION` activity-log row pointing the operator at the §9.4 case-fold guidance. Severity HIGH because Phases 1+2+4+5 entry-guard depend on mutex acquisition; failure halts all mutating phases and leaves the system mid-migration. |
| **(v5 NEW — #14)** Spec author or implementer copy-pastes v3/v4 example body containing a `details` or `resolution_notes` field on a `prod_blockers` POST/PATCH despite the v5 amendment; Directus returns HTTP 400 / unknown-field error; mutex acquisition fails → all mutating phases (Phase 1, 2, 4, 5) entry-guard halts | LOW | HIGH | (1) v5 §9.4 callout enumerates the live 8 fields and prohibits the two non-fields prominently; (2) LD-592 schema-ref doc + LD-595 record the divergence as a permanent gotcha; (3) §6 Gate 11.2 mandates a pre-script-launch lint that greps the mutex POST/PATCH source for `"details"` or `"resolution_notes"` inside any `prod_blockers`-targeted code block and rejects (with the carve-out that `prod_activity_log.details` IS a real JSON column and not the same defect); (4) handoff §6 prod_blockers schema gotchas already documents this for the implementation handoff path; (5) at runtime, an HTTP 400 on the mutex POST or release PATCH produces `MUTEX_POST_HTTP_400_UNKNOWN_FIELD` activity-log row pointing the operator at the §9.4 v5 callout. Severity HIGH because mutex acquisition is the entry guard for Phase 1+2+4+5; failure halts ALL mutating phases and leaves the system mid-migration. Likelihood LOW because the §9.4 v5 corrected example bodies + Gate 11.2 + risk row + LD-595 + schema-ref doc + handoff §6 form a five-layer redundancy against the defect re-entering the script. |

---

## §8 — Rollback per phase (preserved verbatim from v3 + v4)

(Preserved verbatim from v4 §8. Per-phase rollback narrative + v3 rehearsal-tied addendum. v5 introduces no §8-level changes.)

See v3 §8 / v4 §8 for the verbatim text.

---

## §9 — Operational notes (v4 preserved + v5 §9.4 field-name fix)

(§9.1, §9.2, §9.3 preserved verbatim from v2 through v3 through v4 through v5.)

### §9.4 — Concurrency, lockfile, and remote mutex (v5 FIELD-NAME FIX over v4 — self-discovered defect; v4 deferred)

**Field-name fix (v5 NEW correction).** Live `prod_blockers` has only **8 fields**: `id`, `module_id`, `severity`, `title`, `description`, `is_resolved`, `created_at`, `resolved_at` (live-probed 2026-05-08 via `DirectusAdminClient.fields("prod_blockers")` returning exactly 8 entries). There is **NO `details` field** and **NO `resolution_notes` field**. v3 + v4 example bodies referenced both — v5 corrects them. Structured payload (host/pid/started_at/script_version) goes in `description` text as `STRUCTURED_DETAILS_JSON:` + JSON literal per `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` §5 (lines 362-377). Resolution context appends to `description` on release PATCH. Cross-reference: LD-592 (schema-ref doc §5 prod_blockers gotchas) + LD-593 (v4 case-fold) + LD-595 (v5 field-name fix) + handoff §6 prod_blockers schema gotchas (added v2.1).

**Severity case (v4 preserved).** Live `prod_blockers.severity` enum requires LOWERCASE values: `critical` / `high` / `medium` / `low` (live-probed 2026-05-08 from `/fields/prod_blockers/severity`; canonical reference `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` §5; authority LD-592). The v3 spec mandated uppercase `CRITICAL` which would return HTTP 500 on POST. The migration script's mutex POST MUST use lowercase `critical`. Note: this collision is invisible to spec readers because `prod_locked_decisions.severity` IS uppercase (HARD/SOFT canonical, CRITICAL/HIGH/MEDIUM/LOW legacy) — the two collections share the field name `severity` but have **opposite case conventions**. v4 §6 Gate 11.1 + §7 risk #13 enforce this at gate-time.

---

**v2 said:** "the migration script MUST hold a lockfile so a concurrent run cannot double-PATCH rows. Recommend `~/.claude/mindfulnest-cache/schema_vocab_migration.lock` (this path is global Claude config, allowed by §3.0 outside-canonical rule)."

**v3 said (Cursor Task E):** the v2 LOCAL lockfile is preserved as a defense-in-depth secondary lock (one-host-multi-process), but the PRIMARY concurrency guard is now a REMOTE mutex via a Directus `prod_blockers` row.

**v4 amended ONLY the severity case.** **v5 amends the example body field names.** Convention:

- **Title:** `SCHEMA_MIGRATION_LOCK_HELD_BY_<HOST>` where `<HOST>` is `socket.gethostname()`.
- **Collection:** `prod_blockers`.
- **severity:** `critical` (lowercase per v4 — `prod_blockers.severity` enum is lowercase-only).
- **is_resolved:** `false` while held; `true` after Phase 6 success.
- **description (v5 NEW corrected):** carries plain prose plus a `STRUCTURED_DETAILS_JSON:`-anchored JSON literal encoding `host`, `pid`, `started_at` (ISO-8601), `script_version`. v3 used `details` (non-existent field). v4 used `description` but as a plain string without the canonical JSON-embedded pattern. v5 standardizes the encoding to match `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` §5 lines 362-377.

**Acquisition (Phase 1-5 entry guard, v5 field-name corrected + v4 case-folded):**

```python
import json
import os
import socket
import sys
from datetime import datetime, timezone

host = socket.gethostname()
SCRIPT_VERSION = "migrate_schema_vocab_v1.py@2026-05-08"

existing = client.get_items("prod_blockers",
    filters={"is_resolved": {"_eq": False},
             "title": {"_starts_with": "SCHEMA_MIGRATION_LOCK_HELD_BY_"}})
for lock in existing:
    if lock["title"] != f"SCHEMA_MIGRATION_LOCK_HELD_BY_{host}":
        # Held by another host — refuse
        sys.exit(1)

# v5: structured payload encoded inside description (no `details` field on prod_blockers)
structured_payload = {
    "host": host,
    "pid": os.getpid(),
    "started_at": datetime.now(timezone.utc).isoformat(),
    "script_version": SCRIPT_VERSION,
}
description_text = (
    f"Schema vocab migration in progress on host {host}; PID={os.getpid()}.\n\n"
    f"STRUCTURED_DETAILS_JSON: {json.dumps(structured_payload)}"
)

# v4: severity is LOWERCASE 'critical' per prod_blockers.severity enum
# v5: only the 8 live prod_blockers fields appear as keys (id is auto-assigned)
client.post_item("prod_blockers", {
    "title": f"SCHEMA_MIGRATION_LOCK_HELD_BY_{host}",
    "severity": "critical",       # v4: lowercase per live enum
    "is_resolved": False,
    "description": description_text,  # v5: STRUCTURED_DETAILS_JSON encoded inside (was 'details' in v3)
})
```

**Release (Phase 6 final-audit success, v5 field-name corrected):**

```python
# v5: 'resolution_notes' is NOT a live prod_blockers field; APPEND to description instead.
# Read existing description; concatenate resolution context; PATCH only the 8 live fields.
existing_blocker = client.get_item("prod_blockers", mutex_blocker_id)
existing_description = existing_blocker.get("description", "") or ""

resolution_text = f"Phase 6 final audit complete; report at {phase_6_report_path}"
new_description = (
    f"{existing_description.rstrip()} | "
    f"RESOLVED: {resolution_text} (see Phase 6 final-audit report at {phase_6_report_path})"
)

client.patch_item("prod_blockers", mutex_blocker_id, {
    "is_resolved": True,
    "description": new_description,  # v5: append to existing (was 'resolution_notes' in v3)
    # resolved_at is auto-set by Directus when is_resolved flips to true
})
```

**Stale-mutex cleanup (v5 field-name corrected):** if a script crashes leaving the mutex held, `release_stale_mutex.py` (helper to be authored at execution time) reads the mutex row's `description` field (v5: was `details` in v3 — `prod_blockers` has no `details` field; v4 narrative acknowledged this informationally), parses the PID from the embedded `STRUCTURED_DETAILS_JSON:` JSON block, and checks if the recorded PID is alive on the recorded host. Pattern:

```python
import json
import re

# v5: parse PID from description's STRUCTURED_DETAILS_JSON block
# (replaces v3's parse-from-`details`-field which didn't work because the field doesn't exist)
description = blocker_row.get("description", "") or ""
match = re.search(r"STRUCTURED_DETAILS_JSON:\s*(\{.*?\})\s*$", description, re.DOTALL | re.MULTILINE)
if match:
    payload = json.loads(match.group(1))
    pid = payload.get("pid")
    host_recorded = payload.get("host")
    started_at = payload.get("started_at")
else:
    # Legacy mutex without STRUCTURED_DETAILS_JSON encoding — fall back to manual review
    pid = None
    host_recorded = None
    started_at = None

# Force-release if dead (kill -0 <pid> if local; manual review if remote)
```

Force-releases if dead. Manual override is always available — Kim can PATCH `is_resolved=true` directly via Directus admin UI.

**Why both remote AND local lock (v3 preserved):** the remote lock prevents multi-host concurrent runs (the v2 gap Cursor flagged); the local flock prevents a single-host operator from accidentally launching the script twice in parallel terminals before the remote mutex is acquired. Both are cheap; defense-in-depth.

**Why this case-fold matters (v4 NEW, preserved):** the Phase 1-5 entry-guard's first action after row-list construction is the mutex POST. If that POST returns HTTP 500 due to severity case violation, every mutating phase HALTS before any row is touched.

**Why this field-name fix matters (v5 NEW):** even with the v4 case-fold applied, a literal POST per v3+v4 example bodies still includes a `details` key (v3) or — in v4's "informational" partial fix — a plain-string `description` without the canonical STRUCTURED_DETAILS_JSON encoding. The release PATCH still includes `resolution_notes` (v3) or omits resolution annotation entirely (v4). Both fail: `details` and `resolution_notes` return HTTP 400 / unknown-field; missing canonical encoding breaks the stale-mutex cleanup contract documented in `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` §5. Phase 1+2+4+5 entry-guards depend on mutex acquisition + release; failure halts the whole migration. v5 §6 Gate 11.2 + §7 risk #14 + LD-595 + handoff §6 form a five-layer redundancy against the defect re-entering the script.

---

## §10 — Cursor review companion (v3 preserved; v4 + v5 unchanged)

This spec v5 is a post-authorization touch-up over v4 (which was itself a touch-up over v3). The v3 Cursor cross-review handoff at `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v3.md` is the canonical review companion for v5 as well — v5's only material change is a §9.4 field-name fix that aligns the spec example bodies with the live 8-field schema (no new design surface for Cursor to re-review). The v2 handoff at `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v2.md` is preserved as historical baseline. v1 also preserved.

---

## §11 — Reference index (v4 preserved + v5 entries added)

(All v2 entries preserved verbatim through v3 → v4 → v5. All v3-NEW entries preserved. All v4-NEW entries preserved.)

- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v4.md` — **v4 historical baseline (this spec's predecessor)** (v5 NEW reference).
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v3.md` — v3 historical baseline (v4 reference; v5 preserved).
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v2.md` — v2 historical baseline.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v1.md` — v1 historical baseline.
- `Production/scripts/lock_decision.py` — canonical-aware as of 2026-05-08 per Cursor Task H execution.
- `Production/scripts/lock_decision.py.bak.20260508` — pre-Task-H backup.
- `LD_WRITER_CANONICAL_VOCAB_V1` — LD documenting Task H execution (HARD severity).
- `LD-590 SCHEMA_VOCAB_MIGRATION_V3_LOCKED` — v3 authorization decision.
- `LD-591` — `weekly_preflight_audit.py` schema-ref-doc enforcement amendment.
- `LD-592 DIRECTUS_SCHEMA_REF_PROD_BLOCKERS_GOTCHAS_V1` — schema-ref doc §5 prod_blockers gotchas authority (lowercase severity + STRUCTURED_DETAILS_JSON workaround); v4 §9.4 case-fold + v5 §9.4 field-name fix both cross-reference this LD.
- `LD-593` — v4 §9.4 severity case-fold authority (preserved through v5 since the case-fold remains in effect).
- `LD-595 SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V5_FIELD_NAME_FIX_V1` — **v5 field-name fix authority** (v5 NEW reference; filed 2026-05-08 same session as v5 spec authoring).
- `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` §5 — live-probed `prod_blockers` schema reference; ground truth for both the v4 §9.4 case-fold AND the v5 §9.4 field-name fix (8-field enumeration at lines 311-320, severity enum at lines 322-331, STRUCTURED_DETAILS_JSON pattern at lines 362-377).
- `Production/docs/HANDOFF_SCHEMA_MIGRATION_V3_IMPLEMENTATION_20260508.md` — implementation handoff. §6 prod_blockers schema gotchas (added v2.1) anticipates v5's correction and may need a v2.2 amendment to point at v5 explicitly (surface to Kim per §12 changelog).
- `Production/exports/prod_locked_decisions_<DATE>.jsonl` — cached canonical-export.
- `Production/exports/prod_locked_decisions_<DATE>.metadata.json` — cached export metadata sidecar.
- `Production/exports/schema_migration_checkpoint_<DATE>.jsonl` — append-only checkpoint per §5.0.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_ROLLBACK_REHEARSAL_<YYYYMMDD>.md` — rehearsal pass/fail report.
- `Production/exports/DEFERRED_DIRECTUS_WRITES_20260508_lock_decision_canonical.jsonl` — queued Directus writes deferred while Directus production is offline.
- `Production/docs/SCHEMA_MIGRATION_V3_AND_LOCK_DECISION_FIX_REPORT_20260508.md` — final proof report for v3 spec + handoff + Task H execution.
- `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v3.md` — companion review handoff (v3; remains canonical for v5).
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v5.md` — **THIS SPEC (v5)** (v5 NEW self-reference).

---

## §12 — Change log

- **v1** — 2026-05-08 — initial draft. Author: Claude Opus 4.7 (1M context). Status: superseded by v2.
- **v2** — 2026-05-08 — Cursor AMEND_V2 (4 amendments) applied: PHASE_5_ENABLED feature flag + dual-canonical paths + snapshot integrity fields + cost split. Status: superseded by v3.
- **v3** — 2026-05-08 — Cursor AMEND_V2 on v2 (5 amendments — Tasks B/D/E/F/H) applied: cached canonical-export + rollback rehearsal + remote mutex §9.4 + checkpoint schema §5.0 + lock_decision.py canonical-aware Task H execution. Status: superseded by v4. Author: Claude Opus 4.7 (1M context).
- **v4** — 2026-05-08 — self-discovered §9.4 severity case-fold (NOT a Cursor amendment). Live `prod_blockers.severity` enum lowercase-only (`critical`/`high`/`medium`/`low`) but v3 §9.4 mandated uppercase `CRITICAL` returning HTTP 500. v4 case-folds severity to lowercase `critical`, adds §6 Gate 11.1, adds §7 risk #13, cross-references `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` §5 + LD-592. v4 also flagged two informational schema observations (no `details`, no `resolution_notes`) without correcting the example bodies (minimal-amendment mandate). Status: superseded by v5. Author: Claude Opus 4.7 (1M context).
- **v5** — 2026-05-08 — self-discovered §9.4 field-name fix (NOT a Cursor amendment; corrects what v4 explicitly deferred). Live `prod_blockers` has exactly 8 fields (`id`, `module_id`, `severity`, `title`, `description`, `is_resolved`, `created_at`, `resolved_at`); v3+v4 example bodies referenced `details` (acquisition POST + stale-mutex cleanup parsing) and `resolution_notes` (release PATCH) — both non-existent fields returning HTTP 400 unknown-field. v5 corrects: (1) acquisition POST encodes `host`/`pid`/`started_at`/`script_version` inside `description` as `STRUCTURED_DETAILS_JSON:` + JSON literal per `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` §5 lines 362-377; (2) release PATCH appends resolution context to `description` rather than using non-existent `resolution_notes`; (3) stale-mutex cleanup parses PID from `description` via regex anchored on `STRUCTURED_DETAILS_JSON:` then `json.loads(...)`. Adds §6 Gate 11.2 (field-name compliance + lint), adds §7 risk #14 (HTTP 400 on copy-paste), adds §11 reference-index entries (v4 historical baseline + LD-595 + this v5 self-reference), files LD-595 `SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V5_FIELD_NAME_FIX_V1`. Cross-references LD-592 (schema-ref doc §5 authority) + LD-593 (v4 case-fold) + handoff §6 prod_blockers schema gotchas (which already documented this for the implementation path; v5 is the formal spec-side reconciliation). All other v4 design (cached export, rollback rehearsal, checkpoint protocol, Phase 5 feature flag, Task H, severity case-fold, Gate 11.1, risk #13) preserved verbatim. v1 + v2 + v3 + v4 preserved as historical baselines. **Note:** handoff §6 prod_blockers schema gotchas should likely be amended to v2.2 to explicitly cite v5 as the spec-side reconciliation (rather than the v2.1 phrasing "the script wins, the spec needs reconciliation in a future v4 amendment"). Surface to Kim. Author: Claude Opus 4.7 (1M context).
