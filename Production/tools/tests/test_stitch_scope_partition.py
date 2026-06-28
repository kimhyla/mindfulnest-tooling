"""STITCH_SCOPE_PARTITION_V1 — stitch partition scope on dedicated event servers."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from server_handlers import stitch_scope as ss
from server_handlers import stitch_editor as se


class StitchScopePartitionSourceGuards(unittest.TestCase):
    def test_milestone_scope_documents_stitch_partition(self) -> None:
        src = Path(__import__("server_handlers.milestone_scope", fromlist=[""]).__file__).read_text(
            encoding="utf-8",
        )
        self.assertIn("STITCH_SCOPE_PARTITION_V1", src)

    def test_save_and_preview_use_partition_scope(self) -> None:
        src = Path(se.__file__).read_text(encoding="utf-8")
        save_block = src.split("def handle_stitch_save_job", 1)[1].split(
            "\ndef handle_stitch_delete_job", 1,
        )[0]
        preview_block = src.split("def handle_stitch_preview", 1)[1].split(
            "\ndef handle_stitch", 1,
        )[0]
        self.assertIn("assert_stitch_partition_scope", save_block)
        self.assertIn("assert_stitch_partition_scope", preview_block)
        self.assertNotIn("_assert_stitch_mutation_scope", src)


class AssertStitchPartitionScopeTests(unittest.TestCase):
    def test_milestone_job_on_event_dedicated_server_resolves_milestone_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            mid = "milestone1_arc1"
            event_dir = root / "Production" / "Event_2"
            event_dir.mkdir(parents=True)
            mdir = root / "Production" / "Milestones" / mid
            mdir.mkdir(parents=True)
            (mdir / "stitch_state.json").write_text(
                json.dumps({"version": 1, "jobs": {}}),
                encoding="utf-8",
            )
            (event_dir / "production_state.json").write_text(
                json.dumps({"videos": {"intro": {}, "resolution": {}}}),
                encoding="utf-8",
            )

            from production_server import StitchEditorState  # noqa: PLC0415

            global_store = StitchEditorState(root / "Production" / "tools" / "stitch_editor_state.json")
            h = MagicMock()
            h.app.event_dir = event_dir
            h.app.stitch_state = global_store
            h.app.scope_type = "event"
            h.app.event_generation = 1
            h.app.state._VALID_VIDEO_ROLES = {"intro", "resolution", "standalone"}
            h.app.state.validate_video_role = lambda role: role in {"intro", "resolution"}
            h._send_error_v59 = MagicMock()

            job_name = f"milestone_{mid}_stitch"
            body = {
                "name": job_name,
                "scope_event_id": "Event_2",
                "scope_milestone_id": mid,
                "scope_video_role": "standalone",
                "event_id": "Event_2",
            }
            binding = ss.assert_stitch_partition_scope(h, body, job_name=job_name)
            self.assertIsNotNone(binding)
            assert binding is not None
            self.assertTrue(binding.ctx.is_milestone)
            self.assertEqual(binding.job_name, job_name)
            self.assertEqual(
                Path(binding.stitch_store.state_path),
                mdir / "stitch_state.json",
            )
            h._send_error_v59.assert_not_called()

    def test_event_stitch_job_accepts_without_state_videos_partition(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            event_dir = root / "Production" / "Event_2"
            event_dir.mkdir(parents=True)
            (event_dir / "production_state.json").write_text(
                json.dumps({"videos": {}}),
                encoding="utf-8",
            )

            from production_server import StitchEditorState  # noqa: PLC0415

            h = MagicMock()
            h.app.event_dir = event_dir
            h.app.stitch_state = StitchEditorState(root / "stitch_editor_state.json")
            h.app.scope_type = "event"
            h.app.event_generation = 1
            h.app.state._VALID_VIDEO_ROLES = {"intro", "resolution", "standalone"}
            h.app.state.validate_video_role = lambda role: False
            h._send_error_v59 = MagicMock()

            body = {
                "name": "Event_2_stitch",
                "scope_event_id": "Event_2",
                "scope_video_role": "standalone",
                "event_id": "Event_2",
            }
            binding = ss.assert_stitch_partition_scope(h, body, job_name="Event_2_stitch")
            self.assertIsNotNone(binding)
            h._send_error_v59.assert_not_called()

    def test_non_event_stitch_job_still_requires_state_videos_partition(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            event_dir = root / "Production" / "Event_2"
            event_dir.mkdir(parents=True)
            (event_dir / "production_state.json").write_text(
                json.dumps({"videos": {"intro": {}, "resolution": {}}}),
                encoding="utf-8",
            )

            from production_server import StitchEditorState  # noqa: PLC0415

            h = MagicMock()
            h.app.event_dir = event_dir
            h.app.stitch_state = StitchEditorState(root / "stitch_editor_state.json")
            h.app.scope_type = "event"
            h.app.event_generation = 1
            h.app.state._VALID_VIDEO_ROLES = {"intro", "resolution", "standalone"}
            h.app.state.validate_video_role = lambda role: role in {"intro", "resolution"}
            h._send_error_v59 = MagicMock()

            body = {
                "name": "custom_stitch",
                "scope_event_id": "Event_2",
                "scope_video_role": "standalone",
                "event_id": "Event_2",
            }
            binding = ss.assert_stitch_partition_scope(h, body, job_name="custom_stitch")
            self.assertIsNone(binding)
            h._send_error_v59.assert_called()
            err = h._send_error_v59.call_args.kwargs.get("extra") or h._send_error_v59.call_args[1].get("extra")
            if err is None and len(h._send_error_v59.call_args[0]) > 4:
                err = h._send_error_v59.call_args[0][4]
            self.assertEqual(err.get("code"), "VIDEO_ROLE_INVALID")


if __name__ == "__main__":
    unittest.main()
