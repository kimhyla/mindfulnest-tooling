"""Per-option O3 front/back trim — start + end crop on one clip."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import beat_generator as bg


def test_set_o3_option_trim_start_and_end(tmp_path: Path):
    clip = tmp_path / "g17_delivery.mp4"
    clip.write_bytes(b"x")
    beat = {
        "beat_id": "bg_arc1_event2_pre_beat_04",
        "kling_o3_generation": 17,
        "kling_o3_video_path": str(clip),
        "kling_o3_options": [
            {"key": "opt", "video_path": str(clip), "slot_index": 1},
        ],
    }
    with patch.object(bg, "_ffprobe_duration", return_value=5.0):
        result = bg.set_o3_option_trim(
            beat,
            slot_index=1,
            trim_start=0.8,
            trim_back=1.2,
            video_path=str(clip),
        )
    opt = beat["kling_o3_options"][0]
    assert opt["trim_start_s"] == 0.8
    assert opt["trim_back_s"] == 1.2
    assert "cut_start_s" not in opt
    assert beat["kling_o3_trim_start"] == 0.8
    assert beat["kling_o3_trim_back"] == 1.2
    assert result["effective_duration_s"] == 3.0


def test_migrate_head_cut_to_trim_start(tmp_path: Path):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"x")
    beat = {
        "beat_id": "bg_test",
        "kling_o3_video_path": str(clip),
        "kling_o3_options": [
            {
                "video_path": str(clip),
                "slot_index": 0,
                "cut_start_s": 0.0,
                "cut_end_s": 2.4,
            },
        ],
    }
    with patch.object(bg, "_ffprobe_duration", return_value=5.0):
        assert bg.migrate_o3_options_edge_cut_to_trim(beat) is True
    opt = beat["kling_o3_options"][0]
    assert opt["trim_start_s"] == 2.4
    assert "cut_start_s" not in opt
    assert beat["kling_o3_trim_start"] == 2.4


def test_materialize_cut_out_stages_on_local_disk(tmp_path: Path, monkeypatch):
    """ffmpeg output must not land in Dropbox scratch — stage locally then durable copy."""
    src = tmp_path / "src.mp4"
    src.write_bytes(b"fake")
    dest = tmp_path / "CloudStorage" / "Dropbox" / "Event_2" / "assembled" / "out_export_cut.mp4"
    dest.parent.mkdir(parents=True)
    beat = {
        "beat_id": "bg_test",
        "kling_o3_video_path": str(src),
        "kling_o3_cut_start_s": 0.0,
        "kling_o3_cut_end_s": 1.0,
    }
    local_tmp = tmp_path / "local_stage.cut_tmp.mp4"
    calls: list[str] = []

    monkeypatch.setattr(bg, "run_ffmpeg_to_dest", lambda cmd, dest, **kw: Path(dest).write_bytes(b"encoded") or Path(dest))
    monkeypatch.setattr(bg, "ensure_local_media", lambda p, **kw: p)
    monkeypatch.setattr(bg, "_ffprobe_duration", lambda _p: 5.0)

    bg.materialize_o3_cut_out_clip(beat, dest, source_path=src, event_dir=tmp_path)
    assert dest.read_bytes() == b"encoded"
