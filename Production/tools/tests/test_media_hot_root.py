"""Local APFS media hot root — Dropbox event dirs redirect; pytest tmp stays local."""
from __future__ import annotations

from pathlib import Path

import media_hot_root as mhr
import media_playback_cache as mpc


def test_tmp_event_dir_stays_in_place(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("MN_MEDIA_HOT_ROOT", raising=False)
    event = tmp_path / "Event_6"
    event.mkdir()
    assert mhr.resolve_media_workspace(event) == event
    scratch = mhr.kling_o3_trim_scratch_dir(event)
    assert scratch == event / "assembled" / "_kling_o3_trim_scratch"
    assert scratch.is_dir()
    cache = mpc.playback_cache_dir(event)
    assert cache == event / ".playback_cache"
    assert cache.is_dir()


def test_cloud_event_dir_redirects_to_local_hot_root(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("MN_MEDIA_HOT_ROOT", raising=False)
    hot = tmp_path / "hot"
    monkeypatch.setenv("MN_MEDIA_HOT_ROOT", str(hot))
    # Simulate Dropbox path shape; need not exist on disk for name mapping.
    cloud_event = Path(
        "/Users/kimberlysmith/Library/CloudStorage/Dropbox/"
        "Claude Mindfulnest Project Files/Production/Event_6"
    )
    assert mhr.event_dir_is_cloud_backed(cloud_event)
    ws = mhr.resolve_media_workspace(cloud_event)
    assert ws == hot / "Event_6"
    assert ws.is_dir()
    scratch = mhr.kling_o3_trim_scratch_dir(cloud_event)
    assert scratch == hot / "Event_6" / "assembled" / "_kling_o3_trim_scratch"
    assert "_kling_o3_trim_scratch" in str(scratch)
    assert str(hot) in str(scratch)
    cache = mpc.playback_cache_dir(cloud_event)
    assert cache == hot / "Event_6" / ".playback_cache"


def test_env_zero_disables_redirect(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MN_MEDIA_HOT_ROOT", "0")
    cloud_event = Path(
        "/Users/kimberlysmith/Library/CloudStorage/Dropbox/"
        "Claude Mindfulnest Project Files/Production/Event_6"
    )
    # Even cloud paths stay under event_dir when opt-out is set.
    # Use a real tmp dir named like Event_6 under a CloudStorage-like path tree.
    fake_cloud = tmp_path / "Library" / "CloudStorage" / "Dropbox" / "Production" / "Event_6"
    fake_cloud.mkdir(parents=True)
    assert mhr.event_dir_is_cloud_backed(fake_cloud)
    assert mhr.resolve_media_workspace(fake_cloud) == fake_cloud


def test_media_hot_serve_roots_include_configured_root(tmp_path: Path, monkeypatch):
    hot = tmp_path / "hot_root"
    monkeypatch.setenv("MN_MEDIA_HOT_ROOT", str(hot))
    roots = mhr.media_hot_serve_roots()
    assert any(str(hot.resolve()) == r or r.startswith(str(hot.resolve())) for r in roots)
