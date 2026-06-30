"""Kling O3 Omni handlers for Beat Generator tab."""

from __future__ import annotations

import concurrent.futures as _cf
import json
import os
import threading
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

from lib.paths import API_KEYS_MASTER_PATH
from tools import kling_o3_client
from tools import kling_o3_job_store as job_store
from tools.production_server import _KLING_O3_JOBS, _bg_module, parse_api_keys


def _bg(h):
    return _bg_module()


def _api_key() -> str:
    keys = parse_api_keys(API_KEYS_MASTER_PATH)
    key = keys.get("wavespeed") or ""
    if not key:
        raise RuntimeError("WAVESPEED_API_KEY not configured")
    return key


def _apply_kling_beat_result(
    bg,
    beat_id: str,
    generation: int,
    prompt: str,
    duration: int,
    result: dict,
    event_dir: Path,
) -> None:
    beat_obj_for_preserve = None

    def _mutator(beat_obj: dict, _sidecar: dict) -> None:
        nonlocal beat_obj_for_preserve
        beat_obj["kling_o3_prompt_prepared"] = prompt
        beat_obj["kling_o3_duration"] = duration
        if result.get("ok"):
            vp = str(result.get("video_path") or "")
            from kling_stitch_readiness import finalize_kling_delivery_clip  # noqa: PLC0415

            beat_obj["kling_o3_task_id"] = result.get("task_id")
            beat_obj["kling_o3_completed_at"] = datetime.now(timezone.utc).isoformat()
            beat_obj["kling_o3_generation"] = generation
            if result.get("mode"):
                beat_obj["kling_o3_mode"] = result.get("mode")
            elif result.get("submit_mode"):
                beat_obj["kling_o3_mode"] = result.get("submit_mode")
            if vp and os.path.isfile(vp):
                finalize_kling_delivery_clip(beat_obj, vp)
                bg.clear_kling_o3_beat_trim(beat_obj)
                trim_info = bg.trim_kling_o3_clip_post_speech(Path(vp))
                if trim_info.get("trimmed"):
                    beat_obj["kling_o3_post_speech_trim"] = trim_info
                actual = bg._ffprobe_duration(Path(vp))
                if actual > 0:
                    beat_obj["kling_o3_actual_duration_s"] = round(actual, 3)
            else:
                beat_obj["kling_o3_status"] = "failed"
                beat_obj["kling_o3_error"] = "generation reported ok but video missing on disk"
        else:
            beat_obj["kling_o3_status"] = "failed"
            beat_obj["kling_o3_error"] = str(
                result.get("error") or result.get("status") or result.get("result")
            )
        if result.get("ok") and beat_obj.get("kling_o3_video_path"):
            beat_obj_for_preserve = dict(beat_obj)

    bg.update_beat_locked(beat_id, _mutator)
    if beat_obj_for_preserve:
        bg.preserve_kling_o3_beat_slot(beat_obj_for_preserve, event_dir, reason="generation_complete")


def _resume_beat_from_task(
    event_dir: Path,
    api_key: str,
    beat_id: str,
    task_id: str,
    dest: Path,
    *,
    job_id: str | None = None,
    generation: int = 0,
    prompt: str = "",
    duration: int = 8,
) -> dict:
    bg = _bg_module()
    try:
        result = kling_o3_client.resume_task_to_mp4(api_key, task_id, dest)
    except Exception as exc:
        result = {"ok": False, "task_id": task_id, "error": str(exc)}
    if job_id:
        job_store.record_job_result(event_dir, job_id, beat_id, result)
    _apply_kling_beat_result(bg, beat_id, generation, prompt, duration, result, event_dir)
    return {"beat_id": beat_id, **result}


def _beat_needs_recovery(beat_id: str, meta: dict, results: dict) -> bool:
    prior = results.get(beat_id)
    if prior and prior.get("ok"):
        return False
    status = (meta.get("status") or "queued").lower()
    if status in ("queued", "processing", "submitted"):
        return True
    # Client poll timed out while WaveSpeed task may still be running.
    if meta.get("task_id") and (prior or {}).get("status") == "timeout":
        return True
    return False


def _beat_should_resume_timed_out_task(beat: dict, dest: Path) -> bool:
    """True when a prior client-side poll timed out but task_id + dest slot remain."""
    if dest.is_file():
        return False
    task_id = beat.get("kling_o3_task_id")
    if not task_id:
        return False
    err = str(beat.get("kling_o3_error") or "").lower()
    st = str(beat.get("kling_o3_status") or "").lower()
    return err == "timeout" or (st == "failed" and err == "timeout")


def recover_kling_o3_jobs_on_startup(event_dir: Path, api_key: str | None) -> int:
    """Rehydrate in-flight jobs after server restart; resume WaveSpeed polling."""
    if not api_key:
        return 0
    bg = _bg_module()
    from beatgen_scope import beatgen_scope_ctx, build_event_production_scope  # noqa: PLC0415

    scope = build_event_production_scope(event_dir)
    with beatgen_scope_ctx(scope, bg):
        bg.mutate_sidecar_locked(
            lambda sidecar: bg.reconcile_kling_o3_sidecar(sidecar, event_dir),
            scope=scope,
            caller="recover_kling_o3_jobs_on_startup",
        )

    resumed = 0
    for job in job_store.list_active_jobs(event_dir):
        job_id = job.get("job_id")
        if not job_id:
            continue
        _KLING_O3_JOBS[job_id] = job_store.job_to_memory(job)
        beats = job.get("beats") or {}
        results = job.get("results") or {}
        pending_poll = [
            (bid, meta) for bid, meta in beats.items()
            if meta.get("task_id") and _beat_needs_recovery(bid, meta, results)
        ]
        pending_submit = [
            (bid, meta) for bid, meta in beats.items()
            if not meta.get("task_id") and _beat_needs_recovery(bid, meta, results)
        ]

        def _recover_job(
            jid=job_id,
            poll_beats=pending_poll,
            submit_beats=pending_submit,
            ctx=job.get("context") or {},
        ):
            for beat_id, meta in submit_beats:
                sidecar = bg.read_sidecar()
                _, live = bg.find_beat(sidecar, beat_id)
                if not live:
                    res = {"beat_id": beat_id, "ok": False, "error": "beat_not_found_on_recovery"}
                    job_store.record_job_result(event_dir, jid, beat_id, res)
                    _KLING_O3_JOBS[jid]["results"][beat_id] = res
                    _KLING_O3_JOBS[jid]["failed_count"] = int(_KLING_O3_JOBS[jid].get("failed_count") or 0) + 1
                    continue
                beat_copy = dict(live)
                job_store.update_job_beat(event_dir, jid, beat_id, status="processing")
                res = _run_single_beat(
                    _RecoveryHandler(event_dir),
                    {"context": ctx},
                    beat_copy,
                    event_dir,
                    api_key,
                    job_id=jid,
                    skip_pin_check=True,
                )
                job_store.record_job_result(event_dir, jid, beat_id, res)
                _KLING_O3_JOBS[jid]["results"][beat_id] = res
                if res.get("ok"):
                    _KLING_O3_JOBS[jid]["done_count"] = int(_KLING_O3_JOBS[jid].get("done_count") or 0) + 1
                else:
                    _KLING_O3_JOBS[jid]["failed_count"] = int(_KLING_O3_JOBS[jid].get("failed_count") or 0) + 1

            for beat_id, meta in poll_beats:
                task_id = meta.get("task_id")
                dest = Path(meta.get("dest_mp4") or "")
                if not task_id or not dest:
                    continue
                res = _resume_beat_from_task(
                    event_dir,
                    api_key,
                    beat_id,
                    task_id,
                    dest,
                    job_id=jid,
                    generation=int(meta.get("generation") or 0),
                    prompt=str(meta.get("prompt_prepared") or ""),
                    duration=int(meta.get("duration") or 8),
                )
                _KLING_O3_JOBS[jid]["results"][beat_id] = res
                if res.get("ok"):
                    _KLING_O3_JOBS[jid]["done_count"] = int(_KLING_O3_JOBS[jid].get("done_count") or 0) + 1
                else:
                    _KLING_O3_JOBS[jid]["failed_count"] = int(_KLING_O3_JOBS[jid].get("failed_count") or 0) + 1
            _KLING_O3_JOBS[jid]["status"] = "done"
            job_store.finalize_job(event_dir, jid, "done")

        if pending_poll or pending_submit:
            threading.Thread(
                target=_recover_job,
                daemon=True,
                name=f"kling-o3-recover-{job_id}",
            ).start()
            resumed += 1
            print(
                f"[startup] Kling O3: resuming job {job_id} "
                f"({len(pending_submit)} re-submit, {len(pending_poll)} poll)"
            )
        else:
            job_store.finalize_job(event_dir, job_id, "done")
    return resumed


class _RecoveryHandler:
    """Minimal handler stub for startup job recovery (no HTTP request context)."""

    def __init__(self, event_dir: Path) -> None:
        self.app = type("App", (), {"event_dir": str(event_dir)})()

    def _check_event_pin(self, _pin: dict, _stage: str) -> bool:
        return True


def handle_bg_kling_o3_active_jobs(h) -> None:
    """GET /api/bg/kling-o3-active-jobs — re-attach client polling after refresh."""
    if not h._assert_event_scope({}, allow_missing=True):
        return
    summaries = job_store.active_jobs_summary(h.app.event_dir)
    for item in summaries:
        jid = item.get("job_id")
        if jid and jid not in _KLING_O3_JOBS:
            loaded = job_store.load_job(h.app.event_dir, jid)
            if loaded:
                _KLING_O3_JOBS[jid] = job_store.job_to_memory(loaded)
    return h._send_json(200, {"ok": True, "jobs": summaries})


def handle_bg_generate_kling_prompts(h, body: dict) -> None:
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return
    arc_number = int(body.get("arc_number", 1))
    event_id = str(body.get("event_id", "1"))
    phase = str(body.get("phase", "full"))
    bg = _bg(h)
    count = 0
    beats: list = []

    def _mutator(sidecar: dict) -> None:
        nonlocal count, beats
        count = bg.generate_kling_prompts_for_segment(sidecar, arc_number, event_id, phase)
        seg = bg.get_seg_entry(sidecar, arc_number, event_id, phase)
        beats = seg.get("beats") or []

    bg.mutate_sidecar_locked(_mutator)
    return h._send_json(200, {"ok": True, "count": count, "beats": beats})


def handle_bg_import_locked_lines(h, body: dict) -> None:
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return
    arc_number = int(body.get("arc_number", 1))
    event_id = str(body.get("event_id", "1"))
    phase = str(body.get("phase", "pre"))
    rel_path = body.get("path") or "Event_1/M1E1_locked_lines_v16.json"
    locked_path = Path(h.app.event_dir).parent / rel_path
    if not locked_path.is_file():
        locked_path = Path(h.app.event_dir) / Path(rel_path).name
    if not locked_path.is_file():
        return h._send_error_v59(
            404,
            error_code="LOCKED_LINES_NOT_FOUND",
            error_message=f"Locked lines file not found: {rel_path}",
            retry_safe=False,
        )
    bg = _bg(h)
    beats = bg.import_locked_lines_beats(locked_path, arc_number, event_id, phase)
    merged: list = []

    def _mutator(sidecar: dict) -> None:
        nonlocal merged
        seg = bg.get_seg_entry(sidecar, arc_number, event_id, phase)
        merged = bg.merge_incoming_segment_beats(seg.get("beats") or [], beats)
        seg["beats"] = merged
        seg["name"] = seg.get("name") or f"Event {event_id} {phase} (locked lines)"
        sidecar["active_context"] = {"arc_number": arc_number, "event_id": event_id, "phase": phase}

    bg.mutate_sidecar_locked(_mutator)
    return h._send_json(200, {"ok": True, "beats": merged, "count": len(merged)})


def _run_single_beat(
    h,
    pin: dict,
    beat: dict,
    event_dir: Path,
    api_key: str,
    *,
    job_id: str | None = None,
    skip_pin_check: bool = False,
) -> dict:
    bg = _bg(h)
    beat_id = beat["beat_id"]
    raw_prompt = (beat.get("kling_o3_prompt") or "").strip()
    if not raw_prompt:
        return {"beat_id": beat_id, "ok": False, "error": "kling_o3_prompt empty"}
    prompt = bg.prepare_kling_o3_prompt_for_submit(beat, raw_prompt)
    if not prompt:
        return {"beat_id": beat_id, "ok": False, "error": "kling_o3_prompt empty after prep"}
    duration = bg.resolve_kling_o3_submit_duration(beat, prompt)
    ctx = pin.get("context") or {}
    event_id = str(ctx.get("event_id", "1"))
    phase = str(ctx.get("phase", "full"))
    submit_mode = bg.resolve_kling_o3_submit_mode(beat)
    char_path = bg.resolve_beat_char_ref_path(beat)
    bg_path = bg.resolve_beat_bg_ref_path(beat, event_id, phase)
    start_path = bg.resolve_beat_start_frame_path(beat)
    end_path = bg.resolve_beat_end_frame_path(beat)
    if submit_mode == "startend":
        if not start_path or not end_path:
            return {
                "beat_id": beat_id,
                "ok": False,
                "error": f"missing start/end frames start={bool(start_path)} end={bool(end_path)}",
            }
    elif not char_path or not bg_path:
        return {
            "beat_id": beat_id,
            "ok": False,
            "error": f"missing refs char={bool(char_path)} bg={bool(bg_path)}",
        }
    generation = int(beat.get("kling_o3_generation") or 0)
    dest = bg.kling_o3_clips_dir(event_dir) / f"{beat_id}_g{generation}.mp4"
    meta_path = dest.with_suffix(".json")

    resume_task_id = None
    if _beat_should_resume_timed_out_task(beat, dest):
        resume_task_id = beat.get("kling_o3_task_id")
        tier = "pro"
        try:
            from tools import kling_character_registry as reg
            tier = "pro" if reg.get_element_list_entry(beat.get("speaker") or "") else "std"
        except Exception:
            pass
    else:
        try:
            if submit_mode == "startend":
                task_id, tier = kling_o3_client.submit_image_to_video_startend(
                    api_key,
                    prompt,
                    start_path,
                    end_path,
                    duration=duration,
                    speaker=beat.get("speaker"),
                    sound=True,
                )
            else:
                task_id, tier = kling_o3_client.submit_reference_to_video(
                    api_key, prompt, char_path, bg_path, duration=duration, speaker=beat.get("speaker"),
                )
        except Exception as exc:
            return {"beat_id": beat_id, "ok": False, "error": str(exc)}

        if job_id:
            job_store.update_job_beat(
                event_dir, job_id, beat_id,
                task_id=task_id,
                status="submitted",
                tier=tier,
                dest_mp4=str(dest),
                generation=generation,
                prompt_prepared=prompt,
                duration=duration,
                submit_mode=submit_mode,
            )

        def _stamp_processing(b: dict, _sc: dict) -> None:
            b["kling_o3_task_id"] = task_id
            b["kling_o3_status"] = "processing"
            b["kling_o3_mode"] = submit_mode
            b.pop("kling_o3_error", None)

        bg.update_beat_locked(beat_id, _stamp_processing)

        resume_task_id = task_id

    try:
        poll_result = kling_o3_client.poll_until_done(resume_task_id, api_key)
        status = (poll_result.get("status") or "").lower()
        if status != "completed":
            result = {
                "ok": False,
                "task_id": resume_task_id,
                "status": status,
                "tier": tier,
                "result": poll_result,
                "error": (
                    poll_result.get("error")
                    or (
                        f"WaveSpeed poll timed out (task {resume_task_id}) — "
                        "approved options preserved; retry Generate when ready"
                        if status == "timeout"
                        else status
                    )
                ),
            }
        else:
            url = kling_o3_client.extract_output_url(poll_result)
            if not url:
                result = {
                    "ok": False,
                    "task_id": resume_task_id,
                    "status": "no_output_url",
                    "tier": tier,
                    "result": poll_result,
                }
            else:
                kling_o3_client.download_mp4(url, dest)
                result = {
                    "ok": True,
                    "task_id": resume_task_id,
                    "tier": tier,
                    "video_path": str(dest),
                    "video_url": url,
                    "status": status,
                    "submit_mode": submit_mode,
                }
    except Exception as exc:
        return {"beat_id": beat_id, "ok": False, "error": str(exc), "task_id": resume_task_id}

    if not skip_pin_check and not h._check_event_pin(pin, "kling_o3_write_sidecar"):
        return {"beat_id": beat_id, "ok": False, "error": "event_changed_mid_job", "task_id": resume_task_id}

    _apply_kling_beat_result(bg, beat_id, generation, prompt, duration, result, event_dir)
    meta_path.write_text(json.dumps({
        "beat_id": beat_id,
        "result": result,
        "prompt": prompt,
        "submit_mode": submit_mode,
    }, indent=2))
    return {"beat_id": beat_id, "submit_mode": submit_mode, **result}


def handle_bg_submit_kling_o3_batch(h, body: dict) -> None:
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return
    beat_ids = body.get("beat_ids") or []
    if not beat_ids:
        return h._send_error_v59(
            400, error_code="MISSING_BEAT_IDS", error_message="beat_ids required", retry_safe=False,
        )
    max_parallel = int(body.get("max_parallel") or os.environ.get("KLING_O3_MAX_PARALLEL", "5"))
    max_parallel = max(1, min(max_parallel, 11))

    pin = {
        "pinned_generation": h.app.event_generation,
        "pinned_event_dir": h.app.event_dir,
        "context": {
            "event_id": body.get("event_id"),
            "phase": body.get("phase"),
        },
    }
    if not h._check_event_pin(pin, "kling_o3_batch_pre_work"):
        return h._send_error_v59(
            423, error_code="EVENT_CHANGED_PRE_WORK", error_message="event_changed_pre_work", retry_safe=False,
        )

    job_id = str(uuid.uuid4())[:8]
    bg = _bg(h)
    event_id = str(body.get("event_id") or "1")
    phase = str(body.get("phase") or "full")
    beat_prompts = body.get("beat_prompts") or {}
    beats_to_run = []
    skipped_done: list[str] = []

    def _prepare_batch(sidecar: dict) -> None:
        nonlocal beats_to_run, skipped_done
        if beat_prompts:
            bg.apply_live_kling_o3_prompts(sidecar, beat_prompts)
        reconciled = bg.reconcile_kling_o3_sidecar(sidecar, Path(h.app.event_dir))
        sidecar_dirty = bool(reconciled) or bool(beat_prompts)
        for bid in beat_ids:
            _, beat = bg.find_beat(sidecar, bid)
            if not beat:
                continue
            if bg.ensure_beat_element_aligned_reference(beat):
                sidecar_dirty = True
            st = beat.get("kling_o3_status") or "draft"
            if st in ("completed", "approved") and beat.get("kling_o3_video_path"):
                skipped_done.append(bid)
                continue
            beats_to_run.append(dict(beat))
        if not sidecar_dirty and not beats_to_run:
            return

    bg.mutate_sidecar_locked(_prepare_batch)

    if not beats_to_run:
        return h._send_json(200, {
            "ok": True,
            "job_id": None,
            "beat_ids": [],
            "skipped_done": skipped_done,
            "message": "All selected beats already have Kling clips",
        })

    validation_errors = bg.validate_kling_o3_beats_for_submit(
        beats_to_run,
        event_id=event_id,
        phase=phase,
    )
    if validation_errors:
        return h._send_error_v59(
            400,
            error_code="KLING_O3_PRE_SUBMIT_VALIDATION",
            error_message=(
                f"{len(validation_errors)} pre-submit check(s) failed — "
                "fix voice registry or dialogue length before submitting."
            ),
            retry_safe=False,
            extra={"errors": validation_errors},
        )

    def _queue_beats(sidecar: dict) -> None:
        run_ids = {b["beat_id"] for b in beats_to_run}
        for bid in run_ids:
            _, beat = bg.find_beat(sidecar, bid)
            if beat:
                beat["kling_o3_status"] = "queued"

    bg.mutate_sidecar_locked(_queue_beats)

    event_dir = Path(h.app.event_dir)
    beat_entries: dict[str, dict] = {}
    for beat in beats_to_run:
        bid = beat["beat_id"]
        gen = int(beat.get("kling_o3_generation") or 0)
        beat_entries[bid] = {
            "status": "queued",
            "generation": gen,
            "dest_mp4": str(bg.kling_o3_clips_dir(event_dir) / f"{bid}_g{gen}.mp4"),
        }
    scope_body = h._scope_body(body)
    scope_event_id = str(scope_body.get("scope_event_id") or h.app.event_id)
    job_store.create_job(
        event_dir,
        job_id=job_id,
        beat_entries=beat_entries,
        context={"event_id": event_id, "phase": phase},
        scope_event_id=scope_event_id,
    )

    _KLING_O3_JOBS[job_id] = {
        "status": "running",
        "results": {},
        "total": len(beats_to_run),
        "done_count": 0,
        "failed_count": 0,
    }

    def _run_job():
        from beatgen_scope import run_in_beatgen_scope  # noqa: PLC0415

        def _body():
            try:
                api_key = _api_key()
            except Exception as exc:
                _KLING_O3_JOBS[job_id]["status"] = "failed"
                _KLING_O3_JOBS[job_id]["error"] = str(exc)
                job_store.finalize_job(event_dir, job_id, "failed", error=str(exc))
                return

            def _one(beat):
                if not h._check_event_pin(pin, "kling_o3_beat_start"):
                    return {"beat_id": beat["beat_id"], "ok": False, "error": "event_changed"}
                job_store.update_job_beat(event_dir, job_id, beat["beat_id"], status="processing")

                def _mark_processing(b: dict, _sc: dict) -> None:
                    b["kling_o3_status"] = "processing"
                    beat.update(b)

                bg.update_beat_locked(beat["beat_id"], _mark_processing, caller="kling_o3_batch")
                return _run_single_beat(h, pin, beat, event_dir, api_key, job_id=job_id)

            with _cf.ThreadPoolExecutor(max_workers=max_parallel, thread_name_prefix="kling-o3") as pool:
                futures = {pool.submit(_one, b): b["beat_id"] for b in beats_to_run}
                for fut in _cf.as_completed(futures):
                    bid = futures[fut]
                    try:
                        res = fut.result()
                    except Exception as exc:
                        res = {"beat_id": bid, "ok": False, "error": str(exc)}
                    job_store.record_job_result(event_dir, job_id, bid, res)
                    _KLING_O3_JOBS[job_id]["results"][bid] = res
                    if res.get("ok"):
                        _KLING_O3_JOBS[job_id]["done_count"] += 1
                    else:
                        _KLING_O3_JOBS[job_id]["failed_count"] += 1
            _KLING_O3_JOBS[job_id]["status"] = "done"
            job_store.finalize_job(event_dir, job_id, "done")

        run_in_beatgen_scope(h.app, bg, _body)

    threading.Thread(target=_run_job, daemon=True, name=f"kling-o3-{job_id}").start()
    return h._send_json(200, {
        "ok": True,
        "job_id": job_id,
        "beat_ids": beat_ids,
        "max_parallel": max_parallel,
    })


def handle_bg_poll_kling_o3_status(h) -> None:
    import urllib.parse

    qs = urllib.parse.parse_qs(urllib.parse.urlparse(h.path).query)
    job_id = (qs.get("job_id") or [""])[0]
    if not job_id:
        return h._send_error_v59(
            404, error_code="JOB_NOT_FOUND", error_message="job_id required", retry_safe=False,
        )
    job = _KLING_O3_JOBS.get(job_id)
    if not job:
        stored = job_store.load_job(h.app.event_dir, job_id)
        if stored:
            job = job_store.job_to_memory(stored)
            _KLING_O3_JOBS[job_id] = job
        else:
            return h._send_error_v59(
                404, error_code="JOB_NOT_FOUND", error_message=f"job {job_id!r} not found", retry_safe=False,
            )
    return h._send_json(200, {
        "status": job["status"],
        "results": job.get("results", {}),
        "total": job.get("total", 0),
        "done_count": job.get("done_count", 0),
        "failed_count": job.get("failed_count", 0),
    })


def handle_bg_approve_kling_o3(h, body: dict) -> None:
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return
    beat_id = body.get("beat_id")
    if not beat_id:
        return h._send_error_v59(
            400, error_code="MISSING_BEAT_ID", error_message="beat_id required", retry_safe=False,
        )
    bg = _bg(h)
    sidecar = bg.read_sidecar()
    _, beat = bg.find_beat(sidecar, beat_id)
    if not beat:
        return h._send_error_v59(
            404, error_code="BEAT_NOT_FOUND", error_message=f"beat {beat_id} not found", retry_safe=False,
        )
    if not beat.get("kling_o3_video_path"):
        return h._send_error_v59(
            400, error_code="NO_VIDEO", error_message="No kling_o3_video_path on beat", retry_safe=False,
        )

    def _approve(b: dict, _sc: dict) -> None:
        from kling_stitch_readiness import finalize_kling_delivery_clip  # noqa: PLC0415

        vp = str(b.get("kling_o3_video_path") or "")
        if bg.beat_is_still_insert(b):
            b["kling_o3_still_stitch_approved"] = True
            b["kling_o3_still_stitch_approved_at"] = datetime.now(timezone.utc).isoformat()
        finalize_kling_delivery_clip(b, vp)

    bg.update_beat_locked(beat_id, _approve)
    return h._send_json(200, {"ok": True, "beat_id": beat_id})


def handle_bg_redo_kling_o3(h, body: dict) -> None:
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return
    beat_id = body.get("beat_id")
    if not beat_id:
        return h._send_error_v59(
            400, error_code="MISSING_BEAT_ID", error_message="beat_id required", retry_safe=False,
        )
    bg = _bg(h)
    event_dir = Path(h.app.event_dir)
    sidecar = bg.read_sidecar()
    _, beat = bg.find_beat(sidecar, beat_id)
    if not beat:
        return h._send_error_v59(
            404, error_code="BEAT_NOT_FOUND", error_message=f"beat {beat_id} not found", retry_safe=False,
        )

    def _redo(b: dict, _sc: dict) -> None:
        bg.preserve_kling_o3_beat_slot(b, event_dir, reason="redo")
        bg.reset_kling_o3_beat_for_redo(b, event_dir)

    bg.update_beat_locked(beat_id, _redo)
    return handle_bg_submit_kling_o3_batch(h, {"beat_ids": [beat_id], **body})


def handle_bg_pin_kling_o3(h, body: dict) -> None:
    """POST /api/bg/pin-kling-o3 — manual preserve before redo."""
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return
    beat_id = body.get("beat_id")
    if not beat_id:
        return h._send_error_v59(
            400, error_code="MISSING_BEAT_ID", error_message="beat_id required", retry_safe=False,
        )
    bg = _bg(h)
    event_dir = Path(h.app.event_dir)
    pin_result: dict = {}

    def _pin(b: dict, _sc: dict) -> None:
        ok, err = bg.pin_kling_o3_beat(b, event_dir)
        pin_result["ok"] = ok
        pin_result["err"] = err

    ok, _beat = bg.update_beat_locked(beat_id, _pin)
    if not ok:
        return h._send_error_v59(
            404, error_code="BEAT_NOT_FOUND", error_message=f"beat {beat_id} not found", retry_safe=False,
        )
    if not pin_result.get("ok"):
        return h._send_error_v59(
            400,
            error_code="PIN_FAILED",
            error_message=f"Could not preserve beat: {pin_result.get('err')}",
            retry_safe=False,
        )
    sidecar = bg.read_sidecar()
    _, beat = bg.find_beat(sidecar, beat_id)
    beat_out = bg.enrich_beat_kling_o3_pinned(beat or {}, event_dir)
    return h._send_json(200, {"ok": True, "beat_id": beat_id, "beat": beat_out})


def handle_bg_restore_kling_o3(h, body: dict) -> None:
    """POST /api/bg/restore-kling-o3 — restore pinned clip over current generation."""
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return
    beat_id = body.get("beat_id")
    if not beat_id:
        return h._send_error_v59(
            400, error_code="MISSING_BEAT_ID", error_message="beat_id required", retry_safe=False,
        )
    bg = _bg(h)
    event_dir = Path(h.app.event_dir)
    restore_result: dict = {}

    def _restore(sidecar: dict) -> None:
        ok, err, beat_out = bg.restore_pinned_kling_o3_beat(beat_id, event_dir, sidecar)
        restore_result["ok"] = ok
        restore_result["err"] = err
        restore_result["beat_out"] = beat_out

    bg.mutate_sidecar_locked(_restore)
    if not restore_result.get("ok"):
        err = restore_result.get("err")
        code = 404 if err == "no_pinned" else 400
        return h._send_error_v59(
            code,
            error_code="RESTORE_FAILED",
            error_message=f"Could not restore preserved beat: {err}",
            retry_safe=False,
        )
    return h._send_json(
        200,
        {"ok": True, "beat_id": beat_id, "beat": restore_result.get("beat_out")},
    )


def handle_bg_kling_o3_preview(h, body: dict) -> None:
    """POST /api/bg/kling-o3-preview — show extracted dialogue + warnings before submit."""
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return
    beat_id = body.get("beat_id")
    if not beat_id:
        return h._send_error_v59(
            400, error_code="MISSING_BEAT_ID", error_message="beat_id required", retry_safe=False,
        )
    raw_prompt = (body.get("kling_o3_prompt") or body.get("prompt") or "").strip()
    event_id = str(body.get("event_id") or "1")
    phase = str(body.get("phase") or "full")
    bg = _bg(h)
    sidecar = bg.read_sidecar()
    _, beat = bg.find_beat(sidecar, beat_id)
    if not beat:
        return h._send_error_v59(
            404, error_code="BEAT_NOT_FOUND", error_message=f"beat {beat_id} not found", retry_safe=False,
        )
    beat_copy = dict(beat)
    if raw_prompt:
        beat_copy["kling_o3_prompt"] = raw_prompt
    preview = bg.preview_kling_o3_submit(beat_copy, raw_prompt or beat_copy.get("kling_o3_prompt") or "", event_id=event_id, phase=phase)
    return h._send_json(200, {"ok": True, **preview})


def handle_bg_kling_o3_trim(h, body: dict) -> None:
    """POST /api/bg/kling-o3-trim — set front/back trim on a Kling O3 beat clip."""
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return
    beat_id = body.get("beat_id")
    if not beat_id:
        return h._send_error_v59(
            400, error_code="MISSING_BEAT_ID", error_message="beat_id required", retry_safe=False,
        )
    raw_trim_start = body.get("trim_start")
    if raw_trim_start is None:
        raw_trim_start = body.get("trim_in", 0)
    try:
        trim_start = float(raw_trim_start)
    except (TypeError, ValueError):
        return h._send_error_v59(
            400, error_code="INVALID_TRIM_START", error_message="trim_start must be numeric", retry_safe=False,
        )
    raw_trim_back = body.get("trim_back")
    trim_back: float | None
    if raw_trim_back is None:
        trim_back = None
    else:
        try:
            trim_back = float(raw_trim_back)
        except (TypeError, ValueError):
            return h._send_error_v59(
                400, error_code="INVALID_TRIM_BACK", error_message="trim_back must be numeric", retry_safe=False,
            )
    if trim_start < 0:
        return h._send_error_v59(
            400, error_code="TRIM_START_MUST_BE", error_message="trim_start must be >= 0", retry_safe=False,
        )
    if trim_back is not None and trim_back < 0:
        return h._send_error_v59(
            400, error_code="TRIM_BACK_MUST_BE", error_message="trim_back must be >= 0", retry_safe=False,
        )

    bg = _bg(h)
    sidecar = bg.read_sidecar()
    _, beat = bg.find_beat(sidecar, beat_id)
    if not beat:
        return h._send_error_v59(
            404, error_code="BEAT_NOT_FOUND", error_message=f"beat {beat_id} not found", retry_safe=False,
        )
    if beat.get("pipeline") != "kling_o3_omni":
        return h._send_error_v59(
            400, error_code="NOT_KLING_O3", error_message="beat is not kling_o3_omni", retry_safe=False,
        )
    trim_result: dict = {}

    def _trim(b: dict, _sc: dict) -> None:
        trim_result.update(bg.set_kling_o3_beat_trim(b, trim_start=trim_start, trim_back=trim_back))

    try:
        ok, _beat = bg.update_beat_locked(beat_id, _trim)
    except ValueError as exc:
        return h._send_error_v59(
            400, error_code="TRIM_VALIDATION", error_message=str(exc), retry_safe=False,
        )
    if not ok:
        return h._send_error_v59(
            404, error_code="BEAT_NOT_FOUND", error_message=f"beat {beat_id} not found", retry_safe=False,
        )
    return h._send_json(200, {"ok": True, "beat_id": beat_id, **trim_result})


def _bg_export_scope_key(arc_number: int, bg_event_id: str, phase: str, slot_key: str) -> str:
    return f"{arc_number}|{bg_event_id}|{phase}|{slot_key}"


def _prepare_bg_export_request(h, body: dict) -> dict | None:
    """Validate segment + sync trim seed. Returns context dict or None after HTTP error."""
    pctx = getattr(h, "_production_scope_ctx", None)
    bg = _bg(h)
    if pctx and pctx.is_milestone:
        skel = pctx.skeleton_ref or {}
        arc_number = int(skel.get("arc_number") or 1)
        event_id = str(skel.get("event_id"))
        phase = str(skel.get("phase") or "full")
        slot_key = "standalone"
        data_dir = pctx.root_dir
    else:
        arc_number = int(body.get("arc_number", 1))
        event_id = bg.normalize_bg_event_id(str(body.get("event_id", "1")))
        phase = str(body.get("phase", "pre"))
        video_role = str(body.get("scope_video_role") or body.get("video_role") or "")
        slot_key = (
            body.get("slot_key")
            or bg.resolve_bg_export_stitch_slot(phase=phase, video_role=video_role or None)
        )
        data_dir = h.app.event_dir
    if not slot_key:
        h._send_error_v59(
            400,
            error_code="UNSUPPORTED_PHASE",
            error_message=(
                f"no stitch slot mapping for BG phase {phase!r} "
                f"(supported: pre/intro→intro, post/resolution→resolution, "
                f"phase_a, phase_b; or set scope_video_role)"
            ),
            retry_safe=False,
        )
        return None

    sidecar = bg.read_sidecar()
    seg = bg.get_seg_entry(sidecar, arc_number, event_id, phase)
    beats = list(seg.get("beats") or [])

    if not beats:
        h._send_error_v59(
            400, error_code="NO_BEATS", error_message="segment has no beats", retry_safe=False,
        )
        return None

    not_ready = []
    for beat in beats:
        if not bg.beat_has_stitch_export_clip(beat, data_dir):
            not_ready.append(beat.get("beat_id"))

    if not_ready:
        h._send_error_v59(
            400,
            error_code="BEATS_NOT_APPROVED",
            error_message=(
                f"{len(not_ready)} beat(s) not ready for stitch export "
                "(need approved Kling clip or magic-on-still composite)"
            ),
            retry_safe=False,
            extra={"beat_ids": not_ready},
        )
        return None

    seg_key = f"event_{event_id}_{phase}"
    guide = bg._infer_teleport_intro_guide(sidecar, seg_key)
    trim_seeded = False
    for beat in beats:
        if beat.get("intro_beat_role") == bg.INTRO_BEAT_ROLE_CANONICAL_MIRROR:
            if bg.seed_canonical_intro_tail_export_trim(
                beat,
                guide=guide,
                sidecar=sidecar,
                segment_key=seg_key,
            ):
                trim_seeded = True
    if trim_seeded:
        try:
            bg.write_sidecar(sidecar)
        except Exception as exc:  # noqa: BLE001
            print(f"[BG] export-to-stitcher trim seed persist failed: {exc}", flush=True)

    trim_changed, trim_errors = bg.prepare_beats_for_stitch_export(beats)
    if trim_errors:
        h._send_error_v59(
            400,
            error_code="EXPORT_TRIM_AUTHORITY",
            error_message="; ".join(trim_errors),
            retry_safe=False,
            extra={"beat_ids": [e.split(":")[0] for e in trim_errors], "code": bg.KLING_O3_EXPORT_TRIM_AUTHORITY_V1},
        )
        return None
    if trim_changed:
        try:
            bg.write_sidecar(sidecar)
        except Exception as exc:  # noqa: BLE001
            print(f"[BG] export-to-stitcher trim migrate persist failed: {exc}", flush=True)

    from o3_gallery_option_identity import (  # noqa: PLC0415
        O3GalleryExportAuthorityError,
        normalize_o3_gallery_options,
        assert_beat_export_gallery_authority,
    )

    gallery_errors: list[str] = []
    for beat in beats:
        normalize_o3_gallery_options(beat)
        try:
            assert_beat_export_gallery_authority(beat)
        except O3GalleryExportAuthorityError as exc:
            gallery_errors.append(str(exc))
    if gallery_errors:
        h._send_error_v59(
            400,
            error_code="EXPORT_GALLERY_AUTHORITY",
            error_message="; ".join(gallery_errors),
            retry_safe=False,
            extra={"code": "O3_GALLERY_OPTION_IDENTITY_V1"},
        )
        return None

    scope_key = _bg_export_scope_key(arc_number, event_id, phase, str(slot_key))
    milestone_id = pctx.milestone_id if pctx and pctx.is_milestone else None
    return {
        "arc_number": arc_number,
        "bg_event_id": event_id,
        "phase": phase,
        "slot_key": str(slot_key),
        "scope_key": scope_key,
        "beat_ids": [str(b.get("beat_id")) for b in beats if b.get("beat_id")],
        "beats": beats,
        "data_dir": str(data_dir),
        "milestone_id": milestone_id,
        "stitch_job_name": pctx.stitch_job_name if pctx and pctx.is_milestone else None,
    }


def _load_beats_for_export_job(bg, sidecar: dict, ctx: dict) -> list[dict]:
    """Live segment order at execution time — never a stale submit-time beat_ids snapshot."""
    seg = bg.get_seg_entry(sidecar, ctx["arc_number"], ctx["bg_event_id"], ctx["phase"])
    live_beats = [b for b in (seg.get("beats") or []) if isinstance(b, dict) and b.get("beat_id")]
    if not live_beats:
        raise ValueError("segment has no beats during export")
    frozen_ids = [str(bid) for bid in (ctx.get("beat_ids") or []) if bid]
    live_ids = [str(b.get("beat_id")) for b in live_beats]
    if frozen_ids and frozen_ids != live_ids:
        print(
            "[BG] export-to-stitcher using live segment beat order "
            f"(submit snapshot {len(frozen_ids)} ≠ live {len(live_ids)})",
            flush=True,
        )
    return live_beats


def _run_bg_export_to_stitcher_core(
    h,
    ctx: dict,
    pin: dict,
    *,
    progress_cb=None,
) -> dict:
    """Materialize, concat, upsert stitch slot. Returns ok/error dict (no HTTP)."""
    bg = _bg(h)
    arc_number = ctx["arc_number"]
    event_id = ctx["bg_event_id"]
    phase = ctx["phase"]
    slot_key = ctx["slot_key"]
    data_dir = Path(ctx.get("data_dir") or h.app.event_dir)
    sidecar = bg.read_sidecar()
    beats = _load_beats_for_export_job(bg, sidecar, ctx)

    if progress_cb:
        progress_cb("Concatenating approved beats…", phase="concat", beat_index=0)

    def _materialize_progress(beat_index: int, beat_total: int, _beat_id: str) -> None:
        if progress_cb:
            progress_cb(
                f"Materializing beat {beat_index}/{beat_total}…",
                phase="materialize",
                beat_index=beat_index,
                beat_total=beat_total,
            )

    try:
        out_path, boundaries, duration_s = bg.concat_kling_o3_approved_beats(
            beats,
            data_dir,
            slot_key,
            phase=phase,
            event_id=event_id,
            progress_cb=_materialize_progress,
        )
    except (ValueError, FileNotFoundError) as exc:
        return {
            "ok": False,
            "error_code": "EXPORT_VALIDATION",
            "error_message": str(exc),
            "retry_safe": False,
        }
    except RuntimeError as exc:
        return {
            "ok": False,
            "error_code": "FFMPEG_CONCAT_FAILED",
            "error_message": str(exc),
            "retry_safe": True,
        }

    event_name = data_dir.name
    root = h._stitch_project_root()
    try:
        video_rel = str(out_path.resolve().relative_to(root))
    except ValueError:
        video_rel = f"Production/{event_name}/assembled/{out_path.name}"

    try:
        h._stitch_resolve_path(video_rel)
    except ValueError:
        return {
            "ok": False,
            "error_code": "VIDEO_PATH_OUTSIDE_PROJECT_ROOT",
            "error_message": "export video path outside project root",
            "retry_safe": False,
        }

    from server_handlers.stitch_editor import (  # noqa: PLC0415
        STITCH_EXPORT_MUX_BAKE_V1,
        STITCH_SLOT_EXPORT_FULL_MEDIA_V1,
        STITCH_SLOT_MEDIA_LINEAGE_DURABILITY_V1,
        STITCH_SLOT_VIDEO_LINEAGE_V1,
        stitch_upsert_event_slot,
    )

    if progress_cb:
        progress_cb("Updating Stitcher slot…", phase="upsert")

    if not h._check_event_pin(pin, "bg_export_stitcher_terminal"):
        return {
            "ok": False,
            "error_code": "EVENT_CHANGED_MID_JOB",
            "error_message": "event_changed_mid_job",
            "retry_safe": False,
            "video_path": video_rel,
        }

    stitch_job_name = ctx.get("stitch_job_name")
    stitch_event_key = ctx.get("milestone_id") or event_name
    orig_stitch_state = None
    if stitch_job_name:
        from server_handlers.milestone_scope import stitch_state_for_scope
        from lib.scope_context import ScopeContext

        pctx = getattr(h, "_production_scope_ctx", None)
        if pctx is None and ctx.get("milestone_id"):
            pctx = ScopeContext(
                scope_type="milestone",
                root_dir=data_dir,
                scope_id=str(ctx["milestone_id"]),
                video_role="standalone",
                generation=h.app.event_generation,
                library_event_dir=getattr(h.app, "milestone_library_event_dir", None) or h.app.event_dir,
                prod_root=h.app.event_dir.parent,
                milestone_id=str(ctx["milestone_id"]),
            )
        if pctx:
            orig_stitch_state = h.app.stitch_state
            h.app.stitch_state = stitch_state_for_scope(h.app, pctx)

    try:
        job_name, export_dur_ms, export_warnings, playback_artifacts = stitch_upsert_event_slot(
            h,
            stitch_event_key,
            slot_key,
            {
                "video_path": video_rel,
                "overlay_baked": False,
                "source": f"kling_o3_export_{phase}",
            },
            beat_boundaries=boundaries,
            operator_export=True,
            job_name=stitch_job_name,
        )
    except ValueError as exc:
        return {
            "ok": False,
            "error_code": "STITCH_SLOT_EXPORT_MEDIA_BLOCKED",
            "error_message": str(exc),
            "retry_safe": False,
            "code": STITCH_SLOT_MEDIA_LINEAGE_DURABILITY_V1,
            "export_full_media": STITCH_SLOT_EXPORT_FULL_MEDIA_V1,
        }
    finally:
        if orig_stitch_state is not None:
            h.app.stitch_state = orig_stitch_state

    if any("kept existing export" in (w or "") for w in (export_warnings or [])):
        return {
            "ok": False,
            "error_code": "STITCH_EXPORT_NOT_APPLIED",
            "error_message": (
                f"{slot_key}: stitch slot was not updated "
                "(incoming export not newer than stored video)"
            ),
            "retry_safe": False,
            "code": STITCH_SLOT_VIDEO_LINEAGE_V1,
            "warnings": export_warnings,
            "video_path": video_rel,
        }

    from server_handlers.stitch_editor import (  # noqa: PLC0415
        STITCH_WRITE_TIME_PLAYBACK_ARTIFACTS_V1,
        _playback_artifact_bake_is_mandatory,
    )

    if _playback_artifact_bake_is_mandatory(playback_artifacts or {}):
        return {
            "ok": False,
            "error_code": "STITCH_PLAYBACK_ARTIFACT_BAKE_FAILED",
            "error_message": (
                playback_artifacts.get("error")
                or playback_artifacts.get("skipped")
                or f"{slot_key}: playback artifact bake failed"
            ),
            "retry_safe": True,
            "code": STITCH_WRITE_TIME_PLAYBACK_ARTIFACTS_V1,
            "warnings": export_warnings,
            "video_path": video_rel,
            "playback_artifacts": playback_artifacts,
        }

    from bg_directus_register import (  # noqa: PLC0415
        BG_DIRECTUS_EXPORT_V1,
        persist_directus_export_on_sidecar,
        register_bg_export_to_directus,
    )
    from production_server import _resolve_module_id_for_state  # noqa: PLC0415

    if progress_cb:
        progress_cb("Registering export…", phase="directus")

    directus_result: dict = {"code": BG_DIRECTUS_EXPORT_V1, "warnings": []}
    preserved_clip_count = 0

    def _post_export_sidecar(sidecar_mut: dict) -> None:
        nonlocal directus_result, preserved_clip_count
        preserved_clip_count = bg.preserve_kling_o3_segment_beats(
            sidecar_mut,
            arc_number,
            event_id,
            phase,
            h.app.event_dir,
            reason="send_to_stitcher",
        )
        clip_paths, _scratch = bg.resolve_segment_stitch_export_clip_paths(
            beats,
            h.app.event_dir,
            phase=phase,
            event_name=event_name,
            event_id=event_id,
        )
        directus_result = register_bg_export_to_directus(
            beats=beats,
            clip_paths=clip_paths,
            concat_path=out_path,
            module_id=_resolve_module_id_for_state(h.app.state),
            event_dir=h.app.event_dir,
            slot_key=slot_key,
            phase=phase,
            boundaries=boundaries,
            duration_s=duration_s,
        )
        persist_directus_export_on_sidecar(
            sidecar_mut,
            arc_number=arc_number,
            event_id=event_id,
            phase=phase,
            directus_result=directus_result,
        )

    try:
        from beatgen_scope import scope_from_app  # noqa: PLC0415

        export_scope = scope_from_app(h.app)
        bg.mutate_sidecar_locked(
            _post_export_sidecar,
            scope=export_scope,
            caller="export_to_stitcher_post",
        )
    except Exception as exc:
        print(f"[BG] export-to-stitcher directus/preserve failed: {exc}", flush=True)
        directus_result.setdefault("warnings", []).append(f"sidecar persist failed: {exc}")

    all_warnings = list(export_warnings or [])
    all_warnings.extend(directus_result.get("warnings") or [])

    return {
        "ok": True,
        "job_name": job_name,
        "slot_key": slot_key,
        "video_path": video_rel,
        "duration_s": duration_s,
        "video_dur_ms": export_dur_ms,
        "warnings": all_warnings,
        "beat_count": len(beats),
        "beat_boundaries": boundaries,
        "code": STITCH_SLOT_MEDIA_LINEAGE_DURABILITY_V1,
        "export_full_media": STITCH_SLOT_EXPORT_FULL_MEDIA_V1,
        "directus": directus_result,
        "preserved_clip_count": preserved_clip_count,
        "playback_artifacts": playback_artifacts,
        "export_mux_bake": STITCH_EXPORT_MUX_BAKE_V1,
    }


def _execute_bg_export_to_stitcher_job(
    h,
    *,
    job_id: str,
    scope_key: str,
    ctx: dict,
    pin: dict,
    lock_path: Path,
) -> None:
    from bg_export_stitcher_job_store import (  # noqa: PLC0415
        finalize_job,
        update_job_progress,
    )

    pin = dict(pin)
    pin["_export_job_id"] = job_id
    fd = None
    store_dir = Path(ctx.get("data_dir") or h.app.event_dir)
    from beatgen_scope import run_in_beatgen_scope  # noqa: PLC0415

    def _worker_body():
        nonlocal fd
        try:
            import fcntl  # noqa: PLC0415

            fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR)
            fcntl.flock(fd, fcntl.LOCK_EX)

            update_job_progress(
                store_dir,
                job_id,
                status="running",
                phase="materialize",
                message="Preparing export clips…",
                beat_index=0,
                beat_total=len(ctx.get("beat_ids") or []),
            )

            def _job_progress(
                message: str,
                *,
                phase: str | None = None,
                beat_index: int | None = None,
                beat_total: int | None = None,
            ) -> None:
                kwargs: dict = {
                    "status": "running",
                    "phase": phase or "materialize",
                    "message": message,
                }
                if beat_index is not None:
                    kwargs["beat_index"] = beat_index
                if beat_total is not None:
                    kwargs["beat_total"] = beat_total
                update_job_progress(store_dir, job_id, **kwargs)

            result = _run_bg_export_to_stitcher_core(h, ctx, pin, progress_cb=_job_progress)
            if result.get("ok"):
                finalize_job(store_dir, job_id, "done", result=result)
                return

            finalize_job(
                store_dir,
                job_id,
                "failed",
                error=result.get("error_message") or "Export failed",
                error_code=result.get("error_code"),
                result=result,
            )
        except Exception as exc:
            traceback.print_exc()
            finalize_job(
                store_dir,
                job_id,
                "failed",
                error=str(exc),
                error_code="BG_EXPORT_STITCHER_EXCEPTION",
            )
        finally:
            if fd is not None:
                try:
                    import fcntl  # noqa: PLC0415

                    fcntl.flock(fd, fcntl.LOCK_UN)
                    os.close(fd)
                except OSError:
                    pass

    bg = _bg(h)
    run_in_beatgen_scope(h.app, bg, _worker_body)


def handle_bg_export_to_stitcher(h, body: dict) -> None:
    """POST /api/bg/export-to-stitcher — async job; poll GET /api/bg/poll-export-to-stitcher."""
    from beatgen_scope import log_beatgen_mutation, scope_from_current_globals  # noqa: PLC0415
    from bg_export_stitcher_job_store import (  # noqa: PLC0415
        BG_EXPORT_TO_STITCHER_ASYNC_V1,
        create_job,
        export_lock_is_free,
        export_lock_path,
        find_active_job_for_scope_key,
        job_poll_payload,
        new_job_id,
        reconcile_stale_running_jobs,
    )

    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return

    _pin = {
        "pinned_generation": h.app.event_generation,
        "pinned_event_dir": h.app.event_dir,
        "pinned_video_role": (body or {}).get("scope_video_role") or (body or {}).get("scope_target_video"),
        "_handler": "_handle_bg_export_to_stitcher",
    }
    if not h._check_event_pin(_pin, "_handle_bg_export_to_stitcher_pre_work"):
        return h._send_error_v59(
            423,
            error_code="EVENT_CHANGED_PRE_WORK",
            error_message="event_changed_pre_work",
            retry_safe=False,
            extra={
                "code": "ASYNC_JOB_GENERATION_PIN_V1",
                "handler": "_handle_bg_export_to_stitcher",
                "hint": (
                    "Event changed between scope-guard and work start. "
                    "No work was done; client should re-hydrate scope and retry."
                ),
            },
        )

    ctx = _prepare_bg_export_request(h, body)
    if ctx is None:
        return

    bg = _bg_module()
    scope = scope_from_current_globals(bg)
    log_beatgen_mutation(
        operation="export_to_stitcher",
        beat_id=str(ctx.get("scope_key") or scope.event_id or "segment"),
        scope=scope,
        caller="handle_bg_export_to_stitcher",
        extra={"phase": ctx.get("phase"), "video_role": ctx.get("video_role")},
    )

    data_dir = Path(ctx.get("data_dir") or h.app.event_dir)
    lock_path = export_lock_path(data_dir)
    reconcile_stale_running_jobs(data_dir, lock_path)

    existing = find_active_job_for_scope_key(data_dir, ctx["scope_key"])
    if existing:
        payload = job_poll_payload(existing)
        payload.update({"ok": True, "reattach": True})
        return h._send_json(200, payload)

    if not export_lock_is_free(lock_path):
        return h._send_error_v59(
            409,
            error_code="EXPORT_ALREADY_IN_PROGRESS",
            error_message="Another Send to Stitcher export is in progress for this scope",
            retry_safe=False,
            extra={"code": BG_EXPORT_TO_STITCHER_ASYNC_V1},
        )

    scope_body = h._scope_body(body)
    scope_event_id = str(
        scope_body.get("scope_milestone_id")
        or scope_body.get("scope_event_id")
        or scope_body.get("event_id")
        or data_dir.name
    )
    job_id = new_job_id()
    create_job(
        data_dir,
        job_id=job_id,
        scope_key=ctx["scope_key"],
        scope_event_id=scope_event_id,
        arc_number=ctx["arc_number"],
        bg_event_id=ctx["bg_event_id"],
        phase=ctx["phase"],
        slot_key=ctx["slot_key"],
        beat_ids=ctx["beat_ids"],
        pin=_pin,
    )

    worker = threading.Thread(
        target=_execute_bg_export_to_stitcher_job,
        args=(h,),
        kwargs={
            "job_id": job_id,
            "scope_key": ctx["scope_key"],
            "ctx": ctx,
            "pin": _pin,
            "lock_path": lock_path,
        },
        daemon=True,
        name=f"bg-export-stitch-{job_id}",
    )
    worker.start()

    job_record = find_active_job_for_scope_key(data_dir, ctx["scope_key"]) or {"job_id": job_id}
    payload = job_poll_payload(job_record)
    payload.update({"ok": True, "submitted": True})
    return h._send_json(202, payload)


def handle_bg_poll_export_to_stitcher_status(h) -> None:
    """GET /api/bg/poll-export-to-stitcher?job_id= — poll async export job."""
    import urllib.parse  # noqa: PLC0415

    from bg_export_stitcher_job_store import (  # noqa: PLC0415
        BG_EXPORT_TO_STITCHER_ASYNC_V1,
        export_job_store_roots,
        export_lock_path,
        find_export_job,
        job_poll_payload,
        reconcile_stale_running_jobs,
    )

    qs = urllib.parse.parse_qs(urllib.parse.urlparse(h.path).query)
    job_id = (qs.get("job_id") or [""])[0].strip()
    if not job_id:
        return h._send_error_v59(
            400,
            error_code="JOB_ID_REQUIRED",
            error_message="job_id required",
            retry_safe=False,
            extra={"code": BG_EXPORT_TO_STITCHER_ASYNC_V1},
        )

    store_roots = export_job_store_roots(
        h.app.event_dir,
        app_milestone_dir=getattr(h.app, "milestone_dir", None),
    )
    found = find_export_job(store_roots, job_id)
    if not found:
        return h._send_error_v59(
            404,
            error_code="EXPORT_JOB_NOT_FOUND",
            error_message=f"no export job found for job_id={job_id}",
            retry_safe=False,
            extra={"code": BG_EXPORT_TO_STITCHER_ASYNC_V1},
        )

    store_dir, job = found
    lock_path = export_lock_path(store_dir)
    reconcile_stale_running_jobs(store_dir, lock_path)
    job = find_export_job([store_dir], job_id)
    if not job:
        return h._send_error_v59(
            404,
            error_code="EXPORT_JOB_NOT_FOUND",
            error_message=f"no export job found for job_id={job_id}",
            retry_safe=False,
            extra={"code": BG_EXPORT_TO_STITCHER_ASYNC_V1},
        )
    _, job = job

    payload = job_poll_payload(job)
    payload["ok"] = True
    return h._send_json(200, payload)
