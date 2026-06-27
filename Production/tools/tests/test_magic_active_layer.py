"""Active magic layer — newest on-disk artifact wins when still + video coexist."""
from __future__ import annotations

import os
import time

import beat_generator as bg


def _touch(path, mtime: float) -> None:
    os.utime(path, (mtime, mtime))


def test_active_magic_layer_still_newer_wins_event2_shape(tmp_path):
    """Regression: Event_2 beat_07 — redo magic on still must beat stale magic_video."""
    event_dir = tmp_path / "Event_2"
    event_dir.mkdir()
    magic_video = event_dir / "magic_video_bg_arc1_event2_post_beat_07_20260621-010601.mp4"
    magic_still = event_dir / "magic_still_bg_arc1_event2_post_beat_07_20260621-082918.mp4"
    magic_video.write_bytes(b"old-video-magic")
    magic_still.write_bytes(b"new-still-magic")
    base = time.time()
    _touch(magic_video, base)
    _touch(magic_still, base + 3600)
    beat = {
        "beat_id": "bg_arc1_event2_post_beat_07",
        "pipeline": "still_insert",
        "magic_video_path": magic_video.name,
        "magic_still_path": magic_still.name,
    }
    assert bg.resolve_active_magic_layer(beat, event_dir) == "still"
    assert bg.resolve_bg_magic_canonical_kind(beat, event_dir) == "still"
    chosen = bg.resolve_beat_stitch_export_clip_path(beat, event_dir, tmp_path / "scratch")
    assert chosen == magic_still.resolve()


def test_active_magic_layer_video_newer_wins(tmp_path):
    event_dir = tmp_path / "Event_1"
    event_dir.mkdir()
    magic_video = event_dir / "magic_video_beat_01.mp4"
    magic_still = event_dir / "magic_still_beat_01.mp4"
    magic_video.write_bytes(b"mv")
    magic_still.write_bytes(b"ms")
    base = time.time()
    _touch(magic_still, base)
    _touch(magic_video, base + 100)
    beat = {
        "beat_id": "bg_arc1_event1_post_beat_01",
        "kling_o3_status": "approved",
        "magic_video_path": magic_video.name,
        "magic_still_path": magic_still.name,
    }
    assert bg.resolve_active_magic_layer(beat, event_dir) == "video"
    chosen = bg.resolve_beat_stitch_export_clip_path(beat, event_dir, tmp_path / "scratch")
    assert chosen == magic_video.resolve()


def test_active_magic_layer_still_insert_tie_prefers_still(tmp_path):
    event_dir = tmp_path / "Event_1"
    event_dir.mkdir()
    magic_video = event_dir / "magic_video_beat_21.mp4"
    magic_still = event_dir / "magic_still_beat_21.mp4"
    magic_video.write_bytes(b"mv")
    magic_still.write_bytes(b"ms")
    same = time.time()
    _touch(magic_video, same)
    _touch(magic_still, same)
    beat = {
        "beat_id": "bg_arc1_event1_post_beat_21",
        "pipeline": "still_insert",
        "magic_video_path": magic_video.name,
        "magic_still_path": magic_still.name,
    }
    assert bg.resolve_active_magic_layer(beat, event_dir) == "still"


def test_active_magic_layer_lipsync_tie_prefers_video(tmp_path):
    event_dir = tmp_path / "Event_1"
    event_dir.mkdir()
    magic_video = event_dir / "magic_video_beat_01.mp4"
    magic_still = event_dir / "magic_still_beat_01.mp4"
    magic_video.write_bytes(b"mv")
    magic_still.write_bytes(b"ms")
    same = time.time()
    _touch(magic_video, same)
    _touch(magic_still, same)
    beat = {
        "beat_id": "bg_arc1_event1_post_beat_01",
        "kling_o3_status": "approved",
        "magic_video_path": magic_video.name,
        "magic_still_path": magic_still.name,
    }
    assert bg.resolve_active_magic_layer(beat, event_dir) == "video"


def test_active_magic_layer_only_still_on_disk(tmp_path):
    event_dir = tmp_path / "Event_1"
    event_dir.mkdir()
    magic_still = event_dir / "magic_still_beat_21.mp4"
    magic_still.write_bytes(b"ms")
    beat = {
        "pipeline": "still_insert",
        "magic_still_path": magic_still.name,
        "magic_video_path": "missing_video.mp4",
    }
    assert bg.resolve_active_magic_layer(beat, event_dir) == "still"


def test_enrich_beat_sets_canonical_from_mtimes(tmp_path):
    event_dir = tmp_path / "Event_2"
    event_dir.mkdir()
    magic_video = event_dir / "magic_video_old.mp4"
    magic_still = event_dir / "magic_still_new.mp4"
    magic_video.write_bytes(b"v")
    magic_still.write_bytes(b"s")
    base = time.time()
    _touch(magic_video, base)
    _touch(magic_still, base + 500)
    beat = {
        "beat_id": "bg_arc1_event2_post_beat_07",
        "pipeline": "still_insert",
        "magic_video_path": magic_video.name,
        "magic_still_path": magic_still.name,
    }
    enriched = bg.enrich_beat_kling_o3_pinned(beat, event_dir)
    assert enriched["magic_canonical_kind"] == "still"


def test_stitch_export_kling_when_no_magic_on_beat(tmp_path):
    event_dir = tmp_path / "Event_2"
    event_dir.mkdir()
    kling = event_dir / "bg_arc1_event2_post_beat_03_g5_delivery.mp4"
    kling.write_bytes(b"kling")
    beat = {
        "beat_id": "bg_arc1_event2_post_beat_03",
        "kling_o3_status": "approved",
        "kling_o3_video_path": str(kling),
    }
    chosen = bg.resolve_beat_stitch_export_clip_path(beat, event_dir, tmp_path / "scratch")
    assert chosen == kling.resolve()


def test_stitch_export_magic_video_when_on_beat(tmp_path):
    event_dir = tmp_path / "Event_2"
    event_dir.mkdir()
    kling = event_dir / "idle.mp4"
    magic_video = event_dir / "magic_video_beat_02.mp4"
    kling.write_bytes(b"kling")
    magic_video.write_bytes(b"magic")
    beat = {
        "beat_id": "bg_arc1_event2_post_beat_02",
        "pipeline": "still_insert",
        "kling_o3_still_stitch_approved": True,
        "kling_o3_video_path": str(kling),
        "magic_video_path": magic_video.name,
    }
    chosen = bg.resolve_beat_stitch_export_clip_path(beat, event_dir, tmp_path / "scratch")
    assert chosen == magic_video.resolve()


def test_stitch_export_magic_still_when_on_beat(tmp_path):
    event_dir = tmp_path / "Event_2"
    event_dir.mkdir()
    kling = event_dir / "idle.mp4"
    magic_still = event_dir / "magic_still_beat_07.mp4"
    magic_video = event_dir / "magic_video_stale.mp4"
    kling.write_bytes(b"kling")
    magic_still.write_bytes(b"still-magic")
    magic_video.write_bytes(b"stale")
    base = time.time()
    os.utime(magic_video, (base, base))
    os.utime(magic_still, (base + 100, base + 100))
    beat = {
        "beat_id": "bg_arc1_event2_post_beat_07",
        "pipeline": "still_insert",
        "kling_o3_still_stitch_approved": True,
        "kling_o3_video_path": str(kling),
        "magic_still_path": magic_still.name,
        "magic_video_path": magic_video.name,
    }
    chosen = bg.resolve_beat_stitch_export_clip_path(beat, event_dir, tmp_path / "scratch")
    assert chosen == magic_still.resolve()
