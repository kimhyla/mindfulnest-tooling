#!/usr/bin/env python3
"""Phase B Suggest Script — authoring doc loader contract tests."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

import beat_generator as bg  # noqa: E402


class TestPhaseBSuggestScriptDocs(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        root = Path(self._tmpdir.name)
        prod = root / "Production"
        prod.mkdir(parents=True)
        (prod / "PHASE_B_CLARITY_CHECKLIST_v1.md").write_text(
            "OLD CLARITY v1", encoding="utf-8"
        )
        (prod / "PHASE_B_CLARITY_CHECKLIST_v1_1.md").write_text(
            "CURRENT CLARITY v1_1", encoding="utf-8"
        )
        (prod / "PHASE_B_PRODUCTION_PROCESS_v1_2.md").write_text(
            "CURRENT PROCESS v1_2", encoding="utf-8"
        )
        event_dir = prod / "Event_test"
        event_dir.mkdir()
        bg.init_bg_paths(event_dir)

    def test_load_phase_b_suggest_script_docs_picks_highest_versions(self):
        docs = bg.load_phase_b_suggest_script_docs()
        by_key = {d["key"]: d for d in docs}
        self.assertEqual(
            by_key["clarity_checklist"]["filename"],
            "PHASE_B_CLARITY_CHECKLIST_v1_1.md",
        )
        self.assertEqual(by_key["clarity_checklist"]["version"], 1)
        self.assertIn("CURRENT CLARITY v1_1", by_key["clarity_checklist"]["text"])
        self.assertEqual(
            by_key["production_process"]["filename"],
            "PHASE_B_PRODUCTION_PROCESS_v1_2.md",
        )
        self.assertEqual(by_key["production_process"]["version"], 2)
        self.assertIn("CURRENT PROCESS v1_2", by_key["production_process"]["text"])

    def test_missing_docs_return_empty_text(self):
        root = Path(self._tmpdir.name)
        for name in (
            "PHASE_B_CLARITY_CHECKLIST_v1.md",
            "PHASE_B_CLARITY_CHECKLIST_v1_1.md",
            "PHASE_B_PRODUCTION_PROCESS_v1_2.md",
        ):
            (root / "Production" / name).unlink()
        event_dir = root / "Production" / "Event_test"
        bg.init_bg_paths(event_dir)
        docs = bg.load_phase_b_suggest_script_docs()
        self.assertEqual(len(docs), 2)
        for doc in docs:
            self.assertEqual(doc["chars"], 0)
            self.assertEqual(doc["text"], "")


if __name__ == "__main__":
    unittest.main()
