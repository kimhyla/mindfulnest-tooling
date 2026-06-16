"""Regression guard — Extract beats wiring must not be dropped silently."""
from __future__ import annotations

import re
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
STORYBOARD_SRC = TOOLS / "storyboard-v2" / "src"


def test_production_server_registers_extract_routes():
    text = (TOOLS / "production_server.py").read_text(encoding="utf-8")
    for path in (
        "/api/bg/extract-beats/plan",
        "/api/bg/extract-beats/approve",
        "/api/bg/extract-beats/draft",
        "/api/bg/extract-beats/draft/save",
        "/api/bg/extract-beats",
    ):
        assert path in text, f"missing route {path}"


def test_endpoints_ts_wires_extract_mutations():
    text = (STORYBOARD_SRC / "api" / "endpoints.ts").read_text(encoding="utf-8")
    for key in (
        "bg_extract_beats_plan",
        "bg_extract_beats_approve",
        "bg_extract_beats_draft",
        "bg_extract_beats_draft_save",
    ):
        assert key in text, f"missing endpoint key {key}"


def test_bgtab_single_extract_button_no_suggest():
    text = (STORYBOARD_SRC / "components" / "BgTab.tsx").read_text(encoding="utf-8")
    assert "bg-extract-btn" in text
    assert "Extract Beats from script" in text
    assert "bg-suggest-beats-btn" not in text
    assert "onSuggestBeats" not in text
    assert "Review saved plan" in text
    assert "openBeatPlanDraft" in text
    assert "extract-overwrite-confirm" in text
    assert "onBeatPlanAutosave" in text


def test_claude_extract_uses_structured_tools():
    text = (TOOLS / "claude_extract_beats.py").read_text(encoding="utf-8")
    assert "submit_beat_plan" in text
    assert "submit_kling_prompts" in text
    assert "postprocess_kling_author_results" in text
    assert "_parse_structured_response" in text
    assert 'tool_choice={"type": "tool"' in text


def test_background_handler_sidecar_lock_on_plan():
    text = (TOOLS / "server_handlers" / "background.py").read_text(encoding="utf-8")
    assert "handle_bg_extract_beats_plan" in text
    assert "sidecar_file_lock()" in text
    assert "beat_plan_draft" in text
    assert "persist_beat_plan_draft" in text


def test_beat_plan_modal_and_format_present():
    assert (STORYBOARD_SRC / "components" / "BeatPlanModal.tsx").is_file()
    assert (STORYBOARD_SRC / "components" / "beatPlanFormat.ts").is_file()
    fmt = (STORYBOARD_SRC / "components" / "beatPlanFormat.ts").read_text(encoding="utf-8")
    assert "formatEmotionForLine" in fmt
    assert "headerMatch[4]" in fmt
    assert "parseBeatPlanText" in fmt


def test_cast_policy_module_present():
    text = (TOOLS / "beat_extract_policy.py").read_text(encoding="utf-8")
    assert "postprocess_beats_plan" in text
    assert "stage_still" in text
    assert "Lorelai" in text


def test_event2_gold_reference_present():
    gold = (
        TOOLS.parent
        / ".claude"
        / "skills"
        / "beat-extract-planner"
        / "EVENT2_INTRO_GOLD.md"
    )
    assert gold.is_file()
    body = gold.read_text(encoding="utf-8")
    assert "Lemur Peace Prize" in body
    assert "Chipper" not in body or "Never Luna, Chipper" in body
