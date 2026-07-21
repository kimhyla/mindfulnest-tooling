"""Ledger-first paid-provider spend accounting contracts."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from Production.lib.provider_spend import (
    SUMMARY_APPLIED_KEYS,
    rebuild_spend_summary,
    record_spend_once,
)


def _write_summary(event_dir: Path, *, lipsync: float = 0.0) -> None:
    event_dir.mkdir(parents=True)
    (event_dir / "production_spend.json").write_text(
        json.dumps(
            {
                "event_id": event_dir.name,
                "budget": 10.0,
                "spent": {"lipsync": lipsync},
                "total_spent": lipsync,
                "budget_remaining": 10.0 - lipsync,
                "warnings_shown": [],
                "overrides": 0,
            }
        ),
        encoding="utf-8",
    )


def test_provider_task_is_charged_exactly_once(tmp_path: Path) -> None:
    event_dir = tmp_path / "Event_3"
    _write_summary(event_dir)

    first = record_spend_once(
        event_dir,
        category="lipsync",
        amount=0.35,
        idempotency_key="wavespeed:lipsync:task-1",
        provider_task_id="task-1",
    )
    second = record_spend_once(
        event_dir,
        category="lipsync",
        amount=0.35,
        idempotency_key="wavespeed:lipsync:task-1",
        provider_task_id="task-1",
    )

    assert first["spent"]["lipsync"] == pytest.approx(0.35)
    assert second["spent"]["lipsync"] == pytest.approx(0.35)
    rows = (event_dir / "spend_ledger.jsonl").read_text().splitlines()
    assert len(rows) == 1


def test_rebuild_applies_row_left_by_crash_before_summary_write(
    tmp_path: Path,
) -> None:
    event_dir = tmp_path / "Event_3"
    _write_summary(event_dir)
    # Initialize v2 summary authority with an empty ledger.
    rebuild_spend_summary(event_dir)
    entry = {
        "schema_version": 2,
        "idempotency_key": "wavespeed:lipsync:task-crash",
        "task_id": "task-crash",
        "category": "lipsync",
        "amount": 0.35,
    }
    (event_dir / "spend_ledger.jsonl").write_text(
        json.dumps(entry) + "\n",
        encoding="utf-8",
    )

    rebuilt = rebuild_spend_summary(event_dir)
    repeated = rebuild_spend_summary(event_dir)

    assert rebuilt["spent"]["lipsync"] == pytest.approx(0.35)
    assert repeated["spent"]["lipsync"] == pytest.approx(0.35)
    assert "wavespeed:lipsync:task-crash" in rebuilt[SUMMARY_APPLIED_KEYS]


def test_legacy_summary_first_row_is_migrated_without_double_charge(
    tmp_path: Path,
) -> None:
    event_dir = tmp_path / "Event_3"
    _write_summary(event_dir, lipsync=0.35)
    (event_dir / "spend_ledger.jsonl").write_text(
        json.dumps(
            {
                "task_id": "legacy-task",
                "category": "lipsync",
                "amount": 0.35,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    migrated = record_spend_once(
        event_dir,
        category="lipsync",
        amount=0.35,
        idempotency_key="legacy:legacy-task",
        provider_task_id="legacy-task",
    )

    assert migrated["spent"]["lipsync"] == pytest.approx(0.35)
    assert len((event_dir / "spend_ledger.jsonl").read_text().splitlines()) == 1


def test_malformed_ledger_fails_closed(tmp_path: Path) -> None:
    event_dir = tmp_path / "Event_3"
    _write_summary(event_dir)
    (event_dir / "spend_ledger.jsonl").write_text("{broken\n", encoding="utf-8")

    with pytest.raises(ValueError, match="malformed spend ledger"):
        rebuild_spend_summary(event_dir)
