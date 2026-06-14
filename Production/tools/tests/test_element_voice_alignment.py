"""Element @Image1 alignment gates — bound voice requires Element pose set."""
from __future__ import annotations

import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

import beat_generator as bg  # noqa: E402


def test_align_beat_reference_tessa_prefers_element_canonical(tmp_path: Path, monkeypatch):
    canonical = tmp_path / "tessa_event1_canonical.png"
    library = tmp_path / "library_still.png"
    canonical.write_bytes(b"canonical")
    library.write_bytes(b"library")

    def fake_element_paths(_speaker: str):
        return [canonical]

    monkeypatch.setattr(
        "tools.kling_character_registry.element_image_paths",
        fake_element_paths,
    )
    monkeypatch.setattr(
        "tools.kling_character_registry.get_character_entry",
        lambda _s: {"status": "active", "element_id": "123"},
    )

    beat = {
        "speaker": "Tessa",
        "emotion": "curious, polite",
        "reference_image": {"abs_path": str(library)},
    }
    assert bg.align_beat_reference_to_element(beat) is True
    assert beat["reference_image"]["abs_path"] == str(canonical.resolve())


def test_extract_spoken_used_for_element_prompt_inject():
    from kling_o3_element_beat_pipeline import _inject_locked_voice

    stored = (
        "@Image1 (Tessa) Scene.\n\n"
        "Tessa speaks warmly and politely: [curious, polite] Hello .\n\n"
        "Children's illustrated fantasy storybook style."
    )
    locked = _inject_locked_voice(stored, "Tessa", "Hello .")
    assert "speaks in a warm gentle conversational pace" in locked
    assert "speaks warmly and politely" not in locked
    assert "<<<voice_" not in locked
