# Session Handoff — April 11, 2026 (Thread 3 → Thread 4)

**Thread:** Infrastructure + Dashboard Automation + Pipeline Gap Analysis + Document Cascade
**Date:** April 11, 2026 (Saturday, ~midnight)
**Kim's working style:** Solo founder, uses AI tools (Lovable, Cursor, Claude Code), expects Claude to operate autonomously, hates busywork, prefers parallel agent execution, wants zero browser touching for infrastructure

---

## WHAT TO DO FIRST IN THE NEXT SESSION

### Priority 2: Build audio-producer skill (1-2 sessions estimated)

This is the **#1 production bottleneck** now that WaveSpeed credits are refilled. Every module's audio is currently assembled manually. The skill needs:

**Batch TTS generation** — ElevenLabs API (`api.elevenlabs.io/v1/text-to-speech/{voice_id}`). Key on file in `Production/API_KEYS_MASTER.md`. Voice IDs locked: Myrrhin `oR4uRy4fHDUGGISL0Rev`, Guide Bird `7o9pyvsN0ob5GO6LBQp6`. Creator plan ($22/mo). Read `TTS_PERSONALIZATION_PIPELINE_v1.md` for the segment-level personalization spec — only sentences containing `{childName}` etc. are rendered per-child; universal sentences are shared across all children.

**Vosk cue-point extraction** — Proven in M1/M2 but no automation script exists. Vosk STT generates word-level timestamps from TTS output. These timestamps become cue points for breathing cycle sync, bell triggers, inhale/exhale markers. See `Production/AUDIO_PIPELINE_MASTER_PLAN_v1.md` and `Production/PHASE_B_AUDIO_ASSEMBLY_GUIDE_v1_4.md`.

**ffmpeg multi-track mixing** — Layer voice stem + ambient bed + functional SFX (breathing cues, transition bells, landing shimmer). Three-layer architecture documented in `Sound_Design_Vision_v1.md`. Output: MP3 192kbps.

**CRITICAL GAP: No ambient bed assets exist yet.** Domain sound palettes are designed conceptually (Calm=warm pads, Focus=crystalline, Heart=heartbeat textures) but never produced. Options: ElevenLabs SFX v2, commission, or AI generation. This blocks full Phase B audio mixing.

**What exists for reference:**
- `Production/PHASE_B_AUDIO_ASSEMBLY_GUIDE_v1_4.md` — step-by-step manual process
- `Production/AUDIO_PIPELINE_MASTER_PLAN_v1.md` — full pipeline with Vosk integration
- `Production/Sound_Design_Vision_v1.md` — domain sound palettes, functional sound types
- `Production/Event_1/` — M1 Tessa production artifacts (completed example)
- Only `inhale sound.mp3` and `exhale sound.mp3` exist in Production/ for breathing cues
- M1, M2, M3 have final mixes; M4-M54 have nothing

### Priority 4: Codify narrative generation system prompts (1 session)

The Audio Pipeline Master Plan says Claude Haiku generates 6 narrative text fields per module: Call, Buy-In, Rescue Transition, Win, Nudge, Bridge. But the actual system prompt templates were never written down. Extract patterns from M1-M3 completed modules and codify reusable prompt templates so narrative text generation can be automated from skeleton data.

---

## COMPLETE INFRASTRUCTURE MAP (Everything the next thread needs)

### Directus Production Dashboard — FULLY OPERATIONAL

**URL:** `https://directus-production-3460.up.railway.app`
**Auth:** Email/password → JWT (15-min TTL). Re-authenticate before each batch.
**Credentials:** In `Production/API_KEYS_MASTER.md` (Directus admin: `kimhyla11@gmail.com` / `directus11$`)

**Authentication pattern:**
```bash
TOKEN=$(curl -s -X POST "https://directus-production-3460.up.railway.app/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "kimhyla11@gmail.com", "password": "directus11$"}' \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['data']['access_token'])")
BASE="https://directus-production-3460.up.railway.app"
```

**20 registered collections:**
- Core: `prod_modules` (Kanban source), `prod_arcs`, `prod_creatures`, `prod_techniques`
- Content: `prod_phase_b_scripts`, `prod_phase_a_scenes`, `prod_module_json`
- Assets: `prod_audio_assets`, `prod_visual_assets`, `prod_voice_profiles`, `prod_asset_versions`
- Workflow: `prod_activity_log`, `prod_blockers`, `prod_approvals`, `prod_checklists`, `prod_checklist_items`, `prod_dependencies`, `prod_session_decisions`
- Reference: `prod_stages`, `prod_assets`

**Two-field status system (CRITICAL — learn this):**
- `current_stage`: text FK → one of: `intake`, `kim_seeds`, `phase_b`, `phase_a_json`, `audio`, `listen_through`
- `stage_status`: PostgreSQL enum → one of: `not_started`, `in_progress`, `blocked`, `completed`
- The enum is DB-enforced. Any other value = rejected write.

**7 tracking fields added April 11:**
- `stage_entered_at` (timestamp) — when module entered current stage
- `seed_card` (text) — reference to seed card content
- `phase_b_script_id` (integer FK → prod_phase_b_scripts)
- `phase_a_scene_id` (integer FK → prod_phase_a_scenes)
- `module_json_id` (integer FK → prod_module_json)
- `audio_status` (text) — audio production sub-status
- `visual_status` (text) — visual production sub-status

**Existing presets:**
- Kanban (ID 1): grouped by `current_stage`, title=`creature_name`, text=`spell_name`
- "Active Blockers": tabular view of `prod_blockers`, sorted by `-created_at`
- "Recent Activity": tabular view of `prod_activity_log`, sorted by `-created_at`
- Display template: `M{{m_number}} {{creature_name}} — {{spell_name}}`

**Current module state (as of April 11):**
- M1 (Tessa): `current_stage=phase_a_json`, `stage_status=not_started`
- All others: early pipeline stages (most at intake or kim_seeds)

**Current blockers (unresolved):**
- ID 3: M5 (Bork) Phase B Script Missing (severity: high)
- ID 4: M6 (Bramble) Phase B Script Missing (severity: high)
- ID 1: M1 Phase B v4 Approval — RESOLVED
- ID 2: WaveSpeed Credits Exhausted — RESOLVED (refilled to $150.13)

**Moving a module forward:**
1. Set `stage_status = 'completed'` on the current stage
2. Update `current_stage` to the next stage key
3. Reset `stage_status = 'not_started'`
4. Log the transition in `prod_activity_log`
5. For hard gates (phase_b, listen_through): record in `prod_approvals` first, only after Kim confirms

**The dashboard-ops skill** (`/.claude/skills/dashboard-ops/SKILL.md`) has complete API reference with curl examples for every operation. ALWAYS load this skill before touching any production data.

### Railway — Hosting Infrastructure

**Project:** `efficient-grace` (Free trial, $5 credit)
**Services:** Directus + Redis only (PostGIS deleted April 10)
**API Token:** `200d4b4e-c009-475e-ae4e-d5a677fd4835` (workspace scope)
**GraphQL endpoint:** `https://backboard.railway.com/graphql/v2` with Bearer token
**Note:** Workspace-scoped tokens can't query `me` — use `projects` query directly

### Supabase — PostgreSQL Database

**Project ref:** `ugjpauwozlruyctrygby` (mindfulnest-production, Pro plan, us-east-1)
**DB Host:** `db.ugjpauwozlruyctrygby.supabase.co`
**DB User (pooler):** `postgres.ugjpauwozlruyctrygby`
**DB Password:** `supapass11mn` (changed from `supapass11$` because Railway mangled the `$`)
**Port:** 5432, Database: `postgres`

### WaveSpeed AI — Video Animation + Lip Sync

**API Key:** `<REDACTED_PER_LD208_USE_DOPPLER>`
**Balance:** $150.13 (Silver tier, refilled April 11)
**Endpoints:**
- Seedance 1.5 Pro: `api.wavespeed.ai/api/v3/bytedance/seedance-v1.5-pro/image-to-video` (POST) — ~$0.06/clip
- Seedance poll: `api.wavespeed.ai/api/v3/predictions/{id}/result` (GET)
- ByteDance LipSync: `api.wavespeed.ai/api/v3/bytedance/lipsync/audio-to-video` (POST) — ~$0.15/clip

### All Other API Keys

All in `Production/API_KEYS_MASTER.md`. Key ones:
- **ElevenLabs:** `<REDACTED_PER_LD208_USE_DOPPLER>` (Creator $22/mo)
- **FLUX Kontext (BFL):** `<REDACTED_PER_LD208_USE_DOPPLER>` (~920 credits, $0.08/img)
- **fal.ai:** `<REDACTED_PER_LD208_USE_DOPPLER>`
- **Replicate:** `<REDACTED_PER_LD208_USE_DOPPLER>`
- **Segmind:** `<REDACTED_PER_LD208_USE_DOPPLER>` (low credits)

---

## THE 6-STAGE PIPELINE (Collapsed April 10 from 10 stages)

| # | Stage Key | Name | Owner | Hard Gate? | Time Est. |
|---|-----------|------|-------|------------|-----------|
| 1 | `intake` | Intake | Claude + Kim | No | ~7-10 min |
| 2 | `kim_seeds` | Kim Seeds | Kim | No | ~5 min |
| 3 | `phase_b` | Phase B Draft + Approval | Claude draft, Kim approves | **YES** | 15-30 min |
| 4 | `phase_a_json` | Phase A + JSON Build | Claude | No | ~20-30 min |
| 5 | `audio` | Audio Production | Claude Code | No | ~15-45 min |
| 6 | `listen_through` | Listen-Through | Kim | **YES** | ~5 min |

**Batch production strategy:** Assembly-line batching — 4-6 modules batch through each stage together. One queue type per session (INTAKE, SEEDS, PHASE_B, ASSEMBLY, AUDIO). Reduces Kim's context-switching.

**What was removed:** Research (old Stage 4), Research Review (old Stage 5), standalone Design Review (old Stage 9), Triage as standalone (folded into Kim Seeds).

---

## 3-STAGE VIDEO PIPELINE (All via REST API)

1. **FLUX Kontext stills** → Character-consistent image generation ($0.08/img via BFL API)
2. **Seedance 2.0 / Kling 3.0 animation** → Image-to-video ($0.06/clip via WaveSpeed)
3. **ByteDance lip sync** → Audio-to-video mouth sync ($0.15/clip via WaveSpeed)

**Scripts exist:** `Production/video_pipeline/generate.py`, `extract_scenes.py`, `config.py`, `review.py`
**Character refs:** 419 images across all creatures in `Production/` subfolders
**Species swap recipe:** `Production/Guide_Bird/SPECIES_SWAP_RECIPE_v1.md` + `species_swap.py`
**Visual style:** Pixar 3D (confirmed April 10, supersedes painterly)

**What's missing:** Batch orchestration with retry logic and vendor fallback switching. Currently manual, one-event-at-a-time.

---

## 5 AUDIO STREAMS

1. **Phase B meditation** — Myrrhin narrator voice, breathing cycles, ambient beds, cue points
2. **Narrative dialogue** — Per-character TTS with locked voice profiles
3. **TTS personalization** — Segment-level: only `{childName}` sentences re-rendered per child (~$2.82/child lifetime)
4. **Guide Bird AI dialogue** — Dynamic generation for interactive scenes
5. **Map/UI audio** — Ambient, transitions, UI sounds

---

## WHAT WAS ACCOMPLISHED IN THIS SESSION (Thread 3)

### Staleness scan + document corrections
- Bible v13_10 → v13_11: Fixed 2 "Keepers" → "Light Keepers" references
- ArcBuilder v1_4 → v1_5: Fixed 9 stale version references (all verified by independent validator)
- All 6 canonical files confirmed current and consistent

### Infrastructure setup (all via API, no browser)
- 20 prod_* collections registered in Directus via PATCH /collections/{name}
- Two-field status system configured (current_stage + stage_status with PostgreSQL enum)
- Kanban preset created (grouped by pipeline stage)
- Tabular presets for Active Blockers and Recent Activity
- Display template configured: `M{{m_number}} {{creature_name}} — {{spell_name}}`
- M1 Tessa status updated to phase_a_json/not_started
- Railway API token created and stored
- PostGIS service deleted from Railway (only Directus + Redis remain)

### Dashboard-ops skill created and installed
- Full skill at `/.claude/skills/dashboard-ops/SKILL.md`
- Covers: auth, two-field status system, all 20 collections, CRUD operations, error reference, Railway management
- Kim installed via .skill package

### WaveSpeed credits refilled
- Kim added $100 → total balance $150.13 (Silver tier)
- Blocker ID 2 resolved on dashboard, activity logged

### 7 tracking fields added to prod_modules
- stage_entered_at, seed_card, phase_b_script_id, phase_a_scene_id, module_json_id, audio_status, visual_status
- All independently validated as present in live schema
- FK relationships may need UI configuration in Directus (API reported collection-not-found for relationship setup, but integer fields are in place)

### Document cascade (April 10-11 decisions)
- MODULE_PRODUCTION_MASTER_PLAN v2_0 → v2_1: 6-stage pipeline, batch production, Directus dashboard section
- MINDFULNEST_BUILD_EXECUTION_PLAN v2_0 → v2_1: Sequential → parallel engineering, Directus refs, 8 stale term/version fixes
- Memory files updated: pipeline memory (10→6 stage), Directus memory (7 new fields), MEMORY.md index
- All validated by independent agents — zero errors

### Production Gap Analysis created
- `Production/PRODUCTION_GAP_ANALYSIS_APRIL10_2026.docx` — comprehensive .docx with tiered priorities
- Tier 1 (critical): WaveSpeed credits ✅ RESOLVED, audio automation scripts (STILL NEEDED), ambient bed assets (STILL NEEDED)
- Tier 2 (medium): Dashboard schema ✅ DONE, narrative prompts (STILL NEEDED), video batch queue (STILL NEEDED), module JSON builder (STILL NEEDED)
- Tier 3 (pre-delivery): Runtime scene composer, Phase A React components, CDN pipeline, breathing cue library, personalization engine

---

## HARD-WON LESSONS (Critical for next thread)

### Browser automation DOES NOT WORK
- Chrome gets "read" tier in computer-use (screenshots only, no clicks)
- Chrome MCP extension disconnects due to MV3 service worker idling
- **Solution:** Use Directus REST API and Railway GraphQL API directly via curl in Bash. This is the ONLY reliable path. The dashboard-ops skill encodes all the patterns.

### Directus API quirks
- Use PATCH (not POST) for registering existing tables — POST returns "Collection already exists"
- JWT tokens expire in 15 minutes — re-authenticate before each batch
- PostgreSQL enums are enforced at DB level — `stage_status` ONLY accepts: not_started, in_progress, blocked, completed
- Field creation works via POST /fields/{collection}, but relationship creation (POST /relations) may fail with "collection not found" even when collection exists — configure relationships in Directus UI if API fails
- Clear schema cache after DB changes: POST /utils/cache/clear

### Railway API quirks
- Workspace-scoped tokens can't query `me` — use `projects` query directly
- GraphQL endpoint: `https://backboard.railway.com/graphql/v2`

### File management rules
- Version-up, never overwrite (v2_0 → v2_1, never modify v2_0)
- .docx is the working format for production docs; .md for reference/canonical
- Always backup before editing, validate after
- Kim edits files on her Mac via Dropbox — always re-read from disk before writing

---

## CANONICAL DOCUMENT VERSIONS (Current as of April 11)

| Document | Version | Status |
|----------|---------|--------|
| Bible | v13_11 | Current |
| NDU | v2_8 | Current |
| ARC Production Bible | v2_10 | Current |
| ArcBuilder (skill) | v1_5 | Current |
| ArcBuilder (reference) | v2_3 | Current |
| Unified Technique Inventory | v1_15 | Current |
| Canonical Data Model | v1_12 | Current |
| TTS Personalization Pipeline | v1 | Current |
| Module Production Master Plan | v2_1 | Current (updated this session) |
| Build Execution Plan | v2_1 | Current (updated this session) |

---

## REMAINING GAP ANALYSIS PRIORITIES (After 2 and 4)

| Priority | What | Est. Effort | Status |
|----------|------|-------------|--------|
| 1 | WaveSpeed credits | Immediate | ✅ DONE |
| 2 | Audio-producer skill | 1-2 sessions | **DO THIS FIRST** |
| 3 | Dashboard field migration | 30 min | ✅ DONE |
| 4 | Narrative generation prompts | 1 session | **DO THIS SECOND** |
| 5 | Video batch orchestrator | 1-2 sessions | Pending |
| 6 | Module JSON builder | 2 sessions | Pending |
| 7 | Runtime scene composer spec | 1 session | Pending |
| 8 | Phase A component library | 2+ sessions | Pending |

---

## OTHER PENDING WORK (From original handoff, not yet started)

### Pre-launch Supabase actions (Priority 3 from Thread 2)
- RLS audit on all production tables
- COPPA DPA (Data Processing Addendum)
- Backup strategy
- TypeScript types generation from schema

### Ongoing production
- M1 (Tessa) is at phase_a_json/not_started — ready for Phase A + JSON build
- M5 (Bork) and M6 (Bramble) Phase B scripts missing (blockers on dashboard)
- Only M1-M3 have final audio mixes

---

## KEY SKILLS TO LOAD

- **dashboard-ops** — ALWAYS load before touching any production data
- **video-producer** — For any video/animation production work
- **verified-edit** — For any multi-document editing
- **cross-document-update** — For cascading decisions across docs
- **arcbuilder** — For any arc skeleton work

---

## KIM'S PROFILE (Quick Reference)

- Solo founder, no engineering team
- Near-zero build costs (Kim + AI tools)
- Doctoral student (CRI framework = her dissertation)
- Hates busywork, loves parallel execution
- Expects Claude to operate infrastructure autonomously
- Uses spell names only in conversation (never clinical labels)
- Narrative-first: MindfulNest is a "story game" where techniques serve the story
- Files live in Dropbox-synced folder on Mac
- Check `.auto-memory/MEMORY.md` for full profile and all feedback memories

---

*End of handoff. Next thread: start with staleness scan (per CLAUDE.md), then tackle Priority 2 (audio-producer skill) and Priority 4 (narrative generation prompts).*
