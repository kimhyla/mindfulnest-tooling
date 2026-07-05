#!/usr/bin/env python3
"""Tests for /api/production/next-options diff logic."""
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

from server_handlers.production_map import compute_next_options  # noqa: E402
from lib.production_event_map import suggested_event_folder_id  # noqa: E402


class TestComputeNextOptions(unittest.TestCase):
    def test_arc2_first_module_is_event_7(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Event_1").mkdir()
            (root / "Event_2").mkdir()
            (root / "Event_3").mkdir()
            (root / "Event_4").mkdir()
            (root / "Event_5").mkdir()
            (root / "Event_6").mkdir()
            prod_modules = [
                {"m_number": n, "creature_name": "Tessa", "spell_name": "X"}
                for n in range(1, 7)
            ]
            out = compute_next_options(
                production_root=root,
                prod_modules=prod_modules,
                arc_filter=2,
            )
            options = out["options"]
            self.assertTrue(options, "Arc 2 should have pending slots")
            first = options[0]
            self.assertEqual(first["kind"], "module")
            self.assertEqual(first["m_number"], 7)
            self.assertEqual(first["suggested_id"], "Event_7")

    def test_m13_before_m10_in_arc2_options(self):
        """M13 play-order precedes M10 — next-options should surface M13 first among arc2 modules."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for n in range(1, 7):
                (root / f"Event_{n}").mkdir()
            prod_modules = [
                {"m_number": n, "creature_name": "TBD", "spell_name": "TBD"}
                for n in list(range(7, 10)) + [10, 11, 12]
            ]
            out = compute_next_options(
                production_root=root,
                prod_modules=prod_modules,
                arc_filter=2,
            )
            module_opts = [o for o in out["options"] if o["kind"] == "module"]
            m_numbers = [o["m_number"] for o in module_opts]
            self.assertIn(13, m_numbers)
            if 13 in m_numbers and 10 in m_numbers:
                self.assertLess(m_numbers.index(13), m_numbers.index(10))

    def test_suggested_event_folder_arc2_m13_is_event_10(self):
        """M13 is the 4th Arc 2 module → global module 10 → Event_10."""
        self.assertEqual(suggested_event_folder_id(2, 13), "Event_10")


if __name__ == "__main__":
    unittest.main()
