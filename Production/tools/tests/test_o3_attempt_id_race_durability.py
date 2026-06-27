"""O3 attempt_id must survive session-state GET while subprocess checkpoints."""
from __future__ import annotations

from pathlib import Path


def test_session_state_read_only_no_heal_persist_race():
    src = (
        Path(__file__).resolve().parent.parent / "server_handlers" / "background.py"
    ).read_text(encoding="utf-8")
    block = src.split("def handle_bg_session_state", 1)[1].split("\ndef ", 1)[0]
    assert "persist_heals" not in block
    assert "_apply_session_heal_deltas" not in block
    assert "_enrich_beats_job_busy" in block


def test_o3_pipeline_heals_attempt_id_on_job_match():
    src = (
        Path(__file__).resolve().parent.parent / "kling_o3_element_beat_pipeline.py"
    ).read_text(encoding="utf-8")
    assert "MN_O3_ATTEMPT_ID" in src
    assert "heal_attempt" in src
    assert 'ui_job == job_id' in src
