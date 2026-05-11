"""
Tests for Production/scripts/r2_upload.py — Stream F R2 S3-compatible upload helper.

Per V59_PRODUCTION_PIPELINE_STREAM_BF_SPEC_v1.md §4.4 (Phase D) + §13.1 Open Decision 3
(LOCKED Kim 2026-05-08: urllib + AWS Sig V4 hand-rolled; NOT boto3) +
R2_DEPLOYMENT_CONTRACT.md.

DS-2 strict TDD: this file lands RED in a commit BEFORE r2_upload.py exists.
GREEN commit follows with the implementation.

Run with:
    python3 -m unittest Production.scripts.tests.test_r2_upload -v

Mock-based — patches urllib.request.urlopen for HTTP. Tests run offline; no real
R2 / Cloudflare network access required.
"""

from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_TOOLING_REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_TOOLING_REPO))

from Production.scripts import r2_upload  # noqa: E402  RED until GREEN commit


# ----------------------------------------------------------------------------
# Test helpers — synthetic env, synthetic HTTP responses.
# ----------------------------------------------------------------------------

_FAKE_ENV = {
    "R2_ACCESS_KEY_ID": "AKIA_TEST_ID",
    "R2_SECRET_ACCESS_KEY": "test_secret_key_PLACEHOLDER_value_for_tests_only",
    "R2_ACCOUNT_ID": "00000000000000000000000000000000",
    "R2_BUCKET_NAME": "mindfulnest-staging",
}


def _fake_response(*, status: int = 200, headers: dict | None = None, body: bytes = b"") -> MagicMock:
    """Build a MagicMock urllib response object with the given status/headers/body."""
    resp = MagicMock()
    resp.status = status
    resp.getcode.return_value = status
    resp.read.return_value = body
    hdrs = headers or {}
    # urllib responses expose headers via .headers.get(name); also iterable
    resp.headers = hdrs
    resp.getheader = lambda name, default=None: hdrs.get(name, default)
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def _make_temp_file(content: bytes = b"hello mindfulnest") -> Path:
    """Write a temp file with the given content; return Path."""
    fd, name = tempfile.mkstemp(prefix="r2_test_", suffix=".mp4")
    with os.fdopen(fd, "wb") as fh:
        fh.write(content)
    return Path(name)


# ----------------------------------------------------------------------------
# Public API surface tests
# ----------------------------------------------------------------------------

class PublicAPITests(unittest.TestCase):
    """The module exposes the documented public functions + exception types."""

    def test_module_imports_cleanly(self) -> None:
        self.assertTrue(hasattr(r2_upload, "upload"))
        self.assertTrue(hasattr(r2_upload, "head"))
        self.assertTrue(hasattr(r2_upload, "range_get"))

    def test_credentials_missing_exception_exists(self) -> None:
        self.assertTrue(hasattr(r2_upload, "R2CredentialsMissingError"))
        self.assertTrue(issubclass(r2_upload.R2CredentialsMissingError, Exception))

    def test_request_error_exception_exists(self) -> None:
        self.assertTrue(hasattr(r2_upload, "R2RequestError"))
        self.assertTrue(issubclass(r2_upload.R2RequestError, Exception))


# ----------------------------------------------------------------------------
# Credential loading tests
# ----------------------------------------------------------------------------

class CredentialLoadingTests(unittest.TestCase):
    """All 4 env vars are required; absence raises R2CredentialsMissingError."""

    def _env_without(self, key: str) -> dict[str, str]:
        env = dict(_FAKE_ENV)
        env.pop(key)
        return env

    def test_upload_raises_when_access_key_id_missing(self) -> None:
        local = _make_temp_file()
        try:
            with patch.dict(os.environ, self._env_without("R2_ACCESS_KEY_ID"), clear=True):
                with self.assertRaises(r2_upload.R2CredentialsMissingError):
                    r2_upload.upload(local, "modules/M1.test.mp4", "video/mp4", "public, max-age=31536000, immutable")
        finally:
            local.unlink(missing_ok=True)

    def test_upload_raises_when_secret_missing(self) -> None:
        local = _make_temp_file()
        try:
            with patch.dict(os.environ, self._env_without("R2_SECRET_ACCESS_KEY"), clear=True):
                with self.assertRaises(r2_upload.R2CredentialsMissingError):
                    r2_upload.upload(local, "modules/M1.test.mp4", "video/mp4", "public, max-age=31536000, immutable")
        finally:
            local.unlink(missing_ok=True)

    def test_upload_raises_when_account_id_missing(self) -> None:
        local = _make_temp_file()
        try:
            with patch.dict(os.environ, self._env_without("R2_ACCOUNT_ID"), clear=True):
                with self.assertRaises(r2_upload.R2CredentialsMissingError):
                    r2_upload.upload(local, "modules/M1.test.mp4", "video/mp4", "public, max-age=31536000, immutable")
        finally:
            local.unlink(missing_ok=True)

    def test_upload_raises_when_bucket_missing(self) -> None:
        local = _make_temp_file()
        try:
            with patch.dict(os.environ, self._env_without("R2_BUCKET_NAME"), clear=True):
                with self.assertRaises(r2_upload.R2CredentialsMissingError):
                    r2_upload.upload(local, "modules/M1.test.mp4", "video/mp4", "public, max-age=31536000, immutable")
        finally:
            local.unlink(missing_ok=True)


# ----------------------------------------------------------------------------
# Upload behavior tests
# ----------------------------------------------------------------------------

class UploadTests(unittest.TestCase):
    """upload() PUTs the file with the requested Cache-Control + Content-Type,
    signs with AWS Sig V4, and returns the structured result dict."""

    def test_upload_returns_dict_with_expected_keys(self) -> None:
        local = _make_temp_file(b"x" * 4096)
        try:
            etag = '"deadbeef0123456789abcdef"'
            resp = _fake_response(status=200, headers={"ETag": etag})
            with patch.dict(os.environ, _FAKE_ENV, clear=True):
                with patch.object(r2_upload, "_urlopen", return_value=resp) as mock_open, \
                     patch.object(r2_upload, "_activity_log") as mock_log:
                    result = r2_upload.upload(
                        local, "modules/M1.deadbeef0123.mp4", "video/mp4",
                        "public, max-age=31536000, immutable",
                    )
            self.assertIn("key", result)
            self.assertIn("etag", result)
            self.assertIn("status", result)
            self.assertIn("bytes_uploaded", result)
            self.assertEqual(result["status"], 200)
            self.assertEqual(result["etag"].strip('"'), "deadbeef0123456789abcdef")
            self.assertEqual(result["bytes_uploaded"], 4096)
            # Activity log was triggered exactly once
            self.assertEqual(mock_log.call_count, 1)
            (action, details) = mock_log.call_args.args
            self.assertTrue(action.startswith("R2_UPLOAD_"))
            self.assertIn("modules/M1.deadbeef0123.mp4", action)
        finally:
            local.unlink(missing_ok=True)

    def test_upload_sets_cache_control_header(self) -> None:
        """The Cache-Control header argument MUST be applied to the signed request."""
        local = _make_temp_file()
        try:
            resp = _fake_response(status=200, headers={"ETag": '"abc"'})
            captured_req = {}

            def _spy(req, *args, **kwargs):
                captured_req["headers"] = dict(req.header_items())
                return resp

            with patch.dict(os.environ, _FAKE_ENV, clear=True):
                with patch.object(r2_upload, "_urlopen", side_effect=_spy), \
                     patch.object(r2_upload, "_activity_log"):
                    r2_upload.upload(
                        local, "modules/M1.aaa.mp4", "video/mp4",
                        "public, max-age=31536000, immutable",
                    )
            # urllib normalizes headers to title-case at .add_header time;
            # exact case-insensitive match.
            lower_headers = {k.lower(): v for k, v in captured_req["headers"].items()}
            self.assertEqual(
                lower_headers.get("cache-control"),
                "public, max-age=31536000, immutable",
            )
            self.assertEqual(lower_headers.get("content-type"), "video/mp4")
        finally:
            local.unlink(missing_ok=True)

    def test_upload_signs_with_aws_sig_v4(self) -> None:
        """Authorization header MUST be present + start with 'AWS4-HMAC-SHA256 Credential=...'."""
        local = _make_temp_file()
        try:
            resp = _fake_response(status=200, headers={"ETag": '"abc"'})
            captured_req = {}

            def _spy(req, *args, **kwargs):
                captured_req["headers"] = dict(req.header_items())
                return resp

            with patch.dict(os.environ, _FAKE_ENV, clear=True):
                with patch.object(r2_upload, "_urlopen", side_effect=_spy), \
                     patch.object(r2_upload, "_activity_log"):
                    r2_upload.upload(local, "modules/M1.test.mp4", "video/mp4", "public, max-age=31536000, immutable")
            lower_headers = {k.lower(): v for k, v in captured_req["headers"].items()}
            auth = lower_headers.get("authorization", "")
            self.assertTrue(auth.startswith("AWS4-HMAC-SHA256 "), f"Authorization header missing/wrong: {auth!r}")
            self.assertIn("Credential=AKIA_TEST_ID/", auth)
            self.assertIn("SignedHeaders=", auth)
            self.assertIn("Signature=", auth)
            # x-amz-date and x-amz-content-sha256 are both required by Sig V4
            self.assertIn("x-amz-date", lower_headers)
            self.assertIn("x-amz-content-sha256", lower_headers)
        finally:
            local.unlink(missing_ok=True)

    def test_upload_targets_correct_r2_endpoint(self) -> None:
        """URL MUST be https://<account>.r2.cloudflarestorage.com/<bucket>/<key>."""
        local = _make_temp_file()
        try:
            resp = _fake_response(status=200, headers={"ETag": '"abc"'})
            captured_req = {}

            def _spy(req, *args, **kwargs):
                captured_req["url"] = req.full_url
                return resp

            with patch.dict(os.environ, _FAKE_ENV, clear=True):
                with patch.object(r2_upload, "_urlopen", side_effect=_spy), \
                     patch.object(r2_upload, "_activity_log"):
                    r2_upload.upload(local, "modules/M1.xyz.mp4", "video/mp4", "public, max-age=31536000, immutable")
            url = captured_req["url"]
            self.assertIn(_FAKE_ENV["R2_ACCOUNT_ID"], url)
            self.assertIn(".r2.cloudflarestorage.com", url)
            self.assertIn(_FAKE_ENV["R2_BUCKET_NAME"], url)
            self.assertIn("modules/M1.xyz.mp4", url)
            self.assertTrue(url.startswith("https://"))
        finally:
            local.unlink(missing_ok=True)

    def test_upload_raises_on_http_error(self) -> None:
        """A non-2xx response MUST raise R2RequestError, not silent-pass."""
        local = _make_temp_file()
        try:
            resp = _fake_response(status=500, headers={}, body=b"InternalError")
            with patch.dict(os.environ, _FAKE_ENV, clear=True):
                with patch.object(r2_upload, "_urlopen", return_value=resp), \
                     patch.object(r2_upload, "_activity_log"):
                    with self.assertRaises(r2_upload.R2RequestError):
                        r2_upload.upload(local, "modules/M1.bad.mp4", "video/mp4", "public, max-age=31536000, immutable")
        finally:
            local.unlink(missing_ok=True)

    def test_upload_log_to_directus_can_be_disabled(self) -> None:
        local = _make_temp_file()
        try:
            resp = _fake_response(status=200, headers={"ETag": '"abc"'})
            with patch.dict(os.environ, _FAKE_ENV, clear=True):
                with patch.object(r2_upload, "_urlopen", return_value=resp), \
                     patch.object(r2_upload, "_activity_log") as mock_log:
                    r2_upload.upload(
                        local, "modules/M1.silent.mp4", "video/mp4",
                        "public, max-age=31536000, immutable",
                        log=False,
                    )
            self.assertEqual(mock_log.call_count, 0)
        finally:
            local.unlink(missing_ok=True)


# ----------------------------------------------------------------------------
# HEAD tests
# ----------------------------------------------------------------------------

class HeadTests(unittest.TestCase):

    def test_head_returns_metadata_dict_on_200(self) -> None:
        resp = _fake_response(status=200, headers={
            "ETag": '"abc123"',
            "Content-Length": "4096",
            "Content-Type": "video/mp4",
            "Cache-Control": "public, max-age=31536000, immutable",
        })
        with patch.dict(os.environ, _FAKE_ENV, clear=True):
            with patch.object(r2_upload, "_urlopen", return_value=resp):
                meta = r2_upload.head("modules/M1.aaa.mp4")
        self.assertIsNotNone(meta)
        assert meta is not None  # narrow for type-checkers
        self.assertEqual(meta["etag"].strip('"'), "abc123")
        self.assertEqual(meta["content_length"], 4096)
        self.assertEqual(meta["content_type"], "video/mp4")
        self.assertEqual(meta["cache_control"], "public, max-age=31536000, immutable")
        self.assertEqual(meta["status"], 200)

    def test_head_returns_none_on_404(self) -> None:
        import urllib.error
        with patch.dict(os.environ, _FAKE_ENV, clear=True):
            with patch.object(
                r2_upload,
                "_urlopen",
                side_effect=urllib.error.HTTPError(
                    "https://x", 404, "Not Found", {}, io.BytesIO(b""),
                ),
            ):
                meta = r2_upload.head("modules/M1.does-not-exist.mp4")
        self.assertIsNone(meta)

    def test_head_uses_HEAD_method(self) -> None:
        resp = _fake_response(status=200, headers={"ETag": '"abc"', "Content-Length": "1"})
        captured = {}

        def _spy(req, *args, **kwargs):
            captured["method"] = req.get_method()
            return resp

        with patch.dict(os.environ, _FAKE_ENV, clear=True):
            with patch.object(r2_upload, "_urlopen", side_effect=_spy):
                r2_upload.head("modules/M1.aaa.mp4")
        self.assertEqual(captured["method"], "HEAD")


# ----------------------------------------------------------------------------
# range_get tests
# ----------------------------------------------------------------------------

class RangeGetTests(unittest.TestCase):

    def test_range_get_issues_range_header(self) -> None:
        resp = _fake_response(
            status=206,
            headers={"Content-Range": "bytes 0-1023/4096", "Content-Length": "1024"},
            body=b"x" * 1024,
        )
        captured = {}

        def _spy(req, *args, **kwargs):
            captured["headers"] = dict(req.header_items())
            captured["method"] = req.get_method()
            return resp

        with patch.dict(os.environ, _FAKE_ENV, clear=True):
            with patch.object(r2_upload, "_urlopen", side_effect=_spy):
                r2_upload.range_get("modules/M1.aaa.mp4", (0, 1023))
        lower = {k.lower(): v for k, v in captured["headers"].items()}
        self.assertEqual(lower.get("range"), "bytes=0-1023")
        self.assertEqual(captured["method"], "GET")

    def test_range_get_returns_206_with_bytes(self) -> None:
        body = b"\x00\x11\x22" * 342  # 1026 bytes — close to 1024
        resp = _fake_response(
            status=206,
            headers={"Content-Range": "bytes 0-1025/4096", "Content-Length": str(len(body))},
            body=body,
        )
        with patch.dict(os.environ, _FAKE_ENV, clear=True):
            with patch.object(r2_upload, "_urlopen", return_value=resp):
                result = r2_upload.range_get("modules/M1.aaa.mp4", (0, 1025))
        self.assertEqual(result["status"], 206)
        self.assertEqual(result["content"], body)
        self.assertEqual(result["content_range"], "bytes 0-1025/4096")


if __name__ == "__main__":
    unittest.main()
