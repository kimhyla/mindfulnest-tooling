#!/usr/bin/env python3
"""Milestone stitch upsert must persist to milestone-local stitch_state.json."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS.parent.parent))

from Production.tools.server_handlers import stitch_editor as se  # noqa: E402


class MilestoneStitchUpsertStoreTests(unittest.TestCase):
    def test_upsert_writes_milestone_local_stitch_state_not_global(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prod = root / "Production"
            event_dir = prod / "Event_2"
            event_dir.mkdir(parents=True)
            milestone_dir = prod / "Milestones" / "milestone1_arc1"
            milestone_dir.mkdir(parents=True)
            (milestone_dir / "state.json").write_text(
                json.dumps({"milestone_id": "milestone1_arc1"}),
                encoding="utf-8",
            )
            global_state = prod / "tools" / "stitch_editor_state.json"
            global_state.parent.mkdir(parents=True, exist_ok=True)
            global_state.write_text(json.dumps({"version": 1, "jobs": {}}), encoding="utf-8")

            from production_server import StitchEditorState  # noqa: PLC0415

            h = MagicMock()
            h.app.event_dir = event_dir
            h.app.stitch_state = StitchEditorState(global_state)
            h._stitch_project_root = lambda: root  # noqa: ARG005
            h._stitch_resolve_path = lambda p: root / p  # noqa: ARG005

            video = milestone_dir / "assembled" / "standalone_test.mp4"
            video.parent.mkdir(parents=True, exist_ok=True)
            video.write_bytes(b"\x00" * 256)

            se.stitch_slot_export_media_preflight = lambda *_a, **_k: (5000, [])  # noqa: ARG005
            se.sync_stitch_slot_video_dur_ms = lambda *_a, **_k: None
            se.apply_stitch_slot_default_ambient_preset = lambda *_a, **_k: False

            job_name = se.stitch_milestone_job_name("milestone1_arc1")
            rel = "Production/Milestones/milestone1_arc1/assembled/standalone_test.mp4"
            name, dur_ms, warnings, _playback = se.stitch_upsert_event_slot(
                h,
                "milestone1_arc1",
                "standalone",
                {"video_path": rel},
                operator_export=True,
                job_name=job_name,
            )
            self.assertEqual(name, job_name)
            self.assertEqual(dur_ms, 5000)
            self.assertEqual(warnings, [])

            milestone_state_path = milestone_dir / "stitch_state.json"
            self.assertTrue(milestone_state_path.is_file(), "milestone stitch_state.json missing")
            milestone_saved = json.loads(milestone_state_path.read_text(encoding="utf-8"))
            slot = milestone_saved["jobs"][job_name]["slots"]["standalone"]
            self.assertEqual(slot["video_path"], rel)

            global_saved = json.loads(global_state.read_text(encoding="utf-8"))
            self.assertNotIn(job_name, global_saved.get("jobs", {}))


if __name__ == "__main__":
    unittest.main()
