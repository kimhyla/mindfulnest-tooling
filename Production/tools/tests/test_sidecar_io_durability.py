"""Dropbox errno 11/35 sidecar I/O + orphan O3 delivery recovery."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import beat_generator as bg


def test_read_json_file_durable_retries_errno11(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "sidecar.json"
    path.write_text('{"schema_version": 1, "arcs": {}}', encoding="utf-8")
    calls = {"n": 0}
    real_copy = bg._copy_file_chunked

    def flaky_copy(src, dst, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError(11, "Resource deadlock avoided")
        return real_copy(src, dst)

    monkeypatch.setattr(bg, "_copy_file_chunked", flaky_copy)
    monkeypatch.setattr(bg.time, "sleep", lambda _s: None)
    data = bg._read_json_file_durable(str(path))
    assert data.get("schema_version") == 1
    assert calls["n"] == 2


def test_read_json_file_durable_avoids_shutil_copy2(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "sidecar.json"
    path.write_text('{"ok": true}', encoding="utf-8")

    def copy2_should_not_run(*_a, **_k):
        raise AssertionError("shutil.copy2 must not be used for Dropbox sidecar reads")

    monkeypatch.setattr(bg.shutil, "copy2", copy2_should_not_run)
    assert bg._read_json_file_durable(str(path)) == {"ok": True}


def test_update_beat_locked_retries_transient_sidecar_io(monkeypatch, tmp_path: Path) -> None:
    sidecar_path = tmp_path / "beat_generator_state.json"
    sidecar_path.write_text(
        json.dumps({
            "schema_version": 1,
            "arcs": {
                "arc_1": {
                    "segments": {
                        "event_2_pre": {
                            "beats": [{"beat_id": "bg_test", "speaker": "Lorelai", "status": "draft"}],
                        },
                    },
                },
            },
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(bg, "BG_SIDECAR_PATH", str(sidecar_path))
    calls = {"n": 0}
    real_write = bg.write_sidecar

    def flaky_write(data):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError(11, "Resource deadlock avoided")
        return real_write(data)

    monkeypatch.setattr(bg, "write_sidecar", flaky_write)
    monkeypatch.setattr(bg.time, "sleep", lambda _s: None)

    def apply(beat, _sidecar):
        beat["status"] = "approved"

    ok, beat = bg.update_beat_locked("bg_test", apply)
    assert ok is True
    assert beat["status"] == "approved"
    assert calls["n"] == 2


def test_write_sidecar_retries_errno11(monkeypatch, tmp_path: Path) -> None:
    sidecar_path = tmp_path / "beat_generator_state.json"
    monkeypatch.setattr(bg, "BG_SIDECAR_PATH", str(sidecar_path))
    calls = {"n": 0}
    real_replace = bg.os.replace

    def flaky_replace(src, dst):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError(11, "Resource deadlock avoided")
        return real_replace(src, dst)

    monkeypatch.setattr(bg.os, "replace", flaky_replace)
    monkeypatch.setattr(bg.time, "sleep", lambda _s: None)
    payload = {"schema_version": 1, "arcs": {}}
    bg.write_sidecar(payload)
    assert sidecar_path.is_file()
    assert json.loads(sidecar_path.read_text(encoding="utf-8"))["schema_version"] == 1
    assert calls["n"] == 2


def test_recover_orphan_o3_delivery_from_log(tmp_path: Path, monkeypatch) -> None:
    event_dir = tmp_path / "Event_2"
    clips = event_dir / "kling_o3_clips"
    clips.mkdir(parents=True)
    delivery = clips / "bg_arc1_event2_pre_beat_27_g10_element_o3_master_delivery.mp4"
    delivery.write_bytes(b"mp4")
    log_path = event_dir / "arlo_o3_jobs" / "759cb825_beat_27.log"
    log_path.parent.mkdir(parents=True)
    log_path.write_text(
        json.dumps({"phase": "delivery_encode", "dst": str(delivery)})
        + "\n"
        + json.dumps({"phase": "done", "beat_id": "bg_arc1_event2_pre_beat_27", "video": str(delivery)})
        + "\n",
        encoding="utf-8",
    )
    sidecar_path = tmp_path / "beat_generator_state.json"
    sidecar_path.write_text(
        json.dumps({
            "schema_version": 1,
            "arcs": {
                "arc_1": {
                    "segments": {
                        "event_2_pre": {
                            "beats": [{
                                "beat_id": "bg_arc1_event2_pre_beat_27",
                                "speaker": "Loral",
                                "status": "o3_element_running",
                                "kling_o3_status": "submitted",
                                "kling_o3_generation": 10,
                                "kling_o3_voice_fix_status": "failed",
                                "kling_o3_voice_fix_error": "OSError: [Errno 11] Resource deadlock avoided",
                                "kling_o3_options": [None, None, None],
                            }],
                        },
                    },
                },
            },
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(bg, "BG_SIDECAR_PATH", str(sidecar_path))
    monkeypatch.setenv("MN_PROD_ROOT", str(tmp_path))
    result = bg.recover_orphan_o3_delivery(
        "bg_arc1_event2_pre_beat_27",
        event_dir,
        log_path=log_path,
        make_active=True,
    )
    assert result.get("recovered") is True
    beat = json.loads(sidecar_path.read_text(encoding="utf-8"))["arcs"]["arc_1"]["segments"]["event_2_pre"]["beats"][0]
    assert beat["kling_o3_status"] == "approved"
    assert beat["kling_o3_video_path"] == str(delivery)
    assert beat.get("kling_o3_voice_fix_error") is None


def test_sidecar_io_transient_errnos_include_11_and_35() -> None:
    assert 11 in bg._SIDECAR_IO_TRANSIENT_ERRNOS
    assert 35 in bg._SIDECAR_IO_TRANSIENT_ERRNOS


def test_sidecar_io_transient_helper() -> None:
    assert bg.sidecar_io_transient(OSError(11, "Resource deadlock avoided"))
    assert bg.sidecar_io_transient(OSError(35, "Resource temporarily unavailable"))
    assert not bg.sidecar_io_transient(OSError(2, "No such file"))
    assert not bg.sidecar_io_transient(ValueError("nope"))
