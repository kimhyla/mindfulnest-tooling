# Storyboard Builder Tool

Generates interactive HTML storyboards for MindfulNest video production.

## Quick Usage (from Python)

```python
from build_storyboard import build_storyboard

config = {
    "title": "Event 1: Tessa's Fall",
    "subtitle": "MindfulNest Arc 1 / M1 Story Scene",
    "images": {
        "master": "/path/to/Production/Event_1/gemini_stills/shot6_v6_c1_1.png",
        "tessa_closeup": "/path/to/Production/Event_1/gemini_stills/crops/shot6_tessa_closeup.png",
        "guidebird_face": "/path/to/Production/Event_1/gemini_stills/crops/shot6_guidebird_face.png",
        "medium_twoshot": "/path/to/Production/Event_1/gemini_stills/crops/shot6_medium_twoshot.png"
    },
    "image_labels": {
        "master": "Master Wide Shot",
        "tessa_closeup": "Tessa Close-up",
        "guidebird_face": "Guide Bird Face",
        "medium_twoshot": "Medium Two-Shot"
    },
    "audio": {
        "shot6_s1": "/path/to/Production/Event_1/tts_emotional/shot6_s1.mp3",
        "shot6_s2": "/path/to/Production/Event_1/tts_emotional/shot6_s2.mp3"
        # ... add all audio files that exist
    },
    "speakers": ["Guide Bird", "Tessa", "Luna", "[Stage Direction]", "[Narration]"],
    "lines": [
        {"speaker": "Guide Bird", "text": "Are you OK...?", "image": "master", "audio_key": None, "pause": 0.5, "section": "Setup"},
        {"speaker": "Tessa", "text": "I fell...", "image": "tessa_closeup", "audio_key": "shot6_s1", "pause": 0.3, "section": "Resolution"}
    ]
}

build_storyboard(config, "/path/to/output/storyboard.html")
```

## CLI Usage

```bash
python3 build_storyboard.py --config storyboard_config.json --output storyboard.html
```

## What the Output HTML Does

- Dark themed, renders in any browser (Chrome, Safari, Firefox)
- Each line has an editable textarea for dialogue
- Speaker dropdown (change who says what)
- Green play button (circle) for lines with TTS audio — click to hear
- Gray circle for lines without audio yet
- Image assignment dropdown per line
- Thumbnail preview of assigned image
- Pause duration slider (0-3 seconds between lines)
- Reorder arrows (move lines up/down)
- Delete button per line
- Add Line button
- Play All — sequences through all lines that have audio
- Export button — generates a text summary of the locked sequence

## Technical Notes

- Images are resized to 80px thumbnails (inline) and 200px (reference grid) via PIL
- Audio is embedded as base64 data URIs — plays via `new Audio()` in browser
- NO template literals (backticks) in JS — they break when generated from Python
- NO localStorage — not supported in some sandbox environments
- All JS uses pure DOM manipulation and ES5 syntax for maximum compatibility
- Requires PIL/Pillow for image resizing (`pip install Pillow`). Without PIL, full-size images are embedded (larger file but still works).

## File Size Guide

- 4 images + 5 audio clips = ~500-600KB HTML
- Without thumbnail resizing (no PIL) = ~3MB+ HTML
- Keep total under 5MB for browser performance
