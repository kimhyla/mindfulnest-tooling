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
    """Return (kling_prompt, spoken_log). Upgrades legacy voice tags before submit."""
    stored_prompt = (beat.get("kling_o3_prompt") or "").strip()
    build_prompt, normalize_spoken = _load_build_prompt()
    speaker = str(beat.get("speaker") or "").strip()
    if bg_sidecar.o3_prompt_box_law_active(beat) and stored_prompt:
        prepared = bg_sidecar.prepare_kling_o3_prompt_for_submit(beat, stored_prompt)
        spoken = bg_sidecar.extract_spoken_dialogue_from_kling_prompt(stored_prompt) or ""
        return prepared, spoken
    if stored_prompt:
        from tools import kling_o3_prompt as o3p

        upgraded, spoken, changed = o3p.upgrade_element_bound_voice_prompt(
            speaker,
            stored_prompt,
            extract_spoken=bg_sidecar.extract_spoken_dialogue_from_kling_prompt,
        )
        prompt = upgraded if changed else stored_prompt
        if changed:
            beat["kling_o3_prompt"] = prompt
        prompt = bg_sidecar.normalize_o3_element_bound_prompt(beat, prompt)
        if prompt != stored_prompt:
            beat["kling_o3_prompt"] = prompt
        if not spoken and re.search(r"\b(?:speaks|says)\b", prompt, re.I):
            raise RuntimeError(
                "ELEMENT_VOICE_PROMPT: could not extract spoken dialogue from the "
                "voice line — put the full line in double quotes after speaks…:"
            )
        return prompt, spoken or ""
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
    sidecar_path = prod_root / "beat_generator_state.json"
    sc = json.loads(sidecar_path.read_text(encoding="utf-8"))
    found = _find_beat(sc, beat_id)
    if not found:
        raise RuntimeError(f"beat not found: {beat_id}")
    beat, segment_key = found
    event_dir = _event_dir_for_segment(prod_root, segment_key)
    bg_sidecar.init_bg_paths(event_dir)
    sidecar_path = Path(bg_sidecar.BG_SIDECAR_PATH)
    with bg_sidecar._sidecar_lock:
        sc = bg_sidecar.read_sidecar()
        found = _find_beat(sc, beat_id)
        if not found:
            raise RuntimeError(f"beat not found after init_bg_paths: {beat_id}")
        beat, segment_key = found
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
    if not bg_sidecar.o3_prompt_box_law_active(beat):
        bg_sidecar.heal_o3_element_submit_prompt(beat)
    prompt, spoken = resolve_element_o3_submit_prompt(beat)
    from tools import kling_o3_prompt as o3p

    element_entry = bg_sidecar.resolve_o3_element_list_entry(beat, speaker)
    if not element_entry:
        raise RuntimeError(
            f"{speaker!r} has no active element_list entry — "
            "run setup_all_kling_character_voices.py before O3 Element generate."
        )
    prepared = bg_sidecar.prepare_kling_o3_prompt_for_submit(beat, prompt)
    if prepared and prepared != beat.get("kling_o3_prompt"):
        beat["kling_o3_prompt"] = prepared
        prompt = prepared
    align_errors = o3p.validate_element_list_alignment(
        speaker, element_entry, prepared or prompt, beat=beat,
    )
    if align_errors:
        raise RuntimeError(
            "ELEMENT_VOICE_ALIGN: "
            + "; ".join(align_errors)
            + " — fix before O3 submit (generic Kling TTS otherwise)."
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
    duration = bg_sidecar.resolve_kling_o3_submit_duration(beat, prepared)
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

    def persist(fields: dict | None = None, *, remove: tuple[str, ...] = ()):
        if fields:
            beat.update(fields)
        for key in remove:
            beat.pop(key, None)

        def apply(current: dict, _sidecar: dict) -> None:
            if fields:
                current.update(fields)
            for key in remove:
                current.pop(key, None)

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

    print(json.dumps({
        "phase": "o3_submit",
        "beat_id": beat_id,
        "speaker": speaker,
        "element": element_entry,
        "kling_voice_id": element_entry.get("voice_id") or reg.get_bound_voice_id(speaker),
        "o3_voice_stack_pin": beat.get("o3_voice_stack_pin") if bg_sidecar.o3_voice_stack_pin_active(beat) else None,
        "prod_root": str(prod_root),
        "event_dir": str(event_dir),
        "char_ref_aligned": True,
        "char_ref": str(char_path),
        "voice_line_locked": "speaks in a" in prepared.lower(),
        "spoken_sent": spoken,
        "prompt_box_law": bg_sidecar.o3_prompt_box_law_active(beat),
        "prompt_verbatim": bg_sidecar.o3_prompt_box_law_active(beat) or bool(stored_prompt),
        "prompt_prepared": prepared != prompt,
        "prompt_voice_excerpt": prepared[:500],
        "kling_o3_duration": duration,
    }), flush=True)
    submit_prompt = prepared or prompt
    if submit_prompt != prompt:
        beat["kling_o3_prompt"] = submit_prompt
        prompt = submit_prompt
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
    encode_delivery_video(master, delivery, include_audio=True, sharpen=sharpen)
    delivery_probe = _probe(delivery)
    if delivery_probe["width"] != 1280 or delivery_probe["height"] != 720:
        raise RuntimeError(f"Delivery encode did not land at 1280x720: {delivery_probe}")

    binding = bg_sidecar._o3_voice_binding_snapshot(beat, speaker)
    binding = {k: v for k, v in binding.items() if v}

    recovered_gen = bg_sidecar._kling_o3_gen_from_video_path(str(delivery))
    slot_index = int(beat.get("kling_o3_replace_slot_index") or 0)
    label = f"g{recovered_gen} O3 Element voice" if recovered_gen else "latest O3 Element voice"
    bg_sidecar.persist_o3_delivery_option_checkpoint(
        beat_id,
        video_path=str(delivery),
        slot_index=slot_index,
        label=label,
        o3_voice_binding=binding or None,
        attempt_id=attempt_id,
        generation=recovered_gen,
    )

    now = datetime.now(timezone.utc).isoformat()
    dur = float(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(delivery),
    ], text=True).strip())

    final = {
        "kling_o3_video_path": str(delivery),
        "kling_o3_status": "approved",
        "status": "approved",
        "kling_o3_completed_at": now,
        "kling_o3_mode": "o3_element_native_voice",
        "kling_o3_voice_fix_status": "approved",
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
    with bg_sidecar._sidecar_lock:
        sc_refresh = bg_sidecar.read_sidecar()
        found_refresh = _find_beat(sc_refresh, beat_id)
        if found_refresh:
            beat["kling_o3_options"] = found_refresh[0].get("kling_o3_options")
    bg_sidecar.prune_stale_o3_voice_options(beat, speaker)
    bg_sidecar.reconcile_o3_disk_deliveries_for_beat(beat, event_dir)
    final["kling_o3_options"] = beat.get("kling_o3_options")
    try:
        persist(final, remove=(
            "kling_o3_voice_fix_ui_job_id",
            "kling_o3_voice_fix_job_pid",
            "kling_o3_voice_fix_job_started_at",
            "kling_o3_voice_fix_error",
            "kling_o3_voice_fix_error_code",
            "o3_prompt_box_law",
            "o3_prompt_box_law_at",
        ))
        bg_sidecar.auto_pin_approved_kling_o3_delivery(beat, event_dir)
    except Exception as exc:
        recovered = bg_sidecar.recover_orphan_o3_delivery(
            beat_id,
            event_dir,
            log_path=os.environ.get("MN_O3_JOB_LOG"),
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
    run_pipeline(args.beat_id, sharpen=not args.no_sharpen, attempt_id=args.attempt_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
