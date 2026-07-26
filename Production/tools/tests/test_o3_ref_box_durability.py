"""O3 Generate must use operator ref box paths, not stale sidecar, on every event."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from o3_generation_intent import (
    build_generation_intent,
    load_intent_visual_ref_fields_from_env,
    load_intent_visual_ref_fields_from_job_log,
    resolve_o3_submit_ref,
    resolve_o3_submit_refs,
    sidecar_fields_from_intent,
    sidecar_visual_ref_fields_from_intent,
)


def _minimal_sidecar(beat: dict) -> dict:
    return {
        "schema_version": 1,
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_2_pre": {
                        "beats": [beat],
                    },
                },
            },
        },
    }


def _voice_ready_beat(tmp_path: Path, beat_id: str, speaker: str = "Lorelai") -> dict:
    char = tmp_path / f"{beat_id}_char.png"
    sidecar_bg = tmp_path / f"{beat_id}_sidecar_bg.png"
    char.write_bytes(b"char-bytes-hands-face")
    sidecar_bg.write_bytes(b"sidecar-bg")
    return {
        "beat_id": beat_id,
        "speaker": speaker,
        "beat_plan_source": "operator_insert_v1",
        "kling_o3_generation": 3,
        "reference_image_locked": True,
        "reference_image": {"abs_path": str(char)},
        "bg_ref_image": {"abs_path": str(sidecar_bg)},
        "kling_o3_prompt": f'{speaker} speaks: "Hello"',
    }


@patch("tools.kling_character_registry.is_speaker_voice_ready", return_value=True)
@patch("tools.kling_character_registry.char_ref_matches_element_images", return_value=(True, ""))
@patch("beat_generator.resolve_o3_element_list_entry")
@patch("beat_generator.validate_proven_o3_element_submit", return_value=None)
@patch("tools.kling_voice_bind.detect_voice_bind_drift", return_value=None)
@patch("tools.kling_o3_prompt.validate_element_list_alignment", return_value=[])
def test_ref_box_wins_char_and_bg_over_sidecar(
    _align, _drift, _proven, mock_element, _ready, _char_ok, tmp_path: Path,
):
    mock_element.return_value = {
        "element_id": "313441038164306",
        "element_name": "Lorelai",
        "voice_id": "895210468825628751",
    }
    beat_id = "bg_arc1_event2_pre_beat_14"
    beat = _voice_ready_beat(tmp_path, beat_id)
    ref_box_char = tmp_path / "ref_box_char.png"
    ref_box_bg = tmp_path / "ref_box_bg.png"
    ref_box_char.write_bytes(b"ref-char")
    ref_box_bg.write_bytes(b"ref-bg")
    body = {
        "kling_o3_prompt": beat["kling_o3_prompt"],
        "reference_image": {"abs_path": str(ref_box_char)},
        "bg_ref_image": {"abs_path": str(ref_box_bg)},
    }
    event_dir = tmp_path / "Event_2"
    event_dir.mkdir()
    intent = build_generation_intent(
        beat=beat,
        sidecar=_minimal_sidecar(beat),
        body=body,
        beat_id=beat_id,
        event_dir=event_dir,
        job_id="refbox01",
        attempt_id="a-ref-box",
        log_path=event_dir / "j.log",
        pipeline_script=tmp_path / "p.py",
        wavespeed_key="k",
    )
    assert intent["visual"]["char_ref_abs_path"] == str(ref_box_char.resolve())
    assert intent["visual"]["bg_ref_abs_path"] == str(ref_box_bg.resolve())


def test_sidecar_fallback_when_body_omits_ref_fields(tmp_path: Path):
    beat_id = "bg_arc1_event2_pre_beat_10"
    beat = _voice_ready_beat(tmp_path, beat_id)
    char_ref, bg_ref = resolve_o3_submit_refs({"kling_o3_prompt": "x"}, beat)
    assert char_ref is not None
    assert bg_ref is not None
    assert char_ref["abs_path"] == beat["reference_image"]["abs_path"]
    assert bg_ref["abs_path"] == beat["bg_ref_image"]["abs_path"]


def test_resolve_o3_submit_ref_char_box_wins(tmp_path: Path):
    sidecar_char = tmp_path / "sidecar_char.png"
    box_char = tmp_path / "box_char.png"
    sidecar_char.write_bytes(b"a")
    box_char.write_bytes(b"b")
    beat = {"reference_image": {"abs_path": str(sidecar_char)}}
    body = {"reference_image": {"abs_path": str(box_char)}}
    resolved = resolve_o3_submit_ref("reference_image", body=body, beat=beat)
    assert resolved is not None
    assert resolved["abs_path"] == str(box_char)


@pytest.mark.parametrize(
    ("beat_id", "event_name"),
    [
        ("bg_arc1_event1_pre_beat_03", "Event_1"),
        ("bg_arc1_event2_pre_beat_14", "Event_2"),
        ("bg_arc1_event3_pre_beat_01", "Event_3"),
    ],
)
@patch("tools.kling_character_registry.is_speaker_voice_ready", return_value=True)
@patch("tools.kling_character_registry.char_ref_matches_element_images", return_value=(True, ""))
@patch("beat_generator.resolve_o3_element_list_entry")
@patch("beat_generator.validate_proven_o3_element_submit", return_value=None)
@patch("tools.kling_voice_bind.detect_voice_bind_drift", return_value=None)
@patch("tools.kling_o3_prompt.validate_element_list_alignment", return_value=[])
def test_ref_box_commit_on_all_event_beat_ids(
    _align,
    _drift,
    _proven,
    mock_element,
    _ready,
    _char_ok,
    tmp_path: Path,
    beat_id: str,
    event_name: str,
):
    mock_element.return_value = {
        "element_id": "1",
        "element_name": "Lorelai",
        "voice_id": "895210468825628751",
    }
    beat = _voice_ready_beat(tmp_path, beat_id)
    ref_bg = tmp_path / f"{event_name}_ref_box_bg.png"
    ref_bg.write_bytes(b"operator-bg")
    body = {
        "kling_o3_prompt": beat["kling_o3_prompt"],
        "reference_image": beat["reference_image"],
        "bg_ref_image": {"abs_path": str(ref_bg)},
    }
    event_dir = tmp_path / event_name
    event_dir.mkdir()
    intent = build_generation_intent(
        beat=beat,
        sidecar=_minimal_sidecar(beat),
        body=body,
        beat_id=beat_id,
        event_dir=event_dir,
        job_id="evref01",
        attempt_id="a-ev",
        log_path=event_dir / "j.log",
        pipeline_script=tmp_path / "p.py",
        wavespeed_key="k",
    )
    assert intent["event_id"] == event_name
    assert intent["visual"]["bg_ref_abs_path"] == str(ref_bg.resolve())


def test_submit_handler_wires_ref_box_resolver():
    src = Path(__file__).resolve().parents[1] / "server_handlers" / "background.py"
    text = src.read_text(encoding="utf-8")
    block = text.split("def handle_bg_submit_arlo_o3_voice", 1)[1].split("\ndef ", 1)[0]
    assert "build_generation_intent" in block
    assert "Ref snapshot durability" in block or "visible refs on submit" in block


def test_pipeline_logs_bg_ref_on_intent_submit():
    src = Path(__file__).resolve().parents[1] / "kling_o3_element_beat_pipeline.py"
    text = src.read_text(encoding="utf-8")
    block = text.split("def run_pipeline_from_intent", 1)[1].split("\ndef ", 1)[0]
    assert '"bg_ref"' in block
    assert "visual.get(\"bg_ref_abs_path\")" in block or "bg_path" in block


@patch("tools.kling_character_registry.is_speaker_voice_ready", return_value=True)
@patch("tools.kling_character_registry.char_ref_matches_element_images", return_value=(True, ""))
@patch("beat_generator.resolve_o3_element_list_entry")
@patch("beat_generator.validate_proven_o3_element_submit", return_value=None)
@patch("tools.kling_voice_bind.detect_voice_bind_drift", return_value=None)
@patch("tools.kling_o3_prompt.validate_element_list_alignment", return_value=[])
def test_intent_commit_locks_bg_ref_from_ref_box(
    _align, _drift, _proven, mock_element, _ready, _char_ok, tmp_path: Path,
):
    mock_element.return_value = {
        "element_id": "313441038164306",
        "element_name": "Lorelai",
        "voice_id": "895210468825628751",
    }
    beat_id = "bg_arc1_event2_pre_beat_02"
    beat = _voice_ready_beat(tmp_path, beat_id)
    ref_box_bg = tmp_path / "ref_box_bg.png"
    ref_box_bg.write_bytes(b"operator-bg")
    body = {
        "kling_o3_prompt": beat["kling_o3_prompt"],
        "reference_image": beat["reference_image"],
        "bg_ref_image": {"abs_path": str(ref_box_bg)},
    }
    event_dir = tmp_path / "Event_2"
    event_dir.mkdir()
    intent = build_generation_intent(
        beat=beat,
        sidecar=_minimal_sidecar(beat),
        body=body,
        beat_id=beat_id,
        event_dir=event_dir,
        job_id="bglock01",
        attempt_id="a-bg-lock",
        log_path=event_dir / "j.log",
        pipeline_script=tmp_path / "p.py",
        wavespeed_key="k",
    )
    assert intent["visual"]["bg_ref_image_locked"] is True
    sidecar_fields = sidecar_fields_from_intent(intent)
    assert sidecar_fields["bg_ref_image"]["abs_path"] == str(ref_box_bg.resolve())
    assert sidecar_fields["bg_ref_image_locked"] is True


@patch("tools.kling_character_registry.is_speaker_voice_ready", return_value=True)
@patch("tools.kling_character_registry.char_ref_matches_element_images", return_value=(True, ""))
@patch("beat_generator.resolve_o3_element_list_entry")
@patch("beat_generator.validate_proven_o3_element_submit", return_value=None)
@patch("tools.kling_voice_bind.detect_voice_bind_drift", return_value=None)
@patch("tools.kling_o3_prompt.validate_element_list_alignment", return_value=[])
def test_intent_commit_locks_char_ref_from_ref_box(
    _align, _drift, _proven, mock_element, _ready, _char_ok, tmp_path: Path,
):
    mock_element.return_value = {
        "element_id": "313441038164306",
        "element_name": "Lorelai",
        "voice_id": "895210468825628751",
    }
    beat_id = "bg_arc1_event2_pre_beat_03"
    beat = _voice_ready_beat(tmp_path, beat_id)
    ref_box_char = tmp_path / "ref_box_char.png"
    ref_box_char.write_bytes(b"operator-char")
    body = {
        "kling_o3_prompt": beat["kling_o3_prompt"],
        "reference_image": {"abs_path": str(ref_box_char)},
        "bg_ref_image": beat["bg_ref_image"],
    }
    event_dir = tmp_path / "Event_2"
    event_dir.mkdir()
    intent = build_generation_intent(
        beat=beat,
        sidecar=_minimal_sidecar(beat),
        body=body,
        beat_id=beat_id,
        event_dir=event_dir,
        job_id="charlock01",
        attempt_id="a-char-lock",
        log_path=event_dir / "j.log",
        pipeline_script=tmp_path / "p.py",
        wavespeed_key="k",
    )
    assert intent["visual"]["reference_image_locked"] is True
    sidecar_fields = sidecar_fields_from_intent(intent)
    assert sidecar_fields["reference_image"]["abs_path"] == str(ref_box_char.resolve())
    assert sidecar_fields["reference_image_locked"] is True


@patch("tools.kling_character_registry.is_speaker_voice_ready", return_value=True)
@patch("tools.kling_character_registry.char_ref_matches_element_images", return_value=(True, ""))
@patch("beat_generator.resolve_o3_element_list_entry")
@patch("beat_generator.validate_proven_o3_element_submit", return_value=None)
@patch("tools.kling_voice_bind.detect_voice_bind_drift", return_value=None)
@patch("tools.kling_o3_prompt.validate_element_list_alignment", return_value=[])
def test_event2_beat_03_golden_char_ref_box_wins_stale_sidecar(
    _align, _drift, _proven, mock_element, _ready, _char_ok, tmp_path: Path,
):
    """Golden from 0dfbc46f — sidecar Jun 14 char; operator ref box must win at commit."""
    mock_element.return_value = {
        "element_id": "313441038164306",
        "element_name": "Lorelai",
        "voice_id": "895210468825628751",
    }
    beat_id = "bg_arc1_event2_pre_beat_03"
    stale_char = tmp_path / "ChatGPT Image Jun 14, 2026, 03_33_59 AM.png"
    operator_char = tmp_path / "ChatGPT Image Jun 16, 2026, 04_53_13 PM.png"
    bg_img = tmp_path / "ChatGPT Image Jun 17, 2026, 11_26_11 AM.png"
    stale_char.write_bytes(b"stale-jun14")
    operator_char.write_bytes(b"operator-jun16")
    bg_img.write_bytes(b"bg-jun17")
    beat = {
        "beat_id": beat_id,
        "speaker": "Lorelai",
        "beat_plan_source": "claude_extract_v1",
        "kling_o3_generation": 8,
        "reference_image_locked": True,
        "reference_image": {"abs_path": str(stale_char)},
        "bg_ref_image": {"abs_path": str(bg_img)},
        "bg_ref_image_locked": True,
        "kling_o3_prompt": "Lorelai speaks: \"Hello\"",
    }
    body = {
        "kling_o3_prompt": beat["kling_o3_prompt"],
        "reference_image": {"abs_path": str(operator_char)},
        "bg_ref_image": beat["bg_ref_image"],
    }
    event_dir = tmp_path / "Event_2"
    event_dir.mkdir()
    intent = build_generation_intent(
        beat=beat,
        sidecar=_minimal_sidecar(beat),
        body=body,
        beat_id=beat_id,
        event_dir=event_dir,
        job_id="0dfbc46f",
        attempt_id="a-b03-golden",
        log_path=event_dir / "arlo_o3_jobs" / "0dfbc46f_bg_arc1_event2_pre_beat_03.log",
        pipeline_script=tmp_path / "p.py",
        wavespeed_key="k",
    )
    assert intent["visual"]["char_ref_abs_path"] == str(operator_char.resolve())
    assert intent["visual"]["bg_ref_abs_path"] == str(bg_img.resolve())
    assert intent["visual"]["reference_image_locked"] is True


def test_finalize_reasserts_intent_visual_refs():
    intent = {
        "visual": {
            "char_ref_abs_path": "/tmp/char.png",
            "bg_ref_abs_path": "/tmp/bg.png",
            "reference_image_locked": True,
            "bg_ref_image_locked": True,
        },
    }
    fields = sidecar_visual_ref_fields_from_intent(intent)
    assert fields["reference_image"]["abs_path"] == "/tmp/char.png"
    assert fields["bg_ref_image"]["abs_path"] == "/tmp/bg.png"
    assert fields["reference_image_locked"] is True
    assert fields["bg_ref_image_locked"] is True


def test_load_intent_visual_ref_fields_from_env_reads_mn_o3_intent_path(
    tmp_path: Path, monkeypatch,
):
    intent_path = tmp_path / "intent.json"
    char = tmp_path / "char.png"
    bg = tmp_path / "bg.png"
    char.write_bytes(b"c")
    bg.write_bytes(b"b")
    intent_path.write_text(
        json.dumps({
            "schema_version": 1,
            "job_id": "envtest01",
            "visual": {
                "char_ref_abs_path": str(char),
                "bg_ref_abs_path": str(bg),
                "reference_image_locked": True,
                "bg_ref_image_locked": True,
            },
        }),
        encoding="utf-8",
    )
    monkeypatch.setenv("MN_O3_INTENT_PATH", str(intent_path))
    fields = load_intent_visual_ref_fields_from_env()
    assert fields["bg_ref_image"]["abs_path"] == str(bg)
    assert fields["bg_ref_image_locked"] is True


def test_both_pipelines_reassert_intent_refs_on_finalize():
    element_src = Path(__file__).resolve().parents[1] / "kling_o3_element_beat_pipeline.py"
    voice_src = Path(__file__).resolve().parents[1] / "arlo_o3_voice_pipeline.py"
    element_text = element_src.read_text(encoding="utf-8")
    voice_text = voice_src.read_text(encoding="utf-8")
    assert "sidecar_visual_ref_fields_from_intent(intent)" in element_text
    assert "load_intent_visual_ref_fields_from_env()" in element_text
    assert "load_intent_visual_ref_fields_from_env()" in voice_text


def test_orphan_recovery_reasserts_intent_visual_refs():
    bg_src = Path(__file__).resolve().parents[1] / "beat_generator.py"
    text = bg_src.read_text(encoding="utf-8")
    block = text.split("def recover_orphan_o3_delivery", 1)[1].split("\ndef ", 1)[0]
    assert "load_intent_visual_ref_fields_from_job_log" in block


def test_refresh_state_preserves_locked_ref_boxes_on_session_merge():
    """Ref-box merge authority is bgSessionBeatMerge → promptEditRegistry, not BgTab text."""
    merge = (
        Path(__file__).resolve().parents[1]
        / "storyboard-v2"
        / "src"
        / "utils"
        / "bgSessionBeatMerge.ts"
    ).read_text(encoding="utf-8")
    registry = (
        Path(__file__).resolve().parents[1]
        / "storyboard-v2"
        / "src"
        / "state"
        / "promptEditRegistry.ts"
    ).read_text(encoding="utf-8")
    store = (
        Path(__file__).resolve().parents[1]
        / "storyboard-v2"
        / "src"
        / "state"
        / "bgSessionStore.ts"
    ).read_text(encoding="utf-8")
    assert "preserveRefBoxesOnServerBeatMerge" in merge
    assert "export function preserveRefBoxesOnServerBeatMerge" in registry
    assert "mergeBeatsOnSessionHydrate" in store


def test_optimistic_ref_drop_sets_local_lock_flag():
    bg_tab = Path(__file__).resolve().parents[1] / "storyboard-v2" / "src" / "components" / "BgTab.tsx"
    text = bg_tab.read_text(encoding="utf-8")
    block = text.split("const onPatchRefImageForBeat = (", 1)[1].split("};", 1)[0]
    assert "reference_image_locked" in block
    assert "bg_ref_image_locked" in block


def test_load_intent_visual_ref_fields_from_job_log(tmp_path: Path):
    event_dir = tmp_path / "Event_2"
    jobs = event_dir / "arlo_o3_jobs"
    jobs.mkdir(parents=True)
    char = tmp_path / "char.png"
    bg = tmp_path / "bg.png"
    char.write_bytes(b"c")
    bg.write_bytes(b"b")
    (jobs / "abc12345_intent.json").write_text(
        json.dumps({
            "schema_version": 1,
            "job_id": "abc12345",
            "visual": {
                "char_ref_abs_path": str(char),
                "bg_ref_abs_path": str(bg),
                "reference_image_locked": True,
                "bg_ref_image_locked": True,
            },
        }),
        encoding="utf-8",
    )
    fields = load_intent_visual_ref_fields_from_job_log(
        jobs / "abc12345_bg_arc1_event2_pre_beat_03.log",
        event_dir,
    )
    assert fields["reference_image"]["abs_path"] == str(char)
    assert fields["bg_ref_image"]["abs_path"] == str(bg)
