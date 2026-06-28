"""Dropbox errno 11/35 sidecar I/O + orphan O3 delivery recovery."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import beat_generator as bg
import lib.ffmpeg_io as fio


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


def test_copy_file_durable_retries_errno11(monkeypatch, tmp_path: Path) -> None:
    src = tmp_path / "src.bin"
    dst = tmp_path / "dst.bin"
    src.write_bytes(b"pose-bytes")
    calls = {"n": 0}
    real_chunked = fio._copy_file_chunked

    def flaky_chunked(s, d, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError(11, "Resource deadlock avoided")
        return real_chunked(s, d, **kwargs)

    monkeypatch.setattr(fio, "_copy_file_chunked", flaky_chunked)
    monkeypatch.setattr(bg.time, "sleep", lambda _s: None)
    bg.copy_file_durable(src, dst)
    assert dst.read_bytes() == b"pose-bytes"
    assert calls["n"] == 2


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


def test_persist_o3_delivery_option_checkpoint_raises_on_attempt_race(
    monkeypatch, tmp_path: Path,
) -> None:
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
                                "speaker": "Lorelai",
                                "kling_o3_voice_fix_attempt_id": "other-attempt",
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
    delivery = tmp_path / "clip_delivery.mp4"
    delivery.write_bytes(b"mp4")
    with pytest.raises(RuntimeError, match="checkpoint persist failed"):
        bg.persist_o3_delivery_option_checkpoint(
            "bg_arc1_event2_pre_beat_27",
            video_path=str(delivery),
            slot_index=0,
            label="g10 O3 Element voice",
            o3_voice_binding={"element_id": "e1", "kling_voice_id": "v1"},
            attempt_id="expected-attempt",
            generation=10,
            ui_job_id="fcbb17fe",
        )


def test_persist_o3_delivery_option_checkpoint_paid_bypass_when_attempt_cleared(
    monkeypatch, tmp_path: Path,
) -> None:
    sidecar_path = tmp_path / "beat_generator_state.json"
    sidecar_path.write_text(
        json.dumps({
            "schema_version": 1,
            "arcs": {
                "arc_1": {
                    "segments": {
                        "event_3_pre": {
                            "beats": [{
                                "beat_id": "bg_arc1_event3_pre_beat_02",
                                "speaker": "Ember",
                                "kling_o3_voice_fix_attempt_id": None,
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
    delivery = tmp_path / "bg_arc1_event3_pre_beat_02_g5_element_o3_master_delivery.mp4"
    delivery.write_bytes(b"mp4")
    monkeypatch.setenv("MN_O3_ATTEMPT_ID", "9c33cbb48d6f458c9bfdcb147b5d9d9a")
    bg.persist_o3_delivery_option_checkpoint(
        "bg_arc1_event3_pre_beat_02",
        video_path=str(delivery),
        slot_index=0,
        label="g5 O3 Element voice",
        o3_voice_binding={"element_id": "e1", "kling_voice_id": "v1"},
        attempt_id="9c33cbb48d6f458c9bfdcb147b5d9d9a",
        generation=5,
        ui_job_id="fcbb17fe",
    )
    live = json.loads(sidecar_path.read_text(encoding="utf-8"))
    beat = live["arcs"]["arc_1"]["segments"]["event_3_pre"]["beats"][0]
    assert beat["kling_o3_generation"] == 5
    assert any(
        str(o.get("video_path") or "") == str(delivery)
        for o in beat.get("kling_o3_options") or []
        if isinstance(o, dict)
    )


def test_assign_kling_o3_option_syncs_top_level_generation() -> None:
    beat = {
        "beat_id": "bg_arc1_event2_pre_beat_03",
        "kling_o3_generation": 7,
        "kling_o3_options": [],
    }
    bg.assign_kling_o3_option_to_slot(
        beat,
        0,
        video_path="/clips/bg_arc1_event2_pre_beat_03_g8_element_o3_master_delivery.mp4",
        label="g8 O3 Element voice",
        source="kling_o3_element_native_voice",
        now="2026-06-16T00:00:00+00:00",
        make_active=True,
    )
    assert beat["kling_o3_generation"] == 8


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


def test_recover_orphan_reasserts_intent_char_and_bg_refs(tmp_path: Path, monkeypatch) -> None:
    """Beat 03 class — orphan recovery must not leave stale sidecar refs after intent job."""
    import beat_generator as bg

    event_dir = tmp_path / "Event_2"
    clips = event_dir / "kling_o3_clips"
    clips.mkdir(parents=True)
    jobs = event_dir / "arlo_o3_jobs"
    jobs.mkdir(parents=True)
    delivery = clips / "bg_arc1_event2_pre_beat_03_g9_element_o3_master_delivery.mp4"
    delivery.write_bytes(b"mp4")
    operator_char = tmp_path / "operator_char.png"
    operator_bg = tmp_path / "operator_bg.png"
    stale_char = tmp_path / "stale_char.png"
    operator_char.write_bytes(b"op-char")
    operator_bg.write_bytes(b"op-bg")
    stale_char.write_bytes(b"stale")
    job_id = "0dfbc46f"
    (jobs / f"{job_id}_intent.json").write_text(
        json.dumps({
            "schema_version": 1,
            "job_id": job_id,
            "visual": {
                "char_ref_abs_path": str(operator_char),
                "bg_ref_abs_path": str(operator_bg),
                "reference_image_locked": True,
                "bg_ref_image_locked": True,
            },
        }),
        encoding="utf-8",
    )
    log_path = jobs / f"{job_id}_bg_arc1_event2_pre_beat_03.log"
    log_path.write_text(
        json.dumps({"phase": "done", "beat_id": "bg_arc1_event2_pre_beat_03", "video": str(delivery)})
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
                                "beat_id": "bg_arc1_event2_pre_beat_03",
                                "speaker": "Lorelai",
                                "status": "o3_element_running",
                                "kling_o3_status": "submitted",
                                "kling_o3_generation": 9,
                                "reference_image": {"abs_path": str(stale_char)},
                                "bg_ref_image": {"abs_path": str(stale_char)},
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
        "bg_arc1_event2_pre_beat_03",
        event_dir,
        log_path=log_path,
        make_active=True,
    )
    assert result.get("recovered") is True
    beat = json.loads(sidecar_path.read_text(encoding="utf-8"))["arcs"]["arc_1"]["segments"]["event_2_pre"]["beats"][0]
    assert beat["reference_image"]["abs_path"] == str(operator_char)
    assert beat["bg_ref_image"]["abs_path"] == str(operator_bg)
    assert beat["reference_image_locked"] is True
    assert beat["bg_ref_image_locked"] is True


def test_sidecar_io_transient_errnos_include_11_and_35() -> None:
    assert 11 in bg._SIDECAR_IO_TRANSIENT_ERRNOS
    assert 35 in bg._SIDECAR_IO_TRANSIENT_ERRNOS


def test_sidecar_io_transient_helper() -> None:
    assert bg.sidecar_io_transient(OSError(11, "Resource deadlock avoided"))
    assert bg.sidecar_io_transient(OSError(35, "Resource temporarily unavailable"))
    assert not bg.sidecar_io_transient(OSError(2, "No such file"))
    assert not bg.sidecar_io_transient(ValueError("nope"))
