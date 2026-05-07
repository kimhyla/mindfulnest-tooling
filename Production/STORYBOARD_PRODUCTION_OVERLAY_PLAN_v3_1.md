# Storyboard Production Overlay — Technical Plan v3.1

**Date:** April 15, 2026
**Status:** Ready for implementation by new Claude thread
**Owner:** Claude (implementation) → Kim (review/selection gates)
**Supersedes:** v3 (file:// CORS fix + threading fix), v2 (pure-browser — CORS-blocked)
**Phased delivery:** v1 = Animation (this plan), v1.1 = TTS, v1.2 = Lip-Sync

---

## 1. Executive Summary

The Storyboard Production Overlay lets Kim go from an arranged storyboard to animation-ready clips in a single session. She opens a URL, clicks "Fire Away," 3 animation options appear per beat, she picks winners, and exports her selections. All without leaving the browser.

**Architecture:** A Python local server (`production_server.py`) on `localhost:5111` handles everything — serves the storyboard HTML, makes all external API calls, writes files to disk, and persists state. The browser is a pure thin client. No file:// protocol, no CORS issues, no localStorage, no API keys in HTML.

**What ships now (v1 MVP):** Phase 1 only — Kling animation generation + selection UI + Test Mode. TTS (v1.1) and lip-sync (v1.2) are designed but not built yet. Each phase is independently useful. This was the unanimous recommendation of 10 review agents: ship Phase 1 alone, let Kim validate the workflow, then layer TTS and lip-sync.

**CLAUDE.md classification:** Extended Path B. The injected JS is a thin UI layer (~200-300 lines) with zero API keys, zero file I/O, zero external API calls. The Python server is a separate production tool, not an HTML modification. MD5 image validation confirms byte-identity before/after injection. Three governance conditions apply (Section 8).

**What changed from v3:**
1. Server serves the HTML at `http://localhost:5111/storyboard` (not file:// — fixes Safari CORS block)
2. `ThreadingHTTPServer` for concurrent request handling (fixes single-thread blocking)
3. Batched WaveSpeed polling (5 tasks/poll, 2s gaps — prevents rate-limit 429s)
4. Phase 1 MVP only (TTS and lip-sync deferred to v1.1/v1.2)
5. Backward editing: "Re-Do Beat N" button for individual beat re-generation
6. Server cleanup on session start (`pkill` stale processes, port check)
7. All media served via `http://localhost:5111/asset/` (not file:// paths)

---

## 2. Architecture Overview

### 2.1 Single-Origin Hybrid: Python Server Serves Everything

```
┌─────────────────────────────────────────────────────────┐
│  Kim's Browser (Safari or Chrome)                       │
│                                                          │
│  http://localhost:5111/storyboard                        │
│  ┌───────────────────────────────────────────────────┐  │
│  │  Storyboard HTML (served by Python, not file://)  │  │
│  │  ┌─────────────────────────────────────────────┐  │  │
│  │  │  Original beats, images, dialogue            │  │  │
│  │  │  [READ-ONLY — never mutated by overlay]     │  │  │
│  │  └─────────────────────────────────────────────┘  │  │
│  │  ┌─────────────────────────────────────────────┐  │  │
│  │  │  Injected Production Overlay (JS + CSS)     │  │  │
│  │  │  • "Fire Away" button + Test Mode toggle    │  │  │
│  │  │  • Per-beat progress + video players        │  │  │
│  │  │  • Selection UI (pick winner per beat)      │  │  │
│  │  │  • "Re-Do Beat N" for backward editing      │  │  │
│  │  │  • Server health indicator                  │  │  │
│  │  │  • ALL calls → localhost:5111/api/*          │  │  │
│  │  └─────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────┘  │
│                         │ fetch('/api/*')  ← same origin │
└─────────────────────────┼───────────────────────────────┘
                          │
┌─────────────────────────┼───────────────────────────────┐
│  Python Local Server (production_server.py)              │
│  http://localhost:5111                                   │
│                                                          │
│  SERVES:                                                 │
│  /storyboard              → the _prod.html file          │
│  /asset/<filename>        → MP4/MP3 from animation_clips/│
│                                                          │
│  API ENDPOINTS:                                          │
│  /api/health              → server alive + uptime        │
│  /api/state               → full production state        │
│  /api/animate             → submit Kling jobs            │
│  /api/animate/status      → poll animation results       │
│  /api/animate/redo        → re-do single beat (backward) │
│  /api/select              → record Kim's picks           │
│  /api/export              → export selections manifest   │
│                                                          │
│  FUTURE (v1.1/v1.2 — designed, not built):               │
│  /api/tts                 → ElevenLabs audio [v1.1]      │
│  /api/tts/status          → poll TTS results [v1.1]      │
│  /api/lipsync             → ByteDance lip-sync [v1.2]    │
│  /api/lipsync/status      → poll lip-sync [v1.2]         │
│                                                          │
│  HANDLES:                                                │
│  • ALL external API calls (WaveSpeed Kling v3)           │
│  • ALL file writes (MP4 to animation_clips/)             │
│  • ALL state persistence (production_state.json on disk) │
│  • API key storage (from API_KEYS_MASTER.md, never sent  │
│    to browser)                                           │
│  • Cost tracking (production_spend.json on disk)         │
│  • Retry logic (3 silent retries + batched polling)      │
│  • Stale process cleanup on startup                      │
└──────────────────────────────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────┐
│  External APIs                                           │
│  • WaveSpeed: Kling v3 animation generation              │
│    POST api.wavespeed.ai/api/v3/kwaivgi/kling-v3.0-pro/ │
│         image-to-video                                   │
│    GET  api.wavespeed.ai/api/v3/predictions/{id}/result  │
│  • Directus: motion prompts + voice profiles (cached)    │
└──────────────────────────────────────────────────────────┘
```

### 2.2 Why Single-Origin Solves All v2/v3 Issues

| Problem | v2 (broken) | v3 (risky) | v3.1 (safe) |
|---------|-------------|------------|-------------|
| CORS | file:// → https:// BLOCKED | file:// → localhost BLOCKED in Safari | Same origin (localhost → localhost) — no CORS |
| localStorage | Unavailable in Chrome from file:// | Disk JSON (OK) | Disk JSON (OK) |
| File writes | Browser can't write to disk | Python writes (OK) | Python writes (OK) |
| API keys | Embedded in HTML | Server-only (OK) | Server-only (OK) |
| Video playback | file:// src (fragile) | file:// src (fragile) | `http://localhost:5111/asset/file.mp4` (robust) |
| Threading | N/A | Single-threaded (BLOCKED) | `ThreadingHTTPServer` (concurrent) |
| Polling rate limits | Not addressed | Not addressed | Batched: 5 tasks/poll, 2s gaps |

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
│   └── production_server.py             [NEW: local server — serves HTML + APIs]
├── Event_1/
│   ├── storyboard_v14.html              [Kim's storyboard — NEVER MODIFIED]
│   ├── storyboard_v14_prod.html         [overlay-injected — served by Python]
│   ├── production_state.json            [persistent state — replaces localStorage]
│   ├── production_spend.json            [cost tracking]
│   └── animation_clips/
│       ├── beat_001_option_1.mp4
│       ├── beat_001_option_2.mp4
│       ├── beat_001_option_3.mp4
│       └── ...
└── .auto-memory/
    └── production_overlay_manifest.json [feature audit + injection log]
```

### 2.5 Startup Sequence (Claude Executes)

When Kim says "let's produce" or "fire up the overlay":

```
Step 1: Cleanup — kill stale server if running:
        kill $(cat Production/Event_1/production_server.pid) 2>/dev/null
        rm -f Production/Event_1/production_server.pid
Step 2: Run pre-injection gates (Section 2.3) — all 4 must pass
Step 3: Run inject_production_overlay.py → creates _prod.html
Step 4: Start production_server.py as background process
Step 5: Verify server alive: GET http://localhost:5111/api/health
Step 6: Open http://localhost:5111/storyboard in Kim's browser via:
        open "http://localhost:5111/storyboard"
Step 7: Kim sees storyboard with "Fire Away" button — ready to go
```

**Server lifecycle:**
- Runs as background Python process (survives Mac sleep/wake)
- Auto-shuts down after 4 hours of inactivity (no HTTP requests of ANY kind — API calls, asset serves, health checks, and storyboard page loads ALL count as activity. This prevents the server dying while Kim reviews video clips.)
- If Claude's session ends: server keeps running until inactivity timeout
- Next session start: Step 1 cleanup kills any stale process before starting fresh

---

## 2.6 Storyboard HTML Beat Array Structure

The storyboard builder (`build_storyboard.py`) embeds beat data as a JavaScript array in a `<script>` tag. The production server and injection script parse this structure to extract images and metadata.

**Exact format (from build_storyboard.py output):**
```html
<script>
  window.storyboardData = {
    "module": "M1",
    "event": 1,
    "lines": [
      {
        "line_number": 1,
        "speaker": "[Stage Direction]",
        "text": "The scene opens on a rocky hillside...",
        "image": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUg...",
        "audio_key": "m1_e1_line_001",
        "section": "Setup",
        "pause_ms": 1500
      },
      {
        "line_number": 2,
        "speaker": "Guide Bird",
        "text": "{childName}, look! The Heartwood is glowing again!",
        "image": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUg...",
        "audio_key": "m1_e1_line_002",
        "section": "Discovery",
        "pause_ms": 800
      }
    ]
  };
</script>
```

**Parsing method (Python):**
```python
import re, json

def extract_beats_from_html(html_content):
    """Extract beat array from storyboard HTML."""
    match = re.search(
        r'window\.storyboardData\s*=\s*(\{.*?\});',
        html_content,
        re.DOTALL
    )
    if not match:
        raise ValueError("Could not find window.storyboardData in HTML")
    data = json.loads(match.group(1))
    return data["lines"]  # List of beat dicts

def extract_image_base64(beat):
    """Extract base64 data URI from a beat's image field."""
    # beat["image"] is already "data:image/png;base64,iVBOR..."
    return beat["image"]  # Pass directly to WaveSpeed API
```

**Key fields per beat:**
- `image`: Full data URI (`data:image/png;base64,...`) — passed directly to WaveSpeed
- `speaker`: Character name — used to select motion prompt and anti-lip-sync constraints
- `text`: Dialogue line — used for TTS in v1.1 (not used in v1)
- `audio_key`: Audio identifier — used for file naming
- `section`: Narrative section — used for UI grouping

**Beat count:** Varies per event. M1E1 has 11 beats. Other events may have 15-25 beats. The server handles any count; the 11-beat references throughout this plan are examples, not limits.

---

## 2.7 API_KEYS_MASTER.md Format

The `Production/API_KEYS_MASTER.md` file is a Markdown document with API credentials in a structured format. The server parses it at startup.

**File format (simplified view):**
```markdown
## WaveSpeed
- API Key: `<REDACTED_PER_LD208_USE_DOPPLER>`
- Base URL: `https://api.wavespeed.ai/`

## ElevenLabs
- API Key: `<REDACTED_PER_LD208_USE_DOPPLER>`
- Base URL: `https://api.elevenlabs.io/v1/`

## Directus
- Token: `[token value]`
- Base URL: `https://directus.mindfulnest.app/`
```

**Parsing method (Python):**
```python
import re

def parse_api_keys(filepath):
    """Parse API keys from API_KEYS_MASTER.md."""
    content = open(filepath).read()
    keys = {}
    
    # Extract key values from markdown code spans
    for section, key_name in [
        ("WaveSpeed", "wavespeed"),
        ("ElevenLabs", "elevenlabs"),
        ("Directus", "directus")
    ]:
        # Find section, then extract first backtick-wrapped value after "Key:" or "Token:"
        section_match = re.search(
            rf'## {section}.*?(?:Key|Token):\s*`([^`]+)`',
            content, re.DOTALL
        )
        if section_match:
            keys[key_name] = section_match.group(1)
    
    return keys
```

---

## 3. Python Local Server (`production_server.py`)

### 3.1 Technology

- **Framework:** Python `http.server.ThreadingHTTPServer` (stdlib, Python 3.7+)
- **Threading:** `ThreadingHTTPServer` handles concurrent HTTP requests. One dedicated background thread for WaveSpeed polling (runs independently of request handling). A `threading.Lock()` protects all reads/writes to `production_state.json` and `production_spend.json` to prevent race conditions between the HTTP threads and the polling thread.
- **Range requests:** Custom request handler supports HTTP 206 Partial Content for video seeking. Parses `Range: bytes=X-Y` headers, returns partial file content with `Content-Range` header. Required for Safari video seeking (~40 lines of handler code).
- **Port:** 5111 (checked at startup; if occupied, kill stale process by PID)
- **Process management:** Server writes its PID to `production_server.pid` on startup. Cleanup uses this PID file instead of `pkill -f` (which could match wrong processes): `kill $(cat production_server.pid) 2>/dev/null; rm -f production_server.pid`
- **CORS:** Not needed — HTML served from same origin (`localhost:5111`)
- **Auth:** None required (localhost-only, single user)
- **Dependencies:** `requests` library (`pip install requests` if not present). Everything else is stdlib.

**Thread safety pattern:**
```python
import threading

class ProductionServer:
    def __init__(self):
        self.state_lock = threading.Lock()
    
    def read_state(self):
        with self.state_lock:
            return json.load(open('production_state.json'))
    
    def write_state(self, state):
        with self.state_lock:
            json.dump(state, open('production_state.json', 'w'), indent=2)
```

### 3.2 Static File Serving

The server serves two types of static files:

**Storyboard HTML:**
`GET /storyboard` → reads and returns `storyboard_v14_prod.html` from disk with `Content-Type: text/html`.

**Media assets:**
`GET /asset/<filename>` → reads and returns file from `animation_clips/` directory.
- `.mp4` files → `Content-Type: video/mp4`
- `.mp3` files → `Content-Type: audio/mpeg`
- Supports range requests for video seeking (HTTP 206 Partial Content)

This means all `<video>` and `<audio>` elements in the overlay use relative URLs like `/asset/beat_001_option_1.mp4` — no file:// paths anywhere.

### 3.3 State Management (Disk-Based)

All state lives in `production_state.json` on disk. The server reads it on startup, writes after every state change. No browser storage of any kind.

```json
{
  "event_id": "Event_1",
  "version": "v1",
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
          {
            "task_id": "abc123",
            "status": "completed",
            "file": "beat_001_option_1.mp4",
            "submitted_at": "2026-04-15T14:33:00Z",
            "size_bytes": 2400000
          },
          {
            "task_id": "def456",
            "status": "completed",
            "file": "beat_001_option_2.mp4",
            "submitted_at": "2026-04-15T14:33:00Z",
            "size_bytes": 2100000
          },
          {
            "task_id": "ghi789",
            "status": "polling",
            "file": null,
            "submitted_at": "2026-04-15T14:33:00Z",
            "retries": 1,
            "last_error": null
          }
        ],
        "selected_option": null
      }
    }
  }
}
```

**Resume logic:** On server start, read `production_state.json`. For any option with `status: "polling"` and `submitted_at` < 2 hours ago → resume polling. For `submitted_at` > 2 hours → mark as `"expired"`. For `status: "completed"` with file on disk → skip (already done).

### 3.4 API Endpoints (v1 MVP — Animation Only)

#### `GET /api/health`
```json
{"status": "ok", "uptime_seconds": 123, "event_id": "Event_1", "version": "v1"}
```
Browser polls every 30s. Shows 🟢/🔴 indicator.

#### `GET /api/state`
Returns full `production_state.json`. Browser calls on page load to restore UI state.

#### `POST /api/animate`
Triggers Kling animation generation.

**Request:**
```json
{
  "beats": ["beat_001", "beat_002", "beat_003"],
  "options_per_beat": 3,
  "mode": "all"
}
```

Modes:
- `"all"` — Fire Away: generate for all beats
- `"test"` — Test Mode: generate for specified beats only (1-3)
- `"retry"` — Retry: re-submit only failed/expired beats
- `"redo"` — Re-Do: re-generate a specific beat (backward editing)

**Server behavior:**
1. Read base64 image for each beat from the storyboard HTML on disk (NOT from browser)
2. Build motion prompt per beat (from Directus cache or default template)
3. Submit to WaveSpeed in staggered batches: 6 jobs (2 beats × 3 options), 2-second gap, next batch
4. Store task IDs in `production_state.json` immediately (before polling starts)
5. Return immediately: `{"submitted": 9, "beats_queued": 3, "status": "polling"}`
6. Background polling thread picks up new task IDs automatically

**WaveSpeed Kling v3 API (CORRECT — verified in prior session):**

Submit:
```
POST https://api.wavespeed.ai/api/v3/kwaivgi/kling-v3.0-pro/image-to-video

Headers:
  Authorization: Bearer {WAVESPEED_API_KEY}
  Content-Type: application/json

Body:
{
  "model": "kwaivgi/kling-v3.0-pro/image-to-video",
  "input": {
    "image": "data:image/png;base64,iVBORw0KG...",
    "prompt": "[motion prompt — see Section 4]",
    "negative_prompt": "lip sync, speaking, talking, mouth movement, dialogue, speech, open mouth, Chinese, audio, voice, singing",
    "duration": 5,
    "cfg_scale": 0.5,
    "seed": -1
  },
  "sound": false
}
```

- `image` field MUST be `data:image/png;base64,{base64_string}` format (NOT file:// URL)
- Image base64 extracted from storyboard HTML beat data
- **Image dimension validation (CLAUDE.md Rule 6):** Before submission, decode the base64 image and check dimensions. If shortest side < 600px, REJECT the beat and log a warning: `"Beat N image too small (WxH). Minimum shortest side: 600px."` This enforces Rule 6's 3-layer image enforcement at the production overlay level. Implementation: `from PIL import Image; img = Image.open(io.BytesIO(base64.b64decode(b64))); w, h = img.size; assert min(w, h) >= 600`

Poll:
```
GET https://api.wavespeed.ai/api/v3/predictions/{task_id}/result

Headers:
  Authorization: Bearer {WAVESPEED_API_KEY}
```

Response when complete:
```json
{
  "code": 200,
  "data": {
    "id": "task_abc123",
    "status": "completed",
    "outputs": ["https://storage.wavespeed.ai/...video.mp4"]
  }
}
```

Extract video URL: `response_json["data"]["outputs"][0]`
Download with `requests.get(url)` and save to `animation_clips/beat_XXX_option_N.mp4`.

#### `GET /api/animate/status`
Returns current animation progress. **This endpoint reads from `production_state.json`** (cached state updated by the background polling thread). It does NOT poll WaveSpeed directly — the polling thread handles all WaveSpeed communication. This makes the endpoint fast (<10ms response) and prevents the browser from triggering additional WaveSpeed requests.

Browser polls this every 10 seconds during generation.

```json
{
  "total_beats": 11,
  "completed": 7,
  "polling": 3,
  "failed": 1,
  "expired": 0,
  "cost_so_far": 4.68,
  "budget_remaining": 20.32,
  "beats": {
    "beat_001": {
      "status": "completed",
      "options": [
        {"file": "beat_001_option_1.mp4", "size_mb": 2.3, "url": "/asset/beat_001_option_1.mp4"},
        {"file": "beat_001_option_2.mp4", "size_mb": 2.1, "url": "/asset/beat_001_option_2.mp4"},
        {"file": "beat_001_option_3.mp4", "size_mb": 2.4, "url": "/asset/beat_001_option_3.mp4"}
      ]
    },
    "beat_002": {
      "status": "polling",
      "retries": 1,
      "eta_seconds": 45
    },
    "beat_005": {
      "status": "failed",
      "error": "3 retries exhausted",
      "can_retry": true
    }
  }
}
```

#### `POST /api/animate/redo`
Re-generates animation for a single beat. Used for backward editing — Kim approved beat 5 but later wants to try different options.

**Request:**
```json
{"beat": "beat_005", "options_per_beat": 3}
```

**Behavior (thread-safe — acquires `state_lock` for all state + file operations):**
1. Acquire `state_lock`
2. Read current beat_005 state, note old clip filenames
3. Clear beat_005's Phase 1 state (options, selection) in state dict
4. Write updated state to `production_state.json`
5. Release `state_lock`
6. Delete old clip files from `animation_clips/` (safe now — state no longer references them, polling thread won't touch them)
7. Re-submit 3 new Kling jobs for beat_005
8. Polling thread picks up new task IDs and downloads new clips

**Why this ordering matters:** The polling thread checks `production_state.json` to know which files to write. By clearing the beat's state BEFORE deleting old files, we prevent a race where the polling thread tries to write to a file that's being deleted. The `state_lock` ensures atomic read-modify-write of the state file.

#### `POST /api/select`
Records Kim's animation pick for a beat.
```json
{"beat": "beat_001", "selected_option": 2}
```
Updates `production_state.json`. Returns `{"ok": true}`.

#### `POST /api/export`
Exports final selections manifest.
```json
{
  "event_id": "Event_1",
  "exported_at": "2026-04-15T16:00:00Z",
  "beats": [
    {
      "beat": "beat_001",
      "speaker": "Guide Bird",
      "selected_animation": "beat_001_option_2.mp4",
      "section": "Story"
    }
  ],
  "total_cost": 4.68,
  "clips_directory": "Production/Event_1/animation_clips/"
}
```

**Dual output:**
1. **Writes `animation_selections.json` to disk** in the event directory (for downstream pipeline use)
2. **Triggers a browser file download** — the server returns the JSON with `Content-Disposition: attachment; filename="animation_selections.json"` header, which prompts a download dialog in Kim's browser. Kim sees the file appear in her Downloads folder.
3. **If re-exporting** (Kim changed selections), the server backs up the prior export to `animation_selections_backup.json` before overwriting.

**Browser-side download trigger (in injected JS):**
```javascript
// Export button handler
async function exportSelections() {
    const resp = await fetch('/api/export', {method: 'POST'});
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'animation_selections.json';
    a.click();
    URL.revokeObjectURL(url);
    showStatus('✅ Exported! Check your Downloads folder.');
}
```

### 3.5 Background Polling Thread

A single dedicated thread polls WaveSpeed for all pending tasks. Runs independently of HTTP request handling.

**Polling algorithm (batched to prevent rate-limit 429s):**
```python
def polling_loop():
    while server_running:
        pending_tasks = get_tasks_with_status("polling")
        
        # Batch: poll 5 tasks at a time, 2-second gaps
        for batch in chunks(pending_tasks, 5):
            for task in batch:
                result = poll_wavespeed(task["task_id"])
                if result["status"] == "completed":
                    download_video(result["outputs"][0], task["output_path"])
                    update_task_status(task, "completed")
                elif result["status"] == "failed":
                    handle_retry(task)  # Layer 2
            
            time.sleep(2)  # 2-second gap between batches
        
        time.sleep(10)  # 10-second gap between full polling cycles
```

### 3.6 Multi-Layer Retry Logic (Server-Side)

**Layer 1: Staggered submission**
- Submit in batches of 6 jobs (2 beats × 3 options), 2-second gap between batches
- Total submission time for 11 beats: ~12 seconds
- Prevents WaveSpeed rate-limit 429s from simultaneous blast

**Layer 2: 3 silent auto-retries with exponential backoff**
- On timeout or error: retry after 5s, 10s, 20s
- Server logs retries but browser only sees "Processing..."
- After 3 retries exhausted: mark as "failed", show error to Kim

**Layer 3: Re-poll before re-submit (cost guard)**
- Before any retry, re-poll the old task_id first
- ~30% of "failed" jobs actually completed (polling timed out, not the job)
- Only re-submit if re-poll confirms genuine failure
- Saves ~$0.78 per event on average

**Layer 4: Resume from disk state**
- On server restart: read `production_state.json`
- Resume polling for tasks < 2 hours old
- Mark tasks > 2 hours as "expired" (Kim can re-submit)

### 3.7 Cost Tracking

**Cost constants (hardcoded in server config):**
```python
# production_server.py — cost configuration
COST_PER_CLIP_KLING = 0.26     # WaveSpeed Kling v3.0 Pro, verified April 2026
COST_PER_CLIP_FAL_AI = 0.35    # fal.ai fallback (v1.1+)
COST_PER_TTS_CALL = 0.03       # ElevenLabs (v1.1+)
COST_PER_LIPSYNC = 0.26        # ByteDance via WaveSpeed (v1.2+)
DEFAULT_BUDGET = 32.00          # Per-event budget (raised from $25 per cost review)
```

`production_spend.json`:
```json
{
  "event_id": "Event_1",
  "budget": 32.00,
  "spent": {
    "kling_animation": 4.68,
    "retries": 0.26
  },
  "total_spent": 4.94,
  "budget_remaining": 27.06,
  "warnings_shown": [],
  "overrides": 0
}
```

**Thresholds:**
- 80% ($25.60): `/api/animate/status` returns `"budget_warning": true`; browser shows "⚠️ $25.60 of $32 used"
- 100% ($32): Server blocks new submissions; returns `"budget_blocked": true`; browser shows "⛔ Budget limit. [Override +$5] [Stop]"
- Override: `POST /api/budget/override` adds $5 → unblocks
- Every override logged to Directus `prod_activity_log` with timestamp and reason

---

## 4. Motion Prompt Strategy

### 4.1 Sources

**v1 uses default templates only.** Motion prompts in v1 are constructed from the beat's speaker field + default templates. Directus `prod_session_decisions` may contain per-beat custom prompts in the future (v1.1+), but v1 does NOT query Directus for prompts — it generates them from templates.

**Default template (v1 — the only source):**
```
[Character type] character [action context]. [Anti-lip-sync constraint]. Silent subtle idle movement only.
```

**Prompt construction logic (Python):**
```python
ANTI_LIPSYNC = {
    "bird": "Beak closed, no speech, no lip movement.",
    "default": "Mouth closed, no speech."
}

BIRD_SPEAKERS = {"Guide Bird", "Luna"}

def build_motion_prompt(beat):
    speaker = beat["speaker"]
    section = beat["section"]
    constraint = ANTI_LIPSYNC["bird"] if speaker in BIRD_SPEAKERS else ANTI_LIPSYNC["default"]
    
    # Default action based on section type
    if section in ("Setup", "Story"):
        action = "looking around with curiosity, subtle body movement"
    elif section in ("Discovery", "Introduction"):
        action = "gentle expressive gestures, slight head tilts"
    elif section == "Transition to Spell":
        action = "focused attention toward camera, slight forward lean"
    else:
        action = "subtle idle movement, gentle breathing"
    
    return f"Cartoon {speaker} character, {action}. {constraint} Silent subtle idle movement only."
```

**Personalization variables (`{childName}` etc.) are NOT used in motion prompts.** They appear in beat text for TTS (v1.1). Motion prompts describe visual action only.

**Examples:**
- Tessa (turtle), discovery: `"Cartoon turtle discovers a glowing stone, physical excitement, bouncing slightly. Mouth closed, no speech. Silent subtle idle movement only."`
- Guide Bird, teaching: `"Cartoon bird gestures with wings toward camera, focused attention. Beak closed, no speech, no lip movement. Silent subtle idle movement only."`
- Bork, frustrated: `"Cartoon creature throws arms up in frustration, bold movement. Mouth closed, no speech. Silent subtle idle movement only."`

### 4.2 Anti-Lip-Sync Hardening (CLAUDE.md Rule 8 — ALWAYS ON)

**Banned words in ALL motion prompts (server validates before submission):**
`speaking`, `speech`, `dialogue`, `lip sync`, `lip movement`, `mouth movement`, `beak movement`, `talking`, `singing`, `vocal`, `open mouth`

**Character-specific constraints:**
- Birds (Guide Bird, Luna): `"Beak closed, no speech, no lip movement"`
- Turtles (Tessa): `"Mouth closed, no speech"`
- All others: `"Mouth closed, no speech"`

**API parameters (ALWAYS set by server):**
- `sound: false`
- `negative_prompt: "lip sync, speaking, talking, mouth movement, dialogue, speech, open mouth, Chinese, audio, voice, singing"`
- `cfg_scale: 0.5`

**Server-side validation:** Before submitting ANY motion prompt to WaveSpeed, the server scans the prompt text for banned words. Behavior:
- If banned word found: strip it from the prompt, log a warning to server console, continue with cleaned prompt
- The server does NOT reject the request or return an error — it silently cleans and proceeds
- This is a safety net for custom prompts (v1.1+). Default templates (v1) will never contain banned words.

### 4.3 Duration (v1 MVP)

Default: 5 seconds for all animations in v1. Duration auto-matching from TTS length is a v1.1 feature (requires TTS to exist first).

---

## 5. Browser Overlay (Injected JS + CSS)

### 5.1 What the Injected JS Does (Thin Client)

The injected JavaScript is ~200-300 lines. It:
- Calls `http://localhost:5111/api/*` endpoints (same-origin — no CORS)
- Renders progress bars, video players, selection UI
- Polls `/api/animate/status` every 10 seconds during generation
- Polls `/api/health` every 30 seconds for server status
- Does NOT store any state (all state on server disk)
- Does NOT make external API calls
- Does NOT write files
- Does NOT contain API keys
- Does NOT use localStorage or IndexedDB

### 5.2 Server Health Indicator

Top-right corner:
- 🟢 "Production server online" — `/api/health` returns 200
- 🔴 "Server offline — ask Claude to restart" — `/api/health` fails or times out
- Polls every 30 seconds
- If offline for >60 seconds: show red banner across top of page

### 5.3 Phase 1 UI: Animation Generation

**"Fire Away" button:**
```
┌─────────────────────────────────────────────────────┐
│  🎬 PRODUCTION OVERLAY                    🟢 Online │
│                                                      │
│  ☐ Test Mode (select 1-3 beats to test first)       │
│                                                      │
│  [ 🚀 Fire Away — Generate All Animations ]          │
│                                                      │
│  Budget: $32.00 available                            │
│  Estimated cost: $8.58 (11 beats × 3 options × $0.26)│
│  Estimated time: ~3-5 minutes for all beats           │
└─────────────────────────────────────────────────────┘
```

- Shows estimated wait time BEFORE clicking (based on beat count × ~30s average per beat)
- Disables immediately on click (prevents double-click)
- Shows spinner: "🎬 Generating animations for 11 beats... first results in ~40 seconds"
- Calls `POST /api/animate` with `mode: "all"` (or `"test"` if Test Mode checked)

**Test Mode:**
- Checkbox above Fire Away
- When checked: Kim clicks individual beats to select them (1-3 max)
- Fire Away only generates selected beats
- Tooltip: "Try a few beats first to check quality before generating all"

**Per-beat animation display (after generation):**
```
┌─────────────────────────────────────────────────────┐
│ Beat 1 — Guide Bird [Story]                          │
│ "{childName}, look! The Heartwood is glowing again!" │
│                                                      │
│ [▶] Option 1 (2.3 MB)  ○                            │
│ [▶] Option 2 (2.1 MB)  ◉ ← selected                │
│ [▶] Option 3 (2.4 MB)  ○                            │
│                                                      │
│ [↻ Re-Do This Beat]                                 │
└─────────────────────────────────────────────────────┘
```

- Video elements use `<video src="/asset/beat_001_option_1.mp4">` (same-origin)
- Radio buttons for selection → calls `POST /api/select` on change
- "Re-Do This Beat" → calls `POST /api/animate/redo` → generates 3 new options

**Scroll-lock during video playback:**
When Kim clicks a video `[▶]` to preview an animation clip, the overlay pauses all live UI updates (new beat arrivals, progress bar changes, status messages) until the video ends or Kim clicks away. This prevents the page from scrolling or reflowing while she's watching. Implementation: the injected JS sets a `videoPlaying = true` flag on the `<video>` element's `play` event and clears it on `pause`/`ended`. The polling response handler checks this flag and queues DOM updates until `videoPlaying === false`, then flushes them all at once.

**Global progress bar:**
```
Phase 1: ████████░░ 7/11 beats ready, 3 processing, 1 retrying
Estimated time: ~2 minutes remaining
Cost: $4.68 of $32.00
```

**Phase completion:**
```
✅ All 11 beats ready! Select your favorites above.
Selections: 8/11 made (3 remaining)

[ Export Selections ] ← enabled when all 11 selected
```

### 5.4 Error Messages (Human-Friendly Only)

| Scenario | Message | Action |
|----------|---------|--------|
| Server offline | 🔴 "Production server is offline. Ask Claude to restart it." | Red banner |
| Beat timeout (auto-retrying) | "Beat 3 is taking longer than expected... retrying" | None (auto) |
| Beat failed (3 retries exhausted) | "Beat 3 couldn't generate. [Check Again — Free] [Re-Submit — $0.78] [Skip]" | Buttons — "Check Again" re-polls existing task IDs (zero cost, catches the ~30% that actually completed). "Re-Submit" creates new Kling jobs (costs 3 × $0.26). Distinct styling: Check Again is outlined/secondary, Re-Submit is filled/primary with cost shown. |
| All beats complete | "✅ 11 beats ready! Pick your favorites." | Selection UI |
| Budget 80% | "⚠️ $25.60 of $32 used" | Yellow banner |
| Budget 100% | "⛔ Budget limit reached. [Override +$5] [Stop]" | Buttons |
| Double-click prevention | Button disabled + spinner on first click | Auto |
| Server restarted mid-session | "Reconnected! Resuming from where you left off..." | Auto-resume |

No task IDs, no JSON, no technical jargon in ANY error message.

### 5.5 Export

Single button: **"📦 Export Selections"**

Creates `animation_selections.json` (via `POST /api/export`) containing beat-by-beat selection data. Kim can take this file to the next production step.

No "Download ZIP" or "View Summary" options in v1. Keep it simple.

---

## 6. Injection Script (`inject_production_overlay.py`)

### 6.1 What It Does

Python script run BY CLAUDE (not Kim):
1. Reads existing storyboard HTML from disk
2. MD5 hashes all embedded base64 images
3. Injects `<script>` block (~200-300 lines, thin UI client)
4. Injects `<style>` block (overlay CSS)
5. **Does NOT inject any raw HTML elements** (`<div>`, `<video>`, `<button>`, etc.). All overlay UI elements are created dynamically via `document.createElement()` + `appendChild()` inside the injected `<script>` block. This ensures strict CLAUDE.md Rule 7 Path B compliance: ONLY `<script>` and `<style>` blocks are patched.
6. Verifies all base64 images byte-identical after injection
7. Verifies NO API keys present in output HTML
8. Verifies ALL fetch URLs point to `localhost:5111` only
9. Verifies NO raw HTML elements were added outside `<script>` and `<style>` tags (diff check: count non-script/style tags in input vs output — must be identical)
10. Writes new `_prod.html` file (never overwrites original)
11. Generates `production_overlay_manifest.json`

### 6.2 CLI Usage

```bash
python3 Production/tools/inject_production_overlay.py \
  --input Production/Event_1/storyboard_v14.html \
  --output Production/Event_1/storyboard_v14_prod.html \
  --event-id "Event_1" \
  --validate-images \
  --validate-no-keys \
  --validate-localhost-only
```

No `--api-keys` or `--directus-token` flags. Keys live in the server only.

### 6.3 Validation Checks (BLOCKING)

After injection, the script runs these checks. ALL must pass or injection is aborted:

1. ✅ Beat count: output beat count matches input
2. ✅ Beat integrity: all beats have speaker + text + image
3. ✅ Image MD5: every embedded image hash matches input → output
4. ✅ No API keys: grep output for WaveSpeed key pattern, ElevenLabs key pattern — must find zero matches
5. ✅ Localhost only: all `fetch(` calls in injected JS target `localhost:5111` or relative paths — no external URLs
6. ✅ Original beat data: beat array in output is character-identical to input

If any check fails: abort, delete output file, print error with specific failing check.

### 6.4 Manifest

Written to `Production/.auto-memory/production_overlay_manifest.json`:

```json
{
  "timestamp": "2026-04-15T14:32:00Z",
  "input_file": "Production/Event_1/storyboard_v14.html",
  "output_file": "Production/Event_1/storyboard_v14_prod.html",
  "beat_count": 11,
  "injected_js_lines": 267,
  "injected_css_lines": 85,
  "image_validation": {
    "total_images": 11,
    "all_hashes_match": true
  },
  "security_validation": {
    "api_keys_found": 0,
    "external_urls_found": 0,
    "all_fetches_localhost": true
  },
  "status": "PASSED — all checks green"
}
```

---

## 7. API Credentials

**All credentials from `Production/API_KEYS_MASTER.md` — read by Python server at startup, NEVER in browser.**

| Service | Endpoint | Auth Header | v1 Usage |
|---------|----------|-------------|----------|
| WaveSpeed (Kling v3) | `https://api.wavespeed.ai/api/v3/` | `Authorization: Bearer {key}` | Animation generation + polling |
| Directus | `https://directus.mindfulnest.app/` | `Authorization: Bearer {token}` | Activity logging only in v1 (motion prompts use default templates, not Directus queries) |

**v1.1 additions (designed, not needed for v1):**

| Service | Endpoint | Auth Header |
|---------|----------|-------------|
| ElevenLabs (TTS) | `https://api.elevenlabs.io/v1/` | `xi-api-key: {key}` |
| WaveSpeed (ByteDance lip-sync) | `https://api.wavespeed.ai/api/v3/` | `Authorization: Bearer {key}` |

---

## 8. Governance & Compliance

### 8.1 CLAUDE.md Rules

| Rule | How v3.1 Complies |
|------|-------------------|
| **Rule 3 (Kim-confirmation)** | Explicit gate before writing `_prod.html` — Claude asks with exact filename, waits for confirmation |
| **Rule 7 (Two-Path Protocol)** | Extended Path B: injected JS is thin UI only (~200-300 lines), no API keys, no file I/O, no external URLs. MD5 validation on all images. Server is a separate tool. |
| **Rule 8 (Anti-Lip-Sync)** | Banned words validated server-side before every Kling submission. negative_prompt, cfg_scale:0.5, sound:false always set. |

### 8.2 Extended Path B Conditions (3 Required)

This overlay is classified as Extended Path B (not standard Path B, not Path A). Three conditions MUST hold:

1. **Injected JS is thin UI only:** No API keys, no file I/O, no external API calls, no state storage. All calls go to `localhost:5111`. Verified by injection script validation checks (Section 6.3).

2. **Kim-confirmation gate enforced:** Claude asks Kim with exact filename before every `_prod.html` write. Also asks before any `POST /api/animate` call that exceeds $10 estimated cost.

3. **Server code audit before first production use:** The implementing Claude thread must test `production_server.py` with a 3-beat sample before Kim's first real event. Audit checklist:
   - [ ] Server starts and serves HTML
   - [ ] Health endpoint responds
   - [ ] Animation submission works (3 beats)
   - [ ] Polling completes and downloads MP4s
   - [ ] State persists across server restart
   - [ ] No API keys leak to browser (check network tab)

### 8.3 Session Spend Tracking

- Tracked in `production_spend.json` on disk (survives everything)
- Also logged to Directus `prod_activity_log` after each generation batch
- Warn at 80%, block at 100%, override in $5 increments
- v1 budget covers animation only (~$0.26/clip × 3 options × N beats)

---

## 9. v1.1 and v1.2 Design Notes (For Future Implementation)

### v1.1: TTS Generation (ElevenLabs)

**New endpoints:**
- `POST /api/tts` — generate TTS for selected beats
- `GET /api/tts/status` — poll TTS progress

**Key details:**
- ElevenLabs returns raw MP3 binary (NOT JSON) — handle with `response.content`
- **Myrrhin voice lock (MANDATORY):** stability=0.70, speed=0.50, hardcoded regardless of Directus
- Personalization variables (`{childName}`, `{therapistName}`, etc.) substituted by server before API call
- Sequential submission: 1 TTS request at a time, 500ms delay (ElevenLabs rate limit protection)
- Auto-recalculate animation duration from TTS length: if TTS > 5s, re-submit Kling at 10s

**New UI elements:**
- "Generate TTS" button (appears after Phase 1 selections made)
- Audio player per beat with duration display
- Myrrhin lock indicator: "🔒 Voice locked" for Myrrhin beats

### v1.2: Lip-Sync (ByteDance via WaveSpeed)

**New endpoints:**
- `POST /api/lipsync` — submit lip-sync jobs
- `GET /api/lipsync/status` — poll progress

**Key details:**
- ByteDance needs uploaded video + audio URLs (not local paths). Server uploads to WaveSpeed storage first.
- **Lip-Sync Review Gate (MANDATORY per Rule 8):** Kim must approve every clip. Batch approval UI: grid of all clips, Kim flags bad ones, rest auto-approved.
- fal.ai fallback with $5 cap if WaveSpeed fails 3 times

**New UI elements:**
- "Send for Lip Sync" button
- Batch review grid (not individual approvals — fixes v2 tedium issue)
- Single "📦 Download Ready-to-Ship" button for final export

---

## 10. Implementation Checklist (v1 MVP Only)

### Day 1: Infrastructure
- [ ] Build `production_server.py` scaffold:
  - [ ] `ThreadingHTTPServer` on port 5111
  - [ ] `threading.Lock()` for all state file reads/writes
  - [ ] HTTP 206 range request handler for video seeking (~40 lines)
  - [ ] Static file serving (`/storyboard` for HTML, `/asset/*` for MP4/MP3)
  - [ ] `/api/health` endpoint
  - [ ] `/api/state` endpoint (read `production_state.json`)
  - [ ] PID file write on startup (`production_server.pid`)
  - [ ] PID-based cleanup on startup (kill stale process by PID, not pkill)
  - [ ] API key parsing from `API_KEYS_MASTER.md` (see Section 2.7 for format)
  - [ ] Beat array extraction from storyboard HTML (see Section 2.6 for format)
- [ ] Build `inject_production_overlay.py` scaffold:
  - [ ] HTML parsing (extract beat array)
  - [ ] MD5 image hashing
  - [ ] JS/CSS injection
  - [ ] 6-point validation (Section 6.3)
  - [ ] Manifest generation
- [ ] Test: server starts, health check works, serves HTML, injection validates

### Days 2-3: Phase 1 Animation
- [ ] Implement `/api/animate` endpoint:
  - [ ] Extract base64 images from storyboard HTML
  - [ ] Build motion prompts (Directus cache + defaults)
  - [ ] Validate prompts against banned words list (Rule 8)
  - [ ] Submit to WaveSpeed Kling in staggered batches (6 jobs, 2s gaps)
  - [ ] Store task IDs in `production_state.json`
- [ ] Implement background polling thread:
  - [ ] Batched polling (5 tasks/poll, 2s gaps)
  - [ ] Download completed MP4s to `animation_clips/`
  - [ ] 3 silent retries with exponential backoff (5s, 10s, 20s)
  - [ ] Re-poll before re-submit (cost guard)
- [ ] Implement `/api/animate/status` endpoint
- [ ] Implement `/api/animate/redo` endpoint (backward editing)
- [ ] Implement `/api/select` endpoint
- [ ] Implement `/api/export` endpoint
- [ ] Implement cost tracking (`production_spend.json`)
- [ ] Build Phase 1 overlay JS:
  - [ ] Fire Away button with disable-on-click
  - [ ] Test Mode checkbox with beat selection
  - [ ] Progress bar with live counter
  - [ ] Per-beat video players (3 options each)
  - [ ] Radio button selection
  - [ ] Re-Do Beat button
  - [ ] Server health indicator
  - [ ] Error messages (human-friendly)
  - [ ] Budget warnings (80%, 100%, override)
  - [ ] Export button

### Day 4: Integration & QA
- [ ] End-to-end test: 3 beats through full Phase 1
- [ ] Resume test: kill server mid-generation, restart, verify recovery
- [ ] Verify: no API keys in HTML: `grep -c '8e88bb702e31\|11f1c7afb99b' storyboard_*_prod.html` must return 0
- [ ] Verify: no external URLs in injected JS: `grep -c 'wavespeed.ai\|elevenlabs.io\|directus.mindfulnest' storyboard_*_prod.html` must return 0
- [ ] Verify: all fetch calls target localhost: `grep "fetch(" storyboard_*_prod.html` — every match must contain `localhost:5111` or be a relative path
- [ ] Verify: video playback works in Safari AND Chrome
- [ ] Verify: cost tracking accurate
- [ ] Verify: stale process cleanup works
- [ ] Log production event to Directus `prod_activity_log`

### Day 5: Delivery to Kim
- [ ] Run full 11-beat generation for M1E1
- [ ] Open `http://localhost:5111/storyboard` for Kim
- [ ] Walk Kim through: Fire Away → review → select → export
- [ ] Collect feedback for v1.1 planning

---

## 11. Questions for Implementation Thread

Before starting, verify these:

1. Does Python `ThreadingHTTPServer` handle 2-3 concurrent requests reliably for our use case (polling + status checks)? If issues arise, upgrade to Flask `threaded=True`.
2. Does `open "http://localhost:5111/storyboard"` open in Kim's default browser on Mac? (Expected: yes)
3. What's the exact format of motion prompts in Directus `prod_session_decisions`? One prompt per beat, or one per creature per section?
4. Does WaveSpeed have a documented rate limit? If not, start conservative (6 jobs/batch, 2s gap) and adjust based on 429 responses.

**Success criteria for v1:**
- Kim clicks Fire Away → 3 animation options appear per beat within 5 minutes
- Kim selects winners → export works
- Resume: kill server, restart → state recovered, no re-generation needed
- Budget tracked and enforced
- No API keys visible in browser (network tab clean)

---

## 12. Summary: v2 → v3 → v3.1 Evolution

| Aspect | v2 | v3 | v3.1 |
|--------|-----|-----|------|
| Architecture | Pure browser | Hybrid (file:// + localhost) | Hybrid (localhost serves everything) |
| HTML delivery | file:// from Finder | file:// from Finder | `http://localhost:5111/storyboard` |
| CORS status | BROKEN | RISKY (Safari blocks) | SAFE (same origin) |
| Threading | N/A | Not addressed | `ThreadingHTTPServer` |
| Polling | Not addressed | Not addressed | Batched (5/poll, 2s gaps) |
| Scope | All 3 phases | All 3 phases | Phase 1 MVP only |
| Timeline | 4 days | 5 days | 5 days (Phase 1 only) |
| Video playback | file:// src | file:// src | `/asset/` localhost src |
| Backward editing | Not available | Not available | "Re-Do Beat N" button |
| Test Mode | Not available | Added | Refined UX |
| Rule 7 class | Questionable Path B | Extended Path B | Extended Path B + 3 conditions |

---

**END OF DOCUMENT**

This plan covers v1 (animation only). It is self-contained and ready for a new Claude thread to implement Phase 1 through the full checklist above. v1.1 (TTS) and v1.2 (lip-sync) design notes are included for continuity but are NOT in scope for v1 implementation.
