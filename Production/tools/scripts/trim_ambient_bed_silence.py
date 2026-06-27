#!/usr/bin/env python3
"""Trim leading/trailing silence from ambient bed MP3s using stitch probe logic.

Backs up originals as ``*.pre_trim_backup.mp3`` before overwriting.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from server_handlers.stitch_ambient_loop import probe_ambient_bed_active_span  # noqa: E402


def _ffprobe_duration_s(path: Path) -> float:
    out = subprocess.check_output(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "csv=p=0", str(path),
        ],
        text=True,
        timeout=15,
    ).strip()
    return float(out)


def trim_bed(path: Path, *, dry_run: bool = False) -> bool:
    if not path.is_file():
        print(f"skip (missing): {path}")
        return False
    file_dur_s = _ffprobe_duration_s(path)
    start_s, end_s = probe_ambient_bed_active_span(path, file_dur_s=file_dur_s)
    trim_head_s = max(0.0, start_s)
    trim_tail_s = max(0.0, file_dur_s - end_s)
    if trim_head_s < 0.05 and trim_tail_s < 0.05:
        print(f"ok (no trim needed): {path.name} ({file_dur_s:.2f}s)")
        return False
    out_dur_s = end_s - start_s
    print(
        f"trim {path.name}: {file_dur_s:.2f}s → {out_dur_s:.2f}s "
        f"(head {trim_head_s:.2f}s, tail {trim_tail_s:.2f}s)",
    )
    if dry_run:
        return True
    backup = path.with_suffix(".pre_trim_backup.mp3")
    if not backup.exists():
        shutil.copy2(path, backup)
        print(f"  backup: {backup.name}")
    tmp = path.with_suffix(".trim_tmp.mp3")
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(path),
        "-af", f"atrim=start={start_s}:end={end_s},asetpts=PTS-STARTPTS",
        "-codec:a", "libmp3lame", "-q:a", "2",
        str(tmp),
    ]
    subprocess.run(cmd, check=True, timeout=120)
    tmp.replace(path)
    print(f"  wrote: {path}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Trim ambient bed MP3 silence tails/heads.")
    parser.add_argument(
        "paths",
        nargs="*",
        help="MP3 paths (default: canonical Event_2 preset beds with known silence)",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.paths:
        targets = [Path(p) for p in args.paths]
    else:
        dropbox = Path.home() / (
            "Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files"
            "/Production/assets/sound_library/ambient"
        )
        targets = [
            dropbox / "ambien bed pretty option4.mp3",
            dropbox / "ambient bed pretty option2.mp3",
        ]
    changed = 0
    for p in targets:
        if trim_bed(p, dry_run=args.dry_run):
            changed += 1
    print(f"done: {changed} file(s) trimmed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
