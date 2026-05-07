# Storyboard v59 — Video Role Picker Spec v1

**Date:** 2026-05-05
**Classification:** ARCHITECTURAL FIX — surfaces a UI/UX gap in the v3 scope architecture; no state shape change, no new server endpoints (one server contract clarification + one test).
**Predecessor:** S5.5g shipped 2026-05-04 (PR #5 `d11e573`); v59 client = FEATURE-COMPLETE on paper. Kim's day-1 testing discovered that the scope picker is incomplete.
**Working tree:** `~/Projects/mindfulnest-tooling/` (main, post-PR-#5)

## §1 What Kim discovered (real bug, not paper-only)

Kim opened the v59 client at `http://localhost:5111/` and immediately surfaced three symptoms that all trace to ONE root cause:

1. **Top-right Event picker has no companion Video Role picker.** She can pick `Event_2` but cannot pick "Event_2 intro" vs "Event_2 resolution" vs "Event_2 phase_a" etc.
2. **Production Map "intro" in every row** — the `video_role` column shows `intro` for all 53 modules because that's the implicit default when nothing has been explicitly selected.
3. **Event picker change → `409 Conflict` on `/api/v2/event-state`** — the scope chip stays at `Event_1:global:v1` even though dropdown shows `Event_2 (current)`. Likely downstream of the same gap (server expects full scope; client provides partial).

**Root cause:** the v3 architecture supports `state.videos.{intro, resolution, standalone}` + `state.phase_a` + `state.phase_b` — five distinct working surfaces per event/milestone. The `activeTargetVideo` signal exists in `src/state/scope.ts`. The `VideoSelector` component exists in `src/components/VideoSelector.tsx` (we just migrated its 2 fetch sites in Wave 1). But the **picker is not visible in the current layout** — nowhere in the UI exposes the role dimension.

**Terminology note:** Kim's "Win video" = architecture's `resolution`. Same partition, informal name. UI labels can show "Resolution" with optional "(Win)" hint if helpful.

## §2 Task

Land 5 things:

1. **Surface a Video Role picker** — make `VideoSelector` (or an equivalent) visibly accessible in the layout, next to or below the Event picker.
2. **Wire it to `activeTargetVideo` signal** — picker change updates the signal; signal change re-fetches relevant tab state per the proper-fix R1 pattern.
3. **Make picker context-sensitive — picker exposes only `state.videos.{}` partitions** (per Cursor R1 — Phase A/B are NOT video roles; they are top-level state surfaces with dedicated tabs):
   - Event scope → roles available: `intro`, `resolution` (the 2 multi-beat composers in `state.videos.{}`)
   - Milestone scope → role available: `standalone` only (per LD-486 milestone independence)
   - **Phase A and Phase B are NOT in the picker.** They're top-level state shapes (`state.phase_a`, `state.phase_b`) accessed via their dedicated tabs (PhaseProducer with phase='a' or 'b'). The picker selecting `intro` doesn't switch user to Phase A — Phase A is reachable via the Phase A tab regardless of picker state. Tab visibility per LD-486 (Phase A/B tabs disabled in milestone scope).
4. **Production Map per-role columns — derived from on-disk artifacts, NOT a schema migration** (per Cursor R3): instead of one `video_role` column showing "intro" implicitly, render per-role status per module via existing on-disk file presence checks. Columns reflect the 4 stitched-output components: intro / phase_a / phase_b / resolution + final_concat. `_handle_production_map` already joins `prod_modules` + on-disk segment artifacts (per its docstring at `production_server.py:8508`); this fix EXTENDS the on-disk scan to check each role's artifact file. **No `prod_modules` schema migration; no new Directus columns.**
5. **`/api/v2/event-state` 409 — audit, then fix the mismatch** (per Cursor R2): Phase A.5 audits the server handler + the client call site to determine the actual cause. Phase G applies whatever fix the audit reveals (server contract loosening; client sending stale value; race on signal propagation; or other). The spec does NOT prescribe the fix shape upfront — only the audit-driven decision tree (see §5 Phase G).

## §3 Governing decisions

### LDs respected (do not violate)

| LD | Reason |
|---|---|
| LD-456 SCOPE_VALIDATION_V1 | 409 handling already exists; this fix should use it correctly, not bypass |
| LD-461 SCOPE_KEY_AUTO_INJECTION_V1 | pathappPatch auto-injects `scope_target_video`; this fix wires the signal that auto-injection reads |
| LD-486 (milestone independence) | Phase A/B tabs disabled in milestone scope; standalone is the only valid role |
| LD-494 TargetVideoSelector visibility per scope | THIS IS THE LD THAT PARTIALLY ANSWERS — verify what it requires; this fix may be what LD-494 always intended |
| LD-519 MUTATION_CHANNEL_INVARIANT_V1 | Picker mutation MUST go through `pathappPatch`; no raw fetch |
| DS-1..DS-12 (zero-error-qa skill) | Standard discipline |

### NEW LDs this spec writes (3)

| Key | Severity | Purpose |
|---|---|---|
| `VIDEO_ROLE_PICKER_UI_V1` | HARD | Video Role picker is mandatory UI; renders next to Event picker; shows {intro, resolution} for events / {standalone} for milestones (per Cursor R1 — Phase A/B are top-level surfaces with dedicated tabs, NOT video roles); wired to `activeTargetVideo` signal. **Stitcher tab is NOT affected by picker** — Stitcher always assembles all 4 slots (intro + phase_a + phase_b + resolution) regardless of which video_role is active in the picker (per Cursor R4). The picker scopes the Storyboard tab + Beat Generator tab to the active video_role's beats; Phase A and Phase B tabs operate on their own state surfaces independently of the picker. |
| `PRODUCTION_MAP_PER_ROLE_COLUMNS_V1` | HARD | Production Map renders per-role status columns per module (intro / phase_a / phase_b / resolution / final), not a single role column. Server `_handle_production_map` returns per-role asset presence per module. |
| `EVENT_STATE_FULL_SCOPE_CONTRACT_V1` | HARD | `/api/v2/event-state` requires `(scope_event_id, scope_target_video)` pair. Client must send both; server validates both; 409 only fires on actual mismatch, not on partial scope. |

## §4 Approach — TDD per DS-2

### §4.1 Investigate first, fix second

Before any code change, **Phase A audits**:

1. Read `src/components/VideoSelector.tsx` — what does it currently render? Why isn't it visible?
2. Read `src/state/scope.ts` — confirm `activeTargetVideo` signal type + initial value
3. Read `src/components/EventSelector.tsx` / `ProjectSelector.tsx` — where Event picker lives + how it's laid out
4. Read `src/components/StoryboardTab.tsx`, `BgTab.tsx`, etc. — see how each tab uses `activeTargetVideo` (do they read the signal? skip it?)
5. Read `production_server.py` `_handle_event_state` (search for `/api/v2/event-state`) — see what scope params it expects
6. Read `_handle_production_map` at `:8507` — see what data it returns + whether it can return per-role status
7. Capture findings in Phase A audit doc; lock decisions for Phase B+

### §4.2 TDD discipline

Per DS-2, every phase ends with: write Playwright RED → commit → CI red → implement → commit → CI green.

## §5 Implementation phases

### Phase A — Pre-flight + audit

- A.0 Branch hygiene: `cd ~/Projects/mindfulnest-tooling && git checkout main && git pull && git checkout -b claude/video-role-picker`
- A.0.1 Verify HEAD includes `d11e573` (S5.5g merge)
- A.0.2 Verify CI on main is green
- A.0.3 Verify MUTATION_CHANNEL_INVARIANT_V1 grep gate passes (per DS-5)
- A.1 Audit VideoSelector + scope.ts + tab usage of `activeTargetVideo` (per §4.1)
- A.2 Reproduce Kim's 3 symptoms locally — confirm scope chip stays stale on Event change; confirm 409 Conflict; confirm Production Map shows "intro"
- A.3 Capture findings + locked decisions in `Production/docs/STORYBOARD_V59_VIDEO_ROLE_PICKER_PHASE_A_AUDIT.md`
- A.preflight: `prod_preflight_reviews` row task_id="video-role-picker-fix-20260505"

### Phase B — RED tests for Video Role picker UI

`e2e/video_role_picker.spec.ts` — new spec file:

- VRP.1: Picker is visible in the layout (top-right or below Event picker)
- VRP.2: Event scope → picker shows 2 options (`intro`, `resolution`) — NOT 4; Phase A/B are accessed via dedicated tabs, not via this picker (per Cursor R1)
- VRP.3: Milestone scope → picker shows 1 option (`standalone`) OR is hidden entirely; Phase A/B tabs are also hidden per LD-486
- VRP.4: Picker change → `pathappPatch(scope, 'video_set_active', {...})` POSTs with auto-injected scope keys (verify via network spy per DS-1)
- VRP.5: Picker change → `activeTargetVideo` signal updates → Storyboard tab + Beat Generator tab re-fetch with new role's beats (StoryboardTab beats reload, BgTab options reload). Phase A and Phase B tabs are unaffected by picker (they read their own state surfaces). Stitcher tab is unaffected (always assembles all 4 slots; per Cursor R4).
- VRP.6: Picker change → no 409 Conflict on `/api/v2/event-state`

Run locally → RED. Commit. Push. CI red.

### Phase C — GREEN: implement picker UI + signal wiring

- C.1 Surface VideoSelector in the layout (probably extend ProjectSelector to include it, OR add a new top-bar row)
- C.2 Wire picker `onChange` → `pathappPatch(scope, 'video_set_active', {target_video})` (per LD-519 mutation channel)
- C.3 Confirm signal subscription in StoryboardTab + BgTab + Stitcher reads `activeTargetVideo` and re-fetches on change (per proper-fix R1 pattern)
- C.4 Add 200ms debounce on picker change to prevent fetch storm (per proper-fix R1 + LD-184)

Run VRP.1-VRP.6 → GREEN.

### Phase D — RED tests for Production Map per-role columns

`e2e/production_map_per_role.spec.ts` — new spec file:

- PMR.1: Production Map renders 5 per-role columns per row (instead of single video_role column)
- PMR.2: Each column shows asset presence indicator (✅ / ❌ / count)
- PMR.3: Module M1 (Event_1, fully assembled) → all 5 columns show ✅
- PMR.4: Module M7 (TBD module) → all 5 columns show appropriate placeholder (✅ for any auto-populated; ❌ for missing)
- PMR.5: Click any cell in a column → routes to that (event, role) scope (e.g., M5 phase_a cell → Event_5 + role=phase_a)

Run locally → RED. Commit. Push. CI red.

### Phase E — GREEN: extend Production Map server response + UI columns (DERIVED, not schema)

**Implementation boundary (per Cursor R3):** per-role status is DERIVED at request time from existing on-disk artifact presence. NO `prod_modules` schema migration; NO new Directus columns. The existing `_handle_production_map` docstring at `production_server.py:8508` already says "Joins prod_modules + on-disk segment artifacts" — this fix EXTENDS the on-disk scan to check each role's artifact file (intro_atomic.mp4 / phase_a_stitched.mp4 / phase_b_lipsync.mp4 / resolution_atomic.mp4 / final_atomic.mp4 — actual filenames per audit).

- E.1 Extend `_handle_production_map` at `production_server.py:8507` to compute per-role status from on-disk file presence per module (data shape change to map row: `{m_number, creature_name, intro_status, phase_a_status, phase_b_status, resolution_status, final_status}`). Phase A audit captures the exact filename pattern per role.
- E.2 Update `ProductionMapTab.tsx` columns array to render the new shape (5 status columns instead of 1 video_role column)
- E.3 Wire cell click → routes to (event, role) scope via existing `loadEvent` helper (NOT pathappPatch — event_load is sanctioned exception per blockers #50-53; loadEvent intentionally skips snapshot for event swaps)

Run PMR.1-PMR.5 → GREEN.

### Phase F — RED test for /api/v2/event-state 409 contract

`e2e/event_state_contract.spec.ts` — new spec file (or add to architectural_fix.spec.ts):

- ESC.1: Switch event from Event_1 → Event_2 with target_video='intro' → /api/v2/event-state returns 200, scope chip shows `Event_2:intro:v1`
- ESC.2: Switch event without target_video selected → either picker provides default OR server falls back to default (no 409)

Run locally → RED. Commit. Push. CI red.

### Phase G — GREEN: fix server contract OR client contract

Decision tree:
- If server requires both `(scope_event_id, scope_target_video)` and was missing the second → CLIENT FIX: ensure picker sends both
- If server is misvalidating → SERVER FIX: handler accepts default target_video when client provides only event_id
- Apply whichever the audit reveals; log the decision in audit doc + LD `EVENT_STATE_FULL_SCOPE_CONTRACT_V1`

Run ESC.1-ESC.2 → GREEN.

### Phase H — Verification gates

- H.G1 `npm run build` clean
- H.G2 Server `/api/health` 200 (Rule 29 staleness check after server.py edits)
- H.G3 All existing 91+ e2e tests still pass
- H.G4-G8: VRP.1-VRP.6 pass
- H.G9-G13: PMR.1-PMR.5 pass
- H.G14-G15: ESC.1-ESC.2 pass
- H.G16 CI workflow extension: APPEND `e2e/video_role_picker.spec.ts` + `e2e/production_map_per_role.spec.ts` + `e2e/event_state_contract.spec.ts` to test command (per DS-10)
- H.G17 Spec count after additions: 13 (still under DS-10 / §19.6.1 threshold of 15)
- H.G18 RED-then-GREEN proof captured (Phases B/D/F red commits → C/E/G green commits)
- H.G19 No new MUTATION_CHANNEL_INVARIANT_V1 violations (per DS-5 grep gate)
- H.G20 Browser smoke per LD-509 — Kim verifies picker feels right + Production Map per-role rendering looks right + event-switch is responsive (no 409, scope chip updates immediately)

### Phase I — LDs + closeout

- I.1 3 NEW LDs (HARD per §3): VIDEO_ROLE_PICKER_UI_V1, PRODUCTION_MAP_PER_ROLE_COLUMNS_V1, EVENT_STATE_FULL_SCOPE_CONTRACT_V1
- I.2 PATCH any related blockers Kim filed during testing (set is_resolved=true, resolved_at=now)
- I.3 `prod_activity_log` `VIDEO_ROLE_PICKER_FIX_COMPLETE` row
- I.4 Master overview status table append (NEW row pointing to this spec)
- I.5 Update `STORYBOARD_V59_ARCHITECTURE_OVERVIEW_v1.md` §10 — add §10.9 noting picker landed
- I.6 Update `STORYBOARD_V59_TESTING_DEBUGGING_HANDOFF.md` §6 known-issues to mark these 3 symptoms RESOLVED
- **I.7 PATCH LD-494 `TARGET_VIDEO_SELECTOR_VISIBILITY_PER_SCOPE` (per Cursor R5):** append `notes` field with reference to `STORYBOARD_V59_VIDEO_ROLE_PICKER_SPEC_v1.md` + the new `VIDEO_ROLE_PICKER_UI_V1` LD that operationalizes it. Mark LD-494 as having been the umbrella decision that this spec implements. If LD-494's `decision_text` warrants amendment to reflect the actual landed behavior, append (don't replace). Read-back verify the PATCH per Rule 35.
- I.8 Single git commit + push + `gh pr create`

## §6 Files modified / created

### Created
- `Production/docs/STORYBOARD_V59_VIDEO_ROLE_PICKER_PHASE_A_AUDIT.md`
- `Production/tools/storyboard-v2/e2e/video_role_picker.spec.ts`
- `Production/tools/storyboard-v2/e2e/production_map_per_role.spec.ts`
- `Production/tools/storyboard-v2/e2e/event_state_contract.spec.ts`

### Modified
- `Production/tools/storyboard-v2/src/components/VideoSelector.tsx` (visibility wiring; possibly add Resolution/Win label hint)
- `Production/tools/storyboard-v2/src/components/ProjectSelector.tsx` OR `src/app.tsx` (layout — surface VideoSelector visibly)
- `Production/tools/storyboard-v2/src/components/ProductionMapTab.tsx` (column array → 5 per-role columns)
- `Production/tools/storyboard-v2/src/state/scope.ts` (verify activeTargetVideo wiring; possibly tighten contract)
- `Production/tools/storyboard-v2/src/api/endpoints.ts` (verify `video_set_active` exists; from Wave 1 it should)
- `Production/tools/production_server.py` (extend `_handle_production_map` per-role response; possibly fix `_handle_event_state` contract)
- `.github/workflows/playwright_e2e.yml` (APPEND 3 new specs per DS-10)

### Directus
- 3 NEW LDs (522-524 or whatever next ID)
- 1 prod_activity_log row
- 1 prod_preflight_reviews row
- N prod_blockers PATCHes (resolved status)

## §7 Error cases / escape hatches

| Failure | Handling |
|---|---|
| Phase A audit reveals VideoSelector requires major rewrite (not just visibility) | STOP; surface to Kim — may need separate spec |
| `/api/v2/event-state` server contract is more complex than scope_target_video issue | STOP; surface — server fix may need its own spec |
| Production Map per-role data not available from existing server tables | STOP; may require schema work; defer per-role to follow-up |
| Picker change causes mass re-fetch storm degrading UX | Tighten debounce per LD-184; if still bad, add explicit "loading…" state |
| Existing tab components don't subscribe to `activeTargetVideo` correctly | Diagnose; may surface deeper signal-architecture issues |
| Phase A audit reveals "win" terminology is in master tech spec but not v3 architecture | Surface; would mean architectural amendment, not just UI fix |
| Standalone (milestone) scope picker behavior unclear | Default to "no picker visible" in milestone scope; confirm with Kim |

## §8 Out of scope (defer)

- Per-role progress indicators beyond binary asset-presence (e.g., "% complete") — UX polish
- Drag-and-drop assets between roles (cross-role workflow) — separate session
- Bulk operations across modules (e.g., "regenerate all M5 intros") — separate session
- Sprint D / Wave 3 cleanup of #50-53 event_load violations — opportunistic; this fix may incidentally close some but doesn't target them
- Sprint E server audit — separate session

## §9 Dependencies

- v59 client at HEAD of main (post-S5.5g `d11e573`)
- v3 architecture's `state.videos.{intro, resolution, standalone}` shape (already in place)
- `activeTargetVideo` signal in `src/state/scope.ts` (already exists)
- VideoSelector component (already exists; needs visibility wiring)

## §10 Notes for the executing session

- This is THE first post-merge fix session. Kim is testing v59 in production. Surface progress visibly so she can validate.
- Phase A audit IS load-bearing — do it BEFORE writing tests; the audit reveals where the picker should render and how server contract works.
- Per DS-9: NEW LDs use HARD (all three are behaviorally enforced).
- Per DS-2: TDD strict — RED tests committed BEFORE implementation. CI red proof per phase.
- Per DS-12: phase boundary commit + push; do not mid-phase checkpoint.
- Per LD-509: browser smoke "feels right?" subjective UX is Kim's; this spec adds H.G20 explicit smoke gate.
- Estimated 5-7 hours; compaction-aware checkpoint authority at phase boundaries.

## §11 Cursor review checklist

For Cursor before terminal handoff:

1. Is the 3-LD grain right? Or should the picker UI + server contract be separate LDs?
2. Phase A audit — anything I'm missing in the read-list?
3. Production Map per-role columns — is the data shape change at server side correct, or does the existing schema not support it?
4. Standalone (milestone) picker behavior — hide picker entirely OR show single locked option?
5. Could the 409 Conflict on /api/v2/event-state be from somewhere ELSE than scope partial-state? (Audit Phase A.5 should catch but worth flagging as risk.)
6. Spec count after this session: 13 (current 10 + 3 new). Approaching §19.6.1 threshold of 15. Should we consolidate?
7. Severity HARD on all 3 — defensible?
8. Is there an existing LD I'm missing that already partially specs this (LD-494 mentioned in §3)?
9. Does the picker also need to handle the Stitcher tab's slot context (Stitcher always assembles all 4 roles; picker doesn't apply there)?
10. Pattern check — any architectural smell in v3's scope model that this fix doesn't address?

Append findings as §12 if reviewing.

## §12 Cursor review findings (2026-05-05)

**Verdict:** **REVISE**

The spec addresses a real architectural usability gap and the TDD structure is strong, but there is one major model mismatch plus a few scope/contract clarifications needed before execution.

### §11 checklist answers (Q1-Q10)

1. **Q1 (3-LD grain):** Close, but slightly overlapping. UI picker + event-state contract are distinct and good as separate HARD LDs. Production Map columns can remain separate if kept as UI/API contract (not schema migration).
2. **Q2 (Phase A audit read-list):** Good list. Add explicit read of `src/app.tsx` and current top-bar layout wiring path where selector visibility is decided.
3. **Q3 (Production Map per-role columns feasibility):** Feasible from on-disk artifact/status checks without deep schema migration, but avoid implied role-model expansion unless server output contract is defined narrowly.
4. **Q4 (milestone picker behavior):** Prefer showing a single locked `standalone` option (visible state clarity) over hiding entirely, unless UI clutter is a concern. Pick one and lock it in spec text.
5. **Q5 (409 could be from elsewhere):** Yes, real risk. Could be stale generation pin, event-load sequencing, or stale scope chip update path—not only partial scope pair. Phase A.5 should explicitly include event generation/version checks.
6. **Q6 (spec count growth):** 13 is still fine under the 15 threshold. No consolidation required now.
7. **Q7 (HARD severities):** Defensible for picker + event-state contract. Production Map columns can still be HARD if treated as behaviorally enforced output contract.
8. **Q8 (LD-494 interaction):** This fix appears to be what LD-494 intended. Recommend PATCH LD-494 with explicit pointer to this spec/closure rather than leaving parallel intent ambiguous.
9. **Q9 (Stitcher tab context):** Correct to skip picker semantics inside Stitcher composition logic; spec should explicitly state picker does not alter Stitcher 4-slot bake semantics.
10. **Q10 (architectural smell):** Main smell is scope model drift in terminology/types across docs/components (target video roles vs phase surfaces), which caused this visibility gap to ship.

### Required edits before ship

- **R1 — Resolve role-model mismatch before implementation.**  
  Spec currently states event roles `{intro, phase_a, phase_b, resolution}`, but `activeTargetVideo` in code is typed/used as `{intro, resolution, standalone}`. Lock one canonical picker role set and describe how Phase A/B surfaces map (tab context vs target-video role), or this session will mutate architecture accidentally.

- **R2 — Tighten EVENT_STATE contract language to observed server/client reality.**  
  Replace prescriptive "`/api/v2/event-state` requires `(scope_event_id, scope_target_video)` pair" with "audit determines required scope tuple; fix client/server mismatch accordingly." Keep LD intent as "no false 409 on valid event switch."

- **R3 — Clarify Production Map scope for this session (no deep schema migration).**  
  Explicitly state whether per-role columns are derived from filesystem/status checks only (preferred here) and that no Directus schema migration is in scope unless Phase A proves required.

- **R4 — Add explicit Stitcher non-applicability note.**  
  In task/approach text, state picker affects event-scoped partition views and does not change Stitcher tab's 4-slot assembly semantics.

- **R5 — Add LD-494 linkage closeout step.**  
  In Phase I closeout, add "PATCH LD-494 with pointer to this spec + resolved scope visibility behavior" to prevent overlapping LD intent.

---

**End of Video Role Picker Spec v1.**

Awaiting Cursor verification per §11 checklist. After approval, fresh terminal session executes Phases A-I per DS-2 TDD discipline.

---

## §13 R1-R5 fold log (Cursor §12 R-rows folded 2026-05-05)

| Cursor required edit | Where it landed |
|---|---|
| R1 — Resolve canonical picker role model vs Phase A/B surface mapping | §1 "What Kim discovered" reframed: picker exposes only `state.videos.{}` partitions (intro/resolution/standalone). §2 task #3 rewritten — Phase A/B explicitly NOT in picker (they're top-level state surfaces with dedicated tabs). §3 NEW LD `VIDEO_ROLE_PICKER_UI_V1` description updated to specify 2-option picker for events (intro/resolution) + standalone for milestones; explicit non-effect on Phase A/B tabs. §5 Phase B VRP.2 + VRP.5 corrected — 2 options not 4; Phase A/B tabs unaffected by picker. |
| R2 — Rephrase /api/v2/event-state contract claim to "audit then fix" | §2 task #5 rewritten — audit-driven; Phase A.5 audits + Phase G applies whatever fix the audit reveals. Spec does NOT prescribe fix shape upfront; only the decision tree (server contract loosening / client stale signal / race / other). |
| R3 — Clarify Production Map per-role implementation boundary | §2 task #4 + §5 Phase E header explicit: per-role status DERIVED at request time from existing on-disk artifact presence. NO `prod_modules` schema migration. NO new Directus columns. Existing `_handle_production_map` docstring already says "joins prod_modules + on-disk segment artifacts" — this fix EXTENDS the on-disk scan only. |
| R4 — Explicitly state picker does not alter Stitcher 4-slot semantics | §3 NEW LD `VIDEO_ROLE_PICKER_UI_V1` description appended: "Stitcher tab is NOT affected by picker — Stitcher always assembles all 4 slots regardless of which video_role is active in picker." §5 Phase B VRP.5 amended: "Stitcher tab is unaffected (always assembles all 4 slots)." Picker scopes ONLY Storyboard tab + Beat Generator tab to active video_role's beats; Phase A/B tabs operate on their own state surfaces; Stitcher operates on the union (all 4). |
| R5 — Closeout step to patch/link LD-494 | §5 Phase I added new substep I.7: PATCH LD-494 `TARGET_VIDEO_SELECTOR_VISIBILITY_PER_SCOPE` notes field with reference to this spec + the new `VIDEO_ROLE_PICKER_UI_V1` LD. Marks LD-494 as the umbrella decision this spec implements. Read-back verified per Rule 35. |

All 5 edits are mechanical applications of Cursor's required language. R1 was the most substantive — surfaced a real architectural conflation (picker options vs top-level surfaces) that would have produced the wrong UI without correction. R3 prevents accidental schema-migration scope creep. R4 + R5 add explicit non-effects + closeout linkage that prevent future drift.

Spec ready for Cursor v2 verification pass.
