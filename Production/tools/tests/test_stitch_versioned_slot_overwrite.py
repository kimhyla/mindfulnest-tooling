"""Versioned stitch slot overwrite — stale exports must not replace newer stored video."""
from __future__ import annotations

import unittest
import unittest.mock as mock

from server_handlers.stitch_editor import (
    _stitch_should_skip_video_replace,
    _stitch_video_path_epoch,
    stitch_upsert_event_slot,
)


class _MockStitchState:
    def __init__(self, initial=None):
        self.state = initial or {"jobs": {}}

    def read_state(self):
        return self.state

    def mutate_state(self, fn):
        fn(self.state)


class _MockHandler:
    def __init__(self, state=None):
        self.app = type("App", (), {"stitch_state": _MockStitchState(state)})()

    def _stitch_resolve_path(self, path: str) -> str:
        return path


class StitchVersionedOverwriteTests(unittest.TestCase):
    def test_epoch_from_iso_filename(self):
        h = _MockHandler()
        epoch = _stitch_video_path_epoch(
            h,
            "Production/Event_2/assembled/intro_kling_o3_20260619T193118Z.mp4",
        )
        self.assertGreater(epoch, 1_700_000_000)

    def test_skip_when_incoming_older_than_stored(self):
        h = _MockHandler()
        old = "Production/Event_2/assembled/intro_kling_o3_20260619T193118Z.mp4"
        new = "Production/Event_2/assembled/intro_kling_o3_20260618T120000Z.mp4"
        self.assertTrue(_stitch_should_skip_video_replace(h, old, new))

    def test_allow_when_incoming_newer_than_stored(self):
        h = _MockHandler()
        old = "Production/Event_2/assembled/intro_kling_o3_20260618T120000Z.mp4"
        new = "Production/Event_2/assembled/intro_kling_o3_20260619T193118Z.mp4"
        self.assertFalse(_stitch_should_skip_video_replace(h, old, new))

    def test_upsert_skips_stale_export_without_mutating_slot(self):
        state = {
            "jobs": {
                "Event_2_stitch": {
                    "slots": {
                        "intro": {
                            "video_path": "Production/Event_2/assembled/intro_kling_o3_20260619T193118Z.mp4",
                            "video_dur_ms": 177_000,
                            "sfx_cues": [{"id": "cue-1"}],
                        },
                    },
                },
            },
        }
        h = _MockHandler(state)
        job_name, kept_ms, warnings, _playback = stitch_upsert_event_slot(
            h,
            "Event_2",
            "intro",
            {
                "video_path": "Production/Event_2/assembled/intro_kling_o3_20260618T120000Z.mp4",
                "source": "test",
            },
            beat_boundaries=[{"beat_id": "b1", "start_ms": 0, "end_ms": 1000}],
        )
        self.assertEqual(job_name, "Event_2_stitch")
        self.assertEqual(kept_ms, 177_000)
        self.assertTrue(any("kept existing" in w for w in warnings))
        slot = h.app.stitch_state.state["jobs"]["Event_2_stitch"]["slots"]["intro"]
        self.assertIn("20260619T193118Z", slot["video_path"])
        self.assertEqual(slot["sfx_cues"], [{"id": "cue-1"}])


if __name__ == "__main__":
    unittest.main()
