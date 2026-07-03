"""O3_JOB_TRUTH_STACK_V1 — resolve_beat_o3_truth authority tests."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from o3_generation_intent import write_intent_terminal
from o3_job_truth import O3_JOB_TRUTH_STACK_V1, resolve_beat_o3_truth


class TestO3JobTruthStack(unittest.TestCase):
    def test_terminal_failed_beats_sidecar_running_latch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            event_dir = Path(tmp)
            jobs = event_dir / "arlo_o3_jobs"
            jobs.mkdir()
            clips = event_dir / "kling_o3_clips"
            clips.mkdir()
            beat_id = "bg_arc1_event4_pre_beat_15"
            g3 = clips / f"{beat_id}_g3_element_o3_master_delivery.mp4"
            g3.write_bytes(b"g3")
            job_id = "7860a4d9-test"
            write_intent_terminal(
                job_id,
                event_dir,
                {
                    "schema_version": 1,
                    "job_id": job_id,
                    "beat_id": beat_id,
                    "status": "failed",
                    "failure": {"message": "O3 job ended without terminal record"},
                    "intent": {"generation_slot": "g4"},
                },
            )
            beat = {
                "beat_id": beat_id,
                "status": "o3_element_running",
                "kling_o3_status": "submitted",
                "kling_o3_voice_fix_status": "o3_element_running",
                "kling_o3_generation": 4,
                "o3_current_job_id": job_id,
                "kling_o3_options": [
                    {"key": "g3", "video_path": str(g3), "generation": 3},
                ],
            }
            with mock.patch(
                "o3_job_status_contract.beat_o3_operator_busy",
                return_value=False,
            ):
                truth = resolve_beat_o3_truth(beat_id, event_dir, beat, sidecar={})
            self.assertEqual(truth["authority"], O3_JOB_TRUTH_STACK_V1)
            self.assertEqual(truth["terminal_status"], "failed")
            self.assertFalse(truth["operator_busy"])
            reconciled = truth["reconciled_beat"]
            self.assertEqual(reconciled["kling_o3_status"], "approved")
            self.assertEqual(
                Path(reconciled["kling_o3_video_path"]).resolve(),
                g3.resolve(),
            )


if __name__ == "__main__":
    unittest.main()
