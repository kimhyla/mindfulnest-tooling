# TECH_SPEC — O3 Gallery Closure Invariant v1

## Problem

Beat Gen splits **lifecycle truth** (`*_terminal.json`, `job_busy`, poll latch) from **gallery truth** (`kling_o3_options`, UI tile slots). A Kling/O3 job can reach terminal `done` with delivery on disk and `kling_o3_video_path` set while `kling_o3_options` is still empty. The UI renders tiles from options only, so operators see an empty slot, no spinner, and no red dot — “lost order.”

Evidence: Event_3 intro beat `bg_arc1_event3_pre_beat_09`, job `7ab3dc40` — terminal `done`, delivery mp4 on disk, sidecar option `source: kling_o3_disk_reconcile` (async repair), not checkpoint.

## Invariant (closure)

> A job is not operator-closed until **terminal is terminal** AND **delivery ∈ `kling_o3_options`** as a user-selectable row.

## Category fix (not patch)

| Layer | Change |
|-------|--------|
| **Write path** | Intent pipeline finalizes with `kling_o3_options` refresh (parity with legacy path); `assert_gallery_closed_before_terminal` before writing terminal `done`. |
| **Read path** | Session GET runs terminal/gallery reconcile **synchronously** before `job_busy` enrichment; poll snapshot reconciles single beat before returning. |
| **Lifecycle** | `beat_job_busy` stays `true` when terminal is `done`/`done_with_warning` but gallery closure pending. |
| **Client** | Submit/poll latch clears only when `beatHasPopulatedO3Slot` (options row), not `kling_o3_video_path` alone. |

## Modules

- `Production/tools/o3_gallery_closure.py` — shared helpers
- `Production/tools/o3_job_status_contract.py` — `beat_job_busy` gallery gate
- `Production/tools/kling_o3_element_beat_pipeline.py` — intent finalize parity
- `Production/tools/server_handlers/background.py` — sync session reconcile + poll reconcile
- `Production/tools/storyboard-v2/src/o3JobStatusContract.ts` — client latch

## Tests

- `tests/test_o3_gallery_closure.py`
- `tests/test_o3_checkpoint_before_done_contract.py` (existing)
- `storyboard-v2/src/utils/__tests__/o3JobStatusContract.test.ts`

## Out of scope (sibling categories)

- O3 heartbeat during long Kling poll waits (separate liveness category)
- Server restart clearing in-memory poll map
- Per-server `MN_BEATGEN_DB_PATH` dual-writer policy

## Acceptance

1. Hard refresh after Generate shows tiles when terminal is done (no empty slot gap).
2. `job_busy` true until gallery row exists.
3. Submit latch survives `approved` + `video_path` without options.
4. pytest + TS contract tests green; deploy smoke on Event_3 port 5113.
