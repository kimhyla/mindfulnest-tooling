# dashboard-ops — Governance Gate

**Skill:** dashboard-ops
**Created:** April 15, 2026
**Severity:** MEDIUM

## Governing Documents (Read Before Proceeding)

1. `Production/PIPELINE_BRAIN_v1.md` — Collection schemas
2. `Production/API_KEYS_MASTER.md` — All credentials
3. `CLAUDE.md` Rule 15 — Registry Sync Protocol
4. `Production/TASK_GOVERNANCE_PROTOCOL.md` — Category 5 (API Integration)

## Startup Validation Checklist

### 1. API Method Check
- [ ] Python `urllib.request` for ALL Directus API calls (NEVER curl)
- [ ] Reason: Directus password contains `$` which curl silently truncates
- [ ] curl is acceptable ONLY for non-Directus APIs where password has no special chars (e.g., ElevenLabs)
- [ ] Credentials read from `Production/API_KEYS_MASTER.md` at runtime

### 2. Schema Compliance Check
- [ ] `module_id` is INTEGER (not string) — use `1`, not `"M1"`
- [ ] `stage_status` uses PostgreSQL enum: only `not_started`, `in_progress`, `blocked`, `completed`
- [ ] `prod_activity_log` uses fields `action` and `details` (NOT `description` or `status`)
- [ ] Required fields known per collection (write will fail silently if missing)

### 3. Stage Transition Protocol
- [ ] To advance a module: set `stage_status = 'completed'` → update `current_stage` to next → reset `stage_status = 'not_started'` → log transition
- [ ] Hard gates at `phase_b` and `listen_through` — cannot advance without Kim's explicit approval
- [ ] Two-Write Rule: every action = one `prod_activity_log` write + one asset/status write

### 4. Token Management
- [ ] JWT tokens expire in 15 minutes
- [ ] Re-authenticate before API calls in long sessions
- [ ] If 401 returned: re-authenticate, don't retry with same token

## Validation Logic (Pseudocode)

```python
def validate_dashboard_ops_governance():
    errors = []
    
    # Check 1: API method
    if api_method == "curl" and target == "directus":
        errors.append("HARD FAIL: Use Python urllib.request for Directus (password contains $)")
    
    # Check 2: Schema types
    if isinstance(module_id, str):
        errors.append("HARD FAIL: module_id must be INTEGER, not string")
    if stage_status not in ["not_started", "in_progress", "blocked", "completed"]:
        errors.append(f"HARD FAIL: Invalid stage_status '{stage_status}' — PostgreSQL enum will reject")
    
    # Check 3: Field names
    if "description" in activity_log_fields or "status" in activity_log_fields:
        errors.append("HARD FAIL: prod_activity_log uses 'action' and 'details', NOT 'description' or 'status'")
    
    # Check 4: Hard gate
    if advancing_past in ["phase_b", "listen_through"] and not kim_approved:
        errors.append("HARD FAIL: Cannot advance past hard gate without Kim's explicit approval")
    
    return errors
```

## What Happens When Validation Fails

**HARD FAIL (blocks execution):**
- curl used for Directus → Refuse. Switch to Python `urllib.request`.
- Wrong field types (string module_id, invalid enum) → Refuse. Fix the payload before sending.
- Wrong field names on activity_log → Refuse. Use `action`/`details`, not `description`/`status`.
- Hard gate bypass attempted → Refuse. Kim must explicitly approve advancement past `phase_b` and `listen_through`.

**SOFT FAIL (warn and proceed with caution):**
- JWT token age unknown → Re-authenticate proactively before next API call.
- Optional fields missing from write payload → Warn, proceed (write will succeed but data will be incomplete).

## Past Failure(s) This Gate Prevents

**Multiple sessions:** curl-based Directus API calls silently failed because the password contains `$`, which bash interprets as a variable. Switching to Python `urllib.request` eliminated the problem. Also, invalid enum values for `stage_status` caused silent write failures, and using wrong field names (`description` instead of `action`) on `prod_activity_log` caused 400 errors that were hard to debug.

### prod_assets Schema Gotchas (LD: `PROD_ASSETS_SCHEMA_GOTCHAS_V1`) — April 25, 2026
Hard-won field rules that caused HTTP 400/500 errors when unknown:
- `prod_assets.status` enum accepts ONLY `"pending"` (NOT `"approved"`). Record Kim's approval verdict in the `notes` field instead.
- `prod_assets.module_id` is REQUIRED (NOT NULL) and MUST be an integer (e.g., `1`). Never pass a string (`"m1"` returns HTTP 500).
- `prod_activity_log.module_id` is an integer column — pass integer or omit (NULL). Never pass `"m1"`.
- `prod_visual_assets` returns HTTP 403 on complex filtered queries. Default to `prod_assets` for registered deliverables.
