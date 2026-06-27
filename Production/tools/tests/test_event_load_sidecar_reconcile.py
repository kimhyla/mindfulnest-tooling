"""EVENT_LOAD_SIDECAR_RECONCILE_V1 — restore event beats after milestone polluted SQLite."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import beat_generator as bg


def test_restore_preserved_segment_beats_if_empty(tmp_path: Path) -> None:
    event_dir = tmp_path / "Event_2"
    seg_dir = (
        event_dir
        / "kling_o3_clips"
        / "_preserved"
        / "segments"
        / "arc1_event2_pre"
    )
    beats_dir = seg_dir / "beats"
    beats_dir.mkdir(parents=True)
    beats = [{"beat_id": "bg_arc1_event2_pre_beat_01", "speaker": "Lorelai"}]
    (seg_dir / "manifest.json").write_text(
        json.dumps(
            {
                "arc_number": 1,
                "event_id": "2",
                "phase": "pre",
                "name": "Event 2 pre",
                "beats": beats,
            },
        ),
    )
    sidecar: dict = {"arcs": {"arc_1": {"segments": {"event_2_pre": {"beats": []}}}}}
    n = bg.restore_preserved_segment_beats_if_empty(sidecar, event_dir, 1, "2", "pre")
    assert n == 1
    assert sidecar["arcs"]["arc_1"]["segments"]["event_2_pre"]["beats"][0]["beat_id"] == (
        "bg_arc1_event2_pre_beat_01"
    )


def test_purge_sidecar_segments_not_for_event() -> None:
    sidecar = {
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_2_pre": {"beats": [{"beat_id": "a"}]},
                    "event_3b_full": {"beats": [{"beat_id": "b"}]},
                },
            },
        },
    }
    removed = bg.purge_sidecar_segments_not_for_event(sidecar, "Event_2")
    assert "arc_1/event_3b_full" in removed
    assert "event_2_pre" in sidecar["arcs"]["arc_1"]["segments"]
    assert "event_3b_full" not in sidecar["arcs"]["arc_1"]["segments"]


def test_purge_sidecar_keeps_other_production_event_segments() -> None:
    """Event_2 event/load must not delete Event_3 beats from shared SQLite."""
    sidecar = {
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_2_pre": {"beats": [{"beat_id": "e2"}]},
                    "event_3_pre": {"beats": [{"beat_id": "e3"}]},
                    "event_3b_full": {"beats": [{"beat_id": "milestone"}]},
                },
            },
        },
    }
    removed = bg.purge_sidecar_segments_not_for_event(sidecar, "Event_2")
    assert "arc_1/event_3b_full" in removed
    assert "arc_1/event_3_pre" not in removed
    assert "event_3_pre" in sidecar["arcs"]["arc_1"]["segments"]
    assert sidecar["arcs"]["arc_1"]["segments"]["event_3_pre"]["beats"][0]["beat_id"] == "e3"


def test_reconcile_event_sidecar_after_milestone_exit(tmp_path: Path, monkeypatch) -> None:
    event_dir = tmp_path / "Event_2"
    seg_dir = (
        event_dir
        / "kling_o3_clips"
        / "_preserved"
        / "segments"
        / "arc1_event2_pre"
    )
    seg_dir.mkdir(parents=True)
    (seg_dir / "manifest.json").write_text(
        json.dumps(
            {
                "arc_number": 1,
                "event_id": "2",
                "phase": "pre",
                "beats": [{"beat_id": "bg_arc1_event2_pre_beat_01"}],
            },
        ),
    )

    store: dict = {
        "active_context": {"arc_number": 1, "event_id": "3b", "phase": "full"},
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_3b_full": {"beats": [{"beat_id": "milestone_beat"}]},
                    "event_2_pre": {"beats": []},
                },
            },
        },
    }

    def fake_mutate(fn):
        fn(store)

    monkeypatch.setattr(bg, "mutate_sidecar_locked", fake_mutate)
    monkeypatch.setattr(bg, "BG_SIDECAR_PATH", str(tmp_path / "no_mirror.json"))
    rep = bg.reconcile_event_sidecar_after_milestone_exit(event_dir, "Event_2")
    assert "event_3b_full" in str(rep["removed_segments"])
    assert rep["restored_segments"].get("arc1_event2_pre") == 1
    assert store["active_context"] == {"arc_number": 1, "event_id": "2", "phase": "pre"}
    assert len(store["arcs"]["arc_1"]["segments"]["event_2_pre"]["beats"]) == 1


def test_reconcile_event_load_merges_missing_beats_from_json_mirror(
    tmp_path: Path, monkeypatch,
) -> None:
    event_dir = tmp_path / "Event_3"
    event_dir.mkdir()
    mirror = tmp_path / "beat_generator_state.json"
    mirror.write_text(
        json.dumps(
            {
                "arcs": {
                    "arc_1": {
                        "segments": {
                            "event_3_pre": {
                                "beats": [
                                    {"beat_id": "bg_arc1_event3_pre_beat_02", "status": "approved"},
                                    {"beat_id": "bg_arc1_event3_pre_beat_08", "status": "draft"},
                                ],
                            },
                        },
                    },
                },
            },
        ),
    )
    store: dict = {
        "active_context": {"arc_number": 1, "event_id": "3", "phase": "pre"},
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_3_pre": {
                        "beats": [
                            {"beat_id": "bg_arc1_event3_pre_beat_02", "status": "approved", "kling_o3_status": "approved"},
                        ],
                    },
                },
            },
        },
    }

    def fake_mutate(fn):
        fn(store)

    monkeypatch.setattr(bg, "mutate_sidecar_locked", fake_mutate)
    monkeypatch.setattr(bg, "BG_SIDECAR_PATH", str(mirror))
    rep = bg.reconcile_event_sidecar_after_milestone_exit(event_dir, "Event_3")
    assert rep.get("merged_json_mirror") == {"event_3_pre": 1}
    beats = store["arcs"]["arc_1"]["segments"]["event_3_pre"]["beats"]
    assert len(beats) == 2
    assert beats[1]["beat_id"] == "bg_arc1_event3_pre_beat_08"
