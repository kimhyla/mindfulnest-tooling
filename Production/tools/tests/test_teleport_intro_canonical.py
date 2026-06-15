"""Tests for teleport_intro_canonical rotation (no API)."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

import teleport_intro_canonical as tic  # noqa: E402


class TeleportIntroCanonicalTests(unittest.TestCase):
    def test_rotation_event_numbers(self):
        self.assertEqual(tic.intro_tail_variant_index(1), 0)
        self.assertEqual(tic.intro_tail_variant_index(2), 1)
        self.assertEqual(tic.intro_tail_variant_index(3), 2)
        self.assertEqual(tic.intro_tail_variant_index(4), 0)
        self.assertEqual(tic.intro_tail_variant_index(7), 0)

    def test_parse_event_number(self):
        self.assertEqual(tic.parse_event_number("Event_1"), 1)
        self.assertEqual(tic.parse_event_number("Event_12"), 12)
        self.assertEqual(tic.parse_event_number("4"), 4)
        self.assertEqual(tic.parse_event_number("event_3b"), 3)

    def test_arc_local_reset(self):
        """Arc 2 Event 1 uses slot 0 — same as Arc 1 Event 1."""
        self.assertEqual(tic.intro_tail_variant_index(tic.parse_event_number("1")), 0)
        self.assertEqual(tic.intro_tail_variant_index(tic.parse_event_number("4")), 0)
        self.assertEqual(tic.intro_tail_variant_index(tic.parse_event_number("7")), 0)

    def test_resolve_skips_resolution_phase(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reg = {
                "variant_count": 3,
                "variants": [{
                    "slot": 0,
                    "intro_tail_rel": "tail.mp4",
                }],
            }
            (root / "tail.mp4").write_bytes(b"x")
            tic.save_registry(root, reg)
            self.assertIsNone(tic.resolve_canonical_tail_for_event("Event_1", root, phase="post"))
            p = tic.resolve_canonical_tail_for_event("Event_1", root, phase="pre")
            self.assertTrue(p.is_file())

    def test_event2_uses_slot_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reg = {"variant_count": 3, "variants": []}
            for slot in (0, 1, 2):
                rel = f"v{slot}.mp4"
                (root / rel).write_bytes(b"x")
                reg = tic.upsert_variant(
                    reg,
                    slot=slot,
                    speak_source=f"/speak/{slot}.mp4",
                    intro_tail_rel=rel,
                )
            tic.save_registry(root, reg)
            p = tic.resolve_canonical_tail_for_event("Event_2", root, phase="pre")
            self.assertEqual(p.name, "v1.mp4")

    def test_single_canonical_uses_slot_0_for_all_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rel = "Production/templates/chipper_teleport_intro/canonical/variant_0/intro_tail.mp4"
            tail_path = root / rel
            tail_path.parent.mkdir(parents=True, exist_ok=True)
            tail_path.write_bytes(b"x")
            reg = {
                "variant_count": 1,
                "single_canonical": True,
                "variants": [{
                    "slot": 0,
                    "intro_tail_rel": rel,
                    "speak_source": "/speak/g14.mp4",
                }],
            }
            tic.save_registry(root, reg)
            for ev in ("Event_1", "Event_2", "Event_4"):
                p = tic.resolve_canonical_tail_for_event(ev, root, phase="pre")
                self.assertTrue(p.is_file())
                self.assertEqual(p.name, "intro_tail.mp4")


if __name__ == "__main__":
    unittest.main()
