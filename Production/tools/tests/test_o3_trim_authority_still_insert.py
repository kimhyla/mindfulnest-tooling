"""Regression: still-insert trim authority must not use unrelated delivery duration."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import beat_generator as bg


def test_guess_untrimmed_skips_delivery_for_still_insert_option(tmp_path: Path):
    still_trimmed = tmp_path / "bg_arc1_event4_post_beat_05_still_insert_7536_s0_kling_idle_tts_trimmed.mp4"
    delivery_raw = tmp_path / "bg_arc1_event4_post_beat_05_g1_element_o3_master_delivery.mp4"
    still_trimmed.write_bytes(b"t")
    delivery_raw.write_bytes(b"d")
    beat = {
        "beat_id": "bg_arc1_event4_post_beat_05",
        "pipeline": "still_insert",
        "kling_o3_options": [
            {
                "video_path": str(still_trimmed),
                "source": "still_insert_kling_idle",
                "slot_index": 1,
            },
            {"video_path": str(delivery_raw), "slot_index": 2},
        ],
    }
    opt = beat["kling_o3_options"][0]
    with patch.object(bg, "_ffprobe_duration", side_effect=lambda p: 10.042 if "delivery" in str(p) else 8.125):
        untrimmed = bg._guess_o3_untrimmed_video_path(beat, opt)
    assert untrimmed is None or "delivery" not in str(untrimmed).lower()


def test_trim_authority_uses_pretrimmed_delivery_not_raw(tmp_path: Path):
    delivery_trimmed = tmp_path / "bg_test_g1_element_o3_master_delivery_trimmed.mp4"
    delivery_raw = tmp_path / "bg_test_g1_element_o3_master_delivery.mp4"
    delivery_trimmed.write_bytes(b"t")
    delivery_raw.write_bytes(b"d")
    beat = {
        "beat_id": "bg_test",
        "pipeline": "still_insert",
        "kling_o3_options": [
            {
                "video_path": str(delivery_trimmed),
                "source": "still_insert_kling_idle",
                "slot_index": 1,
            },
            {"video_path": str(delivery_raw), "slot_index": 2},
        ],
    }
    opt = beat["kling_o3_options"][0]

    def _dur(p: Path) -> float:
        if "delivery_trimmed" in p.name:
            return 8.125
        if "delivery" in p.name:
            return 10.042
        return 0.0

    with patch.object(bg, "_ffprobe_duration", side_effect=_dur):
        authority = bg._o3_trim_authority_path(beat, opt, str(delivery_trimmed))
        result = bg.set_o3_option_trim(
            beat,
            slot_index=1,
            trim_start=4.48,
            trim_back=None,
            video_path=str(delivery_trimmed),
        )
    assert authority.resolve() == delivery_trimmed.resolve()
    assert result["raw_duration_s"] == 8.125
    assert result["effective_duration_s"] == 3.645


def test_kling_idle_retrim_uses_visible_file_not_tts_sibling(tmp_path: Path):
    full = tmp_path / "bg_test_still_insert_7536_s0_kling_idle_tts.mp4"
    trimmed = tmp_path / "bg_test_still_insert_7536_s0_kling_idle_tts_trimmed.mp4"
    full.write_bytes(b"f" * 100)
    trimmed.write_bytes(b"t" * 50)
    beat = {
        "beat_id": "bg_test",
        "pipeline": "still_insert",
        "kling_o3_options": [{
            "video_path": str(trimmed),
            "source": "still_insert_kling_idle",
            "slot_index": 1,
        }],
    }

    def _dur(p: Path) -> float:
        if "tts_trimmed" in p.name:
            return 5.042
        if "tts.mp4" in p.name:
            return 10.042
        return 0.0

    with patch.object(bg, "_ffprobe_duration", side_effect=_dur):
        opt = beat["kling_o3_options"][0]
        auth = bg._o3_trim_authority_path(beat, opt, str(trimmed))
        result = bg.set_o3_option_trim(
            beat,
            slot_index=1,
            trim_start=0.0,
            trim_back=1.0,
            video_path=str(trimmed),
        )
    assert auth.resolve() == trimmed.resolve()
    assert result["raw_duration_s"] == 5.042
    assert result["effective_duration_s"] == 4.042


def test_find_o3_option_by_video_path_prefers_exact_over_untrimmed():
    full = "/clips/bg_test_still_insert_7300_s0_kling_idle_tts.mp4"
    trimmed = "/clips/bg_test_still_insert_7300_s0_kling_idle_tts_trimmed.mp4"
    beat = {
        "kling_o3_options": [
            {
                "video_path": trimmed,
                "o3_untrimmed_video_path": full,
                "slot_index": 0,
                "source": "still_insert_kling_idle",
            },
            {
                "video_path": full,
                "slot_index": 2,
                "source": "kling_o3_disk_reconcile",
                "trim_start_s": 4.31,
                "trim_back_s": 1.9,
            },
        ],
    }
    opt = bg.find_o3_option_by_video_path(beat, full)
    assert opt is not None
    assert opt["slot_index"] == 2
    assert opt.get("trim_start_s") == 4.31


def test_o3_option_paths_same_clip_family_still_insert_tts_sibling_trim():
    tts = "/clips/bg_arc1_event5_pre_beat_06_still_insert_1783130402_tts.mp4"
    trimmed = "/clips/bg_arc1_event5_pre_beat_06_still_insert_1783130402_trimmed.mp4"
    tts_trimmed = "/clips/bg_arc1_event5_pre_beat_06_still_insert_1783130402_tts_trimmed.mp4"
    other_gen = "/clips/bg_arc1_event5_pre_beat_06_still_insert_1783130246_tts.mp4"
    assert bg._o3_option_paths_same_clip_family(tts, trimmed)
    assert bg._o3_option_paths_same_clip_family(tts, tts_trimmed)
    assert not bg._o3_option_paths_same_clip_family(tts, other_gen)


def test_find_o3_option_by_slot_index_accepts_pre_bake_path_after_trim(tmp_path: Path):
    full = tmp_path / "bg_test_still_insert_7300_s0_kling_idle_tts.mp4"
    trimmed = tmp_path / "bg_test_still_insert_7300_s0_kling_idle_tts_trimmed.mp4"
    full.write_bytes(b"f")
    trimmed.write_bytes(b"t")
    beat = {
        "beat_id": "bg_test",
        "pipeline": "still_insert",
        "kling_o3_video_path": str(trimmed),
        "kling_o3_options": [{
            "video_path": str(trimmed),
            "o3_untrimmed_video_path": str(full),
            "source": "still_insert_kling_idle",
            "slot_index": 2,
        }],
    }
    opt = bg.find_o3_option_by_slot_index(
        beat,
        2,
        video_path=str(full),
    )
    assert opt is not None
    assert opt["video_path"] == str(trimmed)


def test_heal_duplicate_o3_slot_indexes_prefers_delivery_over_reconcile():
    beat = {
        "kling_o3_options": [
            {"video_path": "/a/g1_delivery_trimmed.mp4", "source": "o3_pov_motion_i2v", "slot_index": 1},
            {"video_path": "/a/still_insert_tts_trimmed.mp4", "source": "kling_o3_disk_reconcile", "slot_index": 1},
        ],
    }
    assert bg.heal_duplicate_o3_slot_indexes(beat) is True
    slots = {
        int(o["slot_index"]): o["video_path"]
        for o in beat["kling_o3_options"]
        if isinstance(o.get("slot_index"), int)
    }
    assert slots[1].endswith("g1_delivery_trimmed.mp4")
    assert any(o["video_path"].endswith("still_insert_tts_trimmed.mp4") for o in beat["kling_o3_options"])
    assert all(
        len([o for o in beat["kling_o3_options"] if o.get("slot_index") == si]) <= 1
        for si in range(3)
    )


def test_bake_still_insert_uses_trimmed_delivery_authority(tmp_path: Path, monkeypatch):
    delivery_trimmed = tmp_path / "bg_test_g1_element_o3_master_delivery_trimmed.mp4"
    delivery_raw = tmp_path / "bg_test_g1_element_o3_master_delivery.mp4"
    delivery_trimmed.write_bytes(b"t" * 50)
    delivery_raw.write_bytes(b"d" * 100)
    used_src: list[str] = []

    def _mat(_beat, dest, *, source_path=None):
        used_src.append(str(source_path))
        dest.write_bytes(b"b")
        return dest

    def _dur(p: Path) -> float:
        if "delivery_trimmed" in str(p):
            return 8.125
        if "delivery" in str(p):
            return 10.042
        return 4.0

    monkeypatch.setattr(bg, "_ffprobe_duration", _dur)
    monkeypatch.setattr(bg, "kling_o3_trim_is_active", lambda beat, raw_dur=None: True)
    monkeypatch.setattr(bg, "materialize_kling_o3_trimmed_clip", _mat)
    beat = {
        "beat_id": "bg_test",
        "pipeline": "still_insert",
        "kling_o3_video_path": str(delivery_trimmed),
        "kling_o3_trim_start": 4.48,
        "kling_o3_trim_back": 1.88,
        "kling_o3_options": [
            {
                "video_path": str(delivery_trimmed),
                "source": "still_insert_kling_idle",
                "slot_index": 1,
                "trim_start_s": 4.48,
                "trim_back_s": 1.88,
            },
            {"video_path": str(delivery_raw), "slot_index": 2},
        ],
    }
    bg.bake_still_insert_trim_into_clip(beat)
    assert used_src
    assert str(delivery_trimmed.resolve()) in used_src[0]
