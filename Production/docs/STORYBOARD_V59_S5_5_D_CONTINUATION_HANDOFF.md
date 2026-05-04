# Storyboard v59 — S5.5d Continuation Handoff

**Created:** 2026-05-03
**Status:** PARTIAL execution — clean checkpoint at end of Phase B partial
**Predecessor:** S5.5b (preflight #196 clean) → S5.5d started here (preflight #197)
**Successor:** S5.5d-cont (recommended fresh terminal session)

---

## Why a continuation handoff

S5.5d session was launched in autonomous mode against v3 spec (`STORYBOARD_V59_PHASE_AB_REVISION_SPEC_v3.md`). On honest scope realism, the session completed Phases 0, A, B0, and a coherent subset of Phase B. The remaining Phase B work (4 milestone endpoints + 3 admin/drain endpoints + 2 export-pipeline endpoints + decorator + 18 sites) plus full Phase D (12+ TypeScript files + 2 new tabs) plus 37-gate live verification realistically exceeds one session. Per CLAUDE.md Rule 19 ("no error paths"), halting at this clean checkpoint is preferred over leaving Phase B half-applied.

**The system is in a SAFE checkpoint state:** all py_compile checks pass; no state files mutated; server is stopped per Phase B1.

---

## What's done (do NOT redo)

### Phase 0 — Preflight + reference docs (DONE)

- `prod_preflight_reviews` row **id=197**, `task_id="s5_5d-v59-phase-ab-revision-20260503"`, approved_to_proceed=true, related_activity_log_id=1477
- `prod_reference_docs`:
  - **id=188** → v1 spec (is_current=false, status=superseded, supersedes none, superseded_by 189)
  - **id=189** → v2 spec (is_current=false, status=superseded, supersedes 188, superseded_by 190)
  - **id=190** → v3 spec (is_current=true, status=active, supersedes 189) ← **source of truth**
  - **id=191** → lessons learned (is_current=true, status=active)
- `prod_activity_log`:
  - **id=1477** S5_5D_PHASE_A_PRESPEC
  - **id=1478** S5_5D_SESSION_PARTIAL_CHECKPOINT (full status snapshot)

### Phase A — Reverse migration script (DONE, NOT YET APPLIED)

`Production/scripts/migrate_phase_partitions_to_top_level.py` (~440 lines). Verified:
- py_compile clean
- `--dry-run` PASSES on real `Production/Event_1/production_state.json` and `Production/Event_2/production_state.json`
  - Event_1: would lift phase_a (13 keys) + phase_b (6 keys) to top-level, rename win→resolution, seed completed_mp4_path
  - Event_2: would rename win→resolution, seed completed_mp4_path (no phase_a/b to lift)
- Synthetic half-state correctly fails-closed via Cursor v6 Q2 strict 7-field invariant
- Synthetic collision (top-level phase_a present pre-migration) correctly fails-closed
- `--validate` correctly returns non-zero against v2 state (because target is v3)
- Drain-protocol integration in `--apply` mode (calls `/api/admin/{drain_start, drain_end, inflight_count}`); `--skip-drain` flag bypasses for offline migration

### Phase B0 — Win-literal audit (DONE)

5 server + 1 client = 6 actual-role 'win' literals found:
- `production_server.py:853` (state seed key)
- `production_server.py:854` (state seed `video_role`)
- `production_server.py:1081` (`_VALID_VIDEO_ROLES` set)
- `production_server.py:1119` (mutate_video_state branch)
- `production_server.py:1168` (create_video branch)
- `Production/tools/storyboard-v2/src/components/VideoSelector.tsx:36` (CANONICAL_ROLES)
- `production_server.py:369` is `os.environ.get("USERNAME", "win")` — coincidental Windows username default, **NOT in scope**

### Phase B partial (DONE — these are coherent, do NOT revert)

| Step | Status | What |
|---|---|---|
| B1 | DONE | Server stopped (`pkill -f Production/tools/production_server.py`); lsof -ti:5111 returns nothing |
| B2 partial | DONE | `_init_files` v2→v3 shape with completed_mp4_path; `mutate_video_state` v3 partition init; `create_video` removed phase_a/b auto-create; `_auto_assemble_phase_a_stitched` _apply lifts to top-level; `_handle_phase_suggest_script` reads top-level phase_b |
| B3 | DONE | `_VALID_VIDEO_ROLES` = {intro, resolution, standalone} |
| B10 | DONE | `registered_write._ACCEPTED_ASSET_TYPES` += `'scene_concat_mp4'` |
| B11 | DONE | `_handle_export` replaced with HTTP 410 stub pointing to `/api/scene/assemble` |
| B12 partial | DONE (event_load) | `_handle_event_load` sets `app.scope_type='event'` + `app.active_milestone_id=None` |
| B16 | DONE | `lib/ffmpeg_stitch.py` codec aligned to LD-284 strict: `-preset slow`, `setsar=1:1`, `-g 48`. NORMALIZATION_RECIPE_VERSION v2→v3. NORMALIZATION_RECIPE_HASH `8e9da052b166895a` → `f3f39a6702aaf001` |
| B17 | DONE | `AppContext.__init__` adds `accept_new_jobs:bool=True`, `_sync_inflight:set[str]`, `_sync_inflight_lock:threading.Lock`, `scope_type:str='event'`, `active_milestone_id`, `milestone_dir` |

All edits compile clean (py_compile production_server.py + lib/ffmpeg_stitch.py + registered_write.py + migration script).

---

## What remains (this is the continuation work)

### Phase B remaining (must complete BEFORE server restart)

**B5** — `_handle_use_as_final` (around line 9413-9485): change hardcoded `'intro'` reads to use `scope_video_role` from body, validating against `{intro, resolution, standalone}`. Single edit.

**B6** — 4 NEW milestone endpoints (~150 LOC):
- `GET /api/milestones/list`
- `POST /api/milestones/create` — validates `milestone_id` regex `^[a-z0-9][a-z0-9_-]{2,63}$` and reserved-word prefix list; case-insensitive collision returns HTTP 409
- `POST /api/milestones/load` — uses `event_load_lock`; bumps `event_generation`; sets `app.scope_type='milestone'`; cache invalidation per LD-475
- `GET /api/project/list` — combines events + milestones for `ProjectSelector.tsx`

**B7** — 3 NEW admin/drain endpoints (~100 LOC):
- `POST /api/admin/drain_start` — sets `accept_new_jobs=False`; returns `{ok, inflight_count, active_jobs}`
- `POST /api/admin/drain_end` — sets `accept_new_jobs=True`; returns `{ok}`
- `GET /api/admin/inflight_count` — full enumeration over `_GPT_JOBS` + `_MAGIC_JOBS` + `_ASSEMBLE_JOBS` + `app._sync_inflight` + lipsync state-scan across `videos.{intro,resolution,standalone}` partitions. Reference: v3 spec §3.7 has the canonical implementation.

**B8** — `@with_pin_and_drain` decorator (per v3 spec §3.7):
- Replaces 17 sites of duplicated boilerplate (drain gate + pin capture + pre-work check + sync register/unregister)
- Apply with `track_sync=True` to 14 sync handlers (list in v3 spec §4 Phase B8)
- Apply with `track_sync=False` to 4 thread-spawning handlers (`_handle_bg_submit_gpt_batch`, `_handle_bg_assemble_group`, `_handle_magic_submit_path`, `_handle_lipsync_submit`)
- Do NOT apply to read-only/poll endpoints (must stay responsive during drain)

**B9** — 2 NEW export pipeline endpoints (~300 LOC combined):
- `POST /api/beat/finalize` — Stage 1 cache; `finalize_args_hash` per Cursor Q1 (excludes fade_after_ms + pause_after_ms — those are Stage 2 concerns); register per-beat MP4 as `beat_scene` asset
- `POST /api/scene/assemble` — Stage 2 mirroring `_handle_preview_stitched` at `production_server.py:11862-12210`: pairwise `render_xfade_pair` + `trim_body` + interleaved parts list `[body_0, pair_01, body_1, ..., body_N]` + final stream-copy `concat_with_xfade_clips`. **Includes wiring `pause_after_ms` (currently dead metadata)** via silent black filler clips at LD-284 codec recipe. SIZE_BUDGET gate matching `_handle_stitch_bake` at lines 13668-13694. Register concat as `scene_concat_mp4` asset.
- New helpers needed in `lib/ffmpeg_stitch.py`: `compute_finalize_args_hash`, `_scene_lock_path`, `FINALIZE_RECIPE_VERSION`, `ASSEMBLE_RECIPE_VERSION` constants

**B12** — `_handle_milestone_load` handler (NEW, ~50 LOC). Mirrors `_handle_event_load` but sets `app.scope_type='milestone'`, `app.active_milestone_id=<id>`, `app.milestone_dir=Production/Milestones/<id>/`.

**B13/B14** — auto-covered by B3. The new `_VALID_VIDEO_ROLES = {intro, resolution, standalone}` structurally rejects `phase_a`/`phase_b`/`win` from `_handle_video_set_active` and `_handle_video_create` via existing `validate_video_role` checks.

**B15** — `_V2_MODULE_ALLOWED_FIELDS` (around line 3587-3621): add `'phase_a_stitched_file'` and `'phase_a_stitched_mtime'`. Tiny edit.

**B19** — Restart server only AFTER all of B5-B12 + URL routing complete.

### Phase C — apply migration

Once server is up with new admin/drain endpoints (B7), run:

```
python3 Production/scripts/migrate_phase_partitions_to_top_level.py --apply
```

This will: drain_start → enumerate inflight → ABORT if non-empty → 60s sync residue poll → snapshot to `.backups/state/<TS>_pre_phase_revision.json` (sha256 logged) → atomic v2→v3 write per Event → drain_end.

Alternative offline path (if continuation session opts to migrate BEFORE finishing B6-B12): server is currently stopped, so:

```
python3 Production/scripts/migrate_phase_partitions_to_top_level.py --apply --skip-drain
```

bypasses drain protocol because no in-flight jobs are possible while server is dead.

### Phase D — v59 client restructure (NOT STARTED)

12+ TypeScript files + 2 new tabs. Per v3 spec §4 Phase D. Summary:
- `scope.ts`: rename `activeVideoRole` → `activeTargetVideo`; restrict to `'intro' | 'resolution' | 'standalone'`; add `activeProjectType: 'event' | 'milestone'`, `activeMilestoneId: string | null`
- `VideoSelector.tsx` → rename to `TargetVideoSelector.tsx`; restrict to `['intro', 'resolution']`; hide in milestone scope
- `EventSelector.tsx` → rename to `ProjectSelector.tsx`; lists events + milestones grouped
- `ScopeBoundary.tsx`: read URL params on boot; call appropriate load endpoint
- `api/client.ts`: auto-inject `scope_target_video`, `scope_milestone_id`, `scope_event_id`
- `StoryboardTab.tsx`: REMOVE `<PhaseProducer phase="b" />` and `<PhaseProducer phase="a" />` siblings; FIX beat list to read `state.videos[activeTargetVideo.value].beats`; "Send Out" → POST `/api/scene/assemble`
- NEW `tabs/PhaseATab.tsx` (~50 lines)
- NEW `tabs/PhaseBTab.tsx` (~50 lines)
- `TabBar.tsx`: new order `[Beat Generator, Cropper, Storyboard, Phase B, Phase A, Stitcher]`; Phase A/B disabled when milestone scope
- `app.tsx`: route new tab keys
- `StitcherTab.tsx`: auto-detect mode from `activeProjectType`
- `BeatGeneratorTab.tsx`: works in event AND milestone scope
- `npm run build` clean

### Phase E — 37 verification gates

Per v3 spec §4 Phase E. E1-E37. **E19 deferred to Kim hands-on per spec §Notes.**

**Live pipeline gates require working server + completed Phase B + applied migration:**
- E17 — Pipeline probe Stage 1 (POST /api/beat/finalize cache hit/miss + beat_scene asset registered)
- E18 — Pipeline probe Stage 2 (POST /api/scene/assemble end-to-end + completed_mp4_path written + scene_concat_mp4 asset registered)
- E34 — Milestone scene/assemble end-to-end (lock at `Production/Milestones/<id>/scene_assemble_standalone.lock`)
- E35 — XFADE PARITY: scene/assemble parts list IDENTICAL (sha256 per part) to preview-stitched for same input
- E36 — Re-send produces distinct `scene_concat_mp4` row with different `assemble_hash`
- E37 — Drain rejects new work (503) while threaded job runs; resumes after drain_end

### Phase F — LD writes (NOT STARTED)

Per v3 spec §4 Phase F. 12 NEW LDs + 2 SUPERSEDES (LD-473, LD-474) + 5 amendments (LD-475/477/478/481/482) + 2 PATCHes (LD-139, LD-460). LD-284 NOT PATCHed (code aligned in B16 instead).

All via `try_post_or_queue` with read-back per Rule 35.

### Phase G — Closeout (NOT STARTED)

Final activity_log row `S5_5D_PHASE_AB_REVISION_COMPLETE`; S6 handoff stub; update `STORYBOARD_V59_S5_5_C_HANDOFF.md`; final tail-end verifier subagent.

---

## Key facts for continuation

- **Migration script exists and dry-runs cleanly** — do NOT recreate it; it lives at `Production/scripts/migrate_phase_partitions_to_top_level.py`
- **Server is stopped** — DO NOT restart until Phase B B5-B12 complete + URL routing wired (current code expects v3 state shape but state files are still v2; reads would return null)
- **NORMALIZATION_RECIPE_HASH cascade**: every cached `*_normalized.mp4` invalidates on next access. Source clips untouched. Re-encode ~3-5 sec/beat. Expected behavior; call out in activity log when Phase E runs.
- **Stage 2 must mirror `_handle_preview_stitched`** at `production_server.py:11862-12210` — NOT `_handle_canonical_stitch` (has cumulative-offset xfade drift bug per Agent A). The misnamed `concat_with_xfade_clips` IS used — at the END as stream-copy concat of an interleaved parts list `[body_0, pair_01, body_1, pair_12, ..., body_N]`.
- **Drain protocol does NOT invent a parallel registry** — derives from existing `_GPT_JOBS` + `_MAGIC_JOBS` + `_ASSEMBLE_JOBS` + new `app._sync_inflight` set + state-scan for lipsync (lives in `state.beats[bk].lipsync.status`).
- **Decorator `@with_pin_and_drain`** is pure refactor of 17 boilerplate sites + drain gate + sync register. v3 spec §3.7 has the canonical implementation.
- **Browser smoke E19 is the ONLY browser gate**; E25 is server-side tab structure audit.
- **Per Rule 35**: every Directus write must consult `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` BEFORE composing payload; uses `try_post_or_queue` with read-back.
- **Per Rule 19**: no shortcuts. The Phase B remaining work is required before the system is in a working v3 state.
- **`registered_write.py` is at `Production/tools/registered_write.py`** (NOT `scripts/`).

---

## Files modified by S5.5d (do NOT revert)

| File | Status | Tracked |
|---|---|---|
| `Production/tools/production_server.py` | M (modified) | git-tracked |
| `Production/tools/lib/ffmpeg_stitch.py` | M | not git-tracked (physical edit only) |
| `Production/tools/registered_write.py` | M | not git-tracked (physical edit only) |
| `Production/scripts/migrate_phase_partitions_to_top_level.py` | A (new) | not git-tracked |

State files **NOT mutated** (Event_1 + Event_2 production_state.json still v2).

---

## Recommended continuation prompt

> Continue execution of v59 Storyboard Phase A/B Architecture Revision per `Production/docs/STORYBOARD_V59_PHASE_AB_REVISION_SPEC_v3.md`. Predecessor session S5.5d (preflight #197, activity log id=1478) completed Phases 0, A, B0, and Phase B partial (B1, B2-partial, B3, B10, B11, B12-partial, B16, B17). Resume from Phase B B5 (`_handle_use_as_final`), then B6 (4 milestone endpoints), B7 (3 admin/drain endpoints), B8 (decorator + 18 sites), B9 (2 export pipeline endpoints with full xfade orchestration mirroring `_handle_preview_stitched` at production_server.py:11862-12210), B12 (`_handle_milestone_load`), B15 (`_V2_MODULE_ALLOWED_FIELDS`), URL routing, B19 restart. Then Phase C (--apply migration with --skip-drain since server is currently stopped, OR drain integration if you've restarted), Phase D (12+ client files + 2 new tabs), Phase E (37 gates; E19 deferred to Kim), Phase F (12 NEW LDs + 2 supersedes + 7 PATCHes), Phase G closeout. Use full autonomous mode + zero-error-qa + escape hatches. Read this handoff, the v3 spec, and the lessons doc before resuming. Files modified by S5.5d are listed in this handoff — do NOT revert them.

---

**End of S5.5d continuation handoff.**
