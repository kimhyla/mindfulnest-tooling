# dashboard-gate — Governance Gate

**Skill:** dashboard-gate
**Created:** April 15, 2026
**Severity:** MEDIUM

## Governing Documents (Read Before Proceeding)

1. `Production/PIPELINE_BRAIN_v1.md` — Part 1B (dashboard-first workflow)
2. `Production/API_KEYS_MASTER.md` — Directus credentials
3. `CLAUDE.md` Rule 15 — Registry Sync Protocol (structural sync at session start)
4. `Production/TASK_GOVERNANCE_PROTOCOL.md` — Category 5 (API Integration)

## Startup Validation Checklist

### 1. Authentication Check
- [ ] Credentials read from `Production/API_KEYS_MASTER.md` at runtime (never hardcoded)
- [ ] Python `urllib.request` used for Directus API calls (NEVER curl — password contains `$`)
- [ ] JWT token obtained and verified (not null, not expired)

### 2. 7-Query Protocol Completion Check
- [ ] Query 1: `prod_audio_locked_decisions` — loaded
- [ ] Query 2: `prod_modules/{id}` — `current_stage`, `stage_status`, `session_checklist`, `session_resumption_notes` read
- [ ] Query 3: `prod_activity_log` — recent iterations with `voice_settings`, `kim_verdict`, `kim_feedback` reviewed
- [ ] Query 4: `prod_audio_assets` — file inventory loaded
- [ ] Query 5: `prod_blockers` — unresolved blockers checked
- [ ] Query 6: `prod_session_decisions` — past decisions loaded
- [ ] Query 7: `prod_voice_profiles` — Myrrhin settings confirmed (stability 0.70, speed 0.50)
- [ ] Dashboard State Summary presented to Kim

### 3. Registry Sync Check (CLAUDE.md Rule 15)
- [ ] `prod_reference_docs` queried for all active entries
- [ ] Disk scan of project root for .md/.docx files (maxdepth 1)
- [ ] Comparison run: new files, missing files, path mismatches
- [ ] If issues found: asked Kim before proceeding (BLOCKING)

### 4. Real-Time Logging Discipline
- [ ] Two-Write Rule understood: every action = one `prod_activity_log` entry + one asset/status update
- [ ] Token refresh protocol understood (re-auth before API calls after 15 min)

## Validation Logic (Pseudocode)

```python
def validate_dashboard_gate_governance():
    errors = []
    
    # Check 1: Auth method
    if api_method == "curl":
        errors.append("HARD FAIL: Must use Python urllib.request, not curl (password contains $)")
    
    # Check 2: 7-query protocol
    queries_completed = [q1, q2, q3, q4, q5, q6, q7]
    if not all(queries_completed):
        missing = [i+1 for i, q in enumerate(queries_completed) if not q]
        errors.append(f"HARD FAIL: 7-query protocol incomplete. Missing queries: {missing}")
    
    # Check 3: Registry sync
    if not registry_sync_completed:
        errors.append("HARD FAIL: Registry sync check not run (CLAUDE.md Rule 15)")
    
    # Check 4: Dashboard summary
    if not dashboard_summary_presented:
        errors.append("SOFT FAIL: Dashboard state summary should be presented to Kim before production work begins")
    
    return errors
```

## What Happens When Validation Fails

**HARD FAIL (blocks execution):**
- curl used for Directus API → Refuse. Switch to Python `urllib.request`.
- 7-query protocol incomplete → Refuse to start production work until all 7 queries run.
- Registry sync not completed → Refuse until sync check passes (CLAUDE.md Rule 15).

**SOFT FAIL (warn and proceed with caution):**
- Dashboard summary not shown to Kim → Warn, present summary, then proceed.
- Individual query returns empty results (e.g., no blockers) → Log and proceed (empty is valid).

## Past Failure(s) This Gate Prevents

**April 11, 2026:** Claude skipped the session-start protocol and generated 4 voice stems with wrong settings because it didn't read `prod_audio_locked_decisions`. Also re-tried settings Kim had already rejected because it didn't read `prod_activity_log` for previous `kim_verdict` entries. Both failures would have been caught by completing the 7-query protocol before starting work.
