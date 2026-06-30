#!/usr/bin/env python3
"""Avatar Pro still prep — 1920×1080 scale-to-fill + center crop (category choke point)."""

from __future__ import annotations

import importlib.util
import io
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

_PIL_AVAILABLE = importlib.util.find_spec("PIL") is not None

OLIVER_STILL = (
    Path.home()
    / "Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production"
    / "Event_1/library/images/sources/ChatGPT Image Jun 24, 2026, 01_34_29 PM (2).png"
)


class AvatarStillPrepTests(unittest.TestCase):
    @unittest.skipUnless(_PIL_AVAILABLE, "Pillow not installed")
    def test_ensure_avatar_still_dimensions_exported(self) -> None:
        import kling_startend_pipeline as mod

        self.assertTrue(hasattr(mod, "ensure_avatar_still_dimensions"))

    @unittest.skipUnless(_PIL_AVAILABLE, "Pillow not installed")
    def test_exact_1920x1080_passthrough(self) -> None:
        from PIL import Image

        import kling_startend_pipeline as mod

        buf = io.BytesIO()
        Image.new("RGB", (1920, 1080), color=(64, 64, 64)).save(buf, format="PNG")
        raw = buf.getvalue()
        out, info, (w, h) = mod.ensure_avatar_still_dimensions(raw)
        self.assertEqual((w, h), (1920, 1080))
        self.assertEqual(out, raw)
        self.assertIn("OK 1920x1080", info)

    @unittest.skipUnless(_PIL_AVAILABLE, "Pillow not installed")
    def test_oliver_still_becomes_1920x1080(self) -> None:
        from PIL import Image

        import kling_startend_pipeline as mod
        import video_delivery

        if not OLIVER_STILL.is_file():
            self.skipTest(f"Oliver fixture missing: {OLIVER_STILL}")

        raw = OLIVER_STILL.read_bytes()
        with Image.open(io.BytesIO(raw)) as img:
            self.assertEqual(img.size, (1672, 941))

        png, min_info, _ = mod.ensure_min_dimensions(raw)
        self.assertIn("OK 1672x941", min_info)

        png, still_info, (w, h) = mod.ensure_avatar_still_dimensions(png)
        self.assertEqual(
            (w, h),
            (video_delivery.LIPSYNC_INPUT_WIDTH, video_delivery.LIPSYNC_INPUT_HEIGHT),
        )
        self.assertIn("avatar_still 1672x941 → 1920x1080", still_info)

        with Image.open(io.BytesIO(png)) as out_img:
            self.assertEqual(out_img.size, (1920, 1080))

    @unittest.skipUnless(_PIL_AVAILABLE, "Pillow not installed")
    def test_small_image_chain_min_then_avatar(self) -> None:
        from PIL import Image

        import kling_startend_pipeline as mod

        buf = io.BytesIO()
        Image.new("RGB", (400, 300), color=(200, 100, 50)).save(buf, format="PNG")
        raw = buf.getvalue()
        png, min_info, _ = mod.ensure_min_dimensions(raw, min_side=600, target_min=800)
        self.assertIn("upscaled", min_info)
        png, still_info, (w, h) = mod.ensure_avatar_still_dimensions(png)
        self.assertEqual((w, h), (1920, 1080))
        self.assertIn("avatar_still", still_info)


class AvatarStillPrepContractTests(unittest.TestCase):
    def test_submit_avatar_pro_calls_both_prep_steps(self) -> None:
        src = (TOOLS / "lipsync_sender.py").read_text(encoding="utf-8")
        block = src[src.index("def submit_avatar_pro") : src.index("def ", src.index("def submit_avatar_pro") + 1)]
        self.assertIn("ensure_min_dimensions", block)
        self.assertIn("ensure_avatar_still_dimensions", block)
        self.assertIn("negative_prompt", block)
        self.assertIn("AVATAR_PRO_NEGATIVE_PROMPT", block)

    def test_segmented_production_uses_submit_avatar_pro(self) -> None:
        src = (TOOLS / "run_phase_b_avatar_segmented_production.py").read_text(encoding="utf-8")
        self.assertIn("client.submit_avatar_pro", src)
        self.assertNotIn("AVATAR_ENDPOINT", src)


if __name__ == "__main__":
    unittest.main()
