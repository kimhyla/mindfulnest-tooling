"""O3 session-state — read-only GET + server job_busy (BG_BEAT_JOB_TRUTH_GALLERY_SPEC_v1)."""
from __future__ import annotations

import re
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
BACKGROUND = TOOLS / "server_handlers" / "background.py"


def _handler_block(name: str) -> str:
    text = BACKGROUND.read_text(encoding="utf-8")
    start = text.index(f"def {name}(")
    rest = text[start + 1 :]
    end_offset = len(rest)
    for marker in ("\ndef handle_", "\ndef _finalize", "\ndef _run_o3"):
        idx = rest.find(marker)
        if idx >= 0:
            end_offset = min(end_offset, idx)
    return text[start : start + 1 + end_offset]


def test_read_only_get_no_lifecycle_heal_chain():
    block = _handler_block("handle_bg_session_state")
    for retired in (
        "reconcile_stuck_o3_voice_beats",
        "rehydrate_o3_ui_job_ids",
        "reconcile_stale_o3_intent_locks_all_events",
        "reconcile_o3_terminal_attempt_fields_all_events",
        "_apply_session_heal_deltas",
        "persist_heals",
    ):
        assert retired not in block, f"retired heal {retired} still in session GET"


def test_session_get_runs_terminal_disk_reconcile():
    block = _handler_block("handle_bg_session_state")
    assert "_apply_o3_session_terminal_reconcile" in block
    assert "o3_terminal_outcomes" in block


def test_session_get_enriches_job_busy():
    block = _handler_block("handle_bg_session_state")
    assert "_enrich_beats_job_busy" in block
    assert "session_read_only=True" in block
    assert "read_sidecar_for_poll_snapshot" in block


def test_gallery_repair_at_startup_not_on_idle_get():
    block = _handler_block("handle_bg_session_state")
    assert "if force_reconcile_o3 and scope_event_id" in block
    src = BACKGROUND.read_text(encoding="utf-8")
    assert "def schedule_o3_gallery_repair_at_startup" in src


def test_job_busy_contract_module():
    src = (TOOLS / "o3_job_status_contract.py").read_text(encoding="utf-8")
    assert "def beat_job_busy" in src
    assert "o3_current_job_id" in src
