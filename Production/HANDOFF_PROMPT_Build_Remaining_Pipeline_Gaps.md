# Handoff Prompt — Build Remaining Pipeline Gaps

**Date:** April 11, 2026
**For:** Next Claude thread continuing MindfulNest production automation work

---

## CONTEXT

In the prior session (April 11, 2026), we completed a comprehensive audit and correction of all 7 MindfulNest production skills:

1. **Triple-blind evaluation:** 21 independent agents (3 per skill) evaluated each skill against canonical authority documents. Findings were cross-compared to separate real issues from false positives.

2. **36 verified corrections** applied across all 7 skills using the verified-edit protocol (4 phases: master correction list → parallel editing agents → self-verification → 3 independent validator agents reading files cold).

3. **End-to-end readiness audit** with 3 agents tracing the full 6-stage pipeline. Verdict: ~60% automated. Individual skills work correctly but the connective tissue between them is incomplete.

4. **Comprehensive reference document created:** `Production/AUTOMATED_PRODUCTION_SKILLS_v1.md` — contains verified inventory of all 7 skills AND detailed specs for all 5 remaining gaps.

5. **New skill created:** `document-handling-rules` — governs every file write with 8 rules (re-read before edit, grep verification, pre/post checks, multi-agent architecture, no shortcuts for small edits). This skill MUST be loaded before touching any file.

## YOUR FIRST TASK: Read These Files

Before doing ANY work, read these files in order:

1. **`Production/AUTOMATED_PRODUCTION_SKILLS_v1.md`** — THE master reference. Part 1 tells you what each skill does and its current state. Part 2 tells you exactly what needs to be built, with detailed specs.

2. **`.claude/skills/document-handling-rules/SKILL.md`** — The file safety protocol. Load this BEFORE touching any file.

3. **`.claude/skills/verified-edit/SKILL.md`** — The mechanical editing protocol. 7-step per-edit sequence.

4. **`.claude/skills/dashboard-ops/SKILL.md`** — The dashboard API skill. You'll need its curl patterns.

5. **`Production/VOICE_ROSTER_LOCKED_v2.md`** — Voice settings authority. Do not change.

6. **`CLAUDE.md`** — Project-wide rules. Kim-confirmation gate, read-before-write, version-up, Source Fidelity Protocol.

## YOUR SECOND TASK: Build the Gaps in Priority Order

The gaps are fully specified in Part 2 of `AUTOMATED_PRODUCTION_SKILLS_v1.md`. Build them in this order:

### Gap 1 (PRIORITY 1, ~2-3 hrs): Dashboard Handoff Additions

Add "Post-Completion: Dashboard Update" sections to 3 skills:
- **phase-b-writer** — dashboard updates after draft complete + after Kim approval
- **phase-a-designer** — dashboard updates after beat sheet complete + after JSON build
- **video-producer** — visual_status updates at Steps 4, 5, 6, and 8

Each section needs EXECUTABLE curl patterns matching dashboard-ops's API format. Follow audio-producer as the model — it's the only skill that currently does this correctly.

**Use the verified-edit protocol for all modifications.** Backup each file before editing. Grep-verify before and after each edit. Launch independent validation agents afterward.

### Gap 2 (PRIORITY 2, ~1 hr): Gate-Manager Pattern

Add a "Gate Advancement Procedure" section to dashboard-ops with a reusable bash pattern for hard gate advancement. The full sequence: verify Kim approval → POST to prod_approvals → GET verification → PATCH to advance → LOG.

### Gap 3 (PRIORITY 3, ~4-5 hrs): Module JSON Builder Skill

Create a new skill: `module-json-builder`. Takes approved Phase A beat sheet + Phase B script → assembles module JSON per CDM v1.12 → runs Q1-Q19 guardrail checks → outputs validated .json. Use the skill-creator skill for this.

### Gap 4 (PRIORITY 4, ~2-3 hrs): Intake Briefer Skill

Create a new skill: `intake-briefer`. Reads arc skeleton + technique inventory → produces Intake Briefs → creates dashboard records. Supports batch mode (all modules in one arc). Use the skill-creator skill.

### Gap 5 (SEPARATE INITIATIVE, ~4-6 hrs): Priority 4 Reframe

Three deliverables: Module Context Registry (JSON mapping 54 modules to context variables), Creature Vocabulary Appendix (physical vocabulary per creature), Stage 4 Operator Runbook (Haiku generation automation).

## CRITICAL RULES

- **document-handling-rules skill governs every file write.** No exceptions. Read it first.
- **Version-up, never overwrite.** Create new version files when editing.
- **Read-before-write on all files.** Re-read from disk before every edit.
- **Source Fidelity Protocol.** Kim's dialogue preserved VERBATIM.
- **Kim-confirmation gate** before writing any working document (.docx). Full filename required.
- **Multi-agent safety:** Use research agents to find changes, editing agents to apply, validation agents to verify. Never let the editing agent be the only checker.
- **Report everything.** After each gap, produce: files touched, lines changed, verification status, validation result.

## VOICE SETTINGS REFERENCE (LOCKED — DO NOT CHANGE)

All characters: stability 0.30, similarity_boost 0.80, style 0.30 on eleven_v3.
Exceptions: Oliver stability 0.35; Bork stability 0.20, style 0.40.
Authority: VOICE_ROSTER_LOCKED_v2.md (April 6, 2026).
Myrrhin: oR4uRy4fHDUGGISL0Rev
Guide Bird (Chipper1): 7o9pyvsN0ob5GO6LBQp6

## KEY REFERENCE FILES

| File | Location | What It's For |
|------|----------|--------------|
| AUTOMATED_PRODUCTION_SKILLS_v1.md | Production/ | Master reference — read FIRST |
| SKILL_CORRECTION_MASTER_PLAN_v1.md | Production/ | Audit trail of all corrections |
| SKILL_CORRECTION_DIFF_REPORT_April11.md | Production/ | Line-by-line diffs |
| MODULE_PRODUCTION_MASTER_PLAN_v2_1.md | Production/ | 6-stage pipeline, batch strategy |
| VOICE_ROSTER_LOCKED_v2.md | Production/ | Voice settings authority |
| API_KEYS_MASTER.md | Production/ | All API credentials (read at runtime) |
| CANONICAL_DATA_MODEL_v1_12.md | Canon/ | Firestore schema (for JSON builder) |
| CLAUDE_Guide_Bird_AI_System_Prompt_v1_4.md | Canon/ | Haiku prompt (for Priority 4 reframe) |
| UNIFIED_TECHNIQUE_INVENTORY_v1_14.md | Canon/ | Technique names/domains (for intake briefer) |
| ARC_PRODUCTION_BIBLE_v2_10.md | Canon/ | Module format rules |

## WHAT SUCCESS LOOKS LIKE

After all 5 gaps are built:
- Every skill updates the Directus dashboard at its completion points
- Hard gates are enforced with verified approval records before any advancement
- Stage 4b (JSON build) is automated with validation
- Stage 1 (intake) supports batch processing of entire arcs
- The Haiku narrative generation pipeline has its context registry and operator runbook
- Pipeline automation goes from ~60% to ~95%

The only manual steps remaining are Kim's: writing Seed Cards (Stage 2) and Listen-Through approval (Stage 6). Everything else is automated.

---

*— End of Handoff —*
