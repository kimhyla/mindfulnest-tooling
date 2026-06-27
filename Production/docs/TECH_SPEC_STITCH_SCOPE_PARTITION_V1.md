# TECH_SPEC — Stitch Scope Partition V1

**Status:** Implemented  
**Branch:** `fix/build-sha-drift-banner`  
**Extends:** `TECH_SPEC_STITCH_SINGLE_OWNER_V1.md`, `SCOPE_CLIENT_AUTHORITY_SPEC_v1.md`, `TECH_SPEC_MILESTONE_BEATGEN_INTEGRATION_v1.md`

---

## 1. Problem (two bug classes, one missing invariant)

### 1.1 Truth masking (single-owner)

After `STITCH_SINGLE_OWNER_V1`, `GET /api/stitch_editor/job/<milestone_job>` returns **HTTP 200** with a **synthetic empty** `{ standalone: {} }` when `stitch_state.json` has `jobs: {}`. That looks like a valid loaded job with no video — indistinguishable from a failed POST persist. Deploy/E2E treated **GET 200** as readiness and **POST 200** as proof without read-your-writes.

**Terminal cause:** No API invariant that clients/gates can ask: *“Is this job row persisted on disk?”*

### 1.2 Scope channel collision (dedicated event servers)

Production uses **event-dedicated servers** (`Event_2` → `:5112`, `Event_3` → `:5113`, …). `assert_production_scope` **intentionally strips** `scope_milestone_id` on those servers because activating milestone Beat Gen runs **sidecar isolation** against shared global SQLite and **can delete Event beat rows**.

Stitch mutations were routed to `Milestones/<id>/stitch_state.json` by **job name**, but scope gates still used **`_assert_event_scope`** → `standalone` validated against **Event_N `state.videos`** (intro/resolution only). Milestone stitch POST/preview failed or behaved inconsistently on every dedicated event server — not only Event_2.

**Terminal cause:** One scope gate (`assert_production_scope`) used for two different channels — **BG/sidecar** vs **stitch JSON partition** — without a partition router.

---

## 2. Why dedicated servers strip milestone scope (and must keep doing it)

| Channel | Activates BG paths? | Touches shared sidecar/SQLite? | Safe on Event_N dedicated server? |
|---------|---------------------|--------------------------------|-----------------------------------|
| `assert_production_scope` (milestone) | Yes | Yes (isolation prune) | **No** — strip `scope_milestone_id` |
| `assert_stitch_partition_scope` | **No** | **No** — only `stitch_state.json` | **Yes** |

This applies to **all** future `Event_N` dedicated ports (`5110 + N`), not just Event_2.

---

## 3. Category fix — three invariants

### I1 — Persist truth (`STITCH_SINGLE_OWNER_V1`)

- `load_job` response includes `job_persisted: bool` and `ephemeral_milestone_job: true` when synthetic.
- `save_job` response includes `job_persisted: true`, `saved_video_path`, `saved_slots` (read-your-writes proof).

### I2 — Stitch partition scope (`STITCH_SCOPE_PARTITION_V1`)

New module: `server_handlers/stitch_scope.py`

- `assert_stitch_partition_scope(handler, body, job_name=…)` → `StitchScopeBinding`
- Resolves `ScopeContext` via `resolve_scope_from_app` **without** stripping milestone id on dedicated servers.
- **Never** calls `activate_bg_for_scope`.
- Validates `scope_video_role` against **owning partition** (milestone `state.json` or event `production_state.json`).
- Returns `stitch_store` via `stitch_state_for_scope`.

All stitch **mutations** (`save_job`, `preview`, …) use this — not `_assert_event_scope` alone.

### I3 — Deploy/E2E acceptance contract

- Deploy warm: N consecutive `/api/event/current` OK (not stitch GET 200).
- E2E bootstrap: assert POST `saved_video_path`; poll GET until `job_persisted && video_path`.

---

## 4. Files

| File | Change |
|------|--------|
| `server_handlers/stitch_scope.py` | Partition scope router |
| `server_handlers/stitch_editor.py` | save/preview/load use partition + persist truth |
| `server_handlers/milestone_scope.py` | Comment cross-ref stitch partition |
| `e2e/stitch_sfx_playback_truth_live.spec.ts` | Read-your-writes poll |
| `scripts/verify_stitch_sfx_playback_truth_live_e2e.sh` | Server stability warm |
| `tests/test_stitch_scope_partition.py` | Partition unit tests |

---

## 5. What this prevents

- Empty milestone slot masked as valid GET on dedicated servers (all Event_N).
- Milestone stitch bootstrap/E2E failing on Event_N because `standalone ∉ state.videos`.
- Deploy gate false-green on ephemeral milestone jobs.
- Future handlers accidentally using BG scope for stitch JSON writes.

---

## 6. Non-goals

- Does not re-enable passive `load_job` hydrate from `assembled/` (single-owner stands).
- Does not allow milestone BG activation on dedicated event servers (sidecar safety stands).

---

## 7. Client mirror — `DEDICATED_PORT_MILESTONE_LAYOUT_V1`

Server stitch partition scope has a client counterpart in `storyboard-v2/src/state/scope.ts`:

- On `Event_N` dedicated port + intentional `?milestone=` deep link, adopt **client milestone layout** (`activeProjectType=milestone`, standalone rail) **without** `POST /api/milestones/load`.
- `confirmServerMilestoneScope` on dedicated ports calls `adoptDedicatedPortMilestoneLayout` only — never activates server BG milestone scope.
- Client partition gate: `milestonePartitionDeepLinkAuthorized()` per `TECH_SPEC_MILESTONE_PARTITION_RESOLVER_V1.md` — **not** `readAuthoritativeEventId()` port inference.
- `reconcileClientScope` uses the same rule when `/api/event/current` reports `scope_type=event`.

This fixes the class where Stitcher rendered **4 event segments** (`intro|phase_a|phase_b|resolution`) while the milestone job lived under `milestone_<id>_stitch` — E2E locator `stitcher-multiphase-segment-standalone` was absent.
