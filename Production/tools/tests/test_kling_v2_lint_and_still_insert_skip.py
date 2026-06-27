"""Kling V2 lint — still-insert skip + legacy prompt heal."""
from __future__ import annotations

from kling_o3_prompt import kling_o3_prompt_passes_v2_lint


def test_v2_lint_rejects_legacy_verbatim_dialogue() -> None:
    assert kling_o3_prompt_passes_v2_lint("[awed] Wow ... look at this ...") is False


def test_v2_lint_accepts_canonical_header() -> None:
    prompt = (
        "@Image1 (Tessa). Scene from @Image2.\n\n"
        'Tessa speaks in a warm calm conversational pace: [curious] "Hello."'
    )
    assert kling_o3_prompt_passes_v2_lint(prompt) is True


def test_heal_legacy_skips_still_insert_pipeline() -> None:
    import beat_generator as bg

    beat = {
        "beat_id": "bg_arc1_event2_pre_beat_31",
        "speaker": "Tessa",
        "pipeline": "still_insert",
        "kling_o3_prompt": "[awed] Wow ... look at this ...",
        "dialogue_text": "Wow . look at this .",
    }
    assert bg.heal_legacy_kling_o3_prompt_v2_shape(beat) is False
    assert beat["kling_o3_prompt"] == "[awed] Wow ... look at this ..."


def test_smoke_script_skips_beat_is_still_insert() -> None:
    from pathlib import Path

    text = (Path(__file__).resolve().parents[2] / "scripts" / "smoke_kling_canonical_prompt_shape_live.sh").read_text(
        encoding="utf-8",
    )
    assert "beat_is_still_insert" in text
    assert "is_still_insert_prompt_text" in text
