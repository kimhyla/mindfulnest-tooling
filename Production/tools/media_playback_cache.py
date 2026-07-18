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
import time
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


_EVENT_LEAF_RE = re.compile(r"^(Event|event)_[A-Za-z0-9._-]+$")


def event_dir_from_media_path(
    path: Path | str,
    *,
    fallback: Path | str | None = None,
) -> Path:
    """Nearest Event_N ancestor for a media path, else fallback."""
    # Walk parents without Path.resolve() — CodeQL treats resolve of user
    # paths as path-injection sinks; Event_* leaf regex is the gate.
    p = Path(path)
    for parent in (p.parent, *p.parents):
        name = parent.name
        if _EVENT_LEAF_RE.fullmatch(name):
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

    src_s = os.path.realpath(os.path.expanduser(str(path)))
    src_resolved = Path(src_s)
    if not path_is_cloud_storage_backed(src_resolved):
        return src_resolved
    # Already under local hot root (absolute /files to ui_preview, etc.)
    try:
        hot = os.path.realpath(str(default_media_hot_root().expanduser()))
        if src_s == hot or src_s.startswith(hot + os.sep):
            return Path(src_s)
    except OSError:
        pass
    # Existence probe only after string is bound; copy uses materialize below.
    if not os.path.isfile(src_s):
        return src_resolved
    ed = (
        Path(event_dir)
        if event_dir is not None
        else event_dir_from_media_path(src_resolved)
    )
    # File Provider often returns EDEADLK on concurrent master reads — retry
    # before giving up so /files never falls back to streaming Dropbox bytes.
    last_err: OSError | None = None
    for attempt in range(12):
        try:
            return materialize_playback_cache(ed, Path(src_s))
        except OSError as exc:
            last_err = exc
            if exc.errno not in (11, 35) or attempt >= 11:
                raise
            time.sleep(min(4.0, 0.15 * (2 ** attempt)))
    if last_err:
        raise last_err
    raise RuntimeError(f"hot-serve materialize failed: {src_s}")


def playback_cache_token(source_path: Path) -> str:
    src_s = os.path.realpath(str(source_path))
    stat = os.stat(src_s)
    digest = hashlib.sha256(
        f"{src_s}:{stat.st_mtime_ns}:{stat.st_size}".encode("utf-8"),
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
    # HOT_SERVE_ALL_FILES_V1 — cache holds mp4 + audio stems + images (pb_*).
    # Basename-only entries from listdir; reject traversal names.
    try:
        cache_s = os.path.realpath(str(cache))
        names = os.listdir(cache_s)
    except OSError:
        return
    files: list[str] = []
    for name in names:
        if not name.startswith("pb_") or "/" in name or "\\" in name or name in (".", ".."):
            continue
        full = os.path.join(cache_s, name)
        if os.path.isfile(full):
            files.append(full)
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    for stale in files[keep:]:
        try:
            os.unlink(stale)
        except OSError:
            pass


def materialize_playback_cache(event_dir: Path, source_path: Path) -> Path:
    src_s = os.path.realpath(str(source_path))
    if not os.path.isfile(src_s):
        raise FileNotFoundError(f"missing playback source: {src_s}")
    src = Path(src_s)
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
    src = Path(os.path.realpath(str(source_path)))
    if not os.path.isfile(str(src)):
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
    prefix = f"pb_{token}_"
    try:
        names = sorted(os.listdir(str(cache)))
    except OSError:
        return None
    for name in names:
        if not name.startswith(prefix) or not name.endswith(".mp4"):
            continue
        path = cache / name
        if path.is_file():
            return path
    return None


def event_id_from_dir(event_dir: Path) -> str:
    name = Path(event_dir).name
    if name.startswith("Event_"):
        return name
    return name or "Event_1"
