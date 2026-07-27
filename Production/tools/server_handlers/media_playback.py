"""Media playback cache API handlers — PLAYBACK_CACHE_V1."""
from __future__ import annotations

import re
from pathlib import Path

from media_playback_cache import (
    lookup_playback_cache_file,
    resolve_playback_url,
)
from o3_session_terminal_reconcile import playback_event_dir_for_source


def _playback_search_event_dirs(h, scoped_event: str) -> list[Path]:
    """Event dirs to search for warmed playback cache entries (milestone library + server scope)."""
    prod = Path(h.app.event_dir).parent
    dirs: list[Path] = []
    seen: set[str] = set()

    def _add(path: Path | None) -> None:
        if path is None:
            return
        p = Path(path).resolve()
        key = str(p)
        if not p.is_dir() or key in seen:
            return
        seen.add(key)
        dirs.append(p)

    _add(getattr(h.app, "milestone_library_event_dir", None))
    _add(Path(h.app.event_dir))
    candidate = prod / scoped_event
    _add(candidate if candidate.is_dir() else None)
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
    try:
        abs_path = h._stitch_resolve_path(path)
    except ValueError:
        return h._send_error_v59(
            403,
            error_code="PATH_OUTSIDE_PROJECT_ROOT",
            error_message="path outside project root",
            retry_safe=False,
        )
    from lib.ffmpeg_io import path_isfile_durable
    from media_playback_cache import _operator_media_roots, find_cached_by_basename

    src = Path(abs_path)
    roots = _operator_media_roots()

    def _src_available(candidate: Path) -> bool:
        # HOT_SERVE_TRUE_CACHE_FIRST_V2 — APFS warm hit before Dropbox isfile.
        # Dozens of Beat Gen tiles call playback_resolve on load; Dropbox-first
        # starved /files and left videos gray.
        try:
            ed = playback_event_dir_for_source(
                candidate,
                Path(h.app.event_dir),
                getattr(h.app, "milestone_library_event_dir", None),
            )
        except Exception:
            ed = Path(h.app.event_dir)
        if find_cached_by_basename(ed, candidate) is not None:
            return True
        try:
            if path_isfile_durable(candidate, roots=roots):
                return True
        except (OSError, PermissionError):
            pass
        return False

    if not _src_available(src):
        lib = getattr(h.app, "milestone_library_event_dir", None)
        if lib is not None and not Path(abs_path).is_absolute():
            alt = Path(lib) / path
            if _src_available(alt):
                abs_path = str(alt.resolve())
                src = alt.resolve()
        if not _src_available(src) and re.search(r"Event_\d+", path):
            try:
                abs_path = h._stitch_resolve_path(path)
                src = Path(abs_path)
            except ValueError:
                pass
    if not _src_available(src):
        return h._send_error_v59(
            404,
            error_code="FILE_NOT_FOUND",
            error_message=f"file not found: {path}",
            retry_safe=False,
        )
    playback_event_dir = playback_event_dir_for_source(
        src,
        Path(h.app.event_dir),
        getattr(h.app, "milestone_library_event_dir", None),
    )
    event_id = playback_event_dir.name
    host = h.headers.get("Host", "localhost:5111")
    server_base = f"http://{host}"
    try:
        result = resolve_playback_url(
            abs_path,
            event_dir=playback_event_dir,
            event_id=event_id,
            server_base=server_base,
        )
    except FileNotFoundError as exc:
        return h._send_error_v59(
            404,
            error_code="FILE_NOT_FOUND",
            error_message=str(exc),
            retry_safe=False,
        )
    except OSError as exc:
        return h._send_error_v59(
            503,
            error_code="PLAYBACK_CACHE_FAILED",
            error_message=str(exc),
            retry_safe=True,
        )
    payload = {
        "ok": True,
        "code": "PLAYBACK_CACHE_V1",
        **result,
    }
    duration_s = result.get("duration_s")
    if duration_s is not None:
        payload["raw_duration_s"] = duration_s
    return h._send_json(200, payload)


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
