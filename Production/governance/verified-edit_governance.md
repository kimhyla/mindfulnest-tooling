# verified-edit — Governance Gate

**Skill:** verified-edit
**Created:** April 15, 2026
**Severity:** LOW

## Governing Documents (Read Before Proceeding)

1. `CLAUDE.md` Rule 2 — Version-up, never overwrite
2. `CLAUDE.md` Rule 3 — Read-before-write, Kim-confirmation gate
3. `CLAUDE.md` Rule 9 — Find-and-replace rules (detailed change report, preserve formatting, flag ambiguous replacements)
4. `Production/TASK_GOVERNANCE_PROTOCOL.md` — Category 9 (Document Editing)

## Startup Validation Checklist

### 1. Correction List Check
- [ ] Master Correction List EXISTS as a written document (not in memory)
- [ ] Each correction has: ID, target file, old text, new text, scope (targeted/global)
- [ ] No edits will be made that aren't in the correction list

### 2. Edit Method Check
- [ ] Surgical Edit tool only (exact old_string → new_string)
- [ ] NEVER use Write tool on existing files
- [ ] NEVER rewrite sections from scratch
- [ ] Backup created before first edit to each file

### 3. Per-Edit Verification Protocol
- [ ] 7-step protocol will be followed for EVERY edit:
  1. Pre-read (locate exact line)
  2. Pre-grep (uniqueness check)
  3. Backup (first edit per file)
  4. Edit (surgical)
  5. Post-grep (landing check)
  6. Negative grep (removal check)
  7. Log (ID, old→new, counts, status)

### 4. Global Replace Safety
- [ ] Pre-count: total instances vs. changelog instances
- [ ] Classify EVERY instance: REPLACE vs. PRESERVE (changelogs stay)
- [ ] Surgical per-instance replacement (not replace_all) unless zero PRESERVE instances
- [ ] Post-count: remaining old term count must equal PRESERVE count

### 5. Independent Validation
- [ ] Fresh agent (not the editing agent) reads finished files cold
- [ ] Validator has NO access to correction list (checks correctness, not list compliance)
- [ ] Cross-reference validation, term sweep, consistency check all completed
- [ ] Diff report generated for Kim's review

## Validation Logic (Pseudocode)

```python
def validate_verified_edit_governance():
    errors = []
    
    # Check 1: Correction list
    if not correction_list_exists_on_disk:
        errors.append("HARD FAIL: Master Correction List must exist as written document before any edits")
    
    # Check 2: Edit method
    if edit_method == "write_tool":
        errors.append("HARD FAIL: Write tool forbidden on existing files — use Edit tool only")
    if edit_method == "rewrite_from_scratch":
        errors.append("HARD FAIL: Surgical edits only — never rewrite sections from scratch")
    
    # Check 3: Backup
    if not backup_created_before_first_edit:
        errors.append("HARD FAIL: Must create backup before first edit to each file")
    
    # Check 4: Verification
    if not independent_validator_used:
        errors.append("SOFT FAIL: Independent validator should read files cold (no access to correction list)")
    
    # Check 5: Global replace safety
    if global_replace and not all_instances_classified:
        errors.append("HARD FAIL: Every instance must be classified REPLACE vs. PRESERVE before global replace")
    
    return errors
```

## What Happens When Validation Fails

**HARD FAIL (blocks execution):**
- No correction list on disk → Refuse. Write the correction list first.
- Write tool used on existing file → Refuse. Switch to Edit tool with exact old_string → new_string.
- Section rewritten from scratch → Refuse. Surgical edits only.
- No backup before first edit → Refuse. Create backup first.
- Global replace without instance classification → Refuse. Classify all instances first.

**SOFT FAIL (warn and proceed with caution):**
- Independent validator not available → Warn Kim, offer to self-validate with explicit note that independent validation is preferred.
- Minor formatting differences post-edit → Log, verify intentional, proceed.

## Past Failure(s) This Gate Prevents

**No single dated incident — preventive gate.** This gate prevents the class of failures where batch edits introduce silent errors: stale terms surviving in changelogs (because replace_all hit changelog entries too), table formatting broken by misaligned replacements, version confusion when editing the wrong version of a file. The independent validation step (fresh agent reading files cold, no access to correction list) is the highest-value safety mechanism — it catches errors the editing agent is blind to because it "knows" what the text should say.
