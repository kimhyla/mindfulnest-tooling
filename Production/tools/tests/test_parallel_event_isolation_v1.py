"""PARALLEL_EVENT_ISOLATION_V1 — per-event local mirror + scoped startup reconcile."""
from __future__ import annotations

from pathlib import Path

import pytest

import beat_generator as bg
from server_handlers import background as shbg


def test_event_sidecar_mirror_path_defaults_local(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("MN_SIDECAR_MIRROR_PATH", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    import sys

    repo_root = str(Path(__file__).resolve().parents[3])
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    from Production.lib.paths import event_sidecar_mirror_path

    p = event_sidecar_mirror_path("/tmp/Production/Event_11")
    assert p == tmp_path / ".mindfulnest" / "mirror" / "beatgen_event11.json"


def test_merge_skips_global_read_for_isolated_mirror(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(bg, "_PROD_DIR", str(tmp_path / "Production"))
    monkeypatch.setattr(bg, "_BG_EVENT_DIR", str(tmp_path / "Production" / "Event_3"))
    monkeypatch.setattr(bg, "_bootstrap_import_is_event_scoped", lambda: True)
    local_mirror = str(tmp_path / "mirror" / "beatgen_event3.json")
    data = {"arcs": {"a1": {"segments": {"event_3_pre": {"beats": []}}}}}
    out = bg._merge_event_scoped_mirror(data, local_mirror)
    assert out is data


def test_startup_reconcile_transient_detector() -> None:
    assert shbg._o3_startup_admin_reconcile_transient("[Errno 11] Resource deadlock avoided")
    assert shbg._o3_startup_admin_reconcile_transient("sidecar lock busy")
    assert not shbg._o3_startup_admin_reconcile_transient("ValueError: bad beat")


def test_run_blocking_o3_startup_uses_event_scoped_force_false(monkeypatch) -> None:
    calls: list[bool] = []

    def fake_reconcile(_h, _scope, *, force: bool = False) -> dict:
        calls.append(force)
        return {"ok": True, "counts": {}, "changed": 0}

    monkeypatch.setattr(shbg, "_run_o3_admin_reconcile", fake_reconcile)
    monkeypatch.setattr(shbg, "_data_root", lambda _h: Path("/tmp/Production"))

    import o3_generation_intent as o3i

    monkeypatch.setattr(o3i, "run_blocking_o3_startup_reconcile", lambda *_a, **_k: {"closed": 0, "errors": []})

    app = type("App", (), {"event_id": "3"})()
    shbg.run_blocking_o3_startup(app)
    assert calls == [False]
