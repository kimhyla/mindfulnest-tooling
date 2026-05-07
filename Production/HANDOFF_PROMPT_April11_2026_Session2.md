# Handoff Prompt — April 11, 2026 (Session 2 of 2)

**Copy everything below this line into your next thread as the opening message.**

---

This session is being continued from a previous conversation that ran out of context. The summary below covers TWO consecutive sessions on April 11, 2026 — one focused on safety hardening (Session 1), and one focused on autonomy assessment + gap-filling (Session 2). Together they represent the complete pipeline buildout.

## What These Two Sessions Accomplished

### Session 1: Safety Hardening (3 Rounds)

All 8 production skills were hardened with safety mechanisms across 3 rounds of verified edits:

**Round 1 (14 corrections):** kim_seeds completion gate, Version-Up Rule (4 skills), Pre-Write Kim Confirmation Gate (3 skills), Pipeline Stage Verification bash blocks (6 skills).

**Round 2 (7 corrections):** Filled gaps found by validators — missing Version-Up and Kim gates in phase-b-writer, audio-producer, phase-a-designer, module-json-builder.

**Round 3 (17 corrections):** Blocker-blind stage checks (6 files), filename mismatch (audio↔video alignment), rejection workflow, concurrent session guard, token TTL mandatory re-auth, read-before-write rules, intake handoff, Event 0 guard.

**Diff reports saved to:**
- `Production/SAFETY_FIXES_DIFF_REPORT_20260411.md` (Rounds 1-2)
- `Production/SAFETY_FIXES_ROUND3_DIFF_REPORT_20260411.md` (Round 3)

### Session 2: Autonomy Assessment + Gap-Filling (4 Batches)

Kim asked: "Can Claude produce everything in the pipeline autonomously (except human oversight steps)?" 

**Phase 1 — Assessment:** 5 agents analyzed the full pipeline. Found 13 potential gaps.

**Phase 2 — Counter-Verification:** 5 agents challenged each gap. Result: 7 of 13 were FALSE or OVERSTATED, leaving 6 verified real gaps.

**Phase 3 — Solution Design:** 5 agents designed solutions for the 6 real gaps, which expanded to 9 distinct fixes.

**Phase 4 — Implementation:** 9 fixes implemented across 4 batches, each with independent blind verification:

| Batch | Fixes | Files Modified |
|-------|-------|----------------|
| **1: Pipeline Collapse** | Removed kim_seeds stage entirely (6→5 stage pipeline), renumbered all 8 skills | All 8 skill SKILL.md files |
| **1B: API Retry** | Added API Retry Protocol (exponential backoff 2→32s, 5 attempts) | audio-producer, video-producer, narrative-generator |
| **2A: Email Notifications** | Added Gmail notification protocol for hard gates + API failures | dashboard-ops, phase-b-writer, audio-producer |
| **2B: Cost Circuit-Breaker** | Added $50/session threshold with per-API cost tracking | dashboard-ops, audio-producer, video-producer, narrative-generator |
| **3A: Cross-Stage Validation** | Added skeleton-vs-module validation at every stage | intake-briefer, phase-b-writer, phase-a-designer, module-json-builder |
| **3B: Sub-Step Tracking** | Added `sub_step` field for session resumption (Phase B: 0-9, Phase A: 1-5) | dashboard-ops, phase-b-writer, phase-a-designer |
| **4A: Pre-Write Gate Fix** | Added pipeline exemption to CLAUDE.md (generated files skip Kim gate) | CLAUDE.md |
| **4B: API Consolidation** | Created WAVESPEED_API_REFERENCE_v1.md (Seedance + ByteDance specs) | Production/WAVESPEED_API_REFERENCE_v1.md (new) |
| **4C: Dashboard Filters** | Added 5 additional Directus query patterns | dashboard-ops |

### Session 2 Final Actions: Backup Consolidation + Protocol Update

**Backup cleanup:** 23 scattered backup files (from all 4 batches + Session 1) were moved from 8 individual skill directories into `.claude/skills/_backups_20260411/`. That archive now holds **51 total backup files**. Zero backup files remain in active skill directories.

**Protocol update:** Added "Phase 5: Backup Cleanup" as the new final step in `verified-edit/SKILL.md`. The verified-edit protocol now has 5 phases: Correction List → Editing (7-step per-edit) → Self-Verification + Independent Validation → Diff Report → **Backup Cleanup**. The Quick Reference checklist was also updated.

---

## Current State: The 5-Stage Production Pipeline

### The Pipeline (Fully Operational as of April 11, 2026)

```
Stage 1: INTAKE ................. Claude            (~7-10 min/module)
Stage 2: PHASE B DRAFT+APPROVAL . Claude + Kim      (~15-45 min) — HARD GATE
Stage 3: PHASE A + MODULE JSON .. Claude + Kim       (~20-30 min/module)
Stage 4: AUDIO PRODUCTION ....... Claude Code        (ElevenLabs + ffmpeg)
Stage 5: LISTEN-THROUGH ......... Kim                (~5 min/module) — HARD GATE
```

**Directus stage keys:** `intake` → `phase_b` → `phase_a_json` → `audio` → `listen_through`

**Two-field status system:** `current_stage` (text FK) + `stage_status` (enum: not_started, in_progress, blocked, completed)

**Sub-step tracking:** `sub_step` field in Directus for Phase B (steps 0-9) and Phase A (steps 1-5), enabling session resumption

### Why kim_seeds Was Removed

The old Stage 2 ("kim_seeds") was removed because:
- Its workflow was undefined — no skill file, no file format, no completion signal
- Kim's creative/clinical direction is already captured during the Phase B review hard gate
- Intake now advances directly to `phase_b`

### The 8 Production Skills (all under `.claude/skills/`)

| # | Skill | Pipeline Role | Key Features |
|---|-------|--------------|--------------|
| 1 | **dashboard-ops** | Central hub | Auth, stage advancement, gate procedures, concurrent session safety, email notifications, cost tracking, sub-step tracking, additional filter patterns |
| 2 | **intake-briefer** | Stage 1 | Parse skeleton → Intake Briefs → Directus records, cross-stage validation |
| 3 | **phase-b-writer** | Stage 2 | 9-step meditation script production, rejection workflow, cross-stage validation, sub-step tracking |
| 4 | **phase-a-designer** | Stage 3a | Interactive demo beat sheet design, cross-stage validation, sub-step tracking |
| 5 | **module-json-builder** | Stage 3b | Assemble Firestore-ready module JSON, cross-stage validation, CDM enum check |
| 6 | **audio-producer** | Stage 4 | TTS → Vosk STT → breathCycle → ffmpeg mixing, API retry, cost circuit-breaker |
| 7 | **video-producer** | Master orchestrator | FLUX Kontext stills → Seedance animation → ByteDance lip sync → assembly, API retry, cost circuit-breaker |
| 8 | **narrative-generator** | Stage 3 | Haiku API generation of 6 aiNarrativeCache fields, Event 0 guard, API retry |

### Safety Mechanisms Now Present Across All Skills

| Mechanism | Where |
|-----------|-------|
| Pipeline Stage Verification (with blocker check) | 6 skills (all except dashboard-ops and audio-producer*) |
| Version-Up Rule | All 8 skills |
| Pre-Write Kim Confirmation Gate | All 8 skills |
| Read-Before-Write Rule | phase-b-writer, phase-a-designer, module-json-builder |
| Concurrent Session Safety | dashboard-ops (referenced by all) |
| Rejection Workflow | phase-b-writer |
| Mandatory Re-Auth Before Dashboard Updates | video-producer, phase-b-writer |
| API Retry Protocol (exponential backoff) | audio-producer, video-producer, narrative-generator |
| Email Notifications at Hard Gates | dashboard-ops, phase-b-writer, audio-producer |
| Cost Circuit-Breaker ($50/session) | dashboard-ops, audio-producer, video-producer, narrative-generator |
| Cross-Stage Validation (skeleton is source of truth) | intake-briefer, phase-b-writer, phase-a-designer, module-json-builder |
| Sub-Step Tracking (session resumption) | dashboard-ops, phase-b-writer, phase-a-designer |
| Pre-Write Gate Exemption for pipeline outputs | CLAUDE.md (global rule) |

*audio-producer delegates auth and dashboard updates to dashboard-ops.

---

## Video Production Pipeline

**3-Stage Flow:** FLUX Kontext Max image ($0.08/img, Pixar 3D style) → Seedance 1.5 Pro animation ($0.06/clip) → ByteDance Lipsync ($0.15/5s clip) = **~$0.26/scene**

**Visual style:** Pixar 3D (locked April 10, 2026 — supersedes painterly/Ori aesthetic)

**APIs:**
- FLUX Kontext Max: `POST api.bfl.ai/v1/flux-kontext-max` (BFL API key in API_KEYS_MASTER.md)
- Seedance 1.5 Pro: `POST api.wavespeed.ai/api/v3/bytedance/seedance-v1.5-pro/image-to-video`
- ByteDance Lipsync: `POST api.wavespeed.ai/api/v3/bytedance/lipsync/audio-to-video`
- Full specs: `Production/WAVESPEED_API_REFERENCE_v1.md`

**WaveSpeed credits:** Refilled to $150.13 on April 11 (Silver tier). Budget covers all of Arc 1 and likely Arc 2.

**Known issue:** Extra limbs in Seedance — mitigate with camera-motion prompts.

**File hosting for API inputs:** uguu.se for audio/video, imgur for images.

---

## Audio Production Pipeline

**Flow:** Approved Phase B script (with `{{INHALE_CUE}}` etc. markers) → ElevenLabs TTS voice stem → Vosk STT cue-point extraction → breathCycle rhythm assignment → ffmpeg multi-track mixing → flat MP3

**Key voice:** Myrrhin (ElevenLabs library voice) narrates ALL Phase B meditations + Opening Storybook.

**Audio file naming:** `m{N}_phase_b_complete_mix.mp3` (lowercase m, underscored — aligned across audio-producer and video-producer)

**Volume architecture:** Voice -12dB, Breath sounds -24dB, Transitions -18dB, Ambient -36dB

**Cost:** ~$0.70-1.80/module (dominated by TTS iteration)

**Asset gaps:** M4 (Ember) and M6 (Bramble) need new ambient beds before audio production. 57 existing MP3 assets inventoried in audio-producer skill references.

**ElevenLabs API key:** In `Production/API_KEYS_MASTER.md` (and in `.auto-memory/reference_elevenlabs.md`)

---

## Directus Dashboard

- **URL:** `https://directus-production-3460.up.railway.app`
- **Auth:** POST `/auth/login` → JWT (15-min TTL). Credentials in `Production/API_KEYS_MASTER.md`
- **Admin:** kimhyla11@gmail.com
- **Hosted on:** Railway (project `efficient-grace`), connected to Supabase PostgreSQL
- **Current state:** 20 `prod_*` collections registered, Kanban preset on `prod_modules`, 6 Arc 1 modules seeded (all currently `not_started`)
- **7 tracking fields (added April 11):** kim_notes, claude_approach, edge_cases, narrative_integration, learnings, next_batch, status_updated
- **Kim uses multiple Claude threads simultaneously** — the Concurrent Session Safety section in dashboard-ops addresses this

---

## Verified-Edit Protocol (Current: 5-Phase)

The protocol for any multi-file editing work now has 5 phases:

1. **Phase 0: Correction List** — Write a detailed master correction list as a file (not from memory)
2. **Phase 1: Editing** — 7-step per-edit protocol: PRE-READ → PRE-GREP → BACKUP → EDIT → POST-GREP → NEGATIVE GREP → LOG
3. **Phase 2: Self-Verification** — Retired term check, edit count validation, formatting check
4. **Phase 3: Independent Validation** — Fresh agent reads files cold, verifies every edit landed
5. **Phase 4: Diff Report** — Generate diff report for Kim's review
6. **Phase 5: Backup Cleanup** — Move all backups to `_backups_YYYYMMDD/`, verify zero remain in working dirs

Skill file: `.claude/skills/verified-edit/SKILL.md`

---

## Backup Archive

All 51 backup files from April 11 (both sessions) are consolidated in `.claude/skills/_backups_20260411/`. Naming convention: `{source-directory}__{original-filename}.md`. Safe to delete once Kim confirms stability.

---

## Key Files and Documents

### Production Pipeline Files
- `Production/WAVESPEED_API_REFERENCE_v1.md` — Consolidated Seedance + ByteDance API specs (NEW, created this session)
- `Production/SAFETY_FIXES_DIFF_REPORT_20260411.md` — Rounds 1-2 diff report
- `Production/SAFETY_FIXES_ROUND3_DIFF_REPORT_20260411.md` — Round 3 diff report
- `Production/API_KEYS_MASTER.md` — All API keys (read at runtime, never hardcode)
- `Production/MODULE_PRODUCTION_MASTER_PLAN_v2_0.md` — Original master plan
- `Production/HANDOFF_PROMPT_April11_2026.md` — Session 1 handoff (for deep reference)
- `Production/HANDOFF_PROMPT_April11_2026_Session2.md` — THIS document

### Canonical Authorities (current versions)
- `CLAUDE_Everdale_World_Design_Bible_v13_10.md` (Bible)
- `NARRATIVE_DECISIONS_UNIFIED_v2_8.md` (NDU — often more current than Bible)
- `ARC_PRODUCTION_BIBLE_v2_10.md`
- `ArcBuilder_v2_3.md`
- `UNIFIED_TECHNIQUE_INVENTORY_v1_14.md`
- `CANONICAL_DATA_MODEL_v1_12.md`
- `TTS_PERSONALIZATION_PIPELINE_v1.md`

### Key Business/Strategy Documents
- `MindfulNest_CRI_Parent_System_Business_Model_v1.md` — Current business model
- `MINDFULNEST_VIRAL_GROWTH_EXECUTIVE_SUMMARY.md` — 8 ranked growth strategies
- `AI_PARENT_COACH_DECISIONS_EXTRACTED.md` — Locked Architecture A decisions
- See `.auto-memory/reference_project_files.md` for the full 200+ document guide

---

## CLAUDE.md Key Rules (Quick Reference)

These are in the project-level CLAUDE.md and govern ALL Claude behavior:

1. **NEVER modify document content without explicit instruction**
2. **Version-up, never overwrite** — always create v(N+1), never write over existing
3. **Single-format workflow** — working docs are .docx ONLY, reference docs are .md
4. **Kim-confirmation gate** — must ask Kim with FULL FILENAME before overwriting any working doc. Pipeline-generated outputs are EXEMPT.
5. **Source Fidelity** — Kim's dialogue is copied character-for-character, never retyped through Claude
6. **M-Number Convention** — M1=Tessa, M2=Luna, M3=Benson, M4=Ember, M5=Bork, M6=Bramble. FIXED.
7. **Read existing docs first** — before any analytical/strategic work, search for and read existing project docs
8. **Session-start staleness scan** — required before any production work (see CLAUDE.md for full procedure)

---

## Kim's Working Style and Preferences

**From this session and prior feedback (stored in `.auto-memory/`):**

- Kim wants **exhaustive verification** — multiple agents, multi-pass checks, independent blind validation. No shortcuts or "acceptable risk."
- Kim uses **multiple Claude threads simultaneously** — skills must handle concurrency
- Kim is the **sole founder** building MindfulNest with AI tools (Lovable, Cursor, Claude Code). No engineering team.
- Kim is a **doctoral candidate** — CRI (Competence-Rooted Identity) is her proprietary clinical framework
- **Narrative-first design** — MindfulNest is a "story game"; narrative entertainment comes first, techniques serve the story
- **Phase A must be simple** — shows WHAT (ingredients + outcome), not HOW. No vocabulary, no sensation language
- **Always use spell names** in conversation, never clinical labels
- **File outputs always go to the Dropbox project folder** — never stray paths
- Kim's email: kimhyla11@gmail.com (for Gmail MCP notifications at hard gates)

---

## What Should Happen Next

The pipeline is now fully built, safety-hardened, and ready for production. Likely next steps:

1. **Run the staleness scan** (required by CLAUDE.md at session start) — last one was not performed during these sessions since they went straight into infrastructure work
2. **Run the first module through the pipeline** — intake Arc 1 modules and start producing. M4 (Ember/Heart-Sending) has the most existing production progress. All 6 Arc 1 modules are seeded in Directus as `not_started`.
3. **Check dashboard status** — verify the 6 Arc 1 modules on the Directus board
4. **Asset gap work** — M4 (Ember) and M6 (Bramble) need new ambient beds before audio production
5. **Any other MindfulNest work** — marketing, dissertation, arc skeleton work, website, etc.

---

## Technical Quick Reference

| Item | Value |
|------|-------|
| Directus URL | `https://directus-production-3460.up.railway.app` |
| Auth | JWT, 15-min TTL, credentials in API_KEYS_MASTER.md |
| Pipeline stages | `intake` → `phase_b` → `phase_a_json` → `audio` → `listen_through` |
| Status fields | `current_stage` + `stage_status` (not_started/in_progress/blocked/completed) |
| Hard gates | `phase_b` and `listen_through` — require Kim's explicit approval |
| Phase B audio naming | `m{N}_phase_b_complete_mix.mp3` |
| Video cost/scene | ~$0.26 (FLUX $0.08 + Seedance $0.06 + Lipsync $0.15) |
| Audio cost/module | ~$0.70-1.80 |
| WaveSpeed balance | ~$150 (Silver tier) |
| BFL (FLUX) credits | ~920 remaining |
| Cost circuit-breaker | $50/session |
| Backup archive | `.claude/skills/_backups_20260411/` (51 files) |
| Memory system | `.auto-memory/MEMORY.md` (index) → individual memory files |
