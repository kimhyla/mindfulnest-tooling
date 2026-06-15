"""O3 delivery disk ↔ sidecar reconcile — paid clips must never stay orphaned."""
from __future__ import annotations

import json
from pathlib import Path

import beat_generator as bg


def test_reconcile_imports_all_disk_deliveries_into_options(tmp_path: Path) -> None:
    event_dir = tmp_path / "Event_2"
    clips = event_dir / "kling_o3_clips"
    clips.mkdir(parents=True)
    beat_id = "bg_arc1_event2_pre_beat_27"
    g9 = clips / f"{beat_id}_g9_element_o3_master_delivery.mp4"
    g14 = clips / f"{beat_id}_g14_element_o3_master_delivery.mp4"
    g9.write_bytes(b"a")
    g14.write_bytes(b"b")
    beat = {
        "beat_id": beat_id,
        "speaker": "Lorelai",
        "pipeline": "kling_o3_omni",
        "kling_o3_video_path": str(g14),
        "kling_o3_options": [
            {
                "key": "only_g10",
                "video_path": str(clips / f"{beat_id}_g10_element_o3_master_delivery.mp4"),
                "slot_index": 1,
            },
        ],
    }
    changed = bg.reconcile_o3_disk_deliveries_for_beat(beat, event_dir)
    assert changed is True
    paths = {o.get("video_path") for o in beat["kling_o3_options"]}
    assert str(g9.resolve()) in paths
    assert str(g14.resolve()) in paths
    slotted = [o for o in beat["kling_o3_options"] if isinstance(o.get("slot_index"), int)]
    assert len(slotted) == 3 or len(slotted) == 2  # up to 3 newest on disk
    assert slotted[0].get("slot_index") == 0


def test_prune_never_drops_on_disk_clips_even_when_voice_bind_differs(tmp_path: Path) -> None:
    clip = tmp_path / "bg_test_g1_element_o3_master_delivery.mp4"
    clip.write_bytes(b"x")
    beat = {
        "beat_id": "bg_test",
        "speaker": "Lorelai",
        "kling_o3_options": [
            {
                "video_path": str(clip),
                "o3_voice_binding": {"kling_voice_id": "old_voice", "element_id": "old_el"},
            },
        ],
    }
    changed = bg.prune_stale_o3_voice_options(beat, "Lorelai")
    assert changed is False
    assert len(beat["kling_o3_options"]) == 1


def test_assign_option_to_slot_preserves_full_history(tmp_path: Path) -> None:
    p1 = tmp_path / "g1_element_o3_master_delivery.mp4"
    p2 = tmp_path / "g2_element_o3_master_delivery.mp4"
    p3 = tmp_path / "g3_element_o3_master_delivery.mp4"
    p4 = tmp_path / "g4_element_o3_master_delivery.mp4"
    for p in (p1, p2, p3, p4):
        p.write_bytes(b"v")
    beat = {
        "beat_id": "bg_test",
        "kling_o3_options": [
            {"video_path": str(p1), "key": "k1"},
            {"video_path": str(p2), "key": "k2"},
            {"video_path": str(p3), "key": "k3"},
        ],
    }
    bg.assign_kling_o3_option_to_slot(
        beat,
        0,
        video_path=str(p4),
        label="g4",
        source="test",
        now="now",
        make_active=True,
    )
    paths = {o.get("video_path") for o in beat["kling_o3_options"]}
    assert len(paths) == 4
    assert str(p1) in paths


def test_o3_voice_binding_from_job_log(tmp_path: Path) -> None:
    event_dir = tmp_path / "Event_2"
    jobs = event_dir / "arlo_o3_jobs"
    jobs.mkdir(parents=True)
    delivery = event_dir / "kling_o3_clips" / "bg_arc1_event2_pre_beat_27_g14_element_o3_master_delivery.mp4"
    delivery.parent.mkdir(parents=True)
    delivery.write_bytes(b"mp4")
    log = jobs / "abc_bg_arc1_event2_pre_beat_27.log"
    log.write_text(
        json.dumps(
            {
                "phase": "o3_submit",
                "element": {"element_id": "313441038164306", "element_name": "Loral"},
                "kling_voice_id": "895210468825628751",
            }
        )
        + "\n"
        + json.dumps({"phase": "delivery_encode", "dst": str(delivery)})
        + "\n"
        + json.dumps({"phase": "done", "video": str(delivery)})
        + "\n",
        encoding="utf-8",
    )
    binding = bg._o3_voice_binding_from_job_log(log, delivery)
    assert binding["element_id"] == "313441038164306"
    assert binding["kling_voice_id"] == "895210468825628751"


def test_event_dir_for_beat_id_derives_event_folder(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(bg, "_PROD_DIR", str(tmp_path))
    assert bg.event_dir_for_beat_id("bg_arc1_event2_pre_beat_27") == tmp_path / "Event_2"
    assert bg.event_dir_for_beat_id("bg_arc1_event1_pre_beat_10") == tmp_path / "Event_1"


def test_enrich_uses_beat_event_not_server_pin(tmp_path: Path, monkeypatch) -> None:
    """Event_2 clips must count when server is pinned to Event_1."""
    monkeypatch.setattr(bg, "_PROD_DIR", str(tmp_path))
    event2 = tmp_path / "Event_2"
    clips = event2 / "kling_o3_clips"
    clips.mkdir(parents=True)
    beat_id = "bg_arc1_event2_pre_beat_27"
    delivery = clips / f"{beat_id}_g9_element_o3_master_delivery.mp4"
    delivery.write_bytes(b"x")
    beat = {"beat_id": beat_id, "kling_o3_options": []}
    enriched = bg.enrich_beats_kling_o3_pinned([beat], tmp_path / "Event_1")[0]
    assert enriched["kling_o3_disk_delivery_count"] == 1
    assert "Event_2" in enriched["kling_o3_clips_dir"]


def test_refresh_o3_ui_slot_layout_newest_three_with_labels(tmp_path: Path) -> None:
    """Beat 13 pattern: 4 on disk → slots 0–2 are g4, g3, g2 with canonical labels."""
    beat_id = "bg_arc1_event2_pre_beat_30"
    clips = tmp_path / "kling_o3_clips"
    clips.mkdir(parents=True)
    paths = {}
    for gen in (1, 2, 3, 4):
        p = clips / f"{beat_id}_g{gen}_element_o3_master_delivery.mp4"
        p.write_bytes(f"g{gen}".encode())
        paths[gen] = str(p.resolve())
    beat = {
        "beat_id": beat_id,
        "kling_o3_options": [
            {"video_path": paths[1], "label": "recovered O3 delivery", "slot_index": 0},
            {"video_path": paths[2], "label": "g2 O3 Element voice", "generation": 2, "slot_index": 1},
            {"video_path": paths[3], "label": "latest O3 Element voice", "slot_index": 2},
            {"video_path": paths[4], "label": "g4 O3 Element voice", "generation": 4},
        ],
    }
    changed = bg.refresh_o3_ui_slot_layout(beat)
    assert changed is True
    slotted = sorted(
        [o for o in beat["kling_o3_options"] if isinstance(o.get("slot_index"), int)],
        key=lambda o: o["slot_index"],
    )
    assert len(slotted) == 3
    assert [o.get("generation") for o in slotted] == [4, 3, 2]
    assert [o.get("label") for o in slotted] == [
        "g4 O3 Element voice",
        "g3 O3 Element voice",
        "g2 O3 Element voice",
    ]
    rolled = [o for o in beat["kling_o3_options"] if "slot_index" not in o]
    assert len(rolled) == 1
    assert rolled[0].get("generation") == 1
    assert rolled[0].get("label") == "g1 O3 Element voice"


def test_enrich_refreshes_newest_three_for_api(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(bg, "_PROD_DIR", str(tmp_path))
    beat_id = "bg_arc1_event2_pre_beat_30"
    event2 = tmp_path / "Event_2"
    clips = event2 / "kling_o3_clips"
    clips.mkdir(parents=True)
    p5 = clips / f"{beat_id}_g5_element_o3_master_delivery.mp4"
    p4 = clips / f"{beat_id}_g4_element_o3_master_delivery.mp4"
    p3 = clips / f"{beat_id}_g3_element_o3_master_delivery.mp4"
    for p in (p3, p4, p5):
        p.write_bytes(b"v")
    beat = {
        "beat_id": beat_id,
        "kling_o3_options": [
            {"video_path": str(p3.resolve()), "label": "g3 O3 Element voice", "generation": 3, "slot_index": 0},
            {"video_path": str(p4.resolve()), "label": "g4 O3 Element voice", "generation": 4, "slot_index": 1},
            {"video_path": str(p5.resolve()), "label": "latest O3 Element voice", "slot_index": 2},
        ],
    }
    enriched = bg.enrich_beat_kling_o3_pinned(beat, event2)
    slotted = sorted(
        [o for o in enriched["kling_o3_options"] if isinstance(o.get("slot_index"), int)],
        key=lambda o: o["slot_index"],
    )
    assert [o.get("generation") for o in slotted] == [5, 4, 3]
    assert slotted[0].get("label") == "g5 O3 Element voice"
