"""O3_SUBPROCESS_LIFECYCLE_V1 — shutdown finalize + startup reconcile."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from o3_generation_intent import (
    finalize_live_o3_jobs_before_shutdown,
    load_intent_terminal,
    terminal_path_for_job,
    write_intent_terminal,
)


class TestO3SubprocessLifecycle(unittest.TestCase):
    def test_shutdown_finalize_marks_live_process_cancelled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            event_dir = Path(tmp)
            (event_dir / "arlo_o3_jobs").mkdir()
            job_id = "lifecycle-running-1"
            beat_id = "bg_test_beat_01"
            write_intent_terminal(
                job_id,
                event_dir,
                {
                    "schema_version": 1,
                    "job_id": job_id,
                    "beat_id": beat_id,
                    "status": "running",
                },
            )
            proc = mock.MagicMock()
            proc.poll.return_value = None
            live = {job_id: {"beat_id": beat_id, "process": proc}}
            with mock.patch(
                "o3_generation_intent.close_o3_attempt",
                return_value=None,
            ) as close_mock:
                n = finalize_live_o3_jobs_before_shutdown(
                    event_dir,
                    in_memory_jobs=live,
                )
            self.assertEqual(n, 1)
            close_mock.assert_called_once()
            args = close_mock.call_args[0]
            self.assertEqual(args[0], job_id)
            self.assertEqual(args[2], event_dir)
            self.assertEqual(close_mock.call_args[0][3], "cancelled")

    def test_shutdown_skips_terminal_done_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            event_dir = Path(tmp)
            (event_dir / "arlo_o3_jobs").mkdir()
            job_id = "lifecycle-done-1"
            write_intent_terminal(
                job_id,
                event_dir,
                {
                    "schema_version": 1,
                    "job_id": job_id,
                    "beat_id": "bg_test_beat_02",
                    "status": "done",
                },
            )
            proc = mock.MagicMock()
            proc.poll.return_value = 0
            live = {job_id: {"beat_id": "bg_test_beat_02", "process": proc}}
            n = finalize_live_o3_jobs_before_shutdown(event_dir, in_memory_jobs=live)
            self.assertEqual(n, 0)
            terminal = load_intent_terminal(terminal_path_for_job(job_id, event_dir))
            assert terminal is not None
            self.assertEqual(terminal.get("status"), "done")

    def test_startup_reconcile_imports_finalize(self) -> None:
        src = Path(__file__).resolve().parents[1] / "production_server.py"
        text = src.read_text(encoding="utf-8")
        self.assertIn("finalize_live_o3_jobs_before_shutdown", text)


if __name__ == "__main__":
    unittest.main()
