"""Beat plan draft autosave + approve durability (Kim 2026-06-16)."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

TOOLS = Path(__file__).resolve().parent.parent
REPO = TOOLS.parent.parent
for p in (TOOLS, TOOLS.parent, REPO):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

import beat_generator as bg  # noqa: E402
from beat_extract_policy import (  # noqa: E402
    postprocess_kling_author_row,
    scene_notes_reflected_in_kling_prompt,
    substantive_staging_probe,
)


EVENT4_SIDEcar = Path.home() / (
    "Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/"
    "beat_generator_state.json"
)


@pytest.fixture
def event4_plan_rows():
    if not EVENT4_SIDEcar.is_file():
        pytest.skip("Event 4 sidecar fixture unavailable")
    data = json.loads(EVENT4_SIDEcar.read_text(encoding="utf-8"))
    rows = (
        data.get("arcs", {})
        .get("arc_1", {})
        .get("segments", {})
        .get("event_4_pre", {})
        .get("beat_plan_draft", {})
        .get("beats_plan")
        or []
    )
    if not rows:
        pytest.skip("event_4_pre beat_plan_draft missing")
    return rows


def test_persist_beat_plan_draft_preserves_extract_metadata():
    sidecar: dict = {"arcs": {}}
    bg.persist_beat_plan_draft(
        sidecar, 1, "4", "pre", "summary", [{
            "beat_index": 1,
            "beat_type": "dialogue",
            "speaker": "Bramble",
            "dialogue_text": "Hello",
            "emotion": "warm",
            "scene_notes": "waves hello",
        }],
        source="extract_plan",
        extra={"model_used": "claude-test", "section_meta": {"slice_method": "regex_setup"}},
    )
    seg = bg.get_seg_entry(sidecar, 1, "4", "pre")
    draft = seg.get("beat_plan_draft") or {}
    assert draft.get("source") == "extract_plan"
    assert draft.get("model_used") == "claude-test"
    assert len(draft.get("beats_plan") or []) == 1
    assert draft.get("created_at")
    assert draft.get("updated_at")


def test_persist_beat_plan_draft_modal_autosave_keeps_prior_created_at():
    sidecar: dict = {"arcs": {}}
    bg.persist_beat_plan_draft(
        sidecar, 1, "4", "pre", "v1", [{
            "beat_index": 1,
            "speaker": "Bramble",
            "dialogue_text": "A",
            "emotion": "warm",
            "scene_notes": "",
        }],
        source="extract_plan",
        extra={"created_at": "2026-06-16T00:00:00+00:00"},
    )
    bg.persist_beat_plan_draft(
        sidecar, 1, "4", "pre", "v2", [{
            "beat_index": 1,
            "speaker": "Bramble",
            "dialogue_text": "B",
            "emotion": "warm",
            "scene_notes": "waves",
        }],
        source="modal_autosave",
    )
    draft = bg.get_seg_entry(sidecar, 1, "4", "pre").get("beat_plan_draft") or {}
    assert draft.get("story_summary") == "v2"
    assert draft["beats_plan"][0]["dialogue_text"] == "B"
    assert draft.get("created_at") == "2026-06-16T00:00:00+00:00"
    assert draft.get("source") == "modal_autosave"


def test_scene_notes_reflected_handles_image_header_mismatch():
    scene = (
        "@Image1 (Tessa). Scene from @Image2. Tessa stands near the MindfulNest, "
        "turning slightly toward it."
    )
    prompt = (
        "@Image1 (Tessa) Tessa — arc 1 event 4 pre. Scene from @Image2.\n\n"
        "Camera: static locked shot.\n\n"
        "Tessa stands near the MindfulNest, turning slightly toward it.\n\n"
        'Voice line: Tessa speaks: "Hello"'
    )
    assert scene_notes_reflected_in_kling_prompt(prompt, scene, speaker="Tessa")
    assert substantive_staging_probe(scene).startswith("tessa stands near")


def test_event4_golden_plan_audit_passes_after_resync(event4_plan_rows, monkeypatch):
    monkeypatch.setattr(bg, "append_intro_canonical_tail_beats", lambda *a, **k: None)
    prompts: dict[int, str] = {}
    for row in event4_plan_rows:
        idx = int(row["beat_index"])
        sp = row.get("speaker") or "Character"
        if row.get("beat_type") == "stage_still":
            from beat_extract_policy import build_still_insert_prompt

            prompts[idx] = build_still_insert_prompt(row)
            continue
        fake = (
            f"@Image1 ({sp}) {sp} — arc 1 event 4 pre. Scene from @Image2.\n\n"
            "Camera: static locked shot.\n\n"
            f'Voice line: {sp} speaks: "{(row.get("dialogue_text") or "")[:40]}"\n\n'
            "Children's illustrated fantasy storybook style."
        )
        merged = postprocess_kling_author_row(row, fake)
        prompts[idx] = merged["kling_o3_prompt"]

    sidecar: dict = {"arcs": {}}
    beats = bg.apply_approved_extract_plan(
        sidecar, 1, "4", "pre", "summary", event4_plan_rows, prompts,
    )
    bg.resync_kling_author_prompts_pre_audit(beats)
    audit = bg.audit_kling_author_enrichment(beats)
    assert audit == [], audit


def test_draft_save_and_approve_wiring():
    bg_py = (TOOLS / "server_handlers" / "background.py").read_text(encoding="utf-8")
    assert "handle_bg_extract_beats_draft_save" in bg_py
    assert "modal_pre_approve" in bg_py
    assert "resync_kling_author_prompts_pre_audit" in bg_py
    server = (TOOLS / "production_server.py").read_text(encoding="utf-8")
    assert "/api/bg/extract-beats/draft/save" in server
    endpoints = (TOOLS / "storyboard-v2" / "src" / "api" / "endpoints.ts").read_text(encoding="utf-8")
    assert "bg_extract_beats_draft_save" in endpoints
    bgtab = (TOOLS / "storyboard-v2" / "src" / "components" / "BgTab.tsx").read_text(encoding="utf-8")
    assert "extract-overwrite-confirm" in bgtab
    assert "onBeatPlanAutosave" in bgtab
    modal = (TOOLS / "storyboard-v2" / "src" / "components" / "BeatPlanModal.tsx").read_text(encoding="utf-8")
    assert "onAutosave" in modal
    assert "auto-save" in modal.lower()
