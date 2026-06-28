"""Per-option O3 cut-out trim — persistence, export, and ffmpeg materialize."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import beat_generator as bg


def _beat_with_two_options(tmp_path: Path) -> dict:
    clip_a = tmp_path / "g4_delivery.mp4"
    clip_b = tmp_path / "g5_delivery.mp4"
    clip_a.write_bytes(b"a")
    clip_b.write_bytes(b"b")
    return {
        "beat_id": "bg_arc1_event2_pre_beat_18",
        "kling_o3_generation": 5,
        "kling_o3_video_path": str(clip_a),
        "kling_o3_options": [
            {
                "key": "opt_a",
                "video_path": str(clip_a),
                "slot_index": 0,
                "cut_start_s": 1.0,
                "cut_end_s": 2.5,
            },
            {
                "key": "opt_b",
                "video_path": str(clip_b),
                "slot_index": 1,
                "cut_start_s": 0.5,
                "cut_end_s": 3.0,
            },
        ],
    }


def test_set_o3_option_cut_persists_on_option_row(tmp_path: Path):
    beat = _beat_with_two_options(tmp_path)
    clip_b = beat["kling_o3_options"][1]["video_path"]
    with patch.object(bg, "_ffprobe_duration", return_value=8.0):
        result = bg.set_o3_option_cut(
            beat,
            slot_index=0,
            cut_start_s=1.2,
            cut_end_s=4.0,
            video_path=clip_b,
        )
    opt = bg.find_o3_option_by_video_path(beat, clip_b)
    assert opt is not None
    assert opt["cut_start_s"] == 1.2
    assert opt["cut_end_s"] == 4.0
    assert result["effective_duration_s"] == 5.2


def test_hydrate_beat_cut_from_active_option(tmp_path: Path):
    beat = _beat_with_two_options(tmp_path)
    bg.hydrate_beat_cut_from_active_option(beat)
    assert beat["kling_o3_cut_start_s"] == 1.0
    assert beat["kling_o3_cut_end_s"] == 2.5

    beat["kling_o3_video_path"] = beat["kling_o3_options"][1]["video_path"]
    bg.hydrate_beat_cut_from_active_option(beat)
    assert beat["kling_o3_cut_start_s"] == 0.5
    assert beat["kling_o3_cut_end_s"] == 3.0


def test_clear_o3_option_cut_only_targets_slot(tmp_path: Path):
    beat = _beat_with_two_options(tmp_path)
    clip_a = beat["kling_o3_options"][0]["video_path"]
    bg.clear_o3_option_cut(beat, slot_index=0, video_path=clip_a)
    opt_a = bg.find_o3_option_by_video_path(beat, clip_a)
    opt_b = bg.find_o3_option_by_video_path(beat, beat["kling_o3_options"][1]["video_path"])
    assert opt_a is not None and "cut_start_s" not in opt_a
    assert opt_b is not None and opt_b.get("cut_end_s") == 3.0


def test_find_o3_option_by_slot_index_uses_pin_slot_layout(tmp_path: Path):
    """UI slot layout follows stored slot_index (pin-slot model)."""
    g3 = tmp_path / "bg_test_g3_element_o3_master_delivery.mp4"
    g5 = tmp_path / "bg_test_g5_element_o3_master_delivery.mp4"
    g12 = tmp_path / "bg_test_g12_element_o3_master_delivery.mp4"
    for p in (g3, g5, g12):
        p.write_bytes(b"v")
    beat = {
        "beat_id": "bg_test",
        "kling_o3_options": [
            {"video_path": str(g12), "generation": 12, "slot_index": 0},
            {"video_path": str(g5), "generation": 5, "slot_index": 2},
            {"video_path": str(g3), "generation": 3, "slot_index": 1},
        ],
    }
    ui_slots = bg.build_fixed_o3_ui_slots(beat)
    assert ui_slots[0]["video_path"] == str(g12)
    assert ui_slots[1]["video_path"] == str(g3)
    assert ui_slots[2]["video_path"] == str(g5)

    assert bg.find_o3_option_by_slot_index(beat, 1)["video_path"] == str(g3)
    assert bg.find_o3_option_by_slot_index(beat, 2)["video_path"] == str(g5)

    with patch.object(bg, "_ffprobe_duration", return_value=8.0):
        bg.set_o3_option_cut(
            beat,
            slot_index=1,
            cut_start_s=1.0,
            cut_end_s=2.0,
            video_path=str(g3),
        )
    assert bg.find_o3_option_by_video_path(beat, str(g3))["cut_start_s"] == 1.0
    assert "cut_start_s" not in bg.find_o3_option_by_video_path(beat, str(g5))


def test_o3_cut_is_active_middle_region(tmp_path: Path):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"x")
    beat = {
        "kling_o3_video_path": str(clip),
        "kling_o3_cut_start_s": 2.0,
        "kling_o3_cut_end_s": 4.0,
    }
    with patch.object(bg, "_ffprobe_duration", return_value=8.0):
        assert bg.o3_cut_is_active(beat, raw_dur=8.0) is True


def test_export_clip_path_uses_cut_token(tmp_path: Path):
    clip = tmp_path / "source.mp4"
    clip.write_bytes(b"x")
    beat = {
        "beat_id": "bg_arc1_event2_pre_beat_10",
        "kling_o3_generation": 3,
        "kling_o3_video_path": str(clip),
        "kling_o3_cut_start_s": 1.0,
        "kling_o3_cut_end_s": 3.0,
    }
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    with patch.object(bg, "_ffprobe_duration", return_value=8.0):
        with patch.object(bg, "materialize_o3_cut_out_clip") as mat:
            mat.side_effect = lambda beat, dest, **kw: dest
            dest = bg._kling_o3_export_clip_path(beat, tmp_path, scratch)
    assert "_export_cut.mp4" in dest.name
    assert "c1.0_3.0" in dest.name


def test_heal_invalid_o3_cut_all_options_clears_bad_window(tmp_path: Path):
    clip = tmp_path / "short.mp4"
    clip.write_bytes(b"x")
    beat = {
        "kling_o3_video_path": str(clip),
        "kling_o3_cut_start_s": 1.0,
        "kling_o3_cut_end_s": 7.5,
        "kling_o3_options": [
            {"video_path": str(clip), "slot_index": 0, "cut_start_s": 1.0, "cut_end_s": 7.5},
        ],
    }
    with patch.object(bg, "_ffprobe_duration", return_value=6.0):
        assert bg.heal_invalid_o3_cut_all_options(beat) is True
    assert "kling_o3_cut_start_s" not in beat
    assert "cut_start_s" not in beat["kling_o3_options"][0]


def test_bg_cut_overlay_defers_persist_until_apply_cut_button():
    overlay = (
        Path(__file__).resolve().parent.parent
        / "storyboard-v2"
        / "src"
        / "components"
        / "bg"
        / "BgO3CutOverlay.tsx"
    ).read_text(encoding="utf-8")
    bg_tab = (
        Path(__file__).resolve().parent.parent
        / "storyboard-v2"
        / "src"
        / "components"
        / "BgTab.tsx"
    ).read_text(encoding="utf-8")
    assert "onKeepDraftChange" in overlay
    assert "onCutChange" not in overlay
    assert "bg-o3-apply-cut-" in bg_tab
    assert "applyDraftCut" in bg_tab
    assert "onKeepDraftChange" in bg_tab
    apply_block = bg_tab.split("applyDraftCut")[1].split("BgO3TrimNumericControls")[0]
    assert "previewOnly: true" not in apply_block
    assert "applyCutPreview" in bg_tab
    assert "hasSavedCut && !cutDraftDirty" not in bg_tab
    assert "refreshSavedCutPreview" in bg_tab
    apply_persist_block = bg_tab.split("applyDraftCut")[1].split("const clearCut")[0]
    assert "refreshSavedCutPreview" in apply_persist_block
    assert "lastAutoPreviewRef.current === sig && previewUrl" in bg_tab
    assert "normalizeO3KeepWindow" in overlay
    assert "resolveO3PlaybackDurationS" in overlay
    assert "Math.max(src, playback)" in overlay
    assert "trimTimelineDurationS = playbackDurationS" in bg_tab
    assert "loadedDuration == null" in bg_tab
    assert "resolveO3PlaybackDurationS" in bg_tab


def test_normalize_o3_keep_window_clamps_stale_end_past_duration():
    """Regression: keepEnd from longer timeline must clamp, not toast-reject head trim."""
    overlay = (
        Path(__file__).resolve().parent.parent
        / "storyboard-v2"
        / "src"
        / "components"
        / "bg"
        / "BgO3CutOverlay.tsx"
    ).read_text(encoding="utf-8")
    bg_tab = (
        Path(__file__).resolve().parent.parent
        / "storyboard-v2"
        / "src"
        / "components"
        / "BgTab.tsx"
    ).read_text(encoding="utf-8")
    assert "normalizeO3KeepWindow" in overlay
    # Stale keepEnd=13.625 with export dur=6.064 must clamp to 6.064, keep start=0.8 valid.
    assert "endCap = Math.min" in overlay
    assert "resolveO3PlaybackDurationS" in overlay
    assert "Math.max(src, playback)" in overlay
    assert "trimTimelineDurationS = playbackDurationS" in bg_tab
    assert "loadedDuration == null" in bg_tab
