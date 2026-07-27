"""Media playback cache API handlers — PLAYBACK_CACHE_V1."""
from __future__ import annotations

import os
from pathlib import Path

from media_playback_cache import (
    find_cached_by_basename,
    lookup_playback_cache_file,
    token_from_playback_cache_name,
)
from lib.paths import DROPBOX_ROOT


def _playback_search_event_dirs(h, scoped_event: str) -> list[Path]:
    """Event dirs to search for warmed playback cache entries (milestone library + server scope)."""
    prod = Path(h.app.event_dir).parent
    dirs: list[Path] = []
    seen: set[str] = set()

    def _add(path: Path | None) -> None:
        if path is None:
            return
        # HOT_SERVE_TRUE_CACHE_FIRST_V2 — never Path.resolve()/is_dir() on
        # Dropbox Event roots here; File Provider can block and gray Beat Gen.
        key = os.path.abspath(str(path))
        if key in seen:
            return
        seen.add(key)
        dirs.append(Path(key))

    _add(getattr(h.app, "milestone_library_event_dir", None))
    _add(Path(h.app.event_dir))
    candidate = prod / scoped_event
    _add(candidate)
    return dirs


def handle_playback_resolve(h, body: dict) -> None:
    """POST /api/media/playback_resolve — warm cache + return playback_url."""
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return
    path = str(body.get("path") or body.get("video_path") or "").strip()
    if not path:
        return h._send_error_v59(
            400,
            error_code="PATH_REQUIRED",
            error_message="path required",
            retry_safe=False,
        )

    # HOT_SERVE_TRUE_CACHE_FIRST_V2 — basename APFS hit BEFORE Dropbox
    # Path.resolve()/isfile. Absolute CloudStorage paths hang inside resolve().
    leaf = Path(path).name
    host = h.headers.get("Host", "localhost:5111")
    server_base = f"http://{host}"
    for ed in _playback_search_event_dirs(h, Path(h.app.event_dir).name):
        hit = find_cached_by_basename(ed, leaf) if leaf else None
        if hit is None:
            continue
        token = token_from_playback_cache_name(hit.name)
        if not token:
            continue
        event_id = ed.name
        playback_url = f"{server_base}/api/media/playback/{event_id}/{token}"
        # Skip ffprobe on the warm path — 40 concurrent resolves on Beat Gen
        # load must stay near-instant. duration_s=0 → client keeps /files URL
        # (also APFS cache-first); non-zero would swap onto /api/media/playback.
        payload = {
            "ok": True,
            "code": "PLAYBACK_CACHE_V1",
            "playback_url": playback_url,
            "cache_token": token,
            "duration_s": 0.0,
            "raw_duration_s": 0.0,
            "from_cache": True,
            "cache_path": str(hit),
            "source_path": path,
        }
        return h._send_json(200, payload)

    # Cold miss: do NOT Path.resolve() Dropbox masters (hangs File Provider).
    # Soft abspath containment, then refuse until APFS is warmed elsewhere.
    abs_norm = os.path.abspath(os.path.expanduser(path))
    try:
        drop_prefix = os.path.abspath(str(DROPBOX_ROOT))
    except OSError:
        drop_prefix = str(DROPBOX_ROOT)
    under_drop = abs_norm == drop_prefix or abs_norm.startswith(drop_prefix + os.sep)
    if not under_drop and not Path(path).is_absolute():
        try:
            abs_path = h._stitch_resolve_path(path)
            abs_norm = abs_path
            under_drop = True
        except ValueError:
            under_drop = False
    if not under_drop:
        return h._send_error_v59(
            403,
            error_code="PATH_OUTSIDE_PROJECT_ROOT",
            error_message="path outside project root",
            retry_safe=False,
        )
    return h._send_error_v59(
        503,
        error_code="PLAYBACK_CACHE_FAILED",
        error_message=(
            "local playback cache miss — Dropbox cold probe skipped; retry after warm"
        ),
        retry_safe=True,
    )


def serve_playback_cache_file(h, event_id: str, token: str) -> None:
    """GET /api/media/playback/{event_id}/{token} — immutable cached MP4."""
    scoped_event = f"Event_{event_id}" if not str(event_id).startswith("Event_") else str(event_id)
    for ev_dir in _playback_search_event_dirs(h, scoped_event):
        cached = lookup_playback_cache_file(ev_dir, token)
        if cached is not None and cached.is_file():
            h._serve_mp4_with_range(cached, cache_immutable=True)
            return
    return h._send_error_v59(
        404,
        error_code="PLAYBACK_CACHE_MISS",
        error_message=f"playback cache miss: {token}",
        retry_safe=False,
    )
