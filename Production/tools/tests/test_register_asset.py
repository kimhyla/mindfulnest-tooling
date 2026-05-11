"""
Tests for Production/tools/registered_write.py — register_asset() signature
extension for Phase B R2 fields.

Per V59_PRODUCTION_PIPELINE_STREAM_BF_SPEC_v1.md §4.2 Step 5 (DS-2 strict TDD).

Run with:
    python3 -m unittest Production.tools.tests.test_register_asset -v

Mock-based tests run offline (no Directus). They patch the Directus client at
the registered_write module boundary, so they verify what register_asset SENDS
to the POST endpoint — the read-back leg is exercised by the live integration
test in Phase B Step 8 smoke.

Coverage:
  - cdn_url kwarg accepted + persisted in POSTed payload
  - manifest_published_at kwarg accepted + persisted
  - codec_recipe_hash kwarg accepted + persisted
  - all three together in one call
  - default-None when omitted (backwards compat — existing callers must still work)
  - kwargs are keyword-only (cannot be passed positionally — protects signature evolution)
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Make Production.* importable when run directly or via -m unittest from repo root.
_TOOLING_REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_TOOLING_REPO))

# Idempotent shared fixture root (see test_fixture_root_isolation.py for context):
# whichever test module imports first creates the tempdir and sets MN_DROPBOX_ROOT;
# subsequent test modules bind their _FIXTURE_ROOT to the SAME path. This keeps
# every test in the suite agreeing with registered_write._PROJECT_ROOT (which
# captures MN_DROPBOX_ROOT at import time and cannot be reset thereafter). The
# env var MUST be set before importing registered_write so its path-validation
# guard captures the test fixture path.
if "MN_DROPBOX_ROOT" in os.environ:
    _FIXTURE_ROOT = os.environ["MN_DROPBOX_ROOT"]
else:
    _FIXTURE_ROOT = tempfile.mkdtemp(prefix="phase_b_test_root_")
    os.environ["MN_DROPBOX_ROOT"] = _FIXTURE_ROOT

from Production.tools import registered_write  # noqa: E402


def _make_test_file(suffix: str = ".mp4") -> str:
    """Create a tiny temp file inside the fixture root and return abspath."""
    fd, path = tempfile.mkstemp(suffix=suffix, dir=_FIXTURE_ROOT, prefix="r2_test_")
    with os.fdopen(fd, "wb") as fh:
        fh.write(b"phase-b-test-content-" + os.urandom(16))
    return path


def _capture_post_payload(mock_request):
    """Find the POST /items/prod_assets call and return its data payload."""
    for call_args in mock_request.call_args_list:
        args, kwargs = call_args
        method = args[0] if args else kwargs.get("method")
        path = args[1] if len(args) > 1 else kwargs.get("path", "")
        if method == "POST" and "/items/prod_assets" in path:
            return args[2] if len(args) > 2 else kwargs.get("data")
    return None


class TestRegisterAssetR2FieldsKwargs(unittest.TestCase):
    """register_asset() must accept the 3 new R2-field kwargs as keyword-only."""

    def setUp(self):
        # Reset cached singleton so each test gets a fresh mock.
        registered_write._cached_client = None

    def _patched_client(self):
        """Build a MagicMock that mimics DirectusClient for the registration path."""
        client = MagicMock()

        # _request side_effect returns the right shape per (method, path).
        def request_side_effect(method, path, data=None, **kwargs):
            if method == "GET" and "filter[sha256]" in path:
                return {"data": []}  # No dedup match; force fresh registration.
            if method == "POST" and "/items/prod_assets" in path:
                return {"data": {"id": 99999}}
            if method == "POST" and "/items/prod_activity_log" in path:
                return {"data": {"id": 88888}}
            return {"data": {}}

        client._request = MagicMock(side_effect=request_side_effect)
        return client

    def test_cdn_url_kwarg_accepted_and_persisted(self):
        """register_asset(cdn_url=...) must accept the kwarg + include it in POST payload."""
        client = self._patched_client()
        with patch.object(registered_write, "_client", return_value=client):
            test_file = _make_test_file()
            asset_id, _ = registered_write.register_asset(
                file_path=test_file,
                asset_type="unknown",
                module_id=1,
                produced_by_skill="test_register_asset",
                cdn_url="https://cdn.mindfulnest.app/modules/M1.abc123def456.mp4",
            )

        self.assertEqual(asset_id, 99999)
        payload = _capture_post_payload(client._request)
        self.assertIsNotNone(payload, "no POST /items/prod_assets call captured")
        self.assertIn("cdn_url", payload, "cdn_url missing from POSTed payload")
        self.assertEqual(
            payload["cdn_url"],
            "https://cdn.mindfulnest.app/modules/M1.abc123def456.mp4",
        )

    def test_manifest_published_at_kwarg_accepted_and_persisted(self):
        """register_asset(manifest_published_at=...) must accept + persist."""
        client = self._patched_client()
        with patch.object(registered_write, "_client", return_value=client):
            test_file = _make_test_file()
            asset_id, _ = registered_write.register_asset(
                file_path=test_file,
                asset_type="unknown",
                module_id=1,
                produced_by_skill="test_register_asset",
                manifest_published_at="2026-05-10T21:00:00Z",
            )

        self.assertEqual(asset_id, 99999)
        payload = _capture_post_payload(client._request)
        self.assertIsNotNone(payload)
        self.assertIn("manifest_published_at", payload)
        self.assertEqual(payload["manifest_published_at"], "2026-05-10T21:00:00Z")

    def test_codec_recipe_hash_kwarg_accepted_and_persisted(self):
        """register_asset(codec_recipe_hash=...) must accept + persist."""
        client = self._patched_client()
        with patch.object(registered_write, "_client", return_value=client):
            test_file = _make_test_file()
            asset_id, _ = registered_write.register_asset(
                file_path=test_file,
                asset_type="unknown",
                module_id=1,
                produced_by_skill="test_register_asset",
                codec_recipe_hash="abc123" * 10 + "aaaa",  # 64 chars
            )

        self.assertEqual(asset_id, 99999)
        payload = _capture_post_payload(client._request)
        self.assertIsNotNone(payload)
        self.assertIn("codec_recipe_hash", payload)
        self.assertEqual(payload["codec_recipe_hash"], "abc123" * 10 + "aaaa")

    def test_all_three_r2_fields_together(self):
        """All three R2 kwargs accepted in a single call + all 3 persisted."""
        client = self._patched_client()
        with patch.object(registered_write, "_client", return_value=client):
            test_file = _make_test_file()
            asset_id, _ = registered_write.register_asset(
                file_path=test_file,
                asset_type="unknown",
                module_id=1,
                produced_by_skill="test_register_asset",
                cdn_url="https://cdn.example/x.mp4",
                manifest_published_at="2026-05-10T21:00:00Z",
                codec_recipe_hash="deadbeef" * 8,
            )

        self.assertEqual(asset_id, 99999)
        payload = _capture_post_payload(client._request)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["cdn_url"], "https://cdn.example/x.mp4")
        self.assertEqual(payload["manifest_published_at"], "2026-05-10T21:00:00Z")
        self.assertEqual(payload["codec_recipe_hash"], "deadbeef" * 8)

    def test_r2_fields_default_to_none_when_omitted(self):
        """Existing callers (no R2 kwargs) must still work; new fields default to None."""
        client = self._patched_client()
        with patch.object(registered_write, "_client", return_value=client):
            test_file = _make_test_file()
            asset_id, _ = registered_write.register_asset(
                file_path=test_file,
                asset_type="unknown",
                module_id=1,
                produced_by_skill="test_register_asset",
            )

        self.assertEqual(asset_id, 99999)
        payload = _capture_post_payload(client._request)
        self.assertIsNotNone(payload)
        # The 3 R2 fields must appear in the payload with None (so Directus stores NULL).
        self.assertIn("cdn_url", payload)
        self.assertIsNone(payload["cdn_url"])
        self.assertIn("manifest_published_at", payload)
        self.assertIsNone(payload["manifest_published_at"])
        self.assertIn("codec_recipe_hash", payload)
        self.assertIsNone(payload["codec_recipe_hash"])

    def test_r2_kwargs_are_keyword_only(self):
        """The new R2 kwargs MUST be keyword-only — passing positionally must raise."""
        client = self._patched_client()
        with patch.object(registered_write, "_client", return_value=client):
            test_file = _make_test_file()
            with self.assertRaises(TypeError):
                # 4th positional arg would be the next non-keyword param after
                # (file_path, asset_type, module_id). The * in the signature
                # should reject any extra positionals.
                registered_write.register_asset(
                    test_file,
                    "unknown",
                    1,
                    "https://cdn.bad/positional.mp4",  # should raise
                )


if __name__ == "__main__":
    unittest.main()
