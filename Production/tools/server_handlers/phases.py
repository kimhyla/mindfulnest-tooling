"""Phase A/B handlers — V59 Phase 4 Pass 2.

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
# deeper than production_server.py. _PSERVER_TOOLS_DIR is for CODE-tree
# lookups (sibling Python modules + sys.path inserts). It is NOT used for
# data paths — those come from the runtime event_dir via _data_root(h).
_PSERVER_TOOLS_DIR = Path(__file__).resolve().parent.parent  # Production/tools/


def _data_root(h) -> Path:
    """Runtime ``Production/`` root, anchored on the running server's event_dir."""
    return Path(h.app.event_dir).resolve().parent


# Project-internal modules imported the same way production_server.py does.
# Handler bodies may reference any of these by bare name.
from lib.atomic_json_write import atomic_json_write
from lib.v3_partition import _iter_v3_beats
from lib.event_library import event_watercolors_dir
from lib.watercolor_assets import list_watercolor_items, resolve_watercolor_path
from lib.paths import DROPBOX_ROOT
import scope_router
from ffmpeg_utils import strip_audio as _strip_clip_audio
from lipsync_sender import LipSyncClient, COST_PER_LIPSYNC
from server_handlers._path_security import (
    MEDIA_EXTENSIONS,
    require_basename_under_dir,
    require_media_under_project,
)

# Late-resolvable private helpers from the host module.
from tools.production_server import (  # noqa: E402
    _bg_module,
    _ffprobe_duration,
    _resolve_module_for_event,
    _silcomp_audio,
    _trim_video_to_audio,
    _v2_validate_watercolor_cues_json,
    parse_api_keys,
)

# ---------------------------------------------------------------------------
# White-out fade — standardized Phase B ending transition
# ---------------------------------------------------------------------------
# Locked: Phase B ending transition is handled at stitch module boundaries
# (expand_clips_with_black_pause_boundaries) — NOT baked into lipsync MP4s.
# In-clip whiteout duplicated the intro bug class (fade eating tail dialogue).
PHASE_B_WHITEOUT_ENABLED: bool = False
PHASE_B_WHITEOUT_DURATION_SEC: float = 0.6  # unused when PHASE_B_WHITEOUT_ENABLED=False
# Intro export uses fade_audio=False — dialogue stays full level until hard cut.
# Phase B whiteout matches that: video fades to white; audio untouched until file end.
PHASE_B_WHITEOUT_FADE_AUDIO: bool = False
# Kling LipSync on ~43s stems: p99 ~15 min; auto-clear stuck "running" after 20 min.
PHASE_A_LIPSYNC_STALE_SEC: int = 1200
# Dead worker + no tmp progress after restart — clear so UI can resubmit.
PHASE_A_LIPSYNC_RESTART_ORPHAN_SEC: int = 300

_phase_a_lipsync_worker: threading.Thread | None = None
_phase_a_lipsync_worker_lock = threading.Lock()

# Cleared on reject/regen so lipsync/mix/stitch no longer reference stale outputs.
_PHASE_LIPSYNC_DERIVED_KEYS = (
    "lipsync_file",
    "lipsync_mtime",
    "lipsync_status",
    "lipsync_method",
    "lipsync_qa_dir",
    "lipsync_av_gap_s",
    "lipsync_reliability_note",
    "lipsync_task_id",
    "lipsync_started_at",
    "lipsync_pending_out",
    "mixed_audio_file",
    "mixed_audio_mtime",
    "stitched_file",
    "stitched_mtime",
)
_PHASE_VOICE_STEM_CUT_KEYS = (
    "voice_stem_cut_start_s",
    "voice_stem_cut_end_s",
)
# Legacy keep-region keys (pre-2026-06-12 invert); cleared on write.
_PHASE_VOICE_STEM_TRIM_KEYS_LEGACY = (
    "voice_stem_trim_start_s",
    "voice_stem_trim_back_s",
)


def _phase_voice_stem_cut_window(state: dict, phase: str) -> tuple[float, float]:
    """Return (cut_start_s, cut_end_s) — absolute times of the region TO REMOVE."""
    start = float(state.get(f"phase_{phase}_voice_stem_cut_start_s") or 0.0)
    end = float(state.get(f"phase_{phase}_voice_stem_cut_end_s") or 0.0)
    return max(0.0, start), max(0.0, end)


def _phase_voice_stem_trim_window(state: dict, phase: str) -> tuple[float, float]:
    """Deprecated alias — use _phase_voice_stem_cut_window."""
    return _phase_voice_stem_cut_window(state, phase)


def _materialize_cut_out_audio(
    source: Path,
    dst: Path,
    cut_start_s: float,
    cut_end_s: float,
) -> Path:
    """Remove [cut_start_s, cut_end_s) from *source*; write kept audio to *dst*."""
    if cut_end_s <= cut_start_s + 0.001:
        raise ValueError(
            f"cut region empty or inverted: start={cut_start_s:.3f}s end={cut_end_s:.3f}s",
        )
    dur = _ffprobe_duration(source)
    if cut_end_s - cut_start_s >= dur - 0.001:
        raise ValueError(
            f"cut region covers entire file ({cut_end_s - cut_start_s:.2f}s of {dur:.2f}s)",
        )

    kept = (cut_start_s - 0.0) + max(0.0, dur - cut_end_s)
    if kept < 0.25:
        raise ValueError(
            f"kept audio too small ({kept:.2f}s after removing "
            f"[{cut_start_s:.2f}s, {cut_end_s:.2f}s] from {dur:.2f}s)",
        )

    # Single-segment keeps (head or tail removal).
    if cut_start_s <= 0.001:
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-ss", f"{cut_end_s:.3f}",
                "-i", str(source),
                "-c:a", "libmp3lame", "-q:a", "2",
                str(dst),
            ],
            check=True,
            capture_output=True,
            timeout=120,
        )
        return dst

    if cut_end_s >= dur - 0.001:
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-t", f"{cut_start_s:.3f}",
                "-i", str(source),
                "-c:a", "libmp3lame", "-q:a", "2",
                str(dst),
            ],
            check=True,
            capture_output=True,
            timeout=120,
        )
        return dst

    # Middle removal — concat [0, cut_start) + [cut_end, dur).
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(source),
            "-filter_complex",
            (
                f"[0:a]atrim=0:{cut_start_s:.3f},asetpts=PTS-STARTPTS[a1];"
                f"[0:a]atrim={cut_end_s:.3f}:{dur:.3f},asetpts=PTS-STARTPTS[a2];"
                f"[a1][a2]concat=n=2:v=0:a=1[out]"
            ),
            "-map", "[out]",
            "-c:a", "libmp3lame", "-q:a", "2",
            str(dst),
        ],
        check=True,
        capture_output=True,
        timeout=120,
    )
    return dst


def _materialize_trimmed_audio(
    source: Path,
    dst: Path,
    trim_start_s: float,
    trim_back_s: float,
) -> Path:
    """Legacy keep-region trim — maps to cut-out of complement bands."""
    if trim_start_s <= 0.001 and trim_back_s <= 0.001:
        return source
    dur = _ffprobe_duration(source)
    cut_start = trim_start_s
    cut_end = dur - trim_back_s if trim_back_s > 0.001 else dur
    return _materialize_cut_out_audio(source, dst, cut_start, cut_end)


def _phase_clear_stem_cut_keys(state: dict, phase: str) -> None:
    for suffix in _PHASE_VOICE_STEM_CUT_KEYS + _PHASE_VOICE_STEM_TRIM_KEYS_LEGACY:
        state.pop(f"phase_{phase}_{suffix}", None)


def _phase_clear_lipsync_derived(state: dict, phase: str, *, requires_regen: bool) -> None:
    for suffix in _PHASE_LIPSYNC_DERIVED_KEYS:
        state.pop(f"phase_{phase}_{suffix}", None)
        nested = state.get(f"phase_{phase}")
        if isinstance(nested, dict):
            nested.pop(f"phase_{phase}_{suffix}", None)
    state[f"phase_{phase}_lipsync_requires_regen"] = requires_regen
    nested = state.setdefault(f"phase_{phase}", {})
    if isinstance(nested, dict):
        nested[f"phase_{phase}_lipsync_requires_regen"] = requires_regen


# ---------------------------------------------------------------------------
# Voice stem pin durability (PHASE_VOICE_STEM_PIN_DURABILITY_V1)
# ---------------------------------------------------------------------------
# Incident 2026-06-13: lipsync baked June 6 "I don't know." while June 13 regen
# existed on disk — stale production_state pin + no preflight before lipsync.

PHASE_VOICE_STEM_PIN_DURABILITY_V1 = "PHASE_VOICE_STEM_PIN_DURABILITY_V1"


def _phase_nested_block(state: dict, phase: str) -> dict:
    nested = state.get(f"phase_{phase}")
    return nested if isinstance(nested, dict) else {}


def _phase_resolve_voice_stem_name(state: dict, phase: str) -> str:
    """Canonical stem filename — top-level wins over nested mirror."""
    top = (state.get(f"phase_{phase}_voice_stem_file") or "").strip()
    if top:
        return top
    nested = _phase_nested_block(state, phase)
    return (nested.get(f"phase_{phase}_voice_stem_file") or "").strip()


def _phase_resolve_voice_stem_mtime(state: dict, phase: str) -> int | None:
    top = state.get(f"phase_{phase}_voice_stem_mtime")
    if isinstance(top, (int, float)):
        return int(top)
    nested = _phase_nested_block(state, phase)
    nested_m = nested.get(f"phase_{phase}_voice_stem_mtime")
    if isinstance(nested_m, (int, float)):
        return int(nested_m)
    return None


def _phase_set_voice_stem_keys(state: dict, phase: str, filename: str, mtime: int) -> None:
    """Write voice stem pin to top-level AND nested phase block (mirror parity)."""
    state[f"phase_{phase}_voice_stem_file"] = filename
    state[f"phase_{phase}_voice_stem_mtime"] = mtime
    nested = state.setdefault(f"phase_{phase}", {})
    if isinstance(nested, dict):
        nested[f"phase_{phase}_voice_stem_file"] = filename
        nested[f"phase_{phase}_voice_stem_mtime"] = mtime


def _phase_voice_stem_mirror_drift(state: dict, phase: str) -> str | None:
    top = (state.get(f"phase_{phase}_voice_stem_file") or "").strip()
    nested_name = (_phase_nested_block(state, phase).get(f"phase_{phase}_voice_stem_file") or "").strip()
    if top and nested_name and top != nested_name:
        return nested_name
    return None


def _phase_list_newer_voice_stems_on_disk(
    event_dir: Path, phase: str, pinned_name: str,
) -> list[str]:
    """Orphan stems newer than the pinned file (mtime), excluding pinned."""
    pinned_path = event_dir / pinned_name
    pinned_mtime = pinned_path.stat().st_mtime if pinned_path.is_file() else 0.0
    newer: list[tuple[float, str]] = []
    for p in event_dir.glob(f"phase_{phase}_voice_stem_*.mp3"):
        if p.name == pinned_name:
            continue
        try:
            mt = p.stat().st_mtime
        except OSError:
            continue
        if mt > pinned_mtime + 0.5:
            newer.append((mt, p.name))
    newer.sort(reverse=True)
    return [name for _, name in newer]


def _phase_lipsync_sidecar_audio_source(event_dir: Path, lipsync_name: str) -> str:
    sidecar = event_dir / Path(lipsync_name).with_suffix(".json")
    if not sidecar.is_file():
        return ""
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    src = data.get("audio_source")
    return src if isinstance(src, str) else ""


def _phase_voice_stem_pin_issues(
    h,
    state: dict,
    phase: str,
    *,
    for_lipsync: bool = False,
) -> list[dict]:
    issues: list[dict] = []
    pinned = _phase_resolve_voice_stem_name(state, phase)
    if not pinned:
        issues.append({"code": "STEM_UNSET", "message": f"phase_{phase}_voice_stem_file unset"})
        return issues

    mirror_other = _phase_voice_stem_mirror_drift(state, phase)
    if mirror_other:
        issues.append({
            "code": "STEM_MIRROR_DRIFT",
            "message": f"top-level pin {pinned!r} != nested {mirror_other!r}",
            "pinned": pinned,
            "nested": mirror_other,
        })

    stem_path = h.app.event_dir / pinned
    if not stem_path.is_file():
        issues.append({
            "code": "STEM_MISSING",
            "message": f"pinned stem missing on disk: {pinned}",
            "pinned": pinned,
        })
        return issues

    pinned_mtime_state = _phase_resolve_voice_stem_mtime(state, phase)
    if pinned_mtime_state is not None:
        disk_mtime = int(stem_path.stat().st_mtime)
        if abs(disk_mtime - pinned_mtime_state) > 2:
            issues.append({
                "code": "STEM_MTIME_DRIFT",
                "message": f"state mtime {pinned_mtime_state} != disk {disk_mtime} for {pinned}",
                "pinned": pinned,
            })

    newer = _phase_list_newer_voice_stems_on_disk(h.app.event_dir, phase, pinned)
    if newer:
        issues.append({
            "code": "STEM_PIN_STALE",
            "message": f"newer voice stem(s) on disk than pin {pinned}",
            "pinned": pinned,
            "newer_stems": newer,
        })

    if for_lipsync:
        lipsync_name = (state.get(f"phase_{phase}_lipsync_file") or "").strip()
        if lipsync_name and not state.get(f"phase_{phase}_lipsync_requires_regen"):
            sidecar_src = _phase_lipsync_sidecar_audio_source(h.app.event_dir, lipsync_name)
            sidecar_base = Path(sidecar_src).name if sidecar_src else ""
            if sidecar_base and sidecar_base != pinned:
                issues.append({
                    "code": "LIPSYNC_AUDIO_LINEAGE_STALE",
                    "message": (
                        f"lipsync {lipsync_name} built from {sidecar_base}, "
                        f"pin is {pinned}"
                    ),
                    "lipsync_file": lipsync_name,
                    "audio_source": sidecar_base,
                    "pinned": pinned,
                })

    return issues


def _phase_repair_voice_stem_mirror(h, phase: str) -> None:
    """Sync nested mirror to top-level canonical pin."""

    def _repair(st):
        pinned = (st.get(f"phase_{phase}_voice_stem_file") or "").strip()
        if not pinned:
            return st.get("_module_version", 0)
        mtime = st.get(f"phase_{phase}_voice_stem_mtime")
        nested = st.setdefault(f"phase_{phase}", {})
        if isinstance(nested, dict):
            nested[f"phase_{phase}_voice_stem_file"] = pinned
            if mtime is not None:
                nested[f"phase_{phase}_voice_stem_mtime"] = mtime
        return st.get("_module_version", 0)

    h.app.state.mutate_state(_repair)


def _phase_preflight_voice_stem_for_lipsync(h, state: dict, phase: str):
    """Return None on success, or a V59 error response tuple from _send_error_v59."""
    if _phase_voice_stem_mirror_drift(state, phase):
        _phase_repair_voice_stem_mirror(h, phase)
        state = h.app.state.read_state()

    issues = _phase_voice_stem_pin_issues(h, state, phase, for_lipsync=True)
    blocking_codes = {"STEM_UNSET", "STEM_MISSING", "STEM_PIN_STALE"}
    blocking = [i for i in issues if i["code"] in blocking_codes]
    if not blocking:
        return None

    first = blocking[0]
    code_map = {
        "STEM_PIN_STALE": "PHASE_VOICE_STEM_PIN_STALE",
        "STEM_MISSING": "PHASE_VOICE_STEM_MISSING",
        "STEM_UNSET": "GENERIC_ERROR",
    }
    return h._send_error_v59(
        409,
        error_code=code_map.get(first["code"], "PHASE_VOICE_STEM_PIN_STALE"),
        error_message=first["message"],
        retry_safe=False,
        extra={
            "code": PHASE_VOICE_STEM_PIN_DURABILITY_V1,
            "issues": issues,
            "hint": (
                "Regen Audio to repin the current script delivery before "
                "Send for Lipsync. Do not manually swap to an older stem file."
            ),
        },
    )


def _phase_assert_voice_stem_pin_persisted(h, phase: str, expected_name: str):
    """Return V59 error response if mutate_state did not persist the new stem pin."""
    actual = _phase_resolve_voice_stem_name(h.app.state.read_state(), phase)
    if actual == expected_name:
        return None
    return h._send_error_v59(
        500,
        error_code="PHASE_VOICE_STEM_PIN_PERSIST_FAILED",
        error_message=(
            f"voice stem written to disk as {expected_name} but state pin is {actual!r}"
        ),
        retry_safe=True,
        extra={
            "code": PHASE_VOICE_STEM_PIN_DURABILITY_V1,
            "expected": expected_name,
            "actual": actual,
            "hint": "Retry Regen Audio; if it persists, check production_state.json permissions.",
        },
    )


def _apply_phase_audio_trim(
    h,
    audio_path: Path,
    phase: str,
    state: dict,
    ts: str,
) -> tuple[Path, float]:
    """Resolve lipsync/mix audio path, applying persisted stem cut when active."""
    cut_start, cut_end = _phase_voice_stem_cut_window(state, phase)
    if cut_end <= cut_start + 0.001:
        return audio_path, _ffprobe_duration(audio_path)
    tmp_trim = h.app.event_dir / f"_tmp_stem_trim_phase_{phase}_{ts}.mp3"
    trimmed = _materialize_cut_out_audio(audio_path, tmp_trim, cut_start, cut_end)
    return trimmed, _ffprobe_duration(trimmed)


def _apply_whiteout_fade(video_path: Path, fade_dur: float = PHASE_B_WHITEOUT_DURATION_SEC) -> None:
    """Optional white fade at tail of Phase B lipsync — disabled; stitch handles boundaries."""
    if not PHASE_B_WHITEOUT_ENABLED:
        return
    # Probe duration
    probe = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ],
        capture_output=True, text=True, check=True,
    )
    duration = float(probe.stdout.strip())
    fade_start = max(0.0, duration - fade_dur)

    tmp = video_path.with_suffix(".whiteout_tmp.mp4")
    cmd: list[str] = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-vf", f"fade=out:st={fade_start:.3f}:d={fade_dur:.3f}:color=white",
    ]
    if PHASE_B_WHITEOUT_FADE_AUDIO:
        cmd.extend(["-af", f"afade=out:st={fade_start:.3f}:d={fade_dur:.3f}"])
    else:
        cmd.extend(["-c:a", "copy"])
    cmd.extend([
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        str(tmp),
    ])
    subprocess.run(cmd, check=True, capture_output=True)
    tmp.rename(video_path)
    print(
        f"[phase_b_whiteout] ✓ {fade_dur}s white fade applied "
        f"(fade_start={fade_start:.2f}s, total={duration:.2f}s, "
        f"audio={'afade' if PHASE_B_WHITEOUT_FADE_AUDIO else 'copy'})",
        flush=True,
    )

def handle_phase_watercolor_list(h)-> None:

    """GET /api/phase/watercolor_list — inventory of watercolor library.

    Reads Event_N/library/watercolor/ for PNG/MOV files.
    Returns {items: [{key, filename, kind, thumb_url, mtime}]}.

    kind: 'static' for .png, 'animation' for .mov (animated via the
    Animate-this bridge — LD WATERCOLOR_ANIMATE_THIS_V1).

    Per LD PHASE_A_PRODUCER_V1 + PHASE_B_PRODUCER_V1 (replaces hardcoded
    JS array in v58).
    """
    wc_dir = event_watercolors_dir(h.app.event_dir)
    items = list_watercolor_items(wc_dir)
    return h._send_json(200, {
        "ok": True,
        "items": items,
        "count": len(items),
        "library_dir": str(wc_dir),
    })


def handle_phase_watercolor_file(h)-> None:

    """GET /api/phase/watercolor_file?key=<stem> — serve a single watercolor file.

    Helper for the watercolor_list thumb_url. Reads from the same
    directory; key is the basename without extension.
    """
    try:
        qs = urllib.parse.urlparse(h.path).query
        params = urllib.parse.parse_qs(qs)
        key_list = params.get("key")
        if not key_list:
            return h._send_error_v59(
                       400,
                       error_code="KEY_QUERY_PARAM_REQUIRED",
                       error_message="key query param required",
                       retry_safe=False,
                   )
        key = urllib.parse.unquote(key_list[0])
        wc_dir = event_watercolors_dir(h.app.event_dir)
        try:
            f = resolve_watercolor_path(wc_dir, key, prefer_animation=False)
        except FileNotFoundError:
            return h._send_error_v59(
                       404,
                       error_code="GENERIC_ERROR",
                       error_message=f"no watercolor with key={key!r}",
                       retry_safe=False,
                   )
        data = f.read_bytes()
        ext = f.suffix.lower().lstrip(".")
        ct = {
            "png": "image/png", "webp": "image/webp",
            "mov": "video/quicktime", "mp4": "video/mp4",
        }.get(ext, "application/octet-stream")
        h._send_bytes(200, data, ct,
                      extra_headers={"Cache-Control": "public, max-age=600"})
    except (OSError, KeyError) as exc:
        return h._send_error_v59(
                   500,
                   error_code="GENERIC_ERROR",
                   error_message=str(exc),
                   retry_safe=True,
               )


def handle_phase_watercolor_delete(h, body: dict) -> None:
    """POST /api/phase/watercolor_delete — delete a watercolor file from the library.

    Body: {"key": "<stem>"}   e.g. "hands_rubbing" or "hands_rubbing_animated_20260527-223413"

    Deletes every file in watercolor_library/ whose stem matches key (normally one
    file, but handles rare sidecar cases). Returns 404 when key not found.
    """
    key = (body or {}).get("key")
    if not key:
        return h._send_error_v59(
            400,
            error_code="MISSING_KEY",
            error_message="'key' is required",
            retry_safe=False,
        )
    key = urllib.parse.unquote(str(key))
    wc_dir = event_watercolors_dir(h.app.event_dir)
    matches = [
        m for m in wc_dir.glob(f"{key}.*")
        if m.is_file() and m.suffix.lower() in (".png", ".webp", ".mov", ".mp4")
    ]
    if not matches:
        try:
            matches = [resolve_watercolor_path(wc_dir, key)]
        except FileNotFoundError:
            return h._send_error_v59(
                404,
                error_code="NOT_FOUND",
                error_message=f"no watercolor with key={key!r}",
                retry_safe=False,
            )
    for f in matches:
        f.unlink()
    return h._send_json(200, {"status": "deleted", "key": key, "count": len(matches)})


def handle_phase_base_clips_list(h)-> None:

    """GET /api/phase/base_clips_list — inventory of lipsync base clips.

    Reads Production/assets/lipsync_bases/. Returns {items: [{id,
    filename, character, duration_s?}]}. Backups (.bak*) excluded.

    Per LDs PHASE_A_PRODUCER_V1 + PHASE_B_PRODUCER_V1.
    """
    bases_dir = _data_root(h) / "assets" / "lipsync_bases"
    items: list[dict] = []
    if bases_dir.is_dir():
        for f in sorted(bases_dir.iterdir(), key=lambda p: p.name):
            if not f.is_file():
                continue
            if ".bak" in f.name:
                continue
            ext = f.suffix.lower().lstrip(".")
            if ext not in ("mp4", "mov"):
                continue
            # Character is heuristic: "arlo", "chipper", or "cedric" in filename.
            lname = f.name.lower()
            character = (
                "arlo" if "arlo" in lname
                else "chipper" if "chipper" in lname
                else "cedric" if "cedric" in lname
                else None
            )
            # Duration: best-effort via ffprobe if available, else skip.
            duration_s: float | None = None
            try:
                duration_s = _ffprobe_duration(f)
            except Exception:
                duration_s = None
            items.append({
                "id": f.stem,
                "filename": f.name,
                "ext": ext,
                "character": character,
                "duration_s": round(duration_s, 3) if duration_s else None,
            })
    return h._send_json(200, {"ok": True, "items": items, "count": len(items)})


def handle_phase_b_ambient_preset_list(h)-> None:

    """GET /api/phase_b/ambient_preset_list — list ambient bed presets.

    Returns {ok, items: [{preset_id, file_size_bytes}], count}. Empty
    list (count=0) is a valid result — the producer UI surfaces a
    "no presets available" hint when the list is empty.

    Per LD AMBIENT_PRESET_SELECTOR_INPRODUCER_V1 (S5.5f spec §3.7).

    F-AMBIENT-001 (prod_blockers id=118) fix: directory was previously
    `Production/audio_library/ambient/` which does NOT exist on disk.
    The canonical sound-library convention used by `_handle_stitch_library`
    (line 15531: `production / "assets" / "sound_library"`) is the single
    source of truth. Endpoint now scans `Production/assets/sound_library/ambient/`.
    Note: endpoint name `phase_b_ambient_preset_list` is a misnomer (this is
    a global ambient catalog, not phase-b-specific) but renaming is out of
    scope for this fix per the parent dispatch.
    """
    ambient_dir = _data_root(h) / "assets" / "sound_library" / "ambient"
    items: list[dict] = []
    if ambient_dir.is_dir():
        for f in sorted(ambient_dir.iterdir(), key=lambda p: p.name):
            if not f.is_file():
                continue
            if f.suffix.lower() != ".mp3":
                continue
            items.append({
                "preset_id": f.stem,
                "file_size_bytes": f.stat().st_size,
            })
    return h._send_json(200, {"ok": True, "items": items, "count": len(items)})


# ---------------------------------------------------------------------------
# Anthropic helper — shared by suggest_script + brief generation
# ---------------------------------------------------------------------------

def _call_anthropic_urllib(api_key: str, req_body: dict, timeout: int = 60) -> tuple:
    """Make a single Anthropic Messages API call.
    Returns (resp_data_dict, elapsed_ms_int).
    Raises urllib.error.HTTPError or urllib.error.URLError on failure.
    """
    import urllib.request as _ur
    url = "https://api.anthropic.com/v1/messages"
    req_data = json.dumps(req_body).encode("utf-8")
    req = _ur.Request(
        url, data=req_data,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    t0 = time.time()
    with _ur.urlopen(req, timeout=timeout) as resp:
        resp_data = json.loads(resp.read().decode("utf-8"))
    return resp_data, int((time.time() - t0) * 1000)


def _build_therapeutic_brief(
    api_key: str,
    module_meta: dict,
    therapeutic_note: str,
    technique_inventory: str,
) -> dict | None:
    """Generate a structured therapeutic brief via a separate Haiku call.

    Returns dict with {goal, must_hits, what_to_evoke, watch_outs} or None on
    any failure. Never raises — brief is non-critical; script generation is the
    primary payload.

    Brief content spec (per Kim 2026-05-25):
      goal        — what the child will EXPERIENCE and to what clinical end
      must_hits   — ordered steps the exercise structurally requires
      what_to_evoke — internal state/feeling/insight/body-sensation
      watch_outs  — contraindications for children, clinical caveats
    """
    creature = module_meta.get('creature_name', '')
    technique = module_meta.get('technique_name', '') or '(see Therapeutic Note)'

    system_prompt = (
        "You generate tightly structured clinical guidance briefs for CRI-framework "
        "script writers (MindfulNest therapeutic app, ages 7–11). "
        "Return ONLY a valid JSON object — no preamble, no explanation, no markdown fences."
    )
    user_prompt = (
        f"Creature: {creature}\nTechnique: {technique}\n\n"
        f"Therapeutic Note:\n---\n{therapeutic_note or '(not available)'}\n---\n\n"
        "Return this exact JSON object and nothing else:\n"
        "{\n"
        '  "goal": "<one sentence: what the child will EXPERIENCE, and to what clinical end>",\n'
        '  "must_hits": ["<ordered step 1 the technique structurally requires>", "<step 2>", "..."],\n'
        '  "what_to_evoke": ["<internal state / feeling / insight / body-sensation bullet>", "..."],\n'
        '  "watch_outs": ["<contraindication for children OR clinical caveat OR thing to avoid>", "..."]\n'
        "}\n\n"
        "Rules:\n"
        "  - goal: exactly ONE sentence, clinically precise\n"
        "  - must_hits: 2–4 bullets, ORDERED (step 1 then step 2 etc.), structural requirements of the technique\n"
        "  - what_to_evoke: 2–4 bullets — the internal state/insight/realization/body-feeling the child reaches\n"
        "    (child-accessible language — what the child actually notices, not clinical terminology)\n"
        "  - watch_outs: 2–4 bullets — contraindications for children, clinical caveats, things to avoid;\n"
        "    clinical precision OK here (Kim is the therapist)\n"
        "  - ONLY the JSON object. No extra text, no markdown fences."
    )
    req_body = {
        "model": "claude-haiku-4-5",
        "max_tokens": 512,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }
    try:
        resp_data, _ = _call_anthropic_urllib(api_key, req_body, timeout=30)
        content = resp_data.get("content") or []
        raw = ""
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                raw += block.get("text", "")
        raw = raw.strip()
        # Strip markdown fences if model ignores instructions
        if raw.startswith("```"):
            lines = raw.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            raw = "\n".join(lines).strip()
        brief = json.loads(raw)
        # Validate expected keys are present
        required = ("goal", "must_hits", "what_to_evoke", "watch_outs")
        for k in required:
            if k not in brief:
                print(f"[suggest_script] brief missing key {k!r} — dropping brief")
                return None
        return brief
    except Exception as exc:
        print(f"[suggest_script] therapeutic brief generation failed (non-fatal): {exc}")
        return None


_M1_PHASE_A_FEW_SHOT = (
    "OK, We're back!  The Great Wizard is on his way.  He's going to teach "
    "you a simple Magic Spell. You'll use magic to clear the stress right "
    "out of your body.  This one's super useful.  You can use it at school "
    "if you can't stop wiggling. [pause][pause] You can use it to help you "
    "fall asleep faster at night. [pause][pause][pause] Oh- and it's a great "
    "trick if you're feeling angry and want to get back in control.  "
    "Wanna try? [pause] Oh- here he comes!"
)


_M1_PHASE_B_FEW_SHOT = (
    "[warm] Ah, yes. ….. Welcome little one …... I am your Magical "
    "Arts teacher. I've come to teach you …. the Magic Hands Spell.\n"
    "You'll make a real ball of energy … right between your "
    "hands.[long pause]\n"
    "Step One. [long pause] Rub your hands together. …. Getting "
    "warmer … warmer.[silence:4s]\n"
    "Good.\n"
    "Now imagine a soccer-sized ball of magic in your "
    "hands. [silence:6s]\n"
    "Can you feel it? [long pause] [long pause] Big breath "
    "in.[long pause]\n"
    "As you breathe out, move your hands closer "
    "together. [silence:8s]\n"
    "Good. Pull your hands farther apart. [silence:6s]\n"
    "Now move your hands in and out, however you like. Play with "
    "the energy you feel between your hands.[silence:9s]\n"
    "Keep breathing. [silence:4s]\n"
    "What do you feel between your hands? … Pulling? … Tingling? "
    "… Warmth? … [silence:6s]\n"
    "Can you move the energy around?[silence:4s]\n"
    "That's the magic you have inside of you.\n"
    "Let that magic grow stronger... [silence:4s]. Now, off you "
    "go, little one. Come back again later for your next lesson."
)


def _format_phase_a_authoring_docs_section(docs: list) -> str:
    """Render loaded Production/ Phase A Suggest Script docs for Claude."""
    labels = {
        "suggest_skeleton": (
            "Phase A Suggest Script Beat Skeleton (pre-Phase B sell — "
            "purpose beats, not fixed prose)"
        ),
    }
    parts = []
    for doc in docs or []:
        text = (doc.get("text") or "").strip()
        if not text:
            continue
        fname = doc.get("filename") or doc.get("key") or "unknown"
        label = labels.get(doc.get("key") or "", fname)
        parts.append(
            f"## {label}\n"
            f"Source file: Production/{fname}\n"
            f"---\n{text}\n---"
        )
    if not parts:
        return (
            "Phase A authoring documents: (NOT FOUND — expected "
            "Production/PHASE_A_SUGGEST_SKELETON_v1_*.md on the project root)\n"
        )
    return "\n\n".join(parts) + "\n"


def _build_phase_a_suggest_user_prompt(
    *,
    module_identity: str,
    therapeutic_section: str,
    technique_section: str,
    phase_b_script: str,
    authoring_docs_section: str,
) -> str:
    """Assemble Phase A Suggest Script prompt — pre-Phase B benefit sell."""
    phase_b_alignment = (
        "Phase B draft in state (vocabulary alignment only — child has NOT "
        "heard this yet; Phase A plays BEFORE Phase B):\n"
        f"---\n{phase_b_script}\n---\n"
        if phase_b_script
        and not phase_b_script.startswith("(no phase_b_script")
        else (
            "Phase B draft: (not in state — infer spell name and benefits "
            "from Therapeutic Note only)\n"
        )
    )
    return (
        "You are drafting a Phase A script for MindfulNest (ages 7-11), "
        "spoken by Arlo the guide bird. NARRATIVE POSITION: Phase A plays "
        "**before** Phase B. The child is about to enter the Great Wizard's "
        "lesson. Arlo's job is to SELL the purpose and meaning of what they "
        "are about to learn — not to teach technique steps and not to "
        "recap a meditation they already heard.\n\n"
        f"{module_identity}\n"
        f"{therapeutic_section}\n"
        f"{technique_section}\n"
        f"{phase_b_alignment}\n"
        "AUTHORING DOCUMENTS (canonical — follow beat purposes exactly; "
        "fill each beat from THIS module's Therapeutic Note + Technique "
        "Inventory):\n\n"
        f"{authoring_docs_section}\n"
        "## PRODUCER OUTPUT FORMAT (Storyboard Phase A tab)\n\n"
        "- Output PLAIN SPOKEN TEXT ONLY — no beat labels, no markdown "
        "headers, no speaker prefixes, no commentary.\n"
        "- Satisfy beats in order: RE_ENTRY → WIZARD_INCOMING → "
        "MEANING_PROMISE → BENEFIT_SELL → INTEREST_JOSTLER → HANDOFF.\n"
        "- MEANING_PROMISE: exactly 1 sentence — body, mind, or useful-tool "
        "frame per skeleton rules.\n"
        "- BENEFIT_SELL: 1–3 relatable real-life examples (not a fixed "
        "count); fresh per module.\n"
        "- INTEREST_JOSTLER: exactly 1 short phrase (wanna try / cool right "
        "/ advanced / etc.).\n"
        "- HANDOFF: wizard-arrival bridge into Phase B; no technique HOW.\n"
        "- Use [pause] for breath rhythm between benefit examples when "
        "needed. Do not use [silence:Ns].\n"
        "- Target ~20–45 seconds spoken. Warm Arlo voice — not bouncy "
        "sales-pitch.\n"
        "- Do NOT teach meditation steps, body sensations, or Phase B "
        "instructions.\n\n"
        "## FEW-SHOT (Kim-approved M1 Magic Hands — structure illustration "
        "ONLY; do not copy benefit examples for other modules)\n\n"
        f"{_M1_PHASE_A_FEW_SHOT}\n\n"
        "## TASK\n\n"
        "1. Internally map each beat purpose from the skeleton to this "
        "module's Therapeutic Note.\n"
        "2. Write ONLY the spoken Phase A script — all six beats as "
        "continuous Arlo dialogue."
    )


def _format_phase_b_authoring_docs_section(docs: list) -> str:
    """Render loaded Production/ Phase B authoring docs for the Claude prompt."""
    labels = {
        "clarity_checklist": "Phase B Clarity Checklist (template fork + Q1–Q4 gate)",
        "production_process": "Phase B Production Process (9-step clinical workflow)",
    }
    parts = []
    for doc in docs or []:
        text = (doc.get("text") or "").strip()
        if not text:
            continue
        fname = doc.get("filename") or doc.get("key") or "unknown"
        label = labels.get(doc.get("key") or "", fname)
        parts.append(
            f"## {label}\n"
            f"Source file: Production/{fname}\n"
            f"---\n{text}\n---"
        )
    if not parts:
        return (
            "Phase B authoring documents: (NOT FOUND — expected "
            "Production/PHASE_B_CLARITY_CHECKLIST_v1_*.md and "
            "Production/PHASE_B_PRODUCTION_PROCESS_v1_*.md on the "
            "project root)\n"
        )
    return "\n\n".join(parts) + "\n"


def _build_phase_b_suggest_user_prompt(
    *,
    module_identity: str,
    skeleton_metadata_section: str,
    therapeutic_section: str,
    dossier_section: str,
    technique_section: str,
    phase_a_script: str,
    authoring_docs_section: str,
    approved_few_shot: str | None = None,
    approved_few_shot_label: str = "Kim-approved M1 — match sparseness",
) -> str:
    """Assemble the Phase B Suggest Script user prompt from live doc loads."""
    few_shot = (approved_few_shot or _M1_PHASE_B_FEW_SHOT).strip()
    return (
        "You are drafting a Phase B meditation script for MindfulNest "
        "(ages 7-11), narrated by Cedric the wizard. The child has "
        "eyes CLOSED after Phase A — this is guided practice, not "
        "storytelling.\n\n"
        f"{module_identity}\n"
        f"{skeleton_metadata_section}\n"
        f"{therapeutic_section}\n"
        f"{dossier_section}\n"
        f"{technique_section}\n"
        "Phase A script (locked vocabulary source — CONNECTION must "
        "reuse exact Phase A words; never re-teach what Phase A showed):\n"
        f"---\n{phase_a_script}\n---\n\n"
        "AUTHORING DOCUMENTS (canonical — follow these exactly; "
        "clarity checklist picks the template, production process "
        "governs clinical fidelity; research dossier Recommended "
        "Approach defines ordered exercise steps):\n\n"
        f"{authoring_docs_section}\n"
        "## PRODUCER OUTPUT FORMAT (Storyboard Phase B tab)\n\n"
        "These rules OVERRIDE illustrative {{PAUSE:Xs}} / {{BELL_CUE}} "
        "examples inside the authoring docs above. This draft goes "
        "directly into the Phase B producer textarea + TTS pipeline.\n\n"
        "- Output PLAIN SPOKEN TEXT ONLY — no markdown headers, no "
        "section labels, no word-count footers, no template commentary.\n"
        "- Teach the EXACT spell named in Arc Skeleton metadata — not a "
        "generic meditation or a different module's technique.\n"
        "- NO creature narrative or scene-setting (no 'Luna is excited', "
        "no 'watch what X learns'). Child cannot see the screen.\n"
        "- NO 'Cedric:' speaker prefixes.\n"
        "- Use [silence:Ns] for pauses 2s+ (server ffmpeg injection). "
        "Use ellipsis (…) for sub-2s pauses. [long pause] and [warm] "
        "are valid.\n"
        "- Do NOT use {{PAUSE:Xs}}, {{BELL_CUE}}, {{INHALE_CUE}}, etc. "
        "in this draft (post-approval audio markers per Production "
        "Process Step 9b).\n"
        "- Replace {childName} with universal phrasing ('little one') — "
        "no personalization variables in rendered audio.\n"
        "- Strictly enforce the word budget for the chosen template.\n"
        "- Spend words on instruction clarity, not atmosphere or imagery.\n\n"
        f"## FEW-SHOT ({approved_few_shot_label})\n\n"
        f"{few_shot}\n\n"
        "## TASK\n\n"
        "1. Answer Q1–Q4 + Q2b from the Clarity Checklist internally.\n"
        "2. Select the correct template (standard / sequential-step / "
        "cycle-based / preview-enhanced).\n"
        "3. Follow Research Dossier Recommended Approach steps in order.\n"
        "4. Write ONLY the spoken Phase B script — nothing else."
    )


def handle_phase_suggest_script(h, body: dict)-> None:

    """POST /api/phase/suggest_script {phase, event_id?, scope_event_id?}

    Drafts a Phase A or Phase B script via Claude API, grounded in the
    authored Therapeutic Note + Unified Technique Inventory for the
    current module.

    Phase A loads PHASE_A_SUGGEST_SKELETON_v1_*.md (beat-purpose pre-Phase-B
    sell) and optional phase_b_script for vocabulary alignment only.
    Phase B loads PHASE_B_CLARITY_CHECKLIST + PRODUCTION_PROCESS and locked
    phase_a_script for CONNECTION vocabulary.

    Resolves event_id to module metadata via prod_modules, then loads the
    Therapeutic Note (Arc Skeleton) and UNIFIED_TECHNIQUE_INVENTORY.

    Per LDs PHASE_A_PRODUCER_V1 + PHASE_B_PRODUCER_V1 +
    PB_2_THERAPEUTIC_SOURCES_LOAD_V1.
    """
    # READ-ONLY probe (LLM script suggestion — does not mutate state).
    # Per spec_v2 §5.2 + SCOPE_REQUIRED_DEFAULTS_V1 read-only probes keep
    # allow_missing=True.
    if not h._assert_event_scope(h._scope_body(body), allow_missing=True):
        return
    phase = ((body or {}).get("phase") or "").strip().lower()
    if phase not in ("a", "b"):
        return h._send_error_v59(
                   400,
                   error_code="PHASE_MUST_BE_A_OR",
                   error_message="phase must be 'a' or 'b'",
                   retry_safe=False,
               )

    # Resolve the Anthropic API key.
    try:
        sys.path.insert(0, str(_PSERVER_REPO_ROOT / "lib"))
        from credential_store import get_secret_optional  # type: ignore
        api_key = get_secret_optional("ANTHROPIC_API_KEY")
    except Exception:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return h._send_json(503, {
            "ok": False,
            "code": "ANTHROPIC_API_KEY_MISSING",
            "message": (
                "Anthropic API key not configured. Add ANTHROPIC_API_KEY to "
                "Doppler (project=mindfulnest, config=dev) or set the env var "
                "and restart the server. Endpoint code is ready."
            ),
            "phase": phase,
        })

    # Read state + resolve the event_id to module metadata.
    try:
        state = h.app.state.read_state()
    except Exception:
        state = {}

    scope = h._scope_body(body)
    # Resolve module via Arc Skeleton play-order (Event_3 → M4 Ember, not M3).
    # Production folder name is authoritative over stale/wrong M-form in state.
    _production_folder = (
        getattr(h.app.event_dir, 'name', None)
        if getattr(h.app, 'event_dir', None)
        else None
    )
    _event_id_candidates = [
        state.get('event_id'),
        (body or {}).get('event_id'),
        scope.get('event_id'),
        (body or {}).get('scope_event_id'),
        getattr(h.app, 'event_id', None),
        _production_folder,
    ]
    event_id_str = next((str(c).strip() for c in _event_id_candidates if c), '')
    module_meta = _resolve_module_for_event(
        event_id_str,
        production_folder_id=_production_folder,
    )
    if not module_meta:
        return h._send_error_v59(
            422,
            error_code="MODULE_EVENT_ID_UNRESOLVED",
            error_message=(
                f"Cannot resolve module for event_id={event_id_str!r} "
                f"(folder={_production_folder!r}). "
                "Expected numbered Event_N folder or M-form id resolvable via Arc Skeleton."
            ),
            retry_safe=False,
            extra={
                "ok": False,
                "phase": phase,
                "event_id": event_id_str,
                "production_folder_id": _production_folder,
            },
        )

    # Load the authored therapeutic sources for this module.
    bg = _bg_module()
    arc_num = module_meta['arc_number']
    m_num = module_meta['m_number']
    skeleton_meta = bg.extract_skeleton_module_metadata(arc_num, m_num)
    try:
        sys.path.insert(0, str(_PSERVER_TOOLS_DIR.parent / "lib"))
        from phase_b_suggest_sources import (  # noqa: PLC0415
            build_therapeutic_brief_from_sources,
            enrich_module_meta,
            format_dossier_prompt_section,
            format_skeleton_metadata_section,
        )
    except Exception as _pbs_exc:
        print(f"[suggest_script] phase_b_suggest_sources import failed: {_pbs_exc}")
        build_therapeutic_brief_from_sources = None  # type: ignore
        enrich_module_meta = lambda m, s: m  # type: ignore
        format_dossier_prompt_section = lambda d: ""  # type: ignore
        format_skeleton_metadata_section = lambda s: ""  # type: ignore

    module_meta = enrich_module_meta(module_meta, skeleton_meta)
    therapeutic_note = bg.extract_therapeutic_note(arc_num, m_num)
    technique_inventory_full = bg.load_technique_inventory()
    technique_inventory = bg.slice_technique_inventory_for_module(
        m_num, technique_inventory_full,
    )
    research_dossier = bg.load_phase_b_research_dossier(m_num)
    approved_script = bg.load_phase_b_approved_script(m_num) if phase == "b" else {}
    phase_b_authoring_docs = (
        bg.load_phase_b_suggest_script_docs() if phase == "b" else []
    )
    phase_a_authoring_docs = (
        bg.load_phase_a_suggest_script_docs() if phase == "a" else []
    )

    # Phase B: locked Phase A vocabulary for CONNECTION section.
    _phase_a_partition = state.get("phase_a") or {}
    _phase_b_partition = state.get("phase_b") or {}
    phase_a_script = (
        _phase_a_partition.get("phase_a_script")
        or state.get("phase_a_script")
        or "(no phase_a_script in state — write Phase A first or paste a draft to seed CONNECTION vocabulary)"
    )
    phase_b_script = (
        _phase_b_partition.get("phase_b_script")
        or state.get("phase_b_script")
        or ""
    )

    # Sources_loaded telemetry — surfaced in the JSON response so callers
    # can detect the silent-failure regression class (handler runs but
    # therapeutic sources fail to load).
    sources_loaded = {
        'event_id_resolved': event_id_str,
        'production_folder_id': _production_folder,
        'skeleton_play_order': module_meta.get('play_order'),
        'skeleton_event_id': skeleton_meta.get('skeleton_event_id'),
        'spell_name': module_meta.get('spell_name') or skeleton_meta.get('spell_name'),
        'therapeutic_note_chars': len(therapeutic_note),
        'technique_inventory_chars': len(technique_inventory),
        'technique_inventory_full_chars': len(technique_inventory_full),
        'arc_number': module_meta['arc_number'],
        'm_number': module_meta['m_number'],
        'creature_name': module_meta['creature_name'],
        'technique_name': module_meta['technique_name'],
        'domain': module_meta.get('domain') or skeleton_meta.get('domain'),
    }
    if phase == "b":
        sources_loaded['research_dossier'] = {
            'filename': research_dossier.get('filename'),
            'chars': research_dossier.get('chars'),
        }
        sources_loaded['approved_script'] = {
            'filename': approved_script.get('filename'),
            'chars': approved_script.get('chars'),
        }
    if phase == "b":
        sources_loaded['phase_a_script_chars'] = len(phase_a_script)
        sources_loaded['phase_b_docs'] = [
            {
                'key': d.get('key'),
                'filename': d.get('filename'),
                'version': d.get('version'),
                'chars': d.get('chars'),
            }
            for d in phase_b_authoring_docs
        ]
    if phase == "a":
        sources_loaded['phase_b_script_chars'] = len(phase_b_script)
        sources_loaded['phase_a_docs'] = [
            {
                'key': d.get('key'),
                'filename': d.get('filename'),
                'version': d.get('version'),
                'chars': d.get('chars'),
            }
            for d in phase_a_authoring_docs
        ]
    if not therapeutic_note:
        print(
            f'[suggest_script] WARNING: no Therapeutic Note found for '
            f'arc={module_meta["arc_number"]} m_number={module_meta["m_number"]} '
            f'event_id={event_id_str!r}. Claude prompt will lack authored context.'
        )
    if phase == "b" and not (research_dossier.get("text") or "").strip():
        print(
            f'[suggest_script] WARNING: no Phase B research dossier for '
            f'M{module_meta["m_number"]}. Brief will fall back to Therapeutic Note only.'
        )
    if not technique_inventory:
        print(
            '[suggest_script] WARNING: technique inventory unavailable at '
            'Canon/UNIFIED_TECHNIQUE_INVENTORY_v1_*.md. Claude prompt will '
            'lack canonical technique catalog.'
        )
    if phase == "b":
        for doc in phase_b_authoring_docs:
            if not (doc.get("text") or "").strip():
                print(
                    '[suggest_script] WARNING: Phase B authoring doc missing: '
                    f'{doc.get("key")!r} (expected Production/{doc.get("filename") or "v1_*.md"}). '
                    'Claude prompt will lack canonical template guidance.'
                )
        if phase_a_script.startswith("(no phase_a_script"):
            print(
                '[suggest_script] WARNING: no phase_a_script in state. '
                'CONNECTION section cannot reuse Phase A vocabulary.'
            )
    if phase == "a":
        for doc in phase_a_authoring_docs:
            if not (doc.get("text") or "").strip():
                print(
                    '[suggest_script] WARNING: Phase A authoring doc missing: '
                    f'{doc.get("key")!r} (expected Production/{doc.get("filename") or "PHASE_A_SUGGEST_SKELETON_v1_*.md"}). '
                    'Claude prompt will lack beat-purpose skeleton guidance.'
                )

    # Module identity block — shared header for both phases.
    spell_label = module_meta.get('spell_name') or skeleton_meta.get('spell_name') or ''
    module_identity = (
        f"Module identity (resolved from event_id={event_id_str!r}, "
        f"folder={_production_folder!r}):\n"
        f"  - Arc: {module_meta['arc_number']}\n"
        f"  - Skeleton play order: {module_meta.get('play_order')}\n"
        f"  - M-number: M{module_meta['m_number']}\n"
        f"  - Creature: {module_meta['creature_name']}\n"
        f"  - Domain: {module_meta.get('domain') or skeleton_meta.get('domain') or '(see skeleton)'}\n"
        f"  - Technique: {module_meta['technique_name'] or '(see Therapeutic Note below)'}\n"
        f"  - Spell Name: {spell_label or '(see Arc Skeleton metadata)'}\n"
    )

    skeleton_metadata_section = format_skeleton_metadata_section(skeleton_meta)
    dossier_section = (
        format_dossier_prompt_section(research_dossier) if phase == "b" else ""
    )

    therapeutic_section = (
        "Authored Therapeutic Note for THIS module (from Arc Skeleton — "
        "this is the canonical source of truth for the technique, "
        "rationale, and clinical framing; the script MUST teach the "
        "technique it describes, not a generic meditation):\n"
        f"---\n{therapeutic_note}\n---\n"
        if therapeutic_note
        else "Authored Therapeutic Note: (NOT FOUND — Claude must explicitly state this gap in the response if asked to write a clinically-grounded script)\n"
    )

    technique_section = (
        "Canonical Technique Inventory (the catalog of all MindfulNest "
        "techniques with mechanism, age suitability, and clinical "
        "references — use the matching entry as the authoritative "
        "definition of the technique):\n"
        f"---\n{technique_inventory}\n---\n"
        if technique_inventory
        else ""
    )

    if phase == "a":
        authoring_docs_section = _format_phase_a_authoring_docs_section(
            phase_a_authoring_docs,
        )
        user_prompt = _build_phase_a_suggest_user_prompt(
            module_identity=module_identity,
            therapeutic_section=therapeutic_section,
            technique_section=technique_section,
            phase_b_script=phase_b_script,
            authoring_docs_section=authoring_docs_section,
        )
        system_prompt = (
            "You are a CRI script writer for MindfulNest (ages 7-11), "
            "drafting Phase A pre-Phase-B sell scripts in Arlo the guide "
            "bird voice. Follow the loaded beat-purpose skeleton exactly. "
            "Ground every script in the Therapeutic Note + Technique "
            "Inventory. Output only spoken script text — no markdown or "
            "commentary."
        )
    else:  # phase == "b"
        authoring_docs_section = _format_phase_b_authoring_docs_section(
            phase_b_authoring_docs,
        )
        user_prompt = _build_phase_b_suggest_user_prompt(
            module_identity=module_identity,
            skeleton_metadata_section=skeleton_metadata_section,
            therapeutic_section=therapeutic_section,
            dossier_section=dossier_section,
            technique_section=technique_section,
            phase_a_script=phase_a_script,
            authoring_docs_section=authoring_docs_section,
            approved_few_shot=(approved_script.get("text") or None),
            approved_few_shot_label=(
                f"Kim-approved M{module_meta['m_number']} — match sparseness"
                if (approved_script.get("text") or "").strip()
                else "Kim-approved M1 — match sparseness"
            ),
        )
        system_prompt = (
            "You are a CRI script writer drafting Phase B meditation "
            "scripts for MindfulNest (ages 7-11), narrated by Cedric "
            "the wizard. Follow the loaded authoring documents exactly. "
            "Ground every script in the Therapeutic Note, Technique "
            "Inventory, and Phase A script in the user message. Output "
            "only the spoken script text — no markdown wrappers or "
            "commentary."
        )

    # Call Anthropic in PARALLEL: (1) script generation, (2) therapeutic brief.
    # Both use Haiku. Brief failure is non-fatal — returns null in the response.
    # Using _cf (concurrent.futures) already imported at module top.
    script_req = {
        "model": "claude-haiku-4-5",
        "max_tokens": 2048,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }
    with _cf.ThreadPoolExecutor(max_workers=2) as pool:
        script_future = pool.submit(_call_anthropic_urllib, api_key, script_req, 60)
        therapeutic_brief = None
        if build_therapeutic_brief_from_sources:
            therapeutic_brief = build_therapeutic_brief_from_sources(
                skeleton_meta,
                therapeutic_note,
                research_dossier.get("text") or "",
            )
        brief_future = None
        if therapeutic_brief is None:
            brief_future = pool.submit(
                _build_therapeutic_brief,
                api_key, module_meta, therapeutic_note, technique_inventory,
            )
        # Script result — errors are fatal, returned as HTTP error response
        try:
            resp_data, elapsed_ms = script_future.result()
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            return h._send_error_v59(
                502, error_code="GENERIC_ERROR",
                error_message=f"Anthropic API HTTP {exc.code}",
                retry_safe=True,
                extra={"ok": False, "detail": err_body[:500]},
            )
        except urllib.error.URLError as exc:
            return h._send_error_v59(
                502, error_code="GENERIC_ERROR",
                error_message=f"Anthropic API URL error: {exc}",
                retry_safe=True,
                extra={"ok": False},
            )
        # Brief result — non-fatal
        if brief_future is not None:
            try:
                therapeutic_brief = brief_future.result()
            except Exception as exc:
                print(f"[suggest_script] brief future error (non-fatal): {exc}")
                therapeutic_brief = None

    # Extract text from script response.
    content = resp_data.get("content") or []
    script_text = ""
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            script_text += block.get("text", "")
    usage = resp_data.get("usage") or {}
    return h._send_json(200, {
        "ok": True,
        "phase": phase,
        "script": script_text,
        "therapeutic_brief": therapeutic_brief,
        "model_used": resp_data.get("model", "claude-haiku-4-5"),
        "generation_time_ms": elapsed_ms,
        "tokens_in": usage.get("input_tokens"),
        "tokens_out": usage.get("output_tokens"),
        "sources_loaded": sources_loaded,
    })


PHASE_VOICE_STEM_PAUSE_DEFAULT_S = 0.5
PHASE_VOICE_STEM_CONCAT_V1 = "PHASE_VOICE_STEM_CONCAT_V1"


def _parse_silence_segments(script: str):
    """Split script on pause/silence markers for multi-segment TTS + real silence.

    Supports ``[silence:1.2s]``, ``[pause]``, ``[break]``, ``[silence]`` (same as beat TTS cues).
    Returns list of ('text', str) | ('silence', float) tuples.
    """
    import re as _re

    _PAT = _re.compile(
        r'\[(?:silence:\s*(\d+(?:\.\d+)?)\s*s?|pause|break|silence)\]',
        _re.IGNORECASE,
    )
    parts = []
    last = 0
    for m in _PAT.finditer(script):
        chunk = script[last:m.start()].strip()
        if chunk:
            parts.append(("text", chunk))
        dur_raw = m.group(1)
        dur = float(dur_raw) if dur_raw else PHASE_VOICE_STEM_PAUSE_DEFAULT_S
        parts.append(("silence", dur))
        last = m.end()
    tail = script[last:].strip()
    if tail:
        parts.append(("text", tail))
    return parts


def _concat_audio_parts_seamless(parts: list, out_path) -> None:
    """Decode segments to PCM mono before join — no MP3 frame-boundary clicks."""
    from pathlib import Path as _Path
    import shutil as _shutil

    paths = [_Path(p).resolve() for p in parts]
    if not paths:
        raise ValueError("no audio parts to concat")
    out_path = _Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if len(paths) == 1:
        _shutil.copy2(paths[0], out_path)
        return
    inputs: list[str] = []
    for p in paths:
        inputs.extend(["-i", str(p)])
    n = len(paths)
    lanes = "".join(
        f"[{i}:a]aresample=44100,aformat=sample_fmts=s16:channel_layouts=mono[a{i}];"
        for i in range(n)
    )
    concat_in = "".join(f"[a{i}]" for i in range(n))
    filt = f"{lanes}{concat_in}concat=n={n}:v=0:a=1[aout]"
    subprocess.run(
        [
            "ffmpeg", "-y",
            *inputs,
            "-filter_complex", filt,
            "-map", "[aout]",
            "-c:a", "libmp3lame", "-b:a", "128k",
            str(out_path),
        ],
        check=True,
        capture_output=True,
        timeout=300,
    )


def _build_silence_mp3(duration_s: float, out_path) -> None:
    """Write a silent MP3 of exact duration using ffmpeg anullsrc."""
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"anullsrc=r=44100:cl=mono",
            "-t", str(duration_s),
            "-acodec", "libmp3lame",
            "-b:a", "128k",
            str(out_path),
        ],
        check=True,
        capture_output=True,
    )


def handle_phase_reject_lipsync(h, body: dict) -> None:
    """POST /api/phase_{a|b}/reject_lipsync

    Clears lipsync + derived mix/stitch state so the waveform returns to the
    voice stem. Keeps the lipsync MP4 on disk (archived filename optional later).
    Body: {"phase": "a"|"b"}
    """
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return

    phase = (body.get("phase") or "").strip().lower()
    err = h._phase_check(phase)
    if err:
        return h._send_error_v59(
            400,
            error_code="GENERIC_ERROR",
            error_message=err,
            retry_safe=False,
            extra={"hint": "phase is 'a' or 'b'."},
        )

    state = h.app.state.read_state()
    lipsync_name = state.get(f"phase_{phase}_lipsync_file")
    if not lipsync_name:
        return h._send_error_v59(
            404,
            error_code="GENERIC_ERROR",
            error_message=f"phase_{phase}_lipsync_file not set — nothing to reject",
            retry_safe=False,
            extra={"hint": "Generate a lipsync first, or edit the stem trim directly if no video exists."},
        )

    if state.get(f"phase_{phase}_lipsync_status") == "running":
        return h._send_error_v59(
            409,
            error_code="PHASE_LIPSYNC_RUNNING",
            error_message=f"Phase {phase.upper()} lipsync still running",
            retry_safe=False,
            extra={"hint": "Wait for the in-flight job to finish or time out before rejecting."},
        )
    from phase_lipsync_job_contract import phase_lipsync_job_busy

    if phase_lipsync_job_busy(
        state.get(f"phase_{phase}_lipsync_status"),
        state.get(f"phase_{phase}_lipsync_task_id"),
    ):
        return h._send_error_v59(
            409,
            error_code="PHASE_LIPSYNC_RUNNING",
            error_message=f"Phase {phase.upper()} lipsync still running",
            retry_safe=False,
            extra={"hint": "Wait for the in-flight job to finish before rejecting."},
        )

    archived_name: str | None = None
    try:
        src = require_basename_under_dir(lipsync_name, h.app.event_dir)
        if src.is_file():
            archive_dir = h.app.event_dir / "_rejected_lipsync"
            archive_dir.mkdir(exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            archived = archive_dir / f"phase_{phase}_lipsync_rejected_{ts}_{src.name}"
            shutil.move(str(src), str(archived))
            archived_name = archived.name
    except (ValueError, OSError) as exc:
        print(f"[phase_reject_lipsync] archive move skipped: {exc}", flush=True)

    def _apply(st, _p=phase):
        _phase_clear_lipsync_derived(st, _p, requires_regen=True)
        st[f"phase_{_p}_lipsync_status"] = "rejected"
        st["_module_version"] = int(st.get("_module_version", 0) or 0) + 1
        return st["_module_version"]

    try:
        new_version = h.app.state.mutate_state(_apply)
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        return h._send_error_v59(
            500,
            error_code="GENERIC_ERROR",
            error_message=f"mutate_state failed: {type(exc).__name__}: {exc}",
            retry_safe=True,
        )

    return h._send_json(200, {
        "ok": True,
        "phase": phase,
        "archived_file": archived_name,
        "previous_lipsync_file": lipsync_name,
        "module_version": new_version,
        "message": (
            "Lipsync cleared from state — waveform now shows voice stem. "
            "Set stem trim (front/back seconds), then Send for Lipsync."
        ),
    })


def handle_phase_apply_stem_cut(h, body: dict) -> None:
    """POST /api/phase_{a|b}/apply_stem_cut

    Bakes persisted stem trim into a new voice_stem mp3 (ffmpeg), replaces
    phase_{phase}_voice_stem_file, clears trim keys, and invalidates lipsync.
    Body: {"phase": "a"|"b"}
    """
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return

    phase = (body.get("phase") or "").strip().lower()
    err = h._phase_check(phase)
    if err:
        return h._send_error_v59(
            400,
            error_code="GENERIC_ERROR",
            error_message=err,
            retry_safe=False,
            extra={"hint": "phase is 'a' or 'b'."},
        )

    state = h.app.state.read_state()
    stem_name = state.get(f"phase_{phase}_voice_stem_file")
    if not stem_name:
        return h._send_error_v59(
            404,
            error_code="GENERIC_ERROR",
            error_message=f"phase_{phase}_voice_stem_file not set",
            retry_safe=False,
            extra={"hint": "Generate a voice stem first."},
        )

    cut_start, cut_end = _phase_voice_stem_cut_window(state, phase)
    if cut_end <= cut_start + 0.001:
        return h._send_error_v59(
            400,
            error_code="GENERIC_ERROR",
            error_message="No stem cut region set — drag amber handles first",
            retry_safe=False,
            extra={"hint": "Amber box = audio to REMOVE. Drag handles, then Apply Cut."},
        )

    try:
        src = require_basename_under_dir(stem_name, h.app.event_dir)
    except ValueError as exc:
        return h._send_error_v59(
            400,
            error_code="GENERIC_ERROR",
            error_message=str(exc),
            retry_safe=False,
        )

    if not src.is_file():
        return h._send_error_v59(
            404,
            error_code="GENERIC_ERROR",
            error_message=f"voice stem missing on disk: {stem_name}",
            retry_safe=False,
        )

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_name = f"phase_{phase}_voice_stem_{ts}.mp3"
    out_path = h.app.event_dir / out_name
    try:
        _materialize_cut_out_audio(src, out_path, cut_start, cut_end)
        duration = _ffprobe_duration(out_path)
    except (subprocess.CalledProcessError, ValueError, OSError) as exc:
        traceback.print_exc()
        return h._send_error_v59(
            500,
            error_code="GENERIC_ERROR",
            error_message=f"stem cut failed: {exc}",
            retry_safe=True,
            extra={"hint": "Check ffmpeg/ffprobe and trim window size."},
        )

    mtime = int(os.path.getmtime(str(out_path)))

    def _apply(st, _p=phase, _n=out_name, _m=mtime):
        _phase_set_voice_stem_keys(st, _p, _n, _m)
        _phase_clear_stem_cut_keys(st, _p)
        _phase_clear_lipsync_derived(st, _p, requires_regen=True)
        st["_module_version"] = int(st.get("_module_version", 0) or 0) + 1
        return st["_module_version"]

    try:
        new_version = h.app.state.mutate_state(_apply)
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        return h._send_error_v59(
            500,
            error_code="GENERIC_ERROR",
            error_message=f"mutate_state failed: {type(exc).__name__}: {exc}",
            retry_safe=True,
        )

    pin_err = _phase_assert_voice_stem_pin_persisted(h, phase, out_name)
    if pin_err is not None:
        return pin_err

    return h._send_json(200, {
        "ok": True,
        "phase": phase,
        "file": out_name,
        "mtime": mtime,
        "duration_s": round(duration, 3),
        "cut_start_s": cut_start,
        "cut_end_s": cut_end,
        "previous_stem_file": stem_name,
        "module_version": new_version,
        "message": "Stem cut applied — removed amber region; waveform reloads kept audio.",
    })


def handle_phase_b_regen_audio(h, body: dict)-> None:

    """POST /api/phase_b/regen_audio

    Body: {"phase": "a"|"b", "script": "text"}

    Supports [silence:Ns] tags in script for exact server-side silence injection.
    Splits script at markers, calls ElevenLabs per segment, ffmpeg-concats with
    real silence between segments.  Single-segment scripts use the fast single-call path.

    Writes phase_{phase}_voice_stem_<TS>.mp3 to event_dir root.
    Patches state phase_X_voice_stem_file + phase_X_voice_stem_mtime via mutate_state.
    Returns 200 with file path + duration on success.
    """
    # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return

    # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — capture pin at entry; terminal writes assert via _check_event_pin.
    _pin = {
        "pinned_generation": h.app.event_generation,
        "pinned_event_dir": h.app.event_dir,
        "pinned_video_role": (body or {}).get("scope_video_role", "intro"),
        "_handler": '_handle_phase_b_regen_audio',
    }
    # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — pre-work pin check (S2).
    # If the event was swapped via /api/event/load between scope-guard
    # and work start, abort BEFORE any expensive work begins.
    if not h._check_event_pin(_pin, '_handle_phase_b_regen_audio_pre_work'):
        return h._send_error_v59(
                   423,
                   error_code="EVENT_CHANGED_PRE_WORK",
                   error_message="event_changed_pre_work",
                   retry_safe=False,
                   extra={"code": "ASYNC_JOB_GENERATION_PIN_V1", "handler": '_handle_phase_b_regen_audio', "hint": "Event changed between scope-guard and work start. "
                "No work was done; no orphan output. Client should "
                "re-hydrate scope and retry."},
               )

    phase = (body.get("phase") or "").strip().lower()
    err = h._phase_check(phase)
    if err:
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=err,
                   retry_safe=False,
                   extra={"hint": "phase is 'a' (Chipper) or 'b' (Cedric)."},
               )
    script = body.get("script") or ""
    if not isinstance(script, str) or not script.strip():
        return h._send_error_v59(
                   400,
                   error_code="SCRIPT_IS_REQUIRED_AND_MUST",
                   error_message="script is required and must be non-empty string",
                   retry_safe=False,
                   extra={"hint": "Paste the Phase {} script in the panel textarea.".format(phase.upper())},
               )
    if len(script) > 50_000:
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=f"script too long ({len(script)} chars, max 50000)",
                   retry_safe=False,
                   extra={"hint": "Split into shorter segments or edit down."},
               )

    # Load ElevenLabs key via parse_api_keys pattern (matches server-wide usage).
    root = h._phase_project_root()
    keys = parse_api_keys(root / "Production" / "API_KEYS_MASTER.md")
    elevenlabs_key = keys.get("elevenlabs")
    if not elevenlabs_key:
        return h._send_error_v59(
                   500,
                   error_code="ELEVENLABS_API_KEY_NOT_CONFIGURED",
                   error_message="ElevenLabs API key not configured",
                   retry_safe=True,
                   extra={"hint": "Set ELEVENLABS_API_KEY env var or populate API_KEYS_MASTER.md."},
               )

    voice_id, model_id, voice_settings, speaker = h._phase_resolve_voice_settings(phase)
    # Universal hardening: robust_https_request with 3 retries + 90s timeout.
    from kling_startend_pipeline import robust_https_request  # noqa: PLC0415

    def _tts_call(text_segment: str):
        """Single ElevenLabs TTS call; returns (status_code, bytes)."""
        body_bytes = json.dumps({
            "text": text_segment,
            "model_id": model_id,
            "voice_settings": voice_settings,
        }).encode("utf-8")
        return robust_https_request(
            host="api.elevenlabs.io",
            path=f"/v1/text-to-speech/{voice_id}",
            method="POST",
            headers={"xi-api-key": elevenlabs_key,
                     "Content-Type": "application/json",
                     "Accept": "audio/mpeg"},
            body=body_bytes,
            timeout=90,
            max_retries=3,
        )

    segments = _parse_silence_segments(script)
    use_multi = any(kind == "silence" for kind, _ in segments)

    t0 = time.time()
    if not use_multi:
        from production_server import _clean_text_for_tts  # noqa: PLC0415

        tts_script = _clean_text_for_tts(script)
        try:
            status_code, audio_bytes = _tts_call(tts_script)
        except Exception as exc:  # noqa: BLE001
            return h._send_error_v59(
                       502,
                       error_code="GENERIC_ERROR",
                       error_message=f"ElevenLabs network failure (after retries): "
                         f"{type(exc).__name__}: {exc}",
                       retry_safe=True,
                       extra={"speaker": speaker, "voice_id": voice_id,
                              "hint": "Check network / ElevenLabs status. Retry after a minute."},
                   )
        if status_code >= 400:
            detail = audio_bytes[:400].decode("utf-8", errors="replace")
            return h._send_error_v59(
                       502,
                       error_code="GENERIC_ERROR",
                       error_message=f"ElevenLabs HTTP {status_code}: {detail}",
                       retry_safe=True,
                       extra={"speaker": speaker,
                              "hint": "Often: API key expired or voice_id renamed. Check API_KEYS_MASTER.md."},
                   )
    else:
        # Multi-segment path: call ElevenLabs per text segment, inject real silence.
        import tempfile as _tempfile
        tmp_dir = Path(_tempfile.mkdtemp(prefix="mn_regen_audio_"))
        concat_parts = []  # list of pathlib.Path in order
        try:
            seg_idx = 0
            for kind, value in segments:
                if kind == 'text':
                    seg_path = tmp_dir / f"seg_{seg_idx:03d}_speech.mp3"
                    from production_server import _clean_text_for_tts  # noqa: PLC0415

                    tts_text = _clean_text_for_tts(value)
                    try:
                        sc, seg_bytes = _tts_call(tts_text)
                    except Exception as exc:  # noqa: BLE001
                        return h._send_error_v59(
                                   502,
                                   error_code="GENERIC_ERROR",
                                   error_message=f"ElevenLabs segment {seg_idx} network failure: "
                                     f"{type(exc).__name__}: {exc}",
                                   retry_safe=True,
                                   extra={"segment_index": seg_idx, "speaker": speaker},
                               )
                    if sc >= 400:
                        detail = seg_bytes[:400].decode("utf-8", errors="replace")
                        return h._send_error_v59(
                                   502,
                                   error_code="GENERIC_ERROR",
                                   error_message=f"ElevenLabs segment {seg_idx} HTTP {sc}: {detail}",
                                   retry_safe=True,
                                   extra={"segment_index": seg_idx, "speaker": speaker},
                               )
                    seg_path.write_bytes(seg_bytes)
                    concat_parts.append(seg_path)
                    seg_idx += 1
                else:  # silence
                    sil_path = tmp_dir / f"seg_{seg_idx:03d}_silence_{value}s.mp3"
                    try:
                        _build_silence_mp3(value, sil_path)
                    except subprocess.CalledProcessError as exc:
                        return h._send_error_v59(
                                   500,
                                   error_code="GENERIC_ERROR",
                                   error_message=f"ffmpeg silence generation failed for {value}s: {exc}",
                                   retry_safe=True,
                               )
                    concat_parts.append(sil_path)
                    seg_idx += 1

            concat_out = tmp_dir / "concat_out.mp3"
            _concat_audio_parts_seamless(concat_parts, concat_out)
            audio_bytes = concat_out.read_bytes()
        finally:
            # Clean up temp dir regardless of success/failure.
            import shutil as _shutil
            _shutil.rmtree(tmp_dir, ignore_errors=True)

    elapsed_call = time.time() - t0

    # Atomic write to event_dir root.
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_name = f"phase_{phase}_voice_stem_{ts}.mp3"
    out_path = h.app.event_dir / out_name
    tmp = out_path.with_suffix(f".mp3.tmp.{os.getpid()}")
    # LD-460 — terminal pin check before voice-stem file write.
    if not h._check_event_pin(_pin, "phase_b_regen_audio_write_bytes"):
        return h._send_error_v59(
                   423,
                   error_code="EVENT_CHANGED_MID_JOB",
                   error_message="event_changed_mid_job",
                   retry_safe=False,
                   extra={"code": "ASYNC_JOB_GENERATION_PIN_V1"},
               )
    try:
        tmp.write_bytes(audio_bytes)
        os.replace(tmp, out_path)
    except OSError as exc:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass
        return h._send_error_v59(
                   500,
                   error_code="GENERIC_ERROR",
                   error_message=f"atomic write failed: {exc}",
                   retry_safe=True,
                   extra={"hint": "Check event_dir permissions / disk space."},
               )
    # NOTE: No atempo post-processing on the regen_audio (audition) path.
    # ElevenLabs speed=0.50 (from Directus voice profile) already gives meditative
    # pacing for auditioning word delivery. Compounding atempo=0.75 on top produces
    # 37.5% normal speed — unnatural and artifacts on deep voices.
    # The Python production render (render_phase_b_v9_meditation.py) applies
    # atempo=0.75 on the final render where sentence-level silences are added
    # separately and the compounding is intentional.
    try:
        duration = _ffprobe_duration(out_path)
    except (subprocess.CalledProcessError, ValueError, OSError):
        duration = 0.0
    mtime = int(os.path.getmtime(str(out_path)))

    # Patch state via mutate_state.
    def _apply(state, _p=phase, _n=out_name, _m=mtime):
        _phase_set_voice_stem_keys(state, _p, _n, _m)
        # Fresh stem invalidates lipsync/mix/stitch derived from the old audio.
        _phase_clear_lipsync_derived(state, _p, requires_regen=True)
        _phase_clear_stem_cut_keys(state, _p)
        state["_module_version"] = int(state.get("_module_version", 0) or 0) + 1
        return state["_module_version"]
    try:
        new_version = h.app.state.mutate_state(_apply)
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        return h._send_error_v59(
                   500,
                   error_code="GENERIC_ERROR",
                   error_message=f"mutate_state failed: {type(exc).__name__}: {exc}",
                   retry_safe=True,
                   extra={"hint": "State.json could not be persisted. File was written to disk."},
               )

    pin_err = _phase_assert_voice_stem_pin_persisted(h, phase, out_name)
    if pin_err is not None:
        return pin_err

    return h._send_json(200, {
        "status": "ok",
        "phase": phase,
        "file": out_name,
        "mtime": mtime,
        "duration_s": round(duration, 3),
        "size_bytes": len(audio_bytes),
        "voice_id": voice_id,
        "speaker": speaker,
        "elapsed_s": round(elapsed_call, 2),
        "module_version": new_version,
    })


def _resolve_ambient_preset_path(h, preset_id: str) -> Path | None:
    """Resolve ambient bed preset_id to on-disk mp3 (sound_library first)."""
    from server_handlers.stitch_editor import _resolve_stitch_ambient_bed_path  # noqa: PLC0415

    raw = (preset_id or "").strip()
    if not raw or "/" in raw or "\\" in raw or ".." in raw:
        return None
    resolved = _resolve_stitch_ambient_bed_path(h, raw)
    if not resolved:
        return None
    path = Path(resolved)
    return path if path.is_file() else None


def handle_phase_b_mix_audio(h, body: dict)-> None:

    """POST /api/phase_b/mix_audio

    Body: {"phase": "b", "ambient_preset_id": "meditation_fireplace_v1"}

    Phase B only — Phase A ambient beds are applied in Stitcher at compose time.

    Reads phase_b_voice_stem_file from state (must exist).
    Loads ambient preset mp3, mixes voice + ambient, writes phase_b_mixed_<TS>.mp3.
    """
    # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return

    phase_early = (body.get("phase") or "").strip().lower()
    if phase_early == "a":
        return h._send_error_v59(
            400,
            error_code="PHASE_A_AMBIENT_STITCHER_ONLY",
            error_message="Phase A ambient beds are applied in Stitcher only",
            retry_safe=False,
            extra={
                "hint": (
                    "Export dry lipsync to Stitcher; ambient is added on the "
                    "Phase A stitch slot (auto-default on load)."
                ),
            },
        )

    # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — capture pin at entry; terminal writes assert via _check_event_pin.
    _pin = {
        "pinned_generation": h.app.event_generation,
        "pinned_event_dir": h.app.event_dir,
        "pinned_video_role": (body or {}).get("scope_video_role", "intro"),
        "_handler": '_handle_phase_b_mix_audio',
    }
    # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — pre-work pin check (S2).
    # If the event was swapped via /api/event/load between scope-guard
    # and work start, abort BEFORE any expensive work begins.
    if not h._check_event_pin(_pin, '_handle_phase_b_mix_audio_pre_work'):
        return h._send_error_v59(
                   423,
                   error_code="EVENT_CHANGED_PRE_WORK",
                   error_message="event_changed_pre_work",
                   retry_safe=False,
                   extra={"code": "ASYNC_JOB_GENERATION_PIN_V1", "handler": '_handle_phase_b_mix_audio', "hint": "Event changed between scope-guard and work start. "
                "No work was done; no orphan output. Client should "
                "re-hydrate scope and retry."},
               )

    phase = (body.get("phase") or "").strip().lower()
    err = h._phase_check(phase)
    if err:
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=err,
                   retry_safe=False,
                   extra={"hint": "phase is 'a' or 'b'."},
               )
    ambient_preset_id = body.get("ambient_preset_id")
    if not ambient_preset_id or not isinstance(ambient_preset_id, str):
        # Fallback: UI may omit preset if state was set via dropdown patch only.
        state_for_preset = h.app.state.read_state()
        ambient_preset_id = state_for_preset.get(f"phase_{phase}_ambient_preset_id")
    if not ambient_preset_id or not isinstance(ambient_preset_id, str):
        return h._send_error_v59(
                   400,
                   error_code="AMBIENT_PRESET_ID_IS_REQUIRED",
                   error_message="ambient_preset_id is required (string)",
                   retry_safe=False,
                   extra={"hint": "Pick from the ambient preset dropdown."},
               )
    if "/" in ambient_preset_id or "\\" in ambient_preset_id or ".." in ambient_preset_id:
        return h._send_error_v59(
                   400,
                   error_code="INVALID_AMBIENT_PRESET_ID",
                   error_message="invalid ambient_preset_id",
                   retry_safe=False,
               )
    # Resolve voice stem from state.
    state = h.app.state.read_state()
    if _phase_voice_stem_mirror_drift(state, phase):
        _phase_repair_voice_stem_mirror(h, phase)
        state = h.app.state.read_state()
    voice_stem_name = _phase_resolve_voice_stem_name(state, phase)
    stale_issues = [
        i for i in _phase_voice_stem_pin_issues(h, state, phase)
        if i["code"] == "STEM_PIN_STALE"
    ]
    if stale_issues:
        first = stale_issues[0]
        return h._send_error_v59(
            409,
            error_code="PHASE_VOICE_STEM_PIN_STALE",
            error_message=first["message"],
            retry_safe=False,
            extra={
                "code": PHASE_VOICE_STEM_PIN_DURABILITY_V1,
                "issues": stale_issues,
                "hint": "Regen Audio to repin before mixing.",
            },
        )
    if not voice_stem_name:
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=f"phase_{phase}_voice_stem_file not set in state",
                   retry_safe=False,
                   extra={"hint": "Run Regen Audio first to produce a voice stem."},
               )
    try:
        voice_stem_path = require_basename_under_dir(voice_stem_name, h.app.event_dir)
    except ValueError as exc:
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=str(exc),
                   retry_safe=False,
               )
    if not voice_stem_path.is_file():
        return h._send_error_v59(
                   404,
                   error_code="GENERIC_ERROR",
                   error_message=f"voice stem file not found: {voice_stem_name}",
                   retry_safe=False,
                   extra={"hint": "File may have been deleted. Re-run Regen Audio."},
               )
    # Resolve ambient preset (sound_library/ambient, then legacy ambient_library).
    ambient_path = _resolve_ambient_preset_path(h, ambient_preset_id)
    if ambient_path is None:
        return h._send_error_v59(
                   404,
                   error_code="GENERIC_ERROR",
                   error_message=f"ambient preset not found: {ambient_preset_id}.mp3",
                   retry_safe=False,
                   extra={
                       "hint": (
                           "Check Production/assets/sound_library/ambient/ "
                           "or Production/assets/ambient_library/."
                       ),
                   },
               )
    # Voice-source selection:
    # If a lipsync video exists, extract its audio track and use THAT as
    # the voice source — it is bit-exact what ByteDance animated against,
    # so the mixed output preserves perfect beak-sync timing. Running a
    # fresh silcomp here produces subtly different silence boundaries than
    # what was in the lipsync submission, which causes drift.
    # Fallback: use raw voice stem (used when lipsync hasn't run yet).
    # (Fix 2026-04-21 evening.)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    voice_extract_path = h.app.event_dir / f"_tmp_voice_extract_{phase}_{ts}.mp3"
    voice_for_mix_path = voice_stem_path  # default fallback
    cut_start, cut_end = _phase_voice_stem_cut_window(state, phase)
    lipsync_name_for_source = state.get(f"phase_{phase}_lipsync_file")
    lipsync_source_path: Path | None = None
    if lipsync_name_for_source:
        if "/" in lipsync_name_for_source or "\\" in lipsync_name_for_source or ".." in lipsync_name_for_source:
            lipsync_name_for_source = ""
        else:
            try:
                candidate = require_basename_under_dir(
                    lipsync_name_for_source, h.app.event_dir,
                )
            except ValueError:
                candidate = None
        if candidate is not None and candidate.is_file():
            lipsync_source_path = candidate
            try:
                ffmpeg_lipsync_in = require_media_under_project(
                    str(candidate), anchor=h.app.event_dir, extensions=MEDIA_EXTENSIONS,
                )
                subprocess.run([
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-i", ffmpeg_lipsync_in,
                    "-vn", "-c:a", "libmp3lame", "-b:a", "192k",
                    "-ac", "1", "-ar", "44100",
                    "-f", "mp3",
                    str(voice_extract_path),
                ], check=True, capture_output=True, timeout=60)
                voice_for_mix_path = voice_extract_path
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
                    OSError) as exc:
                # Non-fatal: fall back to voice stem + warn in logs.
                print(f"[mix_audio] extract-from-lipsync failed (falling back to voice_stem): {exc}")
                lipsync_source_path = None

    if lipsync_source_path is None and cut_end > cut_start + 0.001:
        try:
            tmp_trim = h.app.event_dir / f"_tmp_stem_trim_mix_{phase}_{ts}.mp3"
            voice_for_mix_path = _materialize_cut_out_audio(
                voice_stem_path, tmp_trim, cut_start, cut_end,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
                OSError, ValueError) as exc:
            return h._send_error_v59(
                400,
                error_code="STEM_TRIM_FAILED",
                error_message=f"stem cut failed: {exc}",
                retry_safe=False,
                extra={
                    "cut_start_s": cut_start,
                    "cut_end_s": cut_end,
                    "hint": "Reduce front/back trim values so at least 0.25s of audio remains.",
                },
            )

    out_name = f"phase_{phase}_mixed_{ts}.mp3"
    out_path = h.app.event_dir / out_name
    tmp = out_path.with_suffix(f".mp3.tmp.{os.getpid()}")
    try:
        # Voice loud, ambient bed quiet and clipped to voice duration.
        # normalize=0 keeps the explicit volume multipliers intact — default
        # amix normalize=1 divides each input by N, silently halving voice
        # to 0.5 and bed to 0.075 (2026-04-21 fix).
        filter_complex = (
            "[0:a]volume=1.0[voice];"
            "[1:a]volume=0.15[bed];"
            "[voice][bed]amix=inputs=2:duration=first:dropout_transition=2:normalize=0[mix]"
        )
        ffmpeg_voice_in = require_media_under_project(
            str(voice_for_mix_path), anchor=h.app.event_dir, extensions=MEDIA_EXTENSIONS,
        )
        ffmpeg_ambient_in = require_media_under_project(
            str(ambient_path), anchor=_data_root(h), extensions=MEDIA_EXTENSIONS,
        )
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", ffmpeg_voice_in,
            "-i", ffmpeg_ambient_in,
            "-filter_complex", filter_complex,
            "-map", "[mix]",
            "-c:a", "libmp3lame", "-b:a", "128k",
            "-ac", "1", "-ar", "44100",
            # Force mp3 format: tmp filename ends in .tmp.<PID> which ffmpeg
            # can't auto-detect as mp3 from the extension (2026-04-21 fix).
            "-f", "mp3",
            str(tmp),
        ]
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
        os.replace(tmp, out_path)
    except subprocess.CalledProcessError as exc:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass
        stderr = (exc.stderr or b"")[:400].decode("utf-8", errors="replace")
        return h._send_error_v59(
                   500,
                   error_code="GENERIC_ERROR",
                   error_message=f"ffmpeg amix failed (returncode={exc.returncode})",
                   retry_safe=True,
                   extra={"stderr": stderr, "hint": "Check ambient preset format (expect mp3, 44.1kHz)."},
               )
    except (subprocess.TimeoutExpired, OSError) as exc:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass
        return h._send_error_v59(
                   500,
                   error_code="GENERIC_ERROR",
                   error_message=f"ffmpeg mix error: {type(exc).__name__}: {exc}",
                   retry_safe=True,
                   extra={"hint": "Try a shorter voice stem or different ambient preset."},
               )
    finally:
        # Cleanup tmp voice-extract file regardless of outcome.
        try:
            voice_extract_path.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass
    try:
        duration = _ffprobe_duration(out_path)
    except (subprocess.CalledProcessError, ValueError, OSError):
        duration = 0.0
    mtime = int(os.path.getmtime(str(out_path)))

    def _apply(state, _p=phase, _n=out_name, _m=mtime, _pid=ambient_preset_id):
        state[f"phase_{_p}_mixed_audio_file"] = _n
        state[f"phase_{_p}_mixed_audio_mtime"] = _m
        state[f"phase_{_p}_ambient_preset_id"] = _pid
        state["_module_version"] = int(state.get("_module_version", 0) or 0) + 1
        return state["_module_version"]
    try:
        new_version = h.app.state.mutate_state(_apply)
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        return h._send_error_v59(
                   500,
                   error_code="GENERIC_ERROR",
                   error_message=f"mutate_state failed: {type(exc).__name__}: {exc}",
                   retry_safe=True,
                   extra={"hint": "State.json could not be persisted. File was written to disk."},
               )

    # Auto-remux: if a lipsync video exists for this phase, replace its
    # audio track with the newly mixed (voice + ambient bed) audio so the
    # "Preview Phase A/B Stitched" button reads the right thing. Added
    # 2026-04-21 after Kim hit the case where Phase A lipsync was baked
    # with voice-only audio (no bed) because the panel workflow is
    # lipsync-first, mix-later. ffmpeg -c:v copy keeps the video stream
    # bit-exact; only the audio track is replaced.
    remux_info = None
    state_after = h.app.state.read_state()
    lipsync_name = state_after.get(f"phase_{phase}_lipsync_file")
    if lipsync_name:
        if "/" not in lipsync_name and "\\" not in lipsync_name and ".." not in lipsync_name:
            try:
                lipsync_path = require_basename_under_dir(lipsync_name, h.app.event_dir)
            except ValueError:
                lipsync_path = None
        else:
            lipsync_path = None
        if lipsync_path is not None and lipsync_path.is_file():
            new_lipsync_name = f"phase_{phase}_lipsync_withbed_{ts}.mp4"
            new_lipsync_path = h.app.event_dir / new_lipsync_name
            try:
                ffmpeg_lipsync_in = require_media_under_project(
                    str(lipsync_path), anchor=h.app.event_dir, extensions=MEDIA_EXTENSIONS,
                )
                ffmpeg_mixed_in = require_media_under_project(
                    str(out_path), anchor=h.app.event_dir, extensions=MEDIA_EXTENSIONS,
                )
                subprocess.run([
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-i", ffmpeg_lipsync_in,
                    "-i", ffmpeg_mixed_in,
                    "-c:v", "copy",
                    "-map", "0:v:0",
                    "-map", "1:a:0",
                    "-shortest",
                    str(new_lipsync_path),
                ], check=True, capture_output=True, timeout=60)
                new_lipsync_mtime = int(os.path.getmtime(str(new_lipsync_path)))
                def _apply_lipsync(state, _p=phase, _n=new_lipsync_name, _m=new_lipsync_mtime):
                    state[f"phase_{_p}_lipsync_file"] = _n
                    state[f"phase_{_p}_lipsync_mtime"] = _m
                    state["_module_version"] = int(state.get("_module_version", 0) or 0) + 1
                    return state["_module_version"]
                new_version = h.app.state.mutate_state(_apply_lipsync)
                remux_info = {"lipsync_file": new_lipsync_name, "lipsync_mtime": new_lipsync_mtime}
            except subprocess.CalledProcessError as exc:
                # Non-fatal: the mix succeeded. Just log and move on.
                stderr = (exc.stderr or b"")[:200].decode("utf-8", errors="replace")
                print(f"[mix_audio] lipsync re-mux failed (non-fatal): rc={exc.returncode} stderr={stderr}")
            except (subprocess.TimeoutExpired, OSError) as exc:
                print(f"[mix_audio] lipsync re-mux failed (non-fatal): {type(exc).__name__}: {exc}")

    # Auto-assemble Phase A canonical — Phase B only path reaches here.
    canonical_info = None

    return h._send_json(200, {
        "status": "ok",
        "phase": phase,
        "file": out_name,
        "mtime": mtime,
        "remux": remux_info,
        "canonical": canonical_info,
        "duration_s": round(duration, 3),
        "ambient_preset_id": ambient_preset_id,
        "module_version": new_version,
    })


def _phase_a_tmp_has_resume_work(event_dir: Path) -> bool:
    tmp_dir = event_dir / "_tmp_phase_a_permanent"
    if not tmp_dir.is_dir():
        return False
    work = tmp_dir / "bytedance_work"
    return (
        work.is_dir()
        or bool(list(tmp_dir.glob("prepped_audio_*")))
        or bool(list(tmp_dir.glob("bytedance_raw_*.mp4")))
    )


def _spawn_phase_a_lipsync_worker(target, *args, **kwargs) -> bool:
    """Start Phase A lipsync worker thread if none is alive."""
    global _phase_a_lipsync_worker
    with _phase_a_lipsync_worker_lock:
        if _phase_a_lipsync_worker is not None and _phase_a_lipsync_worker.is_alive():
            return False
        _phase_a_lipsync_worker = threading.Thread(
            target=target,
            args=args,
            kwargs=kwargs,
            daemon=True,
            name="PhaseALipsyncWorker",
        )
        _phase_a_lipsync_worker.start()
        return True


def sweep_phase_a_lipsync_resume(state_mgr) -> None:
    """Clear legacy Phase A ``running`` rows after Avatar wire (no ByteDance worker).

    Avatar Pro module lipsync uses ``polling`` + ``sweep_phase_module_lipsync_polls``.
    Legacy ``running`` + tmp work from pre-Avatar jobs is cleared so operators resubmit.
    """
    snap = state_mgr.read_state()
    if snap.get("phase_a_lipsync_status") != "running":
        return

    event_dir = Path(state_mgr.event_dir)
    started = snap.get("phase_a_lipsync_started_at")
    stale = not isinstance(started, (int, float)) or (
        time.time() - float(started) > PHASE_A_LIPSYNC_RESTART_ORPHAN_SEC
    )
    has_tmp = _phase_a_tmp_has_resume_work(event_dir)
    if not stale and has_tmp:
        print(
            "[phase_a_lipsync-resume] legacy ByteDance tmp work detected — "
            "clear when stale; use Send for Avatar Pro for new runs",
            flush=True,
        )
        return

    def _clear_legacy(st):
        st["phase_a_lipsync_status"] = (
            "error: legacy_bytedance_running: resubmit with Avatar Pro"
        )
        for key in (
            "phase_a_lipsync_started_at",
            "phase_a_lipsync_pending_output",
            "phase_a_lipsync_pending_audio",
        ):
            st.pop(key, None)
        nested = st.setdefault("phase_a", {})
        if isinstance(nested, dict):
            nested["phase_a_lipsync_status"] = st["phase_a_lipsync_status"]
            for key in (
                "phase_a_lipsync_started_at",
                "phase_a_lipsync_pending_output",
                "phase_a_lipsync_pending_audio",
            ):
                nested.pop(key, None)
        return st.get("_module_version", 0)

    state_mgr.mutate_state(_clear_legacy)
    print(
        "[phase_a_lipsync-resume] cleared legacy running row — operator resubmits via Avatar Pro",
        flush=True,
    )


def handle_phase_a_lipsync(h, body: dict) -> None:
    """POST /api/phase_a/lipsync — Kling V2 Avatar Pro for Arlo (wizard-desk still + stem).

    Category parity with Phase B: submit → persistent poll → delivery encode.
    See Production/docs/TECH_SPEC_PHASE_A_AVATAR_PRO_WIRE_v1.md
    """
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return

    if h.app.client is None:
        return h._send_error_v59(
            500,
            error_code="WAVESPEED_NOT_CONFIGURED",
            error_message="WaveSpeed client not configured (missing API key)",
            retry_safe=True,
            extra={"hint": "Populate API_KEYS_MASTER.md wavespeed entry."},
        )

    phase = "a"
    state = h.app.state.read_state()
    from phase_lipsync_job_contract import phase_lipsync_job_busy

    existing_status = state.get(f"phase_{phase}_lipsync_status")
    existing_tid = state.get(f"phase_{phase}_lipsync_task_id")
    if phase_lipsync_job_busy(existing_status, existing_tid):
        return h._send_json(202, {
            "ok": True,
            "status": "already_polling",
            "task_id": existing_tid,
            "phase": phase,
            "message": "Lipsync already in progress — auto-updating when done.",
        })

    # Clear legacy ByteDance ``running`` rows (no worker thread after Avatar wire).
    if state.get("phase_a_lipsync_status") == "running":
        def _clear_legacy_running(st):
            st["phase_a_lipsync_status"] = (
                "error: legacy_bytedance_running: resubmit with Avatar Pro"
            )
            for key in (
                "phase_a_lipsync_started_at",
                "phase_a_lipsync_pending_output",
                "phase_a_lipsync_pending_audio",
            ):
                st.pop(key, None)
            nested = st.setdefault("phase_a", {})
            if isinstance(nested, dict):
                nested["phase_a_lipsync_status"] = st["phase_a_lipsync_status"]
                for key in (
                    "phase_a_lipsync_started_at",
                    "phase_a_lipsync_pending_output",
                    "phase_a_lipsync_pending_audio",
                ):
                    nested.pop(key, None)
            return st.get("_module_version", 0)

        h.app.state.mutate_state(_clear_legacy_running)
        state = h.app.state.read_state()

    preflight_err = _phase_preflight_voice_stem_for_lipsync(h, state, phase)
    if preflight_err is not None:
        return preflight_err
    state = h.app.state.read_state()

    audio_name = _phase_resolve_voice_stem_name(state, phase) or state.get("phase_a_mixed_audio_file")
    if not audio_name:
        return h._send_error_v59(
            400,
            error_code="GENERIC_ERROR",
            error_message="phase_a_voice_stem_file unset",
            retry_safe=False,
            extra={"hint": "Run Regen Audio first."},
        )
    audio_path = h.app.event_dir / audio_name
    if not audio_path.is_file():
        return h._send_error_v59(
            404,
            error_code="GENERIC_ERROR",
            error_message=f"audio file not found: {audio_name}",
            retry_safe=False,
        )

    from phase_a_avatar_lipsync import (  # noqa: WPS433
        ARLO_WIZARD_DESK_PROMPT,
        PHASE_A_LIPSYNC_METHOD_AVATAR,
        PHASE_A_LIPSYNC_ROUTE_SINGLE_FULL_STEM,
        estimate_avatar_pro_usd,
        resolve_phase_a_arlo_avatar_still,
    )

    production_root = h.app.event_dir.parent
    try:
        still_path = resolve_phase_a_arlo_avatar_still(h.app.event_dir, production_root)
    except FileNotFoundError as exc:
        return h._send_error_v59(
            404,
            error_code="PHASE_A_AVATAR_STILL_MISSING",
            error_message=str(exc),
            retry_safe=False,
            extra={
                "hint": (
                    "Place canonical Arlo still under "
                    "Production/NEW STYLE CHARACTERS/ARLO/ or event phase_a_arlo_canonical_still.png."
                ),
            },
        )

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    try:
        audio_for_lipsync, audio_duration = _apply_phase_audio_trim(
            h, audio_path, phase, state, ts,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
            OSError, ValueError) as exc:
        return h._send_error_v59(
            400,
            error_code="STEM_TRIM_FAILED",
            error_message=f"stem trim failed: {exc}",
            retry_safe=False,
            extra={"hint": "Adjust stem trim front/back seconds before Send for Avatar Pro."},
        )

    estimated_cost = estimate_avatar_pro_usd(audio_duration)
    spend = h.app.state.read_spend()
    if spend["budget_remaining"] < estimated_cost and spend["overrides"] == 0:
        return h._send_error_v59(
            402,
            error_code="BUDGET_EXCEEDED_FOR_LIP_SYNC",
            error_message="budget exceeded for Avatar Pro lipsync",
            retry_safe=False,
            extra={
                "budget_remaining": spend["budget_remaining"],
                "cost": round(estimated_cost, 2),
                "audio_duration_s": round(audio_duration, 3),
                "hint": "Raise budget via /api/budget/override or shorten the voice stem.",
            },
        )

    out_name = f"phase_{phase}_lipsync_{ts}.mp4"
    lipsync_client = LipSyncClient(h.app.client.api_key)
    try:
        task_id = lipsync_client.submit_avatar_pro(
            still_path,
            audio_for_lipsync,
            ARLO_WIZARD_DESK_PROMPT,
        )
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        return h._send_error_v59(
            502,
            error_code="PHASE_A_AVATAR_SUBMIT_FAILED",
            error_message=f"Avatar Pro submit failed: {type(exc).__name__}: {exc}",
            retry_safe=True,
            extra={
                "hint": f"{str(exc)[:200]} — check server stderr, WaveSpeed key, still/audio on disk.",
            },
        )

    def _apply_polling(
        state,
        _p=phase,
        _tid=task_id,
        _out=out_name,
        _still=still_path.name,
        _cost=estimated_cost,
        _dur=audio_duration,
    ):
        state[f"phase_{_p}_lipsync_status"] = "polling"
        state[f"phase_{_p}_lipsync_task_id"] = _tid
        state[f"phase_{_p}_lipsync_pending_out"] = _out
        state[f"phase_{_p}_lipsync_method"] = PHASE_A_LIPSYNC_METHOD_AVATAR
        state[f"phase_{_p}_lipsync_route"] = PHASE_A_LIPSYNC_ROUTE_SINGLE_FULL_STEM
        state[f"phase_{_p}_lipsync_estimated_cost_usd"] = round(_cost, 4)
        state[f"phase_{_p}_avatar_still_file"] = _still
        state[f"phase_{_p}_lipsync_audio_duration_s"] = round(_dur, 3)
        state.pop(f"phase_{_p}_lipsync_started_at", None)
        state.pop(f"phase_{_p}_lipsync_pending_output", None)
        state.pop(f"phase_{_p}_lipsync_pending_audio", None)
        state.pop(f"phase_{_p}_lipsync_qa_dir", None)
        nested = state.setdefault("phase_a", {})
        if isinstance(nested, dict):
            nested[f"phase_{_p}_lipsync_status"] = "polling"
            nested[f"phase_{_p}_lipsync_task_id"] = _tid
        state["_module_version"] = int(state.get("_module_version", 0) or 0) + 1
        return state["_module_version"]

    try:
        h.app.state.mutate_state(_apply_polling)
    except Exception:  # noqa: BLE001
        pass

    print(
        f"[phase_a_lipsync] Avatar Pro submitted task_id={task_id} "
        f"still={still_path.name} audio={audio_duration:.1f}s "
        f"est=${estimated_cost:.2f} → {out_name}",
        flush=True,
    )

    return h._send_json(202, {
        "ok": True,
        "status": "submitted",
        "task_id": task_id,
        "phase": phase,
        "audio_duration_s": round(audio_duration, 3),
        "lipsync_method": PHASE_A_LIPSYNC_METHOD_AVATAR,
        "lipsync_route": PHASE_A_LIPSYNC_ROUTE_SINGLE_FULL_STEM,
        "estimated_cost_usd": round(estimated_cost, 2),
        "avatar_still_file": still_path.name,
        "message": (
            "Avatar Pro is processing (~10–50 min for full Phase A stem). "
            "The storyboard will auto-update when done."
        ),
    })


def handle_phase_b_lipsync(h, body: dict)-> None:

    """POST /api/phase_b/lipsync

    Phase B: Kling V2 Avatar Pro — canonical Cedric still + voice stem + frozen-BG prompt.
    Phase A: delegated to handle_phase_a_lipsync.

    Submit returns 202; LipsyncPollingThread + sweep_phase_module_lipsync_polls finalize.
    """
    # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return

    # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — capture pin at entry; terminal writes assert via _check_event_pin.
    _pin = {
        "pinned_generation": h.app.event_generation,
        "pinned_event_dir": h.app.event_dir,
        "pinned_video_role": (body or {}).get("scope_video_role", "intro"),
        "_handler": '_handle_phase_b_lipsync',
    }

    if h.app.client is None:
        return h._send_error_v59(
                   500,
                   error_code="WAVESPEED_NOT_CONFIGURED",
                   error_message="WaveSpeed client not configured (missing API key)",
                   retry_safe=True,
                   extra={"hint": "Populate API_KEYS_MASTER.md wavespeed entry."},
               )
    phase = (body.get("phase") or "").strip().lower()
    if phase == "a":
        return handle_phase_a_lipsync(h, body)
    err = h._phase_check(phase)
    if err:
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=err,
                   retry_safe=False,
                   extra={"hint": "phase is 'a' or 'b'."},
               )
    # Resolve audio source: prefer mixed_audio_file, fallback to voice_stem.
    state = h.app.state.read_state()
    from phase_lipsync_job_contract import phase_lipsync_job_busy

    existing_status = state.get(f"phase_{phase}_lipsync_status")
    existing_tid = state.get(f"phase_{phase}_lipsync_task_id")
    if phase_lipsync_job_busy(existing_status, existing_tid):
        return h._send_json(202, {
            "ok": True,
            "status": "already_polling",
            "task_id": existing_tid,
            "phase": phase,
            "message": "Lipsync already in progress — auto-updating when done.",
        })
    audio_name = (state.get(f"phase_{phase}_mixed_audio_file")
                  or state.get(f"phase_{phase}_voice_stem_file"))
    if not audio_name:
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=f"phase_{phase}_mixed_audio_file and phase_{phase}_voice_stem_file both unset",
                   retry_safe=False,
                   extra={"hint": "Run Regen Audio (and optionally Mix Audio) first."},
               )
    audio_path = h.app.event_dir / audio_name
    if not audio_path.is_file():
        return h._send_error_v59(
                   404,
                   error_code="GENERIC_ERROR",
                   error_message=f"audio file not found: {audio_name}",
                   retry_safe=False,
                   extra={"hint": "File may have been deleted. Re-run Regen Audio."},
               )

    from phase_b_avatar_lipsync import (  # noqa: WPS433
        PHASE_B_LIPSYNC_METHOD_AVATAR,
        PHASE_B_LIPSYNC_ROUTE_SINGLE_FULL_STEM,
        STATIC_BG_PROMPT,
        estimate_avatar_pro_usd,
        resolve_phase_b_cedric_still,
    )

    production_root = h.app.event_dir.parent
    try:
        still_path = resolve_phase_b_cedric_still(production_root)
    except FileNotFoundError as exc:
        return h._send_error_v59(
            404,
            error_code="PHASE_B_AVATAR_STILL_MISSING",
            error_message=str(exc),
            retry_safe=False,
            extra={"hint": "Place canonical Cedric still under Production/NEW STYLE CHARACTERS/CEDRIC/."},
        )

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    try:
        audio_for_lipsync, audio_duration = _apply_phase_audio_trim(
            h, audio_path, phase, state, ts,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
            OSError, ValueError) as exc:
        return h._send_error_v59(
            400,
            error_code="STEM_TRIM_FAILED",
            error_message=f"stem trim failed: {exc}",
            retry_safe=False,
            extra={"hint": "Adjust stem trim front/back seconds before Send for Lipsync."},
        )

    estimated_cost = estimate_avatar_pro_usd(audio_duration)
    spend = h.app.state.read_spend()
    if spend["budget_remaining"] < estimated_cost and spend["overrides"] == 0:
        return h._send_error_v59(
            402,
            error_code="BUDGET_EXCEEDED_FOR_LIP_SYNC",
            error_message="budget exceeded for Avatar Pro lipsync",
            retry_safe=False,
            extra={
                "budget_remaining": spend["budget_remaining"],
                "cost": round(estimated_cost, 2),
                "audio_duration_s": round(audio_duration, 3),
                "hint": "Raise budget via /api/budget/override or shorten the voice stem.",
            },
        )

    out_name = f"phase_{phase}_lipsync_{ts}.mp4"
    lipsync_client = LipSyncClient(h.app.client.api_key)
    try:
        task_id = lipsync_client.submit_avatar_pro(
            still_path,
            audio_for_lipsync,
            STATIC_BG_PROMPT,
        )
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        return h._send_error_v59(
            502,
            error_code="PHASE_B_AVATAR_SUBMIT_FAILED",
            error_message=f"Avatar Pro submit failed: {type(exc).__name__}: {exc}",
            retry_safe=True,
            extra={
                "hint": f"{str(exc)[:200]} — check server stderr, WaveSpeed key, still/audio on disk.",
            },
        )

    def _apply_polling(
        state,
        _p=phase,
        _tid=task_id,
        _out=out_name,
        _still=still_path.name,
        _cost=estimated_cost,
        _dur=audio_duration,
    ):
        state[f"phase_{_p}_lipsync_status"] = "polling"
        state[f"phase_{_p}_lipsync_task_id"] = _tid
        state[f"phase_{_p}_lipsync_pending_out"] = _out
        state[f"phase_{_p}_lipsync_method"] = PHASE_B_LIPSYNC_METHOD_AVATAR
        state[f"phase_{_p}_lipsync_route"] = PHASE_B_LIPSYNC_ROUTE_SINGLE_FULL_STEM
        state[f"phase_{_p}_lipsync_estimated_cost_usd"] = round(_cost, 4)
        state[f"phase_{_p}_avatar_still_file"] = _still
        state[f"phase_{_p}_lipsync_audio_duration_s"] = round(_dur, 3)
        state.pop(f"phase_{_p}_lipsync_segmented_timeline", None)
        state.pop("phase_b_avatar_segmented", None)
        state.pop(f"phase_{_p}_lipsync_segmented", None)
        state["_module_version"] = int(state.get("_module_version", 0) or 0) + 1
        return state["_module_version"]

    try:
        h.app.state.mutate_state(_apply_polling)
    except Exception:  # noqa: BLE001
        pass  # non-fatal — polling state is cosmetic

    print(
        f"[phase_b_lipsync] Avatar Pro submitted task_id={task_id} "
        f"still={still_path.name} audio={audio_duration:.1f}s "
        f"est=${estimated_cost:.2f} → {out_name}",
        flush=True,
    )

    return h._send_json(202, {
        "ok": True,
        "status": "submitted",
        "task_id": task_id,
        "phase": phase,
        "audio_duration_s": round(audio_duration, 3),
        "lipsync_method": PHASE_B_LIPSYNC_METHOD_AVATAR,
        "lipsync_route": "single_full_stem_v1",
        "estimated_cost_usd": round(estimated_cost, 2),
        "avatar_still_file": still_path.name,
        "message": (
            "Avatar Pro is processing (~10–50 min for full meditation). "
            "The storyboard will auto-update when done."
        ),
    })


def _write_phase_b_lipsync_complete(
    app,
    *,
    phase: str,
    out_path: Path,
    out_name: str,
    base_clip_id: str | None,
    lipsync_method: str | None = None,
    spend_usd: float | None = None,
    avatar_still_file: str | None = None,
) -> None:
    """Terminal success write shared by bg thread + persistent poller."""
    from phase_module_lipsync_delivery import finalize_phase_module_lipsync_delivery  # noqa: PLC0415
    from phase_a_avatar_lipsync import (  # noqa: WPS433
        PHASE_A_LIPSYNC_METHOD_AVATAR,
        PHASE_A_LIPSYNC_ROUTE_SINGLE_FULL_STEM,
    )
    from phase_b_avatar_lipsync import (  # noqa: WPS433
        PHASE_B_LIPSYNC_METHOD_AVATAR,
        PHASE_B_LIPSYNC_ROUTE_SINGLE_FULL_STEM,
    )

    delivery_meta = finalize_phase_module_lipsync_delivery(out_path, sharpen=True)
    print(
        f"[phase_{phase}_lipsync] delivery encode ✓ "
        f"{delivery_meta.get('raw_width')}x{delivery_meta.get('raw_height')} → "
        f"{delivery_meta.get('width')}x{delivery_meta.get('height')} "
        f"@ {delivery_meta.get('bitrate_bps', 0):,} bps "
        f"({delivery_meta.get('delivery_profile')})",
        flush=True,
    )
    charge = spend_usd if spend_usd is not None else COST_PER_LIPSYNC
    app.state.add_spend("lipsync", charge)
    mtime = int(os.path.getmtime(str(out_path)))

    def _apply(
        state,
        _p=phase,
        _n=out_name,
        _m=mtime,
        _bid=base_clip_id,
        _meta=delivery_meta,
        _meth=lipsync_method,
        _still=avatar_still_file,
    ):
        state[f"phase_{_p}_lipsync_file"] = _n
        state[f"phase_{_p}_lipsync_mtime"] = _m
        state[f"phase_{_p}_lipsync_status"] = "done"
        state[f"phase_{_p}_lipsync_requires_regen"] = False
        state[f"phase_{_p}_lipsync_delivery_profile"] = _meta.get("delivery_profile")
        state[f"phase_{_p}_lipsync_delivery_recipe"] = _meta.get("delivery_recipe")
        if _meth:
            state[f"phase_{_p}_lipsync_method"] = _meth
        if _meth in (PHASE_A_LIPSYNC_METHOD_AVATAR, PHASE_B_LIPSYNC_METHOD_AVATAR):
            route = (
                PHASE_A_LIPSYNC_ROUTE_SINGLE_FULL_STEM
                if _p == "a"
                else PHASE_B_LIPSYNC_ROUTE_SINGLE_FULL_STEM
            )
            state[f"phase_{_p}_lipsync_route"] = route
            state.pop(f"phase_{_p}_lipsync_segmented_timeline", None)
            state.pop("phase_b_avatar_segmented", None)
            state.pop(f"phase_{_p}_lipsync_segmented", None)
        if _still:
            state[f"phase_{_p}_avatar_still_file"] = _still
        nested = state.setdefault(f"phase_{_p}", {})
        if isinstance(nested, dict):
            nested[f"phase_{_p}_lipsync_file"] = _n
            nested[f"phase_{_p}_lipsync_mtime"] = _m
            nested[f"phase_{_p}_lipsync_status"] = "done"
            nested[f"phase_{_p}_lipsync_requires_regen"] = False
            if _meth:
                nested[f"phase_{_p}_lipsync_method"] = _meth
        state.pop(f"phase_{_p}_lipsync_task_id", None)
        state.pop(f"phase_{_p}_lipsync_pending_out", None)
        state.pop(f"phase_{_p}_lipsync_estimated_cost_usd", None)
        state.pop(f"phase_{_p}_lipsync_audio_duration_s", None)
        if _bid and _meth not in (PHASE_A_LIPSYNC_METHOD_AVATAR, PHASE_B_LIPSYNC_METHOD_AVATAR):
            key = f"phase_{_p}_cedric_base_clip_id" if _p == "b" else f"phase_{_p}_empty_desk_bg_id"
            state[key] = _bid
        state["_module_version"] = int(state.get("_module_version", 0) or 0) + 1
        return state["_module_version"]

    app.state.mutate_state(_apply)


def sweep_phase_module_lipsync_polls(state, client) -> None:
    """Poll in-flight phase A/B module Avatar Pro jobs — survives server restarts."""
    for phase in ("a", "b"):
        _sweep_one_phase_module_lipsync_poll(state, client, phase)


def _sweep_one_phase_module_lipsync_poll(state, client, phase: str) -> None:
    """Poll one phase module lipsync row when status=polling."""
    snap = state.read_state()
    status = snap.get(f"phase_{phase}_lipsync_status")
    task_id = snap.get(f"phase_{phase}_lipsync_task_id")
    if status != "polling" or not task_id:
        return
    try:
        result = client.poll(task_id)
    except Exception as exc:  # noqa: BLE001
        print(
            f"[phase_{phase}_lipsync-poller] {task_id[:12]}… transport error "
            f"({type(exc).__name__}: {exc!r}); will retry",
            flush=True,
        )
        return
    poll_status = (result.get("status") or "").lower()
    outputs = result.get("outputs") or []
    print(
        f"[phase_{phase}_lipsync-poller] {task_id[:12]}… status={poll_status!r} "
        f"outputs={len(outputs)}",
        flush=True,
    )
    if poll_status == "completed" and outputs:
        pending = str(snap.get(f"phase_{phase}_lipsync_pending_out") or "").strip()
        if pending:
            out_name = pending
        else:
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            out_name = f"phase_{phase}_lipsync_{ts}.mp4"
        out_path = state.event_dir / out_name
        base_clip_id = snap.get(f"phase_{phase}_cedric_base_clip_id")
        lipsync_method = snap.get(f"phase_{phase}_lipsync_method")
        spend_usd = snap.get(f"phase_{phase}_lipsync_estimated_cost_usd")
        avatar_still = snap.get(f"phase_{phase}_avatar_still_file")
        try:
            if isinstance(spend_usd, str):
                spend_usd = float(spend_usd)
            elif spend_usd is not None:
                spend_usd = float(spend_usd)
        except (TypeError, ValueError):
            spend_usd = None
        try:
            LipSyncClient(client.api_key).download(outputs[0], out_path)
        except Exception as exc:  # noqa: BLE001
            print(
                f"[phase_{phase}_lipsync-poller] download failed ({exc}); will retry",
                flush=True,
            )
            return
        if not out_path.is_file():
            print(
                f"[phase_{phase}_lipsync-poller] completed but file missing: {out_path}",
                flush=True,
            )
            return
        # Reconstruct minimal app shim for shared writer (add_spend + mutate_state).
        class _AppShim:
            pass

        shim = _AppShim()
        shim.state = state
        _write_phase_b_lipsync_complete(
            shim,
            phase=phase,
            out_path=out_path,
            out_name=out_name,
            base_clip_id=base_clip_id,
            lipsync_method=lipsync_method,
            spend_usd=spend_usd,
            avatar_still_file=avatar_still,
        )
        print(
            f"[phase_{phase}_lipsync-poller] ✓ recovered → {out_name} "
            f"({out_path.stat().st_size} bytes)",
            flush=True,
        )
    elif poll_status in ("failed", "error"):
        err = result.get("raw", {}).get("error", "unknown")

        def _apply_err(st, _p=phase, _e=err):
            st[f"phase_{_p}_lipsync_status"] = f"error: {str(_e)[:120]}"
            st.pop(f"phase_{_p}_lipsync_task_id", None)
            st.pop(f"phase_{_p}_lipsync_pending_out", None)
            return st

        state.mutate_state(_apply_err)


def _phase_load_overlay_helpers():
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "credentials_lib"))
        from ffmpeg_stitch import (  # type: ignore
            render_watercolor_overlay,
            resolve_watercolor_asset,
            WATERCOLOR_OVERLAY_RECIPE_HASH,
            PREVIEW_OVERLAY_ENCODER_ARGS,
            lru_cleanup,
        )
    except ImportError as exc:
        raise RuntimeError(f"lib/ffmpeg_stitch import failed: {exc}") from exc
    return (
        render_watercolor_overlay,
        resolve_watercolor_asset,
        WATERCOLOR_OVERLAY_RECIPE_HASH,
        PREVIEW_OVERLAY_ENCODER_ARGS,
        lru_cleanup,
    )


def _phase_ensure_overlay_mp4(
    h,
    phase: str,
    *,
    base_video_path: Path | None = None,
    base_video_label: str | None = None,
) -> tuple[Path, str]:
    """Return cached or freshly rendered phase MP4 with watercolor overlays baked in."""
    (
        render_watercolor_overlay,
        resolve_watercolor_asset,
        WATERCOLOR_OVERLAY_RECIPE_HASH,
        PREVIEW_OVERLAY_ENCODER_ARGS,
        lru_cleanup,
    ) = _phase_load_overlay_helpers()

    err = h._phase_check(phase)
    if err:
        raise ValueError(err)

    state = h.app.state.read_state()
    lipsync_name = state.get(f"phase_{phase}_lipsync_file")
    if not lipsync_name:
        raise ValueError(f"phase_{phase}_lipsync_file not set in state")
    if "/" in lipsync_name or "\\" in lipsync_name or ".." in lipsync_name:
        raise ValueError("invalid phase lipsync filename in state")

    lipsync_path = require_basename_under_dir(lipsync_name, h.app.event_dir)
    if not lipsync_path.is_file():
        raise FileNotFoundError(f"lipsync file not found on disk: {lipsync_name}")
    lipsync_path = lipsync_path.resolve()

    if base_video_path is not None:
        base_path = Path(base_video_path).resolve()
        if not base_path.is_file():
            raise FileNotFoundError(f"base video not found on disk: {base_path}")
        render_base_path = base_path
        render_base_label = base_video_label or base_path.name
    else:
        render_base_path = lipsync_path
        render_base_label = lipsync_name

    cues_json = state.get(f"phase_{phase}_watercolor_cues_json") or "[]"
    try:
        cues = json.loads(cues_json)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"phase_{phase}_watercolor_cues_json invalid: {exc}") from exc
    if not isinstance(cues, list):
        raise ValueError(f"phase_{phase}_watercolor_cues_json is not a list")

    library_dir = event_watercolors_dir(h.app.event_dir)
    missing_assets = []
    for i, cue in enumerate(cues):
        try:
            resolve_watercolor_asset(
                library_dir, cue.get("key") or "", cue.get("cue_type") or "png",
            )
        except FileNotFoundError as exc:
            missing_assets.append({"cue_index": i, "error": str(exc)})
    if missing_assets:
        raise FileNotFoundError(f"watercolor assets missing: {missing_assets}")

    frame_x = h._PHASE_FRAME_X[phase]
    frame_y = h._PHASE_FRAME_Y
    frame_max_w = h._PHASE_FRAME_MAX_W[phase]
    frame_max_h = h._PHASE_FRAME_MAX_H[phase]

    render_base_mtime = os.path.getmtime(str(render_base_path))
    normalized_cues_json = _v2_validate_watercolor_cues_json(cues_json)
    from phase_module_lipsync_delivery import PHASE_MODULE_LIPSYNC_DELIVERY_RECIPE_V1  # noqa: PLC0415

    hash_parts = [
        "recipe:v3",
        f"wc_overlay:{WATERCOLOR_OVERLAY_RECIPE_HASH}",
        f"lipsync_delivery:{PHASE_MODULE_LIPSYNC_DELIVERY_RECIPE_V1}",
        f"phase:{phase}",
        f"frame_x:{frame_x}",
        f"frame_y:{frame_y}",
        f"frame_max_w:{frame_max_w}",
        f"frame_max_h:{frame_max_h}",
        f"base:{render_base_label}:{render_base_mtime:.6f}",
        f"lipsync:{lipsync_name}:{os.path.getmtime(str(lipsync_path)):.6f}",
        f"voice_stem_mtime:{state.get(f'phase_{phase}_voice_stem_mtime', 0)}",
        f"ambient:{state.get(f'phase_{phase}_ambient_preset_id', '')}",
        f"mixed_mtime:{state.get(f'phase_{phase}_mixed_audio_mtime', 0)}",
        f"base_clip:{state.get('phase_b_cedric_base_clip_id' if phase == 'b' else 'phase_a_empty_desk_bg_id', '')}",
        f"cues:{hashlib.sha256(normalized_cues_json.encode('utf-8')).hexdigest()[:16]}",
    ]
    cache_hash = hashlib.sha256(";".join(hash_parts).encode("utf-8")).hexdigest()

    preview_dir = h.app.event_dir / "preview" / f"phase_{phase}"
    preview_dir.mkdir(parents=True, exist_ok=True)
    final_path = preview_dir / f"phase_{phase}_preview_{cache_hash}.mp4"
    lock_path = preview_dir / ".lock"

    import fcntl  # noqa: PLC0415
    lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.lockf(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError) as exc:
            raise RuntimeError("another phase preview is generating") from exc

        if final_path.is_file():
            lru_cleanup(preview_dir)
            return final_path, cache_hash

        render_watercolor_overlay(
            base_video_path=render_base_path,
            cues=cues,
            frame_x=frame_x,
            frame_y=frame_y,
            output_path=final_path,
            library_dir=library_dir,
            chromakey_for_video=True,
            frame_max_w=frame_max_w,
            frame_max_h=frame_max_h,
            encoder_args=PREVIEW_OVERLAY_ENCODER_ARGS,
        )
        lru_cleanup(preview_dir)
        return final_path, cache_hash
    finally:
        try:
            fcntl.lockf(lock_fd, fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            os.close(lock_fd)
        except OSError:
            pass


def handle_phase_export_stitcher(h, body: dict) -> None:
    """POST /api/phase/export_stitcher — bake watercolors and upsert stitch slot."""
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return

    phase = (body.get("phase") or "").strip().lower()
    err = h._phase_check(phase)
    if err:
        return h._send_error_v59(
            400,
            error_code="GENERIC_ERROR",
            error_message=err,
            retry_safe=False,
            extra={"hint": "phase is 'a' or 'b'."},
        )

    event_id = h.app.event_dir.name
    slot_key = f"phase_{phase}"
    state = h.app.state.read_state()
    overlay_base: Path | None = None
    overlay_base_label: str | None = None

    if phase == "a":
        from phase_a_stitch_lib import resolve_phase_a_raw_lipsync  # noqa: PLC0415

        if not resolve_phase_a_raw_lipsync(h.app.event_dir, state):
            return h._send_error_v59(
                400,
                error_code="GENERIC_ERROR",
                error_message="phase_a_lipsync_file not set in state",
                retry_safe=False,
                extra={"hint": "Run Send for Lipsync first."},
            )
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        try:
            canonical = h._auto_assemble_phase_a_stitched(ts)
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            return h._send_error_v59(
                500,
                error_code="GENERIC_ERROR",
                error_message=f"Phase A normalize failed: {exc}",
                retry_safe=True,
            )
        if not canonical or not canonical.get("file"):
            return h._send_error_v59(
                404,
                error_code="GENERIC_ERROR",
                error_message="missing raw lipsync input for Phase A export",
                retry_safe=False,
            )
        stitched_name = canonical["file"]
        if "/" in stitched_name or "\\" in stitched_name or ".." in stitched_name:
            return h._send_error_v59(
                400,
                error_code="INVALID_PHASE_STITCHED_FILENAME",
                error_message="invalid phase_a_stitched filename in state",
                retry_safe=False,
            )
        overlay_base = (h.app.event_dir / stitched_name).resolve()
        overlay_base_label = stitched_name

    try:
        final_path, _cache_hash = _phase_ensure_overlay_mp4(
            h,
            phase,
            base_video_path=overlay_base,
            base_video_label=overlay_base_label,
        )
    except ValueError as exc:
        return h._send_error_v59(
            400, error_code="GENERIC_ERROR", error_message=str(exc), retry_safe=False,
        )
    except FileNotFoundError as exc:
        return h._send_error_v59(
            404, error_code="GENERIC_ERROR", error_message=str(exc), retry_safe=False,
        )
    except RuntimeError as exc:
        return h._send_error_v59(
            409, error_code="ANOTHER_PHASE_PREVIEW_IS_GENERATING",
            error_message=str(exc), retry_safe=False,
        )
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or b"")[:600].decode("utf-8", errors="replace")
        return h._send_error_v59(
            500, error_code="GENERIC_ERROR",
            error_message=f"ffmpeg overlay failed (returncode={exc.returncode})",
            retry_safe=True, extra={"stderr": stderr},
        )
    root = h._stitch_project_root()
    video_rel = str(final_path.resolve().relative_to(root))
    overlay_baked = True

    try:
        h._stitch_resolve_path(video_rel)
    except ValueError:
        return h._send_error_v59(
            403,
            error_code="VIDEO_PATH_OUTSIDE_PROJECT_ROOT",
            error_message="export video path outside project root",
            retry_safe=False,
        )

    from server_handlers.stitch_editor import (  # noqa: PLC0415
        STITCH_SLOT_EXPORT_FULL_MEDIA_V1,
        STITCH_SLOT_MEDIA_LINEAGE_DURABILITY_V1,
        STITCH_SLOT_VIDEO_LINEAGE_V1,
        stitch_upsert_event_slot,
    )

    try:
        job_name, export_dur_ms, export_warnings, _playback = stitch_upsert_event_slot(
            h,
            event_id,
            slot_key,
            {
                "video_path": video_rel,
                "overlay_baked": overlay_baked,
                "source": f"phase_{phase}_export",
            },
            operator_export=True,
        )
    except ValueError as exc:
        return h._send_error_v59(
            409,
            error_code="STITCH_SLOT_EXPORT_MEDIA_BLOCKED",
            error_message=str(exc),
            retry_safe=False,
            extra={
                "code": STITCH_SLOT_MEDIA_LINEAGE_DURABILITY_V1,
                "export_full_media": STITCH_SLOT_EXPORT_FULL_MEDIA_V1,
            },
        )

    if any("kept existing export" in (w or "") for w in (export_warnings or [])):
        return h._send_error_v59(
            409,
            error_code="STITCH_EXPORT_NOT_APPLIED",
            error_message=(
                f"{slot_key}: stitch slot was not updated "
                "(incoming export not newer than stored video)"
            ),
            retry_safe=False,
            extra={
                "code": STITCH_SLOT_VIDEO_LINEAGE_V1,
                "warnings": export_warnings,
                "video_path": video_rel,
            },
        )

    return h._send_json(200, {
        "ok": True,
        "job_name": job_name,
        "slot_key": slot_key,
        "video_path": video_rel,
        "overlay_baked": overlay_baked,
        "video_dur_ms": export_dur_ms,
        "warnings": export_warnings,
        "code": STITCH_SLOT_MEDIA_LINEAGE_DURABILITY_V1,
        "export_full_media": STITCH_SLOT_EXPORT_FULL_MEDIA_V1,
    })


def ensure_phase_b_stitch_slot_for_bake(h) -> dict:
    """STITCH_BAKE_PHASE_B_DELIVERY_V1 — delivery lipsync + fresh Phase B preview slot before bake.

    Category contract: Bake final MP4 must not concat a stale sub-720 Phase B slot when
    delivery-encoded lipsync exists on disk. Runs before ``_stitch_build_pipeline``.
    """
    phase = "b"
    state = h.app.state.read_state()
    lipsync_name = (state.get(f"phase_{phase}_lipsync_file") or "").strip()
    if not lipsync_name:
        return {"ok": True, "skipped": True, "reason": "no_phase_b_lipsync_file"}

    lipsync_path = (h.app.event_dir / lipsync_name).resolve()
    if not lipsync_path.is_file():
        return {"ok": True, "skipped": True, "reason": "phase_b_lipsync_missing_on_disk"}

    from phase_module_lipsync_delivery import (  # noqa: PLC0415
        PHASE_MODULE_LIPSYNC_DELIVERY_PROFILE,
        finalize_phase_module_lipsync_delivery,
    )

    delivery_meta: dict | None = None
    profile = (state.get(f"phase_{phase}_lipsync_delivery_profile") or "").strip()
    if profile != PHASE_MODULE_LIPSYNC_DELIVERY_PROFILE:
        delivery_meta = finalize_phase_module_lipsync_delivery(lipsync_path, sharpen=True)

        def _apply_delivery(st, _meta=delivery_meta, _m=int(os.path.getmtime(str(lipsync_path)))):
            st[f"phase_{phase}_lipsync_mtime"] = _m
            st[f"phase_{phase}_lipsync_delivery_profile"] = _meta.get("delivery_profile")
            st[f"phase_{phase}_lipsync_delivery_recipe"] = _meta.get("delivery_recipe")
            st["_module_version"] = int(st.get("_module_version", 0) or 0) + 1
            return st["_module_version"]

        h.app.state.mutate_state(_apply_delivery)

    try:
        final_path, cache_hash = _phase_ensure_overlay_mp4(h, phase)
    except (ValueError, FileNotFoundError, RuntimeError, subprocess.CalledProcessError) as exc:
        return {"ok": False, "error": str(exc)}

    root = h._stitch_project_root()
    video_rel = str(final_path.resolve().relative_to(root))
    h._stitch_resolve_path(video_rel)

    from server_handlers.stitch_editor import stitch_upsert_event_slot  # noqa: PLC0415

    event_id = h.app.event_dir.name
    slot_key = f"phase_{phase}"
    job_name, export_dur_ms, export_warnings, _playback = stitch_upsert_event_slot(
        h,
        event_id,
        slot_key,
        {
            "video_path": video_rel,
            "overlay_baked": True,
            "source": f"phase_{phase}_export",
        },
        operator_export=True,
    )

    return {
        "ok": True,
        "refreshed": True,
        "delivery_meta": delivery_meta,
        "video_path": video_rel,
        "cache_hash": cache_hash,
        "job_name": job_name,
        "video_dur_ms": export_dur_ms,
        "warnings": export_warnings,
        "code": "STITCH_BAKE_PHASE_B_DELIVERY_V1",
    }


def handle_phase_b_preview(h, body: dict)-> None:

    """POST /api/phase_b/preview — stream cached or freshly rendered overlay MP4."""
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return

    phase = (body.get("phase") or "").strip().lower()
    err = h._phase_check(phase)
    if err:
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=err,
                   retry_safe=False,
                   extra={"hint": "phase is 'a' or 'b'."},
               )

    try:
        final_path, cache_hash = _phase_ensure_overlay_mp4(h, phase)
    except RuntimeError as exc:
        if "import failed" in str(exc):
            return h._send_error_v59(
                       500,
                       error_code="GENERIC_ERROR",
                       error_message=str(exc),
                       retry_safe=True,
                       extra={"hint": "Verify Production/tools/lib/ffmpeg_stitch.py has render_watercolor_overlay."},
                   )
        return h._send_error_v59(
                   409,
                   error_code="ANOTHER_PHASE_PREVIEW_IS_GENERATING",
                   error_message="another phase preview is generating",
                   retry_safe=False,
                   extra={"hint": "Wait for the in-flight preview to finish."},
               )
    except ValueError as exc:
        msg = str(exc)
        extra: dict = {}
        if "lipsync_file not set" in msg:
            extra["hint"] = "Send for Lipsync first, then retry Preview."
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=msg,
                   retry_safe=False,
                   extra=extra or None,
               )
    except FileNotFoundError as exc:
        msg = str(exc)
        if "watercolor assets missing" in msg:
            return h._send_error_v59(
                       400,
                       error_code="WATERCOLOR_ASSETS_MISSING_FOR_CUE",
                       error_message="watercolor assets missing for cue(s)",
                       retry_safe=False,
                       extra={"hint": msg},
                   )
        return h._send_error_v59(
                   404,
                   error_code="GENERIC_ERROR",
                   error_message=msg,
                   retry_safe=False,
               )
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or b"")[:600].decode("utf-8", errors="replace")
        return h._send_error_v59(
                   500,
                   error_code="GENERIC_ERROR",
                   error_message=f"ffmpeg overlay failed (returncode={exc.returncode})",
                   retry_safe=True,
                   extra={"stderr": stderr, "hint": "Check stderr; common cause is missing cue asset or corrupt lipsync."},
               )

    try:
        _, _, _, _, lru_cleanup = _phase_load_overlay_helpers()
        evicted = lru_cleanup(final_path.parent)
    except Exception:
        evicted = []
    return h._stream_preview_mp4(final_path, cache_hash, evicted=evicted)


def handle_phase_a_regen_flyin_flyout(h, body: dict) -> None:
    """POST /api/phase_a/regen_flyin_flyout — wide room bookends (~13 min)."""
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return

    state = h.app.state.read_state()
    if state.get("phase_a_flyin_flyout_status") == "running":
        return h._send_error_v59(
            409,
            error_code="GENERIC_ERROR",
            error_message="fly-in/fly-out regeneration already running",
            retry_safe=False,
        )

    # CODE tree — sibling script under Production/tools/
    tools_dir = _PSERVER_TOOLS_DIR
    script = tools_dir / "phase_a_flyin_flyout_wide_v1.py"
    if not script.is_file():
        return h._send_error_v59(
            500,
            error_code="GENERIC_ERROR",
            error_message=f"missing script: {script.name}",
            retry_safe=False,
        )

    _app = h.app
    _stitch = h._auto_assemble_phase_a_stitched

    def _apply_running(state):
        state["phase_a_flyin_flyout_status"] = "running"
        state.pop("phase_a_flyin_flyout_error", None)
        return state

    h.app.state.mutate_state(_apply_running)

    def _bg():
        import subprocess as _sp
        env = {**os.environ, "MN_EVENT_DIR": str(_app.event_dir)}
        try:
            proc = _sp.run(
                [sys.executable, str(script), "--no-element"],
                cwd=str(tools_dir),
                env=env,
                capture_output=True,
                text=True,
                timeout=1800,
            )
            if proc.returncode != 0:
                err = (proc.stderr or proc.stdout or "")[:300]
                def _fail(state, _e=err):
                    state["phase_a_flyin_flyout_status"] = f"error: {_e[:120]}"
                    return state
                _app.state.mutate_state(_fail)
                return
            ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            try:
                canonical = _stitch(ts)
            except Exception as exc:  # noqa: BLE001
                canonical = {"error": str(exc)[:200]}
            def _done(state, _c=canonical):
                state["phase_a_flyin_flyout_status"] = "done"
                return state
            _app.state.mutate_state(_done)
            print(f"[phase_a_regen_flyin_flyout] complete canonical={canonical}", flush=True)
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            def _exc(state, _x=exc):
                state["phase_a_flyin_flyout_status"] = (
                    f"error: {type(_x).__name__}: {str(_x)[:100]}"
                )
                return state
            _app.state.mutate_state(_exc)

    threading.Thread(target=_bg, daemon=True).start()
    return h._send_json(202, {
        "ok": True,
        "status": "running",
        "message": "Kling wide fly-in/out started (~13 min). Phase A will auto-stitch when done.",
    })


def handle_phase_a_regen_base_clip(h, body: dict) -> None:
    """POST /api/phase_a/regen_base_clip — Kling idle base (~6 min)."""
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return

    state = h.app.state.read_state()
    if state.get("phase_a_base_clip_regen_status") == "running":
        return h._send_error_v59(
            409,
            error_code="GENERIC_ERROR",
            error_message="base clip regeneration already running",
            retry_safe=False,
        )

    # CODE tree — sibling script under Production/tools/
    tools_dir = _PSERVER_TOOLS_DIR
    if str(tools_dir) not in sys.path:
        sys.path.insert(0, str(tools_dir))
    from phase_a_arlo_contract import (  # noqa: WPS433
        PHASE_A_ARLO_BASE_CLIP_CANONICAL,
        install_phase_a_arlo_canonical_still,
        resolve_phase_a_arlo_idle_still,
    )
    from phase_a_arlo_lipsync_base import (  # noqa: WPS433
        PHASE_A_BASE_CLIP_DURATION_S,
    )
    script = tools_dir / "phase_a_arlo_lipsync_base.py"
    clip_id = (body or {}).get("clip_id") or PHASE_A_ARLO_BASE_CLIP_CANONICAL
    duration_s = int((body or {}).get("duration_s") or PHASE_A_BASE_CLIP_DURATION_S)
    still_path = (body or {}).get("still_path")
    _app = h.app
    prod_root = _app.event_dir.parent
    try:
        still = resolve_phase_a_arlo_idle_still(
            _app.event_dir,
            prod_root,
            still_path,
        )
        install_phase_a_arlo_canonical_still(_app.event_dir, prod_root)
    except (FileNotFoundError, ValueError) as exc:
        return h._send_error_v59(
            400,
            error_code="GENERIC_ERROR",
            error_message=str(exc),
            retry_safe=False,
        )

    def _apply_running(state):
        state["phase_a_base_clip_regen_status"] = "running"
        return state

    h.app.state.mutate_state(_apply_running)

    def _bg():
        import subprocess as _sp
        env = {**os.environ, "MN_EVENT_DIR": str(_app.event_dir)}
        cmd = [
            sys.executable,
            str(script),
            "--clip-id",
            str(clip_id),
            "--duration",
            str(duration_s),
            "--still",
            str(still),
        ]
        try:
            proc = _sp.run(
                cmd,
                cwd=str(tools_dir),
                env=env,
                capture_output=True,
                text=True,
                timeout=900,
            )
            def _term(state, _rc=proc.returncode, _out=proc.stdout, _err=proc.stderr):
                if _rc == 0:
                    state["phase_a_base_clip_regen_status"] = "done"
                    state["phase_a_chipper_sitting_clip_id"] = clip_id
                    state["phase_a_lipsync_requires_regen"] = True
                else:
                    state["phase_a_base_clip_regen_status"] = (
                        f"error: {(_err or _out or 'failed')[:120]}"
                    )
                return state
            _app.state.mutate_state(_term)
        except Exception as exc:  # noqa: BLE001
            def _exc(state, _x=exc):
                state["phase_a_base_clip_regen_status"] = (
                    f"error: {type(_x).__name__}: {str(_x)[:100]}"
                )
                return state
            _app.state.mutate_state(_exc)

    threading.Thread(target=_bg, daemon=True).start()
    return h._send_json(202, {
        "ok": True,
        "status": "running",
        "clip_id": clip_id,
        "duration_s": duration_s,
        "message": (
            f"Kling idle base clip started (~6 min, {duration_s}s). "
            "Send for Lipsync when done."
        ),
    })


def handle_phase_b_regen_base_clip(h, body: dict) -> None:
    """POST /api/phase_b/regen_base_clip — Kling Cedric idle base (~6 min)."""
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return

    state = h.app.state.read_state()
    if state.get("phase_b_base_clip_regen_status") == "running":
        return h._send_error_v59(
            409,
            error_code="GENERIC_ERROR",
            error_message="base clip regeneration already running",
            retry_safe=False,
        )

    tools_dir = _PSERVER_TOOLS_DIR
    if str(tools_dir) not in sys.path:
        sys.path.insert(0, str(tools_dir))
    from phase_b_cedric_contract import (  # noqa: WPS433
        PHASE_B_CEDRIC_BASE_CLIP_CANONICAL,
    )
    from phase_b_cedric_lipsync_base import (  # noqa: WPS433
        PHASE_B_BASE_CLIP_DURATION_S,
    )
    script = tools_dir / "phase_b_cedric_lipsync_base.py"
    clip_id = (body or {}).get("clip_id") or PHASE_B_CEDRIC_BASE_CLIP_CANONICAL
    duration_s = int((body or {}).get("duration_s") or PHASE_B_BASE_CLIP_DURATION_S)
    still = (body or {}).get("still_path")
    _app = h.app

    def _apply_running(state):
        state["phase_b_base_clip_regen_status"] = "running"
        return state

    h.app.state.mutate_state(_apply_running)

    def _bg():
        import subprocess as _sp
        env = {**os.environ, "MN_EVENT_DIR": str(_app.event_dir)}
        cmd = [
            sys.executable,
            str(script),
            "--clip-id",
            str(clip_id),
            "--duration",
            str(duration_s),
        ]
        if still:
            cmd.extend(["--still", str(still)])
        try:
            proc = _sp.run(
                cmd,
                cwd=str(tools_dir),
                env=env,
                capture_output=True,
                text=True,
                timeout=900,
            )
            def _term(state, _rc=proc.returncode, _out=proc.stdout, _err=proc.stderr):
                if _rc == 0:
                    state["phase_b_base_clip_regen_status"] = "done"
                    state["phase_b_cedric_base_clip_id"] = clip_id
                    state["phase_b_lipsync_requires_regen"] = True
                else:
                    state["phase_b_base_clip_regen_status"] = (
                        f"error: {(_err or _out or 'failed')[:120]}"
                    )
                return state
            _app.state.mutate_state(_term)
        except Exception as exc:  # noqa: BLE001
            def _exc(state, _x=exc):
                state["phase_b_base_clip_regen_status"] = (
                    f"error: {type(_x).__name__}: {str(_x)[:100]}"
                )
                return state
            _app.state.mutate_state(_exc)

    threading.Thread(target=_bg, daemon=True).start()
    return h._send_json(202, {
        "ok": True,
        "status": "running",
        "clip_id": clip_id,
        "duration_s": duration_s,
        "message": (
            f"Kling Cedric idle base started (~6 min, {duration_s}s). "
            "Send for Lipsync when done."
        ),
    })


def handle_phase_a_restitch(h, body: dict) -> None:
    """POST /api/phase_a/restitch — normalize dry lipsync for export preview."""
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    try:
        result = h._auto_assemble_phase_a_stitched(ts)
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        return h._send_error_v59(
            500,
            error_code="GENERIC_ERROR",
            error_message=f"restitch failed: {exc}",
            retry_safe=True,
        )
    if not result:
        return h._send_error_v59(
            404,
            error_code="GENERIC_ERROR",
            error_message="missing raw lipsync input for Phase A stitch",
            retry_safe=False,
        )
    return h._send_json(200, {"ok": True, "canonical": result})


