"""Milestone stitch bake — same lean delivery gates as event module bake."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS.parent.parent))

from Production.tools.server_handlers import stitch_editor as se  # noqa: E402


class MilestoneBakeParitySourceTests(unittest.TestCase):
    def test_bake_core_skips_phase_b_for_milestone(self) -> None:
        src = Path(se.__file__).read_text(encoding="utf-8")
        block = src.split("def _run_stitch_bake_core", 1)[1].split("\ndef _execute_stitch_bake_job", 1)[0]
        self.assertIn("milestone_bake = is_milestone_stitch_job_name(job_name)", block)
        self.assertIn("if not milestone_bake:", block)
        self.assertIn("finalize_milestone_stitch_bake", block)

    def test_hydrate_uses_milestone_stitch_store(self) -> None:
        src = Path(se.__file__).read_text(encoding="utf-8")
        block = src.split("def hydrate_stitch_pipeline_body", 1)[1].split("\ndef _coerce_stitch_pipeline_slots_to_list", 1)[0]
        self.assertIn("stitch_state_store_for_job(h, job_name)", block)
        self.assertIn("STITCH_MILESTONE_SLOT_ORDER", block)

    def test_persist_bake_pointer_uses_job_store(self) -> None:
        src = Path(se.__file__).read_text(encoding="utf-8")
        block = src.split("def _persist_stitch_bake_job_pointer", 1)[1].split("\ndef _milestone_dir_for_stitch_job", 1)[0]
        self.assertIn("stitch_state_store_for_job(h, stitch_job_name)", block)
        self.assertNotIn("h.app.stitch_state.mutate_state(mutate)", block)

    def test_load_job_persists_hydrated_milestone_bake_path(self) -> None:
        src = Path(se.__file__).read_text(encoding="utf-8")
        block = src.split("def handle_stitch_load_job", 1)[1].split("\ndef handle_stitch_serve_module_final", 1)[0]
        self.assertIn("hydrated_bake_path", block)
        self.assertIn('j["bake_path"] = hydrated_bake_path', block)
        self.assertNotIn('j["bake_path"] = canonical_bake_path', block)

    def test_load_job_embeds_module_final_cache_key_on_job(self) -> None:
        src = Path(se.__file__).read_text(encoding="utf-8")
        block = src.split("def handle_stitch_load_job", 1)[1].split("\ndef handle_stitch_serve_module_final", 1)[0]
        self.assertIn('response_job["module_final_cache_key"]', block)

    def test_module_final_serves_milestone_scope(self) -> None:
        src = Path(se.__file__).read_text(encoding="utf-8")
        block = src.split("def handle_stitch_serve_module_final", 1)[1].split("\n\nSTITCH_AMBIENT", 1)[0]
        self.assertIn('_canonical_milestone_standalone_final_path', block)


class PinMilestoneStandaloneFinalTests(unittest.TestCase):
    def test_pins_assembled_final_without_event_production_state(self) -> None:
        from stitch_bake_finalize import finalize_milestone_stitch_bake  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            event_dir = root / "Event_2"
            event_dir.mkdir()
            (event_dir / "production_state.json").write_text(
                json.dumps({"event_id": "M2E2", "canonical_module_final_file": "M2_event_2_final.mp4"}),
                encoding="utf-8",
            )
            milestone_dir = root / "Production" / "Milestones" / "milestone1_arc1"
            milestone_dir.mkdir(parents=True)
            (milestone_dir / "state.json").write_text(
                json.dumps({"milestone_id": "milestone1_arc1", "videos": {"standalone": {}}}),
                encoding="utf-8",
            )
            export = event_dir / "exports" / "stitch_test_final.mp4"
            export.parent.mkdir(parents=True)
            export.write_bytes(b"\x00" * 128)

            with patch("stitch_bake_finalize._ffprobe_duration_ms", return_value=1000), patch(
                "stitch_bake_finalize._sha256_file", return_value="abc123",
            ), patch("video_delivery.ensure_mp4_playback_timestamps"):
                result = finalize_milestone_stitch_bake(
                    milestone_dir,
                    export,
                    job_name="milestone_milestone1_arc1_stitch",
                    delivery_profile="module_final_lean",
                )

            canonical = milestone_dir / "assembled" / "milestone1_arc1_standalone_final.mp4"
            self.assertTrue(canonical.is_file())
            self.assertEqual(result["canonical_name"], "milestone1_arc1_standalone_final.mp4")
            self.assertFalse(result["directus_approved"])

            prod = json.loads((event_dir / "production_state.json").read_text(encoding="utf-8"))
            self.assertEqual(prod.get("canonical_module_final_file"), "M2_event_2_final.mp4")

            mstate = json.loads((milestone_dir / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(
                mstate.get("canonical_standalone_final_file"),
                "milestone1_arc1_standalone_final.mp4",
            )


if __name__ == "__main__":
    unittest.main()
