"""STITCH_MP4_PLAYBACK_TIMESTAMPS_V1 — QuickTime-safe non-negative video DTS."""

from __future__ import annotations

import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from credentials_lib import ffmpeg_stitch as fs  # noqa: E402


def test_remux_clears_negative_video_dts(tmp_path: Path) -> None:
    src = tmp_path / "src.mp4"
    fs.render_black_pause_clip(2.0, src)
    # Simulate concat-style negative DTS by remux without avoid_negative_ts from two clips.
    mid = tmp_path / "mid.mp4"
    fs.render_black_pause_clip(2.0, mid)
    bad = tmp_path / "bad.mp4"
    fs.concat_with_xfade_clips([src, mid], bad)
    dts_before = fs.mp4_first_video_dts_s(bad)
    assert dts_before is not None
    fs.normalize_mp4_browser_playback_timeline(bad)
    dts_after = fs.mp4_first_video_dts_s(bad)
    assert dts_after is not None
    assert fs.mp4_operator_playback_timestamps_safe(bad)
    assert dts_after >= -0.001
