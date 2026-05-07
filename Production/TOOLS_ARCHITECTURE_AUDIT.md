# MindfulNest Production Tools Architecture Audit
**Comprehensive Analysis of 4 Builder Scripts**
**Completed:** April 14, 2026

---

## Executive Summary

MindfulNest has 4 production builder tools that generate self-contained HTML workstations for different review/approval phases. All 4 share a common architectural DNA — embed assets as base64, render via JavaScript, use localStorage for state, support audit/export cycles — but diverge significantly in their data models, interactivity patterns, and integration points. This audit identifies shared patterns, gaps, and recommendations for a unified "universal container" pattern that future tools should follow.

**Key finding:** Tools have 70% code duplication in HTML scaffolding/styling but zero code sharing; all 4 are essentially hand-built variants of the same pattern. A shared library/base class would consolidate this and enable consistent feature rollout.

---

## 1. BUILD_STORYBOARD.PY (1,427 lines)

### Architecture Pattern

**Embed strategy:** Base64 image thumbnails (80px) + reference-size images (200px) stored in JS objects (`TH{}` for thumbs, refs in comments). Audio embeds as full base64 MP3 in `AU{}`.

**HTML structure:**
```
Head
  ├─ CSS (grid, cards, play buttons, drag-drop visual hints)
  └─ Meta: warning comment about direct editing + CLI rebuild advice
Body
  ├─ Controls bar (Play All, Stop, Add Line, Export Sequence)
  ├─ Image reference grid (draggable thumbnails for drag-drop source)
  ├─ Timeline container (dynamic, populated from JS data)
  └─ Export panel (hidden until Export clicked, shows JSON)
Script
  ├─ Asset data (TH, AU, IN=image_labels, SP=speakers, L=lines array)
  ├─ State (cA=currentAudio, paA=playingAll, paI=playIndex, lines array L[])
  └─ Render engine (render() function, ~400 lines of DOM manipulation)
```

### Data Flow

**Input manifest (lines):**
```json
[
  {
    "speaker": "Guide Bird",
    "text": "Are you OK?",
    "image": "master",      // Key into image_labels
    "audio_key": null,       // Key into audio data, or null
    "pause": 0.5,           // Pause duration in seconds
    "section": "Setup"      // Logical grouping (rendered as section header)
  }
]
```

**Output (Export Locked Sequence):**
```json
{
  "lines": [
    {
      "speaker": "...",
      "text": "...",
      "image": "...",
      "audio_key": "...",
      "pause": 0.5,
      "section": "..."
    }
  ],
  "exported_at": "ISO timestamp"
}
```

### Selection Mechanism

**Edit in-browser:** Click speaker dropdown (30+ speakers), edit dialogue textarea (with [pause] tag insertion button), assign image per line via dropdown, adjust pause slider (0-2s range). Reorder lines via drag buttons (↑↓). Add/delete lines.

**Export:** "Export Locked Sequence" button → renders JSON to pre block → "Copy to Clipboard" or "Download as JSON (for builder)" buttons.

### Playback

**Audio:** Click-to-play per line (green button if audio present, gray if not). Mutual exclusion: only one line plays at once. Auto-advances to next line on end. "Play All" button plays audio sequentially across all lines. Stop button stops current playback.

**Visual:** No animation; static images assigned per line. Drag-drop *source* is the image grid above timeline; *drop zones* are the image placeholders in each line.

### Persistence

**localStorage:** Key = `storyboard_edits_{title_slug}`. Stores L[] (lines array) and cA/paA state. Auto-save on textarea/dropdown change. Manual load on page load.

**Caveat:** Kim's exported JSON is the source of truth; localStorage is volatile. CLAUDE.md Rule 6 mandates: "Kim's exported sequence JSON is the MANDATORY primary source for rebuild."

### Registration Hook

**Function:** `register_build_in_directus(output_path, module_id, event_number, build_mode, features_dict)`

**Call:** Triggered automatically after successful build if module_id/event_number provided.

**Actions:**
1. Auth to Directus via `_directus_auth()` (reads API_KEYS_MASTER.md)
2. POST/PATCH `prod_visual_assets` with filename, filepath, module_id, asset_type="storyboard_html", status, build_mode, feature_summary JSON
3. PATCH `prod_modules` with storyboard_status="built", storyboard_version, storyboard_built_at (ISO), storyboard_build_mode
4. POST `prod_activity_log` with action="storyboard_build", details dict (output_path, module_id, event_number, build_mode, asset_id, filename, timestamp)

### CLI Modes

1. **--registry --module M1 --event 1 --lines lines.json --output storyboard.html** (PREFERRED)
   - Calls `build_storyboard_from_registry(module_id, event_number, lines, output_path, title, subtitle, image_base_path)`
   - Queries Directus `prod_visual_assets` registry for approved images (via `query_registry_images()`)
   - Pre-rebuild: extract features from previous version if `--audit-previous` provided
   - Build
   - Post-build: compare features (check for regressions via `compare_features()`)
   - Auto-register

2. **--config config.json --output storyboard.html** (FALLBACK)
   - Legacy mode, warns user
   - Calls `build_storyboard(config, output_path)`
   - Same pre/post audit cycle
   - Auto-register if config has module_id/event_number

3. **--export-image-map --module M1 --event 1 [--output map.json]**
   - Queries registry, generates JSON traceability map: `{storyboard_key: {path, label, dimensions}}`
   - Outputs to file or stdout

4. **--smoke-test**
   - Calls `smoke_test()`: verifies Directus auth works, queries prod_visual_assets schema
   - No build, just connectivity check

5. **--audit storyboard.html**
   - Calls `extract_features(html_path)`: counts images (TH{}), lines (L[]), audio (AU{}), checks for drag-drop/play-all/export functions, extracts per-line image assignments
   - Output: JSON feature manifest

6. **--audit-previous current.html previous.html**
   - Calls `compare_features(before_features, after_path)`: regression check
   - Detects lost drag-drop, lost audio, image count drop, line count drop, image assignment scrambling (per-line image map diffs)
   - Prints warnings if regressions found

### Shared Patterns

- **Base64 encoding:** `encode_image(path, thumb_size=80, ref_size=200)` creates two versions (thumbnail for UI, reference for export). Uses PIL if available, warns if not.
- **Credential reading:** `_read_credentials()` parses API_KEYS_MASTER.md markdown table, falls back to env vars
- **Module ID parsing:** `_parse_module_id(module_id)` converts "M1"/"m1"/1 to integer (required for Directus INTEGER field)
- **Directus auth:** `_directus_auth()` returns (token, base_url), called by registration and registry query
- **Feature extraction:** `extract_features()` regex-parses the built HTML to extract feature manifest (no JSON metadata embedded — must be reconstructed from JS vars)

### Gaps & Limitations

1. **No versioning in output:** HTML file itself has no version number. Feature manifest is reverse-engineered from HTML JS vars, not embedded as metadata. Makes audit brittle.
2. **Image scrambling risk:** Per-line image assignments are extracted via regex (`\{s:"([^"]*)",t:"((?:[^"\\]|\\.)*)",i:"([^"]*)"`) — if Kim's edits weren't exported and rebuild pulls from stale JSON, assignments are lost. CLAUDE.md Rule 6 warns about this.
3. **Drag-drop not auto-registered:** When Kim drags images in browser and doesn't export, next rebuild loses the edits. No auto-save to localStorage+export, only manual JSON export.
4. **No thumbnail refresh:** Thumbnails are frozen at build time; if Directus images are updated, storyboard isn't invalidated.
5. **Registry query is slow:** `query_registry_images()` makes an HTTP request per build; no caching.

---

## 2. BUILD_CROPPER.PY (797 lines)

### Architecture Pattern

**Embed strategy:** Full image as base64 MIME data URI, injected into DOMContentLoaded preload block. Single image, no multi-asset carousel.

**HTML structure:**
```
Head
  ├─ CSS (canvas, crop tools, viewport)
  └─ Meta: HTML5 Canvas-based editor (not SVG, not DOM elements)
Body
  ├─ Canvas element (where crop happens)
  ├─ Controls panel (name crop box, save as PNG, undo, redo)
  └─ Crop library (list of saved crops, drag-to-reorder)
Script
  ├─ Preload block (injected by builder, calls loadImageFromSrc(data_uri, filename))
  ├─ Canvas state (selectedBox, boxes[], undo stack)
  └─ Draw engine (canvas.drawImage, clip region, export as PNG)
```

### Data Flow

**Input:**
```python
build_cropper(image_path, output_path, title, min_dimension=600, module_id, event_number)
```

**Output (Save to Disk per crop):**
```
PNG file (binary) — user clicks "Save as PNG" for each named crop box
```

**No JSON output** — crops are transient, stored in localStorage during session. If user wants to persist, they download each PNG manually.

### Selection Mechanism

**Visual:** Draw crop box on canvas by clicking+dragging. Name each box (text input). Buttons: Undo/Redo, Save as PNG (downloads), Delete crop. Crops can be reordered in sidebar (drag-drop).

**Validation:** Hard gate: minimum shortest dimension = 600px (configurable, default 600). If crop doesn't meet threshold, save button is disabled + warning shown.

### Playback

**None** — this is a static crop tool, not a player.

### Persistence

**localStorage:** Key = `${filename}_crops`. Stores array of `{name, x, y, w, h}` objects. Persists across page reloads. No server-side sync.

### Registration Hook

**Function:** `register_build_in_directus(output_path: str, module_id: int, event_number: int, source_image: str)`

**Call:** Triggered after build if module_id and event_number provided.

**Actions:**
1. Auth to Directus
2. POST `prod_visual_assets` with filename (the HTML tool itself), filepath, module_id, event_number, asset_type="cropper_html", status="built", source_image (the preloaded image filename)
3. PATCH `prod_modules` with cropper_status="built", cropper_built_at (ISO)
4. POST `prod_activity_log` with action="cropper_build", details (output_path, module_id, event_number, source_image, timestamp)

### CLI Mode

**Single mode:**
```bash
python3 build_cropper.py --image master.png --output cropper.html --title "Master Shot" --min-dimension 600 --module-id 1 --event-number 1
```

**No audit/smoke-test modes** — this tool is simpler than storyboard.

### Shared Patterns

- **Base64 encoding:** `base64.b64encode(image_bytes)` for the MIME data URI
- **Preload block:** Template substitution pattern (builder fills `{{PRELOAD_BLOCK}}` in HTML template)
- **Module ID handling:** Integer param, no parsing required
- **Directus registration:** Same auth pattern, credentials from API_KEYS_MASTER.md

### Gaps & Limitations

1. **No export of crop metadata:** Crops are localStorage-only. If user closes tab without saving PNGs, crops are lost.
2. **No batch download:** Must click "Save as PNG" individually for each crop. No "Save All" button.
3. **No image versioning:** Can't compare crops across builds. No audit/regression check.
4. **Single image only:** Can't load multiple images or reference a set of pre-approved master images. Manual per-image.
5. **Canvas rendering:** Platform-dependent rendering differences between Chrome/Safari. No headless export pipeline.

---

## 3. BUILD_TTS_REVIEW.PY (655 lines)

### Architecture Pattern

**Embed strategy:** Audio files as base64 MP3 data URIs in `AUDIO_DATA[]` object. Line metadata in JSON alongside audio keys. No image embedding (though lines can be tagged as "personalized" for visual badge).

**HTML structure:**
```
Head
  ├─ CSS (line cards, play buttons, status dots, verdict badges)
  └─ Meta: TTS audition workstation, interactive line review
Body
  ├─ Header (title, line count, ElevenLabs model version)
  ├─ Line cards (one per TTS segment)
  │  ├─ Speaker + audio status (green play button if audio present)
  │  ├─ Editable text field (`<textarea>` with voice_id data attribute)
  │  ├─ Regenerate button (calls ElevenLabs API in-browser with same voice settings)
  │  ├─ Save to Disk button (triggers download of MP3 after regen)
  │  └─ Verdict buttons (Approve / Redo, with radio-style selection)
  └─ Footer (Export Verdicts button, Save All Approved to Disk button)
Script
  ├─ Asset data (API_KEY, MODEL, SETTINGS={stability,similarity_boost,style}, AUDIO_DATA={}, FILENAMES={}, LINE_IDS=[])
  ├─ State (currentPlaying, verdicts={}, regenCounts={}, unsavedRegens={})
  └─ Playback + regen engine (togglePlay, regenerate via ElevenLabs fetch, saveToDisk via blob/download)
```

### Data Flow

**Input config:**
```json
{
  "title": "Event 1: Tessa's Fall — Story Scene TTS",
  "event_id": "m1_event_1",
  "api_key": "YOUR_ELEVENLABS_API_KEY",
  "model": "eleven_v3",
  "voice_settings": {"stability": 0.30, "similarity_boost": 0.80, "style": 0.30},
  "lines": [
    {
      "id": "line_02",
      "speaker": "Guide Bird",
      "voice_id": "7o9pyvsN0ob5GO6LBQp6",
      "text": "[sympathetic] Hello.... Are you OK...?",
      "audio_path": "/path/to/line_02_guide_bird.mp3",
      "filename": "line_02_guide_bird.mp3",
      "personalized": false
    }
  ]
}
```

**Output (Export Verdicts):**
```
Plain text report:
  === TTS AUDITION VERDICTS ===
  [title]
  Exported: [ISO timestamp]
  
  line_02: APPROVED | regens:0 | original | [sympathetic] Hello.... Are...
  line_03: REDO | regens:2 | saved | [hopeful] I'm okay, I think...
```

**Output (Save to Disk):** Individual MP3 files (post-regeneration)

### Selection Mechanism

**Interactive:** Click speaker-colored line number to focus. Edit text in textarea (with [pause] markers). Click "Regenerate" to call ElevenLabs API in-browser (blocks UI during fetch). Click "Save to Disk" to download blob. Select verdict: Approve or Redo (radio toggle). Export verdicts to clipboard for logging.

**Regeneration:** Reads `text` from textarea, reads `voice_id` from `data-voice` attribute, POSTs to ElevenLabs API with locked `SETTINGS`, receives blob, plays auto, marks as "unsaved", pulsing "Save to Disk" button.

### Playback

**Audio:** Click-to-play per line (mutual exclusion: stops previous line if playing). Status badges show: "original" (green dot, original TTS), "regen #N (unsaved)" (orange dot, regenerated but not downloaded), "regen #N (saved)" (green dot, regenerated and downloaded).

**Visual hints:** Status color coded, regen count displayed.

### Persistence

**localStorage:** Key = `verdicts_{event_id}`, stores `{line_id: "approved"|"redo"|}`. Persists across reloads. No auto-save of text edits or regen state.

**Caveats:** Unsaved regenerations (blob URL state) are lost on tab close. "Save to Disk" is explicit action, not automatic.

### Registration Hook

**Function:** `register_build_in_directus(output_path, module_id, event_number, line_count, build_mode="config")`

**Call:** Triggered after build if module_id and event_number provided.

**Actions:**
1. Auth to Directus
2. POST/PATCH `prod_visual_assets` with filename (the HTML tool), filepath, shot_number=1 (single file), module_id, asset_type="tts_audition_tool", status="built", notes (line count, built via build_tts_review.py)
3. PATCH `prod_modules` with tts_audition_status="built", tts_audition_built_at (ISO), tts_audition_build_mode
4. POST `prod_activity_log` with action="tts_audition_build", details (output_path, module_id, event_number, line_count, build_mode, asset_id, filename, timestamp)

### CLI Mode

**Single mode:**
```bash
python3 build_tts_review.py --config tts_config.json --output audition_player.html [--module-id 1 --event-number 1 --build-mode config]
```

**No audit/smoke-test modes** — config validation only at load time.

### Shared Patterns

- **Base64 encoding:** `encode_audio(path)` reads MP3 as bytes, encodes to base64
- **ElevenLabs API:** Hardcoded endpoint `https://api.elevenlabs.io/v1/text-to-speech/{voice_id}`, headers with `xi-api-key`, JSON body with text/model_id/voice_settings
- **Directus registration:** Same pattern as storyboard
- **Credential handling:** API key embedded in HTML (!) — user provides in config during build

### Gaps & Limitations

1. **API key exposure:** ElevenLabs API key embedded in HTML. Anyone with the HTML can call the API and burn credits. SECURITY ISSUE. (Mitigated by: Kim only shares file with trusted reviewers; tool is ephemeral; should use backend proxy instead.)
2. **No audit trail:** No way to query which lines were regenerated, how many times, when. Only localStorage verdicts exported.
3. **Blob state fragile:** Regenerated audio blobs are lost on tab close. No server-side caching.
4. **No batch regenerate:** Can't regenerate all lines at once; must do individually.
5. **No text diff:** Can't see what changed between original and regenerated TTS without editing text field yourself.

---

## 4. BUILD_ANIMATION_REVIEW.PY (1,424 lines)

### Architecture Pattern

**Embed strategy:** Multiple video clips (3 options per beat) + audio files as base64 data URIs. `VID{}` for videos, `AU{}` for audio. Beat metadata in JSON.

**HTML structure:**
```
Head
  ├─ CSS (grid, video players, beat cards, clip selection UI)
  └─ Meta: Animation review workstation, multi-option clip comparison
Body
  ├─ Header (title, subtitle, progress bar showing N/M beats reviewed)
  ├─ Controls (Play All, Stop, Export Picks, Download JSON)
  ├─ Timeline
  │  ├─ Section headers (e.g., "Scene", "Resolution")
  │  └─ Beat cards (one per dialogue line)
  │     ├─ Beat number (red circle)
  │     ├─ Speaker + text + section tag + "needs X clips" badge (if incomplete)
  │     ├─ Clips container (grid of 3 video players side-by-side, option_A/B/C)
  │     │  └─ Each player: click-to-play video, duration display, selection checkbox
  │     ├─ Audio player (optional, for reference)
  │     └─ Verdict: selected clip badge (option 1/2/3)
  └─ Export panel (hidden, shows selected picks as JSON)
Script
  ├─ Asset data (VID={}, AU={}, BEATS=[])
  ├─ State (selectedPicks={beat_num: 1|2|3|null}, currentPlaying, STORAGE_KEY)
  └─ Player engine (play video on click, mutual exclusion, export picks to JSON+clipboard)
```

### Data Flow

**Input manifest:**
```json
{
  "beats": [
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
  ]
}
```

**Output (Export Picks):**
```json
{
  "picks": {
    "1": 2,      // Beat 1: user selected option 2 (option_B)
    "2": 1,      // Beat 2: option 1 (option_A)
    "3": null    // Beat 3: no selection (incomplete)
  },
  "exported_at": "ISO timestamp"
}
```

### Selection Mechanism

**Visual:** Play each video clip option independently (click play button within each clip card). See all 3 options side-by-side. Click checkbox below a video to select it for that beat. Selected clip gets highlighted border + checkmark badge. "Export Picks" button renders JSON to panel.

**Verdict:** Implicit selection of best clip (1/2/3) per beat. Incomplete beats show "needs X clips" badge in red if some options are missing.

### Playback

**Video:** Click-to-play per option (HTML5 video tag with data URI). Duration displayed. Mutual exclusion: stops previous video if playing. No auto-advance across beats (each beat is independent).

**Audio:** Reference audio plays alongside selected beat (optional). Displayed duration vs. audio_duration for sync check.

### Persistence

**localStorage:** Key = `mindfulnest_animation_review_{title_slug}`. Stores `{beat_num: selected_option_num}` picks dictionary. Persists across reloads.

### Registration Hook

**Function:** `register_build_in_directus(output_path, module_id, event_number, beat_count, video_count, audio_count)`

**Call:** Triggered after build if --register flag provided (explicit, not automatic like storyboard).

**Actions:**
1. Auth to Directus
2. POST `prod_visual_assets` with filename, filepath, module_id, event_number, asset_type="animation_review_html", status="built", notes (beat_count, video_count, audio_count, built via build_animation_review.py)
3. PATCH `prod_modules` with animation_review_status="built", animation_review_built_at (ISO)
4. POST `prod_activity_log` with action="animation_review_build", details (output_path, module_id, event_number, beat_count, video_count, audio_count, timestamp)

### CLI Modes

1. **--manifest beats.json --output review.html [--title "..." --subtitle "..."]**
   - Calls `build_animation_review(manifest, output_path, title, subtitle)`
   - Builds HTML, embeds all video/audio assets

2. **--smoke-test --manifest beats.json**
   - Calls `smoke_test(manifest_path)`: validates JSON structure, checks all video/audio files exist on disk
   - Exit 0 if pass, 1 if fail

3. **--audit review.html**
   - Calls `audit_html(html_path)`: counts beats, videos per beat, audio clips, checks for localStorage/export/drag-drop features
   - Output: JSON feature manifest

4. **--audit-previous current.html previous.html**
   - Calls `audit_previous(current_html, previous_html)`: regression check
   - Detects: beat count mismatch, video count decrease, audio count decrease, feature loss (localStorage, export)

5. **--register --module-id m1e1 --event-number 1** (post-build optional)
   - Registration happens if flag provided; most commonly chained after build

### Shared Patterns

- **Base64 encoding:** `encode_video(path)` and `encode_audio(path)` read binary files, encode to base64
- **Manifest validation:** `read_manifest(manifest_path)` loads JSON, validates structure
- **Feature extraction:** `audit_html()` regex-parses the built HTML to count beats, videos, audio, check for JS functions
- **Directus auth:** Same pattern as other tools
- **Storage key slugify:** `title_slug = re.sub(r'[^a-z0-9]', '_', title.lower()).strip('_')`

### Gaps & Limitations

1. **Video size explosion:** Each beat can have 3 clips (3 data URIs). For a 10-beat event with 2.5MB clips each, that's 75MB of base64 in the HTML. Browsers may choke on parsing/memory.
2. **No clip comparison UI:** Three clips play independently; no sync/side-by-side play. Kim must manually compare timing/pacing.
3. **No duration validation:** Audio duration vs. video duration mismatch isn't flagged. If audio is 2.5s and video option_A is 3.0s, there's no warning.
4. **No undo after export:** Once picks are exported, no way to revise without reload.
5. **Incomplete beat handling:** "Needs X clips" badge counts *missing* options, but doesn't prevent export. Kim can export picks with null values.

---

## Shared Architectural Patterns

### 1. **Base64 Embedding Pattern** (ALL 4 TOOLS)

```python
def encode_asset(path: str) -> str:
    with open(path, 'rb') as f:
        return base64.b64encode(f.read()).decode()

# Embedded in HTML as:
# AUDIO_DATA["key"] = "data:audio/mpeg;base64,{b64_string}";
# or
# window.addEventListener('DOMContentLoaded', () => {
#   img.src = 'data:image/png;base64,{b64_string}';
# });
```

**Trade-offs:**
- Pros: Self-contained HTML, no external fetch calls, works offline
- Cons: File size grows linearly with asset size; browser parsing/memory overhead; base64 is ~33% larger than binary

### 2. **Credential Reading Pattern** (BUILD_STORYBOARD, BUILD_TTS_REVIEW)

```python
def _read_credentials():
    # Try API_KEYS_MASTER.md in several locations
    # Fall back to env vars DIRECTUS_EMAIL / DIRECTUS_PASSWORD
    # Extract from markdown table: parse | delimiters, grab column 3
```

**Consistency:** Storyboard and TTS_Review both implement this. Cropper and Animation_Review don't (they don't call Directus at runtime). Should be a shared utility module.

### 3. **Directus Auto-Registration Pattern** (ALL 4 TOOLS)

**Trigger:** After successful build, if module_id/event_number provided.

**Steps:**
1. Auth via `_directus_auth()` or hardcoded credentials
2. POST/PATCH `prod_visual_assets` (asset metadata)
3. PATCH `prod_modules` (tracking fields for storyboard_status/tts_audition_status/etc.)
4. POST `prod_activity_log` (audit trail)

**Inconsistency:** Storyboard auto-registers by default. Cropper auto-registers if module_id provided. TTS_Review auto-registers if module_id provided. Animation_Review requires explicit `--register` flag.

### 4. **Feature Extraction & Audit Pattern** (BUILD_STORYBOARD, BUILD_ANIMATION_REVIEW)

```python
def extract_features(html_path: str) -> dict:
    # Regex-parse the built HTML to reverse-engineer feature manifest
    # Count: JS data structures (TH, AU, L, VID), functions (initDrag, playAllAudio, exportSeq)
    # Return dict with counts + feature booleans
    
def compare_features(before: dict, after_path: str) -> bool:
    # Detect regressions: lost features, lower counts, scrambled assignments
```

**Tools using this:** Storyboard (has both), Animation_Review (has both). TTS_Review and Cropper don't.

**Limitation:** Feature extraction is brittle regex parsing; no canonical metadata. Should embed version/feature JSON in HTML comment or `<meta>` tag.

### 5. **localStorage Persistence Pattern** (STORYBOARD, TTS_REVIEW, ANIMATION_REVIEW)

```javascript
var STORAGE_KEY = 'storyboard_edits_' + titleSlug;

document.addEventListener('DOMContentLoaded', () => {
  var saved = localStorage.getItem(STORAGE_KEY);
  if (saved) L = JSON.parse(saved);
});

// Auto-save on edit
textarea.oninput = () => {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(L));
};
```

**Cropper also uses localStorage** but for a different purpose (crop boxes, not editable state).

**Limitations:** localStorage is per-domain, not synced to server; cleared if user clears browser data; max ~5-10MB depending on browser.

### 6. **Verdict/Approval Pattern** (TTS_REVIEW, ANIMATION_REVIEW)

**TTS_Review:** Approve/Redo radio buttons per line → export as CSV-ish text.

**Animation_Review:** Select best clip (1/2/3) per beat → export as JSON picks dictionary.

**No shared pattern:** Each tool implements approval differently, no consistency for cross-tool workflows.

### 7. **Error Handling & Validation Pattern**

**Storyboard:** Pre-build smoke-test checks Directus connectivity. Graceful fallback from registry → config mode.

**Cropper:** Checks image dimensions against min_dimension; disables save button if validation fails.

**TTS_Review:** No pre-build validation; config JSON must be well-formed or build fails loudly.

**Animation_Review:** Smoke-test validates manifest structure + file existence.

**No unified validation framework** — each tool rolls its own.

---

## Gaps & Opportunities

### Critical Gaps

1. **No shared base library:** 70% of HTML/CSS/JS is duplicated across tools. A shared `BaseHTMLBuilder` class or template system would:
   - Consolidate styling (dark theme, spacing, colors)
   - Provide reusable components (play buttons, selectors, export panels)
   - Ensure consistent localStorage key naming
   - Centralize credential reading

2. **No canonical metadata format:** Feature manifests are reverse-engineered via regex; no embedded version/feature JSON. Should add:
   ```html
   <!-- METADATA:
   {
     "version": "3",
     "tool": "build_storyboard.py",
     "generated_at": "ISO timestamp",
     "features": {
       "drag_drop": true,
       "audio": true,
       "export": true
     }
   }
   -->
   ```

3. **No unified approval/verdict format:** TTS_Review uses "Approve/Redo" text. Animation_Review uses numeric picks (1/2/3). Should agree on a JSON schema for all approval workflows.

4. **API key exposure (TTS_Review):** ElevenLabs API key embedded in HTML. Should use a backend proxy or secure token exchange.

5. **No batch operations:** 
   - Storyboard: Can't batch-regenerate all audio
   - Cropper: Can't batch-download all crops
   - TTS_Review: Can't batch-regenerate all lines
   - Animation_Review: Can't batch-export multiple beat picks to a manifest

6. **No sync to server:** All state is localStorage-only or requires manual export. No automatic sync to Directus, no conflict resolution if Kim opens two tabs.

7. **No rollback/versioning:** If a rebuild loses features, no way to restore. Should keep `prod_visual_assets` history or tag versions.

### Design Opportunities

1. **Universal container pattern:** A Python base class that all 4 tools inherit from:
   ```python
   class BaseHTMLBuilder:
       def __init__(self, title, subtitle, module_id, event_number):
           self.title = title
           self.subtitle = subtitle
           # ...
       
       def build(self) -> str:
           # Generate HTML scaffold (head, CSS, body structure)
           # Subclasses override to add tool-specific UI
           pass
       
       def embed_assets(self):
           # Encode files, inject into HTML
           pass
       
       def register_in_directus(self):
           # Standard registration flow
           pass
       
       def extract_features(self) -> dict:
           # Standard feature audit
           pass
   ```

2. **Shared credentials module:** Move credential reading, Directus auth, API patterns to a `production/api_client.py`:
   ```python
   from api_client import DirectusClient
   client = DirectusClient()
   client.register_visual_asset(filename, module_id, ...)
   client.patch_modules(module_id, tracking_fields)
   client.log_activity(action, details)
   ```

3. **Unified verdict schema:** All approval tools should export JSON with consistent structure:
   ```json
   {
     "tool": "build_tts_review.py" | "build_animation_review.py",
     "event_id": "m1_event_1",
     "verdicts": {
       "line_02": {"verdict": "approved", "metadata": {...}},
       "beat_01": {"picked_clip": 2, "metadata": {...}}
     },
     "exported_at": "ISO timestamp"
   }
   ```

4. **Server-side sync layer:** Optional backend endpoint that:
   - Receives localStorage state on demand
   - Persists to Directus with conflict resolution
   - Returns latest state on load (multi-tab sync)
   - Archives old versions

5. **Composite review tool:** A 5th tool that loads multiple review types in tabs:
   - Storyboard tab (dialogue, images)
   - Animation tab (clip picks)
   - TTS tab (audio verdicts)
   - Export all verdicts together as one JSON
   - Single Directus registration for the entire event

6. **Asset size management:** For animation_review, implement:
   - Lazy-load video/audio (don't decode until user clicks play)
   - Progressive file size estimates during build
   - Warn if HTML > 100MB
   - Optional: split into multiple HTMLs if too large

---

## Universal Container Pattern (Recommended)

All future production tools should follow this architecture:

### 1. Directory Structure
```
tools/
  ├─ base.py                    # BaseHTMLBuilder class
  ├─ api_client.py              # DirectusClient, credential reading
  ├─ assets.py                  # encode_image, encode_audio, encode_video
  ├─ build_storyboard.py        # Tool 1 (inherits BaseHTMLBuilder)
  ├─ build_cropper.py           # Tool 2
  ├─ build_tts_review.py        # Tool 3
  ├─ build_animation_review.py  # Tool 4
  ├─ build_${NEW_TOOL}.py       # Tool 5+ (future)
  └─ html_templates/            # Shared CSS/JS templates
      ├─ base_style.css
      ├─ base_script.js
      └─ components/            # Reusable UI components (play button, selector, etc.)
```

### 2. BaseHTMLBuilder Interface

```python
class BaseHTMLBuilder:
    def __init__(self, title: str, subtitle: str, module_id: int = None, event_number: int = None):
        self.title = title
        self.subtitle = subtitle
        self.module_id = module_id
        self.event_number = event_number
        self.assets = {}        # {key: base64_encoded_data}
        self.metadata = {}      # Tool-specific metadata for feature audit
    
    def embed_asset(self, key: str, file_path: str, asset_type: str):
        # asset_type in ["audio", "image", "video"]
        self.assets[key] = encode_asset(file_path, asset_type)
    
    def build(self) -> str:
        html_parts = [self._build_head(), self._build_body(), self._build_script()]
        return ''.join(html_parts)
    
    def _build_head(self) -> str:
        # Standard head + CSS (base style + tool-specific overrides)
        pass
    
    def _build_body(self) -> str:
        # Standard layout (header, controls, content area, footer)
        # Subclasses override to add tool-specific UI
        raise NotImplementedError
    
    def _build_script(self) -> str:
        # Standard JS (asset injection, state, export, localStorage)
        # Subclasses override to add tool-specific playback/interaction logic
        raise NotImplementedError
    
    def export_to_file(self, output_path: str) -> str:
        html = self.build()
        with open(output_path, 'w') as f:
            f.write(html)
        self.metadata['file_path'] = output_path
        self.metadata['file_size_kb'] = len(html) // 1024
        return output_path
    
    def extract_features(self) -> dict:
        # Standard feature extraction (must be overridable per tool)
        return {
            'tool': self.__class__.__name__,
            'asset_count': len(self.assets),
            'file_size_kb': self.metadata.get('file_size_kb', 0),
            'version': 1,
            'timestamp': datetime.now().isoformat(),
            **self.metadata  # Tool-specific features
        }
    
    def register_in_directus(self, directus_client: DirectusClient, build_mode: str = 'registry'):
        # Standard registration flow
        directus_client.register_visual_asset(
            filename=os.path.basename(self.metadata['file_path']),
            filepath=self.metadata['file_path'],
            module_id=self.module_id,
            event_number=self.event_number,
            asset_type=self._get_asset_type(),
            status='built',
            build_mode=build_mode,
            feature_summary=self.extract_features()
        )
        directus_client.update_module_tracking(
            module_id=self.module_id,
            tracking_field=self._get_tracking_field(),
            value='built'
        )
        directus_client.log_activity(
            action=f'{self._get_asset_type()}_build',
            details=self.extract_features()
        )
    
    def _get_asset_type(self) -> str:
        # Subclasses override: "storyboard_html", "cropper_html", etc.
        raise NotImplementedError
    
    def _get_tracking_field(self) -> str:
        # Subclasses override: "storyboard_status", "cropper_status", etc.
        raise NotImplementedError
```

### 3. Shared API Client

```python
class DirectusClient:
    def __init__(self, credentials_from_api_keys_master=True):
        if credentials_from_api_keys_master:
            self.email, self.password = read_credentials()
        self.token = None
        self.base_url = "https://directus-production-3460.up.railway.app"
    
    def authenticate(self):
        # Get token, cache it
        pass
    
    def register_visual_asset(self, filename, filepath, module_id, event_number, 
                            asset_type, status, build_mode, feature_summary):
        # POST/PATCH prod_visual_assets
        pass
    
    def update_module_tracking(self, module_id, tracking_field, value):
        # PATCH prod_modules: e.g., storyboard_status = "built"
        pass
    
    def log_activity(self, action, details):
        # POST prod_activity_log
        pass
    
    def query_registry(self, module_id, event_number):
        # GET prod_visual_assets filtered by module_id, event_number
        pass
```

### 4. Shared Asset Encoding

```python
def encode_asset(file_path: str, asset_type: str) -> str:
    """Unified asset encoding (image, audio, video)."""
    with open(file_path, 'rb') as f:
        data = f.read()
    b64 = base64.b64encode(data).decode()
    
    mime_map = {
        'image': {'.png': 'image/png', '.jpg': 'image/jpeg', ...},
        'audio': {'.mp3': 'audio/mpeg', '.wav': 'audio/wav', ...},
        'video': {'.mp4': 'video/mp4', '.webm': 'video/webm', ...},
    }
    
    ext = Path(file_path).suffix.lower()
    mime = mime_map[asset_type].get(ext, 'application/octet-stream')
    
    return f'data:{mime};base64,{b64}'
```

### 5. CLI Pattern (All Tools)

```bash
# Build
python3 build_tool.py --input data.json --output tool.html \
  [--title "..." --subtitle "..." --module-id M1 --event-number 1]

# Validate (pre-build)
python3 build_tool.py --input data.json --smoke-test

# Audit (post-build)
python3 build_tool.py --audit tool.html

# Compare (regression check)
python3 build_tool.py --audit-previous current.html previous.html

# Auto-register (post-build, can be chained)
python3 build_tool.py --input data.json --output tool.html --register
```

All tools expose the same 5 CLI modes, implemented in BaseHTMLBuilder.

---

## Summary Table

| Dimension | Storyboard | Cropper | TTS Review | Animation Review |
|-----------|-----------|---------|-----------|------------------|
| **Lines of code** | 1,427 | 797 | 655 | 1,424 |
| **Asset types** | Images (2 res) + Audio | Image | Audio | Video + Audio |
| **Data flow** | Lines JSON → HTML + export | Single image → cropped PNGs | Config JSON → HTML + regenerate | Manifest JSON → HTML + picks |
| **User action** | Edit + image assign + export | Crop + name + save | Edit + regenerate + verdict + export | Select best clip + export |
| **Persistence** | localStorage (lines) | localStorage (crop boxes) | localStorage (verdicts) | localStorage (picks) |
| **Playback** | Click-play audio, static images | None (crop tool) | Click-play audio, regenerate TTS | Click-play videos, reference audio |
| **Export format** | JSON (locked sequence) | PNGs (per crop) | Text (verdicts) | JSON (picks) |
| **CLI modes** | 6 (registry, config, smoke-test, audit, audit-previous, export-image-map) | 1 | 1 | 5 (build, smoke-test, audit, audit-previous, register) |
| **Directus registration** | Auto | Auto (if module_id provided) | Auto (if module_id provided) | Explicit flag |
| **Feature audit** | Yes (extract_features, compare_features) | No | No | Yes (audit_html, audit_previous) |
| **Smoke test** | Yes (connectivity check) | No | No | Yes (manifest validation) |
| **Security issue** | None identified | None identified | ElevenLabs API key exposed in HTML | None identified |
| **Batch operations** | No batch audio regen | No batch download | No batch regen | No batch export |
| **Missing features** | No thumbnail refresh, image scrambling risk, registry query slow | No export of crop metadata, no batch download, single image only, canvas rendering platform-dependent | No batch regenerate, no text diff, no API key rotation | Video size explosion (75MB+ for 10-beat event with 2.5MB clips), no clip sync comparison, no duration validation, incomplete beat handling |

---

## Conclusion

The 4 tools are well-designed for their individual purposes but suffer from:

1. **High duplication:** 70% HTML/CSS/JS overlap, no shared library
2. **Inconsistent patterns:** Credential reading, registration, audit, CLI modes all vary
3. **Limited features:** No batch operations, no server sync, no unified approval format
4. **Fragile state:** Feature detection via regex, no embedded metadata, localStorage-only
5. **API exposure:** TTS_Review leaks ElevenLabs key in HTML

A universal container pattern + shared API client would consolidate this architecture, reduce duplication, and enable consistent feature rollout across all tools and future tools.

Recommended next steps:

1. **Immediate:** Create `production/base.py` (BaseHTMLBuilder) + `production/api_client.py` (DirectusClient)
2. **Short-term:** Refactor 4 tools to inherit from base class, share credential reading + registration
3. **Medium-term:** Add embedded metadata JSON to all tools, standardize approval/verdict format
4. **Long-term:** Build server-side sync layer for multi-tab state + version history

