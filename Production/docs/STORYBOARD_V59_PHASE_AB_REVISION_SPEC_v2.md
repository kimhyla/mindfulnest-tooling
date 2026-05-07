# Storyboard v59 — Phase A/B Architecture Revision Spec v2

**Date:** 2026-05-03
**Produced by:** tech-spec skill (two-agent Opus debate, v2 cycle incorporating Cursor v6 review)
**Supersedes:** `STORYBOARD_V59_PHASE_AB_REVISION_SPEC_v1.md` (kept as historical reference)
**Classification:** ARCHITECTURAL revision (state shape change + tab restructure + new milestone concept + new export pipeline)
**Prior context:** S5.5a1 + S5.5a2 + S5.5b shipped; browser smoke surfaced design gap; v1 spec authored; Cursor v6 cross-review surfaced 2 release-blockers + 9 amendments; Kim locked Decision 1=A (build the new pipeline) and Decision 2=B (supersede LD-473 + LD-474)

---

## §1 Task

Reverse the architectural mistake from S5.5a1/a2 where `phase_a` and `phase_b` were modeled as video-role siblings of `intro`/`win` under a unified `state.videos.{role}` partition. They are separate top-level state (different KIND of authoring). Browser smoke test on 2026-05-03 confirmed the unification was wrong.

**v2 changes from v1** (driven by Cursor v6 review + Kim's Option A + Option B locked decisions):

1. **Reverse migration** — lift `state.videos.phase_a/b` back to top-level (unchanged from v1)
2. **Server handler reverts** — symbol-based, not line-based; explicitly includes `_auto_assemble_phase_a_stitched` and `StateManager._init_files` (Cursor Q1 + R4)
3. **Naming alignment** — rename `videos.win` → `videos.resolution` (LD-412); explicit win-literal audit phase added (Cursor R4)
4. **Tab restructure** — Phase A and Phase B as top-level tabs; production-order tabs (unchanged from v1)
5. **Milestone (standalone) concept** — independent multi-beat videos; `Production/Milestones/<id>/state.json`; `milestone_id` regex + reserved words + backup parity (Cursor Q6)
6. **TargetVideoSelector** — restricted to `{intro, resolution}`; in milestone scope, **resolves to `'standalone'` (NOT null)** so Storyboard + Beat Generator stay enabled (Cursor Q5 release-blocker fix)
7. **ProjectSelector** — extends EventSelector; lock contract + cache invalidation match `event/load` (Cursor Q4)
8. **NEW EXPORT PIPELINE (Cursor Q3 release-blocker fix)** — build `/api/beat/finalize` (per-beat with `finalize_args_hash` cache) + `/api/scene/assemble` (concat orchestrator) + `_handle_export` rewrite per spec §3.5. Reuses `lib/ffmpeg_stitch.py` primitives (`normalize_for_concat`, `concat_with_xfade_clips`). Per-beat MP4s become first-class registered assets (`asset_type='beat_scene'`); concat MP4 registered as new asset type `scene_concat_mp4`.
9. **NEW DRAIN PROTOCOL** — pre-migration queue drain via `app._inflight_jobs` registry + admin endpoints (Cursor R1 release-blocker fix)
10. **LD work** — 12 NEW LDs (vs v1's 6) + 5 amendments (vs v1's 7; LD-473 + LD-474 SUPERSEDED instead per Cursor Q7) + 2 LD PATCHes (LD-139, LD-460) + 1 CODE-SPEC ALIGNMENT to `lib/ffmpeg_stitch.py` so the live recipe matches LD-284's text (re-bake on next assemble; LD-284 itself unchanged)

This is a SINGLE-SESSION ATOMIC change per Kim's Q3=A directive 2026-05-03.

---

## §2 Governing Decisions

### Locked decisions this spec respects (must not violate)

| LD | Key | Reason |
|---|---|---|
| LD-139 | STITCH_ARCHITECTURE_MULTI_STAGE | Multi-stage finalize → normalize → concat; v2 implements this end-to-end for the first time |
| LD-245 | SILCOMP_CONCAT_PATHS_MUST_BE_ABSOLUTE | concat.txt entries must be `p.resolve()` |
| LD-280 | RENDERING_ARCHITECTURE_SINGLE_MP4_ATOMIC_V1 | Module ships as ONE atomic MP4 (Stitcher slot 4-bake); `final_atomic_mp4` reserved for that |
| LD-281 | NO_RUNTIME_TTS_PERSONALIZATION_V1 | All TTS bakes at production time |
| LD-284 | NORMALIZATION_BEFORE_CONCAT_V1 | Per-segment normalization before module concat. **LIVE CODE aligned to LD-284 strict spec in v2** (`-preset slow`, `setsar=1:1`, `-g 48`); `NORMALIZATION_RECIPE_HASH` auto-bumps; cache invalidates; first re-bake after migration re-encodes from source at the strict recipe |
| LD-316 | MODULE_EXIT_AND_PROGRESSION_V1 | Names "Win video" as in-module section (semantically aligned to "resolution") |
| LD-375 | PHASE_A_CANONICAL_PIPELINE_V1_20260421 | 5-stage Phase A canonical pipeline |
| LD-376 | PHASE_A_XFADE_RECIPE_V1_20260421 | Phase A fade_in 0.5s + fadeblack 2.5s |
| LD-330 | PHASE_B_AUTHORING_WAVEFORM_FIRST_RESTORE_V1 | WaveSurfer ws.load(audio_url) source of truth |
| LD-412 | PHASE_BOUNDARIES_NAMED_OBJECT_V1 | Valid V1 names: `intro, phase_a, phase_b, resolution` — drives win→resolution rename |
| LD-421 / LD-422 | ASSET_FINDABILITY_OVERHAUL_V1 / BUILD_V1 | All media writes via `registered_write.py`; component preservation per Kim Q2 directive; `iteration_notes` indexed |
| LD-423 | STITCH_EDITOR_UNIVERSAL_V1 | N-slot variable assembly (1-slot for milestones; 4-slot for module) |
| LD-456 | SCOPE_VALIDATION_V1 | `_assert_event_scope` + HTTP 409 |
| LD-458 | EVENT_LOAD_GENERATION_LOCK_V1 | Atomic event swap |
| LD-459 | UNIVERSAL_AUTOSAVE_V1 | `.L.json` sidecar |
| LD-460 | ASYNC_JOB_GENERATION_PIN_V1 | Pin tuple at job entry; **PATCHed in v2** to add drain protocol |
| LD-461 | SCOPE_BODY_HELPER_V1 | `_scope_body` normalization |
| LD-462 | PHASE_A_PRODUCER_V1 | v59 Phase A producer (moved from Storyboard collapsible to its own tab) |
| LD-463 | PHASE_B_PRODUCER_V1 | v59 Phase B producer (same) |
| LD-465 | PRODUCTION_MAP_V1 | Already encodes the conceptual split (segments matrix) |
| LD-466 | EXPORT_TO_STITCHER_V1 | Storyboard "Send Out" produces slot input; LD-466 governs Stitcher consumption |
| LD-467 | MULTI_EVENT_SELECTOR_V1 | Top-of-app selector — extended for milestones |
| LD-471 | STITCHER_FULL_UI_V1 | Stitcher slot reads `completed_mp4_path` from `state.videos[role]` |

### Locked decisions this spec amends

| LD | Key | Amendment |
|---|---|---|
| LD-475 | IMAGE_OVERRIDES_CLEAR_ON_EVENT_LOAD_V1 | Clarify: applies only to multi-beat partitions; cache invalidation list extended for milestone load |
| LD-477 | HANDLER_REFACTOR_VIDEOS_PARTITION_V1 | Clarify: handlers refactored for multi-beat partitions; phase_a/b handlers continue to use top-level |
| LD-478 | IMAGE_OVERRIDES_NESTED_BY_ROLE_V1 | Restrict nesting to `{intro, resolution, standalone}` |
| LD-481 | VIDEO_SET_ACTIVE_ENDPOINT_V1 | `state.active_video` enum restricted to `{intro, resolution}` |
| LD-482 | VIDEO_CREATE_ENDPOINT_V1 | Valid roles for `_handle_video_create` restricted to `{intro, resolution, standalone}` |

### Locked decisions this spec SUPERSEDES (per Cursor Q7)

| LD | Key | Reason for supersede (vs amend) |
|---|---|---|
| LD-473 | BG_VIDEO_PARTITION_V1 | Semantic contract changed materially: 5-role unified partition → 3-role multi-beat split. Clean break. Replaced by `BG_VIDEO_PARTITION_V2`. |
| LD-474 | VIDEO_ROLE_PER_REQUEST_V1 | `_VALID_VIDEO_ROLES` set changes from `{intro, phase_a, phase_b, win, standalone}` (5) to `{intro, resolution, standalone}` (3). Replaced by `VIDEO_ROLE_PER_REQUEST_V2`. |

### Locked decisions this spec PATCHES

| LD | Patch reason |
|---|---|
| LD-139 STITCH_ARCHITECTURE_MULTI_STAGE | v2 implements `/api/beat/finalize` and `/api/scene/assemble` for the first time; previously unimplemented |

### Code-spec alignment (LD-284 stays unchanged; live code changes to match it)

LD-284 NORMALIZATION_BEFORE_CONCAT_V1 says `-preset slow`, `setsar=1:1`, `-g 48`. Live recipe at `lib/ffmpeg_stitch.py:47-59` ships `-preset medium`, no setsar, no `-g 48` (drift since LD-284 was authored). **v2 ALIGNS the live code to LD-284's strict spec**, NOT the other way around. Effects:

- `NORMALIZATION_RECIPE_HASH` (sha256 of recipe constants) changes automatically, invalidating every cached `*_normalized.mp4` across both events.
- Next `/api/scene/assemble` per beat: cache MISS → re-encode from source at the strict recipe (~3–5 sec/beat at `-preset slow`). Source clips untouched.
- Subsequent re-sends with cached beats: instant.
- Output quality: smaller files at same perceptual quality (or higher quality at same bitrate) due to `-preset slow`. Explicit `setsar=1:1` prevents downstream stretching. `-g 48` GOP improves seek precision in players.

LD-284 itself is NOT PATCHed. The decision text remains the canonical spec; the code now obeys it.

### NEW LDs this spec writes (12)

| Key | Severity | Purpose |
|---|---|---|
| `PHASE_A_TOP_LEVEL_STATE_V1` | HIGH | Phase A state lives at `state.phase_a.{...}` (top-level), NOT under `state.videos`. Phase A is single-clip producer, not multi-beat sequence. |
| `PHASE_B_TOP_LEVEL_STATE_V1` | HIGH | Same for Phase B. |
| `MILESTONE_STANDALONE_INDEPENDENT_V1` | HIGH | Milestone videos are independent of events; stored at `Production/Milestones/<milestone_id>/state.json`. Authored via Beat Generator + Cropper + Storyboard with `activeTargetVideo='standalone'`; exported via Stitcher 1-slot mode. |
| `BG_VIDEO_PARTITION_V2` | HIGH | Replaces (supersedes) LD-473. Partition contains only `{intro, resolution, standalone}`. Phase_a/phase_b explicitly removed. |
| `VIDEO_ROLE_PER_REQUEST_V2` | HIGH | Replaces (supersedes) LD-474. `_VALID_VIDEO_ROLES = {intro, resolution, standalone}`. Phase_a/phase_b are NOT video roles. |
| `BEAT_FINALIZE_ENDPOINT_V1` | HIGH | Defines `POST /api/beat/finalize` — per-beat finalize+normalize as single artifact, cached by `finalize_args_hash`. Specifies hash variable set, output filename convention, sidecar JSON contract. |
| `SCENE_ASSEMBLE_ENDPOINT_V1` | HIGH | Defines `POST /api/scene/assemble` — concat orchestrator. Snapshot-on-start, fcntl lock per `(event_id, role)`, calls `registered_write.register_asset(asset_type='scene_concat_mp4')`, writes `state.videos[role].completed_mp4_path`. |
| `ASYNC_QUEUE_DRAIN_PROTOCOL_V1` | HIGH | Defines drain mechanism: `app._inflight_jobs` registry, `app.accept_new_jobs` flag, admin endpoints (`/api/admin/drain_start`, `/drain_end`, `/inflight_count`). Migration script polls until drained before applying. Closes Cursor R1. |
| `ASSET_TYPE_SCENE_CONCAT_V1` | LOW | Adds `scene_concat_mp4` to `_ACCEPTED_ASSET_TYPES` in `registered_write.py`. Distinct from `final_atomic_mp4` which stays reserved for the Stitcher 4-slot bake per LD-280. |
| `STORYBOARD_SEND_OUT_PROVENANCE_V1` | MEDIUM | Locks `iteration_notes` template + `parent_asset_id` linkage so re-send produces distinct queryable scene assets with provenance to source beats. Closes Cursor R5. |
| `TARGET_VIDEO_SELECTOR_V1` | MEDIUM | Header dropdown restricted to `{intro, resolution}`. In milestone scope: dropdown HIDDEN; signal value resolves to `'standalone'` so Storyboard + Beat Generator remain functional. Affects Beat Generator + Storyboard tabs ONLY. |
| `TAB_STRUCTURE_PRODUCTION_ORDER_V1` | MEDIUM | Tab order matches production workflow: Beat Generator → Cropper → Storyboard → Phase B → Phase A → Stitcher. Phase A and Phase B are top-level tabs (not collapsibles inside Storyboard). |

---

## §3 Approach

### §3.1 State shape (corrected architecture)

```jsonc
// Per-event state (Production/Event_<N>/production_state.json), version="v3":
{
  "event_id": "M1E1",
  "version": "v3",
  "active_video": "intro",  // {intro, resolution} only
  "_module_version": 240,
  "module_sfx_cues": [...],
  "fade_between_beats_ms": 0,
  "latest_preview_stitched_path": "...",
  "full_module_segment_boundaries": [...],

  // Multi-beat sequences (Beat Gen + Storyboard target these):
  "videos": {
    "intro": {
      "video_role": "intro", "video_label": null,
      "beats": {...}, "image_overrides": {...},
      "display_order": [...],
      "completed_mp4_path": null  // populated by /api/scene/assemble
    },
    "resolution": {
      "video_role": "resolution", "video_label": null,
      "beats": {...}, "image_overrides": {...},
      "display_order": [...],
      "completed_mp4_path": null
    }
  },

  // Single-clip producers (TOP LEVEL, separate top-level state):
  "phase_a": {
    "phase_a_script": "...",
    "phase_a_voice_stem_file": "...", "phase_a_voice_stem_mtime": 0,
    "phase_a_lipsync_file": "...", "phase_a_lipsync_mtime": 0,
    "phase_a_empty_desk_bg_id": "...",
    "phase_a_chipper_flyin_clip_id": "...", "phase_a_chipper_sitting_clip_id": "...", "phase_a_chipper_flyout_clip_id": "...",
    "phase_a_mixed_audio_file": "...", "phase_a_mixed_audio_mtime": 0,
    "phase_a_ambient_preset_id": "...",
    "phase_a_watercolor_cues_json": "[]",
    "phase_a_stitched_file": "...",  // ADD to _V2_MODULE_ALLOWED_FIELDS whitelist
    "phase_a_stitched_mtime": 0,     // ADD to whitelist
    "phase_a_status": "draft"
  },
  "phase_b": {
    "phase_b_script": "...",
    "phase_b_voice_stem_file": "...", "phase_b_voice_stem_mtime": 0,
    "phase_b_ambient_preset_id": "...",
    "phase_b_mixed_audio_file": "...", "phase_b_mixed_audio_mtime": 0,
    "phase_b_cedric_base_clip_id": "...",
    "phase_b_lipsync_file": "...", "phase_b_lipsync_mtime": 0,
    "phase_b_watercolor_cues_json": "[]",
    "phase_b_preview_file": "...",
    "phase_b_status": "draft"
  }
}

// Standalone milestone state (Production/Milestones/<milestone_id>/state.json), version="v3":
{
  "milestone_id": "magic_intro_video",
  "milestone_label": "Magic Intro Video",
  "version": "v3",
  "created_at": "2026-05-03T...",
  "updated_at": "2026-05-03T...",
  "videos": {
    "standalone": {
      "video_role": "standalone", "video_label": null,
      "beats": {...}, "image_overrides": {...},
      "display_order": [...],
      "completed_mp4_path": null
    }
  }
}
```

**Key shape rules:**
- `state.phase_a` and `state.phase_b` keep their `phase_X_` field-name prefixes
- `state.videos` partition contains ONLY `{intro, resolution}` for events; `{standalone}` for milestones
- `state.active_video` restricted to `{intro, resolution}` for events (NULL for milestones — only one role applies)
- Each multi-beat partition gains `completed_mp4_path` field (default null; populated by `/api/scene/assemble`)
- `_V2_MODULE_ALLOWED_FIELDS` whitelist gains `phase_a_stitched_file` + `phase_a_stitched_mtime` (both implied by LD-462 rename but never added)

### §3.2 Tab structure (production workflow order)

```
[Beat Generator]  [Cropper]  [Storyboard]  [Phase B]  [Phase A]  [Stitcher]
       ↑              ↑            ↑           ↑           ↑           ↑
       └─── reusable for ──────────┘           └─ standalone ─┘     Module
       intro / resolution / standalone         (one event)         assembly
       (driven by TargetVideoSelector)         (independent)
```

| Tab | Role | State path | TargetVideoSelector affects? | Disabled when milestone scope? |
|---|---|---|---|---|
| Beat Generator | Multi-beat authoring | `state.videos[<active_target>].beats` | YES | NO (uses 'standalone') |
| Cropper | Image crop tool | image library / asset paths | NO | NO |
| Storyboard | Multi-beat sequence editor + "Send Out as MP4" | `state.videos[<active_target>].{beats, image_overrides, display_order, completed_mp4_path}` | YES | NO (uses 'standalone') |
| Phase B | Single-clip Cedric meditation video | `state.phase_b.{...}` (top-level) | NO | YES (no phase data) |
| Phase A | Single-clip Chipper demo video | `state.phase_a.{...}` (top-level) | NO | YES (no phase data) |
| Stitcher | 4-slot module mode + 1-slot standalone mode | reads `completed_mp4_path` per slot | NO | NO (auto-detects 1-slot mode) |

### §3.3 TargetVideoSelector (Cursor Q5 contradiction fix)

- Header dropdown: `Target: [intro] [resolution]`
- When event scope active: dropdown shows `{intro, resolution}`; signal value matches selection
- When milestone scope active: dropdown HIDDEN; signal value **resolves to `'standalone'`** (NOT null) so Storyboard + Beat Generator continue to operate against `state.videos.standalone.beats`
- Phase A + Phase B tabs disabled in milestone scope (no phase data exists for milestones)
- Affects only Beat Generator + Storyboard tabs (other tabs ignore it)
- No confirm prompt on switch (Q1=A from v1) — partition data auto-saved

### §3.4 ProjectSelector (extends EventSelector)

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

**Lock contract + cache invalidation (Cursor Q4 amendment):**
- `/api/milestones/load` uses the same `event_load_lock` class as `/api/event/load` (atomic swap)
- `event_generation` IS bumped on milestone load (treated as scope-swap; existing pin checks remain valid)
- Cache invalidation list on milestone load matches event load: beats cache, storyboard list cache, image override caches per LD-475
- `app.scope_type: 'event' | 'milestone'` field added to context; persisted via session URL params
- `/api/project/list` and `/api/milestones/list` are READ-ONLY (no scope guard)
- `/api/milestones/create` and `/api/milestones/load` validate input strictly (see §3.4.1)

#### §3.4.1 Milestone ID validation (Cursor Q6 amendment)

- **Regex:** `^[a-z0-9][a-z0-9_-]{2,63}$` (lowercase, alphanumeric + `_-`, 3-64 chars, no leading separator)
- **Reserved words list:** `{event_*, _tmp_*, _backup_*, archive, default, system, admin, root}` — case-insensitive prefix matches rejected
- **Uniqueness:** case-insensitive collision returns HTTP 409
- **Backup parity:** `Production/Milestones/<id>/.backups/state/<TS>_*.json` mirrors event backup structure
- **Persistence:** `Production/Milestones/` is committed to git (NOT gitignored); state.json files version with the project

### §3.5 "Send Out as MP4" — NEW EXPORT PIPELINE (Cursor Q3 release-blocker fix)

When Kim hits "Send Out as MP4" in Storyboard tab for the active target:

#### Stage 1: Per-beat finalize (cached)

```
POST /api/beat/finalize
body: { scope_event_id, scope_target_video, beat_id, force_rebuild? }
```

For each beat in `state.videos[<target>].beats` (or milestone's `videos.standalone.beats`), the server:

1. Snapshots beat state at handler entry (per `_handle_preview_stitched` snapshot-on-start invariant, line 11870-11872)
2. Computes `finalize_args_hash` covering:
   - `beat_id`
   - resolved input file abs path (via `resolve_beat_file()` priority order: `final.file` → `phase_1.selected_option.file`)
   - resolved input file `mtime`
   - `phase_1.selected_option`
   - `phase_1.trim_start`, `trim_end`
   - `phase_1.pause_after_ms`
   - `phase_1.audio_delay`
   - `phase_1.fade_after_ms`
   - `image_overrides[<role>][<beat_id>]` (if compositing applies)
   - `selected_lipsync_path` (if lipsync applied)
   - `NORMALIZATION_RECIPE_HASH` (from `lib/ffmpeg_stitch.py:65-68`)
   - `FINALIZE_RECIPE_VERSION` sentinel (new const, default "v1")
3. Cache filename: `{beat_id}_final_{src_md5_10}_{recipe6}_{trim_start_ms}_{trim_end_ms}_{audio_delay_ms}.mp4` (mirrors existing pattern at production_server.py:12018-12063)
4. Cache directory: `event_dir/animation_clips_final/` (or milestone's `Milestones/<id>/animation_clips_final/`)
5. Sidecar JSON: `<cache_filename>.meta.json` containing `{finalize_args_hash, finalize_args, recipe_hash, recipe_version, generated_at, source_path, source_mtime, source_sha256_first_1mb}`
6. **If cache HIT** (sidecar matches all hash inputs): return existing path, `cache_hit: true`
7. **If cache MISS**: invoke `lib/ffmpeg_stitch.normalize_for_concat()` with trim/audio_delay applied, write atomic tmp+rename, register via `registered_write.register_asset(asset_type='beat_scene', module_id=<resolved>, event_id=<resolved>, beat_id=<beat_id>, role=<role>, parent_asset_id=null, produced_by_skill='beat_finalize_v1', iteration_notes=<template>)`, write sidecar, return path + `cache_hit: false`
8. Per LD-460: full pin tuple at entry + terminal pin check before rename

**Single-artifact strategy:** `beat_NN_final.mp4` is BOTH the trimmed-and-audio-delayed AND the LD-284-normalized version. One cache, one hash. No separate `beat_NN_normalized.mp4` step.

#### Stage 2: Scene assemble (concat orchestrator)

```
POST /api/scene/assemble
body: { scope_event_id, scope_target_video, fade_between_beats_ms?, force_rebuild? }
```

1. `_assert_event_scope` + LD-460 pin tuple at entry
2. fcntl `LOCK_EX | LOCK_NB` on `event_dir/scene_assemble_<role>.lock` — returns 409 if another assemble is in flight on same `(event_id, role)`
3. Snapshot state at handler entry (NEVER re-read mid-pipeline)
4. For each beat in `display_order`: invoke per-beat finalize internally (in-process call, not HTTP)
5. After all beats finalized: invoke `lib/ffmpeg_stitch.concat_with_xfade_clips()` with the finalized paths + `fade_between_beats_ms`
6. Output written atomic tmp+rename to `event_dir/<role>/scene_<role>_<assemble_hash>.mp4`
7. `assemble_hash` = sha256 of `(NORMALIZATION_RECIPE_HASH + ASSEMBLE_RECIPE_VERSION + ordered list of finalize_args_hash per beat + fade_between_beats_ms)`
8. SIZE_BUDGET gates per LD (≤ 1.9 Mbps, ≤ 80 MB) — match existing `_handle_stitch_bake` pattern (lines 13668-13694)
9. Register via `registered_write.register_asset(asset_type='scene_concat_mp4', module_id=<resolved>, event_id=<resolved>, beat_id=null, role=<role>, parent_asset_id=null, produced_by_skill='scene_assemble_v1', iteration_notes=<see below>, colloquial_name=f"{event_id}_{role}_send_out", tags=['scene_assembly', role, 'multi_beat'])`
10. Write path to `state.videos[<target>].completed_mp4_path` via state mutation helper
11. Terminal pin check before state write
12. Returns `{ok: true, asset_id, completed_mp4_path, assemble_hash, beat_count, file_size_bytes, bitrate_bps, cache_stats: {hits, misses}}`

#### `iteration_notes` template (Cursor R5 + STORYBOARD_SEND_OUT_PROVENANCE_V1)

```
[<iso_ts>] Send Out: scene assembly. event=<event_id>, target_video=<role>,
beats=[<ordered beat_id list>], assemble_hash=<short>,
fade_between_beats_ms=<n>, source_beat_asset_ids=[<ids>],
recipe=<NORMALIZATION_RECIPE_HASH>:<ASSEMBLE_RECIPE_VERSION>,
cache_hits=<n>, cache_misses=<n>.
```

This satisfies: re-send produces a distinct concat asset row (new id, new path via different `assemble_hash` when any beat changed); re-send with no beat changes hits cache and is a fast no-op.

#### Component preservation (Cursor R5 verification)

Verified explicitly via Phase E gates:
- Source `state.videos[<target>].beats` unchanged after send-out (gate E26)
- Each `beat_scene` asset row remains queryable via `find_asset.py` (gate E27)
- Re-send with one beat changed produces a new `scene_concat_mp4` row with a different path/asset_id (gate E28)

#### Old `_handle_export` behavior

DELETED per Rule 27 (no obsolete workarounds). The `animation_selections.json` JSON-only manifest is no longer produced. If Kim has downstream consumers of this manifest, they migrate to consuming `state.videos[role].completed_mp4_path` directly.

### §3.6 Stitcher modes

Two modes, one tab (auto-detected from `app.scope_type`):

**Module mode (4-slot, when Event scope active):**
- 4 slots in fixed order: intro → Phase A → Phase B → resolution
- Each multi-beat slot reads `state.videos[<role>].completed_mp4_path`
- Each phase slot reads `state.phase_<a|b>.phase_<a|b>_stitched_file` (existing pattern)
- Per-slot ambient_bed selection (per LD-466)
- Bake → final module MP4 via existing `_handle_stitch_bake` (LD-471)

**Standalone mode (1-slot, when Milestone scope active):**
- 1 slot: standalone milestone MP4
- Reads `state.videos.standalone.completed_mp4_path` from milestone state.json
- Direct export (no module assembly)
- Per LD-423 Universal Stitch Editor's N-slot variable mode (1=N here)

Stitcher tab UI auto-detects mode from `app.scope_type`.

### §3.7 Async drain protocol (NEW — Cursor R1 release-blocker fix)

**Mechanism (per `ASYNC_QUEUE_DRAIN_PROTOCOL_V1`):**

1. `app._inflight_jobs: dict[str, dict]` registry (in-memory). Keyed by job_id.
2. `app.accept_new_jobs: bool = True` flag, default True.
3. **At every pin-init site (the 17 in `production_server.py`):** after pin capture, check `if not self.app.accept_new_jobs: return self._send_json(503, {"error": "drain_in_progress"})`. After pre-work pin check, register job: `self.app._inflight_jobs[job_id] = pin`. In `finally` block: `self.app._inflight_jobs.pop(job_id, None)`.
4. **New endpoints:**
   - `POST /api/admin/drain_start` — sets `accept_new_jobs = False`, returns `{ok: true, inflight_count: <n>}`
   - `POST /api/admin/drain_end` — sets `accept_new_jobs = True`, returns `{ok: true}`
   - `GET /api/admin/inflight_count` — returns `{ok: true, inflight_count: <n>, accept_new_jobs: <bool>}`
5. **Migration script** (`migrate_phase_partitions_to_top_level.py`) in `--apply` mode:
   - First: `POST /api/admin/drain_start`
   - Poll `GET /api/admin/inflight_count` until 0 OR 60-second timeout (fail-closed: abort with explicit error if still in flight after 60s)
   - Snapshot state.json files
   - Apply migration
   - `POST /api/admin/drain_end`

This fences the migration window only. Long-term `pinned_video_role` enforcement is NOT added in this revision (LD-460 PATCHed to note: "drain protocol added; per-role enforcement deferred to migration window only").

---

## §4 Implementation Phases (atomic single-session per Q3=A)

### Phase A — Pre-flight + reverse migration script (read-only / dry-run)

**A1.** Read current state.json files for both events; capture exact pre-state shape.

**A2.** Write `Production/scripts/migrate_phase_partitions_to_top_level.py` with:
- Modes: `--dry-run`, `--apply`, `--validate`
- For each event state.json: lift `state.videos.phase_a.{...}` to `state.{...}` (top-level); same for phase_b; rename `videos.win` → `videos.resolution`; bump `version` v2→v3
- Snapshot to `Production/Event_<N>/.backups/state/<TS>_pre_phase_revision.json` BEFORE write (sha256 logged)
- **`is_already_migrated()` strict invariant** (Cursor Q2 amendment) — ALL must hold:
  - `state["version"] == "v3"`
  - `"resolution" in state["videos"]`
  - `"win" not in state["videos"]`
  - `"phase_a" not in state["videos"]`
  - `"phase_b" not in state["videos"]`
  - top-level `state["phase_a"]` exists OR explicitly absent (`_event_has_phase_data` check; Event_2 may be sparse)
  - top-level `state["phase_b"]` exists OR explicitly absent (same)
- **Fail-closed mixed-version guard:** if some events at v2 and some at v3, abort with explicit error
- **Key-collision check:** abort on FIRST collision between `state.videos.phase_a.<key>` and existing `state.<key>` (mandatory; no override)
- Idempotency: returns "already migrated" if `is_already_migrated()` for all target events

**A3.** Run script in `--dry-run` mode against both events; verify output shows expected lift + rename.

**A4.** Synthesize a fake half-migrated state file; verify fail-closed behavior.

**A5.** Synthesize a fake collision state file (top-level `phase_a_script` already present with different value than `videos.phase_a.phase_a_script`); verify abort.

### Phase B0 — Pre-revert audit (NEW per Cursor R4)

**B0.1.** Grep all live `'win'` literal sites that must be renamed (scope: actual video role values, NOT coincidental matches like Windows USERNAME default at line 369):
- `production_server.py` line 853 (StateManager `_init_files` seed key)
- `production_server.py` line 854 (StateManager `_init_files` seed `video_role` field)
- `production_server.py` line 1081 (`_VALID_VIDEO_ROLES` set)
- `production_server.py` line 1119 (beats-bearing role check `{"intro","win","standalone"}`)
- `production_server.py` line 1168 (same check in `create_video`)
- `Production/tools/storyboard-v2/src/components/VideoSelector.tsx` line 36 (`CANONICAL_ROLES`)

**B0.2.** Document pre-edit count: 5 server + 1 client = 6 actual-role `win` literals (audit verified by Agent B research).

**B0.3.** Confirm coincidental matches (e.g., line 369 `os.environ.get("USERNAME", "win")`) are NOT in the rename scope.

### Phase B — Server handler reverts + new endpoints (symbol-based per Cursor Q1)

**B1.** Stop server (`pkill -f production_server.py`).

**B2.** **Symbol-based handler reverts** (replaces v1's brittle line refs):
- `_handle_phase_suggest_script` — revert `state.videos.phase_b.phase_b_script` read to top-level `state.get("phase_b_script")` (or via `state.phase_b.phase_b_script` post-revert)
- `_auto_assemble_phase_a_stitched` (NEW per Cursor Q1; ~line 14347-14530) — revert all `state.videos.phase_a.{...}` reads/writes to top-level `state.phase_a.{...}` AND ADD `register_asset(asset_type='phase_a_scene', ...)` call after stitch produces output (Agent B finding §10.4 — currently unregistered; v2 fixes inconsistency with `_handle_stitch_bake`)
- `_handle_canonical_stitch` (LD-462; ~line 14401, 14517) — revert top-level reads/writes
- `StateManager._init_files` (NEW per Cursor Q1; line 832-873) — change v2 seed shape to v3:
  - `version: "v3"` (was `"v2"`)
  - `videos.win` → `videos.resolution`
  - Add `completed_mp4_path: null` to each multi-beat partition seed
  - Do NOT seed `phase_a` / `phase_b` partitions in `_init_files` (they're created lazily on first patch via `_handle_v2_module_patch`)
- `StateManager.create_video` (line 1144-1178) — `_VALID_VIDEO_ROLES` becomes `{intro, resolution, standalone}`; phase-role auto-create logic removed (phase data is no longer a "video"); add `completed_mp4_path: null` to multi-beat partition init
- `StateManager.validate_video_role` — accepts only `{intro, resolution, standalone}`
- `StateManager._VALID_VIDEO_ROLES` (line 1081) — restricted to 3 values
- Audit any other `state.videos.phase_a` / `state.videos.phase_b` reads/writes via grep; revert all

**B3.** **Win literal rename** (per Phase B0 audit):
- `production_server.py` lines 853, 854, 1081, 1119, 1168 → `"resolution"`
- `Production/tools/storyboard-v2/src/components/VideoSelector.tsx:36` → `['intro', 'resolution']` (also drops phase_a, phase_b, standalone since this is the multi-event TargetVideoSelector now)

**B4.** **Delete obsolete partition init code per Rule 27:**
- Grep `\.setdefault\("phase_a"` and `\.setdefault\("phase_b"` in `production_server.py`; remove every instance (Agent B noted lines 9454, 9821, 9850, 10548, 10629, 11364, 14519, 14520 from v1 spec §12)

**B5.** **Fix `_handle_use_as_final` hardcoding** (NEW per Agent B finding §10.8; this is in scope because it touches the same partition shape):
- Line 9423: `state.get("videos") or {}).get("intro") or {})` → use `(state.get("videos") or {}).get(scope_video_role, {})`
- Validate `scope_video_role in {intro, resolution, standalone}` per `_VALID_VIDEO_ROLES`

**B6.** **Add new endpoints (milestones):**
- `GET /api/milestones/list` — returns `[{milestone_id, milestone_label, beat_count, completed_mp4_path}]`
- `POST /api/milestones/create` — body `{milestone_id, milestone_label}`; validates `milestone_id` regex + reserved words; creates `Production/Milestones/<milestone_id>/` dir + state.json scaffold; returns 409 on collision
- `POST /api/milestones/load` — body `{milestone_id}`; uses `event_load_lock` (atomic swap); bumps `event_generation`; sets `app.scope_type='milestone'`; cache invalidation matches `_handle_event_load`
- `GET /api/project/list` — returns `{events: [...], milestones: [...]}` for ProjectSelector

**B7.** **Add new endpoints (drain protocol per `ASYNC_QUEUE_DRAIN_PROTOCOL_V1`):**
- `POST /api/admin/drain_start` — sets `app.accept_new_jobs = False`
- `POST /api/admin/drain_end` — sets `app.accept_new_jobs = True`
- `GET /api/admin/inflight_count` — returns count + flag

**B8.** **Wire drain registry at all 17 pin-init sites:**
- After pin capture, check `accept_new_jobs` flag; return 503 if drain active
- After pre-work pin check, register job in `app._inflight_jobs[<job_id>]`
- In `finally`: `app._inflight_jobs.pop(<job_id>, None)`
- `job_id` = `f"{handler_name}_{ts_ms}_{rand_4}"`

**B9.** **Add new endpoints (export pipeline per `BEAT_FINALIZE_ENDPOINT_V1` + `SCENE_ASSEMBLE_ENDPOINT_V1`):**
- `POST /api/beat/finalize` — per spec §3.5 Stage 1
- `POST /api/scene/assemble` — per spec §3.5 Stage 2
- New helper `compute_finalize_args_hash(beat_state, recipe_hash, recipe_version)` in `lib/ffmpeg_stitch.py` (alongside existing `compute_cache_hash` at line 624)

**B10.** **Add `scene_concat_mp4` to `_ACCEPTED_ASSET_TYPES` in `Production/tools/registered_write.py`** (per `ASSET_TYPE_SCENE_CONCAT_V1`).

**B11.** **DELETE old `_handle_export` (line 10999-11069)** per Rule 27. The `/api/export` URL is repurposed: redirect or 410 with migration note pointing to `/api/scene/assemble`.

**B12.** **Update `_handle_event_load` and equivalent milestone-load handler:**
- Cache invalidation per LD-475 (multi-beat partitions only)
- `app.scope_type` set per scope

**B13.** **Update `_handle_video_set_active`:**
- `_VALID_VIDEO_ROLES` change cascades; reject `phase_a`/`phase_b`/`win` with 400 + clear error message including the new valid set

**B14.** **Update `_handle_video_create`:**
- Same role validation

**B15.** **Add new whitelist fields:** `_V2_MODULE_ALLOWED_FIELDS` += `phase_a_stitched_file`, `phase_a_stitched_mtime` (Agent A finding §F)

**B16.** **Codec recipe alignment to LD-284 strict spec** (NEW per Kim's 2026-05-03 re-bake decision). Update `Production/tools/lib/ffmpeg_stitch.py:47-59`:
- `NORMALIZATION_VF_EXPR`: insert `setsar=1:1` into the filter chain (LD-284 explicit SAR)
  - Resulting expression: `"scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1:1,fps=24"`
- `NORMALIZATION_ENCODER_ARGS`: change `"-preset","medium"` → `"-preset","slow"`; add `"-g","48"` after preset
- `NORMALIZATION_RECIPE_HASH = sha256(version + VF + ENCODER)[:16]` recomputes automatically; record old vs new hash in activity log
- **Cache cascade:** every existing `*_normalized.mp4` becomes stale; next `/api/scene/assemble` re-bakes per beat from source (cache miss). Source clips NOT touched.
- **NO LD-284 Directus PATCH** — LD-284 stays as-is; code now matches what LD always specified
- Add an `S5_5D_PHASE_B_CODEC_ALIGNED` activity log row noting old vs new `NORMALIZATION_RECIPE_HASH` for forensic reference

**B17.** **py_compile clean.**

**B18.** **Restart server; `/api/health` 200.**

### Phase C — Apply reverse migration to state.json files

**C0.** **Drain protocol pre-apply** (NEW per Cursor R1):
- `POST /api/admin/drain_start`
- Poll `GET /api/admin/inflight_count` until `inflight_count == 0`, max 60 seconds. Fail-closed if timeout.

**C1.** Confirm Dropbox sync paused (or warn Kim).

**C2.** Run `python3 Production/scripts/migrate_phase_partitions_to_top_level.py --apply`:
- Per-event: snapshot to `.backups/state/<TS>_pre_phase_revision.json`; atomic write of v3-shape state.json; read-back verify `is_already_migrated()`

**C3.** Run `--validate` mode on both events; expect exit 0.

**C4.** `POST /api/admin/drain_end`.

**C5.** Inspect `Event_<N>/.backups/state/`; confirm snapshot exists + sha256-matches pre-migration.

### Phase D — v59 client restructure

**D1.** Update `Production/tools/storyboard-v2/src/state/scope.ts`:
- Rename `activeVideoRole` → `activeTargetVideo`
- Restrict signal value to `'intro' | 'resolution' | 'standalone'` (NOT null per Cursor Q5 fix)
- Add `activeProjectType: 'event' | 'milestone'` signal
- Add `activeMilestoneId: string | null` signal
- **Resolution rule:** when `activeProjectType === 'event'`, signal value is from user selection (intro or resolution). When `activeProjectType === 'milestone'`, signal value is fixed `'standalone'`.

**D2.** Rename `VideoSelector.tsx` → `TargetVideoSelector.tsx`:
- `CANONICAL_ROLES = ['intro', 'resolution']` (drop phase_a, phase_b, win, standalone — standalone is implicit, not selectable)
- Hide entire component when `activeProjectType === 'milestone'`

**D3.** Rename `EventSelector.tsx` → `ProjectSelector.tsx`:
- Lists events + milestones in grouped optgroups
- On select: routes to `/api/event/load` or `/api/milestones/load`
- Updates URL with `?event=<id>` OR `?milestone=<id>`
- "+ New Milestone" prompts for `milestone_id` (validated client-side against regex) + `milestone_label`

**D4.** Update `ScopeBoundary.tsx`:
- On boot, read URL params for `event` OR `milestone`; call appropriate load endpoint
- Hydrate `activeTargetVideo` from `state.active_video` if event scope; fixed `'standalone'` if milestone

**D5.** Update `pathappPatch` (`api/client.ts`):
- Auto-inject `scope_target_video: activeTargetVideo.value` for Beat Gen + Storyboard mutations
- Auto-inject `scope_milestone_id` when milestone scope active
- Skip auto-injection for Phase A/Phase B/Stitcher mutations

**D6.** Restructure `StoryboardTab.tsx`:
- REMOVE `<PhaseProducer phase="b" />` and `<PhaseProducer phase="a" />` siblings (v1 lines 439-442)
- FIX beat list to read from `state.videos[activeTargetVideo.value].beats`
- Storyboard tab content always renders (no null placeholder needed since `activeTargetVideo` always resolves to a value)
- Update existing `ExportButtons` (v1 lines 291-367) to label "Send Out as MP4" and POST to `/api/scene/assemble` with body `{scope_event_id, scope_target_video}`
- Add progress UI for finalize+assemble pipeline (toast on success showing asset_id + cache_stats)

**D7.** Create `Production/tools/storyboard-v2/src/tabs/PhaseATab.tsx`:
- Wraps existing `<PhaseProducer phase="a" />` in a tab pane with header
- Hidden when milestone scope active

**D8.** Create `Production/tools/storyboard-v2/src/tabs/PhaseBTab.tsx`:
- Same pattern, phase="b"
- Hidden when milestone scope active

**D9.** Update `PhaseProducer.tsx`:
- `pickPhaseSlice` reads top-level `state[`phase_${phase}_${suffix}`]` (no change — already correct; fixes itself when state shape reverts)
- Verify hardcoded `Production/Event_1/${...}` paths honor `activeScope.event_id` (cleanup, not blocking)

**D10.** Update `TabBar.tsx`:
- New tab order: `'beat_generator' | 'cropper' | 'storyboard' | 'phase_b' | 'phase_a' | 'stitcher'`
- Disabled states: Phase A/Phase B disabled when milestone scope; Stitcher always enabled (auto-detects mode)

**D11.** Update `app.tsx` `ActivePane()` switch to route the new tab keys + new components.

**D12.** Update `StitcherTab.tsx`:
- Auto-detect mode from `activeProjectType`
- Module mode (event scope): 4 slots intro → phase_a → phase_b → resolution; reads `completed_mp4_path` (multi-beat) or `phase_<a|b>_stitched_file` (phase) per slot
- Standalone mode (milestone scope): 1 slot; reads `state.videos.standalone.completed_mp4_path` from milestone state

**D13.** `BeatGeneratorTab.tsx` (placeholder if not yet built; otherwise add scope check):
- Always operates against `state.videos[activeTargetVideo.value].beats`
- Works in event scope (intro|resolution) AND milestone scope (standalone)

**D14.** `npm run build` clean (no TS errors).

### Phase E — Verification (atomic gate sweep, 33 gates)

All gates must pass before Phase F. New gates added per Cursor Q9 + R1 + R5.

**E1.** `python3 Production/scripts/migrate_phase_partitions_to_top_level.py --validate` exits 0
**E2.** `python3 -m py_compile Production/tools/production_server.py` clean
**E3.** `cd Production/tools/storyboard-v2 && npm run build` clean
**E4.** Server restart; `/api/health` 200; PID start time AFTER last edit (Rule 29)
**E5.** `GET /api/event/current` returns expected shape with `active_video ∈ {intro, resolution}` only
**E6.** `GET /api/video/list` for Event_1 returns `[intro, resolution]` only (no phase_a, phase_b, win, standalone)
**E7.** `GET /api/project/list` returns `{events: [...], milestones: [...]}` shape
**E8.** `POST /api/video/set_active` accepts `intro` and `resolution`; rejects `phase_a`/`phase_b`/`win` with 400 + clear error
**E9.** `POST /api/video/create` same role validation
**E10.** `POST /api/milestones/create` with `{milestone_id: "test_milestone", milestone_label: "Test"}` creates `Production/Milestones/test_milestone/state.json`
**E11.** `POST /api/milestones/create` with invalid milestone_id (e.g., `"_BAD"`, `"event_x"`, uppercase) returns 400
**E12.** `POST /api/milestones/load` with `{milestone_id: "test_milestone"}` swaps active scope; subsequent state reads return milestone state; `app.scope_type='milestone'`
**E13.** State shape probe: read `Production/Event_1/production_state.json` → confirm `state.phase_a.*` fields at top level; confirm `state.videos` has only `{intro, resolution}` (no `phase_a`, `phase_b`, `win`); confirm `version=v3`; confirm `completed_mp4_path` field exists on each multi-beat partition
**E14.** State shape probe: same for Event_2 (Event_2 has no phase data; just confirm `videos` has `{intro, resolution}` not `{intro, win}`)
**E15.** Functional probe: POST a `phase_b_script` update via `_handle_v2_module_patch`; read back via `_handle_v2_event_state`; confirm `state.phase_b.phase_b_script` updated
**E16.** Functional probe: POST a `phase_a_ambient_preset_id` update; same verification
**E17.** **Pipeline probe (NEW for v2):** `POST /api/beat/finalize` with `{event_id, scope_target_video: "intro", beat_id: "beat_01"}` returns `{ok, file_path, cache_hit: false}`; second call returns `cache_hit: true`
**E18.** **Pipeline probe (NEW for v2):** `POST /api/scene/assemble` with `{event_id, scope_target_video: "intro"}` returns `{ok, asset_id, completed_mp4_path}`; verify `state.videos.intro.completed_mp4_path` updated; verify file exists at returned path
**E19.** Browser smoke (DEFERRED but documented):
   - Load Event_1 in v59 client → see ProjectSelector + TargetVideoSelector + 6 tabs in production order
   - Switch TargetVideoSelector to "resolution" → Storyboard + Beat Generator update
   - Click Phase A tab → see Phase A producer
   - Click Phase B tab → see Phase B producer
   - Click "Send Out as MP4" in Storyboard → progress UI → toast with asset_id; switch to Stitcher → intro slot shows MP4
   - Click Stitcher → see 4-slot module mode
   - Switch ProjectSelector to "+ New Milestone" → enter milestone_id → milestone scope loaded → Phase A/B disabled; Stitcher in 1-slot mode; Beat Generator + Storyboard operate against standalone partition
   - Switch back to Event_1 → state preserved
**E20.** LD-474 audit script (`Production/scripts/ld474_audit_active_video.py`) PASSES (regression gate; updated for new role list)
**E21.** Cross-event swap (Event_1 → Event_2 → Event_1) cache-clear log appears 3×
**E22.** Bug 1 retest: Event_1 → Event_2 → Event_1 storyboard images intact
**E23.** Snapshots present at `Event_<N>/.backups/state/<TS>_pre_phase_revision.json`; sha256 matches pre-migration content
**E24.** `_VALID_VIDEO_ROLES` audit: grep server code for any reference to `'phase_a'` or `'phase_b'` or `'win'` as a video_role value; expect ZERO hits in actual-role contexts
**E25.** v59 client tab structure audit: 6 tabs in expected order; Phase A/B are top-level tabs; v59 client `'win'` literal grep returns ZERO actual-role hits
**E26.** **(NEW per Cursor R5)** Component preservation: after `/api/scene/assemble`, source `state.videos[<target>].beats` unchanged (compare hash before/after)
**E27.** **(NEW per Cursor R5)** Component preservation: each `beat_scene` asset created in Phase E17 remains queryable via `find_asset.py`
**E28.** **(NEW per Cursor Q9)** Async pin tuple gate: drain protocol probe — `POST /api/admin/drain_start` then attempt any pinned-handler request → returns 503; `POST /api/admin/drain_end` → requests succeed again
**E29.** **(NEW per Cursor Q9)** Role-literal grep gate: grep `Production/tools/production_server.py` AND `Production/tools/storyboard-v2/src/` for actual-role `'win'` literals; expect ZERO in valid-role contexts (USERNAME default at line 369 OK to remain)
**E30.** Stitcher mode auto-detect: switching ProjectSelector between event and milestone changes Stitcher slot count
**E31.** `find_asset.py` query for recent Phase A / Phase B writes returns expected rows; `iteration_notes` preserved per LD-421
**E32.** `prod_activity_log` row `S5_5D_PHASE_AB_REVISION_COMPLETE` written
**E33.** **(NEW per Kim's 2026-05-03 re-bake decision)** Codec alignment verification: read `Production/tools/lib/ffmpeg_stitch.py:47-59`; assert `NORMALIZATION_VF_EXPR` contains `setsar=1:1`; assert `NORMALIZATION_ENCODER_ARGS` contains `"-preset","slow"` and `"-g","48"`; compute `NORMALIZATION_RECIPE_HASH` and confirm it differs from the pre-edit value; verify Phase E17 cache MISS occurred (proving recipe bump invalidated old caches); verify Phase E18 produced a fresh `scene_concat_mp4` asset registered with the new hash in `iteration_notes`

### Phase F — LD writes + amendments + supersedes

**F1.** Write 12 NEW LDs via `try_post_or_queue` (per Rule 35 schema verification):
- `PHASE_A_TOP_LEVEL_STATE_V1` (HIGH, active)
- `PHASE_B_TOP_LEVEL_STATE_V1` (HIGH, active)
- `MILESTONE_STANDALONE_INDEPENDENT_V1` (HIGH, active)
- `BG_VIDEO_PARTITION_V2` (HIGH, active) — supersedes LD-473
- `VIDEO_ROLE_PER_REQUEST_V2` (HIGH, active) — supersedes LD-474
- `BEAT_FINALIZE_ENDPOINT_V1` (HIGH, active)
- `SCENE_ASSEMBLE_ENDPOINT_V1` (HIGH, active)
- `ASYNC_QUEUE_DRAIN_PROTOCOL_V1` (HIGH, active)
- `ASSET_TYPE_SCENE_CONCAT_V1` (LOW, active)
- `STORYBOARD_SEND_OUT_PROVENANCE_V1` (MEDIUM, active)
- `TARGET_VIDEO_SELECTOR_V1` (MEDIUM, active)
- `TAB_STRUCTURE_PRODUCTION_ORDER_V1` (MEDIUM, active)

**F2.** SUPERSEDE 2 existing LDs (per Cursor Q7):
- LD-473 BG_VIDEO_PARTITION_V1: PATCH `status='superseded'`, `superseded_by_id=<row id of BG_VIDEO_PARTITION_V2>`
- LD-474 VIDEO_ROLE_PER_REQUEST_V1: PATCH `status='superseded'`, `superseded_by_id=<row id of VIDEO_ROLE_PER_REQUEST_V2>`

**F3.** PATCH 5 existing LDs with amendment notes (no status change):
- LD-475 IMAGE_OVERRIDES_CLEAR_ON_EVENT_LOAD_V1: append note about multi-beat-only applicability + milestone load cache invalidation
- LD-477 HANDLER_REFACTOR_VIDEOS_PARTITION_V1: append note about phase_a/b reverting to top-level
- LD-478 IMAGE_OVERRIDES_NESTED_BY_ROLE_V1: append note about restricted role set
- LD-481 VIDEO_SET_ACTIVE_ENDPOINT_V1: append note about restricted enum
- LD-482 VIDEO_CREATE_ENDPOINT_V1: append note about restricted role set

**F4.** PATCH 2 LDs for v2-introduced changes:
- LD-139 STITCH_ARCHITECTURE_MULTI_STAGE: append "v2 implements `/api/beat/finalize` and `/api/scene/assemble` for the first time; reference SCENE_ASSEMBLE_ENDPOINT_V1 for full spec"
- LD-460 ASYNC_JOB_GENERATION_PIN_V1: append note "drain protocol added per ASYNC_QUEUE_DRAIN_PROTOCOL_V1; per-role enforcement of `pinned_video_role` deferred to migration window only"

(LD-284 is NOT PATCHed in v2 — code was aligned to LD-284 instead per Phase B16. No Directus write needed for LD-284.)

**F5.** All writes via `try_post_or_queue` with read-back confirmation per Rule 35.

### Phase G — Closeout

**G1.** `prod_activity_log` row `S5_5D_PHASE_AB_REVISION_COMPLETE` with full 33-gate summary + scope-vs-spec deviation flags + Cursor v6/v7 incorporation notes + `NORMALIZATION_RECIPE_HASH` old/new values from Phase B16 codec alignment.

**G2.** Write S6 handoff stub at `Production/docs/STORYBOARD_V59_S6_HANDOFF.md`.

**G3.** Update `Production/docs/STORYBOARD_V59_S5_5_C_HANDOFF.md` (Beat Generator UI build) — note new architecture: Beat Generator operates on `state.videos[activeTargetVideo.value].beats` with target ∈ `{intro, resolution, standalone}`.

**G4.** Final independent tail-end verification subagent (per a1/a2/b pattern).

**G5.** **Register v2 spec + lessons learned in `prod_reference_docs`** per Rule 15:
- `STORYBOARD_V59_PHASE_AB_REVISION_SPEC_v2.md` — `doc_category: spec`, `is_current: true`
- `LESSONS_LEARNED_May03_2026_v59_Architecture_Revision.md` — `doc_category: lessons_learned`, `is_current: true`
- v1 spec marked `is_current: false`

---

## §5 Files Created / Modified

### Created (NEW)

- `Production/scripts/migrate_phase_partitions_to_top_level.py` — reverse migration script (~280 lines; idempotent + fail-closed + collision-aborting)
- `Production/tools/storyboard-v2/src/tabs/PhaseATab.tsx` — wraps PhaseProducer for top-level tab (~50 lines)
- `Production/tools/storyboard-v2/src/tabs/PhaseBTab.tsx` — same pattern, phase="b" (~50 lines)
- `Production/Milestones/` — new top-level directory (committed to git)
- `Production/docs/STORYBOARD_V59_S6_HANDOFF.md` — S6 prep handoff stub

### Modified

- `Production/tools/production_server.py`:
  - Symbol-based handler reverts: `_handle_phase_suggest_script`, `_auto_assemble_phase_a_stitched`, `_handle_canonical_stitch`
  - `StateManager._init_files` (line 832-873): v3 shape seed
  - `StateManager.create_video` (line 1144-1178): role list + `completed_mp4_path` init
  - `StateManager._VALID_VIDEO_ROLES` (line 1081): restricted to 3 values
  - `_V2_MODULE_ALLOWED_FIELDS` (line 3587-3621): += `phase_a_stitched_file`, `phase_a_stitched_mtime`
  - Win literal rename at lines 853, 854, 1081, 1119, 1168
  - `_handle_use_as_final` (line 9408-9485): role parameterization
  - `_handle_export` (line 10999-11069): DELETED
  - DELETE `state.setdefault("videos", {}).setdefault("phase_a"|"phase_b", ...)` patterns at lines 9454, 9821, 9850, 10548, 10629, 11364, 14519, 14520
  - Wire drain registry at all 17 `pinned_video_role` pin-init sites
  - NEW endpoints: `/api/milestones/list`, `/api/milestones/create`, `/api/milestones/load`, `/api/project/list`, `/api/admin/drain_start`, `/api/admin/drain_end`, `/api/admin/inflight_count`, `/api/beat/finalize`, `/api/scene/assemble`
  - `_handle_event_load`: extended cache invalidation; sets `app.scope_type='event'`
  - Equivalent `_handle_milestone_load` handler

- `Production/tools/lib/ffmpeg_stitch.py`:
  - **CHANGE (Kim 2026-05-03 re-bake decision):** Align `NORMALIZATION_VF_EXPR` and `NORMALIZATION_ENCODER_ARGS` (lines 47-59) to LD-284 strict spec — insert `setsar=1:1`, switch `-preset medium` → `-preset slow`, add `-g 48`. `NORMALIZATION_RECIPE_HASH` recomputes; cache invalidates.
  - NEW: `compute_finalize_args_hash(beat_state, recipe_hash, recipe_version)` helper alongside existing `compute_cache_hash` (line 624)
  - NEW: `FINALIZE_RECIPE_VERSION = "v1"` constant alongside existing `PREVIEW_RECIPE_VERSION`

- `Production/tools/registered_write.py`:
  - `_ACCEPTED_ASSET_TYPES` (line 42-61): += `'scene_concat_mp4'` (per `ASSET_TYPE_SCENE_CONCAT_V1`)

- `Production/scripts/migrate_state_to_videos_partition.py` — original migration script: remove PHASE_A_RE / PHASE_B_RE; add phase_a_*/phase_b_* to TOP_LEVEL_KEEP; rename win → resolution
- `Production/Event_1/production_state.json` — atomic v2→v3 reverse migration (phase_a/phase_b lifted to top-level; win→resolution; `completed_mp4_path` added)
- `Production/Event_2/production_state.json` — atomic v2→v3 (only win→resolution + `completed_mp4_path` add; no phase data)
- `Production/scripts/ld474_audit_active_video.py` — update valid role set
- `Production/tools/storyboard-v2/src/state/scope.ts` — `activeTargetVideo` rename + `activeProjectType` + `activeMilestoneId`
- `Production/tools/storyboard-v2/src/components/VideoSelector.tsx` → renamed `TargetVideoSelector.tsx`
- `Production/tools/storyboard-v2/src/components/EventSelector.tsx` → renamed `ProjectSelector.tsx`
- `Production/tools/storyboard-v2/src/components/ScopeBoundary.tsx`
- `Production/tools/storyboard-v2/src/api/client.ts` — `pathappPatch` auto-injection update
- `Production/tools/storyboard-v2/src/api/endpoints.ts` — new endpoint URLs
- `Production/tools/storyboard-v2/src/components/StoryboardTab.tsx` — Phase A/B sibling removal, `ExportButtons` rewrite for `/api/scene/assemble`
- `Production/tools/storyboard-v2/src/components/phase/PhaseProducer.tsx` — verify reads (likely zero changes)
- `Production/tools/storyboard-v2/src/components/TabBar.tsx` — new tab order + disabled states
- `Production/tools/storyboard-v2/src/app.tsx` — route new tab keys
- `Production/tools/storyboard-v2/src/components/StitcherTab.tsx` — auto-detect mode
- `Production/tools/storyboard-v2/src/components/BeatGeneratorTab.tsx` (if present)
- `Production/docs/STORYBOARD_V59_S5_5_C_HANDOFF.md` — append note about new architecture
- `Production/PIPELINE_BRAIN_v1.md` — section update for new tab structure + state shape + new endpoints (per Rule 15 Reference Docs Registry Sync)
- `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` — note new asset type `scene_concat_mp4`
- `Production/governance/storyboard-producer_governance.md` — update for new tab structure + Send Out pipeline
- `Production/governance/video-producer_governance.md` — update for phase_a/phase_b being top-level

---

## §6 Directus Writes Required

All writes go through `try_post_or_queue` per Rule 35; consult `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` BEFORE composing each payload.

### `prod_locked_decisions`

**POST 12 NEW LDs:** PHASE_A_TOP_LEVEL_STATE_V1, PHASE_B_TOP_LEVEL_STATE_V1, MILESTONE_STANDALONE_INDEPENDENT_V1, BG_VIDEO_PARTITION_V2, VIDEO_ROLE_PER_REQUEST_V2, BEAT_FINALIZE_ENDPOINT_V1, SCENE_ASSEMBLE_ENDPOINT_V1, ASYNC_QUEUE_DRAIN_PROTOCOL_V1, ASSET_TYPE_SCENE_CONCAT_V1, STORYBOARD_SEND_OUT_PROVENANCE_V1, TARGET_VIDEO_SELECTOR_V1, TAB_STRUCTURE_PRODUCTION_ORDER_V1

**PATCH 2 LDs to status=superseded:** LD-473, LD-474

**PATCH 5 LDs with amendment notes:** LD-475, LD-477, LD-478, LD-481, LD-482

**PATCH 2 LDs with v2-introduced changes:** LD-139, LD-460
(LD-284 was previously planned for PATCH; replaced by code alignment in Phase B16. No Directus write for LD-284.)

### `prod_activity_log`

- Phase A complete: `S5_5D_PHASE_A_PRESPEC`
- Phase B0 complete: `S5_5D_PHASE_B0_WIN_AUDIT_COMPLETE` with grep counts
- Phase B complete: `S5_5D_PHASE_B_HANDLER_REVERTS_COMPLETE` with diff stats + new endpoints registered
- Phase B16 complete: `S5_5D_PHASE_B_CODEC_ALIGNED` with old + new `NORMALIZATION_RECIPE_HASH` values
- Phase C complete: `S5_5D_PHASE_C_MIGRATION_APPLIED` with snapshot paths + sha256
- Phase D complete: `S5_5D_PHASE_D_CLIENT_RESTRUCTURE_COMPLETE` with file list
- Phase E gate sweep: `S5_5D_PHASE_E_VERIFICATION_PASS` with all 33 gate results
- Phase F LD writes: `S5_5D_PHASE_F_LDS_REGISTERED` with new + superseded + patched LD IDs
- Phase G closeout: `S5_5D_PHASE_AB_REVISION_COMPLETE` with full session summary

### `prod_preflight_reviews`

- 1 row at session start: `task_type=architectural`, `approved_to_proceed=true`, references this v2 spec
- After Phase G: PATCH `related_activity_log_id` to point at COMPLETE row

### `prod_reference_docs`

- POST: this v2 spec (`STORYBOARD_V59_PHASE_AB_REVISION_SPEC_v2.md`, doc_category=spec, is_current=true)
- POST: lessons learned doc (`LESSONS_LEARNED_May03_2026_v59_Architecture_Revision.md`, doc_category=lessons_learned, is_current=true)
- PATCH: v1 spec (`STORYBOARD_V59_PHASE_AB_REVISION_SPEC_v1.md`) → `is_current=false`

### `prod_assets` (during E17 + E18 verification)

- Per-beat finalize creates `beat_scene` rows
- Scene assemble creates `scene_concat_mp4` rows
- Both via `registered_write.register_asset()` per LD-421/422

---

## §7 Error Cases and Handling

| Failure | Handling |
|---|---|
| Reverse migration script fails on one event but not the other | Halt; restore both events from snapshots; do NOT proceed with handler reverts (state would be inconsistent) |
| Migration `is_already_migrated()` half-true (some fields v3, some v2) | Fail-closed; abort with explicit error pointing at which fields disagree |
| Migration key collision (top-level `phase_a_<key>` already present with different value than `videos.phase_a.<key>`) | Fail-closed; abort; snapshot already taken; manual reconciliation required |
| Drain protocol timeout (jobs still in flight after 60s) | Abort migration; log inflight job ids; surface to Kim for decision (manual kill vs wait longer) |
| Handler revert breaks py_compile | Halt; revert via git per-line until parses; investigate; do not patch on top of broken parse |
| `_V2_MODULE_ALLOWED_FIELDS` already lists phase_a/b at top level | No action needed; schema was already designed for top-level |
| Async pin tuple still includes `video_role: "phase_a"` from in-flight job at migration time | Drain protocol prevents this; if drain fails, abort |
| Client reads `state.videos.phase_a.{...}` and gets `null` post-migration | Expected during transition; client revert (Phase D) prevents this; if it happens, it's a Phase D bug |
| Stitcher mode detection fails (always shows 4-slot even on milestone) | Bug in `activeProjectType` signal; fix via re-render trigger |
| Milestone created with duplicate ID | `POST /api/milestones/create` returns 409 |
| Milestone created with invalid ID (regex/reserved word) | Returns 400 with explicit error |
| ProjectSelector lists events but milestones directory missing | Create `Production/Milestones/` if absent; return empty list (not error) |
| `/api/beat/finalize` cache miss + ffmpeg fails | Fail-closed; no partial cache write; log; return 500 with stderr excerpt |
| `/api/scene/assemble` concurrent on same `(event_id, role)` | Returns 409 (fcntl LOCK_NB pattern); caller retries |
| `/api/scene/assemble` SIZE_BUDGET violation (>1.9 Mbps OR >80 MB) | Fail-closed; log; return 500 with measured values + budget |
| Cursor v7 cross-review surfaces additional gaps | Fold into v3 spec OR document deviation in handoff before paste |

**No silent failures.** Per Rule 19.

---

## §8 Verification

Done when all 33 gates from §4 Phase E pass + 12 new LDs registered + 2 LDs superseded + 7 LDs PATCHed (5 amendments + LD-139 + LD-460; LD-284 NOT PATCHed — code aligned to LD-284 instead per Phase B16) + activity_log rows written + browser smoke verified by Kim (gates E19 + E25) + Cursor v7 cross-review approved (if Kim runs it).

Proof artifacts:
- `git diff` of all file changes
- Migration script dry-run + apply output
- Snapshot file paths + sha256
- Curl probe outputs for all new endpoints (drain_start, drain_end, inflight_count, beat/finalize, scene/assemble, milestones/*, project/list)
- Browser screenshots from Kim hands-on smoke (deferred)
- Directus row IDs for all writes (12 new LDs + 2 supersedes + 8 PATCHes + 2 reference_docs + ≥7 activity_log)
- Final activity_log summary row

---

## §9 Rollback

If anything goes wrong post-Phase C (state files mutated):

1. Stop server
2. Restore both `Production/Event_<N>/production_state.json` from `.backups/state/<TS>_pre_phase_revision.json`
3. `git checkout -- Production/tools/production_server.py` (handler reverts undone)
4. `git checkout -- Production/tools/storyboard-v2/` (client changes undone)
5. **Restart server + health probe** (NEW per Cursor Q10 amendment): `/api/health` 200 + verify state reads work as v2 shape via `GET /api/event/current`
6. Document rollback in `prod_activity_log` action=`S5_5D_ROLLBACK` with reason

If only Phase D (client) goes wrong: `git checkout -- Production/tools/storyboard-v2/` is sufficient; server + state are unchanged.

If only Phase B (server handlers) goes wrong without state migration: `git checkout -- Production/tools/production_server.py` and restart server.

If only Phase F (LDs) goes wrong:
- New LDs: PATCH to `status='superseded'` with `superseded_by_id=null` and notes documenting rollback
- Superseded LDs (LD-473, LD-474): PATCH back to `status='active'` and clear `superseded_by_id`
- Amended LDs: PATCH to remove the new amendment note
- Re-run after fix

---

## §10 Out of Scope (V1)

Things explicitly NOT in this spec (defer to future sessions):

- WaveSurfer.js timeline (LD-472) — Session 6 polish
- Beat Generator UI build (S5.5c) — separate session; this spec only ensures architecture is ready
- Per-event-per-target Playwright matrix expansion
- Stitcher 1-slot UI polish beyond basic mode-switching
- Phase A/B history/diff UI (covered by `find_asset.py`)
- Multiple milestones per single milestone scope (e.g., chapters within a milestone)
- Long-term `pinned_video_role` enforcement in `_check_event_pin` (drain protocol fences migration window only)
- `_auto_assemble_phase_a_stitched` adding `register_asset` call — included in Phase B as it touches the same handler we're reverting
- Migration of existing prod_assets rows to new role taxonomy — they stay as-is; new writes use new taxonomy

---

## §11 Dependencies on Prior Sessions

**Hard dependency on S5.5a1 + S5.5a2 + S5.5b:**
- StateManager helpers (`get_beats`, `mutate_video_state`, etc.) — still load-bearing
- Cache-clear on event load (LD-475) — extended for milestone load
- Scope token + async pin (LD-460) — drain protocol added on top
- 4 endpoints from S5.5b (`/api/event/current`, `/api/video/list`, `/api/video/set_active`, `/api/video/create`) — 3 stay; `/api/video/set_active` gets restricted role enum
- VideoSelector → TargetVideoSelector rename uses S5.5b infrastructure

**Independent of:**
- S5.5c (Beat Generator UI build) — c spec needs minor update for new architecture but doesn't block this revision

**Forward-blocking S6:**
- S6 (parallel-run + cutover) MUST happen AFTER this revision lands
- S6 parallel-run on Event_2 needs the corrected architecture or will exercise the same bugs

---

## §12 Notes for the Executing Session

- This v2 spec incorporates Cursor v6 review findings + Kim's locked decisions (Option A export pipeline; Option B supersede). Send to Cursor v7 BEFORE execution if Kim wants another review pass; otherwise execute directly.
- Per Rule 35: every Directus write consults `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` BEFORE composing payload; uses `try_post_or_queue` from `Production/lib/directus.py`; reads back to confirm
- Per Rule 36: any new Path B-style patches in storyboard-v2 follow §36.1 invariant constraints (the new TargetVideoSelector + ProjectSelector ship as Vite source — not patches — so this is moot)
- Per Rule 19: no shortcuts. The architectural revision is bounded but real; do not stub
- Per Rule 27: delete OLD `videos.phase_a` / `videos.phase_b` partition initialization code; do not leave dead code
- Per Rule 24 confidence annotation: terminal Claude should annotate any inferred claims with `[INFERRED — verify]` tags when uncertain
- Per `feedback_file_links.md`: any Kim-facing previews go through HTML-page-in-Safari pattern, NOT file:// links
- The 6 broken handler sites Agent B identified (lines 14151, 14183, 14583-14584, 14793, 14805, 12481-12482 from v1) become CORRECT automatically when state shape reverts — verify via E15/E16 functional probes
- **`registered_write.py` is at `Production/tools/registered_write.py`** (NOT `scripts/`). v1 spec had this wrong; fixed in v2
- **LD-284 codec spec drift (Kim 2026-05-03 decision: re-bake to strict spec):** v2 ALIGNS `lib/ffmpeg_stitch.py:47-59` to LD-284's strict text (`-preset slow`, `setsar=1:1`, `-g 48`). LD-284 itself is unchanged. Cache invalidates on `NORMALIZATION_RECIPE_HASH` bump; next `/api/scene/assemble` re-encodes from source (~3–5 sec/beat). Source clips untouched.
- **`_handle_use_as_final` role parameterization** (B5) is a small fix inside the same partition logic — included in scope to avoid leaving a known bug behind a renamed surface
- Reuse `lib/ffmpeg_stitch.py` primitives wherever possible: `normalize_for_concat` (line 237), `concat_with_xfade_clips` (line 510), `compute_cache_hash` (line 624) as template for `compute_finalize_args_hash`
- Module ID resolution: `module_id` for `register_asset` is the FK to `prod_modules.id`, NOT the M-number. Easy to wire backwards. Use `_MODULE_MAP` resolver in registered_write.py

---

## §13 Cursor v7 Review Checklist (optional, if Kim wants another pass)

Send Cursor v7 this v2 spec + the following questions:

1. Does the new `/api/beat/finalize` cache hash variable set (§3.5 Stage 1) cover every input that should invalidate the cache? Anything missing?
2. Is `lib/ffmpeg_stitch.compute_cache_hash` a safe template for `compute_finalize_args_hash`, or do per-beat semantics introduce new variables we missed?
3. Code-aligned to LD-284 strict spec in Phase B16 (Kim 2026-05-03 re-bake decision). Verify `lib/ffmpeg_stitch.py:47-59` now contains `-preset slow`, `setsar=1:1`, `-g 48`. Anything else missed in the alignment?
4. Drain protocol: is wiring at all 17 pin-init sites the right granularity, or should it be lifted up to a request middleware?
5. Is the 60-second drain timeout reasonable? Any in-flight job that could legitimately take longer?
6. Is `scene_concat_mp4` the right asset_type, or should we reuse `final_atomic_mp4` and document the role distinction?
7. Single-artifact strategy (`beat_NN_final.mp4` = trimmed + normalized + audio_delay): is this the right choice vs. two cache layers?
8. The `_handle_use_as_final` fix (B5): is this in-scope for v2, or should it be deferred?
9. Verification gates — are 32 enough? Anything we should add?
10. Rollback procedure: any v2-specific edge cases not covered?

Append Cursor v7 findings to this spec as §14 before terminal execution.

---

## §14 Cursor v6 Findings — Folded Into v2 (audit trail)

| Cursor finding | Resolution in v2 | §reference |
|---|---|---|
| Q1 — symbol-based handler list, add `_auto_assemble_phase_a_stitched` + `StateManager._init_files` | DONE | §4 Phase B (B2-B5) |
| Q2 — tighten `is_already_migrated` to 7-field invariant | DONE | §4 Phase A (A2) |
| Q3 RELEASE-BLOCKER — `_handle_export` references nonexistent endpoints | DONE — Option A: build the new pipeline | §3.5, §4 Phase B (B9-B11), 3 new LDs (BEAT_FINALIZE, SCENE_ASSEMBLE, STORYBOARD_SEND_OUT_PROVENANCE) |
| Q4 — milestone endpoints lock contract + cache + input validation | DONE | §3.4, §3.4.1, §4 Phase B (B6, B12) |
| Q5 RELEASE-BLOCKER — milestone target-role contradiction | DONE — `activeTargetVideo='standalone'` (NOT null) | §3.3, §4 Phase D (D1) |
| Q6 — milestone storage naming + backups + ignore policy | DONE | §3.4.1 |
| Q7 — LD-473 + LD-474 supersede (not amend) | DONE | §2 (BG_VIDEO_PARTITION_V2 + VIDEO_ROLE_PER_REQUEST_V2), §4 Phase F (F2) |
| Q8 — cascade list incompleteness | DONE | §5 Modified files (added bootstrap defaults + client constants + governance + reference_docs) |
| Q9 — add 3 hard gates | DONE | §4 Phase E (E26-E29) |
| Q10 — rollback restart + health probe | DONE | §9 (step 5) |
| R1 — async queue drain | DONE | §3.7, §4 Phase B (B7-B8), Phase C (C0), new LD ASYNC_QUEUE_DRAIN_PROTOCOL_V1 |
| R2 — Agent B auto-fix claim | KEEP | Verified via E15/E16 functional probes |
| R3 — `_V2_MODULE_ALLOWED_FIELDS` already aligned | KEEP + 2 field adds (phase_a_stitched_*) | §4 Phase B (B15) |
| R4 — runtime `win` literal audit | DONE | §4 Phase B0 + Phase B (B3), gate E29 |
| R5 — preservation proof path | DONE | §3.5 component preservation, gates E26-E27 |

---

**End of spec v2.**

Cursor v7 review optional (Kim's call). Otherwise hand off to fresh terminal for atomic single-session execution.
