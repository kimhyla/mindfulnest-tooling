"""Regression gates for Chipper video reliability decisions."""
from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))


def test_phase_a_handler_uses_arlo_layered_not_bytedance_default() -> None:
    src = (TOOLS / "server_handlers" / "phases.py").read_text(encoding="utf-8")
    block = src.split("def handle_phase_a_lipsync", 1)[1].split("\ndef handle_phase_b_lipsync", 1)[0]
    layered = src.split("def _handle_phase_a_lipsync_layered", 1)[1].split(
        "\ndef _handle_phase_a_lipsync_bytedance", 1
    )[0]
    assert "submit_avatar_pro" not in block
    assert "run_phase_a_arlo_idle_lipsync_startend_still" not in block
    assert "PHASE_A_ARLO_LAYERED_ROUTE_V1" in block
    assert "execute_layered_job" in layered
    assert "layered_fullbody_greenscreen_kling_lipsync_v2" in layered or "ARLO_PROFILE" in layered
    assert "return _handle_phase_a_lipsync_layered" in block
    # ByteDance remains opt-in, not Send default.
    assert "_handle_phase_a_lipsync_bytedance" in block
    assert "MN_PHASE_A_BYTEDANCE" in block


def test_bytedance_chaining_is_not_default() -> None:
    import phase_a_chipper_bytedance_lipsync as bd
    import phase_a_middle_permanent as middle

    assert inspect.signature(bd.run_bytedance_tight_lipsync).parameters["chain_chunks"].default is False
    assert inspect.signature(middle.run_phase_a_base_clip_bytedance_lipsync).parameters["chain_chunks"].default is False
    assert inspect.signature(middle.run_phase_a_base_clip_bytedance_lipsync).parameters["single_pass"].default is True


def test_arlo_element_guard_blocks_stale_id(tmp_path: Path) -> None:
    from phase_a_chipper_lipsync_base import ARLO_ELEMENT_ID, assert_arlo_element

    registry = {
        "characters": {
            "Arlo": {
                "element_id": "999",
                "description": "Pixar red squirrel",
                "refer_images": ["Arlo/poses/arlo_happy_vest.png"],
            }
        }
    }
    (tmp_path / "character_subjects.json").write_text(json.dumps(registry), encoding="utf-8")

    with pytest.raises(RuntimeError, match="Unexpected Arlo element_id"):
        assert_arlo_element(tmp_path)

    registry["characters"]["Arlo"]["element_id"] = ARLO_ELEMENT_ID
    (tmp_path / "character_subjects.json").write_text(json.dumps(registry), encoding="utf-8")
    assert assert_arlo_element(tmp_path)["element_id"] == ARLO_ELEMENT_ID


def test_chipper_reliability_spec_exists() -> None:
    spec = TOOLS.parent / "docs" / "CHIPPER_VIDEO_RELIABILITY_SPEC_v1.md"
    text = spec.read_text(encoding="utf-8")
    assert "Do Not Proceed Conditions" in text
    assert "base_clip_bytedance_chained_v1" in text
    assert "needs_manual_visual_review" in text
