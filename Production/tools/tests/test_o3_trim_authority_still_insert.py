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
