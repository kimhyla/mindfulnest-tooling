"""STITCH_LOAD_JOB_PLAYBACK_BAKE_V1 — load_job auto-bakes missing mux/ambient artifacts."""

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


def test_load_job_source_guard_has_playback_bake() -> None:
    src = (TOOLS / "server_handlers/stitch_editor.py").read_text(encoding="utf-8")
    block = src.split("def handle_stitch_load_job", 1)[1].split(
        "\ndef handle_stitch_serve_module_final", 1,
    )[0]
    assert "STITCH_LOAD_JOB_PLAYBACK_BAKE_V1" in block
    assert "stitch_slot_needs_playback_artifact_bake" in block
    assert "ensure_stitch_slot_playback_artifacts" in block
    assert "trigger=\"load_job\"" in block or "trigger='load_job'" in block


def test_stitch_slot_needs_playback_bake_when_sfx_missing_mux(tmp_path: Path) -> None:
    from server_handlers.stitch_media_artifacts import stitch_slot_needs_playback_artifact_bake

    project = tmp_path
    state_path = project / "stitch_editor_state.json"
    h, _, _ = _make_handler(project, state_path)
    slot = {
        "video_path": "Production/Event_1/intro.mp4",
        "sfx_cues": [{"id": "c1", "offset_ms": 0, "duration_ms": 500}],
    }
    assert stitch_slot_needs_playback_artifact_bake(h, slot) is True


def test_load_job_bakes_missing_mux_on_persisted_job(tmp_path: Path) -> None:
    from server_handlers.stitch_editor import (
        STITCH_LOAD_JOB_PLAYBACK_BAKE_V1,
        handle_stitch_load_job,
    )

    project = tmp_path
    tools = project / "Production" / "tools"
    tools.mkdir(parents=True)
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
    h, sent, cache = _make_handler(project, state_path)
    fake_preview = cache / "stitch_preview_bakedmux1.mp4"
    fake_preview.write_bytes(b"muxed" * 200)

    with patch(
        "server_handlers.stitch_editor.build_stitch_slot_mux_preview_file",
        return_value=("bakedmux1", 5000),
    ), patch(
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
    payload = sent["payload"]
    assert payload.get("load_job_playback_bake_code") == STITCH_LOAD_JOB_PLAYBACK_BAKE_V1
    intro = payload["job"]["slots"]["intro"]
    assert intro.get("mux_preview_hash") == "bakedmux1"
    assert intro.get("_mux_preview_url")

    saved = json.loads(state_path.read_text(encoding="utf-8"))
    assert saved["jobs"]["Event_1_stitch"]["slots"]["intro"]["mux_preview_hash"] == "bakedmux1"


def test_load_job_skips_bake_when_mux_artifacts_present(tmp_path: Path) -> None:
    from server_handlers.stitch_editor import handle_stitch_load_job

    project = tmp_path
    tools = project / "Production" / "tools"
    tools.mkdir(parents=True)
    state_path = tools / "stitch_editor_state.json"
    amb_hash = "haveamb01"
    peaks_hash = "havepeak1"
    cache = project / "Production" / "stitch_editor_cache"
    cache.mkdir(parents=True)
    (cache / f"se_slot_{amb_hash}.mp4").write_bytes(b"ambient" * 200)
    (cache / f"stitch_peaks_{peaks_hash}.json").write_text(
        json.dumps({"duration_s": 10.0}), encoding="utf-8",
    )
    video_rel = "Production/Event_1/phase_a.mp4"
    (project / video_rel).parent.mkdir(parents=True, exist_ok=True)
    (project / video_rel).write_bytes(b"video")
    job = {
        "created_at": "2026-06-22T00:00:00+00:00",
        "updated_at": "2026-06-22T00:00:00+00:00",
        "slots": {
            "phase_a": {
                "video_path": video_rel,
                "video_dur_ms": 10000,
                "ambient_bed": "ambient bed pretty option2",
                "ambient_volume": 0.15,
                "mix_sig": "abc",
                "ambient_mix_sig": "def",
                "ambient_mix_hash": amb_hash,
                "ambient_mix_duration_ms": 10000,
                "ambient_mix_video_path": video_rel,
                "ambient_mix_video_mtime_ms": 1000,
                "waveform_peaks_hash": peaks_hash,
                "waveform_peaks_duration_s": 10.0,
            },
        },
        "transitions": [],
    }
    state_path.write_text(
        json.dumps({"version": 1, "jobs": {"Event_1_stitch": job}}),
        encoding="utf-8",
    )
    from server_handlers.stitch_media_artifacts import stitch_slot_needs_playback_artifact_bake

    h, sent, _ = _make_handler(project, state_path)
    slot = json.loads(state_path.read_text())["jobs"]["Event_1_stitch"]["slots"]["phase_a"]
    assert stitch_slot_needs_playback_artifact_bake(h, slot) is False

    bake_calls = 0
    import server_handlers.stitch_editor as se

    original = se.ensure_stitch_slot_playback_artifacts

    def _spy(*a, **k):
        nonlocal bake_calls
        bake_calls += 1
        return original(*a, **k)

    with patch(
        "server_handlers.stitch_media_artifacts.stitch_slot_needs_playback_artifact_bake",
        return_value=False,
    ), patch.object(se, "ensure_stitch_slot_playback_artifacts", side_effect=_spy), patch(
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


def test_load_job_skips_rebake_when_mix_sig_requires_ambient_hydrate(tmp_path: Path) -> None:
    """mix_sig is keyed on hydrated ambient_bed_path — load_job must hydrate before validate."""
    from server_handlers.stitch_editor import handle_stitch_load_job
    from server_handlers.stitch_media_sig import compute_stitch_mix_sig_from_slot

    project = tmp_path
    tools = project / "Production" / "tools"
    tools.mkdir(parents=True)
    state_path = tools / "stitch_editor_state.json"
    cache = project / "Production" / "stitch_editor_cache"
    cache.mkdir(parents=True)
    mux_hash = "havemux01"
    (cache / f"stitch_preview_{mux_hash}.mp4").write_bytes(b"muxed" * 256)
    video_rel = "Production/Event_1/intro.mp4"
    amb_rel = "Production/assets/sound_library/ambient/test_ambient.mp3"
    (project / video_rel).parent.mkdir(parents=True, exist_ok=True)
    (project / amb_rel).parent.mkdir(parents=True, exist_ok=True)
    (project / video_rel).write_bytes(b"video" * 100)
    (project / amb_rel).write_bytes(b"ambient")
    h, sent, _ = _make_handler(project, state_path)
    slot_template = {
        "video_path": video_rel,
        "video_dur_ms": 5000,
        "ambient_bed": "test_ambient",
        "ambient_volume": 0.15,
        "sfx_cues": [{"id": "c1", "offset_ms": 0, "duration_ms": 500, "volume": 0.5}],
    }
    hydrated = dict(slot_template)
    from server_handlers.stitch_editor import ensure_slot_ambient_bed_path_hydrated

    ensure_slot_ambient_bed_path_hydrated(h, hydrated)
    mix_sig = compute_stitch_mix_sig_from_slot(h, hydrated)
    job = {
        "created_at": "2026-06-22T00:00:00+00:00",
        "updated_at": "2026-06-22T00:00:00+00:00",
        "slots": {
            "intro": {
                **slot_template,
                "mix_sig": mix_sig,
                "mux_preview_hash": mux_hash,
                "mux_preview_duration_ms": 5000,
                "mux_video_path": video_rel,
                "mux_video_mtime_ms": 1000,
            },
        },
        "transitions": [],
    }
    state_path.write_text(
        json.dumps({"version": 1, "jobs": {"Event_1_stitch": job}}),
        encoding="utf-8",
    )

    bake_calls = 0
    import server_handlers.stitch_editor as se

    original = se.ensure_stitch_slot_playback_artifacts

    def _spy(*a, **k):
        nonlocal bake_calls
        bake_calls += 1
        return original(*a, **k)

    with patch.object(se, "ensure_stitch_slot_playback_artifacts", side_effect=_spy), patch(
        "server_handlers.stitch_editor.collect_stitch_job_slot_warnings",
        return_value={},
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
    intro = sent["payload"]["job"]["slots"]["intro"]
    assert intro.get("mux_preview_hash") == mux_hash
