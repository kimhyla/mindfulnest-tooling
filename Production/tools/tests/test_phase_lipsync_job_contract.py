"""Phase A/B module lipsync job contract — server + UI parity."""
from __future__ import annotations

from pathlib import Path

import phase_lipsync_job_contract as contract

TOOLS = Path(__file__).resolve().parent.parent
PRODUCER = TOOLS / "storyboard-v2" / "src" / "components" / "phase" / "PhaseProducer.tsx"
TS_CONTRACT = TOOLS / "storyboard-v2" / "src" / "phaseLipsyncJobContract.ts"


def test_phase_lipsync_job_busy_requires_task_id_for_polling() -> None:
    assert contract.phase_lipsync_job_busy("polling", "tid_123") is True
    assert contract.phase_lipsync_job_busy("polling", None) is False
    assert contract.phase_lipsync_job_busy("polling", "") is False


def test_phase_lipsync_job_busy_running_without_task_id() -> None:
    assert contract.phase_lipsync_job_busy("running", None) is True


def test_phase_lipsync_job_busy_rejected_not_in_flight() -> None:
    assert contract.phase_lipsync_job_busy("rejected", "stale_tid") is False


def test_phase_lipsync_terminal_banner_rejected() -> None:
    msg = contract.phase_lipsync_terminal_banner("rejected", "b")
    assert msg is not None
    assert "cleared" in msg.lower()


def test_phase_producer_derives_busy_from_contract_only() -> None:
    src = PRODUCER.read_text(encoding="utf-8")
    assert "phaseLipsyncJobContract" in src
    assert "phaseLipsyncJobBusy" in src
    assert "lipsyncing" not in src
    assert "setLipsyncing" not in src
    assert "lipsyncMtimeBefore" not in src
    assert "lipsync_task_id" in src


def test_ts_contract_exports_job_busy() -> None:
    src = TS_CONTRACT.read_text(encoding="utf-8")
    assert "export function phaseLipsyncJobBusy" in src
    assert "rejected" in src
