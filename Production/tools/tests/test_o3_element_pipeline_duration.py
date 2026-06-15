"""Regression — Element O3 pipeline must resolve duration from prompt, not default 8s."""
from __future__ import annotations

from pathlib import Path

PIPELINE = Path(__file__).resolve().parent.parent / "kling_o3_element_beat_pipeline.py"
BACKGROUND = Path(__file__).resolve().parent.parent / "server_handlers" / "background.py"


def test_element_pipeline_uses_resolve_kling_o3_submit_duration():
    text = PIPELINE.read_text(encoding="utf-8")
    assert "resolve_kling_o3_submit_duration(beat, prepared)" in text
    assert "int(beat.get(\"kling_o3_duration\") or 8)" not in text


def test_submit_arlo_o3_voice_sets_duration_before_launch():
    block = BACKGROUND.read_text(encoding="utf-8")
    start = block.index("def handle_bg_submit_arlo_o3_voice")
    end = block.index("\ndef handle_bg_", start + 1)
    section = block[start:end]
    assert "resolve_kling_o3_submit_duration" in section
    assert section.index("resolve_kling_o3_submit_duration") < section.index("subprocess.Popen")


def test_element_pipeline_uses_sidecar_gen_from_delivery_path():
    text = PIPELINE.read_text(encoding="utf-8")
    assert "bg_sidecar._kling_o3_gen_from_video_path(str(delivery))" in text
    assert "\n    recovered_gen = _kling_o3_gen_from_video_path" not in text


def test_long_dialogue_resolves_to_12s_not_8():
    import beat_generator as bg

    spoken = (
        "Guys .... she's right. The Great Wizard told me. He said there was a terrible "
        "storm in Ancient Everdale, a long time ago. Lightning struck, and... the whole "
        "system failed. The Rune Stones have been dark ever since."
    )
    prompt = f'Arlo speaks in a warm calm conversational pace: "{spoken}"'
    assert bg.resolve_kling_o3_submit_duration({}, prompt) == 12
