"""Stitch editor durability: cache validation + beat boundary enrichment."""
from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

from credentials_lib.ffmpeg_stitch import mp4_is_playable, preview_cache_is_valid
from server_handlers.stitch_editor import enrich_beat_boundaries


class StitchCacheValidationTests(unittest.TestCase):
    def test_mp4_is_playable_rejects_empty_streams(self):
        bad = Path("/tmp/stitch_bad_moov.mp4")
        # Minimal broken MP4: ftyp + oversized mvhd box, no trak — mirrors corrupt cache.
        bad.write_bytes(
            b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2avc1mp41"
            b"\x00\x00\x00\x10moov"
            + b"\x00" * 8
        )
        self.addCleanup(lambda: bad.unlink(missing_ok=True))
        self.assertFalse(mp4_is_playable(bad))

    def test_mp4_is_playable_accepts_real_clip(self):
        src = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "tiny_h264.mp4"
        if not src.is_file():
            self.skipTest("tiny_h264.mp4 fixture missing")
        self.assertTrue(mp4_is_playable(src))

    def test_preview_cache_is_valid_rejects_truncated(self):
        bad = Path("/tmp/stitch_preview_truncated.mp4")
        bad.write_bytes(
            b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2avc1mp41"
            b"\x00\x00\x00\x10moov"
            + b"\x00" * 8
        )
        self.addCleanup(lambda: bad.unlink(missing_ok=True))
        self.assertFalse(preview_cache_is_valid(bad, expected_duration_s=38.0))

    def test_preview_cache_is_valid_accepts_real_clip(self):
        src = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "tiny_h264.mp4"
        if not src.is_file():
            self.skipTest("tiny_h264.mp4 fixture missing")
        dur = float(
            subprocess.check_output(
                [
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "csv=p=0", str(src),
                ],
                text=True,
            ).strip()
        )
        self.assertTrue(preview_cache_is_valid(src, expected_duration_s=dur))

    def test_preview_cache_is_valid_rejects_av_drift(self):
        bad = Path("/tmp/stitch_preview_av_drift.mp4")
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "lavfi", "-t", "2", "-i", "anullsrc=r=44100:cl=mono",
                "-f", "lavfi", "-i", "color=c=black:s=160x120:d=2",
                "-filter_complex", "[1:v]tpad=stop_mode=clone:stop_duration=2[v]",
                "-map", "[v]", "-map", "0:a",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                str(bad),
            ],
            check=True,
            capture_output=True,
            timeout=30,
        )
        self.addCleanup(lambda: bad.unlink(missing_ok=True))
        fmt = float(
            subprocess.check_output(
                [
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "csv=p=0", str(bad),
                ],
                text=True,
            ).strip()
        )
        self.assertFalse(preview_cache_is_valid(bad, expected_duration_s=fmt))


class BeatBoundaryEnrichmentTests(unittest.TestCase):
    def test_enrich_adds_duration_ms(self):
        raw = [{"beat_id": "b1", "start_ms": 0, "end_ms": 5000}]
        out = enrich_beat_boundaries(raw)
        self.assertEqual(out[0]["duration_ms"], 5000)

    def test_enrich_preserves_existing_duration_ms(self):
        raw = [{"beat_id": "b1", "start_ms": 0, "end_ms": 5000, "duration_ms": 4999}]
        out = enrich_beat_boundaries(raw)
        self.assertEqual(out[0]["duration_ms"], 4999)


if __name__ == "__main__":
    unittest.main()
