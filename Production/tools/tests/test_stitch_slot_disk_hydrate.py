"""STITCH_SLOT_ASSEMBLED_DISK_HYDRATE_V1 — canonical jobs recover missing slots from disk."""
from __future__ import annotations

import unittest
import unittest.mock as mock
from pathlib import Path

from server_handlers.stitch_editor import (
    STITCH_SLOT_ASSEMBLED_DISK_HYDRATE_V1,
    hydrate_stitch_canonical_slots_from_disk,
)


class _MockStitchState:
    def __init__(self, initial=None):
        self.state = initial or {"jobs": {}}


class _MockStateReader:
    def __init__(self, data=None):
        self._data = data or {}

    def read_state(self):
        return self._data


class _MockApp:
    def __init__(self, root: Path, production_state=None):
        self.stitch_state = _MockStitchState()
        self.state = _MockStateReader(production_state)
        self.event_dir = root / "Production" / "Event_1"


class _MockHandler:
    def __init__(self, root: Path, production_state=None):
        self.app = _MockApp(root, production_state)
        self._root = root

    def _stitch_project_root(self) -> Path:
        return self._root

    def _stitch_resolve_path(self, rel: str) -> str:
        return str(self._root / rel)


class StitchSlotDiskHydrateTests(unittest.TestCase):
    def test_hydrates_empty_intro_and_phase_from_disk(self):
        root = Path(self.tmp).resolve()
        event_dir = root / "Production" / "Event_1"
        assembled = event_dir / "assembled"
        assembled.mkdir(parents=True)
        intro = assembled / "intro_kling_o3_test.mp4"
        intro.write_bytes(b"\x00" * 128)
        phase_a = event_dir / "phase_a_stitched_test.mp4"
        phase_a.write_bytes(b"\x00" * 128)

        h = _MockHandler(
            root,
            production_state={
                "phase_a_stitched_file": phase_a.name,
            },
        )
        state = {
            "jobs": {
                "Event_1_stitch": {
                    "slots": {
                        "resolution": {
                            "video_path": "Production/Event_1/assembled/resolution_x.mp4",
                        },
                    },
                },
            },
        }

        with mock.patch(
            "server_handlers.stitch_editor.sync_stitch_slot_video_dur_ms",
            return_value=False,
        ), mock.patch(
            "server_handlers.stitch_editor.apply_stitch_slot_default_ambient_preset",
            return_value=False,
        ):
            changed = hydrate_stitch_canonical_slots_from_disk(h, state, "Event_1")

        self.assertTrue(changed)
        slots = state["jobs"]["Event_1_stitch"]["slots"]
        self.assertIn("intro", slots)
        self.assertIn("phase_a", slots)
        self.assertIn("resolution", slots)
        self.assertTrue(slots["intro"]["video_path"].endswith("intro_kling_o3_test.mp4"))
        self.assertEqual(slots["intro"]["source"], STITCH_SLOT_ASSEMBLED_DISK_HYDRATE_V1)
        self.assertTrue(slots["phase_a"]["video_path"].endswith("phase_a_stitched_test.mp4"))

    def test_does_not_replace_existing_slot_video(self):
        root = Path(self.tmp).resolve()
        event_dir = root / "Production" / "Event_1"
        assembled = event_dir / "assembled"
        assembled.mkdir(parents=True)
        (assembled / "intro_new.mp4").write_bytes(b"\x00" * 64)

        h = _MockHandler(root)
        state = {
            "jobs": {
                "Event_1_stitch": {
                    "slots": {
                        "intro": {"video_path": "Production/Event_1/assembled/intro_keep.mp4"},
                    },
                },
            },
        }

        with mock.patch(
            "server_handlers.stitch_editor.sync_stitch_slot_video_dur_ms",
            return_value=False,
        ), mock.patch(
            "server_handlers.stitch_editor.apply_stitch_slot_default_ambient_preset",
            return_value=False,
        ):
            changed = hydrate_stitch_canonical_slots_from_disk(h, state, "Event_1")

        self.assertFalse(changed)
        self.assertEqual(
            state["jobs"]["Event_1_stitch"]["slots"]["intro"]["video_path"],
            "Production/Event_1/assembled/intro_keep.mp4",
        )

    def test_hydrates_event_2_job_name_from_disk(self):
        root = Path(self.tmp).resolve()
        event_dir = root / "Production" / "Event_2"
        assembled = event_dir / "assembled"
        assembled.mkdir(parents=True)
        resolution = assembled / "resolution_kling_o3_event2.mp4"
        resolution.write_bytes(b"\x00" * 128)

        h = _MockHandler(root)
        h.app.event_dir = event_dir
        state = {"jobs": {"Event_2_stitch": {"slots": {}}}}

        with mock.patch(
            "server_handlers.stitch_editor.sync_stitch_slot_video_dur_ms",
            return_value=False,
        ), mock.patch(
            "server_handlers.stitch_editor.apply_stitch_slot_default_ambient_preset",
            return_value=False,
        ):
            changed = hydrate_stitch_canonical_slots_from_disk(h, state, "Event_2")

        self.assertTrue(changed)
        self.assertIn(
            "resolution_kling_o3_event2.mp4",
            state["jobs"]["Event_2_stitch"]["slots"]["resolution"]["video_path"],
        )

    def setUp(self):
        import tempfile
        self._td = tempfile.TemporaryDirectory()
        self.tmp = self._td.name

    def tearDown(self):
        self._td.cleanup()


if __name__ == "__main__":
    unittest.main()
