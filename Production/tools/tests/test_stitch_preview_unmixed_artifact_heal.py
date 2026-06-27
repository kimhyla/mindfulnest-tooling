#!/usr/bin/env python3
"""Unmixed mux preview artifacts are cleared when slot expects layered audio."""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS / "server_handlers"))


def _make_tone_mp4(path: Path, duration_s: float = 2.0) -> None:
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


class StitchPreviewUnmixedArtifactHealTests(unittest.TestCase):
    def test_validate_clears_unmixed_preview_when_ambient_configured(self):
        from server_handlers.stitch_media_artifacts import validate_stitch_slot_media_artifacts
        from server_handlers.stitch_media_sig import compute_stitch_mix_sig_from_slot

        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp) / "cache"
            cache_dir.mkdir()
            source = cache_dir / "resolution.mp4"
            _make_tone_mp4(source, 2.0)
            mux_stem = "deadbeef0001"
            preview = cache_dir / f"stitch_preview_{mux_stem}.mp4"
            shutil.copy2(source, preview)

            h = mock.Mock()
            h._stitch_cache_dir.return_value = cache_dir
            h._stitch_resolve_path.side_effect = lambda p: p

            slot = {
                "video_path": str(source),
                "video_dur_ms": 2000,
                "ambient_bed": "ambien bed pretty option4",
                "ambient_bed_path": str(cache_dir / "bed.mp3"),
                "ambient_volume": 0.15,
                "mux_preview_hash": mux_stem,
                "mux_preview_duration_ms": 2000,
                "mux_video_path": str(source),
                "mux_video_mtime_ms": int(source.stat().st_mtime * 1000),
            }
            (cache_dir / "bed.mp3").write_bytes(b"fake")
            slot["mix_sig"] = compute_stitch_mix_sig_from_slot(h, slot)

            warnings = validate_stitch_slot_media_artifacts(h, slot)
            self.assertIn("unmixed", " ".join(warnings).lower())
            self.assertNotIn("mux_preview_hash", slot)

    def test_validate_keeps_mixed_preview_when_files_differ(self):
        from server_handlers.stitch_media_artifacts import validate_stitch_slot_media_artifacts
        from server_handlers.stitch_media_sig import compute_stitch_mix_sig_from_slot

        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp) / "cache"
            cache_dir.mkdir()
            source = cache_dir / "resolution.mp4"
            _make_tone_mp4(source, 2.0)
            mux_stem = "cafebabe0002"
            preview = cache_dir / f"stitch_preview_{mux_stem}.mp4"
            _make_tone_mp4(preview, 2.5)

            h = mock.Mock()
            h._stitch_cache_dir.return_value = cache_dir
            h._stitch_resolve_path.side_effect = lambda p: p

            slot = {
                "video_path": str(source),
                "video_dur_ms": 2500,
                "ambient_bed": "bed",
                "ambient_bed_path": str(cache_dir / "bed.mp3"),
                "mux_preview_hash": mux_stem,
                "mux_preview_duration_ms": 2500,
                "mux_video_path": str(source),
                "mux_video_mtime_ms": int(source.stat().st_mtime * 1000),
            }
            (cache_dir / "bed.mp3").write_bytes(b"fake")
            slot["mix_sig"] = compute_stitch_mix_sig_from_slot(h, slot)

            warnings = validate_stitch_slot_media_artifacts(h, slot)
            self.assertEqual(slot.get("mux_preview_hash"), mux_stem)
            self.assertFalse(any("unmixed" in w.lower() for w in warnings))


if __name__ == "__main__":
    unittest.main()
