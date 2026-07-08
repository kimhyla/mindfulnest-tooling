#!/usr/bin/env python3
"""Canonical Beat Gen O3 path: Element + ElevenLabs create-voice + native O3 audio.

One WaveSpeed O3 Pro reference-to-video call (sound:true, element_list).
No silent O3, no separate ElevenLabs mp3, no WaveSpeed lipsync, no resolution flip-flop.
Always finishes with LD-284/LD-296 delivery encode (1280x720 kid-facing).
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROD = HERE.parent
_tooling_tools = os.environ.get("MN_TOOLING_TOOLS", "").strip()
if _tooling_tools:
    _tooling_path = Path(_tooling_tools).resolve()
    if _tooling_path.is_dir() and str(_tooling_path) not in sys.path:
        sys.path.insert(0, str(_tooling_path))
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
if str(PROD) not in sys.path:
    sys.path.insert(0, str(PROD))

import beat_generator as bg_sidecar  # noqa: E402
from kling_stitch_readiness import active_delivery_sidecar_fields  # noqa: E402
from video_delivery import encode_delivery_video  # noqa: E402


def _load_build_prompt():
    return bg_sidecar.build_kling_o3_prompt, bg_sidecar._kling_o3_normalize_spoken


def _inject_locked_voice(prompt: str, speaker: str, spoken: str) -> str:
    from tools import kling_o3_prompt as o3p

    locked = o3p.voice_block(speaker, spoken)
    lines = prompt.splitlines()
    out: list[str] = []
    replaced = False
    voice_line_re = re.compile(r"\b(speaks|says)\b", re.I)
    for line in lines:
        low = line.lower()
        if not replaced and (voice_line_re.search(line) or "<<<voice_" in low):
            if "speaks in a" in low:
                colon = re.search(r":\s*", line)
                if colon:
                    head = line[: colon.end()].rstrip()
                    out.append(f'{head} "{spoken}"')
                else:
                    out.append(locked)
            else:
                out.append(locked)
            replaced = True
        else:
            out.append(line)
    if replaced:
        return "\n".join(out)
    marker = "Children's illustrated"
    idx = prompt.find(marker)
    if idx < 0:
        return f"{prompt.rstrip()}\n\n{locked}\n"
    return f"{prompt[:idx].rstrip()}\n\n{locked}\n\n{prompt[idx:]}"


def _spoken_from_beat(beat: dict, normalize_fn) -> str:
    dialogue = (beat.get("dialogue_text") or "").strip()
    spoken = re.sub(r"\[[^\]]+\]", " ", dialogue)
    spoken = normalize_fn(re.sub(r"\s+", " ", spoken).strip())
    return spoken or normalize_fn(dialogue)


def resolve_element_o3_submit_prompt(beat: dict) -> tuple[str, str]:
    """Return (kling_prompt, spoken_log). Operator prompt goes verbatim to WaveSpeed."""
    stored_prompt = (beat.get("kling_o3_prompt") or "").strip()
    if stored_prompt:
        spoken = bg_sidecar.extract_spoken_dialogue_from_kling_prompt(stored_prompt) or ""
        return stored_prompt, spoken
    build_prompt, normalize_spoken = _load_build_prompt()
    speaker = str(beat.get("speaker") or "").strip()
    spoken = _spoken_from_beat(beat, normalize_spoken)
    return _inject_locked_voice(build_prompt(beat), speaker, spoken), spoken


def _find_beat(sidecar: dict, beat_id: str):
    for arc in (sidecar.get("arcs") or {}).values():
        for segment_key, segment in (arc.get("segments") or {}).items():
            for beat in segment.get("beats") or []:
                if isinstance(beat, dict) and beat.get("beat_id") == beat_id:
                    return beat, str(segment_key)
    return None


def _runtime_prod_root() -> Path:
    """Dropbox Production root when MN_PROD_ROOT is set (server subprocess path)."""
    from lib.paths import normalize_production_root

    raw = os.environ.get("MN_PROD_ROOT", "").strip()
    if raw:
        root = Path(raw)
        if not root.is_absolute():
            cwd = Path.cwd().resolve()
            # Legacy bug: MN_PROD_ROOT="Production" with cwd already inside Production/.
            if cwd.name == "Production" and root.name == "Production":
                return normalize_production_root(cwd)
            root = cwd / root
        return normalize_production_root(root.resolve())
    return normalize_production_root(PROD.resolve())


def _event_dir_for_segment(prod_root: Path, segment_key: str) -> Path:
    match = re.match(r"event_(\d+)_", segment_key or "")
    if match:
        return prod_root / f"Event_{match.group(1)}"
    return prod_root / "Event_1"


def _ref_path(value) -> Path:
    if isinstance(value, dict):
        return Path(value.get("abs_path") or value.get("path") or "")
    return Path(value or "")


def _probe(path: Path) -> dict:
    raw = subprocess.check_output(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height", "-of", "json", str(path),
        ],
        text=True,
    )
    streams = json.loads(raw).get("streams") or [{}]
    width = int(streams[0].get("width") or 0)
    height = int(streams[0].get("height") or 0)
    audio = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "a:0",
            "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(path),
        ],
        capture_output=True,
        text=True,
    )
    has_audio = audio.returncode == 0 and "audio" in (audio.stdout or "")
    min_dim = min(width, height) if width and height else 0
    return {
        "width": width,
        "height": height,
        "min_dimension": min_dim,
        "has_audio": has_audio,
        "gate_pass": bool(has_audio and min_dim >= 720),
    }


def _option_key(beat_id: str, video_path: str) -> str:
    digest = hashlib.sha1(video_path.encode("utf-8")).hexdigest()[:10]
    return f"{beat_id}_o3_video_{digest}"


def _upsert_option(beat: dict, *, video_path: str, label: str, now: str, o3_voice_binding: dict | None = None) -> None:
    import beat_generator as bg_sidecar  # noqa: PLC0415

    slot_index = int(beat.get("kling_o3_replace_slot_index") or 0)
    bg_sidecar.assign_kling_o3_option_to_slot(
        beat,
        slot_index,
        video_path=video_path,
        label=label,
        source="kling_o3_element_native_voice",
        now=now,
        make_active=True,
        o3_voice_binding=o3_voice_binding,
    )


def run_pipeline_from_intent(
    intent: dict,
    *,
    sharpen: bool = False,
) -> dict:
    """Execute O3 pipeline using immutable generation intent only."""
    from tools.credentials_lib.credentials import load_credentials
    from tools import kling_o3_client as o3
    from o3_generation_intent import sidecar_visual_ref_fields_from_intent, write_intent_terminal

    beat_id = str(intent.get("beat_id") or "").strip()
    attempt_id = str((intent.get("runtime") or {}).get("attempt_id") or "")
    env_attempt = (os.environ.get("MN_O3_ATTEMPT_ID") or "").strip()
    if env_attempt:
        attempt_id = env_attempt
    prompt_block = intent.get("prompt") or {}
    visual = intent.get("visual") or {}
    voice = intent.get("voice") or {}
    generation = intent.get("generation") or {}
    job_id = str(intent.get("job_id") or "").strip()

    submit_prompt = str(prompt_block.get("prepared_for_api") or prompt_block.get("verbatim") or "")
    spoken = str(prompt_block.get("spoken_sent") or "")
    char_path = Path(str(visual.get("char_ref_abs_path") or ""))
    bg_path = Path(str(visual.get("bg_ref_abs_path") or ""))
    if not char_path.is_file() or not bg_path.is_file():
        raise RuntimeError("intent char_ref or bg_ref missing on disk")
    gen = int(generation.get("slot_index") or 0)
    if gen < 1:
        raise RuntimeError("invalid intent generation slot")
    master = Path(str(generation.get("master_clip_path") or ""))
    delivery = Path(str(generation.get("delivery_clip_path") or ""))
    duration = int(generation.get("duration") or 5)
    element_entry = {
        "element_id": voice.get("element_id"),
        "element_name": voice.get("element_name"),
        "voice_id": voice.get("kling_voice_id"),
    }
    speaker = str(voice.get("speaker") or "").strip()

    prod_root = _runtime_prod_root()
    from o3_subprocess_bootstrap import init_bg_paths_for_o3_subprocess

    # Same sidecar authority as HTTP submit (milestone JSON, not global SQLite).
    event_dir = init_bg_paths_for_o3_subprocess(beat_id=beat_id, prod_root=prod_root)

    print(json.dumps({
        "phase": "o3_submit",
        "beat_id": beat_id,
        "intent_id": intent.get("intent_id"),
        "speaker": speaker,
        "element": element_entry,
        "char_ref": str(char_path),
        "bg_ref": str(bg_path),
        "char_ref_aligned": True,
        "prompt_sha256": prompt_block.get("sha256"),
        "prompt_verbatim": True,
        "prompt_prepared": submit_prompt != prompt_block.get("verbatim"),
        "prompt_voice_excerpt": submit_prompt[:500],
        "spoken_sent": spoken,
        "kling_o3_duration": duration,
        "generation_slot": generation.get("slot"),
    }), flush=True)

    creds = load_credentials()
    api_key = creds.get("wavespeed_key") or creds.get("wavespeed")
    if not api_key:
        raise RuntimeError("Missing wavespeed API key")

    def persist(fields: dict | None = None, *, remove: tuple[str, ...] = (), coherence_mode: str | None = None):
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

        expected = attempt_id or None
        ok, live = bg_sidecar.update_beat_locked(
            beat_id,
            apply,
            expected_attempt_id=expected,
        )
        if not ok and expected and live:
            ui_job = str(live.get("kling_o3_voice_fix_ui_job_id") or "")
            if ui_job == job_id:

                def heal_attempt(b: dict, _sidecar: dict) -> None:
                    b["kling_o3_voice_fix_attempt_id"] = expected

                bg_sidecar.update_beat_locked(beat_id, heal_attempt)
                ok, _ = bg_sidecar.update_beat_locked(
                    beat_id,
                    apply,
                    expected_attempt_id=expected,
                )
        if not ok:
            raise RuntimeError(f"sidecar lost attempt_id race for {beat_id}")

    persist({
        "status": "o3_element_running",
        "kling_o3_status": "submitted",
        "kling_o3_generation": gen,
        "kling_o3_voice_fix_status": "o3_running",
        "kling_o3_voice_fix_phase": "o3_element",
        "kling_o3_voice_fix_attempt_id": attempt_id,
        "kling_o3_voice_fix_updated_at": datetime.now(timezone.utc).isoformat(),
        "kling_o3_prompt": str(prompt_block.get("verbatim") or ""),
    })

    master.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = o3.run_beat_generation(
            api_key,
            submit_prompt,
            char_path,
            bg_path,
            master,
            duration=duration,
            speaker=speaker,
            element_entry=element_entry,
        )
    except Exception as exc:
        write_intent_terminal(job_id, event_dir, {
            "intent_id": intent.get("intent_id"),
            "status": "failed",
            "sidecar_persist_ok": False,
            "failure": {"message": str(exc)[:1500]},
            "submitted": {
                "prompt_voice_excerpt": submit_prompt[:500],
                "char_ref": str(char_path),
                "element_id": voice.get("element_id"),
            },
        })
        raise

    if not result.get("ok"):
        err_text = result.get("error") or json.dumps(result)
        write_intent_terminal(job_id, event_dir, {
            "intent_id": intent.get("intent_id"),
            "status": "failed",
            "sidecar_persist_ok": False,
            "failure": {"message": str(err_text)[:1500]},
        })
        raise RuntimeError(f"O3 element generation failed: {result}")

    raw_probe = _probe(master)
    if not raw_probe["gate_pass"]:
        write_intent_terminal(job_id, event_dir, {
            "intent_id": intent.get("intent_id"),
            "status": "failed",
            "failure": {"message": f"Raw O3 gate fail: {raw_probe}"},
        })
        raise RuntimeError(f"Raw O3 gate fail: {raw_probe}")

    print(json.dumps({"phase": "delivery_encode", "src": str(master), "dst": str(delivery)}), flush=True)
    encode_delivery_video(
        master,
        delivery,
        include_audio=True,
        sharpen=True,
        delivery_profile="voice_first_upscale",
    )
    delivery_probe = _probe(delivery)
    if delivery_probe["width"] != 1280 or delivery_probe["height"] != 720:
        raise RuntimeError(f"Delivery encode did not land at 1280x720: {delivery_probe}")

    sidecar_persist_ok = True
    checkpoint_warning = None

    def _recover_orphan(reason: str) -> dict:
        nonlocal checkpoint_warning
        checkpoint_warning = reason[:500]
        return bg_sidecar.recover_orphan_o3_delivery(
            beat_id,
            event_dir,
            log_path=os.environ.get("MN_O3_JOB_LOG"),
            delivery_path=str(delivery),
            make_active=True,
        )

    try:
        bg_sidecar.persist_o3_delivery_option_checkpoint(
            beat_id,
            video_path=str(delivery),
            slot_index=int(generation.get("replace_slot_index") or 0),
            label=bg_sidecar._canonical_o3_option_label(str(delivery), gen),
            o3_voice_binding={
                "element_id": voice.get("element_id"),
                "kling_voice_id": voice.get("kling_voice_id"),
            },
            attempt_id=attempt_id,
            generation=gen,
            ui_job_id=job_id,
        )
    except Exception as exc:
        recovered = _recover_orphan(str(exc))
        if not recovered.get("recovered"):
            raise

    now = datetime.now(timezone.utc).isoformat()
    dur = float(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(delivery),
    ], text=True).strip())

    final = {
        "kling_o3_prompt": str(prompt_block.get("verbatim") or ""),
        "o3_prompt_box_law": True,
        **active_delivery_sidecar_fields(delivery, mark_voice_fix_approved=True),
        "kling_o3_completed_at": now,
        "kling_o3_mode": "o3_element_native_voice",
        "kling_o3_voice_fix_phase": "finalize",
        "kling_o3_voice_fix_completed_at": now,
        "kling_o3_voice_fix_output_duration_s": round(dur, 3),
        "kling_o3_generation": gen,
        "o3_element_quality": {
            "speaker": speaker,
            "element_id": voice.get("element_id"),
            "kling_voice_id": voice.get("kling_voice_id"),
            "delivery_profile": "LD-284/LD-296 1280x720 H.264 <=1.9Mbps +faststart",
            "method": "O3 Pro reference-to-video + Element create-voice (intent snapshot)",
            "applied_at": now,
        },
    }
    final.update(sidecar_visual_ref_fields_from_intent(intent))
    from o3_gallery_closure import (
        assert_gallery_closed_before_terminal,
        refresh_beat_gallery_fields_for_finalize,
    )

    gallery_fields = refresh_beat_gallery_fields_for_finalize(
        beat_id,
        event_dir,
        str(delivery),
    )
    if gallery_fields.get("kling_o3_options") is not None:
        final["kling_o3_options"] = gallery_fields["kling_o3_options"]
    final_remove = (
        "kling_o3_voice_fix_ui_job_id",
        "kling_o3_voice_fix_job_pid",
        "kling_o3_voice_fix_job_started_at",
        "kling_o3_voice_fix_error",
        "kling_o3_voice_fix_error_code",
        "o3_active_intent_id",
        "o3_active_intent_job_id",
        "o3_current_job_id",
    )
    try:
        persist(final, remove=final_remove, coherence_mode=bg_sidecar.O3_GENERATE_MODE_ELEMENT_NATIVE)
    except Exception as exc:
        recovered = _recover_orphan(str(exc))
        if not recovered.get("recovered"):
            sidecar_persist_ok = False
            write_intent_terminal(job_id, event_dir, {
                "intent_id": intent.get("intent_id"),
                "status": "failed",
                "sidecar_persist_ok": False,
                "failure": {"message": str(exc)[:1500]},
            })
            raise
        try:
            persist(final, remove=final_remove)
        except Exception:
            # Orphan recovery already wrote delivery + approved state to sidecar.
            sidecar_persist_ok = True

    assert_gallery_closed_before_terminal(beat_id, event_dir, str(delivery))
    terminal_status = "done" if sidecar_persist_ok else "done_with_warning"
    terminal_body = {
        "intent_id": intent.get("intent_id"),
        "status": terminal_status,
        "phase_last": "finalize",
        "sidecar_persist_ok": sidecar_persist_ok,
        "submitted": {
            "prompt_voice_excerpt": submit_prompt[:500],
            "char_ref": str(char_path),
            "element_id": voice.get("element_id"),
        },
        "delivered": {
            "video_path": str(delivery),
            "duration_s": round(dur, 3),
            "generation": gen,
        },
        "failure": None,
    }
    if not sidecar_persist_ok:
        terminal_body["warning"] = {
            "code": "ORPHAN_DELIVERY_RECOVERED",
            "message": checkpoint_warning or "Sidecar persist failed; delivery recovered from disk.",
            "recovered_from": "orphan_delivery_after_sidecar_io_error",
        }
    write_intent_terminal(job_id, event_dir, terminal_body)
    print(json.dumps({
        "phase": "done",
        "beat_id": beat_id,
        "video": str(delivery),
        "intent_id": intent.get("intent_id"),
        "terminal_status": terminal_status,
    }), flush=True)
    return {"ok": True, "beat_id": beat_id, "video": str(delivery)}


def _touch_o3_heartbeat_for_intent(intent_path: Path, event_dir: Path) -> None:
    try:
        from o3_generation_intent import load_generation_intent, touch_o3_job_heartbeat

        intent = load_generation_intent(intent_path)
        job_id = str(intent.get("job_id") or "").strip()
        if job_id:
            touch_o3_job_heartbeat(job_id, event_dir)
    except Exception:
        pass


def run_pipeline(
    beat_id: str,
    *,
    sharpen: bool = False,
    attempt_id: str | None = None,
) -> dict:
    from tools.credentials_lib.credentials import load_credentials
    from tools import kling_character_registry as reg
    from tools import kling_o3_client as o3

    attempt_id = attempt_id or os.environ.get("MN_O3_ATTEMPT_ID") or __import__("uuid").uuid4().hex
    print(json.dumps({"phase": "starting", "beat_id": beat_id, "route": "o3_element_native_voice", "attempt_id": attempt_id}), flush=True)

    prod_root = _runtime_prod_root()
    reg.set_prod_root(prod_root)
    from o3_subprocess_bootstrap import load_o3_beat_context

    beat, segment_key, sidecar_path, event_dir = load_o3_beat_context(beat_id)
    intent_env = os.environ.get("MN_O3_INTENT_PATH", "").strip()
    if intent_env:
        _touch_o3_heartbeat_for_intent(Path(intent_env), event_dir)
    backup_dir = event_dir / "_o3_element_backups" / (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"_{beat_id}"
    )
    backup_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(sidecar_path, backup_dir / "beat_generator_state.json")

    speaker = (beat.get("speaker") or "").strip()
    if not speaker:
        raise RuntimeError(f"{beat_id} has no speaker")
    if not reg.is_speaker_voice_ready(speaker):
        raise RuntimeError(
            f"{speaker!r} has no active Element + bound voice. "
            f"Run: python3 scripts/setup_all_kling_character_voices.py --char {speaker}"
        )

    if not beat.get("reference_image_locked"):
        bg_sidecar.ensure_beat_element_aligned_reference(beat)

    char_path = _ref_path(beat.get("reference_image"))
    bg_path = _ref_path(beat.get("bg_ref_image"))
    if not char_path.is_file() or not bg_path.is_file():
        raise RuntimeError("reference_image and bg_ref_image must exist on disk")

    creds = load_credentials()
    api_key = creds.get("wavespeed_key") or creds.get("wavespeed")
    if not api_key:
        raise RuntimeError("Missing wavespeed API key")
    bg_sidecar.ensure_beat_element_char_ref_for_o3(beat, api_key)
    bg_sidecar.require_element_char_ref_for_o3(beat)

    stored_prompt = (beat.get("kling_o3_prompt") or "").strip()
    prompt, spoken = resolve_element_o3_submit_prompt(beat)
    submit_prompt = bg_sidecar.prepare_kling_o3_prompt_for_submit(beat, prompt)

    element_entry = bg_sidecar.resolve_o3_element_list_entry(beat, speaker)
    if not element_entry:
        raise RuntimeError(
            f"{speaker!r} has no active element_list entry — "
            "run setup_all_kling_character_voices.py before O3 Element generate."
        )
    from tools.kling_voice_bind import detect_voice_bind_drift

    drift_msg = detect_voice_bind_drift(
        beat,
        speaker,
        reg.get_bound_voice_id(speaker),
    )
    if drift_msg and os.environ.get("MN_ACCEPT_VOICE_DRIFT") != "1":
        raise RuntimeError(f"VOICE_BIND_DRIFT: {drift_msg}")
    event_match = re.match(r"event_(\d+)_", segment_key or "")
    event_id = event_match.group(1) if event_match else "1"
    submit_errors = bg_sidecar.validate_kling_o3_beat_for_submit(
        beat,
        event_id=event_id,
        phase="pre" if (segment_key or "").endswith("_pre") else "full",
    )
    blocking_errors = [
        e for e in submit_errors
        if e.get("code") not in {"DIALOGUE_TOO_LONG"}
    ]
    if blocking_errors:
        codes = ", ".join(
            f"{e.get('code', '?')}: {e.get('message', '')}" for e in blocking_errors
        )
        raise RuntimeError(f"KLING_O3_SUBMIT_BLOCKED: {codes}")
    duration = bg_sidecar.resolve_kling_o3_submit_duration(beat, submit_prompt)
    if not beat.get("kling_o3_duration_locked"):
        beat["kling_o3_duration"] = duration

    clips_dir = event_dir / "kling_o3_clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    prior_video = beat.get("kling_o3_video_path")
    if prior_video and Path(str(prior_video)).is_file():
        bg_sidecar.prune_stale_o3_voice_options(beat, speaker)
        bg_sidecar.stash_prior_kling_o3_before_redo(
            beat,
            event_dir,
            reason="o3_element_redo",
            label="previous approved O3 video",
        )
    gen = int(beat.get("kling_o3_generation") or 0) + 1
    master = clips_dir / f"{beat_id}_g{gen}_element_o3_master.mp4"

    def persist_o3_redo_failure(error_text: str, *, error_code: str, task_id: str | None = None) -> None:
        fail_fields: dict = {
            "kling_o3_voice_fix_completed_at": datetime.now(timezone.utc).isoformat(),
        }
        if task_id:
            fail_fields["kling_o3_task_id"] = task_id
        restored = bg_sidecar.restore_active_kling_o3_after_failed_redo(beat)
        if restored:
            persist(fail_fields, remove=(
                "kling_o3_voice_fix_ui_job_id",
                "kling_o3_voice_fix_error",
                "kling_o3_voice_fix_error_code",
                "kling_o3_voice_fix_phase",
            ))
            print(json.dumps({
                "phase": "o3_redo_failed_kept_prior",
                "beat_id": beat_id,
                "error_code": error_code,
                "task_id": task_id,
                "message": error_text[:500],
            }), flush=True)
            return
        fail_fields.update({
            "status": "o3_element_failed",
            "kling_o3_status": "failed",
            "kling_o3_voice_fix_status": "failed_o3",
            "kling_o3_voice_fix_error": error_text[:1500],
            "kling_o3_voice_fix_error_code": error_code,
            "kling_o3_voice_fix_phase": "failed",
        })
        persist(fail_fields, remove=("kling_o3_voice_fix_ui_job_id",))

    def persist(fields: dict | None = None, *, remove: tuple[str, ...] = (), coherence_mode: str | None = None):
        if fields:
            beat.update(fields)
        for key in remove:
            beat.pop(key, None)

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

        ok, _ = bg_sidecar.update_beat_locked(
            beat_id,
            apply,
            expected_attempt_id=attempt_id,
        )
        if not ok:
            raise RuntimeError(f"sidecar lost attempt_id race for {beat_id}")

    persist({
        "status": "o3_element_running",
        "kling_o3_status": "submitted",
        "kling_o3_generation": gen,
        "kling_o3_voice_fix_status": "o3_running",
        "kling_o3_voice_fix_phase": "o3_element",
        "kling_o3_voice_fix_attempt_id": attempt_id,
        "kling_o3_voice_fix_updated_at": datetime.now(timezone.utc).isoformat(),
    })

    char_gate_ok, char_gate_detail = reg.char_ref_matches_element_images(str(char_path), speaker)
    print(json.dumps({
        "phase": "o3_submit",
        "beat_id": beat_id,
        "speaker": speaker,
        "element": element_entry,
        "kling_voice_id": element_entry.get("voice_id") or reg.get_bound_voice_id(speaker),
        "o3_voice_stack_pin": beat.get("o3_voice_stack_pin") if bg_sidecar.o3_voice_stack_pin_active(beat) else None,
        "prod_root": str(prod_root),
        "event_dir": str(event_dir),
        "char_ref_aligned": char_gate_ok,
        "char_ref_gate_detail": char_gate_detail or None,
        "char_ref": str(char_path),
        "voice_line_locked": "speaks in a" in submit_prompt.lower(),
        "spoken_sent": spoken,
        "prompt_box_law": bg_sidecar.o3_prompt_box_law_active(beat),
        "prompt_verbatim": bg_sidecar.o3_prompt_box_law_active(beat) or bool(stored_prompt),
        "prompt_prepared": submit_prompt != prompt,
        "prompt_voice_excerpt": submit_prompt[:500],
        "kling_o3_duration": duration,
    }), flush=True)
    try:
        result = o3.run_beat_generation(
            api_key,
            submit_prompt,
            char_path,
            bg_path,
            master,
            duration=duration,
            speaker=speaker,
            element_entry=element_entry,
        )
    except Exception as exc:
        msg = str(exc)
        transient = any(token in msg for token in ("Poll HTTP 502", "Poll HTTP 503", "Poll HTTP 504", "Poll HTTP 500", "Poll HTTP 429", "transport failed after retries"))
        persist_o3_redo_failure(
            msg,
            error_code="WAVESPEED_GATEWAY" if transient else "O3_RUNTIME",
        )
        raise
    if not result.get("ok"):
        task_id = str(result.get("task_id") or "")
        if task_id and result.get("retry_safe"):
            print(json.dumps({"phase": "o3_resume", "beat_id": beat_id, "task_id": task_id}), flush=True)
            result = o3.resume_task_to_mp4(api_key, task_id, master)
        if not result.get("ok"):
            err_text = result.get("error") or json.dumps(result)
            code = "WAVESPEED_GATEWAY" if result.get("retry_safe") or result.get("status") == "poll_gateway_error" else "O3_PROVIDER"
            persist_o3_redo_failure(str(err_text), error_code=code, task_id=task_id or None)
            raise RuntimeError(f"O3 element generation failed: {result}")

    raw_probe = _probe(master)
    if not raw_probe["gate_pass"]:
        persist({
            "kling_o3_status": "failed",
            "kling_o3_voice_fix_status": "failed_provider_sub720",
            "kling_o3_voice_fix_error": f"Raw O3 output failed gate: {raw_probe}",
            "kling_o3_voice_fix_output_profile": raw_probe,
            "kling_o3_voice_fix_completed_at": datetime.now(timezone.utc).isoformat(),
        }, remove=("kling_o3_voice_fix_ui_job_id",))
        raise RuntimeError(f"Raw O3 gate fail: {raw_probe}")

    delivery = master.with_name(master.stem + "_delivery.mp4")
    print(json.dumps({"phase": "delivery_encode", "src": str(master), "dst": str(delivery)}), flush=True)
    encode_delivery_video(
        master,
        delivery,
        include_audio=True,
        sharpen=True,
        delivery_profile="voice_first_upscale",
    )
    delivery_probe = _probe(delivery)
    if delivery_probe["width"] != 1280 or delivery_probe["height"] != 720:
        raise RuntimeError(f"Delivery encode did not land at 1280x720: {delivery_probe}")

    binding = bg_sidecar._o3_voice_binding_snapshot(beat, speaker)
    binding = {k: v for k, v in binding.items() if v}

    recovered_gen = bg_sidecar._kling_o3_gen_from_video_path(str(delivery))
    slot_index = int(beat.get("kling_o3_replace_slot_index") or 0)
    label = bg_sidecar._canonical_o3_option_label(str(delivery), recovered_gen)
    try:
        bg_sidecar.persist_o3_delivery_option_checkpoint(
            beat_id,
            video_path=str(delivery),
            slot_index=slot_index,
            label=label,
            o3_voice_binding=binding or None,
            attempt_id=attempt_id,
            generation=recovered_gen,
            ui_job_id=str(beat.get("kling_o3_voice_fix_ui_job_id") or ""),
        )
    except Exception as exc:
        recovered = bg_sidecar.recover_orphan_o3_delivery(
            beat_id,
            event_dir,
            log_path=os.environ.get("MN_O3_JOB_LOG"),
            delivery_path=str(delivery),
            make_active=True,
        )
        if not recovered.get("recovered"):
            raise
        print(json.dumps({
            "phase": "sidecar_recovered",
            "beat_id": beat_id,
            "video": recovered.get("delivery_path"),
            "checkpoint": True,
            "reason": str(exc)[:500],
        }), flush=True)

    now = datetime.now(timezone.utc).isoformat()
    dur = float(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(delivery),
    ], text=True).strip())

    final = {
        **active_delivery_sidecar_fields(delivery, mark_voice_fix_approved=True),
        "kling_o3_completed_at": now,
        "kling_o3_mode": "o3_element_native_voice",
        "kling_o3_voice_fix_phase": "finalize",
        "kling_o3_voice_fix_completed_at": now,
        "kling_o3_voice_fix_output_profile": {
            "raw_master": raw_probe,
            "delivery": delivery_probe,
            "raw_master_path": str(master),
            "delivery_path": str(delivery),
        },
        "kling_o3_voice_fix_output_duration_s": round(dur, 3),
        "o3_element_quality": {
            "speaker": speaker,
            **{
                k: v for k, v in bg_sidecar._o3_voice_binding_snapshot(beat, speaker).items()
                if k in ("element_id", "kling_voice_id")
            },
            "delivery_profile": "LD-284/LD-296 1280x720 H.264 <=1.9Mbps +faststart",
            "method": "O3 Pro reference-to-video + Element create-voice (no lipsync detour)",
            "applied_at": now,
            **(
                {"pinned_from_beat_id": str(beat["o3_voice_stack_pin"].get("pinned_from_beat_id"))}
                if isinstance(beat.get("o3_voice_stack_pin"), dict)
                and beat["o3_voice_stack_pin"].get("pinned_from_beat_id")
                else {}
            ),
        },
    }
    from o3_generation_intent import load_intent_visual_ref_fields_from_env

    final.update(load_intent_visual_ref_fields_from_env())
    with bg_sidecar._sidecar_lock:
        sc_refresh = bg_sidecar.read_sidecar()
        found_refresh = _find_beat(sc_refresh, beat_id)
        if found_refresh:
            beat["kling_o3_options"] = found_refresh[0].get("kling_o3_options")
    bg_sidecar.prune_stale_o3_voice_options(beat, speaker)
    bg_sidecar.reconcile_o3_disk_deliveries_for_beat(beat, event_dir)
    final["kling_o3_options"] = beat.get("kling_o3_options")
    try:
        persist(
            final,
            remove=(
                "kling_o3_voice_fix_ui_job_id",
                "kling_o3_voice_fix_job_pid",
                "kling_o3_voice_fix_job_started_at",
                "kling_o3_voice_fix_error",
                "kling_o3_voice_fix_error_code",
            ),
            coherence_mode=bg_sidecar.O3_GENERATE_MODE_ELEMENT_NATIVE,
        )
        bg_sidecar.auto_pin_approved_kling_o3_delivery(beat, event_dir)
    except Exception as exc:
        recovered = bg_sidecar.recover_orphan_o3_delivery(
            beat_id,
            event_dir,
            log_path=os.environ.get("MN_O3_JOB_LOG"),
            delivery_path=str(delivery),
            make_active=True,
        )
        if not recovered.get("recovered"):
            raise
        print(json.dumps({
            "phase": "sidecar_recovered",
            "beat_id": beat_id,
            "video": recovered.get("delivery_path"),
            "reason": str(exc)[:500],
        }), flush=True)
    print(json.dumps({"phase": "done", "beat_id": beat_id, "video": str(delivery), "raw": raw_probe, "delivery": delivery_probe}), flush=True)
    return {"ok": True, "beat_id": beat_id, "video": str(delivery), "raw_probe": raw_probe, "delivery_probe": delivery_probe}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--beat-id", required=True)
    parser.add_argument("--no-sharpen", action="store_true")
    parser.add_argument("--attempt-id", default=None)
    args = parser.parse_args()
    intent_path = os.environ.get("MN_O3_INTENT_PATH", "").strip()
    try:
        if intent_path:
            from o3_generation_intent import load_generation_intent, write_intent_terminal

            intent = load_generation_intent(Path(intent_path))
            print(json.dumps({
                "phase": "starting",
                "beat_id": args.beat_id,
                "route": "o3_element_intent_snapshot",
                "intent_id": intent.get("intent_id"),
            }), flush=True)
            run_pipeline_from_intent(intent, sharpen=not args.no_sharpen)
        else:
            print(json.dumps({"phase": "legacy_sidecar_submit_path", "beat_id": args.beat_id}), flush=True)
            run_pipeline(args.beat_id, sharpen=not args.no_sharpen, attempt_id=args.attempt_id)
        return 0
    except Exception as exc:
        import traceback as _tb

        print(json.dumps({
            "phase": "failed",
            "beat_id": args.beat_id,
            "error": str(exc)[:1500],
            "traceback": _tb.format_exc()[-4000:],
        }), flush=True)
        job_id = ""
        event_id = "Event_1"
        intent = {}
        if intent_path:
            try:
                from o3_generation_intent import close_o3_attempt, load_generation_intent

                intent = load_generation_intent(Path(intent_path))
                job_id = str(intent.get("job_id") or "")
                event_id = str(intent.get("event_id") or "Event_1")
            except Exception:
                pass
        if job_id:
            try:
                from o3_recovery_seal import seal_o3_recovery_before_terminal

                prod_root = _runtime_prod_root()
                ev_dir = prod_root / event_id
                clips = ev_dir / "kling_o3_clips"
                gen_slot = str(intent.get("generation_slot") or intent.get("generation") or "")
                master = None
                delivery = None
                if gen_slot:
                    master = clips / f"{args.beat_id}_{gen_slot}_element_o3_master.mp4"
                    delivery = clips / f"{args.beat_id}_{gen_slot}_element_o3_master_delivery.mp4"
                log_path = os.environ.get("MN_O3_JOB_LOG", "").strip() or None
                seal = seal_o3_recovery_before_terminal(
                    args.beat_id,
                    ev_dir,
                    master_path=master if master and master.is_file() else None,
                    delivery_path=delivery if delivery and delivery.is_file() else None,
                    log_path=log_path,
                    failure_phase="pipeline_exception",
                    failure_message=str(exc)[:1500],
                )
                from o3_generation_intent import close_o3_attempt

                term_status = str(seal.get("terminal_status") or "failed")
                close_o3_attempt(
                    job_id,
                    args.beat_id,
                    ev_dir,
                    term_status,
                    reason=str(exc)[:1500],
                    phase_last="pipeline_exception",
                    intent=intent,
                    persist_beat=bool(seal.get("sidecar_persist_ok") or term_status != "failed"),
                )
            except Exception:
                try:
                    from o3_generation_intent import write_intent_terminal

                    write_intent_terminal(job_id, prod_root / event_id, {
                        "intent_id": intent.get("intent_id"),
                        "status": "failed",
                        "sidecar_persist_ok": False,
                        "failure": {"message": str(exc)[:1500]},
                    })
                except Exception:
                    pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
