"""FF-038 STITCH_EXPORT_TRUTH v2 — still-insert metadata, ambient tile concat, peaks purge."""

from __future__ import annotations

from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]


def test_still_insert_flags_from_resolve() -> None:
    src = (TOOLS / "beat_generator.py").read_text(encoding="utf-8")
    block = src.split("def resolve_segment_stitch_export_clip_paths", 1)[1].split(
        "\ndef concat_kling_o3_approved_beats", 1,
    )[0]
    assert "still_insert_flags" in block
    assert "beat_is_still_insert(beat)" in block
    assert "return clip_paths, still_insert_flags, scratch_dir" in block


def test_still_insert_video_fade_in_concat() -> None:
    src = (TOOLS / "beat_generator.py").read_text(encoding="utf-8")
    block = src.split("def _ffmpeg_concat_kling_clips_reencode", 1)[1].split(
        "\ndef _TOOLS_DIR", 1,
    )[0]
    assert "STITCH_EXPORT_TRUTH_STILL_INSERT_VIDEO_FADE_V1" in src
    assert "_still_insert_exit_at_join" in block
    assert "fade=t=out" in block
    assert "still_insert_flags" in block


def test_ambient_tile_concat_loop_marker() -> None:
    from server_handlers.stitch_ambient_loop import (  # noqa: PLC0415
        STITCH_AMBIENT_TILE_CONCAT_LOOP_V1,
        build_ambient_bed_filter_lane,
        build_ambient_explicit_tile_concat_loop,
    )

    assert STITCH_AMBIENT_TILE_CONCAT_LOOP_V1
    frag = build_ambient_explicit_tile_concat_loop("amb0tile", 32.808, 121.0)
    assert "asplit=" in frag
    assert "concat=n=" in frag
    assert "aloop" not in frag
    lane = build_ambient_bed_filter_lane(1, 32.808, 121.0, 0.15)
    assert "[amb1tile]aloop=loop=-1" not in lane


def test_waveform_peaks_purged_on_export_bake() -> None:
    src = (TOOLS / "server_handlers" / "stitch_slot_playback.py").read_text(encoding="utf-8")
    assert "STITCH_EXPORT_TRUTH_WAVEFORM_INVALIDATE_ON_EXPORT_V1" in src
    upsert = src.split("def upsert(state: dict)", 1)[1].split("stitch_store.mutate_state", 1)[0]
    assert 'slot.pop("waveform_peaks_hash", None)' in upsert


def test_pair_fade_expands_still_insert_flags() -> None:
    src = (TOOLS / "beat_generator.py").read_text(encoding="utf-8")
    assert "_expand_still_insert_flags_for_pair_fades" in src
    pair_block = src.split("def _ffmpeg_concat_kling_clips_with_pair_fades", 1)[1].split(
        "\ndef _boundaries_for_pair_fade_concat", 1,
    )[0]
    assert "expanded_flags" in pair_block
    assert "still_insert_flags=still_insert_flags" in src
