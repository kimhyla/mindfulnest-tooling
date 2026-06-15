#!/usr/bin/env python3
"""Backfill lipsync on existing beats with the bumped trailing-silence pad.

Approach:
  1. For each named beat, locate its Kling source (selected option) + audio.
  2. Submit to ByteDance LipSync via lipsync_sender.LipSyncClient — the new
     pad_audio_for_lipsync() will auto-apply the bumped 1.5s end pad (adaptive).
  3. Download result + replace beat_NN_lipsync.mp4 on disk.
  4. Bump beat._version in production_state.json so StoryboardTab cache busts.

Bypasses the running production_server.py — submits directly via lipsync_sender.
Safe to run while server is up; only writes to the on-disk MP4 + state.json.

Usage:
  python3 Production/scripts/backfill_lipsync_audio_pad.py --dry-run
  python3 Production/scripts/backfill_lipsync_audio_pad.py --beats beat_05
  python3 Production/scripts/backfill_lipsync_audio_pad.py --beats beat_03,beat_05,beat_17,beat_18

Cost: ~$0.15/beat ByteDance API. Default beat list = the 4 rolled-back beats.

Authority: LD pending LIPSYNC_TAIL_VIA_AUDIO_PAD_V1.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

_THIS = Path(__file__).resolve()
_TOOLS = _THIS.parent.parent / "tools"
sys.path.insert(0, str(_TOOLS))

PROJECT_ROOT = _THIS.parent.parent.parent
EVENT_DIR = PROJECT_ROOT / "Production" / "Event_1"
CLIPS_DIR = EVENT_DIR / "animation_clips"
STATE_PATH = EVENT_DIR / "production_state.json"
TTS_DIR = EVENT_DIR / "story_scene_tts_v2"

DEFAULT_BEATS = ["beat_03", "beat_05", "beat_17", "beat_18"]


def find_audio_for_beat(beat_id: str, state_audio_file: str | None) -> Path | None:
    """Locate the TTS audio file for a beat.

    PRIMARY: use state.audio_file (the canonical filename recorded at last
    lipsync time). Search TTS_DIR + the nested storyboard_v59_prod/.

    FALLBACK: glob match by line_NN_*.mp3 — but only used if state has no
    audio_file recorded. Excludes _archive_*, _tmp_*, *_preedit_* variants.

    DS-22 verify caller: check audio duration matches state's recorded
    `audio_duration_s` before submission — drift means the file has been
    overwritten and re-lipsync would use different audio than expected.
    """
    n = int(beat_id.split("_")[1])

    # PRIMARY: state-declared filename
    if state_audio_file:
        for root in (TTS_DIR, TTS_DIR / "storyboard_v59_prod"):
            p = root / state_audio_file
            if p.is_file():
                return p

    # FALLBACK: glob match
    candidates: list[Path] = []
    for root in (TTS_DIR, TTS_DIR / "storyboard_v59_prod"):
        if not root.is_dir():
            continue
        for f in root.glob(f"line_{n:02d}_*.mp3"):
            if any(s in f.name for s in ("_archive", "_tmp", "_preedit")):
                continue
            if any(p.name.startswith("_archive") for p in f.parents):
                continue
            candidates.append(f)
    if not candidates:
        return None
    canonical = [c for c in candidates if c.stem.count("_") == 2]
    if canonical:
        return canonical[0]
    return candidates[0]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--beats", default=",".join(DEFAULT_BEATS),
                    help=f"Comma-separated beat IDs (default: {','.join(DEFAULT_BEATS)})")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print planned actions without submitting to ByteDance")
    args = ap.parse_args()

    beat_ids = [b.strip() for b in args.beats.split(",") if b.strip()]

    if not STATE_PATH.is_file():
        print(f"FATAL: state.json not found at {STATE_PATH}")
        return 1
    state = json.loads(STATE_PATH.read_text())
    beats_map = ((state.get("videos") or {}).get("resolution") or {}).get("beats", {})

    # Locate API key — credentials module returns `wavespeed_key` (not _api_key)
    try:
        sys.path.insert(0, str(_TOOLS / "credentials_lib"))
        from credentials import load_credentials  # type: ignore
        creds = load_credentials()
        api_key = (
            creds.get("wavespeed_key")
            or creds.get("wavespeed_api_key")
            or os.environ.get("WAVESPEED_API_KEY")
        )
    except Exception as exc:  # noqa: BLE001
        print(f"WARN: credentials load failed: {exc}; falling back to env")
        api_key = os.environ.get("WAVESPEED_API_KEY")
    if not api_key and not args.dry_run:
        print("FATAL: WAVESPEED_API_KEY not available (need env var or credentials_lib)")
        return 1

    from lipsync_sender import LipSyncClient  # noqa: E402

    results = []

    for beat_id in beat_ids:
        beat = beats_map.get(beat_id)
        if not beat:
            print(f"[backfill] {beat_id}: NOT in state.json, skipping")
            results.append((beat_id, "missing_state"))
            continue

        # Source Kling option
        src_opt = ((beat.get("lipsync") or {}).get("source_option")
                   or (beat.get("phase_1") or {}).get("selected_option"))
        if not src_opt:
            print(f"[backfill] {beat_id}: no selected_option, skipping")
            results.append((beat_id, "no_option"))
            continue
        kling_path = CLIPS_DIR / f"{beat_id}_option_{int(src_opt)}.mp4"
        if not kling_path.is_file():
            print(f"[backfill] {beat_id}: Kling source missing: {kling_path.name}")
            results.append((beat_id, "no_kling"))
            continue

        # Audio file — PREFER state.audio_file (canonical at last lipsync)
        state_audio_file = beat.get("audio_file")
        state_audio_dur = beat.get("audio_duration_s")
        audio_path = find_audio_for_beat(beat_id, state_audio_file)
        if not audio_path or not audio_path.is_file():
            print(f"[backfill] {beat_id}: TTS audio not found "
                  f"(state.audio_file={state_audio_file!r})")
            results.append((beat_id, "no_audio"))
            continue

        # DS-22 audio-duration drift check: state vs disk. If they disagree
        # by >0.5s the file has been overwritten since last lipsync — skip
        # to avoid producing a lipsync from unintended audio.
        if state_audio_dur:
            try:
                probe = subprocess.run(
                    ["ffprobe", "-v", "error", "-show_entries",
                     "format=duration", "-of",
                     "default=noprint_wrappers=1:nokey=1", str(audio_path)],
                    capture_output=True, text=True, timeout=10,
                )
                disk_audio_dur = float((probe.stdout or "0").strip() or 0)
            except Exception:  # noqa: BLE001
                disk_audio_dur = 0.0
            if disk_audio_dur > 0 and abs(disk_audio_dur - state_audio_dur) > 0.5:
                print(f"[backfill] {beat_id}: SKIP audio drift "
                      f"(state={state_audio_dur:.2f}s vs disk={disk_audio_dur:.2f}s) "
                      f"file={audio_path.name}")
                results.append((beat_id, f"audio_drift_{disk_audio_dur:.2f}s_vs_state_{state_audio_dur:.2f}s"))
                continue

        # Verify backup exists before overwriting (sanity guard)
        dest = CLIPS_DIR / f"{beat_id}_lipsync.mp4"
        existing_backups = list(CLIPS_DIR.glob(f"_backup_{beat_id}_lipsync_pre_tail_*.mp4"))
        if not existing_backups:
            # Create a safety backup before re-lipsync overwrites
            safety_backup = CLIPS_DIR / f"_backup_{beat_id}_lipsync_pre_audpad_safety.mp4"
            if dest.is_file() and not safety_backup.is_file():
                shutil.copy2(dest, safety_backup)
                print(f"[backfill] {beat_id}: safety backup -> {safety_backup.name}")

        print(f"[backfill] {beat_id}: kling={kling_path.name} audio={audio_path.name}")
        if args.dry_run:
            results.append((beat_id, "dry_run"))
            continue

        # Submit + poll + download
        client = LipSyncClient(api_key)
        out = client.submit_and_wait(kling_path, audio_path, dest)
        if out.get("status") == "completed":
            print(f"[backfill] {beat_id}: COMPLETED {out.get('size_bytes')} bytes")
            # Bump _version so storyboard browser refetches
            beat["_version"] = int(beat.get("_version") or 0) + 1
            # Clear any stale tail_extension metadata from LD-724 era
            ls = beat.get("lipsync") or {}
            ls.pop("tail_extension", None)
            ls["size_bytes"] = out.get("size_bytes")
            ls["file"] = dest.name
            ls["status"] = "completed"
            results.append((beat_id, "completed"))
            # Persist state per beat so a mid-run failure doesn't lose progress
            STATE_PATH.write_text(json.dumps(state, indent=2))
        else:
            print(f"[backfill] {beat_id}: FAILED: {out}")
            results.append((beat_id, f"failed: {out.get('status')}"))

    print("\n=== SUMMARY ===")
    for bid, status in results:
        print(f"  {bid}: {status}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
