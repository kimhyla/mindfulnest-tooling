"""O3 Generation Intent Snapshot — immutable submit contract at Generate click."""
from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

INTENT_SCHEMA_VERSION = 1
TERMINAL_SCHEMA_VERSION = 1

INTENT_TERMINAL_STATUSES = frozenset({"done", "failed", "done_with_warning"})
INTENT_RUNNING_STATUS = "running"

OPERATOR_MUTABLE_FIELDS = frozenset({
    "kling_o3_prompt",
    "reference_image",
    "bg_ref_image",
    "speaker",
})


class IntentActiveError(RuntimeError):
    """Raised when canonical mutation is blocked during active intent."""


class IntentCommitError(Exception):
    def __init__(
        self,
        error_code: str,
        error_message: str,
        *,
        http_status: int = 400,
        detail: dict | None = None,
        retry_safe: bool = False,
    ) -> None:
        super().__init__(error_message)
        self.error_code = error_code
        self.error_message = error_message
        self.http_status = http_status
        self.detail = detail or {}
        self.retry_safe = retry_safe


def _jobs_dir(event_dir: Path) -> Path:
    return event_dir / "arlo_o3_jobs"


def intent_path_for_job(job_id: str, event_dir: Path) -> Path:
    return _jobs_dir(event_dir) / f"{job_id}_intent.json"


def terminal_path_for_job(job_id: str, event_dir: Path) -> Path:
    return _jobs_dir(event_dir) / f"{job_id}_terminal.json"


def _sha256_file(path: str | Path) -> str:
    p = Path(path)
    if not p.is_file():
        return ""
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def load_generation_intent(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if int(data.get("schema_version") or 0) != INTENT_SCHEMA_VERSION:
        raise ValueError(f"unsupported intent schema: {path}")
    return data


def load_intent_terminal(path: Path) -> dict | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_generation_intent(intent: dict, event_dir: Path) -> Path:
    job_id = str(intent.get("job_id") or "").strip()
    if not job_id:
        raise ValueError("intent.job_id required")
    jobs_dir = _jobs_dir(event_dir)
    jobs_dir.mkdir(parents=True, exist_ok=True)
    dest = intent_path_for_job(job_id, event_dir)
    tmp = dest.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(intent, indent=2), encoding="utf-8")
    os.replace(tmp, dest)
    return dest


def write_intent_terminal(job_id: str, event_dir: Path, payload: dict) -> Path:
    jobs_dir = _jobs_dir(event_dir)
    jobs_dir.mkdir(parents=True, exist_ok=True)
    dest = terminal_path_for_job(job_id, event_dir)
    body = {
        "schema_version": TERMINAL_SCHEMA_VERSION,
        "job_id": job_id,
        **payload,
    }
    if "terminal_at" not in body:
        body["terminal_at"] = datetime.now(timezone.utc).isoformat()
    tmp = dest.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(body, indent=2), encoding="utf-8")
    os.replace(tmp, dest)
    return dest


def terminal_status_for_job(job_id: str, event_dir: Path) -> str | None:
    terminal = load_intent_terminal(terminal_path_for_job(job_id, event_dir))
    if not terminal:
        return None
    return str(terminal.get("status") or "").strip() or None


def beat_has_active_intent(beat_id: str, event_dir: Path) -> bool:
    return active_intent_path_for_beat(beat_id, event_dir) is not None


def active_intent_path_for_beat(beat_id: str, event_dir: Path) -> Path | None:
    jobs_dir = _jobs_dir(event_dir)
    if not jobs_dir.is_dir():
        return None
    bid = str(beat_id or "").strip()
    if not bid:
        return None
    candidates: list[tuple[str, Path]] = []
    for path in jobs_dir.glob("*_intent.json"):
        try:
            data = load_generation_intent(path)
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        if str(data.get("beat_id") or "").strip() != bid:
            continue
        job_id = str(data.get("job_id") or path.name.split("_intent")[0]).strip()
        term = terminal_path_for_job(job_id, event_dir)
        if term.is_file():
            try:
                tdata = load_intent_terminal(term)
                if str(tdata.get("status") or "") in INTENT_TERMINAL_STATUSES:
                    continue
            except (OSError, json.JSONDecodeError):
                pass
        committed = str(data.get("committed_at") or "")
        candidates.append((committed, path))
    if not candidates:
        return None
    candidates.sort(key=lambda row: row[0], reverse=True)
    return candidates[0][1]


def assert_canonical_mutation_allowed(beat_id: str, event_dir: Path) -> None:
    if beat_has_active_intent(beat_id, event_dir):
        raise IntentActiveError(
            f"beat {beat_id} has active generation intent — operator fields are locked"
        )


def intent_poll_subset(intent: dict) -> dict:
    prompt = intent.get("prompt") or {}
    visual = intent.get("visual") or {}
    voice = intent.get("voice") or {}
    generation = intent.get("generation") or {}
    return {
        "intent_id": intent.get("intent_id"),
        "job_id": intent.get("job_id"),
        "beat_id": intent.get("beat_id"),
        "prompt": {
            "verbatim": prompt.get("verbatim"),
            "sha256": prompt.get("sha256"),
        },
        "visual": {
            "char_ref_abs_path": visual.get("char_ref_abs_path"),
            "bg_ref_abs_path": visual.get("bg_ref_abs_path"),
            "element_char_ref_gate": visual.get("element_char_ref_gate"),
        },
        "voice": {
            "element_id": voice.get("element_id"),
            "element_name": voice.get("element_name"),
            "kling_voice_id": voice.get("kling_voice_id"),
        },
        "generation": {
            "slot": generation.get("slot"),
            "slot_index": generation.get("slot_index"),
        },
    }


def submitted_audit_from_intent(intent: dict) -> dict:
    prompt = str((intent.get("prompt") or {}).get("verbatim") or "")
    visual = intent.get("visual") or {}
    voice = intent.get("voice") or {}
    gate = visual.get("element_char_ref_gate") or {}
    excerpt = prompt[:500]
    if "speaks" in prompt.lower():
        m = re.search(r"speaks[^:]*:\s*[\"']?(.{0,120})", prompt, re.I | re.S)
        if m:
            excerpt = m.group(0)[:500]
    return {
        "prompt_excerpt": excerpt,
        "char_ref": visual.get("char_ref_abs_path"),
        "element_id": voice.get("element_id"),
        "refer_images": gate.get("refer_images_resolved") or [],
        "generation_slot": (intent.get("generation") or {}).get("slot"),
    }


def build_generation_intent(
    *,
    beat: dict,
    sidecar: dict,
    body: dict,
    beat_id: str,
    event_dir: Path,
    job_id: str,
    attempt_id: str,
    log_path: Path,
    pipeline_script: Path,
    wavespeed_key: str | None,
) -> dict:
    """Build immutable intent from POST body. Raises IntentCommitError on block."""
    import beat_generator as bg
    from tools import kling_character_registry as reg
    from tools import kling_o3_prompt as o3p

    bid = str(beat_id).strip()
    if beat_has_active_intent(bid, event_dir):
        raise IntentCommitError(
            "INTENT_JOB_ACTIVE",
            "O3 generation intent is already active for this beat.",
            http_status=409,
            retry_safe=True,
        )

    user_prompt = str(body.get("kling_o3_prompt") or "").strip()
    if not user_prompt:
        raise IntentCommitError(
            "EMPTY_PROMPT",
            "Prompt box is empty — type the full O3 prompt before Generate.",
            http_status=400,
        )

    speaker = str(beat.get("speaker") or "").strip()
    if not speaker:
        raise IntentCommitError(
            "MISSING_SPEAKER",
            "Beat has no speaker.",
            http_status=400,
        )
    if not reg.is_speaker_voice_ready(speaker):
        raise IntentCommitError(
            "SPEAKER_NOT_VOICE_READY",
            f"{speaker!r} has no active Element + bound voice.",
            http_status=400,
        )

    char_ref = body.get("reference_image") if "reference_image" in body else beat.get("reference_image")
    bg_ref = body.get("bg_ref_image") if "bg_ref_image" in body else beat.get("bg_ref_image")
    if not isinstance(char_ref, dict) or not isinstance(bg_ref, dict):
        raise IntentCommitError(
            "MISSING_O3_REF",
            "Char ref and BG ref must be set before generating O3 video.",
            http_status=400,
        )
    char_path = str(char_ref.get("abs_path") or "").strip()
    bg_path = str(bg_ref.get("abs_path") or "").strip()
    if not char_path or not Path(char_path).is_file():
        raise IntentCommitError(
            "MISSING_REF_FILE",
            f"Char ref file missing: {char_path}",
            http_status=400,
        )
    if not bg_path or not Path(bg_path).is_file():
        raise IntentCommitError(
            "MISSING_REF_FILE",
            f"BG ref file missing: {bg_path}",
            http_status=400,
        )

    ref_locked = bool(beat.get("reference_image_locked")) or bool(body.get("reference_image"))
    work_beat = dict(beat)
    work_beat["reference_image"] = char_ref
    work_beat["bg_ref_image"] = bg_ref
    if ref_locked:
        work_beat["reference_image_locked"] = True

    registration_action = "already_matched"
    aligned, gate_detail = reg.char_ref_matches_element_images(
        char_path, speaker, allow_pose_dir_fallback=False,
    )
    if not aligned:
        if ref_locked and wavespeed_key:
            reg_result = bg.try_register_dropped_char_ref_on_element(work_beat, wavespeed_key)
            if reg_result.get("ok") and reg_result.get("action") == "already_matched":
                aligned, gate_detail = reg.char_ref_matches_element_images(
                    char_path, speaker, allow_pose_dir_fallback=False,
                )
                if not aligned:
                    try:
                        reg_result = reg.reconcile_char_ref_with_element(
                            speaker, char_path, wavespeed_key,
                        )
                        reg_result["action"] = "reconciled_after_pose_only_match"
                    except Exception as exc:
                        reg_result = {"ok": False, "reason": str(exc)}
            if not reg_result.get("ok"):
                raise IntentCommitError(
                    "ELEMENT_VISUAL_MISMATCH",
                    str(work_beat.get("element_char_ref_error") or gate_detail or reg_result.get("reason") or ""),
                    http_status=400,
                    detail={
                        "char_ref": char_path,
                        "refer_images": _refer_images_rel(speaker),
                    },
                )
            registration_action = str(reg_result.get("action") or "registered")
            aligned, gate_detail = reg.char_ref_matches_element_images(
                char_path, speaker, allow_pose_dir_fallback=False,
            )
        if not aligned:
            raise IntentCommitError(
                "ELEMENT_REGISTRATION_FAILED" if registration_action != "already_matched" else "ELEMENT_VISUAL_MISMATCH",
                str(gate_detail or work_beat.get("element_char_ref_error") or ""),
                http_status=400,
                detail={
                    "char_ref": char_path,
                    "refer_images": _refer_images_rel(speaker),
                },
            )

    element_entry = bg.resolve_o3_element_list_entry(work_beat, speaker)
    if not element_entry:
        raise IntentCommitError(
            "MISSING_ELEMENT_ENTRY",
            f"{speaker!r} has no active element_list entry.",
            http_status=400,
        )
    proven_err = bg.validate_proven_o3_element_submit(
        work_beat,
        speaker,
        str(element_entry.get("element_id") or ""),
    )
    if proven_err:
        raise IntentCommitError(
            "PROVEN_O3_BIND_MISMATCH",
            proven_err,
            http_status=409,
        )

    from tools.kling_voice_bind import (
        advance_o3_element_quality_for_proven_registry,
        detect_voice_bind_drift,
    )

    reg_eid = str(element_entry.get("element_id") or "")
    reg_vid = str(reg.get_bound_voice_id(speaker) or element_entry.get("voice_id") or "")
    advance_o3_element_quality_for_proven_registry(
        work_beat,
        speaker,
        registry_element_id=reg_eid,
        registry_voice_id=reg_vid,
    )

    drift_msg = detect_voice_bind_drift(
        work_beat,
        speaker,
        reg_vid,
    )
    if drift_msg and not body.get("accept_voice_drift"):
        raise IntentCommitError(
            "VOICE_BIND_DRIFT",
            drift_msg,
            http_status=409,
            retry_safe=True,
        )

    prepared = bg.prepare_kling_o3_prompt_for_submit(work_beat, user_prompt)

    if prepared and re.search(r"\b(?:speaks|says)\b", prepared, re.I):
        extracted = bg.extract_spoken_dialogue_from_kling_prompt(prepared)
        if not extracted:
            raise IntentCommitError(
                "NO_QUOTED_DIALOGUE",
                "No spoken dialogue found in the prompt voice line.",
                http_status=400,
            )
        spoken_sent = extracted
    else:
        spoken_sent = bg.extract_spoken_dialogue_from_kling_prompt(user_prompt) or ""

    sidecar_gen = int(beat.get("kling_o3_generation") or 0)
    disk_gen_max = bg.highest_o3_generation_on_disk(bid, event_dir)
    next_gen = max(sidecar_gen, disk_gen_max) + 1
    clips_dir = event_dir / "kling_o3_clips"
    master = clips_dir / f"{bid}_g{next_gen}_element_o3_master.mp4"
    delivery = master.with_name(master.stem + "_delivery.mp4")

    replace_slot = body.get("replace_slot_index", beat.get("kling_o3_replace_slot_index", 0))
    try:
        replace_slot = max(0, min(2, int(replace_slot)))
    except (TypeError, ValueError):
        replace_slot = 0

    duration = bg.resolve_kling_o3_submit_duration(work_beat, prepared or user_prompt)

    ev_m = re.match(r"bg_arc\d+_event(\d+)_", bid)
    event_num = ev_m.group(1) if ev_m else "1"
    phase = bg.segment_phase_for_beat(sidecar, bid) or "pre"

    proven_bind = reg.resolve_proven_o3_bind(speaker) or {}
    intent_id = uuid.uuid4().hex

    intent: dict[str, Any] = {
        "schema_version": INTENT_SCHEMA_VERSION,
        "intent_id": intent_id,
        "job_id": job_id,
        "beat_id": bid,
        "event_id": f"Event_{event_num}",
        "phase": phase,
        "committed_at": datetime.now(timezone.utc).isoformat(),
        "committed_by": "submit-arlo-o3-voice",
        "prompt": {
            "verbatim": user_prompt,
            "prepared_for_api": prepared or user_prompt,
            "spoken_sent": spoken_sent,
            "sha256": _sha256_text(user_prompt),
        },
        "visual": {
            "char_ref_abs_path": char_path,
            "char_ref_sha256": _sha256_file(char_path),
            "bg_ref_abs_path": bg_path,
            "bg_ref_sha256": _sha256_file(bg_path),
            "reference_image_locked": ref_locked,
            "element_char_ref_gate": {
                "aligned": True,
                "method": "live_refer_images",
                "refer_images_resolved": _refer_images_rel(speaker),
                "registration_action": registration_action,
                "detail": gate_detail or None,
            },
        },
        "voice": {
            "speaker": speaker,
            "element_id": str(element_entry.get("element_id") or ""),
            "element_name": str(element_entry.get("element_name") or ""),
            "kling_voice_id": str(element_entry.get("voice_id") or reg.get_bound_voice_id(speaker) or ""),
            "proven_o3_bind": {
                "lock_element_id": bool(proven_bind.get("lock_element_id")),
                "proven_from_beat_id": str(proven_bind.get("proven_from_beat_id") or ""),
            } if proven_bind else None,
        },
        "generation": {
            "slot": f"g{next_gen}",
            "slot_index": next_gen,
            "master_clip_path": str(master),
            "delivery_clip_path": str(delivery),
            "sidecar_gen_before": sidecar_gen,
            "disk_gen_max_before": disk_gen_max,
            "replace_slot_index": replace_slot,
            "duration": duration,
        },
        "runtime": {
            "attempt_id": attempt_id,
            "log_path": str(log_path),
            "pipeline_script": str(pipeline_script),
        },
        "preflight": {
            "checks_passed": [
                "prompt_non_empty",
                "char_ref_file_exists",
                "bg_ref_file_exists",
                "element_char_ref_aligned",
                "proven_o3_bind_valid",
                "slot_reserved",
            ],
            "canonical_skipped": [
                "ensure_operator_insert_char_ref_parity",
                "finalize_proven_element_beat",
                "apply_kling_o3_defaults_to_beat",
                "heal_o3_element_submit_prompt",
            ],
        },
    }
    return intent


def _refer_images_rel(speaker: str) -> list[str]:
    from tools import kling_character_registry as reg

    root = reg.prod_root()
    paths = reg.element_image_paths(speaker)
    out: list[str] = []
    for p in paths:
        try:
            out.append(str(p.relative_to(root)))
        except ValueError:
            out.append(str(p))
    return out


def sidecar_fields_from_intent(intent: dict) -> dict:
    """Beat fields to mirror at commit time (same bytes as intent, not rebuilt)."""
    prompt = str((intent.get("prompt") or {}).get("verbatim") or "")
    visual = intent.get("visual") or {}
    generation = intent.get("generation") or {}
    return {
        "kling_o3_prompt": prompt,
        "o3_prompt_box_law": True,
        "reference_image": {
            "abs_path": visual.get("char_ref_abs_path"),
        },
        "bg_ref_image": {
            "abs_path": visual.get("bg_ref_abs_path"),
        },
        "reference_image_locked": visual.get("reference_image_locked", True),
        "kling_o3_replace_slot_index": generation.get("replace_slot_index", 0),
        "kling_o3_duration": generation.get("duration"),
        "element_char_ref_ok": True,
        "o3_active_intent_id": intent.get("intent_id"),
        "o3_active_intent_job_id": intent.get("job_id"),
    }
