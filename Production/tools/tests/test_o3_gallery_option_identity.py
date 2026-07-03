"""O3_GALLERY_OPTION_IDENTITY_V1 — gallery key/path/export authority tests."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from o3_gallery_option_identity import (
    AUDIO_CONTRACT_EMBEDDED_VOICE,
    AUDIO_CONTRACT_VIDEO_ONLY,
    O3GalleryExportAuthorityError,
    O3GalleryOptionAmbiguousError,
    assert_beat_export_gallery_authority,
    canonical_o3_option_key,
    normalize_o3_gallery_options,
    probe_o3_clip_audio_contract,
    resolve_o3_gallery_option,
)


def _make_silent_mp4(path: Path, duration_s: float = 1.0) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"color=c=black:s=320x240:d={duration_s:.3f}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(path),
        ],
        check=True,
        capture_output=True,
        timeout=60,
    )


def _make_tone_mp4(path: Path, duration_s: float = 1.0) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=mono",
            "-f", "lavfi", "-i", f"color=c=black:s=320x240:d={duration_s:.3f}",
            "-shortest",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            str(path),
        ],
        check=True,
        capture_output=True,
        timeout=60,
    )


def test_canonical_key_matches_path() -> None:
    beat_id = "bg_arc1_event4_post_beat_05"
    path = "/tmp/foo/bar_g1_delivery_trimmed.mp4"
    key = canonical_o3_option_key(beat_id, path)
    assert key == f"{beat_id}_o3_video_{__import__('hashlib').sha1(path.encode()).hexdigest()[:10]}"


def test_still_insert_key_preserved_through_normalize(tmp_path: Path) -> None:
    """Still-insert stable keys must survive normalize — export uses selected pointer."""
    clip = tmp_path / "bg_arc1_event4_post_beat_01_still_insert_1782856229_tts.mp4"
    _make_silent_mp4(clip)
    beat_id = "bg_arc1_event4_post_beat_01"
    stable_key = "bg_arc1_event4_post_beat_01_still_insert_1782856229"
    beat = {
        "beat_id": beat_id,
        "kling_o3_video_path": str(clip),
        "kling_o3_selected_option_key": stable_key,
        "kling_o3_options": [
            {
                "key": stable_key,
                "video_path": str(clip),
                "label": "still insert clip",
                "source": "still_insert_ken_burns",
            },
        ],
    }
    logs = normalize_o3_gallery_options(beat)
    assert not any("still_insert" in line and "re-key" in line for line in logs)
    assert beat["kling_o3_options"][0]["key"] == stable_key
    assert resolve_o3_gallery_option(beat, stable_key)
    assert_beat_export_gallery_authority(beat)


def test_still_insert_tts_trimmed_export_authority(tmp_path: Path) -> None:
    """Trimmed still-insert keeps stable base key; selected follows active path."""
    base = tmp_path / "bg_arc1_event3_pre_beat_06_still_insert_1782532197"
    raw = base.with_suffix(".mp4")
    trimmed = Path(str(base) + "_tts_trimmed.mp4")
    _make_tone_mp4(raw)
    _make_tone_mp4(trimmed)
    beat_id = "bg_arc1_event3_pre_beat_06"
    stable_key = "bg_arc1_event3_pre_beat_06_still_insert_1782532197"
    beat = {
        "beat_id": beat_id,
        "kling_o3_video_path": str(trimmed),
        "kling_o3_selected_option_key": stable_key,
        "kling_o3_options": [
            {
                "key": stable_key,
                "video_path": str(raw),
                "label": "raw still",
                "source": "still_insert_ken_burns",
            },
            {
                "key": stable_key,
                "video_path": str(trimmed),
                "label": "trimmed still",
                "source": "still_insert_ken_burns",
                "active": True,
            },
        ],
    }
    normalize_o3_gallery_options(beat)
    assert beat["kling_o3_selected_option_key"] == stable_key
    assert_beat_export_gallery_authority(beat)


def test_normalize_heals_key_path_mismatch(tmp_path: Path) -> None:
    silent = tmp_path / "still_insert_7536_kling_idle_tts.mp4"
    audible = tmp_path / "g1_delivery_trimmed.mp4"
    _make_silent_mp4(silent)
    _make_tone_mp4(audible)
    beat_id = "bg_arc1_event4_post_beat_05"
    wrong_key = canonical_o3_option_key(beat_id, str(silent))
    beat = {
        "beat_id": beat_id,
        "kling_o3_video_path": str(audible),
        "kling_o3_selected_option_key": wrong_key,
        "kling_o3_options": [
            {"key": wrong_key, "video_path": str(audible), "label": "silent mislabeled"},
            {"key": wrong_key, "video_path": str(silent), "label": "silent still"},
        ],
    }
    logs = normalize_o3_gallery_options(beat)
    assert logs
    assert resolve_o3_gallery_option(beat, canonical_o3_option_key(beat_id, str(silent)))
    assert_beat_export_gallery_authority(beat)


def test_resolve_fails_on_duplicate_keys_after_normalize(tmp_path: Path) -> None:
    p1 = tmp_path / "a.mp4"
    p2 = tmp_path / "b.mp4"
    _make_tone_mp4(p1)
    _make_tone_mp4(p2)
    beat_id = "bg_test_beat_01"
    shared = "forced_duplicate_key"
    beat = {
        "beat_id": beat_id,
        "kling_o3_options": [
            {"key": shared, "video_path": str(p1)},
            {"key": shared, "video_path": str(p2)},
        ],
    }
    normalize_o3_gallery_options(beat)
    keys = {o["key"] for o in beat["kling_o3_options"]}
    assert len(keys) == 2
    for key in keys:
        resolve_o3_gallery_option(beat, key)


def test_probe_audio_contracts(tmp_path: Path) -> None:
    silent = tmp_path / "x_still_insert_1_s0_kling_idle_tts.mp4"
    audible = tmp_path / "x_g1_delivery.mp4"
    _make_silent_mp4(silent)
    _make_tone_mp4(audible)
    assert probe_o3_clip_audio_contract(str(silent)) == AUDIO_CONTRACT_VIDEO_ONLY
    assert probe_o3_clip_audio_contract(str(audible)) == AUDIO_CONTRACT_EMBEDDED_VOICE


def test_export_authority_passes_when_aligned(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mp4"
    _make_tone_mp4(clip)
    beat_id = "bg_test_beat_02"
    key = canonical_o3_option_key(beat_id, str(clip))
    beat = {
        "beat_id": beat_id,
        "kling_o3_video_path": str(clip),
        "kling_o3_selected_option_key": key,
        "kling_o3_options": [{"key": key, "video_path": str(clip), "active": True}],
    }
    normalize_o3_gallery_options(beat)
    assert_beat_export_gallery_authority(beat)
