# TECH_SPEC_STITCH_ARTIFACT_ORCHESTRATOR_V1

**Status:** LOCKED (RC16 category fix)  
**Token:** `STITCH_ARTIFACT_ORCHESTRATOR_V1`  
**Extends:** `STITCH_SLOT_EDIT_DISPATCH_V1`, `STITCH_SAVE_ASYNC_ARTIFACTS_V1`

---

## Problem

After RC15 moved ambient ffmpeg off the save_job HTTP thread, **mux preview** (client `stitch_preview` / `buildSlotPreview`) still ran **in parallel** on the same `STITCH_CACHE_BUILD_LOCK_V1`. Milestone slots with `ambient_bed` preset but no persisted `ambient_mix_hash` (mux-only g4-pre warm) queued ambient rebuild on every save while the client immediately POSTed preview — TRUTH-LIVE-1 hung with empty `mux_preview_hash` and orphan `artifact_build.status=running`.

## Invariant

For slots requiring muxed playback:

1. **Ambient tier** must be materialized (`ambient_mix_hash` + sig) before mux tier is considered valid.
2. **One worker per stitch job** executes `ambient_keys → mux_keys` serially.
3. **Client** polls `artifact_build` after save before binding new mux src (or uses orchestrator-completed slot from `load_job`).

## Server

- `server_handlers/stitch_artifact_build.py` — `submit_stitch_artifact_build_plan`, `wait_for_artifact_build`, `reconcile_stale_artifact_builds`
- `handle_stitch_save_job` — passes `ambient_rebuild_keys` + `mux_rebuild_hint_keys` to orchestrator
- `handle_stitch_preview` — orchestrator + wait (cache hit when mix_sig + file playable)

## Client

- `stitchArtifactBuildPoll.ts` — `pollStitchArtifactBuild`
- `StitcherTab.saveJobSlots` — poll then `bindSlotPreviewUrl(..., 'quiet_rebuild')`

## Warm (g4-pre)

- Preview orchestrator must persist **both** `ambient_mix_hash` and `mux_preview_hash`; g4-pre asserts ambient hash after warm.

## Proof

- `test_stitch_artifact_orchestrator.py`
- `verify_deploy_warm_path_durability.sh`
- `stitch_sfx_playback_truth_live.spec.ts` TRUTH-LIVE-1
