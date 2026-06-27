"""Anti-regression contracts — operator kling_o3_prompt must not mutate after materialize."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path
from unittest.mock import patch

import beat_generator as bg
import o3_generation_intent as intent_mod

TOOLS = Path(__file__).resolve().parent.parent
PIPELINE = TOOLS / "kling_o3_element_beat_pipeline.py"
BEAT_GEN = TOOLS / "beat_generator.py"
EXTRACT = TOOLS / "beat_extract_policy.py"
INTENT = TOOLS / "o3_generation_intent.py"

BEAT15_PROMPT = (
    "@Image1 (Loral). Scene from @Image2.\n\n"
    "Camera: static locked shot.\n\n"
    'Loral speaks in a warm excited conversational pace: [gleeful panic, frantic, over-excited] '
    '"Ohhhh what does it MEAN?! [pause]" (thinking it over) '
    '"Oh, I just HAVE to solve this mystery!!"\n\n'
    "Children's illustrated fantasy storybook style"
)


def _fn_body(path: Path, name: str) -> str:
    mod = path.stem
    if mod == "beat_generator":
        import beat_generator as mod_obj

        fn = getattr(mod_obj, name)
    elif mod == "beat_extract_policy":
        from beat_extract_policy import heal_beat_kling_o3_prompt_event1_shape as fn
        if name != "heal_beat_kling_o3_prompt_event1_shape":
            raise KeyError(name)
    else:
        raise KeyError(mod)
    return inspect.getsource(fn)


def test_prepare_kling_o3_prompt_for_submit_is_strip_only():
    src = _fn_body(BEAT_GEN, "prepare_kling_o3_prompt_for_submit")
    assert "normalize_o3_element_bound_prompt" not in src
    assert "align_element_bound_kling_display_names" not in src
    assert "_append_kling_o3_submit_locks" not in src
    assert "inject_locked_voice_line" not in src
    tree = ast.parse(src)
    returns = [n for n in ast.walk(tree) if isinstance(n, ast.Return) and n.value]
    assert len(returns) == 1
    assert isinstance(returns[0].value, ast.Call)
    assert isinstance(returns[0].value.func, ast.Attribute)
    assert returns[0].value.func.attr == "strip"


def test_migrate_heal_functions_are_no_ops():
    beat = {
        "beat_id": "bg_arc1_event2_pre_beat_15",
        "speaker": "Lorelai",
        "kling_o3_prompt": BEAT15_PROMPT,
    }
    from beat_extract_policy import heal_beat_kling_o3_prompt_event1_shape

    assert bg.heal_spoken_staging_in_voice_prompt(beat) is False
    assert bg.heal_o3_element_submit_prompt(beat) is False
    assert bg.heal_element_bound_voice_prompt(beat) is False
    assert heal_beat_kling_o3_prompt_event1_shape(beat) is False
    assert beat["kling_o3_prompt"] == BEAT15_PROMPT


def test_migrate_sidecar_preserves_operator_prompt_without_law_flag():
    sidecar = {
        "schema_version": 3,
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_2_pre": {
                        "beats": [{
                            "beat_id": "bg_arc1_event2_pre_beat_15",
                            "speaker": "Lorelai",
                            "pipeline": "kling_o3_omni",
                            "kling_o3_prompt": BEAT15_PROMPT,
                        }],
                    },
                },
            },
        },
    }
    out = bg._migrate_sidecar(sidecar)
    beat = out["arcs"]["arc_1"]["segments"]["event_2_pre"]["beats"][0]
    assert beat["kling_o3_prompt"] == BEAT15_PROMPT


def test_element_pipeline_does_not_writeback_prompt_on_submit():
    text = PIPELINE.read_text(encoding="utf-8")
    submit_block = text.split('print(json.dumps({\n        "phase": "o3_submit"', 1)[1]
    submit_block = submit_block.split("result = o3.run_beat_generation", 1)[0]
    assert 'beat["kling_o3_prompt"]' not in submit_block


def test_build_generation_intent_prepared_matches_verbatim(tmp_path):
    from o3_generation_intent import build_generation_intent
    from unittest.mock import patch

    beat = {
        "beat_id": "bg_arc1_event2_pre_beat_15",
        "speaker": "Lorelai",
        "reference_image": {"abs_path": str(tmp_path / "char.png")},
        "bg_ref_image": {"abs_path": str(tmp_path / "bg.png")},
        "reference_image_locked": True,
        "element_char_ref_ok": True,
    }
    (tmp_path / "char.png").write_bytes(b"x")
    (tmp_path / "bg.png").write_bytes(b"y")
    event_dir = tmp_path / "Event_2"
    event_dir.mkdir()
    sidecar = {"arcs": {}}
    body = {
        "kling_o3_prompt": BEAT15_PROMPT,
        "reference_image": beat["reference_image"],
        "bg_ref_image": beat["bg_ref_image"],
    }
    with patch("tools.kling_character_registry.is_speaker_voice_ready", return_value=True), \
         patch("tools.kling_character_registry.char_ref_matches_element_images", return_value=(True, "")), \
         patch("beat_generator.resolve_o3_element_list_entry", return_value={"element_id": "e1", "voice_id": "v1"}), \
         patch("beat_generator.validate_proven_o3_element_submit", return_value=None), \
         patch("tools.kling_voice_bind.detect_voice_bind_drift", return_value=None), \
         patch("tools.kling_voice_bind.advance_o3_element_quality_for_proven_registry"), \
         patch.object(intent_mod, "beat_has_active_intent", return_value=False), \
         patch("beat_generator.highest_o3_generation_on_disk", return_value=0):
        committed = build_generation_intent(
            beat=beat,
            sidecar=sidecar,
            body=body,
            beat_id=beat["beat_id"],
            event_dir=event_dir,
            job_id="job1",
            attempt_id="attempt1",
            log_path=event_dir / "job.log",
            pipeline_script=PIPELINE,
            wavespeed_key="ws-key",
        )

    assert committed["prompt"]["verbatim"] == BEAT15_PROMPT
    assert committed["prompt"]["prepared_for_api"] == BEAT15_PROMPT


def test_humanize_never_touches_kling_o3_prompt_field():
    from beat_extract_policy import humanize_kling_body_parts_on_beat

    beat = {
        "speaker": "Lorelai",
        "dialogue_text": "waves with her flipper",
        "scene_notes": "waves with her flipper",
        "kling_o3_prompt": BEAT15_PROMPT,
    }
    assert humanize_kling_body_parts_on_beat(beat) is True
    assert beat["kling_o3_prompt"] == BEAT15_PROMPT
