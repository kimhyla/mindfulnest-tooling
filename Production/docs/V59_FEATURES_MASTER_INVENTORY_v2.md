# V59 Production Tool — Master Feature Inventory v2

**Date:** 2026-05-06
**Supersedes:** v1 (2026-05-03) — Cursor v6 verification pass (commit 9efaabd) folded in
**Purpose:** Authoritative feature checklist with verified status per item. Input for next tech-spec session that partitions across S5.5c → e → f → g.

**Changelog from v1:**
- Item IDs added (BG-/C-/SB-/PB-/PA-/ST-/CC-/EP-/MAG-) for systematic verification
- Cursor v6 status (WIRED / WIRED-BUT-BROKEN / STUBBED / MISSING / DOCTRINE-ONLY / UNCLEAR) per item with file:line evidence
- 5 inventory errors corrected (endpoint namespace, Stitcher milestone disable, pathappPatch global injection scope, trim slider vs field, milestone Stitcher behavior)
- 3 missing items added (event_create flow, module_sfx_cues, Production Map raw fetch)
- LL-28 violation list (placeholder/future/stub comments) added per Rule 19/27
- Open Kim decisions section added
- Cursor v7 prompt (for 71 UNCLEAR pass) added at end

---

## ⚠️ MANDATORY — End-to-End Verification Contract for EVERY Feature Below

(Same as v1 §0 — see `V59_FEATURES_MASTER_INVENTORY_v1.md` for full text.)

For every checkbox in this document, the feature is NOT done until ALL six layers verify:

1. **UI element exists**
2. **UI → backend wiring** (right payload, right field names)
3. **Backend processing matches intent** (server actually USES the input)
4. **State update propagation** (right partition, right metadata)
5. **UI re-render reflects new state**
6. **End-to-end smoke test: vary input → output changes meaningfully**

**Layer 6 failure = RELEASE-BLOCKER, not partial completion.**

High-risk classes: AI-driven, multi-stage pipelines, async fire-and-forget, drag-drop, side-effect captures, cost displays, conditional rendering, state persistence.

---

## Cursor v6 verification summary (commit 9efaabd, 2026-05-06)

After Kim's §13 LOCKED decisions reclassify 4 items (ST-6, ST-20, CC-5, CC-10) from WIRED-BUT-BROKEN → WIRED, and CC-13 was always correct, totals are:

| Status | Count | % |
|---|---|---|
| WIRED | 90 | 45% |
| WIRED-BUT-BROKEN | 21 | 10% |
| STUBBED | 6 | 3% |
| MISSING | 8 | 4% |
| DOCTRINE-ONLY | 6 | 3% |
| UNCLEAR | 71 | 35% |

**Forward gate:** the 71 UNCLEAR items go to Cursor v7 (symbol-level tracing pass) before any session executes. See §14 for the v7 prompt.

---

## Legend

- **WIRED** — implementation present, contract appears correct
- **WIRED-BUT-BROKEN** — partial implementation, behaves incorrectly OR violates a contract
- **STUBBED** — UI shell or endpoint exists; no real wiring
- **MISSING** — not built
- **DOCTRINE-ONLY** — process/policy item, not runtime feature
- **UNCLEAR** — Cursor couldn't deterministically verify; needs v7 symbol-level tracing
- **PENDING-KIM** — open question for Kim before implementation

---

## §1 — TAB 1: Beat Generator (BG-*)

| ID | Feature | Status | Evidence | Notes |
|---|---|---|---|---|
| BG-1 | Extract Beats action | UNCLEAR | beat_generator.py:1-1808 | needs v7 trace |
| BG-2 | Per-beat dialogue textarea | UNCLEAR | BgTab.tsx:1-1400 | needs v7 trace |
| BG-3 | Stage-direction extraction chips (regex `\(([^)]{4,50})\)`, max 2) | UNCLEAR | beat_generator.py | needs v7 trace |
| BG-4 | Chip × removes BOTH chip AND `(...)` from dialogue | UNCLEAR | BgTab.tsx | needs v7 trace |
| BG-5 | Right-click chip → "Edit chip" | UNCLEAR | BgTab.tsx | needs v7 trace |
| BG-6 | Manual `(new direction)` re-extraction on blur | UNCLEAR | BgTab.tsx | needs v7 trace |
| BG-7 | Add Beat button | UNCLEAR | BgTab.tsx | needs v7 trace |
| BG-8 | Insert Beat At Position (right-click → "Insert beat after") | UNCLEAR | BgTab.tsx | needs v7 trace |
| BG-9 | Delete Beat button + confirm modal | UNCLEAR | BgTab.tsx | needs v7 trace |
| BG-10 | Reorder beats via drag-drop | UNCLEAR | BgTab.tsx | needs v7 trace |
| BG-11 | Group beats functionality | UNCLEAR | beat_generator.py | no explicit "group beats" contract found |
| BG-12 | Per-beat Character ref slot | UNCLEAR | BgTab.tsx | needs v7 trace |
| BG-13 | Per-beat BG ref slot | UNCLEAR | BgTab.tsx | needs v7 trace |
| BG-14 | Drag-drop Library → Char ref slot | UNCLEAR | BgTab.tsx | needs v7 trace |
| BG-15 | Drag-drop Library → BG ref slot | UNCLEAR | BgTab.tsx | needs v7 trace |
| BG-16 | Click-to-upload via file picker on each ref slot | UNCLEAR | BgTab.tsx | needs v7 trace |
| BG-17 | Thumbnail preview after upload (≤80px) | UNCLEAR | BgTab.tsx | needs v7 trace |
| BG-18 | Right-click thumbnail → "Remove ref" | UNCLEAR | BgTab.tsx | needs v7 trace |
| BG-19 | Re-click thumbnail to replace | UNCLEAR | BgTab.tsx | needs v7 trace |
| BG-20 | Auto-resize uploads to ≤1280 long-edge (Rule 6.2) | WIRED | beat_generator.py:1407-1420 | `process_crop()` enforces ≤1280 |
| BG-21 | Server-side magic-byte image rejection | WIRED | production_server.py:10023-10027 | `/api/cr/save-crop` validates via PIL |
| BG-22 | Asset registration via `registered_write.py` per LD-421/422 with `iteration_notes` | **WIRED-BUT-BROKEN** | production_server.py:10067-10083 | uses direct Directus write path, NOT explicit `registered_write.register_asset` call. **FIX REQUIRED** |
| BG-23 | "Generate 3 options" button per beat | UNCLEAR | beat_generator.py:1291-1343 | gen logic exists; UI binding needs v7 trace |
| BG-24 | Backend submits 3 gpt-image-2 calls with varied seed via `build_gpt_still_prompt()` (LD-440/439) | WIRED | beat_generator.py:952-1008,1171-1218,1291-1310 | prompt builder + gpt-image-2 path present |
| BG-25 | 3 thumbnails appear in 1×3 layout | UNCLEAR | BgTab.tsx | needs v7 trace |
| BG-26 | Click thumbnail → `selected_option_id` (teal highlight) | UNCLEAR | BgTab.tsx | needs v7 trace |
| BG-27 | Other 2 options stay registered in iteration history per LD-421 | UNCLEAR | production_server.py:9200-9800 | needs v7 trace |
| BG-28 | Re-clicking "Generate 3 options" replaces gen_options array | UNCLEAR | BgTab.tsx | needs v7 trace |
| BG-29 | iteration_notes capture verbatim rejection reason | WIRED | production_server.py:7326-7333,7766 | `iteration_notes` fields written |
| BG-30 | Per-generation cost toast (~4s transient) | UNCLEAR | BgTab.tsx | needs v7 trace |
| BG-31 | Session running total in header | UNCLEAR | BgTab.tsx | needs v7 trace |
| BG-32 | Cost from gpt-image-2 published pricing | UNCLEAR | beat_generator.py:1171-1218 | needs v7 trace |
| BG-33 | Accept All button | WIRED | endpoints.ts:52,105 | endpoint exists |
| BG-34 | Warn modal listing unset beat_ids | UNCLEAR | BgTab.tsx | needs v7 trace |
| BG-35 | Confirm modal: "Lock in N selections..." | UNCLEAR | BgTab.tsx | needs v7 trace |
| BG-36 | POST `/api/bg/accept-beats` (was `/api/beat_gen/accept_all` in v1 — corrected) | WIRED | endpoints.ts:52 | **v1 had wrong endpoint name** |
| BG-37 | Activity log row `BEAT_GEN_ACCEPT_ALL` with selection map | UNCLEAR | production_server.py:8900-9050 | naming needs v7 trace |
| BG-38 | After accept: tab "locked" mode | UNCLEAR | BgTab.tsx | needs v7 trace |
| BG-39 | "Re-open for edit" button (decrement pipeline_stage with confirm) | UNCLEAR | BgTab.tsx | needs v7 trace |
| BG-40 | Cropper invocation from Beat Gen context | WIRED | CropperModal.tsx:90-94,118-136 | wired with target beat + source image |
| BG-41 | Respect TargetVideoSelector (intro/resolution/standalone) | UNCLEAR | BgTab.tsx:129-186 | scope signals exist; full target behavior not validated |

---

## §2 — TAB 2: Cropper (C-*)

| ID | Feature | Status | Evidence | Notes |
|---|---|---|---|---|
| C-1 | Cropper canvas (real impl) | WIRED | CropperCanvas.tsx:1-357 | crop handles + export |
| C-2 | Standalone tab access | WIRED | TabBar.tsx:1-80 | present |
| C-3 | Modal mode invokable from Beat Gen | WIRED | CropperModal.tsx:71-95,183-186 | uses beat target context |
| C-4 | Drag-drop Library → cropper canvas | WIRED | CropperModal.tsx:118-136,187-194 | swaps source |
| C-5 | Pan / zoom on canvas | **WIRED-BUT-BROKEN** | CropperCanvas.tsx:246-271 | only crop-rect drag; NO image pan/zoom |
| C-6 | Crop region selection/resize | WIRED | CropperCanvas.tsx:216-271 | handles |
| C-7 | Save via `cr_save_crop` | WIRED | CropperModal.tsx:90-94 | pathappPatch call |
| C-8 | Enforce shortest-side ≥600px (Rule 6) | WIRED | beat_generator.py:1407-1416 | enforced |
| C-9 | Asset registration via `registered_write.py` (delivery WebP per Rule 6.2) | **WIRED-BUT-BROKEN** | production_server.py:10067-10083 | direct write path, not `registered_write` API. **FIX REQUIRED** |
| C-10 | Reset / cancel crop | WIRED | CropperModal.tsx:63-69,162-169 | present |
| C-11 | Keyboard shortcuts | UNCLEAR | CropperCanvas.tsx:316-347 | no explicit contract found |

---

## §3 — TAB 3: Storyboard (SB-*)

All UNCLEAR — needs v7 symbol-level pass on `StoryboardTab.tsx:1-1515` and per-beat action endpoints. Contract items:

| ID | Feature |
|---|---|
| SB-1 | Read beats from `state.videos[activeTargetVideo].beats` |
| SB-2 | Beat cards in `display_order` |
| SB-3 | Per-beat thumbnail |
| SB-4 | Per-beat dialogue display + edit (contenteditable persistence) |
| SB-5 | `[pause]` marker insertion helper |
| SB-6 | Hide entire beat list when phase_a/phase_b active |
| SB-7 | Per-beat Regenerate Audio button |
| SB-8 | Per-beat Use as Final button |
| SB-9 | Per-beat Preview Beat button |
| SB-10 | Per-beat Send for Lipsync button |
| SB-11 | Per-beat Send for Animation button |
| SB-12 | Per-beat Assign Image button (wire dead `assign_image` endpoint declaration) |
| SB-13 | Per-beat Inject Image button (wire dead `inject_image` endpoint declaration) |
| SB-14 | Drag-drop Library → per-beat image holder |
| SB-15 | Up/down reorder controls |
| SB-16 | Add Beat in Storyboard |
| SB-17 | Delete Beat with confirm |
| SB-18 | "Add magic on still" button (conditional render) |
| SB-19 | "Add magic on video" button (conditional render) |
| SB-20 | path_picker.html integration call-sites |
| SB-21 | "Send Out as MP4" button (finalize → normalize → concat → register → write `completed_mp4_path`) |
| SB-22 | Export Intro button |
| SB-23 | Export Resolution button (renamed from "Win" per LD-412) |
| SB-24 | Export Standalone button |
| SB-25 | Re-send creates new concat MP4 (parent_asset_id linkage) |

---

## §4 — TAB 4: Phase B (PB-*) — Cedric lipsynced video

| ID | Feature | Status | Evidence | Notes |
|---|---|---|---|---|
| PB-1 | Phase B script textarea persists to `state.phase_b.phase_b_script` | **WIRED-BUT-BROKEN** | PhaseProducer.tsx:466-473 | textarea exists; **NO persist write on edit. FIX REQUIRED** |
| PB-2 | Suggest Script button — reads (1) `Canon/UNIFIED_TECHNIQUE_INVENTORY_v1_16.md` for technique catalog; (2) the `### Therapeutic Note —` section embedded in `Arc Skeletons/ARC_<NN>_SKELETON_FINAL.{md\|docx}` for the active module's therapeutic intent (located between `### Narrative Setup` (intro) and `### Resolution` (resolution) per arc skeleton structure) | WIRED-BUT-VERIFY | PhaseProducer.tsx:201-205; production_server.py:7985-7993 | **VERIFY in v7 (Layer 3 critical):** (a) handler resolves active `event_id` → arc number → module within arc → reads correct `Arc Skeletons/ARC_<NN>_SKELETON_FINAL.{md\|docx}` (per CLAUDE.md Rule 10 alignment protocol: read BOTH and diff if they disagree); (b) handler extracts the `### Therapeutic Note —` section for the correct event; (c) handler also loads technique inventory; (d) Claude API prompt actually USES both contexts. If endpoint returns scripts but they're generic AI, Layer 3 silent failure — RELEASE-BLOCKER. Smoke: run Suggest Script for M1E1 (Tessa's Fall, Body-Sensing / Palm Interoception) → output should reference palm/breath/body-sensing technique specifically, NOT generic meditation language |
| PB-3 | Cedric voice resolves from Directus id=1, READ-ONLY UI per LD-463 | WIRED | production_server.py:14382-14387,14396-14417; PhaseProducer.tsx:513-533 | wired |
| PB-4 | Voice stem upload UI (manual override) | STUBBED | PhaseProducer.tsx:495-510 | no manual upload input |
| PB-5 | Regenerate Audio button | WIRED | PhaseProducer.tsx:391-399; production_server.py:16158-16166 | present |
| PB-6 | Cedric base clip dropdown | WIRED | PhaseProducer.tsx:551-565 | present |
| PB-7 | Send for Lipsync button | WIRED | PhaseProducer.tsx:566-574; production_server.py:16899-16907 | present |
| PB-8 | Mix Audio button | NOT-NEEDED (DROPPED) | — | LOCKED 2026-05-06: Phase B pipeline (LD-149/196/348) bakes audio mix INSIDE lipsync step; no separate mix button required. Workflow per Kim: Suggest Script → review → ElevenLabs → review audio → Send for Lipsync → review → place watercolors |
| PB-9 | Export to Stitcher button | WIRED | PhaseProducer.tsx:260-275,586-594 | present |
| PB-10 | Lipsync video player (preview) | WIRED | PhaseProducer.tsx:535-545 | present |
| PB-11 | Watercolor library | WIRED | PhaseProducer.tsx:156-164,665-703 | shown |
| PB-12 | Drag-drop watercolor → timeline | WIRED | PhaseProducer.tsx:348-355; WaveformTimeline.tsx:126-140 | wired |
| PB-13 | Drop-position → `timestamp_ms` in `phase_b_watercolor_cues_json` | WIRED | WaveformTimeline.tsx:135-139; PhaseProducer.tsx:310-320 | persistence path present |
| PB-14 | Cue popover: animation type / duration / Delete | WIRED | CuePopover.tsx:96-121,137-181 | present |
| PB-15 | "Animate this" button per watercolor (LD-464) | WIRED | PhaseProducer.tsx:283-291,690-699 | exists |
| PB-15a | **Watercolor animate WHERE+WHAT-KIND end-to-end** (path_picker textarea reaches Claude API; smoke: same path + different text → different animations) | PARTIALLY-WIRED | path_picker.html:620-635 confirms `motion_description` IS in POST body (Layer 2 ✅); Layer 3 (server uses it in Claude prompt) + Layer 6 (smoke test) UNCLEAR | **CRITICAL GATE per Kim 2026-05-03** — Layer 2 verified 2026-05-06 (Desktop). Cursor v7 must verify Layers 3 + 6 |
| PB-16 | Watercolor cue tile = brown border + cream mat + white interior + centered art (LD-203) | WIRED | app.css:377-401 | styling present |
| PB-17 | Phase B watercolor placement bbox: LEFT 600x540 frame_x=40 (LD-331) | **WIRED-BUT-BROKEN** | production_server.py:17107-17110 | **bbox constants DIFFER from LD-331 spec values. FIX REQUIRED** |
| PB-18 | WaveSurfer waveform | WIRED | WaveformTimeline.tsx:68-77 | integrated |
| PB-19 | `ws.load(audio_url)` source-of-truth (LD-330) | WIRED | WaveformTimeline.tsx:103-106 | present |
| PB-20 | Click-to-seek on waveform | WIRED | WaveformTimeline.tsx:88-96 | present |
| PB-21 | Cue markers visible on waveform | WIRED | WaveformTimeline.tsx:175-188 | present |
| PB-22 | Ambient preset selector inside Phase B producer | REMOVE (LOCKED 2026-05-06) | PhaseProducer.tsx:513-533 | Kim §13 Decision: ambient preset ONLY in Stitcher tab. Remove from Phase B producer. |

---

## §5 — TAB 5: Phase A (PA-*) — Chipper lipsynced + fly-in/fly-out

| ID | Feature | Status | Evidence | Notes |
|---|---|---|---|---|
| PA-1 | Phase A script textarea persists to `state.phase_a.phase_a_script` | **WIRED-BUT-BROKEN** | PhaseProducer.tsx:466-473 | textarea exists; **NO persist write. FIX REQUIRED** |
| PA-2 | Suggest Script button | WIRED | PhaseProducer.tsx:201-205; production_server.py:7985-7993 | wired |
| PA-3 | Chipper voice resolves from Directus id=2 (LD-462) | UNCLEAR | production_server.py:14388-14392 | profile resolution exists; strict id=2 not proven |
| PA-4 | Voice stem upload UI | STUBBED | PhaseProducer.tsx:495-510 | absent |
| PA-5 | Regenerate Audio button | WIRED | PhaseProducer.tsx:391-399; production_server.py:16158-16166 | present |
| PA-6 | Fly-in clip dropdown | **WIRED-BUT-BROKEN** | PhaseProducer.tsx:613-635,652-659 | dropdown exists; **3-clip handling bug (one-clip only). FIX REQUIRED per LD-375** |
| PA-7 | Sitting clip dropdown | WIRED | PhaseProducer.tsx:613-635,652-659 | present |
| PA-8 | Fly-out clip dropdown | WIRED | PhaseProducer.tsx:613-635,652-659 | present |
| PA-9 | Send for Lipsync targets sitting clip per LD-375 | **WIRED-BUT-BROKEN** | PhaseProducer.tsx:233-236 | **uses selected base clip, NOT strictly sitting clip. FIX REQUIRED** |
| PA-10 | "Stitch Fly-In/Out" button (rename from "Mix Audio (auto-stitch)" per Kim 2026-05-06) — fires LD-375 5-stage canonical pipeline AFTER lipsync approval; stitches fly-in + lipsynced sitting + fly-out | WIRED | PhaseProducer.tsx:247-254; production_server.py:16461-16469 | functionality present; **rename label only** |
| PA-11 | Export to Stitcher | WIRED | PhaseProducer.tsx:260-274 | present |
| PA-12 | Lipsync preview player | WIRED | PhaseProducer.tsx:535-545 | present |
| PA-13 | xfade recipe (fade_in 0.5s + fadeblack 2.5s per LD-376) | WIRED | production_server.py:16793-16795,16811-16815 | values present |
| PA-14 | Watercolor library | WIRED | PhaseProducer.tsx:156-164,665-703 | present |
| PA-15 | Drag-drop watercolor → timeline | WIRED | PhaseProducer.tsx:348-355; WaveformTimeline.tsx:126-140 | wired |
| PA-16 | Drop-position → `timestamp_ms` in `phase_a_watercolor_cues_json` | WIRED | WaveformTimeline.tsx:135-139; PhaseProducer.tsx:297-304 | path present |
| PA-17 | Cue popover: animation type / duration / Delete | WIRED | CuePopover.tsx:96-121,137-181 | present |
| PA-18 | "Animate this" button per watercolor (LD-464) | WIRED | PhaseProducer.tsx:283-291,690-699 | present |
| PA-18a | **Watercolor animate WHERE+WHAT-KIND end-to-end** (path_picker textarea → Claude API; same path + different text → different animations) | PARTIALLY-WIRED | path_picker.html:620-635 confirms `motion_description` IS in POST body (Layer 2 ✅); Layer 3 + Layer 6 UNCLEAR | Layer 2 verified 2026-05-06 (Desktop). Cursor v7 must verify Layers 3 + 6 (identical to PB-15a) |
| PA-19 | Phase A watercolor placement bbox: RIGHT 480x540 frame_x=800 (LD-331) | **WIRED-BUT-BROKEN** | production_server.py:17107-17110 | **bbox constants DIFFER from LD-331 spec values. FIX REQUIRED** |
| PA-20 | WaveSurfer waveform | WIRED | WaveformTimeline.tsx:68-77 | present |
| PA-21 | Click-to-seek | WIRED | WaveformTimeline.tsx:88-96 | present |
| PA-22 | Cue markers visible | WIRED | WaveformTimeline.tsx:175-188 | present |
| PA-23 | Ambient preset selector inside Phase A producer | REMOVE (LOCKED 2026-05-06) | PhaseProducer.tsx:513-533 | Kim §13 Decision: ambient preset ONLY in Stitcher tab. Remove from Phase A producer. |

---

## §6 — TAB 6: Stitcher (ST-*)

| ID | Feature | Status | Evidence | Notes |
|---|---|---|---|---|
| ST-1 | 4-slot strip in fixed order: intro → Phase A → Phase B → resolution | WIRED | StitcherTab.tsx:28-35,479-487 | present |
| ST-2 | Each slot reads from corresponding `completed_mp4_path` / `state.phase_a.phase_a_stitched_file` / `state.phase_b.phase_b_lipsync_file` | UNCLEAR | StitcherTab.tsx:127-140; production_server.py:15233-15267 | exact field mapping not proven |
| ST-3 | Per-slot Ambient bed dropdown (LD-466) | WIRED | StitcherTab.tsx:552-565,303-311 | present |
| ST-4 | Per-slot SFX cue placement UI | WIRED | StitcherSlotWaveform.tsx:42-56; StitcherTab.tsx:325-346 | exists |
| ST-5 | Per-slot Transitions UI | WIRED | StitcherTransitionSelector.tsx:39-43; StitcherTab.tsx:591-605 | exists |
| ST-6 | Per-slot Trims UI | WIRED | StitcherTab.tsx:517-550 | numeric trim inputs (Kim LOCKED 2026-05-06, see §13). **DO NOT swap for sliders** |
| ST-7 | Per-slot Loudnorm toggle (LD-471) | WIRED | StitcherTab.tsx:576-584,249-267 | present |
| ST-8 | Per-slot Preview button | WIRED | StitcherTab.tsx:210-219,567-575 | wired |
| ST-9 | Per-slot Bake button | **MISSING** | — | **only final-bake exists; per-slot bake absent. ADD** |
| ST-10 | Final module Bake | WIRED | StitcherTab.tsx:636-644; production_server.py:15968-15976 | wired |
| ST-11 | Module-level `pause_after_ms` wiring | UNCLEAR | production_server.py:7365-7383 | scene assemble path present; stitch flow unclear |
| ST-12 | Standalone 1-slot mode (milestone scope) | WIRED | StitcherTab.tsx:141-157 | present |
| ST-13 | Direct single-slot bake (milestone export) | WIRED | StitcherTab.tsx:155-157,636-644 | present |
| ST-14 | Mode auto-detect from `activeProjectType` signal | **WIRED-BUT-BROKEN** | StitcherTab.tsx:141-144 | **mode inferred from slots length, NOT activeProjectType. REFACTOR** |
| ST-15 | Sound Library tier filter (ambient / sfx / transitions) in Stitcher | **MISSING** | — | **no tier filter dropdown. ADD** |
| ST-16 | LibraryPanel tier extension (ambient / sfx / transitions / images / watercolors) | **WIRED-BUT-BROKEN** | LibraryPanel.tsx:62-69,124-157 | **image-centric only. EXTEND** |
| ST-17 | Audit standalone /stitch_editor for missing features | DOCTRINE-ONLY | STORYBOARD_V59_S5_5_G_SPEC_v1.md:13-14,157-162 | process item |
| ST-18 | Port SFX placement UI from /stitch_editor | WIRED | StitcherSlotWaveform.tsx:1-3; StitcherTab.tsx:325-346 | port done |
| ST-19 | Port transition UI | WIRED | StitcherTransitionSelector.tsx:1-3; StitcherTab.tsx:596-605 | port done |
| ST-20 | Per-slot trim controls (numeric) | WIRED | StitcherTab.tsx:517-550 | LOCKED numeric (Kim 2026-05-06). No slider port required |
| ST-21 | Port inter-slot fade controls | WIRED | StitcherTransitionSelector.tsx:109-123; production_server.py:15890-15900 | present |
| ST-22 | Retire standalone /stitch_editor after parity | DOCTRINE-ONLY | STORYBOARD_V59_S5_5_G_SPEC_v1.md:284-285 | policy |

---

## §7 — Cross-Cutting (CC-*)

| ID | Feature | Status | Evidence | Notes |
|---|---|---|---|---|
| CC-1 | ProjectSelector (renamed from EventSelector, lists events + milestones) | WIRED | ProjectSelector.tsx:316-334,441-472 | implemented |
| CC-2 | "+ New Event" / "+ New Milestone" options | WIRED | ProjectSelector.tsx:45-47,125-129,241-245,457-470 | present |
| CC-3 | Routes to `/api/event/load` / `/api/milestones/load` | WIRED | ProjectSelector.tsx:385-391,414-418 | wired |
| CC-4 | URL `?event=<id>` OR `?milestone=<id>` updates | WIRED | ProjectSelector.tsx:406-409,423-426 | wired |
| CC-5 | Phase A/B disabled in milestone scope; Stitcher stays ENABLED (1-slot mode) | WIRED | TabBar.tsx:36-39,47-52 | LOCKED 2026-05-06 (Kim §13). Current code is correct; v1 spec was wrong |
| CC-6 | Beat Generator + Storyboard operational in milestone scope (target=standalone) | UNCLEAR | BgTab.tsx:129-186 | needs v7 trace |
| CC-7 | TargetVideoSelector (renamed from VideoSelector) | **WIRED-BUT-BROKEN** | app.tsx:91-93 | **still named VideoSelector. RENAME** |
| CC-8 | Dropdown options: intro / resolution only | WIRED | VideoSelector.tsx:37-43 | present |
| CC-9 | Hidden when milestone scope active | **WIRED-BUT-BROKEN** | app.tsx:91-93 | **selector NOT hidden in milestone scope. FIX** |
| CC-10 | `pathappPatch` auto-injects `scope_target_video` GLOBALLY | WIRED | client.ts:216-218 | LOCKED global (Kim 2026-05-06 §13). Current global injection is correct |
| CC-11 | Defaults to `intro` on event load | **WIRED-BUT-BROKEN** | scope.ts:56-57 | default exists; event-load reset contract not explicit |
| CC-12 | Auto-inject scope_target_video | WIRED | client.ts:216-218 | injected |
| CC-13 | Skip auto-injection for Phase A/B/Stitcher mutations | WIRED (not required) | client.ts:216-218 | LOCKED — global injection is fine; handlers ignore the field (Kim 2026-05-06 §13) |
| CC-14 | Auto-inject scope_milestone_id | WIRED | client.ts:224-225 | wired |
| CC-15 | LibraryPanel has draggable items | WIRED | LibraryPanel.tsx:127-133,155 | draggable tiles |
| CC-16 | Drop zones on storyboard image holders, BG ref slots, Cropper, Phase A/B watercolor timelines | **WIRED-BUT-BROKEN** | BgTab.tsx:668-701; CropperModal.tsx:187-194; PhaseProducer.tsx:477-484 | **Storyboard image-holder drop zone evidence missing. ADD** |
| CC-17 | Library tier filter UI | **MISSING** | — | **not built** |
| CC-18 | Library search/filter | **MISSING** | — | **not built** |
| CC-19 | Library item preview interaction | **MISSING** | — | **not built** |
| CC-20 | Modal component | WIRED | ui/Modal.tsx:1-95 | exists |
| CC-21 | Toast component | WIRED | ui/Toast.tsx:1-111 | exists |
| CC-22 | Spinner component | WIRED | ui/Spinner.tsx:1-43 | exists |
| CC-23 | All ref uploads via `registered_write.py` | **WIRED-BUT-BROKEN** | production_server.py:10008-10012,10067-10173 | **upload/crop bypass `registered_write` API. FIX REQUIRED** |
| CC-24 | All generated stills via `registered_write.py` | UNCLEAR | beat_generator.py:1226-1343 | linkage unresolved |
| CC-25 | All Phase A/B mp4 outputs via `registered_write.py` | UNCLEAR | PhaseProducer.tsx:260-281; production_server.py:16061-16087 | "all outputs" not proven |
| CC-26 | iteration_notes captured at production-time | WIRED | production_server.py:7326-7333,7766 | captured |
| CC-27 | parent_asset_id linkage | **WIRED-BUT-BROKEN** | production_server.py:7340,7764 | **set None in key paths. FIX REQUIRED** |
| CC-28 | find_asset.py query support | WIRED | find_asset.py:3-14,71-83; registered_write.py:458-466 | exists |
| CC-29 | HTML preview pages in Safari (NOT file://) | WIRED | find_asset.py:6,14 | present |
| CC-30 | Production Map data: bulk-load script for 59 V1 modules | WIRED | populate_prod_modules_from_gameplay_scope.py:3-8,211-217,295-306 | exists |
| CC-31 | Production Map renders all 10 arcs × ~6 modules | **WIRED-BUT-BROKEN** | ProductionMapTab.tsx:146-223; production_server.py:8765-8768 | rendering wired; **backend cap may not guarantee full 10×6** |
| CC-32 | Per-module per-segment status matrix (LD-465) | WIRED | ProductionMapTab.tsx:49-64,73-90,161-217; production_server.py:8814-8885 | implemented |
| **CC-33** | **Module-level `state.module_sfx_cues` separate from per-slot cues** (NEW — Cursor v6 finding) | UNCLEAR | — | **module-level SFX cue structure exists; relationship to per-slot cues not documented** |
| **CC-34** | **Production Map raw fetch architectural concern** (NEW — Cursor v6 finding) | UNCLEAR | ProductionMapTab.tsx | **bypasses pathappPatch / scope guards** |

---

## §8 — Backend Endpoints (EP-*)

**Important:** v1 used `/api/beat_gen/*` namespace which does NOT exist. Actual namespace is `/api/bg/*` (key names like `bg_submit_gpt_batch`, `bg_accept_option`, `bg_add_beat`, `bg_delete_beat`, `bg_accept_beats`). v2 corrected.

| ID | Endpoint | Status | Evidence |
|---|---|---|---|
| EP-1 | `/api/timeline/cues` | WIRED | endpoints.ts:85; production_server.py:5428-5430,14801-14809 |
| EP-2 | `cr_save_crop` | WIRED | endpoints.ts:61; production_server.py:5388-5389,10008-10173 |
| EP-3 | `assign_image` | WIRED | endpoints.ts:58; production_server.py:5348-5349,13243-13311 |
| EP-4 | `inject_image` | WIRED | endpoints.ts:60; production_server.py:5352-5353,13313-13406 |
| EP-5 | beat regenerate audio | WIRED | endpoints.ts:109; production_server.py:5406-5407,14031-14157 |
| EP-6 | use_as_final | WIRED | endpoints.ts:115; production_server.py:5416-5417,14295-14374 |
| EP-7 | preview path (stitch_preview) | WIRED | endpoints.ts:76 | beat-level binding UNCLEAR |
| EP-8 | send_for_lipsync (Phase A/B) | WIRED | endpoints.ts:81; production_server.py:16899-16907 |
| EP-9 | send_for_animation | WIRED | endpoints.ts:110,111; production_server.py:5408-5409 |
| EP-10 | `/api/phase/suggest_script` | WIRED | endpoints.ts:71; production_server.py:5411-5413,7985-7993 |
| EP-11 | Beat Gen ref upload — actual: `cr_upload` + `bg_accept_lib_image` (v1 expected `/api/beat_gen/upload_ref`) | STUBBED | endpoints.ts:107 | **inventory naming mismatch corrected** |
| EP-12 | Beat Gen generate — actual: `bg_submit_gpt_batch` (v1 expected `/api/beat_gen/generate`) | STUBBED | endpoints.ts:104 | **mismatch corrected** |
| EP-13 | Beat Gen select option — actual: `bg_accept_option` (v1 expected `/api/beat_gen/select_option`) | STUBBED | endpoints.ts:105 | **mismatch corrected** |
| EP-14 | `bg_add_beat` | WIRED | endpoints.ts:103; production_server.py:9598-9629 |
| EP-15 | `bg_delete_beat` | WIRED | endpoints.ts:102; production_server.py:9095-9128 |
| EP-16 | `/api/bg/accept-beats` (v1 expected `/api/beat_gen/accept_all`) | WIRED | endpoints.ts:52; production_server.py:9227-9311 | **corrected** |
| EP-17 | `milestones/list` | WIRED | endpoints.ts:34; production_server.py:5258-5259,6807-6835 |
| EP-18 | `milestones/create` | WIRED | endpoints.ts:95; production_server.py:5450-5451,6837-6901 |
| EP-19 | `milestones/load` | WIRED | endpoints.ts:96; production_server.py:5452-5453,6903-6974 |
| EP-20 | `project/list` | WIRED | endpoints.ts:33; production_server.py:5260-5261,6976-7033 |
| EP-21 | `beat/finalize` | WIRED | endpoints.ts:97; production_server.py:5454-5455,7308-7364 |
| EP-22 | `scene/assemble` | WIRED | endpoints.ts:98; production_server.py:5456-5457,7365-7383 |
| EP-23 | beat graft | WIRED | endpoints.ts:124; production_server.py:5289-5290,12609-12709 |
| **EP-24** | **`event_create` mutation endpoint + modal flow** (NEW — Cursor v6 finding) | UNCLEAR | — | **shipped but not in v1 inventory; needs trace + smoke** |

---

## §9 — Magic Compositor (MAG-*)

| ID | Feature | Status | Evidence | Notes |
|---|---|---|---|---|
| MAG-1 | Visible-magic endpoints (magic_still / magic_video) | **WIRED-BUT-BROKEN** | production_server.py:5418-5421,8201-8204; StoryboardTab.tsx | endpoints exist; **explicit `magic_still_path`/`magic_video_path` storage names not confirmed. VERIFY** |
| MAG-2 | SFX cue placement at Stitcher level | WIRED | StitcherTab.tsx:325-346; production_server.py:14801-14809 | present |
| MAG-3 | Blend-math quality | DOCTRINE-ONLY | production_server.py:8203-8204,8315-8318 | compositor-domain concern, outside this inventory's build scope |
| **MAG-4** | **Watercolor animate WHERE+WHAT-KIND end-to-end** (LD-470) — see PB-15a + PA-18a | UNCLEAR | path_picker.html:214,316 | **CRITICAL — 9 verification gates per v1 §Phase B watercolor section** |

---

## §10 — Rule 19 Violations (LL-28-style — placeholder/future/stub comments in shipped code)

Per Rule 19 + Rule 27: shipping code MUST NOT contain "future", "stub", "later", "TODO", "FIXME" comments unless tracked by an explicit SHORTCUT_* LD with closure plan.

| Location | Comment | Action |
|---|---|---|
| `AssetTile.tsx:7-8` | "future" consumer comment | Delete or convert to LD reference |
| `LibraryPanel.tsx:6-8` | "future drop targets" comment | Delete or convert |
| `PhaseProducer.tsx:10-13` | deferred/future shipping comment | Delete or convert |
| `production_server.py:12-13` | top docstring references stubs | Update or convert |
| `production_server.py:7337` | inline "stub/refine later" (`module_id=1`) | Fix the hardcode or LD it |
| `production_server.py:7761` | inline "stub/refine later" (`module_id=1`) | Fix the hardcode or LD it |

---

## §11 — Watercolor Animate End-to-End Verification (CRITICAL)

(Per Kim 2026-05-03 — preserved verbatim from v1 §Phase B watercolor section.)

The "Animate this" workflow has TWO inputs:
1. **WHERE:** drawn path on path_picker.html canvas
2. **WHAT-KIND:** text in path_picker.html line 214 textarea

Both feed Claude API → ffmpeg `filter_complex` (LD-470) → magic_compositor procedural render → composited onto Phase A/B at LD-331 bbox.

**9 verification gates:**

1. ✅ path_picker.html line 214 textarea exists
2. ✅ path_picker.html line 316 helper text says "Draw the WHERE; describe the WHAT-KIND"
3. ❓ path_picker.html submit handler POST body includes textarea content as named field (e.g., `intent_description`)
4. ❓ `/api/watercolor/animate` accepts `intent_description` and passes to Claude API prompt
5. ❓ Claude API prompt explicitly uses BOTH path geometry AND intent description
6. ❓ Smoke 1: wavy line + "moving up and down" → matches description
7. ❓ Smoke 2: same line + "trembling in place" → animation differs from #6
8. ❓ Smoke 3: different line + "moving up and down" → reflects new path
9. ❓ Risk check: if smoke tests show identical animations regardless of text → RELEASE-BLOCKER

---

## §12 — Updated partition into sub-sessions

Status-aware partition (per Cursor v6 + open work):

### S5.5c — Beat Generator (most UNCLEAR — needs full v7 trace before scoping)
- All 41 BG-* items (mostly UNCLEAR; v7 needed)
- Cropper C-* items (mostly WIRED — minor fixes: C-5 pan/zoom, C-9 registered_write)
- Library drag-drop primitives (CC-15 done, CC-16 needs Storyboard zone, CC-17/18/19 missing)
- Modal/Toast/Spinner already WIRED (CC-20/21/22)

### S5.5e — Storyboard buttons + Production Map data + ProjectSelector cleanup
- All 25 SB-* items (UNCLEAR — needs full v7 trace)
- ProjectSelector cleanup: CC-7 rename, CC-9 hide-on-milestone, CC-11 default-on-event-load
- Production Map fixes: CC-31 backend cap, CC-34 raw fetch architectural concern
- Module SFX cues: CC-33 relationship documentation
- Event create flow: EP-24 trace + smoke

### S5.5f — Phase A/B feature parity + watercolor end-to-end
- **PB-1 textarea persist (BUG)**, **PA-1 textarea persist (BUG)**
- **PB-8 add Mix Audio button (MISSING)**
- **PA-6 3-clip handling (BUG)**, **PA-9 lipsync target sitting clip (BUG)**
- **PB-17, PA-19 bbox constants vs LD-331 (BUG)**
- PB-4, PA-4 voice stem upload UI (STUBBED → build)
- **PB-15a, PA-18a, MAG-4 — watercolor animate end-to-end** (CRITICAL gates)
- All 9 verification gates per §11

### S5.5g — Stitcher SFX/transitions/trims + Library tier filter
- ST-9 add per-slot bake button (MISSING)
- ST-14 refactor mode auto-detect (BUG)
- ST-15 Stitcher tier filter (MISSING)
- ST-16 LibraryPanel tier extension (BUG)
- ST-6/ST-20 trim slider vs numeric (PENDING-KIM — see §13)
- ST-17, ST-22 audit + retire /stitch_editor (DOCTRINE)

### S5.5h (NEW — Asset findability + Rule 19 cleanup)
- BG-22, C-9, CC-23, CC-24, CC-25 — refactor all writes through `registered_write.py`
- CC-27 — fix `parent_asset_id` linkage
- §10 LL-28 violations — delete placeholder/future comments per Rule 19/27

---

## §13 — Kim decisions (LOCKED 2026-05-06)

**Decision 1: Trim controls = NUMERIC INPUTS (LOCKED)**
- ST-6 / ST-20 / S5.5g executing session: do NOT swap numeric inputs for sliders. Current implementation is correct.
- Status flip: ST-6 and ST-20 should be WIRED (not WIRED-BUT-BROKEN) — they were only "broken" against v1's incorrect spec wording
- Lesson recorded: see §13a below

**Decision 2: pathappPatch `scope_target_video` injection = GLOBAL (LOCKED)**
- CC-10 / CC-13: keep current global injection. Phase A/B/Stitcher handlers ignore the field — harmless extra ~20 bytes per request
- Status flip: CC-10 / CC-13 should be WIRED (not WIRED-BUT-BROKEN) — they were only "broken" against v1's "BG+SB only" wording
- Lesson recorded: see §13a below

**Decision 3: Stitcher in milestone scope = ENABLED (LOCKED)**
- CC-5: Stitcher STAYS enabled (1-slot standalone mode for milestone export). Only Phase A and Phase B disabled
- Status flip: CC-5 should be WIRED (not WIRED-BUT-BROKEN) — was only "broken" against v1's incorrect spec
- Workflow confirmed: see §13b below

**Status update:** All three "WIRED-BUT-BROKEN" classifications were against my (wrong) v1 spec. With v2's corrected spec, all three are WIRED. Net Cursor v6 verified-correct count rises from 86 → 90 (4 items reclassified).

### §13a — Authoring discipline lesson (per Kim 2026-05-06)

The pattern that produced these 3 false-broken items: I authored inventory items based on IMAGINED UI/contract specifics, not what was actually built or what Kim explicitly decided. Cursor's verification then found "my imagination ≠ reality" mismatches, classified them as WIRED-BUT-BROKEN, and Kim had to spend cycles deciding between phantom alternatives.

**Going forward, when authoring inventory items:**
- Prefer LOOSE terms ("trim controls", "generation results", "scope auto-injection") over SPECIFIC terms ("trim sliders", "3×3 grid", "BG+SB only injection")
- If a UI specific is genuinely required (e.g., LD-331 bbox values), CITE the source (LD or Kim chat) rather than inventing
- If unsure whether a UI specific is required, mark `[UNDECIDED]` rather than picking arbitrarily
- Never invent endpoint names — grep the actual `endpoints.ts` catalog first

This lesson supersedes any future "loose vs strict spec" confusion. Cross-reference: `feedback_six_layer_feature_verification.md` (the parent rule about end-to-end verification).

### §13b — Milestone export workflow (CONFIRMED 2026-05-06)

Milestones have NO Phase A and NO Phase B. They're independent multi-beat videos. The export path:

1. **Beat Generator** (with TargetVideoSelector hidden — milestones always target `standalone`) → author beats for the milestone
2. **Storyboard** → assemble beats, edit dialogue, assign images
3. **"Send Out as MP4" button** (SB-21) → finalize beats → normalize per LD-284 → ffmpeg concat → register via `registered_write.py` → write `completed_mp4_path` to `state.videos.standalone.completed_mp4_path`
4. **Stitcher in 1-slot standalone mode** (ST-12 / ST-13 — already WIRED) → reads `state.videos.standalone.completed_mp4_path` → final export

**Critical verification gate (NEW — add to S5.5e gates):**
- [ ] SB-21 "Send Out as MP4" works in milestone scope (writes to `state.videos.standalone.completed_mp4_path`, NOT to `state.videos.intro.completed_mp4_path`)
- [ ] Stitcher 1-slot mode picks up the milestone's `completed_mp4_path` automatically when ProjectSelector shows a milestone
- [ ] Direct path: BG → SB → Send Out → Stitcher → export works end-to-end without any Phase A/B intermediate step

**Status: SB-21 currently UNCLEAR per Cursor v6.** Whether it correctly handles milestone scope (writes to `videos.standalone` partition) vs hardcoded to event scope is what v7 will determine. If broken in milestone scope, the fix is small — just route the partition write per `activeProjectType` signal.

**Kim's question answered:** Yes, the existing "Send Out as MP4" button is the right surface — no new "send to stitcher" button needed. But it must work in milestone scope.

---

## §13c — Imagined Specifics Audit (added 2026-05-06 per Kim request)

Following the §13a authoring-discipline lesson, this is a sweep of v2 for items where I specified UI/contract details that I made up rather than verified or got from Kim/LD. Each gets one of: **LOCKED** (Kim picks now), **LOOSEN** (rewrite to generic), or **VERIFY** (kick to Cursor v7 / smoke test).

### Category A: Specific values / counts I made up

| Item | What I specified | Source check | Recommendation |
|---|---|---|---|
| BG-30 | Cost toast "~4s transient" | I made the timing up | **LOOSEN** to "transient cost toast" |
| BG-17 | Thumbnail "≤80px long edge" | I made the size up | **LOOSEN** to "thumbnail size readable but compact" |
| BG-25 | "3 thumbnails appear in 1×3 layout" | I made the layout up | **LOOSEN** to "3 thumbnails visible together"; let implementation pick 1×3 vs 3×1 |
| BG-32 | Cost "from gpt-image-2 published pricing" | Real (LD-440) | **KEEP** |
| PA-3 | "Chipper voice from Directus id=2" | LD-462 cites id=2 | **VERIFY** Cursor v6 said "strict id=2 guarantee not proven" — confirm in v7 |
| PA-13 | "fade_in 0.5s + fadeblack 2.5s per LD-376" | LD cited | **VERIFY** Cursor said values present at line 16793-16795; spot-check matches LD-376 exactly |
| PB-17/PA-19 | LD-331 bbox values | Cursor caught actual constants differ from values I cited | **VERIFY** what the actual LD-331 says vs what's coded (this is a real bug regardless) |

### Category B: UI patterns I imagined

| Item | What I specified | Need? | Recommendation |
|---|---|---|---|
| BG-5, BG-8, BG-18 | "Right-click → context menu" actions (Edit chip, Insert beat after, Remove ref) | Could be button alternatives | **PENDING-KIM** — right-click context menus or visible buttons? Right-click is faster but discoverable; visible buttons are obvious but cluttered |
| BG-9, BG-35, SB-17 | Confirm modal exact copy ("cannot be undone", "Lock in N selections...") | Real warnings needed | **LOOSEN** to "destructive action confirm modal"; let implementation pick wording |
| BG-10, SB-15 | Reorder beats: I wrote "drag-drop" in BG-10 and "up/down controls" in SB-15 — inconsistent | Both work; pick one | **PENDING-KIM** — drag-drop or up/down buttons? Recommend drag-drop (matches Library drag pattern) |
| C-5 | "Pan / zoom on cropper canvas" | Cursor said NOT present | **PENDING-KIM** — do you actually need to pan/zoom the source image while cropping? Or is fixed-fit acceptable? |
| C-11 | "Keyboard shortcuts" | Cursor: UNCLEAR | **PENDING-KIM** — do you want keyboard shortcuts? If no, drop the item |
| ST-9 | Per-slot bake button MISSING | Final bake exists | **PENDING-KIM** — do you actually need per-slot bake, or is final-module bake sufficient? Per-slot is useful for iterating one segment at a time without re-baking everything |
| PA-6/7/8 | 3 separate clip dropdowns (fly-in / sitting / fly-out) | Cursor said one dropdown exists with one-clip bug | **PENDING-KIM** — design intent: 3 separate dropdowns where Kim picks each, OR 1 dropdown for the SITTING clip with fly-in/out auto-selected from a standardized library? |
| PB-22, PA-23 | Ambient preset selector INSIDE phase producer | Stitcher already has it | **PENDING-KIM** — do you want ambient selection in the Phase A/B producers AND the Stitcher? Or only in the Stitcher? |
| CC-17/18/19 | Library tier filter / search / item preview | All MISSING | **PENDING-KIM** — which of these do you actually need? Library will get long with 59 modules' worth of assets |

### Category C: Field names / log names I invented

| Item | What I specified | Verify | Recommendation |
|---|---|---|---|
| PB-15a / MAG-4 | path_picker textarea POST field name `intent_description` | Made up the name | **VERIFY** in v7 — find actual field name in path_picker.html submit handler. If textarea content reaches server at all, the field name exists; just need to use the real name |
| §3.1 (state shape) | `completed_mp4_path` for partition export target | Made up | **VERIFY** — the field needs to exist somewhere; if `completed_mp4_path` doesn't exist yet, propose the name explicitly when writing S5.5e session spec |
| BG-37 | Activity log row name `BEAT_GEN_ACCEPT_ALL` | Made up | **VERIFY** Cursor: "naming not conclusively traced". Find what the actual code writes |
| MAG-1 | Storage field names `magic_still_path` / `magic_video_path` | Made up | **VERIFY** — Cursor: "explicit storage names not confirmed" |

### Category D: Behavior contracts that need Kim confirmation

| Item | What I specified | Open question |
|---|---|---|
| PB-8 | "Phase B Mix Audio button MISSING — ADD for parity" | Does Phase B's pipeline (Cedric lipsync + watercolor + ambient bed) need a Mix Audio step? Phase A's auto-stitch fires the LD-375 5-stage canonical; Phase B's pipeline (LD-149/196) might not need an analog. **PENDING-KIM** |
| BG-11 | "Group beats functionality (if applicable from prior design)" | Pure speculation. **PENDING-KIM** — is there a "group beats" feature you've discussed before? If not, drop the item |
| BG-3, BG-6 | Stage-direction regex `\(([^)]{4,50})\)` max 2 | Specific regex + count cap. From earlier S5.5c spec | **VERIFY** — confirm regex is what's in beat_generator.py; "max 2" was my call |
| SB-5 | `[pause]` marker insertion helper | Specific marker syntax | **VERIFY** — what's the actual pause-marker syntax in current dialogue text? Could be `[pause]`, `(pause)`, or something else |
| SB-22/23/24 | "Export Intro / Resolution / Standalone" buttons | Three separate export buttons in Storyboard | **PENDING-KIM** — three separate buttons OR one "Export" button that infers target from `activeTargetVideo`? One button with target inference seems cleaner |

### Category E: Things Cursor flagged that need implementation decision

| Item | Cursor finding | Recommendation |
|---|---|---|
| CC-31 | "backend cap may not guarantee full 10×6 modules" | **VERIFY** — confirm Production Map endpoint returns all 59 modules (no limit/pagination) |
| CC-33 | "Module-level state.module_sfx_cues separate from per-slot cues" | **PENDING-KIM** — do you intend module-level SFX (overall ambient) vs per-slot SFX (segment-specific)? Both? |
| CC-34 | "Production Map raw fetch — bypasses pathappPatch" | **REFACTOR** — should use pathappPatch for consistency |
| EP-24 | "event_create mutation endpoint and modal flow shipped but not in v1 inventory" | **VERIFY** — confirm exists, document the flow, check it works in milestone scope (probably doesn't apply) |

### Audit summary

- **Category A (specific values):** 7 items — 3 LOOSEN, 4 VERIFY in v7
- **Category B (UI patterns):** 9 items — 3 LOOSEN, 6 PENDING-KIM
- **Category C (field/log names):** 4 items — all VERIFY in v7 (real names exist; just use them)
- **Category D (behavior contracts):** 5 items — 3 PENDING-KIM, 2 VERIFY
- **Category E (Cursor flagged):** 4 items — 1 PENDING-KIM, 1 REFACTOR, 2 VERIFY

**Total Kim decisions needed (PENDING-KIM):** 9 items

**Total deferred to Cursor v7 trace (VERIFY):** ~12 items beyond the original 71 UNCLEAR

When you call the 9 PENDING-KIM decisions, I'll update v2 → v3 with locks. The VERIFY items roll into Cursor v7's pass naturally (v7 will trace them as part of the UNCLEAR sweep).

---

## §14 — Cursor v7 prompt (for the 71 UNCLEAR items)

Send Cursor this prompt with the v2 inventory:

```
You are doing a Cursor v7 verification pass on
Production/docs/V59_FEATURES_MASTER_INVENTORY_v2.md.

Cursor v6 (commit 9efaabd) verified 131 of 202 items. 71 items
remain UNCLEAR. Your job: convert each UNCLEAR to either WIRED,
WIRED-BUT-BROKEN, STUBBED, or MISSING via direct symbol-level
tracing.

For each UNCLEAR item:
1. Locate the relevant symbol(s) in the codebase (component,
   handler, endpoint, state path)
2. Trace the contract end-to-end: UI element → event handler →
   API call → server handler → state mutation → UI re-render
3. Verify the 6-layer contract from the inventory's MANDATORY
   section
4. Status definitions:
   - WIRED: all 6 layers present and correct
   - WIRED-BUT-BROKEN: layers 1-5 present but layer 6 fails OR a
     contract is violated (wrong field name, wrong endpoint
     called, wrong state path written)
   - STUBBED: UI shell exists but no real wiring (dead handler,
     dead endpoint, no state mutation)
   - MISSING: not built at all

Output format: same matrix format as v6 (ID | STATUS | FILE:LINES
| NOTES). For WIRED-BUT-BROKEN and STUBBED, the NOTES column
must specify exactly what's broken or stubbed.

Skip the items already verified in v6 (anything not marked
UNCLEAR in v2). Focus on the 71 UNCLEAR rows.

Return the binary verdicts so v3 can be a clean done/not-done
sheet.
```

---

## §15 — Next steps after Cursor v7 returns

1. Author **inventory v3** with v7 verdicts folded in (UNCLEAR → binary)
2. Author tech-spec for **next sub-session** (probably S5.5c since BG has the most UNCLEAR items needing v7 first)
3. v3 + sub-session spec → Cursor cross-review (one more time, optional)
4. Fresh-terminal handoff → atomic execution

---

**End of inventory v2.** Ready for Cursor v7 pass.
