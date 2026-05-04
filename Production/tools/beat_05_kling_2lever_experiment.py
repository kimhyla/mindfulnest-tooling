#!/usr/bin/env python3
"""
beat_05_kling_2lever_experiment.py

Revised 2-lever test (per Phase 0 preflight id=24, task_id=
beat_05_kling_regen_4levers_20260417):

  Lever 1: GAZE-DIRECTED PROMPT — explicit "eyes meet camera, mouth visible,
           face centered, minimal head motion" language (new pattern).
  Lever 2: cfg_scale=0.75 (deviation from Rule 8's locked 0.5, per
           SHORTCUT_RULE8_CFG_TEST_BEAT05, decision_id=160). Graduated —
           NOT jumping straight to 1.0 per counter-agent finding that
           cfg_scale=1.0 risks over-weighting the anti-lipsync negative
           prompt into a frozen mouth.

HELD CONSTANT (levers dropped per Phase 0 review):
  - duration = 10s (NOT 8s — would violate Rule 11 Source Fidelity since
                    beat_05 audio is 9.88s)
  - source still = tessa_initial_4x3 (same as Options A/B/C so delta is
                                      attributable to prompt+cfg_scale, not
                                      a new visual anchor)
  - anti-lipsync safeguards ALL preserved per Rule 8:
      sound=false, banned words omitted from prompt,
      negative_prompt includes "lip sync, speaking, mouth movement,
      open mouth, Chinese, audio, voice, singing"

OUTPUT (NOT promoted to live — Kim picks in the morning):
  1. Raw Kling clip: animation_clips/beat_05_option_D_kling_2lever_<TS>.mp4
     (new option, NOT overwriting beat_05_option_A/2/3)
  2. Lipsync against same silence-compressed audio + 8.7s trim (same
     setup as the winning silcomp run, so ONLY the source clip changes):
     animation_clips/beat_05_lipsync_2lever_exp_<TS>.mp4

Cost: ~$0.45 Kling + $0.15 lipsync = $0.60
"""

from __future__ import annotations

import base64
import io
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROD_ROOT = HERE.parent
EVENT_DIR = PROD_ROOT / "Event_1"
CLIPS_DIR = EVENT_DIR / "animation_clips"
TTS_DIR = EVENT_DIR / "story_scene_tts_v2"
PRESERVED = EVENT_DIR / "preserved_winners"

# Inputs
SOURCE_IMG_DISK = EVENT_DIR / "_temp_images" / "tessa_initial_4x3.png"  # 200x150
SILCOMP_AUDIO_TEMPLATE = TTS_DIR / "_tmp_line_05_tessa_silboth_20260417-034224.mp3"  # 8.27s

# Kling API
WAVESPEED_SUBMIT = "https://api.wavespeed.ai/api/v3/kwaivgi/kling-v3.0-pro/image-to-video"
WAVESPEED_POLL = "https://api.wavespeed.ai/api/v3/predictions/{task_id}/result"
MIN_ANIMATION_SIZE = 600  # Rule 6

# The 2 Levers
GAZE_PROMPT = (
    "A small sad turtle (Tessa) sits quietly in a soft forest clearing. "
    "Her eyes meet the camera directly — warm, present, remorseful gaze "
    "holding the viewer's attention throughout. Face centered in frame, "
    "mouth closed, beak closed. Slight gentle blink. No dialogue, no "
    "speech, no mouth movement, no beak movement. Minimal body motion — "
    "only subtle breathing. Head remains facing forward, no turning or "
    "looking away. Static camera, soft ambient light, cinematic 4:3 "
    "composition. Silent subtle idle movement only."
)

NEG_PROMPT = (
    "lip sync, speaking, talking, mouth movement, beak movement, dialogue, "
    "speech, open mouth, Chinese, audio, voice, singing, looking away, "
    "profile view, side view, head turned, eyes closed, head down, "
    "looking at ground, fast motion, camera movement, zoom, pan, low quality"
)

CFG_SCALE_TEST = 0.75  # vs Rule 8's locked 0.5 — SHORTCUT_RULE8_CFG_TEST_BEAT05
DURATION_S = 10  # held at max per Phase 0 (no Rule 11 violation)

TIMESTAMP = datetime.now().strftime("%Y%m%d-%H%M%S")
UPSCALED_TMP = EVENT_DIR / f"_tmp_tessa_initial_4x3_upscaled_{TIMESTAMP}.png"
KLING_OUT = CLIPS_DIR / f"beat_05_option_D_kling_2lever_{TIMESTAMP}.mp4"
KLING_TRIMMED = CLIPS_DIR / f"_tmp_option_D_trim8.7s_{TIMESTAMP}.mp4"
LIPSYNC_OUT = CLIPS_DIR / f"beat_05_lipsync_2lever_exp_{TIMESTAMP}.mp4"


def duration_of(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(r.stdout.strip())


def ffmpeg_run(cmd: list[str], what: str) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"ffmpeg failed ({what}):\n{r.stderr[-1500:]}")
        sys.exit(1)


def upscale_source() -> str:
    """Load 200x150 source, upscale to ≥600px shortest side, return data URI."""
    from PIL import Image  # type: ignore
    img = Image.open(SOURCE_IMG_DISK)
    w, h = img.size
    if min(w, h) >= MIN_ANIMATION_SIZE:
        scale = 1.0
        new = img
    else:
        scale = MIN_ANIMATION_SIZE / min(w, h)
        new_w, new_h = int(w * scale), int(h * scale)
        new = img.resize((new_w, new_h), Image.LANCZOS)
    new.save(UPSCALED_TMP, format="PNG")
    print(f"  source {w}x{h} → upscaled {new.size[0]}x{new.size[1]} (×{scale:.2f})")
    buf = io.BytesIO()
    new.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def load_api_key() -> str:
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_prod_server_import", HERE / "production_server.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore
    keys = mod.parse_api_keys(PROD_ROOT / "API_KEYS_MASTER.md")
    key = keys.get("wavespeed")
    if not key:
        sys.exit(f"FATAL: no wavespeed key (got: {sorted(keys.keys())})")
    return key


def kling_submit(image_data_uri: str, api_key: str) -> str:
    """Submit to Kling v3.0 Pro image-to-video, return task_id."""
    payload = {
        "image": image_data_uri,
        "prompt": GAZE_PROMPT,
        "negative_prompt": NEG_PROMPT,
        "duration": DURATION_S,
        "cfg_scale": CFG_SCALE_TEST,
        "sound": False,  # Rule 8 required
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        WAVESPEED_SUBMIT,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
    result = json.loads(raw.decode("utf-8"))
    # WaveSpeed returns {"data": {"id": "..."}} or similar
    task_id = (
        result.get("data", {}).get("id")
        or result.get("id")
        or result.get("task_id")
    )
    if not task_id:
        sys.exit(f"FATAL: no task_id in Kling response: {result}")
    return task_id


def kling_poll(task_id: str, api_key: str, timeout_s: int = 300) -> dict:
    """Poll until task completes or fails. Return final result dict."""
    url = WAVESPEED_POLL.format(task_id=task_id)
    start = time.time()
    last_status = None
    while time.time() - start < timeout_s:
        req = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read()
            result = json.loads(raw.decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            print(f"  poll error at {int(time.time()-start)}s: {exc}")
            time.sleep(5)
            continue
        data = result.get("data") or result
        status = (data.get("status") or "").lower()
        if status != last_status:
            print(f"  t+{int(time.time()-start):3d}s status={status}")
            last_status = status
        if status in ("completed", "failed", "error"):
            return data
        time.sleep(4)
    return {"status": "timeout"}


def kling_download(url: str, dst: Path) -> int:
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()
    dst.write_bytes(data)
    return len(data)


def trim_video(src: Path, dst: Path, seconds: float) -> None:
    if dst.exists():
        dst.unlink()
    ffmpeg_run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(src), "-t", f"{seconds:.3f}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
        str(dst),
    ], "trim_video")


def main() -> None:
    print("=" * 70)
    print("beat_05 2-LEVER Kling regen experiment")
    print(f"  TS: {TIMESTAMP}")
    print(f"  Preflight: id=24, task_id=beat_05_kling_regen_4levers_20260417")
    print(f"  Shortcut:  id=160, SHORTCUT_RULE8_CFG_TEST_BEAT05")
    print("=" * 70)

    # Step 1 — Upscale source image
    print(f"\n[1/7] Upscale source still (tessa_initial_4x3.png)")
    img_uri = upscale_source()
    print(f"  data URI: {len(img_uri):,} chars")

    # Step 2 — Show the 2 levers being tested
    print(f"\n[2/7] The 2 levers")
    print(f"  LEVER 1 (gaze prompt):")
    for line in GAZE_PROMPT.split(". "):
        print(f"    {line.strip()}" + ("." if not line.strip().endswith(".") else ""))
    print(f"  LEVER 2 (cfg_scale): {CFG_SCALE_TEST} (vs Rule 8 locked 0.5)")
    print(f"  HELD: duration={DURATION_S}s, source=tessa_initial_4x3, "
          f"anti-lipsync neg_prompt intact")

    # Step 3 — Submit to Kling
    print(f"\n[3/7] Submit to Kling v3.0 Pro")
    api_key = load_api_key()
    t0 = time.time()
    task_id = kling_submit(img_uri, api_key)
    print(f"  task_id: {task_id}")
    print(f"  submitted in {time.time()-t0:.1f}s")

    # Step 4 — Poll until complete
    print(f"\n[4/7] Poll Kling for result")
    result = kling_poll(task_id, api_key, timeout_s=300)
    if result.get("status") != "completed":
        print(f"  FATAL: Kling returned {result.get('status')}: {result}")
        sys.exit(1)
    outputs = result.get("outputs") or []
    if not outputs:
        print(f"  FATAL: no outputs in result: {result}")
        sys.exit(1)
    clip_url = outputs[0]
    print(f"  Kling completed, clip URL: {clip_url[:80]}...")

    # Step 5 — Download
    print(f"\n[5/7] Download new Kling clip")
    size = kling_download(clip_url, KLING_OUT)
    dur = duration_of(KLING_OUT)
    print(f"  → {KLING_OUT.name} ({dur:.3f}s, {size:,} bytes)")
    # Preserve — this is an "Option D" creative artifact
    PRESERVED.mkdir(exist_ok=True)
    preserved_kling = PRESERVED / f"beat_05_option_D_kling_2lever_{TIMESTAMP}.mp4"
    shutil.copy2(KLING_OUT, preserved_kling)
    print(f"  [preserve] → {preserved_kling.name}")

    # Step 6 — Lipsync against same silcomp audio + same 8.7s trim
    print(f"\n[6/7] Lipsync against silcomp audio (isolates lever effect)")
    # Trim the new Kling clip to 8.7s (same as winning silcomp run)
    trim_video(KLING_OUT, KLING_TRIMMED, 8.7)
    print(f"  trimmed Kling → 8.7s for fair A/B with silcomp winner")
    from lipsync_sender import LipSyncClient  # noqa: E402
    client = LipSyncClient(api_key)
    t_ls = time.time()
    ls_result = client.submit_and_wait(
        KLING_TRIMMED, SILCOMP_AUDIO_TEMPLATE, LIPSYNC_OUT,
    )
    ls_elapsed = time.time() - t_ls
    print(f"  lipsync done in {ls_elapsed:.1f}s: {ls_result.get('status')}")
    if ls_result.get("status") != "completed":
        print(f"  WARN: lipsync failed: {ls_result.get('error')}")
    else:
        print(f"  → {LIPSYNC_OUT.name} "
              f"({duration_of(LIPSYNC_OUT):.3f}s, {ls_result['size_bytes']:,} bytes)")

    # Step 7 — Open in QuickTime for morning review
    print(f"\n[7/7] Opening outputs in QuickTime (for Kim's morning review)")
    if LIPSYNC_OUT.exists():
        subprocess.run(["open", "-a", "QuickTime Player", str(LIPSYNC_OUT)])
    subprocess.run(["open", "-a", "QuickTime Player", str(KLING_OUT)])

    # Write experiment manifest for morning handoff
    manifest = {
        "ts": TIMESTAMP,
        "task_id": "beat_05_kling_regen_4levers_20260417",
        "preflight_id": 24,
        "shortcut_decision_id": 160,
        "levers_tested": {
            "gaze_prompt": GAZE_PROMPT,
            "cfg_scale": CFG_SCALE_TEST,
        },
        "levers_held": {
            "duration": DURATION_S,
            "source_image": "tessa_initial_4x3",
            "negative_prompt": NEG_PROMPT,
            "sound": False,
        },
        "outputs": {
            "raw_kling_clip": str(KLING_OUT.relative_to(PROD_ROOT)),
            "raw_kling_duration_s": dur,
            "lipsync_clip": str(LIPSYNC_OUT.relative_to(PROD_ROOT)),
            "lipsync_duration_s": duration_of(LIPSYNC_OUT) if LIPSYNC_OUT.exists() else None,
        },
        "kling_task_id": task_id,
        "cost_usd": 0.60,
        "status": "completed",
        "baseline_for_comparison": {
            "silcomp_winner": "animation_clips/beat_05_lipsync.mp4",
            "silcomp_source_option": "Option B at 10s, no gaze prompt, cfg_scale=0.5",
        },
    }
    manifest_path = EVENT_DIR / f"beat_05_kling_2lever_manifest_{TIMESTAMP}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"\n  manifest → {manifest_path.name}")

    print("\n" + "=" * 70)
    print("EXPERIMENT COMPLETE")
    print("=" * 70)
    print(f"  Raw Kling:  {KLING_OUT.relative_to(PROD_ROOT)}  ({dur:.2f}s)")
    print(f"  Lipsync:    {LIPSYNC_OUT.relative_to(PROD_ROOT)}")
    print(f"  vs baseline: animation_clips/beat_05_lipsync.mp4 (silcomp winner)")
    print(f"  Manifest:   {manifest_path.relative_to(PROD_ROOT)}")
    print()
    print(f"  Morning A/B checks:")
    print(f"    1. Raw Kling clip — does Tessa look at camera more consistently?")
    print(f"       Is mouth visible throughout all 10s?")
    print(f"    2. Lipsync output — is lipsync tighter than silcomp winner?")
    print(f"       Better phoneme matching on 'more careful'?")
    print(f"    3. Overall — does this look MORE natural than silcomp winner,")
    print(f"       or does cfg_scale=0.75 produce uncanny/frozen motion?")
    print()
    print(f"  If YES wins → promote this to live + amend Rule 8 via Directus.")
    print(f"  If NO or uncanny → revert, keep silcomp winner, close SHORTCUT")
    print(f"     decision as status=failed with lessons learned.")


if __name__ == "__main__":
    main()
