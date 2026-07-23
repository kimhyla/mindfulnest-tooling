# TECH SPEC — Paid provider job durability (v1)

Status: proposed  
Scope: Phase A, Phase B, and compatible Beat Generator provider jobs  
Companion: `TECH_SPEC_PHASE_A_ARLO_LAYERED_DEFAULT_ROUTE_v1.md`

## 1. Decision

Create one durable provider-job foundation for paid asynchronous work.

Phase A and Phase B module lipsync use one shared event-local layered-job
aggregate. Beat Gen keeps its existing intent/PID/heartbeat architecture but
adopts the same provider submission ledger, spend idempotency, immutable scope
identity, and final artifact commit rules where the failure class is shared.

This is one category initiative delivered in sequentially reversible slices.
It is not one giant production cutover and it is not three unrelated tab
patches.

## 2. Confirmed current behavior

Cedric Phase B does not purchase a new start/end idle on Send for Lipsync.
It reuses the pre-generated blue-screen idle units and purchases only lipsync
chunks.

Confirmed Phase module defects:

- Phase B globally pads audio and the shared engine pads each chunk again.
- Preflight counts with 50 seconds while execution uses a 49-second raw limit.
- One process-global worker pointer represents both phases.
- A live worker for one phase can satisfy the other phase’s orphan check.
- Provider task IDs remain in memory until all futures finish.
- Spend is charged in aggregate only after terminal success.
- Delivery encoding mutates bytes after the engine records their hash.
- Manifest installation precedes video installation.
- Mutable event switching can separate state and spend authority.

Confirmed Beat Gen cousins:

- ambiguous paid POST retries can create duplicate WaveSpeed tasks;
- provider task IDs are not fully restart-resumable across O3 modes;
- provider spend is not recorded in the production spend ledger;
- legacy Omni in-memory ownership is not fully event/scope/generation scoped;
- task ID persistence occurs after submit returns, leaving a crash window;
- voice-first finalization references undefined `sc` after paid O3 and
  lipsync work completes.

Beat Gen differences:

- no current double padding was found;
- Beat Gen padding is single-applied but has multiple policy owners;
- no post-hash delivery mutation was found because Beat Gen has no equivalent
  final output-byte hash manifest;
- modern Beat Gen already has durable intent, terminal, PID, heartbeat,
  reattach, sidecar locks, and delivery recovery that must be preserved.

## 3. Invariants

### Paid submission

- Persist `submitting` before any paid HTTP request.
- Pass a provider idempotency key where supported.
- Persist provider task ID immediately after a successful response.
- Never blindly retry an ambiguous paid POST.
- Ambiguous acceptance becomes `submission_unknown`.
- Restart polls known task IDs; it never resubmits them.

Exactly-once purchase cannot be guaranteed when the provider accepts a request
but the process dies before receiving a task ID unless the provider supports
idempotency or task lookup. Safe behavior is to stop and reconcile, not buy
again.

### Spend

- Every returned provider task ID is charged exactly once.
- Charge occurs when the task ID is durably known, not only after media
  delivery succeeds.
- QC, encode, or state failures after provider acceptance do not erase spend.
- Failures before task creation record no spend.
- Spend summary is rebuilt from an append-only ledger.

### Scope

- Every job captures immutable event/scope identity.
- No worker resolves its event from mutable current UI/server state.
- Worker health and orphan checks require complete owner identity.
- Terminal state uses compare-and-swap on active job ID.

### Audio

- One declared owner applies each pad/trim operation.
- Phase module handlers pass trim-only audio.
- The layered engine owns per-chunk boundary context.
- Beat Gen route policies remain parameterized, but duplicate policy
  implementations are consolidated.

### Delivery

- Build output and delivery output have separate hashes.
- Final delivery encoding runs before the authoritative output hash.
- Video installs first; committed manifest installs last.
- State points to media only after manifest/video hash verification.

## 4. Immutable event context

Introduce:

```python
CapturedEventContext(
    production_root,
    event_dir,
    folder_event_id,
    state_event_id,
    event_instance_id,
    event_generation,
    scope_type,
    scope_id,
    video_role,
)
```

`event_instance_id` is a durable UUID created once in each event’s
`production_state.json`. Process-local generation remains an entry-time race
fence but is not restart identity.

Before any terminal state or spend write:

- event directory still resolves beneath the captured production root;
- `event_instance_id` matches;
- active job ID matches;
- committed manifest matches delivered bytes.

## 5. StateManager prerequisite

Add `StateManager.rebind_event(...)`.

`/api/event/load` must atomically rebind every event-scoped path and key:

- event directory and event ID;
- production-state path and lock;
- spend summary path;
- append-only spend ledger path and lock;
- clips/media directories;
- Directus lock key;
- any event-scoped cache or snapshot path.

Tests must switch events and prove state, spend, media, locks, and Directus
identity all move together. This prerequisite lands before provider-job route
changes.

## 6. Shared provider ledger

Add an append-only event-local ledger keyed by provider task ID:

```json
{
  "provider": "wavespeed",
  "operation": "kling_lipsync",
  "provider_task_id": "...",
  "idempotency_key": "wavespeed:kling_lipsync:<task-id>",
  "event_instance_id": "...",
  "scope_type": "event",
  "scope_id": "Event_3",
  "phase": "a",
  "beat_id": null,
  "job_id": "...",
  "attempt_id": "...",
  "chunk_index": 0,
  "amount_usd": 0.35,
  "recorded_at": "..."
}
```

API:

```python
record_spend_once(...)
rebuild_spend_summary(...)
provider_task_already_recorded(...)
```

The ledger append and dedupe check occur under the event spend lock. Summary
drift is healed from ledger entries.

Beat Gen writes beat/generation/attempt identity; Phase modules write
phase/chunk identity.

## 7. Phase A/B layered job aggregate

Add:

`Production/tools/layered_lipsync_jobs.py`

Store:

`Event_N/_jobs/module_lipsync_<phase>_<job_id>.json`

The job stores:

- immutable event context;
- phase, profile, route, and method;
- original and prepared audio paths/hashes;
- exact silence cuts and plan hash;
- chunk input hashes;
- provider submission status/task ID/poll result;
- spend key and charged status;
- downloaded output path/hash;
- build and delivery hashes;
- manifest/video/state commit flags;
- durable worker lease.

Job stages:

`planned → preparing → submitting → provider_polling → assembling → built →
delivering → manifest_committed → state_committed → done`

Terminal alternatives:

- `error`;
- `submission_unknown`;
- `cancelled`.

Chunk stages:

`prepared → submitting → submitted → polling → completed → downloaded →
verified`

## 8. Phase module APIs

Media planning/building remains in
`layered_character_lipsync.py`.

Required APIs:

```python
plan_layered_lipsync(profile, prepared_audio)
count_layered_lipsync_chunks(profile, prepared_audio)
build_layered_lipsync(profile, plan, provider_outputs, ...)
deliver_layered_lipsync(build_result, final_output, ...)
```

Rules:

- planning is the only chunk-boundary implementation;
- raw limit equals provider maximum minus both boundary pads;
- handlers never pre-pad layered audio;
- build has no event destination or state mutation;
- delivery computes the post-encode authoritative hash.

The existing `run_*` functions remain CLI conveniences, not production worker
entry points.

## 9. Worker ownership and reconciliation

Replace the bare phase worker pointer with:

```python
ModuleLipsyncWorkerOwner(
    phase,
    event_instance_id,
    event_dir,
    event_generation,
    job_id,
    server_instance_id,
    thread,
)
```

A worker is healthy only for its exact owner identity.

The server polling thread reconciles durable jobs:

- acquires and renews a lease;
- restores provider task IDs;
- charges known uncharged tasks;
- polls existing tasks;
- downloads missing completed outputs;
- resumes assembly/delivery;
- commits manifest-complete/state-incomplete jobs;
- does not resubmit `submission_unknown`.

## 10. Manifest-last delivery

Add:

`PHASE_MODULE_LAYERED_NATIVE_16X9_V1`

The recipe normalizes only to 1280×720/24fps. It forbids subtitle sacrifice,
adaptive framing, and scale-fill cropping.

Commit order:

1. Encode staged delivery bytes.
2. Full decode and A/V validation.
3. Compute delivery hash and size.
4. Install video.
5. Install `committed=true` manifest last.
6. Re-read and verify hash.
7. Compare-and-swap state.

Manifest records:

- build and delivery hashes;
- original/prepared audio hashes;
- provider task IDs and spend keys;
- immutable event context;
- job and profile configuration.

## 11. Beat Gen adoption boundary

Do not replace Beat Gen’s generation-intent system.

Beat Gen adopts:

- paid-submit state machine;
- provider task checkpoint format;
- provider spend ledger;
- immutable provider owner identity;
- final output-byte hash/commit helper;
- shared parameterized padding-policy registry.

Beat Gen retains:

- immutable prompt/reference intent;
- beat/attempt sidecar semantics;
- subprocess PID and heartbeat;
- option gallery and selection coherence;
- milestone scope logic;
- orphan delivery recovery.

Also correct voice-first finalization to reload/pass the current sidecar rather
than referencing undefined `sc`, with a regression test proving a fully paid
delivery cannot fail at that finalization line.

Legacy Omni ownership must use:

`(scope_type, scope_id, event_instance_id, generation, job_id)`

and recovery must execute inside the captured Beat Gen scope.

## 12. Release slices

### Slice 1 — Reproducible Cedric baseline

- Land every current Cedric/shared-engine dependency in Git.
- Exclude caches and generated bytecode.
- Preserve behavior and state shape.
- Prove clean-checkout imports, tests, code parity, build SHA, and rollback.

No Phase A activation.

### Slice 2 — Event/spend foundation

- Add immutable event context.
- Add `StateManager.rebind_event`.
- Add append-only provider ledger and idempotent summary rebuild.
- Add ambiguous-submit contract.

No production route migration.

### Slice 3 — Harden Phase B

- Add durable layered job aggregate.
- Remove global handler padding.
- Unify exact count/execution plan.
- Replace worker ownership.
- Add resumable task polling and spend.
- Add manifest-last delivery.
- Preserve Cedric output/state semantics.

Canary and rollback before proceeding.

### Slice 4 — Install Arlo runtime assets

- Versioned full-body idle;
- room plate;
- 1280×720 pure key canvas;
- composition oracle;
- pinned asset manifest.

No button wiring.

### Slice 5 — Activate Phase A

- Wire Arlo profile through the hardened aggregate.
- Preserve Phase A manual visual review.
- Remove recurring idle generation.
- Make base clip optional compatibility metadata.
- Update UI copy, authority registry, reject/archive, and Stitcher tests.

### Slice 6 — Beat Gen adapter

- Adopt provider task/spend/commit helpers.
- Preserve intent/PID/heartbeat architecture.
- Fix undefined `sc`.
- Harden legacy Omni scope ownership.
- Add restart, ambiguous-submit, and ledger tests.

## 13. Gate per slice

Each slice requires:

- focused tests;
- clean-checkout importability;
- `git diff --check`;
- no generated caches/bytecode;
- parity path coverage;
- canonical deploy for the canary event when runtime behavior changes;
- served build SHA match;
- rollback proof.

Paid canaries occur only after offline media and restart tests pass.

## 14. Why not one deployment

A single Phase A/B/Beat Gen cutover would combine:

- live Cedric media behavior;
- new Arlo routing;
- event switching and spend storage;
- restart reconciliation;
- Beat Gen intent and milestone semantics;
- delivery and UI changes.

That rollback surface is too large.

The category fix is the shared contract. Sequential migration is how that
contract is safely proven, not a series of temporary symptom patches.

## 15. Acceptance

The release train is complete only when:

- no paid task ID exists only in process memory;
- ambiguous paid submits are never blindly retried;
- every known provider task is charged exactly once;
- event switches cannot split state/spend/media authority;
- Phase A/B worker health is exact-owner scoped;
- layered audio has one padding owner;
- final manifests hash delivered bytes;
- Phase B retains validated Cedric behavior;
- Phase A uses the reusable looped Arlo idle for every event;
- Beat Gen preserves its intent/gallery semantics while using durable provider
  accounting;
- restart and rollback drills pass for all three surfaces.
