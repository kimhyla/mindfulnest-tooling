"""LD-661 closure regression test: concurrent offline-queue writers don't lose entries.

Per Cursor cross-review finding 1B (2026-05-10): without fcntl.flock around
queue_write_offline, two concurrent writers race on read-modify-write and lose
entries. This test fires N parallel writers; expects len(queue) == N afterward.

Run:
    .venv/bin/python -m pytest tests/test_concurrent_offline_queue.py -v
"""

from __future__ import annotations

import json
import os
import sys
import threading
import uuid
from pathlib import Path

import pytest

_THIS = Path(__file__).resolve()
_PRODUCTION = _THIS.parent.parent.parent.parent
sys.path.insert(0, str(_PRODUCTION))

from lib.directus import _PENDING_QUEUE_PATH, queue_write_offline  # noqa: E402


def test_concurrent_writers_preserve_all_entries(tmp_path, monkeypatch):
    # Redirect the queue path to a temp file for this test.
    test_queue = tmp_path / "pending_directus_writes.json"
    test_lock = tmp_path / "pending_directus_writes.lock"
    monkeypatch.setattr("lib.directus._PENDING_QUEUE_PATH", test_queue)
    monkeypatch.setattr("lib.directus._LOCK_PATH", test_lock)

    n_writers = 20
    barrier = threading.Barrier(n_writers)
    errors: list[Exception] = []

    def worker(i: int):
        try:
            barrier.wait()  # all start at the same instant for max contention
            queue_write_offline(
                "prod_test",
                {"writer_index": i, "uuid": str(uuid.uuid4())},
                reason=f"concurrent_test_{i}",
            )
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_writers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert not errors, f"Errors: {errors}"

    # Verify all N entries landed.
    queue = json.loads(test_queue.read_text())
    assert isinstance(queue, list)
    assert len(queue) == n_writers, f"Expected {n_writers} entries, got {len(queue)}"

    indices = sorted(entry["payload"]["writer_index"] for entry in queue)
    assert indices == list(range(n_writers))


def test_lock_path_is_sidecar():
    """Lock file must be a sidecar (.lock), not the queue file itself.
    Otherwise reads of an empty queue at startup could race with the lock.
    """
    from lib.directus import _LOCK_PATH, _PENDING_QUEUE_PATH

    assert _LOCK_PATH != _PENDING_QUEUE_PATH
    assert _LOCK_PATH.suffix == ".lock"
