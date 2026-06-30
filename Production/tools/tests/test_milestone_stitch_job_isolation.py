#!/usr/bin/env python3
"""Milestone stitch job isolation — category contract tests."""
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


class EventStitchStoreIsolationTests(unittest.TestCase):
    def test_event_job_store_ignores_milestone_swap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prod = root / "Production"
            event_dir = prod / "Event_2"
            event_dir.mkdir(parents=True)
            global_state = prod / "tools" / "stitch_editor_state.json"
            global_state.parent.mkdir(parents=True, exist_ok=True)
            global_state.write_text(json.dumps({"version": 1, "jobs": {}}), encoding="utf-8")
            milestone_state = prod / "Milestones" / "milestone1_arc1" / "stitch_state.json"
            milestone_state.parent.mkdir(parents=True, exist_ok=True)
            milestone_state.write_text(json.dumps({"version": 1, "jobs": {}}), encoding="utf-8")

            from production_server import StitchEditorState  # noqa: PLC0415

            h = MagicMock()
            h.app.event_dir = event_dir
            event_store = StitchEditorState(global_state)
            h.app.stitch_state = event_store
            h.app._event_stitch_state = event_store

            milestone_store = StitchEditorState(milestone_state)
            h.app.stitch_state = milestone_store

            resolved = se.stitch_state_store_for_job(h, "Event_2_stitch")
            self.assertEqual(resolved.state_path, global_state)
            self.assertNotEqual(resolved.state_path, milestone_state)


class MilestoneStitchJobNameTests(unittest.TestCase):
    def test_milestone_id_round_trip(self):
        name = se.stitch_milestone_job_name("milestone1_arc1")
        self.assertEqual(se.milestone_id_from_stitch_job_name(name), "milestone1_arc1")
        self.assertTrue(se.is_milestone_stitch_job_name(name))

    def test_event_job_not_milestone(self):
        self.assertFalse(se.is_milestone_stitch_job_name("Event_2_stitch"))

    def test_legacy_milestone_name_detected(self):
        self.assertEqual(
            se.legacy_milestone_id_from_stitch_job_name("milestone1_arc1_stitch"),
            "milestone1_arc1",
        )
        self.assertIsNone(se.legacy_milestone_id_from_stitch_job_name("Event_2_stitch"))
        self.assertIsNone(
            se.legacy_milestone_id_from_stitch_job_name("milestone_milestone1_arc1_stitch"),
        )


class PurgeLegacyMilestoneStitchJobTests(unittest.TestCase):
    def test_purge_removes_legacy_from_global_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "stitch_editor_state.json"
            state_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "jobs": {
                            "Event_2_stitch": {"slots": {"intro": {}}},
                            "milestone1_arc1_stitch": {"slots": {"intro": {}, "phase_a": {}}},
                        },
                    },
                ),
                encoding="utf-8",
            )
            from production_server import StitchEditorState  # noqa: PLC0415

            h = MagicMock()
            h.app.stitch_state = StitchEditorState(state_path)
            h.app._event_stitch_state = h.app.stitch_state
            removed = se.purge_legacy_milestone_stitch_jobs_from_global(h)
            self.assertEqual(removed, ["milestone1_arc1_stitch"])
            saved = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertIn("Event_2_stitch", saved["jobs"])
            self.assertNotIn("milestone1_arc1_stitch", saved["jobs"])


class NormalizeMilestoneStitchJobTests(unittest.TestCase):
    def test_strips_event_slots_and_wrong_bake_path(self):
        job = {
            "slots": {
                "intro": {},
                "phase_a": {"video_path": "Production/x/a.mp4"},
                "phase_b": {"video_path": "Production/x/b.mp4"},
                "resolution": {},
            },
            "bake_path": "/tmp/Production/Event_2/M2_event_2_final.mp4",
        }
        self.assertTrue(se.normalize_milestone_stitch_job(job))
        self.assertEqual(list(job["slots"].keys()), ["standalone"])
        self.assertNotIn("bake_path", job)

    def test_list_slots_coerce_to_standalone_instead_of_wipe(self):
        job = {
            "slots": [
                {
                    "video_path": "Production/Milestones/m1/assembled/x.mp4",
                    "sfx_cues": [{"id": "c1", "offset_ms": 1000}],
                },
            ],
        }
        self.assertTrue(
            se.normalize_milestone_stitch_job(
                job,
                job_name="milestone_m1_stitch",
            ),
        )
        standalone = job["slots"]["standalone"]
        self.assertEqual(len(standalone.get("sfx_cues") or []), 1)


class MilestoneStitchUpsertTests(unittest.TestCase):
    def test_upsert_creates_milestone_job_on_local_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prod = root / "Production"
            event_dir = prod / "Event_2"
            event_dir.mkdir(parents=True)
            milestone_dir = prod / "Milestones" / "milestone1_arc1"
            milestone_dir.mkdir(parents=True)
            global_state = prod / "tools" / "stitch_editor_state.json"
            global_state.parent.mkdir(parents=True, exist_ok=True)
            global_state.write_text(json.dumps({"version": 1, "jobs": {}}), encoding="utf-8")

            from production_server import StitchEditorState  # noqa: PLC0415

            h = MagicMock()
            h.app.event_dir = event_dir
            h.app.stitch_state = StitchEditorState(global_state)
            h._stitch_project_root = lambda: root  # noqa: ARG005
            h._stitch_resolve_path = lambda p: root / p  # noqa: ARG005

            video = milestone_dir / "assembled" / "out.mp4"
            video.parent.mkdir(parents=True, exist_ok=True)
            video.write_bytes(b"\x00" * 64)

            def fake_preflight(_h, _path, _slot, beat_boundaries=None):  # noqa: ARG001
                return 5000, []

            se.stitch_slot_export_media_preflight = fake_preflight
            se.sync_stitch_slot_video_dur_ms = lambda *_a, **_k: None
            se.apply_stitch_slot_default_ambient_preset = lambda *_a, **_k: False

            job_name = se.stitch_milestone_job_name("milestone1_arc1")
            name, dur_ms, warnings, _playback = se.stitch_upsert_event_slot(
                h,
                "milestone1_arc1",
                "standalone",
                {"video_path": "Production/Milestones/milestone1_arc1/assembled/out.mp4"},
                operator_export=True,
                job_name=job_name,
            )
            self.assertEqual(name, job_name)
            self.assertEqual(dur_ms, 5000)
            self.assertEqual(warnings, [])
            milestone_path = milestone_dir / "stitch_state.json"
            saved = json.loads(milestone_path.read_text(encoding="utf-8"))
            slots = saved["jobs"][job_name]["slots"]
            self.assertEqual(list(slots.keys()), ["standalone"])
            self.assertIn("video_path", slots["standalone"])

    def test_upsert_uses_stitch_state_store_for_job(self) -> None:
        src = Path(se.__file__).read_text(encoding="utf-8")
        block = src.split("def stitch_upsert_event_slot", 1)[1].split("\ndef handle_stitch_loudnorm", 1)[0]
        self.assertIn("stitch_store = stitch_state_store_for_job(h, job_name)", block)
        self.assertIn("stitch_store.mutate_state(upsert)", block)
        self.assertNotIn("h.app.stitch_state.mutate_state(upsert)", block)


class PurgeMilestoneGlobalIsolationTests(unittest.TestCase):
    def test_purge_milestone_never_touches_milestone_local_when_stitch_state_swapped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prod = root / "Production"
            event_dir = prod / "Event_2"
            event_dir.mkdir(parents=True)
            global_state = event_dir / "tools" / "stitch_editor_state.json"
            global_state.parent.mkdir(parents=True, exist_ok=True)
            global_state.write_text(json.dumps({"version": 1, "jobs": {}}), encoding="utf-8")
            milestone_state = prod / "Milestones" / "milestone1_arc1" / "stitch_state.json"
            milestone_state.parent.mkdir(parents=True, exist_ok=True)
            job_name = se.stitch_milestone_job_name("milestone1_arc1")
            milestone_state.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "jobs": {
                            job_name: {
                                "slots": {
                                    "standalone": {
                                        "video_path": "Production/Milestones/milestone1_arc1/assembled/out.mp4",
                                    },
                                },
                            },
                        },
                    },
                ),
                encoding="utf-8",
            )

            from production_server import StitchEditorState  # noqa: PLC0415

            h = MagicMock()
            h.app.event_dir = event_dir
            global_store = StitchEditorState(global_state)
            milestone_store = StitchEditorState(milestone_state)
            h.app.stitch_state = milestone_store  # leaked swap from prior save
            h.app._event_stitch_state = global_store

            se.purge_milestone_job_from_global_stitch_state(h, job_name)
            saved = json.loads(milestone_state.read_text(encoding="utf-8"))
            self.assertIn(job_name, saved["jobs"])


class MilestoneLoadJobNoHydrateTests(unittest.TestCase):
    def test_load_job_single_owner_contract(self):
        src = Path(se.__file__).read_text(encoding="utf-8")
        block = src.split("def handle_stitch_load_job", 1)[1].split("\ndef handle_stitch_serve_module_final", 1)[0]
        self.assertIn("STITCH_SINGLE_OWNER_V1", src)
        self.assertIn("job_persisted", block)
        self.assertIn("purge_milestone_job_from_global_stitch_state", block)
        self.assertIn("stitch_state_store_for_job", block)
        self.assertNotIn("persist_milestone_hydrate", block)
        self.assertNotIn("hydrate_stitch_canonical_slots_from_disk(h, state, event_id)", block)


if __name__ == "__main__":
    unittest.main()
