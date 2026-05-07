#!/usr/bin/env python3
"""
tessa_res_v2_pipeline.py — Tessa resolution scene v2 production pipeline

Kim's clean-start solution (2026-04-24):
  still_1_tessa_3q_rear_glow_v2.png  (3/4 view, shell + face visible)
    → FLUX Kontext end frame
    → Kling v3.0 Pro 10s  (§8.2: cfg=0.5, no motion locks)
    → ByteDance lipsync with tessa_res_combined_v1.mp3  (all §8 safety rules)
    → magic_compositor.py tessa_ori per-frame composite on lipsync video
    → stitch: Scene1(lipsync+magic) + Scene2(heartwood) + Scene3(runestone)
    → output: tessa_resolution_final_v9.mp4

Root cause of v1-v8:
  Phantom magic — approved stitch had sparkles pre-baked; ByteDance smeared them;
  re-compositing on top = double trail.  §8.5 operation order violated.

Fixes:
  - Source: clean still, NO pre-existing magic  (§8.5: lipsync first, magic after)
  - Shell visible: 3/4 glow still shows the narrative payoff
  - Per-frame composite: magic laid directly over each lipsync frame (no ffmpeg blend)
  - Audio: apad extends lipsync audio over silent scenes 2+3  (no synthetic silence)
"""

from __future__ import annotations

import base64
import http.client
import io
import json
import os
import shutil
import ssl
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

try:
    from PIL import Image
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow", "-q"])
    from PIL import Image

try:
    import imageio.v3 as iio
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "imageio[ffmpeg]", "-q"])
    import imageio.v3 as iio

# ── Paths ─────────────────────────────────────────────────────────────────────
HERE      = Path(__file__).resolve().parent
PROD_ROOT = HERE.parent
EVENT_DIR = PROD_ROOT / "Event_1"
CLIPS_DIR = EVENT_DIR / "kling_clips"
TTS_DIR   = EVENT_DIR / "story_scene_tts"
STILLS    = EVENT_DIR / "resolution_stills"
PRESERVED = EVENT_DIR / "preserved_winners"
TEMP_IMG  = EVENT_DIR / "_temp_images"

STILL_PATH    = STILLS / "still_1_tessa_3q_rear_glow_v2.png"
AUDIO_PATH    = TTS_DIR / "tessa_res_combined_v1.mp3"
STITCH_PATH   = CLIPS_DIR / "beat02_event1_full_sequence_v1.mp4"
OUTPUT_PATH   = CLIPS_DIR / "tessa_resolution_final_v9.mp4"

# Scene timestamps in approved stitch (17.04s total)
SCENE2_START = 9.0    # heartwood wide magic start
SCENE2_DUR   = 3.5    # heartwood wide duration
SCENE3_START = 12.5   # runestone activation start
SCENE3_DUR   = 4.5    # runestone duration

# Magic trail path — calibrated for still_1_tessa_3q_rear_glow_v2.png
# Tessa's feet are ~x=0.44, y=0.83. Trail departs right along forest floor.
RES_PATH_PTS = [
    (0.30, 0.838),
    (0.44, 0.842),
    (0.57, 0.848),
    (0.70, 0.855),
    (0.83, 0.862),
    (0.96, 0.870),
]

MAGIC_DURATION = 3.5   # seconds of visible trail (§8.5: trail appears and departs)

# Rule 8 compliance constants
CFG_SCALE       = 0.5
RULE8_NEGATIVES = (
    "lip sync, speaking, talking, mouth movement, dialogue, "
    "speech, open mouth, Chinese, audio, voice, singing"
)

# ── Logging ───────────────────────────────────────────────────────────────────
def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def ffmpeg_run(cmd: list[str], what: str) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"ffmpeg failed ({what}):\n{r.stderr[-2000:]}")
        sys.exit(1)


def duration_of(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(r.stdout.strip())


# ── API keys ──────────────────────────────────────────────────────────────────
def load_api_keys() -> dict:
    """Load keys via production_server.parse_api_keys (avoids wavespeed URL bug)."""
    spec_path = HERE / "production_server.py"
    import importlib.util, re
    spec = importlib.util.spec_from_file_location("_ps", spec_path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    keys = mod.parse_api_keys(PROD_ROOT / "API_KEYS_MASTER.md")
    content = (PROD_ROOT / "API_KEYS_MASTER.md").read_text("utf-8")
    m = re.search(r"\|\s*\*+(?:Flux|BFL|Black\s*Forest)[^|]*\*+[^|]*\|\s*`([^`]+)`",
                  content, re.IGNORECASE)
    if m:
        keys["bfl"] = m.group(1).strip()
    if not keys.get("wavespeed"):
        sys.exit("FATAL: no wavespeed key")
    if not keys.get("bfl"):
        sys.exit("FATAL: no BFL key")
    log(f"  keys loaded: wavespeed=...{keys['wavespeed'][-6:]}, bfl=...{keys['bfl'][-6:]}")
    return keys


# ── Robust HTTPS (fresh connection per attempt, no stuck state) ───────────────
def robust_https(host, path, method="GET", headers=None, body=None,
                 timeout=90, retries=3) -> tuple[int, bytes]:
    headers = headers or {}
    last_exc = None
    for attempt in range(retries):
        try:
            ctx = ssl.create_default_context()
            ctx.options |= ssl.OP_NO_TICKET | ssl.OP_NO_COMPRESSION
            conn = http.client.HTTPSConnection(host, timeout=timeout, context=ctx)
            try:
                h = dict(headers)
                if body and "Content-Length" not in h:
                    h["Content-Length"] = str(len(body))
                conn.request(method, path, body=body, headers=h)
                resp = conn.getresponse()
                raw  = resp.read()
                status = resp.status
            finally:
                conn.close()
            if status < 400:
                return status, raw
            if status >= 500:
                last_exc = Exception(f"HTTP {status}: {raw[:200].decode('utf-8','replace')}")
                log(f"  {method} {path[:40]} attempt {attempt+1}/{retries}: HTTP {status}")
            else:
                return status, raw
        except (TimeoutError, http.client.HTTPException, OSError) as exc:
            last_exc = exc
            log(f"  {method} {path[:40]} attempt {attempt+1}/{retries}: {exc}")
        if attempt < retries - 1:
            time.sleep(3 * (3 ** attempt))
    raise last_exc or Exception("robust_https exhausted retries")


# ── FLUX Kontext end-frame generation ─────────────────────────────────────────
BFL_SUBMIT  = "/v1/flux-kontext-pro"
BFL_RESULT  = "/v1/get_result"


def generate_end_frame(start_bytes: bytes, end_prompt: str, api_key: str) -> bytes:
    b64 = base64.b64encode(start_bytes).decode("ascii")
    body = json.dumps({
        "prompt": end_prompt,
        "input_image": b64,
        "aspect_ratio": "4:3",
        "output_format": "png",
        "safety_tolerance": 2,
    }).encode("utf-8")
    log(f"  → POST BFL Kontext ({len(start_bytes):,}B)")
    status, raw = robust_https(
        "api.bfl.ai", BFL_SUBMIT, "POST",
        {"x-key": api_key, "Content-Type": "application/json"}, body,
    )
    if status >= 400:
        sys.exit(f"BFL submit HTTP {status}: {raw[:300].decode('utf-8','replace')}")
    result = json.loads(raw.decode("utf-8"))
    task_id  = result.get("id")
    poll_url = result.get("polling_url") or f"https://api.bfl.ai{BFL_RESULT}?id={task_id}"
    log(f"  BFL task_id={task_id}")

    import urllib.parse as up
    pu = up.urlparse(poll_url)
    poll_path = pu.path + ("?" + pu.query if pu.query else "")
    t0 = time.time()
    while time.time() - t0 < 180:
        try:
            ps, pr = robust_https("api.bfl.ai", poll_path, "GET",
                                  {"x-key": api_key}, retries=1)
            if ps >= 400:
                time.sleep(5); continue
            pr_json = json.loads(pr.decode("utf-8"))
        except Exception as e:
            log(f"  BFL poll err: {e}"); time.sleep(5); continue
        st = (pr_json.get("status") or "").strip()
        log(f"  BFL t+{int(time.time()-t0):3d}s status={st}")
        if st == "Ready":
            sample = (pr_json.get("result") or {}).get("sample")
            if not sample:
                sys.exit(f"BFL Ready but no sample: {pr_json}")
            import urllib.request as ureq
            for _ in range(3):
                try:
                    with ureq.urlopen(sample, timeout=60) as r:
                        return r.read()
                except Exception as e:
                    log(f"  BFL download err: {e}"); time.sleep(3)
            sys.exit("BFL download failed after 3 attempts")
        if st in ("Error", "Failed", "Task not found"):
            sys.exit(f"BFL failed: {pr_json}")
        time.sleep(3)
    sys.exit("BFL timed out after 180s")


# ── Kling v3.0 Pro start-end submission ───────────────────────────────────────
def kling_submit(start_uri: str, end_uri: str, prompt: str, duration: int,
                 api_key: str) -> str:
    payload = {
        "image": start_uri,
        "end_image": end_uri,
        "prompt": prompt,
        "negative_prompt": RULE8_NEGATIVES,
        "duration": duration,
        "cfg_scale": CFG_SCALE,
        "sound": False,
    }
    body = json.dumps(payload).encode("utf-8")
    status, raw = robust_https(
        "api.wavespeed.ai",
        "/api/v3/kwaivgi/kling-v3.0-pro/image-to-video",
        "POST",
        {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        body,
    )
    if status >= 400:
        sys.exit(f"Kling submit HTTP {status}: {raw[:400].decode('utf-8','replace')}")
    result = json.loads(raw.decode("utf-8"))
    task_id = (result.get("data", {}).get("id") or result.get("id") or result.get("task_id"))
    if not task_id:
        sys.exit(f"Kling submit returned no task_id: {result}")
    return task_id


def kling_poll(task_id: str, api_key: str, timeout_s: int = 900) -> dict:
    path = f"/api/v3/predictions/{task_id}/result"
    t0 = time.time()
    last_st = None
    while time.time() - t0 < timeout_s:
        try:
            ctx = ssl.create_default_context()
            ctx.options |= ssl.OP_NO_TICKET | ssl.OP_NO_COMPRESSION
            conn = http.client.HTTPSConnection("api.wavespeed.ai", timeout=20, context=ctx)
            try:
                conn.request("GET", path, headers={"Authorization": f"Bearer {api_key}"})
                resp = conn.getresponse()
                data = json.loads(resp.read().decode("utf-8","replace")).get("data", {})
            finally:
                conn.close()
            st = (data.get("status") or "").lower()
            if st != last_st:
                log(f"  Kling t+{int(time.time()-t0):3d}s status={st}")
                last_st = st
            if st in ("completed", "failed", "error"):
                return data
        except Exception as e:
            log(f"  Kling poll err: {e}")
        time.sleep(5)
    return {"status": "timeout"}


# ── Rule 6: auto-upscale if shortest side < 600px ────────────────────────────
def ensure_min_size(img_bytes: bytes) -> tuple[bytes, str]:
    img = Image.open(io.BytesIO(img_bytes))
    w, h = img.size
    if min(w, h) >= 600:
        return img_bytes, f"OK {w}x{h}"
    scale = 800 / min(w, h)
    new_w, new_h = int(w * scale), int(h * scale)
    up = img.resize((new_w, new_h), Image.LANCZOS)
    buf = io.BytesIO()
    up.save(buf, "PNG")
    return buf.getvalue(), f"upscaled {w}x{h}→{new_w}x{new_h}"


# ── Magic per-frame composite ─────────────────────────────────────────────────
def composite_magic_over_video(lipsync_path: Path, still_path: Path,
                                path_pts: list, magic_dur: float,
                                output_path: Path) -> None:
    """
    Per-frame magic composite over lipsync video.

    Uses MagicCompositor for particle placement + brightness calibration
    (using the source still).  Each lipsync frame is then composited
    directly — no ffmpeg blend, no yuv420p purple artifact.

    Magic trail is rendered only for the first `magic_dur` seconds,
    then fades.  Remaining frames get lipsync video as-is.
    """
    sys.path.insert(0, str(HERE))
    from magic_compositor import MagicCompositor  # type: ignore

    # Load lipsync video frames (resize to still dimensions for consistent composite)
    log("  Loading lipsync frames...")
    raw_frames = list(iio.imiter(str(lipsync_path)))
    n_frames = len(raw_frames)

    # Determine fps from video
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=r_frame_rate",
         "-of", "default=noprint_wrappers=1:nokey=1", str(lipsync_path)],
        capture_output=True, text=True, check=True,
    )
    fps_str = r.stdout.strip().split("\n")[0]
    num, den = map(int, fps_str.split("/")) if "/" in fps_str else (int(fps_str), 1)
    video_fps = num / den
    log(f"  Lipsync: {n_frames} frames @ {video_fps:.1f}fps "
        f"({n_frames/video_fps:.3f}s)")

    # Init compositor with still (for calibration + particle layout)
    mc = MagicCompositor(
        background_path=str(still_path),
        path_pts=path_pts,
        style="tessa_ori",
        duration=magic_dur,
        fps=video_fps,
        seed=99,
    )
    # Override n_frames to exactly match the lipsync video
    mc.n_frames = n_frames

    # Composite each frame
    composited = []
    for i, frame in enumerate(raw_frames):
        if frame.shape[2] == 4:               # drop alpha if present
            frame = frame[:, :, :3]
        if (frame.shape[1], frame.shape[0]) != (mc.W, mc.H):
            pil_frame = Image.fromarray(frame).resize((mc.W, mc.H), Image.LANCZOS)
            frame = np.array(pil_frame)
        trail = mc._make_trail(i)
        bg    = frame.astype(np.float32)
        result = np.clip(bg + trail, 0, 255).astype(np.uint8)
        composited.append(result)
        if i % 12 == 0:
            log(f"    frame {i}/{n_frames}")

    # Write composited video (no audio — audio added in final stitch)
    log(f"  Writing composited video → {output_path.name}")
    iio.imwrite(str(output_path), composited, plugin="pyav", codec="h264",
                fps=int(video_fps))
    log(f"  Done: {output_path.stat().st_size:,} bytes")


# ── Main pipeline ─────────────────────────────────────────────────────────────
def main() -> None:
    TS = datetime.now().strftime("%Y%m%d-%H%M%S")
    PRESERVED.mkdir(exist_ok=True)
    TEMP_IMG.mkdir(exist_ok=True)

    log("=" * 70)
    log("TESSA RESOLUTION V2 PIPELINE")
    log(f"  TS: {TS}")
    log(f"  Source still: {STILL_PATH.name}")
    log(f"  Audio: {AUDIO_PATH.name}")
    log(f"  §8.5: lipsync first, magic after — no pre-existing sparkles")
    log("=" * 70)

    if not STILL_PATH.is_file():
        sys.exit(f"FATAL: still not found: {STILL_PATH}")
    if not AUDIO_PATH.is_file():
        sys.exit(f"FATAL: audio not found: {AUDIO_PATH}")
    if not STITCH_PATH.is_file():
        sys.exit(f"FATAL: approved stitch not found: {STITCH_PATH}")

    keys = load_api_keys()

    # ── [1/6] Load start image ─────────────────────────────────────────────
    log("\n[1/6] Load start still + Rule 6 upscale check")
    start_bytes = STILL_PATH.read_bytes()
    start_bytes, start_info = ensure_min_size(start_bytes)
    log(f"  start frame: {start_info}")

    # ── [2/6] Generate FLUX Kontext end frame ─────────────────────────────
    log("\n[2/6] Generate end frame via FLUX Kontext (§8.3 start-end pipeline)")
    end_prompt = (
        "Same character (Tessa the cartoon 3D turtle), same outfit, same glowing shell, "
        "same forest background, same 3/4 rear-facing pose, same art style and lighting. "
        "Tessa turns her head very slightly more toward camera — eyes wide with happy "
        "surprise, small smile expression. Shell still glowing. "
        "Mouth closed, no speech. Beak at rest, silent. Same 4:3 framing."
    )
    log(f"  end_prompt: {end_prompt[:120]}...")
    end_bytes = generate_end_frame(start_bytes, end_prompt, keys["bfl"])
    end_bytes, end_info = ensure_min_size(end_bytes)
    log(f"  end frame: {end_info}")

    end_frame_path = TEMP_IMG / f"_tmp_res_end_frame_{TS}.png"
    end_frame_path.write_bytes(end_bytes)
    shutil.copy2(end_frame_path, PRESERVED / end_frame_path.name)
    log(f"  saved end frame → {end_frame_path.name}")

    # ── [3/6] Kling v3.0 Pro start-end ───────────────────────────────────
    log("\n[3/6] Submit to Kling v3.0 Pro (start-end, §8.2 compliant)")
    positive_prompt = (
        "A small cartoon 3D turtle (Tessa) in a misty forest clearing, "
        "glowing shell visible, 3/4 rear-facing view. Soft ambient light. "
        "Natural idle movement, no speech. Beak closed. Silent."
    )
    log(f"  positive: {positive_prompt[:80]}...")
    log(f"  negative: {RULE8_NEGATIVES[:80]}...")
    log(f"  cfg_scale={CFG_SCALE}, duration=10s, sound=False")

    start_uri = f"data:image/png;base64,{base64.b64encode(start_bytes).decode()}"
    end_uri   = f"data:image/png;base64,{base64.b64encode(end_bytes).decode()}"

    kling_task_id = kling_submit(start_uri, end_uri, positive_prompt, 10, keys["wavespeed"])
    log(f"  kling_task_id: {kling_task_id}")

    result = kling_poll(kling_task_id, keys["wavespeed"])
    if result.get("status") != "completed":
        sys.exit(f"FATAL: Kling failed: {result}")
    clip_url = (result.get("outputs") or [None])[0]
    if not clip_url:
        sys.exit(f"FATAL: Kling completed but no URL: {result}")

    raw_kling = CLIPS_DIR / f"_tmp_res_kling_raw_{TS}.mp4"
    subprocess.run(["curl", "-sSL", "-o", str(raw_kling), clip_url],
                   check=True, capture_output=True, timeout=180)
    raw_dur = duration_of(raw_kling)
    shutil.copy2(raw_kling, PRESERVED / raw_kling.name)
    log(f"  raw Kling → {raw_kling.name} ({raw_dur:.3f}s, "
        f"{raw_kling.stat().st_size:,} bytes)")

    # ── [4/6] ByteDance lipsync (all §8 safety rules) ─────────────────────
    log("\n[4/6] ByteDance lipsync (§8.1 + §8.4 + §8.5)")

    audio_dur = duration_of(AUDIO_PATH)
    log(f"  audio: {AUDIO_PATH.name} ({audio_dur:.3f}s)")

    # §8.5 routing check: 5.6s audio, no gap >1s → direct submit path
    if audio_dur > 10.0:
        sys.exit(f"FATAL: audio {audio_dur:.2f}s > §8.5 10s ceiling")
    log(f"  §8.5 check: {audio_dur:.2f}s ≤ 10s, direct submit path")

    # Trim Kling to audio_dur + 0.4s tail room (§8.3 pattern)
    trim_to = min(audio_dur + 0.4, raw_dur)
    trimmed_kling = CLIPS_DIR / f"_tmp_res_kling_trim_{TS}.mp4"
    ffmpeg_run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(raw_kling), "-t", f"{trim_to:.3f}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-an", "-movflags", "+faststart",
        str(trimmed_kling),
    ], "trim_kling")
    log(f"  trimmed Kling → {trimmed_kling.name} ({duration_of(trimmed_kling):.3f}s)")

    # Submit lipsync (lipsync_sender.py handles §8.4 padding + §8.5 duration guard)
    sys.path.insert(0, str(HERE))
    from lipsync_sender import LipSyncClient  # type: ignore
    lipsync_raw = CLIPS_DIR / f"_tmp_res_lipsync_raw_{TS}.mp4"
    client = LipSyncClient(keys["wavespeed"])
    t0 = time.time()
    ls_result = client.submit_and_wait(trimmed_kling, AUDIO_PATH, lipsync_raw)
    if ls_result.get("status") != "completed":
        sys.exit(f"FATAL: lipsync failed: {ls_result.get('error')}")
    shutil.copy2(lipsync_raw, PRESERVED / lipsync_raw.name)
    log(f"  lipsync done in {time.time()-t0:.0f}s → {lipsync_raw.name} "
        f"({duration_of(lipsync_raw):.3f}s, {ls_result['size_bytes']:,} bytes)")

    # ── [5/6] Per-frame magic composite ───────────────────────────────────
    log("\n[5/6] Magic composite: tessa_ori trail over lipsync frames")
    log(f"  path_pts: {RES_PATH_PTS}")
    log(f"  magic_duration: {MAGIC_DURATION}s")
    log(f"  Using §8.5 operation order: lipsync done FIRST, magic on top NOW")

    magic_scene1 = CLIPS_DIR / f"_tmp_res_scene1_magic_{TS}.mp4"
    composite_magic_over_video(
        lipsync_path=lipsync_raw,
        still_path=STILL_PATH,
        path_pts=RES_PATH_PTS,
        magic_dur=MAGIC_DURATION,
        output_path=magic_scene1,
    )
    # Re-add audio from lipsync to the composited video
    scene1_with_audio = CLIPS_DIR / f"_tmp_res_scene1_final_{TS}.mp4"
    ffmpeg_run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(magic_scene1),        # composited video (no audio)
        "-i", str(lipsync_raw),         # audio source
        "-map", "0:v", "-map", "1:a",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(scene1_with_audio),
    ], "add_audio_to_scene1")
    log(f"  scene1 with audio → {scene1_with_audio.name} "
        f"({duration_of(scene1_with_audio):.3f}s)")

    # ── [6/6] Extract scenes 2+3 + stitch ─────────────────────────────────
    log("\n[6/6] Extract scenes 2+3 from approved stitch + normalize + concat")

    scene1_dur = duration_of(scene1_with_audio)

    # Normalize scene1 to canonical codec (LD-284: H.264/yuv420p/24fps/AAC)
    NORM_W, NORM_H = 1280, 720
    scene1_norm = CLIPS_DIR / f"_tmp_res_s1_norm_{TS}.mp4"
    ffmpeg_run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(scene1_with_audio),
        "-vf", f"scale={NORM_W}:{NORM_H}:flags=lanczos,fps=24",
        "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
        "-crf", "18", "-preset", "fast",
        "-c:a", "aac", "-b:a", "128k", "-ac", "1", "-ar", "44100",
        "-movflags", "+faststart",
        str(scene1_norm),
    ], "normalize_scene1")
    log(f"  scene1 normalized → {scene1_norm.name} ({duration_of(scene1_norm):.3f}s)")

    # Extract scene 2 (heartwood wide, video-only from approved stitch)
    scene2 = CLIPS_DIR / f"_tmp_res_s2_{TS}.mp4"
    ffmpeg_run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(STITCH_PATH),
        "-ss", str(SCENE2_START), "-t", str(SCENE2_DUR),
        "-vf", f"scale={NORM_W}:{NORM_H}:flags=lanczos,fps=24",
        "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
        "-crf", "18", "-preset", "fast",
        "-an",   # no audio (approved stitch has no audio track)
        "-movflags", "+faststart",
        str(scene2),
    ], "extract_scene2")
    log(f"  scene2 extracted → {scene2.name} ({duration_of(scene2):.3f}s)")

    # Extract scene 3 (runestone, video-only)
    scene3 = CLIPS_DIR / f"_tmp_res_s3_{TS}.mp4"
    ffmpeg_run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(STITCH_PATH),
        "-ss", str(SCENE3_START), "-t", str(SCENE3_DUR),
        "-vf", f"scale={NORM_W}:{NORM_H}:flags=lanczos,fps=24",
        "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
        "-crf", "18", "-preset", "fast",
        "-an",
        "-movflags", "+faststart",
        str(scene3),
    ], "extract_scene3")
    log(f"  scene3 extracted → {scene3.name} ({duration_of(scene3):.3f}s)")

    # Stitch all three scenes.
    # Audio: scene1 has lipsync audio. Scenes 2+3 are silent.
    # Use apad to extend audio to full video duration (no synthetic silence,
    # no AAC boundary artifacts — apad uses same codec state as input audio).
    total_dur = duration_of(scene1_norm) + SCENE2_DUR + SCENE3_DUR

    concat_list = CLIPS_DIR / f"_tmp_res_concat_{TS}.txt"
    concat_list.write_text(
        f"file '{scene1_norm}'\nfile '{scene2}'\nfile '{scene3}'\n"
    )

    # First: concat video streams only (all three, no audio)
    video_concat = CLIPS_DIR / f"_tmp_res_vconcat_{TS}.mp4"
    ffmpeg_run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat_list),
        "-c:v", "copy", "-an",
        str(video_concat),
    ], "concat_video")
    log(f"  video concat → {video_concat.name} ({duration_of(video_concat):.3f}s)")

    # Then: mux audio from scene1 + apad to full video duration
    ffmpeg_run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(video_concat),
        "-i", str(scene1_norm),
        "-filter_complex",
        f"[1:a]apad=whole_dur={total_dur:.3f}[aout]",
        "-map", "0:v", "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "128k", "-ac", "1", "-ar", "44100",
        "-movflags", "+faststart",
        str(OUTPUT_PATH),
    ], "mux_final")

    final_dur  = duration_of(OUTPUT_PATH)
    final_size = OUTPUT_PATH.stat().st_size
    log(f"\n  ✓ OUTPUT → {OUTPUT_PATH.name}  ({final_dur:.3f}s, {final_size:,} bytes)")

    # Preserve
    preserved_out = PRESERVED / OUTPUT_PATH.name
    shutil.copy2(OUTPUT_PATH, preserved_out)
    log(f"  preserved → preserved_winners/{OUTPUT_PATH.name}")

    # Cleanup temp files
    for f in [concat_list, raw_kling, trimmed_kling, lipsync_raw,
              magic_scene1, scene1_with_audio, scene1_norm, scene2,
              scene3, video_concat, end_frame_path]:
        try:
            Path(f).unlink(missing_ok=True)
        except Exception:
            pass

    log("\n" + "=" * 70)
    log("TESSA RESOLUTION V2 PIPELINE COMPLETE")
    log("=" * 70)
    log(f"  Output:    Event_1/kling_clips/{OUTPUT_PATH.name}")
    log(f"  Duration:  {final_dur:.3f}s")
    log(f"  Size:      {final_size:,} bytes")
    log(f"  Cost:      ~$0.08 (BFL) + ~$0.45 (Kling) + ~$0.15 (lipsync) = ~$0.68")
    log(f"\n  Playback checklist:")
    log(f"    1. Scene 1: Tessa shell VISIBLE (3/4 view, glowing)")
    log(f"    2. Scene 1: Mouth syncs to 'Wow your magic worked...'")
    log(f"    3. Scene 1: Gold sparkle trail visible at Tessa's feet")
    log(f"    4. Scene 2: Heartwood wide, magic intact (from approved stitch)")
    log(f"    5. Scene 3: Runestone activation (from approved stitch)")
    log(f"    6. Audio: no bop-bop-bop in scenes 2+3 (apad silence)")
    log(f"    7. No Chinese watermark anywhere")
    log(f"    8. No phantom/double magic trail")

    subprocess.run(["open", "-a", "QuickTime Player", str(OUTPUT_PATH)])


if __name__ == "__main__":
    main()
