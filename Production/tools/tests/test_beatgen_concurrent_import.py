"""S6 (H3) — parallel import POSTs must not tear kling_o3_options."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pytest

import beat_generator as bg
from beatgen_scope import build_event_production_scope
from lib.beatgen_store import BeatgenStore


def _setup_event3(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, str]:
    event_dir = tmp_path / "Event_3"
    (event_dir / "kling_o3_clips").mkdir(parents=True)
    db = tmp_path / "beatgen_event3.db"
    sidecar = event_dir / "beat_generator_sidecar.json"
    beat_id = "bg_arc1_event3_pre_beat_10"
    sidecar.write_text(
        json.dumps(
            {
                "arcs": {
                    "arc_1": {
                        "segments": {
                            "event_3_pre": {
                                "beats": [
                                    {
                                        "beat_id": beat_id,
                                        "pipeline": "still_insert",
                                        "kling_o3_options": [],
                                    }
                                ],
                            },
                        },
                    },
                },
            },
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MN_BEATGEN_DB_PATH", str(db))
    monkeypatch.setenv("MN_SIDECAR_SQLITE_AUTHORITY", "1")
    monkeypatch.setenv("MN_BEATGEN_SERVER_WRITER", "1")
    monkeypatch.setattr(bg, "bootstrap_sqlite_from_legacy_global_db", lambda *_a, **_k: 0)
    BeatgenStore.reset_singleton_for_tests()
    bg.reset_bg_paths_activation_for_tests()
    bg.init_bg_paths(str(event_dir), clear_milestone_scope=True)
    bg._beatgen_store().import_from_dict(json.loads(sidecar.read_text()), replace=True)
    return event_dir, beat_id


def test_sequential_import_distinct_slots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event_dir, beat_id = _setup_event3(tmp_path, monkeypatch)
    scope = build_event_production_scope(event_dir)
    for slot in (0, 1):
        delivery = tmp_path / f"delivery_{slot}.mp4"
        delivery.write_bytes(f"fake-mp4-{slot}".encode())
        ok, _beat = bg.import_delivery_clip_to_beat(
            beat_id=beat_id,
            delivery_mp4=delivery,
            slot_index=slot,
            label=f"slot {slot}",
            make_active=False,
            event_dir=event_dir,
            scope=scope,
            caller="test_sequential_import",
        )
        assert ok
    import sqlite3

    row = sqlite3.connect(str(tmp_path / "beatgen_event3.db")).execute(
        "SELECT beat_json FROM beats WHERE beat_id=?",
        (beat_id,),
    ).fetchone()
    beat = json.loads(row[0])
    slots = {o.get("slot_index") for o in (beat.get("kling_o3_options") or []) if isinstance(o, dict)}
    assert slots >= {0, 1}


def test_parallel_import_distinct_slots_no_torn_options(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event_dir, beat_id = _setup_event3(tmp_path, monkeypatch)
    scope = build_event_production_scope(event_dir)
    deliveries = []
    for i in range(2):
        p = tmp_path / f"delivery_{i}.mp4"
        p.write_bytes(f"fake-mp4-{i}".encode())
        deliveries.append(p)

    def _import(slot: int, delivery: Path) -> tuple[int, bool]:
        ok, _beat = bg.import_delivery_clip_to_beat(
            beat_id=beat_id,
            delivery_mp4=delivery,
            slot_index=slot,
            label=f"slot {slot}",
            make_active=False,
            event_dir=event_dir,
            scope=scope,
            caller="test_concurrent_import",
        )
        return slot, bool(ok)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(_import, 0, deliveries[0]),
            pool.submit(_import, 1, deliveries[1]),
        ]
        results = [f.result() for f in as_completed(futures)]

    assert all(ok for _slot, ok in results)
    import sqlite3

    row = sqlite3.connect(str(tmp_path / "beatgen_event3.db")).execute(
        "SELECT beat_json FROM beats WHERE beat_id=?",
        (beat_id,),
    ).fetchone()
    assert row
    beat = json.loads(row[0])
    options = [o for o in (beat.get("kling_o3_options") or []) if isinstance(o, dict)]
    slots = {o.get("slot_index") for o in options}
    assert slots >= {0, 1}, f"expected slots {{0,1}}, got options={options}"
