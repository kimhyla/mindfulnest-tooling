#!/usr/bin/env python3
"""
beat_05_lipsync_video_tailroom_experiment.py

One-shot diagnostic: test the "ByteDance needs clean mouth-visible frames at
the video tail to stamp the last phonemes" hypothesis for beat_05.

Context (April 17 2026):
Option B and Option C lipsyncs both dropped "I should have been more careful"
at the tail of beat_05. Both source clips are 10.04s; audio is 9.88s; lipsync
outputs are 10.88s (ByteDance adds ~0.84s freeze-frame tail padding).

Hypothesis: the last ~1s of the 10s Kling clip has subtle head/angle drift
that obscures the mouth enough that ByteDance can't stamp "more careful" onto
it. Fix: trim the SOURCE VIDEO to 9.0s so the mouth-visible portion covers
the full audio duration, trim the audio to 8.8s for 0.2s of video run-out.

What this script does:
  1. Preserves the current beat_05_lipsync.mp4 (Option C result) to preserved_winners/
  2. Trims Option B clip (beat_05_option_2.mp4) 10.04s → 9.0s via ffmpeg
  3. Trims the TTS audio (line_05_tessa_trimmed.mp3) 9.88s → 8.8s via ffmpeg
  4. Submits video+audio to ByteDance LipSync (WaveSpeed)
  5. Downloads result to animation_clips/beat_05_lipsync_tailroom_exp_<TS>.mp4
     (does NOT overwrite the live beat_05_lipsync.mp4 — preserves Option C for A/B)
  6. Opens the new output in QuickTime for Kim's review

If this succeeds → we have a clean Tier 4 fix for Kling 10s clips.
If it fails → the mouth-visibility issue is structural; need a new Kling
clip with explicit mouth-centered prompt.

Cost: ~$0.15 (one lipsync submit).
Does NOT touch production_state.json — the current Option C lipsync remains
the "live" one until Kim picks this one.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Paths relative to Production/ root
HERE = Path(__file__).resolve().parent
PROD_ROOT = HERE.parent
EVENT_DIR = PROD_ROOT / "Event_1"
CLIPS_DIR = EVENT_DIR / "animation_clips"
TTS_DIR = EVENT_DIR / "story_scene_tts_v2"
PRESERVED = EVENT_DIR / "preserved_winners"

# Inputs
SOURCE_CLIP = CLIPS_DIR / "beat_05_option_2.mp4"   # Option B (10.04s)
SOURCE_AUDIO = TTS_DIR / "line_05_tessa_trimmed.mp3"  # 9.88s
CURRENT_LIPSYNC = CLIPS_DIR / "beat_05_lipsync.mp4"   # Option C result (to preserve)

# Trim targets
VIDEO_TRIM_SECONDS = 9.0   # shorter than 10.04 so the mouth-drift tail is removed
AUDIO_TRIM_SECONDS = 8.8   # 0.2s of video run-out after audio ends

# Outputs
TIMESTAMP = datetime.now().strftime("%Y%m%d-%H%M%S")
TRIMMED_CLIP = CLIPS_DIR / f"_tmp_beat_05_option_B_trim{VIDEO_TRIM_SECONDS:.1f}s_{TIMESTAMP}.mp4"
TRIMMED_AUDIO = TTS_DIR / f"_tmp_line_05_tessa_trim{AUDIO_TRIM_SECONDS:.1f}s_{TIMESTAMP}.mp3"
LIPSYNC_OUT = CLIPS_DIR / f"beat_05_lipsync_tailroom_exp_{TIMESTAMP}.mp4"


def duration(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(r.stdout.strip())


def ffmpeg_trim(src: Path, dst: Path, seconds: float) -> None:
    """Trim to `seconds` from start. For video, re-encodes to ensure precise
    cut on keyframe boundaries. For audio, uses -c copy (mp3 cut is precise enough).
    """
    if dst.exists():
        dst.unlink()

    if src.suffix.lower() in (".mp4", ".mov", ".webm"):
        # Re-encode video for precise cut (stream copy rounds to keyframes)
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(src),
            "-t", f"{seconds:.3f}",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            str(dst),
        ]
    else:
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(src),
            "-t", f"{seconds:.3f}",
            "-c", "copy",
            str(dst),
        ]

    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("ffmpeg failed:\n", r.stderr)
        sys.exit(1)


def preserve_current() -> Path | None:
    """Back up the current beat_05_lipsync.mp4 (Option C result) so we
    don't lose it when the experiment runs."""
    if not CURRENT_LIPSYNC.exists():
        print(f"  [preserve] no current lipsync at {CURRENT_LIPSYNC.name} — nothing to preserve")
        return None
    PRESERVED.mkdir(exist_ok=True)
    dst = PRESERVED / f"beat_05_lipsync_optC_pre_tailroom_exp_{TIMESTAMP}.mp4"
    shutil.copy2(CURRENT_LIPSYNC, dst)
    print(f"  [preserve] {CURRENT_LIPSYNC.name} → preserved_winners/{dst.name}")
    return dst


def load_api_key() -> str:
    """Read WaveSpeed API key from the master credentials doc.

    Uses production_server.parse_api_keys (NOT lib/credentials.load_credentials)
    because the latter has a known bug where multiple "WaveSpeed" rows in
    API_KEYS_MASTER.md (the real key + Kling endpoint URLs) produce a
    last-match-wins collision that overwrites the key with an endpoint URL.
    parse_api_keys is the canonical parser already used at server startup.
    """
    # Import production_server's parser directly.
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    # Avoid triggering production_server's __main__ block — just grab the fn.
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_prod_server_import", HERE / "production_server.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore
    keys = mod.parse_api_keys(PROD_ROOT / "API_KEYS_MASTER.md")
    key = keys.get("wavespeed")
    if not key:
        print(f"FATAL: no wavespeed key parsed (got: {sorted(keys.keys())})")
        sys.exit(1)
    return key


def main() -> None:
    print("=" * 70)
    print("beat_05 LipSync Tail-Room Experiment")
    print(f"  TS: {TIMESTAMP}")
    print("=" * 70)

    # Step 0 — sanity check inputs exist
    for p in (SOURCE_CLIP, SOURCE_AUDIO):
        if not p.is_file():
            print(f"FATAL: missing input: {p}")
            sys.exit(1)
    print(f"  Input video: {SOURCE_CLIP.name}  ({duration(SOURCE_CLIP):.3f}s)")
    print(f"  Input audio: {SOURCE_AUDIO.name}  ({duration(SOURCE_AUDIO):.3f}s)")

    # Step 1 — preserve current lipsync
    print("\n[1/5] Preserving current beat_05_lipsync.mp4 (Option C)")
    preserve_current()

    # Step 2 — trim source video
    print(f"\n[2/5] Trimming video to {VIDEO_TRIM_SECONDS:.1f}s")
    ffmpeg_trim(SOURCE_CLIP, TRIMMED_CLIP, VIDEO_TRIM_SECONDS)
    actual_v = duration(TRIMMED_CLIP)
    print(f"  → {TRIMMED_CLIP.name}  ({actual_v:.3f}s)")

    # Step 3 — trim source audio
    print(f"\n[3/5] Trimming audio to {AUDIO_TRIM_SECONDS:.1f}s")
    ffmpeg_trim(SOURCE_AUDIO, TRIMMED_AUDIO, AUDIO_TRIM_SECONDS)
    actual_a = duration(TRIMMED_AUDIO)
    print(f"  → {TRIMMED_AUDIO.name}  ({actual_a:.3f}s)")

    # Step 4 — submit to ByteDance LipSync
    print(f"\n[4/5] Submitting to ByteDance LipSync (WaveSpeed)")
    print(f"  video_tail_room = {actual_v - actual_a:.3f}s after audio ends")
    from lipsync_sender import LipSyncClient  # noqa: E402
    key = load_api_key()
    client = LipSyncClient(key)

    t0 = time.time()
    result = client.submit_and_wait(TRIMMED_CLIP, TRIMMED_AUDIO, LIPSYNC_OUT)
    elapsed = time.time() - t0
    print(f"  Done in {elapsed:.1f}s: {result.get('status')}")
    if result.get("status") != "completed":
        print(f"  ERROR: {result.get('error')}")
        sys.exit(1)
    print(f"  Output: {LIPSYNC_OUT.name}  ({duration(LIPSYNC_OUT):.3f}s, {result['size_bytes']:,} bytes)")

    # Step 5 — open in QuickTime (per locked decision)
    print(f"\n[5/5] Opening result in QuickTime for review")
    subprocess.run(["open", "-a", "QuickTime Player", str(LIPSYNC_OUT)])

    print("\n" + "=" * 70)
    print("EXPERIMENT COMPLETE")
    print("=" * 70)
    print(f"  Result: {LIPSYNC_OUT.relative_to(PROD_ROOT)}")
    print(f"  Old (Option C, preserved): preserved_winners/beat_05_lipsync_optC_pre_tailroom_exp_{TIMESTAMP}.mp4")
    print()
    print("  Listen for: 'I should have been more careful' at the tail.")
    print("  If lipsync now reaches that phrase → Tier 4 fix: trim video to")
    print("     (audio_duration + 0.2s) before submitting any lipsync.")
    print("  If still dropped → mouth visibility in Option B's tail frames")
    print("     is the real issue; we need a new Kling clip with explicit")
    print("     mouth-centered prompt.")
    print()
    print("  Temp files left in place for inspection:")
    print(f"    {TRIMMED_CLIP.relative_to(PROD_ROOT)}")
    print(f"    {TRIMMED_AUDIO.relative_to(PROD_ROOT)}")
    print("  (Safe to delete after review.)")


if __name__ == "__main__":
    main()
