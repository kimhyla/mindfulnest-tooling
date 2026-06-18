"""Stuck O3 voice job reconciliation — regression for dead-process + stale errors."""
from __future__ import annotations

import json
from pathlib import Path

import beat_generator as bg

TOOLS = Path(__file__).resolve().parent.parent


def _import_background():
    import importlib

    return importlib.import_module("server_handlers.background")


def test_reconcile_clears_stale_running_with_failed_voice_fix(monkeypatch, tmp_path) -> None:
    bg_mod = _import_background()
    sidecar = {
        "schema_version": 1,
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_1_pre": {
                        "beats": [
                            {
                                "beat_id": "bg_arc1_event1_pre_beat_07",
                                "status": "o3_voice_job_running",
                                "kling_o3_status": "approved",
                                "kling_o3_video_path": str(tmp_path / "delivery.mp4"),
                                "kling_o3_voice_fix_status": "failed",
                                "kling_o3_voice_fix_error": "AttributeError: module 'beat_generator' has no attribute 'update_beat_locked'",
                                "kling_o3_voice_fix_job_pid": 999999,
                                "kling_o3_voice_fix_ui_job_id": "deadjob1",
                            }
                        ],
                    },
                },
            },
        },
    }
    (tmp_path / "delivery.mp4").write_bytes(b"x")
    monkeypatch.setattr(bg_mod, "_pid_is_running", lambda _pid: False)
    changed = bg_mod.reconcile_stuck_o3_voice_beats(sidecar)
    beat = sidecar["arcs"]["arc_1"]["segments"]["event_1_pre"]["beats"][0]
    assert changed == 1
    assert beat["status"] == "approved"
    assert beat.get("kling_o3_voice_fix_error") is None
    assert beat.get("kling_o3_voice_fix_ui_job_id") is None


def test_reconcile_clears_stale_pid_after_approved_element_pipeline(monkeypatch, tmp_path) -> None:
    bg_mod = _import_background()
    delivery = tmp_path / "bg_arc1_event2_pre_beat_02_g5_element_o3_master_delivery.mp4"
    delivery.write_bytes(b"fake mp4")
    sidecar = {
        "schema_version": 1,
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_2_pre": {
                        "beats": [
                            {
                                "beat_id": "bg_arc1_event2_pre_beat_02",
                                "status": "approved",
                                "kling_o3_status": "approved",
                                "kling_o3_video_path": str(delivery),
                                "kling_o3_voice_fix_status": "approved",
                                "kling_o3_voice_fix_job_pid": 96015,
                                "kling_o3_voice_fix_ui_job_id": None,
                            }
                        ],
                    },
                },
            },
        },
    }
    monkeypatch.setattr(bg_mod, "_pid_is_running", lambda _pid: False)
    changed = bg_mod.reconcile_stuck_o3_voice_beats(sidecar)
    beat = sidecar["arcs"]["arc_1"]["segments"]["event_2_pre"]["beats"][0]
    assert changed == 1
    assert beat.get("kling_o3_voice_fix_job_pid") is None


def test_reconcile_recovers_done_element_log_after_dead_subprocess(monkeypatch, tmp_path) -> None:
    bg_mod = _import_background()
    delivery = tmp_path / "bg_arc1_event2_pre_beat_02_g5_element_o3_master_delivery.mp4"
    delivery.write_bytes(b"fake mp4")
    log_path = tmp_path / "job.log"
    log_path.write_text(
        json.dumps({
            "phase": "starting",
            "route": "o3_element_native_voice",
            "beat_id": "bg_arc1_event2_pre_beat_02",
        })
        + "\n"
        + json.dumps({
            "phase": "done",
            "beat_id": "bg_arc1_event2_pre_beat_02",
            "video": str(delivery),
            "delivery": {"width": 1280, "height": 720},
        })
        + "\n",
        encoding="utf-8",
    )
    sidecar = {
        "schema_version": 1,
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_2_pre": {
                        "beats": [
                            {
                                "beat_id": "bg_arc1_event2_pre_beat_02",
                                "status": "o3_element_running",
                                "kling_o3_status": "submitted",
                                "kling_o3_voice_fix_status": "o3_running",
                                "kling_o3_voice_fix_job_pid": 424242,
                                "kling_o3_voice_fix_ui_job_id": "8cde7a99",
                                "kling_o3_voice_fix_job_log_path": str(log_path),
                            }
                        ],
                    },
                },
            },
        },
    }
    monkeypatch.setattr(bg_mod, "_pid_is_running", lambda _pid: False)
    changed = bg_mod.reconcile_stuck_o3_voice_beats(sidecar)
    beat = sidecar["arcs"]["arc_1"]["segments"]["event_2_pre"]["beats"][0]
    assert changed == 1
    assert beat["status"] == "approved"
    assert beat["kling_o3_status"] == "approved"
    assert beat["kling_o3_voice_fix_status"] == "approved"
    assert beat["kling_o3_video_path"] == str(delivery)
    assert beat.get("kling_o3_voice_fix_ui_job_id") is None


def test_parse_element_pipeline_done_log(tmp_path) -> None:
    bg_mod = _import_background()
    log_path = tmp_path / "run.log"
    log_path.write_text(
        '{"phase": "delivery_encode"}\n'
        + json.dumps({
            "phase": "done",
            "beat_id": "bg_arc1_event2_pre_beat_02",
            "video": "/tmp/out.mp4",
            "delivery": {"width": 1280, "height": 720},
        })
        + "\n",
        encoding="utf-8",
    )
    parsed = bg_mod._parse_o3_pipeline_result_from_log(log_path)
    assert parsed is not None
    assert parsed.get("ok") is True
    assert parsed.get("video") == "/tmp/out.mp4"


def test_parse_delivery_encode_when_subprocess_crashed_before_done(tmp_path) -> None:
    bg_mod = _import_background()
    delivery = tmp_path / "bg_arc1_event2_pre_beat_30_g1_element_o3_master_delivery.mp4"
    delivery.write_bytes(b"mp4")
    log_path = tmp_path / "crash.log"
    log_path.write_text(
        json.dumps({"phase": "delivery_encode", "dst": str(delivery)})
        + "\nTraceback ... Resource deadlock avoided\n",
        encoding="utf-8",
    )
    parsed = bg_mod._parse_o3_pipeline_result_from_log(log_path)
    assert parsed is not None
    assert parsed.get("video") == str(delivery)


def test_reconcile_errno11_delivery_encode_only(monkeypatch, tmp_path) -> None:
    bg_mod = _import_background()
    delivery = tmp_path / "bg_arc1_event2_pre_beat_30_g1_element_o3_master_delivery.mp4"
    delivery.write_bytes(b"mp4")
    log_path = tmp_path / "job.log"
    log_path.write_text(
        json.dumps({"phase": "starting", "route": "o3_element_native_voice"})
        + "\n"
        + json.dumps({"phase": "delivery_encode", "dst": str(delivery)})
        + "\nOSError: [Errno 11] Resource deadlock avoided\n",
        encoding="utf-8",
    )
    sidecar = {
        "schema_version": 1,
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_2_pre": {
                        "beats": [{
                            "beat_id": "bg_arc1_event2_pre_beat_30",
                            "status": "o3_element_running",
                            "kling_o3_status": "submitted",
                            "kling_o3_voice_fix_status": "o3_running",
                            "kling_o3_voice_fix_job_pid": 1,
                            "kling_o3_voice_fix_job_log_path": str(log_path),
                        }],
                    },
                },
            },
        },
    }
    monkeypatch.setattr(bg_mod, "_pid_is_running", lambda _pid: False)
    monkeypatch.setattr(
        bg_mod,
        "_try_orphan_o3_delivery_recovery",
        lambda beat_id, event_dir, log_path, **kw: {
            "recovered": True,
            "delivery_path": str(delivery),
        },
    )
    changed = bg_mod.reconcile_stuck_o3_voice_beats(sidecar)
    assert changed == 1


def test_finalize_o3_job_after_subprocess_exit_recovers_orphan(tmp_path, monkeypatch) -> None:
    bg_mod = _import_background()
    delivery = tmp_path / "out_delivery.mp4"
    delivery.write_bytes(b"x")
    log_path = tmp_path / "job.log"
    log_path.write_text(
        json.dumps({"phase": "delivery_encode", "dst": str(delivery)})
        + "\nResource deadlock avoided\n",
        encoding="utf-8",
    )
    proc = type("P", (), {"poll": lambda self: 1})()
    job = {
        "status": "running",
        "proc": proc,
        "beat_id": "bg_arc1_event2_pre_beat_30",
        "log_path": str(log_path),
    }
    monkeypatch.setattr(
        bg_mod,
        "_try_orphan_o3_delivery_recovery",
        lambda beat_id, event_dir, log_path, **kw: {
            "recovered": True,
            "delivery_path": str(delivery),
        },
    )
    bg_mod._finalize_o3_job_after_subprocess_exit(job, tmp_path)
    assert job["status"] == "done"
    assert job["result"]["video"] == str(delivery)


def test_element_pipeline_checkpoint_wraps_orphan_recovery():
    text = (TOOLS / "kling_o3_element_beat_pipeline.py").read_text(encoding="utf-8")
    start = text.index("    try:\n        bg_sidecar.persist_o3_delivery_option_checkpoint")
    end = text.index("    now = datetime.now(timezone.utc).isoformat()", start)
    block = text[start:end]
    assert "_recover_orphan" in block or "recover_orphan_o3_delivery" in block


def test_session_state_handler_calls_reconcile() -> None:
    src = (TOOLS / "server_handlers" / "background.py").read_text(encoding="utf-8")
    assert "reconcile_stuck_o3_voice_beats" in src
    assert "handle_bg_session_state" in src


def test_poll_handler_recovers_orphan_when_log_shows_done() -> None:
    src = (TOOLS / "server_handlers" / "background.py").read_text(encoding="utf-8")
    poll_block = src.split("def handle_bg_poll_arlo_o3_voice_status", 1)[1].split("\ndef ", 1)[0]
    assert '"phase": "done"' in poll_block
    assert "_promote_o3_job_from_log_if_terminal" in poll_block


def test_recover_o3_job_from_sidecar_matches_log_path_when_ui_job_id_cleared(
    monkeypatch, tmp_path,
) -> None:
    bg_mod = _import_background()
    delivery = tmp_path / "bg_arc1_event2_pre_beat_03_g4_element_o3_master_delivery.mp4"
    delivery.write_bytes(b"fake mp4")
    log_path = tmp_path / "f9d7dc09_bg_arc1_event2_pre_beat_03.log"
    log_path.write_text(
        json.dumps({"phase": "done", "video": str(delivery), "beat_id": "bg_arc1_event2_pre_beat_03"})
        + "\n",
        encoding="utf-8",
    )
    sidecar = {
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_2_pre": {
                        "beats": [{
                            "beat_id": "bg_arc1_event2_pre_beat_03",
                            "kling_o3_status": "approved",
                            "kling_o3_voice_fix_status": "approved",
                            "kling_o3_video_path": str(delivery),
                            "kling_o3_voice_fix_job_log_path": str(log_path),
                        }],
                    },
                },
            },
        },
    }

    class _FakeBg:
        @staticmethod
        def sidecar_file_lock():
            import contextlib
            return contextlib.nullcontext()

        @staticmethod
        def read_sidecar():
            return sidecar

        @staticmethod
        def _migrate_sidecar(data):
            return data

    monkeypatch.setattr(bg_mod, "_bg_module", lambda: _FakeBg())
    recovered = bg_mod._recover_o3_job_from_sidecar("f9d7dc09")
    assert recovered is not None
    assert recovered["status"] == "done"
    assert recovered["beat_id"] == "bg_arc1_event2_pre_beat_03"
    assert recovered.get("recovered") is True


def test_reconcile_stale_hosting_uses_credentials_not_process_env(monkeypatch, tmp_path) -> None:
    bg_mod = _import_background()
    video = tmp_path / "beat01.mp4"
    video.write_bytes(b"fake-mp4")
    sidecar = {
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_2_pre": {
                        "beats": [{
                            "beat_id": "bg_arc1_event2_pre_beat_01",
                            "kling_o3_status": "approved",
                            "kling_o3_video_path": str(video),
                            "kling_o3_voice_fix_status": "failed_provider_fetch",
                            "kling_o3_voice_fix_error": (
                                "No lipsync input host returned byte-complete public files."
                            ),
                        }],
                    },
                },
            },
        },
    }

    def _ready(*, creds=None, env=None):
        return bool(creds)

    monkeypatch.setattr("lipsync_public_host.lipsync_public_host_ready", _ready)
    monkeypatch.setattr(
        bg_mod,
        "load_credentials",
        lambda: {"r2_access_key_id": "x"},
        raising=False,
    )

    import server_handlers.background as bg_pkg

    monkeypatch.setattr(
        bg_pkg,
        "load_credentials",
        lambda: {"r2_access_key_id": "x"},
        raising=False,
    )

    # Patch import inside reconcile via credentials module path used there
    import sys
    fake_creds = type(sys)("credentials")
    fake_creds.load_credentials = lambda: {"r2_access_key_id": "x"}
    monkeypatch.setitem(sys.modules, "credentials", fake_creds)

    changed = bg_mod.reconcile_stale_lipsync_hosting_failures(sidecar)
    beat = sidecar["arcs"]["arc_1"]["segments"]["event_2_pre"]["beats"][0]
    assert changed == 1
    assert beat["kling_o3_voice_fix_status"] == "approved"


def test_reconcile_clears_stale_lipsync_hosting_failure_when_r2_ready(
    monkeypatch, tmp_path,
) -> None:
    bg_mod = _import_background()
    video = tmp_path / "beat01.mp4"
    video.write_bytes(b"fake-mp4")
    sidecar = {
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_2_pre": {
                        "beats": [{
                            "beat_id": "bg_arc1_event2_pre_beat_01",
                            "kling_o3_status": "approved",
                            "kling_o3_video_path": str(video),
                            "kling_o3_voice_fix_status": "failed_provider_fetch",
                            "kling_o3_voice_fix_error": (
                                "No lipsync input host returned byte-complete public files. "
                                "r2_cdn: unavailable or preflight failed"
                            ),
                        }],
                    },
                },
            },
        },
    }
    monkeypatch.setattr(
        "lipsync_public_host.lipsync_public_host_ready",
        lambda **_: True,
    )
    changed = bg_mod.reconcile_stale_lipsync_hosting_failures(sidecar)
    beat = sidecar["arcs"]["arc_1"]["segments"]["event_2_pre"]["beats"][0]
    assert changed == 1
    assert beat["kling_o3_voice_fix_status"] == "approved"
    assert "kling_o3_voice_fix_error" not in beat


def test_recover_o3_job_from_sidecar_failed_provider_fetch(
    monkeypatch, tmp_path,
) -> None:
    bg_mod = _import_background()
    log_path = tmp_path / "1e0c92f8_bg_arc1_event2_pre_beat_01.log"
    log_path.write_text("Traceback...\n", encoding="utf-8")
    sidecar = {
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_2_pre": {
                        "beats": [{
                            "beat_id": "bg_arc1_event2_pre_beat_01",
                            "kling_o3_status": "approved",
                            "kling_o3_voice_fix_status": "failed_provider_fetch",
                            "kling_o3_voice_fix_error": (
                                'WaveSpeed response missing job id: '
                                '{"code": 400, "message": "unsafe url: non-public host"}'
                            ),
                            "kling_o3_voice_fix_ui_job_id": "1e0c92f8",
                            "kling_o3_voice_fix_job_log_path": str(log_path),
                        }],
                    },
                },
            },
        },
    }

    class _FakeBg:
        @staticmethod
        def sidecar_file_lock():
            import contextlib
            return contextlib.nullcontext()

        @staticmethod
        def read_sidecar():
            return sidecar

        @staticmethod
        def write_sidecar(data):
            pass

        @staticmethod
        def _migrate_sidecar(data):
            return data

    monkeypatch.setattr(bg_mod, "_bg_module", lambda: _FakeBg())
    recovered = bg_mod._recover_o3_job_from_sidecar("1e0c92f8")
    assert recovered is not None
    assert recovered["status"] == "failed"
    assert "non-public" in recovered["error"].lower() or "localhost" in recovered["error"].lower()
