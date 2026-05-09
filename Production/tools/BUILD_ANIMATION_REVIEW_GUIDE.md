# Animation Review Builder — Complete Guide

## Overview

The `build_animation_review.py` script generates a self-contained HTML animation review tool that allows Kim to:

- **View multiple animation clip options** (A, B, C) for each narrative beat
- **Select the best clip** via click-to-toggle interaction
- **Hear audio sync'd with video** (if available)
- **Compare all 3 clips simultaneously** (side-by-side playback)
- **Auto-save selections** to browser localStorage
- **Export picks as JSON** for downstream integration

The output is a single self-contained HTML file (~1.5MB–2MB with embedded video clips) that works offline.

## Architecture

### Mirrors `build_storyboard.py` Design

The animation review builder follows the same architectural patterns as the existing storyboard builder:

- **Base64 embedding:** Videos and audio are read from disk, base64-encoded, and embedded as data URIs in JavaScript variables (`VID` and `AU`)
- **Single-file output:** No external asset references — all content is embedded
- **Dark theme styling:** Consistent with storyboard builder (#1a1a2e background, #16213e cards, #e94560 accents)
- **Vanilla JavaScript:** No frameworks, no external dependencies; pure DOM manipulation
- **Apple system fonts:** Native look and feel on Mac and cross-platform

### Key Objects

| Object | Purpose | Example |
|--------|---------|---------|
| `VID` | Video clip storage (key → base64 data URI) | `VID["beat_01_1"]`, `VID["beat_01_2"]` |
| `AU` | Audio storage (key → base64 data URI) | `AU["audio_01"]` |
| `BEATS` | Beat metadata array | Array of beat objects with speaker, text, clips, etc. |
| `state` | Selection state (beat_num → clip_num) | `{"beat_01": 1, "beat_03": 2}` |
| `STORAGE_KEY` | localStorage key (title-based slug) | `"mindfulnest_animation_review_m1e1_tessa"` |

## Input Format: Beats Manifest JSON

The builder reads a manifest JSON file describing all beats and their clip options.

### Manifest Schema

```json
{
  "beats": [
    {
      "num": 1,
      "speaker": "Guide Bird",
      "text": "Welcome to the MindfulNest!",
      "image_key": "master_wide_01",
      "audio_key": "line_01",
      "audio_file": "/path/to/line_01.mp3",
      "audio_duration": 3.2,
      "pause": 1.5,
      "section": "Opening",
      "clips": {
        "option_A": "/path/to/beat_01_animated.mp4",
        "option_A_duration": 5.04,
        "option_B": "/path/to/beat_01_alt_B.mp4",
        "option_B_duration": 4.92,
        "option_C": "/path/to/beat_01_alt_C.mp4",
        "option_C_duration": 5.10
      }
    }
  ]
}
```

### Field Descriptions

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `num` | int | Yes | Beat number (1–N) — used as ID |
| `speaker` | str | Yes | Character name (e.g., "Guide Bird", "Tessa", "[Stage Direction]") |
| `text` | str | Yes | Dialogue or direction text |
| `image_key` | str | Yes | Reference to a visual asset (displayed in header) |
| `audio_key` | str | No | Internal key for TTS audio (e.g., "line_01") |
| `audio_file` | str | No | Path to audio MP3 file; if provided, will be embedded |
| `audio_duration` | float | No | Duration in seconds (informational) |
| `pause` | float | No | Pause duration after beat (informational) |
| `section` | str | Yes | Scene/section label (e.g., "Opening", "Climax", "Transition") |
| `clips` | object | Yes | Clip options object |
| `clips.option_A` | str | No | Path to Option A MP4 file (can be null) |
| `clips.option_A_duration` | float | No | Duration of Option A clip |
| `clips.option_B` | str | No | Path to Option B MP4 file (can be null) |
| `clips.option_B_duration` | float | No | Duration of Option B clip |
| `clips.option_C` | str | No | Path to Option C MP4 file (can be null) |
| `clips.option_C_duration` | float | No | Duration of Option C clip |

### Missing Clips Handling

If a beat doesn't have all 3 clips:
- A badge "NEEDS 2 CLIPS" or "NEEDS 3 CLIPS" appears on the beat card
- Placeholder boxes show "Clip not available" for missing options
- Users can still select available clips

## CLI Usage

### Basic Command

```bash
python3 build_animation_review.py \
  --manifest path/to/beats.json \
  --output path/to/output.html \
  --title "M1E1 Tessa Story Scene" \
  --subtitle "Arc 1, Module 1"
```

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--manifest PATH` | Yes | Path to beats manifest JSON file |
| `--output PATH` | Yes | Output HTML file path |
| `--title STR` | No | Page title (default: "Animation Review") |
| `--subtitle STR` | No | Page subtitle (optional) |

### Examples

```bash
# Basic
python3 build_animation_review.py \
  --manifest beats.json \
  --output review.html

# With metadata
python3 build_animation_review.py \
  --manifest beats.json \
  --output /tmp/m1e1_review.html \
  --title "M1E1 Tessa Story Scene" \
  --subtitle "Arc 1 Event 1"

# With absolute paths
python3 build_animation_review.py \
  --manifest /home/kim/project/beats_m1e1.json \
  --output /home/kim/project/review_m1e1.html \
  --title "Tessa Magic Hands Event"
```

## Output: HTML File

### File Size

- **Without video/audio:** ~25KB
- **Typical module (4 beats, 2 video options each, 1 audio per beat):** ~1.5MB–2.5MB
- **Size breakdown:** ~75% video clips, ~15% audio, ~10% HTML/CSS/JS

### Export Format

Users can export selections via the **"↓ Export JSON"** button. The export format is:

```json
{
  "picks": {
    "beat_01": 1,
    "beat_02": 2,
    "beat_03": 1,
    "beat_04": 3
  },
  "timestamp": "2026-04-14T15:30:00.123456",
  "title": "M1E1 Tessa Story Scene"
}
```

The exported file is named `animation_picks_YYYY-MM-DD.json` and is automatically downloaded.

## User Interface

### Header

- **Title:** Large, centered heading with page title
- **Subtitle:** Optional secondary line
- **Progress:** "X / Y clips picked" counter in green

### Controls (Fixed Top)

| Button | Function |
|--------|----------|
| `▶ Play All 3 (simultaneous)` | Reset all clips to t=0, play muted simultaneously |
| `▶ Play Selected + Audio` | Play selected clip (unmuted) + sync'd audio |
| `↓ Export JSON` | Download picks as JSON file |
| `⊗ Clear Selection` | Reset all selections (with confirmation) |

### Beat Cards (Timeline)

Each beat is a card containing:

- **Beat number:** Red circle with white number
- **Speaker & text:** Italicized dialogue (read-only)
- **Section label:** Yellow badge (e.g., "Opening")
- **Needs badge** (if applicable): Red "NEEDS X CLIPS" label
- **3 video cells:** Side-by-side grid, one per option (A, B, C)
  - Click to select (green border + ✓ checkmark)
  - Click again to deselect
  - Native HTML5 video player with controls (play, pause, scrub)
  - Shows clip duration via video player UI
- **Action buttons:**
  - `▶ Play All 3` — play all 3 clips for this beat simultaneously
  - `▶ Play Selected + Audio` (if audio available) — play selected clip + TTS

### Styling

| Element | Color | Purpose |
|---------|-------|---------|
| Background | #1a1a2e | Dark theme |
| Cards | #16213e | Beat containers |
| Beat number | #e94560 | Accent red |
| Selected border | #27ae60 | Success green |
| Section badge | #ffd6a5 | Golden accent |
| Needs badge | #c0392b | Error red |

## Features

### Selection & Persistence

- **Click to select:** Click any video cell to select it (green border appears)
- **Click to deselect:** Click again to deselect
- **Auto-save:** Selections save to browser localStorage automatically
- **Reload persistence:** Closing and re-opening the page restores selections
- **Multiple selections:** Can have different beats with different choices

### Playback

| Feature | Behavior |
|---------|----------|
| **Video controls** | Native HTML5 controls (play, pause, seek, volume) |
| **Play All 3** | Reset all 3 clips to t=0, play simultaneously (muted) |
| **Play Selected + Audio** | Play only selected clip (unmuted) + audio simultaneously |
| **Per-beat playback** | Each beat has its own "Play All 3" button |

### Progress Tracking

- **Header counter:** "0 / 4 clips picked" updates in real-time
- **Play button state:** "Play Selected + Audio" button disables when no clips are picked
- **Visual feedback:** Selected clips show green border + ✓ checkmark

### Export

- **JSON format:** Picks, timestamp, title
- **Auto-named:** `animation_picks_YYYY-MM-DD.json`
- **Always available:** Export works even with partial selections
- **Useful downstream:** Can be imported into production pipeline

## Performance & Technical Notes

### Base64 Encoding

- Videos are read as binary, base64-encoded, and stored in JS variable `VID`
- Audio is read as binary, base64-encoded, and stored in JS variable `AU`
- Base64 bloats file size by ~33% vs. binary, but enables offline use
- Large video files (5–10MB each) can result in 6–30MB HTML files

### Error Handling

- Missing files: Warning printed during build, clip shows placeholder
- Missing manifest: FileNotFoundError with clear message
- Invalid JSON: ValueError with clear message
- Invalid MP4/MP3: Logged as warning, file skipped; doesn't crash

### Storage & Limitations

- **localStorage limit:** ~5–10MB per domain (varies by browser)
  - For large files, export and reload may clear older selections
- **Browser support:** All modern browsers (Chrome, Safari, Firefox, Edge)
- **Mobile:** Works on iOS Safari and Android Chrome; touch-friendly

## Integration with Production Pipeline

### Future: Directus Dashboard Integration

Once implemented, selections can be:

1. **Exported from the review tool** → JSON file
2. **Uploaded to Directus** → `prod_animation_picks` collection
3. **Linked to modules** → `prod_modules.animation_picks_json` field
4. **Passed to video producer** → Selects best clips for final assembly

### Current Workflow

1. Generate manifest JSON from narrative events (manual or via pipeline)
2. Render all clip options (via Runway/Seedance/LatentSync)
3. Run `build_animation_review.py` to create review tool
4. Kim opens HTML in browser, selects best clips
5. Kim exports JSON picks
6. Passes picks to video producer (manual step for now)

## Example: M1E1 Tessa

### Sample Manifest

See `sample_animation_manifest.json` in this directory.

### Generate Review Tool

```bash
python3 build_animation_review.py \
  --manifest sample_animation_manifest.json \
  --output /Users/kimberlysmith/Desktop/m1e1_review.html \
  --title "M1E1 Tessa Story Scene" \
  --subtitle "Arc 1, Event 1 — Magic Hands Spell"
```

### What Kim Sees

1. Header: "M1E1 Tessa Story Scene" + "Arc 1, Event 1 — Magic Hands Spell"
2. Progress: "0 / 4 clips picked"
3. 4 beat cards:
   - Beat 1 (Guide Bird): No clips yet → "NEEDS 3 CLIPS" badge
   - Beat 2 (Tessa): 2 options → select one
   - Beat 3 (Stage Direction): 3 options → select one
   - Beat 4 (Guide Bird): 1 option → select it
4. Click videos to select, watch, compare
5. Click "↓ Export JSON" when done
6. Share JSON with video producer

## Troubleshooting

### Files Not Found

**Error:** "Video file not found"

**Solution:** Check that all file paths in the manifest are absolute and correct. Relative paths are allowed only if they're relative to the manifest file location.

### Large File Size

**Issue:** HTML file is 50MB+ and browser is slow

**Solution:** File size is normal for embedded video. To reduce:
1. Use smaller source video files (~5MB instead of 10MB)
2. Pre-compress video clips to lower bitrate
3. Split into multiple review tools (one per arc event)

### localStorage Clear

**Issue:** Selections were lost after browser update or clearing cache

**Solution:** localStorage is browser-local only. Recommendations:
- Export picks before clearing cache
- Save exported JSON file to disk
- Use dedicated browser profile if storage is critical

### Audio Out of Sync

**Issue:** Audio and video don't play together

**Current limitation:** Browser doesn't guarantee perfectly synchronized playback of separate `<audio>` and `<video>` elements. This is a known limitation of the HTML5 API.

**Workaround:** Use the video player's controls to manually sync (the exported picks JSON captures which clips were selected; actual A/V sync happens during final video assembly).

## Code Structure

### Python Script (~1200 lines)

1. **Imports:** argparse, base64, json, os, re, sys, datetime
2. **Functions:**
   - `read_manifest(path)` → load and validate JSON
   - `encode_video(path)` → read MP4, base64 encode
   - `encode_audio(path)` → read MP3, base64 encode
   - `build_animation_review(manifest, output_path, title, subtitle)` → main builder
   - `main()` → CLI entry point
3. **Output:** ~1500 lines of HTML/CSS/JS embedded in string concatenation

### Generated HTML (~1500 lines)

1. **DOCTYPE + HEAD:** Meta tags, style block
2. **CSS:** Dark theme styling (~400 lines), responsive grid layout
3. **HTML structure:** Header, controls, timeline, timeline items
4. **JS (vanilla):**
   - State management (localStorage sync)
   - Render loop (create beat cards dynamically)
   - Event handlers (click selection, playback)
   - Export function (JSON download)

## Testing

### Quick Test

```bash
# Generate with sample manifest (no actual video files)
python3 build_animation_review.py \
  --manifest sample_animation_manifest.json \
  --output test_review.html \
  --title "Test Review"

# Open in browser
open test_review.html
```

The test tool shows beat structure and placeholder boxes (no actual video playback since the manifest references non-existent files).

## Future Enhancements

- [ ] **Multi-clip export:** Export all 3 clips + metadata (for downstream processing)
- [ ] **Rating system:** Star or comment each clip (5-star rating per option)
- [ ] **Directus upload:** Auto-upload picks to dashboard (requires API integration)
- [ ] **A/V sync calibration:** Offset audio/video timing for perfect sync
- [ ] **Comparison grid:** 2x2 or 3x3 grid view (easier side-by-side comparison)
- [ ] **Batch tool:** Generate multiple review tools in one command (M1E1, M1E2, etc.)

## Support & Questions

For issues or feature requests, contact the production team.

---

**Last updated:** April 14, 2026  
**Builder version:** 1.0  
**Status:** Production-ready
