#!/usr/bin/env python3
"""Preview must not overwrite video_path on non-intro slots (STITCH_PREVIEW_SLOT_GEOMETRY_GUARD_V1)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS / "server_handlers"))

from server_handlers import stitch_editor as se  # noqa: E402


class StitchPreviewSlotGeometryGuardTests(unittest.TestCase):
    def test_hydrated_preview_slot_dict_respects_slot_key(self):
        hydrated = {
            "name": "Event_4_stitch",
            "slots": [
                {"video_path": "Production/Event_4/assembled/intro.mp4", "video_dur_ms": 100},
                {"video_path": "Production/Event_4/phase_a.mp4", "video_dur_ms": 18},
            ],
        }
        intro = se._hydrated_preview_slot_dict(hydrated, "intro")
        phase_a = se._hydrated_preview_slot_dict(hydrated, "phase_a")
        self.assertIsNone(intro)
        self.assertIsNone(phase_a)

    def test_hydrated_preview_slot_dict_single_slot_list(self):
        hydrated = {
            "name": "Event_4_stitch",
            "slots": [{"video_path": "Production/Event_4/phase_a.mp4", "video_dur_ms": 18}],
        }
        slot = se._hydrated_preview_slot_dict(hydrated, "phase_a")
        self.assertEqual(slot["video_path"], "Production/Event_4/phase_a.mp4")

    def test_persist_preview_geometry_does_not_clobber_video_path(self):
        store = MagicMock()
        h = MagicMock()
        h.app.stitch_state = store
        prev_state = {
            "jobs": {
                "Event_4_stitch": {
                    "slots": {
                        "phase_a": {
                            "video_path": "Production/Event_4/phase_a.mp4",
                            "video_dur_ms": 18439,
                            "ambient_bed": "ambient bed pretty option2",
                        }
                    }
                }
            }
        }

        def mutate_state(fn):
            fn(prev_state)

        store.mutate_state.side_effect = mutate_state
        h.app.stitch_state = store
        from server_handlers.stitch_editor import stitch_state_store_for_job  # noqa: PLC0415

        with unittest.mock.patch.object(se, "stitch_state_store_for_job", return_value=store):
            se._persist_stitch_preview_slot_geometry(
                h,
                "Event_4_stitch",
                "phase_a",
                {
                    "video_path": "Production/Event_4/assembled/intro.mp4",
                    "video_dur_ms": 132737,
                    "ambient_bed": "Intro video ambient bed",
                },
            )
        slot = prev_state["jobs"]["Event_4_stitch"]["slots"]["phase_a"]
        self.assertEqual(slot["video_path"], "Production/Event_4/phase_a.mp4")
        self.assertEqual(slot["video_dur_ms"], 18439)
        self.assertEqual(slot["ambient_bed"], "Intro video ambient bed")


if __name__ == "__main__":
    unittest.main()
