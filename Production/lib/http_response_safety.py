"""HTTP response header safety (CodeQL py/http-response-splitting).

Rebuild header values from validated components — no raw user bytes in
send_header sinks. Used by production_server.py file-serve paths.
"""
from __future__ import annotations

import re

_SAFE_HEADER_RE = re.compile(r"[\r\n\x00]")
_SAFE_ETAG_RE = re.compile(r"[^a-zA-Z0-9._-]+")

_CONTENT_TYPE_ALLOWLIST = frozenset({
    "video/mp4",
    "video/quicktime",
    "audio/mpeg",
    "audio/mp4",
    "audio/wav",
    "audio/x-wav",
    "audio/ogg",
    "audio/webm",
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/gif",
    "application/octet-stream",
    "text/plain; charset=utf-8",
    "text/html; charset=utf-8",
})


def safe_http_header_value(raw: str, *, max_len: int = 512) -> str:
    """Strip CR/LF/NUL — prevents response-splitting via header injection."""
    if not isinstance(raw, str):
        return ""
    cleaned = _SAFE_HEADER_RE.sub("", raw).strip()
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len]
    return cleaned


def safe_content_type(mime: str | None, *, fallback: str = "application/octet-stream") -> str:
    """Allowlist Content-Type before send_header."""
    fb = fallback if fallback in _CONTENT_TYPE_ALLOWLIST else "application/octet-stream"
    if not mime:
        return fb
    base = mime.split(";", 1)[0].strip().lower()
    if base in _CONTENT_TYPE_ALLOWLIST:
        return mime if ";" in mime else base
    return fb


def safe_etag_from_basename(name: str) -> str:
    """ETag from filename stem only — alphanumeric + . _ -"""
    stem = name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    safe = _SAFE_ETAG_RE.sub("_", stem)[:128] or "asset"
    return f'"{safe}"'
