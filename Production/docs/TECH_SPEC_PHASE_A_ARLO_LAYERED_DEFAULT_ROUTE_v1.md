# TECH SPEC — Phase A Arlo layered default route (v1)

**Status:** ARCHIVED / SUPERSEDED 2026-08-11 by `TECH_SPEC_PHASE_A_ARLO_LAYERED_DEFAULT_ROUTE_v2.md` (`PHASE_A_ARLO_LAYERED_ROUTE_V2` Gate0 headshot Speak). Historical only — do not implement from this document.  
**SHORTCUT_PHASE_A_LAYERED_V1_ARCHIVE_V1:** deferred live Event_3 deploy/parity wiring and incomplete verify-path notes in this v1 draft are closed by the v2 Gate0 lock + Event_6 proof; remaining v1 checklist text is non-operative.  
Marker: `PHASE_A_ARLO_LAYERED_ROUTE_V1` (superseded)  
Authority concept: `phase_a_lipsync_route` (now V2)  
Companion precedent: `TECH_SPEC_PHASE_B_PATH_A_DEFAULT_ROUTE_v1.md`  
Cross-system durability: `TECH_SPEC_PAID_PROVIDER_JOB_DURABILITY_V1.md`

## 1. Decision

Phase A `Send for Lipsync` will use the same layered route architecture as
Cedric Phase B:

1. Build a full-length character-only idle track from reusable chroma-screen
   idle units.
2. Split the selected Phase A voice stem at silence midpoints.
3. Send complete-character chunks to WaveSpeed Kling Lipsync.
4. Validate provider output and run pupil/body-motion QC.
5. Reconstruct the full chroma character frame.
6. Chroma-key Arlo over the static room plate.
7. Deliver and pin the verified video through the existing Phase A UI/state
   lifecycle.

The canonical Arlo idle is the supplied 15.04-second, 1916×1080, 24fps green
screen full-body idle. It is looped for any Phase A stem length. A new Kling
start/end idle is not generated on each send.

This route is global for every `Event_N`. Event folders provide audio, outputs,
and state only; character assets live once under `Production/NEW STYLE
CHARACTERS/ARLO/`.

## 2. Why the route must change

The current Phase A handler calls
`run_phase_a_arlo_idle_lipsync_startend_still`:

- resolves a canonical still;
- purchases a new Kling start/end-same-still idle;
- loops that newly generated idle;
- submits a second paid Kling Lipsync job;
- uses a fixed two-job budget gate;
- maintains a restart-resume path tied to
  `_tmp_phase_a_arlo_startend`.

That route caused composition and color instability and performs a recurring
idle-generation purchase even though a reusable full-body idle now exists.

Cedric Phase B established the correct architecture:

- the provider receives a complete character composition that already fills
  its chroma-screen input;
- provider output supplies the visible moving character;
- output is placed into a matching chroma carrier;
- the carrier is keyed over a static room plate;
- chunking, bounded submissions, and QC are server-owned;
- the UI observes only the shared state job contract.

Arlo must copy that architecture, not Cedric’s character-specific dimensions.

## 3. Category invariant

Provider framing and final scene placement are separate profile concepts, but a
`whole_character` provider contract may never select only a face or upper-body
region.

Required profile invariants:

- `provider_content="whole_character"` requires
  `provider_crop == complete source frame`.
- `placement_mode="full_canvas"` requires
  `placement == complete output canvas`.
- `cutout_mode="key_canvas"` requires a nearly pure chroma canvas and rejects
  any desk, prop, or foreground pixels.
- The final Arlo silhouette must extend into the expected lower-body region;
  an upper-body-only result fails before delivery.

These invariants prevent the previous failure where a close provider crop
became the final character and a fabricated desk layer hid the lower body.

## 4. Canonical runtime assets

Install once under Dropbox `Production/`; never duplicate per event.

- Full-body idle:
  `NEW STYLE CHARACTERS/ARLO/arlo_fullbody_idle_green_1916x1080_v1.mp4`
  - source asset: existing `NEW STYLE CHARACTERS/arlo idle.mp4`;
  - 1916×1080;
  - 24fps;
  - 15.041667 seconds;
  - green-screen corner median approximately RGB `(6,239,10)`.
- Static room plate:
  `NEW STYLE CHARACTERS/ARLO/arlo_room_plate_1024x576_v1.png`.
- Pure key carrier:
  `NEW STYLE CHARACTERS/ARLO/arlo_key_canvas_1280x720_v1.png`;
  every pixel RGB `(6,239,10)`.
- Composition oracle:
  `NEW STYLE CHARACTERS/ARLO/arlo_fullbody_reference_1024x576_v1.png`;
  this is the approved still showing Arlo’s full standing composition.

The unversioned source file remains untouched. The versioned canonical idle is
the profile target used by production and parity/preflight checks.

Runtime character media is Category 2 data. Deployment mirrors code but must
not overwrite these assets.

Asset installation must also create:

`NEW STYLE CHARACTERS/ARLO/arlo_layered_assets_v1.json`

That manifest pins SHA-256, byte size, dimensions, duration/fps where
applicable, and semantic role for the idle, room plate, key canvas, and
composition oracle. Production preflight compares real files to this manifest
before budget authorization.

## 5. Arlo profile contract

The shared engine authority is
`Production/tools/layered_character_lipsync.py`.

The Arlo wrapper authority is
`Production/tools/arlo_layered_lipsync.py`.

Required Arlo profile:

- profile: `arlo`;
- route: `PHASE_A_ARLO_LAYERED_ROUTE_V1`;
- method: `layered_fullbody_greenscreen_kling_lipsync_v2`;
- source size: 1916×1080;
- provider crop: `(0,0,1916,1080)`;
- provider input: 1920×1080;
- provider output: 832×464, fail closed on any other size;
- output canvas: 1280×720;
- final placement: `(0,0,1280,720)`;
- provider content: `whole_character`;
- placement mode: `full_canvas`;
- cutout mode: `key_canvas`;
- key: `chromakey=0x06EF0A:0.18:0.05`;
- despill: green;
- output fps: 24.

The room plate and provider output are scaled by the same 1.25 factor from the
approved 1024×576 composition to 1280×720. This preserves Arlo’s normalized
position, size, and feet while satisfying the existing module delivery
contract.

The close head-and-torso crop from the failed test is forbidden in this
profile. It may be retained only as a historical experiment and may not be
reachable from a production handler.

### Current working-tree deltas

(ARCHIVED — SHORTCUT_PHASE_A_LAYERED_V1_ARCHIVE_V1) Historical note only; v2 Gate0 is the production contract.
Former “Before wiring” checklist (non-operative):

- change route `ARLO_LAYERED_LIPSYNC_CLI_V2` to the authoritative Phase A
  marker;
- change canvas/placement from 1024×576 to 1280×720;
- replace the unversioned idle path with the versioned canonical asset;
- replace the 1024×576 key canvas with the 1280×720 canonical key canvas;
- update geometry tests that currently lock 1024×576;
- add the count/build/deliver APIs described below.

The prototype’s successful offline preview proves the full-body layering
direction only; it is not evidence that server wiring or delivery is complete.

## 6. Idle loop

The supplied idle is the reusable unit.

- Head trim: 0.35 seconds.
- Tail trim: 0.45 seconds.
- Effective unit duration: approximately 14.24 seconds.
- Join repeated units with a 0.5-second video crossfade.
- Build to the exact prepared stem duration.
- Normalize each unit to 1920×1080, 24fps, square pixels, and a common
  timebase before crossfade.
- Run body-motion still-span QC on the completed idle track.

The idle is looped locally with FFmpeg. Looping creates no provider purchase.

If additional Arlo idles are added later, the profile may rotate them exactly
as Cedric rotates A/B units, but each unit must independently pass:

- complete-character geometry;
- key-background validation;
- measured trim thresholds;
- pupil and body-motion fixtures.

## 7. Audio ownership

The handler remains responsible for:

- Phase A voice-stem pin durability preflight;
- resolving the current top-level `phase_a_voice_stem_file`;
- rejecting stale or missing stem pins;
- applying the persisted waveform cut region.

The shared layered engine owns lipsync boundary context:

- detect silence boundaries using `silencedetect=noise=-35dB:d=0.45`;
- maximum raw chunk duration is
  `50.0 - boundary_pad_start - boundary_pad_end`;
- apply 0.5 seconds of cloned-video/silent-audio context to each chunk only
  after chunking;
- strip that context from provider output before concatenation.

The handler must call `_apply_phase_audio_trim`, not
`_apply_phase_lipsync_audio_prep`, for the layered route. Otherwise global
padding and per-chunk padding are both applied and the final duration changes.

The same ownership must be enforced for Cedric after the shared-engine
refactor so both wrappers have one padding contract.

## 8. Shared engine additions required before wiring

Add or retain these profile-driven entry points:

- `validate_assets(profile, production_root)`;
- `count_layered_lipsync_chunks(profile, audio_path)`;
- `build_layered_lipsync(profile, audio_path, ...) -> LayeredBuildResult`;
- `deliver_layered_lipsync(build_result, final_output, ...)`;
- `build_arlo_layered_lipsync(...)`;
- `run_arlo_layered_lipsync(...)` as a CLI compatibility convenience;
- `count_arlo_layered_lipsync_chunks(...)`;
- `validate_arlo_layered_assets(...)`.

Chunk counting and execution must use the same effective raw chunk limit.
Budget calculation may never estimate with 50 seconds while execution uses
49 seconds.

The engine must:

- build in a local temporary directory;
- cap parallel provider submissions;
- persist provider task IDs and outputs incrementally;
- validate fixed provider dimensions;
- fully decode each provider output and concatenated output;
- run pupil and body-motion QC;
- produce a manifest draft containing profile, route, method, chunk
  boundaries, task IDs, profile configuration, and source hashes;
- leave the final event state untouched on failure.

Manifest lineage distinguishes:

- `audio_source`: event-relative original pinned Phase A voice stem;
- `audio_prepared`: temporary cut/padded engine input;
- source-stem hash and prepared-input hash.

This preserves `_phase_lipsync_sidecar_audio_source` compatibility and prevents
a temporary filename from becoming lineage authority.

`LayeredBuildResult` contains:

- verified local video path;
- manifest draft;
- work directory;
- source hashes;
- chunk records;
- no event destination and no production-state mutation.

The compatibility `run_layered_lipsync` API may remain for CLI experiments,
but production server handlers must use the split build/deliver API.

## 9. Final delivery and manifest ownership

The layered composite must be 1280×720 before module delivery.

This requirement is structural. The existing V2 delivery planner treats a
1024×576 input as a reframe candidate, removes a 9% bottom band, and then
scale-fills 1280×720. That would cut Arlo’s feet despite a correct composite.
At 1280×720, the delivery planner resolves `mode="none"` and performs only the
normal delivery encode.

Add explicit delivery recipe
`PHASE_MODULE_LAYERED_NATIVE_16X9_V1`. It permits scale-only normalization to
1280×720 and forbids letterbox detection, subtitle-band sacrifice, adaptive
nose framing, and scale-to-fill cropping. Arlo uses this recipe even when its
input is already 1280×720; correctness must not depend only on a dimension
side effect.

Required order:

1. Shared engine builds and verifies a local 1280×720 composite.
2. `finalize_phase_module_lipsync_delivery` encodes to a staged event-local
   destination with no reframe/crop.
3. Full decode and A/V gap checks run on the delivered bytes.
4. Final SHA-256 is calculated after delivery encoding.
5. Final video is installed with `os.replace`.
6. A manifest containing the installed video hash and `committed=true` is
   installed last with `os.replace`.
7. State is mutated only after both files exist, hashes match, and the manifest
   is committed.

A video and JSON file cannot be replaced as one filesystem-atomic pair. The
manifest-last commit protocol is the authority:

- readers ignore uncommitted/staged manifests;
- production state never points to the video before the committed manifest;
- a crash after video replace but before manifest/state leaves an unreferenced
  artifact that cleanup may quarantine;
- a crash after manifest commit but before state write is recoverable by the
  job-record reconciler.

The current engine writes a manifest before the terminal delivery re-encode.
That would leave `output_sha256` stale. Wiring must move final manifest
creation after delivery or rewrite the manifest atomically with the delivered
hash.

## 10. Server route

Endpoint remains:

`POST /api/phase_a/lipsync`

Body remains compatible:

```json
{
  "phase": "a",
  "base_clip_id": "arlo_idle_wizard_desk_v8",
  "scope_event_id": "Event_N",
  "scope_video_role": "intro"
}
```

`base_clip_id` is optional compatibility metadata. When present it is coerced
and recorded; when absent the server records the canonical compatibility ID.
It is not a render input and may not block the layered route.

The handler must:

1. Validate event scope and capture the generation/event-directory pin.
2. Verify WaveSpeed credentials.
3. Reject or recover an already-running shared worker.
4. Run voice-stem pin preflight.
5. Resolve and trim the Phase A voice stem.
6. Validate global Arlo profile assets before spending.
7. Count exact chunks using the Arlo profile.
8. Fast-fail the exact per-chunk budget.
9. Set the shared `running` state shape.
10. Spawn the module lipsync worker.
11. Run `build_arlo_layered_lipsync`.
12. Finalize delivery and manifest locally first.
13. Recheck the captured event pin before any terminal state write.
14. Charge actual chunk spend.
15. Write terminal success or error state.

The current call to
`run_phase_a_arlo_idle_lipsync_startend_still` must be removed from the
production handler and restart path.

The worker invocation must always pass
`production_root=captured_event_dir.parent`. It may not rely on
`MN_PRODUCTION_ROOT`, a home-directory fallback, or the mutable current app
event after spawn.

The fixed `lipsync_jobs = 2` budget model must be removed. New cost is:

`COST_PER_LIPSYNC × exact chunk count`.

No Element registration or still resolution is required during Send for
Lipsync. Those remain relevant only to optional base-clip regeneration
workflows.

## 11. Shared orchestration

Do not create another independent copy of the Phase B handler.

Refactor Phase A/B layered submission into a shared server helper parameterized
by:

- phase;
- profile/wrapper;
- base-clip continuity state key;
- terminal success status;
- visual-review policy;
- response copy.

The existing `_phase_a_lipsync_worker` currently serializes both phases despite
its name. Replace the bare thread pointer with a phase-neutral owner record:

```python
ModuleLipsyncWorkerOwner(
    phase="a",
    event_id="Event_N",
    event_dir=...,
    event_generation=...,
    job_id=...,
    thread=...,
)
```

Busy checks and orphan sweeps compare the complete owner identity. A live Phase
A worker may not make stale Phase B state appear healthy, and vice versa.
Single-worker exclusivity per server process remains the initial concurrency
policy.

The generic terminal writer must accept the base-clip state key explicitly:

- Phase A: `phase_a_chipper_sitting_clip_id`;
- Phase B: `phase_b_cedric_base_clip_id`.

Do not reuse the current Phase B writer’s Phase A fallback
`phase_a_empty_desk_bg_id`; that is the wrong semantic field for Arlo.

## 12. State contract

All authoritative keys remain top-level. Existing nested `phase_a` mirrors
remain compatibility mirrors and must be updated in the same mutation.

Running state:

- `phase_a_lipsync_status = "running"`;
- `phase_a_lipsync_started_at`;
- `phase_a_lipsync_pending_output`;
- `phase_a_lipsync_pending_audio`;
- `phase_a_lipsync_route = "PHASE_A_ARLO_LAYERED_ROUTE_V1"`;
- `phase_a_lipsync_method =
  "layered_fullbody_greenscreen_kling_lipsync_v2"`;
- no single vendor `phase_a_lipsync_task_id`;
- `phase_a_chipper_sitting_clip_id` retained for continuity.

Terminal success:

- `phase_a_lipsync_file`;
- `phase_a_lipsync_mtime`;
- `phase_a_lipsync_status = "needs_manual_visual_review"`;
- `phase_a_lipsync_requires_regen = false`;
- route and method retained for audit;
- `phase_a_lipsync_manifest_file`;
- `phase_a_lipsync_qa_dir`;
- `phase_a_lipsync_av_gap_s`;
- delivery profile and recipe;
- chunk count and actual charged cost;
- running/pending/task keys removed.

Phase A keeps `needs_manual_visual_review` rather than Phase B’s immediate
`done`. Existing Phase A policy intentionally prevents automatic stitching
until the operator approves the character result.

Terminal error:

- `phase_a_lipsync_status = "error: <type>: <detail>"`;
- all running/pending keys removed;
- old successful `phase_a_lipsync_file` is not replaced;
- failures before provider task creation record no spend;
- every returned provider task ID is charged exactly once even if later
  provider, QC, composite, or delivery stages fail.

Reject and Regen Audio continue to clear all derived lipsync keys through
`_phase_clear_lipsync_derived`.

Reject moves the committed MP4 and its committed JSON manifest together into
the rejected archive. It must not leave an authoritative manifest beside a
rejected or missing video.

Expand `_PHASE_LIPSYNC_DERIVED_KEYS` to include:

- route and method;
- manifest file;
- delivery profile and recipe;
- chunk count and charged cost;
- A/V gap and QA directory;
- all pending/running keys.

Tests must prove top-level and nested mirrors are written and cleared in the
same mutation.

Every asynchronous path captures the original event directory, state manager,
generation, and job ID. Success, error, spend, manifest commit, orphan cleanup,
and recovery writes all validate that captured identity. No terminal path may
look up the mutable current `app.event_dir` and then write to a newly selected
event.

## 13. Restart and orphan behavior

The old Phase A restart code searches
`_tmp_phase_a_arlo_startend` and re-runs the still-generation pipeline. It
must not run for the layered route.

Use a shared Phase A/B layered orphan sweep:

- `running` plus no live worker, younger than 300 seconds: grace period;
- `running` plus no live worker, older than 300 seconds:
  `error: orphan_restart`;
- live worker older than the stale ceiling:
  `error: stale_timeout`;
- clear pending/running keys so the UI can resubmit.

Provider spend cannot remain memory-only. Each job writes an atomic event-local
record:

`Event_N/_jobs/phase_a_lipsync_<job_id>.json`

The record is updated after each provider submission and poll and contains:

- event/generation/job identity;
- chunk index and source hashes;
- provider task ID and status;
- submission timestamp;
- expected per-job cost;
- downloaded output/hash when available;
- delivery/manifest/state commit status.

On restart, the reconciler:

- polls already-submitted task IDs rather than resubmitting;
- downloads completed outputs that are not present;
- resumes local assembly when every chunk is available;
- records spend idempotently per provider task ID;
- terminal-errors only when recovery is impossible.

No credentials or signed upload contents are written to the job record.
Orphan cleanup without task reconciliation is forbidden because it can cause a
duplicate purchase and under-report actual spend.

Forward compatibility requires no destructive all-event migration:

- a new submit heals missing route/profile fields into the new running shape;
- reads tolerate completed legacy outputs;
- the previous completed clip remains authoritative until a replacement
  commits successfully;
- a legacy `running` job with no layered route marker is terminal-cleared as
  `error: superseded_route_restart` rather than resumed through the retired
  still-generation path;
- `phase_a_arlo_idle_lipsync.py` remains available for rollback during the
  rollout window but is unreachable from new production submissions.

## 14. UI integration

The shared `PhaseProducer` already supports the target job shape:

- Phase A posts to `phase_a_lipsync`;
- `pathappPatch` supplies scoped event identity;
- `phaseLipsyncJobBusy` recognizes `running` without a task ID;
- the button disables while in flight;
- state refresh polls every 15 seconds;
- tab switches, focus, visibility changes, and server rehydrate refresh state;
- the existing video player prioritizes the newest Phase A lipsync;
- Reject Lipsync and Export to Stitcher remain unchanged.

No new UI component or endpoint is required.

Required UI copy changes:

- replace “still idle + LipSync” with
  “looped full-body Arlo + layered Lipsync”;
- report exact chunk count/cost from the 202 response when useful;
- remove the 8–20 minute estimate tied to generating a new idle;
- update stale comments that say Phase A uses ByteDance or a still bookend.

The Phase A base-clip selector remains visible for compatibility and optional
base-clip regeneration. Its selected ID is recorded but does not select the
layered render asset. Missing selection no longer disables Send for Lipsync,
and the “Pick an Arlo base clip first” client precondition is removed. No
per-event Arlo idle selector is introduced.

Required 202 response:

```json
{
  "ok": true,
  "status": "running",
  "phase": "a",
  "route": "PHASE_A_ARLO_LAYERED_ROUTE_V1",
  "chunk_count": 1,
  "audio_duration_s": 29.04,
  "estimated_cost_usd": 0.35,
  "base_clip_id": "arlo_idle_wizard_desk_v8",
  "message": "Layered full-body Arlo lipsync is processing."
}
```

## 15. All-event behavior

No production event literal may appear in the engine, wrapper, handler, or UI.
Tests may use clearly synthetic names such as `Event_9`; named live-proof tests
may identify their explicit fixture event.

For every event:

- event scope comes from the active server/app;
- `production_root = event_dir.parent`;
- profile media resolves relative to the global production root;
- audio resolves only from that event’s pinned state;
- output, manifest, QA frames, and temporary trimmed audio are event-scoped;
- event-generation pin prevents a completed job from mutating another event
  after a scope switch.

New events require no Arlo asset registration. They inherit the global layered
route after code deployment and need only a Phase A script and generated voice
stem.

## 16. Authority and durability updates

Add authority concept `phase_a_lipsync_route` to:

- `Production/tools/authority_registry.py`;
- `Production/docs/STORYBOARD_AUTHORITY_REGISTRY_v1.md`.

The registry marker is `PHASE_A_ARLO_LAYERED_ROUTE_V1`.

Code parity must cover:

- `layered_character_lipsync.py`;
- `arlo_layered_lipsync.py`;
- `phase_b_path_a_pipeline.py`;
- `server_handlers/phases.py`;
- `phase_lipsync_job_contract.py`;
- `phase_module_lipsync_delivery.py`.

(ARCHIVED — SHORTCUT_PHASE_A_LAYERED_V1_ARCHIVE_V1) Historical incompleteness note; closed by v2 Gate0 lock + Event_6 proof.

Runtime asset preflight must remain separate from code parity. The deploy
script must never overwrite the global Arlo idle, room plate, key canvas, or
composition oracle.

Runtime preflight validates the pinned asset manifest, not only file
existence:

- SHA-256 and size;
- idle dimensions, fps, duration, decodability, chroma median, and foreground
  bounds;
- plate/oracle/key-canvas dimensions;
- pure-key ratio;
- approved normalized composition geometry.

## 17. Required tests

### Shared engine

- A clean checkout imports the shared engine, Cedric wrapper, Arlo wrapper, and
  server handler without relying on untracked files.
- Arlo provider crop is the complete 1916×1080 source.
- Arlo placement is the complete 1280×720 canvas.
- `whole_character` rejects a partial source crop.
- `full_canvas` rejects a partial final placement.
- `key_canvas` rejects foreground/desk pixels.
- Canonical idle loops with trimmed 0.5-second crossfades.
- Chunk count uses the same effective limit as execution.
- Provider output must be exactly 832×464.
- Submission concurrency is bounded.
- Pupil and still-span QC fail closed on uninformative crops.
- Final output is 1280×720, 24fps, fully decodable.
- A/V stream gap is no greater than 100ms.
- Final manifest hash matches post-delivery bytes.
- Local work directories and temporary event audio are removed after committed
  success and quarantined with bounded retention after failure.

### Server handler

- Phase A handler contains `PHASE_A_ARLO_LAYERED_ROUTE_V1`.
- Handler calls the Arlo layered wrapper and asset validator.
- Handler does not call:
  - `run_phase_a_arlo_idle_lipsync_startend_still`;
  - `kling_startend_submit`;
  - `resolve_phase_a_arlo_idle_still`.
- Exact chunk budget gate is enforced.
- Successful worker writes the Phase A route/method/manifest state.
- Success remains `needs_manual_visual_review`.
- Pin mismatch leaves the current event’s success file unmodified.
- Phase A and Phase B workers cannot satisfy each other’s owner/orphan checks.
- Provider task records resume without duplicate submission after restart.
- Provider task IDs are charged exactly once.
- Missing global assets fail before budget/spawn.
- Spawn-busy reverts the running state.
- Orphan and stale sweeps clear the Phase A running shape.
- Reject clears route, method, manifest, pending keys, and preview.
- Tests exercise two different temporary `Event_N` directories and prove
  outputs/state never cross.

### UI

- Phase A sends the existing scoped endpoint and compatible base clip ID.
- Phase A can send with no selected base clip; canonical compatibility metadata
  is server-filled.
- `running` without task ID disables the button and starts polling.
- Terminal manual-review state displays the preview.
- Error and reject banners remain terminal.
- Copy names the looped full-body route, not still generation.
- Event switch changes both state and file URLs.
- Python and executable TypeScript job-contract tests cover the same complete
  status/busy/banner matrix.

Update or replace conflicting legacy tests:

- `test_phase_a_avatar_wire.py`;
- `test_phase_a_avatar_lipsync.py`;
- `test_chipper_reliability_gates.py`;
- `storyboard-v2/e2e/f_phase_a_001_routing.spec.ts`;
- PhaseProducer base-clip enablement tests.

### Runtime visual gates

Using the canonical real assets:

- green source foreground union includes the full lower body and reaches the
  bottom edge;
- assembled chroma layer has no desk/foreground occlusion;
- outside the keyed character region, final frames remain equal to the static
  plate within encode tolerance;
- contact-sheet frames at 2s, midpoint, and end match the approved full-body
  composition;
- no green fringe, white-eye span, frozen-body span, or scene-wide warp;
- dark and bright frame samples remain color-stable.

### Stitcher handoff

- `resolve_phase_a_raw_lipsync` resolves the newly pinned layered MP4.
- Phase A normalization preserves the full-body frame.
- Watercolor overlay and `stitch_upsert_event_slot` remain method-agnostic.
- Ambient remains Stitcher-owned and is not baked into the Phase A lipsync.
- Export verifies the Phase A slot references the new layered lineage.

## 18. Rollout

1. Land shared profile/engine tests.
2. Install and hash the versioned global Arlo assets.
3. Wire the shared server orchestrator and terminal writer.
4. Update UI copy and shared job-contract tests.
5. Add authority registry and parity gates.
6. Run focused Python and TypeScript tests.
7. Run a zero-provider offline end-to-end composition using Event 3 audio.
8. Run one paid 10-second Event 3 proof.
9. Require operator visual approval of full body, position, color, and lipsync.
10. Run a full Event 3 Phase A line.
11. Commit before deployment.
12. Deploy exactly with:
    `bash Production/scripts/deploy_option_b.sh --event Event_3`.
13. Verify code parity, served build SHA, HTTP health, and Event 3 URL.
14. Smoke another event without copying any Arlo media into that event.
15. Run the global-asset/state preflight against every existing `Event_N`.
16. Perform a rollback drill with the prior tooling commit.

The Option B deploy mirrors code and restarts/verifies the storyboard fleet; it
does not install `NEW STYLE CHARACTERS` media. Install and validate the
versioned Arlo runtime assets as a separate Category 2 step before deployment.

Do not wire the production button or run a second paid proof until the
1280×720 offline contact sheet passes the approved composition oracle.

## 19. Acceptance criteria

The route is shipped only when:

- every Phase A button uses the global reusable full-body Arlo idle;
- no send generates or purchases a new idle;
- Arlo appears full-body in front of the room plate, matching the approved
  still’s normalized placement;
- no desk or foreground mask cuts off the character;
- any stem length is handled by silence-aligned chunks;
- exact chunk count controls budget and spend;
- QC and full-decode gates fail closed;
- delivered output is 1280×720/24fps with A/V gap ≤100ms;
- the post-delivery manifest hash matches;
- event scope and generation pins prevent cross-event writes;
- worker ownership is phase/event/generation/job specific;
- paid task IDs survive restart, resume without duplicate submission, and are
  charged exactly once;
- UI polling, reject, preview, and export continue without a Phase A-only
  client fork;
- base-clip selection is compatibility metadata, not a submission gate;
- reject archives the MP4 and committed manifest together;
- original stem lineage survives trim/padding through `audio_source`;
- tests, parity, deployment proof, and one cross-event smoke are green.

## 20. Rollback

Rollback is a code-route revert:

- drain new submissions;
- restore the prior tooling commit containing the
  `run_phase_a_arlo_idle_lipsync_startend_still` handler route;
- run the canonical `deploy_option_b.sh` command;
- verify parity, served build SHA, health, and the restored route;
- leave existing event outputs and state history untouched;
- retain global versioned assets for diagnosis;
- clear only an orphaned `running` state through the normal reject/orphan
  contract.

No production-state migration is required for rollback because the established
Phase A file/status keys are preserved.
