"""Form-first insert beat — unified extract materialization (INSERT_BEAT_FORM_FIRST_SPEC_v1)."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

import beat_generator as bg  # noqa: E402
from kling_o3_prompt import validate_element_list_alignment  # noqa: E402
from tools import kling_character_registry as reg  # noqa: E402

BACKGROUND = TOOLS / "server_handlers" / "background.py"


def _handler_block(name: str) -> str:
    text = BACKGROUND.read_text(encoding="utf-8")
    start = text.index(f"def {name}(")
    end = text.index("\ndef ", start + 1)
    return text[start:end]


def _minimal_sidecar_with_proven_source(tmp_path: Path) -> dict:
    char_ref = tmp_path / "lorelai_ref.png"
    char_ref.write_bytes(b"ref")
    bg_ref = tmp_path / "bg.png"
    bg_ref.write_bytes(b"bg")
    source_beat = {
        "beat_id": "bg_arc1_event2_pre_beat_18",
        "speaker": "Lorelai",
        "dialogue_text": "proven line",
        "reference_image": {"abs_path": str(char_ref), "key": "ref"},
        "bg_ref_image": {"abs_path": str(bg_ref), "key": "bg"},
        "reference_image_locked": True,
    }
    return {
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_2_pre": {
                        "name": "Event 2 pre",
                        "beats": [source_beat],
                    },
                },
            },
        },
    }


def _parity_fields(beat: dict) -> dict:
    keys = (
        "pipeline",
        "speaker",
        "emotion",
        "beat_type",
        "kling_o3_status",
        "beat_plan_source",
    )
    out = {k: beat.get(k) for k in keys}
    out["has_prompt"] = bool(str(beat.get("kling_o3_prompt") or "").strip())
    out["has_char_ref"] = bool(beat.get("reference_image"))
    out["has_bg_ref"] = bool(beat.get("bg_ref_image"))
    out["no_pin"] = "o3_voice_stack_pin" not in beat
    out["no_box_law"] = "o3_prompt_box_law" not in beat
    out["prompt_not_character_shell"] = "Character" not in str(
        beat.get("kling_o3_prompt") or ""
    )[:80]
    return out


def test_handle_bg_insert_beat_uses_mutate_sidecar_locked():
    block = _handler_block("handle_bg_insert_beat")
    assert "mutate_sidecar_locked(_insert" in block
    assert "sidecar_file_lock" not in block
    assert "materialize_sidecar_beat_from_plan_row" in block
    assert "create_blank_bg_beat" not in block


def test_handle_bg_add_beat_returns_410():
    block = _handler_block("handle_bg_add_beat")
    assert "INSERT_BEAT_FORM_REQUIRED" in block
    assert "410" in block
    assert "create_blank_bg_beat" not in block


def test_create_blank_bg_beat_raises():
    with pytest.raises(RuntimeError, match="insert-beat"):
        bg.create_blank_bg_beat("bg_arc1_event2_pre_beat_99", "2", "pre")


def test_materialize_lorelai_matches_extract_shape(tmp_path, monkeypatch):
    sidecar = _minimal_sidecar_with_proven_source(tmp_path)
    monkeypatch.setattr(
        "tools.kling_character_registry.resolve_proven_o3_bind",
        lambda _entry: {"proven_from_beat_id": "bg_arc1_event2_pre_beat_18"},
    )
    plan_row = {
        "speaker": "Lorelai",
        "dialogue_text": "Test dialogue for parity.",
        "emotion": "neutral",
        "scene_notes": "close-up head and torso",
        "beat_type": "dialogue",
    }
    insert_beat = bg.materialize_sidecar_beat_from_plan_row(
        plan_row,
        beat_id="bg_arc1_event2_pre_beat_28",
        arc_number=1,
        event_id="2",
        phase="pre",
        sidecar=sidecar,
    )
    extract_beat = bg.build_beats_from_approved_plan(
        [plan_row],
        {},
        arc_number=1,
        event_id="2",
        phase="pre",
    )[0]
    bg.finalize_proven_element_beat(
        extract_beat, sidecar, "Lorelai", event_id="2", phase="pre",
    )
    extract_beat["beat_id"] = "bg_arc1_event2_pre_beat_99"
    extract_beat["beat_plan_source"] = "claude_extract_v1"

    insert_fields = _parity_fields(insert_beat)
    extract_fields = _parity_fields(extract_beat)
    assert insert_fields["pipeline"] == extract_fields["pipeline"] == "kling_o3_omni"
    assert insert_fields["speaker"] == extract_fields["speaker"] == "Lorelai"
    assert insert_fields["no_pin"] is True
    assert insert_fields["no_box_law"] is True
    assert insert_fields["prompt_not_character_shell"] is True
    assert insert_beat["beat_plan_source"] == "operator_insert_v1"
    assert insert_beat.get("reference_image_locked") is True
    src_path = sidecar["arcs"]["arc_1"]["segments"]["event_2_pre"]["beats"][0][
        "reference_image"
    ]["abs_path"]
    assert insert_beat["reference_image"]["abs_path"] == src_path
    assert "element_char_ref_ok" in insert_beat


def test_finalize_proven_element_always_syncs_gate(tmp_path, monkeypatch):
    sidecar = _minimal_sidecar_with_proven_source(tmp_path)
    beat = {"beat_id": "bg_arc1_event2_pre_beat_99", "speaker": "Lorelai"}
    monkeypatch.setattr(
        "tools.kling_character_registry.resolve_proven_o3_bind",
        lambda _entry: {"proven_from_beat_id": "bg_arc1_event2_pre_beat_18"},
    )
    monkeypatch.setattr(bg, "sync_element_char_ref_status", lambda b, **kw: b.update(
        {"element_char_ref_ok": True},
    ) or True)
    bg.finalize_proven_element_beat(
        beat, sidecar, "Lorelai", event_id="2", phase="pre",
    )
    assert beat.get("element_char_ref_ok") is True


def test_handle_bg_insert_beat_auto_registers_char_ref():
    block = _handler_block("handle_bg_insert_beat")
    assert "maybe_auto_register_beat_char_ref" in block
    assert "element_char_ref_ok" in block


def test_finalize_proven_element_sync_not_else_only():
    text = (TOOLS / "beat_generator.py").read_text(encoding="utf-8")
    start = text.index("def finalize_proven_element_beat(")
    end = text.index("\n\n\ndef ", start)
    block = text[start:end]
    assert "sync_element_char_ref_status(beat, heal_mismatch=False)" in block
    assert re.search(
        r"if changed:\s*\n\s*apply_kling_o3_defaults_to_beat",
        block,
    ), "finalize must rebuild prompt when proven refs change"
    assert not re.search(
        r"else:\s*\n\s*sync_element_char_ref_status",
        block,
    ), "gate sync must run after ref copy, not only when refs unchanged"


def test_maybe_auto_register_helper_exists():
    assert hasattr(bg, "maybe_auto_register_beat_char_ref")
    src = (TOOLS / "beat_generator.py").read_text(encoding="utf-8")
    assert "try_register_dropped_char_ref_on_element" in src.split(
        "def maybe_auto_register_beat_char_ref", 1,
    )[1].split("\n\n", 1)[0]


def test_proven_element_list_uses_loral():
    entry = reg.get_proven_element_list_entry("Lorelai")
    assert entry is not None
    assert entry["element_name"] == "Loral"
    assert entry["element_id"] == "314723690963308"
    assert entry["voice_id"] == "900616393057116185"


def test_validate_alignment_no_pin_bypass():
    """Legacy pin on beat must not skip element_list alignment checks."""
    beat = {
        "o3_voice_stack_pin": {
            "element_id": "313390553209506",
            "element_name": "Wrong",
            "kling_voice_id": "895024801360777292",
        },
    }
    bad_entry = {
        "element_id": "313441038164306",
        "element_name": "WrongName",
        "voice_id": "895210468825628751",
    }
    prompt = '@Image1 (Loral). Loral speaks in a warm calm conversational pace: "Hi"'
    errs = validate_element_list_alignment("Lorelai", bad_entry, prompt, beat=beat)
    assert any("element_name must be 'Loral'" in e for e in errs)


def test_resolve_o3_element_list_prefers_proven_over_pin():
    beat = {
        "speaker": "Lorelai",
        "o3_voice_stack_pin": {
            "element_id": "313390553209506",
            "element_name": "Lorelai",
            "kling_voice_id": "895024801360777292",
        },
    }
    entry = bg.resolve_o3_element_list_entry(beat, "Lorelai")
    assert entry["element_name"] == "Loral"
    assert entry["element_id"] == "314723690963308"


def test_operator_insert_char_ref_parity_respects_locked_library_drop(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(bg, "_PROD_DIR", str(tmp_path))
    extract_pose = tmp_path / "Lorelai" / "poses" / "lorelai_canonical_neutral.png"
    library_pose = tmp_path / "Event_2" / "library" / "chatgpt_still.png"
    extract_pose.parent.mkdir(parents=True)
    library_pose.parent.mkdir(parents=True)
    extract_pose.write_bytes(b"canonical")
    library_pose.write_bytes(b"library")
    sidecar = {
        "arcs": {
            "1": {
                "segments": {
                    "event_2_pre": {
                        "beats": [
                            {
                                "beat_id": "bg_arc1_event2_pre_beat_03",
                                "speaker": "Lorelai",
                                "beat_plan_source": "claude_extract_v1",
                                "reference_image": {
                                    "abs_path": str(extract_pose.resolve()),
                                },
                            },
                            {
                                "beat_id": "bg_arc1_event2_pre_beat_30",
                                "speaker": "Lorelai",
                                "beat_plan_source": "operator_insert_v1",
                                "reference_image": {
                                    "abs_path": str(library_pose.resolve()),
                                },
                                "reference_image_locked": True,
                                "o3_prompt_box_law": True,
                            },
                        ],
                    },
                },
            },
        },
    }
    _, insert = bg.find_beat(sidecar, "bg_arc1_event2_pre_beat_30")
    changed = bg.ensure_operator_insert_char_ref_parity(
        insert, sidecar, "Lorelai", event_id="2", phase="pre",
    )
    assert changed is False
    assert bg.resolve_beat_char_ref_path(insert) == str(library_pose.resolve())
    assert insert.get("o3_prompt_box_law") is True


def test_operator_insert_char_ref_parity_copies_extract_pose_when_unlocked(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(bg, "_PROD_DIR", str(tmp_path))
    extract_pose = tmp_path / "Lorelai" / "poses" / "lorelai_canonical_neutral.png"
    library_pose = tmp_path / "Event_2" / "library" / "chatgpt_still.png"
    extract_pose.parent.mkdir(parents=True)
    library_pose.parent.mkdir(parents=True)
    extract_pose.write_bytes(b"canonical")
    library_pose.write_bytes(b"library")
    sidecar = {
        "arcs": {
            "1": {
                "segments": {
                    "event_2_pre": {
                        "beats": [
                            {
                                "beat_id": "bg_arc1_event2_pre_beat_03",
                                "speaker": "Lorelai",
                                "beat_plan_source": "claude_extract_v1",
                                "reference_image": {
                                    "abs_path": str(extract_pose.resolve()),
                                    "thumb_b64": "data:image/jpeg;base64,stale",
                                },
                            },
                            {
                                "beat_id": "bg_arc1_event2_pre_beat_30",
                                "speaker": "Lorelai",
                                "beat_plan_source": "operator_insert_v1",
                                "reference_image": {
                                    "abs_path": str(library_pose.resolve()),
                                },
                                "reference_image_locked": False,
                            },
                        ],
                    },
                },
            },
        },
    }
    _, insert = bg.find_beat(sidecar, "bg_arc1_event2_pre_beat_30")
    changed = bg.ensure_operator_insert_char_ref_parity(
        insert, sidecar, "Lorelai", event_id="2", phase="pre",
    )
    assert changed is True
    assert bg.resolve_beat_char_ref_path(insert) == str(extract_pose.resolve())
    assert "thumb_b64" not in (insert.get("reference_image") or {})


def test_finalize_proven_element_respects_locked_char_ref_on_generate(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(bg, "_PROD_DIR", str(tmp_path))
    proven_pose = tmp_path / "Lorelai" / "poses" / "lorelai_canonical_neutral.png"
    user_pose = tmp_path / "Event_2" / "library" / "user_drop.png"
    proven_pose.parent.mkdir(parents=True)
    user_pose.parent.mkdir(parents=True)
    proven_pose.write_bytes(b"proven")
    user_pose.write_bytes(b"user")
    sidecar = {
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_2_pre": {
                        "beats": [{
                            "beat_id": "bg_arc1_event2_pre_beat_03",
                            "speaker": "Lorelai",
                            "reference_image": {"abs_path": str(proven_pose.resolve())},
                        }],
                    },
                },
            },
        },
    }
    beat = {
        "beat_id": "bg_arc1_event2_pre_beat_30",
        "speaker": "Lorelai",
        "beat_plan_source": "operator_insert_v1",
        "reference_image": {"abs_path": str(user_pose.resolve())},
        "reference_image_locked": True,
        "o3_prompt_box_law": True,
    }

    def fake_proven(_speaker):
        return {"proven_from_beat_id": "bg_arc1_event2_pre_beat_03"}

    monkeypatch.setattr(
        "tools.kling_character_registry.resolve_proven_o3_bind",
        fake_proven,
    )
    monkeypatch.setattr(
        "tools.kling_character_registry.get_character_entry",
        lambda _s: {},
    )
    changed = bg.finalize_proven_element_beat(
        beat, sidecar, "Lorelai", event_id="2", phase="pre",
    )
    bg.ensure_operator_insert_char_ref_parity(
        beat, sidecar, "Lorelai", event_id="2", phase="pre",
    )
    assert changed is False
    assert bg.resolve_beat_char_ref_path(beat) == str(user_pose.resolve())
    assert beat.get("o3_prompt_box_law") is True


def test_allocate_beat_id_gap_safe():
    beats = [
        {"beat_id": "bg_arc1_event2_pre_beat_03"},
        {"beat_id": "bg_arc1_event2_pre_beat_05"},
    ]
    from server_handlers.background import _allocate_bg_beat_id

    new_id = _allocate_bg_beat_id(
        beats, arc_number=1, event_id_int=2, phase="pre",
    )
    assert new_id == "bg_arc1_event2_pre_beat_06"


def test_bgtab_uses_insert_modal_wiring():
    text = (
        TOOLS / "storyboard-v2" / "src" / "components" / "BgTab.tsx"
    ).read_text(encoding="utf-8")
    assert "InsertBeatModal" in text
    assert "bg_insert_beat" in text
    assert "bg-add-empty-btn" not in text
    assert "bg-insert-btn" in text
    assert "Add empty beat" not in text


def test_production_server_routes_insert_beat():
    text = (TOOLS / "production_server.py").read_text(encoding="utf-8")
    assert '"/api/bg/insert-beat"' in text
    assert "_handle_bg_insert_beat" in text
