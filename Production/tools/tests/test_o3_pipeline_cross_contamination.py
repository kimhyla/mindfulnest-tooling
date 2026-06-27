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
    text = src.read_text(encoding="utf-8")
    block = text.split("def _resolve_o3_select_option", 1)[1].split("\ndef _load_elevenlabs_key", 1)[0]
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


def test_scrub_still_insert_prompt_labels_removes_header():
    beat = {
        "kling_o3_prompt": (
            "STILL INSERT — use pre-made GPT still from library.\n"
            "@Image1 (Tessa). Scene from @Image2.\n\nCamera: static."
        ),
    }
    assert bg._scrub_still_insert_prompt_labels(beat) is True
    assert not beat["kling_o3_prompt"].startswith("STILL INSERT")
    assert "@Image1 (Tessa)" in beat["kling_o3_prompt"]


def test_apply_o3_mode_scrubs_still_insert_prompt():
    beat = {
        "beat_id": "bg_arc1_event2_pre_beat_04",
        "speaker": "Tessa",
        "dialogue_text": 'Tessa: "Hello"',
        "pipeline": "still_insert",
        "beat_render_mode": "still_insert",
        "kling_o3_prompt": "STILL INSERT — library still only.\nTessa waves.",
    }
    bg.apply_beat_pipeline_o3_mode(beat, event_id="2", phase="pre")
    assert beat["pipeline"] == bg.PIPELINE_MODE_O3
    assert not (beat.get("kling_o3_prompt") or "").startswith("STILL INSERT")


def test_set_still_mode_clears_o3_generate_mode():
    sidecar = {
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_2_pre": {
                        "beats": [{
                            "beat_id": "bg_arc1_event2_pre_beat_04",
                            "speaker": "Tessa",
                            "dialogue_text": "Hi",
                            "pipeline": "kling_o3_omni",
                            "o3_generate_mode": "voice_first",
                        }],
                    },
                },
            },
        },
    }
    beat = sidecar["arcs"]["arc_1"]["segments"]["event_2_pre"]["beats"][0]
    changed = bg.set_beat_generation_mode(
        beat,
        bg.PIPELINE_MODE_STILL,
        event_id="2",
        phase="pre",
        sidecar=sidecar,
    )
    assert changed is True
    assert "o3_generate_mode" not in beat
    assert bg.resolve_beat_generation_mode(beat, sidecar) == bg.PIPELINE_MODE_STILL


def test_submit_handler_blocks_still_insert_beats():
    src = Path(__file__).resolve().parents[1] / "server_handlers" / "background.py"
    block = src.read_text(encoding="utf-8").split(
        "def handle_bg_submit_arlo_o3_voice", 1,
    )[1].split("\ndef handle_bg_submit_kling", 1)[0]
    assert "resolve_beat_generation_mode" in block
    assert "STILL_INSERT_BEAT" in block
    assert "PIPELINE_MODE_STILL" in block
    assert "validate_o3_submit_prompt_for_mode" in block
    assert "STILL_INSERT_PROMPT_ON_O3_MODE" not in block  # error_code from validator return


def test_lipsync_gate_scoped_to_voice_first_beats():
    src = Path(__file__).resolve().parents[1] / "storyboard-v2" / "src" / "components" / "BgTab.tsx"
    text = src.read_text(encoding="utf-8")
    assert "effectiveGenerationMode(b, eventId) === 'voice_first'" in text
    assert "effectiveGenerationMode(beat, activeScope.value.event_id) === 'voice_first'" in text


def test_o3_generate_button_labels_distinct_by_mode():
    src = Path(__file__).resolve().parents[1] / "storyboard-v2" / "src" / "components" / "BgTab.tsx"
    text = src.read_text(encoding="utf-8")
    assert "function o3GenerateButtonLabel" in text
    assert "Generate voice-first O3 (ElevenLabs + lipsync)" in text
    assert "Generate Element native O3" in text
    assert "o3GenerateButtonLabel(generationMode)" in text


def test_effective_generation_mode_event2_speak_fallback():
    src = Path(__file__).resolve().parents[1] / "storyboard-v2" / "src" / "components" / "BgTab.tsx"
    text = src.read_text(encoding="utf-8")
    assert "ev === '2' && hasSpeak" in text
    assert "effectiveGenerationMode(beat, eventId)" in text


def test_normalize_option_slots_hides_cross_pipeline_clips():
    sidecar, beat = _event2_sidecar_beat4(o3_generate_mode="element_native")
    beat["kling_o3_video_path"] = BEAT4_ELEMENT_PATH
    slots = bg.normalize_kling_o3_option_slots(beat, sidecar)
    visible_paths = [s.get("video_path") for s in slots if s]
    assert BEAT4_ELEMENT_PATH in visible_paths
    assert BEAT4_VOICE_PATH not in visible_paths
