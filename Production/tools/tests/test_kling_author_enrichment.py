"""Phase B Kling author enrichment + extract approve merge policy."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

import beat_generator as bg  # noqa: E402
from beat_extract_policy import postprocess_kling_author_row, postprocess_kling_author_results  # noqa: E402


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
