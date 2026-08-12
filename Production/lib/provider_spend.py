"""Ledger-first, idempotent accounting for paid provider tasks."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .atomic_json_write import atomic_json_write
from . import fcntl_compat as fcntl

LEDGER_SCHEMA_VERSION = 2
SUMMARY_APPLIED_KEYS = "_provider_ledger_applied_keys"
SUMMARY_LEDGER_VERSION = "_provider_ledger_schema_version"


def _entry_key(entry: dict[str, Any]) -> str | None:
    value = entry.get("idempotency_key") or entry.get("task_id")
    return str(value).strip() if value else None


def _read_ledger(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"malformed spend ledger row {line_number}: {path}"
            ) from exc
        if not isinstance(entry, dict) or not _entry_key(entry):
            raise ValueError(
                f"spend ledger row {line_number} has no idempotency key: {path}"
            )
        entries.append(entry)
    return entries


def _append_ledger(path: Path, entry: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _read_summary(path: Path, event_id: str) -> dict[str, Any]:
    if path.exists():
        summary = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(summary, dict):
            raise ValueError(f"spend summary is not an object: {path}")
        return summary
    return {
        "event_id": event_id,
        "budget": 10.0,
        "spent": {},
        "total_spent": 0.0,
        "budget_remaining": 10.0,
        "warnings_shown": [],
        "overrides": 0,
    }


def _write_summary(path: Path, summary: dict[str, Any]) -> None:
    atomic_json_write(str(path), summary)


def _initialize_legacy_authority(
    summary_path: Path,
    summary: dict[str, Any],
    ledger: list[dict[str, Any]],
) -> set[str]:
    """Mark pre-v2 ledger rows applied because legacy code charged them first."""
    raw = summary.get(SUMMARY_APPLIED_KEYS)
    if isinstance(raw, list):
        return {str(value) for value in raw}
    applied = {key for entry in ledger if (key := _entry_key(entry))}
    summary[SUMMARY_APPLIED_KEYS] = sorted(applied)
    summary[SUMMARY_LEDGER_VERSION] = LEDGER_SCHEMA_VERSION
    _write_summary(summary_path, summary)
    return applied


def _apply_unapplied(
    summary: dict[str, Any],
    ledger: list[dict[str, Any]],
    applied: set[str],
) -> bool:
    changed = False
    spent = summary.setdefault("spent", {})
    if not isinstance(spent, dict):
        raise ValueError("production_spend.json spent must be an object")
    for entry in ledger:
        key = _entry_key(entry)
        if key in applied:
            continue
        category = str(entry.get("category") or "").strip()
        if not category:
            raise ValueError(f"spend ledger entry {key!r} has no category")
        amount = float(entry.get("amount"))
        spent[category] = float(spent.get(category, 0.0)) + amount
        applied.add(key)
        changed = True
    if changed:
        total = sum(float(value) for value in spent.values())
        summary["total_spent"] = total
        summary["budget_remaining"] = float(summary.get("budget", 0.0)) - total
        summary[SUMMARY_APPLIED_KEYS] = sorted(applied)
        summary[SUMMARY_LEDGER_VERSION] = LEDGER_SCHEMA_VERSION
    return changed


def record_spend_once(
    event_dir: Path,
    *,
    category: str,
    amount: float,
    idempotency_key: str,
    provider_task_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append provider spend once, then heal the derived summary."""
    event_dir = Path(event_dir)
    event_id = event_dir.name
    summary_path = event_dir / "production_spend.json"
    ledger_path = event_dir / "spend_ledger.jsonl"
    lock_path = event_dir / ".state.lock"
    event_dir.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR)
    try:
        fcntl.lockf(fd, fcntl.LOCK_EX)
        ledger = _read_ledger(ledger_path)
        summary = _read_summary(summary_path, event_id)
        applied = _initialize_legacy_authority(summary_path, summary, ledger)
        known = {
            str(value)
            for entry in ledger
            for value in (_entry_key(entry), entry.get("task_id"))
            if value
        }
        if idempotency_key not in known and (
            not provider_task_id or provider_task_id not in known
        ):
            entry: dict[str, Any] = {
                "schema_version": LEDGER_SCHEMA_VERSION,
                "idempotency_key": idempotency_key,
                "task_id": provider_task_id,
                "category": category,
                "amount": float(amount),
                "charged_at": datetime.now(timezone.utc).isoformat(),
            }
            if metadata:
                entry.update(metadata)
            _append_ledger(ledger_path, entry)
            ledger.append(entry)
        if _apply_unapplied(summary, ledger, applied):
            _write_summary(summary_path, summary)
        return summary
    finally:
        try:
            fcntl.lockf(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def rebuild_spend_summary(event_dir: Path) -> dict[str, Any]:
    """Apply ledger rows left pending by a crash before summary replacement."""
    event_dir = Path(event_dir)
    summary_path = event_dir / "production_spend.json"
    ledger_path = event_dir / "spend_ledger.jsonl"
    lock_path = event_dir / ".state.lock"
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR)
    try:
        fcntl.lockf(fd, fcntl.LOCK_EX)
        ledger = _read_ledger(ledger_path)
        summary = _read_summary(summary_path, event_dir.name)
        applied = _initialize_legacy_authority(summary_path, summary, ledger)
        if _apply_unapplied(summary, ledger, applied):
            _write_summary(summary_path, summary)
        return summary
    finally:
        try:
            fcntl.lockf(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)
