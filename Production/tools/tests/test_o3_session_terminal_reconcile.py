"""Session GET terminal disk reconcile — poll-independent gallery + outcomes."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import beat_generator as bg
import o3_generation_intent as intent_mod
import o3_session_terminal_reconcile as reconcile_mod


def _sidecar_with_beat(beat: dict) -> dict:
    return {
        "schema_version": 3,
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_3b_full": {"beats": [beat]},
                },
            },
        },
    }


def test_session_terminal_reconcile_imports_orphan_delivery(tmp_path: Path, monkeypatch) -> None:
    """Terminal done + delivery on disk merges into sidecar on session plan (milestone library Event_1)."""
    prod = tmp_path / "Production"
    lib = prod / "Event_1"
    clips = lib / "kling_o3_clips"
    jobs = lib / "arlo_o3_jobs"
    clips.mkdir(parents=True)
    jobs.mkdir(parents=True)
    beat_id = "bg_arc1_event3b_full_beat_02"
    job_id = "bb189f21"
    delivery = clips / f"{beat_id}_g2_avatar_pro_delivery.mp4"
    delivery.write_bytes(b"mp4")
    intent_mod.write_intent_terminal(job_id, lib, {
        "status": "done",
        "beat_id": beat_id,
        "delivered": {"video_path": str(delivery)},
    })
    beat = {
        "beat_id": beat_id,
        "pipeline": "kling_o3_omni",
        "o3_generate_mode": "avatar_pro",
        "o3_current_job_id": job_id,
        "kling_o3_voice_fix_status": "job_running",
        "kling_o3_options": [],
    }
    sidecar = _sidecar_with_beat(beat)
    monkeypatch.setattr(bg, "_PROD_DIR", str(prod))

    pending, outcomes = reconcile_mod.plan_session_terminal_reconcile(
        [beat],
        sidecar,
        orphan_recovery=lambda *a, **k: None,
        server_event_dir=lib,
        library_event_dir=lib,
        scope_type="milestone",
    )
    assert pending
    merged = dict(beat)
    merged.update(pending[0][1])
    paths = {
        str(o.get("video_path") or "")
        for o in (merged.get("kling_o3_options") or [])
        if isinstance(o, dict)
    }
    assert str(delivery) in paths
    assert merged.get("kling_o3_video_path") == str(delivery)
    assert outcomes and outcomes[0]["status"] == "done"


def test_playback_event_dir_for_milestone_library_clip(tmp_path: Path) -> None:
    prod = tmp_path / "Production"
    prod.mkdir(parents=True)
    server_ev = prod / "Event_2"
    lib_ev = prod / "Event_1"
    server_ev.mkdir(parents=True)
    lib_ev.mkdir(parents=True)
    clip = lib_ev / "kling_o3_clips" / "bg_arc1_event3b_full_beat_02_g2_avatar_pro_delivery.mp4"
    clip.parent.mkdir(parents=True)
    clip.write_bytes(b"x")
    resolved = reconcile_mod.playback_event_dir_for_source(clip.resolve(), server_ev, lib_ev)
    assert resolved.name == "Event_1"


def test_session_get_read_only_outcomes_empty_on_get() -> None:
    src = (Path(__file__).resolve().parent.parent / "server_handlers" / "background.py").read_text(
        encoding="utf-8",
    )
    block = src.split("def handle_bg_session_state", 1)[1].split("\ndef ", 1)[0]
    assert "_compose_o3_session_terminal_view" not in block
    assert "o3_terminal_outcomes" in block
    assert "def _run_o3_terminal_reconcile_at_startup" in src
