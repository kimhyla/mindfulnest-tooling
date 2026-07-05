"""KLING_REAL_VOICE_HARVEST_V1 — gallery visibility + TTS supersede durability."""
from __future__ import annotations

from pathlib import Path

import pytest

import beat_generator as bg


def _still_beat_with_harvest(*, audio_file: str = "line_02_benson.mp3") -> dict:
    beat_id = "bg_arc1_event5_post_beat_02"
    tts = f"/Event_5/kling_o3_clips/{beat_id}_still_insert_1783211607_tts.mp4"
    harvest = f"/Event_5/kling_o3_clips/{beat_id}_g1_delivery.mp4"
    return {
        "beat_id": beat_id,
        "pipeline": "still_insert",
        "beat_render_mode": "still_insert",
        "audio_file": audio_file,
        "kling_o3_video_path": harvest,
        "kling_o3_options": [
            {
                "key": f"{beat_id}_still_insert_tts",
                "source": "still_insert_ken_burns",
                "video_path": tts,
                "audio_contract": "tts_muxed",
                "slot_index": 0,
                "active": False,
            },
            {
                "key": f"{beat_id}_o3_video_harvest",
                "source": "kling_real_voice_harvest",
                "label": "POV visual + Omni Benson voice (real-voice harvest)",
                "video_path": harvest,
                "audio_contract": "embedded_voice",
                "slot_index": 2,
                "active": True,
            },
        ],
    }


def test_o3_option_visible_in_ui_slots_shows_harvest_on_still_beat():
    beat = _still_beat_with_harvest()
    harvest_opt = beat["kling_o3_options"][1]
    tts_opt = beat["kling_o3_options"][0]
    assert bg.o3_option_visible_in_ui_slots(harvest_opt, bg.PIPELINE_MODE_STILL)
    assert bg.o3_option_visible_in_ui_slots(tts_opt, bg.PIPELINE_MODE_STILL)


def test_normalize_option_slots_includes_harvest_for_still_beat():
    beat = _still_beat_with_harvest()
    slots = bg.normalize_kling_o3_option_slots(beat)
    paths = [s.get("video_path") for s in slots if s]
    assert any("g1_delivery" in (p or "") for p in paths)
    assert any("still_insert" in (p or "") for p in paths)


def test_apply_real_voice_harvest_beat_fields_supersedes_audio_file():
    beat = _still_beat_with_harvest()
    changed = bg.apply_real_voice_harvest_beat_fields(
        beat, now="2026-07-05T00:00:00+00:00",
    )
    assert changed is True
    assert beat.get("real_voice_harvest_active") is True
    assert beat.get("superseded_tts_audio_file") == "line_02_benson.mp3"
    assert "audio_file" not in beat
    assert beat.get("audio_file_exists") is False
    assert bg.apply_real_voice_harvest_beat_fields(beat, now="2026-07-05T01:00:00+00:00") is False


def test_beat_active_clip_supersedes_tts_preview():
    beat = _still_beat_with_harvest()
    assert bg.beat_active_clip_supersedes_tts_preview(beat) is True
    beat["kling_o3_options"][1]["source"] = "kling_o3_element_native_voice"
    assert bg.beat_active_clip_supersedes_tts_preview(beat) is True


def test_bgtab_shows_harvest_in_still_insert_gallery_filter():
    src = Path(__file__).resolve().parents[1] / "storyboard-v2" / "src" / "components" / "BgTab.tsx"
    text = src.read_text(encoding="utf-8")
    assert "source === 'kling_real_voice_harvest'" in text
    assert "beatActiveClipSupersedesTtsPreview" in text
    assert "Omni voice on still (harvest)" in text


def test_import_delivery_clip_applies_harvest_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from beatgen_scope import build_event_production_scope
    from lib.beatgen_store import BeatgenStore

    event_dir = tmp_path / "Event_5"
    clips_dir = event_dir / "kling_o3_clips"
    clips_dir.mkdir(parents=True)
    db = tmp_path / "beatgen_event5.db"
    beat_id = "bg_arc1_event5_post_beat_02"
    sidecar = {
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_5_post": {
                        "beats": [{
                            "beat_id": beat_id,
                            "pipeline": "still_insert",
                            "beat_render_mode": "still_insert",
                            "audio_file": "line_02_benson.mp3",
                            "kling_o3_options": [],
                        }],
                    },
                },
            },
        },
    }
    monkeypatch.setenv("MN_BEATGEN_DB_PATH", str(db))
    monkeypatch.setenv("MN_SIDECAR_SQLITE_AUTHORITY", "1")
    monkeypatch.setenv("MN_BEATGEN_SERVER_WRITER", "1")
    monkeypatch.setattr(bg, "bootstrap_sqlite_from_legacy_global_db", lambda *_a, **_k: 0)
    BeatgenStore.reset_singleton_for_tests()
    bg.reset_bg_paths_activation_for_tests()
    bg.init_bg_paths(str(event_dir), clear_milestone_scope=True)
    bg._beatgen_store().import_from_dict(sidecar, replace=True)
    delivery = tmp_path / "incoming.mp4"
    delivery.write_bytes(b"fake-harvest")
    monkeypatch.setattr(bg, "persist_o3_disk_enrich_on_beat", lambda *a, **k: None)
    monkeypatch.setattr(
        "kling_stitch_readiness.finalize_kling_delivery_clip",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "o3_gallery_option_identity.probe_o3_clip_audio_contract",
        lambda _p: "embedded_voice",
    )
    monkeypatch.setattr(
        "o3_gallery_option_identity.stamp_o3_option_audio_contract",
        lambda opt, **kw: opt.update({"audio_contract": "embedded_voice"}),
    )

    ok, beat = bg.import_delivery_clip_to_beat(
        beat_id=beat_id,
        delivery_mp4=delivery,
        slot_index=2,
        label="POV visual + Omni Benson voice (real-voice harvest)",
        source="kling_real_voice_harvest",
        make_active=True,
        event_dir=event_dir,
        scope=build_event_production_scope(event_dir),
    )
    assert ok is True
    assert beat is not None
    assert beat.get("real_voice_harvest_active") is True
    assert beat.get("superseded_tts_audio_file") == "line_02_benson.mp3"
    assert "audio_file" not in beat
