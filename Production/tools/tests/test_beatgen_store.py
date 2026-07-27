"""Tests for Beat Gen SQLite sidecar authority."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.beatgen_store import BeatgenStore, beats_equal_by_id, sqlite_authority_enabled


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
        "_runtime": {"k": "v"},
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


def test_import_and_assemble_roundtrip(tmp_path: Path, monkeypatch):
    db = tmp_path / "beatgen.db"
    store = BeatgenStore(db)
    src = _sample_sidecar()
    assert store.import_from_dict(src) == 2
    out = store.assemble_sidecar_dict()
    assert beats_equal_by_id(src, out)
    assert out["arcs"]["arc_1"]["segments"]["event_2_pre"]["name"] == "Event 2 intro"


def test_patch_beat_updates_row(tmp_path: Path):
    store = BeatgenStore(tmp_path / "beatgen.db")
    store.import_from_dict(_sample_sidecar())

    def mutator(beat, sidecar):
        beat["kling_o3_status"] = "approved"

    ok, beat = store.patch_beat("bg_arc1_event2_pre_beat_01", mutator)
    assert ok and beat["kling_o3_status"] == "approved"
    out = store.assemble_sidecar_dict()
    _, b = None, None
    for arc in out["arcs"].values():
        for seg in arc["segments"].values():
            for row in seg["beats"]:
                if row["beat_id"] == "bg_arc1_event2_pre_beat_01":
                    assert row["kling_o3_status"] == "approved"


def test_reorder_segment_beats_updates_index_only(tmp_path: Path):
    store = BeatgenStore(tmp_path / "beatgen.db")
    store.import_from_dict(_sample_sidecar())
    ok, err = store.reorder_segment_beats(
        arc_key="arc_1",
        segment_key="event_2_pre",
        beat_ids=[
            "bg_arc1_event2_pre_beat_02",
            "bg_arc1_event2_pre_beat_01",
        ],
    )
    assert ok and err is None
    out = store.assemble_sidecar_dict()
    ids = [
        b["beat_id"]
        for b in out["arcs"]["arc_1"]["segments"]["event_2_pre"]["beats"]
    ]
    assert ids == [
        "bg_arc1_event2_pre_beat_02",
        "bg_arc1_event2_pre_beat_01",
    ]
    # Partial / wrong set must fail closed (no silent truncate).
    bad_ok, bad_err = store.reorder_segment_beats(
        arc_key="arc_1",
        segment_key="event_2_pre",
        beat_ids=["bg_arc1_event2_pre_beat_01"],
    )
    assert not bad_ok and bad_err == "count_mismatch"


def test_sqlite_authority_env_flag(monkeypatch, tmp_path: Path):
    db = tmp_path / "beatgen.db"
    monkeypatch.setenv("MN_BEATGEN_DB_PATH", str(db))
    monkeypatch.delenv("MN_SIDECAR_SQLITE_AUTHORITY", raising=False)
    assert not sqlite_authority_enabled()
    BeatgenStore(db).import_from_dict(_sample_sidecar())
    assert sqlite_authority_enabled()
    monkeypatch.setenv("MN_SIDECAR_SQLITE_AUTHORITY", "0")
    assert not sqlite_authority_enabled()


def test_assemble_from_worker_thread(tmp_path: Path):
    import threading

    db = tmp_path / "beatgen.db"
    BeatgenStore.reset_singleton_for_tests()
    store = BeatgenStore(db)
    store.import_from_dict(_sample_sidecar())
    store.connect()  # main thread
    errors: list[str] = []

    def worker() -> None:
        try:
            store.assemble_sidecar_dict()
        except Exception as exc:
            errors.append(str(exc))

    t = threading.Thread(target=worker)
    t.start()
    t.join()
    assert not errors


def test_bootstrap_from_json(tmp_path: Path, monkeypatch):
    import beat_generator as bg
    from lib.beatgen_store import BeatgenStore

    BeatgenStore.reset_singleton_for_tests()
    bg.reset_bg_paths_activation_for_tests()
    json_path = tmp_path / "beat_generator_state.json"
    data = _sample_sidecar()
    json_path.write_text(json.dumps(data), encoding="utf-8")
    db = tmp_path / "state" / "beatgen.db"
    monkeypatch.setenv("MN_BEATGEN_DB_PATH", str(db))
    monkeypatch.setenv("MN_SIDECAR_SQLITE_AUTHORITY", "1")
    bg.BG_SIDECAR_PATH = str(json_path)
    monkeypatch.setattr(bg, "_BG_EVENT_DIR", None)
    count = bg.bootstrap_sqlite_sidecar_from_json()
    assert count == 2
    assert bg.sqlite_authority_enabled()
    assert beats_equal_by_id(data, bg.read_sidecar())
