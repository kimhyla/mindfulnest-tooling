"""
r2_upload.py — Cloudflare R2 S3-compatible upload helper (urllib + AWS Sig V4).

Authored per V59_PRODUCTION_PIPELINE_STREAM_BF_SPEC_v1.md §4.4 (Phase D) +
R2_DEPLOYMENT_CONTRACT.md.

Governing LDs:
  - LD-432 CDN_CLOUDFLARE_R2_V1 (R2 is the locked CDN vendor; supersedes Firebase Storage)
  - LD-404 MANIFEST_SCHEMA_V1 (consumer of these uploads via r2_atomic_publish.py)
  - LD-405 SECRETS_MANAGEMENT (env-var loading discipline)

Open Decision 3 (LOCKED Kim 2026-05-08): urllib + AWS Sig V4 hand-rolled (NOT
boto3). Rationale per spec §13.1: avoids Rule 26 first-integration-with-new-vendor
Opus escalation mid-execution; higher LOC + bug surface accepted in exchange for
execution stability. The hand-rolled implementation is feasible because R2 is
S3-compatible at the wire level and the signing algorithm is well-documented.

Public API:
    upload(local_path, key, content_type, cache_control, *, log=True) -> dict
    head(key) -> dict | None
    range_get(key, byte_range) -> dict

Exceptions:
    R2CredentialsMissingError — any of the 4 required env vars are unset.
    R2RequestError           — R2 returned a non-success HTTP response.

Activity-log integration: every successful upload is recorded in
`prod_activity_log` with action `R2_UPLOAD_<key>` via
`Production.lib.directus.try_post_or_queue` (soft-fail; queues offline).

Test entry points (underscore-prefixed wrappers exposed for test injection):
    _urlopen, _activity_log
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import hmac
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Mapping, Optional, Tuple


# ---------------------------------------------------------------------------
# Exception types
# ---------------------------------------------------------------------------


class R2CredentialsMissingError(RuntimeError):
    """Raised when any of R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY /
    R2_ACCOUNT_ID / R2_BUCKET_NAME is missing from the environment.

    The error message lists the missing keys so the caller can fix env without
    paging through the source.
    """


class R2RequestError(RuntimeError):
    """Raised when R2 returns a non-success HTTP response on upload/head/range_get."""

    def __init__(self, message: str, *, status: int, key: str, body: bytes = b""):
        super().__init__(message)
        self.status = status
        self.key = key
        self.body = body


# ---------------------------------------------------------------------------
# Env-var contract
# ---------------------------------------------------------------------------


R2_ACCESS_KEY_ID_ENV = "R2_ACCESS_KEY_ID"
R2_SECRET_ACCESS_KEY_ENV = "R2_SECRET_ACCESS_KEY"
R2_ACCOUNT_ID_ENV = "R2_ACCOUNT_ID"
R2_BUCKET_NAME_ENV = "R2_BUCKET_NAME"

_REQUIRED_ENV = (
    R2_ACCESS_KEY_ID_ENV,
    R2_SECRET_ACCESS_KEY_ENV,
    R2_ACCOUNT_ID_ENV,
    R2_BUCKET_NAME_ENV,
)

# R2 is S3-compatible. Sig V4 region for R2 is the literal string "auto".
_R2_SIGNING_REGION = "auto"
_R2_SIGNING_SERVICE = "s3"

# SHA-256 of empty payload — used as x-amz-content-sha256 for HEAD/GET.
_EMPTY_PAYLOAD_SHA256 = (
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
)


def _load_credentials(env: Optional[Mapping[str, str]] = None) -> dict[str, str]:
    """Return the 4 R2 env vars or raise R2CredentialsMissingError."""
    source = env if env is not None else os.environ
    missing = [k for k in _REQUIRED_ENV if not source.get(k)]
    if missing:
        raise R2CredentialsMissingError(
            f"R2 environment variables missing: {', '.join(missing)}. "
            f"Set them in Doppler/shell before invoking r2_upload."
        )
    return {k: source[k] for k in _REQUIRED_ENV}


# ---------------------------------------------------------------------------
# AWS Sig V4 implementation (deliberately self-contained — no boto3)
# ---------------------------------------------------------------------------


def _hex_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hmac_sha256(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _sigv4_signing_key(secret: str, datestamp: str, region: str, service: str) -> bytes:
    """Derive the Sig V4 signing key.

    kSigning = HMAC(HMAC(HMAC(HMAC("AWS4"+secret, date), region), service), "aws4_request")
    """
    k_date = _hmac_sha256(("AWS4" + secret).encode("utf-8"), datestamp)
    k_region = _hmac_sha256(k_date, region)
    k_service = _hmac_sha256(k_region, service)
    return _hmac_sha256(k_service, "aws4_request")


def _canonical_uri(bucket: str, key: str) -> str:
    """Build canonical URI: /<bucket>/<key> with per-segment URI encoding."""
    parts = [bucket] + key.split("/")
    encoded = "/" + "/".join(urllib.parse.quote(p, safe="") for p in parts)
    return encoded


def _canonical_headers(headers: Mapping[str, str]) -> Tuple[str, str]:
    """Return (canonical_headers_block, signed_headers_string).

    Per Sig V4 spec:
      - lowercase header name
      - sequential whitespace collapsed
      - sorted ascending by name
      - each line terminates with \\n
    """
    items = []
    for name, value in headers.items():
        items.append((name.lower(), str(value).strip()))
    items.sort(key=lambda kv: kv[0])
    canonical = "".join(f"{k}:{v}\n" for k, v in items)
    signed = ";".join(k for k, _ in items)
    return canonical, signed


def _sign_request(
    *,
    method: str,
    bucket: str,
    key: str,
    host: str,
    payload_sha256: str,
    extra_headers: Mapping[str, str],
    access_key: str,
    secret_key: str,
    region: str = _R2_SIGNING_REGION,
    service: str = _R2_SIGNING_SERVICE,
    now: Optional[_dt.datetime] = None,
) -> dict[str, str]:
    """Compute the full set of headers (including Authorization) for a Sig V4 request."""
    now = now or _dt.datetime.now(_dt.timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    datestamp = now.strftime("%Y%m%d")

    # Required headers for Sig V4 are host + x-amz-date + x-amz-content-sha256
    # plus whatever the caller wants signed.
    headers: dict[str, str] = {
        "host": host,
        "x-amz-date": amz_date,
        "x-amz-content-sha256": payload_sha256,
    }
    for k, v in extra_headers.items():
        headers[k.lower()] = str(v)

    canonical_headers, signed_headers = _canonical_headers(headers)
    canonical_uri = _canonical_uri(bucket, key)
    canonical_request = (
        f"{method}\n"
        f"{canonical_uri}\n"
        f"\n"  # empty canonical query string
        f"{canonical_headers}\n"
        f"{signed_headers}\n"
        f"{payload_sha256}"
    )

    credential_scope = f"{datestamp}/{region}/{service}/aws4_request"
    string_to_sign = (
        f"AWS4-HMAC-SHA256\n"
        f"{amz_date}\n"
        f"{credential_scope}\n"
        f"{_hex_sha256(canonical_request.encode('utf-8'))}"
    )

    signing_key = _sigv4_signing_key(secret_key, datestamp, region, service)
    signature = hmac.new(
        signing_key, string_to_sign.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    authorization = (
        f"AWS4-HMAC-SHA256 "
        f"Credential={access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, "
        f"Signature={signature}"
    )
    headers["authorization"] = authorization
    return headers


# ---------------------------------------------------------------------------
# urllib + activity-log thin wrappers (patch points for tests)
# ---------------------------------------------------------------------------


def _urlopen(req: urllib.request.Request, *, timeout: float = 60.0):  # pragma: no cover
    """Thin wrapper around urllib.request.urlopen so tests can patch this symbol
    directly without monkey-patching the urllib module."""
    return urllib.request.urlopen(req, timeout=timeout)


def _activity_log(action: str, details: dict) -> None:
    """Soft-fail activity-log write via try_post_or_queue.

    Per spec §4.4 Step 4: each upload logs `R2_UPLOAD_<key>` to prod_activity_log.
    Soft-fail because R2 uploads should never be blocked by an audit-log failure;
    try_post_or_queue handles offline queueing per CLAUDE.md Rule 35.
    """
    try:
        from Production.lib import directus  # local import: avoid hard dep at module load
    except Exception:
        return
    try:
        directus.try_post_or_queue(
            collection="prod_activity_log",
            payload={"action": action, "details": details, "performed_by": "r2_upload"},
        )
    except Exception:
        # Soft-fail: never propagate audit-log errors to the upload caller.
        return


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _endpoint_host(account_id: str) -> str:
    return f"{account_id}.r2.cloudflarestorage.com"


def _endpoint_url(account_id: str, bucket: str, key: str) -> str:
    host = _endpoint_host(account_id)
    quoted_key = "/".join(urllib.parse.quote(p, safe="") for p in key.split("/"))
    return f"https://{host}/{urllib.parse.quote(bucket, safe='')}/{quoted_key}"


def upload(
    local_path: Path | str,
    key: str,
    content_type: str,
    cache_control: str,
    *,
    log: bool = True,
) -> dict[str, Any]:
    """PUT a local file to R2 with the supplied Content-Type + Cache-Control headers.

    Returns:
        {
            "key": <key>,
            "etag": <ETag header from response>,
            "status": <HTTP status int>,
            "bytes_uploaded": <int>,
        }

    Raises:
        R2CredentialsMissingError if any required env var is unset.
        R2RequestError if R2 returns a non-2xx HTTP response.
    """
    creds = _load_credentials()
    local = Path(local_path)
    body = local.read_bytes()
    payload_sha256 = _hex_sha256(body)

    headers = _sign_request(
        method="PUT",
        bucket=creds[R2_BUCKET_NAME_ENV],
        key=key,
        host=_endpoint_host(creds[R2_ACCOUNT_ID_ENV]),
        payload_sha256=payload_sha256,
        extra_headers={
            "content-type": content_type,
            "content-length": str(len(body)),
            "cache-control": cache_control,
        },
        access_key=creds[R2_ACCESS_KEY_ID_ENV],
        secret_key=creds[R2_SECRET_ACCESS_KEY_ENV],
    )

    url = _endpoint_url(creds[R2_ACCOUNT_ID_ENV], creds[R2_BUCKET_NAME_ENV], key)
    req = urllib.request.Request(url=url, data=body, method="PUT")
    for name, value in headers.items():
        req.add_header(name, value)

    try:
        resp = _urlopen(req)
    except urllib.error.HTTPError as e:
        raise R2RequestError(
            f"R2 PUT failed: HTTP {e.code} for key={key!r}",
            status=e.code,
            key=key,
            body=e.read() if hasattr(e, "read") else b"",
        ) from e

    with resp as r:
        status = getattr(r, "status", None) or r.getcode()
        if status < 200 or status >= 300:
            raise R2RequestError(
                f"R2 PUT failed: HTTP {status} for key={key!r}",
                status=status,
                key=key,
                body=r.read() if hasattr(r, "read") else b"",
            )
        etag = (
            r.getheader("ETag")
            if hasattr(r, "getheader")
            else r.headers.get("ETag") if hasattr(r, "headers") else None
        )

    result: dict[str, Any] = {
        "key": key,
        "etag": etag,
        "status": status,
        "bytes_uploaded": len(body),
    }
    if log:
        _activity_log(
            f"R2_UPLOAD_{key}",
            {
                "key": key,
                "bytes": len(body),
                "content_type": content_type,
                "cache_control": cache_control,
                "etag": etag,
                "sha256": payload_sha256,
            },
        )
    return result


def head(key: str) -> Optional[dict[str, Any]]:
    """HEAD an R2 object. Returns metadata dict on 200; None on 404.

    Returned dict keys: etag, content_length (int), content_type, cache_control, status.
    """
    creds = _load_credentials()
    headers = _sign_request(
        method="HEAD",
        bucket=creds[R2_BUCKET_NAME_ENV],
        key=key,
        host=_endpoint_host(creds[R2_ACCOUNT_ID_ENV]),
        payload_sha256=_EMPTY_PAYLOAD_SHA256,
        extra_headers={},
        access_key=creds[R2_ACCESS_KEY_ID_ENV],
        secret_key=creds[R2_SECRET_ACCESS_KEY_ENV],
    )
    url = _endpoint_url(creds[R2_ACCOUNT_ID_ENV], creds[R2_BUCKET_NAME_ENV], key)
    req = urllib.request.Request(url=url, method="HEAD")
    for name, value in headers.items():
        req.add_header(name, value)

    try:
        resp = _urlopen(req)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise R2RequestError(
            f"R2 HEAD failed: HTTP {e.code} for key={key!r}",
            status=e.code,
            key=key,
        ) from e

    with resp as r:
        status = getattr(r, "status", None) or r.getcode()
        def _h(name: str) -> Optional[str]:
            if hasattr(r, "getheader"):
                return r.getheader(name)
            if hasattr(r, "headers"):
                return r.headers.get(name)
            return None
        content_length = _h("Content-Length")
        return {
            "etag": _h("ETag"),
            "content_length": int(content_length) if content_length is not None else None,
            "content_type": _h("Content-Type"),
            "cache_control": _h("Cache-Control"),
            "status": status,
        }


def range_get(key: str, byte_range: Tuple[int, int]) -> dict[str, Any]:
    """Range-GET an R2 object. Returns {status, content, content_range, content_length}.

    Caller MUST verify status == 206 (Partial Content); a 200 response means
    R2 ignored the Range header — likely a misconfiguration. r2_atomic_publish
    aborts on 200 per spec §4.4.
    """
    start, end = byte_range
    creds = _load_credentials()
    range_header = f"bytes={start}-{end}"
    headers = _sign_request(
        method="GET",
        bucket=creds[R2_BUCKET_NAME_ENV],
        key=key,
        host=_endpoint_host(creds[R2_ACCOUNT_ID_ENV]),
        payload_sha256=_EMPTY_PAYLOAD_SHA256,
        extra_headers={"range": range_header},
        access_key=creds[R2_ACCESS_KEY_ID_ENV],
        secret_key=creds[R2_SECRET_ACCESS_KEY_ENV],
    )
    url = _endpoint_url(creds[R2_ACCOUNT_ID_ENV], creds[R2_BUCKET_NAME_ENV], key)
    req = urllib.request.Request(url=url, method="GET")
    for name, value in headers.items():
        req.add_header(name, value)

    try:
        resp = _urlopen(req)
    except urllib.error.HTTPError as e:
        raise R2RequestError(
            f"R2 GET (range) failed: HTTP {e.code} for key={key!r}",
            status=e.code,
            key=key,
            body=e.read() if hasattr(e, "read") else b"",
        ) from e

    with resp as r:
        status = getattr(r, "status", None) or r.getcode()
        content = r.read()
        def _h(name: str) -> Optional[str]:
            if hasattr(r, "getheader"):
                return r.getheader(name)
            if hasattr(r, "headers"):
                return r.headers.get(name)
            return None
        cr = _h("Content-Range")
        cl = _h("Content-Length")
        return {
            "status": status,
            "content": content,
            "content_range": cr,
            "content_length": int(cl) if cl is not None else len(content),
        }
