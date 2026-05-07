#!/usr/bin/env python3
"""
beat_05_lipsync_trim_both.py

Double-trim fix: trim both front AND back of F raw so ByteDance sees only
F's good middle frames. Same 8.7s total length as the original F run
(which had tail working via freeze-extension) but starting 0.5s later
(skips the settling window that broke the opening).

F raw is 10.04s.
Cut: F[0.5 → 9.2s] = 8.7s.
  - Front 0.5s skipped → avoids Kling settling window → opening works
  - Back 0.84s skipped → avoids any tail drift → ByteDance freeze-extends
    F[9.2] (same pattern as the original successful F run, which froze
    F[8.7])

Cost: $0.15 lipsync. No new Kling call.
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

F_RAW = CLIPS_DIR / "beat_05_option_F_kling_strat2_20260417-113105.mp4"
SILCOMP_AUDIO = TTS_DIR / "_tmp_line_05_tessa_silboth_20260417-034224.mp3"

TRIM_START_S = 0.5
DURATION_S   = 8.7   # same as original F full-run; ByteDance freeze-extends

TIMESTAMP = datetime.now().strftime("%Y%m%d-%H%M%S")
F_TRIMMED = CLIPS_DIR / f"_tmp_F_trimBoth_{TRIM_START_S}s-{TRIM_START_S + DURATION_S}s_{TIMESTAMP}.mp4"
LIPSYNC_OUT = CLIPS_DIR / f"beat_05_lipsync_F_trimboth_{TIMESTAMP}.mp4"


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
    print(f"beat_05 — DOUBLE TRIM FIX: F[{TRIM_START_S}s → {TRIM_START_S+DURATION_S}s]")
    print(f"  TS: {TIMESTAMP}")
    print("=" * 70)

    if not F_RAW.exists():
        sys.exit(f"FATAL: F raw not found: {F_RAW}")

    print(f"\n  F raw:         {F_RAW.name}  ({dur(F_RAW):.3f}s)")
    print(f"  silcomp audio: {SILCOMP_AUDIO.name}  ({dur(SILCOMP_AUDIO):.3f}s)")
    print(f"  Trim plan:     F[{TRIM_START_S:.1f} → {TRIM_START_S+DURATION_S:.1f}] = {DURATION_S:.1f}s")
    print(f"  ByteDance will freeze-extend last frame for ~0.57s (matching original F run)")

    print(f"\n[1/3] Trim F raw to middle {DURATION_S:.1f}s (skip settling AND tail drift)")
    ffmpeg_run([
        "ffmpeg","-hide_banner","-loglevel","error","-y",
        "-ss", f"{TRIM_START_S:.3f}",
        "-i", str(F_RAW),
        "-t", f"{DURATION_S:.3f}",
        "-c:v","libx264","-preset","fast","-crf","18",
        "-c:a","aac","-b:a","128k","-movflags","+faststart",
        str(F_TRIMMED),
    ], "trim_both")
    trimmed_dur = dur(F_TRIMMED)
    print(f"  → {F_TRIMMED.name}  ({trimmed_dur:.3f}s)")

    print(f"\n[2/3] Submit to ByteDance LipSync")
    sys.path.insert(0, str(HERE))
    from lipsync_sender import LipSyncClient
    client = LipSyncClient(load_api_key())
    t0 = time.time()
    ls = client.submit_and_wait(F_TRIMMED, SILCOMP_AUDIO, LIPSYNC_OUT)
    elapsed = time.time() - t0
    print(f"  lipsync done in {elapsed:.0f}s: {ls.get('status')}")
    if ls.get("status") != "completed":
        sys.exit(f"FATAL: {ls.get('error')}")

    PRESERVED.mkdir(exist_ok=True)
    shutil.copy2(LIPSYNC_OUT, PRESERVED / LIPSYNC_OUT.name)
    print(f"  [preserve] → {LIPSYNC_OUT.name}")

    print(f"\n[3/3] Open for review")
    subprocess.run(["open","-a","QuickTime Player", str(LIPSYNC_OUT)])
    print(f"  → {LIPSYNC_OUT.name}  ({dur(LIPSYNC_OUT):.3f}s, {ls['size_bytes']:,} bytes)")

    # Manifest
    (EVENT_DIR / f"beat_05_trimboth_manifest_{TIMESTAMP}.json").write_text(json.dumps({
        "ts": TIMESTAMP,
        "test": "double_trim_front_and_back",
        "hypothesis": "Front trim fixes opening (past Kling settling), same 8.7s length forces ByteDance to freeze-extend tail (same pattern as original successful F tail)",
        "source_kling": F_RAW.name,
        "trim_start_s": TRIM_START_S,
        "trim_end_s": TRIM_START_S + DURATION_S,
        "trimmed_duration_s": trimmed_dur,
        "silcomp_audio": SILCOMP_AUDIO.name,
        "output": str(LIPSYNC_OUT.relative_to(PROD_ROOT).as_posix()),
        "output_size_bytes": ls["size_bytes"],
        "cost_usd": 0.15,
    }, indent=2))

    print("\n" + "=" * 70)
    print("DOUBLE-TRIM TEST COMPLETE")
    print("=" * 70)
    print(f"  Compare against:")
    print(f"    Full F (bad open):      beat_05_lipsync_strat2_exp_20260417-113105.mp4")
    print(f"    F front-trim (bad tail): beat_05_lipsync_F_trimstart_20260417-122122.mp4")
    print(f"    B (live):               beat_05_lipsync.mp4")
    print(f"  New candidate:            {LIPSYNC_OUT.name}")
    print(f"  Listen for:")
    print(f"    1. 'I'm sorry. I fell.' — should lipsync (like trimstart test)")
    print(f"    2. 'I should have been more careful' — should lipsync (like original F)")


if __name__ == "__main__":
    main()
