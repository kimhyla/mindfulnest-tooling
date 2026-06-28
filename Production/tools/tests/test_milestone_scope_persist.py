"""Milestone scope survives server restart via server_milestone_scope.json."""
from __future__ import annotations

import json
from pathlib import Path

from lib.milestone_scope_persist import (
    clear_persisted_milestone_scope,
    read_persisted_milestone_scope,
    write_persisted_milestone_scope,
)


def test_write_read_clear_milestone_scope(tmp_path: Path):
    write_persisted_milestone_scope(
        tmp_path,
        event_id="Event_2",
        milestone_id="milestone1_arc1",
        source="test",
    )
    pin = read_persisted_milestone_scope(tmp_path, event_id="Event_2")
    assert pin is not None
    assert pin["active_milestone_id"] == "milestone1_arc1"
    path = tmp_path / "server_milestone_scope.json"
    assert path.is_file()
    data = json.loads(path.read_text())
    assert data["scope_type"] == "milestone"
    clear_persisted_milestone_scope(tmp_path)
    assert read_persisted_milestone_scope(tmp_path, event_id="Event_2") is None
