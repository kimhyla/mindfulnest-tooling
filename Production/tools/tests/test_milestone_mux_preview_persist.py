"""Milestone mux preview artifacts must persist to milestone-local stitch_state.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))


def _milestone_store(tmp_path: Path):
    project = tmp_path
    event_dir = project / "Production" / "Event_2"
    event_dir.mkdir(parents=True)
    milestone_dir = project / "Production" / "Milestones" / "milestone1_arc1"
    milestone_dir.mkdir(parents=True)
    stitch_path = milestone_dir / "stitch_state.json"
    cache = project / "Production" / "stitch_editor_cache"
    cache.mkdir(parents=True)
    return project, event_dir, milestone_dir, stitch_path, cache


class StitchState:
    def __init__(self, path: Path):
        self.state_path = path
        self.lock = __import__("threading").Lock()
        self.file_lock_path = path.with_suffix(".lock")
        path.parent.mkdir(parents=True, exist_ok=True)
        self.file_lock_path.touch()
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"version": 1, "jobs": {}}), encoding="utf-8")

    def read_state(self):
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def mutate_state(self, fn):
        with self.lock:
            state = self.read_state()
            fn(state)
            self.state_path.write_text(json.dumps(state), encoding="utf-8")


def test_validate_heals_mux_when_mix_sig_missing_but_cache_valid(tmp_path: Path) -> None:
    from server_handlers.stitch_media_artifacts import validate_stitch_slot_media_artifacts
    from server_handlers.stitch_media_sig import compute_stitch_mix_sig_from_slot

    project, _, _, stitch_path, cache = _milestone_store(tmp_path)
    mux_hash = "healmux001"
    (cache / f"stitch_preview_{mux_hash}.mp4").write_bytes(b"preview" * 200)
    slot = {
        "video_path": "Production/Milestones/milestone1_arc1/assembled/final.mp4",
        "video_dur_ms": 96000,
        "ambient_bed": "Intro video ambient bed",
        "ambient_volume": 0.15,
        "mux_preview_hash": mux_hash,
        "mux_preview_duration_ms": 96000,
        "mux_video_path": "Production/Milestones/milestone1_arc1/assembled/final.mp4",
        "mux_video_mtime_ms": 1000,
        "sfx_cues": [{"id": "c1", "offset_ms": 79000, "duration_ms": 3000}],
    }
    h = mock.Mock()
    h._stitch_cache_dir.return_value = cache
    h._stitch_resolve_path.side_effect = lambda p: str(project / p)

    expected_sig = compute_stitch_mix_sig_from_slot(h, {**slot, "mix_sig": "placeholder"})
    # mix_sig intentionally absent on disk — validate must heal, not clear mux.
    warnings = validate_stitch_slot_media_artifacts(h, slot, fast=True)
    assert slot.get("mux_preview_hash") == mux_hash
    assert (slot.get("mix_sig") or "").strip()
    assert "mix_sig missing" not in " ".join(warnings).lower()


def test_load_job_persists_validate_pinned_mix_sig(tmp_path: Path) -> None:
    from server_handlers.stitch_editor import handle_stitch_load_job

    project, event_dir, _, stitch_path, cache = _milestone_store(tmp_path)
    mux_hash = "persistmux1"
    (cache / f"stitch_preview_{mux_hash}.mp4").write_bytes(b"preview" * 200)
    job_name = "milestone_milestone1_arc1_stitch"
    job = {
        "created_at": "2026-07-03T00:00:00+00:00",
        "updated_at": "2026-07-03T00:00:00+00:00",
        "slots": {
            "standalone": {
                "video_path": "Production/Milestones/milestone1_arc1/assembled/final.mp4",
                "video_dur_ms": 96000,
                "ambient_bed": "Intro video ambient bed",
                "ambient_volume": 0.15,
                "mux_preview_hash": mux_hash,
                "mux_preview_duration_ms": 96000,
                "mux_video_path": "Production/Milestones/milestone1_arc1/assembled/final.mp4",
                "mux_video_mtime_ms": 1000,
                "sfx_cues": [{"id": "c1", "offset_ms": 79000, "duration_ms": 3000}],
            },
        },
        "transitions": [],
    }
    stitch_path.write_text(json.dumps({"version": 1, "jobs": {job_name: job}}), encoding="utf-8")
    (project / "Production" / "Milestones" / "milestone1_arc1" / "assembled").mkdir(parents=True)
    (project / "Production" / "Milestones" / "milestone1_arc1" / "assembled" / "final.mp4").write_bytes(
        b"video",
    )

    h = mock.Mock()
    h.app.event_dir = str(event_dir)
    h.app.stitch_state = StitchState(project / "Production" / "tools" / "stitch_editor_state.json")
    h.app.stitch_state.state_path.parent.mkdir(parents=True, exist_ok=True)
    h._stitch_project_root = lambda: project
    h._stitch_cache_dir = lambda: cache
    h._stitch_resolve_path = lambda raw: str(
        (project / raw).resolve() if not str(raw).startswith("/") else raw,
    )
    sent: dict = {}

    def _send_json(code, payload):
        sent["code"] = code
        sent["payload"] = payload

    h._send_json = _send_json
    h._send_error_v59 = lambda *a, **k: None

    handle_stitch_load_job(h, job_name)
    assert sent.get("code") == 200
    on_disk = json.loads(stitch_path.read_text(encoding="utf-8"))
    slot = on_disk["jobs"][job_name]["slots"]["standalone"]
    assert slot.get("mux_preview_hash") == mux_hash
    assert (slot.get("mix_sig") or "").strip()


def test_reconcile_stitch_preview_artifacts_from_build(tmp_path: Path) -> None:
    from server_handlers.stitch_artifact_build import (
        artifact_builds_dir,
        reconcile_stitch_preview_artifacts_from_build,
        save_build,
    )

    project, event_dir, _, stitch_path, cache = _milestone_store(tmp_path)
    mux_hash = "reconcile01"
    (cache / f"stitch_preview_{mux_hash}.mp4").write_bytes(b"preview" * 200)
    job_name = "milestone_milestone1_arc1_stitch"
    stitch_path.write_text(
        json.dumps(
            {
                "version": 1,
                "jobs": {
                    job_name: {
                        "slots": {
                            "standalone": {
                                "video_path": (
                                    "Production/Milestones/milestone1_arc1/assembled/final.mp4"
                                ),
                                "video_dur_ms": 96000,
                                "ambient_bed": "Intro video ambient bed",
                                "ambient_volume": 0.15,
                                "sfx_cues": [{"id": "c1", "offset_ms": 79000, "duration_ms": 3000}],
                            },
                        },
                    },
                },
            },
        ),
        encoding="utf-8",
    )
    build_id = "testbuild01"
    save_build(
        event_dir,
        {
            "build_id": build_id,
            "status": "done",
            "built_slots": {
                "standalone": {
                    "mux_preview_hash": mux_hash,
                    "mux_preview_duration_ms": 96000,
                },
            },
        },
    )
    assert artifact_builds_dir(event_dir).is_dir()

    h = mock.Mock()
    h.app.event_dir = str(event_dir)
    h._stitch_cache_dir = lambda: cache
    h._stitch_resolve_path = lambda raw: str(project / raw)
    store = StitchState(stitch_path)

    ok = reconcile_stitch_preview_artifacts_from_build(
        h,
        stitch_job_name=job_name,
        slot_key="standalone",
        build_id=build_id,
        stitch_store=store,
    )
    assert ok is True
    slot = store.read_state()["jobs"][job_name]["slots"]["standalone"]
    assert slot.get("mux_preview_hash") == mux_hash
    assert (slot.get("mix_sig") or "").strip()
