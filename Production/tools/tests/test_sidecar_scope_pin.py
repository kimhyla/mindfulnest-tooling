"""SIDECAR_SCOPE_PIN_V1 — RMW transactions must abort when Beat Gen scope rebinds mid-flight.

Proven corruption (2026-07-17, Event_2 :5112): a long session-state migrate held
the sidecar lock under Event_2 SQLite scope while /api/milestones/load rebound
BG_SIDECAR_PATH to Milestones/milestone1_arc1; the transaction's final write
dumped the Event_2 assembly into the milestone sidecar (then isolation stripped
the alien segments → 0 beats → recurring milestone data loss at deploy smoke h.6).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import beat_generator as bg  # noqa: E402


def _sample_sidecar() -> dict:
    return {
        "schema_version": 3,
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_2_pre": {
                        "name": "Event 2 intro",
                        "beats": [
                            {"beat_id": "bg_arc1_event2_pre_beat_01", "speaker": "Tessa"},
                        ],
                    }
                }
            }
        },
    }


@pytest.fixture()
def json_scope(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """JSON-authority Beat Gen bound to a temp event sidecar."""
    monkeypatch.setenv("MN_SIDECAR_SQLITE_AUTHORITY", "0")
    event_sidecar = tmp_path / "Event_2" / "beat_generator_sidecar.json"
    event_sidecar.parent.mkdir(parents=True)
    event_sidecar.write_text(json.dumps(_sample_sidecar()), encoding="utf-8")
    milestone_sidecar = tmp_path / "Milestones" / "milestone1_arc1" / "beat_generator_sidecar.json"
    milestone_sidecar.parent.mkdir(parents=True)
    milestone_sidecar.write_text(json.dumps({"schema_version": 3, "arcs": {}}), encoding="utf-8")

    monkeypatch.setattr(bg, "BG_SIDECAR_PATH", str(event_sidecar))
    monkeypatch.setattr(bg, "BG_SIDECAR_MIRROR_PATH", str(event_sidecar))
    monkeypatch.setattr(bg, "_MILESTONE_SIDECAR_JSON_ONLY", False)
    return event_sidecar, milestone_sidecar


def _rebind_to_milestone(milestone_sidecar: Path) -> None:
    bg.BG_SIDECAR_PATH = str(milestone_sidecar)
    bg._MILESTONE_SIDECAR_JSON_ONLY = True


def test_mutate_sidecar_locked_aborts_on_mid_transaction_rebind(json_scope) -> None:
    event_sidecar, milestone_sidecar = json_scope
    milestone_before = milestone_sidecar.read_text(encoding="utf-8")

    def mutator(sidecar: dict) -> None:
        # Simulates /api/milestones/load rebinding scope while this
        # transaction holds the sidecar lock.
        _rebind_to_milestone(milestone_sidecar)
        sidecar["polluted"] = True

    with pytest.raises(RuntimeError, match="SIDECAR_SCOPE_PIN_V1"):
        bg.mutate_sidecar_locked(mutator, caller="test_mid_transaction_rebind")

    # Neither file got the cross-scope payload.
    assert milestone_sidecar.read_text(encoding="utf-8") == milestone_before
    assert "polluted" not in json.loads(event_sidecar.read_text(encoding="utf-8"))


def test_update_beat_locked_aborts_on_mid_transaction_rebind(json_scope) -> None:
    event_sidecar, milestone_sidecar = json_scope
    milestone_before = milestone_sidecar.read_text(encoding="utf-8")

    def mutator(beat: dict, _sidecar: dict) -> None:
        _rebind_to_milestone(milestone_sidecar)
        beat["polluted"] = True

    with pytest.raises(RuntimeError, match="SIDECAR_SCOPE_PIN_V1"):
        bg.update_beat_locked(
            "bg_arc1_event2_pre_beat_01",
            mutator,
            caller="test_mid_transaction_rebind",
            skip_single_writer_gate=True,
        )

    assert milestone_sidecar.read_text(encoding="utf-8") == milestone_before


def test_delete_beat_locked_aborts_on_mid_transaction_rebind(json_scope, monkeypatch) -> None:
    event_sidecar, milestone_sidecar = json_scope
    milestone_before = milestone_sidecar.read_text(encoding="utf-8")

    original_read = bg.read_sidecar

    def read_then_rebind():
        data = original_read()
        _rebind_to_milestone(milestone_sidecar)
        return data

    monkeypatch.setattr(bg, "read_sidecar", read_then_rebind)

    with pytest.raises(RuntimeError, match="SIDECAR_SCOPE_PIN_V1"):
        bg.delete_beat_locked(
            "bg_arc1_event2_pre_beat_01",
            caller="test_mid_transaction_rebind",
        )

    assert milestone_sidecar.read_text(encoding="utf-8") == milestone_before
    # Event sidecar untouched — beat still present.
    data = json.loads(event_sidecar.read_text(encoding="utf-8"))
    beats = data["arcs"]["arc_1"]["segments"]["event_2_pre"]["beats"]
    assert [b["beat_id"] for b in beats] == ["bg_arc1_event2_pre_beat_01"]


def test_mutate_sidecar_locked_writes_when_scope_stable(json_scope) -> None:
    event_sidecar, _milestone_sidecar = json_scope

    def mutator(sidecar: dict) -> None:
        sidecar["stable_write"] = True

    bg.mutate_sidecar_locked(mutator, caller="test_scope_stable")
    assert json.loads(event_sidecar.read_text(encoding="utf-8"))["stable_write"] is True
