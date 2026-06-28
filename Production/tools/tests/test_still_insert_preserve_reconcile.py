"""Still+TTS beats must survive Send-to-Stitcher preserve + milestone reconcile."""
from __future__ import annotations

import json
from pathlib import Path

import beat_generator as bg


def _still_beat(beat_id: str) -> dict:
    return {
        "beat_id": beat_id,
        "pipeline": "still_insert",
        "speaker": "Lorelai",
        "kling_o3_video_path": f"/tmp/{beat_id}_tts.mp4",
    }


def _o3_beat(beat_id: str) -> dict:
    return {
        "beat_id": beat_id,
        "pipeline": "kling_o3_omni",
        "speaker": "Lorelai",
        "kling_o3_video_path": f"/tmp/{beat_id}.mp4",
    }


def test_preserve_snapshot_includes_still_insert(tmp_path: Path) -> None:
    event_dir = tmp_path / "Event_2"
    o3_path = tmp_path / "o3.mp4"
    still_path = tmp_path / "still.mp4"
    o3_path.write_bytes(b"\x00")
    still_path.write_bytes(b"\x00")
    sidecar = {
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_2_pre": {
                        "beats": [
                            {
                                **_o3_beat("bg_arc1_event2_pre_beat_01"),
                                "kling_o3_video_path": str(o3_path),
                            },
                            {
                                **_still_beat("bg_arc1_event2_pre_beat_15"),
                                "kling_o3_video_path": str(still_path),
                            },
                        ],
                    },
                },
            },
        },
    }
    n = bg.preserve_kling_o3_segment_beats(
        sidecar, 1, "2", "pre", event_dir, reason="test",
    )
    assert n == 2
    manifest = json.loads(
        (
            event_dir
            / "kling_o3_clips"
            / "_preserved"
            / "segments"
            / "arc1_event2_pre"
            / "manifest.json"
        ).read_text(),
    )
    ids = [b["beat_id"] for b in manifest.get("beats") or []]
    assert "bg_arc1_event2_pre_beat_15" in ids
    assert "bg_arc1_event2_pre_beat_01" in ids


def test_merge_missing_still_insert_beats_from_preserve(tmp_path: Path) -> None:
    event_dir = tmp_path / "Event_2"
    seg_dir = (
        event_dir
        / "kling_o3_clips"
        / "_preserved"
        / "segments"
        / "arc1_event2_pre"
    )
    seg_dir.mkdir(parents=True)
    preserved = [
        _o3_beat("bg_arc1_event2_pre_beat_14"),
        _still_beat("bg_arc1_event2_pre_beat_15"),
        _o3_beat("bg_arc1_event2_pre_beat_17"),
    ]
    (seg_dir / "manifest.json").write_text(
        json.dumps(
            {
                "arc_number": 1,
                "event_id": "2",
                "phase": "pre",
                "beats": preserved,
            },
        ),
    )
    sidecar = {
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_2_pre": {
                        "beats": [
                            _o3_beat("bg_arc1_event2_pre_beat_14"),
                            _o3_beat("bg_arc1_event2_pre_beat_17"),
                        ],
                    },
                },
            },
        },
    }
    merged = bg.merge_missing_still_insert_beats_from_preserve(
        sidecar, event_dir, 1, "2", "pre",
    )
    assert merged == ["bg_arc1_event2_pre_beat_15"]
    beats = sidecar["arcs"]["arc_1"]["segments"]["event_2_pre"]["beats"]
    assert [b["beat_id"] for b in beats] == [
        "bg_arc1_event2_pre_beat_14",
        "bg_arc1_event2_pre_beat_15",
        "bg_arc1_event2_pre_beat_17",
    ]


def test_heal_segment_still_insert_beats_from_backup_rows() -> None:
    backup = [
        _o3_beat("bg_arc1_event2_pre_beat_14"),
        _still_beat("bg_arc1_event2_pre_beat_15"),
        _o3_beat("bg_arc1_event2_pre_beat_17"),
    ]
    sidecar = {
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_2_pre": {
                        "beats": [
                            _o3_beat("bg_arc1_event2_pre_beat_14"),
                            _o3_beat("bg_arc1_event2_pre_beat_31"),
                            _o3_beat("bg_arc1_event2_pre_beat_17"),
                        ],
                    },
                },
            },
        },
    }
    restored = bg.heal_segment_still_insert_beats_from_backup_rows(
        sidecar,
        1,
        "2",
        "pre",
        backup,
        still_insert_ids=["bg_arc1_event2_pre_beat_15"],
        remove_beat_ids=["bg_arc1_event2_pre_beat_31"],
    )
    assert restored == ["bg_arc1_event2_pre_beat_15"]
    ids = [b["beat_id"] for b in sidecar["arcs"]["arc_1"]["segments"]["event_2_pre"]["beats"]]
    assert ids == [
        "bg_arc1_event2_pre_beat_14",
        "bg_arc1_event2_pre_beat_15",
        "bg_arc1_event2_pre_beat_17",
    ]


def test_reconcile_merges_still_insert_when_segment_nonempty(tmp_path: Path, monkeypatch) -> None:
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
                "beats": [
                    _o3_beat("bg_arc1_event2_pre_beat_01"),
                    _still_beat("bg_arc1_event2_pre_beat_15"),
                ],
            },
        ),
    )
    store: dict = {
        "active_context": {"arc_number": 1, "event_id": "3b", "phase": "full"},
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_3b_full": {"beats": [{"beat_id": "milestone_beat"}]},
                    "event_2_pre": {
                        "beats": [_o3_beat("bg_arc1_event2_pre_beat_01")],
                    },
                },
            },
        },
    }

    def fake_mutate(fn):
        fn(store)

    monkeypatch.setattr(bg, "mutate_sidecar_locked", fake_mutate)
    rep = bg.reconcile_event_sidecar_after_milestone_exit(event_dir, "Event_2")
    assert rep.get("merged_still_insert", {}).get("arc1_event2_pre") == [
        "bg_arc1_event2_pre_beat_15",
    ]
    ids = [
        b["beat_id"]
        for b in store["arcs"]["arc_1"]["segments"]["event_2_pre"]["beats"]
    ]
    assert "bg_arc1_event2_pre_beat_15" in ids
