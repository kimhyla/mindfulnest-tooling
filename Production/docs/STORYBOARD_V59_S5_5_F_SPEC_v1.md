# Storyboard v59 — Sub-Session S5.5f Spec v1

**Date:** 2026-05-03
**Classification:** EXECUTION SPEC — feature parity for Phase A and Phase B producers
**Predecessor:** S5.5e (Storyboard buttons + ProjectSelector + Production Map data)
**Master overview:** `STORYBOARD_V59_FEATURE_PARITY_MASTER_OVERVIEW.md`

## §1 Task

Bring Phase A and Phase B producer tabs to feature parity. Add WaveSurfer.js v7 waveform display, watercolor library drag-drop onto timeline, cue popovers (animation type / duration / Delete), Phase A 3-clip handling (fly-in / sitting / fly-out), voice stem upload UI, and ambient preset selector inside producer.

## §2 Governing Decisions

### LDs respected (do not violate)

| LD | Key | Reason |
|---|---|---|
| LD-149 | PHASE_B_CEDRIC_PIPELINE | Phase B IS Cedric lipsynced video (corrects outdated memory) |
| LD-196 | PHASE_B_CANONICAL_PIPELINE | Cedric master FLUX → Kling motion → ByteDance LipSync → final |
| LD-330 | PHASE_B_AUTHORING_WAVEFORM_FIRST_RESTORE_V1 | WaveSurfer is the source of truth for Phase B authoring |
| LD-348 | PHASE_B_LOCKED_M1 | Phase B Cedric pipeline locked for M1 |
| LD-462 | PHASE_A_PRODUCER_V1 | Phase A producer = Chipper-only on empty desk |
| LD-463 | PHASE_B_PRODUCER_V1 | Phase B producer scope |
| LD-464 | WATERCOLOR_ANIMATE_THIS_V1 | Watercolor "Animate This" flow |
| LD-470 | WATERCOLOR_ANIMATE_PROCEDURAL_V1 | Procedural watercolor animation (supersedes magic-watercolor merge) |
| LD-472 | WAVESURFER_TIMELINE_V1 | Waveform timeline component spec |
| LD-484 / LD-485 | PHASE_A_TOP_LEVEL_STATE_V1 / PHASE_B_TOP_LEVEL_STATE_V1 | Phase data at top-level state, not under videos |
| LD-203 | WATERCOLOR_TILE_FRAMING_V1 | Cue tiles = brown border + cream mat + white interior + centered art |

### NEW LDs this spec writes (6)

| Key | Severity | Purpose |
|---|---|---|
| `WAVESURFER_TIMELINE_INTEGRATION_V1` | HIGH | WaveSurfer v7 mounted in PhaseProducer; handles audio source priority lipsync > mixed > stem; supports cue placement at click position |
| `WATERCOLOR_DRAG_DROP_TIMELINE_V1` | HIGH | Drag from LibraryPanel watercolor tier → drop on timeline at time position → cue created. Replaces "open new tab to /magic" flow. |
| `CUE_POPOVER_INSPECTOR_V1` | HIGH | Click cue marker → popover with animation_type / duration / volume / Delete. Reusable component shared with Stitcher (S5.5g). |
| `PHASE_A_THREE_CLIP_HANDLING_V1` | HIGH | Phase A producer renders 3 clip slots: fly-in, sitting, fly-out. Each is a separate clip with own asset picker. |
| `VOICE_STEM_UPLOAD_UI_V1` | MEDIUM | `<input type="file">` UI for voice stem upload (currently no UI; backend exists). Supports drag-drop too. |
| `AMBIENT_PRESET_SELECTOR_INPRODUCER_V1` | MEDIUM | Move/duplicate ambient preset selector inside PhaseProducer (currently only in Stitcher slots). Reuses existing endpoints. |

## §3 Approach

### §3.1 PhaseProducer.tsx surgery

**File:** `src/components/phase/PhaseProducer.tsx` (currently 410 lines; will become ~700 lines with feature parity)

The component is shared between Phase A and Phase B (passed `phase: 'a' | 'b'` prop). Branching via `selectedBaseClip` filter at line 119-120 (Chipper for A, Cedric for B). Most additions are shared; Phase A 3-clip handling is the main A-specific divergence.

### §3.2 WaveSurfer.js v7 timeline

**Add dep:** `npm install wavesurfer.js@7` (adds ~25KB to bundle; acceptable per LD-472)

**New component:** `src/components/phase/WaveformTimeline.tsx` (~250 lines)

```
┌─ Audio Timeline ─────────────────────────────────────────┐
│ [▶ play] 0:00 ──────────────────────────── 1:30 / 2:15  │
│ ┌──────────────────────────────────────────────────────┐ │
│ │ ╱╲    ╱╲╱╲      ╱╲          ╱╲╱╲╲                     │ │ ← waveform
│ │╱  ╲  ╱    ╲    ╱  ╲    ╱╲  ╱      ╲                   │ │
│ │    ╲╱      ╲  ╱    ╲  ╱  ╲╱        ╲                  │ │
│ └─────●──────────────●─────────────●──────────────────┘ │
│       │              │             │                     │
│       cue 1          cue 2         cue 3                  │
│       ●─click→ popover                                    │
│                                                           │
│ Source: lipsync.mp4 (priority 1) / mixed.mp3 / stem.mp3   │
└──────────────────────────────────────────────────────────┘
```

**Behavior:**
- Audio source priority: `phase_X_lipsync_file` > `phase_X_mixed_audio_file` > `phase_X_voice_stem_file`
- WaveSurfer loads audio via `ws.load(audio_url)` per LD-330
- Click on waveform → seek + show timestamp tooltip
- Drag-and-drop target: dropping a watercolor tile creates a cue at the time position
- Cue markers (●) at each `phase_X_watercolor_cues_json` entry's `offset_ms`
- Click cue marker → CuePopover (§3.4)
- Drag cue marker horizontally → update `offset_ms` via `pathappPatch`

### §3.3 Watercolor drag-drop on timeline

Currently: clicking watercolor tile in PhaseProducer (lines 372-400) opens a new browser tab via `window.open('/magic?mode=watercolor_animate')`. This is the legacy flow per LD-464.

**New flow (per `WATERCOLOR_DRAG_DROP_TIMELINE_V1`):**
1. LibraryPanel watercolor tile is draggable (from S5.5c AssetTile primitive)
2. Drop on WaveformTimeline at time position X
3. PhaseProducer adds entry to `phase_X_watercolor_cues_json` array via `pathappPatch`:
   ```json
   { "id": "cue_<uuid>", "watercolor_key": "<lib_key>", "offset_ms": <ms>, "duration_ms": 3000, "animation_type": "fade", "volume": 1.0 }
   ```
4. Cue marker renders at offset_ms
5. Click marker → CuePopover

**Backward compat:** keep "open new tab" flow as fallback for now (some workflows might depend on it). Drag-drop is the primary path going forward.

### §3.4 Cue popover inspector

**New component:** `src/components/phase/CuePopover.tsx` (~150 lines, also reusable in S5.5g Stitcher)

Click cue marker → popover anchored to marker:

```
┌─────────────────────────┐
│ Watercolor cue          │
│                         │
│ Animation: [fade ▼]     │
│ Duration: [3000] ms     │
│ Volume:   [────●────]   │
│                         │
│ [Delete] [Done]         │
└─────────────────────────┘
```

**Animation types** (cue popover — static PNG entrance presets):
- `fade` — fade in/out
- `slide_in` — slide from edge
- `pulse` — opacity pulse
- `static` — no animation (just appear)
- `procedural_drift` — gentle drift (legacy LD-470 label; static tile only)

**Animate This** (path picker → MP4): see §15 — **LD-823** `WATERCOLOR_ANIMATE_PIL_RENDERER_V1` (PIL center-split rub, not Claude/ffmpeg).

**Delete:** removes cue from `phase_X_watercolor_cues_json` array via `pathappPatch`.

### §3.5 Phase A 3-clip handling

Currently `selectedBaseClip` (line 107) handles ONE base clip. Phase A spec requires THREE clips:
- `phase_a_chipper_flyin_clip_id` — fly-in animation
- `phase_a_chipper_sitting_clip_id` — sitting + lipsync animation (the main clip)
- `phase_a_chipper_flyout_clip_id` — fly-out animation

**UI for Phase A only:**

```
┌─ Phase A Clips ─────────────────────────────────────┐
│ ┌─ Fly-in ──┐ ┌─ Sitting ──┐ ┌─ Fly-out ──┐         │
│ │ [thumb]   │ │ [thumb]    │ │ [thumb]    │         │
│ │ duration: │ │ duration:  │ │ duration:  │         │
│ │ 1.5s      │ │ 30s        │ │ 1.0s       │         │
│ │ [pick]    │ │ [pick]     │ │ [pick]     │         │
│ └───────────┘ └────────────┘ └────────────┘         │
│ Total: 32.5s                                         │
└──────────────────────────────────────────────────────┘
```

**Picker:** `BaseClipPicker.tsx` (existing or new?) — verify; modal with library filter for Phase A clip tier.

**Stitch order** (per LD-376 fade recipes): fly-in → fade-to → sitting → fade-to → fly-out. Existing `_auto_assemble_phase_a_stitched` handler at `production_server.py:14347` consumes these 3 clip IDs and produces `phase_a_stitched_file`.

**Phase B does NOT have 3 clips** — it's a single Cedric lipsynced video per LD-149.

### §3.6 Voice stem upload UI

Currently no `<input type="file">` in PhaseProducer.

**New section in PhaseProducer:**
```
┌─ Voice Stem ────────────────────────────────────────┐
│ Current: phase_a_stem_2026-05-03.mp3 (1.2 MB)       │
│ [▶ Preview]                                          │
│                                                      │
│ [📂 Upload new] OR drop file here ──────────────────│
└──────────────────────────────────────────────────────┘
```

**Backend:** existing TTS-stem endpoint (verify path; likely reuses Phase B mix audio handler with mode=stem). If endpoint missing, defer this feature to S6 and document.

### §3.7 Ambient preset selector inside producer

Currently ambient preset is only in Stitcher slot config (StitcherTab.tsx:46-52, hardcoded list of 5).

**New section in PhaseProducer:**
```
┌─ Ambient Bed ───────────────────────────────────────┐
│ Preset: [forest ambient ▼]   Volume: [────●────]    │
│ Loop: [✓]   Fade in: [500] ms  Fade out: [1000] ms  │
│ [Preview with bed]                                   │
└──────────────────────────────────────────────────────┘
```

Backend (Cursor v8 RELEASE-BLOCKER FIX): `/api/phase_b/ambient_preset_list` does NOT exist in `production_server.py` (verified via grep — zero matches). Two options:

(a) **Static preset list** in client + filesystem existence check on save: hardcode preset slugs that map 1:1 to `Production/audio_library/ambient/<preset_id>.mp3`. On save, server validates file exists; rejects with 400 if missing.

(b) **Add a small read endpoint** `GET /api/phase_b/ambient_preset_list` that scans `Production/audio_library/ambient/` and returns `[{preset_id, file_size_bytes}]`. ~30 lines server code; preferred for editorial flexibility.

**Decision:** Option (b). Phase E adds the endpoint + verifies via gate F15. Save preset via `pathappPatch(scope, 'v2_module_patch', {phase_X_ambient_preset_id: preset_id})` (uses `v2_module_patch`; whitelist field already in `_V2_MODULE_ALLOWED_FIELDS`).

## §4 Implementation Phases

### Phase A — Pre-flight + dep add

**A1.** Read master overview, this spec, S5.5e COMPLETE activity log, v3 spec phase A/B sections.

**A2.** `npm install wavesurfer.js@7` (verify version, check bundle size impact).

**A3.** Verify backend endpoints exist for:
- Phase B preview (`/api/phase_b/preview` per Agent A)
- Phase A 3-clip stitch — Cursor v8 RELEASE-BLOCKER FIX: `/api/canonical_stitch` does NOT exist. Real trigger surface: `_auto_assemble_phase_a_stitched` at `production_server.py:15615` is invoked internally from `_handle_phase_b_mix_audio` at `:15369` (called via `pathappPatch(scope, 'phase_b_mix_audio', {phase: 'a'})`). Clip ID writes go via `v2_module_patch` (top-level `phase_a_chipper_<position>_clip_id` fields, in `_V2_MODULE_ALLOWED_FIELDS` whitelist).
- Voice stem upload (TBD — investigate)
- Ambient preset list (TBD — investigate)

**A4.** `prod_preflight_reviews` row.

### Phase B — WaveSurfer integration

**B1.** Build `WaveformTimeline.tsx` per §3.2.

**B2.** WaveSurfer config: barWidth: 2, barGap: 1, normalize: true, height: 80, peaks (server-side preprocess if available).

**B3.** Audio source priority resolution: `phase_X_lipsync_file ?? phase_X_mixed_audio_file ?? phase_X_voice_stem_file`.

**B4.** Cue marker overlay layer (absolute-positioned divs over canvas; pointer-events on markers).

**B5.** Click-to-seek + tooltip on hover.

**B6.** Mount in PhaseProducer below the script editor; replace existing audio player.

**B7.** Test load + seek + cue marker render.

### Phase C — CuePopover + drag-drop

**C1.** Build `CuePopover.tsx` per §3.4.

**C2.** Wire animation_type dropdown, duration input, volume slider, Delete button.

**C3.** All edits flow through `pathappPatch(scope, 'phase_<X>_watercolor_cues_json', updated_array)`.

**C4.** Wire WaveformTimeline as drag drop target.

**C5.** Use S5.5c `dragdrop.ts` payload helper. Watercolor drop creates cue with default animation_type='fade', duration_ms=3000.

**C6.** LibraryPanel watercolor tier: ensure tiles are draggable AssetTiles.

### Phase D — Phase A 3-clip handling

**D1.** Add `BaseClipPicker.tsx` (or extend existing) — modal with library filter for Phase A clips.

**D2.** Render 3 picker slots in PhaseProducer when `phase === 'a'`.

**D3.** Wire each slot to `pathappPatch(scope, 'phase_a_chipper_<position>_clip_id', clip_id)`.

**D4.** Display total duration computed from each clip's duration metadata.

**D5.** Trigger Phase A re-stitch (Cursor v8 fix): clip-ID writes via `pathappPatch(scope, 'v2_module_patch', {phase_a_chipper_flyin_clip_id: <id>})` etc. Re-stitch fires via `pathappPatch(scope, 'phase_b_mix_audio', {phase: 'a'})` which internally calls `_auto_assemble_phase_a_stitched`. Default = MANUAL "Re-stitch" button to avoid running 30-sec ffmpeg on every clip change. (Cursor v8 Q9 amendment.)

**D6.** Test: pick clips → Re-stitch → `phase_a_stitched_file` updates → preview plays the assembled video.

### Phase E — Voice stem upload + ambient preset

**E1.** Add voice stem upload section per §3.6. `<input type="file">` + drag-drop using S5.5c helper.

**E2.** Verify upload endpoint; if missing, document as deferred + skip feature.

**E3.** Add ambient preset selector per §3.7. Wire to `phase_X_ambient_preset_id`.

**E4.** Add Preview-with-bed button: POSTs to `/api/phase_b/preview` with bed mixed in.

### Phase F — Verification (16 gates)

**F1.** `npm run build` clean.
**F2.** Server `/api/health` 200; Rule 29.
**F3.** **WaveSurfer load probe:** open Phase B with valid audio_file → waveform renders.
**F4.** **Audio source priority:** swap `phase_b_lipsync_file` → waveform updates to lipsync. Remove lipsync → falls back to mixed_audio.
**F5.** **Click-to-seek:** click on waveform at 50% → audio seeks to 50% time.
**F6.** **Cue marker render:** cue at offset_ms=15000 renders at correct horizontal position on a 30s waveform.
**F7.** **Drag watercolor onto timeline:** drag watercolor tile from LibraryPanel → drop at time position X → cue created with offset_ms=X.
**F8.** **CuePopover edit:** click cue → popover opens → change duration → `pathappPatch` fires → popover closes → marker updates.
**F9.** **CuePopover delete:** click Delete → cue removed from array → marker disappears.
**F10.** **Phase A 3-clip render:** open Phase A → see 3 picker slots (fly-in / sitting / fly-out).
**F11.** **Phase A clip pick:** click each slot → BaseClipPicker opens → pick clip → state updates.
**F12.** **Phase A re-stitch:** change a clip → `_auto_assemble_phase_a_stitched` fires → `phase_a_stitched_file` updates.
**F13.** **Phase A vs Phase B branching:** open Phase B → no 3-clip UI (only single base clip). Open Phase A → 3-clip UI present.
**F14.** **Voice stem upload:** select file → uploads → `phase_X_voice_stem_file` updates → waveform refreshes (because lipsync/mixed not yet present, stem becomes source).
**F15.** **Ambient preset selector:** change preset → `phase_X_ambient_preset_id` updates → next preview includes new bed.
**F16.** **Watercolor cue framing per LD-203:** verify watercolor library tiles render with brown border + cream mat + white interior + centered art (existing pattern; just verify after drag-drop).

### Phase G — LD writes

**G1.** Write 6 NEW LDs.

### Phase H — Closeout

**H1.** `S5_5F_COMPLETE` activity log row.

**H2.** S5.5g handoff stub.

**H3.** Master overview update.

**H4.** Tail-end verifier.

**H5.** Git commit: `S5.5f — Phase A/B feature parity (16 gates green)`.

## §5 Files Created / Modified

### Created
- `src/components/phase/WaveformTimeline.tsx` (~250 lines)
- `src/components/phase/CuePopover.tsx` (~150 lines)
- `src/components/phase/BaseClipPicker.tsx` (~120 lines if not extending existing)
- `Production/docs/STORYBOARD_V59_S5_5_G_HANDOFF.md`

### Modified
- `package.json` (add wavesurfer.js@7)
- `src/components/phase/PhaseProducer.tsx` (major extension; ~410 → ~700 lines)
- `src/components/LibraryPanel.tsx` (watercolor tier draggable)
- `src/api/endpoints.ts` (add ambient preset, voice stem upload endpoints if needed)

### Modified (Directus)
- `prod_assets`: voice stem uploads create `voice_stem` rows (existing flow)

## §6 Directus Writes Required

### `prod_locked_decisions`
- POST 6 NEW LDs

### `prod_activity_log`
- `S5_5F_PHASE_A_PREFLIGHT`, `_PHASE_B_WAVESURFER`, `_PHASE_C_CUE_POPOVER`, `_PHASE_D_PHASE_A_3_CLIP`, `_PHASE_E_VOICE_AMBIENT`, `_PHASE_F_VERIFICATION_PASS`, `_COMPLETE`

### `prod_assets`
- voice_stem on E14
- watercolor cue creates change-only state mutations (no asset row; cues are state, not assets)

## §7 Error Cases and Handling

| Failure | Handling |
|---|---|
| WaveSurfer fails to load (bad audio URL) | Show error in waveform area; fallback to native `<audio controls>` |
| Cue offset_ms exceeds audio duration | Reject `pathappPatch`; Toast "Cue beyond audio length" |
| Cue duration_ms exceeds remaining audio | Cap at remaining; Toast warning |
| Drag-drop on Safari with broken dataTransfer | Document as known issue; require Chromium for now |
| Phase A clip 0-byte file | Picker rejects; show error |
| `_auto_assemble_phase_a_stitched` fails (3 clips incompatible codecs) | Server returns 500 via `phase_b_mix_audio` handler; show Toast with stderr excerpt |
| Voice stem upload >50MB | Server rejects; show Toast with size limit |
| Voice stem upload format unsupported | Server rejects; show supported formats |
| Ambient preset list endpoint 404 | Show "preset list unavailable"; defer feature |

## §8 Verification

Done when 16 gates green + 6 LDs + activity_log + browser smoke deferred.

## §9 Rollback

- WaveSurfer: revert PhaseProducer.tsx; uninstall wavesurfer.js
- Drag-drop: revert LibraryPanel + dragdrop helper
- Phase A 3-clip: revert PhaseProducer.tsx
- All client changes: `git checkout -- src/`

## §10 Out of Scope

- Per-cue waveform-snippet preview — defer
- Cue copy/paste between beats — defer
- Phase A clip auto-suggest based on scene — defer
- Voice profile management UI — defer
- Multi-take voice stem comparison — defer
- WaveSurfer regions plugin (visual cue regions vs point markers) — defer; point markers are sufficient
- Lipsync-status surface in PhaseProducer (currently in Phase B Send for Lipsync button) — covered

## §11 Dependencies

**Hard on S5.5c:**
- `Modal` (BaseClipPicker uses)
- `Toast` (errors)
- `Spinner` (during waveform load)
- `dragdrop.ts` (watercolor drop)
- `AssetTile` (LibraryPanel)

**Hard on S5.5e:**
- ProjectSelector context (`activeProjectType`) for milestone scope (Phase A/B disabled)

**Hard on v3:**
- Phase tab routing
- Top-level state shape

## §12 Notes for the Executing Session

- WaveSurfer.js v7 is THE waveform library per LD-330. Don't substitute; don't roll your own.
- LD-203 watercolor framing applies to LIBRARY tiles, not cue markers on timeline. Cue markers are simple dots.
- Phase A clip stitching ALREADY EXISTS at `_auto_assemble_phase_a_stitched`. Don't reimplement; just trigger it.
- Voice stem upload endpoint may not exist. Investigate in Phase A. If missing: document, defer feature, but ship the rest of the session.
- LD-149/196/348 confirm Phase B Cedric pipeline. The "audio-only Phase B" memory was outdated. Send for Lipsync button STAYS in Phase B.
- The cross-component CuePopover (used here + S5.5g) should be extracted carefully so S5.5g can reuse without changes.
- Bundle size: WaveSurfer adds ~25KB. Verify total `dist/` < 100KB after build.
- **Playwright mandatory for S5.5f closeout (gate F18).** Chrome MCP can't reach localhost from the Claude extension sandbox (verified 2026-05-03 during S5.5c+e closeout). Project scaffold at `Production/tools/storyboard-v2/e2e/` + `helpers.ts`. Write `s5_5f_smoke.spec.ts` alongside feature work. If a behavior can't be Playwright-tested cleanly, that's a redesign signal — surface to Kim.

## §13 Cursor Review Checklist

1. WaveSurfer v7 vs v6 — any breaking API changes affecting LD-330 implementation?
2. Cue popover coordinates — relative to timeline canvas vs viewport? Edge cases when timeline is scrolled / zoomed.
3. Drag-drop on Safari — known dataTransfer.effectAllowed quirks; do we need a Safari-specific path?
4. Phase A clip duration math — do we sum literal durations or include fade overlap (LD-376)?
5. Voice stem upload: investigate endpoint before Phase E. If missing, scope decision: build endpoint OR defer feature.
6. Ambient preset endpoint same investigation.
7. Cue duration_ms field — when does it apply? Animation duration? Audio sustain? Both?
8. CuePopover delete — confirm before delete? UX preference vs friction.
9. Phase A re-stitch trigger — auto on every change vs manual button? Cost: each stitch is ~30s ffmpeg.
10. WaveSurfer playback head sync with `<audio>` element — does WaveSurfer 7 manage its own audio element, or do we mount one separately for `<audio>` controls?

Append findings as §14.

---

## §14 Cursor v8 findings folded (audit trail)

| Finding | Resolution |
|---|---|
| Q1 WaveSurfer v7 | AMENDED — pin package-lock.json; add gate "import + destroy cycle leaves no WebAudio leaks" |
| Q2 Popover coordinates | AMENDED — portal vs inline + `position: fixed` math + close-on-outside-click |
| Q3 Safari quirks | AMENDED — supported-browser matrix mirrors S5.5c/g |
| Q4 Phase A duration math | AMENDED — display = sum of nominal lengths; bake-time = post-xfade per LD-376 (cite `_auto_assemble_phase_a_stitched`) |
| Q5 Voice stem endpoint | CLARIFIED — `POST /api/phase_b/regen_audio` (misnamed) writes `phase_{a|b}_voice_stem_*.mp3` per `production_server.py:15067-15075`. UX: "Generate stem from script" (NOT file upload). Real multipart upload is OUT OF SCOPE for this session; defer if Kim wants drag-drop file upload. |
| Q6 Ambient preset endpoint | RELEASE-BLOCKER FIX — see §3.7 amendment |
| Q7 duration_ms semantics | AMENDED — animation duration; tied to LD-470 cue model fields in `phase_*_watercolor_cues_json` |
| Q8 Delete confirm | AMENDED — Modal confirm (Toast on success); Shift+click for power-user skip |
| Q9 Auto re-stitch vs manual | AMENDED — manual "Re-stitch" button default; debounced auto behind setting (deferred) |
| Q10 WaveSurfer/audio sync | AMENDED — single playback engine (WaveSurfer manages its own `<audio>` element) |
| Beyond #1 `/api/canonical_stitch` doesn't exist | RELEASE-BLOCKER FIX — see §3.5 + Phase D5 amendment |
| Beyond #2 `v2_module_patch` not in MUTATION_ENDPOINTS | AMENDED — Phase D5 explicitly adds `v2_module_patch` to `MUTATION_ENDPOINTS` set; whitelist fields confirmed via `_V2_MODULE_ALLOWED_FIELDS` |
| Beyond #3 `Production/Event_1/` hardcode in PhaseProducer.fileUrl | NEW GATE — F17 verifies zero literal `Production/Event_1/` strings in `PhaseProducer.tsx`; replaced with `activeScope.event_id` |

**New verification gate added per Cursor v8:**
**F17.** Grep `PhaseProducer.tsx` for `'Production/Event_1/'` literal — expect ZERO hits. All paths derived from `activeScope.event_id`.

**New Playwright automation gate (added 2026-05-03 post-S5.5c+e closeout — Chrome MCP can't reach localhost; Playwright headless Chromium can):**
**F18.** Write `Production/tools/storyboard-v2/e2e/s5_5f_smoke.spec.ts` covering the new behaviors below; `cd Production/tools/storyboard-v2 && npx playwright test e2e/s5_5f_smoke.spec.ts` exits 0:
- WaveSurfer mounts and renders a waveform when a beat with `audio_file` is selected
- Cue marker appears at correct horizontal position when a watercolor tile is dropped on the timeline
- CuePopover opens on cue marker click; volume slider mutates state via `pathappPatch`
- CuePopover Delete button removes cue from `phase_X_watercolor_cues_json`
- Phase A 3-clip pickers render (3 slots: fly-in / sitting / fly-out) — only when `phase === 'a'`
- Phase B does NOT render 3-clip pickers (uses single base clip via existing `selectedBaseClip`)
- Voice stem upload via "Generate stem from script" button posts to `/api/phase_b/regen_audio` (Cursor v8 Q5 clarification: misnamed endpoint writes voice_stem files)
- Ambient preset selector inside producer saves via `pathappPatch(scope, 'v2_module_patch', {phase_X_ambient_preset_id: …})`
- F17 gate (no `Production/Event_1/` hardcode in PhaseProducer) — automated via grep step inside the Playwright suite OR a separate test that asserts file URLs use `activeScope.event_id`

Total gates now: 18 (was 17).

**End of S5.5f spec v1 (Cursor v8 folded).**

---

## §15 Amendment — Watercolor Animate PIL renderer (2026-05-28)

**Supersedes LD-470 implementation path** (Claude → ffmpeg filter chain). LD-470 remains in registry as historical; active decision is **`WATERCOLOR_ANIMATE_PIL_RENDERER_V1`**.

| Topic | Canonical source |
|---|---|
| Encode algorithm | `Production/docs/WATERCOLOR_ANIMATE_PROCEDURAL_TECH_SPEC_v2.md` |
| Lessons / regression checklist | `Production/docs/LESSONS_LEARNED_20260528_PHASE_B_WATERCOLOR_ANIMATE_V1.md` |
| Locked decision | Directus `WATERCOLOR_ANIMATE_PIL_RENDERER_V1` |
| Compositor recipe pin | `WATERCOLOR_OVERLAY_RECIPE_VERSION = wc_v13_hand_only_split` in `ffmpeg_stitch.py` |
| Handler | `handle_watercolor_animate` in `background.py` |

**`motion_description` contract (Phase B Animate This):**

- User types intent in path picker (e.g. "hands rub briskly with friction").
- Server parses keywords **deterministically** — NOT sent to Claude.
- Controls oscillation frequency only (`_osc_freq`: 2.5 / 1.5 / 0.75 Hz); path geometry from `manual_path`.
- Response includes `osc_freq_hz` and `renderer: PIL center-split rub`.

**Kim verification gate (manual, every animate change):**

1. Hard refresh path picker / producer after deploy.
2. Re-run **Animate This** on the watercolor (old MP4s are stale).
3. **Preview with Overlay** at cue time — frame must not shear; hands rub as opposite halves; no magenta holes under hands.

**Registration:** `python3 Production/scripts/register_watercolor_animate_v2_20260528.py`

