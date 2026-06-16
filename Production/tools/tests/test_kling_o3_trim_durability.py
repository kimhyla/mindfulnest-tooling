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
