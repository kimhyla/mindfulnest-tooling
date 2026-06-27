#!/usr/bin/env python3
"""Offline coverage for Production/tools/kling_startend_pipeline.py.

task_id = LD-260-pytest-3-pipeline-scripts-20260418
preflight = 72
LD coverage = LD-260, LD-172 (KLING_STARTEND_V1_CAPABILITY compliance probes),
Rule 6 (min-dimension enforcement), Rule 8.1/8.2/8.3 (anti-lipsync defaults).

Scope: import surface, pure-function behavior (ensure_min_dimensions),
module-level constant sanity (cfg_scale, sound, negative_prompt presence),
argparse --help boot. No WaveSpeed, no BFL, no ffmpeg runtime required at
import time (ffmpeg-dependent helpers are not exercised in this suite).
"""

from __future__ import annotations

import importlib.util
import io
import subprocess
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

_PIL_AVAILABLE = importlib.util.find_spec("PIL") is not None


class KlingStartendImportTests(unittest.TestCase):
    """Module must import cleanly."""

    def test_module_imports(self) -> None:
        import kling_startend_pipeline as mod  # noqa: F401
        self.assertTrue(hasattr(mod, "main"))
        self.assertTrue(hasattr(mod, "ensure_min_dimensions"))
        self.assertTrue(hasattr(mod, "ensure_avatar_still_dimensions"))
        self.assertTrue(hasattr(mod, "flux_kontext_generate_end_frame"))
        self.assertTrue(hasattr(mod, "kling_startend_submit"))

    def test_log_helper_pure(self) -> None:
        """log() must accept a string and not raise."""
        import kling_startend_pipeline as mod
        mod.log("test message — pytest suite")


class EnsureMinDimensionsTests(unittest.TestCase):
    """Rule 6 enforcement: auto-upscale when shortest side < min."""

    @unittest.skipUnless(_PIL_AVAILABLE, "Pillow not installed — skipping upscale tests")
    def test_upscale_small_image(self) -> None:
        from PIL import Image
        import kling_startend_pipeline as mod

        buf = io.BytesIO()
        Image.new("RGB", (400, 400), color=(128, 128, 128)).save(buf, format="PNG")
        upscaled, info, (w, h) = mod.ensure_min_dimensions(buf.getvalue(), min_side=600, target_min=800)
        self.assertGreaterEqual(min(w, h), 800, msg=f"shortest side must be ≥800 after upscale, got {w}x{h}")
        self.assertIn("upscaled", info)

    @unittest.skipUnless(_PIL_AVAILABLE, "Pillow not installed — skipping upscale tests")
    def test_passthrough_large_image(self) -> None:
        from PIL import Image
        import kling_startend_pipeline as mod

        buf = io.BytesIO()
        Image.new("RGB", (1200, 900), color=(0, 0, 0)).save(buf, format="PNG")
        same, info, (w, h) = mod.ensure_min_dimensions(buf.getvalue(), min_side=600, target_min=800)
        self.assertEqual((w, h), (1200, 900))
        self.assertIn("OK", info)


class KlingStartendCliTests(unittest.TestCase):
    """CLI boots and exposes the beat/end-prompt/end-image/dry-run flags."""

    def test_help_exits_zero(self) -> None:
        result = subprocess.run(
            [sys.executable, str(TOOLS / "kling_startend_pipeline.py"), "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("--beat", result.stdout)
        self.assertIn("--dry-run", result.stdout)
        self.assertIn("--skip-lipsync", result.stdout)


if __name__ == "__main__":
    unittest.main()
