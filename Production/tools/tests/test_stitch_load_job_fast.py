"""STITCH_LOAD_JOB_FAST_V1 — load_job opens in seconds without ffprobe/decode."""

from __future__ import annotations

import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))


def test_load_job_uses_fast_validation_marker() -> None:
    src = (TOOLS / "server_handlers/stitch_editor.py").read_text(encoding="utf-8")
    block = src.split("def handle_stitch_load_job", 1)[1].split(
        "\ndef handle_stitch_serve_module_final", 1,
    )[0]
    assert "STITCH_LOAD_JOB_FAST_V1" in block
    assert "STITCH_LOAD_JOB_PLAYBACK_BAKE_V1" in block
    assert "validate_stitch_slot_media_artifacts(h, slot, fast=True)" in block
    assert "ensure_job_slot_defaults(h, live_slots, fast=True)" in block
    assert "probe_video=False" in block
    assert "rebuild_stitch_ambient_mixes_for_job" not in block


def test_validate_fast_skips_decode_helpers() -> None:
    src = (TOOLS / "server_handlers/stitch_media_artifacts.py").read_text(encoding="utf-8")
    block = src.split("def validate_stitch_slot_media_artifacts", 1)[1].split(
        "\ndef persist_stitch_slot_ambient_mix_artifacts", 1,
    )[0]
    assert "STITCH_LOAD_JOB_FAST_V1" in (TOOLS / "server_handlers/stitch_media_sig.py").read_text()
    assert "_artifact_cache_file_present" in block
    assert "fast and stored_ambient_sig == current_ambient_sig" in block


def test_load_job_fast_under_budget(tmp_path: Path) -> None:
    """Synthetic job: fast path must not call stitch_cached_mp4_playable."""
    import json
    import time
    from unittest.mock import MagicMock

    from server_handlers.stitch_editor import handle_stitch_load_job

    project = tmp_path
    cache = project / "Production" / "stitch_editor_cache"
    cache.mkdir(parents=True)
    tools = project / "Production" / "tools"
    tools.mkdir(parents=True)
    state_path = tools / "stitch_editor_state.json"
    amb_hash = "fastamb01"
    mux_hash = "fastmux01"
    peaks_hash = "fastpeaks1"
    (cache / f"se_slot_{amb_hash}.mp4").write_bytes(b"ambient" * 200)
    (cache / f"stitch_preview_{mux_hash}.mp4").write_bytes(b"preview" * 200)
    (cache / f"stitch_peaks_{peaks_hash}.json").write_text(
        json.dumps({"duration_s": 10.0}), encoding="utf-8",
    )
    job = {
        "created_at": "2026-06-22T00:00:00+00:00",
        "updated_at": "2026-06-22T00:00:00+00:00",
        "slots": {
            "phase_a": {
                "video_path": "Production/Event_1/phase_a.mp4",
                "video_dur_ms": 10000,
                "ambient_bed": "ambient bed pretty option2",
                "ambient_volume": 0.15,
                "mix_sig": "abc",
                "ambient_mix_sig": "def",
                "ambient_mix_hash": amb_hash,
                "ambient_mix_duration_ms": 10000,
                "ambient_mix_video_path": "Production/Event_1/phase_a.mp4",
                "ambient_mix_video_mtime_ms": 1000,
                "mux_preview_hash": mux_hash,
                "mux_preview_duration_ms": 10000,
                "mux_video_path": "Production/Event_1/phase_a.mp4",
                "mux_video_mtime_ms": 1000,
                "waveform_peaks_hash": peaks_hash,
                "waveform_peaks_duration_s": 10.0,
                "sfx_cues": [{"id": "c1", "offset_ms": 0, "duration_ms": 500}],
            },
        },
        "transitions": [],
    }
    state_path.write_text(
        json.dumps({"version": 1, "jobs": {"Event_1_stitch": job}}),
        encoding="utf-8",
    )
    (project / "Production" / "Event_1").mkdir(parents=True)
    (project / "Production" / "Event_1" / "phase_a.mp4").write_bytes(b"video")

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

    event_dir = project / "Production" / "Event_1"
    event_dir.mkdir(parents=True, exist_ok=True)

    h = MagicMock()
    h.app.event_dir = str(event_dir)
    h.app.stitch_state = StitchState(state_path)
    h._stitch_project_root = lambda: project
    h._stitch_cache_dir = lambda: cache
    h._stitch_resolve_path = lambda raw: str(
        (project / raw).resolve() if not str(raw).startswith("/") else raw,
    )
    sent = {}

    def _send_json(code, payload):
        sent["code"] = code
        sent["payload"] = payload

    h._send_json = _send_json
    h._send_error_v59 = lambda *a, **k: None

    decode_calls = 0
    import server_handlers.stitch_editor as se

    original = se.stitch_cached_mp4_playable

    def _spy_playable(*a, **k):
        nonlocal decode_calls
        decode_calls += 1
        return original(*a, **k)

    se.stitch_cached_mp4_playable = _spy_playable
    try:
        t0 = time.perf_counter()
        handle_stitch_load_job(h, "Event_1_stitch")
        elapsed = time.perf_counter() - t0
    finally:
        se.stitch_cached_mp4_playable = original

    assert sent.get("code") == 200
    assert sent["payload"].get("load_job_code") == "STITCH_LOAD_JOB_FAST_V1"
    assert decode_calls == 0
    assert elapsed < 2.0
