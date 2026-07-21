"""Cross-platform advisory lock compatibility contract."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from Production.lib import fcntl_compat as fcntl


def test_exclusive_nonblocking_lock_and_release(tmp_path: Path) -> None:
    lock_path = tmp_path / "compat.lock"
    first = os.open(lock_path, os.O_CREAT | os.O_RDWR)
    second = os.open(lock_path, os.O_RDWR)
    try:
        fcntl.flock(first, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises((BlockingIOError, OSError)):
            fcntl.flock(second, fcntl.LOCK_EX | fcntl.LOCK_NB)

        fcntl.flock(first, fcntl.LOCK_UN)
        fcntl.flock(second, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(second, fcntl.LOCK_UN)
    finally:
        os.close(first)
        os.close(second)

    assert lock_path.stat().st_size >= 1
