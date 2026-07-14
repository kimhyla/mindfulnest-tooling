"""Local APFS hot workspace for Storyboard media I/O (off Dropbox File Provider).

Cloud-backed Event_* dirs keep durable masters on Dropbox, but hot operator paths
(.playback_cache, trim/cut scratch) redirect to ~/.mindfulnest/media/<Event_N>
(or MN_MEDIA_HOT_ROOT) so concurrent reads/writes do not hit File Provider EDEADLK.
"""
from __future__ import annotations

import os
from pathlib import Path

_DEFAULT_HOT_ROOT = Path.home() / ".mindfulnest" / "media"


def default_media_hot_root() -> Path:
    env = os.environ.get("MN_MEDIA_HOT_ROOT", "").strip()
    if env and env != "0":
        return Path(env).expanduser()
    return _DEFAULT_HOT_ROOT


def event_dir_is_cloud_backed(event_dir: str | Path) -> bool:
    """True when event_dir lives under Dropbox / macOS CloudStorage File Provider."""
    try:
        text = str(Path(event_dir).expanduser().resolve())
    except OSError:
        text = str(Path(event_dir).expanduser())
    markers = (
        "/CloudStorage/",
        "/Library/CloudStorage/",
        "/Dropbox/",
    )
    if any(m in text for m in markers):
        return True
    return text.rstrip("/").endswith("/Dropbox")


def resolve_media_workspace(event_dir: str | Path) -> Path:
    """Directory that owns .playback_cache and trim scratch for an event.

    - MN_MEDIA_HOT_ROOT=0 → always use event_dir (opt out)
    - MN_MEDIA_HOT_ROOT=/path → always use /path/<Event_N>
    - unset → redirect only when event_dir is cloud-backed; pytest tmp stays local
    """
    ed = Path(event_dir)
    env = os.environ.get("MN_MEDIA_HOT_ROOT", "").strip()
    if env == "0":
        return ed
    if env:
        ws = Path(env).expanduser() / ed.name
        ws.mkdir(parents=True, exist_ok=True)
        return ws
    if not event_dir_is_cloud_backed(ed):
        return ed
    ws = _DEFAULT_HOT_ROOT / ed.name
    ws.mkdir(parents=True, exist_ok=True)
    return ws


def playback_cache_dir_for_event(event_dir: str | Path) -> Path:
    d = resolve_media_workspace(event_dir) / ".playback_cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def kling_o3_trim_scratch_dir(event_dir: str | Path) -> Path:
    d = resolve_media_workspace(event_dir) / "assembled" / "_kling_o3_trim_scratch"
    d.mkdir(parents=True, exist_ok=True)
    return d


def media_hot_serve_roots() -> list[str]:
    """Realpath roots allowed for /files of hot media outside Dropbox."""
    import os as _os

    roots: list[str] = []
    seen: set[str] = set()
    for cand in (default_media_hot_root(), _DEFAULT_HOT_ROOT):
        try:
            cand.mkdir(parents=True, exist_ok=True)
            real = _os.path.realpath(str(cand))
        except OSError:
            continue
        if real in seen:
            continue
        seen.add(real)
        roots.append(real)
    return roots
