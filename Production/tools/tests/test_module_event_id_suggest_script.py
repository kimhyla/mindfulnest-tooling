#!/usr/bin/env python3
"""Arc Skeleton play-order → m_number resolution for Suggest Script."""
from __future__ import annotations

import json
import os
import sys
import tempfile
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
import production_server as PS  # noqa: E402


class TestSkeletonPlayOrderMapping(unittest.TestCase):
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
        event_dir = dropbox_root / "Production/Event_3"
        bg.init_bg_paths(event_dir)

    def test_arc1_play_order_3_is_m4_ember(self):
        self.assertEqual(bg.find_m_number_for_play_order_event(1, 3), 4)

    def test_arc1_play_order_5_is_m3_benson(self):
        self.assertEqual(bg.find_m_number_for_play_order_event(1, 5), 3)

    def test_event_3_folder_resolves_m4(self):
        resolved = mei.resolve_m_number_from_production_folder("Event_3", bg_module=bg)
        self.assertIsNotNone(resolved)
        arc, play, m_num = resolved
        self.assertEqual((arc, play, m_num), (1, 3, 4))

    def test_canonical_event_3_is_m4e1(self):
        self.assertEqual(
            mei.canonical_module_event_id("Event_3", bg_module=bg),
            "M4E1",
        )


class TestResolveModuleForEventPlayOrder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        dropbox_root = (
            Path.home()
            / "Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files"
        )
        if not (dropbox_root / "Arc Skeletons/ARC_01_SKELETON_FINAL.md").is_file():
            raise unittest.SkipTest("Arc 1 skeleton not on disk")
        bg.init_bg_paths(dropbox_root / "Production/Event_3")

    def test_event_3_folder_yields_ember_m4(self):
        meta = PS._resolve_module_for_event(
            "M3E1",
            production_folder_id="Event_3",
        )
        self.assertIsNotNone(meta)
        self.assertEqual(meta["m_number"], 4)
        self.assertEqual(meta["play_order"], 3)

    def test_m2e1_on_event_2_unchanged(self):
        meta = PS._resolve_module_for_event(
            "M2E1",
            production_folder_id="Event_2",
        )
        self.assertIsNotNone(meta)
        self.assertEqual(meta["m_number"], 2)


class TestHealProductionStateEventId(unittest.TestCase):
    def test_heals_event_3_to_m4e1(self):
        from production_server import StateManager

        dropbox_root = (
            Path.home()
            / "Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files"
        )
        arc1 = dropbox_root / "Arc Skeletons/ARC_01_SKELETON_FINAL.md"
        if not arc1.is_file():
            self.skipTest("Arc 1 skeleton not on disk")

        with tempfile.TemporaryDirectory() as tmp:
            event_dir = Path(tmp) / "Event_3"
            event_dir.mkdir()
            state_path = event_dir / "production_state.json"
            state_path.write_text(
                json.dumps({"event_id": "M3E1", "version": "v3"}),
                encoding="utf-8",
            )
            bg.init_bg_paths(dropbox_root / "Production/Event_3")
            sm = StateManager(event_dir, "M3E1")
            self.assertTrue(mei.heal_production_state_event_id(sm, bg_module=bg))
            healed = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(healed["event_id"], "M4E1")


if __name__ == "__main__":
    unittest.main()
