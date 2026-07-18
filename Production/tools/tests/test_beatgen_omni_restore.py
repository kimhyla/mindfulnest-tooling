"""Beat Gen Omni restore — env pin, default routing, Phase B isolation guard."""
from __future__ import annotations

from pathlib import Path

import beat_generator as bg


def _speak_sidecar() -> dict:
    return {
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_3b_full": {
                        "beats": [{
                            "beat_id": "bg_arc1_event3b_full_beat_02",
                            "speaker": "Lorelai",
                            "dialogue_text": "Hello?",
                            "o3_generate_mode": "avatar_pro",
                        }],
                    },
                },
            },
        },
    }


def test_beatgen_avatar_pro_disabled_with_env_pin():
    env = {"MN_O3_GENERATE_MODE": "element_native", "MN_BEATGEN_AVATAR_DISABLED": "1"}
    assert bg.beatgen_avatar_pro_disabled(env) is True


def test_beatgen_avatar_pro_disabled_by_default_without_env():
    assert bg.beatgen_avatar_pro_disabled({}) is True


def test_beatgen_avatar_pro_allowed_opt_in():
    assert bg.beatgen_avatar_pro_disabled({"MN_BEATGEN_AVATAR_ALLOWED": "1"}) is False


def test_resolve_downgrades_sidecar_avatar_when_disabled():
    sidecar = _speak_sidecar()
    beat = sidecar["arcs"]["arc_1"]["segments"]["event_3b_full"]["beats"][0]
    assert bg.resolve_o3_generate_mode(beat, sidecar) == bg.O3_GENERATE_MODE_ELEMENT_NATIVE


def test_default_speak_beat_is_element_native_without_avatar_sidecar():
    sidecar = _speak_sidecar()
    beat = dict(sidecar["arcs"]["arc_1"]["segments"]["event_3b_full"]["beats"][0])
    beat.pop("o3_generate_mode", None)
    assert bg.resolve_o3_generate_mode(beat, sidecar) == bg.O3_GENERATE_MODE_ELEMENT_NATIVE


def test_set_pipeline_rejects_avatar_when_disabled():
    bg_src = Path(__file__).resolve().parents[1] / "server_handlers" / "background.py"
    text = bg_src.read_text(encoding="utf-8")
    block = text.split("def handle_bg_set_pipeline", 1)[1].split("\ndef handle_", 1)[0]
    assert "BEATGEN_AVATAR_DISABLED" in block
    assert "beatgen_avatar_pro_disabled" in block


def test_submit_rejects_avatar_when_disabled():
    bg_src = Path(__file__).resolve().parents[1] / "server_handlers" / "background.py"
    text = bg_src.read_text(encoding="utf-8")
    block = text.split("def handle_bg_submit_arlo_o3_voice", 1)[1].split("\ndef handle_", 1)[0]
    assert "BEATGEN_AVATAR_DISABLED" in block


def test_bgtab_restores_element_and_voice_first_toggles():
    src = Path(__file__).resolve().parents[1] / "storyboard-v2" / "src" / "components" / "BgTab.tsx"
    text = src.read_text(encoding="utf-8")
    assert "bg-pipeline-element-native" in text
    assert "bg-pipeline-voice-first" in text
    assert "bg-pipeline-avatar" not in text
    assert "onSetGenerationMode('avatar_pro')" not in text


def test_phase_b_module_handler_uses_path_a_not_avatar_pro():
    # PHASE_B_PATH_A_ROUTE_V1 replaced both Avatar Pro and the
    # single-pass/segmented whole-frame Kling fork.
    phases = Path(__file__).resolve().parents[1] / "server_handlers" / "phases.py"
    block = phases.read_text(encoding="utf-8").split("def handle_phase_b_lipsync", 1)[1]
    block = block.split("\ndef _finalize_phase_a_lipsync_delivery", 1)[0]
    assert "submit_avatar_pro" not in block
    assert "run_phase_b_path_a_lipsync" in block
    assert "PHASE_B_PATH_A_ROUTE_V1" in block
    assert "PHASE_B_KLING_SEGMENT_STRATEGY_LEGACY" not in block


def test_phase_b_module_unchanged():
    mod = Path(__file__).resolve().parents[1] / "phase_b_avatar_lipsync.py"
    text = mod.read_text(encoding="utf-8")
    assert "PHASE_B_LIPSYNC_METHOD_AVATAR" in text
    assert "resolve_phase_b_cedric_still" in text
    assert "AVATAR_PRO_PROHIBIT" in text
    assert "no Chinese characters" in text
