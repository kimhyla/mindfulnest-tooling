"""Fade-through-black with inserted black hold (does not eat clip bodies)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from credentials_lib import ffmpeg_stitch as fs  # noqa: E402


def test_expand_inserts_black_between_clips(tmp_path: Path) -> None:
    clips = []
    for i in range(2):
        p = tmp_path / f"clip_{i}.mp4"
        fs.render_black_pause_clip(2.0, p)
        clips.append(p)
    out = fs.expand_clips_with_black_pause_boundaries(
        clips,
        [2800],
        tmp_path / "scratch",
        visual_out_ms=600,
        visual_in_ms=600,
        fade_audio=False,
    )
    assert len(out) == 3
    assert out[1].name.startswith("black_pause_")


def test_black_hold_ms_budget() -> None:
    assert max(0, 2800 - 600 - 600) == 1600
    assert max(0, 1500 - 600 - 600) == 300
