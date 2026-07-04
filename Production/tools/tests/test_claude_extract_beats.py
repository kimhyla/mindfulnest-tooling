"""Unit tests for slice_skeleton_section (TECH_SPEC_CLAUDE_SUGGEST_BEATS_v1 §3/P0)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

import beat_generator as bg  # noqa: E402

DROPBOX = Path.home() / (
    "Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files"
)
ARC1 = DROPBOX / "Arc Skeletons" / "ARC_01_SKELETON_FINAL.md"


@pytest.fixture(autouse=True)
def _patch_skeleton_base(monkeypatch):
    if ARC1.is_file():
        monkeypatch.setattr(bg, "_SKELETON_BASE", str(ARC1.parent))


@pytest.mark.skipif(not ARC1.is_file(), reason="Dropbox ARC_01 skeleton not available")
def test_slice_event1_pre_non_empty():
    section = bg.slice_skeleton_section(1, "1", "pre")
    assert section["slice_method"] in ("regex_setup", "regex_bold_intro")
    assert section["char_count"] > 500
    assert "Tessa" in section["text"] or "Guide Bird" in section["text"]


@pytest.mark.skipif(not ARC1.is_file(), reason="Dropbox ARC_01 skeleton not available")
def test_slice_event1_post_resolution():
    section = bg.slice_skeleton_section(1, "1", "post")
    assert section["slice_method"] == "regex_resolution"
    assert section["char_count"] > 200


@pytest.mark.skipif(not ARC1.is_file(), reason="Dropbox ARC_01 skeleton not available")
def test_slice_event2_pre_luna():
    section = bg.slice_skeleton_section(1, "2", "pre")
    assert section["char_count"] > 300
    assert section.get("m_number") == 2


def test_merge_policy_preserves_approved(monkeypatch, tmp_path):
    sidecar = {"arcs": {"arc_1": {"segments": {}}}}
    seg = bg.get_seg_entry(sidecar, 1, "9", "pre")
    seg["beats"] = [
        {
            "beat_id": "bg_arc1_event9_pre_beat_01",
            "speaker": "Tessa",
            "dialogue_text": "old",
            "kling_o3_status": "approved",
            "kling_o3_video_path": str(tmp_path / "clip.mp4"),
        },
    ]
    (tmp_path / "clip.mp4").write_text("x", encoding="utf-8")
    plan = [{
        "beat_index": 1,
        "beat_type": "dialogue",
        "speaker": "Tessa",
        "dialogue_text": "new line",
        "emotion": "warm",
        "scene_notes": "forest",
    }]
    prompts = {1: "@Image1 (Tessa) Tessa — Test. Scene from @Image2.\n\nCamera: static locked shot.\n\n\"new line\"\n\nChildren's illustrated fantasy storybook style, warm golden forest light."}
    monkeypatch.setattr(bg, "append_intro_canonical_tail_beats", lambda *a, **k: None)
    merged = bg.apply_approved_extract_plan(
        sidecar, 1, "9", "pre", "summary", plan, prompts, force=False,
    )
    approved = [b for b in merged if b.get("kling_o3_status") == "approved"]
    assert len(approved) >= 1


def test_normalize_beats_plan_reindexes_and_casts():
    from claude_extract_beats import normalize_beats_plan

    rows = normalize_beats_plan([
        {"speaker": "Luna", "dialogue_text": "Hi", "beat_index": 5},
        {"speaker": "Chipper", "dialogue_text": "Hey", "beat_index": 2},
    ])
    assert [r["beat_index"] for r in rows] == [1, 2]
    assert rows[0]["speaker"] == "Lorelai"
    assert rows[1]["speaker"] == "Arlo"


def test_build_beats_stage_still_vs_dialogue_action():
    still_plan = [{
        "beat_index": 1,
        "beat_type": "stage_still",
        "speaker": "[Stage Direction]",
        "dialogue_text": "",
        "scene_notes": "Inscription still insert",
        "emotion": "neutral",
    }]
    action_plan = [{
        "beat_index": 1,
        "beat_type": "dialogue",
        "speaker": "Benson",
        "dialogue_text": "(hiccup — dives back into burrow)",
        "scene_notes": "Baby bunny at burrow lip.",
        "emotion": "comedic, startled",
    }]
    still_beats = bg.build_beats_from_approved_plan(
        still_plan, {}, arc_number=1, event_id="2", phase="pre",
    )
    action_beats = bg.build_beats_from_approved_plan(
        action_plan, {}, arc_number=1, event_id="5", phase="pre",
    )
    assert still_beats[0]["pipeline"] == "still_insert"
    assert still_beats[0]["beat_render_mode"] == "still_insert"
    assert action_beats[0]["pipeline"] == "kling_o3_omni"
    assert action_beats[0]["beat_type"] == "dialogue"
    assert action_beats[0]["speaker"] == "Benson"


def test_parse_claude_json_trailing_comma_and_preamble():
    from claude_extract_beats import _parse_claude_json

    raw = 'Here is the plan:\n```json\n{"story_summary": "ok", "beats_plan": [{"beat_index": 1},],}\n```'
    parsed = _parse_claude_json(raw)
    assert parsed["story_summary"] == "ok"
    assert len(parsed["beats_plan"]) == 1


def test_parse_structured_tool_response():
    from claude_extract_beats import _parse_structured_response

    resp = {
        "content": [
            {
                "type": "tool_use",
                "name": "submit_beat_plan",
                "input": {
                    "story_summary": "Lorelai discovers the Nest.",
                    "beats_plan": [{"beat_index": 1, "speaker": "Lorelai"}],
                },
            }
        ]
    }
    parsed = _parse_structured_response(resp, tool_name="submit_beat_plan")
    assert parsed["story_summary"].startswith("Lorelai")
    assert parsed["beats_plan"][0]["speaker"] == "Lorelai"
