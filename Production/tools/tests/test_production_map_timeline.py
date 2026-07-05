#!/usr/bin/env python3
"""Tests for interleaved production map timeline."""
from __future__ import annotations

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

from server_handlers.production_map import build_production_map_timeline  # noqa: E402


class TestProductionMapTimeline(unittest.TestCase):
    def test_arc1_oliver_meet_between_m4_and_m6(self):
        with tempfile.TemporaryDirectory() as tmp:
            timeline, _ = build_production_map_timeline(Path(tmp), [])
            arc1 = [r for r in timeline if r.get("arc_number") == 1]
            m4_idx = next(
                i for i, r in enumerate(arc1) if r.get("kind") == "module" and r.get("m_number") == 4
            )
            oliver_idx = next(
                i for i, r in enumerate(arc1) if r.get("suggested_milestone_id") == "oliver_meet"
            )
            m6_idx = next(
                i for i, r in enumerate(arc1) if r.get("kind") == "module" and r.get("m_number") == 6
            )
            self.assertLess(m4_idx, oliver_idx)
            self.assertLess(oliver_idx, m6_idx)

    def test_arc2_two_milestones_after_m12(self):
        """After M10/M11/M12 come Investigation + Revelation milestones in a row."""
        with tempfile.TemporaryDirectory() as tmp:
            timeline, _ = build_production_map_timeline(Path(tmp), [])
            arc2 = [r for r in timeline if r.get("arc_number") == 2]
            m12_idx = next(
                i for i, r in enumerate(arc2) if r.get("kind") == "module" and r.get("m_number") == 12
            )
            after = arc2[m12_idx + 1 : m12_idx + 3]
            self.assertEqual(len(after), 2)
            self.assertEqual(after[0].get("suggested_milestone_id"), "willow_investigation")
            self.assertEqual(after[1].get("suggested_milestone_id"), "willow_revelation")

    def test_arc3_underground_journey_between_m17_m18(self):
        with tempfile.TemporaryDirectory() as tmp:
            timeline, _ = build_production_map_timeline(Path(tmp), [])
            arc3 = [r for r in timeline if r.get("arc_number") == 3]
            ids = [
                (r.get("kind"), r.get("m_number") or r.get("suggested_milestone_id"))
                for r in arc3
            ]
            m17 = ids.index(("module", 17))
            underground = ids.index(("milestone", "underground_journey"))
            m18 = ids.index(("module", 18))
            self.assertLess(m17, underground)
            self.assertLess(underground, m18)

    def test_module_event_folder_uses_play_order_not_m_number(self):
        """M13 is global Event_10, not Event_13."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Event_10").mkdir()
            prod = [{"m_number": 13, "creature_name": "Oliver", "video_role": "intro"}]
            timeline, _ = build_production_map_timeline(root, prod)
            m13 = next(r for r in timeline if r.get("m_number") == 13)
            self.assertEqual(m13.get("event_dir"), "Event_10")


if __name__ == "__main__":
    unittest.main()
