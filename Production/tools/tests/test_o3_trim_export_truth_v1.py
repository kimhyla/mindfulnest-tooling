"""O3_TRIM_EXPORT_TRUTH_V1 — server duration truth + honest preview contracts."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import beat_generator as bg


def test_o3_trim_shortening_requested_edges():
    assert bg.o3_trim_shortening_requested(0.0, None) is False
    assert bg.o3_trim_shortening_requested(0.04, None) is False
    assert bg.o3_trim_shortening_requested(0.2, None) is True
    assert bg.o3_trim_shortening_requested(0.0, 0.2) is True
    assert bg.o3_trim_shortening_requested(0.0, 0.04) is False


def test_o3_trim_effective_is_shorter():
    assert bg.o3_trim_effective_is_shorter(5.0, 3.0) is True
    assert bg.o3_trim_effective_is_shorter(5.0, 4.96) is False
    assert bg.o3_trim_effective_is_shorter(5.0, None) is False


def test_set_o3_option_trim_start_only(tmp_path: Path):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"x")
    beat = {
        "beat_id": "bg_test",
        "kling_o3_video_path": str(clip),
        "kling_o3_options": [{"video_path": str(clip), "slot_index": 0}],
    }
    with patch.object(bg, "_ffprobe_duration", return_value=5.0):
        result = bg.set_o3_option_trim(
            beat,
            slot_index=0,
            trim_start=1.0,
            trim_back=None,
            video_path=str(clip),
        )
    assert result["raw_duration_s"] == 5.0
    assert result["effective_duration_s"] == 4.0
    assert beat["kling_o3_options"][0]["trim_start_s"] == 1.0


def test_set_o3_option_trim_end_only(tmp_path: Path):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"x")
    beat = {
        "beat_id": "bg_test",
        "kling_o3_video_path": str(clip),
        "kling_o3_options": [{"video_path": str(clip), "slot_index": 0}],
    }
    with patch.object(bg, "_ffprobe_duration", return_value=5.0):
        result = bg.set_o3_option_trim(
            beat,
            slot_index=0,
            trim_start=0.0,
            trim_back=1.5,
            video_path=str(clip),
        )
    assert result["effective_duration_s"] == 3.5
    assert beat["kling_o3_options"][0]["trim_back_s"] == 1.5


def test_resolve_playback_url_exposes_duration(tmp_path: Path, monkeypatch):
    import media_playback_cache as mpc

    event_dir = tmp_path / "Event_2"
    event_dir.mkdir()
    src = event_dir / "beat.mp4"
    src.write_bytes(b"\x00\x00\x00\x20ftypmp42" + b"x" * 64)
    monkeypatch.setattr(
        "subprocess.check_output",
        lambda *a, **k: "5.042\n",
    )
    result = mpc.resolve_playback_url(
        src,
        event_dir=event_dir,
        event_id="Event_2",
        server_base="http://localhost:5112",
    )
    assert result["duration_s"] == 5.042


def test_export_uses_trim_when_active(tmp_path: Path):
    clip = tmp_path / "source.mp4"
    clip.write_bytes(b"x")
    beat = {
        "beat_id": "bg_arc1_event2_pre_beat_10",
        "kling_o3_generation": 3,
        "kling_o3_video_path": str(clip),
        "kling_o3_trim_start": 0.0,
        "kling_o3_trim_back": 2.0,
    }
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    with patch.object(bg, "_ffprobe_duration", return_value=5.0):
        with patch.object(bg, "materialize_kling_o3_trimmed_clip") as mat:
            mat.side_effect = lambda beat, dest, **kw: dest
            dest = bg._kling_o3_export_clip_path(beat, tmp_path, scratch)
    assert "export_trim" in dest.name
    mat.assert_called_once()
