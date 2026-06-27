#!/usr/bin/env python3
"""Milestone Beat Gen scope router — category contract tests."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS.parent.parent))

from Production.lib.milestone_store import (  # noqa: E402
    ensure_milestone_runtime_fields,
    resolve_milestone_skeleton_ref,
)
from Production.lib.scope_context import (  # noqa: E402
    ScopeContext,
    normalize_milestone_video_role,
)
from Production.tools.server_handlers.milestone_scope import milestone_bg_segment  # noqa: E402
from Production.tools.server_handlers.stitch_editor import (  # noqa: E402
    STITCH_MILESTONE_SLOT_ORDER,
    _valid_stitch_slot,
    stitch_milestone_job_name,
)


class MilestoneVideoRoleTests(unittest.TestCase):
    def test_event_partition_roles_map_to_standalone(self):
        for role in ("intro", "resolution", "phase_a", "phase_b", "", None):
            self.assertEqual(normalize_milestone_video_role(role), "standalone")

    def test_standalone_preserved(self):
        self.assertEqual(normalize_milestone_video_role("standalone"), "standalone")


class MilestoneSkeletonCatalogTests(unittest.TestCase):
    def test_milestone1_arc1_maps_oliver_meet_3b_full(self):
        skel = resolve_milestone_skeleton_ref({}, "milestone1_arc1")
        self.assertEqual(skel["arc_number"], 1)
        self.assertEqual(skel["event_id"], "3b")
        self.assertEqual(skel["phase"], "full")
        self.assertEqual(skel.get("library_event_id"), "Event_1")

    def test_ensure_runtime_fields_hydrates_existing_milestone(self):
        with tempfile.TemporaryDirectory() as tmp:
            mdir = Path(tmp) / "milestone1_arc1"
            mdir.mkdir()
            state_path = mdir / "state.json"
            state_path.write_text(
                json.dumps({
                    "milestone_id": "milestone1_arc1",
                    "milestone_label": "Oliver enters",
                    "active_video": "standalone",
                    "videos": {"standalone": {"beats": {}, "display_order": []}},
                }),
                encoding="utf-8",
            )
            state = ensure_milestone_runtime_fields(mdir)
            self.assertIn("skeleton_ref", state)
            self.assertEqual(state["skeleton_ref"]["event_id"], "3b")
            self.assertEqual(state["library_event_id"], "Event_1")
            reloaded = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(reloaded["skeleton_ref"]["event_id"], "3b")


class MilestoneScopeContextTests(unittest.TestCase):
    def test_stitch_job_name_isolated_per_milestone(self):
        ctx = ScopeContext(
            scope_type="milestone",
            root_dir=Path("/tmp/Milestones/milestone1_arc1"),
            scope_id="milestone1_arc1",
            video_role="standalone",
            generation=1,
            library_event_dir=Path("/tmp/Production/Event_1"),
            prod_root=Path("/tmp/Production"),
            milestone_id="milestone1_arc1",
            skeleton_ref={"arc_number": 1, "event_id": "3b", "phase": "full"},
        )
        self.assertEqual(ctx.stitch_job_name, "milestone_milestone1_arc1_stitch")
        seg = milestone_bg_segment(ctx)
        self.assertEqual(seg["event_id"], "3b")
        self.assertEqual(seg["phase"], "full")
        self.assertEqual(seg["scope_type"], "milestone")


class MilestoneStitchSlotTests(unittest.TestCase):
    def test_standalone_valid_for_milestone_job_only(self):
        job = stitch_milestone_job_name("milestone1_arc1")
        self.assertEqual(job, "milestone_milestone1_arc1_stitch")
        self.assertTrue(_valid_stitch_slot("standalone", job_name=job))
        self.assertFalse(_valid_stitch_slot("intro", job_name=job))
        self.assertEqual(STITCH_MILESTONE_SLOT_ORDER, ["standalone"])


class MilestoneSidecarJsonOnlyTests(unittest.TestCase):
    def test_milestone_init_bg_paths_uses_json_not_sqlite(self):
        import Production.tools.beat_generator as bg  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmp:
            prod = Path(tmp) / "Production"
            ev = prod / "Event_1"
            mdir = prod / "Milestones" / "milestone1_arc1"
            ev.mkdir(parents=True)
            mdir.mkdir(parents=True)
            (ev / "library" / "images").mkdir(parents=True)
            sidecar = {
                "schema_version": 3,
                "arcs": {"arc_1": {"segments": {"event_3b_full": {"beats": [
                    {"beat_id": "bg_arc1_event3b_full_beat_01", "speaker": "Arlo"},
                ]}}}},
            }
            (mdir / "beat_generator_sidecar.json").write_text(
                json.dumps(sidecar), encoding="utf-8",
            )
            corrupt_db = Path(tmp) / "beatgen.db"
            corrupt_db.write_bytes(b"\x00" * 4096)
            os.environ["MN_BEATGEN_DB_PATH"] = str(corrupt_db)
            try:
                bg.init_bg_paths(ev, milestone_dir=mdir, library_event_dir=ev)
                self.assertTrue(bg._MILESTONE_SIDECAR_JSON_ONLY)
                self.assertFalse(bg._sidecar_use_sqlite())
                loaded = bg.read_sidecar()
                beats = loaded["arcs"]["arc_1"]["segments"]["event_3b_full"]["beats"]
                self.assertEqual(len(beats), 1)
            finally:
                os.environ.pop("MN_BEATGEN_DB_PATH", None)
            self.assertEqual(
                Path(bg.BG_SIDECAR_PATH),
                mdir / "beat_generator_sidecar.json",
            )
            bg.init_bg_paths(ev, clear_milestone_scope=True)
            self.assertFalse(bg._MILESTONE_SIDECAR_JSON_ONLY)


if __name__ == "__main__":
    unittest.main()
