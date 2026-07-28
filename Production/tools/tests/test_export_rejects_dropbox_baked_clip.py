"""KLING_O3_EXPORT_LOCAL_CLIP_V1 — Send to Stitcher must not ffprobe Dropbox bakes.

Repro (Event_6 2026-07-28 job 7f3e8c8f-59e): preflight green (#130 local duration
gates), then export reused sidecar ``kling_o3_baked_path`` under Dropbox
``assembled/_kling_o3_trim_scratch/*_baked.mp4``. Concat A/V assert called
``ffmpeg_stitch.ffprobe_duration(..., check=True)`` → File Provider exit 1 →
button said "starting" then failed.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import beat_generator as bg  # noqa: E402


def _cloud_event(tmp_path: Path) -> Path:
    return tmp_path / "Library" / "CloudStorage" / "Dropbox" / "P" / "Event_6"


def test_dropbox_baked_path_is_not_hot_reusable(tmp_path: Path) -> None:
    event = _cloud_event(tmp_path)
    baked = (
        event
        / "assembled"
        / "_kling_o3_trim_scratch"
        / "bg_arc1_event6_pre_beat_12_g1_14fbe085_s1.08_b0.0_baked.mp4"
    )
    baked.parent.mkdir(parents=True)
    baked.write_bytes(b"\x00\x00\x00\x20ftypmp42" + b"dropbox-bake" * 40)
    assert baked.is_file()
    assert bg._export_baked_path_is_hot_reusable(baked) is False


def test_hot_scratch_baked_path_is_reusable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    hot = tmp_path / "hot"
    monkeypatch.setenv("MN_MEDIA_HOT_ROOT", str(hot))
    event = _cloud_event(tmp_path)
    event.mkdir(parents=True)
    scratch = bg.kling_o3_trim_scratch_dir(event)
    baked = scratch / "beat_12_g1_token_baked.mp4"
    baked.write_bytes(b"\x00\x00\x00\x20ftypmp42" + b"hot-bake" * 40)
    assert "CloudStorage" not in str(baked.resolve())
    assert bg._export_baked_path_is_hot_reusable(baked) is True


def test_export_clip_path_skips_dropbox_bake_and_rematerializes_to_hot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    hot = tmp_path / "hot"
    monkeypatch.setenv("MN_MEDIA_HOT_ROOT", str(hot))
    event = _cloud_event(tmp_path)
    src = event / "kling_o3_clips" / "beat_12_g1_delivery.mp4"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"\x00\x00\x00\x20ftypmp42" + b"master" * 40)
    drop_bake = (
        event
        / "assembled"
        / "_kling_o3_trim_scratch"
        / "bg_arc1_event6_pre_beat_12_g1_14fbe085_s1.08_b0.0_baked.mp4"
    )
    drop_bake.parent.mkdir(parents=True)
    drop_bake.write_bytes(b"\x00\x00\x00\x20ftypmp42" + b"stale-dropbox-bake" * 20)

    token = "14fbe085_s1.08_b0.0"
    beat = {
        "beat_id": "bg_arc1_event6_pre_beat_12",
        "kling_o3_video_path": str(src),
        "kling_o3_generation": 1,
        "kling_o3_trim_start": 1.08,
        "kling_o3_trim_back": 0.0,
        "kling_o3_baked_path": str(drop_bake),
        "kling_o3_baked_token": f"g1_{token}_baked",
        "kling_o3_baked_source_path": str(src.resolve()),
        "kling_o3_options": [
            {
                "slot_index": 0,
                "video_path": str(src),
                "trim_start_s": 1.08,
                "trim_back_s": 0.0,
                "kling_o3_baked_path": str(drop_bake),
                "kling_o3_baked_token": f"g1_{token}_baked",
                "kling_o3_baked_source_path": str(src.resolve()),
            }
        ],
    }
    scratch = bg.kling_o3_trim_scratch_dir(event)
    rematerialized = scratch / "export_trim_out.mp4"

    def _fake_materialize(b, dest, *, source_path=None, event_dir=None):
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(b"hot-export-trim")
        rematerialized.write_bytes(b"hot-export-trim")
        return Path(dest)

    monkeypatch.setattr(bg, "ffprobe_media_duration", lambda *_a, **_k: 10.0)
    monkeypatch.setattr(bg, "_ffprobe_duration", lambda *_a, **_k: 10.0)
    monkeypatch.setattr(bg, "o3_baked_export_token", lambda *_a, **_k: f"g1_{token}_baked")
    monkeypatch.setattr(bg, "kling_o3_trim_scratch_token", lambda *_a, **_k: token)
    monkeypatch.setattr(bg, "materialize_kling_o3_trimmed_clip", _fake_materialize)

    out = bg._kling_o3_export_clip_path(beat, event, scratch)
    assert out.is_file()
    assert "CloudStorage" not in str(out.resolve())
    assert out.read_bytes() == b"hot-export-trim"


def test_resolve_segment_paths_localizes_cloud_clip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    hot = tmp_path / "hot"
    monkeypatch.setenv("MN_MEDIA_HOT_ROOT", str(hot))
    event = _cloud_event(tmp_path)
    src = event / "kling_o3_clips" / "beat_01_delivery.mp4"
    src.parent.mkdir(parents=True)
    payload = b"\x00\x00\x00\x20ftypmp42" + b"delivery" * 30
    src.write_bytes(payload)

    beat = {
        "beat_id": "bg_arc1_event6_pre_beat_01",
        "kling_o3_video_path": str(src),
        "kling_o3_generation": 1,
        "kling_o3_status": "approved",
    }
    monkeypatch.setattr(bg, "ffprobe_media_duration", lambda *_a, **_k: 5.0)
    monkeypatch.setattr(bg, "_ffprobe_duration", lambda *_a, **_k: 5.0)
    monkeypatch.setattr(bg, "resolve_active_magic_layer", lambda *_a, **_k: None)
    with patch(
        "o3_gallery_option_identity.assert_beat_export_audio_contract",
        lambda *_a, **_k: None,
    ):
        # phase=None skips canonical intro-tail resolve (live Dropbox).
        paths, _flags, _scratch = bg.resolve_segment_stitch_export_clip_paths(
            [beat], event, phase=None, event_id="6",
        )
    assert len(paths) == 1
    assert paths[0].is_file()
    assert "CloudStorage" not in str(paths[0])
    assert paths[0].read_bytes() == payload
