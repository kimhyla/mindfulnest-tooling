"""PHASE_A_PATH_A_ROUTE_V1 — handler + pipeline contract tests."""
from __future__ import annotations

from pathlib import Path

import phase_a_path_a_pipeline as pipe

TOOLS = Path(__file__).resolve().parent.parent
PHASES = TOOLS / "server_handlers" / "phases.py"


def _handler_block() -> str:
    block = PHASES.read_text(encoding="utf-8").split("def handle_phase_a_lipsync", 1)[1]
    return block.split("\ndef handle_phase_b_lipsync", 1)[0]


def test_handler_block_is_path_a_single_route():
    block = _handler_block()
    assert "PHASE_A_PATH_A_ROUTE_V1" in block
    assert "run_phase_a_path_a_lipsync" in block
    assert "validate_path_a_assets" in block
    assert "count_phase_a_path_a_chunks" in block
    assert "run_phase_a_arlo_idle_lipsync_startend_still" not in block
    assert "submit_avatar_pro" not in block


def test_handler_budget_gate_is_per_chunk():
    block = _handler_block()
    assert "COST_PER_LIPSYNC * chunk_jobs" in block


def test_pipeline_marker_and_green_key():
    assert pipe.PHASE_A_PATH_A_ROUTE_V1 == "PHASE_A_PATH_A_ROUTE_V1"
    assert "00FF00" in pipe.CHROMAKEY_GREEN or "0x00FF00" in pipe.CHROMAKEY_GREEN
    assert pipe.DEFAULT_ROTATION[0].name == "A"


def test_validate_path_a_assets_present():
    # Live Dropbox assets used by production — skip soft if missing in CI sandbox.
    try:
        pipe.validate_path_a_assets()
    except FileNotFoundError:
        # CI may not mount Dropbox; contract still requires the helper.
        assert callable(pipe.validate_path_a_assets)
        return
    assert pipe.ARLO_CUTOUT_GREEN_PNG.is_file()
    assert pipe.ARLO_ROOM_PLATE_PNG.is_file()
    assert pipe.IDLE_UNIT_A.path.is_file()
