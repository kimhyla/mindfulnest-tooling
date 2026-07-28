"""Durable event-local jobs for Phase A/B layered lipsync."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from lib.atomic_json_write import atomic_json_write
from lib import fcntl_compat as fcntl
from lib.provider_spend import record_spend_once

from layered_character_lipsync import (
    LayeredBuildResult,
    LayeredLipsyncPlan,
    LayeredLipsyncProfile,
    PreparedLayeredInputs,
    atomic_deliver,
    build_layered_lipsync,
    prepare_layered_lipsync_inputs,
    sha256_file,
)

JOB_SCHEMA_VERSION = 1
TERMINAL_JOB_STATUSES = frozenset(
    {"done", "error", "submission_unknown", "cancelled"}
)


@dataclass(frozen=True)
class CapturedEventContext:
    production_root: Path
    event_dir: Path
    folder_event_id: str
    state_event_id: str
    event_instance_id: str
    event_generation: int
    video_role: str


@dataclass(frozen=True)
class ModuleLipsyncWorkerOwner:
    phase: str
    event_instance_id: str
    event_dir: Path
    event_generation: int
    job_id: str
    server_instance_id: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def capture_event_context(app, *, video_role: str) -> CapturedEventContext:
    """Capture durable identity before starting asynchronous work."""
    state = app.state.read_state()
    instance_id = state.get("event_instance_id")
    if not isinstance(instance_id, str) or not instance_id.strip():
        instance_id = app.state.ensure_event_instance_id()
        state = app.state.read_state()
    event_dir = Path(app.event_dir).resolve()
    return CapturedEventContext(
        production_root=event_dir.parent,
        event_dir=event_dir,
        folder_event_id=event_dir.name,
        state_event_id=str(state.get("event_id") or app.event_id),
        event_instance_id=instance_id,
        event_generation=int(app.event_generation),
        video_role=video_role,
    )


def _jobs_dir(event_dir: Path) -> Path:
    path = Path(event_dir) / "_jobs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def job_path(event_dir: Path, phase: str, job_id: str) -> Path:
    return _jobs_dir(event_dir) / f"module_lipsync_{phase}_{job_id}.json"


def _job_lock_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".lock")


def load_layered_job(path: Path) -> dict:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != JOB_SCHEMA_VERSION:
        raise ValueError(f"unsupported layered lipsync job: {path}")
    return value


def mutate_layered_job(path: Path, mutator: Callable[[dict], None]) -> dict:
    """Read-modify-write one job under a cross-process lock."""
    path = Path(path)
    lock_path = _job_lock_path(path)
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR)
    try:
        fcntl.lockf(fd, fcntl.LOCK_EX)
        job = load_layered_job(path)
        mutator(job)
        job["updated_at"] = _now()
        atomic_json_write(str(path), job)
        return job
    finally:
        try:
            fcntl.lockf(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def create_layered_job(
    context: CapturedEventContext,
    profile: LayeredLipsyncProfile,
    audio_source: Path,
    prepared_audio: Path,
    plan: LayeredLipsyncPlan,
    *,
    phase: str,
    output_name: str,
    terminal_status: str,
    base_clip_id: str | None,
    cost_per_chunk: float,
) -> tuple[Path, dict]:
    job_id = str(uuid.uuid4())
    path = job_path(context.event_dir, phase, job_id)
    artifacts = _jobs_dir(context.event_dir) / "module_lipsync_artifacts" / job_id
    artifacts.mkdir(parents=True, exist_ok=False)
    durable_audio = artifacts / f"prepared{Path(prepared_audio).suffix or '.mp3'}"
    shutil.copy2(prepared_audio, durable_audio)
    job = {
        "schema_version": JOB_SCHEMA_VERSION,
        "job_id": job_id,
        "status": "planned",
        "stage": "planned",
        "phase": phase,
        "profile": profile.profile_id,
        "route": profile.route_id,
        "method": profile.method_id,
        "context": {
            **asdict(context),
            "production_root": str(context.production_root),
            "event_dir": str(context.event_dir),
        },
        "audio": {
            "source_file": str(Path(audio_source)),
            "source_sha256": sha256_file(Path(audio_source)),
            "prepared_file": str(durable_audio),
            "prepared_sha256": sha256_file(durable_audio),
            "padding_policy": "ENGINE_CHUNK_CONTEXT_V1",
        },
        "plan": {**asdict(plan), "plan_sha256": plan.plan_sha256},
        "chunks": [
            {
                "index": index,
                "status": "prepared",
                "provider_task_id": None,
                "provider_status": None,
                "outputs": [],
                "input_sha256": None,
                "submission_key": None,
                "spend_key": None,
                "charged_at": None,
                "download_file": None,
                "download_sha256": None,
            }
            for index in range(plan.chunk_count)
        ],
        "delivery": {
            "output_file": output_name,
            "manifest_file": str(
                Path(output_name).with_suffix(".json")
            ),
            "terminal_status": terminal_status,
            "base_clip_id": base_clip_id,
            "video_installed": False,
            "manifest_committed": False,
            "state_committed": False,
        },
        "cost_per_chunk": float(cost_per_chunk),
        "lease": None,
        "created_at": _now(),
        "updated_at": _now(),
    }
    atomic_json_write(str(path), job)
    return path, job


def _plan_from_job(job: dict) -> LayeredLipsyncPlan:
    plan = dict(job["plan"])
    plan.pop("plan_sha256", None)
    plan["cuts"] = tuple(plan["cuts"])
    plan["chunk_durations"] = tuple(plan["chunk_durations"])
    plan["padded_chunk_durations"] = tuple(plan["padded_chunk_durations"])
    value = LayeredLipsyncPlan(**plan)
    if value.plan_sha256 != job["plan"]["plan_sha256"]:
        raise ValueError("layered lipsync plan hash mismatch")
    return value


def claim_layered_job_lease(
    path: Path,
    owner_id: str,
    *,
    lease_seconds: float = 90.0,
) -> bool:
    now = time.time()
    claimed = {"value": False}

    def _claim(job: dict) -> None:
        lease = job.get("lease") or {}
        if (
            lease.get("owner_id")
            and lease.get("owner_id") != owner_id
            and float(lease.get("expires_at_epoch") or 0) > now
        ):
            return
        job["lease"] = {
            "owner_id": owner_id,
            "expires_at_epoch": now + lease_seconds,
        }
        claimed["value"] = True

    mutate_layered_job(path, _claim)
    return claimed["value"]


def _set_job_stage(path: Path, status: str, stage: str) -> dict:
    return mutate_layered_job(
        path,
        lambda job: job.update(status=status, stage=stage),
    )


def _update_chunk(path: Path, index: int, **values) -> dict:
    def _apply(job: dict) -> None:
        chunk = job["chunks"][index]
        if int(chunk["index"]) != index:
            raise ValueError("layered job chunk index mismatch")
        chunk.update(values)

    return mutate_layered_job(path, _apply)


def _checkpoint_prepared_inputs(
    path: Path,
    prepared: PreparedLayeredInputs,
    plan: LayeredLipsyncPlan,
) -> None:
    for index in range(plan.chunk_count):
        audio = prepared.work_dir / f"chunk_{index}_audio.mp3"
        video = prepared.work_dir / f"chunk_{index}_video.mp4"
        digest = _sha256_text(f"{sha256_file(video)}:{sha256_file(audio)}")
        job = load_layered_job(path)
        submission_key = (
            f"layered:{job['context']['event_instance_id']}:"
            f"{job['job_id']}:{index}:{digest}"
        )
        _update_chunk(
            path,
            index,
            input_sha256=digest,
            submission_key=submission_key,
            status="prepared",
        )


def _charge_known_task(path: Path, index: int) -> None:
    job = load_layered_job(path)
    chunk = job["chunks"][index]
    task_id = chunk.get("provider_task_id")
    if not task_id or chunk.get("charged_at"):
        return
    spend_key = f"wavespeed:lipsync:{task_id}"
    event_dir = Path(job["context"]["event_dir"])
    record_spend_once(
        event_dir,
        category="lipsync",
        amount=float(job["cost_per_chunk"]),
        idempotency_key=spend_key,
        provider_task_id=task_id,
        metadata={
            "job_id": job["job_id"],
            "phase": job["phase"],
            "chunk_index": index,
            "event_instance_id": job["context"]["event_instance_id"],
        },
    )
    _update_chunk(
        path,
        index,
        spend_key=spend_key,
        charged_at=_now(),
    )


def verify_captured_event(job: dict, state_manager) -> None:
    """Reject terminal writes if durable event or active job identity changed."""
    state = state_manager.read_state()
    context = job["context"]
    if state.get("event_instance_id") != context["event_instance_id"]:
        raise RuntimeError("event_instance_id changed before terminal write")
    phase = job["phase"]
    if state.get(f"phase_{phase}_lipsync_job_id") != job["job_id"]:
        raise RuntimeError("active layered lipsync job changed before terminal write")
    if Path(state_manager.event_dir).resolve() != Path(context["event_dir"]).resolve():
        raise RuntimeError("state manager event directory differs from captured job")


def _poll_provider_with_lease(
    path: Path,
    owner_id: str,
    client,
    task_id: str,
    *,
    timeout_seconds: float = 1800.0,
    interval_seconds: float = 10.0,
) -> dict:
    if not hasattr(client, "poll"):
        return client.poll_until_done(task_id)
    started = time.time()
    while time.time() - started < timeout_seconds:
        if not claim_layered_job_lease(path, owner_id):
            raise RuntimeError("lost layered lipsync job lease while polling")
        result = client.poll(task_id)
        status = str(result.get("status") or "").lower()
        if status == "completed" and result.get("outputs"):
            return result
        if status in {"failed", "error"}:
            return result
        time.sleep(interval_seconds)
    return {"status": "timeout", "outputs": []}


def execute_layered_job(
    path: Path,
    profile: LayeredLipsyncProfile,
    *,
    api_key: str,
    delivery_callback: Callable[[Path, Path, dict], dict],
    state_commit_callback: Callable[[dict, dict, dict], None],
    client_factory: Callable[[str], object] | None = None,
    owner_id: str | None = None,
) -> dict:
    """Run or resume one durable job without resubmitting known tasks."""
    from lipsync_sender import LipSyncClient, PaidSubmissionUnknownError

    path = Path(path)
    owner_id = owner_id or str(uuid.uuid4())
    if not claim_layered_job_lease(path, owner_id):
        return load_layered_job(path)
    if client_factory is None:
        client_factory = LipSyncClient
    try:
        job = load_layered_job(path)
        if job["status"] in TERMINAL_JOB_STATUSES:
            return job
        if job["stage"] == "manifest_committed":
            output = (
                Path(job["context"]["event_dir"])
                / job["delivery"]["output_file"]
            )
            manifest_path = output.with_suffix(".json")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if not manifest.get("committed"):
                raise RuntimeError("layered manifest is not committed")
            if sha256_file(output) != manifest.get("output_sha256"):
                raise RuntimeError("layered manifest/video hash mismatch")
            delivery_meta = manifest.get("delivery_meta") or {}
            state_commit_callback(job, manifest, delivery_meta)
            mutate_layered_job(
                path,
                lambda value: value["delivery"].update(state_committed=True),
            )
            return _set_job_stage(path, "done", "state_committed")
        plan = _plan_from_job(job)
        root = Path(job["context"]["production_root"])
        audio = Path(job["audio"]["prepared_file"])
        artifacts = audio.parent
        prepared = PreparedLayeredInputs(
            work_dir=artifacts,
            idle_track=artifacts / "idle_track.mp4",
            idle_units=tuple(job.get("idle_units") or ()),
        )
        if job["stage"] in {"planned", "preparing"}:
            _set_job_stage(path, "running", "preparing")
            prepared = prepare_layered_lipsync_inputs(
                profile,
                plan,
                audio,
                production_root=root,
                work_dir=artifacts,
            )
            _checkpoint_prepared_inputs(path, prepared, plan)
            mutate_layered_job(
                path,
                lambda value: value.update(
                    stage="submitting",
                    idle_units=list(prepared.idle_units),
                ),
            )
        else:
            prepared = PreparedLayeredInputs(
                work_dir=artifacts,
                idle_track=artifacts / "idle_track.mp4",
                idle_units=tuple(load_layered_job(path).get("idle_units") or ()),
            )

        client = client_factory(api_key)
        for index in range(plan.chunk_count):
            job = load_layered_job(path)
            chunk = job["chunks"][index]
            if chunk.get("provider_task_id"):
                _charge_known_task(path, index)
                continue
            if chunk.get("status") == "submission_unknown":
                raise PaidSubmissionUnknownError(
                    f"chunk {index} has ambiguous paid submission"
                )
            _update_chunk(path, index, status="submitting")
            try:
                task_id = client.submit(
                    artifacts / f"chunk_{index}_video.mp4",
                    artifacts / f"chunk_{index}_audio.mp3",
                    transport="url",
                )
            except Exception as exc:
                _update_chunk(
                    path,
                    index,
                    status="submission_unknown",
                    error=f"{type(exc).__name__}: {exc}",
                )
                _set_job_stage(path, "submission_unknown", "submitting")
                raise
            _update_chunk(
                path,
                index,
                status="submitted",
                provider_task_id=str(task_id),
                provider_status="submitted",
            )
            _charge_known_task(path, index)

        _set_job_stage(path, "running", "provider_polling")
        for index in range(plan.chunk_count):
            job = load_layered_job(path)
            chunk = job["chunks"][index]
            _charge_known_task(path, index)
            if chunk.get("status") == "verified":
                continue
            result = _poll_provider_with_lease(
                path,
                owner_id,
                client,
                chunk["provider_task_id"],
            )
            status = str(result.get("status") or "unknown")
            outputs = list(result.get("outputs") or [])
            _update_chunk(
                path,
                index,
                status="completed" if status.lower() == "completed" else "polling",
                provider_status=status,
                outputs=outputs,
            )
            if status.lower() != "completed" or not outputs:
                raise RuntimeError(f"provider task {chunk['provider_task_id']} {status}")
            destination = artifacts / f"chunk_{index}_lipsync.mp4"
            client.download(outputs[0], destination)
            _update_chunk(
                path,
                index,
                status="verified",
                download_file=str(destination),
                download_sha256=sha256_file(destination),
            )

        _set_job_stage(path, "running", "assembling")
        provider_records = {
            int(chunk["index"]): {
                "status": "completed",
                "task_id": chunk["provider_task_id"],
                "outputs": chunk["outputs"],
            }
            for chunk in load_layered_job(path)["chunks"]
        }
        build = build_layered_lipsync(
            profile,
            plan,
            audio,
            prepared,
            production_root=root,
            provider_records=provider_records,
        )
        _set_job_stage(path, "running", "delivering")
        delivery_stage = artifacts / "delivery_staged.mp4"
        delivery_meta = delivery_callback(
            build.video_path,
            delivery_stage,
            load_layered_job(path),
        )
        output = Path(job["context"]["event_dir"]) / job["delivery"]["output_file"]
        manifest = {
            "schema_version": 1,
            "committed": True,
            "job_id": job["job_id"],
            "profile": profile.profile_id,
            "route": profile.route_id,
            "method": profile.method_id,
            "context": job["context"],
            "plan": job["plan"],
            "chunks": load_layered_job(path)["chunks"],
            "build_output_sha256": build.build_output_sha256,
            "delivery_output_sha256": sha256_file(delivery_stage),
            "output_sha256": sha256_file(delivery_stage),
            "delivery_meta": delivery_meta,
        }
        manifest_path = atomic_deliver(delivery_stage, output, manifest)
        mutate_layered_job(
            path,
            lambda value: value["delivery"].update(
                video_installed=True,
                manifest_committed=True,
                manifest_file=manifest_path.name,
                output_sha256=manifest["output_sha256"],
            ),
        )
        _set_job_stage(path, "running", "manifest_committed")
        state_commit_callback(load_layered_job(path), manifest, delivery_meta)
        mutate_layered_job(
            path,
            lambda value: value["delivery"].update(state_committed=True),
        )
        return _set_job_stage(path, "done", "state_committed")
    except Exception as exc:
        current = load_layered_job(path)
        if current["status"] != "submission_unknown":
            mutate_layered_job(
                path,
                lambda job: job.update(
                    status="error",
                    error=f"{type(exc).__name__}: {exc}",
                ),
            )
        raise
