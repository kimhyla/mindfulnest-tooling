"""Stitcher SFX QA — video_dur hydration, legacy preview paths, mix metadata."""
from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock

REPO = Path(__file__).resolve().parents[2]
SERVER = REPO / "tools" / "production_server.py"


class TestStitchSlotVideoDurHydrate(unittest.TestCase):
    def test_hydrate_sets_video_dur_when_missing(self):
        from server_handlers.stitch_editor import hydrate_stitch_slot_video_dur_ms

        h = MagicMock()
        h._stitch_resolve_path.return_value = "/proj/Event_1/intro.mp4"
        h._ffprobe_duration_ms.return_value = 66292
        slot = {"video_path": "Production/Event_1/intro.mp4"}
        with unittest.mock.patch(
            "server_handlers.stitch_editor.require_media_under_project",
            return_value="/proj/Event_1/intro.mp4",
        ):
            self.assertTrue(hydrate_stitch_slot_video_dur_ms(h, slot))
        self.assertEqual(slot["video_dur_ms"], 66292)

    def test_hydrate_skips_when_video_dur_present(self):
        from server_handlers.stitch_editor import hydrate_stitch_slot_video_dur_ms

        h = MagicMock()
        slot = {"video_path": "Production/Event_1/intro.mp4", "video_dur_ms": 5000}
        self.assertFalse(hydrate_stitch_slot_video_dur_ms(h, slot))
        h._ffprobe_duration_ms.assert_not_called()


class TestLegacyAudioFileServe(unittest.TestCase):
    def test_serve_stitch_audio_includes_project_root_legacy(self):
        src = SERVER.read_text(encoding="utf-8")
        block = src.split("def _serve_stitch_audio_file", 1)[1].split("\n    def ", 1)[0]
        self.assertIn("project_root / safe", block)


class TestAudioExtractResponse(unittest.TestCase):
    def test_audio_extract_includes_video_dur_ms(self):
        from server_handlers import stitch_editor as se

        src = Path(se.__file__).read_text(encoding="utf-8")
        self.assertIn('"video_dur_ms": video_dur_ms', src)
        self.assertIn('slot["_sfx_mixed"] = True', src)


if __name__ == "__main__":
    unittest.main()
