# Kling Native LipSync Wrapper Replacement Spec v1

Status: proposed, awaiting Kim approval before implementation

## 1. Purpose

Replace only the broken WaveSpeed Kling LipSync wrapper used by the Arlo/O3 voice path while preserving the successful parts of the pipeline:

- Keep Kling/O3/Omni visual generation.
- Keep exact external ElevenLabs audio.
- Keep the existing Beat Gen safety model: prior approved clips stay active, no auto-approval from experiments, raw provider output must pass `min(width,height) >= 720`.
- Stop trying to force WaveSpeed `kwaivgi/kling-lipsync/audio-to-video` to respect size, because live smokes proved it ignores likely resolution fields and returns sub-720 output.

This is not a model switch away from Kling. It is a wrapper replacement: use a native Kling-compatible lip-sync API shape instead of WaveSpeed's broken two-field wrapper.

## 2. Confirmed Evidence

### 2.1 WaveSpeed wrapper behavior

Endpoint:

```text
POST https://api.wavespeed.ai/api/v3/kwaivgi/kling-lipsync/audio-to-video
```

Authenticated WaveSpeed schema exposes only:

```json
{
  "video": "string",
  "audio": "string"
}
```

No hidden `mode`, `resolution`, `quality`, `width`, or `height` field exists in the authenticated schema.

### 2.2 Live provider smokes

All of these completed successfully but returned sub-720 raw output:

| Variant | Input | Extra fields | Raw output |
| --- | --- | --- | --- |
| Baseline | WaveSpeed 1280x720 sample | none | 832x464 |
| Mode std | WaveSpeed 1280x720 sample | `mode: "std"` | 832x464 |
| Resolution 720p | WaveSpeed 1280x720 sample | `resolution: "720p"` | 832x464 |
| Mode pro | WaveSpeed 1280x720 sample | `mode: "pro"` | 832x464 |
| Quality high | WaveSpeed 1280x720 sample | `quality: "high"` | 832x464 |

Artifacts:

```text
Production/tmp_diagnostics/kling_lipsync_contract_20260610T194555Z/manifest.json
Production/tmp_diagnostics/kling_lipsync_contract_extra_20260610T194804Z/manifest.json
```

### 2.3 Aspect-ratio control smoke

Aspect ratio changes the output bucket but still does not pass the raw >=720 gate:

| Submitted input | Raw output | Gate |
| --- | --- | --- |
| 1280x720, 16:9 | 832x464 | fail |
| 960x720, 4:3 | 720x544 | fail |
| 1440x1080, 4:3 | 720x544 | fail |

Artifact:

```text
Production/tmp_diagnostics/kling_lipsync_aspect_20260610T201002Z/manifest.json
```

### 2.4 Conclusion from evidence

The failing behavior is in the WaveSpeed `kwaivgi/kling-lipsync/audio-to-video` wrapper. Rebuilding our local two-field wrapper around that same endpoint would reproduce the failure.

## 3. Non-Negotiable Invariants

1. Do not switch visual generation away from Kling/O3/Omni.
2. Do not switch to a non-Kling creative lipsync model as the production answer.
3. Do not weaken or bypass the raw provider quality gate:

```text
min(width, height) >= 720
```

4. Do not approve any experiment output automatically.
5. Do not remove the existing protected WaveSpeed path until a replacement passes live proof.
6. Do not delete or rewrite the current pipeline blindly. Build the replacement as an isolated route first.
7. Preserve exact external audio. Native generated audio is not a replacement for this task.
8. Every live claim must be backed by downloaded raw output, `ffprobe`, logs, and browser-visible UI state when relevant.
9. Prior approved clip must remain active if any replacement attempt fails.
10. All new paths must record provider, endpoint, request shape, job id, raw output path, raw profile, audio profile, and pass/fail reason.

## 4. Definitions

### Current good path

Kling/O3 visual generation:

```text
kwaivgi/kling-video-o3-pro/reference-to-video
```

This stays.

### Current bad path

WaveSpeed simple Kling LipSync wrapper:

```text
kwaivgi/kling-lipsync/audio-to-video
```

This is the target for replacement.

### Target replacement class

Native Kling-compatible exact-audio lip sync, ideally with:

1. Face identification:

```text
identify-face
```

2. Advanced lip sync:

```text
advanced-lip-sync
```

Typical native shape:

```json
{
  "session_id": "...",
  "face_choose": [
    {
      "face_id": "...",
      "sound_file": "...",
      "sound_start_time": 0,
      "sound_end_time": 6.5,
      "sound_insert_time": 0,
      "sound_volume": 1,
      "original_audio_volume": 0
    }
  ]
}
```

Exact fields vary by provider. Implementation must read live docs/schemas before coding each adapter.

## 5. Candidate Providers

The implementation must not assume provider details from memory. Each provider requires schema confirmation before use.

### Candidate A: Native Kling-compatible Advanced Lip Sync

Examples found by research:

- GMI Cloud: `kling-identify-face`, `kling-lip-sync`
- ThankYou AI: Kling-compatible `identify-face`, `advanced-lip-sync`
- AnyFast: Kling `identify-face`, Kling `lip-sync`
- Cloudsway / UniAPI-compatible Kling endpoints

Why this is preferred:

- It appears closest to Kling's native lip-sync machinery.
- It can use exact external audio.
- It may avoid WaveSpeed's re-ingest/downscale wrapper.

Pass condition:

```text
raw output has audio and min(width,height) >= 720
```

### Candidate B: Other simple Kling LipSync wrappers

Examples:

- Fal: `fal-ai/kling-video/lipsync/audio-to-video`
- RunComfy: `kling/kling/lipsync/audio-to-video`

Why this is useful:

- It is a fast control test.
- It proves whether the downscale is WaveSpeed-specific or common to the simple wrapper class.

Pass condition:

```text
same source video + same audio returns raw min(width,height) >= 720
```

### Candidate C: WaveSpeed alternative or fixed wrapper

Only use this if an authenticated WaveSpeed schema reveals a newer/fixed Kling LipSync endpoint or WaveSpeed provides one.

Known current result:

```text
kwaivgi/kling-lipsync/audio-to-video is rejected as production candidate until fixed.
```

### Non-candidate for exact-audio replacement: Omni native audio

Kling/O3/Omni native audio generation is not the same job because it generates audio. It does not preserve exact ElevenLabs audio unless a provider explicitly supports reference video plus exact external audio in the same request.

## 6. Architecture

### 6.1 Add an isolated route experiment runner

Create:

```text
Production/tools/kling_native_lipsync_experiment.py
```

Responsibilities:

1. Load target beat from `Production/beat_generator_state.json`.
2. Locate existing O3 artifacts:
   - `kling_o3_voice_fix_lipsync_input_path`
   - `kling_o3_voice_fix_lipsync_audio_path`
   - fallback to latest O3 base only if explicitly requested
3. Refuse to regenerate O3 by default.
4. Submit one selected replacement route.
5. Poll provider until terminal state.
6. Download raw provider output.
7. Probe raw video/audio with `ffprobe`.
8. Write only experiment fields unless promotion is explicitly requested later.
9. Exit non-zero on blocked/failed route.

### 6.2 Add provider adapter interface

Create:

```text
Production/tools/kling_native_lipsync_adapters.py
```

Adapter contract:

```python
class KlingNativeLipSyncAdapter:
    route_id: str
    provider: str

    def validate_credentials(self) -> CredentialStatus: ...
    def describe_schema(self) -> dict: ...
    def submit(self, *, video_path: Path, audio_path: Path, work_dir: Path) -> SubmitResult: ...
    def poll(self, job_id: str) -> PollResult: ...
    def download(self, output_url: str, dest: Path) -> Path: ...
```

Minimum result fields:

```json
{
  "provider": "...",
  "route_id": "...",
  "endpoint": "...",
  "job_id": "...",
  "request_shape_public": {},
  "raw_response_public": {},
  "output_url_present": true
}
```

No secrets may be written to logs.

### 6.3 Add route registry

Create explicit registry:

```python
NATIVE_LIPSYNC_ROUTES = {
    "wavespeed_kling_lipsync_baseline": ...,
    "fal_kling_lipsync_a2v": ...,
    "runcomfy_kling_lipsync_a2v": ...,
    "native_kling_identify_face_advanced_lipsync": ...,
}
```

Routes must be opt-in. No dynamic provider names from user input.

### 6.4 Experiment output directory

All live output must go under:

```text
Production/Event_1/kling_native_lipsync_experiments/{beat_id}/{attempt_id}/
```

Required files:

```text
input_video.mp4
input_audio.ext
request_public.json
submit_response_public.json
poll_response_public.json
raw_output.mp4
raw_profile.json
manifest.json
run.log
```

## 7. Sidecar Fields

Only these fields may be written by experiments:

```text
kling_native_lipsync_experiment_status
kling_native_lipsync_experiment_route
kling_native_lipsync_experiment_attempt_id
kling_native_lipsync_experiment_started_at
kling_native_lipsync_experiment_completed_at
kling_native_lipsync_experiment_log_path
kling_native_lipsync_experiment_error
kling_native_lipsync_experiment_error_code
kling_native_lipsync_experiment_result
kling_native_lipsync_experiment_output_path
kling_native_lipsync_experiment_output_profile
kling_native_lipsync_experiment_input_profile
kling_native_lipsync_experiment_passed_gate
```

Forbidden during experiment:

```text
kling_o3_video_path
kling_o3_status=approved
status=approved
kling_o3_options
accepted_video_path
```

Promotion to production requires a later explicit step after Kim review.

## 8. Implementation Phases

### Phase 0: Credential and schema discovery

Goal: determine which native/provider routes are actually callable from Kim's machine.

Steps:

1. Inspect existing credential loader. Do not print secrets.
2. Check for keys for:
   - WaveSpeed
   - Fal
   - RunComfy
   - GMI
   - ThankYou
   - AnyFast
   - Cloudsway / UniAPI / GoAPI / PiAPI
3. For each available provider, fetch live schema/docs.
4. Save sanitized schema snapshots to:

```text
Production/tmp_diagnostics/kling_native_lipsync_schema_{timestamp}/
```

Pass condition:

```text
At least one exact-audio Kling-compatible route is callable, or all candidates are explicitly blocked_missing_credentials.
```

### Phase 1: Control smokes

Goal: prove whether any route returns raw >=720 before integrating with Beat Gen.

Inputs:

1. WaveSpeed sample video/audio already used in diagnostics.
2. One actual O3 lipsync input and audio from the latest failed beat.

For each route:

1. Submit sample input.
2. Download raw output.
3. Probe raw output.
4. Submit O3 input only if sample passes or if route requires O3/Kling-native asset.
5. Record all profiles.

Pass condition:

```text
raw output has audio and min(width,height) >= 720
```

Fail condition:

```text
sub-720 raw output, missing audio, provider failure, unsupported schema, or missing credentials
```

### Phase 2: Build isolated Beat Gen experiment command

Only after at least one route passes Phase 1.

Command:

```bash
python Production/tools/kling_native_lipsync_experiment.py \
  --beat-id <beat_id> \
  --route <route_id> \
  --attempt-id <attempt_id>
```

This command may update only `kling_native_lipsync_experiment_*` fields.

### Phase 3: Backend API

Add:

```text
POST /api/bg/submit-kling-native-lipsync-experiment
GET /api/bg/poll-kling-native-lipsync-experiment-status?job_id=...
```

Rules:

1. Reject if normal O3 voice job is running for the same beat.
2. Dedupe same beat/route running experiment.
3. Never approve output.
4. Return raw profile and pass/fail state.

### Phase 4: UI experiment controls

Add a dev/operator-only control near the O3 failure card:

```text
Test native Kling LipSync route (no approval)
```

UI copy must always include:

```text
No approval. Raw provider output must pass >=720 before promotion.
```

Display:

- route id
- provider
- status
- raw width/height
- audio present
- output path
- error code

### Phase 5: Promotion spec

Promotion is not part of this spec.

After a route passes and Kim visually approves the raw/encoded result, write a short promotion spec that changes the production Arlo O3 voice path from WaveSpeed simple wrapper to the passing native route.

## 9. QA Plan

### Unit tests

Add tests for:

1. Route registry contains only explicit IDs.
2. Missing credentials returns `blocked_missing_credentials`.
3. Missing input artifacts returns `blocked_missing_artifacts`.
4. Experiment writes only `kling_native_lipsync_experiment_*`.
5. Experiment never writes approval fields.
6. Raw 832x464 fails.
7. Raw 720x544 fails.
8. Raw 1280x720 with audio passes.
9. Missing audio fails unless route explicitly supports safe audio mux in a later promotion spec.
10. Sanitized logs do not contain API keys.
11. Backend rejects experiment while O3 job is running.
12. UI copy includes `no approval`.

### Local commands

Run from `mindfulnest-tooling`:

```bash
python -m pytest Production/tools/tests/test_lipsync_hosting_preflight.py
python -m pytest Production/tools/tests/test_kling_lipsync_input_profile.py
python -m pytest Production/tools/tests/test_o3_job_state_reliability.py
python -m pytest Production/tools/tests/test_kling_native_lipsync_experiment.py
```

If frontend changes are made:

```bash
cd Production/tools/storyboard-v2
npm test -- --runInBand
npm run build
```

Use the repo's established QA/deploy commands if changed files require broader coverage.

### Runtime smokes

Every candidate route must produce:

```text
manifest.json
raw_output.mp4
raw_profile.json
```

Each `raw_profile.json` must show:

```json
{
  "width": 1280,
  "height": 720,
  "min_dimension": 720,
  "has_audio": true
}
```

Equivalent higher resolutions pass.

### Browser-level smoke

After backend/UI work:

1. Restart Storyboard server.
2. Confirm HTTP 200 on `/`.
3. Open Storyboard in browser.
4. Navigate to Beat Gen O3 failure card.
5. Confirm experiment button is visible only to operator/dev context.
6. Submit experiment.
7. Confirm UI says `Testing route... not approving`.
8. Confirm final UI shows raw dimensions and pass/fail.
9. Confirm the approved preview did not change.

### Deploy proof

If server/frontend changed:

1. Run canonical deploy script used by this tooling repo.
2. Restart server:

```bash
curl -s -X POST http://localhost:5111/api/server/restart
```

3. Confirm:

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:5111/
```

Expected:

```text
200
```

4. Browser smoke deployed UI, not stale local build.

## 10. Debates and Decisions Needed

### Decision 1: First implementation target

Recommended:

```text
Phase 0 schema discovery, then the first callable native Kling-compatible advanced lip-sync provider.
```

Reason:

This is the closest match to "rebuild the wrapper correctly" without changing the creative model.

Alternative:

```text
Fal/RunComfy simple wrapper first
```

Use only as a quick control if native provider credentials are unavailable.

### Decision 2: Whether to include WaveSpeed baseline in the new harness

Recommended:

Include it as a regression control but mark it expected-fail.

Reason:

It proves the harness catches the known bad route and prevents future accidental approval.

### Decision 3: Whether to keep filebin/catbox preflight

Recommended:

Keep for providers that require public URLs. Prefer native provider upload/base64 APIs if available.

Reason:

Native upload or `video_id` may avoid the downscale/re-ingest path.

### Decision 4: Whether to promote automatically after a pass

Recommended:

No.

Reason:

The first pass proves technical viability. Kim still needs visual review before replacing production lipsync.

## 11. Explicit Non-Goals

- Do not rewrite O3 visual generation.
- Do not replace ElevenLabs exact audio.
- Do not make WaveSpeed `kwaivgi/kling-lipsync/audio-to-video` production again unless WaveSpeed provides a fixed route that passes raw >=720.
- Do not use upscaled delivery as proof.
- Do not rely on docs alone. Every passing route needs live raw output proof.
- Do not delete legacy code during experiment implementation.
- Do not add broad UI controls visible to non-operator users.

## 12. Completion Criteria for This Spec

The implementation is complete only when:

1. At least one native or alternate Kling-compatible exact-audio route has been tested live.
2. Every tested route is recorded as passed, failed, or blocked with evidence.
3. Passing route raw output has audio and `min(width,height) >= 720`.
4. Existing protected WaveSpeed path remains fail-closed.
5. No experiment output auto-approves.
6. Unit tests pass.
7. Runtime smoke artifacts exist.
8. Browser-level smoke confirms UI and approval state.
9. Server deploy/restart proof is recorded if server/UI changed.
10. Final response includes paths to manifests, raw profile summaries, test commands run, and any remaining risks.

