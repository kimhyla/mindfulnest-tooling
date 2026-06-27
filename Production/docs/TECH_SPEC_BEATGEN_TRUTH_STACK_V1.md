# TECH_SPEC — Beat Gen Truth Stack V1 (End the Horror Show)

**Status:** Authoritative implementation + Full QA gate (P0–P5 shipping)  
**Branch target:** `fix/beatgen-truth-stack-v1`  
**Replaces:** piecemeal operator rules; supersedes `TECH_SPEC_BEATGEN_SCOPE_AUTHORITY_V1.md` and reframes `TECH_SPEC_BEATGEN_WRITE_SCOPE_FAIL_CLOSED_V1.md`  
**Builds on (already shipped):** `TECH_SPEC_BEATGEN_PER_EVENT_SQLITE_V1.md`, `TECH_SPEC_STITCH_SCOPE_PARTITION_V1.md`, `BG_BEAT_JOB_TRUTH_GALLERY_SPEC_v1.md`, `BG_BEAT_GEN_FOREVER_PLAN_v1.md`, `TECH_SPEC_BG_SCOPE_ACTIVATION_COLD_BOOT_ONLY_V1.md`

---

## Category-unlocker (mandatory before any code change)

- **Bug category:** **Partition authority collapse** — Beat Gen has multiple legitimate storage authorities (per-event SQLite, milestone JSON, clip disk, O3 job artifacts, UI slot filters) but **no single carried scope object** and **no single agent write front door**. Writers (HTTP handlers, CLI, agents, O3 subprocesses) mutate state via implicit module globals. Correct data routinely lands in the wrong partition; UI reads a different partition than the writer; Kim sees “success” with unchanged Beat Gen.
- **Category fix:** **Beat Gen Truth Stack** — (1) typed `BeatGenScope` on **every** read/write, (2) fail-closed validation + SQLite `event_id` check, (3) **single-writer HTTP** for agent production mutations, (4) display authority = storage authority, (5) canonical resolvers, (6) structured mutation logs, (7) CI + Full QA gates.
- **Fix type:** **CATEGORY**
- **Compelling reason (if PATCH):** N/A
- **Plan:** Six layers (below). Ship in order; no “optional” layers — each closes a sibling bug class.

---

## 1. What “just works right the first time” means

Kim opens **`http://localhost:5113/?event=Event_3`**, intro, Beat 9:

1. Hard refresh → beats present, no disk error.  
2. Active clip in **session-state** = active clip in **slot UI** = file on disk under `Event_3/kling_o3_clips/`.  
3. Agent import on Beat 9 → **one action**, no SQLite knowledge → visible after refresh.  
4. Generate on milestone beat `event3b_full` → `job_busy` within 2s, artifacts under resolved Event folder, poll completes.  
5. Never again: “write succeeded, UI unchanged.”

That requires **one truth stack**, not a checklist of workarounds.

---

## 2. Terminal cause (honest)

| Level | Why |
|-------|-----|
| L1 | Beat 9 showed three Ken Burns stills after O3 i2v import. |
| L2 | Writer used legacy `beatgen.db` / wrong scope; server read `beatgen_event3.db`; UI filtered out non-`still_insert` sources. |
| L3 | **Architecture treats “scope” as ambient state** (globals + env + last `init_bg_paths`) instead of **a mandatory parameter on every truth mutation**. Multiple authorities (SQLite / milestone JSON / mirror JSON / disk / UI filter) are **not linked by invariants**. |

Per-event SQLite (2026) fixed **file sharding**. Job Truth / Forever Plan (2026) fixed **O3 busy/gallery**. **Neither fixed write-path scope or display parity.** This spec closes what remains.

---

## 3. The Beat Gen Truth Stack (six required layers)

Nothing here is “nice to have.” Omitting any layer leaves a sibling bug class open.

### Layer 1 — `BeatGenScope` on every truth operation

**Problem without it:** `rebind_bg_paths_from_app` is **not** on every handler path (evidence: only explicit calls in `background.py` ~3752, ~6740; many `update_beat_locked` sites have no preceding rebind). Globals (`_BG_EVENT_DIR`, `MN_BEATGEN_DB_PATH`, `_MILESTONE_SIDECAR_JSON_ONLY`, `BeatgenStore` singleton) can be **stale, torn, or sticky** (milestone bind). Validating `beat_id` against **wrong globals** still “passes.”

**Fix:**

```python
@dataclass(frozen=True)
class BeatGenScope:
    kind: Literal["event_production", "milestone_arc"]
    event_id: str | None       # Event_3
    event_dir: Path | None
    milestone_id: str | None
    db_path: Path | None       # beatgen_event3.db — None when milestone JSON
    sidecar_authority: Path    # SQLite mirror path OR milestone sidecar JSON

def beatgen_scope(scope: BeatGenScope):
    """Context manager: bind globals, reset BeatgenStore if db_path changed, yield, restore optional."""

def update_beat_locked(beat_id, mutator, *, scope: BeatGenScope, ...):
    with beatgen_scope(scope):
        assert_beat_id_matches_scope(beat_id, scope)
        ...
```

**Rules:**

- **HTTP:** middleware or handler wrapper enters scope from `app` pin **before any** BG handler runs (not only startup).
- **CLI:** `main()` builds scope once; no bare `init_bg_paths`.
- **O3 subprocess:** inherits serialized scope in env (`MN_BEATGEN_SCOPE_JSON`) — same fields as launchd + server pin.
- **Tests:** explicit scope fixture; never rely on ambient `beatgen.db`.

**Why this is required (not Phase 4):** Without it, dedicated-server handlers have the **same** “forgot to rebind” class as CLI.

---

### Layer 2 — Fail-closed validation (inside scope)

| Gate | Action |
|------|--------|
| `beat_id` event N ↔ scope event N | **Raise `BeatGenScopeError`** |
| Milestone scope ↔ beat segment key (`event3b_full` vs `event3_pre`) | **Raise** |
| `MN_BEATGEN_DB_PATH` ≠ `beatgen_eventN.db` on event scope | **Raise** (no legacy fallback) |
| `event_dir_for_beat_id` parse failure | **Raise** — delete Event_1 fallback (`beat_generator.py` ~10444) |
| Clip path event folder ↔ scope event dir | **Raise** on import |
| Legacy `~/.mindfulnest/state/beatgen.db` new writes | **Raise** + migration read-only |

Return **HTTP 409** with structured body for agents:

```json
{"error_code": "BEATGEN_SCOPE_MISMATCH", "beat_id": "...", "scope_event_id": "Event_3", "bound_db": "..."}
```

---

### Layer 3 — Single-writer HTTP (agents + CLI for production beats)

**Problem without it:** Every Cursor session becomes a storage topology maintainer. One missed bind = horror show repeat.

**Fix (hard requirement — not optional HTTP):**

| Writer | Allowed path |
|--------|----------------|
| `production_server` | Direct `update_beat_locked` with `MN_BEATGEN_SERVER_WRITER=1` at startup |
| O3 subprocess (server-spawned) | `MN_BEATGEN_ALLOW_DIRECT_WRITE=1` + scope env |
| Agents / CLI for `eventN_*` beat_ids | **HTTP only** → `POST /api/bg/import-delivery-clip` on `:5110+N` |
| Unit tests | `MN_BEATGEN_TEST_ALLOW_DIRECT_WRITE=1` |

Direct `update_beat_locked` on production beat_ids without server writer → **`BeatGenSingleWriterError`**.

**Implementation:** `Production/tools/beatgen_scope.py` — `assert_direct_write_allowed`, `http_import_delivery_clip`.

**CLI:** `run_o3_pov_motion_i2v.py` defaults to HTTP import for production beats; `--milestone-import` for milestone JSON path.

---

### Layer 3b — HTTP import API (read-your-writes)

| Endpoint | Purpose |
|----------|---------|
| `POST /api/bg/import-delivery-clip` | Copy mp4 → `Event_N/kling_o3_clips/`, slot, make-active, still_insert source tags |
| `POST /api/bg/select-o3-video` | Set active pointer (existing — document as agent entry) |

Response includes full **`beat`** row from authority.

---

### Layer E — SQLite `event_id` defense in depth

**Fix:** `BeatgenStore.patch_beat` verifies row `event_id` matches `_event_id_from_beat_id(beat_id)` before UPDATE.

**Fix:** `assert_db_path_matches_beat` compares DB **basename** to `beatgen_eventN.db` (not legacy `beatgen.db`).

---

### Layer F — Observability

Structured log on every mutation:

```
[beatgen_mutation] {"operation":"update_beat_locked","beat_id":"...","scope_event_id":"Event_3","db_path":"...","caller":"..."}
```

Implemented in `update_beat_locked` via `log_beatgen_mutation`. Extend to all BG mutators in Follow-on H8.

---

### Layer 3 (legacy section header — see Layer 3 + 3b above)

**Deprecated duplicate — use Layer 3 / 3b above.**

---

### Layer 4 — Display authority = storage authority (Still + TTS)

**Problem:** `buildFixedO3OptionSlots` (`BgTab.tsx` ~515–518) filters options: in `still_insert` mode, only `inferO3OptionPipelineMode === still_insert`. Clips tagged `o3_pov_motion_i2v` are **active in SQLite but invisible** in all three slots.

**Fix (pick one, ship both if cheap):**

1. **Write path:** import/motion clips for Still beats use `source: still_insert_kling_idle` and `still_insert_*` filename prefix.  
2. **Read path:** if `kling_o3_status === approved` and active path not in filtered list, **force-show active clip** in slot 0 (mirror Job Truth “approved pointer visible”).

**Full QA:** Browser — Beat 9 slot 0 plays video with Ember TTS; not three identical still thumbs.

**Why required:** Kim’s definition of “works” is **visual**. Correct SQLite with wrong UI = still broken.

---

### Layer 5 — Canonical resolvers (stop guessing paths)

Single modules; grep-enforced; no duplicate logic.

| Resolver | Input | Output | Used by |
|----------|-------|--------|---------|
| `event_id_from_beat_id(beat_id)` | `bg_arc1_event3_pre_beat_10` | `Event_3` | scope builder, HTTP, agents |
| `port_from_event_id(Event_3)` | `Event_3` | `5113` | agents, QA scripts (`event_server_port.sh`) |
| `beatgen_db_path_for_event(Event_3)` | `Event_3` | `beatgen_event3.db` | scope, launchd |
| `resolve_o3_job_event_dir(...)` | beat_id + scope | `Event_N` folder | submit, poll, terminal, reconcile (existing — **parity sweep required**) |
| `storyboard_url_for_beat(beat_id)` | beat_id | `http://localhost:5113/?event=Event_3` | agent skill |

**Agent skill (one page):** “Given beat_id → open this URL → POST these endpoints.” No Dropbox paths in agent instructions.

---

### Layer 6 — Proof gates (make regression impossible to merge)

| Gate | When |
|------|------|
| `test_beatgen_scope_*` | wrong scope write raises; cross-event import raises |
| `test_milestone_init_never_bootstraps_sqlite` | milestone never opens SQLite |
| `test_still_insert_active_clip_visible` | UI contract or server-side option list includes active |
| `verify_beatgen_deploy_smoke.sh PORT` | integrity + session-state + restart |
| `verify_beatgen_per_event_sqlite_durability.sh` | all dedicated ports |
| **Pre-fix repro test** | write without scope → must fail **after** fix (committed) |
| **CI required** | above on every Beat Gen / server PR |
| **Full QA browser** | Kim path on affected beat before merge |
| **build-sha = HEAD** after mirror + restart | deploy rule |

**Legacy DB retirement:** after one release with raise-on-write, rename `beatgen.db` → `beatgen.db.deprecated` in docs; bootstrap import only, never write.

---

## 4. WHAT ELSE IS NEEDED (full blast radius — end the horror show forever)

Beyond the six layers, these are **additional** structural items that otherwise become the *next* incident.

### A. Request-level scope on HTTP (not startup-only)

**Gap:** Server binds at `run_server()` (~13479). Handlers that mutate without fresh scope rely on globals surviving from prior request or sticky milestone bind.

**Need:** `production_server` BG route wrapper:

```python
with beatgen_scope(scope_from_app(app)):
    handler(...)
```

Every `/api/bg/*` mutating route. Session-state GET enters read scope (same object, read-only).

---

### B. UI scope sync (client authority)

**Gap:** Wrong port in URL vs `activeScope` → wrong session-state channel.

**Need (mostly shipped — verify):**

- Dedicated port → URL is authoritative (`resolveAuthoritativeClientScope.ts`)
- `event/load` to wrong event on `:5112` → **409** (Full QA A)
- Visible **scope badge** in Beat Gen: `Event_3 · intro · SQLite beatgen_event3.db` vs `milestone1_arc1 · full · JSON sidecar`

Kim must **see** which authority she is editing.

---

### C. O3 Generate scope parity (same stack as sidecar)

**Gap:** Job Truth fixed busy/gallery; job **folder** still uses `resolve_o3_job_event_dir` separately from sidecar scope. Milestone `event3b` beats must not write intents to fictional `Event_3b/`.

**Need:**

- O3 submit enters same `BeatGenScope` as sidecar write
- `resolve_o3_job_event_dir(beat_id, scope=...)` — no raw `event_dir_for_beat_id` on lifecycle paths (grep sweep §F)
- Full QA C: Generate on `event3b_full` beat → `job_busy` <2s, artifacts path proof

---

### D. JSON mirror is never read for live authority

**Gap:** Operators/agents grep `beat_generator_state.json` and think write worked.

**Need:**

- Code: when SQLite authority, **no read path** uses mirror except bootstrap/migration (already true for `read_sidecar()` — **document + forbid** direct file reads in agent skill)
- QA proof cites **`/api/bg/session-state`** only

---

### E. Snapshot / restore per-event

**Gap:** `.production_snapshots` historically missed Event_3 segments; restore could repopulate wrong DB.

**Need:**

- Snapshots include **per-event** `beatgen_eventN.db` or segment export keyed by event
- Restore script writes **scoped DB**, not legacy global
- `MN_SIDECAR_ALLOW_FULL_REPLACE=1` only in restore scripts, never agents

---

### F. Script surface area cleanup

**Evidence:** `Event_1` defaults in `run_o3_pov_motion_i2v.py:257`, `teleport_intro_kit.py:911`, `phase_a_*.py`, …

**Need:**

- Grep gate in CI: no `default="Event_1"` on `--event-dir` / `--event` in `Production/tools`
- Beat-touching scripts: **required** `--event-dir` or derive from `--beat-id`

---

### G. Concurrency / lock clarity

**Gap:** Sidecar lock starvation (Job Truth docs) — long GET vs write.

**Need (Forever Plan alignment):**

- Session-state GET read-only (no reconcile on hot path — already Job Truth)
- Writes hold scope + lock; scope object documents which DB file

Not the primary horror-show cause, but “works first time” under load requires it — **do not regress Job Truth**.

---

### H. E2E Playwright contract

**Need:**

- `storyboard-v59-bg-scope-sync.spec.ts` (exists) — extend: after import API, slot shows video src
- Beat Gen footer scope badge test
- Dedicated port 409 test

---

### I. Operator / agent skill (single source)

**Need:** One Cursor rule + one skill:

1. Parse `event(\d+)` from beat_id  
2. Open `http://localhost:{5110+N}/?event=Event_N`  
3. Mutate only via `/api/bg/*` on that port  
4. Proof = response `beat.kling_o3_video_path` + browser slot 0  

**No** `import beat_generator` in agent workflows for shipping beats.

---

### J. Merge policy

**Need:**

- Beat Gen / server PRs: CI green + `verify_beatgen_deploy_smoke.sh` on affected ports + agent fills Full QA template
- **No merge** on “fixed in chat”
- Never Find Issues / Bugbot (Kim rule)

---

## 5. Blast radius checklist (all accounted)

| Surface | Layer(s) |
|---------|----------|
| Dedicated HTTP server startup | L2, L6, §4A |
| HTTP BG handlers (all) | L1, L2, §4A |
| Agent / Cursor writes | L3, L5, §4I |
| CLI import/generate scripts | L1, L2, L3, §4F |
| O3 subprocess | L1, §4C |
| `event_dir_for_beat_id` callers | L2, L5 |
| BeatgenStore singleton | L1 |
| Milestone JSON (no SQLite) | L1, L2, L6 |
| Still + TTS UI slots | L4 |
| Session-state vs UI | L4, L6 |
| Stitch export (reads active path) | L2 (correct scope → correct path) |
| JSON mirror / snapshots | §4D, §4E |
| Client scope / port | §4B |
| Legacy beatgen.db | L2, L6 |

---

## 6. Implementation phases (all required — ordered)

| Phase | Deliverable | Closes |
|-------|-------------|--------|
| **P0** | Repro test: off-scope write succeeds today → must fail after P1 | Proof discipline |
| **P1** | `BeatGenScope` + context manager + wire `update_beat_locked` | Global/stale scope |
| **P2** | Fail-closed gates + kill fallbacks + 409 responses | Cross-partition writes |
| **P3** | HTTP middleware scope + wrap all `/api/bg` mutators | Handler forgot rebind |
| **P4** | `POST /api/bg/import-delivery-clip` + read-your-writes + agent skill | Agent horror show |
| **P5** | Still slot display parity (L4) | Browser/UI truth |
| **P6** | Resolvers module + CLI HTTP wrappers + grep CI for Event_1 defaults | Path guessing |
| **P7** | O3 submit scope parity + job dir grep sweep | Generate artifacts |
| **P8** | UI scope badge + Playwright extension | Kim visibility |
| **P9** | Snapshot/restore per-event + legacy DB retirement | Restore incidents |
| **P10** | Full QA on Event_3 Beat 9 + deploy smoke all ports + commit | Ship proof |

**No phase is “optional.”** P1–P5 minimum shippable slice for Event_3-class bugs; P6–P10 close remaining siblings.

---

## 7. What we explicitly reject

| Idea | Why |
|------|-----|
| Operator checklists without L1–L3 | PATCH |
| “Agents should remember bind” | PATCH |
| Single global SQLite | Recreates purge bugs |
| Merge milestone + event sidecars | Recreates isolation bugs |
| HTTP optional if CLI is careful | CLI will never be careful enough |
| Scope object optional | Server has same stale-global class |
| JSON mirror as write proof | Wrong authority |

---

## 8. Full QA (mandatory — Kim rules)

### Category-unlocker before code

(See top of doc.)

### Mandatory checklist

**A. Scope / identity** — URL, `/api/event/current`, dedicated 409, hard refresh before heal  

**B. Beat Gen persistence** — session-state beats > 0; `PRAGMA integrity_check` on `beatgen_eventN.db`; cite authority path  

**C. In-flight Generate** (if touched) — milestone `event3b` beat; job_busy <2s; spinner; artifact paths via resolver  

**D. Deploy** — mirror Dropbox; build-sha; restart HTTP 200  

**E. Regression scan** — primary category + siblings §4; browser slot 0 for Still beats  

### Deliverable template

```markdown
## Full QA — Beat Gen Truth Stack V1

**Root cause:** … (evidence: curl, db path, screenshot)

**Category fix:** Truth Stack layers …

**Proof:** pre-fix repro fails → post-fix passes; pytest; smoke; browser Beat N slot 0

**Commit:** `<sha>` on `fix/beatgen-truth-stack-v1`

**Sibling categories still open:** …
```

---

## 9. Taxonomy (mandatory before merge)

1. **Primary category:** Partition authority collapse  
2. **Siblings:** §4 A–J  
3. **Parallel categories:** Job Truth (busy/gallery) — don’t regress; Stitch scope — separate router  
4. **Underlying chain:** §2  
5. **Gates that would have caught Event_3:** L1+L3+L4+P0 repro  
6. **Open after ship:** only items explicitly failed in P10 with ticket  

---

## 10. Success definition (“horror show ended”)

- [ ] Agent imports Beat 9 clip **only via :5113 API** → browser correct first time  
- [ ] Direct `update_beat_locked` without scope → **raises in tests and production**  
- [ ] Wrong-event write → **409**, zero disk mutation  
- [ ] Active clip always visible in Still + TTS UI when approved  
- [ ] No new writes to `beatgen.db`  
- [ ] All dedicated ports pass deploy smoke after every Beat Gen PR  
- [ ] Kim can identify scope from UI badge without knowing SQLite filenames  

---

## 11. Code references (evidence)

| Fact | Location |
|------|----------|
| Event_N → port `5110+N` | `Production/scripts/event_server_port.sh` |
| Server startup bind only | `production_server.py` ~13479–13490 |
| Milestone stripped on dedicated BG | `milestone_scope.py` ~133–143 |
| `rebind_bg_paths_from_app` not universal | `background.py` sparse call sites vs many `update_beat_locked` |
| Still slot filter | `BgTab.tsx` `buildFixedO3OptionSlots` ~515–518 |
| `event_dir_for_beat_id` → Event_1 | `beat_generator.py` ~10439–10444 |
| O3 job dir resolver | `o3_generation_intent.py` ~238–285 |
| Milestone no SQLite bootstrap test | `test_milestone_init_bg_paths_authority_guard.py` |
| Deploy smoke | `verify_beatgen_deploy_smoke.sh` |
| Event_3 incident | `beatgen.db` vs `beatgen_event3.db` |

---

## 13. Follow-on specs (scope siblings — mandatory program)

See **`TECH_SPEC_BEATGEN_TRUTH_STACK_FOLLOWON_v1.md`** for H1–H9: disk drift, Dropbox conflicts, O3 async scope, milestone promotion, snapshot/restore, observability extension, kid-app catalog.

---

## 14. Shipped files (P0–P5)

| File | Role |
|------|------|
| `Production/tools/beatgen_scope.py` | Scope type, resolvers, single-writer gate, HTTP client |
| `Production/tools/beat_generator.py` | `import_delivery_clip_to_beat`, scoped `update_beat_locked`, `resolve_beat_disk_event_dir` |
| `Production/lib/beatgen_store.py` | SQLite `event_id` check on patch |
| `Production/tools/server_handlers/background.py` | `handle_bg_import_delivery_clip` |
| `Production/tools/production_server.py` | Route + `MN_BEATGEN_SERVER_WRITER=1` |
| `Production/tools/scripts/run_o3_pov_motion_i2v.py` | HTTP default for production beats |
| `Production/tools/tests/test_beatgen_truth_stack.py` | P0 repro + gates |
| `Production/tools/tests/conftest.py` | Test writer allow + singleton reset |

**Previous plan (validation + CLI bind only)** stopped **one** failure mode. It did **not** stop:

- Server handlers without fresh scope  
- Agents forever one mistake away from wrong DB  
- UI lying about active clip  
- O3 artifacts in wrong Event folder  
- Operators reading JSON mirror  

**This plan is the right plan** if the goal is **“just works right the first time, forever.”** It is larger because the bug category is larger than one import script — it is **missing truth stack architecture**.

Smallest **honest** slice: **P0 + P1 + P2 + P3 + P4 + P5** (scope object, gates, HTTP middleware, agent API, Still UI). **P6–P10** close restore, O3 parity, and visibility siblings in the same program — not a second horror-show sequel.
