"""Guardrails: voice-first / Element / still gallery clips must not cross-contaminate."""
from __future__ import annotations

import json
from pathlib import Path

import beat_generator as bg

BEAT4_ELEMENT_PATH = (
    "/Event_2/kling_o3_clips/bg_arc1_event2_pre_beat_04_g4_element_o3_master_delivery.mp4"
)
BEAT4_VOICE_PATH = (
    "/Event_2/kling_o3_clips/bg_arc1_event2_pre_beat_04_tessa_voice_lipsync_delivery.mp4"
)


def _event2_sidecar_beat4(*, o3_generate_mode: str = "voice_first") -> tuple[dict, dict]:
    beat = {
        "beat_id": "bg_arc1_event2_pre_beat_04",
        "speaker": "Tessa",
        "dialogue_text": 'Tessa [thoughtful]: "I think it is. And look at this!"',
        "pipeline": "kling_o3_omni",
        "o3_generate_mode": o3_generate_mode,
        "kling_o3_video_path": BEAT4_ELEMENT_PATH,
        "kling_o3_selected_option_key": "bg_arc1_event2_pre_beat_04_o3_video_fb2f4eab93",
        "kling_o3_options": [
            {
                "key": "bg_arc1_event2_pre_beat_04_o3_video_fb2f4eab93",
                "label": "g4 O3 Element voice",
                "video_path": BEAT4_ELEMENT_PATH,
                "source": "kling_o3_element_native_voice",
                "active": True,
                "generation": 4,
            },
            {
                "key": "bg_arc1_event2_pre_beat_04_o3_video_97e47adf67",
                "label": "latest O3 voice video",
                "video_path": BEAT4_VOICE_PATH,
                "source": "kling_o3_voice_video",
                "active": False,
            },
        ],
    }
    sidecar = {
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_2_pre": {"beats": [beat]},
                },
            },
        },
    }
    return sidecar, beat


def test_infer_o3_option_pipeline_mode_path_beats_stale_source():
    """g5-style rows: path says Element even when source was mislabeled voice_video."""
    opt = {
        "source": "kling_o3_voice_video",
        "video_path": "/Event_2/kling_o3_clips/bg_arc1_event2_pre_beat_04_g5_element_o3_master_delivery.mp4",
    }
    assert bg.infer_o3_option_pipeline_mode(opt) == bg.O3_GENERATE_MODE_ELEMENT_NATIVE


def test_infer_voice_first_from_lipsync_delivery_path():
    opt = {"source": "kling_o3_voice_video", "video_path": BEAT4_VOICE_PATH}
    assert bg.infer_o3_option_pipeline_mode(opt) == bg.O3_GENERATE_MODE_VOICE_FIRST


def test_mismatch_when_voice_first_mode_with_element_clip_selected():
    sidecar, beat = _event2_sidecar_beat4(o3_generate_mode="voice_first")
    assert bg.compute_o3_selection_pipeline_mismatch(beat, sidecar) is True


def test_no_mismatch_when_modes_align():
    sidecar, beat = _event2_sidecar_beat4(o3_generate_mode="voice_first")
    beat["kling_o3_video_path"] = BEAT4_VOICE_PATH
    beat["kling_o3_selected_option_key"] = "bg_arc1_event2_pre_beat_04_o3_video_97e47adf67"
    for o in beat["kling_o3_options"]:
        o["active"] = o.get("video_path") == BEAT4_VOICE_PATH
    assert bg.compute_o3_selection_pipeline_mismatch(beat, sidecar) is False


def test_set_generation_mode_voice_first_auto_selects_matching_clip():
    sidecar, beat = _event2_sidecar_beat4(o3_generate_mode="element_native")
    changed = bg.set_beat_generation_mode(
        beat,
        bg.O3_GENERATE_MODE_VOICE_FIRST,
        event_id="2",
        phase="pre",
        sidecar=sidecar,
    )
    assert changed is True
    assert beat["kling_o3_video_path"] == BEAT4_VOICE_PATH
    assert not beat.get("kling_o3_selection_pipeline_mismatch")
    assert beat.get("kling_o3_mode") == bg.KLING_O3_MODE_VOICE_FIRST


def test_sync_sets_element_mode_on_element_selection():
    sidecar, beat = _event2_sidecar_beat4(o3_generate_mode="element_native")
    element = beat["kling_o3_options"][0]
    bg.sync_o3_selection_pipeline_fields(beat, sidecar, option=element)
    assert beat.get("kling_o3_mode") == bg.KLING_O3_MODE_ELEMENT_NATIVE
    assert not beat.get("kling_o3_selection_pipeline_mismatch")


def test_select_handler_returns_pipeline_mismatch_warning():
    src = Path(__file__).resolve().parents[1] / "server_handlers" / "background.py"
    block = src.read_text(encoding="utf-8").split("def handle_bg_select_o3_video", 1)[1].split("\ndef ", 1)[0]
    assert "pipeline_mismatch" in block
    assert "sync_o3_selection_pipeline_fields" in block


def test_arlo_finalize_stamps_voice_first_kling_mode():
    src = Path(__file__).resolve().parents[1] / "arlo_o3_voice_pipeline.py"
    text = src.read_text(encoding="utf-8")
    assert '"kling_o3_mode": "o3_voice_first_lipsync"' in text
    assert "sync_o3_selection_pipeline_fields" in text


def test_ui_pipeline_mismatch_banner_and_labels():
    src = Path(__file__).resolve().parents[1] / "storyboard-v2" / "src" / "components" / "BgTab.tsx"
    text = src.read_text(encoding="utf-8")
    assert "bg-o3-pipeline-mismatch" in text
    assert "pipelineSelectionMismatchMessage" in text
    assert "displayO3OptionLabel" in text
    assert "ElevenLabs voice-first" in text


def test_sidecar_merge_preserves_pipeline_guard_fields():
    for field in (
        "o3_generate_mode",
        "kling_o3_selection_pipeline_mismatch",
        "kling_o3_active_clip_pipeline",
    ):
        assert field in bg.SIDECAR_MERGE_PRESERVE_FIELDS
