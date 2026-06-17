"""O3 attempt_id must survive session-state GET while subprocess checkpoints."""
from __future__ import annotations

import re
from pathlib import Path


def test_session_state_rereads_before_sidecar_write():
    src = (
        Path(__file__).resolve().parent.parent / "server_handlers" / "background.py"
    ).read_text(encoding="utf-8")
    block = src.split("def handle_bg_session_state", 1)[1].split("\ndef ", 1)[0]
    assert "Re-read under lock before write" in block
    assert re.search(
        r"if persist_heals or ref_hydrated:.*?with bg\.sidecar_file_lock\(timeout_s=30\):"
        r".*?sidecar = bg\.read_sidecar\(\).*?bg\.write_sidecar\(sidecar\)",
        block,
        flags=re.S,
    )


def test_o3_pipeline_heals_attempt_id_on_job_match():
    src = (
        Path(__file__).resolve().parent.parent / "kling_o3_element_beat_pipeline.py"
    ).read_text(encoding="utf-8")
    assert "MN_O3_ATTEMPT_ID" in src
    assert "heal_attempt" in src
    assert 'ui_job == job_id' in src
