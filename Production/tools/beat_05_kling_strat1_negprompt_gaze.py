#!/usr/bin/env python3
"""
beat_05_kling_strat1_negprompt_gaze.py

Strategy 1 (per Agent 3's combination-strategy ranking): negative-prompt-only
gaze control at cfg_scale=0.5. Keeps Option B's lipsync-friendly recipe
100% intact; ONLY adds gaze-off terms to the negative prompt.

WHY THIS SHOULD COMBINE BOTH WINS:
  - Option B (silcomp winner): lipsync works because Kling produced natural
    mouth geometry + micro-motion + head rotation at cfg=0.5 with a generic
    prompt. Only flaw: gaze drifts up-right.
  - Option D (2-lever): gaze locked to camera via "eyes meet camera" positive
    prompt + cfg=0.75, BUT stacked "mouth closed, beak closed, minimal motion"
    flattened the mouth region and froze head motion → destroyed the
    LatentSync landmark + TREPA signals → lipsync broke (per tonight's
    forensic research, logged in Directus activity id=111 + lessons learned).

  Strategy 1 hypothesis: Kling's up-and-right gaze in B was a MODEL DEFAULT,
  not a deliberate creative choice. We can redirect it by putting "looking
  away, looking up, profile view, etc" into the NEGATIVE prompt without
  adding any positive-prompt constraints that would collapse the mouth
  region or freeze the head. Gaze pulls forward, mouth/motion stay natural,
  lipsync still works.

REUSES the same source image (tessa_initial_4x3) and audio (silcomp) so the
ONLY variable is the Kling prompt/cfg combination.

Cost: ~$0.60 ($0.45 Kling + $0.15 lipsync). Runs in ~10-15 min overnight.
"""

from __future__ import annotations

import base64
import io
import json
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROD_ROOT = HERE.parent
EVENT_DIR = PROD_ROOT / "Event_1"
CLIPS_DIR = EVENT_DIR / "animation_clips"
TTS_DIR = EVENT_DIR / "story_scene_tts_v2"
PRESERVED = EVENT_DIR / "preserved_winners"

SOURCE_IMG_DISK = EVENT_DIR / "_temp_images" / "tessa_initial_4x3.png"
SILCOMP_AUDIO = TTS_DIR / "_tmp_line_05_tessa_silboth_20260417-034224.mp3"

WAVESPEED_SUBMIT = "https://api.wavespeed.ai/api/v3/kwaivgi/kling-v3.0-pro/image-to-video"
MIN_ANIMATION_SIZE = 600

# Strategy 1: generic positive prompt + gaze-off terms in negative prompt
# Positive prompt — minimal, matching Option B's "generic motion" approach.
# NO "eyes meet camera", NO "mouth closed, beak closed", NO "minimal motion",
# NO "static camera", NO "head remains facing forward" — all of which killed D.
STRAT1_PROMPT = (
    "A small sad turtle (Tessa) sits quietly in a soft forest clearing. "
    "Remorseful, slightly embarrassed expression. Natural subtle idle "
    "motion — breathing, slight shifts, blinking. Beak at rest. "
    "Soft ambient light, cinematic 4:3 composition. "
    "Silent subtle idle movement only, no dialogue in video."
)

# Rule 8 baseline negatives + Strategy 1 gaze-off additions.
# The gaze-off additions suppress Kling's default tendency to drift eyes
# upward and away from camera, WITHOUT over-constraining the face.
STRAT1_NEGATIVE_PROMPT = (
    # Rule 8 anti-lipsync (required, always on)
    "lip sync, speaking, talking, mouth movement, beak movement, dialogue, "
    "speech, open mouth, Chinese, audio, voice, singing, "
    # Strategy 1 gaze-off additions
    "looking up, looking at sky, looking above camera, eyes rolled up, "
    "eyes looking away, eyes averted, profile view, side view, head turned, "
    "off-axis gaze, three-quarter angle, "
    # General quality
    "low quality, blurry, distorted"
)

CFG_SCALE_BASELINE = 0.5   # Rule 8 compliant — no deviation needed
DURATION_S = 10

TIMESTAMP = datetime.now().strftime("%Y%m%d-%H%M%S")
UPSCALED_TMP = EVENT_DIR / f"_tmp_tessa_initial_4x3_upscaled_s1_{TIMESTAMP}.png"
KLING_OUT = CLIPS_DIR / f"beat_05_option_E_kling_strat1_{TIMESTAMP}.mp4"
KLING_TRIMMED = CLIPS_DIR / f"_tmp_option_E_trim8.7s_{TIMESTAMP}.mp4"
LIPSYNC_OUT = CLIPS_DIR / f"beat_05_lipsync_strat1_exp_{TIMESTAMP}.mp4"


def duration_of(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe","-v","error","-show_entries","format=duration",
         "-of","default=noprint_wrappers=1:nokey=1",str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(r.stdout.strip())


def ffmpeg_run(cmd, what):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"ffmpeg failed ({what}):\n{r.stderr[-1500:]}")
        sys.exit(1)


def upscale_source():
    from PIL import Image
    img = Image.open(SOURCE_IMG_DISK)
    w, h = img.size
    if min(w, h) >= MIN_ANIMATION_SIZE:
        new = img
    else:
        scale = MIN_ANIMATION_SIZE / min(w, h)
        new = img.resize((int(w*scale), int(h*scale)), Image.LANCZOS)
    new.save(UPSCALED_TMP, format="PNG")
    print(f"  source {w}x{h} → upscaled {new.size[0]}x{new.size[1]}")
    buf = io.BytesIO()
    new.save(buf, format="PNG")
    return f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode('ascii')}"


def load_api_key():
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    import importlib.util
    spec = importlib.util.spec_from_file_location("_srv", HERE / "production_server.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    keys = mod.parse_api_keys(PROD_ROOT / "API_KEYS_MASTER.md")
    return keys["wavespeed"]


def kling_submit(image_uri: str, api_key: str) -> str:
    payload = {
        "image": image_uri,
        "prompt": STRAT1_PROMPT,
        "negative_prompt": STRAT1_NEGATIVE_PROMPT,
        "duration": DURATION_S,
        "cfg_scale": CFG_SCALE_BASELINE,
        "sound": False,
    }
    req = urllib.request.Request(
        WAVESPEED_SUBMIT,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}",
                 "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    return (result.get("data", {}).get("id")
            or result.get("id")
            or result.get("task_id"))


def kling_poll_fresh(task_id: str, api_key: str, timeout_s: int = 900) -> dict:
    """Fresh http.client connection per poll — bypasses urllib stuck-state
    that plagued tonight's earlier Kling runs."""
    import http.client, ssl
    path = f"/api/v3/predictions/{task_id}/result"
    start = time.time()
    last_status = None
    while time.time() - start < timeout_s:
        try:
            ctx = ssl.create_default_context()
            ctx.options |= ssl.OP_NO_TICKET | ssl.OP_NO_COMPRESSION
            conn = http.client.HTTPSConnection("api.wavespeed.ai", timeout=20, context=ctx)
            try:
                conn.request("GET", path,
                             headers={"Authorization": f"Bearer {api_key}"})
                resp = conn.getresponse()
                body = resp.read().decode("utf-8", errors="replace")
            finally:
                conn.close()
            data = json.loads(body).get("data", {})
            status = (data.get("status") or "").lower()
            if status != last_status:
                print(f"  t+{int(time.time()-start):3d}s status={status}")
                last_status = status
            if status in ("completed", "failed", "error"):
                return data
        except Exception as exc:
            print(f"  t+{int(time.time()-start):3d}s poll err: {exc}")
        time.sleep(5)
    return {"status": "timeout"}


def main():
    print("=" * 70)
    print("beat_05 STRATEGY 1 — negative-prompt-only gaze, cfg=0.5")
    print(f"  TS: {TIMESTAMP}")
    print(f"  Hypothesis: gaze drift in Option B is a Kling default that can")
    print(f"    be redirected via negative-prompt terms WITHOUT the mouth/")
    print(f"    motion constraints that killed Option D's lipsync.")
    print("=" * 70)

    print("\n[1/6] Upscale source")
    img_uri = upscale_source()
    print(f"  data URI: {len(img_uri):,} chars")

    print(f"\n[2/6] Submit Kling (cfg_scale={CFG_SCALE_BASELINE})")
    api_key = load_api_key()
    task_id = kling_submit(img_uri, api_key)
    print(f"  task_id: {task_id}")

    print(f"\n[3/6] Poll Kling (fresh-connection-per-poll to avoid urllib stuck)")
    result = kling_poll_fresh(task_id, api_key)
    if result.get("status") != "completed":
        print(f"  FATAL: Kling status={result.get('status')}")
        print(f"  (task_id={task_id} — recoverable via fresh poll tomorrow)")
        sys.exit(1)
    clip_url = (result.get("outputs") or [None])[0]
    print(f"  ✓ Kling completed, CDN: {clip_url[:80]}...")

    print(f"\n[4/6] Download + trim to 8.7s")
    r = subprocess.run(
        ["curl","-sSL","-o",str(KLING_OUT), clip_url],
        capture_output=True, text=True, timeout=120,
    )
    if r.returncode != 0:
        sys.exit(f"curl failed: {r.stderr}")
    kling_dur = duration_of(KLING_OUT)
    print(f"  → {KLING_OUT.name} ({kling_dur:.3f}s)")
    PRESERVED.mkdir(exist_ok=True)
    shutil.copy2(KLING_OUT, PRESERVED / KLING_OUT.name)
    print(f"  [preserve] → {PRESERVED.name}/{KLING_OUT.name}")

    ffmpeg_run([
        "ffmpeg","-hide_banner","-loglevel","error","-y",
        "-i", str(KLING_OUT), "-t", "8.7",
        "-c:v","libx264","-preset","fast","-crf","18",
        "-c:a","aac","-b:a","128k","-movflags","+faststart",
        str(KLING_TRIMMED),
    ], "trim")
    print(f"  → {KLING_TRIMMED.name} (trim to 8.7s)")

    print(f"\n[5/6] Submit to ByteDance LipSync (silcomp audio, same as winner)")
    from lipsync_sender import LipSyncClient
    client = LipSyncClient(api_key)
    t0 = time.time()
    ls = client.submit_and_wait(KLING_TRIMMED, SILCOMP_AUDIO, LIPSYNC_OUT)
    elapsed = time.time() - t0
    print(f"  lipsync done in {elapsed:.1f}s: {ls.get('status')}")
    if ls.get("status") != "completed":
        print(f"  WARN: {ls.get('error')}")

    print(f"\n[6/6] Open for Kim's morning review")
    if LIPSYNC_OUT.exists():
        ls_dur = duration_of(LIPSYNC_OUT)
        print(f"  lipsync → {LIPSYNC_OUT.name} ({ls_dur:.3f}s)")
        subprocess.run(["open","-a","QuickTime Player", str(LIPSYNC_OUT)])
    subprocess.run(["open","-a","QuickTime Player", str(KLING_OUT)])

    # Manifest
    manifest = {
        "ts": TIMESTAMP,
        "strategy": "1_negprompt_gaze_cfg05",
        "hypothesis": "Negative-prompt-only gaze control preserves Option B's "
                      "lipsync-friendly recipe while redirecting gaze toward camera",
        "kling_task_id": task_id,
        "kling_status": result.get("status"),
        "positive_prompt": STRAT1_PROMPT,
        "negative_prompt": STRAT1_NEGATIVE_PROMPT,
        "cfg_scale": CFG_SCALE_BASELINE,
        "duration_s": DURATION_S,
        "source_image": "tessa_initial_4x3",
        "outputs": {
            "raw_kling": f"Event_1/animation_clips/{KLING_OUT.name}",
            "raw_kling_dur_s": kling_dur,
            "lipsync": f"Event_1/animation_clips/{LIPSYNC_OUT.name}" if LIPSYNC_OUT.exists() else None,
            "lipsync_dur_s": ls_dur if LIPSYNC_OUT.exists() else None,
        },
        "baseline_for_ab": {
            "silcomp_winner_B": "Event_1/animation_clips/beat_05_lipsync.mp4",
            "failed_2lever_D_raw": "Event_1/animation_clips/beat_05_option_D_kling_2lever_20260417-042007.mp4",
            "failed_2lever_D_lipsync": "Event_1/animation_clips/beat_05_lipsync_2lever_exp_20260417-042007.mp4",
        },
    }
    m_path = EVENT_DIR / f"beat_05_strat1_manifest_{TIMESTAMP}.json"
    m_path.write_text(json.dumps(manifest, indent=2))
    print(f"  manifest → Event_1/{m_path.name}")

    print("\n" + "=" * 70)
    print("STRATEGY 1 COMPLETE — 3-way A/B ready for Kim's morning review:")
    print(f"  (B baseline) beat_05_lipsync.mp4         — good sync / gaze off")
    print(f"  (D failed)   beat_05_lipsync_2lever_exp_ — bad sync / gaze on")
    print(f"  (E new)      {LIPSYNC_OUT.name}")
    print(f"               → hope: good sync AND better gaze")
    print("=" * 70)


if __name__ == "__main__":
    main()
