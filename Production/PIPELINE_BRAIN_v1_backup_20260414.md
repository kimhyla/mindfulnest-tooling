# MindfulNest Production Pipeline Brain v1

**Last updated:** April 11, 2026
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
| `prod_phase_b_scripts` | 1 | Script versions with status |
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
| 5 | **video-producer** | "produce event", "video production" | FLUX stills → Seedance animation → ByteDance lip sync → assembly | All prior outputs + character refs | `M{N}_{CREATURE}_{SEGMENT}.mp4` |

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
| **FLUX Kontext Max** (BFL) | Pixar 3D stills | $0.08/img | `api.bfl.ai/v1/flux-kontext-max` |
| **Seedance 1.5 Pro** (WaveSpeed) | Animation | $0.06/clip | `api.wavespeed.ai/api/v3/bytedance/seedance-v1.5-pro/image-to-video` |
| **ByteDance LipSync** (WaveSpeed) | Lip sync | $0.15/5s clip | `api.wavespeed.ai/api/v3/bytedance/lipsync/audio-to-video` |
| **Claude Haiku** | Narrative gen | ~$0.01/module | Via Anthropic API |

### Cost Controls
- **Per-module audio:** ~$0.70-1.80
- **Per-scene video:** ~$0.26 (FLUX $0.08 + Seedance $0.06 + Lip sync $0.15)
- **Circuit-breaker:** $50/session threshold — stops all API calls, notifies Kim
- **WaveSpeed balance:** ~$150 (Silver tier, as of April 11)
- **BFL credits:** ~920 remaining

### Video Render Specifications

All video outputs (Story Scenes, Resolution Scenes, any exported MP4) must conform to these specs:

| Parameter | Value | Notes |
|-----------|-------|-------|
| **Aspect ratio** | **4:3** | iPad-optimized — fills iPad screens (primary device for ages 7-11), acceptable pillarbox on 16:9 desktop |
| **Resolution** | **1440x1080** (1080p 4:3) | Final delivery. Use 960x720 for drafts/previews |
| **Frame rate** | 24 fps | Matches Seedance/Kling animation output |
| **Codec** | H.264 (MP4) | Universal playback compatibility |
| **Audio** | AAC 192kbps stereo | Embedded in MP4 |

**Source image handling:** All Gemini/FLUX stills are generated at 1024x1024 (1:1). Before use in video, they must be cropped to 4:3 — this is a minimal crop (~25% vs ~44% for 16:9) since 1:1 is close to 4:3. The cropper tool (`Production/tools/build_cropper.py`) defaults to 4:3 locked aspect ratio for this purpose. Compose with character centered in safe zone (center 60% of frame) so edges can be cropped on narrower screens without losing the subject. Never stretch — always crop or pad.

**ffmpeg render command pattern:**
```
ffmpeg -i input.mp4 -vf "scale=1440:1080:force_original_aspect_ratio=decrease,pad=1440:1080:(ow-iw)/2:(oh-ih)/2" -c:v libx264 -preset slow -crf 18 -c:a aac -b:a 192k output_final.mp4
```

### TTS Emotional Rendering Method (Locked April 13, 2026)

The method for getting expressive, emotionally authentic TTS from ElevenLabs eleven_v3 is documented in `VOICE_ROSTER_LOCKED_v2.md` and the `elevenlabs-tts` skill. Two things combined make it work:

**1. Low stability setting (0.30)** — not the default 0.75+. This gives eleven_v3 room to interpret emotional tags expressively instead of rigidly sticking to the base voice tone.

| Parameter | Default Value | Character Exceptions |
|-----------|--------------|---------------------|
| `stability` | **0.30** | Bork: **0.20** (maximum theatrical pomposity). Oliver: **0.35** (consistency on longer lines) |
| `similarity_boost` | **0.80** | — |
| `style` | **0.30** | Bork: **0.40** |

**2. Inline emotional direction tags** — square brackets before the line describing the emotional *state*, not acting instructions:

```
[trying to hold back tears, embarrassed] Oh... Hi... I'm sorry. I'm Tessa.
[sympathetic, gentle] Are you OK...? What's wrong?
[quiet, carrying the weight of memory] They used to shine so bright...
```

**Key insight:** Tags describe *state* ("trying to hold back tears") rather than prescriptive acting directions ("slow down, sound vulnerable"). This distinction lets eleven_v3 naturally modulate pitch, pace, and tone.

**Pause handling:** Use `[pause]` tags between characters. SSML `<break>` tags do NOT work on eleven_v3.

**Exception: Myrrhin (narrator)** — uses different locked settings: stability **0.70**, speed **0.50** (see `prod_audio_locked_decisions` collection in Directus). Myrrhin's narrator voice is deliberately more measured and consistent than character voices.

### TTS Audition Workstation (Added April 13, 2026)

After batch TTS generation, use the **TTS Audition Player** for Kim's line-by-line review. This is a standalone HTML tool built by `Production/tools/build_tts_review.py` (NOT embedded in the storyboard — keeps Rule 6 safe).

**Features:**
- All generated MP3s embedded as base64 for instant playback
- Editable text per line (emotional tags + [pause] markers)
- **Regenerate button** — calls ElevenLabs API directly from browser (same voice settings)
- **Save to Disk button** — downloads current audio (original or regenerated) as MP3 file. After regeneration, the Save button pulses green to remind Kim to persist the new version.
- **Approve/Redo verdicts** per line, exportable to clipboard
- **Save All Approved** — batch-downloads all approved lines

**Workflow:**
1. Generate all TTS lines server-side via Python script → `Production/Event_{N}/story_scene_tts_v2/`
2. Build audition player: `cd Production/Event_{N} && python3 ../tools/build_tts_review.py --config tts_audition_config.json --output tts_audition_player_v3.html`
3. Present to Kim via `present_files` tool
4. Kim auditions each line → edits text if needed → regenerates in-browser → saves to disk
5. Kim sets approve/redo verdict per line
6. Export verdicts → log to Directus `prod_activity_log`
7. Register all approved files in `prod_visual_assets` (asset_type: "tts_audio")

**Critical:** Regenerated audio exists only in browser memory until Save to Disk is clicked. If the browser tab closes, unsaved regenerations are lost. The pulsing Save button is the safety mechanism.

**File location:** `Production/Event_{N}/tts_audition_player_v3.html`
**Builder script:** `Production/tools/build_tts_review.py` (permanent tool, config-driven)
**IMPORTANT:** Run builder from the Event directory (`cd Production/Event_{N}`) so relative audio paths in the config resolve correctly.

### Tools Available in Sandbox
- `ffmpeg` v4.4.2 (audio/video mixing)
- `python3` 3.10.12 (scripting, API calls)
- `vosk` (install via pip — speech-to-text for cue point extraction)
- `pip install --break-system-packages` for new packages

---

## Part 4B: Production Tools (Reusable)

Two self-contained Python tools live in `Production/tools/`. Both generate interactive HTML outputs with embedded media. Reusable across all arcs and events.

### build_cropper.py — Image Cropping Tool

**Location:** `Production/tools/build_cropper.py`

**Purpose:** Generate interactive HTML cropping interface with preloaded image. Kim opens in browser, draws crop boxes, names them, saves PNGs directly to Dropbox.

**CLI Usage:**
```bash
python3 Production/tools/build_cropper.py --image /path/to/image.png --title "Description" --output cropper.html
```

**Python API:**
```python
from build_cropper import build_cropper
build_cropper("/path/to/image.png", "/path/to/output.html", title="Descriptive title")
```

**Key Features:**
- Default aspect ratio: **4:3 locked** (iPad-optimized for final video output)
- Preset ratios available: 1:1, 4:3, 16:9, 9:16, Free
- Draw, move, resize crop boxes with corner handles
- Pixel-exact sidebar fields for manual adjustment
- Zoom, preview, individual or batch save
- **Save method:** Chrome download dialog (File System Access API does NOT work on file:// URLs)

**When to Use:** Whenever you generate master shots (FLUX stills, Gemini renders, AI-generated images) and need precise 4:3 crops for video input. Eliminates programmatic crop errors. Ensures Kim has visual control over framing and composition.

**Why:** Manual/programmatic crops often miss character positioning or misalign elements. Kim's visual judgment is irreplaceable for close-up framing.

### build_storyboard.py — Narrative Storyboard Generator

**Location:** `Production/tools/build_storyboard.py`

**Purpose:** Generate interactive HTML storyboard from a Python config dict (or JSON file). Embeds images and audio for reviewing narrative sequences, beat sheets, and story flow.

**Python API:**
```python
from build_storyboard import build_storyboard

config = {
    "title": "Event 1: Tessa's Fall",
    "subtitle": "Arc 1 / M1 Story Scene",
    "images": {
        "master": "/path/to/wide_shot.png",
        "closeup": "/path/to/closeup.png"
    },
    "image_labels": {
        "master": "Wide Shot",
        "closeup": "Close-up"
    },
    "audio": {
        "s1": "/path/to/audio1.mp3",
        "s2": "/path/to/audio2.mp3"
    },
    "speakers": ["Guide Bird", "Tessa", "[Stage Direction]"],
    "lines": [
        {"speaker": "Guide Bird", "text": "Are you OK?", "image": "master", "audio_key": "s1", "pause": 0.5, "section": "Setup"},
        {"speaker": "Tessa", "text": "I fell...", "image": "closeup", "audio_key": "s2", "pause": 0.3, "section": "Resolution"}
    ]
}

build_storyboard(config, "/path/to/output/storyboard.html")
```

**CLI Usage:**
```bash
python3 Production/tools/build_storyboard.py --config storyboard_config.json --output storyboard.html
```

**Key Features:**
- Dark theme, renders in any modern browser (Chrome, Safari, Firefox)
- Each line: editable textarea, speaker dropdown, image assignment dropdown with thumbnail preview
- Green play button for lines with TTS audio — click to hear; gray circle for lines without audio yet
- Pause duration slider (0-3 seconds) for pacing control
- Reorder arrows, delete button, Add Line button to extend sequence
- Play All — sequences through all lines with audio
- Export button — generates text summary of locked sequence

**Technical Details:**
- Images resized to 80px thumbnails (inline) and 200px (reference grid) via PIL
- Audio embedded as base64 data URIs — plays via native browser Audio() object
- Fully self-contained — no external dependencies beyond optional Pillow
- File size: 4 images + 5 audio clips ≈ 500-600KB HTML
- Pure DOM + ES5 syntax for maximum compatibility; works in restricted sandboxes

**When to Use:**
- Before audio production: lock narrative sequence and pacing
- During Phase A review: verify beat-sheet interactions map to dialogue
- For Kim's narrative review: see and hear the full sequence in real-time
- For shot breakdown: as reference input to visual planning and storyboarding

**Why:** Combines dialogue, timing, visual reference, and audio in one interactive view. Faster than assembling MP3s and stills separately. Lets Kim make editorial decisions (reorder lines, adjust pacing, swap images) before committing to video production.

### build_tts_review.py — TTS Audition Workstation (v3)

**Location:** `Production/tools/build_tts_review.py`

**Purpose:** Generate an interactive HTML audition workstation for line-by-line TTS review. Embeds all MP3s as base64, enables in-browser ElevenLabs regeneration, and provides Save to Disk to persist regenerated audio.

**CLI Usage:**
```bash
python3 Production/tools/build_tts_review.py \
  --config Production/Event_1/tts_audition_config.json \
  --output Production/Event_1/tts_audition_player_v3.html
```

**Config Format (JSON):**
```json
{
  "title": "M1 Event 1 — Tessa's Fall",
  "event_id": "m1_event_1",
  "api_key": "YOUR_ELEVENLABS_API_KEY",
  "model": "eleven_v3",
  "voice_settings": {"stability": 0.30, "similarity_boost": 0.80, "style": 0.30},
  "lines": [
    {
      "id": "line_02",
      "speaker": "Guide Bird",
      "voice_id": "7o9pyvsN0ob5GO6LBQp6",
      "text": "[sympathetic] Hello.... Are you OK...?",
      "audio_path": "story_scene_tts_v2/line_02_guide_bird.mp3",
      "filename": "line_02_guide_bird.mp3",
      "personalized": false
    }
  ]
}
```

**Key Features:**
- Click-to-play per line with embedded base64 audio
- Editable text per line (emotional tags + [pause] markers preserved)
- **Regenerate** — calls ElevenLabs API directly from browser with locked voice settings
- **Save to Disk** — downloads current audio (original or regenerated) as MP3; pulses green after regen to remind Kim
- **Save All Approved** — batch-downloads all approved lines
- **Approve/Redo** verdicts per line; **Export Verdicts** to clipboard for Directus logging

**Critical Data Safety:** Regenerated audio exists ONLY in browser memory until Save to Disk is clicked. If the tab closes, unsaved regenerations are lost. The pulsing Save button is the safety mechanism.

**When to Use:**
- After batch TTS generation for any event's Story Scene dialogue
- After voice roster changes that require re-auditioning
- For any line-by-line audio review where Kim needs edit/regen/approve workflow

**Reuse Pattern:** Create a `tts_audition_config.json` per event with the line data, then run the builder. The config persists — re-run builder anytime to reproduce the player.

---

## Part 4B-2: Tool Persistence Checklist (Added April 13, 2026)

When creating or upgrading ANY production tool, it is NOT done until persisted to ALL 7 locations:

1. **Permanent script** in `Production/tools/` (not /tmp, not session scratchpad)
2. **Config file** in the relevant `Production/Event_N/` directory (JSON with all parameters)
3. **PIPELINE_BRAIN section** documenting usage, CLI flags, and config format (this document, Part 4B)
4. **Relevant skill files** (video-producer, audio-producer, storyboard-producer, etc.) with step references
5. **Memory file** in `.auto-memory/reference_*.md` with usage, config, features, Directus IDs
6. **Directus registry** — tool HTML registered in `prod_visual_assets`, config registered separately
7. **Activity log** — creation logged in `prod_activity_log` with correct `action`/`details` fields (details is jsonb, NOT a string)

**Why:** April 13 — the TTS audition player was built as an ephemeral script in /tmp with no config, no memory entry, no Directus registration. Kim caught it: "it needs to be fully accessible just like the storyboard without rebuild." Fixing after the fact required touching 7+ files.

**File Delivery in Cowork Mode:** When sharing ANY file with Kim (HTML tools, documents, configs), use the `present_files` MCP tool. This is the ONLY working method. The following all FAIL: `computer://` links (404 in Cowork), Finder computer-use navigation (unreliable), Chrome MCP `file://` (blocked), raw file paths (Kim can't click them). Exception: audio files open via QuickTime Player through Finder (locked decision for audio review).

---

## Part 4C: Universal Asset Registry

**Registry Collection:** `prod_visual_assets` in Directus (mandatory prerequisite for all production tool work)

### Registration Requirement

Before building ANY production tool output (croppers, storyboards, video assembly, or visual component), query `prod_visual_assets` to:
1. Identify existing assets that can be reused
2. Prevent duplicate generation
3. Track asset lineage and versioning

All new assets — stills, animations, lip-sync clips, composite frames — MUST be registered immediately after creation with full metadata.

### Asset Lifecycle & Status Workflow

| Status | Meaning | Action |
|--------|---------|--------|
| `candidate` | Generated, awaiting review | Link to activity log entry with generation params |
| `approved` | Passed Kim's review, ready for downstream use | OK to composite into video/storyboard |
| `superseded` | Replaced by newer version | Keep for lineage tracking; do not use |
| `rejected` | Failed review or quality gate | Track reason in notes; do not use |

### Required Fields for Every Asset

| Field | Type | Example | Notes |
|-------|------|---------|-------|
| `asset_name` | text | `m1_tessa_fall_closeup_v2` | Kebab-case, version embedded |
| `file_path` | text | `/Production/Event_1/m1_tessa_fall_closeup_v2.png` | Absolute Dropbox path |
| `asset_type` | enum | `still`, `animation`, `lipsync_clip`, `composite` | Category for filtering |
| `status` | enum | `candidate`, `approved`, `superseded`, `rejected` | Current state |
| `module_id` | FK | M1 | Link to creature/module |
| `event_number` | integer | 1 | Story scene or Phase A segment |
| `dimensions_width` | integer | 1024 | Pixel width at generation |
| `dimensions_height` | integer | 1024 | Pixel height at generation |
| `aspect_ratio` | text | `1:1` | Native ratio before crop |
| `source_asset_id` | FK | (null or prior asset ID) | Parent for superseded/revised assets — traces lineage |
| `notes` | text | `Generated via FLUX Kontext, character centered, ready for 4:3 crop` | Context for future reuse |

### Workflow Integration

Reference the following docs for asset pipeline mechanics:
- **ASSET_REGISTRY_WORKFLOW_v1.md** — Intake → generation → registration → approval → downstream use
- **ASSET_REGISTRY_SKILL_CHECKLIST.md** — Pre-generation, post-generation, approval gates
- **ASSET_REGISTRY_INTEGRATION_GUIDE.md** — How to query registry from video-producer, cropper, storyboard tools

### Query Pattern (API)

```
GET /items/prod_visual_assets?filter[module_id][_eq]={M#}&filter[status][_eq]=approved&sort=-created_at
```

This returns all approved assets for a module, ordered newest first. Use to feed storyboards and video compositing.

---

## Part 4D: Image Traceability Chain (Video Production)

**Critical requirement:** Video production must resolve source images from the Directus registry, NEVER by pattern-matching filenames against Gemini stills or guessing. The registry is the single source of truth for which image file corresponds to which storyboard key.

### The Chain

1. **Cropper tool** → generates 4:3 crops from master shots, saves to `Cropper/` folder
2. **Cropper source registration** → recorded in Directus `prod_visual_assets` with:
   - `filename` = storyboard image key (e.g., `tessa_closeup_4x3.png`)
   - `filepath` = full Cropper source path (e.g., `Cropper/tessa_sad_closeup_4x3_final.png`)
3. **Storyboard builder** → uses `filename` as thumbnail key in HTML
4. **Video pipeline** → resolves full-resolution source via `filepath` from registry lookup

### The Rule

**Do NOT:**
- Guess at which Gemini/FLUX stills correspond to a storyboard key
- Pattern-match filenames against a Gemini stills folder (100+ images per shot, wrong matches likely)
- Hard-code image paths in video scripts

**DO:**
- Query `prod_visual_assets` with the storyboard image key
- Retrieve the `filepath` from the registry record
- Use that filepath (relative to project root) to load the source file

### Registry Query Pattern

```
GET /items/prod_visual_assets?filter[filename][_eq]={STORYBOARD_KEY}&fields=filename,filepath,asset_type,status
```

Example: to find the source for `tessa_closeup_4x3.png` in M1E1, query:
```
GET /items/prod_visual_assets?filter[filename][_eq]=tessa_closeup_4x3.png
```

Response yields one record with:
```json
{
  "filename": "tessa_closeup_4x3.png",
  "filepath": "Cropper/tessa_sad_closeup_4x3_final.png",
  "asset_type": "crop_4x3",
  "status": "approved"
}
```

### Image Paths

Source files are relative to the project root:

```
/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/{filepath}
```

If `filepath` = `Cropper/tessa_sad_closeup_4x3_final.png`, the full path is:

```
/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Cropper/tessa_sad_closeup_4x3_final.png
```

### Image Map Export

The storyboard builder's `--export-image-map` flag generates a JSON mapping file suitable for use by downstream tools (video-producer, narrative-generator, etc.):

```
python3 Production/tools/build_storyboard.py --export-image-map storyboard.html --output image_map.json
```

Output format:
```json
{
  "module_id": 1,
  "event_number": 1,
  "images": [
    {
      "storyboard_key": "tessa_closeup_4x3.png",
      "registry_filepath": "Cropper/tessa_sad_closeup_4x3_final.png",
      "line_number": 5,
      "dialogue": "Tessa says..."
    }
  ]
}
```

### Validation Requirements

Before video production, the pipeline must verify that every storyboard image key resolves to:

1. **Registry presence:** A record in `prod_visual_assets` with `filename` = storyboard key
2. **File existence on disk:** The `filepath` points to a file that exists and is readable
3. **Minimum dimensions:** The file is ≥ 400px on its shortest dimension (ensures 4:3 crops filled adequately)

Validation script (in video-producer or pipeline.py):
```bash
# For each storyboard image key
GET registry for filename = key
IF NOT FOUND → FAIL with "Image key {key} not in registry"
IF FOUND → filepath = response.filepath
IF NOT EXISTS on disk → FAIL with "Source file {filepath} missing"
IF dimensions < 400px → FAIL with "Source too small: {dimensions}px"
```

### Why This Matters

On April 13, 2026, a video production attempt used hardcoded filename guesses to map storyboard keys to Gemini stills. The Gemini stills folder contains 100+ images per shot (variations, lighting, expressions). Guessing which one corresponds to "tessa_closeup_4x3.png" would have produced the WRONG images in the final video—either a wide shot when a close-up was intended, or a different creature entirely.

The registry-based resolution (single source of truth) prevents this entirely. Every storyboard key has exactly one registered source, and that source is verified to exist and meet dimensions before video production begins.

### Storyboard Builder Registry Integration

The storyboard builder (build_storyboard.py) already integrates with the registry:

```
python3 Production/tools/build_storyboard.py --registry --module 1 --event 1 --output storyboard.html
```

In `--registry` mode, the builder:
1. Queries `prod_visual_assets` for all approved images in M{N} 
2. Uses `filename` as the HTML image key
3. Validates each image exists on disk (using `filepath`)
4. Embeds the `filepath` in HTML comments for downstream use

Video-producer, narrative-generator, and other tools can extract the `filepath` from the HTML comments and use it directly without additional registry queries.

### Crop Registration Workflow

**Automated crop handling:** When Kim crops images using the HTML cropper tool, the workflow automatically registers crops in Directus and places them in the `Cropper/` folder.

**Flow:**
1. **Cropper save:** Kim draws crop boxes in the HTML cropper and clicks "Save". The cropper calls the Directus API to pre-register the crop with:
   - `filename` = storyboard key (e.g., `tessa_closeup_4x3.png`)
   - `width`, `height` = actual crop dimensions
   - `module_id`, `asset_type` = metadata
2. **Finalize step:** After Kim finishes cropping, Claude runs `finalize_crops.py`:
   ```bash
   python3 Production/tools/finalize_crops.py --source Downloads/ --dest Cropper/ --update-registry
   ```
   This script:
   - Locates downloaded crops in the Mac's Downloads folder
   - Validates dimensions against the 600px minimum (same as Layer 2 gate)
   - Moves crops to the `Cropper/` folder
   - Updates the Directus `filepath` field to point to the final location
3. **Registry update:** The `filepath` field is now accurate, and video-producer can query it directly.

**Old workflow (deprecated):**
- Manual copy of crops from Downloads to `Cropper/`
- Manual registration in Directus via browser dashboard
- Error-prone, required explicit instruction each time

**New workflow (automated):**
- Cropper pre-registers on save (pre-entry into registry)
- `finalize_crops.py` handles file placement + registry update
- Crops are ready for video production immediately after finalization

**Files:**
- `Production/tools/build_cropper.py` — Cropper tool with Directus pre-registration on save
- `Production/tools/finalize_crops.py` — Moves downloaded crops to `Cropper/`, updates registry filepaths

---

### Image Dimension Enforcement (3-Layer)

**Requirement:** All crop-type assets must have shortest side ≥ 600px. Enforced at three independent layers to prevent undersized images from reaching video production.

**Minimum rationale:** Seedance (video animation tool) requires ≥400px, but 600px provides headroom for iPad display scaling and prevents visible upscaling artifacts in final delivery.

**Layer 1 — Cropper UI (Soft Warning)**
- Live dimension display in `build_cropper.py` as user draws crop boxes
- Yellow "Too Small" warning when shortest side < 600px
- **Does NOT block saves** — informational only, respects Kim's visual judgment
- Flag appears while user crops; can be ignored if intentional

**Layer 2 — Directus Registration Gate (Hard Enforcement)**
- Shared validation module `Production/tools/asset_validation.py`
- `validate_crop_dimensions()` checks all registered crops at intake time
- `register_visual_asset()` rejects registration of crops below 600px
- Undersized crops CANNOT enter `prod_visual_assets` registry
- Any attempt to bypass returns explicit error: "Source dimensions {W}x{H} below minimum 600px"

**Layer 3 — Video Pipeline Auto-Upscale (Safety Net)**
- `Production/tools/produce_event1.py` and downstream video tools auto-detect undersized assets
- Auto-upscales via Lanczos interpolation to temp directory (preserves quality better than naive scaling)
- Logs upscale event to `prod_activity_log` with before/after dimensions
- **Safety net only** — intended for legacy data, not normal flow

**Session-Start Audit:**
Use `asset_validation.audit_registry_dimensions()` during session init (as part of dashboard-gate protocol):
```python
from asset_validation import audit_registry_dimensions
audit_registry_dimensions()  # Queries prod_visual_assets, flags undersized crops, returns report
```

Output: JSON report with:
- Count of assets by dimension range (OK ≥600px | WARNING 400-599px | CRITICAL <400px)
- List of at-risk module IDs and asset names
- Recommended fixes (regenerate, crop tighter, or log upscale if legacy)

**Files:**
- `Production/tools/asset_validation.py` — core validation logic (reused by all production tools)
- `Production/tools/build_cropper.py` — Cropper UI layer, `--min-dimension 600` default
- `Production/tools/produce_event1.py` — video pipeline auto-upscale fallback
- `Production/tools/asset_validation.py::register_visual_asset()` — call this instead of direct Directus writes

### Master Image Resolution Requirements

**Requirement:** Master establishing frames (multi-character establishing shots) must be generated at **2048×2048 minimum** to support high-quality cropping.

**Why:** MindfulNest uses a "single master → crop close-ups" approach for character consistency. One establishing frame is generated at high resolution, then individual character close-ups are cropped from it. This ensures all characters look identical across shots.

The PROBLEM: if a master image is only 960×960, tight character close-ups cropped from it will be undersized (e.g., 503×377), violating the 600px minimum for video production. The crops cannot be larger because there aren't enough pixels in the source.

The SOLUTION: generate master frames at 2048×2048. This provides ample pixels for tight 4:3 close-up crops while maintaining the 600px minimum.

**Anti-pattern (do NOT do this):** Generate separate per-character close-up stills at high resolution to avoid the cropping constraint. This destroys character consistency — the entire reason the single-master approach exists.

**Tools supporting 2048×2048:**
- Gemini 2.5 Flash (`--size 2048x2048` option)
- FLUX Kontext (`resolution: 2048x2048`)

**Workflow:**
1. Generate one 2048×2048 master establishing frame with all characters in scene
2. Crop tight character close-ups from the master using the Cropper tool (4:3, 600px+ minimum per character)
3. Register all crops in `prod_visual_assets`

**Module data notation:** When specifying master image resolution in module specs or production briefs, use:
```
Master establishing frame: 2048×2048 (required for character consistency + cropping)
```

This rule ensures that downstream close-ups will have sufficient resolution and that all instances of a character across a scene have pixel-perfect consistency.

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

**Last updated:** April 11, 2026

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
2. **Read this document** (PIPELINE_BRAIN_v1.md) for current context.
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

**Initial seed (10 decisions):** Myrrhin voice settings (stability **0.70**, similarity_boost 0.80, style 0.20, speed **0.50**, voice_id oR4uRy4fHDUGGISL0Rev, model eleven_v3), TTS Unicode ellipsis ban, Source Fidelity extraction rule, QuickTime delivery method, sequential audio execution rule.

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

*When this document changes, also update: CLAUDE.md version references, `.auto-memory/MEMORY.md` index, and any skill files that reference specific versions or stage counts.*
