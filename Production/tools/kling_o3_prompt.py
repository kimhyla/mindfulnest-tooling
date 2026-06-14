"""Locked Kling O3 voice delivery phrases — beat-to-beat consistency.

Same Element + kling_voice_id gives the same clone; these prompt locks keep
delivery steady and prevent bubbly/hyper reads (Chipper fix reused for Arlo).
"""

from __future__ import annotations

KLING_O3_CHIPPER_VOICE_DELIVERY = (
    "warm calm conversational pace, steady and natural, clear delivery, "
    "brisk but not rushed, not bubbly or hyper, not slow, not dramatic, not childlike or baby-talk"
)

# Arlo shares Chipper1 create-voice today; use identical delivery lock until Arlo gets his own clone.
KLING_O3_ARLO_VOICE_DELIVERY = KLING_O3_CHIPPER_VOICE_DELIVERY

KLING_O3_TESSA_VOICE_DELIVERY = (
    "warm gentle conversational pace, soft and vulnerable but clear, natural delivery, "
    "steady and not slow, not dragging, not whispered, not childlike or baby-talk"
)

KLING_O3_LORELAI_VOICE_DELIVERY = (
    "warm excited conversational pace, clear scholarly delivery, measured deliberate cadence, "
    "slower steady rhythm, not rushed or frantic, not hyper or sputtering, "
    "not dragging, not childlike or baby-talk"
)

_DELIVERY_BY_SPEAKER: dict[str, str] = {
    "Chipper": KLING_O3_CHIPPER_VOICE_DELIVERY,
    "Arlo": KLING_O3_ARLO_VOICE_DELIVERY,
    "Tessa": KLING_O3_TESSA_VOICE_DELIVERY,
    "Lorelai": KLING_O3_LORELAI_VOICE_DELIVERY,
    "Laurel": KLING_O3_LORELAI_VOICE_DELIVERY,
}


def _voice_line_display_name(speaker: str, element_name: str | None) -> str:
    canon = (speaker or "").strip()
    if canon in ("Lorelai", "Laurel"):
        return "Laurel"
    return (element_name or canon or "Character").strip()


def voice_block(speaker: str, spoken: str) -> str:
    """Return the canonical O3 voice line for a speaker (Element-bound delivery)."""
    canon = (speaker or "Character").strip()
    delivery = _DELIVERY_BY_SPEAKER.get(canon)
    element_name = canon
    try:
        from tools import kling_character_registry as reg

        element_name = reg.get_element_name(canon) or canon
    except Exception:
        pass
    voice_name = _voice_line_display_name(canon, element_name)
    if delivery:
        return f'{voice_name} speaks in a {delivery}: "{spoken}"'
    return f'{voice_name} speaks clearly at a natural pace, steady and not bubbly or hyper: "{spoken}"'


def validate_element_bound_voice_prompt(speaker: str, prompt: str) -> list[str]:
    """Hard gates before O3 Pro + element_list — generic TTS if these fail."""
    errors: list[str] = []
    try:
        from tools import kling_character_registry as reg

        if not reg.is_speaker_voice_ready(speaker):
            return errors
    except Exception:
        return errors
    text = (prompt or "").strip()
    lower = text.lower()
    if not text:
        errors.append("empty prompt")
        return errors
    if "<<<voice_" in lower:
        errors.append("prompt contains <<<voice_N>>> (generic Kling TTS tags)")
    if "speaks in a" not in lower:
        errors.append("prompt missing locked Element delivery line (speaks in a …)")
    delivery = _DELIVERY_BY_SPEAKER.get((speaker or "").strip())
    if delivery and delivery.split(",")[0].strip().lower() not in lower:
        errors.append("prompt missing canonical delivery adjectives for this speaker")
    return errors
