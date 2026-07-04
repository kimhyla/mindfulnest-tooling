"""MAGIC_SOURCE_BINDING_V1 — magic applies only to bound still/video source."""
from __future__ import annotations

import os
import time

import beat_generator as bg


def _touch(path, mtime: float) -> None:
    os.utime(path, (mtime, mtime))


def _still_beat(tmp_path, event_dir, *, still_name: str, magic_still_name: str, still_src) -> dict:
    magic_still = event_dir / magic_still_name
    magic_still.write_bytes(b"ms")
    return {
        "beat_id": "bg_arc1_event1_post_beat_21",
        "pipeline": "still_insert",
        "magic_still_path": magic_still.name,
        "magic_still_source_path": str(still_src),
        "accepted_library_ref": {"abs_path": str(still_src)},
    }


def test_legacy_magic_video_without_source_does_not_apply(tmp_path):
    event_dir = tmp_path / "Event_3"
    event_dir.mkdir()
    kling = event_dir / "g1_delivery.mp4"
    magic = event_dir / "magic_video_orphan.mp4"
    kling.write_bytes(b"kling")
    magic.write_bytes(b"magic")
    beat = {
        "beat_id": "bg_arc1_event3_post_beat_01",
        "kling_o3_status": "approved",
        "kling_o3_video_path": str(kling),
        "magic_video_path": magic.name,
    }
    assert bg.magic_video_applies_to_active(beat, event_dir) is False
    assert bg.resolve_active_magic_layer(beat, event_dir) is None
    chosen = bg.resolve_beat_stitch_export_clip_path(beat, event_dir, tmp_path / "scratch")
    assert chosen.resolve() == kling.resolve()


def test_bound_magic_video_applies_only_when_active_matches(tmp_path):
    event_dir = tmp_path / "Event_3"
    event_dir.mkdir()
    g1 = event_dir / "g1_delivery.mp4"
    g3 = event_dir / "g3_delivery.mp4"
    magic = event_dir / "magic_on_g3.mp4"
    for p in (g1, g3, magic):
        p.write_bytes(b"x" * 32)
    beat = {
        "beat_id": "bg_arc1_event3_post_beat_01",
        "kling_o3_status": "approved",
        "kling_o3_video_path": str(g1),
        "magic_video_path": magic.name,
        "magic_video_source_path": str(g3),
    }
    assert bg.magic_video_applies_to_active(beat, event_dir) is False
    beat["kling_o3_video_path"] = str(g3)
    assert bg.magic_video_applies_to_active(beat, event_dir) is True
    assert bg.resolve_active_magic_layer(beat, event_dir) == "video"


def test_replace_gallery_clip_clears_bound_magic(tmp_path):
    event_dir = tmp_path / "Event_3"
    event_dir.mkdir()
    old = event_dir / "old_g3.mp4"
    new = event_dir / "new_g3.mp4"
    magic = event_dir / "magic_g3.mp4"
    for p in (old, new, magic):
        p.write_bytes(b"v")
    beat = {
        "beat_id": "bg_arc1_event3_post_beat_01",
        "kling_o3_options": [{"slot_index": 0, "video_path": str(old), "active": True}],
        "kling_o3_video_path": str(old),
        "magic_video_path": magic.name,
        "magic_video_source_path": str(old),
    }
    bg.maybe_clear_magic_video_on_source_replaced(beat, old, event_dir)
    assert beat.get("magic_video_path") is None
    beat2 = {
        "beat_id": "bg_arc1_event3_post_beat_01",
        "kling_o3_options": [{
            "slot_index": 0,
            "video_path": str(old),
            "active": True,
            "source": "o3_pov_motion_i2v",
        }],
        "kling_o3_video_path": str(old),
        "magic_video_path": magic.name,
        "magic_video_source_path": str(old),
    }
    bg.assign_kling_o3_option_to_slot(
        beat2,
        0,
        video_path=str(new),
        label="new",
        source="o3_pov_motion_i2v",
        now="2026-07-04T00:00:00+00:00",
        make_active=True,
    )
    assert beat2.get("magic_video_path") is None


def test_enrich_exposes_applies_to_active(tmp_path):
    event_dir = tmp_path / "Event_1"
    event_dir.mkdir()
    kling = event_dir / "kling.mp4"
    magic = event_dir / "magic.mp4"
    kling.write_bytes(b"k")
    magic.write_bytes(b"m")
    beat = {
        "beat_id": "bg_arc1_event1_post_beat_01",
        "kling_o3_status": "approved",
        "kling_o3_video_path": str(kling),
        "magic_video_path": magic.name,
        "magic_video_source_path": str(kling),
    }
    enriched = bg.enrich_beat_kling_o3_pinned(beat, event_dir)
    assert enriched["magic_video_applies_to_active"] is True
    assert enriched["magic_canonical_kind"] == "video"
