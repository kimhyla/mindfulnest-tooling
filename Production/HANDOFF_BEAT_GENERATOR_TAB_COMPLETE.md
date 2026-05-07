# BEAT GENERATOR TAB — Complete Implementation Handoff (v3 — FINAL)

**Created:** 2026-04-23  
**Execution mode:** Claude Code terminal CLI ONLY (governed infrastructure — production_server.py is in scope)  
**Authorization:** All approvals pre-granted by Kim. No confirmation gates apply.  
**Self-contained:** Read top-to-bottom before any tool use. Do not skip sections.

---

## 0. WHAT YOU ARE BUILDING — FULL PICTURE

A three-tab extension of the existing MindfulNest storyboard HTML:

```
[ Storyboard ]  [ Beat Generator ]  [ Cropper ]
```

All three tabs share **one JS scope** and **one unified image library**. No port operation between tabs — they all read/write the same `IN{}`, `TH{}`, `L[]`, and gallery DOM.

### Beat Generator tab does exactly this — nothing more:
1. Kim selects an arc (1-10) + segment (event) from a parsed list
2. Claude extracts beats from the arc skeleton (speaker, dialogue, scene notes, emotion)
3. Kim can edit/delete/reorder beats
4. Kim hits "Generate Stills" → FLUX Kontext produces 3 still-image options per beat
5. Kim picks the best still per beat → crops to 4:3 in the Cropper tab
6. Kim hits "Accept All to Storyboard" → beats + chosen stills land in the Storyboard tab `L[]`

### What does NOT happen in the Beat Generator:
- **No Kling calls.** Kling animation happens later in the Storyboard tab ("send for animation" button — already built).
- **No lipsync.** Lipsync happens in the Storyboard tab ("send for lipsync" — already built).
- **No Kling motion prompts.** `build_motion_prompt()` runs in the Storyboard tab's animation pipeline when Kim hits "send for animation." The Beat Generator does not pre-generate or store motion prompts.
- **No audio.** Audio production is a separate pipeline.

### What the Storyboard tab already has (do not rebuild):
- "Send for animation" button per line → calls `build_motion_prompt(beat)` + Kling API
- "Send for lipsync" button per line → ByteDance LipSync API
- Both are already wired in `production_server.py`

---

## 1. THREE-TAB HTML ARCHITECTURE

### 1.1 HTML structure (Path A — use Python builder, never hand-write HTML)

The builder (`build_storyboard.py`) needs a new `--with-extras` flag that appends two new tab panels to the existing storyboard HTML:

```html
<!-- Tab buttons (added to existing tab bar) -->
<button class="tab-btn" data-tab="bg" onclick="_switchTab('bg')">Beat Generator</button>
<button class="tab-btn" data-tab="cr" onclick="_switchTab('cr')">Cropper</button>

<!-- Beat Generator panel (new) -->
<div id="panel-bg" class="tab-panel" hidden>
  <div id="bg-arc-selector">...</div>
  <div id="bg-segment-list">...</div>
  <div id="bg-beats-container">...</div>
  <button onclick="_bgGenerateAllStills()">Generate Stills (All)</button>
  <button onclick="_bgAcceptToStoryboard()">Accept All to Storyboard</button>
</div>

<!-- Cropper panel (new) -->
<div id="panel-cr" class="tab-panel" hidden>
  <canvas id="cr-canvas"></canvas>
  <div id="cr-sidebar">...</div>
  <button onclick="_crSaveCrop()">Save Crop</button>
</div>
```

### 1.2 Tab switching

```javascript
function _switchTab(tab) {
    document.querySelectorAll('.tab-panel').forEach(p => p.hidden = true);
    document.getElementById('panel-' + tab).hidden = false;
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelector('[data-tab="' + tab + '"]').classList.add('active');
    if (tab === 'bg') _bgLoadState();
    if (tab === 'cr') _crLoadLibrary();
}
```

### 1.3 Unified image library — the single rule

`IN{}` (filename map), `TH{}` (thumbnail map), and the gallery DOM all update together via ONE function. Called identically from all three tabs:

```javascript
function _injectImage(key, filename, thumb_b64, gallery_b64) {
    IN[key] = filename;
    TH[key] = thumb_b64;
    var existing = document.querySelector('.ic[data-key="' + key + '"]');
    if (existing) existing.remove();
    var card = document.createElement('div');
    card.className = 'ic';
    card.setAttribute('data-key', key);
    card.setAttribute('draggable', 'true');
    card.style.backgroundImage = 'url(' + gallery_b64 + ')';
    document.getElementById('gallery').appendChild(card);
    _reattachGalleryDragHandlers();
}
```

**Never update `IN`, `TH`, or gallery separately.** Always call `_injectImage()`.

### 1.4 Accepting beats to storyboard (shared scope = trivial)

```javascript
function _bgAcceptToStoryboard() {
    if (!BG_BEATS.length) return;
    BG_BEATS.forEach(function(beat) {
        L.push({
            speaker:   beat.speaker,
            text:      beat.dialogue_text,
            image:     beat.accepted_image_key || null,
            audio_key: null,
            pause:     0,
            section:   BG_SELECTED_SEGMENT ? BG_SELECTED_SEGMENT.name : 'Beat Generator'
        });
    });
    fetch('/api/bg/accept-beats', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ beats: BG_BEATS, segment: BG_SELECTED_SEGMENT })
    });
    render();
    _switchTab('sb');
}
```

No port operation. No rebuild. Shared scope means it's instant.

### 1.5 render() hook wrapper — mandatory pattern (Lesson L1)

Beat Generator's dynamic controls (FLUX option panels, edit handlers, reorder handles, delete buttons) must survive every `render()` call. Use a closure wrapper:

```javascript
var _bgBaseRender = function() { /* renders BG_BEATS list HTML */ };

var render = (function(prev) {
    return function() {
        prev();
        _bgInjectFluxOptionPanels();
        _bgInjectEditHandlers();
        _bgInjectReorderHandles();
        _bgInjectDeleteButtons();
        _bgInjectDragDropListeners();
    };
})(render);
```

Every time `render()` is called (by any tab), the Beat Generator controls are re-attached. This is the pattern that survived 9 production failures — do not deviate.

### 1.6 State variables

```javascript
var BG_BEATS = [];                // array of beat objects for current segment
var BG_SELECTED_SEGMENT = null;   // { arc_number, segment_index, name }
var BG_FLUX_TASK_MAP = {};        // { beat_id: [request_id_1, request_id_2, request_id_3] }
var BG_POLL_ACTIVE = false;       // true while polling loop is running
```

### 1.7 Drag-drop image assignment — POST before UI update (Lesson L3)

```javascript
function _bgHandleDrop(beatId, imageKey) {
    fetch('/api/bg/update-beat', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ beat_id: beatId, accepted_image_key: imageKey })
    }).then(function(r) {
        if (r.ok) _bgApplyImageToUI(beatId, imageKey);
    });
}
```

Server write first. UI update only on success.

---

## 2. SIDECAR STATE FILE

**Single file path:** `Production/beat_generator_state.json`  
**Keyed by arc + segment index** — arc switching never stomps other arcs' state.

```json
{
  "schema_version": 1,
  "active_context": { "arc_number": 1, "segment_index": 0 },
  "arcs": {
    "arc_1": {
      "segments": {
        "seg_0": {
          "name": "Event 1: Tessa's Fall",
          "beats": [
            {
              "beat_id":            "bg_arc1_seg0_beat_01",
              "speaker":            "Guide Bird",
              "dialogue_text":      "Are you OK...? What's wrong?",
              "scene_notes":        "Guide Bird and child find Tessa crying on a rock",
              "emotion":            "neutral",
              "accepted_image_key": null,
              "flux_options":       [],
              "status":             "draft",
              "schema_version":     1
            }
          ]
        }
      }
    }
  },
  "_last_updated": "2026-04-23T00:00:00Z"
}
```

**Fields on each beat — exactly these, nothing more:**

| Field | Type | Notes |
|-------|------|-------|
| `beat_id` | string | `bg_arc{N}_seg{I}_beat_{NN}` |
| `speaker` | string | Canonical name (Chipper, Tessa, etc.) |
| `dialogue_text` | string | Verbatim from skeleton — never paraphrase |
| `scene_notes` | string | Brief scene context for FLUX prompt |
| `emotion` | string | `happy_excited` / `upset_shocked` / `sad_disappointed` / `neutral` |
| `accepted_image_key` | string or null | Key in shared `IN{}` of chosen still |
| `flux_options` | array | `[{ request_id, image_url, local_path }]` — up to 3 |
| `status` | string | `draft` / `stills_pending` / `still_chosen` / `accepted` |

**No `kling_prompt` field.** Motion prompts are generated on-demand by `build_motion_prompt()` in the Storyboard tab's animation pipeline — not pre-stored here.

**Atomic writes (Lesson L6):**
```python
import tempfile, os, json

def _write_sidecar(data, path='Production/beat_generator_state.json'):
    with tempfile.NamedTemporaryFile('w', dir=os.path.dirname(os.path.abspath(path)),
                                     delete=False, suffix='.tmp') as f:
        json.dump(data, f, indent=2)
        tmp = f.name
    os.replace(tmp, os.path.abspath(path))
```

**Thread safety:** All sidecar read-modify-write operations wrapped in `threading.RLock()` — poll callbacks and user-action routes run concurrently.

---

## 3. BEAT EXTRACTION FROM ARC SKELETON

### 3.1 Arc skeleton file paths

```
Arc Skeletons/ARC_01_SKELETON_FINAL.md   (Arc 1)
Arc Skeletons/ARC_02_SKELETON_FINAL.md   (Arc 2)
...
Arc Skeletons/ARC_10_SKELETON_FINAL.md   (Arc 10)
```

Always parse the `.md` file (not `.docx`). The `.md` is the machine-readable version.

### 3.2 Overall document structure (Arc 1 — representative)

```
## ARC SUMMARY
### Module Structure Table
...

## EVENT 0: OPENING VIDEO SEQUENCE (Narrative Event — Video Scene)
### THE SCENE
[dialogue + stage directions]

## EVENT 0a: AVATAR CREATION (Interactive — no video production)

## EVENT 0b: GUIDE BIRD INTRODUCTION (Narrative Event — Video Scene)
### THE SCENE
[dialogue + stage directions]

## EVENT 1: TESSA'S FALL (M1)
### Narrative Setup
[dialogue + stage directions]
### Therapeutic Note — ...
[clinical notes — skip entirely]
**► INSERT MODULE M1 ◄ ...**    ← module boundary: stop extraction here
### Resolution
[dialogue + stage directions — resume extraction here]
### Tomorrow Hook
### Post-M1: Return to Map

## EVENT 2: LUNA'S DISCOVERY (M2)
...
```

### 3.3 Segment list endpoint — `GET /api/bg/segments?arc_number=N`

Used to populate the segment picker in the UI. Parses the skeleton and returns event names + indices:

```python
EVENT_HEADER = re.compile(
    r'^## (EVENT [^\n]+?)(?:\s*\(([^)]+)\))?$',
    re.MULTILINE
)

SKIP_TYPES = {'Interactive', 'no video', 'Avatar Creation', 'MAP', 'no video production'}

def get_segments(arc_number):
    path = f'Arc Skeletons/ARC_{arc_number:02d}_SKELETON_FINAL.md'
    with open(path, encoding='utf-8') as f:
        text = f.read()

    segments = []
    matches = list(EVENT_HEADER.finditer(text))
    lines   = text.splitlines()

    for i, m in enumerate(matches):
        event_type = (m.group(2) or '').strip()
        if any(skip in event_type for skip in SKIP_TYPES):
            continue

        start = text[:m.start()].count('\n')
        end   = text[:matches[i+1].start()].count('\n') if i + 1 < len(matches) else len(lines)

        segments.append({
            'segment_index': len(segments),
            'name':          m.group(1).strip(),
            'event_type':    event_type,
            'start_line':    start,
            'end_line':      end
        })

    return segments
```

### 3.4 Beat extraction — `POST /api/bg/extract-beats`

Body: `{ arc_number, segment_index }`

```python
DIALOGUE_LINE   = re.compile(r'^>\s*\*?([A-Za-z ]+?)\*?:\s*"(.*)"')
SPEAKER_LINE    = re.compile(r'^(?:\*\*)?([A-Z][A-Za-z ]+?):\s*["\(]')
STAGE_DIR       = re.compile(r'^\*[\[\(]|^\*\[')
CAMERA_CUT      = re.compile(r'camera\s+(cuts?|pans?|changes?|zooms?|shifts?)', re.I)
MODULE_MARKER   = re.compile(r'\*\*►\s*INSERT MODULE')
WIN_MARKER      = re.compile(r'^\*\*Win\b|^\*\*Win\s*—')
TOMORROW_HOOK   = re.compile(r'^###\s*Tomorrow Hook')
POST_MODULE     = re.compile(r'^###\s*Post-M\d|^###\s*Post-Oliver')
SKIP_SECTION    = re.compile(r'^###\s*Therapeutic Note|^\*\*Technique-First Match')
DATA_BLOCK      = re.compile(r'^\*\*\[DATA:')

def extract_beats(segment_raw_text):
    lines = segment_raw_text.splitlines()
    beats = []
    speaker  = 'Narrator'
    dialogue = []
    notes    = []
    in_scene = False   # True inside Narrative Setup or THE SCENE
    in_res   = False   # True inside Resolution
    skip_sec = False   # True inside Therapeutic Note (skip entirely)

    for line in lines:
        # ── Section boundary detection ──────────────────────────────────────
        if re.search(r'^###\s*(Narrative Setup|THE SCENE)', line):
            in_scene = True;  in_res = False;  skip_sec = False;  continue
        if re.search(r'^###\s*Resolution', line):
            in_res = True;    in_scene = False; skip_sec = False;  continue
        if SKIP_SECTION.search(line):
            skip_sec = True;  continue
        if re.search(r'^###\s', line):  # any other ### = end of extraction zone
            if dialogue: beats.append(_flush(speaker, dialogue, notes))
            dialogue = []; notes = []
            in_scene = False; in_res = False; skip_sec = False; continue
        if (MODULE_MARKER.search(line) or WIN_MARKER.search(line) or
                TOMORROW_HOOK.search(line) or POST_MODULE.search(line)):
            if dialogue: beats.append(_flush(speaker, dialogue, notes))
            dialogue = []; notes = []
            in_scene = False; in_res = False; continue
        if DATA_BLOCK.search(line) or skip_sec:
            continue
        if not (in_scene or in_res):
            continue

        # ── Dialogue: "> Character: "text"" format ──────────────────────────
        dm = DIALOGUE_LINE.match(line)
        if dm:
            spk, txt = dm.group(1).strip(), dm.group(2).strip()
            spk = _canon(spk)
            if spk != speaker and dialogue:
                beats.append(_flush(speaker, dialogue, notes))
                dialogue = []; notes = []
            speaker = spk
            dialogue.append(txt)
            continue

        # ── Dialogue: "Character: "text"" format (no >) ─────────────────────
        sm = SPEAKER_LINE.match(line)
        if sm:
            spk = _canon(sm.group(1).strip())
            rest = line.split(':', 1)[1].strip().strip('"()')
            if spk != speaker and dialogue:
                beats.append(_flush(speaker, dialogue, notes))
                dialogue = []; notes = []
            speaker = spk
            if rest: dialogue.append(rest)
            continue

        # ── Stage direction ──────────────────────────────────────────────────
        if STAGE_DIR.match(line) or line.startswith('*('):
            if CAMERA_CUT.search(line) and dialogue:
                beats.append(_flush(speaker, dialogue, notes))
                dialogue = []; notes = []
            notes.append(line.strip('*[]() \t'))
            continue

        # ── Plain prose (scene description) ─────────────────────────────────
        stripped = line.strip()
        if stripped and not stripped.startswith('#'):
            notes.append(stripped)

    if dialogue:
        beats.append(_flush(speaker, dialogue, notes))

    return beats


def _flush(speaker, dialogue, notes):
    text = ' '.join(dialogue)
    ctx  = ' '.join(notes[-3:]) if notes else ''
    return {
        'speaker':       speaker,
        'dialogue_text': text,
        'scene_notes':   ctx,
        'emotion':       _infer_emotion(dialogue, notes)
    }


def _canon(name):
    """Canonicalize legacy speaker names."""
    ALIAS = {
        'guide bird': 'Chipper',
        'pip':        'Chipper',
        'chipper':    'Chipper',
        'myrrhin':    'Cedric',
    }
    return ALIAS.get(name.lower().strip(), name)
```

### 3.5 Emotion inference (suggestion only — Kim can override in UI)

```python
SIGNALS = {
    'happy_excited':    ['!!', 'grin', 'smile', 'amazing', 'HUGE', 'Wow', 'WOW',
                         'exciting', 'sputtering', 'Oh this is the most', 'incredible'],
    'upset_shocked':    ['What?!', 'WHAT!', 'shocked', 'WE DO NOT', 'Are you serious',
                         'bristle', 'startled', 'OH FOR'],
    'sad_disappointed': ['crying', 'cry', 'tears', 'sniff', 'sob', 'hurt',
                         'deflated', 'I should have', 'droop', 'losing']
}

def _infer_emotion(dialogue, notes):
    combined = ' '.join(dialogue + notes)
    for emotion, signals in SIGNALS.items():
        if any(s in combined for s in signals):
            return emotion
    return 'neutral'
```

### 3.6 Source fidelity — Kim's dialogue verbatim (Rule 11)

`dialogue_text` is copied character-for-character from the skeleton. Never paraphrase. Never summarize. `scene_notes` is context metadata and can be trimmed — `dialogue_text` never can.

---

## 4. FLUX KONTEXT — STILL IMAGE GENERATION

This is the only external API the Beat Generator calls. Generates 3 still-image options per beat.

**API endpoint:** `POST https://api.bfl.ai/v1/flux-kontext-pro`  
**Auth header:** `x-key: {api_key}` (read from `Production/API_KEYS_MASTER.md` at runtime)  
**Cost:** ~$0.08 per image · 3 options = **$0.24 per beat** · 8-beat event = **~$1.92 total**  
**Typical generation time:** 10–15 seconds per image (parallel poll: ~45-60s for full event batch)

### 4.1 When to use which approach

| Situation | Approach |
|-----------|----------|
| Character reference image exists in library | FLUX Kontext with `input_image` — edits reference to match emotion/pose |
| No reference image available | FLUX Kontext without `input_image` — text-to-image from prompt alone |

Character reference images live in `Production/Character_Assets/` (one master per creature). Always prefer the reference-image path for character consistency.

### 4.2 Submit one FLUX Kontext call

```python
import http.client, ssl, json, base64

def submit_flux_kontext(prompt, reference_image_path=None):
    """
    Submit one FLUX Kontext generation.
    Returns request_id string for polling.
    Uses fresh SSL connection per call (same pattern as Kling, per LD-137).
    """
    api_key = _load_api_key('bfl')

    payload = {"prompt": prompt, "output_format": "png"}
    if reference_image_path and os.path.exists(reference_image_path):
        with open(reference_image_path, 'rb') as f:
            payload["input_image"] = base64.b64encode(f.read()).decode()

    ctx = ssl.create_default_context()
    ctx.options |= ssl.OP_NO_TICKET
    conn = http.client.HTTPSConnection("api.bfl.ai", context=ctx, timeout=30)
    conn.request(
        "POST", "/v1/flux-kontext-pro",
        body=json.dumps(payload),
        headers={"x-key": api_key, "Content-Type": "application/json"}
    )
    resp = conn.getresponse()
    data = json.loads(resp.read())
    conn.close()
    return data["id"]


def poll_flux(request_id, max_attempts=24, interval=5):
    """
    Poll for completion. 24 × 5s = 2 min max. Typical: 10-15s.
    Returns image URL on success, raises on failure.
    """
    api_key = _load_api_key('bfl')
    for _ in range(max_attempts):
        ctx = ssl.create_default_context()
        ctx.options |= ssl.OP_NO_TICKET
        conn = http.client.HTTPSConnection("api.bfl.ai", context=ctx, timeout=30)
        conn.request("GET", f"/v1/get_result?id={request_id}",
                     headers={"x-key": api_key})
        resp = conn.getresponse()
        data = json.loads(resp.read())
        conn.close()
        if data.get("status") == "Ready":
            return data["result"]["sample"]  # image URL
        if data.get("status") in ("Error", "Failed"):
            raise RuntimeError(f"FLUX failed: {data}")
        import time; time.sleep(interval)
    return None
```

### 4.3 FLUX still prompt — what it describes

The FLUX prompt describes the **visual composition of the still** — character pose, expression, scene context, framing, style. This is completely different from a Kling motion prompt (which describes animation movement and is generated later in the Storyboard tab).

```python
EMOTION_VISUAL = {
    'happy_excited':    'expression joyful and bright, eyes wide with delight, body open',
    'upset_shocked':    'expression startled and wide-eyed, body tensed, alert posture',
    'sad_disappointed': 'expression soft and downcast, body language gentle and subdued',
    'neutral':          'expression calm and attentive, natural resting pose'
}

SPECIES_DESC = {
    'Tessa':   'young female turtle with green patterned shell, warm expressive eyes',
    'Luna':    'scholarly female owl with large bright eyes, rumpled academic feathers',
    'Benson':  'small timid male bunny with large ears, gentle wide eyes',
    'Ember':   'young female fox with warm reddish-orange fur, curious alert face',
    'Bork':    'tiny dignified firefly with formal posture, faint bioluminescent glow',
    'Bramble': 'large warm male bear with grounded steady presence, kind eyes',
    'Chipper': 'small colorful bird with bright intelligent eyes, expressive wings',
    'Cedric':  'elderly wise wizard in long robes, long white beard, gentle demeanor',
    'Narrator': 'sweeping magical Everdale landscape'
}

def build_flux_still_prompt(beat, option_variation=0):
    """
    Build a FLUX Kontext prompt for a storyboard still.
    option_variation: 0 (base), 1 (slight pose shift), 2 (lighting variant)
    """
    speaker  = beat.get('speaker', 'Narrator')
    emotion  = beat.get('emotion', 'neutral')
    notes    = beat.get('scene_notes', '')

    species  = SPECIES_DESC.get(speaker, speaker + ' character')
    emo_desc = EMOTION_VISUAL.get(emotion, 'expression calm and attentive')

    variation_suffix = [
        '',
        ' Slight variation in head angle and pose.',
        ' Slightly warmer lighting emphasis, same composition.'
    ][option_variation]

    scene_ctx = notes[:120] if notes else 'Everdale forest clearing, warm golden light, magical atmosphere'

    return (
        f"Same {species}, {emo_desc}. "
        f"Scene context: {scene_ctx}. "
        f"Pixar 3D animated style, warm soft lighting, expressive character design, "
        f"medium shot, character centered in frame, cinematic quality. "
        f"No text, no UI elements, no watermarks."
        f"{variation_suffix}"
    )
```

### 4.4 Generate 3 options per beat

```python
CREATURE_REFS = {
    'Tessa':   'Production/Character_Assets/tessa_reference_master.png',
    'Luna':    'Production/Character_Assets/luna_reference_master.png',
    'Benson':  'Production/Character_Assets/benson_reference_master.png',
    'Ember':   'Production/Character_Assets/ember_reference_master.png',
    'Bork':    'Production/Character_Assets/bork_reference_master.png',
    'Bramble': 'Production/Character_Assets/bramble_reference_master.png',
    'Chipper': 'Production/Character_Assets/chipper_reference_master.png',
    'Cedric':  'Production/Character_Assets/cedric_reference_master.png',
}

def submit_beat_stills(beat):
    """Submit 3 FLUX calls for one beat. Returns list of 3 request_ids."""
    ref = CREATURE_REFS.get(beat['speaker'])  # None if no reference exists
    request_ids = []
    for i in range(3):
        prompt = build_flux_still_prompt(beat, option_variation=i)
        rid = submit_flux_kontext(prompt, reference_image_path=ref)
        request_ids.append(rid)
        import time; time.sleep(0.3)
    return request_ids
```

### 4.5 Burst submit all beats, poll in parallel

```python
import concurrent.futures, threading

_sidecar_lock = threading.RLock()

def submit_all_beats_flux(beats):
    """Burst-submit 3×N calls, return task_map. Typical: ~3s for 8 beats."""
    task_map = {}
    for beat in beats:
        request_ids = submit_beat_stills(beat)
        task_map[beat['beat_id']] = request_ids
    return task_map

def poll_all_parallel(task_map):
    """Poll all requests in parallel. Returns { request_id: image_url_or_None }."""
    all_ids = [rid for rids in task_map.values() for rid in rids]
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        futures = {pool.submit(poll_flux, rid): rid for rid in all_ids}
        for f in concurrent.futures.as_completed(futures):
            rid = futures[f]
            try:
                results[rid] = f.result()
            except Exception as e:
                results[rid] = None
                print(f"[WARN] FLUX {rid} failed: {e}")
    return results
```

### 4.6 Download and inject completed image

```python
import urllib.request

def download_and_inject_still(request_id, image_url, beat_id, option_idx, sidecar):
    """Download image, save to disk, return key + b64 for _injectImage call."""
    filename   = f"bg_{beat_id}_opt{option_idx}.png"
    local_path = f"Production/beat_generator_stills/{filename}"
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    urllib.request.urlretrieve(image_url, local_path)

    # Generate thumbnail
    from PIL import Image
    import io
    img = Image.open(local_path)
    img.thumbnail((256, 192))
    tbuf = io.BytesIO()
    img.save(tbuf, 'PNG')
    thumb_b64 = 'data:image/png;base64,' + base64.b64encode(tbuf.getvalue()).decode()

    with open(local_path, 'rb') as f:
        gallery_b64 = 'data:image/png;base64,' + base64.b64encode(f.read()).decode()

    key = f"bg_{beat_id}_opt{option_idx}"

    # Update sidecar
    with _sidecar_lock:
        for arc_beats in _find_beat(sidecar, beat_id):
            arc_beats['flux_options'].append({
                'request_id': request_id,
                'image_url':  image_url,
                'local_path': local_path,
                'key':        key
            })
        _write_sidecar(sidecar)

    return {'key': key, 'filename': filename, 'thumb_b64': thumb_b64, 'gallery_b64': gallery_b64}
```

---

## 5. CROPPER TAB

### 5.1 Crop ratio: 4:3

All stills crop to 4:3. This matches the storyboard panel format and is the correct input aspect ratio for Kling animation (run later in the Storyboard tab).

### 5.2 Cropper workflow

1. Kim sees 3 FLUX option thumbnails on a beat card
2. Clicks "Crop" on any option → `_switchTab('cr')` with that image pre-loaded onto the canvas
3. Canvas shows the image with a draggable 4:3 crop box
4. Kim repositions to frame the character correctly
5. "Save Crop" → `_crSaveCrop()`:
   - `canvas.toBlob(...)` exports crop PNG
   - `POST /api/cr/save-crop` with blob + `{ beat_id, source_key }`
   - Server applies Rule 6 upscale + WebP conversion
   - Server does Directus Two-Write
   - Returns `{ key, filename, thumb_b64, gallery_b64 }`
   - Client: `_injectImage(key, filename, thumb_b64, gallery_b64)` — appears in gallery + all beat image slots
   - Beat's `accepted_image_key` set to new crop key

### 5.3 Delivery format (Rule 6 + Rule 6.2)

```python
from PIL import Image
import io, base64

def process_crop(crop_bytes):
    """Apply Rule 6 + 6.2 and return delivery WebP + thumbnail PNG."""
    img = Image.open(io.BytesIO(crop_bytes))
    w, h = img.size

    # Rule 6: shortest side ≥ 600px
    if min(w, h) < 600:
        scale = 600 / min(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    # Rule 6.2: delivery = WebP q80, long-edge ≤ 1280
    w, h = img.size
    if max(w, h) > 1280:
        scale = 1280 / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, 'WEBP', quality=80)
    delivery = buf.getvalue()

    # Thumbnail: 256×192 (4:3)
    thumb = img.copy()
    thumb.thumbnail((256, 192), Image.LANCZOS)
    tbuf = io.BytesIO()
    thumb.save(tbuf, 'PNG')
    thumb_b64    = 'data:image/png;base64,'  + base64.b64encode(tbuf.getvalue()).decode()
    gallery_b64  = 'data:image/webp;base64,' + base64.b64encode(delivery).decode()

    return delivery, thumb_b64, gallery_b64
```

### 5.4 Directus Two-Write Rule (mandatory for every saved crop)

```python
# Write 1 — prod_visual_assets
{
    "filename":        delivery_filename,
    "filepath":        delivery_path,
    "role":            "delivery",
    "asset_type":      "crop_4x3",
    "status":          "approved",
    "aspect_ratio":    "4:3",
    "width":           delivery_w,
    "height":          delivery_h,
    "file_size_bytes": len(delivery_bytes)
}

# Write 2 — prod_activity_log
{
    "action":    "crop_saved",
    "component": "beat_generator_cropper",
    "details":   { "key": key, "filename": delivery_filename, "beat_id": beat_id }
}
```

Use `urllib.request` (never curl). On Directus write failure: retry once, then append to `pending_directus_writes.json`.

---

## 6. SERVER ROUTES — COMPLETE LIST

Add all of these to `Production/tools/production_server.py`:

```
# ── Arc skeleton ────────────────────────────────────────────────────────────
GET  /api/bg/segments?arc_number=N
     → { segments: [{ segment_index, name, event_type }] }
     Parses ARC_0N_SKELETON_FINAL.md. Zero API cost.

# ── Session state ───────────────────────────────────────────────────────────
GET  /api/bg/session-state
     → { active_context, beats: [...], flux_options_complete: bool }
     Loads sidecar. Called when Beat Generator tab opens.

# ── Beat management ─────────────────────────────────────────────────────────
POST /api/bg/extract-beats
     Body: { arc_number, segment_index }
     → { beats: [...] }
     Parses skeleton, writes fresh beats to sidecar for this arc+segment.
     Overwrites existing beats for that segment (intentional refresh).

POST /api/bg/update-beat
     Body: { beat_id, [accepted_image_key], [emotion], [dialogue_text], [scene_notes] }
     → { ok: true }
     Partial update — only provided fields are changed in sidecar.

POST /api/bg/reorder-beats
     Body: { beat_ids: ["id1","id2",...] }   (ordered array = new order)
     → { ok: true }

DELETE /api/bg/delete-beat
     Body: { beat_id }
     → { ok: true }

POST /api/bg/accept-beats
     Body: { beats, segment }
     → { ok: true }
     Marks all beats as accepted in sidecar. Client already pushed to L[].

# ── FLUX still generation ────────────────────────────────────────────────────
POST /api/bg/submit-flux-batch
     Body: { beat_ids: ["id1","id2",...] }   (subset or all beats)
     → { task_map: { beat_id: [request_id, request_id, request_id] } }
     Burst-submits 3×N FLUX calls. Returns immediately.

GET  /api/bg/poll-flux-status
     Query: ?request_ids=id1,id2,id3,...
     → { id1: { status, url, key, thumb_b64, gallery_b64 } | null }
     Server polls BFL for any pending request_ids. Downloads + processes completed ones.
     Returns null for still-pending. Client calls this every 5s.

POST /api/bg/accept-option
     Body: { beat_id, option_key }
     → { ok: true }
     Sets beat.accepted_image_key in sidecar.

# ── Cropper ──────────────────────────────────────────────────────────────────
POST /api/cr/save-crop
     Body: multipart { crop_png: <blob>, beat_id: str, source_key: str }
     → { key, filename, thumb_b64, gallery_b64 }
     Applies Rule 6+6.2, writes WebP to disk, Directus Two-Write, returns inject data.

GET  /api/cr/library
     → { images: [{ key, filename, thumb_b64, gallery_b64 }] }
     Returns all saved crops (for sidebar on Cropper tab open).
```

---

## 7. BUTTON-BY-BUTTON STEP-BY-STEP

### Arc + Segment selector (loads on Beat Generator tab open)

1. `_bgLoadState()` calls `GET /api/bg/session-state` — restores last arc/segment + beats
2. Arc buttons (1-10) shown; clicking one calls `GET /api/bg/segments?arc_number=N`
3. Segment list rendered — Kim clicks a segment
4. If sidecar has existing beats for this arc+segment → display them immediately (no re-extract)
5. "Re-extract Beats" button available if Kim wants a fresh parse

---

### "Extract Beats" / "Re-extract Beats" button

1. `POST /api/bg/extract-beats` with `{ arc_number, segment_index }`
2. Server: reads skeleton `.md` → calls `get_segments()` → slices raw text → calls `extract_beats()`
3. Server: writes fresh beats array to sidecar for this arc+segment (atomic write)
4. Server: returns `{ beats }` array
5. Browser: renders beat cards — each card shows:
   - **Speaker** (editable dropdown: all 7 creatures + Narrator + Cedric)
   - **Dialogue** (read-only, verbatim)
   - **Scene notes** (read-only, truncated)
   - **Emotion** (editable dropdown: happy_excited / upset_shocked / sad_disappointed / neutral)
   - **3 image slots** (empty, labelled Option 1 / 2 / 3)
   - **"Generate Stills"** button (this beat only)
   - **"Delete"** button
   - **Drag handle** (reorder)

---

### "Generate Stills" button (per beat OR "Generate All Stills" for whole segment)

1. Browser: `POST /api/bg/submit-flux-batch` with `{ beat_ids }`
2. Server: calls `submit_all_beats_flux(beats)` — burst-submits 3×N FLUX calls (~0.3s each)
3. Server: saves `task_map` to sidecar; updates beat status to `stills_pending`
4. Server: returns `{ task_map }` immediately
5. Browser: saves `BG_FLUX_TASK_MAP`, sets `BG_POLL_ACTIVE = true`, starts poll loop
6. **Poll loop (every 5s):**
   - `GET /api/bg/poll-flux-status?request_ids=id1,id2,...`
   - Server polls BFL, downloads + processes any newly completed images
   - Returns per-request: `{ status:'ready', key, thumb_b64, gallery_b64 }` or `null`
   - Browser: for each newly-ready result → calls `_injectImage(key, ...)` → thumbnail appears in beat card option slot
7. Loop ends when all request_ids return ready (or after 2-minute timeout per request)
8. Total wall time for 8-beat event: **~45-60 seconds**

---

### "Crop" button (on any FLUX option thumbnail)

1. Client stores source image data URI from `_injectImage` call
2. `_switchTab('cr')` — Cropper tab opens with that image pre-loaded on canvas
3. Canvas shows image + draggable 4:3 crop box (starts centered)
4. Kim drags/resizes crop box
5. "Save Crop" → `_crSaveCrop()`:
   - `canvas.toBlob(blob => { POST /api/cr/save-crop })` with beat_id + source_key
   - Server: `process_crop(blob)` → Rule 6 upscale → WebP conversion
   - Server: writes to `Production/beat_generator_stills/crops/` (atomic)
   - Server: Directus Two-Write (asset row + activity log row)
   - Server: returns `{ key, filename, thumb_b64, gallery_b64 }`
   - Client: `_injectImage(key, filename, thumb_b64, gallery_b64)` — crop in gallery
   - Client: `POST /api/bg/accept-option` `{ beat_id, option_key: key }` → persists choice
   - Client: beat card shows chosen crop thumbnail, status → `still_chosen`
   - Client: `_switchTab('bg')` — returns to Beat Generator

---

### "Accept All to Storyboard" button

1. Validation: warn if any beats have no `accepted_image_key` (Kim can override)
2. Calls `_bgAcceptToStoryboard()`:
   ```javascript
   BG_BEATS.forEach(beat => {
       L.push({
           speaker:   beat.speaker,
           text:      beat.dialogue_text,
           image:     beat.accepted_image_key || null,
           audio_key: null,
           pause:     0,
           section:   BG_SELECTED_SEGMENT.name
       });
   });
   ```
3. `POST /api/bg/accept-beats` (marks beats as accepted in sidecar)
4. `render()` — storyboard re-renders with new beats
5. `_switchTab('sb')` — Kim lands in Storyboard tab seeing the new beats with panel images assigned
6. From here, Kim uses the existing "send for animation" / "send for lipsync" buttons — nothing new needed

---

## 8. BUILD ORDER FOR CLI TERMINAL

```bash
# ── Pre-flight ────────────────────────────────────────────────────────────────
# 1. Confirm motion vocabulary exists (already implemented, LD-307)
grep -n "SPEAKER_MOTION_PROFILES" Production/tools/production_server.py

# 2. Smoke test — confirms Directus auth + schema before touching anything
python3 Production/tools/build_storyboard.py --smoke-test

# ── Build ─────────────────────────────────────────────────────────────────────
# 3. Add --with-extras flag to build_storyboard.py (Path A: Python builder only)
#    Emits Beat Generator tab panel + Cropper tab panel HTML

# 4. Add all routes from §6 to production_server.py
#    Implement extract-beats, submit-flux-batch, poll-flux-status, save-crop, etc.

# 5. Build the three-tab storyboard HTML
python3 Production/tools/build_storyboard.py \
    --registry --module M1 --event 1 \
    --with-extras \
    --output Production/Event_1/storyboard_with_bg_v1.html

# 6. Audit — confirm no regressions from prior version
python3 Production/tools/build_storyboard.py \
    --audit Production/Event_1/storyboard_with_bg_v1.html
python3 Production/tools/build_storyboard.py \
    --audit-previous Production/Event_1/storyboard_v22.html   # latest existing version

# ── Start server and test (zero API cost) ────────────────────────────────────
# 7. Start production server
python3 Production/tools/production_server.py &

# 8. Test segment listing
curl "http://localhost:5000/api/bg/segments?arc_number=1"
# Expected: list of events with names like "EVENT 1: TESSA'S FALL"

# 9. Test beat extraction
curl -X POST http://localhost:5000/api/bg/extract-beats \
     -H "Content-Type: application/json" \
     -d '{"arc_number":1,"segment_index":0}'
# Expected: ≥4 beats, Guide Bird/Pip canonicalized to Chipper, emotions inferred

# 10. Test session state rehydration
curl http://localhost:5000/api/bg/session-state
# Expected: same beats from sidecar, active_context set

# ── One real API call to confirm FLUX path (~$0.08) ──────────────────────────
# 11. Submit ONE FLUX call for beat_01 option 0 only
#     (Just verify task_map returned with a valid request_id — no need to poll to completion)
curl -X POST http://localhost:5000/api/bg/submit-flux-batch \
     -H "Content-Type: application/json" \
     -d '{"beat_ids":["bg_arc1_seg0_beat_01"]}'
# Expected: { task_map: { "bg_arc1_seg0_beat_01": ["<id>","<id>","<id>"] } }
# (3 request_ids returned = API path confirmed working)
```

**Stop after step 11.** Do not poll to completion or download during the build session. The route is confirmed by receiving valid request_ids.

---

## 9. COST SUMMARY

| Operation | API | Cost per beat | 8-beat event |
|-----------|-----|--------------|--------------|
| Segment listing | none | $0 | $0 |
| Beat extraction | none | $0 | $0 |
| FLUX stills (3 options) | BFL | $0.24 | $1.92 |
| Crop processing | none | $0 | $0 |
| Directus writes | own instance | $0 | $0 |
| **Beat Generator total** | | **$0.24** | **~$1.92** |

Kling animation and lipsync costs occur later, in the Storyboard tab's existing pipeline.

---

## 10. AUTONOMOUS CLI TERMINAL PROMPT

Use this verbatim:

```
Read completely: Production/HANDOFF_BEAT_GENERATOR_TAB_COMPLETE.md

SKILLS TO LOAD (in order):
1. zero-error-qa — Phase 0 MANDATORY. This is ARCHITECTURAL work
   (new routes on production_server.py + new builder mode).
   Classify ARCHITECTURAL. Spawn 4+4 agents. Write prod_preflight_reviews
   row BEFORE any code changes.
2. no-shortcuts — no TODOs, no placeholders, no "wire up later"
3. dashboard-gate — run full 7-query session-start protocol

BUDGET: Max $1 in real API costs this session.
The only permitted real API call is ONE test of submit-flux-batch
(step 11 in §8 build order) to confirm the BFL path works — ~$0.24.
No polling to completion. No downloading images. No Kling. No lipsync.

BUILD SCOPE — implement exactly §1-§7 of the handoff:
Phase 1: Add --with-extras flag to build_storyboard.py (Path A — Python builder only, no direct HTML editing)
Phase 2: Add all routes from §6 to production_server.py
Phase 3: Implement extract_beats() parser per §3 (including _canon, _infer_emotion)
Phase 4: Implement FLUX Kontext submit + poll per §4 (fresh SSL, parallel poll)
Phase 5: Implement save-crop per §5 (Rule 6 upscale, WebP, Directus Two-Write)
Phase 6: Run build order §8 steps 1-10 (zero API cost verification)
Phase 7: Run step 11 (one real FLUX submit, ~$0.24, confirm request_ids returned)

EXPLICIT NON-SCOPE this session:
- No Kling video calls
- No ByteDance lipsync
- No polling FLUX calls to completion during build
- No .docx file edits
- Do not re-implement build_motion_prompt or SPEAKER_MOTION_PROFILES
  (already in production_server.py, LD-307)

DONE CRITERIA:
- All §8 curl tests pass
- Beat extraction for Arc 1 Event 1 returns ≥4 beats with Chipper (not "Guide Bird")
- FLUX submit returns 3 valid request_ids
- --audit-previous shows zero regressions vs prior storyboard
- prod_preflight_reviews row written
- prod_activity_log rows written (one per phase)
- prod_locked_decisions rows written for any new architectural decisions
- HANDOFF_BEAT_GENERATOR_BUILD_OUTCOME.md written with: what was built,
  what tests passed, CLI commands to verify, exact next-session starting point

Do not stop on ambiguity — spawn 5+5 agents and converge.
All file writes pre-authorized. No Kim-confirmation gate (no .docx touched).
```

---

## 11. KEY LESSONS APPLIED

| Lesson | Source | Applied where |
|--------|--------|---------------|
| L1: render() hook wrapper | Prior session spec v3.0 | FLUX option panels re-attach on every render() |
| L2: 3-way image sync | Prior session spec v3.0 | `_injectImage()` — single function, all tabs |
| L3: drag-drop → POST before UI | Prior session spec v3.0 | `_bgHandleDrop()` |
| L4: arc-switch state isolation | Prior session spec v3.0 | Sidecar keyed `arc_N / seg_I` |
| L5: fresh SSL per API call | LD-137 | `http.client` + `ssl.OP_NO_TICKET` per FLUX call |
| L6: atomic sidecar writes | LD-134 | `.tmp` → `os.replace()` |
| L7: burst submit + parallel poll | Prior session spec v3.0 | `submit_all_beats_flux()` + `poll_all_parallel()` |
| L8: Path A/B protocol | CLAUDE.md Rule 7 | `--with-extras` added to builder; never direct HTML |
| L9: export-first rebuild | April 13 incident | Kim exports JSON before any storyboard rebuild |
| L10: `--audit-previous` after rebuild | CLAUDE.md Rule 7 | Mandatory after build step 5 |
| L11: Two-Write Rule | Registration Compliance Gate | Every crop → asset + activity log |
| L12: `threading.RLock()` on sidecar | Prior session spec v3.0 | All sidecar R/M/W |
| L13: No kling_prompt pre-storage | Kim correction 2026-04-23 | build_motion_prompt() runs in Storyboard tab on demand |
| L14: FLUX not Kling for stills | Kim correction 2026-04-23 | BFL API, ~$0.08/image |

---

## 12. WHAT THE NEXT SESSION NEEDS TO KNOW

1. **No motion prompts in Beat Generator.** `build_motion_prompt()` runs in the Storyboard tab's existing "send for animation" path. Beat Generator only stores `speaker` + `emotion` — those are the inputs `build_motion_prompt()` needs later.

2. **`SPEAKER_MOTION_PROFILES` already exists** in `production_server.py` (LD-307). Do not re-implement.

3. **FLUX Kontext = BFL API** (`api.bfl.ai`), not WaveSpeed. Auth header is `x-key`, not `Authorization: Bearer`.

4. **Kling = Storyboard tab only.** Beat Generator never calls WaveSpeed.

5. **Lore: Guide Bird / Pip = Chipper** (LD-183). Parser canonicalizes at extraction. The skeleton files still contain "Guide Bird" — `_canon()` handles it.

6. **Skip non-video events.** Events with type `Interactive`, `Avatar Creation`, `no video` get no beats.

7. **Module markers stop extraction.** `**► INSERT MODULE M{N} ◄**` = stop extracting. Resume at `### Resolution`.

8. **Source fidelity (Rule 11).** `dialogue_text` is verbatim — never paraphrase, summarize, or rephrase.

9. **Character references** live in `Production/Character_Assets/`. FLUX Kontext uses them as `input_image` for identity preservation. If a creature has no reference yet, pass no `input_image` (text-to-image fallback).

10. **Phase 0 pre-flight is mandatory.** Editing `production_server.py` = ARCHITECTURAL. Must have `prod_preflight_reviews` row before any code change.

---

**End of handoff. Execute in Claude Code terminal CLI only.**
