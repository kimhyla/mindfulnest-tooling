"""Cloud-aware ffmpeg output staging — local encode, durable commit to Dropbox."""
from __future__ import annotations

import contextlib
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Callable, Sequence

# Dropbox/FUSE transient errno on macOS CloudStorage
# [CONFIRMED against Python 3.12 errno constants on Darwin]
# errno 11 = EDEADLK; errno 35 = EAGAIN.
_TRANSIENT_ERRNOS = frozenset({11, 35})
_MAX_ATTEMPTS = 12
# Public aliases for callers that must share the same retry policy.
DROPBOX_IO_TRANSIENT_ERRNOS = _TRANSIENT_ERRNOS
DROPBOX_IO_MAX_ATTEMPTS = _MAX_ATTEMPTS


def _backoff_s(attempt: int) -> float:
    return min(4.0, 0.15 * (2 ** attempt))


def dropbox_io_backoff_s(attempt: int) -> float:
    return _backoff_s(attempt)


def path_is_cloud_storage_backed(path: str | Path) -> bool:
    norm = os.path.normpath(os.path.abspath(str(path)))
    return "CloudStorage" in norm or f"{os.sep}Dropbox{os.sep}" in norm


def local_staging_temp_path(*, suffix: str = ".mp4", prefix: str = "mn_ff_") -> Path:
    staging = Path(tempfile.gettempdir()) / "mn_ffmpeg_scratch"
    staging.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(staging), prefix=prefix, suffix=suffix or ".tmp")
    os.close(fd)
    return Path(tmp_path)


def _copy_file_chunked(src: str, dst: str, *, chunk_size: int = 1024 * 1024) -> None:
    with open(src, "rb") as fin, open(dst, "wb") as fout:
        while True:
            chunk = fin.read(chunk_size)
            if not chunk:
                break
            fout.write(chunk)


def copy_file_durable(src: str | Path, dst: str | Path, *, chunk_size: int = 1024 * 1024) -> None:
    """Copy bytes onto cloud-backed paths with errno 11/35 retry."""
    src_path = os.path.abspath(str(src))
    dst_path = os.path.abspath(str(dst))
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    tmp_dir: str | None = os.path.dirname(dst_path) or None
    if path_is_cloud_storage_backed(dst_path):
        tmp_dir = str(Path(tempfile.gettempdir()) / "mn_ffmpeg_scratch")
        Path(tmp_dir).mkdir(parents=True, exist_ok=True)
    last_err: OSError | None = None
    for attempt in range(_MAX_ATTEMPTS):
        tmp_path: str | None = None
        try:
            fd, tmp_path = tempfile.mkstemp(
                dir=tmp_dir,
                prefix=".mn_copy_",
                suffix=Path(dst_path).suffix or ".tmp",
            )
            os.close(fd)
            _copy_file_chunked(src_path, tmp_path, chunk_size=chunk_size)
            os.replace(tmp_path, dst_path)
            return
        except OSError as exc:
            last_err = exc
            if exc.errno not in _TRANSIENT_ERRNOS or attempt >= _MAX_ATTEMPTS - 1:
                raise
            time.sleep(_backoff_s(attempt))
        finally:
            if tmp_path:
                with contextlib.suppress(OSError):
                    os.unlink(tmp_path)
    if last_err:
        raise last_err


def commit_local_file_to_dest(local_path: str | Path, dest: str | Path) -> None:
    copy_file_durable(local_path, dest)
    with contextlib.suppress(OSError):
        os.unlink(str(local_path))


def sidecar_io_transient(exc: BaseException) -> bool:
    return isinstance(exc, OSError) and getattr(exc, "errno", None) in _TRANSIENT_ERRNOS


def dropbox_io_transient(exc: BaseException) -> bool:
    """True for macOS File Provider errno 11 (EDEADLK) / 35 (EAGAIN)."""
    return sidecar_io_transient(exc)


def confined_path_under_roots(path: str | Path, roots: Sequence[str]) -> str:
    """Return realpath only when it is exactly a root or under root+sep.

    CODEQL_PATH_INJECTION_NATIVE_PATTERN — callers must use the returned string
    (assigned inside the startswith branch) for subsequent open/stat/isfile.
    """
    try:
        real = os.path.realpath(os.path.expanduser(str(path)))
    except OSError:
        real = os.path.abspath(os.path.expanduser(str(path)))
    safe = ""
    for root in roots:
        if not root:
            continue
        try:
            root_real = os.path.realpath(root)
        except OSError:
            root_real = os.path.abspath(root)
        if real == root_real or real.startswith(root_real + os.sep):
            safe = real
            break
    if not safe:
        raise PermissionError(f"path outside allowed roots: {path}")
    return safe


def path_stat_durable(path: str | Path, *, roots: Sequence[str]) -> os.stat_result:
    """stat() with errno 11/35 retry after root confinement."""
    path_s = confined_path_under_roots(path, roots)
    last_err: OSError | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            return os.stat(path_s)
        except OSError as exc:
            last_err = exc
            if exc.errno not in _TRANSIENT_ERRNOS or attempt >= _MAX_ATTEMPTS - 1:
                raise
            time.sleep(_backoff_s(attempt))
    assert last_err is not None
    raise last_err


def path_isfile_durable(path: str | Path, *, roots: Sequence[str]) -> bool:
    """isfile() with errno 11/35 retry after root confinement."""
    path_s = confined_path_under_roots(path, roots)
    last_err: OSError | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            return os.path.isfile(path_s)
        except OSError as exc:
            last_err = exc
            if exc.errno not in _TRANSIENT_ERRNOS or attempt >= _MAX_ATTEMPTS - 1:
                raise
            time.sleep(_backoff_s(attempt))
    assert last_err is not None
    raise last_err


def read_bytes_durable(path: str | Path, *, roots: Sequence[str]) -> bytes:
    """Read whole file with errno 11/35 retry after root confinement."""
    path_s = confined_path_under_roots(path, roots)
    last_err: OSError | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            with open(path_s, "rb") as fh:
                return fh.read()
        except OSError as exc:
            last_err = exc
            if exc.errno not in _TRANSIENT_ERRNOS or attempt >= _MAX_ATTEMPTS - 1:
                raise
            time.sleep(_backoff_s(attempt))
    assert last_err is not None
    raise last_err


def ffmpeg_failure_transient(stderr: str | None) -> bool:
    text = str(stderr or "")
    return (
        "Resource deadlock avoided" in text
        or "[Errno 11]" in text
        or "[Errno 35]" in text
        or "Resource temporarily unavailable" in text
    )


def run_ffmpeg_to_dest(
    cmd: Sequence[str],
    dest: str | Path,
    *,
    timeout: int = 240,
    error_prefix: str = "ffmpeg failed",
) -> Path:
    """Run ffmpeg with output path replaced by local staging; commit to dest on success."""
    dest_path = Path(dest)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    local_tmp = local_staging_temp_path(suffix=dest_path.suffix or ".mp4", prefix="ff_out_")
    out_idx = len(cmd) - 1
    local_cmd = list(cmd)
    local_cmd[out_idx] = str(local_tmp)
    last_err: str | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            r = subprocess.run(local_cmd, capture_output=True, text=True, timeout=timeout)
            if r.returncode != 0 or not local_tmp.is_file():
                last_err = (r.stderr or "")[-500:]
                if ffmpeg_failure_transient(r.stderr) and attempt < _MAX_ATTEMPTS - 1:
                    time.sleep(_backoff_s(attempt))
                    continue
                if local_tmp.is_file():
                    local_tmp.unlink(missing_ok=True)
                raise RuntimeError(f"{error_prefix}: {last_err}")
            commit_local_file_to_dest(local_tmp, dest_path)
            return dest_path
        except OSError as exc:
            if sidecar_io_transient(exc) and attempt < _MAX_ATTEMPTS - 1:
                time.sleep(_backoff_s(attempt))
                continue
            with contextlib.suppress(OSError):
                local_tmp.unlink(missing_ok=True)
            raise
    if local_tmp.is_file():
        local_tmp.unlink(missing_ok=True)
    raise RuntimeError(f"{error_prefix}: {last_err or 'unknown'}")


def run_ffmpeg_builder_to_dest(
    build_cmd: Callable[[Path], Sequence[str]],
    dest: str | Path,
    *,
    timeout: int = 240,
    error_prefix: str = "ffmpeg failed",
) -> Path:
    """Build ffmpeg argv with local output path injected by builder."""
    dest_path = Path(dest)
    local_tmp = local_staging_temp_path(suffix=dest_path.suffix or ".mp4", prefix="ff_out_")
    cmd = list(build_cmd(local_tmp))
    return run_ffmpeg_to_dest(cmd, dest_path, timeout=timeout, error_prefix=error_prefix)
