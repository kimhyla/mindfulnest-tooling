"""Event state/spend/media authority must switch as one unit."""
from __future__ import annotations

import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import production_server as ps  # noqa: E402


def test_rebind_event_moves_every_event_scoped_authority(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(ps, "SINGLE_MACHINE_MODE", True)
    event_1 = tmp_path / "Event_1"
    event_2 = tmp_path / "Event_2"
    manager = ps.StateManager(event_1, "Event_1")

    old_state_path = manager.state_path
    old_spend_path = manager.spend_path
    old_ledger_path = manager.spend_ledger_path
    old_lock_path = manager.file_lock_path
    old_clips_dir = manager.clips_dir

    manager.rebind_event(event_2, "Event_2")

    assert manager.event_dir == event_2
    assert manager.event_id == "Event_2"
    assert manager.state_path == event_2 / "production_state.json"
    assert manager.repo.state_path == manager.state_path
    assert manager.spend_path == event_2 / "production_spend.json"
    assert manager.spend_ledger_path == event_2 / "spend_ledger.jsonl"
    assert manager.file_lock_path == event_2 / ".state.lock"
    assert manager.clips_dir == event_2 / "animation_clips"
    assert manager.directus_lock_key == "Event_2/state"

    assert old_state_path == event_1 / "production_state.json"
    assert old_spend_path == event_1 / "production_spend.json"
    assert old_ledger_path == event_1 / "spend_ledger.jsonl"
    assert old_lock_path == event_1 / ".state.lock"
    assert old_clips_dir == event_1 / "animation_clips"

    assert manager.state_path.is_file()
    assert manager.spend_path.is_file()
    assert manager.file_lock_path.is_file()
    assert manager.clips_dir.is_dir()
    assert json.loads(manager.spend_path.read_text())["event_id"] == "Event_2"


def test_event_instance_id_is_durable_and_event_local(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(ps, "SINGLE_MACHINE_MODE", True)
    event_1 = tmp_path / "Event_1"
    event_2 = tmp_path / "Event_2"
    manager = ps.StateManager(event_1, "Event_1")

    event_1_instance = manager.ensure_event_instance_id()
    assert manager.ensure_event_instance_id() == event_1_instance
    assert json.loads(manager.state_path.read_text())["event_instance_id"] == event_1_instance

    manager.rebind_event(event_2, "Event_2")
    event_2_instance = manager.ensure_event_instance_id()

    assert event_2_instance != event_1_instance
    assert json.loads(manager.state_path.read_text())["event_instance_id"] == event_2_instance
    assert json.loads((event_1 / "production_state.json").read_text())[
        "event_instance_id"
    ] == event_1_instance


def test_rebind_preparation_failure_leaves_old_authority(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manager = ps.StateManager(tmp_path / "Event_1", "Event_1")
    original = {
        "event_dir": manager.event_dir,
        "state_path": manager.state_path,
        "spend_path": manager.spend_path,
        "ledger_path": manager.spend_ledger_path,
        "lock_path": manager.file_lock_path,
        "directus_key": manager.directus_lock_key,
    }

    def _fail_identity(_self) -> str:
        raise OSError("injected target preparation failure")

    monkeypatch.setattr(ps.StateManager, "ensure_event_instance_id", _fail_identity)

    try:
        manager.rebind_event(tmp_path / "Event_2", "Event_2")
    except OSError as exc:
        assert "injected" in str(exc)
    else:
        raise AssertionError("rebind unexpectedly succeeded")

    assert manager.event_dir == original["event_dir"]
    assert manager.state_path == original["state_path"]
    assert manager.spend_path == original["spend_path"]
    assert manager.spend_ledger_path == original["ledger_path"]
    assert manager.file_lock_path == original["lock_path"]
    assert manager.directus_lock_key == original["directus_key"]


def test_state_manager_task_spend_is_ledger_first_and_idempotent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(ps, "SINGLE_MACHINE_MODE", True)
    manager = ps.StateManager(tmp_path / "Event_3", "Event_3")

    manager.add_spend("lipsync", 0.35, task_id="task-state-manager")
    repeated = manager.add_spend(
        "lipsync",
        0.35,
        task_id="task-state-manager",
    )

    assert repeated["spent"]["lipsync"] == 0.35
    rows = manager.spend_ledger_path.read_text().splitlines()
    assert len(rows) == 1
    assert "task-state-manager" in rows[0]
