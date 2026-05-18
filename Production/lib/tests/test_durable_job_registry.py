"""Tests for Production/lib/durable_job_registry.py — V59 Phase 5."""

from __future__ import annotations

import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pytest

_TOOLING_REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_TOOLING_REPO))

from Production.lib.durable_job_registry import DurableJobRegistry  # noqa: E402


def _registry(tmp_path) -> DurableJobRegistry:
    return DurableJobRegistry(db_path=tmp_path / "test.db")


def test_submit_creates_row(tmp_path):
    reg = _registry(tmp_path)
    reg.submit(
        beat_id="beat_01",
        vendor="kling",
        task_id="task-1",
        video_role="intro",
        event_generation=1,
        option_idx=0,
    )
    assert len(reg.all_jobs()) == 1


def test_submit_duplicate_task_id_raises(tmp_path):
    reg = _registry(tmp_path)
    reg.submit(
        beat_id="beat_01",
        vendor="kling",
        task_id="dup-task",
        video_role="intro",
        event_generation=1,
    )
    with pytest.raises(sqlite3.IntegrityError):
        reg.submit(
            beat_id="beat_02",
            vendor="kling",
            task_id="dup-task",
            video_role="intro",
            event_generation=1,
        )


def test_mark_completed(tmp_path):
    reg = _registry(tmp_path)
    reg.submit(
        beat_id="beat_01",
        vendor="kling",
        task_id="task-done",
        video_role="intro",
        event_generation=1,
    )
    reg.mark("task-done", "completed")
    assert reg.list_pending() == []


def test_list_pending_filters_by_vendor(tmp_path):
    reg = _registry(tmp_path)
    reg.submit(
        beat_id="b1",
        vendor="kling",
        task_id="k1",
        video_role="intro",
        event_generation=1,
    )
    reg.submit(
        beat_id="b2",
        vendor="bytedance",
        task_id="b1",
        video_role="intro",
        event_generation=1,
    )
    pending = reg.list_pending(vendor="kling")
    assert len(pending) == 1
    assert pending[0]["vendor"] == "kling"


def test_list_pending_filters_by_event_generation(tmp_path):
    reg = _registry(tmp_path)
    reg.submit(
        beat_id="b1",
        vendor="kling",
        task_id="g1",
        video_role="intro",
        event_generation=1,
    )
    reg.submit(
        beat_id="b2",
        vendor="kling",
        task_id="g2",
        video_role="intro",
        event_generation=2,
    )
    pending = reg.list_pending(event_generation=2)
    assert len(pending) == 1
    assert pending[0]["event_generation"] == 2


def test_purge_stale_keeps_pending(tmp_path, monkeypatch):
    reg = _registry(tmp_path)
    monkeypatch.setattr("Production.lib.durable_job_registry.time.time", lambda: 100)
    reg.submit(
        beat_id="b1",
        vendor="kling",
        task_id="purge-me",
        video_role="intro",
        event_generation=1,
    )
    reg.mark("purge-me", "completed")
    assert reg.purge_stale(older_than_epoch=50) == 0
    assert reg.purge_stale(older_than_epoch=200) == 1
    assert reg.all_jobs() == []


def test_wal_mode_set(tmp_path):
    reg = _registry(tmp_path)
    with reg._conn() as c:
        row = c.execute("PRAGMA journal_mode").fetchone()
    assert row[0].lower() == "wal"


def test_concurrent_submits_serialize(tmp_path):
    reg = _registry(tmp_path)
    n_threads = 4
    per_thread = 25

    def _submit(i: int, j: int) -> None:
        reg.submit(
            beat_id=f"beat_{i}_{j}",
            vendor="kling",
            task_id=f"task-{i}-{j}",
            video_role="intro",
            event_generation=1,
        )

    with ThreadPoolExecutor(max_workers=n_threads) as pool:
        futures = [
            pool.submit(_submit, i, j)
            for i in range(n_threads)
            for j in range(per_thread)
        ]
        for fut in as_completed(futures):
            fut.result()

    jobs = reg.all_jobs()
    assert len(jobs) == n_threads * per_thread
    task_ids = [j["task_id"] for j in jobs]
    assert len(task_ids) == len(set(task_ids))
