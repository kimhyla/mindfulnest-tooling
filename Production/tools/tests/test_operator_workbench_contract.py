"""Operator workbench authority — contract tests."""
from __future__ import annotations

from pathlib import Path

import beat_generator as bg
import operator_workbench_contract as owc


def test_write_still_scene_source_syncs_bg_ref_and_gpt(tmp_path: Path):
    still = tmp_path / "scene.png"
    still.write_bytes(b"png")
    beat: dict = {"beat_id": "bg_test_beat_01", "pipeline": "still_insert"}
    owc.write_still_scene_source(
        beat,
        key="scene_key",
        filename="scene.png",
        abs_path=str(still),
        slot_index=0,
        thumb_b64="data:image/png;base64,abc",
    )
    assert beat["bg_ref_image"]["abs_path"] == str(still)
    assert beat["accepted_library_ref"]["abs_path"] == str(still)
    assert beat["gpt_options"][0]["local_path"] == str(still)
    assert owc.resolve_beat_still_scene_abs_path(beat) == still.resolve()


def test_resolve_still_scene_includes_flux_legacy(tmp_path: Path):
    still = tmp_path / "legacy.png"
    still.write_bytes(b"png")
    beat = {
        "beat_id": "bg_test",
        "pipeline": "still_insert",
        "flux_options": [{"local_path": str(still), "key": "legacy"}],
    }
    assert owc.resolve_beat_still_scene_abs_path(beat) == still.resolve()


def test_migrate_backfills_bg_ref_from_library(tmp_path: Path):
    still = tmp_path / "lib.png"
    still.write_bytes(b"png")
    beat = {
        "beat_id": "bg_arc1_event2_post_beat_02",
        "pipeline": "still_insert",
        "beat_render_mode": "still_insert",
        "accepted_library_ref": {
            "key": "lib_key",
            "filename": "lib.png",
            "abs_path": str(still),
            "slot_index": 0,
        },
        "bg_ref_image": None,
    }
    assert owc.migrate_operator_workbench_beat(beat) is True
    assert beat["bg_ref_image"]["abs_path"] == str(still)


def test_enrich_beat_operator_derived_still_scene(tmp_path: Path):
    still = tmp_path / "scene.png"
    still.write_bytes(b"png")
    beat = {
        "beat_id": "bg_test",
        "pipeline": "still_insert",
        "accepted_library_ref": {
            "key": "k",
            "filename": "scene.png",
            "abs_path": str(still),
            "slot_index": 0,
        },
        "bg_ref_image": None,
        "kling_o3_options": [
            {"key": "v1", "video_path": "/tmp/v1.mp4", "slot_index": 0, "source": "still_insert_ken_burns"},
        ],
    }
    sidecar = {"arcs": {}}
    derived = owc.enrich_beat_operator_derived(
        beat,
        sidecar,
        event_id="2",
        phase="post",
        approved_roots=[],
    )
    assert derived["still_scene_display"]["abs_path"] == str(still)
    assert derived["generation_mode"] == "still_insert"
    assert len(derived["option_slots"]) == 3
    assert derived["option_slots"][0]["video_path"] == "/tmp/v1.mp4"


def test_enrich_beat_operator_derived_stitch_export(tmp_path: Path):
    clip = tmp_path / "still.mp4"
    clip.write_bytes(b"mp4")
    beat = {
        "beat_id": "bg_arc1_event5_pre_beat_06",
        "pipeline": "still_insert",
        "kling_o3_status": "still_rendered",
        "kling_o3_video_path": str(clip),
    }
    sidecar = {"arcs": {}}
    derived = owc.enrich_beat_operator_derived(
        beat,
        sidecar,
        event_id="5",
        phase="pre",
        event_dir=tmp_path,
        approved_roots=[],
    )
    assert derived["stitch_export_ready"] is False
    assert derived["stitch_export_block_label"] == "Approve still clip"
    assert "Approve still for stitch" in (derived["stitch_export_fix_instruction"] or "")
    beat["kling_o3_still_stitch_approved"] = True
    derived2 = owc.enrich_beat_operator_derived(
        beat,
        sidecar,
        event_id="5",
        phase="pre",
        event_dir=tmp_path,
        approved_roots=[],
    )
    assert derived2["stitch_export_ready"] is True
    assert derived2["stitch_export_block_label"] is None


def test_materialize_o3_submit_refs_uses_char_default(tmp_path: Path, monkeypatch):
    char = tmp_path / "lorelai.png"
    char.write_bytes(b"png")
    beat = {"beat_id": "bg_test", "speaker": "Lorelai", "reference_image": None}
    monkeypatch.setattr(bg, "resolve_beat_char_ref_path", lambda _b: str(char))
    monkeypatch.setattr(bg, "resolve_beat_bg_ref_path", lambda _b, _e, _p: str(char))
    char_ref, bg_ref = owc.materialize_o3_submit_refs(
        {},
        beat,
        event_id="2",
        phase="post",
    )
    assert char_ref is not None
    assert char_ref["abs_path"] == str(char)
    assert bg_ref is not None


def test_session_get_does_not_overwrite_kling_prompt(tmp_path: Path):
    """GET derived block carries display_prompt without mutating stored prompt."""
    beat = {
        "beat_id": "bg_test",
        "pipeline": "still_insert",
        "kling_o3_prompt": "stored prompt",
        "kling_o3_prompt_still": "stored prompt",
    }
    sidecar = {"arcs": {}}
    derived = owc.enrich_beat_operator_derived(beat, sidecar, event_id="2", phase="post")
    assert beat["kling_o3_prompt"] == "stored prompt"
    assert derived["display_prompt"] == "stored prompt"


def test_element_char_ref_gate_trusts_persisted_disk_when_pose_dir_strict_fails(
    tmp_path: Path,
    monkeypatch,
):
    """Event 2 beats 1/3: library char ref + disk ok must not block Generate."""
    char = tmp_path / "library_char.png"
    char.write_bytes(b"library-bytes")
    beat = {
        "beat_id": "bg_arc1_event2_post_beat_01",
        "speaker": "Lorelai",
        "reference_image": {"abs_path": str(char), "key": "library_char"},
        "element_char_ref_ok": True,
    }
    sidecar = {"arcs": {}}

    def _strict_fail(_path, _speaker, allow_pose_dir_fallback=False):
        return False, "strict pose-dir mismatch"

    monkeypatch.setattr(bg, "resolve_beat_char_ref_path", lambda _b: str(char))
    monkeypatch.setattr(
        "tools.kling_character_registry.char_ref_matches_element_images",
        _strict_fail,
    )
    monkeypatch.setattr(
        "tools.kling_character_registry.is_speaker_voice_ready",
        lambda _s: True,
    )
    monkeypatch.setattr(
        "tools.kling_character_registry.get_character_entry",
        lambda _s: {"refer_images": []},
    )
    monkeypatch.setattr(
        "tools.kling_character_registry.refer_images_contain_path_or_hash",
        lambda *_a, **_k: False,
    )
    monkeypatch.setattr(
        "tools.kling_character_registry.find_pose_rel_by_hash",
        lambda *_a, **_k: None,
    )

    ok, err = owc.resolve_beat_element_char_ref_gate(beat)
    assert ok is True
    assert err is None

    derived = owc.enrich_beat_operator_derived(beat, sidecar, event_id="2", phase="post")
    assert derived["element_char_ref_ok"] is True


def test_element_char_ref_gate_blocks_when_disk_false_and_no_match(
    tmp_path: Path,
    monkeypatch,
):
    char = tmp_path / "orphan.png"
    char.write_bytes(b"x")
    beat = {
        "speaker": "Lorelai",
        "reference_image": {"abs_path": str(char)},
        "element_char_ref_ok": False,
    }

    monkeypatch.setattr(bg, "resolve_beat_char_ref_path", lambda _b: str(char))
    monkeypatch.setattr(
        "tools.kling_character_registry.is_speaker_voice_ready",
        lambda _s: True,
    )
    monkeypatch.setattr(
        "tools.kling_character_registry.char_ref_matches_element_images",
        lambda *_a, **_k: (False, "no match"),
    )
    monkeypatch.setattr(
        "tools.kling_character_registry.get_character_entry",
        lambda _s: {"refer_images": []},
    )
    monkeypatch.setattr(
        "tools.kling_character_registry.refer_images_contain_path_or_hash",
        lambda *_a, **_k: False,
    )
    monkeypatch.setattr(
        "tools.kling_character_registry.find_pose_rel_by_hash",
        lambda *_a, **_k: None,
    )

    ok, err = owc.resolve_beat_element_char_ref_gate(beat)
    assert ok is False
    assert err == "no match"


def test_session_enrich_recomputes_stale_o3_pipeline_mismatch():
    """Stale sidecar mismatch flags must not leak through session GET."""
    beat = {
        "beat_id": "bg_arc1_event3_pre_beat_10",
        "pipeline": "kling_o3_omni",
        "o3_generate_mode": "element_native",
        "kling_o3_video_path": "/Event_3/kling_o3_clips/bg_arc1_event3_pre_beat_10_g1_delivery.mp4",
        "kling_o3_selection_pipeline_mismatch": True,
        "kling_o3_active_clip_pipeline": "still_insert",
        "kling_o3_options": [
            {
                "key": "k1",
                "video_path": "/Event_3/kling_o3_clips/bg_arc1_event3_pre_beat_10_g1_delivery.mp4",
                "source": "o3_pov_motion_i2v",
                "slot_index": 0,
                "active": True,
            },
        ],
    }
    sidecar = {"arcs": {}}
    rows = owc.enrich_beats_for_session_response(
        [beat],
        sidecar,
        event_id="Event_3",
        phase="pre",
        approved_roots=None,
        production_state=None,
        video_role="intro",
        event_dir="/tmp/Event_3",
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.get("kling_o3_selection_pipeline_mismatch") is None
    assert row.get("kling_o3_active_clip_pipeline") == bg.O3_GENERATE_MODE_ELEMENT_NATIVE
