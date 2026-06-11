#!/usr/bin/env python3
"""Isolated native Kling-compatible lipsync experiment runner.

This command never approves media. It exists to prove or disprove candidate
Kling-compatible lipsync routes with exact external audio and raw >=720 output.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
PROD = HERE.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
if str(PROD) not in sys.path:
    sys.path.insert(0, str(PROD))

import beat_generator as bg_sidecar  # noqa: E402
from lib.paths import EVENT_DIR  # noqa: E402
from kling_native_lipsync_adapters import (  # noqa: E402
    RouteBlocked,
    get_route_registry,
    route_statuses,
    wait_for_result,
)


PASS_MIN_DIMENSION = 720
EXPERIMENT_FIELDS_PREFIX = "kling_native_lipsync_experiment_"
FORBIDDEN_EXPERIMENT_FIELDS = {
    "kling_o3_video_path",
    "kling_o3_status",
    "status",
    "kling_o3_options",
    "accepted_video_path",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_slug(value: str) -> str:
    import re

    slug = re.sub(r"[^a-z0-9_.-]+", "_", (value or "").strip().lower()).strip("_")
    return slug or "experiment"


def probe_media(path: Path) -> dict[str, Any]:
    probe = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "stream=codec_type,width,height,duration:format=duration,size,bit_rate",
            "-of", "json", str(path),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    data = json.loads(probe.stdout)
    streams = data.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    width = int(video.get("width") or 0)
    height = int(video.get("height") or 0)
    return {
        "path": str(path),
        "width": width,
        "height": height,
        "min_dimension": min(width, height) if width and height else 0,
        "has_audio": has_audio,
        "duration_s": float((data.get("format") or {}).get("duration") or 0),
        "size_bytes": int((data.get("format") or {}).get("size") or path.stat().st_size),
        "bit_rate": (data.get("format") or {}).get("bit_rate"),
        "streams": streams,
    }


def passes_gate(profile: dict[str, Any]) -> bool:
    return bool(profile.get("has_audio")) and int(profile.get("min_dimension") or 0) >= PASS_MIN_DIMENSION


def _find_beat(sidecar: dict, beat_id: str) -> tuple[dict, str] | None:
    for arc in (sidecar.get("arcs") or {}).values():
        for segment_key, segment in (arc.get("segments") or {}).items():
            for beat in segment.get("beats") or []:
                if isinstance(beat, dict) and beat.get("beat_id") == beat_id:
                    return beat, str(segment_key)
    return None


def _event_dir_for_segment(segment_key: str) -> Path:
    import re

    match = re.match(r"event_(\d+)_", segment_key or "")
    if match:
        return Path(bg_sidecar._PROD_DIR) / f"Event_{match.group(1)}"
    return Path(bg_sidecar._PROD_DIR) / "Event_1"


def _ref_path(value) -> Path:
    if isinstance(value, dict):
        return Path(value.get("abs_path") or value.get("path") or value.get("local_path") or "")
    return Path(value or "")


def load_beat_inputs(beat_id: str) -> tuple[Path, Path, Path, dict]:
    sidecar = bg_sidecar._migrate_sidecar(bg_sidecar.read_sidecar())
    found = _find_beat(sidecar, beat_id)
    if not found:
        raise RouteBlocked("blocked_missing_beat", f"beat not found: {beat_id}")
    beat, segment_key = found
    video = _ref_path(beat.get("kling_o3_voice_fix_lipsync_input_path"))
    audio = _ref_path(beat.get("kling_o3_voice_fix_lipsync_audio_path"))
    if not video.is_file():
        raise RouteBlocked("blocked_missing_artifacts", f"missing lipsync input video: {video}")
    if not audio.is_file():
        raise RouteBlocked("blocked_missing_artifacts", f"missing lipsync audio: {audio}")
    return video, audio, _event_dir_for_segment(segment_key), beat


def update_experiment_fields(beat_id: str, fields: dict[str, Any], *, remove: tuple[str, ...] = ()) -> None:
    bad = [k for k in fields if k in FORBIDDEN_EXPERIMENT_FIELDS or not k.startswith(EXPERIMENT_FIELDS_PREFIX)]
    if bad:
        raise ValueError(f"experiment attempted to write forbidden fields: {bad}")

    def apply(beat: dict, _sidecar: dict) -> None:
        beat.update(fields)
        for key in remove:
            if key in FORBIDDEN_EXPERIMENT_FIELDS:
                raise ValueError(f"experiment attempted to remove forbidden field: {key}")
            beat.pop(key, None)

    ok, _current = bg_sidecar.update_beat_locked(beat_id, apply)
    if not ok:
        raise RuntimeError(f"could not update experiment fields for beat {beat_id}")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def run_schema_discovery(output_dir: Path) -> dict:
    statuses = route_statuses()
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "route_statuses.json", statuses)
    return {
        "ok": True,
        "mode": "schema_discovery",
        "route_statuses": statuses,
        "output_dir": str(output_dir),
    }


def run_experiment(
    *,
    route_id: str,
    beat_id: str | None,
    input_video: Path | None,
    input_audio: Path | None,
    attempt_id: str | None = None,
    output_root: Path | None = None,
    timeout_s: int = 900,
    return_on_fail: bool = False,
) -> dict:
    registry = get_route_registry()
    if route_id not in registry:
        raise RouteBlocked("blocked_unknown_route", f"unknown route_id: {route_id}")
    adapter = registry[route_id]
    attempt_id = attempt_id or uuid.uuid4().hex
    started = utc_now()

    beat = None
    if beat_id:
        video_path, audio_path, event_dir, beat = load_beat_inputs(beat_id)
    else:
        if not input_video or not input_audio:
            raise RouteBlocked("blocked_missing_artifacts", "--input-video and --input-audio are required without --beat-id")
        video_path = Path(input_video)
        audio_path = Path(input_audio)
        event_dir = output_root or (PROD / "tmp_diagnostics")
        if not video_path.is_file():
            raise RouteBlocked("blocked_missing_artifacts", f"missing input video: {video_path}")
        if not audio_path.is_file():
            raise RouteBlocked("blocked_missing_artifacts", f"missing input audio: {audio_path}")

    work_dir = (
        (output_root or event_dir / "kling_native_lipsync_experiments")
        / _safe_slug(beat_id or "control")
        / _safe_slug(attempt_id)
    )
    work_dir.mkdir(parents=True, exist_ok=True)
    log_path = work_dir / "run.log"
    manifest_path = work_dir / "manifest.json"

    input_video_copy = work_dir / "input_video.mp4"
    input_audio_copy = work_dir / f"input_audio{audio_path.suffix or '.audio'}"
    if video_path.resolve() != input_video_copy.resolve():
        shutil.copy2(video_path, input_video_copy)
    if audio_path.resolve() != input_audio_copy.resolve():
        shutil.copy2(audio_path, input_audio_copy)

    input_profile = {
        "video": probe_media(input_video_copy),
        "audio": probe_media(input_audio_copy),
    }
    write_json(work_dir / "input_profile.json", input_profile)

    if beat_id:
        update_experiment_fields(beat_id, {
            "kling_native_lipsync_experiment_status": "running",
            "kling_native_lipsync_experiment_route": route_id,
            "kling_native_lipsync_experiment_attempt_id": attempt_id,
            "kling_native_lipsync_experiment_started_at": started,
            "kling_native_lipsync_experiment_log_path": str(log_path),
            "kling_native_lipsync_experiment_input_profile": input_profile,
        }, remove=("kling_native_lipsync_experiment_error", "kling_native_lipsync_experiment_error_code"))

    manifest: dict[str, Any] = {
        "attempt_id": attempt_id,
        "beat_id": beat_id,
        "route_id": route_id,
        "provider": adapter.provider,
        "started_at": started,
        "work_dir": str(work_dir),
        "input_profile": input_profile,
        "schema": adapter.describe_schema(),
    }

    try:
        submit = adapter.submit(video_path=input_video_copy, audio_path=input_audio_copy, work_dir=work_dir)
        manifest["submit"] = {
            "provider": submit.provider,
            "route_id": submit.route_id,
            "endpoint": submit.endpoint,
            "job_id": submit.job_id,
            "request_shape_public": submit.request_shape_public,
            "raw_response_public": submit.raw_response_public,
            "output_url_present": bool(submit.output_url),
        }
        write_json(work_dir / "request_public.json", submit.request_shape_public)
        write_json(work_dir / "submit_response_public.json", submit.raw_response_public)

        if submit.output_url:
            poll = {
                "status": "completed",
                "raw_response_public": submit.raw_response_public,
                "output_url": submit.output_url,
            }
        else:
            poll_result = wait_for_result(adapter, submit.job_id, timeout_s=timeout_s)
            poll = {
                "status": poll_result.status,
                "raw_response_public": poll_result.raw_response_public,
                "output_url": poll_result.output_url,
                "error": poll_result.error,
            }
            if getattr(adapter, "_last_poll_payload", None):
                write_json(work_dir / "poll_response_full.json", adapter._last_poll_payload)
        manifest["poll"] = poll
        write_json(work_dir / "poll_response_public.json", poll)

        status = str(poll.get("status") or "").lower()
        output_url = poll.get("output_url")
        if status not in {"completed", "succeeded", "success", "done"} or not output_url:
            raise RouteBlocked("provider_failed_or_no_output", f"provider status={status}, output_url_present={bool(output_url)}")

        raw_output = work_dir / "raw_output.mp4"
        adapter.download(str(output_url), raw_output)
        raw_profile = probe_media(raw_output)
        write_json(work_dir / "raw_profile.json", raw_profile)
        passed = passes_gate(raw_profile)
        completed = utc_now()
        manifest.update({
            "completed_at": completed,
            "raw_output_path": str(raw_output),
            "raw_profile": raw_profile,
            "passed_gate": passed,
            "status": "passed" if passed else "failed",
            "error_code": None if passed else "PROVIDER_RAW_GATE_FAILED",
            "error": None if passed else (
                f"raw output failed gate: width={raw_profile.get('width')} "
                f"height={raw_profile.get('height')} has_audio={raw_profile.get('has_audio')}"
            ),
        })
        if beat_id:
            update_experiment_fields(beat_id, {
                "kling_native_lipsync_experiment_status": "passed" if passed else "failed",
                "kling_native_lipsync_experiment_route": route_id,
                "kling_native_lipsync_experiment_attempt_id": attempt_id,
                "kling_native_lipsync_experiment_completed_at": completed,
                "kling_native_lipsync_experiment_result": manifest.get("submit"),
                "kling_native_lipsync_experiment_output_path": str(raw_output),
                "kling_native_lipsync_experiment_output_profile": raw_profile,
                "kling_native_lipsync_experiment_passed_gate": passed,
                "kling_native_lipsync_experiment_error": manifest.get("error"),
                "kling_native_lipsync_experiment_error_code": manifest.get("error_code"),
            })
        write_json(manifest_path, manifest)
        print(json.dumps(manifest, indent=2, sort_keys=True))
        if not passed:
            if return_on_fail:
                return manifest
            raise SystemExit(2)
        return manifest
    except RouteBlocked as exc:
        completed = utc_now()
        manifest.update({
            "completed_at": completed,
            "status": "blocked" if exc.code.startswith("blocked_") else "failed",
            "error_code": exc.code,
            "error": str(exc),
        })
        write_json(manifest_path, manifest)
        if beat_id:
            update_experiment_fields(beat_id, {
                "kling_native_lipsync_experiment_status": manifest["status"],
                "kling_native_lipsync_experiment_route": route_id,
                "kling_native_lipsync_experiment_attempt_id": attempt_id,
                "kling_native_lipsync_experiment_completed_at": completed,
                "kling_native_lipsync_experiment_error": str(exc),
                "kling_native_lipsync_experiment_error_code": exc.code,
                "kling_native_lipsync_experiment_passed_gate": False,
            })
        print(json.dumps(manifest, indent=2, sort_keys=True))
        if return_on_fail:
            return manifest
        raise SystemExit(3)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema-discovery", action="store_true")
    parser.add_argument("--route", default="wavespeed_kling_lipsync_baseline")
    parser.add_argument("--beat-id", default=None)
    parser.add_argument("--event-dir", type=Path, default=EVENT_DIR(1))
    parser.add_argument("--input-video", type=Path, default=None)
    parser.add_argument("--input-audio", type=Path, default=None)
    parser.add_argument("--attempt-id", default=None)
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--timeout-s", type=int, default=900)
    args = parser.parse_args()
    bg_sidecar.init_bg_paths(args.event_dir)

    if args.schema_discovery:
        out = args.output_root or (PROD / "tmp_diagnostics" / f"kling_native_lipsync_schema_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}")
        print(json.dumps(run_schema_discovery(out), indent=2, sort_keys=True))
        return 0

    run_experiment(
        route_id=args.route,
        beat_id=args.beat_id,
        input_video=args.input_video,
        input_audio=args.input_audio,
        attempt_id=args.attempt_id,
        output_root=args.output_root,
        timeout_s=args.timeout_s,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

