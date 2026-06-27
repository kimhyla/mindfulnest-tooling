# Beat Gen — O3 Job Lifecycle & Audit Spec v2

**Status:** Approved target architecture — 2026-06-21  
**Owner:** mindfulnest-tooling (`Production/tools/`, `storyboard-v2/`)  
**Supersedes:** `BG_O3_JOB_LIVENESS_AUDIT_SPEC_v1.md` (v1 was a patch spec; v2 is the permanent design)  
**Amends:** `BG_BEAT_JOB_TRUTH_GALLERY_SPEC_v1.md` §1 #11, §4.3, §6 — see §2 below  
**Motivation:** Nav Beat 4 (`bg_arc1_event2_post_beat_03`) stuck on “Generating g4…” after dead subprocess + missing terminal (`f2db16c2`). Partial fixes shipped on `feat/bg-job-truth-complete`; this spec defines the **finished** system — no interim layers, no grace-window guessing, no GET-only heal that lies to the operator.

**Operator promise:** Generate is busy **only while a job is actually running**. Restart, deploy, hard refresh, or overnight sleep never leave a beat stuck. When a job fails, Kim sees it on the beat card **and** can re-submit immediately. Disk sidecar, session GET, poll, and UI always agree.

---

## 1. Scope

### In scope

- O3 element-native and voice-first pipelines
- Terminal lifecycle, busy authority, submit gates, reconcile, poll, session GET
- Client busy/poll/toast/refresh behavior in Beat Gen
- Deploy verification (Option B)
- Sidecar merge preserve fields for job cache
- All audit categories **A–O** below

### Out of scope (unchanged product boundaries)

- Gallery pin-slot semantics and additive disk repair rules (gallery spec owns this)
- New operator “Repair from disk” buttons (admin-reconcile remains agent/operator API)
- Regenerating clips to recover from failed attempts
- **Kling V2 lint on still-insert beats** — still-insert rows use Still+TTS prompts, not `@Image1` O3 motion shape; deploy smoke skips via `beat_is_still_insert` + `is_still_insert_prompt_text`

---

## 2. Permanent architecture (single source of truth)

v1 spread authority across pointer, intent, log mtime, pgrep, in-memory dict, and session GET projection. **v2 collapses to one model.**

### 2.1 Authority table

| Layer | Role | Busy authority? |
|-------|------|-----------------|
| **`{job_id}_terminal.json`** | **Sole lifecycle authority** | **Yes** — `status: running` means busy (if subprocess/PID confirms liveness) |
| **`beat.o3_current_job_id`** | Denormalized pointer to open attempt | **No** — cache only; must match terminal |
| **`{job_id}_intent.json`** | Immutable submit audit snapshot | **No** — never blocks Generate after terminal closes |
| **`{job_id}.pid` + `{job_id}.heartbeat`** | Subprocess liveness (written at spawn) | Input to liveness only |
| **`kling_o3_options` / `kling_o3_video_path`** | Gallery | **No** |
| **`_ARLO_O3_JOBS`** | In-memory poll acceleration | **No** — rebuild from terminal + PID on restart |
| **Pipeline log** | Debug / recovery hints | **No** — not used for busy |

### 2.2 Terminal state machine (permanent)

```
submit → terminal.status = "running"  (written under sidecar lock with pointer set)
       → spawn pipeline, write PID file + initial heartbeat
       → pipeline updates heartbeat during work
       → terminal.status ∈ {done, failed, done_with_warning, cancelled}
       → clear pointer + heal gallery row on same persist path
```

**New terminal status:** `running` (non-terminal for busy purposes).  
**Terminal statuses (closed):** `done`, `failed`, `done_with_warning`, `cancelled`.

**Busy rule (`beat_job_busy`):**

```
busy = (
  terminal exists AND terminal.status == "running"
  AND subprocess_or_pid_file_is_live(job_id, beat_id)
)
OR (
  terminal missing AND intent committed < 15s ago AND spawn in flight
  — spawn-failure window only; if spawn fails, write failed terminal immediately
)
```

**Removed as busy inputs (delete from code, not “deprecate”):**

- Log mtime grace (`O3_PIPELINE_LOG_GRACE_S = 600`)
- Intent-without-terminal lock (`beat_has_active_intent` as submit gate)
- `log_indicates_active_o3_pipeline` as liveness oracle
- Session GET in-response projection heal (cleared pointer / synthetic `approved` without persist)
- Pointer-without-terminal → busy (gallery spec §4.3 step 5 — superseded)

### 2.3 Single closer: `close_o3_attempt()`

All paths that end an attempt call **one function** in `o3_generation_intent.py`:

```python
close_o3_attempt(
    job_id, beat_id, event_dir,
    terminal_status,  # failed | done | done_with_warning | cancelled
    reason, phase_last,
    persist_beat=True,  # always True except unit tests
)
```

**Responsibilities (atomic under `mutate_sidecar_locked`):**

1. Write or update `{job_id}_terminal.json` (terminal status ≠ `running`)
2. Clear `O3_JOB_CACHE_FIELDS` on beat row
3. Set `kling_o3_voice_fix_error` when failed (operator-visible on beat card)
4. Heal to `status: approved` when prior delivery clip exists on disk
5. Never touch gallery options except via existing finalize/delivery paths

**Callers (only these):**

| Caller | When |
|--------|------|
| Pipeline subprocess | Normal done / failed exit |
| Poll handler | Reads terminal `running` + liveness false → `close_o3_attempt(failed, …)` |
| **Blocking startup reconcile** | Before HTTP accept — every open `running` terminal with dead subprocess |
| Admin reconcile | Operator/API forced sweep |
| Spawn failure handler | Intent committed but subprocess did not start |

Poll **does not** invent lifecycle state — it reads terminal and closes orphans via `close_o3_attempt`.

### 2.4 Subprocess liveness (permanent, not pgrep-primary)

At pipeline spawn, server writes:

- `{job_id}.pid` — OS pid
- `{job_id}.heartbeat` — touched every 30s by pipeline (or on each log phase)

**Liveness check order:**

1. PID file exists and `_pid_is_running(pid)`
2. Else heartbeat mtime ≤ **90s** (permanent constant `O3_HEARTBEAT_STALE_S`)
3. Else **not live** → `close_o3_attempt(failed, "subprocess lost or server restart")`

`subprocess_running_for_o3_job` (pgrep) remains a **fallback** for legacy in-flight jobs during migration only; remove once PID files are universal on all pipeline entrypoints.

### 2.5 Session GET — honest read-only

**Rule:** Session GET returns **disk truth** after startup reconcile. No synthetic beat overlay.

- `_enrich_beats_job_busy` sets **`job_busy` only** from `beat_job_busy()` (terminal + PID model).
- **Remove** in-response pointer clear, status rewrite, and error injection without persist.
- Gallery fields in GET must match sidecar on disk (gallery spec §1 #11 restored literally).

**Why this is safe:** Blocking startup reconcile (§2.6) runs before first session-state — disk is already healed when Kim loads Beat Gen.

### 2.6 Blocking startup reconcile (permanent)

Before production server accepts HTTP traffic:

1. For each event in scope (pinned event + any event with open `running` terminals under `Production/Event_*/arlo_o3_jobs/`):
   - Scan `*_terminal.json` where `status == "running"`
   - If not live → `close_o3_attempt(failed, …, persist_beat=True)`
2. Run existing admin reconcile hooks (gallery repair, stale intent) **synchronously**
3. **Fail server start** if any beat still has `running` terminal + dead subprocess after sweep (operator must run admin-reconcile or fix disk — do not serve lying GET)

Replaces: async `schedule_o3_admin_reconcile_at_startup` as the **only** authority for post-restart heal.

### 2.7 Submit gate (single gate)

**Generate POST blocked only when:**

```python
beat_job_busy(beat, event_dir, in_memory_jobs=...)  # terminal running + live
```

**Remove from `build_generation_intent`:**

```python
if beat_has_active_intent(bid, event_dir):  # DELETE this gate
    raise IntentCommitError("INTENT_JOB_ACTIVE", ...)
```

`beat_has_active_intent` may remain as a **diagnostic** helper for reconcile; it must **never** block submit when terminal is closed or `job_busy` is false.

**On submit success:** write terminal `running` + set `o3_current_job_id` + spawn pipeline **in one locked sidecar mutation** before returning 200.

### 2.8 Sidecar merge preserve (permanent)

Add all `O3_JOB_CACHE_FIELDS` from `o3_job_status_contract.py` to `SIDECAR_MERGE_PRESERVE_FIELDS` in `beat_generator.py` so extract/reconcile/merge never drops job pointer or PID metadata mid-attempt.

---

## 3. Audit categories A–O

Each category: **Purpose**, **Pass criteria**, **Automated gate**, **Implementation note** (simplest permanent fix).

---

### Category A — Terminal + PID liveness matrix

**Purpose:** Busy reflects **running terminal + live subprocess**, never pointer or log age alone.

| Case | Terminal | PID/heartbeat | Expected `job_busy` |
|------|----------|---------------|---------------------|
| A1 | `running` | live | `true` |
| A2 | `running` | stale/dead | `false` after first observe closes attempt |
| A3 | `failed` / `done` / `cancelled` | any | `false` |
| A4 | missing | spawn in flight (<15s) | `true` |
| A5 | missing | spawn failed / >15s | `false` + terminal `failed` on disk |

**Automated gate:** `tests/test_o3_job_liveness.py` — full matrix; **no pgrep mocks** in A1/A2 (use PID file fixtures).

**Implementation:** Replace log-grace liveness in `o3_job_attempt_is_live` with terminal+PID model; delete `O3_PIPELINE_LOG_GRACE_S` and permissive `log_indicates_active_o3_pipeline` fallback (`phase` truthy → active).

---

### Category B — Post-restart recovery

**Purpose:** Server restart mid-O3 never leaves infinite “Generating…”.

**Pass criteria:**

1. Submit O3 on test beat → `job_busy: true`, terminal `running`, poll `running`.
2. Kill server (`launchctl kickstart -k`).
3. Server restart completes blocking startup reconcile.
4. First session GET: `job_busy: false`, terminal `failed` on disk, pointer cleared, prior g1–g3 visible.
5. Generate POST returns **200** (not 409).

**Automated gate:** `tests/test_o3_stuck_job_recovery.py::test_restart_clears_running_terminal_when_subprocess_dead` — clear in-memory jobs, stale PID, assert startup reconcile persists.

**Manual gate:** Required in Full QA for any O3 lifecycle merge.

---

### Category C — Nav index ↔ beat_id map

**Purpose:** QA never assumes nav label == storyboard beat suffix.

**Simplest permanent fix:** Frozen map + pytest (no DOM change required).

**Event_2 resolution map:**

| Nav | `beat_id` |
|-----|-----------|
| 1 | `bg_arc1_event2_post_beat_01` |
| 2 | `bg_arc1_event2_post_beat_02` |
| 3 | `bg_arc1_event2_post_beat_07` |
| 4 | `bg_arc1_event2_post_beat_03` |
| 5 | `bg_arc1_event2_post_beat_04` |
| 6 | `bg_arc1_event2_post_beat_05` |
| 7 | `bg_arc1_event2_post_beat_06` |

**Automated gate:** `tests/test_bg_nav_beat_id_map.py` — GET session-state, assert beat order matches table. Update table when segment reordered.

**Manual gate:** QA report cites nav index + `beat_id`.

---

### Category D — Poll and beat-card failure surface

**Purpose:** Operator always sees failure; poll never returns perpetual `running`.

**Pass criteria:**

- Poll: terminal `running` + not live → `close_o3_attempt` → response `status: failed`, `intent_zombie_recovery: true`.
- **Beat card** shows `kling_o3_voice_fix_error` (or equivalent) after failed close — **not toast-only**.
- Client poll pushes error toast on `status === 'failed'`.
- Session GET after close shows same error string from **disk** (no projection).

**Automated gate:**

- Server: `tests/test_o3_job_liveness.py::test_poll_closes_running_terminal_when_pid_stale`
- Client: contract test — failed poll clears `activeO3Jobs` and beat card shows error
- Server: `tests/test_o3_session_tier_architecture.py` updated — GET must not mutate beat dict except `job_busy` derivation

**Removed:** Client 45-minute wall-clock poll cap (unnecessary when server obeys terminal model).

---

### Category E — Admin reconcile

**Purpose:** Explicit operator/agent sweep closes stuck beats on disk.

**Pass criteria:**

1. Seed: terminal `running`, dead PID, sidecar pointer set.
2. `POST /api/bg/o3/admin-reconcile` `{ "scope_event_id": "Event_2", "force": true }`.
3. Terminal `failed`, pointer cleared, `status: approved` if prior clip exists.
4. All reconcile paths call `close_o3_attempt(persist_beat=True)` — no `persist_beat=False` in production code paths.

**Automated gate:** `test_reconcile_closes_busy_pointer_orphan_post_beat_03_shape` + `test_reconcile_skips_when_subprocess_still_running`.

---

### Category F — Deploy + in-flight O3 (Option B integrated)

**Purpose:** Every deploy proves O3 busy state before and after restart.

**Permanent fix:** Extend `Production/scripts/verify_deploy_option_b_live.sh` with step **(6/6) O3 busy inventory**:

1. **Pre-restart:** `GET /api/bg/session-state?scope_event_id=Event_N&scope_video_role=resolution` — record all beats with `job_busy: true` (`beat_id`, `o3_current_job_id`).
2. Run deploy (includes launchd restart).
3. **Post-restart:** Same session-state query for recorded beat_ids.
4. **Pass:** Each either `job_busy: false` with gallery intact, or terminal `failed` on disk + error on beat row.
5. **Fail deploy script** if any beat has terminal `running` + dead PID after startup reconcile.

**Automated gate:** Step 6 in `verify_deploy_option_b_live.sh` (blocking — not a separate deferred script).

---

### Category G — Deploy sha parity (UI + Python)

**Purpose:** Prove operator tab **and** server handlers match deployed commit.

**Pass criteria:**

| Artifact | Check |
|----------|--------|
| UI bundle | `[data-testid="app-build-sha"]` and HTML `meta[name="build-sha"]` == `git rev-parse --short HEAD` |
| Python | `curl` response header `X-Tooling-Sha` or `/api/server/info` field == same HEAD |
| Parity | `verify_tooling_dropbox_parity.py` exit 0 |

**Automated gate:** Steps 2–5 of Option B verify (existing) + new Python sha step in same script.

**Manual gate:** Hard refresh before Beat Gen smoke.

---

### Category H — Submit re-open invariant

**Purpose:** `job_busy: false` implies Generate POST succeeds (not 409).

**Pass criteria:**

- After any failed/lost attempt: session GET `job_busy: false` → `POST` generate returns 200.
- No `INTENT_JOB_ACTIVE` when terminal is closed.

**Automated gate:** `tests/test_o3_submit_reopen.py` — seed failed terminal + stale intent file, assert submit succeeds.

**Implementation:** Remove `beat_has_active_intent` gate from `build_generation_intent` (§2.7).

---

### Category I — Sidecar merge preserve

**Purpose:** Extract/merge never drops `o3_current_job_id` or PID cache mid-job.

**Pass criteria:** `SIDECAR_MERGE_PRESERVE_FIELDS` includes every field in `O3_JOB_CACHE_FIELDS`.

**Automated gate:** `tests/test_sidecar_merge_preserves_o3_job_cache.py`.

**Implementation:** One-line tuple extension in `beat_generator.py` (§2.8).

---

### Category J — Disk parity (GET = sidecar)

**Purpose:** Session GET fields match persisted sidecar — no phantom heal.

**Pass criteria:**

- After startup reconcile + failed close: read sidecar JSON from disk and session GET — `status`, `o3_current_job_id`, `kling_o3_voice_fix_error`, `job_busy` match.
- `_enrich_beats_job_busy` does not mutate beat dict except adding `job_busy` (and `o3_current_job_id` mirror for poll convenience when busy).

**Automated gate:** `tests/test_o3_session_disk_parity.py`.

**Implementation:** Remove projection heal from `background.py`; rely on §2.6.

---

### Category K — Client: busy without pollable job_id

**Purpose:** Never show “Generating…” with no poll loop.

**Pass criteria:**

- Server: when `job_busy: true`, session GET always includes non-empty `o3_current_job_id`.
- Client: if `job_busy` true and no job id for **>5s**, force `refreshState()`; if still missing, show beat-card error “job id missing — refresh or admin-reconcile”.

**Automated gate:** Client unit test on `collectActiveO3JobsFromBeats` + server contract test.

---

### Category L — Subprocess detection contract

**Purpose:** Liveness does not depend on fragile pgrep alone.

**Pass criteria:**

- Every pipeline spawn writes PID + heartbeat files.
- Integration test: live PID → busy; kill PID → next poll/startup closes attempt.
- pgrep fallback covered by one regression test then removed when migration complete.

**Automated gate:** `tests/test_o3_pid_heartbeat_liveness.py`.

**Implementation:** Pipeline entrypoints in `kling_o3_element_beat_pipeline.py` and voice pipeline wrapper.

---

### Category M — Authority parity (Python ↔ TypeScript ↔ scripts)

**Purpose:** One busy contract everywhere.

**Pass criteria:**

- UI Generate: `beatO3JobBusy` ← `job_busy` only.
- Nav error badges: **remove** `beatO3JobLooksRunning` as authority; use `job_busy` + `kling_o3_voice_fix_error`.
- Soak scripts (`bg_arc_soak.sh`) use session-state API or terminal files, not raw sidecar pointer alone.

**Automated gate:** Shared constants test or TS/Python contract snapshot (`tests/test_o3_authority_parity.py`).

---

### Category N — Event-pin terminal durability

**Purpose:** Event pin drift cannot suppress terminal write after pipeline work.

**Pass criteria:**

- Pipeline `write_intent_terminal` / `close_o3_attempt` runs **outside** pin-abort path for terminal files (pin guards clip registration, not job lifecycle).
- If pin aborts clip registration, terminal still reaches `failed` or `done` with clear error.

**Automated gate:** `tests/test_o3_terminal_survives_event_pin_abort.py`.

---

### Category O — Client refresh failure

**Purpose:** Silent session GET failure cannot leave stale busy UI.

**Pass criteria:**

- When `refreshState` fails while any beat has local busy latch, push **error toast** with retry.
- Wake/`visibilitychange` refresh uses same path.

**Automated gate:** Client unit test on failed fetch → toast + retry scheduled.

**Implementation:** `BgTab.tsx` `refreshState` error branch.

---

## 4. Root problems — permanent fixes (mapped)

| # | Root problem | v2 fix |
|---|--------------|--------|
| 1 | Distributed job authority | Terminal FSM + `close_o3_attempt` (§2) |
| 2 | GET projection vs disk drift | Honest GET + blocking startup reconcile (§2.5–2.6) |
| 3 | Dual submit gate (`beat_has_active_intent`) | Category H — single `beat_job_busy` gate |
| 4 | Merge drops job cache fields | Category I |
| 5 | Log mtime + pgrep liveness | Category A + L — PID/heartbeat |
| 6 | Client latch cousins | Categories K, O, M |

---

## 5. Operator-visible outcomes (finished system)

| Situation | What Kim sees |
|-----------|----------------|
| g4 running normally | “Generating g4…” until terminal closes |
| Server restart mid-job | On reload: failed message on beat card, Generate enabled, g1–g3 unchanged, re-submit works |
| Deploy during job | Deploy script fails or post-check shows failed terminal — agent fixes before Kim continues |
| Hard refresh | Same as disk — no flicker between “healed” and stale |
| Admin reconcile | Stuck beats clear on disk; next GET matches |

---

## 6. Implementation sequence

Ordered work items — **all required** for spec compliance, not optional phases.

| Order | Work | Categories |
|-------|------|------------|
| 1 | `close_o3_attempt()` + terminal `running` at submit | A, E |
| 2 | PID + heartbeat at spawn; liveness rewrite | A, L |
| 3 | Blocking startup reconcile | B, J |
| 4 | Remove GET projection heal; honest GET | J |
| 5 | Remove `beat_has_active_intent` submit gate | H |
| 6 | `SIDECAR_MERGE_PRESERVE_FIELDS` extension | I |
| 7 | Poll → read terminal + close only | D |
| 8 | Client: error on card, refresh failure toast, nav authority | D, K, M, O |
| 9 | Option B verify step 6 + Python sha | F, G |
| 10 | Nav map test + remaining pytest matrix | C, all |

**Gallery spec amendment:** Update §1 #11 to “only `job_busy` is derived; lifecycle fields on GET must match disk after startup reconcile.” Update §4.3 busy algorithm to terminal+PID model. Mark intent as audit-only in §6 (remove submit lock).

---

## 7. Full QA template (mandatory)

```
O3 Full QA (v2):
- [ ] Categories A–O pytest gates green
- [ ] Category B manual or automated restart proof
- [ ] Category C: nav index + beat_id in report
- [ ] Category F: verify_deploy_option_b_live.sh step 6 pass
- [ ] Category G: UI sha + Python sha match HEAD
- [ ] Category H: submit re-open curl proof on touched beat
- [ ] Category J: disk vs GET field match on failed-close beat
- [ ] Browser: nav beat shows error on card when failed (not toast-only)
- [ ] Commit on feature branch
```

---

## 8. References

- Incident: `bg_arc1_event2_post_beat_03` (nav Beat 4), job `f2db16c2`
- Gallery spec: `BG_BEAT_JOB_TRUTH_GALLERY_SPEC_v1.md` (requires amendment per §6)
- Deploy: `Production/scripts/deploy_option_b.sh`, `verify_deploy_option_b_live.sh`
- v1 spec (superseded): `BG_O3_JOB_LIVENESS_AUDIT_SPEC_v1.md`
