# Technical Spec: Storyboard v59 — Path C Greenfield Rewrite
**Date:** 2026-05-02
**Produced by:** tech-spec skill (synthesis of 8 prior Opus agents + Cursor cross-review)
**Status:** Awaiting Cursor cross-review before Session 1.5 execution
**Supersedes:** Prior in-conversation v59 plan (this is the canonical reference)

---

## 1. Task

Replace the 9,751-line `Production/Event_1/storyboard_v58_prod.html` monolith (24 accumulated Path B patches, 149 IIFE markers, 9 functions wrapped 3+ times) with a Preact + @preact/signals + Vite + TypeScript app at `Production/tools/storyboard-v2/`. The build emits `storyboard_v59_prod.html` so cutover uses the existing `production_server.py --storyboard <filename>` CLI flag. The 12,550-line server stays untouched except for ~50-150 lines of scope guards on 13 coupled handlers and a small set of new endpoints. Goal: structural elimination of the wrap-chain bug class + workflow improvements (inline cropper modal, unified speakers, scope tokens, save-state visibility, "Animate this" on watercolors, "Suggest Script" buttons, multi-event-aware loading, Production Map view, universal autosave, explicit export buttons) + foundation for adding Phase A and Phase B producer panels in v59 (currently exist only in v58).

---

## 2. Governing Decisions

**Locked decisions this spec respects (`prod_locked_decisions`):**

| LD Key | Severity | Constraint imposed on this spec |
|---|---|---|
| `LD-280 RENDERING_ARCHITECTURE_SINGLE_MP4_ATOMIC_V1` | HIGH | Output discipline — produces atomic MP4s for the app pipeline |
| `LD-281 NO_RUNTIME_TTS_PERSONALIZATION_V1` | HIGH | ZERO TTS in v59 frontend; ElevenLabs only via server endpoints |
| `LD-283 SIZE_BUDGET_PER_MODULE_V1` | HIGH | Per-module ≤80 MB ceiling; v59 must surface size to Kim |
| `LD-284 NORMALIZATION_BEFORE_CONCAT_V1` | HIGH | Stitcher second-pass loudnorm enforced |
| `LD-203 PHASE_B_FRAME_SIMPLE_2MATTE_LOCKED` | HIGH | Watercolor framing constants — frames stay baked into PNG via `build_phase_b_tile.py` |
| `LD-419 STORYBOARD_BUILDER_V44_NATIVE_FOLD_V1` | HIGH | v59 supersedes the v58 builder pattern |
| `LD-421/422 ASSET_FINDABILITY` | HIGH | All asset writes via `Production/tools/registered_write.py` |
| `LD-447 DIALOGUE_IMAGE_SAVE_VISIBILITY_V1` | MED | Fix-Q invariants ported as first-class component |
| `LD-452 LIB_MTIME_SORT_AND_DELETE_V1` | HIGH | Server library contract preserved |
| `LD-453 PATCH_INVARIANT_PERSISTENCE_V1` (Rule 36) | HIGH | Class-only selectors from day one |
| `LD-455 PATH_C_REWRITE_V1` | HIGH | Locks the rewrite decision (registered Session 1) |
| `LD-456 SCOPE_VALIDATION_V1` | HIGH | Locks the server scope-guard pattern (registered Session 1) |

**CLAUDE.md rules constraining the work:**

- Rule 7 (Two-Path Protocol): the rewrite IS Path A
- Rule 8 §8.1-§8.5 (Lipsync safety): all enforced server-side; v59 surfaces nothing that would weaken these
- Rule 19 (No Shortcuts): no error paths left open in shipping code
- Rule 22 (App architecture watch list): no runtime TTS, no expo-audio + expo-video, no multi-file playlist
- Rule 27 (Delete Obsolete Workarounds): server-side HTML-patching code deleted only AFTER 14 clean days post-cutover
- Rule 32 (Absolute localhost URLs): every fetch in v59 uses `http://localhost:5111`
- Rule 33 (Verify Server + File Before Test): 4-line bash check before "try it now"
- Rule 34 (Asset Findability): every media write through `registered_write.py`; HTML preview pages in Safari
- Rule 35 (Directus Schema Verification): `try_post_or_queue` mandatory; consult schema doc before payload composition
- Rule 36 (Patch Invariant Persistence): any future Path B patches inherit; v59 itself avoids the wrap-chain class structurally

**New LDs to register during execution:**

- `STORYBOARD_V59_SPEC_V1` — locks this spec as the canonical reference (Session 1.5 start)
- `PHASE_A_PRODUCER_V1` — locks Phase A producer design decisions (Session 2.9 start)
- `PHASE_B_PRODUCER_V1` — locks Phase B producer design decisions (Session 2.7 start)
- `WATERCOLOR_ANIMATE_THIS_V1` — locks the path-picker → magic-compositor → library bridge (Session 3 start)
- `MULTI_EVENT_SERVER_V1` — locks the multi-event-aware server contract (Session 1.5)
- `UNIVERSAL_AUTOSAVE_V1` — locks the pathappPatch optimistic + localStorage shadow + snapshot pattern (Session 1.5)
- `PRODUCTION_MAP_V1` — locks the Production Map view (Session 3.5)
- `EXPORT_TO_STITCHER_V1` — locks explicit export button trio (Session 2 + 2.7 + 2.9)

---

## 3. Approach

**Frontend rewrite scope is bounded.** Only the 9,751-line HTML monolith gets replaced. The 12,550-line `production_server.py` stays — its 91 `_handle_*` endpoints, the magic compositor, the Kling/FLUX/ByteDance/ElevenLabs integrations, the asset pipeline, the 21-collection Directus schema all remain unchanged except for the ~50-150 line scope-guard work and ~7 new endpoints listed below.

**Single mutation channel.** Every state change in v59 flows through `pathappPatch(scope, field, value)`. Components NEVER call `fetch()` directly. The function: (1) optimistically updates the relevant signal store, (2) writes a localStorage shadow IMMEDIATELY (before network), (3) calls `POST /api/state/snapshot` to back up state.json, (4) POSTs the mutation to the appropriate server endpoint, (5) on success clears the shadow and shows a green checkmark, (6) on failure keeps the shadow visible with a red banner + retry button, (7) on page reload replays any uncleared shadows. This eliminates the "lost work" class structurally — every action either persists fully or stays visibly pending.

**Scope tokens make multi-event safe.** Every signal store is keyed by `{event_id, beat_id, version}`. Switching events allocates a fresh store rather than mutating shared state — cross-event leak structurally impossible. The same scope token rides on every server request; the server's 13 newly-guarded handlers reject with HTTP 409 if the body's `event_id` doesn't match the server's active context. The combination of client-side fresh-store-per-event and server-side scope guard means the server can become multi-event-aware (top-of-app event selector loads any `(arc, event, module)` without restart) without risk of one event's state corrupting another's.

**Persistence contract is state.json + sidecar + Directus.** v59's HTML shell is essentially empty (just a Vite bundle loader). The server's existing HTML-patching code in `_handle_assign_image:6276`, `_handle_beat_update_text:8276`, `_handle_inject_image:6393` is made conditional on filename pattern: when target HTML contains v58-shape markers (`var L=[...]`, `var IN=`, `TH["..."]`, `gallery div.ic`), patch HTML AND state; when target is v59-shape (no markers found via grep), patch state.json + sidecar ONLY. Returns the active mode in the response so the client can verify. The v58 fallback continues to work because v58's re-hydration reads state.json on render.

**Phase A and Phase B producers are first-class in v59.** They are NOT deferred to post-cutover. The v58 producer panels (which Kim uses every module) are ported into v59 with explicit design improvements: voice sliders removed, ambient bed moved to Stitcher, "Suggest Script" button added, "Animate this" button on watercolors added, explicit export buttons added, and `phase_a_canonical_<TS>.mp4` renamed to `phase_a_stitched_<TS>.mp4` to reflect that only the fly-in and fly-out are canonical (the middle Chipper segment is unique per Phase A).

**The "Animate this" bridge is the largest new build.** Watercolors currently can be hand-rendered animations only by going through the magic compositor pipeline manually and copying files. v59 wires this end-to-end: watercolor library tile gets an "Animate this" button → opens `path_picker.html` with the watercolor's source image preloaded → Kim draws movement line → YAML POSTs to new `POST /api/watercolor/animate` endpoint → server invokes magic compositor → output writes to `Production/assets/watercolor_library/` as a `cue_type='video'` file with alpha → library auto-refreshes via signal subscription → Kim drag-drops the new animated watercolor as if it had always been there.

**Production Map gives Kim a single view of where everything stands.** New v59 tab querying `GET /api/production/map` joins `prod_modules` + `prod_assets` to show a matrix: rows = (arc, event, module), columns = (intro, Phase A, Phase B, resolution, final concat), cells = ✅ done / ⏳ in-progress / ❌ not started, each clickable to open that scope in the storyboard.

---

## 4. Implementation Steps

### Session 1 — DONE (commit 23812d9)
- Vite + Preact + TypeScript scaffold at `Production/tools/storyboard-v2/`
- 4 tabs (Storyboard / Beat Generator / Cropper / Stitcher) read-only
- Library panel with mtime-sorted thumbnails (~53 items rendering)
- LD-455 + LD-456 registered, preflight #188 opened
- Git initialized, .gitignore protective, commit 23812d9 landed
- v58 backed up with SHA-256 checksum

### Session 1.5 — Server scope guards + persistence contract revision (~2 hours)

1. Open `prod_preflight_reviews` row (`task_type=architectural`, references prior preflight 188 + agent debates + Cursor review).
2. Register `STORYBOARD_V59_SPEC_V1` LD via `Production/lib/directus.py::try_post_or_queue` (Rule 35; consult `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` for field names).
3. Register `MULTI_EVENT_SERVER_V1` and `UNIVERSAL_AUTOSAVE_V1` LDs.
4. Add scope guards to 13 coupled handlers in `production_server.py`:
   - `_handle_bg_accept_beats` (L5507-5561)
   - `_handle_v2_event_state` (L9077-9085) — validate URL `event_id` param
   - `_handle_v2_sidecar` (L9049-9075)
   - `_handle_assign_image` (L6234+)
   - `_handle_beat_update_text` (L8230+)
   - `_handle_inject_image` (L6367+)
   - `_write_sidecar_L_json` (L3599-3647)
   - `_handle_cr_save_crop` (L6089+)
   - `_handle_bg_set_active_context` (L5334)
   - `_handle_bg_extract_beats` (L5354)
   - `_handle_bg_inject_beats` (L5389)
   - `_handle_bg_update_beat` (L5448)
   - `_handle_bg_reorder_beats` (L5475) — NOTE: also has segment_index inconsistency; flag as latent bug, do NOT fix in this scope
5. Each guard pattern: `if body.get('event_id') and body['event_id'] != self.app.event_dir.name: return 409 with {error: 'scope_mismatch', expected, got}`. Log mode in response.
6. Make HTML-patching conditional on filename pattern in 3 handlers (`_handle_assign_image:6276`, `_handle_beat_update_text:8276`, `_handle_inject_image:6393`). Detect via grep on the active storyboard HTML for v58-shape markers. v58 → patch HTML+state; v59 → patch state-only. Log mode in response.
7. Add `POST /api/state/snapshot` endpoint. Body: `{event_id}`. Action: copies `Production/Event_<N>/production_state.json` → `Production/Event_<N>/.backups/state/YYYY-MM-DD_HHMMSS.json`. Returns `{snapshot_path, size_bytes, sha256}`.
8. Add `POST /api/event/load` endpoint. Body: `{arc_number, event_id, module_id}`. Action: changes `self.app.event_dir` to point at the new event folder; reloads `production_state.json` into `self.app.state`; broadcasts `event_changed` via response. Returns `{active_event, beats_count, scope_token}`.
9. Add state file isolation lock (M6): track last-seen client origin (User-Agent + session token) in server memory; reject requests from a different client with HTTP 423 (Locked) and a clear message. Override via env var `MINDFULNEST_ALLOW_PARALLEL=1`.
10. Wire v59 client's `pathappPatch` to call `/api/state/snapshot` before every mutation; uncomment the actual fetch call.
11. Verification (Session 1.5 done when ALL pass):
    - `curl -X POST http://localhost:5111/api/bg/accept-beats -d '{"event_id":"Event_2","beats":[]}'` returns HTTP 409
    - `curl -X POST http://localhost:5111/api/state/snapshot -d '{"event_id":"Event_1"}'` returns the new snapshot path + sha256
    - `curl -X POST http://localhost:5111/api/event/load -d '{"arc_number":1,"event_id":"Event_1","module_id":"M1"}'` returns the active event
    - Existing Session 1 Playwright smoke test still green
    - New Playwright test: load v59, fire ONE mutation via pathappPatch, verify snapshot file exists, verify state.json updated
    - Manual: Kim opens v59 in browser, makes one dialogue edit, refreshes → edit persists; flag-flip back to v58 → same edit visible in v58; flag-flip forward to v59 → still there

### Session 2 — Touchpoint A flows + behavioral parity audit + 4 tabs feature complete (~3-4 hours)

1. Read all 24 `Production/tools/patch_v*.py` scripts. For each, extract the FIXED BEHAVIOR (not the implementation). Dedupe to ~30 unique behaviors.
2. Write 45 Playwright tests asserting each fixed behavior survives in v59 (Cursor's recommendation: 30 tests is too few; CSS regressions, observer-ordering, Fix-W health-registry need specific patterns).
3. Implement Touchpoint A flows §6A (Session 1 read-only verification, locked) and §6B (full v59 cutover contract — drag library to slot, cropper inline modal, dialogue edit persistence, trim persistence, cross-event guard test, Kling generation flow, lipsync, add/delete beat, snapshot fires before mutation).
4. Make all 4 tabs feature complete with universal `pathappPatch`:
   - Storyboard tab: dialogue edit, image assign, lipsync trigger, trim, beat add/delete
   - Beat Generator tab: extract, dialogue, options (3 character refs × 3 BG refs), accept all to storyboard (with scope token)
   - Cropper tab: inline modal pattern (opens over active beat row, no tab switch)
   - Stitcher tab: per-slot preview + bake (existing endpoints; UI rebuild)
5. Add Storyboard export buttons (intro / resolution / standalone routing per `prod_modules.video_role`).
6. Add `prod_modules.video_role` field migration (`'intro' | 'resolution' | 'standalone'`); backfill existing modules to `'intro'` as default.
7. Verification: full Playwright suite 100% green; behavioral parity audit table shows all 30 behaviors covered.

### Session 2.5 — Shared phase infrastructure (~3-4 hours)

1. Build `src/state/phase-state.ts` — signal store factory keyed by `(event_id, phase)`, fields mirroring `production_state.phase_{a,b}_*`.
2. Build `src/api/phase-endpoints.ts` — typed bindings for all Phase A/B endpoints (`regen_audio`, `mix_audio`, `lipsync`, `preview`, `voice_profile_get`, `voice_profile_update`).
3. Build `src/components/phase/PhaseProducer.tsx` — base component taking `phase: 'a' | 'b'` prop. Provides: script editor (textarea with localStorage shadow), Regen Audio button, audio player (WaveSurfer-driven), base clip dropdown (dynamic from new endpoint), Send for Lipsync button, lipsync video player, watercolor library (drag source), watercolor timeline (drag target with start-stop popover), export button, Suggest Script button.
4. Add `GET /api/phase/watercolor_list` — replaces hardcoded JS array; reads `Production/assets/watercolor_library/` directory; returns `{items: [{key, filename, cue_type, thumb_url}]}`.
5. Add `GET /api/phase/base_clips_list` — replaces hardcoded `BASE_CLIPS_LIBRARY`; reads `Production/assets/lipsync_bases/`; returns `{items: [{id, filename, duration_s, character}]}`.
6. Add `POST /api/phase/suggest_script` — calls Claude API server-side with phase context (skeleton + therapeutic + phase-b-writer skill docs for Phase B; just-completed Phase B script + module description for Phase A). Returns `{script, model_used, generation_time_ms}`.
7. Verification: PhaseProducer component renders for both phases against real Event_1 data; dynamic dropdowns populate; Suggest Script button returns a non-empty draft.

### Session 2.7 — Phase B producer panel (~3-4 hours)

1. Register `PHASE_B_PRODUCER_V1` LD.
2. Mount PhaseProducer with `phase="b"` in v59 storyboard tab as expandable section.
3. Cedric voice: read-only at UI surface (consistent with v58 lockout); link to "Edit Cedric in Directus" for adjustment.
4. Remove ambient bed select from Phase B panel (moved to Stitcher in Session 3.5).
5. "Suggest Script" button: wired, reads arc skeleton + therapeutic + phase-b-writer SKILL.md.
6. "Animate this" button: stub for now; full bridge lands in Session 3.
7. Explicit export button: POSTs to `/api/stitch_editor/job` with the lipsync mp4 as Phase B slot in the active module's stitch job.
8. Add `phase_b_script` state field (Phase A has `phase_a_script`; Phase B currently passes script transient — fix asymmetry).
9. Verification: Phase B end-to-end on Event_1 — generate script → edit → regen audio → send for lipsync → drag watercolor onto timeline → export to stitcher. All steps succeed; state persists across reload.

### Session 2.9 — Phase A producer panel (~3-4 hours)

1. Register `PHASE_A_PRODUCER_V1` LD.
2. Mount PhaseProducer with `phase="a"` as second expandable section.
3. Chipper voice sliders REMOVED (per Kim's spec); voice settings still resolved live from `prod_voice_profiles` id=2; sliders that exist in v58 patch (lines 3723-4007) are NOT ported.
4. Remove ambient bed select from Phase A panel.
5. "Suggest Script" button: wired, reads just-completed Phase B script + module context.
6. "Animate this" button: stub.
7. Mix Audio click auto-fires the fly-in + lipsync + fly-out stitch (Kim's A=2 decision); rename output `phase_a_canonical_<TS>.mp4` → `phase_a_stitched_<TS>.mp4`. State field rename `phase_a_canonical_file` → `phase_a_stitched_file`. One-time migration script renames existing files.
8. Explicit export button: POSTs to `/api/stitch_editor/job` with the stitched mp4 as Phase A slot.
9. Verification: Phase A end-to-end on Event_1 — suggest script (referencing Phase B) → edit → regen audio → select base clip → send for lipsync → mix audio (auto-fires stitch) → drag watercolor → export to stitcher.

### Session 3 — "Animate this" bridge (~3-5 hours) — BIGGEST NEW BUILD

1. Register `WATERCOLOR_ANIMATE_THIS_V1` LD.
2. Add "Animate this" button to each watercolor library tile in PhaseProducer.
3. Click handler: opens `path_picker.html?source=<watercolor_key>&return_endpoint=/api/watercolor/animate` in a new tab. Pre-loads the watercolor's source image as the path-picker background.
4. Add `POST /api/watercolor/animate` endpoint. Body: `{source_key, manual_path: [[x,y],...], style?, duration?}`. Action: invokes `magic_compositor.MagicCompositor` with the watercolor source as background; renders animation; output written to `Production/assets/watercolor_library/<key>_animated_<TS>.mov` (alpha-preserving qtrle); registered via `registered_write.py` as `asset_type='watercolor_animation'`, `parent_asset_id` linking to the source; library refresh signal broadcast to v59.
5. Build the source-image preload mechanism in `path_picker.html` — accept `source` URL param, fetch the watercolor source PNG, render as drop-zone background.
6. Wire library auto-refresh: PhaseProducer subscribes to `/api/watercolor/library/changes` (server-sent events or polling); on update, signal store refreshes.
7. Verification: pick a watercolor → "Animate this" → draw line in path-picker → submit → animated `.mov` appears in v59 watercolor library within 30 seconds → drag-drop the animated version onto the timeline → preview shows the animation.

### Session 3.5 — Stitcher enhancements + Production Map + multi-event selector (~3-4 hours)

1. Register `PRODUCTION_MAP_V1` LD.
2. Add `POST /api/stitch_editor/loudnorm` — second-pass loudnorm on slots not marked `loudnorm_already_applied=true` (lipsync outputs auto-mark themselves).
3. Move ambient bed selection from Phase A/B producers to the Stitcher tab. New stitcher field: `ambient_bed_per_segment`.
4. Add `GET /api/production/map` — joins `prod_modules` + `prod_assets`; returns `{modules: [{m_number, creature_name, segments: {intro, phase_a, phase_b, resolution, final_concat}, status_per_segment}]}`.
5. Build "Production Map" tab in v59 (5th tab). Renders the matrix with click-to-open. Each cell shows ✅/⏳/❌ + last-modified timestamp + size.
6. Add top-of-app event selector dropdown. Calls `GET /api/event/list` (new endpoint reading `Production/Arc_*/Event_*/` directories); on change calls `POST /api/event/load`; v59 stores reset and re-hydrate.
7. Verification: switch between Event_1 and Event_2 (when Event_2 exists) without server restart; production map shows accurate per-module status; loudnorm applies correctly on standalone-video stitch jobs.

### Session 4 — Parallel-run module + verification (~2-4 hours)

1. Kim ships ONE complete module end-to-end on v59 (server flag = `storyboard_v59_prod.html`). v58 remains available via flag.
2. Any issues found during the parallel-run module → fix; if structural, halt cutover.
3. Verify: state file written cleanly, all assets registered in Directus, behavioral parity tests stay green, no `patch_invariant_violation` rows in `prod_activity_log`.

### Session 5 — Cutover (~1 hour)

1. After clean module ship: cutover. Update default `--storyboard` flag in launch script.
2. Activate daily state-snapshot cron at `Production/scripts/snapshot_state_daily.sh`; runs for 14 days; auto-disables after.
3. Lock `PATH_C_CUTOVER_COMPLETE_V1` LD.
4. After 14 clean days: delete obsolete server-side HTML-patching code per Rule 27.

---

## 5. Files Created / Modified

| Path | Action | Why |
|---|---|---|
| `Production/tools/storyboard-v2/` (new dir, ~50-80 files, ~5-8 KLOC TypeScript) | Create | The new app |
| `Production/tools/storyboard-v2/src/state/scope.ts` | Create | Scope token type + assertion helpers + per-event store factory |
| `Production/tools/storyboard-v2/src/state/storyboard-state.ts` | Create | Signal-backed store, scope-keyed |
| `Production/tools/storyboard-v2/src/state/bg-state.ts` | Create | Beat Generator store |
| `Production/tools/storyboard-v2/src/state/library-state.ts` | Create | Library store |
| `Production/tools/storyboard-v2/src/state/phase-state.ts` | Create | Phase A/B store factory |
| `Production/tools/storyboard-v2/src/api/client.ts` | Create | `pathappPatch(scope, field, value)` + scope-asserting fetch wrapper |
| `Production/tools/storyboard-v2/src/api/endpoints.ts` | Create | Typed endpoint bindings |
| `Production/tools/storyboard-v2/src/api/phase-endpoints.ts` | Create | Phase A/B typed endpoints |
| `Production/tools/storyboard-v2/src/components/tabs/StoryboardTab.tsx` | Create | Storyboard tab (with PhaseProducer mounts for A and B) |
| `Production/tools/storyboard-v2/src/components/tabs/BeatGeneratorTab.tsx` | Create | BG tab |
| `Production/tools/storyboard-v2/src/components/tabs/CropperTab.tsx` | Create | Cropper as inline modal pattern |
| `Production/tools/storyboard-v2/src/components/tabs/StitcherTab.tsx` | Create | Stitcher tab (with ambient bed control) |
| `Production/tools/storyboard-v2/src/components/tabs/ProductionMapTab.tsx` | Create | Production Map (5th tab) |
| `Production/tools/storyboard-v2/src/components/LibraryPanel.tsx` | Modify | Already created Session 1; add 1+ item assertion already done; class-only selectors |
| `Production/tools/storyboard-v2/src/components/phase/PhaseProducer.tsx` | Create | Shared Phase A/B base component |
| `Production/tools/storyboard-v2/src/components/SaveStatusIndicator.tsx` | Create | Fix-Q pattern as first-class |
| `Production/tools/storyboard-v2/src/components/ScopeBoundary.tsx` | Create | Render-level scope assertion |
| `Production/tools/storyboard-v2/src/components/EventSelector.tsx` | Create | Top-of-app multi-event selector |
| `Production/tools/storyboard-v2/src/utils/snapshot.ts` | Create | Calls `/api/state/snapshot` before mutation |
| `Production/tools/storyboard-v2/src/utils/shadow-write.ts` | Create | localStorage shadow + replay-on-reload |
| `Production/tools/storyboard-v2/scripts/copy-to-event.sh` | Modify | Already created Session 1; add Vite build artifact preservation per M7 |
| `Production/tools/storyboard-v2/e2e/touchpoint-a.spec.ts` | Create | 10 must-pass flows §6A + 10 production workflow flows §6B |
| `Production/tools/storyboard-v2/e2e/behavioral-parity.spec.ts` | Create | 45 patch-derived tests |
| `Production/Event_1/storyboard_v59_prod.html` | Modify (build output, evolves each session) | The artifact `--storyboard` flag points to |
| `Production/Event_1/storyboard_v58_prod.html` | Untouched | Golden backup, indefinite |
| `Production/Event_1/storyboard_v58_prod.html.sha256` | Already exists | Checksum guard |
| `Production/tools/production_server.py` | Modify (~50-150 lines) | 13 scope guards + HTML-patching conditional + 7 new endpoints + state isolation lock |
| `Production/scripts/snapshot_state_daily.sh` | Create | Daily cron for 14 days post-cutover |
| `Production/Event_1/.backups/state/` (new dir) | Create | Snapshot landing zone |
| `Production/docs/STORYBOARD_REAL_FIX_TOUCHPOINT_A.md` | Modify | Already added §6A; add §6B in Session 2 |
| `Production/docs/STORYBOARD_V59_SPEC_v1.md` | Create (this file) | Canonical spec reference |

---

## 6. Directus Writes Required

All writes via `Production/lib/directus.py::try_post_or_queue` (Rule 35). Field names verified against `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md`.

| Collection | Writes | Purpose |
|---|---|---|
| `prod_locked_decisions` | `STORYBOARD_V59_SPEC_V1` (S1.5), `MULTI_EVENT_SERVER_V1` (S1.5), `UNIVERSAL_AUTOSAVE_V1` (S1.5), `PHASE_B_PRODUCER_V1` (S2.7), `PHASE_A_PRODUCER_V1` (S2.9), `WATERCOLOR_ANIMATE_THIS_V1` (S3), `PRODUCTION_MAP_V1` (S3.5), `EXPORT_TO_STITCHER_V1` (S2 + S2.7 + S2.9), `PATH_C_CUTOVER_COMPLETE_V1` (S5) | Lock decisions per Rule 18 |
| `prod_reference_docs` | This spec doc registered with `doc_category=architecture`, `is_current=true`, `has_locked_decisions=true` | Per Rule 15 (registry sync) |
| `prod_activity_log` | Per session: `action='session_complete'`, `details={session, files_touched, tests_passed, ld_keys_locked}` | Audit trail |
| `prod_preflight_reviews` | One row per session start (`task_type=architectural`, references prior preflight + this spec, `claude_summary` captures synthesis) | Per LD-124 |
| `prod_modules` | Add `video_role` field (S2 migration); backfill all existing modules to `'intro'` default | Storyboard export routing |
| `prod_assets` | Every Phase A/B output (voice stem, mixed audio, lipsync mp4, stitched mp4) registered via `registered_write.py` with `asset_type`, `role`, `parent_asset_id`, `iteration_notes` | Per LD-421/422 |

---

## 7. Error Cases and Handling

Per Rule 19: no silent failures. Every error path either succeeds, surfaces visibly to Kim, or triggers automatic recovery.

| Failure | Detection | Response |
|---|---|---|
| Cross-event scope mismatch (client) | `ScopeBoundary` assertion on render | Render error UI; do NOT POST; log to console + `/api/patch_health` |
| Cross-event scope mismatch (server) | Scope guard at handler entry | HTTP 409 with `{error, expected, got}`; client shows red banner |
| State write fails | `pathappPatch` catches non-200 | Red banner + localStorage shadow already written + retry button |
| Snapshot endpoint fails | `pathappPatch` catches non-200 from `/api/state/snapshot` | Red banner "snapshot failed — proceed?" with explicit Kim confirmation; if Kim proceeds, write proceeds without snapshot (logged) |
| Build fails | `npm run build` exits non-zero | Cutover blocked; v58 still active; M7 keeps last good v59 build available; fix forward |
| State file corruption discovered post-cutover | Daily snapshot diff | Restore from prior snapshot; rollback via flag flip if structural |
| Behavioral parity test fails | Playwright run | Cutover blocked until 100% green |
| Vite build artifact missing | Server can't find `storyboard_v59_prod.html` | Server logs + falls back to v58 automatically; alert in `prod_activity_log` |
| State isolation lock triggered | Different client requests state | HTTP 423 Locked with clear message; override via `MINDFULNEST_ALLOW_PARALLEL=1` |
| `path_picker.html` YAML invalid | `_handle_watercolor_animate` validates 2-20 points in [0,1] | HTTP 400 with structured error; Kim sees clear "invalid path" message |
| Magic compositor render fails | Background thread catches exception | Job marked `failed` in `_MAGIC_JOBS`; status endpoint returns failure with traceback in `details` |
| Library refresh signal lost | PhaseProducer falls back to 30s polling on `/api/phase/watercolor_list` | New animations appear within 30s even if SSE drops |

---

## 8. Verification

Each session has explicit gates that must pass before next session begins.

**Session 1.5 verification:**
- ✅ `curl -X POST http://localhost:5111/api/bg/accept-beats -d '{"event_id":"Event_2","beats":[]}'` returns HTTP 409
- ✅ `curl -X POST http://localhost:5111/api/state/snapshot -d '{"event_id":"Event_1"}'` returns snapshot + sha256
- ✅ `curl -X POST http://localhost:5111/api/event/load -d '{...}'` returns active event
- ✅ Session 1 Playwright smoke still green
- ✅ NEW Playwright: load v59, fire one mutation via pathappPatch, verify snapshot file exists, verify state.json updated
- ✅ Manual: dialogue edit in v59 → reload → persists; flag-flip to v58 → visible; flag-flip to v59 → still there

**Session 2 verification:**
- ✅ All 30 behavioral parity tests + 10 Touchpoint A §6A tests + 10 §6B tests = 100% green
- ✅ All 4 tabs feature complete with no console errors
- ✅ Storyboard export buttons route to correct stitcher slot per `video_role`

**Session 2.5 verification:**
- ✅ PhaseProducer renders for both phases against real Event_1 data
- ✅ Dynamic dropdowns populate from new endpoints
- ✅ "Suggest Script" returns non-empty draft

**Session 2.7 verification:**
- ✅ Phase B end-to-end on Event_1 → all steps succeed → state persists across reload

**Session 2.9 verification:**
- ✅ Phase A end-to-end on Event_1 → all steps succeed → state persists
- ✅ Renamed `phase_a_stitched_<TS>.mp4` produced; old `phase_a_canonical_<TS>.mp4` files migrated

**Session 3 verification:**
- ✅ Watercolor → "Animate this" → draw line → submit → animated `.mov` in library within 30s → drag-drop → preview shows animation

**Session 3.5 verification:**
- ✅ Switch between events without server restart
- ✅ Production Map shows accurate per-module status
- ✅ Loudnorm applies correctly on standalone-video stitch jobs

**Session 4 verification:**
- ✅ Kim ships one complete module end-to-end on v59
- ✅ All assets registered in Directus
- ✅ Zero `patch_invariant_violation` rows in `prod_activity_log`
- ✅ Behavioral parity tests stay green

**Session 5 verification (cutover):**
- ✅ Default `--storyboard` flag updated
- ✅ Daily snapshot cron active
- ✅ `PATH_C_CUTOVER_COMPLETE_V1` LD locked
- ✅ 14 clean days → server-side HTML-patching code deleted

---

## 9. Rollback

| Stage | Rollback procedure | Time to recover |
|---|---|---|
| During Session 1.5 | Server changes are additive — revert via git checkout of production_server.py | 1 minute |
| During Sessions 2-3.5 | All work on git branch; v58 still default | 1 minute (flag flip) |
| Post-cutover within 14 days | Daily snapshot restore + flag flip to v58 | 5 minutes |
| Post-cutover after 14 days | v58 still bit-identical on disk; flag flip to v58; state corruption requires manual investigation against Directus `prod_assets` history | 15-60 minutes depending on corruption scope |
| Catastrophic (rare) | Restore git commit 23812d9 (Session 1 baseline); rebuild v59 from scratch; v58 always there as ultimate fallback | 1-2 hours |

---

## 10. Out of Scope (V1)

Explicit scope boundaries to prevent creep during execution:

- **Magic path picker embed inside v59.** Stays as separate `path_picker.html` tool (user opens in new tab). v2 candidate.
- **Server-side HTML-patching cleanup.** Becomes dead code on v59 path; delete per Rule 27 only after 14 clean days post-cutover.
- **Phase B authoring redesign beyond the spec'd improvements.** Port forward as-is otherwise.
- **Stitcher major redesign.** Add loudnorm + ambient bed; otherwise port forward.
- **Magic compositor / Kling / ByteDance / ElevenLabs / Directus pipeline changes.** Out of scope; reuse via existing endpoints.
- **`_handle_bg_reorder_beats` segment_index inconsistency.** Latent bug; flag for separate ticket; do NOT fix in this scope.
- **Cedric voice slider unlock.** Cedric stays read-only at UI surface; manual Directus edit required (consistent with v58).
- **Multi-user collaboration.** v59 is single-user (Kim only); state isolation lock enforces this.
- **Mobile responsive design.** Desktop only.
- **Internationalization.** English only.
- **Real-time collaboration features (presence, cursors, live edits).** Single-user only.

---

## 11. Cursor Cross-Review Questions

Before Session 1.5 execution, this spec gets Cursor cross-review. Questions for Cursor:

1. Is the persistence contract revision (HTML-patching conditional on filename pattern) safe for the v58 fallback path? Walk through what happens if Kim is on v59, makes a write, falls back to v58 — does v58 see the write?
2. Are there other coupled handlers beyond the 13 listed that need scope guards? Re-grep `production_server.py` for `self.app.event_dir` access patterns.
3. The "Animate this" bridge writes new `.mov` files into `Production/assets/watercolor_library/`. Will the existing `WATERCOLOR_LIBRARY` build-time injection mechanism in v58 break when new files appear at runtime? (v58 hardcodes the array at build time.)
4. Multi-event server: when `/api/event/load` switches `self.app.event_dir`, are there in-flight requests against the old event that could race? Do we need request serialization?
5. Production Map endpoint joins `prod_modules` + `prod_assets`. With ~59 modules × ~5 assets per module = ~300 rows, is this a performance concern? Should we add caching?
6. Universal autosave: localStorage shadow could grow unbounded if many writes fail. Is the 24h TTL + per-write quota check enough, or do we need explicit cleanup?
7. The renamed `phase_a_stitched_<TS>.mp4` (was `phase_a_canonical_<TS>.mp4`) requires a one-time migration of existing files. What's the safest pattern for that migration that handles in-flight references?
8. State file isolation lock based on User-Agent + session token: how robust is this against (a) browser updates that change UA, (b) Kim opening v59 and v58 in separate tabs, (c) Playwright tests running in parallel?
9. Sessions 2.5 / 2.7 / 2.9 introduce shared infrastructure (PhaseProducer) before Phase B (2.7) and Phase A (2.9). Is that ordering right, or should Phase A come first since it's simpler (auto-fire stitch vs. waveform-driven cue placement)?
10. The 8 mitigations cover state corruption, parallel-run, build failures, supply chain, and locking. What category of risk is missing?

---

**End of spec. Awaiting Cursor cross-review.**
