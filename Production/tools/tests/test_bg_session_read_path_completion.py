"""BG session read path — default GET must not persist (TECH_SPEC_BG_SESSION_READ_PATH_COMPLETION_v1)."""
from __future__ import annotations

import copy
import threading
import time
from pathlib import Path
from unittest.mock import patch

import beat_generator as bg
from server_handlers import background as bh

TOOLS = Path(__file__).resolve().parent.parent
BACKGROUND = TOOLS / "server_handlers" / "background.py"


def _handler_block(name: str) -> str:
    text = BACKGROUND.read_text(encoding="utf-8")
    start = text.index(f"def {name}(")
    rest = text[start + 1 :]
    end_offset = len(rest)
    for marker in ("\ndef handle_", "\ndef _finalize", "\ndef _run_o3"):
        idx = rest.find(marker)
        if idx >= 0:
            end_offset = min(end_offset, idx)
    return text[start : start + 1 + end_offset]


def test_handle_bg_session_state_read_only_no_compose_on_get():
    block = _handler_block("handle_bg_session_state")
    assert "_compose_o3_session_terminal_view(" not in block
    assert "Session GET is read-only for gallery" in block
    full = BACKGROUND.read_text(encoding="utf-8")
    assert "def _run_o3_terminal_reconcile_at_startup" in full


def test_compose_session_terminal_view_never_calls_mutate_sidecar(tmp_path: Path, monkeypatch):
    event_dir = tmp_path / "Event_3"
    clips = event_dir / "kling_o3_clips"
    clips.mkdir(parents=True)
    beat_id = "bg_arc1_event3_pre_beat_01"
    delivery = clips / f"{beat_id}_g1_element_o3_master_delivery.mp4"
    delivery.write_bytes(b"mp4")
    beat = {
        "beat_id": beat_id,
        "speaker": "Arlo",
        "kling_o3_options": [],
        "kling_o3_video_path": "",
        "o3_current_job_id": "jobcompose1",
    }
    jobs = event_dir / "arlo_o3_jobs"
    jobs.mkdir()
    (jobs / "jobcompose1_terminal.json").write_text(
        '{"status":"done","job_id":"jobcompose1"}',
        encoding="utf-8",
    )
    sidecar = {"arcs": {"1": {"segments": {"event_3_pre": {"beats": [copy.deepcopy(beat)]}}}}}
    beats = [copy.deepcopy(beat)]
    mutate_calls: list[float] = []

    def _track(*_a, **kwargs):
        mutate_calls.append(kwargs.get("timeout_s", 0))
        raise AssertionError("mutate_sidecar_locked must not run on compose path")

    monkeypatch.setattr(bg, "mutate_sidecar_locked", _track)
    monkeypatch.setattr(bg, "update_beat_locked", lambda *_a, **_k: (_ for _ in ()).throw(
        AssertionError("update_beat_locked must not run on compose path")
    ))

    from o3_session_terminal_reconcile import compose_session_terminal_view

    outcomes = compose_session_terminal_view(
        beats,
        sidecar,
        server_event_dir=event_dir,
        scope_type="event",
    )
    assert not mutate_calls
    assert beats[0].get("kling_o3_video_path")
    assert outcomes or beats[0].get("kling_o3_options")


def test_compose_path_replaces_apply_on_default_session_handler(tmp_path: Path, monkeypatch):
    event_dir = tmp_path / "Event_3"
    event_dir.mkdir()
    bg.init_bg_paths(event_dir, clear_milestone_scope=True)
    sidecar = bg.read_sidecar_for_poll_snapshot(lock_timeout_s=5)
    seg = bg.get_seg_entry(sidecar, 1, "3", "pre")
    beats = copy.deepcopy(seg.get("beats") or [])[:1]
    if not beats:
        beats = [{"beat_id": "bg_arc1_event3_pre_beat_01", "speaker": "Arlo"}]

    app = type("App", (), {
        "event_dir": event_dir,
        "event_id": "Event_3",
        "scope_type": "event",
        "milestone_library_event_dir": None,
    })()
    h = type("H", (), {"app": app})()

    mutate_calls: list[int] = []

    def _track(mutator, **kwargs):
        mutate_calls.append(1)
        sc = bg.read_sidecar()
        mutator(sc)
        bg.write_sidecar(sc)
        return sc

    with patch.object(bg, "mutate_sidecar_locked", side_effect=_track):
        bh._compose_o3_session_terminal_view(h, beats, sidecar)
    assert mutate_calls == []


def test_startup_reconcile_plans_outside_lock(monkeypatch, tmp_path: Path):
    event_dir = tmp_path / "Event_3"
    event_dir.mkdir()
    bg.init_bg_paths(event_dir, clear_milestone_scope=True)
    held_during_plan: list[bool] = []
    real_lock = bg._sidecar_lock

    def _plan_sidecar(*_a, **_k):
        held_during_plan.append(real_lock._is_owned())
        return None

    monkeypatch.setattr(bg, "_run_event_sidecar_reconcile_on_sidecar", _plan_sidecar)
    bg.reconcile_event_sidecar_after_milestone_exit(event_dir, "Event_3")
    assert held_during_plan == [False]


def test_parallel_session_get_under_lock_contention(tmp_path: Path, monkeypatch):
    """Category: GET must not queue behind a long writer — bounded read or fast complete."""
    event_dir = tmp_path / "Event_3"
    event_dir.mkdir()
    bg.init_bg_paths(event_dir, clear_milestone_scope=True)
    sidecar = bg.read_sidecar_for_poll_snapshot(lock_timeout_s=5)
    seg = bg.get_seg_entry(sidecar, 1, "3", "pre")
    beats = copy.deepcopy(seg.get("beats") or []) or [{"beat_id": "x"}]

    h = type("H", (), {
        "app": type("App", (), {
            "event_dir": event_dir,
            "scope_type": "event",
            "milestone_library_event_dir": None,
        })(),
    })()

    writer_done = threading.Event()

    def _slow_mutate(_mutator, **kwargs):
        time.sleep(0.05)
        writer_done.set()
        sc = bg.read_sidecar()
        _mutator(sc)
        bg.write_sidecar(sc)
        return sc

    errors: list[Exception] = []
    latencies: list[float] = []

    def _reader():
        t0 = time.monotonic()
        try:
            bh._compose_o3_session_terminal_view(h, copy.deepcopy(beats), sidecar)
        except Exception as exc:
            errors.append(exc)
        latencies.append(time.monotonic() - t0)

    with patch.object(bg, "mutate_sidecar_locked", side_effect=_slow_mutate):
        writer = threading.Thread(
            target=lambda: bg.mutate_sidecar_locked(lambda sc: None, timeout_s=5),
            daemon=True,
        )
        writer.start()
        threads = [threading.Thread(target=_reader, daemon=True) for _ in range(5)]
        for th in threads:
            th.start()
        for th in threads:
            th.join(timeout=3)
        writer.join(timeout=3)

    assert not errors
    assert all(lat < 2.0 for lat in latencies), latencies
