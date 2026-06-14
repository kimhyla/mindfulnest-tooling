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


def test_validate_element_bound_voice_prompt_rejects_generic_tags():
    from tools import kling_o3_prompt as o3p

    bad = '@Image1 (Tessa) <<<voice_1>>> speaks: "Hi"'
    errs = o3p.validate_element_bound_voice_prompt("Tessa", bad)
    assert any("<<<voice_" in e for e in errs)


def test_validate_element_bound_voice_prompt_accepts_locked_delivery():
    from tools import kling_o3_prompt as o3p

    good = (
        'Tessa speaks in a warm gentle conversational pace, soft and vulnerable but clear: "Hello?"'
    )
    assert o3p.validate_element_bound_voice_prompt("Tessa", good) == []


TESSA_EVENT2_VOICE_LINE = (
    "Tessa speaks in a warm gentle conversational pace, soft and vulnerable but clear, "
    "natural delivery, steady and not slow, not dragging, not whispered, not childlike or "
    "baby-talk: [curious, wary of danger] Hello there ... how are you?"
)


def test_extract_unquoted_tessa_voice_line_not_beat_plan_fallback():
    spoken = bg.extract_spoken_dialogue_from_kling_prompt(TESSA_EVENT2_VOICE_LINE)
    assert spoken == "Hello there . how are you?"
    assert spoken != "Hello ."


def test_inject_locked_voice_preserves_delivery_and_quotes_spoken():
    from kling_o3_element_beat_pipeline import _inject_locked_voice

    stored = (
        "@Image1 (Tessa) Scene.\n\n"
        f"{TESSA_EVENT2_VOICE_LINE}\n\n"
        "Children's illustrated fantasy storybook style."
    )
    locked = _inject_locked_voice(stored, "Tessa", "Hello there . how are you?")
    assert "speaks in a warm gentle conversational pace" in locked
    assert '"Hello there . how are you?"' in locked
    assert "Hello ." not in locked
    assert "[curious, wary of danger]" not in locked


def test_element_o3_submit_prompt_is_sidecar_verbatim():
    from kling_o3_element_beat_pipeline import resolve_element_o3_submit_prompt

    stored = (
        "@Image1 (Tessa) Scene.\n\n"
        f"{TESSA_EVENT2_VOICE_LINE}\n\n"
        "Audio: spoken character dialogue only — absolutely no background music.\n"
        "Silent world except speech."
    )
    beat = {
        "speaker": "Tessa",
        "kling_o3_prompt": stored,
        "dialogue_text": "Hello ... [wave]",
    }
    prompt, spoken = resolve_element_o3_submit_prompt(beat)
    assert prompt == stored
    assert spoken == "Hello there . how are you?"
    assert "Hello ." not in spoken


def test_event_dir_uses_mn_prod_root(monkeypatch):
    from kling_o3_element_beat_pipeline import _event_dir_for_segment, _runtime_prod_root

    dropbox = Path("/tmp/dropbox_production")
    monkeypatch.setenv("MN_PROD_ROOT", str(dropbox))
    assert _runtime_prod_root() == dropbox.resolve()
    assert _event_dir_for_segment(_runtime_prod_root(), "event_2_pre").resolve() == (dropbox / "Event_2").resolve()
