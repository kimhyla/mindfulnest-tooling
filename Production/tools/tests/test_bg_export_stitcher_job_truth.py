"""BG_EXPORT_TO_STITCHER_ASYNC_V1 — durable async export job store + handlers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from bg_export_stitcher_job_store import (
    BG_EXPORT_TO_STITCHER_ASYNC_V1,
    create_job,
    export_lock_is_free,
    export_lock_path,
    finalize_job,
    find_active_job_for_scope_key,
    job_poll_payload,
    load_job,
    new_job_id,
    reconcile_stale_running_jobs,
    update_job_progress,
)


def test_create_and_poll_export_job_roundtrip(tmp_path: Path) -> None:
    job_id = new_job_id()
    create_job(
        tmp_path,
        job_id=job_id,
        scope_key="1|2|pre|intro",
        scope_event_id="Event_2",
        arc_number=1,
        bg_event_id="2",
        phase="pre",
        slot_key="intro",
        beat_ids=["b1", "b2"],
        pin={"pinned_generation": 1, "pinned_event_dir": str(tmp_path), "pinned_video_role": "intro"},
    )
    job = load_job(tmp_path, job_id)
    assert job is not None
    assert job["status"] == "queued"
    assert job["code"] == BG_EXPORT_TO_STITCHER_ASYNC_V1
    assert job["segment_phase"] == "pre"

    update_job_progress(tmp_path, job_id, status="running", phase="materialize", beat_index=1, beat_total=2)
    payload = job_poll_payload(load_job(tmp_path, job_id) or {})
    assert payload["status"] == "running"
    assert payload["beat_index"] == 1

    finalize_job(
        tmp_path,
        job_id,
        "done",
        result={"ok": True, "slot_key": "intro", "video_path": "Production/Event_2/assembled/x.mp4"},
    )
    terminal = load_job(tmp_path, job_id)
    assert terminal is not None
    assert terminal["status"] == "done"
    assert terminal["result"]["slot_key"] == "intro"


def test_find_active_job_for_scope_key_skips_terminal(tmp_path: Path) -> None:
    job_id = new_job_id()
    create_job(
        tmp_path,
        job_id=job_id,
        scope_key="1|2|pre|intro",
        scope_event_id="Event_2",
        arc_number=1,
        bg_event_id="2",
        phase="pre",
        slot_key="intro",
        beat_ids=["b1"],
        pin={"pinned_generation": 1, "pinned_event_dir": str(tmp_path), "pinned_video_role": "intro"},
    )
    assert find_active_job_for_scope_key(tmp_path, "1|2|pre|intro") is not None
    finalize_job(tmp_path, job_id, "failed", error="boom", error_code="TEST")
    assert find_active_job_for_scope_key(tmp_path, "1|2|pre|intro") is None


def test_reconcile_stale_running_export_jobs_when_lock_free(tmp_path: Path) -> None:
    lock_path = export_lock_path(tmp_path)
    job_id = new_job_id()
    create_job(
        tmp_path,
        job_id=job_id,
        scope_key="1|2|pre|intro",
        scope_event_id="Event_2",
        arc_number=1,
        bg_event_id="2",
        phase="pre",
        slot_key="intro",
        beat_ids=["b1"],
        pin={"pinned_generation": 1, "pinned_event_dir": str(tmp_path), "pinned_video_role": "intro"},
    )
    update_job_progress(tmp_path, job_id, status="running")

    interrupted = reconcile_stale_running_jobs(tmp_path, lock_path)
    assert job_id in interrupted
    job = load_job(tmp_path, job_id)
    assert job is not None
    assert job["status"] == "interrupted"


def test_export_lock_is_free_when_unheld(tmp_path: Path) -> None:
    assert export_lock_is_free(export_lock_path(tmp_path)) is True


def test_handle_bg_export_submits_async_job(tmp_path: Path) -> None:
    from server_handlers import kling_o3 as ko

    h = MagicMock()
    h.app.event_dir = tmp_path
    h.app.event_generation = 1
    h._assert_event_scope.return_value = True
    h._scope_body.return_value = {"scope_event_id": "Event_2"}
    h._check_event_pin.return_value = True
    h._send_json = MagicMock()

    ctx = {
        "arc_number": 1,
        "bg_event_id": "2",
        "phase": "pre",
        "slot_key": "intro",
        "scope_key": "1|2|pre|intro",
        "beat_ids": ["b1"],
        "beats": [{"beat_id": "b1"}],
    }

    with patch.object(ko, "_prepare_bg_export_request", return_value=ctx):
        with patch.object(ko.threading, "Thread") as thread_cls:
            thread_cls.return_value.start = MagicMock()
            ko.handle_bg_export_to_stitcher(h, {
                "arc_number": 1,
                "event_id": "2",
                "phase": "pre",
                "slot_key": "intro",
                "scope_event_id": "Event_2",
            })

    h._send_json.assert_called_once()
    status = h._send_json.call_args[0][0]
    payload = h._send_json.call_args[0][1]
    assert status == 202
    assert payload.get("submitted") is True
    assert payload.get("job_id")
    thread_cls.return_value.start.assert_called_once()


def test_poll_export_route_registered_in_production_server() -> None:
    tools = Path(__file__).resolve().parent.parent
    src = (tools / "production_server.py").read_text(encoding="utf-8")
    assert 'path == "/api/bg/poll-export-to-stitcher"' in src
    assert "handle_bg_poll_export_to_stitcher_status" in src
