"""BG_DIRECTUS_EXPORT_V1 — Send to Stitcher Directus registration contracts."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

import beat_generator as bg  # noqa: E402
from bg_directus_register import (  # noqa: E402
    BG_DIRECTUS_EXPORT_V1,
    event_num_from_dir,
    persist_directus_export_on_sidecar,
    register_bg_export_to_directus,
)


def test_event_num_from_dir_parses_event_folder():
    assert event_num_from_dir("/tmp/Production/Event_2") == 2
    assert event_num_from_dir("Event_12") == 12
    assert event_num_from_dir("weird") is None


def test_resolve_segment_export_clip_paths_matches_concat_inputs(tmp_path, monkeypatch):
    """Category: one resolver feeds concat + Directus — no path drift."""
    event_dir = tmp_path / "Event_2"
    event_dir.mkdir()
    clips = event_dir / "kling_o3_clips"
    clips.mkdir()
    clip_a = clips / "bg_arc1_event2_pre_beat_01_g1.mp4"
    clip_b = clips / "bg_arc1_event2_pre_beat_02_g1.mp4"
    clip_a.write_bytes(b"\x00\x00\x00\x20ftypmp42" + b"\x00" * 64)
    clip_b.write_bytes(b"\x00\x00\x00\x20ftypmp42" + b"\x00" * 64)

    def _fake_duration(_path):
        return 2.0

    monkeypatch.setattr(bg, "_ffprobe_duration", _fake_duration)
    monkeypatch.setattr(bg, "_ffprobe_ok", lambda _p: True)
    def _norm(src, dst):
        import shutil
        shutil.copy2(src, dst)

    monkeypatch.setattr(
        bg,
        "_ffmpeg_stitch_module",
        lambda: type("FS", (), {
            "assert_stitch_export_clips_av_aligned": staticmethod(lambda _c: None),
            "assert_stitch_export_cumulative_av_aligned": staticmethod(lambda _c: None),
            "assert_stitch_export_assembled_av_drift": staticmethod(lambda _p: None),
            "export_clip_timeline_duration_s": staticmethod(lambda _p: 2.0),
            "normalize_for_concat": staticmethod(_norm),
        })(),
    )
    monkeypatch.setattr(bg, "_ffmpeg_concat_kling_clips_reencode", lambda c, d, **k: d.write_bytes(b"x"))
    monkeypatch.setattr(bg, "_ffmpeg_concat_kling_clips_with_pair_fades", lambda *a, **k: a[1].write_bytes(b"x"))
    monkeypatch.setattr(bg, "_intro_export_pair_fades", lambda *a, **k: [])
    monkeypatch.setattr(bg, "_boundaries_for_pair_fade_concat", lambda b, c, f: [])
    monkeypatch.setattr(
        "teleport_intro_canonical.resolve_canonical_tail_for_event",
        lambda *a, **k: None,
    )

    beats = [
        {
            "beat_id": "bg_arc1_event2_pre_beat_01",
            "kling_o3_video_path": str(clip_a),
            "kling_o3_status": "approved",
        },
        {
            "beat_id": "bg_arc1_event2_pre_beat_02",
            "kling_o3_video_path": str(clip_b),
            "kling_o3_status": "approved",
        },
    ]
    resolved, _, _ = bg.resolve_segment_stitch_export_clip_paths(
        beats, event_dir, phase="pre", event_id="2",
    )
    assert len(resolved) == 2
    assert all(p.is_file() for p in resolved)
    assert resolved[0].name.endswith("_norm_concat.mp4")
    assert resolved[1].name.endswith("_norm_concat.mp4")

    out_path, _, _ = bg.concat_kling_o3_approved_beats(
        beats, event_dir, "intro", phase="pre", event_id="2",
    )
    assert out_path.is_file()


def test_register_bg_export_calls_register_and_approve(tmp_path):
    clip = tmp_path / "beat.mp4"
    clip.write_bytes(b"fake-mp4-bytes-for-test")
    concat = tmp_path / "concat.mp4"
    concat.write_bytes(b"fake-concat-mp4")

    beat = {
        "beat_id": "bg_arc1_event2_post_beat_01",
        "kling_o3_video_path": str(clip),
        "kling_o3_selected_option_key": "opt_a",
    }

    with patch("registered_write.register_asset", return_value=(42, str(clip))) as reg:
        with patch("registered_write.approve_asset", return_value=True) as appr:
            result = register_bg_export_to_directus(
                beats=[beat],
                clip_paths=[clip],
                concat_path=concat,
                module_id=1,
                event_dir=tmp_path / "Event_2",
                slot_key="resolution",
                phase="post",
                boundaries=[{"beat_id": beat["beat_id"], "start_ms": 0, "end_ms": 2000}],
                duration_s=2.0,
            )

    assert result["code"] == BG_DIRECTUS_EXPORT_V1
    assert result["registered_beat_count"] == 1
    assert result["concat_asset_id"] == 42
    reg.assert_called()
    appr.assert_called_once_with(
        42,
        "Send to Stitcher — active highlighted clip exported to stitch slot",
        alias="bg_arc1_event2_post_beat_01 stitch export",
    )
    beat_row = result["beats"][0]
    assert beat_row["asset_id"] == 42
    assert beat_row["approved"] is True


def test_persist_directus_export_writes_sidecar_fields():
    sidecar = {"arcs": {"arc_1": {"segments": {}}}}
    seg = bg.get_seg_entry(sidecar, 1, "2", "post")
    seg["beats"] = [{"beat_id": "bg_arc1_event2_post_beat_01", "speaker": "Arlo"}]
    directus_result = {
        "beats": [{
            "beat_id": "bg_arc1_event2_post_beat_01",
            "asset_id": 99,
            "registered_at": "2026-06-20T12:00:00Z",
            "clip_path": "/tmp/clip.mp4",
        }],
        "concat_asset_id": 100,
        "exported_at": "2026-06-20T12:00:01Z",
    }
    persist_directus_export_on_sidecar(
        sidecar,
        arc_number=1,
        event_id="2",
        phase="post",
        directus_result=directus_result,
    )
    beat = seg["beats"][0]
    assert beat["directus_asset_id"] == 99
    assert beat["directus_export_clip_path"] == "/tmp/clip.mp4"
    assert seg["directus_segment_concat_asset_id"] == 100


def test_export_handler_wires_directus_registration():
    src = (TOOLS / "server_handlers" / "kling_o3.py").read_text(encoding="utf-8")
    block = src.split("def _run_bg_export_to_stitcher_core", 1)[1].split("\ndef ", 1)[0]
    assert "BG_DIRECTUS_EXPORT_V1" in block
    assert "register_bg_export_to_directus" in block
    assert "preserve_kling_o3_segment_beats" in block
    assert "directus" in block


def test_sidecar_preserves_directus_fields():
    text = (TOOLS / "beat_generator.py").read_text(encoding="utf-8")
    block = text.split("SIDECAR_MERGE_PRESERVE_FIELDS", 1)[1].split("_EXTRACT_APPROVE_MERGE_PRESERVE", 1)[0]
    assert "directus_asset_id" in block
    assert "directus_export_clip_path" in block
