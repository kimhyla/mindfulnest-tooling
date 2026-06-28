"""STITCH_SINGLE_OWNER_V1 — load_job read-only; export upsert persists video."""

from __future__ import annotations

import json
import tempfile
import unittest
import unittest.mock
from pathlib import Path
from unittest.mock import MagicMock

from server_handlers import stitch_editor as se
from server_handlers.stitch_editor import STITCH_SINGLE_OWNER_V1


class StitchSingleOwnerSourceGuards(unittest.TestCase):
    def test_load_job_handler_markers(self) -> None:
        src = Path(se.__file__).read_text(encoding="utf-8")
        block = src.split("def handle_stitch_load_job", 1)[1].split(
            "\ndef handle_stitch_serve_module_final", 1,
        )[0]
        self.assertIn(STITCH_SINGLE_OWNER_V1, src)
        self.assertIn("job_persisted", block)
        self.assertNotIn("persist_milestone_hydrate", block)
        self.assertNotIn("bootstrap_milestone_job", block)
        self.assertNotIn("hydrate_stitch_canonical_slots_from_disk(h, state, event_id)", block)
        self.assertNotIn('trigger="load_job"', block)
        self.assertIn("STITCH_WRITE_TIME_PLAYBACK_ARTIFACTS_V1", block)

    def test_hydrate_helpers_retained_for_export_migration(self) -> None:
        src = Path(se.__file__).read_text(encoding="utf-8")
        self.assertIn("def hydrate_milestone_standalone_from_disk", src)
        self.assertIn("def hydrate_stitch_canonical_slots_from_disk", src)

    def test_milestone_save_uses_partition_scope(self) -> None:
        src = Path(se.__file__).read_text(encoding="utf-8")
        self.assertIn("STITCH_SCOPE_PARTITION_V1", src)
        save_block = src.split("def handle_stitch_save_job", 1)[1].split(
            "\ndef handle_stitch_delete_job", 1,
        )[0]
        self.assertIn("assert_stitch_partition_scope", save_block)
        preview_block = src.split("def handle_stitch_preview", 1)[1].split(
            "\ndef handle_stitch", 1,
        )[0]
        self.assertIn("assert_stitch_partition_scope", preview_block)


class LoadJobNoDiskHydratePersist(unittest.TestCase):
    def test_milestone_load_does_not_persist_assembled_hydrate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            mid = "milestone1_arc1"
            job_name = se.stitch_milestone_job_name(mid)
            stitch_path = root / "Production" / "Milestones" / mid / "stitch_state.json"
            stitch_path.parent.mkdir(parents=True)
            assembled = root / "Production" / "Milestones" / mid / "assembled"
            assembled.mkdir(parents=True)
            (assembled / "standalone_kling_o3_20260625T233953Z.mp4").write_bytes(b"\x00" * 64)
            stitch_path.write_text(json.dumps({"version": 1, "jobs": {}}), encoding="utf-8")

            from production_server import StitchEditorState  # noqa: PLC0415

            store = StitchEditorState(stitch_path)
            h = MagicMock()
            h.app.stitch_state = store
            h.app.event_dir = root / "Event_2"
            h._stitch_project_root = lambda: root
            h._stitch_resolve_path = lambda p: str(root / p)
            h._send_json = MagicMock()
            h._send_error_v59 = MagicMock()
            h._stitch_cache_dir = lambda: root / "cache"
            (root / "cache").mkdir(parents=True, exist_ok=True)

            with unittest.mock.patch(
                "stitch_bake_job_store.active_bake_job_summary",
                return_value=None,
            ), unittest.mock.patch(
                "server_handlers.stitch_editor.collect_stitch_job_slot_warnings",
                return_value={},
            ), unittest.mock.patch(
                "server_handlers.stitch_editor.ensure_job_slot_defaults",
                return_value=False,
            ), unittest.mock.patch(
                "server_handlers.stitch_editor.ensure_stitch_slot_timeline_dur_ms",
                return_value=False,
            ), unittest.mock.patch(
                "server_handlers.stitch_media_artifacts.validate_stitch_slot_media_artifacts",
                return_value=[],
            ):
                se.handle_stitch_load_job(h, job_name)

            saved = json.loads(stitch_path.read_text(encoding="utf-8"))
            self.assertEqual(saved.get("jobs", {}), {})
            h._send_json.assert_called()
            payload = h._send_json.call_args[0][1]
            self.assertFalse(payload.get("job_persisted"))
            self.assertTrue(payload.get("ephemeral_milestone_job"))
            job = payload.get("job") or {}
            standalone = (job.get("slots") or {}).get("standalone") or {}
            self.assertFalse((standalone.get("video_path") or "").strip())


if __name__ == "__main__":
    unittest.main()
