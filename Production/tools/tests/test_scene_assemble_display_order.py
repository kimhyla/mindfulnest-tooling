"""SCENE_ASSEMBLE_DISPLAY_ORDER_V1 — legacy int display_order must not 500."""
from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_helper():
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("production_server", root / "production_server.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod._partition_display_order_list


def test_partition_display_order_list_accepts_list():
    fn = _load_helper()
    assert fn({"display_order": ["beat_01", "beat_02"]}) == ["beat_01", "beat_02"]


def test_partition_display_order_list_rejects_legacy_int():
    fn = _load_helper()
    assert fn({"display_order": 1}) == []
    assert fn({"display_order": 2}) == []


def test_partition_display_order_list_missing_key():
    fn = _load_helper()
    assert fn({}) == []
    assert fn(None) == []
