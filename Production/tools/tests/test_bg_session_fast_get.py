"""BG session-state fast GET — SQLite read path without per-beat Dropbox scans."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import beat_generator as bg
from server_handlers import background as bg_handlers

TOOLS = Path(__file__).resolve().parent.parent
BACKGROUND = TOOLS / "server_handlers" / "background.py"


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


def test_session_state_calls_job_busy_read_only() -> None:
    block = _handler_block("handle_bg_session_state")
    assert "_enrich_beats_job_busy(beats, _data_root(h), h, session_read_only=True)" in block


def test_enrich_beats_job_busy_session_read_only_skips_stale_close() -> None:
    enrich = BACKGROUND.read_text(encoding="utf-8").split(
        "def _enrich_beats_job_busy", 1
    )[1].split("\ndef ", 1)[0]
    assert "session_read_only" in enrich
    assert "not session_read_only" in enrich


def test_kling_o3_trim_persist_uses_sidecar_lock() -> None:
    block = _handler_block("handle_bg_kling_o3_trim")
    assert "update_beat_locked(beat_id, _commit_trim" in block
    assert "mutate_sidecar_locked(_flush_trim_sidecar" not in block
    assert "bg.write_sidecar(sidecar)" not in block


def test_session_state_skips_milestone_sidecar_repair_on_get() -> None:
    block = _handler_block("handle_bg_session_state")
    assert "repair_sidecar=False" in block


def test_session_read_enrich_skips_disk_scan(tmp_path: Path) -> None:
    beat_id = "bg_arc1_event2_pre_beat_04"
    clips = tmp_path / "kling_o3_clips"
    clips.mkdir()
    delivery = clips / f"{beat_id}_g7_element_o3_master_delivery.mp4"
    delivery.write_bytes(b"mp4")
    beat = {
        "beat_id": beat_id,
        "kling_o3_video_path": str(delivery),
        "kling_o3_options": [
            {
                "key": f"{beat_id}_o3_video_f134ae1fe6",
                "video_path": str(delivery),
                "video_path_exists": True,
            }
        ],
        "kling_o3_disk_delivery_count": 7,
        "kling_o3_orphan_delivery_count": 0,
        "kling_o3_clips_dir": str(clips),
        "kling_o3_pinned_preserve": False,
        "kling_o3_video_path_exists": True,
        "kling_o3_disk_enrich_at": "2026-06-22T12:00:00+00:00",
    }
    disk_called = False
    exists_called = False

    def _fake_list(*_a, **_k):
        nonlocal disk_called
        disk_called = True
        return []

    def _fake_exists(_p):
        nonlocal exists_called
        exists_called = True
        return True

    with patch.object(bg, "list_o3_element_delivery_paths_on_disk", _fake_list):
        with patch.object(bg, "_kling_o3_video_path_exists", _fake_exists):
            out = bg.enrich_beat_kling_o3_pinned(beat, tmp_path, session_read=True)

    assert not disk_called
    assert not exists_called
    assert out["kling_o3_disk_delivery_count"] == 7
    assert out["kling_o3_options"][0]["video_path_exists"] is True


def test_materialize_and_persist_after_reconcile(tmp_path: Path) -> None:
    beat_id = "bg_arc1_event2_pre_beat_01"
    clips = tmp_path / "kling_o3_clips"
    clips.mkdir()
    delivery = clips / f"{beat_id}_g1_element_o3_master_delivery.mp4"
    delivery.write_bytes(b"mp4")
    beat = {
        "beat_id": beat_id,
        "kling_o3_options": [],
        "kling_o3_video_path": "",
    }
    changed = bg.reconcile_o3_disk_deliveries_for_beat(beat, tmp_path)
    assert changed
    assert beat.get("kling_o3_disk_delivery_count") == 1
    assert beat.get("kling_o3_disk_enrich_at")
    opts = beat.get("kling_o3_options") or []
    assert len(opts) == 1
    assert opts[0].get("video_path_exists") is True


def test_session_read_skips_refresh_slot_layout(tmp_path: Path) -> None:
    beat = {
        "beat_id": "bg_arc1_event2_pre_beat_04",
        "kling_o3_options": [{"video_path": str(tmp_path / "x.mp4"), "generation": 1}],
    }
    called = False

    def _fake_refresh(_beat: dict) -> bool:
        nonlocal called
        called = True
        return False

    with patch.object(bg, "refresh_o3_ui_slot_layout", _fake_refresh):
        bg.enrich_beat_kling_o3_pinned(beat, tmp_path, session_read=True)
    assert not called


def test_default_enrich_still_scans_disk(tmp_path: Path) -> None:
    beat_id = "bg_arc1_event2_pre_beat_02"
    clips = tmp_path / "kling_o3_clips"
    clips.mkdir()
    delivery = clips / f"{beat_id}_g2_element_o3_master_delivery.mp4"
    delivery.write_bytes(b"mp4")
    beat = {
        "beat_id": beat_id,
        "kling_o3_options": [{"video_path": str(delivery)}],
        "kling_o3_video_path": str(delivery),
    }
    disk_called = False

    def _fake_list(*_a, **_k):
        nonlocal disk_called
        disk_called = True
        return [delivery]

    with patch.object(bg, "list_o3_element_delivery_paths_on_disk", _fake_list):
        out = bg.enrich_beat_kling_o3_pinned(beat, tmp_path, session_read=False)

    assert disk_called
    assert out.get("kling_o3_disk_delivery_count") == 1
