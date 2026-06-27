"""Durable lipsync input hosting via production_server staging + optional R2 CDN.

WaveSpeed Kling LipSync requires publicly fetchable video/audio URLs. Ephemeral
hosts (filebin/catbox) fail on Kim's network; this module stages bytes under
``{event_dir}/_lipsync_staging/{token}/`` and serves them at
``GET /api/lipsync/staging/{token}/{filename}`` on the dedicated event server.

When ``MN_LIPSYNC_STAGING_PUBLIC_BASE`` points at a URL WaveSpeed can reach
(ngrok, deployed host, or R2 CDN fallback in lipsync_sender), URL transport
passes the >=720p quality gate reliably.
"""
from __future__ import annotations

import hashlib
import mimetypes
import os
import shutil
import urllib.parse
from pathlib import Path

STAGING_SUBDIR = "_lipsync_staging"


def staging_token_from_env() -> str:
    return (os.environ.get("MN_LIPSYNC_STAGING_TOKEN") or "").strip()


def staging_event_dir_from_env() -> Path | None:
    raw = (os.environ.get("MN_LIPSYNC_STAGING_EVENT_DIR") or "").strip()
    if not raw:
        return None
    return Path(raw)


def staging_public_base_from_env() -> str:
    return (os.environ.get("MN_LIPSYNC_STAGING_PUBLIC_BASE") or "").strip().rstrip("/")


def is_public_staging_base(public_base: str) -> bool:
    """Return True when WaveSpeed can fetch staged bytes from this base URL.

    Local dev servers (localhost / private LAN) pass local preflight but WaveSpeed
    rejects them as non-public hosts — skip staging and use R2/ephemeral hosts.
    """
    raw = (public_base or "").strip()
    if not raw:
        return False
    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme not in {"http", "https"}:
        return False
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    if host in {"localhost", "127.0.0.1", "::1", "0.0.0.0"}:
        return False
    if host.endswith(".local"):
        return False
    if host.startswith("127.") or host.startswith("10."):
        return False
    if host.startswith("192.168.") or host.startswith("169.254."):
        return False
    if host.startswith("172."):
        try:
            second = int(host.split(".")[1])
        except (IndexError, ValueError):
            return False
        if 16 <= second <= 31:
            return False
    return True


def staging_dir(event_dir: Path, token: str) -> Path:
    safe_token = _safe_segment(token)
    return Path(event_dir) / STAGING_SUBDIR / safe_token


def register_staging_file(event_dir: Path, token: str, file_path: Path) -> Path:
    """Copy file into event staging; return absolute staged path."""
    dest_dir = staging_dir(event_dir, token)
    dest_dir.mkdir(parents=True, exist_ok=True)
    safe_name = _safe_filename(file_path.name)
    dest = dest_dir / safe_name
    shutil.copy2(file_path, dest)
    return dest


def build_staging_public_url(public_base: str, token: str, filename: str) -> str:
    base = public_base.rstrip("/")
    token_seg = urllib.parse.quote(_safe_segment(token), safe="")
    name_seg = urllib.parse.quote(_safe_filename(filename), safe="")
    return f"{base}/api/lipsync/staging/{token_seg}/{name_seg}"


def resolve_staged_file(event_dir: Path, token: str, filename: str) -> Path | None:
    staged = staging_dir(event_dir, token) / _safe_filename(filename)
    if staged.is_file():
        return staged
    return None


def upload_via_production_staging(
    file_path: Path,
    *,
    event_dir: Path,
    token: str,
    public_base: str,
    preflight_fn,
) -> dict | None:
    """Stage locally, build public URL, preflight exact bytes."""
    staged = register_staging_file(event_dir, token, file_path)
    url = build_staging_public_url(public_base, token, staged.name)
    proof = preflight_fn(file_path, url, host="production_staging")
    if proof:
        proof["staging_path"] = str(staged)
        proof["token"] = token
    return proof


def r2_cdn_base_from_env() -> str:
    return (
        os.environ.get("MN_R2_CDN_BASE_URL")
        or os.environ.get("R2_CDN_BASE_URL")
        or "https://cdn.mindfulnest.app"
    ).strip().rstrip("/")


def r2_staging_key(token: str, filename: str) -> str:
    safe_token = _safe_segment(token)
    safe_name = _safe_filename(filename)
    return f"ops/lipsync-staging/{safe_token}/{safe_name}"


def r2_public_url(key: str) -> str:
    return f"{r2_cdn_base_from_env()}/{key.lstrip('/')}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def content_type_for(path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    return mime or "application/octet-stream"


def _safe_segment(value: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned or ".." in cleaned or "/" in cleaned or "\\" in cleaned:
        raise ValueError(f"invalid staging segment: {value!r}")
    return cleaned


def _safe_filename(name: str) -> str:
    base = Path(name or "").name
    if not base or base in {".", ".."} or ".." in base:
        raise ValueError(f"invalid staging filename: {name!r}")
    return base
