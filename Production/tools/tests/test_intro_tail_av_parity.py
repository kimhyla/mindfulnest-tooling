"""Canonical intro_tail whiteout hold must keep video and audio durations aligned."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS / "credentials_lib"))

from credentials_lib.ffmpeg_stitch import av_duration_drift_s  # noqa: E402


def _make_av_mp4(path: Path, duration_s: float) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=mono",
            "-f", "lavfi", "-i", f"color=c=black:s=320x240:d={duration_s:.3f}",
            "-shortest",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            str(path),
        ],
        check=True,
        capture_output=True,
        timeout=60,
    )


class IntroTailAvParityTests(unittest.TestCase):
    def test_hold_last_frame_pads_audio_to_match_video(self):
        from teleport_intro_kit import hold_last_frame  # noqa: WPS433

        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "joined.mp4"
            out = Path(tmp) / "intro_tail.mp4"
            _make_av_mp4(src, 8.0)
            hold_last_frame(src, out, hold_s=2.5)
            drift = av_duration_drift_s(out)
            self.assertLessEqual(
                drift,
                0.12,
                f"intro_tail A/V drift {drift:.3f}s exceeds tolerance",
            )

    def test_hold_last_frame_source_mentions_apad(self):
        text = (TOOLS / "teleport_intro_kit.py").read_text(encoding="utf-8")
        block = text.split("def hold_last_frame", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("apad=pad_dur=", block)
        self.assertIn("tpad=stop_mode=clone", block)


if __name__ == "__main__":
    unittest.main()
