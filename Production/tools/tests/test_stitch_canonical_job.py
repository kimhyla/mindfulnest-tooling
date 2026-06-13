"""Unit tests for canonical per-event stitch job upsert + legacy migration."""
from __future__ import annotations

import unittest
import unittest.mock as mock

from server_handlers.stitch_editor import (
    stitch_event_job_name,
    stitch_migrate_legacy_to_canonical,
    stitch_upsert_event_slot,
    STITCH_SLOT_ORDER,
)


class _MockStitchState:
    def __init__(self, initial=None):
        self.state = initial or {"jobs": {}}

    def mutate_state(self, fn):
        fn(self.state)


class _MockApp:
    def __init__(self, state=None):
        self.stitch_state = _MockStitchState(state)


class _MockHandler:
    def __init__(self, state=None):
        self.app = _MockApp(state)


class StitchCanonicalJobTests(unittest.TestCase):
    def test_event_job_name(self):
        self.assertEqual(stitch_event_job_name("Event_1"), "Event_1_stitch")

    def test_migrate_legacy_preserves_resolution_when_phase_b_exports(self):
        state = {
            "jobs": {
                "auto_resolution": {
                    "slots": {
                        "resolution": {"video_path": "/proj/scene_resolution.mp4"},
                    },
                },
                "phase_b_Event_1": {
                    "slots": {
                        "phase_b": {"video_path": "Production/Event_1/phase_b_lipsync_x.mp4"},
                    },
                },
            },
        }
        changed = stitch_migrate_legacy_to_canonical(state, "Event_1")
        self.assertTrue(changed)
        canonical = state["jobs"]["Event_1_stitch"]["slots"]
        self.assertIn("resolution", canonical)
        self.assertIn("phase_b", canonical)
        self.assertEqual(
            canonical["resolution"]["video_path"],
            "/proj/scene_resolution.mp4",
        )

    def test_upsert_does_not_drop_other_slots(self):
        h = _MockHandler(
            {
                "jobs": {
                    "Event_1_stitch": {
                        "slots": {
                            "resolution": {"video_path": "/proj/scene_resolution.mp4"},
                        },
                    },
                },
            },
        )
        with mock.patch(
            "server_handlers.stitch_editor.stitch_slot_export_media_preflight",
            return_value=(60_000, []),
        ), mock.patch(
            "server_handlers.stitch_editor.sync_stitch_slot_video_dur_ms",
            return_value=False,
        ), mock.patch(
            "server_handlers.stitch_editor.apply_stitch_slot_default_ambient_preset",
            return_value=False,
        ):
            stitch_upsert_event_slot(
                h,
                "Event_1",
                "phase_b",
                {"video_path": "Production/Event_1/preview/phase_b/phase_b_preview_abc.mp4"},
            )
        slots = h.app.stitch_state.state["jobs"]["Event_1_stitch"]["slots"]
        self.assertIn("resolution", slots)
        self.assertIn("phase_b", slots)
        self.assertTrue(slots["phase_b"]["video_path"].endswith("phase_b_preview_abc.mp4"))

    def test_slot_order_constant(self):
        self.assertEqual(
            STITCH_SLOT_ORDER,
            ["intro", "phase_a", "phase_b", "resolution"],
        )


if __name__ == "__main__":
    unittest.main()
