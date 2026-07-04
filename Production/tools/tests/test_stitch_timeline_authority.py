#!/usr/bin/env python3
"""STITCH_EXPORT_TIMELINE_AUTHORITY_V1 — dissolve + boundary SFX A/V alignment."""
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
    STITCH_EXPORT_NORM_AV_MAX_DRIFT_S,
    STITCH_EXPORT_TIMELINE_AUTHORITY_V1,
    av_duration_drift_s,
    remux_mp4_video_timeline_authority,
    trim_body_with_fade,
)


def _make_misaligned_clip(path: Path, *, video_s: float, audio_s: float) -> None:
    """Mux unequal stream lengths (no -shortest) to simulate dissolve/overlay drift."""
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"color=c=black:s=320x240:d={video_s}",
            "-f", "lavfi", "-i", f"sine=frequency=440:duration={audio_s}",
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            str(path),
        ],
        check=True,
        capture_output=True,
        timeout=60,
    )


class StitchTimelineAuthorityTests(unittest.TestCase):
    def test_marker_present(self):
        self.assertTrue(STITCH_EXPORT_TIMELINE_AUTHORITY_V1)

    def test_remux_heals_misaligned_clip(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "misaligned.mp4"
            _make_misaligned_clip(src, video_s=2.0, audio_s=2.15)
            self.assertGreater(av_duration_drift_s(src), STITCH_EXPORT_NORM_AV_MAX_DRIFT_S)
            remux_mp4_video_timeline_authority(src, src, re_encode_video=False)
            self.assertLessEqual(
                av_duration_drift_s(src),
                STITCH_EXPORT_NORM_AV_MAX_DRIFT_S,
            )

    def test_trim_body_with_fade_audio_copy_path_aligns(self):
        """Dissolve fade_audio=False must not leave video re-encode + audio copy drift."""
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "dissolve_src.mp4"
            dst = Path(tmp) / "dissolve_out.mp4"
            _make_misaligned_clip(src, video_s=3.0, audio_s=3.12)
            trim_body_with_fade(
                src, dst,
                head_remove_s=0.0,
                tail_remove_s=0.0,
                fade_in_s=0.0,
                fade_out_s=0.6,
                fade_audio=False,
            )
            self.assertLessEqual(
                av_duration_drift_s(dst),
                STITCH_EXPORT_NORM_AV_MAX_DRIFT_S,
            )


if __name__ == "__main__":
    unittest.main()
