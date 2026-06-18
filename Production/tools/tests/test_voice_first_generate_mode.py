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


def test_resolve_voice_first_for_event2_pre_when_segment_override():
    sidecar = _sidecar_event2_pre()
    sidecar["arcs"]["arc_1"]["segments"]["event_2_pre"]["o3_generate_mode"] = "voice_first"
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


def test_arlo_pipeline_stamps_generate_mode_and_pilot_lipsync_fallback():
    src = Path(__file__).resolve().parents[1] / "arlo_o3_voice_pipeline.py"
    text = src.read_text(encoding="utf-8")
    assert "kling_o3_generate_mode" in text
    assert "LipsyncHostingError" in text
    assert "voice_first_pilot_warn" not in text
    assert "lipsync_quality_warn" in text
    assert 'attempts = ["url", "data_uri"]' in text
    assert "MINDFULNEST_DISABLE_LIPSYNC_DATA_URI_FALLBACK" in text
    assert 'min(12, math.ceil(float(lipsync_padding["padded_audio_duration_s"]) + 0.25))' in text


def test_arlo_voice_first_waives_sub720_after_lipsync_for_any_transport():
    src = Path(__file__).resolve().parents[1] / "arlo_o3_voice_pipeline.py"
    text = src.read_text(encoding="utf-8")
    assert "sub720_waived" in text
    assert "lipsync_quality_warn" in text
    assert "if lipsync_transport == \"data_uri\":" not in text.split("_assert_lipsync_quality")[1].split("active = _delivery_video")[0]


def test_submit_handler_stamps_lipsync_staging_env_for_voice_first():
    bg_src = Path(__file__).resolve().parents[1] / "server_handlers" / "background.py"
    text = bg_src.read_text(encoding="utf-8")
    assert "MN_LIPSYNC_STAGING_EVENT_DIR" in text
    assert "MN_LIPSYNC_STAGING_TOKEN" in text
    assert "MN_LIPSYNC_STAGING_PUBLIC_BASE" in text
    assert "is_public_staging_base" in text
    assert "inject_lipsync_r2_env" in text
    assert "LIPSYNC_HOSTING_NOT_CONFIGURED" in text


def test_lipsync_staging_skips_localhost_for_all_event_ports():
    """Event_N default port 5110+N must not become WaveSpeed staging URLs."""
    import lipsync_staging

    for event_num in (1, 2, 3, 4):
        port = 5110 + event_num
        assert not lipsync_staging.is_public_staging_base(f"http://localhost:{port}")


def test_production_server_serves_lipsync_staging_route():
    ps = Path(__file__).resolve().parents[1] / "production_server.py"
    text = ps.read_text(encoding="utf-8")
    assert "/api/lipsync/staging/" in text
    assert "_serve_lipsync_staging" in text
