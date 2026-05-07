# MODULE PIPELINE AI TOOLING ACCELERATION v1

**Version:** 1.0
**Date:** April 1, 2026
**Status:** DRAFT — Pending Kim's approval before implementation
**Companion to:** MODULE_PRODUCTION_MASTER_PLAN_v2_0.md
**Also references:** AUDIO_PIPELINE_MASTER_PLAN_v1.md, VISUAL_PIPELINE_MASTER_PLAN_v5.md
**Purpose:** Map AI tools to each pipeline stage to maximize automation and minimize Kim's active production hours. Every recommendation in this document serves one goal: **reduce the 120-150 Kim hours without reducing quality.**

---

## TABLE OF CONTENTS

1. [Pipeline Bottleneck Analysis](#1-pipeline-bottleneck-analysis)
2. [Tool-to-Stage Map](#2-tool-to-stage-map)
3. [Stage-by-Stage Integration Specs](#3-stage-by-stage-integration-specs)
4. [Workflow Orchestration Layer (n8n)](#4-workflow-orchestration-layer-n8n)
5. [Phase B Archetype Templates](#5-phase-b-archetype-templates)
6. [Automated QA Layer (Playwright)](#6-automated-qa-layer-playwright)
7. [Clinical Research Acceleration (Elicit)](#7-clinical-research-acceleration-elicit)
8. [Phase A Component Generation (Cursor)](#8-phase-a-component-generation-cursor)
9. [Cost Summary](#9-cost-summary)
10. [Implementation Sequence](#10-implementation-sequence)
11. [What We Tested and Rejected](#11-what-we-tested-and-rejected)
12. [Open Questions for Kim](#12-open-questions-for-kim)

---

## 1. PIPELINE BOTTLENECK ANALYSIS

### Where Kim's Time Actually Goes

From Module Production Master Plan v2.0, Kim's per-module time breaks down as:

| Activity | Kim Time (avg) | Reducible? |
|----------|---------------|------------|
| Triage + Seed Card (Stages 2/2.5) | 10 min | NO — this is Kim's therapeutic compass. Irreplaceable. |
| Research Review (Stage 4) | 10-15 min | YES — if the dossier arrives higher-quality, review is faster |
| Phase B Review (Stage 6) | 10-30 min | YES — if drafts are closer to target on first pass |
| Design Review (Stage 8) | 10 min | PARTIALLY — automated QA catches structural errors before Kim sees it |
| Listen-Through (Stage 10) | 5 min | NO — Kim's ear is the final quality gate |

**The two biggest levers:**
1. **Stage 4 (Research Review)** — if dossiers are built from real cited evidence instead of Claude's training data recall, Kim spends less time correcting clinical inaccuracies
2. **Stage 6 (Phase B Review)** — if drafts follow proven structural templates, Kim's revision rate drops

### Where Claude's Time Goes (and What's Wasted)

| Activity | Current Time | Waste Source |
|----------|-------------|-------------|
| Stage 1 (Intake Briefs) | ~2 min/module | None — already fast |
| Stage 3 (Research) | 10-30 min/module | Claude draws from training data, not live clinical databases. May hallucinate citations. |
| Stage 5 (Phase B Draft) | 15-45 min/module | No structural templates — Claude re-invents the Phase B structure each time |
| Stage 7 (Phase A + JSON) | 15-30 min/module | Phase A components built from scratch instead of adapted from proven prototypes |
| Stage 9 (Audio) | 5-10 min/module | Already well-automated (ElevenLabs + Vosk + ffmpeg) |

### Cross-Stage Waste: Manual Handoffs

The 10 stages run through manual Kim↔Claude conversation handoffs. Each handoff involves:
- Kim opening a new session or continuing an existing one
- Claude re-loading context (pipeline docs, skeleton, technique inventory)
- Kim indicating which modules are approved and which need revision
- Claude parsing Kim's feedback and routing to the correct next stage

**Estimated overhead per handoff: 5-10 minutes of session setup + context loading.** With ~5-8 handoffs per module across its pipeline life, that's 25-80 minutes of overhead per module that produces zero content.

---

## 2. TOOL-TO-STAGE MAP

| Stage | Current Tool | New Tool | What Changes | Monthly Cost |
|-------|-------------|----------|-------------|-------------|
| 1: Intake Briefs | Claude (conversation) | **n8n** triggers Claude API | Automated batch generation — no session needed | $60/mo (shared) |
| 2: Triage | Kim (manual) | No change | Kim's judgment is irreplaceable | — |
| 2.5: Seed Cards | Kim (manual) | No change | Kim's therapeutic direction is irreplaceable | — |
| 3: Research | Claude (training data) | **Elicit** + Claude | Elicit finds real papers; Claude synthesizes into dossier format | ~$49/mo |
| 4: Research Review | Kim (reads dossier) | No change (but faster due to better dossiers) | Kim reviews higher-quality input | — |
| 5: Phase B Draft | Claude (ad hoc) | Claude + **Archetype Templates** | Templates provide proven structural scaffolding | $0 (one-time creation) |
| 6: Phase B Approval | Kim (hard gate) | No change | Sacred gate. Never automated. | — |
| 7: Phase A + JSON | Claude (ad hoc) | **Cursor** + existing JSX prototypes | Component generation from prototypes + descriptions | $20/mo |
| 8: Design Review | Kim (manual) | Kim + **Playwright** pre-check | Automated QA catches structural errors before Kim reviews | $0 |
| 9: Audio | Claude Code (ElevenLabs/Vosk/ffmpeg) | No change | Already well-automated | — |
| 10: Listen-Through | Kim (listens) | No change | Kim's ear is the final gate | — |
| Cross-stage | Manual session handoffs | **n8n** orchestration | Automated routing, approval queues, status tracking | $60/mo (shared) |

**Total new monthly cost: ~$129/mo** ($60 n8n + $49 Elicit + $20 Cursor)

---

## 3. STAGE-BY-STAGE INTEGRATION SPECS

### Stage 1 → n8n Automation

**Current:** Kim asks Claude in a conversation to produce intake briefs for an arc's modules.
**New:** Kim triggers an n8n workflow (button click or scheduled). The workflow:

1. Reads the arc skeleton from the project folder (Dropbox-synced)
2. Reads the Technique Inventory (v1.9) and relevant base modules
3. Calls Claude API (Sonnet) with a structured prompt for each module
4. Outputs formatted Intake Briefs to a designated folder
5. Sends Kim a notification (email or Slack) that briefs are ready for triage

**Kim's new time: 0 minutes** (was ~2 min/module of session overhead, now fully automated)

**n8n workflow nodes:**
```
[Trigger: Manual/Schedule] → [Read Skeleton File] → [Read Technique Inventory] →
[Loop: For Each Module] → [Claude API: Generate Intake Brief] → [Write to File] →
[Send Notification to Kim]
```

### Stage 3 → Elicit + Claude

**Current:** Claude generates research dossiers from its training knowledge. Risk of hallucinated citations and missed recent research.
**New:** Two-step process:

**Step 3a: Elicit Evidence Pull (~2-5 min/module, automated)**
- Input: technique name + "children ages 7-10" + "guided practice" + relevant clinical terms
- Elicit searches its database of ~200M academic papers
- Returns: relevant papers with extracted findings, sample sizes, effect sizes, age ranges
- Output: structured evidence table with real citations

**Step 3b: Claude Dossier Assembly (~5-10 min/module, automated)**
- Input: Elicit evidence table + Seed Card + base module (for Evolutions) + Technique Inventory
- Claude synthesizes into the Research Dossier format per Module Production Master Plan
- Every citation in the dossier traces to an Elicit-verified paper
- Output: formatted Research Dossier ready for Kim's Stage 4 review

**Kim benefit:** Dossiers arrive with real citations. Kim spends less time fact-checking and more time applying therapeutic judgment. Estimated review time reduction: **15 min → 8-10 min per dossier** for HEAVY modules.

**Elicit subscription:** Elicit Plus at ~$49/month provides 12,000 paper analyses per month — more than enough for the full project. (Verify current pricing at elicit.com.)

### Stage 5 → Archetype Templates

See Section 5 below for full template specifications.

### Stage 7 → Cursor + JSX Prototypes

See Section 8 below for full Phase A generation specs.

### Stage 8 → Playwright Pre-Check

See Section 6 below for full QA specs.

---

## 4. WORKFLOW ORCHESTRATION LAYER (n8n)

### Why n8n

n8n is an open-source workflow automation platform with dedicated AI nodes. It replaces manual session handoffs with automated routing. Key advantages over alternatives:

| Platform | Why n8n wins |
|----------|-------------|
| Make.com | Make charges per operation. A 10-step module pipeline × 50 modules = 500 executions × 10 operations each = 5,000 operations. At Make's pricing, this costs ~$250/mo. n8n charges per execution: 500 executions on the $60/mo Pro plan. |
| Zapier | Same per-operation pricing problem as Make. Also slower for complex multi-step workflows. |
| Custom scripts | Works, but no visual debugging, no retry logic, no approval queue UI, no notification routing. |
| LangChain | Developer framework — powerful but requires engineering maintenance. n8n is visual and Kim can see pipeline status without code. |

### n8n Architecture for MindfulNest Module Pipeline

**Workflow 1: INTAKE BATCH**
```
Trigger: Kim clicks "Run Intake" for Arc N
→ Read arc skeleton from Dropbox
→ Parse module list from skeleton
→ For each module:
  → Read Technique Inventory entry
  → Read base module (if Evolution)
  → Call Claude API (Sonnet): generate Intake Brief
  → Save brief to /Intake_Briefs/ARC_N/
→ Email Kim: "Arc N intake briefs ready (X modules)"
```

**Workflow 2: RESEARCH BATCH**
```
Trigger: Kim marks modules as triaged (via form or spreadsheet update)
→ For each triaged module (HEAVY or MEDIUM):
  → Call Elicit API: evidence search for technique
  → Collect Elicit results
  → Call Claude API (Opus): synthesize into Research Dossier
  → Save dossier to /Research_Dossiers/
→ Email Kim: "X dossiers ready for review"
```

**Workflow 3: DRAFTING BATCH**
```
Trigger: Kim marks dossiers as approved (via form)
→ For each approved module:
  → Load: approved dossier + Seed Card + archetype template + style reference
  → Call Claude API (Opus): draft Phase B script
  → Save draft to /Phase_B_Drafts/
→ Email Kim: "X Phase B drafts ready for review"
```

**Workflow 4: ASSEMBLY BATCH**
```
Trigger: Kim marks Phase B scripts as approved
→ For each approved module:
  → Generate Phase A component (Cursor or Claude API)
  → Assemble module JSON (Claude API with guardrail checklist)
  → Run Playwright validation suite
  → Save to /Assembled_Modules/
  → If Playwright passes: Email Kim "Module M## ready for Design Review"
  → If Playwright fails: Flag for Claude review, do not send to Kim
```

**Workflow 5: AUDIO BATCH**
```
Trigger: Kim marks Design Review as approved
→ For each approved module:
  → Call ElevenLabs API: generate voice stem (3 takes)
  → Select best take by duration match
  → Run Vosk verification
  → Run ffmpeg mixing script
  → Save final audio to /Audio/
→ Email Kim: "X modules ready for listen-through"
```

### n8n Implementation Notes

- **Self-hosted vs. cloud:** n8n Cloud ($60/mo Pro) is recommended for simplicity. Self-hosted is free but requires a server.
- **Elicit API access:** Elicit offers API access for programmatic evidence searches. If not available, the Elicit step can be manual (Kim or Claude runs the search in the Elicit web UI) with results fed into n8n via a file drop or webhook.
- **Claude API credentials:** n8n has a native Anthropic node. Use the same API key as the existing Parent Coach system.
- **Approval mechanism:** n8n supports "Wait" nodes that pause a workflow until a webhook is triggered. Kim's approval can be a simple email link ("Click to approve M16") or a lightweight web form that triggers the webhook.
- **Error handling:** Each workflow should have error branches that log failures and notify Claude (via a separate session or alert) without blocking other modules in the batch.

---

## 5. PHASE B ARCHETYPE TEMPLATES

### The Problem

Claude currently drafts each Phase B script from scratch, guided by the Seed Card, dossier, and Module Authoring Guide. The structural decisions (section ordering, pacing, transition language, how to handle the 7-section template) are re-derived every time. This leads to:
- Inconsistent section proportions (some scripts spend too long on WELCOME, others rush INTEGRATION)
- Structural variety where consistency would be better (children benefit from predictable meditation structure)
- Revision cycles caused by structural issues rather than therapeutic content issues

### The Solution

Create 5 archetype templates — one per primary therapeutic modality — that provide the structural scaffolding for Phase B scripts. Claude fills in the therapeutic content from the Seed Card and dossier. Kim reviews content, not structure.

**Archetype 1: BODY-SENSING** (Magic Hands, Ground-Strong, Body Scan variants)
- Emphasis: physical sensation discovery → naming → staying with
- Section weights: WELCOME (5%), CONNECTION (10%), ARRIVAL (15%), PRACTICE CORE (40%), DEEPENING (15%), INTEGRATION (10%), CLOSING (5%)
- Pacing: slow, deliberate, lots of silence markers
- Characteristic: body-part scanning sequence, "notice without changing" language
- Used for: M1, M7, M13, M19, M25, M31 and their Evolutions

**Archetype 2: BREATHING** (Belly Breathing, Breath-Squeezers, Humming, 4-7-8 variants)
- Emphasis: rhythm establishment → counting/timing → body response awareness
- Section weights: WELCOME (5%), CONNECTION (10%), ARRIVAL (10%), PRACTICE CORE (45%), DEEPENING (15%), INTEGRATION (10%), CLOSING (5%)
- Pacing: rhythmic, tied to breath cycles, breathCycle markers embedded
- Characteristic: count-based repetition, inhale/exhale markers, progressive depth
- Used for: M2, M4, M6, M8, M10, M14 and their Evolutions

**Archetype 3: MINDFULNESS/WATCHING** (Thought Clouds, Letting Go, Present Moment variants)
- Emphasis: attention placement → observation without engagement → return to anchor
- Section weights: WELCOME (5%), CONNECTION (10%), ARRIVAL (10%), PRACTICE CORE (35%), DEEPENING (20%), INTEGRATION (15%), CLOSING (5%)
- Pacing: medium, with strategic pauses for "watching" practice
- Characteristic: "notice... and let it go" patterns, non-judgment language, anchor returns
- Used for: M3, M9, M15, M21, M27, M33 and their Evolutions

**Archetype 4: COURAGE/ACTION** (Brave Steps, Brave Sniffing, Warrior variants)
- Emphasis: energy building → channeling → directed action → pride/strength
- Section weights: WELCOME (5%), CONNECTION (10%), ARRIVAL (10%), PRACTICE CORE (40%), DEEPENING (15%), INTEGRATION (15%), CLOSING (5%)
- Pacing: builds from calm to energized, then settles
- Characteristic: empowerment language, physical activation cues, "you are strong" beats
- Used for: M5, M11, M17, M23, M29, M35 and their Evolutions

**Archetype 5: COMPASSION/CONNECTION** (Heart-Sending, Warm Heart, Friend-Fix variants)
- Emphasis: warmth generation → directed sending → receiving → expansion
- Section weights: WELCOME (5%), CONNECTION (10%), ARRIVAL (10%), PRACTICE CORE (35%), DEEPENING (20%), INTEGRATION (15%), CLOSING (5%)
- Pacing: warm and slow, emotionally layered
- Characteristic: warmth/light imagery, "sending" language, progressive circle expansion (self → friend → difficult person → all)
- Used for: M6, M12, M18, M24, M30, M36 and their Evolutions

### Template Format

Each archetype template is a document containing:
1. **Section-by-section structure** with word count targets per section
2. **Transition phrases** — approved language for moving between sections (drawn from Kim-approved Phase B scripts M1-M3)
3. **Pacing markers** — where to place `[PAUSE 3s]`, `[PAUSE 5s]`, `[BREATHE]` markers
4. **Anti-patterns** — specific to this archetype (e.g., "In BODY-SENSING, never ask the child to change what they feel — only to notice it")
5. **Example script** — one completed Kim-approved script as the gold standard

### Implementation

Create these templates as .md files in a `/Phase_B_Templates/` folder. Claude loads the relevant template at Stage 5 alongside the Seed Card and dossier. The template constrains structure; the Seed Card and dossier provide content.

**Estimated creation time:** One focused session with Kim (~2-3 hours) to review existing approved scripts (M1-M3), extract structural patterns, and validate the 5 archetype definitions. Claude drafts the templates; Kim refines.

---

## 6. AUTOMATED QA LAYER (Playwright)

### What Playwright Tests

Playwright is a free, open-source end-to-end testing framework. For MindfulNest module production, it runs automated checks that currently happen manually during Claude's Stage 7 guardrail pass and Kim's Stage 8 Design Review.

**Test Suite 1: Module JSON Validation**
```
For each module JSON file:
✓ Module ID matches skeleton assignment
✓ Technique name matches Spell Name Registry (canonical)
✓ Creature assignment matches skeleton
✓ Domain matches creature's assigned domain
✓ All required fields present (per CLAUDE_MODULE_JSON_SCHEMA_GUARDRAILS_v2_3.md)
✓ Phase A and Phase B sections both present
✓ Coin reward within expected range for arc level
✓ Decoration item present with name and rarity tier
✓ Spell card entry present
✓ No retired terminology (GlowDrop, Shelby, Kindness Stone, XP, etc.)
✓ Personalization variables use correct syntax ({childName}, not [childName])
✓ All dialogue lines tagged with speaker character
```

**Test Suite 2: Phase A Component Validation**
```
For each Phase A React component:
✓ Component renders without errors
✓ No missing imports
✓ No hardcoded child names (must use {childName} variable)
✓ Component responds to expected user interactions (tap, drag, etc.)
✓ Duration falls within 60-90 second range when simulated
✓ Accessibility: minimum tap target sizes for child users
```

**Test Suite 3: Phase B Script Validation**
```
For each Phase B meditation script:
✓ Duration within 60-120 seconds at 2 words/second
✓ 7-section structure present (WELCOME, CONNECTION, ARRIVAL, PRACTICE CORE, DEEPENING, INTEGRATION, CLOSING)
✓ No therapy-speak (flagged terms: "regulate," "dysregulated," "coping mechanism," "therapeutic," etc.)
✓ Personalization variables present in WELCOME and/or CLOSING
✓ Breath markers present for breathing-domain scripts
✓ No "you should feel" or "you will feel" language (prescriptive feeling)
✓ Script ends with integration beat (connecting to real life)
```

**Test Suite 4: Cross-Module Consistency**
```
Across all modules in an arc:
✓ No duplicate excitement spikers within same domain
✓ Coin rewards scale appropriately across the arc
✓ Creature assignments match the arc skeleton's event table
✓ No technique name conflicts between modules
```

### Implementation

**Step 1:** Install Playwright in the project: `npm init playwright@latest`
**Step 2:** Create test files in `/tests/modules/` matching the 4 suites above
**Step 3:** Integrate into n8n Workflow 4 (Assembly Batch) as a validation step
**Step 4:** Playwright outputs a pass/fail report per module. Failed modules get flagged for Claude review. Only passing modules reach Kim's Design Review queue.

**Kim time saved:** Estimated 3-5 minutes per module that would otherwise be spent catching structural errors during Design Review. Over 50 modules: **2.5-4 hours of Kim time saved.**

---

## 7. CLINICAL RESEARCH ACCELERATION (Elicit)

### What Elicit Does

Elicit is an AI-powered research tool that searches ~200M+ academic papers and extracts structured data from them. It does not generate text — it finds real papers with real citations and pulls out specific data points (sample sizes, effect sizes, age ranges, methodologies, findings).

### How It Fits the Pipeline

**Current Stage 3 process (Claude from training data):**
1. Claude recalls relevant clinical information from training
2. Claude structures it into dossier format
3. Risk: hallucinated citations, outdated findings, missed recent research
4. Kim must fact-check every clinical claim during Stage 4 review

**New Stage 3 process (Elicit + Claude):**
1. Elicit searches for: `[technique name] + children + ages 7-10 + guided practice`
2. Elicit returns: 10-30 relevant papers with extracted findings
3. Claude synthesizes Elicit's verified evidence into dossier format
4. Every citation in the dossier links to a real paper Kim can verify
5. Kim reviews therapeutic alignment, not factual accuracy

### Elicit Query Templates

For each module weight class, a standardized Elicit query:

**HEAVY modules:**
```
Query: "[Technique clinical name] guided practice children ages 6-11"
Filters: Peer-reviewed, published 2015-2026, sample includes children
Extract: Effect sizes, age-specific findings, recommended duration,
         contraindications, comparison with adult practice
```

**MEDIUM modules (delta dossier):**
```
Query: "[Base technique] vs [evolved technique] children"
Filters: Same as above
Extract: What distinguishes the evolved form, clinical justification
         for progression, prerequisite skills
```

**LIGHT modules:** No Elicit search needed (base module's evidence applies).

### Cost and Access

- **Elicit Plus:** ~$49/month (12,000 paper analyses/month)
- **Project need:** ~200-400 paper analyses total (5 HEAVY × 30 papers + 8 MEDIUM × 15 papers + buffer)
- **Timeline:** 1-2 months of Elicit subscription covers the entire project's research needs
- **API access:** Elicit offers API endpoints for programmatic searches — integrates with n8n
- **Fallback:** If Elicit API is unavailable, run searches manually in the Elicit web UI and export results as CSV for Claude to process

---

## 8. PHASE A COMPONENT GENERATION (Cursor)

### The Opportunity

MindfulNest already has 10+ Phase A JSX prototypes:
- `belly_breathing_full_module.jsx`
- `thought_clouds_full_module.jsx`
- `brave_steps_full_module.jsx`
- `warm_heart_full_module.jsx`
- `squeeze_release_full_module.jsx`
- `sense_anchor_full_module.jsx`
- `mindful_listening_full_module.jsx`
- `sleepy_stargazing_full_module.jsx`
- `worry_box_full_module.jsx`
- `friend_fix_bridge_full_module.jsx`

These prototypes establish the Phase A interaction patterns. New modules need variations of these patterns, not entirely new components.

### Cursor Workflow

**Step 1:** Open the project in Cursor with all JSX prototypes in context
**Step 2:** For each new module, provide Cursor with:
- The therapeutic note from the skeleton (what this module teaches)
- The closest existing prototype (e.g., "this is a breathing variant, use belly_breathing as base")
- The Phase B script (so Phase A demonstration matches what the child will practice)
- Specific instructions: "Generate a Phase A component for M16 that demonstrates [technique]. Use belly_breathing_full_module.jsx as structural reference. Change the visual metaphor from belly → [new metaphor]. Keep the interaction pattern (tap to start, guided animation, bridge cue)."

**Step 3:** Cursor generates the component. Claude reviews for Module Authoring Guide compliance. Playwright validates rendering.

**Estimated time reduction:** Stage 7 drops from 15-30 min/module to ~5-10 min/module for component generation. The JSON assembly portion remains the same.

### Cost

Cursor Pro: $20/month. Covers unlimited completions and chat.

---

## 9. COST SUMMARY

### New Monthly Costs

| Tool | Monthly Cost | What It Replaces | Break-Even |
|------|-------------|-----------------|------------|
| n8n Cloud (Pro) | $60 | Manual session handoffs, batch triggering, approval routing | Saves ~25-80 min overhead per module × 50 modules = 20-66 hours |
| Elicit Plus | $49 | Claude training-data-only research, hallucinated citations | Saves ~5-7 min Kim review per HEAVY/MEDIUM dossier × 13 modules = ~1-1.5 hours + quality improvement |
| Cursor Pro | $20 | Ad-hoc Phase A component writing | Saves ~10-20 min per module at Stage 7 × 50 modules = 8-16 hours |
| **Total** | **$129/mo** | | |

### One-Time Costs

| Item | Cost | Notes |
|------|------|-------|
| Phase B Archetype Templates | $0 (Kim + Claude session time) | ~2-3 hours Kim time to create |
| Playwright test suite | $0 (open source) | ~4-6 hours Claude Code time to build |
| n8n workflow build | $0 (included in subscription) | ~8-12 hours Claude time to configure |

### Projected Time Savings

| Category | Current Estimate | With Tooling | Savings |
|----------|-----------------|-------------|---------|
| Kim active hours (total project) | 120-150 hrs | 90-115 hrs | ~25-35 hrs |
| Claude session overhead | ~40-60 hrs | ~15-25 hrs | ~25-35 hrs |
| Revision cycles (due to better first drafts) | ~30-40 hrs | ~15-25 hrs | ~15 hrs |
| **Total project time reduction** | | | **~65-85 hours** |

At $129/month over ~4-5 months of active production: **~$520-645 total tool cost** to save ~65-85 hours. That's $6-10 per hour saved.

---

## 10. IMPLEMENTATION SEQUENCE

### Phase 0: Foundations (Week 1 — ~4 hours Kim, ~12 hours Claude)

1. **Create Phase B Archetype Templates** — Kim + Claude session to analyze M1-M3 approved scripts, extract structural patterns, define 5 archetypes. Output: 5 template .md files.
2. **Set up Elicit account** — Kim creates account at elicit.com. Run test query for one HEAVY module technique to validate output quality.
3. **Set up n8n Cloud account** — Kim creates account. Claude builds Workflow 1 (Intake Batch) as proof of concept.

### Phase 1: Validation (Week 2 — ~2 hours Kim, ~8 hours Claude)

4. **Run Intake Batch via n8n** for one arc — compare output quality to manually-produced intake briefs. Kim reviews.
5. **Run Elicit research** for 2-3 HEAVY module techniques — compare dossier quality to Claude-only dossiers. Kim reviews.
6. **Draft Phase B script using archetype template** — compare to ad-hoc Claude draft. Kim reviews.
7. **Decision gate:** Kim approves or adjusts each tool's integration before full rollout.

### Phase 2: Full Integration (Week 3-4 — ~6 hours Claude)

8. **Build remaining n8n workflows** (Research Batch, Drafting Batch, Assembly Batch, Audio Batch)
9. **Build Playwright test suite** (4 test suites per Section 6)
10. **Configure Cursor project** with all JSX prototypes loaded as context
11. **Connect n8n to Playwright** (Assembly workflow triggers test suite automatically)

### Phase 3: Production (Week 5+ — ongoing)

12. **All new module production runs through the tooled pipeline**
13. **Track metrics:** revision rate, Kim time per module, first-pass approval rate
14. **Monthly review:** Are the tools delivering the projected savings? Adjust or remove underperforming tools.

---

## 11. WHAT WE TESTED AND REJECTED

Tools researched and determined NOT to be worth adding:

| Tool | What It Does | Why Rejected |
|------|-------------|-------------|
| **Wondercraft AI / Serenify** | AI meditation generators | Generate generic relaxation meditations. Cannot follow CRI framework, Module Authoring Guide, or Source Fidelity rules. Output requires more editing than drafting from scratch with Claude. |
| **Voxtral TTS (Mistral)** | Alternative TTS at $0.016/1K chars | Marginal cost savings over ElevenLabs at current scale. Not worth switching a proven pipeline for ~$1 savings per child. Revisit at 50K+ children. |
| **Chatterbox / Coqui XTTS** | Open-source self-hosted TTS | Requires engineering infrastructure to host. Eliminates ElevenLabs dependency but adds server maintenance. Not justified at current scale. |
| **Hamming AI / Cekura** | Enterprise voice agent testing | $2K+/month. Designed for customer service voice bots, not children's meditation content. Overkill. |
| **Lovable AI** | Full-stack AI app builder | MindfulNest's tech stack (Next.js + Supabase + Phaser) is already decided. Lovable would be rebuilding, not accelerating. |
| **Make.com / Zapier** | Workflow automation | Per-operation pricing makes multi-step module pipelines expensive. n8n is 3-5x cheaper for this use case. |
| **Vellum AI** | Prompt management platform | Enterprise-grade, designed for teams managing hundreds of prompts in production. Kim + Claude's prompt management is conversational and sufficient. |
| **LangChain / LangFlow** | AI pipeline framework | Powerful but requires engineering maintenance. n8n provides 80% of the functionality with visual interface and zero code maintenance. |

---

## 12. OPEN QUESTIONS FOR KIM

1. **Elicit access level:** Does Elicit Plus ($49/mo) provide API access, or is that enterprise-only? If API isn't available, the n8n integration for Stage 3 would use a manual step (Kim/Claude runs Elicit search in browser, exports CSV, drops into a folder that n8n watches). Still valuable, just less automated.

2. **n8n approval mechanism:** What's Kim's preferred way to approve/reject modules between stages? Options:
   - Email with approve/reject links
   - Simple web form (n8n can generate these)
   - Spreadsheet-based (Kim updates a tracking sheet, n8n watches for changes)
   - Stay conversational (Kim tells Claude in a session, Claude triggers n8n)

3. **Phase B template session timing:** The archetype templates need ~2-3 hours of focused Kim time to create. Should this be scheduled as a dedicated session before production begins, or created incrementally as each archetype is needed?

4. **Cursor vs. Claude Code for Phase A:** Cursor Pro ($20/mo) is recommended for Phase A component generation because of its IDE integration and codebase-aware context. However, Claude Code (which Kim already uses) can do similar work. Is the additional $20/mo justified, or should we try Claude Code first and only add Cursor if the output quality is insufficient?

5. **Playwright test suite ownership:** Who maintains the test suite as new module types are added? Recommendation: Claude maintains it, but Kim should know it exists and can request new test cases.

---

## DOCUMENT HISTORY

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | April 1, 2026 | Initial draft. Research completed across pipeline docs, AI tool landscape, and existing MindfulNest architecture. |

---

*This document is a companion to MODULE_PRODUCTION_MASTER_PLAN_v2_0.md. When the Master Plan is next versioned, add a cross-reference: "See MODULE_PIPELINE_AI_TOOLING_ACCELERATION_v1.md for tool integration specifications."*

*— End of Document —*
