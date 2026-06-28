# Beat Gen — O3 Job Liveness Audit & QA Spec v1

> **Superseded by `BG_O3_JOB_LIVENESS_AUDIT_SPEC_v2.md`** (2026-06-21). v1 described a patch layer; v2 is the permanent terminal+PID architecture. Do not implement from v1.

**Status:** Superseded — 2026-06-21  
**Owner:** mindfulnest-tooling (`Production/tools/`, `storyboard-v2/`)  
**Depends on:** `BG_BEAT_JOB_TRUTH_GALLERY_SPEC_v1.md` (job_busy authority, session GET read-only)  
**Motivation:** Nav Beat 4 (`bg_arc1_event2_post_beat_03`) stuck on “Generating g4…” after dead subprocess + missing terminal (`f2db16c2`, 2026-06-20). Category fix shipped in `feat/bg-job-truth-complete` (O3 liveness layer).

**Scope:** This spec defines **seven audit categories** that were missing from prior QA. It does **not** replace the job-truth gallery spec; it adds mandatory verification gates so orphan O3 jobs cannot silently stick again.

**Out of scope (explicit):**
- Changing gallery pin-slot semantics or additive disk repair rules
- Session GET sidecar persist (remains read-only)
- New operator-facing “Repair” buttons
- Regenerating clips to recover from failed attempts
- Intro canonical prompt smoke (Event_2 beat 31) — separate track

---

## 1. Locked truth model (unchanged)

| Layer | Authority |
|-------|-----------|
| **Busy** | `beat_job_busy()` → `job_busy` on session GET. Busy requires **liveness** (subprocess, in-memory job, or fresh intent/log grace). Pointer alone is **not** busy. |
| **Terminal** | `{job_id}_terminal.json` with status ∈ `{done, failed, done_with_warning, cancelled}` |
| **Gallery** | Sidecar `kling_o3_options` / `kling_o3_video_path` — never busy authority |
| **Intent** | `{job_id}_intent.json` — audit + liveness input only |

**Liveness constants (code):**
- `O3_SUBMIT_INTENT_GRACE_S = 45` — brand-new submit before log exists
- `O3_PIPELINE_LOG_GRACE_S = 600` — log mtime + active phase still counts as live

**Subprocess detection:** Must match **both** pipeline scripts:
- `kling_o3_element_beat_pipeline.py` (element native)
- `arlo_o3_voice_pipeline.py` / `o3_voice_pipeline` (voice-first)

---

## 2. Seven audit categories

Each category has: **Purpose**, **Trigger**, **Pass criteria**, **Automated gate**, **Manual proof (Kim path)**.

### Category A — O3 liveness matrix

**Purpose:** Pointer + no terminal + dead subprocess must never report busy.

| Case | Subprocess | Terminal | Log age | Expected `job_busy` |
|------|------------|----------|---------|---------------------|
| A1 | running | none | any | `true` |
| A2 | dead | none | ≤600s, active phase | `true` |
| A3 | dead | none | >600s, `o3_submit` only | `false` |
| A4 | dead | `failed` | any | `false` |
| A5 | dead | none | ≤45s since intent commit | `true` (submit grace) |

**Automated gate:** `tests/test_o3_job_liveness.py` (required in CI pytest suite).

**Manual proof:** `curl session-state` for beat with known orphan → `job_busy: false`.

---

### Category B — Post-restart recovery

**Purpose:** Server restart mid-O3 must not leave infinite “Generating…”.

**Procedure:**
1. Submit element-native O3 on a test beat (Event_2 resolution, nav item with spare slot).
2. Confirm `job_busy: true` and poll returns `running`.
3. Kill server (`launchctl kickstart -k` or deploy restart).
4. Hard refresh Beat Gen.
5. Within one poll cycle + one session GET: `job_busy: false` OR poll returns `failed` with message containing “subprocess lost or server restart”.
6. Prior approved clip (g1–g3) still visible; prompt editable.

**Automated gate:** Integration test in `tests/test_o3_stuck_job_recovery.py` extended with restart simulation (mock in-memory jobs cleared + stale log fixture).

**Manual proof:** Required before merge of any O3 lifecycle change.

---

### Category C — Nav index ↔ beat_id map

**Purpose:** QA scripts must not assume nav label == storyboard beat suffix.

**Event_2 resolution canonical map (2026-06-21):**

| Nav | `beat_id` |
|-----|-----------|
| 1 | `bg_arc1_event2_post_beat_01` |
| 2 | `bg_arc1_event2_post_beat_02` |
| 3 | `bg_arc1_event2_post_beat_07` |
| 4 | `bg_arc1_event2_post_beat_03` |
| 5 | `bg_arc1_event2_post_beat_04` |
| 6 | `bg_arc1_event2_post_beat_05` |
| 7 | `bg_arc1_event2_post_beat_06` |

**Automated gate:** `tests/test_bg_nav_beat_id_map.py` — parses session-state order vs frozen map above (update map when segment reordered).

**Manual proof:** Browser smoke cites **both** nav index and `beat_id` in QA report.

---

### Category D — Poll zombie / stale running

**Purpose:** Poll must not return `running` when subprocess is dead and grace expired.

**Pass criteria:**
- `_recover_o3_job_from_intent_terminal` returns `failed` + `intent_zombie_recovery: true` when liveness false.
- Client poll loop surfaces **error toast** with failure message (not silent loop).

**Automated gate:**
- Unit: poll recovery path in `tests/test_o3_job_liveness.py` (handler-level test via import of `_recover_o3_job_from_intent_terminal`).
- Contract: `BgTab.tsx` poll branch pushes toast on `status === 'failed'`.

**Optional Phase 2 (not in v1 code):** Client wall-clock cap (e.g. 45 min) if server misbehaves — spec only, implement only if Category D unit tests pass for 30 days.

---

### Category E — Reconcile effectiveness on busy pointer

**Purpose:** Admin reconcile must close the **specific** stuck beat, not only unrelated orphans.

**Procedure:**
1. Seed sidecar with `o3_current_job_id`, `status: o3_element_running`, stale log at `o3_submit`, no terminal.
2. `POST /api/bg/o3/admin-reconcile` `{ "scope_event_id": "Event_2", "force": true }`.
3. `{job_id}_terminal.json` exists with `status: failed`.
4. Sidecar beat: pointer cleared, `status: approved` if prior delivery exists.

**Automated gate:** `test_reconcile_closes_busy_pointer_orphan_post_beat_03_shape` in `tests/test_o3_job_liveness.py`.

**Must not regress:** Reconcile skip when `subprocess_running_for_o3_job` true (`test_reconcile_skips_when_subprocess_still_running`).

---

### Category F — Deploy safety (in-flight O3)

**Purpose:** Deploy/restart during active O3 must be followed by verification, not assumed clean.

**Deploy checklist (agent-run, append to Full QA report):**
1. Before deploy: `curl session-state` — list beats with `job_busy: true` (record beat_ids).
2. Run deploy + server restart.
3. After deploy: re-fetch session-state for those beat_ids.
4. For each previously busy beat: either `job_busy: false` + approved gallery restored, or explicit `failed` terminal + error on beat card.
5. If any beat still `job_busy: true` with dead subprocess → **block ship**, run admin-reconcile, re-check.

**Automated gate:** Script `Production/scripts/verify_o3_post_deploy_busy.sh` (to be added in Phase 2 — not blocking v1 category fix).

---

### Category G — Build-sha in operator tab

**Purpose:** Browser QA must prove the operator’s **actual tab** runs the deployed bundle.

**Pass criteria:**
- `[data-testid="app-build-sha"]` text === `git rev-parse --short HEAD` on tooling branch deployed to Event_N.
- Hard refresh (not soft navigation) before Beat Gen smoke.

**Automated gate:** Playwright or browser CDP step in deploy smoke (Phase 2).  
**Manual gate (mandatory now):** Agent captures build-sha from CDP + curl HTML meta tag; both must match HEAD.

---

## 3. Full QA template (Beat Gen O3 changes)

When any O3 lifecycle / busy / poll / reconcile code changes:

```
O3 Full QA:
- [ ] Category A pytest: test_o3_job_liveness.py + test_o3_stale_intent_reconcile.py
- [ ] Category B: restart simulation or documented manual proof
- [ ] Category C: cite nav index + beat_id for touched beats
- [ ] Category D: poll returns failed for f2db16c2-class fixture
- [ ] Category E: admin-reconcile closes busy pointer fixture
- [ ] Category F: pre/post deploy busy beat inventory
- [ ] Category G: build-sha match in browser + curl
- [ ] Commit on feature branch
- [ ] Deploy Event_2 + server 5112 HTTP 200
```

---

## 4. Operator-visible outcomes (after category fix)

| Situation | What Kim sees |
|-----------|----------------|
| g4 submit, server restart, subprocess dead | Generate unlocks; toast: job failed (subprocess lost…); g1–g3 tiles unchanged |
| g4 submit, still running | “Generating g4…” until terminal or grace expiry |
| Hard refresh during live job | `job_busy` from server; no client-only infinite latch |
| Admin reconcile | Stuck beats clear without manual sidecar edit |

---

## 5. Implementation map (v1 category fix)

| Component | Change |
|-----------|--------|
| `o3_generation_intent.py` | `o3_job_attempt_is_live`, `finalize_o3_job_lost_attempt`, element pipeline pgrep, reconcile skip uses liveness not legacy busy |
| `o3_job_status_contract.py` | `beat_job_busy` false when not live |
| `background.py` | Poll zombie → failed + persist; session GET projects healed beat when zombie |
| `tests/test_o3_job_liveness.py` | Category A + E fixtures |

---

## 6. Phase 2 backlog (spec only — do not implement unless requested)

1. `verify_o3_post_deploy_busy.sh` (Category F automation)
2. Playwright Beat Gen nav map smoke (Category C + G)
3. Client poll wall-clock timeout (Category D belt-and-suspenders)
4. Session GET optional async heal queue (only if operator still sees drift after v1 — **not** default)

---

## 7. References

- Incident beat: `bg_arc1_event2_post_beat_03` (nav Beat 4), job `f2db16c2`, log stuck at `o3_submit`, no g4 delivery
- Spec: `BG_BEAT_JOB_TRUTH_GALLERY_SPEC_v1.md`
- Tests: `tests/test_o3_job_liveness.py`, `tests/test_o3_stale_intent_reconcile.py`, `tests/test_bg_job_truth_gallery.py`
