#!/usr/bin/env python3
"""
Final lip sync diagnostic — tries every approach in sequence.
Run: python3 test_lipsync_final.py
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
import json, time, subprocess, base64, sys, os
from pathlib import Path

EVENT_DIR = Path(__file__).parent.parent / "Event_1"
API_KEY = get_secret("WAVESPEED_API_KEY")
SUBMIT_URL = "https://api.wavespeed.ai/api/v3/bytedance/lipsync/audio-to-video"
POLL_BASE = "https://api.wavespeed.ai/api/v3/predictions"

clip = EVENT_DIR / "animation_clips" / "beat_03_option_3.mp4"
audio = EVENT_DIR / "story_scene_tts_v2" / "line_03_tessa_trimmed.mp3"

def curl_post(url, body_dict, timeout=120):
    """POST JSON via curl using temp file for body. Returns parsed JSON."""
    import tempfile
    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
    json.dump(body_dict, tmp)
    tmp.close()
    try:
        r = subprocess.run(
            ["curl", "-s", "-S", "-m", str(timeout), "-X", "POST",
             "-H", f"Authorization: Bearer {API_KEY}",
             "-H", "Content-Type: application/json",
             "-d", f"@{tmp.name}", url],
            capture_output=True, text=True, timeout=timeout+10
        )
        if r.returncode != 0:
            return {"_error": f"curl exit {r.returncode}: {r.stderr[:300]}"}
        return json.loads(r.stdout)
    except Exception as e:
        return {"_error": str(e)}
    finally:
        os.unlink(tmp.name)

def curl_get(url, timeout=15):
    """GET via curl. Returns parsed JSON."""
    r = subprocess.run(
        ["curl", "-s", "-S", "-m", str(timeout),
         "-H", f"Authorization: Bearer {API_KEY}", url],
        capture_output=True, text=True, timeout=timeout+10
    )
    if r.returncode != 0:
        return {"_error": f"curl exit {r.returncode}: {r.stderr[:300]}"}
    return json.loads(r.stdout)

def poll_job(job_id, max_wait=300):
    """Poll until done. Returns final response."""
    url = f"{POLL_BASE}/{job_id}/result"
    print(f"    Polling: {url}")
    start = time.time()
    while time.time() - start < max_wait:
        data = curl_get(url)
        if "_error" in data:
            print(f"    Poll error: {data['_error']}")
            time.sleep(10); continue
        inner = data.get("data") or {}
        status = inner.get("status") or data.get("status", "?")
        print(f"    [{int(time.time()-start)}s] {status}")
        if status == "completed":
            outputs = [o for o in (inner.get("outputs") or []) if o]
            output = inner.get("output") or data.get("video")
            return {"status": "completed", "url": (outputs[0] if outputs else output)}
        if status in ("failed", "error"):
            err = inner.get("error") or data.get("error", "unknown")
            return {"status": "failed", "error": str(err)[:300]}
        time.sleep(10)
    return {"status": "timeout"}

def upload_catbox(fpath):
    """Upload to catbox.moe via curl (avoids Python SSL issues)."""
    r = subprocess.run(
        ["curl", "-s", "-S", "-m", "60", "-F", f"reqtype=fileupload",
         "-F", f"fileToUpload=@{fpath}", "https://catbox.moe/user/api.php"],
        capture_output=True, text=True, timeout=70
    )
    if r.returncode == 0 and r.stdout.startswith("https://"):
        return r.stdout.strip()
    return None

def to_data_uri(fpath, mime):
    b64 = base64.b64encode(fpath.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"

print(f"\n{'='*60}")
print("LIP SYNC — FINAL MULTI-APPROACH TEST")
print(f"{'='*60}\n")
print(f"Video: {clip.name} ({clip.stat().st_size:,} bytes)")
print(f"Audio: {audio.name} ({audio.stat().st_size:,} bytes)")

# Step 0: Connectivity check (just test TCP, don't parse JSON)
print(f"\n[0] Connectivity check...")
chk = subprocess.run(
    ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "-m", "10",
     "https://api.wavespeed.ai/api/v3/"],
    capture_output=True, text=True, timeout=15
)
print(f"    API reachable: {'yes (HTTP ' + chk.stdout + ')' if chk.returncode == 0 else 'NO: ' + chk.stderr[:200]}")

# ---- APPROACH A: catbox URLs (retry — maybe WaveSpeed download was transient) ----
print(f"\n{'='*60}")
print("[A] APPROACH: catbox.moe URLs")
print(f"{'='*60}")

print("    Uploading video to catbox via curl...")
vid_url = upload_catbox(clip)
print(f"    Video: {vid_url}")

print("    Uploading audio to catbox via curl...")
aud_url = upload_catbox(audio)
print(f"    Audio: {aud_url}")

if vid_url and aud_url:
    print("    Submitting to WaveSpeed...")
    resp = curl_post(SUBMIT_URL, {"video": vid_url, "audio": aud_url}, timeout=30)
    if "_error" not in resp:
        job_id = (resp.get("data") or {}).get("id") or resp.get("id")
        print(f"    Job ID: {job_id}")
        if job_id:
            result = poll_job(job_id)
            if result["status"] == "completed":
                print(f"\n    *** APPROACH A SUCCEEDED! ***")
                dest = EVENT_DIR / "animation_clips" / "beat_03_lipsync.mp4"
                subprocess.run(["curl", "-s", "-o", str(dest), "-m", "120", result["url"]], timeout=130)
                print(f"    Downloaded: {dest.name} ({dest.stat().st_size:,} bytes)")
                print(f"\n{'='*60}\nSUCCESS!\n{'='*60}")
                sys.exit(0)
            else:
                print(f"    Approach A failed at polling: {result}")
    else:
        print(f"    Submit error: {resp['_error']}")
else:
    print("    Upload failed, skipping approach A")

# ---- APPROACH B: audio data URI + video catbox URL (small payload + URL) ----
print(f"\n{'='*60}")
print("[B] APPROACH: video=catbox URL, audio=data URI (148KB)")
print(f"{'='*60}")

if vid_url:
    aud_uri = to_data_uri(audio, "audio/mpeg")
    print(f"    Audio data URI: {len(aud_uri)} chars")
    print("    Submitting...")
    resp = curl_post(SUBMIT_URL, {"video": vid_url, "audio": aud_uri}, timeout=30)
    if "_error" not in resp:
        job_id = (resp.get("data") or {}).get("id") or resp.get("id")
        print(f"    Job ID: {job_id}")
        if job_id:
            result = poll_job(job_id)
            if result["status"] == "completed":
                print(f"\n    *** APPROACH B SUCCEEDED! ***")
                dest = EVENT_DIR / "animation_clips" / "beat_03_lipsync.mp4"
                subprocess.run(["curl", "-s", "-o", str(dest), "-m", "120", result["url"]], timeout=130)
                print(f"    Downloaded: {dest.name} ({dest.stat().st_size:,} bytes)")
                print(f"\n{'='*60}\nSUCCESS!\n{'='*60}")
                sys.exit(0)
            else:
                print(f"    Approach B failed at polling: {result}")
    else:
        print(f"    Submit error: {resp['_error']}")
else:
    print("    No video URL, skipping approach B")

# ---- APPROACH C: both data URIs via temp file (5MB payload, longer timeout) ----
print(f"\n{'='*60}")
print("[C] APPROACH: both as data URIs (5.1MB payload, 120s timeout)")
print(f"{'='*60}")

vid_uri = to_data_uri(clip, "video/mp4")
aud_uri = to_data_uri(audio, "audio/mpeg")
payload_size = len(json.dumps({"video": vid_uri, "audio": aud_uri}))
print(f"    Payload: {payload_size/1024/1024:.1f} MB")
print("    Submitting (this may take a while)...")
resp = curl_post(SUBMIT_URL, {"video": vid_uri, "audio": aud_uri}, timeout=120)
if "_error" not in resp:
    job_id = (resp.get("data") or {}).get("id") or resp.get("id")
    print(f"    Job ID: {job_id}")
    if job_id:
        result = poll_job(job_id)
        if result["status"] == "completed":
            print(f"\n    *** APPROACH C SUCCEEDED! ***")
            dest = EVENT_DIR / "animation_clips" / "beat_03_lipsync.mp4"
            subprocess.run(["curl", "-s", "-o", str(dest), "-m", "120", result["url"]], timeout=130)
            print(f"    Downloaded: {dest.name} ({dest.stat().st_size:,} bytes)")
            print(f"\n{'='*60}\nSUCCESS!\n{'='*60}")
            sys.exit(0)
        else:
            print(f"    Approach C failed: {result}")
else:
    print(f"    Submit error: {resp['_error']}")

# ---- ALL FAILED ----
print(f"\n{'='*60}")
print("ALL APPROACHES FAILED")
print("WaveSpeed may be having issues. Try again in 30 minutes.")
print(f"{'='*60}")
sys.exit(1)
