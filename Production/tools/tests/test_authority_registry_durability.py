"""STORYBOARD_AUTHORITY_REGISTRY_V1 — machine registry + doc parity tests."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

from authority_registry import (
    AUTHORITY_REGISTRY_DOC,
    AUTHORITY_REGISTRY_V1,
    CONCEPTS,
    concept_ids,
    shipped_concepts,
)

TOOLS = Path(__file__).resolve().parent.parent
REPO = TOOLS.parent.parent
DOC = REPO / AUTHORITY_REGISTRY_DOC
VERIFY_SH = REPO / "Production/scripts/verify_authority_registry_durability.sh"
SESSION_SH = REPO / "Production/scripts/verify_storyboard_session_durability.sh"


class AuthorityRegistryDurabilityTests(unittest.TestCase):
    def test_registry_marker(self):
        self.assertEqual(AUTHORITY_REGISTRY_V1, "STORYBOARD_AUTHORITY_REGISTRY_V1")

    def test_doc_exists_and_lists_concepts(self):
        self.assertTrue(DOC.is_file(), DOC)
        text = DOC.read_text(encoding="utf-8")
        self.assertIn("STORYBOARD_AUTHORITY_REGISTRY_V1", text)
        for cid in concept_ids():
            self.assertIn(cid, text, f"doc missing concept id {cid}")

    def test_shipped_concepts_have_modules_and_read_gates(self):
        for concept in shipped_concepts():
            if concept.server_module:
                path = TOOLS / concept.server_module
                self.assertTrue(path.is_file(), concept.server_module)
                if concept.server_read:
                    self.assertIn(
                        concept.server_read,
                        path.read_text(encoding="utf-8"),
                        f"{concept.id} server_read missing in {concept.server_module}",
                    )
            if concept.client_module and concept.client_read:
                path = TOOLS / concept.client_module
                self.assertTrue(path.is_file(), concept.client_module)
                self.assertIn(
                    concept.client_read,
                    path.read_text(encoding="utf-8"),
                    f"{concept.id} client_read missing in {concept.client_module}",
                )

    def test_kling_stitch_forbidden_client_patterns(self):
        from authority_registry import CONCEPTS as all_concepts

        concept = next(c for c in all_concepts if c.id == "kling_stitch_export_ready")
        for gate in concept.forbidden_client_gates:
            path = TOOLS / gate.rel_path
            text = path.read_text(encoding="utf-8")
            self.assertIsNone(
                re.search(gate.pattern, text),
                f"{gate.rel_path}: {gate.reason}",
            )

    def test_kling_stitch_server_delegation(self):
        from authority_registry import CONCEPTS as all_concepts

        concept = next(c for c in all_concepts if c.id == "kling_stitch_export_ready")
        for rel, needle in concept.server_delegation:
            path = TOOLS / rel
            self.assertIn(needle, path.read_text(encoding="utf-8"), rel)

    def test_verify_script_wired(self):
        self.assertTrue(VERIFY_SH.is_file())
        session = SESSION_SH.read_text(encoding="utf-8")
        self.assertIn("verify_authority_registry_durability.sh", session)
        self.assertIn("verify_kling_stitch_readiness_durability.sh", session)


    def test_audit_script_wired(self):
        audit = REPO / "Production/scripts/audit_authority_duplicates.sh"
        self.assertTrue(audit.is_file())
        verify = VERIFY_SH.read_text(encoding="utf-8")
        self.assertIn("audit_authority_duplicates.sh", verify)


if __name__ == "__main__":
    unittest.main()
