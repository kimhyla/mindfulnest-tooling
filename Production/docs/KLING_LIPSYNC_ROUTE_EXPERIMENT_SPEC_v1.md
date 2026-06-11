# Kling Lipsync Route Experiment Spec v1

## Problem Statement

Beat Gen's current Arlo O3 voice path uses:

- O3 Pro visual base: `kwaivgi/kling-video-o3-pro/reference-to-video`
- Lipsync: `kwaivgi/kling-lipsync/audio-to-video`

The reliability layer now works: attempts are attempt-scoped, sidecar writes are locked, stale UI state clears, prior approved clips remain active, and sub-720p provider output is rejected. The remaining failure is provider output quality: repeated current-route lipsync attempts have returned raw `832x464` output from valid high-resolution input.

This spec does **not** replace the current pipeline. It adds an isolated experiment path to compare Kling-family routes safely.

## Non-Negotiable Invariants

1. The existing `Generate padded O3 voice video` button stays on the current protected path until a later explicit promotion.
2. Experiments must never write `kling_o3_video_path`, `kling_o3_status=approved`, `status=approved`, or active `kling_o3_options`.
3. Experiments must write only `kling_o3_route_experiment_*` fields and separate files under `Event_1/kling_o3_route_experiments/`.
4. A failed experiment must not remove or mutate the prior approved clip.
5. Every provider result must be probed from the raw downloaded provider output before delivery encode.
6. Raw output passes only when `min(width,height) >= 720`.
7. Output must contain an audio stream or record an explicit audio-missing failure. No silent clip can pass.
8. Current sidecar cross-process locking and attempt-id rules apply to experiment fields too.
9. Experiments are deduped per beat and route while running.
10. Provider credentials may block a route. Blocked routes must be recorded as `blocked_missing_credentials` or `blocked_unsupported_schema`, not silently skipped.

## Candidate Route Order

### Route A: Current WaveSpeed Kling Lipsync Baseline

- Endpoint: `POST https://api.wavespeed.ai/api/v3/kwaivgi/kling-lipsync/audio-to-video`
- Inputs: existing `lipsync_input` video URL + padded ElevenLabs audio URL.
- Schema evidence: public docs list only `video` and `audio`.
- Purpose: baseline comparison and regression proof.
- Expected risk: known `832x464` output.

### Route B: Current WaveSpeed Kling Lipsync With Schema Probe

- Endpoint: same as Route A.
- Inputs: same as Route A.
- Extra payload variants, tried only in experiment mode:
  - `{"resolution":"720p"}`
  - `{"resolution":"1080p"}`
  - `{"mode":"professional"}`
  - `{"quality":"720p"}`
- Purpose: test whether undocumented knobs are accepted or ignored.
- Pass condition: provider accepts payload and raw output is `>=720p`.
- Failure condition: HTTP/schema error, ignored field with sub-720p output, or missing audio.

### Route C: WaveSpeed Kling V2 AI Avatar Pro

- Endpoint: `POST https://api.wavespeed.ai/api/v3/kwaivgi/kling-v2-ai-avatar-pro`
- Inputs: image URL + padded ElevenLabs audio URL + optional prompt.
- This is still Kling-family and uses our audio directly, but it is **image+audio**, not video-to-video. It may not preserve the existing O3 motion/background continuity.
- Purpose: determine whether a Kling avatar route returns usable 720p+ for Arlo-style talking output.
- Pass condition: raw output `>=720p`, audio present, visually plausible enough for human review.
- Failure condition: sub-720p, wrong framing, wrong character identity, missing audio, unsupported animated character.

### Route D: External Kling Wrapper

- Examples: Fal Kling lipsync, RunComfy Kling lipsync, direct Kling/Omni, PiAPI Kling 3 Omni.
- Only run when credentials are available.
- Must use the same artifact isolation and gates.
- Purpose: prove whether the issue is WaveSpeed-specific or Kling-model/cartoon-input-specific.

## Required Data Model

Each beat may contain:

- `kling_o3_route_experiment_status`: `idle | running | passed | failed | blocked`
- `kling_o3_route_experiment_route`: route id, e.g. `wavespeed_kling_lipsync_resolution_720p`
- `kling_o3_route_experiment_attempt_id`: unique id for this experiment attempt
- `kling_o3_route_experiment_ui_job_id`: server job id while running
- `kling_o3_route_experiment_started_at`
- `kling_o3_route_experiment_completed_at`
- `kling_o3_route_experiment_log_path`
- `kling_o3_route_experiment_error`
- `kling_o3_route_experiment_result`: route response metadata
- `kling_o3_route_experiment_output_path`: raw provider output path
- `kling_o3_route_experiment_output_profile`: `{width,height,min_dimension,has_audio,duration_s,path}`
- `kling_o3_route_experiment_input_profile`: input video/audio/image paths and preflight proofs
- `kling_o3_route_experiment_passed_gate`: boolean

These fields must be preserved by Beat Gen extract/inject refresh flows.

## Required Implementation

### Backend Experiment Runner

Create `Production/tools/kling_lipsync_route_experiment.py`.

Responsibilities:

1. Load the target beat from `beat_generator_state.json`.
2. Prefer already materialized artifacts from the latest O3 attempt:
   - `kling_o3_voice_fix_lipsync_input_path`
   - `kling_o3_voice_fix_lipsync_audio_path`
   - `reference_image.abs_path` for avatar routes
3. If required artifacts are missing, fail loudly with a recoverable blocked status. Do not regenerate O3 by default.
4. Upload inputs with the existing byte-exact `upload_to_hosting()`.
5. Submit exactly one selected route.
6. Poll through WaveSpeed prediction polling.
7. Download raw output to `Event_1/kling_o3_route_experiments/{beat_id}_{route}_{attempt_id}_raw.mp4`.
8. Probe resolution, duration, and audio stream.
9. Write only `kling_o3_route_experiment_*` fields under the sidecar lock.
10. Exit non-zero on failed/blocked routes so logs are honest.

### Backend API

Add endpoints:

- `POST /api/bg/submit-kling-route-experiment`
- `GET /api/bg/poll-kling-route-experiment-status?job_id=...`

Submission body:

- `beat_id` required
- `route` required
- `scope_event_id` required via normal BG scope helper

Rules:

1. Dedupe running experiment for same beat/route.
2. Experiments may run while no O3 voice job is running.
3. If an O3 voice job is running for the same beat, reject with 409: `O3_JOB_RUNNING`.
4. Never call the normal approval code path.

### UI

Add a clearly labeled experimental control near the O3 failure message:

- Button label: `Test Kling route (no approval)`
- Route selector initially:
  - `Current Kling lipsync baseline`
  - `Current Kling lipsync + resolution=720p`
  - `Current Kling lipsync + resolution=1080p`
  - `Kling V2 Avatar Pro (image+audio)`

UI rules:

1. Button is disabled while normal O3 generation is running for the beat.
2. Running experiment text must say `Testing route... not approving`.
3. Passed result text must say `Experiment passed raw >=720p; review output before any promotion`.
4. Failed result text must show route, raw size, and reason.
5. Do not add experiment output to the three visible O3 option slots.

## Required Tests

### Unit / Regression

1. Route registry includes only explicit route ids and exact endpoint URLs.
2. Experiment runner refuses to run without required artifacts.
3. Experiment runner writes only `kling_o3_route_experiment_*` fields.
4. Experiment runner never writes `kling_o3_video_path`.
5. Raw `832x464` mocked output fails the gate.
6. Raw `1280x720` mocked output with audio passes the gate.
7. Missing audio fails the gate.
8. Submit endpoint dedupes same beat/route.
9. Submit endpoint rejects when normal O3 job is running.
10. UI copy includes `no approval`.
11. UI active experiment state is derived from server truth, not merged stale local state.

### Runtime Smoke

1. Run baseline route on `beat_11` from existing artifacts.
2. Confirm it either fails `832x464` or passes raw `>=720p`; record exact raw profile.
3. Run one candidate route using WaveSpeed credentials.
4. Confirm active approved clip remains unchanged regardless of experiment result.
5. Browser smoke confirms experiment result text appears and normal Generate button behavior is unchanged.

## Acceptance Criteria

The experiment implementation is complete only when:

1. Existing targeted O3 tests still pass.
2. New route experiment tests pass.
3. Storyboard frontend builds.
4. Canonical deploy script fans out the bundle and server responds 200.
5. Browser smoke shows no stale `Generating...`.
6. At least one route attempt is recorded as `passed`, `failed`, or `blocked` with full evidence.
7. No experiment output is auto-approved.

## Explicit Non-Goals

- Do not replace the default O3 lipsync route in this spec.
- Do not remove the current WaveSpeed Kling lipsync path.
- Do not weaken the `>=720p` quality gate.
- Do not approve image+audio avatar output as a drop-in O3 video replacement without separate human review and promotion spec.
- Do not add non-Kling defaults.

