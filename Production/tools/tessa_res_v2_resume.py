#!/usr/bin/env python3
"""
tessa_res_v2_resume.py
Resume from step 5 (magic composite) using existing lipsync from TS=20260424-091358.
Lipsync output is valid (6.6s, 715184 bytes).
"""
from __future__ import annotations
import subprocess, sys, shutil, json, time
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

HERE      = Path(__file__).resolve().parent
PROD_ROOT = HERE.parent
EVENT_DIR = PROD_ROOT / "Event_1"
CLIPS_DIR = EVENT_DIR / "kling_clips"
STILLS    = EVENT_DIR / "resolution_stills"
PRESERVED = EVENT_DIR / "preserved_winners"

TS            = "20260424-091358"
STILL_PATH    = STILLS / "still_1_tessa_3q_rear_glow_v2.png"
LIPSYNC_RAW   = CLIPS_DIR / f"_tmp_res_lipsync_raw_{TS}.mp4"
OUTPUT_PATH   = CLIPS_DIR / "tessa_resolution_final_v9.mp4"
STITCH_PATH   = CLIPS_DIR / "beat02_event1_full_sequence_v1.mp4"

SCENE2_START, SCENE2_DUR = 9.0, 3.5
SCENE3_START, SCENE3_DUR = 12.5, 4.5
MAGIC_DURATION = 3.5

RES_PATH_PTS = [
    (0.30, 0.838), (0.44, 0.842), (0.57, 0.848),
    (0.70, 0.855), (0.83, 0.862), (0.96, 0.870),
]

NORM_W, NORM_H = 1280, 720

def log(msg):
    from datetime import datetime
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def ffmpeg_run(cmd, what):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"ffmpeg FAILED ({what}):\n{r.stderr[-2000:]}")
        sys.exit(1)

def duration_of(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True)
    return float(r.stdout.strip())

# ── [5/6] Magic per-frame composite ──────────────────────────────────────────
log("=" * 60)
log("RESUME from step 5: magic composite")
log(f"  lipsync: {LIPSYNC_RAW.name} ({LIPSYNC_RAW.stat().st_size:,} bytes)")

sys.path.insert(0, str(HERE))
from magic_compositor import MagicCompositor  # type: ignore

log("  Loading lipsync frames...")
raw_frames = list(iio.imiter(str(LIPSYNC_RAW)))
n_frames = len(raw_frames)

r = subprocess.run(
    ["ffprobe", "-v", "error", "-show_entries", "stream=r_frame_rate",
     "-of", "default=noprint_wrappers=1:nokey=1", str(LIPSYNC_RAW)],
    capture_output=True, text=True, check=True)
fps_str = r.stdout.strip().split("\n")[0]
num, den = (map(int, fps_str.split("/"))) if "/" in fps_str else (int(fps_str), 1)
video_fps = num / den
log(f"  {n_frames} frames @ {video_fps:.1f}fps ({n_frames/video_fps:.3f}s)")

mc = MagicCompositor(
    background_path=str(STILL_PATH),
    path_pts=RES_PATH_PTS,
    style="tessa_ori",
    duration=MAGIC_DURATION,
    fps=video_fps,
    seed=99,
)
mc.n_frames = n_frames

composited = []
for i, frame in enumerate(raw_frames):
    if frame.ndim == 3 and frame.shape[2] == 4:
        frame = frame[:, :, :3]
    if (frame.shape[1], frame.shape[0]) != (mc.W, mc.H):
        pil_f = Image.fromarray(frame).resize((mc.W, mc.H), Image.LANCZOS)
        frame = np.array(pil_f)
    trail  = mc._make_trail(i)
    result = np.clip(frame.astype(np.float32) + trail, 0, 255).astype(np.uint8)
    composited.append(result)
    if i % 24 == 0:
        log(f"    frame {i}/{n_frames}")

magic_scene1 = CLIPS_DIR / f"_tmp_res_scene1_magic_{TS}.mp4"
log(f"  Writing {len(composited)} composited frames...")
iio.imwrite(str(magic_scene1), np.stack(composited), plugin="pyav",
            codec="h264", fps=int(video_fps))
log(f"  magic_scene1 → {magic_scene1.name} ({magic_scene1.stat().st_size:,} bytes)")

# Re-add audio from lipsync to composited video
scene1_with_audio = CLIPS_DIR / f"_tmp_res_scene1_final_{TS}.mp4"
ffmpeg_run([
    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
    "-i", str(magic_scene1),
    "-i", str(LIPSYNC_RAW),
    "-map", "0:v", "-map", "1:a",
    "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
    "-movflags", "+faststart",
    str(scene1_with_audio),
], "add_audio_scene1")
log(f"  scene1+audio → {scene1_with_audio.name} ({duration_of(scene1_with_audio):.3f}s)")

# ── [6/6] Normalize + extract scenes 2+3 + stitch ────────────────────────────
log("\n[6/6] Normalize scene1 + extract scenes 2+3 + stitch")

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
log(f"  scene1 norm → {scene1_norm.name} ({duration_of(scene1_norm):.3f}s)")

scene2 = CLIPS_DIR / f"_tmp_res_s2_{TS}.mp4"
ffmpeg_run([
    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
    "-i", str(STITCH_PATH),
    "-ss", str(SCENE2_START), "-t", str(SCENE2_DUR),
    "-vf", f"scale={NORM_W}:{NORM_H}:flags=lanczos,fps=24",
    "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
    "-crf", "18", "-preset", "fast", "-an",
    "-movflags", "+faststart",
    str(scene2),
], "extract_scene2")
log(f"  scene2 → {scene2.name} ({duration_of(scene2):.3f}s)")

scene3 = CLIPS_DIR / f"_tmp_res_s3_{TS}.mp4"
ffmpeg_run([
    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
    "-i", str(STITCH_PATH),
    "-ss", str(SCENE3_START), "-t", str(SCENE3_DUR),
    "-vf", f"scale={NORM_W}:{NORM_H}:flags=lanczos,fps=24",
    "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
    "-crf", "18", "-preset", "fast", "-an",
    "-movflags", "+faststart",
    str(scene3),
], "extract_scene3")
log(f"  scene3 → {scene3.name} ({duration_of(scene3):.3f}s)")

total_dur = duration_of(scene1_norm) + SCENE2_DUR + SCENE3_DUR
log(f"  target total duration: {total_dur:.3f}s")

concat_list = CLIPS_DIR / f"_tmp_res_concat_{TS}.txt"
concat_list.write_text(
    f"file '{scene1_norm}'\nfile '{scene2}'\nfile '{scene3}'\n"
)

video_concat = CLIPS_DIR / f"_tmp_res_vconcat_{TS}.mp4"
ffmpeg_run([
    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
    "-f", "concat", "-safe", "0", "-i", str(concat_list),
    "-c:v", "copy", "-an",
    str(video_concat),
], "concat_video")
log(f"  video concat → {video_concat.name} ({duration_of(video_concat):.3f}s)")

# Mux audio (lipsync audio from scene1) + apad to full video length
ffmpeg_run([
    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
    "-i", str(video_concat),
    "-i", str(scene1_norm),
    "-filter_complex", f"[1:a]apad=whole_dur={total_dur:.3f}[aout]",
    "-map", "0:v", "-map", "[aout]",
    "-c:v", "copy",
    "-c:a", "aac", "-b:a", "128k", "-ac", "1", "-ar", "44100",
    "-movflags", "+faststart",
    str(OUTPUT_PATH),
], "mux_final")

final_dur  = duration_of(OUTPUT_PATH)
final_size = OUTPUT_PATH.stat().st_size
log(f"\n  ✓ OUTPUT → {OUTPUT_PATH.name}  ({final_dur:.3f}s, {final_size:,} bytes)")

shutil.copy2(OUTPUT_PATH, PRESERVED / OUTPUT_PATH.name)
log(f"  preserved → preserved_winners/{OUTPUT_PATH.name}")

# Cleanup
for f in [magic_scene1, scene1_with_audio, scene1_norm,
          scene2, scene3, video_concat, concat_list,
          CLIPS_DIR / f"_tmp_res_kling_raw_{TS}.mp4",
          CLIPS_DIR / f"_tmp_res_kling_trim_{TS}.mp4",
          CLIPS_DIR / f"_tmp_res_lipsync_raw_{TS}.mp4"]:
    try: Path(f).unlink(missing_ok=True)
    except Exception: pass

log("\n" + "=" * 60)
log("DONE — opening in QuickTime Player")
log("=" * 60)
log(f"  Checklist:")
log(f"  1. Scene 1: Tessa shell visible + glowing")
log(f"  2. Scene 1: Mouth syncs to dialogue")
log(f"  3. Scene 1: Gold sparkle trail at feet")
log(f"  4. Scene 2: Heartwood wide (from approved stitch)")
log(f"  5. Scene 3: Runestone (from approved stitch)")
log(f"  6. NO bop-bop-bop (apad silence)")
log(f"  7. NO Chinese watermark")
log(f"  8. NO phantom/double magic trail")

subprocess.run(["open", "-a", "QuickTime Player", str(OUTPUT_PATH)])
