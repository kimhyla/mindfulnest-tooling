# Storyboard v59 — Sub-Session S5.5g Spec v1

**Date:** 2026-05-03
**Classification:** EXECUTION SPEC — Stitcher SFX/transitions/trims port + Production Map V1 verification
**Predecessor:** S5.5f (Phase A/B feature parity)
**Master overview:** `STORYBOARD_V59_FEATURE_PARITY_MASTER_OVERVIEW.md`
**This is the LAST session in the v59 feature parity arc.**

## §1 Task

Port SFX cue placement + per-slot transitions + per-slot trims FROM the standalone `/stitch_editor` tool INTO the v59 Stitcher tab. Verify Production Map renders all V1 modules after S5.5e populated `prod_modules`. Fix multi-event mapping in Production Map (currently uses Event_1 as canonical for all modules).

After this session: v59 Stitcher tab has full feature parity with `/stitch_editor`. Kim can compose final modules end-to-end in the v59 client without touching the legacy tool. `/stitch_editor` retirement is now possible (defer actual deletion until Kim has used v59 Stitcher for a complete production cycle).

## §2 Governing Decisions

### LDs respected (do not violate)

| LD | Key | Reason |
|---|---|---|
| LD-280 | RENDERING_ARCHITECTURE_SINGLE_MP4_ATOMIC_V1 | Module ships as ONE atomic MP4; `final_atomic_mp4` reserved for Stitcher 4-slot bake |
| LD-284 | NORMALIZATION_BEFORE_CONCAT_V1 | All clips normalized to LD-284 strict spec before concat |
| LD-423 | STITCH_EDITOR_UNIVERSAL_V1 | N-slot variable assembly: 1-slot for milestones, 4-slot for module |
| LD-465 | PRODUCTION_MAP_V1 | Production Map endpoint contract |
| LD-466 | EXPORT_TO_STITCHER_V1 | Phase A/B → Stitcher slot binding |
| LD-471 | STITCHER_FULL_UI_V1 | Stitcher tab full UI scope |
| LD-490 | SCENE_ASSEMBLE_ENDPOINT_V1 | `/api/scene/assemble` Stage 2 orchestration |
| LD-493 | STORYBOARD_SEND_OUT_PROVENANCE_V1 | iteration_notes + source_beat_asset_ids preservation |

### NEW LDs this spec writes (5)

| Key | Severity | Purpose |
|---|---|---|
| `STITCHER_SFX_CUE_UI_V1` | HIGH | Drag SFX from LibraryPanel → drop on slot timeline → cue created with offset_ms, volume, fadein, fadeout. Reuses CuePopover from S5.5f. Backend at `/api/timeline/cues` already exists. |
| `STITCHER_TRANSITIONS_V1` | HIGH | Per-boundary transition selector: crossfade / hard cut / dissolve. Renders between adjacent slots. Backend `trans_<after_slot>` cue synthesis already exists at server.py:14824. |
| `STITCHER_PER_SLOT_TRIMS_V1` | HIGH | Per-slot in/out trim handles via `<video>` scrubber. Backend extension OR reuse `POST /api/beat/trim` pattern. |
| `STITCHER_RAW_FETCH_MIGRATED_V1` | MEDIUM | Migrate raw fetches at StitcherTab.tsx:102/128/170 + ProductionMapTab.tsx:114 to `pathappPatch` per Cursor v7 cleanup. |
| `PRODUCTION_MAP_MULTI_EVENT_MAPPING_V1` | MEDIUM | Production Map cell click routes to the correct event_dir per module (currently uses Event_1 for all). Fix at server.py:8434. |

## §3 Approach

### §3.1 Stitcher tab layout (extended from current 4-slot strip)

**Current `StitcherTab.tsx` (302 lines):** 4 slots with Ambient + Preview + Loudnorm + Bake. Standalone mode = 1 slot.

**Extended layout:**

```
┌─ Stitcher — Module mode ────────────────────────────────┐
│ scope: Event_1:global:v5                                 │
├─────────────────────────────────────────────────────────┤
│ ┌─ Intro ──────┬─ Phase A ─────┬─ Phase B ─────┬─ Resolution ─┐
│ │ scene.mp4    │ stitched.mp4  │ lipsync.mp4   │ scene.mp4    │
│ │ ┌──────────┐ │ ┌──────────┐  │ ┌──────────┐  │ ┌──────────┐ │
│ │ │waveform+ │ │ │waveform+ │  │ │waveform+ │  │ │waveform+ │ │
│ │ │SFX cues  │ │ │SFX cues  │  │ │SFX cues  │  │ │SFX cues  │ │
│ │ └──────────┘ │ └──────────┘  │ └──────────┘  │ └──────────┘ │
│ │ trim: ──●●── │ trim: ──●●──  │ trim: ──●●──  │ trim: ──●●── │
│ │ Ambient: [▼] │ Ambient: [▼]  │ Ambient: [▼]  │ Ambient: [▼] │
│ │ [Preview]    │ [Preview]     │ [Preview]     │ [Preview]    │
│ └──────────────┴───────────────┴───────────────┴──────────────┘
│       │ trans: [crossfade ▼]  │ trans: [cut ▼] │ trans: [crossfade ▼]
│                                                              │
│ Module SFX cues (across all slots): drag from LibraryPanel  │
│ ┌────────────────────────────────────────────────────────┐ │
│ │ ●─ cue_sfx_001  offset 5.2s  vol 0.8  [edit] [delete] │ │
│ │ ●─ cue_amb_002  offset 30.0s vol 0.5  [edit] [delete] │ │
│ └────────────────────────────────────────────────────────┘ │
│                                                              │
│ [Bake final MP4]   [Loudnorm]   [Open in QuickTime]         │
└─────────────────────────────────────────────────────────────┘
```

### §3.2 Per-slot SFX cue placement

**Each slot gets a mini-waveform** showing audio of that slot's MP4. Cues drop on the slot's waveform.

**Drag-drop flow:**
1. LibraryPanel SFX tier (per S5.5c AssetTile + S5.5f tier filter): drag SFX tile
2. Drop on slot waveform at time position X
3. POST `/api/timeline/cues` with body `{slot: 'intro', cue_type: 'sfx', source_path: <lib_key path>, offset_ms: X, volume: 0.45 default, fadein_ms: 300, fadeout_ms: 1200}`
4. Cue marker renders on slot waveform
5. Click marker → CuePopover (reuse from S5.5f) with volume / fadein / fadeout / Delete

**Two SFX scopes:**
- **Per-slot cues**: stored in `slot.sfx_cues` (server.py:14659) — sequenced with that specific slot
- **Module-level cues**: stored in `state.module_sfx_cues` — span across the whole module timeline

UI distinguishes: drop on slot waveform → per-slot cue. Drop on the module timeline (below slots) → module-level cue.

### §3.3 Per-boundary transitions

**Between each adjacent slot pair:** render a transition selector.

```
┌─ Slot A ──┐ trans: [crossfade ▼] ┌─ Slot B ──┐
```

**Transition options:**
- `crossfade` (default) — N-second xfade overlap (default 0.5s)
- `cut` — hard transition; no overlap
- `dissolve` — slow fade through black (LD-376 fadeblack pattern from Phase A)

**Backend:** server already synthesizes `trans_<after_slot>` cues into the bake pipeline at server.py:14824. UI just needs to expose the selection. Save via `pathappPatch(scope, 'stitch_save_job', updated_job_with_transitions)`.

### §3.4 Per-slot trim controls

**Each slot gets in/out trim handles** on a scrubber rendered above the slot's waveform:

```
┌──────────────────┐
│ trim: ──●────●── │ ← in/out handles draggable
└──────────────────┘
```

**Backend:** new endpoint OR extend `POST /api/stitch_editor/job` body with per-slot `trim_in_ms`, `trim_out_ms`. Investigate in Phase A.

If new endpoint: `POST /api/stitch_editor/slot/trim` with body `{slot_key, trim_in_ms, trim_out_ms}`. Then `/api/scene/assemble` consumes these on bake.

### §3.5 Raw fetch migration

Cursor v7 flagged 4 raw fetch sites bypassing `pathappPatch`:
**Cursor v8 corrected line refs:**
- `StitcherTab.tsx ~L70, 88-89, 123, 149, 191` (preview/bake/job/library/audio_extract — multiple sites)
- `ProductionMapTab.tsx ~L114-118` (event_load)
- (Note: line refs DRIFT as code evolves. Pre-flight Phase A: re-grep `fetch\(.*\\\${SERVER_BASE}` in src/components/ to get current anchors before editing.)

Migrate all sites to `pathappPatch` per `STITCHER_RAW_FETCH_MIGRATED_V1`. Add corresponding endpoint URLs to `endpoints.ts` MUTATION_ENDPOINTS catalog. Include `/api/stitch_editor/job` POST (ambient change) in migration list.

### §3.6 Production Map multi-event mapping fix

**Current bug** (`production_server.py:8434-8436`): the Production Map endpoint glob-checks for module artifacts in `Event_1/` regardless of which event the module actually belongs to. If M5 is associated with Event_2, the map says "no Phase A asset" because it looked in Event_1.

**Fix (Cursor v8 Q4 amendment):** PREFER computed mapping derived from `GAMEPLAY_SCOPE_v3.md` + `m_number` lookup at request time. Avoid adding a Directus column unless editor-owned overrides become necessary.

**Implementation:** add `_resolve_event_dir_for_module(m_number)` helper in `production_server.py` that reads GAMEPLAY_SCOPE_v3.md (cached at module load) and returns the correct event_dir per module. Update `_handle_production_map` (`:8420`) to use this helper.

If a column IS added (Kim's call only):
- Migration: add `event_dir` to `prod_modules` schema
- Backfill: PATCH all 59 rows
- Rollback: PATCH back to null; column stays (audit trail)

### §3.7 Production Map V1 scope verification

After S5.5e populated `prod_modules`, verify:
- Map renders 59 rows (all V1 modules)
- Cell-click navigates to correct event scope per multi-event mapping fix above
- Glyph status (✅/❌/⏳) reflects real on-disk artifacts
- `MAP_CELL_NAVIGATE_EVENT` event still fires correctly

## §4 Implementation Phases

### Phase A — Pre-flight + audit /stitch_editor

**A1.** Read master overview, this spec, S5.5f COMPLETE activity log.

**A2.** Open `/stitch_editor` standalone tool (URL: `localhost:5111/stitch_editor`). Browser smoke audit:
- What SFX cue UI does it have? (drag-drop? click-to-add?)
- What transitions UI? (per-boundary? global?)
- What trim UI? (handles on scrubber? text input?)
- Document feature surface in handoff for porting reference.

**A3.** Verify backend endpoints:
- `/api/timeline/cues` POST/DELETE for SFX cues
- `/api/timeline/sfx_library` for SFX library list
- `/api/timeline/cues/bake` for cue-baked preview
- `/api/timeline/open_in_quicktime` for QT preview
- `/api/stitch_editor/audio_extract` for slot audio extract
- Per-slot trim: investigate. If missing: design + add endpoint in Phase D.

**A4.** Verify Production Map data state: `prod_modules` should have 59 rows post-S5.5e. If <59: surface to Kim (something failed in S5.5e).

**A5.** `prod_preflight_reviews` row.

### Phase B — Per-slot SFX cue placement

**B1.** Extend each slot in `StitcherTab.tsx` with mini-waveform (reuse `WaveformTimeline.tsx` from S5.5f, but height: 40px and read-only-cues mode).

**B2.** Wire drop targets per slot.

**B3.** SFX library tier filter in LibraryPanel (per S5.5c AssetTile + tier prop): toggle between image / sfx / watercolor / ambient / transitions.

**B4.** POST `/api/timeline/cues` on drop with `{slot, cue_type: 'sfx', ...}`.

**B5.** Render cue markers; click → CuePopover (reuse from S5.5f).

**B6.** Module-level SFX cue strip below slots (separate timeline spanning all slots).

**B7.** Test: drop sfx onto intro slot → cue appears → click marker → popover edits volume → save.

### Phase C — Per-boundary transitions

**C1.** Render transition selector between each adjacent slot pair (3 selectors for 4 slots: 0-1, 1-2, 2-3).

**C2.** Default values from existing `stitch_save_job` payload structure. New transitions: store in `slot.transition_to_next` field.

**C3.** Wire change → `pathappPatch(scope, 'stitch_save_job', {slots: [...with transitions]})`.

**C4.** Verify bake consumes transitions correctly (server.py:14824 pattern).

### Phase D — Per-slot trims

**D1.** Investigate backend per-slot trim. Three options:
- (a) Extend `stitch_save_job` body schema (preferred — minimal new code)
- (b) New endpoint `POST /api/stitch_editor/slot/trim` (cleaner separation)
- (c) Reuse `/api/beat/trim` pattern (likely won't work — beat-scope vs slot-scope mismatch)

**D2.** Implement chosen option per Phase A4 finding.

**D3.** UI: 2 draggable handles on each slot's scrubber. Snap to whole-second by default, hold Shift for sub-second precision.

**D4.** Save via `pathappPatch`.

**D5.** Verify bake honors trims.

### Phase E — Production Map fixes

**E1.** Verify 59 rows present.

**E2.** Investigate multi-event mapping. If `prod_modules` has no `event_dir` column: add via Directus UI or migration. Populate from GAMEPLAY_SCOPE_v3.md per-module event assignment.

**E3.** Update `_handle_production_map` (`production_server.py:8420`) to join + use correct event_dir.

**E4.** Click any cell → navigates to correct event scope (not always Event_1).

### Phase F — Raw fetch migration (Cursor v7 cleanup)

**F1.** Migrate StitcherTab.tsx:102/128/170 to `pathappPatch`. Add `stitch_preview`, `stitch_bake`, `stitch_save_job` to endpoints.ts catalog if missing.

**F2.** Migrate ProductionMapTab.tsx:114 to `pathappPatch` (event_load).

**F3.** Verify all mutations include auto-injected scope fields.

### Phase G — Verification (14 gates)

**G1.** `npm run build` clean.
**G2.** Server `/api/health` 200; Rule 29.
**G3.** **SFX drag-drop:** drag SFX tile from LibraryPanel → drop on intro slot at time X → cue appears with offset_ms ≈ X.
**G4.** **CuePopover edit:** click cue marker → popover → change volume → save → cue updates.
**G5.** **CuePopover delete:** click delete → cue removed via DELETE `/api/timeline/cues/<id>`.
**G6.** **Module-level cue:** drag onto module timeline (below slots) → cue created in `state.module_sfx_cues` (not slot.sfx_cues).
**G7.** **Transitions render:** 3 transition selectors visible between 4 slots.
**G8.** **Transition change:** select crossfade → save via pathappPatch → next bake honors.
**G9.** **Trim handles render:** each slot has 2 trim handles on scrubber.
**G10.** **Trim edit:** drag in-handle to 2.0s → trim saved → next bake honors.
**G11.** **Bake with cues + transitions + trims:** click Bake → final MP4 produced → preview honors all 3.
**G12.** **Production Map all rows:** GET `/api/production_map` returns ≥ 59 rows.
**G13.** **Production Map multi-event:** click M5 (Event_2) cell → navigates to Event_2 scope, not Event_1.
**G14.** **Raw fetch migration:** all 4 sites now use `pathappPatch`. Verify via Network tab — auto-injected fields present.

**G15.** **(NEW 2026-05-03 — Playwright automation per S5.5c+e learning that Chrome MCP cannot reach localhost.)** Write `Production/tools/storyboard-v2/e2e/s5_5g_smoke.spec.ts` covering:
- SFX cue dropped on slot waveform creates marker; POSTs `/api/timeline/cues` with correct slot + offset_ms
- CuePopover edits volume + saves; verify state mutation
- CuePopover delete removes cue via DELETE `/api/timeline/cues/<id>`
- Module-level cue dropped on module timeline (below slots) writes to `state.module_sfx_cues` (NOT slot.sfx_cues)
- Per-boundary transition selector (3 between 4 slots) saves via `pathappPatch(scope, 'stitch_save_job', ...)`
- Per-slot trim handles (in/out) save trim positions
- Production Map renders ≥ 59 rows
- Production Map cell-click navigates to correct event scope (multi-event mapping fix)
- All 4 raw-fetch migration sites (StitcherTab.tsx + ProductionMapTab.tsx) verified via grep → ZERO hits

`cd Production/tools/storyboard-v2 && npx playwright test e2e/s5_5g_smoke.spec.ts` exits 0.

### Phase H — LD writes

**H1.** Write 5 NEW LDs.

### Phase I — Closeout (final session of feature parity arc)

**I1.** `prod_activity_log` row `S5_5G_COMPLETE` AND `STORYBOARD_V59_FEATURE_PARITY_COMPLETE`.

**I2.** Write `Production/docs/STORYBOARD_V59_FEATURE_PARITY_COMPLETE_HANDOFF.md` summarizing all 4 sessions + the v59 client's now-complete feature surface.

**I3.** Update master overview's table — all 4 sessions = COMPLETE.

**I4.** Tail-end verifier (covers cross-session integration since this is the final session).

**I5.** Browser smoke deferred to Kim with the FULL E19 walkthrough (all 8 steps from v3 spec) — now fully wirable end-to-end.

**I6.** Git commit: `S5.5g — Stitcher SFX/transitions/trims + Production Map fixes (14 gates green) — v59 feature parity COMPLETE`.

**I7.** Post-session decision: `/stitch_editor` retirement timing. Recommend: keep for 2 more weeks while Kim runs production with v59 Stitcher; then mark deprecated; then delete when Kim confirms unused.

## §5 Files Created / Modified

### Created
- `Production/docs/STORYBOARD_V59_FEATURE_PARITY_COMPLETE_HANDOFF.md`

### Modified
- `src/components/StitcherTab.tsx` (major extension; 302 → ~600 lines)
- `src/components/ProductionMapTab.tsx` (raw fetch migration; multi-event nav)
- `src/components/LibraryPanel.tsx` (SFX/ambient/transitions tier filter)
- `src/api/endpoints.ts` (add stitcher + timeline cue endpoints)
- `src/components/phase/CuePopover.tsx` (extend for SFX cue type if not generic enough)
- `production_server.py` (multi-event mapping fix at line 8434; per-slot trim endpoint if Phase D requires)

### Modified (Directus)
- `prod_modules`: add `event_dir` column (or join logic per Phase E2)

## §6 Directus Writes Required

### `prod_locked_decisions`
- POST 5 NEW LDs

### `prod_modules`
- PATCH all 59 rows with `event_dir` per GAMEPLAY_SCOPE_v3.md mapping

### `prod_activity_log`
- `S5_5G_PHASE_A_PREFLIGHT`, `_PHASE_B_SFX_DROP`, `_PHASE_C_TRANSITIONS`, `_PHASE_D_TRIMS`, `_PHASE_E_PRODUCTION_MAP`, `_PHASE_F_RAW_FETCH_MIGRATED`, `_PHASE_G_VERIFICATION_PASS`, `_COMPLETE`, `STORYBOARD_V59_FEATURE_PARITY_COMPLETE`

### `prod_preflight_reviews`
- 1 row at session start; references S5.5f preflight as predecessor

### `prod_assets`
- `scene_concat_mp4` rows on bake (existing flow; unchanged)

## §7 Error Cases and Handling

| Failure | Handling |
|---|---|
| `/stitch_editor` audit reveals features not investigated in this spec | Surface to Kim; either expand session scope OR document gap as deferred |
| Per-slot trim backend not extensible cleanly | Implement new endpoint per Phase D2 option (b) |
| `prod_modules` lacks `event_dir` column | Add column via Directus admin first; populate via update script |
| GAMEPLAY_SCOPE_v3.md doesn't have arc → event mapping | Surface to Kim; she may need to add this; defer multi-event fix |
| Module-level cue dropped on slot timeline (vs module timeline) | Auto-route by drop target; document UX clearly |
| Mini-waveform render fails on slot with no audio | Show "no audio" placeholder; cue drop disabled for that slot |
| Bake with all 3 (cues + transitions + trims) produces incorrect output | Server-side bug; surface to Kim; defer to Phase G11 forensic |
| 4 raw fetch migrations break existing flows | Phase F gates catch this; revert via git checkout per file |

## §8 Verification

Done when 14 gates green + 5 LDs + activity_log + browser smoke deferred to Kim with full E19 walkthrough.

## §9 Rollback

- StitcherTab.tsx, ProductionMapTab.tsx, LibraryPanel.tsx: `git checkout -- src/components/`
- Server multi-event fix + per-slot trim endpoint: `git checkout -- Production/tools/production_server.py`
- prod_modules event_dir column: leave column; PATCH rows back if needed (data preservation)

## §10 Out of Scope (for this session AND for the v59 feature parity arc)

- Sound library tier filter for `transitions` tier (might overlap with §3.3 transitions UI; defer)
- Multi-track audio mixing (current model is single-bed + cues; multi-track is post-V1)
- SFX recording in-app (always external; existing pattern)
- Transition library (custom transitions beyond crossfade/cut/dissolve) — defer
- Slot reordering (drag slots to different positions) — defer; default order is intro→A→B→resolution
- Slot duplication — defer
- "Save as preset" for transition combinations — defer
- /stitch_editor retirement (keep for 2 more weeks; Kim's call when to delete)
- Job registry leak fix (across `_GPT_JOBS`/`_MAGIC_JOBS`/`_ASSEMBLE_JOBS`) — documented smell, defer to S6
- Long-term `pinned_video_role` enforcement — defer

## §11 Dependencies

**Hard on S5.5c:** Modal, Toast, Spinner, AssetTile, dragdrop helper.
**Hard on S5.5e:** ProjectSelector + populated `prod_modules`.
**Hard on S5.5f:** WaveformTimeline component, CuePopover component, watercolor drag-drop pattern.
**Hard on v3:** scope signals, export pipeline, drain protocol.

## §12 Notes for the Executing Session

- This is the LAST session in the v59 feature parity arc. Phase I closeout includes the final feature-parity-complete handoff.
- /stitch_editor audit in Phase A is critical. Every feature there needs to be investigated for porting. Don't skip.
- Per-slot trim backend choice is the only architectural decision in this session. Lean toward extending `stitch_save_job` body unless that creates compatibility issues.
- WaveformTimeline component reuse from S5.5f is load-bearing. If S5.5f shipped a different component (e.g., split into multiple), reconcile here.
- CuePopover from S5.5f handles watercolor cues; SFX cues have different fields (volume, fadein, fadeout, source_path). Make CuePopover generic with cue_type prop OR build StitcherCuePopover. Generic is preferred.
- Production Map multi-event mapping is a data + server fix. Test by switching to a module Kim knows is in Event_2 (per GAMEPLAY_SCOPE_v3.md) and verifying cell click goes there.
- After this session: Kim has full v59 Stitcher tab. /stitch_editor stays as fallback; do not delete this session.
- **Playwright is mandatory for S5.5g closeout (gate G15).** Chrome MCP can't reach localhost from the Claude extension sandbox (verified 2026-05-03 during S5.5c+e closeout). Project scaffold at `Production/tools/storyboard-v2/e2e/`. Write `s5_5g_smoke.spec.ts` alongside the feature work. If a behavior can't be Playwright-tested cleanly, surface to Kim before shipping.
- Browser smoke E19 covers the full 8-step v3 walkthrough. With this session complete, all 8 steps should work end-to-end.

## §13 Cursor Review Checklist

1. Per-slot SFX vs module-level SFX UI — is drop-target-distinguishes-scope clear enough, or do we need explicit toggle?
2. Transition selector default (crossfade vs cut) — what does legacy stitch_editor default to?
3. Per-slot trim backend: extend existing `stitch_save_job` body vs new endpoint vs reuse `beat/trim`? Which is cleanest given LD-490 (`/api/scene/assemble`)?
4. Multi-event mapping: should `event_dir` live in `prod_modules` (column) or be derived from a join with `prod_arcs`/`prod_events`? Schema decision affects long-term flexibility.
5. /stitch_editor audit (Phase A) might find features not enumerated in this spec — what's the protocol for adding scope mid-session?
6. CuePopover genericization: cue_type discriminated union vs prop drilling vs separate components?
7. Bake with combined cues + transitions + trims (gate G11) — what's the test fixture? A specific event with all 3 set, or synthetic test data?
8. SFX library tier filter (G3 prerequisite) — should it be a tab bar within LibraryPanel or a dropdown filter?
9. Trim handle UX: drag-only? Or also keyboard arrow keys for fine adjustment?
10. /stitch_editor retirement: 2 weeks the right window? Or longer to be safe?

Append findings as §14.

---

**End of S5.5g spec v1.**

## §14 Cursor v8 findings folded (audit trail)

| Finding | Resolution |
|---|---|
| Q2 transition default | AMENDED — Phase A2 audit writes down `/stitch_editor` JSON/job schema defaults |
| Q3 trim backend | CONFIRMED option (a) extend `stitch_save_job` body — single persistence choke-point |
| Q4 event_dir column vs derived | AMENDED — PREFER derived mapping from GAMEPLAY_SCOPE_v3.md; column only if editor overrides needed |
| Q5 mid-session scope creep | AMENDED — "Kim checkpoint + mini addendum spec" rule for /stitch_editor audit findings beyond this spec |
| Q7 G11 combined bake fixture | AMENDED — name golden event fixture (Event_1, intro role) OR accept manual Kim bake |
| Q8 SFX tier filter UI | AMENDED — tab bar within LibraryPanel (consistent with S5.5f watercolor tier) |
| Q9 trim keyboard nudge | AMENDED — DEFERRED unless /stitch_editor already supports it |
| Q10 retirement window | AMENDED — metric-based ("zero hits in server logs for N days") not calendar-based |
| Beyond #1 raw-fetch line refs drifted | FIXED — `~L70, 88-89, 123, 149, 191` (StitcherTab) + `~L114-118` (ProductionMapTab); pre-flight re-grep instruction added |
| Beyond #2 WaveformTimeline read-only mode dependency | EXPLICIT — S5.5f must export read-only-cues prop; verify in Phase A4 |
| Beyond #3 `/api/stitch_editor/job` POST in migration scope | INCLUDED in §3.5 migration list |

Total gates: no change (line ref fixes don't add gates).

**End of S5.5g spec v1 (Cursor v8 folded).**

**End of v59 feature parity spec arc** (master overview + 4 session specs).
