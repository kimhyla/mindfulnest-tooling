# MODULE PRODUCTION MASTER PLAN v2.0

**Version:** 2.0 (replaces v1.1)
**Date:** March 25, 2026
**Author:** Kim + Claude
**Status:** Active — governs all module production going forward

---

## 1. SCOPE AND CORRECTED MATH

### What We're Building

MindfulNest contains ~36 modules across 10 arcs. Each module has two phases:

- **Phase A:** The therapeutic demonstration — the creature models the technique for the child. Written as guided meditation/visualization with embedded therapeutic content.
- **Phase B:** The practice phase — the child applies the technique themselves. Written as an interactive exercise with audio guidance.

### The Real Numbers (Corrected from v1.1)

v1.1 estimated 19-23 Phase B scripts needed for Evolution modules. That was wrong. The corrected count:

**Phase B scripts needed: ~40-45 total**

This breaks down by weight class:

**Heavy Evolutions (5 modules) — ~2 hrs each, require full research dossiers:**

| Module | Why Heavy |
|--------|-----------|
| M16 | Significant technique deepening — clinical complexity requires careful Phase B redesign |
| M18 | Multi-technique integration — Phase B must weave multiple prior techniques together |
| M32 | Advanced emotional regulation — requires age-appropriate scaffolding of complex concepts |
| M35 | High-stakes therapeutic content — emotional intensity demands precise calibration |
| M36 | Capstone Evolution — synthesizes techniques from across the full journey |

**Medium Evolutions (8 modules) — ~1 hr each, require delta dossiers:**

| Module | Category |
|--------|----------|
| M8 | Technique refinement — builds on established base |
| M11 | Contextual Evolution — same technique, new emotional context |
| M28 | Complexity step-up — adds a layer to a familiar technique |
| M31 | Domain shift — technique applied in a new therapeutic domain |
| M33 | Integration Evolution — combines two previously separate techniques |
| + 3 additional | To be identified during intake triage (modules with moderate delta from base) |

**Light Evolutions (~27-32 modules) — ~30-60 min each:**

These are straightforward Phase B adaptations where the base technique changes only in narrative context, creature interaction, or difficulty level. The therapeutic core remains the same.

### New Spell Modules

Modules that introduce entirely new techniques (not Evolutions of existing ones) require the full pipeline from Stage 1 through Stage 10. Estimated time per new spell module: **1-2 hours of Kim time**.

### Total Kim Time Estimate

| Category | Count | Kim Time Per Module | Subtotal |
|----------|-------|-------------------|----------|
| Heavy Evolutions | 5 | ~45-60 min | ~4-5 hrs |
| Medium Evolutions | 8 | ~30-45 min | ~4-6 hrs |
| Light Evolutions | ~27-32 | ~15-25 min | ~7-13 hrs |
| New Spell Modules | varies | ~1-2 hrs | varies |
| **Total Kim hours (Evolutions only):** | **~40-45** | | **~15-24 hrs** |

**Full project estimate including all new spells: ~120-150 total Kim hours**

This is spread across multiple months of batch sessions. No single week should exceed ~10 hours of Kim review time.

---

## 2. THE 10-STAGE PIPELINE

Every module flows through these 10 stages, in order. No stage is skipped. Some stages are Claude-owned (asynchronous, no Kim time). Some are Kim-owned (hard gates — Claude does not proceed without Kim's approval).

```
Stage 1: INTAKE BRIEFS ........... Claude    (~2 min/module)
Stage 2: TRIAGE .................. Kim       (~5 min/module)
Stage 2.5: SEED CARDS ........... Kim       (~5 min/module)
Stage 3: RESEARCH ............... Claude    (~10-30 min/module)
Stage 4: RESEARCH REVIEW ........ Kim       (~15 min/dossier)
Stage 5: PHASE B DRAFTING ....... Claude    (~15-45 min/module)
Stage 6: PHASE B APPROVAL ....... Kim       (HARD GATE)
Stage 7: PHASE A + MODULE JSON .. Claude    (guardrails Q1-Q19)
Stage 8: DESIGN REVIEW .......... Kim       (~10 min/module)
Stage 9: AUDIO PRODUCTION ....... Claude Code (ElevenLabs + Vosk + ffmpeg)
Stage 10: LISTEN-THROUGH ........ Kim       (~5 min/module)
```

---

### Stage 1: INTAKE BRIEFS (Claude)

**Time:** ~2 min per module (automated)
**Owner:** Claude
**Inputs:** Technique Inventory, arc skeleton, base module (if Evolution)
**Output:** One Intake Brief per module

Claude reads the technique inventory, the relevant arc skeleton, and (for Evolutions) the base module that this module evolves from. Produces a structured Intake Brief containing:

- Module ID and arc placement
- Technique name and clinical basis
- For Evolutions: what the base module teaches and what THIS module adds
- Creature assignment and domain
- Narrative context from skeleton
- Proposed Phase B approach (Claude's initial read — Kim overrides in Seed Card)
- Flagged concerns (technique overlap, prerequisite gaps, complexity flags)

**Batch size:** All modules in one arc at once. One brief per module.

---

### Stage 2: TRIAGE (Kim, ~5 min/module)

**Time:** ~5 min per module
**Owner:** Kim
**Inputs:** Intake Briefs from Stage 1
**Output:** Triage decisions — categorize each module

Kim reviews each Intake Brief and assigns a weight class:

- **HEAVY** — Needs full research dossier, significant redesign from base
- **MEDIUM** — Needs delta dossier, moderate changes from base
- **LIGHT** — Straightforward adaptation, minimal research needed
- **SKIP** — Base module's Phase B works as-is (rare, but possible)

Kim also flags any modules where the Intake Brief's assumptions are wrong (wrong creature, wrong technique, wrong narrative context).

---

### Stage 2.5: SEED CARDS (Kim, ~5 min/module)

**Time:** ~5 min per module
**Owner:** Kim
**Inputs:** Intake Briefs + Kim's triage decisions
**Output:** One Seed Card per module (2-3 sentences)

This is the most important Kim input per module. The Seed Card is 2-3 sentences of therapeutic direction that tells Claude WHAT the Phase B should accomplish emotionally and therapeutically. It is NOT a script — it's a compass heading.

**Seed Card format:**

```
MODULE: [ID]
SEED: [2-3 sentences of therapeutic direction]
```

**Example Seed Cards:**

```
MODULE: M16
SEED: The child should feel the difference between "pushing away" a difficult
feeling and "making room for it." The exercise should use the body — actual
physical sensation of tension vs. softening. End with the child choosing to
keep the feeling present, not banish it.
```

```
MODULE: M31
SEED: This is the first time the child uses the Warrior Spell in a context
where they're not angry — they're scared. The Phase B needs to help them
discover that the same technique that channels anger can also channel fear
into action. Quick, physical, energizing.
```

**Why Seed Cards matter:** Without them, Claude writes Phase B scripts that are technically correct but therapeutically generic. The Seed Card is what makes each module feel like KIM designed it, not an AI. 5 minutes of Kim's therapeutic intuition saves 30 minutes of revision later.

---

### Stage 3: RESEARCH (Claude)

**Time:** ~10-30 min per module depending on weight
**Owner:** Claude
**Inputs:** Seed Card, Intake Brief, base module (for Evolutions), Technique Inventory, clinical references
**Output:** Research Dossier (full for HEAVY, delta for MEDIUM, none for LIGHT)

**For HEAVY modules — Full Research Dossier:**
Claude produces a comprehensive dossier including:
- Clinical evidence for the technique with the target age group (6-10)
- How the technique is typically taught in child therapy settings
- What makes this Evolution clinically distinct from the base version
- Specific therapeutic mechanisms that the Phase B should activate
- Contraindications or sensitivity flags
- Recommended exercise structure (based on clinical practice)
- How the Seed Card's direction aligns with or diverges from standard clinical practice

**For MEDIUM modules — Delta Dossier:**
Claude produces a focused comparison:
- What the base module's Phase B does
- What needs to change for this Evolution (and why)
- Clinical justification for the changes
- Specific elements to keep, modify, or replace

**For LIGHT modules — No dossier.**
Claude proceeds directly to Stage 5 using the base module + Seed Card.

---

### Stage 4: RESEARCH REVIEW (Kim, ~15 min/dossier)

**Time:** ~15 min per dossier (only HEAVY and MEDIUM modules)
**Owner:** Kim
**Inputs:** Research Dossier from Stage 3
**Output:** Approved dossier (with Kim's annotations/corrections)

Kim reviews the dossier for:
- Clinical accuracy — Is Claude's research correct?
- Therapeutic alignment — Does the proposed approach match Kim's vision?
- Age-appropriateness — Will this work for 6-10 year olds?
- Missing elements — Is there something Claude's research missed?

Kim annotates the dossier with corrections or additions, then approves it. Claude does NOT proceed to drafting without this approval for HEAVY and MEDIUM modules.

---

### Stage 5: PHASE B DRAFTING (Claude)

**Time:** ~15-45 min per module
**Owner:** Claude
**Inputs:** Approved dossier (or base module + Seed Card for LIGHT), style reference module
**Output:** Draft Phase B script

Claude drafts the Phase B script using:
1. The approved research dossier (HEAVY/MEDIUM) or base module + Seed Card (LIGHT)
2. A Kim-approved style reference module (a completed module that exemplifies the right tone, pacing, and therapeutic depth)
3. The Module Authoring Guide for structural rules
4. The arc skeleton for narrative context

**Critical rules for Phase B drafting:**
- Match the style reference's tone and pacing
- The Seed Card's therapeutic direction overrides Claude's research instincts
- No therapy-speak (see ArcBuilder production lessons anti-patterns)
- The child is an active participant, never a passive listener
- Every exercise must be physically doable by a child sitting or lying down
- End with integration — the child connects the exercise to their real life

---

### Stage 6: PHASE B APPROVAL (Kim — HARD GATE)

**Time:** Varies — this is the quality gate
**Owner:** Kim
**Inputs:** Draft Phase B from Stage 5
**Output:** Approved Phase B (or revision notes)

**This is the hardest gate in the pipeline.** Kim reads the Phase B script and decides:

- **APPROVED** — Proceed to Phase A
- **MINOR REVISIONS** — Claude fixes specific issues, Kim re-reviews
- **MAJOR REVISIONS** — Fundamental therapeutic approach needs rethinking. May require new Seed Card or new dossier.
- **RESTART** — Rare. The draft missed the mark entirely. Return to Stage 3 with new direction.

**Claude does NOT proceed past Stage 6 without Kim's explicit approval.** This is not a suggestion — it's a hard gate. No Phase A gets written until the Phase B is locked.

---

### Stage 7: PHASE A + MODULE JSON (Claude)

**Time:** ~15-30 min per module (automated)
**Owner:** Claude
**Inputs:** Approved Phase B, arc skeleton, Module Authoring Guide, Schema Guardrails
**Output:** Complete Phase A script + module JSON file

Claude writes Phase A (the creature demonstration phase) to match the approved Phase B, then assembles the complete module JSON. During assembly, Claude runs the Q1-Q19 guardrail checklist:

- Q1: Does the module ID match the skeleton?
- Q2: Is the technique name canonical (matches Spell Name Registry)?
- Q3: Does Phase A demonstrate what Phase B practices?
- Q4: Is the creature's role consistent with the skeleton?
- Q5-Q19: Full guardrail checklist per Schema Guardrails document

Any guardrail failure is flagged for Kim's review in Stage 8.

---

### Stage 8: DESIGN REVIEW (Kim, ~10 min/module)

**Time:** ~10 min per module
**Owner:** Kim
**Inputs:** Complete module (Phase A + Phase B + JSON)
**Output:** Approved module (or revision notes)

Kim reviews the complete module for:
- Phase A / Phase B coherence — does the demonstration match the practice?
- Narrative consistency — does the module fit its arc position?
- Therapeutic integrity — final check on clinical accuracy
- Any guardrail flags from Stage 7

---

### Stage 9: AUDIO PRODUCTION (Claude Code)

**Time:** ~5-10 min per module (automated)
**Owner:** Claude Code
**Inputs:** Approved module scripts
**Output:** Audio files (narration + ambient)

Automated pipeline:
1. **ElevenLabs** — Text-to-speech generation for all narration lines
2. **Vosk** — Speech-to-text verification (confirms generated audio matches script)
3. **ffmpeg** — Audio processing (normalization, ambient layering, timing assembly)

Quality checks:
- Vosk transcription matches script (>95% accuracy threshold)
- Audio levels within spec
- Timing matches expected module duration
- No artifacts, clicks, or dropout

---

### Stage 10: LISTEN-THROUGH (Kim, ~5 min/module)

**Time:** ~5 min per module
**Owner:** Kim
**Inputs:** Final audio files
**Output:** Ship-ready module (or audio revision notes)

Kim listens to the complete module audio and checks:
- Does it FEEL right? (The most important check — does it feel like MindfulNest?)
- Pacing — too fast? too slow? awkward pauses?
- Voice quality — any words that sound wrong?
- Emotional tone — does the audio match the script's intended feeling?

If the listen-through passes, the module is **DONE**. Ship-ready.

**Parent delivery (NEW March 25, 2026):** Ship-ready Phase B audio is also exposed to parents via a **"Play Spell" button** on parent technique cards. No additional production step — the same audio file serves both the child's module and the parent's card. See PARENT_DASHBOARD_ARCHITECTURE_v1_2.md §3B.

---

## 3. BATCH WORKFLOW

### One Queue Type Per Session

Each work session focuses on ONE type of work across multiple modules. This prevents context-switching overhead and ensures consistent quality.

**Session types:**

| Session Type | What Happens | Kim Time | Batch Size |
|-------------|-------------|----------|------------|
| **INTAKE** | Claude produces Intake Briefs, Kim triages + writes Seed Cards | ~10 min/module | Full arc (all modules) |
| **RESEARCH** | Claude produces dossiers, Kim reviews | ~15 min/dossier | 3-5 HEAVY/MEDIUM modules |
| **DRAFTING** | Claude drafts Phase B, Kim reviews | varies | 3-5 modules |
| **ASSEMBLY** | Claude writes Phase A + JSON, Kim does Design Review | ~10 min/module | 5-8 modules |
| **AUDIO** | Claude Code produces audio, Kim listens | ~5 min/module | 5-10 modules |

### Why One Queue Type Per Session

Mixing queue types in a single session causes:
- Context-switching fatigue for Kim (reviewing dossiers requires different mental mode than approving Phase B scripts)
- Context window bloat for Claude (loading research documents + style references + skeleton + module JSON simultaneously)
- Quality drift (attention degrades when alternating between different evaluation criteria)

### Recommended Weekly Rhythm

| Day | Session Type | Duration | Modules Processed |
|-----|-------------|----------|-------------------|
| Mon | INTAKE + SEED CARDS | 1.5 hrs | 8-10 modules |
| Tue | RESEARCH REVIEW | 1.5 hrs | 4-5 dossiers |
| Wed | DRAFTING REVIEW | 2 hrs | 3-5 Phase B scripts |
| Thu | ASSEMBLY REVIEW | 1.5 hrs | 5-8 modules |
| Fri | AUDIO LISTEN-THROUGH | 1 hr | 8-10 modules |

This is a suggestion, not a mandate. Kim adjusts based on energy and availability.

---

## 4. TIME ESTIMATES SUMMARY

### Per-Module Time (Kim's Active Time)

| Weight Class | Triage + Seed | Research Review | Phase B Review | Design Review | Listen-Through | Total Kim Time |
|-------------|--------------|----------------|---------------|--------------|----------------|----------------|
| HEAVY | 10 min | 15 min | 15-30 min | 10 min | 5 min | **55-70 min** |
| MEDIUM | 10 min | 10 min | 10-20 min | 10 min | 5 min | **45-55 min** |
| LIGHT | 10 min | — | 10-15 min | 10 min | 5 min | **35-40 min** |
| New Spell | 10 min | 15 min | 20-30 min | 10 min | 5 min | **60-70 min** |

### Project-Level Estimates

| Category | Module Count | Avg Kim Time | Subtotal |
|----------|-------------|-------------|----------|
| Heavy Evolutions | 5 | ~60 min | ~5 hrs |
| Medium Evolutions | 8 | ~50 min | ~7 hrs |
| Light Evolutions | ~27-32 | ~35 min | ~16-19 hrs |
| New Spells | ~10-15 (est.) | ~65 min | ~11-16 hrs |
| Overhead (session setup, staleness scans, batch admin) | — | — | ~10 hrs |
| **TOTAL** | **~50-60 modules** | | **~49-57 hrs** |

**Realistic estimate with revision cycles: ~120-150 total Kim hours**

The 49-57 hr figure assumes every module passes on first review. Real production includes revision cycles, re-reviews, edge cases, and decision-making sessions that don't fit neatly into the pipeline. The 120-150 hr range accounts for this reality.

**At ~8-10 hours/week, the full project takes ~12-18 weeks.**

---

## 5. TRACKING SPREADSHEET CONCEPT

### Purpose

A single spreadsheet that tracks every module through the 10-stage pipeline. Kim opens it at the start of every session to see what's ready for her review and what's in Claude's queue.

### Structure

**Sheet 1: Module Tracker (one row per module)**

| Column | Content |
|--------|---------|
| Module ID | M1, M2, ... M36+ |
| Arc | Which arc this module belongs to |
| Weight Class | HEAVY / MEDIUM / LIGHT / NEW |
| Stage 1: Intake | Date completed / — |
| Stage 2: Triage | Date completed / — |
| Stage 2.5: Seed Card | Date completed / — |
| Stage 3: Research | Date completed / — |
| Stage 4: Research Review | Date completed / — |
| Stage 5: Phase B Draft | Date completed / — |
| Stage 6: Phase B Approval | APPROVED / REVISION [N] / — |
| Stage 7: Phase A + JSON | Date completed / — |
| Stage 8: Design Review | APPROVED / REVISION [N] / — |
| Stage 9: Audio | Date completed / — |
| Stage 10: Listen-Through | SHIP-READY / REVISION / — |
| Notes | Free-text for flags, concerns, blockers |

**Sheet 2: Session Log**

| Column | Content |
|--------|---------|
| Date | Session date |
| Session Type | INTAKE / RESEARCH / DRAFTING / ASSEMBLY / AUDIO |
| Modules Touched | List of module IDs processed |
| Kim Time (actual) | Hours and minutes |
| Decisions Made | Key decisions that affect other modules |
| Blockers | Anything preventing progress |

**Sheet 3: Dashboard (auto-calculated)**

- Modules by stage (how many at each pipeline stage)
- Modules by weight class
- Estimated remaining Kim hours
- Projected completion date (based on weekly pace)
- Revision rate (what % of modules need re-review)

### Implementation Note

This spreadsheet should be created as an actual .xlsx file when production begins. The tracking concept here defines the structure; the working spreadsheet lives in the project folder and gets updated every session.

---

## 6. KEY PRINCIPLES

1. **Kim's time is the bottleneck.** Everything in this pipeline is designed to minimize Kim's active time while maximizing the quality of her input. Claude does the heavy lifting; Kim provides the therapeutic compass and the quality gates.

2. **Seed Cards are the secret weapon.** 5 minutes of Kim's therapeutic intuition in a Seed Card prevents 30+ minutes of revision later. Never skip them.

3. **Phase B before Phase A. Always.** The practice phase defines what the demonstration phase needs to show. Writing Phase A first is building a house before designing the floor plan.

4. **One queue type per session.** Context-switching kills quality. Batch similar work together.

5. **Hard gates are hard.** Stage 6 (Phase B Approval) is not a suggestion. Claude does not proceed without Kim's explicit sign-off. This is the single most important quality control in the entire pipeline.

6. **The math is real.** ~40-45 Phase B scripts, not 19-23. Plan for the real number. Under-estimating leads to crunch; over-estimating leads to better planning.

7. **Track everything.** The tracking spreadsheet isn't overhead — it's how Kim knows what to work on and how Claude knows what's approved. Without it, modules get lost in the pipeline.

8. **Audio is automated but not unreviewed.** Claude Code handles the technical audio pipeline, but Kim's listen-through is the final quality gate. A technically perfect audio file that doesn't FEEL right is not ship-ready.

---

## 7. MIGRATION FROM v1.1

### What Changed

| Area | v1.1 | v2.0 |
|------|------|------|
| Evolution count | 19-23 Phase B scripts | ~40-45 Phase B scripts |
| Pipeline stages | 8 stages | 10 stages (added Seed Cards and Listen-Through) |
| Seed Cards | Not in pipeline | Stage 2.5 — Kim's therapeutic direction per module |
| Research tiers | One size fits all | HEAVY / MEDIUM / LIGHT with appropriate dossier depth |
| Batch workflow | Ad hoc | One queue type per session |
| Time estimates | Optimistic | Realistic with revision cycles: 120-150 Kim hours |
| Tracking | Informal | Structured spreadsheet with dashboard |
| Audio QA | Not specified | Stage 10 Listen-Through with Kim approval |

### Action Items for Transition

1. Adopt the 10-stage pipeline immediately for all new module work
2. Modules already in progress under v1.1: complete their current stage, then transition to v2.0 pipeline
3. Create the tracking spreadsheet before the next production session
4. Re-triage all remaining modules using the HEAVY/MEDIUM/LIGHT weight system
5. Write Seed Cards for the next batch of modules before Claude begins drafting

---

*— End of Document —*
