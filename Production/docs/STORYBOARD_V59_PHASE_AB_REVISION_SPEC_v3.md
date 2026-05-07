# Storyboard v59 — Phase A/B Architecture Revision Spec v3

**Date:** 2026-05-03
**Produced by:** tech-spec skill (two-agent Opus debate, v3 cycle incorporating Cursor v7 review)
**Supersedes:** `STORYBOARD_V59_PHASE_AB_REVISION_SPEC_v2.md` (kept as historical reference); v1 also superseded
**Classification:** ARCHITECTURAL revision (state shape change + tab restructure + new milestone concept + new export pipeline + drain protocol)
**Locked decisions:** Decision 1=A (Option A export pipeline), Decision 2=B (supersede LD-473/474), Decision 3=re-bake (LD-284 strict spec, code-aligned), Decision 4=A (drain timeout: pre-flight enumeration, no auto-timeout)

---

## §1 Task

Reverse the architectural mistake from S5.5a1/a2 where `phase_a` and `phase_b` were modeled as video-role siblings of `intro`/`win` under a unified `state.videos.{role}` partition. They are separate top-level state. Browser smoke 2026-05-03 confirmed the unification was wrong.

**v3 changes from v2** (driven by Cursor v7 review):

1–10 unchanged from v2 (state shape, handler reverts, win→resolution, tab restructure, milestone concept, TargetVideoSelector, ProjectSelector, export pipeline, drain protocol, LD work).

**v3-specific corrections (Cursor v7):**

11. **§3.5 Stage 2 redesign (Cursor Beyond #1, RELEASE-BLOCKER FIX):** The v2 spec called `concat_with_xfade_clips` with `fade_between_beats_ms` to "apply crossfades." That helper is stream-copy concat only; it does not apply fades. v3 mirrors the proven `_handle_preview_stitched` pipeline: per-beat finalize → `resolve_pair_fades` → `compute_fade_clamp_per_pair` → per-pair body trim (`trim_body`) + per-pair `render_xfade_pair` → interleaved `[body_0, pair_01, body_1, pair_12, ..., body_N]` parts list → final stream-copy `concat_with_xfade_clips`. Includes wiring `pause_after_ms` (currently dead metadata).

12. **§3.7 drain protocol redesign (Cursor Beyond #2, RELEASE-BLOCKER FIX):** v2's `app._inflight_jobs` invented registry was wrong because most heavy handlers spawn daemon threads and return immediately — the registry would pop while threads were still writing. v3 derives `inflight_count` from the existing module-level registries (`_GPT_JOBS`, `_MAGIC_JOBS`, `_ASSEMBLE_JOBS`) plus a small `_sync_inflight: set[str]` for sync handlers, plus a state-scan for lipsync (special case — tracking lives in `state.beats[bk].lipsync.status`).

13. **Decision 4 = Option A drain timeout policy:** Pre-flight enumeration with explicit abort. If `inflight_count > 0` at `drain_start`, abort migration with explicit list of jobs Kim recognizes (`gpt-stills:<id> (3/9)`, `magic:<scene_key>`, etc.). 60s polling fallback only for sync residue. No auto-timeout for thread-tracked jobs.

14. **Stage 1 hash refinement (Cursor Q1):** Remove `fade_after_ms` and `pause_after_ms` from `finalize_args_hash`. Both are Stage 2 concerns now. Stage 1 hash covers ONLY what Stage 1 actually applies (trim, audio_delay, normalize). Stage 2 hash (`assemble_hash`) covers fades + pauses.

15. **Snapshot shape mandate (Cursor Q2):** v3 mandates building slim snapshots `{beats, image_overrides}` from `videos[<role>]` before calling existing `compute_cache_hash`/`resolve_beat_file` helpers. No library extension.

16. **Decorator pattern (Cursor Q4):** `@with_pin_and_drain(handler_name)` decorator replaces the 17 sites of duplicated pin capture + pre-work check + drain gate + sync-inflight bookkeeping. Single change point.

17. **NORMALIZATION_RECIPE_HASH wording fix (Cursor Q3):** Replace fragile line-cite with "hash over `NORMALIZATION_RECIPE_VERSION` + VF + encoder tuple."

18. **Scope field consistency (Cursor Beyond #3):** Use `scope_event_id` for events, `scope_milestone_id` for milestones. All curl examples normalized to `scope_event_id` (was a mix of `event_id` and `scope_event_id` in v2).

19. **fcntl lock path consistency (Cursor Beyond #4):** Lock at `<scope_root>/scene_assemble_<role>.lock` where `scope_root = event_dir` (event scope) or `Production/Milestones/<id>/` (milestone scope). New helper `_scene_lock_path(scope_type, base, role)`.

20. **§10 / Phase B2 contradiction fix (Cursor Beyond #6):** Strike the `_auto_assemble_phase_a_stitched` `register_asset` bullet from §10 out-of-scope. Phase B2 DOES add it.

21. **§8 typo fix (Cursor Beyond #7):** Browser smoke is gate E19 only. E25 is tab structure audit, not browser smoke.

22. **Provenance wording fix (Cursor Beyond #5):** STORYBOARD_SEND_OUT_PROVENANCE_V1 LD wording clarifies provenance lives in `iteration_notes` + `source_beat_asset_ids` list, NOT `parent_asset_id` (which stays null since it's a list-not-tree linkage).

23. **Verification gate additions (Cursor Q9):** New gates E34 (milestone scene/assemble), E35 (xfade parity vs preview-stitched), E36 (re-send produces distinct concat row), E37 (drain rejects new work while threaded job runs). Total: 37 gates (was 33).

This is a SINGLE-SESSION ATOMIC change per Kim's Q3=A directive 2026-05-03.

---

## §2 Governing Decisions

### Locked decisions this spec respects (must not violate)

| LD | Key | Reason |
|---|---|---|
| LD-139 | STITCH_ARCHITECTURE_MULTI_STAGE | Multi-stage finalize → normalize → concat; v3 implements end-to-end |
| LD-245 | SILCOMP_CONCAT_PATHS_MUST_BE_ABSOLUTE | concat.txt entries must be `p.resolve()` |
| LD-280 | RENDERING_ARCHITECTURE_SINGLE_MP4_ATOMIC_V1 | Module ships as ONE atomic MP4; `final_atomic_mp4` reserved for that |
| LD-281 | NO_RUNTIME_TTS_PERSONALIZATION_V1 | All TTS bakes at production time |
| LD-284 | NORMALIZATION_BEFORE_CONCAT_V1 | Per-segment normalization. **LIVE CODE aligned to LD-284 strict spec in v3** (`-preset slow`, `setsar=1:1`, `-g 48`); LD-284 itself unchanged |
| LD-316 | MODULE_EXIT_AND_PROGRESSION_V1 | Names "Win video" as in-module section |
| LD-375 | PHASE_A_CANONICAL_PIPELINE_V1_20260421 | 5-stage Phase A canonical pipeline |
| LD-376 | PHASE_A_XFADE_RECIPE_V1_20260421 | Phase A fade_in 0.5s + fadeblack 2.5s |
| LD-330 | PHASE_B_AUTHORING_WAVEFORM_FIRST_RESTORE_V1 | WaveSurfer source of truth |
| LD-412 | PHASE_BOUNDARIES_NAMED_OBJECT_V1 | Valid V1 names: `intro, phase_a, phase_b, resolution` — drives win→resolution rename |
| LD-421 / LD-422 | ASSET_FINDABILITY_OVERHAUL_V1 / BUILD_V1 | All media writes via `registered_write.py`; `iteration_notes` indexed |
| LD-423 | STITCH_EDITOR_UNIVERSAL_V1 | N-slot variable assembly (1-slot for milestones; 4-slot for module) |
| LD-456 | SCOPE_VALIDATION_V1 | `_assert_event_scope` + HTTP 409 |
| LD-458 | EVENT_LOAD_GENERATION_LOCK_V1 | Atomic event swap |
| LD-459 | UNIVERSAL_AUTOSAVE_V1 | `.L.json` sidecar |
| LD-460 | ASYNC_JOB_GENERATION_PIN_V1 | Pin tuple at job entry; **PATCHed in v3** to add drain protocol |
| LD-461 | SCOPE_BODY_HELPER_V1 | `_scope_body` normalization |
| LD-462 | PHASE_A_PRODUCER_V1 | v59 Phase A producer (now top-level tab) |
| LD-463 | PHASE_B_PRODUCER_V1 | v59 Phase B producer (now top-level tab) |
| LD-465 | PRODUCTION_MAP_V1 | Encodes the conceptual split |
| LD-466 | EXPORT_TO_STITCHER_V1 | Storyboard "Send Out" produces slot input; LD-466 governs Stitcher consumption |
| LD-467 | MULTI_EVENT_SELECTOR_V1 | Top-of-app selector — extended for milestones |
| LD-471 | STITCHER_FULL_UI_V1 | Stitcher slot reads `completed_mp4_path` |

### Locked decisions this spec amends

| LD | Key | Amendment |
|---|---|---|
| LD-475 | IMAGE_OVERRIDES_CLEAR_ON_EVENT_LOAD_V1 | Multi-beat partitions only; cache invalidation extended for milestone load |
| LD-477 | HANDLER_REFACTOR_VIDEOS_PARTITION_V1 | Phase_a/b handlers continue to use top-level |
| LD-478 | IMAGE_OVERRIDES_NESTED_BY_ROLE_V1 | Restrict nesting to `{intro, resolution, standalone}` |
| LD-481 | VIDEO_SET_ACTIVE_ENDPOINT_V1 | `state.active_video` enum restricted to `{intro, resolution}` |
| LD-482 | VIDEO_CREATE_ENDPOINT_V1 | Valid roles `{intro, resolution, standalone}` |

### Locked decisions this spec SUPERSEDES (per Cursor Q7)

| LD | Key | Reason |
|---|---|---|
| LD-473 | BG_VIDEO_PARTITION_V1 | Semantic contract changed materially. Replaced by `BG_VIDEO_PARTITION_V2`. |
| LD-474 | VIDEO_ROLE_PER_REQUEST_V1 | `_VALID_VIDEO_ROLES` set changes from 5 to 3. Replaced by `VIDEO_ROLE_PER_REQUEST_V2`. |

### Locked decisions this spec PATCHES

| LD | Patch reason |
|---|---|
| LD-139 STITCH_ARCHITECTURE_MULTI_STAGE | v3 implements `/api/beat/finalize` and `/api/scene/assemble` for the first time |
| LD-460 ASYNC_JOB_GENERATION_PIN_V1 | Drain protocol added per ASYNC_QUEUE_DRAIN_PROTOCOL_V1; per-role enforcement deferred |

(LD-284 NOT PATCHed — code aligned to LD-284 instead per Phase B16.)

### Code-spec alignment (LD-284 stays unchanged; live code changes to match it)

LD-284 says `-preset slow`, `setsar=1:1`, `-g 48`. Live recipe at `lib/ffmpeg_stitch.py:47-59` ships `-preset medium`, no setsar, no `-g 48`. **v3 ALIGNS the live code to LD-284's strict spec.**

- `NORMALIZATION_RECIPE_HASH` (hash over `NORMALIZATION_RECIPE_VERSION` + VF + encoder tuple) changes automatically, invalidating every cached `*_normalized.mp4`
- Next `/api/scene/assemble` per beat: cache MISS → re-encode from source at strict recipe (~3–5 sec/beat at `-preset slow`). Source clips untouched.
- Recipe change cascades to ALL callers of `NORMALIZATION_FFMPEG_ARGS`: preview-stitched, timelines, watercolor, finalize. Expected behavior — call out before run.
- Output quality: smaller files at same perceptual quality due to `-preset slow`. Explicit `setsar=1:1` prevents downstream stretching. `-g 48` GOP improves seek precision.

### NEW LDs this spec writes (12)

| Key | Severity | Purpose |
|---|---|---|
| `PHASE_A_TOP_LEVEL_STATE_V1` | HIGH | Phase A state at `state.phase_a.{...}` (top-level), not under `state.videos`. |
| `PHASE_B_TOP_LEVEL_STATE_V1` | HIGH | Same for Phase B. |
| `MILESTONE_STANDALONE_INDEPENDENT_V1` | HIGH | Milestone videos independent of events; `Production/Milestones/<milestone_id>/state.json`. Authored via Beat Generator + Cropper + Storyboard with `activeTargetVideo='standalone'`; exported via Stitcher 1-slot mode. |
| `BG_VIDEO_PARTITION_V2` | HIGH | Replaces LD-473. Partition contains only `{intro, resolution, standalone}`. |
| `VIDEO_ROLE_PER_REQUEST_V2` | HIGH | Replaces LD-474. `_VALID_VIDEO_ROLES = {intro, resolution, standalone}`. |
| `BEAT_FINALIZE_ENDPOINT_V1` | HIGH | Defines `POST /api/beat/finalize` — per-beat finalize+normalize as single artifact. Cached by `finalize_args_hash` covering (resolved input, mtime, trim_start, trim_end, audio_delay, image_overrides slice, lipsync source if applicable, NORMALIZATION_RECIPE_HASH, FINALIZE_RECIPE_VERSION). NOT covered: `fade_after_ms`, `pause_after_ms` — those are Stage 2 concerns. |
| `SCENE_ASSEMBLE_ENDPOINT_V1` | HIGH | Defines `POST /api/scene/assemble` — concat orchestrator mirroring `_handle_preview_stitched`: pairwise `render_xfade_pair` + `trim_body` + interleaved parts list + stream-copy concat. Wires `pause_after_ms` (currently dead metadata). Snapshot-on-start, fcntl lock per `(scope_root, role)`. |
| `ASYNC_QUEUE_DRAIN_PROTOCOL_V1` | HIGH | Drain mechanism: derive `inflight_count` from existing `_GPT_JOBS`/`_MAGIC_JOBS`/`_ASSEMBLE_JOBS` registries + `app._sync_inflight` set + state-scan for lipsync. `app.accept_new_jobs` flag. Admin endpoints. Pre-flight enumeration with abort-on-active. 60s sync residue fallback. |
| `ASSET_TYPE_SCENE_CONCAT_V1` | LOW | Adds `scene_concat_mp4` to `_ACCEPTED_ASSET_TYPES`. |
| `STORYBOARD_SEND_OUT_PROVENANCE_V1` | MEDIUM | Provenance lives in `iteration_notes` + `source_beat_asset_ids` list (NOT `parent_asset_id`, which stays null — list-not-tree linkage). Re-send produces distinct queryable scene assets. |
| `TARGET_VIDEO_SELECTOR_V1` | MEDIUM | Header dropdown restricted to `{intro, resolution}`. Milestone scope: dropdown HIDDEN; signal value resolves to `'standalone'`. |
| `TAB_STRUCTURE_PRODUCTION_ORDER_V1` | MEDIUM | Beat Generator → Cropper → Storyboard → Phase B → Phase A → Stitcher. Phase A and Phase B as top-level tabs. |

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

  "videos": {
    "intro": {
      "video_role": "intro", "video_label": null,
      "beats": {...}, "image_overrides": {...},
      "display_order": [...],
      "completed_mp4_path": null
    },
    "resolution": {
      "video_role": "resolution", "video_label": null,
      "beats": {...}, "image_overrides": {...},
      "display_order": [...],
      "completed_mp4_path": null
    }
  },

  "phase_a": {
    "phase_a_script": "...",
    "phase_a_voice_stem_file": "...", "phase_a_voice_stem_mtime": 0,
    "phase_a_lipsync_file": "...", "phase_a_lipsync_mtime": 0,
    "phase_a_empty_desk_bg_id": "...",
    "phase_a_chipper_flyin_clip_id": "...", "phase_a_chipper_sitting_clip_id": "...", "phase_a_chipper_flyout_clip_id": "...",
    "phase_a_mixed_audio_file": "...", "phase_a_mixed_audio_mtime": 0,
    "phase_a_ambient_preset_id": "...",
    "phase_a_watercolor_cues_json": "[]",
    "phase_a_stitched_file": "...",
    "phase_a_stitched_mtime": 0,
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

### §3.2 Tab structure (production workflow order)

```
[Beat Generator]  [Cropper]  [Storyboard]  [Phase B]  [Phase A]  [Stitcher]
       ↑              ↑            ↑           ↑           ↑           ↑
       └─── reusable for ──────────┘           └─ standalone ─┘     Module
       intro / resolution / standalone         (one event)         assembly
```

| Tab | Role | State path | TargetVideoSelector affects? | Disabled when milestone scope? |
|---|---|---|---|---|
| Beat Generator | Multi-beat authoring | `state.videos[<active_target>].beats` | YES | NO (uses 'standalone') |
| Cropper | Image crop tool | image library | NO | NO |
| Storyboard | Multi-beat sequence editor + "Send Out as MP4" | `state.videos[<active_target>].{beats, image_overrides, display_order, completed_mp4_path}` | YES | NO (uses 'standalone') |
| Phase B | Single-clip Cedric video | `state.phase_b.{...}` | NO | YES |
| Phase A | Single-clip Chipper video | `state.phase_a.{...}` | NO | YES |
| Stitcher | 4-slot module mode + 1-slot standalone mode | reads `completed_mp4_path` per slot | NO | NO (auto-detects 1-slot) |

### §3.3 TargetVideoSelector

- Header dropdown: `Target: [intro] [resolution]`
- Event scope: dropdown shows `{intro, resolution}`; signal matches selection
- Milestone scope: dropdown HIDDEN; signal **resolves to `'standalone'`** (NOT null) so Storyboard + Beat Generator stay enabled
- Phase A + Phase B disabled in milestone scope
- No confirm prompt on switch — partition data auto-saved

### §3.4 ProjectSelector

```
Project: [Event_1 (current)] ▼
  ── Events ──
  ✓ Event_1
    Event_2
    + New Event
  ── Milestones ──
    Milestone: magic_intro_video
    + New Milestone
```

Lock contract: `/api/milestones/load` uses same `event_load_lock` as `/api/event/load`. `event_generation` bumped on milestone load. Cache invalidation matches event load. `app.scope_type: 'event' | 'milestone'` set per scope. `/api/project/list` and `/api/milestones/list` are READ-ONLY.

#### §3.4.1 Milestone ID validation

- Regex: `^[a-z0-9][a-z0-9_-]{2,63}$`
- Reserved words: `{event_*, _tmp_*, _backup_*, archive, default, system, admin, root}` — case-insensitive prefix matches rejected
- Uniqueness: case-insensitive collision returns HTTP 409
- Backup parity: `Production/Milestones/<id>/.backups/state/<TS>_*.json`
- Persistence: `Production/Milestones/` committed to git

### §3.5 "Send Out as MP4" — EXPORT PIPELINE (v3 corrected per Cursor Beyond #1)

#### Stage 1: Per-beat finalize (cached)

```
POST /api/beat/finalize
body: { scope_event_id?, scope_milestone_id?, scope_target_video, beat_id, force_rebuild? }
```

Exactly ONE of `scope_event_id` or `scope_milestone_id` must be present. Validator rejects both-or-neither.

For each beat in `state.videos[<target>].beats` (or milestone's `videos.standalone.beats`):

1. Snapshot beat state at handler entry (per `_handle_preview_stitched` snapshot-on-start invariant, line 11870-11872)
2. Build slim snapshot for hashing (per Cursor Q2): `slim = {"beats": state["videos"][role]["beats"], "image_overrides": state["videos"][role].get("image_overrides", {})}`
3. Compute `finalize_args_hash` over (per Cursor Q1 — Stage 1 ONLY; fades + pauses excluded):
   - `beat_id`
   - resolved input file abs path (via `resolve_beat_file()` — operates on the slim snapshot)
   - resolved input file `mtime`
   - `phase_1.selected_option`
   - `phase_1.trim_start`, `trim_end`
   - `phase_1.audio_delay`
   - `image_overrides[<role>][<beat_id>]` — deterministic JSON serialization (sort_keys=True)
   - `selected_lipsync_path` if `beat.lipsync.status == "completed"`, else null
   - `NORMALIZATION_RECIPE_HASH` (hash over `NORMALIZATION_RECIPE_VERSION` + VF + encoder tuple, per `lib/ffmpeg_stitch.py:65`)
   - `FINALIZE_RECIPE_VERSION` constant ("v1")
4. Cache filename: `{beat_id}_final_{src_md5_10}_{recipe6}_{trim_start_ms}_{trim_end_ms}_{audio_delay_ms}.mp4`
5. Cache directory: `<scope_root>/animation_clips_final/`
6. Sidecar JSON: `<cache_filename>.meta.json` with `{finalize_args_hash, finalize_args, recipe_hash, recipe_version, generated_at, source_path, source_mtime, source_sha256_first_1mb}`
7. **Cache HIT** (sidecar matches): return existing path, `cache_hit: true`
8. **Cache MISS**: invoke `lib/ffmpeg_stitch.normalize_for_concat()` then `lib/ffmpeg_stitch.trim_normalized()` (canonical pipeline order, per Cursor Q7), write atomic tmp+rename, register via `registered_write.register_asset(asset_type='beat_scene', module_id=<resolved>, event_id=<resolved>, beat_id=<beat_id>, role=<role>, parent_asset_id=null, produced_by_skill='beat_finalize_v1', iteration_notes=<template>)`, write sidecar, return path + `cache_hit: false`
9. Per LD-460: full pin tuple at entry + terminal pin check before rename

**Single-artifact strategy:** `beat_NN_final.mp4` is the trimmed-and-audio-delayed AND LD-284-normalized version. One cache, one hash.

#### Stage 2: Scene assemble — MIRRORS preview-stitched orchestration (Cursor Beyond #1 fix)

```
POST /api/scene/assemble
body: { scope_event_id?, scope_milestone_id?, scope_target_video, fade_between_beats_ms?, force_rebuild? }
```

1. `_assert_event_scope` (or milestone equivalent) + LD-460 pin tuple at entry
2. `fcntl.LOCK_EX | LOCK_NB` on `_scene_lock_path(scope_type, scope_root, role)`:
   - Event scope: `<event_dir>/scene_assemble_<role>.lock`
   - Milestone scope: `<milestone_dir>/scene_assemble_<role>.lock`
   - Returns 409 if another assemble is in flight on same `(scope, role)`
3. Snapshot state at handler entry. NEVER re-read mid-pipeline.
4. Resolve `display_order` for `videos[<target>]`. Filter to beats with `phase_1.selected_option` set.
5. **Stage 1 fan-out:** For each `beat_id` in display_order, invoke per-beat finalize internally (in-process call, not HTTP). Collect:
   - `beat_final[i]` = path to finalized MP4
   - `finalize_args_hash[i]` = hash from finalize sidecar
   - `duration[i]` = `ffprobe_duration(beat_final[i])`
   - `pause_after_ms[i]`, `fade_after_ms[i]` from beat state
6. **Compute pair fades** (per `lib/ffmpeg_stitch.py:701-763`):
   - `items_meta = [{file, fade_after_ms, pause_after_ms, duration}, ...]`
   - `requested_pair_fades = resolve_pair_fades(items_meta, fade_between_beats_ms)` — length N-1
   - `clamped_pair_fades = compute_fade_clamp_per_pair(durations, requested_pair_fades)` if N > 1 else `[]`
7. **Build `parts` list** — interleaved per Agent A finding:
   - **Fast path:** if N == 1 OR all clamped fades == 0 AND all `pause_after_ms == 0` → `parts = [beat_final[i] for i in 0..N-1]`
   - **Mixed/xfade path:** for each i in 0..N-1:
     - `head_s = clamped_pair_fades[i-1] / 1000` if `i > 0` and `clamped_pair_fades[i-1] > 0` else `0`
     - `tail_s = clamped_pair_fades[i] / 1000` if `i < N-1` and `clamped_pair_fades[i] > 0` else `0`
     - If `head_s == 0` and `tail_s == 0`: append `beat_final[i]` directly
     - Else: call `trim_body(beat_final[i], body_path, head_s, tail_s)` (helper at `lib/ffmpeg_stitch.py:338-382`); cache filename `{beat_id}_body_{finalize_hash_10}_{head_ms}_{tail_ms}_{recipe6}.mp4`. Append body path.
     - **NEW per Agent A finding §5: pause_after_ms wiring.** If `pause_after_ms[i] > 0` AND not last beat: render silent black filler clip of duration `pause_after_ms[i] / 1000.0` at LD-284 codec recipe to `pause_path = pauses/{beat_id}_pause_{ms}_{recipe6}.mp4`. Append.
     - If `i < N-1` AND `clamped_pair_fades[i] > 0`: `pair_key = md5(f"{src_key_a}+{src_key_b}+{fade_ms}")[:10]`; cache filename `pair_{i:02d}_{pair_key}_{recipe6}.mp4`; call `render_xfade_pair(beat_final[i], beat_final[i+1], clamped_pair_fades[i], pair_path, dur_a=durations[i])`. Append pair path.
8. **Final concat (stream-copy):** call `concat_with_xfade_clips(parts, scene_concat_path)` — this is the misnamed-but-correct stream-copy concat. Inputs are codec-clean (LD-284) so `-c copy` is safe.
9. SIZE_BUDGET gates per LD-280 (≤ 1.9 Mbps, ≤ 80 MB) — match existing `_handle_stitch_bake` pattern (lines 13668-13694)
10. `assemble_hash` = sha256 of:
    ```
    f"recipe:{ASSEMBLE_RECIPE_VERSION}|norm:{NORMALIZATION_RECIPE_HASH}|fade:{fade_between_beats_ms}|order:{','.join(display_order)}"
    + ";".join(f"{bid}:{finalize_args_hash[i]}:{fade_after_ms[i]}:{pause_after_ms[i]}" for i, bid in enumerate(display_order))
    + f"|requested:{requested_pair_fades}|clamped:{clamped_pair_fades}"
    ```
11. Output written atomic tmp+rename to `<scope_root>/<role>/scene_<role>_<assemble_hash>.mp4`
12. Register via `registered_write.register_asset(asset_type='scene_concat_mp4', module_id=<resolved>, event_id=<resolved> OR null, beat_id=null, role=<role>, parent_asset_id=null, produced_by_skill='scene_assemble_v1', iteration_notes=<see below>, colloquial_name=f"{scope_id}_{role}_send_out", tags=['scene_assembly', role, 'multi_beat'])`. **Provenance lives in `iteration_notes` + tags, not `parent_asset_id`** (per Cursor Beyond #5 — list-not-tree linkage).
13. Write path to `state.videos[<target>].completed_mp4_path` via state mutation helper
14. Terminal pin check before state write
15. Returns `{ok: true, asset_id, completed_mp4_path, assemble_hash, beat_count, file_size_bytes, bitrate_bps, cache_stats: {finalize_hits, finalize_misses, body_hits, body_misses, pair_hits, pair_misses, pause_hits, pause_misses}}`

#### `iteration_notes` template

```
[<iso_ts>] Send Out: scene assembly. scope=<event_id|milestone_id>, target_video=<role>,
beats=[<ordered beat_id list>], assemble_hash=<short>,
fade_between_beats_ms=<n>, source_beat_asset_ids=[<ids>],
recipe=<NORMALIZATION_RECIPE_HASH>:<ASSEMBLE_RECIPE_VERSION>,
cache_stats={finalize_hits, finalize_misses, body_hits, body_misses, pair_hits, pair_misses, pause_hits, pause_misses}.
```

#### Component preservation

Verified via Phase E gates:
- Source `state.videos[<target>].beats` unchanged after send-out (E26)
- Each `beat_scene` asset row remains queryable via `find_asset.py` (E27)
- Re-send with one beat changed produces a new `scene_concat_mp4` row with different `assemble_hash` + path + asset_id (E36)

#### Old `_handle_export` behavior

DELETED per Rule 27. The `animation_selections.json` JSON-only manifest is no longer produced. URL `/api/export` returns 410 Gone with migration note.

### §3.6 Stitcher modes

**Module mode (4-slot, Event scope):**
- 4 slots: intro → Phase A → Phase B → resolution
- Multi-beat slots read `state.videos[<role>].completed_mp4_path`
- Phase slots read `state.phase_<a|b>.phase_<a|b>_stitched_file`
- Per-slot ambient_bed (LD-466)
- Bake → final module MP4 via existing `_handle_stitch_bake` (LD-471)

**Standalone mode (1-slot, Milestone scope):**
- 1 slot: standalone milestone MP4
- Reads `state.videos.standalone.completed_mp4_path` from milestone state.json
- Direct export

### §3.7 Async drain protocol — v3 corrected per Cursor Beyond #2 + Q5

**Mechanism (per `ASYNC_QUEUE_DRAIN_PROTOCOL_V1`):**

#### Registries (DERIVE, don't invent)

`inflight_count` is derived from EXISTING module-level registries plus a small new sync set:

1. **`_GPT_JOBS`** ([production_server.py:106](Production/tools/production_server.py:106)): `job_id → {status, results, total}`. Active when `status == "running"`.
2. **`_MAGIC_JOBS`** ([production_server.py:121](Production/tools/production_server.py:121)): `job_id → {status, scene_key, ...}`. Active when `status not in {"done", "error"}`.
3. **`_ASSEMBLE_JOBS`** ([production_server.py:118](Production/tools/production_server.py:118)): `gid → {status, ...}`. Active when `status == "running"`.
4. **`app._sync_inflight: set[str]`** (NEW). Add at sync handler entry; remove in `finally`. Lock-protected via `app._sync_inflight_lock: threading.Lock`.
5. **Lipsync** (special case): live in `state.beats[bk].lipsync.status`. Scan state on demand; active when status in `{"submitting", "polling"}`.

#### `app` additions (in `AppContext.__init__`)

```python
self.accept_new_jobs: bool = True
self._sync_inflight: set[str] = set()
self._sync_inflight_lock: threading.Lock = threading.Lock()
self.scope_type: str = "event"  # 'event' | 'milestone'
```

#### Decorator pattern (Cursor Q4)

```python
def with_pin_and_drain(handler_name: str, *, track_sync: bool = True):
    """Wraps a request-method handler. Replaces 17 sites of duplicated boilerplate.
    - Drain gate: returns 503 if accept_new_jobs is False
    - Pin capture + pre-work pin check
    - Sync-inflight register/unregister (if track_sync=True)
    Sets `_pin` kwarg on the wrapped handler.
    """
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(self, body=None, *a, **kw):
            if not getattr(self.app, "accept_new_jobs", True):
                return self._send_json(503, {
                    "error": "drain_in_progress",
                    "hint": "Server is draining; retry after migration completes.",
                })
            _pin = {
                "pinned_generation": self.app.event_generation,
                "pinned_event_dir": self.app.event_dir,
                "pinned_video_role": (body or {}).get("scope_video_role", "intro"),
                "_handler": handler_name,
            }
            if not self._check_event_pin(_pin, f"{handler_name}_pre_work"):
                return self._send_json(423, {
                    "error": "event_changed_pre_work",
                    "code": "ASYNC_JOB_GENERATION_PIN_V1",
                    "handler": handler_name,
                })
            if track_sync:
                sync_id = f"{handler_name}:{uuid.uuid4().hex[:8]}"
                with self.app._sync_inflight_lock:
                    self.app._sync_inflight.add(sync_id)
                try:
                    return fn(self, body, _pin=_pin, *a, **kw)
                finally:
                    with self.app._sync_inflight_lock:
                        self.app._sync_inflight.discard(sync_id)
            else:
                return fn(self, body, _pin=_pin, *a, **kw)
        return wrapper
    return deco
```

**Decorator application:**
- `track_sync=True` for the 14 drain-critical sync handlers (see Phase B8 list)
- `track_sync=False` for thread-spawning handlers (`_handle_bg_submit_gpt_batch`, `_handle_bg_assemble_group`, `_handle_magic_submit_path`, `_handle_lipsync_submit`) — they DO need the drain gate, but tracking lives in their own registries
- NOT applied to read-only/poll endpoints (`_handle_health`, `_handle_magic_status`, `_handle_bg_poll_gpt_status`, `_handle_bg_poll_assemble_status`, `_handle_voice_profile_get`, etc.) — these MUST stay responsive during drain

#### Endpoints

- `POST /api/admin/drain_start` — sets `accept_new_jobs = False`, returns `{ok: true, inflight_count: <n>, active_jobs: {...}}`
- `POST /api/admin/drain_end` — sets `accept_new_jobs = True`, returns `{ok: true}`
- `GET /api/admin/inflight_count` — full enumeration:

```python
def _handle_admin_inflight_count(self):
    active = {"gpt": [], "magic": [], "assemble": [], "lipsync": [], "sync": []}

    for job_id, info in list(_GPT_JOBS.items()):
        if info.get("status") == "running":
            done = sum(len(v) for v in info.get("results", {}).values())
            total = info.get("total") or 0
            active["gpt"].append({
                "job_id": job_id,
                "name": f"gpt-stills:{job_id}",
                "progress": f"{done}/{total}",
            })

    _MAGIC_TERMINAL = {"done", "error"}
    for job_id, info in list(_MAGIC_JOBS.items()):
        st = info.get("status")
        if st not in _MAGIC_TERMINAL:
            active["magic"].append({
                "job_id": job_id,
                "name": f"magic:{info.get('scene_key','?')}",
                "status": st,
            })

    for gid, info in list(_ASSEMBLE_JOBS.items()):
        if info.get("status") == "running":
            active["assemble"].append({
                "group_id": gid,
                "name": f"assemble:group={gid}",
            })

    try:
        st = self.app.state.read_state()
        for role in ("intro", "resolution", "standalone"):
            beats = ((st.get("videos") or {}).get(role) or {}).get("beats", {})
            for bk, b in beats.items():
                ls = (b or {}).get("lipsync") or {}
                if ls.get("status") in ("submitting", "polling"):
                    active["lipsync"].append({
                        "beat_id": bk,
                        "role": role,
                        "name": f"lipsync:{role}:{bk}",
                        "status": ls["status"],
                    })
    except Exception:
        pass

    with self.app._sync_inflight_lock:
        for sid in sorted(self.app._sync_inflight):
            handler, _, _ = sid.partition(":")
            active["sync"].append({"id": sid, "name": handler})

    total = sum(len(v) for v in active.values())
    return self._send_json(200, {
        "ok": True,
        "inflight_count": total,
        "accept_new_jobs": getattr(self.app, "accept_new_jobs", True),
        "active_jobs": active,
    })
```

#### Migration script flow (Decision 4 = Option A)

```python
def drain_then_apply():
    # 1. Stop accepting new work
    r = http.post(f"{SERVER}/api/admin/drain_start")
    assert r.status_code == 200, f"drain_start failed: {r.text}"

    # 2. Pre-flight: snapshot inflight; ABORT if non-empty
    r = http.get(f"{SERVER}/api/admin/inflight_count")
    body = r.json()
    if body["inflight_count"] > 0:
        active = body["active_jobs"]
        lines = ["MIGRATION ABORTED: in-flight jobs detected."]
        for cls in ("gpt", "magic", "assemble", "lipsync", "sync"):
            for j in active.get(cls, []):
                lines.append(f"  [{cls}] {j.get('name', j)}")
        lines.append("Wait for jobs to complete or cancel them, then retry.")
        http.post(f"{SERVER}/api/admin/drain_end")
        sys.exit("\n".join(lines))

    # 3. 60-second poll for sync residue (fail-closed)
    deadline = time.time() + 60
    while time.time() < deadline:
        r = http.get(f"{SERVER}/api/admin/inflight_count")
        if r.json()["inflight_count"] == 0:
            break
        time.sleep(1.0)
    else:
        active = r.json()["active_jobs"]
        http.post(f"{SERVER}/api/admin/drain_end")
        sys.exit(f"DRAIN TIMEOUT (60s): still in-flight: {active}")

    # 4. Snapshot + apply
    snapshot_state_files()
    apply_migration()

    # 5. Re-open
    http.post(f"{SERVER}/api/admin/drain_end")
```

This fences the migration window. Long-term `pinned_video_role` enforcement is NOT added in this revision.

---

## §4 Implementation Phases (atomic single-session)

### Phase A — Pre-flight + reverse migration script (read-only / dry-run)

**A1.** Read current state.json files for both events; capture pre-state shape.

**A2.** Write `Production/scripts/migrate_phase_partitions_to_top_level.py`:
- Modes: `--dry-run`, `--apply`, `--validate`
- Lift `state.videos.phase_a.{...}` to top-level; same for phase_b; rename `videos.win` → `videos.resolution`; bump `version` v2→v3
- Snapshot to `Production/Event_<N>/.backups/state/<TS>_pre_phase_revision.json` BEFORE write (sha256 logged)
- **`is_already_migrated()` strict invariant:** ALL must hold:
  - `state["version"] == "v3"`
  - `"resolution" in state["videos"]`
  - `"win" not in state["videos"]`
  - `"phase_a" not in state["videos"]`
  - `"phase_b" not in state["videos"]`
  - top-level `state["phase_a"]` exists OR explicitly absent
  - top-level `state["phase_b"]` exists OR explicitly absent
- Fail-closed mixed-version guard
- Key-collision check (abort on first)
- **Drain integration** (NEW per v3): `--apply` mode runs the drain protocol per §3.7 BEFORE snapshot

**A3.** Run script `--dry-run`; verify output.

**A4.** Synthesize fake half-migrated state file; verify fail-closed.

**A5.** Synthesize fake collision state file; verify abort.

### Phase B0 — Pre-revert audit (Cursor R4)

**B0.1.** Grep all live `'win'` literal sites:
- `production_server.py` line 853 (StateManager `_init_files` seed key)
- `production_server.py` line 854 (seed `video_role` field)
- `production_server.py` line 1081 (`_VALID_VIDEO_ROLES` set)
- `production_server.py` line 1119 (beats-bearing role check)
- `production_server.py` line 1168 (same in `create_video`)
- `Production/tools/storyboard-v2/src/components/VideoSelector.tsx` line 36

**B0.2.** Document pre-edit count: 5 server + 1 client = 6 actual-role `win` literals.

**B0.3.** Confirm coincidental matches (line 369 USERNAME default) NOT in scope.

### Phase B — Server handler reverts + new endpoints

**B1.** Stop server (`pkill -f production_server.py`).

**B2.** **Symbol-based handler reverts:**
- `_handle_phase_suggest_script` — revert phase_b reads to top-level
- `_auto_assemble_phase_a_stitched` (~14347-14530) — revert all `state.videos.phase_a.{...}` reads/writes to top-level AND ADD `register_asset(asset_type='phase_a_scene', ...)` after stitch (Agent B finding §10.4)
- `_handle_canonical_stitch` (~14401, 14517) — revert top-level reads/writes
- `StateManager._init_files` (832-873):
  - `version: "v3"` (was `"v2"`)
  - `videos.win` → `videos.resolution`
  - Add `completed_mp4_path: null` to each multi-beat partition seed
  - Do NOT seed `phase_a` / `phase_b` partitions (created lazily)
- `StateManager.create_video` (1144-1178): role list = `{intro, resolution, standalone}`; phase-role auto-create logic removed; add `completed_mp4_path: null`
- `StateManager.validate_video_role`: 3 values
- `StateManager._VALID_VIDEO_ROLES` (1081): 3 values

**B3.** **Win literal rename** at lines 853, 854, 1081, 1119, 1168 → `"resolution"`; `VideoSelector.tsx:36` → `['intro', 'resolution']`.

**B4.** **Delete obsolete partition init code per Rule 27:** grep `\.setdefault\("phase_a"` / `\.setdefault\("phase_b"` and remove (lines 9454, 9821, 9850, 10548, 10629, 11364, 14519, 14520).

**B5.** **Fix `_handle_use_as_final` hardcoding:**
- Line 9423: `state.get("videos") or {}).get("intro") or {})` → `(state.get("videos") or {}).get(scope_video_role, {})`
- Validate `scope_video_role in {intro, resolution, standalone}`

**B6.** **Add new endpoints (milestones):**
- `GET /api/milestones/list`
- `POST /api/milestones/create` — validates `milestone_id` regex + reserved words
- `POST /api/milestones/load` — uses `event_load_lock`; bumps `event_generation`; sets `app.scope_type='milestone'`
- `GET /api/project/list`

**B7.** **Add new endpoints (drain protocol):**
- `POST /api/admin/drain_start`
- `POST /api/admin/drain_end`
- `GET /api/admin/inflight_count` (full enumeration per §3.7)

**B8.** **Implement `@with_pin_and_drain` decorator** (per §3.7) and apply it. Sync handlers (decorator with `track_sync=True`):
- 11862 `_handle_preview_stitched`
- 13588 `_handle_stitch_preview`
- 13611 `_handle_stitch_bake`
- 14347 `_auto_assemble_phase_a_stitched` (called internally — wrap)
- 14107 `_handle_phase_b_mix_audio`
- 14554 `_handle_phase_b_lipsync`
- 13801 `_handle_phase_b_regen_audio`
- 12790 `_handle_timeline_preview_with_sfx`
- 7610 `_handle_bg_submit_flux`
- 6586 `_handle_magic_still`
- 6697 `_handle_magic_video`
- 8060 `_handle_bg_run_local_animation`
- 8362 `_handle_cr_upload`
- 11000 `_handle_export` (will be deleted; decorator irrelevant for the 410 stub)

Thread-spawning handlers (decorator with `track_sync=False`): `_handle_bg_submit_gpt_batch` (7700), `_handle_bg_assemble_group` (7976), `_handle_magic_submit_path` (5179), `_handle_lipsync_submit` (9151).

**B9.** **Add new endpoints (export pipeline):**
- `POST /api/beat/finalize` (per §3.5 Stage 1)
- `POST /api/scene/assemble` (per §3.5 Stage 2 — mirrors `_handle_preview_stitched`)
- New helper `compute_finalize_args_hash(slim_snapshot, beat_id, recipe_hash, recipe_version)` in `lib/ffmpeg_stitch.py` (alongside `compute_cache_hash` at 624)
- New helper `_scene_lock_path(scope_type, base, role)` for lock path resolution

**B10.** **Add `scene_concat_mp4` to `_ACCEPTED_ASSET_TYPES` in `Production/tools/registered_write.py`.**

**B11.** **DELETE old `_handle_export` (10999-11069)** per Rule 27. Replace `/api/export` with HTTP 410 + migration note pointing to `/api/scene/assemble`.

**B12.** **Update `_handle_event_load` and add `_handle_milestone_load`:**
- Cache invalidation per LD-475 (multi-beat partitions)
- `app.scope_type` set per scope

**B13.** **Update `_handle_video_set_active`:** reject `phase_a`/`phase_b`/`win` with 400.

**B14.** **Update `_handle_video_create`:** same role validation.

**B15.** **Whitelist additions:** `_V2_MODULE_ALLOWED_FIELDS` += `phase_a_stitched_file`, `phase_a_stitched_mtime`.

**B16.** **Codec recipe alignment to LD-284 strict spec.** Update `Production/tools/lib/ffmpeg_stitch.py:47-59`:
- `NORMALIZATION_VF_EXPR`: insert `setsar=1:1` (LD-284 explicit SAR)
  - Resulting expression: `"scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1:1,fps=24"`
- `NORMALIZATION_ENCODER_ARGS`: change `"-preset","medium"` → `"-preset","slow"`; add `"-g","48"` after preset
- `NORMALIZATION_RECIPE_HASH` (hash over `NORMALIZATION_RECIPE_VERSION` + VF + encoder tuple) recomputes automatically
- **Cache cascade affects ALL callers** of `NORMALIZATION_FFMPEG_ARGS`: preview-stitched, timelines, watercolor, finalize. Expected behavior — call out in activity log.
- Add `S5_5D_PHASE_B_CODEC_ALIGNED` activity log row noting old vs new hash

**B17.** **Add `app._sync_inflight: set[str]` and `app._sync_inflight_lock`** to `AppContext.__init__`.

**B18.** **py_compile clean.**

**B19.** **Restart server; `/api/health` 200.**

### Phase C — Apply reverse migration

**C0.** **Drain protocol pre-apply (Decision 4 = Option A):**
- `POST /api/admin/drain_start`
- `GET /api/admin/inflight_count` — if `inflight_count > 0`, abort with explicit list (gpt, magic, assemble, lipsync, sync); call `drain_end`; sys.exit
- 60s polling for sync residue — fail-closed if still > 0

**C1.** Confirm Dropbox sync paused.

**C2.** Run `python3 Production/scripts/migrate_phase_partitions_to_top_level.py --apply`.

**C3.** Run `--validate`; expect exit 0.

**C4.** `POST /api/admin/drain_end`.

**C5.** Inspect `Event_<N>/.backups/state/`; confirm snapshot exists + sha256-matches.

### Phase D — v59 client restructure

**D1.** `scope.ts`:
- Rename `activeVideoRole` → `activeTargetVideo`
- Restrict to `'intro' | 'resolution' | 'standalone'` (NOT null)
- Add `activeProjectType: 'event' | 'milestone'`
- Add `activeMilestoneId: string | null`
- Resolution rule: event scope → user selection. Milestone scope → fixed `'standalone'`.

**D2.** `VideoSelector.tsx` → `TargetVideoSelector.tsx`:
- `CANONICAL_ROLES = ['intro', 'resolution']`
- Hide when `activeProjectType === 'milestone'`

**D3.** `EventSelector.tsx` → `ProjectSelector.tsx`:
- Lists events + milestones grouped
- Routes to `/api/event/load` or `/api/milestones/load`
- URL: `?event=<id>` OR `?milestone=<id>`
- "+ New Milestone" prompts for regex-validated id + label

**D4.** `ScopeBoundary.tsx`:
- Read URL params on boot; call appropriate load endpoint
- Hydrate `activeTargetVideo` from `state.active_video` (event) or fixed `'standalone'` (milestone)

**D5.** `pathappPatch` (`api/client.ts`):
- Auto-inject `scope_target_video: activeTargetVideo.value` for Beat Gen + Storyboard mutations
- Auto-inject `scope_milestone_id` when milestone scope active
- Auto-inject `scope_event_id` when event scope active
- Skip auto-injection for Phase A/Phase B/Stitcher mutations

**D6.** `StoryboardTab.tsx`:
- REMOVE `<PhaseProducer phase="b" />` and `<PhaseProducer phase="a" />` siblings
- FIX beat list to read from `state.videos[activeTargetVideo.value].beats`
- Always renders (no null placeholder needed)
- `ExportButtons` → label "Send Out as MP4" → POST to `/api/scene/assemble` with `{scope_event_id OR scope_milestone_id, scope_target_video}`
- Progress UI for finalize+assemble pipeline (toast on success showing asset_id + cache_stats)

**D7.** Create `tabs/PhaseATab.tsx` (~50 lines).

**D8.** Create `tabs/PhaseBTab.tsx` (~50 lines).

**D9.** `PhaseProducer.tsx`: verify reads (likely zero changes — fixes itself when state shape reverts).

**D10.** `TabBar.tsx`: new tab order; Phase A/Phase B disabled when milestone scope.

**D11.** `app.tsx`: route new tab keys.

**D12.** `StitcherTab.tsx`:
- Auto-detect mode from `activeProjectType`
- Module mode: 4 slots intro → phase_a → phase_b → resolution; reads `completed_mp4_path` (multi-beat) or `phase_<a|b>_stitched_file` (phase)
- Standalone mode: 1 slot reads `state.videos.standalone.completed_mp4_path`

**D13.** `BeatGeneratorTab.tsx`: works in event AND milestone scope.

**D14.** `npm run build` clean.

### Phase E — Verification (atomic gate sweep, 37 gates)

**E1.** Migration `--validate` exits 0
**E2.** `python3 -m py_compile Production/tools/production_server.py` clean
**E3.** `cd Production/tools/storyboard-v2 && npm run build` clean
**E4.** Server restart; `/api/health` 200; PID start time AFTER last edit
**E5.** `GET /api/event/current` returns `active_video ∈ {intro, resolution}` only
**E6.** `GET /api/video/list` for Event_1 returns `[intro, resolution]` only
**E7.** `GET /api/project/list` returns `{events: [...], milestones: [...]}`
**E8.** `POST /api/video/set_active` accepts `intro`/`resolution`; rejects others with 400
**E9.** `POST /api/video/create` same role validation
**E10.** `POST /api/milestones/create` with valid id creates `Production/Milestones/test_milestone/state.json`
**E11.** `POST /api/milestones/create` with invalid milestone_id (`"_BAD"`, `"event_x"`, uppercase) returns 400
**E12.** `POST /api/milestones/load` swaps active scope; `app.scope_type='milestone'`
**E13.** State shape Event_1: `state.phase_a.*` top-level; `state.videos` has `{intro, resolution}`; `version=v3`; `completed_mp4_path` field exists
**E14.** State shape Event_2: `videos` has `{intro, resolution}` not `{intro, win}`
**E15.** Functional probe: POST `phase_b_script` update; read back; updated
**E16.** Functional probe: POST `phase_a_ambient_preset_id` update; same
**E17.** **Pipeline probe (Stage 1):** `POST /api/beat/finalize` with `{scope_event_id, scope_target_video: "intro", beat_id: "beat_01"}` returns `{ok, file_path, cache_hit: false}`; second call `cache_hit: true`. Verify `beat_scene` asset registered.
**E18.** **Pipeline probe (Stage 2):** `POST /api/scene/assemble` with `{scope_event_id, scope_target_video: "intro"}` returns `{ok, asset_id, completed_mp4_path, assemble_hash, cache_stats}`; verify `state.videos.intro.completed_mp4_path` updated; verify file exists; verify `scene_concat_mp4` asset registered.
**E19.** Browser smoke (DEFERRED to Kim) — full UI walkthrough per §Notes
**E20.** LD-474 audit script PASSES (updated for new role list)
**E21.** Cross-event swap (Event_1 → Event_2 → Event_1) cache-clear log appears 3×
**E22.** Bug 1 retest: storyboard images intact across event swap
**E23.** Snapshots present at `Event_<N>/.backups/state/<TS>_pre_phase_revision.json`; sha256 matches
**E24.** `_VALID_VIDEO_ROLES` audit: grep server code; ZERO actual-role hits for `'phase_a'`/`'phase_b'`/`'win'`
**E25.** v59 client tab structure audit: 6 tabs in order; Phase A/B top-level; ZERO actual-role `'win'` hits
**E26.** Component preservation (Cursor R5): `state.videos[<target>].beats` unchanged after `/api/scene/assemble` (compare hash before/after)
**E27.** Component preservation (Cursor R5): `beat_scene` assets from E17 remain queryable via `find_asset.py`
**E28.** Drain protocol probe (Cursor Q9): `drain_start` → any pinned-handler request returns 503; `drain_end` → succeeds
**E29.** Role-literal grep (Cursor Q9): ZERO actual-role `'win'` in valid-role contexts
**E30.** Stitcher mode auto-detect: switching scope changes slot count
**E31.** `find_asset.py` query for recent Phase A / Phase B writes; `iteration_notes` preserved
**E32.** `prod_activity_log` row `S5_5D_PHASE_AB_REVISION_COMPLETE` written
**E33.** Codec alignment (Kim 2026-05-03 re-bake decision): read `lib/ffmpeg_stitch.py:47-59`; assert `NORMALIZATION_VF_EXPR` contains `setsar=1:1`; assert `NORMALIZATION_ENCODER_ARGS` contains `"-preset","slow"` and `"-g","48"`; verify `NORMALIZATION_RECIPE_HASH` differs from pre-edit; verify E17 cache MISS occurred; verify E18 produced fresh `scene_concat_mp4` registered with new hash in `iteration_notes`
**E34.** **(NEW v3 per Cursor Q9)** Milestone scene/assemble: `POST /api/milestones/create {milestone_id: "test_assemble", milestone_label: "Test"}`; create one beat in `videos.standalone.beats`; `POST /api/scene/assemble` with `{scope_milestone_id, scope_target_video: "standalone"}`; verify `state.videos.standalone.completed_mp4_path` written to `Production/Milestones/test_assemble/...`; verify lock file at `Production/Milestones/test_assemble/scene_assemble_standalone.lock` was acquired+released
**E35.** **(NEW v3 per Cursor Q9)** XFade parity vs preview-stitched: take a 3-beat sequence with `fade_between_beats_ms=500`; run `_handle_preview_stitched` to produce `preview_stitched.mp4`; run `/api/scene/assemble` to produce `scene_concat.mp4`; assert their assemble pipelines emit IDENTICAL ordered parts list (by file content sha256 of each part) — different final filenames are fine
**E36.** **(NEW v3 per Cursor Q9)** Re-send distinct row: run `/api/scene/assemble` once → `assemble_hash_1`, asset_id_1; modify `beat_03` `phase_1.trim_start`; re-run → `assemble_hash_2 ≠ assemble_hash_1`, asset_id_2 ≠ asset_id_1; verify both rows queryable in `prod_assets` with `is_current=true`
**E37.** **(NEW v3 per Cursor Q9 + Beyond #2)** Drain rejects new work while threaded job runs: spawn a `/api/bg/assemble_group` job (slow); during it, `drain_start`; `inflight_count` shows the assemble job; new `/api/beat/finalize` returns 503; finish the threaded job (or kill); `inflight_count` drops; `drain_end`; verify normal traffic resumes

### Phase F — LD writes + amendments + supersedes

**F1.** Write 12 NEW LDs via `try_post_or_queue`:
- `PHASE_A_TOP_LEVEL_STATE_V1` (HIGH)
- `PHASE_B_TOP_LEVEL_STATE_V1` (HIGH)
- `MILESTONE_STANDALONE_INDEPENDENT_V1` (HIGH)
- `BG_VIDEO_PARTITION_V2` (HIGH) — supersedes LD-473
- `VIDEO_ROLE_PER_REQUEST_V2` (HIGH) — supersedes LD-474
- `BEAT_FINALIZE_ENDPOINT_V1` (HIGH)
- `SCENE_ASSEMBLE_ENDPOINT_V1` (HIGH)
- `ASYNC_QUEUE_DRAIN_PROTOCOL_V1` (HIGH)
- `ASSET_TYPE_SCENE_CONCAT_V1` (LOW)
- `STORYBOARD_SEND_OUT_PROVENANCE_V1` (MEDIUM) — provenance via iteration_notes + source_beat_asset_ids list (NOT parent_asset_id)
- `TARGET_VIDEO_SELECTOR_V1` (MEDIUM)
- `TAB_STRUCTURE_PRODUCTION_ORDER_V1` (MEDIUM)

**F2.** SUPERSEDE 2 LDs: LD-473, LD-474.

**F3.** PATCH 5 LDs with amendment notes: LD-475, LD-477, LD-478, LD-481, LD-482.

**F4.** PATCH 2 LDs:
- LD-139: append "v3 implements `/api/beat/finalize` and `/api/scene/assemble`"
- LD-460: append "drain protocol added per ASYNC_QUEUE_DRAIN_PROTOCOL_V1"

(LD-284 NOT PATCHed — code aligned per Phase B16.)

**F5.** All writes via `try_post_or_queue` with read-back.

### Phase G — Closeout

**G1.** `prod_activity_log` `S5_5D_PHASE_AB_REVISION_COMPLETE` with full 37-gate summary + Cursor v6/v7 incorporation notes + `NORMALIZATION_RECIPE_HASH` old/new.

**G2.** Write S6 handoff stub.

**G3.** Update `STORYBOARD_V59_S5_5_C_HANDOFF.md`.

**G4.** Final independent tail-end verification subagent.

**G5.** Register v3 spec + lessons in `prod_reference_docs`:
- v3 spec: `is_current: true`
- lessons doc: `is_current: true`
- v2 spec: `is_current: false` (SUPERSEDED by v3)
- v1 spec: `is_current: false` (SUPERSEDED — already)

---

## §5 Files Created / Modified

### Created (NEW)

- `Production/scripts/migrate_phase_partitions_to_top_level.py` (~280 lines)
- `Production/tools/storyboard-v2/src/tabs/PhaseATab.tsx` (~50 lines)
- `Production/tools/storyboard-v2/src/tabs/PhaseBTab.tsx` (~50 lines)
- `Production/Milestones/` directory (committed to git)
- `Production/docs/STORYBOARD_V59_S6_HANDOFF.md`

### Modified

- `Production/tools/production_server.py`:
  - Symbol-based handler reverts: `_handle_phase_suggest_script`, `_auto_assemble_phase_a_stitched` (+ register_asset call), `_handle_canonical_stitch`
  - `StateManager._init_files` (832-873): v3 shape seed
  - `StateManager.create_video` (1144-1178): role list + `completed_mp4_path` init
  - `StateManager._VALID_VIDEO_ROLES` (1081): 3 values
  - `_V2_MODULE_ALLOWED_FIELDS` (3587-3621): += `phase_a_stitched_file`, `phase_a_stitched_mtime`
  - Win literal rename at lines 853, 854, 1081, 1119, 1168
  - `_handle_use_as_final` (9408-9485): role parameterization
  - `_handle_export` (10999-11069): DELETED (replaced with HTTP 410 stub)
  - DELETE `state.setdefault("videos", {}).setdefault("phase_a"|"phase_b", ...)` patterns at lines 9454, 9821, 9850, 10548, 10629, 11364, 14519, 14520
  - **NEW:** `@with_pin_and_drain` decorator helper; apply at 14 sync sites + 4 thread-spawning sites (with `track_sync=False`)
  - **NEW:** `app._sync_inflight: set[str]` and `app._sync_inflight_lock: threading.Lock` in `AppContext.__init__`
  - **NEW:** `app.accept_new_jobs: bool = True`, `app.scope_type: str = "event"` in `AppContext.__init__`
  - **NEW endpoints:** `/api/milestones/{list,create,load}`, `/api/project/list`, `/api/admin/{drain_start,drain_end,inflight_count}`, `/api/beat/finalize`, `/api/scene/assemble`
  - `_handle_event_load`: extended cache invalidation; sets `app.scope_type='event'`
  - NEW `_handle_milestone_load` handler

- `Production/tools/lib/ffmpeg_stitch.py`:
  - **CHANGE (codec align):** `NORMALIZATION_VF_EXPR` insert `setsar=1:1`; `NORMALIZATION_ENCODER_ARGS` `medium`→`slow` + add `-g 48`
  - NEW: `compute_finalize_args_hash(slim_snapshot, beat_id, recipe_hash, recipe_version)` helper
  - NEW: `FINALIZE_RECIPE_VERSION = "v1"` constant
  - NEW: `ASSEMBLE_RECIPE_VERSION = "v1"` constant
  - NEW: `_scene_lock_path(scope_type, base, role)` helper

- `Production/tools/registered_write.py`:
  - `_ACCEPTED_ASSET_TYPES` (42-61): += `'scene_concat_mp4'`

- `Production/scripts/migrate_state_to_videos_partition.py`
- `Production/Event_1/production_state.json` (atomic v2→v3)
- `Production/Event_2/production_state.json` (atomic v2→v3)
- `Production/scripts/ld474_audit_active_video.py`
- v59 client files: `scope.ts`, `TargetVideoSelector.tsx` (renamed), `ProjectSelector.tsx` (renamed), `ScopeBoundary.tsx`, `api/client.ts`, `api/endpoints.ts`, `StoryboardTab.tsx`, `PhaseProducer.tsx`, `TabBar.tsx`, `app.tsx`, `StitcherTab.tsx`, `BeatGeneratorTab.tsx`
- `Production/docs/STORYBOARD_V59_S5_5_C_HANDOFF.md`
- `Production/PIPELINE_BRAIN_v1.md`
- `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md`
- `Production/governance/storyboard-producer_governance.md`
- `Production/governance/video-producer_governance.md`

---

## §6 Directus Writes Required

All via `try_post_or_queue` per Rule 35.

### `prod_locked_decisions`

- POST 12 NEW LDs (see §2)
- PATCH 2 LDs to `status=superseded`: LD-473, LD-474
- PATCH 5 LDs with amendment notes: LD-475, LD-477, LD-478, LD-481, LD-482
- PATCH 2 LDs with v3-introduced changes: LD-139, LD-460

### `prod_activity_log`

- `S5_5D_PHASE_A_PRESPEC`
- `S5_5D_PHASE_B0_WIN_AUDIT_COMPLETE`
- `S5_5D_PHASE_B_HANDLER_REVERTS_COMPLETE`
- `S5_5D_PHASE_B_CODEC_ALIGNED` with old + new `NORMALIZATION_RECIPE_HASH`
- `S5_5D_PHASE_B_DRAIN_PROTOCOL_LIVE` with decorator-application count
- `S5_5D_PHASE_C_DRAIN_PRECHECK_PASS` with active_jobs snapshot (expected empty)
- `S5_5D_PHASE_C_MIGRATION_APPLIED` with snapshot paths + sha256
- `S5_5D_PHASE_D_CLIENT_RESTRUCTURE_COMPLETE`
- `S5_5D_PHASE_E_VERIFICATION_PASS` with all 37 gate results
- `S5_5D_PHASE_F_LDS_REGISTERED`
- `S5_5D_PHASE_AB_REVISION_COMPLETE`

### `prod_preflight_reviews`

- 1 row at session start
- After Phase G: PATCH `related_activity_log_id`

### `prod_reference_docs`

- POST: v3 spec, `is_current=true`
- POST: lessons learned, `is_current=true`
- PATCH: v2 spec → `is_current=false`
- PATCH: v1 spec → `is_current=false`

### `prod_assets`

- E17: `beat_scene` rows
- E18, E34, E36: `scene_concat_mp4` rows
- All via `registered_write.register_asset()` per LD-421/422

---

## §7 Error Cases and Handling

| Failure | Handling |
|---|---|
| Migration script fails on one event but not the other | Halt; restore from snapshots |
| Migration `is_already_migrated()` half-true | Fail-closed; abort with explicit error |
| Migration key collision | Fail-closed; abort; manual reconciliation |
| **Drain pre-flight: `inflight_count > 0`** | **Abort with explicit list ([gpt] gpt-stills:..., [magic] magic:..., [assemble] ..., [lipsync] ..., [sync] ...). Kim waits or kills, retries.** |
| Drain 60s sync residue timeout | Fail-closed; abort with active list |
| Handler revert breaks py_compile | Halt; revert per-line |
| `_V2_MODULE_ALLOWED_FIELDS` already lists phase_a/b at top level | No action |
| In-flight job has `pinned_video_role: "phase_a"` at migration time | Drain protocol prevents this |
| Client reads `state.videos.phase_a.{...}` and gets null | Phase D bug — fix |
| Stitcher mode detection fails | Bug in `activeProjectType` signal |
| Milestone duplicate ID | Returns 409 |
| Invalid milestone ID | Returns 400 |
| Milestones directory missing | Create if absent; return empty list |
| `/api/beat/finalize` ffmpeg fails | Fail-closed; no partial cache write; 500 |
| `/api/scene/assemble` concurrent on same `(scope, role)` | Returns 409 (fcntl LOCK_NB) |
| `/api/scene/assemble` SIZE_BUDGET violation | Fail-closed; 500 with measured values |
| `/api/scene/assemble` xfade renders fail mid-pipeline | Fail-closed; clean up partial body/pair files; 500 |
| Job registry leak (existing smell) | v3 documents but doesn't fix; use `restart server` if registries grow large |
| Daemon thread crashes silently | v3 wraps known thread bodies in `try/finally` setting terminal status to `"error"` (Agent B finding §10.2) |
| `_handle_bg_submit_gpt_batch` outer crash | v3 wraps `_run_job` body in `try/finally` to set `_GPT_JOBS[id]["status"]="error"` (Agent B finding §10.2) |
| Cursor v8 surfaces additional gaps | Fold into v4 OR document deviation |

**No silent failures.** Per Rule 19.

---

## §8 Verification

Done when all 37 gates from §4 Phase E pass + 12 new LDs registered + 2 LDs superseded + 7 LDs PATCHed (5 amendments + LD-139 + LD-460; LD-284 NOT PATCHed) + activity_log rows written + browser smoke (E19 ONLY — E25 is tab structure audit, not browser smoke) verified by Kim + Cursor v8 cross-review approved (if Kim runs it).

Proof artifacts:
- `git diff` of all file changes
- Migration script dry-run + apply output
- Snapshot file paths + sha256
- Curl probe outputs for all new endpoints
- Browser screenshots (deferred to Kim)
- Directus row IDs for all writes
- `NORMALIZATION_RECIPE_HASH` old + new values
- `assemble_hash` + `cache_stats` from E18
- Final activity_log summary row

---

## §9 Rollback

If post-Phase C state files mutated:

1. Stop server
2. Restore both `Production/Event_<N>/production_state.json` from snapshots
3. `git checkout -- Production/tools/production_server.py`
4. `git checkout -- Production/tools/storyboard-v2/`
5. `git checkout -- Production/tools/lib/ffmpeg_stitch.py` (reverts B16 codec alignment)
6. `git checkout -- Production/tools/registered_write.py` (reverts asset_type addition)
7. **Restart server + health probe**: `/api/health` 200 + verify state via `GET /api/event/current`
8. **Optional milestone cleanup:** if `Production/Milestones/test_assemble/` etc. created during Phase E, delete (do NOT touch real milestone dirs Kim authored before this session)
9. Document rollback in `prod_activity_log` `S5_5D_ROLLBACK`

If only Phase D: `git checkout -- Production/tools/storyboard-v2/`.

If only Phase B (no state migration): `git checkout -- Production/tools/{production_server.py,lib/ffmpeg_stitch.py,registered_write.py}` and restart.

If only Phase F: PATCH new LDs to superseded; PATCH LD-473/474 back to active; PATCH amended LDs to remove notes.

---

## §10 Out of Scope (V1)

- WaveSurfer.js timeline (LD-472) — Session 6
- Beat Generator UI build (S5.5c) — separate session
- Per-event-per-target Playwright matrix expansion
- Stitcher 1-slot UI polish beyond basic mode-switching
- Phase A/B history/diff UI (covered by `find_asset.py`)
- Multiple milestones per single milestone scope
- Long-term `pinned_video_role` enforcement in `_check_event_pin`
- Migration of existing `prod_assets` rows to new role taxonomy
- Job registry leak fix (LRU cap, TTL sweep) — Agent B finding §10.1; deferred
- `_handle_bg_submit_flux` thread-ification — Agent B finding §10.4; deferred (still synchronous, still blocks for ~30s, but `@with_pin_and_drain` decorator wraps it)
- Lipsync registry promotion (currently lives in state.json) — Agent B finding §10.5; deferred

(NOTE: `_auto_assemble_phase_a_stitched` adding `register_asset` IS in scope — see Phase B2. v2 had a contradictory bullet here; struck per Cursor Beyond #6.)

---

## §11 Dependencies on Prior Sessions

**Hard dependency on S5.5a1 + S5.5a2 + S5.5b:**
- StateManager helpers — load-bearing
- Cache-clear on event load (LD-475) — extended for milestone load
- Scope token + async pin (LD-460) — drain protocol added on top
- 4 endpoints from S5.5b — 3 stay; `/api/video/set_active` gets restricted enum

**Independent of:** S5.5c

**Forward-blocking S6:** Must land before S6 starts.

---

## §12 Notes for the Executing Session

- v3 spec incorporates Cursor v6 + Cursor v7 findings + Kim's locked decisions (Option A export pipeline; supersede LD-473/474; LD-284 re-bake; pre-flight drain enumeration). Send to Cursor v8 BEFORE execution if Kim wants another pass; otherwise execute directly.
- Per Rule 35: every Directus write consults schema reference; uses `try_post_or_queue` with read-back
- Per Rule 19: no shortcuts
- Per Rule 27: delete OLD partition init code; do not leave dead code
- Per Rule 24: annotate inferred claims with `[INFERRED — verify]`
- Per `feedback_file_links.md`: Kim-facing previews use HTML-page-in-Safari, NOT file:// links
- The 6 broken handler sites Agent B identified become CORRECT automatically when state shape reverts — verify via E15/E16
- **`registered_write.py` is at `Production/tools/registered_write.py`** (NOT `scripts/`). v1 had this wrong.
- **LD-284 codec drift (Kim 2026-05-03 re-bake decision):** v3 ALIGNS `lib/ffmpeg_stitch.py:47-59` to LD-284 strict text. LD-284 itself unchanged. Cache invalidates. Source clips untouched.
- **Stage 2 pipeline canonical order** (Cursor Q7): `normalize_for_concat → trim_normalized` per beat, then pairwise `render_xfade_pair` + `trim_body` + interleaved parts list + `concat_with_xfade_clips` (stream-copy concat).
- **Stage 2 pipeline mirrors `_handle_preview_stitched`** at [production_server.py:11862-12210](Production/tools/production_server.py:11862). Do NOT mirror `_handle_canonical_stitch` — it has cumulative-offset xfade drift bug (Agent A flagged).
- **`pause_after_ms` is currently dead metadata.** v3 wires it: insert silent black filler clip between body and pair clips. Without v3 wiring, the field stays orphaned.
- **Drain protocol does NOT invent a parallel registry.** Derives from `_GPT_JOBS`/`_MAGIC_JOBS`/`_ASSEMBLE_JOBS` + `app._sync_inflight` + state.beats lipsync scan. v2's `_inflight_jobs` invention was wrong.
- **Decorator pattern `@with_pin_and_drain`** replaces 17 boilerplate sites. Pure refactor + drain gate + sync register.
- **`_handle_use_as_final` role parameterization** (B5) included to avoid leaving a known bug behind a renamed surface.
- Reuse `lib/ffmpeg_stitch.py` primitives: `normalize_for_concat` (237), `trim_normalized` (317), `render_xfade_pair` (454), `concat_with_xfade_clips` (510, stream-copy), `resolve_pair_fades` (701), `compute_fade_clamp_per_pair` (722), `trim_body` (338), `compute_cache_hash` (624) as template for `compute_finalize_args_hash`.
- Module ID for `register_asset` is FK to `prod_modules.id`, NOT M-number. Use `_MODULE_MAP` resolver.
- All curl examples normalized to `scope_event_id` + `scope_target_video` (was inconsistent in v2).

---

## §13 Cursor v8 Review Checklist (optional)

Send Cursor v8 this v3 spec + the following questions:

1. **Stage 2 pipeline correctness:** Does §3.5 Stage 2 correctly mirror `_handle_preview_stitched`? Specifically the interleaved parts list `[body_0, pair_01, body_1, pair_12, body_2, ..., body_N]` with body trimming + per-pair xfade rendering. Anything missed from preview-stitched orchestration?
2. **`pause_after_ms` wiring:** v3 introduces silent-black filler clips. Is the cache filename + LD-284-recipe rendering approach correct? Edge case: what if pause_after_ms is set on the LAST beat? (Currently v3 skips it on last beat — verify that matches intent.)
3. **`assemble_hash` completeness:** Covers per-beat finalize_args_hash + fade_after_ms + pause_after_ms + requested + clamped pair fades + display_order. Anything missing?
4. **`finalize_args_hash` minimalism (Cursor Q1 fold):** v3 EXCLUDES fade_after_ms and pause_after_ms (Stage 2 concerns). Is this correct given Stage 2 design?
5. **Drain enumeration completeness:** Does the `_handle_admin_inflight_count` implementation cover every drain-critical work source? Specifically: does the lipsync state-scan miss any roles (`{intro, resolution, standalone}` covered) or any state files that aren't currently loaded?
6. **`@with_pin_and_drain` decorator coverage:** Are the 14 sync handlers + 4 thread-spawning handlers the right set? Anything wrongly classified?
7. **Lock path for milestones:** `_scene_lock_path` returns event vs milestone path. Edge case: what if a milestone is created mid-assemble (race)?
8. **Job registry leak smell (Agent B §10.1):** Documented as deferred. Should v3 add at minimum a `S5_5D_DRAIN_PROTOCOL_NOTE` activity log warning Kim about long-running server memory growth?
9. **37 verification gates:** Anything missing? Especially around the new pause_after_ms wiring (is there a gate testing it works?).
10. **Rollback for `lib/ffmpeg_stitch.py`:** §9 step 5 reverts B16 codec alignment via `git checkout`. Does `NORMALIZATION_RECIPE_HASH` revert correctly? (It's computed at module import time; does Python re-import on next request, or do we need explicit server restart?)

Append findings to this spec as §16 before terminal execution.

---

## §14 Cursor v6 Findings — Folded Into v2 (audit trail, kept)

| Finding | Resolution | Section |
|---|---|---|
| Q1 — symbol-based handler list | DONE | §4 Phase B |
| Q2 — tighten `is_already_migrated` | DONE | §4 Phase A |
| Q3 RELEASE-BLOCKER — export endpoints don't exist | DONE — Option A | §3.5, Phase B9 |
| Q4 — milestone endpoints contract | DONE | §3.4, Phase B6 |
| Q5 RELEASE-BLOCKER — milestone target-role contradiction | DONE — `'standalone'` resolution | §3.3, Phase D1 |
| Q6 — milestone storage validation | DONE | §3.4.1 |
| Q7 — supersede LD-473 + LD-474 | DONE | §2 supersedes |
| Q8 — cascade list | DONE | §5 |
| Q9 — 3 hard gates | DONE | E26-E29 |
| Q10 — rollback restart + health | DONE | §9 |
| R1 — async queue drain | DONE | §3.7 |
| R2 — Agent B auto-fix | KEEP | E15/E16 |
| R3 — `_V2_MODULE_ALLOWED_FIELDS` aligned | KEEP + 2 fields | Phase B15 |
| R4 — runtime `win` literal audit | DONE | Phase B0 + Phase B3, gate E29 |
| R5 — preservation proof | DONE | gates E26-E27 |

---

## §15 Cursor v7 Findings — Folded Into v3 (audit trail, NEW)

| Finding | Resolution in v3 | Section |
|---|---|---|
| Q1 — fade_after_ms / pause_after_ms in finalize hash | REMOVED from Stage 1 hash; folded into Stage 2 `assemble_hash` | §3.5 Stage 1 step 3, §3.5 Stage 2 step 10 |
| Q2 — snapshot shape mismatch | Mandate slim `{beats, image_overrides}` snapshot before calling helpers | §3.5 Stage 1 step 2 |
| Q3 — NORMALIZATION_RECIPE_HASH wording | Replaced fragile line-cite with "hash over `NORMALIZATION_RECIPE_VERSION` + VF + encoder tuple" | §2 code-spec alignment, §3.5 Stage 1 |
| Q4 — middleware vs duplicated checks | `@with_pin_and_drain` decorator | §3.7, Phase B8 |
| Q5 RELEASE-BLOCKER — 60s timeout vs 600s GPT | Decision 4=A: pre-flight enumeration with explicit abort + 60s sync residue fallback only | §3.7, Phase C0 |
| Q6 — `scene_concat_mp4` asset type | APPROVED — KEPT | §2 LDs |
| Q7 — single-artifact pipeline order | Spec mandates `normalize_for_concat → trim_normalized` per beat | §3.5 Stage 1, §12 notes |
| Q8 — `_handle_use_as_final` fix | KEPT in scope | Phase B5 |
| Q9 — add 4 gates | E34 milestone assemble, E35 xfade parity, E36 re-send distinct row, E37 drain-during-active-job | Phase E |
| Q10 — rollback edge cases | Added milestone dir cleanup note | §9 step 8 |
| Beyond #1 RELEASE-BLOCKER — `concat_with_xfade_clips` doesn't xfade | Stage 2 redesigned to mirror `_handle_preview_stitched`: pairwise `render_xfade_pair` + `trim_body` + interleaved parts + stream-copy concat | §3.5 Stage 2 |
| Beyond #2 RELEASE-BLOCKER — drain vs daemon threads | Derive `inflight_count` from existing registries + `_sync_inflight` + state-scan for lipsync. NO `_inflight_jobs` invention. | §3.7 |
| Beyond #3 — scope field consistency | All curl examples use `scope_event_id` + `scope_target_video`. New endpoints accept `scope_event_id` XOR `scope_milestone_id`. | §3.5, Phase E curl examples |
| Beyond #4 — fcntl lock for milestones | New helper `_scene_lock_path(scope_type, base, role)` | §3.5 Stage 2 step 2 |
| Beyond #5 — `parent_asset_id=null` vs "linkage" | LD wording clarified: provenance via `iteration_notes` + `source_beat_asset_ids` list (NOT FK tree) | §2 STORYBOARD_SEND_OUT_PROVENANCE_V1 |
| Beyond #6 — §10 contradicts Phase B2 | Struck `_auto_assemble_phase_a_stitched` bullet from §10 | §10 |
| Beyond #7 — §8 E19/E25 typo | Browser smoke is E19 only; E25 is tab audit | §8 |

---

**End of spec v3.**

Cursor v8 review optional. Otherwise hand off to fresh terminal for atomic single-session execution.
