#!/usr/bin/env python3
"""Tests for planned milestone rows on /api/production/map."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
PROD = TOOLS.parent
sys.path.insert(0, str(PROD))
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(PROD / "lib"))

os.environ.setdefault("PRODUCTION_SERVER_SINGLE_MACHINE", "1")

from server_handlers.production_map import build_production_map_milestones  # noqa: E402


def _write_milestone(root: Path, folder: str, *, label: str, arc: int, event_id: str) -> None:
    mdir = root / "Milestones" / folder
    mdir.mkdir(parents=True)
    state = {
        "milestone_label": label,
        "skeleton_ref": {"arc_number": arc, "event_id": event_id, "phase": "full"},
        "videos": {"standalone": {"display_order": [], "beats": {}}},
    }
    (mdir / "state.json").write_text(json.dumps(state), encoding="utf-8")


class TestBuildProductionMapMilestones(unittest.TestCase):
    def test_returns_29_planned_slots(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Milestones").mkdir()
            planned, extras = build_production_map_milestones(root)
            self.assertEqual(len(planned), 30)
            self.assertTrue(all(r.get("planned") is True for r in planned))

    def test_legacy_folder_maps_to_oliver_meet(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_milestone(
                root,
                "milestone1_arc1",
                label="Oliver enters",
                arc=1,
                event_id="3b",
            )
            planned, extras = build_production_map_milestones(root)
            oliver = next(r for r in planned if r.get("suggested_milestone_id") == "oliver_meet")
            self.assertTrue(oliver["created"])
            self.assertEqual(oliver["milestone_id"], "milestone1_arc1")
            self.assertEqual(oliver["label"], "Oliver Meet")

    def test_dev_fixtures_excluded_from_planned(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_milestone(
                root,
                "e10test6df6cd",
                label="E10 test",
                arc=1,
                event_id="e10test6df6cd",
            )
            planned, extras = build_production_map_milestones(root)
            planned_ids = {r.get("milestone_id") for r in planned}
            self.assertNotIn("e10test6df6cd", planned_ids)
            dev_ids = {e.get("milestone_id") for e in extras if e.get("dev_fixture")}
            self.assertIn("e10test6df6cd", dev_ids)

    def test_uncreated_slots_marked_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Milestones").mkdir()
            planned, _extras = build_production_map_milestones(root)
            willows = next(r for r in planned if r.get("suggested_milestone_id") == "willows_entrance")
            self.assertFalse(willows["created"])
            self.assertEqual(willows["videos_by_role"]["standalone"]["state"], "absent")


if __name__ == "__main__":
    unittest.main()
