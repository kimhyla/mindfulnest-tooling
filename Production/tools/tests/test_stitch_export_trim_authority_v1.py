"""KLING_O3_EXPORT_TRIM_AUTHORITY_V1 — option trim must mirror to beat before export."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import beat_generator as bg


def test_prepare_mirrors_option_trim_to_beat(tmp_path: Path):
    clip = tmp_path / "g7.mp4"
    clip.write_bytes(b"x")
    beat = {
        "beat_id": "bg_arc1_event4_post_beat_05",
        "kling_o3_video_path": str(clip),
        "kling_o3_options": [{"video_path": str(clip), "slot_index": 0, "trim_start_s": 0.4, "trim_back_s": 0.6}],
    }
    with patch.object(bg, "_ffprobe_duration", return_value=5.0):
        changed, errors = bg.prepare_beats_for_stitch_export([beat])
    assert not errors
    assert changed
    assert beat.get("kling_o3_trim_start") == 0.4
    assert beat.get("kling_o3_trim_back") == 0.6


def test_prepare_mirrors_trim_from_exact_slot_not_untrimmed_alias(tmp_path: Path):
    full = tmp_path / "7300_kling_idle_tts.mp4"
    trimmed = tmp_path / "7300_kling_idle_tts_trimmed.mp4"
    full.write_bytes(b"f")
    trimmed.write_bytes(b"t")
    beat = {
        "beat_id": "bg_arc1_event4_post_beat_05",
        "pipeline": "still_insert",
        "kling_o3_video_path": str(full),
        "kling_o3_options": [
            {
                "video_path": str(trimmed),
                "o3_untrimmed_video_path": str(full),
                "slot_index": 0,
                "source": "still_insert_kling_idle",
            },
            {
                "video_path": str(full),
                "slot_index": 2,
                "source": "kling_o3_disk_reconcile",
                "trim_start_s": 4.31,
                "trim_back_s": 1.9,
            },
        ],
    }
    with patch.object(bg, "_ffprobe_duration", return_value=10.042):
        changed, errors = bg.prepare_beats_for_stitch_export([beat])
    assert not errors
    assert changed
    assert beat.get("kling_o3_trim_start") == 4.31
    assert beat.get("kling_o3_trim_back") == 1.9


def test_heal_invalid_trim_clears_option_and_beat(tmp_path: Path):
    clip = tmp_path / "short.mp4"
    clip.write_bytes(b"x")
    beat = {
        "beat_id": "bg_test",
        "kling_o3_video_path": str(clip),
        "kling_o3_trim_start": 4.5,
        "kling_o3_trim_back": 0.5,
        "kling_o3_options": [{"video_path": str(clip), "trim_start_s": 4.5, "trim_back_s": 0.5}],
    }
    with patch.object(bg, "_ffprobe_duration", return_value=5.0):
        assert bg.heal_invalid_kling_o3_trim(beat) is True
    assert "kling_o3_trim_start" not in beat
    assert "trim_start_s" not in beat["kling_o3_options"][0]


def test_assert_beat_export_trim_ready_fails_when_unmirrored(tmp_path: Path):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"x")
    beat = {
        "beat_id": "bg_test",
        "kling_o3_video_path": str(clip),
        "kling_o3_options": [{"video_path": str(tmp_path / "other.mp4"), "trim_start_s": 1.0}],
    }
    with patch.object(bg, "_ffprobe_duration", return_value=5.0):
        err = bg.assert_beat_export_trim_ready(beat)
    assert err is None


def test_materialize_trim_uses_output_side_seek(tmp_path: Path, monkeypatch):
    src = tmp_path / "src.mp4"
    src.write_bytes(b"x")
    dest = tmp_path / "out.mp4"
    beat = {
        "beat_id": "bg_test",
        "kling_o3_video_path": str(src),
        "kling_o3_trim_start": 0.5,
        "kling_o3_trim_back": 0.5,
    }
    captured: list[list[str]] = []

    def fake_run(cmd, dest, **_kw):
        captured.append(list(cmd))
        Path(dest).write_bytes(b"out")

    monkeypatch.setattr(bg, "run_ffmpeg_to_dest", fake_run)
    monkeypatch.setattr(bg, "ensure_local_media", lambda p, **_: p)
    with patch.object(bg, "_ffprobe_duration", return_value=5.0):
        bg.materialize_kling_o3_trimmed_clip(beat, dest, source_path=src, event_dir=tmp_path)
    cmd = captured[0]
    i_idx = cmd.index("-i")
    ss_idx = cmd.index("-ss")
    assert i_idx < ss_idx, f"output-side seek required: {cmd}"
    assert bg.KLING_O3_EXPORT_TRIM_ACCURATE_SEEK_V1


def test_concat_raises_on_trim_authority_error(tmp_path: Path, monkeypatch):
    clip = tmp_path / "c.mp4"
    clip.write_bytes(b"x")
    beat = {
        "beat_id": "bg_test",
        "kling_o3_video_path": str(clip),
        "kling_o3_options": [{"video_path": str(clip), "trim_start_s": 1.0}],
    }

    def fake_prepare(beats):
        beats[0].pop("kling_o3_trim_start", None)
        return False, ["bg_test: trim metadata present but export would use full clip (X)"]

    monkeypatch.setattr(bg, "prepare_beats_for_stitch_export", fake_prepare)
    try:
        bg.concat_kling_o3_approved_beats([beat], tmp_path, "resolution")
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "trim metadata present" in str(exc)
