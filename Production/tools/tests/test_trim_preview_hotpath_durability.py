"""Trim preview hot path — no Dropbox audit / heavy migrate / basename miss class."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import beat_generator as bg  # noqa: E402
from server_handlers import background as bgh  # noqa: E402

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


def test_trim_handler_preview_uses_light_migrate_only():
    block = _handler_block("handle_bg_kling_o3_trim")
    assert '_migrate_sidecar(sidecar, heavy_heal=False)' in block
    assert '_migrate_sidecar(sidecar_snap, heavy_heal=False)' in block
    # Must not call bare heavy migrate on this hot path.
    assert "_migrate_sidecar(sidecar)" not in block.replace(
        "_migrate_sidecar(sidecar, heavy_heal=False)", ""
    )
    assert "_migrate_sidecar(sidecar_snap)" not in block.replace(
        "_migrate_sidecar(sidecar_snap, heavy_heal=False)", ""
    )


def test_trim_audit_writes_local_state_not_dropbox_event_dir():
    text = BACKGROUND.read_text(encoding="utf-8")
    audit_block = text.split("def _bg_o3_trim_audit(", 1)[1].split("\ndef ", 1)[0]
    assert "_bg_o3_trim_audit_log_path" in audit_block
    assert 'event_dir / "_bg_o3_trim_audit.jsonl"' not in audit_block
    assert "MN_STATE_ROOT" in text.split("def _bg_o3_trim_audit_log_path", 1)[1].split(
        "\ndef ", 1
    )[0]


def test_find_o3_option_by_basename_matches_absolute_option(tmp_path: Path):
    master = tmp_path / "kling_o3_clips" / "bg_arc1_event6_pre_beat_19_g1_element_o3_master_delivery.mp4"
    master.parent.mkdir(parents=True)
    master.write_bytes(b"x" * 64)
    beat = {
        "beat_id": "bg_arc1_event6_pre_beat_19",
        "kling_o3_options": [
            {
                "slot_index": 0,
                "video_path": str(master),
                "generation": 1,
            }
        ],
    }
    hit = bg.find_o3_option_by_video_path(beat, master.name)
    assert hit is not None
    assert hit["video_path"] == str(master)


def test_find_ui_trim_preview_by_window_ignores_clip_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    hot = tmp_path / "hot"
    monkeypatch.setenv("MN_MEDIA_HOT_ROOT", str(hot))
    event = tmp_path / "Library" / "CloudStorage" / "Dropbox" / "P" / "Event_6"
    event.mkdir(parents=True)
    scratch = bg.kling_o3_trim_scratch_dir(event)
    warm = scratch / "bg_arc1_event6_pre_beat_19_g1_deadbeef_s2.24_b0.42_ui_preview.mp4"
    warm.write_bytes(b"preview" * 400)
    found = bg.find_kling_o3_ui_trim_preview_by_window(
        "bg_arc1_event6_pre_beat_19",
        event,
        trim_start=2.24,
        trim_back=0.42,
    )
    assert found == warm


def test_audit_log_path_under_state_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MN_STATE_ROOT", str(tmp_path / "state"))
    path = bgh._bg_o3_trim_audit_log_path("Event_6")
    assert path == tmp_path / "state" / "logs" / "Event_6" / "_bg_o3_trim_audit.jsonl"
    assert path.parent.is_dir()
    assert "CloudStorage" not in str(path)
    assert "Dropbox" not in str(path)
