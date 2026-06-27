"""Send-to-Stitcher export durability — migration, bake, retry."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import beat_generator as bg


def test_migrate_segment_converts_edge_cut_on_export_prep(tmp_path: Path):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"x")
    beat = {
        "beat_id": "bg_test",
        "kling_o3_video_path": str(clip),
        "kling_o3_options": [
            {"video_path": str(clip), "slot_index": 0, "cut_start_s": 0.0, "cut_end_s": 1.5},
        ],
    }
    with patch.object(bg, "_ffprobe_duration", return_value=5.0):
        assert bg.migrate_segment_o3_trims_for_export([beat]) is True
    opt = beat["kling_o3_options"][0]
    assert opt.get("trim_start_s") == 1.5
    assert "cut_start_s" not in opt


def test_export_clip_path_prefers_trim_over_stale_cut(tmp_path: Path):
    clip = tmp_path / "g17.mp4"
    clip.write_bytes(b"x")
    beat = {
        "beat_id": "bg_arc1_event2_pre_beat_04",
        "kling_o3_generation": 17,
        "kling_o3_video_path": str(clip),
        "kling_o3_trim_start": 1.0,
        "kling_o3_trim_back": 0.5,
        "kling_o3_cut_start_s": 0.0,
        "kling_o3_cut_end_s": 2.0,
    }
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    with patch.object(bg, "_ffprobe_duration", return_value=5.0):
        with patch.object(bg, "materialize_kling_o3_trimmed_clip") as mat_trim:
            with patch.object(bg, "materialize_o3_cut_out_clip") as mat_cut:
                mat_trim.return_value = scratch / "trim.mp4"
                out = bg._kling_o3_export_clip_path(beat, tmp_path, scratch)
    mat_trim.assert_called_once()
    mat_cut.assert_not_called()
    assert out.name == "trim.mp4"


def test_export_uses_baked_path_when_token_matches(tmp_path: Path):
    clip = tmp_path / "src.mp4"
    clip.write_bytes(b"x")
    baked = tmp_path / "baked.mp4"
    baked.write_bytes(b"baked")
    beat = {
        "beat_id": "bg_test",
        "kling_o3_generation": 3,
        "kling_o3_video_path": str(clip),
        "kling_o3_trim_start": 0.5,
        "kling_o3_baked_path": str(baked),
    }
    with patch.object(bg, "_ffprobe_duration", return_value=4.0):
        beat["kling_o3_baked_token"] = bg.o3_baked_export_token(beat, video_path=clip)
        out = bg._kling_o3_export_clip_path(beat, tmp_path, tmp_path / "scratch")
    assert out.resolve() == baked.resolve()


def test_mirror_tail_only_trim_without_trim_start_key(tmp_path: Path):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"x")
    beat = {
        "beat_id": "bg_test",
        "kling_o3_video_path": str(clip),
        "kling_o3_options": [{"video_path": str(clip), "trim_back_s": 1.2}],
    }
    bg.mirror_beat_trim_from_option(beat, beat["kling_o3_options"][0])
    assert beat.get("kling_o3_trim_start") == 0.0
    assert beat.get("kling_o3_trim_back") == 1.2


def test_materialize_beat_export_retry_on_transient(tmp_path: Path, monkeypatch):
    clip = tmp_path / "c.mp4"
    clip.write_bytes(b"x")
    beat = {"beat_id": "bg_retry", "kling_o3_video_path": str(clip)}
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    calls = {"n": 0}

    def flaky(_beat, _ed, _sc):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("Resource deadlock avoided")
        return clip

    monkeypatch.setattr(bg, "resolve_beat_stitch_export_clip_path", flaky)
    monkeypatch.setattr(bg.time, "sleep", lambda _s: None)
    out = bg.materialize_beat_export_clip_with_retry(beat, tmp_path, scratch, max_attempts=3)
    assert out == clip
    assert calls["n"] == 2
