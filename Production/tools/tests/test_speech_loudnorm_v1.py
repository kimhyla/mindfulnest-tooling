"""AUTO_LOUDNORM_V1 — speech loudnorm unit + source guards."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_speech_loudnorm_module_exports_recipe() -> None:
    src = _read("server_handlers/speech_loudnorm.py")
    assert "STITCH_SPEECH_LOUDNORM_V1" in src
    assert "apply_speech_loudnorm_to_mp4" in src
    assert "loudnorm=I=" in src
    assert "-c:v copy" in src


def test_layer_a_hook_in_beat_export() -> None:
    src = _read("beat_generator.py")
    assert "apply_speech_loudnorm_export_beat_clip" in src
    block = src.split("def resolve_segment_stitch_export_clip_paths", 1)[1].split("\ndef ", 1)[0]
    assert "apply_speech_loudnorm_export_beat_clip" in block


def test_layer_b_hook_pre_mix_not_post() -> None:
    pipe = _read("production_server.py")
    block = pipe.split("def _stitch_build_pipeline", 1)[1].split("\n    def ", 1)[0]
    mix_idx = block.index("_stitch_mix_slot_audio")
    ln_idx = block.index("apply_speech_loudnorm_to_mp4")
    assert ln_idx < mix_idx, "speech loudnorm must run before _stitch_mix_slot_audio"


def test_mix_slot_audio_preserves_ambient_volume_constant() -> None:
    mix = _read("production_server.py").split("def _stitch_mix_slot_audio", 1)[1].split("\n    def ", 1)[0]
    editor = _read("server_handlers/stitch_editor.py")
    assert "STITCH_AMBIENT_BED_VOLUME" in mix
    assert "normalize=0" in mix or "normalize=0" in editor


def test_manual_loudnorm_uses_shared_helper() -> None:
    src = _read("server_handlers/stitch_editor.py")
    block = src.split("def handle_stitch_loudnorm", 1)[1].split("\ndef ", 1)[0]
    assert "apply_speech_loudnorm_to_mp4" in block


def test_layer_b_skips_kling_o3_export_paths() -> None:
    src = _read("server_handlers/speech_loudnorm.py")
    assert "slot_video_skips_layer_b_speech_loudnorm" in src
    assert "_kling_o3_" in src


def test_tech_spec_present() -> None:
    spec = Path(__file__).resolve().parents[2] / "docs" / "TECH_SPEC_AUTO_LOUDNORM_V1.md"
    assert spec.is_file()
    text = spec.read_text(encoding="utf-8")
    assert "STITCH_SPEECH_LOUDNORM_V1" in text
    assert "volume=0.15" in text or "0.15" in text
