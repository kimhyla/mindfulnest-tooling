# V59 Phase B (S5.5e-pass2) — Fresh Terminal Handoff

**For:** Fresh Claude Code terminal session
**Spec:** `Production/docs/V59_FEATURES_BUILD_SPEC_v1.md` §4 Phase B (Cursor v8 REVISE-BEFORE-SHIP folded; Cursor v9 SHIP confirmed)
**Phase:** B of E (Storyboard tab feature completion + ProjectSelector cleanup + ProductionMap fixes)
**Classification:** Tier C (escalated per Cursor v8 Q8 — cross-cutting + new contracts)
**Predecessor session:** Phase A (S5.5c-pass2) — completed 2026-05-06; preflight id=206; activity_log COMPLETE row id=1589

---

## Phase A closeout summary (predecessor handoff captured here for traceability)

Phase A shipped 13 scope items + 11 verification gates clean. Highlights:

- **A-1 py_compile clean.** No syntax errors in production_server.py.
- **A-2 npm run build clean.** Vite build → `dist/index.html` 197.26 KB; no TS errors.
- **A-3 server restart + /api/health 200.** Server PID 49300 started 2026-05-06 15:53:47 PT; py mtime 2026-05-06 15:48:55 PT (PID > mtime ✓ per Rule 29).
- **A-4 BG-22 cropper smoke PASS.** Posted real 800×600 PNG to `/api/cr/save-crop`; got asset_id=79; queried `prod_assets/79` and confirmed `iteration_notes` = `"BG cropper output for beat beat_99_smoke_a4 from source key smoke_a4_source (4:3 crop, 800x600 WebP)"`; Rule 34 find_asset-style search by phrase returned the row. Asset has `tags=['bg_cropper','crop_4x3','delivery']`, `library=true`, `produced_by_skill='v59_bg_cropper'`, `module_id=1`, `beat_id='beat_99_smoke_a4'`.
- **A-5 BG-37 activity log smoke PASS.** Posted to `/api/bg/accept-beats` with one beat; got `prod_activity_log` row id=1588 with `action='BEAT_GEN_ACCEPT_ALL'`, `performed_by='v59_bg_accept_beats'`, `details.selection_map={beat_99_smoke_a5: smoke_a5_key}`, `details.event_id='Event_1'`, `details.target='intro'`, `details.accepted_count=1`, `details.ld='BG_ACCEPT_BEATS_ACTIVITY_LOG_V1'`.
- **A-6 BG-34/35 conditional render** — DEFERRED to Kim browser smoke per spec §0.10. Modal primitives present; warn modal lists unset beat_ids when triggered with incomplete selection; confirm modal uses readyCount.
- **A-7 CC-17 tier filter** — DEFERRED to Kim browser smoke per spec §0.10. TIER_TO_FILTER_MAP wired client-side per Kim BS3 lock 2026-05-06 (no schema change). Default=images. Persists in localStorage `mn.library.tier`.
- **A-8 CC-18 search box** — DEFERRED to Kim browser smoke per spec §0.10. Substring match on file_name + display_name + key + iteration_notes; debounced 300ms; combines with tier filter.
- **A-9 CC-19 hover preview** — DEFERRED to Kim browser smoke per spec §0.10 (image 320px max; audio inline + video muted preview shells reserved for Phase D when those tiers populate; click sticky-pins).
- **A-10 activity_log row S5_5C_PASS2_COMPLETE** — written.
- **A-11 LDs registered (read-back verified):**
  - `LIBRARY_TIER_FILTER_V1` (id=542, severity=SOFT)
  - `BG_ACCEPT_BEATS_ACTIVITY_LOG_V1` (id=543, severity=HARD)

**Spec-vs-reality deviations logged (per spec §0.9):**

1. **BG-37 line range +5-line drift.** Spec said `production_server.py:9227-9311`; function actually ends at 9316. Insertion landed correctly between the seed-partition try/except and the final `_send_json` (line ~9332 post-edit). **Resolution:** used the corrected range per Kim BS2 lock 2026-05-06.
2. **BG-22 asset_type rename.** Legacy direct write used `asset_type='crop_4x3'` against `prod_visual_assets`. registered_write's `_ACCEPTED_ASSET_TYPES` whitelist requires `still_delivery` per Rule 6.2 + `prod_assets` (not `prod_visual_assets`). **Resolution:** asset_type='still_delivery', tags=['bg_cropper','crop_4x3','delivery'] preserves the legacy descriptor; legacy `prod_visual_assets` writes removed (was duplicate of canonical prod_assets registry). Phase E asset findability cleanup may reconcile any remaining `prod_visual_assets` references elsewhere.
3. **BG-22 module_id=1 + library=True.** Cropper output is module-agnostic; per `_MODULE_MAP` convention "use any valid module_id (typically 1) + library=True". Documented as expected behavior.
4. **CC-17 tier mapping for non-image tiers.** cr_library currently returns image-only items; ambient/sfx/transitions/watercolors tiers will return zero results until Phase D extends the data source per spec §1 Phase D scope. UI displays "No items in tier X yet (Phase D will extend the data source)."
5. **CC-16 image holder.** Spec said "Add drop target on Storyboard image holders (PREP for Phase B SB-14)." Phase A added a real visible drop zone in BeatCard with image preview when `beat.image_path` is set, calling `assign_image` endpoint on drop. Phase B SB-14 will polish the visual treatment and add the Assign/Inject buttons; the drop contract is already wired.
6. **BG-9 / BG-34/35 / BG-5 / BG-18 multiplexed through a single `BgModalState` machine** in BgTab.tsx. Single-modal stack invariant per Modal.tsx LD UI_PRIMITIVES_SHARED_V1 + Cursor v8 Q2.

**Files changed in Phase A:**

- `Production/tools/production_server.py` — `_handle_bg_accept_beats` (BG-37 activity log) + `_handle_cr_save_crop` (BG-22/C-9 registered_write refactor)
- `Production/tools/storyboard-v2/src/components/BgTab.tsx` — Modal state machine, BG-9, BG-17 thumb class, BG-34/35 modals, BG-5/8/18 buttons, BG-18 remove ref handler
- `Production/tools/storyboard-v2/src/components/LibraryPanel.tsx` — CC-17 tier filter, CC-18 search, CC-19 preview overlay (full rewrite preserving CC-15 drag wiring)
- `Production/tools/storyboard-v2/src/components/StoryboardTab.tsx` — CC-16 BeatImageHolder component + drop zone
- `Production/tools/storyboard-v2/src/app.css` — `.mn-bg-ref-thumb`, `.mn-bg-ref-remove-btn`, `.mn-bg-stage-chip-edit`, `.mn-bg-chip-edit-input`, `.mn-bg-insert-after`, `.mn-bg-modal-unset-list`, `.mn-storyboard-image-drop-zone`, `.mn-library-controls`, `.mn-library-search`, `.mn-library-tier-select`, `.mn-library-preview` family

**Server state at handoff:** PID 49300 on :5111; freshly restarted post-edit; Event_1 pinned.

**Browser smoke gates Kim should run before Phase B begins:**

1. **A-6 BG-34/35**: Open Beat Generator → mark some beats accepted, leave others unset → click "Accept All to Storyboard" → confirm warn modal lists unset beat_ids → click "Continue anyway" → confirm 2nd modal shows "Lock in N selections..." → click "Lock in & advance" → confirm Toast success message.
2. **A-7 CC-17**: Open the v59 storyboard tool → switch tier dropdown from "images" to "sfx" or "ambient" → confirm list narrows to 0 items (expected — Phase D extends data source) → switch back to "images" → list repopulates. Reload page → tier setting persists.
3. **A-8 CC-18**: With "images" tier selected, type a substring in the search box → list narrows after ~300ms.
4. **A-9 CC-19**: Hover an image library item ~500ms → preview overlay appears in lower-right with the image at ≤320px → click the tile → preview pins with a close X → click another tile → preview switches → click outside → preview unpins.
5. **A-6 BG-9**: Open Beat Generator → click ✕ on a beat card → modal appears with "Delete beat ...?" → click Cancel → modal closes, beat remains → click ✕ again → confirm Delete → beat removed.
6. **BG-5/8/18**: Open Beat Generator → on a beat with chips, click ✎ pencil → modal lets you edit chip text → save → text updates. Hover a beat card → "+ Insert beat" button reveals between cards. Hover a ref slot with image → ✕ corner button reveals → click → modal confirm → ref clears.

If any gate fails, log a `S5_5C_DEVIATION_<n>` row in prod_activity_log per spec §0.9 before starting Phase B.

---

## Pre-paste checklist (Kim — Phase B specific)

- [ ] Phase A browser smoke gates 1–6 above PASSED
- [ ] `Production/docs/V59_FEATURES_BUILD_SPEC_v1.md` §4 Phase B reviewed
- [ ] Server still on :5111 (or restarted to pick up any further A1 fixes Kim wants first)
- [ ] State.json files at v3 shape (no Phase A changes touched state shape)
- [ ] Fresh terminal window, fresh `claude` session, no prior context

---

## Paste this into the fresh terminal:

```
═══════════════════════════════════════════════════════════════════
You are executing Phase B (S5.5e-pass2) of the v59 Features Build
per Production/docs/V59_FEATURES_BUILD_SPEC_v1.md.

CONTEXT: Phase A (S5.5c-pass2) shipped 2026-05-06 — preflight id=206;
2 new LDs registered (LIBRARY_TIER_FILTER_V1 id=542 SOFT;
BG_ACCEPT_BEATS_ACTIVITY_LOG_V1 id=543 HARD). Activity log row
S5_5C_PASS2_COMPLETE captures the gate summary + 6 spec deviations.

This is the SECOND of 5 atomic sequential sessions (A → B → C → D → E).
Phase B = Storyboard tab feature completion + ProjectSelector cleanup
+ ProductionMap fixes. Tier C (escalated per Cursor v8 Q8 — cross-cutting
scope + new image-management contracts + ProductionMap mutation-channel
refactor). 4+4 advocate+counter agents per Rule 19 Tier C.

PRE-EXECUTION (per spec §14, do EVERY box BEFORE any edit):

[ ] Read Production/docs/V59_FEATURES_BUILD_SPEC_v1.md §0 fully
    (Mandatory Operating Mode for Executing Sessions)
[ ] Load zero-error-qa skill (governs Phase 0 + DS-1 through DS-19)
[ ] Phase 0 classification: Tier C (Architectural — cross-cutting +
    new contracts SB-3/12/13/14 + ProductionMap raw fetch refactor +
    SB-21 milestone-scope partition write-target Layer 4 contract)
[ ] Spawn 4+4 advocate+counter agents per Tier C Phase 0 architectural
    review (per spec §4 Phase B Phase 0 + Rule 19)
[ ] Write prod_preflight_reviews row via try_post_or_queue (Rule 35)
    BEFORE any edit; reference predecessor preflight id=206 + this
    spec
[ ] LD existence preflight (per spec §0.1 Cursor v8 Q9): Phase B
    introduces 1 new LD (STORYBOARD_IMAGE_HOLDER_V1) — no AMEND/
    SUPERSEDE in this phase
[ ] Rule 36 applicability gate: Phase B is mostly TSX work; no Path B
    HTML patches expected. Document as N/A.
[ ] Read source files cited in spec §4 Phase B FRESH (not from memory):
    - Production/tools/storyboard-v2/src/components/StoryboardTab.tsx
    - Production/tools/storyboard-v2/src/components/EventSelector.tsx
    - Production/tools/storyboard-v2/src/components/ProjectSelector.tsx
    - Production/tools/storyboard-v2/src/components/ProductionMapTab.tsx
    - Production/tools/storyboard-v2/src/components/ScopeBoundary.tsx
    - Production/tools/storyboard-v2/src/state/scope.ts
    - Production/tools/storyboard-v2/src/api/endpoints.ts
    - Production/tools/production_server.py:6322-6370 (event_create)
    - Production/tools/production_server.py:8765-8768 (production_map cap)
[ ] Confirm endpoints catalog: bg_add_beat, bg_delete_beat,
    assign_image, inject_image, scene_assemble, video_set_active,
    event_load, event_create are all in MUTATION_ENDPOINTS
[ ] Server staleness baseline: lsof -ti:5111 + ps -p <PID> -o lstart +
    stat Production/tools/production_server.py mtime

PHASE B SCOPE (per spec §4 Phase B):

B1 — Storyboard image management (~90 min):
  - SB-3: BeatCard renders beat.image_path or fallback gpt_options
  - SB-12/13: Assign/Inject Image buttons
  - SB-14: Drop target uses CC-16 infrastructure (Phase A delivered)
  - SB-15: Reorder controls (drag-drop; fallback to up/down arrows)
  - SB-16/17: Add/Delete Beat buttons with Modal confirm (BG-9 pattern)
  - SB-22/23/24: Single dynamic-label export button
  - SB-21: Milestone scope smoke (Already WIRED per Agent B)

B2 — ProjectSelector + TargetVideoSelector cleanup (~30 min):
  - CC-7: Rename VideoSelector.tsx → TargetVideoSelector.tsx
  - CC-9: Hide TargetVideoSelector in milestone scope
  - CC-11: Reset activeTargetVideo on event load
  - CC-5: Verify Stitcher stays enabled in milestone scope (Q3 lock)

B3 — Production Map fixes (~30 min):
  - CC-31: Verify all 59 V1 modules render (remove pagination cap)
  - CC-34: Refactor ProductionMapTab onCellClick → pathappPatch

B4 — Module SFX cues docs (~15 min):
  - CC-33: Document state.module_sfx_cues vs slot.sfx_cues[]

B5 — Event create flow verification (~10 min):
  - EP-24: Already WIRED — smoke create new event flow

ESCAPE HATCHES (Phase B specific, per spec §4 Phase B):

- SB-21 milestone-scope smoke fails → RELEASE-BLOCKER, surface
- SB-15 drag-drop reorder fragile → fall back to up/down arrows
- ProductionMap endpoint cap (CC-31) needs backend change beyond
  scope → defer + document
- TargetVideoSelector rename (CC-7) breaks any imports not caught
  by TS check → STOP, fix all import sites before proceed

VERIFICATION GATES (per spec §4 Phase B — all must PASS before
COMPLETE; B-15/16 mandatory; B-3 through B-14 may DEFER browser):

B-1 py_compile + npm run build clean
B-2 Server restart + /api/health 200; PID lstart > .py mtime
B-3 SB-3 BeatCard renders thumbnail
B-4 SB-12/13 Assign/Inject Image buttons functional
B-5 SB-14 drag library image → BeatCard → image assigns
B-6 SB-15 reorder beats persist across reload
B-7 SB-16/17 Add Beat / Delete Beat work; confirm modal on delete
B-8 SB-21 milestone smoke — state.videos.standalone path written
B-9 SB-22/23/24 dynamic-label button shows correct target name
B-10 CC-7/9 TargetVideoSelector renamed, hidden in milestone scope
B-11 CC-11 switch event → activeTargetVideo resets to intro
B-12 CC-31 Production Map renders all 59 modules
B-13 CC-34 ProductionMap event_load uses pathappPatch (not raw fetch)
B-14 EP-24 event create + modal flow smoke
B-15 Activity log row S5_5E_PASS2_COMPLETE
B-16 New LD STORYBOARD_IMAGE_HOLDER_V1 registered + read-back verified

END-OF-PHASE CHECKLIST (per spec §14):

[ ] All 16 smoke gates above PASS (B-1 through B-16)
[ ] py_compile + npm run build clean
[ ] Server restart + /api/health 200; PID lstart > .py mtime (Rule 29)
[ ] All Directus writes verified via try_post_or_queue read-back
[ ] LD query snapshot (LIBRARY_TIER_FILTER_V1 id=542 still active;
    BG_ACCEPT_BEATS_ACTIVITY_LOG_V1 id=543 still active; new LD
    STORYBOARD_IMAGE_HOLDER_V1 read-back ok)
[ ] Rule 36 audit run/skipped with reason documented
[ ] Explicit evidence artifact links/IDs for each gate captured in
    phase artifacts
[ ] "Unresolved inferred claims = 0" check per Rule 24
[ ] Activity log row S5_5E_PASS2_COMPLETE written
[ ] Independent tail-end verifier subagent run; verdict captured
[ ] Browser smoke checklist drafted for Kim hands-on
[ ] Phase C handoff stub written:
    Production/docs/V59_S5_5_F_PASS2_HANDOFF.md

═══ Begin ═══

Run Phase 0 pre-flight now per spec §0.1. Tier C: full 4+4 agent
spawn, write preflight row, reference id=206 as predecessor + this
spec. Then execute B1 → B2 → B3 → B4 → B5 in order. Provide proof
of successful execution after each sub-phase. Report back when all
16 verification gates pass.
═══════════════════════════════════════════════════════════════════
```

---

## Notes for Kim (post-paste)

**Browser smoke gates** — A-6/A-7/A-8/A-9 from Phase A are still pending Kim hands-on; please complete those and surface any failures BEFORE pasting the Phase B prompt above. Phase B's B-3 through B-14 are also browser-dependent; defer at the executing session's discretion per spec §0.10 with explicit DEFERRED markers.

**3 phases remain after B:** C → D → E. C is the critical one (PB-2 RELEASE-BLOCKER preflight + standardized_assets prep + watercolor animate Layer 6 smoke).

---

**End of Phase B handoff.**
