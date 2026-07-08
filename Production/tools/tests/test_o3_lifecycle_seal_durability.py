"""TECH_SPEC_O3_LIFECYCLE_SEAL_v1 — contract + anti-regression matrix."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]


def test_lifecycle_ignores_log_path_only():
    from o3_job_status_contract import resolve_o3_job_id_for_lifecycle

    beat = {
        "beat_id": "bg_arc1_event6_pre_beat_02",
        "kling_o3_voice_fix_job_log_path": (
            "/Event_6/arlo_o3_jobs/631adc8f_bg_arc1_event6_pre_beat_02.log"
        ),
    }
    assert resolve_o3_job_id_for_lifecycle(beat) == ""


def test_lifecycle_honors_o3_current_job_id():
    from o3_job_status_contract import resolve_o3_job_id_for_lifecycle

    beat = {
        "o3_current_job_id": "631adc8f",
        "kling_o3_voice_fix_job_log_path": "/other.log",
    }
    assert resolve_o3_job_id_for_lifecycle(beat) == "631adc8f"


def test_terminal_binds_active_lifecycle_requires_pointer():
    from o3_job_status_contract import terminal_binds_active_lifecycle

    beat = {"o3_current_job_id": "631adc8f"}
    assert terminal_binds_active_lifecycle(beat, "631adc8f") is True
    assert terminal_binds_active_lifecycle(beat, "deadbeef") is False
    log_only = {"kling_o3_voice_fix_job_log_path": "/631adc8f_beat.log"}
    assert terminal_binds_active_lifecycle(log_only, "631adc8f") is False


def test_session_get_does_not_compose_terminal_view():
    src = (TOOLS / "server_handlers" / "background.py").read_text(encoding="utf-8")
    block = src.split("def handle_bg_session_state", 1)[1].split("\ndef ", 1)[0]
    assert "_compose_o3_session_terminal_view(" not in block
    assert "Session GET is read-only for gallery" in block


def test_startup_wires_terminal_reconcile():
    src = (TOOLS / "server_handlers" / "background.py").read_text(encoding="utf-8")
    assert "def _run_o3_terminal_reconcile_at_startup" in src
    assert "_run_o3_terminal_reconcile_at_startup(h_stub, scope_event_id)" in src


def test_restore_last_good_does_not_resort_slots():
    src = (TOOLS / "o3_generation_intent.py").read_text(encoding="utf-8")
    fn = src.split("def restore_last_good_o3_delivery_after_failed_attempt", 1)[1]
    fn = fn.split("\ndef ", 1)[0]
    assert "refresh_o3_ui_slot_layout" not in fn


def test_reconcile_failed_skips_without_active_pointer(tmp_path: Path):
    from o3_session_terminal_reconcile import reconcile_beat_terminal_disk

    event_dir = tmp_path / "Event_6"
    jobs = event_dir / "arlo_o3_jobs"
    clips = event_dir / "kling_o3_clips"
    jobs.mkdir(parents=True)
    clips.mkdir(parents=True)
    beat_id = "bg_arc1_event6_pre_beat_02"
    job_id = "631adc8f"
    delivery = clips / f"{beat_id}_g2_element_o3_master_delivery.mp4"
    delivery.write_bytes(b"x" * 200_000)
    (jobs / f"{job_id}_terminal.json").write_text(
        json.dumps({"status": "failed", "job_id": job_id, "failure": {"message": "encode fail"}}),
        encoding="utf-8",
    )
    beat = {
        "beat_id": beat_id,
        "kling_o3_video_path": str(delivery),
        "kling_o3_generation": 2,
        "kling_o3_options": [{"generation": 2, "video_path": str(delivery), "active": True}],
        "kling_o3_voice_fix_job_log_path": f"{jobs}/{job_id}_{beat_id}.log",
    }
    before_video = beat["kling_o3_video_path"]
    reconcile_beat_terminal_disk(beat, {}, event_dir)
    assert beat["kling_o3_video_path"] == before_video
    assert beat.get("kling_o3_generation") == 2


def test_reconcile_failed_heals_with_active_pointer(tmp_path: Path):
    from o3_session_terminal_reconcile import reconcile_beat_terminal_disk

    event_dir = tmp_path / "Event_6"
    clips = event_dir / "kling_o3_clips"
    jobs = event_dir / "arlo_o3_jobs"
    clips.mkdir(parents=True)
    jobs.mkdir(parents=True)
    beat_id = "bg_arc1_event6_pre_beat_02"
    job_id = "631adc8f"
    g2 = clips / f"{beat_id}_g2_element_o3_master_delivery.mp4"
    g3_bad = clips / f"{beat_id}_g3_element_o3_master_delivery.mp4"
    g2.write_bytes(b"x" * 200_000)
    g3_bad.write_bytes(b"y" * 200_000)
    (jobs / f"{job_id}_terminal.json").write_text(
        json.dumps({
            "status": "failed",
            "intent": {"generation_slot": "g3"},
            "failure": {"message": "encode fail"},
        }),
        encoding="utf-8",
    )
    beat = {
        "beat_id": beat_id,
        "o3_current_job_id": job_id,
        "kling_o3_video_path": str(g3_bad),
        "kling_o3_generation": 3,
        "kling_o3_options": [
            {"generation": 2, "video_path": str(g2), "active": False},
            {"generation": 3, "video_path": str(g3_bad), "active": True},
        ],
    }
    reconcile_beat_terminal_disk(beat, {}, event_dir)
    assert str(beat.get("kling_o3_video_path") or "").endswith("_g2_element_o3_master_delivery.mp4")


def test_seal_master_only_returns_done_with_warning(tmp_path: Path):
    from o3_recovery_seal import seal_o3_recovery_before_terminal

    event_dir = tmp_path / "Event_6"
    clips = event_dir / "kling_o3_clips"
    clips.mkdir(parents=True)
    beat_id = "bg_arc1_event6_pre_beat_02"
    master = clips / f"{beat_id}_g3_element_o3_master.mp4"
    master.write_bytes(b"m" * 500_000)
    seal = seal_o3_recovery_before_terminal(
        beat_id,
        event_dir,
        master_path=master,
        failure_message="ffmpeg exit 254",
    )
    assert seal["terminal_status"] == "done_with_warning"
    assert seal["master_path"] == str(master.resolve())
    assert seal["warning"]["code"] == "DELIVERY_ENCODE_PENDING"


def test_seal_delivery_triggers_orphan_recovery(tmp_path: Path, monkeypatch):
    from o3_recovery_seal import seal_o3_recovery_before_terminal

    event_dir = tmp_path / "Event_6"
    clips = event_dir / "kling_o3_clips"
    clips.mkdir(parents=True)
    beat_id = "bg_arc1_event6_pre_beat_02"
    delivery = clips / f"{beat_id}_g3_element_o3_master_delivery.mp4"
    delivery.write_bytes(b"d" * 300_000)

    calls: list[dict] = []

    def _fake_recover(beat_id, event_dir, log_path=None, **kw):
        calls.append({"beat_id": beat_id, **kw})
        return {"ok": True, "video_path": kw.get("delivery_path")}

    import beat_generator as bg

    monkeypatch.setattr(bg, "recover_orphan_o3_delivery", _fake_recover)
    seal = seal_o3_recovery_before_terminal(
        beat_id,
        event_dir,
        delivery_path=delivery,
    )
    assert seal["terminal_status"] == "done"
    assert seal["recovered"] is True
    assert calls


def test_clear_o3_job_metadata_clears_pointer_fields():
    src = (TOOLS / "server_handlers" / "background.py").read_text(encoding="utf-8")
    fn = src.split("def _clear_o3_job_metadata", 1)[1].split("\ndef ", 1)[0]
    assert "clear_o3_job_cache_fields" in fn


def test_session_state_read_only_no_compose_on_get():
    src = (TOOLS / "server_handlers" / "background.py").read_text(encoding="utf-8")
    block = src.split("def handle_bg_session_state", 1)[1].split("\ndef ", 1)[0]
    assert "reconcile_o3_terminal_attempt_fields_all_events" not in block
    assert "_compose_o3_session_terminal_view(" not in block
    assert "def _run_o3_terminal_reconcile_at_startup" in (TOOLS / "server_handlers" / "background.py").read_text(encoding="utf-8")
