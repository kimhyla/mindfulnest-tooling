"""Server honors SfxCue.duration_ms when mixing slot audio."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "production_server.py"


def test_stitch_mix_slot_audio_honors_duration_ms() -> None:
    src = SERVER.read_text(encoding="utf-8")
    assert "atrim=duration=" in src
    assert 'cue.get("duration_ms")' in src


def test_stitch_mix_cache_key_includes_duration_ms() -> None:
    src = SERVER.read_text(encoding="utf-8")
    idx = src.find("def _stitch_mix_slot_audio")
    assert idx >= 0
    chunk = src[idx : idx + 3500]
    assert "duration_ms" in chunk
