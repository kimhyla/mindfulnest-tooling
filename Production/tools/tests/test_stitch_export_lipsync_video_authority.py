#!/usr/bin/env python3
"""FF-040 — video-authority export norm + timeline for lipsync preservation."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS / "credentials_lib"))

from ffmpeg_stitch import (  # noqa: E402
    STITCH_EXPORT_LIPSYNC_VIDEO_AUTHORITY_V1,
    STITCH_EXPORT_NORM_AV_MAX_DRIFT_S,
    assert_stitch_export_clips_av_aligned,
    av_duration_drift_s,
    export_clip_timeline_duration_s,
    normalize_for_concat,
)


def _make_misaligned_clip(path: Path, *, video_s: float, audio_s: float) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"sine=frequency=440:duration={audio_s}",
            "-f", "lavfi", "-i", f"color=c=black:s=320x240:d={video_s}",
            "-shortest",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            str(path),
        ],
        check=True,
        capture_output=True,
        timeout=60,
    )


class LipsyncVideoAuthorityTests(unittest.TestCase):
    def test_markers_present(self):
        self.assertTrue(STITCH_EXPORT_LIPSYNC_VIDEO_AUTHORITY_V1)
        self.assertLessEqual(STITCH_EXPORT_NORM_AV_MAX_DRIFT_S, 0.02)

    def test_timeline_authority_prefers_video(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "misaligned.mp4"
            _make_misaligned_clip(src, video_s=2.0, audio_s=2.12)
            self.assertAlmostEqual(export_clip_timeline_duration_s(src), 2.0, delta=0.05)

    def test_normalize_locks_av_within_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src.mp4"
            dst = Path(tmp) / "norm.mp4"
            _make_misaligned_clip(src, video_s=2.0, audio_s=2.12)
            normalize_for_concat(src, dst)
            self.assertLessEqual(av_duration_drift_s(dst), STITCH_EXPORT_NORM_AV_MAX_DRIFT_S)
            assert_stitch_export_clips_av_aligned([dst])


if __name__ == "__main__":
    unittest.main()
