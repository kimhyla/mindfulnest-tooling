# cross-document-update — Governance Gate

**Skill:** cross-document-update
**Created:** April 15, 2026
**Severity:** LOW (operational risk is higher — cascading errors across 50+ files are possible — but the independent validation step in Check 5 and the Bible-first edit order mitigate this to LOW)

## Governing Documents (Read Before Proceeding)

1. `CLAUDE.md` Rules 2-3 — Version-up, read-before-write, Kim-confirmation gate
2. `CLAUDE.md` Rule 9 — Find-and-replace rules
3. `CLAUDE.md` Rule 13 — Read existing docs before generating analysis
4. `Production/TASK_GOVERNANCE_PROTOCOL.md` — Category 9 (Document Editing)

## Startup Validation Checklist

### 1. Authority Hierarchy Check
- [ ] Authority order understood: Bible > Session Decisions > Arc Production Bible > ArcBuilder > Arc skeletons > All other docs
- [ ] When documents conflict: higher-authority doc wins, lower doc gets fixed

### 2. Two-Direction Change Detection
- [ ] Forward pass: read all session decisions documents, extract every numbered decision
- [ ] Backward pass (CRITICAL): diff downstream documents (Production Bible, ArcBuilder, recent skeleton) against Bible
- [ ] Backward pass catches 30-40% of changes that forward-only misses (character renames, module redesigns applied during sessions but never queued)
- [ ] Master Change List built from BOTH directions before any edits

### 3. Gap Checks (Phase 0D)
- [ ] Name check: every character in recent skeleton exists in Bible
- [ ] Technique check: every module's technique in skeleton matches Bible's skill portfolio
- [ ] Party check: Bible's post-arc party composition matches skeleton's departure DATA tag
- [ ] Item check: backpack item list matches
- [ ] Count check: module count, star count, flight journal entries, hint count all match

### 4. Edit Protocol
- [ ] Bible updated FIRST (keystone), then cascading downstream
- [ ] Surgical updates only — NEVER rewrite Bible from scratch (200K+ document)
- [ ] Grep verification after EACH change (positive + negative)
- [ ] Version-up for every edited file
- [ ] Kim-confirmation gate before any write

### 5. Context Window Management
- [ ] ONE document loaded at a time for editing
- [ ] If context fills: STOP, deliver completed work, list remaining for next session
- [ ] Master Change List used as checkpoint (cross off items as applied)

## Validation Logic (Pseudocode)

```python
def validate_cross_document_governance():
    errors = []
    
    # Check 1: Two-direction detection
    if not backward_pass_completed:
        errors.append("HARD FAIL: Backward pass not run — will miss 30-40% of changes")
    
    # Check 2: Master Change List
    if not master_change_list_exists:
        errors.append("HARD FAIL: Must build Master Change List from both directions before any edits")
    
    # Check 3: Gap checks
    if not all_gap_checks_run:
        errors.append("SOFT FAIL: Gap checks (names, techniques, party, items, counts) not completed")
    
    # Check 4: Bible first
    if first_document_edited != "Bible":
        errors.append("SOFT FAIL: Bible must be updated FIRST, then cascade downstream")
    
    # Check 5: Kim-confirmation gate
    if not kim_confirmed_before_write:
        errors.append("HARD FAIL: Kim-confirmation gate required before any file write (CLAUDE.md Rule 3)")
    
    return errors
```

## What Happens When Validation Fails

**HARD FAIL (blocks execution):**
- Backward pass not run → Refuse to start editing. Run the backward pass first.
- No Master Change List → Refuse. Build the list from both forward and backward passes.
- Kim-confirmation gate skipped → Refuse to write. Ask Kim with full filename.

**SOFT FAIL (warn and proceed with caution):**
- Gap checks incomplete → Warn Kim, proceed with available checks, flag remaining for follow-up.
- Bible not edited first → Warn, reorder if possible, proceed if Bible edits are not applicable.

## Past Failure(s) This Gate Prevents

**March 11, 2026:** Forward-only change detection missed character renames and module redesigns that were applied to downstream documents during a session but never formally queued as Bible Update items. The backward pass (Step 0B) was designed to catch exactly this class of failure — changes that propagated informally without going through the authority hierarchy.
