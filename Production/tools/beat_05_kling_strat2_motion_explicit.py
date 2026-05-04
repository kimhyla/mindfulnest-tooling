#!/usr/bin/env python3
"""
beat_05_kling_strat2_motion_explicit.py — Option F

Strategy 2: Strategy 1's winning recipe (cfg=0.5 + gaze via negative prompt)
PLUS explicit motion directives in the positive prompt, fixing the
"too static opening" bug that caused E's first ~1.5s to not lipsync.

Diagnosis (from Option E review):
  E succeeded at gaze redirection but Tessa held the same wide-eyed stare
  for ~5 seconds before the downcast pose at 7s. TREPA + InsightFace
  starved of per-frame variance in that opening window → LatentSync
  couldn't stamp 'I'm sorry. I fell.'

Fix: promote MOTION from 'subtle' aspirational language to an explicit
directive. Kling obeys explicit prompts; it treats 'subtle' as permission
to flatten.

Rule 8 + decision 162 compliance:
  - cfg_scale still = 0.5 (Rule 8 default, lipsync-safe)
  - Anti-lipsync terms present exactly once ('beak at rest, no dialogue')
  - No motion-locking phrases ('minimal motion', 'static', 'head forward')
  - Gaze control still via negative prompt
  - Still <= Rule 8.2's 'do not stack' limit (only 1 of the 4 forbidden stacks)

Cost: ~$0.60.
"""

from __future__ import annotations

import base64, io, json, shutil, subprocess, sys, time
import urllib.request
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

# STRATEGY 2: motion promoted from "subtle" aspiration to explicit directive.
# The difference vs E is in these specific phrases:
#   "Natural head motion throughout" (not "subtle idle motion")
#   "small tilts, gentle nods, frequent blinks, subtle postural shifts"
#   "Shoulders breathe"
#   "Expression evolves gradually from worry to sorrow"
# The emotional arc language ("worry → sorrow") forces per-frame change,
# which is what TREPA needs.
STRAT2_PROMPT = (
    "A small turtle (Tessa) sits in a soft forest clearing, camera-facing. "
    "Natural head motion throughout: small tilts, gentle nods, frequent "
    "blinks, subtle postural shifts. Shoulders breathe in and out. "
    "Expression evolves gradually from quiet worry to sorrow to soft "
    "acceptance. Beak at rest, no dialogue. Soft ambient light, cinematic "
    "4:3 composition."
)

# Rule 8 anti-lipsync + gaze-off negatives + NEW freeze-pose negatives
# (the freeze-pose additions are the key difference vs E's negative prompt)
STRAT2_NEGATIVE_PROMPT = (
    # Rule 8 anti-lipsync (required, always on)
    "lip sync, speaking, talking, mouth movement, beak movement, dialogue, "
    "speech, open mouth, Chinese, audio, voice, singing, "
    # Strategy 1 gaze-off (carried forward — worked for head pose)
    "looking up, looking at sky, looking above camera, eyes rolled up, "
    "eyes looking away, eyes averted, profile view, side view, head turned, "
    "off-axis gaze, three-quarter angle, "
    # Strategy 2 NEW: freeze-pose negatives (prevents the opening-static bug)
    "frozen pose, static face, wide unblinking stare, held expression, "
    "motionless, rigid posture, locked head, unchanging pose, "
    # General quality
    "low quality, blurry, distorted"
)

CFG_SCALE_BASELINE = 0.5
DURATION_S = 10

TIMESTAMP = datetime.now().strftime("%Y%m%d-%H%M%S")
KLING_OUT = CLIPS_DIR / f"beat_05_option_F_kling_strat2_{TIMESTAMP}.mp4"
KLING_TRIMMED = CLIPS_DIR / f"_tmp_option_F_trim8.7s_{TIMESTAMP}.mp4"
LIPSYNC_OUT = CLIPS_DIR / f"beat_05_lipsync_strat2_exp_{TIMESTAMP}.mp4"


def duration_of(p):
    r = subprocess.run(
        ["ffprobe","-v","error","-show_entries","format=duration",
         "-of","default=noprint_wrappers=1:nokey=1",str(p)],
        capture_output=True, text=True,
    )
    return float(r.stdout.strip())


def ffmpeg_run(cmd, what):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"ffmpeg failed ({what}):\n{r.stderr[-1500:]}")


def upscale_source():
    from PIL import Image
    img = Image.open(SOURCE_IMG_DISK)
    w, h = img.size
    scale = MIN_ANIMATION_SIZE / min(w, h) if min(w, h) < MIN_ANIMATION_SIZE else 1.0
    new = img.resize((int(w*scale), int(h*scale)), Image.LANCZOS) if scale > 1 else img
    buf = io.BytesIO(); new.save(buf, format="PNG")
    return f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode('ascii')}"


def load_api_key():
    if str(HERE) not in sys.path: sys.path.insert(0, str(HERE))
    import importlib.util
    spec = importlib.util.spec_from_file_location("_srv", HERE / "production_server.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod.parse_api_keys(PROD_ROOT / "API_KEYS_MASTER.md")["wavespeed"]


def kling_submit(uri, key):
    payload = {"image": uri, "prompt": STRAT2_PROMPT,
               "negative_prompt": STRAT2_NEGATIVE_PROMPT,
               "duration": DURATION_S, "cfg_scale": CFG_SCALE_BASELINE,
               "sound": False}
    req = urllib.request.Request(
        WAVESPEED_SUBMIT, data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    return result.get("data", {}).get("id") or result.get("id")


def kling_poll_fresh(task_id, key, timeout_s=900):
    import http.client, ssl
    path = f"/api/v3/predictions/{task_id}/result"
    start = time.time(); last = None
    while time.time() - start < timeout_s:
        try:
            ctx = ssl.create_default_context()
            ctx.options |= ssl.OP_NO_TICKET | ssl.OP_NO_COMPRESSION
            conn = http.client.HTTPSConnection("api.wavespeed.ai", timeout=20, context=ctx)
            try:
                conn.request("GET", path, headers={"Authorization": f"Bearer {key}"})
                body = conn.getresponse().read().decode("utf-8", errors="replace")
            finally:
                conn.close()
            data = json.loads(body).get("data", {})
            status = (data.get("status") or "").lower()
            if status != last:
                print(f"  t+{int(time.time()-start):3d}s status={status}")
                last = status
            if status in ("completed", "failed", "error"):
                return data
        except Exception as e:
            print(f"  t+{int(time.time()-start):3d}s err: {e}")
        time.sleep(5)
    return {"status": "timeout"}


def main():
    print("=" * 70)
    print("beat_05 STRATEGY 2 (F) — motion explicit + gaze via negatives")
    print(f"  TS: {TIMESTAMP}")
    print("=" * 70)

    print("\n[1/5] Upscale source")
    uri = upscale_source()

    print(f"\n[2/5] Submit Kling (cfg={CFG_SCALE_BASELINE}, duration={DURATION_S}s)")
    key = load_api_key()
    task_id = kling_submit(uri, key)
    print(f"  task_id: {task_id}")

    print(f"\n[3/5] Poll Kling")
    result = kling_poll_fresh(task_id, key)
    if result.get("status") != "completed":
        sys.exit(f"FATAL: {result}")
    clip_url = (result.get("outputs") or [None])[0]

    print(f"\n[4/5] Download + trim to 8.7s + lipsync")
    subprocess.run(["curl","-sSL","-o",str(KLING_OUT),clip_url],
                   capture_output=True, timeout=120, check=True)
    PRESERVED.mkdir(exist_ok=True)
    shutil.copy2(KLING_OUT, PRESERVED / KLING_OUT.name)
    print(f"  raw: {KLING_OUT.name} ({duration_of(KLING_OUT):.2f}s)")

    ffmpeg_run([
        "ffmpeg","-hide_banner","-loglevel","error","-y",
        "-i",str(KLING_OUT),"-t","8.7",
        "-c:v","libx264","-preset","fast","-crf","18",
        "-c:a","aac","-b:a","128k","-movflags","+faststart",
        str(KLING_TRIMMED),
    ], "trim")

    from lipsync_sender import LipSyncClient
    client = LipSyncClient(key)
    t0 = time.time()
    ls = client.submit_and_wait(KLING_TRIMMED, SILCOMP_AUDIO, LIPSYNC_OUT)
    print(f"  lipsync done in {time.time()-t0:.0f}s: {ls.get('status')}")

    print(f"\n[5/5] Open for review")
    if LIPSYNC_OUT.exists():
        print(f"  lipsync: {LIPSYNC_OUT.name} ({duration_of(LIPSYNC_OUT):.2f}s)")
        subprocess.run(["open","-a","QuickTime Player", str(LIPSYNC_OUT)])
    subprocess.run(["open","-a","QuickTime Player", str(KLING_OUT)])

    # Manifest
    manifest = {
        "ts": TIMESTAMP, "strategy": "2_motion_explicit_neg_freeze",
        "kling_task_id": task_id, "cfg_scale": CFG_SCALE_BASELINE,
        "duration_s": DURATION_S, "prompt": STRAT2_PROMPT,
        "negative_prompt": STRAT2_NEGATIVE_PROMPT,
        "diff_vs_E": {
            "positive_added": "Explicit motion: 'natural head motion, small tilts, gentle nods, frequent blinks, subtle postural shifts, shoulders breathe, expression evolves worry→sorrow'",
            "negative_added": "Freeze-pose blockers: 'frozen pose, static face, wide unblinking stare, held expression, motionless, rigid posture, locked head, unchanging pose'",
            "cfg_unchanged": True, "source_unchanged": True,
        },
        "hypothesis": "Explicit motion directive keeps TREPA + InsightFace fed throughout opening, preventing E's static-opening lipsync gap on 'I'm sorry. I fell.'",
        "outputs": {
            "raw": f"Event_1/animation_clips/{KLING_OUT.name}",
            "lipsync": f"Event_1/animation_clips/{LIPSYNC_OUT.name}" if LIPSYNC_OUT.exists() else None,
        },
    }
    (EVENT_DIR / f"beat_05_strat2_manifest_{TIMESTAMP}.json").write_text(json.dumps(manifest, indent=2))

    print("\n" + "="*70)
    print(f"STRATEGY 2 COMPLETE")
    print(f"  Raw F:     {KLING_OUT.name}")
    print(f"  Lipsync F: {LIPSYNC_OUT.name if LIPSYNC_OUT.exists() else '(failed)'}")
    print(f"  vs E:      beat_05_lipsync_strat1_exp_20260417-044454.mp4")
    print(f"  vs B:      beat_05_lipsync.mp4 (live)")


if __name__ == "__main__":
    main()
