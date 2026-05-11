"""
Tests for Production/scripts/r2_atomic_publish.py — Stream F 5-step atomic publish
per R2_DEPLOYMENT_CONTRACT.md §Atomic publish order + spec §4.4 Phase D.

Step 0: verify_app_hash_encoding (Phase B gate) — RELEASE BLOCKS on Base64 output.
Step 1: Upload each asset with immutable Cache-Control.
Step 2: HEAD verify ETag + Content-Length; abort on mismatch.
Step 3: range_get bytes=0-1023 — expect 206 + matching first 1024 bytes; abort otherwise.
Step 4: Publish manifest.json (no-cache, must-revalidate) AND versioned manifest_v_<catalogVersion>.json (immutable).
Step 5: Smoke test — synthetic client fetches manifest + first asset + verifies SHA-256.

If any step fails, publish is aborted and prior manifest.json remains live.

DS-2 strict TDD: this file lands RED in a commit BEFORE r2_atomic_publish.py exists.

Run with:
    python3 -m unittest Production.scripts.tests.test_r2_atomic_publish -v

Mock-based — r2_upload module + verify_app_hash_encoding + smoke fetcher all
dependency-injected for offline test execution.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_TOOLING_REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_TOOLING_REPO))

from Production.lib.release_gates import (  # noqa: E402
    ReleaseBlockerError,
    AppRepoNotAccessibleError,
)
from Production.scripts import r2_atomic_publish  # noqa: E402  RED until GREEN commit


# ----------------------------------------------------------------------------
# Test helpers
# ----------------------------------------------------------------------------

def _write_temp(content: bytes, *, suffix: str = ".mp4") -> Path:
    fd, name = tempfile.mkstemp(prefix="r2_atomic_test_", suffix=suffix)
    with os.fdopen(fd, "wb") as fh:
        fh.write(content)
    return Path(name)


def _sha256_hex(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _make_manifest_blob(asset_hash: str, asset_url: str) -> bytes:
    """Minimal manifest matching MANIFEST_SCHEMA_V1.json — just enough for tests."""
    manifest = {
        "schemaVersion": 1,
        "catalogVersion": "2026-05-11T00:00:00Z.test",
        "generatedAt": "2026-05-11T00:00:00Z",
        "modules": [{
            "moduleId": "M1",
            "assetUrl": asset_url,
            "source_hash": "0" * 64,
            "output_hash": asset_hash,
            "bytes": 4096,
            "durationMs": 60000,
            "codec": {"video": "h264_high_yuv420p", "audio": "aac"},
            "resolution": {"width": 1280, "height": 720},
            "fps": 24,
            "audio": {"bitrate": 128000, "channels": 1, "sampleRate": 44100},
            "phaseBoundaries": {
                "story_start_ms": 0,
                "phase_b_start_ms": 10000,
                "phase_b_end_ms": 50000,
            },
            "reward": {"coins": 10},
        }],
    }
    return json.dumps(manifest).encode("utf-8")


def _fake_uploader(asset_hash: str, asset_bytes: bytes):
    """Return a MagicMock uploader module whose upload/head/range_get behave
    as a passing R2 publish unless overridden by the caller for negative tests."""
    mod = MagicMock()
    # ETag is the hash (R2 reports the SHA-256 etag-style for non-multipart PUTs;
    # in tests we treat ETag as the hex hash for verification).
    mod.upload.return_value = {
        "key": "stubbed",
        "etag": f'"{asset_hash}"',
        "status": 200,
        "bytes_uploaded": len(asset_bytes),
    }
    mod.head.return_value = {
        "etag": f'"{asset_hash}"',
        "content_length": len(asset_bytes),
        "content_type": "video/mp4",
        "cache_control": "public, max-age=31536000, immutable",
        "status": 200,
    }
    mod.range_get.return_value = {
        "status": 206,
        "content": asset_bytes[:1024],
        "content_range": f"bytes 0-{min(1023, len(asset_bytes)-1)}/{len(asset_bytes)}",
        "content_length": min(1024, len(asset_bytes)),
    }
    # Exception classes mirror r2_upload's.
    from Production.scripts.r2_upload import R2RequestError, R2CredentialsMissingError  # noqa
    mod.R2RequestError = R2RequestError
    mod.R2CredentialsMissingError = R2CredentialsMissingError
    return mod


def _verify_hash_passing():
    return MagicMock(return_value={
        "gate": "verify_app_hash_encoding",
        "result": "pass",
        "files_scanned": 12,
        "digest_call_count": 1,
        "evidence": [],
    })


# ----------------------------------------------------------------------------
# Public API surface tests
# ----------------------------------------------------------------------------

class PublicAPITests(unittest.TestCase):

    def test_atomic_publish_callable_exists(self) -> None:
        self.assertTrue(hasattr(r2_atomic_publish, "atomic_publish"))
        self.assertTrue(callable(r2_atomic_publish.atomic_publish))

    def test_aborted_exception_exists(self) -> None:
        self.assertTrue(hasattr(r2_atomic_publish, "AtomicPublishAbortedError"))
        self.assertTrue(issubclass(r2_atomic_publish.AtomicPublishAbortedError, Exception))

    def test_aborted_exception_carries_step_and_reason(self) -> None:
        err = r2_atomic_publish.AtomicPublishAbortedError(step=2, reason="ETag mismatch")
        self.assertEqual(err.step, 2)
        self.assertEqual(err.reason, "ETag mismatch")


# ----------------------------------------------------------------------------
# Step 0 — verify_app_hash_encoding gate tests
# ----------------------------------------------------------------------------

class Step0VerifyAppHashTests(unittest.TestCase):
    """Phase D MUST call verify_app_hash_encoding BEFORE any R2 traffic."""

    def _setup(self):
        asset_bytes = b"\x00" * 4096
        asset_hash = _sha256_hex(asset_bytes)
        local = _write_temp(asset_bytes)
        manifest_blob = _make_manifest_blob(
            asset_hash,
            f"https://cdn.mindfulnest.app/modules/M1.{asset_hash[:12]}.mp4",
        )
        manifest = _write_temp(manifest_blob, suffix=".json")
        uploader = _fake_uploader(asset_hash, asset_bytes)
        return asset_bytes, asset_hash, local, manifest, manifest_blob, uploader

    def test_verify_called_before_any_upload(self) -> None:
        asset_bytes, asset_hash, local, manifest, manifest_blob, uploader = self._setup()
        try:
            verifier = _verify_hash_passing()
            smoke = MagicMock(return_value=manifest_blob)
            asset_smoke = MagicMock(return_value=asset_bytes)
            call_order: list[str] = []

            verifier.side_effect = lambda *a, **kw: (call_order.append("verify"), {
                "gate": "verify_app_hash_encoding",
                "result": "pass",
                "files_scanned": 1,
                "digest_call_count": 0,
                "evidence": [],
            })[1]
            uploader.upload.side_effect = lambda *a, **kw: (call_order.append("upload"), {
                "key": "stubbed", "etag": f'"{asset_hash}"', "status": 200, "bytes_uploaded": 4096,
            })[1]

            r2_atomic_publish.atomic_publish(
                manifest_path=manifest,
                asset_specs=[{
                    "local_path": local,
                    "key": f"modules/M1.{asset_hash[:12]}.mp4",
                    "content_type": "video/mp4",
                    "expected_hash": asset_hash,
                }],
                catalog_version="2026-05-11T00:00:00Z.test",
                verify_app_hash_encoding=verifier,
                uploader=uploader,
                smoke_fetcher=smoke,
                asset_smoke_fetcher=asset_smoke,
            )
            self.assertGreater(len(call_order), 0)
            self.assertEqual(call_order[0], "verify", f"verify_app_hash_encoding was not the first call; order={call_order}")
        finally:
            local.unlink(missing_ok=True)
            manifest.unlink(missing_ok=True)

    def test_release_blocker_aborts_publish(self) -> None:
        asset_bytes, asset_hash, local, manifest, manifest_blob, uploader = self._setup()
        try:
            def _blocker(*a, **kw):
                raise ReleaseBlockerError(
                    gate="verify_app_hash_encoding",
                    message="Base64 detected",
                )
            with self.assertRaises(r2_atomic_publish.AtomicPublishAbortedError) as ctx:
                r2_atomic_publish.atomic_publish(
                    manifest_path=manifest,
                    asset_specs=[{
                        "local_path": local,
                        "key": "modules/M1.x.mp4",
                        "content_type": "video/mp4",
                        "expected_hash": asset_hash,
                    }],
                    catalog_version="2026-05-11T00:00:00Z.test",
                    verify_app_hash_encoding=_blocker,
                    uploader=uploader,
                )
            self.assertEqual(ctx.exception.step, 0)
            self.assertEqual(uploader.upload.call_count, 0)
        finally:
            local.unlink(missing_ok=True)
            manifest.unlink(missing_ok=True)

    def test_app_repo_missing_fails_closed_by_default(self) -> None:
        asset_bytes, asset_hash, local, manifest, manifest_blob, uploader = self._setup()
        try:
            def _missing(*a, **kw):
                raise AppRepoNotAccessibleError("App repo not found")
            with self.assertRaises(r2_atomic_publish.AtomicPublishAbortedError) as ctx:
                r2_atomic_publish.atomic_publish(
                    manifest_path=manifest,
                    asset_specs=[{
                        "local_path": local,
                        "key": "modules/M1.x.mp4",
                        "content_type": "video/mp4",
                        "expected_hash": asset_hash,
                    }],
                    catalog_version="2026-05-11T00:00:00Z.test",
                    verify_app_hash_encoding=_missing,
                    uploader=uploader,
                )
            self.assertEqual(ctx.exception.step, 0)
            self.assertEqual(uploader.upload.call_count, 0)
        finally:
            local.unlink(missing_ok=True)
            manifest.unlink(missing_ok=True)


# ----------------------------------------------------------------------------
# Step 1 — Upload tests
# ----------------------------------------------------------------------------

class Step1UploadTests(unittest.TestCase):

    def test_assets_uploaded_with_immutable_cache_control(self) -> None:
        asset_bytes = b"\x42" * 4096
        asset_hash = _sha256_hex(asset_bytes)
        local = _write_temp(asset_bytes)
        manifest_blob = _make_manifest_blob(asset_hash, f"https://cdn.mindfulnest.app/modules/M1.{asset_hash[:12]}.mp4")
        manifest = _write_temp(manifest_blob, suffix=".json")
        try:
            uploader = _fake_uploader(asset_hash, asset_bytes)
            smoke = MagicMock(return_value=manifest_blob)
            asset_smoke = MagicMock(return_value=asset_bytes)

            r2_atomic_publish.atomic_publish(
                manifest_path=manifest,
                asset_specs=[{
                    "local_path": local,
                    "key": f"modules/M1.{asset_hash[:12]}.mp4",
                    "content_type": "video/mp4",
                    "expected_hash": asset_hash,
                }],
                catalog_version="2026-05-11T00:00:00Z.test",
                verify_app_hash_encoding=_verify_hash_passing(),
                uploader=uploader,
                smoke_fetcher=smoke,
                asset_smoke_fetcher=asset_smoke,
            )
            # First upload call = the asset, must have immutable cache header.
            first_call = uploader.upload.call_args_list[0]
            kwargs = first_call.kwargs
            args = first_call.args
            cache_control = kwargs.get("cache_control") or (args[3] if len(args) >= 4 else None)
            self.assertEqual(cache_control, "public, max-age=31536000, immutable")
        finally:
            local.unlink(missing_ok=True)
            manifest.unlink(missing_ok=True)


# ----------------------------------------------------------------------------
# Step 2 — HEAD verify tests
# ----------------------------------------------------------------------------

class Step2HeadVerifyTests(unittest.TestCase):

    def test_etag_mismatch_aborts_step_2(self) -> None:
        asset_bytes = b"\x77" * 4096
        asset_hash = _sha256_hex(asset_bytes)
        local = _write_temp(asset_bytes)
        manifest_blob = _make_manifest_blob(asset_hash, f"https://cdn.mindfulnest.app/modules/M1.{asset_hash[:12]}.mp4")
        manifest = _write_temp(manifest_blob, suffix=".json")
        try:
            uploader = _fake_uploader(asset_hash, asset_bytes)
            # Head returns a different etag than expected.
            uploader.head.return_value = {
                "etag": '"FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF"',
                "content_length": len(asset_bytes),
                "content_type": "video/mp4",
                "cache_control": "public, max-age=31536000, immutable",
                "status": 200,
            }
            with self.assertRaises(r2_atomic_publish.AtomicPublishAbortedError) as ctx:
                r2_atomic_publish.atomic_publish(
                    manifest_path=manifest,
                    asset_specs=[{
                        "local_path": local,
                        "key": f"modules/M1.{asset_hash[:12]}.mp4",
                        "content_type": "video/mp4",
                        "expected_hash": asset_hash,
                    }],
                    catalog_version="2026-05-11T00:00:00Z.test",
                    verify_app_hash_encoding=_verify_hash_passing(),
                    uploader=uploader,
                )
            self.assertEqual(ctx.exception.step, 2)
        finally:
            local.unlink(missing_ok=True)
            manifest.unlink(missing_ok=True)

    def test_content_length_mismatch_aborts_step_2(self) -> None:
        asset_bytes = b"\x55" * 4096
        asset_hash = _sha256_hex(asset_bytes)
        local = _write_temp(asset_bytes)
        manifest_blob = _make_manifest_blob(asset_hash, f"https://cdn.mindfulnest.app/modules/M1.{asset_hash[:12]}.mp4")
        manifest = _write_temp(manifest_blob, suffix=".json")
        try:
            uploader = _fake_uploader(asset_hash, asset_bytes)
            uploader.head.return_value = {
                "etag": f'"{asset_hash}"',
                "content_length": 999,  # wrong
                "content_type": "video/mp4",
                "cache_control": "public, max-age=31536000, immutable",
                "status": 200,
            }
            with self.assertRaises(r2_atomic_publish.AtomicPublishAbortedError) as ctx:
                r2_atomic_publish.atomic_publish(
                    manifest_path=manifest,
                    asset_specs=[{
                        "local_path": local,
                        "key": f"modules/M1.{asset_hash[:12]}.mp4",
                        "content_type": "video/mp4",
                        "expected_hash": asset_hash,
                    }],
                    catalog_version="2026-05-11T00:00:00Z.test",
                    verify_app_hash_encoding=_verify_hash_passing(),
                    uploader=uploader,
                )
            self.assertEqual(ctx.exception.step, 2)
        finally:
            local.unlink(missing_ok=True)
            manifest.unlink(missing_ok=True)


# ----------------------------------------------------------------------------
# Step 3 — range_get tests
# ----------------------------------------------------------------------------

class Step3RangeGetTests(unittest.TestCase):

    def test_status_200_aborts_step_3(self) -> None:
        """If R2 returns 200 instead of 206, range support is broken — abort."""
        asset_bytes = b"\x88" * 4096
        asset_hash = _sha256_hex(asset_bytes)
        local = _write_temp(asset_bytes)
        manifest_blob = _make_manifest_blob(asset_hash, f"https://cdn.mindfulnest.app/modules/M1.{asset_hash[:12]}.mp4")
        manifest = _write_temp(manifest_blob, suffix=".json")
        try:
            uploader = _fake_uploader(asset_hash, asset_bytes)
            uploader.range_get.return_value = {
                "status": 200,  # wrong — should be 206
                "content": asset_bytes[:1024],
                "content_range": None,
                "content_length": 1024,
            }
            with self.assertRaises(r2_atomic_publish.AtomicPublishAbortedError) as ctx:
                r2_atomic_publish.atomic_publish(
                    manifest_path=manifest,
                    asset_specs=[{
                        "local_path": local,
                        "key": f"modules/M1.{asset_hash[:12]}.mp4",
                        "content_type": "video/mp4",
                        "expected_hash": asset_hash,
                    }],
                    catalog_version="2026-05-11T00:00:00Z.test",
                    verify_app_hash_encoding=_verify_hash_passing(),
                    uploader=uploader,
                )
            self.assertEqual(ctx.exception.step, 3)
        finally:
            local.unlink(missing_ok=True)
            manifest.unlink(missing_ok=True)

    def test_byte_mismatch_aborts_step_3(self) -> None:
        asset_bytes = b"\x99" * 4096
        asset_hash = _sha256_hex(asset_bytes)
        local = _write_temp(asset_bytes)
        manifest_blob = _make_manifest_blob(asset_hash, f"https://cdn.mindfulnest.app/modules/M1.{asset_hash[:12]}.mp4")
        manifest = _write_temp(manifest_blob, suffix=".json")
        try:
            uploader = _fake_uploader(asset_hash, asset_bytes)
            uploader.range_get.return_value = {
                "status": 206,
                "content": b"\xFF" * 1024,  # WRONG bytes
                "content_range": f"bytes 0-1023/{len(asset_bytes)}",
                "content_length": 1024,
            }
            with self.assertRaises(r2_atomic_publish.AtomicPublishAbortedError) as ctx:
                r2_atomic_publish.atomic_publish(
                    manifest_path=manifest,
                    asset_specs=[{
                        "local_path": local,
                        "key": f"modules/M1.{asset_hash[:12]}.mp4",
                        "content_type": "video/mp4",
                        "expected_hash": asset_hash,
                    }],
                    catalog_version="2026-05-11T00:00:00Z.test",
                    verify_app_hash_encoding=_verify_hash_passing(),
                    uploader=uploader,
                )
            self.assertEqual(ctx.exception.step, 3)
        finally:
            local.unlink(missing_ok=True)
            manifest.unlink(missing_ok=True)


# ----------------------------------------------------------------------------
# Step 4 — manifest publication tests
# ----------------------------------------------------------------------------

class Step4ManifestPublishTests(unittest.TestCase):

    def test_manifest_json_uses_no_cache_header(self) -> None:
        asset_bytes = b"\xAA" * 4096
        asset_hash = _sha256_hex(asset_bytes)
        local = _write_temp(asset_bytes)
        manifest_blob = _make_manifest_blob(asset_hash, f"https://cdn.mindfulnest.app/modules/M1.{asset_hash[:12]}.mp4")
        manifest = _write_temp(manifest_blob, suffix=".json")
        try:
            uploader = _fake_uploader(asset_hash, asset_bytes)
            smoke = MagicMock(return_value=manifest_blob)
            asset_smoke = MagicMock(return_value=asset_bytes)

            r2_atomic_publish.atomic_publish(
                manifest_path=manifest,
                asset_specs=[{
                    "local_path": local,
                    "key": f"modules/M1.{asset_hash[:12]}.mp4",
                    "content_type": "video/mp4",
                    "expected_hash": asset_hash,
                }],
                catalog_version="2026-05-11T00:00:00Z.test",
                verify_app_hash_encoding=_verify_hash_passing(),
                uploader=uploader,
                smoke_fetcher=smoke,
                asset_smoke_fetcher=asset_smoke,
            )
            # Look for the manifest.json upload call.
            manifest_calls = [c for c in uploader.upload.call_args_list
                              if (c.kwargs.get("key") or c.args[1]) == "catalog/manifest.json"]
            self.assertEqual(len(manifest_calls), 1, f"Expected exactly 1 manifest.json upload; got {manifest_calls}")
            cc = (manifest_calls[0].kwargs.get("cache_control")
                  or (manifest_calls[0].args[3] if len(manifest_calls[0].args) >= 4 else None))
            self.assertEqual(cc, "no-cache, must-revalidate")
        finally:
            local.unlink(missing_ok=True)
            manifest.unlink(missing_ok=True)

    def test_versioned_manifest_published_with_immutable_header(self) -> None:
        asset_bytes = b"\xBB" * 4096
        asset_hash = _sha256_hex(asset_bytes)
        local = _write_temp(asset_bytes)
        manifest_blob = _make_manifest_blob(asset_hash, f"https://cdn.mindfulnest.app/modules/M1.{asset_hash[:12]}.mp4")
        manifest = _write_temp(manifest_blob, suffix=".json")
        try:
            uploader = _fake_uploader(asset_hash, asset_bytes)
            smoke = MagicMock(return_value=manifest_blob)
            asset_smoke = MagicMock(return_value=asset_bytes)
            catalog_version = "2026-05-11T00:00:00Z.test"
            r2_atomic_publish.atomic_publish(
                manifest_path=manifest,
                asset_specs=[{
                    "local_path": local,
                    "key": f"modules/M1.{asset_hash[:12]}.mp4",
                    "content_type": "video/mp4",
                    "expected_hash": asset_hash,
                }],
                catalog_version=catalog_version,
                verify_app_hash_encoding=_verify_hash_passing(),
                uploader=uploader,
                smoke_fetcher=smoke,
                asset_smoke_fetcher=asset_smoke,
            )
            versioned_key = f"catalog/manifest_v_{catalog_version}.json"
            versioned_calls = [c for c in uploader.upload.call_args_list
                               if (c.kwargs.get("key") or c.args[1]) == versioned_key]
            self.assertEqual(len(versioned_calls), 1)
            cc = (versioned_calls[0].kwargs.get("cache_control")
                  or (versioned_calls[0].args[3] if len(versioned_calls[0].args) >= 4 else None))
            self.assertEqual(cc, "public, max-age=31536000, immutable")
        finally:
            local.unlink(missing_ok=True)
            manifest.unlink(missing_ok=True)


# ----------------------------------------------------------------------------
# Step 5 — Smoke test
# ----------------------------------------------------------------------------

class Step5SmokeTests(unittest.TestCase):

    def test_smoke_sha_mismatch_aborts(self) -> None:
        asset_bytes = b"\xCC" * 4096
        asset_hash = _sha256_hex(asset_bytes)
        local = _write_temp(asset_bytes)
        manifest_blob = _make_manifest_blob(asset_hash, f"https://cdn.mindfulnest.app/modules/M1.{asset_hash[:12]}.mp4")
        manifest = _write_temp(manifest_blob, suffix=".json")
        try:
            uploader = _fake_uploader(asset_hash, asset_bytes)
            smoke = MagicMock(return_value=manifest_blob)
            # Fetched asset bytes don't match expected hash → smoke must fail.
            wrong_asset = b"\xDE\xAD" * 2048
            asset_smoke = MagicMock(return_value=wrong_asset)
            with self.assertRaises(r2_atomic_publish.AtomicPublishAbortedError) as ctx:
                r2_atomic_publish.atomic_publish(
                    manifest_path=manifest,
                    asset_specs=[{
                        "local_path": local,
                        "key": f"modules/M1.{asset_hash[:12]}.mp4",
                        "content_type": "video/mp4",
                        "expected_hash": asset_hash,
                    }],
                    catalog_version="2026-05-11T00:00:00Z.test",
                    verify_app_hash_encoding=_verify_hash_passing(),
                    uploader=uploader,
                    smoke_fetcher=smoke,
                    asset_smoke_fetcher=asset_smoke,
                )
            self.assertEqual(ctx.exception.step, 5)
        finally:
            local.unlink(missing_ok=True)
            manifest.unlink(missing_ok=True)

    def test_successful_publish_returns_structured_result(self) -> None:
        asset_bytes = b"\xEE" * 4096
        asset_hash = _sha256_hex(asset_bytes)
        local = _write_temp(asset_bytes)
        manifest_blob = _make_manifest_blob(asset_hash, f"https://cdn.mindfulnest.app/modules/M1.{asset_hash[:12]}.mp4")
        manifest = _write_temp(manifest_blob, suffix=".json")
        try:
            uploader = _fake_uploader(asset_hash, asset_bytes)
            smoke = MagicMock(return_value=manifest_blob)
            asset_smoke = MagicMock(return_value=asset_bytes)
            catalog_version = "2026-05-11T00:00:00Z.test"
            result = r2_atomic_publish.atomic_publish(
                manifest_path=manifest,
                asset_specs=[{
                    "local_path": local,
                    "key": f"modules/M1.{asset_hash[:12]}.mp4",
                    "content_type": "video/mp4",
                    "expected_hash": asset_hash,
                }],
                catalog_version=catalog_version,
                verify_app_hash_encoding=_verify_hash_passing(),
                uploader=uploader,
                smoke_fetcher=smoke,
                asset_smoke_fetcher=asset_smoke,
            )
            self.assertIn("catalog_version", result)
            self.assertEqual(result["catalog_version"], catalog_version)
            self.assertIn("asset_keys", result)
            self.assertEqual(len(result["asset_keys"]), 1)
            self.assertIn("manifest_key", result)
            self.assertEqual(result["manifest_key"], "catalog/manifest.json")
            self.assertIn("versioned_manifest_key", result)
            self.assertEqual(result["versioned_manifest_key"], f"catalog/manifest_v_{catalog_version}.json")
            self.assertIn("published_at", result)
        finally:
            local.unlink(missing_ok=True)
            manifest.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
