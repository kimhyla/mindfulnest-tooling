"""Arlo registry must stay pinned to Event 1 Beat 10 proven O3 bind."""
from __future__ import annotations

import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from phase_a_chipper_lipsync_base import ARLO_ELEMENT_ID

ARLO_CANONICAL_VOICE_ID = "893833801724461134"
WRONG_CHIPPER_VOICE_ID = "891326025224429589"


def test_character_subjects_arlo_pins_event1_bind() -> None:
    reg_path = TOOLS.parent / "character_subjects.json"
    data = json.loads(reg_path.read_text(encoding="utf-8"))
    arlo = data["characters"]["Arlo"]
    assert arlo["element_id"] == ARLO_ELEMENT_ID
    assert arlo["kling_voice_id"] == ARLO_CANONICAL_VOICE_ID
    assert arlo["kling_voice_id"] != WRONG_CHIPPER_VOICE_ID


def test_kling_registry_get_bound_voice_id_arlo() -> None:
    import kling_character_registry as reg

    reg.set_prod_root(TOOLS.parent)
    assert reg.get_bound_voice_id("Arlo") == ARLO_CANONICAL_VOICE_ID
    entry = reg.get_element_list_entry("Arlo")
    assert entry is not None
    assert entry["element_id"] == ARLO_ELEMENT_ID
    assert entry["voice_id"] == ARLO_CANONICAL_VOICE_ID
