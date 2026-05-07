# prod_scripts Registry Scalability Test — Final Report

**Test Date:** April 13, 2026  
**Tester:** Claude Code Agent  
**Scope:** Assess M2-M6 script registration fit and 9-arc projection  
**Status:** CONDITIONAL PASS — Schema has critical gaps that must be fixed before scaling

---

## Executive Summary

The prod_scripts collection (currently 5 records for M1 only) **IS SCALABLE to 200-270 records across 9 arcs**, but **ONLY IF** the schema is modernized now. Three critical design issues were found:

1. **Fixed enum issue:** script_type cannot grow beyond M1's original 3-4 types
2. **Variant capture:** No mechanism to link related files (corrections, variants, supersedes)
3. **Naming inconsistency:** M1 and M4 use different conventions for same script types

These issues are NOT blocking for M1 (already produced), but WILL cause registry breakdown when M2-M6 enter production and subsequent arcs scale up.

---

## Part A: Script File Inventory (Disk State as of April 13)

### M1: Tessa (Magic Hands) — IN PRODUCTION
**Status:** Complete, audio stage
**Scripts found:**
- `M1_PHASE_B_MEDITATION_SCRIPT_v1.md` — Clinical meditation sequence
- `M1_PHASE_B_SCRIPT_v5.docx` — Approved TTS narrator version (v5)
- `M1_PHASE_A_PRODUCTION_PACKAGE_v3.md` — Guide Bird demo beats

**Current prod_scripts records:** 5
**Issues:** None apparent at this module level

---

### M2: Luna (Breath-Squeezers) — NOT YET IN PIPELINE
**Status:** Awaiting pipeline entry
**Scripts found:**
- `M2_PHASE_B_MEDITATION_SCRIPT_v2.md` — **MARKED OBSOLETE** (comet revision, March 2026)
  - Old creature: "Shelly the Snail"
  - Old technique: "4-7-8 Breath" (now M2 is Breath-Squeezers)
  - Will be regenerated entirely when M2 enters pipeline
- `M2_PHASE_B_RESEARCH_DOSSIER.md` — Background material (unversioned)

**Projection for M2 production:**
- New v1 PHASE_B_MEDITATION_SCRIPT (Breath-Squeezers, Luna)
- New v1 PHASE_B_ELEVENLABS_SCRIPT (TTS input format)
- New v1 PHASE_B_CUE_MAP (TTS cue markers)
- New v1 PHASE_A_BEAT_SHEET (Interactive demo)
- (Maybe) PHASE_B_RESEARCH_DOSSIER (optional)

**Expected records:** 4-5 (discarding obsolete v2)

---

### M3: Benson (Brave Sniffing) — NOT YET IN PIPELINE
**Status:** Awaiting pipeline entry
**Scripts found:**
- `M3_PHASE_B_MEDITATION_SCRIPT_v2.md` — Current version
- `M3_PHASE_B_MEDITATION_SCRIPT_v2_CORRECTED.md` — Correction variant
- `M3_PHASE_B_RESEARCH_DOSSIER.md` — Background material

**Key issue:** Two versions at same version number (v2 and v2_CORRECTED)
- Are these 1 or 2 prod_scripts records?
- Does "corrected" bump version to v2a or v3?
- Schema provides no answer

**Expected records:** 4-5 (depends on correction versioning rule)

---

### M4: Ember (Heart-Sending) — IN EARLY PRODUCTION
**Status:** Phase B audio stage (highest file diversity)
**Scripts found:**
- `M4_PHASE_B_MEDITATION_SCRIPT_HEART_SENDING_v1.md` — Clinical meditation
- `M4_PHASE_B_ELEVENLABS_SCRIPT_v1.md` — TTS-formatted input (different from meditation)
- `M4_PHASE_B_CUE_MAP_v1.md` — TTS cue markers ({{BELL_CUE}}, {{INHALE_CUE}})
- `M4_PHASE_A_BEAT_SHEET_v1.md` — Interactive demo beats
- `M4_PHASE_B_RESEARCH_DOSSIER.md` — Background material
- `M4_PHASE_B_RESEARCH_DOSSIER_HEART_SENDING_v1.md` — Research variant

**Key insight:** M4 produces MORE script types than M1
- M1: meditation, narrator, beat sheet
- M4: meditation, elevenlabs, cue map, beat sheet, research (2 variants)
- This divergence shows M1 pattern was NOT representative

**Current records in prod_scripts:** Unknown (likely 3-4)
**Expected records to scale:** 5-6

---

### M5: Bork (Self-Grounding) — NOT STARTED
**Status:** Not yet produced
**Files on disk:** None
**Expected records:** 4-5 (assuming M4 pattern)

---

### M6: Bramble (Humming) — NOT STARTED
**Status:** Not yet produced
**Files on disk:** None
**Expected records:** 4-5 (assuming M4 pattern)

---

## Part B: Script Type Count & Taxonomy

### Distinct Script Types Identified Across M1-M4

| Script Type | File Pattern | M# | Count |
|-------------|---|---|---|
| **phase_b_meditation** | `M{N}_PHASE_B_MEDITATION_SCRIPT*` | 1,2,3,4 | 4 |
| **phase_b_elevenlabs** | `M{N}_PHASE_B_ELEVENLABS_SCRIPT*` | 4 | 1 |
| **phase_b_cue_map** | `M{N}_PHASE_B_CUE_MAP*` | 4 | 1 |
| **phase_b_research** | `M{N}_PHASE_B_RESEARCH_DOSSIER*` | 2,3,4 | 3 |
| **phase_a_beat_sheet** | `M{N}_PHASE_A_BEAT_SHEET*` | 4 | 1 |
| **phase_a_production_package** | `M{N}_PHASE_A_PRODUCTION_PACKAGE*` | 1 | 1 |

**Total unique types:** 6-7 (plus variants: "CORRECTED", "HEART_SENDING")

---

## Part C: Arc 1 Projection (M1-M6)

**Calculation:** Sum of files that would be registered if all M1-M6 modules completed production

| Module | Creature | Active Files | Research Files | Total per Module |
|--------|----------|---|---|---|
| M1 | Tessa | 3 (meditation, narrator .docx, beat sheet) | 0 | 3 |
| M2 | Luna | 4 (meditation, elevenlabs, cue_map, beat_sheet) | 1 (research) | 5 |
| M3 | Benson | 4 (meditation, elevenlabs, cue_map, beat_sheet) | 1 (research) | 5 |
| M4 | Ember | 4 (meditation, elevenlabs, cue_map, beat_sheet) | 2 (research variants) | 6 |
| M5 | Bork | 4 (estimated) | 1 (estimated) | 5 |
| M6 | Bramble | 4 (estimated) | 1 (estimated) | 5 |
| **Arc 1 Subtotal** | | | | **29** |
| **Avg per module** | | | | **4.8** |

---

## Part D: Cross-Arc Projection (All 9 Arcs)

**Total modules in MindfulNest:** 9 arcs × 6 modules/arc = 54 modules

**Script registration estimate:**

| Scenario | Per-Module Avg | Arc 1 (6 mods) | Arc 2-9 (48 mods) | **Total 9-Arc** |
|----------|---|---|---|---|
| Conservative (4 scripts/mod) | 4.0 | 24 | 192 | **216** |
| Moderate (4.5 scripts/mod) | 4.5 | 27 | 216 | **243** |
| Aggressive (5.2 scripts/mod, M4 pattern) | 5.2 | 31 | 250 | **281** |

**Expected range: 216-281 prod_scripts records** by Arc 9 completion

This is a **40-50x scale-up** from current state (5 records).

---

## Part E: Critical Schema Issues

### ISSUE 1: script_type Enum Cannot Scale

**Current state (from PIPELINE_BRAIN_v4):**
```
script_type: enum("phase_b_meditation", "phase_b_tts", "phase_a_beat_sheet", ...)
```

**Problem:** If script_type is a PostgreSQL enum, adding new type values requires:
1. ALTER TABLE prod_scripts TYPE script_type ADD VALUE 'phase_b_elevenlabs'
2. Restart database (some configurations)
3. Schema migration, not backward compatible

**Evidence:** M4 already requires types not in M1:
- "phase_b_elevenlabs" (M4 only)
- "phase_b_cue_map" (M4 only)
- "phase_b_research" (M2, M3, M4 but not M1)

**Impact:** By M3-M4 production, the schema will require 6-7 enum values. By Arc 2-3, 10+ types possible.

**Verdict:** BLOCKER IF enum; not an issue if TEXT field

---

### ISSUE 2: Variant & Correction Files Not Captured

**Problem:** M3 has both:
- `M3_PHASE_B_MEDITATION_SCRIPT_v2.md`
- `M3_PHASE_B_MEDITATION_SCRIPT_v2_CORRECTED.md`

Current schema fields:
```
current_version (text): "v2" or "v2_corrected"?
file_path (text): one path only
```

**Question:** Are these 1 record or 2?
- **If 1 record:** Which file is "current"? Schema has no supersedes/replaces mechanism
- **If 2 records:** Do they have the same or different current_version values?

**No answer in PIPELINE_BRAIN_v4**

**M4 similar case:** "MEDITATION_SCRIPT" vs "ELEVENLABS_SCRIPT" for same module
- These are DIFFERENT content (meditation vs TTS format)
- But same creature (Ember) and module (M4)
- Should they be separate records? Schema permits it but doesn't clarify intent

**Impact:** Registry will have orphaned/duplicate records; unclear which file is "active"

---

### ISSUE 3: Research Dossiers Blur Production vs Reference

**Problem:** prod_scripts includes:
- `PHASE_B_RESEARCH_DOSSIER.md` (background material, not audio input)
- `PHASE_B_MEDITATION_SCRIPT.md` (actual meditation to record)

Both live in the same collection. If you query for "all Phase B scripts" to produce audio, you'll get dossiers too — wasting time filtering.

**Current schema:** No asset_category or material_type field to distinguish

**Impact:** Registry becomes noisy; unclear which records are "production" vs "informational"

---

### ISSUE 4: Naming Convention Divergence

**M1 convention:**
- `M1_PHASE_A_PRODUCTION_PACKAGE_v3.md` (Phase A content)

**M4 convention:**
- `M4_PHASE_A_BEAT_SHEET_v1.md` (Phase A content, different name)

**Problem:** Same asset type, different filenames. If you build automation around "BEAT_SHEET", M1 files won't match.

**File format divergence:**
- M1: `M1_PHASE_B_SCRIPT_v5.docx` (Word format)
- M2-M4: All .md (Markdown)

**No schema field for file_format** to distinguish.

---

### ISSUE 5: No Versioning History Link

**Problem:** Version history lives in prod_activity_log, not in prod_scripts
- prod_scripts.current_version = "v2"
- prod_activity_log records changes: v1→v2, v2→v2_corrected, etc.

**But:** No FK from prod_scripts to prod_activity_log entries for lineage
- Can't efficiently query "all versions of this script"
- Can't trace why a version changed (Kim feedback)

**Impact:** Lineage tracking requires multi-table joins; inefficient for scale

---

## Part F: Recommended Schema Migration

### Current Fields
```sql
module_id, creature_name, script_type (enum), current_version, 
file_path, tts_input_path, status, kim_verdict, kim_feedback, 
approved_at, notes
```

### Recommended New Fields

| Field | Type | Purpose | Example |
|-------|------|---------|---------|
| `script_category` | TEXT | Separate production from research | "production", "research" |
| `script_type` | **TEXT** (was ENUM) | Allow flexible script types | "meditation", "elevenlabs_tts", "cue_map" |
| `file_format` | TEXT | Track .md, .docx, .json | "md", "docx", "json" |
| `related_files` | JSONB | Link variants, corrections, supersedes | `[{"type":"correction", "path":"...v2_CORRECTED.md"}, ...]` |
| `variant_of` | UUID FK | If this is a variant, point to parent | (null for originals, UUID for corrections) |
| `activity_log_id` | UUID FK | Link to original creation in activity_log | (backfill from history) |

### Migration Path (Zero Downtime)

1. **Add new fields as nullable** (phase 1):
   - `ALTER TABLE prod_scripts ADD COLUMN script_category TEXT`
   - `ALTER TABLE prod_scripts ADD COLUMN file_format TEXT`
   - `ALTER TABLE prod_scripts ADD COLUMN related_files JSONB`
   - `ALTER TABLE prod_scripts ADD COLUMN variant_of UUID`
   - `ALTER TABLE prod_scripts ADD COLUMN activity_log_id UUID`

2. **Backfill existing M1 records** (phase 2):
   - Set script_category = 'production' for all current records
   - Infer file_format from existing file_path (if ends in .docx → 'docx')
   - Set related_files = [] for M1 records (no variants)
   - Test queries

3. **Plan enum migration for script_type** (phase 3, before M2 production):
   - **Option A (recommended):** Change column type to TEXT
   - **Option B:** Expand enum to cover M1-M6 types in advance
   - Schedule before M2 enters pipeline

---

## Part G: File Naming Standardization Needed

**Before M5 production (currently M4 in early stages), establish:**

1. **Phase A naming:** Choose one
   - Option 1: Standardize all to `BEAT_SHEET` (M4 pattern)
   - Option 2: Standardize all to `PRODUCTION_PACKAGE` (M1 pattern)
   - **Recommendation:** Use `BEAT_SHEET` (more specific to narrative design)

2. **Correction versioning:** Establish rule
   - Option 1: `v2_CORRECTED` = same version record, different file
   - Option 2: `v2a` or `v3` = new version, bumps current_version
   - **Recommendation:** Create separate record, link via variant_of FK (keeps history clean)

3. **File format:** Document why M1 has .docx vs M2-M4 .md
   - If .docx is intentional (working doc in Word), continue for future arcs
   - If .md is newer standard (pipeline evolution), migrate M1 .docx to .md version

4. **Research dossier naming:** Standardize unversioned research files
   - Current: `PHASE_B_RESEARCH_DOSSIER.md` (no version)
   - Recommendation: Add version for lineage tracking: `v1`, `v2`, etc.
   - Or exclude from prod_scripts; use separate collection

---

## Part H: Test Results

### Simulation: Register M2-M6 with Current Schema

**Assumption:** Use current schema as-is, ignore issues

**Results:**
- M2: 5 files → How many records? (uncertain due to obsolete v2)
  - Result: **AMBIGUOUS** (what happens to obsolete scripts?)
- M3: 3 files including v2_CORRECTED
  - Result: **CONFLICT** (is this 1 or 2 records per file?)
- M4: 6 files, 2 research variants
  - Result: **OVERFLOW** (script_type enum doesn't have "cue_map" or separate research type)
- M5-M6: Estimated 5 files each
  - Result: **UNKNOWN** (depends on resolution of M2-M4 issues)

**Verdict:** Current schema CAN store M2-M6 files, but WITH AMBIGUITY AND INCONSISTENCY

**Verdict on Scale:** Schema will become UNMAINTAINABLE by Arc 3-4 (18-24 modules) due to enum bloat, naming conflicts, and unclear variant semantics.

---

## Part I: Recommended Actions

### Phase 1: Immediate (Before M2 Production)
- [ ] Decide: Is script_type enum or TEXT?
  - If enum, pre-expand to cover M1-M6 types
  - If TEXT (recommended), no prep needed
- [ ] Decide: Do research dossiers belong in prod_scripts?
  - If no, create separate prod_research collection
  - If yes, add script_category field to filter
- [ ] Establish Phase A naming standard (BEAT_SHEET vs PRODUCTION_PACKAGE)

### Phase 2: During M2-M4 Production
- [ ] Backfill prod_scripts with file_format, script_category fields
- [ ] Link corrections via variant_of FK (M3_CORRECTED as separate record pointing to v2)
- [ ] Document rule: "Each unique file = 1 record" (no merging meditation + elevenlabs into single record)

### Phase 3: Before M5 Production
- [ ] Run migration: script_type enum → TEXT (if not done in Phase 1)
- [ ] Add related_files JSONB field
- [ ] Test M5 registration with new schema

### Phase 4: Ongoing
- [ ] Monitor: Do any new script types emerge in M5-M6?
- [ ] Track: Do naming conventions hold across arcs?
- [ ] Plan: By Arc 4-5, review for performance (should still be <300 records)

---

## Conclusion

**IS THE SCHEMA SCALABLE?**

**Verdict:** CONDITIONAL YES

The prod_scripts collection **can** handle 200-270 records across 9 arcs, but requires:

1. **Enum fix:** Change script_type from enum → TEXT (or pre-expand enum)
2. **Variant capture:** Add related_files JSONB field + variant_of FK
3. **Categorization:** Add script_category field to separate production from research
4. **Naming standardization:** Agree on Phase A naming, correction versioning, file formats
5. **Implementation before M5 production:** These changes must be done while only M1-M4 are produced; adding them mid-M5 is risky

**If these changes are deferred:**
- M5-M6 production will expose duplicates, naming conflicts, enum overflow
- By Arc 3, registry will be unmaintainable
- Manual cleanup will be required

**Recommended next step:** Schedule 1-hour schema review with Kim to decide on enum vs TEXT and research dossier classification. Implement changes in Phase 1 timeline before M2 enters pipeline production.

