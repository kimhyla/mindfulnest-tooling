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

_DELIVERY_BY_SPEAKER: dict[str, str] = {
    "Chipper": KLING_O3_CHIPPER_VOICE_DELIVERY,
    "Arlo": KLING_O3_ARLO_VOICE_DELIVERY,
    "Tessa": KLING_O3_TESSA_VOICE_DELIVERY,
}


def voice_block(speaker: str, spoken: str) -> str:
    """Return the canonical O3 voice line for a speaker (Element-bound delivery)."""
    canon = (speaker or "Character").strip()
    delivery = _DELIVERY_BY_SPEAKER.get(canon)
    name = canon
    try:
        from tools import kling_character_registry as reg

        name = reg.get_element_name(canon) or canon
    except Exception:
        pass
    if delivery:
        return f'{name} speaks in a {delivery}: "{spoken}"'
    return f'{name} speaks clearly at a natural pace, steady and not bubbly or hyper: "{spoken}"'
