#!/usr/bin/env python3
"""Phase A Suggest Script — authoring doc loader contract tests."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

import beat_generator as bg  # noqa: E402


class TestPhaseASuggestScriptDocs(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        root = Path(self._tmpdir.name)
        prod = root / "Production"
        prod.mkdir(parents=True)
        (prod / "PHASE_A_SUGGEST_SKELETON_v1_0.md").write_text(
            "CURRENT SKELETON v1_0", encoding="utf-8"
        )
        (prod / "PHASE_A_SUGGEST_SKELETON_v1_1.md").write_text(
            "CURRENT SKELETON v1_1", encoding="utf-8"
        )
        event_dir = prod / "Event_test"
        event_dir.mkdir()
        bg.init_bg_paths(event_dir)

    def test_load_phase_a_suggest_script_docs_picks_highest_version(self):
        docs = bg.load_phase_a_suggest_script_docs()
        self.assertEqual(len(docs), 1)
        doc = docs[0]
        self.assertEqual(doc["key"], "suggest_skeleton")
        self.assertEqual(doc["filename"], "PHASE_A_SUGGEST_SKELETON_v1_1.md")
        self.assertEqual(doc["version"], 1)
        self.assertIn("CURRENT SKELETON v1_1", doc["text"])

    def test_missing_doc_returns_empty_text(self):
        root = Path(self._tmpdir.name)
        for name in (
            "PHASE_A_SUGGEST_SKELETON_v1_0.md",
            "PHASE_A_SUGGEST_SKELETON_v1_1.md",
        ):
            (root / "Production" / name).unlink()
        event_dir = root / "Production" / "Event_test"
        bg.init_bg_paths(event_dir)
        docs = bg.load_phase_a_suggest_script_docs()
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0]["chars"], 0)
        self.assertEqual(docs[0]["text"], "")


if __name__ == "__main__":
    unittest.main()
