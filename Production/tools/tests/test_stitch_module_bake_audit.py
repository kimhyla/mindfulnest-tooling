"""STITCH_MODULE_BAKE_AUDIT_V1 — final module bake must leave stdout + JSONL forensics."""

from __future__ import annotations

import json
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]


def test_stitch_module_bake_audit_helper_writes_jsonl(tmp_path: Path) -> None:
    from server_handlers import stitch_editor as se

    class _App:
        event_dir = tmp_path

    class _H:
        app = _App()

    se._stitch_module_bake_audit(
        _H(),
        "BAKE_REQUEST",
        stitch_job_name="Event_4_stitch",
        scope_video_role="resolution",
    )
    log_path = tmp_path / "_stitch_module_bake_audit.jsonl"
    assert log_path.is_file()
    row = json.loads(log_path.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert row["event"] == "BAKE_REQUEST"
    assert row["code"] == se.STITCH_MODULE_BAKE_AUDIT_V1
    assert row["stitch_job_name"] == "Event_4_stitch"


def test_bake_core_and_worker_emit_audit_events() -> None:
    src = (TOOLS / "server_handlers" / "stitch_editor.py").read_text(encoding="utf-8")
    assert "_stitch_module_bake_audit" in src
    assert "STITCH_MODULE_BAKE_AUDIT_V1" in src
    bake_block = src.split("def _run_stitch_bake_core", 1)[1].split("\ndef _execute_stitch_bake_job", 1)[0]
    for event in (
        "BAKE_CORE_START",
        "SLOT_CONTEXT",
        "PIPELINE_START",
        "PIPELINE_OK",
        "PIPELINE_FAIL",
        "ENCODE_START",
        "BAKE_OK",
    ):
        assert event in bake_block
    worker_block = src.split("def _execute_stitch_bake_job", 1)[1].split("\ndef handle_stitch_bake", 1)[0]
    assert "BAKE_JOB_START" in worker_block
    assert "BAKE_EXCEPTION" in worker_block
    handle_block = src.split("def handle_stitch_bake", 1)[1].split("\ndef handle_stitch_bake_status", 1)[0]
    assert "BAKE_REQUEST" in handle_block


def test_stitcher_tab_surfaces_latest_terminal_bake_failure() -> None:
    src = (TOOLS / "storyboard-v2" / "src" / "components" / "StitcherTab.tsx").read_text(
        encoding="utf-8",
    )
    assert "bakeJob.latest_terminal" in src
    assert "stitchBakeTerminalErrorLine" in src
    assert "_stitch_module_bake_audit.jsonl" in src
    assert "stitch_module_bake_audit_client" in src


def test_boundary_sfx_overlay_trims_audio_to_video_duration() -> None:
    src = (TOOLS / "production_server.py").read_text(encoding="utf-8")
    block = src.split("def _stitch_overlay_sfx_on_clip", 1)[1].split("\n    def _stitch_apply_canonical_boundary_sfx", 1)[0]
    assert "ffprobe_stream_duration_s" in block
    assert "apad=whole_dur=" in block
    assert "STITCH_EXPORT_TIMELINE_AUTHORITY_V1" in block
    assert "remux_mp4_video_timeline_authority" in block
    assert "STITCH_EXPORT_NORM_AV_MAX_DRIFT_S" in block
