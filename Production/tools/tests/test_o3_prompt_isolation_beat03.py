"""Golden beat_03 regressions — still-insert prompt must not reach O3 Generate."""
from __future__ import annotations

from pathlib import Path

import beat_generator as bg
import pytest
from o3_generation_intent import IntentCommitError, build_generation_intent

BEAT03_STILL_PROMPT = (
    "STILL INSERT — use pre-made GPT still from library; do not submit to Kling O3 Element.\n"
    "Eyes wide with pleasant surprise, bright smile; one hand holds a rolled map up and "
    "glances at it, then back to camera — rooted in place, no locomotion.\n\n"
    "Assign the still image in Beat Gen. No @Image1 character clip for this beat."
)
BEAT03_O3_PROMPT = (
    "@Image1 (Loral). Scene from @Image2.\n\n"
    "Camera: static locked shot.\n\n"
    'Loral speaks in a warm excited conversational pace: [excited] '
    '"I\'m Loral. From Raccoon College. Is this ... ancient Everdale?"\n\n'
    "Children's illustrated fantasy storybook style, warm soft lighting"
)


def _beat03_sidecar(*, o3_generate_mode: str = "element_native") -> tuple[dict, dict]:
    beat = {
        "beat_id": "bg_arc1_event2_pre_beat_03",
        "speaker": "Lorelai",
        "dialogue_text": (
            'Lorelai [excited]: "I\'m Loral. From Raccoon College. Is this ... ancient Everdale?"'
        ),
        "pipeline": "kling_o3_omni",
        "o3_generate_mode": o3_generate_mode,
        "kling_o3_prompt": BEAT03_STILL_PROMPT,
        "kling_o3_prompt_still": BEAT03_STILL_PROMPT,
        "kling_o3_video_path": (
            "/Event_2/kling_o3_clips/bg_arc1_event2_pre_beat_03_lorelai_voice_lipsync_delivery.mp4"
        ),
        "kling_o3_options": [
            {
                "key": "lipsync",
                "video_path": (
                    "/Event_2/kling_o3_clips/"
                    "bg_arc1_event2_pre_beat_03_lorelai_voice_lipsync_delivery.mp4"
                ),
                "source": "kling_o3_voice_video",
                "active": True,
            },
            {
                "key": "g10",
                "video_path": (
                    "/Event_2/kling_o3_clips/"
                    "bg_arc1_event2_pre_beat_03_g10_element_o3_master_delivery.mp4"
                ),
                "source": "kling_o3_element_native_voice",
                "active": False,
                "generation": 10,
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


def test_validate_blocks_still_insert_on_element_native():
    ok, code, _msg = bg.validate_o3_submit_prompt_for_mode(
        BEAT03_STILL_PROMPT,
        bg.O3_GENERATE_MODE_ELEMENT_NATIVE,
    )
    assert ok is False
    assert code == "STILL_INSERT_PROMPT_ON_O3_MODE"


def test_validate_blocks_still_insert_on_voice_first():
    ok, code, _msg = bg.validate_o3_submit_prompt_for_mode(
        BEAT03_STILL_PROMPT,
        bg.O3_GENERATE_MODE_VOICE_FIRST,
    )
    assert ok is False
    assert code == "STILL_INSERT_PROMPT_ON_O3_MODE"


def test_validate_allows_o3_prompt_on_element_native():
    ok, code, _msg = bg.validate_o3_submit_prompt_for_mode(
        BEAT03_O3_PROMPT,
        bg.O3_GENERATE_MODE_ELEMENT_NATIVE,
    )
    assert ok is True
    assert code == ""


def test_heal_beat_dual_prompts_restores_o3_text():
    sidecar, beat = _beat03_sidecar(o3_generate_mode="element_native")
    changed = bg.heal_beat_dual_prompts(beat, sidecar, event_id="2", phase="pre")
    assert changed is True
    assert beat.get("kling_o3_prompt_still") == BEAT03_STILL_PROMPT
    assert not bg.is_still_insert_prompt_text(beat.get("kling_o3_prompt") or "")
    assert "@Image1 (Loral)" in (beat.get("kling_o3_prompt") or "")


def test_stamp_delivery_coherence_pins_element_mode():
    sidecar, beat = _beat03_sidecar(o3_generate_mode="voice_first")
    bg.stamp_o3_delivery_pipeline_coherence(
        beat,
        sidecar,
        generation_mode=bg.O3_GENERATE_MODE_ELEMENT_NATIVE,
    )
    assert beat.get("o3_generate_mode") == bg.O3_GENERATE_MODE_ELEMENT_NATIVE
    assert beat.get("kling_o3_generate_mode") == bg.O3_GENERATE_MODE_ELEMENT_NATIVE
    assert beat.get("kling_o3_mode") == bg.KLING_O3_MODE_ELEMENT_NATIVE
    assert not beat.get("kling_o3_selection_pipeline_mismatch")


def test_submit_handler_blocks_still_insert_before_intent():
    src = Path(__file__).resolve().parents[1] / "server_handlers" / "background.py"
    block = src.read_text(encoding="utf-8").split("def handle_bg_submit_arlo_o3_voice", 1)[1]
    block = block.split("\ndef handle_bg_submit_kling", 1)[0]
    assert "validate_o3_submit_prompt_for_mode" in block
    assert "heal_beat_dual_prompts" not in block
    assert 'beat["o3_generate_mode"]' in block


def test_ui_blocks_still_insert_before_submit():
    src = Path(__file__).resolve().parents[1] / "storyboard-v2" / "src" / "components" / "BgTab.tsx"
    text = src.read_text(encoding="utf-8")
    assert "bg-o3-still-prompt-block" in text
    assert "generation_mode: generationMode" in text
    assert "beatPromptText(beat, activeScope.value.event_id)" in text


def test_build_generation_intent_rejects_still_insert_prompt(monkeypatch, tmp_path):
    sidecar, beat = _beat03_sidecar(o3_generate_mode="element_native")
    event_dir = tmp_path / "Event_2"
    event_dir.mkdir()
    (event_dir / "arlo_o3_jobs").mkdir()
    char = event_dir / "char.png"
    bgf = event_dir / "bg.png"
    char.write_bytes(b"x")
    bgf.write_bytes(b"y")

    monkeypatch.setattr(
        "tools.kling_character_registry.is_speaker_voice_ready",
        lambda _s: True,
    )
    monkeypatch.setattr(
        "tools.kling_character_registry.char_ref_matches_element_images",
        lambda *_a, **_k: (True, None),
    )
    monkeypatch.setattr(
        "beat_generator.resolve_o3_element_list_entry",
        lambda *_a, **_k: {
            "element_id": "313441038164306",
            "element_name": "Loral",
            "voice_id": "895210468825628751",
        },
    )
    monkeypatch.setattr("beat_generator.validate_proven_o3_element_submit", lambda *_a, **_k: None)
    monkeypatch.setattr("beat_generator.highest_o3_generation_on_disk", lambda *_a, **_k: 9)
    monkeypatch.setattr("o3_generation_intent.beat_has_active_intent", lambda *_a, **_k: False)

    body = {
        "kling_o3_prompt": BEAT03_STILL_PROMPT,
        "generation_mode": "element_native",
        "reference_image": {"abs_path": str(char)},
        "bg_ref_image": {"abs_path": str(bgf)},
    }
    with pytest.raises(IntentCommitError) as exc:
        build_generation_intent(
            beat=beat,
            sidecar=sidecar,
            body=body,
            beat_id=beat["beat_id"],
            event_dir=event_dir,
            job_id="deadbeef",
            attempt_id="a" * 32,
            log_path=event_dir / "arlo_o3_jobs" / "deadbeef.log",
            pipeline_script=tmp_path / "kling_o3_element_beat_pipeline.py",
            wavespeed_key="ws-test",
        )
    assert exc.value.error_code == "STILL_INSERT_PROMPT_ON_O3_MODE"
