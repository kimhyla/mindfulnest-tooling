"""O3 trim must not survive clip swaps when it exceeds the new clip duration."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import beat_generator as bg


def test_heal_invalid_kling_o3_trim_clears_when_back_exceeds_duration(tmp_path: Path):
    clip = tmp_path / "short.mp4"
    clip.write_bytes(b"x")
    beat = {
        "beat_id": "bg_arc1_event2_pre_beat_18",
        "kling_o3_video_path": str(clip),
        "kling_o3_trim_start": 0.0,
        "kling_o3_trim_back": 7.0,
    }
    with patch.object(bg, "_ffprobe_duration", return_value=6.04):
        assert bg.heal_invalid_kling_o3_trim(beat) is True
    assert "kling_o3_trim_back" not in beat
    assert "kling_o3_trim_start" not in beat


def test_heal_invalid_kling_o3_trim_keeps_valid_window(tmp_path: Path):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"x")
    beat = {
        "kling_o3_video_path": str(clip),
        "kling_o3_trim_start": 0.5,
        "kling_o3_trim_back": 1.0,
    }
    with patch.object(bg, "_ffprobe_duration", return_value=8.0):
        assert bg.heal_invalid_kling_o3_trim(beat) is False
    assert beat.get("kling_o3_trim_back") == 1.0


def test_heal_invalid_kling_o3_trim_clears_when_front_exceeds_duration(tmp_path: Path):
    clip = tmp_path / "short.mp4"
    clip.write_bytes(b"x")
    beat = {
        "kling_o3_video_path": str(clip),
        "kling_o3_trim_start": 6.5,
        "kling_o3_trim_back": None,
    }
    with patch.object(bg, "_ffprobe_duration", return_value=6.04):
        assert bg.heal_invalid_kling_o3_trim(beat) is True
    assert "kling_o3_trim_start" not in beat


def test_set_kling_o3_beat_trim_second_front_apply_updates_sidecar(tmp_path: Path):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"x")
    beat = {
        "kling_o3_video_path": str(clip),
        "kling_o3_trim_start": 1.0,
        "kling_o3_trim_back": 0.5,
    }
    with patch.object(bg, "_ffprobe_duration", return_value=8.0):
        bg.set_kling_o3_beat_trim(beat, trim_start=2.5, trim_back=0.5)
    assert beat["kling_o3_trim_start"] == 2.5
    assert beat["kling_o3_trim_back"] == 0.5


def test_assign_kling_o3_option_heals_stale_trim(tmp_path: Path):
    short = tmp_path / "g9_delivery.mp4"
    short.write_bytes(b"x")
    beat = {
        "beat_id": "bg_arc1_event2_pre_beat_18",
        "kling_o3_video_path": str(tmp_path / "old_long.mp4"),
        "kling_o3_trim_start": 0.0,
        "kling_o3_trim_back": 7.0,
        "kling_o3_options": [],
    }
    (tmp_path / "old_long.mp4").write_bytes(b"y")
    with patch.object(bg, "_ffprobe_duration", return_value=6.04):
        with patch.object(bg, "event_dir_for_beat_id", return_value=tmp_path):
            bg.assign_kling_o3_option_to_slot(
                beat,
                0,
                video_path=str(short),
                label="g9 O3 Element voice",
                source="kling_o3_element_native_voice",
                now="2026-06-16T18:00:00+00:00",
                make_active=True,
            )
    assert "kling_o3_trim_back" not in beat


def test_trim_scratch_token_changes_when_front_trim_changes():
    beat = {
        "kling_o3_generation": 9,
        "kling_o3_trim_start": 1.0,
        "kling_o3_trim_back": 2.0,
    }
    t1 = bg.kling_o3_trim_scratch_token(beat)
    beat["kling_o3_trim_start"] = 2.5
    t2 = bg.kling_o3_trim_scratch_token(beat)
    assert t1 != t2
    assert t1 == "s1.0_b2.0"
    assert t2 == "s2.5_b2.0"


def test_ui_trim_preview_path_unique_per_front_trim(tmp_path: Path):
    beat_id = "bg_arc1_event2_pre_beat_10"
    beat_a = {
        "kling_o3_generation": 3,
        "kling_o3_trim_start": 1.0,
        "kling_o3_trim_back": 0.0,
    }
    beat_b = {**beat_a, "kling_o3_trim_start": 2.0}
    path_a = bg.kling_o3_ui_trim_preview_path(beat_id, tmp_path, beat_a)
    path_b = bg.kling_o3_ui_trim_preview_path(beat_id, tmp_path, beat_b)
    assert path_a != path_b
    assert path_a.name == f"{beat_id}_g3_s1.0_b0.0_ui_preview.mp4"


def test_export_trim_path_includes_trim_token(tmp_path: Path):
    clip = tmp_path / "source.mp4"
    clip.write_bytes(b"x")
    beat = {
        "beat_id": "bg_arc1_event2_pre_beat_10",
        "kling_o3_generation": 3,
        "kling_o3_video_path": str(clip),
        "kling_o3_trim_start": 1.5,
        "kling_o3_trim_back": 0.5,
    }
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    with patch.object(bg, "_ffprobe_duration", return_value=8.0):
        with patch.object(bg, "materialize_kling_o3_trimmed_clip") as mat:
            mat.side_effect = lambda beat, dest, **kw: dest
            dest = bg._kling_o3_export_clip_path(beat, tmp_path, scratch)
    assert dest.name == "bg_arc1_event2_pre_beat_10_g3_s1.5_b0.5_export_trim.mp4"


def test_invalidate_kling_o3_trim_scratch_removes_preview_and_export(tmp_path: Path):
    beat_id = "bg_arc1_event2_pre_beat_10"
    scratch = tmp_path / "assembled" / "_kling_o3_trim_scratch"
    scratch.mkdir(parents=True)
    legacy = scratch / f"{beat_id}_ui_trim_preview.mp4"
    preview = scratch / f"{beat_id}_g3_s1.0_b2.0_ui_preview.mp4"
    export = scratch / f"{beat_id}_g3_s1.0_b2.0_export_trim.mp4"
    keep = scratch / f"{beat_id}_magic_still_tts_v1.mp4"
    for p in (legacy, preview, export, keep):
        p.write_bytes(b"x")
    bg.invalidate_kling_o3_trim_scratch(beat_id, tmp_path)
    assert not legacy.is_file()
    assert not preview.is_file()
    assert not export.is_file()
    assert keep.is_file()


def test_prune_stale_kling_o3_trim_scratch_keeps_current_token(tmp_path: Path):
    beat_id = "bg_arc1_event2_pre_beat_10"
    scratch = tmp_path / "assembled" / "_kling_o3_trim_scratch"
    scratch.mkdir(parents=True)
    beat = {
        "kling_o3_generation": 3,
        "kling_o3_trim_start": 2.0,
        "kling_o3_trim_back": 1.0,
    }
    old = scratch / f"{beat_id}_g3_s1.0_b1.0_ui_preview.mp4"
    legacy = scratch / f"{beat_id}_ui_trim_preview.mp4"
    current = bg.kling_o3_ui_trim_preview_path(beat_id, tmp_path, beat)
    for p in (old, legacy, current):
        p.write_bytes(b"x")
    removed = bg.prune_stale_kling_o3_trim_scratch(beat_id, tmp_path, beat)
    assert removed == 2
    assert current.is_file()
    assert not old.is_file()
    assert not legacy.is_file()


def test_reconcile_kling_o3_trim_all_events_clears_stale_scratch_without_sidecar_trim(tmp_path: Path, monkeypatch):
    beat_id = "bg_arc1_event2_pre_beat_10"
    event_dir = tmp_path / "Event_2"
    scratch = event_dir / "assembled" / "_kling_o3_trim_scratch"
    scratch.mkdir(parents=True)
    stale = scratch / f"{beat_id}_ui_trim_preview.mp4"
    stale.write_bytes(b"x")
    sidecar = {
        "arcs": {
            "1": {
                "segments": {
                    "event_2_pre": {
                        "beats": [{
                            "beat_id": beat_id,
                            "kling_o3_video_path": str(event_dir / "clip.mp4"),
                        }],
                    },
                },
            },
        },
    }
    (event_dir / "clip.mp4").write_bytes(b"x")
    monkeypatch.setattr(bg, "event_dir_for_beat_id", lambda bid: event_dir)
    changed = bg.reconcile_kling_o3_trim_all_events(sidecar, tmp_path)
    assert changed >= 1
    assert not stale.is_file()


def test_session_state_wires_trim_reconcile_all_events():
    src = Path(__file__).resolve().parents[1] / "server_handlers" / "background.py"
    text = src.read_text(encoding="utf-8")
    block = text.split("def handle_bg_session_state", 1)[1].split("\ndef ", 1)[0]
    assert "reconcile_kling_o3_trim_all_events" in block
    assert "trim_reconcile_changed" in block
