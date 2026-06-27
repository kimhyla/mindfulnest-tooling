# TECH_SPEC — Beat Gen Truth Stack Follow-on V1 (Scope Siblings + Layer H)

**Status:** Required follow-on program — not optional for “forever”  
**Parent:** `TECH_SPEC_BEATGEN_TRUTH_STACK_V1.md`  
**When:** After P0–P5 ship; parallel tracks where independent

---

## 1. Why this doc exists

Truth Stack P0–P5 closes **partition authority collapse** for production beat writes. These **sibling categories** remain open and will become the next incidents without explicit specs.

---

## 2. H1 — Disk vs sidecar drift

**Category:** Artifact authority split (file on disk ≠ SQLite pointer)

**Fix:**
- Scheduled `reconcile_beat_gallery_from_disk` on explicit admin action only (not session GET hot path — Job Truth)
- Import API returns `beat.kling_o3_video_path` read-your-writes (shipped in P4)
- CI: orphan clip grep under `Event_N/kling_o3_clips/` without sidecar row → warn in deploy smoke

**Proof:** Copy clip to disk without API → admin reconcile imports → browser slot 0

---

## 3. H2 — Dropbox conflict copies

**Category:** Human/process authority (two JSON files on disk)

**Fix:**
- Startup log WARN if `*conflicted copy*` under event sidecar path
- Agent skill: never edit sidecar JSON by hand
- Optional: quarantine helper moves conflict copies to `.conflict_quarantine/`

**Proof:** Grep gate in CI for `conflicted copy` in `Production/Event_*`

---

## 4. H3 — Concurrent writers (SQLite WAL)

**Category:** Last-write-wins under parallel HTTP + subprocess

**Fix:**
- Single-writer for agents (shipped Layer 3)
- Document: one launchd plist writer per `beatgen_eventN.db`
- O3 subprocess inherits `MN_BEATGEN_ALLOW_DIRECT_WRITE=1` only when spawned from server with scope env

**Proof:** Two simultaneous import POSTs → both succeed with distinct slot indices; no torn `kling_o3_options`

---

## 5. H4 — O3 async terminal after scope change

**Category:** Job lifecycle scope tear (submit scope ≠ terminal reconcile scope)

**Fix:**
- Serialize `MN_BEATGEN_SCOPE_JSON` in O3 subprocess env (same fields as server pin)
- Terminal reconcile uses `resolve_o3_job_event_dir(beat_id, scope=…)` only — grep gate §F
- Full QA C on `event3b_full` beat after every O3 handler change

**Proof:** Submit on milestone → terminal JSON under library Event dir cited in session GET

---

## 6. H5 — Milestone ↔ event promotion

**Category:** Lifecycle undefined (beat graduates from milestone JSON to event SQLite)

**Fix:**
- Product doc: promotion = copy beats via extract/inject + new beat_ids OR manual operator runbook
- No auto-promotion without scope object
- UI badge shows milestone vs event authority (Truth Stack P8)

**Proof:** Operator runbook section + Playwright scope badge

---

## 7. H6 — Still pipeline tag matrix

**Category:** Display filter vs storage source tag

**Fix:**
- Write path: `still_insert_kling_idle` for motion+TTS on Still beats (shipped P4/P5)
- Read path: force-show active approved clip (shipped in BgTab ~541–554)
- Export/stitch reads active pointer only after scope validation

**Proof:** Browser Beat 9 slot 0 video + Ember TTS

---

## 8. H7 — Snapshot / restore per-event

**Category:** Restore writes wrong DB shard

**Fix:**
- Snapshots include `beatgen_eventN.db` per event
- Restore script sets `MN_BEATGEN_DB_PATH` before bootstrap
- `MN_SIDECAR_ALLOW_FULL_REPLACE=1` only in restore scripts

**Proof:** Restore Event_3 snapshot → session-state beat count unchanged on :5113

---

## 9. H8 — Observability (mandatory)

**Category:** Post-mortem blindness

**Fix (partially shipped):**
- Structured `[beatgen_mutation]` JSON log on every `update_beat_locked`
- Extend to HTTP import + select-o3 + trim handlers
- Optional: aggregate to Sentry breadcrumb via wrapper (no direct `@sentry` in handlers)

**Proof:** grep server log for `beatgen_mutation` after import POST

---

## 10. H9 — Kid app / catalog downstream

**Category:** Parallel truth layer (tooling vs MindfulNest catalog)

**Fix:** Separate spec when stitch export registers to kid app — out of Beat Gen scope but must be linked in operator runbook

---

## 11. Implementation order

| Priority | Spec | Depends on |
|----------|------|------------|
| 1 | H8 observability extension | P1 shipped |
| 2 | H4 O3 scope env | P7 |
| 3 | H1 disk reconcile admin | Job Truth |
| 4 | H7 snapshot/restore | P9 |
| 5 | H2 Dropbox conflicts | ops |
| 6 | H5 promotion runbook | P8 badge |

---

## 12. CI gates (add to smoke.yml)

```bash
# No Event_1 default on beat-touching CLIs
rg 'default="Event_1"' Production/tools/scripts --glob '*.py' && exit 1 || true

# Truth stack tests required on Beat Gen PR
pytest tests/test_beatgen_truth_stack.py -v
```
