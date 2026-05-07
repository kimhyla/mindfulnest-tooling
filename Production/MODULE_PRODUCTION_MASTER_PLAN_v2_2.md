# MODULE PRODUCTION MASTER PLAN v2.2

**Version:** 2.2 (replaces v2.1)
**Date:** April 14, 2026
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

Modules that introduce entirely new techniques (not Evolutions of existing ones) require the full pipeline from Stage 1 through Stage 5. Estimated time per new spell module: **1-2 hours of Kim time**.

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

## 2. THE 5-STAGE PIPELINE

Every module flows through these 5 stages, in order. No stage is skipped. Some stages are Claude-owned (asynchronous, no Kim time). Some are Kim-owned (hard gates — Claude does not proceed without Kim's approval).

```
Stage 1: INTAKE ......................... Claude    (~7-10 min/module)
Stage 2: PHASE B DRAFT + APPROVAL ...... Claude + Kim (HARD GATE)
Stage 3: PHASE A + JSON BUILD .......... Claude    (~15-30 min/module)
Stage 4: AUDIO PRODUCTION .............. Claude Code (ElevenLabs + ffmpeg)
Stage 5: LISTEN-THROUGH ................ Kim       (~5 min/module) — HARD GATE
```

**Removed from v2.0:** Research stage, Research Review, standalone Design Review, Triage as separate stage. **Removed from v2.1:** Kim Seeds stage (Kim's therapeutic direction now captured during Phase B approval gate; Claude performs synthesis in Intake).

---

### Stage 1: INTAKE (Claude)

**Time:** ~7-10 min per module (includes therapeutic synthesis)
**Owner:** Claude
**Inputs:** Technique Inventory, arc skeleton, base module (if Evolution), CRI framework, narrative context
**Output:** One Intake Brief per module with Proposed Phase B Approach

Claude reads the technique inventory, arc skeleton, CRI framework, and (for Evolutions) the base module that this module evolves from. Claude performs therapeutic synthesis, generating a structured Intake Brief containing:

- Module ID and arc placement
- Technique name and clinical basis
- For Evolutions: what the base module teaches and what THIS module adds
- Creature assignment and domain
- Narrative context from skeleton
- **Proposed Phase B Approach** (Claude's emergent synthesis of technique inventory, skeleton, CRI framework, and narrative context — Kim redirects during Phase B approval if needed)
- Flagged concerns (technique overlap, prerequisite gaps, complexity flags, weight class preliminary assessment)

**Batch size:** All modules in one arc at once. One brief per module.

---

### Stage 2: PHASE B DRAFT + APPROVAL (Claude + Kim — HARD GATE)

**Time:** ~30-60 min per module
**Owner:** Claude (drafting) + Kim (approval)
**Inputs:** Seed Card, Intake Brief, base module (for Evolutions), Technique Inventory, style reference module
**Output:** Approved Phase B script (or revision notes)

#### 2A: Phase B Drafting (Claude)

Claude drafts the Phase B script using:
1. The Proposed Phase B Approach from Stage 1 Intake as therapeutic foundation
2. The base module (for Evolutions) or Technique Inventory (for new spells)
3. A Kim-approved style reference module (a completed module that exemplifies the right tone, pacing, and therapeutic depth)
4. The Module Authoring Guide for structural rules
5. The arc skeleton for narrative context

**Critical rules for Phase B drafting:**
- Match the style reference's tone and pacing
- The Proposed Phase B Approach is a starting point; Kim's input during approval can redirect
- No therapy-speak (see ArcBuilder production lessons anti-patterns)
- The child is an active participant, never a passive listener
- Every exercise must be physically doable by a child sitting or lying down
- End with integration — the child connects the exercise to their real life

#### 2B: Phase B Approval (Kim — HARD GATE)

**This is the hardest gate in the pipeline.** Kim reads the Phase B script and decides:

- **APPROVED** — Proceed to Phase A
- **MINOR REVISIONS** — Claude fixes specific issues, Kim re-reviews
- **MAJOR REVISIONS** — Fundamental therapeutic approach needs rethinking. Return to Stage 1 with new direction.
- **RESTART** — Rare. The draft missed the mark entirely. Return to Stage 1 for deeper synthesis.

**Claude does NOT proceed past Stage 2 without Kim's explicit approval.** This is not a suggestion — it's a hard gate. No Phase A gets written until the Phase B is locked.

---

### Stage 3: PHASE A + JSON BUILD (Claude)

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

Any guardrail failure is flagged for Kim's review in Stage 5. Minor guardrail issues are fixed directly by Claude (no re-review needed).

---

### Stage 4: AUDIO PRODUCTION (Claude Code)

**Time:** ~10-20 min per module (automated)
**Owner:** Claude Code
**Inputs:** Approved module scripts, character reference images from Production/ folders, shot-by-shot production plan
**Output:** Audio files (narration + ambient) + video clips (intro + resolution sequences)

#### 4A: Audio Pipeline
1. **ElevenLabs** — Text-to-speech generation for all narration lines
2. **ffmpeg** — Audio processing (normalization, ambient layering, timing assembly)

Audio quality checks:
- Audio levels within spec
- Timing matches expected module duration
- No artifacts, clicks, or dropout

#### 4B: Video Pipeline (Updated April 10, 2026)
1. **FLUX Kontext [max]** — Generate key scene stills from character reference images ($0.08/img)
2. **Seedance 2.0 / Kling 3.0** — Animate stills with motion prompts, keyframe control, and video extension for scene continuity (~$0.05-0.10/sec)
3. **ByteDance LipSync** — Sync animated clips to TTS dialogue audio for talking scenes ($0.15/5sec)
4. **ffmpeg** — Final assembly, transitions, audio overlay

Video quality checks:
- Character consistency across clips (matches Production/ reference images)
- Smooth video extension transitions (no visual jumps between chained clips)
- Lip sync accuracy on dialogue scenes
- Pixar 3D style consistency throughout
- ~$0.25-0.35 per 5-second dialogue scene

---

### Stage 5: LISTEN-THROUGH (Kim — HARD GATE)

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

## 3. BATCH PRODUCTION STRATEGY

### Assembly-Line Batching

The 5-stage pipeline is optimized for **assembly-line batching** — modules move through the same stage in parallel before Kim's review, then proceed as a batch to the next stage.

**Batching pattern:**

1. **Stage 1 Intake** — Claude produces all Intake Briefs for an arc at once, including Proposed Phase B Approach synthesis (8-10 modules)
2. **Stage 2 Drafting** — Claude drafts Phase B scripts for a batch (4-6 modules at once, leveraging shared narrative context and Intake synthesis)
3. **Stage 2 Approval** — Kim reviews all 4-6 Phase B scripts as one batch, providing therapeutic direction and weight class assignments (~90-150 min depending on weight class)
4. **Stage 3 Phase A + JSON** — Claude builds Phase A and JSON for all approved modules in parallel
5. **Stage 4 Audio** — Claude Code produces audio/video for all approved modules in parallel
6. **Stage 5 Listen-Through** — Kim listens to all finalized audio in one session (~30-50 min for 5-8 modules)

### Benefits of Batch Production

- **Reduced context-switching for Kim** — She reviews all Phase B scripts for an arc together, maintaining narrative consistency and making faster decisions
- **Parallel Claude work** — Audio and Phase A production don't wait for Kim's individual module approvals
- **More consistent quality** — Reviewing all 4-6 scripts together highlights inconsistencies that serial review misses
- **Better pacing** — Kim's full review cycles (Seed Cards → Phase B Approval → Listen-Through) take ~3-5 hours per batch instead of spreading across multiple sessions

### Session Structure

Each work session focuses on ONE pipeline stage across multiple modules:

| Session Type | What Happens | Kim Time | Batch Size | Duration |
|---|---|---|---|---|
| **INTAKE** | Claude produces Intake Briefs + Proposed Phase B Approach for one arc | ~7-10 min/module | Full arc (8-10 modules) | ~70-100 min (async) |
| **PHASE B BATCH** | Claude drafts Phase B scripts, Kim reviews + assigns weight classes | ~15-30 min/module | 4-6 modules | ~90-150 min |
| **ASSEMBLY** | Claude builds Phase A + JSON, assembles modules | ~10-15 min/module | 5-8 modules | ~50-90 min (async) |
| **AUDIO** | Claude Code produces audio + video, Kim listens | ~10 min/module | 5-8 modules | ~50-80 min |

### Why One Queue Type Per Session

Mixing queue types in a single session causes:
- Context-switching fatigue for Kim (approving Phase B scripts requires different mental mode than listening to audio)
- Context window bloat for Claude (loading reference modules + skeleton + base modules simultaneously)
- Quality drift (attention degrades when alternating between different evaluation criteria)

### Recommended Weekly Rhythm (Suggestion)

| Day | Session Type | Duration | Modules Processed |
|-----|-------------|----------|-------------------|
| Mon | INTAKE | 2 hrs | 8-10 modules (with synthesis) |
| Tue | PHASE B BATCH | 2-2.5 hrs | 4-6 Phase B scripts |
| Wed | ASSEMBLY | 1.5 hrs | 5-8 modules |
| Thu | AUDIO | 1.5 hrs | 5-8 modules |
| Fri | (Buffer or next arc INTAKE) | — | — |

This is a suggestion, not a mandate. Kim adjusts based on energy and availability.

---

## 4. DIRECTUS PRODUCTION DASHBOARD

The 5-stage pipeline is tracked and managed via **Directus**, a free, open-source self-hosted headless CMS deployed on Railway.

### Why Directus

- **API-first:** Claude (via dashboard-ops skill) operates entirely via API — no browser needed
- **Customizable collections:** 19 prod_* collections in Supabase (one per module + master tables)
- **Kanban workflow:** Visual drag-and-drop by pipeline stage (Stage 1, Stage 2, Stage 3, Stage 4, Stage 5)
- **Two-field status system:** `current_stage` + `stage_status` (approved/revision/pending)
- **Hard gates enforced:** prod_approvals table prevents Claude from advancing past Kim approval gates
- **Role-based access:** Kim sees full dashboard; Claude reads via API only (writes through dashboard-ops)

### Dashboard Collections (Schema)

**Core collections:**

| Collection | Purpose | Fields |
|---|---|---|
| prod_modules | Module master | module_id, arc, weight_class, title |
| prod_stage_1_intake | Intake Briefs + Proposed Phase B Approach | module_id, brief_text, proposed_phase_b, created_at |
| prod_stage_2_phase_b | Phase B scripts | module_id, draft_text, status, kim_approval, revision_notes, weight_class |
| prod_stage_3_phase_a_json | Phase A + JSON | module_id, phase_a_text, json_file, guardrail_flags |
| prod_stage_4_audio | Audio + Video | module_id, audio_file_url, video_file_url, production_date |
| prod_stage_5_listen | Listen-Through | module_id, kim_approval, pacing_notes, ship_ready_date |
| prod_approvals | Hard gates | module_id, stage, approval_status, approved_by, approved_at |
| prod_sessions | Session log | session_date, session_type, modules_touched, kim_hours_actual, blockers |
| prod_dashboard | Summary stats | total_modules, modules_by_stage, revision_rate, completion_eta |

### Dashboard Operations (via API)

Claude (dashboard-ops skill) performs these operations:

- **Create Intake Brief record** — After Stage 1 completion (includes Proposed Phase B Approach)
- **Move module to Stage 2** — Only after stage_1_intake status = complete
- **Update Phase B status** — Draft/revision/approved as Kim reviews
- **Prevent Stage 3 advance** — Dashboard-ops refuses to create stage_3_phase_a_json record unless prod_approvals shows stage_2_phase_b = approved
- **Log listen-through result** — Kim marks prod_stage_5_listen = approved or revision
- **Report production status** — Kanban summary for Kim's weekly check-in

### Hard Gate Enforcement

The Directus API enforces hard gates via the prod_approvals table:

```
prod_approvals table:
  - module_id (foreign key to prod_modules)
  - stage (1–5)
  - approval_status (pending / approved / revision_needed)
  - approved_by (kim / — for Claude-only stages)
  - approved_at (timestamp)
```

**Before Claude advances past a Kim gate (Stages 2 or 5):**
- dashboard-ops queries prod_approvals WHERE module_id = X AND stage = 2 (or 5)
- If approval_status != approved, dashboard-ops returns error: "Stage 2 approval required before advancing"
- Claude logs error and waits for Kim to update the approval record

### Implementation Notes

- **Deployment:** Directus on Railway (free tier, self-hosted)
- **Database:** Supabase (PostgreSQL backend)
- **API authentication:** Directus access token issued to Claude (via dashboard-ops skill)
- **Kim's interface:** Web UI at Directus dashboard (Railway URL), no CLI needed
- **Initial setup:** ~1 hour to configure collections, create access token, set up hard gate logic

---

## 5. TIME ESTIMATES SUMMARY

### Per-Module Time (Kim's Active Time)

| Weight Class | Phase B Review | Listen-Through | Total Kim Time |
|-------------|----------------|----------------|----------------|
| HEAVY | 15-30 min | 5 min | **20-35 min** |
| MEDIUM | 10-20 min | 5 min | **15-25 min** |
| LIGHT | 10-15 min | 5 min | **15-20 min** |
| New Spell | 20-30 min | 5 min | **25-35 min** |

**Note:** These are per-module times. Batching reduces total Kim time by ~20-30% through amortized decision-making and parallelized Claude work.

### Project-Level Estimates

| Category | Module Count | Avg Kim Time | Subtotal |
|----------|-------------|-------------|----------|
| Heavy Evolutions | 5 | ~27.5 min | ~2.3 hrs |
| Medium Evolutions | 8 | ~20 min | ~2.7 hrs |
| Light Evolutions | ~27-32 | ~17.5 min | ~7.5-9.3 hrs |
| New Spells | ~10-15 (est.) | ~30 min | ~5-7.5 hrs |
| Overhead (batch setup, listen-through consolidation, decision cycles) | — | — | ~5-8 hrs |
| **TOTAL** | **~50-60 modules** | | **~22.5-29 hrs** |

**Realistic estimate with revision cycles: ~60-100 total Kim hours**

The 22.5-29 hr figure assumes every module passes on first review. Real production includes revision cycles, re-reviews, edge cases, and decision-making sessions that don't fit neatly into the pipeline. The 60-100 hr range accounts for this reality and reflects the efficiency gains of batching plus Kim's therapeutic synthesis being embedded in Stage 1 instead of a separate stage.

**At ~8-10 hours/week, the full project takes ~7-12 weeks.**

This is a 30-50% time reduction from v2.0 (120-150 hrs) thanks to batching, removal of Research stage, collapse of Kim Seeds into Phase B approval, and Directus automation.

---

## 6. TRACKING AND VISIBILITY

### Dashboard Kanban View

The Directus dashboard displays all modules in a Kanban view:

```
Stage 1: INTAKE    | Stage 2: PHASE B  | Stage 3: PHASE A  | Stage 4: AUDIO    | Stage 5: LISTEN
————————————————————|———————————————————|———————————————————|———————————————————|—————————————————
M1 (Ready)         | M1 (Draft)        | M1 (Complete)     | M1 (Complete)     | M1 (Approved)
M2 (Ready)         | M2 (Approved)     | M2 (Complete)     | M2 (Complete)     | M2 (Approved)
M3 (Ready)         | M3 (Revision)     | —                 | —                 | —
...                | ...               | ...               | ...               | ...
```

**Kim's session checklist:**

1. Open Directus dashboard at session start
2. Review which modules are waiting in her queues (Stage 2 approvals, Stage 5 listen)
3. Process batch (Phase B approvals or Listen-Throughs)
4. Update module status via dashboard (or via dashboard-ops API calls)
5. Close session with production summary

### Session Log and Metrics

The prod_sessions table captures:

| Field | Purpose |
|---|---|
| session_date | When session occurred |
| session_type | INTAKE / PHASE_B / ASSEMBLY / AUDIO |
| modules_touched | CSV list of module IDs processed |
| kim_hours_actual | Clock time spent (vs. estimated) |
| decisions_made | Key decisions affecting other modules |
| blockers | Anything preventing progress |

**Auto-calculated dashboard metrics:**

- Modules by stage (how many at each pipeline stage)
- Modules by weight class (HEAVY / MEDIUM / LIGHT)
- Revision rate (what % of modules needed re-review)
- Estimated remaining Kim hours (based on module count and weight distribution)
- Projected completion date (based on weekly pace)

---

## 7. KEY PRINCIPLES

1. **Kim's time is the bottleneck.** Everything in this pipeline is designed to minimize Kim's active time while maximizing the quality of her input. Claude does the heavy lifting; Kim provides the therapeutic compass and the quality gates.

2. **Claude's therapeutic synthesis replaces Seed Cards.** The Stage 1 Intake now includes a Proposed Phase B Approach generated by Claude reading technique inventory, skeleton, CRI framework, and narrative context. This synthesis gives Claude the therapeutic foundation to draft Phase B scripts; Kim's approval at Stage 2 provides the redirect if needed. The result: more coherent drafts, fewer revision cycles.

3. **Phase B before Phase A. Always.** The practice phase defines what the demonstration phase needs to show. Writing Phase A first is building a house before designing the floor plan.

4. **One queue type per session.** Context-switching kills quality. Batch similar work together.

5. **Hard gates are hard.** Stages 2 (Phase B Approval) and 5 (Listen-Through) are not suggestions. Claude does not proceed without Kim's explicit sign-off. Directus enforces this at the API level.

6. **Batching is the efficiency lever.** Assembly-line batching (4-6 modules together through each stage) reduces Kim's context-switching and enables parallel Claude work. This is why v2.2 is 30-50% faster than v2.0.

7. **The math is real.** ~40-45 Phase B scripts, not 19-23. Plan for the real number. ~60-100 total Kim hours with batching and synthesis, not 120-150. Under-estimating leads to crunch; over-estimating leads to better planning.

8. **Track everything.** The Directus dashboard isn't overhead — it's how Kim knows what to work on and how Claude knows what's approved. Without it, modules get lost in the pipeline.

9. **Audio and video are automated but not unreviewed.** Claude Code handles the technical audio and video pipelines (ElevenLabs TTS + FLUX Kontext scene stills + Seedance/Kling animation + ByteDance LipSync), but Kim's listen-through is the final quality gate. A technically perfect audio/video file that doesn't FEEL right is not ship-ready.

---

## 8. MIGRATION FROM v2.0 → v2.1 → v2.2

### What Changed (v2.0 → v2.1)

| Area | v2.0 | v2.1 |
|------|------|------|
| Pipeline stages | 10 stages | 6 stages (removed Research, Research Review, Triage as standalone) |
| Research dossiers | Yes (HEAVY/MEDIUM/LIGHT differentiation) | No (replaced by Seed Cards) |
| Triage | Separate stage | Folded into Kim Seeds stage |
| Design Review | Separate stage | Folded into Phase A build (guardrails Q1-Q19) |
| Seed Cards | Stage 2.5 | Stage 2 (integrated with weight class assignment) |
| Batching | Ad hoc | Formalized: 4-6 modules batch through each stage together |
| Production tracking | Spreadsheet concept | Directus dashboard (free, open source, Railway-hosted) |
| Hard gates | 5 gates (Stages 2, 4, 6, 8, 10) | 2 gates (Stages 3, 6) — harder and more tightly enforced |
| Time estimates | ~120-150 hrs | ~80-120 hrs (30-50% reduction via batching) |
| Listen-Through | Optional | Required hard gate (Kim approval mandatory) |

### What Changed (v2.1 → v2.2)

| Area | v2.1 | v2.2 |
|------|------|------|
| Pipeline stages | 6 stages | 5 stages (removed Kim Seeds) |
| Kim Seeds workflow | Separate Stage 2 (~5 min/module) | Integrated into Stage 2 Phase B approval (weight class assignment happens during review) |
| Stage 1 Intake time | ~2 min/module | ~7-10 min/module (includes Claude therapeutic synthesis) |
| Intake output | Intake Brief only | Intake Brief + Proposed Phase B Approach |
| Hard gates | Stages 3, 6 | Stages 2, 5 (renumbered; same gates, different stages) |
| Time estimates | ~80-120 hrs | ~60-100 hrs (additional 15-20% reduction from synthesis + Kim gate collapsing) |
| Directus collections | 10 stage-specific collections | 9 stage-specific collections (removed prod_stage_2_seeds, renumbered stages) |
| Session types | INTAKE, KIM SEEDS, PHASE_B, ASSEMBLY, AUDIO | INTAKE, PHASE_B, ASSEMBLY, AUDIO |

### Action Items for Transition (v2.1 → v2.2)

1. Adopt the 5-stage pipeline immediately for all new module work
2. Modules already in Stage 2 (Kim Seeds) under v2.1: complete their current seed-writing pass, then advance directly to Stage 2 (Phase B Drafting) under v2.2 with Kim's weight class assignment included in approval
3. **Update Directus schema** — remove prod_stage_2_seeds collection, rename remaining stage collections (prod_stage_3_phase_b → prod_stage_2_phase_b, etc.)
4. **Update session tracking** — remove KIM SEEDS session type from prod_sessions
5. **Re-wire dashboard-ops skill** — ensure API calls reference correct stage numbers (1, 2, 3, 4, 5)
6. Move next batch to Stage 1 (INTAKE with synthesis) under v2.2 workflow

---

## 9. CHANGELOG

### v2.2 — April 14, 2026

**Major changes:**
- Collapsed 6-stage pipeline to 5 stages
  - Removed: Kim Seeds (old Stage 2) — workflow integrated into Phase B approval hard gate
  - Renumbered: old Stage 3→2, old Stage 4→3, old Stage 5→4, old Stage 6→5
- **Stage 1 INTAKE now includes Claude therapeutic synthesis**
  - Intake time increased from ~2 min to ~7-10 min per module
  - Output now includes Proposed Phase B Approach (Claude's synthesis of technique inventory, skeleton, CRI framework, narrative context)
  - This synthesis replaces the need for a separate Seed Card writing stage
- **Weight class assignment moved to Phase B approval gate**
  - Kim assigns weight class during Phase B review (instead of separate Seeds stage)
  - Collapses two Kim review steps (Seed Card review + Phase B review) into one
- Updated time estimates: ~60-100 hrs total (vs. v2.1 ~80-120 hrs) — additional 15-20% reduction from synthesis + Kim gate collapsing
- Updated all stage references throughout (renumbered 1-5)
- Restructured Directus collections: removed prod_stage_2_seeds, renumbered remaining stage tables
- Updated Session Log types: removed KIM SEEDS session type
- Updated Kanban view to 5 columns (INTAKE, PHASE B, PHASE A, AUDIO, LISTEN)
- Updated Weekly Rhythm to show revised session timing (INTAKE now 2 hrs with synthesis)
- Revised KEY PRINCIPLES: replaced "Seed Cards are the secret weapon" with "Claude's therapeutic synthesis replaces Seed Cards"

**Rationale:**
- Kim Seeds stage was operationally undefined (no file format, no skill, no completion signal beyond "seed card written")
- Kim's therapeutic direction is captured at the Phase B approval gate anyway — the Seed Card was a proxy for that gate
- By moving synthesis work into Claude's Intake stage, we frontload the therapeutic reasoning and give Kim clearer Phase B drafts to review
- Result: fewer revision cycles, tighter Phase B→Phase A alignment, and simpler production workflow

**Sources:**
- HANDOFF_PROMPT_April11_2026_Session2.md (decision to eliminate Kim Seeds)
- April 14, 2026 v2.1→v2.2 transition session

### v2.1 — April 11, 2026

**Major changes:**
- Collapsed 10-stage pipeline to 6 stages
  - Removed: Research (old Stage 4), Research Review (old Stage 5), standalone Design Review (old Stage 9), Triage as separate stage
  - Folded Triage into Kim Seeds (Stage 2)
  - Folded Design Review into Phase A build (guardrails Q1-Q19)
- Added formalized batch production strategy (assembly-line batching: 4-6 modules per batch through each stage)
- Added Directus production dashboard section (free, self-hosted, Railway-deployed, API-first)
- Updated time estimates: ~80-120 hrs total (vs. v2.0 ~120-150 hrs) — 30-50% reduction via batching
- Restructured per-module time table to reflect v2.1 stage sequence
- Added hard gate enforcement description (Directus prod_approvals table)
- Clarified that Design Review passes happen during Phase A build (no separate stage)
- Updated session structure table to reflect 6-stage batch workflow

**Sources:**
- MASTER_CHANGE_LIST_April11.md (Section D: Structural/Format Rules)
- SESSION_DECISIONS_April10_2026_PRODUCTION_STRATEGY.md
- .auto-memory/production_workflow_10stage_pipeline.md (April 10 memory update)

### v2.0 — March 25, 2026
- Introduced 10-stage pipeline with Seed Cards and Listen-Through
- Established HEAVY/MEDIUM/LIGHT weight class system
- Introduced ~40-45 Phase B scripts math (correcting v1.1)
- Introduced Module Tracker spreadsheet concept

---

*— End of Document —*
