# Skill Correction Master Plan v1
## Generated: April 11, 2026
## Source: Triple-blind agent evaluation of 6 production skills + Priority 4 research
## Protocol: Verified-Edit (Phase 0-4) with multipass agent checks

---

## Authority Chain

| Document | Authority | Purpose |
|----------|-----------|---------|
| VOICE_ROSTER_LOCKED_v2.md | PRIMARY (Kim-approved April 6) | Voice settings, model IDs, character profiles |
| ARC_PRODUCTION_BIBLE_v2_10.md | PRIMARY | Pipeline stages, production rules |
| CANONICAL_DATA_MODEL_v1_12.md | PRIMARY | Firestore schema, field definitions |
| UNIFIED_TECHNIQUE_INVENTORY_v1_15.md | PRIMARY | Technique names, domains, assignments |
| CLAUDE_Guide_Bird_AI_System_Prompt_v1_4.md | PRIMARY | aiNarrativeCache field definitions |
| MODULE_PRODUCTION_MASTER_PLAN_v2_1.md | PRIMARY | 6-stage pipeline, stage definitions |
| PHASE_B_AUDIO_ASSEMBLY_GUIDE_v1_4.md | PRIMARY | Audio assembly specs, breathCycle params |

---

## WAVE 1: Critical (RED) — Production-blocking issues

### SKILL 1: audio-producer (installed skill)
**Location:** `.claude/skills/audio-producer/SKILL.md`
**Writable copy:** `Claude Mindfulnest Project Files/.claude/skills/audio-producer/` — DOES NOT EXIST in project folder (installed April 11, only in session mount)

> **BLOCKER:** audio-producer exists ONLY as a read-only installed skill. We need to create a writable project-folder copy before editing. This requires using the skill-creator to install it to the project folder.

| ID | Old Text | New Text | Scope | Rationale |
|----|----------|----------|-------|-----------|
| A1 | `stability: 0.70, similarity_boost: 0.80, style: 0.20` | `stability: 0.30, similarity_boost: 0.80, style: 0.30` | global (all curl examples) | VOICE_ROSTER_LOCKED_v2 authority. April 6 decision: eleven_v3 Creative mode. |
| A2 | `eleven_multilingual_v2` | `eleven_v3` | global (all model references) | April 6 model switch to eleven_v3 for emotional direction tags. |
| A3 | Myrrhin stability 0.70 | Myrrhin stability 0.30 | targeted (voice table) | VOICE_ROSTER_LOCKED_v2: Myrrhin = 0.30/0.80/0.30 |
| A4 | Guide Bird stability 0.65 | Guide Bird stability 0.30 | targeted (voice table) | VOICE_ROSTER_LOCKED_v2: Guide Bird (Chipper1) = 0.30/0.80/0.30 |

### SKILL 2: elevenlabs-tts
**Location:** `Claude Mindfulnest Project Files/.claude/skills/elevenlabs-tts/SKILL.md` (WRITABLE)

| ID | Old Text | New Text | Scope | Rationale |
|----|----------|----------|-------|-----------|
| E1 | Add: Character quota tracking section | New section: "## ElevenLabs Creator Plan Quota" with monthly character limit tracking, warning thresholds, and per-module character estimates | targeted (new section) | ALL THREE agents flagged. Creator plan has limits; no tracking = production halt risk. |
| E2 | Add: Batch generation error handling | New section: "## Error Handling & Retry Logic" with rate-limit backoff (429 → exponential), malformed response retry (max 3), timeout handling | targeted (new section) | Beta + Gamma flagged. Current skill has no error handling for batch TTS generation. |
| E3 | Add: File output → voice stem concatenation step | New section or paragraph describing: individual line files → ffmpeg concat → single voice stem per module | targeted (new section) | Gamma flagged. Gap between elevenlabs-tts output (individual lines) and audio-producer input (single voice stem). |
| E4 | Add: Personalization variable sentence-level splitting | New section describing: identify sentences containing {childName}/{guideName} → split into per-child render queue vs. universal render | targeted (new section) | Beta + Gamma flagged. TTS_PERSONALIZATION_PIPELINE_v1 describes this but elevenlabs-tts skill doesn't. |

### SKILL 3: scene-to-production
**Location:** `Claude Mindfulnest Project Files/.claude/skills/scene-to-production/SKILL.md` (WRITABLE)

| ID | Old Text | New Text | Scope | Rationale |
|----|----------|----------|-------|-----------|
| S1 | All "Midjourney Prompt" references | "FLUX Kontext Prompt" | global (outside changelogs) | April 10 visual pipeline pivot. FLUX Kontext Max via BFL API replaced Midjourney. |
| S2 | Any "painterly" style references (~line 116) | "Pixar 3D" | global (outside changelogs) | April 10 visual style lock: Pixar 3D supersedes painterly. Memory file `project_visual_style_pixar3d.md` confirms. |
| S3 | `ARC_PRODUCTION_BIBLE_v2_9` | `ARC_PRODUCTION_BIBLE_v2_10` | global | Alpha + Gamma: stale version reference. |
| S4 | Add: Multi-character scene decomposition section | New section: "## Multi-Character Scene Decomposition" with guidance for party scenes (4+ characters in rapid dialogue), shot-by-shot breakdown rules, speaker isolation for lip-sync | targeted (new section) | Gamma RED: no guidance for complex party scenes like Event 3. |
| S5 | Add: Pipeline position clarification | New paragraph in intro: "This skill runs as the FIRST step of video-producer (Step 1: Shot Breakdown). It is NOT a standalone pipeline step." | targeted | Beta YELLOW: overlap with video-producer Step 1 undefined. |

### SKILL 4: dashboard-ops
**Location:** `.claude/skills/dashboard-ops/SKILL.md` (installed, read-only)
**Writable copy:** Project folder does NOT have dashboard-ops.

> **BLOCKER:** Same as audio-producer — needs a writable project-folder copy.

| ID | Old Text | New Text | Scope | Rationale |
|----|----------|----------|-------|-----------|
| D1 | Add: Hard gate enforcement curl pattern | New section: "## Hard Gate Verification" with GET query to `prod_approvals` checking for approval record before allowing PATCH to advance past `phase_b` or `listen_through` stages | targeted (new section) | Beta + Gamma RED: skill documents the requirement but provides no executable curl for the check. |
| D2 | Add: `audio_status` and `visual_status` fields | Add to field reference table and include in relevant curl examples | targeted | Alpha + Gamma YELLOW: fields added April 11 but not in skill. |
| D3 | Add: "Create new module" POST operation | New section with POST curl template for creating a brand-new module record | targeted (new section) | Gamma YELLOW: skill only covers PATCH updates. |
| D4 | Add: Cross-skill integration guide | New section: "## Cross-Skill Handoffs" showing how audio-producer and video-producer update status through dashboard-ops | targeted (new section) | Gamma YELLOW: no documentation on inter-skill status handoffs. |

### SKILL 5: phase-a-designer
**Location:** `Claude Mindfulnest Project Files/.claude/skills/phase-a-designer/SKILL.md` (WRITABLE)

| ID | Old Text | New Text | Scope | Rationale |
|----|----------|----------|-------|-----------|
| P1 | "DO NOT produce: phaseAFlow JSON" | Remove this prohibition OR add: "JSON assembly is a SEPARATE sub-step after beat sheet approval. See MODULE_PRODUCTION_MASTER_PLAN Stage 4b." | targeted | Beta RED: Master Plan says Stage 4 = "Phase A + JSON Build" but skill says don't produce JSON. |
| P2 | Add: JSON handoff specification | New section: "## JSON Build Handoff" describing: beat sheet → Kim approval → JSON assembly (separate step or skill) → schema validation | targeted (new section) | Clarifies the pipeline gap between design and build. |
| P3 | "4-6 cues" guidance | "3-6 cues (match approved module complexity)" | targeted | Gamma YELLOW: M4 approved at 3 beats; rigid "4-6" could encourage overbuilding. |

### SKILL 6: video-producer
**Location:** `Claude Mindfulnest Project Files/.claude/skills/video-producer/SKILL.md` (WRITABLE)

| ID | Old Text | New Text | Scope | Rationale |
|----|----------|----------|-------|-----------|
| V1 | Any reference to Seedance 2.0 | Seedance 1.5 Pro | global (verify first) | Beta: may reference wrong Seedance version. NEEDS VERIFICATION against actual skill text. |
| V2 | Any reference to FLUX Kontext on Replicate | FLUX Kontext Max via BFL API (api.bfl.ai, $0.08/img) | global (verify first) | Beta: may reference wrong API endpoint. NEEDS VERIFICATION. |
| V3 | Step 7 inline Phase B audio section | Replace with: "## Step 7: Phase B Audio — invoke audio-producer skill. See audio-producer/SKILL.md for full pipeline." + brief summary | targeted | Gamma RED: inline version is incomplete (no Vosk, no mixing tool spec). Pointer to dedicated skill is correct approach. |
| V4 | Sub-Skill References table (missing audio-producer) | Add row: "audio-producer | Phase B audio pipeline | .claude/skills/audio-producer/SKILL.md" | targeted | Gamma: audio-producer not listed in references despite being critical dependency. |

---

## WAVE 2: Important (YELLOW) — Non-blocking but should be fixed

### phase-b-writer
| ID | Old Text | New Text | Scope | Rationale |
|----|----------|----------|-------|-----------|
| PB1 | Add: Audio Production Type output field | Add to output section: "audioProductionType: [breathing|observation|compassion|tension_arc|containment|body_awareness]" | targeted | Gamma YELLOW: implicit in Arc 1, needs formalization for Arc 2+. |
| PB2 | Add: Myrrhin voice ID reference | Add note: "Myrrhin Voice ID: oR4uRy4fHDUGGISL0Rev (ElevenLabs, eleven_v3)" | targeted | Alpha YELLOW: production convenience. |

### elevenlabs-tts (additional)
| ID | Old Text | New Text | Scope | Rationale |
|----|----------|----------|-------|-----------|
| E5 | Any `eleven_multilingual_v2` reference | `eleven_v3` | global (verify) | Beta YELLOW: model ID alignment with VOICE_ROSTER_LOCKED_v2. |

### video-producer (additional)
| ID | Old Text | New Text | Scope | Rationale |
|----|----------|----------|-------|-----------|
| V5 | If memory file `project_video_pipeline_pivot.md` still says "painterly" | Update to "Pixar 3D" | targeted | Alpha YELLOW: stale memory file (not skill itself). |

### dashboard-ops (additional)
| ID | Old Text | New Text | Scope | Rationale |
|----|----------|----------|-------|-----------|
| D5 | Validate `prod_approvals` field names against live Directus schema | Confirm or correct field names | targeted | Beta YELLOW: field names unvalidated. |

---

## WAVE 3: Priority 4 Reframe

Priority 4 is NOT "codify the system prompt" (v1.4 already exists). It is three separate deliverables:

### Deliverable A: Module Context Registry
- Create a structured lookup: all 54 modules mapped to context variables (arcName, arcPremise, moduleDomain, moduleCreature, eventType, barPosition, moduleIsEvolution, bridgeDialogue conditions)
- Source: arc skeletons + CDM + technique inventory
- Output: JSON or markdown registry file

### Deliverable B: Creature Vocabulary Appendix
- Extract creature-specific physical vocabulary from ArcBuilder + arc skeletons
- Curate into reference table
- Append to Guide Bird System Prompt v1.5 (or separate reference doc)

### Deliverable C: Stage 4 Operator Runbook
- Production skill or script: reads module context → calls Haiku API with v1.4 → validates JSON → caches to Firestore → updates Directus
- Includes: API settings (model: claude-3-5-haiku, temperature, max_tokens, retry logic)
- Includes: automated validation (sentence count, forbidden term regex, JSON schema)
- Includes: test matrix (minimum 3-5 modules covering full Call, transitional Call, evolution, bridge null)

---

## EXECUTION PROTOCOL

### Phase 0: Master Correction List (THIS DOCUMENT)
- Already complete. This IS the correction list.

### Phase 1: Editing (Parallel Agents, Isolated by Skill)
- **Agent 1:** scene-to-production (corrections S1-S5)
- **Agent 2:** elevenlabs-tts (corrections E1-E5)
- **Agent 3:** phase-a-designer (corrections P1-P3)
- **Agent 4:** video-producer (corrections V1-V5) — V1/V2 require verification first
- **Agent 5:** phase-b-writer (corrections PB1-PB2)
- **Agent 6:** audio-producer — BLOCKED until writable copy created
- **Agent 7:** dashboard-ops — BLOCKED until writable copy created

Each agent follows the 7-step per-edit protocol:
1. PRE-READ (locate exact line)
2. PRE-GREP (uniqueness check)
3. BACKUP (first edit per file)
4. SURGICAL EDIT
5. POST-GREP (landing check)
6. NEGATIVE GREP (removal check)
7. LOG (correction ID, old→new, counts, status)

### Phase 2: Self-Verification
- Each editing agent runs retired term sweep + edit count check + formatting check
- Report: "Edits applied: N of N expected. Retired term sweep: CLEAN/issues. Formatting: CLEAN/issues."

### Phase 3: Independent Validation (Fresh Agents)
- Launch 3 NEW agents (not the editing agents) to read ALL edited files cold
- Validator receives: finished files + VOICE_ROSTER_LOCKED_v2 + ARC_PRODUCTION_BIBLE_v2_10 + retired terms list
- Validator does NOT receive the correction list — they check the FILES, not the list
- Tasks: cross-reference validation, term sweep, consistency check

### Phase 4: Diff Report & Kim Review
- Generate single markdown file showing every line changed across all skills
- Kim reviews before any skill is considered corrected
- After Kim approval: updated skills get installed (replacing read-only copies)

---

## BLOCKERS TO RESOLVE BEFORE EXECUTION

1. **audio-producer writable copy:** Need to create project-folder version of audio-producer skill so it can be edited and synced via Dropbox. Currently only exists as read-only installed skill.

2. **dashboard-ops writable copy:** Same issue — needs project-folder copy.

3. **V1/V2 verification:** Need to read video-producer skill text to confirm whether it actually references "Seedance 2.0" and "Replicate" (Beta flagged but didn't quote exact text).

4. **D5 schema validation:** Need to query live Directus API to verify `prod_approvals` field names match what dashboard-ops skill specifies.

5. **Memory file update (V5):** Update `.auto-memory/project_video_pipeline_pivot.md` to say "Pixar 3D" instead of "painterly."

---

## ESTIMATED EFFORT

- Wave 1 (RED fixes): ~2-3 hours with full verified-edit protocol
- Wave 2 (YELLOW fixes): ~1 hour
- Wave 3 (Priority 4 reframe): Separate initiative, ~4-6 hours for all 3 deliverables
- Phase 3 validation: ~30 minutes (3 parallel validator agents)
- Phase 4 diff report: ~15 minutes

**Total: ~4-5 hours for Waves 1-2 with full safety protocol.**
