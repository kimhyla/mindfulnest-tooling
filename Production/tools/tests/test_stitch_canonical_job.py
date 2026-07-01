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

    def read_state(self):
        return self.state

    def mutate_state(self, fn):
        fn(self.state)


class _MockApp:
    def __init__(self, state=None):
        self.stitch_state = _MockStitchState(state)
        self._event_stitch_state = self.stitch_state
        self.event_dir = "Production/Event_1"


class _MockHandler:
    def __init__(self, state=None):
        self.app = _MockApp(state)

    def _stitch_project_root(self):
        from pathlib import Path
        return Path("/tmp/mn-stitch-test")

    def _stitch_resolve_path(self, raw: str) -> str:
        return raw

    def _ffprobe_duration_ms(self, _path) -> int:
        return 60_000


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
        ), mock.patch(
            "server_handlers.stitch_editor.ensure_stitch_slot_canonical_default_sfx_cues",
            return_value=False,
        ), mock.patch(
            "server_handlers.stitch_slot_playback.bake_slot_playback_mp4",
            return_value=60.0,
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
        self.assertIn("assembled/phase_b_playback_", slots["phase_b"]["video_path"])

    def test_slot_order_constant(self):
        self.assertEqual(
            STITCH_SLOT_ORDER,
            ["intro", "phase_a", "phase_b", "resolution"],
        )


if __name__ == "__main__":
    unittest.main()
