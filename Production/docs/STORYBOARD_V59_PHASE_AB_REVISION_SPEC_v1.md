# Storyboard v59 — Phase A/B Architecture Revision Spec v1

**Date:** 2026-05-03
**Produced by:** tech-spec skill (two-agent Opus debate + judgment-call gate)
**Classification:** ARCHITECTURAL revision (state shape change + tab restructure + new milestone concept)
**Prior context:** S5.5a1 + S5.5a2 + S5.5b shipped; browser smoke surfaced design gap

---

## §1 Task

Reverse the architectural mistake from S5.5a1/a2 where `phase_a` and `phase_b` were modeled as video-role siblings of `intro`/`win` under a unified `state.videos.{role}` partition. They should have been **separate top-level state** (different KIND of authoring). Browser smoke test on 2026-05-03 confirmed the unification was wrong.

This spec covers:

1. **Reverse migration** — lift `state.videos.phase_a.{...}` and `state.videos.phase_b.{...}` back to top-level `state.phase_a.{...}` / `state.phase_b.{...}` for both events
2. **Server handler reverts** — restore the ~3 sites that read/write `state.videos.phase_a/b` to use top-level reads/writes
3. **Naming alignment** — rename `videos.win` → `videos.resolution` (aligns with LD-412 phase_boundaries V1 valid names)
4. **Tab restructure** — promote Phase A and Phase B to top-level tabs; reorder tabs to match production workflow; restrict Beat Generator + Storyboard to multi-beat targets
5. **Milestone (standalone) concept** — introduce independent multi-beat videos NOT tied to events; stored at `Production/Milestones/<milestone_id>/state.json`
6. **TargetVideoSelector restructure** — rename VideoSelector and restrict to multi-beat targets {intro, resolution}; hidden when authoring milestones
7. **ProjectSelector** — extend EventSelector to also list milestones (or separate selector — see §3.4)
8. **LD amendments** — amend LD-473, LD-474, LD-478; PATCH LD-412; write 5 new LDs

This is a SINGLE-SESSION ATOMIC change (Q3 = A) per Kim's directive 2026-05-03.

---

## §2 Governing Decisions

### Locked decisions this spec respects (must not violate)

| LD | Key | Reason |
|---|---|---|
| LD-280 | RENDERING_ARCHITECTURE_SINGLE_MP4_ATOMIC_V1 | Module ships as ONE atomic MP4; preserves Stitcher 4-slot assembly |
| LD-281 | NO_RUNTIME_TTS_PERSONALIZATION_V1 | All TTS bakes at production time |
| LD-284 | NORMALIZATION_BEFORE_CONCAT_V1 | Per-segment normalization before module concat |
| LD-316 | MODULE_EXIT_AND_PROGRESSION_V1 | Names "Win video" as in-module section (semantically aligned to "resolution") |
| LD-375 | PHASE_A_CANONICAL_PIPELINE_V1_20260421 | 5-stage Phase A canonical pipeline |
| LD-376 | PHASE_A_XFADE_RECIPE_V1_20260421 | Phase A fade_in 0.5s + fadeblack 2.5s |
| LD-330 | PHASE_B_AUTHORING_WAVEFORM_FIRST_RESTORE_V1 | WaveSurfer ws.load(audio_url) source of truth |
| LD-412 | PHASE_BOUNDARIES_NAMED_OBJECT_V1 | Valid V1 names: `intro, phase_a, phase_b, resolution` — drives the win→resolution rename |
| LD-421 / LD-422 | ASSET_FINDABILITY_OVERHAUL_V1 | All media writes via `registered_write.py`; component parts preserved per Kim Q2 directive |
| LD-423 | STITCH_EDITOR_UNIVERSAL_V1 | N-slot variable assembly (1-slot for milestones; 4-slot for module) |
| LD-456 | SCOPE_VALIDATION_V1 | `_assert_event_scope` + HTTP 409 |
| LD-458 | EVENT_LOAD_GENERATION_LOCK_V1 | Atomic event swap |
| LD-459 | UNIVERSAL_AUTOSAVE_V1 | `.L.json` sidecar |
| LD-460 | ASYNC_JOB_GENERATION_PIN_V1 | Pin `pinned_video_role` at job entry |
| LD-461 | SCOPE_BODY_HELPER_V1 | `_scope_body` normalization |
| LD-462 | PHASE_A_PRODUCER_V1 | v59 Phase A producer (will be moved from Storyboard collapsible to its own tab) |
| LD-463 | PHASE_B_PRODUCER_V1 | v59 Phase B producer (same) |
| LD-465 | PRODUCTION_MAP_V1 | Already encodes the conceptual split (segments matrix) |
| LD-466 | EXPORT_TO_STITCHER_V1 | 4-slot order: intro → Phase A → Phase B → resolution |
| LD-467 | MULTI_EVENT_SELECTOR_V1 | Top-of-app selector — extended for milestones |

### Locked decisions this spec amends (existing LDs)

| LD | Key | Amendment |
|---|---|---|
| LD-473 | BG_VIDEO_PARTITION_V1 | Restrict partition to multi-beat roles only (intro, resolution, standalone). Phase_a/phase_b explicitly removed. |
| LD-474 | VIDEO_ROLE_PER_REQUEST_V1 | `_VALID_VIDEO_ROLES` becomes `{intro, resolution, standalone}`. Phase_a/phase_b are NOT video roles. |
| LD-475 | IMAGE_OVERRIDES_CLEAR_ON_EVENT_LOAD_V1 | Clarify: applies only to multi-beat partitions |
| LD-478 | IMAGE_OVERRIDES_NESTED_BY_ROLE_V1 | Restrict nesting to {intro, resolution, standalone} |
| LD-477 | HANDLER_REFACTOR_VIDEOS_PARTITION_V1 | Clarify: handlers refactored for multi-beat partitions; phase_a/b handlers continue to use top-level |
| LD-481 | VIDEO_SET_ACTIVE_ENDPOINT_V1 | `state.active_video` enum restricted to multi-beat roles |
| LD-482 | VIDEO_CREATE_ENDPOINT_V1 | Valid roles for `_handle_video_create` restricted to {intro, resolution, standalone} |
| LD-412 | PHASE_BOUNDARIES_NAMED_OBJECT_V1 | Confirm "resolution" naming aligns; if `videos.win` was ever surfaced to upload_module.py, fix |

### New LDs this spec writes

| Key | Severity | Purpose |
|---|---|---|
| PHASE_A_TOP_LEVEL_STATE_V1 | HIGH | Phase A state lives at `state.phase_a.{...}` (top-level), NOT under `state.videos`. Phase A is single-clip producer, not multi-beat sequence. |
| PHASE_B_TOP_LEVEL_STATE_V1 | HIGH | Same for Phase B. |
| MILESTONE_STANDALONE_INDEPENDENT_V1 | HIGH | Milestone videos are independent of events; stored at `Production/Milestones/<milestone_id>/state.json`. Authored via Beat Generator + Cropper + Storyboard; exported via Stitcher 1-slot mode. |
| TARGET_VIDEO_SELECTOR_V1 | MEDIUM | Header dropdown {intro, resolution} (was VideoSelector). Affects Beat Generator + Storyboard ONLY. Hidden when milestone selected. |
| TAB_STRUCTURE_PRODUCTION_ORDER_V1 | MEDIUM | Tab order matches production workflow: Beat Generator → Cropper → Storyboard → Phase B → Phase A → Stitcher. Phase A and Phase B are top-level tabs (not collapsibles inside Storyboard). |
| WIN_RENAMED_RESOLUTION_V1 | MEDIUM | The `videos.win` partition is renamed `videos.resolution` to align with LD-412 phase_boundaries V1 valid names. UI label may say "Resolution" or "Win" — internal key is `resolution`. |

---

## §3 Approach

### §3.1 State shape (corrected architecture)

```jsonc
// Per-event state (Production/Event_<N>/production_state.json):
{
  "event_id": "M1E1",
  "version": "v3",  // bumped from v2 (this revision)
  "active_video": "intro",  // {intro, resolution} — display hint only per LD-474
  "_module_version": 240,
  "module_sfx_cues": [...],
  "fade_between_beats_ms": 0,
  "latest_preview_stitched_path": "...",
  "full_module_segment_boundaries": [...],

  // Multi-beat sequences (Beat Gen + Storyboard target these):
  "videos": {
    "intro": { "video_role": "intro", "video_label": null,
               "beats": {...}, "image_overrides": {...},
               "display_order": [...], "completed_mp4_path": "..." },
    "resolution": { "video_role": "resolution", "video_label": null,
                    "beats": {...}, "image_overrides": {...},
                    "display_order": [...], "completed_mp4_path": "..." }
  },

  // Single-clip producers (TOP LEVEL, separate top-level state):
  "phase_a": {
    "phase_a_script": "...",
    "phase_a_voice_stem_file": "...",
    "phase_a_voice_stem_mtime": 0,
    "phase_a_lipsync_file": "...",
    "phase_a_lipsync_mtime": 0,
    "phase_a_empty_desk_bg_id": "...",
    "phase_a_mixed_audio_file": "...",
    "phase_a_mixed_audio_mtime": 0,
    "phase_a_ambient_preset_id": "...",
    "phase_a_watercolor_cues_json": "[]",
    "phase_a_stitched_file": "...",
    "phase_a_stitched_mtime": 0,
    "phase_a_status": "draft"
  },
  "phase_b": {
    "phase_b_script": "...",
    "phase_b_voice_stem_file": "...",
    "phase_b_lipsync_file": "...",
    "phase_b_lipsync_mtime": 0,
    "phase_b_status": "draft",
    "phase_b_watercolor_cues_json": "[]",
    "phase_b_ambient_preset_id": "...",
    "phase_b_cedric_base_clip_id": "..."
  }
}

// Standalone milestone state (Production/Milestones/<milestone_id>/state.json):
{
  "milestone_id": "magic_intro_video",
  "milestone_label": "Magic Intro Video",
  "version": "v3",
  "created_at": "2026-05-03T...",
  "updated_at": "2026-05-03T...",
  "videos": {
    "standalone": {
      "video_role": "standalone",
      "video_label": null,
      "beats": {...},
      "image_overrides": {...},
      "display_order": [...],
      "completed_mp4_path": "..."
    }
  }
}
```

**Key shape rules:**
- `state.phase_a` and `state.phase_b` keep their `phase_X_` field-name prefixes (preserved from migration; no rename)
- `state.videos` partition contains ONLY `{intro, resolution, standalone}` — never `phase_a`/`phase_b`
- `state.active_video` is restricted to multi-beat roles
- Milestones are NOT in event state.json files; they live in their own `Production/Milestones/<milestone_id>/state.json` files
- Milestone state.json has NO `event_id` field (replaced by `milestone_id`)
- Each multi-beat partition gains a `completed_mp4_path` field — the Storyboard tab's "Send Out" action writes the path here; Stitcher reads from it (Q2 = A semantics)

### §3.2 Tab structure (production workflow order)

```
[Beat Generator]  [Cropper]  [Storyboard]  [Phase B]  [Phase A]  [Stitcher]
       ↑              ↑            ↑           ↑           ↑           ↑
       └─── reusable for ──────────┘           └─ standalone ─┘     Module
       intro / resolution / standalone         (one event)         assembly
       (driven by TargetVideoSelector)         (independent)
```

| Tab | Role | State path | TargetVideoSelector affects? |
|---|---|---|---|
| Beat Generator | Multi-beat authoring (3-option GPT grid + per-beat ref slots + dialogue editor) | `videos.<target>.beats` | YES |
| Cropper | Image crop tool; standalone access + invokable from Beat Gen modal | image library / asset paths | NO |
| Storyboard | Multi-beat sequence editor + "Send Out as MP4" action | `videos.<target>.{beats, image_overrides, display_order}` | YES |
| Phase B | Single-clip Cedric meditation video producer | `state.phase_b.{...}` (top-level) | NO (always Phase B) |
| Phase A | Single-clip Chipper demo video producer (with fly-in/fly-out) | `state.phase_a.{...}` (top-level) | NO (always Phase A) |
| Stitcher | 4-slot module mode + 1-slot standalone mode | reads completed_mp4_paths | NO |

### §3.3 TargetVideoSelector (renamed from VideoSelector)

- Header dropdown: `Target: [intro] [resolution]`
- When event scope is active: dropdown shows {intro, resolution}
- When milestone scope is active: dropdown HIDDEN (milestones are always standalone, only one role applies)
- Affects only Beat Generator + Storyboard tabs (other tabs ignore it)
- No confirm prompt on switch (Q1 = A) — partition data auto-saved, switches reversible

### §3.4 ProjectSelector (extends EventSelector)

Replace the existing EventSelector dropdown with a unified ProjectSelector listing both events AND milestones:

```
Project: [Event_1 (current)] ▼
  ── Events ──
  ✓ Event_1
    Event_2
    + New Event
  ── Milestones ──
    Milestone: magic_intro_video
    Milestone: stone_celebration_v1
    + New Milestone
```

When an Event is selected: TargetVideoSelector shows {intro, resolution}; Phase A/Phase B/Stitcher tabs operational
When a Milestone is selected: TargetVideoSelector hidden; Phase A/Phase B tabs disabled (no phase data for milestones); Stitcher operates in 1-slot standalone mode

### §3.5 "Send Out as MP4" semantics (Q2 = A with preservation)

When Kim hits "Send Out as MP4" in Storyboard tab for the active target:

1. Per LD-139 STITCH_ARCHITECTURE: finalize each beat (`/api/beat/finalize`) → `beat_NN_final.mp4` cached via `finalize_args_hash`
2. Per LD-284 NORMALIZATION: re-encode each finalized beat to canonical codec spec (H.264 High / yuv420p / 1280×720 / 24fps / AAC 128kbps mono 44.1kHz / +faststart)
3. ffmpeg concat demuxer assembles into one MP4 via `/api/scene/assemble`
4. Register the output via `registered_write.py` per LD-421/422 with `iteration_notes` capturing the beats that composed it
5. Write the path to `state.videos.<target>.completed_mp4_path`
6. Stitcher slot for that role reads the path and uses the MP4

**Component preservation (Q2 addendum):** Each individual beat MP4 is ALREADY registered separately in `prod_assets` via the per-beat finalize step. Source beats remain editable in `state.videos.<target>.beats`. Sending out creates a NEW concat MP4 derived from the source beats — it does NOT destroy the source. Re-sending produces a new concat MP4 (registered as new prod_asset row); old concats stay queryable via `find_asset.py` for audit/diff purposes.

### §3.6 Stitcher modes

Two modes, one tab:

**Module mode (4-slot, when Event scope active):**
- 4 slots in fixed order: intro → Phase A → Phase B → resolution
- Each slot reads from corresponding completed_mp4_path
- Per-slot ambient_bed selection (per LD-466)
- Bake → final module MP4 via ffmpeg concat with normalization

**Standalone mode (1-slot, when Milestone scope active):**
- 1 slot: standalone milestone MP4
- Direct export (no module assembly)
- Per LD-423 Universal Stitch Editor's N-slot variable mode (1 = N here)

Stitcher tab UI auto-detects mode from the active scope.

---

## §4 Implementation Phases (atomic single-session per Q3 = A)

### Phase A — Pre-flight + reverse migration script (read-only / dry-run only)

A1. Read current state.json files for both events; capture exact pre-state shape (phase_a/phase_b fields under `videos.{}`)
A2. Write `Production/scripts/migrate_phase_partitions_to_top_level.py` — reverse migration script:
   - For each event state.json: if `videos.phase_a` exists, lift each field to top-level `state.{...}`; assert no key collisions; delete `videos.phase_a`
   - Same for `videos.phase_b`
   - Rename `videos.win` → `videos.resolution`
   - Bump `version` from `v2` → `v3`
   - Snapshot to `Production/Event_<N>/.backups/state/<TS>_pre_phase_revision.json` before write
   - Modes: `--dry-run`, `--apply`, `--validate`
   - Idempotency check: returns "already migrated" if `version=v3` AND no `videos.phase_a`/`phase_b` AND `videos.resolution` (not `videos.win`) present
   - Fail-closed on partial migration (some events at v2, some at v3)
A3. Run script in `--dry-run` mode against both events; verify output shows expected lift + rename
A4. Synthesize a fake half-migrated state file; verify fail-closed behavior

### Phase B — Server handler reverts + new endpoints

B1. Stop server (`pkill -f production_server.py`)
B2. Revert `production_server.py` sites that read/write `videos.phase_a`/`videos.phase_b`:
   - Line 6416-6418 (`_handle_phase_suggest_script`): revert phase_b read to top-level `state.get("phase_b_script")`
   - Line 14401 (canonical-stitch helper): revert to `state.get("phase_a_ambient_preset_id")`
   - Line 14517-14523 (canonical-stitch helper): revert write to top-level `state["phase_a_stitched_file"]` + `state["phase_a_stitched_mtime"]`
   - Audit any other phase_a/phase_b reads/writes via grep; revert all
B3. Update `_VALID_VIDEO_ROLES` (line ~1180): `{intro, resolution, standalone}` (remove `phase_a, phase_b, win`; rename `win` → `resolution`)
B4. Update `validate_video_role()` accordingly
B5. Update migration script for any future events — refuse to lift `phase_a_*` / `phase_b_*` fields under `videos.{}`
B6. Add new endpoints:
   - `GET /api/milestones/list` — returns `[{milestone_id, milestone_label, beat_count, completed_mp4_path}]`
   - `POST /api/milestones/create` — body `{milestone_id, milestone_label}`; creates `Production/Milestones/<milestone_id>/` dir + state.json scaffold
   - `POST /api/milestones/load` — body `{milestone_id}`; switches active scope to milestone (atomic swap per LD-458 pattern)
   - `GET /api/project/list` — returns `{events: [...], milestones: [...]}` for the new ProjectSelector dropdown
B7. Update `_handle_event_load` and equivalent milestone-load handler to use the same `event_load_lock` pattern; cache invalidation per LD-475
B8. Update `_handle_export` (Storyboard tab "Send Out as MP4"):
   - Per §3.5: finalize beats → normalize → concat → register → write `completed_mp4_path` to partition
   - Idempotent: re-running creates new MP4, registers new prod_asset row, updates path
B9. Update `_handle_video_set_active`: `_VALID_VIDEO_ROLES` change cascades; reject `phase_a`/`phase_b`/`win` with 400 + clear error
B10. Update `_handle_video_create`: same role validation
B11. Update `state.create_video()` and `state.validate_video_role()` helpers
B12. py_compile clean
B13. Restart server; `/api/health` 200

### Phase C — Apply reverse migration to state.json files

C1. Confirm Dropbox sync is paused (or warn Kim)
C2. Run `python3 Production/scripts/migrate_phase_partitions_to_top_level.py --apply`
C3. Per-event: snapshot to `.backups/state/<TS>_pre_phase_revision.json`; atomic write of v3-shape state.json; read-back verify `is_already_migrated()`
C4. Run `--validate` mode on both events; expect exit 0
C5. Inspect `Event_1/.backups/state/` — confirm snapshot exists + sha256-matches pre-migration

### Phase D — v59 client restructure

D1. Update `Production/tools/storyboard-v2/src/state/scope.ts`:
   - Rename `activeVideoRole` → `activeTargetVideo`
   - Restrict signal value to `'intro' | 'resolution' | null` (null when milestone scope)
   - Add `activeProjectType` signal: `'event' | 'milestone'`
   - Add `activeMilestoneId` signal: `string | null`
D2. Rename `VideoSelector.tsx` → `TargetVideoSelector.tsx`:
   - `CANONICAL_ROLES = ['intro', 'resolution']` (drop phase_a, phase_b, win, standalone from this dropdown)
   - Hide entire component when `activeProjectType === 'milestone'`
D3. Rename `EventSelector.tsx` → `ProjectSelector.tsx`:
   - Lists events + milestones in grouped optgroups
   - On select: routes to `/api/event/load` or `/api/milestones/load`
   - Updates URL with `?event=<id>` OR `?milestone=<id>`
D4. Update `ScopeBoundary.tsx`:
   - On boot, read URL params for `event` OR `milestone`; call appropriate load endpoint
   - Hydrate `activeTargetVideo` from `state.active_video` if event scope; null if milestone
D5. Update `pathappPatch` (api/client.ts line ~203):
   - Auto-inject `scope_target_video: activeTargetVideo.value` (renamed from scope_video_role) for Beat Gen + Storyboard mutations
   - Skip auto-injection for Phase A/Phase B/Stitcher mutations (they don't need it)
   - Auto-inject `scope_milestone_id` when milestone scope active
D6. Restructure `StoryboardTab.tsx`:
   - REMOVE `<PhaseProducer phase="b" />` and `<PhaseProducer phase="a" />` siblings (lines 439-442)
   - FIX beat list to read from `state.videos[activeTargetVideo.value].beats` (the silent-broken bug)
   - Hide Storyboard tab content when `activeTargetVideo.value === null` (milestone with no partition); show "Select intro or resolution" placeholder
   - Add "Send Out as MP4" button that POSTs to `/api/export` with proper params
D7. Create `Production/tools/storyboard-v2/src/tabs/PhaseATab.tsx`:
   - Wraps existing `<PhaseProducer phase="a" />` in a tab pane with header
   - Hidden when milestone scope active
D8. Create `Production/tools/storyboard-v2/src/tabs/PhaseBTab.tsx`:
   - Same pattern, phase="b"
   - Hidden when milestone scope active
D9. Update `PhaseProducer.tsx`:
   - `pickPhaseSlice` reads top-level `state[`phase_${phase}_${suffix}`]` (this is what it ALREADY does — comes back to working when state shape reverts)
   - Verify hardcoded `Production/Event_1/${...}` paths honor `activeScope.event_id` (cleanup, not blocking)
D10. Update `TabBar.tsx`:
   - New tab order: `'beat_generator' | 'cropper' | 'storyboard' | 'phase_b' | 'phase_a' | 'stitcher'`
   - Add visual indicators: tabs disabled when not applicable to current scope (Phase A/B/Stitcher disabled when milestone)
D11. Update `app.tsx` `ActivePane()` switch to route the new tab keys + new components
D12. Update `StitcherTab.tsx`:
   - Auto-detect mode from `activeProjectType`
   - Module mode (event scope): 4 slots intro → phase_a → phase_b → resolution; reads `completed_mp4_path` from each
   - Standalone mode (milestone scope): 1 slot; reads `completed_mp4_path` from milestone's `videos.standalone`
D13. Restrict `BeatGeneratorTab.tsx` (when shipped — currently deferred to S5.5c):
   - When `activeTargetVideo.value === null`, show placeholder
   - Otherwise authors `state.videos[activeTargetVideo.value].beats` (or milestone's `videos.standalone.beats`)
D14. `npm run build` clean (no TS errors)

### Phase E — Verification (atomic gate sweep)

All gates must pass before Phase F.

E1. `python3 Production/scripts/migrate_phase_partitions_to_top_level.py --validate` exits 0
E2. `python3 -m py_compile Production/tools/production_server.py` clean
E3. `cd Production/tools/storyboard-v2 && npm run build` clean
E4. Server restart; `/api/health` 200; PID start time AFTER last edit (Rule 29)
E5. `GET /api/event/current` returns expected shape with `active_video ∈ {intro, resolution}` only
E6. `GET /api/video/list` for Event_1 returns `[intro, resolution]` only (no phase_a, phase_b, win)
E7. `GET /api/project/list` returns events + milestones structure
E8. `POST /api/video/set_active` accepts `intro` and `resolution`; rejects `phase_a`/`phase_b`/`win` with 400 + clear error
E9. `POST /api/video/create` same role validation
E10. `POST /api/milestones/create` with `{milestone_id: "test_milestone", milestone_label: "Test"}` creates `Production/Milestones/test_milestone/state.json`
E11. `POST /api/milestones/load` with `{milestone_id: "test_milestone"}` swaps active scope; subsequent state reads return milestone state
E12. State shape probe: read `Production/Event_1/production_state.json` → confirm `state.phase_a.*` fields at top level; confirm `state.videos` has only `{intro, resolution}` (no `phase_a`, `phase_b`, `win`); confirm `version=v3`
E13. State shape probe: same for Event_2 (Event_2 has no phase data; just confirm `videos` has `{intro, resolution}` not `{intro, win}`)
E14. Functional probe: POST a `phase_b_script` update via `_handle_v2_module_patch`; read back via `_handle_v2_event_state`; confirm `state.phase_b.phase_b_script` updated
E15. Functional probe: POST a `phase_a_ambient_preset_id` update; same verification
E16. Browser smoke (deferred but documented):
   - Load Event_1 in v59 client → see ProjectSelector + TargetVideoSelector + 6 tabs in production order
   - Switch TargetVideoSelector to "resolution" → Storyboard + Beat Generator update
   - Click Phase A tab → see Phase A producer (formerly inside Storyboard collapsible)
   - Click Phase B tab → see Phase B producer
   - Click Stitcher → see 4-slot module mode
   - Switch ProjectSelector to "+ New Milestone" → enter milestone_id → milestone scope loaded → Phase A/B/Stitcher slots adapt
   - Switch back to Event_1 → state preserved
E17. LD-474 audit script (`Production/scripts/ld474_audit_active_video.py`) STILL PASSES (regression gate; may need to update audit script for new role list)
E18. Cross-event swap (Event_1 → Event_2 → Event_1) cache-clear log appears 3×
E19. Bug 1 retest: Event_1 → Event_2 → Event_1 storyboard images intact
E20. Snapshots present at `Event_<N>/.backups/state/<TS>_pre_phase_revision.json`; sha256 matches pre-migration content
E21. `_VALID_VIDEO_ROLES` audit: grep server code for any reference to `'phase_a'` or `'phase_b'` as a video_role value; expect ZERO hits
E22. v59 client tab structure audit: 6 tabs in expected order; Phase A/B are top-level tabs
E23. Stitcher mode auto-detect: switching ProjectSelector between event and milestone changes Stitcher slot count
E24. `find_asset.py` query for recent Phase A / Phase B writes returns expected rows; iteration_notes preserved per LD-421
E25. `prod_activity_log` row `S5_5D_PHASE_AB_REVISION_COMPLETE` written

### Phase F — LD writes + amendments

F1. Write 6 new LDs via `try_post_or_queue` (per Rule 35 schema verification):
   - PHASE_A_TOP_LEVEL_STATE_V1 (HIGH)
   - PHASE_B_TOP_LEVEL_STATE_V1 (HIGH)
   - MILESTONE_STANDALONE_INDEPENDENT_V1 (HIGH)
   - TARGET_VIDEO_SELECTOR_V1 (MEDIUM)
   - TAB_STRUCTURE_PRODUCTION_ORDER_V1 (MEDIUM)
   - WIN_RENAMED_RESOLUTION_V1 (MEDIUM)

F2. PATCH 7 existing LDs with amendment notes (use Rule 35 protocol):
   - LD-473 BG_VIDEO_PARTITION_V1: append note about restriction to multi-beat roles
   - LD-474 VIDEO_ROLE_PER_REQUEST_V1: append note about new _VALID_VIDEO_ROLES
   - LD-475 IMAGE_OVERRIDES_CLEAR_ON_EVENT_LOAD_V1: append note about multi-beat-only applicability
   - LD-477 HANDLER_REFACTOR_VIDEOS_PARTITION_V1: append note about phase_a/b reverting to top-level
   - LD-478 IMAGE_OVERRIDES_NESTED_BY_ROLE_V1: append note about restricted role set
   - LD-481 VIDEO_SET_ACTIVE_ENDPOINT_V1: append note about restricted enum
   - LD-482 VIDEO_CREATE_ENDPOINT_V1: append note about restricted role set

F3. All writes via `try_post_or_queue` with read-back confirmation per Rule 35

### Phase G — Closeout

G1. `prod_activity_log` row `S5_5D_PHASE_AB_REVISION_COMPLETE` with full 25-gate summary + scope-vs-spec deviation flags (if any)
G2. Write S6 handoff stub (parallel-run + cutover) at `Production/docs/STORYBOARD_V59_S6_HANDOFF.md`
G3. Update `Production/docs/STORYBOARD_V59_S5_5_C_HANDOFF.md` (Beat Generator UI build) — note that Beat Generator now operates on `state.videos[activeTargetVideo.value].beats` with target ∈ {intro, resolution} OR milestone's `videos.standalone.beats`; rest of c spec unchanged
G4. Final independent tail-end verification subagent (per the a1/a2/b pattern)

---

## §5 Files Created / Modified

### Created (NEW)

- `Production/scripts/migrate_phase_partitions_to_top_level.py` — reverse migration script (~250 lines)
- `Production/tools/storyboard-v2/src/tabs/PhaseATab.tsx` — wraps PhaseProducer for top-level tab (~50 lines)
- `Production/tools/storyboard-v2/src/tabs/PhaseBTab.tsx` — wraps PhaseProducer for top-level tab (~50 lines)
- `Production/Milestones/` — new top-level directory for milestone state files
- `Production/docs/STORYBOARD_V59_S6_HANDOFF.md` — S6 prep handoff stub

### Modified

- `Production/tools/production_server.py` — handler reverts (~3 sites) + new endpoints (`/api/milestones/*`, `/api/project/list`) + `_VALID_VIDEO_ROLES` restriction + `_handle_export` semantics + `_handle_video_set_active`/`create` validation + ~5 helper updates
- `Production/scripts/migrate_state_to_videos_partition.py` — original migration script: remove PHASE_A_RE / PHASE_B_RE; add phase_a_*/phase_b_* to TOP_LEVEL_KEEP; rename win → resolution
- `Production/Event_1/production_state.json` — atomic v2→v3 reverse migration; phase_a/phase_b lifted to top-level; win renamed to resolution
- `Production/Event_2/production_state.json` — atomic v2→v3 (only win→resolution rename; no phase data)
- `Production/scripts/ld474_audit_active_video.py` — update valid role set
- `Production/tools/storyboard-v2/src/state/scope.ts` — rename activeVideoRole → activeTargetVideo + add activeProjectType + activeMilestoneId
- `Production/tools/storyboard-v2/src/components/VideoSelector.tsx` → renamed `TargetVideoSelector.tsx` — restrict to {intro, resolution}; hide on milestone
- `Production/tools/storyboard-v2/src/components/EventSelector.tsx` → renamed `ProjectSelector.tsx` — list events + milestones
- `Production/tools/storyboard-v2/src/components/ScopeBoundary.tsx` — handle event vs milestone scope
- `Production/tools/storyboard-v2/src/api/client.ts` — auto-inject scope_target_video / scope_milestone_id
- `Production/tools/storyboard-v2/src/api/endpoints.ts` — add new endpoint URLs
- `Production/tools/storyboard-v2/src/components/StoryboardTab.tsx` — remove Phase A/B siblings; fix beat list read; add "Send Out as MP4"; placeholder for milestone-without-partition
- `Production/tools/storyboard-v2/src/components/phase/PhaseProducer.tsx` — verify reads work post-revert (likely zero changes)
- `Production/tools/storyboard-v2/src/components/TabBar.tsx` — new tab order + disabled states
- `Production/tools/storyboard-v2/src/app.tsx` — route new tab keys
- `Production/tools/storyboard-v2/src/components/StitcherTab.tsx` — auto-detect 4-slot vs 1-slot mode
- `Production/tools/storyboard-v2/src/components/BeatGeneratorTab.tsx` (placeholder if not yet built; otherwise add scope check)
- `Production/docs/STORYBOARD_V59_S5_5_C_HANDOFF.md` — append note about new architecture
- `Production/PIPELINE_BRAIN_v1.md` — section update for new tab structure + state shape (per Rule 15 Reference Docs Registry Sync)
- `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` — add notes if any new schema deviations surface
- `Production/governance/storyboard-producer_governance.md` — update for new tab structure
- `Production/governance/video-producer_governance.md` — update for phase_a/phase_b being top-level

---

## §6 Directus Writes Required

All writes go through `try_post_or_queue` per Rule 35; consult `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` BEFORE composing each payload.

### `prod_locked_decisions`

POST 6 new LDs:
- PHASE_A_TOP_LEVEL_STATE_V1 (HIGH, active)
- PHASE_B_TOP_LEVEL_STATE_V1 (HIGH, active)
- MILESTONE_STANDALONE_INDEPENDENT_V1 (HIGH, active)
- TARGET_VIDEO_SELECTOR_V1 (MEDIUM, active)
- TAB_STRUCTURE_PRODUCTION_ORDER_V1 (MEDIUM, active)
- WIN_RENAMED_RESOLUTION_V1 (MEDIUM, active)

PATCH 7 existing LDs (append amendment notes; do NOT change status):
- LD-473, LD-474, LD-475, LD-477, LD-478, LD-481, LD-482

### `prod_activity_log`

- Phase A complete: `S5_5D_PHASE_A_PRESPEC` (preflight reference)
- Phase B complete: `S5_5D_PHASE_B_HANDLER_REVERTS_COMPLETE` with diff stats
- Phase C complete: `S5_5D_PHASE_C_MIGRATION_APPLIED` with snapshot paths + sha256
- Phase D complete: `S5_5D_PHASE_D_CLIENT_RESTRUCTURE_COMPLETE` with file list
- Phase E gate sweep: `S5_5D_PHASE_E_VERIFICATION_PASS` with all 25 gate results
- Phase F LD writes: `S5_5D_PHASE_F_LDS_REGISTERED` with new + patched LD IDs
- Phase G closeout: `S5_5D_PHASE_AB_REVISION_COMPLETE` with full session summary

### `prod_preflight_reviews`

- 1 row at session start: `task_type=architectural`, `approved_to_proceed=true`, references this spec
- After Phase G: PATCH `related_activity_log_id` to point at the COMPLETE row

### `prod_reference_docs`

- Register this spec doc + lessons learned doc per Rule 15 Write-Time Enforcement

---

## §7 Error Cases and Handling

| Failure | Handling |
|---|---|
| Reverse migration script fails on one event but not the other | Halt; restore both events from snapshots; do NOT proceed with handler reverts (state would be inconsistent) |
| Handler revert breaks py_compile | Halt; revert via git per-line until parses; investigate; do not patch on top of broken parse |
| _V2_MODULE_ALLOWED_FIELDS already lists phase_a/b at top level (per Agent B finding) — check confirms | No action needed; schema was already designed for top-level (this is GOOD, confirms architecture was always intended this way) |
| Async pin tuple still includes `video_role: "phase_a"` from in-flight job at migration time | Document as known transient; in-flight jobs may write to wrong path; mitigation = drain queue before migration apply |
| Client reads `state.videos.phase_a.{...}` and gets `null` post-migration | Expected during transition; but client revert (Phase D) prevents this; if it happens, it's a Phase D bug |
| Stitcher mode detection fails (always shows 4-slot even on milestone) | Bug in `activeProjectType` signal; fix via re-render trigger |
| Milestone created with duplicate ID | `POST /api/milestones/create` returns 409; client should use unique IDs (UUID or slug) |
| ProjectSelector lists events but milestones directory missing | Create `Production/Milestones/` if absent; return empty list (not error) |
| Existing async jobs that hold a pinned partition reference | Jobs were pinned by `(event_dir, event_id, video_role)` per LD-460 + S5.5a2 extension; if pinned to phase_a/phase_b, the post-migration write fails (path doesn't exist in new shape); pin tuple needs amendment for jobs in flight at migration time |
| Cursor v6 cross-review surfaces additional gaps | This spec is being sent to Cursor BEFORE execution per Kim's directive; revise spec based on Cursor findings |

**No silent failures.** Per Rule 19.

---

## §8 Verification

Done when all 25 gates from §4 Phase E pass + 6 new LDs registered + 7 LDs PATCHed + 7 activity_log rows written + browser smoke verified by Kim (gates E16 + E22) + Cursor v6 cross-review approved.

Proof artifacts:
- `git diff` of all file changes
- Migration script dry-run + apply output
- Snapshot file paths + sha256
- Curl probe outputs for new endpoints
- Browser screenshots from Kim hands-on smoke
- Directus row IDs for all writes
- Final activity_log summary row

---

## §9 Rollback

If anything goes wrong post-Phase C (state files mutated):

1. Stop server
2. Restore both `Production/Event_<N>/production_state.json` from `.backups/state/<TS>_pre_phase_revision.json`
3. `git checkout -- Production/tools/production_server.py` (handler reverts undone)
4. `git checkout -- Production/tools/storyboard-v2/` (client changes undone)
5. Restart server; verify `/api/health` 200 + state reads work as v2 shape
6. Document rollback in `prod_activity_log` action=`S5_5D_ROLLBACK` with reason

If only Phase D (client) goes wrong: `git checkout -- Production/tools/storyboard-v2/` is sufficient; server + state are unchanged.

If only Phase B (server handlers) goes wrong without state migration: `git checkout -- Production/tools/production_server.py` and restart server.

If only Phase F (LDs) goes wrong: PATCH new LDs to status=`superseded` with `superseded_by_id=null` and notes documenting rollback; PATCH the amended LDs to remove the new note.

---

## §10 Out of Scope (V1)

Things explicitly NOT in this spec (defer to future sessions):

- WaveSurfer.js timeline (LD-472) — Session 6 polish
- Beat Generator UI build (S5.5c) — separate session; this spec only ensures the architecture is ready for it
- Per-event-per-target Playwright matrix expansion — defer
- Stitcher 1-slot UI polish — basic mode-switching is in scope; advanced standalone export options defer
- Phase A/B history/diff UI for prior MP4 generations — covered by `find_asset.py` query, no in-tool UI
- Multiple milestones per single milestone scope (e.g., chapters within a milestone) — defer
- Migration of existing prod_assets rows to new role taxonomy — they stay as-is; new writes use new taxonomy

---

## §11 Dependencies on Prior Sessions

**Hard dependency on S5.5a1 + S5.5a2 + S5.5b:**
- StateManager helpers (`get_beats`, `mutate_video_state`, etc.) — still load-bearing
- Cache-clear on event load (LD-475) — extended for milestone load
- Scope token + async pin (LD-460) — pin tuple amended to drop video_role for phase_a/b (they don't need it post-revision)
- 4 endpoints from S5.5b (`/api/event/current`, `/api/video/list`, `/api/video/set_active`, `/api/video/create`) — 3 stay, 1 (set_active) gets restricted role enum
- VideoSelector → TargetVideoSelector rename uses S5.5b infrastructure

**Independent of:**
- S5.5c (Beat Generator UI build) — c spec needs minor update for the new architecture but doesn't block this revision

**Forward-blocking S6:**
- S6 (parallel-run + cutover) MUST happen AFTER this revision lands
- S6 parallel-run on Event_2 needs the corrected architecture or it will exercise the same bugs

---

## §12 Notes for the Executing Session

- This spec is being sent to Cursor v6 cross-review BEFORE execution per Kim's directive
- Where Cursor v6 disagrees with this spec, surface to Kim before adopting Cursor's revision
- Per Rule 35: every Directus write consults `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` BEFORE composing payload; uses `try_post_or_queue` from `Production/lib/directus.py`; reads back to confirm
- Per Rule 36: any new Path B-style patches in storyboard-v2 follow §36.1 invariant constraints
- Per Rule 19: no shortcuts. The architectural revision is bounded but real; do not stub
- Per Rule 27: delete the OLD `videos.phase_a` and `videos.phase_b` partition initialization code in handlers (the `state.setdefault("videos", {}).setdefault("phase_a", ...)` pattern at line 14519, 14520, 9454, 9821, 9850, 11364, 10548, 10629 — Agent B's finding G #9). Don't leave dead code that creates empty partitions.
- Per Rule 24 confidence annotation: terminal Claude should annotate any inferred claims with `[INFERRED — verify]` tags when uncertain
- Per `feedback_file_links.md`: any Kim-facing previews go through HTML-page-in-Safari pattern, NOT file:// links
- The 6 broken handler sites Agent B identified (lines 14151, 14183, 14583-14584, 14793, 14805, 12481-12482) become CORRECT automatically when state shape reverts — no edits needed at those sites; just verify via functional probe in Phase E

---

## §13 Cursor v6 Review Checklist

Send Cursor this spec + the following questions:

1. Are there any handlers in `production_server.py` that touch `state.videos.phase_a` or `state.videos.phase_b` that this spec missed? (Agent B identified ~3 sites; please scan for additional)
2. Is the reverse migration script idempotent + fail-closed? (review §4 Phase A2)
3. Does the `_handle_export` "Send Out as MP4" semantics match LD-139 + LD-284 correctly? (review §3.5 + §4 Phase B8)
4. Are the new endpoints (`/api/milestones/*`, `/api/project/list`) safe to add atomically with the rest of the changes?
5. Is the v59 client restructure complete? Specifically:
   - Tab routing in `app.tsx` updated for 6 tabs?
   - PhaseProducer.tsx correctly reads top-level state.{phase_a|phase_b} after revert?
   - StoryboardTab.tsx correctly reads `state.videos[activeTargetVideo].beats`?
   - Stitcher mode auto-detection works for both event and milestone scopes?
6. Is the milestone storage layout safe? (`Production/Milestones/<milestone_id>/state.json`)
7. Is the LD amendment vs replacement decision correct? (7 amend, 6 new)
8. Are there any cascading updates we missed? (PIPELINE_BRAIN, governance docs, schema reference)
9. Verification gates — are 25 enough? Anything we should add?
10. Rollback procedure — is it complete? Edge cases?

Append Cursor's findings to this spec as §14 before terminal execution.

---

**End of spec v1.** Send to Cursor v6, revise per findings, then handoff to fresh terminal for atomic single-session execution.
