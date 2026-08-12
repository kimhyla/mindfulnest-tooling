"""STITCH_MIX_LOCAL_INPUTS_V1 + STITCH_MIX_SPEECH_MONO_V1 — Export ambient mix durability."""
from __future__ import annotations

from pathlib import Path


def _mix_slot_block() -> str:
    src = Path(__file__).resolve().parents[1] / "production_server.py"
    text = src.read_text(encoding="utf-8")
    start = text.index("def _stitch_mix_slot_audio")
    end = text.index("\n    def _stitch_build_pipeline", start)
    return text[start:end]


def test_mix_materializes_dropbox_inputs_before_ffmpeg() -> None:
    block = _mix_slot_block()
    assert "STITCH_MIX_LOCAL_INPUTS_V1" in block
    assert "ensure_hot_serve_file" in block
    assert "mix_norm = ensure_hot_serve_file" in block
    assert '["-i", str(mix_norm)]' in block


def test_mix_forces_speech_mono_before_amix() -> None:
    block = _mix_slot_block()
    assert "STITCH_MIX_SPEECH_MONO_V1" in block
    assert "[0:a]aresample=44100,aformat=channel_layouts=mono[speech]" in block
    assert 'base_audio = "[speech]"' in block
    assert 'base_audio = "[0:a]"' not in block


def test_mix_retries_once_and_reports_stderr_tail() -> None:
    block = _mix_slot_block()
    assert "for attempt in range(2):" in block
    assert "raw_err[-2500:]" in block


def test_phase_export_audits_playback_bake_failure() -> None:
    src = (
        Path(__file__).resolve().parents[1]
        / "server_handlers"
        / "phases.py"
    ).read_text(encoding="utf-8")
    block = src.split("def handle_phase_export_stitcher", 1)[1].split(
        "\ndef validate_phase_b_stitch_slot_authority", 1
    )[0]
    assert 'PLAYBACK_BAKE_FAILED' in block
    assert "STITCH_PLAYBACK_BAKE_FAILED" in block
