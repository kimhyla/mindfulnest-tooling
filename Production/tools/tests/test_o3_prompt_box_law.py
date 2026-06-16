"""Regression — prompt-box law: Generate payload is what Kling hears."""
from __future__ import annotations

import re
from pathlib import Path

import beat_generator as bg
from kling_o3_element_beat_pipeline import resolve_element_o3_submit_prompt

BACKGROUND = Path(__file__).resolve().parent.parent / "server_handlers" / "background.py"

USER_LINE = (
    "OK, Kiddo. CUSTOM USER LINE ONLY. She knows the MindfulNest! "
    "But she's stressed. Let's see if the Wizard can teach you a calming spell."
)
USER_PROMPT = (
    "@Image1 (Arlo). Scene from @Image2.\n\n"
    "Camera: static locked shot.\n\n"
    f'Arlo speaks in a warm calm conversational pace: [warm] "{USER_LINE}"\n\n'
    "Children's illustrated fantasy storybook style, warm soft lighting"
)
CANON_COMPACT = (
    "OK, Kiddo. Lorelai's our best chance. She knows the MindfulNest! "
    "But she's stressed. Let's see if the Wizard can teach you a calming spell."
)


def _semi_canonical_arlo_beat() -> dict:
    return {
        "beat_id": "bg_arc1_event2_pre_beat_24",
        "speaker": "Arlo",
        "intro_beat_role": bg.INTRO_BEAT_ROLE_SEMI_CANONICAL,
        "emotion": "upbeat",
        "dialogue_text": CANON_COMPACT,
        "kling_o3_prompt": USER_PROMPT,
        "o3_prompt_box_law": True,
    }


def test_stamp_and_active_helpers():
    beat: dict = {}
    bg.stamp_o3_prompt_box_law(beat, USER_PROMPT)
    assert beat.get("o3_prompt_box_law") is True
    assert beat.get("kling_o3_prompt") == USER_PROMPT
    assert bg.o3_prompt_box_law_active(beat)
    bg.clear_o3_prompt_box_law(beat)
    assert not bg.o3_prompt_box_law_active(beat)


def test_prepare_returns_prompt_verbatim():
    beat = _semi_canonical_arlo_beat()
    prepared = bg.prepare_kling_o3_prompt_for_submit(beat, USER_PROMPT)
    assert prepared == USER_PROMPT
    assert "Only @Image1 is visible" not in prepared


def test_heal_o3_element_submit_prompt_skipped_under_prompt_box_law():
    beat = _semi_canonical_arlo_beat()
    assert bg.heal_o3_element_submit_prompt(beat) is False
    assert USER_LINE in (beat.get("kling_o3_prompt") or "")


def test_heal_o3_element_submit_prompt_skipped_for_still_insert():
    custom = (
        '@Image1 (Loral). Scene from @Image2.\n\n'
        'Camera: static locked shot.\n\n'
        'Loral speaks in a warm excited conversational pace: "Hello kiddo."\n\n'
        "Children's illustrated fantasy storybook style"
    )
    beat = {
        "beat_id": "bg_arc1_event2_pre_beat_01",
        "speaker": "Lorelai",
        "pipeline": "still_insert",
        "kling_o3_prompt": custom,
    }
    assert bg.heal_o3_element_submit_prompt(beat) is False
    assert beat.get("kling_o3_prompt") == custom


def test_heal_element_bound_voice_prompt_skipped_for_still_insert():
    beat = {
        "beat_id": "bg_arc1_event2_pre_beat_01",
        "speaker": "Lorelai",
        "pipeline": "still_insert",
        "kling_o3_prompt": 'Loral speaks in a CUSTOM delivery pace: "CUSTOM LINE"',
    }
    assert bg.heal_element_bound_voice_prompt(beat) is False
    assert "CUSTOM delivery pace" in (beat.get("kling_o3_prompt") or "")


def test_resolve_element_o3_submit_prompt_preserves_user_line():
    beat = _semi_canonical_arlo_beat()
    prompt, spoken = resolve_element_o3_submit_prompt(beat)
    assert USER_LINE in prompt
    assert "CUSTOM USER LINE ONLY" in spoken
    assert CANON_COMPACT not in spoken


def test_submit_handler_uses_generation_intent_commit():
    text = BACKGROUND.read_text(encoding="utf-8")
    assert "build_generation_intent" in text
    assert "write_generation_intent" in text
    assert 'subprocess_env["MN_O3_INTENT_PATH"]' in text
    assert "stamp_o3_prompt_box_law" in text.split("handle_bg_submit_arlo_o3_voice")[1].split("def ")[0]
    assert "ensure_operator_insert_char_ref_parity" not in text.split("handle_bg_submit_arlo_o3_voice")[1].split("def ")[0]


def test_migrate_sidecar_skips_prompt_morph_when_prompt_box_law():
    from beat_extract_policy import humanize_kling_body_parts_on_beat, heal_beat_kling_o3_prompt_event1_shape

    custom = "CUSTOM PROMPT LINE XYZ — do not rewrite."
    sidecar = {
        "schema_version": 3,
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_2_pre": {
                        "beats": [{
                            "beat_id": "bg_arc1_event2_pre_beat_30",
                            "speaker": "Lorelai",
                            "kling_o3_prompt": custom,
                            "o3_prompt_box_law": True,
                        }],
                    },
                },
            },
        },
    }
    out = bg._migrate_sidecar(sidecar)
    beat = out["arcs"]["arc_1"]["segments"]["event_2_pre"]["beats"][0]
    assert beat["kling_o3_prompt"] == custom
    assert humanize_kling_body_parts_on_beat(beat) is False
    assert heal_beat_kling_o3_prompt_event1_shape(beat) is False


def test_migrate_sidecar_skips_prompt_morph_without_prompt_box_law():
    """Any stored kling_o3_prompt skips migrate heals — law flag not required."""
    custom = "Lorelai speaks in a CUSTOM pace: \"Keep me verbatim.\""
    sidecar = {
        "schema_version": 3,
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_2_pre": {
                        "beats": [{
                            "beat_id": "bg_arc1_event2_pre_beat_15",
                            "speaker": "Lorelai",
                            "kling_o3_prompt": custom,
                        }],
                    },
                },
            },
        },
    }
    out = bg._migrate_sidecar(sidecar)
    beat = out["arcs"]["arc_1"]["segments"]["event_2_pre"]["beats"][0]
    assert beat["kling_o3_prompt"] == custom
    assert bg.heal_spoken_staging_in_voice_prompt(beat) is False


def test_finalize_proven_element_preserves_prompt_box_law(tmp_path):
    sidecar_path = tmp_path / "beat_generator_state.json"
    src_ref = {"abs_path": str(tmp_path / "char.png")}
    src_bg = {"abs_path": str(tmp_path / "bg.png")}
    (tmp_path / "char.png").write_bytes(b"x")
    (tmp_path / "bg.png").write_bytes(b"y")
    sidecar = {
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_2_pre": {
                        "beats": [
                            {
                                "beat_id": "bg_arc1_event2_pre_beat_18",
                                "speaker": "Lorelai",
                                "reference_image": src_ref,
                                "bg_ref_image": src_bg,
                            },
                        ],
                    },
                },
            },
        },
    }
    sidecar_path.write_text("{}", encoding="utf-8")
    custom = (
        '@Image1 (Loral). Scene from @Image2.\n\n'
        'Loral speaks in a female voice: "Hello kiddo."\n\n'
        "Children's illustrated fantasy storybook style"
    )
    beat = {
        "beat_id": "bg_arc1_event2_pre_beat_30",
        "speaker": "Lorelai",
        "beat_plan_source": "operator_insert_v1",
        "kling_o3_prompt": custom,
    }
    bg.stamp_o3_prompt_box_law(beat, custom)
    bg.finalize_proven_element_beat(beat, sidecar, "Lorelai", event_id="2", phase="pre")
    assert bg.o3_prompt_box_law_active(beat)
    assert "female voice" in (beat.get("kling_o3_prompt") or "")
    assert beat.get("kling_o3_prompt") == custom


def test_heal_element_bound_voice_prompt_skipped_under_prompt_box_law():
    beat = _semi_canonical_arlo_beat()
    beat["kling_o3_prompt"] = (
        '@Image1 (Arlo). Scene from @Image2.\n\n'
        'Arlo speaks in a CUSTOM delivery pace: "CUSTOM USER LINE ONLY"\n\n'
        "Children's illustrated fantasy storybook style"
    )
    assert bg.heal_element_bound_voice_prompt(beat) is False
    assert "CUSTOM delivery pace" in (beat.get("kling_o3_prompt") or "")


def test_prepare_is_verbatim_without_law_flag():
    beat = _semi_canonical_arlo_beat()
    beat.pop("o3_prompt_box_law", None)
    prepared = bg.prepare_kling_o3_prompt_for_submit(beat, USER_PROMPT)
    assert prepared == USER_PROMPT


def test_prepare_preserves_registry_staging_name_verbatim():
    """Operator text is never rewritten on submit — including Lorelai in staging."""
    import kling_o3_prompt as o3p

    bad_prompt = (
        "@Image1 (Lorelai). Scene from @Image2.\n\n"
        "Lorelai knits her brow in puzzlement, slight head tilt.\n\n"
        f'Loral speaks in a warm excited conversational pace: '
        '[excited] "Oh. My. Gosh. Did you — No way. This Rune stone is AWAKE? How?!"'
    )
    beat = {
        "speaker": "Lorelai",
        "o3_prompt_box_law": True,
        "kling_o3_prompt": bad_prompt,
    }
    prepared = bg.prepare_kling_o3_prompt_for_submit(beat, bad_prompt)
    assert prepared == bad_prompt
    assert "@Image1 (Lorelai)" in prepared


def test_still_flip_header_preserved_verbatim_on_submit():
    """Beat 10 shape: still-insert header stays exactly as operator wrote it."""
    prompt = (
        "@Image1 (Loral) Loral — Lorelai — Still insert — GPT still. Scene from @Image2.\n\n"
        "Loral is a female raccooon.\n\n"
        'Loral speaks in a warm excited conversational pace: "Hi"'
    )
    beat = {"speaker": "Lorelai", "o3_prompt_box_law": True, "kling_o3_prompt": prompt}
    prepared = bg.prepare_kling_o3_prompt_for_submit(beat, prompt)
    assert prepared == prompt


def test_still_to_o3_flip_does_not_rewrite_prompt(monkeypatch):
    monkeypatch.setattr(
        "tools.kling_character_registry.is_speaker_voice_ready",
        lambda _s: True,
    )
    monkeypatch.setattr(
        "tools.kling_character_registry.kling_element_display_name",
        lambda _s: "Loral",
    )
    original_prompt = "STILL INSERT — Lorelai: \"Oh. My. Gosh.\""
    beat = {
        "beat_id": "bg_arc1_event2_pre_beat_08",
        "speaker": "Lorelai",
        "pipeline": "still_insert",
        "beat_render_mode": "still_insert",
        "scene_notes": "Lorelai knits her brow in puzzlement.",
        "dialogue_text": "Oh. My. Gosh.",
        "kling_o3_prompt": original_prompt,
        "o3_prompt_box_law": True,
    }
    bg.apply_beat_pipeline_o3_mode(beat, "2", "pre")
    assert beat.get("pipeline") == bg.PIPELINE_MODE_O3
    assert beat.get("kling_o3_prompt") == original_prompt


def test_beat15_custom_delivery_prompt_submits_verbatim():
    """Regression: bracket delivery tags + short speaks-in-a line must not block submit."""
    prompt = (
        "@Image1 (Loral). Scene from @Image2.\n\n"
        "Camera: static locked shot.\n\n"
        'Loral speaks in a warm excited conversational pace: [gleeful panic, frantic, over-excited] '
        '"Ohhhh what does it MEAN?! [pause]" (thinking it over) '
        '"Oh, I just HAVE to solve this mystery!!"\n\n'
        "Children's illustrated fantasy storybook style"
    )
    beat = {
        "speaker": "Lorelai",
        "o3_prompt_box_law": True,
        "kling_o3_prompt": prompt,
    }
    prepared = bg.prepare_kling_o3_prompt_for_submit(beat, prompt)
    assert prepared == prompt
    prompt2, spoken = resolve_element_o3_submit_prompt(beat)
    assert prompt2 == prompt
    assert "Ohhhh what does it MEAN" in spoken
    """Prompt textarea debounce must not re-run @Image1 Element gate or emit gate fields."""
    text = BACKGROUND.read_text(encoding="utf-8")
    assert "_BG_ELEMENT_CHAR_REF_SYNC_FIELDS" in text
    assert "speaker" in text.split("_BG_ELEMENT_CHAR_REF_SYNC_FIELDS")[1][:120]
    assert "reference_image" in text.split("_BG_ELEMENT_CHAR_REF_SYNC_FIELDS")[1][:120]
    block = text[text.index("def handle_bg_update_beat"):text.index("\ndef handle_bg_reorder_beats")]
    assert re.search(
        r"if identity_fields_written:\s*\n\s*payload\[\"element_char_ref_ok\"\]",
        block,
    ), "gate fields must be omitted from prompt-only update-beat responses"
