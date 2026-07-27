"""HOT_SERVE_TRUE_CACHE_FIRST_V2 — media serve must survive Dropbox hangs.

Locks the category gap left by JSON-only cold-boot durability (#119/#120) and
the incomplete cache-first (#121): players went black / spun while APFS
.playback_cache already held the bytes, because /files still probed Dropbox
``stat``/``isfile``/``realpath`` *before* returning the warm ``pb_*``.

File Provider can block forever without raising errno — warm hits must never
enter that path.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TOOLS = REPO / "tools"
SERVER = TOOLS / "production_server.py"
CACHE = TOOLS / "media_playback_cache.py"
CROPPER = TOOLS / "server_handlers" / "cropper.py"
FFMPEG_IO = REPO / "lib" / "ffmpeg_io.py"


def test_shared_durable_dropbox_io_helpers_exist() -> None:
    text = FFMPEG_IO.read_text(encoding="utf-8")
    assert "def path_stat_durable" in text
    assert "def path_isfile_durable" in text
    assert "def read_bytes_durable" in text
    assert "11" in text and "35" in text


def test_hot_serve_true_cache_first_wired_in_media_cache() -> None:
    text = CACHE.read_text(encoding="utf-8")
    assert "HOT_SERVE_TRUE_CACHE_FIRST_V2" in text
    assert "def find_cached_by_basename" in text
    assert 'dropbox_probe: str = "when_needed"' in text
    assert "def _ensure_hot_serve_dropbox_short" in text
    # Warm hit must return cached_hit before any Dropbox helper call.
    ensure_block = text.split("def ensure_hot_serve_file", 1)[1].split(
        "def _ensure_hot_serve_dropbox_full", 1,
    )[0]
    assert "cached_hit = find_cached_by_basename" in ensure_block
    assert "if cached_hit is not None:" in ensure_block
    assert "return cached_hit" in ensure_block
    # Must NOT call path_isfile_durable in the warm path (only in full helper).
    assert "path_isfile_durable" not in ensure_block


def test_files_resolve_tries_apfs_cache_before_dropbox_realpath() -> None:
    text = SERVER.read_text(encoding="utf-8")
    resolve = text.split("def _resolve_served_file_path", 1)[1].split(
        "def _handle_preview_phase_a_permanent", 1,
    )[0]
    assert "HOT_SERVE_TRUE_CACHE_FIRST_V2" in resolve
    assert "find_cached_by_basename" in resolve
    # Cache attempt appears before Dropbox candidate loop / isabs Dropbox gate.
    cache_idx = resolve.index("find_cached_by_basename")
    drop_idx = resolve.index("os.path.isabs(file_path)")
    assert cache_idx < drop_idx


def test_request_path_ensure_uses_never_dropbox_probe() -> None:
    text = SERVER.read_text(encoding="utf-8")
    ensure = text.split("def _ensure_local_file_for_serve", 1)[1].split(
        "def _ensure_local_mp4_for_serve", 1,
    )[0]
    assert 'dropbox_probe="never"' in ensure


def test_cr_thumb_warm_cache_before_dropbox_realpath() -> None:
    text = CROPPER.read_text(encoding="utf-8")
    thumb = text.split("def handle_cr_thumb", 1)[1].split(
        "def handle_cr_library", 1,
    )[0]
    assert "find_cached_by_basename" in thumb
    assert 'dropbox_probe="never"' in thumb
    # Production Dropbox thumbs use soft abspath first; realpath only as fallback.
    soft_idx = thumb.index("under_drop")
    real_idx = thumb.index("require_realpath_under_project")
    assert soft_idx < real_idx
    assert "THUMB_MATERIALIZE_FAILED" in thumb


def test_materialize_and_playback_resolve_are_cache_first() -> None:
    text = CACHE.read_text(encoding="utf-8")
    mat = text.split("def materialize_playback_cache", 1)[1].split(
        "def resolve_playback_url", 1,
    )[0]
    assert "cached_hit = find_cached_by_basename" in mat
    assert mat.index("cached_hit = find_cached_by_basename") < mat.index(
        "path_isfile_durable"
    )
    pb = (TOOLS / "server_handlers" / "media_playback.py").read_text(encoding="utf-8")
    avail = pb.split("def _src_available", 1)[1].split("if not _src_available", 1)[0]
    assert "find_cached_by_basename" in avail
    assert avail.index("find_cached_by_basename") < avail.index("path_isfile_durable")


def test_peaks_and_stitch_audio_use_durable_dropbox_reads() -> None:
    text = SERVER.read_text(encoding="utf-8")
    peaks = text.split("def _serve_stitch_peaks_file", 1)[1].split(
        "def _handle_stitch_audio_extract", 1,
    )[0]
    assert "read_bytes_durable" in peaks
    assert "path_isfile_durable" in peaks
    assert "PEAKS_READ_FAILED" in peaks
    audio = text.split("def _serve_stitch_audio_file", 1)[1].split(
        "def _handle_stitch_slot_ambient_loop", 1,
    )[0]
    assert "path_isfile_durable" in audio
    assert "_ensure_local_file_for_serve" in audio
    assert "HOT_SERVE_MATERIALIZE_FAILED" in audio
