"""Durable Phase A/B layered job contracts."""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS.parent))

import layered_character_lipsync as engine  # noqa: E402
import layered_lipsync_jobs as jobs  # noqa: E402


def _context(tmp_path: Path) -> jobs.CapturedEventContext:
    event_dir = tmp_path / "Production" / "Event_3"
    event_dir.mkdir(parents=True)
    return jobs.CapturedEventContext(
        production_root=event_dir.parent,
        event_dir=event_dir,
        folder_event_id="Event_3",
        state_event_id="M4E1",
        event_instance_id="instance-3",
        event_generation=7,
        video_role="intro",
    )


def _plan() -> engine.LayeredLipsyncPlan:
    return engine.LayeredLipsyncPlan(
        audio_duration=10.0,
        max_provider_seconds=50.0,
        boundary_pad_start=0.5,
        boundary_pad_end=0.5,
        raw_chunk_limit=49.0,
        cuts=(),
        chunk_durations=(10.0,),
        padded_chunk_durations=(11.0,),
    )


def _create(tmp_path: Path) -> tuple[Path, dict]:
    context = _context(tmp_path)
    source = context.event_dir / "source.mp3"
    prepared = context.event_dir / "prepared.mp3"
    source.write_bytes(b"source")
    prepared.write_bytes(b"prepared")
    return jobs.create_layered_job(
        context,
        engine.CEDRIC_PROFILE,
        source,
        prepared,
        _plan(),
        phase="b",
        output_name="phase_b_lipsync_test.mp4",
        terminal_status="done",
        base_clip_id="cedric",
        cost_per_chunk=0.35,
    )


def test_create_job_captures_immutable_event_and_audio(tmp_path: Path) -> None:
    path, job = _create(tmp_path)

    assert path.is_file()
    assert job["context"]["event_instance_id"] == "instance-3"
    assert job["context"]["event_generation"] == 7
    assert job["plan"]["raw_chunk_limit"] == 49.0
    assert job["plan"]["plan_sha256"] == _plan().plan_sha256
    assert Path(job["audio"]["prepared_file"]).read_bytes() == b"prepared"


def test_ambiguous_submit_is_durable_and_never_blindly_retried(
    tmp_path: Path,
    monkeypatch,
) -> None:
    path, _ = _create(tmp_path)

    def fake_prepare(_profile, plan, _audio, *, production_root, work_dir):
        work = Path(work_dir)
        (work / "chunk_0_audio.mp3").write_bytes(b"a")
        (work / "chunk_0_video.mp4").write_bytes(b"v")
        return engine.PreparedLayeredInputs(work, work / "idle.mp4", ("A",))

    monkeypatch.setattr(jobs, "prepare_layered_lipsync_inputs", fake_prepare)

    class UnknownClient:
        submits = 0

        def __init__(self, _key: str):
            pass

        def submit(self, *_args, **_kwargs):
            type(self).submits += 1
            raise TimeoutError("POST response lost")

    with pytest.raises(TimeoutError):
        jobs.execute_layered_job(
            path,
            engine.CEDRIC_PROFILE,
            api_key="offline",
            delivery_callback=lambda *_args: {},
            state_commit_callback=lambda *_args: None,
            client_factory=UnknownClient,
        )
    assert jobs.load_layered_job(path)["status"] == "submission_unknown"

    repeated = jobs.execute_layered_job(
        path,
        engine.CEDRIC_PROFILE,
        api_key="offline",
        delivery_callback=lambda *_args: {},
        state_commit_callback=lambda *_args: None,
        client_factory=UnknownClient,
    )
    assert repeated["status"] == "submission_unknown"
    assert UnknownClient.submits == 1


def test_restart_polls_known_task_charges_once_and_delivers(
    tmp_path: Path,
    monkeypatch,
) -> None:
    path, job = _create(tmp_path)
    artifacts = Path(job["audio"]["prepared_file"]).parent
    (artifacts / "chunk_0_lipsync.mp4").write_bytes(b"provider")

    def mark_submitted(value: dict) -> None:
        value["status"] = "running"
        value["stage"] = "provider_polling"
        value["idle_units"] = ["A"]
        value["chunks"][0].update(
            status="submitted",
            provider_task_id="task-known",
            provider_status="submitted",
            outputs=[],
        )

    jobs.mutate_layered_job(path, mark_submitted)

    class ResumeClient:
        submits = 0

        def __init__(self, _key: str):
            pass

        def submit(self, *_args, **_kwargs):
            type(self).submits += 1
            raise AssertionError("known task must not be resubmitted")

        def poll(self, task_id: str):
            assert task_id == "task-known"
            return {"status": "completed", "outputs": ["provider-url"]}

        def download(self, _url: str, destination: Path):
            destination.write_bytes(b"provider")

    build_video = artifacts / "build.mp4"
    build_video.write_bytes(b"build")
    monkeypatch.setattr(
        jobs,
        "build_layered_lipsync",
        lambda *_args, **_kwargs: engine.LayeredBuildResult(
            build_video,
            engine.sha256_file(build_video),
            _plan(),
            ("A",),
            {0: {"status": "completed", "task_id": "task-known", "outputs": ["u"]}},
        ),
    )

    committed: list[str] = []

    def delivery(source: Path, destination: Path, _job: dict) -> dict:
        shutil.copy2(source, destination)
        return {"delivery_recipe": "test"}

    result = jobs.execute_layered_job(
        path,
        engine.CEDRIC_PROFILE,
        api_key="offline",
        delivery_callback=delivery,
        state_commit_callback=lambda job, *_args: committed.append(job["job_id"]),
        client_factory=ResumeClient,
    )

    assert result["status"] == "done"
    assert ResumeClient.submits == 0
    assert committed == [job["job_id"]]
    ledger_rows = (
        Path(job["context"]["event_dir"]) / "spend_ledger.jsonl"
    ).read_text().splitlines()
    assert len(ledger_rows) == 1
    assert json.loads(ledger_rows[0])["task_id"] == "task-known"
    manifest = Path(job["context"]["event_dir"]) / "phase_b_lipsync_test.json"
    assert json.loads(manifest.read_text())["committed"] is True


def test_manifest_committed_job_resumes_state_only(
    tmp_path: Path,
) -> None:
    path, job = _create(tmp_path)
    output = Path(job["context"]["event_dir"]) / job["delivery"]["output_file"]
    output.write_bytes(b"delivered")
    digest = engine.sha256_file(output)
    output.with_suffix(".json").write_text(
        json.dumps(
            {
                "committed": True,
                "output_sha256": digest,
                "delivery_meta": {"delivery_recipe": "test"},
            }
        ),
        encoding="utf-8",
    )
    jobs.mutate_layered_job(
        path,
        lambda value: value.update(status="running", stage="manifest_committed"),
    )
    commits: list[str] = []

    result = jobs.execute_layered_job(
        path,
        engine.CEDRIC_PROFILE,
        api_key="offline",
        delivery_callback=lambda *_args: (_ for _ in ()).throw(
            AssertionError("delivery must not rerun")
        ),
        state_commit_callback=lambda value, *_args: commits.append(
            value["job_id"]
        ),
        client_factory=lambda _key: SimpleNamespace(),
    )

    assert result["status"] == "done"
    assert commits == [job["job_id"]]
