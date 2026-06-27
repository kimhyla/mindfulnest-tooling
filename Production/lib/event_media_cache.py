"""Local mirror cache for Dropbox-backed media — ffmpeg reads from cache, not FUSE."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from lib.ffmpeg_io import copy_file_durable, path_is_cloud_storage_backed

_CACHE_ROOT = Path.home() / ".cache" / "mindfulnest" / "events"


def cache_root_for_event(event_id: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(event_id or "unknown"))
    root = _CACHE_ROOT / safe
    root.mkdir(parents=True, exist_ok=True)
    return root


def _cache_key(source: Path) -> str:
    digest = hashlib.sha1(str(source.resolve()).encode("utf-8")).hexdigest()[:16]
    return f"{digest}{source.suffix or '.bin'}"


def _needs_refresh(source: Path, cached: Path) -> bool:
    if not cached.is_file():
        return True
    try:
        src_stat = source.stat()
        dst_stat = cached.stat()
    except OSError:
        return True
    return src_stat.st_mtime > dst_stat.st_mtime + 0.001 or src_stat.st_size != dst_stat.st_size


def ensure_local_media(path: str | Path, *, event_id: str) -> Path:
    """Return local path suitable for ffmpeg -i (mirror cloud sources into ~/.cache)."""
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"missing media: {source}")
    if not path_is_cloud_storage_backed(source):
        return source.resolve()
    cached = cache_root_for_event(event_id) / _cache_key(source)
    if _needs_refresh(source, cached):
        copy_file_durable(source, cached)
    return cached.resolve()


def invalidate_local_media(path: str | Path, *, event_id: str) -> None:
    source = Path(path)
    if not path_is_cloud_storage_backed(source):
        return
    cached = cache_root_for_event(event_id) / _cache_key(source)
    if cached.is_file():
        os.unlink(cached)
