"""Cloud-aware ffmpeg I/O contract tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from lib import ffmpeg_io as fio


def test_path_is_cloud_storage_backed_detects_dropbox():
    p = "/Users/me/Library/CloudStorage/Dropbox/Production/Event_2/foo.mp4"
    assert fio.path_is_cloud_storage_backed(p) is True
    assert fio.path_is_cloud_storage_backed("/tmp/foo.mp4") is False


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


def test_ffmpeg_failure_transient_detects_deadlock():
    assert fio.ffmpeg_failure_transient("Resource deadlock avoided") is True
    assert fio.ffmpeg_failure_transient("ok") is False
