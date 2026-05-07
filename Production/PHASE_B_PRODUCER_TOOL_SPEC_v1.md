# Phase B Producer Tool — Specification v1

**Status:** DRAFT — pending 4+4 agent review and Kim approval
**Authored:** April 17, 2026
**Author:** Claude (under zero-error-qa + no-shortcuts skill discipline)
**Phase 0 Preflight:** `prod_preflight_reviews` id=44 (PHASE_B_PRODUCER_TOOL_SPEC-20260417)
**Supersedes:** Nothing
**Related:** `audio-producer/SKILL.md`, `video-producer/SKILL.md`, `storyboard-producer/SKILL.md`, `render_phase_b_v9_meditation.py`, `compose_phase_b_poc.py`, `lipsync_sender.py`

---

## 0. TL;DR

Build a local Flask web app (`localhost:5112/phase-b-producer`) with four stages in one interface:

1. **Script + Pauses** — single-beat editor, per-sentence pause annotation, ElevenLabs preview
2. **Audio Render + Standard Wrap** — one button produces final MP3 (voice stem + gong + bed + outtro, all baked in)
3. **LipSync** — one button sends audio + Myrrhin master to ByteDance, retrieves lipsync'd video
4. **Illustration Timeline** — drag iron-framed library illustrations onto scrubber, set crossfades, render final composited POC

Compose existing `audio-producer` + `video-producer` skills via imported Python modules. No new skills. Not CLI. Not YAML. Not storyboard extension.

**Variables per module (Kim edits):** script, pauses, library picks, overlay timeline.
**Constants baked in (Kim never touches):** voice settings, bed, gong, outtro, frame, mascot, overlay position, crossfade duration.

---

## 1. Problem Statement

### 1.1 Today's pain
M1 Magic Hands Phase B took a full day with heavy iteration:
- Markdown-based pause annotation (confusing, had to be redone three times)
- Audio speed tuning via manual A/B (four samples)
- Frame style picking (four candidates generated, one picked)
- White-background → frame → iron-frame iteration (three composition attempts v3/v4/v5)
- Audio stitching (three passes: little_one splice, bed overlay, gong/outtro stitch)
- LipSync (two submissions; first polling failure required direct-query + download)
- Manual Directus registration at the end

### 1.2 Multiply by 54
53 more modules remain (M2-M54). Same pipeline shape every time. Without a tool, expect ~1 day × 53 = ~53 days of Kim-session time. With a tool, target: ~2 hours per module × 53 = ~14 days, most of it Kim's listen-through waiting.

### 1.3 What to standardize
The 80% that repeats:

| Constant | Value |
|---|---|
| Myrrhin voice | ID `oR4uRy4fHDUGGISL0Rev`, stability 0.70, sim_boost 0.80, style 0.20, speed 0.50, model `eleven_v3` |
| Ambient bed | `Claude ElevenLabs Phase B Module Sounds/ambient bed pretty option.mp3`, looped, volume -12dB, fade 4s in/out |
| Gong intro | First 2s of `m1_phase_b_test_mix_v3.mp3` (or extracted standalone gong) |
| Outtro | Last 8s of `m1_phase_b_test_mix_v3.mp3` (or `sfx/outtro1.mp3`) |
| Iron frame | `frame_options/frame_iron_banded_wood.png` (Kim-approved April 17 PM) |
| Mascot anchor | `locked_heroes_v2/CHARACTER_mascot_v1_boy_watercolor.png` |
| Overlay position | Upper-left (24, 24) on 800×480 Myrrhin video |
| Crossfade duration | 1.5s between library frames |

### 1.4 What to vary per module
- **Script text** (approved from `phase-b-writer` skill → `prod_scripts`)
- **Per-sentence pause durations** (new field: `pause_annotation` JSONB in `prod_scripts`)
- **Library illustrations** (drawn from shared library; new ones generable via in-tool button when unique poses needed)
- **Overlay timeline** (which illustration shows up when, crossfade at each transition)
- **Optionally:** alternate Myrrhin master video (hat/outfit variants — deferred to post-M2)

---

## 2. Goals & Non-Goals

### 2.1 Goals
- G1. Reduce Kim's per-module decision count from ~324/54 = 6 intervention classes to 4 (script, pauses, library picks, timeline)
- G2. Eliminate manual stitching / ffmpeg / Python-editing loops
- G3. Full Rule 18 (Locked Decision Auto-Registration) compliance
- G4. Full Rule 15 (Reference Docs Registry Sync) compliance
- G5. Zero error paths left open (Rule 19)
- G6. Modularize today's scripts (no duplicated logic between tool and standalone scripts)
- G7. Output byte-identical POC videos given identical inputs (reproducibility)

### 2.2 Non-Goals
- NG1. Does NOT replace `audio-producer` / `video-producer` skills — composes them
- NG2. Not a general-purpose video editor — Phase B-specific
- NG3. Does NOT handle Phase A in v1 (may extend later)
- NG4. Not batch-processing — one module per session per `audio-producer` Rule 5
- NG5. Not touching the existing `phase-b-writer` workflow (script stays upstream)

---

## 3. Architecture

### 3.1 Dependency-ordered layer stack

```
┌──────────────────────────────────────────────────────┐
│  Layer 0 — Infrastructure (no deps)                  │
├──────────────────────────────────────────────────────┤
│  Layer 1 — Stage 1: Script + Pauses                  │
│  ↑ depends on Layer 0 + ElevenLabs API               │
├──────────────────────────────────────────────────────┤
│  Layer 2 — Stage 2: Audio Render + Wrap              │
│  ↑ depends on Layer 1 data + audio-producer modules  │
│    + standard asset library                          │
├──────────────────────────────────────────────────────┤
│  Layer 3 — Stage 3: LipSync Wrapper                  │
│  ↑ depends on Layer 2 MP3 + lipsync_sender.py        │
│    + WaveSpeed API                                    │
├──────────────────────────────────────────────────────┤
│  Layer 4 — Stage 4: Illustration Timeline            │
│  ↑ depends on Layer 3 video + framed library +       │
│    compose_phase_b_poc.py modules                    │
└──────────────────────────────────────────────────────┘
```

Each layer ships independently. Stage 1 is usable the moment Layer 1 is done, even while Layers 2-4 are in progress. This is both dependency order AND incremental-value order.

### 3.2 Service architecture

- **Framework:** Flask (Python 3.9+)
- **Port:** `localhost:5112` (existing storyboard uses 5111 — this is the sibling port)
- **Binding:** `127.0.0.1` only — no external traffic
- **Entry point:** `Production/tools/phase_b_producer_server.py`
- **Static assets:** `Production/tools/phase_b_producer_web/{css,js,templates}/`
- **State:** all persistent in Directus; local files are ephemeral artifacts
- **Authentication:** Directus service account credentials from `Production/API_KEYS_MASTER.md` at startup
- **Startup contract:** verifies Directus connectivity + API key validity BEFORE accepting requests (fail fast)

### 3.3 Module modularization (pre-Layer-0 work)

Today's scripts become importable modules:

```
Production/tools/phase_b_pipeline/
├── __init__.py
├── audio.py          ← from render_phase_b_v9_meditation.py
├── compose.py        ← from compose_phase_b_poc.py
├── framing.py        ← from apply_iron_frame.py
├── library_gen.py    ← from generate_library_openai.py
├── lipsync.py        ← wraps existing lipsync_sender.py
└── constants.py      ← all the "Constant baked in" values from §1.3
```

Public API surface each module exposes (called by Flask route handlers):
- `audio.render_sentence(text, voice_settings) → Path`
- `audio.concat_with_pauses(segments: list[(Path, float)], out: Path) → Path`
- `audio.stitch_with_standard_wrap(voice_stem: Path, out: Path) → Path`
- `compose.render_final(lipsync_video, timeline, out) → Path`
- `framing.apply_iron_frame(src, dst) → Path`
- `library_gen.generate(module, pose_slug) → Path`
- `lipsync.submit_and_wait(video, audio, out) → dict`

Each function raises explicit exceptions on failure — no silent returns of `None`.

### 3.4 Data model

#### 3.4.1 Existing Directus collections (no schema changes)
- `prod_modules` — module state
- `prod_scripts` — approved Phase B scripts
- `prod_audio_assets` — rendered audio files
- `prod_visual_assets` — illustrations, frames, lipsync videos, final composites
- `prod_locked_decisions` — per Rule 18
- `prod_activity_log` — per Rule 17
- `prod_preflight_reviews` — per Rule 19 Phase 0

#### 3.4.2 New Directus collection: `prod_phase_b_sessions`

Tracks one row per module's production session. Fields:

| Field | Type | Notes |
|---|---|---|
| id | int PK | |
| module_id | int FK→prod_modules | |
| status | enum | `not_started` / `stage1_in_progress` / `stage1_complete` / ... / `stage4_complete` / `approved` |
| script_id | int FK→prod_scripts | |
| pause_annotation_json | json | Per-sentence pause durations |
| voice_stem_asset_id | int FK→prod_audio_assets | Stage 2 output |
| final_audio_asset_id | int FK→prod_audio_assets | Stage 2 wrapped output |
| lipsync_job_id | string | WaveSpeed job ID (for debugging) |
| lipsync_video_asset_id | int FK→prod_visual_assets | Stage 3 output |
| timeline_json | json | Stage 4 overlay timeline |
| final_poc_asset_id | int FK→prod_visual_assets | Stage 4 output |
| kim_verdict | enum | `pending` / `approved` / `rejected` |
| kim_feedback | text | |
| created_at, updated_at | timestamp | |

#### 3.4.3 New field on `prod_scripts`: `pause_annotation`

Add JSONB field. Populated by Stage 1 when Kim saves. Schema:
```json
{
  "sentences": [
    {
      "id": "s01",
      "text": "Ah, yes. Welcome little one...",
      "pause_after_ms": 3000,
      "cues": ["{{BELL_CUE}}"]
    },
    ...
  ],
  "cut_beats": ["s10", "s12"],
  "split_from_original": {"s03a": "s03", "s03b": "s03"}
}
```

---

## 4. Layer-by-Layer Details

### 4.1 Layer 0 — Infrastructure

**Responsibilities:**
- Flask app scaffolding
- Directus client (reuse patterns from `dashboard-ops` skill)
- Startup health check (fails fast if Directus unreachable or API key invalid)
- Session management (one active module session at a time per `audio-producer` Rule 5)
- Shared HTML skeleton (navigation: Stage 1 → 2 → 3 → 4)
- Error handler that logs full stack trace to `prod_activity_log` and surfaces user-friendly message
- `GET /health` endpoint for monitoring

**Files:**
- `Production/tools/phase_b_producer_server.py` — Flask app
- `Production/tools/phase_b_producer_web/templates/base.html` — layout + nav
- `Production/tools/phase_b_producer_web/static/{styles.css,client.js}` — shared UI

### 4.2 Layer 1 — Stage 1: Script + Pauses

**UI:**
- Module selector dropdown (queries `prod_modules` where `phase_b_status=approved`)
- Script display: parse from `prod_scripts.content`, split into sentences on `{{PAUSE:Xs}}` / `{{CUE}}` / `{{BELL_CUE}}` markers
- Per-sentence row:
  - Editable text field (Kim can split/tweak/cut)
  - Pause-after input (numeric, seconds, default inherited from `{{PAUSE:Xs}}` if present)
  - ▶ Preview button (renders single sentence via ElevenLabs, plays inline)
  - Action buttons: Split, Cut, Merge with next
- Save button — persists `pause_annotation_json` to `prod_scripts`

**Backend endpoints:**
- `GET /api/stage1/script/<module_id>` — returns parsed sentences + existing annotations
- `POST /api/stage1/preview` — renders single sentence, returns audio URL
- `POST /api/stage1/save/<module_id>` — persists annotation, creates `prod_phase_b_sessions` row if new

**Rule 18 compliance:**
- On save, write a `prod_locked_decisions` entry with key `PHASE_B_M{N}_PAUSE_ANNOTATION` AND a `prod_activity_log` entry (two-write)

### 4.3 Layer 2 — Stage 2: Audio Render + Standard Wrap

**UI:**
- Shows Stage 1 sentences + pauses (read-only) + total estimated duration
- Single button: "Render voice stem + wrap"
- Progress indicator (per sentence: rendered / pending)
- On completion: audio player with the final MP3

**Backend:**
- Iterates sentences, calls `audio.render_sentence(...)` for each
- Calls `audio.concat_with_pauses(...)` to assemble voice stem
- Calls `audio.stitch_with_standard_wrap(...)` which prepends gong, layers bed, appends outtro — all from `constants.py`
- Registers the voice stem and final MP3 in `prod_audio_assets`
- Updates `prod_phase_b_sessions.status = stage2_complete`

**Error handling (Rule 19):**
- ElevenLabs HTTP 4xx → retry once with same body → if fails, log to `prod_blockers` + surface exact HTTP error to Kim
- ElevenLabs HTTP 5xx → retry 3x with exponential backoff
- ffmpeg stderr non-empty → preserve stderr to `session.ffmpeg_last_error` + halt stage
- Missing standard assets (gong/bed/outtro) → halt at startup health check, not at render time

### 4.4 Layer 3 — Stage 3: LipSync Wrapper

**UI:**
- Shows Stage 2 MP3 + Myrrhin master video preview
- Dropdown: Myrrhin variant (default / hat / outfit1 / outfit2 — initially just default)
- Single button: "Send to LipSync"
- Status panel: submitted / polling / downloading / complete / failed
- Retry button on failure
- On completion: lipsync'd video player

**Backend:**
- `POST /api/stage3/submit/<module_id>` — calls `lipsync.submit_and_wait(...)`
- Uses existing `Production/tools/lipsync_sender.py` robustness
- ADDS: direct-query fallback when polling times out (we learned this today) — if `poll_until_done` times out, directly query the `predictions/{id}/result` endpoint and download if status=completed

**Rule 19 compliance:**
- WaveSpeed timeout ≠ permanent failure — handle gracefully with direct-query
- Download failure → preserve the output URL in session, allow Kim to retry download
- Retry budget: 3 total submit attempts per module before halting

### 4.5 Layer 4 — Stage 4: Illustration Timeline

**UI:**
- Top: lipsync'd video player with scrubber (HTML5 `<video>` + timeline bar)
- Left sidebar: library panel
  - Tabs: Hand library / Body library / Mascot / Orb / Other
  - Each illustration shows thumbnail (iron-framed)
  - "+ Add new" button at each library's top → invokes Layer-0's library-gen flow (new modal with pose prompt + reference)
- Timeline track below video:
  - Drag illustration onto track → creates clip at drop point
  - Clip has resize handles (adjust start/end)
  - Crossfade duration between adjacent clips (default 1.5s, adjustable)
  - "Play preview" button plays composited result inline (ffmpeg rendered to temp file)
- Save timeline button → persists `timeline_json` to session
- Render final POC button → calls `compose.render_final(...)` with approved timeline

**Library tagging:**
- Shared library (all modules) visible by default
- Module-specific additions stored with `module_id` tag
- Filter toggle: "Show only this module's custom additions"

**Rule 18 compliance:**
- Timeline save → `prod_locked_decisions` entry `PHASE_B_M{N}_TIMELINE_APPROVED`
- Final POC render → `prod_activity_log` entry with full pipeline summary + cost

---

## 5. Governance Compliance

### 5.1 Rule 19 (No Shortcuts) checklist

| Scenario | Response |
|---|---|
| ElevenLabs API 429 (rate limit) | Back off per `Retry-After`, resume |
| ElevenLabs API 4xx (bad input) | Surface error to Kim verbatim, halt |
| ElevenLabs API 5xx | Retry 3× exponential backoff, then log + halt |
| WaveSpeed submit fail | Retry once, then log + halt with job ID preserved |
| WaveSpeed poll timeout | Direct-query `/predictions/{id}/result`, download if completed |
| WaveSpeed job fails | Log to `prod_blockers`, surface to Kim |
| ffmpeg fails | Preserve stderr, preserve intermediate files, halt |
| Directus write fails | Queue to `pending_directus_writes.json` on disk, retry next session start |
| Missing expected asset | Halt at startup, not mid-render |
| User cancels mid-render | Clean up temp files, preserve session state |

**No silent failures.** Every halt path surfaces the exact error to Kim via the UI.

### 5.2 Rule 18 (Auto-Registration)

Decisions logged:
- `PHASE_B_M{N}_PAUSE_ANNOTATION` — on Stage 1 save
- `PHASE_B_M{N}_AUDIO_APPROVED` — on Stage 2 Kim listen-through approval
- `PHASE_B_M{N}_LIPSYNC_APPROVED` — on Stage 3 Kim approval
- `PHASE_B_M{N}_TIMELINE_APPROVED` — on Stage 4 save
- `PHASE_B_M{N}_POC_APPROVED` — on final approval

Every "approve" action in the UI → two-write: `prod_locked_decisions` POST + `prod_activity_log` POST.

### 5.3 Rule 15 (Reference Docs Sync)

- Tool source code registered in `prod_reference_docs` on initial deployment
- New library illustrations registered in `prod_visual_assets` at generation time
- Spec document itself registered at approval time

### 5.4 Rule 17 (Skill-Embedded Governance)

Not a skill, but the tool will have a governance checklist embedded at startup:
- Load `Production/governance/phase-b-producer-tool_governance.md` at server startup
- Verify all constants (bed path, gong path, frame path, Myrrhin master) exist on disk
- Verify Directus collections exist and have the expected fields
- Fail fast with clear errors if anything is missing

---

## 6. Testing Strategy

### 6.1 Smoke tests
Each layer exposes `--smoke-test` invocation:
- Layer 0: Flask starts, Directus reachable, all constants present
- Layer 1: Render one test sentence, save dummy annotation
- Layer 2: Render minimal 2-sentence voice stem, wrap with bed
- Layer 3: Submit 5-second dummy audio to LipSync (costs ~$0.15)
- Layer 4: Compose 10-second dummy video with 2 illustrations

### 6.2 Golden path test
Re-run M1 through the tool. Compare outputs to today's manual POC v5/v6 — byte-identical expected.

### 6.3 Per-module validation
Before marking a module's POC as complete:
- Check audio duration matches timeline duration ±0.5s
- Check all timeline clips reference existing library assets
- Check Directus rows are populated (no null FKs where required)

---

## 7. Deployment & Security

- **Host:** Kim's Mac, localhost only
- **Port:** 5112
- **No external traffic:** all generations hit external APIs (OpenAI/ElevenLabs/WaveSpeed), but the tool's UI is not exposed
- **API keys:** loaded at startup from `Production/API_KEYS_MASTER.md`, never hardcoded, never logged
- **File uploads:** sanitized paths, no arbitrary file access outside project root
- **Session persistence:** across server restarts via Directus (no in-memory state loss)

---

## 8. Migration from Today's State

### 8.1 Today's artifacts
- `render_phase_b_v9_meditation.py` → refactor into `phase_b_pipeline.audio`
- `lipsync_sender.py` → keep as-is, import from `phase_b_pipeline.lipsync`
- `compose_phase_b_poc.py` → refactor into `phase_b_pipeline.compose`
- `apply_iron_frame.py` + `remove_white_backgrounds.py` → refactor into `phase_b_pipeline.framing`
- `generate_library_openai.py` → refactor into `phase_b_pipeline.library_gen`

### 8.2 M1 data migration
- Import M1's session into `prod_phase_b_sessions` as the reference record
- Import M1's pause annotations into `prod_scripts.pause_annotation` field
- Import M1's timeline into `prod_phase_b_sessions.timeline_json`
- Link the existing M1 POC v6 (once rendered) as `prod_phase_b_sessions.final_poc_asset_id`

### 8.3 Build order
Session N: Layer 0 + modularization (~1 day)
Session N+1: Layer 1 (~1 day)
Session N+2: Layer 2 (~0.5 day)
Session N+3: Layer 3 (~0.5 day)
Session N+4: Layer 4 (~1.5 days)

**Total:** ~4.5 focused sessions. Kim uses Stage 1 immediately after session N+1 for M2 script work.

---

## 9. Open Questions

### OQ1. Alternate Myrrhin backgrounds
Kim mentioned: "we can alternate myrrhin backgrounds occasionally, or just change up his outfit or his hat." How many initial variants? Generation via OpenAI or manual?
**Proposed default:** start with `default` only. Add `hat_winter` + `outfit_summer` after M4. Each variant = one LipSync master video stored in `prod_visual_assets`.

### OQ2. New-illustration generation
Does the tool include an OpenAI-generation "Add to library" button (Stage 4), or is library growth a separate workflow?
**Proposed default:** include in-tool. Modal form: pose description + reference image selector. Calls `library_gen.generate(...)`. Output auto-framed and added to library.

### OQ3. Phase A support
Extend audio-producer simultaneously to cover Phase A with `--type phase_a` flag?
**Proposed default:** out of scope for v1. Phase A is much shorter (~30-60s), simpler audio (no bed), different composition. Tackle separately after Phase B tool is proven.

### OQ4. Multi-user / concurrent sessions
Do we need to lock a module session so two Claude sessions can't edit the same module simultaneously?
**Proposed default:** yes — `prod_phase_b_sessions.lock_token` field, Flask server obtains lock on session open, releases on close. Stale locks expire after 1 hour.

---

## 10. What I'm NOT Doing

- NOT building in this spec-writing session
- NOT assuming approval of the 4 open questions — they're called out for Kim's decision
- NOT touching any existing skill's SKILL.md
- NOT claiming this spec is complete — agents will review next and surface gaps
- NOT making any Directus schema changes yet (will happen only when coding Layer 0)

---

## 11. Next Steps

1. **Spawn 4 advocate + 4 counter-agent review** of this spec (this session)
2. Synthesize review feedback into `PHASE_B_PRODUCER_TOOL_SPEC_v2.md`
3. Kim reviews v2, approves or requests changes
4. On approval: register v2 in `prod_reference_docs`, create Directus collection `prod_phase_b_sessions`, begin Layer 0 in next session
