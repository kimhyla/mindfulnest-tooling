# Storyboard Production Overlay — Technical Plan v2 (Corrected & Complete)

**Date:** April 15, 2026  
**Status:** Ready for implementation by new Claude thread  
**Owner:** Claude (Phase 1-3 implementation) → Kim (review/selection gates)  
**Target Timeline:** Phase 1 = 2 days, Phase 2 = 1 day, Phase 3 = 1 day  

---

## 1. Executive Summary

The Storyboard Production Overlay is a **Path B JavaScript injection** (CLAUDE.md Rule 7) that extends the existing `build_storyboard.py`-generated HTML with production-grade animation, TTS, and lip-sync generation capabilities. It allows Kim to go from arranged storyboard beats to production-ready video clips in a single session, without leaving the HTML interface.

**Problem solved:**
- Current workflow: Kim arranges beats in storyboard → Claude exports → hand-submits to Kling/ElevenLabs/ByteDance APIs → polls manually → Kim reviews separately → clips integrated manually. Friction: file hunting, multi-step handoffs, manual polling, late-night frustration.
- New workflow: Kim arranges beats → clicks "Fire Away" → 3 animation options + TTS appear inline per beat → picks winners → clicks "Send for Lip Sync" → final clips in storyboard. Zero file hunting.

**Why Path B (JS injection), not rebuild the storyboard builder:**
- CLAUDE.md Rule 7 reserves builder modifications for structural changes (images, dialogue structure). Animation/TTS generation is behavioral — pure JS + API calls. Path B (JS injection) is lighter, doesn't risk existing beat data, doesn't require re-generating base64 images.

**Why incremental phases:**
- Phase 1 (Animation): Kling is the blocking dependency. TTS and lip-sync both depend on animation results. Build and stress-test Phase 1 first, then layer TTS and lip-sync.
- Each phase is independently useful (Phase 1 alone = 3 animation options per beat; Phase 1+2 = animation + TTS; all 3 = full production pipeline).

---

## 2. Architecture Overview

### 2.1 Path B: JS Injection Without Rebuild

The overlay is a **new Python tool** (`inject_production_overlay.py`) that:
1. **Reads** the existing storyboard HTML from disk
2. **Parses** the embedded beat data structure (speaker, text, image base64, audio_key, pause, section)
3. **Injects** new `<script>` and `<style>` blocks with production UI and API integrations
4. **Validates** all base64 image data is byte-identical before/after (MD5 hashing per CLAUDE.md Rule 7)
5. **Writes** a new `.html` file (e.g., `storyboard_v14_prod.html`) — never overwrites the original
6. **Outputs** a manifest of injected features for validation

**Rationale for Path B:**
- Existing beat structure is clean and JSON-serializable. No need to rebuild.
- Animation/TTS generation is a new behavior layer, not a structural change.
- Preserves all drag-drop state, image assignments, and existing storyboard edits.
- Keeps builder pipeline clean; builder remains "beats + images" only.
- Rollback is trivial: delete the `_prod.html` file, original stays untouched.

### 2.2 Pre-Injection Gates (BLOCKING)

**Before Claude injects the overlay:**

1. **Browser-edit gate (CLAUDE.md Rule 7):** Ask Kim: *"Have you made edits in the browser (dialogue, drag-drop, image assignments) that haven't been exported?"* If yes, she MUST click "Export Locked Sequence" first. The HTML file on disk does NOT contain browser-memory edits. Rebuilding from a stale disk file = silent data loss.

2. **Export-first protocol (CLAUDE.md Rule 7):** Kim must export her storyboard selections BEFORE the overlay is injected, because the overlay reads from the HTML file on disk, not browser memory. If Kim's drag-drop image assignments were made in the browser but never exported, the overlay won't see them.

3. **MD5 validation (CLAUDE.md Rule 7 + Rule 9):** After injection, the script MUST verify all base64 image data is byte-identical before/after. Compute MD5 hash for every embedded image in the input HTML, then verify it matches the output HTML. Abort and alert Kim if any differ.

**All three gates are BLOCKING — do not proceed without confirmation.**

### 2.3 File Structure

```
Production/
├── tools/
│   ├── build_storyboard.py                    [existing builder]
│   └── inject_production_overlay.py            [NEW: Phase B tool]
├── Event_1/
│   ├── storyboard_v14.html                    [Kim's edited storyboard — NEVER MODIFIED]
│   ├── storyboard_v14_prod.html               [NEW: injected overlay — rollback by deleting]
│   └── animation_clips/
│       ├── beat_001_kling_option1.mp4
│       ├── beat_001_kling_option2.mp4
│       ├── beat_001_kling_option3.mp4
│       ├── beat_001_tts_audio.mp3
│       └── beat_001_lipsync_final.mp4
└── .auto-memory/
    └── production_overlay_manifest.json       [feature audit + injection log]
```

### 2.4 Storyboard Data Structure (Read-Only In Production Overlay)

The existing storyboard embeds beat data as a JavaScript array. The overlay reads this structure (does NOT modify it):

```javascript
// Example beat object (read from storyboard HTML)
{
  beat_index: 0,
  section: "Story",                    // or "Phase A", "Resolution", etc.
  speaker: "Guide Bird",
  text: "{childName}, look! The Heartwood is glowing again!",
  image: "data:image/png;base64,iVBORw0KG...",
  audio_key: "m2_e1_beat_001",
  pause_ms: 1500,
  duration_seconds: 8,                 // inferred from TTS length (Phase 2+)
  // PRODUCTION OVERLAY ADDS (separate state object):
  animation_options: [
    { id: "option1", url: "file:///Users/kimberlysmith/.../beat_001_kling_option1.mp4", status: "ready", selected: false },
    { id: "option2", url: "file:///Users/kimberlysmith/.../beat_001_kling_option2.mp4", status: "ready", selected: false },
    { id: "option3", url: "file:///Users/kimberlysmith/.../beat_001_kling_option3.mp4", status: "ready", selected: true }
  ],
  tts_audio: {
    url: "file:///Users/kimberlysmith/.../beat_001_tts_audio.mp3",
    voice_id: "Ember",
    status: "ready"
  },
  lipsync_final: {
    url: "file:///Users/kimberlysmith/.../beat_001_lipsync_final.mp4",
    status: "ready"
  },
  production_status: "phase_2_approved"  // "phase_1_pending", "phase_1_options_ready", "phase_1_selected", "phase_2_approved", "phase_3_lipsync_done"
}
```

**Key design choice:** Overlay maintains a **SEPARATE production state object** parallel to the beat array. The original beat array is read-only. Production state (animation options, TTS, lipsync) lives in its own object keyed by beat index. This ensures the beat data is never accidentally mutated.

---

## 3. Phase 1: Animation Generation (Kling v3 via WaveSpeed)

### 3.1 Goals

- Generate 3 Kling v3 animation options per beat from the embedded image + a motion prompt
- Store clips in `animation_clips/` with standard naming
- Display options inline in storyboard with play buttons + selection UI
- Handle WaveSpeed timeouts gracefully with multi-layer retry logic (3 silent auto-retries before surfacing errors)
- Support resume from partial completion (don't re-generate clips that already exist)
- Prevent double-clicks and cost overruns with spend tracking

### 3.2 Motion Prompt Strategy

Motion prompts are beat-specific and pulled from Directus `prod_session_decisions` collection (cached at session start). Each beat's prompt includes:

**Standard structure (always):**
```
[Character name] [creature type] [action from context] [anti-lip-sync constraints]
```

**Example prompts:**

- **Tessa (turtle), discover moment:** "A turtle character discovers a glowing stone. Physical excitement, bouncing slightly. Beak closed, no speech, no lip movement. Subtle idle movement only."
- **Luna (owl), teaching moment:** "An owl stands still, gesturing with wings toward the glowing crystal. Focused attention. Beak closed, no speech, no mouth movement. Silent motion only."
- **Bork (creature), frustrated moment:** "A creature throws its arms up in frustration. Beak/mouth closed, no speech. Bold directional movement, then settle."

**Anti-lip-sync hardening (ALWAYS in prompt, CLAUDE.md Rule 8):**
- **Banned words (DELETE from all prompts):** `speaking`, `speech`, `dialogue`, `lip sync`, `lip movement`, `mouth movement`, `beak movement`, `talking`, `singing`, `vocal`
- **For bird characters:** explicit "Beak closed, no speech, no lip movement"
- **For non-bird characters:** "Mouth closed, no speech"
- **All prompts end with:** "Silent subtle idle movement only" or "no dialogue in video"

**Duration auto-matching:**
- Animation duration = ceil(audio_length_seconds / 5) × 5, capped at 10s max
  - Example: 3.2s audio → 5s animation, 7.8s audio → 10s animation
- **Fallback (Phase 1):** Default to 5s if audio not yet generated
- **Upgrade (Phase 2):** After TTS generation, recalculate and re-run Kling if needed

### 3.3 WaveSpeed Kling API Call Pattern (CORRECTED)

**Endpoint:** `POST https://api.wavespeed.ai/api/v3/kwaivgi/kling-v3.0-pro/image-to-video`

**Request body (CORRECTED — image MUST be data URI, not file:// URL):**
```json
{
  "model": "kwaivgi/kling-v3.0-pro/image-to-video",
  "input": {
    "image": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEA...",
    "prompt": "[as above]",
    "negative_prompt": "lip sync, speaking, talking, mouth movement, dialogue, speech, open mouth, Chinese, audio, voice, singing",
    "duration": 5,
    "cfg_scale": 0.5,
    "seed": -1
  },
  "sound": false
}
```

**Key corrections from v1:**
- `image` field MUST use `data:image/png;base64,{base64_string}` format, NOT `file://` URLs
- The overlay MUST extract the base64 image data from the storyboard beat and pass it as a data URI
- Response field is NOT `data.output.video_url` — it's `data.data.outputs[0]`

**Response (initial):**
```json
{
  "code": 200,
  "data": {
    "id": "task_abc123xyz",
    "status": "created"
  }
}
```

**Polling endpoint (CORRECTED):** `GET https://api.wavespeed.ai/api/v3/predictions/{task_id}/result` (NOT `/api/v3/task/{task_id}`)

**Polling response (complete):**
```json
{
  "code": 200,
  "data": {
    "id": "task_abc123xyz",
    "status": "completed",
    "outputs": ["https://storage.wavespeed.ai/...video.mp4"]
  }
}
```

**Extract video URL:** `response.data.data.outputs[0]` — not `response.data.output.video_url`

### 3.4 Multi-Layer Retry Logic & Resilience (REVISED)

**WaveSpeed timeout issue:** Intermittent connection failures, especially during high load. Multi-layer recovery strategy per resilience debate:

**Layer 1: Submit all jobs immediately (parallel processing)**
- Submit all beats' animation jobs to WaveSpeed at once (they queue and process in parallel on WaveSpeed servers)
- Do NOT poll immediately — WaveSpeed needs time to accept and queue the job
- Return immediately with array of task_ids and status="submitted"

**Layer 2: 3 silent auto-retries with exponential backoff BEFORE showing error to Kim**
- If API call times out: retry with backoff (5s, 10s, 20s)
- If task stays "created" for >2 min: poll again after exponential backoff
- Kim's mental model: "Some are taking longer than others" (she sees "processing", not individual retries)
- Only show "Failed" status after all 3 retries exhausted

**Layer 3: Sequential polling (2 at a time, staggered)**
- Poll sequentially (2 beats at a time, staggered every 5 seconds) to avoid timeout cascades
- Do NOT poll all 20 beats simultaneously — this creates a thundering herd and timeout waterfall
- Stagger: poll beats [1-2] → wait 5s → poll beats [3-4] → wait 5s → etc.

**Layer 4: Re-poll before re-submit (cost guard)**
- Before any retry, always re-poll the old task_id first (~30% of "failed" jobs actually completed but polling timed out)
- Re-polling recovers these for free
- Only re-submit if re-poll confirms failure or task_id expired (>2 hours old)

**Layer 5: Session persistence & resume**
- Store all task IDs and status in browser localStorage (available because HTML runs locally from file:// on Kim's Mac, NOT in claude.ai)
- Also store in IndexedDB as fallback for very large state (future-proofing)
- On reload: restore task state and resume polling (see Section 3.7)
- If task ID is >2 hours old and still "created", mark for fresh submission (task expired)

**localStorage structure:**
```javascript
// Available because this HTML runs locally from file:// on Kim's Mac
{
  "mindfulnest_prod_tasks_Event_1": {
    "beat_001": {
      "phase_1": { 
        task_id: "task_abc123",
        status: "polling",           // "submitted", "polling", "completed", "failed"
        retries: 2,
        last_poll: 1713191400000,
        submitted_at: 1713191200000,
        cost_estimate: 0.26,
        error_message: null
      },
      "phase_2": null,
      "phase_3": null
    },
    "beat_002": { ... }
  }
}
```

**IndexedDB fallback (for future large state):**
- Store same structure in IndexedDB `mindfulnest_prod_db` with object store `tasks`
- Read from localStorage on page load; if corrupted, restore from IndexedDB
- Provides resilience against localStorage size limits (5MB) and accidental clearing

### 3.5 Phase 1 UI & Workflow

**"Fire Away" button (single big action):**
- Location: Top of overlay, prominently placed
- State: `enabled` (ready), `disabled` (already running), `generating...` (in progress with spinner)
- Behavior: Disables immediately on first click (prevent double-click), shows spinner with "Generating animations..."
- Click action: 
  1. Disable button immediately
  2. Submit all beat animation jobs to WaveSpeed (parallel)
  3. Start polling sequence (2 at a time, staggered)
  4. Update UI every 10 seconds with progress

**Per-beat animation options (after Phase 1 completes):**
```
Beat 001 (Guide Bird speaks)
─────────────────────────────
[Play] Option 1 (2.3 MB) ○ select  |  Cost: $0.26
[Play] Option 2 (2.1 MB) ◉ select  |  Cost: $0.26  ← Currently selected
[Play] Option 3 (2.4 MB) ○ select  |  Cost: $0.26

Beat 002 (Luna reacts)
─────────────────────────────
[Generating...] [Retry]
```

**Beat play button behavior:**
- Click to play inline preview (Web Audio API + HTML5 video element, if file:// URLs work)
- Fallback: "Click to download preview" with file:// URL
- Display video dimensions (should be 1280×720 per storyboard standard)

**Progress bar (global):**
- Shows "Generating 1/20 beats..." with live counter
- Updates every 10 seconds as beats complete
- Color: blue (generating), green (done), red (failed beats)
- Below: "Estimated cost: $5.20 (from 20 beats × $0.26/beat)"

**Phase summary (bottom of overlay):**
```
Phase 1 Animation: 20/20 ready  [Skip Phase] [Approve All] [Next: Phase 2]
```

### 3.6 Error Messages & User-Facing Flow (REVISED)

When Kim clicks "Fire Away", here's EXACTLY what she sees:

1. **Immediate feedback (0s):** Button disables, spinner appears. "🎬 Generating animations for 20 beats..."
2. **First status check (after 10s):** "Generating... 3 beats ready, 17 processing"
3. **Continued polling (every 10s):** "6 beats ready, 14 processing" → "12 beats ready, 8 processing" → etc.
4. **All complete (final):** "✅ Animation complete! 20 beats ready. [Approve All] [Next: Phase 2]"

**Error scenarios & exact human-friendly messages:**

| Scenario | Message Shown | Action Available |
|----------|---------------|------------------|
| Beat submission timeout (API unreachable) | "Couldn't connect to animation service — retrying automatically..." | None (auto-retries 3x silently) |
| Beat polling timeout (task stalled) | "Taking longer than expected (2 min)... checking again in 30 seconds" | None (auto-retries, then waits 30s) |
| 6/11 complete, 5 failed | "6 beats ready. 5 need another try. Proceed?" | [Retry Failed Beats] button |
| Browser closed & reopened (mid-generation) | "Found 6 completed beats and 2 still processing. Pick up where you left off?" | [Resume] [Start Over] |
| WaveSpeed completely offline | ⛔ **RED BANNER** "Animation service is offline — try again later" | [Retry] button (disabled until service returns) |
| User double-clicks "Fire Away" | Button disables on first click, spinner appears | Button re-enables only when generation completes |
| Spend reaches 80% of $25 budget | "⚠️ You've used $20 of $25. Current retry would cost $1.13. Proceed?" | [Proceed] [Cancel] |
| Spend reaches 100% of $25 budget | ⛔ "Budget limit reached ($25). Override available for additional cost." | [Override (+$5)] [Cancel] [Stop] |

**No task IDs or JSON in error messages** — only human-friendly status and actions.

### 3.7 Resume From Partial Completion

**Scenario:** Kim clicks "Fire Away", 12 beats complete, then connection dies on beat 13. Later, Kim reloads the storyboard.

**Behavior:**
1. Overlay reads localStorage `mindfulnest_prod_tasks_Event_1` on page load
2. For each beat:
   - If `animation_clips/beat_XXX_kling_option1.mp4` exists on disk → mark as "already generated" (green checkmark)
   - If `task_id` exists in localStorage but no file → resume polling where it left off
   - If no `task_id` → start fresh (grayed out, waiting for "Fire Away" click)
3. UI shows: "✅ 13 clips ready (from prior run), resuming beat 13 (polling)... Waiting for beats 14-20..."
4. User can:
   - Click "Continue from beat 13" → resume polling on incomplete beats
   - Click "Start Fresh" → clear localStorage and regenerate all (costly)
   - Click "Skip to Phase 2" → use the 13 completed beats + skip remaining

**No re-work:** Kling task IDs expire after ~2 hours. If resuming after >2 hours, the overlay detects expired IDs (via `submitted_at` timestamp) and marks them "Expired — needs fresh submit". User can re-generate for cost.

### 3.8 Cost Tracking & Budget Management

**Default budget:** $25/event (per CLAUDE.md Rule additions)

**Tracking:**
- Track cumulative spend in localStorage: `mindfulnest_prod_spend_Event_1`
- Each beat costs ~$0.26 (Kling pricing)
- Before batch retry, show: "3 jobs need retry ($1.13). 2 jobs recovered (no cost). Proceed?" (re-poll cost guard)

**Warnings & limits:**
- At 80% ($20): Show warning "⚠️ You've used $20 of $25. Current retry would cost $1.13. Proceed?"
- At 100% ($25): Block with "⛔ Budget limit reached. Override available for additional $5 cost." + [Override] button
- Override adds $5 increment (so $25 → $30 → $35, etc.)
- Log each spend increment to localStorage for historical tracking

---

## 4. Phase 2: TTS Generation (ElevenLabs v3)

### 4.1 Goals

- Generate ElevenLabs TTS audio for each beat's dialogue
- Parse speaker and dialogue from beat text (with personalization variables)
- Match speaker to correct voice profile (from Directus `prod_voice_profiles`)
- Save MP3 clips to `animation_clips/beat_XXX_tts_audio.mp3`
- Display audio inline with duration + waveform preview
- Auto-calculate animation duration from audio length and re-run Kling if needed

### 4.2 Voice Profile Mapping (with Myrrhin Lock)

Voice assignments come from Directus `prod_voice_profiles` collection (queried at session start). Example:

```json
{
  "character": "Guide Bird",
  "voice_id": "21A8qXBP...",
  "stability": 0.50,
  "similarity_boost": 0.75,
  "style": 0,
  "use_speaker_boost": true
}
```

**Special case: Myrrhin (narrator) — LOCKED SETTINGS (CLAUDE.md Rule 12):**
- **Stability: 0.70 (HARDCODED, ignore Directus)**
- **Speed: 0.50 (HARDCODED, ignore Directus)**
- ElevenLabs library voice (not a custom clone)
- All Phase B meditations use Myrrhin's locked voice

**Personalization variables (from beat text):**
- `{childName}` → from session context
- `{therapistName}` → from session context
- `{parentName}` → from session context
- `{parentTitle}` → from session context (e.g., "Dr.", "Ms.")
- `{chosenGuideName}` → from session context
- `{childPronoun}` → he/she (auto-derived from boy/girl selection)
- `{childPronounObject}` → him/her
- `{childPronounPossessive}` → his/her

**All variables must be replaced BEFORE sending to ElevenLabs.** The API returns raw MP3 binary (not JSON).

### 4.3 ElevenLabs API Call Pattern (CORRECTED)

**Endpoint:** `POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=mp3_128`

**Request headers:**
```
Authorization: Bearer {API_KEY}
Content-Type: application/json
```

**Request body:**
```json
{
  "text": "Sophia, look! The Heartwood is glowing again!",
  "model_id": "eleven_multilingual_v3",
  "voice_settings": {
    "stability": 0.50,
    "similarity_boost": 0.75,
    "style": 0,
    "use_speaker_boost": true
  }
}
```

**Response (CORRECTED — raw MP3 binary, not JSON):**
- ElevenLabs returns **raw MP3 binary data**, not JSON
- Handle with `response.arrayBuffer()`, then create a Blob URL for playback and save to disk
- Do NOT try to parse as JSON — this will fail with "Unexpected token 0xFF..."

**Code pattern (JavaScript):**
```javascript
const response = await fetch('https://api.elevenlabs.io/v1/text-to-speech/{voice_id}...', {
  method: 'POST',
  headers: { 'Authorization': `Bearer ${API_KEY}`, 'Content-Type': 'application/json' },
  body: JSON.stringify({ text, model_id, voice_settings })
});

// CRITICAL: handle as binary, not JSON
const arrayBuffer = await response.arrayBuffer();
const blob = new Blob([arrayBuffer], { type: 'audio/mpeg' });
const blobUrl = URL.createObjectURL(blob);

// Save to disk (via file:// URL)
const filename = `animation_clips/beat_${beat_index}_tts_audio.mp3`;
// [use file write mechanism — details in Phase 2 implementation]

// Playback preview
const audioElement = new Audio();
audioElement.src = blobUrl;
audioElement.play();
```

### 4.4 Phase 2 UI & Workflow

**"Generate TTS Audio" button:**
- Appears only after Phase 1 is approved
- State: `enabled` (ready), `generating...` (in progress), `complete`
- Click: Generates TTS for all approved beats in parallel (similar to Phase 1)

**Per-beat audio display:**
```
Beat 001 (Guide Bird speaks)
─────────────────────────────
"Sophia, look! The Heartwood is glowing again!"
Voice: Guide Bird (ElevenLabs)
[Play] 2.3 seconds | [Download] | Cost: $0.03
Duration auto-updated animation to 5 seconds (from 2.3s audio)
```

**TTS progress:**
```
Phase 2 TTS Audio: 18/20 generated  [Retry Failed] [Next: Phase 3]
Beat 001: ✓ Ready
Beat 002: Generating...
...
```

---

## 5. Phase 3: Lip-Sync Generation (ByteDance via WaveSpeed)

### 5.1 Goals

- Composite final video: animation clip (Phase 1) + TTS audio (Phase 2) + ByteDance lip-sync
- Detect mouth/beak movement and reject (CLAUDE.md Rule 8 lip-sync gate)
- Store final clips in `animation_clips/beat_XXX_lipsync_final.mp4`
- Provide final video preview and download/export options

### 5.2 ByteDance Lip-Sync API (WaveSpeed Gateway)

**Endpoint:** `POST https://api.wavespeed.ai/api/v3/bytedance/lipsync/audio-to-video`

**Request body:**
```json
{
  "model": "bytedance/lipsync/audio-to-video",
  "input": {
    "video_url": "file:///Users/kimberlysmith/.../beat_001_kling_option1.mp4",
    "audio_url": "file:///Users/kimberlysmith/.../beat_001_tts_audio.mp3"
  }
}
```

**Polling:** Same as Phase 1 (GET `/api/v3/predictions/{task_id}/result`)

**Response (complete):**
```json
{
  "code": 200,
  "data": {
    "id": "task_xyz789",
    "status": "completed",
    "outputs": ["https://storage.wavespeed.ai/...final.mp4"]
  }
}
```

### 5.3 Lip-Sync Review Gate (CLAUDE.md Rule 8 MANDATORY)

**Phase 3 MUST include mouth movement detection:**

1. **Download the final lipsync clip** from WaveSpeed
2. **Scan for mouth/beak movement** using one of these heuristics:
   - Optical flow detection: analyze frame-to-frame pixel changes around mouth region (approximate implementation)
   - Frame diff histogram: compare mouth region across first, middle, last frames
   - Manual: Kim watches 3s clip and confirms "No mouth movement detected" or "Reject & retry with different prompt"
3. **If mouth movement detected:** 
   - Alert Kim: ⚠️ "Mouth movement detected in beat 001. This violates the 'closed mouth' constraint. Retry with adjusted prompt?"
   - Option 1: [Retry Phase 3] — re-run ByteDance lip-sync (sometimes helps with different frame timing)
   - Option 2: [Retry Phase 1] — go back to Kling with stronger anti-lip-sync prompt (e.g., add "absolutely motionless mouth" or "frozen beak")
   - Option 3: [Manual Override] — force approval (only if Kim explicitly wants this)

**Why this matters:** Seedance (experimental, ByteDance backup) has a talking-head bias in its model weights that can generate Chinese-phoneme lip-sync even with explicit anti-lip-sync prompts. Kling v3 does not have this bias. The lip-sync review gate catches Seedance failures and recovers by switching to Kling or letting Kim override.

### 5.4 Alternative Model: fal.ai Fallback (Cost Guard)

**If WaveSpeed fails 3 times on a beat, offer fallback option:**
- "WaveSpeed is having issues. Try with fal.ai instead?" + [Switch to fal.ai] button
- fal.ai endpoint: `https://api.fal.ai/v1/image-to-video` (different API, same result quality)
- Costs slightly more (~$0.35/clip vs. $0.26 WaveSpeed) but higher availability

### 5.5 Phase 3 UI & Workflow

**"Send for Lip Sync" button:**
- Location: Phase summary bar, appears only when all Phase 1 + Phase 2 are approved
- State: `disabled` (approvals incomplete), `enabled` (ready), `generating...` (in progress)
- Click: Submits all approved beats to ByteDance lip-sync

**Lip sync progress:**
```
Phase 3 Lip Sync: 15/20 processing  [Retry Failed] [Done]
Beat 001: ✅ Ready (mouth check: clean)
Beat 002: 🔄 Processing...
Beat 003: ✅ Ready (mouth check: clean)
...
```

**Final deliverable:**
- Once all 20 clips are ready: "🎉 All 20 clips complete. Ready for app."
- Options:
  - `[Export JSON]` — metadata for each beat (animation option chosen, TTS voice, lip-sync final clip URL) for app integration
  - `[Download ZIP]` — all MP4 files in one archive (for upload to app production pipeline)
  - `[View in App]` — preview clips in the storyboard context
  - `[Delete _prod.html & cleanup]` — remove the overlay file, keep storyboard + clips

---

## 6. Injection Script Specification

### 6.1 Tool: `inject_production_overlay.py` (Run by Claude, NOT Kim)

**Location:** `Production/tools/inject_production_overlay.py`

**Important:** This script is run BY CLAUDE, not by Kim. Kim just opens the resulting HTML file in Safari/Chrome on her Mac. Claude handles all the injection logic.

**CLI usage (Claude executes this):**
```bash
python3 Production/tools/inject_production_overlay.py \
  --input Production/Event_1/storyboard_v14.html \
  --output Production/Event_1/storyboard_v14_prod.html \
  --event-id "Event_1" \
  --session-context '{"childName": "Sophia", "therapistName": "Dr. Reed", ...}' \
  --api-keys-file Production/API_KEYS_MASTER.md \
  --directus-token "your_token_here" \
  --validate-images
```

**Flag explanations:**
- `--input`: Path to Kim's existing storyboard HTML (from build_storyboard.py output)
- `--output`: Path to write the new `_prod.html` file (never overwrites input)
- `--event-id`: Event identifier (e.g., "Event_1") for localStorage keys
- `--session-context`: JSON with personalization variables (from Directus session context)
- `--api-keys-file`: Path to `API_KEYS_MASTER.md` (tool extracts API keys from this file)
- `--directus-token`: Directus auth token (for fetching motion prompts, voice profiles)
- `--validate-images`: Enable MD5 image validation (RECOMMENDED, CLAUDE.md Rule 7 & 9)

**Responsibilities:**
1. Parse input HTML: Extract storyboard beat array from inline JavaScript (regex or HTML parser)
2. Validate beat structure: Confirm all beats have required fields (speaker, text, image, audio_key)
3. **MD5 hash all embedded images:** Compute MD5 for every image in input HTML
4. Inject production overlay script: Add large `<script>` block with all Phase 1, 2, 3 logic
5. Inject production styles: Add `<style>` block for overlay UI (buttons, progress, panels)
6. Inject initialization code: Set up API keys, session context, localStorage, event listeners
7. **Verify MD5 hashes match output:** Recompute MD5 for every image in output HTML, compare against input
8. Abort if ANY image differs (alert Claude: "Image validation failed on beat 001 — injection aborted")
9. Write output HTML: New file with injected code (do NOT modify input)
10. Generate manifest: Output `production_overlay_manifest.json` with feature audit

### 6.2 Injection Validation & Manifest

**Validation checks (BLOCKING — must pass before proceeding):**
1. ✓ Beat count matches input HTML
2. ✓ All beats have speaker + text + image
3. ✓ API keys present and non-empty
4. ✓ Session context populated (childName, therapistName, etc.)
5. ✓ localStorage persistence code present in injected JavaScript
6. ✓ All MD5 image hashes match between input and output (CLAUDE.md Rule 7 & 9)
7. ⚠️ Mouth movement detection heuristic implemented (Phase 3 critical feature)

**File:** `Production/.auto-memory/production_overlay_manifest.json`

```json
{
  "timestamp": "2026-04-15T14:32:00Z",
  "input_file": "Production/Event_1/storyboard_v14.html",
  "output_file": "Production/Event_1/storyboard_v14_prod.html",
  "beat_count": 20,
  "injected_features": {
    "phase_1_animation": {
      "status": "active",
      "lines_injected": 450,
      "dependencies": ["WaveSpeed API", "file:// URL access"]
    },
    "phase_2_tts": {
      "status": "active",
      "lines_injected": 380,
      "dependencies": ["ElevenLabs API", "Web Audio API"]
    },
    "phase_3_lipsync": {
      "status": "active",
      "lines_injected": 300,
      "dependencies": ["WaveSpeed API", "mouth movement detection"]
    }
  },
  "api_keys_configured": {
    "wavespeed": "***hidden***",
    "elevenlabs": "***hidden***",
    "directus": "***hidden***"
  },
  "session_context": {
    "childName": "Sophia",
    "therapistName": "Dr. Reed",
    "parentName": "Dr. Smith",
    "parentTitle": "Dr.",
    "chosenGuideName": "Feathers"
  },
  "image_validation": {
    "total_images": 20,
    "md5_hashes_match": true,
    "images_checked": ["beat_001_image_md5: a1b2c3d4e5f6...", "beat_002_image_md5: ..."],
    "validation_status": "✓ PASSED"
  },
  "validation_checks": [
    "✓ Beat count matches input",
    "✓ All beats have speaker + text + image",
    "✓ API keys present and non-empty",
    "✓ Session context populated",
    "✓ localStorage persistence code present",
    "✓ All MD5 image hashes match (20/20)",
    "⚠️ Mouth movement detection implemented but not yet tested in production"
  ],
  "notes": "Ready for use. Open storyboard_v14_prod.html in Chrome/Safari on Mac. Click 'Fire Away' to start Phase 1."
}
```

### 6.3 Implementation Pattern (Pseudo-Code)

```python
import hashlib
import json
import re
from pathlib import Path

def inject_production_overlay(input_html_path, output_html_path, event_id, session_context, api_keys, validate_images=True):
    """
    Read input HTML, extract beat array, inject production overlay with image validation.
    """
    # 1. Parse HTML
    with open(input_html_path, 'r') as f:
        input_html = f.read()
    
    beat_array_js = extract_beat_array(input_html)
    beat_count = len(beat_array_js)
    
    # 2. Extract and hash all images from input (CLAUDE.md Rule 7 & 9)
    input_image_hashes = {}
    for beat_index, beat in enumerate(beat_array_js):
        if 'image' in beat and beat['image'].startswith('data:image'):
            # Extract base64 and compute MD5
            b64_data = beat['image'].split(',')[1]
            md5 = hashlib.md5(b64_data.encode()).hexdigest()
            input_image_hashes[f"beat_{beat_index:03d}"] = md5
    
    # 3. Validate
    validate_beats(beat_array_js)
    validate_api_keys(api_keys)
    validate_session_context(session_context)
    
    # 4. Prepare injection payload
    production_script = generate_production_script(
        event_id=event_id,
        beat_count=beat_count,
        session_context=session_context,
        api_keys=api_keys,
        motion_prompts=fetch_motion_prompts_from_directus(event_id)
    )
    
    production_styles = generate_production_styles()
    
    # 5. Inject into original HTML
    output_html = inject_into_html(
        original_html=input_html,
        script_payload=production_script,
        style_payload=production_styles
    )
    
    # 6. Validate images (CLAUDE.md Rule 7 & 9 — BLOCKING)
    if validate_images:
        output_image_hashes = {}
        output_beat_array = extract_beat_array(output_html)
        for beat_index, beat in enumerate(output_beat_array):
            if 'image' in beat and beat['image'].startswith('data:image'):
                b64_data = beat['image'].split(',')[1]
                md5 = hashlib.md5(b64_data.encode()).hexdigest()
                output_image_hashes[f"beat_{beat_index:03d}"] = md5
        
        # Compare hashes
        for beat_key in input_image_hashes:
            if input_image_hashes[beat_key] != output_image_hashes.get(beat_key):
                raise ValueError(f"Image validation FAILED for {beat_key} — injection aborted. MD5 mismatch.")
    
    # 7. Write output
    with open(output_html_path, 'w') as f:
        f.write(output_html)
    
    # 8. Generate manifest
    manifest = build_manifest(
        input_file=str(input_html_path),
        output_file=str(output_html_path),
        beat_count=beat_count,
        features=["phase_1_animation", "phase_2_tts", "phase_3_lipsync"],
        image_hashes=input_image_hashes,
        image_validation_passed=(validate_images and len(input_image_hashes) == len(output_image_hashes)),
        validation_checks=[...]
    )
    manifest_path = Path(".auto-memory/production_overlay_manifest.json")
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)
    
    print(f"✓ Overlay injected into {output_html_path}")
    print(f"✓ Image validation: {len(input_image_hashes)}/{len(input_image_hashes)} hashes matched")
    print(f"✓ Manifest written to {manifest_path}")
    
    return manifest
```

---

## 7. File Opening & Handoff to Kim

**Claude's final step (after injection completes):**

1. **Verify the output file exists:** `ls -lh Production/Event_1/storyboard_v14_prod.html`
2. **Open the file for Kim via Finder** (not via browser link):
   - Use `open file:///Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude\ Mindfulnest\ Project\ Files/Production/Event_1/storyboard_v14_prod.html` command
   - Or use macOS Finder via computer-use tool to navigate and open
   - Kim's browser will load the local HTML file from disk
3. **Confirm file content:**
   - Screenshot the storyboard in browser
   - Verify: "Fire Away" button visible, beat layout intact, all images loaded
4. **Hand off to Kim** with message:
   - "✅ Production overlay injected into `storyboard_v14_prod.html`. Open the file, click 'Fire Away' to start Phase 1 animation generation."
   - "Session budget: $25. Estimated cost for 20 beats: $5.20"
   - "Link: Production/Event_1/storyboard_v14_prod.html"

---

## 8. API Credentials (For Implementing Thread)

**All credentials from `Production/API_KEYS_MASTER.md`:**

| Service | Endpoint | Key |
|---------|----------|-----|
| WaveSpeed (Kling + ByteDance) | `https://api.wavespeed.ai/` | `<REDACTED_PER_LD208_USE_DOPPLER>` |
| ElevenLabs (TTS) | `https://api.elevenlabs.io/v1/` | `<REDACTED_PER_LD208_USE_DOPPLER>` |
| Directus (session context + motion prompts) | `https://directus.mindfulnest.app/` | [from API_KEYS_MASTER.md] |

**Key endpoints (all CORRECTED per v1 mistakes):**
- **Kling request:** `POST https://api.wavespeed.ai/api/v3/kwaivgi/kling-v3.0-pro/image-to-video`
- **Kling polling:** `GET https://api.wavespeed.ai/api/v3/predictions/{task_id}/result` (NOT `/api/v3/task/...`)
- **ByteDance lip-sync:** `POST https://api.wavespeed.ai/api/v3/bytedance/lipsync/audio-to-video`
- **ElevenLabs TTS:** `POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=mp3_128`

---

## 9. Governance & Compliance

### 9.1 CLAUDE.md Rules Compliance

This overlay implementation must comply with:

- **Rule 7 (Two-Path Protocol):** This overlay IS Path B (JS injection). No builder rebuild. Base64 images unchanged.
- **Rule 8 (Anti-Lip-Sync Safeguards):** All Kling/ByteDance prompts include banned-words filter and negative_prompt parameter.
- **Rule 9 (MD5 Image Validation):** Overlay injection validates image byte-identity before/after.
- **Rule 12 (Myrrhin Voice Lock):** Phase 2 hardcodes Myrrhin stability=0.70, speed=0.50 regardless of Directus values.

### 9.2 Pre-Injection Gates (Blocking)

Claude MUST ask Kim these questions BEFORE injection:

1. "Have you made edits in the browser (dialogue, drag-drop, image assignments) that haven't been exported?" → If yes, ask her to export first.
2. "Please confirm you've exported your storyboard selections to `{filename}.json`." → Verify export file exists.
3. "I'm about to inject the production overlay into `{filename}.html`. This creates a new `{filename}_prod.html`. Is this OK?" → Get explicit approval.

All three gates are BLOCKING — do not proceed without Kim's confirmation.

### 9.3 Session Spend Tracking

- Default budget: $25/event
- Track in localStorage + activity log
- Warn at 80%, block at 100% with override option
- Log each spend to Directus `prod_activity_log`

---

## 10. Implementation Checklist for New Claude Thread

**Pre-implementation:**
- [ ] Read this entire document (STORYBOARD_PRODUCTION_OVERLAY_PLAN_v2.md)
- [ ] Read CLAUDE.md Rules 7, 8, 9, 12
- [ ] Read `Production/PIPELINE_BRAIN_v1.md` (context on storyboard builder, Directus APIs)
- [ ] Verify API credentials in `Production/API_KEYS_MASTER.md` are valid
- [ ] Check Directus schema: `prod_voice_profiles`, `prod_session_decisions`, `prod_activity_log`

**Phase 1 (Animation):**
- [ ] Implement `inject_production_overlay.py` scaffold
- [ ] Parse beat array from storyboard HTML
- [ ] Validate beat structure and API keys
- [ ] Generate Kling request with corrected WaveSpeed endpoint + image data URI format
- [ ] Implement multi-layer retry logic (3 silent retries + exponential backoff)
- [ ] Implement localStorage persistence for task IDs
- [ ] Implement resume from partial completion
- [ ] Build Phase 1 UI (Fire Away button, per-beat options, progress bar)
- [ ] Implement cost tracking ($0.26/beat, $25 budget)
- [ ] Test with 3-beat sample storyboard
- [ ] MD5 image validation (hash all images before/after injection)

**Phase 2 (TTS):**
- [ ] Implement ElevenLabs API call with correct binary response handling (arrayBuffer)
- [ ] Implement Myrrhin voice lock (stability 0.70, speed 0.50)
- [ ] Parse beat text and substitute personalization variables
- [ ] Store MP3 clips to `animation_clips/`
- [ ] Build Phase 2 UI (TTS buttons, audio preview, waveform)
- [ ] Auto-recalculate animation duration from TTS length

**Phase 3 (Lip-Sync):**
- [ ] Implement ByteDance lip-sync API call
- [ ] Implement mouth movement detection heuristic
- [ ] Implement lip-sync review gate (MANDATORY per CLAUDE.md Rule 8)
- [ ] Implement fal.ai fallback (if WaveSpeed fails 3x)
- [ ] Build Phase 3 UI (progress, final video preview, export options)

**Testing & Validation:**
- [ ] Injection: verify output file created, all beats present, images byte-identical
- [ ] Animation: submit 3 beats, verify WaveSpeed responses, verify polling works
- [ ] Resume: reload HTML mid-generation, verify task IDs restored and polling resumes
- [ ] TTS: verify ElevenLabs binary response handling, MP3 files saved
- [ ] Lip-sync: verify final clips generated, mouth detection heuristic works (or manual gate)
- [ ] Cost tracking: verify spending tracked and budget enforced
- [ ] Error messages: verify all error messages are user-friendly (no JSON, no task IDs)

**Handoff to Kim:**
- [ ] Run md5 validation (CLAUDE.md Rule 7 & 9)
- [ ] Generate manifest with all checks passing
- [ ] Open `_prod.html` file for Kim via Finder
- [ ] Confirm "Fire Away" button visible and interactive
- [ ] Hand off with clear instructions

---

## 11. Appendix: Key Differences from v1

| Item | v1 | v2 (Corrected) |
|------|-----|-----------------|
| WaveSpeed polling endpoint | `/api/v3/task/{task_id}` | `/api/v3/predictions/{task_id}/result` |
| WaveSpeed image format | `file:///Users/...` | `data:image/png;base64,...` |
| Response parsing | `data.output.video_url` | `data.data.outputs[0]` |
| ElevenLabs response | JSON | Binary MP3 (arrayBuffer) |
| localStorage availability | Unclear | Confirmed (file:// local execution) |
| Image validation | Not present | MD5 hashing before/after (CLAUDE.md Rule 7 & 9) |
| Myrrhin voice lock | Not mentioned | Hardcoded stability=0.70, speed=0.50 (Rule 12) |
| Retry logic | 3 retries mentioned | 3 silent retries + exponential backoff + re-poll cost guard |
| Error messages | Technical | Human-friendly (no JSON, no task IDs) |
| Pre-injection gates | Not mentioned | Browser-edit gate + export-first protocol (Rule 7) |
| Injection execution | Unclear who runs it | Claude runs it (Kim just opens result) |
| Cost tracking | Basic | Detailed with 80/100% thresholds + override |
| Lip-sync review gate | Not present | Mandatory mouth movement detection (Rule 8) |
| fal.ai fallback | Not mentioned | Available if WaveSpeed fails 3x |

---

## 12. Questions for Implementation Thread

**Before starting, verify:**
1. Can localStorage be accessed from file:// URLs opened from Finder on Mac? (Expected: yes, but confirm)
2. Is IndexedDB also available as fallback? (Expected: yes)
3. Can file:// URLs be used for animation preview (video) and TTS preview (audio) in HTML5 elements? (Expected: with limitations, but test)
4. Do we need special CORS headers for WaveSpeed/ElevenLabs API calls from file:// HTML? (Expected: no, server-side API calls via fetch should work)
5. What's the exact format of motion prompts in Directus `prod_session_decisions`? Is it one prompt per beat, or one prompt per creature per section?

**Success criteria:**
- Phase 1: Kim clicks "Fire Away", 3 animation options appear per beat within 5 minutes (with proper retries)
- Phase 2: TTS audio appears per beat, all dialogue personalization variables substituted correctly
- Phase 3: Final lip-sync clips ready, mouth movement detection running (manual gate acceptable for first iteration)
- Resume: Reload HTML mid-generation, task IDs restored, polling resumes without user re-clicking
- Budget: Spend tracked and enforced, warnings at 80/100%

---

**END OF DOCUMENT**

This plan is complete, self-contained, and ready for a new Claude thread to implement all three phases.
