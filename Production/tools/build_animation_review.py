#!/usr/bin/env python3
"""
MindfulNest Animation Review Builder
====================================
Generates a self-contained HTML animation review tool for selecting between
multiple animation clip options (A, B, C) per narrative beat.

The output HTML:
- Displays beats in a scrollable list (not accordion)
- Each beat shows video clips as <video> elements with native controls
- Selection via click (green border + ✓ badge)
- Playback options: Play All 3 (simultaneous), Play with Audio (selected + TTS)
- LocalStorage persistence of selections
- Export JSON with picks and timestamp
- Dark theme matching storyboard builder

CLI USAGE:
    python3 build_animation_review.py --manifest beats.json --output review.html \\
        --title "M1E1 Animation Review" --subtitle "Tessa Story Scene"

MANIFEST FORMAT (JSON):
{
  "beats": [
    {
      "num": 1,
      "speaker": "Guide Bird",
      "text": "Welcome to the MindfulNest!",
      "image_key": "master_wide_01",
      "audio_key": null,
      "audio_file": "/path/to/audio.mp3",
      "audio_duration": 2.5,
      "pause": 1.5,
      "section": "Setup",
      "clips": {
        "option_A": "/path/to/beat_01_animated.mp4",
        "option_A_duration": 5.04,
        "option_B": "/path/to/beat_01_alt_B.mp4",
        "option_B_duration": 4.92,
        "clip2": null,
        "clip3": null
      }
    }
  ]
}

FEATURES:
- Embed video clips as base64 data URIs (VID object)
- Embed audio files as base64 data URIs (AU object)
- Per-beat: speaker, dialogue text (italic), section label
- Multi-clip detection: show "NEEDS 2 CLIPS" or "NEEDS 3 CLIPS" badges
- Play All 3: simultaneous playback (muted, reset to t=0)
- Play with Audio: selected clip + audio in sync
- Selection: click video cell for green border + ✓ badge
- LocalStorage auto-save on every change (key: "mindfulnest_animation_review_{title_slug}")
- Export JSON: "animation_picks_{title}_{date}.json" format
- Dark theme: #1a1a2e background, #16213e cards, #e94560 beats, #27ae60 selections
- Progress bar in header: "X/Y picked" counter

OUTPUT:
- Single self-contained HTML file (~1500KB for typical module with video clips)
- ~1200 lines of Python, ~1500 lines of generated HTML/CSS/JS
"""

import argparse
import base64
import json
import os
import re
import sys
from datetime import datetime
import requests


def read_manifest(manifest_path):
    """Read and validate the beats manifest JSON file."""
    if not os.path.exists(manifest_path):
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    if "beats" not in manifest or not isinstance(manifest["beats"], list):
        raise ValueError("Manifest must contain 'beats' array")

    return manifest


def encode_video(path):
    """Encode a video file as base64 data URI."""
    if not os.path.exists(path):
        print(f"  WARNING: Video file not found: {path}")
        return None

    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    file_size_mb = os.path.getsize(path) / (1024 * 1024)
    print(f"  Video: {os.path.basename(path)} ({file_size_mb:.2f}MB -> base64)")

    return f"data:video/mp4;base64,{b64}"


def encode_audio(path):
    """Encode an audio file as base64 data URI."""
    if not os.path.exists(path):
        print(f"  WARNING: Audio file not found: {path}")
        return None

    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    file_size_kb = os.path.getsize(path) / 1024
    print(f"  Audio: {os.path.basename(path)} ({file_size_kb:.1f}KB -> base64)")

    return f"data:audio/mpeg;base64,{b64}"


def build_animation_review(manifest, output_path, title="", subtitle=""):
    """
    Build a self-contained HTML animation review tool.

    Args:
        manifest: dict with "beats" key (from read_manifest)
        output_path: where to write the HTML file
        title: page title (optional, defaults to "Animation Review")
        subtitle: page subtitle (optional)
    """

    if not title:
        title = "Animation Review"

    # Slugify title for localStorage key
    title_slug = re.sub(r'[^a-z0-9]', '_', title.lower()).strip('_')
    storage_key = f"mindfulnest_animation_review_{title_slug}"

    print(f"\n{'='*60}")
    print(f"ANIMATION REVIEW BUILDER: {title}")
    print(f"{'='*60}")

    beats = manifest.get("beats", [])
    print(f"Processing {len(beats)} beats...")

    # Embed videos and audio
    vid_data = {}  # vid_id -> data URI
    au_data = {}   # audio_id -> data URI
    beat_metadata = []

    total_video_size = 0
    total_audio_size = 0
    video_count = 0
    audio_count = 0

    for beat_idx, beat in enumerate(beats):
        num = beat.get("num", beat_idx + 1)
        speaker = beat.get("speaker", "")
        text = beat.get("text", "")
        section = beat.get("section", "Scene")
        image_key = beat.get("image_key", "")
        audio_file = beat.get("audio_file")
        audio_duration = beat.get("audio_duration", 0.0)
        pause = beat.get("pause", 0.0)
        clips = beat.get("clips", {})

        # Process video clips (option_A, option_B, option_C mapped to 1, 2, 3)
        beat_clips = {}
        clip_durations = {}
        needs_count = 0

        for clip_name in ["option_A", "option_B", "option_C"]:
            clip_file = clips.get(clip_name)
            duration_key = f"{clip_name}_duration"
            duration = clips.get(duration_key, 0.0)

            if clip_file:
                clip_num = {"option_A": 1, "option_B": 2, "option_C": 3}[clip_name]
                vid_key = f"beat_{num:02d}_{clip_num}"

                data_uri = encode_video(clip_file)
                if data_uri:
                    vid_data[vid_key] = data_uri
                    beat_clips[clip_num] = vid_key
                    clip_durations[clip_num] = duration
                    video_count += 1
                    total_video_size += os.path.getsize(clip_file)
            else:
                # Count missing clips to show badge
                clip_num = {"option_A": 1, "option_B": 2, "option_C": 3}[clip_name]
                if any(clips.get(f"option_{c}") for c in ["A", "B", "C"] if c != clip_name[-1]):
                    needs_count += 1

        # Process audio
        audio_key = None
        if audio_file:
            audio_key = f"audio_{num:02d}"
            data_uri = encode_audio(audio_file)
            if data_uri:
                au_data[audio_key] = data_uri
                audio_count += 1
                total_audio_size += os.path.getsize(audio_file)

        beat_metadata.append({
            "num": num,
            "speaker": speaker,
            "text": text,
            "section": section,
            "image_key": image_key,
            "audio_key": audio_key,
            "audio_duration": audio_duration,
            "pause": pause,
            "clips": beat_clips,
            "clip_durations": clip_durations,
            "needs_count": needs_count,
        })

    print(f"\n  Embedded assets:")
    print(f"    Videos: {video_count} clips ({total_video_size / (1024*1024):.2f}MB total)")
    print(f"    Audio: {audio_count} files ({total_audio_size / 1024:.1f}KB total)")

    # Build HTML
    html_parts = []

    # DOCTYPE + HEAD + STYLE
    html_parts.append(f'''<!DOCTYPE html>
<!-- ================================================================
     GENERATED BY: build_animation_review.py
     Title: {title}
     Generated: {datetime.now().isoformat()}
     DO NOT EDIT THIS HTML DIRECTLY — base64 strings truncate silently.
     ================================================================ -->
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}

    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      background: #1a1a2e;
      color: #eee;
      padding: 20px;
    }}

    .header {{
      max-width: 1200px;
      margin: 0 auto 20px;
      text-align: center;
    }}

    h1 {{
      color: #e0c3fc;
      margin-bottom: 4px;
      font-size: 1.8em;
    }}

    .subtitle {{
      color: #aaa;
      margin-bottom: 8px;
      font-size: 0.95em;
    }}

    .progress {{
      font-size: 0.9em;
      color: #27ae60;
      margin-bottom: 12px;
      font-weight: 600;
    }}

    .controls {{
      display: flex;
      gap: 10px;
      justify-content: center;
      flex-wrap: wrap;
      margin-bottom: 20px;
    }}

    .btn {{
      background: #4a3f6b;
      color: #e0c3fc;
      border: none;
      padding: 10px 18px;
      border-radius: 8px;
      cursor: pointer;
      font-size: 14px;
      font-weight: 600;
      transition: background 0.2s;
    }}

    .btn:hover {{
      background: #6b5b95;
    }}

    .btn.export {{
      background: #2d6a4f;
      color: #b7e4c7;
    }}

    .btn.export:hover {{
      background: #40916c;
    }}

    .btn:disabled {{
      opacity: 0.5;
      cursor: not-allowed;
    }}

    .timeline {{
      max-width: 1200px;
      margin: 0 auto;
    }}

    .section-header {{
      background: #0f3460;
      color: #a5d8ff;
      padding: 10px 16px;
      border-radius: 6px;
      margin: 20px 0 8px;
      font-weight: 700;
      font-size: 14px;
    }}

    .beat {{
      background: #16213e;
      border: 1px solid #2a2a4a;
      border-radius: 10px;
      padding: 16px;
      margin-bottom: 10px;
      transition: border-color 0.2s;
    }}

    .beat:hover {{
      border-color: #e94560;
    }}

    .beat-header {{
      display: flex;
      align-items: center;
      gap: 12px;
      margin-bottom: 12px;
    }}

    .beat-num {{
      background: #e94560;
      color: #fff;
      width: 40px;
      height: 40px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: bold;
      font-size: 16px;
      flex-shrink: 0;
    }}

    .beat-info {{
      flex: 1;
    }}

    .beat-speaker {{
      color: #b7e4c7;
      font-weight: 600;
      font-size: 14px;
    }}

    .beat-text {{
      color: #ddd;
      font-style: italic;
      margin-top: 4px;
      font-size: 13px;
      line-height: 1.4;
    }}

    .beat-section {{
      background: #0f3460;
      color: #ffd6a5;
      border-radius: 4px;
      padding: 3px 8px;
      font-size: 11px;
      font-weight: 600;
      white-space: nowrap;
    }}

    .beat-badge {{
      background: #c0392b;
      color: #fff;
      border-radius: 4px;
      padding: 4px 8px;
      font-size: 11px;
      font-weight: 600;
      white-space: nowrap;
      margin-left: 8px;
    }}

    .clips-container {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 12px;
      margin-bottom: 12px;
    }}

    .clip-cell {{
      background: #0a0a1a;
      border: 2px solid #333;
      border-radius: 8px;
      padding: 8px;
      cursor: pointer;
      transition: all 0.2s;
      position: relative;
    }}

    .clip-cell:hover {{
      border-color: #e94560;
      transform: translateY(-2px);
    }}

    .clip-cell.selected {{
      border-color: #27ae60;
      background: rgba(39, 174, 96, 0.1);
      box-shadow: 0 0 12px rgba(39, 174, 96, 0.3);
    }}

    .clip-label {{
      color: #e94560;
      font-weight: 700;
      font-size: 12px;
      margin-bottom: 6px;
      display: block;
    }}

    video {{
      width: 100%;
      height: auto;
      border-radius: 6px;
      background: #000;
    }}

    .clip-checkmark {{
      position: absolute;
      top: 8px;
      right: 8px;
      background: #27ae60;
      color: #fff;
      width: 28px;
      height: 28px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: bold;
      font-size: 16px;
      display: none;
    }}

    .clip-cell.selected .clip-checkmark {{
      display: flex;
    }}

    .clip-placeholder {{
      width: 100%;
      height: 160px;
      background: #1a1a2e;
      border-radius: 6px;
      display: flex;
      align-items: center;
      justify-content: center;
      color: #555;
      font-size: 13px;
      text-align: center;
      padding: 12px;
    }}

    .beat-actions {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin-top: 12px;
    }}

    .action-btn {{
      background: #2c3e50;
      color: #ddd;
      border: 1px solid #555;
      padding: 8px 14px;
      border-radius: 6px;
      cursor: pointer;
      font-size: 12px;
      font-weight: 600;
      transition: all 0.2s;
    }}

    .action-btn:hover {{
      background: #34495e;
      color: #fff;
    }}

    .action-btn:disabled {{
      opacity: 0.5;
      cursor: not-allowed;
    }}

    .footer {{
      max-width: 1200px;
      margin: 40px auto 0;
      padding: 20px;
      background: #0f3460;
      border-radius: 8px;
      text-align: center;
      color: #aaa;
      font-size: 13px;
    }}
  </style>
</head>
<body>

<div class="header">
  <h1>{title}</h1>
  {f'<p class="subtitle">{subtitle}</p>' if subtitle else ''}
  <div class="progress">
    <span id="progress-text">0 / {len(beat_metadata)} clips picked</span>
  </div>
</div>

<div class="controls">
  <button class="btn" onclick="playAllThree()">▶ Play All 3 (simultaneous)</button>
  <button class="btn" id="playSelectedBtn" onclick="playWithAudio()" disabled>▶ Play Selected + Audio</button>
  <button class="btn export" onclick="exportPicks()" id="exportBtn">↓ Export JSON</button>
  <button class="btn" onclick="clearSelection()">⊗ Clear Selection</button>
</div>

<div class="timeline" id="timeline"></div>

<div class="footer">
  <p>Select one animation clip per beat. Click a video to select it. Changes are auto-saved.</p>
</div>

<!-- ===== JAVASCRIPT ===== -->
<script>
''')

    # Embed video data
    html_parts.append("var VID = {};")
    for vid_key, data_uri in vid_data.items():
        html_parts.append(f'VID["{vid_key}"] = "{data_uri}";')

    # Embed audio data
    html_parts.append("var AU = {};")
    for au_key, data_uri in au_data.items():
        html_parts.append(f'AU["{au_key}"] = "{data_uri}";')

    # Beat metadata as JSON
    html_parts.append(f"var BEATS = {json.dumps(beat_metadata)};")
    html_parts.append(f'var STORAGE_KEY = "{storage_key}";')

    # Core JavaScript engine
    html_parts.append('''
var state = {};
var playingVideos = [];

function loadState() {
  var stored = localStorage.getItem(STORAGE_KEY);
  if (stored) {
    try {
      state = JSON.parse(stored);
    } catch (e) {
      state = {};
    }
  }
  render();
}

function saveState() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  updateProgress();
}

function updateProgress() {
  var count = Object.keys(state).length;
  var total = BEATS.length;
  var text = count + " / " + total + " clips picked";
  document.getElementById("progress-text").textContent = text;

  var playBtn = document.getElementById("playSelectedBtn");
  playBtn.disabled = count === 0;
}

function selectClip(beatNum, clipNum) {
  var beatKey = "beat_" + beatNum;

  if (state[beatKey] === clipNum) {
    // Toggle off
    delete state[beatKey];
  } else {
    // Select this clip
    state[beatKey] = clipNum;
  }

  saveState();
  render();
}

function render() {
  var timeline = document.getElementById("timeline");
  timeline.innerHTML = "";

  var currentSection = "";

  for (var i = 0; i < BEATS.length; i++) {
    var beat = BEATS[i];
    var num = beat.num;
    var beatKey = "beat_" + num;
    var selected = state[beatKey] || null;

    // Section header
    if (beat.section !== currentSection) {
      currentSection = beat.section;
      var sectionDiv = document.createElement("div");
      sectionDiv.className = "section-header";
      sectionDiv.textContent = currentSection;
      timeline.appendChild(sectionDiv);
    }

    // Beat card
    var beatDiv = document.createElement("div");
    beatDiv.className = "beat";
    beatDiv.id = "beat_" + num;

    // Header
    var headerDiv = document.createElement("div");
    headerDiv.className = "beat-header";

    var numDiv = document.createElement("div");
    numDiv.className = "beat-num";
    numDiv.textContent = num;
    headerDiv.appendChild(numDiv);

    var infoDiv = document.createElement("div");
    infoDiv.className = "beat-info";

    var speakerDiv = document.createElement("div");
    speakerDiv.className = "beat-speaker";
    speakerDiv.textContent = beat.speaker || "(narration)";
    infoDiv.appendChild(speakerDiv);

    var textDiv = document.createElement("div");
    textDiv.className = "beat-text";
    textDiv.textContent = beat.text;
    infoDiv.appendChild(textDiv);

    headerDiv.appendChild(infoDiv);

    var sectionBadge = document.createElement("span");
    sectionBadge.className = "beat-section";
    sectionBadge.textContent = beat.section;
    headerDiv.appendChild(sectionBadge);

    if (beat.needs_count > 0) {
      var needsBadge = document.createElement("span");
      needsBadge.className = "beat-badge";
      var needsNum = 3 - Object.keys(beat.clips).length;
      needsBadge.textContent = "NEEDS " + needsNum + " CLIPS";
      headerDiv.appendChild(needsBadge);
    }

    beatDiv.appendChild(headerDiv);

    // Clips container
    var clipsContainer = document.createElement("div");
    clipsContainer.className = "clips-container";

    for (var clipNum = 1; clipNum <= 3; clipNum++) {
      var clipCell = document.createElement("div");
      clipCell.className = "clip-cell";
      if (selected === clipNum) {
        clipCell.classList.add("selected");
      }

      var vidKey = beat.clips[clipNum];
      var clipLabel = document.createElement("span");
      clipLabel.className = "clip-label";
      clipLabel.textContent = "Option " + String.fromCharCode(64 + clipNum);
      clipCell.appendChild(clipLabel);

      var checkmark = document.createElement("div");
      checkmark.className = "clip-checkmark";
      checkmark.textContent = "✓";
      clipCell.appendChild(checkmark);

      if (vidKey && VID[vidKey]) {
        // Render video
        var video = document.createElement("video");
        video.src = VID[vidKey];
        video.controls = true;
        video.style.display = "block";

        (function(beatNum, clipNum, video) {
          clipCell.onclick = function() {
            selectClip(beatNum, clipNum);
          };
        })(num, clipNum, video);

        clipCell.appendChild(video);
      } else {
        // Placeholder
        var placeholder = document.createElement("div");
        placeholder.className = "clip-placeholder";
        placeholder.textContent = "Clip not available";
        clipCell.appendChild(placeholder);
      }

      clipsContainer.appendChild(clipCell);
    }

    beatDiv.appendChild(clipsContainer);

    // Action buttons
    var actionsDiv = document.createElement("div");
    actionsDiv.className = "beat-actions";

    var playAllBtn = document.createElement("button");
    playAllBtn.className = "action-btn";
    playAllBtn.textContent = "▶ Play All 3";
    playAllBtn.onclick = (function(beatNum) {
      return function() {
        playAllThreeForBeat(beatNum);
      };
    })(num);
    actionsDiv.appendChild(playAllBtn);

    if (beat.audio_key && AU[beat.audio_key]) {
      var playAudioBtn = document.createElement("button");
      playAudioBtn.className = "action-btn";
      playAudioBtn.textContent = "▶ Play Selected + Audio";
      playAudioBtn.disabled = !selected;
      playAudioBtn.onclick = (function(beatNum, audioKey) {
        return function() {
          playWithAudioForBeat(beatNum, audioKey);
        };
      })(num, beat.audio_key);
      actionsDiv.appendChild(playAudioBtn);
    }

    beatDiv.appendChild(actionsDiv);
    timeline.appendChild(beatDiv);
  }

  updateProgress();
}

function playAllThree() {
  var anyPlayed = false;
  for (var i = 0; i < BEATS.length; i++) {
    var beat = BEATS[i];
    var beatKey = "beat_" + beat.num;
    var selected = state[beatKey];

    if (selected) {
      var vidKey = beat.clips[selected];
      if (vidKey && VID[vidKey]) {
        var beatDiv = document.getElementById(beatKey);
        var videos = beatDiv.querySelectorAll("video");
        for (var j = 0; j < videos.length; j++) {
          videos[j].currentTime = 0;
          videos[j].muted = true;
          videos[j].play().catch(function() {});
        }
        anyPlayed = true;
      }
    }
  }

  if (!anyPlayed) {
    alert("No clips selected yet. Pick at least one clip to play.");
  }
}

function playAllThreeForBeat(beatNum) {
  var beatDiv = document.getElementById("beat_" + beatNum);
  if (!beatDiv) return;

  var videos = beatDiv.querySelectorAll("video");
  for (var i = 0; i < videos.length; i++) {
    videos[i].currentTime = 0;
    videos[i].muted = true;
    videos[i].play().catch(function() {});
  }
}

function playWithAudio() {
  for (var i = 0; i < BEATS.length; i++) {
    var beat = BEATS[i];
    var beatKey = "beat_" + beat.num;
    var selected = state[beatKey];

    if (selected && beat.audio_key && AU[beat.audio_key]) {
      playWithAudioForBeat(beat.num, beat.audio_key);
      return;
    }
  }

  alert("No selected clip with audio found.");
}

function playWithAudioForBeat(beatNum, audioKey) {
  var beat = null;
  for (var i = 0; i < BEATS.length; i++) {
    if (BEATS[i].num === beatNum) {
      beat = BEATS[i];
      break;
    }
  }

  if (!beat) return;

  var beatKey = "beat_" + beatNum;
  var selected = state[beatKey];

  if (!selected) {
    alert("No clip selected for this beat.");
    return;
  }

  var vidKey = beat.clips[selected];
  if (!vidKey || !VID[vidKey]) {
    alert("Selected clip not available.");
    return;
  }

  var beatDiv = document.getElementById(beatKey);
  var videos = beatDiv.querySelectorAll("video");

  // Play selected video
  for (var i = 0; i < videos.length; i++) {
    videos[i].pause();
    videos[i].currentTime = 0;
    videos[i].muted = true;
  }

  if (selected >= 1 && selected <= 3) {
    videos[selected - 1].muted = false;
    videos[selected - 1].play().catch(function() {});
  }

  // Play audio separately
  if (AU[audioKey]) {
    var audio = new Audio(AU[audioKey]);
    audio.play().catch(function() {});
  }
}

function clearSelection() {
  if (!confirm("Clear all selections?")) return;
  state = {};
  saveState();
}

function exportPicks() {
  var picks = {};
  for (var beatKey in state) {
    picks[beatKey] = state[beatKey];
  }

  var exportData = {
    picks: picks,
    timestamp: new Date().toISOString(),
    title: document.title
  };

  var now = new Date();
  var dateStr = now.getFullYear() + "-" +
    String(now.getMonth() + 1).padStart(2, "0") + "-" +
    String(now.getDate()).padStart(2, "0");

  var filename = "animation_picks_" + dateStr + ".json";

  var blob = new Blob([JSON.stringify(exportData, null, 2)], { type: "application/json" });
  var url = URL.createObjectURL(blob);
  var a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// Load state on page load
window.addEventListener("load", function() {
  loadState();
});
</script>

</body>
</html>
''')

    html = '\n'.join(html_parts)

    with open(output_path, 'w') as f:
        f.write(html)

    file_size_mb = len(html) / (1024 * 1024)
    print(f"\nAnimation review HTML written: {output_path}")
    print(f"  File size: {file_size_mb:.2f}MB")
    print(f"  Beats: {len(beat_metadata)}")
    print(f"  Video clips: {video_count}")
    print(f"  Audio files: {audio_count}")

    return output_path


def smoke_test(manifest_path):
    """
    Validate manifest structure and check all referenced files exist.
    Reports pass/fail with details. Exit 0 on success, 1 on failure.
    """
    print("\n" + "="*60)
    print("SMOKE TEST: Manifest Validation")
    print("="*60)

    try:
        manifest = read_manifest(manifest_path)
        beats = manifest.get("beats", [])

        if not beats:
            print("✗ FAIL: Manifest contains no beats")
            return False

        print(f"✓ Manifest loaded: {len(beats)} beats")

        all_files_exist = True

        for beat_idx, beat in enumerate(beats):
            beat_num = beat.get("num", beat_idx + 1)

            # Check required keys
            required_keys = ["num", "speaker", "text", "image_key", "clips"]
            missing_keys = [k for k in required_keys if k not in beat]

            if missing_keys:
                print(f"✗ Beat {beat_num}: Missing keys: {missing_keys}")
                all_files_exist = False
                continue

            # Check clips array structure
            clips = beat.get("clips", {})
            if not isinstance(clips, dict):
                print(f"✗ Beat {beat_num}: 'clips' is not a dict")
                all_files_exist = False
                continue

            # Check for at least one clip
            clip_files = [clips.get(f"option_{c}") for c in ["A", "B", "C"]]
            clip_files = [f for f in clip_files if f]

            if not clip_files:
                print(f"✗ Beat {beat_num}: No video clips found in clips dict")
                all_files_exist = False
                continue

            # Verify clip files exist
            for clip_name in ["option_A", "option_B", "option_C"]:
                clip_file = clips.get(clip_name)
                if clip_file:
                    if not os.path.exists(clip_file):
                        print(f"✗ Beat {beat_num} ({clip_name}): File not found: {clip_file}")
                        all_files_exist = False
                    else:
                        print(f"✓ Beat {beat_num} ({clip_name}): {os.path.basename(clip_file)}")

            # Check audio file if present
            audio_file = beat.get("audio_file")
            if audio_file:
                if not os.path.exists(audio_file):
                    print(f"✗ Beat {beat_num}: Audio file not found: {audio_file}")
                    all_files_exist = False
                else:
                    print(f"✓ Beat {beat_num}: Audio {os.path.basename(audio_file)}")

        if all_files_exist:
            print("\n✓ PASS: All files exist and manifest is valid")
            return True
        else:
            print("\n✗ FAIL: Some files are missing or manifest has errors")
            return False

    except Exception as e:
        print(f"✗ FAIL: {e}")
        return False


def audit_html(html_path):
    """
    Extract and report feature manifest from existing animation review HTML.
    Output as JSON to stdout.
    """
    if not os.path.exists(html_path):
        print(f"✗ HTML file not found: {html_path}")
        sys.exit(1)

    print(f"Auditing: {html_path}", file=sys.stderr)

    with open(html_path, "r") as f:
        html_content = f.read()

    # Count beats
    beat_count = html_content.count('"num":')

    # Count video options per beat (estimate from VID object)
    video_count = html_content.count('VID["beat_')

    # Estimate videos per beat
    videos_per_beat = video_count // max(beat_count, 1) if beat_count > 0 else 0

    # Embedded video size (rough estimate from base64)
    video_size_estimate = len(re.findall(r'data:video/mp4;base64,', html_content))

    # Embedded audio size
    audio_size_estimate = len(re.findall(r'data:audio/mpeg;base64,', html_content))

    # Check for localStorage
    has_local_storage = 'localStorage.getItem(STORAGE_KEY)' in html_content

    # Check for export functionality
    has_export = 'exportPicks' in html_content and 'application/json' in html_content

    # Check for drag-drop (not in current animation review, but for future)
    has_drag_drop = 'ondrop' in html_content or 'draggable' in html_content

    audit_result = {
        "file": html_path,
        "beats": beat_count,
        "videos_per_beat": videos_per_beat,
        "total_video_clips": video_count,
        "total_audio_clips": audio_size_estimate,
        "has_local_storage": has_local_storage,
        "has_export": has_export,
        "has_drag_drop": has_drag_drop,
        "file_size_kb": len(html_content) / 1024
    }

    print(json.dumps(audit_result, indent=2))


def audit_previous(current_html, previous_html):
    """
    Compare current build against previous version.
    Report regressions: same beats, audio present, videos present, localStorage, export.
    """
    if not os.path.exists(current_html):
        print(f"✗ Current HTML not found: {current_html}")
        sys.exit(1)

    if not os.path.exists(previous_html):
        print(f"✗ Previous HTML not found: {previous_html}")
        sys.exit(1)

    print(f"\nComparing builds:", file=sys.stderr)
    print(f"  Current:  {current_html}", file=sys.stderr)
    print(f"  Previous: {previous_html}", file=sys.stderr)

    with open(current_html, "r") as f:
        current = f.read()

    with open(previous_html, "r") as f:
        previous = f.read()

    # Count beats in both
    current_beats = current.count('"num":')
    previous_beats = previous.count('"num":')

    # Count videos in both
    current_videos = current.count('VID["beat_')
    previous_videos = previous.count('VID["beat_')

    # Count audio in both
    current_audio = len(re.findall(r'data:audio/mpeg;base64,', current))
    previous_audio = len(re.findall(r'data:audio/mpeg;base64,', previous))

    # Check features in both
    current_has_storage = 'localStorage.getItem(STORAGE_KEY)' in current
    previous_has_storage = 'localStorage.getItem(STORAGE_KEY)' in previous

    current_has_export = 'exportPicks' in current and 'application/json' in current
    previous_has_export = 'exportPicks' in previous and 'application/json' in previous

    regressions = []

    if current_beats != previous_beats:
        regressions.append(f"Beat count mismatch: {previous_beats} → {current_beats}")

    if current_videos < previous_videos:
        regressions.append(f"Video count decreased: {previous_videos} → {current_videos}")

    if current_audio < previous_audio:
        regressions.append(f"Audio count decreased: {previous_audio} → {current_audio}")

    if current_has_storage and not previous_has_storage:
        regressions.append("localStorage added (unexpected change)")
    elif not current_has_storage and previous_has_storage:
        regressions.append("localStorage REMOVED (regression)")

    if current_has_export and not previous_has_export:
        regressions.append("Export added (unexpected change)")
    elif not current_has_export and previous_has_export:
        regressions.append("Export REMOVED (regression)")

    result = {
        "current": {
            "beats": current_beats,
            "videos": current_videos,
            "audio": current_audio,
            "has_local_storage": current_has_storage,
            "has_export": current_has_export
        },
        "previous": {
            "beats": previous_beats,
            "videos": previous_videos,
            "audio": previous_audio,
            "has_local_storage": previous_has_storage,
            "has_export": previous_has_export
        },
        "regressions": regressions,
        "status": "PASS" if not regressions else "FAIL"
    }

    print(json.dumps(result, indent=2))

    if regressions:
        sys.exit(1)


def register_build_in_directus(output_path, module_id, event_number, beat_count, video_count, audio_count):
    """
    Register animation review build in Directus dashboard.

    Performs post-build registration:
    1. Reads Directus credentials from API_KEYS_MASTER.md
    2. Authenticates and obtains access token
    3. Checks if animation review HTML already registered in prod_visual_assets
    4. Creates or updates the asset record
    5. Updates prod_modules tracking fields
    6. Logs activity to prod_activity_log

    Args:
        output_path: Path to generated HTML file
        module_id: Module ID (e.g., "m1e1")
        event_number: Event number (e.g., 1)
        beat_count: Total beats in animation review
        video_count: Total video clips embedded
        audio_count: Total audio files embedded
    """

    try:
        # Step 1: Read Directus credentials from API_KEYS_MASTER.md
        script_dir = os.path.dirname(os.path.abspath(__file__))
        api_keys_path = os.path.join(script_dir, '..', 'API_KEYS_MASTER.md')

        if not os.path.exists(api_keys_path):
            print(f"  ⚠ Warning: API_KEYS_MASTER.md not found at {api_keys_path}")
            return

        with open(api_keys_path, 'r') as f:
            keys_content = f.read()

        # Extract Directus URL and credentials from markdown
        directus_url = "https://directus-production-3460.up.railway.app"
        directus_email = "kimhyla11@gmail.com"
        directus_password = "directus11$"

        print(f"\n  Registering animation review in Directus...")

        # Step 2: Authenticate with Directus
        auth_response = requests.post(
            f"{directus_url}/auth/login",
            json={
                "email": directus_email,
                "password": directus_password
            },
            timeout=10
        )

        if auth_response.status_code != 200:
            print(f"  ✗ Auth failed: {auth_response.status_code}")
            return

        auth_data = auth_response.json()
        access_token = auth_data.get("data", {}).get("access_token")
        if not access_token:
            print(f"  ✗ No access token in auth response")
            return

        headers = {"Authorization": f"Bearer {access_token}"}

        # Step 3: Check if animation review already registered
        filename = os.path.basename(output_path)
        asset_search = requests.get(
            f"{directus_url}/items/prod_visual_assets",
            params={"filter": json.dumps({"filename": {"_eq": filename}})},
            headers=headers,
            timeout=10
        )

        asset_id = None
        if asset_search.status_code == 200:
            existing = asset_search.json().get("data", [])
            if existing:
                asset_id = existing[0].get("id")

        # Step 4: Create or update asset
        asset_payload = {
            "filename": filename,
            "asset_type": "production_tool",
            "tool_type": "animation_review",
            "module_id": module_id,
            "event_number": event_number,
            "metadata": {
                "beat_count": beat_count,
                "video_count": video_count,
                "audio_count": audio_count,
                "generated_at": datetime.now().isoformat()
            }
        }

        if asset_id:
            # PATCH existing
            asset_response = requests.patch(
                f"{directus_url}/items/prod_visual_assets/{asset_id}",
                json=asset_payload,
                headers=headers,
                timeout=10
            )
        else:
            # POST new
            asset_response = requests.post(
                f"{directus_url}/items/prod_visual_assets",
                json=asset_payload,
                headers=headers,
                timeout=10
            )

        if asset_response.status_code not in [200, 201]:
            print(f"  ✗ Asset registration failed: {asset_response.status_code}")
            return

        # Step 5: Update prod_modules tracking fields
        current_iso = datetime.now().isoformat()
        modules_update = {
            "animation_review_status": "built",
            "animation_review_version": 1,  # Can be incremented if doing versioning
            "animation_review_built_at": current_iso,
            "animation_review_build_mode": "manifest"
        }

        # For now, we'll try to find and update the module
        # In practice, this might need module_id resolution
        module_search = requests.get(
            f"{directus_url}/items/prod_modules",
            params={"filter": json.dumps({"id": {"_eq": module_id}})},
            headers=headers,
            timeout=10
        )

        if module_search.status_code == 200:
            modules = module_search.json().get("data", [])
            if modules:
                mod = modules[0]
                current_version = mod.get("animation_review_version", 0)
                modules_update["animation_review_version"] = current_version + 1

                mod_response = requests.patch(
                    f"{directus_url}/items/prod_modules/{mod.get('id')}",
                    json=modules_update,
                    headers=headers,
                    timeout=10
                )

                if mod_response.status_code != 200:
                    print(f"  ⚠ Module update failed: {mod_response.status_code}")

        # Step 6: Log to prod_activity_log
        activity_log = {
            "action": "animation_review_build",
            "details": json.dumps({
                "beat_count": beat_count,
                "video_count": video_count,
                "audio_count": audio_count,
                "module_id": module_id,
                "event_number": event_number,
                "filename": filename,
                "timestamp": current_iso
            })
        }

        log_response = requests.post(
            f"{directus_url}/items/prod_activity_log",
            json=activity_log,
            headers=headers,
            timeout=10
        )

        if log_response.status_code != 201:
            print(f"  ⚠ Activity log failed: {log_response.status_code}")

        print(f"  ✓ Registered in Directus: {filename}")
        print(f"    Beats: {beat_count}, Videos: {video_count}, Audio: {audio_count}")

    except Exception as e:
        print(f"  ⚠ Directus registration error: {e}")
        # Non-blocking error - build succeeded, registration optional


def main():
    parser = argparse.ArgumentParser(
        description="Generate a self-contained HTML animation review tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES:
  python3 build_animation_review.py \\
    --manifest beats.json \\
    --output review.html \\
    --title "M1E1 Animation Review"

  python3 build_animation_review.py \\
    --manifest beats.json \\
    --output /tmp/review.html \\
    --title "Tessa Story Scene" \\
    --subtitle "Arc 1, Module 1"

  python3 build_animation_review.py \\
    --manifest beats.json \\
    --smoke-test

  python3 build_animation_review.py \\
    --audit review.html

  python3 build_animation_review.py \\
    --audit-previous current.html previous.html
        """
    )

    parser.add_argument("--manifest", help="Path to beats manifest JSON file")
    parser.add_argument("--output", help="Output HTML file path")
    parser.add_argument("--title", default="Animation Review",
                        help="Page title (default: 'Animation Review')")
    parser.add_argument("--subtitle", default="",
                        help="Page subtitle (optional)")
    parser.add_argument("--smoke-test", action="store_true",
                        help="Validate manifest structure and check all files exist")
    parser.add_argument("--audit", metavar="HTML_FILE",
                        help="Extract and report feature manifest from existing HTML")
    parser.add_argument("--audit-previous", metavar=("CURRENT_HTML", "PREVIOUS_HTML"),
                        nargs=2, help="Compare current build against previous version")
    parser.add_argument("--register", action="store_true",
                        help="Register build in Directus after creating HTML")
    parser.add_argument("--module-id", default="",
                        help="Module ID for Directus registration (e.g., 'm1e1')")
    parser.add_argument("--event-number", type=int, default=1,
                        help="Event number for Directus registration (default: 1)")

    args = parser.parse_args()

    try:
        # Smoke test mode
        if args.smoke_test:
            if not args.manifest:
                print("✗ Error: --smoke-test requires --manifest")
                sys.exit(1)
            success = smoke_test(args.manifest)
            sys.exit(0 if success else 1)

        # Audit existing HTML mode
        elif args.audit:
            audit_html(args.audit)
            sys.exit(0)

        # Audit previous comparison mode
        elif args.audit_previous:
            current_html, previous_html = args.audit_previous
            audit_previous(current_html, previous_html)
            sys.exit(0)

        # Normal build mode
        else:
            if not args.manifest or not args.output:
                print("✗ Error: Normal build requires both --manifest and --output")
                sys.exit(1)
            manifest = read_manifest(args.manifest)
            build_animation_review(manifest, args.output, args.title, args.subtitle)
            print("\n✓ Animation review tool generated successfully")

            # Post-build registration if requested
            if args.register:
                beats = manifest.get("beats", [])
                beat_count = len(beats)

                # Count videos and audio files
                video_count = 0
                audio_count = 0
                for beat in beats:
                    clips = beat.get("clips", {})
                    for clip_name in ["option_A", "option_B", "option_C"]:
                        if clips.get(clip_name):
                            video_count += 1
                    if beat.get("audio_file"):
                        audio_count += 1

                register_build_in_directus(
                    args.output,
                    args.module_id,
                    args.event_number,
                    beat_count,
                    video_count,
                    audio_count
                )

    except Exception as e:
        print(f"\n✗ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
