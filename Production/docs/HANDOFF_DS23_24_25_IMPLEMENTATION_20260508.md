# HANDOFF — DS-23 / DS-24 / DS-25 Mechanical CI Gates Implementation

**Header**

- **Title:** DS-23 / DS-24 / DS-25 Mechanical Gate Implementation (pre-commit + CI)
- **Target session:** Terminal CLI session, executed against canonical tooling-repo path `/Users/kimberlysmith/Projects/mindfulnest-tooling/` AND canonical Dropbox path `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/`. Dual-canonical-root rule per HANDOFF_TEMPLATE_v2 + DS-27 v2.
- **Source spec:** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v1.md`
- **Source session:** gallant-bouman-804b4f worktree (this handoff authored from worktree; implementation runs against canonical paths only).
- **Estimated time:** 6–8 hours machine + ~2 hours Kim review
- **Authority:** LD `DS_23_24_25_DISCIPLINE_STANDARDS_V1` (LD 580), `prod_blockers` rows `DS_23_MECHANICAL_GATE_PENDING` / `DS_24_MECHANICAL_GATE_PENDING` / `DS_25_MECHANICAL_GATE_PENDING`. Cursor verdict: **pending v2.1 path-fix** (parallel agent fixing now). DO NOT begin implementation until Cursor verdict is AUTHORIZE_IMPLEMENTATION on a v-fixed spec.
- **Authoring template:** `Production/docs/HANDOFF_TEMPLATE_v2.md` (mandatory v2 structure).
- **Self-classification:** ARCHITECTURAL (governance + CI/local-hook infrastructure across two surfaces; introduces documented bypass mechanism).

---

## §1 Mission

Convert DS-23, DS-24, DS-25 from discipline-only enforcement into mechanical gates that BLOCK commits and/or merges when violated, per the locked tech spec — DS-23 commit-message regex + helper, DS-24 handler-shape regex + sentinel, DS-25 PR body anchor check (CI-only). Each gate ships with `MN_SKIP_*=1` override env var + `DS{23,24,25}_GATE_BYPASSED` audit-row pattern. 30-day FP audit calendar entry locked at implementation time.

---

## §2 Scope

**Changes in scope (this implementation session):**

1. `/Users/kimberlysmith/Projects/mindfulnest-tooling/Production/scripts/git_hooks/pre-commit` — APPEND DS-23 + DS-24 mechanical-check blocks (per spec §8 Phase A). Per DS-10 "APPEND not replace, no globs."
2. `/Users/kimberlysmith/Projects/mindfulnest-tooling/.github/workflows/ds_23_24_25_gate.yml` (NEW) — CI workflow with three jobs: `ds_23_check`, `ds_24_check`, `ds_25_check` (per spec §8 Phase B + §7 per-rule semantics).
3. `/Users/kimberlysmith/Projects/mindfulnest-tooling/.github/PULL_REQUEST_TEMPLATE.md` — extend (or create) with the DS-25 Adjacent Risk Sweep section per spec §8 Phase C.
4. `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/RUNBOOK_GATE_BYPASS_MECHANICS.md` (NEW) — bypass-mechanism documentation per spec §8 Phase D.
5. `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/scripts/write_gate_bypass_row.py` (NEW) — audit-row writer helper.
6. `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/scripts/weekly_preflight_audit.py` — extend with DS-gate bypass-rate audit (per spec §8 Phase E).
7. `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/.claude/skills/zero-error-qa/SKILL.md` — flip DS-23/24/25 enforcement labels from "DISCIPLINE-ONLY" to "MECHANICAL"; amend Phase 7.5 Step 6 + Step 7 to belt-and-suspenders semantics (per spec §8 Phase F).
8. **30-day FP audit calendar entry** — created at implementation time via `mcp__scheduled-tasks__create_scheduled_task` (per spec §10 G7 lock).
9. `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/tests/test_pre_commit_ds_gates.sh` (NEW) — pre-commit hook unit tests per spec §13.1.
10. `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/tests/test_ds_gate_workflow.py` (NEW) — CI workflow unit tests per spec §13.1.
11. Synthetic dry-run PRs for SYNTH1-SYNTH6 per spec §13.2 (test branch `test/ds_23_24_25_gate_dryrun/`).
12. `prod_blockers` PATCH — close `DS_23_MECHANICAL_GATE_PENDING`, `DS_24_MECHANICAL_GATE_PENDING`, `DS_25_MECHANICAL_GATE_PENDING` (per spec §8 Phase F).
13. `prod_blockers` POST — create `DS_24_AST_SIMILARITY_FUTURE_HARDENING_V1` deferred-blocker per spec §14.5.
14. `prod_locked_decisions` POST — LD `DS_23_24_25_MECHANICAL_GATE_V1` per spec §10 G9.
15. `prod_activity_log` POST — go-live row.

**Out of scope (do NOT touch in this session):**

- `MindfulNest/.husky/pre-commit` — RN-app CI/CD must be greenfield per `feedback_main_app_cicd_greenfield_lock.md` from MEMORY.md. Per spec §0.1 #4 + §5.2 OD `DEFER`, this implementation lands ONLY in the tooling repo.
- AST-similarity detection for DS-24 — explicitly future-hardening per spec §0.1 #5.
- Re-litigating DS-23/24/25 rule definitions (locked per LD 580; spec is "given the rules, how do we mechanically enforce them?").
- DS-26 mechanical gate — separate spec, separate handoff (`HANDOFF_DS26_IMPLEMENTATION_20260508.md`).
- DS-19 mechanical gate — discipline-only stays per spec §0.1 #2.

---

## §3 Pre-flight (verify before starting Phase A)

### §3.1 Files to read first (anchored citations per HANDOFF_TEMPLATE_v2)

| Anchor target | v2 anchored check |
|---------------|-------------------|
| Spec end-to-end | Read `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v1.md`. Capture line ranges for §3 (gate locations), §6 (acceptance criteria), §7 (per-rule semantics), §8 (implementation phases), §10 (pre-implementation gates), §13 (testing plan). Quote one verbatim sentence from each to prove read. |
| DS-23/24/25 + Phase 7.5 Step 6+7 | Read `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/.claude/skills/zero-error-qa/SKILL.md`. Anchors: substrings `DS-23`, `DS-24`, `DS-25`, `Phase 7.5 Step 6`, `Phase 7.5 Step 7`. Capture line ranges for each. Quote the `Swept ` template + the `Adjacent risk sweep on ` template verbatim. |
| Existing pre-commit hook (the APPEND target) | Read `/Users/kimberlysmith/Projects/mindfulnest-tooling/Production/scripts/git_hooks/pre-commit`. Anchors: `BYPASS=` / `OVERRIDE=` / `--no-verify` handling block (whichever matches existing pattern). Capture line range. Quote the matched bypass-block verbatim. |
| Tooling-repo CI workflows (peers) | Read `/Users/kimberlysmith/Projects/mindfulnest-tooling/.github/workflows/codeql.yml`, `ai_review.yml`, `smoke.yml`. Anchors: `on:` trigger blocks. Capture line ranges. Quote one verbatim trigger from each. |
| Greenfield-lock memory (RN-app boundary) | Read `~/.claude/projects/-Users-kimberlysmith-Library-CloudStorage-Dropbox-Claude-Mindfulnest-Project-Files/memory/project_main_app_cicd_greenfield_lock.md`. Quote the "NEVER inherit" sentence verbatim to prove RN-app deferral acknowledged. |

### §3.2 Conditions to verify

1. Confirm Cursor verdict on the DS-23/24/25 spec is AUTHORIZE_IMPLEMENTATION on a v-fixed spec (the v1 path-fix may be a v1.1 or v2 file). Source: Cursor review handoff at `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_CURSOR_REVIEW_DS_23_24_25_GATE_SPEC_20260508_v2.md` final-report block (anchor: `## Final proof report`).
2. Confirm `prod_blockers` rows `DS_23_MECHANICAL_GATE_PENDING`, `DS_24_MECHANICAL_GATE_PENDING`, `DS_25_MECHANICAL_GATE_PENDING` are still `open`.
3. Confirm Kim has explicitly approved spec §10 pre-implementation gates G1-G10 via either chat or a `PRE_IMPLEMENTATION_GATES_APPROVED_DS232425` row in `prod_activity_log`.
4. Confirm `prod_activity_log` schema's `action_type` accepts new `DS{23,24,25}_GATE_BYPASSED` values (per spec §10 G5 schema lock). Query `/fields` if needed; per `feedback_directus_schema_canonical.md` the enum is silently permissive but verify before depending on it.
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
| 1 | Has Cursor reviewed the spec (v1.1 / v2 path-fixed) and emitted AUTHORIZE_IMPLEMENTATION? | Cursor review handoff final-report block at `Production/docs/HANDOFF_CURSOR_REVIEW_DS_23_24_25_GATE_SPEC_20260508_v2.md` (anchor `## Final proof report`) OR `prod_locked_decisions` notes for `DS_23_24_25_DISCIPLINE_STANDARDS_V1` updated post-cursor-review | At least one such artifact dated ≥ 2026-05-08 with verdict text containing "AUTHORIZE_IMPLEMENTATION" | Write `HALTED_AWAITING_AUTHORIZATION` row citing this gate; halt-report; surface |
| 2 | Are spec §10 pre-implementation gates G1-G10 explicitly Kim-approved? | Spec §10 itself OR `prod_locked_decisions` notes for `DS_23_24_25_DISCIPLINE_STANDARDS_V1` containing "§10 G1-G10 approved by Kim YYYY-MM-DD" OR a `PRE_IMPLEMENTATION_GATES_APPROVED_DS232425` row in `prod_activity_log` | All 10 gates have explicit Kim-approved evidence | Write `HALTED_AWAITING_AUTHORIZATION`; halt-report; surface |
| 3 | Has the schema verification (G5) confirmed `prod_activity_log.action_type` accepts the new `DS{23,24,25}_GATE_BYPASSED` values? | `/fields` query response captured before Phase A; OR `prod_activity_log` smoke POST + immediate read-back-then-rollback | Enum permissive (silent migration per `feedback_directus_schema_canonical.md`) confirmed via real test write | Write `HALTED_AWAITING_AUTHORIZATION`; halt-report; surface |
| 4 | Are the §13 testing-plan synthetic PR contents pre-authored (G8)? | `Production/tests/fixtures/ds_23_24_25/SYNTH1.md` through `SYNTH6.md` exist | All 6 synthetic-PR fixture files exist with content matching spec §13.2 | Write `HALTED_AWAITING_AUTHORIZATION`; halt-report; surface |
| 5 | Has the RN-app deferral been acknowledged (G6)? | `feedback_main_app_cicd_greenfield_lock.md` has been Read this session AND the implementation does NOT touch `MindfulNest/.husky/` | Read confirmed; touch-set excludes RN-app paths | Write `HALTED_AWAITING_AUTHORIZATION`; halt-report; surface |

If ANY gate fails:
1. Do NOT execute Phase A.
2. Write the `HALTED_AWAITING_AUTHORIZATION` row to `prod_activity_log` with `notes` enumerating which gates failed and citing the evidence search performed.
3. Author the halt-report doc.
4. Emit the Phase 0 Step 2 declaration: `HALT gate scan for HANDOFF_DS23_24_25_IMPLEMENTATION_20260508.md: 5 gate(s) detected, <met> met, <not_met> not met. HALTED.`
5. Surface to Kim and stop.

---

## §5 Sequence

### Phase A — Pre-commit hook extension (DS-23 + DS-24) (per spec §8 Phase A)

**Deliverable:** `Production/scripts/git_hooks/pre-commit` (canonical source) extended with DS-23 + DS-24 mechanical-check blocks.

**Steps:**
1. `ls -la "/Users/kimberlysmith/Projects/mindfulnest-tooling/Production/scripts/git_hooks/pre-commit"` — verify path. Read end-to-end. Anchor: line range of existing watch-list anti-pattern detection block (spec cites lines 104-160; verify by anchor not absolute line number).
2. APPEND the DS-23 block per spec §7.1.1 (sentinel-file pattern, env-var override, security-globs path detection).
3. APPEND the DS-24 block per spec §7.2.1 (handler-shape regex, inline-comment OR sentinel OR override).
4. Update the hook header comment to document `.ds23_sweep` and `.ds24_audit` sentinel files.
5. Edit `.gitignore` to add `.ds23_sweep` and `.ds24_audit` (local-only sentinels).
6. Multipass: re-Read; verify no deletions to existing Dropbox-edit gate (lines 51-69) or watch-list (lines 104-160 anchored).
7. Update `Production/scripts/install_pre_commit_hook.sh` if needed (no changes expected per spec §8 Phase A — installer just copies canonical source).

**Per-step verification:**
- Diff before/after: only ADD lines.
- Existing fail-closed checks unchanged (Dropbox-edit gate + watch-list).
- New DS-23/24 blocks are syntactically valid bash.

**Audit-checklist gate at phase-end:**
- [ ] DS-23 block appended verbatim per spec §7.1.1.
- [ ] DS-24 block appended verbatim per spec §7.2.1.
- [ ] No deletions to Dropbox-edit gate or watch-list block.
- [ ] `.gitignore` updated.
- [ ] Multipass Read confirms.

### Phase B — CI workflow `ds_23_24_25_gate.yml` (per spec §8 Phase B)

**Deliverable:** `/Users/kimberlysmith/Projects/mindfulnest-tooling/.github/workflows/ds_23_24_25_gate.yml` (NEW) — single workflow, three jobs.

**Steps:**
1. `ls -la "/Users/kimberlysmith/Projects/mindfulnest-tooling/.github/workflows/"` — verify directory. Read peer workflows (codeql.yml, ai_review.yml, smoke.yml) for trigger patterns.
2. Author `ds_23_24_25_gate.yml` with three jobs:
   - `ds_23_check` — `pull_request` trigger, security-globs match, commit-message regex per spec §7.1.2 marker `^Swept .+ for ` + backtick + `.+` + backtick + `:`. CI re-validates audit row when bypass env set.
   - `ds_24_check` — `pull_request` trigger, handler-shape regex per spec §7.2.2 (commit-msg `DS-24 audit:` OR inline comment regex `(# |// )Copied .+ pattern from .+:[0-9]+`).
   - `ds_25_check` — `workflow_run` trigger after CodeQL completes + `pull_request` for body-edit re-trigger; per spec §7.3.1. Block must be ≥100 chars to prevent placeholder per spec §6.2 AF5.
3. Use single workflow with three jobs per spec §9 OD6 (matches `legacy-file-gate.yml` precedent).
4. Trigger on PRs to `main` AND on push to `claude/*` per spec §9 OD7.
5. Each job uses `gh` CLI + Directus REST API to validate audit-row presence when `MN_SKIP_*=1` env was set.

**Per-step verification:**
- Workflow YAML validates via `gh workflow view` or `actionlint`.
- Three job names match spec naming.
- Triggers match spec §3.1 table.

**Audit-checklist gate at phase-end:**
- [ ] Workflow file authored at correct path.
- [ ] Three jobs match spec §7.1.2 / §7.2.2 / §7.3.1.
- [ ] Bypass-validation logic queries `prod_activity_log` for `DS{23,24,25}_GATE_BYPASSED` rows.
- [ ] Workflow validates with `actionlint` or `gh workflow view`.

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

### Phase D — Bypass-mechanism wiring (per spec §8 Phase D)

**Deliverable 1:** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/RUNBOOK_GATE_BYPASS_MECHANICS.md` (NEW) — bypass documentation.

**Deliverable 2:** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/scripts/write_gate_bypass_row.py` (NEW) — accepts `--gate DS23|DS24|DS25 --rationale "<text>" --commit-sha <sha>` and writes to `prod_activity_log` via `try_post_or_queue`.

**Steps:**
1. Author the runbook doc covering: `MN_SKIP_DS{23,24,25}_GATE=1` env-var pattern, audit-row pattern, rationale-min-50-chars rule, weekly-preflight-audit threshold, 30-day FP audit checkpoint.
2. Author the `write_gate_bypass_row.py` helper:
   - CLI flags per spec.
   - `try_post_or_queue` integration.
   - Validate rationale ≥ 50 chars (per spec §11.2 mitigation #1).
   - Read-back per Rule 35 after POST.
3. CI workflow (Phase B) uses Directus REST API to query `prod_activity_log` filtered by `action_type=DS{23,24,25}_GATE_BYPASSED` AND metadata.commit_sha matches PR head SHA.

**Per-step verification:**
- Helper rejects rationale < 50 chars.
- Helper writes row + read-back confirms body.

**Audit-checklist gate at phase-end:**
- [ ] Runbook doc authored.
- [ ] Helper script authored + tested.
- [ ] CI bypass-validation queries match helper's row format.

### Phase E — Weekly preflight audit hook (per spec §8 Phase E)

**Deliverable:** `Production/scripts/weekly_preflight_audit.py` extended with DS-gate bypass-rate audit.

**Steps:**
1. Read `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/scripts/weekly_preflight_audit.py`. Anchor: existing audit-check structure.
2. APPEND a new check: count `DS{23,24,25}_GATE_BYPASSED` rows in last 7 days. If >3 OR any rationale <50 chars → write `prod_blockers` row `DS_GATE_BYPASS_THRESHOLD_HIT` with `severity=HARD` per DS-9 / current canonical severity vocab.
3. Multipass Read.

**Audit-checklist gate at phase-end:**
- [ ] Audit check appended.
- [ ] Threshold logic matches spec §11.2 mitigation #2.
- [ ] Smoke test: simulate 4 bypass rows; confirm blocker fires.

### Phase F — SKILL.md amend (per spec §8 Phase F)

**Deliverable:** `.claude/skills/zero-error-qa/SKILL.md` (Dropbox canonical) — flip DS-23/24/25 enforcement labels + amend Phase 7.5 Step 6 + Step 7 to belt-and-suspenders semantics.

**Steps:**
1. Read the canonical Dropbox SKILL.md path. Anchors: substring `ENFORCEMENT IS DISCIPLINE-ONLY for now` (3 instances — DS-23/DS-24/DS-25). Capture each line range and quote verbatim.
2. Flip each instance to: `ENFORCEMENT IS MECHANICAL via Production/scripts/git_hooks/pre-commit + .github/workflows/ds_23_24_25_gate.yml (per Production/docs/DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v1.md). Discipline-only fallback retained as belt-and-suspenders for content quality.`
3. Anchor Phase 7.5 Step 6 + Step 7. Amend each: `DS-23/25 mechanical gate now enforces this in CI. Reviewer's role: confirm `ds_23_24_25_gate / *` is green in PR checks. Manual inspection retained as belt-and-suspenders for cases where the bypass override fired.`
4. Close `prod_blockers` rows: `DS_23_MECHANICAL_GATE_PENDING`, `DS_24_MECHANICAL_GATE_PENDING`, `DS_25_MECHANICAL_GATE_PENDING` via PATCH with `status=closed`, `closure_reason` citing this handoff + spec.
5. Read-back per Rule 35 on each PATCH.
6. Create deferred blocker `DS_24_AST_SIMILARITY_FUTURE_HARDENING_V1` per spec §14.5 (status=deferred, severity=SOFT or current canonical, notes citing future hardening rationale).

**Audit-checklist gate at phase-end:**
- [ ] All 3 DS-23/24/25 enforcement-labels flipped.
- [ ] Phase 7.5 Step 6 + 7 amended.
- [ ] 3 blocker rows closed with read-back proof.
- [ ] Deferred blocker created.

### Phase G — 30-day FP audit calendar entry locked (per spec §8 Phase G + §10 G7)

**Deliverable:** scheduled task in mn-context's scheduled-tasks integration that fires 30 days post-Phase-F completion to run the FP-rate audit.

**Steps:**
1. Use `mcp__scheduled-tasks__create_scheduled_task` (NOT a memory note, NOT a TODO) to create the 30-day audit task.
2. Task content: query `prod_activity_log` for count of `DS{23,24,25}_GATE_BYPASSED` rows in last 30 days; query for count of `DS{23,24,25}_GATE_FAILED` rows in last 30 days. Compute bypass:fail ratio.
3. Action: if ratio > 0.3, surface `DS_GATE_FP_RATE_REVIEW` blocker to Kim. If acceptable, write `DS_2{3,4,5}_MECHANICAL_GATE_FP_AUDIT_PASS_V1` LD.
4. Capture the scheduled-task id for the final report.

**Audit-checklist gate at phase-end:**
- [ ] Scheduled task created with id captured.
- [ ] Task fires 30 days from Phase F completion.

### Phase H — Test cases (per spec §8 + §13 testing plan)

**Deliverable 1:** `Production/tests/test_pre_commit_ds_gates.sh` (NEW) — pre-commit hook unit tests per spec §13.1.

**Deliverable 2:** `Production/tests/test_ds_gate_workflow.py` (NEW) — CI workflow unit tests per spec §13.1 (use `act` local GHA runner OR synthetic PR matrix).

**Deliverable 3:** SYNTH1-SYNTH6 dry-run PRs in test branch `test/ds_23_24_25_gate_dryrun/` per spec §13.2. PRs are NEVER merged; closed with `wontfix` label + activity-log row recording outcome.

**Deliverable 4:** ADV1-ADV4 adversarial tests per spec §13.3.

**Deliverable 5:** end-to-end regression per spec §13.4.

**Steps:**
1. Author the pre-commit unit-test script with 5+ cases covering spec §13.1 fixtures.
2. Author the CI workflow unit-test script (use `act` if available; else synthetic-PR matrix).
3. Create test branch `test/ds_23_24_25_gate_dryrun/` and push 6 synthetic PRs (SYNTH1-SYNTH6).
4. Run ADV1-ADV4 adversarial tests; capture each verdict.
5. Run end-to-end regression on a fresh `claude/*` branch with a real (small) security-adjacent change.

**Per-step verification:**
- All §13.1 unit tests pass.
- All §13.2 synthetic PRs produce expected verdicts.
- All §13.3 adversarial tests caught by CI.
- §13.4 regression confirms SKILL.md text now reads "MECHANICAL".

**Audit-checklist gate at phase-end:**
- [ ] Pre-commit unit tests pass.
- [ ] CI workflow unit tests pass.
- [ ] Synthetic PRs SYNTH1-SYNTH6 verdict-match per spec §13.2 table.
- [ ] Adversarial tests ADV1-ADV4 caught.
- [ ] End-to-end regression passes.

### Phase I — LD POST + activity-log go-live row

**Deliverable:** `prod_locked_decisions` row `DS_23_24_25_MECHANICAL_GATE_V1` per spec §10 G9 + `prod_activity_log` go-live row.

**Steps:**
1. POST `prod_locked_decisions` row with `decision_text` summarizing the implementation, `severity=HARD` (or current canonical), `task_category=governance` (extending canonical per spec §3.3 Rule 3a if approved; else `tech_stack` as fallback).
2. POST `prod_activity_log` row with action `DS_23_24_25_MECHANICAL_GATE_LIVE` and `notes` citing handoff + spec + new LD id + Phase H test-pass summary.
3. Read-back per Rule 35 on both.

**Audit-checklist gate at phase-end:**
- [ ] LD posted with id captured.
- [ ] Activity-log row posted.
- [ ] Read-back proofs captured.

---

## §6 Hard rules

- **Per Rule 35:** read-back-after-write for every Directus PATCH/POST. Capture response body verbatim.
- **Multipass:** re-Read every file after Edit. Confirm intended change AND no collateral.
- **Rule 24 confidence tags:** every factual claim in the report tagged CONFIRMED / INFERRED / GUESSED. Per spec §0 §15 confidence sweep.
- **DS-19 Standing Escape Hatches** active throughout.
- **DS-26 Gate-Check Discipline:** §4 HALT gates above are explicit. If ANY fails mid-execution, STOP and surface. Autonomous mode does NOT bypass.
- **DS-13 Layer 6 smoke:** Phase H's test cases ARE the Layer 6 smoke (input variation → output variation, NOT just compile).
- **DS-27 absolute-path discipline (refactored 2026-05-08 v2 dual-canonical):** All filesystem-touching commands MUST use absolute paths anchored to one of the two canonical roots: (1) `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/` (primary — Mindfulnest project) OR (2) `/Users/kimberlysmith/Projects/` (secondary — tooling repos, MindfulNest RN app, related repos). This handoff legitimately operates across BOTH canonical roots: tooling repo at `/Users/kimberlysmith/Projects/mindfulnest-tooling/` for pre-commit + CI workflow + PR template; Dropbox project for runbook + helper script + weekly audit + SKILL.md + tests + Directus writes. Do NOT operate inside `.claude/worktrees/` subdirectories under either root unless explicitly authorized. Verify paths with `ls -la <absolute-path>` before edits.
- **Anchored citation discipline (HANDOFF_TEMPLATE_v2):** every Read pre-flight evidence requirement uses anchored section/header + snippet match, not absolute line number alone. See §3.1 for the citation table.
- **Concise→full escalation:** N/A for implementation handoffs (no concise verdict mode). Documented N/A explicitly per template requirement.
- **Numeric AMEND_V2 thresholds:** N/A for implementation handoffs (no AUTHORIZE/AMEND verdict semantics). Documented N/A explicitly per template requirement.
- **DS-10 APPEND not replace, no globs:** Phase A explicitly APPENDS DS-23/24 blocks to existing pre-commit hook (per spec §2.2). NEVER refactor or replace existing watch-list / Dropbox-edit gate.
- **DS-12 atomic phase commits:** each of Phases A-I ships as its own atomic commit + push (per spec §10 G10).
- **DS-3 fixture pinning:** Phase H fixtures MUST be pinned (not regenerated each run); fixtures live under `Production/tests/fixtures/ds_23_24_25/` and are version-controlled.
- **Greenfield-lock memory:** the implementation does NOT touch `MindfulNest/.husky/`, `mindfulnest-ios/`, or any RN-app or Expo/EAS path. Verified at §3.2 #4 + §4 gate #5.
- **30-day FP audit:** the calendar entry MUST be created at implementation time (Phase G) — not "we'll remember." Per `feedback_time_estimates.md` from MEMORY.md.

---

## §7 Final proof report structure

**Path:** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/DS23_24_25_IMPLEMENTATION_REPORT_<YYYYMMDD>.md`

The report MUST contain, in order:

1. **HALT gate scan results** — per-gate state (MET / NOT MET / N/A) with evidence cited per §4. Phase 0 Step 2 declaration: `HALT gate scan for HANDOFF_DS23_24_25_IMPLEMENTATION_20260508.md: 5 gate(s) detected, <M> met, <K> not met.`
2. **Per-phase diff (verbatim)** — Phases A through I code/data changes.
3. **Per-phase audit-checklist results** — gate state at phase-end.
4. **Directus writes** — full POST/PATCH bodies + read-back proofs:
   - 3 `prod_blockers` PATCH closures (Phase F).
   - 1 `prod_blockers` POST deferred-blocker (Phase F).
   - 1 `prod_locked_decisions` POST (Phase I) with new id captured.
   - 1+ `prod_activity_log` POSTs (Phases F, I, plus Phase H synthetic-PR outcome rows).
5. **Phase H test results** — verbatim PASS/FAIL output for §13.1 unit tests, §13.2 synthetic PRs SYNTH1-SYNTH6, §13.3 adversarial ADV1-ADV4, §13.4 end-to-end regression.
6. **30-day calendar entry** — scheduled-task id captured.
7. **Confidence tags per Rule 24** — every claim tagged CONFIRMED / INFERRED / GUESSED.
8. **Self-classification** — ARCHITECTURAL.
9. **Limitations** — what wasn't covered:
   - RN-app `MindfulNest/.husky/` deferred to greenfield session.
   - DS-24 AST-similarity hardening deferred to `DS_24_AST_SIMILARITY_FUTURE_HARDENING_V1` blocker.
   - 30-day FP audit fires later — its outcome is post-this-session.
10. **Cross-skill drift** — does this require parallel updates to:
    - zero-error-qa: YES (DS-23/24/25 enforcement labels + Phase 7.5 Step 6+7).
    - mn-context: NO.
    - dashboard-gate: NO.
    - tech-spec: NO.

---

## §8 Rollback per phase

| Phase | Rollback procedure | Cost |
|-------|--------------------|------|
| A (pre-commit) | `git revert <SHA>` removing the DS-23/24 blocks. Existing Dropbox-edit gate + watch-list block remain intact. | Low — single commit. |
| B (CI workflow) | `git rm .github/workflows/ds_23_24_25_gate.yml` + commit. Branch-protection rule update if check was made required. | Low if not yet required-check; medium if required (need branch-protection edit). |
| C (PR template) | `git revert` the template change. | Low — 1 line. |
| D (bypass wiring) | Remove `Production/scripts/write_gate_bypass_row.py` + RUNBOOK doc. Existing audit rows in Directus stay (no historical-row deletion). | Low. |
| E (weekly preflight) | Remove the new check from `Production/scripts/weekly_preflight_audit.py`. | Low. |
| F (SKILL.md amend) | `git revert` the SKILL.md amend; flip ENFORCEMENT label back to DISCIPLINE-ONLY. PATCH `prod_blockers` rows back to `status=open` with rationale. | Medium — Directus operations + audit trail. |
| G (30-day audit) | The audit IS the rollback signal — if it fires, follow §11.2 mitigation 3 (downgrade to discipline-only). The scheduled-task itself can be cancelled via `mcp__scheduled-tasks__update_scheduled_task`. | N/A (the audit IS the rollback decision-point). |
| H (tests) | Remove test scripts + fixtures. Synthetic PRs in `test/ds_23_24_25_gate_dryrun/` already labeled `wontfix`; no further action. | Low. |
| I (LD + activity-log) | PATCH `prod_locked_decisions` row `DS_23_24_25_MECHANICAL_GATE_V1` to `status=superseded` with `notes` documenting rollback. POST follow-up `prod_activity_log` row `DS_23_24_25_MECHANICAL_GATE_ROLLED_BACK`. | Medium — Directus operations. |

**Full-spec rollback:** revert Phases A-I in reverse order. Total cost ~30 minutes. The audit-trail in `prod_activity_log` is preserved (historical bypass / fail rows stay) for post-mortem.

**Per spec §11.2 mitigation #3:** if 30-day FP audit shows bypass:fail ratio > 0.3, gate downgrades to discipline-only with documented post-mortem. No future spec re-introduces the gate without first proving the FP root cause is fixed (sunset clause per spec §4.4 Counter residual concern).

---

## §9 Reference index

- **Spec:** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v1.md`
- **Cursor review handoff (v2):** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_CURSOR_REVIEW_DS_23_24_25_GATE_SPEC_20260508_v2.md`
- **Authoring template:** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_TEMPLATE_v2.md`
- **Existing pre-commit hook (APPEND target):** `/Users/kimberlysmith/Projects/mindfulnest-tooling/Production/scripts/git_hooks/pre-commit`
- **Tooling-repo CI workflows (peers):** `/Users/kimberlysmith/Projects/mindfulnest-tooling/.github/workflows/codeql.yml`, `ai_review.yml`, `smoke.yml`
- **DS-23/24/25 + Phase 7.5 Step 6+7 SKILL.md:** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/.claude/skills/zero-error-qa/SKILL.md`
- **Greenfield-lock memory:** `~/.claude/projects/-Users-kimberlysmith-Library-CloudStorage-Dropbox-Claude-Mindfulnest-Project-Files/memory/project_main_app_cicd_greenfield_lock.md`
- **Schema-canonical memory:** `~/.claude/projects/-Users-kimberlysmith-Library-CloudStorage-Dropbox-Claude-Mindfulnest-Project-Files/memory/feedback_directus_schema_canonical.md`
- **Authority:** LD `DS_23_24_25_DISCIPLINE_STANDARDS_V1` (LD 580); LD 551 VERBAL_DEFERRAL_TRACKING_REQUIRED_V1 (pattern precedent)
- **Tracking:** `prod_blockers` rows `DS_23_MECHANICAL_GATE_PENDING`, `DS_24_MECHANICAL_GATE_PENDING`, `DS_25_MECHANICAL_GATE_PENDING` (closed at Phase F); `DS_24_AST_SIMILARITY_FUTURE_HARDENING_V1` (deferred-created at Phase F); `DS_GATE_BYPASS_THRESHOLD_HIT` (created at Phase E weekly-audit fire); `DS_GATE_FP_RATE_REVIEW` (created at Phase G 30-day audit if threshold hit)
- **Cross-skill drift surfaces:** zero-error-qa
- **CLAUDE.md rules cited:** Rule 19, Rule 24, Rule 35

---

**End of handoff.**
