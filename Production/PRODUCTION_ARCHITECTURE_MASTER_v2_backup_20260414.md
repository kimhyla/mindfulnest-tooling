# MindfulNest Production Architecture — Master Reference
**Version:** 2.0  
**Date:** April 14, 2026 (v2: Two-Write Rule + QA validators)  
**Purpose:** Complete description of the production tool ecosystem, pipeline flow, lessons learned, and prescriptive architecture for all future tools. This document is the authoritative reference for any Claude thread doing production work.

---

## Part 1: What Exists Today

### 1.1 The Four Production Tools

MindfulNest has four self-contained HTML production tools, each built by a Python builder script. All four share the same architectural DNA:

**Shared Pattern:** Python builder reads a manifest/config → encodes assets as base64 data URIs → generates a single self-contained HTML file with embedded CSS, JS, and assets → HTML uses localStorage for state persistence → user makes selections/edits in-browser → exports decisions as JSON → builder auto-registers the output in Directus.

| Tool | Builder Script | Lines | Purpose | Input | Output |
|------|---------------|-------|---------|-------|--------|
| **Storyboard** | `build_storyboard.py` | 1,427 | Edit dialogue, assign images per line, lock sequence | Lines JSON + Directus registry images | Locked Sequence JSON |
| **Cropper** | `build_cropper.py` | 797 | Crop master image into 4:3 close-ups | Single PNG image | PNG crop files |
| **TTS Audition** | `build_tts_review.py` | 655 | Review TTS audio, regenerate in-browser, approve/redo | Config JSON (lines + audio paths + ElevenLabs key) | Verdicts text + MP3 files |
| **Animation Review** | `build_animation_review.py` | 1,424 | Compare up to 3 animated clips per beat, select winner | Beats manifest JSON (clips + audio per beat) | Picks JSON (beat → clip number) |
| **Image Selector + Cropper** | `build_image_selector_cropper.py` | ~900 | Browse masters, select per module/event, crop 4:3 close-ups | Directus registry query or image paths | Crop manifest JSON + PNG crops |

**Total codebase:** ~5,200 lines across 5 builders, with approximately 70% duplication in HTML scaffolding, CSS theming, localStorage patterns, credential reading, and Directus registration hooks.

### 1.2 Shared Infrastructure

**Directus Dashboard (20 collections):** System of record. Every tool auto-registers its output in three places:
1. `prod_visual_assets` — asset metadata (filename, path, type, status, module, event)
2. `prod_modules` — tracking fields per tool (e.g., `storyboard_status`, `storyboard_version`, `storyboard_built_at`, `storyboard_build_mode`)
3. `prod_activity_log` — audit trail entry (action, details JSON, timestamp)

**API_KEYS_MASTER.md:** Central credential store for ElevenLabs, Runway, WaveSpeed, FLUX Kontext, fal.ai, Replicate, Segmind, EvoLink, Directus, and Railway.

**PIPELINE_BRAIN_v1.md:** Single source of truth for the full production pipeline — stages, skills, APIs, safety mechanisms, module data, and step-by-step walkthrough.

### 1.3 How the Tools Cascade

The tools form a production chain. Each tool's output feeds into the next:

```
Master Image Generation (Midjourney/Ideogram/Gemini)
    │
    ▼
┌─────────────┐     ┌──────────────┐
│  CROPPER     │────▶│  Directus    │  (crops registered as crop_4x3 assets)
│  build_      │     │  Registry    │
│  cropper.py  │     └──────┬───────┘
└─────────────┘            │
                           ▼
                ┌─────────────────┐     ┌──────────────┐
                │  STORYBOARD     │────▶│  Locked      │
                │  build_         │     │  Sequence    │
                │  storyboard.py  │     │  JSON        │
                └─────────────────┘     └──────┬───────┘
                                               │
                           ┌───────────────────┘
                           ▼
                ┌─────────────────┐     ┌──────────────┐
                │  TTS AUDITION   │────▶│  Approved    │
                │  build_         │     │  Voice Stems │
                │  tts_review.py  │     │  (.mp3)      │
                └─────────────────┘     └──────┬───────┘
                                               │
                           ┌───────────────────┘
                           ▼
┌─────────────────────────────────────────┐
│  Animation Generation (Kling v3/EvoLink) │
│  generate_animation_options.py           │
└──────────────────┬──────────────────────┘
                   ▼
                ┌─────────────────┐     ┌──────────────┐
                │  ANIMATION      │────▶│  Winning     │
                │  REVIEW         │     │  Clips +     │
                │  build_         │     │  Picks JSON  │
                │  animation_     │     └──────┬───────┘
                │  review.py      │            │
                └─────────────────┘            │
                                               ▼
                                    ┌──────────────────────┐
                                    │ ByteDance LatentSync │
                                    │   (lip sync)         │
                                    └──────────┬───────────┘
                                               │
                                               ▼
                                    ┌─────────────────┐
                                    │  FFmpeg Assembly │
                                    │  → Final Video   │
                                    └─────────────────┘
```

### 1.4 What Does NOT Exist Yet

Based on comprehensive audit, these pipeline stages currently have **no dedicated tool**:

1. ~~**Image Reference Selection Tool**~~ — **BUILT (April 14, 2026).** `build_image_selector_cropper.py` combines image browsing/selection with 4:3 cropping in one unified HTML tool. Queries Directus registry, embeds all masters, Kim selects and crops on one screen. Registered as Directus asset ID 78.

2. **Transition/Cut-Point Editor** — No tool for controlling how clips join together (cuts, fades, crossfades, trim points). See Part 4 for the recommended approach.

3. **Preview/Rough-Cut Viewer** — No tool for previewing the assembled sequence before final ffmpeg render. Kim currently watches the final render in QuickTime.

4. **Automated TTS Pipeline** — `pipeline.py` has placeholder functions (`_step_tts()` and `_step_voice_stem()`) that print "Not yet implemented." TTS generation currently requires the audio-producer skill in Cowork.

5. **Lip-Sync Assembly Tool** — ByteDance LatentSync is called via API but has no dedicated review/approval tool.

---

## Part 2: Lessons Learned (19 Core Rules)

Compiled from 25+ memory files, 6 months of production work, and 10+ failed approaches. These rules are battle-tested and non-negotiable.

### Category 1: File & Asset Safety

**Rule 1 — Never Edit HTML Directly.** Base64 strings truncate silently in text editors. Always use the Python builder (Path A) or JS-only patches via Python (Path B). Direct HTML editing is forbidden. (Source: 5 production failures on April 13, 2026)

**Rule 2 — Never Guess Image Mappings.** The video pipeline must resolve images from the Directus registry, never by filename pattern-matching. Kim's selections may not match any filename on disk — she may have cropped, composited, or hand-selected images that exist only in embedded data. (Source: 7/11 wrong image assignments in a storyboard rebuild)

**Rule 3 — Export Before Rebuild.** Kim's browser edits (drag-drop image assignments, dialogue changes) live in localStorage, NOT in the HTML file on disk. Before any rebuild, ask Kim to click "Export Locked Sequence." Rebuilding from a stale disk file = silent data loss. (Source: April 13 image scrambling incident)

**Rule 4 — Version-Up, Never Overwrite.** Every new version gets a new filename (v2 → v3). Never write over an existing version. The previous version is always recoverable. (Source: March 5-6 data loss incident)

**Rule 5 — Preserve All Authored State.** Any rebuild must preserve ALL state — dialogue, images, selections, pauses, ordering, and metadata. If unsure whether a rebuild will lose state, default to a JS-only patch. When in doubt, patch; don't rebuild. (ROOT PRINCIPLE)

### Category 2: Visual Production

**Rule 6 — Single Master Crop Approach.** Crop close-ups from one 2048×2048 master image for character consistency. Never generate separate per-character stills — this destroys consistency and defeats the purpose of the master-cropping workflow.

**Rule 7 — Minimum 600px Shortest Side.** All crop-type assets must have shortest side ≥600px. Enforced at 3 layers: Cropper UI warning (soft), Directus registration gate (hard), pipeline auto-upscale fallback (safety net).

**Rule 8 — No Freeze Frames.** When audio duration exceeds clip duration, use multi-clip extension. Never freeze-frame — it looks broken and destroys the illusion of life.

**Rule 9 — Never Automate Midjourney.** Web UI automation is unreliable and violates ToS. Use API-based generators (Ideogram, Gemini, FLUX Kontext) instead.

**Rule 10 — 4:3 Aspect Ratio for Crops.** All cropped close-ups must be 4:3 to fill the screen in final video (iPad-optimized viewing).

### Category 3: Audio & TTS

**Rule 11 — Low Stability for Expressiveness.** ElevenLabs eleven_v3 with stability 0.30 + inline emotional state tags (e.g., `[sympathetic]`, `[excited]`) produces expressive, natural-sounding output. High stability sounds robotic.

**Rule 12 — Audio Opens in QuickTime.** All audio for Kim's review MUST be opened in QuickTime Player via Finder (right-click → Open With → QuickTime Player). Never use `computer://` links (auto-play, no pause) or HTML players (break in Cowork). Locked decision.

### Category 4: Pipeline & Workflow

**Rule 13 — Dashboard-First.** Query Directus BEFORE any production work (7-query session start protocol). Log activity AS YOU GO. The dashboard is the system of record, not a reporting tool.

**Rule 14 — Read Existing Docs Before Generating.** Kim has hundreds of hours of strategic work in project documents. Ignoring them and starting from scratch wastes time and produces wrong answers. Always search and read first.

**Rule 15 — Follow Production Order.** Read spec docs and present priority order BEFORE touching tools. Don't chase exciting work — follow the pipeline stages in order.

**Rule 16 — Open Files For Kim.** Use Finder computer-use to open files directly. Never tell Kim a file path — she shouldn't have to navigate to anything.

**Rule 17 — Verify File Before User Opens.** Confirm content is correct + use Finder to open. Never assume browser tab state.

### Category 5: Tool Persistence

**Rule 18 — 7-Location Persistence.** Every production tool must exist in all 7 locations: (1) Production/tools/ script, (2) Production/Event_N/ config/manifest, (3) PIPELINE_BRAIN section, (4) Skill file reference, (5) .auto-memory/ file, (6) Directus prod_visual_assets, (7) prod_activity_log entry.

**Rule 19 — Auto-Registration Hooks.** Every builder must auto-register its output in Directus after a successful build. The root cause of "invisible files" (files on disk but unknown to the dashboard) was builders that created files without telling the dashboard.

---

## Part 3: The Universal Container Pattern

### 3.1 Problem Statement

The 4 tools have 70% code duplication: dark-theme CSS, localStorage patterns, export panels, credential reading, base64 encoding, Directus registration hooks, and CLI argument parsing are all reimplemented in each builder. This means:
- Bug fixes must be applied 4 times
- New features (e.g., auto-save improvements) must be built 4 times
- Inconsistencies accumulate (e.g., animation review requires `--register` flag while storyboard auto-registers)

### 3.2 Proposed Architecture

```
Production/
├── base.py              # BaseHTMLBuilder class (~400 lines)
├── api_client.py        # DirectusClient class (~300 lines)
├── assets.py            # Shared encode_image/audio/video (~100 lines)
├── tools/
│   ├── build_storyboard.py    # StoryboardBuilder(BaseHTMLBuilder) (~600 lines)
│   ├── build_cropper.py       # CropperBuilder(BaseHTMLBuilder) (~350 lines)
│   ├── build_tts_review.py    # TTSReviewBuilder(BaseHTMLBuilder) (~300 lines)
│   ├── build_animation_review.py  # AnimReviewBuilder(BaseHTMLBuilder) (~500 lines)
│   └── [future tools inherit from BaseHTMLBuilder]
└── pipeline.py          # Orchestrator
```

### 3.3 BaseHTMLBuilder Responsibilities

The base class provides:
- **HTML scaffold:** DOCTYPE, meta, CSS reset, dark theme, responsive grid
- **Asset management:** `embed_asset()`, `embed_assets_batch()` using shared encoding
- **localStorage pattern:** Canonical key generation, auto-save on edit, load on DOMContentLoaded
- **Export pattern:** Standard "Export JSON" panel with Copy to Clipboard + Download buttons
- **Feature metadata:** Embedded HTML comment with version, tool name, generated_at, feature flags — replaces brittle regex extraction
- **CLI framework:** Standard argparse with `--title`, `--subtitle`, `--module-id`, `--event-number`, `--smoke-test`, `--audit`, `--output`
- **Registration:** `register_in_directus()` using shared DirectusClient — auto-fires after every build
- **Audit/regression:** `extract_features()` and `compare_features()` using embedded metadata (not regex)

### 3.4 DirectusClient Responsibilities

Shared API client:
- Credential reading from API_KEYS_MASTER.md with env var fallback
- Token caching (15-min TTL)
- `register_visual_asset()` — POST/PATCH prod_visual_assets
- `patch_modules()` — update tracking fields
- `log_activity()` — POST to prod_activity_log
- `query_visual_assets()` — registry queries for image/clip lookup
- `smoke_test()` — connectivity and schema verification

### 3.5 Migration Strategy

**Phase 1 (2-3 hours):** Build base.py, api_client.py, assets.py with tests.
**Phase 2 (3-4 hours):** Refactor storyboard builder first (gold standard, most complex). Verify no regressions with --audit-previous.
**Phase 3 (2-3 hours):** Refactor remaining 3 builders. Each should drop 40-60% of code.
**Phase 4 (1 hour):** Update PIPELINE_BRAIN, skills, and memory files.

**Critical safety:** Every refactored builder must pass `--audit-previous` against its pre-refactor output. If any feature is lost, the refactor is rejected and the old builder is restored.

---

## Part 4: Transition & Cut-Point Architecture (Design Debate Synthesis)

### 4.1 The Problem

When animated clips are assembled into a final video, there is currently no control over how they join. Clips are simply concatenated. This creates:
- Jarring cuts when a character is mid-gesture at clip boundary
- No distinction between within-segment transitions (same scene) and between-segment transitions (narrative shift)
- No special treatment for Phase B entry/exit (meditation requires a calm transition)
- The "looking away" problem (some animation clips end with the character turning away from camera, making the cut to the next clip visually jarring) — continuation clips sometimes end with the character turning away

### 4.2 Recommended Approach: Hybrid Layered System

After evaluating 5 competing proposals (timeline editor, preset dropdowns, preview-first assembly, convention-only, hybrid), the recommended approach layers three solutions at different timescales:

**Layer 1 — Convention-Based Defaults (ship immediately, ~2 hours):**

Embed a hardcoded transition grammar into the ffmpeg assembly script. Zero UI, zero decisions for Kim:

| Boundary Type | Transition | Duration |
|---------------|-----------|----------|
| Within segment (beat to beat) | Hard cut | 0ms |
| Between segments | Crossfade | 500ms |
| Into Phase B (meditation entry) | Fade to black → hold → fade in | 1500ms + 500ms hold + 1500ms |
| Out of Phase B (meditation exit) | Same pattern reversed | 1500ms + 500ms hold + 1500ms |
| Story Scene opening | Fade from black | 1000ms |
| Map Return ending | Fade to black | 1000ms |
| Audio at segment boundaries | Crossfade | 300ms overlap |

Auto-trim logic: If a clip is flagged as having a bad ending (the "looking away" problem), automatically trim 0.5s (12-15 frames) from the tail before applying transitions.

**Layer 2 — Per-Beat Override Controls (extend animation review, ~6 hours):**

Add a collapsed "Transition" panel to each beat in the animation review tool:
- Default: "Auto" (uses Layer 1 convention)
- Overrides: Cut / Fade 0.5s / Fade 1.0s / Crossfade 0.5s / Crossfade 1.0s
- Only visible when Kim expands a beat's detail view
- Yellow indicator shows when an override differs from the auto default
- Export JSON includes `transition_override` field per beat

The ffmpeg assembly script reads overrides and applies them, falling back to Layer 1 conventions for any beat left on "Auto."

**Layer 3 — Preview Assembly Tool (Phase 2, post-M1, ~16 hours):**

A new HTML tool that assembles a rough-cut preview in-browser before final render:
- Loads winning clips + audio from animation review export
- Applies Layer 1 conventions + Layer 2 overrides
- Plays preview in-browser (Web Audio + canvas compositing or WASM ffmpeg)
- Kim marks problem spots (timing, transitions, clips needing trim)
- Generates correction manifest that feeds back into ffmpeg
- Final render only runs ONCE, on approved content

### 4.3 Why This Layered Approach Wins

- **Respects M1 timeline:** Layer 1 takes 2 hours and requires zero new UI
- **Builds incrementally:** Each layer adds capability without breaking the previous one
- **Matches Kim's role:** She's a narrative designer, not a video editor. Conventions handle 90% of cases; the dropdown handles the remaining 10%; the preview catches errors before expensive renders
- **No false choices:** Convention AND control, on different schedules

---

## Part 5: Complete Module Production Flow

### 5.1 The Six Segments — Two Categories

Every module consists of 6 segments. The critical insight is that these segments fall into **two fundamentally different production categories**:

**Category A — Pre-Rendered Video (produce NOW with existing tools):**

| # | Segment | Content | Duration | Production |
|---|---------|---------|----------|------------|
| 1 | **Story Scene** | Animated narrative — creature discovery, emotional hook, conflict | 60-90s | Full video pipeline: storyboard → crops → TTS → animation → lip sync → ffmpeg |
| 5 | **Resolution** | Emotional payoff, creature thanks child, party celebration | 30-45s | Same full video pipeline |

**Category B — Runtime-Composed (produce AUDIO NOW, finish visuals/interaction AFTER app architecture is locked):**

| # | Segment | Audio Production (now) | Visual/Interactive (later) |
|---|---------|----------------------|--------------------------|
| 2 | **Buy-In / Phase A** | Guide Bird TTS voice stems | Runtime React component — `phaseAConfig` JSON drives interaction. Child taps to trigger demo, watches Guide Bird demonstrate. Format depends on app architecture. |
| 3 | **Phase B** | Myrrhin TTS narration + ambient bed + gong/bell triggers + breathCycle cue points | Runtime Phaser breathing circle + energy particles. Each technique gets its Stone color: orange/M1 Body-Sensing, yellow/M2 Now-Watching, red/M4 Kindness, blue/M6 Calm-Breathing, green/M3 Courage, purple/M5 Self-Grounding. NOT video. Composited live on device, synced to audio cue markers. Visual is a "peek anchor" — audio carries the therapeutic load. |
| 4 | **Win** | Coin/reward sound effects, creature celebration audio | UI animation config — coins rain, spell card, decoration item. Format depends on app architecture. |
| 6 | **Map Return** | Creature dialogue TTS (tappable sprites) | Sprite positioning, map state changes, zone features. Entirely runtime. |

### 5.2 Production Sequence (Locked Decision)

**The correct production order is:**

1. **Produce full video** for Story Scene and Resolution — these are pure pre-rendered narrative video. The existing 4 tools (storyboard, cropper, TTS audition, animation review) handle this end-to-end.

2. **Produce audio only** for Buy-In, Phase A, Phase B — all voice stems, ambient beds, sound design, cue points. Register everything in Directus with clear asset types so it's ready when needed.

3. **Build the app** — lock the runtime architecture (React components, Phaser scenes, data schemas, game engine decisions).

4. **Finish Buy-In / Phase A / Phase B** — wire the already-produced audio into whatever component/scene architecture the app uses. Build any visual/interactive production tools needed at that point, informed by the actual app architecture rather than guessing.

**Why this order:** Audio assets are format-agnostic. An MP3 is an MP3 regardless of whether Phase A renders as a React component, a Phaser scene, or something else entirely. But interactive/visual configs are tightly coupled to the app's runtime engine. Designing production tools for those before the engine exists would risk creating conflicts, wasted work, or worse — constraining the app architecture to fit premature tooling decisions.

**App Development Tools:** The app side (React components, Phaser scenes, game engine, database) may be built using AI app builders like Lovable, Cursor, or similar tools. The production sequence deliberately decouples audio asset creation from app architecture decisions, so audio can be produced now regardless of which app development approach is chosen later.

### 5.3 Full Video Pipeline (Story Scene + Resolution)

**Stage 1: Image Selection & Cropping**

```
Kim browses generated images (Midjourney, Ideogram, Gemini, FLUX Kontext)
    │
    ▼  (Manual: Kim picks favorites, tells Claude which to use)
    │
Master images saved to Production/Event_N/images/
    │
    ▼
build_cropper.py → Cropper HTML (one per master image)
    │
    ▼  Kim crops 4:3 close-ups in browser (≥600px enforced)
    │
    ▼  Saves PNGs → auto-registered in Directus as crop_4x3
    │
Crops available in Directus registry for storyboard
```

**Stage 2: Storyboard Assembly**

```
Lines JSON (dialogue, speakers, sections, pauses)
    +
Directus registry images (master + crops)
    │
    ▼
build_storyboard.py --registry --module M1 --event 1
    │
    ▼  Storyboard HTML with drag-drop image assignment
    │
    ▼  Kim reviews: edits dialogue, drags images, adjusts pauses
    │
    ▼  "Export Locked Sequence" → locked_sequence.json
    │
    ▼  Auto-registered in Directus (storyboard_status=built)
    │
Locked sequence is source of truth for all downstream work
```

**Stage 3: TTS Voice Generation**

```
Locked sequence JSON → extract lines needing TTS
    +
ElevenLabs voice profiles (from prod_voice_profiles)
    +
Emotional state tags added to text (e.g., [sympathetic], [excited])
    │
    ▼
build_tts_review.py → TTS Audition HTML
    │
    ▼  Kim reviews each line: Play, Approve, or Redo
    │
    ▼  In-browser regeneration (calls ElevenLabs API directly)
    │
    ▼  "Save to Disk" for approved takes → .mp3 files
    │
    ▼  "Export Verdicts" → verdicts text for activity log
    │
    ▼  Auto-registered in Directus (tts_audition_status=built)
    │
Approved MP3 voice stems ready for animation + mixing
```

**Stage 4: Animation Generation**

```
Approved crops (from Directus registry)
    +
Approved voice stems (.mp3 from Stage 3)
    │
    ▼
generate_animation_options.py (EvoLink API / Kling v3)
    │  Generates up to 3 animation variants per beat
    │  ~$0.375 per 5-second clip, 27 credits per generation
    │  If none of the 3 options work: re-run for that beat to get 3 more
    │
    ▼
build_animation_review.py → Animation Review HTML
    │
    ▼  Kim compares up to 3 options per beat side-by-side
    │
    ▼  Selects winner per beat (click checkbox)
    │
    ▼  If no option works: tell Claude "none work for beat 7, generate more"
    │
    ▼  "Export Picks" → picks.json (beat → clip number)
    │
    ▼  Auto-registered in Directus (animation_review_status=built)
    │
Winning clips ready for lip-sync and assembly
```

**Stage 5: Lip-Sync & Assembly**

```
Winning animation clips (from picks.json)
    +
Approved voice stems (.mp3)
    │
    ▼
ByteDance LatentSync (via WaveSpeed/fal.ai API)
    │  Applies lip movement to match audio
    │
    ▼
Transition conventions applied (Layer 1 grammar)
    +
Any Layer 2 overrides from animation review export
    │
    ▼
FFmpeg assembly script
    │  Concatenates clips with transitions
    │  Mixes audio (voice + ambient bed + bells/gongs)
    │  Outputs final segment video
    │
    ▼
Kim reviews in QuickTime Player
    │
    ▼  Approve → advance to next segment
    │  Reject → identify problem → re-run specific stage
```

### 5.4 Audio-Only Production (Buy-In / Phase A / Phase B)

These segments get their audio produced now. Visual/interactive production waits for the app architecture.

**Buy-In + Phase A Audio:**

```
Locked dialogue from skeleton (Guide Bird lines)
    │
    ▼  ElevenLabs TTS (Guide Bird voice profile)
    │  Emotional state tags: [confident], [encouraging], [excited]
    │
    ▼  TTS Audition tool → Kim approves each line
    │
    ▼  Approved MP3 stems registered in Directus
    │     asset_type: "tts_audio"
    │     segment: "buy_in" or "phase_a"
    │     status: "approved"
    │
    ▼  PARKED — waiting for app architecture to determine
    │  how these audio files get wired into the runtime
    │  React component / interactive experience
```

**Phase B Audio (full production — this IS the primary experience):**

```
Phase B Script (approved .docx with cue markers)
    │
    ▼  Clinical extraction: technique steps, breathCycle timing
    │
    ▼  Language audit: spell names only, no clinical jargon
    │
    ▼
TTS Generation (Myrrhin voice, ElevenLabs)
    │  Low stability (0.30) for warmth
    │  Speed 0.50 for meditation pacing
    │
    ▼
Vosk STT cue-point extraction
    │  Maps precise timestamps for breathing cues
    │
    ▼
breathCycle rhythm assignment
    │  Inhale/exhale timing per cue point
    │
    ▼
Audio mixing (ffmpeg multi-track)
    │  Voice stem + ambient bed + gong/bell triggers
    │
    ▼  Kim listen-through in QuickTime
    │
    ▼  Approved mix registered in Directus
    │     asset_type: "phase_b_audio"
    │     status: "approved"
    │     breathCycle data saved alongside
    │
    ▼  PARKED — visual side (Phaser breathing circle + particles)
    │  waits for app architecture. The breathing circle is NOT video.
    │  It's a runtime Phaser scene that syncs to the breathCycle
    │  cue points from this audio. Format depends on app engine.
```

### 5.5 Human Decision Points

| Gate | Segment | Tool | Decision | Blocking? |
|------|---------|------|----------|-----------|
| **Image Selection** | Story Scene / Resolution | Finder (manual) | Which master images to use | Yes |
| **Storyboard Lock** | Story Scene / Resolution | Storyboard (Export Locked Sequence) | Dialogue, image assignments, pauses | Yes |
| **TTS Approval** | All segments | TTS Audition (Export Verdicts) | Voice quality per line | Yes |
| **Animation Pick** | Story Scene / Resolution | Animation Review (Export Picks) | Best clip per beat (re-generate if none work) | Yes |
| **Listen-Through** | Story Scene / Resolution / Phase B | QuickTime Player | Final assembled audio/video quality | Yes |

---

## Part 6: Building Future Tools — Prescriptive Checklist

### 6.1 Before Writing Any Code

1. Check if an existing tool can be extended (Layer 2 approach) before building something new
2. Read PIPELINE_BRAIN for the current pipeline state
3. Query Directus for the module's current stage and any locked decisions
4. Verify the proposed tool doesn't duplicate functionality that already exists

### 6.2 Architecture Requirements (Non-Negotiable)

Every new production tool MUST:

- [ ] **Inherit from BaseHTMLBuilder** (once the universal container is built) or follow the same patterns
- [ ] **Embed assets as base64 data URIs** — self-contained HTML, no external fetch calls
- [ ] **Use localStorage for state persistence** with canonical key: `mindfulnest_{tool_name}_{title_slug}`
- [ ] **Include Export JSON functionality** — Copy to Clipboard + Download as JSON buttons
- [ ] **Embed metadata in HTML comment** — version, tool name, generated_at, feature flags
- [ ] **Auto-register in Directus (Two-Write Rule)** — after every successful build, write to BOTH the relevant asset collection (`prod_visual_assets` or `prod_audio_assets`) AND `prod_activity_log`. Single-write registration is a silent failure. No manual `--register` flag.
- [ ] **Support `--smoke-test` mode** — verify Directus connectivity and input file existence
- [ ] **Support `--audit` mode** — extract feature manifest from built HTML
- [ ] **Support `--audit-previous` mode** — regression check against prior version
- [ ] **Graceful credential fallback** — read from API_KEYS_MASTER.md with env var fallback, warn clearly if neither exists
- [ ] **Dark theme** — consistent with all other tools (background #1a1a2e, cards #16213e, accent #0f3460)
- [ ] **Mutual exclusion on playback** — only one audio/video plays at a time across the entire tool

### 6.3 Persistence Checklist (7 Locations)

After building any new tool, verify it exists in ALL 7 locations:

1. `Production/tools/{builder_script}.py` — the Python builder
2. `Production/Event_N/{manifest_or_config}.json` — the input data for the tool
3. `Production/PIPELINE_BRAIN_v1.md` — documented in the pipeline reference
4. `.claude/skills/{relevant_skill}/SKILL.md` — referenced in the appropriate skill
5. `.auto-memory/reference_{tool_name}.md` — memory file for future sessions
6. Directus `prod_visual_assets` — registered with asset_type and status
7. Directus `prod_activity_log` — build action logged with full details

### 6.4 CLI Convention

All builders should follow this pattern:

```bash
# Primary build mode
python3 build_{tool}.py --manifest input.json --output tool.html \
  --title "Title" --subtitle "Subtitle" \
  --module-id 1 --event-number 1

# Directus connectivity check
python3 build_{tool}.py --smoke-test

# Feature extraction
python3 build_{tool}.py --audit existing_tool.html

# Regression check
python3 build_{tool}.py --audit-previous new.html old.html
```

### 6.5 Two-Path Protocol Compliance

**Path A (structural changes):** Run the Python builder. Required for adding/removing/replacing assets, changing data structure, modifying HTML skeleton.

**Path B (behavior-only fixes):** JS-only patch via Python script. Read HTML, patch ONLY `<script>` or `<style>` blocks, write new version. MUST verify all base64 data is byte-identical before/after.

**FORBIDDEN:** Direct HTML editing, base64 injection, hand-writing HTML replacements, generating HTML from scratch without the builder.

### 6.6 Testing Protocol

Before delivering any tool to Kim:

1. Run `--smoke-test` — verify Directus auth works
2. Run `--audit` on the built HTML — verify expected features exist
3. If replacing a previous version: run `--audit-previous` — verify no feature regressions
4. Open in Chrome — verify assets load, playback works, export works
5. Check file size — warn if >50MB (browser may struggle)
6. Verify Directus registration — query `prod_visual_assets` to confirm the entry exists
7. Run QA validators on output — `pipeline.py --validate /path/to/output` checks file integrity, format compliance, and Tier 1/Tier 2 thresholds. Kill switch: `--skip-validators` if blocking during development. See `Production/validators/` for the full suite.

---

## Part 7: What To Build Next (Priority Order)

**Note on batching (April 14, 2026):** The SPEED-* optimization decisions (18 entries in Directus `prod_session_decisions`) establish arc-level batching by work type for M2-M6. However, M1 remains the **pilot module** — it follows the module-by-module priorities below to prove the pipeline before batching begins. The SPEED-* batching workflow (all Phase Bs → all images → all audio → all listen-throughs) kicks in for the remaining 5 modules after M1 is complete. See `.auto-memory/project_speed_optimization_plan.md` for the full batching schedule.

### Phase 1: Finish M1 Pre-Rendered Video (Story Scene + Resolution)

**Priority 1a: Transition Convention Layer (Layer 1)**
- **Effort:** 2 hours
- **What:** Add transition grammar to ffmpeg assembly script
- **Why:** Unblocks M1 Story Scene video assembly with professional-quality transitions

**Priority 1b: Complete M1 Story Scene video assembly**
- **What:** Lip-sync → transitions → ffmpeg assembly → Kim listen-through
- **Why:** This is the next concrete deliverable in the pipeline

**Priority 1c: Produce M1 Resolution video**
- **What:** Same full pipeline (storyboard → crops → TTS → animation → assembly) for the Resolution segment
- **Why:** Second pre-rendered segment for M1

### Phase 2: Produce Audio for All Remaining Segments

**Priority 2a: Buy-In + Phase A audio**
- **What:** TTS voice stems for all Guide Bird lines in Buy-In and Phase A
- **Why:** Audio is format-agnostic — produce it now, wire it into the app later
- **Store:** Register in Directus as `tts_audio` with segment tags, parked for app integration

**Priority 2b: Phase B audio (full production)**
- **What:** Myrrhin TTS → Vosk cue extraction → breathCycle → ambient bed + gong → ffmpeg mix
- **Why:** Phase B audio IS the primary therapeutic experience. Produce it completely.
- **Store:** Register mix + breathCycle data in Directus, parked for Phaser visual integration

**Priority 2c: Win / Map Return audio**
- **What:** Celebration sound effects, creature dialogue TTS for map sprites
- **Store:** Register in Directus, parked for app integration

### Phase 3: Build the App

**Priority 3: App architecture decisions**
- **What:** Lock the runtime engine (React components, Phaser scenes, data schemas, game mechanics)
- **Why:** Everything in Phase 4 depends on knowing how the app renders interactive/runtime content
- **This is NOT a production tool task** — it's app development

### Phase 4: Finish Interactive Segments (After App Architecture Is Locked)

**Priority 4a: Wire Buy-In / Phase A audio into app**
- **What:** Connect produced audio to whatever React component / interactive format the app uses
- **Build:** Any production tools needed for Phase A configs, informed by actual app architecture

**Priority 4b: Wire Phase B audio + visuals**
- **What:** Connect produced audio + breathCycle data to Phaser breathing circle + particles
- **Build:** Phaser scene config tools, informed by actual engine

**Priority 4c: Win + Map Return integration**
- **What:** Connect audio to UI animation configs, sprite dialogue systems

### Ongoing (Can Happen Anytime)

**Universal Container Refactor**
- **Effort:** 8-10 hours (phased)
- **What:** BaseHTMLBuilder + DirectusClient + assets.py, refactor all 4 builders
- **Why:** Cuts maintenance by 60%, ensures consistency. Not blocking anything, but improves all future work.

**Transition Override UI (Layer 2)**
- **Effort:** 6 hours
- **What:** Per-beat transition dropdown in animation review tool
- **When:** After Layer 1 conventions have been tested on M1 Story Scene

**Preview/Rough-Cut Tool (Layer 3)**
- **Effort:** 16 hours
- **What:** In-browser preview assembly before final ffmpeg render
- **When:** Post-M1, after the production pattern is proven

---

## Part 8: Integration Patterns & Data Flow Standards

### 8.1 Export JSON Schema Convention

All tools should export decisions in a consistent schema:

```json
{
  "tool": "animation_review",
  "version": 1,
  "module_id": "M1",
  "event_number": 1,
  "exported_at": "2026-04-14T12:00:00Z",
  "decisions": {
    "beat_1": { "selected": "option_A", "transition": "auto" },
    "beat_2": { "selected": "option_B", "transition": "fade_500ms" }
  },
  "metadata": {
    "total_beats": 11,
    "complete": true,
    "duration_estimate_ms": 42000
  }
}
```

### 8.2 Directus Asset Types (Registered)

| asset_type | Tool Source | Description |
|------------|-----------|-------------|
| `storyboard_html` | build_storyboard.py | Interactive dialogue/image editor |
| `cropper_html` | build_cropper.py | 4:3 crop tool for master images |
| `tts_audition_tool` | build_tts_review.py | Voice stem review + regen |
| `animation_review_html` | build_animation_review.py | Multi-clip comparison picker |
| `crop_4x3` | Cropper output | Individual crop PNG files |
| `tts_audio` | TTS generation | Voice stem MP3 files |
| `animation_clip` | EvoLink/Kling generation | Animated MP4 clips |
| `source_image` | Midjourney/Ideogram/etc. | Master images before cropping |
| `sequence_json` | Storyboard export | Locked sequence data |
| `production_tool` | Various | Utility scripts and configs |

### 8.3 Dashboard Tracking Fields Per Tool

Every tool has 4 tracking fields on `prod_modules`:

```
{tool}_status:     not_started | built | approved | needs_rebuild
{tool}_version:    integer (increments on each build)
{tool}_built_at:   ISO timestamp
{tool}_build_mode: registry | config | manual | pipeline
```

Current tools with tracking: storyboard, cropper, tts_audition, animation_review.

---

## Part 9: Safety Mechanisms Summary

| Mechanism | Purpose | Enforcement |
|-----------|---------|-------------|
| **Two-Path Protocol** | Prevents HTML corruption | CLAUDE.md Rule 7, all skills |
| **Export-First Rebuild** | Prevents losing Kim's browser edits | Pre-rebuild gate question |
| **--audit-previous** | Catches feature regressions | Blocking check on every rebuild |
| **Version-up filenames** | Prevents overwriting approved work | CLAUDE.md Rule 2 |
| **Kim-confirmation gate** | Prevents overwriting Kim's edits | Blocking question before file writes |
| **600px minimum** | Ensures crop quality | 3-layer enforcement (UI + Directus + pipeline) |
| **7-query session start** | Prevents re-trying rejected settings | dashboard-gate skill |
| **Auto-registration** | Prevents invisible files | Post-build hooks in all builders |
| **Locked decisions collection** | Prevents revisiting approved choices | `prod_audio_locked_decisions` in Directus |


### 9.2 Known Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| **breathCycle data format** | Lock schema now, embed format version in all exports. Prevents silent data corruption if structure changes. |
| **Parked audio stability** | Register parked audio with `status="parked_pending_architecture"` + SHA256 checksums. Batch-retry failed registrations on session start. |
| **Universal container refactor** | Defer major refactoring until AFTER M1 video is locked + delivered. Current arch is stable; early changes risk breaking working skills. |
| **Directus outage fallback** | Tools should save with `.pending_registration` marker if API fails. Batch retry with exponential backoff on next session start. |
| **Voice profile stability** | Embed voice_id + model_version + stability/speed parameters in asset metadata. Prevents mismatched regen if ElevenLabs voice IDs shift. |
| **Kim-confirmation gate for audio** | Before producing TTS, diff skeleton dialogue against storyboard export. If text changed, ask Kim to confirm new dialogue before rendering. |

---

## Part 10: The 9 Production Skills (Orchestration Layer)

The full production pipeline is orchestrated by 9 specialized skills that work together to move modules through the five pipeline stages (intake → phase_b → phase_a_json → audio → listen_through). All skills are loaded into Cowork and called via the pipeline orchestrator (`pipeline.py`).

**Behavioral Gatekeeper (load FIRST):**
- **dashboard-gate** — Enforces the 7-query session start protocol, real-time dashboard logging, and locked decision compliance. MUST be loaded BEFORE any domain skill (audio-producer, video-producer, etc.). This skill ensures the entire session respects prior decisions and maintains transparency in the dashboard.

**Core Production Skills (loaded in dependency order):**
- **dashboard-ops** — Operate the Directus dashboard API: query collections, update module status, log activity, manage blockers.
- **intake-briefer** — Module intake — summarize creature arc brief and extract narrative requirements.
- **phase-b-writer** — Write Phase B meditation scripts: clinical extraction → language audit → 7-section template → body test → Kim review → audio markers.
- **phase-a-designer** — Design Phase A beat sheets: demo breakdowns, interaction cues, character vocabulary.
- **module-json-builder** — Generate JSON configs: phaseAConfig, phaseBConfig, creature dialogue, reward mechanics.
- **audio-producer** — Full audio pipeline: TTS generation → cue point mapping → breathCycle rhythms → MP3 mixing.
- **video-producer** — Full video pipeline: storyboard → crops → TTS audition → animation generation → animation review → ByteDance lip-sync → ffmpeg assembly.
- **narrative-generator** — AI narrative cache: generate story dialogue alternatives, creature voice personality profiles.

**Cascade and Dependencies:** Each skill's output feeds into the next. For example, phase-b-writer produces a script with audio markers; audio-producer consumes those markers. dashboard-gate sits at the top of the chain and enforces safety constraints across all skills. See PIPELINE_BRAIN Part 3 for full orchestration details and dependency diagrams.

---

## Part 11: Session Start Protocol — Staleness Scan

Before any production work begins, a mandatory staleness scan verifies that all canonical documents are consistent and no stale information will infect the session. This is a BLOCKING prerequisite — no production work begins until the scan completes and Kim acknowledges any RED flags.

**The 7-Step Staleness Scan:**

1. **Load Current Versions** — Retrieve the highest-version-number copies of:
   - `ARC_PRODUCTION_BIBLE` (check version number suffix)
   - ArcBuilder skill (SKILL_arcbuilder_v*_*.md in project folder)
   - Most recent arc skeleton being worked on (identified by file timestamp)
   - `UNIFIED_TECHNIQUE_INVENTORY` (highest version)
   - `CLAUDE_Everdale_World_Design_Bible` (highest version)
   - `NARRATIVE_DECISIONS_UNIFIED` (highest version)

2. **Spot-Check Character Name Drift** — Cross-check all documents against the Terminology Reference table in CLAUDE.md. Flag any old names appearing outside of changelogs:
   - Shelby → Tessa ✓
   - GlowDrop/Prism → Zap ✓
   - XP → Coins ✓
   - Kindness Stone → Heart Stone (Art name unchanged) ✓
   - All others in current reference list

3. **Verify Technique Name Matches** — Compare skeleton technique names against:
   - Bible skill portfolio
   - Unified Technique Inventory
   - Module specifications
   - Any mismatch = RED flag

4. **Check Party Composition** — Confirm post-arc party list matches:
   - Bible's creature departure data
   - Skeleton's crew at arc conclusion
   - Any conflict = RED flag

5. **Scan for Retired Terminology** — Grep the active skeleton and Production Bible for known deprecated terms (Shelby, GlowDrop, XP, Kindness Stone, Breath-Squeezers old names, etc.). Any hit outside changelogs = RED flag.

6. **Verify Version Number References** — Check that documents don't reference outdated versions of other documents. E.g., skeleton should not reference "Bible v11" when v13.5 exists.

7. **Storyboard Freshness Check (if visual work planned)** — Query Directus `prod_modules`:
   - `storyboard_status = needs_rebuild` → 🔴 RED
   - `storyboard_build_mode = manual or unknown` → 🟡 YELLOW
   - `storyboard_built_at` > 7 days old AND status ≠ approved → 🟡 YELLOW
   - Run `python3 Production/tools/build_storyboard.py --smoke-test` to verify Directus auth

**Report Format (color-coded):**
- 🟢 **GREEN:** No drift in this category — documents are consistent.
- 🟡 **YELLOW:** Minor drift detected — not blocking, but should be fixed soon.
- 🔴 **RED:** Significant inconsistency that could cause production errors — recommend fixing before proceeding.

**Blocking Rule:** If any RED items are found, explicitly warn Kim and recommend fixing them before production work begins. Do not advance to production until RED items are resolved and Kim acknowledges.

**If all GREEN or only YELLOW:** Confirm "Staleness scan complete — all clear" and proceed with the session.

See CLAUDE.md "Session Start: Automatic Staleness Scan" for the complete protocol implementation.

---

## Part 12: Session Handoff Protocol

Every production session must end by documenting all work in the session handoff template. This ensures zero-context-loss for the next Claude thread and prevents repeating work or losing decisions.

**Mandatory Handoff Document:** At the end of every production session, fill out `Production/HANDOFF_TEMPLATE.md` with:
- **Files Changed:** List every file modified, created, or deleted with full path and brief description of change
- **Dashboard State:** Summarize module status changes, blocked modules, pending approvals
- **Pending Tasks:** List any incomplete work, blocked by external dependencies, or awaiting Kim decisions
- **Decisions Made:** Note any creative or technical decisions finalized this session, with rationale
- **Session Context:** Any unusual circumstances (Directus outage, voice profile changes, storyboard rebuilds, etc.)

The template is stored at `Production/HANDOFF_TEMPLATE.md` and has sections for each category. See `.auto-memory/reference_handoff_template.md` for the detailed template format.

**Why this matters:** Production work spans multiple sessions. Without a clear handoff, the next Claude thread loses context, re-does work, or misses dependencies. The handoff template is the contract between sessions — a single source of truth for what was done, what's next, and what decisions were made.

---

## Appendix A: File Inventory

### Production Tools (Production/tools/)
- `build_storyboard.py` (1,427 lines) — storyboard builder, 6 CLI modes
- `build_cropper.py` (797 lines) — cropper builder, 1 CLI mode + registration
- `build_tts_review.py` (655 lines) — TTS audition builder, 1 CLI mode + registration
- `build_animation_review.py` (1,424 lines) — animation review builder, 5 CLI modes
- `generate_animation_options.py` (~400 lines) — EvoLink/Kling v3 animation generator
- `pipeline.py` — orchestrator (TTS steps are placeholders)

### M1 Event 1 Assets (Production/Event_1/)
- `animation_review_manifest_v1.json` — 11 beats, clip/audio paths
- `story_scene_v3/animation_review_M1E1_v1.html` — 34.36MB, 11 beats
- `story_scene_v3/storyboard_v21.html` — current approved storyboard
- 15 MP4 animation clips (registered in Directus as IDs 29-43)
- 10 TTS audio files (registered in Directus as IDs 12-21)
- 8 crop_4x3 PNGs (registered in Directus)

### Dashboard State (as of April 14, 2026)
- M1: stage=audio, storyboard_status=approved (v21), animation_review_status=built (v1), cropper_status=approved (v1), tts_audition_status=built (v3)
- prod_visual_assets: 57 active assets, 0 duplicates, all files verified on disk
- All 4 production tools have matching dashboard tracking fields

---

*This document supersedes: TOOLS_ARCHITECTURE_AUDIT.md, TOOLS_QUICK_REFERENCE.md, UNIVERSAL_CONTAINER_IMPLEMENTATION_PLAN.md (all of which remain available as detailed reference).*

*For the step-by-step production walkthrough, see PIPELINE_BRAIN_v1.md. For API credentials, see API_KEYS_MASTER.md. For session-to-session continuity, see HANDOFF_TEMPLATE.md.*
