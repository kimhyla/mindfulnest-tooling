"""Timeline + SFX handlers — V59 Phase 4 Pass 2.

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

# Project-internal modules imported the same way production_server.py does.
# Handler bodies may reference any of these by bare name.
from lib.atomic_json_write import atomic_json_write
from lib.v3_partition import _iter_v3_beats
import scope_router
from server_handlers._path_security import (
    MEDIA_EXTENSIONS,
    require_media_under_project,
    require_realpath_under_project,
)
from ffmpeg_utils import strip_audio as _strip_clip_audio
from lipsync_sender import LipSyncClient, COST_PER_LIPSYNC

def handle_timeline_audio(h, event_id: str)-> None:

    """GET /api/timeline/audio/<event_id>

    Extract audio from FULL MODULE (Story Scene + Phase A + Phase B).
    Replaces intro-only stitch with real 3-segment assembly. Spec B.
    Returns JSON: {audio_url, duration_ms, segment_boundaries}.
    SIZE_BUDGET_AUDIO_V1: AAC 128kbps mono 44.1kHz.
    """
    import hashlib as _hl  # noqa: PLC0415
    try:
        full_mp4, segment_boundaries = h._get_or_build_full_module_mp4()
    except FileNotFoundError as e:
        return h._send_error_v59(
                   404,
                   error_code="GENERIC_ERROR",
                   error_message=str(e),
                   retry_safe=False,
                   extra={"hint": "Click 'Preview-Stitched v2' to build the Story Scene preview first."},
               )
    except Exception as e:
        return h._send_error_v59(
                   500,
                   error_code="GENERIC_ERROR",
                   error_message=f"full module build failed: {e}",
                   retry_safe=True,
               )

    mtime_ms = int(full_mp4.stat().st_mtime * 1000)
    cache_key = _hl.md5(
        f"{full_mp4}:{mtime_ms}".encode(), usedforsecurity=False
    ).hexdigest()[:16]

    cache_dir = h.app.event_dir / "preview" / "timeline_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    audio_fname = f"timeline_audio_{cache_key}.mp3"
    audio_path = cache_dir / audio_fname

    if not audio_path.is_file():
        # nosec: CodeQL false-positive — full_mp4 from server _get_or_build_full_module_mp4
        ffmpeg_in = str(full_mp4.resolve())
        cmd = [
            "ffmpeg", "-y", "-i", ffmpeg_in,
            "-vn", "-ac", "1", "-ar", "44100", "-b:a", "128k",
            str(audio_path),
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

    # Total duration
    try:
        dp = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "json", str(audio_path)],
            capture_output=True, timeout=10, check=True,
        )
        total_ms = int(float(json.loads(dp.stdout)["format"]["duration"]) * 1000)
    except Exception:
        total_ms = 0

    return h._send_json(200, {
        "audio_url": f"/api/media/{audio_fname}",
        "duration_ms": total_ms,
        "segment_boundaries": segment_boundaries,
    })


def handle_timeline_sfx_library(h)-> None:

    """GET /api/timeline/sfx_library

    Scan SFX and ambient dirs; return [{filename, path, duration_ms, category}].
    """
    results: list[dict] = []
    scan_dirs: list[tuple[Path, str]] = [
        (h.app.event_dir / "sfx", "sfx"),
        (h.app.event_dir.parent.parent / "assets" / "ambient_library", "ambient"),
    ]

    for scan_dir, category in scan_dirs:
        if not scan_dir.is_dir():
            continue
        for pat in ("*.mp3", "*.wav", "*.m4a"):
            for f in sorted(scan_dir.glob(pat)):
                duration_ms = h._ffprobe_duration_ms(f)
                results.append({
                    "filename": f.name,
                    "path": str(f),
                    "duration_ms": duration_ms,
                    "category": category,
                })

    # Project-root canonical SFX
    project_root = h.app.event_dir.parent.parent
    canonical_sfx = ["magic burst sound for in video.mp3"]
    for fname in canonical_sfx:
        fp = project_root / fname
        if fp.is_file() and not any(r["filename"] == fname for r in results):
            results.append({
                "filename": fname,
                "path": str(fp),
                "duration_ms": h._ffprobe_duration_ms(fp),
                "category": "sfx",
            })

    return h._send_json(200, results)


def handle_timeline_cue_upsert(h, body: dict)-> None:

    """POST /api/timeline/cues — upsert cue by id; atomic write via mutate_state."""
    # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return

    cue_id = body.get("id")
    if not cue_id:
        return h._send_error_v59(
                   400,
                   error_code="MISSING_CUE_ID",
                   error_message="cue id is required",
                   retry_safe=False,
               )

    cue_type = body.get("cue_type", "sfx")
    if cue_type not in ("sfx", "ambient_segment"):
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=f"invalid cue_type: {cue_type!r}",
                   retry_safe=False,
                   extra={"hint": "Must be 'sfx' or 'ambient_segment'"},
               )

    source_path_str = body.get("source_path", "")
    if not source_path_str:
        return h._send_error_v59(
                   400,
                   error_code="MISSING_SOURCE_PATH",
                   error_message="source_path is required",
                   retry_safe=False,
               )
    try:
        real_path = require_media_under_project(source_path_str, extensions=MEDIA_EXTENSIONS)
    except ValueError as exc:
        return h._send_error_v59(
                   403,
                   error_code="GENERIC_ERROR",
                   error_message=str(exc),
                   retry_safe=False,
               )
    except FileNotFoundError:
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=f"source_path not found: {source_path_str}",
                   retry_safe=False,
                   extra={"hint": "Ensure the SFX file exists at the given path."},
               )
    source_path = Path(real_path)

    cue = {
        "id": cue_id,
        "cue_type": cue_type,
        "source_path": str(source_path),
        "offset_ms": int(body.get("offset_ms", 0)),
        "end_ms": body.get("end_ms"),
        "volume": float(body.get("volume", 0.45)),
        "fadein_ms": int(body.get("fadein_ms", 300)),
        "fadeout_ms": int(body.get("fadeout_ms", 1200)),
    }

    def _upsert(state: dict) -> dict:
        cues = state.get("module_sfx_cues", [])
        idx = next((i for i, c in enumerate(cues) if c.get("id") == cue_id), None)
        if idx is not None:
            cues[idx] = cue
        else:
            cues.append(cue)
        state["module_sfx_cues"] = cues
        return state

    h.app.state.mutate_state(_upsert)
    return h._send_json(200, {"ok": True, "cue": cue})


def handle_timeline_delete_cue(h, cue_id: str)-> None:

    """DELETE /api/timeline/cues/<id> — atomic remove via mutate_state."""
    # LD-456 SCOPE_VALIDATION_V1 (no-body handler — query-string fallback inside helper)
    if not h._assert_event_scope({}, allow_missing=True):
        return

    if not cue_id:
        return h._send_error_v59(
                   400,
                   error_code="MISSING_CUE_ID",
                   error_message="cue id required in path",
                   retry_safe=False,
               )

    removed: list[bool] = [False]

    def _remove(state: dict) -> dict:
        cues = state.get("module_sfx_cues", [])
        new_cues = [c for c in cues if c.get("id") != cue_id]
        removed[0] = len(new_cues) < len(cues)
        state["module_sfx_cues"] = new_cues
        return state

    h.app.state.mutate_state(_remove)
    if not removed[0]:
        return h._send_error_v59(
                   404,
                   error_code="GENERIC_ERROR",
                   error_message=f"cue not found: {cue_id}",
                   retry_safe=False,
               )
    return h._send_json(200, {"ok": True, "deleted": cue_id})


def handle_timeline_bake(h, body: dict)-> None:

    """POST /api/timeline/cues/bake — confirm cues are committed to production_state."""
    state = h.app.state.read_state()
    cues = state.get("module_sfx_cues", [])
    return h._send_json(200, {"ok": True, "baked": len(cues), "cues": cues})


def handle_timeline_open_in_quicktime(h, body: dict)-> None:

    """POST /api/timeline/open_in_quicktime — open mp4_path in QuickTime Player.

    Security (CodeQL py/path-injection alert #29 follow-up):
    Extension whitelist alone leaves any readable .mp4/.mov/.m4v on disk
    openable. macOS media-decoder CVEs make this a non-zero risk surface.
    Add project-root containment so only files inside the repo open.
    """
    mp4_path = body.get("mp4_path", "")
    if not mp4_path:
        return h._send_error_v59(
                   400,
                   error_code="MISSING_MP4_PATH",
                   error_message="mp4_path is required",
                   retry_safe=False,
               )
    try:
        real_path = require_media_under_project(
            mp4_path,
            extensions=frozenset({".mp4", ".mov", ".m4v"}),
        )
    except ValueError as exc:
        return h._send_error_v59(
                   403,
                   error_code="GENERIC_ERROR",
                   error_message=str(exc),
                   retry_safe=False,
               )
    except FileNotFoundError:
        return h._send_error_v59(
                   404,
                   error_code="GENERIC_ERROR",
                   error_message=f"file not found: {mp4_path}",
                   retry_safe=False,
               )
    p = Path(real_path)
    try:
        subprocess.run(
            ["open", "-a", "QuickTime Player", real_path],
            check=True, timeout=10,
        )
    except subprocess.CalledProcessError as exc:
        return h._send_error_v59(
                   500,
                   error_code="GENERIC_ERROR",
                   error_message=f"open failed: {exc}",
                   retry_safe=True,
               )
    return h._send_json(200, {"ok": True, "opened": str(p)})


def handle_timeline_preview_with_sfx(h, body: dict)-> None:

    """POST /api/timeline/preview_with_sfx

    Mix module_sfx_cues into stitched preview. Fast-path stream-copy when 0 cues.
    Post-render: ffprobe bitrate ≤1,900,000 bps + file ≤80MB (SIZE_BUDGET_VIDEO_V1
    + SIZE_BUDGET_PER_MODULE_V1). Returns {mp4_path} on success.
    """
    # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return

    # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — capture pin at entry; terminal writes assert via _check_event_pin.
    _pin = {
        "pinned_generation": h.app.event_generation,
        "pinned_event_dir": h.app.event_dir,
        "pinned_video_role": (body or {}).get("scope_video_role", "intro"),
        "_handler": '_handle_timeline_preview_with_sfx',
    }
    # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — pre-work pin check (S2).
    # If the event was swapped via /api/event/load between scope-guard
    # and work start, abort BEFORE any expensive work begins.
    if not h._check_event_pin(_pin, '_handle_timeline_preview_with_sfx_pre_work'):
        return h._send_error_v59(
                   423,
                   error_code="EVENT_CHANGED_PRE_WORK",
                   error_message="event_changed_pre_work",
                   retry_safe=False,
                   extra={"code": "ASYNC_JOB_GENERATION_PIN_V1", "handler": '_handle_timeline_preview_with_sfx', "hint": "Event changed between scope-guard and work start. "
                "No work was done; no orphan output. Client should "
                "re-hydrate scope and retry."},
               )

    import hashlib as _hl  # noqa: PLC0415

    try:
        preview_mp4, _seg_bounds = h._get_or_build_full_module_mp4()
    except FileNotFoundError as e:
        return h._send_error_v59(
                   404,
                   error_code="GENERIC_ERROR",
                   error_message=str(e),
                   retry_safe=False,
                   extra={"hint": "Click 'Preview-Stitched v2' to build the Story Scene preview first."},
               )
    except Exception as e:
        return h._send_error_v59(
                   500,
                   error_code="GENERIC_ERROR",
                   error_message=f"full module build failed: {e}",
                   retry_safe=True,
               )

    state = h.app.state.read_state()
    cues = state.get("module_sfx_cues", [])

    exports_dir = h.app.event_dir / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)

    # Fast-path: 0 cues -> stream-copy unchanged (no filter_complex needed)
    if not cues:
        nc_hash = _hl.md5(b"no_cues", usedforsecurity=False).hexdigest()[:8]
        out_fname = f"timeline_preview_sfx_{nc_hash}.mp4"
        out_path = exports_dir / out_fname
        if not out_path.is_file():
            # nosec: CodeQL false-positive — preview_mp4 from server _get_or_build_full_module_mp4
            cmd = [
                "ffmpeg", "-y",
                "-i", str(preview_mp4.resolve()),
                "-c", "copy",
                str(out_path.resolve()),
            ]
            try:
                subprocess.run(cmd, check=True, capture_output=True, timeout=60)
            except subprocess.CalledProcessError as exc:
                stderr = (exc.stderr or b"")[:400].decode("utf-8", errors="replace")
                return h._send_error_v59(
                           500,
                           error_code="STREAM_COPY_FAILED",
                           error_message="stream-copy failed",
                           retry_safe=True,
                           extra={"stderr": stderr},
                       )
        return h._send_json(200, {"mp4_path": str(out_path)})

    # Validate all cue source paths (stored from body) before ffmpeg argv.
    sanitized_cues: list[dict] = []
    for cue in cues:
        sp_raw = cue.get("source_path", "")
        if not sp_raw:
            return h._send_error_v59(
                       400,
                       error_code="CUE_MISSING_SOURCE_PATH",
                       error_message="cue missing source_path",
                       retry_safe=False,
                       extra={"hint": "Remove or update the invalid cue before previewing."},
                   )
        try:
            sp_safe = require_media_under_project(sp_raw, extensions=MEDIA_EXTENSIONS)
        except ValueError as exc:
            return h._send_error_v59(
                       403,
                       error_code="GENERIC_ERROR",
                       error_message=str(exc),
                       retry_safe=False,
                       extra={"cue_id": cue.get("id")},
                   )
        except FileNotFoundError:
            return h._send_error_v59(
                       400,
                       error_code="GENERIC_ERROR",
                       error_message=f"SFX file not found: {sp_raw}",
                       retry_safe=False,
                       extra={"hint": "Remove or update the missing cue before previewing."},
                   )
        cue = dict(cue)
        cue["source_path"] = sp_safe
        sanitized_cues.append(cue)
    cues = sanitized_cues

    # Build filter_complex — pattern from LESSONS_LEARNED_April25 §14 verbatim.
    # Each cue lane: aresample=44100 (LD-284), adelay, afade in/out, volume.
    input_args: list[str] = ["-i", str(preview_mp4)]
    filter_lanes: list[str] = []
    mix_inputs: list[str] = ["[0:a]"]

    for idx, cue in enumerate(cues):
        input_args += ["-i", cue["source_path"]]
        stream_idx = idx + 1
        offset_ms = int(cue["offset_ms"])
        fadein_ms = int(cue["fadein_ms"])
        fadeout_ms = int(cue["fadeout_ms"])
        volume = float(cue["volume"])
        cue_dur_ms = h._ffprobe_duration_ms(Path(cue["source_path"]))
        cue_dur_s = cue_dur_ms / 1000.0 if cue_dur_ms else 5.0
        fadeout_start_s = max(0.0, cue_dur_s - fadeout_ms / 1000.0)

        lane = (
            f"[{stream_idx}:a]aresample=44100,"
            f"adelay={offset_ms}|{offset_ms},"
            f"afade=t=in:st=0:d={fadein_ms / 1000:.3f},"
            f"afade=t=out:st={fadeout_start_s:.3f}:d={fadeout_ms / 1000:.3f},"
            f"volume={volume:.3f}[cue{idx}]"
        )
        filter_lanes.append(lane)
        mix_inputs.append(f"[cue{idx}]")

    n_inputs = len(mix_inputs)
    filter_lanes.append(
        f"{''.join(mix_inputs)}amix=inputs={n_inputs}:duration=first:normalize=0[aout]"
    )
    filter_complex = ";".join(filter_lanes)

    # Hash output path from preview mtime + cue ids
    cues_sig = json.dumps([c["id"] for c in cues], sort_keys=True).encode()
    out_hash = _hl.md5(
        f"{preview_mp4}{int(preview_mp4.stat().st_mtime)}".encode() + cues_sig,
        usedforsecurity=False,
    ).hexdigest()[:16]
    out_path = exports_dir / f"timeline_preview_sfx_{out_hash}.mp4"

    cmd = (
        ["ffmpeg", "-y"]
        + input_args
        + [
            "-filter_complex", filter_complex,
            "-map", "0:v",
            "-map", "[aout]",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "128k", "-ac", "1", "-ar", "44100",
            str(out_path),
        ]
    )

    # LD-460 — terminal pin check before ffmpeg write of preview mp4.
    if not h._check_event_pin(_pin, "timeline_preview_sfx_ffmpeg_write"):
        return h._send_error_v59(
                   423,
                   error_code="EVENT_CHANGED_MID_JOB",
                   error_message="event_changed_mid_job",
                   retry_safe=False,
                   extra={"code": "ASYNC_JOB_GENERATION_PIN_V1"},
               )
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=300)
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or b"")[:600].decode("utf-8", errors="replace")
        return h._send_error_v59(
                   500,
                   error_code="FFMPEG_SFX_MIX_FAILED",
                   error_message="ffmpeg SFX mix failed",
                   retry_safe=True,
                   extra={"stderr": stderr, "cmd_head": " ".join(cmd[:10])},
               )
    except subprocess.TimeoutExpired:
        return h._send_error_v59(
                   504,
                   error_code="FFMPEG_SFX_MIX_TIMED_OUT",
                   error_message="ffmpeg SFX mix timed out",
                   retry_safe=True,
               )

    # Post-render validation — SIZE_BUDGET_VIDEO_V1 + SIZE_BUDGET_PER_MODULE_V1
    try:
        vp = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "stream=bit_rate",
             "-select_streams", "v:0", "-of", "json", str(out_path)],
            capture_output=True, timeout=10, check=True,
        )
        streams = json.loads(vp.stdout).get("streams", [])
        video_bitrate = int(streams[0].get("bit_rate", 0)) if streams else 0
    except Exception:
        video_bitrate = 0

    file_size_bytes = out_path.stat().st_size
    size_mb = file_size_bytes / (1024 * 1024)

    if video_bitrate > 1_900_000:
        out_path.unlink(missing_ok=True)
        return h._send_error_v59(
                   422,
                   error_code="GENERIC_ERROR",
                   error_message=f"video bitrate {video_bitrate:,} bps exceeds 1,900,000 bps "
                "ceiling (SIZE_BUDGET_VIDEO_V1). Do not open in QuickTime.",
                   retry_safe=False,
                   extra={"hint": "Source clips may need re-normalization."},
               )

    if size_mb > 80.0:
        out_path.unlink(missing_ok=True)
        return h._send_error_v59(
                   422,
                   error_code="GENERIC_ERROR",
                   error_message=f"output {size_mb:.1f} MB exceeds 80 MB ceiling "
                "(SIZE_BUDGET_PER_MODULE_V1). Do not open in QuickTime.",
                   retry_safe=False,
                   extra={"hint": "Reduce SFX count or compress source clips."},
               )

    return h._send_json(200, {"mp4_path": str(out_path)})


