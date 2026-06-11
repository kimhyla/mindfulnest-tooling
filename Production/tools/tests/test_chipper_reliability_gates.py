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


def test_phase_a_handler_uses_bytedance_base_clip_path() -> None:
    src = (TOOLS / "server_handlers" / "phases.py").read_text(encoding="utf-8")
    assert "run_phase_a_base_clip_bytedance_lipsync" in src
    assert 'lipsync_method = "base_clip_bytedance_tight_v1"' in src
    assert "run_phase_a_base_clip_lipsync(" not in src
    assert "auto-stitch skipped until visual gates pass" in src


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
