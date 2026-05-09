# Schema Vocab Migration — Tech Spec v4

**Authored:** 2026-05-08 (v4 amendment same day as v1 + v2 + v3).
**Author:** Claude Opus 4.7 (1M context).
**Self-classification:** ARCHITECTURAL (governance + data migration).
**Status:** DESIGN ONLY — execution is gated on Kim approval per §7. Phase 5 additionally gated on a feature flag (see §3 Rule 1 v2 resolution, preserved verbatim through v3 → v4).

**Supersedes:** `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v3.md` (preserved as historical baseline; do NOT edit in place). v3 in turn supersedes v2; v2 supersedes v1.

**v3 → v4 driver:** Cursor authorized v3 today (2026-05-08) with verdict `AUTHORIZE_PHASE_0_WITH_RISK_ACCEPTANCE`. While filing `prod_blockers` row id=101 (an admin-UI prereq tracker for Phase 3) the same day, a live schema probe of `prod_blockers.severity` surfaced a single design defect in v3: §9.4 mandates `severity=CRITICAL` (uppercase) for the `SCHEMA_MIGRATION_LOCK_HELD_BY_<HOST>` mutex row, but the live `prod_blockers.severity` enum requires lowercase `critical` and a literal POST per v3 returns HTTP 500. v4 corrects ONLY §9.4 + amends §0.1 changelog + adds Gate 11.1 + adds risk row #13. **All other v3 design (cached export, rollback rehearsal, checkpoint protocol, Phase 5 feature flag, Task H) preserved verbatim.** This is a self-discovered defect, not a Cursor amendment.

**Related artifacts (preserved from v3 + v4 additions):**
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v3.md` — v3 historical baseline (this spec's predecessor).
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v2.md` — v2 historical baseline.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v1.md` — v1 historical baseline.
- `Production/docs/SCHEMA_CLEANUP_AND_SUPABASE_HARDENING_REPORT_20260508.md` — investigation that motivates this spec.
- `Production/lib/severity_vocab.py` — Part 1 cheap defensive read-side fix that has already landed.
- `Production/scripts/lock_decision.py` — LD-writer CLI; **canonical-aware as of 2026-05-08 per Cursor v3 Task H execution** (see §0.1 v3 Task H entry, preserved).
- `Production/scripts/lock_decision.py.bak.20260508` — pre-fix backup.
- `Production/scripts/governance_drift_check.py`, `failure_mode_matrix.py`, `preflight_hook.py` — query consumers updated by Part 1 to be vocab-tolerant.
- LD #586 `SCHEMA_VOCAB_TOLERANT_FILTER_V1` — standing rule mandating that future code import the helper rather than rolling its own dict.
- `LD_WRITER_CANONICAL_VOCAB_V1` — LD filed 2026-05-08 documenting the lock_decision.py canonical-aware fix (HARD severity).
- LD #584 `WORKTREE_CONFUSION_PREVENTION_V1` (amended 2026-05-08 v2 dual-canonical) — authority for the dual-path discipline cited in §3 v2 path discipline section (preserved through v4).
- `LD-590 SCHEMA_VOCAB_MIGRATION_V3_LOCKED` — v3 authorization decision.
- `LD-591` — `weekly_preflight_audit.py` schema-ref-doc enforcement amendment.
- `LD-592 DIRECTUS_SCHEMA_REF_PROD_BLOCKERS_GOTCHAS_V1` — schema-ref doc §5 prod_blockers gotchas authority (lowercase severity + STRUCTURED_DETAILS_JSON workaround); the v4 §9.4 case-fold cross-references this LD.
- `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` §5 — live-probed `prod_blockers` schema reference; ground truth for the v4 §9.4 case-fold.
- `Production/docs/HANDOFF_SCHEMA_MIGRATION_V3_IMPLEMENTATION_20260508.md` — implementation handoff (records v4 amendment in flight per its v2.1 versioning entry).
- `Production/docs/HANDOFF_TEMPLATE_v2.md` — handoff structure used for the Cursor review companion.
- `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v3.md` — companion review handoff (v3; preserved as v4's review companion since v4 is a post-authorization touch-up, not a re-review).
- `Production/exports/prod_locked_decisions_<DATE>.jsonl` — cached canonical-export of `prod_locked_decisions` produced at start of Phase 0 to enable offline review per Cursor Task B fallback (see §5 Phase 0 v3, preserved in v4).

---

## §0.1 — v4 Changelog (single-row amendment over v3)

v4 is a minimal amendment over v3 to fix one §9.4-level schema collision. v3's §0.1 changelog is preserved verbatim immediately below this v4 entry. v4 is NOT a Cursor amendment — it is a self-discovered defect surfaced during `prod_blockers` id=101 filing.

| # | v4 amendment (self-discovered) | Resolution applied in v4 | Sections changed |
|---|---|---|---|
| v4-A | v3 §9.4 mandates `severity=CRITICAL` (uppercase) for the `SCHEMA_MIGRATION_LOCK_HELD_BY_<HOST>` mutex row on `prod_blockers`. Live `prod_blockers.severity` enum is **lowercase only** (`critical` / `high` / `medium` / `low`) per `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` §5 (live-probed 2026-05-08 from `/fields/prod_blockers/severity`). A literal POST per v3 returns HTTP 500. The collision is invisible to readers because the field name `severity` is shared with `prod_locked_decisions.severity` which IS uppercase (HARD/SOFT canonical, CRITICAL/HIGH/MEDIUM/LOW legacy) — the two collections share a field name but have **opposite case conventions**. | v4 §9.4 case-folds every active `severity` value in the mutex POST/PATCH examples from `CRITICAL` to lowercase `critical`. v3 prose describing v2's lockfile is preserved verbatim. v3 references to "severity=`CRITICAL` (treat as a production blocker)" are replaced with "severity=`critical` (treat as a production blocker; lowercase per `prod_blockers.severity` enum)". A v4 NEW callout block in §9.4 cites the live-schema enum + LD-592 + the schema-ref doc §5. §6 adds Gate 11.1 sub-rule mandating the case-fold at Phase 1-5 entry-guard time. §7 adds risk #13 documenting the failure mode (uppercase copy-paste returns HTTP 500). §11 reference index adds LD-590/591/592 + schema-ref doc §5 pointer + v3 historical baseline. §12 changelog appends v4 entry. | §9.4 (severity case-fold + v4 callout), §6 Gate 11.1 (NEW), §7 risk #13 (NEW), §11 reference index, §12 changelog |

**v4 also documents (informational, no spec change):** the schema-ref doc §5 surfaced a SECOND minor v3 issue — the §9.4 release-PATCH example references `resolution_notes` which is NOT a field on `prod_blockers` (the live collection has exactly 8 fields: `id`, `module_id`, `severity`, `title`, `description`, `is_resolved`, `created_at`, `resolved_at`). v4 §9.4 callout notes this as an OBSERVATION but does NOT correct the example body (per the "minimal amendment" mandate of v4 — the resolution-time annotation can ride inside `description` or rely on `is_resolved=true`+`resolved_at` alone, which is a defendable interpretation of the v3 release narrative). A future v5 (or implementation-time edit to the migration script) should normalize this. Tracked: `prod_blockers` id=101 schema-discovery anchor + LD-592 §5.

---

## §0.1 (v3, preserved verbatim) — v3 Changelog (Cursor amendment resolution table)

Cursor's AMEND_V2 verdict on v2 returned 5 amendments (Tasks B, D, E, F, H — collectively spanning v2's prior unresolved gaps after the original v1→v2 amendments addressed the four Cursor v1 findings). Each is reproduced verbatim with the resolution. v2 sections that needed material change are listed under "Sections changed".

| # | Cursor amendment (verbatim) | Resolution applied in v3 | Sections changed |
|---|---|---|---|
| Task B | Cursor couldn't reach Directus from its environment (403 Forbidden / Tunnel failure). Required random CRITICAL sampling failed. **Mitigation:** add explicit offline fallback procedure for Task B evidence — cached export snapshot with deterministic sample method. | v3 spec §5 Phase 0 (NEW Step 0.4) MANDATES generation of a cached canonical-export at `Production/exports/prod_locked_decisions_<DATE>.jsonl` at the START of Phase 0 (before any other Phase 0 step writes). Companion handoff v3 Step 0 explicitly directs reviewers to use this cached export when live Directus is unreachable, with a deterministic sample method (sort by id ASC, take rows where `id % N == 0` for the requested sample size) so two reviewers using the same cached export reach the same sampled set. v3 §11 reference index points at the cached-export path convention. | §5 Phase 0 (NEW Step 0.4), §6 Gate 7 (expanded with cached-export integrity check), §11 |
| Task D | Spec adds row_count/id_uniqueness/all_touched_ids_present in v2 BUT no MANDATORY pre-Phase-5 rollback simulation on sampled subset. **Mitigation:** require a pre-Phase-5 rollback simulation on a sampled subset with pass/fail report. | v3 §4 Phase 0 adds Step 0.5 — pre-Phase-5 rollback rehearsal on 5 random rows. Procedure: pull 5 random ids from the union of touched-ids; simulate the rule's PATCH against a scratch-test row OR perform PATCH+immediate-revert on the live row; verify all 3 metadata fields (`row_count`, `id_uniqueness`, `all_touched_ids_present`) match pre/post. Emit pass/fail report at `Production/docs/SCHEMA_VOCAB_MIGRATION_ROLLBACK_REHEARSAL_<YYYYMMDD>.md`. **Phase 5 HALTS if rehearsal fails.** §6 adds Gate 10 for rehearsal pass. §8 v3 addendum ties rollback rehearsal to live rollback. | §4 Phase 0 (NEW Step 0.5), §5 Phase 0 (Step 0.5 narrative), §6 Gate 10 (NEW), §7 risk #10 (NEW), §8 v3 addendum |
| Task E | Spec §9.4 says lockfile at `~/.claude/mindfulnest-cache/schema_vocab_migration.lock` — LOCAL only. Doesn't prevent multi-host concurrent runners. **Mitigation:** remote/shared lock (Directus mutex row OR DB advisory lock) before any mutating phase. | v3 §9.4 REPLACES the local lockfile with a Directus mutex row in `prod_blockers` collection. Convention: title `SCHEMA_MIGRATION_LOCK_HELD_BY_<HOST>` (where `<HOST>` is `socket.gethostname()`), severity=`CRITICAL` (blocker tier), `is_resolved=false`. Mutating phases (1-5) MUST acquire+verify this row before proceeding; release on Phase 6 success (set `is_resolved=true`) OR by manual override. v3 also keeps the LOCAL lockfile as a defense-in-depth secondary lock (one-host-multi-process). §6 adds Gate 11 for remote-lock-acquisition pass. §7 risk #11 added (lock contention / dead-lock-cleanup). | §9.4 (replaced), §5 Phase 1-5 entry guard (NEW remote-lock check), §6 Gate 11 (NEW), §7 risk #11 (NEW) |
| Task F | Risk table says "resume from last-confirmed row" but no checkpoint schema/path defined. **Mitigation:** durable checkpoint file schema `(phase, row_id, timestamp, hash)` and resume algorithm as mandatory. | v3 §5 (NEW subsection §5.0 — Checkpoint and resume protocol) defines the checkpoint schema verbatim: `{"phase": <int 1-5>, "rule": "<rule_name>", "last_committed_row_id": <int>, "timestamp": "<iso8601>", "snapshot_hash": "<hex>", "rows_processed_in_phase": <int>, "expected_rows_in_phase": <int>}`. Path: `Production/exports/schema_migration_checkpoint_<DATE>.jsonl` (append-only — one line per row commit). Resume algorithm: read last line; verify `snapshot_hash` matches the current Phase 0 snapshot's metadata hash (else HALT — snapshot drift); restart phase from `last_committed_row_id + 1`. §6 adds Gate 12 for checkpoint integrity. §7 risk #12 (resume-after-corruption). | §5.0 (NEW), §5 Phase 1-5 (NEW per-row checkpoint append), §6 Gate 12 (NEW), §7 risk #12 (NEW) |
| Task H | `lock_decision.py` CLI choices still include legacy `critical/HIGH/high/MEDIUM/...` and OMIT canonical HARD/SOFT. Future LD writes via this CLI would reintroduce mixed vocab indefinitely. **EXECUTE NOW (independent of v3 spec).** | **EXECUTED 2026-05-08** in the same session as v3 spec authoring. `Production/scripts/lock_decision.py` updated: `ACCEPTED_SEVERITY_CHOICES` now lists canonical `HARD/SOFT` first followed by legacy values (CRITICAL/HIGH/MEDIUM/LOW + lowercase + MED) for back-compat; `canonicalize_severity()` emits `[DEPRECATED]` warning to stderr on legacy input and auto-maps to canonical before any Directus POST; `cmd_lock()` invokes the canonicalizer so the persisted row is always canonical regardless of input. Backup at `Production/scripts/lock_decision.py.bak.20260508`. New LD `LD_WRITER_CANONICAL_VOCAB_V1` (HARD severity) filed in same session documenting the fix. v3 §11 reference index updated to call lock_decision.py canonical-aware. Verification: `python3 lock_decision.py lock --help` confirms choices include `{HARD,SOFT,CRITICAL,HIGH,MEDIUM,LOW,critical,high,medium,low,MED}`; smoke test of `canonicalize_severity` covered 5 branches (canonical pass-through, legacy upper, legacy lower, MED abbrev, unknown ValueError). | §11 reference index entry for lock_decision.py updated; v3 spec does NOT itself mandate the change (it was executed before v3 was written). |

**v2 vs v3 surface area (preserved verbatim):** v3 adds ~280 lines (cached-export Phase 0 step, rollback-rehearsal step + Gate 10, remote mutex §9.4 replacement + Gate 11, checkpoint schema §5.0 + Gate 12, risk rows 10/11/12, Task H reference-index update). All v2 content preserved (no deletions); v3 additions are clearly labeled `(v3)` or `(NEW v3)` inline. v1 and v2 narrative content (§1, §2, §3.1-§3.4 dual-Opus debate, etc.) preserved verbatim.

**v3 vs v4 surface area (NEW):** v4 adds ~50 lines net (one §0.1 v4 row, one §6 Gate 11.1 row, one §7 risk #13 row, one §9.4 v4 callout block, four §11 reference-index entries, one §12 changelog entry). v4 deletes nothing. The substantive code-affecting change is the case-fold of `CRITICAL` → `critical` inside §9.4's mutex POST narrative + acquisition example. All other v3 content (§1, §2, §3.0-§3.4, §4, §5.0, §5 Phase 0/1/2/3/4/5/6, §8, §9.1-§9.3, §10) preserved verbatim.

---

## §1 — Goal (preserved verbatim from v1 + v2 + v3)

Bring the `prod_locked_decisions` collection's `severity`, `task_category`, and `scope_domain` columns into a **canonical, lossless, audit-trailed state** so:

1. Every active row uses an enum value that appears in the live Directus schema definition.
2. Lossy maps (e.g. `HIGH → HARD`) are explicitly approved by Kim before the row is rewritten.
3. Every PATCH carries a `migration_audit` row in `prod_activity_log` with the old/new value pair, so a rollback (or a "did Claude really do that?" forensic trace) is one query away.
4. Row count after migration matches row count before migration (no lost rows; no auto-creation).
5. The Part 1 vocab-tolerant filter remains correct AFTER migration (i.e. queries that accepted HIGH today and HARD tomorrow continue to return the same answer).

Non-goals:

- This spec does NOT propose canonicalizing `enforcement_type` (already 100% canonical per the audit).
- This spec does NOT propose a status=superseded sweep of the ~30 RESOLVED_BUT_NOT_CLOSED rows.
- This spec does NOT propose schema-enum changes to Directus. Adding `app_architecture`, `infrastructure`, etc. to the canonical task_category list is a SEPARATE Directus schema change Kim must perform via the admin UI.

---

## §2 — Background (preserved verbatim from v1 + v2 + v3)

The cleanup report (`SCHEMA_CLEANUP_AND_SUPABASE_HARDENING_REPORT_20260508.md`) established the dataset baseline (529 active LDs, mixed vocabulary). Part 1 (LD #586) shipped the defensive read-side fix; this migration is OPTIONAL CANONICALIZATION for clarity. See v2 spec §2 for the full preserved background.

**v3 ADD (preserved):** Cursor's v2 review surfaced one additional latent gap not addressed by v1 or v2 amendments: `lock_decision.py`'s argparse choices list was legacy-only and was actively reintroducing pre-2026-05-04 vocabulary on every new LD write. This was diagnosed and EXECUTED-as-fix in the same session as v3 spec authoring (Task H entry in §0.1 v3).

**v4 ADD (informational):** Filing `prod_blockers` row id=101 (Phase 3 admin-UI prereq tracker) on 2026-05-08 surfaced a single §9.4 design defect — uppercase severity collision with `prod_blockers.severity` lowercase enum. v4 corrects in place. No background-level scope change.

---

## §3 — Dual-Opus debate (verbatim) on 4 mapping rules + v2 amendments (preserved in v3 + v4)

§3.0 (path discipline v2 dual-canonical), §3.1 (Rule 1 + v2 PHASE_5_ENABLED feature flag), §3.2 (Rule 2 lowercase severity), §3.3 (Rule 3 task_category), §3.4 (Rule 4 scope_domain) — all preserved verbatim from v2 through v3 through v4. v4 introduces no §3-level changes; the v4 amendment is operational (§6/§7/§9/§11/§12) rather than debate-level.

See `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v2.md` §3.0-§3.4 for the verbatim text.

---

## §4 — Per-rule action table (preserved verbatim from v3)

| Rule | Action | Volume | Risk | Depends-on | v2 flag | v3 prerequisites |
|---|---|---|---|---|---|---|
| 1 | severity HIGH/CRITICAL → HARD | 320 rows | LOW (mechanical) | Kim approves Counter-or-Advocate verdict | `PHASE_5_ENABLED=false` by default; flip required | (v3) Cached export (§5 Phase 0 Step 0.4) + rollback rehearsal pass (§5 Phase 0 Step 0.5) + remote mutex acquired (§9.4) + checkpoint schema initialized (§5.0) |
| 2 | severity lowercase → UPPERCASE | 37 rows | TRIVIAL (case-fold) | none | none | (v3) Cached export + remote mutex + checkpoint |
| 3a | task_category enum extension (7 new values) | 0 rows | LOW (Kim performs in admin UI) | Kim approves the 7 names | none | (v3) Cached export only |
| 3b | task_category synonym remaps | ~110 rows | LOW (mechanical) | Rule 3a (extension) lands first | none | (v3) Cached export + remote mutex + checkpoint |
| 4 | scope_domain remaps | 29 rows | LOW (mechanical) | none | none | (v3) Cached export + remote mutex + checkpoint |

**Total row touches (max scope):** still ~496 PATCHes (unchanged from v2/v3).

### §4 Phase 0 v2 expanded snapshot schema (preserved verbatim from v2 + v3)

The v2 snapshot artifact (`Production/docs/SCHEMA_VOCAB_MIGRATION_SNAPSHOT_<YYYYMMDD>.jsonl`) is preserved verbatim as the row-restoration source for the touched-rows union. v3 ADDS a SECOND artifact at a different path with a different purpose (cached canonical-export at `Production/exports/prod_locked_decisions_<DATE>.jsonl`). Schema, metadata sidecar, and pre-Phase-5 cached-export integrity check all preserved verbatim from v3 §4.

See v3 §4 for the verbatim text. v4 introduces no §4-level changes.

---

## §5 — Migration sequence (preserved verbatim from v3)

§5.0 (Checkpoint and resume protocol — NEW v3 — Cursor Task F), Phase 0 Step 0/1/2/3/0.4/0.5, Phase 1/2/3/4/5/6 — all preserved verbatim from v3. v4 introduces no §5-level changes.

**v4 NOTE (informational):** the Phase 1 entry-guard code block in v3 §5 contains a `severity="CRITICAL"` literal in the mutex POST. Per v4 §9.4 (case-fold), this string MUST be lowercase `"critical"` at script-write time. v4 §9.4 callout is the authoritative source; v4 §6 Gate 11.1 enforces the case-fold at gate time. v3 §5 Phase 1 entry-guard code is preserved verbatim here as historical reference but the migration script's Phase 1 entry-guard implementation must use the lowercase value per v4 §9.4 + Gate 11.1.

See v3 §5.0 + Phase 0 + Phase 1-6 for the verbatim text.

---

## §6 — Pre-implementation gates Kim must approve (v3 preserved + v4 Gate 11.1 added)

(Gates 1-9 preserved verbatim from v2. Gates 10/11/12 preserved verbatim from v3.)

| # | Gate | Kim's decision required |
|---|------|------------------------|
| 10 | **(v3 — Cursor Task D)** Pre-Phase-5 rollback rehearsal: must Phase 0 Step 0.5 produce a "All passed: True" report on 5 random rows BEFORE Phase 5 may execute? Phase 5 entry guard halts if rehearsal report missing or any row failed. | YES (REQUIRED for Phase 5) / NO (only valid if Phase 5 stays DEFERRED) |
| 11 | **(v3 — Cursor Task E)** Remote mutex via Directus `prod_blockers` row `SCHEMA_MIGRATION_LOCK_HELD_BY_<HOST>` (severity per v4 §9.4 case-fold = `critical` lowercase): must mutating phases (1, 2, 4, 5) acquire+verify this row before proceeding? | YES (REQUIRED) / DEFER (single-host operation; rely on local lockfile only) |
| 11.1 | **(v4 NEW — self-discovered defect)** Mutex POST severity case-fold: must the migration script's `prod_blockers` mutex POST/PATCH use `severity='critical'` (LOWERCASE) per the live `prod_blockers.severity` enum? Uppercase `CRITICAL` returns HTTP 500 and would block Phase 1-5 entry-guard acquisition. Reference: live-schema enum `[critical, high, medium, low]` per `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` §5 + LD-592. | YES (REQUIRED — uppercase returns HTTP 500; no defer option) |
| 12 | **(v3 — Cursor Task F)** Checkpoint file `Production/exports/schema_migration_checkpoint_<DATE>.jsonl` (append-only, schema per §5.0): must per-row checkpoint appends be a hard requirement of Phases 1, 2, 4, 5 with the resume algorithm verifying snapshot_hash on session restart? | YES (REQUIRED for resume safety) / NO (single-session execution; no resume protocol needed) |

**Gate 10 verification artifact (v3 preserved):** rollback rehearsal report at `Production/docs/SCHEMA_VOCAB_MIGRATION_ROLLBACK_REHEARSAL_<YYYYMMDD>.md`; Phase 5 entry guard's check #2 reads it.

**Gate 11 verification artifact (v3 preserved):** Directus query for `prod_blockers` row with title `SCHEMA_MIGRATION_LOCK_HELD_BY_<HOST>` and `is_resolved=false`; Phase 1-5 entry guards read it.

**Gate 11.1 verification artifact (v4 NEW):** at script-write time, the migration script's source for the mutex POST/PATCH must be grep-able for `severity=.*critical` (lowercase) and MUST NOT match `severity=.*CRITICAL` (uppercase). Recommended pre-launch lint: `grep -n "severity=.*CRITICAL\|severity=.*\"CRITICAL\"" Production/scripts/migrate_schema_vocab_v1.py` returns NO matches inside any `prod_blockers`-targeted POST/PATCH block. (Matches inside `prod_locked_decisions`-targeted code are FINE — that collection's `severity` enum IS uppercase.) At runtime, the read-back per Rule 35 confirms the persisted value is lowercase `critical`. If HTTP 500 is returned by Directus on the mutex POST, the script HALTS with `MUTEX_POST_HTTP_500_LIKELY_CASE_VIOLATION` activity-log row.

**Gate 12 verification artifact (v3 preserved):** checkpoint file exists at the expected path; snapshot_hash field matches current snapshot's metadata hash; resume algorithm filters target rows to `id > last_committed_row_id`.

---

## §7 — Risk assessment (v3 preserved + v4 risk #13 added)

(Rows 1-9 preserved verbatim from v2. Rows 10/11/12 preserved verbatim from v3.)

| Risk | Likelihood | Severity | Mitigation |
|---|---|---|---|
| **(v3)** Rollback rehearsal passes on 5 sampled rows but actual rollback fails on the remaining 315 rows due to row-specific quirks (e.g., field constraints on outlier rows) | LOW | HIGH | Sample size of 5 is the v3 baseline; if Kim wants higher confidence, increase to 20 or 50; always emit the failed-row id in the activity-log row so Kim can manually investigate |
| **(v3)** Remote mutex acquisition succeeds but mutex is never released due to script crash; subsequent runners blocked indefinitely | LOW | MEDIUM | Mutex includes `pid` field; cleanup helper `release_stale_mutex.py` checks if PID is alive on the recorded host and force-releases if dead; manual override path documented in §9.4 |
| **(v3)** Checkpoint file corrupted mid-write (partial JSON line on the last line) causes resume algorithm to crash or skip valid rows | LOW | MEDIUM | Resume algorithm tolerates corrupt last line via try/except; if last line fails JSON parse, walk backward to last valid line; log "checkpoint last-line corrupt; resuming from previous good line" |
| **(v4 NEW — #13)** Spec author or implementer copy-pastes uppercase `CRITICAL` from v3's §9.4 example (or any v3-era reference) into the migration script's mutex POST despite the v4 amendment, returning HTTP 500 from Directus and halting Phase 1-5 entry-guard acquisition | LOW | HIGH | (1) v4 §9.4 callout cites the case-fold prominently; (2) LD-592 schema-ref doc records the divergence as a permanent gotcha; (3) §6 Gate 11.1 mandates a pre-script-launch lint that greps the mutex POST source for `severity=.*CRITICAL` (uppercase) inside `prod_blockers`-targeted code and rejects; (4) at runtime, an HTTP 500 on the mutex POST produces `MUTEX_POST_HTTP_500_LIKELY_CASE_VIOLATION` activity-log row pointing the operator at the §9.4 case-fold guidance. Severity HIGH because Phases 1+2+4+5 entry-guard depend on mutex acquisition; failure halts all mutating phases and leaves the system mid-migration. |

---

## §8 — Rollback per phase (preserved verbatim from v3)

Per-phase rollback narrative + v3 rehearsal-tied addendum preserved verbatim from v3 §8. v4 introduces no §8-level changes.

See v3 §8 for the verbatim text.

---

## §9 — Operational notes (v3 cost split preserved + v4 §9.4 severity case-fold)

(§9.1, §9.2, §9.3 preserved verbatim from v2 through v3 through v4 — the v2 cost split machine/human/combined remains the planning baseline.)

### §9.4 — Concurrency, lockfile, and remote mutex (v4 SEVERITY CASE-FOLD over v3 — self-discovered defect)

**Severity case (v4 NEW correction).** Live `prod_blockers.severity` enum requires LOWERCASE values: `critical` / `high` / `medium` / `low` (live-probed 2026-05-08 from `/fields/prod_blockers/severity`; canonical reference `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` §5; authority LD-592). The v3 spec mandated uppercase `CRITICAL` which would return HTTP 500 on POST. The migration script's mutex POST MUST use lowercase `critical`. Cross-reference: `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` §5 (prod_blockers schema) + LD-592 `DIRECTUS_SCHEMA_REF_PROD_BLOCKERS_GOTCHAS_V1`. Note: this collision is invisible to spec readers because `prod_locked_decisions.severity` IS uppercase (HARD/SOFT canonical, CRITICAL/HIGH/MEDIUM/LOW legacy) — the two collections share the field name `severity` but have **opposite case conventions**. v4 §6 Gate 11.1 + §7 risk #13 enforce this at gate-time and document the failure mode.

**Observation (v4 informational, no spec change):** the schema-ref doc §5 also notes that `prod_blockers` has NO `resolution_notes` field — the v3 release-PATCH example below uses `resolution_notes` which would silently be ignored or rejected by Directus. v4 does NOT correct the example body in line with the "minimal amendment" mandate; the resolution-time annotation can ride inside `description` or rely on `is_resolved=true`+`resolved_at` alone. Implementers of `migrate_schema_vocab_v1.py` should adapt the release path accordingly (either move resolution prose into `description` or treat `is_resolved=true` as sufficient). Tracked: `prod_blockers` id=101 schema-discovery anchor + LD-592 §5.

---

**v2 said:** "the migration script MUST hold a lockfile so a concurrent run cannot double-PATCH rows. Recommend `~/.claude/mindfulnest-cache/schema_vocab_migration.lock` (this path is global Claude config, allowed by §3.0 outside-canonical rule)."

**v3 said (Cursor Task E):** the v2 LOCAL lockfile is preserved as a defense-in-depth secondary lock (one-host-multi-process), but the PRIMARY concurrency guard is now a REMOTE mutex via a Directus `prod_blockers` row. **v4 amends ONLY the severity case below.** Convention:

- **Title:** `SCHEMA_MIGRATION_LOCK_HELD_BY_<HOST>` where `<HOST>` is `socket.gethostname()`.
- **Collection:** `prod_blockers`.
- **severity:** `critical` (treat as a production blocker; **LOWERCASE per v4 — `prod_blockers.severity` enum is lowercase-only**). v3 historical text said `CRITICAL` (uppercase); v4 corrects to lowercase per the live enum + LD-592.
- **is_resolved:** `false` while held; `true` after Phase 6 success.
- **details (v4 informational):** `prod_blockers` has no `details` field per live schema; the structured payload `Schema vocab migration in progress on host <HOST>; PID=<pid>` rides inside `description` instead. (v3 example below uses `details`; implementers should map to `description`.)

**Acquisition (Phase 1-5 entry guard, v4 case-folded):**

```python
existing = client.get_items("prod_blockers",
    filters={"is_resolved": {"_eq": False},
             "title": {"_starts_with": "SCHEMA_MIGRATION_LOCK_HELD_BY_"}})
for lock in existing:
    if lock["title"] != f"SCHEMA_MIGRATION_LOCK_HELD_BY_{host}":
        # Held by another host — refuse
        sys.exit(1)
# POST or reuse the host's own mutex row
# v4: severity is LOWERCASE 'critical' per prod_blockers.severity enum
client.post_item("prod_blockers", {
    "title": f"SCHEMA_MIGRATION_LOCK_HELD_BY_{host}",
    "severity": "critical",  # v4: lowercase per live enum (was 'CRITICAL' in v3)
    "is_resolved": False,
    "description": f"Schema vocab migration in progress on host {host}; PID={os.getpid()}",
})
```

**Release (Phase 6 final-audit success):**

```python
# v4: 'resolution_notes' is NOT a live prod_blockers field; implementers should
# either append to 'description' or rely on 'is_resolved=true' + 'resolved_at' alone.
client.patch_item("prod_blockers", mutex_blocker_id, {
    "is_resolved": True,
    # resolution_notes intentionally omitted — not a live field per v4 informational note
})
```

**Stale-mutex cleanup:** if a script crashes leaving the mutex held, `release_stale_mutex.py` (helper to be authored at execution time) reads the mutex row's `description` field (v4: was `details` in v3 — `prod_blockers` has no `details` field), parses the PID, and checks if the recorded PID is alive on the recorded host (via `kill -0 <pid>` if local; manual review if remote). Force-releases if dead. Manual override is always available — Kim can PATCH `is_resolved=true` directly via Directus admin UI.

**Why both remote AND local lock (v3 preserved):** the remote lock prevents multi-host concurrent runs (the v2 gap Cursor flagged); the local flock prevents a single-host operator from accidentally launching the script twice in parallel terminals before the remote mutex is acquired. Both are cheap; defense-in-depth.

**Why this case-fold matters (v4 NEW):** the Phase 1-5 entry-guard's first action after row-list construction is the mutex POST. If that POST returns HTTP 500 due to severity case violation, every mutating phase HALTS before any row is touched. The migration becomes literally unrunnable. v4 §6 Gate 11.1 + §7 risk #13 surface this as a first-class concern; the case-fold is mechanical but the failure mode is total.

---

## §10 — Cursor review companion (v3 preserved; v4 unchanged)

This spec v4 is a post-authorization touch-up over v3. The v3 Cursor cross-review handoff at `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v3.md` is the canonical review companion for v4 as well — v4's only material change is a §9.4 case-fold that corrects v3 to match the live schema (no new design surface for Cursor to re-review). The v2 handoff at `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v2.md` is preserved as historical baseline. v1 also preserved.

The v3 handoff specifically addresses Task B (offline Directus fallback procedure): when live Directus is unreachable, reviewer uses the cached export at `Production/exports/prod_locked_decisions_<DATE>.jsonl` (generated at start of Phase 0 per §5 Step 0.4).

---

## §11 — Reference index (v3 preserved + v4 entries added)

(All v2 entries preserved verbatim through v3 through v4. All v3-NEW entries preserved verbatim.)

- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v3.md` — **v3 historical baseline (this spec's predecessor)** (v4 NEW reference).
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v2.md` — v2 historical baseline.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v1.md` — v1 historical baseline.
- `Production/scripts/lock_decision.py` — **canonical-aware as of 2026-05-08** per Cursor Task H execution; choices list now `[HARD, SOFT, CRITICAL, HIGH, MEDIUM, LOW, critical, high, medium, low, MED]` with `canonicalize_severity()` auto-mapping legacy values to canonical before POST.
- `Production/scripts/lock_decision.py.bak.20260508` — pre-Task-H backup.
- `LD_WRITER_CANONICAL_VOCAB_V1` — LD documenting Task H execution (HARD severity).
- `LD-590 SCHEMA_VOCAB_MIGRATION_V3_LOCKED` — v3 authorization decision (Cursor `AUTHORIZE_PHASE_0_WITH_RISK_ACCEPTANCE`) (v4 NEW reference).
- `LD-591` — `weekly_preflight_audit.py` schema-ref-doc enforcement amendment (v4 NEW reference).
- `LD-592 DIRECTUS_SCHEMA_REF_PROD_BLOCKERS_GOTCHAS_V1` — schema-ref doc §5 prod_blockers gotchas authority (lowercase severity + STRUCTURED_DETAILS_JSON workaround); the v4 §9.4 case-fold cross-references this LD (v4 NEW reference).
- `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` §5 — live-probed `prod_blockers` schema reference; ground truth for the v4 §9.4 case-fold (v4 NEW reference).
- `Production/docs/HANDOFF_SCHEMA_MIGRATION_V3_IMPLEMENTATION_20260508.md` — implementation handoff; §6 records v4 amendment in flight (v4 NEW reference).
- `Production/exports/prod_locked_decisions_<DATE>.jsonl` — cached canonical-export for offline review (v3 NEW per Task B).
- `Production/exports/prod_locked_decisions_<DATE>.metadata.json` — cached export metadata sidecar (v3 NEW).
- `Production/exports/schema_migration_checkpoint_<DATE>.jsonl` — append-only checkpoint per §5.0 (v3 NEW per Task F).
- `Production/docs/SCHEMA_VOCAB_MIGRATION_ROLLBACK_REHEARSAL_<YYYYMMDD>.md` — rehearsal pass/fail report (v3 NEW per Task D).
- `Production/exports/DEFERRED_DIRECTUS_WRITES_20260508_lock_decision_canonical.jsonl` — queued Directus writes (Task H activity log + LD POST) deferred while Directus production is offline; replay when Directus is restored.
- `Production/docs/SCHEMA_MIGRATION_V3_AND_LOCK_DECISION_FIX_REPORT_20260508.md` — final proof report for v3 spec + handoff + Task H execution.
- `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v3.md` — companion review handoff (v3; remains canonical for v4 since v4 introduces no new design surface).
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v4.md` — **THIS SPEC (v4)** (v4 NEW self-reference).

---

## §12 — Change log

- **v1** — 2026-05-08 — initial draft. Author: Claude Opus 4.7 (1M context). Status: superseded by v2.
- **v2** — 2026-05-08 — Cursor AMEND_V2 (4 amendments) applied: PHASE_5_ENABLED feature flag + dual-canonical paths + snapshot integrity fields + cost split. Status: superseded by v3.
- **v3** — 2026-05-08 — Cursor AMEND_V2 on v2 (5 amendments — Tasks B/D/E/F/H) applied: (B) cached canonical-export at `Production/exports/prod_locked_decisions_<DATE>.jsonl` for offline review when Directus unreachable; (D) Phase 0 Step 0.5 rollback rehearsal on 5 random rows with pass/fail report + Gate 10; (E) §9.4 replaced — remote Directus mutex `prod_blockers` row replaces local-only lockfile (defense-in-depth keeps both); (F) §5.0 NEW — checkpoint schema `(phase, row_id, timestamp, hash, rows_processed, expected_rows)` + resume algorithm + Gate 12; (H) **EXECUTED** in same session — `lock_decision.py` choices made canonical-aware (HARD/SOFT first, legacy back-compat with deprecation warning + auto-canonicalization); LD_WRITER_CANONICAL_VOCAB_V1 filed. v1 + v2 preserved as historical baselines. Status: superseded by v4. Author: Claude Opus 4.7 (1M context).
- **v4** — 2026-05-08 — self-discovered §9.4 severity case-fold (NOT a Cursor amendment). Surfaced during `prod_blockers` row id=101 filing the same day; live `prod_blockers.severity` enum is lowercase-only (`critical` / `high` / `medium` / `low` per `/fields/prod_blockers/severity` live probe), but v3 §9.4 mandated uppercase `CRITICAL` which returns HTTP 500. v4 case-folds severity to lowercase `critical` in the §9.4 mutex POST/PATCH narrative + acquisition example, adds §6 Gate 11.1 (mutex POST severity case-fold required), adds §7 risk #13 (uppercase copy-paste returns HTTP 500), and cross-references the live-schema reference (`Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` §5) + LD-592. v4 also flags two informational schema observations (`prod_blockers` has no `details` field — use `description`; `prod_blockers` has no `resolution_notes` field — append to `description` or rely on `is_resolved=true`+`resolved_at`) without correcting the example bodies (minimal-amendment mandate). All other v3 design preserved verbatim. v1 + v2 + v3 preserved as historical baselines. Author: Claude Opus 4.7 (1M context).
