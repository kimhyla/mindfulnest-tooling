"""Small cross-platform subset of :mod:`fcntl` used by MindfulNest.

Windows has no ``fcntl`` module. This adapter preserves the LOCK_EX/LOCK_UN/
LOCK_NB API used by the tooling and maps one-byte advisory locks to
``msvcrt.locking``.
"""
from __future__ import annotations

import errno
import os
import sys

LOCK_EX = 1
LOCK_UN = 2
LOCK_NB = 4

if sys.platform != "win32":
    import fcntl as _fcntl

    LOCK_EX = _fcntl.LOCK_EX
    LOCK_UN = _fcntl.LOCK_UN
    LOCK_NB = _fcntl.LOCK_NB

    def flock(fd: int, operation: int) -> None:
        _fcntl.flock(fd, operation)

    def lockf(fd: int, operation: int) -> None:
        _fcntl.lockf(fd, operation)

else:
    import msvcrt

    def _ensure_lock_byte(fd: int) -> None:
        if os.fstat(fd).st_size == 0:
            os.lseek(fd, 0, os.SEEK_SET)
            os.write(fd, b"\0")
        os.lseek(fd, 0, os.SEEK_SET)

    def _locking(fd: int, operation: int) -> None:
        _ensure_lock_byte(fd)
        if operation & LOCK_UN:
            mode = msvcrt.LK_UNLCK
        elif operation & LOCK_NB:
            mode = msvcrt.LK_NBLCK
        else:
            mode = msvcrt.LK_LOCK
        try:
            msvcrt.locking(fd, mode, 1)
        except OSError as exc:
            if operation & LOCK_NB:
                raise BlockingIOError(
                    errno.EAGAIN,
                    "file lock is held by another process",
                ) from exc
            raise

    def flock(fd: int, operation: int) -> None:
        _locking(fd, operation)

    def lockf(fd: int, operation: int) -> None:
        _locking(fd, operation)
