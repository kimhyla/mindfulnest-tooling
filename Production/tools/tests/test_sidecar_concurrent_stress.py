"""SIDECAR_SQLITE_AUTHORITY_V1 — concurrent patch stress (temp DB only)."""
from __future__ import annotations

import threading
from pathlib import Path

import pytest

from lib.beatgen_store import BeatgenStore


@pytest.fixture(autouse=True)
def _reset_store(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MN_SIDECAR_SQLITE_AUTHORITY", "1")
    BeatgenStore.reset_singleton_for_tests()
    yield
    BeatgenStore.reset_singleton_for_tests()


def _sample_sidecar() -> dict:
    return {
        "schema_version": 3,
        "active_context": {"arc": 1},
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_2_pre": {
                        "name": "Event 2 intro",
                        "beats": [
                            {"beat_id": "bg_arc1_event2_pre_beat_01", "speaker": "Tessa"},
                            {"beat_id": "bg_arc1_event2_pre_beat_02", "speaker": "Arlo"},
                        ],
                    }
                }
            }
        },
    }


def test_concurrent_patch_beats_no_lost_writes(tmp_path: Path) -> None:
    store = BeatgenStore(tmp_path / "beatgen.db")
    store.import_from_dict(_sample_sidecar())
    errors: list[str] = []

    def worker(beat_id: str, value: str) -> None:
        try:
            def mutator(beat, _sidecar):
                beat["stress_token"] = value

            ok, _ = store.patch_beat(beat_id, mutator)
            if not ok:
                errors.append(f"patch failed {beat_id}")
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))

    threads = [
        threading.Thread(target=worker, args=("bg_arc1_event2_pre_beat_01", "a")),
        threading.Thread(target=worker, args=("bg_arc1_event2_pre_beat_02", "b")),
        threading.Thread(target=worker, args=("bg_arc1_event2_pre_beat_01", "c")),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert not errors, errors
    out = store.assemble_sidecar_dict()
    tokens = {}
    for arc in out["arcs"].values():
        for seg in arc["segments"].values():
            for row in seg["beats"]:
                if "stress_token" in row:
                    tokens[row["beat_id"]] = row["stress_token"]
    assert tokens["bg_arc1_event2_pre_beat_01"] in {"a", "c"}
    assert tokens["bg_arc1_event2_pre_beat_02"] == "b"
