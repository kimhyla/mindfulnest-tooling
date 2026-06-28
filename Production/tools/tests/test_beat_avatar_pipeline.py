"""Beat Gen Avatar Pro default routing + pipeline contract tests."""
from __future__ import annotations

import re
from pathlib import Path

from unittest.mock import patch

import beat_generator as bg
import pytest


def _sidecar_speak_beats() -> dict:
    return {
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_2_pre": {
                        "beats": [{
                            "beat_id": "bg_arc1_event2_pre_beat_08",
                            "speaker": "Tessa",
                            "dialogue_text": "Power source?",
                        }],
                    },
                    "event_1_pre": {
                        "beats": [{
                            "beat_id": "bg_arc1_event1_pre_beat_01",
                            "speaker": "Chipper",
                            "dialogue_text": "Hello",
                        }],
                    },
                },
            },
        },
    }


def test_resolve_element_native_default_for_speak_beats():
    sidecar = _sidecar_speak_beats()
    for seg in ("event_2_pre", "event_1_pre"):
        beat = sidecar["arcs"]["arc_1"]["segments"][seg]["beats"][0]
        assert bg.resolve_o3_generate_mode(beat, sidecar) == bg.O3_GENERATE_MODE_ELEMENT_NATIVE
        assert bg.resolve_beat_generation_mode(beat, sidecar) == bg.O3_GENERATE_MODE_ELEMENT_NATIVE


def test_sidecar_avatar_downgrades_when_omni_pin_active():
    sidecar = _sidecar_speak_beats()
    beat = sidecar["arcs"]["arc_1"]["segments"]["event_2_pre"]["beats"][0]
    beat["o3_generate_mode"] = bg.O3_GENERATE_MODE_AVATAR
    env = {"MN_O3_GENERATE_MODE": "element_native", "MN_BEATGEN_AVATAR_DISABLED": "1"}
    assert bg.resolve_o3_generate_mode(beat, sidecar, env=env) == bg.O3_GENERATE_MODE_ELEMENT_NATIVE


def test_env_override_voice_first_still_works():
    sidecar = _sidecar_speak_beats()
    beat = sidecar["arcs"]["arc_1"]["segments"]["event_1_pre"]["beats"][0]
    env = {"MN_O3_GENERATE_MODE": "voice_first"}
    assert bg.resolve_o3_generate_mode(beat, sidecar, env=env) == "voice_first"


def test_infer_o3_option_avatar_path():
    opt = {"video_path": "/tmp/bg_beat_01_chipper_avatar_pro.mp4", "source": "kling_o3_avatar_pro"}
    assert bg.infer_o3_option_pipeline_mode(opt) == bg.O3_GENERATE_MODE_AVATAR


def test_handler_routes_avatar_pipeline_script():
    text = (Path(__file__).resolve().parents[1] / "server_handlers" / "background.py").read_text(
        encoding="utf-8",
    )
    assert "arlo_avatar_beat_pipeline.py" in text
    assert "O3_GENERATE_MODE_AVATAR" in text


def test_avatar_pipeline_uses_submit_avatar_pro_not_lipsync():
    text = (Path(__file__).resolve().parents[1] / "arlo_avatar_beat_pipeline.py").read_text(
        encoding="utf-8",
    )
    assert "submit_avatar_pro" in text
    assert "encode_lipsync_input" not in text
    assert "KLING_O3_MODE_AVATAR" in text
    assert "sync_o3_selection_pipeline_fields(beat, sc_for_sync)" in text
    assert "sync_o3_selection_pipeline_fields(beat, sc)" not in text
    assert "write_intent_terminal" in text
    assert '_write_avatar_intent_terminal' in text
    assert "_g{generation}_avatar_pro" in text or "_g{generation}_avatar_pro.mp4" in text
    assert "if _is_user_selectable_o3_video(str(prior_video" not in text
    assert "prepare_avatar_pro_audio" in text
    assert "avatar_audio_pad" in text
    assert "encode_avatar_pro_delivery" in text
    assert "delivery_meta.get(\"delivery_profile\")" in text
    assert "standard when raw" not in text


def test_prepare_avatar_pro_audio_adds_lead_tail_padding(tmp_path):
    from beat_avatar_lipsync import prepare_avatar_pro_audio

    audio = tmp_path / "line.mp3"
    subprocess = __import__("subprocess")
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-t", "1.0", "-i", "sine=frequency=440:sample_rate=44100",
            "-codec:a", "libmp3lame", "-q:a", "2", str(audio),
        ],
        check=True,
        timeout=30,
    )
    padded, spoken, padded_dur = prepare_avatar_pro_audio(audio)
    assert spoken == pytest.approx(1.0, abs=0.08)
    assert padded_dur == pytest.approx(4.0, abs=0.12)
    assert padded.resolve() != audio.resolve()
    if padded.is_file():
        padded.unlink()


def test_apply_beat_continuity_chain_skips_stage_still_gap():
    from beat_extract_policy import apply_beat_continuity_chain

    beats = [
        {
            "beat_id": "b1",
            "speaker": "Arlo",
            "dialogue_text": "Welcome.",
            "kling_o3_prompt": "Arlo line.",
        },
        {
            "beat_id": "b2",
            "speaker": "[Stage Direction]",
            "beat_type": "stage_still",
            "kling_o3_prompt": "Still frame.",
        },
        {
            "beat_id": "b3",
            "speaker": "Oliver",
            "dialogue_text": "Thank you.",
            "kling_o3_prompt": "@Image1 (Oliver). Scene from @Image2.\n\nOliver speaks: \"Thank you.\"",
        },
    ]
    apply_beat_continuity_chain(beats)
    assert "Continuity:" in beats[2]["kling_o3_prompt"]
    assert "Before speaking, Oliver" in beats[2]["kling_o3_prompt"]
    assert "Welcome" not in beats[2]["kling_o3_prompt"]


def test_heal_sidecar_beat_continuity_injects_prompts():
    sidecar = {
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_3b_full": {
                        "beats": [
                            {
                                "beat_id": "b1",
                                "speaker": "Oliver",
                                "dialogue_text": "You did it.",
                                "kling_o3_prompt": "@Image1 (Oliver). Scene from @Image2.\n\nLine one.",
                            },
                            {
                                "beat_id": "b2",
                                "speaker": "Loral",
                                "dialogue_text": "Who are you?",
                                "kling_o3_prompt": "@Image1 (Loral). Scene from @Image2.\n\nLine two.",
                            },
                        ],
                    },
                },
            },
        },
    }
    assert bg.heal_sidecar_beat_continuity(sidecar) is True
    b2 = sidecar["arcs"]["arc_1"]["segments"]["event_3b_full"]["beats"][1]
    assert "Continuity:" in b2["kling_o3_prompt"]


def test_build_avatar_beat_prompt_includes_tripod_lock():
    from beat_avatar_lipsync import build_avatar_beat_prompt

    prompt = build_avatar_beat_prompt(
        {"kling_o3_prompt": "Chipper speaks: \"Hello kiddo.\""},
        speaker="Chipper",
    )
    assert "TRIPOD LOCK" in prompt
    assert "Chipper" in prompt or "Arlo" in prompt


def test_build_avatar_beat_prompt_preserves_fidelity_locks_not_broken_fragments():
    from beat_avatar_lipsync import build_avatar_beat_prompt

    o3 = (
        "@Image1 (Oliver). Scene from @Image2.\n\n"
        "Oliver stands at the tree line, hand pressed to his chest, eyes fixed forward in disbelief.\n\n"
        "Oliver speaks in a breathless tone: \"You did it.\"\n\n"
        "Children's illustrated fantasy storybook style, warm golden forest light.\n\n"
        "Only @Image1 is visible in the frame. No other characters on screen.\n\n"
        "Match @Image1 character appearance, proportions, and facial expression exactly. "
        "Do not change the character design from @Image1.\n\n"
        "Match the natural lighting on @Image1 to @Image2 exactly — same warm golden direction, "
        "same soft shadow depth, same color temperature on character and background.\n\n"
        "Audio: spoken character dialogue only."
    )
    prompt = build_avatar_beat_prompt({"kling_o3_prompt": o3}, speaker="Oliver")
    assert "portrait framing" not in prompt.lower()
    assert "Scene staging (frozen backdrop only)" not in prompt
    assert "Match Oliver character appearance" in prompt
    assert "Do not change the character design from Oliver" in prompt
    assert "input portrait of Oliver" in prompt
    assert "PROHIBIT:" in prompt
    assert "no Chinese characters" in prompt
    assert "tree line" in prompt
    assert "Only Oliver moves" in prompt
    assert "Continuity:" not in prompt
    assert "background scene exactly" not in prompt
    assert re.search(r"\bOnly\s*\n\s*Match\b", prompt) is None
    assert re.search(r"Match\s*\n\s*Match the natural lighting on\s*$", prompt) is None


def test_omni_restore_applies_element_char_ref_gate_for_sidecar_avatar():
    sidecar = _sidecar_speak_beats()
    beat = {
        **sidecar["arcs"]["arc_1"]["segments"]["event_2_pre"]["beats"][0],
        "o3_generate_mode": bg.O3_GENERATE_MODE_AVATAR,
        "reference_image": {"abs_path": "/tmp/lorelai_library_still.png"},
        "element_char_ref_ok": False,
        "element_char_ref_error": "stale element mismatch",
    }
    assert bg.resolve_o3_generate_mode(beat, sidecar) == bg.O3_GENERATE_MODE_ELEMENT_NATIVE
    assert bg.element_char_ref_required_for_beat(beat, sidecar) is True


def test_omni_restore_generation_gate_requires_element_when_sidecar_avatar(monkeypatch, tmp_path):
    import operator_workbench_contract as owc

    sidecar = _sidecar_speak_beats()
    still = tmp_path / "lorelai.png"
    still.write_bytes(b"\x89PNG\r\n")
    beat = {
        **sidecar["arcs"]["arc_1"]["segments"]["event_2_pre"]["beats"][0],
        "speaker": "Lorelai",
        "o3_generate_mode": bg.O3_GENERATE_MODE_AVATAR,
        "reference_image": {"abs_path": str(still)},
        "element_char_ref_ok": False,
        "element_char_ref_error": "does not match Element images",
    }
    gate = owc.resolve_beat_generation_gate(beat, sidecar)
    assert gate["generation_mode"] == bg.O3_GENERATE_MODE_ELEMENT_NATIVE
    assert gate["can_generate"] is False
    assert gate["element_char_ref_ok"] is False


def test_voice_first_still_requires_element_and_bg_ref_gates():
    sidecar = _sidecar_speak_beats()
    beat = sidecar["arcs"]["arc_1"]["segments"]["event_1_pre"]["beats"][0]
    beat = {
        **beat,
        "o3_generate_mode": "voice_first",
        "reference_image": {"abs_path": "/tmp/missing.png"},
    }
    assert bg.element_char_ref_required_for_beat(beat, sidecar) is True
    assert bg.o3_bg_ref_required_for_beat(beat, sidecar) is True


@patch("tools.kling_character_registry.is_speaker_voice_ready", return_value=True)
def test_avatar_pro_build_intent_char_ref_only_no_bg(_ready, tmp_path, monkeypatch):
    from o3_generation_intent import build_generation_intent

    monkeypatch.setenv("MN_BEATGEN_AVATAR_ALLOWED", "1")

    char = tmp_path / "lorelai_portrait.png"
    char.write_bytes(b"\x89PNG\r\n")
    beat = {
        "beat_id": "bg_arc1_event2_pre_beat_02",
        "speaker": "Lorelai",
        "o3_generate_mode": bg.O3_GENERATE_MODE_AVATAR,
        "reference_image": {"abs_path": str(char), "reference_image_locked": True},
        "kling_o3_prompt": 'Loral (female raccoon) speaks: "Hello kiddo"',
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
    event_dir = tmp_path / "Event_2"
    event_dir.mkdir()
    intent = build_generation_intent(
        beat=beat,
        sidecar=sidecar,
        body={
            "kling_o3_prompt": beat["kling_o3_prompt"],
            "generation_mode": bg.O3_GENERATE_MODE_AVATAR,
            "reference_image": beat["reference_image"],
        },
        beat_id=beat["beat_id"],
        event_dir=event_dir,
        job_id="avtr1234",
        attempt_id="attempt-avatar",
        log_path=event_dir / "arlo_o3_jobs" / "avtr1234_beat.log",
        pipeline_script=tmp_path / "arlo_avatar_beat_pipeline.py",
        wavespeed_key=None,
    )
    assert intent["generation_mode"] == bg.O3_GENERATE_MODE_AVATAR
    assert intent["visual"]["char_ref_abs_path"] == str(char.resolve())
    assert "bg_ref_abs_path" not in intent["visual"]
    assert intent["generation"]["master_clip_path"].endswith("_avatar_pro.mp4")
    assert "bg_ref_file_exists" not in intent["preflight"]["checks_passed"]


@patch(
    "operator_workbench_contract.materialize_o3_submit_refs",
    side_effect=lambda body, beat, **kw: (
        beat.get("reference_image"),
        None,
    ),
)
@patch(
    "tools.kling_character_registry.char_ref_matches_element_images",
    return_value=(True, None),
)
@patch("tools.kling_character_registry.is_speaker_voice_ready", return_value=True)
def test_voice_first_build_intent_still_requires_bg_ref(_ready, _aligned, _refs, tmp_path):
    from o3_generation_intent import IntentCommitError, build_generation_intent

    char = tmp_path / "char.png"
    char.write_bytes(b"char")
    beat = {
        "beat_id": "bg_arc1_event1_pre_beat_01",
        "speaker": "Chipper",
        "o3_generate_mode": bg.O3_GENERATE_MODE_VOICE_FIRST,
        "reference_image": {"abs_path": str(char)},
        "kling_o3_prompt": 'Chipper speaks: "Hi"',
    }
    sidecar = _sidecar_speak_beats()
    event_dir = tmp_path / "Event_1"
    event_dir.mkdir()
    with pytest.raises(IntentCommitError) as exc:
        build_generation_intent(
            beat=beat,
            sidecar=sidecar,
            body={
                "kling_o3_prompt": beat["kling_o3_prompt"],
                "generation_mode": bg.O3_GENERATE_MODE_VOICE_FIRST,
                "reference_image": beat["reference_image"],
            },
            beat_id=beat["beat_id"],
            event_dir=event_dir,
            job_id="vf123456",
            attempt_id="attempt-vf",
            log_path=event_dir / "arlo_o3_jobs" / "vf123456_beat.log",
            pipeline_script=tmp_path / "arlo_o3_voice_pipeline.py",
            wavespeed_key=None,
        )
    assert exc.value.error_code == "MISSING_O3_REF"
