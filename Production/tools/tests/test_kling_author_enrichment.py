"""Phase B Kling author enrichment + extract approve merge policy."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

TOOLS = Path(__file__).resolve().parent.parent
STORYBOARD_SRC = TOOLS / "storyboard-v2" / "src"
sys.path.insert(0, str(TOOLS))

import beat_generator as bg  # noqa: E402
from beat_extract_policy import (  # noqa: E402
    extract_spoken_from_dialogue,
    heal_beat_kling_o3_prompt_event1_shape,
    normalize_kling_o3_prompt_event1_quality,
    normalize_plan_row,
    postprocess_kling_author_row,
    postprocess_kling_author_results,
    repair_corrupted_plan_dialogue,
)


def test_extract_spoken_from_dialogue_ignores_scene_prefix_and_double_brackets():
    dialogue = (
        "Ancient mossy ruins in warm forest light. "
        'Lorelai [[muttering, lost]]: "Oooh ... Its got to be around here somewhere!"'
    )
    speaker, spoken = extract_spoken_from_dialogue(dialogue)
    assert speaker == "Lorelai"
    assert spoken == "Oooh ... Its got to be around here somewhere!"


def test_postprocess_infers_lorelai_and_spoken_only_in_voice_line():
    row = {
        "speaker": "Character",
        "dialogue_text": "Lorelai [[surprised, bright]]: Oh! Hi there!",
        "emotion": "[surprised, bright]",
        "scene_notes": "Eyes wide",
        "beat_type": "dialogue",
    }
    prompt = (
        "@Image1 (Character) Character — Discovery. Scene from @Image2.\n\n"
        'Lorelai speaks with warm energy: "wrong line"'
    )
    merged = postprocess_kling_author_row(row, prompt)
    assert "@Image1 (Laurel)" in merged["kling_o3_prompt"]
    assert "Laurel speaks" in merged["kling_o3_prompt"]
    assert "Lorelai speaks" not in merged["kling_o3_prompt"]
    assert "Oh! Hi there!" in merged["kling_o3_prompt"]


def test_postprocess_injects_emotion_staging_and_cast():
    plan = {
        "beat_index": 2,
        "beat_type": "dialogue",
        "speaker": "Tessa",
        "dialogue_text": "Hello ...",
        "emotion": "curious, polite",
        "scene_notes": "soft smile, gentle wave",
    }
    stale = (
        '@Image1 (Luna) Luna — Discovery. Scene from @Image2.\n\n'
        "Camera: static locked shot, no zoom, no dolly, no pan, no camera movement, "
        "stable eye-level medium shot.\n\n"
        '@Image1 <<<voice_1>>> speaks clearly at a natural pace: '
        '"WHAT is THAT. Is that . Is that IT.? Did I find it??"\n\n'
        "Children's illustrated fantasy storybook style, warm golden forest light."
    )
    out = postprocess_kling_author_row(plan, stale)
    prompt = out["kling_o3_prompt"]
    assert "@Image1 (Tessa)" in prompt
    assert "Luna" not in prompt
    assert "soft smile, gentle wave" in prompt
    assert "[curious, polite]" in prompt
    assert "Hello" in prompt
    assert "WHAT is THAT" not in prompt


def test_postprocess_kling_author_results_wires_all_indices():
    plan = [
        {
            "beat_index": 1,
            "beat_type": "dialogue",
            "speaker": "Lorelai",
            "dialogue_text": "Oh my goodness!",
            "emotion": "awe, breathless",
            "scene_notes": "eyes wide, mouth open",
        },
    ]
    prompts = {1: (
        "@Image1 (Lorelai) Lorelai — Discovery. Scene from @Image2.\n\n"
        "Camera: static locked shot.\n\n"
        'Lorelai says: "Oh my goodness!"'
    )}
    enriched_prompts, enriched_plan = postprocess_kling_author_results(plan, prompts)
    assert "[awe, breathless]" in enriched_prompts[1]
    assert "eyes wide" in enriched_prompts[1]
    assert enriched_plan[0]["emotion"] == "awe, breathless"


def test_build_beats_from_approved_plan_strips_corrupted_dialogue():
    plan = [{
        "beat_index": 4,
        "beat_type": "dialogue",
        "speaker": "Lorelai",
        "dialogue_text": "Character [[surprised, bright]]: Lorelai [[surprised, bright]]: Oh! Hi there!",
        "emotion": "[surprised, bright]",
        "scene_notes": "eyes wide",
    }]
    beats = bg.build_beats_from_approved_plan(
        plan, {4: "@Image1 (Lorelai) Lorelai says: Oh! Hi there!"},
        arc_number=1, event_id="2", phase="pre",
    )
    beat = beats[0]
    assert beat["speaker"] == "Lorelai"
    assert beat["dialogue_text"] == "Oh! Hi there!"
    assert beat["emotion"] == "surprised, bright"
    assert "[[" not in beat["dialogue_text"]


def test_extract_approve_replaces_stale_kling_prompt(monkeypatch, tmp_path):
    sidecar = {"arcs": {"arc_1": {"segments": {}}}}
    seg = bg.get_seg_entry(sidecar, 1, "2", "pre")
    seg["beats"] = [{
        "beat_id": "bg_arc1_event2_pre_beat_02",
        "speaker": "Tessa",
        "dialogue_text": "old wrong",
        "kling_o3_prompt": '@Image1 (Luna) stale prompt with wrong dialogue',
        "kling_o3_status": "draft",
    }]
    plan = [{
        "beat_index": 2,
        "beat_type": "dialogue",
        "speaker": "Tessa",
        "dialogue_text": "Hello ...",
        "emotion": "curious, polite",
        "scene_notes": "soft smile, gentle wave",
    }]
    fresh = (
        "@Image1 (Tessa) Tessa — Discovery. Scene from @Image2.\n\n"
        "Camera: static locked shot.\n\n"
        "Tessa — soft smile, gentle wave, rooted in place.\n\n"
        'Tessa says: "[curious, polite] Hello ..."'
    )
    monkeypatch.setattr(bg, "append_intro_canonical_tail_beats", lambda *a, **k: None)
    merged = bg.apply_approved_extract_plan(
        sidecar, 1, "2", "pre", "summary", plan, {2: fresh}, force=False,
    )
    beat = next(b for b in merged if b["beat_id"] == "bg_arc1_event2_pre_beat_02")
    assert "Luna" not in beat["kling_o3_prompt"]
    assert "Hello" in beat["kling_o3_prompt"]
    assert beat["emotion"] == "curious, polite"


def test_approved_beat_keeps_video_but_not_stale_prompt(monkeypatch):
    sidecar = {"arcs": {"arc_1": {"segments": {}}}}
    seg = bg.get_seg_entry(sidecar, 1, "2", "pre")
    stale_video = "/tmp/still_trimmed.mp4"
    seg["beats"] = [{
        "beat_id": "bg_arc1_event2_pre_beat_01",
        "speaker": "[Stage Direction]",
        "pipeline": "still_insert",
        "beat_render_mode": "still_insert",
        "kling_o3_prompt": '@Image1 (Luna) stale wrong prompt',
        "kling_o3_status": "approved",
        "kling_o3_video_path": stale_video,
        "kling_o3_options": [{"key": "x", "video_path": stale_video, "slot_index": 0}],
    }]
    plan = [{
        "beat_index": 1,
        "beat_type": "stage_still",
        "speaker": "[Stage Direction]",
        "dialogue_text": "Ancient ruins. [Still insert — GPT still]. Lorelai: hi",
        "emotion": "quiet establishing",
        "scene_notes": "eyes scan ruins, rooted in place",
    }]
    fresh_still = (
        "STILL INSERT — use pre-made GPT still from library; do not submit to Kling O3 Element.\n"
        "eyes scan ruins, rooted in place\n\n"
        "Assign the still image in Beat Gen. No @Image1 character clip for this beat."
    )
    monkeypatch.setattr(bg, "append_intro_canonical_tail_beats", lambda *a, **k: None)
    merged = bg.apply_approved_extract_plan(
        sidecar, 1, "2", "pre", "summary", plan, {1: fresh_still}, force=False,
    )
    beat = next(b for b in merged if b["beat_id"] == "bg_arc1_event2_pre_beat_01")
    assert "Luna" not in beat["kling_o3_prompt"]
    assert "STILL INSERT" in beat["kling_o3_prompt"]
    assert beat["kling_o3_video_path"] == stale_video
    assert beat["kling_o3_status"] == "approved"
    assert bg.audit_kling_author_enrichment(merged) == []


def test_audit_flags_stale_luna_prompt():
    beats = [{
        "beat_id": "bg_arc1_event2_pre_beat_02",
        "speaker": "Tessa",
        "dialogue_text": "Hello",
        "emotion": "curious",
        "scene_notes": "soft smile, rooted in place",
        "kling_o3_prompt": '@Image1 (Luna) Luna says: "Hello"',
        "pipeline": "kling_o3_omni",
    }]
    warnings = bg.audit_kling_author_enrichment(beats)
    assert any("Luna" in w for w in warnings)


def test_claude_author_calls_postprocess():
    from claude_extract_beats import claude_author_kling_prompts

    plan = [{
        "beat_index": 1,
        "beat_type": "dialogue",
        "speaker": "Arlo",
        "dialogue_text": "OK, Kiddo.",
        "emotion": "warm, to camera",
        "scene_notes": "faces camera, gentle nod",
    }]
    fake_resp = {
        "content": [{
            "type": "tool_use",
            "name": "submit_kling_prompts",
            "input": {
                "beats": [{
                    "beat_index": 1,
                    "kling_o3_prompt": (
                        "@Image1 (Arlo) Arlo — guide. Scene from @Image2.\n\n"
                        "Camera: static locked shot.\n\n"
                        'Arlo says: "OK, Kiddo."'
                    ),
                    "emotion": "warm, to camera",
                    "scene_notes": "faces camera, gentle nod",
                }],
            },
        }],
    }
    with patch("claude_extract_beats._call_anthropic", return_value=(fake_resp, 10)):
        with patch("claude_extract_beats.resolve_anthropic_api_key", return_value="test-key"):
            result = claude_author_kling_prompts("summary", plan, meta={"arc_number": 1, "event_id": "2", "phase": "pre"}, api_key="k")
    prompt = result["prompt_by_index"][1]
    assert "[warm, to camera]" in prompt
    assert "faces camera" in prompt
    assert result.get("beats_plan_enriched")


def test_wiring_author_tool_includes_emotion_fields():
    text = (TOOLS / "claude_extract_beats.py").read_text(encoding="utf-8")
    assert "postprocess_kling_author_results" in text
    assert '"emotion"' in text
    assert '"scene_notes"' in text
    assert "_EXTRACT_APPROVE_MERGE_PRESERVE" in (TOOLS / "beat_generator.py").read_text(encoding="utf-8")


def test_repair_corrupted_plan_dialogue_strips_character_wrapper():
    speaker, dialogue = repair_corrupted_plan_dialogue(
        "Character [[curious, polite]]: Tessa [[curious, polite]]: Hello ...",
        "Character",
    )
    assert speaker == "Tessa"
    assert dialogue == "Hello ..."


def test_normalize_plan_row_strips_bracket_emotion_and_repairs_dialogue():
    row, _warnings = normalize_plan_row({
        "beat_type": "dialogue",
        "speaker": "Character",
        "dialogue_text": "Character [[surprised, bright]]: Lorelai [[surprised, bright]]: Oh! Hi.",
        "emotion": "[surprised, bright]",
        "scene_notes": "eyes wide",
    }, beat_index=1)
    assert row["speaker"] == "Lorelai"
    assert row["emotion"] == "surprised, bright"
    assert row["dialogue_text"] == "Oh! Hi."
    assert "[[" not in row["dialogue_text"]


def test_beat_plan_format_parser_uses_dialogue_tail_not_emotion():
    fmt = (TOOLS / "storyboard-v2" / "src" / "components" / "beatPlanFormat.ts").read_text(
        encoding="utf-8",
    )
    assert "headerMatch[4].trim()" in fmt
    assert "headerMatch[3].trim()" not in fmt.replace("headerMatch[4].trim()", "")


def test_bgtab_prompt_box_is_kling_o3_prompt():
    text = (STORYBOARD_SRC / "components" / "BgTab.tsx").read_text(encoding="utf-8")
    assert "beatPromptText" in text
    assert "kling_o3_prompt: nextText" in text
    assert "mn-bg-kling-prompt-editor" in text
    assert "mn-bg-kling-prompt-body" not in text


def test_normalize_strips_species_taxonomy_and_upgrades_voice_delivery():
    stale = (
        "@Image1 (Tessa) Tessa — arc 1 event 2 pre, beat 02. Tessa is a small green sea turtle "
        "with a smooth domed shell, gentle dark eyes, and small front hands. Scene from @Image2.\n\n"
        "Camera: static locked shot, no zoom, no dolly, no pan, no camera movement, "
        "stable eye-level medium shot.  Tessa shown from waist up near front of the screen.\n\n"
        "Tessa holds a soft polite smile, one small hand rising in a gentle wave hello.\n\n"
        'Tessa speaks: "[curious, wary of danger] Hello...?"\n\n'
        "Children's illustrated fantasy storybook style, warm golden Everdale light."
    )
    out = normalize_kling_o3_prompt_event1_quality(
        stale,
        speaker="Tessa",
        dialogue="Hello ...",
        emotion="curious, polite",
        scene_notes="soft smile, gentle wave",
    )
    assert "is a small green sea turtle" not in out
    assert "waist up near front" not in out
    assert "speaks in a warm gentle conversational pace" in out
    assert "Silent world except speech" in out
    assert "Match @Image1 character appearance" in out


def test_heal_beat_migrate_rewrites_event2_tessa_prompt():
    beat = {
        "beat_id": "bg_arc1_event2_pre_beat_02",
        "speaker": "Tessa",
        "dialogue_text": "Hello ...",
        "emotion": "curious, polite",
        "scene_notes": "Soft polite smile; one hand rises in a small gentle wave",
        "kling_o3_prompt": (
            "@Image1 (Tessa) Tessa — arc 1 event 2 pre, beat 02. Tessa is a small green sea turtle "
            "with a smooth domed shell. Scene from @Image2.\n\n"
            'Tessa speaks: "[curious] Hello...?"'
        ),
        "pipeline": "kling_o3_omni",
    }
    assert heal_beat_kling_o3_prompt_event1_shape(beat) is True
    assert "is a small green sea turtle" not in beat["kling_o3_prompt"]
    assert "speaks in a warm gentle conversational pace" in beat["kling_o3_prompt"]


def test_normalize_identity_footer_replaces_drifted_species_anatomy():
    drifted = (
        "@Image1 (Tessa) Tessa — Discovery. Scene from @Image2.\n\n"
        "Match @Image1 character appearance, proportions, shell, flippers, and facial expression "
        "exactly. Do not change the character design from @Image1.\n\n"
        "Silent world except speech."
    )
    out = normalize_kling_o3_prompt_event1_quality(
        drifted,
        speaker="Tessa",
        dialogue="Hello",
        emotion="curious",
        scene_notes="soft smile",
    )
    assert "shell" not in out.lower() or "shell" not in out.split("Match @Image1")[1].split("\n\n")[0]
    assert bg.KLING_O3_IDENTITY_LOCK in out
    assert bg.identity_footer_is_canonical(out)


def test_audit_flags_identity_footer_drift():
    beats = [{
        "beat_id": "bg_arc1_event2_pre_beat_03",
        "speaker": "Lorelai",
        "dialogue_text": "Oh my goodness!",
        "emotion": "awe",
        "scene_notes": "eyes wide, rooted in place",
        "kling_o3_prompt": (
            "@Image1 (Lorelai) Lorelai — Discovery. Scene from @Image2.\n\n"
            "Match @Image1 character appearance, proportions, paws, and facial expression exactly.\n\n"
            'Lorelai speaks in a warm excited conversational pace: "Oh my goodness!"'
        ),
        "pipeline": "kling_o3_omni",
    }]
    warnings = bg.audit_kling_author_enrichment(beats)
    assert any("identity footer drift" in w for w in warnings)


def test_normalize_upgrades_lorelai_voice_delivery_to_laurel_slower():
    stale = (
        "@Image1 (Lorelai) Lorelai — Discovery. Scene from @Image2.\n\n"
        "Camera: static locked shot.\n\n"
        'Lorelai says: "[awe, breathless] Oh my goodness!"'
    )
    out = normalize_kling_o3_prompt_event1_quality(
        stale,
        speaker="Lorelai",
        dialogue="Oh my goodness!",
        emotion="awe, breathless",
        scene_notes="eyes wide, mouth open",
    )
    assert "Lorelai says:" not in out
    assert "Laurel speaks in a warm excited conversational pace" in out
    assert "@Image1 (Laurel)" in out
    assert "Lorelai speaks" not in out
    assert "slower steady rhythm" in out
    assert "not rushed or frantic" in out


def test_update_beat_accepts_kling_o3_prompt():
    text = (TOOLS / "server_handlers" / "background.py").read_text(encoding="utf-8")
    assert '"kling_o3_prompt"' in text.split("_BG_BEAT_WRITABLE")[1][:200]
    assert "sync_beat_dialogue_from_kling_prompt" in text


def test_submit_locks_append_lighting_when_image1_and_image2():
    raw = (
        "@Image1 (Lorelai) Lorelai — Discovery. Scene from @Image2.\n\n"
        "Camera: static locked shot.\n\n"
        'Lorelai speaks in a warm excited conversational pace: "Hello!"'
    )
    out = bg.prepare_kling_o3_prompt_for_submit({"speaker": "Lorelai"}, raw)
    assert bg.KLING_O3_LIGHTING_LOCK in out
    assert bg.KLING_O3_IDENTITY_LOCK in out


def test_build_kling_o3_prompt_includes_lighting_lock():
    beat = {
        "speaker": "Lorelai",
        "dialogue_text": "Hello!",
        "emotion": "neutral",
        "scene_notes": "soft smile",
    }
    out = bg.build_kling_o3_prompt(beat)
    assert bg.KLING_O3_LIGHTING_LOCK in out
