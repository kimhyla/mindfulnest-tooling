# Phase 2 Spec: Governance File Expansion for 7 Remaining Skills

**Created:** April 15, 2026
**Purpose:** Exact specifications for expanding 7 stub governance files into full validation-checklist governance gates, matching the template established by `video-producer_governance.md` and `audio-producer_governance.md`.
**Estimated time:** ~2 hours total (15-20 min per file)
**Prerequisite:** Phase 1 complete (CLAUDE.md Rules 15-17, TASK_GOVERNANCE_PROTOCOL.md, 2 full + 7 stub governance files)

---

## Template Structure (Every Governance File Must Have)

Each expanded file follows this exact structure (modeled on the Phase 1 files):

```
# [Skill Name] — Governance Gate

**Skill:** [skill-name]
**Created:** April 15, 2026
**Severity:** [HIGH / MEDIUM / LOW]

## Governing Documents (Read Before Proceeding)
[Numbered list of specific docs + CLAUDE.md rules]

## Startup Validation Checklist
[Numbered sub-sections with checkbox items]

## Validation Logic (Pseudocode)
[Python-style pseudocode for automated checks]

## What Happens When Validation Fails
[HARD FAIL vs SOFT FAIL definitions]

## Past Failure(s) This Gate Prevents
[Specific dated incident, or "No direct past failure — preventive gate"]
```

---

## Priority Order

| # | Skill | Severity | Rationale | Est. Time |
|---|-------|----------|-----------|-----------|
| 1 | storyboard-producer | HIGH | Two-Path Protocol violations caused 5 failures April 13 | 20 min |
| 2 | dashboard-gate | MEDIUM | Already has 7 enforcement rules, but needs governing doc cross-refs | 15 min |
| 3 | dashboard-ops | MEDIUM | API method rules (Python not curl), schema constraints | 15 min |
| 4 | arcbuilder | MEDIUM | Source Fidelity, M-number convention, Three Questions Gate | 20 min |
| 5 | video-expander | MEDIUM | Source Fidelity is the entire point; mechanical extraction rules | 15 min |
| 6 | cross-document-update | LOW | Authority hierarchy, backward-pass requirement | 15 min |
| 7 | verified-edit | LOW | Surgical edit protocol, version-up rule | 15 min |

---

## File 1: storyboard-producer_governance.md

**Location:** `Production/governance/storyboard-producer_governance.md`
**Severity:** HIGH

### Governing Documents

1. `CLAUDE.md` Rule 7 — Two-Path Protocol (CRITICAL)
2. `CLAUDE.md` Rule 7 — Export-first rebuild protocol (April 13, 2026)
3. `CLAUDE.md` Rule 7 — Pre-rebuild browser-edit gate
4. `Production/PIPELINE_BRAIN_v1.md` — Storyboard section
5. `Production/TASK_GOVERNANCE_PROTOCOL.md` — Category 3

### Startup Validation Checklist

**1. Build Method Check**
- [ ] Structural/image changes → Path A (Python builder `build_storyboard.py`)
- [ ] JS/behavior-only fixes → Path B (JS-only patch script)
- [ ] FORBIDDEN: Direct HTML editing, base64 injection, hand-writing HTML replacements
- [ ] If both image + JS changes needed: Path A first, then Path B

**2. Pre-Rebuild Gate**
- [ ] Asked Kim: "Have you made edits in the browser (dialogue, drag-drop, image assignments) that haven't been exported?"
- [ ] If Kim has unsaved edits: she must click "Export Locked Sequence" FIRST
- [ ] Export-first protocol: Kim's exported sequence JSON is MANDATORY primary source for `--lines` input
- [ ] NEVER extract lines from previous storyboard's embedded JavaScript (doesn't reflect drag-drop edits)

**3. Image Source Check**
- [ ] Never guess at disk file paths when rebuilding
- [ ] Extract embedded images FROM current HTML if rebuilding (or use Kim's explicit file paths)
- [ ] Exception: Kim explicitly provides a new/replacement image path

**4. Audit Check**
- [ ] `--audit` run on current version BEFORE rebuild
- [ ] `--audit-previous` run AFTER rebuild to compare features
- [ ] RED flags checked: drag-drop lost, play-all lost, export lost, image count dropped, line count dropped
- [ ] If ANY red flag and not intentional → DO NOT deliver

**5. Registry Mode Check**
- [ ] Default: `--registry` mode (queries Directus `prod_visual_assets`)
- [ ] If auth failure (401/403): escalate to Kim (token refresh)
- [ ] If server error (5xx) after 2 retries: switch to `--config` mode, warn Kim
- [ ] If BOTH fail: STOP and ask Kim — never manually reconstruct

**6. Version Check**
- [ ] Version-in-filename incremented (never overwrite)
- [ ] All prior versions preserved until Kim approves new one

### Validation Logic (Pseudocode)

```python
def validate_storyboard_governance():
    errors = []
    
    # Check 1: Build method
    if change_type == "structural" and method != "path_a_builder":
        errors.append("HARD FAIL: Structural changes require Path A (Python builder)")
    if change_type == "js_only" and method != "path_b_js_patch":
        errors.append("HARD FAIL: JS-only changes require Path B (JS patch script)")
    if method == "direct_html_edit":
        errors.append("HARD FAIL: Direct HTML editing is FORBIDDEN")
    
    # Check 2: Pre-rebuild gate
    if not kim_confirmed_no_browser_edits:
        errors.append("HARD FAIL: Must ask Kim about unsaved browser edits before rebuild")
    
    # Check 3: Audit
    if previous_version_exists and not audit_run_before:
        errors.append("HARD FAIL: Must run --audit on current version before rebuild")
    
    return errors
```

### Past Failures This Gate Prevents

**April 13, 2026 — 5 related failures:**
1. Drag-drop lost in v8→v9 rebuild (no feature audit)
2. Wrong image embedded (base64 hand-injected instead of builder)
3. Registry functions existed but main() wasn't wired to them
4. Full rebuild scrambled Kim's image selections (disk file paths guessed wrong)
5. The enforcement rule itself ("always use the builder") caused scrambling — a JS-only patch would have been safe

---

## File 2: dashboard-gate_governance.md

**Location:** `Production/governance/dashboard-gate_governance.md`
**Severity:** MEDIUM

### Governing Documents

1. `Production/PIPELINE_BRAIN_v1.md` — Part 1B (dashboard-first workflow)
2. `Production/API_KEYS_MASTER.md` — Directus credentials
3. `CLAUDE.md` Rule 15 — Registry Sync Protocol (new — Step 2.5)
4. `Production/TASK_GOVERNANCE_PROTOCOL.md` — Category 5 (API Integration)

### Startup Validation Checklist

**1. Authentication Check**
- [ ] Credentials read from `Production/API_KEYS_MASTER.md` at runtime (never hardcoded)
- [ ] Python `urllib.request` used for Directus API calls (NEVER curl — password contains `$`)
- [ ] JWT token obtained and verified (not null, not expired)

**2. 7-Query Protocol Completion Check**
- [ ] Query 1: `prod_audio_locked_decisions` — loaded
- [ ] Query 2: `prod_modules/{id}` — `current_stage`, `stage_status`, `session_checklist`, `session_resumption_notes` read
- [ ] Query 3: `prod_activity_log` — recent iterations with `voice_settings`, `kim_verdict`, `kim_feedback` reviewed
- [ ] Query 4: `prod_audio_assets` — file inventory loaded
- [ ] Query 5: `prod_blockers` — unresolved blockers checked
- [ ] Query 6: `prod_session_decisions` — past decisions loaded
- [ ] Query 7: `prod_voice_profiles` — Myrrhin settings confirmed
- [ ] Dashboard State Summary presented to Kim

**3. Registry Sync Check (CLAUDE.md Rule 15)**
- [ ] `prod_reference_docs` queried for all active entries
- [ ] Disk scan of project root for .md/.docx files (maxdepth 1)
- [ ] Comparison run: new files, missing files, path mismatches
- [ ] If issues found: asked Kim before proceeding (BLOCKING)

**4. Real-Time Logging Discipline**
- [ ] Two-Write Rule understood: every action = one `prod_activity_log` entry + one asset/status update
- [ ] Token refresh protocol understood (re-auth before API calls after 15 min)

### Validation Logic (Pseudocode)

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
    
    return errors
```

### Past Failure This Gate Prevents

**April 11, 2026:** Claude skipped the session-start protocol and generated 4 voice stems with wrong settings because it didn't read `prod_audio_locked_decisions`. Also re-tried settings Kim had already rejected because it didn't read `prod_activity_log`.

---

## File 3: dashboard-ops_governance.md

**Location:** `Production/governance/dashboard-ops_governance.md`
**Severity:** MEDIUM

### Governing Documents

1. `Production/PIPELINE_BRAIN_v1.md` — Collection schemas
2. `Production/API_KEYS_MASTER.md` — All credentials
3. `CLAUDE.md` Rule 15 — Registry Sync Protocol
4. `Production/TASK_GOVERNANCE_PROTOCOL.md` — Category 5 (API Integration)

### Startup Validation Checklist

**1. API Method Check**
- [ ] Python `urllib.request` for ALL Directus API calls (NEVER curl)
- [ ] Reason: Directus password contains `$` which curl silently truncates
- [ ] curl is acceptable ONLY for non-Directus APIs where password has no special chars (e.g., ElevenLabs)
- [ ] Credentials read from `Production/API_KEYS_MASTER.md` at runtime

**2. Schema Compliance Check**
- [ ] `module_id` is INTEGER (not string) — use `1`, not `"M1"`
- [ ] `stage_status` uses PostgreSQL enum: only `not_started`, `in_progress`, `blocked`, `completed`
- [ ] `prod_activity_log` uses fields `action` and `details` (NOT `description` or `status`)
- [ ] Required fields known per collection (write will fail silently if missing)

**3. Stage Transition Protocol**
- [ ] To advance a module: set `stage_status = 'completed'` → update `current_stage` to next → reset `stage_status = 'not_started'` → log transition
- [ ] Hard gates at `phase_b` and `listen_through` — cannot advance without Kim's explicit approval
- [ ] Two-Write Rule: every action = one `prod_activity_log` write + one asset/status write

**4. Token Management**
- [ ] JWT tokens expire in 15 minutes
- [ ] Re-authenticate before API calls in long sessions
- [ ] If 401 returned: re-authenticate, don't retry with same token

### Validation Logic (Pseudocode)

```python
def validate_dashboard_ops_governance():
    errors = []
    
    # Check 1: API method
    if api_method == "curl" and target == "directus":
        errors.append("HARD FAIL: Use Python urllib.request for Directus (password contains $)")
    
    # Check 2: Schema
    if isinstance(module_id, str):
        errors.append("HARD FAIL: module_id must be INTEGER, not string")
    if stage_status not in ["not_started", "in_progress", "blocked", "completed"]:
        errors.append(f"HARD FAIL: Invalid stage_status '{stage_status}' — PostgreSQL enum will reject")
    
    # Check 3: Hard gate
    if advancing_past in ["phase_b", "listen_through"] and not kim_approved:
        errors.append("HARD FAIL: Cannot advance past hard gate without Kim's explicit approval")
    
    return errors
```

### Past Failure This Gate Prevents

**Multiple sessions:** curl-based Directus API calls silently failed because the password contains `$`, which bash interprets as a variable. Switching to Python `urllib.request` eliminated the problem. Also, invalid enum values for `stage_status` caused silent write failures.

---

## File 4: arcbuilder_governance.md

**Location:** `Production/governance/arcbuilder_governance.md`
**Severity:** MEDIUM

### Governing Documents

1. `ARC_PRODUCTION_BIBLE_v2_10.md` — World state, locked decisions, format rules
2. `ArcBuilder_v2_3.md` — Production methodology, Braid Checklist, Quality Gate, Module Format Template
3. `UNIFIED_TECHNIQUE_INVENTORY_v1_14.md` — Canonical spell names, technique definitions
4. `CLAUDE.md` Rule 11 — Source Fidelity Protocol
5. `CLAUDE.md` Rule 12 — M-Number Convention
6. `Production/TASK_GOVERNANCE_PROTOCOL.md` — Category 8 (Arc Skeleton / Narrative Work)

### Startup Validation Checklist

**1. Source Fidelity Check**
- [ ] Kim-authored dialogue will be preserved VERBATIM — never retyped through Claude's text generation
- [ ] Screen direction from skeleton treated as binding production instruction
- [ ] If revising existing skeleton: read it COMPLETELY before making any changes

**2. M-Number Convention Check**
- [ ] M-numbers FIXED to creatures: M1=Tessa, M2=Luna, M3=Benson, M4=Ember, M5=Bork, M6=Bramble
- [ ] Play order differs from M-number order (Arc 1: M1→M2→M4→M6→M3→M5)
- [ ] M-numbers NEVER change — verify no M-number reassignments in the work

**3. Three Questions Gate (Before Phase A/B Work)**
- [ ] Q1 answered: What to show conceptually? (therapeutic mechanism in Everdale terms)
- [ ] Q2 answered: How does the creature show it? (creature-specific physical vocabulary)
- [ ] Q3 answered: What technique solves it? (actual clinical technique)
- [ ] If ANY question unanswered: STOP and ask Kim

**4. Spell Name Verification**
- [ ] Every spell name cross-checked against `UNIFIED_TECHNIQUE_INVENTORY_v1_14.md` §8 (Canonical Spell Name Registry)
- [ ] Use spell names in conversation, never clinical labels (feedback_spell_names_only.md)

**5. Document Load Sequence**
- [ ] For new arc from brief: Batch 1 (governance + method) → Batch 2 (world state + format) → Batch 3 (clinical + format reference)
- [ ] For revision pass: skeleton loaded COMPLETELY before any changes, then only load docs relevant to revision
- [ ] Never hold more than 3 project documents in active context simultaneously

**6. Kim-Confirmation Gate**
- [ ] Before writing or overwriting ANY working document: ask Kim with FULL FILENAME
- [ ] Kim must confirm using the full filename too
- [ ] Version-up, never overwrite (create new filename)
- [ ] Single-format workflow: working docs are .docx ONLY

### Validation Logic (Pseudocode)

```python
def validate_arcbuilder_governance():
    errors = []
    
    # Check 1: Three Questions
    if task_involves_phase_a_or_b:
        if not all([q1_answered, q2_answered, q3_answered]):
            errors.append("HARD FAIL: Three Questions Gate not cleared before Phase A/B work")
    
    # Check 2: M-number convention
    M_NUMBERS = {"M1": "Tessa", "M2": "Luna", "M3": "Benson", 
                 "M4": "Ember", "M5": "Bork", "M6": "Bramble"}
    for m_num, creature in work_assignments.items():
        if M_NUMBERS.get(m_num) != creature:
            errors.append(f"HARD FAIL: {m_num} is {M_NUMBERS[m_num]}, not {creature}")
    
    # Check 3: Source fidelity
    if modifying_existing_skeleton and not skeleton_read_completely:
        errors.append("HARD FAIL: Must read entire skeleton before making revisions")
    
    # Check 4: Spell names
    for spell in spell_names_used:
        if spell not in canonical_registry:
            errors.append(f"SOFT FAIL: Spell name '{spell}' not in Canonical Spell Name Registry")
    
    return errors
```

### Past Failure This Gate Prevents

**No single dated incident — preventive gate.** This gate prevents the class of failures where Claude produces skeleton content that contradicts locked narrative decisions (wrong M-number assignments, wrong spell names, rewritten dialogue). The Three Questions Gate specifically prevents the "therapy-speak" failure mode where Phase A/B content is written without understanding the therapeutic mechanism.

---

## File 5: video-expander_governance.md

**Location:** `Production/governance/video-expander_governance.md`
**Severity:** MEDIUM

### Governing Documents

1. `CLAUDE.md` Rule 11 — Source Fidelity Protocol (CRITICAL — this skill exists because of Source Fidelity)
2. `ARC_PRODUCTION_BIBLE_v2_10.md` — World state for expansion writing
3. `ArcBuilder_v2_3.md` — §4.5 production lessons, creature physical vocabulary
4. `Production/TASK_GOVERNANCE_PROTOCOL.md` — Category 8 (Arc Skeleton / Narrative Work)

### Startup Validation Checklist

**1. Mechanical Extraction Check**
- [ ] Source .docx will be extracted to markdown via pandoc (NOT read through Claude's generation)
- [ ] Per-event source files will be isolated via bash (NOT retyped)
- [ ] Pandoc conversion artifacts will be cleaned via sed (apostrophes, em-dashes, backslashes)
- [ ] Both raw and cleaned versions of extract will be preserved

**2. Locked Content Identification**
- [ ] ALL Kim-authored content classified as LOCKED: dialogue, stage direction, narrative prose, notes, flags, variable formats, TBD markers, apparent typos
- [ ] When uncertain whether content is Kim's or Claude's: treat as Kim's (false-positive protection)
- [ ] Variable formats preserved as-is (this skill OVERRIDES ArcBuilder Phase 2b variable standardization rule)

**3. Expansion Zone Rules**
- [ ] Claude writes ONLY into expansion zones (before scenes, between dialogue blocks, where camera direction is missing)
- [ ] Claude NEVER retypes Kim's text through its own generation
- [ ] Claude NEVER interleaves generation with locked text in the same write operation
- [ ] Locked text inserted mechanically via bash (`sed -n` / line extraction)

**4. Approved Corrections Protocol**
- [ ] Each correction has Kim's explicit approval documented
- [ ] Corrections manifest created BEFORE starting expansion
- [ ] Corrections applied during WRAP phase, not EXTRACT
- [ ] Each correction gets its own diff verification
- [ ] Correction scope NEVER expanded beyond what Kim approved

**5. Verification Check**
- [ ] Post-expansion diff of all dialogue lines (source vs. expanded)
- [ ] ANY changes to Kim's text beyond permitted changes and approved corrections = STOP and fix
- [ ] Permitted changes exhaustively limited to: pandoc artifacts, Kim-approved spell name replacements, corrections manifest items

### Validation Logic (Pseudocode)

```python
def validate_video_expander_governance():
    errors = []
    
    # Check 1: Extraction method
    if extraction_method != "pandoc_mechanical":
        errors.append("HARD FAIL: Source must be extracted via pandoc, not read through Claude's generation")
    
    # Check 2: Source fidelity
    if any_kim_text_retyped_through_generation:
        errors.append("HARD FAIL: FM-17 Silent Normalization — Kim's text was retyped, not mechanically extracted")
    
    # Check 3: Variable formats
    if variable_formats_standardized:
        errors.append("HARD FAIL: Variable format standardization is forbidden in this skill (overrides ArcBuilder)")
    
    # Check 4: Diff verification
    if not post_expansion_diff_run:
        errors.append("HARD FAIL: Must run dialogue diff between source and expanded version")
    
    return errors
```

### Past Failure This Gate Prevents

**Arc 8 skeleton production (undated):** Claude was asked to expand thin video descriptions into full production scenes. Claude wrote detailed expansions and silently rewrote every piece of Kim's dialogue in the process — normalizing spelling, grammar, punctuation, and phrasing without awareness. Hours of Kim's carefully authored dialogue were destroyed. This is FM-17: Silent Normalization, the single most dangerous failure mode when Claude works with locked text.

---

## File 6: cross-document-update_governance.md

**Location:** `Production/governance/cross-document-update_governance.md`
**Severity:** LOW

### Governing Documents

1. `CLAUDE.md` Rules 2-3 — Version-up, read-before-write, Kim-confirmation gate
2. `CLAUDE.md` Rule 9 — Find-and-replace rules
3. `CLAUDE.md` Rule 13 — Read existing docs before generating analysis
4. `Production/TASK_GOVERNANCE_PROTOCOL.md` — Category 9 (Document Editing)

### Startup Validation Checklist

**1. Authority Hierarchy Check**
- [ ] Authority order understood: Bible > Session Decisions > Arc Production Bible > ArcBuilder > Arc skeletons > All other docs
- [ ] When documents conflict: higher-authority doc wins, lower doc gets fixed

**2. Two-Direction Change Detection**
- [ ] Forward pass: read all session decisions documents, extract every numbered decision
- [ ] Backward pass (CRITICAL): diff downstream documents (Production Bible, ArcBuilder, recent skeleton) against Bible
- [ ] Backward pass catches 30-40% of changes that forward-only misses (character renames, module redesigns applied during sessions but never queued)
- [ ] Master Change List built from BOTH directions before any edits

**3. Gap Checks (Phase 0D)**
- [ ] Name check: every character in recent skeleton exists in Bible
- [ ] Technique check: every module's technique in skeleton matches Bible's skill portfolio
- [ ] Party check: Bible's post-arc party composition matches skeleton's departure DATA tag
- [ ] Item check: backpack item list matches
- [ ] Count check: module count, star count, flight journal entries, hint count all match

**4. Edit Protocol**
- [ ] Bible updated FIRST (keystone), then cascading downstream
- [ ] Surgical updates only — NEVER rewrite Bible from scratch (200K+ document)
- [ ] Grep verification after EACH change (positive + negative)
- [ ] Version-up for every edited file
- [ ] Kim-confirmation gate before any write

**5. Context Window Management**
- [ ] ONE document loaded at a time for editing
- [ ] If context fills: STOP, deliver completed work, list remaining for next session
- [ ] Master Change List used as checkpoint (cross off items as applied)

### Validation Logic (Pseudocode)

```python
def validate_cross_document_governance():
    errors = []
    
    # Check 1: Two-direction detection
    if not backward_pass_completed:
        errors.append("HARD FAIL: Backward pass not run — will miss 30-40% of changes")
    
    # Check 2: Gap checks
    if not all_gap_checks_run:
        errors.append("SOFT FAIL: Gap checks (names, techniques, party, items, counts) not completed")
    
    # Check 3: Bible first
    if first_document_edited != "Bible":
        errors.append("SOFT FAIL: Bible must be updated FIRST, then cascade downstream")
    
    return errors
```

### Past Failure This Gate Prevents

**March 11, 2026:** Forward-only change detection missed character renames and module redesigns that were applied to downstream documents during a session but never formally queued as Bible Update items. The backward pass (Step 0B) was designed to catch exactly this class of failure.

---

## File 7: verified-edit_governance.md

**Location:** `Production/governance/verified-edit_governance.md`
**Severity:** LOW

### Governing Documents

1. `CLAUDE.md` Rule 2 — Version-up, never overwrite
2. `CLAUDE.md` Rule 3 — Read-before-write, Kim-confirmation gate
3. `CLAUDE.md` Rule 9 — Find-and-replace rules (detailed change report, preserve formatting, flag ambiguous replacements)
4. `Production/TASK_GOVERNANCE_PROTOCOL.md` — Category 9 (Document Editing)

### Startup Validation Checklist

**1. Correction List Check**
- [ ] Master Correction List EXISTS as a written document (not in memory)
- [ ] Each correction has: ID, target file, old text, new text, scope (targeted/global)
- [ ] No edits will be made that aren't in the correction list

**2. Edit Method Check**
- [ ] Surgical Edit tool only (exact old_string → new_string)
- [ ] NEVER use Write tool on existing files
- [ ] NEVER rewrite sections from scratch
- [ ] Backup created before first edit to each file

**3. Per-Edit Verification Protocol**
- [ ] 7-step protocol will be followed for EVERY edit:
  1. Pre-read (locate exact line)
  2. Pre-grep (uniqueness check)
  3. Backup (first edit per file)
  4. Edit (surgical)
  5. Post-grep (landing check)
  6. Negative grep (removal check)
  7. Log (ID, old→new, counts, status)

**4. Global Replace Safety**
- [ ] Pre-count: total instances vs. changelog instances
- [ ] Classify EVERY instance: REPLACE vs. PRESERVE (changelogs stay)
- [ ] Surgical per-instance replacement (not replace_all) unless zero PRESERVE instances
- [ ] Post-count: remaining old term count must equal PRESERVE count

**5. Independent Validation**
- [ ] Fresh agent (not the editing agent) reads finished files cold
- [ ] Validator has NO access to correction list (checks correctness, not list compliance)
- [ ] Cross-reference validation, term sweep, consistency check all completed
- [ ] Diff report generated for Kim's review

### Validation Logic (Pseudocode)

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
    
    # Check 3: Verification
    if not independent_validator_used:
        errors.append("SOFT FAIL: Independent validator should read files cold (no access to correction list)")
    
    return errors
```

### Past Failure This Gate Prevents

**No single dated incident — preventive gate.** This gate prevents the class of failures where batch edits introduce silent errors: stale terms surviving in changelogs, table formatting broken by misaligned replacements, version confusion when editing the wrong version. The independent validation step (fresh agent, no correction list access) is the highest-value safety mechanism.

---

## Execution Protocol for Phase 2

### Step 1: Read each stub file from disk
Confirm it still contains the Phase 2 stub content (not modified since Phase 1).

### Step 2: Write expanded content
For each file, in priority order (1-7 above), replace the stub with the full governance content specified in this document.

### Step 3: Per-file verification
After writing each file, read it back and verify:
- [ ] All sections present (Governing Documents, Startup Validation Checklist, Validation Logic, Failure handling, Past Failures)
- [ ] Governing doc references match TASK_GOVERNANCE_PROTOCOL.md categories
- [ ] CLAUDE.md rule numbers are correct (Rules 2, 3, 7, 8, 9, 11, 12, 15)
- [ ] No contradictions with the skill's own SKILL.md

### Step 4: Cross-file consistency check (agent)
Launch a verification agent to read ALL 9 governance files (2 from Phase 1 + 7 from Phase 2) and check:
- [ ] Consistent template structure across all files
- [ ] No duplicate governing doc references that contradict each other
- [ ] All CLAUDE.md rule numbers valid and current
- [ ] All 10 TASK_GOVERNANCE_PROTOCOL categories covered by at least one governance file

### Step 5: Counter-agent adversarial review
Launch a counter-agent to find gaps, contradictions, and practical issues in the full set of 9 governance files.

### Step 6: Fix any issues found
Apply fixes from Steps 4-5.

### Step 7: Update TASK_GOVERNANCE_PROTOCOL.md
Change the Phase 2 status line from "Phase 2 (next session): Expand 7 stub governance files" to "Phase 2 COMPLETE: All 9 governance files fully expanded [date]."

### Step 8: Update memory file
Update `.auto-memory/protocol_execution_tracking.md` to reflect Phase 2 completion.

---

## What Phase 2 Does NOT Include

- **Phase 3 (Directus `prod_locked_decisions` collection):** Creating a queryable Directus collection of ~50 extracted locked decisions. This is a separate ~2 hour task.
- **Skill SKILL.md modifications:** The skill files in `.claude/skills/` are read-only in Cowork. The governance files work as external references via CLAUDE.md Rules 16-17. If skill files need updating (e.g., to add "read your governance file at startup" instructions), that requires the skill-creator packaging workflow.
- **Dashboard-gate SKILL.md Step 2.5:** The registry sync check logic is documented in CLAUDE.md Rule 15 and the dashboard-gate governance file. The actual SKILL.md in the read-only skills folder cannot be edited without skill-creator packaging.

---

## Success Criteria

1. All 9 `Production/governance/` files contain full content (no stubs remaining)
2. Every file follows the template structure (5 sections)
3. All governing doc references verified against actual file existence
4. All CLAUDE.md rule numbers verified as correct
5. Verification agent and counter-agent both pass
6. TASK_GOVERNANCE_PROTOCOL.md updated to show Phase 2 complete
