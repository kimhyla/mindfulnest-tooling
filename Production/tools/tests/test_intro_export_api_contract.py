"""Intro export / Send-to-Stitcher API contract (static + handler wiring)."""
from __future__ import annotations

from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent


def test_export_route_registered_in_production_server() -> None:
    src = (TOOLS / "production_server.py").read_text(encoding="utf-8")
    assert 'path == "/api/bg/export-to-stitcher"' in src


def test_kling_o3_handler_exports_concat() -> None:
    src = (TOOLS / "server_handlers" / "kling_o3.py").read_text(encoding="utf-8")
    assert "def handle_bg_export_to_stitcher" in src
    assert "concat_kling_o3_approved_beats" in src


def test_endpoints_catalog_lists_export_to_stitcher() -> None:
    src = (TOOLS / "storyboard-v2" / "src" / "api" / "endpoints.ts").read_text(encoding="utf-8")
    assert "export-to-stitcher" in src or "export_to_stitcher" in src


def test_intro_export_applies_penultimate_fades_only() -> None:
    src = (TOOLS / "beat_generator.py").read_text(encoding="utf-8")
    assert "pre_penultimate_pair_fade_ms" in src
    assert "final_pair_fade_ms" in src


def test_job_store_module_present_for_export() -> None:
    assert (TOOLS / "bg_export_stitcher_job_store.py").is_file()


def test_poll_export_to_stitcher_route_registered() -> None:
    src = (TOOLS / "production_server.py").read_text(encoding="utf-8")
    assert 'path == "/api/bg/poll-export-to-stitcher"' in src
