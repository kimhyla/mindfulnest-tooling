# TECH_SPEC — Beat Gen Truth Stack Siblings V2 (H1–H9 + P10 closeout)

**Status:** Authoritative follow-on to Truth Stack P0–P10  
**Parent:** `TECH_SPEC_BEATGEN_TRUTH_STACK_V1.md`  
**Supersedes:** `TECH_SPEC_BEATGEN_TRUTH_STACK_FOLLOWON_v1.md` (outline only — this doc is executable)  
**Branch target:** `fix/beatgen-truth-stack-v1` → merge to `main`  
**When:** After P3–P9 ship on dedicated ports; each sibling is a **category fix** with mandatory Full QA

---

## Category-unlocker (mandatory before any sibling code change)

- **Bug category:** *(one of H1–H9 below)*
- **Category fix:** *(closes the class, not one beat)*
- **Fix type:** CATEGORY | PATCH
- **Compelling reason (if PATCH):** …
- **Plan:** repro → unit → deploy/restart → API proof → browser → hard refresh repeat

---

## 1. What “same diligence as Truth Stack” means

Every sibling ships with:

1. **Reproduce first** — curl/log/file path evidence before edit  
2. **Category fix** — no operator checklist without code gate  
3. **Multipass at every boundary** — pytest → mirror Dropbox → restart → `build-sha` → user-path browser  
4. **No heal-before-proof** — hard refresh on cold load before manual fixes  
5. **Commit on branch** — “fixed in chat” is not shipped  
6. **Mandatory proof checklist** (§8) — all applicable rows checked with evidence  
7. **Taxonomy pass** (§9) — before closing the sibling  
8. **Never** Cursor Find Issues / Bugbot — CI + pre-push + Full QA template  

Deliverable per sibling: **Full QA — [Hn title]** block (§8 template).

---

## 2. Relationship to Truth Stack P0–P10

| Truth Stack phase | Status (2026-06-27) | Evidence |
|-------------------|---------------------|----------|
| P0–P2 | DONE | `test_beatgen_truth_stack.py`, single-writer gate |
| P3 | DONE | `rebind_bg_paths_from_app` on mutation `_assert_event_scope` |
| P4 | DONE | `/api/bg/import-delivery-clip`, agent rule |
| P5 | DONE | Event_3 Beat 9 Still+TTS slot browser proof |
| P6 | DONE | `verify_beatgen_truth_stack_durability.sh` |
| P7 | DONE | `MN_BEATGEN_SCOPE_JSON`, O3 bootstrap resolver sweep |
| P8 | DONE | `bg-authority-badge`, Playwright extension |
| P9 | PARTIAL | Snapshot **includes** `beatgen_eventN.db`; **restore script** = S4 (H7) |
| P10 | PARTIAL | `:5111–5113` deploy smoke + build-sha; `:5114+` = S9 |

**Sibling program (S1–S9)** closes H1–H9 and finishes P9/P10.

---

## 3. Sibling phases (implementation order — all required)

| Phase | Maps to | Deliverable | Closes |
|-------|---------|-------------|--------|
| **S1** | H8 | `log_beatgen_mutation` on all BG write handlers; grep gate | Post-mortem blindness |
| **S2** | H4 | Milestone `event3b` Generate Full QA C; terminal resolver grep sweep | O3 scope tear |
| **S3** | H1 | Admin disk reconcile contract + orphan-clip deploy **warn** | Disk ≠ sidecar |
| **S4** | H7 | `restore_beatgen_event_snapshot.sh` + restore Full QA | Wrong shard on restore |
| **S5** | H2 | Startup conflict-copy WARN + CI grep gate | Dropbox dual-authority |
| **S6** | H3 | Concurrent import test + launchd single-writer doc in spec | WAL last-write-wins |
| **S7** | H5 | Milestone→event promotion runbook (no auto-promote) | Lifecycle undefined |
| **S8** | H6 | Export/stitch scope validation grep; regression test | Tag matrix drift |
| **S9** | H9 + P10 | All dedicated ports smoke; kid-app link doc; PR merge | Ship proof |

**Parallel track (MindfulNest app):** H9 kid-app catalog is **out of tooling repo** — link only in operator runbook §S9.

---

## 4. S1 — H8 Observability extension

### Category
Post-mortem blindness — mutations without structured scope in logs.

### Category fix
Every Beat Gen **write** handler emits `[beatgen_mutation]` JSON with `scope_event_id`, `db_path`, `operation`, `beat_id`, `caller`.

### Deliverables
| Item | Location |
|------|----------|
| Core logger | `beatgen_scope.log_beatgen_mutation` (exists) |
| Wired today | `update_beat_locked`, `import_delivery_clip_to_beat` |
| **S1 remaining** | `handle_bg_select_o3_video`, `handle_bg_kling_o3_trim`, `handle_bg_render_still_clip`, export-to-stitcher write path |
| Grep gate | `verify_beatgen_siblings_durability.sh` |

### Full QA proof
```bash
curl -X POST http://127.0.0.1:5113/api/bg/import-delivery-clip ... 
# server log must contain: [beatgen_mutation] {"operation":"update_beat_locked",...}
```

---

## 5. S2 — H4 O3 async terminal after scope change

### Category
Job lifecycle scope tear — submit dir ≠ terminal reconcile dir (milestone `event3b`).

### Category fix
- `MN_BEATGEN_SCOPE_JSON` in O3 subprocess env (**shipped P7**)
- Terminal reconcile uses `resolve_o3_job_event_dir` / `_o3_job_event_dir(h, beat_id)` only — **no** bare `event_dir_for_beat_id` on lifecycle paths
- Grep gate: no new `event_dir_for_beat_id(` in `o3_*.py` job paths without `_o3_job_event_dir` wrapper

### Full QA C (mandatory when touching Generate)
1. Load milestone on `:5112`: `POST /api/milestones/load` `{milestone_id:milestone1_arc1}`  
2. Pick beat `bg_arc1_event3b_full_beat_*`  
3. Click Generate — within **2s**: session GET `job_busy: true`, `o3_current_job_id` set  
4. UI: blue spinner “Generating…”  
5. Artifacts: `*_intent.json`, `*_terminal.json` under **library** `Event_1` (not fictional `Event_3b/`)  
6. Poll until terminal `done|failed`  

---

## 6. S3 — H1 Disk vs sidecar drift

### Category
Artifact authority split — MP4 on disk without SQLite/sidecar pointer.

### Category fix
- **Never** auto-reconcile on session GET hot path (Job Truth — already guarded in tests)  
- **Explicit** admin: `POST /api/bg/o3/admin-reconcile` `{force:true}` (exists)  
- Deploy smoke: **warn** on orphan clips under `Event_N/kling_o3_clips/` (`beatgen_sidecar_health.warn_orphan_clips`)  

### Full QA proof
1. Copy orphan MP4 into `Event_3/kling_o3_clips/` (test fixture)  
2. Admin reconcile → session-state shows new option row  
3. Browser slot 0 updates after hard refresh  

---

## 7. S4 — H7 Snapshot / restore per-event

### Category
Restore writes wrong DB shard (`beatgen.db` vs `beatgen_event3.db`).

### Category fix
| Layer | Deliverable |
|-------|-------------|
| Snapshot | `POST /api/state/snapshot` copies `beatgen_eventN.db` (**shipped P9**) |
| Restore | `Production/scripts/restore_beatgen_event_snapshot.sh Event_N [backup_ts\|latest]` |
| Env | Sets `MN_BEATGEN_DB_PATH` + `MN_SIDECAR_ALLOW_FULL_REPLACE=1` **only in script** |
| Gate | Restore → session-state beat count unchanged on `:511{N}` |

### Full QA proof
```bash
bash Production/scripts/restore_beatgen_event_snapshot.sh Event_3 latest
bash Production/scripts/verify_beatgen_deploy_smoke.sh 5113
```

---

## 8. S5 — H2 Dropbox conflict copies

### Category
Human/process authority — two sidecar JSON files on disk.

### Category fix
- Startup: `beatgen_sidecar_health.warn_dropbox_conflict_copies(event_dir)` → `[startup] WARN`  
- CI: `verify_beatgen_siblings_durability.sh` fails if `conflicted copy` under tracked `Production/Event_*`  
- Agent rule: never hand-edit sidecar JSON (**shipped**)  

### Full QA proof
- Startup log line after placing fixture `beat_generator_sidecar (conflicted copy).json`  
- Grep gate exit 0 on clean tree  

---

## 9. S6 — H3 Concurrent writers (SQLite WAL)

### Category
Last-write-wins under parallel HTTP + subprocess.

### Category fix
- Agents: single-writer HTTP only (**shipped L3**)  
- Ops: one launchd plist per `beatgen_eventN.db` (document in §10)  
- Test: two parallel import POSTs → distinct slot indices, no torn `kling_o3_options`  

### Full QA proof
`pytest tests/test_beatgen_concurrent_import.py` (S6 deliverable)

---

## 10. S7 — H5 Milestone ↔ event promotion

### Category
Lifecycle undefined — beat “graduates” from milestone JSON to event SQLite.

### Category fix (product — no auto-promote)
1. Promotion = **Extract beats** on milestone → **Inject beats** on target event with **new beat_ids**  
2. Or operator runbook: export JSON segment → manual import via BG inject API  
3. UI: `bg-authority-badge` shows JSON vs SQLite (**shipped P8**)  

### Full QA proof
Playwright: milestone scope badge shows `JSON sidecar`; event scope shows `SQLite beatgen_eventN.db`.

---

## 11. S8 — H6 Still pipeline tag matrix

### Category
Display filter vs storage source tag.

### Status
**Mostly DONE** (P4/P5): `still_insert_kling_idle` write path; BgTab read path force-shows approved clip.

### S8 remaining
- Grep: stitch export reads `kling_o3_video_path` only after scope validation  
- Regression: `test_beatgen_truth_stack.py::test_import_delivery_clip_to_beat_still_insert_source`  

---

## 12. S9 — H9 Kid app + P10 all ports

### H9 (MindfulNest repo)
Stitch export → kid-app catalog is a **parallel truth layer**. Tooling deliverable: operator runbook paragraph + link to MindfulNest module catalog spec.

### P10 closeout
| Port | Event | Smoke |
|------|-------|-------|
| 5111 | Event_1 | `verify_beatgen_deploy_smoke.sh 5111` |
| 5112 | Event_2 | milestone + intro (**done**) |
| 5113 | Event_3 | intro + Beat 9 (**done**) |
| 5114+ | Event_N | same script per active launchd plist |

**Merge criteria:** all S1–S8 gates green OR explicitly deferred with ticket in PR body; S9 ports for all active events; `build-sha` = git HEAD on each port.

---

## 13. Ops contract — single SQLite writer (H3)

| Rule | Enforcement |
|------|-------------|
| One writer process per `beatgen_eventN.db` | Dedicated port launchd plists |
| Optional override | `MN_BEATGEN_DB_PATH` in plist (must match Event_N) |
| Agents | HTTP only on `:5110+N` — never CLI `update_beat_locked` for shipping beats |
| O3 subprocess | `MN_BEATGEN_ALLOW_DIRECT_WRITE=1` only when spawned from server with `MN_BEATGEN_SCOPE_JSON` |

---

## 14. Durability gates (mandatory — same as Truth Stack Part 3)

### A. Milestone SQLite contract
`init_bg_paths(milestone_dir=…)` must never call `bootstrap_sqlite_sidecar_from_json`.  
**Test:** `test_milestone_init_bg_paths_authority_guard.py`

### B. Deploy smoke
`verify_beatgen_deploy_smoke.sh PORT` — integrity + beat count before/after restart.

### C. Dual-server policy
Document §13; never run two servers with same `MN_BEATGEN_DB_PATH`.

### D. Recovery hardening
Integrity before quarantine; serialize bootstrap; catch `OperationalError`.

### E. O3 job event-dir single resolver
Submit, session GET `job_busy`, poll, terminal, delivery → `_o3_job_event_dir(h, beat_id)`.

### F. Cross-surface parity sweep
After each sibling fix, grep for bare `event_dir_for_beat_id` on job paths; fix cousins same commit or list open.

### G. Dedicated-port restart
If `:511{N}` doesn’t recover in 60s after restart API, relaunch from Dropbox/tooling — do not mark deploy done.

**Sibling aggregate gate:** `verify_beatgen_siblings_durability.sh`

---

## 15. CI / deploy gate chain

```text
verify_storyboard_session_durability.sh
  └─ verify_beatgen_truth_stack_durability.sh   (P6/P7)
  └─ verify_beatgen_siblings_durability.sh      (S1–S5 grep + pytest)
deploy_storyboard_v59.sh
  └─ verify_beatgen_deploy_smoke.sh 5112 + 5113
```

---

## 16. Full QA mandatory checklist (copy per sibling)

**A. Scope / identity** — URL, `/api/event/current`, dedicated 409, hard refresh before heal  

**B. Beat Gen persistence** — session-state beats > 0; `PRAGMA integrity_check`; cite db path  

**C. In-flight Generate** (S2/H4 only) — milestone `event3b`; job_busy <2s; spinner; artifact paths  

**D. Deploy** — mirror Dropbox; `build-sha`; restart HTTP 200  

**E. Regression scan** — primary category + siblings; browser slot 0 when clip-related  

### Deliverable template

```markdown
## Full QA — [Hn / Sn title]

**Root cause:** … (evidence)

**Category fix:** …

**Proof:** repro / unit / smoke / browser / hard-refresh

**Commit:** `<sha>` on `fix/beatgen-truth-stack-v1`

**Sibling categories still open:** …
```

---

## 17. Taxonomy pass (mandatory before closing each sibling)

1. Primary bug category for this sibling  
2. Sibling bugs in same category (other failure sites)  
3. Parallel categories (different truth layers)  
4. Underlying chain (3 levels of “why”)  
5. Which gates (§14) would have caught this earlier  
6. What remains open after this fix (honest list)  

---

## 18. Success definition (siblings program complete)

- [ ] S1: grep finds `log_beatgen_mutation` in all listed write handlers  
- [ ] S2: Full QA C green on milestone `event3b` beat after any O3 change  
- [ ] S3: admin reconcile imports orphan disk clip; deploy warns on orphans  
- [ ] S4: restore script + smoke on Event_3  
- [ ] S5: startup WARN + no conflict copies in CI tree  
- [ ] S6: concurrent import test + ops doc  
- [ ] S7: promotion runbook linked from agent rule  
- [ ] S8: stitch export scope grep green  
- [ ] S9: all active dedicated ports smoke-green; PR merged  

---

## 19. 3×3 debate (surface area — siblings program)

| | **Keep scope minimal** | **Category fix depth** | **Risk if wrong** |
|--|------------------------|------------------------|-------------------|
| **H1 disk drift** | Admin-only reconcile (exists) | Orphan warn in deploy, not auto-import | Session GET slowdown / Job Truth regression |
| **H7 restore** | Script + env pin only | Full replace gated to script | Wrong shard restore wipes beats |
| **H4 O3 scope** | Env JSON shipped | Full QA C on every O3 PR | Milestone jobs in wrong Event folder |

**Decision:** Ship S5+S4+S3 gates first (ops visibility + restore); S2 Full QA C before next O3 feature; S1 handler logging in same PRs as touched handlers.

---

## 20. Code references

| Fact | Location |
|------|----------|
| Mutation logger | `beatgen_scope.log_beatgen_mutation` |
| Disk reconcile | `beat_generator.reconcile_beat_gallery_from_disk` |
| Admin reconcile API | `handle_bg_o3_admin_reconcile` |
| Snapshot + db backup | `server_handlers/core.handle_state_snapshot` |
| Conflict / orphan health | `beatgen_sidecar_health.py` |
| Restore script | `Production/scripts/restore_beatgen_event_snapshot.sh` |
| Sibling CI gate | `verify_beatgen_siblings_durability.sh` |
