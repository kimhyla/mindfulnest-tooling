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
    find_cached_by_basename,
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


def test_resolve_playback_url_token_matches_basename_cache_hit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PLAYBACK_TOKEN_MATCHES_CACHE_FILE_V1 — Event_6 intro_tail spinner class.

    When materialize returns an older pb_* leaf (basename hit), the URL token
    must be that leaf's token — not a freshly hashed source token that 404s.
    """
    import media_playback_cache as mpc

    event_dir = tmp_path / "Event_6"
    event_dir.mkdir()
    src = event_dir / "intro_tail.mp4"
    payload = b"\x00\x00\x00\x20ftypmp42" + b"intro-tail" * 40
    src.write_bytes(payload)

    stale = playback_cache_dir(event_dir) / "pb_18f93af27cd36e60_intro_tail.mp4"
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_bytes(payload)

    monkeypatch.setattr(mpc, "materialize_playback_cache", lambda *_a, **_k: stale)

    result = resolve_playback_url(
        src,
        event_dir=event_dir,
        event_id="Event_6",
        server_base="http://localhost:5116",
    )
    assert result["cache_token"] == "18f93af27cd36e60"
    assert result["playback_url"].endswith("/api/media/playback/Event_6/18f93af27cd36e60")
    # Fresh source token would differ after mtime touch — must NOT be used.
    src.write_bytes(payload + b"x")
    fresh = playback_cache_token(src)
    assert fresh != "18f93af27cd36e60"
    assert lookup_playback_cache_file(event_dir, result["cache_token"]) == stale


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
    monkeypatch.setenv("MN_MEDIA_PATH_ROOTS", str(tmp_path))
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
    monkeypatch.setenv("MN_MEDIA_PATH_ROOTS", str(tmp_path))
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


def test_ensure_hot_serve_serves_basename_cache_when_dropbox_stat_deadlocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CATEGORY HOT_SERVE_CACHE_FIRST_V1: errno 11 must not black-out warmed media.

    Event_6 repro: local APFS already had phase_b_lipsync / beat deliveries, but
    Dropbox ``stat``/copy raised Resource deadlock avoided and /files returned 503.
    """
    import media_playback_cache as mpc

    hot = tmp_path / "hot-media"
    monkeypatch.setenv("MN_MEDIA_HOT_ROOT", str(hot))
    monkeypatch.setenv("MN_MEDIA_PATH_ROOTS", str(tmp_path))
    event = (
        tmp_path / "Library" / "CloudStorage" / "Dropbox" / "x"
        / "Production" / "Event_6"
    )
    src = event / "phase_b_lipsync_20260718-025314.mp4"
    src.parent.mkdir(parents=True)
    payload = b"\x00\x00\x00\x20ftypmp42" + b"phase-b-warm" * 80
    src.write_bytes(payload)

    # Warm cache once while Dropbox answers.
    warmed = ensure_hot_serve_file(src, event_dir=event)
    assert warmed.is_file()
    assert warmed.read_bytes() == payload
    assert find_cached_by_basename(event, src) == warmed

    def always_deadlock(*_a, **_k):
        raise OSError(11, "Resource deadlock avoided")

    monkeypatch.setattr(mpc, "path_isfile_durable", always_deadlock)
    monkeypatch.setattr(mpc, "path_stat_durable", always_deadlock)
    monkeypatch.setattr(mpc, "materialize_playback_cache", always_deadlock)

    served = ensure_hot_serve_file(src, event_dir=event)
    assert served == warmed
    assert served.read_bytes() == payload
    assert "CloudStorage" not in str(served)


def test_ensure_hot_serve_warm_hit_never_probes_dropbox(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CATEGORY HOT_SERVE_TRUE_CACHE_FIRST_V2: warm pb_* must not call Dropbox at all.

    Prior V1 only fell back after errno. File Provider can *block* inside isfile
    without raising — that hung /files even when APFS cache was warm (Event_6).
    """
    import media_playback_cache as mpc

    hot = tmp_path / "hot-media"
    monkeypatch.setenv("MN_MEDIA_HOT_ROOT", str(hot))
    monkeypatch.setenv("MN_MEDIA_PATH_ROOTS", str(tmp_path))
    event = (
        tmp_path / "Library" / "CloudStorage" / "Dropbox" / "x"
        / "Production" / "Event_6"
    )
    src = event / "kling_o3_clips" / "bg_arc1_event6_pre_beat_10_g1_master_delivery.mp4"
    src.parent.mkdir(parents=True)
    payload = b"\x00\x00\x00\x20ftypmp42" + b"warm-zero-probe" * 40
    src.write_bytes(payload)

    warmed = ensure_hot_serve_file(src, event_dir=event)
    assert find_cached_by_basename(event, src) == warmed

    probes: list[str] = []

    def ban_dropbox(name: str):
        def _ban(*_a, **_k):
            probes.append(name)
            raise AssertionError(f"Dropbox probe forbidden on warm hit: {name}")

        return _ban

    monkeypatch.setattr(mpc, "path_isfile_durable", ban_dropbox("path_isfile_durable"))
    monkeypatch.setattr(mpc, "path_stat_durable", ban_dropbox("path_stat_durable"))
    monkeypatch.setattr(mpc, "materialize_playback_cache", ban_dropbox("materialize"))
    monkeypatch.setattr(mpc, "_ensure_hot_serve_dropbox_full", ban_dropbox("dropbox_full"))
    monkeypatch.setattr(mpc, "_ensure_hot_serve_dropbox_short", ban_dropbox("dropbox_short"))

    served = ensure_hot_serve_file(src, event_dir=event, dropbox_probe="short")
    assert served == warmed
    assert probes == [], f"warm hit must not probe Dropbox; got {probes}"


def test_materialize_warm_hit_never_probes_dropbox(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CATEGORY: materialize/playback_resolve must not Dropbox-probe warm pb_*."""
    import media_playback_cache as mpc

    hot = tmp_path / "hot-media"
    monkeypatch.setenv("MN_MEDIA_HOT_ROOT", str(hot))
    monkeypatch.setenv("MN_MEDIA_PATH_ROOTS", str(tmp_path))
    event = (
        tmp_path / "Library" / "CloudStorage" / "Dropbox" / "x"
        / "Production" / "Event_6"
    )
    src = event / "kling_o3_clips" / "bg_arc1_event6_pre_beat_01_g1_element_o3_master_delivery.mp4"
    src.parent.mkdir(parents=True)
    payload = b"\x00\x00\x00\x20ftypmp42" + b"mat-warm" * 40
    src.write_bytes(payload)
    warmed = materialize_playback_cache(event, src)

    probes: list[str] = []

    def ban(name: str):
        def _ban(*_a, **_k):
            probes.append(name)
            raise AssertionError(f"forbidden Dropbox probe: {name}")
        return _ban

    monkeypatch.setattr(mpc, "path_isfile_durable", ban("path_isfile_durable"))
    monkeypatch.setattr(mpc, "path_stat_durable", ban("path_stat_durable"))
    monkeypatch.setattr(mpc, "copy_file_durable", ban("copy_file_durable"))

    again = materialize_playback_cache(event, src)
    assert again == warmed
    assert probes == []
    resolved = resolve_playback_url(
        src, event_dir=event, event_id="Event_6", server_base="http://localhost:5116",
    )
    assert resolved["cache_token"]
    assert probes == []
    assert "playback" in resolved["playback_url"]


def test_ensure_hot_serve_never_probe_raises_without_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Thumbs fail-fast: dropbox_probe=never must not touch File Provider."""
    import media_playback_cache as mpc

    hot = tmp_path / "hot-media"
    monkeypatch.setenv("MN_MEDIA_HOT_ROOT", str(hot))
    monkeypatch.setenv("MN_MEDIA_PATH_ROOTS", str(tmp_path))
    event = (
        tmp_path / "Library" / "CloudStorage" / "Dropbox" / "x"
        / "Production" / "Event_6"
    )
    src = event / "library" / "cold_thumb.png"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"\x89PNG\r\n\x1a\n" + b"cold" * 20)

    def ban(*_a, **_k):
        raise AssertionError("dropbox_probe=never must not call Dropbox helpers")

    monkeypatch.setattr(mpc, "path_isfile_durable", ban)
    monkeypatch.setattr(mpc, "_ensure_hot_serve_dropbox_full", ban)
    monkeypatch.setattr(mpc, "_ensure_hot_serve_dropbox_short", ban)

    with pytest.raises(OSError) as ei:
        ensure_hot_serve_file(src, event_dir=event, dropbox_probe="never")
    assert ei.value.errno == 11
    assert "Dropbox probe skipped" in str(ei.value)


@pytest.mark.parametrize("transient_errno", [11, 35])
def test_materialize_falls_back_to_basename_cache_on_transient_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, transient_errno: int,
) -> None:
    import media_playback_cache as mpc

    hot = tmp_path / "hot-media"
    monkeypatch.setenv("MN_MEDIA_HOT_ROOT", str(hot))
    monkeypatch.setenv("MN_MEDIA_PATH_ROOTS", str(tmp_path))
    event = (
        tmp_path / "Library" / "CloudStorage" / "Dropbox" / "x"
        / "Production" / "Event_6"
    )
    src = event / "kling_o3_clips" / "bg_arc1_event6_pre_beat_01_g1_element_o3_master_delivery.mp4"
    src.parent.mkdir(parents=True)
    payload = b"\x00\x00\x00\x20ftypmp42" + b"beat01" * 40
    src.write_bytes(payload)
    warmed = materialize_playback_cache(event, src)

    def boom(*_a, **_k):
        raise OSError(transient_errno, "transient File Provider failure")

    monkeypatch.setattr(mpc, "copy_file_durable", boom)
    # Force rematerialize path by renaming the exact token file aside… keep basename hit.
    # Delete exact token dest so materialize must copy — basename cache still present
    # only if we re-create under a different token name.
    alt = warmed.parent / f"pb_deadbeefcafef00d_{warmed.name.split('_', 2)[-1]}"
    alt.write_bytes(payload)
    warmed.unlink()

    # Stat still works (source on "cloud" fixture). Copy fails → basename fallback.
    served = materialize_playback_cache(event, src)
    assert served == alt
    assert served.read_bytes() == payload


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
