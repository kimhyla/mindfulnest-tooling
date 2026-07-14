"""Media Playback Cache (MPP) — local bytes for storyboard operator playback.

PLAYBACK_CACHE_V1: Beat Gen + Stitcher serve warmed copies under a local hot
workspace (.playback_cache), not live Dropbox File Provider range reads.
Cloud-backed Event dirs → ~/.mindfulnest/media/<Event_N>/.playback_cache
(see media_hot_root.py). Local/tmp event dirs stay in-tree for pytest.
"""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

import beat_generator as bg
from media_hot_root import playback_cache_dir_for_event

PLAYBACK_CACHE_VERSION = "PLAYBACK_CACHE_V1"
# Keep enough masters+previews for a full Event intro refresh without
# Dropbox rematerialize storms (was 50; Event_6 alone warms 15–40 clips).
_LRU_KEEP = 120
_TOKEN_RE = re.compile(r"^[0-9a-f]{16}$")


def playback_cache_dir(event_dir: Path) -> Path:
    return playback_cache_dir_for_event(event_dir)


def event_dir_from_media_path(
    path: Path | str,
    *,
    fallback: Path | str | None = None,
) -> Path:
    """Nearest Event_N ancestor for a media path, else fallback."""
    p = Path(path)
    try:
        p = p.resolve()
    except OSError:
        p = Path(path)
    for parent in (p.parent, *p.parents):
        name = parent.name
        if name.startswith("Event_") or name.startswith("event_"):
            return parent
    if fallback is not None:
        return Path(fallback)
    raise ValueError(f"cannot resolve Event dir for media path: {path}")


def ensure_hot_serve_file(
    path: Path | str,
    *,
    event_dir: Path | str | None = None,
) -> Path:
    """Return a path safe for range-serve (never Dropbox File Provider bytes).

    Cloud-backed masters stay on Dropbox as durable cold store. Operator GET
    /files and playback serve materialize once into ~/.mindfulnest/media
    .playback_cache (APFS), then stream from there.
    """
    from lib.ffmpeg_io import path_is_cloud_storage_backed
    from media_hot_root import default_media_hot_root

    src = Path(path)
    try:
        src_resolved = src.resolve()
    except OSError:
        src_resolved = src
    if not path_is_cloud_storage_backed(src_resolved):
        return src_resolved
    # Already under local hot root (absolute /files to ui_preview, etc.)
    try:
        hot = default_media_hot_root().expanduser().resolve()
        if src_resolved.is_relative_to(hot):
            return src_resolved
    except (OSError, ValueError):
        pass
    if not src_resolved.is_file():
        return src_resolved
    ed = (
        Path(event_dir)
        if event_dir is not None
        else event_dir_from_media_path(src_resolved)
    )
    return materialize_playback_cache(ed, src_resolved)


def playback_cache_token(source_path: Path) -> str:
    src = source_path.resolve()
    stat = src.stat()
    digest = hashlib.sha256(
        f"{src}:{stat.st_mtime_ns}:{stat.st_size}".encode("utf-8"),
        usedforsecurity=False,
    )
    return digest.hexdigest()[:16]


def _safe_basename(source_path: Path) -> str:
    name = source_path.name or "clip.mp4"
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    return safe[:120] or "clip.mp4"


def playback_cache_path(event_dir: Path, source_path: Path) -> Path:
    token = playback_cache_token(source_path)
    return playback_cache_dir(event_dir) / f"pb_{token}_{_safe_basename(source_path)}"


def playback_cache_lru_cleanup(event_dir: Path, *, keep: int = _LRU_KEEP) -> None:
    cache = playback_cache_dir(event_dir)
    files = sorted(
        (p for p in cache.glob("pb_*.mp4") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for stale in files[keep:]:
        try:
            stale.unlink()
        except OSError:
            pass


def materialize_playback_cache(event_dir: Path, source_path: Path) -> Path:
    src = Path(source_path).resolve()
    if not src.is_file():
        raise FileNotFoundError(f"missing playback source: {src}")
    dest = playback_cache_path(event_dir, src)
    if dest.is_file():
        try:
            if dest.stat().st_size == src.stat().st_size:
                return dest
        except OSError:
            pass
    bg.copy_file_durable(src, dest)
    playback_cache_lru_cleanup(event_dir)
    return dest


def resolve_playback_url(
    source_path: str | Path,
    *,
    event_dir: Path,
    event_id: str,
    server_base: str = "",
) -> dict:
    """Return playback_url + metadata for a canonical on-disk media file."""
    src = Path(source_path).resolve()
    if not src.is_file():
        raise FileNotFoundError(f"missing playback source: {src}")
    cached = materialize_playback_cache(event_dir, src)
    token = playback_cache_token(src)
    base = (server_base or "").rstrip("/")
    playback_url = f"{base}/api/media/playback/{event_id}/{token}"
    try:
        import subprocess

        out = subprocess.check_output(
            [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(cached),
            ],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=30,
        ).strip()
        duration_s = float(out) if out else 0.0
    except (subprocess.SubprocessError, ValueError, OSError):
        duration_s = 0.0
    return {
        "playback_url": playback_url,
        "cache_token": token,
        "duration_s": duration_s,
        "from_cache": cached.is_file(),
        "cache_path": str(cached),
        "source_path": str(src),
    }


def lookup_playback_cache_file(event_dir: Path, token: str) -> Path | None:
    if not _TOKEN_RE.match(str(token or "")):
        return None
    cache = playback_cache_dir(event_dir)
    matches = sorted(cache.glob(f"pb_{token}_*.mp4"))
    for path in matches:
        if path.is_file():
            return path
    return None


def event_id_from_dir(event_dir: Path) -> str:
    name = Path(event_dir).name
    if name.startswith("Event_"):
        return name
    return name or "Event_1"
