#!/usr/bin/env python3
"""O3 subprocess must bootstrap milestone sidecar/SQLite — not global JSON first."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

import beat_generator as bg  # noqa: E402
from o3_subprocess_bootstrap import (  # noqa: E402
    inject_o3_subprocess_scope_env,
    load_o3_beat_context,
)


class O3SubprocessBootstrapTests(unittest.TestCase):
    def test_inject_milestone_scope_env(self):
        env: dict = {}
        app = SimpleNamespace(
            scope_type="milestone",
            active_milestone_id="milestone_test_01",
            milestone_dir=Path("/tmp/milestones/milestone_test_01"),
            milestone_library_event_dir=Path("/tmp/Production/Event_1"),
            event_dir=Path("/tmp/Production/Event_2"),
        )
        with mock.patch(
            "lib.milestone_store.load_milestone_state",
            return_value={"skeleton_ref": {"arc_number": 1, "event_id": "3b", "phase": "full"}},
        ), mock.patch(
            "lib.milestone_store.resolve_milestone_skeleton_ref",
            return_value={"arc_number": 1, "event_id": "3b", "phase": "full", "library_event_id": "Event_1"},
        ):
            inject_o3_subprocess_scope_env(env, app)
        self.assertEqual(env["MN_MILESTONE_DIR"], str(app.milestone_dir.resolve()))
        self.assertEqual(env["MN_BG_LIBRARY_EVENT_DIR"], str(app.milestone_library_event_dir.resolve()))
        self.assertEqual(env["MN_O3_EVENT_DIR"], str(app.milestone_library_event_dir.resolve()))
        skel = json.loads(env["MN_MILESTONE_SKELETON_REF"])
        self.assertEqual(skel["event_id"], "3b")

    def test_inject_event_scope_clears_milestone_keys(self):
        env = {
            "MN_MILESTONE_DIR": "/stale",
            "MN_BG_LIBRARY_EVENT_DIR": "/stale",
            "MN_MILESTONE_SKELETON_REF": "{}",
        }
        app = SimpleNamespace(
            scope_type="event",
            active_milestone_id=None,
            event_dir=Path("/tmp/Production/Event_2"),
        )
        inject_o3_subprocess_scope_env(env, app)
        self.assertNotIn("MN_MILESTONE_DIR", env)
        self.assertEqual(env["MN_O3_EVENT_DIR"], str(app.event_dir.resolve()))

    def test_inject_event_scope_copies_beatgen_db_path(self):
        env: dict = {}
        app = SimpleNamespace(
            scope_type="event",
            active_milestone_id=None,
            event_dir=Path("/tmp/Production/Event_3"),
        )
        with mock.patch.dict(
            os.environ,
            {"MN_BEATGEN_DB_PATH": "/tmp/beatgen_event3.db"},
            clear=False,
        ):
            inject_o3_subprocess_scope_env(env, app)
        self.assertEqual(env["MN_BEATGEN_DB_PATH"], "/tmp/beatgen_event3.db")

    def test_load_o3_beat_context_milestone_sidecar(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lib = root / "Event_1"
            lib.mkdir()
            mdir = root / "Milestones" / "milestone_blank_x"
            mdir.mkdir(parents=True)
            beat_id = "bg_arc1_event3b_full_beat_01"
            sidecar = {
                "schema_version": 3,
                "active_context": {"arc_number": 1, "event_id": "3b", "phase": "full"},
                "arcs": {
                    "arc_1": {
                        "segments": {
                            "event_3b_full": {
                                "beats": [{"beat_id": beat_id, "speaker": "Oliver", "dialogue_text": "Hi"}],
                            },
                        },
                    },
                },
            }
            (mdir / "beat_generator_sidecar.json").write_text(json.dumps(sidecar), encoding="utf-8")
            (mdir / "state.json").write_text(
                json.dumps(
                    {
                        "milestone_id": "milestone_blank_x",
                        "skeleton_ref": {"arc_number": 1, "event_id": "3b", "phase": "full"},
                        "library_event_id": "Event_1",
                    }
                ),
                encoding="utf-8",
            )
            os.environ["MN_PROD_ROOT"] = str(root)
            os.environ["MN_MILESTONE_DIR"] = str(mdir)
            os.environ["MN_BG_LIBRARY_EVENT_DIR"] = str(lib)
            os.environ["MN_MILESTONE_SKELETON_REF"] = json.dumps(
                {"arc_number": 1, "event_id": "3b", "phase": "full", "library_event_id": "Event_1"},
            )
            try:
                beat, seg_key, sidecar_path, event_dir = load_o3_beat_context(beat_id)
            finally:
                for key in (
                    "MN_PROD_ROOT",
                    "MN_MILESTONE_DIR",
                    "MN_BG_LIBRARY_EVENT_DIR",
                    "MN_MILESTONE_SKELETON_REF",
                ):
                    os.environ.pop(key, None)
            self.assertEqual(beat["beat_id"], beat_id)
            self.assertEqual(seg_key, "event_3b_full")
            self.assertTrue(str(sidecar_path).endswith("beat_generator_sidecar.json"))
            self.assertEqual(event_dir.resolve(), lib.resolve())

    def test_bootstrap_scope_from_intent_when_env_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lib = root / "Event_1"
            lib.mkdir()
            mdir = root / "Milestones" / "milestone_blank_x"
            mdir.mkdir(parents=True)
            beat_id = "bg_arc1_event3b_full_beat_01"
            sidecar = {
                "schema_version": 3,
                "active_context": {"arc_number": 1, "event_id": "3b", "phase": "full"},
                "arcs": {
                    "arc_1": {
                        "segments": {
                            "event_3b_full": {
                                "beats": [{"beat_id": beat_id, "speaker": "Oliver", "dialogue_text": "Hi"}],
                            },
                        },
                    },
                },
            }
            (mdir / "beat_generator_sidecar.json").write_text(json.dumps(sidecar), encoding="utf-8")
            jobs = root / "Event_2" / "arlo_o3_jobs"
            jobs.mkdir(parents=True)
            intent_path = jobs / "job1_intent.json"
            intent_path.write_text(
                json.dumps(
                    {
                        "job_id": "job1",
                        "beat_id": beat_id,
                        "runtime_scope": {
                            "scope_type": "milestone",
                            "milestone_id": "milestone_blank_x",
                            "milestone_dir": str(mdir),
                            "library_event_dir": str(lib),
                            "skeleton_ref": {
                                "arc_number": 1,
                                "event_id": "3b",
                                "phase": "full",
                                "library_event_id": "Event_1",
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            os.environ["MN_PROD_ROOT"] = str(root)
            os.environ["MN_O3_INTENT_PATH"] = str(intent_path)
            for key in ("MN_MILESTONE_DIR", "MN_BG_LIBRARY_EVENT_DIR", "MN_MILESTONE_SKELETON_REF"):
                os.environ.pop(key, None)
            try:
                beat, seg_key, _, event_dir = load_o3_beat_context(beat_id)
            finally:
                for key in ("MN_PROD_ROOT", "MN_O3_INTENT_PATH", "MN_MILESTONE_DIR", "MN_BG_LIBRARY_EVENT_DIR", "MN_MILESTONE_SKELETON_REF"):
                    os.environ.pop(key, None)
            self.assertEqual(beat["beat_id"], beat_id)
            self.assertEqual(seg_key, "event_3b_full")
            self.assertEqual(event_dir.resolve(), lib.resolve())

    def test_element_intent_pipeline_uses_scoped_bootstrap(self):
        block = (TOOLS / "kling_o3_element_beat_pipeline.py").read_text(encoding="utf-8")
        block = block.split("def run_pipeline_from_intent", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("init_bg_paths_for_o3_subprocess", block)
        self.assertNotIn("bg_sidecar.init_bg_paths(event_dir)", block)


if __name__ == "__main__":
    unittest.main()
