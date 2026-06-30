#!/usr/bin/env python3
"""STITCH_ARTIFACT_ORCHESTRATOR_V1 — orchestrator unit tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

from server_handlers import stitch_artifact_build as sab  # noqa: E402


class StitchArtifactOrchestratorTests(unittest.TestCase):
    def test_exports_orchestrator_marker(self) -> None:
        assert sab.STITCH_ARTIFACT_ORCHESTRATOR_V1
        assert callable(sab.submit_stitch_artifact_build_plan)
        assert callable(sab.wait_for_artifact_build)
        assert callable(sab.reconcile_stale_artifact_builds)

    def test_save_job_wires_mux_and_ambient_plan(self) -> None:
        src = (TOOLS / "server_handlers" / "stitch_editor.py").read_text(encoding="utf-8")
        block = src.split("def handle_stitch_save_job", 1)[1].split("\ndef handle_stitch_delete_job", 1)[0]
        assert "submit_stitch_artifact_build_plan" in block
        assert "mux_keys" in block
        assert "STITCH_ARTIFACT_ORCHESTRATOR_V1" in block

    def test_preview_uses_orchestrator_not_direct_pipeline(self) -> None:
        src = (TOOLS / "server_handlers" / "stitch_editor.py").read_text(encoding="utf-8")
        block = src.split("def handle_stitch_preview", 1)[1].split("\ndef _persist_stitch_bake_job_pointer", 1)[0]
        assert "submit_stitch_artifact_build_plan" in block
        assert "wait_for_artifact_build" in block
        assert "_stitch_build_pipeline(hydrated)" not in block

    def test_build_poll_payload_includes_mux_keys(self) -> None:
        payload = sab.build_poll_payload({
            "build_id": "abc",
            "status": "queued",
            "phase": "queued",
            "ambient_rebuild_keys": ["standalone"],
            "mux_rebuild_keys": ["standalone"],
        })
        assert payload["code"] == sab.STITCH_ARTIFACT_ORCHESTRATOR_V1
        assert payload["mux_rebuild_keys"] == ["standalone"]

    def test_worker_swaps_stitch_state_for_milestone_job(self) -> None:
        src = (TOOLS / "server_handlers" / "stitch_artifact_build.py").read_text(encoding="utf-8")
        block = src.split("def _execute_artifact_plan", 1)[1].split("\ndef _start_worker", 1)[0]
        assert "stitch_state_store_for_job" in block
        assert "orig_stitch_state" in block
        assert "h.app.stitch_state = stitch_store" in block

    def test_client_strip_stale_preserves_ambient_tier(self) -> None:
        src = (TOOLS / "storyboard-v2" / "src" / "utils" / "stitchSlotMuxAudioSig.ts").read_text(
            encoding="utf-8",
        )
        block = src.split("export function stripStaleStitchSlotArtifacts", 1)[1].split("\n}", 1)[0]
        assert "ambient_mix_hash" not in block
        assert "mux_preview_hash" in block
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            event_dir = Path(tmp)
            jobs_dir = sab.artifact_builds_dir(event_dir)
            path = jobs_dir / "stale1.json"
            path.write_text(
                json.dumps(
                    {
                        "build_id": "stale1",
                        "status": "running",
                        "phase": "ambient_mix",
                        "stitch_job_name": "test_job",
                        "updated_at": "2020-01-01T00:00:00+00:00",
                    },
                ),
                encoding="utf-8",
            )
            reconciled = sab.reconcile_stale_artifact_builds(event_dir, stale_after_s=60.0)
            self.assertIn("stale1", reconciled)
            loaded = sab.load_build(event_dir, "stale1")
            assert loaded is not None
            self.assertEqual(loaded["status"], "failed")


if __name__ == "__main__":
    unittest.main()
