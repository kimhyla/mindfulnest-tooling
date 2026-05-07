# Storyboard v59 — S6 Handoff (stub)

**Created:** 2026-05-03 (S5.5d-cont closeout)
**Predecessor:** S5.5d-cont (preflight #198, activity_log #1479 / #1480)
**Status:** S6 not yet started — this is a context anchor for the next session.

---

## Where things stand at end of S5.5d-cont

The v59 Storyboard Phase A/B Architecture Revision (`STORYBOARD_V59_PHASE_AB_REVISION_SPEC_v3.md` — `prod_reference_docs` id=190) is complete:

- **State migration applied** — Event_1 + Event_2 are at `version=v3` shape:
  - `state.videos.{intro, resolution}` (multi-beat partitions only)
  - `state.phase_a.*` + `state.phase_b.*` lifted to top-level
  - `state.videos.<role>.completed_mp4_path` field added
  - Snapshot at `Production/Event_<N>/.backups/state/20260503T191817Z_pre_phase_revision.json`

- **Server endpoints landed:**
  - `POST /api/admin/{drain_start, drain_end}` + `GET /api/admin/inflight_count`
  - `POST /api/milestones/{create, load}` + `GET /api/milestones/list` + `GET /api/project/list`
  - `POST /api/beat/finalize` (Stage 1 — cached per-beat finalize)
  - `POST /api/scene/assemble` (Stage 2 — xfade-orchestrated scene assembly mirroring `_handle_preview_stitched`)
  - `_handle_export` replaced with HTTP 410 stub pointing to `/api/scene/assemble`

- **Decorator wired** — `@with_pin_and_drain(name, track_sync=True|False)` applied to 12 sync handlers + 4 thread-spawning handlers + 2 export-pipeline handlers (16 total wrappers in production_server.py).

- **v59 client restructured:**
  - `scope.ts`: `activeTargetVideo` + `activeProjectType` + `activeMilestoneId` signals (`activeVideoRole` retained as alias)
  - `endpoints.ts` + `client.ts`: new endpoint URLs + `scope_target_video` / `scope_milestone_id` auto-injection
  - `VideoSelector.tsx`: `CANONICAL_ROLES = ['intro', 'resolution']`
  - `StoryboardTab.tsx`: PhaseProducer siblings removed; beat list now reads `state.videos[<role>].beats`; `SendOutButton` replaces legacy ExportButtons → `POST /api/scene/assemble`
  - `TabBar.tsx`: new tab order [Beat Generator, Cropper, Storyboard, Phase B, Phase A, Stitcher, Map] with Phase A/B disabled in milestone scope
  - NEW `tabs/PhaseATab.tsx` + `tabs/PhaseBTab.tsx` (thin wrappers around existing `PhaseProducer`)
  - `app.tsx` routes the new tab keys
  - `npm run build` clean

- **Codec recipe aligned to LD-284 strict spec** (S5.5d B16):
  - `setsar=1:1` in `NORMALIZATION_VF_EXPR`
  - `-preset slow` + `-g 48` in `NORMALIZATION_ENCODER_ARGS`
  - `NORMALIZATION_RECIPE_HASH = "f3f39a6702aaf001"` (was `8e9da052b166895a`)

- **Phase E gates:** 37/37 PASS (E19 deferred to Kim hands-on browser smoke per spec §Notes).

- **Locked decisions:** 12 NEW LDs (484–495) + LD-473/474 superseded + LD-475/477/478/481/482/139/460 amended. **LD-284 NOT PATCHed** — code aligned to spec instead.

---

## Open items for S6

1. **Browser smoke (E19)** — Kim's hands-on walkthrough of the v59 client at the new tab order: open `dist/index.html` (or run `npm run dev` against localhost:5111), exercise:
   - Project selector lists Event_1, Event_2, and any milestones
   - VideoSelector shows only intro / resolution in event scope
   - Storyboard tab no longer shows Phase A/B inline; the "Send Out as MP4" button runs scene assembly and surfaces asset_id + cache_stats
   - Phase A and Phase B tabs render PhaseProducer; both grey-out in milestone scope
   - Stitcher tab still functions in event scope (4-slot)
   - Drain status surfaces gracefully if migration is in progress (HTTP 503)

2. **Milestone hardening** — `_handle_milestone_load` currently leaves `app.event_dir` unchanged for safety. Long-term, milestone-aware handlers should consult `app.scope_type + app.active_milestone_id` rather than `event_dir`. This is a documentation + grep-and-edit task; non-blocking.

3. **`_auto_assemble_phase_a_stitched` decorator** — Spec §B8 lists this internal helper but its `(self, ts: str)` signature differs from request handlers. Currently NOT wrapped; covered by parent handlers' drain gate. Decision deferred to S6 + Kim review.

4. **Provenance enrichment** — Stage 2 `iteration_notes` template includes `source_beat_hashes` (10-char hash prefixes). For deeper traceability, S6 may switch to `source_beat_asset_ids` (numeric prod_assets ids resolved via find_asset). Non-blocking.

5. **Cursor v8 review (optional)** — None required at the close of S5.5d-cont; v3 spec §13 is the optional checklist if Kim wants another cross-review.

6. **Long-term `pinned_video_role` enforcement** — explicitly NOT added in this revision per v3 spec §3.7 closing note. S6 may add it once the client + server have converged on `scope_target_video` everywhere.

---

## How to resume S6

1. Read this stub + the v3 spec (`prod_reference_docs` id=190).
2. Query `prod_locked_decisions` for keys starting with `PHASE_A_` / `PHASE_B_` / `MILESTONE_` / `BG_VIDEO_` / `VIDEO_ROLE_` / `BEAT_FINALIZE_` / `SCENE_ASSEMBLE_` / `ASYNC_QUEUE_` / `ASSET_TYPE_SCENE_CONCAT` / `STORYBOARD_SEND_OUT_` / `TARGET_VIDEO_` / `TAB_STRUCTURE_`.
3. Run the Phase E final gate suite (`/tmp/phase_e_final.py` from S5.5d-cont, or rebuild it from the v3 spec §4 Phase E) to confirm no regressions.
4. Pick up open item 1 (Kim browser smoke) first.

---

**End of S6 handoff stub.**
