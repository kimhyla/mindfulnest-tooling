"""O3 trim slot identity — fail-closed slots and content-addressed bakes."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import beat_generator as bg
import pytest


def test_invalid_slot_index_rejects_without_video_path(tmp_path: Path):
    g2 = tmp_path / "g2.mp4"
    g6 = tmp_path / "g6.mp4"
    g2.write_bytes(b"2")
    g6.write_bytes(b"6")
    beat = {
        "beat_id": "bg_test",
        "kling_o3_generation": 6,
        "kling_o3_video_path": str(g6),
        "kling_o3_options": [
            {"video_path": str(g6), "generation": 6, "slot_index": 1},
            {"video_path": str(g2), "generation": 2, "slot_index": 2},
        ],
    }
    with pytest.raises(ValueError, match="slot_index must be 0"):
        bg.find_o3_option_by_slot_index(beat, 5)


def test_invalid_slot_resolves_by_video_path(tmp_path: Path):
    g6 = tmp_path / "g6.mp4"
    g6.write_bytes(b"6")
    beat = {
        "kling_o3_options": [
            {"video_path": str(g6), "generation": 6, "slot_index": 1},
        ],
    }
    opt = bg.find_o3_option_by_slot_index(beat, 5, video_path=str(g6))
    assert opt["video_path"] == str(g6)


def test_trim_scratch_token_binds_source_clip(tmp_path: Path):
    clip_a = tmp_path / "a.mp4"
    clip_b = tmp_path / "b.mp4"
    clip_a.write_bytes(b"a")
    clip_b.write_bytes(b"b")
    beat = {"kling_o3_trim_start": 3.33, "kling_o3_trim_back": 0.0}
    ta = bg.kling_o3_trim_scratch_token(beat, video_path=str(clip_a))
    tb = bg.kling_o3_trim_scratch_token(beat, video_path=str(clip_b))
    assert ta != tb
    assert ta.endswith("_s3.33_b0.0")


def test_export_rejects_stale_bake_from_wrong_source(tmp_path: Path):
    g2 = tmp_path / "g2.mp4"
    g6 = tmp_path / "g6.mp4"
    stale_bake = tmp_path / "stale_bake.mp4"
    for p in (g2, g6, stale_bake):
        p.write_bytes(b"x")
    beat = {
        "beat_id": "bg_arc1_event5_pre_beat_01",
        "kling_o3_generation": 6,
        "kling_o3_video_path": str(g6),
        "kling_o3_trim_start": 3.33,
    }
    token = bg.o3_baked_export_token(beat, video_path=str(g6))
    beat["kling_o3_options"] = [
        {
            "video_path": str(g6),
            "trim_start_s": 3.33,
            "kling_o3_baked_path": str(stale_bake),
            "kling_o3_baked_token": token,
            "kling_o3_baked_source_path": str(g2.resolve()),
        },
    ]
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    with patch.object(bg, "_ffprobe_duration", return_value=5.0):
        with patch.object(bg, "materialize_kling_o3_trimmed_clip") as mat:
            mat.side_effect = lambda _beat, dest, **kw: dest
            out = bg._kling_o3_export_clip_path(beat, tmp_path, scratch)
    mat.assert_called_once()
    assert out.name.endswith("_export_trim.mp4")


def test_export_uses_bake_when_source_matches(tmp_path: Path):
    clip = tmp_path / "g6.mp4"
    baked = tmp_path / "baked.mp4"
    clip.write_bytes(b"x")
    baked.write_bytes(b"baked")
    beat = {
        "beat_id": "bg_test",
        "kling_o3_generation": 6,
        "kling_o3_video_path": str(clip),
        "kling_o3_trim_start": 3.33,
        "kling_o3_options": [{"video_path": str(clip), "trim_start_s": 3.33}],
    }
    with patch.object(bg, "_ffprobe_duration", return_value=5.0):
        token = bg.o3_baked_export_token(beat, video_path=clip)
        beat["kling_o3_options"][0]["kling_o3_baked_path"] = str(baked)
        beat["kling_o3_options"][0]["kling_o3_baked_token"] = token
        beat["kling_o3_options"][0]["kling_o3_baked_source_path"] = str(clip.resolve())
        with patch.object(bg, "materialize_kling_o3_trimmed_clip") as mat:
            out = bg._kling_o3_export_clip_path(beat, tmp_path, tmp_path / "scratch")
    mat.assert_not_called()
    assert out.resolve() == baked.resolve()
