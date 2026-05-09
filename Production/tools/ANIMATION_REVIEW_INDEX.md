# Animation Review Builder — File Index

## Quick Links

| File | Purpose | Size |
|------|---------|------|
| `build_animation_review.py` | **Main script** — generates review tools | 48KB |
| `README_ANIMATION_REVIEW.md` | **Start here** — quick start guide | 8KB |
| `BUILD_ANIMATION_REVIEW_GUIDE.md` | **Complete reference** — full documentation | 17KB |
| `ANIMATION_REVIEW_FEATURES.md` | **Checklist** — feature verification | 12KB |
| `sample_animation_manifest.json` | Example manifest JSON | 2KB |
| `sample_animation_review.html` | Example output (test file) | 25KB |

## What Is It?

`build_animation_review.py` generates a self-contained HTML tool for reviewing and selecting animation clips for MindfulNest narrative events.

**Use case:** After rendering 3 animation options (A, B, C) for each beat, use this tool to review and pick the best clips for each beat. Kim selects clips in a browser, and the tool exports selections as JSON for the video producer.

## Getting Started (30 seconds)

### 1. Create a Manifest JSON

List your beats and clip paths:

```json
{
  "beats": [
    {
      "num": 1,
      "speaker": "Guide Bird",
      "text": "Welcome to MindfulNest!",
      "image_key": "master_01",
      "section": "Opening",
      "clips": {
        "option_A": "/path/to/beat_01_A.mp4",
        "option_A_duration": 5.04,
        "option_B": "/path/to/beat_01_B.mp4",
        "option_B_duration": 4.92,
        "option_C": null
      }
    }
  ]
}
```

See `BUILD_ANIMATION_REVIEW_GUIDE.md` for full schema.

### 2. Run the Builder

```bash
python3 build_animation_review.py \
  --manifest beats.json \
  --output review.html \
  --title "M1E1 Tessa Scene"
```

### 3. Review in Browser

Open `review.html` in any browser:
- Click videos to select clips
- Click "▶ Play All 3" to compare
- Click "▶ Play Selected + Audio" to hear with TTS
- Click "↓ Export JSON" when done

Selections auto-save to browser storage.

## Files Explained

### Core Script

**`build_animation_review.py`** (952 lines)
- CLI: `python3 build_animation_review.py --manifest JSON --output HTML`
- Reads manifest JSON with beat + clip data
- Encodes videos/audio as base64 data URIs
- Generates single self-contained HTML file
- ~650 lines of generated HTML/CSS/JS per tool

**Features:**
- ✅ 3 video cells per beat (click to select)
- ✅ "Play All 3" (simultaneous comparison)
- ✅ "Play with Audio" (selected clip + TTS)
- ✅ localStorage auto-save
- ✅ Export picks as JSON
- ✅ Dark theme (matching storyboard)
- ✅ Responsive grid layout

### Documentation

**`README_ANIMATION_REVIEW.md`** — Quick start
- 5-minute overview
- CLI usage with examples
- UI features table
- Troubleshooting tips
- Keyboard shortcuts (future)

**`BUILD_ANIMATION_REVIEW_GUIDE.md`** — Complete reference
- Full manifest schema
- Architecture deep-dive
- Feature descriptions
- Integration points
- Performance notes
- Future enhancements

**`ANIMATION_REVIEW_FEATURES.md`** — Feature checklist
- 18 features verified ✅
- Architecture compliance
- Testing procedures
- Known limitations
- Compliance matrix

### Sample Files

**`sample_animation_manifest.json`** — Test manifest
- 4 beats with varying clip options
- Use to test generator without real videos
- Shows required + optional fields

**`sample_animation_review.html`** — Example output
- Generated from sample manifest
- Shows full UI structure
- Placeholders for missing clips
- Test without large video files

## Command Reference

### Basic Syntax

```bash
python3 build_animation_review.py \
  --manifest PATH \
  --output PATH \
  [--title STR] \
  [--subtitle STR]
```

### Required Arguments

| Arg | Description | Example |
|-----|-------------|---------|
| `--manifest` | Path to beats JSON | `beats.json` |
| `--output` | Output HTML path | `review.html` |

### Optional Arguments

| Arg | Description | Default |
|-----|-------------|---------|
| `--title` | Page title | "Animation Review" |
| `--subtitle` | Page subtitle | (empty) |

### Examples

```bash
# Minimal
python3 build_animation_review.py \
  --manifest beats.json \
  --output review.html

# With metadata
python3 build_animation_review.py \
  --manifest beats.json \
  --output m1e1_review.html \
  --title "M1E1 Tessa Story Scene" \
  --subtitle "Arc 1, Event 1"

# Absolute paths
python3 build_animation_review.py \
  --manifest /Users/kim/project/beats.json \
  --output /tmp/review.html \
  --title "Test Review"

# Batch (multiple events)
for event in 1 2 3 4 5 6; do
  python3 build_animation_review.py \
    --manifest beats_m1e${event}.json \
    --output m1e${event}_review.html \
    --title "M1E${event} Animation Review"
done
```

## Input Schema

### Manifest JSON Structure

```json
{
  "beats": [
    {
      "num": 1,
      "speaker": "Guide Bird",
      "text": "Welcome to MindfulNest!",
      "image_key": "master_wide_01",
      "audio_key": "line_01",
      "audio_file": "/path/to/line_01.mp3",
      "audio_duration": 3.2,
      "pause": 1.5,
      "section": "Opening",
      "clips": {
        "option_A": "/path/to/beat_01_A.mp4",
        "option_A_duration": 5.04,
        "option_B": "/path/to/beat_01_B.mp4",
        "option_B_duration": 4.92,
        "option_C": "/path/to/beat_01_C.mp4",
        "option_C_duration": 5.10
      }
    }
  ]
}
```

**Required fields:**
- `num` (int) — beat number
- `speaker` (str) — character/narrator
- `text` (str) — dialogue or stage direction
- `section` (str) — scene label
- `clips` (object) — video options

**Optional fields:**
- `image_key`, `audio_key`, `audio_file`, `audio_duration`, `pause`

## Output Schema

### Exported JSON

Downloaded as: `animation_picks_YYYY-MM-DD.json`

```json
{
  "picks": {
    "beat_01": 1,
    "beat_02": 3,
    "beat_03": 2,
    "beat_04": 1
  },
  "timestamp": "2026-04-14T15:30:00.123456",
  "title": "M1E1 Tessa Story Scene"
}
```

**Interpretation:**
- `1` = Option A selected
- `2` = Option B selected
- `3` = Option C selected
- `null` or missing = not yet picked

## Features Overview

### Selection & Playback

| Feature | How It Works |
|---------|--------------|
| **Click to select** | Click any video → green border + ✓ checkmark |
| **Click to deselect** | Click selected video again → border removed |
| **Play All 3** | All videos reset to t=0, play muted simultaneously |
| **Play with Audio** | Selected video (unmuted) + audio playback synced |
| **Per-beat buttons** | Each beat has its own play buttons |

### State Management

- **Auto-save:** Selections saved to browser localStorage
- **Persist reload:** Closing/reopening page keeps selections
- **Storage key:** `"mindfulnest_animation_review_{title_slug}"`
- **Clear all:** "⊗ Clear Selection" button with confirmation

### User Interface

- **Fixed header:** Title, subtitle, progress "X / Y picked"
- **Scrollable timeline:** Beat cards in scrollable list
- **Section headers:** Separate beats by scene
- **Progress counter:** Live update as selections change
- **Dark theme:** #1a1a2e background, #16213e cards

### Export

- **Button:** "↓ Export JSON" in toolbar
- **Format:** Standard JSON with picks + timestamp + title
- **Filename:** `animation_picks_YYYY-MM-DD.json`
- **Availability:** Always available (even partial selections)

## Manifest Best Practices

### File Paths

```bash
# ✅ Good: Absolute paths
"option_A": "/Users/kim/project/renders/beat_01_A.mp4"

# ✅ Good: Relative to working directory
"option_A": "renders/beat_01_A.mp4"

# ✅ Good: Can be null if not available
"option_C": null

# ❌ Bad: Relative paths without base
"option_A": "../renders/beat_01_A.mp4"  # Only works if running from specific dir
```

### Beat Numbering

- Start at 1 (not 0)
- Sequential but gaps OK (beat 1, 2, 3... or 1, 2, 5)
- Used as primary key in selections

### Sections

- Group related beats together
- Common values: "Opening", "Setup", "Transition", "Climax", "Resolution"
- Automatically adds visual dividers in the tool

## Performance

### Build Time

- **Typical 4-beat scene:** 2–5 seconds
- **Includes:** Base64 encoding of all videos/audio
- **Linear with:** Total file size of source videos

### File Size

- **Base HTML:** 25KB
- **Per 5MB video:** +6.7MB (33% base64 overhead)
- **Example:** 4 beats, 2 videos, 1 audio = 1.5–2.5MB

### Browser Performance

- **Selection:** Instant (localStorage sync)
- **Rendering:** Instant (vanilla JS)
- **Playback:** Native browser codec
- **Memory:** 20+ videos typically fine

## Troubleshooting

### "File not found" Warning

**Cause:** Video/audio path in manifest doesn't exist

**Solution:** Check file paths are absolute and correct

```bash
# Test path exists:
ls -l /path/to/beat_01_A.mp4
```

### "Invalid JSON" Error

**Cause:** Manifest JSON is malformed

**Solution:** Validate JSON syntax

```bash
# Validate JSON:
python3 -m json.tool beats.json
```

### Large File Size

**Issue:** HTML is 50MB+, browser is slow

**Solution:**
1. Compress source video (lower bitrate)
2. Split into multiple review tools (one per 2–3 beats)
3. Use dedicated browser with more memory

### Selections Lost After Reload

**Cause:** Browser cleared localStorage

**Solution:**
- Export picks BEFORE clearing cache
- Use persistent browser (not private/incognito)
- Save exported JSON for backup

## Integration with Production

### Current Workflow

1. Generate 3 animation options per beat (Runway/Seedance)
2. Create manifest JSON listing all clips
3. Run `build_animation_review.py`
4. Kim opens HTML, selects best clips
5. Kim exports JSON picks
6. Video producer reads picks, assembles final video

### Future: Directus Integration

Planned enhancements:
- Auto-upload picks to Directus dashboard
- Link picks to module records
- Auto-populate video producer skill

## Getting Help

### Documentation Files

- **Quick start:** `README_ANIMATION_REVIEW.md`
- **Complete guide:** `BUILD_ANIMATION_REVIEW_GUIDE.md`
- **Features & compliance:** `ANIMATION_REVIEW_FEATURES.md`

### Script Help

```bash
python3 build_animation_review.py --help
```

### Test Run

```bash
python3 build_animation_review.py \
  --manifest sample_animation_manifest.json \
  --output test_review.html \
  --title "Test"

# Open test_review.html in browser
```

## Files Summary

```
Production/tools/
├── build_animation_review.py          [Main script — 952 lines]
├── README_ANIMATION_REVIEW.md         [Quick start guide]
├── BUILD_ANIMATION_REVIEW_GUIDE.md    [Complete reference]
├── ANIMATION_REVIEW_FEATURES.md       [Feature checklist]
├── ANIMATION_REVIEW_INDEX.md          [This file]
├── sample_animation_manifest.json     [Example input]
└── sample_animation_review.html       [Example output]
```

---

**Version:** 1.0  
**Status:** Production-ready  
**Last updated:** April 14, 2026
