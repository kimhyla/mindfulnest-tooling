"""HOT_SERVE_BAKE_V1 — trim/cut ffmpeg inputs use shared APFS hot-serve cache."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import beat_generator as bg  # noqa: E402


def test_ensure_local_media_routes_cloud_to_playback_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    hot = tmp_path / "hot"
    monkeypatch.setenv("MN_MEDIA_HOT_ROOT", str(hot))
    event = tmp_path / "Library" / "CloudStorage" / "Dropbox" / "P" / "Event_6"
    src = event / "kling_o3_clips" / "master.mp4"
    src.parent.mkdir(parents=True)
    payload = b"\x00\x00\x00\x20ftypmp42" + b"bake-input" * 30
    src.write_bytes(payload)

    local = bg.ensure_local_media(src, event_id="Event_6", event_dir=event)
    assert local.is_file()
    assert local.read_bytes() == payload
    assert "CloudStorage" not in str(local)
    assert ".playback_cache" in str(local)


def test_materialize_trim_ffmpeg_i_uses_hot_cache_not_dropbox(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    hot = tmp_path / "hot"
    monkeypatch.setenv("MN_MEDIA_HOT_ROOT", str(hot))
    event = tmp_path / "Library" / "CloudStorage" / "Dropbox" / "P" / "Event_6"
    src = event / "kling_o3_clips" / "master.mp4"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"\x00\x00\x00\x20ftypmp42" + b"x" * 200)
    dest = tmp_path / "out_trim.mp4"
    captured: list[list[str]] = []

    def fake_run(cmd, dest_path, **_kw):
        captured.append(list(cmd))
        Path(dest_path).write_bytes(b"trimmed")

    monkeypatch.setattr(bg, "run_ffmpeg_to_dest", fake_run)
    monkeypatch.setattr(bg, "_ffprobe_duration", lambda _p: 5.0)

    beat = {
        "beat_id": "bg_arc1_event6_pre_beat_04",
        "kling_o3_video_path": str(src),
        "kling_o3_trim_start": 1.0,
        "kling_o3_trim_back": 0.5,
        "kling_o3_generation": 1,
    }
    bg.materialize_kling_o3_trimmed_clip(beat, dest, source_path=src, event_dir=event)
    assert captured, "ffmpeg must run"
    i_path = captured[0][captured[0].index("-i") + 1]
    assert "CloudStorage" not in i_path
    assert ".playback_cache" in i_path
    assert dest.read_bytes() == b"trimmed"
