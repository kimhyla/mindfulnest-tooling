# TECH SPEC — Phase B Path A default lipsync route (v1)

Marker: `PHASE_B_PATH_A_ROUTE_V1`
Registry concept: `phase_b_lipsync_route`
Runbook: `Production/tools/PHASE_B_PATH_A_LIPSYNC_RUNBOOK_v1.md`
Validated end-to-end on Event 5 Phase B (Jul 17 2026) before wiring.

## 1. Problem / category

The Phase B module lipsync route (`handle_phase_b_lipsync`) submits a
whole-frame idle video to Kling lipsync. The whole class of defects Kim has
been fighting is inherent to that route, not to individual jobs:

- **Scene-wide warp** — Kling re-renders every pixel, so shelves/props morph.
- **Detail loss** — Kling lipsync always outputs 832x464 regardless of input;
  a wide frame leaves the character a small fraction of those pixels.
- **Frozen mouth** — the base idle uses `MOUTH LOCK` prompts, so the body is
  either static or mouth-frozen; no true full-body gesture during speech.
- **No QC gates** — white-eye hallucinations and frozen seams ship silently.

## 2. Fix (category)

Make the **Path A layered pipeline** (`phase_b_path_a_pipeline.py`) the single
default route for Phase B module lipsync:

1. Static room plate + blue-screen character cutout — only Cedric is ever
   re-rendered by Kling.
2. Gesture idle track from trimmed 10s bookend units joined with 0.5s
   crossfades (no frozen seams).
3. Voice stem split at silence midpoints into ≤50s chunks; chunks submitted
   in parallel (`transport="url"`).
4. QC gates before compositing: pupil scan (white eyes) per chunk, body
   still-span scan (≥0.5s) on idle track and final composite.
5. Chunks padded to exact audio duration, concatenated, sharpened,
   chroma-keyed, composited over the plate with the full stem.

This also **collapses the ≤185s / >185s fork** — chunking handles all stem
lengths uniformly, so `LIPSYNC_SINGLE_PASS_MAX_S` no longer routes anything.

## 3. Server integration contract

### Handler (`server_handlers/phases.py handle_phase_b_lipsync`)

Unchanged: scope validation, generation pin, WaveSpeed client check,
`phase == "a"` redirect, `base_clip_id` required + coerced (recorded in state
for continuity; Path A does not read it), audio resolution + stem-trim prep,
busy check via `phase_lipsync_job_busy`.

Changed:

- Chunk count computed with `count_phase_b_path_a_chunks(audio)`; budget
  gate = `COST_PER_LIPSYNC * chunk_count` (per-chunk spend, like the old
  segmented path).
- State moves to the **`running` + pending_output** shape (already supported
  by `phase_lipsync_job_contract` + TS mirror — no client change):
  `phase_b_lipsync_status="running"`, `_started_at`, `_pending_output`,
  `_pending_audio`; `task_id` popped (multi-chunk job has no single vendor id).
- Background worker (`_spawn_phase_a_lipsync_worker`) runs
  `run_phase_b_path_a_lipsync(...)` then the shared terminal writer
  `_write_phase_b_lipsync_complete(...)` with `spend_usd = per-chunk total`.
  On exception: `status="error: ..."` + pending keys popped.

### Pipeline entry (`phase_b_path_a_pipeline.py`)

```python
run_phase_b_path_a_lipsync(audio_path, out_path, *, api_key, work_dir=None) -> dict
```

- Builds everything in a **local** work dir (`/tmp` mkdtemp default) —
  Dropbox CloudStorage corrupted a 2-min encode mid-write (see runbook) —
  then copies the verified composite to `out_path` (event dir).
- Raises `PhaseBPathAQCError` when a QC gate fails: idle still-span, chunk
  pupil scan, composite still-span. Failure lands in
  `phase_b_lipsync_status = "error: PhaseBPathAQCError: ..."` — never a
  silently bad deliverable.
- Returns manifest dict: `chunk_count`, `cuts`, `units`, per-chunk lipsync
  results, QC outcomes.

### Terminal write / delivery

Same choke point as before: `_write_phase_b_lipsync_complete` →
`finalize_phase_module_lipsync_delivery(RECIPE_V2)`. Path A output is already
1280x720, so the V2 reframe plan resolves `mode="none"` (dimension equality
branch) and the encode runs the plain `voice_first_upscale` profile — which
sets `phase_b_lipsync_delivery_profile` so `ensure_phase_b_stitch_slot_for_bake`
does **not** re-encode at bake.

### Restart durability (`PHASE_B_PATH_A_ORPHAN_SWEEP_V1`)

Pre-existing gap (also affected the old segmented path): a `running` Phase B
job's worker thread dies on deploy/restart and the state wedges busy forever.
New `sweep_phase_b_lipsync_orphan(state_mgr)` runs in the persistent
`LipsyncPollingThread` sweep next to the Phase A resume:

- status `running` + worker thread not alive + `started_at` older than
  `PHASE_B_LIPSYNC_RESTART_ORPHAN_SEC` (300s) → terminal
  `error: orphan_restart: ...`, pending keys popped → Kim can resubmit.
- Also `PHASE_B_LIPSYNC_STALE_SEC` (3600s) guards a hung worker.

Reject path: `phase_b_lipsync_pending_output` / `_pending_audio` /
`_started_at` added to `_PHASE_LIPSYNC_DERIVED_KEYS` so Reject fully clears
the running shape (pre-existing gap).

### DNS (LD-379 class, category placement)

`transport="url"` uploads (filebin/catbox/uguu) fail with NXDOMAIN on Kim's
ISP resolver. The fallback now lives **inside `lipsync_sender`** (public-DNS
getaddrinfo fallback for exactly those upload hosts, only after the system
resolver fails) so every URL-transport caller — server route, CLI, future
pipelines — is covered without per-caller monkeypatching.

## 4. What is NOT changed

- UI (`PhaseProducer.tsx`), endpoint shape, and `phaseLipsyncJobContract.ts` —
  the `running` shape is already in the contract.
- `phase_b_kling_base_prep.py`, `phase_b_kling_segmented_lipsync.py` — no
  longer called by the handler; modules + unit tests remain (regen_base_clip
  and history).
- Stitcher export / bake authority (`STITCH_BAKE_SLOT_AUTHORITY_V1`).
- Phase A route.

## 5. Assets (deploy-time preconditions)

All must exist under Dropbox `Production/` (validated by the pipeline at
run start, hard error otherwise):

- `NEW STYLE CHARACTERS/CEDRIC/path_a_prep/cedric_cutout_blue_1280x720_v1.png`
- `NEW STYLE CHARACTERS/CEDRIC/path_a_prep/cedric_room_plate_1280x720_v1.png`
- `assets/lipsync_bases/cedric_path_a_gesture_idle_10s_loop_v1_blue_1920x1080.mp4` (unit A)
- `assets/lipsync_bases/cedric_path_a_gesture_idle_B_10s_loop_v1_blue_1920x1080.mp4` (unit B)

## 6. Cost

`COST_PER_LIPSYNC` ($0.35) × chunk count (~4 for a 180s stem ≈ $1.40/line) —
charged once at terminal write, same as the old segmented path. Idle units are
one-time assets (already produced).

## 7. Tests

- `tests/test_phase_b_path_a_route.py` (new) — behavior, not grep:
  - chunk boundary detection on synthesized audio (tone+silence fixtures);
    contracts: every chunk ≤ max, cuts inside silences, count for real
    178.44s stem shape
  - `qc_still_scan` catches a synthesized frozen span; passes a moving clip
  - `qc_pupil_scan` catches synthesized white-eye frames; passes dark-pupil frames
  - orphan sweep: running+dead worker+old started_at → error; young job → untouched
  - handler block contains marker `PHASE_B_PATH_A_ROUTE_V1`, calls
    `run_phase_b_path_a_lipsync`, no `submit_avatar_pro`, no single-pass fork
- Updated grep-contract tests:
  - `test_phase_b_kling_base_prep.py::test_phases_handler_uses_auto_base_prep`
    → handler now asserts Path A entry (prep module unit tests unchanged)
  - `test_beatgen_omni_restore.py::test_phase_b_module_handler_uses_kling_not_avatar_pro`
    → asserts Path A route, still bans `submit_avatar_pro`
- Registry durability: concept `phase_b_lipsync_route` row in
  `authority_registry.py` + `STORYBOARD_AUTHORITY_REGISTRY_v1.md`; markers
  verified by `test_authority_registry_durability.py`.

## 8. Rollout

Full-QA loop: pytest bundle → commit on feature branch →
`deploy_storyboard_v59.sh` → fleet build-sha parity (5111-5114) → multipass
proof x2 → live user-path smoke (real Phase B submit on the pinned event,
verify `running` → `done`, delivery profile set, output present and QC-clean).

Rollback: revert the handler commit — the old single-pass/segmented code path
is preserved in git history; no data migration involved (state keys unchanged).
