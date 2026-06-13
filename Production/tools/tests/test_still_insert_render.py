"""Still-insert Ken Burns → O3 slot clip (Beat Gen restore)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import beat_generator as bg


def test_beat_is_still_insert():
    assert bg.beat_is_still_insert({"pipeline": "still_insert"})
    assert bg.beat_is_still_insert({"beat_render_mode": "still_insert"})
    assert not bg.beat_is_still_insert({"pipeline": "kling_o3"})
    assert not bg.beat_is_still_insert({})


def test_resolve_still_source_prefers_library_drop(tmp_path: Path):
    still = tmp_path / "scene.png"
    still.write_bytes(b"png")
    beat = {
        "accepted_library_ref": {"abs_path": str(still)},
        "bg_ref_image": {"abs_path": str(tmp_path / "other.png")},
    }
    assert bg.resolve_still_source_abs_path(beat) == still.resolve()


def test_resolve_still_source_falls_back_to_bg_ref(tmp_path: Path):
    still = tmp_path / "bg.webp"
    still.write_bytes(b"webp")
    beat = {"bg_ref_image": {"abs_path": str(still)}}
    assert bg.resolve_still_source_abs_path(beat) == still.resolve()


def test_render_still_insert_o3_clip_writes_o3_fields(tmp_path: Path):
    event_dir = tmp_path / "Event_2"
    event_dir.mkdir()
    still = event_dir / "still.png"
    still.write_bytes(b"png")
    beat = {
        "beat_id": "bg_arc1_event2_pre_beat_01",
        "pipeline": "still_insert",
        "bg_ref_image": {"abs_path": str(still)},
    }

    def _fake_ken_burns(_beat, _still_path, *_args, **kwargs):
        out = Path(kwargs["out_path"])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"mp4")
        return {"video_path": str(out), "preview_path": _still_path}

    with patch.object(bg, "run_ken_burns", side_effect=_fake_ken_burns), patch.object(
        bg, "resolve_bg_beat_tts_audio_path", return_value=None,
    ):
        result = bg.render_still_insert_o3_clip(
            beat, event_dir, method="ken_burns", duration=4.0, slot_index=0,
        )

    assert Path(result["video_path"]).is_file()
    assert beat["kling_o3_status"] == "approved"
    assert beat["status"] == "approved"
    assert beat["kling_o3_video_path"] == result["video_path"]
    assert any(o.get("video_path") == result["video_path"] for o in beat["kling_o3_options"])


def test_production_server_registers_render_still_clip_route():
    text = (Path(__file__).resolve().parent.parent / "production_server.py").read_text(
        encoding="utf-8",
    )
    assert "/api/bg/render-still-clip" in text
    assert "_handle_bg_render_still_clip" in text


def test_endpoints_and_bgtab_wiring():
    root = Path(__file__).resolve().parent.parent / "storyboard-v2" / "src"
    endpoints = (root / "api" / "endpoints.ts").read_text(encoding="utf-8")
    assert "bg_render_still_clip" in endpoints
    bgtab = (root / "components" / "BgTab.tsx").read_text(encoding="utf-8")
    assert "isStillInsertBeat" in bgtab
    assert "Render still clip (Ken Burns + TTS)" in bgtab
    assert "bg_render_still_clip" in bgtab
