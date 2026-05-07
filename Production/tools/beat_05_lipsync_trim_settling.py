#!/usr/bin/env python3
"""
beat_05_lipsync_trim_settling.py

Tests the "Kling settling window" hypothesis cheaply — no new Kling call.

Hypothesis (from F review):
  Kling's first ~0.5s of output is a ramp-up from the static input still.
  LatentSync can't track landmarks stably in that ramp-up window → no
  mouth stamp on "I'm sorry. I fell." which lands at video second ~0.5
  after ByteDance's own audio padding.

Fix: trim F's first 0.5s, re-lipsync. "I'm sorry" now lands at
video second ~0.5 of a trimmed clip that starts from F[0.5] (post-ramp-up,
full motion already underway).

Reuses F raw — no new Kling cost. $0.15 ByteDance lipsync only.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROD_ROOT = HERE.parent
EVENT_DIR = PROD_ROOT / "Event_1"
CLIPS_DIR = EVENT_DIR / "animation_clips"
TTS_DIR = EVENT_DIR / "story_scene_tts_v2"
PRESERVED = EVENT_DIR / "preserved_winners"

# F raw from the Strategy 2 run
F_RAW = CLIPS_DIR / "beat_05_option_F_kling_strat2_20260417-113105.mp4"
SILCOMP_AUDIO = TTS_DIR / "_tmp_line_05_tessa_silboth_20260417-034224.mp3"

# How much to trim off the front. 0.5s skips Kling's visible ramp-up.
TRIM_START_SECONDS = 0.5

TIMESTAMP = datetime.now().strftime("%Y%m%d-%H%M%S")
F_TRIMMED = CLIPS_DIR / f"_tmp_F_trimStart{TRIM_START_SECONDS}s_{TIMESTAMP}.mp4"
LIPSYNC_OUT = CLIPS_DIR / f"beat_05_lipsync_F_trimstart_{TIMESTAMP}.mp4"


def dur(p):
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


def load_api_key():
    if str(HERE) not in sys.path: sys.path.insert(0, str(HERE))
    import importlib.util
    spec = importlib.util.spec_from_file_location("_srv", HERE / "production_server.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod.parse_api_keys(PROD_ROOT / "API_KEYS_MASTER.md")["wavespeed"]


def main():
    print("=" * 70)
    print(f"beat_05 — TRIM-SETTLING FIX (trim {TRIM_START_SECONDS}s off F start)")
    print(f"  TS: {TIMESTAMP}")
    print("=" * 70)

    if not F_RAW.exists():
        sys.exit(f"FATAL: F raw not found: {F_RAW}")

    orig_dur = dur(F_RAW)
    audio_dur = dur(SILCOMP_AUDIO)
    print(f"\n  F raw:         {F_RAW.name}  ({orig_dur:.3f}s)")
    print(f"  silcomp audio: {SILCOMP_AUDIO.name}  ({audio_dur:.3f}s)")

    # Re-encode with precise start (stream-copy would round to keyframe)
    print(f"\n[1/3] Trim F raw front by {TRIM_START_SECONDS}s (re-encoded for precise cut)")
    ffmpeg_run([
        "ffmpeg","-hide_banner","-loglevel","error","-y",
        "-ss", f"{TRIM_START_SECONDS:.3f}",
        "-i", str(F_RAW),
        "-c:v","libx264","-preset","fast","-crf","18",
        "-c:a","aac","-b:a","128k","-movflags","+faststart",
        str(F_TRIMMED),
    ], "trim_start")
    trimmed_dur = dur(F_TRIMMED)
    tail_room = trimmed_dur - audio_dur
    print(f"  → {F_TRIMMED.name}  ({trimmed_dur:.3f}s)")
    print(f"  tail_room after audio ends = {tail_room:.3f}s (good if ≥ 0.4)")

    # Lipsync
    print(f"\n[2/3] Submit to ByteDance LipSync (fresh connection-per-poll)")
    sys.path.insert(0, str(HERE))
    from lipsync_sender import LipSyncClient
    client = LipSyncClient(load_api_key())
    t0 = time.time()
    ls = client.submit_and_wait(F_TRIMMED, SILCOMP_AUDIO, LIPSYNC_OUT)
    elapsed = time.time() - t0
    print(f"  lipsync done in {elapsed:.0f}s: {ls.get('status')}")
    if ls.get("status") != "completed":
        print(f"  WARN: {ls.get('error')}")
        sys.exit(1)

    # Preserve
    PRESERVED.mkdir(exist_ok=True)
    preserved = PRESERVED / LIPSYNC_OUT.name
    shutil.copy2(LIPSYNC_OUT, preserved)
    print(f"  [preserve] → {preserved.name}")

    # Open
    print(f"\n[3/3] Open for review")
    subprocess.run(["open","-a","QuickTime Player", str(LIPSYNC_OUT)])
    print(f"  → {LIPSYNC_OUT.name}  ({dur(LIPSYNC_OUT):.3f}s, "
          f"{ls['size_bytes']:,} bytes)")

    # Manifest
    manifest = {
        "ts": TIMESTAMP,
        "test": "trim_settling_window",
        "hypothesis": "Kling's first 0.5s is a ramp-up from static still; LatentSync can't stamp that window. Trimming front 0.5s should put 'I'm sorry' past the settling region.",
        "source_kling": F_RAW.name,
        "trim_start_s": TRIM_START_SECONDS,
        "trimmed_duration_s": trimmed_dur,
        "silcomp_audio": SILCOMP_AUDIO.name,
        "audio_duration_s": audio_dur,
        "tail_room_s": tail_room,
        "output": str(LIPSYNC_OUT.relative_to(PROD_ROOT).as_posix()),
        "output_size_bytes": ls["size_bytes"],
        "cost_usd": 0.15,
        "no_new_kling_call": True,
    }
    (EVENT_DIR / f"beat_05_trimsettling_manifest_{TIMESTAMP}.json").write_text(
        json.dumps(manifest, indent=2))

    print("\n" + "=" * 70)
    print("TRIM-SETTLING TEST COMPLETE")
    print("=" * 70)
    print(f"  Compare against:")
    print(f"    F (with settling): beat_05_lipsync_strat2_exp_20260417-113105.mp4")
    print(f"    B (live):          beat_05_lipsync.mp4")
    print(f"  New candidate:       {LIPSYNC_OUT.name}")
    print(f"  Critical listen: does 'I'm sorry. I fell.' lipsync now?")


if __name__ == "__main__":
    main()
