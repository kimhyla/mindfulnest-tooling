"""
Tests for Production/lib/directus.py — post_item_verified + helpers.

Run with:
    python3 -m unittest Production.lib.tests.test_directus_verified -v

Or directly:
    DIRECTUS_EMAIL=... DIRECTUS_PASSWORD=... python3 Production/lib/tests/test_directus_verified.py

Mock-based tests (1-6) run offline. Live test (7) is OPT-IN via env var
MN_CONTEXT_LIVE_DIRECTUS_TESTS=1. It writes to prod_activity_log, which is
safe (append-only audit trail, rows tagged with the test id).
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Make Production/lib importable when run directly
_LIB_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_LIB_DIR.parent))  # makes `lib.` importable

from lib.directus import (  # noqa: E402
    DirectusReadError,
    DirectusWriteError,
    SilentWriteFailure,
    _diff_payload_vs_row,
    _values_equal,
    post_item_verified,
    queue_write_offline,
    try_post_or_queue,
)
from lib.directus_admin_client import DirectusAdminError  # noqa: E402


def _fake_client_returning(created: dict, read_back: dict):
    """Return a MagicMock that mimics DirectusAdminClient for post + get."""
    c = MagicMock()
    c.post_item.return_value = created
    c.get_item.return_value = read_back
    return c


class TestValuesEqual(unittest.TestCase):
    def test_none_equality(self):
        self.assertTrue(_values_equal(None, None))
        self.assertFalse(_values_equal(None, ""))
        self.assertFalse(_values_equal(None, 0))

    def test_int_float_cross(self):
        self.assertTrue(_values_equal(42, 42.0))
        self.assertTrue(_values_equal(0, 0.0))

    def test_bool_strict(self):
        # bool is NOT equal to its int equivalent for schema fidelity.
        self.assertFalse(_values_equal(True, 1))
        self.assertFalse(_values_equal(False, 0))
        self.assertTrue(_values_equal(True, True))

    def test_nested_dict(self):
        a = {"x": {"y": [1, {"z": True}]}}
        b = {"x": {"y": [1, {"z": True}]}}
        self.assertTrue(_values_equal(a, b))
        c = {"x": {"y": [1, {"z": False}]}}
        self.assertFalse(_values_equal(a, c))

    def test_list_order_sensitive(self):
        self.assertTrue(_values_equal([1, 2, 3], [1, 2, 3]))
        self.assertFalse(_values_equal([1, 2, 3], [3, 2, 1]))

    def test_iso_datetime_roundtrip(self):
        self.assertTrue(
            _values_equal("2026-04-21T19:30:00Z", "2026-04-21T19:30:00.000+00:00")
        )
        self.assertFalse(
            _values_equal("2026-04-21T19:30:00Z", "2026-04-22T19:30:00Z")
        )

    def test_type_coercion_rejected(self):
        # "42" is NOT 42 — we want to SURFACE this so the caller knows.
        self.assertFalse(_values_equal("42", 42))


class TestHappyPath(unittest.TestCase):
    def test_write_readback_match_returns_row(self):
        payload = {"action": "test", "details": {"k": "v"}}
        read = {"id": 1001, "action": "test", "details": {"k": "v"}}
        c = _fake_client_returning({"id": 1001, **payload}, read)
        row = post_item_verified("prod_activity_log", payload, client=c)
        self.assertEqual(row["id"], 1001)
        c.post_item.assert_called_once()
        c.get_item.assert_called_once_with("prod_activity_log", 1001)


class TestSilentDrop(unittest.TestCase):
    def test_missing_field_surfaces_mismatch(self):
        payload = {"action": "x", "details": {"k": "v"}, "will_be_dropped": "yes"}
        # Directus silently drops the unknown field:
        created = {"id": 5, "action": "x", "details": {"k": "v"}}
        read = {"id": 5, "action": "x", "details": {"k": "v"}}
        c = _fake_client_returning(created, read)
        with self.assertRaises(SilentWriteFailure) as ctx:
            post_item_verified("c", payload, client=c)
        self.assertEqual(len(ctx.exception.mismatches), 1)
        self.assertEqual(ctx.exception.mismatches[0]["field"], "will_be_dropped")


class TestTypeCoercion(unittest.TestCase):
    def test_string_to_int_coercion_surfaces(self):
        payload = {"count": "42"}  # sent as string
        created = {"id": 7, "count": 42}  # Directus stored as int
        read = {"id": 7, "count": 42}
        c = _fake_client_returning(created, read)
        with self.assertRaises(SilentWriteFailure) as ctx:
            post_item_verified("c", payload, client=c)
        fm = ctx.exception.mismatches[0]
        self.assertEqual(fm["field"], "count")
        self.assertEqual(fm["sent"], "42")
        self.assertEqual(fm["got"], 42)


class TestAuthError(unittest.TestCase):
    def test_http_error_on_post_raises_write_error(self):
        c = MagicMock()
        c.post_item.side_effect = DirectusAdminError(
            status=401, body="unauthorized", path="/items/x", method="POST"
        )
        with self.assertRaises(DirectusWriteError) as ctx:
            post_item_verified("x", {"a": 1}, client=c)
        self.assertEqual(ctx.exception.collection, "x")


class TestReadBackFailure(unittest.TestCase):
    def test_404_on_readback_raises_read_error(self):
        c = MagicMock()
        c.post_item.return_value = {"id": 9, "a": 1}
        c.get_item.side_effect = DirectusAdminError(
            status=404, body="not found", path="/items/x/9", method="GET"
        )
        with self.assertRaises(DirectusReadError) as ctx:
            post_item_verified("x", {"a": 1}, client=c)
        self.assertEqual(ctx.exception.item_id, 9)


class TestNestedJson(unittest.TestCase):
    def test_deep_nested_match(self):
        payload = {"details": {"a": {"b": {"c": [1, 2, {"d": "ok"}]}}}}
        created = {"id": 11, **payload}
        read = {"id": 11, **payload}
        c = _fake_client_returning(created, read)
        row = post_item_verified("c", payload, client=c)
        self.assertEqual(row["id"], 11)

    def test_deep_nested_mismatch(self):
        payload = {"details": {"a": {"b": {"c": [1, 2]}}}}
        created = {"id": 12, **payload}
        read = {"id": 12, "details": {"a": {"b": {"c": [1, 2, 3]}}}}
        c = _fake_client_returning(created, read)
        with self.assertRaises(SilentWriteFailure):
            post_item_verified("c", payload, client=c)


class TestIdempotencyNote(unittest.TestCase):
    def test_two_calls_produce_two_rows(self):
        """post_item_verified is NOT dedup-keyed by default.

        Calling twice with the same payload produces two rows (standard POST
        semantics). Callers wanting dedup must provide a unique key in their
        payload and query before posting.
        """
        c = MagicMock()
        c.post_item.side_effect = [{"id": 100, "a": 1}, {"id": 101, "a": 1}]
        c.get_item.side_effect = [{"id": 100, "a": 1}, {"id": 101, "a": 1}]
        row1 = post_item_verified("x", {"a": 1}, client=c)
        row2 = post_item_verified("x", {"a": 1}, client=c)
        self.assertNotEqual(row1["id"], row2["id"])
        self.assertEqual(c.post_item.call_count, 2)


class TestAutoFieldsPresenceOnly(unittest.TestCase):
    def test_auto_fields_presence_verified_not_valued(self):
        """If caller includes an auto-field (e.g. 'id') in payload, only
        presence is verified — not value equality. Directus owns the value."""
        payload = {"id": "will-be-overwritten", "action": "x"}
        created = {"id": 50, "action": "x"}
        read = {"id": 50, "action": "x"}
        c = _fake_client_returning(created, read)
        row = post_item_verified("c", payload, client=c)
        self.assertEqual(row["id"], 50)


class TestDiffHelper(unittest.TestCase):
    def test_empty_diff(self):
        self.assertEqual(_diff_payload_vs_row({"a": 1}, {"id": 1, "a": 1}), [])

    def test_missing_field(self):
        diffs = _diff_payload_vs_row({"a": 1, "b": 2}, {"id": 1, "a": 1})
        self.assertEqual(len(diffs), 1)
        self.assertEqual(diffs[0]["field"], "b")


class TestOfflineQueue(unittest.TestCase):
    def setUp(self):
        self.tmp_queue = Path(__file__).resolve().parent / "_test_queue.json"
        if self.tmp_queue.exists():
            self.tmp_queue.unlink()

    def tearDown(self):
        if self.tmp_queue.exists():
            self.tmp_queue.unlink()

    def test_queue_and_try_post_fallback(self):
        """try_post_or_queue must NEVER raise, even on write failure."""
        c = MagicMock()
        c.post_item.side_effect = DirectusAdminError(
            status=0, body="no network", path="/items/x", method="POST"
        )
        result = try_post_or_queue("prod_activity_log", {"action": "offline_test"}, client=c)
        self.assertTrue(result.get("queued"))
        self.assertIn("path", result)
        # Clean up the queued entry so we don't leave garbage
        qpath = Path(result["path"])
        if qpath.exists():
            data = json.loads(qpath.read_text(encoding="utf-8"))
            # Remove only entries from this test
            data = [e for e in data if e.get("payload", {}).get("action") != "offline_test"]
            qpath.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ----------------------------------------------------------------------------
# Opt-in live integration test (writes a real row). Safe on prod_activity_log.
# ----------------------------------------------------------------------------

_LIVE = os.environ.get("MN_CONTEXT_LIVE_DIRECTUS_TESTS") == "1"


@unittest.skipUnless(_LIVE, "Set MN_CONTEXT_LIVE_DIRECTUS_TESTS=1 to run live tests")
class TestLiveDirectus(unittest.TestCase):
    def test_live_roundtrip_activity_log(self):
        payload = {
            "action": "post_item_verified_integration_test",
            "details": {"test": "test_live_roundtrip_activity_log", "marker": "mn-context-v1"},
            "performed_by": "autonomous_build_tests",
        }
        row = post_item_verified("prod_activity_log", payload)
        self.assertIn("id", row)
        self.assertEqual(row["action"], payload["action"])
        self.assertEqual(row["details"]["marker"], "mn-context-v1")


if __name__ == "__main__":
    unittest.main(verbosity=2)
