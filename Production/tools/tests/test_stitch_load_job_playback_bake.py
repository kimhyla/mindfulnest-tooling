"""STITCH_LOAD_JOB_PLAYBACK_BAKE_V1 retired — load_job must stay read-only (STITCH_WRITE_TIME_PLAYBACK_ARTIFACTS_V1)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))


def _make_handler(project: Path, state_path: Path, *, event_dir: Path | None = None):
    cache = project / "Production" / "stitch_editor_cache"
    cache.mkdir(parents=True, exist_ok=True)
    event_dir = event_dir or (project / "Production" / "Event_1")
    event_dir.mkdir(parents=True, exist_ok=True)

    class StitchState:
        def __init__(self, path: Path):
            self.state_path = path
            self.lock = __import__("threading").Lock()
            self.file_lock_path = path.with_suffix(".lock")
            self.file_lock_path.touch()

        def read_state(self):
            return json.loads(self.state_path.read_text(encoding="utf-8"))

        def mutate_state(self, fn):
            with self.lock:
                state = self.read_state()
                fn(state)
                self.state_path.write_text(json.dumps(state), encoding="utf-8")

    h = MagicMock()
    h.app.event_dir = str(event_dir)
    h.app.stitch_state = StitchState(state_path)
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
    return h, sent, cache


def test_load_job_source_guard_has_no_playback_bake() -> None:
    src = (TOOLS / "server_handlers/stitch_editor.py").read_text(encoding="utf-8")
    block = src.split("def handle_stitch_load_job", 1)[1].split(
        "\ndef handle_stitch_serve_module_final", 1,
    )[0]
    assert "STITCH_WRITE_TIME_PLAYBACK_ARTIFACTS_V1" in block
    assert "STITCH_LOAD_JOB_PLAYBACK_BAKE_V1" not in block
    assert 'trigger="load_job"' not in block


def test_load_job_does_not_call_playback_bake() -> None:
    from server_handlers.stitch_editor import handle_stitch_load_job

    project = Path("/tmp/stitch_load_job_no_bake")
    tools = project / "Production" / "tools"
    tools.mkdir(parents=True, exist_ok=True)
    state_path = tools / "stitch_editor_state.json"
    video_rel = "Production/Event_1/intro.mp4"
    (project / video_rel).parent.mkdir(parents=True, exist_ok=True)
    (project / video_rel).write_bytes(b"video" * 100)
    job = {
        "created_at": "2026-06-22T00:00:00+00:00",
        "updated_at": "2026-06-22T00:00:00+00:00",
        "slots": {
            "intro": {
                "video_path": video_rel,
                "video_dur_ms": 5000,
                "ambient_bed": "Intro video ambient bed",
                "ambient_volume": 0.15,
                "sfx_cues": [{"id": "c1", "offset_ms": 0, "duration_ms": 500}],
            },
        },
        "transitions": [],
    }
    state_path.write_text(
        json.dumps({"version": 1, "jobs": {"Event_1_stitch": job}}),
        encoding="utf-8",
    )
    h, sent, _ = _make_handler(project, state_path)
    bake_calls = 0
    import server_handlers.stitch_editor as se

    def _spy(*a, **k):
        nonlocal bake_calls
        bake_calls += 1
        return {"ok": True}

    with patch.object(se, "ensure_stitch_slot_playback_artifacts", side_effect=_spy), patch(
        "server_handlers.stitch_editor.collect_stitch_job_slot_warnings",
        return_value={},
    ), patch(
        "server_handlers.stitch_editor.ensure_job_slot_defaults",
        return_value=False,
    ), patch(
        "server_handlers.stitch_editor.ensure_stitch_slot_timeline_dur_ms",
        return_value=False,
    ), patch(
        "stitch_bake_job_store.active_bake_job_summary",
        return_value=None,
    ):
        handle_stitch_load_job(h, "Event_1_stitch")

    assert sent.get("code") == 200
    assert bake_calls == 0
    assert "load_job_playback_bake_code" not in sent["payload"]
