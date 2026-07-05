#!/usr/bin/env python3
"""Regression tests for production_folder_to_arc_play_order (Phase 0c)."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

LIB = Path(__file__).resolve().parent.parent.parent / "lib"
TOOLS = Path(__file__).resolve().parent.parent
PROD = LIB.parent
sys.path.insert(0, str(PROD))
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(LIB))

os.environ.setdefault("PRODUCTION_SERVER_SINGLE_MACHINE", "1")

import beat_generator as bg  # noqa: E402
import module_event_id as mei  # noqa: E402


class TestProductionFolderArcPlayOrder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        dropbox_root = (
            Path.home()
            / "Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files"
        )
        arc1 = dropbox_root / "Arc Skeletons/ARC_01_SKELETON_FINAL.md"
        if not arc1.is_file():
            raise unittest.SkipTest(f"Arc 1 skeleton not on disk: {arc1}")
        cls.dropbox_root = dropbox_root
        bg.init_bg_paths(dropbox_root / "Production/Event_3")

    def test_event_3_unchanged_arc1_play3(self):
        self.assertEqual(mei.production_folder_to_arc_play_order("Event_3"), (1, 3))
        resolved = mei.resolve_m_number_from_production_folder("Event_3", bg_module=bg)
        self.assertEqual(resolved, (1, 3, 4))

    def test_event_7_arc2_module_index_1(self):
        self.assertEqual(mei.production_folder_to_arc_play_order("Event_7"), (2, 1))
        self.assertEqual(bg.find_m_number_for_play_order_event(2, 1), 7)

    def test_event_13_arc2_module_index_7_m13(self):
        self.assertEqual(mei.production_folder_to_arc_play_order("Event_13"), (2, 7))
        # Skeleton may lag map until Dropbox sync; verify when present.
        m_num = bg.find_m_number_for_play_order_event(2, 7)
        if m_num is not None:
            self.assertIn(m_num, (12, 13), "Arc 2 play-order 7 should be M13 (or legacy M12 skeleton)")

    def test_event_32_arc6_module_index_1(self):
        self.assertEqual(mei.production_folder_to_arc_play_order("Event_32"), (6, 1))
        self.assertEqual(bg.find_m_number_for_play_order_event(6, 1), 32)

    def test_five_module_arcs_boundaries(self):
        # Arc 5 ends at Event_31; Arc 6 (5 modules) → Event_32–36
        self.assertEqual(mei.production_folder_to_arc_play_order("Event_32"), (6, 1))
        self.assertEqual(mei.production_folder_to_arc_play_order("Event_36"), (6, 5))
        # Arc 9 (5 modules) starts after 48 global modules → Event_49
        self.assertEqual(mei.production_folder_to_arc_play_order("Event_49"), (9, 1))
        # Arc 10 starts at Event_54
        self.assertEqual(mei.production_folder_to_arc_play_order("Event_54"), (10, 1))


if __name__ == "__main__":
    unittest.main()
