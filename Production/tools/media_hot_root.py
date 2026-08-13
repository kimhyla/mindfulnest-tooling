"""Local APFS hot workspace for Storyboard media I/O (off Dropbox File Provider).

Cloud-backed Event_* dirs keep durable masters on Dropbox, but hot operator paths
(.playback_cache, trim/cut scratch) redirect to ~/.mindfulnest/media/<Event_N>
(or MN_MEDIA_HOT_ROOT). MP4/MOV /files serves also materialize through the
playback cache (see media_playback_cache.ensure_hot_serve_file) so browser
range reads never hit File Provider EDEADLK.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

_DEFAULT_HOT_ROOT = Path.home() / ".mindfulnest" / "media"
# Leaf names allowed under the hot root (CodeQL py/path-injection).
_EVENT_LEAF_RE = re.compile(r"^(Event|event)_[A-Za-z0-9._-]+$")


def default_media_hot_root() -> Path:
    env = os.environ.get("MN_MEDIA_HOT_ROOT", "").strip()
    if env and env != "0":
        return Path(env).expanduser()
    return _DEFAULT_HOT_ROOT


def _safe_event_leaf_name(event_dir: str | Path) -> str | None:
    """Return Event_N leaf when safe; None when name must not join under hot root."""
    name = Path(event_dir).name
    if _EVENT_LEAF_RE.fullmatch(name):
        return name
    return None


def event_dir_is_cloud_backed(event_dir: str | Path) -> bool:
    """True when event_dir lives under Dropbox / macOS CloudStorage File Provider."""
    # normpath (not Path.resolve) — CodeQL treats resolve() of user paths as sinks.
    text = os.path.normpath(os.path.expanduser(str(event_dir))).replace("\\", "/")
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
    leaf = _safe_event_leaf_name(ed)
    if env:
        if not leaf:
            raise ValueError(f"invalid event workspace name for hot root: {ed.name!r}")
        hot_root = os.path.realpath(os.path.expanduser(env))
        # Inline startswith (CodeQL native sanitizer) — no helper call.
        ws_cand = os.path.realpath(os.path.join(hot_root, leaf))
        safe_ws = ""
        if ws_cand == hot_root or ws_cand.startswith(hot_root + os.sep):
            safe_ws = ws_cand
        if not safe_ws:
            raise ValueError(f"hot workspace escaped root: {ws_cand!r}")
        os.makedirs(safe_ws, exist_ok=True)
        return Path(safe_ws)
    if not event_dir_is_cloud_backed(ed):
        return ed
    if not leaf:
        # Non-Event_* cloud path — stay in-tree rather than invent a hot leaf.
        return ed
    hot_root = os.path.realpath(str(_DEFAULT_HOT_ROOT.expanduser()))
    ws_cand = os.path.realpath(os.path.join(hot_root, leaf))
    safe_ws = ""
    if ws_cand == hot_root or ws_cand.startswith(hot_root + os.sep):
        safe_ws = ws_cand
    if not safe_ws:
        raise ValueError(f"hot workspace escaped root: {ws_cand!r}")
    os.makedirs(safe_ws, exist_ok=True)
    return Path(safe_ws)


def playback_cache_dir_for_event(event_dir: str | Path) -> Path:
    d = resolve_media_workspace(event_dir) / ".playback_cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def kling_o3_trim_scratch_dir(event_dir: str | Path) -> Path:
    d = resolve_media_workspace(event_dir) / "assembled" / "_kling_o3_trim_scratch"
    d.mkdir(parents=True, exist_ok=True)
    return d


def still_tts_hot_dir(
    event_dir: str | Path,
    storyboard_stem: str = "",
    *,
    create: bool = True,
) -> Path:
    """APFS (or in-tree) TTS dir — never mkdir Dropbox on the still+TTS request path."""
    d = resolve_media_workspace(event_dir) / "story_scene_tts_v2"
    stem = Path(str(storyboard_stem or "").strip()).name
    if stem and stem not in (".", ".."):
        d = d / stem
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def media_hot_serve_roots() -> list[str]:
    """Realpath roots allowed for /files of hot media outside Dropbox."""
    roots: list[str] = []
    seen: set[str] = set()
    for cand in (default_media_hot_root(), _DEFAULT_HOT_ROOT):
        try:
            p = Path(cand).expanduser()
            p.mkdir(parents=True, exist_ok=True)
            real = os.path.realpath(str(p))
        except OSError:
            continue
        if real in seen:
            continue
        seen.add(real)
        roots.append(real)
    return roots
