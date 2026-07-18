"""BG_EXPORT_DIRECTUS_AFTER_DONE_V1 — Directus must not gate terminal export done."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from bg_export_stitcher_job_store import create_job, load_job, new_job_id


def test_core_returns_deferred_directus_without_register_call() -> None:
    """Source contract: core ok path defers Directus; register lives after done."""
    tools = Path(__file__).resolve().parent.parent
    src = (tools / "server_handlers" / "kling_o3.py").read_text(encoding="utf-8")
    core = src.split("def _run_bg_export_to_stitcher_core", 1)[1].split(
        "\ndef _run_bg_export_directus_after_done", 1
    )[0]
    after = src.split("def _run_bg_export_directus_after_done", 1)[1].split(
        "\ndef _execute_bg_export_to_stitcher_job", 1
    )[0]
    worker = src.split("def _execute_bg_export_to_stitcher_job", 1)[1].split(
        "\ndef handle_bg_export_to_stitcher_preflight", 1
    )[0]
    assert "BG_EXPORT_DIRECTUS_AFTER_DONE_V1" in core
    assert '"deferred": True' in core or "'deferred': True" in core
    assert "register_bg_export_to_directus" not in core
    assert "preserve_kling_o3_segment_beats" in core
    assert "register_bg_export_to_directus" in after
    assert "finalize_job" in worker
    # done before Directus
    done_idx = worker.find('finalize_job(store_dir, job_id, "done"')
    directus_idx = worker.find("_run_bg_export_directus_after_done")
    assert done_idx >= 0 and directus_idx >= 0
    assert done_idx < directus_idx


def test_finalize_done_survives_directus_raise(tmp_path: Path) -> None:
    """Worker: Directus raise after done must leave job status done."""
    from server_handlers import kling_o3 as ko3

    job_id = new_job_id()
    create_job(
        tmp_path,
        job_id=job_id,
        scope_key="1|6|pre|intro",
        scope_event_id="Event_6",
        arc_number=1,
        bg_event_id="6",
        phase="pre",
        slot_key="intro",
        beat_ids=["b1"],
        pin={"pinned_generation": 1, "pinned_event_dir": str(tmp_path)},
    )
    lock_path = tmp_path / "export.lock"
    lock_path.write_text("", encoding="utf-8")

    h = MagicMock()
    h.app.event_dir = tmp_path
    ctx = {
        "data_dir": str(tmp_path),
        "arc_number": 1,
        "bg_event_id": "6",
        "phase": "pre",
        "slot_key": "intro",
        "beat_ids": ["b1"],
    }
    pin = {"pinned_generation": 1, "pinned_event_dir": str(tmp_path)}
    deferred = {
        "arc_number": 1,
        "event_id": "6",
        "phase": "pre",
        "slot_key": "intro",
        "video_rel": "assembled/intro.mp4",
        "out_path": str(tmp_path / "assembled" / "intro.mp4"),
        "boundaries": [],
        "duration_s": 1.0,
        "beat_ids": ["b1"],
    }
    ok_result = {
        "ok": True,
        "slot_key": "intro",
        "video_path": "assembled/intro.mp4",
        "warnings": [],
        "_deferred_directus": deferred,
        "directus": {"deferred": True, "code": "BG_EXPORT_DIRECTUS_AFTER_DONE_V1"},
    }

    with (
        patch.object(ko3, "_run_bg_export_to_stitcher_core", return_value=ok_result),
        patch.object(
            ko3,
            "_run_bg_export_directus_after_done",
            side_effect=RuntimeError("directus hang"),
        ),
        patch("beatgen_scope.run_in_beatgen_scope", side_effect=lambda app, bg, fn: fn()),
        patch.object(ko3, "_bg", return_value=MagicMock()),
    ):
        ko3._execute_bg_export_to_stitcher_job(
            h,
            job_id=job_id,
            scope_key="1|6|pre|intro",
            ctx=ctx,
            pin=pin,
            lock_path=lock_path,
        )

    job = load_job(tmp_path, job_id)
    assert job is not None
    assert job["status"] == "done"
    assert job["phase"] == "done"
    result = job.get("result") or {}
    assert result.get("ok") is True
    assert result.get("directus", {}).get("ran_after_done") is False
    assert "Directus after done failed" in " ".join(result.get("warnings") or [])


def test_marker_present_in_worker_and_core() -> None:
    tools = Path(__file__).resolve().parent.parent
    src = (tools / "server_handlers" / "kling_o3.py").read_text(encoding="utf-8")
    assert "BG_EXPORT_DIRECTUS_AFTER_DONE_V1" in src
    assert src.count("BG_EXPORT_DIRECTUS_AFTER_DONE_V1") >= 2
