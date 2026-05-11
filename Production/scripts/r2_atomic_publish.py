"""
r2_atomic_publish.py — Stream F 5-step atomic publish orchestration.

Authored per V59_PRODUCTION_PIPELINE_STREAM_BF_SPEC_v1.md §4.4 (Phase D) +
R2_DEPLOYMENT_CONTRACT.md §Atomic publish order.

Governing LDs:
  - LD-432 CDN_CLOUDFLARE_R2_V1
  - LD-404 MANIFEST_SCHEMA_V1 (consumes the named-object phaseBoundaries per LD-412
    AMEND landing in this Phase D)
  - LD-282 CATALOG_DELIVERY

5-step protocol:
  Step 0 (gate): verify_app_hash_encoding — RELEASE BLOCKS if app uses Base64 output.
  Step 1: Upload each asset with `public, max-age=31536000, immutable` Cache-Control.
  Step 2: HEAD each asset; verify ETag matches expected hash + Content-Length matches file.
  Step 3: range_get bytes=0-1023; status MUST be 206; first 1024 bytes MUST match local.
  Step 4: Upload manifest.json (`no-cache, must-revalidate`) AND versioned manifest_v_<cat>.json
          (`public, max-age=31536000, immutable`).
  Step 5: Smoke test — synthetic client fetches manifest + first asset; verifies SHA-256.

If any step fails, AtomicPublishAbortedError is raised carrying the step number +
reason + evidence dict. Prior manifest.json is preserved (we never overwrite it
before Step 4 succeeds).

Public API:
    atomic_publish(manifest_path, asset_specs, catalog_version, *, ...) -> dict

Exceptions:
    AtomicPublishAbortedError — any of Steps 0-5 failed; the publish is aborted.

This module performs BUILD-ONLY infrastructure. The Firebase-to-R2 cutover
(spec §4.4 Step 7 / migrate_firebase_to_r2.py) is OUT OF SCOPE for this build
and requires explicit Kim authorization per CLAUDE.md prohibited-actions list
(production user-facing impact).
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import urllib.request
from pathlib import Path
from typing import Any, Callable, Optional

from Production.lib.release_gates import (
    AppRepoNotAccessibleError,
    ReleaseBlockerError,
    verify_app_hash_encoding as _default_verify_app_hash_encoding,
)


# ---------------------------------------------------------------------------
# Cache-Control headers per R2_DEPLOYMENT_CONTRACT.md
# ---------------------------------------------------------------------------


ASSET_CACHE_CONTROL = "public, max-age=31536000, immutable"
MANIFEST_CURRENT_CACHE_CONTROL = "no-cache, must-revalidate"
MANIFEST_VERSIONED_CACHE_CONTROL = "public, max-age=31536000, immutable"

DEFAULT_CDN_BASE_URL = "https://cdn.mindfulnest.app"


# ---------------------------------------------------------------------------
# Exception types
# ---------------------------------------------------------------------------


class AtomicPublishAbortedError(RuntimeError):
    """Raised when atomic_publish() halts at any of the 5 steps (or step 0 gate).

    Attributes:
        step: int — the step at which the abort occurred (0..5).
        reason: str — human-readable explanation.
        evidence: dict — structured evidence (per-asset failures, mismatched hashes, etc.).
    """

    def __init__(self, *, step: int, reason: str, evidence: Optional[dict] = None):
        super().__init__(f"[step {step}] {reason}")
        self.step = step
        self.reason = reason
        self.evidence = evidence or {}


# ---------------------------------------------------------------------------
# Default smoke fetcher (urllib over public CDN)
# ---------------------------------------------------------------------------


def _default_smoke_fetcher(url: str) -> bytes:
    """Default smoke-test fetcher — urllib GET against the public CDN URL.

    Tests inject a MagicMock that returns canned bytes instead.
    """
    with urllib.request.urlopen(url, timeout=30.0) as resp:  # pragma: no cover (network)
        return resp.read()


def _strip_etag(etag: Optional[str]) -> str:
    if etag is None:
        return ""
    return etag.strip().strip('"')


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def atomic_publish(
    *,
    manifest_path: Path | str,
    asset_specs: list[dict],
    catalog_version: str,
    app_repo_path: Optional[Path] = None,
    fail_closed_on_app_repo_missing: bool = True,
    verify_app_hash_encoding: Optional[Callable] = None,
    uploader: Any = None,
    smoke_fetcher: Optional[Callable[[str], bytes]] = None,
    asset_smoke_fetcher: Optional[Callable[[str], bytes]] = None,
    cdn_base_url: str = DEFAULT_CDN_BASE_URL,
) -> dict[str, Any]:
    """Execute the 5-step atomic publish protocol.

    Args:
        manifest_path: Local path to the manifest.json to publish.
        asset_specs: List of dicts, each with keys:
            local_path: Path  — local file to upload
            key: str          — R2 object key (e.g., "modules/M1.<sha12>.mp4")
            content_type: str — Content-Type header
            expected_hash: str — full SHA-256 hex of the local file (used for
                                 verification in Steps 2/3/5)
        catalog_version: Used to construct the versioned manifest key
            ("catalog/manifest_v_<catalog_version>.json"). Format per
            MANIFEST_SCHEMA_V1.json $catalogVersion.
        app_repo_path: Optional override for verify_app_hash_encoding's repo path.
        fail_closed_on_app_repo_missing: If True (default), an absent app repo
            aborts the publish per spec §15.7 / R2_DEPLOYMENT_CONTRACT.md.
            CI / sandboxed contexts can pass False to soft-pass with audit row.
        verify_app_hash_encoding: Dependency-injection of the Phase B gate. Defaults
            to Production.lib.release_gates.verify_app_hash_encoding.
        uploader: Dependency-injection of the r2_upload module (anything with
            upload/head/range_get callables). Defaults to Production.scripts.r2_upload.
        smoke_fetcher: Callable(url) -> bytes for fetching manifest.json during Step 5.
        asset_smoke_fetcher: Callable(url) -> bytes for fetching the first asset
            during Step 5. Separate from smoke_fetcher so tests can return different
            bodies for manifest vs asset fetches.
        cdn_base_url: Public CDN base URL (default: https://cdn.mindfulnest.app).

    Returns:
        {
            "catalog_version": str,
            "published_at": ISO-8601 UTC timestamp,
            "asset_keys": list[str],
            "manifest_key": "catalog/manifest.json",
            "versioned_manifest_key": "catalog/manifest_v_<catalog_version>.json",
            "verify_app_hash_result": dict,
        }

    Raises:
        AtomicPublishAbortedError if any of Steps 0-5 fails.
    """
    verifier = verify_app_hash_encoding or _default_verify_app_hash_encoding
    if uploader is None:
        from Production.scripts import r2_upload as uploader  # type: ignore
    smoke = smoke_fetcher or _default_smoke_fetcher
    asset_smoke = asset_smoke_fetcher or _default_smoke_fetcher

    manifest_local = Path(manifest_path)

    # ---------- Step 0: Phase B gate ----------
    try:
        verify_result = verifier(app_repo_path)
    except ReleaseBlockerError as e:
        raise AtomicPublishAbortedError(
            step=0,
            reason=f"verify_app_hash_encoding RELEASE BLOCKED: {e}",
            evidence={"gate": e.gate, "blocker_evidence": e.evidence},
        ) from e
    except AppRepoNotAccessibleError as e:
        if fail_closed_on_app_repo_missing:
            raise AtomicPublishAbortedError(
                step=0,
                reason=(
                    f"App repo not accessible and fail_closed_on_app_repo_missing=True: {e}"
                ),
                evidence={"app_repo_path": str(app_repo_path)},
            ) from e
        # Soft-pass path for CI / sandboxed contexts.
        verify_result = {
            "gate": "verify_app_hash_encoding",
            "result": "deferred",
            "reason": str(e),
        }

    # ---------- Step 1: Upload each asset ----------
    upload_results = []
    for spec in asset_specs:
        local_path = Path(spec["local_path"])
        key = spec["key"]
        content_type = spec.get("content_type", "video/mp4")
        try:
            result = uploader.upload(
                local_path=local_path,
                key=key,
                content_type=content_type,
                cache_control=ASSET_CACHE_CONTROL,
            )
        except Exception as e:
            raise AtomicPublishAbortedError(
                step=1,
                reason=f"Asset upload failed for key={key!r}: {type(e).__name__}: {e}",
                evidence={"key": key, "exception": str(e)},
            ) from e
        upload_results.append({"spec": spec, "result": result})

    # ---------- Step 2: HEAD verify each asset ----------
    for entry in upload_results:
        spec = entry["spec"]
        key = spec["key"]
        expected_hash = spec["expected_hash"]
        local_size = Path(spec["local_path"]).stat().st_size
        meta = uploader.head(key)
        if meta is None:
            raise AtomicPublishAbortedError(
                step=2,
                reason=f"HEAD returned 404 for just-uploaded key={key!r}",
                evidence={"key": key},
            )
        actual_etag = _strip_etag(meta.get("etag"))
        if actual_etag != expected_hash:
            raise AtomicPublishAbortedError(
                step=2,
                reason=(
                    f"ETag mismatch for key={key!r}: "
                    f"expected={expected_hash!r}, got={actual_etag!r}"
                ),
                evidence={"key": key, "expected_etag": expected_hash, "actual_etag": actual_etag},
            )
        actual_length = meta.get("content_length")
        if actual_length is not None and actual_length != local_size:
            raise AtomicPublishAbortedError(
                step=2,
                reason=(
                    f"Content-Length mismatch for key={key!r}: "
                    f"local_size={local_size}, head_length={actual_length}"
                ),
                evidence={"key": key, "local_size": local_size, "head_length": actual_length},
            )

    # ---------- Step 3: range_get verify each asset ----------
    for entry in upload_results:
        spec = entry["spec"]
        key = spec["key"]
        local_bytes = Path(spec["local_path"]).read_bytes()
        expected_prefix = local_bytes[:1024]
        end_offset = max(0, len(expected_prefix) - 1)
        rg = uploader.range_get(key, (0, end_offset))
        if rg.get("status") != 206:
            raise AtomicPublishAbortedError(
                step=3,
                reason=(
                    f"Range request returned status={rg.get('status')} for key={key!r}; "
                    f"expected 206 Partial Content. R2 misconfiguration likely."
                ),
                evidence={"key": key, "status": rg.get("status")},
            )
        actual_prefix = rg.get("content") or b""
        if bytes(actual_prefix) != bytes(expected_prefix):
            raise AtomicPublishAbortedError(
                step=3,
                reason=f"First-1024 byte mismatch for key={key!r}",
                evidence={
                    "key": key,
                    "expected_sha256": _sha256(expected_prefix),
                    "actual_sha256": _sha256(actual_prefix),
                },
            )

    # ---------- Step 4: Publish manifests ----------
    manifest_key = "catalog/manifest.json"
    versioned_manifest_key = f"catalog/manifest_v_{catalog_version}.json"
    try:
        uploader.upload(
            local_path=manifest_local,
            key=manifest_key,
            content_type="application/json",
            cache_control=MANIFEST_CURRENT_CACHE_CONTROL,
        )
    except Exception as e:
        raise AtomicPublishAbortedError(
            step=4,
            reason=f"manifest.json upload failed: {type(e).__name__}: {e}",
            evidence={"key": manifest_key, "exception": str(e)},
        ) from e
    try:
        uploader.upload(
            local_path=manifest_local,
            key=versioned_manifest_key,
            content_type="application/json",
            cache_control=MANIFEST_VERSIONED_CACHE_CONTROL,
        )
    except Exception as e:
        raise AtomicPublishAbortedError(
            step=4,
            reason=f"versioned manifest upload failed: {type(e).__name__}: {e}",
            evidence={"key": versioned_manifest_key, "exception": str(e)},
        ) from e

    # ---------- Step 5: Smoke test ----------
    manifest_url = f"{cdn_base_url.rstrip('/')}/{manifest_key}"
    try:
        manifest_bytes = smoke(manifest_url)
        parsed = json.loads(manifest_bytes)
    except Exception as e:
        raise AtomicPublishAbortedError(
            step=5,
            reason=f"smoke fetch/parse of manifest.json failed: {type(e).__name__}: {e}",
            evidence={"url": manifest_url, "exception": str(e)},
        ) from e
    modules = parsed.get("modules") or []
    if not modules:
        raise AtomicPublishAbortedError(
            step=5,
            reason="smoke fetch of manifest.json returned no modules entries",
            evidence={"manifest_bytes_len": len(manifest_bytes)},
        )
    first_module = modules[0]
    first_asset_url = first_module["assetUrl"]
    expected_output_hash = first_module["output_hash"]
    try:
        asset_bytes = asset_smoke(first_asset_url)
    except Exception as e:
        raise AtomicPublishAbortedError(
            step=5,
            reason=f"smoke fetch of first asset failed: {type(e).__name__}: {e}",
            evidence={"url": first_asset_url, "exception": str(e)},
        ) from e
    actual_hash = _sha256(asset_bytes)
    if actual_hash != expected_output_hash:
        raise AtomicPublishAbortedError(
            step=5,
            reason=(
                f"smoke SHA-256 mismatch for first asset: "
                f"manifest.output_hash={expected_output_hash!r}, "
                f"fetched bytes hash={actual_hash!r}"
            ),
            evidence={
                "url": first_asset_url,
                "expected_hash": expected_output_hash,
                "actual_hash": actual_hash,
            },
        )

    return {
        "catalog_version": catalog_version,
        "published_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "asset_keys": [entry["spec"]["key"] for entry in upload_results],
        "manifest_key": manifest_key,
        "versioned_manifest_key": versioned_manifest_key,
        "verify_app_hash_result": verify_result,
    }
