# MindfulNest Production Tools — Quick Reference Guide

## At-a-Glance Comparison

### Tool Overview

| Tool | Purpose | Input | Output | Users | Key Feature |
|------|---------|-------|--------|-------|-------------|
| **build_storyboard.py** | Edit dialogue, assign images, lock sequence | Lines JSON | Locked sequence JSON | Kim | Drag-drop image assignment, audio playback, export |
| **build_cropper.py** | Crop master image into close-ups | Single image file | PNG crops | Kim | Canvas crop tool, 600px minimum validation |
| **build_tts_review.py** | Review TTS audio, regenerate, approve | Config JSON (lines + audio paths + ElevenLabs key) | Verdicts text + MP3 files | Kim | In-browser TTS regeneration (API key embedded in HTML!) |
| **build_animation_review.py** | Select best animation clip from 3 options per beat | Beats manifest JSON (3 clips + audio per beat) | Picks JSON (beat → clip #) | Kim | Multi-option video comparison, localStorage picks |

---

## Data Model Reference

### Storyboard Line Object
```json
{
  "speaker": "Guide Bird",
  "text": "Are you OK?",
  "image": "master",          // Key into image registry
  "audio_key": "line_02",     // Key into embedded audio (or null)
  "pause": 0.5,               // Seconds
  "section": "Setup"          // Logical grouping
}
```

### TTS Config Lines
```json
{
  "id": "line_02",
  "speaker": "Guide Bird",
  "voice_id": "7o9pyvsN0ob5GO6LBQp6",  // ElevenLabs voice ID
  "text": "[sympathetic] Hello.... Are you OK...?",
  "audio_path": "/path/to/line_02_guide_bird.mp3",
  "filename": "line_02_guide_bird.mp3",  // For download
  "personalized": false
}
```

### Animation Beat Object
```json
{
  "num": 1,
  "speaker": "Tessa",
  "text": "I fell...",
  "section": "Scene",
  "image_key": "master",
  "audio_file": "/path/to/audio_1.mp3",
  "audio_duration": 2.5,
  "pause": 0.3,
  "clips": {
    "option_A": "/path/to/clip_A.mp4",
    "option_A_duration": 2.8,
    "option_B": "/path/to/clip_B.mp4",
    "option_B_duration": 2.5,
    "option_C": "/path/to/clip_C.mp4",
    "option_C_duration": 3.0
  }
}
```

---

## CLI Commands (Typical Usage)

### Storyboard

```bash
# Build from registry (PREFERRED)
python3 build_storyboard.py --registry --module M1 --event 1 \
  --lines lines.json --output storyboard.html \
  --title "Event 1: Tessa's Fall" --subtitle "Arc 1 Storyboard"

# Build from config (fallback)
python3 build_storyboard.py --config config.json --output storyboard.html

# Validate Directus connectivity
python3 build_storyboard.py --smoke-test

# Audit existing HTML (extract features)
python3 build_storyboard.py --audit storyboard_v13.html

# Compare for regressions before replacing old version
python3 build_storyboard.py --registry --module M1 --event 1 \
  --lines lines.json --output storyboard_v14.html \
  --audit-previous storyboard_v13.html
```

### Cropper

```bash
# Build
python3 build_cropper.py \
  --image master_image.png \
  --output cropper.html \
  --title "Master Shot — Wide" \
  --min-dimension 600 \
  --module-id 1 --event-number 1
```

### TTS Review

```bash
# Build (includes auto-registration if module-id provided)
python3 build_tts_review.py \
  --config tts_config.json \
  --output audition_player.html \
  --module-id 1 --event-number 1 --build-mode config
```

### Animation Review

```bash
# Validate manifest before building
python3 build_animation_review.py --manifest beats.json --smoke-test

# Build
python3 build_animation_review.py \
  --manifest beats.json \
  --output review.html \
  --title "M1E1 Animation Review" \
  --subtitle "Arc 1, Module 1"

# Optionally register after build
python3 build_animation_review.py \
  --manifest beats.json \
  --output review.html \
  --register --module-id m1e1 --event-number 1

# Audit for regressions
python3 build_animation_review.py \
  --audit-previous current.html previous.html
```

---

## JavaScript State & Export Patterns

### Storyboard localStorage
```javascript
// Key: storyboard_edits_{title_slug}
// Value: JSON stringified L[] (lines array)
// Saved on every edit, loaded on page load
localStorage.setItem('storyboard_edits_event_1_tessa_fall', JSON.stringify(L));

// Export format (user clicks "Export Locked Sequence")
{
  "lines": [
    { "speaker": "Guide Bird", "text": "...", "image": "...", ... }
  ],
  "exported_at": "2026-04-14T10:30:00Z"
}
```

### TTS Review localStorage
```javascript
// Key: matches event_id from config
// Value: {line_id: "approved"|"redo"|"pending"}
// Saved on verdict button click
localStorage.setItem('tts_audition_m1_event_1', JSON.stringify(verdicts));

// Export format (user clicks "Export Verdicts")
line_02: APPROVED | regens:0 | original | [sympathetic] Hello....
line_03: REDO | regens:2 | saved | [hopeful] I'm okay...
```

### Animation Review localStorage
```javascript
// Key: mindfulnest_animation_review_{title_slug}
// Value: {beat_num: 1|2|3|null}  (selected clip per beat)
// Saved on clip selection
localStorage.setItem('mindfulnest_animation_review_m1e1', JSON.stringify(picks));

// Export format (user clicks "Export Picks")
{
  "picks": {
    "1": 2,      // Beat 1: selected option 2 (option_B)
    "2": 1,      // Beat 2: selected option 1 (option_A)
    "3": null    // Beat 3: no selection
  },
  "exported_at": "2026-04-14T10:30:00Z"
}
```

---

## Directus Registration (Auto-Triggered)

All 4 tools perform post-build registration if module_id/event_number provided:

### Step 1: Authenticate
```python
token, base_url = _directus_auth()
# Reads email/password from API_KEYS_MASTER.md
# POST {base_url}/auth/login
```

### Step 2: Register Visual Asset
```
POST {base_url}/items/prod_visual_assets
{
  "filename": "storyboard.html",
  "filepath": "/path/to/storyboard.html",
  "asset_type": "storyboard_html",       // Tool-specific
  "module_id": 1,                         // INTEGER, not string
  "event_number": 1,
  "status": "built",
  "build_mode": "registry|config|manual",
  "feature_summary": { ... }              // JSON dict of features
}
```

### Step 3: Update Module Tracking
```
PATCH {base_url}/items/prod_modules/{module_id}
{
  "storyboard_status": "built",           // Tool-specific field
  "storyboard_built_at": "2026-04-14T...",
  "storyboard_build_mode": "registry"
}
```

### Step 4: Log Activity
```
POST {base_url}/items/prod_activity_log
{
  "action": "storyboard_build",
  "details": {
    "output_path": "...",
    "module_id": 1,
    "event_number": 1,
    "build_mode": "registry",
    "asset_id": "...",
    "filename": "...",
    "timestamp": "2026-04-14T..."
  }
}
```

---

## Feature Extraction Pattern (Storyboard & Animation Review)

### Pre-Build Audit (Extract Features from Previous Version)
```python
before_features = extract_features("storyboard_v13.html")
# Returns: {
#   "image_count": 8,
#   "line_count": 42,
#   "audio_count": 15,
#   "has_drag_drop": true,
#   "has_play_all": true,
#   "has_export": true,
#   "image_keys": ["master", "tessa_closeup", ...],
#   "per_line_images": [
#     {"speaker": "Guide Bird", "text": "Are you OK?", "image": "master"},
#     ...
#   ]
# }
```

### Post-Build Comparison (Detect Regressions)
```python
compare_features(before_features, "storyboard_v14.html")
# Checks:
# - Drag-drop present before, missing after? ❌ REGRESSION
# - Image count dropped? ❌ REGRESSION
# - Per-line image assignments changed? ❌ IMAGE SCRAMBLING
# - Line count dropped > 20%? ❌ REGRESSION
# Output: Prints warnings, returns True/False (pass/fail)
```

---

## Common Gotchas

### Storyboard
- **Image scrambling:** If you edit images in browser (drag-drop) and don't click "Export Locked Sequence" before rebuild, edits are lost. Always export first.
- **Registry requires module_id + event_number:** Can't build in registry mode without both; falls back to manual config mode.
- **Smoke-test only checks connectivity:** Doesn't validate that all images in the registry actually exist on disk.

### Cropper
- **No metadata export:** Crop boxes are stored in localStorage only. Close tab = lose crops. Must click "Save as PNG" for each crop to persist.
- **Canvas rendering platform-dependent:** Crop coordinates may differ slightly between Chrome/Safari/Firefox.
- **Min dimension is hard gate:** If crop < 600px shortest side, save button disabled. Can override `--min-dimension` but not recommended.

### TTS Review
- **⚠️ SECURITY: ElevenLabs API key embedded in HTML.** Anyone with the HTML can regenerate audio and burn credits. Only share with trusted reviewers; key is ephemeral, should be rotated/revoked after use.
- **No regen counter in export:** Export verdicts don't include how many times each line was regenerated. Can check status dots in browser but not in final export.
- **Unsaved audio lost on tab close:** If you regenerate a line but don't click "Save to Disk" before closing the tab, the blob is lost. "Save to Disk" is explicit, not auto-save.

### Animation Review
- **Video file size explosion:** 3 clips × 10 beats × 2.5MB per clip = 75MB of base64 in HTML. Browsers may choke. Consider splitting large events into multiple HTMLs.
- **No audio/video sync validation:** If audio duration (2.5s) doesn't match video clip duration (3.0s), no warning. Kim must manually check.
- **Incomplete beats allowed in export:** If a beat has only 1/3 clip options, pick is null, but export still succeeds. No validation that all beats are complete.

---

## File Locations & API Credentials

### Credentials Source (All Tools)
```
/Sessions/admiring-quirky-noether/mnt/Claude Mindfulnest Project Files/Production/API_KEYS_MASTER.md
```
Markdown table with:
- Directus Admin Email
- Directus Admin Password
- Directus URL: https://directus-production-3460.up.railway.app
- ElevenLabs API Key
- WaveSpeed API Key
- Other API keys

### Fallback
If API_KEYS_MASTER.md is missing, tools check environment variables:
- `DIRECTUS_EMAIL`
- `DIRECTUS_PASSWORD`
- `ELEVENLABS_API_KEY`

---

## Shared Utilities (To Be Extracted)

These functions/patterns appear in multiple tools and should be consolidated:

```python
# Shared credential reading
from api_client import read_credentials
email, password = read_credentials()

# Shared Directus auth
from api_client import directus_auth
token, base_url = directus_auth()

# Shared asset encoding
from assets import encode_image, encode_audio, encode_video
b64_audio = encode_audio("/path/to/audio.mp3")

# Shared registration
from api_client import register_visual_asset, update_modules, log_activity
```

Currently each tool implements these independently. Consolidation would reduce duplication by ~300 lines.

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| TTS_Review v4 | Apr 14, 2026 | Added post-build auto-registration (Directus) |
| Storyboard | Apr 13, 2026 | Drag-drop + audio fixed (registry native), audit features added |
| Animation_Review | Apr 12, 2026 | Smoke-test + audit modes added |
| Cropper | Apr 12, 2026 | Initial release |
| TTS_Review v3 | Apr 13, 2026 | Save to Disk + Save All Approved added |

---

## Testing Checklist (Before First Production Use of a New Tool)

- [ ] Run `--smoke-test` to verify Directus connectivity
- [ ] Build with sample data (small JSON, test image, etc.)
- [ ] Verify HTML embeds assets correctly (open in browser, console check for base64)
- [ ] Test play/edit/export functions manually
- [ ] Check localStorage after edits (dev tools → Application → localStorage)
- [ ] Export and inspect output JSON format
- [ ] Verify Directus registration (check prod_visual_assets + prod_modules + prod_activity_log)
- [ ] Test regression detection: build v1 → audit v1 → build v2 → audit-previous (should pass)
- [ ] Test on different browsers (Chrome, Safari, Firefox) if platform-dependent

