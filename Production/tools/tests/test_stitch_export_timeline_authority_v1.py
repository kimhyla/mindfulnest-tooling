"""STITCH_EXPORT_TIMELINE_AUTHORITY_V1 — single timeline duration + cumulative drift gate."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS / "credentials_lib"))

from ffmpeg_stitch import (  # noqa: E402
    STITCH_EXPORT_TIMELINE_AUTHORITY_V1,
    assert_stitch_export_cumulative_av_aligned,
    export_clip_timeline_duration_s,
)


def test_marker_present() -> None:
    assert STITCH_EXPORT_TIMELINE_AUTHORITY_V1


def _make_av_clip(path: Path) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
            "-f", "lavfi", "-i", "color=c=black:s=320x240:d=2.00",
            "-shortest",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            str(path),
        ],
        check=True,
        capture_output=True,
        timeout=60,
    )


def test_export_clip_timeline_duration_positive(tmp_path: Path) -> None:
    clip = tmp_path / "c.mp4"
    _make_av_clip(clip)
    assert export_clip_timeline_duration_s(clip) > 0.5


def test_cumulative_gate_passes_aligned_clips(tmp_path: Path) -> None:
    a = tmp_path / "a.mp4"
    b = tmp_path / "b.mp4"
    _make_av_clip(a)
    _make_av_clip(b)
    assert_stitch_export_cumulative_av_aligned([a, b])
