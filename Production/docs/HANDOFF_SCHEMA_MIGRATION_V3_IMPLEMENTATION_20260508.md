# HANDOFF — Schema Vocab Migration v3 — Implementation (Phases 0-4 + 6 autonomous; Phase 5 self-gated on PHASE_5_ENABLED)

**Header**

- **Title:** Schema Vocab Migration v3 — Implementation (Phase 0 non-mutating dry-run + cached export + snapshot + rollback rehearsal; Phase 1 Rule 4 scope_domain remap; Phase 2 Rule 2 lowercase severity → UPPER; Phase 3 admin-UI mechanical detection; Phase 4 Rule 3b task_category synonym remap; Phase 6 final audit; Phase 5 self-gated on PHASE_5_ENABLED env var)
- **Target session:** Terminal CLI (autonomous-mode authorized for Phases 0-4 + 6; mechanical halts only on real failures per §4 below; Phase 5 stays self-gated on spec §3.1 PHASE_5_ENABLED env var which this session does NOT set)
- **Source spec:** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v8.md` — Dropbox-rooted (canonical root #1) — sha256 `c6220e519f5b8fb023e163936099f153610ac078d4d3392c6d9f9a454267c052`, 321 lines, 47,583 bytes (was v3 stale SHA-1; v8 amendment 2026-05-09 — current spec authority is v8 per CLI dispatch session findings + LD-NEW SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V8_DRY_RUN_FINDINGS_AMENDMENT_V1; v2.4 amendments already redirected the §11 versioning trail through v6 → v7 → v8, this surgical edit closes out the §1-area Header bullet drift)
- **Source session:** gallant-bouman-804b4f worktree (handoff authored from worktree; implementation runs against canonical roots, NOT inside `.claude/worktrees/`)
- **Estimated time:** 8-12 hours machine (Phases 0-4 + 6 across ~496 row PATCHes via §5.0 checkpoint protocol) + Kim review of final report only if a mechanical halt fired
- **Authority:**
  - Cursor verdict on schema migration v3 = `AUTHORIZE_PHASE_0_WITH_RISK_ACCEPTANCE` (offline-fallback review based on cached export + sidecars + deferred-write evidence + Kim's live confirmation of LD 588 LD_WRITER_CANONICAL_VOCAB_V1; no v4-level design blocker found)
  - LD 586 `SCHEMA_VOCAB_TOLERANT_FILTER_V1` (Part 1 read-side defensive fix, predecessor)
  - LD 588 `LD_WRITER_CANONICAL_VOCAB_V1` (Task H executed 2026-05-08; LD POST confirmed live by Kim)
  - LD 584 `WORKTREE_CONFUSION_PREVENTION_V1` (DS-27 v2 dual-canonical) — authority for absolute-path discipline
  - LD `GATE_CHECK_DISCIPLINE_NO_AUTONOMOUS_BYPASS_V1` (id=578; DS-26 authority)
- **Authoring template:** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_TEMPLATE_v2.md` — Dropbox-rooted (canonical root #1)
- **Self-classification:** ARCHITECTURAL (governance + data-touching migration; first migration to introduce remote-mutex, checkpoint, and rollback-rehearsal disciplines on `prod_locked_decisions`)
- **Confidence:** [CONFIRMED — spec v3 read end-to-end same session; lock_decision.py Task H execution confirmed via .bak.20260508 file; LD 588 confirmed live by Kim in chat]

---

## §1 Mission

Implement schema vocab migration v3 end-to-end with the EXCEPTION of Phase 5 (which is self-gated by spec §3.1 PHASE_5_ENABLED env var; this session does NOT set the env var, so Phase 5 mechanically halts at its entry-guard with `PHASE_5_GATED_NO_FLAG` activity-log row + clean exit 0). Concretely: (a) Phase 0 non-mutating dry-run + cached canonical-export of `prod_locked_decisions` per Cursor Task B + row-restoration snapshot for the touched-rows union per spec §4 + dry-run report enumerating every planned PATCH + rollback rehearsal on 5 deterministically-sampled rows per Cursor Task D / spec §5 Step 0.5; (b) Phase 1 Rule 4 scope_domain remap (~29 rows) per spec §5 Phase 1 with §9.4 remote mutex + §5.0 checkpoint append per row; (c) Phase 2 Rule 2 lowercase severity → UPPER (~37 rows); (d) Phase 3 admin-UI gate detection (mechanical: probe live Directus schema for the 7 new task_category enum values; if not present, halt with `PHASE_3_BLOCKED_BY_TASK_CATEGORY_ENUM_INCOMPLETE` activity-log row referencing canonical pre-filed `prod_blockers` id=101 (severity=`high` lowercase, filed 2026-05-08; do NOT autofile a duplicate at runtime per v2.1); on hit-path, idempotent auto-resolve of row 101 per Phase K step 4; this is the only genuine Kim-action point and is mechanically detected, not artificially gated for review); (e) Phase 4 Rule 3b task_category synonym remap (~110 rows) — depends on Phase 3 completion; (f) Phase 5 ATTEMPT — reads `PHASE_5_ENABLED` env var, halts cleanly per spec §3.1 (this session never sets it); (g) Phase 6 final audit (only runs if Phases 1-4 completed) — reconciles snapshot row counts vs post-migration counts, writes final-audit report, releases the §9.4 remote mutex by PATCHing `is_resolved=true`. Author `migrate_schema_vocab_v1.py` from scratch with all phases fully implemented. Mechanical halts only — see §4 below — and the final report surfaces to Kim only if one of those halts fired or to confirm clean completion. Multipass per file edit; dual-canonical absolute-path discipline; activity-log + LD POST via `try_post_or_queue` so Directus offline is tolerated. **Authorization basis:** Cursor's verdict of `AUTHORIZE_PHASE_0_WITH_RISK_ACCEPTANCE` was about spec design soundness ("no v4-level design blocker was found"), not phase-by-phase authorization; spec §3.1 PHASE_5_ENABLED is the only spec-mandated execution gate beyond §6 Gates 1-9; therefore Phases 1-4 + 6 execution is consistent with both Cursor's verdict and the spec. [INFERRED — Cursor's verdict text speaks to design soundness, not phase scope; spec §3.1 PHASE_5_ENABLED gate is the only spec-mandated execution gate beyond §6 Gates 1-9.]

---

## §2 Scope

**Changes in scope (this implementation session — Phases 0, 1, 2, 3, 4, 6):**

1. **Phase A — preflight + HALT gate scan** — verify all 5 entry-level HALT gates MET (existence of spec, Cursor verdict on v3, LD 588 live, Kim's session-level approval, spec §6 Gates 1-9). Document gate state to `prod_activity_log` regardless of outcome.
2. **Phase B — migration script authoring (`migrate_schema_vocab_v1.py`)** — author `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/scripts/migrate_schema_vocab_v1.py` (NEW) with **Phases 0, 1, 2, 3, 4, 6 fully implemented** + **Phase 5 stub gated on `PHASE_5_ENABLED` env var per spec §3.1**. Phase 6 is fully implemented because Phases 1-4 will complete, so the final-audit rollup runs in the same session. Phase 5 stub: reads `PHASE_5_ENABLED`; if unset/false, halts with `PHASE_5_GATED_NO_FLAG` activity-log row + exit 0 (expected path).
3. **Phase C — Step 0 canonical-root resolution** — script asserts cwd resolves under canonical root #1 (Dropbox tree); halts if cwd is in `.claude/worktrees/` or under root #2 unintentionally.
4. **Phase D — Step 0.4 cached canonical-export (v3 NEW)** — generate `Production/exports/prod_locked_decisions_<DATE>.jsonl` + metadata sidecar per spec §4 v3 schema.
5. **Phase E — Step 1 row-restoration snapshot (preserved from v2)** — for every row id any phase plans to touch (union of Phase 1+2+3+4+5 target sets), pull full row body to `Production/docs/SCHEMA_VOCAB_MIGRATION_SNAPSHOT_<YYYYMMDD>.jsonl` + metadata sidecar with `row_count`, `id_uniqueness`, `all_touched_ids_present` invariants.
6. **Phase F — Step 2 dry-run report + drift check (preserved from v2 + NEW drift evaluation)** — emit JSON report at `Production/docs/SCHEMA_VOCAB_MIGRATION_DRY_RUN_<YYYYMMDD>.md` enumerating per-rule row count + sample of 5 ids per rule + computed target value mapping. **NEW:** evaluate drift threshold against spec §4 expected counts (Rule 1=320, Rule 2=37, Rule 3b≈110, Rule 4=29). If any rule's actual count drifts > 25% from expected (v1 heuristic), mechanical halt #2 fires.
7. **Phase G — Step 0.5 rollback rehearsal (v3 NEW)** — 5 deterministically-sampled ids (random.seed(42) per spec); for each: PATCH+revert+verify-snapshot-invariants. Emit `Production/docs/SCHEMA_VOCAB_MIGRATION_ROLLBACK_REHEARSAL_<YYYYMMDD>.md` with pass/fail per row. **Mechanical halt #1 fires if any row fails.**
8. **Phase H — Step 3 activity log marker (preserved from v2)** — POST `SCHEMA_VOCAB_MIGRATION_PHASE_0_COMPLETE` row to `prod_activity_log` via `try_post_or_queue` citing all 4 artifact paths + invariant counts.
9. **Phase I — Phase 1 execution (Rule 4 scope_domain remap, ~29 rows) (NEW)** — acquire §9.4 remote mutex via Directus `prod_blockers` row `SCHEMA_MIGRATION_LOCK_HELD_BY_<HOST>` (severity=CRITICAL); local lockfile flock as defense-in-depth. Per-row: PATCH + read-back per Rule 35 + activity-log row + checkpoint append per §5.0. On any read-back mismatch, mechanical halt #4 fires; snapshot + checkpoint left intact for resume.
10. **Phase J — Phase 2 execution (Rule 2 severity lowercase → UPPER, ~37 rows) (NEW)** — same pattern as Phase I.
11. **Phase K — Phase 3 admin-UI mechanical detection (Rule 3a) (NEW; v2.1)** — script PROBES live Directus schema for the 7 new task_category enum values. If not present, halts with `PHASE_3_BLOCKED_BY_TASK_CATEGORY_ENUM_INCOMPLETE` activity-log row referencing canonical pre-filed `prod_blockers` id=**101** (`SCHEMA_VOCAB_MIGRATION_PHASE_3_TASK_CATEGORY_ENUM_ADD_PENDING_V1`, severity=`high` lowercase, filed 2026-05-08) + exits non-zero so Kim sees it. Does NOT autofile a duplicate row. If present, idempotent auto-resolve of row 101 (PATCH `is_resolved=true` + read-back per Rule 35) and proceeds to Phase L.
12. **Phase L — Phase 4 execution (Rule 3b task_category synonym remap, ~110 rows) (NEW)** — depends on Phase K completion (the 7 enum values must exist). Same PATCH + read-back + checkpoint pattern as Phases I/J.
13. **Phase M — Phase 5 ATTEMPT (gated halt) (NEW)** — reads `PHASE_5_ENABLED` env var. If unset or false, halts with `PHASE_5_GATED_NO_FLAG` activity-log row + exits 0 cleanly (this is the EXPECTED path for this session). The handoff EXPLICITLY does not authorize setting `PHASE_5_ENABLED=true`; that requires a separate handoff + LD `SCHEMA_VOCAB_MIGRATION_PHASE_5_AUTHORIZED_V1` per spec §3.1.
14. **Phase N — Phase 6 final audit (NEW; only runs if Phases 1-4 completed)** — reconciles snapshot row counts vs post-migration counts; writes `Production/docs/SCHEMA_VOCAB_MIGRATION_PHASE_6_REPORT_<DATE>.md`; releases §9.4 remote mutex by PATCHing `is_resolved=true` with resolution_notes citing Phase 6 report path.
15. **Phase O — Final report authoring (per HANDOFF_TEMPLATE_v2 §"Final report")** — author `Production/docs/SCHEMA_MIGRATION_V3_IMPLEMENTATION_REPORT_<YYYYMMDD>.md`. No HALT for Kim review unless one of the four mechanical halts fired.

**Out of scope (do NOT touch in this session):**

- **Phase 5 (Rule 1 severity HIGH/CRITICAL → HARD, ~320 rows)** — self-gated on `PHASE_5_ENABLED` env var per spec §3.1 v2 resolution; this session does NOT set the env var, so Phase 5 mechanically halts at its entry guard with `PHASE_5_GATED_NO_FLAG` activity-log row. Dispatching Phase 5 requires a SEPARATE handoff that sets `PHASE_5_ENABLED=true` + files LD `SCHEMA_VOCAB_MIGRATION_PHASE_5_AUTHORIZED_V1`.
- **lock_decision.py modifications** — already executed Task H (LD 588); do NOT re-edit.
- **prod_locked_decisions schema changes (Rule 3a)** — Phase 3 is Kim's hands in admin UI; the script DETECTS whether the 7 enum values exist (mechanical) but does NOT touch the Directus schema directly. If detection fails, Phase L cannot run; the script exits with a `prod_blockers` row + activity log entry surfaced to Kim.
- **Editing files inside `.claude/worktrees/<name>/`** — DS-27 v2 dual-canonical hard rule.
- **Touching the main RN app CI/CD** (per memory `project_main_app_cicd_greenfield_lock.md`) — schema migration is governance-data, not CI/CD; no overlap. [CONFIRMED — spec §1 non-goals + spec §11 reference index do not list any CI/CD file.]
- **Severity-vocab read-side changes** — `Production/lib/severity_vocab.py` already shipped per LD 586; do NOT re-edit.

---

## §3 Pre-flight (verify before starting Phase A)

### §3.1 Files to read first (anchored citations per HANDOFF_TEMPLATE_v2 anti-pattern #7)

| Anchor target | v2 anchored check |
|---------------|-------------------|
| Spec end-to-end | Read `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v3.md`. Capture line ranges for §0.1 changelog, §4 per-rule action table, §5.0 checkpoint protocol, §5 Phase 0 (Steps 0/0.4/0.5/1/2/3), §5 Phase 5 entry guard, §6 Gates 1-12, §7 risk table, §9.4 remote mutex, §11 reference index. Quote one verbatim sentence from each section to prove the read happened. Preflight HALTs if any section absent. |
| Cursor v3 review verdict | Read `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v3.md`. Anchor: `## Step 3 — After Cursor responds` heading. Capture line range. Confirm verdict block contains `AUTHORIZE_PHASE_0_WITH_RISK_ACCEPTANCE` (or stronger AUTHORIZE_IMPLEMENTATION). |
| HANDOFF_TEMPLATE_v2 structure | Read `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_TEMPLATE_v2.md`. Anchor: `## Required structure` heading. Capture line range. Quote the 7 required sections list verbatim. |
| v2 historical baseline | Read `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v2.md`. Anchor: `## §5 — Migration sequence` heading. Capture line range. Quote one verbatim sentence to prove the v2 Phase 0 Step 1 + Step 2 + Step 3 narrative is preserved as referenced by v3. |
| Cleanup/baseline report | Read `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_CLEANUP_AND_SUPABASE_HARDENING_REPORT_20260508.md`. Anchor: the baseline counts (529 active LDs, mixed vocabulary). Capture line range. Confirm the four canonical rules referenced by spec §3 are present. |
| Severity vocab helper (Part 1) | Read `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/lib/severity_vocab.py`. Anchor: `SEVERITY_RANK` dict definition (the canonical-tolerant map; `HARD == HIGH == 3`). Capture line range. Quote the dict verbatim. Phase F dry-run uses this helper for Rule 1 mapping logic. |
| Directus client + try_post_or_queue | Read `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/lib/directus.py`. Anchor: `try_post_or_queue` function definition + `_validate_json_columns` validator. Capture line range. Confirm the queue path under `pending_directus_writes.json` is honored (Phase H POST relies on this for offline tolerance). |
| lock_decision.py canonical-aware | Read `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/scripts/lock_decision.py`. Anchor: `ACCEPTED_SEVERITY_CHOICES` constant + `canonicalize_severity()` function. Capture line range. Confirm choices list contains `[HARD, SOFT, CRITICAL, HIGH, MEDIUM, LOW, critical, high, medium, low, MED]`. Predecessor Task H. |

### §3.2 Conditions to verify

1. **Cursor v3 verdict captured.** Source: `HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v3.md` final-report block OR `prod_activity_log` row dated 2026-05-08 with `notes` containing `AUTHORIZE_PHASE_0_WITH_RISK_ACCEPTANCE`. Stale verdicts on v1 or v2 fail this check.
2. **LD 588 confirmed live.** Either query `prod_locked_decisions` for `LD_WRITER_CANONICAL_VOCAB_V1` and confirm `status=active` AND `severity=HARD`, OR confirm Kim's chat-message quote stating "LD 588 confirmed live" in this session. [CONFIRMED — Kim verbally confirmed in this session per summary.]
3. **Both canonical roots reachable.**
   - `ls -la "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/scripts/"` (canonical root #1 — primary)
   - `ls -la "/Users/kimberlysmith/Projects/"` (canonical root #2 — exists, no edits needed this session)
   - `ls -la ~/.claude/` (global Claude config — no edits this session)
4. **Directus reachability probe.** Run `curl -s -H "Authorization: Bearer $DIRECTUS_TOKEN" https://directus-production-3460.up.railway.app/server/info` (using Doppler-injected env). If Directus is offline, Phase 0 falls back to deferred-write mode (try_post_or_queue queues to `pending_directus_writes.json`). Phase G rollback rehearsal REQUIRES live Directus — if offline, Phase G HALTs with a `PHASE_0_BLOCKED_BY_DIRECTUS_OFFLINE` activity-log row (queued).
5. **`prod_locked_decisions` reachable for read.** Phase D requires `GET /items/prod_locked_decisions?limit=-1&filter[status][_neq]=superseded`. If the GET fails, Phase D HALTs (cached export cannot be generated).
6. **No prior `SCHEMA_MIGRATION_LOCK_HELD_BY_*` row exists.** Informational query (Phase 0 is non-mutating except rehearsal): GET `prod_blockers` filtered by `title=_starts_with=SCHEMA_MIGRATION_LOCK_HELD_BY_` AND `is_resolved=false`. If a row exists held by another host, surface to Kim before proceeding (rehearsal will conflict with another active migration).
7. **Disk write authorization.** `Production/exports/` and `Production/docs/` MUST be writable. Probe with `touch "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/exports/.preflight_$(date +%s)"` then `rm` the marker.
8. **Git status clean enough.** `git status --short` must NOT show uncommitted edits to `Production/scripts/migrate_schema_vocab_v1.py` (file does not yet exist; clean status confirms no half-written prior attempt). [CONFIRMED — file does NOT exist yet per ls verification at handoff authoring time.]

---

## §4 HALT gates

**Autonomous mode does not bypass HALT gates per DS-26.** If a gate-check fails, HALT and write a "halted, awaiting authorization" report. Do NOT interpret blanket autonomous-mode authorization as override.

Autonomous mode (LD-232) authorizes execution of documented work without per-step confirmation. HALT gates ARE part of the documented work. Skipping a gate is skipping the procedure, not "trusting the autonomous-mode authorization."

**Gate philosophy for this handoff:** there are TWO classes of gate. (a) **Entry-level gates 1-5** — Kim-approval / spec-soundness checks that must be MET before Phase B begins. These are the same as the prior handoff. (b) **Mechanical halts #1-#4** — failures detected during execution that mechanically halt the affected phase + write activity-log evidence + leave snapshot/checkpoint intact for resume. Mechanical halts are NOT artificial Kim-review checkpoints; they are real-failure responses. Spec §6 Gates 10/11/12 are NOT halt-blocking gates in this handoff because (10) is mechanical (rehearsal pass→proceed, fail→spec already mandates HALT — captured as mechanical halt #1), (11) is a rubber-stamp (Kim is single-host; cost of YES near zero — accepted as YES via this handoff), (12) is a rubber-stamp (cost is one append per row, benefit is crash recovery — accepted as YES via this handoff).

### Entry-level gates (must all be MET before Phase B begins)

| # | Gate | Evidence source | Pass criterion | Fail action |
|---|------|------------------|-----------------|-------------|
| 1 | Does the spec exist and match the expected sha256? **(Updated 2026-05-09 v2.5: spec authority is now v8 per LD-611; v7 was prior canonical per LD-598; v3-v6 preserved as historical baselines.)** | `ls -la "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v8.md"` returns size 47,583 bytes (±200) AND `shasum -a 256` returns prefix `c6220e5...` (full: `c6220e519f5b8fb023e163936099f153610ac078d4d3392c6d9f9a454267c052`). Predecessor v7 sha256 prefix `dc7db3e3...` is acceptable as historical reference but v8 is current authority for any new dispatch. | Both checks pass. | Write `HALTED_AWAITING_AUTHORIZATION` row citing this gate; write halt-report to `Production/docs/HALT_AWAITING_AUTHORIZATION_<DATE>.md`; surface to Kim |
| 2 | Has Cursor reviewed v3 and emitted `AUTHORIZE_PHASE_0_WITH_RISK_ACCEPTANCE` (or stronger)? | Final-report block at the bottom of `HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v3.md` (anchor: `## Step 3 — After Cursor responds`) OR a `CURSOR_REVIEW_PASSED_SCHEMA_MIGRATION_V3` row in `prod_activity_log` OR `prod_locked_decisions` notes citing the verdict | At least one such artifact dated >= 2026-05-08 with verdict text containing `AUTHORIZE_PHASE_0_WITH_RISK_ACCEPTANCE` (verdict speaks to design soundness; per §1 Mission, this authorizes Phases 1-4 + 6 because the only spec-mandated execution gate beyond §6 Gates 1-9 is the §3.1 PHASE_5_ENABLED env var) OR `AUTHORIZE_IMPLEMENTATION`. AMEND_V2 / PAUSE_FOR_REDEBATE FAILS this gate. | Write `HALTED_AWAITING_AUTHORIZATION`; halt-report; surface |
| 3 | Is LD 588 `LD_WRITER_CANONICAL_VOCAB_V1` confirmed live (Task H predecessor)? | Directus query `GET /items/prod_locked_decisions?filter[ld_key][_eq]=LD_WRITER_CANONICAL_VOCAB_V1` returns one row with `status=active` AND `severity=HARD` AND `id=588` (or whatever id Kim confirmed) OR Kim's chat quote in this session confirming LD 588 is live. | One artifact present. | Write `HALTED_AWAITING_AUTHORIZATION`; halt-report; surface. (If LD 588 is not live, the implication is `lock_decision.py` is still emitting legacy vocabulary and the cached export may include rows written under the legacy CLI; the migration's invariants would be miscounted.) |
| 4 | Has Kim explicitly approved this implementation handoff in THIS session? | Chat-message quote in current session approving the revised Phases-0-4-+-6 scope OR `prod_locked_decisions` notes for `SCHEMA_VOCAB_MIGRATION_IMPLEMENTATION_AUTHORIZED_V1` OR `prod_activity_log` row `SCHEMA_MIGRATION_IMPLEMENTATION_AUTHORIZED` dated `>= today` | Kim's "yes proceed" captured in this conversation. Blanket prior autonomous-mode authorization is acceptable; mutating Phases 1-4 are run under §9.4 remote mutex + §5.0 checkpoint protocol per spec, with mechanical halts on real failures. | Write `HALTED_AWAITING_AUTHORIZATION` row; halt-report; surface |
| 5 | Are spec §6 Gates 1-9 explicitly approved? | Spec §6 itself OR `prod_locked_decisions` notes citing the gates-approved date OR a `PRE_IMPLEMENTATION_GATES_1_9_APPROVED_SCHEMA_MIGRATION_V3` row in `prod_activity_log` | All 9 gates have explicit Kim-approved evidence (chat quote OR LD note OR activity-log row). Spec §6 Gates 10/11/12 are NOT entry-level for this handoff (see "Gate philosophy" above). | Write `HALTED_AWAITING_AUTHORIZATION`; halt-report; surface |

If ANY entry-level gate fails:
1. Do NOT execute Phase B (script authoring) or beyond.
2. Write the `HALTED_AWAITING_AUTHORIZATION` row to `prod_activity_log` (via `try_post_or_queue`) with `notes` enumerating which gates failed and citing the evidence search performed. Use `details` as a JSON dict (not a string — see §6 hard rules JSON-column gotcha).
3. Author the halt-report doc at `Production/docs/HALT_AWAITING_AUTHORIZATION_<DATE>.md`.
4. Emit the declaration: `HALT gate scan for HANDOFF_SCHEMA_MIGRATION_V3_IMPLEMENTATION_20260508.md: 5 gate(s) detected, <met> met, <not_met> not met. HALTED.` (per DS-26 §6.1 declaration-format tightening).
5. Surface to Kim and stop.

### Mechanical halts (fire DURING execution; not Kim-review checkpoints)

Each mechanical halt: writes an activity-log row with the halt's identifier; leaves the snapshot + checkpoint file intact for resume; exits non-zero so the operator sees a clear failure signal.

- **Mechanical halt #1 — rollback rehearsal failed.** If Phase G (Step 0.5 rollback rehearsal) returns `all_passed=False` for any of the 5 sampled rows, halt immediately. Activity-log row: `PHASE_0_BLOCKED_BY_REHEARSAL_FAIL` (per spec §5 Step 0.5). The migration cannot proceed to Phases 1-4 without rehearsal pass; the rehearsal report at `Production/docs/SCHEMA_VOCAB_MIGRATION_ROLLBACK_REHEARSAL_<YYYYMMDD>.md` lists the failing row + its observed-vs-expected severity/scope_domain/task_category for forensic review.
- **Mechanical halt #2 — drift threshold exceeded.** If Phase F drift check detects any rule's actual row count drifting > 25% from spec §4 expected counts (Rule 1=320, Rule 2=37, Rule 3b≈110, Rule 4=29), halt. Activity-log row: `PHASE_0_BLOCKED_BY_DRIFT`. ALSO autofile a `prod_blockers` row at `severity=HIGH`, `title=SCHEMA_VOCAB_MIGRATION_DRIFT_<DATE>`, `details = {"per_rule_expected_vs_actual": {...}, "threshold_pct": 25}`. (NOTE: 25% is a v1 heuristic; if Kim wants tighter or looser drift tolerance, the threshold is a constant at the top of `migrate_schema_vocab_v1.py` named `DRIFT_THRESHOLD_PCT`.)
- **Mechanical halt #3 — Directus unreachable mid-rehearsal or mid-Phase-1/2/4.** If Directus returns connection error / 5xx / timeout during a PATCH or read-back, halt cleanly. Partial state is recorded via the §5.0 checkpoint protocol; resume algorithm filters target rows to `id > last_committed_row_id`. Activity-log row: `PHASE_<N>_BLOCKED_BY_DIRECTUS_OFFLINE` (queued via `try_post_or_queue`). When Directus returns, re-invoke the same `phase-N` subcommand; resume logic picks up at the last-confirmed row.
- **Mechanical halt #4 — PATCH+read-back verification mismatch.** If any per-row PATCH returns success but the immediate read-back returns a value that doesn't match the target value, halt that phase. Activity-log row: `PHASE_<N>_BLOCKED_BY_PATCH_VERIFY_FAIL` with `details = {"row_id": <id>, "field": "<field>", "target": "<value>", "observed": "<value>"}`. Snapshot + checkpoint stay intact.

**Phase 3 admin-UI detection (also mechanical; v2.1):** Phase K probes the live Directus schema for the 7 new task_category enum values. If absent, the script halts with `PHASE_3_BLOCKED_BY_TASK_CATEGORY_ENUM_INCOMPLETE` activity-log row referencing canonical pre-filed `prod_blockers` id=**101** (`SCHEMA_VOCAB_MIGRATION_PHASE_3_TASK_CATEGORY_ENUM_ADD_PENDING_V1`, severity=`high` lowercase, filed 2026-05-08; do NOT autofile a duplicate at runtime per v2.1) + exits non-zero. This is the ONE genuine Kim-action point (admin UI work cannot be automated), but it is mechanically detected, NOT an artificial Kim-review halt. Once Kim adds the 7 enum values, re-invoke the migration; Phase K probes again, finds them, idempotently auto-resolves row 101, and Phase L runs.

---

## §5 Sequence

### Phase A — Preflight + HALT gate scan

**Deliverable:** Phase 0 declaration line + per-gate state report. No code authored or executed if any gate fails.

**Steps:**
1. Read all 8 anchored citations from §3.1; confirm each anchor resolves to a current-content match.
2. Run all 8 conditions from §3.2; capture verbatim outputs.
3. Run the §4 HALT gate scan; emit the declaration line.
4. If all gates MET, write a `prod_activity_log` row `SCHEMA_MIGRATION_V3_PHASE_0_PREFLIGHT_PASSED` with `details` JSON containing the per-gate evidence captured. Read-back the POST per Rule 35.
5. If any gate fails, halt per §4 fail-action.

**Per-step verification:**
- `details` field MUST be a JSON dict, NOT a string (Directus 500 if string per memory `feedback_directus_schema_canonical.md` JSON columns).
- Every Read tool call captures the line range it inspected (anti-pattern #7 v2 anchored citation).
- Confidence tags: `[CONFIRMED — handoff §3.1 anchors verified mtime + content match]` for each anchor probe.

### Phase B — Migration script authoring (`migrate_schema_vocab_v1.py`)

**Deliverable:** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/scripts/migrate_schema_vocab_v1.py` (NEW), Python 3.11+, executable, with **Phases 0, 1, 2, 3 (mechanical detection), 4, 6 fully implemented** + **Phase 5 stub gated on `PHASE_5_ENABLED` env var per spec §3.1**:

1. Top-of-file docstring citing spec v3 sha256 + handoff path.
2. Imports: `argparse`, `datetime`, `fcntl`, `hashlib`, `json`, `os`, `random`, `socket`, `sys`, `time`, `pathlib.Path`, `Production.lib.directus.DirectusClient` + `try_post_or_queue`, `Production.lib.severity_vocab.SEVERITY_RANK`.
3. Constants:
   - `CANONICAL_ROOT_DROPBOX = "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files"`
   - `SCRIPT_VERSION = "v3-implementation"`
   - `EXPORT_DIR = Path(CANONICAL_ROOT_DROPBOX) / "Production/exports"`
   - `DOCS_DIR = Path(CANONICAL_ROOT_DROPBOX) / "Production/docs"`
   - `DRIFT_THRESHOLD_PCT = 25` (mechanical halt #2 threshold; v1 heuristic)
   - `EXPECTED_ROW_COUNTS = {"rule_1_severity_high_critical_to_hard": 320, "rule_2_severity_lowercase_to_upper": 37, "rule_3b_task_category_remap": 110, "rule_4_scope_domain_remap": 29}` (per spec §4 — drift evaluated against these)
   - `REQUIRED_TASK_CATEGORY_ENUM_VALUES_FOR_PHASE_3 = ["app_architecture", "infrastructure", "security", "governance", "production_tool_ui", "data_model", "visual_production"]` (the 7 new values per spec §3.3 / §5 Phase 3 / LD-601; Phase K detection probes `client.fields("prod_locked_decisions")` for the task_category field's `meta.options.choices` list. **NOTE:** These 7 values match Phase K's `REQUIRED_TASK_CATEGORY_VALUES` exactly — Phase K is authoritative; this list is its mirror in the script's constants block. F3-fix 2026-05-08 corrected an earlier wrong list (`ci_cd`/`schema`/`production`/`tooling`) that did not exist in live schema.)
4. CLI argparse with subcommands: `phase-0`, `phase-1`, `phase-2`, `phase-3`, `phase-4`, `phase-5`, `phase-6`, `all` (runs 0→1→2→3→4→5→6 in dependency order), `dry-run-only`. The `all` subcommand is the canonical entrypoint for this handoff. **Phase 5 includes the `PHASE_5_ENABLED` env-var gate per spec §3.1**: `if os.environ.get("PHASE_5_ENABLED") != "true": post_activity_log("PHASE_5_GATED_NO_FLAG", details={...}); sys.exit(0)`. Phase 5 also requires a verifiable LD `SCHEMA_VOCAB_MIGRATION_PHASE_5_AUTHORIZED_V1` per spec §3.1 Layer 2; if env var is true but LD missing, halts.
5. Phase 0 fully implemented per spec §5 Steps 0/0.4/0.5/1/2/3.
6. Phase 1 (Rule 4 scope_domain remap) fully implemented per spec §5 Phase 1 + §9.4 mutex acquisition + §5.0 per-row checkpoint append.
7. Phase 2 (Rule 2 severity lowercase → UPPER) fully implemented; same pattern as Phase 1.
8. Phase 3 (Rule 3a admin-UI mechanical detection) fully implemented (v2.1): probes live Directus schema; on miss-path halts referencing canonical pre-filed `prod_blockers` id=101 (no autofile); on hit-path idempotently auto-resolves row 101 and proceeds.
9. Phase 4 (Rule 3b task_category synonym remap) fully implemented per spec §5 Phase 4; depends on Phase 3 success.
10. Phase 5 stub gated on `PHASE_5_ENABLED` env var per spec §3.1 (this session does not set the env var).
11. Phase 6 (final audit) fully implemented per spec §5 Phase 6 + §9.4 mutex release.
12. Snapshot-hash computation helper (used by §5.0 checkpoint integrity check).
13. Resume algorithm per spec §5.0 (filters target rows by `id > last_committed_row_id`).
14. Module-level `if __name__ == "__main__": main()` entrypoint.

**Steps:**
1. Author the file end-to-end. Use `Write` tool with the full content. Length budget: ~1500-2000 lines (Phase 0 + 6 mutating phases + 1 final-audit + checkpoint + mutex helpers + resume algorithm).
2. Run `python3 -m py_compile "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/scripts/migrate_schema_vocab_v1.py"` to confirm syntactic validity. HALT if compile fails.
3. Multipass: Re-Read the full file. Confirm every reference matches the canonical-root absolute path + the spec's mandatory schemas.
4. Confidence: `[CONFIRMED — script compiles; spec v3 §5 + §5.0 schemas implemented verbatim per file diff in final report]`.

### Phase C — Step 0 canonical-root resolution (per spec §3.0 + §5 Step 0)

**Deliverable:** Phase 0 entrypoint asserts cwd resolves under canonical root #1; halts if anchored to `.claude/worktrees/` or to root #2 unintentionally.

**Steps:**
1. The script's `phase-0` handler runs `Path.cwd().resolve()` and asserts the path startswith `CANONICAL_ROOT_DROPBOX`. If the path contains `.claude/worktrees/`, it halts with `PHASE_0_BLOCKED_BY_WORKTREE_CONFUSION` activity-log row.
2. The script also checks `git rev-parse --show-toplevel` to confirm the git root matches the canonical root (defense-in-depth against a symlink or alias).
3. If both checks pass, emit `PHASE_0_STEP_0_CANONICAL_ROOT_OK` activity-log row.

**Per-step verification:** test the assertion by temporarily running the script from `.claude/worktrees/gallant-bouman-804b4f/` (a worktree). Confirm it halts with the expected error message. Reset to canonical root and re-run; confirm it proceeds.

### Phase D — Step 0.4 cached canonical-export (v3 NEW per Cursor Task B)

**Deliverable:** Two artifacts in `Production/exports/`:
1. `prod_locked_decisions_<DATE>.jsonl` — every active row in `prod_locked_decisions` (status != superseded), one full JSON object per line.
2. `prod_locked_decisions_<DATE>.metadata.json` — sidecar with `export_version=v3`, `export_taken_at`, `directus_url`, `total_active_rows`, `schema_hash`, `deterministic_sample_method`, `intended_consumer` per spec §4 v3.

**Steps:**
1. Probe Directus reachability: `client = DirectusClient(...); response = client.get("/server/info")`. If unreachable, halt with `PHASE_0_BLOCKED_BY_DIRECTUS_OFFLINE` activity-log row (queue per try_post_or_queue).
2. Pull active rows: `client.get_items("prod_locked_decisions", filters={"status": {"_neq": "superseded"}}, limit=-1)`. Capture row count.
3. Write the JSONL artifact: open in 'w' mode, iterate rows, `f.write(json.dumps(row) + "\n")`. Flush + fsync.
4. Compute `schema_hash`: `client.fields("prod_locked_decisions")` → list field names → `sha256(json.dumps(sorted(names)).hexdigest())`.
5. Write the metadata sidecar with the schema per spec §4 v3.
6. Multipass: re-Read the JSONL artifact. Confirm line count == row count. Pick 3 random lines and verify each parses as valid JSON.
7. Activity log: POST `SCHEMA_MIGRATION_V3_STEP_0_4_CACHED_EXPORT` with `details = {"row_count": N, "export_path": <path>, "schema_hash": <hex>}`.

**Per-step verification:**
- Date format: `YYYYMMDD` UTC (matches existing `Production/exports/prod_locked_decisions_2026-05-08.jsonl` which already exists from earlier this session — note the dash-separated form; new export uses contiguous form for v3 pattern). Coordinate with the v3 reviewer's expected file name; if existing dated export is the canonical, use that path naming.
- Memory probe: an existing 570-row 1,124,003-byte cached export at `Production/exports/prod_locked_decisions_2026-05-08.jsonl` (sha256 4ac319c4...) was generated earlier this session; this Phase D may detect it exists and either RE-USE it (preferred — preserves Cursor's review trail) or supersede it with a fresh export. **Decision rule:** if the existing export's `total_active_rows` matches the live count and the schema_hash matches the live schema, RE-USE; otherwise SUPERSEDE and document both paths in the metadata sidecar.
- `[CONFIRMED — file exists per ls preflight; row count + schema_hash MUST be verified live before re-use decision]`

### Phase E — Step 1 row-restoration snapshot (preserved verbatim from v2)

**Deliverable:** Two artifacts:
1. `Production/docs/SCHEMA_VOCAB_MIGRATION_SNAPSHOT_<YYYYMMDD>.jsonl` — for every row id any phase plans to touch, full row body, one JSON object per line.
2. `Production/docs/SCHEMA_VOCAB_MIGRATION_SNAPSHOT_<YYYYMMDD>.metadata.json` — sidecar with `row_count`, `id_uniqueness` (boolean), `all_touched_ids_present` (boolean), per-rule target id list, `snapshot_hash` (used by §5.0 checkpoint protocol).

**Steps:**
1. Compute the union of touched-ids:
   - Rule 1 targets: rows with `severity IN ('HIGH','CRITICAL','high','critical')` (Phase 5 maps to HARD).
   - Rule 2 targets: rows with `severity IN ('low','medium','high','critical','med')` (Phase 2 case-folds).
   - Rule 3b targets: rows with `task_category` in the synonym-remap list (per spec §3.3).
   - Rule 4 targets: rows with `scope_domain` in the remap list (per spec §3.4).
2. Pull each touched row's full body via `client.get_item("prod_locked_decisions", id)`.
3. Write the JSONL.
4. Compute invariants:
   - `row_count` = len(touched_rows)
   - `id_uniqueness` = (len(set(ids)) == len(ids))
   - `all_touched_ids_present` = every targeted id appears exactly once in the JSONL
   - `snapshot_hash` = `sha256(json.dumps(metadata, sort_keys=True).encode()).hexdigest()`
5. Write metadata sidecar.
6. Multipass: Re-Read JSONL; verify line count matches.
7. Activity log: POST `SCHEMA_MIGRATION_V3_STEP_1_SNAPSHOT_COMPLETE` with `details` JSON containing all invariants.

**Per-step verification:** if `row_count != expected (per Rule 1+2+3b+4 union estimate from spec §4)`, surface to Kim — drift between spec authoring (v3 = 2026-05-08) and execution time may indicate new rows landed via `lock_decision.py` post-LD-588.

### Phase F — Step 2 dry-run report + drift check (preserved from v2 + NEW drift halt)

**Deliverable:** `Production/docs/SCHEMA_VOCAB_MIGRATION_DRY_RUN_<YYYYMMDD>.md` enumerating per-rule planned PATCHes with computed target values + drift evaluation. NO PATCHes issued.

**Steps:**
1. For each of Rules 1, 2, 3a, 3b, 4: compute target value per row using the spec §3 mapping rules. For Rule 1, use `SEVERITY_RANK` from `severity_vocab.py` to confirm HARD == HIGH == 3 invariant before mapping.
2. Render the report markdown:
   - Per-rule row count (matches snapshot row_count for that rule).
   - Sample of 5 random ids per rule with verbatim before/after values.
   - Computed invariant deltas (none, since dry-run).
   - Drift check section: actual vs `EXPECTED_ROW_COUNTS` per spec §4; per-rule absolute delta + percentage delta.
3. **Drift evaluation (mechanical halt #2):** for each rule, compute `pct_drift = abs(actual - expected) / expected * 100`. If any rule's `pct_drift > DRIFT_THRESHOLD_PCT (25)`, mechanical halt #2 fires:
   - POST activity-log `PHASE_0_BLOCKED_BY_DRIFT` with `details = {"per_rule_expected_vs_actual": {...}, "threshold_pct": 25, "violating_rules": [...]}`.
   - Autofile a `prod_blockers` row at `severity=HIGH`, `title=SCHEMA_VOCAB_MIGRATION_DRIFT_<DATE>`, `details = {"per_rule_expected_vs_actual": {...}, "threshold_pct": 25}`, `is_resolved=false`.
   - Exit non-zero. Snapshot + cached export remain intact for forensic review.
4. If no drift halt fires, activity log: POST `SCHEMA_MIGRATION_V3_STEP_2_DRY_RUN_COMPLETE` with `details` JSON containing per-rule counts + drift percentages.

**Per-step verification:** every "before" value MUST appear in the snapshot JSONL; every "after" value MUST be a canonical-vocab value (per `SEVERITY_RANK` + spec §3 mapping tables). Reject the dry-run if any after-value is non-canonical. Drift threshold 25% is a v1 heuristic captured in `DRIFT_THRESHOLD_PCT` constant; future tuning is one-line edit.

### Phase G — Step 0.5 rollback rehearsal (v3 NEW per Cursor Task D)

**Deliverable:** `Production/docs/SCHEMA_VOCAB_MIGRATION_ROLLBACK_REHEARSAL_<YYYYMMDD>.md` with per-row pass/fail report on 5 deterministically-sampled ids.

**Steps:**
1. `random.seed(42)` (deterministic per spec §5 Step 0.5 — two reviewers reach same sample).
2. Pull union of touched-ids from snapshot JSONL.
3. `sampled_ids = random.sample(touched_ids, min(5, len(touched_ids)))`.
4. For each sampled id:
   a. `pre = client.get_item("prod_locked_decisions", sid)`.
   b. Compute `target_value` per the row's applicable rule (Rule 1 if severity is HIGH/CRITICAL; else Rule 2 if lowercase severity; else Rule 3b/4 per task_category/scope_domain).
   c. PATCH the row to `target_value`.
   d. Read-back: `intermediate = client.get_item(...)`. Assert `intermediate[<field>] == target_value`.
   e. Revert: PATCH back to `pre[<field>]`.
   f. Read-back: `post = client.get_item(...)`. Assert `post[<field>] == pre[<field>]`.
   g. Append result dict to `rehearsal_results`.
5. `all_passed = all(r["passed"] for r in rehearsal_results)`.
6. Write the report markdown with sampled ids, per-row results, and `All passed: True/False`.
7. **HALT if not all_passed (mechanical halt #1).** Activity log: POST `PHASE_0_BLOCKED_BY_REHEARSAL_FAIL` (per spec §5 Step 0.5; same semantics as spec's `PHASE_5_BLOCKED_BY_ROLLBACK_REHEARSAL` but pre-Phase-5 since this handoff blocks Phase 1+ on rehearsal pass) with `details = {"sampled_ids": [...], "rehearsal_results": [...], "all_passed": false}`. Exit non-zero. Snapshot + cached export remain intact for forensic review.
8. If all_passed: activity log POST `SCHEMA_MIGRATION_V3_STEP_0_5_REHEARSAL_PASSED` with `details = {"sampled_ids": [...], "all_passed": true, "report_path": <path>}`.

**Per-step verification:**
- Read-back per Rule 35 on EVERY PATCH — both the PATCH-to-target and the revert-to-pre.
- The rehearsal IS the only mutating action in Phase 0; net effect on data is ZERO (every PATCH is reverted within the same loop iteration).
- If Directus offline mid-rehearsal, halt — partial rehearsal leaves some rows mutated. Cleanup: re-run rehearsal once Directus is back; the deterministic seed means same ids will be sampled.
- Confidence: `[CONFIRMED — every row's pre/intermediate/post severities/scope_domains/task_categories captured verbatim in report]`.

### Phase H — Step 3 activity log marker

**Deliverable:** `prod_activity_log` row `SCHEMA_VOCAB_MIGRATION_PHASE_0_COMPLETE` (per spec §5 Step 3) citing all 4 artifact paths + invariant counts.

**Steps:**
1. Aggregate Phase 0 outputs:
   - Cached export path + row count + schema_hash (from Phase D).
   - Snapshot path + invariants (from Phase E).
   - Dry-run report path + per-rule counts (from Phase F).
   - Rehearsal report path + all_passed (from Phase G).
2. POST via `try_post_or_queue` with `details` JSON dict containing all the above.
3. Read-back per Rule 35.

**Per-step verification:** the row's `details` field MUST be a JSON dict (not a string — JSON-column gotcha). The row's `action` field SHOULD be `SCHEMA_VOCAB_MIGRATION_PHASE_0_COMPLETE` matching the spec. Capture the row id for the final report.

### Phase I — Phase 1 execution: Rule 4 scope_domain remap (~29 rows) (NEW)

**Deliverable:** ~29 rows in `prod_locked_decisions` with `scope_domain` remapped to canonical values per spec §3.4. One activity-log row per PATCH. Checkpoint file appended per row. §9.4 remote mutex held throughout.

**Dependencies:** Phase H (Phase 0 complete activity-log marker) must have written. Mechanical halts #1, #2 must NOT have fired.

**Steps:**
1. **Remote-mutex acquisition (§9.4):** query `prod_blockers` filtered by `is_resolved=false` AND `title=_starts_with=SCHEMA_MIGRATION_LOCK_HELD_BY_`. If any row exists with title != `SCHEMA_MIGRATION_LOCK_HELD_BY_<HOST>` (current host), halt with `PHASE_1_BLOCKED_BY_MUTEX_CONTENTION` (mechanical halt #3 family). Otherwise POST a new row titled `SCHEMA_MIGRATION_LOCK_HELD_BY_<HOST>`, `severity=CRITICAL`, `is_resolved=false`, `details={"phase":"in-progress","host":"<host>","pid":<pid>}`. Capture mutex_blocker_id.
2. **Local lockfile (defense-in-depth):** flock `~/.claude/mindfulnest-cache/schema_vocab_migration.lock` with `LOCK_EX | LOCK_NB`. If contention, halt with `PHASE_1_BLOCKED_BY_LOCAL_LOCK_CONTENTION`.
3. **Resume init (§5.0):** read `Production/exports/schema_migration_checkpoint_<DATE>.jsonl` (initialize empty if absent). Compute resume `last_committed_row_id` (default -1). Compute current `snapshot_hash`; verify against checkpoint's `snapshot_hash` (if checkpoint has prior phase entries). On hash mismatch, halt with `PHASE_1_BLOCKED_BY_SNAPSHOT_DRIFT`.
4. **Per-row PATCH loop (resumable):** for each row in Rule 4 target set with `id > last_committed_row_id`:
   a. `pre = client.get_item("prod_locked_decisions", id)`. Capture pre-`scope_domain`.
   b. Compute target per spec §3.4 mapping table.
   c. PATCH `{"scope_domain": <target>}` via `try_post_or_queue`.
   d. If Directus returns 5xx / connection error / timeout → mechanical halt #3 (`PHASE_1_BLOCKED_BY_DIRECTUS_OFFLINE`); checkpoint left at last successful row.
   e. **Read-back per Rule 35:** `post = client.get_item(...)`. If `post["scope_domain"] != target` → mechanical halt #4 (`PHASE_1_BLOCKED_BY_PATCH_VERIFY_FAIL` with row_id, expected, observed in details).
   f. POST `migration_audit` activity-log row: `action=SCHEMA_VOCAB_MIGRATION_PHASE_1_PATCH`, `details = {"row_id": id, "field": "scope_domain", "pre": <pre>, "post": <target>, "rule": "rule_4_scope_domain_remap"}`.
   g. **Append checkpoint line (§5.0):** `{"phase":1,"rule":"scope_domain_remap","last_committed_row_id":id,"timestamp":"<iso>","snapshot_hash":"<hex>","rows_processed_in_phase":N,"expected_rows_in_phase":29}`. Open in append mode + flush + fsync before next row.
5. After loop: write `Production/docs/SCHEMA_VOCAB_MIGRATION_PHASE_1_REPORT_<DATE>.md` summarizing rows touched + sample 5 before/after pairs + total elapsed time.
6. Activity log: POST `SCHEMA_MIGRATION_V3_PHASE_1_COMPLETE` with `details = {"rows_patched": N, "expected": 29, "report_path": <path>}`.

**Per-step verification:**
- Read-back per Rule 35 on EVERY PATCH.
- Checkpoint append MUST be flushed + fsync'd before next row begins.
- If `rows_patched != 29` (allowing for spec drift up to 25% per §F drift check), surface but proceed; the discrepancy is captured in the activity-log row.

### Phase J — Phase 2 execution: Rule 2 severity lowercase → UPPER (~37 rows) (NEW)

**Deliverable:** ~37 rows with `severity` case-folded to UPPER per spec §3.2. Same pattern as Phase I.

**Dependencies:** Phase I complete. Remote mutex still held (single mutex spans Phases 1-4).

**Steps:** identical pattern to Phase I, with these differences:
- Target set: rows with `severity IN ('low', 'medium', 'high', 'critical', 'med')`.
- Target value: `severity.upper()` (with `med` → `MEDIUM` per spec §3.2 expansion).
- Activity-log action: `SCHEMA_VOCAB_MIGRATION_PHASE_2_PATCH`; rule descriptor: `severity_lower_to_upper`.
- Checkpoint phase=2; expected_rows_in_phase=37.
- Mechanical halts #3 + #4 same family; halt names `PHASE_2_BLOCKED_BY_*`.
- Final report: `Production/docs/SCHEMA_VOCAB_MIGRATION_PHASE_2_REPORT_<DATE>.md`.
- Completion activity-log: `SCHEMA_MIGRATION_V3_PHASE_2_COMPLETE`.

### Phase K — Phase 3 admin-UI mechanical detection (Rule 3a) (NEW; v2.1 references prod_blockers id=101)

**Deliverable:** verdict on whether the 7 new task_category enum values exist in live Directus schema. NO row mutations on miss-path (the canonical `prod_blockers` row already exists at id=101). On hit-path, idempotent auto-resolve of row 101.

**Dependencies:** Phase J complete. Remote mutex still held. Canonical pre-filed row: `prod_blockers` id=**101** title `SCHEMA_VOCAB_MIGRATION_PHASE_3_TASK_CATEGORY_ENUM_ADD_PENDING_V1` (filed 2026-05-08; severity=`high` lowercase; is_resolved=false at handoff authoring time). [CONFIRMED via DirectusAdminClient.get_item probe in Wave A]

**Canonical row reference (do NOT autofile a duplicate at runtime):**
- `PHASE_3_BLOCKER_ID = 101`
- title: `SCHEMA_VOCAB_MIGRATION_PHASE_3_TASK_CATEGORY_ENUM_ADD_PENDING_V1`
- severity: `high` (lowercase per live schema; see §6 prod_blockers schema gotchas)
- The structured payload (7 values, kim action steps, anchors) lives inside the `description` field as a text-embedded JSON block keyed `STRUCTURED_DETAILS_JSON:` because `prod_blockers` has NO `details` JSON column.

**Required enum values (constant in script):**
```
REQUIRED_TASK_CATEGORY_VALUES = {
    "app_architecture", "infrastructure", "security", "governance",
    "production_tool_ui", "data_model", "visual_production",
}
```

**Steps:**
1. Pull live schema for `prod_locked_decisions.task_category`: `client.fields("prod_locked_decisions")` → locate the `task_category` field entry → read `meta.options.choices` (each choice has `value` + `text`). Build `choices = {c["value"] for c in ...}`.
2. Compute `missing = REQUIRED_TASK_CATEGORY_VALUES - choices` and `present = REQUIRED_TASK_CATEGORY_VALUES & choices`.
3. **If `missing` is non-empty (mechanical halt — Phase 3 admin-UI not done):**
   a. **Do NOT autofile a fresh `prod_blockers` row.** Row 101 already exists. Read it back via `client.get_item("prod_blockers", PHASE_3_BLOCKER_ID)` and surface its current state (title, severity, is_resolved) to stderr along with `sorted(missing)`.
   b. POST activity-log `PHASE_3_BLOCKED_BY_TASK_CATEGORY_ENUM_INCOMPLETE` via `try_post_or_queue("prod_activity_log", {...})` with `details` as a **dict** (not JSON string) listing `prod_blockers_id=101`, `missing_enum_values=sorted(missing)`, `present_enum_values=sorted(present)`.
   c. Release the remote mutex (Phase L cannot run; cleanup mutex so other workflows aren't blocked). PATCH the mutex blocker row with `is_resolved=true`, `resolution_notes="Released at Phase 3 detection halt; re-acquire on resume."` Local lockfile released.
   d. `sys.exit(2)` so Kim sees the failure clearly.
4. **If `missing` is empty (all 7 present — hit path):**
   a. Read `prod_blockers` id=101 via `client.get_item(...)`. If `is_resolved` is already `true`, skip the PATCH (idempotent re-run).
   b. Else: PATCH row 101 with `{"is_resolved": True, "resolved_at": datetime.now(timezone.utc).isoformat()}`. Read-back per Rule 35 (`assert after["is_resolved"] is True`).
   c. POST activity-log `PHASE_3_PASSED_TASK_CATEGORY_ENUM_VERIFIED` via `try_post_or_queue` with `details` as dict containing `prod_blockers_id=101`, `verified_enum_values=sorted(REQUIRED_TASK_CATEGORY_VALUES)`, `auto_resolved=<bool — True if PATCHed this run, False if already resolved>`.
   d. Proceed to Phase L.

**Canonical pseudocode (encode in `migrate_schema_vocab_v1.py`):**
```python
PHASE_3_BLOCKER_ID = 101  # SCHEMA_VOCAB_MIGRATION_PHASE_3_TASK_CATEGORY_ENUM_ADD_PENDING_V1
REQUIRED_TASK_CATEGORY_VALUES = {
    "app_architecture", "infrastructure", "security", "governance",
    "production_tool_ui", "data_model", "visual_production",
}

field_meta = client.fields("prod_locked_decisions")
task_category_field = next(f for f in field_meta if f["field"] == "task_category")
choices = {c["value"] for c in task_category_field.get("meta", {}).get("options", {}).get("choices", [])}

missing = REQUIRED_TASK_CATEGORY_VALUES - choices
present = REQUIRED_TASK_CATEGORY_VALUES & choices

if missing:
    blocker = client.get_item("prod_blockers", PHASE_3_BLOCKER_ID)
    sys.stderr.write(
        f"PHASE_3_BLOCKED: existing prod_blockers id={PHASE_3_BLOCKER_ID} "
        f"(title={blocker['title']}, severity={blocker['severity']}, "
        f"is_resolved={blocker['is_resolved']}). Missing enum values: {sorted(missing)}\n"
    )
    try_post_or_queue("prod_activity_log", {
        "action": "PHASE_3_BLOCKED_BY_TASK_CATEGORY_ENUM_INCOMPLETE",
        "details": {  # dict (not string) per JSON-column gotcha
            "prod_blockers_id": PHASE_3_BLOCKER_ID,
            "missing_enum_values": sorted(missing),
            "present_enum_values": sorted(present),
        },
    })
    # release remote mutex here per step 3c
    sys.exit(2)

# Hit path — idempotent auto-resolve
blocker = client.get_item("prod_blockers", PHASE_3_BLOCKER_ID)
auto_resolved_this_run = False
if not blocker["is_resolved"]:
    client.patch_item("prod_blockers", PHASE_3_BLOCKER_ID, {
        "is_resolved": True,
        "resolved_at": datetime.now(timezone.utc).isoformat(),
    })
    after = client.get_item("prod_blockers", PHASE_3_BLOCKER_ID)
    assert after["is_resolved"] is True  # Rule 35 read-back
    auto_resolved_this_run = True

try_post_or_queue("prod_activity_log", {
    "action": "PHASE_3_PASSED_TASK_CATEGORY_ENUM_VERIFIED",
    "details": {  # dict
        "prod_blockers_id": PHASE_3_BLOCKER_ID,
        "verified_enum_values": sorted(REQUIRED_TASK_CATEGORY_VALUES),
        "auto_resolved": auto_resolved_this_run,
    },
})
# proceed to Phase L
```

**Per-step verification:** the 7 names are encoded as a single constant (`REQUIRED_TASK_CATEGORY_VALUES`) for easy adjustment if spec §3.3 vocabulary evolves. Detection probes the LIVE schema (not the cached export) because the cached export captures rows, not schema enum lists. The PATCH to row 101 is idempotent (skip if already resolved) so re-runs after the admin-UI fix don't double-resolve. Per §6 prod_blockers schema gotchas: severity stays lowercase on any PATCH; `details` is NOT a column on prod_blockers — payload remains in `description` text field.

### Phase L — Phase 4 execution: Rule 3b task_category synonym remap (~110 rows) (NEW)

**Deliverable:** ~110 rows with `task_category` remapped to canonical values per spec §3.3.

**Dependencies:** Phase K passed (the 7 enum values are present). Remote mutex still held.

**Steps:** identical pattern to Phase I/J, with these differences:
- Target set: rows with `task_category` in the synonym-remap table per spec §3.3.
- Target value: synonym-remap mapping per spec §3.3.
- Activity-log action: `SCHEMA_VOCAB_MIGRATION_PHASE_4_PATCH`; rule descriptor: `task_category_remap`.
- Checkpoint phase=4; expected_rows_in_phase=110.
- Mechanical halts #3 + #4 same family; halt names `PHASE_4_BLOCKED_BY_*`.
- Final report: `Production/docs/SCHEMA_VOCAB_MIGRATION_PHASE_4_REPORT_<DATE>.md`.
- Completion activity-log: `SCHEMA_MIGRATION_V3_PHASE_4_COMPLETE`.

### Phase M — Phase 5 ATTEMPT (gated halt; expected path = clean exit) (NEW)

**Deliverable:** activity-log row confirming Phase 5 was attempted but halted on the `PHASE_5_ENABLED` env-var gate per spec §3.1. Exit code 0 (this is the EXPECTED path; Phase 5 is deliberately deferred).

**Dependencies:** Phase L complete.

**Steps:**
1. Read `os.environ.get("PHASE_5_ENABLED")`. This handoff's session does NOT set it.
2. **If unset OR != "true":** POST activity-log `PHASE_5_GATED_NO_FLAG` with `details = {"reason": "PHASE_5_ENABLED env var not set to true; Phase 5 deferred per spec §3.1", "expected": true, "next_step": "Set PHASE_5_ENABLED=true and file LD SCHEMA_VOCAB_MIGRATION_PHASE_5_AUTHORIZED_V1 to dispatch Phase 5"}`. Exit 0 cleanly. Continue to Phase N (final audit may still proceed for Phases 1-4).
3. **If `PHASE_5_ENABLED=true`** (this session does NOT trigger this path; documented for completeness): verify spec §3.1 Layer 2 — query `prod_locked_decisions` for `ld_key=SCHEMA_VOCAB_MIGRATION_PHASE_5_AUTHORIZED_V1` AND `status=active` AND notes contain "Kim approved". If LD missing, halt with `PHASE_5_BLOCKED_NO_LD` activity-log + exit non-zero. If LD present, run Phase 5 PATCH loop per spec §5 Phase 5 (320 rows; Rule 1 severity HIGH/CRITICAL → HARD). **THIS HANDOFF DOES NOT AUTHORIZE THIS PATH.**

**Per-step verification:** the env-var check is the ONLY gate for the expected path; spec §3.1 mandates this is the canonical Phase 5 deferral mechanism.

### Phase N — Phase 6 final audit + §9.4 mutex release (NEW)

**Deliverable:** `Production/docs/SCHEMA_VOCAB_MIGRATION_PHASE_6_REPORT_<DATE>.md` reconciling pre/post row counts; remote mutex released by PATCHing `is_resolved=true`.

**Dependencies:** Phases I, J, K (passed), L completed. Phase M halted cleanly on env-var gate (expected) OR ran successfully (not expected this session).

**Steps:**
1. Pull post-migration row counts for each touched rule (re-query with filters identical to Phase 0 Phase E).
2. Reconcile against snapshot's `row_count` per rule. For Rules 1, 2, 4, 3b: rows that were in snapshot's per-rule target set should now have canonical values.
3. **Phase 5 carve-out:** since Phase 5 (Rule 1) did NOT execute this session, the 320 rows targeted by Rule 1 retain their pre-migration values (HIGH / CRITICAL / etc.). Phase 6 audit explicitly records this carve-out: `phase_5_deferred=true; rule_1_rows_unchanged=<count>`.
4. Compute final invariants: total rows in `prod_locked_decisions` post-migration = total rows pre-migration (no auto-creation, no deletion) per spec §1 goal #4.
5. Write the report markdown:
   - Per-rule pre/post counts.
   - Rule 1 deferral record.
   - Sample of 5 random ids per executed rule with verbatim before/after.
   - Total session elapsed time.
   - Mutex acquisition/release timestamps.
6. **Mutex release (§9.4):** PATCH `prod_blockers/<mutex_blocker_id>` with `{"is_resolved": true, "resolution_notes": f"Schema migration v3 Phases 1-4 + 6 complete (Phase 5 deferred on PHASE_5_ENABLED gate per spec §3.1); audit at <phase_6_report_path>"}`. Read-back per Rule 35.
7. **Local lockfile released:** `fcntl.flock(fd, LOCK_UN); os.unlink(local_lock_path)`.
8. Activity log: POST `SCHEMA_MIGRATION_V3_PHASE_6_COMPLETE` with `details = {"phase_5_deferred": true, "rules_executed": [1,2,3,4], "report_path": <path>, "mutex_released": true}`.

**Per-step verification:** Phase 6 only runs if at least Phase L completed; if Phase K halted on admin-UI detection, Phase 6 still runs to RELEASE the mutex (Phase K does this itself, but Phase N is the canonical release point on the success path).

### Phase O — Final report authoring (per HANDOFF_TEMPLATE_v2)

**Deliverable:** `Production/docs/SCHEMA_MIGRATION_V3_IMPLEMENTATION_REPORT_<YYYYMMDD>.md` per HANDOFF_TEMPLATE_v2 §"Final report" structure.

**Steps:**
1. Author the report with the 9 required sections (HALT gate scan results / per-phase diff / per-phase audit-checklist / Directus writes with read-back proofs / activity log rows verbatim / confidence tags / self-classification / limitations / cross-skill drift).
2. The "HALT gate scan results" section reports MET on Gates 1-5 (entry-level) AND lists which (if any) of mechanical halts #1-#4 fired during execution. If none fired, the report records "Phases 0-4 + 6 complete; Phase 5 self-gated cleanly per spec §3.1". If a mechanical halt fired, the report is a halt-report and surfaces the failure to Kim.
3. **NO HALT for Kim review unless a mechanical halt fired.** Phase O completes the session; clean termination if nothing went wrong.

**Per-step verification:**
- The final report's "Limitations" section MUST list: Phase 5 deferred on `PHASE_5_ENABLED` env var (expected); whichever of mechanical halts #1-#4 fired (if any) is the limitation; if Phase K detected admin-UI gap, that is the limitation + the canonical pre-filed `prod_blockers` row id=101 is the resolution path (no duplicate autofiled per v2.1).
- The "Cross-skill drift" section MUST note any updates needed to mn-context, dashboard-gate, the schema reference doc (potentially updates to reflect v3 cached-export pattern in `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md`).

---

## §6 Hard rules

- **Per Rule 35:** read-back-after-write for every Directus PATCH/POST (including every PATCH and every revert in Phase G).
- **Multipass:** re-Read every file after edit (script body, sidecar metadata, dry-run report, rehearsal report, final report).
- **Rule 24:** confidence tags throughout (CONFIRMED / INFERRED / GUESSED). Every "I think this works" claim is GUESSED until verified; every state assertion needs same-turn evidence.
- **DS-19** (Standing Escape Hatches) and **DS-26** (Gate-Check Discipline) always active — fire on any of their trigger conditions.
- **DS-13 Layer 6:** end-to-end smoke test for every new behavior. The migration script's Phase 0 is the smoke test; vary input (no-op vs cached-export already exists) → output changes meaningfully (re-use vs supersede decision logged).
- **DS-26 explicit:** "Autonomous mode does not bypass HALT gates. If a HALT gate fires mid-execution (e.g., Phase G rehearsal fails on row 3 of 5), STOP and surface."
- **DS-27 explicit (v2 dual-canonical):** "All filesystem-touching commands MUST use absolute paths anchored to one of the two canonical roots: (1) `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/` (primary — Mindfulnest project) OR (2) `/Users/kimberlysmith/Projects/` (secondary — tooling repos, MindfulNest RN app, related repos). Do NOT operate inside `.claude/worktrees/` subdirectories under either root unless explicitly authorized. Verify paths with `ls -la <absolute-path>` before edits. Paths outside both canonical roots require explicit Kim authorization."
- **Companion path discipline (HANDOFF_TEMPLATE_v2 §0.3):** every companion file in §11 of this handoff has its absolute path AND canonical-root tag.
- **Anchored citation:** every preflight evidence requirement in §3.1 uses anchored section/header + snippet match, not absolute line number alone.
- **Concise→full escalation:** N/A — this is an implementation handoff, not a review handoff. Documented as N/A per HANDOFF_TEMPLATE_v2 §"Concise→full escalation rule".
- **Numeric AMEND_V2 thresholds:** N/A — this is an implementation handoff, no AUTHORIZE/AMEND verdict semantics. Documented as N/A.
- **DS-28 dependency-order discipline:** the implementation graph is Phase A → B → C → D → E → F (drift check) → G (rehearsal) → H (Phase 0 marker) → I (Phase 1 Rule 4) → J (Phase 2 Rule 2) → K (Phase 3 detection — Kim's hands if missing) → L (Phase 4 Rule 3b) → M (Phase 5 gated halt) → N (Phase 6 audit + mutex release) → O (final report). Order matters: cached export (D) precedes snapshot (E) per spec §4 v3; snapshot (E) precedes dry-run (F); dry-run (F) precedes rehearsal (G); rehearsal (G) precedes Phase 0 marker (H); Phase 0 marker precedes mutating Phases I/J/K/L; Phase 3 detection (K) precedes Rule 3b execution (L) per spec dependency table; mutating phases (I/J/L) precede Phase 5 gate (M) per spec §5 sequence; Phase 5 gate precedes Phase 6 audit (N) which RELEASES the mutex; Phase 6 precedes final report (O).
- **JSON-column gotcha:** `prod_activity_log.details` and `prod_blockers.details` are JSON columns — string payloads return HTTP 500. Validator in `Production/lib/directus.py::_validate_json_columns` enforces dict-type. Every POST in Phases C, D, E, F, G, H, I, J, K, L, M, N, O MUST pass `details` as a dict, not a JSON string.
- **try_post_or_queue tolerance:** every Directus POST/PATCH (including read-backs) goes through `try_post_or_queue`. If Directus is offline, writes queue to `pending_directus_writes.json`; replay later via `replay_pending_writes.py`. EXCEPTION: Phase G rollback rehearsal AND Phases I/J/L mutating PATCH loops REQUIRE live Directus — if Directus goes offline mid-execution, mechanical halt #3 fires; resume via re-invoking the same `phase-N` subcommand once Directus is back; §5.0 checkpoint protocol filters target rows to `id > last_committed_row_id`.
- **No Phase 5 attempt without `PHASE_5_ENABLED=true` env var.** The script's Phase M handler reads `PHASE_5_ENABLED`; if unset/false, halts cleanly with `PHASE_5_GATED_NO_FLAG` activity-log row + exit 0. This handoff EXPLICITLY does not authorize setting that env var; Phase 5 dispatch requires a SEPARATE handoff that sets the env var + files LD `SCHEMA_VOCAB_MIGRATION_PHASE_5_AUTHORIZED_V1` per spec §3.1. Phases 1-4 + 6 execute autonomously after Phase 0 if rehearsal passes; mechanical halts #1-#4 are the only halt-blocking conditions during execution.
- **No git commits.** This session writes files but does NOT commit. Kim reviews artifacts + final report after Phase O. The autofiled `prod_blockers` rows (drift halt; remote mutex while held) are non-commit Directus rows. Note: the Phase 3 admin-UI detection halt does NOT autofile a fresh row — it references existing canonical row id=101 per Phase K v2.1.

### prod_blockers schema gotchas (added v2.1)

These three findings emerged from Wave A schema discovery on 2026-05-08; surfacing here so future authors don't re-discover or mis-code:

- **No `details` JSON column.** `prod_blockers` has only 8 fields: `id`, `module_id`, `severity`, `title`, `description`, `is_resolved`, `created_at`, `resolved_at`. Any structured payload MUST live inside `description` as a text-embedded JSON block keyed `STRUCTURED_DETAILS_JSON:` (the convention used by row 101). Do NOT try to POST a `details` key to `prod_blockers` — Directus will reject it. (Source: Wave A schema probe via `DirectusAdminClient.fields("prod_blockers")`.)
- **Severity is lowercase.** `prod_blockers.severity` enum is `high` / `critical` / `medium` / `low` (lowercase) — opposite of `prod_locked_decisions.severity` which is `HARD` / `HIGH` / `MEDIUM` / `SOFT` (uppercase). Mixing the two collections' severity casings is a common mistake. Always check which collection you're writing to before picking case. (Source: Wave A live row probe of id=101: `severity: "high"`.)
- **Mutex collision risk for spec v3 §9.4.** Spec v3 §9.4 mandates `severity=CRITICAL` for the `SCHEMA_MIGRATION_LOCK_HELD_BY_<HOST>` mutex row, but live `prod_blockers.severity` enum uses lowercase `critical`. Migration script's mutex POST MUST case-fold (`severity="critical"` not `"CRITICAL"`) or the POST returns HTTP 500. Treat this as a known spec-vs-live divergence; spec reconciliation landed: v4 §9.4 (LD-593 `SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V4_MUTEX_CASEFOLD_V1`) corrected the severity case-fold; v5 §9.4 (LD-595 `SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V5_FIELD_NAME_FIX_V1`) corrected the field-name defects (`details` → `description` text-embedded JSON; `resolution_notes` removed, replaced with append-to-`description` on release PATCH); v6 §9.4 (LD-596 `SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V6_AMEND_V2_FIXES_V1`, Cursor AMEND_V2 hardening — guarded JSON parse with `extract_structured_payload`, balanced-brace extraction replacing brittle regex, runtime payload-key validator `validate_prod_blockers_payload` replacing grep lint, `schema_version: "v1"` tag, `RESOLUTION_APPEND_MAX_CHARS=256` cap with `[truncated]` marker); v7 §9.4 (LD-598 `SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V7_JSON_STRING_AWARE_EXTRACTOR_V1`, Cursor AMEND_V3 hardening — `extract_structured_payload` replaced brace counter with JSON-string-aware state machine tracking `in_string` + `escape`; only counts `{`/`}` outside strings; preserves graceful None fallback + STALE_MUTEX_PARSE_FAILURE activity-log row). v3+v4 example bodies remain as historical record.
- **Field-name gotcha (added v2.2; v6 authoritative as of v2.3; v7 authoritative as of v2.4).** `prod_blockers` has only 8 fields (per bullet 1 above); `details` and `resolution_notes` are NOT fields. v3 + v4 example bodies referenced both incorrectly; v5 §9.4 corrected; v6 §9.4 hardened; v7 §9.4 further hardened the extractor. Migration script MUST follow v7's example bodies — `STRUCTURED_DETAILS_JSON:` text-embedded JSON inside `description` for the structured payload (host/pid/started_at/script_version + `schema_version: "v1"` tag per v6 non-blocker E, preserved in v7); resolution context appends to `description` on release PATCH, capped at `RESOLUTION_APPEND_MAX_CHARS=256` with `[truncated]` marker (preserved in v7). Stale-mutex parser (Phase G rehearsal + acquire path) MUST use the v7 JSON-string-aware state-machine extractor `extract_structured_payload(description)` (delimiter-find + JSON-string-aware brace counting tracking `in_string` + `escape`; only counts `{`/`}` when `not in_string`; try/except wraps `json.loads`) per v7 Blocker F (LD-598) — replaces v6's plain brace counter that mis-handled `}` inside JSON string values. Every prod_blockers POST/PATCH MUST also pass through the runtime payload-key validator `validate_prod_blockers_payload(payload)` per v6 Blocker B, preserved verbatim in v7 (replaces v5's grep-only lint defense; grep lint is now optional defense-in-depth, not the sole gate). Cross-references: spec v7 §9.4 + spec v6 §6 Gate 11.2 (v6 replacement, preserved in v7) + §7 risk #14 + risk #15 (regex-extraction failure mode) + risk #16 (brace-counter implementer drift; LOW likelihood / HIGH severity, NEW in v7) + LD-596 + LD-598 + schema-ref doc §5 + LD-592.
- **Runtime helpers + allowed-keys constant (added v2.3).** v6 ships two runtime helpers + one whitelist constant that the migration script MUST import + invoke; they are the spec-side authority for prod_blockers writes going forward. (1) `extract_structured_payload(description: str) -> Optional[dict]` — locates the `STRUCTURED_DETAILS_JSON:` delimiter inside a `prod_blockers.description` field, extracts the JSON object via balanced-brace counting (handles nested braces correctly, unlike the v5-era regex), and returns the parsed dict or `None` on parse failure (try/except wraps `json.loads`). Used by Phase G rollback rehearsal + the §9.4 acquire-path stale-mutex check. **v7 update (added v2.4):** `extract_structured_payload` uses JSON-string-aware state machine per v7 §9.4 + LD-598 (replaces v6's brace counter that mis-handled `}` inside JSON string values); the v7 implementation tracks `in_string` + `escape` and only counts `{`/`}` when `not in_string`; graceful `None` fallback + STALE_MUTEX_PARSE_FAILURE activity-log row preserved. All other v6 patterns unchanged. (2) `validate_prod_blockers_payload(payload: dict) -> None` — raises if any key in `payload` is not in `ALLOWED_PROD_BLOCKERS_KEYS = {"id", "module_id", "severity", "title", "description", "is_resolved", "created_at", "resolved_at"}`. The migration script MUST invoke this validator IMMEDIATELY BEFORE every POST or PATCH to `prod_blockers` — the §9.4 mutex acquire POST, the §9.4 mutex release PATCH, the Phase 3 admin-UI canonical row id=101 idempotent-resolve PATCH, and any drift-halt autofile POST. The validator + ALLOWED_PROD_BLOCKERS_KEYS stay v6-authored (still valid in v7). Hazard warning: historical-block (cf. v6 non-blocker D) — bullets 3+4 reference older spec versions for traceability ONLY; do NOT treat v3/v4/v5/v6's brace-counter extractor as authoritative for new code. v7 + LD-598 are the active spec-side authority for `extract_structured_payload`; v6 + LD-596 remain authority for `validate_prod_blockers_payload` + ALLOWED_PROD_BLOCKERS_KEYS + Gate 11.2 + schema_version + RESOLUTION_APPEND_MAX_CHARS. Cross-references: spec v7 §9.4 (extractor) + spec v6 §6 Gate 11.2 + §9.4 validator definitions + LD-596 + LD-598.

---

## §7 Final report — required structure (per HANDOFF_TEMPLATE_v2)

Final report path: `Production/docs/SCHEMA_MIGRATION_V3_IMPLEMENTATION_REPORT_<YYYYMMDD>.md`.

Required sections (9 total per HANDOFF_TEMPLATE_v2 §"Final report — required structure"):

1. **HALT gate scan results** — entry-level Gates 1-5 state at session start (MET / NOT MET / N/A) with evidence cited. Quote the §4 declaration line verbatim. PLUS mechanical halts #1-#4 firing log: which (if any) fired, with the activity-log row id capturing the halt's evidence. If any entry-level gate was NOT MET, the report is a halt-report and remaining sections are N/A.
2. **Per-phase diff (verbatim)** — every code/data change. For Phase B: full file content of `migrate_schema_vocab_v1.py` (or the ranges). For Phases D-N: list of artifacts written + their sha256 + size + line count + checkpoint file final state.
3. **Per-phase audit-checklist results** — gate state at phase-end. For each phase A-O: did it produce its deliverable? Did its per-step verification pass?
4. **Directus writes** — full POST/PATCH bodies + read-back proofs. List every activity-log row id captured + every `prod_blockers` row id (drift halt autofile if any; canonical pre-filed Phase 3 row id=101 — referenced by id, NOT autofiled, with idempotent auto-resolve PATCH on hit-path; remote mutex acquire/release). Note any queued writes (Directus-offline path).
5. **Activity log rows** — verbatim row contents with row id captured. Cite every row by id + action + details. Total expected rows in clean execution: ~496 PATCH activity-log rows (Phases I+J+L) + Phase 0 markers (5) + Phase 6 marker + mutex acquire/release (2) + Phase 5 gated-halt marker (1).
6. **Confidence tags per Rule 24** — every claim in the report tagged CONFIRMED / INFERRED / GUESSED.
7. **Self-classification** — TRIVIAL / ROUTINE / ARCHITECTURAL. Default to ARCHITECTURAL given the migration introduces remote-mutex + checkpoint + rollback-rehearsal disciplines for the first time + executes ~176 row mutations under those disciplines.
8. **Limitations** — what wasn't covered. EXPLICITLY list: Phase 5 (Rule 1 severity HIGH/CRITICAL → HARD, ~320 rows) deferred per spec §3.1 PHASE_5_ENABLED gate (expected); whichever of mechanical halts #1-#4 fired (if any); whether Phase K detected admin-UI gap (if so, canonical pre-filed `prod_blockers` id=101 is the resolution path; no duplicate autofiled per v2.1); LD_WRITER_CANONICAL_VOCAB_V1 confirmation source (live query vs Kim chat); cached-export re-use vs supersede decision (whichever was made).
9. **Cross-skill drift** — does this change require parallel updates to mn-context, dashboard-gate, tech-spec, or schema reference doc? Document any required follow-ups; create as `prod_blockers` rows with `is_resolved=false` if the follow-ups can't ship in this session.

The final report ALSO includes a **summary block to Kim** at the bottom:

> **Phases 0-4 + 6 complete; Phase 5 self-gated on PHASE_5_ENABLED (deferred).**
>
> Per spec v3 §3.1, Phase 5 (Rule 1 severity HIGH/CRITICAL → HARD, ~320 rows) is the only execution-gated phase; this session deliberately did not set the env var, so Phase 5 halted cleanly per spec design.
>
> Per-phase summary:
> - Phase 0 (cached export + snapshot + dry-run + rehearsal): COMPLETE / HALTED-mechanical-#N
> - Phase 1 (Rule 4 scope_domain remap, ~29 rows): COMPLETE / HALTED-mechanical-#N
> - Phase 2 (Rule 2 lowercase → UPPER, ~37 rows): COMPLETE / HALTED-mechanical-#N
> - Phase 3 (admin-UI detection): PASSED-7-enum-values-present (idempotent auto-resolve of prod_blockers id=101) / HALTED-AWAITING-KIM-ADMIN-UI (canonical prod_blockers id=101 still unresolved; no duplicate autofile per v2.1)
> - Phase 4 (Rule 3b task_category remap, ~110 rows): COMPLETE / HALTED-mechanical-#N / SKIPPED-because-Phase-3-blocked
> - Phase 5 (Rule 1, ~320 rows): DEFERRED-on-PHASE_5_ENABLED-gate (expected)
> - Phase 6 (final audit + mutex release): COMPLETE
>
> If you want to dispatch Phase 5, set `PHASE_5_ENABLED=true` and file LD `SCHEMA_VOCAB_MIGRATION_PHASE_5_AUTHORIZED_V1` per spec §3.1; otherwise Phase 5 stays deferred. If a mechanical halt fired during execution, the activity-log row + the snapshot + the checkpoint file together define the resume path; re-invoke `python3 migrate_schema_vocab_v1.py all` once the underlying issue is resolved.

---

## §8 Reference files (companion paths per HANDOFF_TEMPLATE_v2 §0.3)

All paths absolute + canonical-root tagged per HANDOFF_TEMPLATE_v2 §0.3 §"Companion path discipline".

**Specs + handoffs (Dropbox-rooted, canonical root #1):**
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v3.md` — Dropbox-rooted (canonical root #1; the v3 spec under implementation)
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v2.md` — Dropbox-rooted (v2 historical baseline; Phase 0 §5 narrative inherited)
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v1.md` — Dropbox-rooted (v1 historical baseline)
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v3.md` — Dropbox-rooted (Cursor v3 review handoff; verdict source)
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_TEMPLATE_v2.md` — Dropbox-rooted (authoring template)
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_CLEANUP_AND_SUPABASE_HARDENING_REPORT_20260508.md` — Dropbox-rooted (baseline counts + 4 canonical rules motivation)

**Code + libraries (Dropbox-rooted, canonical root #1):**
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/scripts/migrate_schema_vocab_v1.py` — Dropbox-rooted (NEW; Phase B authors this file)
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/lib/directus.py` — Dropbox-rooted (DirectusClient + try_post_or_queue + _validate_json_columns)
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/lib/severity_vocab.py` — Dropbox-rooted (SEVERITY_RANK helper for Rule 1 mapping)
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/scripts/lock_decision.py` — Dropbox-rooted (canonical-aware as of LD 588; Task H predecessor)
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/scripts/lock_decision.py.bak.20260508` — Dropbox-rooted (pre-Task-H backup; reference)

**Generated artifacts (Dropbox-rooted, canonical root #1):**
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/exports/prod_locked_decisions_<DATE>.jsonl` — Dropbox-rooted (Phase D output)
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/exports/prod_locked_decisions_<DATE>.metadata.json` — Dropbox-rooted (Phase D sidecar)
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/exports/prod_locked_decisions_2026-05-08.jsonl` — Dropbox-rooted (existing 570-row export from earlier this session; potential re-use candidate per Phase D decision rule)
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/exports/DEFERRED_DIRECTUS_WRITES_20260508_lock_decision_canonical.jsonl` — Dropbox-rooted (already-replayed; reference for queue pattern)
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_VOCAB_MIGRATION_SNAPSHOT_<YYYYMMDD>.jsonl` — Dropbox-rooted (Phase E output)
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_VOCAB_MIGRATION_SNAPSHOT_<YYYYMMDD>.metadata.json` — Dropbox-rooted (Phase E sidecar)
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_VOCAB_MIGRATION_DRY_RUN_<YYYYMMDD>.md` — Dropbox-rooted (Phase F output)
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_VOCAB_MIGRATION_ROLLBACK_REHEARSAL_<YYYYMMDD>.md` — Dropbox-rooted (Phase G output)
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/exports/schema_migration_checkpoint_<DATE>.jsonl` — Dropbox-rooted (Phases I/J/L per-row append per spec §5.0)
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_VOCAB_MIGRATION_PHASE_1_REPORT_<DATE>.md` — Dropbox-rooted (Phase I output; Rule 4 scope_domain remap, ~29 rows)
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_VOCAB_MIGRATION_PHASE_2_REPORT_<DATE>.md` — Dropbox-rooted (Phase J output; Rule 2 lowercase → UPPER, ~37 rows)
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_VOCAB_MIGRATION_PHASE_4_REPORT_<DATE>.md` — Dropbox-rooted (Phase L output; Rule 3b task_category remap, ~110 rows)
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_VOCAB_MIGRATION_PHASE_6_REPORT_<DATE>.md` — Dropbox-rooted (Phase N output; final-audit reconciliation)
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_MIGRATION_V3_IMPLEMENTATION_REPORT_<YYYYMMDD>.md` — Dropbox-rooted (Phase O output; the final session report)

**Directus rows pre-filed (canonical reference by id) and mechanically autofiled at runtime:**
- `prod_blockers` row id=**101** — `SCHEMA_VOCAB_MIGRATION_PHASE_3_TASK_CATEGORY_ENUM_ADD_PENDING_V1` (filed 2026-05-08, severity=`high` lowercase, is_resolved=false at handoff authoring time). PRE-FILED canonical reference for Phase K — Phase K does NOT autofile a duplicate; references this id verbatim. Idempotent auto-resolve on Phase 3 hit-path per Phase K step 4.
- `prod_activity_log` row id=**1788** — `SCHEMA_VOCAB_MIGRATION_PHASE_3_BLOCKER_FILED` (companion activity-log row recording the filing of prod_blockers id=101).
- `prod_blockers` row `SCHEMA_MIGRATION_LOCK_HELD_BY_<HOST>` — §9.4 remote mutex; acquired Phase I, released Phase N (or Phase K on admin-UI halt). Severity `critical` (lowercase per live schema; spec v3 §9.4's `CRITICAL` must be case-folded — see §6 prod_blockers schema gotchas). `is_resolved` false→true.
- `prod_blockers` row `SCHEMA_VOCAB_MIGRATION_DRIFT_<DATE>` — Phase F mechanical halt #2 autofile (only if drift > 25%). Severity `high` (lowercase). `is_resolved=false`.

**Configuration + state (outside-canonical-but-allowed exceptions per HANDOFF_TEMPLATE_v2 §"Operational consequence"):**
- `~/.claude/skills/zero-error-qa/SKILL.md` — global Claude config (DS-26, DS-27, DS-28 authority)
- `~/.claude/skills/tech-spec/SKILL.md` — global Claude config (§0.11 dependency-order discipline reference)
- `pending_directus_writes.json` — relative to script cwd (per DirectusClient default); resolves under canonical root #1 when script is run from there

**LDs and activity-log rows (Directus-rooted; reference by id):**
- LD 586 `SCHEMA_VOCAB_TOLERANT_FILTER_V1` (Part 1 read-side defensive fix)
- LD 588 `LD_WRITER_CANONICAL_VOCAB_V1` (Task H execution; Kim-confirmed live)
- LD 584 `WORKTREE_CONFUSION_PREVENTION_V1` (DS-27 v2 dual-canonical; absolute-path authority)
- LD 578 `GATE_CHECK_DISCIPLINE_NO_AUTONOMOUS_BYPASS_V1` (DS-26 authority)
- (NEW pending Phase O) LD `SCHEMA_VOCAB_MIGRATION_V3_IMPLEMENTATION_COMPLETE_V1` — recommended LD to file at Phase O documenting clean Phases-0-4-+-6 completion + Phase 5 deferred-on-PHASE_5_ENABLED + artifact paths + mutex release evidence. SOFT severity, governance scope. (If a mechanical halt fired, file instead `SCHEMA_VOCAB_MIGRATION_V3_HALT_<HALT_NAME>_V1` with HARD severity to flag the resume requirement.)

---

## §9 Confidence summary (Rule 24)

| Claim | Tag | Evidence |
|-------|-----|----------|
| Spec v3 sha256 = `e8ea98...` | CONFIRMED | shasum probe in handoff authoring (487 lines, 38,433 bytes) |
| Cursor v3 verdict = AUTHORIZE_PHASE_0_WITH_RISK_ACCEPTANCE | CONFIRMED | Direct quote from Cursor's response in this session |
| LD 588 confirmed live | CONFIRMED | Kim verbal confirmation in this session per summary |
| `migrate_schema_vocab_v1.py` does not exist yet | CONFIRMED | ls -la at handoff authoring time returned "No such file or directory" |
| 570-row cached export at `Production/exports/prod_locked_decisions_2026-05-08.jsonl` already exists | CONFIRMED | Memory + summary; ls -la returned 1,124,003 bytes, sha256 4ac319c4... |
| Phase G rehearsal will produce same sample with random.seed(42) | CONFIRMED | Spec §5 Step 0.5 mandates the seed; deterministic by design |
| Directus reachability at handoff authoring time | INFERRED | Railway agent earlier this session restored Directus; current state assumed up but MUST be probed in Phase A |
| Phase D existing-export re-use vs supersede decision | INFERRED | Decision rule documented; outcome depends on live Directus state |
| `details` JSON-column gotcha applies to all POST in this handoff | CONFIRMED | Memory `feedback_directus_schema_canonical.md` + `_validate_json_columns` validator |
| Phase 5 mechanical gating via `PHASE_5_ENABLED` env var per spec §3.1 v2 resolution | CONFIRMED | Spec §3.1 explicitly mandates `PHASE_5_ENABLED=false` by default; flip required for Phase 5 dispatch; this handoff §5 Phase M honors that gate |
| Phases 1-4 + 6 execute autonomously after Phase 0 if rehearsal passes | INFERRED | Per §1 Mission authorization argument: Cursor's verdict speaks to design soundness; spec §3.1 PHASE_5_ENABLED is the only spec-mandated execution gate beyond §6 Gates 1-9; therefore Phases 1-4 + 6 execution is consistent with both Cursor's verdict and the spec |
| Mechanical halts #1-#4 are the only halt-blocking conditions during execution | CONFIRMED | Per §4 mechanical halts catalog; each maps to a real failure (rehearsal fail / drift > 25% / Directus offline / PATCH-verify mismatch) |
| Phase 3 admin-UI detection is mechanical, not artificial Kim-review halt | CONFIRMED | Per §5 Phase K v2.1: probes live Directus schema for the 7 enum values; halts only if absent; references canonical pre-filed prod_blockers id=101 (no duplicate autofile) + activity-log + exit non-zero; on hit-path idempotently auto-resolves row 101 |
| Drift threshold of 25% is a v1 heuristic | CONFIRMED | Per §4 mechanical halt #2 + §5 Phase F: `DRIFT_THRESHOLD_PCT=25` constant; future tuning is one-line edit |
| `prod_blockers` row id=101 is the canonical Phase 3 admin-UI reference (filed 2026-05-08, title `SCHEMA_VOCAB_MIGRATION_PHASE_3_TASK_CATEGORY_ENUM_ADD_PENDING_V1`, severity=`high` lowercase, is_resolved=false at handoff authoring time) | CONFIRMED | Wave A live probe via `DirectusAdminClient.get_item("prod_blockers", 101)`; Phase K v2.1 references this id verbatim with idempotent auto-resolve on hit-path |
| `prod_blockers` schema has NO `details` JSON column (only 8 fields: id, module_id, severity, title, description, is_resolved, created_at, resolved_at) | CONFIRMED | Wave A schema probe via `DirectusAdminClient.fields("prod_blockers")`; row 101's structured payload lives in `description` as text-embedded `STRUCTURED_DETAILS_JSON:` block |
| `prod_blockers.severity` enum is lowercase (high/critical/medium/low) — opposite of `prod_locked_decisions.severity` (HARD/HIGH/etc.) | CONFIRMED | Wave A live probe of row 101 returned `severity: "high"`; mutex collision risk for spec §9.4 documented in §6 prod_blockers schema gotchas |

---

## §10 What NOT to do (anti-patterns specific to this handoff)

1. **Do not invoke `phase-5` subcommand without `PHASE_5_ENABLED=true` env var.** The script will halt mechanically at the env-var gate per spec §3.1, but the handoff explicitly states this is forbidden in this session — Phase 5 dispatch is a SEPARATE handoff that sets the env var + files LD `SCHEMA_VOCAB_MIGRATION_PHASE_5_AUTHORIZED_V1`.
2. **Do not skip the rollback rehearsal.** Mechanical halt #1 fires if rehearsal fails; the migration cannot proceed past Phase 0 without rehearsal pass. Cursor's risk-acceptance hinges on this artifact.
3. **Do not commit any files in this session.** Phase B writes the script; Phases D-G write Phase 0 artifacts; Phases I/J/L write per-phase reports + checkpoint file; Phase N writes Phase 6 audit; Phase O writes the final session report. None get git-committed in this handoff. Kim reviews + commits separately.
4. **Do not edit `lock_decision.py`.** Task H already executed; LD 588 already filed; re-editing would be a duplicate change.
5. **Do not write `details` as a JSON string.** Always pass dict to `try_post_or_queue`; the validator will catch and surface, but better to never trip it.
6. **Do not run from `.claude/worktrees/...`.** DS-27 v2 dual-canonical hard rule. Step 0 (Phase C) asserts this and halts if violated.
7. **Do not assume the existing 2026-05-08 cached export is still valid.** Re-probe schema_hash + total_active_rows before re-using; new LDs may have landed via lock_decision.py since the 11:51 mtime of the existing export.
8. **Do not bypass `try_post_or_queue`.** Direct `client.post(...)` calls bypass the JSON-column validator + the offline queue — both load-bearing for end-to-end robustness.
9. **Do not skip the §5.0 checkpoint append for any row in Phases I/J/L.** Each successful PATCH+read-back+activity-log triple MUST append a checkpoint line + flush + fsync before the next row begins. A crash between rows leaves the checkpoint at the last-confirmed-good row; resume picks up there.
10. **Do not release the §9.4 remote mutex prematurely.** Phase I acquires; Phase N (or Phase K on admin-UI halt) releases. Releasing in the middle of Phases I/J/L would allow a concurrent runner to double-PATCH.
11. **Do not retry mechanical halts in a sleep loop.** If mechanical halt #1, #2, #3, or #4 fires, surface the failure to Kim via the activity-log row + the autofiled `prod_blockers` row. Retrying the same operation without addressing the underlying cause re-fires the halt and pollutes the activity log.
12. **Do not auto-detect 7 task_category enum names from the cached export.** Phase K probes the LIVE Directus schema (not the cached export rows); the cached export captures rows, not schema enum lists. Schema enum changes are Kim's hands in admin UI per spec §5 Phase 3.
13. **Do NOT autofile a fresh `prod_blockers` row at runtime when a prereq row already exists.** Phase K v2.1 references canonical row id=**101** (`SCHEMA_VOCAB_MIGRATION_PHASE_3_TASK_CATEGORY_ENUM_ADD_PENDING_V1`, filed earlier same day 2026-05-08). On hit-path, idempotent auto-resolve. On miss-path, do NOT POST a duplicate prod_blockers row — instead, surface row 101 to stderr + log activity-log row referencing `prod_blockers_id=101`.
14. **Do NOT use uppercase severity on `prod_blockers` writes.** Live schema is lowercase (`high` / `critical` / `medium` / `low`). Spec v3 §9.4's `CRITICAL` for the mutex row must be case-folded to `critical` before POST or Directus returns HTTP 500. See §6 prod_blockers schema gotchas (added v2.1).
15. **Do NOT POST a `details` key to `prod_blockers`.** That collection has only 8 fields; `details` is not one of them. Structured payloads live in `description` as a text-embedded `STRUCTURED_DETAILS_JSON:` block (the convention established by row 101). `prod_activity_log.details` IS a JSON column (dict-not-string per the existing JSON-column gotcha).

---

## §11 Versioning

- **v1** — 2026-05-08 — initial canonical implementation handoff for schema migration v3 Phase 0 only. Author: gallant-bouman-804b4f worktree session, post-Cursor-AUTHORIZE_PHASE_0_WITH_RISK_ACCEPTANCE verdict on v3 spec. Old filename: `HANDOFF_SCHEMA_MIGRATION_V3_PHASE_0_IMPLEMENTATION_20260508.md`. Bound execution to Phase 0 + asked Kim to review "Gates 1-12" before authorizing Phases 1-5.
- **v2** — 2026-05-08 — revised in response to Kim's challenge that Gates 1-12 review is not a genuine human decision (Gate 10 = mechanical: pass→proceed, fail→spec already mandates HALT; Gate 11 = rubber-stamp; Gate 12 = rubber-stamp; "drift signal" = mechanical with threshold halt; Phase 5 lossy mapping decision = already debated in dual-Opus + already gated by `PHASE_5_ENABLED` feature flag in spec). Phases 1-4 + 6 added to scope; Phase 5 stays self-gated on `PHASE_5_ENABLED` env var per spec §3.1. Mechanical halts only (rehearsal fail / drift > 25% / Directus offline / PATCH-verify fail / Phase 3 admin-UI not done). Filename rename: `HANDOFF_SCHEMA_MIGRATION_V3_PHASE_0_IMPLEMENTATION` → `HANDOFF_SCHEMA_MIGRATION_V3_IMPLEMENTATION` (drop "PHASE_0" since now covers Phases 0-4 + 6). Authority for Phases 1-4 + 6 execution: Cursor's `AUTHORIZE_PHASE_0_WITH_RISK_ACCEPTANCE` was about spec design soundness ("no v4-level design blocker was found"), not phase-by-phase authorization; spec §3.1 PHASE_5_ENABLED is the only spec-mandated execution gate beyond §6 Gates 1-9; therefore Phases 1-4 + 6 execution is consistent with both Cursor's verdict and the spec. [INFERRED]
- **v2.1** — 2026-05-08 — Phase K updated to reference prod_blockers id=101 (filed today) instead of mechanically autofiling at runtime; defense-in-depth runtime check preserved with auto-resolve-on-success behavior. Idempotent: skip PATCH if row already resolved. §6 Hard rules subsection added documenting prod_blockers schema gotchas (no `details` column / lowercase severity / mutex collision risk for §9.4). §8 Reference files amended to list prod_blockers id=101 + companion prod_activity_log id=1788 as canonical pre-filed rows. §9 Confidence summary added 3 rows covering id=101 + the 2 prod_blockers schema findings. §10 added anti-patterns 13/14/15 (no-duplicate-autofile / no-uppercase-severity / no-`details`-on-prod_blockers). Author: gallant-bouman-804b4f session, post-Kim-challenge same day.
- **v2.2** — 2026-05-08 — §6 Hard rules `prod_blockers schema gotchas` subsection updated. Third bullet's closing clause changed from "spec needs reconciliation in a future v4 amendment" to "spec reconciliation landed at v4 (LD-593, severity case-fold) + v5 (LD-595, field-name fixes)." New fourth bullet added documenting the field-name gotcha (`details`/`resolution_notes` not real fields; `STRUCTURED_DETAILS_JSON:` pattern in `description` per v5 §9.4). Authority: spec v5 + LD-595 + schema-ref doc §5 + handoff §6 prod_blockers schema gotchas (preserved bullets 1-2 from v2.1). Author: gallant-bouman-804b4f session, post-Kim-authorization same day.
- **v2.3** — 2026-05-08 — §6 prod_blockers schema gotchas updated. Third bullet's closing clause extended with v6 §9.4 + LD-596 (Cursor AMEND_V2 hardening — guarded JSON parse, balanced-brace extraction, runtime validator, schema_version, resolution-append cap). Fourth bullet's cross-references updated to cite v6 + LD-596 + risk #15 (regex-extraction failure mode). NEW fifth bullet added documenting `extract_structured_payload` + `validate_prod_blockers_payload` runtime patterns + `ALLOWED_PROD_BLOCKERS_KEYS` constant. v6 + LD-596 are now spec-side authority for all prod_blockers writes; v3-v5 example bodies preserved as historical record only. Author: gallant-bouman-804b4f session, post-Cursor-AMEND_V2-on-v5 + Kim-authorization same day.
- **v2.4** — 2026-05-08 — §6 prod_blockers schema gotchas updated. Third bullet's closing clause extended once more with v7 §9.4 + LD-598 (Cursor AMEND_V3 hardening — `extract_structured_payload` JSON-string-aware state machine; replaces v6's brace counter that ignored JSON string state). Fourth bullet's cross-references updated to add LD-598 + risk #16. Fifth bullet's `extract_structured_payload` clause clarified to specify the v7 state-machine version is authoritative (v6 brace counter retired). v7 + LD-598 are now spec-side authority for all prod_blockers writes; v3-v6 example bodies and v6's brace-counter extractor preserved as historical record only. Author: gallant-bouman-804b4f session, post-Cursor-AMEND_V3-on-v6 + Kim-authorization same day.
- **v2.5** — 2026-05-09 — §1 Header sha256 reference updated from spec v3 stale SHA-1 to spec v8 actual sha256 (per CLI dispatch findings + LD-NEW). Spec lineage now v3 → v4 → v5 → v6 → v7 → v8. Author: gallant-bouman-804b4f session, post-CLI-Phase-F.
- Future revisions: a Phase 5 dispatch handoff (`HANDOFF_SCHEMA_MIGRATION_V3_PHASE_5_DISPATCH_<DATE>.md`) would be a SEPARATE doc that sets `PHASE_5_ENABLED=true` + files LD `SCHEMA_VOCAB_MIGRATION_PHASE_5_AUTHORIZED_V1`. Do NOT extend this handoff for Phase 5; author a new one when Kim is ready.

---

## §12 Origin context

This handoff is the implementation companion to spec v3, which itself was the result of:
- v1 (2026-05-08 morning) — initial dual-Opus debate produced 4 mapping rules.
- v2 (2026-05-08 mid-day) — Cursor AMEND_V2 on v1 (4 amendments) → PHASE_5_ENABLED feature flag + dual-canonical paths + snapshot integrity fields + cost split.
- v3 (2026-05-08 afternoon) — Cursor AMEND_V2 on v2 (5 amendments — Tasks B/D/E/F/H) → cached export + rollback rehearsal + remote mutex + checkpoint protocol + lock_decision.py canonical-aware (Task H executed inline).
- Cursor v3 review (2026-05-08 afternoon) — `AUTHORIZE_PHASE_0_WITH_RISK_ACCEPTANCE` based on offline-fallback (Cursor's 403 to live Directus) + cached export evidence + Kim-confirmed LD 588.
- Handoff v1 (2026-05-08 evening) — bound execution to Phase 0 only + asked Kim to review Gates 1-12.
- Handoff v2 (2026-05-08 evening) — Kim challenged the Gates 1-12 review as not a genuine human decision; revised to dispatch Phases 0-4 + 6 autonomously with mechanical halts only; Phase 5 stays self-gated on PHASE_5_ENABLED.

This v2 handoff dispatches Phases 0-4 + 6. Phase 5 dispatch requires fresh Kim consent + a separate handoff that sets `PHASE_5_ENABLED=true` per spec §3.1.

---

## §13 Cross-references

- Spec v3 §0.1 changelog — verbatim resolution of Cursor's 5 amendments to v2.
- Spec v3 §3.1 v2 PHASE_5_ENABLED feature flag — the canonical Phase 5 self-gating mechanism.
- Spec v3 §5 Phase 0 (Steps 0/0.4/0.5/1/2/3) — Phase 0 work.
- Spec v3 §5 Phase 1, 2, 4 — mutating-phase narrative (Phases I, J, L of this handoff).
- Spec v3 §5 Phase 3 — admin-UI work (Phase K mechanical detection of this handoff).
- Spec v3 §5 Phase 6 — final-audit narrative (Phase N of this handoff).
- Spec v3 §5.0 — checkpoint and resume protocol (Phases I/J/L per-row append).
- Spec v3 §6 Gates 1-9 — entry-level acceptance criteria.
- Spec v3 §6 Gates 10/11/12 — accepted as YES-by-construction in this handoff (rehearsal pass = mechanical halt #1; remote mutex = standard for mutating phases; checkpoint protocol = standard for mutating phases).
- Spec v3 §9.4 — remote mutex via Directus `prod_blockers` row.
- HANDOFF_TEMPLATE_v2 §"HALT gates" — the §4 of this handoff conforms to that structure (entry-level Gates 1-5 + mechanical halts #1-#4).
- HANDOFF_TEMPLATE_v2 §"Anchored citation discipline" — applied throughout §3.1.
- HANDOFF_TEMPLATE_v2 §"Companion path discipline" — applied throughout §8.
- HANDOFF_TEMPLATE_v2 §"Absolute-path filesystem discipline" — applied throughout §6 hard rules.
- DS-26 (zero-error-qa SKILL.md) — agent-side gate-check enforcement.
- DS-27 (zero-error-qa SKILL.md) — agent-side absolute-path enforcement.
- DS-28 (zero-error-qa SKILL.md) — agent-side dependency-order enforcement (Phase A→B→...→O sequence).
- LD 586 — Part 1 vocab-tolerant filter (predecessor; read-side defensive).
- LD 588 — Task H executed (predecessor; LD-writer canonical-aware).
