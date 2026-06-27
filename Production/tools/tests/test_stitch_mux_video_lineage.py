#!/usr/bin/env python3
"""Mux preview artifacts must match slot video lineage (path, mtime, duration)."""
from __future__ import annotations

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


class StitchMuxVideoLineageTests(unittest.TestCase):
    def test_validate_clears_mux_when_duration_drift_exceeds_slot_video(self):
        from server_handlers.stitch_media_artifacts import validate_stitch_slot_media_artifacts
        from server_handlers.stitch_media_sig import compute_stitch_mix_sig_from_slot

        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp) / "cache"
            cache_dir.mkdir()
            source = cache_dir / "phase_a.mp4"
            _make_tone_mp4(source, 22.75)
            mux_stem = "stalemux0001"
            preview = cache_dir / f"stitch_preview_{mux_stem}.mp4"
            _make_tone_mp4(preview, 22.36)

            h = mock.Mock()
            h._stitch_cache_dir.return_value = cache_dir
            h._stitch_resolve_path.side_effect = lambda p: p

            slot = {
                "video_path": str(source),
                "video_dur_ms": 22750,
                "ambient_bed": "bed",
                "ambient_bed_path": str(cache_dir / "bed.mp3"),
                "mux_preview_hash": mux_stem,
                "mux_preview_duration_ms": 22360,
                "mux_video_path": str(source),
                "mux_video_mtime_ms": int(source.stat().st_mtime * 1000),
            }
            (cache_dir / "bed.mp3").write_bytes(b"fake")
            slot["mix_sig"] = compute_stitch_mix_sig_from_slot(h, slot)

            warnings = validate_stitch_slot_media_artifacts(h, slot)
            self.assertIn("duration drift", " ".join(warnings).lower())
            self.assertNotIn("mux_preview_hash", slot)

    def test_validate_clears_mux_when_video_mtime_changes(self):
        from server_handlers.stitch_media_artifacts import validate_stitch_slot_media_artifacts
        from server_handlers.stitch_media_sig import compute_stitch_mix_sig_from_slot

        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp) / "cache"
            cache_dir.mkdir()
            source = cache_dir / "phase_a.mp4"
            _make_tone_mp4(source, 2.0)
            mux_stem = "oldrev0002"
            preview = cache_dir / f"stitch_preview_{mux_stem}.mp4"
            _make_tone_mp4(preview, 2.0)

            h = mock.Mock()
            h._stitch_cache_dir.return_value = cache_dir
            h._stitch_resolve_path.side_effect = lambda p: p

            slot = {
                "video_path": str(source),
                "video_dur_ms": 2000,
                "ambient_bed": "bed",
                "ambient_bed_path": str(cache_dir / "bed.mp3"),
                "mux_preview_hash": mux_stem,
                "mux_preview_duration_ms": 2000,
                "mux_video_path": str(source),
                "mux_video_mtime_ms": 1,
            }
            (cache_dir / "bed.mp3").write_bytes(b"fake")
            slot["mix_sig"] = compute_stitch_mix_sig_from_slot(h, slot)

            warnings = validate_stitch_slot_media_artifacts(h, slot)
            self.assertIn("older video revision", " ".join(warnings).lower())
            self.assertNotIn("mux_preview_hash", slot)

    def test_validate_clears_unpinned_legacy_mux(self):
        from server_handlers.stitch_media_artifacts import validate_stitch_slot_media_artifacts
        from server_handlers.stitch_media_sig import (
            STITCH_MUX_VIDEO_LINEAGE_V1,
            compute_stitch_mix_sig_from_slot,
        )

        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp) / "cache"
            cache_dir.mkdir()
            source = cache_dir / "phase_a.mp4"
            _make_tone_mp4(source, 2.0)
            mux_stem = "legacymux0003"
            preview = cache_dir / f"stitch_preview_{mux_stem}.mp4"
            _make_tone_mp4(preview, 2.0)

            h = mock.Mock()
            h._stitch_cache_dir.return_value = cache_dir
            h._stitch_resolve_path.side_effect = lambda p: p

            slot = {
                "video_path": str(source),
                "video_dur_ms": 2000,
                "ambient_bed": "bed",
                "ambient_bed_path": str(cache_dir / "bed.mp3"),
                "mux_preview_hash": mux_stem,
                "mux_preview_duration_ms": 2000,
            }
            (cache_dir / "bed.mp3").write_bytes(b"fake")
            slot["mix_sig"] = compute_stitch_mix_sig_from_slot(h, slot)

            warnings = validate_stitch_slot_media_artifacts(h, slot)
            self.assertIn(STITCH_MUX_VIDEO_LINEAGE_V1, " ".join(warnings))
            self.assertNotIn("mux_preview_hash", slot)

    def test_persist_mux_pins_video_lineage(self):
        from server_handlers.stitch_media_artifacts import persist_stitch_slot_media_artifacts

        state = {
            "jobs": {
                "Event_2_stitch": {
                    "slots": {
                        "phase_a": {
                            "video_path": "Production/Event_2/phase_a.mp4",
                        },
                    },
                },
            },
        }

        def mutate(fn):
            fn(state)

        h = mock.Mock()
        h.app.stitch_state.mutate_state.side_effect = mutate

        persist_stitch_slot_media_artifacts(
            h,
            "Event_2_stitch",
            "phase_a",
            mix_sig="abc123",
            mux_preview_hash="muxhash123",
            mux_preview_duration_ms=22750,
            mux_video_path="Production/Event_2/phase_a.mp4",
            mux_video_mtime_ms=1234567890,
        )

        slot = state["jobs"]["Event_2_stitch"]["slots"]["phase_a"]
        self.assertEqual(slot["mux_video_path"], "Production/Event_2/phase_a.mp4")
        self.assertEqual(slot["mux_video_mtime_ms"], 1234567890)


if __name__ == "__main__":
    unittest.main()
