"""Media Playback Cache (MPP) — PLAYBACK_CACHE_V1 contract tests."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
TOOLS = REPO / "tools"

import sys

sys.path.insert(0, str(TOOLS))

from media_playback_cache import (  # noqa: E402
    ensure_hot_serve_file,
    event_dir_from_media_path,
    lookup_playback_cache_file,
    materialize_playback_cache,
    playback_cache_dir,
    playback_cache_token,
    resolve_playback_url,
)
from waveform_peaks import generate_peaks_from_audio, write_peaks_json  # noqa: E402


def test_playback_cache_token_is_stable_for_same_file(tmp_path: Path) -> None:
    src = tmp_path / "clip.mp4"
    src.write_bytes(b"\x00\x00\x00\x20ftypmp42" + b"\x00" * 100)
    t1 = playback_cache_token(src)
    t2 = playback_cache_token(src)
    assert t1 == t2
    assert len(t1) == 16
    assert all(c in "0123456789abcdef" for c in t1)


def test_materialize_playback_cache_copies_bytes(tmp_path: Path) -> None:
    event_dir = tmp_path / "Event_2"
    event_dir.mkdir()
    src = event_dir / "source.mp4"
    payload = b"\x00\x00\x00\x20ftypmp42" + b"hello-playback" * 20
    src.write_bytes(payload)

    dest = materialize_playback_cache(event_dir, src)
    assert dest.is_file()
    assert dest.read_bytes() == payload
    assert dest.parent == playback_cache_dir(event_dir)


def test_resolve_playback_url_returns_cache_endpoint(tmp_path: Path) -> None:
    event_dir = tmp_path / "Event_2"
    event_dir.mkdir()
    src = event_dir / "beat.mp4"
    src.write_bytes(b"\x00\x00\x00\x20ftypmp42" + b"x" * 64)

    result = resolve_playback_url(
        src,
        event_dir=event_dir,
        event_id="Event_2",
        server_base="http://localhost:5112",
    )
    assert "/api/media/playback/Event_2/" in result["playback_url"]
    assert result.get("cache_token")
    token = result["playback_url"].rstrip("/").split("/")[-1]
    cached = lookup_playback_cache_file(event_dir, token)
    assert cached is not None and cached.is_file()


def test_lookup_playback_cache_miss_returns_none(tmp_path: Path) -> None:
    event_dir = tmp_path / "Event_2"
    event_dir.mkdir()
    playback_cache_dir(event_dir)
    assert lookup_playback_cache_file(event_dir, "deadbeefcafebabe") is None


def test_event_dir_from_media_path_finds_event_ancestor(tmp_path: Path) -> None:
    event = tmp_path / "CloudStorage" / "Dropbox" / "Production" / "Event_6"
    clip = event / "kling_o3_clips" / "master.mp4"
    clip.parent.mkdir(parents=True)
    clip.write_bytes(b"x")
    assert event_dir_from_media_path(clip) == event.resolve()


def test_ensure_hot_serve_file_remaps_cloud_master(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """CATEGORY: Dropbox masters serve from local APFS cache, not File Provider."""
    hot = tmp_path / "hot-media"
    monkeypatch.setenv("MN_MEDIA_HOT_ROOT", str(hot))
    event = tmp_path / "Library" / "CloudStorage" / "Dropbox" / "x" / "Production" / "Event_6"
    src = event / "kling_o3_clips" / "master_delivery.mp4"
    src.parent.mkdir(parents=True)
    payload = b"\x00\x00\x00\x20ftypmp42" + b"cloud-master" * 40
    src.write_bytes(payload)

    served = ensure_hot_serve_file(src, event_dir=event)
    assert served.is_file()
    assert served.read_bytes() == payload
    assert "CloudStorage" not in str(served)
    assert served.parent == playback_cache_dir(event)
    # Second call must hit cache (same path), not require Dropbox rematerialize
    served2 = ensure_hot_serve_file(src, event_dir=event)
    assert served2 == served


def test_ensure_hot_serve_file_leaves_local_paths(tmp_path: Path) -> None:
    event = tmp_path / "Event_local"
    event.mkdir()
    local = event / "already_local.mp4"
    local.write_bytes(b"\x00\x00\x00\x20ftypmp42" + b"local")
    assert ensure_hot_serve_file(local, event_dir=event) == local.resolve()


def test_ensure_hot_serve_file_remaps_cloud_mp3_stem(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CATEGORY HOT_SERVE_ALL_FILES_V1: Phase B voice stems must not stream Dropbox."""
    hot = tmp_path / "hot-media"
    monkeypatch.setenv("MN_MEDIA_HOT_ROOT", str(hot))
    event = (
        tmp_path / "Library" / "CloudStorage" / "Dropbox" / "x"
        / "Production" / "Event_3"
    )
    src = event / "phase_b_voice_stem_20260705-205227.mp3"
    src.parent.mkdir(parents=True)
    payload = b"ID3" + b"\x00" * 200 + b"cloud-stem-audio"
    src.write_bytes(payload)

    served = ensure_hot_serve_file(src, event_dir=event)
    assert served.is_file()
    assert served.read_bytes() == payload
    assert "CloudStorage" not in str(served)
    assert served.suffix == ".mp3"
    assert served.parent == playback_cache_dir(event)


@pytest.mark.skipif(
    not Path("/usr/bin/ffmpeg").is_file() and not Path("/opt/homebrew/bin/ffmpeg").is_file(),
    reason="ffmpeg required for peaks generation",
)
def test_generate_peaks_from_audio_produces_normalized_bins(tmp_path: Path) -> None:
    import subprocess

    audio = tmp_path / "tone.wav"
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
            str(audio),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    peaks = generate_peaks_from_audio(audio, num_bins=64)
    assert peaks["length"] == len(peaks["data"]) == 64
    assert peaks["duration_s"] > 0
    assert max(peaks["data"]) <= 1.0
    out = tmp_path / "peaks.json"
    write_peaks_json(peaks, out)
    assert out.is_file()
    assert hashlib.sha256(out.read_bytes()).hexdigest()
