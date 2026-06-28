# TECH_SPEC — Beat Gen O3 submit UI reattach V1

**Status:** Implemented  
**Branch:** `feat/bg-o3-submit-ui-reattach-v1`  
**Category:** O3 submit ack ↔ session GET split-brain (Generate dead / no toast / no red dot)

## Problem

Operator clicks Generate; server commits O3 job (`job_busy: true`, PID, intent/terminal on disk) but UI shows idle Generate — no toast, no nav red dot, no poll loop.

## Root cause (evidence)

1. **Submit poll latch dropped on stale `job_busy: false`** — `pruneSubmitPollLatch` and `activeO3PollJobsFromBeats` treated pre-job session GET as authoritative, clearing latch before server `job_busy` enriched.
2. **Re-submit returns `BEAT_JOB_BUSY` (409)** before dedup path — `build_generation_intent` raises busy; dedup block ran only after successful intent build.
3. **Silent Generate pre-gates** — `flushSave()` failure and `beatSaveBlockedRef` returned without toast.

## Category fix

| Layer | Change |
|-------|--------|
| Client contract | Submit latch wins over stale `job_busy: false` until terminal idle or server `job_busy: true` |
| Client UX | Toast on flushSave/block; reattach from session on ambiguous submit |
| Server | Early reattach (200 `deduped`) when job already running — before intent build |

## Verification

- `node --test storyboard-v2/src/utils/__tests__/o3JobStatusContract.test.ts`
- `pytest tests/test_o3_submit_reattach_early.py tests/test_o3_job_status_contract_parity.py -v`
- `verify_beatgen_deploy_smoke.sh 5113`
- Browser: Generate on Event_3 → spinner + red dot within 2s
