"""Voice-first Beat Gen routing — resolve_o3_generate_mode + submit handler contract."""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import beat_generator as bg


def _sidecar_event2_pre() -> dict:
    return {
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_2_pre": {
                        "name": "Event 2 Intro",
                        "beats": [
                            {
                                "beat_id": "bg_arc1_event2_pre_beat_08",
                                "speaker": "Tessa",
                                "dialogue_text": "Power source?",
                            },
                        ],
                    },
                    "event_1_pre": {
                        "beats": [
                            {
                                "beat_id": "bg_arc1_event1_pre_beat_01",
                                "speaker": "Chipper",
                                "dialogue_text": "Hello",
                            },
                        ],
                    },
                },
            },
        },
    }


def test_resolve_voice_first_for_event2_pre_speak_beat():
    sidecar = _sidecar_event2_pre()
    beat = sidecar["arcs"]["arc_1"]["segments"]["event_2_pre"]["beats"][0]
    assert bg.resolve_o3_generate_mode(beat, sidecar) == "voice_first"


def test_resolve_element_native_for_event1():
    sidecar = _sidecar_event2_pre()
    beat = sidecar["arcs"]["arc_1"]["segments"]["event_1_pre"]["beats"][0]
    assert bg.resolve_o3_generate_mode(beat, sidecar) == "element_native"


def test_env_override_voice_first():
    sidecar = _sidecar_event2_pre()
    beat = sidecar["arcs"]["arc_1"]["segments"]["event_1_pre"]["beats"][0]
    env = {"MN_O3_GENERATE_MODE": "voice_first"}
    assert bg.resolve_o3_generate_mode(beat, sidecar, env=env) == "voice_first"


def test_segment_override_element_native_on_event2():
    sidecar = _sidecar_event2_pre()
    sidecar["arcs"]["arc_1"]["segments"]["event_2_pre"]["o3_generate_mode"] = "element_native"
    beat = sidecar["arcs"]["arc_1"]["segments"]["event_2_pre"]["beats"][0]
    assert bg.resolve_o3_generate_mode(beat, sidecar) == "element_native"


def test_submit_handler_selects_arlo_script_for_voice_first():
    bg_src = Path(__file__).resolve().parents[1] / "server_handlers" / "background.py"
    text = bg_src.read_text(encoding="utf-8")
    assert "resolve_o3_generate_mode" in text
    assert "arlo_o3_voice_pipeline.py" in text
    assert "o3_generate_mode" in text


def test_arlo_pipeline_stamps_generate_mode_and_data_uri_fallback():
    src = Path(__file__).resolve().parents[1] / "arlo_o3_voice_pipeline.py"
    text = src.read_text(encoding="utf-8")
    assert "kling_o3_generate_mode" in text
    assert "LipsyncHostingError" in text
    assert "voice_first_pilot_warn" in text
    assert 'min(12, math.ceil(float(lipsync_padding["padded_audio_duration_s"]) + 0.25))' in text
