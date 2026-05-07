"""Tests for Phase F mechanical gate in Production/lib/directus.py.

LD BROWSER_SMOKE_MECHANICAL_GATE_V1 / DS-21 — try_post_or_queue MUST reject
``prod_activity_log`` writes whose ``action`` ends in ``_COMPLETE`` unless
a matching ``KIM_BROWSER_SMOKE_PASSED`` row exists. Override path requires
both ``MN_SKIP_BROWSER_SMOKE_GATE=1`` AND a ``BROWSER_SMOKE_DEFERRED`` row.

Run:
    python3 -m unittest Production.lib.tests.test_browser_smoke_gate -v
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_LIB_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_LIB_DIR.parent))

from lib.directus import (  # noqa: E402
    _extract_phase_key,
    _is_phase_complete_action,
    try_post_or_queue,
)


class TestPhaseCompleteHelpers(unittest.TestCase):
    def test_recognizes_phase_complete(self):
        self.assertTrue(_is_phase_complete_action("PHASE_A_COMPLETE"))
        self.assertTrue(_is_phase_complete_action("S5_5C_PASS2_COMPLETE"))
        self.assertTrue(_is_phase_complete_action("PHASE_F_COMPLETE"))

    def test_recursion_safe_actions(self):
        # KIM_BROWSER_SMOKE_PASSED + BROWSER_SMOKE_DEFERRED MUST bypass the
        # gate; otherwise the gate would block the smoke row that's required
        # to satisfy the gate (deadlock).
        self.assertFalse(_is_phase_complete_action("KIM_BROWSER_SMOKE_PASSED"))
        self.assertFalse(_is_phase_complete_action("BROWSER_SMOKE_DEFERRED"))

    def test_handles_garbage_inputs(self):
        self.assertFalse(_is_phase_complete_action(""))
        self.assertFalse(_is_phase_complete_action(None))  # type: ignore[arg-type]
        self.assertFalse(_is_phase_complete_action("_COMPLETE"))  # bare suffix
        self.assertFalse(_is_phase_complete_action("not a complete action"))

    def test_extracts_phase_key(self):
        self.assertEqual(_extract_phase_key("PHASE_A_COMPLETE"), "PHASE_A")
        self.assertEqual(
            _extract_phase_key("S5_5C_PASS2_COMPLETE"), "S5_5C_PASS2"
        )
        # Non-COMPLETE actions return unchanged
        self.assertEqual(
            _extract_phase_key("KIM_BROWSER_SMOKE_PASSED"),
            "KIM_BROWSER_SMOKE_PASSED",
        )


class TestPhaseFGate(unittest.TestCase):
    """F6–F9 gate behavior tests using a mocked Directus client."""

    def setUp(self):
        # Reset override env between tests
        os.environ.pop("MN_SKIP_BROWSER_SMOKE_GATE", None)

    def tearDown(self):
        os.environ.pop("MN_SKIP_BROWSER_SMOKE_GATE", None)

    def _build_client_returning(self, *, smoke_rows=None, deferred_rows=None):
        """Build a mock client whose get_items returns smoke or deferred rows."""
        smoke_rows = smoke_rows or []
        deferred_rows = deferred_rows or []

        def get_items(collection, **kwargs):
            assert collection == "prod_activity_log"
            f = (kwargs.get("filter") or {}).get("action") or {}
            action = f.get("_eq")
            if action == "KIM_BROWSER_SMOKE_PASSED":
                return smoke_rows
            if action == "BROWSER_SMOKE_DEFERRED":
                return deferred_rows
            return []

        client = MagicMock()
        client.get_items.side_effect = get_items
        return client

    # --- F6 -----------------------------------------------------------------
    def test_F6_missing_smoke_rejects_phase_complete(self):
        client = self._build_client_returning(smoke_rows=[])
        result = try_post_or_queue(
            "prod_activity_log",
            {"action": "TEST_FOO_COMPLETE", "details": {"phase": "TEST_FOO"}},
            client=client,
        )
        self.assertTrue(result.get("browser_smoke_missing"))
        self.assertEqual(result.get("phase_key"), "TEST_FOO")
        client.get_items.assert_called()

    # --- F7 -----------------------------------------------------------------
    def test_F7_smoke_present_allows_phase_complete(self):
        client = self._build_client_returning(
            smoke_rows=[{"id": 99, "details": {"phase": "TEST_FOO"}}]
        )
        # Make post_item_verified succeed by patching it (we are not testing
        # the underlying write, just that the gate lets the call through).
        with patch("lib.directus.post_item_verified") as mock_post:
            mock_post.return_value = {
                "id": 100,
                "action": "TEST_FOO_COMPLETE",
                "details": {"phase": "TEST_FOO"},
            }
            result = try_post_or_queue(
                "prod_activity_log",
                {"action": "TEST_FOO_COMPLETE", "details": {"phase": "TEST_FOO"}},
                client=client,
            )
        self.assertEqual(result.get("id"), 100)
        self.assertNotIn("browser_smoke_missing", result)

    # --- F8 -----------------------------------------------------------------
    def test_F8_smoke_passed_action_bypasses_gate(self):
        # Writing the SMOKE row itself MUST not be blocked by the gate
        # (otherwise nothing could ever satisfy the gate).
        client = self._build_client_returning(smoke_rows=[])  # no smoke yet
        with patch("lib.directus.post_item_verified") as mock_post:
            mock_post.return_value = {
                "id": 200,
                "action": "KIM_BROWSER_SMOKE_PASSED",
            }
            result = try_post_or_queue(
                "prod_activity_log",
                {
                    "action": "KIM_BROWSER_SMOKE_PASSED",
                    "details": {"phase": "TEST_FOO"},
                },
                client=client,
            )
        self.assertEqual(result.get("id"), 200)
        # Gate should NOT have queried for smoke rows when writing the smoke row
        client.get_items.assert_not_called()

    def test_F8b_deferred_action_bypasses_gate(self):
        client = self._build_client_returning(smoke_rows=[])
        with patch("lib.directus.post_item_verified") as mock_post:
            mock_post.return_value = {
                "id": 201,
                "action": "BROWSER_SMOKE_DEFERRED",
            }
            result = try_post_or_queue(
                "prod_activity_log",
                {
                    "action": "BROWSER_SMOKE_DEFERRED",
                    "details": {"phase": "TEST_FOO"},
                },
                client=client,
            )
        self.assertEqual(result.get("id"), 201)
        client.get_items.assert_not_called()

    # --- F9 -----------------------------------------------------------------
    def test_F9_override_without_deferred_audit_rejected(self):
        os.environ["MN_SKIP_BROWSER_SMOKE_GATE"] = "1"
        client = self._build_client_returning(smoke_rows=[], deferred_rows=[])
        result = try_post_or_queue(
            "prod_activity_log",
            {"action": "TEST_FOO_COMPLETE", "details": {"phase": "TEST_FOO"}},
            client=client,
        )
        self.assertTrue(result.get("override_without_audit"))
        self.assertEqual(result.get("phase_key"), "TEST_FOO")

    def test_F9b_override_plus_deferred_audit_allows(self):
        os.environ["MN_SKIP_BROWSER_SMOKE_GATE"] = "1"
        client = self._build_client_returning(
            smoke_rows=[],
            deferred_rows=[{"id": 50, "details": {"phase": "TEST_FOO"}}],
        )
        with patch("lib.directus.post_item_verified") as mock_post:
            mock_post.return_value = {
                "id": 300,
                "action": "TEST_FOO_COMPLETE",
                "details": {"phase": "TEST_FOO"},
            }
            result = try_post_or_queue(
                "prod_activity_log",
                {"action": "TEST_FOO_COMPLETE", "details": {"phase": "TEST_FOO"}},
                client=client,
            )
        self.assertEqual(result.get("id"), 300)

    # --- fail-CLOSED on Directus error --------------------------------------
    def test_fail_closed_when_smoke_query_raises(self):
        client = MagicMock()
        client.get_items.side_effect = RuntimeError("network down")
        result = try_post_or_queue(
            "prod_activity_log",
            {"action": "TEST_FOO_COMPLETE", "details": {"phase": "TEST_FOO"}},
            client=client,
        )
        self.assertTrue(result.get("browser_smoke_gate_unverifiable"))
        self.assertEqual(result.get("phase_key"), "TEST_FOO")

    # --- non-activity_log writes are NOT gated ------------------------------
    def test_non_activity_log_collection_not_gated(self):
        client = MagicMock()
        with patch("lib.directus.post_item_verified") as mock_post:
            mock_post.return_value = {
                "id": 400,
                "decision_key": "TEST_LD_V1",
            }
            result = try_post_or_queue(
                "prod_locked_decisions",
                {"decision_key": "TEST_LD_V1"},
                client=client,
            )
        self.assertEqual(result.get("id"), 400)
        client.get_items.assert_not_called()


if __name__ == "__main__":
    unittest.main()
