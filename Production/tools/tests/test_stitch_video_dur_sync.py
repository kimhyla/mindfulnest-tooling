"""Stitch slot video_dur_ms — drift sync + intro default whoosh."""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock

REPO = Path(__file__).resolve().parents[2]


class TestStitchVideoDurSync(unittest.TestCase):
    def test_sync_updates_when_stored_duration_drifts(self):
        from server_handlers.stitch_editor import sync_stitch_slot_video_dur_ms

        h = MagicMock()
        h._stitch_resolve_path.return_value = "/proj/Event_1/phase_a.mp4"
        h._ffprobe_duration_ms.return_value = 38312
        slot = {
            "video_path": "Production/Event_1/phase_a.mp4",
            "video_dur_ms": 50949,
        }
        with unittest.mock.patch(
            "server_handlers.stitch_editor.require_media_under_project",
            return_value="/proj/Event_1/phase_a.mp4",
        ):
            self.assertTrue(sync_stitch_slot_video_dur_ms(h, slot))
        self.assertEqual(slot["video_dur_ms"], 38312)

    def test_sync_skips_when_within_tolerance(self):
        from server_handlers.stitch_editor import sync_stitch_slot_video_dur_ms

        h = MagicMock()
        h._stitch_resolve_path.return_value = "/proj/Event_1/intro.mp4"
        h._ffprobe_duration_ms.return_value = 66295
        slot = {"video_path": "Production/Event_1/intro.mp4", "video_dur_ms": 66292}
        with unittest.mock.patch(
            "server_handlers.stitch_editor.require_media_under_project",
            return_value="/proj/Event_1/intro.mp4",
        ):
            self.assertFalse(sync_stitch_slot_video_dur_ms(h, slot))
        self.assertEqual(slot["video_dur_ms"], 66292)


class TestIntroDefaultWhoosh(unittest.TestCase):
    def test_apply_whoosh_at_tail_on_new_intro(self):
        from server_handlers.stitch_editor import ensure_stitch_intro_default_whoosh_cue

        h = MagicMock()
        h._stitch_project_root.return_value = Path("/proj")
        whoosh = Path("/proj/whoosh sound.mp3")

        def ffprobe(p):
            if str(p).endswith("whoosh sound.mp3"):
                return 8039
            return 66291

        h._ffprobe_duration_ms.side_effect = ffprobe
        slot = {"video_path": "Production/Event_1/intro.mp4", "video_dur_ms": 66291}

        with unittest.mock.patch(
            "server_handlers.stitch_editor._resolve_stitch_intro_whoosh_path",
            return_value=str(whoosh),
        ):
            self.assertTrue(ensure_stitch_intro_default_whoosh_cue(h, slot))

        self.assertEqual(len(slot["sfx_cues"]), 1)
        cue = slot["sfx_cues"][0]
        self.assertIn("whoosh", cue["name"].lower())
        self.assertEqual(cue["offset_ms"], 66291 - cue["duration_ms"])
        self.assertTrue(cue.get("auto_default"))

    def test_apply_whoosh_skips_when_cue_already_present(self):
        from server_handlers.stitch_editor import ensure_stitch_intro_default_whoosh_cue

        h = MagicMock()
        slot = {
            "video_path": "Production/Event_1/intro.mp4",
            "video_dur_ms": 66000,
            "sfx_cues": [{"id": "x", "name": "whoosh sound.mp3", "source_path": "/a.mp3"}],
        }
        self.assertFalse(ensure_stitch_intro_default_whoosh_cue(h, slot))
        self.assertEqual(len(slot["sfx_cues"]), 1)

    def test_apply_whoosh_skips_when_dismissed(self):
        from server_handlers.stitch_editor import ensure_stitch_intro_default_whoosh_cue

        h = MagicMock()
        slot = {
            "video_path": "Production/Event_1/intro.mp4",
            "video_dur_ms": 66000,
            "intro_whoosh_default_dismissed": True,
        }
        self.assertFalse(ensure_stitch_intro_default_whoosh_cue(h, slot))
        self.assertEqual(slot.get("sfx_cues"), None)


class TestStitchSlotDurationWarnings(unittest.TestCase):
    def test_warns_when_beat_map_exceeds_file(self):
        from server_handlers.stitch_editor import stitch_slot_duration_warnings

        h = MagicMock()
        h._stitch_resolve_path.return_value = "/proj/phase_a.mp4"
        h._ffprobe_duration_ms.return_value = 38333
        slot = {
            "video_path": "Production/Event_1/phase_a.mp4",
            "video_dur_ms": 50949,
            "beat_boundaries": [{"beat_id": "b1", "start_ms": 0, "end_ms": 50949}],
        }
        with unittest.mock.patch(
            "server_handlers.stitch_editor.require_media_under_project",
            return_value="/proj/phase_a.mp4",
        ):
            warnings = stitch_slot_duration_warnings(h, "phase_a", slot)
        self.assertTrue(any("truncated" in w for w in warnings))
        self.assertTrue(any("50949" in w for w in warnings))


class TestPhaseATabCanonicalSync(unittest.TestCase):
    def test_sync_phase_a_from_production_state(self):
        from server_handlers.stitch_editor import sync_stitch_phase_a_from_phase_tab

        h = MagicMock()
        h.app.event_dir = Path("/proj/Production/Event_1")
        h.app.state.read_state.return_value = {
            "phase_a_stitched_file": "phase_a_stitched_20260611-175925.mp4",
        }
        h._stitch_resolve_path.return_value = (
            "/proj/Production/Event_1/phase_a_stitched_20260611-175925.mp4"
        )
        h._ffprobe_duration_ms.return_value = 38333
        slot = {
            "video_path": "Production/Event_1/phase_a_stitched_20260609-153516.mp4",
            "video_dur_ms": 50908,
        }
        with unittest.mock.patch(
            "server_handlers.stitch_editor.require_media_under_project",
            return_value="/proj/Production/Event_1/phase_a_stitched_20260611-175925.mp4",
        ):
            self.assertTrue(sync_stitch_phase_a_from_phase_tab(h, slot))
        self.assertEqual(
            slot["video_path"],
            "Production/Event_1/phase_a_stitched_20260611-175925.mp4",
        )
        self.assertEqual(slot["video_dur_ms"], 38333)


if __name__ == "__main__":
    unittest.main()
