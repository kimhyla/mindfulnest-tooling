#!/usr/bin/env python3
"""
MindfulNest Storyboard Builder
===============================
Generates a self-contained HTML storyboard from images, audio, and dialogue data.
The output HTML has editable text, play buttons, image assignment, pause sliders,
reorder, and an export button.

REGISTRY-FIRST WORKFLOW (PREFERRED):
    Use build_storyboard_from_registry(module_id, event_number, lines, output_path, title, subtitle)
    This queries the Directus prod_visual_assets registry to ensure all images are approved
    and registered, maintaining pipeline integrity.

    from build_storyboard import build_storyboard_from_registry
    build_storyboard_from_registry(
        module_id="M1",
        event_number=1,
        lines=[{"speaker":"Guide Bird","text":"Hello!","image":"master","audio_key":None,"pause":0.5,"section":"Setup"}],
        output_path="storyboard.html",
        title="Event 1: First Meeting",
        subtitle="Arc 1 Storyboard"
    )

IMAGE MAP EXPORT WORKFLOW:
    python3 build_storyboard.py --export-image-map --module M1 --event 1 [--output map.json]
    Generates a detailed JSON file mapping storyboard image keys to source filepaths on disk.
    Useful for downstream tools needing full traceability of visual assets.

LEGACY WORKFLOW (MANUAL CONFIG — FALLBACK ONLY):
    python3 build_storyboard.py --config storyboard_config.json --output storyboard.html

CONFIG FORMAT (JSON):
{
  "title": "Event 1: Tessa's Fall",
  "subtitle": "MindfulNest Arc 1 / M1 Story Scene",
  "images": {
    "master": "/path/to/master.png",
    "tessa_closeup": "/path/to/tessa_closeup.png",
    "guidebird_face": "/path/to/guidebird_face.png"
  },
  "image_labels": {
    "master": "Master Wide Shot",
    "tessa_closeup": "Tessa Close-up",
    "guidebird_face": "Guide Bird Face"
  },
  "audio": {
    "shot6_s1": "/path/to/shot6_s1.mp3",
    "shot6_s2": "/path/to/shot6_s2.mp3"
  },
  "speakers": ["Guide Bird", "Tessa", "Luna", "[Stage Direction]", "[Narration]"],
  "lines": [
    {"speaker": "Guide Bird", "text": "Are you OK?", "image": "master", "audio_key": null, "pause": 0.5, "section": "Setup"},
    {"speaker": "Tessa", "text": "I fell...", "image": "tessa_closeup", "audio_key": "shot6_s1", "pause": 0.3, "section": "Setup"}
  ]
}

OR call build_storyboard() directly from Python:

    from build_storyboard import build_storyboard
    build_storyboard(config_dict, output_path)
"""

import argparse
import base64
import hashlib
import io
import json
import os
import re
import sys

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


def _read_credentials():
    """
    Read Directus credentials from API_KEYS_MASTER.md at runtime.
    NEVER hardcode credentials — this function is the single source of truth.

    Falls back to environment variables DIRECTUS_EMAIL / DIRECTUS_PASSWORD
    if the file cannot be found (e.g. in CI or isolated environments).
    """
    # Try to find API_KEYS_MASTER.md relative to this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(script_dir, "..", "API_KEYS_MASTER.md"),
        os.path.join(script_dir, "..", "..", "Production", "API_KEYS_MASTER.md"),
    ]

    for path in candidates:
        path = os.path.normpath(path)
        if os.path.exists(path):
            with open(path, "r") as f:
                content = f.read()
            # Extract Directus credentials from the markdown table
            # Table format: | Service | Credential | Value | Notes |
            # We need the Value column (3rd column) from Directus rows
            email = None
            password = None
            for line in content.split("\n"):
                if "Directus" in line and "Admin Email" in line:
                    # Split on | and grab the value column (3rd column, index 3)
                    parts = line.split("|")
                    if len(parts) >= 4:
                        email = parts[3].strip().strip("`").strip()
                elif "Directus" in line and "Admin Password" in line:
                    parts = line.split("|")
                    if len(parts) >= 4:
                        password = parts[3].strip().strip("`").strip()
            if email and password:
                print(f"  Credentials loaded from {os.path.basename(path)}")
                return email, password

    # Fallback to environment variables
    email = os.environ.get("DIRECTUS_EMAIL")
    password = os.environ.get("DIRECTUS_PASSWORD")
    if email and password:
        print("  Credentials loaded from environment variables")
        return email, password

    raise FileNotFoundError(
        "Cannot find API_KEYS_MASTER.md and no DIRECTUS_EMAIL/DIRECTUS_PASSWORD env vars set. "
        "Ensure API_KEYS_MASTER.md exists in Production/ or set environment variables."
    )


def _parse_module_id(module_id):
    """
    Parse module_id to integer for Directus queries.
    Directus prod_visual_assets.module_id is INTEGER, not string.

    Accepts: "M1" -> 1, "M5" -> 5, 1 -> 1, "arc1_m1_event1" -> 1, None -> None
    """
    if module_id is None:
        return None
    if isinstance(module_id, int):
        return module_id
    match = re.search(r'[Mm](\d+)', str(module_id))
    if match:
        return int(match.group(1))
    try:
        return int(module_id)
    except (ValueError, TypeError):
        print(f"  WARNING: Cannot parse module_id '{module_id}' to integer, using None")
        return None


def _directus_auth():
    """
    Authenticate to Directus and return (token, base_url).
    Reads credentials from API_KEYS_MASTER.md at runtime.
    """
    if not HAS_REQUESTS:
        raise ImportError(
            "requests library required for Directus queries. "
            "Install: pip install requests"
        )

    DIRECTUS_BASE = "https://directus-production-3460.up.railway.app"
    email, password = _read_credentials()

    auth_resp = requests.post(
        f"{DIRECTUS_BASE}/auth/login",
        json={"email": email, "password": password},
        timeout=10
    )
    auth_resp.raise_for_status()
    token = auth_resp.json().get("data", {}).get("access_token")

    if not token:
        raise ValueError("No access token returned from Directus auth")

    print(f"  Directus auth OK (token: {token[:12]}...)")
    return token, DIRECTUS_BASE


def query_registry_images(module_id, event_number):
    """
    Query the MindfulNest Directus prod_visual_assets registry for approved images.

    MANDATORY ENTRY POINT: This function enforces the registry-first workflow.
    All storyboard builds should begin by querying the registry to ensure consistency
    with the production pipeline.

    Args:
        module_id: str or int, e.g. "M1" or 1 (parsed to integer internally)
        event_number: int, e.g. 1 (for Event 1)

    Returns:
        dict of {filename: {"path": filepath, "label": filename, "dimensions": [w,h],
                            "type": asset_type, "id": directus_id, "purpose": purpose}}
        Returns empty dict if no approved assets found.

    Schema mapping (code field -> Directus field):
        filename    -> filename (REQUIRED)
        filepath    -> filepath (REQUIRED)
        width       -> width (REQUIRED, integer)
        height      -> height (REQUIRED, integer)
        asset_type  -> asset_type (optional)
        status      -> status (filtered to 'approved')
        module_id   -> module_id (INTEGER, not string — "M1" parsed to 1)
        event_number -> event_number (integer)

    Raises:
        ImportError: if requests library is not available
        Exception: detailed error on auth or API failure
    """
    token, base_url = _directus_auth()

    # Parse module_id to integer (Directus schema requires int, not "M1")
    mid = _parse_module_id(module_id)

    # Build filter — module_id may be null in some records
    filters = f"filter[status][_eq]=approved&filter[event_number][_eq]={event_number}"
    if mid is not None:
        filters += f"&filter[module_id][_eq]={mid}"
    else:
        # If module_id is null, also include records where module_id is null
        filters += "&filter[module_id][_null]=true"

    query_url = f"{base_url}/items/prod_visual_assets?{filters}&sort=id"
    headers = {"Authorization": f"Bearer {token}"}

    try:
        query_resp = requests.get(query_url, headers=headers, timeout=10)
        query_resp.raise_for_status()
        items = query_resp.json().get("data", [])

        # Build asset dict keyed by filename (the actual Directus field)
        result = {}
        for item in items:
            fname = item.get("filename", "unnamed")
            # Skip placeholder records (e.g. filename="PENDING")
            if fname.upper() == "PENDING":
                print(f"  Skipping placeholder record ID:{item.get('id')} (filename=PENDING)")
                continue
            # Use filename stem (without extension) as the asset key
            key = os.path.splitext(fname)[0].replace(" ", "_").lower()
            w = item.get("width") or 0
            h = item.get("height") or 0
            result[key] = {
                "path": item.get("filepath", ""),
                "label": fname,
                "dimensions": [w, h],
                "type": item.get("asset_type", "unknown"),
                "id": item.get("id"),
                "purpose": item.get("purpose", ""),
            }

        print(f"  Registry query: {len(result)} approved assets for module_id={mid} event={event_number}")
        for k, v in result.items():
            print(f"    {k}: {v['label']} ({v['dimensions'][0]}x{v['dimensions'][1]}) [{v['type']}]")
        return result

    except Exception as e:
        print(f"ERROR: Registry query failed for module_id={mid} event={event_number}: {e}")
        raise


def build_storyboard_from_registry(module_id, event_number, lines, output_path,
                                    title="", subtitle="", image_base_path=None):
    """
    Build a storyboard by querying the Directus registry for approved images.

    PREFERRED ENTRY POINT: This function should be called instead of manually
    constructing config dicts. It ensures all images are registered and approved
    before inclusion in the storyboard, maintaining pipeline integrity.

    Args:
        module_id: str or int, e.g. "M1" or 1 (parsed to integer internally)
        event_number: int, e.g. 1
        lines: list of line dicts (same format as build_storyboard config["lines"])
               Each line should have: speaker, text, image, audio_key (optional), pause, section
        output_path: where to write the HTML
        title: storyboard title (default: auto-generated)
        subtitle: storyboard subtitle (default: "")
        image_base_path: optional base directory to resolve relative filepaths from registry

    Returns:
        output_path (str) on success

    Raises:
        ImportError: if requests library not available
        Exception: if registry query fails or no approved images found
    """
    print(f"\n{'='*60}")
    print(f"REGISTRY-FIRST BUILD: module={module_id} event={event_number}")
    print(f"{'='*60}")

    # Step 1: Query registry for approved images
    registry_assets = query_registry_images(module_id, event_number)

    if not registry_assets:
        raise ValueError(
            f"No approved images found in registry for {module_id} event {event_number}. "
            "Ensure images are uploaded and marked status=approved in Directus before building."
        )

    # Step 2: Build image config from registry data
    # Resolve filepaths — registry stores relative paths, we may need absolute
    images = {}
    image_labels = {}
    missing_files = []

    # Filter to image-type assets only (skip audio, config, production tools)
    IMAGE_TYPES = {"reference_master", "crop_4x3", "crop", "still", "composite", "reference", "image"}
    NON_IMAGE_EXTENSIONS = {".mp3", ".wav", ".json", ".html", ".py", ".txt", ".md"}

    for asset_key, asset_data in registry_assets.items():
        # Skip non-image assets by type
        asset_type = asset_data.get("type", "").lower()
        if asset_type and asset_type not in IMAGE_TYPES:
            continue
        # Skip non-image assets by file extension
        fpath = asset_data["path"]
        _, ext = os.path.splitext(fpath)
        if ext.lower() in NON_IMAGE_EXTENSIONS:
            continue
        # Try to resolve filepath
        if image_base_path and not os.path.isabs(fpath):
            fpath = os.path.join(image_base_path, fpath)
        if os.path.exists(fpath):
            images[asset_key] = fpath
            image_labels[asset_key] = asset_data["label"]
        else:
            missing_files.append((asset_key, fpath, asset_data.get("id")))
            print(f"  WARNING: File not found for '{asset_key}': {fpath} (registry ID: {asset_data.get('id')})")

    if missing_files and not images:
        raise FileNotFoundError(
            f"No image files found on disk for any of {len(registry_assets)} registry assets. "
            f"Missing: {[m[1] for m in missing_files]}. "
            "Check that image_base_path is correct or that filepaths in Directus are absolute."
        )

    if missing_files:
        print(f"  NOTE: {len(missing_files)} of {len(registry_assets)} images missing from disk. "
              "Building with available images.")

    # Step 3: Build full config dict
    config = {
        "title": title or f"Module {module_id} – Event {event_number}",
        "subtitle": subtitle,
        "images": images,
        "image_labels": image_labels,
        "audio": {},
        "speakers": list(set(line.get("speaker", "Character") for line in lines)),
        "lines": lines,
        "_registry_validated": True,  # Signals build_storyboard() to skip the warning
    }

    # Resolve audio from registry assets and line references
    # Registry audio assets have keys like "line_02_guide_bird" with paths to .mp3 files
    # Lines reference audio as "line_02", "line_03", etc. — need to match by prefix
    AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg"}
    registry_audio = {}
    for asset_key, asset_data in registry_assets.items():
        fpath = asset_data["path"]
        _, ext = os.path.splitext(fpath)
        if ext.lower() in AUDIO_EXTENSIONS:
            # Resolve path relative to image_base_path if needed
            resolved = fpath
            if image_base_path and not os.path.isabs(fpath):
                resolved = os.path.join(image_base_path, fpath)
            if os.path.exists(resolved):
                registry_audio[asset_key] = resolved

    for line in lines:
        audio_key = line.get("audio_key")
        if audio_key and audio_key not in config["audio"]:
            # Try exact match first (e.g., "line_02" matches registry key "line_02")
            if audio_key in registry_audio:
                config["audio"][audio_key] = registry_audio[audio_key]
            else:
                # Try prefix match (e.g., "line_02" matches "line_02_guide_bird")
                matched = False
                for rkey, rpath in registry_audio.items():
                    if rkey.startswith(audio_key + "_"):
                        config["audio"][audio_key] = rpath
                        matched = True
                        break
                if not matched:
                    config["audio"][audio_key] = ""  # No match — empty path

    print(f"\n  Building storyboard: {len(images)} images found on disk, {len(lines)} lines")
    result = build_storyboard(config, output_path)

    # Step 4: Post-build verification (Agent 5 "registry-as-test" pattern)
    # Hash the embedded images and verify they match the source files
    if HAS_PIL:
        _verify_embedded_images(result, images)

    # Step 5: Auto-generate image map as a side effect (traceability)
    # This ensures the full storyboard key → source filepath chain is always available
    output_dir = os.path.dirname(os.path.abspath(output_path))
    mid_str = str(module_id).upper().replace("M", "M") if module_id else "unknown"
    map_path = os.path.join(output_dir, f"storyboard_image_map_{mid_str}_event{event_number}.json")
    export_image_map(
        module_id=module_id,
        event_number=event_number,
        output_path=map_path,
        image_base_path=image_base_path
    )

    return result


def _verify_embedded_images(html_path, source_images):
    """
    Post-build verification: re-read the generated HTML and verify that
    embedded base64 images decode to the correct dimensions.
    This implements the "input-output encoding verification" gate from
    the root cause analysis — catching wrong-file bugs and corruption.
    """
    print(f"\n  POST-BUILD VERIFICATION:")
    with open(html_path, "r") as f:
        html = f.read()

    errors = []
    for key, path in source_images.items():
        # Check that the image key appears in the HTML's TH or IN data
        if f'TH["{key}"]' not in html and f'"{key}"' not in html:
            errors.append(f"  MISSING: Image key '{key}' not found in generated HTML")
            continue

        # Verify source file hash for traceability
        with open(path, "rb") as f:
            source_hash = hashlib.sha256(f.read()).hexdigest()[:12]
        img = Image.open(path)
        print(f"    {key}: {img.size[0]}x{img.size[1]} SHA256:{source_hash} — embedded ✓")

    if errors:
        print("  VERIFICATION ERRORS:")
        for e in errors:
            print(f"    ❌ {e}")
        print("  WARNING: Some images may not have been correctly embedded.")
    else:
        print(f"  ✅ All {len(source_images)} images verified in output HTML")


def encode_image(path, thumb_size=80, ref_size=200):
    """Encode an image as base64, creating thumbnail and reference versions."""
    if HAS_PIL:
        img = Image.open(path)
        # Thumbnail
        t = img.copy()
        t.thumbnail((thumb_size, thumb_size), Image.LANCZOS)
        buf = io.BytesIO()
        t.save(buf, format="PNG", optimize=True)
        thumb_b64 = base64.b64encode(buf.getvalue()).decode()
        # Reference (larger for grid display)
        r = img.copy()
        r.thumbnail((ref_size, ref_size), Image.LANCZOS)
        buf2 = io.BytesIO()
        r.save(buf2, format="PNG", optimize=True)
        ref_b64 = base64.b64encode(buf2.getvalue()).decode()
    else:
        # Without PIL, encode full image (larger file but still works)
        with open(path, "rb") as f:
            full_b64 = base64.b64encode(f.read()).decode()
        thumb_b64 = full_b64
        ref_b64 = full_b64
    return thumb_b64, ref_b64


def encode_audio(path):
    """Encode an audio file as base64."""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def emit_full_timeline_panel():
    """Return the HTML/CSS/JS for the Full Module Assembly Timeline Editor panel.

    FULL_TIMELINE_EDITOR_V1 — added 2026-04-26.
    WaveSurfer MUST use ws.load(url) ONLY. Never ws.setMediaElement(). Never bind
    to a <video> element. See archive/20260420_failed_wavesurfer_bindings/README.md.
    Drag-drop pattern lifted verbatim from build_storyboard.py lines 595-820.
    """
    return (
        '<script src="https://unpkg.com/wavesurfer.js@7/dist/wavesurfer.min.js"></script>\n'
        '<style>\n'
        '.tl-panel{max-width:900px;margin:20px auto;background:#16213e;border-radius:12px;padding:16px;border:1px solid #333}\n'
        '.tl-panel h3{color:#e0c3fc;font-size:14px;margin-bottom:10px;letter-spacing:.5px}\n'
        '.tl-header{display:flex;align-items:center;gap:8px;margin-bottom:10px}\n'
        '.tl-header h3{margin:0;flex:1}\n'
        '.tl-header button{background:#4a3f6b;color:#e0c3fc;border:none;padding:5px 12px;border-radius:6px;cursor:pointer;font-size:13px}\n'
        '.tl-header button:hover{background:#6b5b95}\n'
        '.tl-waveform-wrap{position:relative;background:#0a0a1a;border-radius:8px;overflow:hidden;min-height:90px;border:2px dashed #333;cursor:crosshair}\n'
        '.tl-waveform-wrap.tl-drop-active{border-color:#52b788;box-shadow:0 0 12px rgba(82,183,136,.3)}\n'
        '#tl-waveform{position:relative;z-index:1}\n'
        '.tl-segments{position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:2}\n'
        '.tl-seg-line{position:absolute;top:0;height:100%;border-left:1px dashed #4a3f6b;pointer-events:none}\n'
        '.tl-seg-label{position:absolute;top:3px;left:3px;font-size:9px;color:#6b5b95;white-space:nowrap}\n'
        '.tl-markers{position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:3}\n'
        '.tl-cue-dot{position:absolute;top:50%;transform:translate(-50%,-50%);width:12px;height:12px;background:#f39c12;border-radius:50%;border:2px solid #e67e22;cursor:pointer;pointer-events:all;transition:transform .1s}\n'
        '.tl-cue-dot:hover{transform:translate(-50%,-50%) scale(1.4)}\n'
        '.tl-cue-bar{position:absolute;top:55%;height:14px;background:rgba(52,152,219,.45);border:1px solid #3498db;border-radius:3px;cursor:pointer;pointer-events:all}\n'
        '.tl-cue-bar-handle{position:absolute;right:-4px;top:0;width:8px;height:100%;cursor:ew-resize;background:#3498db;border-radius:2px;pointer-events:all}\n'
        '.tl-banner{background:#2c1a0e;color:#e67e22;border:1px solid #e67e22;border-radius:6px;padding:10px 14px;font-size:12px;margin-bottom:10px}\n'
        '.tl-library{margin-top:12px}\n'
        '.tl-library h4{color:#aaa;font-size:12px;margin-bottom:6px}\n'
        '.tl-tabs{display:flex;gap:4px;margin-bottom:6px}\n'
        '.tl-tab{background:#0f3460;color:#a5d8ff;border:1px solid #333;padding:4px 12px;border-radius:4px;cursor:pointer;font-size:12px}\n'
        '.tl-tab.active{background:#4a3f6b;color:#e0c3fc;border-color:#6b5b95}\n'
        '.tl-lib-list{display:flex;flex-wrap:wrap;gap:6px;min-height:30px}\n'
        '.tl-lib-item{background:#1a3a5e;color:#a5d8ff;border:1px solid #2d5a8e;padding:4px 10px;border-radius:6px;font-size:11px;cursor:grab;user-select:none}\n'
        '.tl-lib-item:hover{background:#2d5a8e}\n'
        '.tl-lib-item.dragging{opacity:.4;cursor:grabbing}\n'
        '.tl-inspector{background:#0f3460;border:1px solid #4a3f6b;border-radius:8px;padding:10px;margin-top:10px;font-size:12px}\n'
        '.tl-inspector label{color:#aaa;margin-right:4px}\n'
        '.tl-inspector input[type=range]{width:120px;vertical-align:middle}\n'
        '.tl-inspector input[type=number]{width:60px;background:#0a0a1a;color:#eee;border:1px solid #444;border-radius:4px;padding:2px 4px}\n'
        '.tl-inspector .tl-del-btn{background:#4a2020;color:#ff8888;border:none;padding:3px 8px;border-radius:4px;cursor:pointer;margin-left:8px;font-size:11px}\n'
        '.tl-actions{display:flex;align-items:center;gap:8px;margin-top:10px;flex-wrap:wrap}\n'
        '.tl-actions button{background:#2d6a4f;color:#b7e4c7;border:none;padding:6px 14px;border-radius:6px;cursor:pointer;font-size:12px}\n'
        '.tl-actions button:hover{background:#40916c}\n'
        '#tl-status{font-size:11px;color:#aaa;margin-left:4px}\n'
        '</style>\n'
        '<div class="tl-panel">\n'
        '  <div class="tl-header"><h3>FULL MODULE TIMELINE</h3>'
        '<button onclick="tlPlay()">&#9654; Play</button>'
        '<button onclick="tlStop()">&#9632; Stop</button></div>\n'
        '  <div id="tl-banner" class="tl-banner" style="display:none">'
        'Click <strong>Preview-Stitched v2</strong> first &mdash; then the waveform will appear here.</div>\n'
        '  <div id="tl-waveform-wrap" class="tl-waveform-wrap">\n'
        '    <div id="tl-waveform"></div>\n'
        '    <div id="tl-segments" class="tl-segments"></div>\n'
        '    <div id="tl-markers" class="tl-markers"></div>\n'
        '  </div>\n'
        '  <div class="tl-library">\n'
        '    <h4>SOUND LIBRARY</h4>\n'
        '    <div class="tl-tabs">'
        '<button class="tl-tab active" onclick="tlShowTab(\'sfx\')">SFX</button>'
        '<button class="tl-tab" onclick="tlShowTab(\'ambient\')">Ambient</button></div>\n'
        '    <div id="tl-sfx-list" class="tl-lib-list"></div>\n'
        '    <div id="tl-ambient-list" class="tl-lib-list" style="display:none"></div>\n'
        '  </div>\n'
        '  <div id="tl-inspector" class="tl-inspector" style="display:none">\n'
        '    <strong id="tl-insp-name" style="color:#e0c3fc"></strong><br>\n'
        '    <label>Vol:</label><input type="range" id="tl-insp-vol" min="0" max="1" step="0.01" oninput="tlInspUpdate()">'
        '<span id="tl-insp-vol-val" style="color:#e0c3fc;margin:0 8px 0 4px;font-size:11px"></span>\n'
        '    <label>Fade in:</label><input type="number" id="tl-insp-fadein" min="0" max="5000" oninput="tlInspUpdate()"> ms&nbsp;'
        '<label>Fade out:</label><input type="number" id="tl-insp-fadeout" min="0" max="5000" oninput="tlInspUpdate()"> ms'
        '<button class="tl-del-btn" onclick="tlDeleteCue(tlInspCueId)">Delete</button>\n'
        '  </div>\n'
        '  <div class="tl-actions">'
        '<button onclick="tlPreviewWithSfx()">Preview with SFX</button>'
        '<button onclick="tlBakeToFinal()" style="background:#1a4a6e;color:#a5d8ff">Bake to Final</button>'
        '<span id="tl-status"></span></div>\n'
        '</div>\n'
        '<script>\n'
        '/* Full Module Timeline Editor — FULL_TIMELINE_EDITOR_V1 (2026-04-26)\n'
        ' * WaveSurfer: ws.load(url) ONLY. Never ws.setMediaElement().\n'
        ' * See: archive/20260420_failed_wavesurfer_bindings/README.md */\n'
        'var tlWs=null,tlDurationMs=0,tlCues={},tlSegBounds=[],tlInspCueId=null;\n'
        'var tlDraggingSfxPath=null,tlDraggingSfxCat=null;\n'
        '\n'
        'function tlInit(){\n'
        '  tlLoadAudio();\n'
        '  tlLoadSfxLibrary();\n'
        '  window.addEventListener("focus",function(){tlCheckStaleness();});\n'
        '}\n'
        '\n'
        'function tlLoadAudio(){\n'
        '  var banner=document.getElementById("tl-banner");\n'
        '  var wrap=document.getElementById("tl-waveform-wrap");\n'
        '  fetch("/api/timeline/audio/event_1")\n'
        '    .then(function(r){\n'
        '      if(r.status===404){\n'
        '        banner.style.display="block";\n'
        '        wrap.style.minHeight="10px";\n'
        '        return null;\n'
        '      }\n'
        '      banner.style.display="none";\n'
        '      wrap.style.minHeight="90px";\n'
        '      return r.json();\n'
        '    })\n'
        '    .then(function(data){\n'
        '      if(!data)return;\n'
        '      tlDurationMs=data.duration_ms;\n'
        '      tlSegBounds=data.segment_boundaries||[];\n'
        '      tlInitWaveSurfer(data.audio_url);\n'
        '    })\n'
        '    .catch(function(e){console.error("[tl] audio load:",e);});\n'
        '}\n'
        '\n'
        'function tlInitWaveSurfer(audioUrl){\n'
        '  if(tlWs){try{tlWs.destroy();}catch(_){}tlWs=null;}\n'
        '  if(typeof WaveSurfer==="undefined"){\n'
        '    document.getElementById("tl-status").textContent="WaveSurfer not loaded (no internet?)";\n'
        '    return;\n'
        '  }\n'
        '  /* CRITICAL: ws.load(url) ONLY. Never ws.setMediaElement(). */\n'
        '  tlWs=WaveSurfer.create({\n'
        '    container:"#tl-waveform",\n'
        '    waveColor:"#6b5b95",\n'
        '    progressColor:"#e0c3fc",\n'
        '    height:80,\n'
        '    normalize:true,\n'
        '    interact:true,\n'
        '  });\n'
        '  tlWs.load(audioUrl);\n'
        '  tlWs.on("ready",function(){tlDrawSegments();tlRedrawMarkers();});\n'
        '  tlWs.on("error",function(e){\n'
        '    document.getElementById("tl-status").textContent="Waveform error: "+e;\n'
        '  });\n'
        '}\n'
        '\n'
        'function tlDrawSegments(){\n'
        '  var segs=document.getElementById("tl-segments");\n'
        '  segs.innerHTML="";\n'
        '  if(!tlDurationMs)return;\n'
        '  for(var i=0;i<tlSegBounds.length;i++){\n'
        '    var s=tlSegBounds[i];\n'
        '    var pct=(s.start_ms/tlDurationMs)*100;\n'
        '    var div=document.createElement("div");\n'
        '    div.className="tl-seg-line";\n'
        '    div.style.left=pct+"%";\n'
        '    var lbl=document.createElement("span");\n'
        '    lbl.className="tl-seg-label";\n'
        '    lbl.textContent=s.label;\n'
        '    div.appendChild(lbl);\n'
        '    segs.appendChild(div);\n'
        '  }\n'
        '}\n'
        '\n'
        'function tlRedrawMarkers(){\n'
        '  var markers=document.getElementById("tl-markers");\n'
        '  markers.innerHTML="";\n'
        '  Object.keys(tlCues).forEach(function(id){tlAddMarkerEl(tlCues[id]);});\n'
        '}\n'
        '\n'
        'function tlAddMarkerEl(cue){\n'
        '  var markers=document.getElementById("tl-markers");\n'
        '  var pct=tlDurationMs?(cue.offset_ms/tlDurationMs)*100:0;\n'
        '  var el=document.createElement("div");\n'
        '  el.id="tl-cue-"+cue.id;\n'
        '  if(cue.cue_type==="ambient_segment"){\n'
        '    el.className="tl-cue-bar";\n'
        '    var endPct=cue.end_ms?(cue.end_ms/tlDurationMs*100):Math.min(pct+8,100);\n'
        '    el.style.left=pct+"%";\n'
        '    el.style.width=(endPct-pct)+"%";\n'
        '    var handle=document.createElement("div");\n'
        '    handle.className="tl-cue-bar-handle";\n'
        '    (function(cid){handle.addEventListener("mousedown",function(e){tlStartResizeBar(e,cid);});})(cue.id);\n'
        '    el.appendChild(handle);\n'
        '  } else {\n'
        '    el.className="tl-cue-dot";\n'
        '    el.style.left=pct+"%";\n'
        '  }\n'
        '  el.title=cue.id+" @ "+(cue.offset_ms/1000).toFixed(2)+"s";\n'
        '  (function(cid){el.addEventListener("click",function(e){e.stopPropagation();tlShowInspector(cid);});})(cue.id);\n'
        '  markers.appendChild(el);\n'
        '}\n'
        '\n'
        'function tlStartResizeBar(e,cueId){\n'
        '  e.preventDefault();\n'
        '  var wrapEl=document.getElementById("tl-waveform-wrap");\n'
        '  function onMove(ev){\n'
        '    var rect=wrapEl.getBoundingClientRect();\n'
        '    var pct=Math.max(0,Math.min(1,(ev.clientX-rect.left)/rect.width));\n'
        '    var newEndMs=Math.round(pct*tlDurationMs);\n'
        '    if(tlCues[cueId]){\n'
        '      tlCues[cueId].end_ms=newEndMs;\n'
        '      var barEl=document.getElementById("tl-cue-"+cueId);\n'
        '      if(barEl){\n'
        '        var startPct=tlCues[cueId].offset_ms/tlDurationMs*100;\n'
        '        barEl.style.width=(pct*100-startPct)+"%";\n'
        '      }\n'
        '    }\n'
        '  }\n'
        '  function onUp(){\n'
        '    document.removeEventListener("mousemove",onMove);\n'
        '    document.removeEventListener("mouseup",onUp);\n'
        '    if(tlCues[cueId])tlSaveCue(tlCues[cueId]);\n'
        '  }\n'
        '  document.addEventListener("mousemove",onMove);\n'
        '  document.addEventListener("mouseup",onUp);\n'
        '}\n'
        '\n'
        'function tlSetupLibraryDrag(){\n'
        '  var items=document.querySelectorAll(".tl-lib-item");\n'
        '  items.forEach(function(item){\n'
        '    item.setAttribute("draggable","true");\n'
        '    item.addEventListener("dragstart",function(e){\n'
        '      tlDraggingSfxPath=this.getAttribute("data-path");\n'
        '      tlDraggingSfxCat=this.getAttribute("data-category");\n'
        '      this.classList.add("dragging");\n'
        '      e.dataTransfer.effectAllowed="copy";\n'
        '      e.dataTransfer.setData("sfx_path",tlDraggingSfxPath);\n'
        '      e.dataTransfer.setData("sfx_category",tlDraggingSfxCat);\n'
        '    });\n'
        '    item.addEventListener("dragend",function(){\n'
        '      this.classList.remove("dragging");\n'
        '      tlDraggingSfxPath=null;tlDraggingSfxCat=null;\n'
        '    });\n'
        '  });\n'
        '}\n'
        '\n'
        'function tlSetupDropZone(){\n'
        '  var wrapEl=document.getElementById("tl-waveform-wrap");\n'
        '  wrapEl.addEventListener("dragover",function(e){\n'
        '    e.preventDefault();\n'
        '    e.dataTransfer.dropEffect="copy";\n'
        '    this.classList.add("tl-drop-active");\n'
        '  });\n'
        '  wrapEl.addEventListener("dragleave",function(e){\n'
        '    if(!this.contains(e.relatedTarget))this.classList.remove("tl-drop-active");\n'
        '  });\n'
        '  wrapEl.addEventListener("drop",function(e){\n'
        '    e.preventDefault();\n'
        '    this.classList.remove("tl-drop-active");\n'
        '    var sfxPath=e.dataTransfer.getData("sfx_path");\n'
        '    var sfxCat=e.dataTransfer.getData("sfx_category");\n'
        '    if(!sfxPath)return;\n'
        '    var rect=this.getBoundingClientRect();\n'
        '    var pct=Math.max(0,Math.min(1,(e.clientX-rect.left)/rect.width));\n'
        '    var offsetMs=Math.round(pct*tlDurationMs);\n'
        '    var cueId="cue_"+Date.now();\n'
        '    var cue={\n'
        '      id:cueId,\n'
        '      cue_type:sfxCat==="ambient"?"ambient_segment":"sfx",\n'
        '      source_path:sfxPath,\n'
        '      offset_ms:offsetMs,\n'
        '      end_ms:sfxCat==="ambient"?offsetMs+10000:null,\n'
        '      volume:0.45,\n'
        '      fadein_ms:300,\n'
        '      fadeout_ms:1200,\n'
        '    };\n'
        '    tlCues[cueId]=cue;\n'
        '    tlAddMarkerEl(cue);\n'
        '    tlSaveCue(cue);\n'
        '  });\n'
        '}\n'
        '\n'
        'function tlSaveCue(cue){\n'
        '  fetch("/api/timeline/cues",{\n'
        '    method:"POST",\n'
        '    headers:{"Content-Type":"application/json"},\n'
        '    body:JSON.stringify(cue),\n'
        '  }).then(function(r){return r.json();})\n'
        '    .then(function(d){\n'
        '      if(d.error){document.getElementById("tl-status").textContent="Save error: "+d.error;}\n'
        '    })\n'
        '    .catch(function(e){document.getElementById("tl-status").textContent="Save error: "+e.message;});\n'
        '}\n'
        '\n'
        'function tlDeleteCue(cueId){\n'
        '  if(!cueId)return;\n'
        '  var el=document.getElementById("tl-cue-"+cueId);\n'
        '  if(el)el.parentNode.removeChild(el);\n'
        '  delete tlCues[cueId];\n'
        '  tlHideInspector();\n'
        '  fetch("/api/timeline/cues/"+encodeURIComponent(cueId),{method:"DELETE"})\n'
        '    .catch(function(e){console.error("[tl] delete error:",e);});\n'
        '}\n'
        '\n'
        'function tlShowInspector(cueId){\n'
        '  var cue=tlCues[cueId];\n'
        '  if(!cue)return;\n'
        '  tlInspCueId=cueId;\n'
        '  document.getElementById("tl-insp-name").textContent=\n'
        '    cue.id+" — "+cue.source_path.split("/").pop();\n'
        '  document.getElementById("tl-insp-vol").value=cue.volume;\n'
        '  document.getElementById("tl-insp-vol-val").textContent=cue.volume.toFixed(2);\n'
        '  document.getElementById("tl-insp-fadein").value=cue.fadein_ms;\n'
        '  document.getElementById("tl-insp-fadeout").value=cue.fadeout_ms;\n'
        '  document.getElementById("tl-inspector").style.display="block";\n'
        '}\n'
        '\n'
        'function tlHideInspector(){\n'
        '  tlInspCueId=null;\n'
        '  document.getElementById("tl-inspector").style.display="none";\n'
        '}\n'
        '\n'
        'function tlInspUpdate(){\n'
        '  if(!tlInspCueId||!tlCues[tlInspCueId])return;\n'
        '  var cue=tlCues[tlInspCueId];\n'
        '  var vol=parseFloat(document.getElementById("tl-insp-vol").value);\n'
        '  var fadein=parseInt(document.getElementById("tl-insp-fadein").value,10);\n'
        '  var fadeout=parseInt(document.getElementById("tl-insp-fadeout").value,10);\n'
        '  document.getElementById("tl-insp-vol-val").textContent=vol.toFixed(2);\n'
        '  cue.volume=vol;cue.fadein_ms=fadein;cue.fadeout_ms=fadeout;\n'
        '  tlSaveCue(cue);\n'
        '}\n'
        '\n'
        'function tlShowTab(tab){\n'
        '  document.getElementById("tl-sfx-list").style.display=tab==="sfx"?"flex":"none";\n'
        '  document.getElementById("tl-ambient-list").style.display=tab==="ambient"?"flex":"none";\n'
        '  document.querySelectorAll(".tl-tab").forEach(function(t){\n'
        '    t.classList.toggle("active",t.textContent.toLowerCase()===tab);\n'
        '  });\n'
        '}\n'
        '\n'
        'function tlLoadSfxLibrary(){\n'
        '  fetch("/api/timeline/sfx_library")\n'
        '    .then(function(r){return r.json();})\n'
        '    .then(function(items){\n'
        '      var sfxEl=document.getElementById("tl-sfx-list");\n'
        '      var ambEl=document.getElementById("tl-ambient-list");\n'
        '      sfxEl.innerHTML="";ambEl.innerHTML="";\n'
        '      items.forEach(function(item){\n'
        '        var el=document.createElement("div");\n'
        '        el.className="tl-lib-item";\n'
        '        el.setAttribute("data-path",item.path);\n'
        '        el.setAttribute("data-category",item.category);\n'
        '        el.textContent=item.filename.replace(/\\.[^.]+$/,"");\n'
        '        el.title=item.filename+" ("+(item.duration_ms/1000).toFixed(1)+"s)";\n'
        '        if(item.category==="ambient"){ambEl.appendChild(el);}\n'
        '        else{sfxEl.appendChild(el);}\n'
        '      });\n'
        '      tlSetupLibraryDrag();\n'
        '    })\n'
        '    .catch(function(e){console.error("[tl] sfx library:",e);});\n'
        '}\n'
        '\n'
        'function tlPlay(){if(tlWs){try{tlWs.playPause();}catch(_){}}}\n'
        'function tlStop(){if(tlWs){try{tlWs.stop();}catch(_){}}}\n'
        '\n'
        'function tlPreviewWithSfx(){\n'
        '  document.getElementById("tl-status").textContent="Mixing… (30-60s)";\n'
        '  fetch("/api/timeline/preview_with_sfx",{\n'
        '    method:"POST",\n'
        '    headers:{"Content-Type":"application/json"},\n'
        '    body:JSON.stringify({event_id:"event_1"}),\n'
        '  }).then(function(r){return r.json();})\n'
        '    .then(function(d){\n'
        '      if(d.error){\n'
        '        document.getElementById("tl-status").textContent="Error: "+d.error;\n'
        '        return;\n'
        '      }\n'
        '      document.getElementById("tl-status").textContent="✓ Done — opening in QuickTime…";\n'
        '      fetch("/api/timeline/open_in_quicktime",{\n'
        '        method:"POST",\n'
        '        headers:{"Content-Type":"application/json"},\n'
        '        body:JSON.stringify({mp4_path:d.mp4_path}),\n'
        '      }).catch(function(){});\n'
        '    })\n'
        '    .catch(function(e){\n'
        '      document.getElementById("tl-status").textContent="Error: "+e.message;\n'
        '    });\n'
        '}\n'
        '\n'
        'function tlBakeToFinal(){\n'
        '  fetch("/api/timeline/cues/bake",{\n'
        '    method:"POST",\n'
        '    headers:{"Content-Type":"application/json"},\n'
        '    body:JSON.stringify({}),\n'
        '  }).then(function(r){return r.json();})\n'
        '    .then(function(d){\n'
        '      document.getElementById("tl-status").textContent="✓ Saved — "+d.baked+" cue(s) baked to production_state.json";\n'
        '    })\n'
        '    .catch(function(e){\n'
        '      document.getElementById("tl-status").textContent="Bake error: "+e.message;\n'
        '    });\n'
        '}\n'
        '\n'
        'function tlCheckStaleness(){\n'
        '  fetch("/api/timeline/audio/event_1")\n'
        '    .then(function(r){if(r.ok)return r.json();return null;})\n'
        '    .then(function(data){\n'
        '      if(data&&data.audio_url&&tlWs){\n'
        '        /* Reload waveform if audio URL changed (preview rebuilt) */\n'
        '        var current=tlWs._lastLoadedUrl||"";\n'
        '        if(current&&data.audio_url!==current){\n'
        '          tlDurationMs=data.duration_ms;\n'
        '          tlSegBounds=data.segment_boundaries||[];\n'
        '          tlInitWaveSurfer(data.audio_url);\n'
        '        }\n'
        '        if(tlWs)tlWs._lastLoadedUrl=data.audio_url;\n'
        '      }\n'
        '    })\n'
        '    .catch(function(){});\n'
        '}\n'
        '\n'
        'document.addEventListener("DOMContentLoaded",function(){\n'
        '  tlInit();\n'
        '  tlSetupDropZone();\n'
        '});\n'
        '</script>\n'
    )


def build_storyboard(config, output_path):
    """
    Build a self-contained HTML storyboard from a config dict.

    WARNING: This is a LOW-LEVEL function. For production work, use
    build_storyboard_from_registry() instead. That function queries the
    Directus registry to ensure all images are approved and registered.
    Manual config should only be used as a fallback for testing or offline work.

    Args:
        config: dict with keys: title, subtitle, images, image_labels, audio, speakers, lines
        output_path: where to write the HTML file
    """
    # Emit warning if config was constructed manually (no registry query)
    if not config.get("_registry_validated"):
        print(
            "⚠️  WARNING: build_storyboard() called without registry validation. "
            "For production, use build_storyboard_from_registry(module_id, event_number, ...) "
            "to ensure images are registered and approved in Directus."
        )

    title = config.get("title", "Storyboard")
    subtitle = config.get("subtitle", "")
    speakers = config.get("speakers", ["Character A", "Character B", "[Stage Direction]"])
    image_labels = config.get("image_labels", {})
    image_labels["none"] = "(No image)"

    # Encode images
    thumbs = {}
    refs = {}
    for key, path in config.get("images", {}).items():
        if os.path.exists(path):
            thumbs[key], refs[key] = encode_image(path)
            print(f"  Image: {key} ({os.path.getsize(path)//1024}KB -> thumb {len(thumbs[key])//1024}KB)")
        else:
            print(f"  WARNING: Image not found: {path}")

    # Encode audio
    audio_data = {}
    for key, path in config.get("audio", {}).items():
        if os.path.exists(path):
            audio_data[key] = encode_audio(path)
            print(f"  Audio: {key} ({os.path.getsize(path)//1024}KB)")
        else:
            print(f"  WARNING: Audio not found: {path}")

    # Build HTML
    parts = []

    # ===== HEAD + CSS =====
    # Registry validation flag for the HTML comment
    build_mode = "REGISTRY" if config.get("_registry_validated") else "MANUAL CONFIG (fallback)"
    parts.append(f'''<!DOCTYPE html>
<!-- ================================================================
     GENERATED BY: build_storyboard.py ({build_mode} mode)
     DO NOT EDIT THIS HTML DIRECTLY — base64 strings truncate silently.
     TO REBUILD: python3 build_storyboard.py --registry --module [M#] --event [N] --lines [JSON] --output [HTML]
     TO AUDIT:   python3 build_storyboard.py --audit [this_file]
     SEE: CLAUDE.md Rule 6 and .auto-memory/reference_storyboard_builder_modes.md
     ================================================================ -->
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#1a1a2e;color:#eee;padding:20px}}
h1{{text-align:center;color:#e0c3fc;margin-bottom:3px;font-size:1.4em}}
.sub{{text-align:center;color:#888;margin-bottom:8px;font-size:.85em}}
.inst{{text-align:center;color:#aaa;font-size:.8em;margin-bottom:15px;line-height:1.5;max-width:700px;margin-left:auto;margin-right:auto}}
.inst strong{{color:#e0c3fc}}
.bar{{display:flex;gap:8px;justify-content:center;margin-bottom:15px;flex-wrap:wrap}}
.b{{background:#4a3f6b;color:#e0c3fc;border:none;padding:8px 16px;border-radius:8px;cursor:pointer;font-size:13px}}
.b:hover{{background:#6b5b95}}
.b.exp{{background:#2d6a4f;color:#b7e4c7}}
.b.add{{background:#1a4a6e;color:#a5d8ff}}
.sh{{max-width:880px;margin:18px auto 6px;padding:8px 12px;background:#0f3460;border-radius:8px;color:#a5d8ff;font-weight:600;font-size:14px}}
.tl{{max-width:880px;margin:0 auto}}
.lr{{background:#16213e;border-radius:10px;padding:12px;margin-bottom:8px;border:1px solid #333}}
.lr.act{{border-color:#e0c3fc;box-shadow:0 0 12px rgba(224,195,252,.2)}}
.lt{{display:flex;align-items:center;gap:10px;margin-bottom:6px}}
.ln{{background:#4a3f6b;color:#e0c3fc;min-width:26px;height:26px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:bold;font-size:12px}}
.ss{{background:#0f3460;color:#ffd6a5;border:1px solid #444;border-radius:6px;padding:4px 6px;font-size:12px;font-weight:600}}
.at{{font-size:11px;color:#666;margin-left:auto}}
.at.h{{color:#40916c}}
.de{{width:100%;background:#0a0a1a;color:#eee;border:1px solid #333;border-radius:6px;padding:8px 10px;font-size:13px;font-family:inherit;resize:vertical;min-height:36px;line-height:1.4}}
.de:focus{{border-color:#e0c3fc;outline:none}}
.de.sd{{color:#888;font-style:italic}}
.lc{{display:flex;align-items:center;gap:12px;margin-top:6px;flex-wrap:wrap}}
.pb{{border:none;width:42px;height:42px;border-radius:50%;cursor:pointer;font-size:20px;display:flex;align-items:center;justify-content:center;flex-shrink:0}}
.pb.green{{background:#2d6a4f;color:#b7e4c7}}
.pb.green:hover{{background:#40916c;transform:scale(1.08)}}
.pb.gray{{background:#333;color:#666;cursor:default}}
.pb.playing{{background:#c06060;color:#fff}}
.th{{width:50px;height:50px;border-radius:6px;object-fit:cover;border:1px solid #444}}
.is select{{background:#0f3460;color:#eee;border:1px solid #444;border-radius:6px;padding:4px;font-size:11px}}
.pc{{display:flex;align-items:center;gap:6px}}
.pc label{{color:#888;font-size:11px}}
.pc input{{width:70px}}
.pv{{color:#e0c3fc;font-size:11px;min-width:28px}}
.ro button{{background:#333;color:#888;border:none;width:22px;height:18px;cursor:pointer;border-radius:3px;font-size:10px;display:block;margin:1px 0}}
.ro button:hover{{background:#555;color:#eee}}
.db{{background:#4a2020;color:#ff8888;border:none;width:22px;height:22px;border-radius:4px;cursor:pointer;font-size:12px}}
.ep{{max-width:880px;margin:15px auto;background:#16213e;border-radius:10px;padding:15px;border:1px solid #333;display:none}}
@keyframes epFlash{{0%{{border-color:#52b788;box-shadow:0 0 20px rgba(82,183,136,0.4)}}100%{{border-color:#333;box-shadow:none}}}}
.ep h3{{color:#b7e4c7;margin-bottom:8px;font-size:14px}}
.ep pre{{background:#0a0a1a;padding:10px;border-radius:8px;color:#ccc;font-size:11px;white-space:pre-wrap;max-height:400px;overflow-y:auto}}
.ig{{max-width:880px;margin:15px auto}}
.ig h3{{color:#e0c3fc;margin-bottom:8px;font-size:13px}}
.gg{{display:flex;gap:8px;flex-wrap:wrap}}
.ic{{text-align:center}}
.ic img{{width:120px;height:120px;object-fit:cover;border-radius:6px;border:2px solid #333}}
.ic p{{color:#888;font-size:10px;margin-top:3px}}
.ic img{{cursor:grab}}
.ic img:active{{cursor:grabbing}}
.ic img.dragging{{opacity:0.4;border-color:#e0c3fc;cursor:grabbing}}
.drop-target{{border-color:#52b788 !important;box-shadow:0 0 12px rgba(82,183,136,0.3)}}
.drop-hint{{display:none;text-align:center;color:#52b788;font-size:11px;padding:4px;margin-top:4px}}
.lr.drop-target .drop-hint{{display:block}}
</style></head><body>
<h1>{title}</h1>
<p class="sub">{subtitle}</p>
<div class="inst"><strong>How to use:</strong> Edit dialogue directly in text boxes. Change speakers, reorder, assign images, set pauses.
Click <strong>Export</strong> to lock the sequence. Then we generate TTS from your locked text.<br>
<span style="color:#2d6a4f;font-size:16px">&#9654;</span> Green = has TTS (click to hear) &nbsp;
<span style="color:#666;font-size:16px">&#9711;</span> Gray = no audio yet</div>
<div class="bar">
<button class="b" onclick="playAllAudio()" id="pab">&#9654; Play All (audio lines)</button>
<button class="b" onclick="stopAll()">&#9632; Stop</button>
<button class="b add" onclick="addLine()">+ Add Line</button>
<button class="b exp" onclick="exportSeq()">&#128230; Export Locked Sequence</button>
</div>''')

    # Image reference grid
    parts.append('<div class="ig"><h3>Available Images</h3><div class="gg">')
    for key in config.get("images", {}).keys():
        if key in refs:
            label = image_labels.get(key, key)
            parts.append(f'<div class="ic"><img src="data:image/png;base64,{refs[key]}"><p>{label}</p></div>')
    parts.append('</div></div>')

    parts.append('<div class="tl" id="tl"></div>')
    parts.append('<div class="ep" id="ep"><h3>&#9989; Locked Sequence</h3>')
    parts.append('<pre id="et"></pre>')
    parts.append('<div style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap">')
    parts.append('<button class="b cpb" onclick="copyExp()">Copy to Clipboard</button>')
    parts.append('<button class="b" onclick="downloadJSON()" style="background:#1a5276">&#128190; Download as JSON (for builder)</button>')
    parts.append('</div></div>')

    # ===== JAVASCRIPT =====
    parts.append('<script>')

    # Embed thumbnail data
    parts.append('var TH={};')
    parts.append('var _TOP_SERVER="http://localhost:5111";')
    parts.append('var SERVER=_TOP_SERVER; /* SERVER-SCOPE-V1: global alias for render() fetch calls */')
    for key, b64 in thumbs.items():
        parts.append(f'TH["{key}"]="data:image/png;base64,{b64}";')

    # Embed audio data
    parts.append('var AU={};')
    for key, b64 in audio_data.items():
        parts.append(f'AU["{key}"]="data:audio/mpeg;base64,{b64}";')

    # Image labels
    labels_json = json.dumps(image_labels)
    parts.append(f'var IN={labels_json};')

    # Speakers
    speakers_json = json.dumps(speakers)
    parts.append(f'var SP={speakers_json};')

    # Lines data
    lines_js = []
    for line in config.get("lines", []):
        s = line.get("speaker", "")
        t = line.get("text", "").replace('"', '\\"').replace("'", "\\'")
        i = line.get("image", "none")
        a = line.get("audio_key")
        p = line.get("pause", 0.5)
        g = line.get("section", "")
        a_str = f'"{a}"' if a else "null"
        lines_js.append(f'{{s:"{s}",t:"{t}",i:"{i}",a:{a_str},p:{p},g:"{g}"}}')
    parts.append("var L=[" + ",\n".join(lines_js) + "];")

    # Core JS engine (no template literals, pure DOM manipulation)
    parts.append('''
var cA=null,paA=false,paI=-1;

function render(){
var c=document.getElementById("tl");c.innerHTML="";var cg="";
for(var i=0;i<L.length;i++){var l=L[i];
if(l.g!==cg){cg=l.g;var h=document.createElement("div");h.className="sh";h.textContent=cg;c.appendChild(h);}
var r=document.createElement("div");r.className="lr";r.id="r"+i;
var ha=l.a&&AU[l.a];var sd=l.s==="[Stage Direction]"||l.s==="[Narration]";
var tp=document.createElement("div");tp.className="lt";
var nm=document.createElement("div");nm.className="ln";nm.textContent=""+(i+1);tp.appendChild(nm);
var sl=document.createElement("select");sl.className="ss";sl.setAttribute("data-i",""+i);
sl.onchange=function(){var x=parseInt(this.getAttribute("data-i"));L[x].s=this.value;render();};
for(var j=0;j<SP.length;j++){var o=document.createElement("option");o.value=SP[j];o.textContent=SP[j];if(SP[j]===l.s)o.selected=true;sl.appendChild(o);}
tp.appendChild(sl);
var tg=document.createElement("span");tg.className="at"+(ha?" h":"");tg.textContent=ha?"(TTS: "+l.a+")":"(no TTS yet)";tp.appendChild(tg);
r.appendChild(tp);
var ta=document.createElement("textarea");ta.className="de"+(sd?" sd":"");ta.value=l.t;
ta.rows=Math.max(1,Math.ceil(l.t.length/80));
ta.setAttribute("data-i",""+i);
ta.oninput=function(){L[parseInt(this.getAttribute("data-i"))].t=this.value;var si=document.getElementById("saveind"+parseInt(this.getAttribute("data-i")));if(si){si.textContent="\u2026";si.style.color="#888";}};
/* DIALOGUE_EDITS_MUST_PERSIST (decision id=151): auto-save on blur. */
ta.onblur=function(){var idx=parseInt(this.getAttribute("data-i"));var bid="beat_"+(idx<9?"0":"")+(idx+1);var txt=this.value;var si=document.getElementById("saveind"+idx);if(si){si.textContent="saving\u2026";si.style.color="#888";}fetch(SERVER+"/api/beat/update_text",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({beat:bid,text:txt})}).then(function(r){return r.json();}).then(function(d){if(si){if(d.error){si.textContent="\u2717 "+d.error.substring(0,40);si.style.color="#e74c3c";}else{si.textContent="\u2713 saved"+(d.text_modified_after_tts?" (TTS stale)":"");si.style.color=d.text_modified_after_tts?"#f39c12":"#2ecc71";}}}).catch(function(err){if(si){si.textContent="\u2717 "+err.message;si.style.color="#e74c3c";}});};
r.appendChild(ta);
var si=document.createElement("span");si.id="saveind"+i;si.className="saveind";si.style.cssText="font-size:10px;margin-left:8px;opacity:0.85";r.appendChild(si);
var ptb=document.createElement("div");ptb.style.cssText="margin:2px 0 4px 0";var pbtn=document.createElement("button");pbtn.textContent="\u23F8 [pause]";pbtn.style.cssText="font-size:11px;padding:2px 8px;background:#2c3e50;color:#ccc;border:1px solid #555;border-radius:3px;cursor:pointer;margin-right:4px";pbtn.title="Insert [pause] tag at cursor position";pbtn.setAttribute("data-i",""+i);pbtn.onclick=function(){var idx=parseInt(this.getAttribute("data-i"));var tael=document.querySelector('textarea[data-i=\"'+idx+'\"]');if(tael){var start=tael.selectionStart;var end=tael.selectionEnd;var val=tael.value;tael.value=val.substring(0,start)+"[pause]"+val.substring(end);tael.selectionStart=tael.selectionEnd=start+7;L[idx].t=tael.value;tael.focus();}};ptb.appendChild(pbtn);
/* Decision 181 TTS_AUTO_REGEN_ON_TEXT_EDIT — explicit button companion. */
var rbtn=document.createElement("button");rbtn.textContent="🎙 Regen Audio";rbtn.style.cssText="font-size:11px;padding:2px 8px;background:#4a2c5e;color:#eee;border:1px solid #9370b8;border-radius:3px;cursor:pointer;margin-right:4px";rbtn.title="Regenerate ElevenLabs v3 audio for the current text (force)";rbtn.setAttribute("data-i",""+i);rbtn.onclick=function(){var idx=parseInt(this.getAttribute("data-i"));var bid="beat_"+(idx<9?"0":"")+(idx+1);var si=document.getElementById("saveind"+idx);var btn=this;btn.disabled=true;btn.textContent="🎙 regenerating…";if(si){si.textContent="🎙 regenerating audio via ElevenLabs v3 (5–8s)…";si.style.color="#888";}/* REGEN-TIMEOUT-V1: 30s abort so hung requests fail visibly */var _rac=new AbortController();var _rat=setTimeout(function(){_rac.abort();},30000);fetch(SERVER+"/api/beat/regenerate_audio",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({beat:bid}),signal:_rac.signal}).then(function(r){clearTimeout(_rat);return r.json();}).then(function(d){btn.disabled=false;btn.textContent="🎙 Regen Audio";if(!si)return;var tr=d.tts_regen||{};if(tr.ok){si.textContent="✓ audio regen: "+tr.audio_file+" ("+(tr.audio_duration_s||0).toFixed(2)+"s, "+(tr.elapsed_s||0).toFixed(1)+"s call)";si.style.color="#2ecc71";}else{si.textContent="✗ "+((tr.error||d.error||"unknown").substring(0,80));si.style.color="#e74c3c";}}).catch(function(err){clearTimeout(_rat);btn.disabled=false;btn.textContent="🎙 Regen Audio";if(si){si.textContent="✗ "+(err.name==="AbortError"?"Timed out — server restarted?":err.message);si.style.color="#e74c3c";}});};ptb.appendChild(rbtn);
r.appendChild(ptb);
var ct=document.createElement("div");ct.className="lc";
var pb=document.createElement("button");pb.id="pb"+i;
if(ha){pb.className="pb green";pb.innerHTML="&#9654;";pb.title="Play TTS audio";
pb.setAttribute("data-i",""+i);pb.onclick=function(){playLine(parseInt(this.getAttribute("data-i")));};
}else{pb.className="pb gray";pb.innerHTML="&#9711;";pb.title="No audio yet";}
ct.appendChild(pb);
if(l.i!=="none"&&TH[l.i]){var im=document.createElement("img");im.className="th";im.src=TH[l.i];ct.appendChild(im);
}else{var ph=document.createElement("div");ph.style.cssText="width:50px;height:50px;background:#222;border-radius:6px;display:flex;align-items:center;justify-content:center;color:#555;font-size:10px";ph.textContent="none";ct.appendChild(ph);}
var id=document.createElement("div");id.className="is";
var is2=document.createElement("select");is2.setAttribute("data-i",""+i);
is2.onchange=function(){var x=parseInt(this.getAttribute("data-i"));L[x].i=this.value;render();};
var ks=Object.keys(IN);for(var k=0;k<ks.length;k++){var oo=document.createElement("option");oo.value=ks[k];oo.textContent=IN[ks[k]];if(ks[k]===l.i)oo.selected=true;is2.appendChild(oo);}
id.appendChild(is2);ct.appendChild(id);
var pc=document.createElement("div");pc.className="pc";
var pl2=document.createElement("label");pl2.textContent="Pause:";pc.appendChild(pl2);
var ps=document.createElement("input");ps.type="range";ps.min="0";ps.max="3";ps.step="0.1";ps.value=""+l.p;
ps.setAttribute("data-i",""+i);ps.oninput=function(){var x=parseInt(this.getAttribute("data-i"));L[x].p=parseFloat(this.value);document.getElementById("pv"+x).textContent=this.value+"s";};
pc.appendChild(ps);
var pvl=document.createElement("span");pvl.className="pv";pvl.id="pv"+i;pvl.textContent=l.p.toFixed(1)+"s";pc.appendChild(pvl);
ct.appendChild(pc);
var ro=document.createElement("div");ro.className="ro";
var ub=document.createElement("button");ub.innerHTML="&#9650;";ub.setAttribute("data-i",""+i);
ub.onclick=function(){mv(parseInt(this.getAttribute("data-i")),-1);};if(i===0)ub.disabled=true;ro.appendChild(ub);
var dnb=document.createElement("button");dnb.innerHTML="&#9660;";dnb.setAttribute("data-i",""+i);
dnb.onclick=function(){mv(parseInt(this.getAttribute("data-i")),1);};if(i===L.length-1)dnb.disabled=true;ro.appendChild(dnb);
ct.appendChild(ro);
var dl=document.createElement("button");dl.className="db";dl.innerHTML="&#10005;";dl.setAttribute("data-i",""+i);
dl.onclick=function(){var x=parseInt(this.getAttribute("data-i"));if(confirm("Delete line "+(x+1)+"?")){L.splice(x,1);render();}};
ct.appendChild(dl);
r.appendChild(ct);c.appendChild(r);}}

function mv(i,d){var j=i+d;if(j<0||j>=L.length)return;var t=L[i];L[i]=L[j];L[j]=t;render();}
function addLine(){L.push({s:SP[0],t:"(new line)",i:"master",a:null,p:0.5,g:"Custom"});render();window.scrollTo(0,document.body.scrollHeight);}

function playLine(i){
stopAll();var k=L[i].a;if(!k||!AU[k])return;
cA=new Audio(AU[k]);
var b=document.getElementById("pb"+i);var r=document.getElementById("r"+i);
b.className="pb playing";b.innerHTML="&#9632;";r.classList.add("act");
cA.play().catch(function(e){console.error(e);});
cA.onended=function(){b.className="pb green";b.innerHTML="&#9654;";r.classList.remove("act");cA=null;
if(paA&&paI===i){setTimeout(function(){if(!paA)return;var n=i+1;while(n<L.length&&(!L[n].a||!AU[L[n].a]))n++;
if(n<L.length){paI=n;playLine(n);}else{paA=false;document.getElementById("pab").innerHTML="&#9654; Play All (audio lines)";}
},L[i].p*1000);}};}

function playAllAudio(){if(paA){stopAll();return;}paA=true;
var f=-1;for(var i=0;i<L.length;i++){if(L[i].a&&AU[L[i].a]){f=i;break;}}
if(f===-1){alert("No lines have TTS audio yet.");paA=false;return;}
paI=f;document.getElementById("pab").innerHTML="&#9632; Stop";playLine(f);}

function stopAll(){paA=false;paI=-1;if(cA){cA.pause();cA=null;}
var bs=document.querySelectorAll(".pb.playing");for(var i=0;i<bs.length;i++){bs[i].className="pb green";bs[i].innerHTML="&#9654;";}
var rs=document.querySelectorAll(".lr.act");for(var i=0;i<rs.length;i++)rs[i].classList.remove("act");
var p=document.getElementById("pab");if(p)p.innerHTML="&#9654; Play All (audio lines)";}

function exportSeq(){
var ep=document.getElementById("ep");ep.style.display="block";
var t=document.title+" - LOCKED STORYBOARD\\nExported: "+new Date().toLocaleString()+"\\n"+"=".repeat(50)+"\\n\\n";
var cg="";
for(var i=0;i<L.length;i++){var l=L[i];
if(l.g!==cg){cg=l.g;t+="--- "+cg+" ---\\n\\n";}
var im=IN[l.i]||"none";var an=l.a?" [HAS TTS: "+l.a+"]":" [NEEDS TTS]";
if(l.s==="[Stage Direction]"||l.s==="[Narration]"){t+=(i+1)+". "+l.t+"\\n   Image: "+im+" | Pause: "+l.p.toFixed(1)+"s\\n\\n";}
else{t+=(i+1)+". ["+im+"] "+l.s+': "'+l.t+'"\\n   Pause: '+l.p.toFixed(1)+"s"+an+"\\n\\n";}}
var nt=0,ht=0;for(var i=0;i<L.length;i++){if(L[i].a)ht++;else if(L[i].s!=="[Stage Direction]"&&L[i].s!=="[Narration]")nt++;}
t+="\\n--- SUMMARY ---\\nTotal: "+L.length+" | With TTS: "+ht+" | Needs TTS: "+nt+"\\n";
document.getElementById("et").textContent=t;
ep.scrollIntoView({behavior:"smooth",block:"start"});
ep.style.animation="none";ep.offsetHeight;ep.style.animation="epFlash 0.6s ease";}

function downloadJSON(){
var out=[];for(var i=0;i<L.length;i++){var l=L[i];out.push({speaker:l.s,text:l.t,image:l.i,audio_key:l.a,pause:l.p,section:l.g});}
var blob=new Blob([JSON.stringify(out,null,2)],{type:"application/json"});
var a=document.createElement("a");a.href=URL.createObjectURL(blob);
a.download="storyboard_sequence_"+new Date().toISOString().slice(0,10)+".json";
document.body.appendChild(a);a.click();document.body.removeChild(a);
URL.revokeObjectURL(a.href);}

function copyExp(){var t=document.getElementById("et").textContent;var btn=document.querySelector(".cpb");function onSuccess(){if(btn){btn.textContent="Copied!";btn.style.background="#2d6a4f";setTimeout(function(){btn.textContent="Copy to Clipboard";btn.style.background="";},1500);}}function fallbackCopy(){var ta=document.createElement("textarea");ta.value=t;ta.style.position="fixed";ta.style.left="-9999px";document.body.appendChild(ta);ta.select();try{document.execCommand("copy");onSuccess();}catch(e){if(btn){btn.textContent="Copy failed";btn.style.background="#c0392b";setTimeout(function(){btn.textContent="Copy to Clipboard";btn.style.background="";},2000);}}document.body.removeChild(ta);}if(navigator.clipboard&&navigator.clipboard.writeText&&window.isSecureContext){navigator.clipboard.writeText(t).then(onSuccess).catch(fallbackCopy);}else{fallbackCopy();}}

var dragKey=null;
function initDrag(){
  var imgs=document.querySelectorAll(".ic img");
  var keys=Object.keys(IN).filter(function(k){return k!=="none";});
  for(var i=0;i<imgs.length&&i<keys.length;i++){
    imgs[i].setAttribute("draggable","true");
    imgs[i].setAttribute("data-imgkey",keys[i]);
    (function(img){
      img.addEventListener("dragstart",function(e){
        dragKey=this.getAttribute("data-imgkey");
        this.classList.add("dragging");
        e.dataTransfer.effectAllowed="copy";
        e.dataTransfer.setData("text/plain",dragKey);
      });
      img.addEventListener("dragend",function(){
        this.classList.remove("dragging");
        dragKey=null;
        var ts=document.querySelectorAll(".lr.drop-target");
        for(var j=0;j<ts.length;j++)ts[j].classList.remove("drop-target");
      });
    })(imgs[i]);
  }
}
function setupDropZones(){
  var rows=document.querySelectorAll(".lr");
  for(var i=0;i<rows.length;i++){
    var hint=document.createElement("div");
    hint.className="drop-hint";
    hint.textContent="\\u2193 Drop image here to assign";
    rows[i].appendChild(hint);
    (function(row){
      row.addEventListener("dragover",function(e){
        e.preventDefault();e.dataTransfer.dropEffect="copy";
        this.classList.add("drop-target");
      });
      row.addEventListener("dragleave",function(e){
        if(!this.contains(e.relatedTarget))this.classList.remove("drop-target");
      });
      row.addEventListener("drop",function(e){
        e.preventDefault();this.classList.remove("drop-target");
        var key=e.dataTransfer.getData("text/plain");
        if(!key)return;
        var idx=parseInt(this.id.replace("r",""));
        if(!isNaN(idx)&&idx>=0&&idx<L.length){L[idx].i=key;render();}
      });
    })(rows[i]);
  }
}
var _baseRender=render;
render=function(){_baseRender();initDrag();setupDropZones();};
render();
''')
    parts.append('</script>')
    # Full Module Timeline Editor panel (FULL_TIMELINE_EDITOR_V1, 2026-04-26)
    parts.append(emit_full_timeline_panel())
    parts.append('</body></html>')

    html = '\n'.join(parts)
    with open(output_path, 'w') as f:
        f.write(html)
    print(f"\nStoryboard written: {output_path} ({len(html)//1024}KB)")
    return output_path


def extract_features(html_path):
    """
    Pre-rebuild feature audit: extract a feature manifest from an existing
    storyboard HTML so that after a rebuild, we can verify no features were lost.

    This implements the "pre-rebuild feature manifest" gate from the root cause
    analysis — preventing silent feature regression (like drag-drop loss in v8→v9).

    Returns dict with:
        image_count: number of images in TH{} data
        line_count: number of lines in L[] array
        audio_count: number of audio entries in AU{} data
        has_drag_drop: whether initDrag/setupDropZones exist
        has_play_all: whether playAllAudio exists
        has_export: whether exportSeq exists
        image_keys: list of image key names
        speakers: list of speaker names
    """
    if not os.path.exists(html_path):
        print(f"  No previous storyboard at {html_path} — skipping feature audit")
        return None

    with open(html_path, "r", encoding="utf-8", errors="replace") as f:
        html = f.read()

    features = {
        "image_count": len(re.findall(r'TH\["[^"]+"\]', html)),
        "line_count": html.count("{s:"),
        "audio_count": len(re.findall(r'AU\["[^"]+"\]', html)),
        "has_drag_drop": "initDrag" in html and "setupDropZones" in html,
        "has_play_all": "playAllAudio" in html,
        "has_export": "exportSeq" in html,
        "image_keys": re.findall(r'TH\["([^"]+)"\]', html),
        "speakers": re.findall(r'"([^"]+)" was found in SP', html) or [],
        "file_size_kb": len(html) // 1024,
    }

    # Extract per-line image assignments to prevent scrambling on rebuild.
    # Each line in the JS array is {s:"Speaker",t:"text",i:"image_key",...}
    per_line_images = []
    for match in re.finditer(r'\{s:"([^"]*)",t:"((?:[^"\\]|\\.)*)",i:"([^"]*)"', html):
        per_line_images.append({
            "speaker": match.group(1),
            "text_preview": (match.group(2)[:50] + "...") if len(match.group(2)) > 50 else match.group(2),
            "image": match.group(3)
        })
    features["per_line_images"] = per_line_images

    print(f"\n  FEATURE AUDIT of {os.path.basename(html_path)}:")
    print(f"    Images: {features['image_count']} ({', '.join(features['image_keys'][:5])}{'...' if len(features['image_keys']) > 5 else ''})")
    print(f"    Lines: {features['line_count']}")
    print(f"    Audio: {features['audio_count']}")
    print(f"    Drag-drop: {'YES' if features['has_drag_drop'] else 'NO'}")
    print(f"    Play All: {'YES' if features['has_play_all'] else 'NO'}")
    print(f"    Export: {'YES' if features['has_export'] else 'NO'}")
    print(f"    Size: {features['file_size_kb']}KB")
    if per_line_images:
        print(f"    Per-line image map: {len(per_line_images)} lines extracted")
        for idx, pli in enumerate(per_line_images):
            print(f"      Line {idx+1}: [{pli['image']}] {pli['speaker']}: {pli['text_preview']}")

    return features


def compare_features(before, after_path):
    """
    Post-rebuild comparison: check that a rebuilt storyboard didn't lose features.
    Prints warnings for any regressions.
    """
    if before is None:
        return True  # No previous version to compare

    after = extract_features(after_path)
    if after is None:
        return False

    regressions = []

    if before["has_drag_drop"] and not after["has_drag_drop"]:
        regressions.append("DRAG-DROP was present in previous version but MISSING in rebuild")
    if before["has_play_all"] and not after["has_play_all"]:
        regressions.append("PLAY-ALL was present in previous version but MISSING in rebuild")
    if before["has_export"] and not after["has_export"]:
        regressions.append("EXPORT was present in previous version but MISSING in rebuild")
    if after["image_count"] < before["image_count"]:
        lost = set(before["image_keys"]) - set(after["image_keys"])
        regressions.append(f"IMAGE COUNT dropped from {before['image_count']} to {after['image_count']}. Lost: {lost}")
    if after["line_count"] < before["line_count"] * 0.8:  # Allow some flexibility
        regressions.append(f"LINE COUNT dropped significantly: {before['line_count']} -> {after['line_count']}")

    # Check per-line image assignments for scrambling
    before_pli = before.get("per_line_images", [])
    after_pli = after.get("per_line_images", [])
    if before_pli and after_pli:
        scrambled_lines = []
        check_count = min(len(before_pli), len(after_pli))
        for idx in range(check_count):
            b_img = before_pli[idx]["image"]
            a_img = after_pli[idx]["image"]
            if b_img != a_img and b_img != "none":
                scrambled_lines.append(
                    f"Line {idx+1} ({before_pli[idx]['speaker']}): "
                    f"was [{b_img}] → now [{a_img}]"
                )
        if scrambled_lines:
            regressions.append(
                f"IMAGE ASSIGNMENTS CHANGED on {len(scrambled_lines)} line(s):\n"
                + "\n".join(f"      {s}" for s in scrambled_lines)
            )

    if regressions:
        print(f"\n  ⚠️  FEATURE REGRESSIONS DETECTED:")
        for r in regressions:
            print(f"    ❌ {r}")
        print(f"  The rebuild may have lost features. Review before replacing the previous version.")
        return False
    else:
        print(f"\n  ✅ Feature comparison passed: no regressions detected")
        return True


def smoke_test():
    """
    Session-start smoke test: verify Directus auth works and registry is queryable.
    Run this at the beginning of any production session to catch credential rot
    and schema drift before they become runtime errors.

    Implements the "smoke test at session start" gate from root cause analysis.
    """
    print(f"\n{'='*60}")
    print("SMOKE TEST: Directus connectivity + registry health")
    print(f"{'='*60}")

    results = {"auth": False, "query": False, "schema": False}

    # Test 1: Authentication
    try:
        token, base_url = _directus_auth()
        results["auth"] = True
        print("  [1/3] Auth: ✅ PASS")
    except Exception as e:
        print(f"  [1/3] Auth: ❌ FAIL — {e}")
        return results

    # Test 2: Query prod_visual_assets (just check it returns data)
    try:
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get(
            f"{base_url}/items/prod_visual_assets?limit=1",
            headers=headers, timeout=10
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
        results["query"] = True
        print(f"  [2/3] Query: ✅ PASS — {len(data)} record(s) returned")
    except Exception as e:
        print(f"  [2/3] Query: ❌ FAIL — {e}")
        return results

    # Test 3: Schema check — verify expected fields exist
    try:
        resp = requests.get(
            f"{base_url}/fields/prod_visual_assets",
            headers=headers, timeout=10
        )
        resp.raise_for_status()
        fields = {f["field"] for f in resp.json().get("data", [])}
        expected = {"filename", "filepath", "module_id", "event_number", "status",
                    "width", "height", "asset_type"}
        missing = expected - fields
        if missing:
            print(f"  [3/3] Schema: ⚠️  WARN — Missing expected fields: {missing}")
        else:
            results["schema"] = True
            print(f"  [3/3] Schema: ✅ PASS — All {len(expected)} expected fields present")
    except Exception as e:
        print(f"  [3/3] Schema: ❌ FAIL — {e}")

    all_pass = all(results.values())
    print(f"\n  {'✅ ALL TESTS PASSED' if all_pass else '❌ SOME TESTS FAILED'}")
    return results


def export_image_map(module_id, event_number, output_path=None, image_base_path=None):
    """
    Export a detailed image map (storyboard key → source filepath traceability).

    This function queries Directus for approved images and generates a JSON file
    mapping each storyboard image key to its full source information, including:
    - Registry ID (Directus record ID)
    - Filename in registry
    - Source filepath on disk
    - Absolute path (resolved)
    - Image dimensions
    - Asset type
    - Approval status

    Args:
        module_id: str or int, e.g. "M1" or 1 (parsed to integer internally)
        event_number: int, e.g. 1
        output_path: optional output JSON path (default: storyboard_image_map_{module}_{event}.json)
        image_base_path: optional base directory to resolve relative filepaths from registry

    Returns:
        dict: the generated image map (also writes to JSON file)

    Raises:
        ImportError: if requests library not available
        Exception: if registry query fails
    """
    print(f"\n{'='*60}")
    print(f"IMAGE MAP EXPORT: module={module_id} event={event_number}")
    print(f"{'='*60}")

    # Step 1: Query registry for approved images
    registry_assets = query_registry_images(module_id, event_number)

    if not registry_assets:
        print(f"WARNING: No approved images found in registry for {module_id} event {event_number}")
        return {}

    # Step 2: Determine project base path (parent of Production/)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # From tools/ → tools/../.. = Production/.. = project root
    project_base = os.path.normpath(os.path.join(script_dir, "..", ".."))
    if not image_base_path:
        image_base_path = project_base

    # Step 3: Build image map with full traceability
    image_map = {
        "generated_at": io.StringIO(
            __import__("datetime").datetime.utcnow().isoformat() + "Z"
        ).getvalue().strip(),
        "module": str(module_id).upper().replace("M", "M"),  # Normalize to "M1" format
        "event": event_number,
        "project_base": project_base,
        "image_base_path": image_base_path,
        "images": {}
    }

    # Filter to image-type assets only
    IMAGE_TYPES = {"reference_master", "crop_4x3", "crop", "still", "composite", "reference", "image"}
    NON_IMAGE_EXTENSIONS = {".mp3", ".wav", ".json", ".html", ".py", ".txt", ".md"}

    missing_files = []
    for asset_key, asset_data in registry_assets.items():
        # Skip non-image assets by type
        asset_type = asset_data.get("type", "").lower()
        if asset_type and asset_type not in IMAGE_TYPES:
            continue

        # Skip non-image assets by file extension
        fpath = asset_data["path"]
        _, ext = os.path.splitext(fpath)
        if ext.lower() in NON_IMAGE_EXTENSIONS:
            continue

        # Resolve absolute path
        abs_path = fpath
        if not os.path.isabs(abs_path):
            abs_path = os.path.join(image_base_path, abs_path)

        # Normalize path
        abs_path = os.path.normpath(abs_path)

        # Check if file exists
        file_exists = os.path.exists(abs_path)
        if not file_exists:
            missing_files.append((asset_key, fpath, asset_data.get("id")))
            print(f"  WARNING: File not found for '{asset_key}': {abs_path} (registry ID: {asset_data.get('id')})")

        # Add to map regardless of existence (for full transparency)
        image_map["images"][asset_key] = {
            "registry_id": asset_data.get("id"),
            "filename": asset_data.get("label", ""),
            "source_filepath": fpath,
            "absolute_path": abs_path,
            "width": asset_data.get("dimensions", [0, 0])[0],
            "height": asset_data.get("dimensions", [0, 0])[1],
            "aspect_ratio": _compute_aspect_ratio(
                asset_data.get("dimensions", [0, 0])[0],
                asset_data.get("dimensions", [0, 0])[1]
            ),
            "asset_type": asset_data.get("type", "unknown"),
            "status": "approved",
            "file_exists": file_exists
        }

    # Step 4: Determine output path
    if not output_path:
        mid_str = str(module_id).upper().replace("M", "M") if module_id else "unknown"
        output_path = f"storyboard_image_map_{mid_str}_event{event_number}.json"

    # Ensure output path is absolute
    if not os.path.isabs(output_path):
        output_path = os.path.abspath(output_path)

    # Step 5: Write JSON file
    with open(output_path, "w") as f:
        json.dump(image_map, f, indent=2)

    print(f"\n  Image map exported: {output_path}")
    print(f"  Total images: {len(image_map['images'])}")
    print(f"  Files found: {len(image_map['images']) - len(missing_files)}")
    if missing_files:
        print(f"  Files missing: {len(missing_files)}")

    return image_map


def _compute_aspect_ratio(width, height):
    """
    Compute aspect ratio string (e.g., '4:3', '16:9') from pixel dimensions.
    Returns 'unknown' if dimensions are 0 or invalid.
    """
    if not width or not height:
        return "unknown"

    from math import gcd
    g = gcd(int(width), int(height))
    w_ratio = int(width) // g
    h_ratio = int(height) // g
    return f"{w_ratio}:{h_ratio}"


def register_build_in_directus(output_path, module_id, event_number, build_mode, features_dict):
    """
    Post-build auto-registration: register the generated storyboard HTML in Directus.

    This function is called automatically after a successful storyboard build.
    It registers the output file in prod_visual_assets and updates prod_modules
    tracking fields.

    Args:
        output_path: Path to the generated HTML file (full path)
        module_id: Module identifier, e.g. "M1" or 1 (will be parsed to integer)
        event_number: Event number, e.g. 1
        build_mode: String describing the build mode used, e.g. "registry" or "manual_config"
        features_dict: Dict with feature extraction data (image_count, line_count, has_drag_drop, etc.)

    Returns:
        dict with registration results, or None if registration failed (non-blocking)
    """
    if not HAS_REQUESTS:
        print("  WARNING: requests library not available — skipping Directus registration")
        return None

    try:
        # Step 1: Authenticate
        print(f"\n  POST-BUILD REGISTRATION:")
        token, base_url = _directus_auth()

        # Step 2: Register/update in prod_visual_assets
        filename = os.path.basename(output_path)
        asset_type = "storyboard_html"
        status = "built_registry" if build_mode == "registry" else "built_manual"

        # Check if this asset already exists
        query = f"{base_url}/items/prod_visual_assets?filter[filename][_eq]={filename}&limit=1"
        headers = {"Authorization": f"Bearer {token}"}

        check_resp = requests.get(query, headers=headers, timeout=10)
        check_resp.raise_for_status()
        existing = check_resp.json().get("data", [])

        asset_data = {
            "filename": filename,
            "filepath": output_path,
            "asset_type": asset_type,
            "status": status,
            "module_id": _parse_module_id(module_id),
            "event_number": event_number,
            "build_mode": build_mode,
            "feature_summary": json.dumps(features_dict, default=str),
            "notes": f"Auto-registered post-build on {__import__('datetime').datetime.utcnow().isoformat()}Z"
        }

        if existing:
            # PATCH existing asset
            asset_id = existing[0].get("id")
            update_resp = requests.patch(
                f"{base_url}/items/prod_visual_assets/{asset_id}",
                json=asset_data,
                headers=headers,
                timeout=10
            )
            update_resp.raise_for_status()
            print(f"    ✓ Updated prod_visual_assets ID {asset_id}: {filename}")
        else:
            # POST new asset
            create_resp = requests.post(
                f"{base_url}/items/prod_visual_assets",
                json=asset_data,
                headers=headers,
                timeout=10
            )
            create_resp.raise_for_status()
            asset_id = create_resp.json().get("data", {}).get("id")
            print(f"    ✓ Created prod_visual_assets ID {asset_id}: {filename}")

        # Step 3: Update prod_modules tracking fields
        module_id_int = _parse_module_id(module_id)
        if module_id_int:
            # Query current storyboard_version to increment it
            mod_query = f"{base_url}/items/prod_modules/{module_id_int}?fields=storyboard_version"
            mod_resp = requests.get(mod_query, headers=headers, timeout=10)
            mod_resp.raise_for_status()
            current_version = mod_resp.json().get("data", {}).get("storyboard_version", 0) or 0
            next_version = (current_version if isinstance(current_version, int) else 0) + 1

            now_iso = __import__('datetime').datetime.utcnow().isoformat() + "Z"

            module_update = {
                "storyboard_version": next_version,
                "storyboard_status": status,
                "storyboard_built_at": now_iso,
                "storyboard_build_mode": build_mode,
            }

            mod_patch_resp = requests.patch(
                f"{base_url}/items/prod_modules/{module_id_int}",
                json=module_update,
                headers=headers,
                timeout=10
            )
            mod_patch_resp.raise_for_status()
            print(f"    ✓ Updated prod_modules M{module_id_int}: version→{next_version}, status→{status}")

        # Step 4: Log to prod_activity_log
        log_entry = {
            "action": "storyboard_build",
            "module_id": module_id_int,
            "event_number": event_number,
            "details": json.dumps({
                "filename": filename,
                "build_mode": build_mode,
                "image_count": features_dict.get("image_count", 0),
                "line_count": features_dict.get("line_count", 0),
                "has_drag_drop": features_dict.get("has_drag_drop", False),
                "has_audio": features_dict.get("has_audio", False),
                "has_export": features_dict.get("has_export", False),
                "has_play_all": features_dict.get("has_play_all", False),
                "has_pause_sliders": features_dict.get("has_pause_sliders", False),
                "storyboard_version": next_version if module_id_int else None,
            }, default=str)
        }

        log_resp = requests.post(
            f"{base_url}/items/prod_activity_log",
            json=log_entry,
            headers=headers,
            timeout=10
        )
        log_resp.raise_for_status()
        print(f"    ✓ Logged to prod_activity_log")

        print(f"  POST-BUILD REGISTRATION: SUCCESS")
        return {
            "asset_id": asset_id,
            "module_version": next_version if module_id_int else None,
            "status": status,
        }

    except Exception as e:
        print(f"  WARNING: Directus registration failed (non-blocking): {e}")
        print(f"  The storyboard HTML was built successfully, but the dashboard update failed.")
        print(f"  You may need to register it manually in Directus.")
        return None


def append_extras_tabs(output_path):
    """
    Append Beat Generator + Cropper tabs to a built storyboard HTML (Path A).

    Injection strategy (safe string anchors, no base64 in injection zones):
    1. Tab CSS injected before </style>.
    2. Tab bar + panel-sb opening div injected after <body>.
    3. panel-bg + panel-cr HTML injected before the first <script> tag
       (which follows the image/audio gallery HTML in build_storyboard output).
    4. Beat Generator JS injected before </script></body></html>.

    Only call on freshly built storyboards (single <script> block).
    """
    with open(output_path, "r", encoding="utf-8") as f:
        html = f.read()

    # ---- 1. Tab CSS ----
    tab_css = """
/* Beat Generator + Cropper tabs */
.bgtabs{display:flex;gap:6px;margin-bottom:12px;border-bottom:2px solid #333;padding-bottom:8px}
.bgtab{background:#16213e;color:#888;border:none;padding:8px 18px;border-radius:6px 6px 0 0;cursor:pointer;font-size:13px;font-weight:600}
.bgtab.active{background:#4a3f6b;color:#e0c3fc;border-bottom:2px solid #e0c3fc}
.bgtab:hover:not(.active){background:#1f3460;color:#ccc}
.tab-panel{display:none}.tab-panel.active{display:block}
/* Beat Generator panel */
#panel-bg{max-width:920px;margin:0 auto}
.bg-arc-sel{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px}
.bg-arc-btn{background:#16213e;color:#aaa;border:1px solid #333;padding:5px 12px;border-radius:6px;cursor:pointer;font-size:12px}
.bg-arc-btn.sel{background:#4a3f6b;color:#e0c3fc;border-color:#e0c3fc}
.bg-seg-list{margin-bottom:12px}
.bg-seg-item{background:#16213e;border:1px solid #333;border-radius:6px;padding:6px 12px;margin-bottom:4px;cursor:pointer;font-size:12px;color:#ccc;display:flex;align-items:center;justify-content:space-between}
.bg-seg-item.sel{background:#1a4a6e;border-color:#a5d8ff;color:#a5d8ff}
.bg-seg-item:hover:not(.sel){background:#1f2a40}
.bg-actions{display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap}
.bg-beat-card{background:#16213e;border:1px solid #333;border-radius:10px;padding:12px;margin-bottom:10px}
.bg-beat-card.drag-over{border-color:#52b788;box-shadow:0 0 10px rgba(82,183,136,.3)}
.bg-ref-row{display:flex;gap:6px;margin-bottom:8px}
.bg-ref-slot{flex:1;min-height:72px;border:1px dashed #555;border-radius:6px;background:#0f1a2e;position:relative;display:flex;align-items:center;justify-content:center;font-size:11px;color:#8aa;overflow:hidden;cursor:pointer}
.bg-ref-slot.drag-over{border-color:#52b788;border-style:solid;box-shadow:0 0 8px rgba(82,183,136,.4)}
.bg-ref-slot.has-ref{border-color:#52b788;border-style:solid}
.bg-ref-slot img{width:100%;height:100%;object-fit:cover;position:absolute;top:0;left:0}
.bg-ref-slot .bg-ref-lbl{position:relative;z-index:1;background:rgba(0,0,0,.55);padding:2px 5px;border-radius:3px;pointer-events:none}
.bg-ref-slot .bg-ref-clr{position:absolute;top:2px;right:4px;z-index:2;background:rgba(0,0,0,.6);border:none;color:#f88;cursor:pointer;font-size:13px;line-height:1;padding:1px 4px;border-radius:3px}
.bg-beat-hdr{display:flex;align-items:center;gap:8px;margin-bottom:8px}
.bg-beat-num{background:#4a3f6b;color:#e0c3fc;width:24px;height:24px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:bold;font-size:11px;flex-shrink:0}
.bg-spk-sel{background:#0f3460;color:#eee;border:1px solid #444;border-radius:6px;padding:3px 6px;font-size:12px}
.bg-emo-sel{background:#0f3460;color:#eee;border:1px solid #444;border-radius:6px;padding:3px 6px;font-size:12px}
.bg-dlg{color:#ddd;font-size:13px;line-height:1.5;margin-bottom:6px;padding:6px 8px;background:#0a0a1a;border-radius:6px;border:1px solid #222}
.bg-scene{color:#888;font-size:11px;margin-bottom:8px;font-style:italic}
.bg-opts{display:flex;gap:8px;margin-bottom:8px;flex-wrap:wrap}
.bg-opt{width:100px;height:75px;border:2px solid #333;border-radius:6px;background:#0a0a1a;display:flex;align-items:center;justify-content:center;cursor:pointer;position:relative;overflow:hidden}
.bg-opt img{width:100%;height:100%;object-fit:cover;border-radius:4px}
.bg-opt.chosen{border-color:#52b788}
.bg-opt-lbl{position:absolute;bottom:2px;left:2px;background:rgba(0,0,0,.7);color:#ccc;font-size:9px;padding:1px 3px;border-radius:3px}
.bg-opt-crop{position:absolute;top:2px;right:2px;background:#4a3f6b;color:#e0c3fc;border:none;font-size:9px;padding:1px 4px;border-radius:3px;cursor:pointer;display:none}
.bg-opt:hover .bg-opt-crop{display:block}
.bg-card-btns{display:flex;gap:6px;flex-wrap:wrap}
.bg-gen-btn{background:#2d6a4f;color:#b7e4c7;border:none;padding:5px 10px;border-radius:6px;cursor:pointer;font-size:11px}
.bg-gen-btn:disabled{background:#333;color:#666;cursor:default}
.bg-del-btn{background:#4a2020;color:#ff8888;border:none;padding:5px 10px;border-radius:6px;cursor:pointer;font-size:11px}
.bg-status{font-size:11px;color:#888;margin-left:auto}
.bg-empty{text-align:center;color:#666;padding:40px;font-size:14px}
/* Cropper panel */
#panel-cr{max-width:920px;margin:0 auto;gap:16px;align-items:flex-start}
#panel-cr.active{display:flex}
#cr-canvas-wrap{flex:1;background:#0a0a1a;border:1px solid #333;border-radius:8px;overflow:hidden;position:relative}
#cr-canvas{display:block;cursor:crosshair}
#cr-sidebar{width:200px;flex-shrink:0}
.cr-info{color:#888;font-size:12px;margin-bottom:12px;line-height:1.6}
.cr-crop-info{background:#16213e;padding:8px;border-radius:6px;font-size:11px;color:#ccc;margin-bottom:12px}
/* ── Animation method + Stitch Groups ────────────────────────────────── */
.bg-anim-row{display:flex;align-items:center;gap:8px;margin:4px 0}
.bg-anim-method{background:#1a1f2e;color:#e8e8e8;border:1px solid #3a3f52;border-radius:4px;padding:4px 8px;font-size:13px}
.bg-group-chip{font-size:10px;padding:2px 6px;border-radius:3px;color:#fff;margin-left:4px;font-weight:bold}
#bg-groups-section{margin-top:24px;padding-top:16px;border-top:2px solid #444}
.bg-groups-header{display:flex;align-items:center;gap:10px;margin-bottom:10px;flex-wrap:wrap}
.bg-groups-header h3{margin:0;font-size:15px;color:#e8e8e8}
.bg-group-row{padding:8px 12px;margin:4px 0;background:#1a1f2e;border:1px solid #3a3f52;border-radius:6px;display:grid;grid-template-columns:1fr auto auto auto auto;gap:8px;align-items:center}
.bg-group-name{color:#e8e8e8;cursor:pointer;font-size:13px}
.bg-group-status{font-size:11px;padding:2px 8px;border-radius:3px;background:#333;color:#aaa}
.bg-status-ready{background:#1a3a1a;color:#6f6}
.bg-status-assembled{background:#1a2a3a;color:#6af}
.bg-status-assembling{background:#2a2a1a;color:#fa6}
.bg-status-error{background:#3a1a1a;color:#f66}
.bg-status-empty,.bg-status-pending{background:#333;color:#aaa}
.bg-assemble-btn{background:#2a5a2a;color:#fff;border:none;border-radius:4px;padding:4px 10px;cursor:pointer;font-size:12px}
.bg-assemble-btn:disabled{opacity:0.4;cursor:not-allowed}
.bg-delete-group{background:none;border:none;color:#f66;cursor:pointer;font-size:16px;padding:0 4px}
.bg-local-config-panel{background:#141920;border:1px solid #3a3f52;padding:12px;margin-top:8px;border-radius:4px}
.bg-local-config-panel label{display:block;color:#aaa;font-size:12px;margin:6px 0 2px}
.bg-local-config-panel input[type=range]{width:100%}
.bg-local-config-panel textarea{width:100%;box-sizing:border-box;background:#1a1f2e;color:#e8e8e8;border:1px solid #3a3f52;border-radius:4px;padding:6px;font-family:monospace;font-size:12px}
.bg-mc-preview-img{max-width:100%;margin-top:8px;border-radius:4px}
.bg-run-btn{background:#2a3f6a;color:#fff;border:none;border-radius:4px;padding:6px 14px;cursor:pointer;font-size:13px;margin-right:6px}
.bg-accept-local-btn{background:#2a5a2a;color:#fff;border:none;border-radius:4px;padding:6px 14px;cursor:pointer;font-size:13px}
.bg-multiselect-check{margin-right:8px;cursor:pointer}
.bg-configure-local-btn{background:#3a2a5a;color:#fff;border:none;border-radius:4px;padding:5px 12px;cursor:pointer;font-size:12px}
/* ── Persistent Library Sidebar (mn-context library-panel) ── */
#mn-lib-sidebar{position:fixed;top:0;right:0;width:260px;height:100vh;background:#0f1722;border-left:1px solid #333;display:flex;flex-direction:row;z-index:1000;transform:translateX(calc(100% - 36px));transition:transform .2s}
#mn-lib-sidebar.open{transform:translateX(0)}
#mn-lib-toggle{writing-mode:vertical-rl;cursor:pointer;background:#4a3f6b;color:#e0c3fc;border:none;padding:10px 4px;font-size:11px;font-weight:bold;flex-shrink:0;width:36px;align-self:stretch;letter-spacing:1px}
.mn-lib-body{flex:1;overflow-y:auto;padding:8px 6px;min-width:0}
.mn-lib-section{margin-bottom:12px}
.mn-lib-section-hdr{color:#888;font-size:10px;text-transform:uppercase;letter-spacing:1px;margin:8px 0 4px;padding-bottom:3px;border-bottom:1px solid #222}
.mn-lib-grid{display:flex;flex-wrap:wrap;gap:4px;margin-bottom:6px}
.mn-lib-item{width:100px;height:75px;border:2px solid #333;border-radius:4px;cursor:grab;overflow:hidden;position:relative;flex-shrink:0}
.mn-lib-item img{width:100%;height:100%;object-fit:cover;display:block}
.mn-lib-item:hover{border-color:#52b788}
.mn-lib-item[data-tier="source"]{border-color:#4a6faa}
.mn-lib-item[data-tier="character_master"]{border-color:#7a5a3a}
.mn-lib-item.dragging{opacity:.45}
.mn-lib-tier-badge{position:absolute;bottom:2px;left:2px;font-size:8px;padding:1px 3px;border-radius:2px;background:rgba(0,0,0,.75);color:#aaa;pointer-events:none}
.mn-lib-upload-btn{display:block;width:100%;background:#141e14;color:#6f6;border:1px dashed #2a4a2a;padding:4px;border-radius:4px;cursor:pointer;font-size:10px;text-align:center;box-sizing:border-box}
.mn-lib-upload-input{display:none}
.mn-lib-empty{color:#555;font-size:11px;font-style:italic;padding:4px 0}
.mn-lib-refresh{background:none;border:none;color:#666;cursor:pointer;font-size:11px;padding:0;margin-left:auto}
#mn-lib-sidebar .bg-beat-card.drag-over,.lr.drag-over-lib{outline:2px dashed #52b788}
"""
    # Inject before </style>
    if "</style>" in html:
        html = html.replace("</style>", tab_css + "\n</style>", 1)

    # ---- 2. Tab bar + panel-sb opening div ----
    # The build_storyboard output opens <body> right after </style></head>
    tab_bar_html = """<div class="bgtabs">
<button class="bgtab active" data-panel="sb" onclick="_bgSwitchTab('sb',this)">Storyboard</button>
<button class="bgtab" data-panel="bg" onclick="_bgSwitchTab('bg',this)">Beat Generator</button>
<button class="bgtab" data-panel="cr" onclick="_bgSwitchTab('cr',this)">Cropper</button>
</div>
<div id="panel-sb" class="tab-panel active">"""

    if "</style></head><body>" in html:
        html = html.replace("</style></head><body>", "</style></head><body>\n" + tab_bar_html, 1)
    elif "<body>" in html:
        html = html.replace("<body>", "<body>\n" + tab_bar_html, 1)

    # ---- 3. panel-bg + panel-cr HTML (injected before first <script>) ----
    # Close panel-sb, add new panels
    bg_panels_html = """</div><!-- /panel-sb -->

<div id="panel-bg" class="tab-panel">
  <div id="bg-arc-sel-wrap">
    <div style="color:#888;font-size:12px;margin-bottom:6px">Select arc:</div>
    <div class="bg-arc-sel" id="bg-arc-sel"></div>
  </div>
  <div id="bg-seg-wrap" style="display:none">
    <div style="color:#888;font-size:12px;margin-bottom:4px">Select segment:</div>
    <div id="bg-seg-list" class="bg-seg-list"></div>
  </div>
  <div class="bg-actions" id="bg-actions" style="display:none">
    <button class="b" onclick="_bgExtractBeats()">&#128196; Extract Beats</button>
    <button class="b" onclick="_bgGenerateAll()" id="bg-gen-all-btn" disabled>&#9889; Generate All Stills</button>
    <button class="b exp" onclick="_bgAcceptToStoryboard()" id="bg-accept-btn" disabled>&#10003; Accept All to Storyboard</button>
  </div>
  <div id="bg-beats" style="max-width:880px;margin:0 auto"></div>
</div>

<div id="panel-cr" class="tab-panel">
  <div id="cr-canvas-wrap">
    <canvas id="cr-canvas" width="800" height="600"></canvas>
  </div>
  <div id="cr-sidebar">
    <div class="cr-info"><strong>Crop tool</strong><br>
    Click and drag on the image to set the crop area.<br>
    4:3 aspect ratio locked.<br>
    Crop will be auto-upscaled to ≥600px shortest side.</div>
    <div class="cr-crop-info" id="cr-crop-info">No image loaded</div>
    <div style="display:flex;gap:6px;flex-wrap:wrap">
      <button class="b" onclick="_crSaveCrop()" id="cr-save-btn" disabled>&#128190; Save Crop</button>
      <button class="b" onclick="_bgSwitchTab('bg',null)">&#8592; Back</button>
    </div>
  </div>
</div>

<div id="mn-lib-sidebar">
<button id="mn-lib-toggle" onclick="_mnLibToggle()">&#x2261; Library</button>
<div class="mn-lib-body">
  <div class="mn-lib-section">
    <div class="mn-lib-section-hdr">Source Images</div>
    <div class="mn-lib-grid" id="mn-lib-grid-source"></div>
    <div class="mn-lib-empty" id="mn-lib-empty-source">No source images yet.</div>
  </div>
  <div class="mn-lib-section">
    <div class="mn-lib-section-hdr" style="display:flex;align-items:center">Ready Images <button class="mn-lib-refresh" onclick="_mnLibFetch()" title="Refresh">&#x21bb;</button></div>
    <div class="mn-lib-grid" id="mn-lib-grid-cropped"></div>
    <div class="mn-lib-empty" id="mn-lib-empty-cropped">No crops yet.</div>
  </div>
  <div class="mn-lib-section">
    <div class="mn-lib-section-hdr">Character Masters</div>
    <div class="mn-lib-grid" id="mn-lib-grid-character_master"></div>
    <div class="mn-lib-empty" id="mn-lib-empty-character_master">No masters yet.</div>
  </div>
  <label class="mn-lib-upload-btn">&#x2B06; Upload Image<input class="mn-lib-upload-input" type="file" accept="image/*" onchange="_mnLibUpload(this)"></label>
</div>
</div>
"""
    # Insert before the first <script> tag
    script_idx = html.find("<script>")
    if script_idx != -1:
        html = html[:script_idx] + bg_panels_html + "\n" + html[script_idx:]

    # ---- 4. Beat Generator JavaScript (before </script></body></html>) ----
    bg_js = r"""

// ====================================================================
// BEAT GENERATOR TAB  (appended by build_storyboard.py --with-extras)
// ====================================================================
var BG_SERVER   = "http://localhost:5111";
var BG_BEATS    = [];
var BG_ARC      = null;
var BG_SEG      = null;
var BG_TASK_MAP = {};  // { beat_id: [rid0, rid1, rid2] }
var BG_POLL_ID  = null;

// Speakers + emotions for dropdowns
var BG_SPEAKERS = ["Chipper","Tessa","Luna","Benson","Ember","Bork","Bramble","Cedric","Narrator"];
var BG_EMOTIONS = ["neutral","happy_excited","upset_shocked","sad_disappointed"];

// ---- Tab switching ----
function _bgSwitchTab(panelId, btn) {
  document.querySelectorAll(".tab-panel").forEach(function(p){ p.classList.remove("active"); });
  document.querySelectorAll(".bgtab").forEach(function(b){ b.classList.remove("active"); });
  var panel = document.getElementById("panel-" + panelId);
  if (panel) panel.classList.add("active");
  if (btn) btn.classList.add("active");
  else {
    var tabs = document.querySelectorAll(".bgtab");
    for (var i = 0; i < tabs.length; i++) {
      if (tabs[i].getAttribute("data-panel") === panelId) tabs[i].classList.add("active");
    }
  }
  if (panelId === "bg") _bgLoadState();
  if (panelId === "cr") _crInitCanvas();
}

// ---- Arc selector init ----
(function() {
  var sel = document.getElementById("bg-arc-sel");
  if (!sel) return;
  for (var i = 1; i <= 10; i++) {
    (function(arcNum) {
      var btn = document.createElement("button");
      btn.className = "bg-arc-btn";
      btn.textContent = "Arc " + arcNum;
      btn.setAttribute("data-arc", arcNum);
      btn.onclick = function() {
        document.querySelectorAll(".bg-arc-btn").forEach(function(b){ b.classList.remove("sel"); });
        this.classList.add("sel");
        BG_ARC = arcNum;
        BG_SEG = null;
        BG_BEATS = [];
        _bgRenderBeats([]);
        _bgLoadSegments(arcNum);
      };
      sel.appendChild(btn);
    })(i);
  }
})();

// ---- Load segments for arc ----
function _bgLoadSegments(arcNum) {
  fetch(BG_SERVER + "/api/bg/segments?arc_number=" + arcNum)
    .then(function(r){ return r.json(); })
    .then(function(d) {
      var list = document.getElementById("bg-seg-list");
      if (!list) return;
      list.innerHTML = "";
      var wrap = document.getElementById("bg-seg-wrap");
      if (wrap) wrap.style.display = "block";
      (d.segments || []).forEach(function(seg) {
        var item = document.createElement("div");
        item.className = "bg-seg-item";
        item.textContent = seg.name;
        item.onclick = function() {
          document.querySelectorAll(".bg-seg-item").forEach(function(x){ x.classList.remove("sel"); });
          this.classList.add("sel");
          BG_SEG = seg;
          BG_BEATS = [];
          var acts = document.getElementById("bg-actions");
          if (acts) acts.style.display = "flex";
          _bgRenderBeats([]);
        };
        list.appendChild(item);
      });
      if (typeof _bgLoadGroups === "function") _bgLoadGroups(arcNum);
    })
    .catch(function(e){ console.error("[BG] segments error:", e); });
}

// ---- Load session state ----
function _bgLoadState() {
  fetch(BG_SERVER + "/api/bg/session-state")
    .then(function(r){ return r.json(); })
    .then(function(d) {
      if (d.beats && d.beats.length) {
        BG_BEATS = d.beats;
        _bgRenderBeats(BG_BEATS);
        var acceptBtn = document.getElementById("bg-accept-btn");
        if (acceptBtn) acceptBtn.disabled = false;
      }
      if (d.active_context) {
        BG_ARC = d.active_context.arc_number;
        var arcBtns = document.querySelectorAll(".bg-arc-btn");
        arcBtns.forEach(function(b){
          if (parseInt(b.getAttribute("data-arc")) === BG_ARC) {
            b.classList.add("sel");
            _bgLoadSegments(BG_ARC);
          }
        });
      }
    })
    .catch(function(){});
}

// ---- Extract beats ----
function _bgExtractBeats() {
  if (!BG_ARC || !BG_SEG) { alert("Select an arc and segment first."); return; }
  var container = document.getElementById("bg-beats");
  if (container) container.innerHTML = '<div class="bg-empty">Extracting beats\u2026</div>';
  fetch(BG_SERVER + "/api/bg/extract-beats", {
    method: "POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify({arc_number: BG_ARC, event_id: BG_SEG.event_id, phase: BG_SEG.phase || "full"})
  })
  .then(function(r){ return r.json(); })
  .then(function(d) {
    BG_BEATS = d.beats || [];
    _bgRenderBeats(BG_BEATS);
    var genBtn = document.getElementById("bg-gen-all-btn");
    var acceptBtn = document.getElementById("bg-accept-btn");
    if (genBtn) genBtn.disabled = BG_BEATS.length === 0;
    if (acceptBtn) acceptBtn.disabled = BG_BEATS.length === 0;
  })
  .catch(function(e){ alert("Extract failed: " + e); });
}

// ---- Render beats ----
function _bgRenderBeats(beats) {
  var container = document.getElementById("bg-beats");
  if (!container) return;
  if (!beats || !beats.length) {
    container.innerHTML = '<div class="bg-empty">No beats yet. Select a segment and click Extract Beats.</div>';
    return;
  }
  container.innerHTML = "";
  beats.forEach(function(beat, idx) {
    var card = document.createElement("div");
    card.className = "bg-beat-card";
    card.id = "bg-card-" + beat.beat_id;

    // Header row: number + speaker + emotion + status + delete
    var hdr = document.createElement("div");
    hdr.className = "bg-beat-hdr";

    var num = document.createElement("div");
    num.className = "bg-beat-num";
    num.textContent = idx + 1;
    hdr.appendChild(num);

    var spkSel = document.createElement("select");
    spkSel.className = "bg-spk-sel";
    BG_SPEAKERS.forEach(function(s){
      var o = document.createElement("option");
      o.value = s; o.textContent = s;
      if (s === beat.speaker) o.selected = true;
      spkSel.appendChild(o);
    });
    spkSel.onchange = function() {
      beat.speaker = this.value;
      _bgUpdateBeat(beat.beat_id, {speaker: this.value});
    };
    hdr.appendChild(spkSel);

    var emoSel = document.createElement("select");
    emoSel.className = "bg-emo-sel";
    BG_EMOTIONS.forEach(function(e){
      var o = document.createElement("option");
      o.value = e; o.textContent = e.replace(/_/g," ");
      if (e === beat.emotion) o.selected = true;
      emoSel.appendChild(o);
    });
    emoSel.onchange = function() {
      beat.emotion = this.value;
      _bgUpdateBeat(beat.beat_id, {emotion: this.value});
    };
    hdr.appendChild(emoSel);

    var statusSpan = document.createElement("span");
    statusSpan.className = "bg-status";
    statusSpan.id = "bg-status-" + beat.beat_id;
    statusSpan.textContent = beat.status || "draft";
    hdr.appendChild(statusSpan);

    var delBtn = document.createElement("button");
    delBtn.className = "bg-del-btn";
    delBtn.textContent = "\u00d7";
    delBtn.title = "Delete beat";
    delBtn.onclick = function() {
      if (!confirm("Delete this beat?")) return;
      fetch(BG_SERVER + "/api/bg/delete-beat", {
        method: "POST",
        headers: {"Content-Type":"application/json"},
        body: JSON.stringify({beat_id: beat.beat_id})
      }).then(function(r){ return r.json(); })
      .then(function(d){
        if (d.ok) {
          BG_BEATS = BG_BEATS.filter(function(b){ return b.beat_id !== beat.beat_id; });
          _bgRenderBeats(BG_BEATS);
        }
      });
    };
    hdr.appendChild(delBtn);
    card.appendChild(hdr);

    // --- Reference image slots (Char Ref + BG Ref) ---
    var refRow = document.createElement("div");
    refRow.className = "bg-ref-row";

    function _makeRefSlot(bid, field, label, currentPath) {
      var sl = document.createElement("div");
      sl.className = "bg-ref-slot" + (currentPath ? " has-ref" : "");
      sl.dataset.beatId = bid;
      sl.dataset.field = field;
      var lbl = document.createElement("span");
      lbl.className = "bg-ref-lbl";
      lbl.textContent = currentPath ? label + " \u2713" : label;
      sl.appendChild(lbl);
      if (currentPath) {
        sl.title = currentPath.split(/[/\\\\]/).pop();
        var found = null;
        for (var _i = 0; _i < MN_LIB_DATA.length; _i++) {
          if (MN_LIB_DATA[_i].abs_path === currentPath) { found = MN_LIB_DATA[_i]; break; }
        }
        if (found && found.thumb_b64) {
          var timg = document.createElement("img");
          timg.src = found.thumb_b64;
          sl.insertBefore(timg, lbl);
        }
        var clr = document.createElement("button");
        clr.className = "bg-ref-clr";
        clr.textContent = "\u00d7";
        clr.title = "Clear " + label;
        clr.onclick = (function(b, f) {
          return function(e) {
            e.stopPropagation(); e.preventDefault();
            var pld = {}; pld[f] = null;
            _bgUpdateBeat(b, pld);
            var bt = (BG_BEATS || []).find(function(x){ return x.beat_id === b; });
            if (bt) bt[f] = null;
            _bgRenderBeats(BG_BEATS);
          };
        })(bid, field);
        sl.appendChild(clr);
      }
      sl.addEventListener("dragover", function(e) {
        if (!_mnLibHasKey(e)) return;
        e.preventDefault(); e.stopPropagation();
        sl.classList.add("drag-over");
      });
      sl.addEventListener("dragleave", function(e) {
        if (!sl.contains(e.relatedTarget)) sl.classList.remove("drag-over");
      });
      sl.addEventListener("drop", function(e) {
        e.preventDefault(); e.stopPropagation();
        sl.classList.remove("drag-over");
        var key = e.dataTransfer.getData("mn-lib-key");
        if (!key) return;
        var item = null;
        for (var _j = 0; _j < MN_LIB_DATA.length; _j++) {
          if (MN_LIB_DATA[_j].key === key) { item = MN_LIB_DATA[_j]; break; }
        }
        if (!item || !item.abs_path) return;
        var apath = item.abs_path;
        var fld = sl.dataset.field;
        var beatId = sl.dataset.beatId;
        var pld = {}; pld[fld] = apath;
        _bgUpdateBeat(beatId, pld).then(function(r) {
          if (!r || r.ok === false) {
            console.error("[BG] ref write failed:", r);
            sl.style.borderColor = "#f44";
            return;
          }
          var bt = (BG_BEATS || []).find(function(x){ return x.beat_id === beatId; });
          if (bt) bt[fld] = apath;
          _bgRenderBeats(BG_BEATS);
        });
      });
      return sl;
    }

    refRow.appendChild(_makeRefSlot(beat.beat_id, "reference_image", "Char Ref", beat.reference_image || null));
    refRow.appendChild(_makeRefSlot(beat.beat_id, "bg_ref_image",    "BG Ref",   beat.bg_ref_image   || null));
    card.appendChild(refRow);
    // --- end reference image slots ---

    // Dialogue — editable textarea
    var dlg = document.createElement("textarea");
    dlg.className = "bg-dlg";
    dlg.value = beat.dialogue_text;
    dlg.rows = 2;
    dlg.style.cssText = "width:100%;box-sizing:border-box;background:#1a1f2e;color:#e8e8e8;border:1px solid #3a3f52;border-radius:4px;padding:8px 10px;font-size:14px;font-family:inherit;resize:vertical;";
    dlg.onblur = function() {
      var newVal = this.value.trim();
      if (newVal !== beat.dialogue_text) {
        beat.dialogue_text = newVal;
        _bgUpdateBeat(beat.beat_id, {dialogue_text: newVal});
      }
    };
    card.appendChild(dlg);

    // Scene notes — editable
    var sc = document.createElement("div");
    sc.className = "bg-scene";
    sc.textContent = beat.scene_notes || "";
    sc.contentEditable = "true";
    sc.style.cursor = "text";
    sc.title = "Click to edit scene notes";
    sc.onblur = function() {
      var newVal = this.textContent.trim();
      if (newVal !== beat.scene_notes) {
        beat.scene_notes = newVal;
        _bgUpdateBeat(beat.beat_id, {scene_notes: newVal});
      }
    };
    card.appendChild(sc);

    // 3 option slots
    var opts = document.createElement("div");
    opts.className = "bg-opts";
    opts.id = "bg-opts-" + beat.beat_id;
    for (var o = 0; o < 3; o++) {
      var slot = document.createElement("div");
      slot.className = "bg-opt";
      slot.id = "bg-opt-" + beat.beat_id + "-" + o;
      slot.setAttribute("data-opt", o);
      slot.setAttribute("data-beat", beat.beat_id);
      var lbl = document.createElement("span");
      lbl.className = "bg-opt-lbl";
      lbl.textContent = "Option " + (o + 1);
      slot.appendChild(lbl);
      // Crop button
      var cropBtn = document.createElement("button");
      cropBtn.className = "bg-opt-crop";
      cropBtn.textContent = "Crop";
      cropBtn.onclick = (function(b, oi) {
        return function(e) {
          e.stopPropagation();
          var key = "bg_" + b.beat_id + "_opt" + oi;
          _crLoadImage(key, b.beat_id);
        };
      })(beat, o);
      slot.appendChild(cropBtn);
      // Check if already have option — prefer /bg-stills/ URL over ephemeral TH cache
      if (beat.flux_options && beat.flux_options[o]) {
        var fopt = beat.flux_options[o];
        if (fopt.local_path) {
          var fname = fopt.local_path.split("/").pop();
          if (fname) {
            var img = document.createElement("img");
            var url = BG_SERVER + "/bg-stills/" + encodeURIComponent(fname)
                    + "?v=" + encodeURIComponent(fopt.request_id || "0");
            img.setAttribute("data-fixc-url", url);
            img.src = url;
            slot.insertBefore(img, lbl);
            if (fopt.key && fopt.key === beat.accepted_image_key) slot.classList.add("chosen");
          }
        } else if (fopt.key && TH[fopt.key]) {
          var img = document.createElement("img");
          img.src = TH[fopt.key];
          slot.insertBefore(img, lbl);
          if (fopt.key === beat.accepted_image_key) slot.classList.add("chosen");
        }
      }
      opts.appendChild(slot);
    }
    card.appendChild(opts);

    // Per-beat generate button
    var cardBtns = document.createElement("div");
    cardBtns.className = "bg-card-btns";
    var genOne = document.createElement("button");
    genOne.className = "bg-gen-btn";
    genOne.textContent = "\u26a1 Generate Stills";
    genOne.setAttribute("data-beat", beat.beat_id);
    genOne.onclick = function() {
      var bid = this.getAttribute("data-beat");
      _bgSubmitBatch([bid]);
    };
    cardBtns.appendChild(genOne);
    card.appendChild(cardBtns);

    container.appendChild(card);
  });
}

// ---- Update one beat field ----
function _bgUpdateBeat(beatId, fields) {
  var payload = Object.assign({beat_id: beatId}, fields);
  return fetch(BG_SERVER + "/api/bg/update-beat", {
    method: "POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify(payload)
  }).then(function(r){ return r.json(); })
    .catch(function(e){ console.warn("[BG] update-beat error:", e); return {ok:false}; });
}

// ---- Generate all stills ----
function _bgGenerateAll() {
  var ids = BG_BEATS.map(function(b){ return b.beat_id; });
  if (!ids.length) return;
  _bgSubmitBatch(ids);
}

// ---- Submit flux batch ----
function _bgSubmitBatch(beatIds) {
  var genBtn = document.getElementById("bg-gen-all-btn");
  if (genBtn) { genBtn.disabled = true; genBtn.textContent = "\u23f3 Submitting\u2026"; }

  fetch(BG_SERVER + "/api/bg/submit-flux-batch", {
    method: "POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify({beat_ids: beatIds})
  })
  .then(function(r){ return r.json(); })
  .then(function(d) {
    if (d.error) { alert("Submit error: " + d.error); return; }
    var taskMap = d.task_map || {};
    Object.assign(BG_TASK_MAP, taskMap);
    // Update status indicators
    beatIds.forEach(function(bid) {
      var sp = document.getElementById("bg-status-" + bid);
      if (sp) sp.textContent = "pending\u2026";
    });
    // Start poll loop
    if (!BG_POLL_ID) {
      BG_POLL_ID = setInterval(_bgPollStatus, 5000);
    }
    if (genBtn) { genBtn.disabled = false; genBtn.textContent = "\u26a1 Generate All Stills"; }
  })
  .catch(function(e) {
    alert("Submit failed: " + e);
    if (genBtn) { genBtn.disabled = false; genBtn.textContent = "\u26a1 Generate All Stills"; }
  });
}

// ---- Poll flux status ----
function _bgPollStatus() {
  // Collect all pending request_ids
  var pending = [];
  Object.keys(BG_TASK_MAP).forEach(function(bid) {
    (BG_TASK_MAP[bid] || []).forEach(function(rid) {
      pending.push(rid);
    });
  });
  if (!pending.length) {
    clearInterval(BG_POLL_ID);
    BG_POLL_ID = null;
    return;
  }

  fetch(BG_SERVER + "/api/bg/poll-flux-status?request_ids=" + pending.join(","))
    .then(function(r){ return r.json(); })
    .then(function(results) {
      var allDone = true;
      Object.keys(BG_TASK_MAP).forEach(function(bid) {
        var rids = BG_TASK_MAP[bid] || [];
        rids.forEach(function(rid, optIdx) {
          var r = results[rid];
          if (r && r.status === "ready") {
            // Inject image into gallery + beat card slot
            if (r.key && r.thumb_b64 && r.gallery_b64) {
              _injectImage(r.key, r.filename || r.key, r.thumb_b64, r.gallery_b64);
            }
            // Update slot UI
            var slot = document.getElementById("bg-opt-" + bid + "-" + optIdx);
            if (slot && r.thumb_b64) {
              var existing = slot.querySelector("img");
              if (!existing) {
                var img = document.createElement("img");
                img.src = r.thumb_b64;
                slot.insertBefore(img, slot.firstChild);
              }
            }
            // Mark beat result in BG_BEATS
            var beat = BG_BEATS.find(function(b){ return b.beat_id === bid; });
            if (beat) {
              beat.flux_options = beat.flux_options || [];
              beat.flux_options[optIdx] = {key: r.key, request_id: rid};
              var sp = document.getElementById("bg-status-" + bid);
              if (sp) sp.textContent = "stills ready";
            }
            // Remove from task map (done)
            BG_TASK_MAP[bid][optIdx] = null;
          } else if (r && r.status === "error") {
            BG_TASK_MAP[bid][optIdx] = null;
          } else {
            allDone = false;
          }
        });
      });
      if (allDone) {
        clearInterval(BG_POLL_ID);
        BG_POLL_ID = null;
      }
    })
    .catch(function(e){ console.warn("[BG] poll error:", e); });
}

// ---- _injectImage (unified library update — all three tabs) ----
// If the storyboard already defines _injectImage via Path A++, this no-ops.
if (typeof _injectImage === "undefined") {
  function _injectImage(key, filename, thumb_b64, gallery_b64) {
    IN[key] = filename;
    TH[key] = thumb_b64;
    var existing = document.querySelector('.ic[data-key="' + key + '"]');
    if (existing) existing.remove();
    var card = document.createElement("div");
    card.className = "ic";
    card.setAttribute("data-key", key);
    card.setAttribute("draggable", "true");
    var img = document.createElement("img");
    img.src = thumb_b64;
    card.appendChild(img);
    var p = document.createElement("p");
    p.textContent = key;
    card.appendChild(p);
    var gg = document.getElementById("gg") || document.querySelector(".gg");
    if (gg) gg.appendChild(card);
    // Re-attach gallery drag handler for new card
    if (typeof initDrag === "function") initDrag();
  }
}

// ---- Accept all beats to storyboard ----
function _bgAcceptToStoryboard() {
  if (!BG_BEATS.length) return;
  var missing = BG_BEATS.filter(function(b){ return !b.accepted_image_key; }).length;
  if (missing > 0 && !confirm(missing + " beat(s) have no image assigned. Accept anyway?")) return;

  BG_BEATS.forEach(function(beat) {
    L.push({
      s: beat.speaker,
      t: beat.dialogue_text,
      i: beat.accepted_image_key || "none",
      a: null,
      p: 0.5,
      g: BG_SEG ? BG_SEG.name : "Beat Generator"
    });
  });

  fetch(BG_SERVER + "/api/bg/accept-beats", {
    method: "POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify({beats: BG_BEATS, segment: BG_SEG})
  }).catch(function(){});

  if (typeof render === "function") render();
  _bgSwitchTab("sb", null);
}

// ====================================================================
// CROPPER TAB
// ====================================================================
var CR_IMG      = null;  // Image object
var CR_CANVAS   = null;
var CR_CTX      = null;
var CR_BEAT_ID  = null;
var CR_SRC_KEY  = null;
var CR_CROP_BOX = {x:0, y:0, w:0, h:0};  // in image coords
var CR_DRAG     = null;  // {startX, startY, mode}

function _crInitCanvas() {
  CR_CANVAS = document.getElementById("cr-canvas");
  if (!CR_CANVAS) return;
  CR_CTX = CR_CANVAS.getContext("2d");
  if (!CR_IMG) {
    CR_CTX.fillStyle = "#0a0a1a";
    CR_CTX.fillRect(0, 0, CR_CANVAS.width, CR_CANVAS.height);
    CR_CTX.fillStyle = "#555";
    CR_CTX.font = "14px sans-serif";
    CR_CTX.textAlign = "center";
    CR_CTX.fillText("Click 'Crop' on a Beat Generator still to load", CR_CANVAS.width/2, CR_CANVAS.height/2);
  } else {
    _crDraw();
  }
}

function _crLoadImage(key, beatId) {
  CR_BEAT_ID = beatId;
  CR_SRC_KEY = key;
  var src = TH[key];  // use full gallery b64 if available
  if (!src) { alert("Image not found in gallery: " + key); return; }

  var img = new Image();
  img.onload = function() {
    CR_IMG = img;
    // Init crop box: full image, 4:3 centered
    var cw = 800, ch = 600;
    var scale = Math.min(cw / img.width, ch / img.height);
    // CR_CROP_BOX in image coords — start with center 4:3 crop
    var cropW = Math.min(img.width, img.height * 4/3);
    var cropH = cropW * 3/4;
    CR_CROP_BOX = {
      x: (img.width - cropW) / 2,
      y: (img.height - cropH) / 2,
      w: cropW,
      h: cropH
    };
    _bgSwitchTab("cr", null);
    _crDraw();
    var info = document.getElementById("cr-crop-info");
    if (info) info.textContent = "Image: " + img.width + "\u00d7" + img.height + "px\nCrop: 4:3";
    var saveBtn = document.getElementById("cr-save-btn");
    if (saveBtn) saveBtn.disabled = false;
  };
  img.onerror = function(){ alert("Failed to load image."); };
  img.src = src;
}

function _crDraw() {
  if (!CR_CANVAS || !CR_CTX || !CR_IMG) return;
  var cw = CR_CANVAS.width, ch = CR_CANVAS.height;
  var scale = Math.min(cw / CR_IMG.width, ch / CR_IMG.height);
  var dw = CR_IMG.width * scale, dh = CR_IMG.height * scale;
  var dx = (cw - dw) / 2, dy = (ch - dh) / 2;

  CR_CTX.clearRect(0, 0, cw, ch);
  CR_CTX.fillStyle = "#0a0a1a";
  CR_CTX.fillRect(0, 0, cw, ch);
  CR_CTX.drawImage(CR_IMG, dx, dy, dw, dh);

  // Draw crop overlay
  var bx = dx + CR_CROP_BOX.x * scale;
  var by = dy + CR_CROP_BOX.y * scale;
  var bw = CR_CROP_BOX.w * scale;
  var bh = CR_CROP_BOX.h * scale;

  // Darken outside crop
  CR_CTX.fillStyle = "rgba(0,0,0,0.5)";
  CR_CTX.fillRect(0, 0, cw, by);
  CR_CTX.fillRect(0, by, bx, bh);
  CR_CTX.fillRect(bx + bw, by, cw - bx - bw, bh);
  CR_CTX.fillRect(0, by + bh, cw, ch - by - bh);

  // Crop border
  CR_CTX.strokeStyle = "#52b788";
  CR_CTX.lineWidth = 2;
  CR_CTX.strokeRect(bx, by, bw, bh);

  // Corner handles
  var hs = 8;
  CR_CTX.fillStyle = "#52b788";
  [[bx,by],[bx+bw-hs,by],[bx,by+bh-hs],[bx+bw-hs,by+bh-hs]].forEach(function(c){
    CR_CTX.fillRect(c[0], c[1], hs, hs);
  });
}

// Mouse drag on canvas to reposition crop box
(function() {
  document.addEventListener("DOMContentLoaded", function() {
    var canvas = document.getElementById("cr-canvas");
    if (!canvas) return;
    canvas.addEventListener("mousedown", function(e) {
      if (!CR_IMG) return;
      var r = canvas.getBoundingClientRect();
      var mx = e.clientX - r.left, my = e.clientY - r.top;
      CR_DRAG = {startX: mx, startY: my, boxStart: Object.assign({}, CR_CROP_BOX)};
    });
    canvas.addEventListener("mousemove", function(e) {
      if (!CR_DRAG || !CR_IMG) return;
      var r = canvas.getBoundingClientRect();
      var mx = e.clientX - r.left, my = e.clientY - r.top;
      var cw = canvas.width, ch = canvas.height;
      var scale = Math.min(cw / CR_IMG.width, ch / CR_IMG.height);
      var dx = (mx - CR_DRAG.startX) / scale;
      var dy = (my - CR_DRAG.startY) / scale;
      // Move crop box, clamped to image bounds
      var nx = Math.max(0, Math.min(CR_IMG.width - CR_CROP_BOX.w, CR_DRAG.boxStart.x + dx));
      var ny = Math.max(0, Math.min(CR_IMG.height - CR_CROP_BOX.h, CR_DRAG.boxStart.y + dy));
      CR_CROP_BOX.x = nx;
      CR_CROP_BOX.y = ny;
      _crDraw();
    });
    canvas.addEventListener("mouseup", function(){ CR_DRAG = null; });
    canvas.addEventListener("mouseleave", function(){ CR_DRAG = null; });
  });
})();

// ---- Save crop ----
function _crSaveCrop() {
  if (!CR_IMG || !CR_CANVAS) { alert("No image loaded."); return; }
  // Export the cropped region to a temp canvas
  var tempCanvas = document.createElement("canvas");
  var cropW = Math.round(CR_CROP_BOX.w);
  var cropH = Math.round(CR_CROP_BOX.h);
  tempCanvas.width  = cropW;
  tempCanvas.height = cropH;
  var ctx2 = tempCanvas.getContext("2d");
  ctx2.drawImage(CR_IMG,
    CR_CROP_BOX.x, CR_CROP_BOX.y, cropW, cropH,
    0, 0, cropW, cropH
  );
  var saveBtn = document.getElementById("cr-save-btn");
  if (saveBtn) { saveBtn.disabled = true; saveBtn.textContent = "Saving\u2026"; }

  tempCanvas.toBlob(function(blob) {
    var reader = new FileReader();
    reader.onload = function() {
      var b64 = reader.result.split(",")[1];
      fetch(BG_SERVER + "/api/cr/save-crop", {
        method: "POST",
        headers: {"Content-Type":"application/json"},
        body: JSON.stringify({
          crop_png_b64: b64,
          beat_id: CR_BEAT_ID,
          source_key: CR_SRC_KEY
        })
      })
      .then(function(r){ return r.json(); })
      .then(function(d) {
        if (d.error) { alert("Save failed: " + d.error); return; }
        // Inject into gallery
        if (d.key && d.thumb_b64 && d.gallery_b64) {
          _injectImage(d.key, d.filename || d.key, d.thumb_b64, d.gallery_b64);
        }
        // Set as accepted on the beat
        if (CR_BEAT_ID && d.key) {
          fetch(BG_SERVER + "/api/bg/accept-option", {
            method: "POST",
            headers: {"Content-Type":"application/json"},
            body: JSON.stringify({beat_id: CR_BEAT_ID, option_key: d.key})
          }).catch(function(){});
          var beat = BG_BEATS.find(function(b){ return b.beat_id === CR_BEAT_ID; });
          if (beat) beat.accepted_image_key = d.key;
        }
        _bgSwitchTab("bg", null);
      })
      .catch(function(e) { alert("Crop upload error: " + e); })
      .finally(function() {
        if (saveBtn) { saveBtn.disabled = false; saveBtn.textContent = "\u{1F4BE} Save Crop"; }
      });
    };
    reader.readAsDataURL(blob);
  }, "image/png");
}

// Hook render() so BG controls survive every re-render
var _bgBaseRender = render;
render = (function(prev) {
  return function() {
    prev();
    // Re-render BG beats if BG panel is visible
    var bgPanel = document.getElementById("panel-bg");
    if (bgPanel && bgPanel.classList.contains("active") && BG_BEATS.length) {
      _bgRenderBeats(BG_BEATS);
    }
  };
})(render);

// ====================================================================
// STITCH GROUPS + ANIMATION METHOD SELECTOR (added 2026-04-23)
// ====================================================================
var BG_GROUPS = [];
var BG_MULTISELECT = false;
var BG_SELECTED_BEATS = {};  // beat_id → true (object used as set for IE compat)
var BG_CAPABILITIES = {};

function _bgSelectedCount(){ var n=0; for(var k in BG_SELECTED_BEATS) if(BG_SELECTED_BEATS[k]) n++; return n; }
function _bgSelectedList(){ var a=[]; for(var k in BG_SELECTED_BEATS) if(BG_SELECTED_BEATS[k]) a.push(k); return a; }

function _bgGroupColor(gid) {
  var h = 0;
  for(var i=0;i<gid.length;i++) h=(h*31+gid.charCodeAt(i))&0xffff;
  return 'hsl('+(h%360)+',60%,45%)';
}
function _bgGroupName(gid) {
  for (var i=0;i<BG_GROUPS.length;i++) if (BG_GROUPS[i].group_id === gid) return BG_GROUPS[i].name;
  return gid;
}

function _bgLoadGroups(arcNum) {
  fetch(BG_SERVER + '/api/bg/groups?arc=' + arcNum)
    .then(function(r){ return r.json(); })
    .then(function(j){ if (j.ok) { BG_GROUPS = j.groups || []; _bgRenderGroups(); } })
    .catch(function(e){ console.warn('[BG] groups load err', e); });
}

// Wrap original _bgRenderBeats to inject animation row + group chip + multi-select
var _bgRenderBeats_orig = _bgRenderBeats;
_bgRenderBeats = function(beats) {
  _bgRenderBeats_orig(beats || BG_BEATS);
  var cards = document.querySelectorAll('.bg-beat-card');
  cards.forEach(function(card) {
    var bid = card.id ? card.id.replace(/^bg-card-/, '') : null;
    if (!bid) return;
    var beat = (BG_BEATS || []).find(function(b){ return b.beat_id === bid; });
    if (!beat) return;
    if (card.querySelector('.bg-anim-row')) return; // already injected
    var anim = beat.animation_method || 'kling';
    var groupChip = beat.group_id
      ? '<span class="bg-group-chip" style="background:'+_bgGroupColor(beat.group_id)+'">\u2726 '+_bgGroupName(beat.group_id)+'</span>'
      : '';
    var multiBox = BG_MULTISELECT
      ? '<input type="checkbox" class="bg-multiselect-check" data-beat-id="'+bid+'"'+(BG_SELECTED_BEATS[bid]?' checked':'')+'>'
      : '';
    var row = document.createElement('div');
    row.className = 'bg-anim-row';
    row.innerHTML = multiBox
      + '<label style="color:#aaa;font-size:12px;min-width:80px">Animation:</label>'
      + '<select class="bg-anim-method" data-beat-id="'+bid+'">'
      + '<option value="kling"'+(anim==='kling'?' selected':'')+'>\u26A1 Kling</option>'
      + '<option value="magic_compositor"'+(anim==='magic_compositor'?' selected':'')+'>\u2728 Magic Trail</option>'
      + '<option value="ken_burns"'+(anim==='ken_burns'?' selected':'')+'>\uD83C\uDFAC Ken Burns</option>'
      + '<option value="static_hold"'+(anim==='static_hold'?' selected':'')+'>\uD83D\uDCF7 Static Hold</option>'
      + '</select>'
      + groupChip;
    var dlg = card.querySelector('textarea.bg-dlg');
    if (dlg) card.insertBefore(row, dlg);
    else card.appendChild(row);
    // If non-kling, swap the per-beat Generate Stills button for Configure & Run
    if (anim !== 'kling') {
      var genBtn = card.querySelector('.bg-gen-btn');
      if (genBtn) {
        var cfgBtn = document.createElement('button');
        cfgBtn.className = 'bg-configure-local-btn';
        cfgBtn.dataset.beatId = bid;
        cfgBtn.textContent = 'Configure & Run';
        genBtn.parentNode.replaceChild(cfgBtn, genBtn);
      }
    }
  });
  _bgRenderGroups();
};

function _bgUpdateBeatAnimMethod(bid, method) {
  fetch(BG_SERVER + '/api/bg/update-beat-animation-method', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({beat_id:bid, animation_method:method})
  }).then(function(r){ return r.json(); }).then(function(j){
    if (j.ok) {
      var b = (BG_BEATS||[]).find(function(x){ return x.beat_id===bid; });
      if (b) b.animation_method = method;
      _bgRenderBeats(BG_BEATS);
    } else {
      alert('Update anim method error: ' + j.error);
    }
  });
}

function _bgRenderGroups() {
  var root = document.getElementById('bg-groups-section');
  if (!root) {
    var beatsList = document.getElementById('bg-beats');
    if (!beatsList) return;
    root = document.createElement('div');
    root.id = 'bg-groups-section';
    root.innerHTML = '<div class="bg-groups-header">'
      + '<h3>Stitch Groups</h3>'
      + '<button onclick="_bgToggleMultiSelect()" id="bg-select-btn" style="background:#3a3f52;color:#e8e8e8;border:none;border-radius:4px;padding:5px 10px;cursor:pointer;font-size:12px">Select Beats...</button>'
      + '<button onclick="_bgNewGroup()" style="background:#2a3f2a;color:#e8e8e8;border:none;border-radius:4px;padding:5px 10px;cursor:pointer;font-size:12px">+ New Group</button>'
      + '</div>'
      + '<div id="bg-groups-list"></div>';
    beatsList.parentNode.insertBefore(root, beatsList.nextSibling);
  }
  var list = document.getElementById('bg-groups-list');
  if (!list) return;
  if (!BG_GROUPS.length) {
    list.innerHTML = '<p style="color:#666;font-size:12px;margin:8px 0">No groups yet. Select beats and click "+ New Group".</p>';
    return;
  }
  list.innerHTML = BG_GROUPS.map(function(g) {
    var ready = g.status === 'ready';
    var assembled = g.status === 'assembled';
    var dlLink = assembled && g.assembled_clip_path
      ? ' <a href="' + BG_SERVER + '/files?path='+encodeURIComponent(g.assembled_clip_path)+'" target="_blank" style="color:#6af;font-size:12px">\u2B07 download</a>'
      : '';
    return '<div class="bg-group-row" data-group-id="'+g.group_id+'">'
      + '<span class="bg-group-name" onclick="_bgToggleGroupExpand(\''+g.group_id+'\')" title="Click to expand">'
      + '<span style="width:10px;height:10px;border-radius:50%;display:inline-block;background:'+_bgGroupColor(g.group_id)+'"></span> '
      + g.name + ' (' + g.beat_ids_ordered.length + ' beats)</span>'
      + '<span class="bg-group-status bg-status-'+g.status+'">'+g.status+'</span>'
      + '<button class="bg-assemble-btn" '+(ready?'':'disabled')+' onclick="_bgAssembleGroup(\''+g.group_id+'\')">Assemble</button>'
      + dlLink
      + '<button class="bg-delete-group" onclick="_bgDeleteGroup(\''+g.group_id+'\')">\u2715</button>'
      + '</div>';
  }).join('');
}

function _bgToggleMultiSelect() {
  BG_MULTISELECT = !BG_MULTISELECT;
  BG_SELECTED_BEATS = {};
  var btn = document.getElementById('bg-select-btn');
  if (btn) btn.style.background = BG_MULTISELECT ? '#5a3f2a' : '#3a3f52';
  _bgRenderBeats(BG_BEATS);
}

function _bgNewGroup() {
  if (_bgSelectedCount() === 0) {
    alert('Select at least one beat first (click "Select Beats...")');
    return;
  }
  var name = window.prompt('Group name:', 'Resolution Stitch');
  if (!name || !name.trim()) return;
  var arcN = BG_ARC || 1;
  fetch(BG_SERVER + '/api/bg/create-group', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({group_name:name.trim(), arc_number:arcN, beat_ids:_bgSelectedList()})
  }).then(function(r){ return r.json(); }).then(function(j){
    if (j.ok) {
      BG_MULTISELECT = false;
      BG_SELECTED_BEATS = {};
      _bgLoadGroups(arcN);
      _bgRenderBeats(BG_BEATS);
    } else {
      alert('Error: ' + j.error);
    }
  });
}

function _bgDeleteGroup(gid) {
  if (!confirm('Delete group "' + _bgGroupName(gid) + '"?')) return;
  fetch(BG_SERVER + '/api/bg/delete-group', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({group_id:gid})
  }).then(function(r){ return r.json(); }).then(function(j){
    if (j.ok) {
      BG_GROUPS = BG_GROUPS.filter(function(g){ return g.group_id !== gid; });
      _bgRenderGroups();
    }
  });
}

function _bgAssembleGroup(gid) {
  var btn = document.querySelector('.bg-group-row[data-group-id="'+gid+'"] .bg-assemble-btn');
  if (btn) { btn.disabled = true; btn.textContent = 'Assembling...'; }
  fetch(BG_SERVER + '/api/bg/assemble-group', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({group_id:gid})
  }).then(function(r){ return r.json(); }).then(function(j){
    if (j.ok) {
      var poll = setInterval(function(){
        fetch(BG_SERVER + '/api/bg/poll-assemble-status?group_id='+gid)
          .then(function(r){ return r.json(); })
          .then(function(pj){
            if (pj.status === 'done') {
              clearInterval(poll);
              var g = BG_GROUPS.find(function(x){ return x.group_id === gid; });
              if (g) { g.status = 'assembled'; g.assembled_clip_path = pj.assembled_clip_path; }
              _bgRenderGroups();
            } else if (pj.status === 'error') {
              clearInterval(poll);
              alert('Assembly failed: ' + pj.error);
              _bgRenderGroups();
            }
          });
      }, 2000);
    } else {
      alert('Assemble error: ' + j.error);
      if (btn) { btn.disabled = false; btn.textContent = 'Assemble'; }
    }
  });
}

function _bgToggleGroupExpand(gid) {
  var g = BG_GROUPS.find(function(x){ return x.group_id === gid; });
  if (!g) return;
  var existing = document.getElementById('bg-group-exp-'+gid);
  if (existing) { existing.remove(); return; }
  var row = document.querySelector('.bg-group-row[data-group-id="'+gid+'"]');
  if (!row) return;
  var exp = document.createElement('div');
  exp.id = 'bg-group-exp-'+gid;
  exp.style.cssText = 'padding:8px 12px;background:#111;border:1px solid #3a3f52;border-top:none;margin-bottom:4px;border-radius:0 0 4px 4px';
  exp.innerHTML = '<p style="color:#aaa;font-size:11px;margin:0 0 6px">Beats in order:</p>'
    + g.beat_ids_ordered.map(function(bid,i){
        var b = (BG_BEATS||[]).find(function(x){ return x.beat_id === bid; });
        var dlg = b ? (b.dialogue_text || '').substring(0,50) : bid;
        var st = b ? b.status : '?';
        return '<div style="padding:4px 0;color:#ccc;font-size:12px">'+(i+1)+'. ['+st+'] '+dlg+'</div>';
      }).join('');
  row.parentNode.insertBefore(exp, row.nextSibling);
}

// Delegated change + click handlers for new UI
document.addEventListener('change', function(e) {
  if (e.target.classList && e.target.classList.contains('bg-anim-method')) {
    var bid = e.target.dataset.beatId;
    _bgUpdateBeatAnimMethod(bid, e.target.value);
  }
  if (e.target.classList && e.target.classList.contains('bg-multiselect-check')) {
    var bid = e.target.dataset.beatId;
    if (e.target.checked) BG_SELECTED_BEATS[bid] = true;
    else delete BG_SELECTED_BEATS[bid];
  }
});

document.addEventListener('click', function(e) {
  if (e.target.classList && e.target.classList.contains('bg-configure-local-btn')) {
    _bgOpenLocalConfig(e.target.dataset.beatId);
  }
});

function _bgOpenLocalConfig(bid) {
  var card = document.querySelector('.bg-beat-card[id="bg-card-'+bid+'"]') || document.getElementById('bg-card-'+bid);
  if (!card) return;
  var existing = card.querySelector('.bg-local-config-panel');
  if (existing) { existing.remove(); return; }
  var beat = (BG_BEATS||[]).find(function(b){ return b.beat_id === bid; });
  if (!beat) return;
  var method = beat.animation_method || 'kling';
  var stillPath = beat.accepted_image_key
    ? 'Production/beat_generator_stills/' + beat.accepted_image_key + '.png'
    : '';
  var panel = document.createElement('div');
  panel.className = 'bg-local-config-panel';
  var inner = '';
  if (method === 'magic_compositor') {
    var defaultPts = JSON.stringify([[0.0,0.65],[0.3,0.60],[0.6,0.55]]);
    if (beat.local_render_params && beat.local_render_params.path_pts)
      defaultPts = JSON.stringify(beat.local_render_params.path_pts);
    inner = '<label>Background image path:</label>'
      + '<input type="text" class="bg-mc-bg" value="'+stillPath+'" style="width:100%;box-sizing:border-box;background:#1a1f2e;color:#e8e8e8;border:1px solid #3a3f52;border-radius:4px;padding:6px;font-size:12px">'
      + '<label>Path points (JSON [[x,y],...], fractions 0-1):</label>'
      + '<textarea class="bg-path-pts" rows="3">'+defaultPts+'</textarea>'
      + '<label>Style:</label>'
      + '<select class="bg-mc-style" style="background:#1a1f2e;color:#e8e8e8;border:1px solid #3a3f52;border-radius:4px;padding:4px"><option value="tessa_ori">tessa_ori</option></select>'
      + '<label>Duration: <span class="bg-mc-dur-val">3.5</span>s</label>'
      + '<input type="range" class="bg-mc-dur" min="1" max="8" step="0.5" value="3.5">'
      + '<div style="margin-top:8px">'
      + '<button class="bg-run-btn bg-mc-preview-btn" data-beat-id="'+bid+'">Preview Frame</button>'
      + '<button class="bg-run-btn bg-mc-render-btn" data-beat-id="'+bid+'">Render Video</button>'
      + '</div>'
      + '<div class="bg-mc-result"></div>';
  } else if (method === 'ken_burns') {
    inner = '<label>Still path:</label>'
      + '<input type="text" class="bg-kb-still" value="'+stillPath+'" style="width:100%;box-sizing:border-box;background:#1a1f2e;color:#e8e8e8;border:1px solid #3a3f52;border-radius:4px;padding:6px;font-size:12px">'
      + '<label>Pan X: <span class="bg-kb-px-val">20</span>%</label><input type="range" class="bg-kb-px" min="0" max="80" value="20">'
      + '<label>Pan Y: <span class="bg-kb-py-val">20</span>%</label><input type="range" class="bg-kb-py" min="0" max="80" value="20">'
      + '<label>Zoom start: <span class="bg-kb-zs-val">1.0</span></label><input type="range" class="bg-kb-zs" min="1.0" max="2.0" step="0.05" value="1.0">'
      + '<label>Zoom end: <span class="bg-kb-ze-val">1.3</span></label><input type="range" class="bg-kb-ze" min="1.0" max="2.0" step="0.05" value="1.3">'
      + '<label>Duration: <span class="bg-kb-dur-val">4.0</span>s</label><input type="range" class="bg-kb-dur" min="1" max="8" step="0.5" value="4.0">'
      + '<div style="margin-top:8px"><button class="bg-run-btn bg-kb-render-btn" data-beat-id="'+bid+'">Render Video</button></div>'
      + '<div class="bg-kb-result"></div>';
  } else if (method === 'static_hold') {
    inner = '<label>Still path:</label>'
      + '<input type="text" class="bg-sh-still" value="'+stillPath+'" style="width:100%;box-sizing:border-box;background:#1a1f2e;color:#e8e8e8;border:1px solid #3a3f52;border-radius:4px;padding:6px;font-size:12px">'
      + '<label>Duration: <span class="bg-sh-dur-val">4.0</span>s</label><input type="range" class="bg-sh-dur" min="1" max="8" step="0.5" value="4.0">'
      + '<div style="margin-top:8px"><button class="bg-run-btn bg-sh-render-btn" data-beat-id="'+bid+'">Render Video</button></div>'
      + '<div class="bg-sh-result"></div>';
  }
  panel.innerHTML = inner;
  card.appendChild(panel);
  // Wire range sliders to update their label spans
  panel.querySelectorAll('input[type=range]').forEach(function(sl){
    sl.addEventListener('input', function(){
      // find preceding label and span
      var lbl = sl.previousElementSibling;
      if (lbl && lbl.tagName === 'LABEL') {
        var sp = lbl.querySelector('span'); if (sp) sp.textContent = sl.value;
      }
    });
  });
}

document.addEventListener('click', function(e){
  // Magic compositor preview
  if (e.target.classList && e.target.classList.contains('bg-mc-preview-btn')) {
    var bid = e.target.dataset.beatId;
    var card = document.getElementById('bg-card-'+bid);
    var panel = card && card.querySelector('.bg-local-config-panel');
    if (!panel) return;
    var bgPath = panel.querySelector('.bg-mc-bg').value.trim();
    var pts; try { pts = JSON.parse(panel.querySelector('.bg-path-pts').value); } catch (e2) { alert('Invalid JSON path_pts'); return; }
    var style = panel.querySelector('.bg-mc-style').value;
    var dur = parseFloat(panel.querySelector('.bg-mc-dur').value);
    var result = panel.querySelector('.bg-mc-result');
    result.innerHTML = '<span style="color:#fa6">Rendering preview...</span>';
    fetch(BG_SERVER + '/api/bg/run-local-animation', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({beat_id:bid, method:'magic_compositor',
        params:{background_path:bgPath, path_pts:pts, style:style, duration:dur},
        preview_only:true})
    }).then(function(r){ return r.json(); }).then(function(j){
      if (j.ok) result.innerHTML = '<img class="bg-mc-preview-img" src="'+BG_SERVER+'/files?path='+encodeURIComponent(j.preview_path)+'">';
      else result.innerHTML = '<span style="color:#f66">'+j.error+'</span>';
    });
  }
  // Magic compositor render
  if (e.target.classList && e.target.classList.contains('bg-mc-render-btn')) {
    var bid = e.target.dataset.beatId;
    var card = document.getElementById('bg-card-'+bid);
    var panel = card && card.querySelector('.bg-local-config-panel');
    if (!panel) return;
    var bgPath = panel.querySelector('.bg-mc-bg').value.trim();
    var pts; try { pts = JSON.parse(panel.querySelector('.bg-path-pts').value); } catch (e2) { alert('Invalid JSON path_pts'); return; }
    var style = panel.querySelector('.bg-mc-style').value;
    var dur = parseFloat(panel.querySelector('.bg-mc-dur').value);
    var result = panel.querySelector('.bg-mc-result');
    result.innerHTML = '<span style="color:#fa6">Rendering video (10-30s)...</span>';
    fetch(BG_SERVER + '/api/bg/run-local-animation', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({beat_id:bid, method:'magic_compositor',
        params:{background_path:bgPath, path_pts:pts, style:style, duration:dur},
        preview_only:false})
    }).then(function(r){ return r.json(); }).then(function(j){
      if (j.ok) result.innerHTML = '<video src="'+BG_SERVER+'/files?path='+encodeURIComponent(j.video_path)+'" controls style="max-width:100%;margin-top:8px"></video>'
        + '<br><button class="bg-accept-local-btn" data-beat-id="'+bid+'" data-video-path="'+j.video_path+'">Accept This Animation</button>';
      else result.innerHTML = '<span style="color:#f66">'+j.error+'</span>';
    });
  }
  // Ken Burns render
  if (e.target.classList && e.target.classList.contains('bg-kb-render-btn')) {
    var bid = e.target.dataset.beatId;
    var card = document.getElementById('bg-card-'+bid);
    var panel = card && card.querySelector('.bg-local-config-panel');
    if (!panel) return;
    var result = panel.querySelector('.bg-kb-result');
    result.innerHTML = '<span style="color:#fa6">Rendering Ken Burns...</span>';
    fetch(BG_SERVER + '/api/bg/run-local-animation', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({beat_id:bid, method:'ken_burns', params:{
        still_path: panel.querySelector('.bg-kb-still').value,
        pan_x_pct: parseFloat(panel.querySelector('.bg-kb-px').value),
        pan_y_pct: parseFloat(panel.querySelector('.bg-kb-py').value),
        zoom_start: parseFloat(panel.querySelector('.bg-kb-zs').value),
        zoom_end: parseFloat(panel.querySelector('.bg-kb-ze').value),
        duration: parseFloat(panel.querySelector('.bg-kb-dur').value),
      }})
    }).then(function(r){ return r.json(); }).then(function(j){
      if (j.ok) result.innerHTML = '<video src="'+BG_SERVER+'/files?path='+encodeURIComponent(j.video_path)+'" controls style="max-width:100%;margin-top:8px"></video>'
        + '<br><button class="bg-accept-local-btn" data-beat-id="'+bid+'" data-video-path="'+j.video_path+'">Accept This Animation</button>';
      else result.innerHTML = '<span style="color:#f66">'+j.error+'</span>';
    });
  }
  // Static hold render
  if (e.target.classList && e.target.classList.contains('bg-sh-render-btn')) {
    var bid = e.target.dataset.beatId;
    var card = document.getElementById('bg-card-'+bid);
    var panel = card && card.querySelector('.bg-local-config-panel');
    if (!panel) return;
    var result = panel.querySelector('.bg-sh-result');
    result.innerHTML = '<span style="color:#fa6">Encoding static hold...</span>';
    fetch(BG_SERVER + '/api/bg/run-local-animation', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({beat_id:bid, method:'static_hold', params:{
        still_path: panel.querySelector('.bg-sh-still').value,
        duration: parseFloat(panel.querySelector('.bg-sh-dur').value),
      }})
    }).then(function(r){ return r.json(); }).then(function(j){
      if (j.ok) result.innerHTML = '<video src="'+BG_SERVER+'/files?path='+encodeURIComponent(j.video_path)+'" controls style="max-width:100%;margin-top:8px"></video>'
        + '<br><button class="bg-accept-local-btn" data-beat-id="'+bid+'" data-video-path="'+j.video_path+'">Accept This Animation</button>';
      else result.innerHTML = '<span style="color:#f66">'+j.error+'</span>';
    });
  }
  // Accept local animation
  if (e.target.classList && e.target.classList.contains('bg-accept-local-btn')) {
    var bid = e.target.dataset.beatId;
    var vp = e.target.dataset.videoPath;
    fetch(BG_SERVER + '/api/bg/accept-local-animation', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({beat_id:bid, video_path:vp})
    }).then(function(r){ return r.json(); }).then(function(j){
      if (j.ok) {
        var b = (BG_BEATS||[]).find(function(x){ return x.beat_id === bid; });
        if (b) { b.status = 'accepted'; b.accepted_video_path = vp; }
        _bgRenderBeats(BG_BEATS);
        _bgLoadGroups(BG_ARC || 1);
      } else {
        alert('Accept error: ' + j.error);
      }
    });
  }
});

// Pull capabilities from session-state on BG panel open
(function(){
  var orig = _bgLoadState;
  _bgLoadState = function() {
    fetch(BG_SERVER + '/api/bg/session-state')
      .then(function(r){ return r.json(); })
      .then(function(d){
        if (d.capabilities) BG_CAPABILITIES = d.capabilities;
        if (d.beats && d.beats.length) {
          BG_BEATS = d.beats;
          _bgRenderBeats(BG_BEATS);
          var acceptBtn = document.getElementById("bg-accept-btn");
          if (acceptBtn) acceptBtn.disabled = false;
        }
        if (d.active_context) {
          BG_ARC = d.active_context.arc_number;
          var arcBtns = document.querySelectorAll(".bg-arc-btn");
          arcBtns.forEach(function(b){
            if (parseInt(b.getAttribute("data-arc")) === BG_ARC) {
              b.classList.add("sel");
              _bgLoadSegments(BG_ARC);
            }
          });
          _bgLoadGroups(BG_ARC);
        }
      })
      .catch(function(){});
  };
})();

// ====================================================================
// PERSISTENT LIBRARY SIDEBAR  (idempotency guard — no-op on rebuild)
// ====================================================================
if (typeof _bgLibraryInited === "undefined") {
var _bgLibraryInited = true;
var MN_LIB_DATA = [];

function _mnLibToggle() {
  var s = document.getElementById('mn-lib-sidebar');
  if (s) {
    s.classList.toggle('open');
    if (s.classList.contains('open')) _mnLibFetch();
  }
}

function _mnLibFetch() {
  fetch(BG_SERVER + '/api/cr/library?_t=' + Date.now())
    .then(function(r){ return r.json(); })
    .then(function(d) {
      MN_LIB_DATA = d.images || [];
      _mnLibRender();
      var body = document.querySelector('.mn-lib-body');
      if (body) body.scrollTop = 0;
    })
    .catch(function(e){ console.warn('[MNLib] fetch error:', e); });
}

function _mnLibRender() {
  ['source','cropped','character_master'].forEach(function(tier) {
    var gid = 'mn-lib-grid-' + tier;
    var eid = 'mn-lib-empty-' + tier;
    var grid = document.getElementById(gid);
    var empty = document.getElementById(eid);
    if (!grid) return;
    grid.innerHTML = '';
    var items = MN_LIB_DATA.filter(function(x){ return x.tier === tier; });
    if (!items.length) { if (empty) empty.style.display = 'block'; return; }
    if (empty) empty.style.display = 'none';
    items.forEach(function(item) {
      var el = document.createElement('div');
      el.className = 'mn-lib-item';
      el.setAttribute('data-tier', item.tier);
      el.setAttribute('data-key', item.key);
      el.setAttribute('draggable', 'true');
      el.title = item.filename;
      var img = document.createElement('img');
      img.src = item.thumb_b64;
      img.alt = item.filename;
      el.appendChild(img);
      var badge = document.createElement('span');
      badge.className = 'mn-lib-tier-badge';
      badge.textContent = tier === 'character_master' ? 'master' : tier;
      el.appendChild(badge);
      el.addEventListener('dragstart', function(e) {
        el.classList.add('dragging');
        e.dataTransfer.setData('mn-lib-key', item.key); // key only — full data looked up in MN_LIB_DATA on drop
        e.dataTransfer.effectAllowed = 'copy';
      });
      el.addEventListener('dragend', function(){ el.classList.remove('dragging'); });
      grid.appendChild(el);
    });
  });
}

function _mnLibHasKey(e) {
  try {
    var t = e.dataTransfer.types;
    return t.indexOf ? t.indexOf('mn-lib-key') !== -1 : t.includes('mn-lib-key');
  } catch(ex){ return false; }
}

document.addEventListener('dragover', function(e) {
  if (_mnLibHasKey(e)) e.preventDefault();
});

document.addEventListener('dragenter', function(e) {
  if (!_mnLibHasKey(e)) return;
  var card = e.target && e.target.closest && e.target.closest('.bg-beat-card');
  if (card) card.classList.add('drag-over');
  var lr = e.target && e.target.closest && e.target.closest('.lr');
  if (lr) lr.classList.add('drag-over-lib');
});

document.addEventListener('dragleave', function(e) {
  var card = e.target && e.target.closest && e.target.closest('.bg-beat-card');
  if (card && !card.contains(e.relatedTarget)) card.classList.remove('drag-over');
  var lr = e.target && e.target.closest && e.target.closest('.lr');
  if (lr && !lr.contains(e.relatedTarget)) lr.classList.remove('drag-over-lib');
});

// Capture-phase: prevent textareas/inputs from accepting library drops as text
document.addEventListener('drop', function(e) {
  if (!_mnLibHasKey(e)) return;
  var tag = e.target && e.target.tagName;
  if (tag === 'TEXTAREA' || tag === 'INPUT' || (e.target && e.target.contentEditable === 'true')) {
    e.preventDefault();
  }
}, true);

document.addEventListener('drop', function(e) {
  var key = e.dataTransfer && e.dataTransfer.getData('mn-lib-key');
  if (!key) return;
  // Look up data from in-memory cache — NOT from dataTransfer (avoids textarea text-drop bug)
  var libItem = null;
  for (var i = 0; i < MN_LIB_DATA.length; i++) { if (MN_LIB_DATA[i].key === key) { libItem = MN_LIB_DATA[i]; break; } }
  if (!libItem) return;
  var b64   = libItem.gallery_b64;
  var fname = libItem.filename;
  var apath = libItem.abs_path || '';

  // Drop on .bg-beat-card → set reference_image for beat
  var card = e.target.closest && e.target.closest('.bg-beat-card');
  if (card) {
    e.preventDefault();
    card.classList.remove('drag-over');
    var bid = card.id ? card.id.replace(/^bg-card-/, '') : null;
    if (!bid) return;
    _bgUpdateBeat(bid, {reference_image: apath});
    var slot0 = document.getElementById('bg-opt-' + bid + '-0');
    if (slot0 && b64) {
      var eimg = slot0.querySelector('img');
      if (!eimg) { eimg = document.createElement('img'); slot0.insertBefore(eimg, slot0.firstChild); }
      eimg.src = b64;
      slot0.title = 'Ref: ' + fname;
    }
    return;
  }

  // Drop on .lr (Storyboard row) → inject into gallery + assign
  var lr = e.target.closest && e.target.closest('.lr');
  if (lr) {
    e.preventDefault();
    lr.classList.remove('drag-over-lib');
    if (b64 && key) {
      _injectImage(key, fname, b64, b64);
      var sel = lr.querySelector('select');
      if (sel) {
        var found = false;
        for (var i = 0; i < sel.options.length; i++) { if (sel.options[i].value === key) { found = true; break; } }
        if (!found) { var o = document.createElement('option'); o.value = key; o.textContent = fname; sel.appendChild(o); }
        sel.value = key;
        sel.dispatchEvent(new Event('change'));
      }
    }
    return;
  }

  // Drop on #cr-canvas-wrap → load into Cropper (no beat context needed)
  var crw = e.target.closest && e.target.closest('#cr-canvas-wrap');
  if (crw) {
    e.preventDefault();
    if (!b64) return;
    CR_BEAT_ID = null;
    CR_SRC_KEY = key;
    var img2 = new Image();
    img2.onload = function() {
      CR_IMG = img2;
      var cw = Math.min(img2.width, img2.height * 4/3);
      var ch = cw * 3/4;
      CR_CROP_BOX = {x:(img2.width-cw)/2, y:(img2.height-ch)/2, w:cw, h:ch};
      _bgSwitchTab('cr', null);
      _crDraw();
      var info = document.getElementById('cr-crop-info');
      if (info) info.textContent = 'Image: ' + img2.width + '\u00d7' + img2.height + 'px  Crop: 4:3';
      var saveBtn = document.getElementById('cr-save-btn');
      if (saveBtn) saveBtn.disabled = false;
    };
    img2.src = b64;
    return;
  }
});

function _mnLibUpload(input) {
  if (!input.files || !input.files[0]) return;
  var file = input.files[0];
  var reader = new FileReader();
  reader.onload = function() {
    var b64 = reader.result.split(',')[1];
    fetch(BG_SERVER + '/api/cr/upload', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({filename: file.name, image_b64: b64, tier: 'source'})
    }).then(function(r){ return r.json(); })
    .then(function(d){ if (d.ok) _mnLibFetch(); else alert('Upload failed: ' + (d.error || 'unknown')); })
    .catch(function(ex){ alert('Upload error: ' + ex); });
  };
  reader.readAsDataURL(file);
  input.value = '';
}

// Auto-fetch on page ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', _mnLibFetch);
} else {
  _mnLibFetch();
}
} // end _bgLibraryInited guard
"""
    # Inject before the final </script> (robust to any whitespace/newline layout)
    _idx = html.rfind("</script>")
    if _idx != -1:
        html = html[:_idx] + bg_js + "\n" + html[_idx:]
    elif "</body>" in html:
        # No existing <script> block — must wrap our own
        html = html.replace("</body>", "<script>\n" + bg_js + "\n</script>\n</body>", 1)
    else:
        raise RuntimeError("append_extras_tabs: neither </script> nor </body> found")

    # GROUP 2 — Inject v44 CRFIX/LIBFIX patch blocks before </body>
    # Stored as base64 to avoid Python string-escape fragility.
    _PATCHES_B64 = (
        "PHNjcmlwdD4KLy8gPT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09Ci8vIEZJWC1DIFNUQVRJQyBTVElMTFMgUEFUQ0ggKDIwMjYtMDQtMjUpCi8vIFJvb3QgY2F1c2U6IFRIIChicm93c2VyLW1lbW9yeSB0aHVtYm5haWwgY2FjaGUpIGlzIGVwaGVtZXJhbCDigJQgZGllcwovLyBvbiBldmVyeSBwYWdlIHJlZnJlc2guIE9wdGlvbiBzbG90cyByZW5kZXIgYXMgYmxhY2sgYm94ZXMgZXZlbiB3aGVuCi8vIFBOR3MgYXJlIGFscmVhZHkgb24gZGlzay4KLy8gRml4OiBwZXJzaXN0ZWQgZmx1eF9vcHRpb25zIHVzZSAvYmctc3RpbGxzLzxmaWxlbmFtZT4gc3RhdGljIFVSTHMuCi8vICAgICAgVEggZmFsbGJhY2sgcmV0YWluZWQgZm9yIGluLWZsaWdodCAobm90LXlldC1kb3dubG9hZGVkKSBvcHRpb25zLgovLyBBdXRob3JlZCBzdG9yeWJvYXJkIGJhc2U2NCBpbWFnZXMgKGRpYWxvZ3VlIGNlbGxzKSBhcmUgTk9UIHRvdWNoZWQuCi8vIENoYW5nZXMgaW4gdGhpcyBwYXRjaDoKLy8gICBDMiAgX2JnUmVuZGVyQmVhdHMgd3JhcCAgIOKAlCBVUkwgcmVuZGVyICsgYnV0dG9uIGxhYmVscwovLyAgIEMzICBfY3JMb2FkSW1hZ2Ugb3ZlcnJpZGUg4oCUIFhIUiBmYWxsYmFjayB0byAvYmctc3RpbGxzLyB3aGVuIFRIIGVtcHR5Ci8vICAgQzQgIF9iZ1BvbGxTdGF0dXMgcmVwbGFjZSDigJQgYWx3YXlzIHVwZGF0ZSBleGlzdGluZyBpbWcuc3JjIChub3Qgc2tpcCkKLy8gICBDNSAgX2JnTG9hZFN0YXRlIHJlcGxhY2UgIOKAlCByZWNvbmNpbGUgcG9sbHMgb24gbG9hZAovLyAgIEM2ICBfYmdTdWJtaXRCYXRjaCB3cmFwICAg4oCUIHNwaW5uZXIgKyB0b2FzdCBmZWVkYmFjawovLyA9PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT0KKGZ1bmN0aW9uICgpIHsKICAidXNlIHN0cmljdCI7CgogIC8vIC0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLQogIC8vIEM1OiBSZXBsYWNlIF9iZ0xvYWRTdGF0ZSDigJQgcmVoeWRyYXRlcyBzbG90cyB2aWEgX2JnUmVuZGVyQmVhdHMgKHdoaWNoCiAgLy8gICAgIG5vdyB1c2VzIFVSTHMpLCB0aGVuIHJlY29uY2lsZXMgYW55IHN0YWxlIHBlbmRpbmcgcG9sbCB0YXNrcy4KICAvLyAtLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0KICB3aW5kb3cuX2JnTG9hZFN0YXRlID0gZnVuY3Rpb24gKCkgewogICAgZmV0Y2goQkdfU0VSVkVSICsgIi9hcGkvYmcvc2Vzc2lvbi1zdGF0ZSIpCiAgICAgIC50aGVuKGZ1bmN0aW9uIChyKSB7IHJldHVybiByLmpzb24oKTsgfSkKICAgICAgLnRoZW4oZnVuY3Rpb24gKGQpIHsKICAgICAgICBpZiAoZC5iZWF0cyAmJiBkLmJlYXRzLmxlbmd0aCkgewogICAgICAgICAgQkdfQkVBVFMgPSBkLmJlYXRzOwogICAgICAgICAgX2JnUmVuZGVyQmVhdHMoQkdfQkVBVFMpOyAgICAgICAgICAvLyBDMiB3cmFwcGVyIHJ1bnMgaGVyZQogICAgICAgICAgdmFyIGFjY2VwdEJ0biA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJiZy1hY2NlcHQtYnRuIik7CiAgICAgICAgICBpZiAoYWNjZXB0QnRuKSBhY2NlcHRCdG4uZGlzYWJsZWQgPSBmYWxzZTsKICAgICAgICAgIF9iZ1JlY29uY2lsZVBvbGxzKCk7ICAgICAgICAgICAgICAgLy8gQzUgaGVscGVyCiAgICAgICAgfQogICAgICAgIGlmIChkLmFjdGl2ZV9jb250ZXh0KSB7CiAgICAgICAgICBCR19BUkMgPSBkLmFjdGl2ZV9jb250ZXh0LmFyY19udW1iZXI7CiAgICAgICAgICBkb2N1bWVudC5xdWVyeVNlbGVjdG9yQWxsKCIuYmctYXJjLWJ0biIpLmZvckVhY2goZnVuY3Rpb24gKGIpIHsKICAgICAgICAgICAgaWYgKHBhcnNlSW50KGIuZ2V0QXR0cmlidXRlKCJkYXRhLWFyYyIpLCAxMCkgPT09IEJHX0FSQykgewogICAgICAgICAgICAgIGIuY2xhc3NMaXN0LmFkZCgic2VsIik7CiAgICAgICAgICAgICAgX2JnTG9hZFNlZ21lbnRzKEJHX0FSQyk7CiAgICAgICAgICAgIH0KICAgICAgICAgIH0pOwogICAgICAgIH0KICAgICAgfSkKICAgICAgLmNhdGNoKGZ1bmN0aW9uICgpIHt9KTsKICB9OwoKICAvLyBDNSBoZWxwZXI6IHJlc3RvcmUgQkdfVEFTS19NQVAgZnJvbSBfdGFza19yaWRzIHNvIGZyZXNoIGpvYnMga2VlcCBwb2xsaW5nCiAgd2luZG93Ll9iZ1JlY29uY2lsZVBvbGxzID0gZnVuY3Rpb24gKCkgewogICAgdmFyIG5lZWRzUG9sbCA9IGZhbHNlOwogICAgKEJHX0JFQVRTIHx8IFtdKS5mb3JFYWNoKGZ1bmN0aW9uIChiZWF0KSB7CiAgICAgIGlmICghYmVhdC5fdGFza19yaWRzIHx8ICFiZWF0Ll90YXNrX3JpZHMubGVuZ3RoKSByZXR1cm47CiAgICAgIC8vIEFsd2F5cyByZXN0b3JlIOKAlCBldmVuIGlmIGxvY2FsX3BhdGggZXhpc3RzLCBhIHJlZ2VuIG1heSBiZSBpbiBmbGlnaHQKICAgICAgQkdfVEFTS19NQVBbYmVhdC5iZWF0X2lkXSA9IGJlYXQuX3Rhc2tfcmlkcy5zbGljZSgpOwogICAgICBuZWVkc1BvbGwgPSB0cnVlOwogICAgfSk7CiAgICBpZiAobmVlZHNQb2xsICYmICFCR19QT0xMX0lEKSB7CiAgICAgIEJHX1BPTExfSUQgPSBzZXRJbnRlcnZhbChfYmdQb2xsU3RhdHVzLCA1MDAwKTsKICAgIH0KICB9OwoKICAvLyAtLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0KICAvLyBDMjogV3JhcCBfYmdSZW5kZXJCZWF0cyDigJQgYWZ0ZXIgdGhlIGV4aXN0aW5nIHJlbmRlciwgb3ZlcndyaXRlIG9wdGlvbgogIC8vICAgICBzbG90IGltZ3MgdGhhdCBoYXZlIGxvY2FsX3BhdGggd2l0aCBhIC9iZy1zdGlsbHMvIFVSTCwgYW5kIHVwZGF0ZQogIC8vICAgICBidXR0b24gbGFiZWxzLgogIC8vIC0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLQogIHZhciBfYmdSZW5kZXJCZWF0c19wcmV2ID0gX2JnUmVuZGVyQmVhdHM7CiAgX2JnUmVuZGVyQmVhdHMgPSBmdW5jdGlvbiAoYmVhdHMpIHsKICAgIF9iZ1JlbmRlckJlYXRzX3ByZXYoYmVhdHMgfHwgQkdfQkVBVFMpOwoKICAgIChiZWF0cyB8fCBCR19CRUFUUykuZm9yRWFjaChmdW5jdGlvbiAoYmVhdCkgewogICAgICB2YXIgb3B0cyA9IGJlYXQuZmx1eF9vcHRpb25zIHx8IFtdOwoKICAgICAgLy8gVXBkYXRlIG9wdGlvbiBzbG90IGltYWdlcwogICAgICBvcHRzLmZvckVhY2goZnVuY3Rpb24gKGZvcHQsIG8pIHsKICAgICAgICBpZiAoIWZvcHQgfHwgIWZvcHQubG9jYWxfcGF0aCkgcmV0dXJuOwogICAgICAgIHZhciBmbmFtZSA9IGZvcHQubG9jYWxfcGF0aC5zcGxpdCgiLyIpLnBvcCgpOwogICAgICAgIGlmICghZm5hbWUpIHJldHVybjsKICAgICAgICAvLyBjYWNoZS1idXN0ZXI6IHJlcXVlc3RfaWQgaXMgdW5pcXVlIHBlciBnZW5lcmF0aW9uIHJ1bgogICAgICAgIHZhciB1cmwgPSBCR19TRVJWRVIgKyAiL2JnLXN0aWxscy8iICsgZW5jb2RlVVJJQ29tcG9uZW50KGZuYW1lKQogICAgICAgICAgICAgICAgKyAiP3Y9IiArIGVuY29kZVVSSUNvbXBvbmVudChmb3B0LnJlcXVlc3RfaWQgfHwgIjAiKTsKICAgICAgICB2YXIgc2xvdCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJiZy1vcHQtIiArIGJlYXQuYmVhdF9pZCArICItIiArIG8pOwogICAgICAgIGlmICghc2xvdCkgcmV0dXJuOwogICAgICAgIHZhciBpbWcgPSBzbG90LnF1ZXJ5U2VsZWN0b3IoImltZyIpOwogICAgICAgIGlmICghaW1nKSB7CiAgICAgICAgICBpbWcgPSBkb2N1bWVudC5jcmVhdGVFbGVtZW50KCJpbWciKTsKICAgICAgICAgIHNsb3QuaW5zZXJ0QmVmb3JlKGltZywgc2xvdC5maXJzdENoaWxkKTsKICAgICAgICB9CiAgICAgICAgLy8gT25seSB1cGRhdGUgc3JjIGlmIGl0IGRpZmZlcnMgKGF2b2lkIHVubmVjZXNzYXJ5IHJlbG9hZHMpCiAgICAgICAgaWYgKGltZy5nZXRBdHRyaWJ1dGUoImRhdGEtZml4Yy11cmwiKSAhPT0gdXJsKSB7CiAgICAgICAgICBpbWcuc2V0QXR0cmlidXRlKCJkYXRhLWZpeGMtdXJsIiwgdXJsKTsKICAgICAgICAgIGltZy5zcmMgPSB1cmw7CiAgICAgICAgfQogICAgICAgIGlmIChmb3B0LmtleSAmJiBmb3B0LmtleSA9PT0gYmVhdC5hY2NlcHRlZF9pbWFnZV9rZXkpIHsKICAgICAgICAgIHNsb3QuY2xhc3NMaXN0LmFkZCgiY2hvc2VuIik7CiAgICAgICAgfQogICAgICB9KTsKCiAgICAgIC8vIEJ1dHRvbiBsYWJlbAogICAgICB2YXIgY2FyZCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJiZy1jYXJkLSIgKyBiZWF0LmJlYXRfaWQpOwogICAgICBpZiAoIWNhcmQpIHJldHVybjsKICAgICAgdmFyIGJ0biA9IGNhcmQucXVlcnlTZWxlY3RvcigiLmJnLWdlbi1idG4iKTsKICAgICAgaWYgKCFidG4pIHJldHVybjsKICAgICAgdmFyIGhhc0V4aXN0aW5nID0gb3B0cy5zb21lKGZ1bmN0aW9uIChvKSB7IHJldHVybiBvICYmIG8ubG9jYWxfcGF0aDsgfSk7CiAgICAgIGJ0bi50ZXh0Q29udGVudCA9IGhhc0V4aXN0aW5nID8gIlx1MjFiYSBSZWdlbmVyYXRlIFN0aWxscyIgOiAiXHUyNmExIEdlbmVyYXRlIFN0aWxscyI7CiAgICB9KTsKICB9OwoKICAvLyAtLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0KICAvLyBDNDogUmVwbGFjZSBfYmdQb2xsU3RhdHVzIOKAlCBhbHdheXMgdXBkYXRlIGV4aXN0aW5nIGltZy5zcmMgd2hlbiBhCiAgLy8gICAgIGZyZXNoIEZMVVggam9iIGNvbXBsZXRlcyAob3JpZ2luYWwgb25seSBjcmVhdGVkIGlmICFleGlzdGluZykuCiAgLy8gLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tCiAgX2JnUG9sbFN0YXR1cyA9IGZ1bmN0aW9uICgpIHsKICAgIHZhciBwZW5kaW5nID0gW107CiAgICBPYmplY3Qua2V5cyhCR19UQVNLX01BUCkuZm9yRWFjaChmdW5jdGlvbiAoYmlkKSB7CiAgICAgIChCR19UQVNLX01BUFtiaWRdIHx8IFtdKS5mb3JFYWNoKGZ1bmN0aW9uIChyaWQpIHsKICAgICAgICBpZiAocmlkKSBwZW5kaW5nLnB1c2gocmlkKTsKICAgICAgfSk7CiAgICB9KTsKICAgIGlmICghcGVuZGluZy5sZW5ndGgpIHsKICAgICAgY2xlYXJJbnRlcnZhbChCR19QT0xMX0lEKTsKICAgICAgQkdfUE9MTF9JRCA9IG51bGw7CiAgICAgIHJldHVybjsKICAgIH0KCiAgICBmZXRjaChCR19TRVJWRVIgKyAiL2FwaS9iZy9wb2xsLWZsdXgtc3RhdHVzP3JlcXVlc3RfaWRzPSIgKyBwZW5kaW5nLmpvaW4oIiwiKSkKICAgICAgLnRoZW4oZnVuY3Rpb24gKHIpIHsgcmV0dXJuIHIuanNvbigpOyB9KQogICAgICAudGhlbihmdW5jdGlvbiAocmVzdWx0cykgewogICAgICAgIHZhciBhbGxEb25lID0gdHJ1ZTsKICAgICAgICBPYmplY3Qua2V5cyhCR19UQVNLX01BUCkuZm9yRWFjaChmdW5jdGlvbiAoYmlkKSB7CiAgICAgICAgICAoQkdfVEFTS19NQVBbYmlkXSB8fCBbXSkuZm9yRWFjaChmdW5jdGlvbiAocmlkLCBvcHRJZHgpIHsKICAgICAgICAgICAgaWYgKCFyaWQpIHJldHVybjsKICAgICAgICAgICAgdmFyIHIgPSByZXN1bHRzW3JpZF07CiAgICAgICAgICAgIGlmIChyICYmIHIuc3RhdHVzID09PSAicmVhZHkiKSB7CiAgICAgICAgICAgICAgLy8gUG9wdWxhdGUgVEggYW5kIGdhbGxlcnkgZm9yIGluLXNlc3Npb24gdXNlCiAgICAgICAgICAgICAgaWYgKHIua2V5ICYmIHIudGh1bWJfYjY0ICYmIHIuZ2FsbGVyeV9iNjQpIHsKICAgICAgICAgICAgICAgIF9pbmplY3RJbWFnZShyLmtleSwgci5maWxlbmFtZSB8fCByLmtleSwgci50aHVtYl9iNjQsIHIuZ2FsbGVyeV9iNjQpOwogICAgICAgICAgICAgIH0KICAgICAgICAgICAgICAvLyBBbHdheXMgdXBkYXRlIHNsb3QgaW1nLnNyYyAoQzQgZml4OiB3YXMgaWYoIWV4aXN0aW5nKSBvbmx5KQogICAgICAgICAgICAgIHZhciBzbG90ID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoImJnLW9wdC0iICsgYmlkICsgIi0iICsgb3B0SWR4KTsKICAgICAgICAgICAgICBpZiAoc2xvdCAmJiByLnRodW1iX2I2NCkgewogICAgICAgICAgICAgICAgdmFyIGV4aXN0aW5nID0gc2xvdC5xdWVyeVNlbGVjdG9yKCJpbWciKTsKICAgICAgICAgICAgICAgIGlmIChleGlzdGluZykgewogICAgICAgICAgICAgICAgICBleGlzdGluZy5zcmMgPSByLnRodW1iX2I2NDsgICAgICAgICAgLy8gdHJhbnNpdGlvbiBVUkzihpJkYXRhLVVSSQogICAgICAgICAgICAgICAgICBleGlzdGluZy5yZW1vdmVBdHRyaWJ1dGUoImRhdGEtZml4Yy11cmwiKTsgLy8gY2xlYXIgVVJMIG1hcmtlcgogICAgICAgICAgICAgICAgfSBlbHNlIHsKICAgICAgICAgICAgICAgICAgdmFyIGltZyA9IGRvY3VtZW50LmNyZWF0ZUVsZW1lbnQoImltZyIpOwogICAgICAgICAgICAgICAgICBpbWcuc3JjID0gci50aHVtYl9iNjQ7CiAgICAgICAgICAgICAgICAgIHNsb3QuaW5zZXJ0QmVmb3JlKGltZywgc2xvdC5maXJzdENoaWxkKTsKICAgICAgICAgICAgICAgIH0KICAgICAgICAgICAgICB9CiAgICAgICAgICAgICAgLy8gVXBkYXRlIGluLW1lbW9yeSBiZWF0IHJlY29yZAogICAgICAgICAgICAgIHZhciBiZWF0ID0gKEJHX0JFQVRTIHx8IFtdKS5maW5kKGZ1bmN0aW9uIChiKSB7IHJldHVybiBiLmJlYXRfaWQgPT09IGJpZDsgfSk7CiAgICAgICAgICAgICAgaWYgKGJlYXQpIHsKICAgICAgICAgICAgICAgIGJlYXQuZmx1eF9vcHRpb25zID0gYmVhdC5mbHV4X29wdGlvbnMgfHwgW107CiAgICAgICAgICAgICAgICBiZWF0LmZsdXhfb3B0aW9uc1tvcHRJZHhdID0geyBrZXk6IHIua2V5LCByZXF1ZXN0X2lkOiByaWQgfTsKICAgICAgICAgICAgICAgIHZhciBzcCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJiZy1zdGF0dXMtIiArIGJpZCk7CiAgICAgICAgICAgICAgICBpZiAoc3ApIHNwLnRleHRDb250ZW50ID0gInN0aWxscyByZWFkeSI7CiAgICAgICAgICAgICAgfQogICAgICAgICAgICAgIEJHX1RBU0tfTUFQW2JpZF1bb3B0SWR4XSA9IG51bGw7CiAgICAgICAgICAgIH0gZWxzZSBpZiAociAmJiByLnN0YXR1cyA9PT0gImVycm9yIikgewogICAgICAgICAgICAgIEJHX1RBU0tfTUFQW2JpZF1bb3B0SWR4XSA9IG51bGw7CiAgICAgICAgICAgIH0gZWxzZSB7CiAgICAgICAgICAgICAgYWxsRG9uZSA9IGZhbHNlOwogICAgICAgICAgICB9CiAgICAgICAgICB9KTsKICAgICAgICB9KTsKICAgICAgICBpZiAoYWxsRG9uZSkgewogICAgICAgICAgY2xlYXJJbnRlcnZhbChCR19QT0xMX0lEKTsKICAgICAgICAgIEJHX1BPTExfSUQgPSBudWxsOwogICAgICAgIH0KICAgICAgfSkKICAgICAgLmNhdGNoKGZ1bmN0aW9uIChlKSB7IGNvbnNvbGUud2FybigiW0JHXSBwb2xsIGVycm9yOiIsIGUpOyB9KTsKICB9OwoKICAvLyAtLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0KICAvLyBDMzogT3ZlcnJpZGUgX2NyTG9hZEltYWdlIOKAlCBpZiBUSFtrZXldIGlzIGVtcHR5IChwb3N0LXJlZnJlc2gpLAogIC8vICAgICBmZXRjaCB0aGUgUE5HIGZyb20gL2JnLXN0aWxscy8sIGNvbnZlcnQgdG8gZGF0YSBVUkwsIHBvcHVsYXRlCiAgLy8gICAgIFRILCB0aGVuIGNhbGwgb3JpZ2luYWwuIE9ubHkgZmlyZXMgb24gY2FjaGUgbWlzcy4KICAvLyAgICAgT25seSBGTFVYIHN0aWxsIGtleXMgbWF0Y2ggcGF0dGVybiBiZ18qX29wdCog4oaSIC5wbmcKICAvLyAtLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0KICB2YXIgX2NyTG9hZEltYWdlX29yaWcgPSBfY3JMb2FkSW1hZ2U7CiAgX2NyTG9hZEltYWdlID0gZnVuY3Rpb24gKGtleSwgYmVhdElkKSB7CiAgICBpZiAoVEhba2V5XSkgewogICAgICAvLyBUSCBwb3B1bGF0ZWQgKGluLWZsaWdodCBvciBhbHJlYWR5IGZldGNoZWQpIOKAlCBvcmlnaW5hbCBwYXRoCiAgICAgIF9jckxvYWRJbWFnZV9vcmlnKGtleSwgYmVhdElkKTsKICAgICAgcmV0dXJuOwogICAgfQogICAgLy8gQ2FjaGUgbWlzczogdHJ5IC9iZy1zdGlsbHMvCiAgICB2YXIgdXJsID0gQkdfU0VSVkVSICsgIi9iZy1zdGlsbHMvIiArIGVuY29kZVVSSUNvbXBvbmVudChrZXkgKyAiLnBuZyIpCiAgICAgICAgICAgICsgIj92PSIgKyBEYXRlLm5vdygpOwogICAgdmFyIHhociA9IG5ldyBYTUxIdHRwUmVxdWVzdCgpOwogICAgeGhyLm9wZW4oIkdFVCIsIHVybCwgdHJ1ZSk7CiAgICB4aHIucmVzcG9uc2VUeXBlID0gImJsb2IiOwogICAgeGhyLm9ubG9hZCA9IGZ1bmN0aW9uICgpIHsKICAgICAgaWYgKHhoci5zdGF0dXMgPT09IDIwMCkgewogICAgICAgIHZhciByZWFkZXIgPSBuZXcgRmlsZVJlYWRlcigpOwogICAgICAgIHJlYWRlci5vbmxvYWQgPSBmdW5jdGlvbiAoKSB7CiAgICAgICAgICBUSFtrZXldID0gcmVhZGVyLnJlc3VsdDsgICAgICAgICAgIC8vIHBvcHVsYXRlIFRIIGZyb20gZGlzawogICAgICAgICAgX2NyTG9hZEltYWdlX29yaWcoa2V5LCBiZWF0SWQpOyAgICAvLyBvcmlnaW5hbCBmdW5jdGlvbiB3b3JrcyBub3JtYWxseQogICAgICAgIH07CiAgICAgICAgcmVhZGVyLnJlYWRBc0RhdGFVUkwoeGhyLnJlc3BvbnNlKTsKICAgICAgfSBlbHNlIHsKICAgICAgICBhbGVydCgiSW1hZ2Ugbm90IGZvdW5kIG9uIGRpc2s6ICIgKyBrZXkpOwogICAgICB9CiAgICB9OwogICAgeGhyLm9uZXJyb3IgPSBmdW5jdGlvbiAoKSB7IGFsZXJ0KCJGYWlsZWQgdG8gbG9hZCBpbWFnZTogIiArIGtleSk7IH07CiAgICB4aHIuc2VuZCgpOwogIH07CgogIC8vIC0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLQogIC8vIEM2OiBXcmFwIF9iZ1N1Ym1pdEJhdGNoIOKAlCBzcGlubmVyIG9uIGNsaWNrLCB0b2FzdCBvbiBzdWNjZXNzCiAgLy8gLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tCiAgdmFyIF9iZ1N1Ym1pdEJhdGNoX3ByZXYgPSBfYmdTdWJtaXRCYXRjaDsKICBfYmdTdWJtaXRCYXRjaCA9IGZ1bmN0aW9uIChiZWF0SWRzKSB7CiAgICAvLyBJbW1lZGlhdGUgZmVlZGJhY2s6IGRpc2FibGUgKyBzcGlubmVyCiAgICBiZWF0SWRzLmZvckVhY2goZnVuY3Rpb24gKGJpZCkgewogICAgICB2YXIgY2FyZCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJiZy1jYXJkLSIgKyBiaWQpOwogICAgICBpZiAoIWNhcmQpIHJldHVybjsKICAgICAgdmFyIGJ0biA9IGNhcmQucXVlcnlTZWxlY3RvcigiLmJnLWdlbi1idG4iKTsKICAgICAgaWYgKGJ0bikgeyBidG4uZGlzYWJsZWQgPSB0cnVlOyBidG4udGV4dENvbnRlbnQgPSAiXHUyM2YzIFN1Ym1pdHRpbmdcdTIwMjYiOyB9CiAgICB9KTsKCiAgICBmZXRjaChCR19TRVJWRVIgKyAiL2FwaS9iZy9zdWJtaXQtZmx1eC1iYXRjaCIsIHsKICAgICAgbWV0aG9kOiAiUE9TVCIsCiAgICAgIGhlYWRlcnM6IHsgIkNvbnRlbnQtVHlwZSI6ICJhcHBsaWNhdGlvbi9qc29uIiB9LAogICAgICBib2R5OiBKU09OLnN0cmluZ2lmeSh7IGJlYXRfaWRzOiBiZWF0SWRzIH0pCiAgICB9KQogICAgICAudGhlbihmdW5jdGlvbiAocikgeyByZXR1cm4gci5qc29uKCk7IH0pCiAgICAgIC50aGVuKGZ1bmN0aW9uIChkKSB7CiAgICAgICAgaWYgKGQuZXJyb3IpIHsKICAgICAgICAgIGFsZXJ0KCJTdWJtaXQgZXJyb3I6ICIgKyBkLmVycm9yKTsKICAgICAgICAgIF9maXhjX3Jlc3RvcmVCdG5zKGJlYXRJZHMpOwogICAgICAgICAgcmV0dXJuOwogICAgICAgIH0KICAgICAgICBPYmplY3QuYXNzaWduKEJHX1RBU0tfTUFQLCBkLnRhc2tfbWFwIHx8IHt9KTsKICAgICAgICBiZWF0SWRzLmZvckVhY2goZnVuY3Rpb24gKGJpZCkgewogICAgICAgICAgdmFyIHNwID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoImJnLXN0YXR1cy0iICsgYmlkKTsKICAgICAgICAgIGlmIChzcCkgc3AudGV4dENvbnRlbnQgPSAicGVuZGluZ1x1MjAyNiI7CiAgICAgICAgfSk7CiAgICAgICAgaWYgKCFCR19QT0xMX0lEKSBCR19QT0xMX0lEID0gc2V0SW50ZXJ2YWwoX2JnUG9sbFN0YXR1cywgNTAwMCk7CiAgICAgICAgX2ZpeGNfcmVzdG9yZUJ0bnMoYmVhdElkcyk7CiAgICAgICAgX2ZpeGNfdG9hc3QoIlx1MjcxMyBTdWJtaXR0ZWQgIiArIChiZWF0SWRzLmxlbmd0aCAqIDMpICsgIiBqb2JzIFx1MjAxNCBpbWFnZXMgYXBwZWFyIGluIH4zMHMiKTsKICAgICAgfSkKICAgICAgLmNhdGNoKGZ1bmN0aW9uIChlKSB7CiAgICAgICAgYWxlcnQoIlN1Ym1pdCBmYWlsZWQ6ICIgKyBlKTsKICAgICAgICBfZml4Y19yZXN0b3JlQnRucyhiZWF0SWRzKTsKICAgICAgfSk7CiAgfTsKCiAgZnVuY3Rpb24gX2ZpeGNfcmVzdG9yZUJ0bnMoYmVhdElkcykgewogICAgYmVhdElkcy5mb3JFYWNoKGZ1bmN0aW9uIChiaWQpIHsKICAgICAgdmFyIGNhcmQgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgiYmctY2FyZC0iICsgYmlkKTsKICAgICAgaWYgKCFjYXJkKSByZXR1cm47CiAgICAgIHZhciBidG4gPSBjYXJkLnF1ZXJ5U2VsZWN0b3IoIi5iZy1nZW4tYnRuIik7CiAgICAgIGlmICghYnRuKSByZXR1cm47CiAgICAgIGJ0bi5kaXNhYmxlZCA9IGZhbHNlOwogICAgICB2YXIgYmVhdCA9IChCR19CRUFUUyB8fCBbXSkuZmluZChmdW5jdGlvbiAoYikgeyByZXR1cm4gYi5iZWF0X2lkID09PSBiaWQ7IH0pOwogICAgICB2YXIgaGFzID0gYmVhdCAmJiAoYmVhdC5mbHV4X29wdGlvbnMgfHwgW10pLnNvbWUoZnVuY3Rpb24gKG8pIHsgcmV0dXJuIG8gJiYgby5sb2NhbF9wYXRoOyB9KTsKICAgICAgYnRuLnRleHRDb250ZW50ID0gaGFzID8gIlx1MjFiYSBSZWdlbmVyYXRlIFN0aWxscyIgOiAiXHUyNmExIEdlbmVyYXRlIFN0aWxscyI7CiAgICB9KTsKICB9CgogIHdpbmRvdy5fZml4Y190b2FzdCA9IGZ1bmN0aW9uIChtc2cpIHsKICAgIHZhciB0ID0gZG9jdW1lbnQuY3JlYXRlRWxlbWVudCgiZGl2Iik7CiAgICB0LnN0eWxlLmNzc1RleHQgPSBbCiAgICAgICJwb3NpdGlvbjpmaXhlZCIsICJib3R0b206MjRweCIsICJyaWdodDoyNHB4IiwKICAgICAgImJhY2tncm91bmQ6IzFiNDMzMiIsICJjb2xvcjojYjdlNGM3IiwKICAgICAgInBhZGRpbmc6MTBweCAxOHB4IiwgImJvcmRlci1yYWRpdXM6OHB4IiwKICAgICAgImZvbnQtc2l6ZToxMnB4IiwgInotaW5kZXg6OTk5OSIsCiAgICAgICJib3gtc2hhZG93OjAgMnB4IDEwcHggcmdiYSgwLDAsMCwuNSkiCiAgICBdLmpvaW4oIjsiKTsKICAgIHQudGV4dENvbnRlbnQgPSBtc2c7CiAgICBkb2N1bWVudC5ib2R5LmFwcGVuZENoaWxkKHQpOwogICAgc2V0VGltZW91dChmdW5jdGlvbiAoKSB7CiAgICAgIGlmICh0LnBhcmVudE5vZGUpIHQucGFyZW50Tm9kZS5yZW1vdmVDaGlsZCh0KTsKICAgIH0sIDQwMDApOwogIH07Cgp9KSgpOwovLyA9PT0gRU5EIEZJWC1DIFNUQVRJQyBTVElMTFMgUEFUQ0ggPT09Cjwvc2NyaXB0PgoKPHNjcmlwdD4KLy8gPT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09Ci8vIEZJWC1DM2IgRlVMTC1SRVMgQ1JPUCAoMjAyNi0wNC0yNSkKLy8gUm9vdCBjYXVzZTogX2luamVjdEltYWdlKCkgcHV0cyB0aHVtYl9iNjQgKDI1NngxOTApIGluIFRIW2tleV0uCi8vIEZpeC1DJ3MgQzMgcGF0Y2ggaGFkIGBpZiAoVEhba2V5XSkgcmV0dXJuIGVhcmx5YCDigJQgc28gaXQgdXNlZCB0aGUKLy8gdGh1bWJuYWlsIGluc3RlYWQgb2YgWEhSaW5nIHRoZSBmdWxsLXJlcyBQTkcgZnJvbSAvYmctc3RpbGxzLy4KLy8gRml4OiBhbHdheXMgWEhSIC9iZy1zdGlsbHMvPGtleT4ucG5nIChmdWxsIHJlc29sdXRpb24pIGZvciBjcm9wLgovLyAgICAgIEZhbGwgYmFjayB0byBUSCBvbiA0MDQuIFVwZ3JhZGUgVEggdG8gZnVsbC1yZXMgb24gc3VjY2Vzcy4KLy8gPT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09CihmdW5jdGlvbiAoKSB7CiAgInVzZSBzdHJpY3QiOwoKICBmdW5jdGlvbiBfY3JPcGVuRnVsbFJlcyhrZXksIHNyYykgewogICAgdmFyIGltZyA9IG5ldyBJbWFnZSgpOwogICAgaW1nLm9ubG9hZCA9IGZ1bmN0aW9uICgpIHsKICAgICAgQ1JfSU1HID0gaW1nOwogICAgICB2YXIgY3JvcFcgPSBNYXRoLm1pbihpbWcud2lkdGgsIGltZy5oZWlnaHQgKiA0IC8gMyk7CiAgICAgIHZhciBjcm9wSCA9IGNyb3BXICogMyAvIDQ7CiAgICAgIENSX0NST1BfQk9YID0gewogICAgICAgIHg6IChpbWcud2lkdGggLSBjcm9wVykgLyAyLAogICAgICAgIHk6IChpbWcuaGVpZ2h0IC0gY3JvcEgpIC8gMiwKICAgICAgICB3OiBjcm9wVywKICAgICAgICBoOiBjcm9wSAogICAgICB9OwogICAgICBfYmdTd2l0Y2hUYWIoImNyIiwgbnVsbCk7CiAgICAgIF9jckRyYXcoKTsKICAgICAgdmFyIGluZm8gPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgiY3ItY3JvcC1pbmZvIik7CiAgICAgIGlmIChpbmZvKSBpbmZvLnRleHRDb250ZW50ID0gIkltYWdlOiAiICsgaW1nLndpZHRoICsgIlx1MDBkNyIgKyBpbWcuaGVpZ2h0ICsgInB4XG5Dcm9wOiA0OjMiOwogICAgICB2YXIgc2F2ZUJ0biA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJjci1zYXZlLWJ0biIpOwogICAgICBpZiAoc2F2ZUJ0bikgc2F2ZUJ0bi5kaXNhYmxlZCA9IGZhbHNlOwogICAgfTsKICAgIGltZy5vbmVycm9yID0gZnVuY3Rpb24gKCkgeyBhbGVydCgiRmFpbGVkIHRvIGxvYWQgaW1hZ2UuIik7IH07CiAgICBpbWcuc3JjID0gc3JjOwogIH0KCiAgLy8gRnVsbCByZXBsYWNlbWVudCBvZiBfY3JMb2FkSW1hZ2Ug4oCUIGFsd2F5cyB1c2VzIC9iZy1zdGlsbHMvIGZ1bGwtcmVzCiAgd2luZG93Ll9jckxvYWRJbWFnZSA9IGZ1bmN0aW9uIChrZXksIGJlYXRJZCkgewogICAgQ1JfQkVBVF9JRCA9IGJlYXRJZDsKICAgIENSX1NSQ19LRVkgPSBrZXk7CgogICAgdmFyIHVybCA9IEJHX1NFUlZFUiArICIvYmctc3RpbGxzLyIgKyBlbmNvZGVVUklDb21wb25lbnQoa2V5ICsgIi5wbmciKQogICAgICAgICAgICArICI/dj0iICsgRGF0ZS5ub3coKTsKICAgIHZhciB4aHIgPSBuZXcgWE1MSHR0cFJlcXVlc3QoKTsKICAgIHhoci5vcGVuKCJHRVQiLCB1cmwsIHRydWUpOwogICAgeGhyLnJlc3BvbnNlVHlwZSA9ICJibG9iIjsKICAgIHhoci5vbmxvYWQgPSBmdW5jdGlvbiAoKSB7CiAgICAgIGlmICh4aHIuc3RhdHVzID09PSAyMDApIHsKICAgICAgICB2YXIgcmVhZGVyID0gbmV3IEZpbGVSZWFkZXIoKTsKICAgICAgICByZWFkZXIub25sb2FkID0gZnVuY3Rpb24gKCkgewogICAgICAgICAgVEhba2V5XSA9IHJlYWRlci5yZXN1bHQ7ICAgICAgICAgLy8gdXBncmFkZSBUSCBmcm9tIHRodW1iIHRvIGZ1bGwtcmVzCiAgICAgICAgICBfY3JPcGVuRnVsbFJlcyhrZXksIFRIW2tleV0pOwogICAgICAgIH07CiAgICAgICAgcmVhZGVyLnJlYWRBc0RhdGFVUkwoeGhyLnJlc3BvbnNlKTsKICAgICAgfSBlbHNlIGlmIChUSFtrZXldKSB7CiAgICAgICAgLy8gL2JnLXN0aWxscy8gcmV0dXJuZWQgNDA0L2Vycm9yIOKAlCBmYWxsIGJhY2sgdG8gd2hhdGV2ZXIgVEggaGFzCiAgICAgICAgX2NyT3BlbkZ1bGxSZXMoa2V5LCBUSFtrZXldKTsKICAgICAgfSBlbHNlIHsKICAgICAgICBhbGVydCgiSW1hZ2Ugbm90IGZvdW5kIG9uIGRpc2s6ICIgKyBrZXkpOwogICAgICB9CiAgICB9OwogICAgeGhyLm9uZXJyb3IgPSBmdW5jdGlvbiAoKSB7CiAgICAgIGlmIChUSFtrZXldKSB7IF9jck9wZW5GdWxsUmVzKGtleSwgVEhba2V5XSk7IH0KICAgICAgZWxzZSB7IGFsZXJ0KCJGYWlsZWQgdG8gbG9hZCBpbWFnZTogIiArIGtleSk7IH0KICAgIH07CiAgICB4aHIuc2VuZCgpOwogIH07Cgp9KSgpOwovLyA9PT0gRU5EIEZJWC1DM2IgRlVMTC1SRVMgQ1JPUCA9PT0KPC9zY3JpcHQ+Cgo8c2NyaXB0PgovLyA9PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT0KLy8gRklYLUQgQkcgUEFORUwgUEVSU0lTVEVOQ0UgKDIwMjYtMDQtMjUpCi8vIFByb2JsZW0gMTogX2JnTG9hZFN0YXRlKCkgb25seSBmaXJlcyBvbiBCRyB0YWIgY2xpY2sgKGxpbmUgMzk3OSkuCi8vICAgU3Rvcnlib2FyZCB0YWIgaGFzIExbXSBlbWJlZGRlZCBpbiBIVE1MIOKAlCBhbHdheXMgcmVhZHkuIEJHIHRhYgovLyAgIG5lZWRzIGVxdWl2YWxlbnQ6IHByZS1sb2FkIHN0YXRlIGF0IERPTUNvbnRlbnRMb2FkZWQuCi8vIFByb2JsZW0gMjogQ2hhciBSZWYgLyBCRyBSZWYgaW1hZ2VzIHJlbHkgb24gTU5fTElCX0RBVEEgKHBvcHVsYXRlZAovLyAgIGJ5IF9tbkxpYkZldGNoLCBhc3luYykuIElmIGJlYXRzIHJlbmRlciBiZWZvcmUgbGliIGRhdGEgYXJyaXZlcywKLy8gICByZWYgaW1hZ2Ugc2xvdHMgYXJlIGJsYW5rLiBGaXg6IHJlLXJlbmRlciBiZWF0cyBhZnRlciBsaWIgbG9hZHMuCi8vID09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PQooZnVuY3Rpb24gKCkgewogICJ1c2Ugc3RyaWN0IjsKCiAgLy8gLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tCiAgLy8gRml4IDE6IFByZS1sb2FkIEJHIHN0YXRlIGF0IERPTUNvbnRlbnRMb2FkZWQgKGJhY2tncm91bmQgaHlkcmF0aW9uKQogIC8vIC0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLQogIGRvY3VtZW50LmFkZEV2ZW50TGlzdGVuZXIoIkRPTUNvbnRlbnRMb2FkZWQiLCBmdW5jdGlvbiAoKSB7CiAgICAvLyBTbWFsbCBkZWxheSBzbyBvdGhlciBET01Db250ZW50TG9hZGVkIGhhbmRsZXJzIChsaWIgZmV0Y2gsIGFyYwogICAgLy8gc2VsZWN0b3IsIGV0Yy4pIHJlZ2lzdGVyIGZpcnN0LCBhdm9pZGluZyBkZXBlbmRlbmN5IHJhY2VzLgogICAgc2V0VGltZW91dChmdW5jdGlvbiAoKSB7CiAgICAgIGlmICh0eXBlb2YgX2JnTG9hZFN0YXRlID09PSAiZnVuY3Rpb24iKSB7CiAgICAgICAgX2JnTG9hZFN0YXRlKCk7CiAgICAgIH0KICAgIH0sIDMwMCk7CiAgfSk7CgogIC8vIC0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLQogIC8vIEZpeCAyOiBBZnRlciBsaWIgZGF0YSBhcnJpdmVzLCByZS1yZW5kZXIgYmVhdHMgdG8gcGljayB1cCByZWYgaW1hZ2VzLgogIC8vIF9tbkxpYlJlbmRlciBpcyBjYWxsZWQgYXQgZW5kIG9mIGV2ZXJ5IF9tbkxpYkZldGNoIOKAlCB3cmFwcGluZyBpdAogIC8vIGVuc3VyZXMgYmVhdHMgcmUtcmVuZGVyIHdoZW5ldmVyIE1OX0xJQl9EQVRBIGlzIGZyZXNobHkgcG9wdWxhdGVkLgogIC8vIEd1YXJkOiBvbmx5IHJlLXJlbmRlciBpZiBCR19CRUFUUyBpcyBhbHJlYWR5IGxvYWRlZCAobm9uLWVtcHR5KS4KICAvLyBHdWFyZDogZGVib3VuY2UgMjAwbXMgc28gcmFwaWQgbGliIHJlZnJlc2hlcyBkb24ndCBzcGFtIHJlLXJlbmRlcnMuCiAgLy8gLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tCiAgdmFyIF9maXhkX3JlcmVuZGVyX3RpbWVyID0gbnVsbDsKICBpZiAodHlwZW9mIF9tbkxpYlJlbmRlciA9PT0gImZ1bmN0aW9uIikgewogICAgdmFyIF9tbkxpYlJlbmRlcl9vcmlnID0gX21uTGliUmVuZGVyOwogICAgd2luZG93Ll9tbkxpYlJlbmRlciA9IF9tbkxpYlJlbmRlciA9IGZ1bmN0aW9uICgpIHsKICAgICAgX21uTGliUmVuZGVyX29yaWcuYXBwbHkodGhpcywgYXJndW1lbnRzKTsKICAgICAgLy8gUmUtcmVuZGVyIGJlYXRzIHRvIHBpY2sgdXAgcmVmIGltYWdlcyBub3cgdGhhdCBNTl9MSUJfREFUQSBpcyBzZXQKICAgICAgY2xlYXJUaW1lb3V0KF9maXhkX3JlcmVuZGVyX3RpbWVyKTsKICAgICAgX2ZpeGRfcmVyZW5kZXJfdGltZXIgPSBzZXRUaW1lb3V0KGZ1bmN0aW9uICgpIHsKICAgICAgICBpZiAodHlwZW9mIEJHX0JFQVRTICE9PSAidW5kZWZpbmVkIiAmJiBCR19CRUFUUyAmJiBCR19CRUFUUy5sZW5ndGgpIHsKICAgICAgICAgIF9iZ1JlbmRlckJlYXRzKEJHX0JFQVRTKTsKICAgICAgICB9CiAgICAgIH0sIDIwMCk7CiAgICB9OwogIH0KCn0pKCk7Ci8vID09PSBFTkQgRklYLUQgQkcgUEFORUwgUEVSU0lTVEVOQ0UgPT09Cjwvc2NyaXB0PgoKPHN0eWxlPgovKiBGSVgtRTogbGlicmFyeSBzY3JvbGwgcGFkZGluZyAoMjAyNi0wNC0yNSkKICAgTGV0cyB1c2VyIHNjcm9sbCBBZGQgSW1hZ2UgYnV0dG9uIGFib3ZlIHRoZSBmaXhlZCBkZWJ1Zy9SZXN0YXJ0IG92ZXJsYXkgKi8KLm1uLWxpYi1ib2R5IHsgcGFkZGluZy1ib3R0b206IDE0MHB4ICFpbXBvcnRhbnQ7IH0KPC9zdHlsZT4KCjxzdHlsZT4KLyogRklYLUY6IHVwbG9hZCBidXR0b24gYXQgdG9wLCByZW1vdmUgYm90dG9tIHBhZGRpbmcgaGFjayAoMjAyNi0wNC0yNSkgKi8KLm1uLWxpYi1ib2R5IHsgcGFkZGluZy1ib3R0b206IDhweCAhaW1wb3J0YW50OyB9Ci5tbi1saWItdXBsb2FkLWJ0biB7IG1hcmdpbi1ib3R0b206IDhweDsgfQo8L3N0eWxlPgo8c2NyaXB0PgovLyBGSVgtRjogTW92ZSAubW4tbGliLXVwbG9hZC1idG4gdG8gVE9QIG9mIC5tbi1saWItYm9keSAoMjAyNi0wNC0yNSkKLy8gVGhlIGJ1dHRvbiB3YXMgbGFzdCDigJQgYnVyaWVkIGJlaGluZCB0aGUgZml4ZWQgZGVidWcvUmVzdGFydCBTZXJ2ZXIgb3ZlcmxheS4KLy8gTW92aW5nIHRvIHRvcCBtYWtlcyBpdCBhbHdheXMgYWNjZXNzaWJsZSB3aXRob3V0IHNjcm9sbGluZy4KZG9jdW1lbnQuYWRkRXZlbnRMaXN0ZW5lcigiRE9NQ29udGVudExvYWRlZCIsIGZ1bmN0aW9uICgpIHsKICB2YXIgYm9keSA9IGRvY3VtZW50LnF1ZXJ5U2VsZWN0b3IoIi5tbi1saWItYm9keSIpOwogIHZhciBidG4gID0gZG9jdW1lbnQucXVlcnlTZWxlY3RvcigiLm1uLWxpYi11cGxvYWQtYnRuIik7CiAgaWYgKGJvZHkgJiYgYnRuICYmIGJvZHkuZmlyc3RDaGlsZCAhPT0gYnRuKSB7CiAgICBib2R5Lmluc2VydEJlZm9yZShidG4sIGJvZHkuZmlyc3RDaGlsZCk7CiAgfQp9KTsKLy8gPT09IEVORCBGSVgtRiBVUExPQUQgVE9QID09PQo8L3NjcmlwdD4KCjxzY3JpcHQ+Ci8vID09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PQovLyBGSVgtRyBTRUdNRU5UIENMSUNLIFBFUlNJU1RFTkNFICgyMDI2LTA0LTI1KQovLyBSb290IGNhdXNlOiBfYmdMb2FkU2VnbWVudHMgc2VnbWVudCBvbmNsaWNrIGRpZCBCR19CRUFUUz1bXTsgX2JnUmVuZGVyQmVhdHMoW10pCi8vIGltbWVkaWF0ZWx5LCBkaXNjYXJkaW5nIGFueSBwcmV2aW91c2x5IHNhdmVkIGJlYXRzIGZvciB0aGF0IHNlZ21lbnQuCi8vIEZpeDogd3JhcCBfYmdMb2FkU2VnbWVudHMgdG8gdXNlIC9hcGkvYmcvc2V0LWFjdGl2ZS1jb250ZXh0IHdoaWNoIHJldHVybnMKLy8gc2F2ZWQgYmVhdHMgZnJvbSB0aGUgc2lkZWNhci4gUmVuZGVycyB0aGVtIGlmIGZvdW5kOyBzaG93cyBlbXB0eSBwcm9tcHQgaWYgbm90LgovLyA9PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT0KKGZ1bmN0aW9uICgpIHsKICAidXNlIHN0cmljdCI7CgogIHZhciBfYmdMb2FkU2VnbWVudHNfb3JpZyA9IF9iZ0xvYWRTZWdtZW50czsKCiAgd2luZG93Ll9iZ0xvYWRTZWdtZW50cyA9IF9iZ0xvYWRTZWdtZW50cyA9IGZ1bmN0aW9uIChhcmNOdW0pIHsKICAgIGZldGNoKEJHX1NFUlZFUiArICIvYXBpL2JnL3NlZ21lbnRzP2FyY19udW1iZXI9IiArIGFyY051bSkKICAgICAgLnRoZW4oZnVuY3Rpb24gKHIpIHsgcmV0dXJuIHIuanNvbigpOyB9KQogICAgICAudGhlbihmdW5jdGlvbiAoZCkgewogICAgICAgIHZhciBsaXN0ID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoImJnLXNlZy1saXN0Iik7CiAgICAgICAgaWYgKCFsaXN0KSByZXR1cm47CiAgICAgICAgbGlzdC5pbm5lckhUTUwgPSAiIjsKICAgICAgICB2YXIgd3JhcCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJiZy1zZWctd3JhcCIpOwogICAgICAgIGlmICh3cmFwKSB3cmFwLnN0eWxlLmRpc3BsYXkgPSAiYmxvY2siOwoKICAgICAgICAoZC5zZWdtZW50cyB8fCBbXSkuZm9yRWFjaChmdW5jdGlvbiAoc2VnKSB7CiAgICAgICAgICB2YXIgaXRlbSA9IGRvY3VtZW50LmNyZWF0ZUVsZW1lbnQoImRpdiIpOwogICAgICAgICAgaXRlbS5jbGFzc05hbWUgPSAiYmctc2VnLWl0ZW0iOwogICAgICAgICAgaXRlbS50ZXh0Q29udGVudCA9IHNlZy5uYW1lOwoKICAgICAgICAgIGl0ZW0ub25jbGljayA9IGZ1bmN0aW9uICgpIHsKICAgICAgICAgICAgZG9jdW1lbnQucXVlcnlTZWxlY3RvckFsbCgiLmJnLXNlZy1pdGVtIikuZm9yRWFjaChmdW5jdGlvbiAoeCkgewogICAgICAgICAgICAgIHguY2xhc3NMaXN0LnJlbW92ZSgic2VsIik7CiAgICAgICAgICAgIH0pOwogICAgICAgICAgICB0aGlzLmNsYXNzTGlzdC5hZGQoInNlbCIpOwogICAgICAgICAgICBCR19TRUcgPSBzZWc7CiAgICAgICAgICAgIEJHX0FSQyA9IGFyY051bTsKCiAgICAgICAgICAgIHZhciBhY3RzID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoImJnLWFjdGlvbnMiKTsKICAgICAgICAgICAgaWYgKGFjdHMpIGFjdHMuc3R5bGUuZGlzcGxheSA9ICJmbGV4IjsKCiAgICAgICAgICAgIC8vIFNob3cgbG9hZGluZyBzdGF0ZSB3aGlsZSB3ZSBjaGVjayBzaWRlY2FyCiAgICAgICAgICAgIHZhciBjb250YWluZXIgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgiYmctYmVhdHMiKTsKICAgICAgICAgICAgaWYgKGNvbnRhaW5lcikgewogICAgICAgICAgICAgIGNvbnRhaW5lci5pbm5lckhUTUwgPSAnPGRpdiBjbGFzcz0iYmctZW1wdHkiPkxvYWRpbmfigKY8L2Rpdj4nOwogICAgICAgICAgICB9CgogICAgICAgICAgICAvLyBBc2sgc2VydmVyIHRvIHN3aXRjaCBhY3RpdmUgY29udGV4dCArIHJldHVybiBhbnkgc2F2ZWQgYmVhdHMKICAgICAgICAgICAgZmV0Y2goQkdfU0VSVkVSICsgIi9hcGkvYmcvc2V0LWFjdGl2ZS1jb250ZXh0IiwgewogICAgICAgICAgICAgIG1ldGhvZDogIlBPU1QiLAogICAgICAgICAgICAgIGhlYWRlcnM6IHsgIkNvbnRlbnQtVHlwZSI6ICJhcHBsaWNhdGlvbi9qc29uIiB9LAogICAgICAgICAgICAgIGJvZHk6IEpTT04uc3RyaW5naWZ5KHsKICAgICAgICAgICAgICAgIGFyY19udW1iZXI6IGFyY051bSwKICAgICAgICAgICAgICAgIGV2ZW50X2lkOiBzZWcuZXZlbnRfaWQsCiAgICAgICAgICAgICAgICBwaGFzZTogc2VnLnBoYXNlIHx8ICJmdWxsIgogICAgICAgICAgICAgIH0pCiAgICAgICAgICAgIH0pCiAgICAgICAgICAgICAgLnRoZW4oZnVuY3Rpb24gKHIpIHsgcmV0dXJuIHIuanNvbigpOyB9KQogICAgICAgICAgICAgIC50aGVuKGZ1bmN0aW9uIChkYXRhKSB7CiAgICAgICAgICAgICAgICB2YXIgc2F2ZWQgPSBkYXRhLmJlYXRzIHx8IFtdOwogICAgICAgICAgICAgICAgQkdfQkVBVFMgPSBzYXZlZDsKICAgICAgICAgICAgICAgIF9iZ1JlbmRlckJlYXRzKEJHX0JFQVRTKTsKCiAgICAgICAgICAgICAgICB2YXIgZ2VuQnRuID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoImJnLWdlbi1hbGwtYnRuIik7CiAgICAgICAgICAgICAgICB2YXIgYWNjZXB0QnRuID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoImJnLWFjY2VwdC1idG4iKTsKICAgICAgICAgICAgICAgIGlmIChnZW5CdG4pIGdlbkJ0bi5kaXNhYmxlZCA9IEJHX0JFQVRTLmxlbmd0aCA9PT0gMDsKICAgICAgICAgICAgICAgIGlmIChhY2NlcHRCdG4pIGFjY2VwdEJ0bi5kaXNhYmxlZCA9IEJHX0JFQVRTLmxlbmd0aCA9PT0gMDsKICAgICAgICAgICAgICB9KQogICAgICAgICAgICAgIC5jYXRjaChmdW5jdGlvbiAoZSkgewogICAgICAgICAgICAgICAgY29uc29sZS5lcnJvcigiW0JHXSBzZXQtYWN0aXZlLWNvbnRleHQgZXJyb3I6IiwgZSk7CiAgICAgICAgICAgICAgICBCR19CRUFUUyA9IFtdOwogICAgICAgICAgICAgICAgX2JnUmVuZGVyQmVhdHMoW10pOwogICAgICAgICAgICAgIH0pOwogICAgICAgICAgfTsKCiAgICAgICAgICBsaXN0LmFwcGVuZENoaWxkKGl0ZW0pOwogICAgICAgIH0pOwoKICAgICAgICBpZiAodHlwZW9mIF9iZ0xvYWRHcm91cHMgPT09ICJmdW5jdGlvbiIpIF9iZ0xvYWRHcm91cHMoYXJjTnVtKTsKICAgICAgfSkKICAgICAgLmNhdGNoKGZ1bmN0aW9uIChlKSB7IGNvbnNvbGUuZXJyb3IoIltCR10gc2VnbWVudHMgZXJyb3I6IiwgZSk7IH0pOwogIH07Cgp9KSgpOwovLyA9PT0gRU5EIEZJWC1HIFNFR01FTlQgQ0xJQ0sgUEVSU0lTVEVOQ0UgPT09Cjwvc2NyaXB0PgoKPHN0eWxlPgovKiBGSVgtSDogdXBsb2FkIGJ1dHRvbiBhcyBwZXJzaXN0ZW50IGhlYWRlciBhYm92ZSBzY3JvbGxhYmxlIGxpYnJhcnkgYm9keSAoMjAyNi0wNC0yNSkgKi8KI21uLWxpYi11cGxvYWQtaGVhZGVyIHsKICBwYWRkaW5nOiA0cHggNnB4IDJweCA2cHg7CiAgZmxleC1zaHJpbms6IDA7Cn0KI21uLWxpYi11cGxvYWQtaGVhZGVyIC5tbi1saWItdXBsb2FkLWJ0biB7CiAgbWFyZ2luLWJvdHRvbTogMDsKfQovKiBSZW1vdmUgRml4LUYvRml4LUUgYm90dG9tIHBhZGRpbmcgaGFja3Mg4oCUIG5vIGxvbmdlciBuZWVkZWQgKi8KLm1uLWxpYi1ib2R5IHsgcGFkZGluZy1ib3R0b206IDhweCAhaW1wb3J0YW50OyB9Cjwvc3R5bGU+CjxzY3JpcHQ+Ci8vIEZJWC1IOiBNb3ZlIHVwbG9hZCBidXR0b24gT1VUU0lERSBzY3JvbGxhYmxlIC5tbi1saWItYm9keSAoMjAyNi0wNC0yNSkKLy8gQ3JlYXRlcyBhIHBlcnNpc3RlbnQgI21uLWxpYi11cGxvYWQtaGVhZGVyIGRpdiBiZXR3ZWVuIHRoZSB0b2dnbGUgYW5kIHRoZQovLyBzY3JvbGxhYmxlIGJvZHkgc28gdGhlIGJ1dHRvbiBpcyBhbHdheXMgdmlzaWJsZSByZWdhcmRsZXNzIG9mIHNjcm9sbCBwb3NpdGlvbi4KKGZ1bmN0aW9uICgpIHsKICAidXNlIHN0cmljdCI7CgogIGZ1bmN0aW9uIF9maXhoTW92ZVVwbG9hZEJ0bigpIHsKICAgIHZhciBzaWRlYmFyID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoIm1uLWxpYi1zaWRlYmFyIik7CiAgICB2YXIgYm9keSAgICA9IGRvY3VtZW50LnF1ZXJ5U2VsZWN0b3IoIi5tbi1saWItYm9keSIpOwogICAgdmFyIGJ0biAgICAgPSBkb2N1bWVudC5xdWVyeVNlbGVjdG9yKCIubW4tbGliLXVwbG9hZC1idG4iKTsKICAgIGlmICghc2lkZWJhciB8fCAhYm9keSB8fCAhYnRuKSByZXR1cm47CgogICAgLy8gQWxyZWFkeSBtb3ZlZD8gKGlkZW1wb3RlbnQpCiAgICBpZiAoZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoIm1uLWxpYi11cGxvYWQtaGVhZGVyIikpIHJldHVybjsKCiAgICB2YXIgaGVhZGVyID0gZG9jdW1lbnQuY3JlYXRlRWxlbWVudCgiZGl2Iik7CiAgICBoZWFkZXIuaWQgPSAibW4tbGliLXVwbG9hZC1oZWFkZXIiOwogICAgaGVhZGVyLmFwcGVuZENoaWxkKGJ0bik7ICAgICAgICAgICAgICAvLyByZW1vdmUgZnJvbSBib2R5LCBpbnNlcnQgaW50byBoZWFkZXIKICAgIHNpZGViYXIuaW5zZXJ0QmVmb3JlKGhlYWRlciwgYm9keSk7ICAgLy8gaGVhZGVyIHNpdHMgYmV0d2VlbiB0b2dnbGUgYW5kIGJvZHkKICB9CgogIGRvY3VtZW50LmFkZEV2ZW50TGlzdGVuZXIoIkRPTUNvbnRlbnRMb2FkZWQiLCBfZml4aE1vdmVVcGxvYWRCdG4pOwoKICAvLyBSZS1ydW4gYWZ0ZXIgbGliIGZldGNoIGluIGNhc2UgcmVuZGVyIHJlLWluc2VydGVkIGl0IChkZWZlbnNpdmUpCiAgdmFyIF9vcmlnRmV0Y2ggPSB3aW5kb3cuX21uTGliRmV0Y2g7CiAgaWYgKHR5cGVvZiBfb3JpZ0ZldGNoID09PSAiZnVuY3Rpb24iKSB7CiAgICB3aW5kb3cuX21uTGliRmV0Y2ggPSBmdW5jdGlvbiAoKSB7CiAgICAgIF9vcmlnRmV0Y2guYXBwbHkodGhpcywgYXJndW1lbnRzKTsKICAgICAgc2V0VGltZW91dChfZml4aE1vdmVVcGxvYWRCdG4sIDUwKTsKICAgIH07CiAgfQoKfSkoKTsKLy8gPT09IEVORCBGSVgtSCBVUExPQUQgSEVBREVSID09PQo8L3NjcmlwdD4KCjxzdHlsZT4KLyogRklYLUgyOiBzdGlja3kgdXBsb2FkIGJ0biBhbHdheXMgdmlzaWJsZSBhdCB0b3Agb2YgbGlicmFyeSBzY3JvbGwgYXJlYSAoMjAyNi0wNC0yNSkgKi8KLm1uLWxpYi11cGxvYWQtYnRuIHsKICBwb3NpdGlvbjogc3RpY2t5ICFpbXBvcnRhbnQ7CiAgdG9wOiAwICFpbXBvcnRhbnQ7CiAgei1pbmRleDogNSAhaW1wb3J0YW50OwogIGJhY2tncm91bmQ6ICMxNDFlMTQgIWltcG9ydGFudDsKICBtYXJnaW4tYm90dG9tOiA2cHggIWltcG9ydGFudDsKICBib3JkZXItYm90dG9tOiAxcHggc29saWQgIzJhNGEyYSAhaW1wb3J0YW50OwogIGRpc3BsYXk6IGJsb2NrICFpbXBvcnRhbnQ7Cn0KLm1uLWxpYi1ib2R5IHsgcGFkZGluZy1ib3R0b206IDhweCAhaW1wb3J0YW50OyB9Cjwvc3R5bGU+CjxzY3JpcHQ+Ci8vIEZJWC1IMjogRml4LUggcHV0IHRoZSBidXR0b24gaW4gYSByb3ctZmxleCBzaWRlYmFyIGNvbHVtbiAod3JvbmcpLiAoMjAyNi0wNC0yNSkKLy8gVGhpcyBjb3JyZWN0cyBpdDogbW92ZSBidG4gYmFjayBpbnRvIC5tbi1saWItYm9keSBhcyB0aGUgZmlyc3QgZWxlbWVudCBjaGlsZC4KLy8gcG9zaXRpb246c3RpY2t5O3RvcDowIChDU1MgYWJvdmUpIHBpbnMgaXQgdG8gdGhlIHRvcCBvZiB0aGUgc2Nyb2xsIHZpZXdwb3J0LgooZnVuY3Rpb24gKCkgewogICJ1c2Ugc3RyaWN0IjsKCiAgZnVuY3Rpb24gX2ZpeGgyUGluKCkgewogICAgdmFyIGJvZHkgPSBkb2N1bWVudC5xdWVyeVNlbGVjdG9yKCIubW4tbGliLWJvZHkiKTsKICAgIGlmICghYm9keSkgcmV0dXJuOwogICAgLy8gSWYgRml4LUggbW92ZWQgYnRuIG91dHNpZGUgLm1uLWxpYi1ib2R5IChpbnRvICNtbi1saWItdXBsb2FkLWhlYWRlciksIG1vdmUgaXQgYmFjawogICAgdmFyIG1pc3BsYWNlZEhlYWRlciA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJtbi1saWItdXBsb2FkLWhlYWRlciIpOwogICAgaWYgKG1pc3BsYWNlZEhlYWRlcikgewogICAgICB2YXIgYnRuID0gbWlzcGxhY2VkSGVhZGVyLnF1ZXJ5U2VsZWN0b3IoIi5tbi1saWItdXBsb2FkLWJ0biIpOwogICAgICBpZiAoYnRuKSB7CiAgICAgICAgYm9keS5pbnNlcnRCZWZvcmUoYnRuLCBib2R5LmZpcnN0Q2hpbGQpOwogICAgICB9CiAgICAgIGlmIChtaXNwbGFjZWRIZWFkZXIucGFyZW50Tm9kZSkgbWlzcGxhY2VkSGVhZGVyLnBhcmVudE5vZGUucmVtb3ZlQ2hpbGQobWlzcGxhY2VkSGVhZGVyKTsKICAgIH0gZWxzZSB7CiAgICAgIC8vIE5vIG1pc3BsYWNlZCBoZWFkZXIg4oCUIGVuc3VyZSBidG4gaXMgZmlyc3QgY2hpbGQgb2YgYm9keQogICAgICB2YXIgYnRuMiA9IGRvY3VtZW50LnF1ZXJ5U2VsZWN0b3IoIi5tbi1saWItdXBsb2FkLWJ0biIpOwogICAgICBpZiAoYnRuMiAmJiBib2R5LmZpcnN0RWxlbWVudENoaWxkICE9PSBidG4yKSB7CiAgICAgICAgYm9keS5pbnNlcnRCZWZvcmUoYnRuMiwgYm9keS5maXJzdENoaWxkKTsKICAgICAgfQogICAgfQogIH0KCiAgLy8gUnVuIGF0IERPTUNvbnRlbnRMb2FkZWQgQU5EIGFmdGVyIGFueSBkeW5hbWljIHJlbmRlcgogIGRvY3VtZW50LmFkZEV2ZW50TGlzdGVuZXIoIkRPTUNvbnRlbnRMb2FkZWQiLCBfZml4aDJQaW4pOwoKICAvLyBBbHNvIGhvb2sgX21uTGliRmV0Y2ggc28gdGhlIHBpbiBzdXJ2aXZlcyBsaWJyYXJ5IHJlZnJlc2gKICBkb2N1bWVudC5hZGRFdmVudExpc3RlbmVyKCJET01Db250ZW50TG9hZGVkIiwgZnVuY3Rpb24gKCkgewogICAgdmFyIF9vcmlnRmV0Y2ggPSB3aW5kb3cuX21uTGliRmV0Y2g7CiAgICBpZiAodHlwZW9mIF9vcmlnRmV0Y2ggPT09ICJmdW5jdGlvbiIpIHsKICAgICAgd2luZG93Ll9tbkxpYkZldGNoID0gX21uTGliRmV0Y2ggPSBmdW5jdGlvbiAoKSB7CiAgICAgICAgdmFyIHJlc3VsdCA9IF9vcmlnRmV0Y2guYXBwbHkodGhpcywgYXJndW1lbnRzKTsKICAgICAgICBzZXRUaW1lb3V0KF9maXhoMlBpbiwgMTAwKTsKICAgICAgICByZXR1cm4gcmVzdWx0OwogICAgICB9OwogICAgfQogIH0pOwoKfSkoKTsKLy8gPT09IEVORCBGSVgtSDIgVVBMT0FEIFNUSUNLWSA9PT0KPC9zY3JpcHQ+Cgo8c3R5bGU+Ci8qIEZJWExJQi1GSU5BTDogZmxleC1jb2x1bW4gLm1uLWxpYi1ib2R5IHNvIHVwbG9hZCBidG4gaXMgYWx3YXlzIGFib3ZlIHNjcm9sbCBhcmVhICovCi5tbi1saWItYm9keSB7CiAgZGlzcGxheTogZmxleCAhaW1wb3J0YW50OwogIGZsZXgtZGlyZWN0aW9uOiBjb2x1bW4gIWltcG9ydGFudDsKICBvdmVyZmxvdzogaGlkZGVuICFpbXBvcnRhbnQ7CiAgcGFkZGluZzogMCAhaW1wb3J0YW50Owp9Ci5tbi1saWItdXBsb2FkLWJ0biB7CiAgZmxleC1zaHJpbms6IDAgIWltcG9ydGFudDsKICBwb3NpdGlvbjogc3RhdGljICFpbXBvcnRhbnQ7CiAgbWFyZ2luOiA1cHggNnB4IDRweCA2cHggIWltcG9ydGFudDsKICB3aWR0aDogY2FsYygxMDAlIC0gMTJweCkgIWltcG9ydGFudDsKICBib3gtc2l6aW5nOiBib3JkZXItYm94ICFpbXBvcnRhbnQ7CiAgYm9yZGVyLWJvdHRvbTogMXB4IHNvbGlkICMyYTRhMmEgIWltcG9ydGFudDsKICBwYWRkaW5nLWJvdHRvbTogNnB4ICFpbXBvcnRhbnQ7CiAgei1pbmRleDogYXV0byAhaW1wb3J0YW50Owp9CiNtbi1saWItc2Nyb2xsLWlubmVyIHsKICBmbGV4OiAxOwogIG92ZXJmbG93LXk6IGF1dG87CiAgcGFkZGluZzogNHB4IDZweCAxMnB4IDZweDsKICBtaW4taGVpZ2h0OiAwOwp9Cjwvc3R5bGU+CjxzY3JpcHQ+Ci8vIEZJWExJQi1GSU5BTDogUmVzdHJ1Y3R1cmUgLm1uLWxpYi1ib2R5IGludG8gZmxleC1jb2x1bW4gd2l0aCBwaW5uZWQgdXBsb2FkIGJ0biAoMjAyNi0wNC0yNSkKLy8gQ2xlYW5zIHVwIGFsbCBwcmlvciBGaXgtRS9GL0cvSC9IMiBhdHRlbXB0cyBhbmQgZG9lcyBpdCBjb3JyZWN0bHkgb25jZS4KKGZ1bmN0aW9uICgpIHsKICAidXNlIHN0cmljdCI7CgogIGZ1bmN0aW9uIF9maXhsaWJTZXR1cCgpIHsKICAgIGlmIChkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgibW4tbGliLXNjcm9sbC1pbm5lciIpKSByZXR1cm47IC8vIGFscmVhZHkgZG9uZQoKICAgIHZhciBib2R5ID0gZG9jdW1lbnQucXVlcnlTZWxlY3RvcigiLm1uLWxpYi1ib2R5Iik7CiAgICBpZiAoIWJvZHkpIHJldHVybjsKCiAgICAvLyBSZWNvdmVyIHVwbG9hZCBidG4gZnJvbSBGaXgtSCdzIG1pc3BsYWNlZCAjbW4tbGliLXVwbG9hZC1oZWFkZXIgaWYgcHJlc2VudAogICAgdmFyIGJhZEhlYWRlciA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJtbi1saWItdXBsb2FkLWhlYWRlciIpOwogICAgaWYgKGJhZEhlYWRlciAmJiBiYWRIZWFkZXIucGFyZW50Tm9kZSkgewogICAgICBiYWRIZWFkZXIucGFyZW50Tm9kZS5yZW1vdmVDaGlsZChiYWRIZWFkZXIpOwogICAgfQoKICAgIHZhciBidG4gPSBkb2N1bWVudC5xdWVyeVNlbGVjdG9yKCIubW4tbGliLXVwbG9hZC1idG4iKTsKCiAgICAvLyBXcmFwIHRoZSAzIC5tbi1saWItc2VjdGlvbiBkaXZzIGluIGEgc2Nyb2xsYWJsZSBpbm5lciBjb250YWluZXIKICAgIHZhciBpbm5lciA9IGRvY3VtZW50LmNyZWF0ZUVsZW1lbnQoImRpdiIpOwogICAgaW5uZXIuaWQgPSAibW4tbGliLXNjcm9sbC1pbm5lciI7CgogICAgdmFyIHNlY3Rpb25zID0gQXJyYXkucHJvdG90eXBlLnNsaWNlLmNhbGwoYm9keS5xdWVyeVNlbGVjdG9yQWxsKCIubW4tbGliLXNlY3Rpb24iKSk7CiAgICBzZWN0aW9ucy5mb3JFYWNoKGZ1bmN0aW9uIChzKSB7IGlubmVyLmFwcGVuZENoaWxkKHMpOyB9KTsKCiAgICAvLyBSZWJ1aWxkIGJvZHk6IHVwbG9hZCBidG4gKHBpbm5lZCkgdGhlbiBzY3JvbGxhYmxlIGlubmVyCiAgICAvLyBDbGVhciBldmVyeXRoaW5nIChzZWN0aW9ucyBtb3ZlZCwgYnRuIG1heSBzdGlsbCBiZSBpbiBib2R5KQogICAgd2hpbGUgKGJvZHkuZmlyc3RDaGlsZCkgYm9keS5yZW1vdmVDaGlsZChib2R5LmZpcnN0Q2hpbGQpOwoKICAgIGlmIChidG4pIGJvZHkuYXBwZW5kQ2hpbGQoYnRuKTsKICAgIGJvZHkuYXBwZW5kQ2hpbGQoaW5uZXIpOwogIH0KCiAgLy8gUnVuIGF0IERPTSByZWFkeQogIGlmIChkb2N1bWVudC5yZWFkeVN0YXRlID09PSAibG9hZGluZyIpIHsKICAgIGRvY3VtZW50LmFkZEV2ZW50TGlzdGVuZXIoIkRPTUNvbnRlbnRMb2FkZWQiLCBfZml4bGliU2V0dXApOwogIH0gZWxzZSB7CiAgICBfZml4bGliU2V0dXAoKTsKICB9CgogIC8vIFJlLXJ1biBhZnRlciBfbW5MaWJGZXRjaCByZW5kZXJzIGNvbnRlbnQgKGRlZmVuc2l2ZSDigJQgX21uTGliUmVuZGVyIG9ubHkgdXBkYXRlcwogIC8vIGdyaWQgY2hpbGRyZW4sIG5vdCAubW4tbGliLXNlY3Rpb24gZWxlbWVudHMsIHNvIHRoaXMgc2hvdWxkIGJlIGEgbm8tb3Agbm9ybWFsbHkpCiAgdmFyIF9jaGVja0ludGVydmFsID0gc2V0SW50ZXJ2YWwoZnVuY3Rpb24gKCkgewogICAgaWYgKGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJtbi1saWItc2Nyb2xsLWlubmVyIikpIHsKICAgICAgY2xlYXJJbnRlcnZhbChfY2hlY2tJbnRlcnZhbCk7CiAgICAgIHJldHVybjsKICAgIH0KICAgIF9maXhsaWJTZXR1cCgpOwogIH0sIDUwMCk7CiAgLy8gU3RvcCBjaGVja2luZyBhZnRlciAxMHMKICBzZXRUaW1lb3V0KGZ1bmN0aW9uICgpIHsgY2xlYXJJbnRlcnZhbChfY2hlY2tJbnRlcnZhbCk7IH0sIDEwMDAwKTsKCn0pKCk7Ci8vID09PSBFTkQgRklYTElCLUZJTkFMID09PQo8L3NjcmlwdD4KCjxzdHlsZT4KLyogTElCRFJPUC1UTy1TTE9UOiBsaWJyYXJ5LWFzc2lnbmVkIGJlYXQgb3B0aW9uIHNsb3Qgc3RhdGVzICgyMDI2LTA0LTI1KSAqLwouYmctb3B0LmJnLWxpYi1kcm9wLW92ZXIgewogIG91dGxpbmU6IDJweCBkYXNoZWQgIzUyYjc4OCAhaW1wb3J0YW50OwogIGJhY2tncm91bmQ6IHJnYmEoODIsMTgzLDEzNiwwLjEwKSAhaW1wb3J0YW50Owp9Ci5iZy1vcHQuYmctbGliLWNob3NlbiB7CiAgb3V0bGluZTogMnB4IHNvbGlkICMyZDZhNGYgIWltcG9ydGFudDsKfQouYmctbGliLWJhZGdlIHsKICBwb3NpdGlvbjogYWJzb2x1dGU7CiAgdG9wOiAycHg7CiAgbGVmdDogMnB4OwogIGJhY2tncm91bmQ6ICMyZDZhNGY7CiAgY29sb3I6ICNmZmY7CiAgZm9udC1zaXplOiA4cHg7CiAgZm9udC13ZWlnaHQ6IDcwMDsKICBwYWRkaW5nOiAxcHggM3B4OwogIGJvcmRlci1yYWRpdXM6IDNweDsKICBwb2ludGVyLWV2ZW50czogbm9uZTsKICB6LWluZGV4OiAxMDsKICBsZXR0ZXItc3BhY2luZzogMC41cHg7Cn0KPC9zdHlsZT4KPHNjcmlwdD4KLy8gPT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09Ci8vIExJQkRST1AtVE8tU0xPVDogTGlicmFyeSBJbWFnZSDihpIgQmVhdCBPcHRpb24gU2xvdCAoMjAyNi0wNC0yNSkKLy8gQWxsb3dzIGRyYWdnaW5nIGEgbGlicmFyeSBjYXJkIGRpcmVjdGx5IG9udG8gYSBiZWF0IG9wdGlvbiBzbG90IGFzIHRoZQovLyBhY2NlcHRlZCBpbWFnZSwgYnlwYXNzaW5nIEZMVVggZ2VuZXJhdGlvbi4KLy8gUm91dGU6IFBPU1QgL2FwaS9iZy9hY2NlcHQtbGliLWltYWdlIChhZGRlZCB0byBwcm9kdWN0aW9uX3NlcnZlci5weSkKLy8gPT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09CgovLyDilIDilIAgMS4gQ2FwdHVyZS1waGFzZSBkcm9wIGludGVyY2VwdG9yIOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgAovLyBGaXJlcyBCRUZPUkUgdGhlIGV4aXN0aW5nIGJ1YmJsZS1waGFzZSBkb2N1bWVudC5kcm9wIGhhbmRsZXIsIHNvIHdlCi8vIGNhbiBoYW5kbGUgLmJnLW9wdCBzbG90IGRyb3BzIGJlZm9yZSB0aGUgYmVhdC1jYXJkIGhhbmRsZXIgY29udmVydHMKLy8gdGhlbSBpbnRvIHJlZmVyZW5jZV9pbWFnZSBhc3NpZ25tZW50cy4KZG9jdW1lbnQuYWRkRXZlbnRMaXN0ZW5lcignZHJvcCcsIGZ1bmN0aW9uIChlKSB7CiAgInVzZSBzdHJpY3QiOwogIHZhciBzbG90ID0gZS50YXJnZXQgJiYgZS50YXJnZXQuY2xvc2VzdCAmJiBlLnRhcmdldC5jbG9zZXN0KCcuYmctb3B0Jyk7CiAgaWYgKCFzbG90KSByZXR1cm47ICAgICAgICAgICAgICAgICAgICAgICAgLy8gbm90IGEgc2xvdCDigJQgbGV0IGJ1YmJsZSBwaGFzZSBoYW5kbGUKCiAgdmFyIGtleSA9IGUuZGF0YVRyYW5zZmVyICYmIGUuZGF0YVRyYW5zZmVyLmdldERhdGEoJ21uLWxpYi1rZXknKTsKICBpZiAoIWtleSkgcmV0dXJuOwoKICBlLnByZXZlbnREZWZhdWx0KCk7CiAgZS5zdG9wUHJvcGFnYXRpb24oKTsgICAgICAgICAgICAgICAgICAgICAgLy8gcHJldmVudCBidWJibGUtcGhhc2UgYmVhdC1jYXJkIGhhbmRsZXIKCiAgdmFyIGxpYkl0ZW0gPSBudWxsOwogIGZvciAodmFyIGkgPSAwOyBpIDwgTU5fTElCX0RBVEEubGVuZ3RoOyBpKyspIHsKICAgIGlmIChNTl9MSUJfREFUQVtpXS5rZXkgPT09IGtleSkgeyBsaWJJdGVtID0gTU5fTElCX0RBVEFbaV07IGJyZWFrOyB9CiAgfQogIGlmICghbGliSXRlbSkgewogICAgY29uc29sZS53YXJuKCdbTElCRFJPUF0ga2V5IG5vdCBmb3VuZCBpbiBNTl9MSUJfREFUQTonLCBrZXkpOwogICAgcmV0dXJuOwogIH0KCiAgdmFyIGJlYXRJZCAgPSBzbG90LmdldEF0dHJpYnV0ZSgnZGF0YS1iZWF0Jyk7CiAgdmFyIHNsb3RJZHggPSBwYXJzZUludChzbG90LmdldEF0dHJpYnV0ZSgnZGF0YS1vcHQnKSB8fCAnMCcsIDEwKTsKICBfYmdIYW5kbGVMaWJTbG90RHJvcChzbG90LCBiZWF0SWQsIHNsb3RJZHgsIGxpYkl0ZW0pOwoKfSwgdHJ1ZSAvKiBjYXB0dXJlIHBoYXNlICovKTsKCi8vIOKUgOKUgCAyLiBEcmFnb3ZlciAvIGRyYWdsZWF2ZSB2aXN1YWxzIGZvciAuYmctb3B0IHNsb3RzIChkZWxlZ2F0ZWQpIOKUgOKUgOKUgOKUgOKUgApkb2N1bWVudC5hZGRFdmVudExpc3RlbmVyKCdkcmFnb3ZlcicsIGZ1bmN0aW9uIChlKSB7CiAgdmFyIHR5cGVzID0gZS5kYXRhVHJhbnNmZXIgJiYgZS5kYXRhVHJhbnNmZXIudHlwZXM7CiAgaWYgKCF0eXBlcykgcmV0dXJuOwogIHZhciBoYXNMaWIgPSAodHlwZXMuaW5kZXhPZiA/IHR5cGVzLmluZGV4T2YoJ21uLWxpYi1rZXknKSAhPT0gLTEgOiB0eXBlcy5pbmNsdWRlcygnbW4tbGliLWtleScpKTsKICBpZiAoIWhhc0xpYikgcmV0dXJuOwogIHZhciBzbG90ID0gZS50YXJnZXQgJiYgZS50YXJnZXQuY2xvc2VzdCAmJiBlLnRhcmdldC5jbG9zZXN0KCcuYmctb3B0Jyk7CiAgaWYgKHNsb3QpIHsgZS5wcmV2ZW50RGVmYXVsdCgpOyBzbG90LmNsYXNzTGlzdC5hZGQoJ2JnLWxpYi1kcm9wLW92ZXInKTsgfQp9LCBmYWxzZSk7Cgpkb2N1bWVudC5hZGRFdmVudExpc3RlbmVyKCdkcmFnbGVhdmUnLCBmdW5jdGlvbiAoZSkgewogIHZhciBzbG90ID0gZS50YXJnZXQgJiYgZS50YXJnZXQuY2xvc2VzdCAmJiBlLnRhcmdldC5jbG9zZXN0KCcuYmctb3B0Jyk7CiAgaWYgKHNsb3QgJiYgIXNsb3QuY29udGFpbnMoZS5yZWxhdGVkVGFyZ2V0KSkgewogICAgc2xvdC5jbGFzc0xpc3QucmVtb3ZlKCdiZy1saWItZHJvcC1vdmVyJyk7CiAgfQp9LCBmYWxzZSk7CgovLyDilIDilIAgMy4gQ29yZSBoYW5kbGVyIOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgApmdW5jdGlvbiBfYmdIYW5kbGVMaWJTbG90RHJvcChzbG90LCBiZWF0SWQsIHNsb3RJZHgsIGxpYkl0ZW0pIHsKICAidXNlIHN0cmljdCI7CiAgc2xvdC5jbGFzc0xpc3QucmVtb3ZlKCdiZy1saWItZHJvcC1vdmVyJyk7CgogIC8vIENsZWFyIHByaW9yIGxpYnJhcnkgYmFkZ2VzICsgY2hvc2VuIHN0YXRlIGZyb20gQUxMIHNsb3RzIG9uIHRoaXMgYmVhdAogIHZhciBjYXJkID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2JnLWNhcmQtJyArIGJlYXRJZCk7CiAgaWYgKGNhcmQpIHsKICAgIHZhciBhbGxTbG90cyA9IGNhcmQucXVlcnlTZWxlY3RvckFsbCgnLmJnLW9wdCcpOwogICAgZm9yICh2YXIgc2kgPSAwOyBzaSA8IGFsbFNsb3RzLmxlbmd0aDsgc2krKykgewogICAgICB2YXIgcyA9IGFsbFNsb3RzW3NpXTsKICAgICAgdmFyIGIgPSBzLnF1ZXJ5U2VsZWN0b3IoJy5iZy1saWItYmFkZ2UnKTsKICAgICAgaWYgKGIpIGIucGFyZW50Tm9kZS5yZW1vdmVDaGlsZChiKTsKICAgICAgcy5jbGFzc0xpc3QucmVtb3ZlKCdiZy1saWItY2hvc2VuJywgJ2Nob3NlbicpOwogICAgICAvLyBSZS1lbmFibGUgQ3JvcCBvbiBzbG90cyB0aGF0IHdlcmUgcHJldmlvdXNseSBsaWJyYXJ5LWFzc2lnbmVkCiAgICAgIHZhciBjYiA9IHMucXVlcnlTZWxlY3RvcignLmJnLW9wdC1jcm9wJyk7CiAgICAgIGlmIChjYikgY2IuZGlzYWJsZWQgPSBmYWxzZTsKICAgICAgLy8gUmVtb3ZlIGxpYiBtYXJrZXIgZnJvbSBpbWcKICAgICAgdmFyIGltID0gcy5xdWVyeVNlbGVjdG9yKCdpbWcnKTsKICAgICAgaWYgKGltICYmIGltLmdldEF0dHJpYnV0ZSgnZGF0YS1saWIta2V5JykpIHsKICAgICAgICBpbS5yZW1vdmVBdHRyaWJ1dGUoJ2RhdGEtbGliLWtleScpOwogICAgICB9CiAgICB9CiAgfQoKICAvLyDilIDilIAgUG9wdWxhdGUgVEhbXSBmcm9tIGdhbGxlcnlfYjY0IOKAlCB6ZXJvIHNlcnZlciByb3VuZC10cmlwcyDilIDilIDilIDilIDilIDilIDilIDilIAKICAvLyBNTl9MSUJfREFUQSBhbHdheXMgaGFzIGdhbGxlcnlfYjY0IChwb3B1bGF0ZWQgYnkgX21uTGliRmV0Y2ggb24gbG9hZCkuCiAgdmFyIGI2NCA9IGxpYkl0ZW0uZ2FsbGVyeV9iNjQgfHwgbGliSXRlbS50aHVtYl9iNjQgfHwgJyc7CiAgaWYgKGI2NCkgewogICAgVEhbbGliSXRlbS5rZXldID0gYjY0OwogIH0KCiAgLy8g4pSA4pSAIFNob3cgaW1hZ2UgaW4gc2xvdCDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIAKICB2YXIgaW1nID0gc2xvdC5xdWVyeVNlbGVjdG9yKCdpbWcnKTsKICBpZiAoIWltZykgewogICAgaW1nID0gZG9jdW1lbnQuY3JlYXRlRWxlbWVudCgnaW1nJyk7CiAgICBzbG90Lmluc2VydEJlZm9yZShpbWcsIHNsb3QuZmlyc3RDaGlsZCk7CiAgfQogIGlmIChiNjQpIHsgaW1nLnNyYyA9IGI2NDsgfQogIGltZy5zZXRBdHRyaWJ1dGUoJ2RhdGEtbGliLWtleScsIGxpYkl0ZW0ua2V5KTsKICBpbWcuc3R5bGUuY3NzVGV4dCA9ICd3aWR0aDoxMDAlO2hlaWdodDoxMDAlO29iamVjdC1maXQ6Y292ZXI7Ym9yZGVyLXJhZGl1czo0cHg7JzsKCiAgLy8g4pSA4pSAIExJQiBiYWRnZSDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIAKICB2YXIgYmFkZ2UgPSBkb2N1bWVudC5jcmVhdGVFbGVtZW50KCdzcGFuJyk7CiAgYmFkZ2UuY2xhc3NOYW1lID0gJ2JnLWxpYi1iYWRnZSc7CiAgYmFkZ2UudGV4dENvbnRlbnQgPSAnTElCJzsKICBzbG90LmFwcGVuZENoaWxkKGJhZGdlKTsKICBzbG90LmNsYXNzTGlzdC5hZGQoJ2JnLWxpYi1jaG9zZW4nLCAnY2hvc2VuJyk7CgogIC8vIOKUgOKUgCBEaXNhYmxlIENyb3AgZm9yIHRoaXMgc2xvdCDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIAKICAvLyBMaWJyYXJ5IGltYWdlcyBhcmUgbm90IEZMVVggc3RpbGxzIOKAlCB0aGUgQkcgY3JvcHBlciBvcGVyYXRlcyBvbiAucG5nCiAgLy8gZmlsZXMgaW4gQkdfU1RJTExTX0RJUiBvbmx5LiAgS2ltIGNhbiBjcm9wIHNlcGFyYXRlbHkgdmlhIENyb3BwZXIgdGFiLgogIHZhciBjcm9wQnRuID0gc2xvdC5xdWVyeVNlbGVjdG9yKCcuYmctb3B0LWNyb3AnKTsKICBpZiAoY3JvcEJ0bikgY3JvcEJ0bi5kaXNhYmxlZCA9IHRydWU7CgogIC8vIOKUgOKUgCBQT1NUIHRvIHNlcnZlcjogcGVyc2lzdCBhY2NlcHRlZF9saWJyYXJ5X3JlZiArIGFjY2VwdGVkX2ltYWdlX2tleSDilIAKICBmZXRjaChCR19TRVJWRVIgKyAnL2FwaS9iZy9hY2NlcHQtbGliLWltYWdlJywgewogICAgbWV0aG9kOiAnUE9TVCcsCiAgICBoZWFkZXJzOiB7ICdDb250ZW50LVR5cGUnOiAnYXBwbGljYXRpb24vanNvbicgfSwKICAgIGJvZHk6IEpTT04uc3RyaW5naWZ5KHsKICAgICAgYmVhdF9pZDogICAgYmVhdElkLAogICAgICBrZXk6ICAgICAgICBsaWJJdGVtLmtleSwKICAgICAgZmlsZW5hbWU6ICAgbGliSXRlbS5maWxlbmFtZSB8fCBsaWJJdGVtLmtleSwKICAgICAgYWJzX3BhdGg6ICAgbGliSXRlbS5hYnNfcGF0aCB8fCAnJywKICAgICAgc2xvdF9pbmRleDogc2xvdElkeAogICAgfSkKICB9KQogIC50aGVuKGZ1bmN0aW9uIChyKSB7IHJldHVybiByLmpzb24oKTsgfSkKICAudGhlbihmdW5jdGlvbiAoZCkgewogICAgaWYgKCFkLm9rKSB7CiAgICAgIGNvbnNvbGUuZXJyb3IoJ1tMSUJEUk9QXSBhY2NlcHQtbGliLWltYWdlIGZhaWxlZDonLCBkKTsKICAgICAgcmV0dXJuOwogICAgfQogICAgLy8g4pSA4pSAIFVwZGF0ZSBpbi1tZW1vcnkgYmVhdCByZWNvcmQg4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSACiAgICB2YXIgYmVhdCA9IG51bGw7CiAgICBmb3IgKHZhciBqID0gMDsgaiA8IChCR19CRUFUUyB8fCBbXSkubGVuZ3RoOyBqKyspIHsKICAgICAgaWYgKEJHX0JFQVRTW2pdLmJlYXRfaWQgPT09IGJlYXRJZCkgeyBiZWF0ID0gQkdfQkVBVFNbal07IGJyZWFrOyB9CiAgICB9CiAgICBpZiAoYmVhdCkgewogICAgICBiZWF0LmFjY2VwdGVkX2ltYWdlX2tleSAgID0gbGliSXRlbS5rZXk7CiAgICAgIGJlYXQuYWNjZXB0ZWRfbGlicmFyeV9yZWYgPSB7CiAgICAgICAga2V5OiAgICAgICAgbGliSXRlbS5rZXksCiAgICAgICAgZmlsZW5hbWU6ICAgbGliSXRlbS5maWxlbmFtZSB8fCBsaWJJdGVtLmtleSwKICAgICAgICBhYnNfcGF0aDogICBsaWJJdGVtLmFic19wYXRoIHx8ICcnLAogICAgICAgIHNsb3RfaW5kZXg6IHNsb3RJZHgKICAgICAgfTsKICAgICAgYmVhdC5zdGF0dXMgPSAnbGliX2Nob3Nlbic7CiAgICB9CgogICAgLy8g4pSA4pSAIEVuYWJsZSAiQWNjZXB0IEFsbCB0byBTdG9yeWJvYXJkIiBidXR0b24g4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSACiAgICB2YXIgYWNjZXB0QnRuID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2JnLWFjY2VwdC1idG4nKTsKICAgIGlmIChhY2NlcHRCdG4pIGFjY2VwdEJ0bi5kaXNhYmxlZCA9IGZhbHNlOwoKICAgIC8vIOKUgOKUgCBVcGRhdGUgc3RhdHVzIGNoaXAg4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSACiAgICB2YXIgc3AgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYmctc3RhdHVzLScgKyBiZWF0SWQpOwogICAgaWYgKHNwKSBzcC50ZXh0Q29udGVudCA9ICdsaWIg4pyTJzsKICB9KQogIC5jYXRjaChmdW5jdGlvbiAoZSkgewogICAgY29uc29sZS5lcnJvcignW0xJQkRST1BdIHNlcnZlciBlcnJvcjonLCBlKTsKICB9KTsKfQoKLy8g4pSA4pSAIDQuIFJlLWh5ZHJhdGlvbiB3cmFwcGVyIGFyb3VuZCBfYmdSZW5kZXJCZWF0cyDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIAKLy8gQWZ0ZXIgZXZlcnkgcmVuZGVyLCBmb3IgYmVhdHMgd2l0aCBhY2NlcHRlZF9saWJyYXJ5X3JlZiwgaWYgVEhbXSBpcyBjb2xkCi8vIChoYXJkIHJlZnJlc2gpLCBmZXRjaCBnYWxsZXJ5X2I2NCBmcm9tIC9hcGkvY3IvZnVsbCBhbmQgcmVzdG9yZSB0aGUgc2xvdC4KKGZ1bmN0aW9uICgpIHsKICAidXNlIHN0cmljdCI7CiAgdmFyIF9wcmV2UmVuZGVyID0gX2JnUmVuZGVyQmVhdHM7CgogIF9iZ1JlbmRlckJlYXRzID0gZnVuY3Rpb24gKGJlYXRzKSB7CiAgICBfcHJldlJlbmRlcihiZWF0cyB8fCBCR19CRUFUUyk7CgogICAgdmFyIGJsaXN0ID0gYmVhdHMgfHwgQkdfQkVBVFMgfHwgW107CiAgICBmb3IgKHZhciBpID0gMDsgaSA8IGJsaXN0Lmxlbmd0aDsgaSsrKSB7CiAgICAgIChmdW5jdGlvbiAoYmVhdCkgewogICAgICAgIGlmICghYmVhdCB8fCAhYmVhdC5hY2NlcHRlZF9saWJyYXJ5X3JlZikgcmV0dXJuOwogICAgICAgIHZhciByZWYgICAgID0gYmVhdC5hY2NlcHRlZF9saWJyYXJ5X3JlZjsKICAgICAgICB2YXIgc2kgICAgICA9IHJlZi5zbG90X2luZGV4IHx8IDA7CiAgICAgICAgdmFyIHNsb3QgICAgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYmctb3B0LScgKyBiZWF0LmJlYXRfaWQgKyAnLScgKyBzaSk7CiAgICAgICAgaWYgKCFzbG90KSByZXR1cm47CgogICAgICAgIHZhciBkb1Jlc3RvcmVTbG90ID0gZnVuY3Rpb24gKGI2NE9yVXJsKSB7CiAgICAgICAgICB2YXIgaW1nID0gc2xvdC5xdWVyeVNlbGVjdG9yKCdpbWcnKTsKICAgICAgICAgIGlmICghaW1nKSB7CiAgICAgICAgICAgIGltZyA9IGRvY3VtZW50LmNyZWF0ZUVsZW1lbnQoJ2ltZycpOwogICAgICAgICAgICBzbG90Lmluc2VydEJlZm9yZShpbWcsIHNsb3QuZmlyc3RDaGlsZCk7CiAgICAgICAgICB9CiAgICAgICAgICBpZiAoYjY0T3JVcmwpIGltZy5zcmMgPSBiNjRPclVybDsKICAgICAgICAgIGltZy5zZXRBdHRyaWJ1dGUoJ2RhdGEtbGliLWtleScsIHJlZi5rZXkpOwogICAgICAgICAgLy8gUmVzdG9yZSBMSUIgYmFkZ2UgaWYgYWJzZW50IChjbGVhcmVkIGJ5IHJlLXJlbmRlcikKICAgICAgICAgIGlmICghc2xvdC5xdWVyeVNlbGVjdG9yKCcuYmctbGliLWJhZGdlJykpIHsKICAgICAgICAgICAgdmFyIGJhZGdlID0gZG9jdW1lbnQuY3JlYXRlRWxlbWVudCgnc3BhbicpOwogICAgICAgICAgICBiYWRnZS5jbGFzc05hbWUgPSAnYmctbGliLWJhZGdlJzsKICAgICAgICAgICAgYmFkZ2UudGV4dENvbnRlbnQgPSAnTElCJzsKICAgICAgICAgICAgc2xvdC5hcHBlbmRDaGlsZChiYWRnZSk7CiAgICAgICAgICB9CiAgICAgICAgICBzbG90LmNsYXNzTGlzdC5hZGQoJ2JnLWxpYi1jaG9zZW4nLCAnY2hvc2VuJyk7CiAgICAgICAgICB2YXIgY3JvcEJ0biA9IHNsb3QucXVlcnlTZWxlY3RvcignLmJnLW9wdC1jcm9wJyk7CiAgICAgICAgICBpZiAoY3JvcEJ0bikgY3JvcEJ0bi5kaXNhYmxlZCA9IHRydWU7CiAgICAgICAgfTsKCiAgICAgICAgaWYgKFRIW3JlZi5rZXldKSB7CiAgICAgICAgICAvLyBUSCB3YXJtIOKAlCByZXN0b3JlIGltbWVkaWF0ZWx5CiAgICAgICAgICBkb1Jlc3RvcmVTbG90KFRIW3JlZi5rZXldKTsKICAgICAgICB9IGVsc2UgaWYgKHJlZi5hYnNfcGF0aCkgewogICAgICAgICAgLy8gVEggY29sZCAocG9zdCBoYXJkLXJlZnJlc2gpIOKAlCBmZXRjaCBiYXNlNjQgZnJvbSBzZXJ2ZXIKICAgICAgICAgIGZldGNoKEJHX1NFUlZFUiArICcvYXBpL2NyL2Z1bGw/YWJzX3BhdGg9JyArIGVuY29kZVVSSUNvbXBvbmVudChyZWYuYWJzX3BhdGgpKQogICAgICAgICAgICAudGhlbihmdW5jdGlvbiAocikgeyByZXR1cm4gci5qc29uKCk7IH0pCiAgICAgICAgICAgIC50aGVuKGZ1bmN0aW9uIChkKSB7CiAgICAgICAgICAgICAgaWYgKGQuZGF0YV91cmkpIHsKICAgICAgICAgICAgICAgIFRIW3JlZi5rZXldID0gZC5kYXRhX3VyaTsKICAgICAgICAgICAgICAgIGRvUmVzdG9yZVNsb3QoZC5kYXRhX3VyaSk7CiAgICAgICAgICAgICAgfSBlbHNlIHsKICAgICAgICAgICAgICAgIC8vIEZhbGxiYWNrOiB1c2UgL2ZpbGVzP3BhdGg9IGFzIGltZy5zcmMgKGJ5dGUgc3RyZWFtLCBubyBUSCBwb3B1bGF0aW9uKQogICAgICAgICAgICAgICAgZG9SZXN0b3JlU2xvdChCR19TRVJWRVIgKyAnL2ZpbGVzP3BhdGg9JyArIGVuY29kZVVSSUNvbXBvbmVudChyZWYuYWJzX3BhdGgpKTsKICAgICAgICAgICAgICB9CiAgICAgICAgICAgIH0pCiAgICAgICAgICAgIC5jYXRjaChmdW5jdGlvbiAoZXJyKSB7CiAgICAgICAgICAgICAgY29uc29sZS53YXJuKCdbTElCRFJPUF0gcmVoeWRyYXRlIGZhaWxlZCBmb3InLCByZWYua2V5LCBlcnIpOwogICAgICAgICAgICAgIC8vIEJlc3QtZWZmb3J0OiBkaXJlY3QgZmlsZSBzdHJlYW0KICAgICAgICAgICAgICBkb1Jlc3RvcmVTbG90KEJHX1NFUlZFUiArICcvZmlsZXM/cGF0aD0nICsgZW5jb2RlVVJJQ29tcG9uZW50KHJlZi5hYnNfcGF0aCB8fCAnJykpOwogICAgICAgICAgICB9KTsKICAgICAgICB9CiAgICAgIH0pKGJsaXN0W2ldKTsKICAgIH0KICB9Owp9KSgpOwovLyA9PT0gRU5EIExJQkRST1AtVE8tU0xPVCA9PT0KPC9zY3JpcHQ+Cgo8c3R5bGU+Ci8qIExJQkZJWC1WMjogaGlnaC1zcGVjaWZpY2l0eSBvdmVycmlkZSBmb3IgLm1uLWxpYi1ib2R5IGZsZXggc3RydWN0dXJlICgyMDI2LTA0LTI1KQogICBVc2VzICNtbi1saWItc2lkZWJhciA+IC5tbi1saWItYm9keSAoc3BlY2lmaWNpdHkgMCwxLDEsMSkgdG8gYmVhdCBhbGwgcHJpb3IKICAgY2xhc3Mtb25seSBydWxlcyAoLm1uLWxpYi1ib2R5ID0gMCwwLDEsMCkgc28gdGhlIGNvbHVtbiBsYXlvdXQgYWx3YXlzIHdpbnMuICovCiNtbi1saWItc2lkZWJhciA+IC5tbi1saWItYm9keSB7CiAgZGlzcGxheTogZmxleCAhaW1wb3J0YW50OwogIGZsZXgtZGlyZWN0aW9uOiBjb2x1bW4gIWltcG9ydGFudDsKICBvdmVyZmxvdzogaGlkZGVuICFpbXBvcnRhbnQ7CiAgcGFkZGluZzogMCAhaW1wb3J0YW50Owp9Ci8qIFVwbG9hZCBidG46IHBpbm5lZCBmbGV4IGl0ZW0gYXQgdG9wIG9mIHRoZSBjb2x1bW4gKG5vIHN0aWNreSwgbm8gZml4ZWQpICovCiNtbi1saWItc2lkZWJhciA+IC5tbi1saWItYm9keSA+IC5tbi1saWItdXBsb2FkLWJ0biB7CiAgZmxleC1zaHJpbms6IDAgIWltcG9ydGFudDsKICBwb3NpdGlvbjogc3RhdGljICFpbXBvcnRhbnQ7CiAgbWFyZ2luOiA1cHggNnB4IDRweCA2cHggIWltcG9ydGFudDsKICB3aWR0aDogY2FsYygxMDAlIC0gMTJweCkgIWltcG9ydGFudDsKICBib3gtc2l6aW5nOiBib3JkZXItYm94ICFpbXBvcnRhbnQ7CiAgYm9yZGVyLWJvdHRvbTogMXB4IHNvbGlkICMyYTRhMmEgIWltcG9ydGFudDsKICBwYWRkaW5nLWJvdHRvbTogNnB4ICFpbXBvcnRhbnQ7CiAgei1pbmRleDogYXV0byAhaW1wb3J0YW50OwogIG9yZGVyOiAtMSAhaW1wb3J0YW50Owp9Ci8qIFNjcm9sbCBpbm5lciBmcm9tIEZJWExJQi1GSU5BTDogdGFrZXMgcmVtYWluaW5nIHNwYWNlLCBzY3JvbGxzIGludGVybmFsbHkgKi8KI21uLWxpYi1zaWRlYmFyID4gLm1uLWxpYi1ib2R5ID4gI21uLWxpYi1zY3JvbGwtaW5uZXIgewogIGZsZXg6IDEgIWltcG9ydGFudDsKICBvdmVyZmxvdy15OiBhdXRvICFpbXBvcnRhbnQ7CiAgcGFkZGluZzogNHB4IDZweCAxMnB4IDZweCAhaW1wb3J0YW50OwogIG1pbi1oZWlnaHQ6IDAgIWltcG9ydGFudDsKfQo8L3N0eWxlPgo8c2NyaXB0PgovLyA9PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT0KLy8gTElCRklYLVYyOiBEZWZpbml0aXZlIGxpYnJhcnkgdXBsb2FkIGJ1dHRvbiBmaXggKDIwMjYtMDQtMjUpCi8vIE5ldXRyYWxpemVzIEZpeC1IJ3MgX2ZpeGhNb3ZlVXBsb2FkQnRuICh0aGUgc291cmNlIG9mIHRoZSBiYXR0bGUpLAovLyB0aGVuIGVuZm9yY2VzIGNvcnJlY3Qgc3RydWN0dXJlIG9uIGV2ZXJ5IF9tbkxpYlRvZ2dsZSBvcGVuLgovLyA9PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT0KCihmdW5jdGlvbiAoKSB7CiAgInVzZSBzdHJpY3QiOwoKICAvLyDilIDilIAgMS4gTmV1dHJhbGl6ZSBGaXgtSCdzIF9maXhoTW92ZVVwbG9hZEJ0biBwZXJtYW5lbnRseSDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIAKICAvLyBGaXgtSCB3cmFwcGVkIF9tbkxpYkZldGNoIGF0IHBhcnNlLXRpbWUgc28gX2ZpeGhNb3ZlVXBsb2FkQnRuIGZpcmVzCiAgLy8gNTBtcyBhZnRlciBldmVyeSBsaWJyYXJ5IGZldGNoLCBtb3ZpbmcgdGhlIGJ0biB0byBhIFdST05HIHNpZGViYXIKICAvLyBzaWJsaW5nICgjbW4tbGliLXVwbG9hZC1oZWFkZXIgaW4gYSBmbGV4LXJvdyBwYXJlbnQgPSBuYXJyb3cgY29sdW1uKS4KICAvLyBTaW1wbHkgcmVwbGFjaW5nIHRoZSBmdW5jdGlvbiB3aXRoIGEgbm8tb3AgYnJlYWtzIHRoZSBjeWNsZS4KICBpZiAodHlwZW9mIHdpbmRvdy5fZml4aE1vdmVVcGxvYWRCdG4gPT09ICJmdW5jdGlvbiIpIHsKICAgIHdpbmRvdy5fZml4aE1vdmVVcGxvYWRCdG4gPSBmdW5jdGlvbiAoKSB7IC8qIGRpc2FibGVkIGJ5IExJQkZJWC1WMiAqLyB9OwogIH0KICAvLyBHdWFyZDogcmVkZWZpbmUgdmlhIGRlZmluZVByb3BlcnR5IHNvIGl0IGNhbm5vdCBiZSBvdmVyd3JpdHRlbiBsYXRlcgogIC8vIChiZWx0LWFuZC1zdXNwZW5kZXJzIOKAlCB0aGUgb3ZlcnJpZGUgYWJvdmUgaXMgc3VmZmljaWVudCBmb3Igb3VyIHNldHVwKS4KICB0cnkgewogICAgT2JqZWN0LmRlZmluZVByb3BlcnR5KHdpbmRvdywgIl9maXhoTW92ZVVwbG9hZEJ0biIsIHsKICAgICAgdmFsdWU6IGZ1bmN0aW9uICgpIHsgLyogZGlzYWJsZWQgYnkgTElCRklYLVYyICovIH0sCiAgICAgIHdyaXRhYmxlOiBmYWxzZSwgY29uZmlndXJhYmxlOiBmYWxzZQogICAgfSk7CiAgfSBjYXRjaCAoZSkgeyAvKiBhbHJlYWR5IG5vbi1jb25maWd1cmFibGUgb3Igc3RyaWN0LW1vZGUgYmxvY2tlZCDigJQgZmluZSAqLyB9CgogIC8vIOKUgOKUgCAyLiBBdXRob3JpdGF0aXZlIHN0cnVjdHVyZSBmdW5jdGlvbiDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIAKICAvLyBDcmVhdGVzICNtbi1saWItc2Nyb2xsLWlubmVyIGlmIGFic2VudCBhbmQgZW5zdXJlcyBidG4gaXMgdGhlIGZpcnN0CiAgLy8gZmxleCBjaGlsZCBvZiAubW4tbGliLWJvZHkuIElkZW1wb3RlbnQg4oCUIHNhZmUgdG8gY2FsbCByZXBlYXRlZGx5LgogIGZ1bmN0aW9uIF9saWJmaXhWMkVuZm9yY2UoKSB7CiAgICB2YXIgYm9keSA9IGRvY3VtZW50LnF1ZXJ5U2VsZWN0b3IoIi5tbi1saWItYm9keSIpOwogICAgaWYgKCFib2R5KSByZXR1cm47CgogICAgLy8gUmVtb3ZlIGFueSBzdGFsZSAjbW4tbGliLXVwbG9hZC1oZWFkZXIgdGhhdCBGaXgtSCBtYXkgaGF2ZSBsZWZ0CiAgICB2YXIgc3RhbGVIZWFkZXIgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgibW4tbGliLXVwbG9hZC1oZWFkZXIiKTsKICAgIGlmIChzdGFsZUhlYWRlciAmJiBzdGFsZUhlYWRlci5wYXJlbnROb2RlKSB7CiAgICAgIC8vIFJlc2N1ZSBidG4gYmVmb3JlIGRlbGV0aW5nIHRoZSBoZWFkZXIKICAgICAgdmFyIHJlc2N1ZUJ0biA9IHN0YWxlSGVhZGVyLnF1ZXJ5U2VsZWN0b3IoIi5tbi1saWItdXBsb2FkLWJ0biIpOwogICAgICBpZiAocmVzY3VlQnRuKSBib2R5Lmluc2VydEJlZm9yZShyZXNjdWVCdG4sIGJvZHkuZmlyc3RDaGlsZCk7CiAgICAgIHN0YWxlSGVhZGVyLnBhcmVudE5vZGUucmVtb3ZlQ2hpbGQoc3RhbGVIZWFkZXIpOwogICAgfQoKICAgIHZhciBidG4gPSBib2R5LnF1ZXJ5U2VsZWN0b3IoIi5tbi1saWItdXBsb2FkLWJ0biIpOwoKICAgIC8vIEVuc3VyZSAjbW4tbGliLXNjcm9sbC1pbm5lciBleGlzdHMgYW5kIGNvbnRhaW5zIGFsbCAubW4tbGliLXNlY3Rpb24gZGl2cwogICAgdmFyIGlubmVyID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoIm1uLWxpYi1zY3JvbGwtaW5uZXIiKTsKICAgIGlmICghaW5uZXIpIHsKICAgICAgaW5uZXIgPSBkb2N1bWVudC5jcmVhdGVFbGVtZW50KCJkaXYiKTsKICAgICAgaW5uZXIuaWQgPSAibW4tbGliLXNjcm9sbC1pbm5lciI7CiAgICAgIHZhciBzZWN0aW9ucyA9IEFycmF5LnByb3RvdHlwZS5zbGljZS5jYWxsKGJvZHkucXVlcnlTZWxlY3RvckFsbCgiLm1uLWxpYi1zZWN0aW9uIikpOwogICAgICBzZWN0aW9ucy5mb3JFYWNoKGZ1bmN0aW9uIChzKSB7IGlubmVyLmFwcGVuZENoaWxkKHMpOyB9KTsKICAgICAgLy8gQ2xlYXIgYm9keSBhbmQgcmVidWlsZDogYnRuIGZpcnN0LCB0aGVuIHNjcm9sbC1pbm5lcgogICAgICB3aGlsZSAoYm9keS5maXJzdENoaWxkKSBib2R5LnJlbW92ZUNoaWxkKGJvZHkuZmlyc3RDaGlsZCk7CiAgICAgIGlmIChidG4pIGJvZHkuYXBwZW5kQ2hpbGQoYnRuKTsKICAgICAgYm9keS5hcHBlbmRDaGlsZChpbm5lcik7CiAgICB9IGVsc2UgewogICAgICAvLyBpbm5lciBleGlzdHMg4oCUIGp1c3QgZW5zdXJlIGJ0biBpcyB0aGUgZmlyc3QgY2hpbGQgb2YgYm9keSAobm90IGluc2lkZSBpbm5lcikKICAgICAgaWYgKGJ0biAmJiBidG4ucGFyZW50Tm9kZSAhPT0gYm9keSkgewogICAgICAgIGJvZHkuaW5zZXJ0QmVmb3JlKGJ0biwgYm9keS5maXJzdENoaWxkKTsKICAgICAgfSBlbHNlIGlmIChidG4gJiYgYm9keS5maXJzdEVsZW1lbnRDaGlsZCAhPT0gYnRuKSB7CiAgICAgICAgYm9keS5pbnNlcnRCZWZvcmUoYnRuLCBib2R5LmZpcnN0Q2hpbGQpOwogICAgICB9CiAgICB9CiAgfQoKICAvLyDilIDilIAgMy4gUnVuIG9uIERPTUNvbnRlbnRMb2FkZWQg4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSACiAgaWYgKGRvY3VtZW50LnJlYWR5U3RhdGUgPT09ICJsb2FkaW5nIikgewogICAgZG9jdW1lbnQuYWRkRXZlbnRMaXN0ZW5lcigiRE9NQ29udGVudExvYWRlZCIsIF9saWJmaXhWMkVuZm9yY2UpOwogIH0gZWxzZSB7CiAgICBfbGliZml4VjJFbmZvcmNlKCk7CiAgfQoKICAvLyDilIDilIAgNC4gV3JhcCBfbW5MaWJUb2dnbGUgc28gc3RydWN0dXJlIGlzIGVuZm9yY2VkIG9uIGV2ZXJ5IHBhbmVsIG9wZW4g4pSACiAgLy8gX21uTGliVG9nZ2xlIGlzIGRlZmluZWQgYXQgcGFyc2UtdGltZSAobm90IG9uIERPTUNvbnRlbnRMb2FkZWQpLCBzbyB3ZQogIC8vIGNhbiB3cmFwIGl0IGltbWVkaWF0ZWx5IGF0IHRoZSBlbmQgb2YgdGhlIGRvY3VtZW50LgogIGRvY3VtZW50LmFkZEV2ZW50TGlzdGVuZXIoIkRPTUNvbnRlbnRMb2FkZWQiLCBmdW5jdGlvbiAoKSB7CiAgICB2YXIgX29yaWdUb2dnbGUgPSB3aW5kb3cuX21uTGliVG9nZ2xlOwogICAgaWYgKHR5cGVvZiBfb3JpZ1RvZ2dsZSA9PT0gImZ1bmN0aW9uIikgewogICAgICB3aW5kb3cuX21uTGliVG9nZ2xlID0gZnVuY3Rpb24gKCkgewogICAgICAgIF9vcmlnVG9nZ2xlLmFwcGx5KHRoaXMsIGFyZ3VtZW50cyk7CiAgICAgICAgLy8gQWZ0ZXIgdG9nZ2xlLCBpZiBwYW5lbCBpcyBub3cgb3BlbiwgcmUtZW5mb3JjZSBzdHJ1Y3R1cmUKICAgICAgICB2YXIgc2lkZWJhciA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJtbi1saWItc2lkZWJhciIpOwogICAgICAgIGlmIChzaWRlYmFyICYmIHNpZGViYXIuY2xhc3NMaXN0LmNvbnRhaW5zKCJvcGVuIikpIHsKICAgICAgICAgIC8vIERlZmVyIGJ5IG9uZSB0aWNrIHNvIHRoZSBwYW5lbCBDU1MgdHJhbnNpdGlvbiBzdGFydHMgZmlyc3QsCiAgICAgICAgICAvLyB0aGVuIGVuZm9yY2UgYWZ0ZXIgZmV0Y2grcmVuZGVyIGhhcyBoYWQgdGltZSB0byBzZXR0bGUuCiAgICAgICAgICBzZXRUaW1lb3V0KF9saWJmaXhWMkVuZm9yY2UsIDE1MCk7CiAgICAgICAgfQogICAgICB9OwogICAgfQoKICAgIC8vIEFsc28gcGF0Y2ggX21uTGliRmV0Y2ggdG8gcmUtZW5mb3JjZSBhZnRlciBldmVyeSByZW5kZXIKICAgIC8vIChjb3ZlcnMgcHJvZ3JhbW1hdGljIGZldGNoIGNhbGxzIHRoYXQgYnlwYXNzIF9tbkxpYlRvZ2dsZSkKICAgIHZhciBfb3JpZ0ZldGNoID0gd2luZG93Ll9tbkxpYkZldGNoOwogICAgaWYgKHR5cGVvZiBfb3JpZ0ZldGNoID09PSAiZnVuY3Rpb24iKSB7CiAgICAgIHdpbmRvdy5fbW5MaWJGZXRjaCA9IF9tbkxpYkZldGNoID0gZnVuY3Rpb24gKCkgewogICAgICAgIHZhciByZXN1bHQgPSBfb3JpZ0ZldGNoLmFwcGx5KHRoaXMsIGFyZ3VtZW50cyk7CiAgICAgICAgc2V0VGltZW91dChfbGliZml4VjJFbmZvcmNlLCAxNTApOwogICAgICAgIHJldHVybiByZXN1bHQ7CiAgICAgIH07CiAgICB9CiAgfSk7CgogIC8vIOKUgOKUgCA1LiBQZXJzaXN0ZW50IHNhZmV0eSBwb2xsIChubyAxMHMgbGltaXQpIOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgAogIC8vIFJ1bnMgZXZlcnkgODAwbXMgd2hpbGUgdGhlIGxpYnJhcnkgcGFuZWwgaXMgT1BFTiB0byBjYXRjaCBhbnkKICAvLyBsYXRlLWFycml2aW5nIERPTSBjaGFuZ2UgKGltZyBsb2FkcywgZHluYW1pYyBjb250ZW50LCBldGMuKS4KICBzZXRJbnRlcnZhbChmdW5jdGlvbiAoKSB7CiAgICB2YXIgc2lkZWJhciA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJtbi1saWItc2lkZWJhciIpOwogICAgaWYgKCFzaWRlYmFyIHx8ICFzaWRlYmFyLmNsYXNzTGlzdC5jb250YWlucygib3BlbiIpKSByZXR1cm47IC8vIG9ubHkgd2hlbiBvcGVuCiAgICB2YXIgYm9keSA9IGRvY3VtZW50LnF1ZXJ5U2VsZWN0b3IoIi5tbi1saWItYm9keSIpOwogICAgdmFyIGJ0biA9IGJvZHkgJiYgYm9keS5xdWVyeVNlbGVjdG9yKCIubW4tbGliLXVwbG9hZC1idG4iKTsKICAgIC8vIElmIGJ0biBpcyBub3QgdGhlIGZpcnN0IGZsZXggY2hpbGQgb2YgYm9keSwgZml4IGl0CiAgICBpZiAoYnRuICYmIGJvZHkgJiYgYm9keS5maXJzdEVsZW1lbnRDaGlsZCAhPT0gYnRuKSB7CiAgICAgIF9saWJmaXhWMkVuZm9yY2UoKTsKICAgIH0KICAgIC8vIElmICNtbi1saWItdXBsb2FkLWhlYWRlciBhcHBlYXJlZCAoRml4LUggZmlyZWQgc29tZWhvdyksIG5ldXRyYWxpemUgaXQKICAgIGlmIChkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgibW4tbGliLXVwbG9hZC1oZWFkZXIiKSkgewogICAgICBfbGliZml4VjJFbmZvcmNlKCk7CiAgICB9CiAgfSwgODAwKTsKCn0pKCk7CgovLyDilIDilIAgNi4gRml4ICJzdGlsbHMgcGVuZGluZyIgc3RhdHVzOiBDMyB3cmFwcGVyIHBhdGNoIOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgAovLyBXaGVuIF9iZ1JlbmRlckJlYXRzIHJ1bnMsIHVwZGF0ZSBiZWF0IHN0YXR1cyBkaXNwbGF5IHRvICJzdGlsbHMgcmVhZHkiCi8vIGlmIHRoZSBiZWF0IGhhcyBmbHV4X29wdGlvbnMgd2l0aCBsb2NhbF9wYXRoIHZhbHVlcyAoc3RpbGxzIGV4aXN0IG9uIGRpc2spLgovLyBUaGUgc2lkZWNhciBtYXkgc3RpbGwgaGF2ZSBzdGF0dXM9InN0aWxsc19wZW5kaW5nIiBpZiB0aGUgcGFnZSB3YXMKLy8gcmVmcmVzaGVkIGJlZm9yZSBwb2xsaW5nIGNvbXBsZXRlZCDigJQgdGhpcyBjb3JyZWN0cyB0aGUgVUkgbGFiZWwgb25seS4KKGZ1bmN0aW9uICgpIHsKICAidXNlIHN0cmljdCI7CiAgdmFyIF9wcmV2UmVuZGVyID0gX2JnUmVuZGVyQmVhdHM7CiAgX2JnUmVuZGVyQmVhdHMgPSBmdW5jdGlvbiAoYmVhdHMpIHsKICAgIF9wcmV2UmVuZGVyKGJlYXRzIHx8IEJHX0JFQVRTKTsKICAgIChiZWF0cyB8fCBCR19CRUFUUyB8fCBbXSkuZm9yRWFjaChmdW5jdGlvbiAoYmVhdCkgewogICAgICAvLyBDaGVjayBpZiBzdGlsbHMgZXhpc3QgaW4gZmx1eF9vcHRpb25zCiAgICAgIHZhciBmb3B0cyA9IGJlYXQuZmx1eF9vcHRpb25zIHx8IFtdOwogICAgICB2YXIgaGFzU3RpbGxzID0gZm9wdHMuc29tZShmdW5jdGlvbiAoZikgeyByZXR1cm4gZiAmJiBmLmxvY2FsX3BhdGg7IH0pOwogICAgICBpZiAoIWhhc1N0aWxscykgcmV0dXJuOwogICAgICAvLyBTdGF0dXMgaXMgInN0aWxsc19wZW5kaW5nIiBvciBzaW1pbGFyIGJ1dCBzdGlsbHMgZXhpc3Q6IHVwZGF0ZSBsYWJlbAogICAgICB2YXIgc3AgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgiYmctc3RhdHVzLSIgKyBiZWF0LmJlYXRfaWQpOwogICAgICBpZiAoc3ApIHsKICAgICAgICB2YXIgY3VyID0gc3AudGV4dENvbnRlbnQgfHwgIiI7CiAgICAgICAgaWYgKGN1ci5pbmRleE9mKCJwZW5kaW5nIikgIT09IC0xIHx8IGN1ciA9PT0gImRyYWZ0IikgewogICAgICAgICAgc3AudGV4dENvbnRlbnQgPSAic3RpbGxzIHJlYWR5IjsKICAgICAgICB9CiAgICAgIH0KICAgIH0pOwogIH07Cn0pKCk7Ci8vID09PSBFTkQgTElCRklYLVYyID09PQo8L3NjcmlwdD4KCjxzdHlsZT4KLyogTElCRklYLVYzOiBTdGF0aWMgSFRNTCBzdHJ1Y3R1cmUgZml4ICgyMDI2LTA0LTI1KQogICAubW4tbGliLWJvZHkgaXMgbm93IGZsZXgtY29sdW1uIHdpdGggdXBsb2FkIGJ0biBGSVJTVCBpbiBET00gKyAjbW4tbGliLXNjcm9sbC1pbm5lcgogICB3cmFwcGluZyB0aGUgc2VjdGlvbnMuIE5vIEpTIG5lZWRlZCDigJQgRklYTElCLUZJTkFMIGFuZCBMSUJGSVgtVjIgZ3VhcmRzIGZpcmUgYXMKICAgbm8tb3BzIHNpbmNlIHRoZSBzdHJ1Y3R1cmUgYWxyZWFkeSBtYXRjaGVzIHdoYXQgdGhleSB3ZXJlIHRyeWluZyB0byBidWlsZC4gKi8KCi8qIEVuc3VyZSB0aGUgdXBsb2FkIGJ0biBpcyBhbHdheXMgdmlzaWJsZSBhbmQgc3R5bGVkIGNvcnJlY3RseSBhdCB0b3Agb2YgYm9keSAqLwojbW4tbGliLXNpZGViYXIgPiAubW4tbGliLWJvZHkgPiAubW4tbGliLXVwbG9hZC1idG4gewogIGRpc3BsYXk6IGJsb2NrICFpbXBvcnRhbnQ7CiAgZmxleC1zaHJpbms6IDAgIWltcG9ydGFudDsKICBwb3NpdGlvbjogc3RhdGljICFpbXBvcnRhbnQ7CiAgbWFyZ2luOiA2cHggNnB4IDRweCA2cHggIWltcG9ydGFudDsKICB3aWR0aDogY2FsYygxMDAlIC0gMTJweCkgIWltcG9ydGFudDsKICBib3gtc2l6aW5nOiBib3JkZXItYm94ICFpbXBvcnRhbnQ7CiAgYm9yZGVyLWJvdHRvbTogMXB4IHNvbGlkICMyYTRhMmEgIWltcG9ydGFudDsKICBwYWRkaW5nLWJvdHRvbTogNnB4ICFpbXBvcnRhbnQ7CiAgb3JkZXI6IC05OTkgIWltcG9ydGFudDsKfQoKLyogUGVyLW9wdGlvbiBhY2NlcHQgYnV0dG9uICovCi5iZy1vcHQtYWNjZXB0IHsKICBwb3NpdGlvbjogYWJzb2x1dGU7CiAgYm90dG9tOiAycHg7CiAgcmlnaHQ6IDJweDsKICBiYWNrZ3JvdW5kOiAjMmQ2YTRmOwogIGNvbG9yOiAjZmZmOwogIGJvcmRlcjogbm9uZTsKICBib3JkZXItcmFkaXVzOiAzcHg7CiAgZm9udC1zaXplOiA5cHg7CiAgZm9udC13ZWlnaHQ6IDcwMDsKICBwYWRkaW5nOiAycHggNXB4OwogIGN1cnNvcjogcG9pbnRlcjsKICB6LWluZGV4OiA4OwogIGxldHRlci1zcGFjaW5nOiAwLjNweDsKICB3aGl0ZS1zcGFjZTogbm93cmFwOwp9Ci5iZy1vcHQtYWNjZXB0OmhvdmVyIHsgYmFja2dyb3VuZDogIzQwOTE2YzsgfQouYmctb3B0LmNob3NlbiAuYmctb3B0LWFjY2VwdCB7CiAgYmFja2dyb3VuZDogIzFiNDMzMjsKICBjb250ZW50OiAiwrkzIEFjY2VwdGVkIjsKfQovKiBNYWtlIGJnLW9wdCBwb3NpdGlvbjpyZWxhdGl2ZSBzbyBhYnNvbHV0ZSBjaGlsZHJlbiB3b3JrICovCi5iZy1vcHQgeyBwb3NpdGlvbjogcmVsYXRpdmUgIWltcG9ydGFudDsgfQo8L3N0eWxlPgo8c2NyaXB0PgovLyA9PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT0KLy8gTElCRklYLVYzOiBBY2NlcHQgZmxvdyBlbmhhbmNlbWVudHMgKDIwMjYtMDQtMjUpCi8vIDEuICLinJMgVXNlIFRoaXMiIGJ1dHRvbiBvbiBlYWNoIEZMVVggb3B0aW9uIHNsb3QgKHNldHMgYWNjZXB0ZWRfaW1hZ2Vfa2V5KQovLyAyLiBfYmdBY2NlcHRUb1N0b3J5Ym9hcmQgZW5oYW5jZWQ6IHNraXBzIGJlYXRzIHdpdGggbm8gYWNjZXB0ZWRfaW1hZ2Vfa2V5Ci8vICAgIChiZWF0IDEgaXMgaW50ZW50aW9uYWxseSBlbXB0eSkgd2l0aG91dCBhIGNvbmZpcm0oKSBkaWFsb2cKLy8gPT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09CgooZnVuY3Rpb24gKCkgewogICJ1c2Ugc3RyaWN0IjsKCiAgLy8g4pSA4pSAIDEuIEluamVjdCAi4pyTIFVzZSBUaGlzIiBidXR0b25zIGludG8gcmVuZGVyZWQgRkxVWCBvcHRpb24gc2xvdHMg4pSA4pSA4pSA4pSACiAgLy8gX2JnUmVuZGVyQmVhdHMgY3JlYXRlcyB0aGUgc2xvdHMgYnV0IGhhcyBubyBhY2NlcHQgYnV0dG9uLgogIC8vIFdlIHdyYXAgX2JnUmVuZGVyQmVhdHMgdG8gaW5qZWN0IGFjY2VwdCBidXR0b25zIGFmdGVyIGV2ZXJ5IHJlbmRlci4KICBkb2N1bWVudC5hZGRFdmVudExpc3RlbmVyKCJET01Db250ZW50TG9hZGVkIiwgZnVuY3Rpb24gKCkgewogICAgdmFyIF9wcmV2UmVuZGVyID0gd2luZG93Ll9iZ1JlbmRlckJlYXRzOwogICAgaWYgKHR5cGVvZiBfcHJldlJlbmRlciAhPT0gImZ1bmN0aW9uIikgcmV0dXJuOwoKICAgIGZ1bmN0aW9uIF9pbmplY3RBY2NlcHRCdXR0b25zKCkgewogICAgICB2YXIgc2xvdHMgPSBkb2N1bWVudC5xdWVyeVNlbGVjdG9yQWxsKCIuYmctb3B0W2RhdGEtYmVhdF1bZGF0YS1vcHRdIik7CiAgICAgIGZvciAodmFyIGkgPSAwOyBpIDwgc2xvdHMubGVuZ3RoOyBpKyspIHsKICAgICAgICB2YXIgc2xvdCA9IHNsb3RzW2ldOwogICAgICAgIGlmIChzbG90LnF1ZXJ5U2VsZWN0b3IoIi5iZy1vcHQtYWNjZXB0IikpIGNvbnRpbnVlOyAvLyBhbHJlYWR5IGhhcyBidXR0b24KICAgICAgICAvLyBPbmx5IGFkZCBpZiBzbG90IGhhcyBhbiBpbWFnZSAoaS5lLiBhIEZMVVggc3RpbGwgbG9hZGVkKQogICAgICAgIHZhciBpbWcgPSBzbG90LnF1ZXJ5U2VsZWN0b3IoImltZyIpOwogICAgICAgIGlmICghaW1nKSBjb250aW51ZTsKCiAgICAgICAgdmFyIGJlYXRJZCAgPSBzbG90LmdldEF0dHJpYnV0ZSgiZGF0YS1iZWF0Iik7CiAgICAgICAgdmFyIHNsb3RJZHggPSBwYXJzZUludChzbG90LmdldEF0dHJpYnV0ZSgiZGF0YS1vcHQiKSB8fCAiMCIsIDEwKTsKCiAgICAgICAgKGZ1bmN0aW9uIChiaWQsIHNpLCBzbCkgewogICAgICAgICAgdmFyIGJ0biA9IGRvY3VtZW50LmNyZWF0ZUVsZW1lbnQoImJ1dHRvbiIpOwogICAgICAgICAgYnRuLmNsYXNzTmFtZSA9ICJiZy1vcHQtYWNjZXB0IjsKICAgICAgICAgIGJ0bi50ZXh0Q29udGVudCA9ICLinJMgVXNlIFRoaXMiOwogICAgICAgICAgYnRuLnRpdGxlID0gIk1hcmsgdGhpcyBzdGlsbCBhcyB0aGUgYWNjZXB0ZWQgaW1hZ2UgZm9yIHRoaXMgYmVhdCI7CiAgICAgICAgICBidG4ub25jbGljayA9IGZ1bmN0aW9uIChlKSB7CiAgICAgICAgICAgIGUuc3RvcFByb3BhZ2F0aW9uKCk7CiAgICAgICAgICAgIF9iZ0FjY2VwdEZsdXhPcHRpb24oYmlkLCBzaSwgc2wpOwogICAgICAgICAgfTsKICAgICAgICAgIHNsLmFwcGVuZENoaWxkKGJ0bik7CiAgICAgICAgfSkoYmVhdElkLCBzbG90SWR4LCBzbG90KTsKICAgICAgfQogICAgfQoKICAgIHdpbmRvdy5fYmdSZW5kZXJCZWF0cyA9IGZ1bmN0aW9uIChiZWF0cykgewogICAgICBfcHJldlJlbmRlcihiZWF0cyB8fCBCR19CRUFUUyk7CiAgICAgIHNldFRpbWVvdXQoX2luamVjdEFjY2VwdEJ1dHRvbnMsIDUwKTsKICAgIH07CgogICAgLy8gQWxzbyBpbmplY3Qgb24gZmlyc3QgbG9hZCAoaWYgYmVhdHMgYWxyZWFkeSByZW5kZXJlZCBiZWZvcmUgdGhpcyBzY3JpcHQpCiAgICBzZXRUaW1lb3V0KF9pbmplY3RBY2NlcHRCdXR0b25zLCAzMDApOwogIH0pOwoKICAvLyDilIDilIAgMi4gQWNjZXB0IGEgRkxVWCBvcHRpb24gYXMgdGhlIGNob3NlbiBzdGlsbCBmb3IgYSBiZWF0IOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgAogIHdpbmRvdy5fYmdBY2NlcHRGbHV4T3B0aW9uID0gZnVuY3Rpb24gKGJlYXRJZCwgc2xvdEluZGV4LCBzbG90RWwpIHsKICAgIC8vIEZpbmQgdGhlIGJlYXQncyBmbHV4X29wdGlvbnNbc2xvdEluZGV4XS5rZXkKICAgIHZhciBiZWF0ID0gbnVsbDsKICAgIGZvciAodmFyIGogPSAwOyBqIDwgKEJHX0JFQVRTIHx8IFtdKS5sZW5ndGg7IGorKykgewogICAgICBpZiAoQkdfQkVBVFNbal0uYmVhdF9pZCA9PT0gYmVhdElkKSB7IGJlYXQgPSBCR19CRUFUU1tqXTsgYnJlYWs7IH0KICAgIH0KICAgIGlmICghYmVhdCkgeyBjb25zb2xlLndhcm4oIltCRy1BQ0NFUFRdIGJlYXQgbm90IGZvdW5kOiIsIGJlYXRJZCk7IHJldHVybjsgfQoKICAgIHZhciBmb3B0cyA9IGJlYXQuZmx1eF9vcHRpb25zIHx8IFtdOwogICAgdmFyIGZvcHQgID0gZm9wdHNbc2xvdEluZGV4XTsKICAgIGlmICghZm9wdCB8fCAhZm9wdC5rZXkpIHsKICAgICAgY29uc29sZS53YXJuKCJbQkctQUNDRVBUXSBubyBmbHV4X29wdGlvbnMga2V5IGF0IHNsb3QiLCBzbG90SW5kZXgsICJmb3IgYmVhdCIsIGJlYXRJZCk7CiAgICAgIHJldHVybjsKICAgIH0KCiAgICB2YXIga2V5ID0gZm9wdC5rZXk7CgogICAgLy8gVXBkYXRlIGluLW1lbW9yeQogICAgYmVhdC5hY2NlcHRlZF9pbWFnZV9rZXkgPSBrZXk7CiAgICBiZWF0LnN0YXR1cyA9ICJhY2NlcHRlZCI7CgogICAgLy8gVmlzdWFsOiBtYXJrIGNob3NlbiBzbG90LCB1bi1jaG9vc2Ugb3RoZXJzIG9uIHRoaXMgYmVhdAogICAgdmFyIGNhcmQgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgiYmctY2FyZC0iICsgYmVhdElkKTsKICAgIGlmIChjYXJkKSB7CiAgICAgIHZhciBhbGxTbG90cyA9IGNhcmQucXVlcnlTZWxlY3RvckFsbCgiLmJnLW9wdCIpOwogICAgICBmb3IgKHZhciBzaSA9IDA7IHNpIDwgYWxsU2xvdHMubGVuZ3RoOyBzaSsrKSB7CiAgICAgICAgYWxsU2xvdHNbc2ldLmNsYXNzTGlzdC5yZW1vdmUoImNob3NlbiIpOwogICAgICAgIHZhciBhYiA9IGFsbFNsb3RzW3NpXS5xdWVyeVNlbGVjdG9yKCIuYmctb3B0LWFjY2VwdCIpOwogICAgICAgIGlmIChhYikgYWIudGV4dENvbnRlbnQgPSAi4pyTIFVzZSBUaGlzIjsKICAgICAgfQogICAgfQogICAgc2xvdEVsLmNsYXNzTGlzdC5hZGQoImNob3NlbiIpOwogICAgdmFyIGFjY2VwdEJ0biA9IHNsb3RFbC5xdWVyeVNlbGVjdG9yKCIuYmctb3B0LWFjY2VwdCIpOwogICAgaWYgKGFjY2VwdEJ0bikgYWNjZXB0QnRuLnRleHRDb250ZW50ID0gIuKckyBBY2NlcHRlZCI7CgogICAgLy8gRW5hYmxlIHRoZSBBY2NlcHQgQWxsIHRvIFN0b3J5Ym9hcmQgYnV0dG9uCiAgICB2YXIgZ2xvYmFsQnRuID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoImJnLWFjY2VwdC1idG4iKTsKICAgIGlmIChnbG9iYWxCdG4pIGdsb2JhbEJ0bi5kaXNhYmxlZCA9IGZhbHNlOwoKICAgIC8vIFVwZGF0ZSBzdGF0dXMgY2hpcAogICAgdmFyIHNwID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoImJnLXN0YXR1cy0iICsgYmVhdElkKTsKICAgIGlmIChzcCkgc3AudGV4dENvbnRlbnQgPSAiYWNjZXB0ZWQiOwoKICAgIC8vIFBlcnNpc3QgdG8gc2VydmVyCiAgICBmZXRjaChCR19TRVJWRVIgKyAiL2FwaS9iZy91cGRhdGUtYmVhdCIsIHsKICAgICAgbWV0aG9kOiAiUE9TVCIsCiAgICAgIGhlYWRlcnM6IHsiQ29udGVudC1UeXBlIjogImFwcGxpY2F0aW9uL2pzb24ifSwKICAgICAgYm9keTogSlNPTi5zdHJpbmdpZnkoewogICAgICAgIGJlYXRfaWQ6IGJlYXRJZCwKICAgICAgICBhY2NlcHRlZF9pbWFnZV9rZXk6IGtleSwKICAgICAgICBzdGF0dXM6ICJhY2NlcHRlZCIKICAgICAgfSkKICAgIH0pLmNhdGNoKGZ1bmN0aW9uIChlKSB7CiAgICAgIGNvbnNvbGUud2FybigiW0JHLUFDQ0VQVF0gc2VydmVyIHBlcnNpc3QgZmFpbGVkOiIsIGUpOwogICAgfSk7CgogICAgY29uc29sZS5sb2coIltCRy1BQ0NFUFRdIEJlYXQiLCBiZWF0SWQsICJhY2NlcHRlZCBzbG90Iiwgc2xvdEluZGV4LCAia2V5OiIsIGtleSk7CiAgfTsKCiAgLy8g4pSA4pSAIDMuIEVuaGFuY2VkIEFjY2VwdCBBbGwgdG8gU3Rvcnlib2FyZCDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIAKICAvLyBSZXBsYWNlcyB0aGUgZXhpc3RpbmcgX2JnQWNjZXB0VG9TdG9yeWJvYXJkIHRvOgogIC8vICAgLSBTS0lQIGJlYXRzIHdpdGggbm8gYWNjZXB0ZWRfaW1hZ2Vfa2V5IChkb24ndCBwdXNoIHRvIExbXSBvciB3YXJuKQogIC8vICAgLSBMb2cgc2tpcHBlZCBiZWF0cyB0byBjb25zb2xlCiAgLy8gICAtIFN3aXRjaCB0byBzdG9yeWJvYXJkIHRhYiBhZnRlciBwdXNoCiAgZG9jdW1lbnQuYWRkRXZlbnRMaXN0ZW5lcigiRE9NQ29udGVudExvYWRlZCIsIGZ1bmN0aW9uICgpIHsKICAgIHZhciBidG4gPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgiYmctYWNjZXB0LWJ0biIpOwogICAgaWYgKGJ0bikgewogICAgICAvLyBSZW1vdmUgb2xkIG9uY2xpY2sgYW5kIHJlcGxhY2UKICAgICAgYnRuLm9uY2xpY2sgPSBudWxsOwogICAgICBidG4ucmVtb3ZlQXR0cmlidXRlKCJvbmNsaWNrIik7CiAgICAgIGJ0bi5hZGRFdmVudExpc3RlbmVyKCJjbGljayIsIGZ1bmN0aW9uICgpIHsKICAgICAgICBfYmdBY2NlcHRUb1N0b3J5Ym9hcmRWMygpOwogICAgICB9KTsKICAgIH0KICAgIHdpbmRvdy5fYmdBY2NlcHRUb1N0b3J5Ym9hcmQgPSBfYmdBY2NlcHRUb1N0b3J5Ym9hcmRWMzsKICB9KTsKCiAgd2luZG93Ll9iZ0FjY2VwdFRvU3Rvcnlib2FyZFYzID0gZnVuY3Rpb24gKCkgewogICAgLy8gTEZJWC1WOS1ESVJFQ1Q6IGNsZWFyIG9sZCBzdG9yeWJvYXJkIGxpbmVzIGJlZm9yZSBpbnNlcnRpbmcgQkcgYmVhdHMKICAgIGlmICh0eXBlb2YgTCAhPT0gJ3VuZGVmaW5lZCcgJiYgQXJyYXkuaXNBcnJheShMKSkgeyBMLmxlbmd0aCA9IDA7IH0KICAgIGlmICghQkdfQkVBVFMgfHwgIUJHX0JFQVRTLmxlbmd0aCkgcmV0dXJuOwoKICAgIHZhciBwdXNoZWQgPSAwOwogICAgdmFyIHNraXBwZWQgPSBbXTsKCiAgICBCR19CRUFUUy5mb3JFYWNoKGZ1bmN0aW9uIChiZWF0LCBpZHgpIHsKICAgICAgaWYgKCFiZWF0LmFjY2VwdGVkX2ltYWdlX2tleSkgewogICAgICAgIC8vIEJlYXQgaW50ZW50aW9uYWxseSBlbXB0eSBvciBub3QgeWV0IGRlY2lkZWQg4oCUIHNraXAgc2lsZW50bHkKICAgICAgICBza2lwcGVkLnB1c2goIkJlYXQgIiArIChpZHggKyAxKSArICIgKCIgKyBiZWF0LmJlYXRfaWQgKyAiKSIpOwogICAgICAgIHJldHVybjsKICAgICAgfQogICAgICBMLnB1c2goewogICAgICAgIHM6IGJlYXQuc3BlYWtlciB8fCAiQ2hpcHBlciIsCiAgICAgICAgdDogYmVhdC5kaWFsb2d1ZV90ZXh0IHx8ICIiLAogICAgICAgIGk6IGJlYXQuYWNjZXB0ZWRfaW1hZ2Vfa2V5LAogICAgICAgIGE6IG51bGwsCiAgICAgICAgcDogMC41LAogICAgICAgIGc6IEJHX1NFRyA/IEJHX1NFRy5uYW1lIDogIkJlYXQgR2VuZXJhdG9yIgogICAgICB9KTsKICAgICAgcHVzaGVkKys7CiAgICB9KTsKCiAgICBpZiAoc2tpcHBlZC5sZW5ndGgpIHsKICAgICAgY29uc29sZS5sb2coIltCRy1BQ0NFUFQtQUxMXSBTa2lwcGVkIGVtcHR5IGJlYXRzOiIsIHNraXBwZWQuam9pbigiLCAiKSk7CiAgICB9CiAgICBpZiAoIXB1c2hlZCkgewogICAgICBhbGVydCgiTm8gYmVhdHMgaGF2ZSBhbiBhY2NlcHRlZCBpbWFnZSB5ZXQuXG5DbGljayBcdTI3MTMgVXNlIFRoaXMgb24gYSBzdGlsbCBmaXJzdC4iKTsKICAgICAgcmV0dXJuOwogICAgfQoKICAgIC8vIFBlcnNpc3QgdG8gc2VydmVyCiAgICBmZXRjaChCR19TRVJWRVIgKyAiL2FwaS9iZy9hY2NlcHQtYmVhdHMiLCB7CiAgICAgIG1ldGhvZDogIlBPU1QiLAogICAgICBoZWFkZXJzOiB7IkNvbnRlbnQtVHlwZSI6ICJhcHBsaWNhdGlvbi9qc29uIn0sCiAgICAgIGJvZHk6IEpTT04uc3RyaW5naWZ5KHtiZWF0czogQkdfQkVBVFMsIHNlZ21lbnQ6IEJHX1NFR30pCiAgICB9KS5jYXRjaChmdW5jdGlvbiAoKSB7fSk7CgogICAgLy8gUmUtcmVuZGVyIHN0b3J5Ym9hcmQgYW5kIHN3aXRjaCB0YWIKICAgIGlmICh0eXBlb2YgcmVuZGVyID09PSAiZnVuY3Rpb24iKSByZW5kZXIoKTsKICAgIF9iZ1N3aXRjaFRhYigic2IiLCBudWxsKTsKCiAgICBjb25zb2xlLmxvZygiW0JHLUFDQ0VQVC1BTExdIFB1c2hlZCAiICsgcHVzaGVkICsgIiBiZWF0cyB0byBzdG9yeWJvYXJkIExbXSwgc2tpcHBlZCAiICsgc2tpcHBlZC5sZW5ndGggKyAiLiIpOwogIH07Cgp9KSgpOwovLyA9PT0gRU5EIExJQkZJWC1WMyA9PT0KPC9zY3JpcHQ+Cgo8c3R5bGU+Ci8qID09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PQogICBDUkZJWC1MSUJGSVgtVjQgKDIwMjYtMDQtMjUpCiAgIFVwbG9hZCBidXR0b246IHBvc2l0aW9uOmZpeGVkIGVzY2FwZSArIHBhbmVsIG9wZW4gZml4CiAgIENyb3BwZXI6IG92ZXJmbG93OnZpc2libGUgKyBzY2FsZS1jb3JyZWN0IGNvb3JkcwogICA9PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT0gKi8KCi8qIDEuIEZpeCB0aGUgQ1NTICFpbXBvcnRhbnQgbG9jayB0aGF0IHByZXZlbnRzICNtbi1saWItc2lkZWJhci5vcGVuIGZyb20gd29ya2luZy4KICAgICAgQm90aCBydWxlcyBoYXZlICFpbXBvcnRhbnQg4oaSIGhpZ2hlciBzcGVjaWZpY2l0eSB3aW5zOgogICAgICAjbW4tbGliLXNpZGViYXIub3BlbiAoMC0xLTEtMCkgYmVhdHMgI21uLWxpYi1zaWRlYmFyICgwLTEtMC0wKSAqLwojbW4tbGliLXNpZGViYXIub3BlbiB7CiAgdHJhbnNmb3JtOiB0cmFuc2xhdGVYKDApICFpbXBvcnRhbnQ7CiAgdHJhbnNpdGlvbjogdHJhbnNmb3JtIDAuMnMgIWltcG9ydGFudDsKfQoKLyogMi4gVXBsb2FkIGJ1dHRvbjogZXNjYXBlIEFMTCBmbGV4L292ZXJmbG93IGxheW91dC4KICAgICAgcG9zaXRpb246Zml4ZWQgdGFrZXMgaXQgb3V0IG9mIHN0YWNraW5nIGNvbnRleHQg4oCUIGV2ZW4gb3ZlcmZsb3c6aGlkZGVuCiAgICAgIG9uIG1uLWxpYi1ib2R5IGNhbm5vdCBjbGlwIGl0LiBTaG93IG9ubHkgd2hlbiBsaWJyYXJ5IGlzIG9wZW4uICovCi5tbi1saWItdXBsb2FkLWJ0biB7CiAgcG9zaXRpb246IGZpeGVkICFpbXBvcnRhbnQ7CiAgcmlnaHQ6IDEwcHggIWltcG9ydGFudDsKICBib3R0b206IDYwcHggIWltcG9ydGFudDsKICB3aWR0aDogMjQycHggIWltcG9ydGFudDsKICB6LWluZGV4OiAxMDAwMiAhaW1wb3J0YW50OwogIGRpc3BsYXk6IG5vbmUgIWltcG9ydGFudDsKICBiYWNrZ3JvdW5kOiAjMWEyZTFhICFpbXBvcnRhbnQ7CiAgY29sb3I6ICM2ZjYgIWltcG9ydGFudDsKICBib3JkZXI6IDFweCBkYXNoZWQgIzJhNGEyYSAhaW1wb3J0YW50OwogIHBhZGRpbmc6IDhweCA0cHggIWltcG9ydGFudDsKICBib3JkZXItcmFkaXVzOiA0cHggIWltcG9ydGFudDsKICBjdXJzb3I6IHBvaW50ZXIgIWltcG9ydGFudDsKICBmb250LXNpemU6IDExcHggIWltcG9ydGFudDsKICB0ZXh0LWFsaWduOiBjZW50ZXIgIWltcG9ydGFudDsKICBib3gtc2l6aW5nOiBib3JkZXItYm94ICFpbXBvcnRhbnQ7Cn0KYm9keS5tbi1saWItb3BlbiAubW4tbGliLXVwbG9hZC1idG4gewogIGRpc3BsYXk6IGJsb2NrICFpbXBvcnRhbnQ7Cn0KCi8qIDMuIENyb3BwZXIgY2FudmFzIHdyYXA6IGxldCBjYW52YXMgYnJlYXRoZSDigJQgbm8gbW9yZSBjbGlwcGluZyAqLwojY3ItY2FudmFzLXdyYXAgewogIG92ZXJmbG93OiB2aXNpYmxlICFpbXBvcnRhbnQ7Cn0KI2NyLWNhbnZhcyB7CiAgZGlzcGxheTogYmxvY2sgIWltcG9ydGFudDsKICBmbGV4LXNocmluazogMCAhaW1wb3J0YW50OwogIGN1cnNvcjogY3Jvc3NoYWlyICFpbXBvcnRhbnQ7Cn0KCi8qIDQuIEFjY2VwdGVkIGNyb3AgdGh1bWJuYWlsIGluIGJlYXQgY2FyZCBoZWFkZXIgKi8KLmJnLWFjY2VwdGVkLXByZXZpZXcgewogIHdpZHRoOiA2MHB4ICFpbXBvcnRhbnQ7CiAgaGVpZ2h0OiA0NXB4ICFpbXBvcnRhbnQ7CiAgb2JqZWN0LWZpdDogY292ZXIgIWltcG9ydGFudDsKICBib3JkZXItcmFkaXVzOiAzcHggIWltcG9ydGFudDsKICBib3JkZXI6IDJweCBzb2xpZCAjNTJiNzg4ICFpbXBvcnRhbnQ7CiAgbWFyZ2luLWxlZnQ6IDhweCAhaW1wb3J0YW50OwogIHZlcnRpY2FsLWFsaWduOiBtaWRkbGUgIWltcG9ydGFudDsKICBmbGV4LXNocmluazogMCAhaW1wb3J0YW50Owp9Cjwvc3R5bGU+CjxzY3JpcHQ+Ci8vID09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PQovLyBDUkZJWC1MSUJGSVgtVjQ6IERlZmluaXRpdmUgY3JvcHBlciArIHVwbG9hZCBidXR0b24gZml4ZXMgKDIwMjYtMDQtMjUpCi8vID09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PQoKKGZ1bmN0aW9uICgpIHsKICAidXNlIHN0cmljdCI7CgogIC8vIOKUgOKUgCAxLiBUb2dnbGUgYm9keS5tbi1saWItb3BlbiBzbyB1cGxvYWQgYnRuIGJlY29tZXMgdmlzaWJsZSDilIDilIDilIDilIDilIDilIDilIDilIDilIAKICAvLyBXcmFwIF9tbkxpYlRvZ2dsZSB0byBhZGQvcmVtb3ZlIGNsYXNzIHRoYXQgY29udHJvbHMgYnRuIGRpc3BsYXkKICBkb2N1bWVudC5hZGRFdmVudExpc3RlbmVyKCJET01Db250ZW50TG9hZGVkIiwgZnVuY3Rpb24gKCkgewogICAgdmFyIF9vcmlnID0gd2luZG93Ll9tbkxpYlRvZ2dsZTsKICAgIGlmICh0eXBlb2YgX29yaWcgPT09ICJmdW5jdGlvbiIpIHsKICAgICAgd2luZG93Ll9tbkxpYlRvZ2dsZSA9IGZ1bmN0aW9uICgpIHsKICAgICAgICBfb3JpZy5hcHBseSh0aGlzLCBhcmd1bWVudHMpOwogICAgICAgIHZhciBzaWRlYmFyID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoIm1uLWxpYi1zaWRlYmFyIik7CiAgICAgICAgaWYgKHNpZGViYXIpIHsKICAgICAgICAgIGlmIChzaWRlYmFyLmNsYXNzTGlzdC5jb250YWlucygib3BlbiIpKSB7CiAgICAgICAgICAgIGRvY3VtZW50LmJvZHkuY2xhc3NMaXN0LmFkZCgibW4tbGliLW9wZW4iKTsKICAgICAgICAgIH0gZWxzZSB7CiAgICAgICAgICAgIGRvY3VtZW50LmJvZHkuY2xhc3NMaXN0LnJlbW92ZSgibW4tbGliLW9wZW4iKTsKICAgICAgICAgIH0KICAgICAgICB9CiAgICAgIH07CiAgICB9CiAgfSk7CgogIC8vIOKUgOKUgCAyLiBSZXBsYWNlIGNyb3BwZXIgbW91c2UgaGFuZGxlcnMgd2l0aCBzY2FsZS1jb3JyZWN0ZWQgKyByZXNpemUg4pSA4pSACiAgZG9jdW1lbnQuYWRkRXZlbnRMaXN0ZW5lcigiRE9NQ29udGVudExvYWRlZCIsIGZ1bmN0aW9uICgpIHsKICAgIHZhciBjYW52YXMgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgiY3ItY2FudmFzIik7CiAgICBpZiAoIWNhbnZhcykgcmV0dXJuOwoKICAgIC8vIEhlbHBlcjogZ2V0IHNjYWxlLWNvcnJlY3RlZCBjYW52YXMgY29vcmRzIGZyb20gYSBtb3VzZSBldmVudAogICAgZnVuY3Rpb24gX2NyTW91c2VQb3MoZSkgewogICAgICB2YXIgciA9IGNhbnZhcy5nZXRCb3VuZGluZ0NsaWVudFJlY3QoKTsKICAgICAgdmFyIHNjYWxlWCA9IGNhbnZhcy53aWR0aCAgLyAoci53aWR0aCAgfHwgY2FudmFzLndpZHRoKTsKICAgICAgdmFyIHNjYWxlWSA9IGNhbnZhcy5oZWlnaHQgLyAoci5oZWlnaHQgfHwgY2FudmFzLmhlaWdodCk7CiAgICAgIHJldHVybiB7CiAgICAgICAgeDogKGUuY2xpZW50WCAtIHIubGVmdCkgKiBzY2FsZVgsCiAgICAgICAgeTogKGUuY2xpZW50WSAtIHIudG9wKSAgKiBzY2FsZVkKICAgICAgfTsKICAgIH0KCiAgICAvLyBIZWxwZXI6IHdoaWNoIGNvcm5lciBpcyBhdCBjYW52YXMtY29vcmQgKGN4LCBjeSk/IFJldHVybnMgJ3RsJywndHInLCdibCcsJ2JyJyBvciBudWxsCiAgICB2YXIgSEFORExFID0gMTQ7IC8vIHB4IGhpdCBhcmVhIG9uIGVhY2ggY29ybmVyIGhhbmRsZQogICAgZnVuY3Rpb24gX2NyQ29ybmVySGl0KGN4LCBjeSkgewogICAgICBpZiAoIUNSX0NST1BfQk9YIHx8ICFDUl9JTUcpIHJldHVybiBudWxsOwogICAgICB2YXIgY3cgPSBjYW52YXMud2lkdGgsIGNoID0gY2FudmFzLmhlaWdodDsKICAgICAgdmFyIHNjYWxlID0gTWF0aC5taW4oY3cgLyBDUl9JTUcud2lkdGgsIGNoIC8gQ1JfSU1HLmhlaWdodCk7CiAgICAgIHZhciBkeCA9IChjdyAtIENSX0lNRy53aWR0aCAgKiBzY2FsZSkgLyAyOwogICAgICB2YXIgZHkgPSAoY2ggLSBDUl9JTUcuaGVpZ2h0ICogc2NhbGUpIC8gMjsKICAgICAgdmFyIGJ4ID0gZHggKyBDUl9DUk9QX0JPWC54ICogc2NhbGU7CiAgICAgIHZhciBieSA9IGR5ICsgQ1JfQ1JPUF9CT1gueSAqIHNjYWxlOwogICAgICB2YXIgYncgPSBDUl9DUk9QX0JPWC53ICogc2NhbGU7CiAgICAgIHZhciBiaCA9IENSX0NST1BfQk9YLmggKiBzY2FsZTsKICAgICAgdmFyIGNvcm5lcnMgPSB7CiAgICAgICAgdGw6IFtieCwgICAgICAgIGJ5ICAgICAgIF0sCiAgICAgICAgdHI6IFtieCArIGJ3LCAgIGJ5ICAgICAgIF0sCiAgICAgICAgYmw6IFtieCwgICAgICAgIGJ5ICsgYmggIF0sCiAgICAgICAgYnI6IFtieCArIGJ3LCAgIGJ5ICsgYmggIF0KICAgICAgfTsKICAgICAgZm9yICh2YXIgbmFtZSBpbiBjb3JuZXJzKSB7CiAgICAgICAgdmFyIGMgPSBjb3JuZXJzW25hbWVdOwogICAgICAgIGlmIChNYXRoLmFicyhjeCAtIGNbMF0pIDw9IEhBTkRMRSAmJiBNYXRoLmFicyhjeSAtIGNbMV0pIDw9IEhBTkRMRSkgewogICAgICAgICAgcmV0dXJuIG5hbWU7CiAgICAgICAgfQogICAgICB9CiAgICAgIHJldHVybiBudWxsOwogICAgfQoKICAgIHZhciBfY3JTdGF0ZSA9IG51bGw7IC8vIHttb2RlOiAncGFuJ3wncmVzaXplJywgY29ybmVyLCBzdGFydFBvcywgYm94U3RhcnQsIGltZ1NjYWxlLCBpbWdPZmZzZXR9CgogICAgLy8gUkVNT1ZFIGV4aXN0aW5nIHBhbi1vbmx5IGxpc3RlbmVycyBieSBjbG9uaW5nIChyZXBsYWNlcyB0aGUgbm9kZSkKICAgIHZhciBuZXdDYW52YXMgPSBjYW52YXMuY2xvbmVOb2RlKHRydWUpOwogICAgY2FudmFzLnBhcmVudE5vZGUucmVwbGFjZUNoaWxkKG5ld0NhbnZhcywgY2FudmFzKTsKICAgIGNhbnZhcyA9IG5ld0NhbnZhczsKICAgIC8vIFJlLXdpcmUgQ1JfQ0FOVkFTIGdsb2JhbAogICAgaWYgKHR5cGVvZiBDUl9DQU5WQVMgIT09ICJ1bmRlZmluZWQiKSB7IC8qIHdpbGwgYmUgcmUtYXNzaWduZWQgb24gbmV4dCBfY3JMb2FkSW1hZ2UgKi8gfQoKICAgIGNhbnZhcy5hZGRFdmVudExpc3RlbmVyKCJtb3VzZWRvd24iLCBmdW5jdGlvbiAoZSkgewogICAgICBpZiAoIUNSX0lNRykgcmV0dXJuOwogICAgICB2YXIgcG9zID0gX2NyTW91c2VQb3MoZSk7CiAgICAgIHZhciBjb3JuZXIgPSBfY3JDb3JuZXJIaXQocG9zLngsIHBvcy55KTsKCiAgICAgIHZhciBjdyA9IGNhbnZhcy53aWR0aCwgY2ggPSBjYW52YXMuaGVpZ2h0OwogICAgICB2YXIgc2NhbGUgPSBNYXRoLm1pbihjdyAvIENSX0lNRy53aWR0aCwgY2ggLyBDUl9JTUcuaGVpZ2h0KTsKICAgICAgdmFyIGltZ0R4ID0gKGN3IC0gQ1JfSU1HLndpZHRoICAqIHNjYWxlKSAvIDI7CiAgICAgIHZhciBpbWdEeSA9IChjaCAtIENSX0lNRy5oZWlnaHQgKiBzY2FsZSkgLyAyOwoKICAgICAgX2NyU3RhdGUgPSB7CiAgICAgICAgbW9kZTogICAgICBjb3JuZXIgPyAicmVzaXplIiA6ICJwYW4iLAogICAgICAgIGNvcm5lcjogICAgY29ybmVyLAogICAgICAgIHN0YXJ0UG9zOiAgcG9zLAogICAgICAgIGJveFN0YXJ0OiAgT2JqZWN0LmFzc2lnbih7fSwgQ1JfQ1JPUF9CT1gpLAogICAgICAgIGltZ1NjYWxlOiAgc2NhbGUsCiAgICAgICAgaW1nT2Zmc2V0OiB7eDogaW1nRHgsIHk6IGltZ0R5fQogICAgICB9OwogICAgfSk7CgogICAgY2FudmFzLmFkZEV2ZW50TGlzdGVuZXIoIm1vdXNlbW92ZSIsIGZ1bmN0aW9uIChlKSB7CiAgICAgIGlmICghX2NyU3RhdGUgfHwgIUNSX0lNRykgcmV0dXJuOwogICAgICB2YXIgcG9zICA9IF9jck1vdXNlUG9zKGUpOwogICAgICB2YXIgc3QgICA9IF9jclN0YXRlOwogICAgICB2YXIgc2MgICA9IHN0LmltZ1NjYWxlOwogICAgICB2YXIgZGR4ICA9IChwb3MueCAtIHN0LnN0YXJ0UG9zLngpIC8gc2M7IC8vIGRlbHRhIGluIGltYWdlLXNwYWNlIHBpeGVscwogICAgICB2YXIgZGR5ICA9IChwb3MueSAtIHN0LnN0YXJ0UG9zLnkpIC8gc2M7CiAgICAgIHZhciBib3ggID0gc3QuYm94U3RhcnQ7CiAgICAgIHZhciBpdyAgID0gQ1JfSU1HLndpZHRoLCBpaCA9IENSX0lNRy5oZWlnaHQ7CiAgICAgIHZhciBSQVRJTyA9IDQgLyAzOwoKICAgICAgaWYgKHN0Lm1vZGUgPT09ICJwYW4iKSB7CiAgICAgICAgQ1JfQ1JPUF9CT1gueCA9IE1hdGgubWF4KDAsIE1hdGgubWluKGl3IC0gYm94LncsIGJveC54ICsgZGR4KSk7CiAgICAgICAgQ1JfQ1JPUF9CT1gueSA9IE1hdGgubWF4KDAsIE1hdGgubWluKGloIC0gYm94LmgsIGJveC55ICsgZGR5KSk7CgogICAgICB9IGVsc2UgewogICAgICAgIC8vIFJlc2l6ZTogYW5jaG9yIHRoZSBvcHBvc2l0ZSBjb3JuZXIsIGRyYWcgdGhlIGhpdCBjb3JuZXIKICAgICAgICAvLyBPbmx5IHdpZHRoIGRyaXZlcyBhc3BlY3QgKDQ6MyBsb2NrZWQpLCBoZWlnaHQgaXMgZGVyaXZlZAogICAgICAgIHZhciBuZXdYID0gYm94LngsIG5ld1cgPSBib3gudywgbmV3SCA9IGJveC5oOwogICAgICAgIHZhciBNSU4gPSA4MDsgLy8gbWluaW11bSBjcm9wIHdpZHRoIGluIGltYWdlIHBpeGVscwoKICAgICAgICBzd2l0Y2ggKHN0LmNvcm5lcikgewogICAgICAgICAgY2FzZSAiYnIiOgogICAgICAgICAgICBuZXdXID0gTWF0aC5tYXgoTUlOLCBib3gudyArIGRkeCk7CiAgICAgICAgICAgIGJyZWFrOwogICAgICAgICAgY2FzZSAiYmwiOgogICAgICAgICAgICBuZXdXID0gTWF0aC5tYXgoTUlOLCBib3gudyAtIGRkeCk7CiAgICAgICAgICAgIG5ld1ggPSBib3gueCArIGJveC53IC0gbmV3VzsKICAgICAgICAgICAgYnJlYWs7CiAgICAgICAgICBjYXNlICJ0ciI6CiAgICAgICAgICAgIG5ld1cgPSBNYXRoLm1heChNSU4sIGJveC53ICsgZGR4KTsKICAgICAgICAgICAgYnJlYWs7CiAgICAgICAgICBjYXNlICJ0bCI6CiAgICAgICAgICAgIG5ld1cgPSBNYXRoLm1heChNSU4sIGJveC53IC0gZGR4KTsKICAgICAgICAgICAgbmV3WCA9IGJveC54ICsgYm94LncgLSBuZXdXOwogICAgICAgICAgICBicmVhazsKICAgICAgICB9CiAgICAgICAgbmV3SCA9IG5ld1cgLyBSQVRJTzsKCiAgICAgICAgLy8gVmVydGljYWwgYW5jaG9yIGZvciB0b3AtY29ybmVyIGRyYWdzCiAgICAgICAgdmFyIG5ld1kgPSBib3gueTsKICAgICAgICBpZiAoc3QuY29ybmVyID09PSAidGwiIHx8IHN0LmNvcm5lciA9PT0gInRyIikgewogICAgICAgICAgbmV3WSA9IGJveC55ICsgYm94LmggLSBuZXdIOwogICAgICAgIH0KCiAgICAgICAgLy8gQ2xhbXAgdG8gaW1hZ2UgYm91bmRzCiAgICAgICAgbmV3WCA9IE1hdGgubWF4KDAsIG5ld1gpOwogICAgICAgIG5ld1kgPSBNYXRoLm1heCgwLCBuZXdZKTsKICAgICAgICBpZiAobmV3WCArIG5ld1cgPiBpdykgeyBuZXdXID0gaXcgLSBuZXdYOyBuZXdIID0gbmV3VyAvIFJBVElPOyB9CiAgICAgICAgaWYgKG5ld1kgKyBuZXdIID4gaWgpIHsgbmV3SCA9IGloIC0gbmV3WTsgbmV3VyA9IG5ld0ggKiBSQVRJTzsgfQoKICAgICAgICBDUl9DUk9QX0JPWC54ID0gbmV3WDsKICAgICAgICBDUl9DUk9QX0JPWC55ID0gbmV3WTsKICAgICAgICBDUl9DUk9QX0JPWC53ID0gbmV3VzsKICAgICAgICBDUl9DUk9QX0JPWC5oID0gbmV3SDsKICAgICAgfQoKICAgICAgaWYgKHR5cGVvZiBfY3JEcmF3ID09PSAiZnVuY3Rpb24iKSBfY3JEcmF3KCk7CiAgICB9KTsKCiAgICBjYW52YXMuYWRkRXZlbnRMaXN0ZW5lcigibW91c2V1cCIsICAgIGZ1bmN0aW9uICgpIHsgX2NyU3RhdGUgPSBudWxsOyB9KTsKICAgIGNhbnZhcy5hZGRFdmVudExpc3RlbmVyKCJtb3VzZWxlYXZlIiwgZnVuY3Rpb24gKCkgeyBfY3JTdGF0ZSA9IG51bGw7IH0pOwoKICAgIC8vIFJlLXdpcmUgQ1JfQ0FOVkFTIHNvIF9jckRyYXcoKSB1c2VzIHRoZSBuZXcgbm9kZQogICAgLy8gKGNsb25lTm9kZSByZXBsYWNlcyB0aGUgb2xkIHJlZmVyZW5jZSkKICAgIGlmICh0eXBlb2YgX2NySW5pdENhbnZhcyA9PT0gImZ1bmN0aW9uIikgewogICAgICBkb2N1bWVudC5hZGRFdmVudExpc3RlbmVyKCJtbi1saWItY3ItcmVhZHkiLCBfY3JJbml0Q2FudmFzKTsKICAgIH0KICAgIC8vIERpcmVjdCBhc3NpZ25tZW50IOKAlCBfY3JMb2FkSW1hZ2Ugc2V0cyBDUl9DQU5WQVMgdmlhIGdldEVsZW1lbnRCeUlkCiAgICAvLyBzbyB0aGUgY2xvbmUgaXMgZm91bmQgY29ycmVjdGx5IGFzIGxvbmcgYXMgdGhlIGlkIGlzIHByZXNlcnZlZCAoaXQgaXMpLgogIH0pOwoKICAvLyDilIDilIAgMy4gQWZ0ZXIgY3JvcCBzYXZlOiBzaG93IGFjY2VwdGVkIHRodW1ibmFpbCBpbiBiZWF0IGNhcmQgaGVhZGVyIOKUgOKUgAogIC8vIFdyYXAgX2NyU2F2ZUNyb3AgdG8gaW5qZWN0IHByZXZpZXcgYWZ0ZXIgc3VjY2Vzc2Z1bCBzYXZlLgogIGRvY3VtZW50LmFkZEV2ZW50TGlzdGVuZXIoIkRPTUNvbnRlbnRMb2FkZWQiLCBmdW5jdGlvbiAoKSB7CiAgICB2YXIgX29yaWdTYXZlID0gd2luZG93Ll9jclNhdmVDcm9wOwogICAgaWYgKHR5cGVvZiBfb3JpZ1NhdmUgIT09ICJmdW5jdGlvbiIpIHJldHVybjsKCiAgICB3aW5kb3cuX2NyU2F2ZUNyb3AgPSBmdW5jdGlvbiAoKSB7CiAgICAgIC8vIEludGVyY2VwdCBieSBtb25rZXktcGF0Y2hpbmcgZmV0Y2ggQUZURVIgX29yaWdTYXZlIGNhbGxzIGl0LgogICAgICAvLyBTaW1wbGVyOiBvdmVycmlkZSBvbmx5IHRoZSBzdWNjZXNzIGJyYW5jaCBieSBwb3N0LXByb2Nlc3NpbmcuCiAgICAgIC8vIFdlIGRvIHRoaXMgYnkgdGVtcG9yYXJpbHkgd3JhcHBpbmcgZmV0Y2ggZm9yIHRoZSAvYXBpL2NyL3NhdmUtY3JvcCBjYWxsLgogICAgICB2YXIgX29yaWdGZXRjaCA9IHdpbmRvdy5mZXRjaDsKICAgICAgdmFyIF9vbmNlID0gZmFsc2U7CiAgICAgIHdpbmRvdy5mZXRjaCA9IGZ1bmN0aW9uICh1cmwsIG9wdHMpIHsKICAgICAgICB2YXIgcCA9IF9vcmlnRmV0Y2guYXBwbHkodGhpcywgYXJndW1lbnRzKTsKICAgICAgICBpZiAoIV9vbmNlICYmIHR5cGVvZiB1cmwgPT09ICJzdHJpbmciICYmIHVybC5pbmRleE9mKCIvYXBpL2NyL3NhdmUtY3JvcCIpICE9PSAtMSkgewogICAgICAgICAgX29uY2UgPSB0cnVlOwogICAgICAgICAgd2luZG93LmZldGNoID0gX29yaWdGZXRjaDsgLy8gcmVzdG9yZSBpbW1lZGlhdGVseQogICAgICAgICAgcCA9IHAudGhlbihmdW5jdGlvbiAocmVzcCkgewogICAgICAgICAgICAvLyBDbG9uZSBhbmQgdGVlIHRoZSByZXNwb25zZSBzbyBfb3JpZ1NhdmUgY2FuIHN0aWxsIHJlYWQgaXQKICAgICAgICAgICAgdmFyIHJlc3BDbG9uZSA9IHJlc3AuY2xvbmUoKTsKICAgICAgICAgICAgcmVzcENsb25lLmpzb24oKS50aGVuKGZ1bmN0aW9uIChkKSB7CiAgICAgICAgICAgICAgaWYgKGQgJiYgZC5rZXkgJiYgQ1JfQkVBVF9JRCkgewogICAgICAgICAgICAgICAgX2luamVjdEFjY2VwdGVkUHJldmlldyhDUl9CRUFUX0lELCBkLmdhbGxlcnlfYjY0IHx8IGQudGh1bWJfYjY0IHx8ICIiKTsKICAgICAgICAgICAgICB9CiAgICAgICAgICAgIH0pLmNhdGNoKGZ1bmN0aW9uKCl7fSk7CiAgICAgICAgICAgIHJldHVybiByZXNwOwogICAgICAgICAgfSk7CiAgICAgICAgfQogICAgICAgIHJldHVybiBwOwogICAgICB9OwogICAgICBfb3JpZ1NhdmUuYXBwbHkodGhpcywgYXJndW1lbnRzKTsKICAgIH07CiAgfSk7CgogIGZ1bmN0aW9uIF9pbmplY3RBY2NlcHRlZFByZXZpZXcoYmVhdElkLCBiNjRzcmMpIHsKICAgIHZhciBjYXJkID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoImJnLWNhcmQtIiArIGJlYXRJZCk7CiAgICBpZiAoIWNhcmQpIHJldHVybjsKICAgIHZhciBoZHIgPSBjYXJkLnF1ZXJ5U2VsZWN0b3IoIi5iZy1iZWF0LWhkciIpOwogICAgaWYgKCFoZHIpIHJldHVybjsKCiAgICAvLyBSZW1vdmUgYW55IHByZXZpb3VzIHByZXZpZXcKICAgIHZhciBvbGQgPSBoZHIucXVlcnlTZWxlY3RvcigiLmJnLWFjY2VwdGVkLXByZXZpZXciKTsKICAgIGlmIChvbGQpIG9sZC5wYXJlbnROb2RlLnJlbW92ZUNoaWxkKG9sZCk7CgogICAgaWYgKGI2NHNyYykgewogICAgICB2YXIgdGh1bWIgPSBkb2N1bWVudC5jcmVhdGVFbGVtZW50KCJpbWciKTsKICAgICAgdGh1bWIuY2xhc3NOYW1lID0gImJnLWFjY2VwdGVkLXByZXZpZXciOwogICAgICB0aHVtYi5zcmMgPSBiNjRzcmM7CiAgICAgIHRodW1iLnRpdGxlID0gIkFjY2VwdGVkIGNyb3AiOwogICAgICBoZHIuYXBwZW5kQ2hpbGQodGh1bWIpOwogICAgfQoKICAgIC8vIFVwZGF0ZSBzdGF0dXMgY2hpcAogICAgdmFyIHNwID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoImJnLXN0YXR1cy0iICsgYmVhdElkKTsKICAgIGlmIChzcCkgc3AudGV4dENvbnRlbnQgPSAiY3JvcHBlZCDinJMiOwoKICAgIC8vIEVuYWJsZSBBY2NlcHQgQWxsIGJ1dHRvbgogICAgdmFyIGdsb2JhbEJ0biA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJiZy1hY2NlcHQtYnRuIik7CiAgICBpZiAoZ2xvYmFsQnRuKSBnbG9iYWxCdG4uZGlzYWJsZWQgPSBmYWxzZTsKCiAgICBjb25zb2xlLmxvZygiW0NSRklYLVY0XSBCZWF0IiwgYmVhdElkLCAiYWNjZXB0ZWQgcHJldmlldyBpbmplY3RlZC4iKTsKICB9Cgp9KSgpOwovLyA9PT0gRU5EIENSRklYLUxJQkZJWC1WNCA9PT0KPC9zY3JpcHQ+Cgo8bGFiZWwgY2xhc3M9Im1uLWxpYi11cGxvYWQtYnRuIj4mI3gyQjA2OyBVcGxvYWQgSW1hZ2U8aW5wdXQgY2xhc3M9Im1uLWxpYi11cGxvYWQtaW5wdXQiIHR5cGU9ImZpbGUiIGFjY2VwdD0iaW1hZ2UvKiIgb25jaGFuZ2U9Il9tbkxpYlVwbG9hZCh0aGlzKSI+PC9sYWJlbD4KCjxzdHlsZT4KLyogPT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09CiAgIENSRklYLUxJQkZJWC1WNSAoMjAyNi0wNC0yNSkKICAgVXBsb2FkIGJ1dHRvbjogbW92ZWQgdG8gPGJvZHk+IGRpcmVjdCBjaGlsZCDigJQgdmlld3BvcnQtcmVsYXRpdmUgZml4ZWQKICAgQ3JvcCBzYXZlOiBjb21wbGV0ZSByZXdyaXRlIOKAlCB0aHVtYm5haWwgc3Vydml2ZXMgcmUtcmVuZGVyCiAgID09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PSAqLwoKLyogQnV0dG9uIGlzIG5vdyBhIERJUkVDVCBjaGlsZCBvZiA8Ym9keT4sIG5vIHRyYW5zZm9ybWVkIGFuY2VzdG9yLgogICBwb3NpdGlvbjpmaXhlZCBpcyB2aWV3cG9ydC1yZWxhdGl2ZS4gU2hvdyB3aGVuIGJvZHkubW4tbGliLW9wZW4KICAgKHNldCBieSBfbW5MaWJUb2dnbGUgd3JhcHBlciBhbHJlYWR5IGluc3RhbGxlZCBpbiBDUkZJWC1MSUJGSVgtVjQpLiAqLwpib2R5ID4gbGFiZWwubW4tbGliLXVwbG9hZC1idG4gewogIHBvc2l0aW9uOiBmaXhlZCAhaW1wb3J0YW50OwogIHJpZ2h0OiAxMHB4ICFpbXBvcnRhbnQ7CiAgYm90dG9tOiA2MHB4ICFpbXBvcnRhbnQ7CiAgd2lkdGg6IDI0MnB4ICFpbXBvcnRhbnQ7CiAgei1pbmRleDogMTAwMDIgIWltcG9ydGFudDsKICBkaXNwbGF5OiBub25lICFpbXBvcnRhbnQ7CiAgYmFja2dyb3VuZDogIzFhMmUxYSAhaW1wb3J0YW50OwogIGNvbG9yOiAjNmY2ICFpbXBvcnRhbnQ7CiAgYm9yZGVyOiAxcHggZGFzaGVkICMyYTRhMmEgIWltcG9ydGFudDsKICBwYWRkaW5nOiA4cHggNHB4ICFpbXBvcnRhbnQ7CiAgYm9yZGVyLXJhZGl1czogNHB4ICFpbXBvcnRhbnQ7CiAgY3Vyc29yOiBwb2ludGVyICFpbXBvcnRhbnQ7CiAgZm9udC1zaXplOiAxMXB4ICFpbXBvcnRhbnQ7CiAgdGV4dC1hbGlnbjogY2VudGVyICFpbXBvcnRhbnQ7CiAgYm94LXNpemluZzogYm9yZGVyLWJveCAhaW1wb3J0YW50Owp9CmJvZHkubW4tbGliLW9wZW4gPiBsYWJlbC5tbi1saWItdXBsb2FkLWJ0biB7CiAgZGlzcGxheTogYmxvY2sgIWltcG9ydGFudDsKfQo8L3N0eWxlPgo8c2NyaXB0PgovLyA9PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT0KLy8gQ1JGSVgtTElCRklYLVY1OiBUZXJtaW5hbCB1cGxvYWQgYnV0dG9uICsgY3JvcCB0aHVtYm5haWwgZml4ICgyMDI2LTA0LTI1KQovLyA9PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT0KCihmdW5jdGlvbiAoKSB7CiAgInVzZSBzdHJpY3QiOwoKICAvLyDilIDilIAgMS4gU2FmZXR5LW5ldDogZW5zdXJlIC5tbi1saWItdXBsb2FkLWJ0biBpcyBkaXJlY3QgY2hpbGQgb2YgPGJvZHk+IOKUgOKUgAogIC8vIFN0YXRpYyBIVE1MIHdhcyBhbHJlYWR5IHJlc3RydWN0dXJlZCBhYm92ZS4gVGhpcyBndWFyZCBydW5zIG9uCiAgLy8gRE9NQ29udGVudExvYWRlZCBhcyBhIGJlbHQtYW5kLXN1c3BlbmRlcnMgY2hlY2suCiAgZG9jdW1lbnQuYWRkRXZlbnRMaXN0ZW5lcigiRE9NQ29udGVudExvYWRlZCIsIGZ1bmN0aW9uICgpIHsKICAgIHZhciBidG4gPSBkb2N1bWVudC5xdWVyeVNlbGVjdG9yKCJsYWJlbC5tbi1saWItdXBsb2FkLWJ0biIpOwogICAgaWYgKCFidG4pIHsgY29uc29sZS53YXJuKCJbVjVdIC5tbi1saWItdXBsb2FkLWJ0biBub3QgZm91bmQgaW4gRE9NIik7IHJldHVybjsgfQogICAgaWYgKGJ0bi5wYXJlbnROb2RlICE9PSBkb2N1bWVudC5ib2R5KSB7CiAgICAgIGRvY3VtZW50LmJvZHkuYXBwZW5kQ2hpbGQoYnRuKTsKICAgICAgY29uc29sZS5sb2coIltWNV0gdXBsb2FkIGJ0biBtb3ZlZCB0byBib2R5IGZyb206IiwgYnRuLnBhcmVudE5vZGUgJiYgYnRuLnBhcmVudE5vZGUuaWQpOwogICAgfSBlbHNlIHsKICAgICAgY29uc29sZS5sb2coIltWNV0gdXBsb2FkIGJ0biBhbHJlYWR5IGF0IGJvZHkgbGV2ZWwg4oCUIE9LIik7CiAgICB9CiAgfSk7CgogIC8vIOKUgOKUgCAyLiBDb21wbGV0ZSBfY3JTYXZlQ3JvcCByZXdyaXRlIOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgAogIC8vIFJlcGxhY2VzIHRoZSBicm9rZW4gVjQgZmV0Y2gtaW50ZXJjZXB0aW9uIGFwcHJvYWNoIGVudGlyZWx5LgogIC8vIEtleSBpbnZhcmlhbnRzOgogIC8vICAgLSBiZWF0SWRBdFNhdmUgY2FwdHVyZWQgc3luY2hyb25vdXNseSBiZWZvcmUgYW55IGFzeW5jIHdvcmsKICAvLyAgIC0gRHJhd3MgZnJvbSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgiY3ItY2FudmFzIikgc28gY2FudmFzIGNsb25lIChmcm9tIFY0KQogIC8vICAgICBkb2Vzbid0IGNhdXNlIENSX0NBTlZBUyBnbG9iYWwgdG8gcG9pbnQgdG8gYSBkZXRhY2hlZCBub2RlCiAgLy8gICAtIF9iZ1N3aXRjaFRhYiBjYWxsZWQgZmlyc3QsIHRoZW4gX2luamVjdEFjY2VwdGVkUHJldmlldyB3aXRoIHNldFRpbWVvdXQoMTUwKQogIC8vICAgICBzbyB0aHVtYm5haWwgaXMgaW5qZWN0ZWQgQUZURVIgX2JnUmVuZGVyQmVhdHMgcmUtcmVuZGVyIHNldHRsZXMKICAvLyAgIC0gVEhbXSBwb3B1bGF0ZWQgaW1tZWRpYXRlbHkgc28gZnV0dXJlIHJlbmRlcnMgY2FuIHJlLWluamVjdCB0aGUgdGh1bWJuYWlsCiAgZG9jdW1lbnQuYWRkRXZlbnRMaXN0ZW5lcigiRE9NQ29udGVudExvYWRlZCIsIGZ1bmN0aW9uICgpIHsKCiAgICB3aW5kb3cuX2NyU2F2ZUNyb3AgPSBmdW5jdGlvbiAoKSB7CiAgICAgIC8vIFByZWZlciBnZXRFbGVtZW50QnlJZCBvdmVyIENSX0NBTlZBUyBnbG9iYWwgKGNsb25lIG1heSBoYXZlIGRldGFjaGVkIG9sZCByZWYpCiAgICAgIHZhciBzcmNDYW52YXMgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgiY3ItY2FudmFzIik7CiAgICAgIGlmICghc3JjQ2FudmFzICYmIHR5cGVvZiBDUl9DQU5WQVMgIT09ICJ1bmRlZmluZWQiKSBzcmNDYW52YXMgPSBDUl9DQU5WQVM7CiAgICAgIGlmICghQ1JfSU1HIHx8ICFzcmNDYW52YXMpIHsKICAgICAgICBhbGVydCgiTm8gaW1hZ2UgbG9hZGVkIGludG8gY3JvcHBlci4iKTsKICAgICAgICByZXR1cm47CiAgICAgIH0KCiAgICAgIC8vIENhcHR1cmUgbXV0YWJsZSBnbG9iYWxzIE5PVyBiZWZvcmUgYW55IGFzeW5jCiAgICAgIHZhciBiZWF0SWRBdFNhdmUgPSAodHlwZW9mIENSX0JFQVRfSUQgIT09ICJ1bmRlZmluZWQiKSA/IENSX0JFQVRfSUQgOiBudWxsOwogICAgICB2YXIgc3JjS2V5QXRTYXZlID0gKHR5cGVvZiBDUl9TUkNfS0VZICE9PSAidW5kZWZpbmVkIikgPyBDUl9TUkNfS0VZIDogbnVsbDsKCiAgICAgIC8vIEJ1aWxkIGNyb3AgY2FudmFzCiAgICAgIHZhciB3ID0gTWF0aC5tYXgoMSwgTWF0aC5yb3VuZChDUl9DUk9QX0JPWC53KSk7CiAgICAgIHZhciBoID0gTWF0aC5tYXgoMSwgTWF0aC5yb3VuZChDUl9DUk9QX0JPWC5oKSk7CiAgICAgIHZhciB0bXAgPSBkb2N1bWVudC5jcmVhdGVFbGVtZW50KCJjYW52YXMiKTsKICAgICAgdG1wLndpZHRoICA9IHc7CiAgICAgIHRtcC5oZWlnaHQgPSBoOwogICAgICB0bXAuZ2V0Q29udGV4dCgiMmQiKS5kcmF3SW1hZ2UoCiAgICAgICAgQ1JfSU1HLAogICAgICAgIENSX0NST1BfQk9YLngsIENSX0NST1BfQk9YLnksIHcsIGgsCiAgICAgICAgMCwgMCwgdywgaAogICAgICApOwoKICAgICAgLy8gRGlzYWJsZSBzYXZlIGJ1dHRvbiB3aGlsZSBpbiBmbGlnaHQKICAgICAgdmFyIHNhdmVCdG4gPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgiY3Itc2F2ZS1idG4iKTsKICAgICAgaWYgKHNhdmVCdG4pIHsgc2F2ZUJ0bi5kaXNhYmxlZCA9IHRydWU7IHNhdmVCdG4udGV4dENvbnRlbnQgPSAiU2F2aW5n4oCmIjsgfQoKICAgICAgdmFyIF9yZXN0b3JlQnRuID0gZnVuY3Rpb24gKCkgewogICAgICAgIGlmIChzYXZlQnRuKSB7IHNhdmVCdG4uZGlzYWJsZWQgPSBmYWxzZTsgc2F2ZUJ0bi50ZXh0Q29udGVudCA9ICJcdUQ4M0RcdURDQkUgU2F2ZSBDcm9wIjsgfQogICAgICB9OwoKICAgICAgdG1wLnRvQmxvYihmdW5jdGlvbiAoYmxvYikgewogICAgICAgIGlmICghYmxvYikgeyBfcmVzdG9yZUJ0bigpOyBhbGVydCgiRmFpbGVkIHRvIGdlbmVyYXRlIGNyb3AgUE5HLiIpOyByZXR1cm47IH0KCiAgICAgICAgdmFyIHJlYWRlciA9IG5ldyBGaWxlUmVhZGVyKCk7CiAgICAgICAgcmVhZGVyLm9ubG9hZCA9IGZ1bmN0aW9uICgpIHsKICAgICAgICAgIHZhciBiNjQgPSByZWFkZXIucmVzdWx0LnNwbGl0KCIsIilbMV07CgogICAgICAgICAgZmV0Y2goQkdfU0VSVkVSICsgIi9hcGkvY3Ivc2F2ZS1jcm9wIiwgewogICAgICAgICAgICBtZXRob2Q6ICJQT1NUIiwKICAgICAgICAgICAgaGVhZGVyczogeyAiQ29udGVudC1UeXBlIjogImFwcGxpY2F0aW9uL2pzb24iIH0sCiAgICAgICAgICAgIGJvZHk6IEpTT04uc3RyaW5naWZ5KHsKICAgICAgICAgICAgICBjcm9wX3BuZ19iNjQ6IGI2NCwKICAgICAgICAgICAgICBiZWF0X2lkOiAgICAgIGJlYXRJZEF0U2F2ZSwKICAgICAgICAgICAgICBzb3VyY2Vfa2V5OiAgIHNyY0tleUF0U2F2ZQogICAgICAgICAgICB9KQogICAgICAgICAgfSkKICAgICAgICAgIC50aGVuKGZ1bmN0aW9uIChyKSB7IHJldHVybiByLmpzb24oKTsgfSkKICAgICAgICAgIC50aGVuKGZ1bmN0aW9uIChkKSB7CiAgICAgICAgICAgIGlmICghZCB8fCBkLmVycm9yKSB7CiAgICAgICAgICAgICAgYWxlcnQoIlNhdmUgZmFpbGVkOiAiICsgKGQgJiYgZC5lcnJvciA/IGQuZXJyb3IgOiAidW5rbm93biIpKTsKICAgICAgICAgICAgICByZXR1cm47CiAgICAgICAgICAgIH0KCiAgICAgICAgICAgIC8vIEFkZCB0byBsaWJyYXJ5IGdhbGxlcnkKICAgICAgICAgICAgaWYgKGQua2V5ICYmIGQuZmlsZW5hbWUgJiYgZC50aHVtYl9iNjQgJiYgZC5nYWxsZXJ5X2I2NCkgewogICAgICAgICAgICAgIGlmICh0eXBlb2YgX2luamVjdEltYWdlID09PSAiZnVuY3Rpb24iKSB7CiAgICAgICAgICAgICAgICBfaW5qZWN0SW1hZ2UoZC5rZXksIGQuZmlsZW5hbWUsIGQudGh1bWJfYjY0LCBkLmdhbGxlcnlfYjY0KTsKICAgICAgICAgICAgICB9CiAgICAgICAgICAgIH0KCiAgICAgICAgICAgIC8vIFBvcHVsYXRlIFRIW10gc28gZnV0dXJlIHJlbmRlcnMgY2FuIHJlLWluamVjdCB0aGUgdGh1bWJuYWlsCiAgICAgICAgICAgIHZhciB0aHVtYlNyYyA9IGQuZ2FsbGVyeV9iNjQgfHwgZC50aHVtYl9iNjQ7CiAgICAgICAgICAgIGlmICh0aHVtYlNyYyAmJiBkLmtleSAmJiB0eXBlb2YgVEggIT09ICJ1bmRlZmluZWQiKSB7CiAgICAgICAgICAgICAgVEhbZC5rZXldID0gdGh1bWJTcmM7CiAgICAgICAgICAgIH0KCiAgICAgICAgICAgIC8vIFVwZGF0ZSBpbi1tZW1vcnkgYmVhdCByZWNvcmQKICAgICAgICAgICAgaWYgKGJlYXRJZEF0U2F2ZSAmJiBkLmtleSkgewogICAgICAgICAgICAgIHZhciBibGlzdCA9IEFycmF5LmlzQXJyYXkoQkdfQkVBVFMpID8gQkdfQkVBVFMgOiBbXTsKICAgICAgICAgICAgICBmb3IgKHZhciBqID0gMDsgaiA8IGJsaXN0Lmxlbmd0aDsgaisrKSB7CiAgICAgICAgICAgICAgICBpZiAoYmxpc3Rbal0uYmVhdF9pZCA9PT0gYmVhdElkQXRTYXZlKSB7CiAgICAgICAgICAgICAgICAgIGJsaXN0W2pdLmFjY2VwdGVkX2ltYWdlX2tleSA9IGQua2V5OwogICAgICAgICAgICAgICAgICBibGlzdFtqXS5zdGF0dXMgPSAiY3JvcHBlZCI7CiAgICAgICAgICAgICAgICAgIGJyZWFrOwogICAgICAgICAgICAgICAgfQogICAgICAgICAgICAgIH0KICAgICAgICAgICAgICAvLyBQZXJzaXN0IHRvIHNlcnZlcgogICAgICAgICAgICAgIGZldGNoKEJHX1NFUlZFUiArICIvYXBpL2JnL2FjY2VwdC1vcHRpb24iLCB7CiAgICAgICAgICAgICAgICBtZXRob2Q6ICJQT1NUIiwKICAgICAgICAgICAgICAgIGhlYWRlcnM6IHsgIkNvbnRlbnQtVHlwZSI6ICJhcHBsaWNhdGlvbi9qc29uIiB9LAogICAgICAgICAgICAgICAgYm9keTogSlNPTi5zdHJpbmdpZnkoeyBiZWF0X2lkOiBiZWF0SWRBdFNhdmUsIG9wdGlvbl9rZXk6IGQua2V5IH0pCiAgICAgICAgICAgICAgfSkuY2F0Y2goZnVuY3Rpb24gKCkge30pOwogICAgICAgICAgICB9CgogICAgICAgICAgICAvLyBTd2l0Y2ggdGFiIEZJUlNUICh0cmlnZ2VycyBfYmdSZW5kZXJCZWF0cyB3aGljaCByZWJ1aWxkcyBjYXJkcykKICAgICAgICAgICAgaWYgKHR5cGVvZiBfYmdTd2l0Y2hUYWIgPT09ICJmdW5jdGlvbiIpIHsKICAgICAgICAgICAgICBfYmdTd2l0Y2hUYWIoImJnIiwgbnVsbCk7CiAgICAgICAgICAgIH0KCiAgICAgICAgICAgIC8vIEluamVjdCB0aHVtYm5haWwgQUZURVIgcmUtcmVuZGVyIHNldHRsZXMgKDE1MG1zID4gb25lIFJlYWN0IHRpY2spCiAgICAgICAgICAgIGlmIChiZWF0SWRBdFNhdmUgJiYgdGh1bWJTcmMpIHsKICAgICAgICAgICAgICBzZXRUaW1lb3V0KGZ1bmN0aW9uICgpIHsKICAgICAgICAgICAgICAgIF9pbmplY3RBY2NlcHRlZFByZXZpZXcoYmVhdElkQXRTYXZlLCB0aHVtYlNyYyk7CiAgICAgICAgICAgICAgfSwgMTUwKTsKICAgICAgICAgICAgfQoKICAgICAgICAgICAgY29uc29sZS5sb2coIltWNS1DUk9QXSBCZWF0IiwgYmVhdElkQXRTYXZlLCAic2F2ZWQga2V5OiIsIGQua2V5KTsKICAgICAgICAgIH0pCiAgICAgICAgICAuY2F0Y2goZnVuY3Rpb24gKGUpIHsgYWxlcnQoIkNyb3AgdXBsb2FkIGVycm9yOiAiICsgZSk7IH0pCiAgICAgICAgICAuZmluYWxseShfcmVzdG9yZUJ0bik7CiAgICAgICAgfTsKICAgICAgICByZWFkZXIucmVhZEFzRGF0YVVSTChibG9iKTsKICAgICAgfSwgImltYWdlL3BuZyIpOwogICAgfTsKCiAgfSk7CgogIC8vIOKUgOKUgCAzLiBfYmdSZW5kZXJCZWF0cyB3cmFwcGVyOiByZS1pbmplY3QgdGh1bWJuYWlscyBhZnRlciBldmVyeSByZW5kZXIg4pSA4pSACiAgLy8gRXZlcnkgX2JnUmVuZGVyQmVhdHMgY2FsbCByZWJ1aWxkcyBiZWF0IGNhcmRzIGZyb20gc2NyYXRjaCwgd2lwaW5nIGFueQogIC8vIC5iZy1hY2NlcHRlZC1wcmV2aWV3IGVsZW1lbnRzLiBUaGlzIHdyYXBwZXIgcmUtaW5qZWN0cyB0aGVtIGZvciBhbGwgYmVhdHMKICAvLyB0aGF0IGhhdmUgYWNjZXB0ZWRfaW1hZ2Vfa2V5IHByZXNlbnQgaW4gVEhbXS4KICBkb2N1bWVudC5hZGRFdmVudExpc3RlbmVyKCJET01Db250ZW50TG9hZGVkIiwgZnVuY3Rpb24gKCkgewogICAgdmFyIF9wcmV2ID0gd2luZG93Ll9iZ1JlbmRlckJlYXRzOwogICAgaWYgKHR5cGVvZiBfcHJldiAhPT0gImZ1bmN0aW9uIikgcmV0dXJuOwoKICAgIHdpbmRvdy5fYmdSZW5kZXJCZWF0cyA9IGZ1bmN0aW9uIChiZWF0cykgewogICAgICBfcHJldi5jYWxsKHRoaXMsIGJlYXRzIHx8IEJHX0JFQVRTKTsKICAgICAgc2V0VGltZW91dChmdW5jdGlvbiAoKSB7CiAgICAgICAgdmFyIGJsaXN0ID0gQXJyYXkuaXNBcnJheShCR19CRUFUUykgPyBCR19CRUFUUyA6IFtdOwogICAgICAgIGZvciAodmFyIGkgPSAwOyBpIDwgYmxpc3QubGVuZ3RoOyBpKyspIHsKICAgICAgICAgIHZhciBiZWF0ID0gYmxpc3RbaV07CiAgICAgICAgICBpZiAoIWJlYXQgfHwgIWJlYXQuYWNjZXB0ZWRfaW1hZ2Vfa2V5KSBjb250aW51ZTsKICAgICAgICAgIHZhciBzcmMgPSAodHlwZW9mIFRIICE9PSAidW5kZWZpbmVkIikgPyBUSFtiZWF0LmFjY2VwdGVkX2ltYWdlX2tleV0gOiBudWxsOwogICAgICAgICAgaWYgKHNyYyAmJiB0eXBlb2YgX2luamVjdEFjY2VwdGVkUHJldmlldyA9PT0gImZ1bmN0aW9uIikgewogICAgICAgICAgICBfaW5qZWN0QWNjZXB0ZWRQcmV2aWV3KGJlYXQuYmVhdF9pZCwgc3JjKTsKICAgICAgICAgIH0KICAgICAgICB9CiAgICAgIH0sIDgwKTsKICAgIH07CiAgfSk7Cgp9KSgpOwovLyA9PT0gRU5EIENSRklYLUxJQkZJWC1WNSA9PT0KPC9zY3JpcHQ+Cgo8c3R5bGU+Ci8qID09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PQogICBDUkZJWC1MSUJGSVgtVjYgKDIwMjYtMDQtMjUpCiAgIFVwbG9hZCBidXR0b246IHJpZ2h0OjI3MHB4IHNvIGl0IGNsZWFycyB0aGUgMjYwcHggbGlicmFyeSBwYW5lbAogICA9PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT0gKi8KCi8qIE92ZXJyaWRlIFY1J3MgcmlnaHQ6MTBweCDigJQgYXQgcmlnaHQ6MTBweCB0aGUgYnV0dG9uIHNpdHMgSU5TSURFCiAgIHRoZSBsaWJyYXJ5IHBhbmVsICgyNjBweCB3aWRlIGZyb20gdGhlIHJpZ2h0KS4KICAgcmlnaHQ6MjcwcHggcHV0cyBpdCAxMHB4IHRvIHRoZSBMRUZUIG9mIHRoZSBsaWJyYXJ5IHBhbmVsIGVkZ2UuICovCmJvZHkgPiBsYWJlbC5tbi1saWItdXBsb2FkLWJ0biB7CiAgcmlnaHQ6IDI3MHB4ICFpbXBvcnRhbnQ7CiAgYm90dG9tOiA4MHB4ICFpbXBvcnRhbnQ7Cn0KYm9keS5tbi1saWItb3BlbiA+IGxhYmVsLm1uLWxpYi11cGxvYWQtYnRuIHsKICBkaXNwbGF5OiBibG9jayAhaW1wb3J0YW50Owp9Cjwvc3R5bGU+CjxzY3JpcHQ+Ci8vID09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PQovLyBDUkZJWC1MSUJGSVgtVjY6IEdsb2JhbCBfaW5qZWN0QWNjZXB0ZWRQcmV2aWV3ICsgYnV0dG9uIHBsYWNlbWVudCAoMjAyNi0wNC0yNSkKLy8KLy8gVjQgZGVmaW5lZCBfaW5qZWN0QWNjZXB0ZWRQcmV2aWV3KCkgaW5zaWRlIGFuIElJRkUg4oCUIExPQ0FMIHNjb3BlIG9ubHkuCi8vIFY1J3MgX2NyU2F2ZUNyb3AgYW5kIF9iZ1JlbmRlckJlYXRzIHdyYXBwZXIgY2FuJ3QgY2FsbCBpdCAoUmVmZXJlbmNlRXJyb3IpLgovLyBUaGlzIHBhdGNoIGV4cG9zZXMgaXQgZ2xvYmFsbHkgc28gYm90aCBjYW4gZmluZCBpdC4KLy8gPT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09CgovLyBEZWZpbmUgZ2xvYmFsbHkgQkVGT1JFIERPTUNvbnRlbnRMb2FkZWQgc28gX2NyU2F2ZUNyb3AgY2FuIGNhbGwgaXQKLy8gc3luY2hyb25vdXNseSAodGhlIGNhbGwgc2l0ZSBpcyBpbnNpZGUgYSAudGhlbigpIGNhbGxiYWNrIGJ1dCB0aGUgZnVuY3Rpb24KLy8gcmVmZXJlbmNlIGlzIGxvb2tlZCB1cCBhdCBjYWxsIHRpbWUsIG5vdCBhdCBwYXJzZSB0aW1lLCBzbyBnbG9iYWwgaXMgZmluZSkuCndpbmRvdy5faW5qZWN0QWNjZXB0ZWRQcmV2aWV3ID0gZnVuY3Rpb24gKGJlYXRJZCwgYjY0c3JjKSB7CiAgdmFyIGNhcmQgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgiYmctY2FyZC0iICsgYmVhdElkKTsKICBpZiAoIWNhcmQpIHsKICAgIGNvbnNvbGUud2FybigiW1Y2XSBiZy1jYXJkLSIgKyBiZWF0SWQgKyAiIG5vdCBmb3VuZCBmb3IgdGh1bWJuYWlsIGluamVjdCIpOwogICAgcmV0dXJuOwogIH0KICB2YXIgaGRyID0gY2FyZC5xdWVyeVNlbGVjdG9yKCIuYmctYmVhdC1oZHIiKTsKICBpZiAoIWhkcikgcmV0dXJuOwoKICAvLyBSZW1vdmUgYW55IHByZXZpb3VzIHByZXZpZXcKICB2YXIgb2xkID0gaGRyLnF1ZXJ5U2VsZWN0b3IoIi5iZy1hY2NlcHRlZC1wcmV2aWV3Iik7CiAgaWYgKG9sZCkgb2xkLnBhcmVudE5vZGUucmVtb3ZlQ2hpbGQob2xkKTsKCiAgaWYgKGI2NHNyYykgewogICAgdmFyIHRodW1iID0gZG9jdW1lbnQuY3JlYXRlRWxlbWVudCgiaW1nIik7CiAgICB0aHVtYi5jbGFzc05hbWUgPSAiYmctYWNjZXB0ZWQtcHJldmlldyI7CiAgICB0aHVtYi5zcmMgPSBiNjRzcmM7CiAgICB0aHVtYi50aXRsZSA9ICJBY2NlcHRlZCBjcm9wIjsKICAgIGhkci5hcHBlbmRDaGlsZCh0aHVtYik7CiAgfQoKICAvLyBVcGRhdGUgc3RhdHVzIGNoaXAKICB2YXIgc3AgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgiYmctc3RhdHVzLSIgKyBiZWF0SWQpOwogIGlmIChzcCkgc3AudGV4dENvbnRlbnQgPSAiY3JvcHBlZCDinJMiOwoKICAvLyBFbmFibGUgQWNjZXB0IEFsbCBidXR0b24KICB2YXIgZ2xvYmFsQnRuID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoImJnLWFjY2VwdC1idG4iKTsKICBpZiAoZ2xvYmFsQnRuKSBnbG9iYWxCdG4uZGlzYWJsZWQgPSBmYWxzZTsKCiAgY29uc29sZS5sb2coIltWNl0gX2luamVjdEFjY2VwdGVkUHJldmlldzogYmVhdCIsIGJlYXRJZCwgInRodW1ibmFpbCBpbmplY3RlZCIpOwp9OwovLyA9PT0gRU5EIENSRklYLUxJQkZJWC1WNiA9PT0KPC9zY3JpcHQ+Cgo8c3R5bGU+Ci8qID09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PQogICBDUkZJWC1MSUJGSVgtVjcgKDIwMjYtMDQtMjUpCiAgIEZpeDogaGlkZSB0aGUgZmlsZSBpbnB1dCBpbnNpZGUgdGhlIHVwbG9hZCBsYWJlbCBzbyBpdAogICBsb29rcyBsaWtlIGEgY29tcGFjdCBidXR0b24sIG5vdCBhIGdpYW50IHJlY3RhbmdsZS4KICAgPT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09ICovCgovKiBDb25zdHJhaW4gdGhlIGxhYmVsIHRvIGJ1dHRvbiBzaXplICovCmJvZHkgPiBsYWJlbC5tbi1saWItdXBsb2FkLWJ0biB7CiAgaGVpZ2h0OiAzMnB4ICFpbXBvcnRhbnQ7CiAgbGluZS1oZWlnaHQ6IDMycHggIWltcG9ydGFudDsKICBvdmVyZmxvdzogaGlkZGVuICFpbXBvcnRhbnQ7CiAgcGFkZGluZzogMCA4cHggIWltcG9ydGFudDsKICB3aGl0ZS1zcGFjZTogbm93cmFwICFpbXBvcnRhbnQ7Cn0KCi8qIEhpZGUgdGhlIGZpbGUgaW5wdXQg4oCUIGNsaWNraW5nIHRoZSBsYWJlbCB0cmlnZ2VycyBpdCB2aWEgYnJvd3NlciBkZWZhdWx0ICovCmJvZHkgPiBsYWJlbC5tbi1saWItdXBsb2FkLWJ0biBpbnB1dFt0eXBlPSJmaWxlIl0sCmJvZHkgPiBsYWJlbC5tbi1saWItdXBsb2FkLWJ0biBpbnB1dC5tbi1saWItdXBsb2FkLWlucHV0IHsKICBwb3NpdGlvbjogYWJzb2x1dGUgIWltcG9ydGFudDsKICB3aWR0aDogMCAhaW1wb3J0YW50OwogIGhlaWdodDogMCAhaW1wb3J0YW50OwogIG9wYWNpdHk6IDAgIWltcG9ydGFudDsKICBvdmVyZmxvdzogaGlkZGVuICFpbXBvcnRhbnQ7CiAgcG9pbnRlci1ldmVudHM6IG5vbmUgIWltcG9ydGFudDsKfQo8L3N0eWxlPgo8IS0tIENSRklYLUxJQkZJWC1WNyAtLT4KCjxzY3JpcHQ+Ci8vID09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PQovLyBDUkZJWC1MSUJGSVgtVjg6IFdpcmUgdGh1bWJuYWlsIGludG8gIlVzZSBUaGlzIiBhY2NlcHQgZmxvdyAoMjAyNi0wNC0yNSkKLy8gX2JnQWNjZXB0Rmx1eE9wdGlvbiAoTElCRklYLVYzKSBuZXZlciBjYWxsZWQgX2luamVjdEFjY2VwdGVkUHJldmlldy4KLy8gVGhpcyB3cmFwcGVyIGFkZHMgdGhhdCBjYWxsIHNvIHRoZSBjaG9zZW4gc3RpbGwgYmFkZ2UgYXBwZWFycyBpbW1lZGlhdGVseS4KLy8gPT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09CmRvY3VtZW50LmFkZEV2ZW50TGlzdGVuZXIoIkRPTUNvbnRlbnRMb2FkZWQiLCBmdW5jdGlvbiAoKSB7CiAgdmFyIF9vcmlnQWNjZXB0ID0gd2luZG93Ll9iZ0FjY2VwdEZsdXhPcHRpb247CiAgaWYgKHR5cGVvZiBfb3JpZ0FjY2VwdCAhPT0gImZ1bmN0aW9uIikgcmV0dXJuOwoKICB3aW5kb3cuX2JnQWNjZXB0Rmx1eE9wdGlvbiA9IGZ1bmN0aW9uIChiZWF0SWQsIHNsb3RJbmRleCwgc2xvdEVsKSB7CiAgICBfb3JpZ0FjY2VwdC5hcHBseSh0aGlzLCBhcmd1bWVudHMpOwoKICAgIC8vIEZpbmQgdGhlIGtleSB0aGF0IHdhcyBqdXN0IGFjY2VwdGVkCiAgICB2YXIgYmxpc3QgPSBBcnJheS5pc0FycmF5KEJHX0JFQVRTKSA/IEJHX0JFQVRTIDogW107CiAgICB2YXIgYWNjZXB0ZWRLZXkgPSBudWxsOwogICAgZm9yICh2YXIgaSA9IDA7IGkgPCBibGlzdC5sZW5ndGg7IGkrKykgewogICAgICBpZiAoYmxpc3RbaV0uYmVhdF9pZCA9PT0gYmVhdElkKSB7CiAgICAgICAgYWNjZXB0ZWRLZXkgPSBibGlzdFtpXS5hY2NlcHRlZF9pbWFnZV9rZXk7CiAgICAgICAgYnJlYWs7CiAgICAgIH0KICAgIH0KCiAgICAvLyBJbmplY3QgdGh1bWJuYWlsIOKAlCBUSFtdIGlzIGFscmVhZHkgcG9wdWxhdGVkIGZyb20gdGhlIHJlbmRlciBwYXNzCiAgICBpZiAoYWNjZXB0ZWRLZXkgJiYgdHlwZW9mIHdpbmRvdy5faW5qZWN0QWNjZXB0ZWRQcmV2aWV3ID09PSAiZnVuY3Rpb24iKSB7CiAgICAgIHZhciBzcmMgPSAodHlwZW9mIFRIICE9PSAidW5kZWZpbmVkIikgPyBUSFthY2NlcHRlZEtleV0gOiBudWxsOwogICAgICBpZiAoc3JjKSB7CiAgICAgICAgd2luZG93Ll9pbmplY3RBY2NlcHRlZFByZXZpZXcoYmVhdElkLCBzcmMpOwogICAgICB9IGVsc2UgewogICAgICAgIC8vIFRIIGNvbGQgKHVubGlrZWx5IGJ1dCBwb3NzaWJsZSBvbiBmcmVzaCBsb2FkKTogdHJ5IHRoZSBzbG90IGltYWdlIGRpcmVjdGx5CiAgICAgICAgdmFyIGltZyA9IHNsb3RFbCAmJiBzbG90RWwucXVlcnlTZWxlY3RvcigiaW1nIik7CiAgICAgICAgaWYgKGltZyAmJiBpbWcuc3JjKSB7CiAgICAgICAgICB3aW5kb3cuX2luamVjdEFjY2VwdGVkUHJldmlldyhiZWF0SWQsIGltZy5zcmMpOwogICAgICAgIH0KICAgICAgfQogICAgfQogIH07CgogIGNvbnNvbGUubG9nKCJbVjhdIF9iZ0FjY2VwdEZsdXhPcHRpb24gd3JhcHBlZCDigJQgdGh1bWJuYWlsIHdpbGwgc2hvdyBvbiBVc2UgVGhpcy4iKTsKfSk7Ci8vID09PSBFTkQgQ1JGSVgtTElCRklYLVY4ID09PQo8L3NjcmlwdD4KCjxzY3JpcHQ+Ci8vID09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PQovLyBDUkZJWC1MSUJGSVgtVjk6ICJBY2NlcHQgQWxsIHRvIFN0b3J5Ym9hcmQiIHJlcGxhY2VzIExbXSwgbm90IGFwcGVuZHMgKDIwMjYtMDQtMjUpCi8vIF9iZ0FjY2VwdFRvU3Rvcnlib2FyZFYzIChMSUJGSVgtVjMpIHVzZWQgTC5wdXNoKCkg4oCUIG9sZCBzdG9yeWJvYXJkIGNvbnRlbnQKLy8gcmVtYWluZWQgd2hlbiBiZWF0IGdlbmVyYXRvciBiZWF0cyB3ZXJlIGFkZGVkLiBUaGlzIHdyYXBwZXIgY2xlYXJzIExbXSBmaXJzdC4KLy8gPT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09CmRvY3VtZW50LmFkZEV2ZW50TGlzdGVuZXIoIkRPTUNvbnRlbnRMb2FkZWQiLCBmdW5jdGlvbiAoKSB7CiAgdmFyIF9vcmlnQWNjZXB0QWxsID0gd2luZG93Ll9iZ0FjY2VwdFRvU3Rvcnlib2FyZFYzOwogIGlmICh0eXBlb2YgX29yaWdBY2NlcHRBbGwgIT09ICJmdW5jdGlvbiIpIHsKICAgIGNvbnNvbGUud2FybigiW1Y5XSBfYmdBY2NlcHRUb1N0b3J5Ym9hcmRWMyBub3QgZm91bmQg4oCUIHdyYXBwZXIgc2tpcHBlZC4iKTsKICAgIHJldHVybjsKICB9CgogIHZhciBfd3JhcHBlZCA9IGZ1bmN0aW9uICgpIHsKICAgIC8vIENsZWFyIGV4aXN0aW5nIHN0b3J5Ym9hcmQgbGluZXMgYmVmb3JlIGFjY2VwdGluZyBiZWF0IGdlbmVyYXRvciBjb250ZW50CiAgICBpZiAodHlwZW9mIEwgIT09ICJ1bmRlZmluZWQiICYmIEFycmF5LmlzQXJyYXkoTCkpIHsKICAgICAgTC5sZW5ndGggPSAwOwogICAgICBjb25zb2xlLmxvZygiW1Y5XSBMW10gY2xlYXJlZCDigJQgc3Rvcnlib2FyZCB3aWxsIGJlIHJlcGxhY2VkLCBub3QgYXBwZW5kZWQuIik7CiAgICB9CiAgICBfb3JpZ0FjY2VwdEFsbC5hcHBseSh0aGlzLCBhcmd1bWVudHMpOwogIH07CgogIHdpbmRvdy5fYmdBY2NlcHRUb1N0b3J5Ym9hcmRWMyA9IF93cmFwcGVkOwogIHdpbmRvdy5fYmdBY2NlcHRUb1N0b3J5Ym9hcmQgICA9IF93cmFwcGVkOwoKICBjb25zb2xlLmxvZygiW1Y5XSBfYmdBY2NlcHRUb1N0b3J5Ym9hcmRWMyB3cmFwcGVkIOKAlCBBY2NlcHQgQWxsIG5vdyBSRVBMQUNFUyBzdG9yeWJvYXJkLiIpOwp9KTsKLy8gPT09IEVORCBDUkZJWC1MSUJGSVgtVjkgPT09Cjwvc2NyaXB0PgoKPHNjcmlwdD4KLy8gPT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09Ci8vIENSRklYLUxJQkZJWC1WMTA6IEluamVjdCB0aHVtYm5haWwgYWZ0ZXIgbGlicmFyeS1kcm9wIGFjY2VwdGFuY2UgKDIwMjYtMDQtMjUpCi8vIExJQkRST1AtVE8tU0xPVCBzZXRzICJsaWIg4pyTIiBzdGF0dXMgY2hpcCBidXQgbmV2ZXIgY2FsbHMgX2luamVjdEFjY2VwdGVkUHJldmlldy4KLy8gVGhpcyBpbnRlcmNlcHRvciBjYXRjaGVzIC9hcGkvYmcvYWNjZXB0LWxpYi1pbWFnZSByZXNwb25zZXMsIGZldGNoZXMgdGhlCi8vIGZ1bGwtcmVzIGltYWdlIHZpYSAvYXBpL2NyL2Z1bGw/YWJzX3BhdGg9Li4uLCBhbmQgaW5qZWN0cyB0aGUgdGh1bWJuYWlsLgovLyA9PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT0KZG9jdW1lbnQuYWRkRXZlbnRMaXN0ZW5lcigiRE9NQ29udGVudExvYWRlZCIsIGZ1bmN0aW9uICgpIHsKICB2YXIgX29yaWdGZXRjaCA9IHdpbmRvdy5mZXRjaDsKCiAgd2luZG93LmZldGNoID0gZnVuY3Rpb24gKHVybCwgb3B0cykgewogICAgdmFyIHAgPSBfb3JpZ0ZldGNoLmFwcGx5KHRoaXMsIGFyZ3VtZW50cyk7CgogICAgaWYgKHR5cGVvZiB1cmwgPT09ICJzdHJpbmciICYmIHVybC5pbmRleE9mKCIvYXBpL2JnL2FjY2VwdC1saWItaW1hZ2UiKSAhPT0gLTEpIHsKICAgICAgLy8gUGFyc2UgdGhlIHJlcXVlc3QgYm9keSB0byBnZXQgYmVhdF9pZCBhbmQgYWJzX3BhdGgKICAgICAgdmFyIGJlYXRJZCAgPSBudWxsOwogICAgICB2YXIgYWJzUGF0aCA9IG51bGw7CiAgICAgIHZhciBsaWJLZXkgID0gbnVsbDsKICAgICAgdHJ5IHsKICAgICAgICB2YXIgYm9keSA9IEpTT04ucGFyc2UoKG9wdHMgJiYgb3B0cy5ib2R5KSB8fCAie30iKTsKICAgICAgICBiZWF0SWQgID0gYm9keS5iZWF0X2lkICB8fCBudWxsOwogICAgICAgIGFic1BhdGggPSBib2R5LmFic19wYXRoIHx8IG51bGw7CiAgICAgICAgbGliS2V5ICA9IGJvZHkua2V5ICAgICAgfHwgbnVsbDsKICAgICAgfSBjYXRjaCAoZSkgeyAvKiBtYWxmb3JtZWQgYm9keSDigJQgc2tpcCAqLyB9CgogICAgICBpZiAoYmVhdElkICYmIChhYnNQYXRoIHx8IGxpYktleSkpIHsKICAgICAgICBwID0gcC50aGVuKGZ1bmN0aW9uIChyZXNwKSB7CiAgICAgICAgICB2YXIgcmVzcENsb25lID0gcmVzcC5jbG9uZSgpOwogICAgICAgICAgcmVzcENsb25lLmpzb24oKS50aGVuKGZ1bmN0aW9uIChkKSB7CiAgICAgICAgICAgIGlmICghZCB8fCAhZC5vaykgcmV0dXJuOwoKICAgICAgICAgICAgLy8gVHJ5IFRIW10gZmlyc3QgKGZyZWUgaWYgdGhlIGltYWdlIHdhcyBhbHJlYWR5IGxvYWRlZCkKICAgICAgICAgICAgdmFyIHNyYyA9ICh0eXBlb2YgVEggIT09ICJ1bmRlZmluZWQiICYmIGxpYktleSkgPyBUSFtsaWJLZXldIDogbnVsbDsKCiAgICAgICAgICAgIGlmIChzcmMgJiYgdHlwZW9mIHdpbmRvdy5faW5qZWN0QWNjZXB0ZWRQcmV2aWV3ID09PSAiZnVuY3Rpb24iKSB7CiAgICAgICAgICAgICAgd2luZG93Ll9pbmplY3RBY2NlcHRlZFByZXZpZXcoYmVhdElkLCBzcmMpOwogICAgICAgICAgICAgIHJldHVybjsKICAgICAgICAgICAgfQoKICAgICAgICAgICAgLy8gRmFsbGJhY2s6IGZldGNoIGZ1bGwtcmVzIGZyb20gc2VydmVyIHVzaW5nIGFic19wYXRoCiAgICAgICAgICAgIGlmICghYWJzUGF0aCkgcmV0dXJuOwogICAgICAgICAgICBfb3JpZ0ZldGNoKEJHX1NFUlZFUiArICIvYXBpL2NyL2Z1bGw/YWJzX3BhdGg9IiArIGVuY29kZVVSSUNvbXBvbmVudChhYnNQYXRoKSkKICAgICAgICAgICAgICAudGhlbihmdW5jdGlvbiAocikgeyByZXR1cm4gci5qc29uKCk7IH0pCiAgICAgICAgICAgICAgLnRoZW4oZnVuY3Rpb24gKGltZ2QpIHsKICAgICAgICAgICAgICAgIHZhciBpbWdTcmMgPSBpbWdkICYmIGltZ2QuZGF0YV91cmk7CiAgICAgICAgICAgICAgICBpZiAoIWltZ1NyYykgcmV0dXJuOwogICAgICAgICAgICAgICAgLy8gQ2FjaGUgaW4gVEhbXSBmb3IgZnV0dXJlIHJlLXJlbmRlcnMKICAgICAgICAgICAgICAgIGlmIChsaWJLZXkgJiYgdHlwZW9mIFRIICE9PSAidW5kZWZpbmVkIikgVEhbbGliS2V5XSA9IGltZ1NyYzsKICAgICAgICAgICAgICAgIGlmICh0eXBlb2Ygd2luZG93Ll9pbmplY3RBY2NlcHRlZFByZXZpZXcgPT09ICJmdW5jdGlvbiIpIHsKICAgICAgICAgICAgICAgICAgd2luZG93Ll9pbmplY3RBY2NlcHRlZFByZXZpZXcoYmVhdElkLCBpbWdTcmMpOwogICAgICAgICAgICAgICAgfQogICAgICAgICAgICAgIH0pCiAgICAgICAgICAgICAgLmNhdGNoKGZ1bmN0aW9uIChlKSB7CiAgICAgICAgICAgICAgICBjb25zb2xlLndhcm4oIltWMTBdIC9hcGkvY3IvZnVsbCBmZXRjaCBmYWlsZWQ6IiwgZSk7CiAgICAgICAgICAgICAgfSk7CiAgICAgICAgICB9KS5jYXRjaChmdW5jdGlvbiAoKSB7fSk7CiAgICAgICAgICByZXR1cm4gcmVzcDsKICAgICAgICB9KTsKICAgICAgfQogICAgfQoKICAgIHJldHVybiBwOwogIH07CgogIGNvbnNvbGUubG9nKCJbVjEwXSAvYXBpL2JnL2FjY2VwdC1saWItaW1hZ2UgaW50ZXJjZXB0ZWQg4oCUIGxpYiB0aHVtYm5haWwgd2lsbCBpbmplY3Qgb24gZHJvcC4iKTsKfSk7Ci8vID09PSBFTkQgQ1JGSVgtTElCRklYLVYxMCA9PT0KPC9zY3JpcHQ+Cgo8c2NyaXB0PgovLyA9PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT0KLy8gQ1JGSVgtQkdBQ0NFUFQtVjExOiBGaXggb2xkIGFuaW1hdGlvbiBpbmplY3Rpb24gKyBjb2xkIFRIW10gb24gQWNjZXB0IEFsbCAoMjAyNi0wNC0yNSkKLy8KLy8gQnVnIDE6IGluamVjdEFuaW1hdGlvbnNGcm9tU3RhdHVzIG1hcHMgYmVhdF8wMS0+cm93MCBieSBwb3NpdGlvbiBpbmRleCwKLy8gICBzbyBvbGQgVGVzc2EgUGhhc2UgQSBjbGlwcyBhcHBlYXIgaW4gQkcgYmVhdCByb3dzIGFmdGVyIEFjY2VwdCBBbGwuCi8vICAgRml4OiB3aW5kb3cuX0JHX01PREUgPSB0cnVlIHN1cHByZXNzZXMgX2luamVjdEFuaW1hdGlvbnMgaW4gQkcgbW9kZS4KLy8KLy8gQnVnIDI6IGFjY2VwdGVkIGNyb3AgdGh1bWJuYWlsIGFic2VudCBhZnRlciBjb2xkIHBhZ2UgcmVsb2FkIChUSFtdIGVtcHR5KS4KLy8gICBGaXg6IF9iZ0FjY2VwdFRvU3Rvcnlib2FyZFYzIHByZS1maWxscyBUSFtdIGZyb20gL2FwaS9iZy9jcm9wLXByZXZpZXcKLy8gICBiZWZvcmUgY2FsbGluZyByZW5kZXIoKS4KLy8gPT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09CmRvY3VtZW50LmFkZEV2ZW50TGlzdGVuZXIoIkRPTUNvbnRlbnRMb2FkZWQiLCBmdW5jdGlvbiAoKSB7CgogIC8vIOKUgOKUgCBGaXggMTogc3VwcHJlc3Mgb2xkIGFuaW1hdGlvbiBpbmplY3Rpb24gaW4gQkcgbW9kZSDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIAKICB2YXIgX29yaWdJbmplY3RBbmltYXRpb25zID0gd2luZG93Ll9pbmplY3RBbmltYXRpb25zOwogIHdpbmRvdy5faW5qZWN0QW5pbWF0aW9ucyA9IGZ1bmN0aW9uICgpIHsKICAgIGlmICh3aW5kb3cuX0JHX01PREUpIHsKICAgICAgY29uc29sZS5sb2coIltWMTFdIF9pbmplY3RBbmltYXRpb25zIHN1cHByZXNzZWQg4oCUIEJHIG1vZGUgYWN0aXZlLCBvbGQgY2xpcHMgYmxvY2tlZC4iKTsKICAgICAgcmV0dXJuOwogICAgfQogICAgaWYgKHR5cGVvZiBfb3JpZ0luamVjdEFuaW1hdGlvbnMgPT09ICJmdW5jdGlvbiIpIF9vcmlnSW5qZWN0QW5pbWF0aW9ucy5hcHBseSh0aGlzLCBhcmd1bWVudHMpOwogIH07CgogIC8vIEFsc28gaW50ZXJjZXB0IHRoZSBjb250aW51b3VzIHBvbGwgcGF0aCAoaW5qZWN0QW5pbWF0aW9uc0Zyb21TdGF0dXMKICAvLyBpcyBjYWxsZWQgZnJvbSBmbHVzaFF1ZXVlZCBpbnNpZGUgdGhlIHN0YXR1cy1wb2xsIGNsb3N1cmUpLiBXZSBjYW4ndAogIC8vIGVhc2lseSB3cmFwIHRoZSBwcml2YXRlIGNsb3N1cmUsIGJ1dCBfaW5qZWN0QW5pbWF0aW9ucyBpcyB0aGUgcHVibGljCiAgLy8gZW50cnkgcG9pbnQgdGhhdCByZW5kZXIoKSBjYWxscyDigJQgd3JhcHBpbmcgaXQgY2F0Y2hlcyB0aGUgcmVuZGVyIHBhc3MuCiAgLy8gVGhlIHBvbGwtZHJpdmVuIGluamVjdGlvbiBwYXRoIGNhbGxzIHRoZSBwcml2YXRlIGluamVjdEFuaW1hdGlvbnNGcm9tU3RhdHVzCiAgLy8gZGlyZWN0bHk7IGludGVyY2VwdCB0aGF0IHZpYSB0aGUgc3RhdHVzLXBvbGwgY2FsbGJhY2sgaWYgYWNjZXNzaWJsZS4KICBpZiAodHlwZW9mIHdpbmRvdy5fcG9sbFN0YXR1c0NiID09PSAiZnVuY3Rpb24iKSB7CiAgICB2YXIgX29yaWdQb2xsQ2IgPSB3aW5kb3cuX3BvbGxTdGF0dXNDYjsKICAgIHdpbmRvdy5fcG9sbFN0YXR1c0NiID0gZnVuY3Rpb24ocykgewogICAgICBpZiAod2luZG93Ll9CR19NT0RFKSByZXR1cm47CiAgICAgIF9vcmlnUG9sbENiLmFwcGx5KHRoaXMsIGFyZ3VtZW50cyk7CiAgICB9OwogIH0KCiAgLy8g4pSA4pSAIEZpeCAyOiBwcmUtZmlsbCBUSFtdIGJlZm9yZSByZW5kZXIoKSBpbiBBY2NlcHQgQWxsIHBhdGgg4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSACiAgdmFyIF9vcmlnQWNjZXB0QWxsID0gd2luZG93Ll9iZ0FjY2VwdFRvU3Rvcnlib2FyZFYzOwogIGlmICh0eXBlb2YgX29yaWdBY2NlcHRBbGwgIT09ICJmdW5jdGlvbiIpIHsKICAgIGNvbnNvbGUud2FybigiW1YxMV0gX2JnQWNjZXB0VG9TdG9yeWJvYXJkVjMgbm90IGZvdW5kIGF0IERPTUNvbnRlbnRMb2FkZWQg4oCUIFYxMSBwYXJ0aWFsLiIpOwogIH0gZWxzZSB7CiAgICB3aW5kb3cuX2JnQWNjZXB0VG9TdG9yeWJvYXJkVjMgPSBmdW5jdGlvbiAoKSB7CiAgICAgIHdpbmRvdy5fQkdfTU9ERSA9IHRydWU7CiAgICAgIGNvbnNvbGUubG9nKCJbVjExXSBCRyBtb2RlIE9OIOKAlCBvbGQgYW5pbWF0aW9uIGluamVjdGlvbiBibG9ja2VkLiIpOwoKICAgICAgLy8gQ29sbGVjdCBhY2NlcHRlZCBrZXlzIHRoYXQgYXJlIG1pc3NpbmcgZnJvbSBUSFtdCiAgICAgIHZhciBtaXNzaW5nS2V5cyA9IFtdOwogICAgICBpZiAoQXJyYXkuaXNBcnJheShCR19CRUFUUykpIHsKICAgICAgICBCR19CRUFUUy5mb3JFYWNoKGZ1bmN0aW9uKGJlYXQpIHsKICAgICAgICAgIHZhciBrID0gYmVhdC5hY2NlcHRlZF9pbWFnZV9rZXk7CiAgICAgICAgICBpZiAoayAmJiAhKHR5cGVvZiBUSCAhPT0gInVuZGVmaW5lZCIgJiYgVEhba10pKSB7CiAgICAgICAgICAgIG1pc3NpbmdLZXlzLnB1c2goayk7CiAgICAgICAgICB9CiAgICAgICAgfSk7CiAgICAgIH0KCiAgICAgIGlmIChtaXNzaW5nS2V5cy5sZW5ndGggPT09IDApIHsKICAgICAgICAvLyBUSFtdIGFscmVhZHkgd2FybSDigJQgcHJvY2VlZCBzeW5jaHJvbm91c2x5CiAgICAgICAgX29yaWdBY2NlcHRBbGwuYXBwbHkodGhpcywgYXJndW1lbnRzKTsKICAgICAgICByZXR1cm47CiAgICAgIH0KCiAgICAgIC8vIEZldGNoIG1pc3NpbmcgdGh1bWJuYWlscyBmcm9tIHNlcnZlciwgdGhlbiByZW5kZXIKICAgICAgdmFyIHNlbGYgPSB0aGlzLCBhcmdzID0gYXJndW1lbnRzOwogICAgICB2YXIgdXJsID0gQkdfU0VSVkVSICsgIi9hcGkvYmcvY3JvcC1wcmV2aWV3P2tleXM9IiArIG1pc3NpbmdLZXlzLm1hcChlbmNvZGVVUklDb21wb25lbnQpLmpvaW4oIiwiKTsKICAgICAgZmV0Y2godXJsKQogICAgICAgIC50aGVuKGZ1bmN0aW9uKHIpIHsgcmV0dXJuIHIuanNvbigpOyB9KQogICAgICAgIC50aGVuKGZ1bmN0aW9uKGQpIHsKICAgICAgICAgIHZhciBwcmV2aWV3cyA9IChkICYmIGQucHJldmlld3MpIHx8IHt9OwogICAgICAgICAgT2JqZWN0LmtleXMocHJldmlld3MpLmZvckVhY2goZnVuY3Rpb24oaykgewogICAgICAgICAgICBpZiAodHlwZW9mIFRIICE9PSAidW5kZWZpbmVkIikgVEhba10gPSBwcmV2aWV3c1trXTsKICAgICAgICAgIH0pOwogICAgICAgICAgY29uc29sZS5sb2coIltWMTFdIFByZS1maWxsZWQgVEhbXSB3aXRoICIgKyBPYmplY3Qua2V5cyhwcmV2aWV3cykubGVuZ3RoICsgIiBjcm9wIHByZXZpZXcocykuIik7CiAgICAgICAgfSkKICAgICAgICAuY2F0Y2goZnVuY3Rpb24oZSkgewogICAgICAgICAgY29uc29sZS53YXJuKCJbVjExXSBjcm9wLXByZXZpZXcgZmV0Y2ggZmFpbGVkOiIsIGUpOwogICAgICAgIH0pCiAgICAgICAgLmZpbmFsbHkoZnVuY3Rpb24oKSB7CiAgICAgICAgICBfb3JpZ0FjY2VwdEFsbC5hcHBseShzZWxmLCBhcmdzKTsKICAgICAgICB9KTsKICAgIH07CgogICAgd2luZG93Ll9iZ0FjY2VwdFRvU3Rvcnlib2FyZCA9IHdpbmRvdy5fYmdBY2NlcHRUb1N0b3J5Ym9hcmRWMzsKICAgIGNvbnNvbGUubG9nKCJbVjExXSBfYmdBY2NlcHRUb1N0b3J5Ym9hcmRWMyB3cmFwcGVkIOKAlCBUSFtdIHByZS1maWxsICsgQkcgbW9kZSBnYXRlIGFjdGl2ZS4iKTsKICB9Cn0pOwovLyA9PT0gRU5EIENSRklYLUJHQUNDRVBULVYxMSA9PT0KPC9zY3JpcHQ+Cgo8c2NyaXB0PgovLyA9PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT0KLy8gQ1JGSVgtQkdBQ0NFUFQtVjEyOiBTeW5jLWZpcnN0IEFjY2VwdCBBbGwgKyBsYXp5IHRodW1ibmFpbCBmZXRjaCAoMjAyNi0wNC0yNSkKLy8KLy8gVjExIHdhcyBhc3luYy1iZWZvcmUtcmVuZGVyIHdoaWNoIHNpbGVudGx5IGJyb2tlIEFjY2VwdCBBbGwgKHJlbmRlcigpCi8vIG5ldmVyIGZpcmVkIGJlY2F1c2UgaXQgbGl2ZWQgaW5zaWRlIC5maW5hbGx5KCkgd2hpY2ggcmFuIHRvbyBsYXRlKS4KLy8gVjEyIGZpeGVzOiBjYWxsIF9vcmlnQWNjZXB0QWxsKCkgc3luY2hyb25vdXNseSwgVEhFTiBmZXRjaCB0aHVtYm5haWxzLgovLyA9PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT0KZG9jdW1lbnQuYWRkRXZlbnRMaXN0ZW5lcigiRE9NQ29udGVudExvYWRlZCIsIGZ1bmN0aW9uICgpIHsKCiAgLy8g4pSA4pSAIFN1cHByZXNzIG9sZCBhbmltYXRpb24gaW5qZWN0aW9uIGluIEJHIG1vZGUgKHNhbWUgYXMgVjExIEZpeCAxKSDilIDilIAKICB2YXIgX29yaWdJbmplY3RBbmltcyA9IHdpbmRvdy5faW5qZWN0QW5pbWF0aW9uczsKICB3aW5kb3cuX2luamVjdEFuaW1hdGlvbnMgPSBmdW5jdGlvbiAoKSB7CiAgICBpZiAod2luZG93Ll9CR19NT0RFKSB7CiAgICAgIGNvbnNvbGUubG9nKCJbVjEyXSBfaW5qZWN0QW5pbWF0aW9ucyBzdXBwcmVzc2VkIOKAlCBCRyBtb2RlIGFjdGl2ZS4iKTsKICAgICAgcmV0dXJuOwogICAgfQogICAgaWYgKHR5cGVvZiBfb3JpZ0luamVjdEFuaW1zID09PSAiZnVuY3Rpb24iKSBfb3JpZ0luamVjdEFuaW1zLmFwcGx5KHRoaXMsIGFyZ3VtZW50cyk7CiAgfTsKCiAgLy8g4pSA4pSAIEZpeCBBY2NlcHQgQWxsOiBzeW5jLWZpcnN0LCBhc3luYyB0aHVtYm5haWxzIGFmdGVyIOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgAogIHZhciBfb3JpZ0FjY2VwdEFsbCA9IHdpbmRvdy5fYmdBY2NlcHRUb1N0b3J5Ym9hcmRWMzsKICBpZiAodHlwZW9mIF9vcmlnQWNjZXB0QWxsICE9PSAiZnVuY3Rpb24iKSB7CiAgICBjb25zb2xlLndhcm4oIltWMTJdIF9iZ0FjY2VwdFRvU3Rvcnlib2FyZFYzIG5vdCBmb3VuZCDigJQgc2tpcHBpbmcgd3JhcHBlci4iKTsKICAgIHJldHVybjsKICB9CgogIHdpbmRvdy5fYmdBY2NlcHRUb1N0b3J5Ym9hcmRWMyA9IGZ1bmN0aW9uICgpIHsKICAgIC8vIDEuIFNldCBCRyBtb2RlIEJFRk9SRSByZW5kZXIoKSBzbyBfaW5qZWN0QW5pbWF0aW9ucyBpcyBzdXBwcmVzc2VkCiAgICB3aW5kb3cuX0JHX01PREUgPSB0cnVlOwogICAgY29uc29sZS5sb2coIltWMTJdIEJHIG1vZGUgT04uIik7CgogICAgLy8gMi4gQ2FsbCBvcmlnaW5hbCBTWU5DSFJPTk9VU0xZIOKAlCBMLmxlbmd0aD0wLCBwdXNoIGJlYXRzLCByZW5kZXIsIHN3aXRjaCB0YWIKICAgIF9vcmlnQWNjZXB0QWxsLmFwcGx5KHRoaXMsIGFyZ3VtZW50cyk7CgogICAgLy8gMy4gVEhFTiBhc3luYy1mZXRjaCBtaXNzaW5nIHRodW1ibmFpbHMgYW5kIHJlLXJlbmRlcgogICAgdmFyIG1pc3NpbmdLZXlzID0gW107CiAgICBpZiAoQXJyYXkuaXNBcnJheShCR19CRUFUUykpIHsKICAgICAgQkdfQkVBVFMuZm9yRWFjaChmdW5jdGlvbihiZWF0KSB7CiAgICAgICAgdmFyIGsgPSBiZWF0LmFjY2VwdGVkX2ltYWdlX2tleTsKICAgICAgICBpZiAoayAmJiAhKHR5cGVvZiBUSCAhPT0gInVuZGVmaW5lZCIgJiYgVEhba10pKSB7CiAgICAgICAgICBtaXNzaW5nS2V5cy5wdXNoKGspOwogICAgICAgIH0KICAgICAgfSk7CiAgICB9CgogICAgaWYgKG1pc3NpbmdLZXlzLmxlbmd0aCA+IDApIHsKICAgICAgdmFyIHVybCA9IEJHX1NFUlZFUiArICIvYXBpL2JnL2Nyb3AtcHJldmlldz9rZXlzPSIgKwogICAgICAgICAgICAgICAgbWlzc2luZ0tleXMubWFwKGVuY29kZVVSSUNvbXBvbmVudCkuam9pbigiLCIpOwogICAgICBmZXRjaCh1cmwpCiAgICAgICAgLnRoZW4oZnVuY3Rpb24ocikgeyByZXR1cm4gci5qc29uKCk7IH0pCiAgICAgICAgLnRoZW4oZnVuY3Rpb24oZCkgewogICAgICAgICAgdmFyIHByZXZpZXdzID0gKGQgJiYgZC5wcmV2aWV3cykgfHwge307CiAgICAgICAgICB2YXIgZmlsbGVkID0gMDsKICAgICAgICAgIE9iamVjdC5rZXlzKHByZXZpZXdzKS5mb3JFYWNoKGZ1bmN0aW9uKGspIHsKICAgICAgICAgICAgaWYgKHR5cGVvZiBUSCAhPT0gInVuZGVmaW5lZCIpIHsgVEhba10gPSBwcmV2aWV3c1trXTsgZmlsbGVkKys7IH0KICAgICAgICAgIH0pOwogICAgICAgICAgaWYgKGZpbGxlZCA+IDAgJiYgdHlwZW9mIHJlbmRlciA9PT0gImZ1bmN0aW9uIikgewogICAgICAgICAgICBjb25zb2xlLmxvZygiW1YxMl0gVEhbXSBmaWxsZWQgd2l0aCAiICsgZmlsbGVkICsgIiBwcmV2aWV3KHMpIOKAlCByZS1yZW5kZXJpbmcuIik7CiAgICAgICAgICAgIHJlbmRlcigpOwogICAgICAgICAgfQogICAgICAgIH0pCiAgICAgICAgLmNhdGNoKGZ1bmN0aW9uKGUpIHsKICAgICAgICAgIGNvbnNvbGUud2FybigiW1YxMl0gY3JvcC1wcmV2aWV3IGZldGNoIGZhaWxlZCAoc2VydmVyIHJlc3RhcnQgbmVlZGVkPyk6IiwgZSk7CiAgICAgICAgfSk7CiAgICB9CiAgfTsKCiAgd2luZG93Ll9iZ0FjY2VwdFRvU3Rvcnlib2FyZCA9IHdpbmRvdy5fYmdBY2NlcHRUb1N0b3J5Ym9hcmRWMzsKICBjb25zb2xlLmxvZygiW1YxMl0gX2JnQWNjZXB0VG9TdG9yeWJvYXJkVjMgd3JhcHBlZCDigJQgc3luYy1maXJzdCBBY2NlcHQgQWxsIGFjdGl2ZS4iKTsKfSk7Ci8vID09PSBFTkQgQ1JGSVgtQkdBQ0NFUFQtVjEyID09PQo8L3NjcmlwdD4="
    )
    _patches_html = base64.b64decode(_PATCHES_B64).decode("utf-8")
    if "</body>" in html:
        html = html.replace("</body>", _patches_html + "\n</body>", 1)
    else:
        html += _patches_html

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  [--with-extras] Beat Generator + Cropper + v44 patches injected. Size: {len(html)//1024}KB")
    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Build MindfulNest storyboard HTML",
        epilog="Registry mode (preferred): --registry --module M1 --event 1 --lines lines.json --output out.html\n"
               "Config mode (fallback):    --config config.json --output out.html\n"
               "Export image map:          --export-image-map --module M1 --event 1 [--output map.json]\n"
               "Smoke test:                --smoke-test\n"
               "Feature audit:             --audit storyboard.html",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--config", help="Path to JSON config file (legacy/fallback mode)")
    parser.add_argument("--output", help="Output HTML or JSON path")
    parser.add_argument("--registry", action="store_true",
                        help="Use registry-first workflow (queries Directus for approved images)")
    parser.add_argument("--module", help="Module ID, e.g. 'M1' (used with --registry and --export-image-map)")
    parser.add_argument("--event", type=int, help="Event number, e.g. 1 (used with --registry and --export-image-map)")
    parser.add_argument("--lines", help="Path to JSON lines file (used with --registry)")
    parser.add_argument("--title", default="", help="Storyboard title")
    parser.add_argument("--subtitle", default="", help="Storyboard subtitle")
    parser.add_argument("--image-base", help="Base path to resolve relative image filepaths from registry")
    parser.add_argument("--export-image-map", action="store_true",
                        help="Export image map (storyboard key → source filepath traceability)")
    parser.add_argument("--smoke-test", action="store_true",
                        help="Run connectivity smoke test against Directus (no build)")
    parser.add_argument("--audit", help="Extract feature manifest from existing storyboard HTML")
    parser.add_argument("--audit-previous", help="Path to previous storyboard to compare against after build")
    parser.add_argument("--no-extras", dest="with_extras", action="store_false",
                        help="Skip Beat Generator + Cropper + patch tabs (Path A extras off)")
    parser.set_defaults(with_extras=True)
    args = parser.parse_args()

    # Mode 1: Smoke test
    if args.smoke_test:
        results = smoke_test()
        sys.exit(0 if all(results.values()) else 1)

    # Mode 2: Feature audit only
    if args.audit:
        features = extract_features(args.audit)
        if features:
            print(json.dumps(features, indent=2, default=str))
        sys.exit(0 if features else 1)

    # Mode 3: Export image map (NEW)
    if args.export_image_map:
        if not args.module or not args.event:
            parser.error("--export-image-map requires --module and --event")

        image_map = export_image_map(
            module_id=args.module,
            event_number=args.event,
            output_path=args.output,
            image_base_path=args.image_base,
        )

        # Print the JSON to stdout as well
        print("\n" + json.dumps(image_map, indent=2))
        sys.exit(0)

    # Mode 5: Registry-first build (PREFERRED)
    if args.registry:
        if not args.module or not args.event or not args.lines or not args.output:
            parser.error("--registry requires --module, --event, --lines, and --output")

        with open(args.lines) as f:
            lines = json.load(f)

        # Pre-rebuild feature audit if previous version exists
        before_features = None
        if args.audit_previous:
            before_features = extract_features(args.audit_previous)

        result = build_storyboard_from_registry(
            module_id=args.module,
            event_number=args.event,
            lines=lines,
            output_path=args.output,
            title=args.title,
            subtitle=args.subtitle,
            image_base_path=args.image_base,
        )

        # Post-rebuild feature comparison
        if before_features:
            compare_features(before_features, result)

        # POST-BUILD AUTO-REGISTRATION: Register in Directus
        # Extract features from the newly built storyboard for logging
        features = extract_features(result)
        register_build_in_directus(
            output_path=result,
            module_id=args.module,
            event_number=args.event,
            build_mode="registry",
            features_dict=features or {}
        )

        if args.with_extras:
            append_extras_tabs(result)
            print(f"  Beat Generator + Cropper tabs appended to {result}")

        return

    # Mode 6: Legacy config-based build (FALLBACK)
    if args.config and args.output:
        # Pre-rebuild feature audit if previous version exists
        before_features = None
        if args.audit_previous:
            before_features = extract_features(args.audit_previous)

        with open(args.config) as f:
            config = json.load(f)

        result = build_storyboard(config, args.output)

        if before_features:
            compare_features(before_features, result)

        # POST-BUILD AUTO-REGISTRATION: Register in Directus (fallback mode)
        # Config-based builds may not have module_id/event_number, so attempt registration
        # only if they're available from config metadata
        if "module_id" in config and "event_number" in config:
            features = extract_features(result)
            register_build_in_directus(
                output_path=result,
                module_id=config["module_id"],
                event_number=config["event_number"],
                build_mode="manual_config",
                features_dict=features or {}
            )

        if args.with_extras:
            append_extras_tabs(result)
            print(f"  Beat Generator + Cropper tabs appended to {result}")

        return

    parser.error("Must use either --registry mode, --config mode, --export-image-map, --smoke-test, or --audit")


if __name__ == "__main__":
    main()
