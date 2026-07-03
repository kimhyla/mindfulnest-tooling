"""O3_JOB_TRUTH_STACK_V1 — 12-case parametrized truth matrix (Phase 1)."""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest import mock

import pytest
from o3_generation_intent import write_intent_terminal
from o3_job_truth import O3_JOB_TRUTH_STACK_V1, resolve_beat_o3_truth

BEAT_ID = "bg_arc1_event4_pre_beat_15"


def _fixture_dirs(tmp: str) -> tuple[Path, Path, Path]:
    event_dir = Path(tmp)
    (event_dir / "arlo_o3_jobs").mkdir()
    clips = event_dir / "kling_o3_clips"
    clips.mkdir()
    return event_dir, clips, clips / f"{BEAT_ID}_g3_element_o3_master_delivery.mp4"


def _resolve(
    event_dir: Path,
    beat: dict,
    *,
    orphan_preview: bool = False,
    busy: bool | None = None,
) -> dict:
    kwargs = {
        "sidecar": {},
        "orphan_preview": orphan_preview,
    }
    if busy is None:
        return resolve_beat_o3_truth(BEAT_ID, event_dir, beat, **kwargs)
    with mock.patch(
        "o3_job_status_contract.beat_o3_operator_busy",
        return_value=busy,
    ):
        return resolve_beat_o3_truth(BEAT_ID, event_dir, beat, **kwargs)


@pytest.mark.parametrize(
    "case_id,beat_factory,terminal_factory,expect,use_busy_mock",
    [
        (
            "terminal_failed_restores_g3",
            lambda g3, jid: {
                "beat_id": BEAT_ID,
                "status": "o3_element_running",
                "kling_o3_status": "submitted",
                "kling_o3_voice_fix_status": "o3_element_running",
                "kling_o3_generation": 4,
                "o3_current_job_id": jid,
                "kling_o3_options": [{"key": "g3", "video_path": str(g3), "generation": 3}],
            },
            lambda ev, jid: write_intent_terminal(
                jid,
                ev,
                {
                    "schema_version": 1,
                    "job_id": jid,
                    "beat_id": BEAT_ID,
                    "status": "failed",
                    "failure": {"message": "ended without terminal"},
                },
            ),
            {"terminal_status": "failed", "kling_status": "approved", "video_exists": True},
            False,
        ),
        (
            "terminal_done_with_video",
            lambda g3, jid: {
                "beat_id": BEAT_ID,
                "kling_o3_status": "submitted",
                "o3_current_job_id": jid,
                "kling_o3_video_path": str(g3),
                "kling_o3_options": [{"key": "g3", "video_path": str(g3), "generation": 3}],
            },
            lambda ev, jid: write_intent_terminal(
                jid,
                ev,
                {
                    "schema_version": 1,
                    "job_id": jid,
                    "beat_id": BEAT_ID,
                    "status": "done",
                    "delivered": {"video_path": str(ev / "kling_o3_clips" / f"{BEAT_ID}_g3_element_o3_master_delivery.mp4")},
                },
            ),
            {"terminal_status": "done", "video_exists": True},
            False,
        ),
        (
            "terminal_cancelled",
            lambda _g3, jid: {
                "beat_id": BEAT_ID,
                "kling_o3_status": "submitted",
                "o3_current_job_id": jid,
            },
            lambda ev, jid: write_intent_terminal(
                jid,
                ev,
                {"schema_version": 1, "job_id": jid, "beat_id": BEAT_ID, "status": "cancelled"},
            ),
            {"terminal_status": "cancelled"},
            False,
        ),
        (
            "sidecar_approved_disk_only",
            lambda g3, _jid: {
                "beat_id": BEAT_ID,
                "kling_o3_status": "approved",
                "kling_o3_voice_fix_status": "approved",
                "kling_o3_video_path": str(g3),
                "kling_o3_generation": 3,
            },
            lambda _ev, _jid: None,
            {"kling_status": "approved", "video_exists": True},
            False,
        ),
        (
            "terminal_failed_no_prior",
            lambda _g3, jid: {
                "beat_id": BEAT_ID,
                "kling_o3_status": "submitted",
                "kling_o3_generation": 4,
                "o3_current_job_id": jid,
                "kling_o3_options": [],
            },
            lambda ev, jid: write_intent_terminal(
                jid,
                ev,
                {
                    "schema_version": 1,
                    "job_id": jid,
                    "beat_id": BEAT_ID,
                    "status": "failed",
                    "failure": {"message": "no prior"},
                },
            ),
            {"terminal_status": "failed"},
            False,
        ),
        (
            "orphan_preview_heals_in_memory",
            lambda g3, jid: {
                "beat_id": BEAT_ID,
                "kling_o3_status": "submitted",
                "kling_o3_generation": 4,
                "o3_current_job_id": jid,
                "kling_o3_options": [{"key": "g3", "video_path": str(g3), "generation": 3}],
            },
            lambda ev, jid: write_intent_terminal(
                jid,
                ev,
                {
                    "schema_version": 1,
                    "job_id": jid,
                    "beat_id": BEAT_ID,
                    "status": "failed",
                    "failure": {"message": "orphan"},
                },
            ),
            {"kling_status": "approved", "video_exists": True},
            False,
        ),
        (
            "submitted_sidecar_disk_path",
            lambda g3, _jid: {
                "beat_id": BEAT_ID,
                "kling_o3_status": "submitted",
                "kling_o3_voice_fix_status": "o3_element_running",
                "kling_o3_video_path": str(g3),
            },
            lambda _ev, _jid: None,
            {"video_exists": True},
            False,
        ),
        (
            "terminal_message_preserved",
            lambda _g3, jid: {
                "beat_id": BEAT_ID,
                "o3_current_job_id": jid,
                "kling_o3_status": "submitted",
            },
            lambda ev, jid: write_intent_terminal(
                jid,
                ev,
                {
                    "schema_version": 1,
                    "job_id": jid,
                    "beat_id": BEAT_ID,
                    "status": "failed",
                    "failure": {"message": "explicit failure msg"},
                },
            ),
            {"terminal_message": "explicit failure msg"},
            False,
        ),
        (
            "generation_healed_to_g3",
            lambda g3, jid: {
                "beat_id": BEAT_ID,
                "kling_o3_status": "submitted",
                "kling_o3_generation": 4,
                "o3_current_job_id": jid,
                "kling_o3_options": [{"key": "g3", "video_path": str(g3), "generation": 3}],
            },
            lambda ev, jid: write_intent_terminal(
                jid,
                ev,
                {
                    "schema_version": 1,
                    "job_id": jid,
                    "beat_id": BEAT_ID,
                    "status": "failed",
                    "failure": {"message": "g4 fail"},
                },
            ),
            {"generation": 3},
            False,
        ),
        (
            "voice_fix_approved_after_heal",
            lambda g3, jid: {
                "beat_id": BEAT_ID,
                "kling_o3_status": "submitted",
                "kling_o3_generation": 4,
                "o3_current_job_id": jid,
                "kling_o3_options": [{"key": "g3", "video_path": str(g3), "generation": 3}],
            },
            lambda ev, jid: write_intent_terminal(
                jid,
                ev,
                {
                    "schema_version": 1,
                    "job_id": jid,
                    "beat_id": BEAT_ID,
                    "status": "failed",
                    "failure": {"message": "heal"},
                },
            ),
            {"voice_fix": "approved"},
            False,
        ),
        (
            "options_nonempty_after_heal",
            lambda g3, jid: {
                "beat_id": BEAT_ID,
                "kling_o3_status": "submitted",
                "kling_o3_generation": 4,
                "o3_current_job_id": jid,
                "kling_o3_options": [{"key": "g3", "video_path": str(g3), "generation": 3}],
            },
            lambda ev, jid: write_intent_terminal(
                jid,
                ev,
                {
                    "schema_version": 1,
                    "job_id": jid,
                    "beat_id": BEAT_ID,
                    "status": "failed",
                    "failure": {"message": "opts"},
                },
            ),
            {"options_len_ge": 1},
            False,
        ),
        (
            "running_terminal_busy",
            lambda _g3, jid: {
                "beat_id": BEAT_ID,
                "status": "o3_element_running",
                "kling_o3_status": "submitted",
                "o3_current_job_id": jid,
                "kling_o3_voice_fix_status": "o3_element_running",
            },
            lambda ev, jid: write_intent_terminal(
                jid,
                ev,
                {"schema_version": 1, "job_id": jid, "beat_id": BEAT_ID, "status": "running"},
            ),
            {"terminal_status": "running", "busy": True},
            True,
        ),
    ],
)
def test_o3_job_truth_matrix(
    case_id: str,
    beat_factory,
    terminal_factory,
    expect,
    use_busy_mock: bool,
) -> None:
    job_id = f"matrix-{case_id}"
    with tempfile.TemporaryDirectory() as tmp:
        event_dir, _clips, g3 = _fixture_dirs(tmp)
        g3.write_bytes(b"g3-bytes")
        beat = beat_factory(g3, job_id)
        terminal_factory(event_dir, job_id)
        orphan = case_id == "orphan_preview_heals_in_memory"
        busy = expect.get("busy") if use_busy_mock else False if "busy" not in expect else None
        truth = _resolve(event_dir, beat, orphan_preview=orphan, busy=busy)

        assert truth["authority"] == O3_JOB_TRUTH_STACK_V1
        if "terminal_status" in expect:
            assert truth["terminal_status"] == expect["terminal_status"]
        if "terminal_message" in expect:
            assert expect["terminal_message"] in truth["terminal_message"]
        if "kling_status" in expect:
            assert truth["kling_o3_status"] == expect["kling_status"]
        if "voice_fix" in expect:
            assert truth["kling_o3_voice_fix_status"] == expect["voice_fix"]
        if "video_exists" in expect:
            assert truth["video_path_exists"] is expect["video_exists"]
        if "busy" in expect:
            assert truth["operator_busy"] is expect["busy"]
        if "generation" in expect:
            assert truth["reconciled_beat"]["kling_o3_generation"] == expect["generation"]
        if "options_len_ge" in expect:
            assert len(truth["kling_o3_options"]) >= expect["options_len_ge"]
