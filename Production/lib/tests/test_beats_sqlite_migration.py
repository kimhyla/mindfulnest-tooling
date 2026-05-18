"""Tests for V59 Phase 9 — beats JSON ↔ SQLite migration."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
import pytest

_TOOLING_REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_TOOLING_REPO))
sys.path.insert(0, str(_TOOLING_REPO / "Production"))

from Production.scripts import migrate_beats_to_json as down_mod  # noqa: E402
from Production.scripts import migrate_beats_to_sqlite as up_mod  # noqa: E402


def _write_state(event_dir: Path, beats_by_role: dict[str, dict[str, dict]]) -> None:
    videos = {
        role: {"beats": beats}
        for role, beats in beats_by_role.items()
    }
    state = {
        "event_id": event_dir.name,
        "version": "v2",
        "videos": videos,
    }
    event_dir.mkdir(parents=True, exist_ok=True)
    (event_dir / "production_state.json").write_text(
        json.dumps(state, indent=2),
        encoding="utf-8",
    )


def test_migration_creates_correct_row_count(tmp_path: Path) -> None:
    event_dir = tmp_path / "Event_test"
    _write_state(
        event_dir,
        {
            "intro": {"i1": {"id": "i1"}, "i2": {"id": "i2"}},
            "resolution": {
                "r1": {"id": "r1"},
                "r2": {"id": "r2"},
                "r3": {"id": "r3"},
            },
            "standalone": {},
        },
    )
    assert up_mod.run_migration(event_dir) == 0

    db_path = event_dir / "beats.db"
    conn = sqlite3.connect(db_path)
    try:
        count = conn.execute("SELECT COUNT(*) FROM beats").fetchone()[0]
    finally:
        conn.close()
    assert count == 5


def test_migration_is_transactional_on_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    event_dir = tmp_path / "Event_tx"
    _write_state(
        event_dir,
        {
            "intro": {"a": {"n": 1}, "b": {"n": 2}},
            "resolution": {"c": {"n": 3}},
            "standalone": {},
        },
    )

    real_dumps = json.dumps
    calls = {"n": 0}

    def flaky_dumps(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("simulated mid-migration failure")
        return real_dumps(*args, **kwargs)

    monkeypatch.setattr(up_mod.json, "dumps", flaky_dumps)

    with pytest.raises(RuntimeError, match="simulated"):
        up_mod.run_migration(event_dir, no_verify=True)

    db_path = event_dir / "beats.db"
    assert db_path.exists()
    conn = sqlite3.connect(db_path)
    try:
        count = conn.execute("SELECT COUNT(*) FROM beats").fetchone()[0]
        audit = conn.execute("SELECT COUNT(*) FROM beats_audit").fetchone()[0]
    finally:
        conn.close()
    assert count == 0
    assert audit == 0


def test_verify_pass_after_migration(tmp_path: Path) -> None:
    event_dir = tmp_path / "Event_verify"
    _write_state(
        event_dir,
        {
            "intro": {"x": {"v": 1}},
            "resolution": {"y": {"v": 2}},
            "standalone": {},
        },
    )
    assert up_mod.run_migration(event_dir) == 0
    assert up_mod.run_migration(event_dir, verify_only=True) == 0


def test_verify_detects_drift(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    event_dir = tmp_path / "Event_drift"
    _write_state(
        event_dir,
        {
            "intro": {"only": {"status": "ok"}},
            "resolution": {},
            "standalone": {},
        },
    )
    assert up_mod.run_migration(event_dir) == 0

    db_path = event_dir / "beats.db"
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT payload FROM beats WHERE beat_id = 'only'"
        ).fetchone()
        mutated = json.loads(row[0])
        mutated["status"] = "tampered"
        conn.execute(
            "UPDATE beats SET payload = ? WHERE beat_id = 'only'",
            (json.dumps(mutated),),
        )
        conn.commit()
    finally:
        conn.close()

    state = up_mod.load_state(event_dir)
    rc = up_mod.verify_beats(db_path, state, event_id=event_dir.name)
    captured = capsys.readouterr()
    assert rc == 1
    assert "VERIFY_FAIL" in captured.err


def test_down_migration_roundtrip(tmp_path: Path) -> None:
    event_dir = tmp_path / "Event_roundtrip"
    _write_state(
        event_dir,
        {
            "intro": {"a": {"phase": 1, "etag": "skip-me"}},
            "resolution": {"b": {"phase": 2}},
            "standalone": {"c": {"phase": 3}},
        },
    )
    original = json.loads((event_dir / "production_state.json").read_text(encoding="utf-8"))
    original_norm = up_mod.source_beats_map(original)

    assert up_mod.run_migration(event_dir) == 0
    sidecar = down_mod.down_migrate(event_dir)
    restored = json.loads(sidecar.read_text(encoding="utf-8"))
    restored_norm = up_mod.source_beats_map(restored)

    assert restored_norm == original_norm
