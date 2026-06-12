"""Stitch editor handlers — V59 Phase 4 Pass 2.

Handlers extracted from production_server.py.
Each function takes the live `ProductionHandler` instance as `h`.
"""
from __future__ import annotations

import argparse
import base64
import collections as _pathapp_collections
import concurrent.futures as _cf
import functools
import hashlib
import io
import json
import os
import platform
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import uuid as _stdlib_uuid
import uuid as _pathapp_uuid
import http.client
import ssl
import traceback
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# V59 Phase 4 path-depth correction: extracted modules are one level
# deeper than production_server.py. These constants map original
# `_PSERVER_TOOLS_DIR[.parent]*` targets correctly.
# LD-505 Phase C (2026-05-19): _PSERVER_TOOLS_DIR is for CODE-tree only
# (sys.path inserts to import sibling Python modules). NOT for data paths.
_PSERVER_TOOLS_DIR = Path(__file__).resolve().parent.parent  # Production/tools/


# Project-internal modules imported the same way production_server.py does.
# Handler bodies may reference any of these by bare name.
from lib.atomic_json_write import atomic_json_write
from lib.v3_partition import _iter_v3_beats
from lib.paths import DROPBOX_ROOT
import scope_router
from ffmpeg_utils import strip_audio as _strip_clip_audio
from lipsync_sender import LipSyncClient, COST_PER_LIPSYNC

from server_handlers._path_security import (
    MEDIA_EXTENSIONS,
    require_media_under_project,
)

# Late-resolvable private helpers from the host module.
from tools.production_server import (  # noqa: E402
    _resolve_module_id_for_state,
    _silcomp_audio,
)

# Canonical stitch job: one per event; slots accumulate across Send Out + exports.
STITCH_SLOT_ORDER = ["intro", "phase_a", "phase_b", "resolution"]
# Canonical under-speech ambient level (Phase A stitch + preview/bake mix).
STITCH_AMBIENT_BED_VOLUME = 0.15


def stitch_event_job_name(event_id: str) -> str:
    return f"{event_id}_stitch"


def _normalize_job_slots(slots) -> dict:
    if isinstance(slots, dict):
        return dict(slots)
    return {}


def _slot_has_video(slot) -> bool:
    return isinstance(slot, dict) and bool((slot.get("video_path") or "").strip())


def _slot_merge_worthy(slot) -> bool:
    """Fields that may be merged into an existing stitch job slot."""
    if not isinstance(slot, dict):
        return False
    return (
        _slot_has_video(slot)
        or slot.get("sfx_cues")
        or slot.get("trim_in_s") is not None
        or slot.get("trim_out_ms") is not None
        or "ambient_bed" in slot
    )


def _resolve_stitch_ambient_bed_path(h, preset_or_path: str) -> str:
    """Map stitch slot ambient_bed preset_id → on-disk mp3 for ffmpeg mix."""
    raw = (preset_or_path or "").strip()
    if not raw:
        return ""
    if os.path.isfile(raw):
        return raw
    if "/" in raw or "\\" in raw or ".." in raw:
        return ""
    project_root = h._stitch_project_root()
    for rel in (
        Path("Production") / "assets" / "sound_library" / "ambient" / f"{raw}.mp3",
        Path("Production") / "assets" / "ambient_library" / f"{raw}.mp3",
    ):
        candidate = project_root / rel
        if candidate.is_file():
            return str(candidate.resolve())
    return ""


def _hydrate_slot_ambient_paths(h, slots: list) -> None:
    """In-place: ambient_bed preset_id → ambient_bed_path for preview/bake mix."""
    for slot in slots:
        if not isinstance(slot, dict):
            continue
        preset = (slot.get("ambient_bed") or "").strip()
        if preset:
            resolved = _resolve_stitch_ambient_bed_path(h, preset)
            if resolved:
                slot["ambient_bed_path"] = resolved
                slot.setdefault("ambient_volume", STITCH_AMBIENT_BED_VOLUME)
            else:
                slot.pop("ambient_bed_path", None)
        else:
            slot.pop("ambient_bed_path", None)


def stitch_migrate_legacy_to_canonical(state: dict, event_id: str) -> bool:
    """Merge auto_* / phase_* legacy jobs into {event_id}_stitch without dropping slots."""
    jobs = state.setdefault("jobs", {})
    canonical_name = stitch_event_job_name(event_id)
    canonical = jobs.setdefault(
        canonical_name,
        {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "slots": {},
            "transitions": [],
        },
    )
    if not isinstance(canonical.get("slots"), dict):
        canonical["slots"] = {}

    merged: dict[str, dict] = {}
    for slot_key in STITCH_SLOT_ORDER:
        existing = canonical["slots"].get(slot_key)
        if _slot_has_video(existing):
            merged[slot_key] = dict(existing)

    changed = False
    for name, job in jobs.items():
        if name == canonical_name:
            continue
        if not (
            name.startswith("auto_")
            or (name.startswith("phase_") and event_id in name)
        ):
            continue
        for slot_key, slot in _normalize_job_slots(job.get("slots")).items():
            if slot_key not in STITCH_SLOT_ORDER or not _slot_has_video(slot):
                continue
            prev = merged.get(slot_key)
            if prev is None or not _slot_has_video(prev):
                merged[slot_key] = dict(slot)
                changed = True

    for slot_key, slot in merged.items():
        if not _slot_has_video(slot):
            continue
        prev = canonical["slots"].get(slot_key) or {}
        if prev.get("video_path") != slot.get("video_path") or not _slot_has_video(prev):
            canonical["slots"][slot_key] = {**prev, **slot}
            changed = True

    if changed:
        canonical["updated_at"] = datetime.now(timezone.utc).isoformat()
    return changed


def enrich_beat_boundaries(boundaries: list | None) -> list | None:
    """Ensure each boundary has duration_ms (UI roadmap + waveform math)."""
    if not boundaries:
        return boundaries
    out: list[dict] = []
    for raw in boundaries:
        if not isinstance(raw, dict):
            continue
        b = dict(raw)
        if b.get("duration_ms") is None:
            try:
                b["duration_ms"] = int(b["end_ms"]) - int(b["start_ms"])
            except (TypeError, ValueError, KeyError):
                continue
        out.append(b)
    return out


def stitch_upsert_event_slot(
    h,
    event_id: str,
    slot_key: str,
    slot_patch: dict,
    *,
    beat_boundaries: list | None = None,
) -> str:
    """Upsert one slot into the canonical per-event stitch job."""
    if slot_key not in STITCH_SLOT_ORDER:
        raise ValueError(f"invalid stitch slot key: {slot_key!r}")

    now_iso = datetime.now(timezone.utc).isoformat()
    job_name = stitch_event_job_name(event_id)

    def upsert(state: dict) -> None:
        stitch_migrate_legacy_to_canonical(state, event_id)
        jobs = state.setdefault("jobs", {})
        job = jobs[job_name]
        if not isinstance(job.get("slots"), dict):
            job["slots"] = {}
        slot = job["slots"].setdefault(slot_key, {})
        slot.update(slot_patch)
        if beat_boundaries is not None:
            slot["beat_boundaries"] = enrich_beat_boundaries(beat_boundaries)
        job["updated_at"] = now_iso

    h.app.stitch_state.mutate_state(upsert)
    return job_name


def handle_stitch_loudnorm(h, body: dict)-> None:

    """POST /api/stitch_editor/loudnorm — apply ffmpeg single-pass loudnorm.

    Body: {
      input_path: str,        # absolute or event-relative path to mp4
      output_path?: str,      # optional override; default <input>_ln.mp4
      target_lufs?: float,    # default -19 (matches _silcomp_audio pattern)
      target_tp?: float,      # default -1.5 dBTP
      target_lra?: float,     # default 11 LU
      scope_event_id?: str
    }

    Skips re-application if input has already been marked
    loudnorm_already_applied=true in stitch_state (lipsync outputs auto-mark
    themselves to prevent double-application).

    Per LD-466 EXPORT_TO_STITCHER_V1 + spec §3.5.1 + Rule 8 (audio safety).
    """
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return

    input_path_raw = (body or {}).get("input_path")
    if not input_path_raw:
        return h._send_error_v59(
                   400,
                   error_code="MISSING_INPUT_PATH",
                   error_message="input_path required",
                   retry_safe=False,
               )

    try:
        ip_str = h._stitch_resolve_path(input_path_raw)
    except ValueError:
        return h._send_error_v59(
                   403,
                   error_code="INPUT_PATH_OUTSIDE_PROJECT_ROOT",
                   error_message="input_path outside project root",
                   retry_safe=False,
               )
    try:
        ip_str = require_media_under_project(ip_str, extensions=MEDIA_EXTENSIONS)
    except ValueError as exc:
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=str(exc),
                   retry_safe=False,
               )
    except FileNotFoundError:
        return h._send_error_v59(
                   404,
                   error_code="INPUT_FILE_NOT_FOUND",
                   error_message="input file not found",
                   retry_safe=False,
                   extra={"input_path": input_path_raw},
               )
    ip = Path(ip_str)

    target_lufs = float((body or {}).get("target_lufs", -19.0))
    target_tp = float((body or {}).get("target_tp", -1.5))
    target_lra = float((body or {}).get("target_lra", 11.0))

    # Output path: default to <input>_ln.<ext> in same dir.
    out_raw = (body or {}).get("output_path")
    if out_raw:
        try:
            op_str = h._stitch_resolve_path(out_raw)
        except ValueError:
            return h._send_error_v59(
                       403,
                       error_code="OUTPUT_PATH_OUTSIDE_PROJECT_ROOT",
                       error_message="output_path outside project root",
                       retry_safe=False,
                   )
        op = Path(op_str)
    else:
        op = ip.with_name(f"{ip.stem}_ln{ip.suffix}")

    # Already-applied guard: check stitch_state.
    try:
        stitch = h.app.stitch_state.read_state() or {}
    except Exception:
        stitch = {}
    applied_paths = set(stitch.get("loudnorm_already_applied_paths", []))
    if str(ip) in applied_paths:
        return h._send_json(200, {
            "ok": True,
            "skipped": True,
            "reason": "loudnorm_already_applied",
            "input_path": str(ip),
            "output_path": str(ip),  # nothing to do; "output" is the input
        })

    # Run ffmpeg single-pass loudnorm.
    # -af "loudnorm=I=-19:TP=-1.5:LRA=11" -c:v copy preserves video frames.
    # CodeQL-recognized sanitizer at subprocess sink (require_media already validated).
    safe_ffmpeg_in = os.path.realpath(ip_str)
    safe_ffmpeg_out = os.path.realpath(str(op.resolve()))
    cmd = [
        "ffmpeg", "-y",
        "-i", safe_ffmpeg_in,
        "-af", f"loudnorm=I={target_lufs}:TP={target_tp}:LRA={target_lra}",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        safe_ffmpeg_out,
    ]
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, timeout=600)
    except subprocess.CalledProcessError as exc:
        return h._send_error_v59(
                   500,
                   error_code="FFMPEG_LOUDNORM_FAILED",
                   error_message="ffmpeg loudnorm failed",
                   retry_safe=True,
                   extra={"returncode": exc.returncode, "stderr": exc.stderr.decode("utf-8", errors="replace")[-2000:]},
               )
    except subprocess.TimeoutExpired:
        return h._send_error_v59(
                   504,
                   error_code="FFMPEG_LOUDNORM_TIMED_OUT",
                   error_message="ffmpeg loudnorm timed out (>600s)",
                   retry_safe=True,
               )

    # Mark the OUTPUT as loudnorm_already_applied so a re-run skips it.
    try:
        def _mark(state, _p=str(op)):
            paths = state.setdefault("loudnorm_already_applied_paths", [])
            if _p not in paths:
                paths.append(_p)
            return None
        h.app.stitch_state.mutate_state(_mark)
    except Exception as exc:
        print(f"[loudnorm] WARN could not mark applied: {exc}", flush=True)

    safe_op_check = os.path.realpath(str(op.resolve()))
    if not os.path.isfile(safe_op_check):
        return h._send_error_v59(
                   500,
                   error_code="FFMPEG_SUCCEEDED_BUT_OUTPUT_FILE",
                   error_message="ffmpeg succeeded but output file missing",
                   retry_safe=True,
                   extra={"output_path": str(op)},
               )
    size_bytes = op.stat().st_size
    return h._send_json(200, {
        "ok": True,
        "input_path": str(ip),
        "output_path": str(op),
        "size_bytes": size_bytes,
        "target_lufs": target_lufs,
        "target_tp": target_tp,
        "target_lra": target_lra,
        "marked_loudnorm_already_applied": True,
    })


def handle_stitch_library(h)-> None:

    """GET /api/stitch_editor/library — scan sound_library + backward-compat dirs.

    Returns {ambient: [...], sfx: [...], transitions: [...]}.
    Each item: {filename, path, duration_ms, category, source_folder}.
    Canonical folders (sound_library/*) take priority over backward-compat duplicates.
    """
    production = h._stitch_production_dir()
    project_root = h._stitch_project_root()
    canonical_base = production / "assets" / "sound_library"

    result: dict[str, list[dict]] = {"ambient": [], "sfx": [], "transitions": []}
    seen_filenames: set[str] = set()

    def scan(scan_dir: Path, category: str, source_label: str) -> None:
        if not scan_dir.is_dir():
            return
        for pat in ("*.mp3", "*.wav", "*.m4a"):
            for f in sorted(scan_dir.glob(pat)):
                if f.name in seen_filenames:
                    continue
                seen_filenames.add(f.name)
                result[category].append({
                    "filename": f.name,
                    "path": str(f),
                    "duration_ms": h._ffprobe_duration_ms(f),
                    "category": category,
                    "source_folder": source_label,
                })

    # 1. Canonical folders (preferred — Kim populates these)
    scan(canonical_base / "ambient", "ambient", "sound_library/ambient")
    scan(canonical_base / "sfx", "sfx", "sound_library/sfx")
    scan(canonical_base / "transitions", "transitions", "sound_library/transitions")

    # 2. Backward-compat scan (for files not yet migrated to canonical)
    event1_sfx = h.app.event_dir / "sfx"
    if event1_sfx.is_dir():
        for pat in ("*.mp3", "*.wav", "*.m4a"):
            for f in sorted(event1_sfx.glob(pat)):
                if f.name in seen_filenames:
                    continue
                seen_filenames.add(f.name)
                name_lower = f.name.lower()
                if any(x in name_lower for x in ("outtro", "whoosh", "return_to_map")):
                    cat = "transitions"
                else:
                    cat = "sfx"
                result[cat].append({
                    "filename": f.name, "path": str(f),
                    "duration_ms": h._ffprobe_duration_ms(f),
                    "category": cat, "source_folder": "Event_1/sfx (legacy)",
                })

    ambient_lib = production / "assets" / "ambient_library"
    scan(ambient_lib, "ambient", "ambient_library (legacy)")

    # 3. Project-root canonical SFX
    for fname in ["magic burst sound for in video.mp3", "magic sound.mp3", "whoosh sound.mp3"]:
        fp = project_root / fname
        if fp.is_file() and fp.name not in seen_filenames:
            seen_filenames.add(fp.name)
            result["sfx"].append({
                "filename": fp.name, "path": str(fp),
                "duration_ms": h._ffprobe_duration_ms(fp),
                "category": "sfx", "source_folder": "project_root (legacy)",
            })

    h.send_response(200)
    h.send_header("Content-Type", "application/json")
    h.send_header("Cache-Control", "no-store")
    h._cors_headers()
    payload = json.dumps(result).encode()
    h.send_header("Content-Length", str(len(payload)))
    h.end_headers()
    h.wfile.write(payload)


def handle_stitch_list_jobs(h)-> None:

    """GET /api/stitch_editor/jobs — list saved job summaries."""
    state = h.app.stitch_state.read_state()
    jobs = [
        {
            "name": k,
            "created_at": v.get("created_at", ""),
            "updated_at": v.get("updated_at", ""),
            "slot_count": len(v.get("slots", [])),
        }
        for k, v in state.get("jobs", {}).items()
    ]
    return h._send_json(200, {"jobs": jobs})


def handle_stitch_load_job(h, name: str)-> None:

    """GET /api/stitch_editor/job/<name> — load full job dict."""
    if name.endswith("_stitch"):
        event_id = name[: -len("_stitch")]
        if event_id:

            def migrate(state: dict) -> None:
                stitch_migrate_legacy_to_canonical(state, event_id)

            h.app.stitch_state.mutate_state(migrate)

    import copy  # noqa: PLC0415

    state = h.app.stitch_state.read_state()
    job = state.get("jobs", {}).get(name)
    if job is None:
        return h._send_error_v59(
                   404,
                   error_code="GENERIC_ERROR",
                   error_message=f"Job not found: {name!r}",
                   retry_safe=False,
               )
    response_job = copy.deepcopy(job) if isinstance(job, dict) else job
    if isinstance(response_job, dict):
        slots = response_job.get("slots")
        if isinstance(slots, dict):
            for slot in slots.values():
                if isinstance(slot, dict) and slot.get("beat_boundaries"):
                    slot["beat_boundaries"] = enrich_beat_boundaries(
                        slot["beat_boundaries"],
                    )
    return h._send_json(200, {"job": response_job, "name": name})


def handle_stitch_save_job(h, body: dict)-> None:

    """POST /api/stitch_editor/job — save or upsert a named job."""
    # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return

    name = (body.get("name") or "").strip()
    if not name:
        return h._send_error_v59(
                   400,
                   error_code="MISSING_JOB_NAME",
                   error_message="Job name is required",
                   retry_safe=False,
               )

    slots_raw = body.get("slots")
    transitions = body.get("transitions", [])
    slot_key_partial = (body.get("slot") or "").strip()
    ambient_bed_partial = body.get("ambient_bed") if "ambient_bed" in body else None

    # Legacy v59 client sent {name, slot, ambient_bed} without slots — never wipe job.
    partial_ambient_merge = False
    if (
        slots_raw is None
        and slot_key_partial in STITCH_SLOT_ORDER
        and ambient_bed_partial is not None
    ):
        partial_ambient_merge = True
        slots_raw = {slot_key_partial: {"ambient_bed": ambient_bed_partial or ""}}
    elif slots_raw is None:
        slots_raw = []

    # Slots may be dict keyed by slot id (v59 client + scene_assemble auto-populate)
    # or legacy list. Validate video_path on slot dict values only.
    if isinstance(slots_raw, dict):
        slots = slots_raw
        slot_items = [v for v in slots_raw.values() if isinstance(v, dict)]
    elif isinstance(slots_raw, list):
        slots = slots_raw
        slot_items = [s for s in slots_raw if isinstance(s, dict)]
    else:
        slots = {}
        slot_items = []

    for i, slot in enumerate(slot_items):
        vp = slot.get("video_path", "")
        if vp:
            try:
                h._stitch_resolve_path(vp)
            except ValueError:
                return h._send_error_v59(
                           403,
                           error_code="GENERIC_ERROR",
                           error_message=f"Slot {i} video_path outside project root",
                           retry_safe=False,
                       )

    now_iso = datetime.now(timezone.utc).isoformat()
    merge_slots = bool(body.get("merge_slots")) or partial_ambient_merge
    scope = h._scope_body(body) or {}
    event_id = (scope.get("event_id") or scope.get("scope_event_id") or "").strip()

    def upsert(state: dict) -> None:
        jobs = state.setdefault("jobs", {})
        existing = jobs.get(name, {})
        if merge_slots and event_id and name == stitch_event_job_name(event_id):
            stitch_migrate_legacy_to_canonical(state, event_id)
            existing = jobs.get(name, {})
            base_slots = _normalize_job_slots(existing.get("slots"))
            incoming = _normalize_job_slots(slots)
            for slot_key, slot in incoming.items():
                if not isinstance(slot, dict):
                    continue
                if _slot_merge_worthy(slot):
                    prev = base_slots.get(slot_key) or {}
                    merged = {**prev, **slot}
                    if "ambient_bed" in slot and (slot.get("ambient_bed") or "") != (
                        prev.get("ambient_bed") or ""
                    ):
                        merged.pop("ambient_bed_path", None)
                    if (merged.get("ambient_bed") or "").strip():
                        merged.setdefault("ambient_volume", STITCH_AMBIENT_BED_VOLUME)
                    elif "ambient_bed" in slot:
                        merged.pop("ambient_volume", None)
                    base_slots[slot_key] = merged
            slots_out = base_slots
        elif merge_slots and isinstance(slots, dict):
            base_slots = _normalize_job_slots(existing.get("slots"))
            for slot_key, slot in slots.items():
                if not isinstance(slot, dict):
                    continue
                if _slot_merge_worthy(slot):
                    prev = base_slots.get(slot_key) or {}
                    merged = {**prev, **slot}
                    if "ambient_bed" in slot and (slot.get("ambient_bed") or "") != (
                        prev.get("ambient_bed") or ""
                    ):
                        merged.pop("ambient_bed_path", None)
                    if (merged.get("ambient_bed") or "").strip():
                        merged.setdefault("ambient_volume", STITCH_AMBIENT_BED_VOLUME)
                    elif "ambient_bed" in slot:
                        merged.pop("ambient_volume", None)
                    base_slots[slot_key] = merged
            slots_out = base_slots
        elif not slot_items and existing.get("slots"):
            # Malformed save without merge_slots — preserve existing slots.
            slots_out = _normalize_job_slots(existing.get("slots"))
        else:
            slots_out = slots
        jobs[name] = {
            "created_at": existing.get("created_at", now_iso),
            "updated_at": now_iso,
            "slots": slots_out,
            "transitions": transitions if transitions else existing.get("transitions", []),
        }

    h.app.stitch_state.mutate_state(upsert)
    return h._send_json(200, {"ok": True, "name": name})


def handle_stitch_delete_job(h, name: str)-> None:

    """DELETE /api/stitch_editor/job/<name> — remove named job."""
    # LD-456 SCOPE_VALIDATION_V1 (no-body handler — query-string fallback inside helper)
    if not h._assert_event_scope({}, allow_missing=True):
        return

    def remove(state: dict) -> None:
        state.get("jobs", {}).pop(name, None)
    h.app.stitch_state.mutate_state(remove)
    return h._send_json(200, {"ok": True, "name": name})


def handle_stitch_audio_extract(h, body: dict)-> None:

    """POST /api/stitch_editor/audio_extract — extract audio track for WaveSurfer.

    Input: {video_path, optional ambient_bed preset_id, optional ambient_volume}
    Output: {audio_url: "http://localhost:5111/api/stitch_editor/audio_file/<hash>", duration_ms: N}
    When ambient_bed is set, mixes the bed under slot video audio for composer waveform parity.
    """
    import hashlib as _hl  # noqa: PLC0415
    video_path_str = body.get("video_path", "")
    if not video_path_str:
        return h._send_error_v59(
                   400,
                   error_code="VIDEO_PATH_REQUIRED",
                   error_message="video_path required",
                   retry_safe=False,
               )

    try:
        abs_path = h._stitch_resolve_path(video_path_str)
    except ValueError:
        return h._send_error_v59(
                   403,
                   error_code="VIDEO_PATH_OUTSIDE_PROJECT_ROOT",
                   error_message="video_path outside project root",
                   retry_safe=False,
               )
    try:
        abs_path = require_media_under_project(
            abs_path, extensions=MEDIA_EXTENSIONS,
        )
    except ValueError as exc:
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=str(exc),
                   retry_safe=False,
               )
    except FileNotFoundError:
        return h._send_error_v59(
                   404,
                   error_code="GENERIC_ERROR",
                   error_message=f"File not found: {video_path_str}",
                   retry_safe=False,
               )

    # Cache key: md5(path) + mtime — Producer/Consumer drift rule (source identity)
    mtime_ms = int(os.path.getmtime(abs_path) * 1000)
    cache_key = _hl.md5(
        f"{abs_path}:{mtime_ms}".encode(), usedforsecurity=False
    ).hexdigest()[:16]

    cache_dir = h._stitch_cache_dir()
    audio_fname = f"stitch_audio_{cache_key}.mp3"
    audio_path = cache_dir / audio_fname

    if not audio_path.is_file():
        safe_ffmpeg_src = os.path.realpath(abs_path)
        ffmpeg_dst = str(audio_path.resolve())
        cmd = [
            "ffmpeg", "-y", "-i", safe_ffmpeg_src,
            "-vn", "-ac", "1", "-ar", "44100", "-b:a", "128k",
            ffmpeg_dst,
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=180)
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or b"")[:400].decode("utf-8", errors="replace")
            return h._send_error_v59(
                       500,
                       error_code="AUDIO_EXTRACTION_FAILED",
                       error_message="audio extraction failed",
                       retry_safe=True,
                       extra={"stderr": stderr},
                   )
        except subprocess.TimeoutExpired:
            return h._send_error_v59(
                       504,
                       error_code="AUDIO_EXTRACTION_TIMED_OUT",
                       error_message="audio extraction timed out",
                       retry_safe=True,
                   )

    duration_ms = h._ffprobe_duration_ms(audio_path)
    serve_fname = audio_fname
    ambient_bed = (body.get("ambient_bed") or "").strip()
    ambient_volume = float(body.get("ambient_volume", STITCH_AMBIENT_BED_VOLUME))
    ambient_path = _resolve_stitch_ambient_bed_path(h, ambient_bed) if ambient_bed else ""
    if ambient_path and not os.path.isfile(ambient_path):
        ambient_path = ""

    if ambient_path:
        mix_sig = _hl.md5(
            f"{cache_key}:{ambient_path}:{ambient_volume:.4f}".encode(),
            usedforsecurity=False,
        ).hexdigest()[:12]
        mixed_fname = f"stitch_audio_{mix_sig}.mp3"
        mixed_path = cache_dir / mixed_fname
        if not mixed_path.is_file():
            slot_dur_s = max(duration_ms, 1) / 1000.0
            filter_complex = (
                f"[1:a]aloop=-1:size=2147483647,atrim=duration={slot_dur_s:.3f},"
                f"volume={ambient_volume:.3f}[bed];"
                f"[0:a][bed]amix=inputs=2:duration=first:normalize=0[aout]"
            )
            mix_cmd = [
                "ffmpeg", "-y",
                "-i", str(audio_path.resolve()),
                "-i", ambient_path,
                "-filter_complex", filter_complex,
                "-map", "[aout]",
                "-ac", "1", "-ar", "44100", "-b:a", "128k",
                str(mixed_path.resolve()),
            ]
            try:
                subprocess.run(mix_cmd, check=True, capture_output=True, timeout=180)
            except subprocess.CalledProcessError as exc:
                stderr = (exc.stderr or b"")[:400].decode("utf-8", errors="replace")
                return h._send_error_v59(
                           500,
                           error_code="AMBIENT_MIX_FAILED",
                           error_message="ambient waveform mix failed",
                           retry_safe=True,
                           extra={"stderr": stderr},
                       )
            except subprocess.TimeoutExpired:
                return h._send_error_v59(
                           504,
                           error_code="AMBIENT_MIX_TIMED_OUT",
                           error_message="ambient waveform mix timed out",
                           retry_safe=True,
                       )
        serve_fname = mixed_fname
        duration_ms = h._ffprobe_duration_ms(mixed_path)

    return h._send_json(200, {
        "audio_url": f"http://localhost:5111/api/stitch_editor/audio_file/{serve_fname}",
        "duration_ms": duration_ms,
        "ambient_mixed": bool(ambient_path),
    })


_STITCH_SLOT_ORDER = ["intro", "phase_a", "phase_b", "resolution"]
_DEFAULT_PHASE_TRANSITION_FADE_MS = 2800


def default_stitch_transitions() -> list[dict]:
    """Prolonged dissolve at each phase boundary (matches intro canonical fade scale)."""
    return [
        {
            "after_slot": i,
            "kind": "dissolve",
            "fade_ms": _DEFAULT_PHASE_TRANSITION_FADE_MS,
            "audio_xfade_ms": 0,
        }
        for i in range(3)
    ]


def hydrate_stitch_pipeline_body(h, body: dict) -> dict:
    """Load ordered slots + transitions from stitch job when client sends {name} only."""
    _body = dict(body or {})
    job_name = _body.get("name") or ""
    job = None
    if job_name:
        try:
            _st = h.app.stitch_state.read_state()
            job = (_st.get("jobs") or {}).get(job_name)
        except Exception as exc:
            print(f"[stitch] WARN: job hydration read failed: {exc}")

    if not _body.get("slots") and job:
        _slots_dict = job.get("slots") or {}
        if isinstance(_slots_dict, dict):
            _slots_list = [
                _slots_dict[k]
                for k in _STITCH_SLOT_ORDER
                if k in _slots_dict and (_slots_dict[k] or {}).get("video_path")
            ]
        else:
            _slots_list = [
                s for s in (_slots_dict or [])
                if isinstance(s, dict) and s.get("video_path")
            ]
        if _slots_list:
            _body["slots"] = _slots_list
            _hydrate_slot_ambient_paths(h, _body["slots"])

    if _body.get("slots"):
        _hydrate_slot_ambient_paths(h, _body["slots"])

    if "transitions" not in _body and job:
        _body["transitions"] = job.get("transitions") or []

    if not _body.get("transitions"):
        _body["transitions"] = default_stitch_transitions()

    return _body


def handle_stitch_preview(h, body: dict)-> None:

    """POST /api/stitch_editor/preview — build temp MP4, return URL for inline playback.

    LD-140: preview is unregistered. Rule 19: all error paths explicit.
    V59 architectural-fix (Wave 1, 2026-05-04): scope-guarded for
    consistency with _handle_stitch_bake / _handle_stitch_save_job per
    MUTATION_CHANNEL_INVARIANT_V1 + LD-456 SCOPE_VALIDATION_V1.
    """
    # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return
    try:
        hydrated = hydrate_stitch_pipeline_body(h, body)
        out_path, slot_durations, slot_start_offsets_ms = h._stitch_build_pipeline(hydrated)
    except (ValueError, PermissionError) as exc:
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=str(exc),
                   retry_safe=False,
               )
    except FileNotFoundError as exc:
        return h._send_error_v59(
                   404,
                   error_code="GENERIC_ERROR",
                   error_message=str(exc),
                   retry_safe=False,
               )
    except RuntimeError as exc:
        return h._send_error_v59(
                   500,
                   error_code="GENERIC_ERROR",
                   error_message=str(exc),
                   retry_safe=True,
               )

    # Strip the stitch_preview_ prefix for the URL hash segment
    hash_id = out_path.stem.replace("stitch_preview_", "")
    duration_ms = h._ffprobe_duration_ms(out_path)
    return h._send_json(200, {
        "preview_url": f"http://localhost:5111/api/stitch_editor/preview_file/{hash_id}",
        "duration_ms": duration_ms,
        "slot_durations": slot_durations,
        "slot_start_offsets_ms": slot_start_offsets_ms,
    })


def handle_stitch_bake(h, body: dict)-> None:

    """POST /api/stitch_editor/bake — final MP4, SIZE_BUDGET gates, Directus registration.

    LD-140: bake IS registered (unlike preview). LD-280: single atomic MP4.
    LD-283: ≤80MB. SIZE_BUDGET_VIDEO_V1: ≤1,900,000 bps.
    """
    # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return

    # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — capture pin at entry; terminal writes assert via _check_event_pin.
    _pin = {
        "pinned_generation": h.app.event_generation,
        "pinned_event_dir": h.app.event_dir,
        "pinned_video_role": (body or {}).get("scope_video_role", "intro"),
        "_handler": '_handle_stitch_bake',
    }
    # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — pre-work pin check (S2).
    # If the event was swapped via /api/event/load between scope-guard
    # and work start, abort BEFORE any expensive work begins.
    if not h._check_event_pin(_pin, '_handle_stitch_bake_pre_work'):
        return h._send_error_v59(
                   423,
                   error_code="EVENT_CHANGED_PRE_WORK",
                   error_message="event_changed_pre_work",
                   retry_safe=False,
                   extra={"code": "ASYNC_JOB_GENERATION_PIN_V1", "handler": '_handle_stitch_bake', "hint": "Event changed between scope-guard and work start. "
                "No work was done; no orphan output. Client should "
                "re-hydrate scope and retry."},
               )

    import fcntl  # noqa: PLC0415

    bake_lock_path = h._stitch_cache_dir() / "stitch_bake.lock"
    bake_lock_path.touch(exist_ok=True)

    try:
        # nosec: CodeQL false-positive — lock_path from server stitch cache dir, not user input
        fd = os.open(str(bake_lock_path), os.O_RDWR)
        try:
            fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError):
            os.close(fd)
            return h._send_error_v59(
                       409,
                       error_code="BAKE_ALREADY_IN_PROGRESS",
                       error_message="Bake already in progress",
                       retry_safe=False,
                   )
    except Exception as exc:
        return h._send_error_v59(
                   500,
                   error_code="GENERIC_ERROR",
                   error_message=f"Lock setup failed: {exc}",
                   retry_safe=True,
               )

    try:
        _body = hydrate_stitch_pipeline_body(h, body)
        if not _body.get("slots"):
            raise ValueError("No slots provided — assign videos to all stitch slots first")

        try:
            out_path, _durations, _slot_starts = h._stitch_build_pipeline(_body)
        except (ValueError, PermissionError) as exc:
            return h._send_error_v59(
                       400,
                       error_code="GENERIC_ERROR",
                       error_message=str(exc),
                       retry_safe=False,
                   )
        except FileNotFoundError as exc:
            return h._send_error_v59(
                       404,
                       error_code="GENERIC_ERROR",
                       error_message=str(exc),
                       retry_safe=False,
                   )
        except RuntimeError as exc:
            return h._send_error_v59(
                       500,
                       error_code="GENERIC_ERROR",
                       error_message=str(exc),
                       retry_safe=True,
                   )

        # SIZE_BUDGET_VIDEO_V1: ffprobe bitrate assertion ≤ 1,900,000 bps
        try:
            # nosec: CodeQL false-positive — out_path from server _stitch_build_pipeline
            vp = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=bit_rate",
                 "-of", "json", str(out_path.resolve())],
                capture_output=True, timeout=10, check=True,
            )
            bitrate = int(json.loads(vp.stdout).get("format", {}).get("bit_rate", 0))
        except Exception:
            bitrate = 0

        if bitrate > 1_900_000:
            out_path.unlink(missing_ok=True)
            return h._send_error_v59(
                       422,
                       error_code="GENERIC_ERROR",
                       error_message=f"Video bitrate {bitrate:,} bps exceeds 1,900,000 bps (SIZE_BUDGET_VIDEO_V1)",
                       retry_safe=False,
                       extra={"actual_bps": bitrate},
                   )

        # SIZE_BUDGET_PER_MODULE_V1: ≤ 80 MB
        file_size = out_path.stat().st_size
        size_mb = file_size / (1024 * 1024)
        if size_mb > 80.0:
            out_path.unlink(missing_ok=True)
            return h._send_error_v59(
                       422,
                       error_code="GENERIC_ERROR",
                       error_message=f"Output {size_mb:.1f} MB exceeds 80 MB ceiling (SIZE_BUDGET_PER_MODULE_V1)",
                       retry_safe=False,
                       extra={"actual_bytes": file_size},
                   )

        # Copy to stable bake path
        job_name = body.get("name") or "untitled"
        now_ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        bake_name = f"stitch_{job_name}_{now_ts}.mp4"
        exports_dir = h._stitch_exports_dir()
        bake_path = exports_dir / bake_name
        shutil.copy2(str(out_path), str(bake_path))

        # LD-421: register via registered_write.py two-write rule
        asset_id = -1
        try:
            # registered_write lives in Production/tools/ (CODE tree)
            sys.path.insert(0, str(_PSERVER_TOOLS_DIR))
            from registered_write import register_asset  # noqa: PLC0415
            slots = _body.get("slots") or []
            iter_notes = (
                f"Stitch editor bake. Job: {job_name}. "
                f"{len(slots)} slot(s), {sum(len(s.get('sfx_cues') or []) for s in slots)} SFX cues."
            )
            # module_id resolved via state.event_id -> prod_modules per
            # LD MODULE_ID_DYNAMIC_RESOLUTION_V1; closes the Rule 19
            # "module_id=1 sentinel" stub class.
            # LD-460 — terminal pin check before final asset register.
            if not h._check_event_pin(_pin, "stitch_bake_register_asset"):
                return h._send_error_v59(
                           423,
                           error_code="EVENT_CHANGED_MID_JOB",
                           error_message="event_changed_mid_job",
                           retry_safe=False,
                           extra={"code": "ASYNC_JOB_GENERATION_PIN_V1", "orphaned_bake_path": str(bake_path)},
                       )
            asset_id, _ = register_asset(
                file_path=str(bake_path),
                asset_type="final_atomic_mp4",
                module_id=_resolve_module_id_for_state(h.app.state),
                event_id=None,
                produced_by_skill="stitch-editor",
                iteration_notes=iter_notes,
                colloquial_name=job_name,
                library=True,
                notes=f"Stitch editor bake {now_ts}. Job: {job_name}. Slots: {[s.get('video_path','?') for s in slots]}",
                role="delivery",
            )
        except Exception as reg_exc:
            print(f"[stitch-bake] WARN: Directus registration failed: {reg_exc}")

        return h._send_json(200, {
            "ok": True,
            "asset_id": asset_id,
            "bake_name": bake_name,
            "bake_path": str(bake_path),
            "file_size_bytes": file_size,
            "bitrate_bps": bitrate,
        })

    finally:
        try:
            fcntl.lockf(fd, fcntl.LOCK_UN)
            os.close(fd)
        except Exception:
            pass


