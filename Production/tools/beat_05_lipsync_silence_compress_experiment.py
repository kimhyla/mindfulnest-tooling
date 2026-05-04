#!/usr/bin/env python3
"""
beat_05_lipsync_silence_compress_experiment.py

Second experiment: tail-room approach but WITHOUT losing any spoken words.

Previous experiment ("tailroom") truncated audio at 8.8s — cut mid-word in
"I should have been more careful." Middle syllables lipsync'd better
(tail-room hypothesis confirmed), but the phrase itself was lost.

Root observation via ffmpeg silencedetect:
  Current audio (9.883s):
    0.50 → 0.71  ( 0.21s pause after "I'm sorry")
    1.50 → 2.88  ( 1.38s pause after "I fell")
    4.30 → 5.61  ( 1.30s pause after "It's just been a long day")
    6.76 → 8.59  ( 1.83s pause before "I should have been more careful") ← biggest
  Total silence: 4.51s in a 9.88s file (~46% silence!)

Strategy: splice at silence boundaries, keep every spoken word identical,
shrink ONLY the 1.83s pause before the final phrase to 0.8s. Preserves
Tessa's delivery pace WITHIN phrases; reduces ONE dramatic pause by 1.03s.

Net result:
  - Audio 9.883s → ~8.85s (-1.03s)
  - Video 10.042s → 9.3s (trim 0.74s off the problematic tail-drift region)
  - Tail room = 9.3 - 8.85 = 0.45s (vs 0.16s in failed Option B attempt)
  - All spoken words preserved

Cost: $0.15 (one lipsync submit). No TTS regen, no Kling regen.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROD_ROOT = HERE.parent
EVENT_DIR = PROD_ROOT / "Event_1"
CLIPS_DIR = EVENT_DIR / "animation_clips"
TTS_DIR = EVENT_DIR / "story_scene_tts_v2"
PRESERVED = EVENT_DIR / "preserved_winners"

# Inputs
SOURCE_CLIP = CLIPS_DIR / "beat_05_option_2.mp4"   # Option B (10.04s)
SOURCE_AUDIO = TTS_DIR / "line_05_tessa_trimmed.mp3"  # 9.88s
CURRENT_LIPSYNC = CLIPS_DIR / "beat_05_lipsync.mp4"

# Silence plan (measured from ffmpeg silencedetect at -32dB / 150ms threshold)
# Only the LAST silence gets compressed — earlier pauses are kept at original
# length so Tessa's rhythm through "I'm sorry / I fell / long day" is intact.
FINAL_SILENCE_START = 6.76   # end of "long day"
FINAL_SILENCE_END   = 8.59   # start of "I should"
FINAL_SILENCE_NEW_DUR = 0.8  # was 1.83s; shrink to 0.8s (still a real pause)

VIDEO_TRIM_SECONDS = 9.3     # gives ~0.45s tail room after audio ends

# Outputs
TIMESTAMP = datetime.now().strftime("%Y%m%d-%H%M%S")
TRIMMED_CLIP = CLIPS_DIR / f"_tmp_beat_05_option_B_trim{VIDEO_TRIM_SECONDS:.1f}s_{TIMESTAMP}.mp4"
COMPRESSED_AUDIO = TTS_DIR / f"_tmp_line_05_tessa_silcomp_{TIMESTAMP}.mp3"
LIPSYNC_OUT = CLIPS_DIR / f"beat_05_lipsync_silcomp_exp_{TIMESTAMP}.mp4"


def duration(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(r.stdout.strip())


def ffmpeg_run(cmd: list[str], what: str) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"ffmpeg failed ({what}):")
        print(r.stderr[-2000:])
        sys.exit(1)


def splice_audio(src: Path, dst: Path,
                 cut_start: float, cut_end: float, replacement_silence: float) -> None:
    """Keep [0..cut_start], insert N seconds of silence, keep [cut_end..end]."""
    if dst.exists():
        dst.unlink()

    tmp_a = dst.with_suffix(".part1.wav")
    tmp_b = dst.with_suffix(".part2.wav")
    tmp_s = dst.with_suffix(".silence.wav")

    # Part 1: [0 .. cut_start]
    ffmpeg_run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(src), "-t", f"{cut_start:.3f}",
        "-ac", "1", "-ar", "44100",
        str(tmp_a),
    ], "part1")

    # Part 2: [cut_end .. end]
    ffmpeg_run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{cut_end:.3f}", "-i", str(src),
        "-ac", "1", "-ar", "44100",
        str(tmp_b),
    ], "part2")

    # Synthesized silence of replacement_silence duration
    ffmpeg_run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=mono",
        "-t", f"{replacement_silence:.3f}",
        "-ac", "1", "-ar", "44100",
        str(tmp_s),
    ], "silence")

    # Concat all three via concat demuxer
    concat_list = dst.with_suffix(".concat.txt")
    concat_list.write_text(
        f"file '{tmp_a}'\nfile '{tmp_s}'\nfile '{tmp_b}'\n",
        encoding="utf-8",
    )
    # Concat decodes then re-encodes to mp3 (not stream-copy — different inputs)
    ffmpeg_run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat_list),
        "-c:a", "libmp3lame", "-b:a", "192k",
        str(dst),
    ], "concat")

    # Cleanup scratch
    for p in (tmp_a, tmp_b, tmp_s, concat_list):
        try: p.unlink()
        except Exception: pass


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


def preserve_current() -> Path | None:
    if not CURRENT_LIPSYNC.exists():
        print(f"  [preserve] no current lipsync — skipping")
        return None
    PRESERVED.mkdir(exist_ok=True)
    dst = PRESERVED / f"beat_05_lipsync_pre_silcomp_{TIMESTAMP}.mp4"
    shutil.copy2(CURRENT_LIPSYNC, dst)
    print(f"  [preserve] {CURRENT_LIPSYNC.name} → preserved_winners/{dst.name}")
    return dst


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


def main() -> None:
    print("=" * 70)
    print("beat_05 LipSync Silence-Compression Experiment")
    print(f"  TS: {TIMESTAMP}")
    print("=" * 70)

    for p in (SOURCE_CLIP, SOURCE_AUDIO):
        if not p.is_file():
            sys.exit(f"FATAL: missing input: {p}")
    src_audio_dur = duration(SOURCE_AUDIO)
    src_video_dur = duration(SOURCE_CLIP)
    print(f"  Input video: {SOURCE_CLIP.name}  ({src_video_dur:.3f}s)")
    print(f"  Input audio: {SOURCE_AUDIO.name}  ({src_audio_dur:.3f}s)")
    print(f"  Final silence plan: [{FINAL_SILENCE_START:.2f}..{FINAL_SILENCE_END:.2f}] "
          f"= {FINAL_SILENCE_END - FINAL_SILENCE_START:.2f}s → {FINAL_SILENCE_NEW_DUR:.2f}s")

    # Step 1 — preserve current
    print("\n[1/5] Preserving current beat_05_lipsync.mp4")
    preserve_current()

    # Step 2 — splice audio: shorten the final pre-"I should" silence
    print(f"\n[2/5] Splicing audio (compress silence, keep all words)")
    splice_audio(SOURCE_AUDIO, COMPRESSED_AUDIO,
                 FINAL_SILENCE_START, FINAL_SILENCE_END, FINAL_SILENCE_NEW_DUR)
    new_audio_dur = duration(COMPRESSED_AUDIO)
    saved = src_audio_dur - new_audio_dur
    print(f"  → {COMPRESSED_AUDIO.name}  ({new_audio_dur:.3f}s, saved {saved:.3f}s)")

    # Step 3 — trim video
    print(f"\n[3/5] Trimming video to {VIDEO_TRIM_SECONDS:.1f}s")
    trim_video(SOURCE_CLIP, TRIMMED_CLIP, VIDEO_TRIM_SECONDS)
    new_video_dur = duration(TRIMMED_CLIP)
    print(f"  → {TRIMMED_CLIP.name}  ({new_video_dur:.3f}s)")
    tail_room = new_video_dur - new_audio_dur
    print(f"  tail_room = {tail_room:.3f}s (video continues after audio ends)")

    # Step 4 — submit lipsync
    print(f"\n[4/5] Submitting to ByteDance LipSync (WaveSpeed)")
    from lipsync_sender import LipSyncClient  # noqa: E402
    key = load_api_key()
    client = LipSyncClient(key)
    t0 = time.time()
    result = client.submit_and_wait(TRIMMED_CLIP, COMPRESSED_AUDIO, LIPSYNC_OUT)
    elapsed = time.time() - t0
    print(f"  Done in {elapsed:.1f}s: {result.get('status')}")
    if result.get("status") != "completed":
        print(f"  ERROR: {result.get('error')}")
        sys.exit(1)
    print(f"  Output: {LIPSYNC_OUT.name}  ({duration(LIPSYNC_OUT):.3f}s, {result['size_bytes']:,} bytes)")

    # Step 5 — open QuickTime
    print(f"\n[5/5] Opening result in QuickTime")
    subprocess.run(["open", "-a", "QuickTime Player", str(LIPSYNC_OUT)])

    print("\n" + "=" * 70)
    print("EXPERIMENT COMPLETE")
    print("=" * 70)
    print(f"  Result: {LIPSYNC_OUT.relative_to(PROD_ROOT)}")
    print()
    print("  Listen for:")
    print("    1. 'I should have been more careful' — did it lipsync all the way?")
    print("    2. The shortened pause before 'I should' — does it still feel natural?")
    print()
    print("  If BOTH yes → Tier 4 confirmed: pre-lipsync silence compression.")
    print("  If phrase drops again → mouth visibility in Option B tail is the")
    print("     real issue; generate a new Kling clip with mouth-centered prompt.")
    print("  If pause feels wrong → revert to 1.83s silence, try a different")
    print("     angle (regen Kling, or TTS speed regen).")


if __name__ == "__main__":
    main()
