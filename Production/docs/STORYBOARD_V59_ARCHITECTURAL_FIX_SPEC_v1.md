# Storyboard v59 — Architectural Fix Spec v1 (TDD-style; mutation-channel + server hygiene)

**Date:** 2026-05-04
**Classification:** ARCHITECTURAL FIX — addresses 4 prod_blockers logged by retroactive coverage sprint v1 (PR #2)
**Predecessors:**
- PR #1 (proper-fix, squash `1d375de`): CI gate live + Event_e2e_fixture/ + 5 LDs (506-510)
- PR #2 (retroactive coverage, squash `724942d`): 41 e2e tests across 6 surfaces; 4 blockers found
**Working tree:** `~/Projects/mindfulnest-tooling/` (main, post both merges)
**Master overview:** `STORYBOARD_V59_FEATURE_PARITY_MASTER_OVERVIEW.md`

## §1 Why combined

The retroactive coverage sprint surfaced 4 prod_blockers (#46-49). Three of them — F-S2-001, F-S2-002, F-SVR-001 — are real architectural / behavioral issues that warrant a dedicated fix session. F-CI-001 is process hygiene that folds in cheaply. Combining them in one TDD-ordered session is appropriate because:

1. **F-S2-001 + F-S2-002 are the SAME class of fix** (raw fetch → pathappPatch via the existing mutation channel). Same patterns, same tests, single review surface.
2. **F-S2-002 was the upstream cause of test pollution** during retroactive run 1 (S6.7 fired video_set_active raw, polluted state.json, broke R1.1 next run). Fixing it makes test isolation easier going forward — directly improves the test infrastructure that S5.5f depends on.
3. **F-SVR-001 is independent** but small — diagnose + fix one server location. Folding in avoids a separate session.
4. **F-CI-001 is hygiene** — adding `Production/tools/requirements.txt` + workflow update is a 30-min change that prevents future "ModuleNotFoundError on new code path" friction.

The retroactive sprint already wrote 14 tests covering S2 + S6 surfaces. **Those tests are the safety net for this fix** — they were written against the buggy SUT and confirm pathappPatch behavior on the mutation channel; this session extends them to assert StitcherTab + VideoSelector mutations also flow through pathappPatch.

## §2 Task

Land 4 fixes:

1. **F-S2-001:** Convert StitcherTab.tsx mutations at lines 123 (preview), 149 (bake), 191 (save) from raw `fetch()` to `pathappPatch`. Verified line numbers via grep on main 2026-05-04.
2. **F-S2-002:** Convert VideoSelector.tsx mutations at lines 81 (set_active), 128 (create) from raw `fetch()` to `pathappPatch`. Verified line numbers.
3. **F-SVR-001:** Diagnose + fix the silent `[sidecar] write failed: TypeError 'int' object is not iterable` log at `production_server.py:3899`. Either fail-loud or fix the root TypeError (preferred).
4. **F-CI-001:** Create `Production/tools/requirements.txt` enumerating non-stdlib runtime deps (yaml + Pillow at minimum; audit for others); update `.github/workflows/playwright_e2e.yml` to `pip install -r Production/tools/requirements.txt`.

## §3 Governing decisions

### LDs respected

| LD | Reason |
|---|---|
| LD-461 SCOPE_KEY_AUTO_INJECTION_V1 | pathappPatch auto-injects scope_event_id / scope_version / scope_target_video; raw fetch bypasses |
| LD-456 SCOPE_VALIDATION_V1 | 409/423 handling + scope-mismatch banner only fire through pathappPatch |
| PATH_C_REWRITE_V1 | All client mutations through the mutation channel (this is the LD F-S2-001/002 violate) |
| LD PATCH_INVARIANT_PERSISTENCE_V1 (LD-453) | Pre-write state_snapshot for rollback; raw fetch bypasses |
| LD-507 MANDATORY_E2E_GATE_V1 | New behavior must be Playwright-tested |
| LD-508 CI_PLAYWRIGHT_ON_COMMIT_V1 | CI workflow enforces |
| LD §16 flake governance (proper-fix) | Critical-path tests stay green |
| LD §17 fixture pinning (proper-fix) | Tests use Event_e2e_fixture/ only |
| LD-19 Rule 19 | No shortcuts; no "we'll fix the silent server error later" |

### NEW LDs this spec writes (3)

| Key | Severity | Purpose |
|---|---|---|
| `MUTATION_CHANNEL_INVARIANT_V1` | HARD | All client-side state mutations MUST flow through pathappPatch. Raw fetch to mutation endpoints (anything that POSTs/PATCHes/DELETEs against state) is a violation. ESLint rule or grep CI gate enforces (this LD writes the rule + the CI gate). Codifies what F-S2-001/002 violated. |
| `SERVER_SILENT_FAILURE_FAIL_LOUD_V1` | HARD | When a server-side write path fails with a caught exception, log + raise (or fail the request) — NEVER silent print. F-SVR-001 was the example. The fix here applies to that one site; the LD applies to future server code. |
| `PRODUCTION_TOOLING_REQUIREMENTS_TXT_V1` | SOFT | `Production/tools/requirements.txt` is the canonical runtime dep list for production_server.py + sibling tools modules. CI workflow installs from it. New deps: add to file, not to inline pip command. |

## §4 Approach (TDD-ordered)

### §4.1 Diagnosis confirmed by direct code inspection 2026-05-04

| Issue | Evidence (verified on main `724942d`) |
|---|---|
| F-S2-001 StitcherTab | `StitcherTab.tsx:70` is a READ (`/api/stitch_editor/jobs` list) — keep as raw fetch (pathappPatch is for mutations). `StitcherTab.tsx:123, 149, 191` are MUTATIONS — convert. |
| F-S2-002 VideoSelector | `VideoSelector.tsx:81` (`MUTATION_ENDPOINTS.video_set_active`), `:128` (`video_create`) — both already use the MUTATION_ENDPOINTS constant which means they're declared as mutations but route raw. The fix is mechanical — `fetch(URL, opts)` → `pathappPatch(scope, action, body)`. |
| F-SVR-001 | `production_server.py:3899` `print(f"[sidecar] write failed: {type(exc).__name__}: {exc}")`. The `exc` is a TypeError from somewhere in the surrounding `try:` block. Diagnosis: read the try block (lines 3870-3899 approximately) to find which call raises `'int' object is not iterable`. Common cause: code expecting `for x in some_field:` where `some_field` is now an int (data-shape regression). |
| F-CI-001 | `production_server.py:5240` imports `yaml` (PyYAML); other non-stdlib deps need audit. Runtime imports observed: `from PIL import Image` (Pillow), `import yaml` (PyYAML). Audit step in Phase 1 confirms full list. |

### §4.2 TDD flow

**Phase 1 (discovery + RED tests)** writes failing tests asserting the desired post-fix behavior. **Phase 2 (GREEN code)** turns them green. **Phase 3 (CI verification)** confirms the gate works. **Phase 4 (closeout)** ships.

The retroactive sprint's S2 tests already establish the pattern — they test that pathappPatch persists mutations. This spec's new tests assert specifically that StitcherTab + VideoSelector USE pathappPatch (vs raw fetch). **Note (per Cursor R1):** `pathappPatch()` at `client.ts:175` does NOT route through any unified `/api/state/path` endpoint — it resolves `MUTATION_ENDPOINTS[endpoint]` and POSTs directly to the real mutation URL with scope keys auto-injected in the body. So tests assert:

- The REAL mutation endpoint URL is hit (e.g., `/api/stitch_editor/preview`, `/api/stitch_editor/bake`, `/api/stitch_editor/job`, `/api/video/set_active`, `/api/video/create`)
- The request body has auto-injected scope keys per `scopeKeyFor(endpoint)`: `scope_event_id` (BG endpoints) or `event_id` (others), plus `scope_target_video`, `scope_video_role`, optional `scope_milestone_id`
- BEFORE the mutation, a separate POST to `MUTATION_ENDPOINTS.state_snapshot` (`/api/state/snapshot` or similar) fires (the M1 snapshot, fire-and-forget)
- 409 response (scope_mismatch, LD-456) → `mn:scope-mismatch` event emitted → UI banner shown
- 423 response (event_changed_mid_job, LD-458/460) → re-hydrate scope + retry once

## §5 Implementation phases

### Phase 0 — Pre-flight

**0.1.** Read this spec + retroactive results doc + proper-fix spec §16/§17.

**0.2.** `prod_preflight_reviews` row task_id="architectural-fix-mutation-channel-20260504" referencing PR #1 + PR #2 + blockers #46-49 as predecessors.

**0.3.** Verify working tree state:
- `cd ~/Projects/mindfulnest-tooling && git checkout main && git pull`
- `git log --oneline -3` should show `724942d` (retroactive merge) and `1d375de` (proper-fix merge)
- `git checkout -b claude/architectural-fix-mutation-channel`

**0.4.** Re-grep to confirm fix sites still match pre-discovery line numbers (drift-resistant):
- `grep -nE "fetch\(.*api" Production/tools/storyboard-v2/src/components/StitcherTab.tsx` — expect lines 70, 123, 149, 191
- `grep -nE "fetch\(MUTATION_ENDPOINTS\." Production/tools/storyboard-v2/src/components/VideoSelector.tsx` — expect lines 81, 128
- `grep -nE "\[sidecar\] write failed" Production/tools/production_server.py` — expect line 3899

If line numbers shifted, capture new ones in spec amendment + proceed; if structure changed (e.g., StitcherTab no longer has raw fetch), STOP and surface (something else fixed it).

**0.5. Pre-implementation routing/compile verification (NEW per Cursor R3):**

Before writing any tests in Phase 1 or any fixes in Phase 2, verify that `pathappPatch(scope, endpoint, body)` will actually compile + route for all 5 mutation sites:

- Read `endpoints.ts` `MUTATION_ENDPOINTS` object. Confirm presence of: `video_set_active`, `video_create`, `stitch_save_job`. Capture the exact key spelling.
- Confirm ABSENCE of `stitch_preview` and `stitch_bake` keys (Cursor verified 2026-05-04: these keys do NOT exist; `stitch_save_job` does). The fix REQUIRES extending the catalog before converting the StitcherTab fetches.
- Read `BG_MUTATION_ENDPOINTS` set + `scopeKeyFor()` to determine which scope key gets auto-injected for each endpoint key (`scope_event_id` for BG endpoints; `event_id` for others). The 5 mutation sites here are NOT in BG_MUTATION_ENDPOINTS, so they get `event_id`. Document this in scratch notes for Phase 1 test assertions.
- Read server handlers to confirm scope guard behavior:
  - `_handle_video_set_active` / `_handle_video_create` — confirmed scope-aware (per Cursor §14 Q6)
  - `_handle_stitch_bake` / `_handle_stitch_save_job` — already scope-guard (per Cursor §14 Q6)
  - `_handle_stitch_preview` — currently does NOT scope-guard (per Cursor §14 Q6). Phase 2.1 must DECIDE: add scope-guard to `_handle_stitch_preview` (preferred — consistency), OR document that preview is intentionally scope-loose (only with strong rationale + LD note).

If any of the above differs from this section's assertions, capture the divergence and surface to Kim before writing tests. This is the spec's biggest architectural unknown; Phase 0.5 closes it.

### Phase 1 — Write failing tests (RED)

**1.1.** Read `pathappPatch` signature at `src/api/client.ts:175` to confirm interface — must understand action key + body shape before writing assertions.

**1.2.** Read existing retroactive tests for the pattern:
- `e2e/retroactive_s2_pathapp_patch.spec.ts` — pathappPatch persistence tests (reference)
- `e2e/retroactive_s6_project_selector.spec.ts` — VideoSelector mock-only test pattern (reference)

**1.3.** Create `e2e/architectural_fix.spec.ts` with these test cases:

**StitcherTab (F-S2-001) — assertions per §4.2 (pathappPatch posts directly to real mutation URLs with auto-injected scope keys):**
- AF.1.1: Click Preview button → network spy sees POST `/api/stitch_editor/preview` (the real endpoint, hit via pathappPatch). Body must contain auto-injected `event_id` (per `scopeKeyFor('stitch_preview')` resolving to non-BG branch) + `scope_target_video` + `scope_video_role`. ALSO before that POST, network spy sees the M1 snapshot POST to `MUTATION_ENDPOINTS.state_snapshot` (fire-and-forget, fires on every non-snapshot mutation).
- AF.1.2: Click Bake button → POST `/api/stitch_editor/bake` (via pathappPatch) with same auto-injected scope-key body shape; M1 snapshot fires beforehand.
- AF.1.3: Click Save Job → POST `/api/stitch_editor/job` (via pathappPatch, key `stitch_save_job`) with same auto-injected body shape; M1 snapshot fires beforehand.
- AF.1.4: Mid-action event swap → server returns 409 (scope_mismatch, LD-456) → `mn:scope-mismatch` event emitted by pathappPatch → UI shows scope-mismatch banner.
- AF.1.5: Stub server to return 423 (event_changed_mid_job, LD-458/460) on first call → pathappPatch re-hydrates scope + retries once → second call has updated scope keys → succeeds.

**VideoSelector (F-S2-002) — same assertion model:**
- AF.2.1: Switch active video (intro → resolution) → POST `/api/video/set_active` (the real endpoint, hit via pathappPatch with key `video_set_active`). Body has auto-injected `event_id` + `scope_target_video` + `scope_video_role`. M1 snapshot fires beforehand.
- AF.2.2: Create new video → POST `/api/video/create` (via pathappPatch with key `video_create`) with same auto-injected scope-key body shape; M1 snapshot fires beforehand.
- AF.2.3: For both AF.2.1 + AF.2.2, assert auto-injected scope keys are present in body (verified via network spy payload, not just method/URL).
- AF.2.4: Stub server 423 response on video_set_active → pathappPatch re-hydrates + retries once → second call succeeds.

**F-SVR-001:**
- AF.3.1: Trigger the path that produces the sidecar TypeError (Phase 1 needs to identify the path; if not reproducible from a test, this becomes a unit-level Python test)
- After fix, this test passes (or no longer logs the error)

**F-CI-001:**
- No e2e test; verified at gate level (Phase 3 G6)

**1.4.** Run tests locally — all should FAIL (RED). Commit. Push. CI red.

### Phase 2 — Fix code (GREEN)

**2.1. F-S2-001 — StitcherTab raw fetch → pathappPatch (3 sites):**

**2.1.0 (NEW per Cursor R2): Extend `MUTATION_ENDPOINTS` catalog FIRST.** Per Phase 0.5 verification, `endpoints.ts:49-107` has `stitch_save_job` and `stitch_loudnorm` but lacks `stitch_preview` + `stitch_bake`. Add them:

```typescript
// In Production/tools/storyboard-v2/src/api/endpoints.ts MUTATION_ENDPOINTS:
stitch_preview: `${SERVER_BASE}/api/stitch_editor/preview`,
stitch_bake:    `${SERVER_BASE}/api/stitch_editor/bake`,
// stitch_save_job already exists at line 76
```

This is REQUIRED before converting the fetches; without it, `pathappPatch(scope, 'stitch_preview', body)` fails the `MutationEndpoint` keyof check at TypeScript compile.

**2.1.1 Scope-guard decision for `_handle_stitch_preview`** (per Phase 0.5 + Cursor R2):
- DEFAULT: add scope-guard to `_handle_stitch_preview` for consistency with `_handle_stitch_bake` / `_handle_stitch_save_job`. Surface in PR description.
- ALTERNATIVE (only with rationale): document why preview is intentionally scope-loose; write rationale to a follow-up LD `STITCH_PREVIEW_SCOPE_LOOSE_RATIONALE_V1` (SOFT) so the next reader doesn't undo it.

**2.1.2 Convert the 3 fetches** at lines 123, 149, 191:

```typescript
// BEFORE (line 123 example):
const res = await fetch(`${SERVER_BASE}/api/stitch_editor/preview`, {method:'POST', body: JSON.stringify(payload)});

// AFTER:
const res = await pathappPatch(activeScope.value, 'stitch_preview', {
  // body fields per existing payload — MINUS scope keys (auto-injected by pathappPatch)
});
```

Use the catalog keys added in 2.1.0: `stitch_preview` (line 123), `stitch_bake` (line 149), `stitch_save_job` (line 191; key already exists). NOT the placeholder names (`stitch_editor_preview` etc.) used in earlier drafts — those won't compile.

Run AF.1.1-AF.1.5 → GREEN.

**2.2. F-S2-002 — VideoSelector raw fetch → pathappPatch (2 sites):**
- Lines 81, 128 — same pattern.
- Server side: `video_set_active` and `video_create` MUST accept the pathappPatch envelope. Verify; surface if not.

Run AF.2.1-AF.2.4 → GREEN.

**2.3. F-SVR-001 — Diagnose + fix (per Cursor R4 hardening):**

**Root cause fix is MANDATORY default.** The fail-loud fallback (b) is constrained because `_write_sidecar_L_json` is INTENTIONALLY non-fatal by contract (per Cursor R4 — making it raise unconditionally could destabilize callers that don't expect to handle this exception path).

Steps:

- Read `production_server.py` lines 3870-3899 (the try block surrounding line 3899)
- Read all callers of `_write_sidecar_L_json` (or whatever the surrounding function is) to confirm the non-fatal contract
- Identify the call raising `TypeError 'int' object is not iterable` — likely a data-shape mismatch where code expects iterable but got int. Common cause: `for x in some_field:` where `some_field` is now an int (data-shape regression in upstream producer).
- **(a) MANDATORY DEFAULT:** fix the root cause. Either:
  - Update the consumer to handle int (e.g., `if isinstance(some_field, int): some_field = [some_field]` or skip the loop entirely)
  - OR update the producer to always emit list shape
  - Prefer the producer fix if the int shape is itself the bug; prefer the consumer fix if the int shape is legitimate input that the consumer mishandled
- **(b) GUARDED FALLBACK** (only if root cause requires architectural changes beyond this session's scope):
  - Replace `print(...)` with structured logging at WARN level + `prod_blockers` row creation (so the silent failure becomes a tracked blocker, not just a log line)
  - Do NOT replace with unconditional `raise` — that breaks the non-fatal contract
  - Add explicit comment in code documenting the contract: `# NOTE: this writer is non-fatal by design; callers do not handle this exception path`
  - Create a follow-up `prod_blockers` row IN THE SAME PR for the underlying TypeError so it's tracked, not buried
  - Surface the fallback decision to Kim in the PR description with explicit impact note

Run AF.3.1 → GREEN (or verify no more sidecar log lines in CI run output, or — if (b) — verify the WARN log fires + blocker row created).

**2.4. F-CI-001 — requirements.txt:**
- Audit non-stdlib imports across `production_server.py`, `ffmpeg_utils.py`, `lipsync_sender.py`, `kling_startend_pipeline.py`, `Production/lib/*.py`
- Create `Production/tools/requirements.txt`:
```
PyYAML>=6.0
Pillow>=10.0
# Add others as audit reveals
```
- Update `.github/workflows/playwright_e2e.yml`:
```yaml
# BEFORE:
- name: Install Python deps
  run: pip install Pillow PyYAML
# AFTER:
- name: Install Python deps
  run: pip install -r Production/tools/requirements.txt
```
- Commit.

### Phase 3 — CI verification

**3.1.** Push branch to origin.

**3.2.** Confirm CI runs all tests (existing 54 + new ~10) → green.

**3.3.** Validate the new MUTATION_CHANNEL_INVARIANT gate works: deliberately convert ONE pathappPatch back to raw fetch in a scratch commit → push → CI should go red on the corresponding AF test → restore → green. Document in commit message.

**3.4. MANDATORY (per Cursor R5): CI grep step enforces MUTATION_CHANNEL_INVARIANT_V1.**

This was previously labeled optional. Per Cursor §14 Q15, optional enforcement reduces this fix to whack-a-mole site patching rather than architectural pattern closure. Promoting to mandatory:

Add to `.github/workflows/playwright_e2e.yml` BEFORE the Playwright test step:

```yaml
- name: Mutation channel invariant check
  working-directory: Production/tools/storyboard-v2
  run: |
    set -e
    echo "Searching for raw fetch to MUTATION_ENDPOINTS in components/ (allowed only in src/api/)..."
    if grep -rE "fetch\(.*MUTATION_ENDPOINTS\." src/components/ src/state/ src/utils/ 2>/dev/null; then
      echo "::error::Raw fetch to MUTATION_ENDPOINTS found outside src/api/ — violates MUTATION_CHANNEL_INVARIANT_V1. Use pathappPatch."
      exit 1
    fi
    echo "Searching for raw fetch to /api/stitch_editor/* paths in components/..."
    if grep -rnE "fetch\(.*\/api\/stitch_editor\/(preview|bake|job|jobs)" src/components/ src/state/ 2>/dev/null | grep -vE "^[^:]+:[0-9]+:.*/jobs[^/]"; then
      # /jobs (list) is a READ — keep raw fetch allowed; mutations (preview/bake/job singular) banned
      echo "::error::Raw fetch to stitch_editor mutation endpoint found — violates MUTATION_CHANNEL_INVARIANT_V1."
      exit 1
    fi
    echo "Searching for raw fetch to /api/video/(set_active|create) in components/..."
    if grep -rE "fetch\(.*\/api\/video\/(set_active|create)" src/components/ src/state/ 2>/dev/null; then
      echo "::error::Raw fetch to video mutation endpoint — violates MUTATION_CHANNEL_INVARIANT_V1."
      exit 1
    fi
    echo "Mutation channel invariant: PASS"
```

The exclusion of `src/api/` from the search lets `pathappPatch` itself legitimately use `MUTATION_ENDPOINTS` internally (it's the channel implementation; everything else routes through it). The `/jobs` list read is preserved as a legitimate raw fetch (READ, not MUTATION).

This step runs on every push + PR. Adding new mutation endpoints in the future requires either using `pathappPatch` (passes) or explicitly extending this grep with a new exclusion (forces a reviewer to ack the exception, which is what we want).

### Phase 4 — Verification (13 gates per Cursor R5)

**G1.** `npm run build` clean.
**G2.** Server `/api/health` 200 (Rule 29 staleness check on production_server.py edits).
**G3.** All 54 existing e2e tests still pass.
**G4.** New AF.1.1-AF.1.5 (StitcherTab) pass.
**G5.** New AF.2.1-AF.2.4 (VideoSelector) pass.
**G6.** New AF.3.1 (or sidecar-log absence) pass.
**G7.** `Production/tools/requirements.txt` exists; CI workflow installs from it.
**G8.** CI run on feature branch is green.
**G9.** RED-then-GREEN proof captured (Phase 3.3) — the gate enforces.
**G10.** No raw fetch to mutation endpoints in StitcherTab or VideoSelector (grep verifies zero matches for `fetch(.*MUTATION_ENDPOINTS\.` and `fetch(.*\/api\/stitch_editor\/(preview|bake|job)` outside src/api/).
**G11.** Sidecar TypeError no longer logged in CI run output (grep CI logs for `[sidecar] write failed`).
**G12.** 3 NEW LDs registered (HARD/SOFT severity per schema migration note).
**G13. (NEW per Cursor R5)** CI workflow includes the mutation channel invariant grep step (Phase 3.4) + the step ran successfully on the PR's CI run + a deliberate test (e.g., add a raw fetch to a scratch component, push, see CI red, remove, push, see CI green) confirms the enforcement actually fires. This is the structural pattern-level closure of Q15.

### Phase 5 — Closeout

**5.1.** `prod_activity_log` row `ARCHITECTURAL_FIX_MUTATION_CHANNEL_COMPLETE` with full gate summary + 4 finding resolution status.

**5.2.** PATCH the 4 prod_blockers (#46-49):
- #46 (F-S2-001): status=resolved
- #47 (F-S2-002): status=resolved
- #48 (F-CI-001): status=resolved
- #49 (F-SVR-001): status=resolved (or partially-resolved if Phase 2.3 fell back to fail-loud option (b))

**5.3.** Master overview status table updated with this session's row.

**5.4.** Single git commit + push + gh pr create.

## §6 Files modified

### Created
- `Production/tools/requirements.txt`
- `Production/tools/storyboard-v2/e2e/architectural_fix.spec.ts`

### Modified
- `Production/tools/storyboard-v2/src/components/StitcherTab.tsx` (3 fetch → pathappPatch)
- `Production/tools/storyboard-v2/src/components/VideoSelector.tsx` (2 fetch → pathappPatch)
- `Production/tools/production_server.py` (sidecar TypeError fix near line 3899)
- `.github/workflows/playwright_e2e.yml` (pip install -r requirements.txt + add architectural_fix.spec.ts to test command per proper-fix §19.6 append-not-replace)

### Server-side (conditional — only if pathappPatch envelope incompatibility surfaces)
- `production_server.py` `_handle_stitch_editor_preview` / `_handle_stitch_editor_bake` / `_handle_stitch_editor_job` / `_handle_video_set_active` / `_handle_video_create` — adapter to accept pathappPatch envelope. Surface to Kim BEFORE making these changes if needed; this is substantive scope expansion.

## §7 Directus writes

- `prod_locked_decisions`: 3 NEW LDs (severity HARD or SOFT per schema migration note 2026-05-04)
- `prod_blockers`: 4 PATCHes (status=resolved)
- `prod_activity_log`: phase rows + COMPLETE
- `prod_preflight_reviews`: 1 row at session start

## §8 Error cases

| Failure | Handling |
|---|---|
| Re-grep at Phase 0.4 shows StitcherTab/VideoSelector no longer have raw fetch | STOP — something else already fixed it; close blockers as already-resolved |
| pathappPatch envelope incompatible with `_handle_stitch_editor_*` server handlers | STOP; surface to Kim — server-side adapter is substantive scope; decide whether to expand session OR file a server-side follow-up |
| F-SVR-001 root cause requires architectural change beyond one session | Fall back to fail-loud (option b); file follow-up blocker for the deeper TypeError |
| New requirements.txt audit reveals 5+ unexpected non-stdlib deps | Surface to Kim — may indicate import drift worth its own audit session |
| Phase 3 CI red after fix → diagnose; if 30 min unproductive, STOP + surface |
| 409/423 handling test (AF.1.4 / AF.2.4) requires server-side test fixture changes | Skip those test cases; document in PR body; file follow-up |
| Rule 26 Opus Escalation triggers | STOP, surface |

**No silent failures.** Per Rule 19.

## §9 Verification

12 gates green + 3 LDs registered + 4 blockers resolved + CI workflow runs green on a real commit + RED-then-GREEN proof.

## §10 Out of scope

- Adding pathappPatch enforcement at server side (mechanical-rejection of non-envelope POSTs to mutation endpoints) — separate session if architectural smell remains
- Further investigation of any TypeError pattern beyond F-SVR-001 — file as separate blocker
- pip-tools / lockfile (`requirements.lock`) — defer; plain requirements.txt is sufficient for this session
- Broad audit of other components for raw-fetch mutations beyond the 5 planned mutation sites (StitcherTab × 3, VideoSelector × 2) — assume retroactive sprint surfaced what's there
- Server-side handler unification (multiple `_handle_*` methods that could share an envelope adapter) — defer
- Browser smoke verification — Kim's job, redefined scope per LD-509

**Incidentally-found violations rule (per Cursor R6):** if Phase 0.5 / Phase 2 work surfaces ADDITIONAL raw-fetch-to-mutation violations in components NOT in the planned 5 sites, **log them as new `prod_blockers` rows + do NOT fix in this session**. The mandatory grep gate (Phase 3.4 / G13) then surfaces them on the very next PR's CI run as red — forcing the next session to address them. This preserves session scope discipline while ensuring no incidentally-discovered violation is lost. Same rule applies to additional silent-failure sites discovered while diagnosing F-SVR-001.

## §11 Dependencies

- PR #1 + PR #2 merged on main (verified pre-flight)
- pathappPatch interface stable at `src/api/client.ts:175` (assume)
- Server-side mutation handlers accept pathappPatch envelope (verify in Phase 2.1; surface if not)

## §12 Notes for the executing session

- **TDD ORDER IS LOAD-BEARING.** Phase 1 (RED tests) → Phase 2 (GREEN code) → Phase 3 (CI proof). Don't write fixes before tests.
- **F-S2-001 + F-S2-002 are the SAME class of fix** — convert in same commit if scope tight. The 5 sites are all `fetch(URL, {method, body})` → `pathappPatch(scope, action, body)`.
- **Server-side compatibility is the unknown.** If `_handle_stitch_editor_*` server handlers don't accept pathappPatch envelopes (scope_event_id auto-injection, etc.), STOP and surface — the fix becomes a server-side change in addition to client. That's a scope decision.
- **F-SVR-001 root-cause (option a) preferred over fail-loud (option b).** Option b is the fallback if root cause requires more time than this session has.
- **F-CI-001 audit must enumerate ALL non-stdlib imports** — not just the two known (PyYAML + Pillow). Don't ship requirements.txt that's missing a dep that surfaces later.
- **Use HARD/SOFT severity** for new LDs per schema migration note 2026-05-04.
- **Per Rule 35:** every Directus write via `try_post_or_queue` with read-back.
- **Per Rule 29:** server staleness check after production_server.py edits.
- **Per Rule 19:** no shortcuts. Don't paper over server compatibility issues; surface them.
- **Compaction-aware checkpoint authority:** atomic boundaries are after Phase 2.1 (StitcherTab fixed), Phase 2.2 (VideoSelector fixed), Phase 2.3 (server fixed), Phase 2.4 (requirements.txt). Don't checkpoint mid-fix.

## §13 Cursor review checklist

For Cursor to verify before terminal handoff:

1. Does this spec correctly address all 4 prod_blockers (#46-49) found in retroactive sprint?
2. Are the line numbers in §4.1 still accurate as of HEAD on main? (re-grep)
3. Is the TDD ordering load-bearing or could fixes be done before tests safely?
4. Are the 3 NEW LDs (MUTATION_CHANNEL_INVARIANT_V1, SERVER_SILENT_FAILURE_FAIL_LOUD_V1, PRODUCTION_TOOLING_REQUIREMENTS_TXT_V1) the right grain — too narrow? too broad? overlapping with existing LDs?
5. Severity assignment HARD vs SOFT — defensible?
6. Server-side compatibility risk in Phase 2.1/2.2 — does pathappPatch's expected envelope match what `_handle_stitch_editor_*` and `_handle_video_*` actually accept? If not, what's the right scope split?
7. F-SVR-001 fix decision tree (root cause vs fail-loud) — is option (a) achievable in one session, or is fail-loud + follow-up the more honest plan?
8. F-CI-001 audit method (`grep -hE` of imports) — sufficient, or need a more rigorous tool (`pipreqs`)?
9. Phase 3.3 RED-then-GREEN proof on a live CI commit — same pattern as proper-fix Phase 4; any new failure modes?
10. Phase 3.4 grep CI step (optional ESLint replacement) — worth including, or scope creep?
11. Test count (~10 new tests) adequate, or need more around edge cases (e.g., what if scope_event_id is missing from pathappPatch body)?
12. 12 verification gates the right count? Any to drop or add?
13. Out-of-scope §10 — anything missing that should be defended against scope creep?
14. Are there any architectural smells in the StitcherTab/VideoSelector raw-fetch pattern that suggest a deeper fix beyond just routing through pathappPatch? (e.g., mutation endpoints not consistently named, scope handling distributed across many components)
15. Q15 (the honest-pattern question): does this spec address the *root pattern* that produced F-S2-001/002, or just patch the two specific sites? If pattern-level, what's the structural enforcement? If site-level, what protects the next new component from making the same mistake?

Append findings as §14 before terminal execution.

---

**End of Architectural Fix Spec v1.**

Awaiting Cursor review per §13 checklist.

## §14 Cursor v11 review findings (2026-05-04)

**Verdict:** **REVISE BEFORE SHIP**

The spec is close and directionally correct, but three load-bearing clarifications are required before execution:
1) correct the pathappPatch/network assertion model, 2) tighten server-compatibility handling for Stitcher endpoints, 3) make pattern enforcement mandatory (not optional) so this is architectural, not just site patching.

### §13 checklist answers (Q1-Q15)

1. **Q1 (all 4 blockers addressed):** **YES, with amendments.** All four blockers have explicit workstreams (F-S2-001/002, F-SVR-001, F-CI-001).
2. **Q2 (line numbers accurate):** **MOSTLY YES at review time** (StitcherTab raw fetch at 123/149/191; VideoSelector at 81/128; sidecar print at 3899). Keep Phase 0.4 re-grep as written.
3. **Q3 (TDD ordering):** **YES.** RED -> GREEN -> CI proof is appropriate and load-bearing here.
4. **Q4 (new LD grain):** **GOOD GRAIN.** `MUTATION_CHANNEL_INVARIANT_V1` and server fail-loud LD are architectural; requirements LD is hygiene-scoped.
5. **Q5 (HARD/SOFT severity):** **DEFENSIBLE.** `MUTATION_CHANNEL_INVARIANT_V1` as **HARD** is correct because violations create behavioral regressions (scope injection, 409/423 semantics, snapshot path).
6. **Q6 (server compatibility risk):** **PARTIAL COMPATIBILITY; REQUIRES SPEC AMEND.**  
   - `video_set_active`/`video_create` already accept `scope_event_id` via `_scope_body` and should work with pathappPatch envelope.  
   - Stitcher mutation path is not fully drop-in: `MUTATION_ENDPOINTS` currently has `stitch_save_job` but not preview/bake keys; spec example uses action names (`stitch_editor_preview` etc.) that do not exist in current endpoint catalog typing.  
   - `_handle_stitch_bake`/`_handle_stitch_save_job` already scope-guard; `_handle_stitch_preview` currently does not.  
   **Conclusion:** risk is real but bounded; fix requires endpoint-catalog/action-key alignment and explicit decision on preview scope-guard behavior.
7. **Q7 (F-SVR-001 root-cause vs fail-loud):** **REVISE DECISION TREE.** Root-cause fix is likely achievable in one session (probable shape guard in sidecar projection path), while unconditional fail-loud could be destabilizing because `_write_sidecar_L_json` is intentionally non-fatal by contract. Make (a) mandatory first; (b) only with guardrails and explicit impact note.
8. **Q8 (requirements audit method):** **SUFFICIENT if scoped.** `rg` import audit + runtime smoke is adequate for this session; `pipreqs` not required.
9. **Q9 (RED-then-GREEN proof):** **GOOD.** Same pattern as proper-fix and still valuable.
10. **Q10 (optional grep step):** **SHOULD BE MANDATORY.** Optional enforcement undercuts the architectural claim.
11. **Q11 (test count):** **ADEQUATE baseline** if tests assert channel semantics correctly (see required edit below re `/api/state/path`).
12. **Q12 (12 gates):** **GOOD COUNT**, but add one gate for mandatory invariant enforcement if Q10 is promoted.
13. **Q13 (out-of-scope creep control):** **GOOD/TIGHT ENOUGH.** It explicitly defers broad repo audit and server handler unification.
14. **Q14 (deeper smell):** **YES, known smell exists**: mutation routing discipline is distributed/manual. This spec mitigates via invariant + enforcement; without mandatory enforcement, smell remains.
15. **Q15 (pattern vs two-site patch):** **CURRENTLY MOSTLY SITE-LEVEL.** With Phase 3.4 optional, protections are weak. Promote enforcement to mandatory CI gate (grep or lint) and this becomes a real pattern-level fix.

### Required edits before ship

- **R1 — Fix test strategy wording in Phase 1.3:**  
  Replace "`/api/state/path` spy should fire" with assertions against actual mutation endpoints invoked via `pathappPatch` (e.g., `/api/stitch_editor/preview`, `/api/stitch_editor/bake`, `/api/video/set_active`, `/api/video/create`) plus payload assertions for injected scope keys and 409/423 behavior.
- **R2 — Correct Stitcher action-key/catalog plan in Phase 2.1:**  
  Explicitly require adding/using valid `MUTATION_ENDPOINTS` keys for preview/bake/save (aligned with current endpoint typing). Remove ambiguous placeholder names (`stitch_editor_preview` etc.) unless those keys are created in `endpoints.ts`.
- **R3 — Q6 compatibility guardrail:**  
  Add a pre-implementation verification step: confirm `pathappPatch(..., endpointKey, body)` compiles and routes for all 5 sites before writing tests; if not, treat as planned catalog update (not surprise scope).
- **R4 — Q7 decision tree hardening:**  
  Make root-cause fix for F-SVR-001 the default deliverable; if fallback fail-loud is used, require explicit note on non-fatal contract impact and create follow-up blocker in same PR.
- **R5 — Promote Phase 3.4 to mandatory:**  
  Convert optional grep/lint invariant into a required gate and add corresponding verification gate (e.g., G13). This is required for Q15 pattern-level closure.
- **R6 — Keep §10 out-of-scope boundary explicit:**  
  Preserve "no broad audit of all components" language, but add one sentence: "New violations discovered incidentally are logged as blockers, not fixed in this session unless they are in the five planned mutation sites."

### Final recommendation

After R1-R6, this spec is approvable and will represent a true architectural fix rather than a one-off patch set.

---

## §15 R1-R6 fold log (2026-05-04 post-Cursor)

All 6 required edits from §14 folded into the spec body. Mapping:

| Cursor required edit | Where it landed |
|---|---|
| R1 — Fix test strategy wording (no `/api/state/path`) | §4.2 TDD flow — assertions rewritten to target real mutation endpoints + scope-key auto-injection in body |
| R2 — Stitcher action-key/catalog plan | §5 Phase 2.1.0 (NEW) — extends `MUTATION_ENDPOINTS` with `stitch_preview` + `stitch_bake` BEFORE the fetch conversions; §5 Phase 2.1.1 — scope-guard decision for `_handle_stitch_preview` |
| R3 — Pre-implementation compile/routing verification | §5 Phase 0.5 (NEW) — verify pathappPatch routes for all 5 sites + read server handlers + decide preview scope-guard before tests |
| R4 — F-SVR-001 decision tree hardening | §5 Phase 2.3 — root-cause now MANDATORY default; fail-loud only as guarded fallback with structured logging + blocker creation, NOT unconditional raise (which would break non-fatal contract) |
| R5 — Promote Phase 3.4 to mandatory | §5 Phase 3.4 — full CI grep YAML provided; G13 added to gate list (now 13 gates, was 12); RED-then-GREEN proof for the gate itself required |
| R6 — Incidentally-found violation handling | §10 — explicit rule: log new violations as blockers, don't fix in this session; mandatory grep gate then forces next session to address |

Verified against actual code 2026-05-04:
- pathappPatch at `client.ts:175` confirmed to route via `MUTATION_ENDPOINTS[endpoint]` (not `/api/state/path`) — Cursor R1 was correct
- `endpoints.ts:49-107` confirmed missing `stitch_preview` + `stitch_bake` keys; `stitch_save_job` + `video_set_active` + `video_create` present — Cursor R2 was correct

Spec now ready for terminal handoff.

---

## §16 Wave-1 framing — this session within a larger program (added 2026-05-04 per Kim "do not leave bugs")

This architectural-fix session is **Wave 1** of the comprehensive retroactive coverage program defined in:

`Production/docs/STORYBOARD_V59_COMPREHENSIVE_RETROACTIVE_COVERAGE_PLAN_v1.md`

That program is a 6-wave multi-session plan responding to Kim's 2026-05-04 direction: do not leave bugs. **All 6 waves are mandatory; none are optional.** This session ships:

- The 4 fixes from Wave 1 (F-S2-001, F-S2-002, F-SVR-001, F-CI-001)
- The mandatory `MUTATION_CHANNEL_INVARIANT_V1` grep gate (Phase 3.4 / G13) which is **structurally retroactive across the whole client tree** for the F-S2 class — making this gate the prototype for similar gates in later waves

After this session ships, subsequent waves run per the program plan §2:
- Wave 2a: Beat Generator + Storyboard edges (uncovered by retroactive sprint v1)
- Wave 2b: Phase A/B producers (after S5.5f ships)
- Wave 2c: Production Map + scope/event management
- Wave 2d: Scope/state management edges
- Wave 2e: Library / cropper / asset system
- Wave 3: Mutation channel comprehensive (all MUTATION_ENDPOINTS consumers)
- Wave 4: Server-side audit (silent-failure pattern, drain protocol, snapshot consistency)
- Wave 5: Static analysis pass (TypeScript strict, ESLint expansion, mypy)
- Wave 6: Manual code review (highest-risk infrastructure)

**No "core 3" optimization.** All 6 waves run end-to-end. Honest cost: ~24-32 hours of dedicated retroactive work over weeks/months, interleaved with forward feature sessions via worktree parallelism.

**Honest limit acknowledged in plan §0:** even with all 6 waves, "zero bugs forever" is not a state any methodology can guarantee. What the program delivers is high confidence in covered surfaces + structural enforcement preventing recurrence of every pattern surfaced + a documented trail of what was checked. Bug classes specifically out of scope: performance regressions, visual regressions, a11y, cross-browser, mobile, security (each is its own program if pursued).

This Wave 1 session does NOT execute the rest of the plan. It executes only the architectural-fix scope. The plan is referenced here so Cursor can sanity-check the program-level approach alongside the session-level spec.
