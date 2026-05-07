# MindfulNest Production Pipeline Brain v4

**Last updated:** April 13, 2026 (v4)  
**Purpose:** Single source of truth for every Claude session. Read THIS before doing any production work. If it's not in here, it doesn't exist.

---

## Part 1: What This System Is

MindfulNest is a therapeutic app for children ages 7-11. Children explore a fantasy world (Everdale), guided by a Guide Bird character, learning real therapeutic techniques framed as "magic spells" to help creatures in need. Kim Smith is the sole founder, building with AI tools (Lovable, Cursor, Claude Code). No engineering team.

Claude operates the entire production pipeline autonomously via API — Kim never touches a browser. Kim's only roles are creative/clinical review at two hard gates (Phase B script approval and Listen-Through audio approval).

---

## Part 1B: Dashboard-First Workflow (MANDATORY)

The Directus dashboard is the **central hub** for all production work. It is not a reporting tool you update at the end — it is the system of record you check FIRST and update AS YOU GO.

### Session Start Protocol (before any production work)

1. **Authenticate:** Get a fresh JWT token (15-min TTL — re-auth before each batch)
2. **Read locked decisions:** `GET /items/prod_audio_locked_decisions` — these are rules you MUST respect
3. **Read module state:** `GET /items/prod_modules/{id}` — check `current_stage`, `stage_status`, `session_checklist`, `session_resumption_notes`
4. **Read recent activity:** `GET /items/prod_activity_log?filter[module_id][_eq]={id}&sort=-created_at&limit=10` — see what's been tried
5. **Read unresolved blockers:** `GET /items/prod_blockers?filter[module_id][_eq]={id}&filter[is_resolved][_eq]=false`
6. **Read audio assets:** `GET /items/prod_audio_assets?filter[module_id][_eq]={id}` — see what files exist and their status
7. **Read session decisions:** `GET /items/prod_session_decisions?filter[module_id][_eq]={id}&sort=-created_at` — past decisions

Only after reading all 7 should you begin work.

### During Production — Log Everything

| When This Happens | Log It Here |
|-------------------|-------------|
| Generate a voice stem | `prod_activity_log` (with voice_settings, script_version) + `prod_audio_assets` (new row) |
| Kim approves/rejects something | `prod_activity_log` (kim_verdict + kim_feedback) + update asset status in `prod_audio_assets` |
| Hit a blocker | `prod_blockers` (with severity) |
| Make a creative/technical decision | `prod_session_decisions` |
| Resolve a blocker | PATCH `prod_blockers/{id}` (is_resolved=true, resolved_at) |
| Complete a checklist item | Update `prod_modules.session_checklist` (mark item done) |
| Create any file | `prod_audio_assets` or `prod_visual_assets` (register it) |

### Session End Protocol

1. Update `prod_modules.session_resumption_notes` — exactly where you stopped, what's next
2. Update `prod_modules.session_checklist` — mark completed items, add new ones if discovered
3. Log final activity entry: "Session ended. State: [summary]"

### Collections Quick Reference

| Collection | Records | Purpose |
|------------|---------|---------|
| `prod_modules` | 6 (Arc 1) | Module status, stage, checklist, handoff notes |
| `prod_audio_locked_decisions` | 10 | Rules that MUST be respected (voice settings, delivery, etc.) |
| `prod_activity_log` | 9+ | Every action with voice_settings, verdict, feedback |
| `prod_audio_assets` | 6+ | Every audio file with status and Kim feedback |
| `prod_session_decisions` | 6+ | Creative/technical decisions with context |
| `prod_blockers` | 4 | Current and resolved blockers |
| `prod_approvals` | 0 | Hard gate approval records |
| `prod_arcs` | 1 | Arc-level metadata |
| `prod_creatures` | 6 | Creature profiles |
| `prod_techniques` | 6 | Technique definitions (spell name, clinical name, tier) |
| `prod_voice_profiles` | 2 | Myrrhin + Guide Bird voice settings |
| `prod_scripts` | 6+ | Unified script registry. One record per script per module. Tracks Phase B meditation, Phase B TTS input, Buy-In, Phase A, Resolution, Return to Map. Fields: module_id, creature_name, script_type, current_version, file_path, tts_input_path, status, kim_verdict, kim_feedback, approved_at, notes. Version HISTORY lives in prod_activity_log (not duplicated here). Design: Agent 2 collection + Counter-Agent 3 activity_log for history. |
| `prod_phase_b_scripts` | 1 | Script versions with status (backward compatibility; `prod_scripts` is canonical registry) |
| `prod_phase_a_scenes` | 0 | Phase A scene data |
| `prod_module_json` | 0 | Module JSON exports |
| `prod_visual_assets` | 0 | Stills, animations, lip sync |
| `prod_asset_versions` | 0 | Version chains |
| `prod_checklists` / `prod_checklist_items` | 0 | Quality checklists |
| `prod_dependencies` | 0 | Module dependency graph |
| `prod_stages` | 6 | Stage definitions (read-only ref) |

---

## Part 2: The 5-Stage Pipeline

```
Stage 1: INTAKE .................. Claude autonomous     (~15 min/module)
Stage 2: PHASE B DRAFT+APPROVAL .. Claude + Kim          (~2-3 hours) — HARD GATE
Stage 3: PHASE A + MODULE JSON ... Claude + Kim review    (~2-3 hours/module)
Stage 4: AUDIO PRODUCTION ........ Claude autonomous      (~1.5-2 hours)
Stage 5: LISTEN-THROUGH .......... Kim                    (~15-30 min) — HARD GATE
```

### Directus Stage Keys
`intake` → `phase_b` → `phase_a_json` → `audio` → `listen_through`

### Two-Field Status System
| Field | Type | Values |
|-------|------|--------|
| `current_stage` | text FK | `intake`, `phase_b`, `phase_a_json`, `audio`, `listen_through` |
| `stage_status` | PostgreSQL enum | `not_started`, `in_progress`, `blocked`, `completed` |

### Moving a Module Forward
1. Set `stage_status = 'completed'`
2. Update `current_stage` to next stage key
3. Reset `stage_status = 'not_started'`
4. Log transition in `prod_activity_log`

### Hard Gates (Require Kim's Explicit Approval)
- **Phase B Approval** (Stage 2): Kim says "approved" → record in `prod_approvals` → advance to `phase_a_json`
- **Listen-Through** (Stage 5): Kim listens to audio + says "approved" → record in `prod_approvals` → module complete

---

## Part 3: The 9 Production Skills

All skills live in `.claude/skills/`. Load via the Skill tool.

**LOADING ORDER:** Always load `dashboard-gate` FIRST before any production work. It enforces the 7-query session start protocol, real-time logging, and locked decision compliance. Then load the domain skill for the current stage (e.g., `audio-producer`, `phase-b-writer`). `dashboard-ops` is available as API reference but rarely needs explicit loading.

### Skill Dependency Chain

```
Arc Skeleton (Kim's source of truth)
    │
    ├→ [1] intake-briefer ──→ Intake Briefs + Directus records
    │                              │
    │                              ▼
    ├→ [2] phase-b-writer ──→ Approved Phase B script with {{CUE_MARKERS}}
    │                              │
    │              ┌───────────────┼───────────────┐
    │              ▼               ▼               ▼
    ├→ [3a] phase-a-designer  [3b] module-json-builder  [3c] narrative-generator
    │         │                     │                         │
    │         ▼                     ▼                         ▼
    │    Beat sheet          module_M{N}_config.json    aiNarrativeCache
    │                              │
    │                              ▼
    ├→ [4] audio-producer ──→ m{N}_phase_b_complete_mix.mp3
    │                              │
    │                              ▼
    └→ [5] video-producer ──→ Story Scene + Resolution MP4s (parallel visual stream)
    
    [0a] dashboard-gate ←── LOAD FIRST: behavioral enforcement (when/why to query dashboard)
    [0b] dashboard-ops ←── API reference (how to query dashboard: schemas, curl, gates)
```

### Skill Quick Reference

| # | Skill | Trigger Phrase | What It Does | Inputs | Outputs |
|---|-------|---------------|--------------|--------|---------|
| 0 | **dashboard-ops** | "check dashboard", "update status", "move M1" | Directus API hub: auth, stage changes, blockers, activity log | API_KEYS_MASTER.md | Status updates, approval records |
| 1 | **intake-briefer** | "intake arc", "start production" | Parse skeleton → create Intake Briefs + Directus records | Arc skeleton | `M{N}_{CREATURE}_{SPELL}_INTAKE_BRIEF.md` |
| 2 | **phase-b-writer** | "write Phase B", "meditation script" | 9-step meditation script with cue markers | Intake brief + skeleton + Technique Inventory | Approved script with `{{INHALE_CUE}}` markers |
| 3a | **phase-a-designer** | "design Phase A", "beat sheet" | Interactive demo design (Guide Bird narrates, child performs) | Approved Phase B + skeleton | Beat sheet with interactions + timeouts |
| 3b | **module-json-builder** | "build JSON", "module config" | Firestore-ready module JSON with Q1-Q19 guardrails | Phase A beat sheet + Phase B script + CDM | `module_M{N}_config.json` + guardrail report |
| 3c | **narrative-generator** | "generate narrative", "Guide Bird dialogue" | Haiku-generated aiNarrativeCache (6 fields) | Skeleton + Guide Bird System Prompt | aiNarrativeCache document |
| 4 | **audio-producer** | "produce audio", "TTS generation", "mix module" | ElevenLabs TTS → Vosk STT → breathCycle → ffmpeg mix | Phase B script with markers | `m{N}_phase_b_complete_mix.mp3` |
| 5 | **video-producer** | "produce event", "video production" | [UPDATED] Gemini 2.5 Flash stills → Seedance/Kling animation → ByteDance lip sync → assembly | All prior outputs + character refs | `M{N}_{CREATURE}_{SEGMENT}.mp4` |

### Cross-Skill Handoff Contracts

| From | Data | To | Contract |
|------|------|----|----------|
| intake-briefer | Intake brief | phase-b-writer | Creature/domain/spell confirmed |
| phase-b-writer | Script + cue markers | audio-producer | `{{INHALE_CUE}}` etc. embedded |
| phase-b-writer | Vocabulary card | phase-a-designer | Exact Phase A words, no synonyms |
| phase-a-designer | Beat sheet | module-json-builder | Trigger names + VERBATIM text |
| phase-b-writer | Script | module-json-builder | phaseBTransitionCue + audioProductionType |
| module-json-builder | JSON config | audio-producer | guidedAudioRef path |
| audio-producer | Complete MP3 | video-producer | Location: `Production/Event_{N}/` |

---

## Part 4: Infrastructure

### Directus Dashboard
- **URL:** `https://directus-production-3460.up.railway.app`
- **Auth:** POST `/auth/login` → JWT (15-min TTL). ALWAYS re-auth before writes.
- **Credentials:** In `Production/API_KEYS_MASTER.md` — read at runtime, NEVER hardcode
- **Admin:** kimhyla11@gmail.com
- **Collections:** 20 `prod_*` collections (modules, blockers, approvals, activity_log, phase_b_scripts, phase_a_scenes, module_json, audio_assets, visual_assets, etc.)
- **Tracking fields on prod_modules:** kim_notes, claude_approach, blockers_count, last_updated_by, phase_b_approved_at, listen_through_approved_at (added April 11, 2026)

### External APIs

| API | Use | Cost | Endpoint |
|-----|-----|------|----------|
| **ElevenLabs** | TTS voices | ~$0.24/1K chars | `api.elevenlabs.io/v1/text-to-speech/{voice_id}` |
| **Gemini 2.5 Flash Image** [NEW April 12] | Pixar 3D character stills (two-pass for duo shots) | ~$0.039/img | Via google.genai Python library (gemini-2.5-flash-image model). Two-pass: Pass 1 = primary char + scene, Pass 2 = add secondary char to Pass 1 output. |
| **Seedance 1.5 Pro** (WaveSpeed) | Animation | $0.06/clip | `api.wavespeed.ai/api/v3/bytedance/seedance-v1.5-pro/image-to-video` |
| **ByteDance LipSync** (WaveSpeed) | Lip sync | $0.15/5s clip | `api.wavespeed.ai/api/v3/bytedance/lipsync/audio-to-video` |
| **Kling v1.5/pro+** (fallback) [UPDATED April 13] | Animation (ONLY v1.5/pro or higher — v1/standard BANNED) | ~$0.10/sec | When Seedance is unreachable. NEVER use v1/standard tier. |
| **Claude Haiku** | Narrative gen | ~$0.01/module | Via Anthropic API |

### Cost Controls
- **Per-module audio:** ~$0.70-1.80
- **Per-scene video:** ~$0.26 (Gemini $0.039 + Seedance $0.06 + Lip sync $0.15) [UPDATED]
- **Circuit-breaker:** $50/session threshold — stops all API calls, notifies Kim
- **WaveSpeed balance:** ~$150 (Silver tier, as of April 11)
- **Gemini API:** No per-request limits noted in testing (April 12)

### Visual Production Rules [NEW April 13]

**HARD RULES — These are non-negotiable production constraints:**

1. **NO TEARS IN STILLS:** All image-to-video models amplify liquid features into waterfalls. Remove ALL visible tears from character stills before animation. Convey crying through audio (ElevenLabs voice acting with emotional direction tags) only. Acceptable visual cues: puffy/tired eyes, downcast expression, withdrawn posture. NOT acceptable: tear drops, wet cheeks, glistening eyes, tear tracks.

2. **NO Kling v1/standard:** Catastrophically bad quality — prompt-dominant model that ignores input image entirely. Produces random scenes, rubber artifacts, face mushing, hallucinated text. Use Seedance 1.5 Pro (primary) or Kling v1.5/pro+ (fallback only). Fallback chain: Seedance 1.5 Pro → fal.ai Seedance 2.0 → Kling v1.5/pro+. SKIP v1/standard.

3. **Single-scene multi-angle for dialogue:** For dialogue-heavy scenes, use one master wide shot + cropped close-ups of each character's head. Animate each piece separately. This eliminates scale drift, ghost doubling, and multi-character artifacts. Matches professional animated film technique.

4. **Gemini two-pass for duo shots:** Pass 1 = primary character + scene (3-4 refs). Pass 2 = add secondary character to Pass 1 output (3-4 refs of secondary char). Never put 7+ reference images in a single Gemini call — identity drift occurs on the subtler character.

5. **Anti-bioluminescence:** All "magical forest" prompts must explicitly block: "NO bioluminescent particles, NO glowing flowers, NO magical sparkles, NO light trails." Gemini hallucinates light effects when "magical" is in the prompt.

6. **Blue scarf enforcement:** Every Guide Bird prompt must say: "BLUE KNITTED SCARF made of YARN/WOOL, NOT a brown hood, NOT a cloak, NOT leather." Gemini generates a brown hood ~30-40% of the time without this blocking language.

### Tools Available in Sandbox
- `ffmpeg` v4.4.2 (audio/video mixing)
- `python3` 3.10.12 (scripting, API calls)
- `vosk` (install via pip — speech-to-text for cue point extraction)
- `google-genai` Python library (for Gemini 2.5 Flash image generation) [NEW April 12]
- `pip install --break-system-packages` for new packages

---

## Part 5: Safety Mechanisms

Every skill has these protections. Do NOT skip them.

| Mechanism | Where | What It Does |
|-----------|-------|-------------|
| **Pipeline Stage Verification** | 6 skills | Bash check: confirms module is at correct stage + not blocked before proceeding |
| **Version-Up Rule** | All 8 | Create v(N+1), never overwrite existing files |
| **Pre-Write Kim Confirmation Gate** | All 8 | Ask Kim with FULL FILENAME before overwriting working docs. **Pipeline-generated outputs EXEMPT.** |
| **Read-Before-Write** | phase-b-writer, phase-a-designer, module-json-builder | Re-read file from disk before generating new version |
| **Concurrent Session Safety** | dashboard-ops | Check activity log for recent changes by other sessions |
| **Rejection Workflow** | phase-b-writer | If Kim says "no": stay at phase_b, create blocker, log reason |
| **Mandatory Re-Auth** | video-producer, phase-b-writer | Fresh JWT before any dashboard write |
| **API Retry Protocol** | audio-producer, video-producer, narrative-generator | Exponential backoff: 2s→4s→8s→16s→32s, max 5 attempts |
| **Email Notifications** | dashboard-ops, phase-b-writer, audio-producer | Gmail MCP notification to Kim at hard gates + API failures |
| **Cost Circuit-Breaker** | dashboard-ops, audio-producer, video-producer, narrative-generator | $50/session threshold |
| **Cross-Stage Validation** | intake-briefer, phase-b-writer, phase-a-designer, module-json-builder | Verify skeleton data matches across all stages |
| **Sub-Step Tracking** | dashboard-ops, phase-b-writer, phase-a-designer | `sub_step` field for session resumption |

---

## Part 6: Arc 1 Module Data (FIXED)

M-numbers are PERMANENT. Never change these.

| Play Order | M# | Creature | Domain | Stone | Color | Spell | Inscription | Opening Gong |
|-----------|-----|----------|--------|-------|-------|-------|-------------|---------------|
| 1 | M1 | Tessa | Body-Sensing | Body Stone | Orange | Magic Hands Spell | "Feel what's real" | m1_gong_final.mp3 (Kim-approved) |
| 2 | M2 | Luna | Now-Watching | Watching Stone | Yellow | Breath-Squeezers Spell | "Stay loose and light" | TBD |
| 3 | M4 | Ember | Kindness | Heart Stone | Red | Heart-Sending Spell | "Let the flowers bloom" | TBD |
| 4 | M6 | Bramble | Calm-Breathing | Calm Stone | Blue | Humming Spell | "Everything is made of energy" | TBD |
| 5 | M3 | Benson | Courage | Courage Stone | Green | Brave Sniffing Spell | "There is nothing to fear when you go inside" | TBD |
| 6 | M5 | Bork | Self-Grounding | Grounding Stone | Purple | Letting Go Spell | "Connect with the Light" | TBD |

### Comet Philosophy (Technique Ordering)
Arc 1 front-loads physiologically impactful techniques:
- **Tier 1 (impossible to miss):** Magic Hands (tingling), Breath-Squeezers (squeeze-release), Humming (vibration)
- **Tier 2 (clear with attention):** Brave Sniffing (heart-rate shift), Heart-Sending (warmth)
- **Tier 3 (subtle):** Letting Go (absence of effort)

### Voice Architecture
- **Myrrhin:** Old wizard, ElevenLabs library voice (`oR4uRy4fHDUGGISL0Rev`). Narrates Opening Storybook + ALL Phase B meditations.
- **Guide Bird:** Consistent across all arcs (`7o9pyvsN0ob5GO6LBQp6`). Warm, energetic, self-deprecating.
- **Each creature:** Unique voice, designed when arc enters production.
- **Personalization variables:** `{childName}`, `{chosenGuideName}`, `{therapistName}`, `{parentTitle}`, `{parentName}`, pronouns (boy→he/him/his, girl→she/her/her). No they/them.

---

## Part 7: Current Production Status (Update This Section)

**Last updated:** April 12, 2026

| Module | Directus Stage | Phase B Script | Audio | Gong Selection | Notes |
|--------|---------------|---------------|-------|-----------------|-------|
| M1 Tessa | `audio` / in_progress | v6 (approved) | Voice stem v5 pending | m1_gong_final.mp3 ✓ LOCKED | Gong approved, opening mix + final voice stem TBD |
| M2 Luna | `intake` / not_started | v2 exists — **STALE** (references "Shelly") | Exists but likely stale | TBD | Needs Phase B rewrite |
| M3 Benson | `intake` / not_started | v2 corrected | Complete mix | TBD | Ready for Phase A |
| M4 Ember | `intake` / not_started | Approved, needs cue markers | Not started | TBD | Ready after markers |
| M5 Bork | `intake` / not_started | Not written | Not started | TBD | Needs Phase B |
| M6 Bramble | `intake` / not_started | Not written | Not started | TBD | Needs Phase B |

**Known Asset Gaps:**
- M4 (Ember) and M6 (Bramble) ambient beds — 11 existing beds in library may cover these; check domain-appropriate selections in audio-producer skill
- M2 Phase B script references wrong creature name ("Shelly" → should be "Luna")

---

## Part 8: Canonical Authority Documents

Always use the HIGHEST version number. These are the source of truth.

| Document | Current Version | Location |
|----------|----------------|----------|
| World Design Bible | v13_11 | `Canon/CLAUDE_Everdale_World_Design_Bible_v13_11.md` |
| Narrative Decisions Unified | v2_8 | `Canon/NARRATIVE_DECISIONS_UNIFIED_v2_8.md` |
| Arc Production Bible | v2_10 | `Canon/ARC_PRODUCTION_BIBLE_v2_10.md` |
| ArcBuilder | v2_3 | `Canon/ArcBuilder_v2_3.md` |
| Technique Inventory | v1_15 | `Canon/UNIFIED_TECHNIQUE_INVENTORY_v1_15.md` |
| Canonical Data Model | v1_12 | `Canon/CANONICAL_DATA_MODEL_v1_12.md` |
| TTS Personalization Pipeline | v1 | `Canon/TTS_PERSONALIZATION_PIPELINE_v1.md` |
| WaveSpeed API Reference | v1 | `Production/WAVESPEED_API_REFERENCE_v1.md` |
| API Keys Master | — | `Production/API_KEYS_MASTER.md` |

---

## Part 9: Terminology (Current vs. Retired)

| Old/Wrong | Current/Correct | Notes |
|-----------|----------------|-------|
| GlowDrop | Zap | Firestore key still uses `glowdrop` |
| Prism (communication) | Zap | April 2 rename; "prism" now = Wisdom Stone optics |
| Shelby | Tessa | Turtle, fully renamed |
| Kindness Stone | Heart Stone | Art name stays "Art of Kindness" |
| XP | Coins | Reward currency |
| Keepers | Light Keepers | Light Masters = powerful Light Keepers |
| Breath-Squeezers (M1) | Magic Hands Spell (M1) | Post-comet revision |
| Thought Clouds (M2) | Breath-Squeezers Spell (M2) | Post-comet revision |
| Ground-Strong (M6) | Humming Spell (M6) | Post-comet revision |
| Brave Steps (M3) | Brave Sniffing Spell (M3) | Post-comet revision |

---

## Part 10: Kim's Working Rules

These are non-negotiable behavioral expectations from Kim:

1. **Read existing docs first.** Kim has 200+ project documents. Search and read before generating new analysis.
2. **Narrative-first design.** MindfulNest is a "story game." Narrative entertainment comes first; techniques serve the story.
3. **Phase A must be simple.** Shows WHAT (ingredients + outcome), not HOW. No vocabulary, no sensation language.
4. **Use spell names only.** "Magic Hands Spell," never "Palm Interoception."
5. **Source fidelity.** Kim's dialogue is copied character-for-character, never retyped through Claude's text generation.
6. **Exhaustive verification.** Multiple agents, multi-pass checks, independent blind validation. No shortcuts.
7. **File output to Dropbox project folder only.** Never stray paths.
8. **Version-up, never overwrite.** Always create v(N+1).
9. **Kim-confirmation gate with FULL FILENAME.** "Kim, I'm about to write `[EXACT_FILENAME]`. Have you made edits?" Pipeline-generated outputs exempt.
10. **Density is not progress.** Never show activity frequency as a progress indicator. Only measured goals (GPR/CLQ).
11. **Keep clinical layers separate.** Layer 1 (mechanism) = Therapeutic Notes only. Layer 2 (character feeling) = dialogue. Layer 3 (child sees) = video.
12. **No manipulative mechanics.** No streaks, no "last active," no emotional dark patterns.
13. **Follow production order.** Read spec → present priority order to Kim → get alignment → then touch tools.

---

## Part 11: Session Start Protocol

**MANDATORY before any production work:**

1. **Run staleness scan** (see CLAUDE.md for full procedure) — check canonical docs for drift in character names, technique names, party composition, retired terminology, version numbers. Produce GREEN/YELLOW/RED report.
2. **Read this document** (PIPELINE_BRAIN_v2.md) for current context.
3. **Check `.auto-memory/MEMORY.md`** for accumulated decisions and feedback.
4. **Query Directus** for current module statuses (via dashboard-ops skill).
5. **If any RED flags from staleness scan:** Fix before proceeding.

---

## Part 12: How to Run a Module Through the Pipeline

### Step-by-Step (for one module, e.g., M1 Tessa)

**Stage 1 — Intake:**
1. Load `intake-briefer` skill
2. Read current arc skeleton
3. Extract module data (creature, domain, spell, narrative context)
4. Create Intake Brief (`M1_TESSA_MAGIC_HANDS_INTAKE_BRIEF.md`)
5. Create/update Directus record: `current_stage=intake`, `stage_status=completed`
6. Log to `prod_activity_log`

**Stage 2 — Phase B (HARD GATE):**
1. Load `phase-b-writer` skill
2. Follow 9-step process: clinical extraction → language audit → draft script → body test → negative space → age-down → clinical cross-check → Phase A alignment → Kim review
3. Embed audio cue markers (`{{INHALE_CUE}}`, `{{EXHALE_CUE}}`, etc.) in Step 9b
4. Present script to Kim with supporting materials
5. **WAIT for Kim's explicit "approved"**
6. On approval: record in `prod_approvals`, advance to `phase_a_json`
7. On rejection: stay at `phase_b`, create blocker, log reason

**Stage 3a — Phase A Design:**
1. Load `phase-a-designer` skill
2. Create beat sheet (Guide Bird narrates, child performs)
3. Design one demo cycle with timeout fallback
4. Present to Kim for quality review

**Stage 3b — Module JSON:**
1. Load `module-json-builder` skill
2. Assemble Firestore-ready JSON from Phase A + Phase B
3. Run Q1-Q19 guardrail checks
4. Advance to `audio` stage

**Stage 3c — Narrative Generation (parallel):**
1. Load `narrative-generator` skill
2. Generate 6 aiNarrativeCache fields via Haiku
3. Validate against forbidden terms + field rules
4. Present to Kim for confirmation

**Stage 4 — Audio Production:**
1. Load `audio-producer` skill
2. Generate ElevenLabs voice stem (Myrrhin voice)
3. Kim reviews pacing
4. Run Vosk STT for cue point extraction
5. Assign breathCycle rhythms (breathing modules only)
6. ffmpeg mix: Voice (-12dB) + Ambient (-36dB) + SFX (-18 to -24dB)
7. Output: `m{N}_phase_b_complete_mix.mp3`

**Stage 5 — Listen-Through (HARD GATE):**
1. Notify Kim (Gmail MCP or in-chat)
2. Kim listens to complete audio
3. **WAIT for Kim's explicit "approved"**
4. On approval: record in `prod_approvals`, mark module complete
5. On rejection: note specific issues, return to audio-producer for fixes

---

## Part 13: Support Skills (Non-Pipeline)

These skills handle work outside the production pipeline:

| Skill | Use For |
|-------|---------|
| `cross-document-update` | Cascade decisions across canonical docs (Bible, NDU, ArcBuilder, etc.) |
| `verified-edit` | Zero-error multi-file editing (7-step per-edit protocol) |
| `pipeline-sync` | "Update the pipeline" — cascade changes to PIPELINE_BRAIN + all skill files |
| `arcbuilder` | Draft/revise arc skeletons |
| `arc-office-hours` | Interrogate arc ideas BEFORE writing briefs |
| `arc-ceo-review` | Adversarial review of completed arc briefs |
| `video-expander` | Add production detail to skeleton scenes |
| `dissertation-revision` | Edit Kim's doctoral dissertation |
| `brand-voice-guard` | Foundation layer for ALL marketing content |
| `therapist-outreach` | Cold emails, follow-ups, clinic pitches |
| `clinic-pitch` | Pitch decks, demo scripts, one-pagers |
| `website-copy` | Landing pages, feature pages, CTAs |
| `seo-blog` | Blog posts, content marketing |
| `linkedin-content` | LinkedIn posts, articles, carousels |
| `email-nurture` | Drip sequences, onboarding emails |
| `clinical-content` | White papers, CRI Theory, conference abstracts |
| `case-study` | Therapist testimonials, success stories |
| `segment-one-pager` | Audience-specific one-page sales docs |

---

## Part 14: Key File Locations

| What | Path |
|------|------|
| Project root | `Claude Mindfulnest Project Files/` |
| All skills | `.claude/skills/` (inside project folder) |
| API credentials | `Production/API_KEYS_MASTER.md` |
| Arc skeletons | `Arc Skeletons/` |
| Canonical docs | `Canon/` |
| Production assets | `Production/` |
| Audio asset library | `Claude ElevenLabs Phase B/` |
| Business docs | `Business/` |
| Memory system | `.auto-memory/` |
| Skill backups | `.claude/skills/_backups_20260411/` (51 files) |

---

## Part 15: Business Context (Quick Reference)

- **Model:** B2C. Parents pay $499 one-time for 6-month program (10 chapters). $89/mo is SUPERSEDED. Therapists get FREE access + tiered lump-sum commissions ($200-275 per family).
- **CRI Framework:** Kim's proprietary clinical framework (Competence-Rooted Identity). Instruments: CLQ (assessment), GPR (goal tracking).
- **AI Parent Coach:** Architecture A (COPPA-only, no HIPAA). 5-layer system prompt. Claude API: 60% Haiku, 30% Sonnet, 10% Opus. Cost: ~$0.29-0.58/parent/month.
- **Per-child variable cost:** ~$3.91/month (TTS + AI Coach + Firebase + materials).
- **Fixed costs:** ~$500-2,000/month.
- **Addressable therapist market:** ~180,000+ professionals (child psychologists, LCSWs, LPCs, school counselors, play therapists, etc.).

---

## Part 16: Changelog

| Date | Change | By |
|------|--------|----|
| 2026-04-11 | v1 created — initial PIPELINE_BRAIN with full pipeline context | Claude |
| 2026-04-11 | Added Part 17: Lessons Learned (contextual production lessons) | Claude |
| 2026-04-11 | Added Part 18: Infrastructure additions (locked decisions collection, iteration logging, session handoff fields) | Claude |
| 2026-04-12 | **v2 created** — Video production method updated based on April 12 testing session (Gemini 2.5 Flash, duo shot two-pass approach, reference image capacity constraints, text overlay safeguards) | Claude |
| 2026-04-13 | **v3 created** — Updated from v2 (no major changes documented in this session) | Claude |
| 2026-04-13 | **v4 created** — Added `prod_scripts` collection (unified script registry for all script types). Added 5 locked creative decisions from April 13 (Buy-In + Phase A segment, Win Sequence ordering, Guide Bird Phase A demonstrations, Phase B visual system, Myrrhin character title). | Claude |

---

## Part 17: Lessons Learned

*Contextual lessons from production sessions that don't directly modify the pipeline stages or skills, but which every future session should know. These are hard-won discoveries — each one cost real time and Kim's patience.*

### 17.1 ElevenLabs TTS — What Breaks It

**Unicode ellipsis characters (…) produce garbled speech.** Kim's scripts use `…..` and `......` for pacing. ElevenLabs interprets Unicode ellipsis (U+2026) unpredictably — "Ah, yes….. Welcome" becomes "battita welcome." The fix: convert ALL ellipses to ASCII periods, commas, or sentence breaks before TTS input. This is now a locked decision in `prod_audio_locked_decisions`.

**"child" as a placeholder sounds robotic.** Using literal "child" for `{childName}` produces unnatural TTS. Always use a realistic test name (e.g., "Emma") in TTS previews.

**Speed settings have massive impact.** Myrrhin at speed 1.0 was "wayyyy too fast." At 0.75 he was "almost comical." At 0.50 he finally sounds right — unhurried, wise, grandfatherly. These settings are locked. Don't re-test them.

### 17.2 Source Fidelity — The #1 Rule

**Never hand-retype Kim's dialogue.** When building TTS input text from the production package, extract mechanically (copy-paste from the .md file, then apply punctuation substitutions). Claude's text generation will subtly alter wording — changing "I've come to teach you" to "I have come to teach you" or similar. This violates Source Fidelity Protocol and is the single most important rule in this project.

**The mechanical extraction process:**
1. Read the production package `.md` file
2. Extract only the quoted dialogue lines (inside `> Myrrhin: "..."`)
3. Apply TTS-safe substitutions (ellipses → periods/commas, capitalize sentence openers)
4. Write to `m{N}_tts_input_v{X}_clean.txt`
5. Never touch the words themselves — only punctuation

### 17.3 Audio Delivery — What Works and What Doesn't

| Method | Status | Problem |
|--------|--------|---------|
| `computer://` links to .mp3 | ❌ BROKEN | Auto-plays in Music app, no pause/scrub |
| HTML listen-through player | ❌ BROKEN | Chrome blocks local file:// access; bash heredoc corrupts base64 |
| HTML player via Python base64 | ⚠️ WORKS in Chrome only | Doesn't render in Cowork side panel |
| **QuickTime Player via Finder** | ✅ LOCKED | Native play/pause/scrub. Open via computer-use: Finder → right-click → Open With → QuickTime Player |

**The rule:** Every time Kim needs to hear audio, open it in QuickTime Player. No exceptions. No HTML engineering. No computer:// links.

### 17.4 Parallel Execution — When It Helps and When It Kills

**Safe to parallelize:** Independent research tasks, file reads, agent queries about different topics.

**NEVER parallelize at audio stage:** When iterating on voice stems, script edits, and audio mixing, do ONE thing at a time. Verify completion. Then move to the next. This session juggled 6 parallel tasks (gong sourcing, voice stem regen, script update, HTML player, infrastructure research, counter-agents) and dropped the most critical one (Kim's script update).

**The sequential audio rule:** At the `audio` pipeline stage, strict sequential execution. The checklist on `prod_modules.session_checklist` defines the order. Complete item 1, verify with Kim, then move to item 2.

### 17.5 Session Handoff — Preventing Lost Context

**Problem:** Each new session starts with zero knowledge of prior iteration attempts, rejected settings, and Kim's feedback. This leads to re-trying settings Kim already rejected.

**Solution (now implemented):**
- `prod_activity_log` logs every TTS attempt with `voice_settings`, `script_version`, `kim_verdict`, `kim_feedback`
- `prod_audio_locked_decisions` stores rules that every session must respect
- `prod_modules.session_resumption_notes` tells the next session exactly where to pick up
- `prod_modules.session_checklist` is the ordered to-do list for the current stage

**At session start:** Read locked decisions. Read M1's resumption notes. Read the activity log for recent iterations. Don't start work until you know what's already been tried.

### 17.6 [NEW April 12] Video Generation — Gemini 2.5 Flash Still Generation

**Reference image capacity has hard limits.** Gemini 2.5 Flash can process multiple reference images, but when combined with background references, character designs degrade — especially subtle designs like Tessa's (specific shell proportions, harness details, neck length). Guide Bird survives because his design is more visually distinctive (blue bird with scarf).

**Proven approach (April 12 testing):**
- Solo character generation: 3 reference images (hero + 2 poses) = consistent, high-quality identity ✓
- Two-character sans background: 6 character reference images (3 per character) = good results ✓
- Two-character WITH background: 7 reference images total = Tessa identity breaks ✗

**Solutions identified:**
1. **Two-pass approach:** Generate Tessa solo first (Pass 1), use that output as reference to add Guide Bird (Pass 2). This distributes the reference load and preserves Tessa's identity.
2. **Reduce reference count:** Use hero-only references for one character if identity is flexible
3. **Background-first strategy:** Generate background separately, then add characters

**Cost trade-off:** Two-pass doubles per-scene cost (2× Gemini API calls per duo shot) but preserves character identity. Single-pass is cheaper but risks character degradation.

### 17.7 [NEW April 12] Skeleton vs. Beat Sheet Precision Gap

The Arc 1 skeleton provides **emotional/narrative arc**. Existing beat sheets (e.g., EVENT_1_STORY_SCENE_PRODUCTION_v1.md) provide **production-level precision**: exact camera framing per dialogue line, lighting transitions (cold-to-warm), specific visual markers (crumbling stone path, broken signpost), continuity notes.

**Real production requires beat-sheet level detail.** Generic skeleton descriptions ("Tessa crying on a rock") are insufficient. Production needs: specific emotional expressions, body poses, precise character interactions, exact environment details.

**Impact:** Only Event 1 has detailed beat sheets. Events 2-7 need beat sheet creation before scene generation. Without beat sheets, generated scenes are "in the right ballpark" but not production-ready.

### 17.8 [NEW April 12] Text Overlay — Never Use AI Generation

**CRITICAL LESSON:** Do NOT use FLUX Kontext, AI generators, or any image-to-image tool to add text overlays to generated images. This approach produced blue contamination, text baking errors, and unrecoverable artifacts in earlier testing (the "Everdale sign disaster").

**Rule:** Use PIL (Python Image Library) or ffmpeg compositing only for text overlays. Text is data — composite it programmatically, never with AI generation.

---

## Part 18: Infrastructure Additions (April 11, 2026)

### 18.1 New Directus Collection: `prod_audio_locked_decisions`

**Purpose:** Stores locked production decisions that every future session must respect. These are settings, rules, and methods that were validated through trial-and-error and should never be re-tested without Kim's explicit instruction.

| Field | Type | Description |
|-------|------|-------------|
| `id` | integer (PK) | Auto-increment |
| `decision_key` | string (unique) | Machine-readable key (e.g., `myrrhin_speed`) |
| `decision_value` | string | The locked value or rule |
| `context` | text | Why this was locked — what went wrong that led to this decision |
| `applies_to` | string | Scope: `myrrhin`, `all_modules`, `m1_tessa`, etc. |
| `locked_by` | string | `kim` or `claude` |
| `locked_at` | timestamp | When locked |
| `created_at` | timestamp | Auto-set |

**Initial seed (10 decisions from April 11):** Myrrhin voice settings (stability **0.70**, similarity_boost 0.80, style 0.20, speed **0.50**, voice_id oR4uRy4fHDUGGISL0Rev, model eleven_v3), TTS Unicode ellipsis ban, Source Fidelity extraction rule, QuickTime delivery method, sequential audio execution rule.

**Additions (April 13, 2026):** Buy-In + Phase A combined into one segment, Win Sequence comes BEFORE Resolution, Guide Bird demonstrates in ALL Arc 1 Phase A modules, Phase B uses runtime Phaser breathing circle + energy particles (not video), Myrrhin title changes from "Magical Arts teacher" to "Great Wizard".

**Usage:** At the start of any audio production session, query this collection and respect all decisions. If Kim wants to change a locked decision, update the record — don't delete it.

### 18.2 Extended Fields on `prod_activity_log`

| New Field | Type | Purpose |
|-----------|------|---------|
| `voice_settings` | JSON | TTS settings used: `{stability, similarity_boost, style, speed}` |
| `script_version` | string | Which script version was used (e.g., `v6`, `v6_clean`) |
| `kim_verdict` | string (dropdown) | `approved`, `rejected`, `needs_revision`, `pending` |
| `kim_feedback` | text | Kim's verbatim feedback on this iteration |

**Usage:** Log every TTS generation attempt. Before generating a new voice stem, query recent activity log entries for this module to see what's already been tried and what Kim said about each.

### 18.3 Extended Fields on `prod_modules`

| New Field | Type | Purpose |
|-----------|------|---------|
| `session_checklist` | JSON (array) | Ordered list of tasks for the current production stage |
| `session_resumption_notes` | text | Free-text handoff notes for the next session |

**Usage:** At session end (or at compaction risk), write the current state to these fields. At session start, read them before doing anything.

---

## Part 19: [NEW April 12] Video Production Pipeline — Still Generation

### 19.1 Still Generation — Gemini 2.5 Flash

**[UPDATED] Tool:** Gemini 2.5 Flash Image (google.genai Python library, model: `gemini-2.5-flash-image`) replaces previous approaches.

**Cost:** ~$0.039 per image

**API setup:**
```python
import google.generativeai as genai
genai.configure(api_key="<GEMINI_API_KEY>")
model = genai.GenerativeModel("gemini-2.5-flash-image")
result = model.generate_content([prompt, *reference_images], response_modalities=["IMAGE"])
```

**Reference image strategy:**
- **Per character:** 3 reference images (hero image first, then 2 variant poses)
- **HERO image first:** Always include the primary character design reference as the first image
- **For duo shots:** Use two-pass approach to preserve character identity
  - **Pass 1:** Generate primary character solo with 3 character + optional background refs (max 4 total)
  - **Pass 2:** Generate duo using Pass 1 output as new reference for primary character (3-4 refs total for secondary + Pass 1 output)

**Identity enforcement prompt language:**
- Lead with character name and key visual markers: "Tessa the turtle with orange shell, specific harness design, gentle proportions"
- Include physical descriptors from character sheet
- For background composites: "Use the background reference as location context but ensure character is fully visible and correct design"
- **Anti-blue contamination language:** "Do not tint the character blue from the background. Maintain accurate colors." (lesson from Everdale sign failure)
- **Anti-text-baking language:** "Do not render text, signs, or written words as part of the image. Any text elements must be separately composited." (lesson from text overlay failures)

**Style (locked as of April 10, 2026):** Always "Pixar 3D animated movie" style. Not painterly, not Ori aesthetic, not watercolor. Luminous, warm, cinematic lighting, soft materials.

**Contact sheet delivery:** Generate 3-4 candidates per scene and deliver as interactive HTML contact sheet for Kim review before proceeding to animation.

### 19.2 [NEW April 12] Duo Shot Two-Pass Process

**When to use:** Any scene with 2+ characters where both must have strong identity consistency.

**Process:**

1. **Identify primary and secondary characters** (e.g., Tessa = primary, Guide Bird = secondary)
2. **Pass 1 — Primary character solo:**
   - Prompt: Scene description + character emotional beat
   - References: 3 primary character refs (hero first) + optional background (max 4 total)
   - Output: Solo image of primary character in scene
3. **Pass 2 — Add secondary character:**
   - Prompt: Updated scene description including secondary character interaction
   - References: 3-4 secondary character refs (hero first) + Pass 1 output as reference for primary character positioning
   - Output: Duo image with both characters

**Why this works:** Distributes reference image load across two API calls. Pass 1 establishes primary character's pose and positioning. Pass 2 uses that as a reference instead of trying to maintain identity for two characters simultaneously with background reference competing for attention.

**Cost:** ~$0.078 per duo shot (2× Gemini calls × $0.039)

### 19.3 [NEW April 12] Text Overlay — PIL/ffmpeg Only

**RULE: NEVER use AI generation for text overlays.** Lesson from Everdale sign production failure.

**Correct approach:**
1. Generate image without text via Gemini
2. Use PIL (Python Imaging Library) to composite text programmatically:
   ```python
   from PIL import Image, ImageDraw, ImageFont
   img = Image.open("background.png")
   draw = ImageDraw.Draw(img)
   font = ImageFont.truetype("font.ttf", size=40)
   draw.text((x, y), "Text here", fill="color", font=font)
   img.save("output.png")
   ```
3. Or use ffmpeg for video text overlay if integrating with animation

**Never:**
- Feed image + text prompt to FLUX Kontext
- Use image-to-image with text prompts
- Rely on AI to bake text correctly

### 19.4 [NEW April 27] GPT Stills — gpt-4o Responses API + gpt-image-1 fallback

**Status:** Primary path activated 2026-04-27 — `gpt-4o` org verification confirmed ACTIVE via probe `POST /v1/responses` returning HTTP 200 (resolved `gpt-4o-2024-08-06`). Activity log: `prod_activity_log id=1366`. Fallback path was production-active since 2026-04-27 morning per LD `GPT_STILLS_ENDPOINT_V1`. See `LESSONS_LEARNED_April27_2026_GPT_Stills_Pipeline.md` for the 10 lessons from endpoint discovery.

**When to use vs Gemini (Part 19.1):** GPT stills are for reference-image-guided character compositing where **strict character identity** matters (Cedric, Tessa, Chipper, creature duos). Gemini 2.5 Flash is cheaper and sufficient for style-only / scene-only work where character identity is loose.

**Three paths — pick by character-identity strictness:**

| Need | Tier | Model | Endpoint | Notes |
|---|---|---|---|---|
| Strict character identity (ChatGPT-vision quality) | **Primary** | `gpt-4o` | `POST /v1/responses` (JSON) with `input_image` content blocks + `tools=[{type:image_generation}]` | Activated 2026-04-27. Code: `beat_generator.py::_openai_responses_api`. |
| Loose "inspired by" reference (scene/background exploration) | Fallback | `gpt-image-1` | `POST /v1/images/edits` (multipart, `image[]` array for refs) | Per LD `GPT_STILLS_ENDPOINT_V1`. ~$0.08–$0.20/img. |
| Text-only generation (no refs) | Last resort | `gpt-image-1` | `POST /v1/images/generations` (JSON) | Use only when refs unavailable. No `response_format` param. |

**Locked parameters:**
- `quality=high` (LD `GPT_STILLS_QUALITY_HIGH_V1`). `"standard"` is dall-e-2 vocabulary and is rejected by gpt-image-1.
- Do NOT pass `response_format` to gpt-image-1 — returns `Unknown parameter` error. gpt-image-1 always returns `data[0].b64_json`.
- `dall-e-2` is deprecated/lower-quality — never the right answer regardless of error messages from parallel sessions (Lesson 8).

**Reference image strategy (mirrors Gemini Part 19.1):**
- Per character: 3 reference images, hero image first.
- Duo shots: use Pass 1 / Pass 2 strategy from Part 19.2.
- All `_CREATURE_REFS` paths MUST `os.path.exists()` before submission — missing refs silently block the entire pipeline (Lesson 10).

**Style: same lock as Gemini** — "Pixar 3D animated movie." Anti-blue contamination + anti-text-baking prompt language still applies.

**Text overlay:** still NEVER bake via AI — use PIL/ffmpeg per Part 19.3.

**Billing pre-flight:** Auto-recharge must be ON at platform.openai.com — pay-as-you-go credit balance is separate from the monthly org budget. Negative balance rejects all calls with a misleading "monthly limit" error (Lesson 7).

**Server staleness (Rule 29):** `beat_generator.py` is imported by long-running `production_server.py`. After any edit to either, restart the server BEFORE "try it now" — verify mtime-vs-process-start. Stale server runs the old code silently for as long as it stays up.

---

## Part 20: [NEW April 12] Video Production Pipeline — Animation

### 20.1 Primary Tool: Seedance 1.5 Pro (WaveSpeed)

**[UPDATED] Status:** Reliable as primary with documented fallback.

**API:** `api.wavespeed.ai/api/v3/bytedance/seedance-v1.5-pro/image-to-video`

**Cost:** ~$0.06 per clip

**Known issue:** Intermittent "connection refused" errors due to WaveSpeed infrastructure instability. Bronze tier has 5 videos/min rate limit.

**Workaround for unreachable WaveSpeed:**
- Set timeout and retry loop (5 attempts, exponential backoff)
- If WaveSpeed unavailable after retries: switch to **fal.ai Kling 3.0** as fallback

### 20.2 Fallback Tool: Kling 3.0 (fal.ai)

**Cost:** ~$0.10 per second (more expensive than Seedance but available when WaveSpeed is down)

**When to use:** Only when Seedance API is consistently unreachable for >60 seconds

**Setup:** fal.ai account with Kling 3.0 model credentials in API_KEYS_MASTER.md

**Tool consistency rule:** Once you select a tool for a video segment (Seedance for intro, Kling for resolution), use the SAME tool for all clips in that segment. Mixing tools creates visual style inconsistency.

### 20.3 Motion Prompts

**6-step formula for Seedance motion prompts:**

1. **SUBJECT:** Character name + key visual identifiers (e.g., "Tessa turtle with orange shell and harness")
2. **ACTION:** Specific movement anatomy-appropriate to creature (e.g., "slowly extending neck from shell, blinking, looking upward")
3. **ENVIRONMENT:** Setting details from skeleton (e.g., "on rocky streamside path with water visible in background")
4. **CAMERA:** ONE camera movement only matching skeleton screen direction (e.g., "gentle camera dolly from right to left following character")
5. **STYLE:** Pixar 3D lighting + mood (e.g., "warm golden hour light, soft shadows, cozy intimate mood")
6. **CONSTRAINTS:** Duration + limitations (e.g., "5-second clip, no dialogue in video, no extra limbs, character fully visible")

**Creature-specific vocabulary:**
- **Tessa (turtle):** slow, deliberate, shell tucks, head extends/retracts, blinks
- **Luna (owl):** wing flaps, head tilts, excited hopping, expressive eyes
- **Benson (bear):** heavy footfalls, chest puffs, deliberate movements, strength
- (Extend for other creatures based on skeleton character descriptions)

---

## Part 21: [NEW April 12] TTS Audio — Per-Sentence Rendering

### 21.1 Sentence-Level Personalization

**Principle:** Only sentences containing variables are rendered per-child; universal sentences render once and are shared.

**Process:**
1. Identify each dialogue line
2. Check for personalization variables (`{childName}`, `{chosenGuideName}`, pronouns, etc.)
3. Split line at sentence boundaries
4. **For sentences WITHOUT variables:** Render once, store as universal audio
5. **For sentences WITH variables:** Render per-child at runtime via TTS API

**Example:** "Well you've come to the right place. I'm {chosenGuideName}. This is my new apprentice, {childName}."
- Sentence A: "Well you've come to the right place." → Render once (universal)
- Sentence B: "I'm {chosenGuideName}." → Render per-child (variable)
- Sentence C: "This is my new apprentice, {childName}." → Render per-child (variable)

**Cost impact:** Per-child TTS cost ~$2.82 one-time for full app (all 9 arcs, 54 modules) because most sentences are universal and shared.

### 21.2 Silence Gaps & Variable Silence Ranges

**[NEW April 12] Within-speaker silences:** 300-800ms (variable, not fixed)
- Creates natural pacing variation
- Avoids robotic uniformity
- Use random generation within range per session

**Between-speaker silences:** 600-1200ms (variable, not fixed)
- Gives listener time to process speaker change
- Conversation rhythm varies based on emotional beat

**Implemented in:** ffmpeg silence insertion via `apad` filter or manual mp3 concatenation with silence tracks

### 21.3 Character-Specific Stability Settings

**[UPDATED] Myrrhin (Phase B narrator only):**
- Stability: 0.70 (locked, do not re-test)
- Similarity boost: 0.80
- Style: 0.20
- Speed: 0.50 (locked, critical for "grandfatherly unhurried" tone)
- Voice ID: `oR4uRy4fHDUGGISL0Rev` (ElevenLabs library)

**Guide Bird + creatures:** Stability 0.30, Similarity 0.80, Style 0.30 (standard across all non-Myrrhin voices)

**Per-line emotional direction tags:** Apply to every dialogue line (e.g., `[excitedly]`, `[with relief]`, `[gently]`) to guide TTS emotional register. These are production annotations, not part of Kim's dialogue.

---

## Part 22: [NEW April 12] ffmpeg Assembly — Beat-Based Crossfades

### 22.1 Crossfade Strategy

**Within narrative beat:** Longer crossfades (0.8-1.0 seconds)
- Creates smooth emotional continuity within same scene moment
- Maintains meditative/story quality

**Between narrative beats:** Sharper crossfades (0.2-0.3 seconds)
- Marks clear transitions between scene moments
- Prevents monotony

**Implementation:**
```bash
# Example: 0.8s fade between clips in same beat
ffmpeg -i clip1.mp4 -i clip2.mp4 -filter_complex \
  "[0][1]xfade=transition=fade:duration=0.8:offset=$(duration1-0.8)" \
  output.mp4
```

### 22.2 Resolution/Framerate Normalization

**Standard output:**
- Resolution: 1920×1080 (1080p)
- Framerate: 30fps (matches most animation tools)
- Codec: h.264 with reasonable bitrate for web

**Normalize all inputs before assembly:**
```bash
# Standardize incoming video clips
ffmpeg -i input.mp4 -vf "scale=1920:1080,fps=30" -c:v libx264 output.mp4
```

---

## Part 23: [NEW April 12] Lip Sync — ByteDance (WaveSpeed)

**[UNCHANGED] Remains primary lip sync tool.** No updates from April 12 testing (solo character focus, duo-shot lip sync not tested).

**API:** `api.wavespeed.ai/api/v3/bytedance/lipsync/audio-to-video`

**Cost:** ~$0.15 per 5-second clip

**Scope:** Apply only to clips where character speaks on-screen dialogue. Skip for voice-over/narration (character not visible on screen).

---

## Part 24: Lessons Learned — Video Production (April 12, 2026)

### What's Proven

- ✓ Solo character generation (3 refs) = consistent, high-quality identity
- ✓ Two-character without background (6 refs) = good results
- ✓ Guide Bird identity is robust across scenarios
- ✓ Gemini 2.5 Flash for Pixar 3D style character stills

### What's Not Proven

- ? Two-character + background simultaneously (two-pass approach proposed but not yet tested)
- ? Specific emotional expressions in generated scenes (narrative-aligned emotion matching)
- ? Beat-sheet level precision (vs. skeleton-level scene generation)

### What Needs Work

- Lack of beat sheets for Events 2-7 (only Event 1 fully specified)
- Multi-character composition in complex backgrounds
- Narrative precision (exact emotional expressions matching character arcs)

---

*When this document changes, also update: CLAUDE.md version references, `.auto-memory/MEMORY.md` index, and any skill files that reference specific versions or stage counts.*
