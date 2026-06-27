#!/usr/bin/env python3
"""Phase B Suggest Script — dossier, skeleton metadata, brief extraction."""
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
import phase_b_suggest_sources as pbs  # noqa: E402
import production_server as PS  # noqa: E402


class TestArcSkeletonMultiFormat(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        dropbox_root = (
            Path.home()
            / "Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files"
        )
        arc1 = dropbox_root / "Arc Skeletons/ARC_01_SKELETON_FINAL.md"
        arc2 = dropbox_root / "Arc Skeletons/ARC_02_SKELETON_FINAL.md"
        if not arc1.is_file() or not arc2.is_file():
            raise unittest.SkipTest("Arc skeletons not on disk")
        cls.dropbox_root = dropbox_root
        bg.init_bg_paths(dropbox_root / "Production/Event_3")

    def test_arc1_event3_m4_therapeutic_note(self):
        note = bg.extract_therapeutic_note(1, 4)
        self.assertGreater(len(note), 1000)
        self.assertIn("Heart-Sending", note)

    def test_arc1_m4_skeleton_metadata(self):
        meta = bg.extract_skeleton_module_metadata(1, 4)
        self.assertEqual(meta.get("spell_name"), "Heart-Sending Spell")
        self.assertIn("Ember", meta.get("creature", ""))

    def test_arc2_play_order_1_is_m7(self):
        self.assertEqual(bg.find_m_number_for_play_order_event(2, 1), 7)

    def test_arc2_m7_therapeutic_note(self):
        note = bg.extract_therapeutic_note(2, 7)
        self.assertGreater(len(note), 500)
        self.assertIn("Big-Little", note)

    def test_event_7_folder_resolves_m7(self):
        bg.init_bg_paths(self.dropbox_root / "Production/Event_7")
        meta = PS._resolve_module_for_event(
            "Event_7",
            production_folder_id="Event_7",
        )
        self.assertIsNotNone(meta)
        self.assertEqual(meta["m_number"], 7)
        self.assertEqual(meta["play_order"], 1)


class TestDossierBriefExtraction(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        dropbox_root = (
            Path.home()
            / "Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files"
        )
        prod = dropbox_root / "Production"
        if not prod.is_dir():
            raise unittest.SkipTest("Production folder not on disk")
        cls.prod_dir = str(prod)
        bg.init_bg_paths(prod / "Event_3")

    def test_m4_dossier_loads(self):
        doc = pbs.load_phase_b_research_dossier(self.prod_dir, 4)
        self.assertTrue(doc.get("filename"))
        self.assertGreater(doc.get("chars", 0), 5000)

    def test_m4_brief_from_dossier(self):
        doc = pbs.load_phase_b_research_dossier(self.prod_dir, 4)
        meta = bg.extract_skeleton_module_metadata(1, 4)
        note = bg.extract_therapeutic_note(1, 4)
        brief = pbs.build_therapeutic_brief_from_sources(meta, note, doc["text"])
        self.assertIsNotNone(brief)
        self.assertEqual(brief.get("source"), "dossier_extraction")
        self.assertEqual(brief.get("spell_name"), "Heart-Sending Spell")
        self.assertGreaterEqual(len(brief.get("must_hits") or []), 5)
        joined = " ".join(brief.get("must_hits") or [])
        self.assertIn("warmth", joined.lower())

    def test_m4_brief_formats_for_script_prompt(self):
        doc = pbs.load_phase_b_research_dossier(self.prod_dir, 4)
        meta = bg.extract_skeleton_module_metadata(1, 4)
        note = bg.extract_therapeutic_note(1, 4)
        brief = pbs.build_therapeutic_brief_from_sources(meta, note, doc["text"])
        section = pbs.format_therapeutic_brief_for_script_prompt(brief)
        self.assertIn("MANDATORY SCRIPT BLUEPRINT", section)
        self.assertIn("Open with a brief grounding", section)
        self.assertNotIn("**Open", section)

    def test_phase_b_prompt_includes_brief_section(self):
        from server_handlers.phases import _build_phase_b_suggest_user_prompt

        doc = pbs.load_phase_b_research_dossier(self.prod_dir, 4)
        meta = bg.extract_skeleton_module_metadata(1, 4)
        note = bg.extract_therapeutic_note(1, 4)
        brief = pbs.build_therapeutic_brief_from_sources(meta, note, doc["text"])
        brief_sec = pbs.format_therapeutic_brief_for_script_prompt(brief)
        prompt = _build_phase_b_suggest_user_prompt(
            module_identity="test",
            skeleton_metadata_section="",
            therapeutic_brief_section=brief_sec,
            therapeutic_section="",
            dossier_section="",
            technique_section="",
            phase_a_script="test",
            authoring_docs_section="",
        )
        self.assertIn("MANDATORY SCRIPT BLUEPRINT", prompt)
        self.assertIn("must_hits", prompt)
        self.assertIn("every must_hit", prompt.lower())

    def test_m4_approved_script_loads(self):
        doc = pbs.load_phase_b_approved_script(self.prod_dir, 4)
        self.assertIn("HEART_SENDING", doc.get("filename", "").upper())
        self.assertGreater(doc.get("chars", 0), 200)


class TestTechniqueInventorySlice(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        dropbox_root = (
            Path.home()
            / "Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files"
        )
        bg.init_bg_paths(dropbox_root / "Production/Event_3")

    def test_m4_slice_smaller_than_full(self):
        full = bg.load_technique_inventory()
        sl = bg.slice_technique_inventory_for_module(4, full)
        self.assertLess(len(sl), len(full))
        self.assertIn("M4", sl)


if __name__ == "__main__":
    unittest.main()
