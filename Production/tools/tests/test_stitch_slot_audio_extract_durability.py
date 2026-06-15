#!/usr/bin/env python3
"""STITCH_SLOT_MEDIA_LINEAGE_DURABILITY_V1 — truncated audio extract guards."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS / "credentials_lib"))

from credentials_lib.ffmpeg_stitch import stitch_audio_cache_is_valid  # noqa: E402


def _make_tone_mp4(path: Path, duration_s: float) -> None:
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


def _extract_mp3(src: Path, dst: Path) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(src),
            "-vn", "-ac", "1", "-ar", "44100", "-b:a", "128k",
            str(dst),
        ],
        check=True,
        capture_output=True,
        timeout=60,
    )


class StitchSlotAudioExtractDurabilityTests(unittest.TestCase):
    def test_stitch_audio_cache_is_valid_accepts_full_extract(self):
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "slot.mp4"
            audio = Path(tmp) / "extract.mp3"
            _make_tone_mp4(video, 38.0)
            _extract_mp3(video, audio)
            self.assertTrue(stitch_audio_cache_is_valid(audio, 38.0))

    def test_stitch_audio_cache_is_valid_rejects_truncated(self):
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "slot.mp4"
            short = Path(tmp) / "short.mp3"
            _make_tone_mp4(video, 38.0)
            _make_tone_mp4(Path(tmp) / "tiny.mp4", 15.0)
            _extract_mp3(Path(tmp) / "tiny.mp4", short)
            self.assertFalse(stitch_audio_cache_is_valid(short, 38.0))

    def test_source_markers_present(self):
        editor = (TOOLS / "server_handlers" / "stitch_editor.py").read_text(encoding="utf-8")
        self.assertIn("STITCH_SLOT_MEDIA_LINEAGE_DURABILITY_V1", editor)
        self.assertIn("STITCH_SLOT_AUDIO_EXTRACT_TRUNCATED", editor)
        self.assertIn("expected_video_dur_ms", editor)


if __name__ == "__main__":
    unittest.main()
