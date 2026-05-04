#!/usr/bin/env python3
"""
One-shot pipeline: Guide Bird beat_02 (Event 1 post-resolution)
"Kiddo! [pause] [pause] I think you just woke up a runestone!"

Start image:  crop_bg_arc1_event1_post_beat_02_1777141175.webp  (accepted BG crop)
Audio:        line_01_guide_bird.mp3  (3.92s, already confirmed)
Output:       3 Kling animation options, then lipsync on the one Kim selects

Rule 8 compliant: cfg_scale=0.5, sound=False, anti-lipsync negatives
Rule 8.3: start+end frame pipeline (end frame generated via FLUX Kontext)
Rule 8.5: audio 3.92s ≤ 10s, single phrase, no silence gap → direct submit path
"""

from __future__ import annotations
import base64, json, subprocess, sys, time, urllib.request, urllib.error
from datetime import datetime, timezone
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────
PROD = Path("/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production")
CROPS = PROD / "beat_generator_stills/crops"
TTS_DIR = PROD / "Event_1/story_scene_tts_v2"
OUT_DIR = PROD / "Event_1/animation_clips"
PRESERVED = PROD / "Event_1/preserved_winners"

START_IMG  = CROPS / "crop_bg_arc1_event1_post_beat_02_1777141175.webp"
AUDIO_PATH = TTS_DIR / "line_01_guide_bird.mp3"
END_IMG_PATH = PROD / "Event_1/_temp_images/guidebird_beat02_end_frame.png"

OUT_DIR.mkdir(exist_ok=True)
PRESERVED.mkdir(exist_ok=True)
END_IMG_PATH.parent.mkdir(exist_ok=True)

# ── API Keys ───────────────────────────────────────────────────────────────
WAVESPEED_KEY = "8e88bb702e312db41d94dd39caadb8835d69088441c3e319fa804a9a9dc284d3"
BFL_KEY       = "bfl_BfxdzBz24Fa1Zht3Pv41tPNYCKTmHd6L"

# ── Constants (Rule 8) ─────────────────────────────────────────────────────
KLING_ENDPOINT  = "https://api.wavespeed.ai/api/v3/kwaivgi/kling-v3.0-pro/image-to-video"
POLL_ENDPOINT   = "https://api.wavespeed.ai/api/v3/predictions/{}/result"
LIPSYNC_ENDPOINT = "https://api.wavespeed.ai/api/v3/bytedance/lipsync/audio-to-video"
BFL_KONTEXT     = "https://api.bfl.ai/v1/flux-kontext-pro"
BFL_POLL        = "https://api.bfl.ai/v1/get_result?id={}"

ANTI_LIPSYNC_NEG = (
    "lip sync, speaking, talking, mouth movement, beak movement, dialogue, "
    "speech, open mouth, Chinese, audio, voice, singing"
)

KLING_POSITIVE = (
    "A small round blue-and-white bird (Chipper the Guide Bird) in a magical "
    "forest clearing, soft golden ambient light. Cinematic 4:3 composition. "
    "Beak closed, no speech, no beak movement. Natural idle motion only. "
    "Expressive eyes, feathers slightly ruffled with excitement. "
    "Natural interpolation between the two provided frames."
)

END_FRAME_PROMPT = (
    "Same character — Chipper, a small round blue-and-white cartoon bird with "
    "big expressive eyes, wearing a blue scarf, in a soft magical forest clearing. "
    "Same art style, same lighting, same 4:3 composition. "
    "Now settling into a wide-eyed, breathless, awe-struck stillness — "
    "beak just barely closed after an excited outburst, eyes wide and bright, "
    "feathers slightly raised. No mouth open. Same background."
)


def ts() -> str:
    return datetime.now().strftime("%H:%M:%S")

def log(msg: str) -> None:
    print(f"[{ts()}] {msg}")

def img_to_b64_uri(path: Path) -> str:
    data = path.read_bytes()
    ext = path.suffix.lower().lstrip(".")
    mime = {"webp": "image/webp", "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}.get(ext, "image/png")
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"

def duration_of(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True)
    return float(r.stdout.strip())

def check_size(path: Path) -> tuple[int, int]:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height",
         "-of", "csv=s=x:p=0", str(path)],
        capture_output=True, text=True, check=True)
    w, h = map(int, r.stdout.strip().split("x"))
    return w, h

def upscale_if_needed(path: Path) -> Path:
    w, h = check_size(path)
    short = min(w, h)
    if short >= 600:
        log(f"  Size OK: {w}×{h}")
        return path
    scale = 600 / short
    new_w, new_h = int(w * scale), int(h * scale)
    out = path.parent / (path.stem + "_upscaled.png")
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(path), "-vf", f"scale={new_w}:{new_h}", str(out)],
        check=True, capture_output=True)
    log(f"  Upscaled {w}×{h} → {new_w}×{new_h}")
    return out

def api_post(url: str, payload: dict, headers: dict) -> dict:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())

def api_get(url: str, headers: dict) -> dict:
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())

def poll_wavespeed(pred_id: str, label: str, timeout: int = 600) -> dict:
    url = POLL_ENDPOINT.format(pred_id)
    headers = {"Authorization": f"Bearer {WAVESPEED_KEY}"}
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = api_get(url, headers)
        status = r.get("data", {}).get("status", r.get("status", ""))
        if status in ("completed", "succeeded"):
            return r
        if status in ("failed", "error"):
            raise RuntimeError(f"{label} failed: {r}")
        log(f"  {label}: {status} …")
        time.sleep(8)
    raise TimeoutError(f"{label} timed out after {timeout}s")

def poll_bfl(task_id: str, timeout: int = 300) -> str:
    """Returns image URL."""
    url = BFL_POLL.format(task_id)
    headers = {"x-key": BFL_KEY}
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = api_get(url, headers)
        status = r.get("status", "")
        if status == "Ready":
            return r["result"]["sample"]
        if status in ("Error", "Failed", "Content Moderated"):
            raise RuntimeError(f"BFL failed: {r}")
        log(f"  BFL: {status} …")
        time.sleep(5)
    raise TimeoutError("BFL Kontext timed out")

def download(url: str, dest: Path) -> Path:
    urllib.request.urlretrieve(url, dest)
    return dest


# ══════════════════════════════════════════════════════════════════════════════
# STEP 1: FLUX Kontext — generate end frame
# ══════════════════════════════════════════════════════════════════════════════
log("STEP 1: Generating end frame via FLUX Kontext (~$0.08)")
start_uri = img_to_b64_uri(START_IMG)

bfl_payload = {
    "prompt": END_FRAME_PROMPT,
    "input_image": start_uri,
    "width": 1024,
    "height": 768,
}
bfl_headers = {"x-key": BFL_KEY, "Content-Type": "application/json"}

r = api_post(BFL_KONTEXT, bfl_payload, bfl_headers)
task_id = r.get("id") or r.get("task_id")
log(f"  BFL task_id: {task_id}")

end_img_url = poll_bfl(task_id)
log(f"  End frame ready: {end_img_url[:80]}...")
download(end_img_url, END_IMG_PATH)
log(f"  Saved to {END_IMG_PATH.name}")


# ══════════════════════════════════════════════════════════════════════════════
# STEP 2: Rule 6 upscale check on both frames
# ══════════════════════════════════════════════════════════════════════════════
log("STEP 2: Checking image sizes (Rule 6, ≥600px short side)")
start_final = upscale_if_needed(START_IMG)
end_final   = upscale_if_needed(END_IMG_PATH)

start_uri_final = img_to_b64_uri(start_final)
end_uri_final   = img_to_b64_uri(end_final)


# ══════════════════════════════════════════════════════════════════════════════
# STEP 3: Submit 3 Kling jobs (Options A, B, C)
# ══════════════════════════════════════════════════════════════════════════════
log("STEP 3: Submitting 3 Kling v3.0 Pro jobs (~$0.45 each)")
kling_headers = {
    "Authorization": f"Bearer {WAVESPEED_KEY}",
    "Content-Type": "application/json",
}

audio_dur = duration_of(AUDIO_PATH)
log(f"  Audio duration: {audio_dur:.2f}s")
kling_dur = min(10, max(5, round(audio_dur + 0.4)))
log(f"  Kling duration: {kling_dur}s")

kling_payload = {
    "prompt": KLING_POSITIVE,
    "negative_prompt": ANTI_LIPSYNC_NEG,
    "image": start_uri_final,
    "end_image": end_uri_final,
    "duration": kling_dur,
    "cfg_scale": 0.5,
    "sound": False,
}

pred_ids = []
for i in range(3):
    r = api_post(KLING_ENDPOINT, kling_payload, kling_headers)
    pred_id = r.get("data", {}).get("id") or r.get("id")
    log(f"  Option {chr(65+i)} submitted: {pred_id}")
    pred_ids.append(pred_id)
    time.sleep(1)  # brief stagger


# ══════════════════════════════════════════════════════════════════════════════
# STEP 4: Poll all 3 Kling jobs
# ══════════════════════════════════════════════════════════════════════════════
log("STEP 4: Polling Kling jobs (this takes 3-8 min per job) …")
clip_paths = []
ts_now = int(time.time())

for i, pred_id in enumerate(pred_ids):
    label = f"Option {chr(65+i)}"
    log(f"  Waiting for {label} …")
    result = poll_wavespeed(pred_id, label, timeout=600)

    # Extract video URL
    data = result.get("data", result)
    outputs = data.get("outputs", data.get("output", []))
    if isinstance(outputs, list):
        video_url = outputs[0] if outputs else None
    elif isinstance(outputs, str):
        video_url = outputs
    else:
        video_url = data.get("video_url") or data.get("url")

    if not video_url:
        log(f"  WARNING: No video URL in response for {label}: {result}")
        continue

    clip_name = f"guidebird_beat02_option_{chr(65+i).lower()}_{ts_now}.mp4"
    clip_path = OUT_DIR / clip_name
    download(video_url, clip_path)
    size_mb = clip_path.stat().st_size / (1024*1024)
    log(f"  {label} saved: {clip_name} ({size_mb:.2f} MB)")
    clip_paths.append((label, clip_path))


# ══════════════════════════════════════════════════════════════════════════════
# STEP 5: Summary
# ══════════════════════════════════════════════════════════════════════════════
print()
print("═" * 60)
print("GUIDE BIRD BEAT 02 — ANIMATION OPTIONS READY")
print("═" * 60)
for label, path in clip_paths:
    size_mb = path.stat().st_size / (1024*1024)
    print(f"  {label}: {path.name}  ({size_mb:.2f} MB)")
    print(f"    file://{path}")
print()
print(f"Audio ready:  file://{AUDIO_PATH}")
print()
print("Next step: Review clips above, pick the best one, then run:")
print("  python3 tools/run_guidebird_beat02_lipsync.py --clip <path>")
print("═" * 60)

# Save clip paths to a temp handoff file so lipsync script can find them
handoff = {
    "beat": "bg_arc1_event1_post_beat_02",
    "audio": str(AUDIO_PATH),
    "audio_duration_s": audio_dur,
    "clips": [{"label": lbl, "path": str(p)} for lbl, p in clip_paths],
    "end_frame": str(END_IMG_PATH),
    "generated_at": datetime.now(timezone.utc).isoformat(),
}
handoff_path = PROD / "Event_1/_guidebird_beat02_handoff.json"
handoff_path.write_text(json.dumps(handoff, indent=2))
log(f"Handoff saved: {handoff_path.name}")
