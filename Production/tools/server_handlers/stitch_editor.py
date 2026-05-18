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
_PSERVER_TOOLS_DIR = Path(__file__).resolve().parent.parent  # Production/tools/
_PSERVER_PRODUCTION_DIR = _PSERVER_TOOLS_DIR.parent  # Production/
_PSERVER_REPO_ROOT = _PSERVER_PRODUCTION_DIR.parent  # repo root


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
        return h._send_json(400, {"error": "input_path required"})

    try:
        ip_str = h._stitch_resolve_path(input_path_raw)
    except ValueError:
        return h._send_json(403, {"error": "input_path outside project root"})
    try:
        ip_str = require_media_under_project(ip_str, extensions=MEDIA_EXTENSIONS)
    except ValueError as exc:
        return h._send_json(400, {"error": str(exc)})
    except FileNotFoundError:
        return h._send_json(404, {
            "error": "input file not found",
            "input_path": input_path_raw,
        })
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
            return h._send_json(403, {"error": "output_path outside project root"})
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
    ffmpeg_in = ip_str
    ffmpeg_out = str(op.resolve())
    cmd = [
        "ffmpeg", "-y",
        "-i", ffmpeg_in,
        "-af", f"loudnorm=I={target_lufs}:TP={target_tp}:LRA={target_lra}",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        ffmpeg_out,
    ]
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, timeout=600)
    except subprocess.CalledProcessError as exc:
        return h._send_json(500, {
            "error": "ffmpeg loudnorm failed",
            "returncode": exc.returncode,
            "stderr": exc.stderr.decode("utf-8", errors="replace")[-2000:],
        })
    except subprocess.TimeoutExpired:
        return h._send_json(504, {"error": "ffmpeg loudnorm timed out (>600s)"})

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

    if not op.is_file():
        return h._send_json(500, {
            "error": "ffmpeg succeeded but output file missing",
            "output_path": str(op),
        })
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
    state = h.app.stitch_state.read_state()
    job = state.get("jobs", {}).get(name)
    if job is None:
        return h._send_json(404, {"error": f"Job not found: {name!r}"})
    return h._send_json(200, {"job": job, "name": name})


def handle_stitch_save_job(h, body: dict)-> None:

    """POST /api/stitch_editor/job — save or upsert a named job."""
    # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return

    name = (body.get("name") or "").strip()
    if not name:
        return h._send_json(400, {"error": "Job name is required"})

    slots = body.get("slots", [])
    transitions = body.get("transitions", [])

    for i, slot in enumerate(slots):
        vp = slot.get("video_path", "")
        if vp:
            try:
                h._stitch_resolve_path(vp)
            except ValueError:
                return h._send_json(403, {"error": f"Slot {i} video_path outside project root"})

    now_iso = datetime.now(timezone.utc).isoformat()

    def upsert(state: dict) -> None:
        jobs = state.setdefault("jobs", {})
        existing = jobs.get(name, {})
        jobs[name] = {
            "created_at": existing.get("created_at", now_iso),
            "updated_at": now_iso,
            "slots": slots,
            "transitions": transitions,
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

    Input: {video_path: "/abs/path/..."}
    Output: {audio_url: "http://localhost:5111/api/stitch_editor/audio_file/<hash>", duration_ms: N}
    """
    import hashlib as _hl  # noqa: PLC0415
    video_path_str = body.get("video_path", "")
    if not video_path_str:
        return h._send_json(400, {"error": "video_path required"})

    try:
        abs_path = h._stitch_resolve_path(video_path_str)
    except ValueError:
        return h._send_json(403, {"error": "video_path outside project root"})
    try:
        abs_path = require_media_under_project(
            abs_path, extensions=MEDIA_EXTENSIONS,
        )
    except ValueError as exc:
        return h._send_json(400, {"error": str(exc)})
    except FileNotFoundError:
        return h._send_json(404, {"error": f"File not found: {video_path_str}"})

    # Cache key: md5(path) + mtime — Producer/Consumer drift rule (source identity)
    mtime_ms = int(os.path.getmtime(abs_path) * 1000)
    cache_key = _hl.md5(
        f"{abs_path}:{mtime_ms}".encode(), usedforsecurity=False
    ).hexdigest()[:16]

    cache_dir = h._stitch_cache_dir()
    audio_fname = f"stitch_audio_{cache_key}.mp3"
    audio_path = cache_dir / audio_fname

    if not audio_path.is_file():
        ffmpeg_src = abs_path
        ffmpeg_dst = str(audio_path.resolve())
        cmd = [
            "ffmpeg", "-y", "-i", ffmpeg_src,
            "-vn", "-ac", "1", "-ar", "44100", "-b:a", "128k",
            ffmpeg_dst,
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=180)
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or b"")[:400].decode("utf-8", errors="replace")
            return h._send_json(500, {"error": "audio extraction failed", "stderr": stderr})
        except subprocess.TimeoutExpired:
            return h._send_json(504, {"error": "audio extraction timed out"})

    duration_ms = h._ffprobe_duration_ms(audio_path)
    return h._send_json(200, {
        "audio_url": f"http://localhost:5111/api/stitch_editor/audio_file/{audio_fname}",
        "duration_ms": duration_ms,
    })


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
        out_path, slot_durations = h._stitch_build_pipeline(body)
    except (ValueError, PermissionError) as exc:
        return h._send_json(400, {"error": str(exc)})
    except FileNotFoundError as exc:
        return h._send_json(404, {"error": str(exc)})
    except RuntimeError as exc:
        return h._send_json(500, {"error": str(exc)})

    # Strip the stitch_preview_ prefix for the URL hash segment
    hash_id = out_path.stem.replace("stitch_preview_", "")
    duration_ms = h._ffprobe_duration_ms(out_path)
    return h._send_json(200, {
        "preview_url": f"http://localhost:5111/api/stitch_editor/preview_file/{hash_id}",
        "duration_ms": duration_ms,
        "slot_durations": slot_durations,
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
        return h._send_json(423, {
            "error": "event_changed_pre_work",
            "code": "ASYNC_JOB_GENERATION_PIN_V1",
            "handler": '_handle_stitch_bake',
            "hint": (
                "Event changed between scope-guard and work start. "
                "No work was done; no orphan output. Client should "
                "re-hydrate scope and retry."
            ),
        })

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
            return h._send_json(409, {"error": "Bake already in progress"})
    except Exception as exc:
        return h._send_json(500, {"error": f"Lock setup failed: {exc}"})

    try:
        try:
            out_path, _durations = h._stitch_build_pipeline(body)
        except (ValueError, PermissionError) as exc:
            return h._send_json(400, {"error": str(exc)})
        except FileNotFoundError as exc:
            return h._send_json(404, {"error": str(exc)})
        except RuntimeError as exc:
            return h._send_json(500, {"error": str(exc)})

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
            return h._send_json(422, {
                "error": f"Video bitrate {bitrate:,} bps exceeds 1,900,000 bps (SIZE_BUDGET_VIDEO_V1)",
                "actual_bps": bitrate,
            })

        # SIZE_BUDGET_PER_MODULE_V1: ≤ 80 MB
        file_size = out_path.stat().st_size
        size_mb = file_size / (1024 * 1024)
        if size_mb > 80.0:
            out_path.unlink(missing_ok=True)
            return h._send_json(422, {
                "error": f"Output {size_mb:.1f} MB exceeds 80 MB ceiling (SIZE_BUDGET_PER_MODULE_V1)",
                "actual_bytes": file_size,
            })

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
            sys.path.insert(0, str(_PSERVER_PRODUCTION_DIR))
            from registered_write import register_asset  # noqa: PLC0415
            slots = body.get("slots") or []
            iter_notes = (
                f"Stitch editor bake. Job: {job_name}. "
                f"{len(slots)} slot(s), {sum(len(s.get('sfx_cues') or []) for s in slots)} SFX cues."
            )
            # module_id resolved via state.event_id -> prod_modules per
            # LD MODULE_ID_DYNAMIC_RESOLUTION_V1; closes the Rule 19
            # "module_id=1 sentinel" stub class.
            # LD-460 — terminal pin check before final asset register.
            if not h._check_event_pin(_pin, "stitch_bake_register_asset"):
                return h._send_json(423, {"error": "event_changed_mid_job", "code": "ASYNC_JOB_GENERATION_PIN_V1", "orphaned_bake_path": str(bake_path)})
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


