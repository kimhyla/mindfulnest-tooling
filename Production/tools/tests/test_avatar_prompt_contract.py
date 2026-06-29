"""Golden Avatar Pro prompt contract — Beat Gen parity with Phase B + Element PROHIBIT."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]


LORELAI_BEAT_02_O3 = """\
Continuity: Loral has just heard Oliver say: "You did it. I can't believe you actually did it.". Before speaking, Loral shows a brief natural reaction (attentive) — a nod, glance, or listening beat — then delivers the line.

Continuity: Loral the raccoon has just witnessed the arrival of someone unexpected.

She looks briefly surprised, and then speaks:  "Hello ... who are you?"

Match @Image1 character appearance, proportions, and facial expression exactly. Do not change the character design from @Image1.

Match the natural lighting on @Image1 to @Image2 exactly — same warm golden direction, same soft shadow depth, same color temperature on character and background. Character must look physically present in the scene, not pasted on or separately lit. No rim-light mismatch, no saturation jump between foreground and background.

Audio: spoken character dialogue only."""


def test_avatar_prompt_contract_lorelai_continuity_sidecar():
    from beat_avatar_lipsync import AVATAR_PRO_PROHIBIT, build_avatar_beat_prompt

    prompt = build_avatar_beat_prompt(
        {"kling_o3_prompt": LORELAI_BEAT_02_O3},
        speaker="Lorelai",
    )
    assert "Continuity:" not in prompt
    assert "has just heard Oliver" not in prompt
    assert AVATAR_PRO_PROHIBIT in prompt
    assert "no Chinese characters" in prompt
    assert "no subtitles" in prompt
    assert "TRIPOD LOCK" in prompt
    assert "looks briefly surprised" in prompt
    assert "input portrait of Loral" in prompt
    assert "background scene exactly" not in prompt
    assert "@Image2" not in prompt


def test_avatar_prompt_contract_matches_live_milestone_sidecar():
    import beat_generator as bg
    from beat_avatar_lipsync import build_avatar_beat_prompt

    prod = Path(
        "/Users/kimberlysmith/Library/CloudStorage/Dropbox/"
        "Claude Mindfulnest Project Files/Production"
    )
    sidecar_path = prod / "Milestones" / "milestone1_arc1" / "beat_generator_sidecar.json"
    if not sidecar_path.is_file():
        pytest.skip("Dropbox milestone sidecar not available")

    bg.init_bg_paths(
        prod / "Event_1",
        milestone_dir=prod / "Milestones" / "milestone1_arc1",
        library_event_dir=prod / "Event_1",
    )
    sc = json.loads(sidecar_path.read_text(encoding="utf-8"))
    _, beat = bg.find_beat(sc, "bg_arc1_event3b_full_beat_02")
    assert beat is not None
    prompt = build_avatar_beat_prompt(beat, speaker=beat.get("speaker", "Lorelai"))
    assert "Continuity:" not in prompt
    assert "PROHIBIT:" in prompt


def test_avatar_prompt_module_exports_prohibit_constant():
    src = (TOOLS / "beat_avatar_lipsync.py").read_text(encoding="utf-8")
    assert "AVATAR_PRO_PROHIBIT" in src
    assert "from phase_b_avatar_lipsync import AVATAR_PRO_PROHIBIT" in src
    assert "KLING_O3_LIGHTING_LOCK" not in src.split("def build_avatar_beat_prompt", 1)[1].split("\ndef ", 1)[0]
    phase_b = (TOOLS / "phase_b_avatar_lipsync.py").read_text(encoding="utf-8")
    assert "no Chinese characters" in phase_b


def test_phase_b_static_prompt_shares_avatar_pro_prohibit():
    from phase_b_avatar_lipsync import AVATAR_PRO_PROHIBIT, PHASE_B_BACKGROUND_IDLE_LOCK, STATIC_BG_PROMPT

    assert AVATAR_PRO_PROHIBIT in STATIC_BG_PROMPT
    assert PHASE_B_BACKGROUND_IDLE_LOCK in STATIC_BG_PROMPT
    assert "no Chinese characters" in STATIC_BG_PROMPT
    assert "TRIPOD LOCK" in STATIC_BG_PROMPT
    assert "Do NOT animate steam" in STATIC_BG_PROMPT
