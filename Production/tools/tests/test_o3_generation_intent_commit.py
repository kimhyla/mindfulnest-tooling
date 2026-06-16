"""O3 generation intent snapshot — commit contract tests."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import beat_generator as bg
import pytest
from o3_generation_intent import (
    IntentCommitError,
    beat_has_active_intent,
    build_generation_intent,
    write_generation_intent,
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


def _voice_ready_lorelai_beat(tmp_path: Path) -> dict:
    char = tmp_path / "char.png"
    bg_img = tmp_path / "bg.png"
    char.write_bytes(b"char-bytes-hands-face")
    bg_img.write_bytes(b"bg-bytes")
    return {
        "beat_id": "bg_arc1_event2_pre_beat_30",
        "speaker": "Lorelai",
        "beat_plan_source": "operator_insert_v1",
        "kling_o3_generation": 6,
        "reference_image_locked": True,
        "reference_image": {"abs_path": str(char)},
        "bg_ref_image": {"abs_path": str(bg_img)},
        "kling_o3_prompt": "Loral (female raccoon) speaks with a warm female voice: \"Hello\"",
    }


@patch("tools.kling_character_registry.is_speaker_voice_ready", return_value=True)
@patch("tools.kling_character_registry.char_ref_matches_element_images", return_value=(True, ""))
@patch("beat_generator.resolve_o3_element_list_entry")
@patch("beat_generator.validate_proven_o3_element_submit", return_value=None)
@patch("tools.kling_voice_bind.detect_voice_bind_drift", return_value=None)
@patch("tools.kling_o3_prompt.validate_element_list_alignment", return_value=[])
def test_commit_writes_intent_json(
    _align, _drift, _proven, mock_element, _ready, _char_ok, tmp_path,
):
    mock_element.return_value = {
        "element_id": "313441038164306",
        "element_name": "Loral",
        "voice_id": "895210468825628751",
    }
    beat = _voice_ready_lorelai_beat(tmp_path)
    sidecar = _minimal_sidecar(beat)
    event_dir = tmp_path / "Event_2"
    event_dir.mkdir()
    body = {
        "kling_o3_prompt": beat["kling_o3_prompt"],
        "reference_image": beat["reference_image"],
        "bg_ref_image": beat["bg_ref_image"],
    }
    intent = build_generation_intent(
        beat=beat,
        sidecar=sidecar,
        body=body,
        beat_id=beat["beat_id"],
        event_dir=event_dir,
        job_id="abc12345",
        attempt_id="attempt-1",
        log_path=event_dir / "arlo_o3_jobs" / "abc12345_beat.log",
        pipeline_script=tmp_path / "pipeline.py",
        wavespeed_key="ws-key",
    )
    path = write_generation_intent(intent, event_dir)
    assert path.is_file()
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["schema_version"] == 1
    assert loaded["prompt"]["verbatim"] == body["kling_o3_prompt"]
    assert "(female raccoon)" in loaded["prompt"]["verbatim"]
    assert loaded["prompt"]["sha256"] == intent["prompt"]["sha256"]


@patch("tools.kling_character_registry.is_speaker_voice_ready", return_value=True)
@patch("tools.kling_character_registry.char_ref_matches_element_images", return_value=(True, ""))
@patch("beat_generator.resolve_o3_element_list_entry")
@patch("beat_generator.validate_proven_o3_element_submit", return_value=None)
@patch("tools.kling_voice_bind.detect_voice_bind_drift", return_value=None)
@patch("tools.kling_o3_prompt.validate_element_list_alignment", return_value=[])
def test_commit_prompt_verbatim_no_morph(
    _align, _drift, _proven, mock_element, _ready, _char_ok, tmp_path,
):
    mock_element.return_value = {
        "element_id": "1",
        "element_name": "Loral",
        "voice_id": "v1",
    }
    beat = _voice_ready_lorelai_beat(tmp_path)
    sidecar = _minimal_sidecar(beat)
    event_dir = tmp_path / "Event_2"
    event_dir.mkdir()
    prompt = "Loral (female raccoon) speaks: \"Hi\""
    body = {
        "kling_o3_prompt": prompt,
        "reference_image": beat["reference_image"],
        "bg_ref_image": beat["bg_ref_image"],
    }
    with patch("beat_generator.build_kling_o3_prompt") as morph:
        morph.side_effect = AssertionError("build_kling_o3_prompt must not run during intent commit")
        intent = build_generation_intent(
            beat=beat,
            sidecar=sidecar,
            body=body,
            beat_id=beat["beat_id"],
            event_dir=event_dir,
            job_id="job1",
            attempt_id="a1",
            log_path=event_dir / "j.log",
            pipeline_script=tmp_path / "p.py",
            wavespeed_key="k",
        )
    assert intent["prompt"]["verbatim"] == prompt
    assert intent["prompt"]["prepared_for_api"] == prompt


@patch("tools.kling_character_registry.is_speaker_voice_ready", return_value=True)
@patch("beat_generator.resolve_o3_element_list_entry")
@patch("beat_generator.validate_proven_o3_element_submit", return_value=None)
@patch("tools.kling_voice_bind.detect_voice_bind_drift", return_value=None)
@patch("tools.kling_o3_prompt.validate_element_list_alignment", return_value=[])
def test_commit_blocks_pose_dir_false_positive(
    _align, _drift, _proven, mock_element, _ready, tmp_path,
):
    mock_element.return_value = {"element_id": "1", "element_name": "Loral", "voice_id": "v1"}
    beat = _voice_ready_lorelai_beat(tmp_path)
    sidecar = _minimal_sidecar(beat)
    event_dir = tmp_path / "Event_2"
    event_dir.mkdir()
    body = {
        "kling_o3_prompt": beat["kling_o3_prompt"],
        "reference_image": beat["reference_image"],
        "bg_ref_image": beat["bg_ref_image"],
    }
    with patch(
        "tools.kling_character_registry.char_ref_matches_element_images",
        return_value=(False, "mismatch"),
    ), patch(
        "beat_generator.try_register_dropped_char_ref_on_element",
        return_value={"ok": False, "reason": "fail"},
    ):
        with pytest.raises(IntentCommitError) as exc:
            build_generation_intent(
                beat=beat,
                sidecar=sidecar,
                body=body,
                beat_id=beat["beat_id"],
                event_dir=event_dir,
                job_id="job2",
                attempt_id="a2",
                log_path=event_dir / "j.log",
                pipeline_script=tmp_path / "p.py",
                wavespeed_key="k",
            )
    assert exc.value.error_code == "ELEMENT_VISUAL_MISMATCH"


@patch("tools.kling_character_registry.is_speaker_voice_ready", return_value=True)
@patch("tools.kling_character_registry.char_ref_matches_element_images", return_value=(True, ""))
@patch("beat_generator.resolve_o3_element_list_entry")
@patch("beat_generator.validate_proven_o3_element_submit", return_value=None)
@patch("tools.kling_voice_bind.detect_voice_bind_drift", return_value=None)
@patch("tools.kling_o3_prompt.validate_element_list_alignment", return_value=[])
def test_commit_slot_max_sidecar_disk(
    _align, _drift, _proven, mock_element, _ready, _char_ok, tmp_path, monkeypatch,
):
    mock_element.return_value = {"element_id": "1", "element_name": "Loral", "voice_id": "v1"}
    beat = _voice_ready_lorelai_beat(tmp_path)
    beat["kling_o3_generation"] = 6
    sidecar = _minimal_sidecar(beat)
    event_dir = tmp_path / "Event_2"
    clips = event_dir / "kling_o3_clips"
    clips.mkdir(parents=True)
    g7 = clips / "bg_arc1_event2_pre_beat_30_g7_element_o3_master_delivery.mp4"
    g7.write_bytes(b"fake")
    monkeypatch.setattr(bg, "highest_o3_generation_on_disk", lambda _bid, _ed: 7)
    body = {
        "kling_o3_prompt": beat["kling_o3_prompt"],
        "reference_image": beat["reference_image"],
        "bg_ref_image": beat["bg_ref_image"],
    }
    intent = build_generation_intent(
        beat=beat,
        sidecar=sidecar,
        body=body,
        beat_id=beat["beat_id"],
        event_dir=event_dir,
        job_id="job3",
        attempt_id="a3",
        log_path=event_dir / "j.log",
        pipeline_script=tmp_path / "p.py",
        wavespeed_key="k",
    )
    assert intent["generation"]["slot"] == "g8"
    assert intent["generation"]["slot_index"] == 8


def test_commit_does_not_delete_existing_g7(tmp_path, monkeypatch):
    event_dir = tmp_path / "Event_2"
    clips = event_dir / "kling_o3_clips"
    clips.mkdir(parents=True)
    g7 = clips / "bg_arc1_event2_pre_beat_30_g7_element_o3_master_delivery.mp4"
    g7.write_bytes(b"keep-me")
    mtime_before = g7.stat().st_mtime
    beat = _voice_ready_lorelai_beat(tmp_path)
    beat["kling_o3_generation"] = 6
    with patch("tools.kling_character_registry.is_speaker_voice_ready", return_value=True), \
         patch("tools.kling_character_registry.char_ref_matches_element_images", return_value=(True, "")), \
         patch("beat_generator.resolve_o3_element_list_entry", return_value={"element_id": "1", "element_name": "L", "voice_id": "v"}), \
         patch("beat_generator.validate_proven_o3_element_submit", return_value=None), \
         patch("tools.kling_voice_bind.detect_voice_bind_drift", return_value=None), \
         patch("tools.kling_o3_prompt.validate_element_list_alignment", return_value=[]), \
         patch("beat_generator.highest_o3_generation_on_disk", return_value=7):
        intent = build_generation_intent(
            beat=beat,
            sidecar=_minimal_sidecar(beat),
            body={
                "kling_o3_prompt": beat["kling_o3_prompt"],
                "reference_image": beat["reference_image"],
                "bg_ref_image": beat["bg_ref_image"],
            },
            beat_id=beat["beat_id"],
            event_dir=event_dir,
            job_id="job4",
            attempt_id="a4",
            log_path=event_dir / "j.log",
            pipeline_script=tmp_path / "p.py",
            wavespeed_key="k",
        )
    assert g7.is_file()
    assert g7.stat().st_mtime == mtime_before
    assert intent["generation"]["slot_index"] == 8


def test_active_intent_detected_without_terminal(tmp_path):
    event_dir = tmp_path / "Event_2"
    jobs = event_dir / "arlo_o3_jobs"
    jobs.mkdir(parents=True)
    intent = {
        "schema_version": 1,
        "job_id": "deadbeef",
        "beat_id": "bg_arc1_event2_pre_beat_30",
        "committed_at": "2026-06-15T20:00:00Z",
    }
    (jobs / "deadbeef_intent.json").write_text(json.dumps(intent), encoding="utf-8")
    assert beat_has_active_intent("bg_arc1_event2_pre_beat_30", event_dir) is True


def test_locked_element_char_ref_gate_rejects_pose_only_match(tmp_path):
    """Locked char ref must align with refer_images, not poses/ bytes alone."""
    char = tmp_path / "hands_face.png"
    char.write_bytes(b"operator-still")
    beat = {
        "speaker": "Lorelai",
        "reference_image_locked": True,
        "reference_image": {"abs_path": str(char)},
    }

    def _match(_path, _speaker, allow_pose_dir_fallback=True):
        if allow_pose_dir_fallback:
            return True, ""
        return False, "not in refer_images"

    with patch(
        "tools.kling_character_registry.is_speaker_voice_ready",
        return_value=True,
    ), patch(
        "tools.kling_character_registry.char_ref_matches_element_images",
        side_effect=_match,
    ), patch(
        "beat_generator.resolve_beat_char_ref_path",
        return_value=str(char),
    ):
        ok, detail = bg.element_char_ref_gate(beat)
    assert ok is False
    assert "refer_images" in detail


def test_try_register_reconciles_when_only_pose_dir_matches(tmp_path):
    char = tmp_path / "hands_face.png"
    char.write_bytes(b"operator-still")
    beat = {
        "speaker": "Lorelai",
        "reference_image": {"abs_path": str(char)},
    }

    def _match(_path, _speaker, allow_pose_dir_fallback=True):
        if allow_pose_dir_fallback:
            return True, ""
        return False, "not in refer_images"

    with patch(
        "tools.kling_character_registry.is_speaker_voice_ready",
        return_value=True,
    ), patch(
        "tools.kling_character_registry.char_ref_matches_element_images",
        side_effect=_match,
    ), patch(
        "beat_generator.resolve_beat_char_ref_path",
        return_value=str(char),
    ), patch(
        "tools.kling_character_registry.reconcile_char_ref_with_element",
        return_value={"ok": True, "pose_rel": "Lorelai/poses/hands_face.png"},
    ) as reconcile:
        result = bg.try_register_dropped_char_ref_on_element(beat, "ws-key")
    reconcile.assert_called_once()
    assert result["ok"] is True
    assert result["action"] == "reconciled"


@patch("tools.kling_character_registry.is_speaker_voice_ready", return_value=True)
@patch("beat_generator.resolve_o3_element_list_entry")
@patch("beat_generator.validate_proven_o3_element_submit", return_value=None)
@patch("tools.kling_voice_bind.detect_voice_bind_drift", return_value=None)
@patch("tools.kling_o3_prompt.validate_element_list_alignment", return_value=[])
def test_commit_reconciles_pose_only_already_matched(
    _align, _drift, _proven, mock_element, _ready, tmp_path,
):
    mock_element.return_value = {"element_id": "1", "element_name": "Loral", "voice_id": "v1"}
    beat = _voice_ready_lorelai_beat(tmp_path)
    sidecar = _minimal_sidecar(beat)
    event_dir = tmp_path / "Event_2"
    event_dir.mkdir()
    body = {
        "kling_o3_prompt": beat["kling_o3_prompt"],
        "reference_image": beat["reference_image"],
        "bg_ref_image": beat["bg_ref_image"],
    }
    char_path = beat["reference_image"]["abs_path"]
    calls = {"strict": 0}

    def _match(_path, _speaker, allow_pose_dir_fallback=True):
        if not allow_pose_dir_fallback:
            calls["strict"] += 1
            return calls["strict"] >= 3, ""
        return True, ""

    with patch(
        "tools.kling_character_registry.char_ref_matches_element_images",
        side_effect=_match,
    ), patch(
        "beat_generator.try_register_dropped_char_ref_on_element",
        return_value={"ok": True, "action": "already_matched"},
    ), patch(
        "tools.kling_character_registry.reconcile_char_ref_with_element",
        return_value={"ok": True, "pose_rel": "Lorelai/poses/hands_face.png"},
    ) as reconcile:
        intent = build_generation_intent(
            beat=beat,
            sidecar=sidecar,
            body=body,
            beat_id=beat["beat_id"],
            event_dir=event_dir,
            job_id="job5",
            attempt_id="a5",
            log_path=event_dir / "j.log",
            pipeline_script=tmp_path / "p.py",
            wavespeed_key="k",
        )
    reconcile.assert_called_once_with("Lorelai", char_path, "k")
    assert intent["visual"]["element_char_ref_gate"]["registration_action"] == "reconciled_after_pose_only_match"
