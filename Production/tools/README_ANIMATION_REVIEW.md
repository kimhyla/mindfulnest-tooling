# Animation Review Builder — Quick Start

## What Is It?

`build_animation_review.py` is a Python script that generates a self-contained HTML tool for reviewing and selecting animation clips for MindfulNest narrative events.

**Use case:** After you have 3 animation options (A, B, C) rendered for each beat of a scene, use this tool to:
- View all 3 clips for each beat side-by-side
- Select the best one via click
- Hear audio sync'd with video (if available)
- Export selections as JSON for downstream production

## Quick Start

### 1. Prepare Your Manifest JSON

Create a JSON file listing all beats and their clip locations:

```json
{
  "beats": [
    {
      "num": 1,
      "speaker": "Guide Bird",
      "text": "Welcome to MindfulNest!",
      "image_key": "master_01",
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
        "option_C": null
      }
    }
  ]
}
```

See `BUILD_ANIMATION_REVIEW_GUIDE.md` for full schema documentation.

### 2. Run the Builder

```bash
python3 build_animation_review.py \
  --manifest beats.json \
  --output review.html \
  --title "M1E1 Tessa Scene" \
  --subtitle "Arc 1, Event 1"
```

### 3. Review & Select in Browser

1. Open the generated HTML file in your browser
2. Click on any video clip to select it (green border appears)
3. Use "Play All 3" to compare clips
4. Use "Play Selected + Audio" to hear the final audio with your selection
5. Click "Export JSON" when satisfied with choices

### 4. Export Picks

The tool automatically downloads a JSON file with your selections:

```json
{
  "picks": {
    "beat_01": 1,
    "beat_02": 3,
    "beat_03": 2
  },
  "timestamp": "2026-04-14T15:30:00.123456",
  "title": "M1E1 Tessa Scene"
}
```

## Features

| Feature | How to Use |
|---------|-----------|
| **View 3 clips** | Videos displayed side-by-side, one per beat |
| **Select best clip** | Click any video cell (green border + ✓ checkmark) |
| **Play all 3** | Click "▶ Play All 3" button → all reset to t=0, play muted simultaneously |
| **Play with audio** | Click "▶ Play Selected + Audio" → selected clip plays unmuted + TTS audio |
| **Compare within beat** | "Play All 3" on the beat card itself (per-beat button) |
| **Progress tracking** | "X / Y clips picked" counter at top |
| **Auto-save** | Selections persist in browser (localStorage) |
| **Export picks** | "↓ Export JSON" downloads a file with your selections |
| **Clear all** | "⊗ Clear Selection" resets (with confirmation) |
| **Missing clips** | Shows "NEEDS X CLIPS" badge if not all 3 options are available |

## File Details

### Python Script

- **File:** `build_animation_review.py`
- **Lines:** ~950
- **Dependencies:** Python 3.6+ (standard library only — no pip installs needed)
- **Executable:** Yes (chmod +x already set)

### Generated HTML

- **Size:** ~25KB (no video) to ~2MB (with 6 video clips embedded)
- **Format:** Single self-contained file (no external assets)
- **Dependencies:** None (vanilla JS, no frameworks)
- **Browser support:** All modern browsers (Chrome, Safari, Firefox, Edge)

### Sample Files

- **Sample manifest:** `sample_animation_manifest.json` (4 beats, 2–3 clips each)
- **Sample output:** `sample_animation_review.html` (test file, no actual videos)
- **Documentation:** `BUILD_ANIMATION_REVIEW_GUIDE.md` (complete reference)

## CLI Options

```bash
python3 build_animation_review.py --manifest JSON --output HTML [--title STR] [--subtitle STR]
```

| Option | Required | Example |
|--------|----------|---------|
| `--manifest PATH` | Yes | `beats.json` |
| `--output PATH` | Yes | `/tmp/review.html` |
| `--title STR` | No | `"M1E1 Tessa Scene"` |
| `--subtitle STR` | No | `"Arc 1, Event 1"` |

## Error Handling

| Error | Cause | Solution |
|-------|-------|----------|
| "Manifest not found" | File path is wrong | Check file exists and path is absolute |
| "Invalid JSON" | Manifest is malformed | Validate JSON syntax (use jsonlint or Python `json.tool`) |
| "Video file not found" | Clip file path doesn't exist | Check all `option_A/B/C` paths in manifest are correct |
| "Missing 'beats' key" | Manifest structure is wrong | Ensure manifest has `{"beats": [...]}` top-level key |

## Output File Size

For typical M1E1 event (4 beats, 2–3 video options per beat):

```
Manifest JSON:           0.002 MB
HTML structure:          0.040 MB
CSS + JS:               0.150 MB
Video 1 (5s, 30Mbps):   18.75 MB
Video 2 (5s, 30Mbps):   18.75 MB
Video 3 (5s, 30Mbps):   18.75 MB
Audio 1 (3s, 192kbps):   0.072 MB
Audio 2 (3s, 192kbps):   0.072 MB
Audio 3 (3s, 192kbps):   0.072 MB
Audio 4 (3s, 192kbps):   0.072 MB
─────────────────────────────────
TOTAL:                  ~77 MB
```

**Note:** File size is due to embedded base64 video. If too large for your workflow:
1. Compress source video files (use lower bitrate or resolution)
2. Split scenes into separate review tools
3. Consider rendering lower-quality preview clips just for review

## Architecture

The builder follows the same design as `build_storyboard.py`:

1. **Read manifest JSON** → parse beats and clip paths
2. **Encode videos as base64** → store in JS variable `VID`
3. **Encode audio as base64** → store in JS variable `AU`
4. **Generate HTML** → single string concatenation
5. **Embed all assets** → data URIs, no external files
6. **Write HTML file** → complete, offline-ready HTML

## Integration with Production

### Current Use

For now, this tool is a **standalone review and decision tool**:
- Kim generates a review HTML for each scene
- Kim opens in browser, selects best clips
- Kim exports JSON picks
- Picks are manually passed to the video producer skill

### Future: Directus Dashboard

Once implemented:
1. Picks automatically upload to Directus `prod_animation_picks` collection
2. Picks are linked to module records
3. Video producer skill reads picks from Directus
4. Final video assembly uses picked clips automatically

## Keyboard Shortcuts

Currently none (future enhancement). For now:
- Use mouse clicks to select clips
- Use browser search (Cmd/Ctrl+F) to find beat numbers

## Tips & Tricks

### Test Without Video Files

The sample manifest has no actual video paths. You can still:
1. Generate the review tool (it will show placeholders)
2. See the full UI and structure
3. Test selection/export without large files

```bash
python3 build_animation_review.py \
  --manifest sample_animation_manifest.json \
  --output test.html \
  --title "Test"
```

### Export and Re-import

Exported JSON captures which clips were picked. You can:
1. Export picks from the review tool
2. Save the JSON file for reference/approval
3. Later, parse the JSON and pass to video producer

### Batch Builds

To generate review tools for multiple events:

```bash
for event in 1 2 3 4 5 6; do
  python3 build_animation_review.py \
    --manifest beats_m1e${event}.json \
    --output m1e${event}_review.html \
    --title "M1E${event} Animation Review"
done
```

## Troubleshooting

### "Video plays but audio doesn't sync"

**Known limitation:** Browser HTML5 API doesn't guarantee perfect A/V sync when video and audio are separate elements. This is a browser limitation, not a bug.

**Workaround:** Sync happens during final video assembly (video producer uses picked clips + audio separately, merges with ffmpeg for perfect sync).

### "File is too large to open in browser"

**Solution:** Modern browsers should handle 2–3MB files fine. If larger:
1. Use a different video codec (H.265 instead of H.264 for better compression)
2. Split into multiple review tools (one per 2–3 beats)
3. Use desktop Safari or Chrome for better memory handling

### "Selections disappeared after closing browser"

**Root cause:** Browser cleared localStorage (privacy mode, cache clear, etc.)

**Solution:** 
- Export picks before closing browser
- Use a persistent browser (not private/incognito mode)
- Share exported JSON files for backup

### "Button is disabled"

Buttons disable automatically in certain states:
- "Play Selected + Audio" button disables if no clips are picked
- Reorder buttons (if implemented) disable at edges

This is intentional. Select a clip to enable playback buttons.

## Contact & Support

For questions, bug reports, or feature requests, contact the MindfulNest production team.

---

**Version:** 1.0  
**Last updated:** April 14, 2026  
**Status:** Production-ready
