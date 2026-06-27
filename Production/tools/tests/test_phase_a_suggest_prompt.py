#!/usr/bin/env python3
"""Phase A Suggest Script — prompt builder contract tests."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

from server_handlers.phases import (  # noqa: E402
    _M1_PHASE_A_FEW_SHOT,
    _build_phase_a_suggest_user_prompt,
    _format_phase_a_authoring_docs_section,
)


class TestPhaseASuggestPrompt(unittest.TestCase):
    def _sample_docs(self):
        return [
            {
                "key": "suggest_skeleton",
                "filename": "PHASE_A_SUGGEST_SKELETON_v1_0.md",
                "version": 0,
                "chars": 42,
                "text": "Beat RE_ENTRY purpose: warm return.",
            }
        ]

    def test_format_phase_a_authoring_docs_section_renders_skeleton(self):
        section = _format_phase_a_authoring_docs_section(self._sample_docs())
        self.assertIn("Phase A Suggest Script Beat Skeleton", section)
        self.assertIn("Beat RE_ENTRY purpose", section)

    def test_format_phase_a_authoring_docs_section_missing_doc(self):
        section = _format_phase_a_authoring_docs_section(
            [{"key": "suggest_skeleton", "text": "", "filename": ""}],
        )
        self.assertIn("NOT FOUND", section)

    def test_build_phase_a_prompt_pre_phase_b_sell_framing(self):
        prompt = _build_phase_a_suggest_user_prompt(
            module_identity="Module: M1\n",
            therapeutic_section="Therapeutic Note:\n---\nnote\n---\n",
            technique_section="Inventory:\n---\ninv\n---\n",
            phase_b_script="",
            authoring_docs_section=_format_phase_a_authoring_docs_section(
                self._sample_docs(),
            ),
        )
        self.assertIn("before** Phase B", prompt)
        self.assertIn("SELL the purpose and meaning", prompt)
        self.assertIn("RE_ENTRY", prompt)
        self.assertIn("MEANING_PROMISE", prompt)
        self.assertIn("BENEFIT_SELL", prompt)
        self.assertIn("INTEREST_JOSTLER", prompt)
        self.assertIn("HANDOFF", prompt)
        self.assertIn("1–3 relatable", prompt)
        self.assertNotIn("follows Phase B", prompt)
        self.assertNotIn("just completed Phase B", prompt)
        self.assertNotIn("demonstrate the technique", prompt)

    def test_build_phase_a_prompt_phase_b_alignment_not_recap(self):
        prompt = _build_phase_a_suggest_user_prompt(
            module_identity="Module: M1\n",
            therapeutic_section="Therapeutic Note:\n---\nnote\n---\n",
            technique_section="",
            phase_b_script="Wizard teaches Magic Hands.",
            authoring_docs_section=_format_phase_a_authoring_docs_section(
                self._sample_docs(),
            ),
        )
        self.assertIn("vocabulary alignment only", prompt)
        self.assertIn("child has NOT heard this yet", prompt)
        self.assertIn("Wizard teaches Magic Hands.", prompt)

    def test_m1_few_shot_present_in_prompt(self):
        prompt = _build_phase_a_suggest_user_prompt(
            module_identity="",
            therapeutic_section="",
            technique_section="",
            phase_b_script="",
            authoring_docs_section="",
        )
        self.assertIn(_M1_PHASE_A_FEW_SHOT, prompt)
        self.assertIn("do not copy benefit examples", prompt.lower())


if __name__ == "__main__":
    unittest.main()
