#!/usr/bin/env python3
"""Quick diagnostic test for lip sync pipeline — run in Terminal."""

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
import json, time, urllib.request, urllib.error, sys, mimetypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lipsync_sender import upload_to_hosting, LipSyncClient

EVENT_DIR = Path(__file__).parent.parent / "Event_1"
API_KEY = get_secret("WAVESPEED_API_KEY")

clip = EVENT_DIR / "animation_clips" / "beat_03_option_3.mp4"
audio = EVENT_DIR / "story_scene_tts_v2" / "line_03_tessa_trimmed.mp3"

print(f"\n{'='*60}")
print("LIP SYNC DIAGNOSTIC TEST")
print(f"{'='*60}\n")

# Step 1: Check files exist
print(f"[1] Video: {clip.name} — {'EXISTS' if clip.exists() else 'MISSING'} ({clip.stat().st_size if clip.exists() else 0} bytes)")
print(f"[1] Audio: {audio.name} — {'EXISTS' if audio.exists() else 'MISSING'} ({audio.stat().st_size if audio.exists() else 0} bytes)")
if not clip.exists() or not audio.exists():
    print("FAIL: Files missing"); sys.exit(1)

# Step 2: Skipped — using data URIs directly (no file hosting needed)
print(f"\n[2] Using data URIs (files embedded in request) — no upload step needed")

# Step 3: Submit to WaveSpeed via curl with data URIs
print(f"\n[3] Submitting to WaveSpeed via curl (data URIs — no file hosting needed)...")
from lipsync_sender import file_to_data_uri
client = LipSyncClient(API_KEY)

video_data_uri = file_to_data_uri(clip, "video/mp4")
audio_data_uri = file_to_data_uri(audio, "audio/mpeg")
body = {"video": video_data_uri, "audio": audio_data_uri}
body_size = len(json.dumps(body))
print(f"    Payload size: {body_size / 1024 / 1024:.1f} MB")

t0 = time.time()
try:
    result = client._curl_json("POST", "https://api.wavespeed.ai/api/v3/bytedance/lipsync/audio-to-video", body, timeout=120)
    elapsed = time.time() - t0
    print(f"    Response ({elapsed:.1f}s): {json.dumps(result, indent=2)[:500]}")
    job_id = (result.get("data") or {}).get("id") or result.get("id")
    print(f"    Job ID: {job_id}")
except Exception as e:
    print(f"    ERROR ({time.time()-t0:.1f}s): {e}")
    sys.exit(1)

if not job_id:
    print("FAIL: No job ID in response"); sys.exit(1)

# Step 4: Poll via curl
print(f"\n[4] Polling for result...")
poll_url = f"https://api.wavespeed.ai/api/v3/predictions/{job_id}/result"
print(f"    Poll URL: {poll_url}")

for i in range(60):  # 10 minutes max
    try:
        poll_data = client._curl_json("GET", poll_url, timeout=15)
        data = poll_data.get("data") or {}
        status = data.get("status") or poll_data.get("status", "unknown")
        print(f"    [{i*10}s] status={status}")

        if status == "completed":
            outputs = [o for o in (data.get("outputs") or []) if o]
            video_out = data.get("output") or poll_data.get("video")
            print(f"\n    SUCCESS! Outputs: {outputs or video_out}")
            print(f"    Full response: {json.dumps(poll_data, indent=2)[:500]}")

            dl_url = (outputs[0] if outputs else None) or video_out
            if dl_url:
                dest = EVENT_DIR / "animation_clips" / "beat_03_lipsync.mp4"
                print(f"\n[5] Downloading to {dest.name}...")
                client.download(dl_url, dest)
                print(f"\n{'='*60}")
                print("ALL STEPS PASSED — Lip sync working!")
                print(f"{'='*60}")
            sys.exit(0)
        elif status in ("failed", "error"):
            print(f"\n    FAILED: {json.dumps(poll_data, indent=2)[:500]}")
            sys.exit(1)
    except Exception as e:
        print(f"    [{i*10}s] poll error: {e}")

    time.sleep(10)

print("TIMEOUT after 10 minutes")
sys.exit(1)
