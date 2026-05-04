#!/usr/bin/env python3
"""audit_beat_durations.py — Audit MindfulNest beat animation vs audio durations.

Scans `production_state.json` for each beat's currently-selected animation clip,
ffprobes the clip's duration, ffprobes the matching TTS audio's duration, and
flags mismatches that would cause lipsync or visual-timing problems.

Context (April 16 2026): the `Regenerate B+C` code path historically defaulted
animation clips to 5 seconds regardless of audio length. `ANIMATION_DURATION_MATCHES_AUDIO`
(prod_locked_decisions id=144) now fixes the server. This audit tool catches
EXISTING clips that were generated under the old 5s default and flags them for
regeneration. The fix doesn't auto-invalidate completed clips, so Kim (or CI)
needs to run this audit to discover stale clips.

USAGE:
    # Read-only audit of Event_1:
    python3 Production/scripts/audit_beat_durations.py --event-dir Production/Event_1

    # Exit nonzero on any mismatch (for CI / pre-stitch blocking):
    python3 Production/scripts/audit_beat_durations.py --event-dir Production/Event_1 --strict

    # JSON output for programmatic consumption:
    python3 Production/scripts/audit_beat_durations.py --event-dir Production/Event_1 --json

VERDICT codes:
    OK          — clip duration within tolerance of audio duration
    STALE_5s    — clip is 5s but audio is > 4.5s; likely legacy bug → regenerate
    UNDER_TRIM  — clip shorter than audio but trim_end doesn't cover (video ends mid-speech)
    OVER_LONG   — clip longer than audio + padding (visual drags; consider trim_end)
    NO_AUDIO    — no matching TTS file; cannot audit
    NO_CLIP     — selected clip file on disk is missing; cannot audit
    UNSELECTED  — options exist but selected_option is None; Kim needs to pick
    AUDIO_OVER_KLING — audio exceeds Kling 10s max; CAN'T regenerate without editing script

Tier 3 companion: this script only READS state. It never mutates. Safe to run
while production_server is active.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


SHORT_AUDIO_THRESHOLD_SEC = 4.5  # matches _AUDIO_SHORT_THRESHOLD_SEC in production_server.py
KLING_MAX_DURATION_SEC = 10
CLIP_AUDIO_TOLERANCE_SEC = 0.6  # ± tolerance for OK verdict


def ffprobe_duration(path: Path) -> float | None:
    if not path.is_file():
        return None
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=10,
        )
        raw = r.stdout.strip()
        if not raw:
            return None
        return float(raw)
    except (FileNotFoundError, ValueError, subprocess.TimeoutExpired, OSError):
        return None


def find_beat_audio(event_dir: Path, beat_key: str) -> Path | None:
    """Mirror of production_server.py _find_beat_audio (same priority ladder)."""
    try:
        beat_num = int(beat_key.split("_")[1])
    except (IndexError, ValueError):
        return None
    tts_dir = event_dir / "story_scene_tts_v2"
    if not tts_dir.is_dir():
        return None
    candidates = [
        f for f in sorted(tts_dir.iterdir())
        if f.name.startswith(f"line_{beat_num:02d}_") and f.suffix == ".mp3"
    ]
    trimmed = [c for c in candidates if "trimmed" in c.name]
    regular = [c for c in candidates if "trim" not in c.name]
    trim5s = [c for c in candidates if "trim5s" in c.name]
    result = (trimmed or regular or trim5s or [None])[0]
    return result if (result and result.is_file()) else None


def verdict_for(audio_dur: float | None, clip_dur: float | None, trim_end: float | None) -> tuple[str, str]:
    """Return (verdict_code, human_reason)."""
    if audio_dur is None:
        return "NO_AUDIO", "no TTS audio found"
    if clip_dur is None:
        return "NO_CLIP", "selected clip file missing from disk"
    if audio_dur > KLING_MAX_DURATION_SEC:
        return "AUDIO_OVER_KLING", (
            f"audio {audio_dur:.2f}s exceeds Kling max {KLING_MAX_DURATION_SEC}s; "
            f"split audio or edit script — regeneration will fail until fixed"
        )
    effective_clip = min(clip_dur, trim_end) if trim_end is not None else clip_dur

    if abs(effective_clip - audio_dur) <= CLIP_AUDIO_TOLERANCE_SEC:
        return "OK", f"clip {effective_clip:.2f}s ≈ audio {audio_dur:.2f}s"
    if abs(clip_dur - 5.0) < 0.15 and audio_dur > SHORT_AUDIO_THRESHOLD_SEC:
        return "STALE_5s", (
            f"clip is 5.00s but audio is {audio_dur:.2f}s — legacy 5s-default bug; "
            f"regenerate this beat to get a 10s clip"
        )
    if effective_clip < audio_dur - CLIP_AUDIO_TOLERANCE_SEC:
        return "UNDER_TRIM", (
            f"effective clip {effective_clip:.2f}s shorter than audio {audio_dur:.2f}s — "
            f"video ends mid-speech"
        )
    if effective_clip > audio_dur + CLIP_AUDIO_TOLERANCE_SEC:
        return "OVER_LONG", (
            f"effective clip {effective_clip:.2f}s longer than audio {audio_dur:.2f}s — "
            f"consider setting trim_end to {audio_dur:.2f}"
        )
    return "OK", f"within tolerance"


def audit(event_dir: Path) -> list[dict]:
    state_path = event_dir / "production_state.json"
    if not state_path.exists():
        raise FileNotFoundError(f"production_state.json not found at {state_path}")
    state = json.loads(state_path.read_text())

    rows: list[dict] = []
    for beat_id, beat in sorted(state.get("beats", {}).items()):
        phase1 = beat.get("phase_1") or {}
        sel_idx = phase1.get("selected_option")
        options = phase1.get("options", [])
        trim_end = phase1.get("trim_end")

        selected_file = None
        unselected = False
        if sel_idx and 1 <= sel_idx <= len(options):
            selected_file = options[sel_idx - 1].get("file")
        elif options and sel_idx is None:
            # Phase 3 M3 fix (April 16 2026): distinguish "no pick yet" from "file missing"
            unselected = True

        clip_path = (event_dir / "animation_clips" / selected_file) if selected_file else None
        audio_path = find_beat_audio(event_dir, beat_id)

        audio_dur = ffprobe_duration(audio_path) if audio_path else None
        clip_dur = ffprobe_duration(clip_path) if clip_path else None

        if unselected:
            code, reason = "UNSELECTED", f"{len(options)} option(s) exist but selected_option is None — Kim needs to pick"
        else:
            code, reason = verdict_for(audio_dur, clip_dur, trim_end)
        rows.append({
            "beat_id": beat_id,
            "selected_option": sel_idx,
            "selected_file": selected_file,
            "clip_duration_s": round(clip_dur, 2) if clip_dur is not None else None,
            "audio_file": audio_path.name if audio_path else None,
            "audio_duration_s": round(audio_dur, 2) if audio_dur is not None else None,
            "trim_end": trim_end,
            "verdict": code,
            "reason": reason,
        })
    return rows


def print_table(rows: list[dict]) -> None:
    if not rows:
        print("No beats found.")
        return
    counts = {}
    for r in rows:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1

    # Column widths
    print(f"{'BEAT':9} {'VERDICT':16} {'CLIP':>7} {'AUDIO':>7} {'TRIM':>6}  REASON")
    print("-" * 110)
    for r in rows:
        clip = f"{r['clip_duration_s']}s" if r['clip_duration_s'] is not None else "-"
        audio = f"{r['audio_duration_s']}s" if r['audio_duration_s'] is not None else "-"
        trim = f"{r['trim_end']}" if r['trim_end'] is not None else "-"
        verdict_marker = {
            "OK": "✓",
            "STALE_5s": "⚠",
            "UNDER_TRIM": "✗",
            "OVER_LONG": "⚠",
            "NO_AUDIO": "?",
            "NO_CLIP": "?",
            "UNSELECTED": "◯",
            "AUDIO_OVER_KLING": "✗",
        }.get(r['verdict'], "?")
        verdict = f"{verdict_marker} {r['verdict']}"
        print(f"{r['beat_id']:9} {verdict:16} {clip:>7} {audio:>7} {trim:>6}  {r['reason']}")
    print("-" * 110)
    summary = "  ".join(f"{k}={v}" for k, v in sorted(counts.items()))
    print(f"Summary: {summary}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--event-dir", required=True, type=Path)
    p.add_argument("--strict", action="store_true",
                   help="Exit nonzero if any beat has a non-OK verdict")
    p.add_argument("--json", action="store_true",
                   help="Emit JSON instead of human-readable table")
    args = p.parse_args()

    if not args.event_dir.is_dir():
        print(f"[error] event_dir not found: {args.event_dir}", file=sys.stderr)
        return 2

    try:
        rows = audit(args.event_dir)
    except FileNotFoundError as e:
        print(f"[error] {e}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        print_table(rows)

    if args.strict:
        bad = [r for r in rows if r["verdict"] != "OK"]
        return 1 if bad else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
