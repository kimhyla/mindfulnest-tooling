"""O3_FAILED_REDO_HEAL_V1 — failed g4+ restores prior on-disk delivery."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import beat_generator as bg
from o3_generation_intent import restore_last_good_o3_delivery_after_failed_attempt


class TestO3FailedRedoHeal(unittest.TestCase):
    def test_failed_g4_restores_g3_when_submitted_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            event_dir = Path(tmp)
            clips = event_dir / "kling_o3_clips"
            clips.mkdir(parents=True)
            beat_id = "bg_arc1_event4_pre_beat_15"
            g3 = clips / f"{beat_id}_g3_element_o3_master_delivery.mp4"
            g3.write_bytes(b"g3")
            beat = {
                "beat_id": beat_id,
                "status": "o3_element_running",
                "kling_o3_status": "submitted",
                "kling_o3_voice_fix_status": "o3_element_running",
                "kling_o3_generation": 4,
                "kling_o3_video_path": str(clips / f"{beat_id}_g4.mp4"),
                "kling_o3_options": [
                    {
                        "key": "g3",
                        "video_path": str(g3),
                        "generation": 3,
                        "active": False,
                    },
                ],
                "o3_current_job_id": "job-failed-g4",
            }
            with mock.patch(
                "o3_job_status_contract.beat_o3_operator_busy",
                return_value=False,
            ):
                ok = restore_last_good_o3_delivery_after_failed_attempt(
                    beat,
                    event_dir,
                    failed_generation=4,
                )
            self.assertTrue(ok)
            self.assertEqual(beat["kling_o3_status"], "approved")
            self.assertEqual(beat["status"], "approved")
            self.assertEqual(beat["kling_o3_voice_fix_status"], "approved")
            self.assertEqual(Path(beat["kling_o3_video_path"]).resolve(), g3.resolve())
            self.assertEqual(beat["kling_o3_generation"], 3)
            self.assertNotIn("o3_current_job_id", beat)

    def test_reconcile_imports_disk_g3_when_options_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            event_dir = Path(tmp)
            clips = event_dir / "kling_o3_clips"
            clips.mkdir(parents=True)
            beat_id = "bg_arc1_event4_pre_beat_15"
            g3 = clips / f"{beat_id}_g3_element_o3_master_delivery.mp4"
            g3.write_bytes(b"g3")
            beat = {
                "beat_id": beat_id,
                "status": "o3_element_running",
                "kling_o3_status": "submitted",
                "kling_o3_generation": 4,
                "kling_o3_options": [],
            }
            with mock.patch(
                "o3_job_status_contract.beat_o3_operator_busy",
                return_value=False,
            ):
                ok = restore_last_good_o3_delivery_after_failed_attempt(
                    beat,
                    event_dir,
                    failed_generation=4,
                )
            self.assertTrue(ok)
            self.assertTrue(Path(beat["kling_o3_video_path"]).is_file())


if __name__ == "__main__":
    unittest.main()
