"""Beat Gen O3 voice-first paid-submit / spend / finalize contracts."""
from __future__ import annotations

from pathlib import Path

import arlo_o3_voice_pipeline as pipe


TOOLS = Path(__file__).resolve().parent.parent
SRC = TOOLS / "arlo_o3_voice_pipeline.py"


def test_voice_first_finalize_reloads_sidecar_not_undefined_sc() -> None:
    text = SRC.read_text(encoding="utf-8")
    assert "sc_for_sync = bg_mod.read_sidecar()" in text
    assert "sync_o3_selection_pipeline_fields(beat, sc_for_sync)" in text
    assert "sync_o3_selection_pipeline_fields(beat, sc)" not in text


def test_voice_first_charges_provider_tasks_on_acceptance() -> None:
    text = SRC.read_text(encoding="utf-8")
    assert "def _charge_known_provider_task" in text
    assert 'category="kling_animation"' in text
    assert 'category="lipsync"' in text
    assert "PaidSubmissionUnknownError" in text
    assert "PAID_SUBMISSION_UNKNOWN" in text


def test_charge_known_provider_task_is_idempotent(tmp_path: Path) -> None:
    event = tmp_path / "Event_3"
    event.mkdir()
    for _ in range(2):
        pipe._charge_known_provider_task(
            event,
            category="lipsync",
            amount=0.35,
            task_id="task-abc",
            beat_id="beat_01",
            stage="lipsync",
        )
    ledger = (event / "spend_ledger.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(ledger) == 1
    assert "task-abc" in ledger[0]
