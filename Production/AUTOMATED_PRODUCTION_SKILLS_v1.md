# AUTOMATED PRODUCTION SKILLS — MindfulNest Module Pipeline

**Version:** 1.0
**Date:** April 11, 2026
**Status:** Reference document — comprehensive inventory of all production skills and remaining gaps
**Context:** Generated after triple-blind evaluation of all 7 production skills, 36 verified corrections, and end-to-end readiness audit

---

## PURPOSE

This document serves two functions:

1. **Part 1** is a verified inventory of every production skill, its role in the 6-stage pipeline, its inputs/outputs, dashboard integration status, and key configuration details — all confirmed accurate as of April 11, 2026.

2. **Part 2** is a detailed specification of every remaining gap that must be built before the pipeline is fully automated end-to-end.

Together, these parts constitute the complete picture of "what works now" and "what still needs to be built" for MindfulNest's automated module production system.

---

## THE 6-STAGE PIPELINE (Reference)

Every module flows through these stages. No stage is skipped.

```
Stage 1: INTAKE .................. Claude        (~2 min/module)
Stage 2: KIM SEEDS .............. Kim           (~5 min/module)
Stage 3: PHASE B DRAFT + APPROVAL Claude + Kim  (HARD GATE)
Stage 4: PHASE A + JSON BUILD ... Claude        (~15-30 min/module)
Stage 5: AUDIO PRODUCTION ....... Claude Code   (ElevenLabs + ffmpeg)
Stage 6: LISTEN-THROUGH ......... Kim           (~5 min/module — HARD GATE)
```

Hard gates at Stage 3 (Phase B Approval) and Stage 6 (Listen-Through) require Kim's explicit approval recorded in `prod_approvals` before the module can advance.

**Dashboard tracking:** Directus REST API with JWT auth (15-min TTL), hosted on Railway. Two-field status system: `current_stage` (text FK) + `stage_status` (PostgreSQL enum: `not_started`, `in_progress`, `blocked`, `completed`). Sub-status fields: `audio_status` and `visual_status` for granular Stage 5 tracking.

**Authority:** MODULE_PRODUCTION_MASTER_PLAN_v2_1.md

---

# PART 1: VERIFIED SKILL INVENTORY

Each skill below has been evaluated by 3 independent agents, cross-compared to filter false positives, corrected where needed, and validated by 3 independent validation agents. All corrections are documented in `SKILL_CORRECTION_MASTER_PLAN_v1.md` and `SKILL_CORRECTION_DIFF_REPORT_April11.md`.

---

## SKILL 1: dashboard-ops

**Location:** `.claude/skills/dashboard-ops/SKILL.md`
**Pipeline Position:** Cross-cutting — serves ALL stages as the central API interface to Directus
**Last Corrected:** April 11, 2026 (76 lines changed — D1-D4)

### What It Does

Operates Kim's entire production dashboard via Directus REST API from the terminal sandbox. No browser automation, no screenshots, no manual clicking. Authenticates with Directus, reads and writes production data, manages pipeline stages, and handles infrastructure operations — all programmatically.

This is the "conductor" skill. Every other production skill should call dashboard-ops patterns at their completion points to update the board.

### Inputs

- Directus API credentials (read from `Production/API_KEYS_MASTER.md` at runtime — never hardcoded)
- Module identifiers (M-number or database record ID)
- Stage transition data (new stage, new status, reason)

### Outputs

- CRUD operations on all 20 `prod_*` collections
- Hard gate verification (checks `prod_approvals` before allowing advance past `phase_b` or `listen_through`)
- Activity logging to `prod_activity_log`
- Pipeline status summaries

### Key Configuration

- **Base URL:** `https://directus-production-3460.up.railway.app`
- **Auth:** Email/password → JWT (15-min TTL). Re-authenticate before each batch.
- **Database:** Supabase PostgreSQL at `db.ugjpauwozlruyctrygby.supabase.co`
- **Hosting:** Railway project `efficient-grace`

### Database Schema (Key Fields)

| Field | Type | Allowed Values |
|-------|------|----------------|
| `current_stage` | text (FK) | `intake`, `kim_seeds`, `phase_b`, `phase_a_json`, `audio`, `listen_through` |
| `stage_status` | PostgreSQL enum | `not_started`, `in_progress`, `blocked`, `completed` |
| `audio_status` | text | `not_started`, `voice_stem`, `cue_mapped`, `mix_complete`, `approved` |
| `visual_status` | text | `not_started`, `stills_done`, `animated`, `lip_synced`, `composited` |

### Dashboard Integration Status: FULLY FUNCTIONAL

Dashboard-ops IS the dashboard integration layer. It provides:
- Hard gate verification with executable curl patterns (added April 11)
- Cross-skill handoffs table documenting when each skill updates the dashboard (added April 11)
- Module CRUD (read, create, update)
- Blocker management
- Approval recording
- Activity logging

### April 11 Corrections Applied

- **D1:** Added hard gate verification curl pattern with enforcement rule and 4-step sequence
- **D2:** Added `audio_status` and `visual_status` fields to schema reference
- **D3:** Added POST operation for creating new module records
- **D4:** Added cross-skill handoffs table (7 rows: phase-b-writer, audio-producer ×2, video-producer ×3, phase-a-designer)

---

## SKILL 2: phase-b-writer

**Location:** `.claude/skills/phase-b-writer/SKILL.md`
**Pipeline Position:** Stage 3 — Phase B Draft + Approval
**Last Corrected:** April 11, 2026 (13 lines changed — PB1-PB2)

### What It Does

Writes Phase B meditation scripts using a 9-step clinical extraction process. Takes Kim's Seed Card + the module's technique from the Unified Technique Inventory → produces a complete Phase B script with 7 standard sections, embedded cue markers, and audio production metadata.

### The 9-Step Process

1. Clinical technique extraction from Technique Inventory
2. Language audit (remove therapy-speak, translate to child-accessible language)
3. 7-section template assembly (Opening, Grounding, Instruction, Deepening, Integration, Landing, Exit)
4. Breathing pattern design (for breathing modules)
5. Body test (is every instruction physically doable by a sitting/lying child?)
6. Creature integration (creature's role in the narrative wrapper)
7. Kim review draft
8. Revision cycle
9. Audio cue marker embedding ({{INHALE_CUE}}, {{EXHALE_CUE}}, {{BELL_CUE}}, {{NOTICING_CUE}}, {{PAUSE:Xs}})

### Inputs

- Kim's Seed Card (2-3 sentences of therapeutic direction)
- Intake Brief from Stage 1
- Unified Technique Inventory entry for this module's technique
- Base module (for Evolutions)
- Arc skeleton (narrative context)
- Module Authoring Guide (structural rules)

### Outputs

- Complete Phase B script with 7 sections
- Embedded `{{CUE_MARKERS}}` for audio production handoff
- `audioProductionType` field: one of `breathing`, `observation`, `compassion`, `tension_arc`, `containment`, `body_awareness` (added April 11)
- Myrrhin Voice ID reference: `oR4uRy4fHDUGGISL0Rev` (ElevenLabs, eleven_v3, 0.30/0.80/0.30) (added April 11)

### Key Rules

- Source Fidelity Protocol applies (Kim's therapeutic direction preserved verbatim)
- Phase B before Phase A — always
- The Seed Card's therapeutic direction overrides Claude's research instincts
- No therapy-speak; child is active participant, never passive listener
- Every exercise physically doable by a sitting/lying child

### Dashboard Integration Status: PARTIAL — NEEDS HANDOFF ADDITION

Phase-b-writer does NOT currently:
- Update `stage_status` on the dashboard when a draft is complete
- Record Kim's approval in `prod_approvals` after review
- Advance the module to Stage 4 after approval

The dashboard-ops cross-skill handoffs table DEFINES what phase-b-writer should do, but phase-b-writer's own SKILL.md does not contain the curl patterns to execute those updates.

### April 11 Corrections Applied

- **PB1:** Added `audioProductionType` output field (tells audio-producer which cue pattern and ffmpeg recipe to apply)
- **PB2:** Added Myrrhin voice ID reference with locked settings

---

## SKILL 3: phase-a-designer

**Location:** `.claude/skills/phase-a-designer/SKILL.md`
**Pipeline Position:** Stage 4a — Phase A Beat Sheet Design
**Last Corrected:** April 11, 2026 (25 lines changed — P1-P3)

### What It Does

Designs the Phase A interactive demonstration — the creature models the technique for the child. Produces a beat sheet (numbered cues with visual/audio specifications), NOT code and NOT JSON. Phase A shows WHAT the child will do (ingredients + outcome), not HOW (that's Phase B's job).

### Inputs

- Approved Phase B script (Phase B defines what Phase A must demonstrate)
- Arc skeleton (creature context, narrative setup)
- Module Authoring Guide §4.1-4.12
- M4 Phase A Beat Sheet v1 (canonical reference implementation)

### Outputs

- Numbered beat sheet (3-6 cues, matching approved module complexity)
- Metaphor map
- Timeout fallback behavior
- Visual asset requirements
- Guide Bird narration lines per beat

### Key Rules

- Two absolute rules: (1) Guide Bird ALWAYS narrates, (2) the child's character performs the action
- One demo cycle only — no repetition (that's Phase B thinking)
- No sensation vocabulary ("tingling," "warmth," "calm") — those belong to Phase B
- Phase A vocabulary must match Buy-In vocabulary
- Runtime duration under 30 seconds

### Stage 4a/4b Split (Clarified April 11)

- **Stage 4a (this skill):** Beat sheet design → Kim approval gate
- **Stage 4b (separate step):** JSON assembly from approved beat sheet → schema validation → integration

The old prohibition "DO NOT produce: phaseAFlow JSON" was removed and replaced with this split clarification. JSON build follows beat sheet approval as a separate sub-step.

### Dashboard Integration Status: PARTIAL — NEEDS HANDOFF ADDITION

Phase-a-designer does NOT currently:
- Update `stage_status` when beat sheet is complete
- Advance the module within Stage 4 after Kim approves

The dashboard-ops cross-skill handoffs table says phase-a-designer should "Advance to `phase_a_json` stage" after beat sheet approval, but the skill itself has no curl patterns.

### April 11 Corrections Applied

- **P1:** Removed JSON prohibition; clarified Stage 4a/4b split
- **P2:** Added JSON Build Handoff (Stage 4b) section
- **P3:** Cue count guidance widened from "4-6" to "3-6 cues (match approved module complexity)"

---

## SKILL 4: elevenlabs-tts

**Location:** `.claude/skills/elevenlabs-tts/SKILL.md`
**Pipeline Position:** Sub-skill — serves Stage 3 (Phase B voice rendering), Stage 5 (all character dialogue)
**Last Corrected:** April 11, 2026 (67 lines changed — E1-E5)

### What It Does

Generates TTS audio via ElevenLabs API. Handles emotional direction tagging, pronunciation rules, personalization variable splitting, voice stem assembly, quota tracking, and error handling.

### Inputs

- Finalized dialogue text (from skeleton or approved Phase B script)
- Voice ID (from VOICE_ROSTER_LOCKED_v2)
- Emotional direction tags (derived from skeleton stage directions)

### Outputs

- Individual MP3 line files
- Concatenated voice stem (`m{N}_voice_stem.mp3`) via ffmpeg concat
- Quota usage report

### Key Configuration (LOCKED — April 6, 2026)

| Parameter | Value | Authority |
|-----------|-------|-----------|
| Model | `eleven_v3` | VOICE_ROSTER_LOCKED_v2 |
| Stability | 0.30 | VOICE_ROSTER_LOCKED_v2 |
| Similarity Boost | 0.80 | VOICE_ROSTER_LOCKED_v2 |
| Style | 0.30 | VOICE_ROSTER_LOCKED_v2 |
| Plan | Creator ($22/mo) | Current subscription |

**Exceptions:** Oliver stability 0.35; Bork stability 0.20, style 0.40.

**Key Voice IDs:**
- Myrrhin: `oR4uRy4fHDUGGISL0Rev` (ALL Phase B narration)
- Guide Bird (Chipper1): `7o9pyvsN0ob5GO6LBQp6`

### Key Rules

- "MindfulNest" ALWAYS hyphenated as "Mindful-Nest" in TTS scripts
- Emotional direction tags on EVERY line
- Personalization: sentences with variables rendered per-child; sentences without rendered once (universal)
- Source Fidelity Protocol — Kim's dialogue VERBATIM, only emotional direction tags added
- Sequential batch generation with 1s delay (no parallelization — rate limits)

### Dashboard Integration Status: NOT APPLICABLE

elevenlabs-tts is a sub-skill called by audio-producer and video-producer. It does not directly update the dashboard — the calling skill handles status updates.

### April 11 Corrections Applied

- **E1:** Added Creator Plan quota tracking section (curl to check usage, per-module estimates, 80% warning threshold)
- **E2:** Added error handling and retry logic (429 backoff, 500 retry, malformed response handling, quota exceeded stop)
- **E3:** Added voice stem assembly section (ffmpeg concat of individual lines)
- **E4:** Added personalization variable sentence splitting section
- **E5:** Model ID confirmed as eleven_v3 (was already correct)

---

## SKILL 5: audio-producer

**Location:** `.claude/skills/audio-producer/SKILL.md`
**Pipeline Position:** Stage 5 — Audio Production
**Last Corrected:** April 11, 2026 (19 lines changed — A1-A5)

### What It Does

Produces the Phase B meditation audio for a single module — from approved script to finished flat MP3. Orchestrates the full 5-step pipeline: voice stem generation → Vosk STT cue extraction → breathCycle rhythm assignment → sound layering → ffmpeg mixing.

**This is the gold standard for dashboard integration.** audio-producer is the only skill that currently implements full dashboard handoffs within its own workflow.

### The 5-Step Pipeline

1. **Generate Voice Stem** — ElevenLabs TTS (Myrrhin, eleven_v3, 0.30/0.80/0.30) → Kim approves pacing
2. **Extract Cue Points** — Vosk STT word-level timestamps → match to script `{{CUE_MARKERS}}` → JSON cue-point map
3. **Assign breathCycle Rhythms** — For breathing modules: Instruction rhythm (4s-2s-5s=11s), Deepening rhythm (3s-1s-4s=8s). For non-breathing modules: spacer silence + noticing tones
4. **Layer Sound Elements** — Three-layer architecture: Voice (-12 dB) + Ambient bed (-36 dB) + Functional SFX (-18 to -24 dB)
5. **Mix to Flat MP3** — ffmpeg, 192kbps, output to `Production/Event_{N}/m{N}_phase_b_complete_mix.mp3`

### Inputs

- Approved Phase B script with embedded `{{CUE_MARKERS}}`
- ElevenLabs API key (from API_KEYS_MASTER.md)
- Asset library: 57 production-ready MP3s (11 ambient beds, 12 breathing cues, 3 bells, 8 instrument loops, 8 SFX)
- `audioProductionType` from phase-b-writer (determines cue pattern and mixing recipe)

### Outputs

- `m{N}_phase_b_complete_mix.mp3` — finished Phase B audio
- Cue-point JSON map (Vosk timestamps)
- Dashboard updates: `audio_status` progression + stage advancement

### Key Configuration

- **Myrrhin Voice ID:** `oR4uRy4fHDUGGISL0Rev`
- **Model:** eleven_v3
- **Settings:** stability 0.30, similarity_boost 0.80, style 0.30
- **Cost per module:** ~$0.70-1.80 (dominated by TTS iteration — budgeting 3-6 pacing variants)

### Dashboard Integration Status: FULLY INTEGRATED

audio-producer is the model for how all skills should integrate:
- Updates `audio_status` progressively (`voice_stem` → `cue_mapped` → `mix_complete`)
- Advances `current_stage` to `listen_through` when mix is complete
- Logs all actions to `prod_activity_log`
- Respects the Kim gate at listen-through (does NOT mark audio as approved — waits for Kim)

### Key Lessons Learned (From M1-M3 Production)

- Voice stem is timing master — never finalize timestamps from estimates
- Vosk STT prevents 8-second drift (discovered during M2 production)
- No punctuation between count numbers in breathing scripts
- 0.08 gain for ambient bed (not 0.1, not 0.05)
- 2 breathing cycles standard (not 3 — too long for ages 7-11)
- Bell at 0.5s (not 0.0s — prevents audio pop)
- M1/M2 narration stems may be pre-comet — verify before reuse

### April 11 Corrections Applied

- **A1-A2:** Voice table updated from 0.5/0.75 to 0.30/0.80/0.30 per VOICE_ROSTER_LOCKED_v2
- **A3:** Model ID updated from eleven_multilingual_v2 to eleven_v3
- **A4:** Curl example voice settings aligned to v2 standard
- **A5:** Added model/settings rationale note (Creative mode for emotional direction tags)
- **Post-validation fix:** "M3 (Thought Clouds)" corrected to "M3 (Breath-Squeezers Spell)" in Lessons Learned

---

## SKILL 6: scene-to-production

**Location:** `.claude/skills/scene-to-production/SKILL.md`
**Pipeline Position:** Feeds into video-producer Step 1 (Shot Breakdown)
**Last Corrected:** April 11, 2026 (45 lines changed — S1-S5)

### What It Does

Converts skeleton scene text into production-ready shot breakdowns — numbered shots with FLUX Kontext prompts, Seedance motion prompts, TTS dialogue lists, and lip-sync flags. This is the FIRST step of the video production pipeline, not a standalone stage.

### Inputs

- Arc skeleton event text (dialogue, stage directions, production notes)
- Character reference images from `Production/` subfolders
- Production Bible resolution rules
- Module Authoring Guide §2-3 (Call/Buy-In) and §6 (Resolution)

### Outputs

1. Shot Breakdown Document (numbered shots with all technical specs)
2. FLUX Kontext Prompts (one per shot — hero images)
3. Seedance Motion Prompts (one per shot — animation/motion)
4. TTS Dialogue List (all lines with voice IDs, emotional tags, pronunciation notes)
5. Lip-Sync Flag List (shots requiring ByteDance processing)
6. Continuity Notes (what must match between adjacent shots)

### Key Rules

- Source Fidelity Protocol — skeleton dialogue is VERBATIM
- The skeleton IS the screenplay — decompose, don't generate
- Screen direction is binding ("camera pans left" = left pan, period)
- Style: **Pixar 3D** (NOT painterly — updated April 11)
- Image gen: **FLUX Kontext** via BFL API (NOT Midjourney — updated April 11)

### Multi-Character Scene Decomposition (Added April 11)

For party scenes with 3+ characters in rapid dialogue:
1. One speaker per shot — never two characters speaking simultaneously
2. Reaction shots are separate
3. Establish → Isolate → Reestablish pattern
4. Lip-sync flagging: speaking shots = `lip_sync: true`; silent reaction = `lip_sync: false`
5. Max 4 speakers per scene; extras as background presence in establishing shots

### Dashboard Integration Status: NOT APPLICABLE

scene-to-production is a sub-skill consumed by video-producer. It does not directly update the dashboard.

### April 11 Corrections Applied

- **S1:** All "Midjourney" references → "FLUX Kontext" (April 10 pipeline pivot)
- **S2:** "painterly" style → "Pixar 3D" (April 10 style lock)
- **S3:** ARC_PRODUCTION_BIBLE version reference v2_9 → v2_10
- **S4:** Added multi-character scene decomposition section (5 rules)
- **S5:** Added pipeline position clarification (feeds video-producer Step 1)

---

## SKILL 7: video-producer

**Location:** `.claude/skills/video-producer/SKILL.md`
**Pipeline Position:** Stage 5 (parallel with audio-producer) — Video Production
**Last Corrected:** April 11, 2026 (47 lines changed — V1-V4)

### What It Does

Orchestrates the complete video production of a MindfulNest module event — from skeleton to delivered video files. Consolidates scene-to-production, phase-a-designer, and phase-b-writer workflows into a single 9-step pipeline covering all 7 segments (Story Scene, Buy-In, Phase A, Phase B, Resolution, Win, Map Return).

### The 9-Step Pipeline

0. **Gate 0:** Pre-production readiness check
1. **Read & Decompose Skeleton** — Extract dialogue, stage directions, camera instructions
2. **TTS Voice Setup** — Verify voice profiles from VOICE_ROSTER_LOCKED_v2
3. **Generate All TTS Audio** — Batch render dialogue with emotional direction tags
4. **Generate Key Stills** — FLUX Kontext Max via BFL API ($0.08/image)
5. **Animate Clips** — Seedance 1.5 Pro / Kling 3.0 / Pika Pikaframes
6. **Lip Sync** — ByteDance Lip Sync API (~$0.15/5s clip)
7. **Phase B Audio** — Delegates to audio-producer skill
8. **Assembly** — ffmpeg concatenation, crossfades, audio overlay → final MP4/MP3
9. **Kim Final Review** — Watch/listen through everything

### Inputs

- Arc skeleton (the screenplay)
- Character reference images (382+ in Production/ subfolders)
- Approved Phase A design brief
- Approved Phase B script (with cue markers)
- VOICE_ROSTER_LOCKED_v2 (voice IDs and settings)

### Outputs

- `M[N]_[CREATURE]_[SEGMENT].mp4` for each video segment (1080p)
- `M[N]_PHASE_B_FINAL_MIX.mp3` for Phase B audio
- All files to `Production/Event_[N]/`

### Key Configuration

| Component | Tool | Cost |
|-----------|------|------|
| Still generation | FLUX Kontext Max via BFL API (api.bfl.ai) | $0.08/image |
| Animation | Seedance 1.5 Pro via WaveSpeed API | ~$0.05/sec |
| Lip sync | ByteDance LatentSync via WaveSpeed API | ~$0.15/5s clip |
| TTS | ElevenLabs (eleven_v3) | Included in $22/mo Creator plan |
| Mixing | ffmpeg (local) | Free |
| **Total per event** | | **~$4-7** |

**Style:** Pixar 3D — luminous, warm, cinematic lighting, soft materials (locked April 10, 2026)

### Key Rules

- Source Fidelity Protocol — Kim's dialogue VERBATIM
- The skeleton IS the screenplay — decompose, don't generate
- Screen direction is binding
- Three Questions Gate before Phase A/B work
- One module per session
- Event 0 (Opening Storybook) is pre-produced — do NOT run this pipeline on it
- No Midjourney — FLUX Kontext only
- Resolution stills use first-person camera (child IS the camera)
- Tool consistency within segments (don't mix Seedance and Kling in same segment)

### Dashboard Integration Status: PARTIAL — NEEDS VISUAL_STATUS UPDATES

video-producer does NOT currently:
- Update `visual_status` progressively (`stills_done` → `animated` → `lip_synced` → `composited`)
- Log visual production milestones to `prod_activity_log`

The dashboard-ops cross-skill handoffs table defines 3 visual_status updates that video-producer should make, but video-producer's SKILL.md does not contain the curl patterns.

Note: Phase B audio dashboard updates ARE handled correctly because video-producer delegates to audio-producer (which is fully integrated).

### April 11 Corrections Applied

- **V1:** "Seedance 2.0" → "Seedance 1.5 Pro" (5 instances in active text)
- **V2:** "FLUX Kontext via Replicate" → "via BFL API (api.bfl.ai)" (3 instances)
- **V3:** Inline Phase B audio section replaced with pointer to audio-producer skill
- **V4:** audio-producer added to Sub-Skill References table

---

## CROSS-SKILL INTEGRATION MAP

This table shows how skills connect. Green = working. Yellow = defined but not implemented. Red = missing.

| Source Skill | Trigger | Dashboard Action | Status |
|-------------|---------|-----------------|--------|
| audio-producer | Voice stem generated | `audio_status = 'voice_stem'` | WORKING |
| audio-producer | Mix complete | `audio_status = 'mix_complete'`, advance to `listen_through` | WORKING |
| phase-b-writer | Script draft complete | `stage_status = 'completed'` on `phase_b` | DEFINED, NOT IMPLEMENTED |
| phase-b-writer | Kim approves | Record in `prod_approvals` | DEFINED, NOT IMPLEMENTED |
| phase-a-designer | Beat sheet approved | Advance to `phase_a_json` stage | DEFINED, NOT IMPLEMENTED |
| video-producer | Stills generated | `visual_status = 'stills_done'` | DEFINED, NOT IMPLEMENTED |
| video-producer | Animation complete | `visual_status = 'animated'` | DEFINED, NOT IMPLEMENTED |
| video-producer | Lip sync complete | `visual_status = 'lip_synced'` | DEFINED, NOT IMPLEMENTED |

**Summary:** 2 of 8 cross-skill handoffs are working. The remaining 6 are defined in dashboard-ops's cross-skill handoffs table but not yet implemented in the source skills.

---

## AUTOMATION READINESS SUMMARY

| Pipeline Stage | Skill(s) | Automation Level | Blocker |
|---------------|----------|-----------------|---------|
| Stage 1: Intake | (no skill yet) | NOT AUTOMATED | Intake briefer skill needed |
| Stage 2: Kim Seeds | Kim (manual) | N/A — human stage | None |
| Stage 3: Phase B | phase-b-writer | ~80% — drafting works, dashboard handoff missing | Gap 1 |
| Stage 4a: Phase A Design | phase-a-designer | ~80% — design works, dashboard handoff missing | Gap 1 |
| Stage 4b: JSON Build | (no skill yet) | NOT AUTOMATED | Module JSON builder needed (Gap 3) |
| Stage 5: Audio | audio-producer + elevenlabs-tts | ~95% — FULLY INTEGRATED | Minor: verify real production run |
| Stage 5: Video | video-producer + scene-to-production | ~70% — works but no visual_status dashboard updates | Gap 1 |
| Stage 6: Listen-Through | Kim (manual) + dashboard-ops | ~90% — gate verification works | Gate-manager pattern would help (Gap 2) |

**Overall pipeline automation: ~60%**

---

# PART 2: WHAT STILL NEEDS TO BE BUILT

Five gaps stand between the current state and full end-to-end automation. They are listed in priority order (highest-leverage first).

---

## GAP 1: Dashboard Handoff Additions (PRIORITY 1)

**Effort:** ~2-3 hours
**Impact:** Connects all existing skills to the board — highest leverage fix
**Skills Affected:** phase-b-writer, phase-a-designer, video-producer

### The Problem

Dashboard-ops has a "Cross-Skill Handoffs" table that defines exactly when each skill should update the dashboard. But the skills themselves don't contain the curl patterns to execute those updates. audio-producer is the only skill that actually does its own dashboard updates. The other three content-producing skills finish their work and... stop. No board update.

### What to Build

For each of the three skills, add a "Post-Completion: Dashboard Update" section containing explicit dashboard-ops curl patterns. The section should be placed at the END of each skill (after the main workflow), following audio-producer's pattern.

#### phase-b-writer — Add After Step 9

```
## Post-Completion: Dashboard Update

After completing a Phase B draft:
1. Read API_KEYS_MASTER.md for Directus credentials
2. Authenticate with Directus
3. PATCH prod_modules: set stage_status = 'completed' on phase_b stage
4. POST to prod_activity_log: "Phase B draft complete for M{N}"

After Kim approves:
5. POST to prod_approvals: module_id, gate_type='phase_b', status='approved', approved_by='kim'
6. Verify approval exists (hard gate check)
7. PATCH prod_modules: advance current_stage to 'phase_a_json', stage_status = 'not_started'
8. POST to prod_activity_log: "M{N} Phase B approved — advancing to Phase A + JSON"
```

Include the actual curl commands (matching dashboard-ops patterns), not just descriptions.

#### phase-a-designer — Add After Checklist Verification

```
## Post-Completion: Dashboard Update

After completing a Phase A beat sheet:
1. Authenticate with Directus
2. PATCH prod_modules: set stage_status = 'in_progress' on phase_a_json stage
3. POST to prod_activity_log: "Phase A beat sheet complete for M{N}"

After Kim approves the beat sheet and JSON is built (Stage 4b):
4. PATCH prod_modules: set stage_status = 'completed' on phase_a_json
5. PATCH prod_modules: advance current_stage to 'audio', stage_status = 'not_started'
6. POST to prod_activity_log: "M{N} Phase A + JSON complete — advancing to Audio"
```

#### video-producer — Add visual_status Updates Throughout

Add curl patterns at each visual production milestone within Steps 4-6:

```
After Step 4 (Stills generated):
  PATCH prod_modules: visual_status = 'stills_done'
  POST prod_activity_log: "M{N} stills generated — {count} images"

After Step 5 (Animation complete):
  PATCH prod_modules: visual_status = 'animated'
  POST prod_activity_log: "M{N} animation complete — {count} clips"

After Step 6 (Lip sync complete):
  PATCH prod_modules: visual_status = 'lip_synced'
  POST prod_activity_log: "M{N} lip sync complete"

After Step 8 (Assembly complete):
  PATCH prod_modules: visual_status = 'composited'
  POST prod_activity_log: "M{N} video assembly complete"
```

### Acceptance Criteria

- Each skill contains executable curl patterns (not just descriptions)
- Patterns match dashboard-ops authentication and API format exactly
- `prod_activity_log` entries are generated for every state change
- Hard gate check (GET `prod_approvals`) is included before any gate advancement
- Verified by independent validation agent reading the edited skills cold

---

## GAP 2: Gate-Manager Pattern (PRIORITY 2)

**Effort:** ~1 hour
**Impact:** Standardizes the most error-prone operation in the pipeline

### The Problem

Hard gate advancement (Phase B approval and Listen-Through) is a multi-step sequence:
1. Kim says "approved" in conversation
2. POST to `prod_approvals`
3. Verify approval exists with GET
4. PATCH module to advance to next stage
5. Log the transition

This sequence is documented in dashboard-ops but exists only as scattered examples. No reusable pattern exists that all skills can call.

### What to Build

**Option A: Document the Pattern in dashboard-ops**

Add a "## Gate Advancement Procedure" section to dashboard-ops that provides a single, copy-pasteable bash function or script block that handles the full sequence. Other skills reference this section.

**Option B: Standalone gate-manager Skill**

Create a minimal skill that accepts: `module_id`, `gate_type` (phase_b or listen_through), `approved_by` (kim). Executes the full sequence and returns success/failure.

**Recommendation:** Option A is simpler and avoids adding another skill. The pattern is small enough to live in dashboard-ops.

### Pattern Specification

```bash
# Gate Advancement Function
# Inputs: MODULE_ID, GATE_TYPE (phase_b|listen_through), NEXT_STAGE
# Prerequisite: Kim has explicitly said "approved" in conversation

# Step 1: Authenticate
TOKEN=$(curl -s -X POST $BASE/auth/login ...)

# Step 2: Record approval
curl -s -X POST "$BASE/items/prod_approvals" \
  -d '{"module_id": MODULE_ID, "gate_type": "GATE_TYPE", "status": "approved", "approved_by": "kim"}'

# Step 3: Verify approval exists
APPROVAL=$(curl -s "$BASE/items/prod_approvals?filter[module_id][_eq]=MODULE_ID&filter[gate_type][_eq]=GATE_TYPE&filter[status][_eq]=approved" ...)

# Step 4: If verified, advance module
curl -s -X PATCH "$BASE/items/prod_modules/MODULE_ID" \
  -d '{"current_stage": "NEXT_STAGE", "stage_status": "not_started"}'

# Step 5: Log
curl -s -X POST "$BASE/items/prod_activity_log" \
  -d '{"module_id": MODULE_ID, "action": "Advanced past GATE_TYPE gate", "performed_by": "claude"}'
```

### Acceptance Criteria

- One documented, reusable pattern that handles the full gate advancement sequence
- Includes pre-check (verify Kim has approved), POST, GET verification, PATCH, and LOG
- Referenced by phase-b-writer and audio-producer (listen-through handoff)
- Fails safely: if verification fails, STOP and report to Kim (never advance without verified approval)

---

## GAP 3: Module JSON Builder Skill (PRIORITY 3)

**Effort:** ~4-5 hours
**Impact:** Automates Stage 4b — the missing link between Phase A design and audio production

### The Problem

Stage 4 of the pipeline is "Phase A + JSON Build." phase-a-designer handles 4a (beat sheet design). But there is NO skill for 4b: converting the approved beat sheet + Phase B script into the final `phaseAFlow` JSON structure that the app runtime consumes.

Currently, this step would need to be done manually or ad-hoc. It's the biggest missing piece in the pipeline.

### What to Build

A new skill: `module-json-builder`

**Inputs:**
- Approved Phase A beat sheet (from phase-a-designer)
- Approved Phase B script (from phase-b-writer)
- Arc skeleton (narrative context, module placement)
- CANONICAL_DATA_MODEL_v1_12.md (Firestore schema — defines all field names and types)
- MODULE_JSON_SCHEMA_GUARDRAILS (Q1-Q19 checklist)

**Processing:**
1. Read the approved beat sheet and extract: cue sequence, visual asset list, Guide Bird narration lines, creature actions, timeout fallbacks
2. Read the approved Phase B script and extract: section structure, cue markers, audioProductionType, breathing patterns
3. Map both to the CDM v1.12 field structure
4. Assemble complete module JSON including: moduleId, arcId, creatureName, spellName, domain, stoneColor, phaseAFlow, phaseBConfig, winConfig, mapReturnConfig
5. Run Q1-Q19 guardrail checklist:
   - Q1: Module ID matches skeleton?
   - Q2: Technique name canonical (matches Spell Name Registry)?
   - Q3: Phase A demonstrates what Phase B practices?
   - Q4: Creature role consistent with skeleton?
   - Q5-Q19: Full checklist per schema guardrails
6. Output: validated `.json` file + guardrail report

**Outputs:**
- `module_M{N}_config.json` — complete module configuration
- Guardrail validation report (PASS/FAIL per check, with details)
- Dashboard update: PATCH `stage_status = 'completed'` on `phase_a_json`

**Key Rules:**
- Source Fidelity Protocol applies to any dialogue in the JSON
- JSON field names MUST match CDM v1.12 exactly (no aliases, no camelCase drift)
- All personalization variables (`{childName}`, etc.) must be preserved as-is in JSON strings
- If any Q1-Q19 check fails, flag for Kim review — do not auto-fix

### Schema Reference

The JSON structure must conform to `CANONICAL_DATA_MODEL_v1_12.md`. Key top-level fields:

```json
{
  "moduleId": "m1",
  "arcId": "arc1",
  "creatureName": "Tessa",
  "spellName": "Magic Hands Spell",
  "domain": "body_sensing",
  "stoneColor": "orange",
  "phaseAFlow": { /* beat sheet → interactive cues */ },
  "phaseBConfig": { /* audio file refs, breathing params */ },
  "winConfig": { /* coins, spell, decoration */ },
  "mapReturnConfig": { /* trigger sprite, map sprites, state changes */ }
}
```

### Acceptance Criteria

- Produces valid JSON that matches CDM v1.12 field structure
- All 19 guardrail checks execute and report results
- Source Fidelity Protocol verified (dialogue text in JSON matches approved scripts)
- Dashboard update on completion
- Tested against at least 1 real module (M1 or M4, which have approved Phase A beat sheets)

---

## GAP 4: Intake Briefer Skill (PRIORITY 4)

**Effort:** ~2-3 hours
**Impact:** Automates Stage 1 — enables batch intake of entire arcs

### The Problem

Stage 1 (Intake) is described in MODULE_PRODUCTION_MASTER_PLAN_v2_1 but has no dedicated skill. Claude currently does intake ad-hoc by reading the skeleton and technique inventory manually. A dedicated skill would standardize the output format and automatically create the dashboard record.

### What to Build

A new skill: `intake-briefer`

**Inputs:**
- Arc skeleton (identifies all modules, creatures, narrative context)
- UNIFIED_TECHNIQUE_INVENTORY_v1_14.md (technique definitions, clinical basis)
- Base module (for Evolution modules — the module this one evolves from)
- Arc Production Bible (module format, structural rules)

**Processing:**
1. Read the arc skeleton and identify all modules in the arc
2. For each module, extract: M-number, creature, spell name, domain, stone, narrative context
3. Cross-reference with Technique Inventory for clinical basis
4. For Evolutions: identify the base module and what THIS module adds
5. Produce a structured Intake Brief per module
6. Create initial `prod_modules` record in Directus for each module

**Output per Module — Intake Brief:**
```
MODULE: M{N}
ARC: {arc_number}
CREATURE: {creature_name}
SPELL: {spell_name}
DOMAIN: {domain}
TECHNIQUE: {clinical_technique_name}
TYPE: New Spell | Evolution of M{base}

NARRATIVE CONTEXT:
[2-3 sentences from skeleton describing this module's narrative role]

CLINICAL BASIS:
[1-2 sentences from Technique Inventory]

FOR EVOLUTIONS:
Base Module: M{base} ({spell_name})
What This Module Adds: [delta description]

PROPOSED PHASE B APPROACH:
[Claude's initial read — Kim overrides in Seed Card]

FLAGS:
[Technique overlap, prerequisite gaps, complexity flags]
```

**Dashboard Action:**
- POST to `prod_modules`: create new record with `current_stage = 'intake'`, `stage_status = 'completed'`
- POST to `prod_activity_log`: "Intake brief created for M{N}"
- Advance to `kim_seeds` stage automatically (no hard gate at intake)

### Batch Mode

The skill should support batch intake: process ALL modules in one arc in a single run. Output: one Intake Brief per module, all dashboard records created.

### Acceptance Criteria

- Produces standardized Intake Briefs matching the format above
- Creates dashboard records for all modules in the arc
- Cross-references Technique Inventory correctly
- Identifies Evolutions and their base modules
- Flags potential issues (technique overlap, missing prerequisites)

---

## GAP 5: Priority 4 Reframe — Three Separate Deliverables

**Effort:** ~4-6 hours total (separate initiative from Gaps 1-4)
**Impact:** Completes the Haiku narrative generation pipeline (Stage 4 aiNarrativeCache)

### Context

Priority 4 was originally scoped as "codify the Guide Bird AI System Prompt." The triple-blind evaluation revealed that the Guide Bird System Prompt v1.4 already exists and is comprehensive — it covers all 6 aiNarrativeCache fields, voice rules, creature profiles, and validation checklists. The real remaining work is three separate deliverables.

### Deliverable A: Module Context Registry

**What:** A structured lookup mapping all 54 modules to their context variables.

**Fields per module:**
- arcName, arcPremise
- moduleDomain, moduleCreature, moduleSpellName
- eventType (full Call, transitional Call, evolution)
- barPosition (1-6 within arc)
- moduleIsEvolution (boolean)
- bridgeDialogue conditions (what triggers bridge dialogue vs. null)
- Base module reference (for evolutions)

**Sources:** Arc skeletons + CDM v1.12 + Technique Inventory + Arc Production Bible

**Output:** JSON or markdown registry file. The Haiku API reads this at runtime to populate the system prompt's module-specific section.

**Why it matters:** Without this registry, someone has to manually look up every module's context variables before each Haiku generation call. The registry makes it automated.

### Deliverable B: Creature Vocabulary Appendix

**What:** A reference table of creature-specific physical vocabulary extracted from ArcBuilder and arc skeletons.

**Per creature:**
- Species and physical description
- Movement vocabulary (how they walk, gesture, express emotion)
- Emotional expression vocabulary (how they show fear, joy, curiosity)
- Sound vocabulary (vocalizations, characteristic sounds)
- Key visual identifiers (for prompt generation consistency)

**Sources:** ArcBuilder v2_3, arc skeletons, skeleton creature description sections

**Output:** Appendix document that can be appended to Guide Bird System Prompt v1.5 (or maintained as a separate reference). Enables Haiku to generate creature-appropriate vocabulary without hallucinating physical capabilities.

### Deliverable C: Stage 4 Operator Runbook

**What:** A production skill or script that automates the Haiku narrative generation pipeline.

**Pipeline:**
1. Read module context from Module Context Registry (Deliverable A)
2. Populate Guide Bird System Prompt v1.4 with module-specific context
3. Call Claude Haiku API with populated prompt
4. Validate output against field-level rules:
   - Sentence count checks per field
   - Forbidden term regex (no therapy-speak, no clinical language)
   - JSON schema validation
   - tomorrowHook is NOT Haiku-generated (it's pre-authored — verify it wasn't overwritten)
5. Cache validated output to Firestore (`aiNarrativeCache` collection)
6. Update Directus dashboard

**API Configuration:**
- Model: `claude-3-5-haiku` (or current Haiku model)
- Temperature: TBD (recommend 0.7 for creative variation)
- Max tokens: TBD per field
- Retry logic: max 3 attempts per field, with validation between retries

**Test Matrix:**
- Minimum 3-5 modules covering: full Call, transitional Call, evolution, bridge null, bridge active
- Validate that each generated field meets its specific constraints

### Acceptance Criteria

- Module Context Registry covers all 54 modules with correct data
- Creature Vocabulary Appendix covers all 6 Arc 1 creatures with physically accurate vocabulary
- Operator Runbook produces valid aiNarrativeCache entries that pass all validation checks
- End-to-end test: runbook reads registry → calls Haiku → validates → caches (at least 3 modules)

---

## IMPLEMENTATION PRIORITY ORDER

| Priority | Gap | Effort | Impact |
|----------|-----|--------|--------|
| 1 | Dashboard handoff additions (3 skills) | ~2-3 hrs | Connects all existing skills to the board |
| 2 | Gate-manager pattern | ~1 hr | Standardizes hard gate advancement |
| 3 | Module JSON builder skill | ~4-5 hrs | Fills the Stage 4b void |
| 4 | Intake briefer skill | ~2-3 hrs | Automates Stage 1 for batch processing |
| 5 | Priority 4 reframe (3 deliverables) | ~4-6 hrs | Completes Haiku generation pipeline |

**Total remaining effort: ~13-18 hours**

After Gap 1 and Gap 2 are complete, the pipeline goes from ~60% to ~80% automated. After all gaps are filled, it reaches ~95% (the remaining 5% is Kim's manual stages: Seeds and Listen-Through).

---

## SAFETY PROTOCOLS FOR ALL FUTURE EDITS

All modifications to production skills and documents must follow:

1. **document-handling-rules** skill — 8 rules governing every file write
2. **verified-edit** skill — 7-step per-edit protocol with independent validation
3. **CLAUDE.md** safety protocols — Kim-confirmation gate, read-before-write, version-up, Source Fidelity

These are non-negotiable. See `.claude/skills/document-handling-rules/SKILL.md` and `.claude/skills/verified-edit/SKILL.md`.

---

## AUTHORITY DOCUMENTS

| Document | Version | Authority For |
|----------|---------|--------------|
| MODULE_PRODUCTION_MASTER_PLAN_v2_1.md | v2.1 | Pipeline stages, batch strategy, Directus schema |
| VOICE_ROSTER_LOCKED_v2.md | v2 (April 6) | Voice IDs, model, settings |
| ARC_PRODUCTION_BIBLE_v2_10.md | v2.10 | Module format, resolution rules, return-to-map |
| CANONICAL_DATA_MODEL_v1_12.md | v1.12 | Firestore schema, field definitions |
| UNIFIED_TECHNIQUE_INVENTORY_v1_14.md | v1.14 | Technique names, domains, clinical sources |
| CLAUDE_Guide_Bird_AI_System_Prompt_v1_4.md | v1.4 | Haiku narrative generation prompt |
| PHASE_B_AUDIO_ASSEMBLY_GUIDE_v1_4.md | v1.4 | Audio assembly specs, breathCycle params |
| SKILL_CORRECTION_MASTER_PLAN_v1.md | v1 | Correction plan and audit trail |
| SKILL_CORRECTION_DIFF_REPORT_April11.md | April 11 | Line-by-line diff of all corrections |

---

*— End of Document —*
