#!/usr/bin/env python3
"""Beat Gen speak pipeline — ElevenLabs TTS + Kling Avatar Pro + 720 delivery encode."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import beat_generator as bg_sidecar  # noqa: E402
import kling_character_registry as reg  # noqa: E402
from kling_stitch_readiness import active_delivery_sidecar_fields  # noqa: E402
from arlo_o3_voice_pipeline import (  # noqa: E402
    _clean_bg_text,
    _delivery_video,
    _event_dir_for_segment,
    _find_beat,
    _is_user_selectable_o3_video,
    _probe_video_size,
    _restore_prior_video_state,
    _safe_slug,
    _write_elevenlabs_audio,
)
from beat_avatar_lipsync import (  # noqa: E402
    KLING_O3_MODE_AVATAR,
    O3_OPTION_SOURCE_AVATAR,
    avatar_pro_padding_metadata,
    build_avatar_beat_prompt,
    encode_avatar_pro_delivery,
    prepare_avatar_pro_audio,
    resolve_beat_avatar_still,
)
from kling_o3_element_beat_pipeline import _runtime_prod_root  # noqa: E402
from kling_startend_pipeline import load_api_keys  # noqa: E402
from lipsync_sender import LipSyncClient  # noqa: E402


def _touch_o3_job_heartbeat(beat_id: str, event_dir: Path) -> None:
    """Keep session GET ``job_busy`` true during long Avatar Pro WaveSpeed polls."""
    job_id = _job_id_from_env()
    if not job_id:
        return
    try:
        from o3_generation_intent import touch_o3_job_heartbeat

        touch_o3_job_heartbeat(job_id, _intent_event_dir_from_env(beat_id, event_dir))
    except Exception:
        pass


def _avatar_poll_with_heartbeat(
    task_id: str,
    api_key: str,
    *,
    beat_id: str,
    event_dir: Path,
    timeout_s: int = 900,
) -> dict:
    import time

    _touch_o3_job_heartbeat(beat_id, event_dir)
    start = time.time()
    last_touch = start
    path = f"/api/v3/predictions/{task_id}/result"
    last_status = None
    while time.time() - start < timeout_s:
        now = time.time()
        if now - last_touch >= 45:
            _touch_o3_job_heartbeat(beat_id, event_dir)
            last_touch = now
        try:
            import http.client
            import json as _json
            import ssl

            ctx = ssl.create_default_context()
            ctx.options |= ssl.OP_NO_TICKET | ssl.OP_NO_COMPRESSION
            conn = http.client.HTTPSConnection("api.wavespeed.ai", timeout=20, context=ctx)
            try:
                conn.request(
                    "GET",
                    path,
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                resp = conn.getresponse()
                body = resp.read().decode("utf-8", errors="replace")
            finally:
                conn.close()
            data = _json.loads(body).get("data", {})
            status = (data.get("status") or "").lower()
            if status != last_status:
                print(
                    _json.dumps({
                        "phase": "avatar_poll",
                        "beat_id": beat_id,
                        "task_id": task_id,
                        "t_s": int(now - start),
                        "status": status,
                    }),
                    flush=True,
                )
                last_status = status
            if status in ("completed", "failed", "error"):
                return data
        except Exception as exc:
            print(
                json.dumps({
                    "phase": "avatar_poll_err",
                    "beat_id": beat_id,
                    "task_id": task_id,
                    "error": str(exc)[:200],
                }),
                flush=True,
            )
        time.sleep(5)
    return {"status": "timeout"}


def _job_id_from_env() -> str:
    raw = (os.environ.get("MN_O3_INTENT_PATH") or "").strip()
    if raw:
        stem = Path(raw).stem
        if stem.endswith("_intent"):
            return stem[: -len("_intent")]
    log_raw = (os.environ.get("MN_O3_JOB_LOG") or "").strip()
    if log_raw:
        stem = Path(log_raw).stem
        if "_" in stem:
            return stem.split("_", 1)[0]
    return ""


def _intent_event_dir_from_env(beat_id: str, fallback: Path) -> Path:
    for key in ("MN_O3_INTENT_PATH", "MN_O3_JOB_LOG"):
        raw = (os.environ.get(key) or "").strip()
        if not raw:
            continue
        path = Path(raw).expanduser().resolve()
        if path.parent.name == "arlo_o3_jobs":
            return path.parent.parent
    from o3_generation_intent import intent_event_dir_for_beat

    return intent_event_dir_for_beat(beat_id, fallback)


def _load_intent_snapshot() -> dict:
    raw = (os.environ.get("MN_O3_INTENT_PATH") or "").strip()
    if not raw:
        return {}
    try:
        from o3_generation_intent import load_generation_intent

        return load_generation_intent(Path(raw).expanduser().resolve())
    except Exception:
        return {}


def _write_avatar_intent_terminal(
    *,
    beat_id: str,
    event_dir: Path,
    status: str,
    video_path: str | None = None,
    duration_s: float | None = None,
    failure_message: str | None = None,
    phase_last: str,
    sidecar_persist_ok: bool = True,
) -> None:
    job_id = _job_id_from_env()
    if not job_id:
        return
    intent_event_dir = _intent_event_dir_from_env(beat_id, event_dir)
    intent = _load_intent_snapshot()
    from o3_generation_intent import write_intent_terminal

    body: dict = {
        "intent_id": intent.get("intent_id"),
        "beat_id": beat_id,
        "status": status,
        "phase_last": phase_last,
        "sidecar_persist_ok": sidecar_persist_ok,
    }
    if status in ("done", "done_with_warning") and video_path:
        body["delivered"] = {
            "video_path": str(video_path),
            "duration_s": round(float(duration_s or 0), 3) if duration_s is not None else None,
        }
        body["failure"] = None
    elif status == "failed":
        body["failure"] = {"message": (failure_message or "Avatar Pro job failed")[:1500]}
    write_intent_terminal(job_id, intent_event_dir, body)


def _upsert_avatar_option(beat: dict, *, video_path: str, active: bool, now: str) -> None:
    if not _is_user_selectable_o3_video(video_path):
        return
    slot_index = int(beat.get("kling_o3_replace_slot_index") or 0)
    bg_sidecar.assign_kling_o3_option_to_slot(
        beat,
        slot_index,
        video_path=video_path,
        label="Avatar Pro (latest)",
        source=O3_OPTION_SOURCE_AVATAR,
        now=now,
        make_active=active,
    )


def _next_avatar_generation(beat: dict) -> int:
    """Monotonic g{N} for avatar outputs — never reuse a delivery path when filling another slot."""
    max_gen = int(beat.get("kling_o3_generation") or 0)
    for opt in beat.get("kling_o3_options") or []:
        if not isinstance(opt, dict):
            continue
        gen = bg_sidecar._kling_o3_gen_from_video_path(str(opt.get("video_path") or ""))
        if gen is not None:
            max_gen = max(max_gen, int(gen))
    prior = str(beat.get("kling_o3_video_path") or "")
    if prior and "_avatar_pro" in prior.lower() and "_g" not in Path(prior).name.lower():
        max_gen = max(max_gen, 1)
    return max_gen + 1


def _avatar_clip_paths(clips_dir: Path, beat_id: str, *, generation: int) -> tuple[Path, Path]:
    """Raw master + delivery paths for this generation (delivery suffix matches _delivery_video)."""
    raw = clips_dir / f"{beat_id}_g{generation}_avatar_pro.mp4"
    delivery = raw.with_name(f"{raw.stem}_delivery.mp4")
    return raw, delivery


def run_pipeline(beat_id: str, *, sharpen: bool = True, attempt_id: str | None = None) -> dict:
    attempt_id = attempt_id or os.environ.get("MN_O3_ATTEMPT_ID") or __import__("uuid").uuid4().hex
    print(json.dumps({
        "phase": "starting",
        "beat_id": beat_id,
        "pipeline": "avatar_pro",
        "attempt_id": attempt_id,
    }), flush=True)
    prod_root = _runtime_prod_root()
    reg.set_prod_root(prod_root)
    from o3_subprocess_bootstrap import load_o3_beat_context

    beat, segment_key, sidecar_path, event_dir = load_o3_beat_context(beat_id)
    _touch_o3_job_heartbeat(beat_id, event_dir)
    backup_dir = event_dir / "_avatar_backups" / (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"_pre_avatar_{beat_id}"
    )
    backup_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(sidecar_path, backup_dir / "beat_generator_state.json")
    speaker = (beat.get("speaker") or "").strip()
    if not speaker:
        raise RuntimeError(f"{beat_id} has no speaker")
    speaker_slug = _safe_slug(speaker)
    now = datetime.now(timezone.utc).isoformat()
    prior_video = beat.get("kling_o3_video_path")
    prior_status = beat.get("kling_o3_status")
    prior_beat_status = beat.get("status")
    avatar_generation = _next_avatar_generation(beat)

    def persist(
        fields: dict | None = None,
        *,
        remove: tuple[str, ...] = (),
        expected: bool = True,
        coherence_mode: str | None = None,
    ) -> None:
        if fields:
            beat.update(fields)

        def apply(current: dict, sidecar: dict) -> None:
            if fields:
                current.update(fields)
            for key in remove:
                current.pop(key, None)
            if coherence_mode:
                bg_sidecar.stamp_o3_delivery_pipeline_coherence(
                    current,
                    sidecar,
                    generation_mode=coherence_mode,
                )

        ok, _current = bg_sidecar.update_beat_locked(
            beat_id,
            apply,
            expected_attempt_id=attempt_id if expected else None,
        )
        if not ok and expected:
            raise RuntimeError(f"{beat_id} attempt {attempt_id} was superseded before sidecar update")

    keys = load_api_keys()
    still = resolve_beat_avatar_still(beat)
    spoken = _clean_bg_text(beat.get("dialogue_text") or "")
    print(json.dumps({"phase": "tts_start", "beat_id": beat_id, "spoken_text": spoken}), flush=True)
    audio, profile, voice_model, audio_dur = _write_elevenlabs_audio(
        event_dir=event_dir,
        beat_id=beat_id,
        speaker=speaker,
        text=spoken,
        keys=keys,
    )
    generate_mode = bg_sidecar.O3_GENERATE_MODE_AVATAR
    persist({
        "status": "arlo_avatar_running",
        "kling_o3_status": "visual_running",
        "kling_o3_generate_mode": generate_mode,
        "o3_generate_mode": generate_mode,
        "generation_mode": generate_mode,
        "kling_o3_voice_fix_attempt_id": attempt_id,
        "kling_o3_voice_fix_status": "avatar_running",
        "kling_o3_voice_fix_phase": "tts",
        "kling_o3_voice_fix_updated_at": now,
        "kling_o3_voice_fix_audio_path": str(audio),
        "kling_o3_voice_fix_spoken_text": spoken,
        "kling_o3_voice_fix_audio_duration_s": round(audio_dur, 3),
        "kling_o3_voice_fix_lipsync_transport": "avatar_pro_data_uri",
    }, expected=False)

    padded_audio, spoken_duration_s, padded_duration_s = prepare_avatar_pro_audio(audio)
    padding_meta = avatar_pro_padding_metadata(
        spoken_duration_s=spoken_duration_s,
        padded_duration_s=padded_duration_s,
    )
    padding_meta["kling_o3_voice_fix_audio_padded_path"] = (
        str(padded_audio) if padded_audio.resolve() != audio.resolve() else None
    )
    print(json.dumps({
        "phase": "avatar_audio_pad",
        "beat_id": beat_id,
        "spoken_duration_s": spoken_duration_s,
        "padded_duration_s": padded_duration_s,
        "padding_applied": padding_meta["kling_o3_voice_fix_audio_padding_applied"],
    }), flush=True)
    persist({
        **padding_meta,
        "kling_o3_voice_fix_updated_at": datetime.now(timezone.utc).isoformat(),
    }, expected=False)

    prompt = build_avatar_beat_prompt(beat, speaker=speaker)
    client = LipSyncClient(keys["wavespeed"])
    print(json.dumps({"phase": "avatar_submit", "beat_id": beat_id, "still": still.name}), flush=True)
    try:
        task_id = client.submit_avatar_pro(still, padded_audio, prompt)
    finally:
        if padded_audio.resolve() != audio.resolve() and padded_audio.is_file():
            try:
                padded_audio.unlink()
            except OSError:
                pass
    persist({
        "kling_o3_voice_fix_task_id": task_id,
        "kling_o3_voice_fix_status": "avatar_running",
        "kling_o3_voice_fix_phase": "avatar_poll",
        "kling_o3_voice_fix_updated_at": datetime.now(timezone.utc).isoformat(),
    })

    print(json.dumps({"phase": "avatar_poll", "beat_id": beat_id, "task_id": task_id}), flush=True)
    result = _avatar_poll_with_heartbeat(
        task_id,
        keys["wavespeed"],
        beat_id=beat_id,
        event_dir=event_dir,
        timeout_s=900,
    )
    if (result.get("status") or "").lower() != "completed":
        _restore_prior_video_state(
            beat,
            prior_video=prior_video,
            prior_status=prior_status,
            prior_beat_status=prior_beat_status,
        )
        fail_msg = f"Avatar Pro failed: {result}"
        persist({
            "status": beat.get("status") or "arlo_avatar_failed",
            "kling_o3_status": beat.get("kling_o3_status") or "failed",
            "kling_o3_video_path": beat.get("kling_o3_video_path"),
            "kling_o3_voice_fix_status": "failed_avatar",
            "kling_o3_voice_fix_error_code": "AVATAR_FAILED",
            "kling_o3_voice_fix_error": json.dumps(result)[:1000],
            "kling_o3_voice_fix_completed_at": datetime.now(timezone.utc).isoformat(),
        }, remove=("kling_o3_voice_fix_ui_job_id",))
        _write_avatar_intent_terminal(
            beat_id=beat_id,
            event_dir=event_dir,
            status="failed",
            failure_message=fail_msg,
            phase_last="avatar_poll",
            sidecar_persist_ok=True,
        )
        raise RuntimeError(fail_msg)

    clips_dir = event_dir / "kling_o3_clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    raw, delivery_target = _avatar_clip_paths(clips_dir, beat_id, generation=avatar_generation)
    client.download((result.get("outputs") or [None])[0], raw)
    active, delivery_meta = encode_avatar_pro_delivery(raw, delivery_target)
    if active.resolve() != delivery_target.resolve():
        shutil.move(str(active), str(delivery_target))
        active = delivery_target
    del_w, del_h = _probe_video_size(active)
    out_dur = float(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(active),
    ], text=True).strip())
    completed = datetime.now(timezone.utc).isoformat()
    quality = {
        "path": str(raw),
        "delivery_path": str(active),
        "delivery_width": del_w,
        "delivery_height": del_h,
        "delivery_min_dimension": min(del_w, del_h),
        "transport": "avatar_pro_data_uri",
        "kid_facing_gate": "LD-296 delivery encode",
    }
    final_fields = {
        **active_delivery_sidecar_fields(active, mark_voice_fix_approved=True),
        "kling_o3_mode": KLING_O3_MODE_AVATAR,
        "kling_o3_generate_mode": generate_mode,
        "o3_generate_mode": generate_mode,
        "generation_mode": generate_mode,
        "kling_o3_completed_at": completed,
        "kling_o3_generation": avatar_generation,
        "kling_o3_actual_duration_s": round(out_dur, 3),
        "kling_o3_voice_fix_phase": "finalize",
        "kling_o3_voice_fix_completed_at": completed,
        "kling_o3_voice_fix_result": result,
        "kling_o3_voice_fix_output_profile": quality,
        "kling_o3_voice_fix_output_duration_s": round(out_dur, 3),
        "kling_o3_voice_fix_lipsync_transport": "avatar_pro_data_uri",
    }
    from o3_generation_intent import load_intent_visual_ref_fields_from_env

    final_fields.update(load_intent_visual_ref_fields_from_env())
    beat.update(final_fields)
    _upsert_avatar_option(beat, video_path=str(active), active=True, now=completed)
    with bg_sidecar._sidecar_lock:
        sc_for_sync = bg_sidecar.read_sidecar()
    bg_sidecar.sync_o3_selection_pipeline_fields(beat, sc_for_sync)
    final_fields["kling_o3_options"] = beat.get("kling_o3_options")
    final_fields["kling_o3_selected_option_key"] = beat.get("kling_o3_selected_option_key")
    if beat.get("kling_o3_active_clip_pipeline"):
        final_fields["kling_o3_active_clip_pipeline"] = beat["kling_o3_active_clip_pipeline"]
    beat.pop("kling_o3_selection_pipeline_mismatch", None)
    final_fields["arlo_visual_quality"] = {
        "speaker": speaker,
        "delivery_profile": delivery_meta.get("delivery_profile"),
        "delivery_recipe": delivery_meta.get("delivery_recipe"),
        "sharpened_delivery": delivery_meta.get("sharpen"),
        "avatar_still_path": str(still),
        "avatar_master_video_path": str(raw),
        "playback_video_path": str(active),
        "active_video_path": str(active),
        "method": "ElevenLabs voice + Kling Avatar Pro + voice_first_upscale delivery",
        "applied_at": completed,
    }
    persist(
        final_fields,
        remove=("kling_o3_voice_fix_ui_job_id", "kling_o3_voice_fix_error", "kling_o3_voice_fix_error_code"),
        coherence_mode=generate_mode,
    )
    bg_sidecar.auto_pin_approved_kling_o3_delivery(beat, event_dir)
    _write_avatar_intent_terminal(
        beat_id=beat_id,
        event_dir=event_dir,
        status="done",
        video_path=str(active),
        duration_s=out_dur,
        phase_last="finalize",
        sidecar_persist_ok=True,
    )
    return {
        "ok": True,
        "beat_id": beat_id,
        "video": str(active),
        "duration_s": round(out_dur, 3),
        "avatar_task_id": task_id,
        "pipeline": "avatar_pro",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--beat-id", required=True)
    parser.add_argument("--no-sharpen", action="store_true")
    parser.add_argument("--attempt-id", default=None)
    args = parser.parse_args()
    print(json.dumps(run_pipeline(
        args.beat_id,
        sharpen=not args.no_sharpen,
        attempt_id=args.attempt_id,
    )))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
