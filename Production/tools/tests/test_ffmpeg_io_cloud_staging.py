"""Cloud-aware ffmpeg I/O contract tests."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from lib import ffmpeg_io as fio


def test_path_is_cloud_storage_backed_detects_dropbox():
    p = "/Users/me/Library/CloudStorage/Dropbox/Production/Event_2/foo.mp4"
    assert fio.path_is_cloud_storage_backed(p) is True
    assert fio.path_is_cloud_storage_backed("/tmp/foo.mp4") is False


@pytest.mark.parametrize("transient_errno", [11, 35])
def test_path_stat_and_read_bytes_retry_transient_errno(
    tmp_path: Path, monkeypatch, transient_errno: int,
):
    path = tmp_path / "peaks.json"
    path.write_bytes(b'{"ok":true}')
    calls = {"stat": 0, "open": 0}
    real_stat = os.stat
    real_open = open

    def flaky_stat(p, *a, **k):
        if os.path.abspath(str(p)) == os.path.abspath(str(path)):
            calls["stat"] += 1
            if calls["stat"] == 1:
                raise OSError(transient_errno, "transient File Provider failure")
        return real_stat(p, *a, **k)

    def flaky_open(file, mode="r", *a, **k):
        if os.path.abspath(str(file)) == os.path.abspath(str(path)) and "b" in str(mode):
            calls["open"] += 1
            if calls["open"] == 1:
                raise OSError(transient_errno, "transient File Provider failure")
        return real_open(file, mode, *a, **k)

    monkeypatch.setattr(fio.os, "stat", flaky_stat)
    monkeypatch.setattr("builtins.open", flaky_open)
    monkeypatch.setattr(fio.time, "sleep", lambda _s: None)

    st = fio.path_stat_durable(path)
    assert st.st_size == path.stat().st_size
    assert fio.read_bytes_durable(path) == b'{"ok":true}'
    assert calls["stat"] >= 2
    assert calls["open"] == 2


def test_path_isfile_durable_retries_errno11(tmp_path: Path, monkeypatch):
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"x")
    calls = {"n": 0}
    real_isfile = os.path.isfile

    def flaky_isfile(p):
        if os.path.abspath(str(p)) == os.path.abspath(str(path)):
            calls["n"] += 1
            if calls["n"] == 1:
                raise OSError(11, "Resource deadlock avoided")
        return real_isfile(p)

    monkeypatch.setattr(fio.os.path, "isfile", flaky_isfile)
    monkeypatch.setattr(fio.time, "sleep", lambda _s: None)
    assert fio.path_isfile_durable(path) is True
    assert calls["n"] == 2


def test_local_staging_temp_path_not_under_cloud(tmp_path: Path):
    p = fio.local_staging_temp_path(suffix=".mp4", prefix="t_")
    assert "mn_ffmpeg_scratch" in str(p)
    assert "CloudStorage" not in str(p)
    p.unlink(missing_ok=True)


def test_run_ffmpeg_to_dest_never_writes_cloud_directly(tmp_path: Path, monkeypatch):
    cloud_dest = tmp_path / "CloudStorage" / "Dropbox" / "Event_2" / "out.mp4"
    cloud_dest.parent.mkdir(parents=True)
    local_paths: list[Path] = []

    def fake_local(*, suffix: str, prefix: str) -> Path:
        lp = tmp_path / f"{prefix}stage{suffix}"
        local_paths.append(lp)
        return lp

    def fake_run(cmd, **kwargs):
        out = Path(cmd[-1])
        out.write_bytes(b"vid")
        return type("R", (), {"returncode": 0, "stderr": ""})()

    monkeypatch.setattr(fio, "local_staging_temp_path", fake_local)
    monkeypatch.setattr(fio.subprocess, "run", fake_run)
    monkeypatch.setattr(fio, "commit_local_file_to_dest", lambda s, d: Path(d).write_bytes(Path(s).read_bytes()))

    fio.run_ffmpeg_to_dest(
        ["ffmpeg", "-y", "-i", "in.mp4", str(cloud_dest)],
        cloud_dest,
        error_prefix="test ffmpeg",
    )
    assert cloud_dest.read_bytes() == b"vid"
    assert local_paths
    assert all("CloudStorage" not in str(p) for p in local_paths)


def test_encode_delivery_video_stages_on_local_disk(tmp_path: Path, monkeypatch):
    """Integration: ffmpeg argv output path must never be under CloudStorage."""
    import video_delivery as vd

    cloud_dest = (
        tmp_path
        / "Users"
        / "me"
        / "Library"
        / "CloudStorage"
        / "Dropbox"
        / "Production"
        / "Event_6"
        / "kling_o3_clips"
        / "proof_delivery.mp4"
    )
    cloud_dest.parent.mkdir(parents=True)
    src = tmp_path / "src.mp4"
    src.write_bytes(b"not-real-video")

    ffmpeg_out_paths: list[str] = []

    def _capture_run(cmd, **kwargs):
        ffmpeg_out_paths.append(str(cmd[-1]))
        # Simulate successful encode without running ffmpeg
        Path(cmd[-1]).write_bytes(b"x" * 500_000)
        return type("R", (), {"returncode": 0, "stderr": ""})()

    monkeypatch.setattr(vd.subprocess, "run", _capture_run)
    monkeypatch.setattr(vd, "_has_audio", lambda _p: True)
    monkeypatch.setattr(vd, "_probe_bitrate", lambda _p: 1_500_000)
    monkeypatch.setattr(vd, "ensure_mp4_playback_timestamps", lambda p, **k: p)

    vd.encode_delivery_video(
        src,
        cloud_dest,
        include_audio=False,
        delivery_profile="standard",
    )

    assert cloud_dest.is_file()
    assert ffmpeg_out_paths
    # Primary delivery encode must stage on local disk — not the growing tmp that killed g3.
    delivery_encode_paths = [p for p in ffmpeg_out_paths if "mn_del_" in p or "mn_ffmpeg_scratch" in p]
    assert delivery_encode_paths
    assert all("CloudStorage" not in p for p in delivery_encode_paths)
