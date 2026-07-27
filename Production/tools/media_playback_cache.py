"""Media Playback Cache (MPP) — local bytes for storyboard operator playback.

PLAYBACK_CACHE_V1: Beat Gen + Stitcher serve warmed copies under a local hot
workspace (.playback_cache), not live Dropbox File Provider range reads.
Cloud-backed Event dirs → ~/.mindfulnest/media/<Event_N>/.playback_cache
(see media_hot_root.py). Local/tmp event dirs stay in-tree for pytest.

HOT_SERVE_CACHE_FIRST_V1 — [CONFIRMED against Event_6 :5116 logs 2026-07-26
hot-serve materialize failed errno 11 while ~/.mindfulnest/media/Event_6/
.playback_cache already held phase_b_lipsync + beat deliveries]: when Dropbox
metadata/copy raises errno 11/35, serve any already-warmed local
``pb_*_<basename>`` rather than black players. Token identity still prefers
size+mtime when File Provider answers.

HOT_SERVE_TRUE_CACHE_FIRST_V2 — [CONFIRMED Event_6 2026-07-26]: File Provider
can *block* inside ``isfile``/``realpath`` without raising. Warm ``pb_*`` must
return **before** any Dropbox probe — not only after an errno. Otherwise hung
/files and /api/cr/thumb occupy HTTP worker + browser lanes and even warm
Beat Gen clips spin forever.
"""
from __future__ import annotations

import concurrent.futures
import hashlib
import os
import re
import time
from pathlib import Path

# Request-path cold miss: do not sit in Dropbox isfile/copy for tens of seconds
# while Beat Gen videos starve. Warm hits never reach this budget.
_SHORT_DROPBOX_PROBE_S = 2.0
_SHORT_DROPBOX_ATTEMPTS = 2

from lib.ffmpeg_io import (
    DROPBOX_IO_MAX_ATTEMPTS,
    DROPBOX_IO_TRANSIENT_ERRNOS,
    copy_file_durable,  # pre-existing in lib.ffmpeg_io (not added by this PR)
    dropbox_io_backoff_s,
    dropbox_io_transient,
    path_isfile_durable,
    path_stat_durable,
)
from media_hot_root import playback_cache_dir_for_event

PLAYBACK_CACHE_VERSION = "PLAYBACK_CACHE_V1"
# Keep enough masters+previews for a full Event intro refresh without
# Dropbox rematerialize storms (was 50; Event_6 alone warms 15–40 clips).
_LRU_KEEP = 120
_TOKEN_RE = re.compile(r"^[0-9a-f]{16}$")
_PB_CACHE_NAME_RE = re.compile(r"^pb_[0-9a-f]{16}_([A-Za-z0-9._-]{1,120})$")
_TRANSIENT_ERRNOS = DROPBOX_IO_TRANSIENT_ERRNOS
_MAX_ATTEMPTS = DROPBOX_IO_MAX_ATTEMPTS


def playback_cache_dir(event_dir: Path) -> Path:
    return playback_cache_dir_for_event(event_dir)


_EVENT_LEAF_RE = re.compile(r"^(Event|event)_[A-Za-z0-9._-]+$")


def _operator_media_roots() -> list[str]:
    """Trusted roots for confined Dropbox/hot media I/O (never derived from request path)."""
    from media_hot_root import media_hot_serve_roots

    roots: list[str] = []
    roots.extend(media_hot_serve_roots())
    try:
        roots.append(os.path.realpath(str(Path.home() / ".mindfulnest")))
    except OSError:
        roots.append(os.path.abspath(str(Path.home() / ".mindfulnest")))
    drop = os.environ.get("MN_DROPBOX_ROOT", "").strip() or os.path.expanduser(
        "~/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files"
    )
    try:
        roots.append(os.path.realpath(drop))
    except OSError:
        roots.append(os.path.abspath(drop))
    env_hot = os.environ.get("MN_MEDIA_HOT_ROOT", "").strip()
    if env_hot and env_hot != "0":
        try:
            hot_p = Path(env_hot).expanduser()
            roots.append(os.path.realpath(str(hot_p)))
            # Pytest fixtures place CloudStorage under the same tmp parent as the
            # hot root (MN_MEDIA_HOT_ROOT=<tmp>/hot → allow <tmp>).
            roots.append(os.path.realpath(str(hot_p.parent)))
        except OSError:
            pass
    # Pytest / operator overrides — colon-separated absolute roots.
    extra = os.environ.get("MN_MEDIA_PATH_ROOTS", "").strip()
    if extra:
        for part in extra.split(":"):
            part = part.strip()
            if not part:
                continue
            try:
                roots.append(os.path.realpath(part))
            except OSError:
                roots.append(os.path.abspath(part))
    # Dedup while preserving order
    out: list[str] = []
    seen: set[str] = set()
    for r in roots:
        if r and r not in seen:
            seen.add(r)
            out.append(r)
    return out


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


def _backoff_s(attempt: int) -> float:
    return dropbox_io_backoff_s(attempt)


def _safe_basename(source_path: Path | str) -> str:
    name = Path(source_path).name or "clip.mp4"
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    return safe[:120] or "clip.mp4"


def _norm_source_path(path: Path | str) -> str:
    """Absolute path without requiring a Dropbox File Provider realpath()."""
    return os.path.abspath(os.path.expanduser(str(path)))


def find_cached_by_basename(
    event_dir: Path | str,
    source_path: Path | str,
) -> Path | None:
    """Newest non-empty local cache entry matching the source basename.

    Used when Dropbox ``stat``/copy is unavailable (errno 11/35) so operators
    keep seeing already-warmed Phase B / Beat Gen / intro media.
    """
    safe = _safe_basename(source_path)
    if not safe or "/" in safe or "\\" in safe or safe in (".", ".."):
        return None
    cache = playback_cache_dir(Path(event_dir))
    try:
        # CODEQL_PATH_INJECTION_NATIVE_PATTERN — realpath cache root, then
        # assign joined path only inside startswith (never open unsanitized).
        cache_s = os.path.realpath(str(cache))
        names = os.listdir(cache_s)
    except OSError:
        return None
    hits: list[tuple[float, str]] = []
    for name in names:
        # Strict pb_* regex — do not join request-derived suffix strings.
        m = _PB_CACHE_NAME_RE.fullmatch(name)
        if not m or m.group(1) != safe:
            continue
        cand = os.path.realpath(os.path.join(cache_s, name))
        safe_full = ""
        if cand == cache_s or cand.startswith(cache_s + os.sep):
            safe_full = cand
        if not safe_full:
            continue
        try:
            # codeql[py/path-injection]: safe_full assigned only inside
            # realpath+startswith of cache_s (CODEQL_PATH_INJECTION_NATIVE_PATTERN).
            st = os.stat(safe_full)
        except OSError:
            continue
        # codeql[py/path-injection]: same confined safe_full as above.
        if not os.path.isfile(safe_full) or st.st_size <= 0:
            continue
        hits.append((st.st_mtime, safe_full))
    if not hits:
        return None
    hits.sort(reverse=True)
    return Path(hits[0][1])


def ensure_hot_serve_file(
    path: Path | str,
    *,
    event_dir: Path | str | None = None,
    dropbox_probe: str = "when_needed",
) -> Path:
    """Return a path safe for range-serve (never Dropbox File Provider bytes).

    Cloud-backed masters stay on Dropbox as durable cold store. Operator GET
    /files and playback serve materialize once into ~/.mindfulnest/media
    .playback_cache (APFS), then stream from there.

    HOT_SERVE_TRUE_CACHE_FIRST_V2 — warm ``pb_*_<basename>`` returns
    immediately with **zero** Dropbox ``isfile``/``stat``/copy. File Provider
    can block forever without raising; probing first reintroduced Beat Gen spin.

    ``dropbox_probe`` (cold miss only):
    - ``when_needed`` — full durable retries (background warm / explicit copy)
    - ``short`` — ~2s budget for request-path ``/files`` and thumbs
    - ``never`` — raise OSError(11) if no local cache (fail-fast thumbs)
    """
    from lib.ffmpeg_io import path_is_cloud_storage_backed
    from media_hot_root import default_media_hot_root

    if dropbox_probe not in ("when_needed", "short", "never"):
        raise ValueError(f"invalid dropbox_probe: {dropbox_probe!r}")

    src_s = _norm_source_path(path)
    src_resolved = Path(src_s)
    if not path_is_cloud_storage_backed(src_resolved):
        return src_resolved
    # Already under local hot root (absolute /files to ui_preview, etc.)
    try:
        hot = os.path.realpath(str(default_media_hot_root().expanduser()))
        # CODEQL_PATH_INJECTION_NATIVE_PATTERN
        safe_hot = ""
        if src_s == hot or src_s.startswith(hot + os.sep):
            safe_hot = src_s
        if safe_hot:
            return Path(safe_hot)
    except OSError:
        pass

    ed = (
        Path(event_dir)
        if event_dir is not None
        else event_dir_from_media_path(src_resolved)
    )

    # TRUE cache-first: never touch Dropbox when APFS already has bytes.
    cached_hit = find_cached_by_basename(ed, src_resolved)
    if cached_hit is not None:
        return cached_hit

    if dropbox_probe == "never":
        raise OSError(
            11,
            f"no local hot-serve cache; Dropbox probe skipped: {src_s}",
        )

    if dropbox_probe == "short":
        return _ensure_hot_serve_dropbox_short(ed, src_s)

    return _ensure_hot_serve_dropbox_full(ed, src_s)


def _ensure_hot_serve_dropbox_full(ed: Path, src_s: str) -> Path:
    """Cold miss: durable Dropbox isfile + materialize (may block)."""
    roots = _operator_media_roots()
    try:
        exists = path_isfile_durable(src_s, roots=roots)
    except (OSError, PermissionError) as exc:
        raise OSError(
            getattr(exc, "errno", 11) or 11,
            f"Dropbox metadata unavailable for hot-serve: {src_s}: {exc}",
        ) from exc
    if not exists:
        return Path(src_s)

    last_err: OSError | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            return materialize_playback_cache(ed, Path(src_s))
        except OSError as exc:
            last_err = exc
            if exc.errno not in _TRANSIENT_ERRNOS or attempt >= _MAX_ATTEMPTS - 1:
                break
            time.sleep(_backoff_s(attempt))
    if last_err:
        raise last_err
    raise RuntimeError(f"hot-serve materialize failed: {src_s}")


def _ensure_hot_serve_dropbox_short(ed: Path, src_s: str) -> Path:
    """Cold miss on request path: bounded Dropbox budget, then errno 11.

    File Provider can block inside ``isfile`` without raising. Cap wall time so
    hung thumbs/library GETs cannot occupy HTTP workers forever.
    """
    roots = _operator_media_roots()

    def _probe() -> Path:
        # One-shot isfile (no durable 12-retry loop) — timeout thread owns budget.
        try:
            from lib.ffmpeg_io import confined_path_under_roots

            path_s = confined_path_under_roots(src_s, roots)
            if not os.path.isfile(path_s):
                return Path(src_s)
        except (OSError, PermissionError, ValueError) as exc:
            raise OSError(
                getattr(exc, "errno", 11) or 11,
                f"Dropbox metadata unavailable for hot-serve: {src_s}: {exc}",
            ) from exc
        last_err: OSError | None = None
        for attempt in range(_SHORT_DROPBOX_ATTEMPTS):
            try:
                return materialize_playback_cache(ed, Path(src_s))
            except OSError as exc:
                last_err = exc
                if (
                    exc.errno not in _TRANSIENT_ERRNOS
                    or attempt >= _SHORT_DROPBOX_ATTEMPTS - 1
                ):
                    break
                time.sleep(min(_backoff_s(attempt), 0.25))
        if last_err:
            raise last_err
        raise RuntimeError(f"hot-serve materialize failed: {src_s}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(_probe)
        try:
            return fut.result(timeout=_SHORT_DROPBOX_PROBE_S)
        except concurrent.futures.TimeoutError as exc:
            raise OSError(
                11,
                f"Dropbox hot-serve probe timed out after {_SHORT_DROPBOX_PROBE_S}s: {src_s}",
            ) from exc


def playback_cache_token(source_path: Path) -> str:
    from lib.ffmpeg_io import path_is_cloud_storage_backed

    src_s = _norm_source_path(source_path)
    if path_is_cloud_storage_backed(src_s):
        stat = path_stat_durable(src_s, roots=_operator_media_roots())
    else:
        stat = os.stat(src_s)
    digest = hashlib.sha256(
        f"{src_s}:{stat.st_mtime_ns}:{stat.st_size}".encode("utf-8"),
        usedforsecurity=False,
    )
    return digest.hexdigest()[:16]


def token_from_playback_cache_name(name: str) -> str | None:
    """Extract the 16-hex token from a ``pb_<token>_<basename>`` cache leaf."""
    m = re.match(r"^pb_([0-9a-f]{16})_", str(name or ""))
    return m.group(1) if m else None


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
        if "/" in name or "\\" in name or name in (".", ".."):
            continue
        cand = os.path.realpath(os.path.join(cache_s, name))
        # CODEQL_PATH_INJECTION_NATIVE_PATTERN
        safe_full = ""
        if cand == cache_s or cand.startswith(cache_s + os.sep):
            safe_full = cand
        if not safe_full:
            continue
        # Incomplete durable copies left behind under File Provider pressure.
        if name.startswith(".mn_copy_"):
            try:
                # codeql[py/path-injection]: safe_full confined to cache_s above.
                os.unlink(safe_full)
            except OSError:
                pass
            continue
        if not name.startswith("pb_"):
            continue
        # codeql[py/path-injection]: safe_full confined to cache_s above.
        if os.path.isfile(safe_full):
            files.append(safe_full)
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    for stale in files[keep:]:
        try:
            # codeql[py/path-injection]: stale came from confined safe_full list.
            os.unlink(stale)
        except OSError:
            pass


def materialize_playback_cache(event_dir: Path, source_path: Path) -> Path:
    from lib.ffmpeg_io import path_is_cloud_storage_backed

    src_s = _norm_source_path(source_path)
    # HOT_SERVE_TRUE_CACHE_FIRST_V2 — warm pb_* before any Dropbox isfile/stat.
    # Beat Gen fires dozens of playback_resolve calls on load; probing Dropbox
    # first hung HTTP workers and left option <video> tiles gray (readyState 0).
    cached_hit = find_cached_by_basename(event_dir, source_path)
    if cached_hit is not None:
        return cached_hit

    cloud = path_is_cloud_storage_backed(src_s)
    roots = _operator_media_roots() if cloud else []
    try:
        if cloud:
            present = path_isfile_durable(src_s, roots=roots)
        else:
            # Local/tmp masters — not Dropbox File Provider.
            # codeql[py/path-injection]: non-cloud path; operator workspace only.
            present = os.path.isfile(src_s)
    except (OSError, PermissionError):
        present = False
    if not present:
        raise FileNotFoundError(f"missing playback source: {src_s}")
    src = Path(src_s)

    # Exact token path when Dropbox metadata answers.
    try:
        dest = playback_cache_path(event_dir, src)
        if cloud:
            src_size = path_stat_durable(src_s, roots=roots).st_size
        else:
            # codeql[py/path-injection]: non-cloud path; operator workspace only.
            src_size = os.stat(src_s).st_size
        if dest.is_file():
            try:
                if dest.stat().st_size == src_size:
                    return dest
            except OSError:
                pass
        copy_file_durable(src, dest)
        playback_cache_lru_cleanup(event_dir)
        return dest
    except OSError as exc:
        if not dropbox_io_transient(exc):
            raise
        raise


def resolve_playback_url(
    source_path: str | Path,
    *,
    event_dir: Path,
    event_id: str,
    server_base: str = "",
) -> dict:
    """Return playback_url + metadata for a canonical on-disk media file."""
    src = Path(_norm_source_path(source_path))
    # Always materialize into pb_* cache — /api/media/playback/{token} looks up
    # by token there. ensure_hot_serve alone leaves local paths uncached.
    # materialize is cache-first (HOT_SERVE_TRUE_CACHE_FIRST_V2).
    try:
        cached = materialize_playback_cache(event_dir, src)
    except OSError:
        cached = ensure_hot_serve_file(src, event_dir=event_dir, dropbox_probe="never")
    # PLAYBACK_TOKEN_MATCHES_CACHE_FILE_V1 — GET /api/media/playback/{token}
    # looks up pb_{token}_*. The URL token MUST be the token embedded in the
    # materialized leaf. Recomputing playback_cache_token(src) after a basename
    # cache hit (mtime drift / Dropbox flake) produced Event_6 intro_tail 404s:
    # resolve returned e277… while disk had pb_18f93…. UI swapped off working
    # /files onto that 404 → black spinner forever.
    token = token_from_playback_cache_name(cached.name)
    if not token:
        try:
            token = playback_cache_token(src)
        except OSError:
            token = hashlib.sha256(
                str(src).encode("utf-8"), usedforsecurity=False,
            ).hexdigest()[:16]
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
            timeout=8,
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
        if not name.startswith(prefix):
            continue
        # HOT_SERVE_ALL_FILES_V1 — mp4 + mp3 + images
        path = cache / name
        if path.is_file() and path.stat().st_size > 0:
            return path
    return None


def event_id_from_dir(event_dir: Path) -> str:
    name = Path(event_dir).name
    if name.startswith("Event_"):
        return name
    return name or "Event_1"
