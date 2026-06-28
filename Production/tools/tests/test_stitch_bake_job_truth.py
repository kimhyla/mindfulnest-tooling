"""STITCH_BAKE_JOB_TRUTH_V1 — durable async stitch bake job store + handlers."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from stitch_bake_job_store import (
    STITCH_BAKE_JOB_TRUTH_V1,
    active_bake_job_summary,
    bake_lock_is_free,
    create_job,
    finalize_job,
    find_active_job_for_stitch_job,
    job_poll_payload,
    load_job,
    new_job_id,
    reconcile_stale_running_jobs,
    update_job_progress,
)


def test_create_and_poll_job_roundtrip(tmp_path: Path) -> None:
    job_id = new_job_id()
    create_job(
        tmp_path,
        job_id=job_id,
        stitch_job_name="Event_2_stitch",
        scope_event_id="Event_2",
    )
    job = load_job(tmp_path, job_id)
    assert job is not None
    assert job["status"] == "queued"
    assert job["code"] == STITCH_BAKE_JOB_TRUTH_V1

    update_job_progress(tmp_path, job_id, status="running", phase="encode", message="Encoding…")
    payload = job_poll_payload(load_job(tmp_path, job_id) or {})
    assert payload["status"] == "running"
    assert payload["phase"] == "encode"

    finalize_job(
        tmp_path,
        job_id,
        "done",
        result={"ok": True, "bake_path": "/tmp/out.mp4", "canonical_path": "/canon/out.mp4"},
    )
    terminal = load_job(tmp_path, job_id)
    assert terminal is not None
    assert terminal["status"] == "done"
    assert terminal["result"]["canonical_path"] == "/canon/out.mp4"


def test_find_active_job_for_stitch_job_skips_terminal(tmp_path: Path) -> None:
    job_id = new_job_id()
    create_job(tmp_path, job_id=job_id, stitch_job_name="Event_2_stitch", scope_event_id="Event_2")
    assert find_active_job_for_stitch_job(tmp_path, "Event_2_stitch") is not None
    finalize_job(tmp_path, job_id, "failed", error="boom")
    assert find_active_job_for_stitch_job(tmp_path, "Event_2_stitch") is None


def test_reconcile_stale_running_jobs_when_lock_free(tmp_path: Path) -> None:
    lock_path = tmp_path / "stitch_bake.lock"
    lock_path.touch()
    job_id = new_job_id()
    create_job(tmp_path, job_id=job_id, stitch_job_name="Event_2_stitch", scope_event_id="Event_2")
    update_job_progress(tmp_path, job_id, status="running")

    interrupted = reconcile_stale_running_jobs(tmp_path, lock_path)
    assert job_id in interrupted
    job = load_job(tmp_path, job_id)
    assert job is not None
    assert job["status"] == "interrupted"
    assert "interrupted" in (job.get("message") or "").lower()


def test_active_bake_job_summary_prefers_running(tmp_path: Path) -> None:
    import fcntl
    import os

    lock_path = tmp_path / "stitch_bake.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR)
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
        older = new_job_id()
        newer = new_job_id()
        create_job(tmp_path, job_id=older, stitch_job_name="Event_2_stitch", scope_event_id="Event_2")
        finalize_job(tmp_path, older, "failed", error="old")
        create_job(tmp_path, job_id=newer, stitch_job_name="Event_2_stitch", scope_event_id="Event_2")
        update_job_progress(tmp_path, newer, status="running", message="Working")

        summary = active_bake_job_summary(tmp_path, "Event_2_stitch", lock_path=lock_path)
        assert summary is not None
        assert summary["job_id"] == newer
        assert summary["status"] == "running"
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def test_bake_lock_is_free_when_unheld(tmp_path: Path) -> None:
    lock_path = tmp_path / "stitch_bake.lock"
    assert bake_lock_is_free(lock_path) is True


def test_handle_stitch_bake_submits_async_job(tmp_path: Path) -> None:
    from server_handlers import stitch_editor as se

    h = MagicMock()
    h.app.event_dir = tmp_path
    h.app.event_generation = 1
    h._assert_event_scope.return_value = True
    h._scope_body.return_value = {"scope_event_id": "Event_2"}
    h._check_event_pin.return_value = True
    h._stitch_cache_dir.return_value = tmp_path / "cache"
    (tmp_path / "cache").mkdir(parents=True, exist_ok=True)
    h._send_json = MagicMock()

    body = {"name": "Event_2_stitch", "scope_event_id": "Event_2"}
    with patch.object(se.threading, "Thread") as thread_cls:
        thread_cls.return_value.start = MagicMock()
        se.handle_stitch_bake(h, body)

    h._send_json.assert_called_once()
    status_code, payload = h._send_json.call_args[0]
    assert status_code == 202
    assert payload["ok"] is True
    assert payload["job_id"]
    assert payload["code"] == STITCH_BAKE_JOB_TRUTH_V1
    thread_cls.assert_called_once()


def test_handle_stitch_bake_status_returns_job(tmp_path: Path) -> None:
    from server_handlers import stitch_editor as se

    job_id = new_job_id()
    create_job(tmp_path, job_id=job_id, stitch_job_name="Event_2_stitch", scope_event_id="Event_2")
    finalize_job(tmp_path, job_id, "done", result={"ok": True, "bake_path": "/x.mp4"})

    h = MagicMock()
    h.app.event_dir = tmp_path
    h.path = f"/api/stitch_editor/bake/status?job_id={job_id}"
    h._stitch_cache_dir.return_value = tmp_path / "cache"
    h._send_json = MagicMock()

    se.handle_stitch_bake_status(h)
    h._send_json.assert_called_once()
    status_code, payload = h._send_json.call_args[0]
    assert status_code == 200
    assert payload["job_id"] == job_id
    assert payload["status"] == "done"


def test_load_job_includes_bake_job_summary(tmp_path: Path) -> None:
    import fcntl
    import os

    from server_handlers import stitch_editor as se

    job_id = new_job_id()
    create_job(tmp_path, job_id=job_id, stitch_job_name="Event_2_stitch", scope_event_id="Event_2")
    update_job_progress(tmp_path, job_id, status="running", message="Encoding")

    h = MagicMock()
    h.app.event_dir = tmp_path
    h.app.stitch_state.read_state.return_value = {
        "jobs": {"Event_2_stitch": {"slots": {"intro": {"video_path": "intro.mp4"}}}},
    }
    h._stitch_cache_dir.return_value = tmp_path / "cache"
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    lock_path = cache_dir / "stitch_bake.lock"
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR)
    fcntl.flock(fd, fcntl.LOCK_EX)
    h._send_json = MagicMock()

    try:
        with patch("copy.deepcopy", side_effect=lambda x: json.loads(json.dumps(x))), patch.object(
            se, "normalize_job_slots_audio",
        ), patch.object(se, "ensure_job_slot_defaults", return_value=False), patch.object(
            se, "collect_stitch_job_slot_warnings", return_value=None,
        ):
            se.handle_stitch_load_job(h, "Event_2_stitch")
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)

    h._send_json.assert_called_once()
    payload = h._send_json.call_args[0][1]
    assert payload.get("bake_job_code") == STITCH_BAKE_JOB_TRUTH_V1
    assert payload["bake_job"]["job_id"] == job_id
    assert payload["bake_job"]["status"] == "running"
