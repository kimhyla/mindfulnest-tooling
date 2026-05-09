# HANDOFF v3 — DS-23 / DS-24 / DS-25 Mechanical CI Gates Implementation

**Header**

- **Title:** DS-23 / DS-24 / DS-25 Mechanical Gate Implementation v3 (pre-commit + CI; trigger-model fix applied)
- **Target session:** Terminal CLI session, executed against canonical tooling-repo path `/Users/kimberlysmith/Projects/mindfulnest-tooling/` AND canonical Dropbox path `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/`. Dual-canonical-root rule per HANDOFF_TEMPLATE_v2 + DS-27 v2.
- **Source spec (v3 content):** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v2.md` (file path `..._v2.md`; CONTENT version is v3 per §0.1 changelog inside the spec — v3 = AMEND_V2 of v2 content).
- **v2 baseline (historical, preserved):** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v1.md` (file path `..._v1.md`; CONTENT was v2 per its prior changelog). Do NOT delete or modify; needed for diff comparison.
- **Source session:** gallant-bouman-804b4f worktree (this handoff authored from worktree; implementation runs against canonical paths only).
- **Estimated time:** 6–8 hours machine + ~2 hours Kim review (unchanged from v2 handoff).
- **Authority:** LD `DS_23_24_25_DISCIPLINE_STANDARDS_V1` (LD 580), `prod_blockers` rows `DS_23_MECHANICAL_GATE_PENDING` / `DS_24_MECHANICAL_GATE_PENDING` / `DS_25_MECHANICAL_GATE_PENDING`. **Cursor verdict on v3 spec: AUTHORIZE_IMPLEMENTATION** (per `Production/docs/HANDOFF_CURSOR_REVIEW_DS_23_24_25_GATE_SPEC_20260508_v3.md` — Cursor re-reviewed v3 after v2's HIGH blocker (Q-NEW-1: workflow_run / pull_request payload mismatch) was fixed via §7.3.1 trigger-model split).
- **Authoring template:** `Production/docs/HANDOFF_TEMPLATE_v2.md` (mandatory v2 structure).
- **Self-classification:** ARCHITECTURAL (governance + CI/local-hook infrastructure across two surfaces; introduces documented bypass mechanism + new-contributor `MN_FRESH` ergonomic pathway). v3 amendment classification: STANDARD (faithful rendering of GHA event-model semantics; no doctrine change to DS-23/24/25).
- **Predecessor handoff (preserved as historical):** `Production/docs/HANDOFF_DS23_24_25_IMPLEMENTATION_20260508.md` (v2 handoff, authored against v2 spec). Do NOT delete; needed for diff history.

---

## §0.1 v3 Changelog — what changed from the v2 handoff

This handoff supersedes `HANDOFF_DS23_24_25_IMPLEMENTATION_20260508.md` (the v2 handoff). The v2 handoff was authored when the spec was still under Cursor review for v2 content; Cursor returned **AMEND_V2** with 1 HIGH blocker (Q-NEW-1) + 4 MED non-blockers (V3/V4/V5/V6). The spec was amended to v3 content (file path remains `..._v2.md` per the spec's path-naming convention; content is v3 per §0.1 changelog inside). Cursor then re-reviewed v3 and emitted **AUTHORIZE_IMPLEMENTATION**.

This v3 handoff incorporates the v3 spec's amendments into the implementation plan. v2 handoff is preserved as historical baseline.

| # | v2-handoff state | v3-handoff state | Rationale |
|---|-------------------|-------------------|-----------|
| 1 | Source spec citation = `..._v1.md` (v1 file naming, v1/v2 content ambiguity) | Source spec citation = `..._v2.md` (v3 content per §0.1 changelog inside) | v3 spec content is the implementation target. v2 baseline at `..._v1.md` is preserved historical only. |
| 2 | Cursor verdict = "pending v2.1 path-fix" | Cursor verdict = "AUTHORIZE_IMPLEMENTATION on v3 content" | Cursor re-reviewed v3 after the workflow_run/pull_request HIGH blocker fix and authorized implementation. |
| 3 | Phase B Step 2 lists ONE workflow file (`ds_23_24_25_gate.yml` containing all three jobs including `ds_25_check`) | Phase B Step 2 lists `ds_23_24_25_gate.yml` (DS-23 + DS-24 jobs only) PLUS `ds_25_check.yml` (REQUIRED — `pull_request` primary trigger) PLUS optional `ds_25_check_after_codeql.yml` (`workflow_run` secondary trigger using `gh api`) | v3 §7.3.1.A/B split: DS-25 needs `pull_request` trigger (canonical) for reliable `github.event.pull_request.body` access. The `workflow_run` secondary trigger MUST query the PR via `gh api` rather than reading payload fields (this is the v2 HIGH blocker fix). |
| 4 | DS-25 CI check (Phase B Step 2 third bullet) reads `${{ github.event.pull_request.body }}` regardless of trigger | DS-25 CI check uses TWO YAML files per §7.3.1.A/B: primary reads `github.event.pull_request.body` under `pull_request`; secondary uses `gh pr view --json body` under `workflow_run` and explicitly does NOT reference `github.event.pull_request.*` | v2's pattern would fail at runtime under `workflow_run` because the payload doesn't populate those fields reliably. |
| 5 | No Phase E.5 (SKILL flip is in Phase F) | Phase E.5 inserted (SKILL flip lands same-day as Phase D); old Phase F is renamed "Phase F (legacy)" and now ONLY handles `prod_blockers` row retirement + Phase 7.5 Step 6/7 narrative update | v3 closes the stale-doc window where SKILL.md says "DISCIPLINE-ONLY" while gates are already mechanical. |
| 6 | No `MN_FRESH=1` pathway | New §11.3 implementation: pre-commit hook + CI gate honor `MN_FRESH=1` for fresh contributors (<30 days of commits in tooling repo); warning-not-fail; logs `DS_FRESH_CONTRIBUTOR_BYPASS` activity row | v3 addresses sentinel ergonomics for new contributors per Cursor MED V4. |
| 7 | §11.2 thresholds (>3 bypasses/7d, <50 chars rationale) tagged as fixed values | §11.2 thresholds tagged `[INFERRED — calibrate after Phase G 30-day audit]`; Phase G now has explicit re-calibration directive | v3 acknowledges thresholds are not yet evidence-backed per Cursor MED V5. |
| 8 | Final-report path is `Production/docs/DS23_24_25_IMPLEMENTATION_REPORT_<YYYYMMDD>.md` | Final-report path is `Production/docs/DS23_24_25_IMPLEMENTATION_REPORT_<YYYYMMDD>_v3.md` | Distinguishes v3 implementation from any future v4 amendment. |
| 9 | Phase ordering: A → B → C → D → E → F → G → H → I (9 phases) | Phase ordering: A → B → C → D → E.5 → E → F → G → H → I (10 phase slots; E.5 inserted) | v3 phase ordering per §8 amendment. |
| 10 | LD POST cites spec `..._v1.md` | LD POST cites spec `..._v2.md` (v3 content) and notes v3 amendment of v2 baseline at `..._v1.md` | LD references the implementation target spec, not the historical baseline. |

---

## §1 Mission

Convert DS-23, DS-24, DS-25 from discipline-only enforcement into mechanical gates that BLOCK commits and/or merges when violated, per the v3 tech spec — DS-23 commit-message regex + helper, DS-24 handler-shape regex + sentinel, DS-25 PR body anchor check (CI-only with v3 trigger-model split: `pull_request` primary + optional `workflow_run` secondary). Each gate ships with `MN_SKIP_*=1` override env var + `DS{23,24,25}_GATE_BYPASSED` audit-row pattern AND a new `MN_FRESH=1` warning-not-fail pathway for fresh contributors. 30-day FP audit calendar entry locked at implementation time, with v3 directive to ALSO re-calibrate §11.2 thresholds from empirical data.

---

## §2 Scope

**Changes in scope (this implementation session):**

1. `/Users/kimberlysmith/Projects/mindfulnest-tooling/Production/scripts/git_hooks/pre-commit` — APPEND DS-23 + DS-24 mechanical-check blocks (per spec §8 Phase A) PLUS `MN_FRESH=1` detection logic per spec §11.3. Per DS-10 "APPEND not replace, no globs."
2. `/Users/kimberlysmith/Projects/mindfulnest-tooling/.github/workflows/ds_23_24_25_gate.yml` (NEW) — CI workflow with TWO jobs (`ds_23_check`, `ds_24_check`) per spec §8 Phase B + §7 per-rule semantics. **v3 change:** DS-25 moves to its own workflow file(s) per §7.3.1.A/B split.
3. `/Users/kimberlysmith/Projects/mindfulnest-tooling/.github/workflows/ds_25_check.yml` (NEW — REQUIRED in v3) — DS-25 primary check with `on: pull_request` trigger types `[opened, edited, synchronize, reopened]`. Reads `github.event.pull_request.body` + `.number` (these fields populate reliably under `pull_request` trigger). Per spec §7.3.1.A.
4. `/Users/kimberlysmith/Projects/mindfulnest-tooling/.github/workflows/ds_25_check_after_codeql.yml` (NEW — OPTIONAL in v3) — DS-25 secondary check with `on: workflow_run` trigger after CodeQL completes. Resolves PR via `gh api /repos/.../commits/<head_sha>/pulls` and reads body via `gh pr view <pr_number> --json body`. **MUST NOT** reference `github.event.pull_request.*` anywhere in this file. Per spec §7.3.1.B. Phase B implementer ships this only if they evidence a concrete CodeQL-late-alert scenario worth the extra workflow.
5. `/Users/kimberlysmith/Projects/mindfulnest-tooling/.github/PULL_REQUEST_TEMPLATE.md` — extend (or create) with the DS-25 Adjacent Risk Sweep section per spec §8 Phase C.
6. `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/RUNBOOK_GATE_BYPASS_MECHANICS.md` (NEW) — bypass-mechanism documentation per spec §8 Phase D, INCLUDING `MN_FRESH=1` pathway documentation per v3 §11.3.
7. `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/scripts/write_gate_bypass_row.py` (NEW) — audit-row writer helper, supports `--gate DS23|DS24|DS25|FRESH` (`FRESH` writes `DS_FRESH_CONTRIBUTOR_BYPASS` row).
8. `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/scripts/weekly_preflight_audit.py` — extend with DS-gate bypass-rate audit (per spec §8 Phase E). Thresholds tagged `[INFERRED — calibrate after Phase G 30-day audit]` per v3 §11.2.
9. `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/.claude/skills/zero-error-qa/SKILL.md` — flip DS-23/24/25 enforcement labels from "DISCIPLINE-ONLY" to "MECHANICAL"; amend Phase 7.5 Step 6 + Step 7 to belt-and-suspenders semantics. **v3 change:** SKILL flip executes in Phase E.5 (immediately after Phase D), NOT Phase F. Phase F retains `prod_blockers` row retirement + Phase 7.5 Step 6/7 narrative update.
10. **30-day FP audit calendar entry** — created at implementation time via `mcp__scheduled-tasks__create_scheduled_task` (per spec §10 G7 + v3 §8 Phase G). Calendar entry directive includes v3 NEW: re-calibrate §11.2 thresholds from empirical data.
11. `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/tests/test_pre_commit_ds_gates.sh` (NEW) — pre-commit hook unit tests per spec §13.1. **v3 addition:** include `MN_FRESH=1` test cases.
12. `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/tests/test_ds_gate_workflow.py` (NEW) — CI workflow unit tests per spec §13.1 + §13.5 (v3 NEW trigger-model regression tests TRG1/TRG2/TRG3).
13. Synthetic dry-run PRs for SYNTH1-SYNTH6 per spec §13.2 (test branch `test/ds_23_24_25_gate_dryrun/`).
14. `prod_blockers` PATCH — close `DS_23_MECHANICAL_GATE_PENDING`, `DS_24_MECHANICAL_GATE_PENDING`, `DS_25_MECHANICAL_GATE_PENDING` (per spec §8 Phase F).
15. `prod_blockers` POST — create `DS_24_AST_SIMILARITY_FUTURE_HARDENING_V1` deferred-blocker per spec §14.5.
16. `prod_locked_decisions` POST — LD `DS_23_24_25_MECHANICAL_GATE_V1` per spec §10 G9. LD references v3 spec at `..._v2.md` and notes v2 baseline preservation at `..._v1.md`.
17. `prod_activity_log` POST — go-live row.

**Out of scope (do NOT touch in this session):**

- `MindfulNest/.husky/pre-commit` — RN-app CI/CD must be greenfield per `feedback_main_app_cicd_greenfield_lock.md` from MEMORY.md. Per spec §0.1 #4 + §5.2 OD `DEFER`, this implementation lands ONLY in the tooling repo. (Unchanged from v2 handoff.)
- AST-similarity detection for DS-24 — explicitly future-hardening per spec §0.1 (v2 §0.1) #5.
- Re-litigating DS-23/24/25 rule definitions (locked per LD 580; spec is "given the rules, how do we mechanically enforce them?").
- DS-26 mechanical gate — separate spec, separate handoff (`HANDOFF_DS26_IMPLEMENTATION_20260508.md`).
- DS-19 mechanical gate — discipline-only stays per spec §0.1 (v2 §0.1) #2.
- Re-debating the v3 amendments (Cursor authorized v3; v3 amendments are the implementation target).

---

## §3 Pre-flight (verify before starting Phase A)

### §3.1 Files to read first (anchored citations per HANDOFF_TEMPLATE_v2)

| Anchor target | v3 anchored check |
|---------------|-------------------|
| Spec end-to-end (v3 content) | Read `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v2.md`. Capture line ranges for §0.1 (v3 changelog), §3 (gate locations), §6 (acceptance criteria), §7 (per-rule semantics, INCLUDING §7.3.1.A and §7.3.1.B YAML), §8 (implementation phases, INCLUDING new Phase E.5), §10 (pre-implementation gates), §11.2 + §11.3 (v3-amended), §13 (testing plan, INCLUDING new §13.5 trigger-model regression). Quote one verbatim sentence from §7.3.1.A `on: pull_request` block AND one verbatim sentence from §7.3.1.B `gh api` block to prove read of the v3 trigger-model fix. |
| v2 baseline preservation | `ls -la "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v1.md"` — confirm v2 baseline still exists and mtime predates v3 spec mtime. Do NOT modify. |
| Cursor v3 verdict | Read `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_CURSOR_REVIEW_DS_23_24_25_GATE_SPEC_20260508_v3.md`. Anchor: `## §0.1 v3 Changelog — Cursor amendments applied (HIGH + 4 MED)`. Quote the Q-NEW-1 row of the changelog table verbatim. Confirm verdict text contains `AUTHORIZE_IMPLEMENTATION` (or capture the actual verdict block from the Cursor review session output). |
| DS-23/24/25 + Phase 7.5 Step 6+7 | Read `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/.claude/skills/zero-error-qa/SKILL.md`. Anchors: substrings `DS-23`, `DS-24`, `DS-25`, `Phase 7.5 Step 6`, `Phase 7.5 Step 7`. Capture line ranges for each. Quote the `Swept ` template + the `Adjacent risk sweep on ` template verbatim. |
| Existing pre-commit hook (the APPEND target) | Read `/Users/kimberlysmith/Projects/mindfulnest-tooling/Production/scripts/git_hooks/pre-commit`. Anchors: `BYPASS=` / `OVERRIDE=` / `--no-verify` handling block (whichever matches existing pattern). Capture line range. Quote the matched bypass-block verbatim. |
| Tooling-repo CI workflows (peers) | Read `/Users/kimberlysmith/Projects/mindfulnest-tooling/.github/workflows/codeql.yml`, `ai_review.yml`, `smoke.yml`. Anchors: `on:` trigger blocks. Capture line ranges. Quote one verbatim trigger from each. |
| `workflow_run` precedent (v3 NEW) | Read any existing tooling-repo workflow that uses `on: workflow_run` (search via `grep -l 'workflow_run' /Users/kimberlysmith/Projects/mindfulnest-tooling/.github/workflows/*.yml`). If none exist, document this as Phase B novel-pattern. The v3 spec §7.3.1.B YAML is the canonical example to copy from. |
| Greenfield-lock memory (RN-app boundary) | Read `~/.claude/projects/-Users-kimberlysmith-Library-CloudStorage-Dropbox-Claude-Mindfulnest-Project-Files/memory/project_main_app_cicd_greenfield_lock.md`. Quote the "NEVER inherit" sentence verbatim to prove RN-app deferral acknowledged. |

### §3.2 Conditions to verify

1. Confirm Cursor verdict on the v3 spec is AUTHORIZE_IMPLEMENTATION. Source: Cursor review handoff at `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_CURSOR_REVIEW_DS_23_24_25_GATE_SPEC_20260508_v3.md` final-report block (anchor: Cursor's response after the prompt in `## Step 2` is pasted into Cursor; verdict line should contain `AUTHORIZE_IMPLEMENTATION` per the Cursor review session output captured at handoff close).
2. Confirm `prod_blockers` rows `DS_23_MECHANICAL_GATE_PENDING`, `DS_24_MECHANICAL_GATE_PENDING`, `DS_25_MECHANICAL_GATE_PENDING` are still `open`.
3. Confirm Kim has explicitly approved spec §10 pre-implementation gates G1-G10 via either chat or a `PRE_IMPLEMENTATION_GATES_APPROVED_DS232425` row in `prod_activity_log`. **v3 NOTE:** G2 ("Cursor cross-review verdict") expects v3 verdict (AUTHORIZE_IMPLEMENTATION on v3 content), NOT v2 verdict (AMEND_V2 on v2 content).
4. Confirm `prod_activity_log` schema's `action` field accepts new `DS{23,24,25}_GATE_BYPASSED` AND `DS_FRESH_CONTRIBUTOR_BYPASS` values (per spec §10 G5 schema lock + v3 §11.3 new event type). Query `/fields` if needed; per `feedback_directus_schema_canonical.md` the enum is silently permissive but verify before depending on it.
5. Confirm canonical-root accessibility:
   - `ls -la "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/scripts/git_hooks/pre-commit"` (Dropbox canonical — source-of-truth pre-commit content; this may differ from the tooling repo's working copy)
   - `ls -la "/Users/kimberlysmith/Projects/mindfulnest-tooling/Production/scripts/git_hooks/pre-commit"` (Projects canonical — the actual installed-source path)
   - `ls -la "/Users/kimberlysmith/Projects/mindfulnest-tooling/.github/workflows/"` (CI workflow target)
   - **Note on dual-source:** the tooling repo holds the source-controlled pre-commit; the Dropbox project is the agent-canonical source-of-truth for `Production/scripts/`. Implementation MUST edit the tooling repo's path AND verify the Dropbox project path matches (per the existing Dropbox-edit-gate semantics in the existing pre-commit hook lines 51-69).

---

## §4 HALT gates

**Autonomous mode does not bypass HALT gates per DS-26.** If the gate-check fails, HALT and write a "halted, awaiting authorization" report. Do NOT interpret blanket autonomous-mode authorization as override.

Autonomous mode (LD-232) authorizes execution of documented work without per-step confirmation. HALT gates ARE part of the documented work. Skipping a gate is skipping the procedure, not "trusting the autonomous-mode authorization."

### Gates (must all be MET before Phase A begins)

| # | Gate | Evidence source | Pass criterion | Fail action |
|---|------|------------------|-----------------|-------------|
| 1 | Has Cursor reviewed the v3 spec content and emitted AUTHORIZE_IMPLEMENTATION? | Cursor review handoff final-report block at `Production/docs/HANDOFF_CURSOR_REVIEW_DS_23_24_25_GATE_SPEC_20260508_v3.md` (anchor `## §0.1 v3 Changelog`) AND captured Cursor session output (verdict line) OR `prod_locked_decisions` notes for `DS_23_24_25_DISCIPLINE_STANDARDS_V1` updated post-cursor-review with v3 verdict | At least one such artifact dated ≥ 2026-05-08 with verdict text containing "AUTHORIZE_IMPLEMENTATION" referencing v3 content (NOT v2) | Write `HALTED_AWAITING_AUTHORIZATION` row citing this gate; halt-report; surface |
| 2 | Are spec §10 pre-implementation gates G1-G10 explicitly Kim-approved (with G2 referencing v3)? | Spec §10 itself OR `prod_locked_decisions` notes for `DS_23_24_25_DISCIPLINE_STANDARDS_V1` containing "§10 G1-G10 approved by Kim YYYY-MM-DD on v3 content" OR a `PRE_IMPLEMENTATION_GATES_APPROVED_DS232425_V3` row in `prod_activity_log` | All 10 gates have explicit Kim-approved evidence; G2 references v3 verdict | Write `HALTED_AWAITING_AUTHORIZATION`; halt-report; surface |
| 3 | Has the schema verification (G5) confirmed `prod_activity_log.action` accepts the new `DS{23,24,25}_GATE_BYPASSED` AND `DS_FRESH_CONTRIBUTOR_BYPASS` values? | `/fields` query response captured before Phase A; OR `prod_activity_log` smoke POST + immediate read-back-then-rollback | Enum permissive (silent migration per `feedback_directus_schema_canonical.md`) confirmed via real test write for BOTH event-type families | Write `HALTED_AWAITING_AUTHORIZATION`; halt-report; surface |
| 4 | Are the §13 testing-plan synthetic PR contents pre-authored (G8) — INCLUDING v3 §13.5 TRG1/TRG2/TRG3 trigger-model regression fixtures? | `Production/tests/fixtures/ds_23_24_25/SYNTH1.md` through `SYNTH6.md` exist AND `Production/tests/fixtures/ds_23_24_25/TRG1.md`, `TRG2.md`, `TRG3.md` exist | All 6 synthetic-PR fixture files exist with content matching spec §13.2 AND 3 trigger-regression fixtures match spec §13.5 | Write `HALTED_AWAITING_AUTHORIZATION`; halt-report; surface |
| 5 | Has the RN-app deferral been acknowledged (G6)? | `feedback_main_app_cicd_greenfield_lock.md` has been Read this session AND the implementation does NOT touch `MindfulNest/.husky/` | Read confirmed; touch-set excludes RN-app paths | Write `HALTED_AWAITING_AUTHORIZATION`; halt-report; surface |
| 6 | **v3 NEW** — Has the implementer Read v2 baseline at `..._v1.md` AND confirmed the v3 file at `..._v2.md` differs in §7.3.1 (trigger-model split), §8 (Phase E.5 inserted), §11.2 (threshold tags), §11.3 (MN_FRESH pathway), §14.6 (path audit)? | Diff capture: `diff "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v1.md" "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v2.md" \| head -200` | Diff shows expected §0.1 changelog header + §7.3.1.A/B YAML blocks + Phase E.5 insertion + §11.3 MN_FRESH section + §14.6 audit table; v2 baseline file mtime predates v3 mtime | Write `HALTED_AWAITING_AUTHORIZATION`; halt-report; surface |

If ANY gate fails:
1. Do NOT execute Phase A.
2. Write the `HALTED_AWAITING_AUTHORIZATION` row to `prod_activity_log` with `notes` enumerating which gates failed and citing the evidence search performed.
3. Author the halt-report doc.
4. Emit the Phase 0 Step 2 declaration: `HALT gate scan for HANDOFF_DS23_24_25_IMPLEMENTATION_20260508_v3.md: 6 gate(s) detected, <met> met, <not_met> not met. HALTED.`
5. Surface to Kim and stop.

---

## §5 Sequence

### Phase A — Pre-commit hook extension (DS-23 + DS-24 + MN_FRESH detection) (per spec §8 Phase A + v3 §11.3)

**Deliverable:** `Production/scripts/git_hooks/pre-commit` (canonical source) extended with DS-23 + DS-24 mechanical-check blocks AND `MN_FRESH=1` detection logic.

**Steps:**
1. `ls -la "/Users/kimberlysmith/Projects/mindfulnest-tooling/Production/scripts/git_hooks/pre-commit"` — verify path. Read end-to-end. Anchor: line range of existing watch-list anti-pattern detection block (spec cites lines 104-160; verify by anchor not absolute line number).
2. APPEND the DS-23 block per spec §7.1.1 (sentinel-file pattern, env-var override, security-globs path detection).
3. APPEND the DS-24 block per spec §7.2.1 (handler-shape regex, inline-comment OR sentinel OR override).
4. **v3 NEW:** APPEND the `MN_FRESH=1` detection logic per spec §11.3:
   ```bash
   # MN_FRESH=1 — fresh contributor warning-not-fail pathway (v3 §11.3)
   if [[ "${MN_FRESH:-0}" == "1" ]]; then
       AUTHOR_EMAIL=$(git config user.email)
       FRESH_COMMIT_COUNT=$(git log --author="$AUTHOR_EMAIL" --since='30 days ago' --oneline 2>/dev/null | wc -l)
       if [[ "$FRESH_COMMIT_COUNT" -eq 0 ]]; then
           echo "::warning::MN_FRESH=1 honored — fresh contributor (no commits in last 30 days)"
           echo "::warning::DS-23/24 gates emit warnings only; DS_FRESH_CONTRIBUTOR_BYPASS row will be logged"
           # Set sentinel so downstream DS-23/24 checks downgrade fail→warning
           export MN_FRESH_HONORED=1
       else
           echo "::warning::MN_FRESH=1 set but author has $FRESH_COMMIT_COUNT commits in last 30 days; ignoring"
       fi
   fi
   ```
   Then in DS-23 + DS-24 fail paths, check `${MN_FRESH_HONORED:-0}` and emit warning instead of `exit 1` if set.
5. Update the hook header comment to document `.ds23_sweep` and `.ds24_audit` sentinel files AND `MN_FRESH=1` env var.
6. Edit `.gitignore` to add `.ds23_sweep` and `.ds24_audit` (local-only sentinels).
7. Multipass: re-Read; verify no deletions to existing Dropbox-edit gate (lines 51-69) or watch-list (lines 104-160 anchored).
8. Update `Production/scripts/install_pre_commit_hook.sh` if needed (no changes expected per spec §8 Phase A — installer just copies canonical source).

**Per-step verification:**
- Diff before/after: only ADD lines.
- Existing fail-closed checks unchanged (Dropbox-edit gate + watch-list).
- New DS-23/24 + MN_FRESH blocks are syntactically valid bash (`bash -n` lint).

**Audit-checklist gate at phase-end:**
- [ ] DS-23 block appended verbatim per spec §7.1.1.
- [ ] DS-24 block appended verbatim per spec §7.2.1.
- [ ] `MN_FRESH=1` detection block appended per v3 §11.3.
- [ ] DS-23 + DS-24 fail paths check `MN_FRESH_HONORED` and degrade to warnings when set.
- [ ] No deletions to Dropbox-edit gate or watch-list block.
- [ ] `.gitignore` updated.
- [ ] Multipass Read confirms.

### Phase B — CI workflows (DS-23 + DS-24 unified workflow + DS-25 split per v3 §7.3.1.A/B) (per spec §8 Phase B)

**Deliverable 1 (REQUIRED):** `/Users/kimberlysmith/Projects/mindfulnest-tooling/.github/workflows/ds_23_24_25_gate.yml` (NEW) — workflow with TWO jobs (`ds_23_check`, `ds_24_check`). Note: despite the filename, this v3 file ONLY contains DS-23 + DS-24 jobs. DS-25 lives in separate file(s) per v3 §7.3.1 split.

**Deliverable 2 (REQUIRED — v3 NEW):** `/Users/kimberlysmith/Projects/mindfulnest-tooling/.github/workflows/ds_25_check.yml` (NEW) — DS-25 primary check with `on: pull_request` trigger types `[opened, edited, synchronize, reopened]`, branches `[main]`. Per spec §7.3.1.A.

**Deliverable 3 (OPTIONAL — v3 NEW):** `/Users/kimberlysmith/Projects/mindfulnest-tooling/.github/workflows/ds_25_check_after_codeql.yml` (NEW) — DS-25 secondary check with `on: workflow_run` trigger after CodeQL completes. Per spec §7.3.1.B. Phase B implementer ships this only if they evidence a concrete CodeQL-late-alert scenario worth the extra workflow.

**Steps:**
1. `ls -la "/Users/kimberlysmith/Projects/mindfulnest-tooling/.github/workflows/"` — verify directory. Read peer workflows (codeql.yml, ai_review.yml, smoke.yml) for trigger patterns.
2. Author `ds_23_24_25_gate.yml` with TWO jobs (DS-23 + DS-24 only):
   - `ds_23_check` — `pull_request` trigger, security-globs match, commit-message regex per spec §7.1.2 marker `^Swept .+ for ` + backtick + `.+` + backtick + `:`. CI re-validates audit row when bypass env set. Honors `MN_FRESH_HONORED=1` from helper script (warning-not-fail).
   - `ds_24_check` — `pull_request` trigger, handler-shape regex per spec §7.2.2 (commit-msg `DS-24 audit:` OR inline comment regex `(# |// )Copied .+ pattern from .+:[0-9]+`). Honors `MN_FRESH_HONORED=1`.
3. Author `ds_25_check.yml` per spec §7.3.1.A — primary `pull_request` trigger:
   - Trigger: `on: pull_request: types: [opened, edited, synchronize, reopened] branches: [main]`.
   - Job: `ds_25_check` runs on `ubuntu-latest` with `if: github.event.pull_request.base.ref == 'main'`.
   - Steps: checkout → check if PR touches CodeQL-flagged files (via `gh api code-scanning/alerts?state=open`) → require sweep block in PR body (read `${{ github.event.pull_request.body }}`) → fail if missing OR block <100 chars.
   - Status check name: `ds_25_check` (consistent with §7.3.1.B for branch protection).
4. (OPTIONAL) Author `ds_25_check_after_codeql.yml` per spec §7.3.1.B — secondary `workflow_run` trigger:
   - Trigger: `on: workflow_run: workflows: [CodeQL] types: [completed]`.
   - Job: `ds_25_check_after_codeql` runs on `ubuntu-latest` with `if: ${{ github.event.workflow_run.conclusion == 'success' && github.event.workflow_run.event == 'pull_request' }}`.
   - Steps: checkout → resolve PR number from `head_sha` via `gh api -H "Accept: application/vnd.github+json" /repos/${{ github.repository }}/commits/${HEAD_SHA}/pulls --jq '.[0].number'` → fetch body via `gh pr view "$PR_NUMBER" --json body --jq '.body'` (write to `/tmp/pr_body.txt` for multi-line safety) → check CodeQL scope → require sweep block (read from `/tmp/pr_body.txt`).
   - Status check name: `ds_25_check` (same as §7.3.1.A — branch protection enumerates only one).
   - **CRITICAL — v3 §7.3.1 fix:** This file MUST NOT contain ANY reference to `github.event.pull_request.*`. Verify with `grep -n 'github.event.pull_request' .github/workflows/ds_25_check_after_codeql.yml` — expected: zero matches.
5. Use single workflow (`ds_23_24_25_gate.yml`) for DS-23 + DS-24 per spec §9 OD6 (matches `legacy-file-gate.yml` precedent). DS-25 must be split because the trigger model differs (per v3 §7.3.1).
6. Trigger DS-23 + DS-24 on PRs to `main` AND on push to `claude/*` per spec §9 OD7. DS-25 primary triggers on `pull_request` events ONLY (the canonical event model for PR-body checks).
7. Each job uses `gh` CLI + Directus REST API to validate audit-row presence when `MN_SKIP_*=1` env was set.
8. **v3 NEW:** Each job ALSO checks for `DS_FRESH_CONTRIBUTOR_BYPASS` activity row matching commit SHA + author identity; if found, downgrades fail→warning.

**Per-step verification:**
- All workflow YAML files validate via `gh workflow view` or `actionlint`.
- Job names match spec naming.
- Triggers match spec §3.1 table + §7.3.1.A/B.
- `grep -n 'github.event.pull_request' ds_25_check_after_codeql.yml` returns zero matches (v3 HIGH blocker fix verified).

**Audit-checklist gate at phase-end:**
- [ ] `ds_23_24_25_gate.yml` authored with TWO jobs (DS-23 + DS-24 only — NOT three).
- [ ] `ds_25_check.yml` authored with `on: pull_request` trigger per spec §7.3.1.A.
- [ ] (If shipped) `ds_25_check_after_codeql.yml` authored with `on: workflow_run` trigger per spec §7.3.1.B AND zero references to `github.event.pull_request.*`.
- [ ] Bypass-validation logic queries `prod_activity_log` for `DS{23,24,25}_GATE_BYPASSED` rows.
- [ ] MN_FRESH validation logic queries `prod_activity_log` for `DS_FRESH_CONTRIBUTOR_BYPASS` rows.
- [ ] All workflows validate with `actionlint` or `gh workflow view`.
- [ ] DS-25 primary + secondary use same status check name (`ds_25_check`) so branch-protection rules don't need to enumerate both.

### Phase C — PR template extension (per spec §8 Phase C)

**Deliverable:** `.github/PULL_REQUEST_TEMPLATE.md` extended (or created) with DS-25 Adjacent Risk Sweep section.

**Steps:**
1. `ls -la "/Users/kimberlysmith/Projects/mindfulnest-tooling/.github/"` — confirm whether `PULL_REQUEST_TEMPLATE.md` already exists.
2. If exists: anchor on existing structure; APPEND a new section `## Adjacent Risk Sweep (DS-25 — required if PR closes a CodeQL alert)` with the template block from spec §7.3.1 / SKILL.md DS-25 template lines.
3. If NEW: author full template with the DS-25 section pre-populated.
4. Multipass Read.

**Audit-checklist gate at phase-end:**
- [ ] PR template authored/extended.
- [ ] DS-25 section pre-populated with template per spec.

### Phase D — Bypass-mechanism wiring (per spec §8 Phase D + v3 §11.3 MN_FRESH integration)

**Deliverable 1:** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/RUNBOOK_GATE_BYPASS_MECHANICS.md` (NEW) — bypass documentation INCLUDING `MN_FRESH=1` pathway per v3 §11.3.

**Deliverable 2:** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/scripts/write_gate_bypass_row.py` (NEW) — accepts `--gate DS23|DS24|DS25|FRESH --rationale "<text>" --commit-sha <sha>` and writes to `prod_activity_log` via `try_post_or_queue`. `FRESH` mode writes `DS_FRESH_CONTRIBUTOR_BYPASS` row; other modes write `DS{23,24,25}_GATE_BYPASSED`.

**Steps:**
1. Author the runbook doc covering: `MN_SKIP_DS{23,24,25}_GATE=1` env-var pattern, audit-row pattern, rationale-min-50-chars rule (tagged `[INFERRED — calibrate after Phase G 30-day audit]` per v3 §11.2), weekly-preflight-audit threshold, 30-day FP audit checkpoint, AND `MN_FRESH=1` pathway documentation per v3 §11.3 (eligibility = git author email has <30 days of repo commits; behavior = warning-not-fail; expiry = 30 days OR 5 commits, whichever comes first).
2. Author the `write_gate_bypass_row.py` helper:
   - CLI flags per spec.
   - `--gate FRESH` writes `DS_FRESH_CONTRIBUTOR_BYPASS` row with metadata `{author_email, commit_sha, fresh_commit_count}`.
   - `try_post_or_queue` integration.
   - Validate rationale ≥ 50 chars when `--gate DS23|DS24|DS25` (per spec §11.2 mitigation #1, threshold tagged `[INFERRED]`).
   - For `--gate FRESH`, rationale is optional (the warning is the rationale).
   - Read-back per Rule 35 after POST.
3. CI workflow (Phase B) uses Directus REST API to query `prod_activity_log` filtered by `action=DS{23,24,25}_GATE_BYPASSED` AND metadata.commit_sha matches PR head SHA. ALSO queries for `action=DS_FRESH_CONTRIBUTOR_BYPASS` matching same SHA + author.

**Per-step verification:**
- Helper rejects rationale <50 chars for non-FRESH gates.
- Helper writes row + read-back confirms body.
- Helper accepts `--gate FRESH` without rationale-length check.

**Audit-checklist gate at phase-end:**
- [ ] Runbook doc authored.
- [ ] Helper script authored + tested for all 4 `--gate` values (DS23/DS24/DS25/FRESH).
- [ ] CI bypass-validation queries match helper's row format for both event-type families.

### Phase E.5 — SKILL.md amend (NEW IN V3 — same-day as Phase D ship) (per spec §8 Phase E.5)

**Deliverable:** `.claude/skills/zero-error-qa/SKILL.md` (Dropbox canonical) — flip DS-23/24/25 enforcement labels from "DISCIPLINE-ONLY" to "MECHANICAL". **v3 NEW: this lands the SAME DAY as Phase D, BEFORE Phase E weekly-audit.** Closes the stale-doc window from "Phase D end → Phase F end" (potentially weeks) to "same day as Phase D".

**Steps:**
1. Read the canonical Dropbox SKILL.md path. Anchors: substring `ENFORCEMENT IS DISCIPLINE-ONLY for now` (3 instances — DS-23/DS-24/DS-25). Capture each line range and quote verbatim.
2. Flip each instance to: `ENFORCEMENT IS MECHANICAL via Production/scripts/git_hooks/pre-commit + .github/workflows/ds_23_24_25_gate.yml + .github/workflows/ds_25_check.yml (per Production/docs/DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v2.md, v3 content). Discipline-only fallback retained as belt-and-suspenders for content quality.`
3. Multipass Read.

**Per-step verification:**
- All 3 instances flipped.
- Flipped text references both workflow files (DS-25 lives in its own file per v3).
- Flipped text cites the v3 spec at `..._v2.md` (NOT v1).

**Audit-checklist gate at phase-end:**
- [ ] All 3 DS-23/24/25 enforcement-labels flipped same-day as Phase D.
- [ ] Flipped text references both workflow files (`ds_23_24_25_gate.yml` + `ds_25_check.yml`).
- [ ] Multipass Read confirms.

### Phase E — Weekly preflight audit hook (per spec §8 Phase E + v3 §11.2 threshold tagging)

**Deliverable:** `Production/scripts/weekly_preflight_audit.py` extended with DS-gate bypass-rate audit.

**Steps:**
1. Read `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/scripts/weekly_preflight_audit.py`. Anchor: existing audit-check structure.
2. APPEND a new check: count `DS{23,24,25}_GATE_BYPASSED` rows in last 7 days. **v3 threshold tagging:** if `>3` (TAG: `[INFERRED — calibrate after Phase G 30-day audit per v3 §11.2]`) OR any rationale `<50` chars (TAG: `[INFERRED]`) → write `prod_blockers` row `DS_GATE_BYPASS_THRESHOLD_HIT` with `severity=HARD` per DS-9 / current canonical severity vocab.
3. **v3 NEW:** ALSO count `DS_FRESH_CONTRIBUTOR_BYPASS` rows in last 7 days. If unusually high (say `>5` — also `[INFERRED]`), surface for visibility (no blocker; this is informational — many fresh contributors is healthy contributor onboarding, not abuse).
4. Multipass Read.

**Audit-checklist gate at phase-end:**
- [ ] Audit check appended.
- [ ] Threshold logic matches spec §11.2 mitigation #2 (with v3 [INFERRED] tags).
- [ ] MN_FRESH bypass count surfaced (informational, not blocker).
- [ ] Smoke test: simulate 4 bypass rows; confirm blocker fires.

### Phase F — Blocker row retirement + manual-review commentary update (per spec §8 Phase F, REVISED IN V3)

**Deliverable:** `prod_blockers` row retirement + Phase 7.5 Step 6/7 commentary update in SKILL.md. **v3 NOTE:** SKILL ENFORCEMENT label flip already happened in Phase E.5. Phase F is now ONLY blocker-retirement + Step 6/7 narrative update.

**Steps:**
1. Anchor Phase 7.5 Step 6 + Step 7 in SKILL.md. Amend each: `DS-23/25 mechanical gate now enforces this in CI. Reviewer's role: confirm `ds_23_check` / `ds_25_check` is green in PR checks. Manual inspection retained as belt-and-suspenders for cases where the bypass override fired or MN_FRESH path activated.`
2. Close `prod_blockers` rows: `DS_23_MECHANICAL_GATE_PENDING`, `DS_24_MECHANICAL_GATE_PENDING`, `DS_25_MECHANICAL_GATE_PENDING` via PATCH with `status=closed`, `closure_reason` citing this v3 handoff + v3 spec at `..._v2.md`.
3. Read-back per Rule 35 on each PATCH.
4. Create deferred blocker `DS_24_AST_SIMILARITY_FUTURE_HARDENING_V1` per spec §14.5 (status=deferred, severity=SOFT or current canonical, notes citing future hardening rationale).

**Audit-checklist gate at phase-end:**
- [ ] Phase 7.5 Step 6 + 7 narrative updated (NOT the ENFORCEMENT label — that was Phase E.5).
- [ ] 3 blocker rows closed with read-back proof.
- [ ] Deferred blocker created.

### Phase G — 30-day FP audit calendar entry locked (per spec §8 Phase G + §10 G7 + v3 re-calibration directive)

**Deliverable:** scheduled task in mn-context's scheduled-tasks integration that fires 30 days post-Phase-F completion to run the FP-rate audit AND re-calibrate §11.2 thresholds.

**Steps:**
1. Use `mcp__scheduled-tasks__create_scheduled_task` (NOT a memory note, NOT a TODO) to create the 30-day audit task.
2. Task content: query `prod_activity_log` for count of `DS{23,24,25}_GATE_BYPASSED` rows in last 30 days; query for count of `DS{23,24,25}_GATE_FAILED` rows in last 30 days; query for count of `DS_FRESH_CONTRIBUTOR_BYPASS` rows. Compute bypass:fail ratio.
3. **v3 NEW directive:** the same audit re-calibrates §11.2 thresholds (>3 bypasses/7d, <50 char rationale) using empirical data. If the 30-day data shows the threshold is too tight (legitimate bypasses regularly trigger the alarm) or too loose (abuse goes undetected), the LD `DS_2{3,4,5}_MECHANICAL_GATE_FP_AUDIT_PASS_V1` is amended with calibrated numbers, and §11.2 in the spec amends to reference the LD.
4. Action: if ratio > 0.3, surface `DS_GATE_FP_RATE_REVIEW` blocker to Kim. If acceptable, write `DS_2{3,4,5}_MECHANICAL_GATE_FP_AUDIT_PASS_V1` LD with calibrated thresholds.
5. Capture the scheduled-task id for the final report.

**Audit-checklist gate at phase-end:**
- [ ] Scheduled task created with id captured.
- [ ] Task fires 30 days from Phase F completion.
- [ ] Task content includes v3 re-calibration directive (NOT just the v2 ratio check).

### Phase H — Test cases (per spec §8 + §13 testing plan + v3 §13.5 trigger-model regression)

**Deliverable 1:** `Production/tests/test_pre_commit_ds_gates.sh` (NEW) — pre-commit hook unit tests per spec §13.1, INCLUDING `MN_FRESH=1` test cases per v3 §11.3.

**Deliverable 2:** `Production/tests/test_ds_gate_workflow.py` (NEW) — CI workflow unit tests per spec §13.1 + §13.5 (use `act` local GHA runner OR synthetic PR matrix).

**Deliverable 3:** SYNTH1-SYNTH6 dry-run PRs in test branch `test/ds_23_24_25_gate_dryrun/` per spec §13.2. PRs are NEVER merged; closed with `wontfix` label + activity-log row recording outcome.

**Deliverable 4:** ADV1-ADV4 adversarial tests per spec §13.3.

**Deliverable 5:** end-to-end regression per spec §13.4 (v3-amended for §7.3.1.A/B).

**Deliverable 6 (V3 NEW):** TRG1/TRG2/TRG3 trigger-model regression tests per spec §13.5:
- TRG1: PR opened against `main`. Expected: `ds_25_check.yml` fires on `pull_request:opened`. `github.event.pull_request.body` is non-empty in the workflow logs. PASS = correct trigger model.
- TRG2: CodeQL workflow completes for the same PR. Expected: `ds_25_check_after_codeql.yml` (if shipped) fires on `workflow_run`. The workflow does NOT reference `github.event.pull_request.body` anywhere. PASS = no `github.event.pull_request.*` field reads.
- TRG3: Force-push to the PR. Expected: `pull_request:synchronize` re-fires `ds_25_check.yml`. Sweep block still required.

**Steps:**
1. Author the pre-commit unit-test script with 5+ cases covering spec §13.1 fixtures + 3 MN_FRESH cases (fresh/not-fresh/MN_FRESH-set-but-not-actually-fresh).
2. Author the CI workflow unit-test script (use `act` if available; else synthetic-PR matrix) covering spec §13.1 + v3 §13.5 trigger-model regression.
3. Create test branch `test/ds_23_24_25_gate_dryrun/` and push 6 synthetic PRs (SYNTH1-SYNTH6) + 3 trigger-regression PRs (TRG1-TRG3).
4. Run ADV1-ADV4 adversarial tests; capture each verdict.
5. Run end-to-end regression on a fresh `claude/*` branch with a real (small) security-adjacent change.

**Per-step verification:**
- All §13.1 unit tests pass.
- All §13.2 synthetic PRs produce expected verdicts.
- All §13.3 adversarial tests caught by CI.
- §13.4 regression confirms SKILL.md text now reads "MECHANICAL".
- **v3 NEW:** §13.5 TRG1/TRG2/TRG3 verify trigger-model fix (no v2 regression).

**Audit-checklist gate at phase-end:**
- [ ] Pre-commit unit tests pass (including MN_FRESH cases).
- [ ] CI workflow unit tests pass.
- [ ] Synthetic PRs SYNTH1-SYNTH6 verdict-match per spec §13.2 table.
- [ ] Adversarial tests ADV1-ADV4 caught.
- [ ] **v3:** TRG1/TRG2/TRG3 trigger-model regression tests pass; `grep -n 'github.event.pull_request' ds_25_check_after_codeql.yml` returns zero matches.
- [ ] End-to-end regression passes.

### Phase I — LD POST + activity-log go-live row

**Deliverable:** `prod_locked_decisions` row `DS_23_24_25_MECHANICAL_GATE_V1` per spec §10 G9 + `prod_activity_log` go-live row.

**Steps:**
1. POST `prod_locked_decisions` row with `decision_text` summarizing the implementation, `severity=HARD` (or current canonical), `task_category=governance` (extending canonical per spec §3.3 Rule 3a if approved; else `tech_stack` as fallback). **v3:** decision_text MUST cite spec at `..._v2.md` (v3 content) AND note v2 baseline preservation at `..._v1.md`.
2. POST `prod_activity_log` row with `action=DS_23_24_25_MECHANICAL_GATE_LIVE_V3` and `notes` citing v3 handoff + v3 spec + new LD id + Phase H test-pass summary (including v3 §13.5 trigger-regression results).
3. Read-back per Rule 35 on both.

**Audit-checklist gate at phase-end:**
- [ ] LD posted with id captured; decision_text references v3 spec content.
- [ ] Activity-log row posted with `action=DS_23_24_25_MECHANICAL_GATE_LIVE_V3`.
- [ ] Read-back proofs captured.

---

## §6 Hard rules

- **Per Rule 35:** read-back-after-write for every Directus PATCH/POST. Capture response body verbatim.
- **Multipass:** re-Read every file after Edit. Confirm intended change AND no collateral.
- **Rule 24 confidence tags:** every factual claim in the report tagged CONFIRMED / INFERRED / GUESSED. Per spec §0 §15 confidence sweep. **v3 NEW:** v3 amendments use `[INFERRED — calibrate after Phase G 30-day audit]` for threshold values per spec §11.2 v3 amendment.
- **DS-19 Standing Escape Hatches** active throughout.
- **DS-26 Gate-Check Discipline:** §4 HALT gates above are explicit. If ANY fails mid-execution, STOP and surface. Autonomous mode does NOT bypass.
- **DS-13 Layer 6 smoke:** Phase H's test cases ARE the Layer 6 smoke (input variation → output variation, NOT just compile). **v3:** §13.5 TRG1/TRG2/TRG3 are also Layer 6 smoke for the trigger-model fix.
- **DS-27 absolute-path discipline (refactored 2026-05-08 v2 dual-canonical):** All filesystem-touching commands MUST use absolute paths anchored to one of the two canonical roots: (1) `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/` (primary — Mindfulnest project) OR (2) `/Users/kimberlysmith/Projects/` (secondary — tooling repos, MindfulNest RN app, related repos). This handoff legitimately operates across BOTH canonical roots: tooling repo at `/Users/kimberlysmith/Projects/mindfulnest-tooling/` for pre-commit + CI workflow files (THREE workflow files in v3, not one) + PR template; Dropbox project for runbook + helper script + weekly audit + SKILL.md + tests + Directus writes. Do NOT operate inside `.claude/worktrees/` subdirectories under either root unless explicitly authorized. Verify paths with `ls -la <absolute-path>` before edits.
- **Anchored citation discipline (HANDOFF_TEMPLATE_v2):** every Read pre-flight evidence requirement uses anchored section/header + snippet match, not absolute line number alone. See §3.1 for the citation table.
- **Concise→full escalation:** N/A for implementation handoffs (no concise verdict mode). Documented N/A explicitly per template requirement.
- **Numeric AMEND_V2 thresholds:** N/A for implementation handoffs (no AUTHORIZE/AMEND verdict semantics). Documented N/A explicitly per template requirement.
- **DS-10 APPEND not replace, no globs:** Phase A explicitly APPENDS DS-23/24 + MN_FRESH blocks to existing pre-commit hook (per spec §2.2). NEVER refactor or replace existing watch-list / Dropbox-edit gate.
- **DS-12 atomic phase commits:** each of Phases A-I (10 phases including E.5) ships as its own atomic commit + push (per spec §10 G10). **v3 NEW:** Phase E.5 commit MUST be SAME-DAY as Phase D commit (per spec §8 Phase E.5 stale-doc-window closure).
- **DS-3 fixture pinning:** Phase H fixtures MUST be pinned (not regenerated each run); fixtures live under `Production/tests/fixtures/ds_23_24_25/` and are version-controlled. **v3 NEW:** TRG1-TRG3 trigger-regression fixtures also pinned.
- **Greenfield-lock memory:** the implementation does NOT touch `MindfulNest/.husky/`, `mindfulnest-ios/`, or any RN-app or Expo/EAS path. Verified at §3.2 #4 + §4 gate #5.
- **30-day FP audit:** the calendar entry MUST be created at implementation time (Phase G) — not "we'll remember." Per `feedback_time_estimates.md` from MEMORY.md. **v3 NEW:** calendar entry directive includes re-calibrate §11.2 thresholds.
- **v3 trigger-model invariant:** `ds_25_check_after_codeql.yml` MUST NOT contain ANY reference to `github.event.pull_request.*`. Verify with `grep -n 'github.event.pull_request' .github/workflows/ds_25_check_after_codeql.yml` after Phase B; expected output = zero matches. This is the v2 HIGH blocker (Q-NEW-1) regression check.

---

## §7 Final proof report structure

**Path:** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/DS23_24_25_IMPLEMENTATION_REPORT_<YYYYMMDD>_v3.md`

The report MUST contain, in order:

1. **HALT gate scan results** — per-gate state (MET / NOT MET / N/A) with evidence cited per §4. Phase 0 Step 2 declaration: `HALT gate scan for HANDOFF_DS23_24_25_IMPLEMENTATION_20260508_v3.md: 6 gate(s) detected, <M> met, <K> not met.` (Note: 6 gates in v3, including the new gate #6 — v2 baseline + v3 diff verification.)
2. **Per-phase diff (verbatim)** — Phases A through I (10 phase slots including E.5) code/data changes.
3. **Per-phase audit-checklist results** — gate state at phase-end.
4. **Directus writes** — full POST/PATCH bodies + read-back proofs:
   - 3 `prod_blockers` PATCH closures (Phase F).
   - 1 `prod_blockers` POST deferred-blocker (Phase F).
   - 1 `prod_locked_decisions` POST (Phase I) with new id captured. Decision_text references v3 spec at `..._v2.md`.
   - 1+ `prod_activity_log` POSTs (Phase E.5 SKILL-flip log row, Phase F SKILL Step-6/7 update row, Phase I go-live row, plus Phase H synthetic-PR outcome rows + v3 §13.5 trigger-regression rows).
5. **Phase H test results** — verbatim PASS/FAIL output for §13.1 unit tests (including MN_FRESH cases), §13.2 synthetic PRs SYNTH1-SYNTH6, §13.3 adversarial ADV1-ADV4, §13.4 end-to-end regression, **§13.5 v3 NEW trigger-regression TRG1/TRG2/TRG3**.
6. **30-day calendar entry** — scheduled-task id captured. Task content cites v3 re-calibration directive.
7. **v3 trigger-model regression proof** — `grep -n 'github.event.pull_request' .github/workflows/ds_25_check_after_codeql.yml` output (expected: zero matches). This proves the v2 HIGH blocker (Q-NEW-1) does not regress.
8. **Confidence tags per Rule 24** — every claim tagged CONFIRMED / INFERRED / GUESSED. v3 thresholds tagged `[INFERRED — calibrate after Phase G]`.
9. **Self-classification** — ARCHITECTURAL (governance + CI infra). v3 amendment classification: STANDARD (faithful rendering of GHA event-model semantics; no doctrine change).
10. **Limitations** — what wasn't covered:
    - RN-app `MindfulNest/.husky/` deferred to greenfield session.
    - DS-24 AST-similarity hardening deferred to `DS_24_AST_SIMILARITY_FUTURE_HARDENING_V1` blocker.
    - 30-day FP audit fires later — its outcome is post-this-session.
    - **v3:** if §7.3.1.B `workflow_run` chain is NOT shipped (Phase B implementer judgment), the optional secondary trigger remains future work; the primary `pull_request` trigger is sufficient on its own per spec §7.3.1.
11. **Cross-skill drift** — does this require parallel updates to:
    - zero-error-qa: YES (DS-23/24/25 enforcement labels via Phase E.5 + Phase 7.5 Step 6+7 narrative via Phase F).
    - mn-context: NO.
    - dashboard-gate: NO.
    - tech-spec: NO.

---

## §8 Rollback per phase

| Phase | Rollback procedure | Cost |
|-------|--------------------|------|
| A (pre-commit + MN_FRESH) | `git revert <SHA>` removing the DS-23/24 + MN_FRESH blocks. Existing Dropbox-edit gate + watch-list block remain intact. | Low — single commit. |
| B (CI workflows — 2 or 3 files) | `git rm .github/workflows/ds_23_24_25_gate.yml .github/workflows/ds_25_check.yml [.github/workflows/ds_25_check_after_codeql.yml]` + commit. Branch-protection rule update if any check was made required. | Low if not yet required-check; medium if required (need branch-protection edit). |
| C (PR template) | `git revert` the template change. | Low — 1 line. |
| D (bypass wiring + MN_FRESH integration) | Remove `Production/scripts/write_gate_bypass_row.py` + RUNBOOK doc. Existing audit rows in Directus stay (no historical-row deletion). | Low. |
| **E.5 (SKILL.md amend — NEW IN V3)** | `git revert` the SKILL.md flip; ENFORCEMENT label returns to DISCIPLINE-ONLY. Composes with Phase D rollback: if Phase D is reverted, Phase E.5 SHOULD also be reverted (since the runbook + helper scripts no longer exist), but this is a separate `git revert` (NOT automatic). | Low — 3 line-blocks flipped. |
| E (weekly preflight) | Remove the new check from `Production/scripts/weekly_preflight_audit.py`. | Low. |
| F (blocker retirement + Step 6/7 commentary) | `git revert` the SKILL.md commentary update; PATCH `prod_blockers` rows back to `status=open` with rationale. (Phase E.5 rollback handles ENFORCEMENT label.) | Medium — Directus operations + audit trail. |
| G (30-day audit) | The audit IS the rollback signal — if it fires, follow §11.2 mitigation 3 (downgrade to discipline-only). The scheduled-task itself can be cancelled via `mcp__scheduled-tasks__update_scheduled_task`. | N/A (the audit IS the rollback decision-point). |
| H (tests) | Remove test scripts + fixtures. Synthetic PRs in `test/ds_23_24_25_gate_dryrun/` already labeled `wontfix`; no further action. | Low. |
| I (LD + activity-log) | PATCH `prod_locked_decisions` row `DS_23_24_25_MECHANICAL_GATE_V1` to `status=superseded` with `notes` documenting rollback. POST follow-up `prod_activity_log` row `DS_23_24_25_MECHANICAL_GATE_ROLLED_BACK_V3`. | Medium — Directus operations. |

**Full-spec rollback:** revert Phases A-I (10 phases including E.5) in reverse order: I → H → G → F → E → E.5 → D → C → B → A. Total cost ~30-35 minutes. The audit-trail in `prod_activity_log` is preserved (historical bypass / fail / fresh rows stay) for post-mortem.

**Per spec §11.2 mitigation #3:** if 30-day FP audit shows bypass:fail ratio > 0.3, gate downgrades to discipline-only with documented post-mortem. No future spec re-introduces the gate without first proving the FP root cause is fixed (sunset clause per spec §4.4 Counter residual concern).

---

## §9 Reference index

- **Spec (v3 content, file path `..._v2.md`):** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v2.md`
- **v2 baseline (historical, file path `..._v1.md`):** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v1.md`
- **Cursor review handoff (v3):** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_CURSOR_REVIEW_DS_23_24_25_GATE_SPEC_20260508_v3.md`
- **Cursor review handoff (v2 — historical):** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_CURSOR_REVIEW_DS_23_24_25_GATE_SPEC_20260508_v2.md`
- **Predecessor implementation handoff (v2 — historical):** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_DS23_24_25_IMPLEMENTATION_20260508.md`
- **Authoring template:** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_TEMPLATE_v2.md`
- **Existing pre-commit hook (APPEND target):** `/Users/kimberlysmith/Projects/mindfulnest-tooling/Production/scripts/git_hooks/pre-commit`
- **Tooling-repo CI workflows (peers):** `/Users/kimberlysmith/Projects/mindfulnest-tooling/.github/workflows/codeql.yml`, `ai_review.yml`, `smoke.yml`
- **Legacy-file-gate precedent:** `/Users/kimberlysmith/Projects/MindfulNest/.github/workflows/legacy-file-gate.yml`
- **DS-23/24/25 + Phase 7.5 Step 6+7 SKILL.md:** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/.claude/skills/zero-error-qa/SKILL.md`
- **Greenfield-lock memory:** `~/.claude/projects/-Users-kimberlysmith-Library-CloudStorage-Dropbox-Claude-Mindfulnest-Project-Files/memory/project_main_app_cicd_greenfield_lock.md`
- **Schema-canonical memory:** `~/.claude/projects/-Users-kimberlysmith-Library-CloudStorage-Dropbox-Claude-Mindfulnest-Project-Files/memory/feedback_directus_schema_canonical.md`
- **Authority:** LD `DS_23_24_25_DISCIPLINE_STANDARDS_V1` (LD 580); LD 551 VERBAL_DEFERRAL_TRACKING_REQUIRED_V1 (pattern precedent)
- **Tracking:** `prod_blockers` rows `DS_23_MECHANICAL_GATE_PENDING`, `DS_24_MECHANICAL_GATE_PENDING`, `DS_25_MECHANICAL_GATE_PENDING` (closed at Phase F); `DS_24_AST_SIMILARITY_FUTURE_HARDENING_V1` (deferred-created at Phase F); `DS_GATE_BYPASS_THRESHOLD_HIT` (created at Phase E weekly-audit fire); `DS_GATE_FP_RATE_REVIEW` (created at Phase G 30-day audit if threshold hit)
- **Cross-skill drift surfaces:** zero-error-qa (Phase E.5 + Phase F)
- **CLAUDE.md rules cited:** Rule 19, Rule 24, Rule 35

---

**End of v3 handoff.**
