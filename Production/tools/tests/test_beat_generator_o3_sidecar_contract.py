"""Static contract: beat_generator must export O3 sidecar lock API at import time."""

from __future__ import annotations

import importlib


def test_beat_generator_exports_o3_sidecar_api() -> None:
    bg = importlib.import_module("beat_generator")
    assert callable(getattr(bg, "update_beat_locked", None)), "update_beat_locked"
    assert callable(getattr(bg, "sidecar_file_lock", None)), "sidecar_file_lock"
    assert callable(getattr(bg, "stash_prior_kling_o3_before_redo", None)), "stash_prior_kling_o3_before_redo"


def test_probe_capabilities_reports_o3_sidecar_api() -> None:
    bg = importlib.import_module("beat_generator")
    caps = bg.probe_capabilities()
    assert caps.get("update_beat_locked") is True
    assert caps.get("sidecar_file_lock") is True
