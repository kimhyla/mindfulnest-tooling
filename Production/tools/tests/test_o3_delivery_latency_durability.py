"""O3 delivery latency — session/poll/submit hot paths must not block subprocess checkpoints."""
from __future__ import annotations

import json
import re
from pathlib import Path

import beat_generator as bg

BACKGROUND = Path(__file__).resolve().parent.parent / "server_handlers" / "background.py"
VIDEO_DELIVERY = Path(__file__).resolve().parent.parent / "video_delivery.py"


def _handler_block(name: str) -> str:
    text = BACKGROUND.read_text(encoding="utf-8")
    start = text.index(f"def {name}(")
    rest = text[start + 1 :]
    end_offset = len(rest)
    for marker in ("\ndef handle_", "\ndef _finalize", "\ndef _run_o3"):
        idx = rest.find(marker)
        if idx >= 0:
            end_offset = min(end_offset, idx)
    return text[start : start + 1 + end_offset]


def test_session_state_skips_full_migrate_and_wavespeed_heal():
    block = _handler_block("handle_bg_session_state")
    assert "ensure_sidecar_schema_defaults(sidecar)" in block
    assert "reconcile_stale_o3_intent_locks_all_events" not in block
    assert "maybe_auto_register_beat_char_ref" not in block


def test_session_state_disk_reconcile_force_only():
    text = BACKGROUND.read_text(encoding="utf-8")
    assert "if force_reconcile_o3 and event_dir.is_dir():" in text
    assert "reconcile_kling_o3_sidecar" in text


def test_submit_uses_fast_sidecar_read_and_update_beat_locked_for_pid():
    block = _handler_block("handle_bg_submit_arlo_o3_voice")
    intent_idx = block.index("build_generation_intent(")
    commit_idx = block.index("update_beat_locked(")
    assert intent_idx < commit_idx
    assert "read_sidecar_for_poll_snapshot" in block
    assert "update_beat_locked(" in block
    assert block.count("_migrate_sidecar(sidecar)") == 0


def test_poll_throttles_metadata_and_tails_log():
    block = _handler_block("handle_bg_poll_arlo_o3_voice_status")
    poll_helpers = BACKGROUND.read_text(encoding="utf-8")
    assert "_O3_JOB_METADATA_STAMP_INTERVAL_S" in poll_helpers
    assert "_tail_read_text" in poll_helpers
    assert "load_intent_terminal" in block
    assert "read_sidecar_for_poll_snapshot" in poll_helpers


def test_poll_beat_snapshot_does_not_require_exclusive_lock():
    text = BACKGROUND.read_text(encoding="utf-8")
    snap_block = text.split("def _enriched_beat_snapshot_for_o3_poll", 1)[1].split("\ndef ", 1)[0]
    assert "read_sidecar_for_poll_snapshot" in snap_block


def test_ensure_o3_job_metadata_throttled_and_update_beat_locked():
    block = _handler_block("_ensure_o3_job_metadata")
    assert "_O3_JOB_METADATA_STAMP_INTERVAL_S" in block
    assert "update_beat_locked(" in block


def test_parse_o3_pipeline_result_from_log_supports_tail_only():
    bg_mod = __import__(
        "server_handlers.background",
        fromlist=["_parse_o3_pipeline_result_from_log", "_tail_read_text"],
    )
    log = Path(__file__).parent / "_tmp_o3_tail.log"
    head = json.dumps({"phase": "starting", "beat_id": "bg_arc1_event1_pre_beat_01"}) + "\n"
    tail = json.dumps(
        {
            "phase": "done",
            "beat_id": "bg_arc1_event1_pre_beat_01",
            "video": "/tmp/delivery.mp4",
        }
    ) + "\n"
    log.write_text("x" * 20000 + head + tail, encoding="utf-8")
    try:
        parsed = bg_mod._parse_o3_pipeline_result_from_log(log, tail_bytes=4096)
        assert parsed and parsed.get("video") == "/tmp/delivery.mp4"
    finally:
        log.unlink(missing_ok=True)


def test_migrate_sidecar_heal_trim_optional(monkeypatch):
    sidecar = {
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_1_pre": {
                        "beats": [
                            {
                                "beat_id": "bg_arc1_event1_pre_beat_01",
                                "kling_o3_video_path": "/fake.mp4",
                                "kling_o3_trim_start": 99.0,
                            }
                        ],
                    },
                },
            },
        },
    }
    calls: list[str] = []

    def _fake_heal(beat: dict) -> bool:
        calls.append(str(beat.get("beat_id")))
        return False

    monkeypatch.setattr(bg, "heal_invalid_kling_o3_trim", _fake_heal)
    bg._migrate_sidecar(sidecar, heal_trim=False, heavy_heal=False)
    assert calls == []


def test_delivery_encode_stages_ffmpeg_output_locally():
    """L1 — O3 delivery encode must not write growing tmp files on Dropbox."""
    text = VIDEO_DELIVERY.read_text(encoding="utf-8")
    delivery_block = text.split("def encode_delivery_video", 1)[1].split("\ndef ", 1)[0]
    lipsync_block = text.split("def encode_lipsync_input", 1)[1].split("\ndef ", 1)[0]
    for block in (delivery_block, lipsync_block):
        assert "local_staging_temp_path" in block
        assert "commit_local_file_to_dest" in block
        assert ".tmp." not in block or "dst.stem}.tmp" not in block
    assert "from lib.ffmpeg_io import" in text


def test_delivery_encode_uses_medium_preset():
    text = VIDEO_DELIVERY.read_text(encoding="utf-8")
    block = text.split("def _run_single_delivery_encode", 1)[1].split("\ndef ", 1)[0]
    assert re.search(r'"-preset", "medium"', block)


def test_stuck_reconcile_skips_idle_beats(monkeypatch):
    bg_mod = __import__(
        "server_handlers.background",
        fromlist=["reconcile_stuck_o3_voice_beats"],
    )
    sidecar = {
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_1_pre": {
                        "beats": [
                            {
                                "beat_id": "bg_arc1_event1_pre_beat_01",
                                "status": "draft",
                                "kling_o3_voice_fix_status": "",
                            },
                            {
                                "beat_id": "bg_arc1_event1_pre_beat_02",
                                "status": "approved",
                                "kling_o3_status": "approved",
                                "kling_o3_voice_fix_status": "approved",
                                "kling_o3_voice_fix_job_pid": 99999,
                            },
                        ],
                    },
                },
            },
        },
    }
    monkeypatch.setattr(bg_mod, "_pid_is_running", lambda _pid: False)
    changed = bg_mod.reconcile_stuck_o3_voice_beats(sidecar)
    assert changed == 1
    assert sidecar["arcs"]["arc_1"]["segments"]["event_1_pre"]["beats"][0]["status"] == "draft"
