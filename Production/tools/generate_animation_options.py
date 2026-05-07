#!/usr/bin/env python3
"""
Generate 3 Animation Options Per Beat — M1E1 Tessa Story Scene
================================================================
For each beat, submits the same source still to Kling v3 (via EvoLink)
3 separate times with the same motion prompt but different seeds.
Each generation produces a distinct 5s animation.

Then injects all videos as base64 into the animation review HTML tool.

For multi-clip beats (audio > 5s), generates 3 options for clip 1 only.
Kim picks the best clip 1, then we generate continuation clips from her pick.

Usage:
  python3 generate_animation_options.py [--beats 3,5,6,11] [--dry-run]
"""

# --- WA-C14 Doppler migration (per LD-208) ---
# credential_store reads from Doppler env vars first, falls back to API_KEYS_MASTER.md.
import os as _os, sys as _sys
from pathlib import Path as _Path
_p = _Path(__file__).resolve()
while _p.parent != _p and _p.name != "Production":
    _p = _p.parent
if _p.name == "Production":
    _sys.path.insert(0, str(_p))
from lib.credential_store import get_secret  # noqa: E402
# --- end WA-C14 boilerplate ---

import os, sys, json, time, math, base64, ssl, threading, subprocess
import urllib.request, urllib.error

# Auto-strip audio from downloaded animation clips (CLAUDE.md Rule 8 defense)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ffmpeg_utils import strip_audio as _strip_clip_audio

# =============================================================================
# CONFIG
# =============================================================================
# Auto-detect session path
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_SCRIPT_DIR))  # up from Production/tools/ to project root
EVENT_DIR = os.path.join(_PROJECT_ROOT, "Production", "Event_1")
OUTPUT_DIR = f"{EVENT_DIR}/story_scene_v3"
TTS_DIR = f"{EVENT_DIR}/story_scene_tts_v2"
REVIEW_HTML = f"{EVENT_DIR}/story_scene_v3/animation_review_M1E1_v1.html"
OUTPUT_HTML = f"{EVENT_DIR}/story_scene_v3/animation_review_M1E1.html"

EVOLINK_KEY = get_secret("EVOLINK_API_KEY")
EVOLINK_BASE = "https://api.evolink.ai"
EVOLINK_GENERATE = f"{EVOLINK_BASE}/v1/videos/generations"
EVOLINK_STATUS_TPL = f"{EVOLINK_BASE}/v1/tasks/{{task_id}}"

# WaveSpeed fallback — Kling v3 (same model, different gateway)
WAVESPEED_KEY = get_secret("WAVESPEED_API_KEY")
WAVESPEED_BASE = "https://api.wavespeed.ai/api/v3"
WAVESPEED_KLING_ENDPOINT = f"{WAVESPEED_BASE}/kwaivgi/kling-v3.0-pro/image-to-video"
WAVESPEED_STATUS_TPL = f"{WAVESPEED_BASE}/predictions/{{pred_id}}/result"

# Anti-lip-sync negative prompt (applied to ALL models)
ANTI_LIPSYNC_NEGATIVE = ("lip sync, speaking, talking, mouth movement, dialogue, speech, "
                         "open mouth, Chinese, audio, voice, singing")

# Which API to try first: "evolink" or "wavespeed"
PREFERRED_API = "wavespeed"  # Changed from evolink — WaveSpeed Kling is more reliable

# Directus config
DIRECTUS_URL = None  # Will be loaded from API_KEYS_MASTER
DIRECTUS_EMAIL = None
DIRECTUS_PASS = None

SSL_CTX = ssl.create_default_context()
OPTIONS_PER_BEAT = 3

# Storyboard sequence
SEQUENCE_FILE = f"{EVENT_DIR}/storyboard_lines_v22.json"

# =============================================================================
# LEGACY — NOT IMPORTED BY production_server.py
# =============================================================================
# MOTION_PROMPTS below is used ONLY by this standalone CLI tool and contains
# prompts that pre-date multiple currently-locked design decisions:
#
#   * CLAUDE.md Rule 8.2 / LD-162 (LIPSYNC_SOURCE_MUST_PRESERVE_MOUTH_MOTION,
#     HIGH severity, 2026-04-17): all 7 prompts use "Locked-off static camera"
#     motion-lock language that breaks downstream ByteDance LipSync; 2 prompts
#     (guidebird_closeup_4x3, guide_bird_looks_at_camera1) additionally stack
#     the Rule 8.1 anti-lipsync tail "Silent subtle idle movement only" with
#     "beak closed, no speech, no lip movement" phrasing literally in the
#     prompt body, violating Rule 8.2's do-not-stack rule.
#   * LD-183 (2026-04-17 lore update): bird character renamed "Guide Bird" ->
#     "Chipper". This dict still names "Guide Bird".
#
# The live pipeline reads SPEAKER_MOTION_PROFILES + build_motion_prompt from
# production_server.py (post-2026-04-19 per LD MOTION_VOCABULARY_PER_CREATURE_V1).
# Running this CLI tool without --allow-legacy-prompts is refused at the entry
# point below (see main()). Retained per HANDOFF_20260419_motion_vocabulary_
# implementation.md Section 7 dead-dict debate: cumulative 20-agent vote
# converged on Option B+ (LEGACY HEADER + RUNTIME GATE). If you're reading
# this before reviving the tool, migrate the prompts to the live vocabulary
# first or accept that --allow-legacy-prompts ships Rule 8.2-violating prompts
# to WaveSpeed.
# =============================================================================
MOTION_PROMPTS = {
    "tessa_initial_full": (
        "SUBJECT: Tessa — baby turtle character standing in a misty forest clearing, "
        "wearing a leather harness, looking downward with sad expression\n"
        "ACTION: Subtle weight shifting, slow sad breathing (slight shell rise/fall), "
        "one slow head lift to look around then back down, gentle leaf falling nearby\n"
        "ENVIRONMENT: Misty forest with towering trees, dappled light, mossy path\n"
        "CAMERA: Locked-off medium-wide shot, eye level\n"
        "STYLE: Pixar 3D animated, atmospheric lighting, melancholic mood\n"
        "CONSTRAINTS: 3-5 seconds of subtle movement, preserve exact character appearance, "
        "no dialogue in video"
    ),
    "ref_establishing": (
        "SUBJECT: Two characters in a forest clearing — small blue bird with knitted scarf "
        "approaching a baby turtle character from a forest path\n"
        "ACTION: Bird hops/walks forward with gentle wing adjustments, cautious approach. "
        "Turtle shifts slightly, looks up toward approaching bird. Subtle forest atmosphere "
        "(floating dust motes, slight branch sway)\n"
        "ENVIRONMENT: Misty forest clearing, warm golden light filtering through canopy\n"
        "CAMERA: Locked-off establishing shot, medium-wide framing showing both characters\n"
        "STYLE: Pixar 3D animated, warm atmospheric lighting\n"
        "CONSTRAINTS: 3-5 seconds, preserve both characters' exact appearances, "
        "no dialogue in video"
    ),
    "tessa_closeup_4x3": (
        "SUBJECT: Tessa close-up — baby turtle character, large brown eyes with visible "
        "emotion, rosy cheeks, small crack on shell edge visible\n"
        "ACTION: Subtle emotional eye movement (slow blinks, small glances down then back up), "
        "gentle head micro-tilts (shy or uncertain feeling), slight mouth quiver "
        "(holding back emotion), minimal chin movement\n"
        "ENVIRONMENT: Soft forest background with blurred greenery and warm light\n"
        "CAMERA: Locked-off static camera at Tessa's eye level, close-up framing on face\n"
        "STYLE: Pixar 3D animated, warm key light on face, gentle emotional mood, "
        "detailed eye rendering with light reflections\n"
        "CONSTRAINTS: 2-3 seconds of subtle movement, turtle anatomy (head retracts slightly "
        "when nervous), preserve exact Tessa appearance (green skin, brown shell, rosy cheeks), "
        "character fully visible, no tears or magical effects, no dialogue in video"
    ),
    "gb_sideview_4x3": (
        "SUBJECT: Guide Bird — small blue bird character, wearing a knitted blue cowl/scarf, "
        "standing at three-quarter angle\n"
        "ACTION: Gentle body sway (shifting weight side to side), subtle wing adjustments "
        "(resting at sides with small tucks), warm head tilts toward camera (engaged, "
        "sympathetic), soft blinking\n"
        "ENVIRONMENT: Forest clearing with soft diffuse lighting, warm golden undertone, "
        "blurred tree trunks in background\n"
        "CAMERA: Locked-off static camera, medium shot showing full body at slight angle\n"
        "STYLE: Pixar 3D animated, warm soft lighting, friendly gentle mood, detailed "
        "feather and scarf rendering\n"
        "CONSTRAINTS: 2-3 seconds of gentle idle movement, bird anatomy (no human gestures), "
        "preserve exact Guide Bird appearance (blue body, blue knitted cowl, warm expression), "
        "character fully visible, no tears or magical effects, no dialogue in video"
    ),
    "tessa_initial_4x3": (
        "SUBJECT: Tessa — baby turtle character, medium shot, wearing leather harness, "
        "slightly brightened expression\n"
        "ACTION: Subtle reaction animation — small head lift, eyes widening slightly, "
        "gentle weight shift forward (showing interest), one slow blink\n"
        "ENVIRONMENT: Forest background, warm lighting\n"
        "CAMERA: Locked-off medium shot at eye level\n"
        "STYLE: Pixar 3D animated, warm key light\n"
        "CONSTRAINTS: 2-3 seconds of subtle movement, preserve exact Tessa appearance, "
        "no dialogue in video"
    ),
    "guidebird_closeup_4x3": (
        "SUBJECT: Guide Bird close-up — small blue bird character, expressive eyes, blue scarf "
        "detail visible\n"
        "ACTION: Warm eye focus, subtle head tilts (engaged listening and gentle encouragement), "
        "soft blinking, gentle feather ruffle\n"
        "ENVIRONMENT: Warm forest background, soft golden light on face\n"
        "CAMERA: Locked-off static camera at face level, close-up framing\n"
        "STYLE: Pixar 3D animated, warm key light on face, bright gentle mood, soft feather "
        "rendering\n"
        "CONSTRAINTS: 2-3 seconds, bird anatomy (head and eye movement only), preserve exact "
        "Guide Bird appearance (blue body, blue scarf, warm expression), character fully visible, "
        "beak closed, no speech, no lip movement, no tears or magical effects, "
        "silent subtle idle movement only"
    ),
    "guide_bird_looks_at_camera1": (
        "SUBJECT: Guide Bird — small blue bird character, looking directly at camera, "
        "wearing blue knitted cowl/scarf, bright expressive eyes, warm engaging expression\n"
        "ACTION: Energetic subtle body bounce (shifting weight forward with excitement), "
        "bright eye sparkle, gentle head nod toward camera (encouraging, 'let's do this!'), "
        "soft feather ruffle, one enthusiastic wing adjustment\n"
        "ENVIRONMENT: Forest background with warm golden-green lighting, soft bokeh\n"
        "CAMERA: Locked-off static camera, close-up at eye level, direct eye contact with viewer\n"
        "STYLE: Pixar 3D animated, warm bright key light, excited encouraging mood, "
        "detailed feather and scarf rendering\n"
        "CONSTRAINTS: 2-3 seconds of energetic idle movement, bird anatomy (no human gestures), "
        "preserve exact Guide Bird appearance (blue body, blue knitted cowl, direct camera gaze), "
        "character fully visible, beak closed, no speech, no lip movement, no beak movement, "
        "no tears or magical effects, no dialogue in video, silent subtle idle movement only"
    ),
}

print_lock = threading.Lock()
def tprint(msg):
    with print_lock:
        print(msg, flush=True)

# =============================================================================
# API HELPERS
# =============================================================================
def api_request(url, data=None, headers=None, method=None, timeout=120):
    if headers is None:
        headers = {}
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers.setdefault("Content-Type", "application/json")
        if method is None:
            method = "POST"
    else:
        body = None
        if method is None:
            method = "GET"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    resp = urllib.request.urlopen(req, context=SSL_CTX, timeout=timeout)
    return json.loads(resp.read().decode("utf-8"))

def load_api_keys():
    """Load Directus credentials from API_KEYS_MASTER."""
    global DIRECTUS_URL, DIRECTUS_EMAIL, DIRECTUS_PASS
    keys_file = f"{EVENT_DIR}/../Production/API_KEYS_MASTER.md"
    if not os.path.exists(keys_file):
        keys_file = f"{EVENT_DIR}/../../Production/API_KEYS_MASTER.md"
    # Try the project root
    for candidate in [
        "/sessions/brave-optimistic-tesla/mnt/Claude Mindfulnest Project Files/Production/API_KEYS_MASTER.md",
    ]:
        if os.path.exists(candidate):
            keys_file = candidate
            break

    if not os.path.exists(keys_file):
        tprint("⚠ API_KEYS_MASTER.md not found, skipping Directus")
        return False

    with open(keys_file) as f:
        content = f.read()

    import re
    url_m = re.search(r'URL[:\s]+`?(https://[^\s`]+)', content)
    email_m = re.search(r'Email[:\s]+`?([^\s`]+@[^\s`]+)', content)
    pass_m = re.search(r'Password[:\s]+`?([^\s`]+)', content)

    if url_m: DIRECTUS_URL = url_m.group(1).rstrip('/')
    if email_m: DIRECTUS_EMAIL = email_m.group(1)
    if pass_m: DIRECTUS_PASS = pass_m.group(1)

    return bool(DIRECTUS_URL and DIRECTUS_EMAIL and DIRECTUS_PASS)

def directus_auth():
    """Authenticate with Directus and return token."""
    try:
        resp = api_request(f"{DIRECTUS_URL}/auth/login", {
            "email": DIRECTUS_EMAIL, "password": DIRECTUS_PASS
        })
        return resp.get("data", {}).get("access_token")
    except Exception as e:
        tprint(f"⚠ Directus auth failed: {e}")
        return None

def resolve_images_from_directus(token):
    """Get image file paths from Directus prod_visual_assets registry."""
    try:
        resp = api_request(
            f"{DIRECTUS_URL}/items/prod_visual_assets?fields=asset_key,file_path&filter[module][_eq]=M1&filter[status][_eq]=approved&limit=50",
            headers={"Authorization": f"Bearer {token}"}
        )
        mapping = {}
        for item in resp.get("data", []):
            mapping[item["asset_key"]] = item["file_path"]
        return mapping
    except Exception as e:
        tprint(f"⚠ Directus image resolve failed: {e}")
        return {}

def resolve_images_fallback():
    """Fallback: resolve images from known paths."""
    stills_dir = f"{EVENT_DIR}/stills"
    cropper_dir = f"{EVENT_DIR}/Cropper"
    temp_dir = f"{EVENT_DIR}/_temp_images"
    crops_dir = f"{EVENT_DIR}/crops"

    # Priority: _temp_images (production 4x3 crops) > crops > stills > Cropper
    known_mappings = {
        "tessa_initial_full": None,
        "ref_establishing": None,
        "tessa_closeup_4x3": None,
        "gb_sideview_4x3": None,
        "tessa_initial_4x3": None,
        "guidebird_closeup_4x3": None,
        "guide_bird_looks_at_camera1": None,
    }

    # Check _temp_images first (these are the production-ready 4x3 crops)
    if os.path.isdir(temp_dir):
        for f in os.listdir(temp_dir):
            fl = f.lower()
            fp = os.path.join(temp_dir, f)
            if "tessa_closeup_4x3" in fl:
                known_mappings["tessa_closeup_4x3"] = fp
            elif "gb_sideview_4x3" in fl:
                known_mappings["gb_sideview_4x3"] = fp
            elif "tessa_initial_4x3" in fl:
                known_mappings["tessa_initial_4x3"] = fp
            elif "guidebird_closeup_4x3" in fl:
                known_mappings["guidebird_closeup_4x3"] = fp
            elif "guide bird looks at camera1" in f.lower() or "guide_bird_looks_at_camera1" in fl:
                known_mappings["guide_bird_looks_at_camera1"] = fp
            elif "medium_twoshot" in fl:
                known_mappings["ref_establishing"] = fp

    # Fill remaining from crops/stills directories
    for search_dir in [crops_dir, stills_dir]:
        if os.path.isdir(search_dir):
            for f in os.listdir(search_dir):
                fl = f.lower()
                fp = os.path.join(search_dir, f)
                if not known_mappings.get("tessa_initial_full") and "tessa" in fl and "closeup" in fl:
                    known_mappings["tessa_initial_full"] = fp
                if not known_mappings.get("ref_establishing") and "ref" in fl and "intro" in fl:
                    known_mappings["ref_establishing"] = fp
                if not known_mappings.get("guidebird_closeup_4x3") and "guidebird" in fl and "closeup" in fl:
                    known_mappings["guidebird_closeup_4x3"] = fp

    # Search Cropper directory for any remaining gaps
    if os.path.isdir(cropper_dir):
        for f in os.listdir(cropper_dir):
            fl = f.lower()
            fp = os.path.join(cropper_dir, f)
            if not known_mappings.get("tessa_closeup_4x3") and "tessa" in fl and "closeup" in fl and "4x3" in fl:
                known_mappings["tessa_closeup_4x3"] = fp
            elif not known_mappings.get("gb_sideview_4x3") and ("guide" in fl or "gb" in fl) and "side" in fl:
                known_mappings["gb_sideview_4x3"] = fp

    return {k: v for k, v in known_mappings.items() if v and os.path.exists(v)}

# =============================================================================
# KLING GENERATION VIA EVOLINK
# =============================================================================
def submit_kling_generation(image_path, motion_prompt, beat_num, option_idx):
    """Submit a single Kling v3 generation via EvoLink."""
    labels = ['A', 'B', 'C']
    label = labels[option_idx]

    # Read image as base64
    with open(image_path, 'rb') as f:
        img_b64 = base64.b64encode(f.read()).decode('utf-8')

    ext = os.path.splitext(image_path)[1].lower()
    mime = 'image/png' if ext == '.png' else 'image/jpeg'
    data_uri = f"data:{mime};base64,{img_b64}"

    payload = {
        "model": "kling",
        "model_version": "3.0",
        "input": {
            "image_start": data_uri,
            "prompt": motion_prompt,
            "duration": 5,
            "aspect_ratio": "4:3"
        }
    }

    tprint(f"  Beat {beat_num:2d} Option {label}: 🚀 Submitting to Kling v3...")

    try:
        resp = api_request(
            EVOLINK_GENERATE,
            data=payload,
            headers={"Authorization": f"Bearer {EVOLINK_KEY}"},
            timeout=30
        )
        task_id = resp.get("id") or resp.get("task_id") or resp.get("data", {}).get("task_id")
        if task_id:
            tprint(f"  Beat {beat_num:2d} Option {label}: ✓ Task submitted: {task_id}")
            return task_id
        else:
            tprint(f"  Beat {beat_num:2d} Option {label}: ❌ No task ID in response: {resp}")
            return None
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        tprint(f"  Beat {beat_num:2d} Option {label}: ❌ HTTP {e.code}: {body[:200]}")
        return None
    except Exception as e:
        tprint(f"  Beat {beat_num:2d} Option {label}: ❌ Error: {e}")
        return None

def poll_kling_task(task_id, beat_num, option_idx, max_wait=300):
    """Poll EvoLink for task completion, return video URL."""
    labels = ['A', 'B', 'C']
    label = labels[option_idx]
    url = EVOLINK_STATUS_TPL.format(task_id=task_id)

    start = time.time()
    while time.time() - start < max_wait:
        try:
            resp = api_request(url, headers={"Authorization": f"Bearer {EVOLINK_KEY}"})
            status = resp.get("status") or resp.get("data", {}).get("status", "")

            if status in ("completed", "succeeded", "success"):
                video_url = (resp.get("output", {}).get("video_url") or
                           resp.get("data", {}).get("output", {}).get("video_url") or
                           resp.get("video_url"))
                if video_url:
                    tprint(f"  Beat {beat_num:2d} Option {label}: ✅ Complete!")
                    return video_url

            elif status in ("failed", "error"):
                err = resp.get("error") or resp.get("data", {}).get("error", "unknown")
                tprint(f"  Beat {beat_num:2d} Option {label}: ❌ Failed: {err}")
                return None

            # Still processing
            elapsed = int(time.time() - start)
            if elapsed % 30 == 0 and elapsed > 0:
                tprint(f"  Beat {beat_num:2d} Option {label}: ⏳ Still generating... ({elapsed}s)")

        except Exception as e:
            tprint(f"  Beat {beat_num:2d} Option {label}: ⚠ Poll error: {e}")

        time.sleep(5)

    tprint(f"  Beat {beat_num:2d} Option {label}: ⏰ Timeout after {max_wait}s")
    return None

def download_video(url, output_path):
    """Download video from URL to local file."""
    try:
        req = urllib.request.Request(url)
        resp = urllib.request.urlopen(req, context=SSL_CTX, timeout=60)
        with open(output_path, 'wb') as f:
            f.write(resp.read())
        # Auto-strip unwanted audio tracks (WaveSpeed sometimes ignores sound:false)
        _strip_clip_audio(output_path, verbose=True)
        return os.path.exists(output_path) and os.path.getsize(output_path) > 1000
    except Exception as e:
        tprint(f"  ⚠ Download failed: {e}")
        return False

def get_duration(path):
    """Get video duration using ffprobe."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", path],
            capture_output=True, text=True
        )
        return float(r.stdout.strip())
    except:
        return 0.0

# =============================================================================
# KLING GENERATION VIA WAVESPEED (FALLBACK)
# =============================================================================
def submit_wavespeed_kling(image_path, motion_prompt, beat_num, option_idx):
    """Submit a Kling v3 generation via WaveSpeed (fallback when EvoLink is down)."""
    labels = ['A', 'B', 'C']
    label = labels[option_idx]

    # Upload image to uguu.se for URL-based input
    import urllib.parse
    with open(image_path, 'rb') as f:
        img_data = f.read()

    ext = os.path.splitext(image_path)[1].lower()
    mime = 'image/png' if ext == '.png' else 'image/jpeg'

    # Use base64 data URI for WaveSpeed
    img_b64 = base64.b64encode(img_data).decode('utf-8')
    data_uri = f"data:{mime};base64,{img_b64}"

    payload = {
        "image": data_uri,
        "prompt": motion_prompt,
        "negative_prompt": ANTI_LIPSYNC_NEGATIVE,
        "sound": False,
        "cfg_scale": 0.5,
        "duration": 5,
        "aspect_ratio": "4:3"
    }

    tprint(f"  Beat {beat_num:2d} Option {label}: 🚀 Submitting to Kling v3 via WaveSpeed...")

    try:
        resp = api_request(
            WAVESPEED_KLING_ENDPOINT,
            data=payload,
            headers={"Authorization": f"Bearer {WAVESPEED_KEY}"},
            timeout=30
        )
        pred_id = resp.get("id") or resp.get("data", {}).get("id")
        if pred_id:
            tprint(f"  Beat {beat_num:2d} Option {label}: ✓ WaveSpeed task: {pred_id}")
            return pred_id
        else:
            tprint(f"  Beat {beat_num:2d} Option {label}: ❌ No prediction ID: {resp}")
            return None
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        tprint(f"  Beat {beat_num:2d} Option {label}: ❌ WaveSpeed HTTP {e.code}: {body[:200]}")
        return None
    except Exception as e:
        tprint(f"  Beat {beat_num:2d} Option {label}: ❌ WaveSpeed error: {e}")
        return None

def poll_wavespeed_task(pred_id, beat_num, option_idx, max_wait=300):
    """Poll WaveSpeed for task completion, return video URL."""
    labels = ['A', 'B', 'C']
    label = labels[option_idx]
    url = WAVESPEED_STATUS_TPL.format(pred_id=pred_id)

    start = time.time()
    while time.time() - start < max_wait:
        try:
            resp = api_request(url, headers={"Authorization": f"Bearer {WAVESPEED_KEY}"})
            status = resp.get("status") or resp.get("data", {}).get("status", "")

            if status in ("completed", "succeeded", "success"):
                outputs = resp.get("data", {}).get("outputs", []) or resp.get("outputs", [])
                video_url = outputs[0] if outputs else resp.get("data", {}).get("output", {}).get("video_url")
                if video_url:
                    tprint(f"  Beat {beat_num:2d} Option {label}: ✅ WaveSpeed complete!")
                    return video_url

            elif status in ("failed", "error"):
                err = resp.get("error") or resp.get("data", {}).get("error", "unknown")
                tprint(f"  Beat {beat_num:2d} Option {label}: ❌ WaveSpeed failed: {err}")
                return None

            elapsed = int(time.time() - start)
            if elapsed % 30 == 0 and elapsed > 0:
                tprint(f"  Beat {beat_num:2d} Option {label}: ⏳ WaveSpeed generating... ({elapsed}s)")

        except Exception as e:
            tprint(f"  Beat {beat_num:2d} Option {label}: ⚠ WaveSpeed poll error: {e}")

        time.sleep(5)

    tprint(f"  Beat {beat_num:2d} Option {label}: ⏰ WaveSpeed timeout after {max_wait}s")
    return None

def submit_generation(image_path, motion_prompt, beat_num, option_idx):
    """Submit generation with automatic fallback: preferred API first, then fallback."""
    if PREFERRED_API == "wavespeed":
        # Try WaveSpeed Kling first
        task_id = submit_wavespeed_kling(image_path, motion_prompt, beat_num, option_idx)
        if task_id:
            return ("wavespeed", task_id)
        # Fallback to EvoLink
        tprint(f"  ⚠ WaveSpeed failed, falling back to EvoLink...")
        task_id = submit_kling_generation(image_path, motion_prompt, beat_num, option_idx)
        if task_id:
            return ("evolink", task_id)
    else:
        # Try EvoLink first
        task_id = submit_kling_generation(image_path, motion_prompt, beat_num, option_idx)
        if task_id:
            return ("evolink", task_id)
        # Fallback to WaveSpeed Kling
        tprint(f"  ⚠ EvoLink failed, falling back to WaveSpeed Kling...")
        task_id = submit_wavespeed_kling(image_path, motion_prompt, beat_num, option_idx)
        if task_id:
            return ("wavespeed", task_id)
    return (None, None)

def poll_generation(api_name, task_id, beat_num, option_idx, max_wait=300):
    """Poll the correct API based on which one submitted the task."""
    if api_name == "wavespeed":
        return poll_wavespeed_task(task_id, beat_num, option_idx, max_wait)
    else:
        return poll_kling_task(task_id, beat_num, option_idx, max_wait)

# =============================================================================
# GENERATE OPTIONS FOR ONE BEAT
# =============================================================================
def generate_beat_options(beat_num, image_path, motion_prompt, output_dir):
    """Generate 3 animation options for a single beat. Returns list of video paths."""
    labels = ['A', 'B', 'C']
    results = [None, None, None]

    # Submit all 3 in parallel with slight stagger
    # task_ids stores (api_name, task_id) tuples for proper polling
    task_entries = [None, None, None]

    def submit(idx):
        time.sleep(idx * 2)  # 2s stagger to get different seeds
        task_entries[idx] = submit_generation(image_path, motion_prompt, beat_num, idx)

    threads = []
    for idx in range(OPTIONS_PER_BEAT):
        t = threading.Thread(target=submit, args=(idx,))
        t.start()
        threads.append(t)
    for t in threads:
        t.join()

    # Poll all in parallel
    def poll_and_download(idx):
        if not task_entries[idx] or not task_entries[idx][1]:
            return
        api_name, task_id = task_entries[idx]
        video_url = poll_generation(api_name, task_id, beat_num, idx)
        if video_url:
            out_path = os.path.join(output_dir, f"beat_{beat_num:02d}_option_{labels[idx]}.mp4")
            if download_video(video_url, out_path):
                dur = get_duration(out_path)
                tprint(f"  Beat {beat_num:2d} Option {labels[idx]}: 💾 Saved via {api_name} ({dur:.1f}s)")
                results[idx] = out_path

    threads = []
    for idx in range(OPTIONS_PER_BEAT):
        t = threading.Thread(target=poll_and_download, args=(idx,))
        t.start()
        threads.append(t)
    for t in threads:
        t.join()

    return results

# =============================================================================
# BUILD REVIEW HTML
# =============================================================================
def build_review_html(all_options):
    """Inject generated video data into the review HTML template."""
    tprint("\n📄 Building review HTML...")

    # Read template
    with open(REVIEW_HTML) as f:
        html = f.read()

    # Build video data object
    video_entries = []
    for beat_num, options in sorted(all_options.items()):
        for idx, path in enumerate(options):
            if path and os.path.exists(path):
                dur = get_duration(path)
                with open(path, 'rb') as f:
                    b64 = base64.b64encode(f.read()).decode('utf-8')
                video_entries.append(
                    f'  "{beat_num}_{idx}": {{ src: "data:video/mp4;base64,{b64}", duration: "{dur:.1f}" }}'
                )

    # Inject into HTML
    injection = "const INJECTED_VIDEOS = {\n" + ",\n".join(video_entries) + "\n};\n"
    html = html.replace(
        "// INJECTED_VIDEOS will be populated by the build script\n"
        "// Format: { \"3_0\": { src: \"data:video/mp4;base64,...\", duration: \"5.0\" }, ... }",
        injection
    )

    # Write output
    with open(OUTPUT_HTML, 'w') as f:
        f.write(html)

    size_mb = os.path.getsize(OUTPUT_HTML) / (1024 * 1024)
    tprint(f"✓ Review HTML written: {OUTPUT_HTML} ({size_mb:.1f} MB)")
    return OUTPUT_HTML

# =============================================================================
# MAIN
# =============================================================================
_LEGACY_PROMPTS_REFUSAL_MSG = (
    "REFUSED: MOTION_PROMPTS in this file contains CLAUDE.md Rule 8.2 "
    "violations (7/7 prompts use 'Locked-off static camera' motion-lock; "
    "2/7 stack the Rule 8.1 anti-lipsync tail in the prompt body) and "
    "LD-183 legacy 'Guide Bird' naming (canonical is 'Chipper' since "
    "2026-04-17). The live pipeline uses production_server.py's "
    "SPEAKER_MOTION_PROFILES + build_motion_prompt(). To run this tool "
    "anyway, pass --allow-legacy-prompts. Motivation + dead-dict debate "
    "outcome: HANDOFF_20260419_motion_vocabulary_implementation.md Section 7."
)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Generate 3 animation options per beat')
    parser.add_argument('--beats', type=str, default='all',
                       help='Comma-separated beat numbers (e.g., 3,5,6,11) or "all"')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be generated without calling API')
    parser.add_argument('--use-existing', action='store_true',
                       help='Use existing animated clips as option A, generate B and C only')
    parser.add_argument('--allow-legacy-prompts', action='store_true',
                       help=('Required: acknowledges MOTION_PROMPTS contains Rule 8.2 '
                             'violations and LD-183 legacy lore (see file header). '
                             'Without this flag the tool refuses to run.'))
    args = parser.parse_args()

    if not args.allow_legacy_prompts:
        print(_LEGACY_PROMPTS_REFUSAL_MSG, file=sys.stderr)
        sys.exit(2)

    print("!" * 70, file=sys.stderr)
    print("WARN: running with Rule 8.2-violating legacy MOTION_PROMPTS; "
          "see file header for details.", file=sys.stderr)
    print("!" * 70, file=sys.stderr)

    print("=" * 70)
    print("ANIMATION OPTIONS GENERATOR — M1E1 Tessa Story Scene")
    print(f"3 options per beat via Kling v3 (EvoLink API)")
    print(f"Cost: ~$0.375 per option (5s clip)")
    print("=" * 70)

    # Load sequence
    with open(SEQUENCE_FILE) as f:
        beats = json.load(f)
    print(f"\n✓ {len(beats)} beats loaded")

    # Determine which beats to generate
    if args.beats == 'all':
        beat_nums = list(range(1, len(beats) + 1))
    else:
        beat_nums = [int(x.strip()) for x in args.beats.split(',')]

    print(f"Beats to generate: {beat_nums}")

    # Resolve images
    tprint("\nResolving images...")
    image_mapping = {}

    if load_api_keys():
        token = directus_auth()
        if token:
            image_mapping = resolve_images_from_directus(token)
            tprint(f"✓ {len(image_mapping)} images from Directus registry")

    if not image_mapping:
        image_mapping = resolve_images_fallback()
        tprint(f"✓ {len(image_mapping)} images from fallback paths")

    if not image_mapping:
        tprint("❌ No images resolved! Cannot generate animations.")
        tprint("Available stills:")
        for d in [f"{EVENT_DIR}/stills", f"{EVENT_DIR}/Cropper"]:
            if os.path.isdir(d):
                for f in os.listdir(d):
                    tprint(f"  {d}/{f}")
        return

    tprint("\nImage mapping:")
    for k, v in image_mapping.items():
        tprint(f"  {k} → {os.path.basename(v)}")

    # Cost estimate
    total_options = len(beat_nums) * OPTIONS_PER_BEAT
    est_cost = total_options * 0.375
    est_credits = total_options * 27
    print(f"\n💰 Estimated cost: {total_options} options × $0.375 = ${est_cost:.2f}")
    print(f"   Credits needed: {est_credits} (27 per 5s clip)")

    if args.dry_run:
        print("\n[DRY RUN] Would generate the following:")
        for bn in beat_nums:
            beat = beats[bn - 1]
            img_key = beat["image"]
            has_image = img_key in image_mapping
            print(f"  Beat {bn:2d}: image={img_key} ({'✓' if has_image else '❌'}) → 3 options")
        return

    # Generate options
    all_options = {}
    options_dir = os.path.join(OUTPUT_DIR, "animation_options")
    os.makedirs(options_dir, exist_ok=True)

    for bn in beat_nums:
        beat = beats[bn - 1]
        img_key = beat["image"]

        if img_key not in image_mapping:
            tprint(f"\n⚠ Beat {bn}: Image '{img_key}' not in registry, skipping")
            continue

        img_path = image_mapping[img_key]
        motion_prompt = MOTION_PROMPTS.get(img_key, MOTION_PROMPTS.get("tessa_closeup_4x3"))

        tprint(f"\n{'='*50}")
        tprint(f"Beat {bn}: Generating 3 options")
        tprint(f"  Image: {os.path.basename(img_path)}")
        tprint(f"  Audio: {beat.get('audio_key', 'none')}")
        tprint(f"{'='*50}")

        beat_options_dir = os.path.join(options_dir, f"beat_{bn:02d}")
        os.makedirs(beat_options_dir, exist_ok=True)

        if args.use_existing:
            # Use existing v3/v5 animated clip as option A, generate B and C only
            existing = os.path.join(OUTPUT_DIR, f"beat_{bn:02d}", f"beat_{bn:02d}_animated.mp4")
            if os.path.exists(existing):
                import shutil
                opt_a_path = os.path.join(beat_options_dir, f"beat_{bn:02d}_option_A.mp4")
                shutil.copy2(existing, opt_a_path)
                tprint(f"  Beat {bn:2d} Option A: 📎 Using existing clip ({get_duration(opt_a_path):.1f}s)")

                # Generate Options B and C only
                labels = ['A', 'B', 'C']
                task_entries_bc = [None, None]  # B and C

                def submit_bc(idx):
                    time.sleep(idx * 2)
                    task_entries_bc[idx] = submit_generation(img_path, motion_prompt, bn, idx + 1)

                threads = []
                for idx in range(2):
                    t = threading.Thread(target=submit_bc, args=(idx,))
                    t.start()
                    threads.append(t)
                for t in threads:
                    t.join()

                bc_results = [None, None]
                def poll_bc(idx):
                    if not task_entries_bc[idx] or not task_entries_bc[idx][1]:
                        return
                    api_name, task_id = task_entries_bc[idx]
                    video_url = poll_generation(api_name, task_id, bn, idx + 1)
                    if video_url:
                        out_path = os.path.join(beat_options_dir, f"beat_{bn:02d}_option_{labels[idx + 1]}.mp4")
                        if download_video(video_url, out_path):
                            dur = get_duration(out_path)
                            tprint(f"  Beat {bn:2d} Option {labels[idx + 1]}: 💾 Saved via {api_name} ({dur:.1f}s)")
                            bc_results[idx] = out_path

                threads = []
                for idx in range(2):
                    t = threading.Thread(target=poll_bc, args=(idx,))
                    t.start()
                    threads.append(t)
                for t in threads:
                    t.join()

                all_options[bn] = [opt_a_path, bc_results[0], bc_results[1]]
                success = sum(1 for r in all_options[bn] if r)
                tprint(f"  Beat {bn}: {success}/3 options ready (A=existing, B+C=generated)")
                continue

        results = generate_beat_options(bn, img_path, motion_prompt, beat_options_dir)
        all_options[bn] = results

        success = sum(1 for r in results if r)
        tprint(f"  Beat {bn}: {success}/3 options generated")

    # Build review HTML
    if any(any(opts) for opts in all_options.values()):
        html_path = build_review_html(all_options)
        tprint(f"\n🎬 Review tool ready: {html_path}")
        tprint("Open in browser to pick the best animation for each beat!")
    else:
        tprint("\n❌ No options generated. Check EvoLink credits and API status.")

    # Summary
    print(f"\n{'='*70}")
    print("GENERATION SUMMARY")
    print(f"{'='*70}")
    total_generated = 0
    for bn in sorted(all_options.keys()):
        opts = all_options[bn]
        labels = ['A', 'B', 'C']
        status = []
        for i, o in enumerate(opts):
            if o:
                dur = get_duration(o)
                status.append(f"{labels[i]}:✅({dur:.1f}s)")
                total_generated += 1
            else:
                status.append(f"{labels[i]}:❌")
        print(f"  Beat {bn:2d}: {' | '.join(status)}")

    print(f"\nTotal: {total_generated}/{len(beat_nums)*3} options generated")
    actual_cost = total_generated * 0.375
    print(f"Actual cost: ${actual_cost:.2f}")

if __name__ == "__main__":
    main()
