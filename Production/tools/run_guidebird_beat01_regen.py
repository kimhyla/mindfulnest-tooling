#!/usr/bin/env python3
"""
Re-run Guide Bird beat_01 Kling options with anti-hand anatomical prompts.
Source: crop_bg_arc1_event1_post_beat_02_1777141175.webp
Audio:  line_01_guide_bird.mp3 (3.92s)
Fix:    adds "no human hands/fingers" to positive + negative prompts
"""

from __future__ import annotations
import base64, json, subprocess, sys, time, urllib.request, urllib.error
from datetime import datetime
from pathlib import Path

PROD      = Path("/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production")
START_IMG = PROD / "beat_generator_stills/crops/crop_bg_arc1_event1_post_beat_02_1777141175.webp"
AUDIO     = PROD / "Event_1/story_scene_tts_v2/storyboard_v43_prod/line_01_guide_bird.mp3"
OUT_DIR   = PROD / "Event_1/animation_clips"
OUT_DIR.mkdir(exist_ok=True)

WAVESPEED_KEY  = "8e88bb702e312db41d94dd39caadb8835d69088441c3e319fa804a9a9dc284d3"
KLING_ENDPOINT = "https://api.wavespeed.ai/api/v3/kwaivgi/kling-v3.0-pro/image-to-video"
POLL_ENDPOINT  = "https://api.wavespeed.ai/api/v3/predictions/{}/result"

POSITIVE = (
    "Chipper the Guide Bird — a small round blue-and-white cartoon bird with "
    "big expressive eyes and a blue scarf — glowing with happy delighted joy, "
    "warm excited smile energy, bright wide eyes full of wonder and delight, "
    "in a magical forest clearing, soft golden ambient light. "
    "Gentle happy idle motion, calm and content. "
    "Wings remain anatomically correct bird wings with feathers throughout — "
    "no fingers, no hands at any point. "
    "Beak closed, no speech. Character moves gently, background stays completely still. "
    "Cinematic 4:3 composition."
)

NEGATIVE = (
    "lip sync, speaking, talking, mouth movement, beak movement, dialogue, speech, "
    "open mouth, Chinese, audio, voice, singing, background motion, camera pan, zoom, "
    "moving background, parallax, "
    "scared, fearful, horrified, alarmed, shocked, anxious, ruffled feathers, frightened, "
    "human hands, fingers, five fingers, hand, wrist, knuckles, human anatomy, "
    "human limb, finger joints"
)

def ts():
    return datetime.now().strftime("%H:%M:%S")

def log(msg):
    print(f"[{ts()}] {msg}", flush=True)

def img_to_b64_uri(path: Path) -> str:
    data = path.read_bytes()
    ext  = path.suffix.lower().lstrip(".")
    mime = {"webp": "image/webp", "png": "image/png", "jpg": "image/jpeg"}.get(ext, "image/png")
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"

def audio_duration(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True)
    return float(r.stdout.strip())

def api_post(url, payload, headers, retries=4, timeout=90):
    body = json.dumps(payload).encode()
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
        except urllib.error.URLError as e:
            if attempt < retries - 1:
                wait = 10 * (attempt + 1)
                log(f"  Submit error (attempt {attempt+1}): {e} — retrying in {wait}s …")
                time.sleep(wait)
            else:
                raise

def api_get(url, headers):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())

def poll(pred_id: str, label: str, timeout: int = 600) -> dict:
    url     = POLL_ENDPOINT.format(pred_id)
    headers = {"Authorization": f"Bearer {WAVESPEED_KEY}"}
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r      = api_get(url, headers)
            status = r.get("data", {}).get("status", r.get("status", ""))
            if status in ("completed", "succeeded"):
                return r
            if status in ("failed", "error"):
                raise RuntimeError(f"{label} failed: {r}")
            log(f"  {label}: {status} …")
        except urllib.error.URLError as e:
            log(f"  {label} poll error: {e}")
        time.sleep(8)
    raise TimeoutError(f"{label} timed out")


log("Preparing source image …")
start_uri  = img_to_b64_uri(START_IMG)
audio_dur  = audio_duration(AUDIO)
kling_dur  = min(10, max(5, round(audio_dur + 0.4)))
log(f"Audio: {audio_dur:.2f}s → Kling duration: {kling_dur}s")

headers = {
    "Authorization": f"Bearer {WAVESPEED_KEY}",
    "Content-Type":  "application/json",
}

payload = {
    "prompt":          POSITIVE,
    "negative_prompt": NEGATIVE,
    "image":           start_uri,
    "duration":        kling_dur,
    "cfg_scale":       0.5,
    "sound":           False,
}

log("Submitting 3 Kling v3.0 Pro jobs …")
pred_ids = []
for i in range(3):
    r       = api_post(KLING_ENDPOINT, payload, headers)
    pred_id = r.get("data", {}).get("id") or r.get("id")
    log(f"  Option {chr(65+i)} submitted: {pred_id}")
    pred_ids.append(pred_id)
    time.sleep(1)

log("Polling (3–8 min per job) …")
ts_now     = int(time.time())
clip_paths = []

for i, pred_id in enumerate(pred_ids):
    label = f"Option {chr(65+i)}"
    log(f"  Waiting for {label} …")
    result  = poll(pred_id, label)
    data    = result.get("data", result)
    outputs = data.get("outputs", data.get("output", []))
    if isinstance(outputs, list):
        video_url = outputs[0] if outputs else None
    elif isinstance(outputs, str):
        video_url = outputs
    else:
        video_url = data.get("video_url") or data.get("url")

    if not video_url:
        log(f"  WARNING: no video URL for {label}: {result}")
        continue

    name = f"guidebird_beat01_nohand_{chr(65+i).lower()}_{ts_now}.mp4"
    dest = OUT_DIR / name
    urllib.request.urlretrieve(video_url, dest)
    mb = dest.stat().st_size / (1024*1024)
    log(f"  {label} saved: {name} ({mb:.2f} MB)")
    clip_paths.append((label, dest))

print()
print("=" * 60)
print("GUIDE BIRD BEAT 01 — ANTI-HAND REGEN COMPLETE")
print("=" * 60)
for label, path in clip_paths:
    mb = path.stat().st_size / (1024*1024)
    print(f"  {label}: {path.name}  ({mb:.2f} MB)")
    print(f"    file://{path}")
print()
print(f"Audio: file://{AUDIO}")
print()
print("Next: review clips, pick best, run lipsync via:")
print("  POST http://localhost:5111/api/select  {beat, selected_option}")
print("  POST http://localhost:5111/api/lipsync {beat: beat_01}")
print("=" * 60)
