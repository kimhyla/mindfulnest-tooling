"""STITCH_SLOT_MEDIA_ARTIFACTS_V1 — fcntl lock + atomic cache writes for stitch_editor_cache."""
from __future__ import annotations

import os
import subprocess
import threading
import time
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path

from lib import fcntl_compat as fcntl

STITCH_CACHE_BUILD_WAIT_TIMEOUT_S = 600.0
STITCH_CACHE_BUILD_POLL_INTERVAL_S = 0.25
STITCH_CACHE_BUILD_LOCK_V1 = "STITCH_CACHE_BUILD_LOCK_V1"

# fcntl.flock on separately opened fds does not exclude concurrent threads in the
# same process on macOS — pair with a per-cache-dir threading.Lock (STITCH_CACHE_BUILD_LOCK_V1).
_thread_lock_guard = threading.Lock()
_thread_locks_by_cache: dict[str, threading.Lock] = {}


def _thread_lock_for(cache_dir: Path) -> threading.Lock:
    key = str(cache_dir.resolve())
    with _thread_lock_guard:
        lock = _thread_locks_by_cache.get(key)
        if lock is None:
            lock = threading.Lock()
            _thread_locks_by_cache[key] = lock
        return lock


class StitchCacheBuildBusy(Exception):
    """Another process holds the stitch cache build lock."""


@contextmanager
def stitch_cache_build_lock(cache_dir: Path):
    """Exclusive lock for stitch_editor_cache ffmpeg writes (in-process + cross-process)."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    lock_path = cache_dir / ".lock"
    with _thread_lock_for(cache_dir):
        fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
        try:
            try:
                fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (BlockingIOError, OSError) as exc:
                raise StitchCacheBuildBusy(
                    "stitch cache build in progress — retry shortly",
                ) from exc
            yield
        finally:
            try:
                fcntl.lockf(fd, fcntl.LOCK_UN)
            except OSError:
                pass
            try:
                os.close(fd)
            except OSError:
                pass


def run_stitch_cache_build(
    cache_dir: Path,
    *,
    ready: Callable[[], bool],
    build: Callable[[], None],
    wait_timeout_s: float = STITCH_CACHE_BUILD_WAIT_TIMEOUT_S,
) -> None:
    """Exactly one ffmpeg builder; waiters poll until cache is ready or lock opens.

    STITCH_CACHE_BUILD_LOCK_V1 — prevents concurrent cache-miss writes that share
    the same ``.tmp.{pid}`` path inside a single server process.
    """
    if ready():
        return
    deadline = time.monotonic() + wait_timeout_s
    while True:
        if ready():
            return
        try:
            with stitch_cache_build_lock(cache_dir):
                if ready():
                    return
                build()
                return
        except StitchCacheBuildBusy:
            if ready():
                return
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    f"stitch cache build wait timed out after {wait_timeout_s:.0f}s "
                    f"({STITCH_CACHE_BUILD_LOCK_V1})",
                ) from None
            time.sleep(STITCH_CACHE_BUILD_POLL_INTERVAL_S)


def sweep_stitch_cache_orphan_temps(
    cache_dir: Path,
    *,
    max_age_s: float = 3600.0,
) -> int:
    """Delete abandoned ``*.tmp.{pid}.mp4`` orphans (killed ffmpeg before os.replace)."""
    cache_dir = Path(cache_dir)
    if not cache_dir.is_dir():
        return 0
    removed = 0
    now = time.time()
    for candidate in cache_dir.glob("*.tmp.*.mp4"):
        try:
            if now - candidate.stat().st_mtime < max_age_s:
                continue
            candidate.unlink()
            removed += 1
        except OSError:
            continue
    return removed


def sweep_stitch_cache_unreferenced(
    cache_dir: Path,
    referenced_stems: set[str],
    *,
    max_age_s: float = 3600.0,
) -> int:
    """Delete cache files whose stem is not referenced by stitch job artifacts."""
    cache_dir = Path(cache_dir)
    if not cache_dir.is_dir():
        return 0
    removed = 0
    patterns = (
        "stitch_preview_*.mp4",
        "se_slot_*.mp4",
        "se_norm_*_pv.mp4",
        "stitch_audio_*.mp3",
        "stitch_peaks_*.json",
    )
    for pattern in patterns:
        for candidate in cache_dir.glob(pattern):
            stem = candidate.stem
            if stem.startswith("stitch_preview_"):
                stem = stem[len("stitch_preview_"):]
            elif stem.startswith("se_slot_"):
                stem = stem[len("se_slot_"):]
            elif stem.startswith("stitch_peaks_"):
                stem = stem[len("stitch_peaks_"):]
            elif stem.startswith("stitch_audio_"):
                stem = stem[len("stitch_audio_"):]
            elif stem.startswith("se_norm_"):
                if stem in referenced_stems:
                    continue
                try:
                    if time.time() - candidate.stat().st_mtime < max_age_s:
                        continue
                    candidate.unlink()
                    removed += 1
                except OSError:
                    pass
                continue
            if stem in referenced_stems:
                continue
            try:
                if time.time() - candidate.stat().st_mtime < max_age_s:
                    continue
                candidate.unlink()
                removed += 1
            except OSError:
                continue
    return removed


def atomic_ffmpeg_output(
    cmd: list[str],
    final_path: Path,
    *,
    expected_duration_s: float,
    validator: Callable[[Path, float], bool],
    timeout: int = 180,
) -> Path:
    """Run ffmpeg to a tmp file, validate duration, atomic rename to final_path."""
    from lib.ffmpeg_io import (
        commit_local_file_to_dest,
        local_staging_temp_path,
        path_is_cloud_storage_backed,
    )

    final_path = Path(final_path)
    if path_is_cloud_storage_backed(final_path):
        tmp_path = local_staging_temp_path(
            suffix=final_path.suffix or ".mp4",
            prefix="stitch_ff_",
        )
    else:
        tmp_path = final_path.parent / (
            f"{final_path.stem}.tmp.{os.getpid()}{final_path.suffix}"
        )
    tmp_cmd = list(cmd)
    for i, part in enumerate(tmp_cmd):
        if part == str(final_path.resolve()) or part == str(final_path):
            tmp_cmd[i] = str(tmp_path.resolve())
            break
    else:
        if "-y" in tmp_cmd:
            tmp_cmd = tmp_cmd[:-1] + [str(tmp_path.resolve())]
        else:
            raise ValueError("ffmpeg cmd must target final_path")

    try:
        if tmp_path.is_file():
            tmp_path.unlink()
    except OSError:
        pass

    subprocess.run(tmp_cmd, check=True, capture_output=True, timeout=timeout)

    if expected_duration_s > 0 and not validator(tmp_path, expected_duration_s):
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise RuntimeError(
            f"ffmpeg output truncated: expected ~{expected_duration_s:.1f}s",
        )

    if path_is_cloud_storage_backed(final_path):
        commit_local_file_to_dest(tmp_path, final_path)
    else:
        os.replace(tmp_path, final_path)
    return final_path
