# WaveSpeed API Reference v1

**Last updated:** April 11, 2026  
**Status:** Production (used in video-producer Step 5 and Step 6)  
**Cost tracking:** See dashboard-ops for balance monitoring

---

## Overview

WaveSpeed AI (https://api.wavespeed.ai) hosts two critical video production APIs:
1. **Seedance 1.5 Pro** — Image-to-video animation with motion prompts
2. **ByteDance LatentSync** — Lip-sync service for dialogue scenes

Both services run asynchronously via polling. The video-producer skill orchestrates both endpoints.

---

## Authentication

**API Key:** Read from `Production/API_KEYS_MASTER.md` at runtime  
**Current Key:** `<REDACTED_PER_LD208_USE_DOPPLER>`

**Header Format:**
```
Authorization: Bearer {api_key}
Content-Type: application/json
```

---

## Seedance 1.5 Pro — Image-to-Video Animation

### Endpoint
```
POST https://api.wavespeed.ai/api/v3/bytedance/seedance-v1.5-pro/image-to-video
```

### Use Case
Convert a still image + motion prompt into 4-10 second animated video. Outputs standard MP4. Supports video extension (clip chaining) by feeding last frame as input to next generation.

### Request Format

```json
{
  "image_source": {
    "type": "url",
    "url": "https://example.com/image.png"
  },
  "prompt": "Tessa the turtle shell glowing orange, slow gentle movement, head tilting toward the light, Pixar 3D style, cinematic lighting",
  "duration": 5,
  "aspect_ratio": "16:9",
  "seed": [optional integer for reproducibility]
}
```

**Key parameters:**

| Parameter | Type | Required | Notes |
|-----------|------|----------|-------|
| `image_source` | object | YES | URL-based image input. Alternatively `base64_source` for direct encoding. |
| `prompt` | string | YES | 60-100 word motion prompt. Should include: SUBJECT, ACTION, ENVIRONMENT, CAMERA (one movement only), STYLE, CONSTRAINTS. See video-producer SKILL.md for formula. |
| `duration` | integer | NO | Seconds (default 5, range 4-10). Used for cost estimation. |
| `aspect_ratio` | string | NO | Default: `16:9`. Also supports `9:16` (vertical), `1:1` (square). |
| `seed` | integer | NO | For reproducibility across generations. Optional. |

**Example prompt structure:**
```
SUBJECT: Tessa the turtle with weathered orange shell and gentle eyes
ACTION: Slow deliberate movement — shell glowing warm orange, head turning to face the light
ENVIRONMENT: Misty forest clearing, dappled sunlight through leaves, moss-covered ground
CAMERA: Slow pan left, reveal the source of light
STYLE: Pixar 3D, warm lighting, soft materials, cinematic depth of field
CONSTRAINTS: 5 seconds, no dialogue, natural creature movement
```

### Response Format

```json
{
  "id": "task_abc123def456",
  "status": "processing",
  "request": {
    "prompt": "[submitted prompt]",
    "duration": 5
  }
}
```

**Response fields:**

| Field | Type | Notes |
|-------|------|-------|
| `id` | string | Task ID. Use this to poll for results. |
| `status` | string | Initial status: `processing`, `queued`, or `pending`. |
| `request` | object | Echo of submitted parameters for verification. |

### Polling for Completion

**Endpoint:**
```
GET https://api.wavespeed.ai/api/v3/predictions/{task_id}/result
```

**Example:**
```
GET https://api.wavespeed.ai/api/v3/predictions/task_abc123def456/result
Authorization: Bearer {api_key}
```

**Polling response (while processing):**
```json
{
  "id": "task_abc123def456",
  "status": "processing",
  "created_at": "2026-04-11T12:34:56Z"
}
```

**Completed response:**
```json
{
  "id": "task_abc123def456",
  "status": "completed",
  "output": {
    "video_url": "https://cdn.wavespeed.ai/v/task_abc123def456.mp4"
  },
  "created_at": "2026-04-11T12:34:56Z",
  "completed_at": "2026-04-11T12:39:42Z"
}
```

**Polling strategy:**
1. Submit job → receive task_id
2. Poll every 5-10 seconds
3. Status values: `processing`, `completed`, `failed`, `cancelled`
4. On `completed`: extract `output.video_url`
5. On `failed`: check error response for rate limit / credit issues
6. Timeout: ~180 seconds typical for 5-second video

**Timeout handling:**
If a job exceeds 3 minutes without completion:
- Check WaveSpeed account balance (likely insufficient credits)
- Implement exponential backoff: 5s, 10s, 20s, 30s max
- After 10 polling attempts without progress, report to Kim for account review

### Video Extension (Clip Chaining)

To create longer sequences, use the last frame of one clip as the starting image for the next:

1. Generate initial clip → get video_url
2. Extract final frame: `ffmpeg -i clip1.mp4 -vf "select=gte(n\,FRAME_COUNT-1)" -vf scale=1280:720 last_frame.png`
3. Submit new Seedance request with `last_frame.png` as input image + new motion prompt
4. Result: seamless continuation

**Cost:** Each extension counts as a separate request (~$0.06/clip). Video extension is how to build 50+ second sequences from 4-5 second clips.

### Cost

**~$0.06 per 5-second clip** (video-producer Step 5)

Actual cost varies slightly by duration and model. A typical module event (Story Scene + Resolution) with 8-12 clips costs $0.50-0.80 for animation.

---

## ByteDance LatentSync — Lip Sync

### Endpoint
```
POST https://api.wavespeed.ai/api/v3/bytedance/lipsync/audio-to-video
```

### Use Case
Given an animated character video + TTS dialogue audio, generate a new video with the character's lips synchronized to the audio.

### Request Format

```json
{
  "video_source": {
    "type": "url",
    "url": "https://example.com/seedance_output.mp4"
  },
  "audio_source": {
    "type": "url",
    "url": "https://example.com/tessa_dialogue.mp3"
  }
}
```

**Key parameters:**

| Parameter | Type | Required | Notes |
|-----------|------|----------|-------|
| `video_source` | object | YES | URL to Seedance-generated MP4 (or any character animation). |
| `audio_source` | object | YES | URL to ElevenLabs TTS MP3 (mono or stereo, 44.1kHz-48kHz). |
| `frame_rate` | integer | NO | Default: 24fps. Optional — match source video. |

**Input requirements:**
- Video: MP4, 720p-1080p, 5-60 seconds
- Audio: MP3, WAV, or AAC, synced to video duration (audio must not exceed video length)
- Character must be reasonably visible in frame (head + neck at minimum)

### Response Format

```json
{
  "id": "task_lipsync_xyz789",
  "status": "processing"
}
```

### Polling for Completion

**Endpoint:**
```
GET https://api.wavespeed.ai/api/v3/predictions/{task_id}/result
```

**Polling response (while processing):**
```json
{
  "id": "task_lipsync_xyz789",
  "status": "processing"
}
```

**Completed response:**
```json
{
  "id": "task_lipsync_xyz789",
  "status": "completed",
  "output": {
    "video_url": "https://cdn.wavespeed.ai/v/task_lipsync_xyz789.mp4"
  }
}
```

**Polling strategy:** Same as Seedance — poll every 5-10 seconds, timeout ~120 seconds for typical 5-10 second clips.

### Output Quality

ByteDance LatentSync produces natural mouth movement synchronized to dialogue. Tested on painted character videos (e.g., Ember fox test, April 3) — Kim confirmed "perfect" sync.

**Skip lip sync for:**
- Establishing shots (no character on screen)
- Narration / voice-over (character not speaking)
- Ambient/SFX-only segments
- Only use when a character delivers dialogue on-screen

### Cost

**~$0.15 per 5-10 second clip** (video-producer Step 6)

A typical module event with 6-8 dialogue clips costs $1.00-1.20 for lip sync.

---

## Error Handling

### Common Error Responses

**Insufficient credits:**
```json
{
  "error": "Insufficient credits",
  "balance": 0.45,
  "message": "Your account balance is too low to process this request"
}
```

**Action:** Check `Production/API_KEYS_MASTER.md`, contact Kim to top up account via WaveSpeed dashboard. Current balance tracked in dashboard-ops (Directus).

**Rate limit (429):**
```json
{
  "error": "Too many requests",
  "retry_after": 60
}
```

**Action:** Wait `retry_after` seconds, then retry. Implement exponential backoff (5s, 10s, 20s, 30s max).

**Invalid input:**
```json
{
  "error": "Invalid image format or URL unreachable"
}
```

**Action:** Verify image/audio URLs are publicly accessible. Check file format (PNG/JPG for image, MP3/WAV for audio). Re-upload to temporary hosting (uguu.se or similar) if needed.

**Video too long or short:**
```json
{
  "error": "Duration must be between 4 and 10 seconds"
}
```

**Action:** Adjust duration in request. For longer sequences, use video extension (clip chaining).

### Retry Protocol

1. **Transient errors** (rate limit, timeout, processing error): retry after exponential backoff
2. **Persistent errors** (invalid input, bad URL): fix input and resubmit
3. **Credit errors** (insufficient balance): stop, report to Kim, wait for account top-up
4. **Max retries:** 3 attempts per job, then fail and report

---

## Cost Tracking & Balance

**Current balance:** Stored in Directus via dashboard-ops skill. See Session Handoff (April 11) for refill history.

**Cost model:**
- Seedance 1.5 Pro: ~$0.06/5-sec clip
- ByteDance LatentSync: ~$0.15/5-10-sec clip
- **Per-event cost:** Story Scene (8 clips) + Resolution (8 clips) = 16 total = ~$1.92 (Seedance) + ~$2.40 (LipSync) = **~$4.32/event**

**Monthly budget estimate:** 10 events/month × $4.32 = $43.20/month for video production at current pipeline volume.

---

## Implementation Notes for video-producer Skill

### Step 5: Seedance Animation

1. Load API key from `API_KEYS_MASTER.md`
2. For each scene clip:
   - Prepare motion prompt (60-100 words, 6-step formula)
   - Upload image to temporary hosting (if not already hosted)
   - Submit POST request to Seedance endpoint
   - Receive task_id
   - Begin polling
3. On completion, download MP4 from `output.video_url`
4. Extract last frame for next clip (if chaining)

### Step 6: ByteDance Lip Sync

1. Skip if clip has no dialogue
2. Ensure Seedance output MP4 exists
3. Ensure corresponding TTS audio MP3 exists (from Step 3)
4. Submit POST request with both video_url and audio_url
5. Begin polling
6. On completion, download MP4 from `output.video_url`

### Handling Missing Assets

If image upload fails:
- Check URL is publicly accessible
- Try base64 encoding instead: `"image_source": {"type": "base64", "data": "..."}`
- Alternative: encode locally and embed in request

If audio upload fails:
- Verify MP3 is valid (ffprobe or similar)
- Check audio duration matches or is shorter than video
- Re-render TTS if corrupted

---

## References

- **API_KEYS_MASTER.md** — WaveSpeed API key and all other credentials
- **video-producer/SKILL.md** — Full production pipeline using these endpoints
- **SESSION_HANDOFF_April11_2026_Thread3.md** — Infrastructure setup and balance tracking
- **ELEVENLABS_VIDEO_PRODUCTION_HANDOFF_April5_2026.md** — Historical pipeline context and tools comparison

---

**This reference is current as of April 11, 2026. For the latest API changes, check WaveSpeed documentation at https://api.wavespeed.ai/docs or contact support.**
