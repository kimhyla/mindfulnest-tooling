# Storyboard Production Overlay — Technical Plan v3 (Hybrid Architecture)

**Date:** April 15, 2026  
**Status:** Ready for implementation review  
**Owner:** Claude (Phase 1-3 implementation) → Kim (review/selection gates)  
**Target Timeline:** Phase 1 = 3 days, Phase 2 = 1 day, Phase 3 = 1 day  
**Supersedes:** v2 (pure-browser approach — blocked by CORS/file-write constraints)

---

## 1. Executive Summary

The Storyboard Production Overlay lets Kim go from an arranged storyboard to production-ready animated clips in a single session. She clicks "Fire Away," 3 animation options appear per beat, she picks winners, generates TTS, and sends for lip sync — all without leaving the HTML interface.

**What changed from v2 (and why):**

v2 assumed browser JavaScript (from `file://` HTML) could make fetch() calls to external APIs and write files to disk. Five-agent review found this is **impossible** — browsers block cross-origin requests from `file://`, localStorage is unavailable in Chrome from `file://`, and browser JS cannot write to the filesystem.

v3 uses a **hybrid architecture**: a lightweight Python local server handles all API calls, file writes, and state persistence. The browser HTML handles only visualization and Kim's input. Communication is via `http://localhost:5111` — no CORS issues, no file-write issues, no API key exposure.

**Kim's experience is identical to v2:** she opens an HTML file, clicks "Fire Away," animations appear, she picks winners. The Python server runs invisibly in the background (Claude starts it before opening the HTML for Kim).

**Why this is still Path B (CLAUDE.md Rule 7):**

The injected JavaScript is now dramatically simpler — it's a thin UI layer that calls `localhost:5111/api/*` endpoints. No API keys in HTML, no direct external API calls, no file-system access. The Python server is a *separate tool* (`production_server.py`), not a modification to the storyboard builder. The HTML injection remains behavior-only: UI elements + localhost fetch calls. The storyboard's beat data, images, and structure are untouched.

---

## 2. Architecture Overview

### 2.1 Hybrid: Python Server + Browser UI

```
┌─────────────────────────────────────────────────────────┐
│  Kim's Browser (Safari/Chrome)                          │
│  ┌───────────────────────────────────────────────────┐  │
│  │  storyboard_v14_prod.html                         │  │
│  │  ┌─────────────────────────────────────────────┐  │  │
│  │  │  Original storyboard (beats, images, audio) │  │  │
│  │  │  [UNTOUCHED — read-only]                    │  │  │
│  │  └─────────────────────────────────────────────┘  │  │
│  │  ┌─────────────────────────────────────────────┐  │  │
│  │  │  Injected Production Overlay (JS + CSS)     │  │  │
│  │  │  • "Fire Away" button                       │  │  │
│  │  │  • Progress bars per beat                   │  │  │
│  │  │  • Video/audio preview players              │  │  │
│  │  │  • Selection UI (pick winner per beat)      │  │  │
│  │  │  • All calls go to localhost:5111           │  │  │
│  │  └─────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────┘  │
│                         │ fetch('http://localhost:5111') │
└─────────────────────────┼───────────────────────────────┘
                          │
┌─────────────────────────┼───────────────────────────────┐
│  Python Local Server    │  (production_server.py)        │
│  localhost:5111         ▼                                │
│  ┌───────────────────────────────────────────────────┐  │
│  │  /api/health          → server alive check        │  │
│  │  /api/state           → get/set production state  │  │
│  │  /api/animate         → submit Kling jobs         │  │
│  │  /api/animate/status  → poll Kling results        │  │
│  │  /api/tts             → generate ElevenLabs audio │  │
│  │  /api/lipsync         → submit ByteDance jobs     │  │
│  │  /api/lipsync/status  → poll lip-sync results     │  │
│  │  /api/select          → record Kim's picks        │  │
│  │  /api/export          → export final manifest     │  │
│  └───────────────────────────────────────────────────┘  │
│                                                          │
│  Handles:                                                │
│  • ALL external API calls (WaveSpeed, ElevenLabs)        │
│  • ALL file writes (MP4, MP3 to animation_clips/)        │
│  • ALL state persistence (JSON file on disk)             │
│  • API key storage (read from API_KEYS_MASTER.md)        │
│  • Cost tracking (persistent JSON on disk)               │
│  • Retry logic (3 silent retries + exponential backoff)  │
└──────────────────────────────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────┐
│  External APIs                                           │
│  • WaveSpeed (Kling v3 animation + ByteDance lip-sync)   │
│  • ElevenLabs (TTS voice generation)                     │
│  • Directus (motion prompts, voice profiles, logging)    │
└──────────────────────────────────────────────────────────┘
```

### 2.2 Why Hybrid Solves v2's Blockers

| v2 Problem | v3 Solution |
|-----------|-------------|
| `fetch()` from `file://` to `https://` blocked by CORS | Python server makes all external calls; browser only calls `localhost:5111` |
| `localStorage` unavailable in Chrome from `file://` | State stored as JSON file on disk (`production_state.json`) |
| Browser JS can't write files to disk | Python server writes MP4/MP3 files directly |
| API keys embedded in HTML (security risk) | Keys read from `API_KEYS_MASTER.md` by Python, never sent to browser |
| IndexedDB fragile (sandboxed per-file-path) | Eliminated — disk JSON is path-independent |

### 2.3 Pre-Injection Gates (BLOCKING)

Before Claude injects the overlay OR starts the server:

1. **Browser-edit gate (CLAUDE.md Rule 7):** Ask Kim: *"Have you made edits in the browser (dialogue, drag-drop, image assignments) that haven't been exported?"* If yes, she MUST click "Export Locked Sequence" first.

2. **Export-first protocol (CLAUDE.md Rule 7):** Kim must export her storyboard selections BEFORE the overlay is injected. The overlay reads from the HTML file on disk, not browser memory.

3. **Kim-confirmation gate (CLAUDE.md Rule 3):** *"Kim, I'm about to write `storyboard_M1E1_v14_prod.html`. Have you made any edits to `storyboard_M1E1_v14.html` since we last touched it?"* Wait for Kim's confirmation with the exact filename.

4. **MD5 validation (CLAUDE.md Rule 7):** After injection, verify all base64 image data is byte-identical before/after. Compute MD5 hash for every embedded image in input HTML, verify match in output HTML. Abort if any differ.

All four gates are BLOCKING — do not proceed without confirmation.

### 2.4 File Structure

```
Production/
├── tools/
│   ├── build_storyboard.py              [existing builder — UNTOUCHED]
│   ├── inject_production_overlay.py     [NEW: injects thin UI JS into HTML]
│   └── production_server.py             [NEW: local API server]
├── Event_1/
│   ├── storyboard_v14.html              [Kim's storyboard — NEVER MODIFIED]
│   ├── storyboard_v14_prod.html         [NEW: overlay-injected version]
│   ├── production_state.json            [NEW: persistent state (replaces localStorage)]
│   ├── production_spend.json            [NEW: cost tracking]
│   └── animation_clips/
│       ├── beat_001_option_1.mp4
│       ├── beat_001_option_2.mp4
│       ├── beat_001_option_3.mp4
│       ├── beat_001_tts.mp3
│       └── beat_001_lipsync.mp4
└── .auto-memory/
    └── production_overlay_manifest.json [feature audit + injection log]
```

### 2.5 Startup Sequence (Claude Executes)

When Kim says "let's produce" or "fire up the overlay":

```
Step 1: Claude runs pre-injection gates (Section 2.3)
Step 2: Claude runs inject_production_overlay.py → creates _prod.html
Step 3: Claude starts production_server.py (background process)
Step 4: Claude verifies server is alive: GET http://localhost:5111/api/health
Step 5: Claude opens _prod.html for Kim via Finder
Step 6: Kim sees storyboard with "Fire Away" button
```

**Server lifecycle:** The Python server runs as long as Kim is working. Claude starts it at session start and it auto-shuts down after 2 hours of inactivity. If Kim's browser loses connection (shows "Server offline" banner), Claude restarts the server.

---

## 3. Python Local Server (`production_server.py`)

### 3.1 Technology

- **Framework:** Python `http.server` (stdlib) or Flask (if available). No external dependencies required — stdlib HTTPServer is sufficient for single-user local use.
- **Port:** 5111 (unlikely to conflict with common dev tools)
- **CORS:** Server adds `Access-Control-Allow-Origin: *` header to all responses (safe because it's localhost-only)
- **Auth:** None required (localhost access only, single user)

### 3.2 State Management (Disk-Based)

All state lives in `production_state.json` — a single JSON file on disk, read/written by the Python server. No localStorage, no IndexedDB, no browser storage of any kind.

```json
{
  "event_id": "Event_1",
  "created_at": "2026-04-15T14:32:00Z",
  "updated_at": "2026-04-15T15:01:00Z",
  "beats": {
    "beat_001": {
      "speaker": "Guide Bird",
      "text": "{childName}, look! The Heartwood is glowing again!",
      "section": "Story",
      "phase_1": {
        "status": "completed",
        "options": [
          { "task_id": "abc123", "status": "completed", "file": "animation_clips/beat_001_option_1.mp4", "submitted_at": "2026-04-15T14:33:00Z" },
          { "task_id": "def456", "status": "completed", "file": "animation_clips/beat_001_option_2.mp4", "submitted_at": "2026-04-15T14:33:00Z" },
          { "task_id": "ghi789", "status": "polling", "file": null, "submitted_at": "2026-04-15T14:33:00Z", "retries": 1 }
        ],
        "selected_option": 1
      },
      "phase_2": {
        "status": "completed",
        "file": "animation_clips/beat_001_tts.mp3",
        "voice_id": "21A8qXBP...",
        "duration_seconds": 3.2
      },
      "phase_3": {
        "status": "pending",
        "file": null,
        "mouth_check": null
      }
    }
  }
}
```

**Resume logic:** On server start, read `production_state.json`. For any beat with `status: "polling"` and `submitted_at` < 2 hours ago, resume polling. For `submitted_at` > 2 hours, mark as `"expired"` (needs fresh submission).

### 3.3 API Endpoints

#### `GET /api/health`
Returns `{"status": "ok", "uptime_seconds": 123}`. Browser polls this every 30s to show "Server online" indicator.

#### `GET /api/state`
Returns the full `production_state.json`. Browser calls this on page load to populate UI.

#### `POST /api/animate`
**Triggers Phase 1 animation generation for specified beats.**

Request:
```json
{
  "beats": ["beat_001", "beat_002", "beat_003"],
  "options_per_beat": 3,
  "mode": "all"
}
```

- `mode: "all"` = generate for all beats (Fire Away)
- `mode: "test"` = generate for specified beats only (Test Mode — 1-3 beats)
- `mode: "retry"` = retry only failed beats

Behavior:
1. For each beat, extract base64 image from storyboard HTML (read from disk, NOT from browser)
2. Build motion prompt per beat (from Directus `prod_session_decisions`, cached at server start)
3. Submit to WaveSpeed Kling v3 API (3 jobs per beat)
4. Store task IDs in `production_state.json`
5. Return immediately with `{"submitted": 9, "status": "polling"}`
6. Background thread polls WaveSpeed, downloads MP4s to `animation_clips/`, updates state

**WaveSpeed Kling API call (CORRECTED from v2):**
```
POST https://api.wavespeed.ai/api/v3/kwaivgi/kling-v3.0-pro/image-to-video

{
  "model": "kwaivgi/kling-v3.0-pro/image-to-video",
  "input": {
    "image": "data:image/png;base64,iVBORw0KG...",
    "prompt": "[character] [action]. Beak closed, no speech, no lip movement. Silent subtle idle movement only.",
    "negative_prompt": "lip sync, speaking, talking, mouth movement, dialogue, speech, open mouth, Chinese, audio, voice, singing",
    "duration": 5,
    "cfg_scale": 0.5,
    "seed": -1
  },
  "sound": false
}
```

**Polling:** `GET https://api.wavespeed.ai/api/v3/predictions/{task_id}/result`
**Response:** `data.data.outputs[0]` = video URL. Download to `animation_clips/`.

**Anti-lip-sync (CLAUDE.md Rule 8 — ALWAYS ON):**
- Banned words: `speaking`, `speech`, `dialogue`, `lip sync`, `lip movement`, `mouth movement`, `beak movement`, `talking`, `singing`, `vocal`
- For bird characters: `"Beak closed, no speech, no lip movement"`
- For non-bird characters: `"Mouth closed, no speech"`
- All prompts end with: `"Silent subtle idle movement only"`
- API params: `sound: false`, `negative_prompt` as above, `cfg_scale: 0.5`

**Duration auto-matching:**
- Default: 5 seconds (Phase 1, before TTS exists)
- After TTS: `ceil(tts_duration / 5) × 5`, capped at 10s
- If recalculation yields longer duration than original generation, server re-submits to Kling at the new duration

#### `GET /api/animate/status`
Returns current state of all animation jobs. Browser polls this every 10 seconds while Phase 1 is active.

Response:
```json
{
  "total_beats": 11,
  "completed": 7,
  "polling": 3,
  "failed": 1,
  "beats": {
    "beat_001": { "status": "completed", "options": [{"file": "...", "size_mb": 2.3}, ...] },
    "beat_002": { "status": "polling", "retries": 1, "eta_seconds": 45 }
  }
}
```

#### `POST /api/tts`
**Triggers Phase 2 TTS generation for specified beats.**

Request:
```json
{
  "beats": ["beat_001", "beat_002"],
  "session_context": {
    "childName": "Sophia",
    "therapistName": "Dr. Reed",
    "chosenGuideName": "Feathers"
  }
}
```

Behavior:
1. For each beat, get speaker + text from storyboard data
2. Substitute personalization variables (`{childName}` → "Sophia", etc.)
3. Look up voice profile from Directus `prod_voice_profiles` (cached at server start)
4. **Myrrhin lock (MANDATORY):** If speaker is Myrrhin, HARDCODE stability=0.70, speed=0.50 regardless of Directus values
5. Call ElevenLabs API
6. Handle binary MP3 response (`response.content`, NOT `.json()`)
7. Save to `animation_clips/beat_XXX_tts.mp3`
8. Update `production_state.json` with duration

**ElevenLabs API call:**
```
POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=mp3_128

Headers:
  xi-api-key: {API_KEY}
  Content-Type: application/json

Body:
{
  "text": "Sophia, look! The Heartwood is glowing again!",
  "model_id": "eleven_multilingual_v2",
  "voice_settings": {
    "stability": 0.50,
    "similarity_boost": 0.75,
    "style": 0,
    "use_speaker_boost": true
  }
}
```

**Response:** Raw MP3 binary. Save with `open(path, 'wb').write(response.content)`.

**Rate limiting:** Submit TTS requests sequentially (1 at a time) with 500ms delay between calls. ElevenLabs handles concurrency poorly at high volume.

#### `POST /api/lipsync`
**Triggers Phase 3 lip-sync for specified beats.**

Request:
```json
{
  "beats": ["beat_001", "beat_002"],
  "source": "selected_animation"
}
```

Behavior:
1. For each beat, get the selected animation clip + TTS audio
2. Submit to WaveSpeed ByteDance lip-sync API
3. Download result, save to `animation_clips/beat_XXX_lipsync.mp4`
4. **Lip-Sync Review Gate (CLAUDE.md Rule 8 — MANDATORY):** Flag for Kim's visual review

**ByteDance API call:**
```
POST https://api.wavespeed.ai/api/v3/bytedance/lipsync/audio-to-video

{
  "model": "bytedance/lipsync/audio-to-video",
  "input": {
    "video_url": "https://storage.wavespeed.ai/...",
    "audio_url": "https://storage.wavespeed.ai/..."
  }
}
```

**Note:** ByteDance requires URLs, not local file paths. The server must first upload the selected animation clip and TTS audio to a temporary URL (WaveSpeed storage or pre-signed URL) before submitting the lip-sync job. If direct upload isn't available, base64-encode both and submit as data URIs.

**Polling:** Same as Kling — `GET /api/v3/predictions/{task_id}/result`

#### `POST /api/select`
Records Kim's animation pick for a beat.

```json
{ "beat": "beat_001", "selected_option": 2 }
```

Updates `production_state.json` and returns confirmation.

#### `POST /api/export`
Exports final manifest with all selected clips, TTS files, and lip-sync results. Used for downstream app integration.

### 3.4 Multi-Layer Retry Logic (Server-Side)

All retry logic lives in Python (not browser JS). Simpler, more reliable, survives browser refreshes.

**Layer 1: Staggered submission (prevent thundering herd)**
- Submit animation jobs in batches of 6 (2 beats × 3 options), staggered 2 seconds apart
- Total submission time for 20 beats: ~20 seconds (vs. simultaneous blast that triggers rate limits)

**Layer 2: 3 silent auto-retries with exponential backoff**
- Timeout/error → retry after 5s, 10s, 20s
- Server logs retries but does NOT report them to browser until all 3 exhausted
- Browser sees: "Processing..." (not "Retry #2 of 3")

**Layer 3: Re-poll before re-submit (cost guard)**
- Before any retry submission, re-poll the old task_id first
- ~30% of "failed" jobs actually completed but polling timed out
- Re-polling recovers these at zero cost
- Only re-submit if re-poll confirms failure or task expired (>2 hours old)

**Layer 4: Resume from partial completion**
- On server start, read `production_state.json`
- For pending tasks with `submitted_at` < 2 hours: resume polling
- For pending tasks with `submitted_at` > 2 hours: mark expired, offer re-submit
- For completed tasks with files on disk: skip (already done)

**Layer 5: Fallback to fal.ai (cost-capped)**
- If WaveSpeed fails 3 times on a specific beat, offer fal.ai fallback
- fal.ai fallback has its own budget cap: $5 max across entire event
- Server tracks fallback spend separately in `production_spend.json`

### 3.5 Cost Tracking (Disk-Based)

`production_spend.json`:
```json
{
  "event_id": "Event_1",
  "budget": 25.00,
  "spent": {
    "kling": 15.60,
    "elevenlabs": 0.60,
    "bytedance_lipsync": 5.20,
    "fal_ai_fallback": 0.00,
    "retries": 0.52
  },
  "total_spent": 21.92,
  "warnings_shown": ["80_percent"],
  "override_budget": 0.00
}
```

**Thresholds:**
- 80% ($20): Server returns warning flag; browser shows "⚠️ $20 of $25 used"
- 100% ($25): Server blocks new submissions; browser shows "⛔ Budget limit. Override for +$5?"
- Override: Kim clicks override → server adds $5 to budget → unblocks

---

## 4. Browser Overlay (Injected JS + CSS)

### 4.1 What the Injected JS Does (Thin Client)

The injected JavaScript is a **thin UI layer** — approximately 300-400 lines. It:
- Calls `http://localhost:5111/api/*` endpoints
- Renders progress bars, video players, audio players, selection UI
- Polls `/api/animate/status` every 10 seconds during generation
- Polls `/api/health` every 30 seconds to show server status
- Does NOT store any state (all state is on server)
- Does NOT make external API calls (all go through Python)
- Does NOT write files (all file I/O is Python)
- Does NOT contain API keys (keys are server-side only)

### 4.2 Server Health Indicator

Top-right corner of overlay:
- 🟢 "Server online" — `/api/health` returns 200
- 🔴 "Server offline — ask Claude to restart" — `/api/health` fails
- Browser checks every 30 seconds

### 4.3 Phase 1 UI (Animation Generation)

**"Fire Away" button:**
- Location: Top of overlay, prominent
- Disables on click (prevent double-click)
- Calls `POST /api/animate` with `mode: "all"`
- Shows spinner: "🎬 Generating animations for 11 beats..."

**Test Mode toggle (NEW in v3):**
- Checkbox above Fire Away: "☐ Test Mode (1-3 beats only)"
- When enabled, Kim selects specific beats, clicks Fire Away → only those beats submitted
- Cheaper and faster for initial testing

**Per-beat animation options:**
```
Beat 001 (Guide Bird speaks)                    [Section: Story]
─────────────────────────────────────────────────
"Sophia, look! The Heartwood is glowing again!"
[▶ Play] Option 1 (2.3 MB)  ○ select
[▶ Play] Option 2 (2.1 MB)  ◉ selected  ✓
[▶ Play] Option 3 (2.4 MB)  ○ select
```

**Video playback:** Videos are served from disk via `file://` paths (HTML5 video with file:// src works natively on macOS). No server involvement for playback.

**Global progress:**
```
Phase 1: 7/11 beats ready, 3 processing, 1 retrying...
Estimated time remaining: ~2 minutes
Cost so far: $4.68 of $25.00
[Retry Failed] [Skip to Phase 2 (with 7 beats)]
```

**Error messages (human-friendly only):**

| Scenario | Message | Action |
|----------|---------|--------|
| Server offline | "🔴 Production server is offline. Ask Claude to restart it." | None |
| Beat submission timeout | "Taking longer than expected... retrying automatically" | None (auto) |
| 3 retries exhausted | "Beat 3 failed after 3 tries. [Retry] [Skip]" | Button |
| All complete | "✅ 11 beats ready! Pick your favorites, then Phase 2." | Selection UI |
| Budget 80% | "⚠️ $20 of $25 used" | Info only |
| Budget 100% | "⛔ Budget limit. [Override +$5] [Stop]" | Button |

### 4.4 Phase 2 UI (TTS Generation)

**"Generate TTS" button:**
- Appears only after Phase 1 selections are made
- Calls `POST /api/tts` with selected beats

**Per-beat audio:**
```
Beat 001 (Guide Bird)
─────────────────────
[▶ Play] 3.2 seconds | Voice: Guide Bird
Animation duration: 5s (matches)
```

**Myrrhin indicator:** For Myrrhin beats, shows: "🔒 Voice locked: stability 0.70, speed 0.50"

### 4.5 Phase 3 UI (Lip-Sync)

**"Send for Lip Sync" button:**
- Appears only when Phase 1 + Phase 2 are approved
- Calls `POST /api/lipsync`

**Lip-Sync Review Gate (MANDATORY per Rule 8):**
Each completed lip-sync clip shows:
```
Beat 001 — Lip Sync Result
[▶ Play 3s preview]
Does this look right? [👍 Approve] [👎 Reject & Retry]
```

Kim must explicitly approve or reject each clip. No auto-approve.

**Final export:**
```
🎉 All 11 clips complete!
[Export Manifest JSON] [Download All as ZIP] [View Summary]
```

---

## 5. Injection Script (`inject_production_overlay.py`)

### 5.1 What It Does

A Python script run BY CLAUDE (not Kim) that:
1. Reads the existing storyboard HTML from disk
2. MD5 hashes all embedded base64 images
3. Injects a `<script>` block with the thin UI client (~300-400 lines)
4. Injects a `<style>` block with overlay CSS
5. Verifies all base64 images are byte-identical after injection
6. Writes new `_prod.html` file (never overwrites original)
7. Generates `production_overlay_manifest.json`

### 5.2 CLI Usage

```bash
python3 Production/tools/inject_production_overlay.py \
  --input Production/Event_1/storyboard_v14.html \
  --output Production/Event_1/storyboard_v14_prod.html \
  --event-id "Event_1" \
  --validate-images
```

**Note:** No `--api-keys` or `--directus-token` flags. Keys live in the server, not the HTML.

### 5.3 Validation Checks (BLOCKING)

1. ✓ Beat count matches input HTML
2. ✓ All beats have speaker + text + image
3. ✓ All MD5 image hashes match between input and output
4. ✓ No API keys present in output HTML
5. ✓ Injected JS only references `localhost:5111` (no external URLs)
6. ✓ Original beat data structure untouched

---

## 6. Production Server (`production_server.py`)

### 6.1 CLI Usage

```bash
python3 Production/tools/production_server.py \
  --event-id "Event_1" \
  --storyboard Production/Event_1/storyboard_v14_prod.html \
  --output-dir Production/Event_1/animation_clips/ \
  --api-keys Production/API_KEYS_MASTER.md \
  --directus-token "TOKEN" \
  --port 5111 \
  --budget 25.00 \
  --session-context '{"childName":"Sophia","therapistName":"Dr. Reed","chosenGuideName":"Feathers"}'
```

### 6.2 Server Startup Sequence

1. Parse API keys from `API_KEYS_MASTER.md`
2. Load or create `production_state.json`
3. Load or create `production_spend.json`
4. Cache motion prompts from Directus `prod_session_decisions`
5. Cache voice profiles from Directus `prod_voice_profiles`
6. Resume any pending tasks from prior session (Layer 4)
7. Start HTTP server on `localhost:5111`
8. Log: "Production server ready on http://localhost:5111"

### 6.3 Auto-Shutdown

Server shuts down after 2 hours of no API calls (inactivity timer). Prevents zombie processes on Kim's Mac.

### 6.4 Dependencies

- Python 3.8+ (already available on Mac)
- `requests` library (for external API calls — `pip install requests` if not present)
- `http.server` from stdlib (for local HTTP server)
- No other dependencies required

---

## 7. Motion Prompt Strategy

### 7.1 Prompt Sources

Motion prompts come from Directus `prod_session_decisions` collection, cached at server start. If no prompt exists for a beat, use a default template:

**Default template:**
```
[Character type] character with [emotion from context]. [Physical action]. 
[Anti-lip-sync constraint]. Silent subtle idle movement only.
```

**Character-specific constraints (Rule 8):**
- Birds (Guide Bird, Luna): "Beak closed, no speech, no lip movement"
- Turtles (Tessa): "Mouth closed, no speech"
- All others: "Mouth closed, no speech"

### 7.2 Duration Auto-Matching

| Audio Length | Animation Duration | Note |
|-------------|-------------------|------|
| No audio yet (Phase 1) | 5 seconds | Default |
| 0-5 seconds | 5 seconds | Standard |
| 5.1-10 seconds | 10 seconds | Extended |
| >10 seconds | 10 seconds + loop | Cap at 10s, loop for excess |

After Phase 2 TTS, if duration needs upgrading (e.g., 3.2s audio generated 5s clip, but later TTS is 7.8s), server re-submits to Kling at 10s and replaces the clip.

---

## 8. Governance & Compliance

### 8.1 CLAUDE.md Rules Compliance

| Rule | How v3 Complies |
|------|-----------------|
| **Rule 3 (Kim-confirmation gate)** | Explicit gate before writing `_prod.html` — Claude asks Kim with exact filename, waits for confirmation |
| **Rule 7 (Two-Path Protocol)** | Path B: injected JS is behavior-only (thin UI client, ~300 lines, no API keys, no file I/O). Python server is a separate tool, not an HTML modification. MD5 validation on all images. |
| **Rule 8 (Anti-Lip-Sync)** | Banned words enforced in all motion prompts. negative_prompt, cfg_scale:0.5, sound:false on all Kling calls. Lip-sync review gate mandatory for all Phase 3 clips. |
| **Rule 9 (Change reporting)** | Injection manifest documents every injected feature, line counts, and validation results |
| **Myrrhin voice lock** | Server hardcodes stability=0.70, speed=0.50 for Myrrhin regardless of Directus |

### 8.2 API Key Security

- Keys read from `API_KEYS_MASTER.md` by Python server at startup
- Keys NEVER appear in HTML, JavaScript, or browser-accessible responses
- `/api/health` and `/api/state` responses contain NO credentials
- Server binds to `localhost` only — not accessible from other machines

### 8.3 Session Spend Tracking

- Tracked in `production_spend.json` on disk (survives browser crashes)
- Also logged to Directus `prod_activity_log` after each phase completes
- Warn at 80%, block at 100%, override in $5 increments
- Fallback (fal.ai) has separate $5 cap

---

## 9. Implementation Checklist

**Phase 0: Infrastructure (Day 1)**
- [ ] Build `production_server.py` scaffold (HTTP server, health endpoint, state management)
- [ ] Build `inject_production_overlay.py` (HTML parsing, MD5 validation, JS injection)
- [ ] Test: server starts, health check works, injection produces valid HTML
- [ ] Test: injected HTML can reach `localhost:5111` from Safari and Chrome

**Phase 1: Animation (Days 1-3)**
- [ ] Implement `/api/animate` endpoint (WaveSpeed Kling submission)
- [ ] Implement background polling thread (staggered, 2 beats at a time)
- [ ] Implement 3-layer retry logic (silent retries + re-poll + exponential backoff)
- [ ] Implement `/api/animate/status` endpoint
- [ ] Implement cost tracking in `production_spend.json`
- [ ] Build Phase 1 UI in injected JS (Fire Away, progress, video players, selection)
- [ ] Implement Test Mode (1-3 beats selective generation)
- [ ] Implement resume from `production_state.json`
- [ ] Test with 3-beat sample storyboard end-to-end

**Phase 2: TTS (Day 4)**
- [ ] Implement `/api/tts` endpoint (ElevenLabs with binary MP3 handling)
- [ ] Implement Myrrhin voice lock (stability 0.70, speed 0.50)
- [ ] Implement personalization variable substitution
- [ ] Implement sequential TTS with 500ms delay
- [ ] Build Phase 2 UI (Generate TTS, audio players, duration display)
- [ ] Test: verify MP3 files saved, duration calculated, auto-match triggers

**Phase 3: Lip-Sync (Day 5)**
- [ ] Implement `/api/lipsync` endpoint (ByteDance via WaveSpeed)
- [ ] Handle file upload requirement (animation clip + audio to WaveSpeed storage)
- [ ] Implement lip-sync review gate (mandatory per Rule 8)
- [ ] Implement fal.ai fallback with $5 cap
- [ ] Build Phase 3 UI (Send for Lip Sync, review gate, final export)
- [ ] Test: verify lip-sync clips generated, review gate works

**Validation & Handoff**
- [ ] End-to-end test: 3 beats through all 3 phases
- [ ] Verify: no API keys in HTML (grep for key patterns)
- [ ] Verify: all files saved to correct locations
- [ ] Verify: cost tracking accurate across all phases
- [ ] Verify: resume works (kill server mid-generation, restart, verify recovery)
- [ ] Log production to Directus `prod_activity_log`
- [ ] Open for Kim via Finder, confirm Fire Away button works

---

## 10. Questions for Implementation Thread

1. Does `http.server` from Python stdlib handle concurrent requests well enough, or should we use Flask/FastAPI with threading? (Recommendation: start with stdlib, upgrade if needed)
2. For ByteDance lip-sync, how do we upload local files to WaveSpeed storage? Is there an upload endpoint, or must we base64-encode?
3. What's the exact format of motion prompts in Directus `prod_session_decisions`? One prompt per beat, or one per creature per section?
4. Should the server auto-start when Kim opens the HTML (via an embedded script tag that checks `localhost:5111`), or must Claude always start it manually?

---

## 11. Key Differences: v2 → v3

| Item | v2 | v3 |
|------|-----|-----|
| Architecture | Pure browser (file:// HTML + JS) | Hybrid (Python server + thin browser client) |
| API calls | Browser fetch() to external APIs | Python `requests` to external APIs |
| File writes | Browser JS (BROKEN) | Python file I/O |
| State persistence | localStorage (BROKEN in Chrome) | `production_state.json` on disk |
| API key storage | Embedded in HTML (security risk) | Python server only, never in HTML |
| Injected JS size | ~1000+ lines (full API logic) | ~300-400 lines (thin UI client) |
| Cost tracking | localStorage (lost on cache clear) | `production_spend.json` on disk |
| Resume logic | Browser localStorage (fragile) | Server reads disk state on start |
| Server dependency | None | Python local server on port 5111 |
| CORS issues | BROKEN (file:// → https://) | None (browser → localhost) |
| Rule 7 compliance | Questionable (massive JS payload) | Strong (thin UI only, no API logic) |
| Test Mode | Not available | ☐ checkbox for 1-3 beat testing |
| Timeline | 4 days | 5 days (1 extra for server infrastructure) |

---

**END OF DOCUMENT**

This plan is self-contained and ready for agent review, then implementation in a new Claude thread.
