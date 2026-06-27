#!/usr/bin/env python3
"""Phase A dry export — ambient beds owned by Stitcher only."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

from server_handlers import phases  # noqa: E402
from server_handlers import stitch_editor  # noqa: E402


class TestPhaseAStitcherAmbientOnly(unittest.TestCase):
    def test_mix_audio_rejects_phase_a(self):
        src = Path(phases.__file__).read_text(encoding="utf-8")
        self.assertIn("PHASE_A_AMBIENT_STITCHER_ONLY", src)
        self.assertIn('if phase_early == "a":', src)

    def test_auto_assemble_has_no_ambient_overlay(self):
        src = Path(TOOLS / "production_server.py").read_text(encoding="utf-8")
        block_start = src.index("def _auto_assemble_phase_a_stitched")
        block = src[block_start:block_start + 3500]
        self.assertIn("stitcher_only", block)
        self.assertNotIn("phase_a_ambient_preset_id", block)
        self.assertNotIn("amix=inputs=2", block)

    def test_export_normalizes_dry_lipsync(self):
        src = Path(phases.__file__).read_text(encoding="utf-8")
        self.assertIn("_auto_assemble_phase_a_stitched(ts)", src)
        self.assertNotIn("Run Mix Audio (auto-stitch) first", src)

    def test_stitcher_default_ambient_for_phase_a(self):
        self.assertEqual(
            stitch_editor.STITCH_DEFAULT_AMBIENT_BEDS["phase_a"],
            "ambient bed pretty option2",
        )


if __name__ == "__main__":
    unittest.main()
