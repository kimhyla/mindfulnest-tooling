# Retroactive Coverage Sprint v1 — Results

**Date:** 2026-05-04
**Spec:** `Production/docs/STORYBOARD_V59_RETROACTIVE_COVERAGE_SPEC_v1.md`
**Branch:** `claude/retroactive-coverage-sprint`
**Worktree:** `~/Projects/mindfulnest-tooling-retro/`
**Predecessor:** S5.5c+e proper-fix complete (`prod_activity_log` id=1494, `prod_preflight_reviews` id=201, PR #1 merged 2026-05-04T12:04:06Z, LDs 506-510)
**This session preflight:** `prod_preflight_reviews` id=202 (task_id `retroactive-coverage-sprint-20260504`)
**CI runs:**
- First run [25318767660](https://github.com/kimhyla/mindfulnest-tooling/actions/runs/25318767660) — RED proof: 52 pass / 2 fail (S4.6 yaml import + R1.1 pollution from S6.7)
- Second run [25319006667](https://github.com/kimhyla/mindfulnest-tooling/actions/runs/25319006667) — **GREEN: 54/54 passed in 39.5s**

## Summary

Tests-only retroactive Playwright coverage sprint for the 6 prioritized surfaces from §3 of the spec. **41 new tests across 6 spec files** landed and all green in CI alongside the 13 proper-fix R-tests = **54/54 passing**. **Zero production code modifications** (G5 verified — `git diff main -- :^Production/tools/storyboard-v2/e2e :^.github/workflows :^Production/docs` empty).

Per Kim's session-start update, the original 3-hour cap was lifted. Substantive stop-signals (per-surface bloat → drop a lower-priority surface; 5+ bugs in early going → surface to Kim; critical bug → surface immediately) governed instead. None triggered.

## Surfaces covered (G3)

| # | Surface | Tests | Spec file |
|---|---------|-------|-----------|
| S1 | Beat lifecycle state machine | 8 | `e2e/retroactive_s1_beat_lifecycle.spec.ts` |
| S2 | pathappPatch mutation channel | 6 | `e2e/retroactive_s2_pathapp_patch.spec.ts` |
| S3 | StoryboardTab refresh logic | 4 | `e2e/retroactive_s3_storyboard_refresh.spec.ts` |
| S4 | Magic compositor | 8 | `e2e/retroactive_s4_magic_compositor.spec.ts` |
| S5 | Library rendering edge cases | 7 | `e2e/retroactive_s5_library_rendering.spec.ts` |
| S6 | ProjectSelector + ScopeBoundary | 8 | `e2e/retroactive_s6_scope_boundary.spec.ts` |

### Per-test outcome (all GREEN — no quarantines)

**S1 (8 tests, all green):** S1.1 draft, S1.2 audio_generated, S1.3 animated, S1.4 selected, S1.5 lipsync_pending, S1.6 final, S1.7 no-skip-state guard, S1.8 Use-as-Final mutation contract.

**S2 (6 tests, all green):** S2.1 bg_accept_option scope-injection + snapshot ordering, S2.2 beat_update_text non-BG event_id key, S2.3 409 mn:scope-mismatch event, S2.4 423 re-hydrate-and-retry, S2.5 bg_accept_lib_image BG body shape, S2.6 state_snapshot non-recursive.

**S3 (4 tests, all green):** S3.1 select-option triggers refresh draft→selected, S3.2 use_as_final triggers refresh selected→final, S3.3 mn-magic-or-animate-complete postMessage triggers refresh, S3.4 BG-tab mutation does NOT trigger StoryboardTab refresh (negative invariant).

**S4 (8 tests, all green):** S4.1/S4.2 magic-still button gating, S4.3 window.open URL contract (mode/beat_id/source_image_path/return_endpoint/scope_event_id), S4.4 magic/status missing job_id → 400, S4.5 magic/status unknown job_id → 404, S4.6 magic/resolve_bg missing scene_key → 400 (after PyYAML CI install fix), S4.7 magic/submit_path empty body 4xx, S4.8 magic-video gating on video source.

**S5 (7 tests, all green):** S5.1 0-item empty state, S5.2 120-item scroll-bound, S5.3 delete-button stopPropagation, S5.4 delete refetches library, S5.5 dragstart payload identity, S5.6 legacy `{sources,crops,masters}` flatten, S5.7 server-error pane visible.

**S6 (8 tests, all green):** S6.1 data-resolved-scope format, S6.2 Events+Milestones groups + sentinels, S6.3 NewEvent modal opens (no load fetch), S6.4 NewMilestone modal opens (no load fetch), S6.5 milestone_load via pathappPatch with scope-injected body, S6.6 cross-event server reject (404/409), S6.7 video-role change is partition-level (mocked, no state pollution), S6.8 NewEvent regex error.

## Spec drift findings (documented; per Rule 1, NOT fixed)

The retroactive-coverage spec was authored before the S5.5d v3 architecture revision shipped. Two surface descriptions referenced endpoints/components that were superseded; tests were adapted to the actual SUT and the drift is captured here:

| Spec wording | Reality on origin/main 1d375de | Tests adapted to |
|---|---|---|
| S1: "production_server.py `_handle_bg_finalize_beat`, `_handle_bg_unlock_beat`" | No such handlers exist. Lifecycle is derived client-side in `StoryboardTab.tsx::deriveBeatLifecycle()` from beat fields. Equivalent state-close mutation is `beat_use_as_final` (POST `/api/beat/use_as_final`). | Lifecycle derivation + visibility table + Use-as-Final mutation contract. |
| S4: "Magic compositor invocation from BgTab" | Magic UI lives in `StoryboardTab.tsx::BeatMagicButtons` (lines 559-635), not BgTab. Server endpoints: `/api/magic/{status,resolve_bg,submit_path}`, `/api/storyboard/magic_{still,video}`. | StoryboardTab button gating + window.open URL contract + server endpoint contracts. |

**Recommendation:** amend the spec on a future maintenance pass, OR mark §3 S1 + §3 S4 with "superseded by S5.5d v3 — see RETROACTIVE_COVERAGE_RESULTS_V1.md".

## Bugs / findings deferred (NOT fixed in this session)

Per spec §2 Rule 3, findings get logged + deferred — no inline diagnosis or fix. None of these caused a test to RED on its own; they were observed alongside passing tests or via the §3 S2 raw-fetch spot-check. They become inputs to follow-up fix sessions.

### F-S2-001 — Stitcher mutations bypass pathappPatch
- **Where:** `StitcherTab.tsx:123` (POST `/api/stitch_editor/preview`), `:149` (`/api/stitch_editor/bake`), `:191` (`/api/stitch_editor/job` save).
- **Symptom:** Mutations issued via raw `fetch()` skip the M1 pre-write `state_snapshot`, do not auto-inject `scope_event_id`/`scope_version`/`scope_target_video` per LD-461, and do not handle 409/423 via the documented event channels.
- **Why it matters:** Bypasses the single-mutation-channel architectural commitment per LD `PATH_C_REWRITE_V1` + LD-456 + LD-461. If StitcherTab mutations ever target the wrong scope mid-event-swap, the rest of the system has no signal.
- **Severity classification (per schema heads-up):** HARD (behavioral/architectural).
- **Recommendation:** Migrate all three call-sites to `pathappPatch`. Ensure `MUTATION_ENDPOINTS.stitch_*` keys exist (some already do — `stitch_loudnorm`, `stitch_save_job`).

### F-S2-002 — VideoSelector mutations bypass pathappPatch
- **Where:** `VideoSelector.tsx:81` (POST `MUTATION_ENDPOINTS.video_set_active`), `:128` (`MUTATION_ENDPOINTS.video_create`).
- **Symptom:** Same class as F-S2-001 — raw fetch on mutation endpoints, no scope-injection, no snapshot, no 409/423 handling.
- **Why it matters:** This is also the **upstream cause** of the test-pollution we hit in CI run 1 (S6.7 → R1.1). If `set_active` went through pathappPatch with a documented "is this scope-mutating?" override, test isolation would be cleaner. Production-side: a switch from `intro` → `resolution` mid-mutation pin window would not be re-checked.
- **Severity classification:** HARD (architectural).
- **Recommendation:** Same as F-S2-001.

### F-CI-001 — `production_server.py` imports `yaml` but project has no requirements.txt
- **Where:** `production_server.py:5240` (inside `_handle_magic_resolve_bg`).
- **Symptom:** CI run 1 failed S4.6 because the workflow's pip install step had only `Pillow`. Because the project has no requirements pin, every CI workflow has to enumerate every transitive runtime dep manually — and only the dep needed by the proper-fix scope was listed.
- **Why it matters:** Each new test session that exercises a previously-untouched server path risks CI red until someone notices and amends the workflow's pip line. This is friction, not a deep bug, but it's recurring.
- **Severity classification:** SOFT (process / dev-experience).
- **Recommendation:** Create `Production/tools/requirements.txt` enumerating Pillow, PyYAML, anything else `production_server.py` imports beyond stdlib; have the workflow `pip install -r` from it. Out of scope for this sprint per Rule 1.

### F-SVR-001 — `[sidecar] write failed: TypeError: 'int' object is not iterable`
- **Where:** Surfaced as a server warning in CI logs during the green run. Not yet attributed to a specific handler — search `production_server.py` for `[sidecar] write failed`.
- **Symptom:** The sidecar write code path emits a TypeError + recovers silently (tests still pass). Per Rule 19 spirit ("no error paths left open"), silent server failures are themselves the bug.
- **Why it matters:** This warning fired during a session where 54 tests passed — meaning some sidecar-related write is silently failing in normal operation. Could indicate stale data in `L.json` for some beats over time.
- **Severity classification:** HARD (silent corruption potential).
- **Recommendation:** Diagnose in a separate session — grep `[sidecar] write failed`, instrument or fail-loud the write, then fix. Out of scope here per Rule 1.

## Verification gates (G1-G8)

| Gate | Check | Status |
|---|---|---|
| G1 | Proper-fix `S5_5CE_PROPER_FIX_COMPLETE` activity row found and verified | **PASS** — id=1494 verified 2026-05-04T04:39Z |
| G2 | `Production/Event_e2e_fixture/` exists; tests use it | **PASS** — `.pristine/` + storyboard placeholder + globalSetup pin |
| G3 | At least 1 test landed for each of S1-S6 | **PASS** — all six covered (S1=8, S2=6, S3=4, S4=8, S5=7, S6=8 = 41 tests) |
| G4 | Every red-on-first-run test has matching `BUG_FOUND` row + `test.fixme` | **PASS (vacuous)** — no test stayed red after iteration; both first-run failures were CI-infra (PyYAML) and test-pollution (S6.7), neither were SUT bugs warranting quarantine. Per Rule 1 + Rule 5 the fix was test-side. |
| G5 | No production code (`src/`, `production_server.py`, `lib/`) modified | **PASS** — `git diff main -- :^Production/tools/storyboard-v2/e2e :^.github/workflows :^Production/docs` empty |
| G6 | CI run on the branch is green | **PASS** — run [25319006667](https://github.com/kimhyla/mindfulnest-tooling/actions/runs/25319006667), 54/54 passed |
| G7 | Results doc exists in Dropbox | **PASS** — this file |
| G8 | LD + activity + master overview updates registered | **PASS** at closeout |

## Recommendations for next session(s)

In rough priority order:

1. **Architectural fix-session:** address F-S2-001 + F-S2-002. Migrate StitcherTab + VideoSelector mutations onto `pathappPatch`. Single PR, tests-already-exist (S2 + S6 coverage in this sprint will protect the migration).
2. **Hygiene fix-session:** F-CI-001 — create `Production/tools/requirements.txt` and update `playwright_e2e.yml` to install from it.
3. **Diagnose-and-fix session:** F-SVR-001 — sidecar TypeError; instrument first to find the offending handler, then fix.
4. **Spec hygiene:** amend `STORYBOARD_V59_RETROACTIVE_COVERAGE_SPEC_v1.md` §3 S1 + §3 S4 to reflect S5.5d v3 reality.
5. **Coverage v2 (only if Kim wants it):** spec §3.7 deferred items — Cropper modal canvas behavior beyond drag-drop, TabBar tab switch state preservation, Toast/Spinner/Modal primitive behavior under unusual conditions.

## File summary

### Created
- 6 spec files in `Production/tools/storyboard-v2/e2e/retroactive_s{1-6}_*.spec.ts`
- This results doc: `Production/docs/RETROACTIVE_COVERAGE_RESULTS_V1.md` (Dropbox)

### Modified
- `.github/workflows/playwright_e2e.yml` — added the six new specs to the `npx playwright test` inclusion list per §8.9 convention; added `PyYAML` to the pip install line. (Workflow yaml is not in spec §7's "NOT modified" list and the workflow comment lines 7-12 explicitly direct future sessions to extend it.)

### NOT modified (per spec §7 + Rule 1)
- All production code (`src/`, `production_server.py`, `lib/`, `scripts/`)
- All existing e2e specs (smoke, behavioral-parity, rollback, touchpoint-a, s5_5ce_proper_fix)
- All fixture data (Event_e2e_fixture untouched at session end)
- All spec docs other than master overview status table (appended this session)

## Directus rows registered

- `prod_preflight_reviews` id=**202** (task_id `retroactive-coverage-sprint-20260504`)
- `prod_activity_log`:
  - id=1492 — earlier G1-fail abort (superseded once proper-fix landed)
  - id=**1496** — `RETROACTIVE_COVERAGE_SPRINT_PHASE_0_COMPLETE`
  - id=**1498** — `RETROACTIVE_COVERAGE_SPRINT_COMPLETE` (closeout report)
- `prod_locked_decisions`: id=**511** `RETROACTIVE_COVERAGE_SPRINT_V1_COMPLETE` (severity=SOFT, scope_domain=infra, enforcement_type=ci_check, status=active)
- `prod_blockers`:
  - id=**46** F-S2-001 (severity=high) StitcherTab.tsx raw-fetch mutations
  - id=**47** F-S2-002 (severity=high) VideoSelector.tsx raw-fetch mutations
  - id=**48** F-CI-001 (severity=low) Missing requirements.txt
  - id=**49** F-SVR-001 (severity=high) Sidecar TypeError silent failure

---

**End of Retroactive Coverage Sprint v1 Results.**
