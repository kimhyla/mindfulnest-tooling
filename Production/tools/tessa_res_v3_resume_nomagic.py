#!/usr/bin/env python3
"""
tessa_res_v3_resume_nomagic.py

Resume from preserved v3 lipsync (noglow Tessa).
Scene 1 = clean lipsync ONLY, no magic composite.
Magic is already pre-baked in scenes 2+3 from the approved stitch.
"""
import subprocess, sys, shutil
from pathlib import Path

HERE      = Path(__file__).resolve().parent
PROD_ROOT = HERE.parent
EVENT_DIR = PROD_ROOT / "Event_1"
CLIPS_DIR = EVENT_DIR / "kling_clips"
PRESERVED = EVENT_DIR / "preserved_winners"
STITCH    = CLIPS_DIR / "beat02_event1_full_sequence_v1.mp4"

TS             = "20260424-094756"
LIPSYNC_RAW    = PRESERVED / f"_tmp_res_v3_lipsync_raw_{TS}.mp4"
OUTPUT_PATH    = CLIPS_DIR / "tessa_resolution_final_v11.mp4"

SCENE2_START, SCENE2_DUR = 9.0, 3.5
SCENE3_START, SCENE3_DUR = 12.5, 4.5
NORM_W, NORM_H = 1280, 720

from datetime import datetime
def log(m): print(f"[{datetime.now().strftime('%H:%M:%S')}] {m}", flush=True)

def ffmpeg_run(cmd, what):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"ffmpeg FAILED ({what}):\n{r.stderr[-2000:]}")
        sys.exit(1)

def duration_of(p):
    r = subprocess.run(
        ["ffprobe","-v","error","-show_entries","format=duration",
         "-of","default=noprint_wrappers=1:nokey=1",str(p)],
        capture_output=True, text=True, check=True)
    return float(r.stdout.strip())

log("=" * 60)
log("RESUME v3 — Scene 1: clean lipsync, NO magic composite")
log(f"  lipsync: {LIPSYNC_RAW.name} ({LIPSYNC_RAW.stat().st_size:,} bytes)")
log("=" * 60)

# Normalize scene 1 (no magic — just clean noglow lipsync)
scene1_norm = CLIPS_DIR / f"_tmp_res_v3nm_s1_{TS}.mp4"
ffmpeg_run([
    "ffmpeg","-hide_banner","-loglevel","error","-y",
    "-i", str(LIPSYNC_RAW),
    "-vf", f"scale={NORM_W}:{NORM_H}:flags=lanczos,fps=24",
    "-c:v","libx264","-profile:v","high","-pix_fmt","yuv420p",
    "-crf","18","-preset","fast",
    "-c:a","aac","-b:a","128k","-ac","1","-ar","44100",
    "-movflags","+faststart",
    str(scene1_norm),
], "normalize_scene1")
log(f"  scene1 norm → {scene1_norm.name} ({duration_of(scene1_norm):.3f}s)")

# Extract scene 2
scene2 = CLIPS_DIR / f"_tmp_res_v3nm_s2_{TS}.mp4"
ffmpeg_run([
    "ffmpeg","-hide_banner","-loglevel","error","-y",
    "-i", str(STITCH),
    "-ss",str(SCENE2_START),"-t",str(SCENE2_DUR),
    "-vf",f"scale={NORM_W}:{NORM_H}:flags=lanczos,fps=24",
    "-c:v","libx264","-profile:v","high","-pix_fmt","yuv420p",
    "-crf","18","-preset","fast","-an","-movflags","+faststart",
    str(scene2),
], "extract_scene2")
log(f"  scene2 → {scene2.name} ({duration_of(scene2):.3f}s)")

# Extract scene 3
scene3 = CLIPS_DIR / f"_tmp_res_v3nm_s3_{TS}.mp4"
ffmpeg_run([
    "ffmpeg","-hide_banner","-loglevel","error","-y",
    "-i", str(STITCH),
    "-ss",str(SCENE3_START),"-t",str(SCENE3_DUR),
    "-vf",f"scale={NORM_W}:{NORM_H}:flags=lanczos,fps=24",
    "-c:v","libx264","-profile:v","high","-pix_fmt","yuv420p",
    "-crf","18","-preset","fast","-an","-movflags","+faststart",
    str(scene3),
], "extract_scene3")
log(f"  scene3 → {scene3.name} ({duration_of(scene3):.3f}s)")

total_dur = duration_of(scene1_norm) + SCENE2_DUR + SCENE3_DUR
log(f"  total: {total_dur:.3f}s")

concat_list = CLIPS_DIR / f"_tmp_res_v3nm_concat_{TS}.txt"
concat_list.write_text(f"file '{scene1_norm}'\nfile '{scene2}'\nfile '{scene3}'\n")

video_concat = CLIPS_DIR / f"_tmp_res_v3nm_vconcat_{TS}.mp4"
ffmpeg_run([
    "ffmpeg","-hide_banner","-loglevel","error","-y",
    "-f","concat","-safe","0","-i",str(concat_list),
    "-c:v","copy","-an", str(video_concat),
], "concat_video")

ffmpeg_run([
    "ffmpeg","-hide_banner","-loglevel","error","-y",
    "-i", str(video_concat),
    "-i", str(scene1_norm),
    "-filter_complex", f"[1:a]apad=whole_dur={total_dur:.3f}[aout]",
    "-map","0:v","-map","[aout]",
    "-c:v","copy","-c:a","aac","-b:a","128k","-ac","1","-ar","44100",
    "-movflags","+faststart",
    str(OUTPUT_PATH),
], "mux_final")

final_dur  = duration_of(OUTPUT_PATH)
final_size = OUTPUT_PATH.stat().st_size
log(f"\n  ✓ OUTPUT → {OUTPUT_PATH.name}  ({final_dur:.3f}s, {final_size:,} bytes)")

shutil.copy2(OUTPUT_PATH, PRESERVED / OUTPUT_PATH.name)
log(f"  preserved → preserved_winners/{OUTPUT_PATH.name}")

for f in [scene1_norm, scene2, scene3, video_concat, concat_list]:
    try: Path(f).unlink(missing_ok=True)
    except: pass

log("\nDONE")
subprocess.run(["open","-a","QuickTime Player", str(OUTPUT_PATH)])
