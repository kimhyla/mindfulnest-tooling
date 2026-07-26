"""O3 poll must survive sidecar lock contention — never fail the job poll loop."""
from __future__ import annotations

import json
from pathlib import Path

import beat_generator as bg

SB_SRC = Path(__file__).resolve().parent.parent / "storyboard-v2" / "src"


def test_read_sidecar_for_poll_snapshot_falls_back_on_lock_timeout(monkeypatch, tmp_path) -> None:
    sidecar = tmp_path / "beat_generator_state.json"
    payload = {"arcs": {"arc_1": {"segments": {"event_2_pre": {"beats": []}}}}}
    sidecar.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(bg, "BG_SIDECAR_PATH", str(sidecar))

    class _CM:
        def __enter__(self):
            raise TimeoutError(f"sidecar lock timeout after 5s ({sidecar}.lock)")

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(bg, "sidecar_file_lock", lambda **kwargs: _CM())
    out = bg.read_sidecar_for_poll_snapshot(lock_timeout_s=0.01)
    assert out == payload


def test_enriched_poll_snapshot_uses_poll_read_helper() -> None:
    bg_src = Path(__file__).resolve().parent.parent / "server_handlers" / "background.py"
    block = bg_src.read_text(encoding="utf-8")
    snap_fn = block.split("def _enriched_beat_snapshot_for_o3_poll", 1)[1].split("\ndef ", 1)[0]
    assert "read_sidecar_for_poll_snapshot" in snap_fn
    assert "sidecar_file_lock(timeout_s=5)" not in snap_fn


def test_poll_payload_survives_snapshot_read_failure(monkeypatch, tmp_path) -> None:
    """Enriched snapshot failure must not drop status; minimal beat fallback is OK."""
    import importlib

    bg_mod = importlib.import_module("server_handlers.background")
    event_dir = tmp_path / "Event_2"
    event_dir.mkdir()

    def _boom(*_a, **_k):
        raise TimeoutError("sidecar lock timeout after 5s")

    monkeypatch.setattr(bg_mod, "_enriched_beat_snapshot_for_o3_poll", _boom)
    monkeypatch.setattr(
        bg_mod,
        "_minimal_sidecar_beat_for_o3_poll",
        lambda beat_id, _ed: {"beat_id": beat_id, "speaker": "Tessa"},
    )
    payload = {"status": "running", "beat_id": "bg_arc1_event2_pre_beat_06", "job_id": "abc12345"}
    out = bg_mod._o3_poll_payload_with_beat_snapshot(payload, event_dir)
    assert out["status"] == "running"
    assert out["beat"]["beat_id"] == "bg_arc1_event2_pre_beat_06"


def test_poll_payload_omits_beat_only_when_both_snapshots_fail(monkeypatch, tmp_path) -> None:
    import importlib

    bg_mod = importlib.import_module("server_handlers.background")
    event_dir = tmp_path / "Event_2"
    event_dir.mkdir()

    monkeypatch.setattr(
        bg_mod,
        "_enriched_beat_snapshot_for_o3_poll",
        lambda *_a, **_k: (_ for _ in ()).throw(TimeoutError("lock")),
    )
    monkeypatch.setattr(bg_mod, "_minimal_sidecar_beat_for_o3_poll", lambda *_a, **_k: None)
    payload = {"status": "running", "beat_id": "bg_arc1_event2_pre_beat_06", "job_id": "abc12345"}
    out = bg_mod._o3_poll_payload_with_beat_snapshot(payload, event_dir)
    assert out["status"] == "running"
    assert "beat" not in out


def test_ui_treats_sidecar_lock_timeout_as_transient_poll_blip() -> None:
    """Authority lives in bgPollHelpers + BgPollCoordinator (not BgTab.tsx text)."""
    helpers = (SB_SRC / "utils" / "bgPollHelpers.ts").read_text(encoding="utf-8")
    coord = (SB_SRC / "components" / "BgPollCoordinator.tsx").read_text(encoding="utf-8")
    assert "export function isSidecarLockPollBlip" in helpers
    assert "isSidecarLockPollBlip" in coord
    assert "isSidecarLockPollBlip(res)" in coord


def test_poll_handler_never_raises_on_snapshot_lock_timeout() -> None:
    src = (Path(__file__).resolve().parent.parent / "server_handlers" / "background.py").read_text(
        encoding="utf-8",
    )
    poll_block = src.split("def handle_bg_poll_arlo_o3_voice_status", 1)[1].split("\ndef ", 1)[0]
    assert "except TimeoutError as exc:" in poll_block
    assert "_o3_poll_payload_with_beat_snapshot(payload, event_dir)" in poll_block
    assert "return h._send_json(200, payload)" in poll_block


def test_read_sidecar_for_poll_snapshot_exported_in_capabilities() -> None:
    import importlib

    bg = importlib.import_module("beat_generator")
    assert bg.probe_capabilities().get("read_sidecar_for_poll_snapshot") is True
