"""Per-event SQLite authority — bootstrap filter, mirror merge, O3 rehydrate rank."""
from __future__ import annotations

import json
from pathlib import Path

import beat_generator as bg


def test_filter_sidecar_dict_for_event_keeps_only_matching_segments() -> None:
    data = {
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_2_pre": {"beats": [{"beat_id": "e2"}]},
                    "event_3_pre": {"beats": [{"beat_id": "e3"}]},
                },
            },
        },
    }
    filtered = bg._filter_sidecar_dict_for_event(data, "/tmp/Production/Event_3")
    segs = filtered["arcs"]["arc_1"]["segments"]
    assert list(segs.keys()) == ["event_3_pre"]
    assert segs["event_3_pre"]["beats"][0]["beat_id"] == "e3"


def test_merge_event_scoped_mirror_preserves_sibling_events(
    tmp_path: Path, monkeypatch,
) -> None:
    mirror = tmp_path / "beat_generator_state.json"
    mirror.write_text(
        json.dumps(
            {
                "arcs": {
                    "arc_1": {
                        "segments": {
                            "event_2_pre": {"beats": [{"beat_id": "e2"}]},
                        },
                    },
                },
            },
        ),
    )
    monkeypatch.setenv("MN_BEATGEN_DB_PATH", str(tmp_path / "beatgen_event3.db"))
    monkeypatch.setattr(bg, "_PROD_DIR", str(tmp_path))
    monkeypatch.setattr(bg, "_BG_EVENT_DIR", str(tmp_path / "Event_3"))
    incoming = {
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_3_pre": {"beats": [{"beat_id": "e3"}]},
                },
            },
        },
    }
    merged = bg._merge_event_scoped_mirror(incoming, str(mirror))
    segs = merged["arcs"]["arc_1"]["segments"]
    assert "event_2_pre" in segs
    assert "event_3_pre" in segs
    assert segs["event_2_pre"]["beats"][0]["beat_id"] == "e2"
    assert segs["event_3_pre"]["beats"][0]["beat_id"] == "e3"


def test_merge_event_scoped_mirror_never_shrinks_segment_beat_count(
    tmp_path: Path, monkeypatch,
) -> None:
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
    monkeypatch.setenv("MN_BEATGEN_DB_PATH", str(tmp_path / "beatgen_event3.db"))
    monkeypatch.setattr(bg, "_PROD_DIR", str(tmp_path))
    monkeypatch.setattr(bg, "_BG_EVENT_DIR", str(tmp_path / "Event_3"))
    incoming = {
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
    merged = bg._merge_event_scoped_mirror(incoming, str(mirror))
    beats = merged["arcs"]["arc_1"]["segments"]["event_3_pre"]["beats"]
    assert len(beats) == 2
    assert beats[0]["kling_o3_status"] == "approved"
    assert beats[1]["beat_id"] == "bg_arc1_event3_pre_beat_08"


def test_o3_artifact_row_rank_prefers_done_delivery_over_failed() -> None:
    done = {
        "terminal_status": "done",
        "video_path": "/tmp/x.mp4",
        "_terminal_at": "2026-06-27T01:00:00+00:00",
    }
    failed = {
        "terminal_status": "failed",
        "video_path": "",
        "_terminal_at": "2026-06-27T02:00:00+00:00",
    }
    assert bg._o3_artifact_row_rank(done) > bg._o3_artifact_row_rank(failed)


def test_merge_missing_segment_beats_from_json_mirror_unions_draft_rows(
    tmp_path: Path,
) -> None:
    mirror = tmp_path / "beat_generator_state.json"
    mirror.write_text(
        json.dumps(
            {
                "arcs": {
                    "arc_1": {
                        "segments": {
                            "event_3_pre": {
                                "beat_plan_draft": {"beats_plan": [{"beat_index": 1}]},
                                "beats": [
                                    {"beat_id": "bg_arc1_event3_pre_beat_02", "speaker": "Ember", "status": "approved"},
                                    {"beat_id": "bg_arc1_event3_pre_beat_08", "speaker": "Tessa", "status": "draft"},
                                    {"beat_id": "bg_arc1_event3_pre_beat_13", "speaker": "Arlo", "status": "draft"},
                                ],
                            },
                        },
                    },
                },
            },
        ),
    )
    sidecar: dict = {
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_3_pre": {
                        "beats": [
                            {"beat_id": "bg_arc1_event3_pre_beat_02", "speaker": "Ember", "status": "approved", "kling_o3_status": "approved"},
                        ],
                    },
                },
            },
        },
    }
    merged = bg.merge_missing_segment_beats_from_json_mirror(sidecar, mirror, "3")
    beats = sidecar["arcs"]["arc_1"]["segments"]["event_3_pre"]["beats"]
    assert merged == {"event_3_pre": 2}
    assert len(beats) == 3
    assert beats[0]["beat_id"] == "bg_arc1_event3_pre_beat_02"
    assert beats[0]["kling_o3_status"] == "approved"
    assert beats[1]["beat_id"] == "bg_arc1_event3_pre_beat_08"
    assert beats[2]["beat_id"] == "bg_arc1_event3_pre_beat_13"
    assert sidecar["arcs"]["arc_1"]["segments"]["event_3_pre"]["beat_plan_draft"]["beats_plan"]


def test_merge_missing_beats_does_not_overwrite_live_sqlite_rows(tmp_path: Path) -> None:
    mirror = tmp_path / "mirror.json"
    mirror.write_text(
        json.dumps(
            {
                "arcs": {
                    "arc_1": {
                        "segments": {
                            "event_3_pre": {
                                "beats": [
                                    {"beat_id": "bg_arc1_event3_pre_beat_02", "speaker": "Ember", "dialogue_text": "mirror text"},
                                ],
                            },
                        },
                    },
                },
            },
        ),
    )
    sidecar: dict = {
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_3_pre": {
                        "beats": [
                            {"beat_id": "bg_arc1_event3_pre_beat_02", "speaker": "Ember", "dialogue_text": "live text", "kling_o3_status": "approved"},
                        ],
                    },
                },
            },
        },
    }
    assert bg.merge_missing_segment_beats_from_json_mirror(sidecar, mirror, "3") == {}
    beat = sidecar["arcs"]["arc_1"]["segments"]["event_3_pre"]["beats"][0]
    assert beat["dialogue_text"] == "live text"
    assert beat["kling_o3_status"] == "approved"


def test_rehydrate_segment_from_o3_artifacts(tmp_path: Path) -> None:
    event_dir = tmp_path / "Event_3"
    jobs = event_dir / "arlo_o3_jobs"
    jobs.mkdir(parents=True)
    clip = event_dir / "kling_o3_clips"
    clip.mkdir(parents=True)
    delivery = clip / "bg_arc1_event3_pre_beat_02_g1_element_o3_master_delivery.mp4"
    delivery.write_bytes(b"\x00")
    (jobs / "abc123_intent.json").write_text(
        json.dumps(
            {
                "beat_id": "bg_arc1_event3_pre_beat_02",
                "prompt": {
                    "verbatim": '@Image1 (Ember) says "Hi."',
                    "spoken_sent": "Hi.",
                },
            },
        ),
    )
    (jobs / "abc123_terminal.json").write_text(
        json.dumps(
            {
                "status": "done",
                "terminal_at": "2026-06-27T03:00:00+00:00",
                "delivered": {"video_path": str(delivery)},
                "submitted": {"char_ref": str(tmp_path / "ember.png")},
            },
        ),
    )
    (tmp_path / "ember.png").write_bytes(b"x")
    sidecar: dict = {"arcs": {"arc_1": {"segments": {"event_3_pre": {"beats": []}}}}}
    n = bg.rehydrate_segment_beats_from_o3_artifacts(sidecar, event_dir, 1, "3", "pre")
    assert n == 1
    beat = sidecar["arcs"]["arc_1"]["segments"]["event_3_pre"]["beats"][0]
    assert beat["beat_id"] == "bg_arc1_event3_pre_beat_02"
    assert beat["speaker"] == "Ember"
    assert beat["kling_o3_status"] == "approved"
    assert beat["reference_image"]["abs_path"] == str(tmp_path / "ember.png")


def test_delete_beat_locked_sqlite(tmp_path: Path, monkeypatch) -> None:
    from lib.beatgen_store import BeatgenStore

    db = tmp_path / "beatgen_event4.db"
    monkeypatch.setenv("MN_BEATGEN_DB_PATH", str(db))
    monkeypatch.setenv("MN_SIDECAR_SQLITE_AUTHORITY", "1")
    monkeypatch.setenv("MN_BEATGEN_TEST_ALLOW_DIRECT_WRITE", "1")
    BeatgenStore.reset_singleton_for_tests()
    sidecar = {
        "schema_version": 3,
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_4_pre": {
                        "beats": [
                            {"beat_id": "bg_arc1_event4_pre_beat_01", "speaker": "A"},
                            {"beat_id": "bg_arc1_event4_pre_beat_02", "speaker": "B"},
                        ],
                    },
                },
            },
        },
    }
    BeatgenStore(db).import_from_dict(sidecar, replace=True)
    assert bg.delete_beat_locked("bg_arc1_event4_pre_beat_01", caller="test") is True
    store = BeatgenStore(db)
    assert store.beat_count() == 1
    remaining = store.assemble_sidecar_dict()["arcs"]["arc_1"]["segments"]["event_4_pre"]["beats"]
    assert len(remaining) == 1
    assert remaining[0]["beat_id"] == "bg_arc1_event4_pre_beat_02"


def test_replace_full_blocks_any_net_beat_loss(tmp_path: Path, monkeypatch) -> None:
    from lib.beatgen_store import BeatgenStore

    db = tmp_path / "beatgen_event9.db"
    monkeypatch.setenv("MN_BEATGEN_DB_PATH", str(db))
    BeatgenStore.reset_singleton_for_tests()
    store = BeatgenStore(db)
    sidecar = {
        "schema_version": 3,
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_9_pre": {
                        "beats": [
                            {"beat_id": "bg_arc1_event9_pre_beat_01"},
                            {"beat_id": "bg_arc1_event9_pre_beat_02"},
                        ],
                    },
                },
            },
        },
    }
    store.import_from_dict(sidecar, replace=True)
    thin = {
        "schema_version": 3,
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_9_pre": {"beats": [{"beat_id": "bg_arc1_event9_pre_beat_01"}]},
                },
            },
        },
    }
    import pytest

    with pytest.raises(RuntimeError, match="replace_full blocked"):
        bg._assert_sidecar_replace_full_safe(store, thin)


def test_production_server_startup_runs_sidecar_reconcile() -> None:
    text = (
        Path(__file__).resolve().parent.parent / "production_server.py"
    ).read_text(encoding="utf-8")
    assert "reconcile_event_sidecar_after_milestone_exit" in text
    assert "[startup] sidecar reconcile" in text
    assert "assert_beatgen_db_path_matches_event" in text


def test_assert_beatgen_db_path_matches_event_ok(monkeypatch) -> None:
    monkeypatch.setenv("MN_BEATGEN_DB_PATH", "/tmp/beatgen_event3.db")
    bg.assert_beatgen_db_path_matches_event("Event_3")


def test_assert_beatgen_db_path_mismatch_raises(monkeypatch) -> None:
    monkeypatch.setenv("MN_BEATGEN_DB_PATH", "/tmp/beatgen_event3.db")
    import pytest

    with pytest.raises(RuntimeError, match="does not match event_id"):
        bg.assert_beatgen_db_path_matches_event("Event_2")


def test_snapshot_union_when_mirror_empty(tmp_path: Path, monkeypatch) -> None:
    from lib.beatgen_store import BeatgenStore

    event_dir = tmp_path / "Event_3"
    event_dir.mkdir()
    prod = tmp_path
    mirror = prod / "beat_generator_state.json"
    mirror.write_text(json.dumps({"arcs": {"arc_1": {"segments": {}}}}))
    snap_root = prod / ".production_snapshots" / "latest" / "global"
    snap_root.mkdir(parents=True)
    snap = snap_root / "beat_generator_state.json"
    snap.write_text(
        json.dumps(
            {
                "arcs": {
                    "arc_1": {
                        "segments": {
                            "event_3_pre": {
                                "beats": [{"beat_id": "bg_arc1_event3_pre_beat_99"}],
                            },
                        },
                    },
                },
            },
        ),
    )
    db = tmp_path / "beatgen_event3.db"
    monkeypatch.setenv("MN_BEATGEN_DB_PATH", str(db))
    BeatgenStore.reset_singleton_for_tests()
    store = BeatgenStore(db)
    store.import_from_dict(
        {"arcs": {"arc_1": {"segments": {"event_3_pre": {"beats": []}}}}},
        replace=True,
    )
    monkeypatch.setattr(bg, "_PROD_DIR", str(prod))
    monkeypatch.setattr(bg, "BG_SIDECAR_PATH", str(mirror))
    monkeypatch.setattr(bg, "_MILESTONE_SIDECAR_JSON_ONLY", False)
    monkeypatch.setattr(bg, "_sidecar_use_sqlite", lambda: True)
    report = bg.reconcile_sqlite_segment_beats_from_json_mirror(event_dir)
    assert report.get("event_3_pre") == 1
