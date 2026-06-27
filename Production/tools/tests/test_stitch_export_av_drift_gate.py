"""Beat Gen Send-to-Stitcher must reject clips with large video/audio drift."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS / "credentials_lib"))

from credentials_lib.ffmpeg_stitch import (  # noqa: E402
    STITCH_EXPORT_AV_MAX_DRIFT_S,
    assert_stitch_export_clips_av_aligned,
)


def _make_misaligned_mp4(path: Path) -> None:
    """Video ~6s, audio ~3s — mimics broken whiteout hold."""
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-t", "3", "-i", "anullsrc=r=44100:cl=mono",
            "-f", "lavfi", "-i", "color=c=black:s=320x240:d=3",
            "-filter_complex", "[1:v]tpad=stop_mode=clone:stop_duration=3[v]",
            "-map", "[v]", "-map", "0:a",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            str(path),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )


class StitchExportAvDriftGateTests(unittest.TestCase):
    def test_assert_blocks_misaligned_clip(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "intro_tail.mp4"
            _make_misaligned_mp4(bad)
            with self.assertRaises(ValueError) as ctx:
                assert_stitch_export_clips_av_aligned([bad])
            self.assertIn("intro_tail.mp4", str(ctx.exception))

    def test_concat_export_calls_av_gate(self):
        text = (TOOLS / "beat_generator.py").read_text(encoding="utf-8")
        block = text.split("def concat_kling_o3_approved_beats", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("assert_stitch_export_clips_av_aligned", block)

    def test_export_drift_threshold_is_quarter_second(self):
        self.assertEqual(STITCH_EXPORT_AV_MAX_DRIFT_S, 0.25)


if __name__ == "__main__":
    unittest.main()
