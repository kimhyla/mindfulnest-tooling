"""PHASE_B_PATH_A_ROUTE_V1 — behavior tests (golden-style synthetic fixtures).

Covers the failure classes the route was built to kill:
- chunk cuts landing mid-word (silence-aligned chunking contract)
- frozen seams shipping silently (still-span QC gate)
- white-eye hallucinations shipping silently (pupil QC gate)
- Phase B ``running`` state wedging busy UI after restart (orphan sweep)
"""
from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest

import phase_b_path_a_pipeline as pipe

TOOLS = Path(__file__).resolve().parent.parent
PHASES = TOOLS / "server_handlers" / "phases.py"


def _handler_block() -> str:
    block = PHASES.read_text(encoding="utf-8").split("def handle_phase_b_lipsync", 1)[1]
    return block.split("\ndef _finalize_phase_a_lipsync_delivery", 1)[0]


# ---------------------------------------------------------------------------
# Route wiring contracts
# ---------------------------------------------------------------------------

def test_handler_block_is_path_a_single_route():
    block = _handler_block()
    assert "PHASE_B_PATH_A_ROUTE_V1" in block
    assert "execute_layered_job" in block
    assert "create_layered_job" in block
    assert "validate_path_a_assets" in block
    # single route: the duration fork and whole-frame submits are gone
    assert "LIPSYNC_SINGLE_PASS_MAX_S" not in block
    assert "run_phase_b_kling_segmented_lipsync" not in block
    assert "submit_avatar_pro" not in block


def test_handler_budget_gate_is_per_chunk():
    block = _handler_block()
    assert "plan_layered_lipsync" in block
    assert "COST_PER_LIPSYNC * chunk_jobs" in block
    assert "_apply_phase_audio_trim" in block
    assert "_apply_phase_lipsync_audio_prep(" not in block


def test_handler_terminal_writer_unchanged():
    # Delivery profile contract: bake re-encodes unless the shared terminal
    # writer (voice_first_upscale) runs.
    block = _handler_block()
    assert "_write_phase_b_lipsync_complete" in block


def test_orphan_sweep_wired_into_polling_thread():
    server = (TOOLS / "production_server.py").read_text(encoding="utf-8")
    assert "sweep_phase_b_lipsync_orphan" in server
    assert "reconcile_phase_b_layered_lipsync" in server


def test_reject_clears_running_shape_keys():
    import server_handlers.phases as phases

    for key in (
        "lipsync_pending_output",
        "lipsync_pending_audio",
        "lipsync_started_at",
        "lipsync_job_id",
        "lipsync_manifest_file",
    ):
        assert key in phases._PHASE_LIPSYNC_DERIVED_KEYS


# ---------------------------------------------------------------------------
# Synthetic media fixtures
# ---------------------------------------------------------------------------

def _make_audio_with_silences(dest: Path) -> None:
    """60s: tone 0-25s, silence 25-27s, tone 27-58s, silence 58-60s."""
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi",
         "-i", (
             "sine=frequency=440:duration=60,"
             "volume=0:enable='between(t,25,27)+between(t,58,60)'"
         ),
         "-c:a", "libmp3lame", "-q:a", "4", str(dest)],
        check=True, timeout=120,
    )


def _make_motion_clip(dest: Path, seconds: float) -> None:
    """Per-frame random noise — constant high motion."""
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", f"nullsrc=s=200x200:r=12:d={seconds}",
         "-vf", "geq=lum='random(1)*255':cb=128:cr=128",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(dest)],
        check=True, timeout=120,
    )


def _make_freeze_sandwich(dest: Path, tmp: Path) -> None:
    """3s motion + 3s frozen frame + 3s motion at 200x200/12fps."""
    a, b, c = tmp / "a.mp4", tmp / "b.mp4", tmp / "c.mp4"
    _make_motion_clip(a, 3)
    _make_motion_clip(c, 3)
    still = tmp / "still.png"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(a), "-frames:v", "1", str(still)],
        check=True, timeout=60,
    )
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-loop", "1", "-i", str(still),
         "-t", "3", "-r", "12", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(b)],
        check=True, timeout=60,
    )
    lst = tmp / "concat.txt"
    lst.write_text(f"file '{a.name}'\nfile '{b.name}'\nfile '{c.name}'\n")
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
         "-i", str(lst), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "12",
         str(dest)],
        check=True, timeout=120,
    )


def _make_eye_band_clip(dest: Path, *, white_span: bool) -> None:
    """832x464 clip with eye detail; optionally a 3s white span."""
    if white_span:
        # frames 48-84 at 12fps = 4-7s (geq has N, not t; escape commas)
        vf = (
            r"geq=lum=if(between(N\,48\,84)\,235\,"
            r"50+20*sin(X)):cb=128:cr=128"
        )
    else:
        # Non-uniform dark detail avoids the fail-closed all-dark crop guard.
        vf = "geq=lum='50+20*sin(X)':cb=128:cr=128"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", "nullsrc=s=832x464:r=12:d=12",
         "-vf", vf,
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(dest)],
        check=True, timeout=120,
    )


# ---------------------------------------------------------------------------
# Chunking behavior
# ---------------------------------------------------------------------------

def test_chunk_boundaries_land_in_silence(tmp_path: Path):
    stem = tmp_path / "stem.mp3"
    _make_audio_with_silences(stem)
    cuts = pipe.detect_chunk_boundaries(stem, max_chunk=50.0)
    assert cuts, "60s stem over 50s max must produce at least one cut"
    # every cut sits inside the authored 25-27s silence (only silence <50s in)
    assert all(24.5 <= c <= 27.5 for c in cuts), cuts
    # chunk-size contract
    bounds = [0.0, *cuts, pipe.ffprobe_duration(stem)]
    sizes = [b - a for a, b in zip(bounds, bounds[1:])]
    assert all(s <= 50.0 + 0.5 for s in sizes), sizes


def test_chunk_count_matches_cuts(tmp_path: Path):
    stem = tmp_path / "stem.mp3"
    _make_audio_with_silences(stem)
    n = pipe.count_phase_b_path_a_chunks(stem, max_chunk=50.0)
    cuts = pipe.detect_chunk_boundaries(stem, max_chunk=50.0)
    assert n == len(cuts) + 1


def test_short_stem_is_single_chunk(tmp_path: Path):
    stem = tmp_path / "short.mp3"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
         "-i", "sine=frequency=440:duration=20",
         "-c:a", "libmp3lame", "-q:a", "4", str(stem)],
        check=True, timeout=60,
    )
    assert pipe.count_phase_b_path_a_chunks(stem, max_chunk=50.0) == 1


# ---------------------------------------------------------------------------
# QC gates behavior
# ---------------------------------------------------------------------------

def test_still_scan_catches_frozen_span(tmp_path: Path):
    clip = tmp_path / "sandwich.mp4"
    _make_freeze_sandwich(clip, tmp_path)
    spans = pipe.qc_still_scan(clip, crop="100:100:50:50")
    assert spans, "3s frozen span must be detected"
    start, dur = spans[0]
    assert 2.0 <= start <= 4.0 and dur >= 2.0, spans


def test_still_scan_passes_moving_clip(tmp_path: Path):
    clip = tmp_path / "motion.mp4"
    _make_motion_clip(clip, 9)
    assert pipe.qc_still_scan(clip, crop="100:100:50:50") == []


def test_pupil_scan_catches_white_eye_span(tmp_path: Path):
    clip = tmp_path / "white.mp4"
    _make_eye_band_clip(clip, white_span=True)
    spans = pipe.qc_pupil_scan(clip)
    assert spans, "white-eye span must be detected"
    start, end = spans[0]
    assert 3.0 <= start <= 5.0 and end >= 6.0, spans


def test_pupil_scan_passes_dark_pupils(tmp_path: Path):
    clip = tmp_path / "dark.mp4"
    _make_eye_band_clip(clip, white_span=False)
    assert pipe.qc_pupil_scan(clip) == []


# ---------------------------------------------------------------------------
# Orphan sweep behavior
# ---------------------------------------------------------------------------

class _FakeStateMgr:
    def __init__(self, state: dict):
        self._state = dict(state)
        self.mutations = 0

    def read_state(self) -> dict:
        return dict(self._state)

    def mutate_state(self, fn):
        self.mutations += 1
        fn(self._state)
        return self._state.get("_module_version", 0)


@pytest.fixture()
def _no_worker(monkeypatch: pytest.MonkeyPatch):
    import server_handlers.phases as phases

    monkeypatch.setattr(phases, "_phase_a_lipsync_worker", None)
    return phases


def test_orphan_sweep_clears_dead_running(_no_worker):
    phases = _no_worker
    mgr = _FakeStateMgr({
        "phase_b_lipsync_status": "running",
        "phase_b_lipsync_started_at": time.time() - 3600,
        "phase_b_lipsync_pending_output": "x.mp4",
        "phase_b_lipsync_pending_audio": "x.mp3",
    })
    phases.sweep_phase_b_lipsync_orphan(mgr)
    snap = mgr.read_state()
    assert snap["phase_b_lipsync_status"].startswith("error: orphan_restart")
    assert "phase_b_lipsync_pending_output" not in snap
    assert "phase_b_lipsync_pending_audio" not in snap
    assert "phase_b_lipsync_started_at" not in snap


def test_orphan_sweep_respects_grace_window(_no_worker):
    phases = _no_worker
    mgr = _FakeStateMgr({
        "phase_b_lipsync_status": "running",
        "phase_b_lipsync_started_at": time.time() - 10,
    })
    phases.sweep_phase_b_lipsync_orphan(mgr)
    assert mgr.read_state()["phase_b_lipsync_status"] == "running"
    assert mgr.mutations == 0


def test_orphan_sweep_ignores_terminal_states(_no_worker):
    phases = _no_worker
    for status in ("done", "polling", "error: x", None):
        mgr = _FakeStateMgr({"phase_b_lipsync_status": status})
        phases.sweep_phase_b_lipsync_orphan(mgr)
        assert mgr.mutations == 0


def test_orphan_sweep_leaves_alive_worker_alone(monkeypatch: pytest.MonkeyPatch):
    import server_handlers.phases as phases
    from layered_lipsync_jobs import ModuleLipsyncWorkerOwner

    class _AliveThread:
        @staticmethod
        def is_alive() -> bool:
            return True

    owner = ModuleLipsyncWorkerOwner(
        phase="b",
        event_instance_id="instance",
        event_dir=Path("/tmp/Event_3"),
        event_generation=1,
        job_id="job-alive",
        server_instance_id="server",
    )
    monkeypatch.setattr(phases, "_module_lipsync_worker", _AliveThread())
    monkeypatch.setattr(phases, "_module_lipsync_worker_owner", owner)
    mgr = _FakeStateMgr({
        "phase_b_lipsync_status": "running",
        "phase_b_lipsync_started_at": time.time() - 1800,
    })
    mgr.event_dir = Path("/tmp/Event_3")
    phases.sweep_phase_b_lipsync_orphan(mgr)
    assert mgr.read_state()["phase_b_lipsync_status"] == "running"


def test_orphan_sweep_stale_guard_for_hung_worker(monkeypatch: pytest.MonkeyPatch):
    import server_handlers.phases as phases
    from layered_lipsync_jobs import ModuleLipsyncWorkerOwner

    class _AliveThread:
        @staticmethod
        def is_alive() -> bool:
            return True

    owner = ModuleLipsyncWorkerOwner(
        phase="b",
        event_instance_id="instance",
        event_dir=Path("/tmp/Event_3"),
        event_generation=1,
        job_id="job-stale",
        server_instance_id="server",
    )
    monkeypatch.setattr(phases, "_module_lipsync_worker", _AliveThread())
    monkeypatch.setattr(phases, "_module_lipsync_worker_owner", owner)
    mgr = _FakeStateMgr({
        "phase_b_lipsync_status": "running",
        "phase_b_lipsync_started_at": time.time() - 7200,
    })
    mgr.event_dir = Path("/tmp/Event_3")
    phases.sweep_phase_b_lipsync_orphan(mgr)
    assert mgr.read_state()["phase_b_lipsync_status"].startswith("error: stale_timeout")


# ---------------------------------------------------------------------------
# Asset preconditions (runs on Kim's machine where Dropbox is mounted)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not pipe.DROPBOX_PRODUCTION.exists(),
    reason="Dropbox Production not mounted",
)
def test_path_a_canonical_assets_exist():
    pipe.validate_path_a_assets()


def test_qc_error_is_runtime_error():
    # handler error-write formats the type name into the status string
    assert issubclass(pipe.PhaseBPathAQCError, RuntimeError)
