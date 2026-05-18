#!/usr/bin/env python3
"""
MindfulNest — Reference Image Selector + Cropper Builder
=========================================================
Generates a unified HTML tool that combines image browsing/selection with
4:3 cropping — all on one screen. Kim can browse master images, select them
for a module/event, crop close-ups, and export decisions.

USAGE (Registry mode — queries Directus for available masters):
    python3 build_image_selector_cropper.py --registry --module M1 --event 1 --output selector_cropper.html

USAGE (Local images mode — provide image paths directly):
    python3 build_image_selector_cropper.py --images img1.png img2.png --output selector_cropper.html

USAGE (Smoke test — verify Directus connectivity):
    python3 build_image_selector_cropper.py --smoke-test

USAGE (Audit — extract feature manifest from built HTML):
    python3 build_image_selector_cropper.py --audit existing_tool.html

USAGE (Audit Previous — regression check):
    python3 build_image_selector_cropper.py --audit-previous new.html old.html

Architecture: Part 6 of PRODUCTION_ARCHITECTURE_MASTER_v2.md
Constraints: CLAUDE.md Rule 6 (600px min), Rule 7 (Two-Path Protocol), Rule 10 (4:3 crops)
"""

import argparse
import base64
import json
import os
import re
import sys
from pathlib import Path
from datetime import datetime, timezone

try:
    import requests
except ImportError:
    requests = None


# ─── DIRECTUS UTILITIES ────────────────────────────────────────────────────

def read_gemini_api_key():
    """Read Gemini API key from API_KEYS_MASTER.md or env var."""
    # Try env var first
    key = os.environ.get('GEMINI_API_KEY')
    if key:
        return key
    # Try API_KEYS_MASTER.md
    script_dir = Path(__file__).parent
    keys_file = script_dir.parent / "API_KEYS_MASTER.md"
    if keys_file.exists():
        with open(keys_file, 'r') as f:
            content = f.read()
        match = re.search(r'Gemini.*?`(AIzaSy[A-Za-z0-9_-]+)`', content, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1)
        # Try loose pattern
        match = re.search(r'AIzaSy[A-Za-z0-9_-]{33}', content)
        if match:
            return match.group(0)
    return None


def read_directus_credentials():
    """Read Directus credentials from API_KEYS_MASTER.md."""
    script_dir = Path(__file__).parent
    keys_file = script_dir.parent / "API_KEYS_MASTER.md"
    if not keys_file.exists():
        raise FileNotFoundError(f"API_KEYS_MASTER.md not found at {keys_file}")
    with open(keys_file, 'r') as f:
        content = f.read()
    email_match = re.search(r'\|\s*\*\*Directus\*\*.*?Admin Email\s*\|\s*`?([^`\|]+)`?\s*\|', content)
    pass_match = re.search(r'Admin Password\s*\|\s*`([^`]+)`', content)
    url_match = re.search(r'URL:\s*([^\s\)]+)', content)
    if not (email_match and pass_match and url_match):
        raise ValueError("Could not extract Directus credentials from API_KEYS_MASTER.md")
    return {
        'email': email_match.group(1).strip(),
        'password': pass_match.group(1).strip(),
        'url': url_match.group(1).strip()
    }


def directus_auth(creds):
    """Authenticate with Directus, return (access_token, base_url)."""
    base_url = creds['url'].rstrip('/')
    resp = requests.post(f"{base_url}/auth/login", json={
        'email': creds['email'], 'password': creds['password']
    }, timeout=10)
    resp.raise_for_status()
    token = resp.json().get('data', {}).get('access_token')
    if not token:
        raise RuntimeError("No access_token in Directus auth response")
    return token, base_url


def query_registry_images(token, base_url, module_id=None, event_number=None):
    """Query prod_visual_assets for master/source images."""
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    filters = {'asset_type': {'_in': ['source_image', 'crop_4x3', 'master_image', 'reference_master', 'crop']}}
    if module_id is not None:
        filters['module_id'] = {'_eq': module_id}
    if event_number is not None:
        filters['event_number'] = {'_eq': event_number}
    params = {
        'filter': json.dumps(filters),
        'fields': 'id,filename,filepath,asset_type,module_id,event_number,status,source_asset_id',
        'limit': 100
    }
    resp = requests.get(f"{base_url}/items/prod_visual_assets", params=params,
                        headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json().get('data', [])


def register_in_directus(token, base_url, output_path, module_id, event_number, image_count, source_images):
    """Two-Write Rule: register in prod_visual_assets AND prod_activity_log."""
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    filename = Path(output_path).name

    # Write 1: Activity log FIRST (records intent — survives if asset write fails)
    activity_payload = {
        'module_id': module_id,
        'event_number': event_number,
        'action': 'image_selector_cropper_build',
        'details': json.dumps({
            'filename': filename,
            'image_count': image_count,
            'source_images': source_images,
            'output_path': str(output_path),
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
    }
    try:
        log_resp = requests.post(f"{base_url}/items/prod_activity_log", json=activity_payload,
                                 headers=headers, timeout=10)
        log_resp.raise_for_status()
        print(f"✓ Directus: Logged image_selector_cropper_build to prod_activity_log")
    except Exception as e:
        print(f"WARNING: Activity log write failed: {e}", file=sys.stderr)

    # Write 2: Asset registration
    query_params = {
        'filter': json.dumps({'filename': {'_eq': filename}}),
        'limit': 1
    }
    query_resp = requests.get(f"{base_url}/items/prod_visual_assets", params=query_params,
                              headers=headers, timeout=10)
    query_resp.raise_for_status()
    existing = query_resp.json().get('data', [])

    asset_payload = {
        'filename': filename,
        'asset_type': 'production_tool',
        'module_id': module_id,
        'event_number': event_number,
        'status': 'built',
        'filepath': str(output_path),
        'shot_number': 0,
        'width': 0,
        'height': 0,
        'aspect_ratio': 'N/A',
        'purpose': 'Image selection and 4:3 cropping tool'
    }

    if existing:
        asset_id = existing[0]['id']
        resp = requests.patch(f"{base_url}/items/prod_visual_assets/{asset_id}",
                              json=asset_payload, headers=headers, timeout=10)
        resp.raise_for_status()
        print(f"✓ Directus: Updated prod_visual_assets/{asset_id} ({filename})")
    else:
        resp = requests.post(f"{base_url}/items/prod_visual_assets",
                             json=asset_payload, headers=headers, timeout=10)
        resp.raise_for_status()
        new_id = resp.json().get('data', {}).get('id')
        print(f"✓ Directus: Created prod_visual_assets/{new_id} ({filename})")


# ─── SMOKE TEST ─────────────────────────────────────────────────────────────

def smoke_test():
    """Verify Directus connectivity and schema."""
    if requests is None:
        print("FAIL: requests library not installed")
        return False
    try:
        creds = read_directus_credentials()
        print(f"✓ Credentials loaded from API_KEYS_MASTER.md")
        token, base_url = directus_auth(creds)
        print(f"✓ Auth: token acquired from {base_url}")

        headers = {'Authorization': f'Bearer {token}'}
        # Check prod_visual_assets
        resp = requests.get(f"{base_url}/items/prod_visual_assets?limit=1",
                            headers=headers, timeout=10)
        resp.raise_for_status()
        print(f"✓ Registry: prod_visual_assets accessible")

        # Check prod_activity_log
        resp = requests.get(f"{base_url}/items/prod_activity_log?limit=1",
                            headers=headers, timeout=10)
        resp.raise_for_status()
        print(f"✓ Registry: prod_activity_log accessible")

        # Check prod_modules
        resp = requests.get(f"{base_url}/items/prod_modules?limit=1",
                            headers=headers, timeout=10)
        resp.raise_for_status()
        print(f"✓ Registry: prod_modules accessible")

        print("\nSMOKE TEST: PASS")
        return True
    except Exception as e:
        print(f"\nSMOKE TEST: FAIL — {e}")
        return False


# ─── AUDIT ──────────────────────────────────────────────────────────────────

def extract_features(html_path):
    """Extract feature manifest from built HTML."""
    with open(html_path, 'r') as f:
        content = f.read()

    # Try to extract embedded metadata comment
    meta_match = re.search(r'<!--\s*TOOL_METADATA\s*(.*?)\s*-->', content, re.DOTALL)
    metadata = {}
    if meta_match:
        try:
            metadata = json.loads(meta_match.group(1))
        except json.JSONDecodeError:
            pass

    # Get image count from metadata or from masters JSON
    image_count = metadata.get('image_count', 0)
    if image_count == 0:
        # Fallback: count masters in embedded JSON
        masters_match = re.search(r'const masters = (\[.*?\]);', content, re.DOTALL)
        if masters_match:
            try:
                image_count = len(json.loads(masters_match.group(1)))
            except (json.JSONDecodeError, TypeError):
                image_count = len(re.findall(r'"id":\s*"master_', content))

    # Check feature flags from metadata
    flags = metadata.get('feature_flags', {})

    features = {
        'tool_name': metadata.get('tool_name', 'unknown'),
        'version': metadata.get('version', 'unknown'),
        'generated_at': metadata.get('generated_at', 'unknown'),
        'image_count': image_count,
        'has_crop_canvas': 'id="cropCanvas"' in content,
        'has_image_browser': 'id="imageBrowser"' in content,
        'has_export': 'buildExportJSON' in content or 'Export' in content,
        'has_localStorage': 'localStorage' in content,
        'has_size_enforcement': 'MIN_DIMENSION' in content,
        'has_directus_registration': flags.get('localStorage_persistence', False) or 'register_in_directus' in content or 'Two-Write' in content,
        'has_dark_theme': '#1a1a2e' in content,
        'has_4x3_lock': '4 / 3' in content or '4/3' in content,
        'has_batch_save': 'btnSaveAll' in content,
        'has_file_input': 'fileInput' in content,
        'has_generation': 'GEMINI_API_KEY' in content and 'generateImages' in content,
        'has_import_drag_drop': 'handleFileDrop' in content,
        'has_source_tracking': 'source-badge' in content,
        'has_toast_notifications': 'toast-container' in content,
        'has_gen_panel': 'gen-panel' in content,
        'file_size_mb': round(os.path.getsize(html_path) / (1024 * 1024), 2),
    }
    return features


def audit(html_path):
    """Print feature manifest for a built HTML."""
    features = extract_features(html_path)
    print(f"AUDIT: {html_path}")
    print(f"{'─' * 50}")
    for k, v in features.items():
        status = '✓' if v and v not in ('unknown', 0, False) else '✗'
        print(f"  {status} {k}: {v}")
    return features


def audit_previous(new_path, old_path):
    """Compare features between new and old builds."""
    new_f = extract_features(new_path)
    old_f = extract_features(old_path)
    regressions = []
    print(f"AUDIT-PREVIOUS: {Path(new_path).name} vs {Path(old_path).name}")
    print(f"{'─' * 60}")
    for key in sorted(set(list(new_f.keys()) + list(old_f.keys()))):
        old_v = old_f.get(key, 'N/A')
        new_v = new_f.get(key, 'N/A')
        if old_v is True and new_v is not True:
            regressions.append(key)
            print(f"  🔴 REGRESSION {key}: {old_v} → {new_v}")
        elif old_v != new_v:
            print(f"  🟡 CHANGED    {key}: {old_v} → {new_v}")
        else:
            print(f"  🟢 OK         {key}: {new_v}")

    if regressions:
        print(f"\n⛔ {len(regressions)} REGRESSION(S) DETECTED — do not deliver.")
        return False
    else:
        print(f"\n✅ No regressions detected.")
        return True


# ─── IMAGE ENCODING ────────────────────────────────────────────────────────

def encode_image(path, as_jpeg=True, quality=85):
    """Encode an image file as base64 data URI. Optionally convert to JPEG for size."""
    path = Path(path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {path}")

    suffix = path.suffix.lower()
    mime_map = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                '.webp': 'image/webp', '.gif': 'image/gif'}

    if as_jpeg and suffix == '.png':
        # Convert PNG to JPEG for smaller base64 size
        try:
            from PIL import Image
            img = Image.open(path)
            if img.mode == 'RGBA':
                bg = Image.new('RGB', img.size, (26, 26, 46))  # dark theme bg
                bg.paste(img, mask=img.split()[3])
                img = bg
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            import io
            buf = io.BytesIO()
            img.save(buf, format='JPEG', quality=quality)
            b64 = base64.b64encode(buf.getvalue()).decode()
            return f"data:image/jpeg;base64,{b64}", img.size[0], img.size[1]
        except ImportError:
            pass  # Fall through to raw encoding

    mime = mime_map.get(suffix, 'image/png')
    with open(path, 'rb') as f:
        raw = f.read()
    b64 = base64.b64encode(raw).decode()

    # Get dimensions
    w, h = 0, 0
    try:
        from PIL import Image
        img = Image.open(path)
        w, h = img.size
    except ImportError:
        # Try to parse PNG/JPEG header
        if raw[:8] == b'\x89PNG\r\n\x1a\n' and len(raw) > 24:
            import struct
            w = struct.unpack('>I', raw[16:20])[0]
            h = struct.unpack('>I', raw[20:24])[0]
        elif raw[:2] == b'\xff\xd8':
            # JPEG — scan for SOF marker
            i = 2
            while i < len(raw) - 9:
                if raw[i] == 0xFF and raw[i+1] in (0xC0, 0xC2):
                    import struct
                    h = struct.unpack('>H', raw[i+5:i+7])[0]
                    w = struct.unpack('>H', raw[i+7:i+9])[0]
                    break
                i += 2 + (raw[i+2] << 8 | raw[i+3]) if raw[i] == 0xFF else 1

    return f"data:{mime};base64,{b64}", w, h


def encode_image_thumbnail(path, max_size=256):
    """Create a small thumbnail data URI for the browser panel."""
    try:
        from PIL import Image
        import io
        img = Image.open(path)
        img.thumbnail((max_size, max_size), Image.LANCZOS)
        if img.mode == 'RGBA':
            bg = Image.new('RGB', img.size, (26, 26, 46))
            bg.paste(img, mask=img.split()[3])
            img = bg
        elif img.mode != 'RGB':
            img = img.convert('RGB')
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=75)
        b64 = base64.b64encode(buf.getvalue()).decode()
        return f"data:image/jpeg;base64,{b64}"
    except ImportError:
        # PIL not available — return full image as fallback
        data_uri, _, _ = encode_image(path, as_jpeg=True, quality=60)
        return data_uri


# ─── HTML TEMPLATE ──────────────────────────────────────────────────────────

TOOL_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>MindfulNest — Image Selector + Cropper{{TITLE_SUFFIX}}</title>
<!-- TOOL_METADATA {{METADATA_JSON}} -->
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #1a1a2e; color: #e0e0e0; overflow: hidden; }

  /* ─── HEADER ─── */
  .header { padding: 12px 20px; background: #16213e; border-bottom: 1px solid #0f3460; display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
  .header h1 { font-size: 17px; color: #e94560; white-space: nowrap; }
  .header .subtitle { font-size: 12px; color: #888; }
  .header .status { margin-left: auto; font-size: 12px; color: #4caf50; }

  /* ─── TOOLBAR ─── */
  .toolbar { padding: 8px 20px; background: #1a1a2e; border-bottom: 1px solid #333; display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
  .toolbar button { padding: 5px 12px; border: 1px solid #0f3460; background: #16213e; color: #e0e0e0; border-radius: 4px; cursor: pointer; font-size: 12px; }
  .toolbar button:hover { background: #0f3460; }
  .toolbar button.primary { background: #e94560; border-color: #e94560; color: #fff; font-weight: 600; }
  .toolbar button.primary:hover { background: #c73550; }
  .toolbar button:disabled { opacity: 0.4; cursor: default; }
  .toolbar .sep { width: 1px; height: 20px; background: #333; }
  .toolbar label { font-size: 12px; color: #aaa; }

  .dimensions-display { padding: 4px 8px; background: #16213e; border: 1px solid #0f3460; border-radius: 4px; font-size: 12px; color: #e0e0e0; font-family: monospace; }
  .dimensions-display.warning { border-color: #ffeb3b; color: #ffeb3b; }
  .dimensions-display.ready { border-color: #4caf50; color: #4caf50; }
  .size-banner { padding: 5px 10px; border-radius: 4px; font-size: 12px; font-weight: 600; display: none; }
  .size-banner.warning { background: #ffeb3b; color: #000; display: flex; }
  .size-banner.ready { background: #4caf50; color: #fff; display: flex; }

  /* ─── MAIN THREE-PANEL LAYOUT ─── */
  .main { display: flex; height: calc(100vh - 88px); }

  /* Left panel: Image browser */
  .panel-left { width: 220px; background: #16213e; border-right: 1px solid #0f3460; display: flex; flex-direction: column; overflow: hidden; }
  .panel-left .panel-header { padding: 10px 12px; border-bottom: 1px solid #333; display: flex; align-items: center; justify-content: space-between; }
  .panel-left .panel-header h3 { font-size: 13px; color: #e94560; }
  .panel-left .panel-header .count { font-size: 11px; color: #888; }
  .image-list { flex: 1; overflow-y: auto; padding: 8px; }
  .image-card { background: #1a1a2e; border: 2px solid #333; border-radius: 6px; padding: 6px; margin-bottom: 8px; cursor: pointer; transition: border-color 0.2s; }
  .image-card:hover { border-color: #0f3460; }
  .image-card.active { border-color: #e94560; box-shadow: 0 0 8px rgba(233,69,96,0.3); }
  .image-card img { width: 100%; border-radius: 4px; display: block; }
  .image-card .card-info { padding: 4px 2px 0; }
  .image-card .card-name { font-size: 11px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .image-card .card-dims { font-size: 10px; color: #888; }
  .image-card .card-status { font-size: 10px; color: #4caf50; }
  .image-card .card-crops { font-size: 10px; color: #e94560; margin-top: 2px; }

  /* Center panel: Canvas + crop area */
  .panel-center { flex: 1; position: relative; overflow: auto; background: #111; display: flex; align-items: center; justify-content: center; }
  .panel-center canvas { cursor: crosshair; }
  .empty-state { text-align: center; color: #555; }
  .empty-state h2 { font-size: 18px; margin-bottom: 8px; }
  .empty-state p { font-size: 13px; }

  /* Right panel: Crops sidebar */
  .panel-right { width: 300px; background: #16213e; border-left: 1px solid #0f3460; display: flex; flex-direction: column; overflow: hidden; }
  .panel-right .panel-header { padding: 10px 12px; border-bottom: 1px solid #333; display: flex; align-items: center; justify-content: space-between; }
  .panel-right .panel-header h3 { font-size: 13px; color: #e94560; }

  .crop-controls { padding: 10px 12px; border-bottom: 1px solid #333; }
  .crop-controls h4 { font-size: 12px; color: #aaa; margin-bottom: 6px; }
  .field { display: flex; align-items: center; gap: 6px; margin: 3px 0; }
  .field label { font-size: 11px; color: #aaa; width: 50px; flex-shrink: 0; }
  .field input { width: 65px; padding: 3px 5px; background: #1a1a2e; border: 1px solid #333; color: #e0e0e0; border-radius: 3px; font-size: 11px; text-align: right; }
  .field span { font-size: 11px; color: #666; }
  .ratio-lock { display: flex; align-items: center; gap: 6px; margin-top: 4px; }
  .ratio-lock input[type="checkbox"] { margin: 0; }
  .ratio-lock label { font-size: 11px; color: #aaa; cursor: pointer; }
  .aspect-presets { display: flex; gap: 3px; margin-top: 4px; }
  .aspect-presets button { font-size: 10px; padding: 2px 7px; border: 1px solid #333; background: #1a1a2e; color: #aaa; border-radius: 3px; cursor: pointer; }
  .aspect-presets button:hover { background: #0f3460; color: #e0e0e0; }
  .aspect-presets button.active { background: #e94560; border-color: #e94560; color: #fff; }

  .preview-box { background: #111; border: 1px solid #333; border-radius: 4px; min-height: 140px; display: flex; align-items: center; justify-content: center; overflow: hidden; margin: 8px 12px; }
  .preview-box img { max-width: 100%; max-height: 200px; object-fit: contain; }
  .preview-box .placeholder { color: #555; font-size: 11px; }

  .btn-add-crop { margin: 0 12px 8px; padding: 8px; width: calc(100% - 24px); }

  .crop-list { flex: 1; overflow-y: auto; padding: 8px 12px; }
  .crop-item { background: #1a1a2e; border: 1px solid #333; border-radius: 4px; padding: 6px; margin-bottom: 6px; cursor: pointer; }
  .crop-item:hover { border-color: #e94560; }
  .crop-item.active { border-color: #e94560; background: #1f1f3a; }
  .crop-item .ci-header { display: flex; justify-content: space-between; align-items: center; }
  .crop-item .ci-name { font-size: 12px; font-weight: 600; }
  .crop-item .ci-dims { font-size: 10px; color: #888; }
  .crop-item .ci-source { font-size: 10px; color: #666; margin-top: 2px; }
  .crop-item .ci-thumb { margin-top: 4px; max-height: 70px; border-radius: 2px; }
  .crop-item .ci-actions { margin-top: 4px; display: flex; gap: 4px; }
  .crop-item .ci-actions button { font-size: 10px; padding: 2px 6px; border: 1px solid #333; background: #16213e; color: #aaa; border-radius: 3px; cursor: pointer; }
  .crop-item .ci-actions button:hover { background: #0f3460; color: #e0e0e0; }

  .export-panel { padding: 10px 12px; border-top: 1px solid #333; background: #16213e; }
  .export-panel button { width: 100%; margin-bottom: 4px; padding: 7px; font-size: 12px; }

  /* ─── INFO BAR ─── */
  .info-bar { padding: 4px 20px; background: #16213e; border-top: 1px solid #0f3460; font-size: 11px; color: #888; display: flex; gap: 20px; position: fixed; bottom: 0; left: 0; right: 0; }

  /* Scrollbar styling */
  ::-webkit-scrollbar { width: 6px; }
  ::-webkit-scrollbar-track { background: #1a1a2e; }
  ::-webkit-scrollbar-thumb { background: #333; border-radius: 3px; }
  ::-webkit-scrollbar-thumb:hover { background: #555; }

  /* ─── GENERATION PANEL (slide-out) ─── */
  .gen-panel { position: fixed; top: 0; left: -420px; width: 400px; height: 100vh; background: #16213e; border-right: 2px solid #e94560; z-index: 100; transition: left 0.3s ease; display: flex; flex-direction: column; overflow: hidden; }
  .gen-panel.open { left: 0; }
  .gen-panel .gp-header { padding: 14px 16px; background: #0f3460; display: flex; justify-content: space-between; align-items: center; }
  .gen-panel .gp-header h2 { font-size: 15px; color: #e94560; }
  .gen-panel .gp-close { background: none; border: none; color: #888; font-size: 20px; cursor: pointer; padding: 4px 8px; }
  .gen-panel .gp-close:hover { color: #e94560; }
  .gen-panel .gp-body { flex: 1; overflow-y: auto; padding: 16px; }
  .gen-panel .gp-section { margin-bottom: 14px; }
  .gen-panel .gp-section label { display: block; font-size: 12px; color: #aaa; margin-bottom: 4px; }
  .gen-panel textarea { width: 100%; height: 80px; background: #1a1a2e; border: 1px solid #333; color: #e0e0e0; border-radius: 4px; padding: 8px; font-size: 13px; resize: vertical; font-family: inherit; }
  .gen-panel textarea:focus { border-color: #e94560; outline: none; }
  .gen-panel select { width: 100%; padding: 6px 8px; background: #1a1a2e; border: 1px solid #333; color: #e0e0e0; border-radius: 4px; font-size: 12px; }
  .gen-panel .gp-cost { font-size: 11px; color: #888; margin-top: 4px; }
  .gen-panel .gp-refs { display: flex; gap: 8px; margin-top: 6px; }
  .gen-panel .gp-ref-slot { width: 80px; height: 60px; border: 2px dashed #555; border-radius: 4px; display: flex; align-items: center; justify-content: center; font-size: 10px; color: #888; cursor: pointer; overflow: hidden; position: relative; background: #1a1a2e; transition: border-color 0.2s, background 0.15s; text-align: center; line-height: 1.3; }
  .gen-panel .gp-ref-slot:hover { border-color: #e94560; }
  .gen-panel .gp-ref-slot img { width: 100%; height: 100%; object-fit: cover; }
  .gen-panel .gp-ref-slot .gp-ref-remove { position: absolute; top: 2px; right: 2px; background: rgba(0,0,0,0.7); color: #fff; border: none; font-size: 10px; cursor: pointer; width: 16px; height: 16px; border-radius: 50%; display: none; }
  .gen-panel .gp-ref-slot:hover .gp-ref-remove { display: block; }

  .gen-btn-generate { width: 100%; padding: 10px; background: #e94560; border: none; color: #fff; border-radius: 4px; font-size: 14px; font-weight: 600; cursor: pointer; }
  .gen-btn-generate:hover { background: #c73550; }
  .gen-btn-generate:disabled { opacity: 0.4; cursor: default; }

  /* ─── CANDIDATE CARDS ─── */
  .gen-candidates { margin-top: 14px; }
  .gen-candidates h4 { font-size: 12px; color: #aaa; margin-bottom: 8px; }
  .gen-cand-grid { display: flex; gap: 8px; flex-wrap: wrap; }
  .gen-cand-card { width: calc(50% - 4px); background: #1a1a2e; border: 2px solid #333; border-radius: 6px; overflow: hidden; position: relative; }
  .gen-cand-card img { width: 100%; aspect-ratio: 4/3; object-fit: cover; display: block; }
  .gen-cand-card .cand-actions { display: flex; gap: 4px; padding: 6px; }
  .gen-cand-card .cand-actions button { flex: 1; padding: 5px; border: 1px solid #333; background: #16213e; color: #e0e0e0; border-radius: 3px; cursor: pointer; font-size: 11px; }
  .gen-cand-card .cand-actions .cand-approve { background: #2e7d32; border-color: #2e7d32; color: #fff; }
  .gen-cand-card .cand-actions .cand-approve:hover { background: #1b5e20; }
  .gen-cand-card .cand-actions .cand-discard { background: #c62828; border-color: #c62828; color: #fff; }
  .gen-cand-card .cand-actions .cand-discard:hover { background: #b71c1c; }
  .gen-cand-card.approved { border-color: #4caf50; }
  .gen-cand-card.discarded { opacity: 0.3; }
  .gen-cand-status { position: absolute; top: 4px; right: 4px; font-size: 10px; padding: 2px 6px; border-radius: 3px; font-weight: 600; }
  .gen-cand-status.approved { background: #4caf50; color: #fff; }
  .gen-cand-status.discarded { background: #c62828; color: #fff; }

  /* ─── LOADING SKELETON ─── */
  .gen-loading { display: flex; gap: 8px; flex-wrap: wrap; }
  .gen-skel { width: calc(50% - 4px); aspect-ratio: 4/3; background: linear-gradient(90deg, #1a1a2e 25%, #222244 50%, #1a1a2e 75%); background-size: 200% 100%; border-radius: 6px; animation: shimmer 1.5s infinite; }
  @keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }

  /* ─── SOURCE BADGES ─── */
  .source-badge { position: absolute; bottom: 4px; left: 4px; font-size: 9px; padding: 1px 5px; border-radius: 2px; font-weight: 600; }
  .source-badge.ai { background: rgba(33,150,243,0.8); color: #fff; }
  .source-badge.import { background: rgba(158,158,158,0.8); color: #fff; }

  /* ─── DROP ZONE ─── */
  .drop-zone { margin: 8px; padding: 16px 8px; border: 2px dashed #333; border-radius: 6px; text-align: center; font-size: 11px; color: #555; transition: all 0.2s; }
  .drop-zone.dragover { border-color: #e94560; color: #e94560; background: rgba(233,69,96,0.05); }

  /* ─── TOAST ─── */
  .toast-container { position: fixed; bottom: 40px; right: 20px; z-index: 200; display: flex; flex-direction: column; gap: 6px; }
  .toast { padding: 10px 16px; border-radius: 4px; font-size: 12px; color: #fff; opacity: 0; transform: translateX(20px); transition: all 0.3s; max-width: 320px; }
  .toast.show { opacity: 1; transform: translateX(0); }
  .toast.success { background: #2e7d32; }
  .toast.error { background: #c62828; }
  .toast.info { background: #0f3460; }

  /* ─── GEN PANEL OVERLAY ─── */
  .gen-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.4); z-index: 99; display: none; }
  .gen-overlay.show { display: block; }
</style>
</head>
<body>

<div class="header">
  <h1>Image Selector + Cropper</h1>
  <span class="subtitle">{{SUBTITLE}}</span>
  <span class="status" id="headerStatus">Ready</span>
</div>

<div class="toolbar">
  <button id="btnGenerate" class="primary" style="display:{{GEN_DISPLAY}};">+ Generate Images</button>
  <button id="btnImportFile" style="background:#0f3460; border-color:#0f3460; color:#e0e0e0;">+ Import File</button>
  <input type="file" id="fileInput" accept="image/*" multiple style="display:none;">
  <div class="sep"></div>
  <label>Zoom:</label>
  <button id="btnZoomOut">&minus;</button>
  <span id="zoomLevel" style="font-size:12px; min-width:40px; text-align:center;">100%</span>
  <button id="btnZoomIn">+</button>
  <button id="btnZoomFit">Fit</button>
  <div class="sep"></div>
  <div class="dimensions-display" id="dimsDisplay">No selection</div>
  <div class="size-banner" id="sizeBanner"></div>
  <div class="sep"></div>
  <button id="btnUndo" disabled>Undo</button>
  <div class="sep"></div>
  <button id="btnSaveAll" class="primary" disabled>Save All Crops</button>
  <span id="sessionCost" style="font-size:11px; color:#888; margin-left:auto; display:{{GEN_DISPLAY}};">Session: $0.00</span>
</div>

<!-- GENERATION PANEL (slides from left) -->
<div class="gen-overlay" id="genOverlay"></div>
<div class="gen-panel" id="genPanel">
  <div class="gp-header">
    <h2>Generate New Images</h2>
    <button class="gp-close" id="genClose">&times;</button>
  </div>
  <div class="gp-body">
    <div class="gp-section">
      <label>Describe the image you need:</label>
      <textarea id="genPrompt" placeholder="e.g., Guide Bird looking directly at the camera, wings slightly raised, warm forest background..."></textarea>
    </div>
    <div class="gp-section">
      <label>Style preset:</label>
      <select id="genStyle">
        <option value="pixar_standard">Pixar 3D — luminous, warm, cinematic lighting, soft materials</option>
        <option value="pixar_closeup">Pixar 3D — close-up, detailed expression, soft focus background</option>
        <option value="pixar_wide">Pixar 3D — wide establishing shot, environment detail, golden hour</option>
      </select>
    </div>
    <div class="gp-section">
      <label>Reference images (click to browse or drag from library, optional):</label>
      <div class="gp-refs">
        <div class="gp-ref-slot" id="refSlot0" onclick="clickRef(0)" ondrop="dropRef(event,0)" ondragover="event.preventDefault(); this.style.borderColor='#e94560';" ondragleave="this.style.borderColor='#333';"><span>Click or<br>drag ref</span></div>
        <div class="gp-ref-slot" id="refSlot1" onclick="clickRef(1)" ondrop="dropRef(event,1)" ondragover="event.preventDefault(); this.style.borderColor='#e94560';" ondragleave="this.style.borderColor='#333';"><span>Click or<br>drag ref</span></div>
      </div>
      <input type="file" id="refFileInput" accept="image/*" style="display:none;">
    </div>
    <div class="gp-section">
      <button class="gen-btn-generate" id="btnDoGenerate">Generate 3 Images (~$0.12)</button>
      <div class="gp-cost">Gemini 2.5 Flash Image · ~$0.039/image · 3 candidates</div>
    </div>
    <div class="gen-candidates" id="genCandidates" style="display:none;">
      <h4>Candidates — approve or discard:</h4>
      <div class="gen-cand-grid" id="candGrid"></div>
      <button id="btnGenDone" class="primary" style="width:100%; margin-top:10px; display:none;">Done — Add Approved to Library</button>
    </div>
  </div>
</div>

<div class="main">
  <!-- LEFT PANEL: Image Browser -->
  <div class="panel-left">
    <div class="panel-header">
      <h3>Masters</h3>
      <span class="count" id="masterCount">0 images</span>
    </div>
    <div class="image-list" id="imageBrowser">
      <!-- Image cards populated by JS -->
    </div>
    <div class="drop-zone" id="dropZone" ondrop="handleFileDrop(event)" ondragover="handleDragOver(event)" ondragleave="handleDragLeave(event)">
      Drop images here
    </div>
  </div>

  <!-- CENTER PANEL: Canvas -->
  <div class="panel-center" id="canvasArea">
    <div class="empty-state" id="emptyState">
      <h2>Select a master image</h2>
      <p>Click an image in the left panel to start cropping</p>
    </div>
    <canvas id="cropCanvas" style="display:none;"></canvas>
  </div>

  <!-- RIGHT PANEL: Crops -->
  <div class="panel-right">
    <div class="panel-header">
      <h3>Crops</h3>
      <span class="count" id="cropCount">0</span>
    </div>

    <div class="crop-controls">
      <h4>Current Selection</h4>
      <div class="field"><label>X:</label><input type="number" id="cropX" value="0"><span>px</span></div>
      <div class="field"><label>Y:</label><input type="number" id="cropY" value="0"><span>px</span></div>
      <div class="field"><label>Width:</label><input type="number" id="cropW" value="0"><span>px</span></div>
      <div class="field"><label>Height:</label><input type="number" id="cropH" value="0"><span>px</span></div>
      <div class="ratio-lock">
        <input type="checkbox" id="lockRatio" checked>
        <label for="lockRatio">Lock aspect ratio</label>
      </div>
      <div class="aspect-presets">
        <button onclick="setPreset(4,3)" class="active">4:3</button>
        <button onclick="setPreset(1,1)">1:1</button>
        <button onclick="setPreset(16,9)">16:9</button>
        <button onclick="setPreset(0,0)">Free</button>
      </div>
    </div>

    <div class="preview-box" id="previewBox">
      <span class="placeholder">Draw a crop region</span>
    </div>

    <button id="btnAddCrop" class="primary btn-add-crop" disabled>+ Add This Crop</button>

    <div class="crop-list" id="cropList">
      <!-- Crop items populated by JS -->
    </div>

    <div class="export-panel">
      <button class="primary" id="btnExportJSON">Export Crop Manifest (JSON)</button>
      <button id="btnCopyJSON">Copy to Clipboard</button>
    </div>
  </div>
</div>

<div class="toast-container" id="toastContainer"></div>
<div class="info-bar">
  <span id="mousePos">Mouse: —</span>
  <span id="selectionInfo">Selection: none</span>
  <span id="imgInfo">Image: —</span>
  <span id="storageInfo">localStorage: —</span>
</div>

<script>
// ═══════════════════════════════════════════════════════════════════════════
// MindfulNest Image Selector + Cropper — Client-Side Logic
// ═══════════════════════════════════════════════════════════════════════════

const STORAGE_KEY = '{{STORAGE_KEY}}';
const MIN_DIMENSION = {{MIN_DIMENSION}};

// ─── STATE ───────────────────────────────────────────────────────────────
const masters = {{MASTERS_JSON}};   // [{id, name, dataUri, thumbUri, width, height, registryId}]
let currentMasterId = null;
let zoom = 1;
let img = null;

// Crops keyed by master ID: { masterId: [{x, y, w, h, name, dataUrl}] }
let allCrops = {};
let activeCropIdx = -1;

// Drawing state
let isDrawing = false, isDragging = false, isResizing = false;
let resizeHandle = null;
let startX = 0, startY = 0;
let cropRect = { x: 0, y: 0, w: 0, h: 0 };
let dragOffset = { x: 0, y: 0 };
let lockedRatio = 4 / 3;

const canvas = document.getElementById('cropCanvas');
const ctx = canvas.getContext('2d');
const canvasArea = document.getElementById('canvasArea');

// ─── LOCALSTORAGE PERSISTENCE ────────────────────────────────────────────
function saveState() {
  try {
    const state = {
      currentMasterId,
      allCrops: {},
      zoom
    };
    // Save crop coordinates only (not dataUrls — too large for localStorage)
    for (const [mid, crops] of Object.entries(allCrops)) {
      state.allCrops[mid] = crops.map(c => ({ x: c.x, y: c.y, w: c.w, h: c.h, name: c.name }));
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    updateStorageInfo();
  } catch (e) {
    console.warn('localStorage save failed:', e);
  }
}

function loadState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return;
    const state = JSON.parse(raw);
    if (state.zoom) zoom = state.zoom;
    if (state.allCrops) {
      // Restore coordinates; regenerate dataUrls when master is loaded
      for (const [mid, crops] of Object.entries(state.allCrops)) {
        allCrops[mid] = crops.map(c => ({ ...c, dataUrl: null }));
      }
    }
    if (state.currentMasterId && masters.find(m => m.id === state.currentMasterId)) {
      selectMaster(state.currentMasterId);
    }
    updateStorageInfo();
  } catch (e) {
    console.warn('localStorage load failed:', e);
  }
}

function updateStorageInfo() {
  const used = new Blob([localStorage.getItem(STORAGE_KEY) || '']).size;
  document.getElementById('storageInfo').textContent = 'localStorage: ' + (used / 1024).toFixed(1) + ' KB';
}

// ─── IMAGE BROWSER (LEFT PANEL) ─────────────────────────────────────────
function renderImageBrowser() {
  const browser = document.getElementById('imageBrowser');
  document.getElementById('masterCount').textContent = masters.length + ' image' + (masters.length !== 1 ? 's' : '');

  if (masters.length === 0) {
    browser.innerHTML = '<div style="padding:20px; text-align:center; color:#555; font-size:12px;">No images loaded.<br>Use the file picker to add images.</div>';
    return;
  }

  let html = '';
  masters.forEach(m => {
    const isActive = m.id === currentMasterId;
    const cropCount = (allCrops[m.id] || []).length;
    html += '<div class="image-card' + (isActive ? ' active' : '') + '" data-master-id="' + m.id + '" onclick="selectMaster(\'' + m.id + '\')">';
    html += '<img src="' + m.thumbUri + '" alt="' + m.name + '">';
    html += '<div class="card-info">';
    html += '<div class="card-name" title="' + m.name + '">' + m.name + '</div>';
    html += '<div class="card-dims">' + m.width + ' × ' + m.height + '</div>';
    if (cropCount > 0) {
      html += '<div class="card-crops">' + cropCount + ' crop' + (cropCount > 1 ? 's' : '') + '</div>';
    }
    html += '</div></div>';
  });
  browser.innerHTML = html;
}

function selectMaster(masterId) {
  const master = masters.find(m => m.id === masterId);
  if (!master) return;

  currentMasterId = masterId;
  activeCropIdx = -1;
  cropRect = { x: 0, y: 0, w: 0, h: 0 };

  // Load the full image
  img = new Image();
  img.onload = () => {
    document.getElementById('emptyState').style.display = 'none';
    canvas.style.display = 'block';
    fitZoom();

    // Regenerate dataUrls for any restored crops
    const crops = allCrops[masterId] || [];
    crops.forEach(c => {
      if (!c.dataUrl) {
        const tc = document.createElement('canvas');
        tc.width = c.w; tc.height = c.h;
        tc.getContext('2d').drawImage(img, c.x, c.y, c.w, c.h, 0, 0, c.w, c.h);
        c.dataUrl = tc.toDataURL('image/png');
      }
    });

    renderImageBrowser();
    renderCropList();
    draw();
    document.getElementById('imgInfo').textContent = 'Image: ' + master.name + ' (' + img.naturalWidth + '×' + img.naturalHeight + ')';
    saveState();
  };
  img.src = master.dataUri;
}

// ─── CANVAS DRAWING ─────────────────────────────────────────────────────
function fitZoom() {
  if (!img) return;
  const aW = canvasArea.clientWidth - 40;
  const aH = canvasArea.clientHeight - 40;
  zoom = Math.min(aW / img.naturalWidth, aH / img.naturalHeight, 1);
  zoom = Math.round(zoom * 100) / 100;
  updateCanvas();
}

function updateCanvas() {
  if (!img) return;
  canvas.width = Math.round(img.naturalWidth * zoom);
  canvas.height = Math.round(img.naturalHeight * zoom);
  document.getElementById('zoomLevel').textContent = Math.round(zoom * 100) + '%';
  draw();
}

function draw() {
  if (!img) return;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

  // Draw saved crops for current master
  const crops = allCrops[currentMasterId] || [];
  crops.forEach((c, i) => {
    ctx.strokeStyle = i === activeCropIdx ? '#e94560' : 'rgba(233,69,96,0.5)';
    ctx.lineWidth = i === activeCropIdx ? 2 : 1;
    ctx.setLineDash(i === activeCropIdx ? [] : [4, 4]);
    ctx.strokeRect(c.x * zoom, c.y * zoom, c.w * zoom, c.h * zoom);
    ctx.setLineDash([]);
    ctx.fillStyle = i === activeCropIdx ? '#e94560' : 'rgba(233,69,96,0.6)';
    ctx.font = Math.max(11, 13 * zoom) + 'px sans-serif';
    ctx.fillText(c.name || 'Crop ' + (i+1), c.x * zoom + 4, c.y * zoom - 4);
  });

  // Draw current selection
  if (cropRect.w !== 0 && cropRect.h !== 0) {
    const rx = Math.min(cropRect.x, cropRect.x + cropRect.w);
    const ry = Math.min(cropRect.y, cropRect.y + cropRect.h);
    const rw = Math.abs(cropRect.w);
    const rh = Math.abs(cropRect.h);

    // Dimming overlay
    ctx.fillStyle = 'rgba(0,0,0,0.45)';
    ctx.fillRect(0, 0, canvas.width, ry * zoom);
    ctx.fillRect(0, ry * zoom, rx * zoom, rh * zoom);
    ctx.fillRect((rx + rw) * zoom, ry * zoom, canvas.width - (rx + rw) * zoom, rh * zoom);
    ctx.fillRect(0, (ry + rh) * zoom, canvas.width, canvas.height - (ry + rh) * zoom);

    // Selection border
    ctx.strokeStyle = '#00ff88';
    ctx.lineWidth = 2;
    ctx.strokeRect(rx * zoom, ry * zoom, rw * zoom, rh * zoom);

    // Corner handles
    const hs = 6;
    ctx.fillStyle = '#00ff88';
    [[rx, ry], [rx + rw, ry], [rx, ry + rh], [rx + rw, ry + rh]].forEach(([hx, hy]) => {
      ctx.fillRect(hx * zoom - hs/2, hy * zoom - hs/2, hs, hs);
    });

    // Dimensions label
    ctx.fillStyle = '#00ff88';
    ctx.font = Math.max(12, 14 * zoom) + 'px monospace';
    ctx.fillText(rw + ' \u00d7 ' + rh, rx * zoom + 4, (ry + rh) * zoom + 16);
  }
}

// ─── SIZE ENFORCEMENT (Layer 1) ─────────────────────────────────────────
function updateSizeEnforcement() {
  const rw = Math.abs(cropRect.w), rh = Math.abs(cropRect.h);
  const dimsEl = document.getElementById('dimsDisplay');
  const bannerEl = document.getElementById('sizeBanner');
  if (rw < 2 || rh < 2) {
    dimsEl.textContent = 'No selection'; dimsEl.className = 'dimensions-display';
    bannerEl.style.display = 'none'; bannerEl.className = 'size-banner'; return;
  }
  dimsEl.textContent = rw + ' × ' + rh + ' px';
  const shortest = Math.min(rw, rh);
  if (shortest < MIN_DIMENSION) {
    dimsEl.className = 'dimensions-display warning';
    bannerEl.className = 'size-banner warning';
    bannerEl.innerHTML = '\u26a0 Too small (' + shortest + 'px < ' + MIN_DIMENSION + 'px min)';
  } else {
    dimsEl.className = 'dimensions-display ready';
    bannerEl.className = 'size-banner ready';
    bannerEl.innerHTML = '\u2705 ' + rw + ' × ' + rh;
  }
}

// ─── MOUSE INTERACTION ──────────────────────────────────────────────────
function getImgCoords(e) {
  const r = canvas.getBoundingClientRect();
  return { x: Math.round((e.clientX - r.left) / zoom), y: Math.round((e.clientY - r.top) / zoom) };
}

function getHandle(mx, my) {
  if (cropRect.w === 0 && cropRect.h === 0) return null;
  const rx = Math.min(cropRect.x, cropRect.x + cropRect.w);
  const ry = Math.min(cropRect.y, cropRect.y + cropRect.h);
  const rw = Math.abs(cropRect.w), rh = Math.abs(cropRect.h);
  const t = 8 / zoom;
  const handles = [
    { n: 'tl', x: rx, y: ry }, { n: 'tr', x: rx + rw, y: ry },
    { n: 'bl', x: rx, y: ry + rh }, { n: 'br', x: rx + rw, y: ry + rh }
  ];
  for (const h of handles) { if (Math.abs(mx - h.x) < t && Math.abs(my - h.y) < t) return h.n; }
  return null;
}

function isInside(mx, my) {
  const rx = Math.min(cropRect.x, cropRect.x + cropRect.w);
  const ry = Math.min(cropRect.y, cropRect.y + cropRect.h);
  return mx >= rx && mx <= rx + Math.abs(cropRect.w) && my >= ry && my <= ry + Math.abs(cropRect.h);
}

canvas.addEventListener('mousedown', (e) => {
  if (!img) return;
  const { x, y } = getImgCoords(e);
  const handle = getHandle(x, y);
  if (handle) { isResizing = true; resizeHandle = handle; startX = x; startY = y; return; }
  if (isInside(x, y)) { isDragging = true; dragOffset.x = x - Math.min(cropRect.x, cropRect.x + cropRect.w); dragOffset.y = y - Math.min(cropRect.y, cropRect.y + cropRect.h); return; }
  isDrawing = true; cropRect.x = x; cropRect.y = y; cropRect.w = 0; cropRect.h = 0;
});

canvas.addEventListener('mousemove', (e) => {
  if (!img) return;
  const { x, y } = getImgCoords(e);
  document.getElementById('mousePos').textContent = 'Mouse: ' + x + ', ' + y;
  const handle = getHandle(x, y);
  if (handle) canvas.style.cursor = (handle === 'tl' || handle === 'br') ? 'nwse-resize' : 'nesw-resize';
  else if (isInside(x, y)) canvas.style.cursor = 'move';
  else canvas.style.cursor = 'crosshair';

  if (isDrawing) {
    let nw = x - cropRect.x, nh = y - cropRect.y;
    if (lockedRatio) nh = Math.round(Math.abs(nw) / lockedRatio) * (Math.sign(nh) || 1);
    cropRect.w = clampW(cropRect.x, nw); cropRect.h = clampH(cropRect.y, nh);
    draw(); updateFields(); updatePreview(); updateSizeEnforcement();
  }
  if (isDragging) {
    const rw = Math.abs(cropRect.w), rh = Math.abs(cropRect.h);
    cropRect.x = Math.max(0, Math.min(x - dragOffset.x, img.naturalWidth - rw));
    cropRect.y = Math.max(0, Math.min(y - dragOffset.y, img.naturalHeight - rh));
    cropRect.w = rw; cropRect.h = rh;
    draw(); updateFields(); updatePreview(); updateSizeEnforcement();
  }
  if (isResizing) {
    const rx = Math.min(cropRect.x, cropRect.x + cropRect.w), ry = Math.min(cropRect.y, cropRect.y + cropRect.h);
    const rw = Math.abs(cropRect.w), rh = Math.abs(cropRect.h);
    let nx = rx, ny = ry, nw = rw, nh = rh;
    if (resizeHandle.includes('l')) { nx = Math.max(0, x); nw = rx + rw - nx; }
    if (resizeHandle.includes('r')) { nw = Math.min(x - rx, img.naturalWidth - rx); }
    if (resizeHandle.includes('t')) { ny = Math.max(0, y); nh = ry + rh - ny; }
    if (resizeHandle.includes('b')) { nh = Math.min(y - ry, img.naturalHeight - ry); }
    if (lockedRatio) {
      if (resizeHandle.includes('l') || resizeHandle.includes('r')) { nh = Math.round(Math.abs(nw) / lockedRatio); if (resizeHandle.includes('t')) ny = ry + rh - nh; }
      else { nw = Math.round(Math.abs(nh) * lockedRatio); if (resizeHandle.includes('l')) nx = rx + rw - nw; }
    }
    if (nw > 0 && nh > 0) { cropRect.x = nx; cropRect.y = ny; cropRect.w = nw; cropRect.h = nh; }
    draw(); updateFields(); updatePreview(); updateSizeEnforcement();
  }
});

document.addEventListener('mouseup', () => {
  if (!isDrawing && !isDragging && !isResizing) return;
  isDrawing = false; isDragging = false; isResizing = false;
  if (cropRect.w < 0) { cropRect.x += cropRect.w; cropRect.w = -cropRect.w; }
  if (cropRect.h < 0) { cropRect.y += cropRect.h; cropRect.h = -cropRect.h; }
  draw(); updateFields(); updatePreview(); updateSizeEnforcement();
  document.getElementById('btnAddCrop').disabled = (cropRect.w < 2 || cropRect.h < 2);
  document.getElementById('selectionInfo').textContent = cropRect.w > 0 ? 'Selection: ' + Math.abs(cropRect.w) + '×' + Math.abs(cropRect.h) : 'Selection: none';
});

function clampW(sx, w) { return w >= 0 ? Math.min(w, img.naturalWidth - sx) : Math.max(w, -sx); }
function clampH(sy, h) { return h >= 0 ? Math.min(h, img.naturalHeight - sy) : Math.max(h, -sy); }

function updateFields() {
  document.getElementById('cropX').value = Math.min(cropRect.x, cropRect.x + cropRect.w);
  document.getElementById('cropY').value = Math.min(cropRect.y, cropRect.y + cropRect.h);
  document.getElementById('cropW').value = Math.abs(cropRect.w);
  document.getElementById('cropH').value = Math.abs(cropRect.h);
}

function updatePreview() {
  const box = document.getElementById('previewBox');
  const rw = Math.abs(cropRect.w), rh = Math.abs(cropRect.h);
  if (rw < 2 || rh < 2 || !img) { box.innerHTML = '<span class="placeholder">Draw a crop region</span>'; return; }
  const rx = Math.min(cropRect.x, cropRect.x + cropRect.w), ry = Math.min(cropRect.y, cropRect.y + cropRect.h);
  const tc = document.createElement('canvas'); tc.width = rw; tc.height = rh;
  tc.getContext('2d').drawImage(img, rx, ry, rw, rh, 0, 0, rw, rh);
  box.innerHTML = '<img src="' + tc.toDataURL('image/png') + '" alt="Preview">';
}

// Field inputs
['cropX','cropY','cropW','cropH'].forEach(id => {
  document.getElementById(id).addEventListener('change', () => {
    cropRect.x = parseInt(document.getElementById('cropX').value) || 0;
    cropRect.y = parseInt(document.getElementById('cropY').value) || 0;
    cropRect.w = parseInt(document.getElementById('cropW').value) || 0;
    cropRect.h = parseInt(document.getElementById('cropH').value) || 0;
    draw(); updatePreview(); updateSizeEnforcement();
    document.getElementById('btnAddCrop').disabled = (cropRect.w < 2 || cropRect.h < 2);
  });
});

// ─── ASPECT RATIO PRESETS ───────────────────────────────────────────────
function setPreset(w, h) {
  document.querySelectorAll('.aspect-presets button').forEach(b => b.classList.remove('active'));
  if (w === 0 && h === 0) {
    lockedRatio = null;
    document.getElementById('lockRatio').checked = false;
    event.target.classList.add('active');
  } else {
    lockedRatio = w / h;
    document.getElementById('lockRatio').checked = true;
    event.target.classList.add('active');
  }
}

document.getElementById('lockRatio').addEventListener('change', (e) => {
  if (e.target.checked && cropRect.w > 0 && cropRect.h > 0) lockedRatio = Math.abs(cropRect.w) / Math.abs(cropRect.h);
  else if (!e.target.checked) lockedRatio = null;
});

// ─── CROP MANAGEMENT ────────────────────────────────────────────────────
document.getElementById('btnAddCrop').addEventListener('click', () => {
  if (!currentMasterId || !img) return;
  const rw = Math.abs(cropRect.w), rh = Math.abs(cropRect.h);
  if (rw < 2 || rh < 2) return;
  const rx = Math.min(cropRect.x, cropRect.x + cropRect.w);
  const ry = Math.min(cropRect.y, cropRect.y + cropRect.h);
  const master = masters.find(m => m.id === currentMasterId);
  const defaultName = (master ? master.name.replace(/\.[^.]+$/, '') : 'crop') + '_' + ((allCrops[currentMasterId] || []).length + 1);
  const name = prompt('Name this crop:', defaultName);
  if (!name) return;
  const tc = document.createElement('canvas'); tc.width = rw; tc.height = rh;
  tc.getContext('2d').drawImage(img, rx, ry, rw, rh, 0, 0, rw, rh);
  if (!allCrops[currentMasterId]) allCrops[currentMasterId] = [];
  allCrops[currentMasterId].push({ x: rx, y: ry, w: rw, h: rh, name, dataUrl: tc.toDataURL('image/png'), masterId: currentMasterId });
  activeCropIdx = allCrops[currentMasterId].length - 1;
  renderCropList(); renderImageBrowser(); draw();
  document.getElementById('btnSaveAll').disabled = false;
  document.getElementById('btnUndo').disabled = false;
  saveState();
});

function renderCropList() {
  const list = document.getElementById('cropList');
  // Show ALL crops across all masters, grouped
  let totalCrops = 0;
  let html = '';

  for (const master of masters) {
    const crops = allCrops[master.id] || [];
    if (crops.length === 0) continue;
    totalCrops += crops.length;
    const isCurrent = master.id === currentMasterId;
    html += '<div style="margin-bottom:8px;"><div style="font-size:10px; color:#888; padding:2px 0; border-bottom:1px solid #333;">' + master.name + '</div>';
    crops.forEach((c, i) => {
      const isActive = isCurrent && i === activeCropIdx;
      html += '<div class="crop-item' + (isActive ? ' active' : '') + '" onclick="jumpToCrop(\'' + master.id + '\',' + i + ')">';
      html += '<div class="ci-header"><span class="ci-name">' + c.name + '</span><span class="ci-dims">' + c.w + '×' + c.h + '</span></div>';
      if (c.dataUrl) html += '<img class="ci-thumb" src="' + c.dataUrl + '" alt="' + c.name + '">';
      html += '<div class="ci-actions">';
      html += '<button onclick="event.stopPropagation(); saveSingle(\'' + master.id + '\',' + i + ')">Save PNG</button>';
      html += '<button onclick="event.stopPropagation(); renameCrop(\'' + master.id + '\',' + i + ')">Rename</button>';
      html += '<button onclick="event.stopPropagation(); deleteCrop(\'' + master.id + '\',' + i + ')">Delete</button>';
      html += '</div></div>';
    });
    html += '</div>';
  }

  if (totalCrops === 0) html = '<div style="padding:10px; text-align:center; color:#555; font-size:11px;">No crops yet.<br>Select a master and draw a crop region.</div>';
  list.innerHTML = html;
  document.getElementById('cropCount').textContent = totalCrops;
}

function jumpToCrop(masterId, cropIdx) {
  if (masterId !== currentMasterId) {
    // Switch master first, then select crop after load
    const prevHandler = () => {
      activeCropIdx = cropIdx;
      const c = allCrops[masterId][cropIdx];
      cropRect = { x: c.x, y: c.y, w: c.w, h: c.h };
      updateFields(); updatePreview(); updateSizeEnforcement(); draw(); renderCropList();
    };
    selectMaster(masterId);
    // Wait for image load
    setTimeout(prevHandler, 100);
  } else {
    activeCropIdx = cropIdx;
    const c = allCrops[masterId][cropIdx];
    cropRect = { x: c.x, y: c.y, w: c.w, h: c.h };
    updateFields(); updatePreview(); updateSizeEnforcement(); draw(); renderCropList();
  }
}

function saveSingle(masterId, idx) {
  const c = allCrops[masterId][idx];
  if (!c || !c.dataUrl) return;
  const a = document.createElement('a');
  a.href = c.dataUrl; a.download = c.name + '.png';
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
  document.getElementById('headerStatus').textContent = '\u2705 Saved: ' + c.name + '.png';
}

function renameCrop(masterId, idx) {
  const c = allCrops[masterId][idx];
  const n = prompt('New name:', c.name);
  if (n) { c.name = n; renderCropList(); draw(); saveState(); }
}

function deleteCrop(masterId, idx) {
  allCrops[masterId].splice(idx, 1);
  if (masterId === currentMasterId) activeCropIdx = Math.min(activeCropIdx, (allCrops[masterId] || []).length - 1);
  renderCropList(); renderImageBrowser(); draw(); saveState();
  // Update buttons
  const total = Object.values(allCrops).reduce((s, a) => s + a.length, 0);
  if (total === 0) { document.getElementById('btnSaveAll').disabled = true; document.getElementById('btnUndo').disabled = true; }
}

// ─── DIRECTUS AUTHENTICATION ──────────────────────────────────────────────
const DIRECTUS_EMAIL = '{{DIRECTUS_EMAIL}}';
const DIRECTUS_PASSWORD = '{{DIRECTUS_PASSWORD}}';
const DIRECTUS_BASE_URL = '{{DIRECTUS_BASE_URL}}';
const MODULE_ID_INT = {{MODULE_ID_INT}};
const EVENT_NUM = {{EVENT_NUMBER}};

let directusToken = null;

async function getDirectusToken() {
  if (directusToken) return directusToken;
  try {
    const resp = await fetch(DIRECTUS_BASE_URL + '/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: DIRECTUS_EMAIL, password: DIRECTUS_PASSWORD })
    });
    if (!resp.ok) {
      console.warn('Directus auth failed:', resp.status);
      return null;
    }
    const data = await resp.json();
    directusToken = data.data && data.data.access_token;
    return directusToken;
  } catch (e) {
    console.warn('Directus auth error:', e);
    return null;
  }
}

async function registerCropInDirectus(cropData) {
  if (!DIRECTUS_EMAIL || !DIRECTUS_PASSWORD || !DIRECTUS_BASE_URL) {
    console.warn('Directus credentials not configured');
    return null;
  }
  const token = await getDirectusToken();
  if (!token) {
    console.warn('Could not obtain Directus token');
    return null;
  }

  try {
    // Register in prod_visual_assets
    const assetResp = await fetch(DIRECTUS_BASE_URL + '/items/prod_visual_assets', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + token
      },
      body: JSON.stringify({
        module_id: MODULE_ID_INT,
        event_number: EVENT_NUM,
        asset_type: 'crop_4x3',
        shot_number: cropData.shotNumber || 0,
        filename: cropData.filename,
        filepath: cropData.filepath || '',
        status: 'approved',
        width: cropData.width,
        height: cropData.height,
        aspect_ratio: '4:3',
        purpose: 'cropped_image',
        notes: 'Auto-registered from Image Command Center'
      })
    });

    if (!assetResp.ok) {
      console.warn('Asset registration failed:', assetResp.status, await assetResp.text());
      return null;
    }

    const assetData = await assetResp.json();
    const assetId = assetData.data && assetData.data.id;

    // Log to prod_activity_log (Two-Write Rule)
    if (assetId) {
      await fetch(DIRECTUS_BASE_URL + '/items/prod_activity_log', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer ' + token
        },
        body: JSON.stringify({
          module_id: MODULE_ID_INT,
          action: 'crop_registered_from_tool',
          details: {
            crop_name: cropData.filename,
            asset_id: assetId,
            tool: 'image_command_center',
            timestamp: new Date().toISOString()
          },
          performed_by: 'image_command_center'
        })
      }).catch(e => console.warn('Activity log write failed:', e));
    }

    return assetId;
  } catch (e) {
    console.warn('Directus registration error:', e);
    return null;
  }
}

// ─── BATCH SAVE ─────────────────────────────────────────────────────────
document.getElementById('btnSaveAll').addEventListener('click', async () => {
  let count = 0;
  let registeredCount = 0;
  for (const [mid, crops] of Object.entries(allCrops)) {
    for (const c of crops) {
      if (!c.dataUrl) continue;
      const a = document.createElement('a');
      a.href = c.dataUrl; a.download = c.name + '.png';
      document.body.appendChild(a); a.click(); document.body.removeChild(a);
      count++;

      // Register in Directus
      const assetId = await registerCropInDirectus({
        filename: c.name + '.png',
        filepath: '',
        width: c.w,
        height: c.h,
        shotNumber: count
      });
      if (assetId) {
        registeredCount++;
        showToast('Registered: ' + c.name, 'success');
      } else {
        showToast('Failed to register: ' + c.name, 'error');
      }

      await new Promise(r => setTimeout(r, 300)); // Small delay between downloads
    }
  }
  document.getElementById('headerStatus').textContent = '\u2705 Saved ' + count + ' crops (' + registeredCount + ' registered in Directus)';
});

// ─── UNDO ───────────────────────────────────────────────────────────────
document.getElementById('btnUndo').addEventListener('click', () => {
  if (!currentMasterId || !allCrops[currentMasterId] || !allCrops[currentMasterId].length) return;
  allCrops[currentMasterId].pop();
  activeCropIdx = allCrops[currentMasterId].length - 1;
  renderCropList(); renderImageBrowser(); draw(); saveState();
  const total = Object.values(allCrops).reduce((s, a) => s + a.length, 0);
  if (total === 0) { document.getElementById('btnSaveAll').disabled = true; document.getElementById('btnUndo').disabled = true; }
});

// ─── ZOOM CONTROLS ──────────────────────────────────────────────────────
document.getElementById('btnZoomIn').onclick = () => { zoom = Math.min(zoom + 0.1, 3); updateCanvas(); };
document.getElementById('btnZoomOut').onclick = () => { zoom = Math.max(zoom - 0.1, 0.1); updateCanvas(); };
document.getElementById('btnZoomFit').onclick = fitZoom;

// ─── FILE INPUT (Add more images) ──────────────────────────────────────
document.getElementById('fileInput').addEventListener('change', (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (ev) => {
    const tmpImg = new Image();
    tmpImg.onload = () => {
      const id = 'local_' + Date.now();
      masters.push({
        id, name: file.name, dataUri: ev.target.result,
        thumbUri: ev.target.result, // Use full image as thumb for local files
        width: tmpImg.naturalWidth, height: tmpImg.naturalHeight,
        registryId: null
      });
      renderImageBrowser();
      selectMaster(id);
    };
    tmpImg.src = ev.target.result;
  };
  reader.readAsDataURL(file);
});

// ─── EXPORT JSON ────────────────────────────────────────────────────────
function buildExportJSON() {
  const decisions = {};
  let totalCrops = 0;
  for (const [mid, crops] of Object.entries(allCrops)) {
    if (crops.length === 0) continue;
    const master = masters.find(m => m.id === mid);
    decisions[mid] = {
      master_name: master ? master.name : mid,
      master_width: master ? master.width : 0,
      master_height: master ? master.height : 0,
      registry_id: master ? master.registryId : null,
      crops: crops.map(c => ({
        name: c.name, x: c.x, y: c.y, w: c.w, h: c.h,
        aspect_ratio: c.w && c.h ? (c.w / c.h).toFixed(4) : null,
        meets_min_dimension: Math.min(c.w, c.h) >= MIN_DIMENSION
      }))
    };
    totalCrops += crops.length;
  }
  return {
    tool: 'image_selector_cropper',
    version: 1,
    exported_at: new Date().toISOString(),
    module_id: '{{MODULE_ID}}',
    event_number: {{EVENT_NUMBER}},
    total_masters: masters.length,
    total_crops: totalCrops,
    min_dimension: MIN_DIMENSION,
    decisions
  };
}

document.getElementById('btnExportJSON').addEventListener('click', () => {
  const data = buildExportJSON();
  const json = JSON.stringify(data, null, 2);
  const blob = new Blob([json], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = 'crop_manifest_{{MODULE_ID}}_e{{EVENT_NUMBER}}.json';
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
  URL.revokeObjectURL(url);
  document.getElementById('headerStatus').textContent = '\u2705 Manifest exported';
});

document.getElementById('btnCopyJSON').addEventListener('click', () => {
  const data = buildExportJSON();
  navigator.clipboard.writeText(JSON.stringify(data, null, 2)).then(() => {
    document.getElementById('headerStatus').textContent = '\u2705 Copied to clipboard';
  });
});

// ─── KEYBOARD SHORTCUTS ─────────────────────────────────────────────────
document.addEventListener('keydown', (e) => {
  if (e.target.closest('input')) return;
  if (e.key === 'Escape') { cropRect = { x: 0, y: 0, w: 0, h: 0 }; draw(); updateFields(); document.getElementById('previewBox').innerHTML = '<span class="placeholder">Draw a crop region</span>'; updateSizeEnforcement(); }
  if (e.key === '+' || e.key === '=') { zoom = Math.min(zoom + 0.1, 3); updateCanvas(); }
  if (e.key === '-') { zoom = Math.max(zoom - 0.1, 0.1); updateCanvas(); }
  if (e.key === 'Enter' && cropRect.w > 2 && cropRect.h > 2) { document.getElementById('btnAddCrop').click(); }
});

// ═══════════════════════════════════════════════════════════════════════════
// GENERATION — Gemini 2.5 Flash Image API
// ═══════════════════════════════════════════════════════════════════════════

const GEMINI_API_KEY = '{{GEMINI_API_KEY}}';
const GENERATION_ENABLED = {{GENERATION_ENABLED}};
let sessionCost = 0;
let genCandidates = [];
let refImages = [null, null];

const STYLE_PRESETS = {
  pixar_standard: 'Pixar 3D animation style, luminous warm cinematic lighting, soft rounded materials, rich saturated colors, high detail',
  pixar_closeup: 'Pixar 3D animation style, close-up shot, detailed expressive face, soft bokeh background, warm rim lighting',
  pixar_wide: 'Pixar 3D animation style, wide establishing shot, detailed environment, golden hour lighting, depth of field'
};

// ─── TOAST HELPER ──────────────────────────────────────────────────────
function showToast(msg, type='info', duration=3000) {
  const container = document.getElementById('toastContainer');
  const t = document.createElement('div');
  t.className = 'toast ' + type;
  t.textContent = msg;
  container.appendChild(t);
  requestAnimationFrame(() => t.classList.add('show'));
  setTimeout(() => { t.classList.remove('show'); setTimeout(() => t.remove(), 300); }, duration);
}

// ─── GENERATION PANEL CONTROLS ─────────────────────────────────────────
function openGenPanel() { document.getElementById('genPanel').classList.add('open'); document.getElementById('genOverlay').classList.add('show'); }
function closeGenPanel() { document.getElementById('genPanel').classList.remove('open'); document.getElementById('genOverlay').classList.remove('show'); }

if (document.getElementById('btnGenerate')) {
  document.getElementById('btnGenerate').addEventListener('click', openGenPanel);
}
document.getElementById('genClose').addEventListener('click', closeGenPanel);
document.getElementById('genOverlay').addEventListener('click', closeGenPanel);

// ─── REFERENCE IMAGE DRAG ──────────────────────────────────────────────
// Make library image cards draggable
function makeCardsDraggable() {
  document.querySelectorAll('.image-card').forEach(card => {
    card.setAttribute('draggable', 'true');
    card.addEventListener('dragstart', (e) => {
      e.dataTransfer.setData('text/plain', card.dataset.masterId);
    });
  });
}

function dropRef(e, slotIdx) {
  e.preventDefault();
  e.currentTarget.style.borderColor = '#333';

  // Check if file was dropped directly onto ref slot
  if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
    loadRefFromFile(e.dataTransfer.files[0], slotIdx);
    return;
  }

  const masterId = e.dataTransfer.getData('text/plain');
  const master = masters.find(m => m.id === masterId);
  if (!master) return;
  refImages[slotIdx] = master;
  const slot = document.getElementById('refSlot' + slotIdx);
  slot.innerHTML = '<img src="' + master.thumbUri + '" alt="ref"><button class="gp-ref-remove" onclick="event.stopPropagation(); clearRef(' + slotIdx + ')">&times;</button>';
}

// Click a ref slot to open file picker — uses per-call listener to avoid race condition
function clickRef(slotIdx) {
  // Don't open picker if image already loaded (user should click X first)
  if (refImages[slotIdx]) return;
  const inp = document.getElementById('refFileInput');
  inp.value = ''; // reset
  // Remove any prior listener, bind fresh one scoped to this slotIdx
  const handler = function(e) {
    inp.removeEventListener('change', handler);
    if (e.target.files && e.target.files.length > 0) {
      loadRefFromFile(e.target.files[0], slotIdx);
      e.target.value = '';
    }
  };
  inp.addEventListener('change', handler);
  inp.click();
}

function loadRefFromFile(file, slotIdx) {
  if (!file.type.startsWith('image/')) { showToast('Please select an image file', 'error'); return; }
  const reader = new FileReader();
  reader.onload = function(ev) {
    const dataUri = ev.target.result;
    // Create a virtual ref object compatible with the generation flow
    refImages[slotIdx] = { id: 'ref_' + Date.now(), name: file.name, dataUri: dataUri, thumbUri: dataUri };
    const slot = document.getElementById('refSlot' + slotIdx);
    slot.innerHTML = '<img src="' + dataUri + '" alt="ref"><button class="gp-ref-remove" onclick="event.stopPropagation(); clearRef(' + slotIdx + ')">&times;</button>';
    showToast('Reference ' + (slotIdx+1) + ' loaded: ' + file.name, 'success');
  };
  reader.readAsDataURL(file);
}

function clearRef(slotIdx) {
  refImages[slotIdx] = null;
  document.getElementById('refSlot' + slotIdx).innerHTML = '<span>Click or<br>drag ref</span>';
}

// ─── GEMINI API CALL ───────────────────────────────────────────────────
async function generateImages() {
  if (!GENERATION_ENABLED || !GEMINI_API_KEY) {
    showToast('Generation not enabled — rebuild with --generation-enabled', 'error');
    return;
  }

  const promptText = document.getElementById('genPrompt').value.trim();
  if (!promptText) { showToast('Please enter a prompt', 'error'); return; }

  const styleKey = document.getElementById('genStyle').value;
  const fullPrompt = promptText + '. ' + STYLE_PRESETS[styleKey];

  // Show loading
  const btnGen = document.getElementById('btnDoGenerate');
  btnGen.disabled = true;
  btnGen.textContent = 'Generating...';
  document.getElementById('genCandidates').style.display = 'block';
  document.getElementById('candGrid').innerHTML = '<div class="gen-loading"><div class="gen-skel"></div><div class="gen-skel"></div><div class="gen-skel"></div></div>';
  document.getElementById('btnGenDone').style.display = 'none';

  genCandidates = [];

  // Build reference parts
  const refParts = [];
  for (const ref of refImages) {
    if (ref && ref.dataUri) {
      // Extract base64 from data URI
      const b64 = ref.dataUri.split(',')[1];
      const mime = ref.dataUri.split(';')[0].split(':')[1];
      refParts.push({ inlineData: { mimeType: mime, data: b64 } });
    }
  }

  // Generate 3 images sequentially (Gemini doesn't batch image gen)
  const results = [];
  for (let i = 0; i < 3; i++) {
    try {
      const parts = [{ text: fullPrompt + ' (variation ' + (i+1) + ' of 3, unique composition)' }];
      parts.push(...refParts);

      const resp = await fetch(
        'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent?key=' + GEMINI_API_KEY,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            contents: [{ parts }],
            generationConfig: {
              responseModalities: ['TEXT', 'IMAGE']
            }
          })
        }
      );

      if (!resp.ok) {
        const errText = await resp.text();
        console.error('Gemini API error:', resp.status, errText);
        results.push({ error: 'API error: ' + resp.status });
        continue;
      }

      const data = await resp.json();
      // Find image part in response
      const candidate = data.candidates && data.candidates[0];
      if (!candidate) { results.push({ error: 'No candidate returned' }); continue; }

      const imgPart = candidate.content.parts.find(p => p.inlineData);
      if (imgPart) {
        const dataUri = 'data:' + imgPart.inlineData.mimeType + ';base64,' + imgPart.inlineData.data;
        results.push({ dataUri, prompt: fullPrompt, cost: 0.039 });
        sessionCost += 0.039;
      } else {
        results.push({ error: 'No image in response' });
      }
    } catch (err) {
      console.error('Generation error:', err);
      results.push({ error: err.message });
    }
  }

  // Update cost display
  document.getElementById('sessionCost').textContent = 'Session: $' + sessionCost.toFixed(2);

  // Render candidates
  genCandidates = results;
  renderCandidates();

  btnGen.disabled = false;
  btnGen.textContent = 'Generate 3 More (~$0.12)';
}

function renderCandidates() {
  const grid = document.getElementById('candGrid');
  let html = '';
  genCandidates.forEach((c, i) => {
    if (c.error) {
      html += '<div class="gen-cand-card" style="padding:12px; text-align:center; color:#c62828; font-size:11px;">' + c.error + '</div>';
      return;
    }
    const statusClass = c.status === 'approved' ? ' approved' : c.status === 'discarded' ? ' discarded' : '';
    html += '<div class="gen-cand-card' + statusClass + '" id="cand_' + i + '">';
    html += '<img src="' + c.dataUri + '" alt="Candidate ' + (i+1) + '">';
    if (c.status) {
      html += '<div class="gen-cand-status ' + c.status + '">' + c.status + '</div>';
    }
    if (!c.status) {
      html += '<div class="cand-actions">';
      html += '<button class="cand-approve" onclick="approveCandidate(' + i + ')">Approve</button>';
      html += '<button class="cand-discard" onclick="discardCandidate(' + i + ')">Discard</button>';
      html += '</div>';
    }
    html += '</div>';
  });
  grid.innerHTML = html;

  // Show Done button if any approved
  const anyApproved = genCandidates.some(c => c.status === 'approved');
  document.getElementById('btnGenDone').style.display = anyApproved ? 'block' : 'none';
}

function approveCandidate(idx) {
  genCandidates[idx].status = 'approved';
  renderCandidates();
  showToast('Image approved — click Done to add to library', 'success');
}

function discardCandidate(idx) {
  genCandidates[idx].status = 'discarded';
  renderCandidates();
}

// ─── ADD APPROVED TO LIBRARY ───────────────────────────────────────────
document.getElementById('btnGenDone').addEventListener('click', () => {
  const approved = genCandidates.filter(c => c.status === 'approved');
  if (approved.length === 0) return;

  let firstNewId = null;
  approved.forEach((c, i) => {
    const id = 'gen_' + Date.now() + '_' + i;
    if (!firstNewId) firstNewId = id;

    // Get dimensions from the image
    const tmpImg = new Image();
    tmpImg.onload = () => {
      masters.push({
        id, name: 'generated_' + new Date().toISOString().slice(0,19).replace(/[:-]/g,'') + '_' + (i+1) + '.png',
        dataUri: c.dataUri, thumbUri: c.dataUri,
        width: tmpImg.naturalWidth, height: tmpImg.naturalHeight,
        registryId: null, source: 'ai', prompt: c.prompt
      });
      renderImageBrowser();
      makeCardsDraggable();
      if (i === 0) selectMaster(id);
    };
    tmpImg.src = c.dataUri;
  });

  showToast(approved.length + ' image(s) added to library', 'success');
  closeGenPanel();
  genCandidates = [];
});

document.getElementById('btnDoGenerate').addEventListener('click', generateImages);

// ═══════════════════════════════════════════════════════════════════════════
// FILE IMPORT — Drag & Drop + File Picker
// ═══════════════════════════════════════════════════════════════════════════

document.getElementById('btnImportFile').addEventListener('click', () => {
  document.getElementById('fileInput').click();
});

document.getElementById('fileInput').addEventListener('change', (e) => {
  const files = Array.from(e.target.files);
  if (!files.length) return;
  files.forEach(file => importFile(file));
  e.target.value = ''; // Reset for re-use
});

function importFile(file) {
  if (!file.type.startsWith('image/')) { showToast('Not an image: ' + file.name, 'error'); return; }
  const reader = new FileReader();
  reader.onload = (ev) => {
    const tmpImg = new Image();
    tmpImg.onload = () => {
      const id = 'import_' + Date.now() + '_' + Math.random().toString(36).slice(2,6);
      masters.push({
        id, name: file.name, dataUri: ev.target.result,
        thumbUri: ev.target.result,
        width: tmpImg.naturalWidth, height: tmpImg.naturalHeight,
        registryId: null, source: 'import'
      });
      renderImageBrowser();
      makeCardsDraggable();
      selectMaster(id);
      showToast('Imported: ' + file.name, 'success');
    };
    tmpImg.src = ev.target.result;
  };
  reader.readAsDataURL(file);
}

// ─── DROP ZONE HANDLERS ────────────────────────────────────────────────
function handleDragOver(e) { e.preventDefault(); e.currentTarget.classList.add('dragover'); }
function handleDragLeave(e) { e.currentTarget.classList.remove('dragover'); }
function handleFileDrop(e) {
  e.preventDefault();
  e.currentTarget.classList.remove('dragover');
  const files = Array.from(e.dataTransfer.files);
  files.forEach(file => importFile(file));
}

// ═══════════════════════════════════════════════════════════════════════════
// SOURCE TRACKING — Badges on library cards
// ═══════════════════════════════════════════════════════════════════════════

const _origRenderImageBrowser = renderImageBrowser;
renderImageBrowser = function() {
  _origRenderImageBrowser();
  // Add source badges and draggable
  document.querySelectorAll('.image-card').forEach(card => {
    const masterId = card.dataset.masterId;
    const master = masters.find(m => m.id === masterId);
    if (master && master.source === 'ai') {
      const badge = document.createElement('span');
      badge.className = 'source-badge ai'; badge.textContent = 'AI';
      card.style.position = 'relative';
      card.appendChild(badge);
    } else if (master && master.source === 'import') {
      const badge = document.createElement('span');
      badge.className = 'source-badge import'; badge.textContent = 'Import';
      card.style.position = 'relative';
      card.appendChild(badge);
    }
    // Make all cards draggable (for reference image slots)
    card.setAttribute('draggable', 'true');
    card.addEventListener('dragstart', (e) => {
      e.dataTransfer.setData('text/plain', masterId);
    });
  });
};

// ═══════════════════════════════════════════════════════════════════════════
// SAVE GENERATED IMAGES TO DISK
// ═══════════════════════════════════════════════════════════════════════════

function saveImageToDisk(masterId) {
  const master = masters.find(m => m.id === masterId);
  if (!master || !master.dataUri) return;
  const a = document.createElement('a');
  a.href = master.dataUri;
  a.download = master.name;
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
  showToast('Saved: ' + master.name, 'success');
}

// ─── PASTE IMAGE INTO REF SLOTS ───────────────────────────────────────
document.addEventListener('paste', function(e) {
  const items = e.clipboardData && e.clipboardData.items;
  if (!items) return;
  for (let i = 0; i < items.length; i++) {
    if (items[i].type.startsWith('image/')) {
      e.preventDefault();
      const file = items[i].getAsFile();
      // Find first empty ref slot, or slot 0
      let slot = refImages[0] ? (refImages[1] ? -1 : 1) : 0;
      if (slot === -1) { showToast('Both ref slots full — clear one first', 'error'); return; }
      loadRefFromFile(file, slot);
      return;
    }
  }
});

// ─── BEFOREUNLOAD WARNING ──────────────────────────────────────────────
window.addEventListener('beforeunload', (e) => {
  const unsaved = masters.filter(m => (m.source === 'ai' || m.source === 'import') && !m.registryId);
  if (unsaved.length > 0) {
    e.preventDefault();
    e.returnValue = 'You have ' + unsaved.length + ' unsaved generated/imported image(s). Are you sure you want to leave?';
  }
});

// ─── INIT ───────────────────────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', () => {
  renderImageBrowser();
  renderCropList();
  loadState();
  makeCardsDraggable();

  // If no saved state but masters exist, select first
  if (!currentMasterId && masters.length > 0) {
    selectMaster(masters[0].id);
  }

  // Hide generation button if not enabled
  if (!GENERATION_ENABLED) {
    const genBtn = document.getElementById('btnGenerate');
    if (genBtn) genBtn.style.display = 'none';
  }
});
</script>
</body>
</html>"""


# ─── BUILD FUNCTION ─────────────────────────────────────────────────────

def build_image_selector_cropper(
    image_paths=None,
    output_path="image_selector_cropper.html",
    title=None,
    subtitle=None,
    module_id=None,
    event_number=None,
    min_dimension=600,
    use_registry=False,
    generation_enabled=False
):
    """
    Build the unified Image Selector + Cropper HTML tool.

    Args:
        image_paths: List of image file paths to embed
        output_path: Where to write the HTML file
        title: Optional title suffix
        subtitle: Optional subtitle text
        module_id: M-number string (e.g., "M1") or int
        event_number: Event number (int)
        min_dimension: Minimum shortest side for production crops (default 600)
        use_registry: If True, query Directus for images (requires module_id)
    """
    masters_data = []
    source_image_names = []

    # Resolve module_id to int for Directus
    module_int = None
    module_str = str(module_id) if module_id else None
    if module_id is not None:
        if isinstance(module_id, str) and module_id.upper().startswith('M'):
            module_int = int(module_id[1:])
            module_str = module_id.upper()
        else:
            module_int = int(module_id)
            module_str = f"M{module_int}"

    # Registry mode: query Directus for available images
    token = None
    base_url = None
    registry_images = []

    if use_registry:
        if requests is None:
            print("ERROR: requests library required for --registry mode", file=sys.stderr)
            sys.exit(1)
        try:
            creds = read_directus_credentials()
            token, base_url = directus_auth(creds)
            registry_images = query_registry_images(token, base_url, module_int, event_number)
            print(f"✓ Registry: Found {len(registry_images)} assets for {module_str} Event {event_number}")

            # Filter to image assets (masters and crops) that exist on disk
            project_dir = Path(__file__).parent.parent.parent  # Production/tools/ → project root
            # Also try the immediate parent of Production/
            prod_parent = Path(__file__).parent.parent.parent
            for asset in registry_images:
                asset_type = asset.get('asset_type', '')
                # Skip non-image assets (audio, configs, tools)
                if asset_type in ('tts_audio', 'production_tool', 'config'):
                    continue
                filepath = asset.get('filepath', '')
                if not filepath:
                    continue
                # Try to resolve the path relative to project root
                candidates = [
                    Path(filepath),
                    project_dir / filepath,
                    prod_parent / filepath,
                    Path(__file__).parent.parent / filepath,
                ]
                found_path = None
                for c in candidates:
                    if c.exists():
                        found_path = c
                        break
                if found_path:
                    if image_paths is None:
                        image_paths = []
                    image_paths.append(str(found_path))
                    # Track registry ID for this image
                    source_image_names.append(asset.get('filename', found_path.name))
                else:
                    print(f"  ⚠ Registry asset {asset.get('filename')} not found on disk ({filepath})")

        except Exception as e:
            print(f"WARNING: Registry query failed: {e}", file=sys.stderr)
            if not image_paths:
                print("ERROR: No images available. Provide --images or fix registry.", file=sys.stderr)
                sys.exit(1)

    if not image_paths:
        print("ERROR: No images provided. Use --images or --registry.", file=sys.stderr)
        sys.exit(1)

    # Encode all images
    print(f"Encoding {len(image_paths)} images...")
    for i, path in enumerate(image_paths):
        path = Path(path).resolve()
        name = path.name
        print(f"  [{i+1}/{len(image_paths)}] {name}...", end=" ")

        try:
            data_uri, w, h = encode_image(str(path), as_jpeg=True)
            thumb_uri = encode_image_thumbnail(str(path))
            master_id = f"master_{i}"

            # Check if this image has a registry ID
            registry_id = None
            for asset in registry_images:
                if asset.get('filename') == name:
                    registry_id = asset.get('id')
                    break

            masters_data.append({
                'id': master_id,
                'name': name,
                'dataUri': data_uri,
                'thumbUri': thumb_uri,
                'width': w,
                'height': h,
                'registryId': registry_id
            })

            size_kb = len(data_uri) * 3 / 4 / 1024  # Approximate decoded size
            print(f"{w}×{h}, ~{size_kb:.0f} KB")

            if not source_image_names or i >= len(source_image_names):
                source_image_names.append(name)

        except Exception as e:
            print(f"FAILED: {e}")
            continue

    if not masters_data:
        print("ERROR: No images could be encoded.", file=sys.stderr)
        sys.exit(1)

    # Build subtitle
    if not subtitle:
        subtitle = f"{module_str or 'Module'} Event {event_number or '?'} — {len(masters_data)} master image{'s' if len(masters_data) != 1 else ''}"

    # Storage key
    slug = (module_str or 'unknown').lower() + '_e' + str(event_number or 0)
    storage_key = f"mindfulnest_image_selector_cropper_{slug}"

    # Metadata
    metadata = {
        'tool_name': 'image_selector_cropper',
        'version': 1,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'module_id': module_str,
        'event_number': event_number,
        'image_count': len(masters_data),
        'min_dimension': min_dimension,
        'feature_flags': {
            'image_browser': True,
            'crop_canvas': True,
            'localStorage_persistence': True,
            'export_json': True,
            'size_enforcement': True,
            'dark_theme': True,
            '4x3_default_lock': True,
            'batch_save': True,
            'file_input_add': True,
            'generation_enabled': bool(generation_enabled),
            'import_drag_drop': True,
            'source_tracking': True,
            'toast_notifications': True
        }
    }

    # Read Gemini API key if generation enabled
    gemini_key = ''
    if generation_enabled is True:
        gemini_key = read_gemini_api_key() or ''
        if not gemini_key:
            print("WARNING: --generation-enabled but no Gemini API key found in API_KEYS_MASTER.md", file=sys.stderr)
        else:
            print(f"✓ Gemini API key loaded for in-browser generation")

    # Read Directus credentials for crop registration
    directus_email = ''
    directus_password = ''
    directus_base_url = ''
    try:
        creds = read_directus_credentials()
        directus_email = creds['email']
        directus_password = creds['password']
        directus_base_url = creds['url']
        print(f"✓ Directus credentials loaded for crop registration")
    except Exception as e:
        print(f"WARNING: Could not load Directus credentials: {e}", file=sys.stderr)

    # Fill template
    html = TOOL_HTML
    html = html.replace('{{TITLE_SUFFIX}}', f' — {title}' if title else '')
    html = html.replace('{{SUBTITLE}}', subtitle)
    html = html.replace('{{STORAGE_KEY}}', storage_key)
    html = html.replace('{{MIN_DIMENSION}}', str(min_dimension))
    html = html.replace('{{MASTERS_JSON}}', json.dumps(masters_data))
    html = html.replace('{{MODULE_ID}}', module_str or '')
    html = html.replace('{{EVENT_NUMBER}}', str(event_number or 0))
    html = html.replace('{{MODULE_ID_INT}}', str(module_int or 0))
    html = html.replace('{{METADATA_JSON}}', json.dumps(metadata))
    html = html.replace('{{GEMINI_API_KEY}}', gemini_key)
    html = html.replace('{{GENERATION_ENABLED}}', 'true' if generation_enabled and gemini_key else 'false')
    html = html.replace('{{GEN_DISPLAY}}', 'inline-block' if generation_enabled and gemini_key else 'none')
    # SECURITY (CodeQL py/clear-text-storage-sensitive-data #96):
    # Below, the user's Directus password is substituted into the generated
    # HTML so the in-browser tool can authenticate directly. This is by
    # design for the LOCAL dev workflow (cropper is a single-user authoring
    # tool, not a shared deploy artifact). Defense layer: .gitignore blocks
    # the canonical output filenames (image_selector_cropper*.html) so
    # `git add` refuses them — accidental commit cannot leak the password.
    # If you change the output filename, ALSO update .gitignore.
    html = html.replace('{{DIRECTUS_EMAIL}}', directus_email)
    html = html.replace('{{DIRECTUS_PASSWORD}}', directus_password)
    html = html.replace('{{DIRECTUS_BASE_URL}}', directus_base_url)

    # Write output
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        f.write(html)

    file_size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"\n✓ Built: {output_path}")
    print(f"  Images: {len(masters_data)}")
    print(f"  File size: {file_size_mb:.1f} MB")

    if file_size_mb > 50:
        print(f"  ⚠ WARNING: File is large ({file_size_mb:.1f} MB). Browser may struggle.")

    # Auto-register in Directus (Two-Write Rule)
    if token and base_url and module_int is not None:
        try:
            register_in_directus(token, base_url, str(output_path), module_int,
                                 event_number, len(masters_data), source_image_names)
        except Exception as e:
            print(f"WARNING: Directus registration failed: {e}", file=sys.stderr)

    return str(output_path)


# ─── CLI ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='MindfulNest Image Selector + Cropper Builder',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Registry mode (recommended)
  python3 build_image_selector_cropper.py --registry --module M1 --event 1 --output tool.html

  # Local images mode
  python3 build_image_selector_cropper.py --images img1.png img2.png --module M1 --event 1 --output tool.html

  # Smoke test
  python3 build_image_selector_cropper.py --smoke-test

  # Audit
  python3 build_image_selector_cropper.py --audit tool.html

  # Regression check
  python3 build_image_selector_cropper.py --audit-previous new.html old.html
        """
    )

    # Mode flags
    parser.add_argument('--smoke-test', action='store_true', help='Verify Directus connectivity')
    parser.add_argument('--audit', metavar='HTML', help='Extract feature manifest from built HTML')
    parser.add_argument('--audit-previous', nargs=2, metavar=('NEW', 'OLD'),
                        help='Regression check between two built HTMLs')

    # Build flags
    parser.add_argument('--registry', action='store_true', help='Query Directus registry for images')
    parser.add_argument('--images', nargs='+', help='Image file paths to embed')
    parser.add_argument('--output', '-o', default='image_selector_cropper.html', help='Output HTML path')
    parser.add_argument('--title', help='Optional title suffix')
    parser.add_argument('--subtitle', help='Optional subtitle text')
    parser.add_argument('--module', '--module-id', dest='module_id', help='Module ID (e.g., M1)')
    parser.add_argument('--event', '--event-number', dest='event_number', type=int, help='Event number')
    parser.add_argument('--min-dimension', type=int, default=600,
                        help='Minimum shortest side for crops (default: 600)')
    parser.add_argument('--generation-enabled', action='store_true',
                        help='Enable in-browser AI image generation via Gemini API')

    args = parser.parse_args()

    # Mode dispatch
    if args.smoke_test:
        success = smoke_test()
        sys.exit(0 if success else 1)

    if args.audit:
        audit(args.audit)
        sys.exit(0)

    if args.audit_previous:
        success = audit_previous(args.audit_previous[0], args.audit_previous[1])
        sys.exit(0 if success else 1)

    # Build mode
    if not args.registry and not args.images:
        parser.error("Either --registry or --images is required for build mode")

    build_image_selector_cropper(
        image_paths=args.images,
        output_path=args.output,
        title=args.title,
        subtitle=args.subtitle,
        module_id=args.module_id,
        event_number=args.event_number,
        min_dimension=args.min_dimension,
        use_registry=args.registry,
        generation_enabled=args.generation_enabled
    )


if __name__ == '__main__':
    main()
