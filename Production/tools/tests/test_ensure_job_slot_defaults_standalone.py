"""ensure_job_slot_defaults applies ambient preset to milestone standalone slots."""

from __future__ import annotations

import unittest
import unittest.mock as mock

from server_handlers.stitch_editor import (
    STITCH_AMBIENT_BED_VOLUME,
    ensure_job_slot_defaults,
)


class EnsureJobSlotDefaultsStandaloneTests(unittest.TestCase):
    def test_standalone_gets_intro_ambient_bed_when_video_present(self) -> None:
        slots = {
            "standalone": {
                "video_path": "Production/Milestones/milestone1_arc1/assembled/out.mp4",
            },
        }
        h = mock.MagicMock()
        with mock.patch(
            "server_handlers.stitch_editor.strip_stale_pipeline_boundary_slot_cues",
            return_value=False,
        ), mock.patch(
            "server_handlers.stitch_editor.strip_stale_resolution_head_sfx_cues",
            return_value=False,
        ), mock.patch(
            "server_handlers.stitch_editor.sync_stitch_slot_video_dur_ms",
            return_value=False,
        ):
            changed = ensure_job_slot_defaults(h, slots, fast=True)
        self.assertTrue(changed)
        self.assertEqual(slots["standalone"]["ambient_bed"], "Intro video ambient bed")
        self.assertEqual(slots["standalone"]["ambient_volume"], STITCH_AMBIENT_BED_VOLUME)


if __name__ == "__main__":
    unittest.main()
