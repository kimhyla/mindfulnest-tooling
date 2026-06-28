# TECH_SPEC — Milestone Beat Generator Integration v1

**Status:** DRAFT — execution spec (not yet implemented)  
**Date:** 2026-06-23  
**Repos:** `mindfulnest-tooling` (server + storyboard-v2); deploy via Dropbox mirror per operator workflow  
**Classification:** CATEGORY fix — completes `MILESTONE_STANDALONE_INDEPENDENT_V1` scaffolding shipped in S5.5d  
**Symptom:** ProjectSelector creates/loads milestones; Beat Generator, Storyboard, and Stitcher data paths still read Event sidecar / arc skeleton  
**Reference incident:** `milestone1_arc1` (“Oliver enters”) — scope switches on server; BG still shows Event 2 intro segment + 13 beats  

---

## §1 — Product intent (Kim-facing)

Milestone videos are **standalone single-MP4 projects** (trailers, map cinematics, Oliver enters, etc.). In Beat Generator they must behave like **Resolution (`post`) segments**:

| Property | Intro (`pre`) | Resolution (`post`) | Milestone (`standalone` / `main`) |
|----------|---------------|---------------------|-------------------------------------|
| Canonical intro tail beats | **Yes** | No | **No** |
| Phase A / Phase B | Yes (event scope) | Yes (event scope) | **No** |
| Stitcher layout | 4-slot module | 4-slot module | **1-slot standalone** |
| Arc skeleton segment row | Yes | Yes | **No** (not in skeleton) |
| Send to Stitcher target | `intro` or `resolution` slot | same | **`standalone` slot only** |

**Success statement:** Select milestone in Project dropdown → Beat Gen opens empty (or persisted) beat list for that milestone → author like Resolution → Send to Stitcher → Stitcher 1-slot shows MP4 → Bake works — **without mutating the previously pinned Event’s sidecar or stitch job.**

---

## §2 — Current state (verified 2026-06-23)

### Shipped (scaffolding)

| Layer | Evidence |
|-------|----------|
| Create/load API | `handle_milestones_create`, `handle_milestone_load` in `server_handlers/event_video.py` |
| On-disk shape | `Production/Milestones/<id>/state.json` with `videos.standalone` |
| Client ProjectSelector | `ProjectSelector.tsx` — create, load, auto-load |
| Scope signals | `activeProjectType`, `activeMilestoneId` in `scope.ts` |
| Mutation scope inject | `pathappPatch` adds `scope_milestone_id` when milestone active |
| Tab gating | Phase A/B disabled; VideoSelector hidden (`app.tsx`, `TabBar.tsx`) |
| Stitcher UI mode | `standaloneMode = activeProjectType === 'milestone'` |
| Export pipeline | `_resolve_scope_root` in `production_server.py` for `beat_finalize` / `scene_assemble` |

### Not shipped (root gap)

| Layer | Current wrong behavior |
|-------|------------------------|
| `GET /api/event/current` | Returns pinned **Event** `active_video` (`intro`) while `scope_type=milestone` |
| `apiGet` | Does **not** inject `scope_milestone_id` on reads |
| `ensureBgSession` | Key = `{event_id}\|{video_role}` — ignores milestone |
| `GET /api/bg/segments` | Arc skeleton only — milestones never appear |
| `GET /api/bg/session-state` | Event `beat_generator_sidecar.json` — ignores milestone |
| All BG mutations | Write Event sidecar paths (`init_bg_paths(event_dir)`) |
| `activeTargetVideo` | Stays `intro` after milestone load (hydrated from Event state) |
| Storyboard session | `ensureStoryboardSession` key includes milestone but fetcher still calls `v2_event_state` for **Event id only** |
| Stitch job | `stitch_event_job_name(event_id)` → `{Event_N}_stitch` — milestone export would land in wrong job |
| `_assert_event_scope` | Compares `scope_event_id` to `app.event_dir.name` — **no milestone branch**; milestone mutations that omit `scope_event_id` may pass reads but writes still hit Event paths |

---

## §3 — 3×3 agent debate (decision record)

Three architectural axes. Each axis: **Agent A**, **Agent B**, **Agent C (Counter-synthesis)** argue; **Verdict** is binding for implementation.

---

### Axis 1 — Where milestone beats live (source of truth)

| Agent | Position | Argument |
|-------|----------|----------|
| **A — state.json only** | `Milestones/<id>/state.json → videos.standalone.beats` is the **only** store. Matches v3 spec, `scene/assemble`, Storyboard partition model. | Single truth; export pipeline already resolves milestone root. |
| **B — Milestone sidecar clone** | Add `Milestones/<id>/beat_generator_sidecar.json` mirroring event sidecar with one segment `{phase:"main"}`. Minimal change to `beat_generator.py` segment helpers. | Reuses 95% of BG code; sidecar is proven for O3 job liveness. |
| **C — Scope router + dual write with guard** | **Authoritative:** state.json beats dict + `display_order`. **Ephemeral job overlay:** milestone-local sidecar for in-flight O3/GPT job fields only; sidecar **must not** be read for beat list after job completes — merge into state.json on terminal status. Router picks store from `scope_type`. | Avoids two competing beat lists; keeps O3 durability patterns; state.json remains what Stitcher/assemble read. |

**Verdict: C (with simplification)** — Implement `_resolve_production_scope(body|query) → ScopeContext` first. Milestone beat **list authority** = `state.json`. Milestone **sidecar allowed only as O3 job scratch** (same file name under milestone dir for code reuse), with explicit `scope_type` gate preventing Event sidecar reads when milestone active. **Forbidden:** milestone beats living only in Event sidecar; milestone beats only in sidecar with no state.json sync.

---

### Axis 2 — Scope guard model (cross-event safety)

| Agent | Position | Argument |
|-------|----------|----------|
| **A — Extend `_assert_event_scope`** | Add `if scope_milestone_id: validate against app.active_milestone_id` branch inside existing helper. | Smallest diff to call sites. |
| **B — New `_assert_production_scope`** | Replace event-only guard; returns `ScopeContext` or sends 409/400. All handlers migrate. | One front door; impossible to forget milestone branch on new endpoints. |
| **C — Router + keep `_assert_event_scope` for events only** | New `_assert_production_scope` **wraps** event and milestone paths. Event handlers call `_assert_event_scope` only when `scope_type==event`. Milestone handlers call `_assert_milestone_scope`. Shared `_scope_body` normalizes keys. Reads use `allow_missing=True` but **must** parse `scope_milestone_id` from query when `app.scope_type==milestone`. | Preserves LD-456 event leak fix; adds milestone without widening allow_missing on mutations. |

**Verdict: C** — Introduce `ScopeContext` dataclass and `_resolve_production_scope` used by:

1. `_assert_production_scope(body, *, allow_missing, require_video_role)` — single mutation/read gate  
2. `handle_bg_session_state`, `handle_bg_segments`, all `pathappPatch` BG ops, `handle_bg_export_to_stitcher`, stitch load/save when milestone  

**Hard rule:** When `scope_milestone_id` present, **`scope_event_id` must be absent** on mutations (400 `SCOPE_AMBIGUOUS` — already in `_resolve_scope_root`). When `app.scope_type==milestone`, **`scope_event_id` in body must not bind beat writes** even if client bug sends Event_2 id.

---

### Axis 3 — Beat Generator UX (segment dropdown)

| Agent | Position | Argument |
|-------|----------|----------|
| **A — Hide Arc + Segment controls** | Milestone scope: no arc skeleton. Show read-only chip: `{milestone_id} — {label} (standalone)`. Auto-set internal segment to synthetic `main`. | Matches user mental model; zero confusion with Event 2 pre/post list. |
| **B — Add milestone rows to segment dropdown** | Extend `get_segments()` to append milestone entries from `/api/project/list`. | Reuses dropdown component; pollutes arc list; wrong coupling. |
| **C — Separate “Segment” from “Project”** | Project dropdown = scope (already). Segment dropdown = **event-only**; hidden in milestone scope. Arc dropdown hidden. BG session keyed by milestone. | Clear separation of concerns; no fake skeleton rows. |

**Verdict: C** — Hide Arc selector + Segment selector when `activeProjectType==='milestone'`. Render `mn-milestone-scope-chip` in pane header. Internal `bgActiveSegment` fixed to `{milestone_id}|main`.

---

## §4 — Converged architecture

### §4.1 ScopeContext (new server primitive)

```python
@dataclass(frozen=True)
class ScopeContext:
    scope_type: Literal["event", "milestone"]
    root_dir: Path              # Event_N/ or Milestones/<id>/
    scope_id: str               # event_id or milestone_id
    video_role: str             # intro|resolution|standalone
    generation: int             # app.event_generation
    # Event-only:
    event_dir: Path | None
    # Milestone-only:
    milestone_id: str | None
```

**Resolvers:**

| Function | Input | Output |
|----------|-------|--------|
| `_resolve_production_scope(body_or_qs)` | `scope_event_id` XOR `scope_milestone_id`, plus video role | `ScopeContext` or HTTP error |
| `_bg_store_for_scope(ctx)` | ScopeContext | sidecar path + segment key + state partition ref |
| `_stitch_job_name_for_scope(ctx)` | ScopeContext | `{event_id}_stitch` or `milestone_{id}_stitch` |

### §4.2 Client scope vector (single source)

When milestone loads, client **must** atomically set:

```typescript
activeProjectType = 'milestone'
activeMilestoneId = '<id>'
activeTargetVideo = 'standalone'   // NOT from event/current active_video
```

`ProducerSessionCoordinator` effect deps:

```typescript
[eventId, projectType, milestoneId, videoRole]
```

Cache keys (PSL amendment):

| Resource | Event key | Milestone key |
|----------|-----------|---------------|
| Beat Gen | `{event_id}\|{video_role}` | `milestone:{milestone_id}\|standalone` |
| Storyboard | `{event_id}\|event\|` | `milestone:{milestone_id}\|milestone\|{id}` |
| Stitch job | `{event_id}` | `milestone:{milestone_id}` |

### §4.3 API contract changes

#### `GET /api/event/current`

When `app.scope_type==milestone`:

```json
{
  "ok": true,
  "scope_type": "milestone",
  "active_milestone_id": "milestone1_arc1",
  "event_id": "Event_2",
  "event_generation": 2,
  "active_video": "standalone",
  "partition_keys": ["standalone"],
  "milestone_label": "Oliver enters"
}
```

`event_id` remains the **pinned event dir** for legacy paths (library roots, CR) — documented, not used for BG beat partition when milestone scope active.

#### `GET /api/bg/segments`

| scope | Response |
|-------|----------|
| event (default) | Unchanged — arc skeleton list |
| milestone (`scope_milestone_id` query or `app.scope_type`) | `{ segments: [{ event_id: "<milestone_id>", phase: "main", name: "<label or id>" }], arc_number: null, scope_type: "milestone" }` |

#### `GET /api/bg/session-state`

Resolve beats from milestone `state.json` via `display_order` + `videos.standalone.beats` when milestone scope. **Do not read** Event sidecar. `scope_active_context`:

```json
{ "arc_number": 0, "event_id": "milestone1_arc1", "phase": "main" }
```

`apiGet` must inject on all BG reads when milestone active:

- `scope_milestone_id`
- `scope_video_role=standalone`
- `scope_target_video=standalone`

#### `POST /api/bg/export-to-stitcher`

| Field | Event | Milestone |
|-------|-------|-----------|
| `slot_key` | `intro` / `resolution` | **`standalone`** |
| stitch job | `{Event_N}_stitch` | **`milestone_{id}_stitch`** |
| concat output dir | `event_dir/animation_clips_final/` | `milestone_dir/animation_clips_final/` |
| sidecar read | event sidecar | milestone sidecar or state-only path per Axis 1 |

**Intro canonical tail:** `append_intro_canonical_tail_beats` gated on `phase=="pre"` only — milestone `main` never triggers (already true; add regression test).

### §4.4 Stitcher standalone job shape

New canonical job name: `milestone_{milestone_id}_stitch`

```json
{
  "slots": {
    "standalone": {
      "video_path": "Production/Milestones/milestone1_arc1/animation_clips_final/....mp4",
      "overlay_baked": false
    }
  }
}
```

`STITCH_SLOT_ORDER` for standalone mode: `["standalone"]` only. `_stitch_pipeline_slot_count(body)` returns 1 when `scope_milestone_id` set.

Stitch state file: keep **`Event_N/stitch_state.json`** for events. Milestone jobs stored in **`Milestones/<id>/stitch_state.json`** (new file, mirror event layout) — **prevents** milestone bake from touching Event_2 jobs.

---

## §5 — Integration surface inventory (zero-surprise matrix)

Every touchpoint must be explicitly **Event / Milestone / Both** with test ID.

### §5.1 Server — read handlers

| Handler | File | Milestone behavior | Gate |
|---------|------|-------------------|------|
| `handle_event_current` | `event_video.py` | Return milestone partition metadata | E1 |
| `handle_bg_segments` | `background.py` | Synthetic single segment | E2 |
| `handle_bg_session_state` | `background.py` | Beats from milestone state.json | E3 |
| `handle_stitch_load_job` | `stitch_editor.py` | Load `milestone_*_stitch` from milestone stitch_state | E4 |
| `handle_stitch_list_jobs` | `stitch_editor.py` | Filter/milestone root | E4 |
| `handle_video_list` | `event_video.py` | 404 or empty when milestone scope (VideoSelector hidden) | E5 |
| `v2_event_state` | `production_server.py` | Milestone: read milestone state.json shape | E6 |

### §5.2 Server — mutation handlers (BG)

All routes in `MUTATION_ENDPOINTS` with `bg_` prefix + export + beat CRUD:

| Category | Rule |
|----------|------|
| Scope gate | `_assert_production_scope` at top |
| Path init | `init_bg_paths(ctx.root_dir)` on milestone load **and** before BG write |
| Beat persist | Milestone → mutate `state.json` partition; event → sidecar segment |
| O3 jobs | Job pin includes `scope_type` + `milestone_id` in pin dict |
| File outputs | Clips under `ctx.root_dir/kling_o3_clips/` not Event dir |

**Critical:** `handle_bg_export_to_stitcher` → `_run_bg_export_to_stitcher_core` must use `ctx.root_dir` not `h.app.event_dir`.

### §5.3 Client

| File | Change |
|------|--------|
| `api/client.ts` | `apiGet` injects milestone query params; `buildScopeQuery()` shared with pathappPatch |
| `scopeReconcile.ts` | On `scope_type=milestone`, force `activeTargetVideo='standalone'` |
| `ProjectSelector.tsx` | After milestone load, set `activeTargetVideo` |
| `producerSessionKeys.ts` | `bgSessionKey`, `stitchJobSessionKey` milestone variants |
| `bgSessionStore.ts` | Milestone-aware fetch + cache key |
| `storyboardSessionStore.ts` | Fetch milestone state endpoint (new or extended v2) |
| `stitchJobSessionStore.ts` | Load `milestone_{id}_stitch` |
| `ProducerSessionCoordinator.tsx` | Pass milestone into ensure* calls |
| `BgTab.tsx` | Hide arc/segment; milestone chip; export slot `standalone` |
| `StitcherTab.tsx` | Verify standalone mode uses milestone job name |

### §5.4 Explicit non-regression (must not change)

| Area | Invariant |
|------|-----------|
| Event BG | Arc skeleton segments unchanged |
| Event intro | Canonical tail still appends on `pre` only |
| Event stitch | `{Event_N}_stitch` 4-slot composer unchanged |
| Scope leak | Event A beats never appear when editing milestone B |
| LD-456 | Cross-event 409 preserved for event scope |
| Phase A/B | Still disabled in milestone scope |
| Dedicated port | `?event=Event_2` URL pinning unaffected |
| O3 intro export | Event 2 intro send-to-stitcher regression suite green |

---

## §6 — NEW LDs (write on merge)

| Key | Severity | Text |
|-----|----------|------|
| `MILESTONE_BG_SCOPE_ROUTER_V1` | BLOCKER | All BG read/write paths resolve `ScopeContext` first; milestone beats never read Event sidecar. |
| `MILESTONE_STITCH_JOB_ISOLATION_V1` | BLOCKER | Milestone stitch jobs live in `Milestones/<id>/stitch_state.json` with name `milestone_{id}_stitch`; never upsert into `{Event_N}_stitch`. |
| `MILESTONE_CLIENT_SCOPE_VECTOR_V1` | HIGH | Milestone load sets `activeTargetVideo=standalone`; apiGet injects `scope_milestone_id`. |
| `MILESTONE_BG_UX_HIDE_ARC_SEGMENT_V1` | MEDIUM | Arc + Segment dropdowns hidden in milestone scope; synthetic `main` segment only. |

---

## §7 — Implementation phases (atomic deploy units)

Each phase: **code + tests + Dropbox mirror + server restart + proof** before next phase.

### Phase 0 — Scope router foundation (server only)

1. Add `ScopeContext`, `_resolve_production_scope`, `_assert_production_scope` in `production_server.py` (or `lib/scope_context.py`).
2. Wire `handle_event_current` milestone branch.
3. Unit tests: ambiguous scope, missing scope, milestone not found, event mismatch unchanged.

**Gate P0:** pytest scope router; curl event/current shows `active_video: standalone` when milestone loaded.

### Phase 1 — Client scope vector

1. `apiGet` scope injection.
2. `ProjectSelector` + `scopeReconcile` set `activeTargetVideo`.
3. PSL cache key helpers.
4. `ProducerSessionCoordinator` passes milestone into ensure*.

**Gate P1:** Playwright F119.x extended — after milestone load, BG session-state request URL contains `scope_milestone_id` + `scope_video_role=standalone`.

### Phase 2 — BG read path

1. `handle_bg_segments` milestone branch.
2. `handle_bg_session_state` milestone beats from state.json.
3. `init_bg_paths(milestone_dir)` on milestone_load.
4. BgTab hide arc/segment + milestone chip.

**Gate P2:** Load `milestone1_arc1` → BG shows **0 beats**, header chip “Oliver enters”, no Event 2 beats.

### Phase 3 — BG write path

1. add_beat, save_beat, delete_beat, O3 submit, trim, magic — all scope-routed.
2. Milestone sidecar path under milestone dir (if using Axis 1-C job scratch).
3. State.json sync on beat list mutations.

**Gate P3:** Add empty beat → persists in `Milestones/milestone1_arc1/state.json`; Event_2 sidecar byte-identical before/after.

### Phase 4 — Export + Stitcher

1. `handle_bg_export_to_stitcher` milestone branch → `standalone` slot.
2. `stitch_upsert_milestone_slot` + milestone stitch_state file.
3. `stitchJobSessionStore` + StitcherTab load correct job.
4. Storyboard session reads milestone partition.

**Gate P4:** Send to Stitcher → `milestone_milestone1_arc1_stitch.slots.standalone.video_path` set; Event_2 stitch job untouched; Stitcher preview plays.

### Phase 5 — Real durability

1. Golden fixture: create milestone → 2 beats → mock Kling approve → export → stitch bake.
2. Anti-regression matrix: run Event_2 intro export test + milestone export in same pytest session.
3. E2E `f_milestone_bg_golden_path.spec.ts`.

**Gate P5:** Full QA skill loop; commit on feature branch.

---

## §8 — Test plan (anti-regression matrix)

| ID | Type | Assert |
|----|------|--------|
| T1 | pytest | `_resolve_production_scope` rejects both event+milestone ids |
| T2 | pytest | Milestone session-state returns 0 beats on fresh milestone |
| T3 | pytest | `append_intro_canonical_tail_beats` not called for phase `main` |
| T4 | pytest | Export writes `milestone_{id}_stitch` not `{Event}_stitch` |
| T5 | pytest | Event intro export regression (existing suite) still green |
| T6 | Playwright | Milestone load hides arc/segment dropdowns |
| T7 | Playwright | Add beat in milestone scope increases milestone state beat count |
| T8 | curl | `scope_type=milestone` → `active_video=standalone` |
| T9 | manual | Switch milestone → Event_2 → milestone; beat lists independent |

---

## §9 — Failure modes explicitly prevented

| Failure | Prevention |
|---------|------------|
| Edit milestone, corrupt Event 2 sidecar | Scope router binds writes to `ctx.root_dir` only |
| Milestone export overwrites Event 2 intro slot | Separate stitch job name + stitch_state file |
| Segment dropdown shows Event 2 pre while milestone selected | Hide dropdown; synthetic segment |
| `active_video=intro` causes wrong BG partition | Client + server force `standalone` |
| apiGet missing milestone scope | Shared `buildScopeQuery()` for GET+POST |
| O3 job completes into wrong dir | `init_bg_paths(milestone_dir)` on load + pin includes milestone_id |
| Storyboard shows Event beats under milestone project | Storyboard fetcher uses milestone state endpoint |
| Cache bleed Event↔milestone | PSL keys include `milestone:` prefix |

---

## §10 — Open product decisions (Kim — before Phase 3)

1. **Script import:** Milestones start empty only, or “Import from skeleton event” action (e.g. pull Event 3b Oliver Meet text)? *Spec default: empty start; import is Phase 6 optional.*
2. **Library / CR roots:** Milestone BG uses global Production library (current pinned event dir for CR paths) or milestone-local library folder? *Spec default: global library, clips under milestone dir.*
3. **Production Map:** Show milestone nodes linked to arc? *Out of scope v1 — no map changes.*
4. **Final MP4 naming:** `{milestone_id}_final.mp4` vs label-based? *Spec default: `{milestone_id}_standalone_final.mp4` under milestone `animation_clips_final/`.*

---

## §11 — Execution checklist (agent operator)

- [ ] Work in `mindfulnest-tooling` feature branch  
- [ ] Implement Phase 0→5 sequentially; no skipping gates  
- [ ] Mirror to Dropbox + `verify_tooling_dropbox_parity.py` exit 0  
- [ ] Restart production server; hard refresh storyboard (`build-sha` matches)  
- [ ] Proof block in PR: curl + pytest + Playwright artifact paths  
- [ ] Do **not** widen `_assert_event_scope(allow_missing=True)` on mutations  

---

## §12 — Debate summary (one paragraph)

The 3×3 debate converges on **scope router first**, **state.json as milestone beat authority**, **isolated stitch jobs**, and **hiding event-only BG chrome** rather than polluting the arc segment list. Agent B’s sidecar-clone shortcut was rejected as a dual-truth hazard; Agent A’s state-only approach was accepted but requires an O3 job scratch path (Axis 1-C). Extending `_assert_event_scope` alone (Axis 2-A) was rejected as a continuing footgun for new endpoints. The winning pattern mirrors Producer Session Layer: **one coordinator, explicit cache keys, scope vector drives all ensures** — so milestone integration cannot regress Event intro/resolution behavior because every handler receives a frozen `ScopeContext` before touching disk.

**End of TECH_SPEC_MILESTONE_BEATGEN_INTEGRATION_v1**
