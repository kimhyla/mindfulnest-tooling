"""STITCH_SAVE_ASYNC_ARTIFACTS_V1 — save_job must not block on ambient ffmpeg."""

from __future__ import annotations

import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))


def test_save_job_uses_fast_defaults_without_ambient_inject() -> None:
    src = (TOOLS / "server_handlers/stitch_editor.py").read_text(encoding="utf-8")
    block = src.split("def handle_stitch_save_job", 1)[1].split("\ndef handle_stitch_delete_job", 1)[0]
    assert "fast=True" in block
    assert "apply_ambient_presets=bool(body.get(\"apply_canonical_defaults\"))" in block
    assert "rebuild_stitch_ambient_mixes_for_job" not in block
    assert "submit_stitch_ambient_rebuild" in block
    assert "STITCH_SAVE_ASYNC_ARTIFACTS_V1" in block


def test_load_job_surfaces_active_artifact_build() -> None:
    src = (TOOLS / "server_handlers/stitch_editor.py").read_text(encoding="utf-8")
    block = src.split("def handle_stitch_load_job", 1)[1].split(
        "\ndef handle_stitch_serve_module_final", 1,
    )[0]
    assert "find_active_build_for_stitch_job" in block
    assert "artifact_build" in block


def test_artifact_build_module_exports_marker() -> None:
    from server_handlers.stitch_artifact_build import (  # noqa: E402
        STITCH_SAVE_ASYNC_ARTIFACTS_V1,
        submit_stitch_ambient_rebuild,
    )

    assert STITCH_SAVE_ASYNC_ARTIFACTS_V1
    assert callable(submit_stitch_ambient_rebuild)


def test_ensure_job_slot_defaults_respects_apply_ambient_presets_flag() -> None:
    src = (TOOLS / "server_handlers/stitch_editor.py").read_text(encoding="utf-8")
    block = src.split("def ensure_job_slot_defaults", 1)[1].split("\ndef collect_stitch_job_slot_warnings", 1)[0]
    assert "apply_ambient_presets" in block
    assert "apply_ambient_presets and apply_stitch_slot_default_ambient_preset" in block
