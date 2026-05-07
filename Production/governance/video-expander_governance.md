# video-expander — Governance Gate

**Skill:** video-expander
**Created:** April 15, 2026
**Severity:** MEDIUM

## Governing Documents (Read Before Proceeding)

1. `CLAUDE.md` Rule 11 — Source Fidelity Protocol (CRITICAL — this skill exists because of Source Fidelity)
2. `ARC_PRODUCTION_BIBLE_v2_10.md` — World state for expansion writing
3. `ArcBuilder_v2_3.md` — §4.5 production lessons, creature physical vocabulary
4. `Production/TASK_GOVERNANCE_PROTOCOL.md` — Category 8 (Arc Skeleton / Narrative Work)

## Startup Validation Checklist

### 1. Mechanical Extraction Check
- [ ] Source .docx will be extracted to markdown via pandoc (NOT read through Claude's generation)
- [ ] Per-event source files will be isolated via bash (NOT retyped)
- [ ] Pandoc conversion artifacts will be cleaned via sed (apostrophes, em-dashes, backslashes)
- [ ] Both raw and cleaned versions of extract will be preserved

### 2. Locked Content Identification
- [ ] ALL Kim-authored content classified as LOCKED: dialogue, stage direction, narrative prose, notes, flags, variable formats, TBD markers, apparent typos
- [ ] When uncertain whether content is Kim's or Claude's: treat as Kim's (false-positive protection)
- [ ] Variable formats preserved as-is (this skill OVERRIDES ArcBuilder Phase 2b variable standardization rule)

### 3. Expansion Zone Rules
- [ ] Claude writes ONLY into expansion zones (before scenes, between dialogue blocks, where camera direction is missing)
- [ ] Claude NEVER retypes Kim's text through its own generation
- [ ] Claude NEVER interleaves generation with locked text in the same write operation
- [ ] Locked text inserted mechanically via bash (`sed -n` / line extraction)

### 4. Approved Corrections Protocol
- [ ] Each correction has Kim's explicit approval documented
- [ ] Corrections manifest created BEFORE starting expansion
- [ ] Corrections applied during WRAP phase, not EXTRACT
- [ ] Each correction gets its own diff verification
- [ ] Correction scope NEVER expanded beyond what Kim approved

### 5. Verification Check
- [ ] Post-expansion diff of all dialogue lines (source vs. expanded)
- [ ] ANY changes to Kim's text beyond permitted changes and approved corrections = STOP and fix
- [ ] Permitted changes exhaustively limited to: pandoc artifacts, Kim-approved spell name replacements, corrections manifest items

## Validation Logic (Pseudocode)

```python
def validate_video_expander_governance():
    errors = []
    
    # Check 1: Extraction method
    if extraction_method != "pandoc_mechanical":
        errors.append("HARD FAIL: Source must be extracted via pandoc, not read through Claude's generation")
    
    # Check 2: Source fidelity
    if any_kim_text_retyped_through_generation:
        errors.append("HARD FAIL: FM-17 Silent Normalization — Kim's text was retyped, not mechanically extracted")
    
    # Check 3: Expansion zones
    if claude_text_overwrites_locked_content:
        errors.append("HARD FAIL: Claude may only write into expansion zones, never over locked content")
    
    # Check 4: Variable formats
    if variable_formats_standardized:
        errors.append("HARD FAIL: Variable format standardization is forbidden in this skill (overrides ArcBuilder)")
    
    # Check 5: Diff verification
    if not post_expansion_diff_run:
        errors.append("HARD FAIL: Must run dialogue diff between source and expanded version")
    
    return errors
```

## What Happens When Validation Fails

**HARD FAIL (blocks execution):**
- Non-mechanical extraction attempted → Refuse. Must use pandoc + bash, not Claude's text generation.
- Kim's text retyped through generation (FM-17) → STOP immediately. Revert to source and redo mechanically.
- Expansion overwrites locked content → STOP. Identify the overwrite, restore from source, restrict to expansion zones.
- Variable formats changed → Refuse. Preserve all variable formats as-is.
- Post-expansion diff not run → Refuse to deliver until diff confirms zero unauthorized changes.

**SOFT FAIL (warn and proceed with caution):**
- Pandoc artifact not caught in cleaning pass → Warn, clean, proceed.
- Expansion zone placement ambiguous → Flag for Kim's review before proceeding.

## Past Failure(s) This Gate Prevents

**Arc 8 skeleton production (undated):** Claude was asked to expand thin video descriptions into full production scenes. Claude wrote detailed expansions and silently rewrote every piece of Kim's dialogue in the process — normalizing spelling, grammar, punctuation, and phrasing without awareness. Hours of Kim's carefully authored dialogue were destroyed. This is FM-17: Silent Normalization, the single most dangerous failure mode when Claude works with locked text. The mechanical extraction + expansion zone approach eliminates FM-17 by ensuring Kim's text is never passed through Claude's text generation.

## Locked Architecture Constraints (added 2026-04-18, task_id: size-budget-arch-cascade-1caa1e0b)

Before producing ANY deliverable, verify:

- [ ] **Single-MP4 atomic (RENDERING_ARCHITECTURE_SINGLE_MP4_ATOMIC_V1):** Output is ONE MP4 file per module/event with all audio + video + animations baked in. No separate audio track. No separate overlay file. No multi-file deliverable.
- [ ] **No runtime TTS (NO_RUNTIME_TTS_PERSONALIZATION_V1):** Rendered audio contains NO personalization variables (`{childName}`, `{therapistName}`, `{parentTitle}`, `{parentName}`, `{chosenGuideName}`, pronouns). All spoken content is universal phrasing. ElevenLabs runs ONCE per module in the production pipeline; never at runtime from the app.
- [ ] **Arc-aware sizing (CATALOG_DELIVERY_ARC_AT_A_TIME_V1):** Per-module target ≤ 60 MB with 100 MB hard ceiling. If exceeded, either compress before registering or file a `SHORTCUT_SIZE_OVERRIDE_*` escape-hatch decision with Kim's approval.
- [ ] **Transparent MP4 loops (if used for characters/breathing circle):** BAKED INTO the atomic module MP4 at production time. Not layered at runtime. Reference: LD-128 2026-04-18 appendix.
- [ ] **Tool-layer enforcement (per Rule 19 addendum):** ffmpeg/cwebp/ElevenLabs command flags in this governance file are the enforcement point — hardcode bitrate and format ceilings here. Phase 0 prose gate is a reminder, not enforcement.

If ANY box cannot be checked, STOP. Either adjust the plan to comply OR file a `SHORTCUT_*` Directus decision with Kim's explicit approval.

Reference: `APP_ARCHITECTURE_MASTER_v1.md`, `SIZE_BUDGET_AUDIT_20260418.md`, preflight id=84.
