"""Category J — session GET job fields match disk sidecar after close (no projection heal)."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import o3_generation_intent as intent_mod
import o3_job_status_contract as contract


def _sidecar_with_beat(beat: dict) -> dict:
    return {
        "schema_version": 3,
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_2_post": {"beats": [beat]},
                },
            },
        },
    }


def test_session_disk_parity_after_failed_close(tmp_path: Path, monkeypatch) -> None:
    """After close_o3_attempt, disk sidecar and job_busy contract agree."""
    prod = tmp_path / "Production"
    event_dir = prod / "Event_2"
    jobs = event_dir / "arlo_o3_jobs"
    jobs.mkdir(parents=True)
    beat_id = "bg_arc1_event2_post_beat_03"
    job_id = "deadjob1"
    beat = {
        "beat_id": beat_id,
        "status": "o3_element_running",
        "kling_o3_status": "submitted",
        "o3_current_job_id": job_id,
        "kling_o3_voice_fix_error": "pipeline lost",
    }
    sidecar = _sidecar_with_beat(beat)
    intent_mod.write_running_terminal_at_submit(job_id, event_dir, beat_id=beat_id)

    import beat_generator as bg

    monkeypatch.setattr(bg, "_PROD_DIR", str(prod))
    monkeypatch.setattr(bg, "read_sidecar", lambda: sidecar)

    def _update(bid: str, fn):
        _, row = bg.find_beat(sidecar, bid)
        fn(row, sidecar)
        return True, sidecar

    monkeypatch.setattr(bg, "update_beat_locked", _update)
    terminal = intent_mod.close_o3_attempt(
        job_id,
        beat_id,
        event_dir,
        "failed",
        reason="subprocess lost after restart",
    )
    assert terminal["status"] == "failed"

    disk_beat = sidecar["arcs"]["arc_1"]["segments"]["event_2_post"]["beats"][0]
    assert disk_beat.get("o3_current_job_id") in (None, "")
    assert disk_beat.get("kling_o3_voice_fix_error")

    busy = contract.beat_job_busy(disk_beat, event_dir, in_memory_jobs={})
    assert busy is False


def test_enrich_beats_job_busy_adds_only_derived_fields() -> None:
    """_enrich_beats_job_busy must not rewrite gallery/status — only job_busy + pointer mirror."""
    from server_handlers import background as bg_handlers

    beat = {
        "beat_id": "bg_arc1_event2_post_beat_03",
        "status": "approved",
        "kling_o3_status": "approved",
        "kling_o3_video_path": "/Event_2/clips/x.mp4",
        "o3_current_job_id": None,
    }
    before = dict(beat)
    prod = Path("/tmp/unused")
    h = MagicMock(app=SimpleNamespace(event_dir=prod / "Event_2", scope_type="event"))
    with patch.object(bg_handlers, "_resolve_beat_job_busy_for_session", return_value=False):
        bg_handlers._enrich_beats_job_busy([beat], prod, h)
    assert beat["job_busy"] is False
    assert beat["o3_current_job_id"] is None
    for key in ("status", "kling_o3_status", "kling_o3_video_path"):
        assert beat[key] == before[key]
