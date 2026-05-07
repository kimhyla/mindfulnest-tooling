# Storyboard v59 — Retroactive Coverage Sprint Spec v1

**Date:** 2026-05-04
**Classification:** TESTS-ONLY SPRINT — no fixes; bugs found get logged as follow-ups
**Predecessor (HARD GATE):** S5.5c+e proper-fix session ALL 20 GATES GREEN; CI live
**Successor:** Whatever bug-fix session(s) tackle the issues this sprint surfaces, then S5.5f
**Working tree:** `~/Projects/mindfulnest-tooling/` (CI-bound; same as proper-fix)

## §1 Why this session exists

S5.5d (v3 architecture revision), S5.5c+e (Beat Generator + Storyboard buttons + Production Map), and the underlying state-machine work all shipped before mandatory Playwright e2e was a CI gate. Cursor v9 named the pattern: "server-only gates without e2e on critical paths." The proper-fix session caught and fixed 5 bugs in c+e via browser smoke + new e2e tests, but the rest of the prior-shipped surface area has unknown Playwright coverage. Statistically, more integration bugs lurk.

This session **adds retroactive Playwright coverage** for the highest-risk untested surfaces — without fixing anything. Bugs surfaced are deferred to dedicated fix sessions. Mixing test-writing with bug-fixing in one session reproduces the very coupling pattern that produced this debt.

## §2 Hard rules

| # | Rule | Why |
|---|---|---|
| 1 | **TESTS ONLY.** No code changes outside `e2e/`. No bug fixes. | Decouples discovery from repair. Mixing them produces "scope eats the universe" sessions. |
| 2 | **TIME-BOXED 3 HOURS HARD CAP.** | Prevents "audit-the-universe" creep that Cursor v11 warned against. |
| 3 | **Bugs found → log + quarantine + continue.** Mark the test `test.fixme` with a comment block linking the bug log row; write `prod_activity_log` action `BUG_FOUND_IN_RETROACTIVE_COVERAGE` + a `prod_blockers` row; do NOT diagnose deeply, do NOT propose fixes inline. | Diagnostic depth is the next session's job. |
| 4 | **Tests must use `Production/Event_e2e_fixture/`** (created in proper-fix Phase 1.3) — never `Event_1`/`Event_2`. | Per proper-fix §17 fixture pinning. |
| 5 | **Critical-path tests NEVER quarantined.** R1-R5 + +NewEvent stay green. New retroactive tests CAN be quarantined per Rule 3 above. | Proper-fix §16 flake governance. |
| 6 | **Per Rule 19: no shortcuts.** No "we'll add tests later for THIS one too." | The whole sprint exists because that pattern produced the debt. |

## §3 Scope — 6 prioritized surfaces

Ordered by risk × effort. The 3-hour box may not cover all 6; that's fine. Stop at the time-box, log what's done, defer rest to a follow-up coverage sprint v2 if Kim wants.

### S1 — Beat lifecycle state machine (HIGHEST risk, ~30 min)
- Per LD `BEAT_LIFECYCLE_STATE_MACHINE_V1` (S5.5e)
- Test transitions: created → option_set → option_locked → finalized → unlock → re-edit
- Test guard rails: can a beat skip states? does the radio actually persist? does unlock clear the lock?
- Reference: `BgTab.tsx` beat row controls; `production_server.py` `_handle_bg_finalize_beat`, `_handle_bg_unlock_beat`

### S2 — pathappPatch mutation channel coverage (~25 min)
- Per LD-456 / Rule 36 PATCH_INVARIANT_PERSISTENCE_V1
- Test that mutations through `pathappPatch` actually persist (read-back from state.json) for: bg_set_option, bg_accept_option, bg_finalize, bg_unlock, scope_change, milestone_create
- Spot-check that bypassing pathappPatch (raw fetch) is impossible — search src/ for raw fetch to /api endpoints

### S3 — StoryboardTab refresh logic beyond R1 (~25 min)
- R1 covered scope-change re-fetch. Other refresh triggers untested:
  - After bg_finalize_beat completes → does StoryboardTab beat list refresh?
  - After bg_unlock → does StoryboardTab show updated state?
  - After option lock → does the beat row reflect immediately?
- Reference: `StoryboardTab.tsx` `refreshTick` bumps + dep effects

### S4 — Magic compositor invocation from BgTab (~25 min)
- BgTab triggers magic compositor for beats with magic intent (Tessa's voice etc.)
- Test: trigger magic on a fixture beat → POST `/api/magic/run` → poll status → result registered
- Test: magic running concurrent with bg_finalize → does drain protocol prevent race?
- Reference: `BgTab.tsx` magic button + `production_server.py` `_handle_magic_*`

### S5 — AssetTile/library rendering edge cases (~25 min)
- R5 covered tile width. Untested:
  - Library with 0 items → empty state visible
  - Library with 100+ items → scroll works; no DOM perf collapse
  - Tile click vs drag (mouse-up vs drag-end) — discrimination
  - Library category filter (if exists) — switching filters refreshes
- Reference: `LibraryPanel.tsx`, `AssetTile.tsx`

### S6 — ProjectSelector + scope boundary integration (~20 min)
- Switching from Event_1 to Event_2 mid-session — does scope leak? (Event_2 magic test)
- Switching from event scope to milestone scope — does Phase A/B tab visibility correctly toggle?
- Switching from milestone back to event — does scope correctly restore?
- Reference: `ProjectSelector.tsx`, `ScopeBoundary.tsx`, scope.ts signals

### §3.7 If time remains after S1-S6 (unlikely):
- Cropper modal canvas behavior beyond drag-drop
- TabBar tab switch state preservation
- Toast / Spinner / Modal primitive behavior under unusual conditions

## §4 Phases

### Phase 0 — Pre-flight (10 min)
- Verify proper-fix session shipped: query `prod_activity_log` for `S5_5CE_PROPER_FIX_COMPLETE`; if missing, ABORT
- Verify CI workflow `.github/workflows/playwright_e2e.yml` is live and was green on the last main commit
- Verify `Production/Event_e2e_fixture/` exists in this tree (created by proper-fix Phase 1.3)
- `prod_preflight_reviews` row task_id="retroactive-coverage-sprint-20260504"; reference proper-fix preflight as predecessor
- Read CRITICAL: §2 hard rules; §3 surface list

### Phase 1 — Discovery audit (15 min)
- For each surface S1-S6: grep existing `e2e/*.spec.ts` for related test cases. List what's already covered.
- Output `/tmp/retroactive_coverage_audit.md` with: surface | existing tests | gap

### Phase 2 — Prioritize within time-box (5 min)
- Compute remaining time after Phase 0+1. Allocate per-surface time budget.
- If one surface looks like it'll take much longer than estimate, drop a lower-priority surface.

### Phase 3 — Write tests (~120 min total, distributed across surfaces)
- One spec file per surface: `e2e/retroactive_<surface>.spec.ts`
- Each test follows the proper-fix pattern: scope setup → action → assert
- Use the fixture; no Event_1/Event_2 mutation
- After each spec file: run locally to confirm pass/fail. Capture results.

### Phase 4 — Bug logging (per Rule 3) — interleaved with Phase 3
- Each test that goes RED on first run despite covering existing-and-presumed-working behavior:
  - Mark `test.fixme` with comment block: `// FIXME: bug discovered retroactive 2026-05-04 / log row id <X> / surface <Sn>`
  - Write `prod_activity_log` row action="BUG_FOUND_IN_RETROACTIVE_COVERAGE", details={surface, test_name, brief_repro, expected, actual}
  - Write `prod_blockers` row severity=HIGH, blocked_action="<surface description>", reference to activity row
  - DO NOT diagnose root cause. DO NOT propose fix.
- Each test that goes GREEN: confirms surface working; commit it.

### Phase 5 — CI verification (10 min)
- Push to `claude/retroactive-coverage-sprint` branch
- Verify CI runs all new tests; non-quarantined ones green; quarantined ones skipped (not red)
- If CI red on a non-quarantined test: that's a flake or your green-locally test is actually broken. Diagnose; if flake, retry once; if not flake, re-mark as quarantined per Rule 3.

### Phase 6 — Closeout (15 min)
- Write `Production/docs/RETROACTIVE_COVERAGE_RESULTS_V1.md` (Dropbox tree) with:
  - Surfaces covered (which of S1-S6 + ~ how many tests each)
  - Tests landed green (count + list)
  - Tests quarantined as bugs (count + activity_log row IDs + brief repro one-liners)
  - Time spent vs 3-hour box
  - Recommendations for next session(s) — usually "fix the quarantined tests" + which to prioritize
- Write LD `RETROACTIVE_COVERAGE_SPRINT_V1_COMPLETE` (HIGH) with summary
- `prod_activity_log` action `RETROACTIVE_COVERAGE_SPRINT_COMPLETE` with full report
- Update `STORYBOARD_V59_FEATURE_PARITY_MASTER_OVERVIEW.md` status table
- Single git commit + push: `Retroactive coverage sprint — N tests added, M bugs surfaced (deferred for fix)`
- gh pr create (audit trail)

## §5 Verification gates

| Gate | Check |
|---|---|
| G1 | Proper-fix `S5_5CE_PROPER_FIX_COMPLETE` activity row found and verified |
| G2 | `Production/Event_e2e_fixture/` exists; tests use it |
| G3 | At least 1 test landed for each of S1-S6 (or surface explicitly skipped per time-box, logged) |
| G4 | Every red-on-first-run test has matching `prod_activity_log` BUG_FOUND row + `test.fixme` quarantine |
| G5 | No production code (`src/`, `production_server.py`, `lib/`) modified — `git diff main -- :^e2e :^Production/docs` is empty |
| G6 | CI run on the branch is green (or only quarantined tests are skipped) |
| G7 | Results doc exists in Dropbox |
| G8 | LD + activity + master overview updates registered |

## §6 Escape hatches (HALT + surface)

| Trigger | Action |
|---|---|
| Proper-fix session not yet complete (G1 fail) | ABORT immediately; Kim hasn't told you to start yet |
| Time-box approaching with surfaces still to cover | STOP at time-box; document what's deferred; do NOT extend |
| A test surfaces what looks like a CRITICAL bug (data loss, state corruption, security) | Log per Rule 3 AND surface to Kim immediately with severity flagged |
| 5+ bugs surfaced in first hour | Pause; surface to Kim — coverage sprint is finding more than expected; she may want to redirect to fix-mode session instead |
| Fixture data missing or wrong shape for a planned test | Skip that test; log; do NOT amend fixture (that's proper-fix territory) |
| You catch yourself wanting to fix something | STOP. Re-read §2 Rule 1. Add the test, mark fixme, move on. |
| Anything triggering Rule 26 Opus Escalation | Surface |

## §7 Files modified

### Created
- `~/Projects/mindfulnest-tooling/Production/tools/storyboard-v2/e2e/retroactive_<surface>.spec.ts` (up to 6 files)
- `Production/docs/RETROACTIVE_COVERAGE_RESULTS_V1.md` (Dropbox)

### NOT modified
- Any production code (`src/`, `production_server.py`, `lib/`, `scripts/`, etc.)
- Existing e2e specs (smoke, behavioral-parity, rollback, touchpoint-a, s5_5ce_proper_fix)
- Fixture data
- Spec docs other than master overview status table

### Directus
- `prod_locked_decisions`: 1 NEW LD
- `prod_preflight_reviews`: 1 row
- `prod_activity_log`: phase rows + COMPLETE + per-bug rows
- `prod_blockers`: 1 row per bug found

## §8 Out of scope (defer)

- Fixing any bug surfaced
- Adding fixture data for new test scenarios
- Refactoring existing tests
- Coverage sprints for additional surfaces beyond S1-S6 in this session
- Rewriting tests in different framework
- Visual regression testing

## §9 Notes for the executing session

- This session is **bounded discipline**, not feature work. The hard rules in §2 are the load-bearing piece.
- **The instinct to fix a bug when you see it is wrong here.** That instinct is exactly what produced the debt this session is paying down. Resist; log; move on.
- **Time-box is real.** If at 2h45m you've covered S1-S3 and not started S4-S6, STOP at 3h00m and document. Don't sprint to 4 hours.
- **Bugs found are not failures of this session.** The session SUCCEEDS by surfacing them. If you find 0 bugs, that's also success — confidence increases.
- Per zero-error-qa: multipass at every phase boundary; read-back Directus writes; surface blockers; no shortcuts.

---

**End of Retroactive Coverage Sprint Spec v1.**
