"""Milestone stitch standalone disk hydrate (STITCH_SFX_PLAYBACK_TRUTH_V1)."""
from __future__ import annotations

import tempfile
import unittest
import unittest.mock as mock
from pathlib import Path

from server_handlers import stitch_editor as se
from server_handlers.stitch_editor import STITCH_SLOT_ASSEMBLED_DISK_HYDRATE_V1


class MilestoneStitchDiskHydrateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()

    def test_hydrate_fills_empty_standalone_from_assembled(self) -> None:
        root = Path(self.tmp).resolve()
        mid = "milestone1_arc1"
        assembled = root / "Production" / "Milestones" / mid / "assembled"
        assembled.mkdir(parents=True)
        mp4 = assembled / "standalone_kling_o3_20260625T233953Z.mp4"
        mp4.write_bytes(b"\x00" * 128)

        class _Handler:
            def _stitch_project_root(self) -> Path:
                return root

            def _stitch_resolve_path(self, rel: str) -> str:
                return str(root / rel)

        h = _Handler()
        state = {
            "jobs": {
                f"milestone_{mid}_stitch": {
                    "slots": {"standalone": {}},
                    "transitions": [],
                }
            }
        }
        job_name = f"milestone_{mid}_stitch"
        with mock.patch(
            "server_handlers.stitch_editor.sync_stitch_slot_video_dur_ms",
            return_value=False,
        ), mock.patch(
            "server_handlers.stitch_editor.apply_stitch_slot_default_ambient_preset",
            return_value=False,
        ):
            changed = se.hydrate_milestone_standalone_from_disk(h, state, job_name)
        self.assertTrue(changed)
        slot = state["jobs"][job_name]["slots"]["standalone"]
        self.assertIn("standalone_kling_o3", slot.get("video_path", ""))
        self.assertEqual(slot.get("source"), STITCH_SLOT_ASSEMBLED_DISK_HYDRATE_V1)


if __name__ == "__main__":
    unittest.main()
