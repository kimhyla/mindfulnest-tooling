#!/usr/bin/env python3
"""
beat_05_lipsync_both_silences_experiment.py

Third experiment: apply the tail-room silence-compression treatment at BOTH
ends of the clip.

Previous (silence-compression) run: compressed only the 1.83s pause before
"I should have been more careful" → 0.80s. Result: tail phrase lipsynced
perfectly, but the START of the clip had off lipsync ("I'm sorry. I fell."
and/or the early portion).

Kim's instruction: apply the same treatment to the start.

Silence map (measured, -32dB / 150ms):
  0.50 → 0.71  (0.21s, short — leave alone)
  1.50 → 2.88  (1.38s pause after "I fell")       ← COMPRESS → 0.80s
  4.30 → 5.61  (1.30s pause in the middle)        ← leave as-is
  6.76 → 8.59  (1.83s pause before "I should...")  ← COMPRESS → 0.80s (proven)

After compression:
  Saved from first silence:  1.38 - 0.80 = 0.58s
  Saved from final silence:  1.83 - 0.80 = 1.03s
  Total saved:               1.61s
  New audio:                 9.88 - 1.61 = ~8.27s
  Video target:              8.7s (0.43s tail room, same as last successful run)

All spoken words preserved byte-identical. Only two pauses are shortened —
both to 0.80s. Middle pause (1.30s) left alone — if this run works, we have
our answer. If the start STILL lipsyncs off, next step is a new Kling clip.
"""

from __future__ import annotations

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

SOURCE_CLIP = CLIPS_DIR / "beat_05_option_2.mp4"
SOURCE_AUDIO = TTS_DIR / "line_05_tessa_trimmed.mp3"
CURRENT_LIPSYNC = CLIPS_DIR / "beat_05_lipsync.mp4"
# Also preserve the good-tail clip from the previous run
PREV_EXPERIMENT_RESULT = CLIPS_DIR / "beat_05_lipsync_silcomp_exp_20260417-032410.mp4"

# Silences to compress. Each tuple: (silence_start_s, silence_end_s, new_silence_dur_s)
# Measured at -32dB / 150ms detection threshold.
SILENCES_TO_COMPRESS = [
    (1.50, 2.88, 0.80),  # NEW: after "I fell"
    (6.76, 8.59, 0.80),  # previous run: before "I should have been more careful"
]

VIDEO_TRIM_SECONDS = 8.7

TIMESTAMP = datetime.now().strftime("%Y%m%d-%H%M%S")
TRIMMED_CLIP = CLIPS_DIR / f"_tmp_beat_05_option_B_trim{VIDEO_TRIM_SECONDS:.1f}s_{TIMESTAMP}.mp4"
COMPRESSED_AUDIO = TTS_DIR / f"_tmp_line_05_tessa_silboth_{TIMESTAMP}.mp3"
LIPSYNC_OUT = CLIPS_DIR / f"beat_05_lipsync_silboth_exp_{TIMESTAMP}.mp4"


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


def splice_audio_multi(src: Path, dst: Path,
                       silences: list[tuple[float, float, float]]) -> None:
    """Keep all speech; replace each specified silence region with a shorter
    synthesized silence. `silences` is a sorted-by-start list of
    (silence_start_s, silence_end_s, new_silence_dur_s) tuples.

    Concat order: [0..sil0_start] + silence(new0) + [sil0_end..sil1_start] +
                  silence(new1) + ... + [silN_end..audio_end]
    """
    if dst.exists():
        dst.unlink()

    # Build segment list
    parts: list[tuple[str, float, float | None, float | None]] = []
    # (kind, arg1, arg2 or None, arg3 or None)
    # kinds: "copy" (start, end), "silence" (duration, None)

    src_end = duration(src)
    prev_end = 0.0
    for s_start, s_end, s_new in silences:
        if s_start < prev_end:
            sys.exit(f"FATAL: silences overlap or unsorted at {s_start}")
        parts.append(("copy", prev_end, s_start, None))
        parts.append(("silence", s_new, None, None))
        prev_end = s_end
    parts.append(("copy", prev_end, src_end, None))

    scratch_dir = dst.parent
    segment_files: list[Path] = []

    for idx, (kind, a, b, _c) in enumerate(parts):
        out = scratch_dir / f"{dst.stem}._seg{idx:02d}.wav"
        if kind == "copy":
            ffmpeg_run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-ss", f"{a:.3f}", "-i", str(src),
                "-t", f"{(b - a):.3f}",
                "-ac", "1", "-ar", "44100",
                str(out),
            ], f"seg{idx}_copy")
        else:  # silence
            ffmpeg_run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
                "-t", f"{a:.3f}",
                "-ac", "1", "-ar", "44100",
                str(out),
            ], f"seg{idx}_silence")
        segment_files.append(out)

    concat_list = dst.with_suffix(".concat.txt")
    concat_list.write_text(
        "\n".join(f"file '{p}'" for p in segment_files) + "\n",
        encoding="utf-8",
    )
    ffmpeg_run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat_list),
        "-c:a", "libmp3lame", "-b:a", "192k",
        str(dst),
    ], "concat")

    for p in segment_files:
        try: p.unlink()
        except Exception: pass
    try: concat_list.unlink()
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


def preserve_current() -> None:
    PRESERVED.mkdir(exist_ok=True)
    # The "current" live clip
    if CURRENT_LIPSYNC.exists():
        dst = PRESERVED / f"beat_05_lipsync_pre_silboth_{TIMESTAMP}.mp4"
        shutil.copy2(CURRENT_LIPSYNC, dst)
        print(f"  [preserve] {CURRENT_LIPSYNC.name} → {dst.name}")
    # Also preserve the previous experiment's result so nothing is lost
    if PREV_EXPERIMENT_RESULT.exists():
        dst2 = PRESERVED / f"beat_05_lipsync_silcomp_GOOD_TAIL_{TIMESTAMP}.mp4"
        if not dst2.exists():
            shutil.copy2(PREV_EXPERIMENT_RESULT, dst2)
            print(f"  [preserve] {PREV_EXPERIMENT_RESULT.name} → {dst2.name}")


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
    print("beat_05 LipSync — compress BOTH big silences (start + end)")
    print(f"  TS: {TIMESTAMP}")
    print("=" * 70)

    for p in (SOURCE_CLIP, SOURCE_AUDIO):
        if not p.is_file():
            sys.exit(f"FATAL: missing input: {p}")
    src_audio_dur = duration(SOURCE_AUDIO)
    src_video_dur = duration(SOURCE_CLIP)
    print(f"  Input video: {SOURCE_CLIP.name}  ({src_video_dur:.3f}s)")
    print(f"  Input audio: {SOURCE_AUDIO.name}  ({src_audio_dur:.3f}s)")
    print(f"  Silences to compress:")
    for s_start, s_end, s_new in SILENCES_TO_COMPRESS:
        was = s_end - s_start
        print(f"    [{s_start:.2f} → {s_end:.2f}]  {was:.2f}s → {s_new:.2f}s "
              f"(saves {was - s_new:+.2f}s)")

    print("\n[1/5] Preserving current + prior experiment outputs")
    preserve_current()

    print(f"\n[2/5] Splicing audio (compress two silences, keep all words)")
    splice_audio_multi(SOURCE_AUDIO, COMPRESSED_AUDIO, SILENCES_TO_COMPRESS)
    new_audio_dur = duration(COMPRESSED_AUDIO)
    print(f"  → {COMPRESSED_AUDIO.name}  ({new_audio_dur:.3f}s, "
          f"saved {src_audio_dur - new_audio_dur:.3f}s total)")

    print(f"\n[3/5] Trimming video to {VIDEO_TRIM_SECONDS:.1f}s")
    trim_video(SOURCE_CLIP, TRIMMED_CLIP, VIDEO_TRIM_SECONDS)
    new_video_dur = duration(TRIMMED_CLIP)
    tail_room = new_video_dur - new_audio_dur
    print(f"  → {TRIMMED_CLIP.name}  ({new_video_dur:.3f}s)")
    print(f"  tail_room = {tail_room:.3f}s (should be ~0.4s for good lipsync)")

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
    print(f"  Output: {LIPSYNC_OUT.name}  ({duration(LIPSYNC_OUT):.3f}s, "
          f"{result['size_bytes']:,} bytes)")

    print(f"\n[5/5] Opening in QuickTime")
    subprocess.run(["open", "-a", "QuickTime Player", str(LIPSYNC_OUT)])

    print("\n" + "=" * 70)
    print("EXPERIMENT COMPLETE")
    print("=" * 70)
    print(f"  Result: {LIPSYNC_OUT.relative_to(PROD_ROOT)}")
    print()
    print("  Listen check:")
    print("    1. 'I'm sorry. I fell.' — do opening mouth movements sync?")
    print("    2. 'It's just been a long day.' — middle syncs?")
    print("    3. 'I should have been more careful.' — tail still syncs?")
    print("    4. Do the shortened pauses feel natural / emotionally right?")
    print()
    print("  If all four YES → Tier 4 pattern locks: pre-lipsync, compress any")
    print("     silence > 1.0s to 0.8s. Also: audio_duration + 0.4s tail_room =")
    print("     video trim target. Reusable across beats 6-11.")


if __name__ == "__main__":
    main()
