#!/usr/bin/env python3
"""STITCH_SLOT_MEDIA_ARTIFACTS_V1 — durable slot media artifact tests."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS / "credentials_lib"))
sys.path.insert(0, str(TOOLS / "server_handlers"))

from credentials_lib.ffmpeg_stitch import stitch_audio_cache_is_valid  # noqa: E402
from credentials_lib.stitch_cache_build import atomic_ffmpeg_output  # noqa: E402
from server_handlers.stitch_media_sig import (  # noqa: E402
    STITCH_SLOT_MEDIA_ARTIFACTS_V1,
    compute_stitch_mix_sig,
    stitch_sfx_cue_sig_parts,
    waveform_mix_hash_from_parts,
)


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


class StitchSlotMediaArtifactsTests(unittest.TestCase):
    def test_mix_sig_includes_fade_fields(self):
        parts_a = stitch_sfx_cue_sig_parts([
            {"id": "c1", "offset_ms": 0, "fadein_ms": 300, "fadeout_ms": 1200, "volume": 0.45},
        ])
        parts_b = stitch_sfx_cue_sig_parts([
            {"id": "c1", "offset_ms": 0, "fadein_ms": 500, "fadeout_ms": 1200, "volume": 0.45},
        ])
        self.assertNotEqual(parts_a, parts_b)

    def test_waveform_mix_hash_changes_with_fade(self):
        base = ["cachekey", "mono_v3", "40000", "/tmp/bed.mp3", "0.1500"]
        h1 = waveform_mix_hash_from_parts(base + stitch_sfx_cue_sig_parts([
            {"id": "c1", "fadein_ms": 300, "fadeout_ms": 1200, "volume": 0.45},
        ]))
        h2 = waveform_mix_hash_from_parts(base + stitch_sfx_cue_sig_parts([
            {"id": "c1", "fadein_ms": 500, "fadeout_ms": 1200, "volume": 0.45},
        ]))
        self.assertNotEqual(h1, h2)

    def test_atomic_ffmpeg_output_validates_duration(self):
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "slot.mp4"
            out = Path(tmp) / "out.mp3"
            _make_tone_mp4(video, 5.0)
            cmd = [
                "ffmpeg", "-y", "-i", str(video),
                "-vn", "-ac", "1", "-ar", "44100", "-b:a", "128k",
                str(out.resolve()),
            ]
            atomic_ffmpeg_output(
                cmd, out, expected_duration_s=5.0,
                validator=stitch_audio_cache_is_valid,
            )
            self.assertTrue(out.is_file())
            self.assertTrue(stitch_audio_cache_is_valid(out, 5.0))

    def test_stitch_cache_lock_module_used(self):
        editor = (TOOLS / "server_handlers" / "stitch_editor.py").read_text(encoding="utf-8")
        self.assertIn("stitch_cache_build_lock", editor)
        self.assertIn("atomic_ffmpeg_output", editor)
        server = (TOOLS / "production_server.py").read_text(encoding="utf-8")
        norm_block = server.split("def _stitch_normalize_slot", 1)[1].split("\n    def ", 1)[0]
        self.assertIn("run_stitch_cache_build", norm_block)

    def test_source_markers_present(self):
        editor = (TOOLS / "server_handlers" / "stitch_editor.py").read_text(encoding="utf-8")
        self.assertIn(STITCH_SLOT_MEDIA_ARTIFACTS_V1, editor)
        artifacts = (TOOLS / "server_handlers" / "stitch_media_artifacts.py").read_text(encoding="utf-8")
        self.assertIn("validate_stitch_slot_media_artifacts", artifacts)
        self.assertIn("persist_stitch_slot_media_artifacts", artifacts)

    def test_compute_stitch_mix_sig_stable(self):
        sig = compute_stitch_mix_sig(
            video_path="Production/Event_2/assembled/res.mp4",
            video_mtime_ms=123456,
            ambient_bed="ambien bed pretty option4",
            ambient_volume=0.15,
        )
        self.assertEqual(len(sig), 16)
        self.assertEqual(sig, compute_stitch_mix_sig(
            video_path="Production/Event_2/assembled/res.mp4",
            video_mtime_ms=123456,
            ambient_bed="ambien bed pretty option4",
            ambient_volume=0.15,
        ))


class ValidateMixSigRepairTests(unittest.TestCase):
    def test_validate_syncs_mix_sig_after_stale_clear(self):
        from server_handlers.stitch_media_artifacts import (  # noqa: PLC0415
            validate_stitch_slot_media_artifacts,
        )
        from server_handlers.stitch_media_sig import compute_stitch_mix_sig_from_slot  # noqa: PLC0415

        slot = {
            "video_path": "Production/Milestones/m1/assembled/x.mp4",
            "video_dur_ms": 94063,
            "ambient_bed": "Intro video ambient bed",
            "ambient_volume": 0.15,
            "sfx_cues": [],
            "mix_sig": "deadbeefdeadbeef",
            "mux_preview_hash": "abc12345",
        }
        h = mock.MagicMock()
        h._stitch_cache_dir.return_value = Path(tempfile.mkdtemp())
        with mock.patch(
            "server_handlers.stitch_media_artifacts._artifact_cache_file_present",
            return_value=True,
        ):
            warnings = validate_stitch_slot_media_artifacts(h, slot, fast=True)
        self.assertTrue(any("mix_sig stale" in w for w in warnings))
        self.assertNotIn("mux_preview_hash", slot)
        current = compute_stitch_mix_sig_from_slot(h, slot)
        self.assertEqual(slot.get("mix_sig"), current)
        self.assertNotEqual(slot.get("mix_sig"), "deadbeefdeadbeef")


if __name__ == "__main__":
    unittest.main()
