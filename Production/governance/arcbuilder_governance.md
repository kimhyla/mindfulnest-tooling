# arcbuilder — Governance Gate

**Skill:** arcbuilder
**Created:** April 15, 2026
**Severity:** MEDIUM

## Governing Documents (Read Before Proceeding)

1. `ARC_PRODUCTION_BIBLE_v2_10.md` — World state, locked decisions, format rules
2. `ArcBuilder_v2_3.md` — Production methodology, Braid Checklist, Quality Gate, Module Format Template
3. `UNIFIED_TECHNIQUE_INVENTORY_v1_14.md` — Canonical spell names, technique definitions
4. `CLAUDE.md` Rule 11 — Source Fidelity Protocol
5. `CLAUDE.md` Rule 12 — M-Number Convention
6. `Production/TASK_GOVERNANCE_PROTOCOL.md` — Category 8 (Arc Skeleton / Narrative Work)

## Startup Validation Checklist

### 1. Source Fidelity Check
- [ ] Kim-authored dialogue will be preserved VERBATIM — never retyped through Claude's text generation
- [ ] Screen direction from skeleton treated as binding production instruction
- [ ] If revising existing skeleton: read it COMPLETELY before making any changes

### 2. M-Number Convention Check
- [ ] M-numbers FIXED to creatures: M1=Tessa, M2=Luna, M3=**Benson** (RESTORED 2026-04-21 per LD-353 V1_CREATURE_SET_6_BENSON_AT_M3, supersedes LD-335), M4=Ember, M5=Bork, M6=Bramble
- [ ] V1 play order: **M1 → M2 → M3[Benson] → M4 → M6 → M5** (Benson at M3 teaching Physiological Sigh under Courage domain; Oliver is Arc 1 narrative-only)
- [ ] Post-V1 play order (unchanged): M1→M2→M4→M6→M3→M5
- [ ] M-numbers NEVER change — verify no M-number reassignments in the work
- [ ] **[V1 CASCADE TAG 2026-04-21 — V1_SCOPE_CONDENSED_20260420 (revised 2×)]** Arc 8 Hopegrove skeleton work is IN V1 (Arc 8 reinstated 2026-04-20 evening; Benson reinstated 2026-04-21). Intake Arc 8 per original design; confirm V1 arc numbering against `GAMEPLAY_SCOPE_v2`.

### 3. Three Questions Gate (Before Phase A/B Work)
- [ ] Q1 answered: What to show conceptually? (therapeutic mechanism in Everdale terms)
- [ ] Q2 answered: How does the creature show it? (creature-specific physical vocabulary)
- [ ] Q3 answered: What technique solves it? (actual clinical technique)
- [ ] If ANY question unanswered: STOP and ask Kim

### 4. Spell Name Verification
- [ ] Every spell name cross-checked against `UNIFIED_TECHNIQUE_INVENTORY_v1_14.md` §8 (Canonical Spell Name Registry)
- [ ] Use spell names in conversation, never clinical labels

### 5. Document Load Sequence
- [ ] For new arc from brief: Batch 1 (governance + method) → Batch 2 (world state + format) → Batch 3 (clinical + format reference)
- [ ] For revision pass: skeleton loaded COMPLETELY before any changes, then only load docs relevant to revision
- [ ] Never hold more than 3 project documents in active context simultaneously

### 6. Kim-Confirmation Gate
- [ ] Before writing or overwriting ANY working document: ask Kim with FULL FILENAME
- [ ] Kim must confirm using the full filename too
- [ ] Version-up, never overwrite (create new filename)
- [ ] Single-format workflow: working docs are .docx ONLY
- [ ] Note: Arc skeletons are WORKING DOCUMENTS (Kim actively edits them), so the Kim-confirmation gate ALWAYS applies. They are NOT pipeline-generated outputs, even when produced during a pipeline run.

## Validation Logic (Pseudocode)

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
    
    # Check 5: File format
    if output_format != "docx":
        errors.append("HARD FAIL: Working documents must be .docx ONLY (CLAUDE.md Rule 3)")
    
    return errors
```

## What Happens When Validation Fails

**HARD FAIL (blocks execution):**
- Three Questions unanswered → Refuse to write Phase A/B content. Ask Kim to answer the three questions first.
- M-number mismatch → Refuse. M-numbers are fixed to creatures and never change.
- Skeleton not read completely before revision → Refuse. Read the entire skeleton first.
- Working document not .docx → Refuse. Convert to .docx format.

**SOFT FAIL (warn and proceed with caution):**
- Spell name not found in Canonical Registry → Warn Kim. May be a new spell not yet registered, or a typo.
- Document load order suboptimal → Warn, reorder loads if possible, proceed.

## Past Failure(s) This Gate Prevents

**No single dated incident — preventive gate.** This gate prevents the class of failures where Claude produces skeleton content that contradicts locked narrative decisions (wrong M-number assignments, wrong spell names, rewritten dialogue). The Three Questions Gate specifically prevents the "therapy-speak" failure mode where Phase A/B content is written without understanding the therapeutic mechanism in Everdale terms. The Source Fidelity check prevents FM-17 (Silent Normalization) where Claude rewrites Kim's dialogue while generating new content.

## Locked Architecture Constraints (added 2026-04-18, task_id: size-budget-arch-cascade-1caa1e0b)

Before producing ANY deliverable, verify:

- [ ] **Single-MP4 atomic (RENDERING_ARCHITECTURE_SINGLE_MP4_ATOMIC_V1):** Output is ONE MP4 file per module/event with all audio + video + animations baked in. No separate audio track. No separate overlay file. No multi-file deliverable.
- [ ] **No runtime TTS (NO_RUNTIME_TTS_PERSONALIZATION_V1):** Rendered audio contains NO personalization variables (`{childName}`, `{therapistName}`, `{parentTitle}`, `{parentName}`, `{chosenGuideName}`, pronouns). All spoken content is universal phrasing. ElevenLabs runs ONCE per module in the production pipeline; never at runtime from the app.
- [ ] **Arc-aware sizing (CATALOG_DELIVERY_ARC_AT_A_TIME_V1):** Per-module target ≤ 60 MB with 100 MB hard ceiling. If exceeded, either compress before registering or file a `SHORTCUT_SIZE_OVERRIDE_*` escape-hatch decision with Kim's approval.
- [ ] **Transparent MP4 loops (if used for characters/breathing circle):** BAKED INTO the atomic module MP4 at production time. Not layered at runtime. Reference: LD-128 2026-04-18 appendix.
- [ ] **Tool-layer enforcement (per Rule 19 addendum):** ffmpeg/cwebp/ElevenLabs command flags in this governance file are the enforcement point — hardcode bitrate and format ceilings here. Phase 0 prose gate is a reminder, not enforcement.

If ANY box cannot be checked, STOP. Either adjust the plan to comply OR file a `SHORTCUT_*` Directus decision with Kim's explicit approval.

Reference: `APP_ARCHITECTURE_MASTER_v1.md`, `SIZE_BUDGET_AUDIT_20260418.md`, preflight id=84.
