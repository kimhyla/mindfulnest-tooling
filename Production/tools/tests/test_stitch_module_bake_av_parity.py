"""STITCH_MODULE_BAKE_AV_PARITY_V1 — module bake must reject A/V stream drift."""
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
    av_duration_drift_s,
    preview_cache_is_valid,
)


def _make_misaligned_mp4(path: Path) -> None:
    """Video ~6s, audio ~3s — mimics broken concat copy (audio longer than video)."""
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


class StitchModuleBakeAvParityTests(unittest.TestCase):
    def test_misaligned_clip_blocked_by_assert(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "module_preview.mp4"
            _make_misaligned_mp4(bad)
            self.assertGreater(av_duration_drift_s(bad), STITCH_EXPORT_AV_MAX_DRIFT_S)
            with self.assertRaises(ValueError):
                assert_stitch_export_clips_av_aligned([bad])

    def test_preview_cache_rejects_av_drift_even_when_format_duration_long(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "stitch_preview_bad.mp4"
            _make_misaligned_mp4(bad)
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
            self.assertGreater(fmt, 5.0)
            self.assertFalse(preview_cache_is_valid(bad, expected_duration_s=fmt))

    def test_stitch_build_pipeline_gates_pre_and_post_concat(self):
        text = (TOOLS / "production_server.py").read_text(encoding="utf-8")
        block = text.split("def _stitch_build_pipeline", 1)[1].split("\n    def ", 1)[0]
        self.assertIn("STITCH_MODULE_BAKE_AV_PARITY_V1", block)
        self.assertIn("assert_stitch_export_clips_av_aligned(slot_finals)", block)
        self.assertIn("preview_av_drift_s = av_duration_drift_s(out_path)", block)

    def test_concat_with_xfade_clips_has_reencode_av_fallback(self):
        text = (TOOLS / "credentials_lib" / "ffmpeg_stitch.py").read_text(encoding="utf-8")
        block = text.split("def concat_with_xfade_clips", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("STITCH_MODULE_BAKE_AV_PARITY_V1", block)
        self.assertIn("copy_streams=False", block)
        self.assertIn("re-encode fallback", block)

    def test_stitch_bake_core_gates_pre_and_post_encode(self):
        text = (TOOLS / "server_handlers" / "stitch_editor.py").read_text(encoding="utf-8")
        block = text.split("def _run_stitch_bake_core", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("STITCH_MODULE_BAKE_AV_PARITY_V1", block)
        self.assertIn("assert_stitch_export_clips_av_aligned([out_path])", block)
        self.assertIn("bake_av_drift_s = av_duration_drift_s(bake_path)", block)

    def test_stitch_cached_mp4_playable_uses_copy_remux_not_full_reencode(self):
        text = (TOOLS / "server_handlers" / "stitch_editor.py").read_text(encoding="utf-8")
        block = text.split("def stitch_cached_mp4_playable", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("remux_mp4_playback_safe", block)
        self.assertNotIn("ensure_mp4_playback_timestamps", block)

    def test_stitch_cached_mp4_playable_rejects_av_drift(self):
        from server_handlers.stitch_editor import stitch_cached_mp4_playable  # noqa: E402

        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "playable_bad.mp4"
            _make_misaligned_mp4(bad)
            self.assertFalse(stitch_cached_mp4_playable(bad))

    def test_module_preview_decode_timeout_scales_with_duration(self):
        from credentials_lib.ffmpeg_stitch import stitch_preview_decode_timeout_s  # noqa: E402

        self.assertEqual(stitch_preview_decode_timeout_s(0), 45)
        self.assertEqual(stitch_preview_decode_timeout_s(30), 45)
        self.assertGreater(stitch_preview_decode_timeout_s(380), 120)
        self.assertLessEqual(stitch_preview_decode_timeout_s(380), 600)


if __name__ == "__main__":
    unittest.main()
