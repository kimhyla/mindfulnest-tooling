"""HOT_SERVE_CACHE_FIRST_V1 — media serve must survive Dropbox errno 11/35.

Locks the category gap left by JSON-only cold-boot durability (#119/#120):
players went black while APFS .playback_cache already held the bytes, because
/files and peaks still required a live Dropbox ``stat``/``read`` first.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TOOLS = REPO / "tools"
SERVER = TOOLS / "production_server.py"
CACHE = TOOLS / "media_playback_cache.py"
FFMPEG_IO = REPO / "lib" / "ffmpeg_io.py"


def test_shared_durable_dropbox_io_helpers_exist() -> None:
    text = FFMPEG_IO.read_text(encoding="utf-8")
    assert "def path_stat_durable" in text
    assert "def path_isfile_durable" in text
    assert "def read_bytes_durable" in text
    assert "11" in text and "35" in text


def test_hot_serve_cache_first_wired_in_media_cache() -> None:
    text = CACHE.read_text(encoding="utf-8")
    assert "HOT_SERVE_CACHE_FIRST_V1" in text
    assert "def find_cached_by_basename" in text
    assert "path_isfile_durable" in text
    assert "path_stat_durable" in text


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
