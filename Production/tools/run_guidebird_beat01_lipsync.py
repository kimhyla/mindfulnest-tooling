#!/usr/bin/env python3
"""
Guide Bird beat_01 lipsync — §8.4 silcomp + §8.5 direct submit.
Source video: guidebird_beat01_nohand_c_1777157672.mp4
Audio:        line_01_guide_bird.mp3 (3.92s, has ~1.31s pause)
"""

from __future__ import annotations
import base64, json, subprocess, sys, tempfile, time, urllib.request, urllib.error
from datetime import datetime
from pathlib import Path

PROD      = Path("/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production")
VIDEO_SRC = PROD / "Event_1/animation_clips/guidebird_beat01_nohand_c_1777157672.mp4"
AUDIO_SRC = PROD / "Event_1/story_scene_tts_v2/storyboard_v43_prod/line_01_guide_bird.mp3"
OUT_DIR   = PROD / "Event_1/animation_clips"
TMP_DIR   = Path(tempfile.mkdtemp(prefix="lipsync_beat01_"))

WAVESPEED_KEY      = "8e88bb702e312db41d94dd39caadb8835d69088441c3e319fa804a9a9dc284d3"
LIPSYNC_ENDPOINT   = "https://api.wavespeed.ai/api/v3/bytedance/lipsync/audio-to-video"
POLL_ENDPOINT      = "https://api.wavespeed.ai/api/v3/predictions/{}/result"

def ts():
    return datetime.now().strftime("%H:%M:%S")

def log(msg):
    print(f"[{ts()}] {msg}", flush=True)

def run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, **kw)

def duration(path: Path) -> float:
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)])
    return float(r.stdout.strip())

def to_b64_uri(path: Path) -> str:
    data = path.read_bytes()
    ext  = path.suffix.lower().lstrip(".")
    mime = {"mp4": "video/mp4", "mp3": "audio/mpeg", "wav": "audio/wav"}.get(ext, "application/octet-stream")
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"

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

def api_get(url, headers, timeout=30):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())

def poll(pred_id: str, timeout: int = 600) -> dict:
    url      = POLL_ENDPOINT.format(pred_id)
    headers  = {"Authorization": f"Bearer {WAVESPEED_KEY}"}
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r      = api_get(url, headers)
            status = r.get("data", {}).get("status", r.get("status", ""))
            if status in ("completed", "succeeded"):
                return r
            if status in ("failed", "error"):
                raise RuntimeError(f"Lipsync failed: {r}")
            log(f"  status: {status} …")
        except urllib.error.URLError as e:
            log(f"  poll error: {e}")
        time.sleep(8)
    raise TimeoutError("Lipsync timed out")


# ── §8.4 Silence compression ──────────────────────────────────────────────────
log("§8.4 Detecting silence in audio …")
r = run(["ffmpeg", "-i", str(AUDIO_SRC),
         "-af", "silencedetect=noise=-32dB:duration=0.15",
         "-f", "null", "-"],
        text=True)
stderr = r.stderr

import re
silences = []
starts   = [float(m.group(1)) for m in re.finditer(r"silence_start: ([\d.]+)", stderr)]
ends     = [float(m.group(1)) for m in re.finditer(r"silence_end: ([\d.]+)", stderr)]
for s, e in zip(starts, ends):
    dur = e - s
    if dur > 1.0:
        silences.append((s, e, dur))
        log(f"  Silence {dur:.2f}s at {s:.2f}–{e:.2f}s → compress to 0.8s")

if silences:
    # Build concat list: split around each long silence, replace with 0.8s null
    audio_dur    = duration(AUDIO_SRC)
    segments     = []
    cursor       = 0.0
    seg_files    = []

    for idx, (sil_start, sil_end, sil_dur) in enumerate(silences):
        # speech before silence
        if sil_start > cursor + 0.01:
            seg = TMP_DIR / f"seg_speech_{idx}.mp3"
            run(["ffmpeg", "-y", "-i", str(AUDIO_SRC),
                 "-ss", str(cursor), "-to", str(sil_start),
                 "-c", "copy", str(seg)])
            seg_files.append(seg)

        # replacement silence 0.8s
        sil_seg = TMP_DIR / f"seg_sil_{idx}.mp3"
        run(["ffmpeg", "-y",
             "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
             "-t", "0.8", "-c:a", "libmp3lame", "-b:a", "128k", str(sil_seg)])
        seg_files.append(sil_seg)
        cursor = sil_end

    # trailing speech
    if cursor < audio_dur - 0.05:
        seg = TMP_DIR / f"seg_speech_tail.mp3"
        run(["ffmpeg", "-y", "-i", str(AUDIO_SRC),
             "-ss", str(cursor), "-c", "copy", str(seg)])
        seg_files.append(seg)

    # concat
    concat_list = TMP_DIR / "concat.txt"
    concat_list.write_text("\n".join(f"file '{f}'" for f in seg_files))
    audio_silcomp = TMP_DIR / "audio_silcomp.mp3"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0",
         "-i", str(concat_list), "-c", "copy", str(audio_silcomp)])
    log(f"  Silcomp done: {duration(audio_silcomp):.2f}s")
else:
    log("  No long silences found — using original audio")
    audio_silcomp = AUDIO_SRC

# ── Loudnorm ──────────────────────────────────────────────────────────────────
log("Loudnorm to -16 LUFS …")
audio_loudnorm = TMP_DIR / "audio_loudnorm.mp3"
run(["ffmpeg", "-y", "-i", str(audio_silcomp),
     "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
     "-c:a", "libmp3lame", "-b:a", "128k", str(audio_loudnorm)])

# Add 1.5s silence tail — gives ByteDance plenty of room to finish "a runestone"
log("Adding 1.5s tail padding …")
tail_silence = TMP_DIR / "tail_silence.mp3"
run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
     "-t", "1.5", "-c:a", "libmp3lame", "-b:a", "128k", str(tail_silence)])
pad_list = TMP_DIR / "pad_concat.txt"
pad_list.write_text(f"file '{audio_loudnorm}'\nfile '{tail_silence}'")
audio_norm = TMP_DIR / "audio_norm.mp3"
run(["ffmpeg", "-y", "-f", "concat", "-safe", "0",
     "-i", str(pad_list), "-c", "copy", str(audio_norm)])
audio_final_dur = duration(audio_norm)
log(f"  Final audio: {audio_final_dur:.2f}s (including 1.5s tail pad)")

# ── Trim video to audio + 0.4s tail room ─────────────────────────────────────
src_dur  = duration(VIDEO_SRC)
trim_dur = min(audio_final_dur + 1.9, src_dur)
log(f"Trimming video to {trim_dur:.2f}s (source: {src_dur:.2f}s) …")
video_trimmed = TMP_DIR / "video_trimmed.mp4"
run(["ffmpeg", "-y", "-i", str(VIDEO_SRC),
     "-t", str(trim_dur),
     "-c:v", "libx264", "-preset", "fast", "-crf", "18",
     "-an", str(video_trimmed)])
log(f"  Trimmed video: {duration(video_trimmed):.2f}s")

# §8.5 check: must be ≤10s
if audio_final_dur > 10.0:
    raise ValueError(f"Audio {audio_final_dur:.2f}s exceeds ByteDance 10s limit — use silence-split protocol")

# ── Submit to ByteDance LipSync ───────────────────────────────────────────────
log("Encoding video + audio as base64 …")
video_uri = to_b64_uri(video_trimmed)
audio_uri = to_b64_uri(audio_norm)

headers = {
    "Authorization": f"Bearer {WAVESPEED_KEY}",
    "Content-Type":  "application/json",
}
payload = {
    "video": video_uri,
    "audio": audio_uri,
}

log("Submitting to ByteDance LipSync …")
r       = api_post(LIPSYNC_ENDPOINT, payload, headers)
pred_id = r.get("data", {}).get("id") or r.get("id")
log(f"  Prediction ID: {pred_id}")

log("Polling lipsync (2–5 min) …")
result  = poll(pred_id)
data    = result.get("data", result)
outputs = data.get("outputs", data.get("output", []))
if isinstance(outputs, list):
    video_url = outputs[0] if outputs else None
elif isinstance(outputs, str):
    video_url = outputs
else:
    video_url = data.get("video_url") or data.get("url")

if not video_url:
    raise RuntimeError(f"No output URL: {result}")

ts_now   = int(time.time())
out_path = OUT_DIR / f"guidebird_beat01_lipsync_final_{ts_now}.mp4"
log(f"Downloading result …")
urllib.request.urlretrieve(video_url, out_path)
mb = out_path.stat().st_size / (1024*1024)

print()
print("=" * 60)
print("GUIDE BIRD BEAT 01 — LIPSYNC COMPLETE")
print("=" * 60)
print(f"  Output: {out_path.name}  ({mb:.2f} MB)")
print(f"  file://{out_path}")
print("=" * 60)
