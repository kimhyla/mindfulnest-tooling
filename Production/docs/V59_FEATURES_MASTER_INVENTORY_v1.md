# V59 Production Tool — Master Feature Inventory v1

**Date:** 2026-05-03
**Purpose:** Comprehensive feature checklist for v59 Preact client to be production-ready. Input for the next tech-spec session that partitions these across S5.5c → e → f → g.
**Authority:** Compiled from v3 architecture spec, browser smoke 2026-05-03, agent inventory cross-check, prior session memories, and Kim's explicit feature requests in chat 2026-05-03.

**Critical reading:** This doc lists FEATURE REQUIREMENTS, not implementation status. Some items are partially done, some have UI shells without backend wiring, some are not started. The next tech-spec session must verify CURRENT STATE per item before scoping.

---

## ⚠️ MANDATORY — End-to-End Verification Contract for EVERY Feature Below

**The single biggest failure mode for this inventory:** treating a feature as "done" because the UI element exists, when in fact the input is silently dropped between the UI and the backend, or the backend ignores it, or the output doesn't reflect the input.

**For every checkbox in this document, the feature is NOT done until ALL six layers verify:**

1. **UI element exists** — button rendered, drop zone reactive, textarea editable, etc.
2. **UI → backend wiring** — the user's input reaches the server in the expected payload shape with the expected field names (no silently-dropped fields, no shape mismatches)
3. **Backend processing matches intent** — the server actually USES the input. Not "the request returns 200" but "the request body materially affects the output"
4. **State update propagation** — the result is written to the right partition / database row / file path with the right metadata (iteration_notes, parent_asset_id, timestamps, etc.)
5. **UI re-render reflects new state** — the user sees the correct outcome (thumbnail updates, status changes, cost displays, error messages)
6. **End-to-end smoke test confirms intent → outcome** — vary the input, observe the output changes meaningfully. Same input twice → same output. Different input → different output.

**If a feature passes layers 1-5 but fails layer 6 (input doesn't actually shape the output), it is a RELEASE-BLOCKER, not partial completion.**

### Categories of features at HIGH RISK for layer 2/3/6 silent failure:

| Risk class | Examples | Specific risk |
|---|---|---|
| **AI-driven** | Suggest Script, 3-option GPT generation, Animate this watercolor (with WHAT-KIND text), Beat dialogue suggestions | Input gets dropped client-side OR AI ignores the input. Output looks plausible but doesn't reflect what the user provided. |
| **Multi-stage pipelines** | Phase A 5-stage canonical (LD-375), Phase B Cedric pipeline (LD-149/196/348), magic compositor | Stage 3 silently fails / no-ops; final output looks "close enough" but a stage was skipped |
| **Async / fire-and-forget** | Send for Lipsync, Send for Animation, GPT job submission | Success/failure not surfaced to UI; user thinks it worked when it didn't |
| **Drag-drop interactions** | Library → image holder, library → ref slot, library → cropper, watercolor → timeline | Wrong asset path delivered, wrong format, wrong target field updated |
| **Side-effect captures** | iteration_notes capture, parent_asset_id linkage, auto-resize, registered_write.py adoption | Side effect "works" 95% of the time but skipped on edge cases (specific paths, specific formats, error paths) |
| **Cost / metric displays** | Per-gen cost toast, session running total, beat counts | Hardcoded estimates instead of real API response data |
| **Conditional rendering** | "Add magic on still" vs "Add magic on video" (beat 1 vs others), tab disabling on milestone scope | Conditions tested for happy path, fail on edge cases |
| **State persistence** | TargetVideoSelector switch persistence, locked-mode after Accept All, scope swap state preservation | Works in current session, fails after page refresh |

### Mandatory verification protocol for every session executing items from this inventory

**Phase 0 of any feature-build session:**
1. Read this contract section (above)
2. For the features in scope, identify which RISK CLASS each falls into
3. Add explicit smoke tests to the verification gates that vary the input and observe the output
4. Treat "the request returns 200" as NECESSARY but NOT SUFFICIENT
5. Browser smoke is the final arbiter — server-side gates do NOT verify user-visible correctness (per `feedback_browser_smoke_required.md`)

**If a feature is documented as "already wired" or "exists" in this inventory, the session executing it must STILL run the 6-layer verification.** Documentation said the watercolor Animate this textarea was wired — verification would have caught (or confirmed) that the textarea content actually flows through to Claude API.

**If smoke testing isn't possible in-session** (requires Kim hands-on), explicitly DEFER that feature to Kim's review and don't mark COMPLETE until she confirms.

---

---

## TAB 1: Beat Generator

### Core authoring
- [ ] Extract Beats action (extract beats from arc skeleton or external source into the active partition)
- [ ] Per-beat dialogue textarea (editable, persists to `state.videos.<target>.beats[id].dialogue`)
- [ ] Stage-direction extraction chips (regex `\(([^)]{4,50})\)`, max 2, extracted on textarea blur)
- [ ] Chip × button removes BOTH the chip AND the parenthesized text from dialogue
- [ ] Right-click chip → "Edit chip" (replaces parenthesized text + chip together)
- [ ] Manual typing of `(new direction)` re-extracts chip
- [ ] Add Beat button (+ at end of beat list)
- [ ] Insert Beat At Position (right-click any beat → "Insert beat after")
- [ ] Delete Beat button (× per beat, with confirm modal "cannot be undone")
- [ ] Reorder beats (drag-drop to reorder within the partition)
- [ ] Group beats functionality (if applicable from prior design)

### Reference uploads
- [ ] Per-beat Character ref slot (1 char ref per beat)
- [ ] Per-beat BG ref slot (1 BG ref per beat)
- [ ] Drag-drop from Library Panel to Char ref slot
- [ ] Drag-drop from Library Panel to BG ref slot
- [ ] Click-to-upload via file picker (image/* filter) on each ref slot
- [ ] Thumbnail preview after upload (≤80px long edge in UI)
- [ ] Right-click thumbnail → "Remove ref"
- [ ] Re-click thumbnail to replace
- [ ] Auto-resize uploads to ≤1280 long-edge (matches Rule 6.2 delivery tier)
- [ ] Server-side magic-byte check rejects non-image
- [ ] Asset registration via `registered_write.py` per LD-421/422 with `iteration_notes`

### 3-option GPT generation (NOT 3×3, NOT 9 stills)
- [ ] "Generate 3 options" button per beat
- [ ] Backend submits 3 `gpt-image-2` calls (LD-440) with varied seed, image-led ~380-char prompt (LD-439) via `build_gpt_still_prompt()` at `beat_generator.py:934-947`
- [ ] 3 thumbnails appear in a row (1×3 layout)
- [ ] Click thumbnail → that option becomes `selected_option_id` (teal border highlight)
- [ ] Other 2 options stay registered in iteration history per LD-421
- [ ] Re-clicking "Generate 3 options" replaces gen_options array (old options remain in Directus)
- [ ] iteration_notes capture Kim's verbatim rejection reason if provided

### Cost display
- [ ] Per-generation cost toast (transient, ~4s after each `/generate` returns)
- [ ] Session running total in header strip (persistent, accumulates)
- [ ] Cost from gpt-image-2 published pricing (typical ~$0.04 × 3 = $0.12 per generation)

### Acceptance
- [ ] Accept All button (validates every beat has `selected_option_id`)
- [ ] Warn modal if any unset (lists beat_ids)
- [ ] Confirm modal: "Lock in N selections and advance pipeline_stage?"
- [ ] On confirm: POST `/api/beat_gen/accept_all` → server advances `pipeline_stage`
- [ ] Activity log row `BEAT_GEN_ACCEPT_ALL` with selection map
- [ ] After acceptance: tab enters "locked" mode (Generate buttons disabled, upload slots disabled)
- [ ] "Re-open for edit" button (decrements pipeline_stage with confirm)

### Integration
- [ ] Cropper invocation from Beat Gen context (modal opens with current beat's ref image)
- [ ] Send beats to Storyboard tab (the partition is shared — nothing to "send", just the Storyboard tab reads same data)
- [ ] Respect TargetVideoSelector — works on intro / resolution / standalone partition

---

## TAB 2: Cropper

- [ ] Cropper canvas (real implementation; currently 1×1 placeholder PNG)
- [ ] Standalone tab access (image library management)
- [ ] Modal mode invokable from Beat Generator (opens with specific beat's ref image)
- [ ] Drag-drop from Library Panel to cropper canvas
- [ ] Pan / zoom on cropper canvas
- [ ] Crop region selection
- [ ] Save crop via `cr_save_crop` backend
- [ ] Enforce shortest-side ≥600px per Rule 6
- [ ] Asset registration via `registered_write.py` (delivery WebP per Rule 6.2)
- [ ] Reset / cancel crop
- [ ] Keyboard shortcuts (if applicable)

---

## TAB 3: Storyboard

### Multi-beat list rendering
- [ ] Read beats from `state.videos[activeTargetVideo].beats` (CURRENTLY BROKEN — reads `state.beats`)
- [ ] Beat cards in `display_order`
- [ ] Per-beat thumbnail
- [ ] Per-beat dialogue display + edit
- [ ] [pause] marker insertion helper in dialogue editor
- [ ] contenteditable text with persistence
- [ ] Hide entire beat list when phase_a/phase_b active (with new architecture they're top-level — Storyboard only renders for intro/resolution/standalone)

### Per-beat actions (currently MISSING in v59 client; backend exists)
- [ ] Regenerate Audio button per beat (calls existing endpoint)
- [ ] Use as Final button per beat
- [ ] Preview Beat button per beat
- [ ] Send for Lipsync button per beat
- [ ] Send for Animation button per beat
- [ ] Assign Image button (wire `endpoints.ts` dead `assign_image` declaration)
- [ ] Inject Image button (wire `endpoints.ts` dead `inject_image` declaration)
- [ ] Drag-drop from Library Panel to per-beat image holder

### Magic compositing (already wired per LD-468/469)
- [ ] "Add magic on still" button per beat (conditional: shows when beat.magic_still_path is empty AND there's a still)
- [ ] "Add magic on video" button per beat (conditional: shows when beat.magic_video_path is empty AND there's a video)
- [ ] Path picker integration via path_picker.html (click-to-place pixel-exact)

### Export
- [ ] "Send Out as MP4" button: finalize beats → normalize per LD-284 → ffmpeg concat → register → write `completed_mp4_path` to partition
- [ ] Re-send creates new concat MP4 (registered as new prod_asset row); source beats preserved per LD-421

---

## TAB 4: Phase B (top-level, Cedric lipsynced video)

### Script + audio
- [ ] Phase B script textarea (persists to `state.phase_b.phase_b_script`)
- [ ] Suggest Script button (reads arc skeleton + therapeutic context)
- [ ] Voice resolves live from Directus `prod_voice_profiles` id=1 (Cedric, stability 0.70, speed 0.50) — READ-ONLY at UI per LD-463
- [ ] Voice stem upload UI (manual override; currently missing)
- [ ] Regenerate Audio button (Cedric TTS)

### Video pipeline (Phase B IS Cedric lipsynced — confirmed 2026-05-03)
- [ ] Cedric base clip dropdown (`placeholder_cedric_base_clip_v1`, etc.)
- [ ] Send for Lipsync button (KEEP — Phase B IS lipsynced per LD-149/196/348)
- [ ] Mix Audio button
- [ ] Export to Stitcher button
- [ ] Lipsync video player (preview)

### Watercolor overlays
- [ ] Watercolor library (5 watercolors per current Event 1)
- [ ] Drag-drop watercolor from library onto Phase B timeline
- [ ] Drop-position translates to `timestamp_ms` in `phase_b_watercolor_cues_json`
- [ ] Cue popover: animation type / duration / Delete (per LD-472)
- [ ] **"Animate this" button per watercolor → opens path_picker.html in `watercolor_animate` mode (LD-464)**
- [ ] Watercolor cue tile rendering = brown border + cream mat + white interior + centered art (LD-203)
- [ ] Watercolor placement bbox: Phase B LEFT 600x540 (frame_x=40) per LD-331

### **Watercolor Animate end-to-end verification (NEW — added 2026-05-03 per Kim)**

The "Animate this" workflow has TWO inputs the user provides:
1. **WHERE:** A drawn path on the HTML canvas (geometry of motion)
2. **WHAT-KIND:** A text description in the textarea ("moving up and down on either side", "trembling in place", "spiraling outward")

Per LD-470, both feed Claude API which generates an ffmpeg `filter_complex` (with safety gate) → magic_compositor renders procedurally → animated watercolor video → composited onto Phase A or Phase B at the placement bbox.

**End-to-end verification gates (must pass for the workflow to work as designed):**

- [ ] `path_picker.html` line 214 textarea exists (verified ✅)
- [ ] `path_picker.html` line 316 helper text says "Draw the WHERE; describe the WHAT-KIND in the box above" (verified ✅)
- [ ] `path_picker.html` submit handler POST body includes textarea content as a named field (e.g., `intent_description`)
- [ ] `/api/watercolor/animate` server handler accepts `intent_description` and passes it into the Claude API prompt
- [ ] Claude API prompt template explicitly instructs Claude to use BOTH the drawn path geometry AND the intent description when generating the ffmpeg `filter_complex`
- [ ] **Smoke test 1:** Draw a wavy line + type "moving up and down on either side" → resulting video shows the watercolor doing exactly that motion (not generic motion that ignores either input)
- [ ] **Smoke test 2:** Same drawn line + different text "trembling in place" → animation differs meaningfully per text description
- [ ] **Smoke test 3:** Different drawn line + same text → animation reflects the new path while preserving the text-described motion style
- [ ] **Risk check:** If smoke tests show identical animations regardless of text, the textarea content is being silently dropped between client and server (or Claude is ignoring it). Treat as release-blocker for Phase A/B feature parity session.

### Audio waveform
- [ ] WaveSurfer.js v7 waveform display (LD-472)
- [ ] WaveSurfer ws.load(audio_url) is source of truth (LD-330) — never bind to `<video>`
- [ ] Click-to-seek on waveform
- [ ] Cue markers visible on waveform
- [ ] WaveSurfer not in package.json — needs add

### Ambient + presets
- [ ] Ambient preset selector inside Phase B producer (currently only in Stitcher)

---

## TAB 5: Phase A (top-level, Chipper lipsynced video with fly-in/fly-out)

### Script + audio
- [ ] Phase A script textarea (persists to `state.phase_a.phase_a_script`)
- [ ] Suggest Script button (reads Phase B + module context)
- [ ] Voice resolves live from Directus `prod_voice_profiles` id=2 (Chipper, stability 0.20, similarity 0.75, style 0.55, eleven_v3) — voice sliders REMOVED per LD-462
- [ ] Voice stem upload UI (manual override; currently missing)
- [ ] Regenerate Audio button (Chipper TTS)

### Video pipeline (3-clip handling — currently only handles ONE clip; this is a real bug)
- [ ] Fly-in clip dropdown (standardized fly-in asset)
- [ ] Sitting (Chipper-on-empty-desk) clip dropdown — `chipper_idle_on_empty_desk_v2` etc.
- [ ] Fly-out clip dropdown (standardized fly-out asset)
- [ ] Send for Lipsync button (lipsyncs the SITTING clip per LD-375)
- [ ] Mix Audio (auto-stitch) button — auto-fires the 5-stage Phase A canonical pipeline (LD-375)
- [ ] Export to Stitcher button (sends `phase_a_stitched_file` per LD-462 rename from `phase_a_canonical_file`)
- [ ] Lipsync video player (preview)
- [ ] Phase A xfade recipe per LD-376: fade_in 0.5s + fadeblack 2.5s

### Watercolor overlays (same WHERE+WHAT-KIND verification as Phase B)
- [ ] Watercolor library (same 5 watercolors)
- [ ] Drag-drop watercolor from library onto Phase A timeline
- [ ] Drop-position → `timestamp_ms` in `phase_a_watercolor_cues_json`
- [ ] Cue popover: animation type / duration / Delete
- [ ] **"Animate this" button per watercolor → opens path_picker.html in watercolor_animate mode (LD-464)**
- [ ] **All 9 watercolor animate end-to-end verification gates from §Phase B watercolor section** (textarea POST body, intent_description in Claude API prompt, 3 smoke tests, etc.) — apply identically to Phase A
- [ ] Watercolor placement bbox: Phase A RIGHT 480x540 (frame_x=800) per LD-331

### Audio waveform
- [ ] WaveSurfer waveform (same as Phase B)
- [ ] Click-to-seek
- [ ] Cue markers visible

### Ambient + presets
- [ ] Ambient preset selector inside Phase A producer

---

## TAB 6: Stitcher

### Module mode (event scope)
- [ ] 4-slot strip in fixed order: intro → Phase A → Phase B → resolution
- [ ] Each slot reads from corresponding `completed_mp4_path` + `state.phase_a.phase_a_stitched_file` + `state.phase_b.phase_b_lipsync_file`
- [ ] Per-slot Ambient bed dropdown (LD-466 `ambient_bed_per_segment`) — already exists
- [ ] Per-slot SFX cue placement UI (CURRENTLY MISSING; backend at `/api/timeline/cues` exists)
- [ ] Per-slot Transitions UI (CURRENTLY MISSING; backend builds trans_slot cues)
- [ ] Per-slot Trims UI (CURRENTLY MISSING; needs backend extension)
- [ ] Per-slot Loudnorm toggle (LD-471)
- [ ] Per-slot Preview button (`_handle_stitch_preview`)
- [ ] Per-slot Bake button (`_handle_stitch_bake`)
- [ ] Final module Bake (assembles module MP4 via ffmpeg concat + LD-284 normalization)
- [ ] Module-level `pause_after_ms` wiring (already in v3 via /api/scene/assemble)

### Standalone mode (milestone scope)
- [ ] 1-slot strip (per LD-423 Universal Stitch Editor's N-slot variable mode)
- [ ] Direct export (no module assembly)
- [ ] Auto-detect mode from `activeProjectType` signal

### Sound Library tier filter
- [ ] Tier filter dropdown: ambient / sfx / transitions / images / watercolors
- [ ] LibraryPanel currently only shows image tiers — needs tier extension

### Port from /stitch_editor (LD-423)
- [ ] Audit standalone /stitch_editor for any features missing in v59 Stitcher tab
- [ ] Port SFX placement UI
- [ ] Port transition UI
- [ ] Port per-slot trim sliders
- [ ] Port inter-slot fade controls
- [ ] After parity validated, retire standalone /stitch_editor

---

## CROSS-CUTTING

### Project / Scope selection
- [ ] ProjectSelector (renamed from EventSelector) — extends to list events + milestones
- [ ] Lists events with current-event indicator
- [ ] Lists milestones in separate optgroup
- [ ] "+ New Event" option
- [ ] "+ New Milestone" option (creates `Production/Milestones/<id>/state.json`)
- [ ] Routes to `/api/event/load` or `/api/milestones/load`
- [ ] Updates URL with `?event=<id>` OR `?milestone=<id>`
- [ ] Phase A/B/Stitcher tabs DISABLED when milestone scope active
- [ ] Beat Generator + Storyboard tabs operational in milestone scope (target = standalone)

### Target Video selection
- [ ] TargetVideoSelector (renamed from VideoSelector) in header
- [ ] Dropdown options: intro / resolution (NOT phase_a, phase_b)
- [ ] HIDDEN when milestone scope active
- [ ] Affects Beat Generator + Storyboard tabs ONLY
- [ ] Defaults to `intro` on event load
- [ ] No confirm prompt on switch (Q1=A from earlier judgment call)

### Mutation channel
- [ ] `pathappPatch(scope, field, value)` auto-injects `scope_target_video` for Beat Gen + Storyboard mutations
- [ ] Skips auto-injection for Phase A/B/Stitcher (they don't need it)
- [ ] Auto-inject `scope_milestone_id` when milestone scope active

### Library Panel (right sidebar)
- [ ] LibraryPanel has draggable items (CURRENTLY zero draggable attrs)
- [ ] onDragStart handlers on every library item
- [ ] Drop zones on: storyboard image holders, Beat Gen ref slots, Cropper canvas, Phase A/B watercolor timelines
- [ ] Tier filter: images / ambient / sfx / transitions / watercolors
- [ ] Search/filter library items
- [ ] Library item preview (hover or click)

### Shared UI primitives (CURRENTLY MISSING)
- [ ] Modal component (confirm dialogs)
- [ ] Toast component (success/error notifications, cost display)
- [ ] Spinner component (async operation indicator)
- [ ] These should be extracted before feature work to avoid per-tab reinvention

### Asset findability (LD-421/422)
- [ ] All ref uploads via `registered_write.py` → `prod_assets` row
- [ ] All generated stills via `registered_write.py`
- [ ] All Phase A/B mp4 outputs via `registered_write.py`
- [ ] Iteration_notes captured at production-time
- [ ] `parent_asset_id` linkage: refs as parents for gen options; sources as parents for concat MP4
- [ ] `find_asset.py` query support for "find me X" requests
- [ ] HTML preview pages in Safari for previews (NOT file:// links per `feedback_file_links.md`)

### Production Map data
- [ ] Bulk-load `prod_modules` Directus collection from `GAMEPLAY_SCOPE_v3.md` (currently only 6 modules; need all 59 V1)
- [ ] Production Map renders all 10 arcs × ~6 modules
- [ ] Per-module per-segment status matrix (segments per LD-465: intro / phase_a / phase_b / resolution / final_concat)

### Magic compositor / visible magic
- [ ] "Add magic on still" workflow (LD-468) — already wired in StoryboardTab
- [ ] "Add magic on video" workflow (LD-469) — already wired in StoryboardTab
- [ ] **"Animate this" watercolor procedural rendering (LD-470 / LD-464) — see Watercolor Animate end-to-end verification gates under Phase A and Phase B sections**
- [ ] path_picker.html integration (click-to-place pixel-exact)
- [ ] Magic SFX placement (separate concern from visible magic — goes in Stitcher tab)
- [ ] Cross-platform compositor wiring (Mac/Windows) — separate tooling concern, NOT in scope for v59 client features

### Voice production
- [ ] Voice profile management UI (LD-462 Phase A panel)
- [ ] Read-only voice display (Cedric for Phase B) with Directus link for adjustment per LD-463
- [ ] Voice stem upload UI for manual override

### Backend endpoints to wire (already exist; UI just needs to call them)
- [ ] `/api/timeline/cues` — SFX cue placement
- [ ] `cr_save_crop` — Cropper save
- [ ] `assign_image` — Storyboard per-beat image assignment (dead declaration in endpoints.ts)
- [ ] `inject_image` — Storyboard per-beat image inject (dead declaration in endpoints.ts)
- [ ] `regenerate_audio` per beat
- [ ] `use_as_final` per beat
- [ ] `preview_beat` per beat
- [ ] `send_for_lipsync` per beat (Storyboard) AND for Phase A/B
- [ ] `send_for_animation` per beat
- [ ] `/api/phase/suggest_script` (already exists per S5.5b)
- [ ] `/api/watercolor/animate` (verify intent_description is consumed correctly)
- [ ] `/api/beat_gen/upload_ref`, `/generate`, `/select_option`, `/add_beat`, `/delete_beat`, `/accept_all` (S5.5c spec)

### Backend endpoints that need to be NEW
- [ ] `/api/milestones/list`, `/api/milestones/create`, `/api/milestones/load`
- [ ] `/api/project/list` (combined events + milestones for ProjectSelector)
- [ ] `/api/beat/finalize` (already in v3 spec)
- [ ] `/api/scene/assemble` (already in v3 spec)
- [ ] `/api/timeline/cues/*` for SFX/transitions if Stitcher tab adds new cue types
- [ ] Per-slot trim endpoint (likely needs new endpoint extension)

### State shape (post-revision; for reference)
- `state.videos.{intro, resolution}` — multi-beat partitions (per event)
- `state.videos.standalone` — milestone partition (per milestone)
- `state.phase_a.{...}` — top-level single-clip producer (per event)
- `state.phase_b.{...}` — top-level single-clip producer (per event)
- `Production/Milestones/<id>/state.json` — independent milestones
- Each partition gains `completed_mp4_path` field (for Stitcher slot read)

### Browser smoke gates (run AFTER each session)
- [ ] Load Event_1 → see ProjectSelector + TargetVideoSelector + 6 tabs in production order
- [ ] Switch TargetVideoSelector to "resolution" → tabs update
- [ ] Click each tab → producer panels render correctly
- [ ] Drag-drop library item to each drop zone → renders correctly
- [ ] Click each button → no console errors, expected behavior
- [ ] Switch ProjectSelector to milestone → Phase A/B/Stitcher disable; Beat Gen + Storyboard target standalone
- [ ] Switch back to event → state preserved per-scope
- [ ] **Watercolor animate dual-input smoke (3 tests per Phase A and Phase B)** — see §Phase B watercolor end-to-end verification

---

## Partition into 4 sub-sessions (per `project_v59_features_planning.md`)

| Session | Sections this inventory feeds |
|---|---|
| **S5.5c** | TAB 1 (Beat Generator entire section) + Cropper (TAB 2) + LibraryPanel drag-drop primitives + Modal/Toast/Spinner |
| **S5.5e** | TAB 3 (Storyboard) per-beat actions + ProjectSelector + Production Map data |
| **S5.5f** | TAB 4 (Phase B) + TAB 5 (Phase A) + WaveSurfer + watercolor drag-drop + cue popovers + **Watercolor Animate end-to-end verification (CRITICAL — Kim 2026-05-03)** + voice stem upload + ambient preset selector |
| **S5.5g** | TAB 6 (Stitcher) SFX/transitions/trims port from /stitch_editor + Sound Library tier filter |

---

**End of inventory v1.** Send this to the next tech-spec session as input. Verify CURRENT STATE per item before scoping work into specific session specs.
