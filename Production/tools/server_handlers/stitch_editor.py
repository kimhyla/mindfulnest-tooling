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
STITCH_MILESTONE_SLOT_ORDER = ["standalone"]
STITCH_EXPORT_ATOMIC_V1 = "STITCH_EXPORT_ATOMIC_V1"
# Canonical under-speech ambient level (all stitch slots — waveform, preview, bake).
STITCH_AMBIENT_BED_VOLUME = 0.15
STITCH_SFX_CUE_DEFAULT_VOLUME = 0.45
STITCH_SFX_CUE_DEFAULT_FADEIN_MS = 300
STITCH_SFX_CUE_DEFAULT_FADEOUT_MS = 1200
# Bust pre-2026-06-13 mix cache: stereo ambient bed + mono speech made amix drop SFX lanes;
# afade after adelay also silenced cues in the 3-way mix — fade must run before delay.
STITCH_WAVEFORM_MIX_MONO_V1 = "mono_v3"


def _stitch_media_public_url(h, api_path: str) -> str:
    """Media URL on the active storyboard server origin (5111, 5112, …).

    Hardcoding localhost:5111 breaks Event_2 on :5112 — WaveSurfer then fails with
    "Failed to fetch" while the slot video (same-origin /files) still plays.
    """
    path = api_path if api_path.startswith("/") else f"/{api_path.lstrip('/')}"
    try:
        host = (h.headers.get("Host") or "").strip()
    except Exception:
        host = ""
    if host:
        return f"http://{host}{path}"
    return path
# Canonical ambient bed preset_id per stitch slot (filename stem under sound_library/ambient/).
STITCH_DEFAULT_AMBIENT_BEDS: dict[str, str] = {
    "intro": "Intro video ambient bed",
    "standalone": "Intro video ambient bed",
    "phase_a": "ambient bed pretty option2",
    "phase_b": "ambient bed pretty option",
    "resolution": "ambien bed pretty option4",
}
# Canonical teleport whoosh — auto-placed on intro Send-to-Stitcher (removable in UI).
STITCH_INTRO_DEFAULT_WHOOSH_FILENAME = "whoosh sound.mp3"
STITCH_INTRO_DEFAULT_WHOOSH_PLAY_MS = 3104
# Resolution head whoosh matches intro tail whoosh (not after_win ba-bum stinger).
STITCH_RESOLUTION_HEAD_SFX_FILENAME = STITCH_INTRO_DEFAULT_WHOOSH_FILENAME
STITCH_RESOLUTION_HEAD_SFX_PLAY_MS = STITCH_INTRO_DEFAULT_WHOOSH_PLAY_MS
STITCH_LEGACY_RESOLUTION_HEAD_SFX_FILENAME = "after_win_return_to_map_music.mp3"
STITCH_RESOLUTION_TAIL_SFX_FILENAME = "exit resolution video sfx.mp3"
STITCH_RESOLUTION_HEAD_WHOOSH_V1 = "STITCH_RESOLUTION_HEAD_WHOOSH_V1"
STITCH_SFX_PLACEMENT_HEAD = "head"
STITCH_SFX_PLACEMENT_TAIL = "tail"
# STITCH_SLOT_CANONICAL_DEFAULTS_V1 — ambient beds + canonical SFX materialized as slot.sfx_cues.
STITCH_SLOT_CANONICAL_DEFAULTS_V1 = "STITCH_SLOT_CANONICAL_DEFAULTS_V1"
STITCH_CANONICAL_DEFAULTS_PERSIST_V1 = "STITCH_CANONICAL_DEFAULTS_PERSIST_V1"
# STITCH_BOUNDARY_SFX_PIPELINE_ONLY_V1 — phase_a/b boundary SFX span fades in bake pipeline only.
STITCH_BOUNDARY_SFX_PIPELINE_ONLY_V1 = "STITCH_BOUNDARY_SFX_PIPELINE_ONLY_V1"
# STITCH_PHASE_B_NO_OUTGOING_VISUAL_FADE_V1 — phase_b→resolution: no outgoing clip dim (black hold only).
STITCH_PHASE_B_NO_OUTGOING_VISUAL_FADE_V1 = "STITCH_PHASE_B_NO_OUTGOING_VISUAL_FADE_V1"
STITCH_PHASE_B_TO_RESOLUTION_PAIR_INDEX = 2
STITCH_SLOT_DEFAULT_TAIL_SFX_MAX_MS = 8000
# Boundary dissolve SFX filenames owned by _stitch_apply_canonical_boundary_sfx (not slot tail cues).
STITCH_PIPELINE_BOUNDARY_SLOT_TAIL_SFX: dict[str, str] = {
    "phase_a": "windy_magic.mp3",
    "phase_b": "magic_sound.mp3",
}
# slot_key → [(library filename, default play ms; 0 = file duration, placement head|tail)]
STITCH_SLOT_CANONICAL_DEFAULT_SFX: dict[str, list[tuple[str, int, str]]] = {
    "intro": [
        (STITCH_INTRO_DEFAULT_WHOOSH_FILENAME, STITCH_INTRO_DEFAULT_WHOOSH_PLAY_MS, STITCH_SFX_PLACEMENT_TAIL),
    ],
    "resolution": [
        (STITCH_RESOLUTION_HEAD_SFX_FILENAME, STITCH_RESOLUTION_HEAD_SFX_PLAY_MS, STITCH_SFX_PLACEMENT_HEAD),
        (STITCH_RESOLUTION_TAIL_SFX_FILENAME, 0, STITCH_SFX_PLACEMENT_TAIL),
    ],
}
# Back-compat alias (single tail cue per slot).
STITCH_SLOT_DEFAULT_TAIL_SFX: dict[str, tuple[str, int]] = {
    slot_key: (specs[0][0], specs[0][1])
    for slot_key, specs in STITCH_SLOT_CANONICAL_DEFAULT_SFX.items()
    if len(specs) == 1 and specs[0][2] == STITCH_SFX_PLACEMENT_TAIL
}
STITCH_SLOT_TAIL_SFX_DISMISS_KEYS: dict[str, str] = {
    "intro": "intro_whoosh_default_dismissed",
    "phase_a": "phase_a_tail_sfx_default_dismissed",
    "phase_b": "phase_b_tail_sfx_default_dismissed",
}
STITCH_SLOT_CANONICAL_SFX_FILE_DISMISS: dict[str, dict[str, str]] = {
    "resolution": {
        STITCH_RESOLUTION_HEAD_SFX_FILENAME: "resolution_head_sfx_default_dismissed",
        STITCH_RESOLUTION_TAIL_SFX_FILENAME: "resolution_tail_sfx_default_dismissed",
    },
}
# Re-probe when stored duration differs from on-disk file by more than this (ms).
STITCH_VIDEO_DUR_DRIFT_TOLERANCE_MS = 500
STITCH_SLOT_TIMELINE_ATOMIC_V1 = "STITCH_SLOT_TIMELINE_ATOMIC_V1"
# STITCH_SLOT_MEDIA_LINEAGE_DURABILITY_V1 — export/sync must not serve truncated audio extracts.
STITCH_SLOT_MEDIA_LINEAGE_DURABILITY_V1 = "STITCH_SLOT_MEDIA_LINEAGE_DURABILITY_V1"
# STITCH_SLOT_EXPORT_FULL_MEDIA_V1 — all four tab exports must upsert full playable slot video.
STITCH_SLOT_EXPORT_FULL_MEDIA_V1 = "STITCH_SLOT_EXPORT_FULL_MEDIA_V1"
# STITCH_SLOT_ASSEMBLED_DISK_HYDRATE_V1 — empty canonical slots recover from on-disk exports.
STITCH_SLOT_ASSEMBLED_DISK_HYDRATE_V1 = "STITCH_SLOT_ASSEMBLED_DISK_HYDRATE_V1"
# STITCH_SINGLE_OWNER_V1 — stitch_state.json job slot is sole authority after export;
# load_job must not persist pipeline disk hydrate (assembled/*.mp4).
STITCH_SINGLE_OWNER_V1 = "STITCH_SINGLE_OWNER_V1"
# STITCH_SAVE_ASYNC_ARTIFACTS_V1 — save_job persists JSON; ambient ffmpeg runs async.
STITCH_SAVE_ASYNC_ARTIFACTS_V1 = "STITCH_SAVE_ASYNC_ARTIFACTS_V1"
# STITCH_WRITE_TIME_PLAYBACK_ARTIFACTS_V1 — mux/ambient bake completes on export/hydrate only;
# load_job GET must never run ffmpeg repair.
STITCH_WRITE_TIME_PLAYBACK_ARTIFACTS_V1 = "STITCH_WRITE_TIME_PLAYBACK_ARTIFACTS_V1"
_PLAYBACK_BAKE_OPTIONAL_SKIPS = frozenset({
    "speech_only",
    "no_video",
    "job_missing",
    "handler_incomplete",
})
STITCH_ASSEMBLED_SLOT_GLOBS: dict[str, tuple[str, ...]] = {
    "intro": ("intro_*.mp4", "intro_kling_o3_*.mp4"),
    "phase_a": ("phase_a_*.mp4", "phase_a_stitched_*.mp4"),
    "phase_b": ("phase_b_*.mp4", "phase_b_lipsync_*.mp4"),
    "resolution": ("resolution_*.mp4", "resolution_kling_o3_*.mp4"),
    "standalone": ("standalone_*.mp4", "standalone_kling_o3_*.mp4"),
}
STITCH_AUDIO_DUR_MIN_RATIO = 0.85
STITCH_AUDIO_MAX_DRIFT_MS = 2000
STITCH_AUDIO_MAX_DRIFT_RATIO = 0.015
# STITCH_MODULE_PIPELINE_V1 — module-only transforms (finale, boundary black, dissolve concat).
STITCH_MODULE_PIPELINE_V1 = "STITCH_MODULE_PIPELINE_V1"
# STITCH_SLOT_PREVIEW_V1 — per-slot composer preview (normalize + ambient mix + copy only).
STITCH_SLOT_PREVIEW_V1 = "STITCH_SLOT_PREVIEW_V1"
# STITCH_SLOT_PREVIEW_VIDEO_PLAYABLE_V1 — preview MP4 must decode before URL is returned.
STITCH_SLOT_PREVIEW_VIDEO_PLAYABLE_V1 = "STITCH_SLOT_PREVIEW_VIDEO_PLAYABLE_V1"
# STITCH_SLOT_VIDEO_LINEAGE_V1 — operator export replaces slot video; playback cache must follow.
STITCH_SLOT_VIDEO_LINEAGE_V1 = "STITCH_SLOT_VIDEO_LINEAGE_V1"
# STITCH_SLOT_MEDIA_ARTIFACTS_V1 — server-persisted mux/peaks hashes on stitch job slots.
STITCH_SLOT_MEDIA_ARTIFACTS_V1 = "STITCH_SLOT_MEDIA_ARTIFACTS_V1"


def _stitch_pipeline_slot_count(body: dict) -> int:
    slots = body.get("slots")
    if isinstance(slots, list):
        return len([s for s in slots if isinstance(s, dict)])
    if isinstance(slots, dict):
        return len([s for s in slots.values() if isinstance(s, dict)])
    return 0


def tag_stitch_pipeline_scope(body: dict) -> None:
    """In-place flags so _stitch_build_pipeline applies the correct transform tier."""
    if body.get("module_pipeline") is True:
        body["slot_preview"] = False
        return
    if body.get("slot_preview") is True:
        body["module_pipeline"] = False
        return
    n = _stitch_pipeline_slot_count(body)
    if n <= 1:
        body["slot_preview"] = True
        body["module_pipeline"] = False
    else:
        body["slot_preview"] = False
        body["module_pipeline"] = True


def stitch_pipeline_apply_module_boundaries(body: dict) -> bool:
    """Dissolve black-pause boundaries — multi-slot module paths only."""
    if body.get("slot_preview"):
        return False
    return bool(body.get("module_pipeline")) and _stitch_pipeline_slot_count(body) >= 2


def stitch_pipeline_should_apply_resolution_finale(body: dict) -> bool:
    """Resolution outtro + black tail — full module ending in resolution only."""
    if body.get("slot_preview"):
        return False
    if not body.get("module_pipeline"):
        return False
    job_name = (body.get("name") or "").strip()
    if is_milestone_stitch_job_name(job_name):
        return False
    return _stitch_pipeline_slot_count(body) >= 4


def stitch_pipeline_should_apply_milestone_finale(body: dict) -> bool:
    """Standalone milestone bake — outtro3 fade + black tail (not slot preview)."""
    if body.get("slot_preview"):
        return False
    if not body.get("module_pipeline"):
        return False
    if _stitch_pipeline_slot_count(body) != 1:
        return False
    job_name = (body.get("name") or "").strip()
    return is_milestone_stitch_job_name(job_name)


def purge_stitch_cache_mp4(path) -> None:
    """Delete a cached MP4 that failed playable/decode validation."""
    try:
        p = Path(path)
        if p.is_file():
            p.unlink()
    except OSError:
        pass


def stitch_cached_mp4_playable(
    path,
    *,
    expected_s: float | None = None,
    min_ratio: float = STITCH_AUDIO_DUR_MIN_RATIO,
) -> bool:
    """STITCH_SLOT_PREVIEW_VIDEO_PLAYABLE_V1 — decode + QuickTime-safe timestamps + duration."""
    from credentials_lib.ffmpeg_stitch import (  # noqa: PLC0415
        STITCH_EXPORT_AV_MAX_DRIFT_S,
        av_duration_drift_s,
        ffprobe_stream_duration_s,
        mp4_decodes_cleanly,
        mp4_is_playable,
        mp4_operator_playback_timestamps_safe,
        preview_cache_is_valid,
        remux_mp4_playback_safe,
        stitch_preview_decode_timeout_s,
    )

    p = Path(path)
    if not p.is_file():
        return False
    decode_timeout_s = stitch_preview_decode_timeout_s(float(expected_s or 0.0))
    if not mp4_operator_playback_timestamps_safe(p):
        try:
            remux_mp4_playback_safe(p, timeout_s=max(120, decode_timeout_s))
        except (subprocess.CalledProcessError, RuntimeError, OSError):
            return False
    if expected_s is not None and expected_s > 0:
        if not preview_cache_is_valid(p, expected_s, min_ratio=min_ratio):
            return False
    else:
        if not mp4_is_playable(p):
            return False
        try:
            vdur_probe = float(ffprobe_stream_duration_s(p, "v"))
        except (TypeError, ValueError):
            vdur_probe = 0.0
        if not mp4_decodes_cleanly(
            p,
            timeout_s=stitch_preview_decode_timeout_s(vdur_probe),
        ):
            return False
    if av_duration_drift_s(p) > STITCH_EXPORT_AV_MAX_DRIFT_S:
        return False
    try:
        vdur = float(ffprobe_stream_duration_s(p, "v"))
    except (TypeError, ValueError):
        vdur = 0.0
    return vdur > 0.05


def stitch_slot_av_drift_exceeds(video_dur_ms: int, audio_dur_ms: int) -> bool:
    """True when slot video/audio durations are too far apart for linked playback."""
    drift_ms = abs(int(video_dur_ms) - int(audio_dur_ms))
    if drift_ms <= 0:
        return False
    if drift_ms > STITCH_AUDIO_MAX_DRIFT_MS:
        return True
    if video_dur_ms > 0 and drift_ms > int(video_dur_ms * STITCH_AUDIO_MAX_DRIFT_RATIO):
        return True
    return False


def apply_stitch_slot_default_ambient_preset(slot_key: str, slot: dict) -> bool:
    """Apply canonical ambient preset when slot has video but no bed selected yet."""
    if slot_key not in STITCH_DEFAULT_AMBIENT_BEDS:
        return False
    if not isinstance(slot, dict) or not (slot.get("video_path") or "").strip():
        return False
    if (slot.get("ambient_bed") or "").strip():
        return False
    slot["ambient_bed"] = STITCH_DEFAULT_AMBIENT_BEDS[slot_key]
    slot["ambient_volume"] = STITCH_AMBIENT_BED_VOLUME
    slot.pop("ambient_bed_path", None)
    return True


def _job_canonical_audio_needs_persist(live_slots, normalized_slots: dict) -> bool:
    """True when persisted job lacks canonical ambient_bed volume/path vs normalized view."""
    if not isinstance(normalized_slots, dict):
        return False
    live = live_slots if isinstance(live_slots, dict) else {}
    for slot_key in STITCH_SLOT_ORDER:
        src = normalized_slots.get(slot_key)
        if not isinstance(src, dict):
            continue
        preset = (src.get("ambient_bed") or "").strip()
        dur_ms = src.get("video_dur_ms")
        if not preset and not dur_ms:
            continue
        dst = live.get(slot_key)
        if not isinstance(dst, dict):
            return True
        if preset and (dst.get("ambient_bed") or "").strip() != preset:
            return True
        if preset:
            try:
                vol = float(dst.get("ambient_volume", 0))
            except (TypeError, ValueError):
                return True
            if abs(vol - STITCH_AMBIENT_BED_VOLUME) > 1e-6:
                return True
            if dst.get("ambient_bed_path"):
                return True
        if dur_ms is not None:
            try:
                live_dur = int(dst.get("video_dur_ms") or 0)
                norm_dur = int(dur_ms)
            except (TypeError, ValueError):
                return True
            if norm_dur > 0 and live_dur != norm_dur:
                return True
        src_path = (src.get("video_path") or "").strip()
        if src_path and (dst.get("video_path") or "").strip() != src_path:
            return True
        src_cues = [c for c in (src.get("sfx_cues") or []) if isinstance(c, dict)]
        dst_cues = [c for c in (dst.get("sfx_cues") or []) if isinstance(c, dict)]
        if len(src_cues) != len(dst_cues):
            return True
        src_auto = sorted(
            f"{c.get('name', '')}:{c.get('offset_ms', '')}" for c in src_cues if c.get("auto_default")
        )
        dst_auto = sorted(
            f"{c.get('name', '')}:{c.get('offset_ms', '')}" for c in dst_cues if c.get("auto_default")
        )
        if src_auto != dst_auto:
            return True
    return False


def _persist_stitch_job_canonical_audio(state: dict, name: str, normalized_slots: dict) -> None:
    """Write canonical slot fields (ambient, duration, phase_a path) into persisted stitch job."""
    live = state.get("jobs", {}).get(name)
    if not isinstance(live, dict) or not isinstance(live.get("slots"), dict):
        return
    if not isinstance(normalized_slots, dict):
        return
    for slot_key in STITCH_SLOT_ORDER:
        src = normalized_slots.get(slot_key)
        if not isinstance(src, dict):
            continue
        dst = live["slots"].setdefault(slot_key, {})
        if not isinstance(dst, dict):
            continue
        preset = (src.get("ambient_bed") or "").strip()
        if preset:
            dst["ambient_bed"] = preset
            dst["ambient_volume"] = STITCH_AMBIENT_BED_VOLUME
            dst.pop("ambient_bed_path", None)
        elif "ambient_bed" in src and not preset:
            dst.pop("ambient_bed", None)
            dst.pop("ambient_volume", None)
            dst.pop("ambient_bed_path", None)
        dur_ms = src.get("video_dur_ms")
        if dur_ms is not None:
            try:
                dur_i = int(dur_ms)
            except (TypeError, ValueError):
                dur_i = 0
            if dur_i > 0:
                dst["video_dur_ms"] = dur_i
        src_path = (src.get("video_path") or "").strip()
        if src_path:
            dst["video_path"] = src_path
        src_cues = src.get("sfx_cues")
        if isinstance(src_cues, list):
            dst["sfx_cues"] = [dict(c) for c in src_cues if isinstance(c, dict)]
        for dismiss_key in STITCH_SLOT_TAIL_SFX_DISMISS_KEYS.values():
            if dismiss_key in src:
                dst[dismiss_key] = src[dismiss_key]
            elif dismiss_key in dst:
                dst.pop(dismiss_key, None)
        normalize_slot_audio_mix_levels(dst)
    live["updated_at"] = datetime.now(timezone.utc).isoformat()


def _persist_stitch_job_healed_slots(
    state: dict,
    name: str,
    healed_slots: dict,
) -> None:
    """Persist artifact field clears/heals from load_job validation (not just canonical audio)."""
    from server_handlers.stitch_media_sig import STITCH_SLOT_ARTIFACT_FIELDS  # noqa: PLC0415

    live = state.get("jobs", {}).get(name)
    if not isinstance(live, dict) or not isinstance(live.get("slots"), dict):
        return
    if not isinstance(healed_slots, dict):
        return
    for slot_key, src in healed_slots.items():
        if not isinstance(src, dict):
            continue
        dst = live["slots"].setdefault(slot_key, {})
        if not isinstance(dst, dict):
            continue
        for field in STITCH_SLOT_ARTIFACT_FIELDS:
            if field in src:
                dst[field] = src[field]
            else:
                dst.pop(field, None)
        for ephemeral in ("_mux_preview_url", "_ambient_mix_url", "_waveform_peaks_url"):
            dst.pop(ephemeral, None)
    live["updated_at"] = datetime.now(timezone.utc).isoformat()


def apply_stitch_job_default_ambient_presets(slots) -> bool:
    """Backfill empty ambient_bed on all canonical slots. Returns True if any slot changed."""
    if not isinstance(slots, dict):
        return False
    changed = False
    for slot_key in STITCH_SLOT_ORDER:
        slot = slots.get(slot_key)
        if isinstance(slot, dict) and apply_stitch_slot_default_ambient_preset(slot_key, slot):
            changed = True
    return changed


def normalize_slot_audio_mix_levels(slot: dict) -> None:
    """Canonical ambient + SFX mix levels for any stitch slot (all four phases)."""
    if not isinstance(slot, dict):
        return
    preset = (slot.get("ambient_bed") or "").strip()
    amb_path = (slot.get("ambient_bed_path") or "").strip()
    if preset or amb_path:
        slot["ambient_volume"] = STITCH_AMBIENT_BED_VOLUME
    elif not preset and not amb_path:
        slot.pop("ambient_volume", None)
    for cue in slot.get("sfx_cues") or []:
        if not isinstance(cue, dict):
            continue
        cue.setdefault("volume", STITCH_SFX_CUE_DEFAULT_VOLUME)
        cue.setdefault("fadein_ms", STITCH_SFX_CUE_DEFAULT_FADEIN_MS)
        cue.setdefault("fadeout_ms", STITCH_SFX_CUE_DEFAULT_FADEOUT_MS)


def normalize_job_slots_audio(slots) -> None:
    """Apply normalize_slot_audio_mix_levels to every canonical stitch slot key."""
    if not isinstance(slots, dict):
        return
    for slot_key in STITCH_SLOT_ORDER:
        slot = slots.get(slot_key)
        if isinstance(slot, dict):
            apply_stitch_slot_default_ambient_preset(slot_key, slot)
            normalize_slot_audio_mix_levels(slot)


def _probe_stitch_slot_video_dur_ms(h, slot: dict) -> int:
    """Return ffprobe duration (ms) for slot video_path, or 0 when unavailable."""
    if not isinstance(slot, dict):
        return 0
    vp = (slot.get("video_path") or "").strip()
    if not vp or not hasattr(h, "_stitch_resolve_path") or not hasattr(h, "_ffprobe_duration_ms"):
        return 0
    try:
        abs_path = h._stitch_resolve_path(vp)
        abs_path = require_media_under_project(abs_path, extensions=MEDIA_EXTENSIONS)
    except (ValueError, FileNotFoundError):
        return 0
    return int(h._ffprobe_duration_ms(abs_path) or 0)


def sync_stitch_slot_video_dur_ms(h, slot: dict, *, force: bool = False) -> bool:
    """Probe slot video_path and keep video_dur_ms aligned with the file on disk."""
    probed = _probe_stitch_slot_video_dur_ms(h, slot)
    if probed <= 0:
        return False
    try:
        existing = int(slot.get("video_dur_ms") or 0)
    except (TypeError, ValueError):
        existing = 0
    if not force and existing > 0 and abs(existing - probed) <= STITCH_VIDEO_DUR_DRIFT_TOLERANCE_MS:
        return False
    if existing != probed:
        slot["video_dur_ms"] = probed
        return True
    return False


def hydrate_stitch_slot_video_dur_ms(h, slot: dict) -> bool:
    """Back-compat alias — always syncs when missing or drifted."""
    return sync_stitch_slot_video_dur_ms(h, slot)


def ensure_stitch_slot_timeline_dur_ms(h, slot: dict) -> bool:
    """STITCH_SLOT_TIMELINE_ATOMIC_V1 — slot with video_path must expose video_dur_ms."""
    if not isinstance(slot, dict):
        return False
    if not (slot.get("video_path") or "").strip():
        return False
    try:
        existing = int(slot.get("video_dur_ms") or 0)
    except (TypeError, ValueError):
        existing = 0
    if existing > 0:
        return False
    if sync_stitch_slot_video_dur_ms(h, slot, force=True):
        return True
    try:
        mux_ms = int(slot.get("mux_preview_duration_ms") or 0)
    except (TypeError, ValueError):
        mux_ms = 0
    if mux_ms > 0:
        slot["video_dur_ms"] = mux_ms
        return True
    return False


def hydrate_job_slot_video_durs(h, slots) -> bool:
    """Reconcile video_dur_ms on all canonical slots. Returns True if any slot changed."""
    if not isinstance(slots, dict):
        return False
    changed = False
    for slot_key in STITCH_SLOT_ORDER:
        slot = slots.get(slot_key)
        if isinstance(slot, dict) and sync_stitch_slot_video_dur_ms(h, slot):
            changed = True
    return changed


def _resolve_stitch_intro_whoosh_path(h) -> str:
    """Canonical project-root whoosh used by stitch library (legacy delivery file)."""
    project_root = h._stitch_project_root()
    fp = project_root / STITCH_INTRO_DEFAULT_WHOOSH_FILENAME
    return str(fp) if fp.is_file() else ""


def _resolve_stitch_slot_tail_sfx_path(h, slot_key: str, filename: str) -> str:
    """Resolve slot SFX — whoosh at project root; other cues from sfx library."""
    if filename == STITCH_INTRO_DEFAULT_WHOOSH_FILENAME:
        return _resolve_stitch_intro_whoosh_path(h)
    return resolve_canonical_boundary_sfx_path(h, filename)


def _slot_has_canonical_sfx_cue(slot: dict, filename: str) -> bool:
    """True when slot already has a cue matching the canonical filename."""
    stem = Path(filename).stem.lower().replace("_", " ")
    for cue in slot.get("sfx_cues") or []:
        if not isinstance(cue, dict):
            continue
        label = f"{cue.get('name', '')} {cue.get('source_path', '')}".lower().replace("_", " ")
        if stem in label or Path(filename).name.lower() in label:
            return True
    return False


def _slot_has_tail_sfx_cue(slot: dict, filename: str) -> bool:
    return _slot_has_canonical_sfx_cue(slot, filename)


def _slot_has_whoosh_cue(slot: dict) -> bool:
    return _slot_has_canonical_sfx_cue(slot, STITCH_INTRO_DEFAULT_WHOOSH_FILENAME)


def _canonical_sfx_dismissed(slot: dict, slot_key: str, filename: str) -> bool:
    per_file = STITCH_SLOT_CANONICAL_SFX_FILE_DISMISS.get(slot_key, {})
    dismiss_key = per_file.get(filename) or STITCH_SLOT_TAIL_SFX_DISMISS_KEYS.get(slot_key)
    if not dismiss_key:
        return False
    return bool(slot.get(dismiss_key))


def _clear_canonical_sfx_dismiss_flags(slot: dict, slot_key: str) -> None:
    dismiss_key = STITCH_SLOT_TAIL_SFX_DISMISS_KEYS.get(slot_key)
    if dismiss_key:
        slot.pop(dismiss_key, None)
    for key in STITCH_SLOT_CANONICAL_SFX_FILE_DISMISS.get(slot_key, {}).values():
        slot.pop(key, None)


def _canonical_sfx_play_ms(
    h,
    sfx_path: str,
    default_play_ms: int,
    video_dur_ms: int,
) -> int:
    raw_dur = h._ffprobe_duration_ms(Path(sfx_path))
    try:
        file_dur_ms = int(raw_dur or 0)
    except (TypeError, ValueError):
        file_dur_ms = 0
    play_ms = default_play_ms or (file_dur_ms if file_dur_ms > 0 else 3000)
    if file_dur_ms > 0 and play_ms > file_dur_ms:
        play_ms = int(file_dur_ms)
    play_ms = min(play_ms, STITCH_SLOT_DEFAULT_TAIL_SFX_MAX_MS)
    return max(500, min(play_ms, video_dur_ms))


def _canonical_sfx_offset_ms(
    video_dur_ms: int,
    play_ms: int,
    placement: str,
) -> int:
    if placement == STITCH_SFX_PLACEMENT_HEAD:
        return 0
    return max(0, video_dur_ms - play_ms)


def _find_canonical_sfx_cue(slot: dict, filename: str) -> dict | None:
    target = filename.lower()
    for cue in slot.get("sfx_cues") or []:
        if not isinstance(cue, dict) or not cue.get("auto_default"):
            continue
        name = (cue.get("name") or Path(str(cue.get("source_path") or "")).name or "").lower()
        if target in name or name in target:
            return cue
    return None


def _reanchor_canonical_sfx_cue(
    h,
    slot: dict,
    slot_key: str,
    filename: str,
    default_play_ms: int,
    placement: str,
) -> bool:
    """Keep auto_default canonical cues aligned to current slot duration."""
    if _canonical_sfx_dismissed(slot, slot_key, filename):
        return False
    sfx_path = _resolve_stitch_slot_tail_sfx_path(h, slot_key, filename)
    if not sfx_path:
        return False
    sync_stitch_slot_video_dur_ms(h, slot, force=True)
    video_dur_ms = int(slot.get("video_dur_ms") or 0)
    if video_dur_ms <= 0:
        return False
    play_ms = _canonical_sfx_play_ms(h, sfx_path, default_play_ms, video_dur_ms)
    offset_ms = _canonical_sfx_offset_ms(video_dur_ms, play_ms, placement)
    existing = _find_canonical_sfx_cue(slot, filename)
    if existing:
        changed = False
        if existing.get("source_path") != sfx_path:
            existing["source_path"] = sfx_path
            changed = True
        if existing.get("name") != filename:
            existing["name"] = filename
            changed = True
        if int(existing.get("offset_ms") or 0) != offset_ms:
            existing["offset_ms"] = offset_ms
            changed = True
        if int(existing.get("duration_ms") or 0) != play_ms:
            existing["duration_ms"] = play_ms
            changed = True
        return changed
    return _append_canonical_sfx_cue(
        h, slot, slot_key, filename, default_play_ms, placement,
    )


def _append_canonical_sfx_cue(
    h,
    slot: dict,
    slot_key: str,
    filename: str,
    default_play_ms: int,
    placement: str,
) -> bool:
    if _canonical_sfx_dismissed(slot, slot_key, filename):
        return False
    if _slot_has_canonical_sfx_cue(slot, filename):
        return False
    sfx_path = _resolve_stitch_slot_tail_sfx_path(h, slot_key, filename)
    if not sfx_path:
        return False
    sync_stitch_slot_video_dur_ms(h, slot, force=True)
    video_dur_ms = int(slot.get("video_dur_ms") or 0)
    if video_dur_ms <= 0:
        return False
    play_ms = _canonical_sfx_play_ms(h, sfx_path, default_play_ms, video_dur_ms)
    offset_ms = _canonical_sfx_offset_ms(video_dur_ms, play_ms, placement)
    import secrets as _secrets  # noqa: PLC0415

    cue = {
        "id": f"cue_{_secrets.token_hex(4)}",
        "source_path": sfx_path,
        "name": filename,
        "offset_ms": offset_ms,
        "duration_ms": play_ms,
        "volume": STITCH_SFX_CUE_DEFAULT_VOLUME,
        "fadein_ms": STITCH_SFX_CUE_DEFAULT_FADEIN_MS,
        "fadeout_ms": STITCH_SFX_CUE_DEFAULT_FADEOUT_MS,
        "auto_default": True,
    }
    slot["sfx_cues"] = list(slot.get("sfx_cues") or []) + [cue]
    return True


def ensure_stitch_slot_canonical_default_sfx_cues(h, slot_key: str, slot: dict) -> bool:
    """Materialize or re-anchor canonical default SFX on slot.sfx_cues (head and/or tail)."""
    specs = STITCH_SLOT_CANONICAL_DEFAULT_SFX.get(slot_key)
    if not specs or not isinstance(slot, dict) or not (slot.get("video_path") or "").strip():
        return False
    changed = False
    for filename, default_play_ms, placement in specs:
        if _reanchor_canonical_sfx_cue(
            h, slot, slot_key, filename, default_play_ms, placement,
        ):
            changed = True
    return changed


def ensure_stitch_slot_default_tail_sfx_cue(h, slot_key: str, slot: dict) -> bool:
    """Back-compat — delegates to ensure_stitch_slot_canonical_default_sfx_cues."""
    return ensure_stitch_slot_canonical_default_sfx_cues(h, slot_key, slot)


def ensure_stitch_intro_default_whoosh_cue(h, slot: dict) -> bool:
    """Ensure intro tail whoosh exists until the operator explicitly deletes it."""
    return ensure_stitch_slot_default_tail_sfx_cue(h, "intro", slot)


# Back-compat alias (tests + external imports).
apply_stitch_intro_default_whoosh_cue = ensure_stitch_intro_default_whoosh_cue


def _is_stale_pipeline_boundary_tail_cue(slot_key: str, cue: dict) -> bool:
    """True when auto_default tail cue duplicates pipeline-owned boundary SFX."""
    if not isinstance(cue, dict) or not cue.get("auto_default"):
        return False
    boundary_name = STITCH_PIPELINE_BOUNDARY_SLOT_TAIL_SFX.get(slot_key, "")
    if not boundary_name:
        return False
    name = (cue.get("name") or Path(str(cue.get("source_path") or "")).name or "").lower()
    return boundary_name.lower() in name


def _is_stale_resolution_head_cue(slot_key: str, cue: dict) -> bool:
    """True when auto_default head cue is the retired after_win stinger."""
    if slot_key != "resolution" or not isinstance(cue, dict) or not cue.get("auto_default"):
        return False
    legacy = STITCH_LEGACY_RESOLUTION_HEAD_SFX_FILENAME.lower()
    name = (cue.get("name") or Path(str(cue.get("source_path") or "")).name or "").lower()
    return legacy in name or "after_win" in name


def strip_stale_resolution_head_sfx_cues(slots) -> bool:
    """Remove retired after_win auto_default head cues from resolution slot."""
    if isinstance(slots, dict):
        slot = slots.get("resolution")
        if not isinstance(slot, dict):
            return False
        cues = slot.get("sfx_cues") or []
        kept = [c for c in cues if not _is_stale_resolution_head_cue("resolution", c)]
        if len(kept) != len(cues):
            slot["sfx_cues"] = kept
            return True
        return False
    if isinstance(slots, list) and len(slots) > 3:
        slot = slots[3]
        if not isinstance(slot, dict):
            return False
        cues = slot.get("sfx_cues") or []
        kept = [c for c in cues if not _is_stale_resolution_head_cue("resolution", c)]
        if len(kept) != len(cues):
            slot["sfx_cues"] = kept
            return True
    return False


def strip_stale_pipeline_boundary_slot_cues(slots) -> bool:
    """Remove phase_a/b auto_default tail cues that block pipeline boundary SFX span."""
    if isinstance(slots, dict):
        slot_items = ((k, slots.get(k)) for k in STITCH_SLOT_ORDER if k in slots)
    elif isinstance(slots, list):
        slot_items = (
            (STITCH_SLOT_ORDER[i], slots[i])
            for i in range(min(len(slots), len(STITCH_SLOT_ORDER)))
        )
    else:
        return False
    changed = False
    for slot_key, slot in slot_items:
        if not isinstance(slot, dict):
            continue
        cues = slot.get("sfx_cues") or []
        if not cues:
            continue
        kept = [c for c in cues if not _is_stale_pipeline_boundary_tail_cue(slot_key, c)]
        if len(kept) != len(cues):
            slot["sfx_cues"] = kept
            changed = True
    return changed


def stitch_slot_export_media_preflight(
    h,
    video_path_str: str,
    slot_key: str,
    *,
    beat_boundaries: list | None = None,
) -> tuple[int, list[str]]:
    """Probe export target; reject corrupt/truncated files before any stitch slot upsert."""
    from credentials_lib.ffmpeg_stitch import mp4_decodes_cleanly, mp4_is_playable  # noqa: PLC0415

    try:
        abs_path = h._stitch_resolve_path(video_path_str)
        abs_path = Path(
            require_media_under_project(abs_path, extensions=MEDIA_EXTENSIONS),
        )
    except (ValueError, FileNotFoundError) as exc:
        raise ValueError(str(exc)) from exc

    if abs_path.suffix.lower() in (".mp4", ".mov", ".webm"):
        if not mp4_is_playable(abs_path):
            raise ValueError(
                f"{slot_key}: export video is not a playable file "
                f"({STITCH_SLOT_EXPORT_FULL_MEDIA_V1})",
            )
        if not mp4_decodes_cleanly(abs_path, timeout_s=45):
            raise ValueError(
                f"{slot_key}: export video fails decode smoke test "
                f"({STITCH_SLOT_EXPORT_FULL_MEDIA_V1})",
            )

    probed_ms = _probe_stitch_slot_video_dur_ms(h, {"video_path": video_path_str})
    if probed_ms <= 0:
        raise ValueError(
            f"{slot_key}: export video unreadable or zero duration "
            f"({STITCH_SLOT_EXPORT_FULL_MEDIA_V1})",
        )

    if beat_boundaries:
        enriched = enrich_beat_boundaries(beat_boundaries)
        beat_end = 0
        for b in enriched:
            if not isinstance(b, dict):
                continue
            try:
                beat_end = max(beat_end, int(b.get("end_ms") or 0))
            except (TypeError, ValueError):
                continue
        if beat_end > probed_ms + STITCH_VIDEO_DUR_DRIFT_TOLERANCE_MS:
            raise ValueError(
                f"{slot_key}: beat map ends at {beat_end}ms but file is only "
                f"{probed_ms}ms — export would truncate beats "
                f"({STITCH_SLOT_EXPORT_FULL_MEDIA_V1})",
            )

    if slot_key == "phase_a" and hasattr(h.app, "state"):
        from server_handlers.phases import (  # noqa: PLC0415
            PHASE_VOICE_STEM_PIN_DURABILITY_V1,
            _phase_lipsync_sidecar_audio_source,
            _phase_preflight_voice_stem_for_lipsync,
            _phase_resolve_voice_stem_name,
        )

        state = h.app.state.read_state() or {}
        stem = _phase_resolve_voice_stem_name(state, "a")
        lipsync = (state.get("phase_a_lipsync_file") or "").strip()
        if stem and lipsync and not state.get("phase_a_lipsync_requires_regen"):
            sidecar = _phase_lipsync_sidecar_audio_source(h.app.event_dir, lipsync)
            sidecar_base = Path(sidecar).name if sidecar else ""
            if sidecar_base and sidecar_base != stem:
                raise ValueError(
                    f"phase_a export blocked: lipsync built from {sidecar_base!r} "
                    f"but stem pin is {stem!r} ({PHASE_VOICE_STEM_PIN_DURABILITY_V1})",
                )
        preflight_err = _phase_preflight_voice_stem_for_lipsync(h, state, "a")
        if preflight_err is not None:
            raise ValueError(
                f"phase_a export blocked: stale voice stem pin "
                f"({PHASE_VOICE_STEM_PIN_DURABILITY_V1})",
            )

    warnings = stitch_slot_duration_warnings(
        h, slot_key, {"video_path": video_path_str},
    )
    return probed_ms, warnings


def stitch_slot_duration_warnings(h, slot_key: str, slot: dict) -> list[str]:
    """Detect stale metadata / truncated files before they confuse slot review."""
    if not isinstance(slot, dict):
        return []
    probed = _probe_stitch_slot_video_dur_ms(h, slot)
    if probed <= 0:
        return []
    warnings: list[str] = []
    try:
        stored = int(slot.get("video_dur_ms") or 0)
    except (TypeError, ValueError):
        stored = 0
    if stored > 0 and abs(stored - probed) > STITCH_VIDEO_DUR_DRIFT_TOLERANCE_MS:
        warnings.append(
            f"{slot_key}: stored duration {stored}ms ≠ file {probed}ms — timeline was out of sync",
        )
    boundaries = slot.get("beat_boundaries") or []
    if boundaries:
        beat_end = 0
        for b in boundaries:
            if not isinstance(b, dict):
                continue
            try:
                beat_end = max(beat_end, int(b.get("end_ms") or 0))
            except (TypeError, ValueError):
                continue
        if beat_end > probed + STITCH_VIDEO_DUR_DRIFT_TOLERANCE_MS:
            warnings.append(
                f"{slot_key}: beat map ends at {beat_end}ms but file is only {probed}ms — clip may be truncated",
            )
    return warnings


def _slot_canonical_sfx_materialized(slot_key: str, slot: dict) -> bool:
    """True when every canonical default SFX cue is already on the slot."""
    specs = STITCH_SLOT_CANONICAL_DEFAULT_SFX.get(slot_key)
    if not specs:
        return True
    for filename, _play_ms, _placement in specs:
        if _find_canonical_sfx_cue(slot, filename) is None:
            return False
    return True


def ensure_job_slot_defaults(
    h,
    slots,
    *,
    fast: bool = False,
    apply_ambient_presets: bool = True,
) -> bool:
    """Sync durations, ambient presets, canonical tail SFX, and phase_a path."""
    if not isinstance(slots, dict):
        return False
    changed = strip_stale_pipeline_boundary_slot_cues(slots)
    if strip_stale_resolution_head_sfx_cues(slots):
        changed = True
    slot_keys = list(STITCH_SLOT_ORDER)
    for milestone_key in STITCH_MILESTONE_SLOT_ORDER:
        if milestone_key in slots and milestone_key not in slot_keys:
            slot_keys.append(milestone_key)
    for slot_key in slot_keys:
        slot = slots.get(slot_key)
        if not isinstance(slot, dict):
            continue
        if not fast and slot_key == "phase_a" and sync_stitch_phase_a_from_phase_tab(h, slot):
            changed = True
        if not fast and sync_stitch_slot_video_dur_ms(h, slot):
            changed = True
        if apply_ambient_presets and apply_stitch_slot_default_ambient_preset(slot_key, slot):
            changed = True
        if slot_key in STITCH_SLOT_CANONICAL_DEFAULT_SFX:
            if fast and _slot_canonical_sfx_materialized(slot_key, slot):
                pass
            elif ensure_stitch_slot_canonical_default_sfx_cues(h, slot_key, slot):
                changed = True
        normalize_slot_audio_mix_levels(slot)
    return changed


def collect_stitch_job_slot_warnings(
    h,
    slots,
    *,
    probe_video: bool = True,
) -> dict[str, list[str]]:
    if not isinstance(slots, dict):
        return {}
    if not probe_video:
        return {}
    out: dict[str, list[str]] = {}
    for slot_key in STITCH_SLOT_ORDER:
        slot = slots.get(slot_key)
        if not isinstance(slot, dict):
            continue
        warnings = stitch_slot_duration_warnings(h, slot_key, slot)
        if warnings:
            out[slot_key] = warnings
    return out


def _stitch_scope_event_id(h) -> str:
    if hasattr(h.app, "event_dir"):
        return Path(h.app.event_dir).name
    return ""


def _production_state_phase_a_stitched_filename(h) -> str:
    """Same key as Phase A tab player (`stitched_file` / phase_a_stitched_file)."""
    if not hasattr(h.app, "state"):
        return ""
    try:
        state = h.app.state.read_state() or {}
    except Exception:
        return ""
    return (state.get("phase_a_stitched_file") or "").strip()


def _canonical_module_final_bake_path(h) -> str | None:
    """Kid-facing canonical MP4 on disk for the pinned event (footer preview source)."""
    if not hasattr(h.app, "state"):
        return None
    try:
        state = h.app.state.read_state() or {}
    except Exception:
        return None
    canonical_name = (state.get("canonical_module_final_file") or "").strip()
    if not canonical_name or not hasattr(h.app, "event_dir"):
        return None
    target = (Path(h.app.event_dir) / canonical_name).resolve()
    event_root = Path(h.app.event_dir).resolve()
    if str(target).startswith(str(event_root)) and target.is_file():
        return str(target)
    return None


def sync_stitch_phase_a_from_phase_tab(h, slot: dict) -> bool:
    """Point stitch phase_a at production_state phase_a_stitched_file (Phase A tab parity)."""
    if not isinstance(slot, dict):
        return False
    fname = _production_state_phase_a_stitched_filename(h)
    event_id = _stitch_scope_event_id(h)
    if not fname or not event_id:
        return False

    # PHASE_VOICE_STEM_PIN_DURABILITY_V1 — do not sync stitched output whose
    # lipsync lineage does not match the pinned voice stem.
    try:
        from server_handlers.phases import (  # noqa: PLC0415
            PHASE_VOICE_STEM_PIN_DURABILITY_V1,
            _phase_lipsync_sidecar_audio_source,
            _phase_resolve_voice_stem_name,
        )

        state = h.app.state.read_state() or {}
        stem = _phase_resolve_voice_stem_name(state, "a")
        lipsync = (state.get("phase_a_lipsync_file") or "").strip()
        if (
            stem
            and lipsync
            and not state.get("phase_a_lipsync_requires_regen")
        ):
            sidecar_src = _phase_lipsync_sidecar_audio_source(h.app.event_dir, lipsync)
            sidecar_base = Path(sidecar_src).name if sidecar_src else ""
            if sidecar_base and sidecar_base != stem:
                print(
                    "[stitch] phase_a sync blocked — lipsync audio_source "
                    f"{sidecar_base!r} != stem pin {stem!r} "
                    f"({PHASE_VOICE_STEM_PIN_DURABILITY_V1})",
                    flush=True,
                )
                return False
    except Exception:  # noqa: BLE001
        pass

    canonical_path = f"Production/{event_id}/{fname}"
    current = (slot.get("video_path") or "").strip()
    if current == canonical_path:
        return False
    try:
        abs_path = h._stitch_resolve_path(canonical_path)
        require_media_under_project(abs_path, extensions=MEDIA_EXTENSIONS)
    except (ValueError, FileNotFoundError):
        return False
    slot["video_path"] = canonical_path
    sync_stitch_slot_video_dur_ms(h, slot, force=True)
    return True


def stitch_event_job_name(event_id: str) -> str:
    return f"{event_id}_stitch"


def stitch_milestone_job_name(milestone_id: str) -> str:
    return f"milestone_{milestone_id}_stitch"


def milestone_id_from_stitch_job_name(job_name: str) -> str | None:
    """Extract milestone_id from ``milestone_{id}_stitch`` job names."""
    prefix = "milestone_"
    suffix = "_stitch"
    if not (job_name.startswith(prefix) and job_name.endswith(suffix)):
        return None
    mid = job_name[len(prefix): -len(suffix)].strip()
    return mid or None


def is_milestone_stitch_job_name(job_name: str) -> bool:
    return milestone_id_from_stitch_job_name(job_name) is not None


_EVENT_STITCH_JOB_RE = re.compile(r"^Event_\d+_stitch$")


def legacy_milestone_id_from_stitch_job_name(job_name: str) -> str | None:
    """Retired pre-bbfd338 names like ``milestone1_arc1_stitch`` (no ``milestone_`` prefix)."""
    if not job_name.endswith("_stitch"):
        return None
    if is_milestone_stitch_job_name(job_name):
        return None
    if _EVENT_STITCH_JOB_RE.match(job_name):
        return None
    body = job_name[: -len("_stitch")].strip()
    if not body or body.startswith("Event_"):
        return None
    if body.startswith("milestone") and not body.startswith("milestone_"):
        return body
    return None


def purge_legacy_milestone_stitch_jobs_from_global(h) -> list[str]:
    """Remove retired milestone job names from global ``stitch_editor_state.json``."""
    removed: list[str] = []

    def purge(state: dict) -> None:
        jobs = state.get("jobs")
        if not isinstance(jobs, dict):
            return
        for key in list(jobs.keys()):
            if legacy_milestone_id_from_stitch_job_name(key):
                jobs.pop(key, None)
                removed.append(key)

    _event_stitch_state_store(h).mutate_state(purge)
    return removed


def _event_stitch_state_store(h):
    """Event-global stitch store — never the transient milestone swap on ``h.app.stitch_state``."""
    return getattr(h.app, "_event_stitch_state", None) or h.app.stitch_state


def purge_event_jobs_from_milestone_stitch_store(stitch_store) -> list[str]:
    """Drop ``Event_N_stitch`` keys wrongly persisted in milestone-local ``stitch_state.json``."""
    removed: list[str] = []

    def purge(state: dict) -> None:
        jobs = state.get("jobs")
        if not isinstance(jobs, dict):
            return
        for key in list(jobs.keys()):
            if _EVENT_STITCH_JOB_RE.match(str(key)):
                jobs.pop(key, None)
                removed.append(str(key))

    stitch_store.mutate_state(purge)
    return removed


def stitch_state_store_for_job(h, job_name: str):
    """Global stitch state for event jobs; milestone-local ``stitch_state.json`` otherwise."""
    mid = milestone_id_from_stitch_job_name(job_name)
    if not mid:
        return _event_stitch_state_store(h)
    from lib.milestone_store import milestone_stitch_state_path  # noqa: PLC0415
    from lib.paths import runtime_production_root  # noqa: PLC0415
    from production_server import StitchEditorState  # noqa: PLC0415

    prod = runtime_production_root(h.app.event_dir)
    path = milestone_stitch_state_path(prod / "Milestones" / mid)
    return StitchEditorState(path)


def _coerce_stitch_save_slots_to_dict(
    slots,
    job_name: str,
    slot_key_hint: str = "",
) -> dict:
    """Save payloads may use preview-style slot lists — milestone jobs need dict keys."""
    if isinstance(slots, dict):
        return slots
    if not isinstance(slots, list):
        return {}
    items = [s for s in slots if isinstance(s, dict)]
    if not items:
        return {}
    if is_milestone_stitch_job_name(job_name):
        if slot_key_hint in STITCH_MILESTONE_SLOT_ORDER:
            return {slot_key_hint: items[0]}
        if len(items) == 1:
            return {"standalone": items[0]}
        return {
            STITCH_MILESTONE_SLOT_ORDER[i]: items[i]
            for i in range(min(len(items), len(STITCH_MILESTONE_SLOT_ORDER)))
        }
    order = STITCH_SLOT_ORDER
    return {
        order[i]: items[i]
        for i in range(min(len(items), len(order)))
    }


def normalize_milestone_stitch_job(job: dict, *, job_name: str = "") -> bool:
    """Milestone jobs are 1-slot ``standalone`` only — strip event-slot pollution."""
    if not isinstance(job, dict):
        return False
    changed = False
    slots = job.get("slots")
    if isinstance(slots, list):
        coerced = _coerce_stitch_save_slots_to_dict(slots, job_name)
        job["slots"] = coerced
        slots = coerced
        changed = True
    if not isinstance(slots, dict):
        job["slots"] = {}
        slots = job["slots"]
        changed = True
    allowed = set(STITCH_MILESTONE_SLOT_ORDER)
    for key in list(slots.keys()):
        if key not in allowed:
            del slots[key]
            changed = True
    if "standalone" not in slots:
        slots["standalone"] = {}
        changed = True
    bake = (job.get("bake_path") or "").strip()
    if bake and "/Event_" in bake.replace("\\", "/"):
        job.pop("bake_path", None)
        changed = True
    return changed


def purge_milestone_job_from_global_stitch_state(h, job_name: str) -> None:
    """Remove milestone stitch jobs wrongly persisted in global ``stitch_editor_state.json``."""
    if not is_milestone_stitch_job_name(job_name):
        return

    def purge(state: dict) -> None:
        jobs = state.get("jobs")
        if isinstance(jobs, dict):
            jobs.pop(job_name, None)

    _event_stitch_state_store(h).mutate_state(purge)


def _valid_stitch_slot(slot_key: str, *, job_name: str | None = None) -> bool:
    if job_name and job_name.startswith("milestone_"):
        return slot_key in STITCH_MILESTONE_SLOT_ORDER
    return slot_key in STITCH_SLOT_ORDER


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
        if isinstance(slot, dict):
            ensure_slot_ambient_bed_path_hydrated(h, slot)


def ensure_slot_ambient_bed_path_hydrated(h, slot: dict) -> None:
    """Resolve ambient_bed preset → ambient_bed_path before any ffmpeg mix (all call paths)."""
    if not isinstance(slot, dict):
        return
    preset = (slot.get("ambient_bed") or "").strip()
    path = (slot.get("ambient_bed_path") or "").strip()
    if preset:
        if not path or not os.path.isfile(path):
            resolved = _resolve_stitch_ambient_bed_path(h, preset)
            if resolved:
                slot["ambient_bed_path"] = resolved
            else:
                slot.pop("ambient_bed_path", None)
    else:
        slot.pop("ambient_bed_path", None)
    normalize_slot_audio_mix_levels(slot)


def _mix_stitch_waveform_audio(
    h,
    base_audio_path: Path,
    slot: dict,
    cache_dir: Path,
    base_sig: str,
    *,
    expected_video_dur_ms: int,
) -> Path | None:
    """Mix ambient bed + SFX cues into extracted slot audio for composer waveform (all slots)."""
    import hashlib as _hl  # noqa: PLC0415
    from credentials_lib.ffmpeg_stitch import stitch_audio_cache_is_valid  # noqa: PLC0415

    ensure_slot_ambient_bed_path_hydrated(h, slot)
    ambient_path = (slot.get("ambient_bed_path") or "").strip()
    ambient_volume = float(slot.get("ambient_volume", STITCH_AMBIENT_BED_VOLUME))
    sfx_cues = [c for c in (slot.get("sfx_cues") or []) if isinstance(c, dict)]

    if not ambient_path and not sfx_cues:
        return None
    if ambient_path and not os.path.isfile(ambient_path):
        ambient_path = ""

    video_dur_ms = max(int(expected_video_dur_ms or 0), 0)
    if video_dur_ms <= 0:
        video_dur_ms = h._ffprobe_duration_ms(base_audio_path)
    expected_s = max(video_dur_ms, 1) / 1000.0
    slot_dur_s = expected_s

    sig_parts = [
        base_sig,
        STITCH_WAVEFORM_MIX_MONO_V1,
        str(video_dur_ms),
        ambient_path,
        f"{ambient_volume:.4f}",
    ]
    from server_handlers.stitch_media_sig import (  # noqa: PLC0415
        stitch_sfx_cue_sig_parts,
        waveform_mix_hash_from_parts,
        waveform_mix_hash_parts,
    )

    sig_parts = waveform_mix_hash_parts(
        base_sig, video_dur_ms, ambient_path, ambient_volume, sfx_cues,
    )
    mix_hash = waveform_mix_hash_from_parts(sig_parts)
    out_path = cache_dir / f"stitch_audio_{mix_hash}.mp3"

    valid_cue_labels: list[str] = []
    for idx, cue in enumerate(sfx_cues):
        src = cue.get("source_path") or ""
        if not src or not os.path.isfile(src):
            continue
        valid_cue_labels.append(f"cue{len(valid_cue_labels)}")

    if out_path.is_file():
        if not stitch_audio_cache_is_valid(
            out_path, expected_s, min_ratio=STITCH_AUDIO_DUR_MIN_RATIO,
        ):
            try:
                out_path.unlink()
            except OSError:
                pass
        elif valid_cue_labels or ambient_path:
            if valid_cue_labels:
                slot["_sfx_mixed"] = True
            return out_path

    input_args: list[str] = ["-i", str(base_audio_path.resolve())]
    filter_lanes: list[str] = []
    base_audio = "[0:a]"
    next_input_idx = 1

    if ambient_path:
        input_args += ["-i", ambient_path]
        aidx = next_input_idx
        next_input_idx += 1
        bed_dur_ms = h._ffprobe_duration_ms(Path(ambient_path))
        bed_dur_s = bed_dur_ms / 1000.0 if bed_dur_ms else 0.0
        from server_handlers.stitch_ambient_loop import build_ambient_bed_filter_lane_for_file  # noqa: PLC0415

        filter_lanes.append(
            build_ambient_bed_filter_lane_for_file(
                aidx, ambient_path, bed_dur_s, slot_dur_s, ambient_volume, out_label="bed",
            )
        )

    for idx, cue in enumerate(sfx_cues):
        src = cue.get("source_path") or ""
        if not src or not os.path.isfile(src):
            continue
        input_args += ["-i", src]
        cidx = next_input_idx
        next_input_idx += 1
        offset_ms = int(cue.get("offset_ms", 0))
        fadein_ms = int(cue.get("fadein_ms", STITCH_SFX_CUE_DEFAULT_FADEIN_MS))
        fadeout_ms = int(cue.get("fadeout_ms", STITCH_SFX_CUE_DEFAULT_FADEOUT_MS))
        vol = float(cue.get("volume", STITCH_SFX_CUE_DEFAULT_VOLUME))
        cue_dur_ms = h._ffprobe_duration_ms(Path(src))
        cue_dur_s = cue_dur_ms / 1000.0 if cue_dur_ms else 5.0
        play_ms = cue.get("duration_ms")
        if play_ms is not None and int(play_ms) > 0:
            play_s = min(cue_dur_s, int(play_ms) / 1000.0)
        else:
            play_s = cue_dur_s
        fadeout_start_s = max(0.0, play_s - fadeout_ms / 1000.0)
        label = f"cue{len(valid_cue_labels)}"
        valid_cue_labels.append(label)
        filter_lanes.append(
            f"[{cidx}:a]aresample=44100,aformat=channel_layouts=mono,"
            f"atrim=duration={play_s:.3f},"
            f"afade=t=in:st=0:d={fadein_ms / 1000:.3f},"
            f"afade=t=out:st={fadeout_start_s:.3f}:d={fadeout_ms / 1000:.3f},"
            f"adelay={offset_ms}:all=1,"
            f"volume={vol:.3f}[{label}]"
        )

    mix_inputs = [base_audio]
    if ambient_path:
        mix_inputs.append("[bed]")
    mix_inputs += [f"[{label}]" for label in valid_cue_labels]
    if len(mix_inputs) < 2:
        return None

    if valid_cue_labels:
        slot["_sfx_mixed"] = True

    n_mix = len(mix_inputs)
    filter_lanes.append(
        f"{''.join(mix_inputs)}amix=inputs={n_mix}:duration=longest:normalize=0,"
        f"apad=whole_dur={slot_dur_s:.3f},atrim=duration={slot_dur_s:.3f}[aout]"
    )
    filter_complex = ";".join(filter_lanes)
    mix_cmd = [
        "ffmpeg", "-y",
        *input_args,
        "-filter_complex", filter_complex,
        "-map", "[aout]",
        "-ac", "1", "-ar", "44100", "-b:a", "128k",
        str(out_path.resolve()),
    ]
    from credentials_lib.stitch_cache_build import (  # noqa: PLC0415
        atomic_ffmpeg_output,
        run_stitch_cache_build,
        stitch_cache_build_lock,
    )

    def _mix_ready() -> bool:
        return out_path.is_file() and stitch_audio_cache_is_valid(
            out_path, expected_s, min_ratio=STITCH_AUDIO_DUR_MIN_RATIO,
        )

    def _build_mix() -> None:
        if _mix_ready():
            return
        atomic_ffmpeg_output(
            mix_cmd,
            out_path,
            expected_duration_s=expected_s,
            validator=lambda p, exp: stitch_audio_cache_is_valid(
                p, exp, min_ratio=STITCH_AUDIO_DUR_MIN_RATIO,
            ),
        )

    try:
        run_stitch_cache_build(cache_dir, ready=_mix_ready, build=_build_mix)
    except RuntimeError as exc:
        raise RuntimeError(str(exc)) from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or b"")[:400].decode("utf-8", errors="replace")
        raise RuntimeError(f"waveform audio mix failed: {stderr}") from exc
    if not stitch_audio_cache_is_valid(
        out_path, expected_s, min_ratio=STITCH_AUDIO_DUR_MIN_RATIO,
    ):
        try:
            out_path.unlink()
        except OSError:
            pass
        raise RuntimeError(
            f"waveform mix truncated: expected ~{expected_s:.1f}s "
            f"({STITCH_SLOT_MEDIA_LINEAGE_DURABILITY_V1})",
        )
    if valid_cue_labels:
        slot["_sfx_mixed"] = True
    return out_path


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
        normalize_job_slots_audio(canonical["slots"])
        canonical["updated_at"] = datetime.now(timezone.utc).isoformat()
    return changed


def _pick_newest_playable_mp4(candidates: list[Path]) -> Path | None:
    valid = [
        p for p in candidates
        if p.is_file() and p.stat().st_size > 0
    ]
    if not valid:
        return None
    return max(valid, key=lambda p: p.stat().st_mtime)


def _phase_production_state_video_rel(h, event_id: str, slot_key: str) -> str | None:
    """Phase A/B stitch exports live in production_state, not always under assembled/."""
    if slot_key not in ("phase_a", "phase_b"):
        return None
    try:
        state = h.app.state.read_state()
    except Exception:
        return None
    if slot_key == "phase_a":
        name = (state.get("phase_a_stitched_file") or "").strip()
    else:
        pb = state.get("phase_b") or {}
        name = (
            (state.get("phase_b_lipsync_file") or pb.get("lipsync_file") or "")
            .strip()
        )
    if not name or "/" in name or "\\" in name or ".." in name:
        return None
    rel = f"Production/{event_id}/{name}"
    try:
        h._stitch_resolve_path(rel)
    except ValueError:
        return None
    return rel


def _assembled_disk_video_rel(h, event_id: str, slot_key: str) -> str | None:
    root = h._stitch_project_root()
    event_dir = root / "Production" / event_id
    patterns = STITCH_ASSEMBLED_SLOT_GLOBS.get(slot_key, ())
    search_dirs = [event_dir / "assembled"]
    if slot_key in ("phase_a", "phase_b"):
        search_dirs.append(event_dir)
    candidates: list[Path] = []
    for directory in search_dirs:
        if not directory.is_dir():
            continue
        for pattern in patterns:
            candidates.extend(directory.glob(pattern))
    picked = _pick_newest_playable_mp4(candidates)
    if picked is None:
        return None
    try:
        return str(picked.resolve().relative_to(root))
    except ValueError:
        return None


EVENT_STITCH_JOB_BOOTSTRAP_V1 = "EVENT_STITCH_JOB_BOOTSTRAP_V1"
_NUMBERED_EVENT_ID_RE = re.compile(r"^Event_\d+$")


def is_numbered_event_id(event_id: str) -> bool:
    """True for Event_1 … Event_89 (dedicated-port numbered events)."""
    return bool(_NUMBERED_EVENT_ID_RE.match((event_id or "").strip()))


def stitch_bootstrap_shim_for_app(app):
    """Minimal handler surface for stitch bootstrap at server startup (no HTTP handler yet)."""

    class _StitchBootstrapShim:
        def __init__(self, app):
            self.app = app

        def _stitch_project_root(self) -> Path:
            return self.app.event_dir.resolve().parent.parent

        def _stitch_resolve_path(self, raw: str) -> str:
            root = self._stitch_project_root()
            p = Path(raw)
            resolved = str((p if p.is_absolute() else root / p).resolve())
            root_s = str(root)
            if not (resolved == root_s or resolved.startswith(root_s + os.sep)):
                raise ValueError(f"path outside project root: {raw!r}")
            return resolved

    return _StitchBootstrapShim(app)


def _playback_artifact_bake_is_mandatory(report: dict) -> bool:
    if report.get("ok"):
        return False
    skip = (report.get("skipped") or "").strip()
    return skip not in _PLAYBACK_BAKE_OPTIONAL_SKIPS


def _require_playback_artifacts_on_write(slot_key: str, report: dict) -> None:
    if not _playback_artifact_bake_is_mandatory(report):
        return
    err = report.get("error") or report.get("skipped") or "unknown"
    raise ValueError(
        f"{slot_key}: playback artifact bake required at write time failed ({err}) "
        f"[{STITCH_WRITE_TIME_PLAYBACK_ARTIFACTS_V1}]",
    )


def _repair_stitch_job_playback_artifacts_on_write(
    h,
    job_name: str,
    stitch_store,
) -> list[str]:
    """Write-path heal for slots with video but missing mux/ambient artifacts."""
    from server_handlers.stitch_media_artifacts import stitch_slot_needs_playback_artifact_bake  # noqa: PLC0415

    repaired: list[str] = []
    state = stitch_store.read_state() or {}
    job = (state.get("jobs") or {}).get(job_name)
    if not isinstance(job, dict):
        return repaired
    slots = job.get("slots") or {}
    if not isinstance(slots, dict):
        return repaired
    for slot_key, slot in list(slots.items()):
        if not isinstance(slot, dict):
            continue
        if not stitch_slot_needs_playback_artifact_bake(h, slot):
            continue
        rep = ensure_stitch_slot_playback_artifacts_on_export(
            h,
            job_name,
            slot_key,
            stitch_store=stitch_store,
        )
        if rep.get("ok"):
            repaired.append(str(slot_key))
        else:
            print(
                f"[stitch] write-path playback repair failed "
                f"{job_name}/{slot_key}: {rep}",
                flush=True,
            )
    return repaired


def ensure_event_stitch_job_registered(
    h,
    event_id: str,
    *,
    hydrate_from_disk: bool = True,
) -> dict:
    """Ensure ``{event_id}_stitch`` exists in global stitch state (EVENT_STITCH_JOB_BOOTSTRAP_V1).

    Idempotent: migrates legacy auto_/phase_* jobs, creates empty canonical slots,
    optionally hydrates empty slots from on-disk exports when the server is pinned
    to the same event. Persists only when something changes.
    """
    event_id = (event_id or "").strip()
    if not is_numbered_event_id(event_id):
        return {
            "ok": True,
            "skipped": True,
            "reason": "not_numbered_event",
            "code": EVENT_STITCH_JOB_BOOTSTRAP_V1,
        }

    job_name = stitch_event_job_name(event_id)
    stitch_store = stitch_state_store_for_job(h, job_name)
    report: dict = {
        "ok": True,
        "code": EVENT_STITCH_JOB_BOOTSTRAP_V1,
        "event_id": event_id,
        "job_name": job_name,
        "created": False,
        "migrated": False,
        "hydrated": False,
        "changed": False,
    }
    pinned_event = getattr(getattr(h, "app", None), "event_dir", None)
    pinned_name = pinned_event.name if pinned_event is not None else ""
    do_hydrate = bool(
        hydrate_from_disk
        and pinned_name == event_id
    )

    def bootstrap(state: dict) -> None:
        existed_before = isinstance((state.get("jobs") or {}).get(job_name), dict)
        migrated = stitch_migrate_legacy_to_canonical(state, event_id)
        report["migrated"] = bool(migrated)
        jobs = state.setdefault("jobs", {})
        job = jobs.get(job_name)
        slot_keys_added = False
        if not isinstance(job, dict):
            jobs[job_name] = {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "slots": {slot_key: {} for slot_key in STITCH_SLOT_ORDER},
                "transitions": [],
            }
            slot_keys_added = True
        else:
            slots = job.setdefault("slots", {})
            if not isinstance(slots, dict):
                job["slots"] = {slot_key: {} for slot_key in STITCH_SLOT_ORDER}
                slot_keys_added = True
            else:
                for slot_key in STITCH_SLOT_ORDER:
                    if slot_key not in slots:
                        slots[slot_key] = {}
                        slot_keys_added = True
        if not existed_before:
            report["created"] = True
        changed = bool(migrated or slot_keys_added or not existed_before)
        if do_hydrate and hydrate_stitch_canonical_slots_from_disk(h, state, event_id):
            report["hydrated"] = True
            changed = True
        report["changed"] = changed
        if changed:
            job_ref = jobs.get(job_name)
            if isinstance(job_ref, dict):
                job_ref["updated_at"] = datetime.now(timezone.utc).isoformat()

    stitch_store.mutate_state(bootstrap)
    if do_hydrate:
        repaired = _repair_stitch_job_playback_artifacts_on_write(
            h,
            job_name,
            stitch_store,
        )
        if repaired:
            report["playback_artifacts_repaired"] = repaired
            report["write_time_playback_code"] = STITCH_WRITE_TIME_PLAYBACK_ARTIFACTS_V1
    return report


def hydrate_stitch_canonical_slots_from_disk(h, state: dict, event_id: str) -> bool:
    """Fill empty canonical stitch slots from newest on-disk exports (all events).

    Runs after legacy migration so a partial canonical job (e.g. resolution-only)
    still shows intro / phase_a / phase_b when their MP4s exist on disk.
    """
    stitch_migrate_legacy_to_canonical(state, event_id)
    job_name = stitch_event_job_name(event_id)
    jobs = state.setdefault("jobs", {})
    job = jobs.setdefault(
        job_name,
        {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "slots": {},
            "transitions": [],
        },
    )
    if not isinstance(job.get("slots"), dict):
        job["slots"] = {}

    changed = False
    for slot_key in STITCH_SLOT_ORDER:
        slot = job["slots"].setdefault(slot_key, {})
        if _slot_has_video(slot):
            continue
        rel = _phase_production_state_video_rel(h, event_id, slot_key)
        if not rel:
            rel = _assembled_disk_video_rel(h, event_id, slot_key)
        if not rel:
            continue
        slot["video_path"] = rel
        slot["source"] = STITCH_SLOT_ASSEMBLED_DISK_HYDRATE_V1
        sync_stitch_slot_video_dur_ms(h, slot, force=True)
        apply_stitch_slot_default_ambient_preset(slot_key, slot)
        if slot_key in STITCH_SLOT_CANONICAL_DEFAULT_SFX:
            ensure_stitch_slot_canonical_default_sfx_cues(h, slot_key, slot)
        normalize_slot_audio_mix_levels(slot)
        changed = True

    if changed:
        normalize_job_slots_audio(job["slots"])
        job["updated_at"] = datetime.now(timezone.utc).isoformat()
    return changed


def hydrate_milestone_standalone_from_disk(h, state: dict, job_name: str) -> bool:
    """Fill empty milestone ``standalone`` slot from newest assembled export on disk."""
    if not is_milestone_stitch_job_name(job_name):
        return False
    mid = milestone_id_from_stitch_job_name(job_name)
    if not mid:
        return False
    jobs = state.setdefault("jobs", {})
    job = jobs.setdefault(
        job_name,
        {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "slots": {"standalone": {}},
            "transitions": [],
        },
    )
    if not isinstance(job.get("slots"), dict):
        job["slots"] = {"standalone": {}}
    slot = job["slots"].setdefault("standalone", {})
    if _slot_has_video(slot):
        return False
    root = h._stitch_project_root()
    assembled = root / "Production" / "Milestones" / mid / "assembled"
    candidates: list[Path] = []
    if assembled.is_dir():
        for pattern in STITCH_ASSEMBLED_SLOT_GLOBS.get("standalone", ()):
            candidates.extend(assembled.glob(pattern))
    picked = _pick_newest_playable_mp4(candidates)
    if picked is None:
        return False
    try:
        rel = str(picked.resolve().relative_to(root))
    except ValueError:
        return False
    slot["video_path"] = rel
    slot["source"] = STITCH_SLOT_ASSEMBLED_DISK_HYDRATE_V1
    sync_stitch_slot_video_dur_ms(h, slot, force=True)
    apply_stitch_slot_default_ambient_preset("standalone", slot)
    normalize_job_slots_audio(job["slots"])
    job["updated_at"] = datetime.now(timezone.utc).isoformat()
    return True


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


def _stitch_video_path_epoch(h, path: str) -> float:
    """Monotonic sort key for stitch slot video_path (higher = newer export)."""
    raw = (path or "").strip()
    if not raw:
        return 0.0
    m = re.search(r"(\d{8})T(\d{6})Z", raw)
    if m:
        try:
            dt = datetime.strptime(f"{m.group(1)}{m.group(2)}", "%Y%m%d%H%M%S").replace(
                tzinfo=timezone.utc,
            )
            return dt.timestamp()
        except ValueError:
            pass
    try:
        return Path(h._stitch_resolve_path(raw)).stat().st_mtime
    except (ValueError, OSError):
        return 0.0


def _stitch_should_skip_video_replace(h, old_path: str, new_path: str) -> bool:
    """Keep stored slot video when an incoming export is same age or older."""
    old_path = (old_path or "").strip()
    new_path = (new_path or "").strip()
    if not old_path or not new_path or old_path == new_path:
        return False
    return _stitch_video_path_epoch(h, new_path) <= _stitch_video_path_epoch(h, old_path)


def stitch_upsert_event_slot(
    h,
    event_id: str,
    slot_key: str,
    slot_patch: dict,
    *,
    beat_boundaries: list | None = None,
    operator_export: bool = False,
    job_name: str | None = None,
) -> tuple[str, int, list[str]]:
    """Upsert one slot into the canonical per-event stitch job.

    STITCH_SLOT_EXPORT_FULL_MEDIA_V1: every caller (Beat Gen intro/resolution,
    Phase A/B export, scene assemble) must pass video_path; full file is probed,
    playability-checked, and video_dur_ms is written before persist.
    """
    resolved_job = job_name or stitch_event_job_name(event_id)
    if not _valid_stitch_slot(slot_key, job_name=resolved_job):
        raise ValueError(f"invalid stitch slot key: {slot_key!r}")

    new_video_path = (slot_patch.get("video_path") or "").strip()
    if not new_video_path:
        raise ValueError(
            f"{slot_key}: video_path required for stitch export "
            f"({STITCH_SLOT_EXPORT_FULL_MEDIA_V1})",
        )

    job_name = resolved_job
    stitch_store = stitch_state_store_for_job(h, job_name)
    peek_state = stitch_store.read_state()
    peek_job = (peek_state.get("jobs") or {}).get(job_name) or {}
    peek_slots = peek_job.get("slots") if isinstance(peek_job.get("slots"), dict) else {}
    peek_slot = peek_slots.get(slot_key) if isinstance(peek_slots, dict) else {}
    old_video_path = (peek_slot.get("video_path") or "").strip() if isinstance(peek_slot, dict) else ""
    if (
        not operator_export
        and _stitch_should_skip_video_replace(h, old_video_path, new_video_path)
    ):
        kept_ms = int(peek_slot.get("video_dur_ms") or 0) if isinstance(peek_slot, dict) else 0
        return job_name, kept_ms, [
            f"{slot_key}: kept existing export (incoming video not newer than stored)",
        ]

    probed_ms, export_warnings = stitch_slot_export_media_preflight(
        h,
        new_video_path,
        slot_key,
        beat_boundaries=beat_boundaries,
    )
    patched = dict(slot_patch)
    patched["video_dur_ms"] = probed_ms

    now_iso = datetime.now(timezone.utc).isoformat()

    def upsert(state: dict) -> None:
        if not is_milestone_stitch_job_name(job_name):
            stitch_migrate_legacy_to_canonical(state, event_id)
        jobs = state.setdefault("jobs", {})
        if job_name not in jobs:
            jobs[job_name] = {
                "created_at": now_iso,
                "updated_at": now_iso,
                "slots": {},
                "transitions": [],
            }
        job = jobs[job_name]
        if not isinstance(job.get("slots"), dict):
            job["slots"] = {}
        slot = job["slots"].setdefault(slot_key, {})
        old_video_path = (slot.get("video_path") or "").strip()
        slot.update(patched)
        new_path = (slot.get("video_path") or "").strip()
        from server_handlers.stitch_media_artifacts import (  # noqa: PLC0415
            clear_stitch_slot_artifacts_on_video_change,
        )

        clear_stitch_slot_artifacts_on_video_change(slot, old_video_path, new_path)
        video_path_changed = bool(new_path and new_path != old_video_path)
        sync_stitch_slot_video_dur_ms(h, slot, force=True)
        stored_ms = int(slot.get("video_dur_ms") or 0)
        if abs(stored_ms - probed_ms) > STITCH_VIDEO_DUR_DRIFT_TOLERANCE_MS:
            slot["video_dur_ms"] = probed_ms
        apply_stitch_slot_default_ambient_preset(slot_key, slot)
        if video_path_changed:
            _clear_canonical_sfx_dismiss_flags(slot, slot_key)
        if slot_key in STITCH_SLOT_CANONICAL_DEFAULT_SFX:
            ensure_stitch_slot_canonical_default_sfx_cues(h, slot_key, slot)
        normalize_slot_audio_mix_levels(slot)
        if beat_boundaries is not None:
            slot["beat_boundaries"] = enrich_beat_boundaries(beat_boundaries)
        job["updated_at"] = now_iso

    stitch_store.mutate_state(upsert)

    # STITCH_EXPORT_ATOMIC_V1 — operator export skips pre-bake validate that clears
    # mux/ambient hashes before ensure_stitch_slot_playback_artifacts_on_export runs.
    if not operator_export:
        def heal_slot_artifacts(state: dict) -> None:
            job = (state.get("jobs") or {}).get(job_name)
            if not isinstance(job, dict):
                return
            slots = job.get("slots")
            if not isinstance(slots, dict):
                return
            slot = slots.get(slot_key)
            if not isinstance(slot, dict):
                return
            from server_handlers.stitch_media_artifacts import (  # noqa: PLC0415
                validate_stitch_slot_media_artifacts,
            )

            try:
                validate_stitch_slot_media_artifacts(h, slot)
            except AttributeError:
                pass

        stitch_store.mutate_state(heal_slot_artifacts)
    playback_artifacts = ensure_stitch_slot_playback_artifacts_on_export(
        h,
        job_name,
        slot_key,
        stitch_store=stitch_store,
    )
    _require_playback_artifacts_on_write(slot_key, playback_artifacts)
    if playback_artifacts.get("ok"):
        export_warnings = list(export_warnings or [])
        kind = playback_artifacts.get("kind")
        if kind == "mux_preview":
            export_warnings.append(
                f"{slot_key}: mux preview baked ({playback_artifacts.get('mux_preview_hash')})",
            )
        elif kind == "ambient_mix":
            export_warnings.append(
                f"{slot_key}: ambient mix baked ({playback_artifacts.get('ambient_mix_hash')})",
            )
    return job_name, probed_ms, export_warnings, playback_artifacts


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

    # Run ffmpeg single-pass loudnorm via shared AUTO_LOUDNORM_V1 helper.
    from server_handlers.speech_loudnorm import apply_speech_loudnorm_to_mp4  # noqa: PLC0415

    try:
        out_path, applied = apply_speech_loudnorm_to_mp4(
            ip,
            output_path=op,
            target_lufs=target_lufs,
            target_tp=target_tp,
            target_lra=target_lra,
            force=True,
        )
    except RuntimeError as exc:
        msg = str(exc)
        if "timed out" in msg.lower():
            return h._send_error_v59(
                504,
                error_code="FFMPEG_LOUDNORM_TIMED_OUT",
                error_message="ffmpeg loudnorm timed out (>600s)",
                retry_safe=True,
            )
        return h._send_error_v59(
            500,
            error_code="FFMPEG_LOUDNORM_FAILED",
            error_message="ffmpeg loudnorm failed",
            retry_safe=True,
            extra={"stderr": msg[-2000:]},
        )
    op = out_path

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


def _job_canonical_slots_have_video(state: dict, event_id: str) -> bool:
    """True when persisted canonical job already has video on every slot."""
    job_name = stitch_event_job_name(event_id)
    job = (state.get("jobs") or {}).get(job_name)
    if not isinstance(job, dict):
        return False
    slots = job.get("slots")
    if not isinstance(slots, dict):
        return False
    for slot_key in STITCH_SLOT_ORDER:
        slot = slots.get(slot_key)
        if not isinstance(slot, dict) or not (slot.get("video_path") or "").strip():
            return False
    return True


def handle_stitch_load_job(h, name: str)-> None:

    """GET /api/stitch_editor/job/<name> — load full job dict."""
    legacy_mid = legacy_milestone_id_from_stitch_job_name(name)
    if legacy_mid:
        purge_legacy_milestone_stitch_jobs_from_global(h)
        canonical = stitch_milestone_job_name(legacy_mid)
        return h._send_error_v59(
            409,
            error_code="LEGACY_STITCH_JOB_NAME",
            error_message=(
                f"Stitch job {name!r} uses a retired milestone name; "
                f"use {canonical!r} (milestone-local stitch_state.json)."
            ),
            retry_safe=False,
            hint=f"/api/stitch_editor/job/{canonical}",
        )

    stitch_store = stitch_state_store_for_job(h, name)
    milestone_job = is_milestone_stitch_job_name(name)
    if milestone_job:
        purge_milestone_job_from_global_stitch_state(h, name)
        purge_legacy_milestone_stitch_jobs_from_global(h)
        purge_event_jobs_from_milestone_stitch_store(stitch_store)

    # STITCH_SINGLE_OWNER_V1 — pipeline assembled/ MP4s enter stitch_state via
    # stitch_upsert_event_slot (Send to Stitcher) or stitch_save_job — never load_job.

    import copy  # noqa: PLC0415

    from server_handlers.stitch_media_artifacts import (  # noqa: PLC0415
        attach_stitch_slot_derived_media_urls,
        validate_stitch_slot_media_artifacts,
    )
    from server_handlers.stitch_media_sig import STITCH_LOAD_JOB_FAST_V1  # noqa: PLC0415

    state = stitch_store.read_state()
    job = state.get("jobs", {}).get(name)
    job_persisted = isinstance(job, dict)
    payload_boot: dict | None = None
    if job is None and milestone_job:
        job = {
            "slots": {"standalone": {}},
            "transitions": [],
        }
    elif job is None and _EVENT_STITCH_JOB_RE.match(name):
        event_id = name[: -len("_stitch")]
        boot = ensure_event_stitch_job_registered(
            h,
            event_id,
            hydrate_from_disk=False,
        )
        state = stitch_store.read_state() or {}
        job = state.get("jobs", {}).get(name)
        job_persisted = isinstance(job, dict)
        if job is None:
            return h._send_error_v59(
                       404,
                       error_code="GENERIC_ERROR",
                       error_message=f"Job not found: {name!r}",
                       retry_safe=False,
                   )
        if boot.get("changed"):
            payload_boot = {
                "event_stitch_job_bootstrap": boot,
                "bootstrap_code": EVENT_STITCH_JOB_BOOTSTRAP_V1,
            }
    elif job is None:
        return h._send_error_v59(
                   404,
                   error_code="GENERIC_ERROR",
                   error_message=f"Job not found: {name!r}",
                   retry_safe=False,
               )
    milestone_normalized = False
    if milestone_job and isinstance(job, dict):
        milestone_normalized = normalize_milestone_stitch_job(job, job_name=name)
        if milestone_normalized and job_persisted:

            def persist_milestone_shape(state: dict) -> None:
                j = state.setdefault("jobs", {}).setdefault(name, {})
                j.update(job)

            stitch_store.mutate_state(persist_milestone_shape)
    defaults_changed = False
    artifact_warnings: list[str] = []
    artifacts_healed = False
    live_slots = (job.get("slots") if isinstance(job, dict) else None)
    if isinstance(live_slots, dict):
        normalize_job_slots_audio(live_slots)
        defaults_changed = ensure_job_slot_defaults(h, live_slots, fast=True)
        timeline_atomic_changed = False
        for slot in live_slots.values():
            if isinstance(slot, dict) and ensure_stitch_slot_timeline_dur_ms(h, slot):
                timeline_atomic_changed = True
        if timeline_atomic_changed:
            defaults_changed = True
        for slot in live_slots.values():
            if isinstance(slot, dict) and slot.get("beat_boundaries"):
                slot["beat_boundaries"] = enrich_beat_boundaries(
                    slot["beat_boundaries"],
                )

        # mix_sig / ambient_mix_sig are computed with hydrated ambient_bed_path (export
        # and load_job bake). Validate before hydrate falsely clears mux/ambient artifacts.
        for slot in live_slots.values():
            if not isinstance(slot, dict):
                continue
            before_amb_path = (slot.get("ambient_bed_path") or "").strip()
            ensure_slot_ambient_bed_path_hydrated(h, slot)
            if (slot.get("ambient_bed_path") or "").strip() != before_amb_path:
                defaults_changed = True

        mux_cleared_on_load = False
        for slot_key, slot in live_slots.items():
            if not isinstance(slot, dict):
                continue
            before_mux = (slot.get("mux_preview_hash") or "").strip()
            artifact_warnings.extend(
                validate_stitch_slot_media_artifacts(h, slot, fast=True),
            )
            after_mux = (slot.get("mux_preview_hash") or "").strip()
            if before_mux and before_mux != after_mux:
                artifacts_healed = True
                mux_cleared_on_load = True
            attach_stitch_slot_derived_media_urls(h, slot)
        if mux_cleared_on_load and job_persisted:

            def persist_mux_clears(state: dict) -> None:
                _persist_stitch_job_healed_slots(state, name, live_slots)

            stitch_store.mutate_state(persist_mux_clears)

    response_job = copy.deepcopy(job) if isinstance(job, dict) else job
    if isinstance(response_job, dict) and isinstance(live_slots, dict):
        response_slots = response_job.setdefault("slots", {})
        for slot_key, slot_val in live_slots.items():
            response_slots[slot_key] = copy.deepcopy(slot_val)
    canonical_bake_path = None if milestone_job else _canonical_module_final_bake_path(h)
    hydrated_bake_path: str | None = None
    bake_path_hydrated = False
    if isinstance(response_job, dict) and canonical_bake_path and not (
        response_job.get("bake_path") or ""
    ).strip():
        response_job["bake_path"] = canonical_bake_path
        hydrated_bake_path = canonical_bake_path
        bake_path_hydrated = True
    if milestone_job and isinstance(response_job, dict):
        mid = milestone_id_from_stitch_job_name(name) or ""
        if mid and not (response_job.get("bake_path") or "").strip():
            canonical_milestone = _canonical_milestone_standalone_final_path(h, mid)
            if canonical_milestone:
                response_job["bake_path"] = canonical_milestone
                hydrated_bake_path = canonical_milestone
                bake_path_hydrated = True
    if job_persisted and isinstance(live_slots, dict) and (
        defaults_changed
        or artifacts_healed
        or _job_canonical_audio_needs_persist(live_slots, live_slots)
    ):

        def persist_job_slots(state: dict) -> None:
            _persist_stitch_job_canonical_audio(state, name, live_slots)
            if artifacts_healed:
                _persist_stitch_job_healed_slots(state, name, live_slots)

        stitch_store.mutate_state(persist_job_slots)
    if bake_path_hydrated and job_persisted and hydrated_bake_path:

        def persist_bake_path(state: dict) -> None:
            j = state.setdefault("jobs", {}).setdefault(name, {})
            j["bake_path"] = hydrated_bake_path

        stitch_store.mutate_state(persist_bake_path)
    module_final_cache_key: str | None = None
    payload = {
        "job": response_job,
        "name": name,
        "job_persisted": job_persisted,
        "load_job_code": STITCH_LOAD_JOB_FAST_V1,
        "single_owner_code": STITCH_SINGLE_OWNER_V1,
    }
    if payload_boot:
        payload.update(payload_boot)
    payload["write_time_playback_code"] = STITCH_WRITE_TIME_PLAYBACK_ARTIFACTS_V1
    if milestone_job and not job_persisted:
        payload["ephemeral_milestone_job"] = True
    from server_handlers.stitch_scope import STITCH_SCOPE_PARTITION_V1  # noqa: PLC0415

    payload["partition_code"] = STITCH_SCOPE_PARTITION_V1
    if isinstance(response_job, dict):
        slots = response_job.get("slots")
        if isinstance(slots, dict):
            warnings = collect_stitch_job_slot_warnings(h, slots, probe_video=False)
            if artifact_warnings:
                warnings = warnings or {}
                for msg in artifact_warnings:
                    warnings.setdefault("_artifacts", []).append(msg)
            if warnings:
                payload["slot_warnings"] = warnings
            if defaults_changed:
                payload["defaults_applied"] = True
                payload["code"] = STITCH_CANONICAL_DEFAULTS_PERSIST_V1
    from stitch_bake_job_store import STITCH_BAKE_JOB_TRUTH_V1, active_bake_job_summary  # noqa: PLC0415

    lock_path = h._stitch_cache_dir() / "stitch_bake.lock"
    bake_summary = active_bake_job_summary(h.app.event_dir, name, lock_path=lock_path)
    if bake_summary:
        payload["bake_job"] = bake_summary
        payload["bake_job_code"] = STITCH_BAKE_JOB_TRUTH_V1
    payload["module_final_url"] = f"/api/stitch_editor/module_final"
    if milestone_job:
        mid = milestone_id_from_stitch_job_name(name) or ""
        if mid:
            from lib.milestone_store import load_milestone_state  # noqa: PLC0415

            mdir = _milestone_dir_for_stitch_job(h, name)
            if mdir and mdir.is_dir():
                mstate = load_milestone_state(mdir)
                cache_key = (
                    mstate.get("canonical_standalone_final_sha256")
                    or mstate.get("canonical_standalone_final_mtime")
                )
                if cache_key:
                    module_final_cache_key = str(cache_key)
    else:
        prod_state_path = Path(h.app.event_dir) / "production_state.json"
        if prod_state_path.is_file():
            try:
                prod_state = json.loads(prod_state_path.read_text(encoding="utf-8"))
                cache_key = (
                    prod_state.get("canonical_module_final_sha256")
                    or prod_state.get("canonical_module_final_mtime")
                )
                if cache_key:
                    module_final_cache_key = str(cache_key)
            except (OSError, json.JSONDecodeError):
                pass
    if module_final_cache_key:
        payload["module_final_cache_key"] = module_final_cache_key
        if isinstance(response_job, dict):
            response_job["module_final_cache_key"] = module_final_cache_key
    from server_handlers.stitch_artifact_build import (  # noqa: PLC0415
        STITCH_SAVE_ASYNC_ARTIFACTS_V1,
        build_poll_payload,
        find_active_build_for_stitch_job,
    )

    active_artifact = find_active_build_for_stitch_job(h.app.event_dir, name)
    if active_artifact:
        payload["artifact_build"] = build_poll_payload(active_artifact)
        payload["async_artifact_code"] = STITCH_SAVE_ASYNC_ARTIFACTS_V1
    return h._send_json(200, payload)


def handle_stitch_serve_module_final(h) -> None:
    """GET /api/stitch_editor/module_final — kid-facing canonical module MP4 (byte-range)."""
    import json as _json  # noqa: PLC0415

    milestone_id = (getattr(h.app, "active_milestone_id", None) or "").strip()
    if getattr(h.app, "scope_type", "event") == "milestone" and milestone_id:
        target_path = _canonical_milestone_standalone_final_path(h, milestone_id)
        if target_path:
            return h._serve_mp4_with_range(Path(target_path), cache_immutable=False)
        stitch_job = stitch_milestone_job_name(milestone_id)
        store = stitch_state_store_for_job(h, stitch_job)
        job = (store.read_state().get("jobs") or {}).get(stitch_job) or {}
        bake_path = (job.get("bake_path") or "").strip()
        if bake_path:
            try:
                target = h._stitch_resolve_path(bake_path)
                if target.is_file():
                    return h._serve_mp4_with_range(target, cache_immutable=False)
            except (ValueError, OSError):
                pass
        return h._send_error_v59(
            404,
            error_code="CANONICAL_MODULE_FINAL_MISSING",
            error_message="No milestone standalone final pinned yet — bake first",
            retry_safe=False,
        )

    state_path = Path(h.app.event_dir) / "production_state.json"
    if not state_path.is_file():
        return h._send_error_v59(
            404,
            error_code="CANONICAL_MODULE_FINAL_MISSING",
            error_message="production_state.json not found",
            retry_safe=False,
        )
    try:
        state = _json.loads(state_path.read_text(encoding="utf-8"))
    except _json.JSONDecodeError:
        return h._send_error_v59(
            500,
            error_code="GENERIC_ERROR",
            error_message="invalid production_state.json",
            retry_safe=False,
        )
    canonical_name = (state.get("canonical_module_final_file") or "").strip()
    if not canonical_name:
        return h._send_error_v59(
            404,
            error_code="CANONICAL_MODULE_FINAL_MISSING",
            error_message="No canonical module final pinned for this event",
            retry_safe=False,
        )
    target = (Path(h.app.event_dir) / canonical_name).resolve()
    event_root = Path(h.app.event_dir).resolve()
    if not str(target).startswith(str(event_root)) or not target.is_file():
        return h._send_error_v59(
            404,
            error_code="CANONICAL_MODULE_FINAL_MISSING",
            error_message=f"Canonical file not found: {canonical_name}",
            retry_safe=False,
        )
    h._serve_mp4_with_range(target, cache_immutable=False)


STITCH_AMBIENT_BAKE_ON_SAVE_V1 = "STITCH_AMBIENT_BAKE_ON_SAVE_V1"
STITCH_AMBIENT_FORCE_REBUILD_ON_EXPORT_V1 = "STITCH_AMBIENT_FORCE_REBUILD_ON_EXPORT_V1"
STITCH_EXPORT_MUX_BAKE_V1 = "STITCH_EXPORT_MUX_BAKE_V1"
STITCH_LOAD_JOB_PLAYBACK_BAKE_V1 = "STITCH_LOAD_JOB_PLAYBACK_BAKE_V1"


def _stitch_slot_needs_ambient_mix(slot: dict) -> bool:
    ambient = (slot.get("ambient_bed") or "").strip()
    return bool((slot.get("video_path") or "").strip() and ambient)


def build_stitch_slot_ambient_mix_file(h, slot: dict) -> tuple[str, int]:
    """Build se_slot_* with speech + ambient (no SFX). Returns (hash_stem, duration_ms)."""
    from server_handlers.stitch_media_artifacts import _stitch_slot_has_ambient  # noqa: PLC0415

    normalize_slot_audio_mix_levels(slot)
    ensure_slot_ambient_bed_path_hydrated(h, slot)
    if not _stitch_slot_has_ambient(slot):
        raise ValueError("ambient bed not configured")
    video_path = (slot.get("video_path") or "").strip()
    abs_vp = h._stitch_resolve_path(video_path)
    cache_dir = h._stitch_cache_dir()
    norm = h._stitch_normalize_slot(
        abs_vp, cache_dir, preview_only=True,
    )
    norm = h._stitch_ensure_audio(norm, cache_dir)
    mix_slot = dict(slot)
    mix_slot["sfx_cues"] = []
    mixed = h._stitch_mix_slot_audio(norm, mix_slot, cache_dir, force_rebuild=True)
    stem = mixed.stem
    if stem.startswith("se_slot_"):
        stem = stem[len("se_slot_"):]
    dur_ms = h._ffprobe_duration_ms(mixed)
    if dur_ms <= 0:
        raise RuntimeError(f"ambient mix unreadable for {video_path}")
    if not stitch_cached_mp4_playable(mixed, expected_s=dur_ms / 1000.0):
        purge_stitch_cache_mp4(mixed)
        raise RuntimeError(
            f"ambient mix failed playback gate ({STITCH_AMBIENT_BAKE_ON_SAVE_V1})",
        )
    return stem, dur_ms


def build_stitch_slot_mux_preview_file(h, slot: dict) -> tuple[str, int]:
    """Build stitch_preview_* MP4 with speech + ambient + SFX for one slot."""
    normalize_slot_audio_mix_levels(slot)
    _hydrate_slot_ambient_paths(h, [slot])
    body = {
        "slots": [dict(slot)],
        "slot_preview": True,
        "transitions": [],
        # STITCH_AMBIENT_FORCE_REBUILD_ON_EXPORT_V1 — export bake only; UI Review reuses se_slot_* cache.
        "force_ambient_mix_rebuild": True,
    }
    out_path, slot_durations, _ = h._stitch_build_pipeline(body)
    hash_id = out_path.stem.replace("stitch_preview_", "")
    dur_ms = int(slot_durations[0] if slot_durations else h._ffprobe_duration_ms(out_path))
    if dur_ms <= 0:
        raise RuntimeError("mux preview unreadable")
    if not stitch_cached_mp4_playable(out_path, expected_s=dur_ms / 1000.0):
        purge_stitch_cache_mp4(out_path)
        raise RuntimeError(
            f"mux preview failed playback gate ({STITCH_EXPORT_MUX_BAKE_V1})",
        )
    return hash_id, dur_ms


def ensure_stitch_slot_playback_artifacts(
    h,
    job_name: str,
    slot_key: str,
    *,
    stitch_store=None,
    trigger: str = "export",
) -> dict:
    """Bake mux (SFX slots) or ambient mix — export upsert and bootstrap hydrate only."""
    from server_handlers.stitch_media_artifacts import (  # noqa: PLC0415
        _stitch_slot_has_ambient,
        _stitch_slot_has_sfx,
        attach_stitch_slot_derived_media_urls,
        persist_stitch_slot_ambient_mix_artifacts,
        persist_stitch_slot_media_artifacts,
    )
    from server_handlers.stitch_media_sig import (  # noqa: PLC0415
        compute_stitch_ambient_mix_sig_from_slot,
        compute_stitch_mix_sig_from_slot,
        _video_mtime_ms,
    )

    stitch_store = stitch_store or stitch_state_store_for_job(h, job_name)
    bake_code = (
        STITCH_LOAD_JOB_PLAYBACK_BAKE_V1
        if trigger == "load_job"
        else STITCH_EXPORT_MUX_BAKE_V1
    )
    if not callable(getattr(h, "_stitch_cache_dir", None)):
        return {
            "slot": slot_key,
            "code": bake_code,
            "trigger": trigger,
            "skipped": "handler_incomplete",
        }
    orig_stitch_state = None
    if stitch_store is not h.app.stitch_state:
        orig_stitch_state = h.app.stitch_state
        h.app.stitch_state = stitch_store
    report: dict = {"slot": slot_key, "code": bake_code, "trigger": trigger}
    try:
        state = stitch_store.read_state() or {}
        job = (state.get("jobs") or {}).get(job_name)
        if not isinstance(job, dict):
            report["skipped"] = "job_missing"
            return report
        slot = (job.get("slots") or {}).get(slot_key)
        if not isinstance(slot, dict) or not (slot.get("video_path") or "").strip():
            report["skipped"] = "no_video"
            return report
        normalize_slot_audio_mix_levels(slot)
        _hydrate_slot_ambient_paths(h, [slot])
        if _stitch_slot_has_sfx(slot):
            mix_sig = compute_stitch_mix_sig_from_slot(h, slot)
            hash_id, dur_ms = build_stitch_slot_mux_preview_file(h, slot)
            video_path = (slot.get("video_path") or "").strip()
            mux_video_mtime_ms: int | None = None
            if video_path:
                try:
                    mux_video_mtime_ms = _video_mtime_ms(
                        str(h._stitch_resolve_path(video_path)),
                    )
                except (ValueError, TypeError, OSError):
                    mux_video_mtime_ms = None
            persist_stitch_slot_media_artifacts(
                h,
                job_name,
                slot_key,
                mix_sig=mix_sig,
                mux_preview_hash=hash_id,
                mux_preview_duration_ms=dur_ms,
                mux_video_path=video_path or None,
                mux_video_mtime_ms=mux_video_mtime_ms,
                persist_ambient_bed_path=(slot.get("ambient_bed_path") or "").strip() or None,
            )
            report.update({
                "ok": True,
                "kind": "mux_preview",
                "mux_preview_hash": hash_id,
                "mux_preview_duration_ms": dur_ms,
            })
            return report
        if _stitch_slot_has_ambient(slot):
            ambient_sig = compute_stitch_ambient_mix_sig_from_slot(h, slot)
            hash_stem, dur_ms = build_stitch_slot_ambient_mix_file(h, slot)
            persist_stitch_slot_ambient_mix_artifacts(
                h,
                job_name,
                slot_key,
                ambient_mix_sig=ambient_sig,
                ambient_mix_hash=hash_stem,
                ambient_mix_duration_ms=dur_ms,
            )
            attach_stitch_slot_derived_media_urls(h, slot)
            report.update({
                "ok": True,
                "kind": "ambient_mix",
                "ambient_mix_hash": hash_stem,
                "ambient_mix_duration_ms": dur_ms,
            })
            return report
        report["skipped"] = "speech_only"
        return report
    except (OSError, ValueError, RuntimeError) as exc:
        report["ok"] = False
        report["error"] = str(exc)
        return report
    finally:
        if orig_stitch_state is not None:
            h.app.stitch_state = orig_stitch_state


def ensure_stitch_slot_playback_artifacts_on_export(
    h,
    job_name: str,
    slot_key: str,
    *,
    stitch_store=None,
) -> dict:
    """Bake mux (SFX slots) or ambient mix after export upsert — Stitcher preview-ready."""
    return ensure_stitch_slot_playback_artifacts(
        h,
        job_name,
        slot_key,
        stitch_store=stitch_store,
        trigger="export",
    )


def rebuild_stitch_ambient_mixes_for_job(
    h,
    job_name: str,
    *,
    slot_keys: list[str] | None = None,
) -> dict:
    """Bake ambient mixes for slots; persist artifacts. Returns built_slots map."""
    from server_handlers.stitch_media_artifacts import (  # noqa: PLC0415
        attach_stitch_slot_derived_media_urls,
        clear_stitch_slot_ambient_mix_artifacts,
        persist_stitch_slot_ambient_mix_artifacts,
    )
    from server_handlers.stitch_media_sig import compute_stitch_ambient_mix_sig_from_slot  # noqa: PLC0415

    stitch_store = stitch_state_store_for_job(h, job_name)
    orig_stitch_state = None
    if stitch_store is not h.app.stitch_state:
        orig_stitch_state = h.app.stitch_state
        h.app.stitch_state = stitch_store
    try:
        state = stitch_store.read_state() or {}
        job = (state.get("jobs") or {}).get(job_name)
        if not isinstance(job, dict):
            return {}
        slots = job.get("slots") or {}
        if not isinstance(slots, dict):
            return {}
        if slot_keys is not None:
            keys = list(slot_keys)
        elif is_milestone_stitch_job_name(job_name):
            keys = list(STITCH_MILESTONE_SLOT_ORDER)
        else:
            keys = list(STITCH_SLOT_ORDER)
        built: dict = {}

        for slot_key in keys:
            slot = slots.get(slot_key)
            if not isinstance(slot, dict):
                continue
            if not (slot.get("video_path") or "").strip():
                continue
            ambient_bed = (slot.get("ambient_bed") or "").strip()
            if not ambient_bed:
                def clear_ambient(state: dict) -> None:
                    j = (state.get("jobs") or {}).get(job_name)
                    if not isinstance(j, dict):
                        return
                    s = (j.get("slots") or {}).get(slot_key)
                    if isinstance(s, dict):
                        clear_stitch_slot_ambient_mix_artifacts(s)

                stitch_store.mutate_state(clear_ambient)
                built[slot_key] = {"ok": True, "cleared": True, "code": STITCH_AMBIENT_BAKE_ON_SAVE_V1}
                continue
            try:
                ambient_sig = compute_stitch_ambient_mix_sig_from_slot(h, slot)
                stored_sig = (slot.get("ambient_mix_sig") or "").strip()
                stored_hash = (slot.get("ambient_mix_hash") or "").strip()
                # STITCH_AMBIENT_BAKE_SKIP_UNCHANGED_V1 — SFX-only saves must not
                # re-ffmpeg ambient; ambient sig excludes sfx_cues.
                if (
                    stored_sig
                    and stored_sig == ambient_sig
                    and stored_hash
                ):
                    cache_path = h._stitch_cache_dir() / f"se_slot_{stored_hash}.mp4"
                    dur_ms = int(slot.get("ambient_mix_duration_ms") or 0)
                    if dur_ms <= 0 and cache_path.is_file():
                        dur_ms = h._ffprobe_duration_ms(cache_path)
                    if (
                        cache_path.is_file()
                        and stitch_cached_mp4_playable(
                            cache_path,
                            expected_s=dur_ms / 1000.0 if dur_ms > 0 else None,
                        )
                    ):
                        attach_stitch_slot_derived_media_urls(h, slot)
                        built[slot_key] = {
                            "ok": True,
                            "skipped": True,
                            "ambient_mix_hash": stored_hash,
                            "ambient_mix_duration_ms": dur_ms,
                            "ambient_mix_sig": ambient_sig,
                            "_ambient_mix_url": slot.get("_ambient_mix_url"),
                            "code": STITCH_AMBIENT_BAKE_ON_SAVE_V1,
                        }
                        continue
                hash_stem, dur_ms = build_stitch_slot_ambient_mix_file(h, slot)
                persist_stitch_slot_ambient_mix_artifacts(
                    h,
                    job_name,
                    slot_key,
                    ambient_mix_sig=ambient_sig,
                    ambient_mix_hash=hash_stem,
                    ambient_mix_duration_ms=dur_ms,
                    ambient_mix_video_path=(slot.get("video_path") or "").strip() or None,
                )
                state = stitch_store.read_state() or {}
                refreshed = (
                    (state.get("jobs") or {}).get(job_name, {}).get("slots", {}).get(slot_key)
                )
                if isinstance(refreshed, dict):
                    attach_stitch_slot_derived_media_urls(h, refreshed)
                    built[slot_key] = {
                        "ok": True,
                        "ambient_mix_hash": hash_stem,
                        "ambient_mix_duration_ms": dur_ms,
                        "ambient_mix_sig": ambient_sig,
                        "_ambient_mix_url": refreshed.get("_ambient_mix_url"),
                        "code": STITCH_AMBIENT_BAKE_ON_SAVE_V1,
                    }
                else:
                    built[slot_key] = {
                        "ok": True,
                        "ambient_mix_hash": hash_stem,
                        "code": STITCH_AMBIENT_BAKE_ON_SAVE_V1,
                    }
            except Exception as exc:
                built[slot_key] = {
                    "ok": False,
                    "error": str(exc),
                    "code": STITCH_AMBIENT_BAKE_ON_SAVE_V1,
                }

        return built
    finally:
        if orig_stitch_state is not None:
            h.app.stitch_state = orig_stitch_state


def handle_stitch_save_job(h, body: dict)-> None:

    """POST /api/stitch_editor/job — save or upsert a named job."""
    from server_handlers.stitch_scope import (  # noqa: PLC0415
        STITCH_SCOPE_PARTITION_V1,
        assert_stitch_partition_scope,
    )

    name = (body.get("name") or "").strip()
    binding = assert_stitch_partition_scope(h, body, job_name=name)
    if binding is None:
        return
    name = binding.job_name
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

    merge_slots = bool(body.get("merge_slots")) or partial_ambient_merge

    # Slots may be dict keyed by slot id (v59 client + scene_assemble auto-populate)
    # or legacy list. Validate video_path on slot dict values only.
    if isinstance(slots_raw, dict):
        slots = slots_raw
        slot_items = [v for v in slots_raw.values() if isinstance(v, dict)]
    elif isinstance(slots_raw, list):
        if merge_slots or is_milestone_stitch_job_name(name):
            slots = _coerce_stitch_save_slots_to_dict(slots_raw, name, slot_key_partial)
            slot_items = [v for v in slots.values() if isinstance(v, dict)]
        else:
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
    scope = h._scope_body(body) or {}
    event_id = (scope.get("event_id") or scope.get("scope_event_id") or "").strip()
    stitch_store = binding.stitch_store
    orig_stitch_state = None
    if stitch_store is not h.app.stitch_state:
        orig_stitch_state = h.app.stitch_state
        h.app.stitch_state = stitch_store

    pre_state = stitch_store.read_state() or {}
    pre_job = (pre_state.get("jobs") or {}).get(name) or {}
    pre_slots = _normalize_job_slots(pre_job.get("slots") if isinstance(pre_job, dict) else {})
    touched_keys = (
        list(slots.keys()) if isinstance(slots, dict) else []
    )
    edit_kind_hint = (body.get("edit_kind") or "").strip() or None

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
                    normalize_slot_audio_mix_levels(merged)
                    from server_handlers.stitch_media_artifacts import (  # noqa: PLC0415
                        invalidate_stitch_slot_artifacts_if_mix_drift,
                    )

                    invalidate_stitch_slot_artifacts_if_mix_drift(h, merged)
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
                    normalize_slot_audio_mix_levels(merged)
                    from server_handlers.stitch_media_artifacts import (  # noqa: PLC0415
                        invalidate_stitch_slot_artifacts_if_mix_drift,
                    )

                    invalidate_stitch_slot_artifacts_if_mix_drift(h, merged)
                    base_slots[slot_key] = merged
            slots_out = base_slots
        elif not slot_items and existing.get("slots"):
            # Malformed save without merge_slots — preserve existing slots.
            slots_out = _normalize_job_slots(existing.get("slots"))
        else:
            slots_out = slots
        if isinstance(slots_out, dict):
            ensure_job_slot_defaults(
                h,
                slots_out,
                fast=True,
                apply_ambient_presets=bool(body.get("apply_canonical_defaults")),
            )
        normalize_job_slots_audio(slots_out if isinstance(slots_out, dict) else {})
        jobs[name] = {
            "created_at": existing.get("created_at", now_iso),
            "updated_at": now_iso,
            "slots": slots_out,
            "transitions": canonical_stitch_transitions_for_pipeline(
                transitions or existing.get("transitions"),
            ),
        }
        if is_milestone_stitch_job_name(name):
            normalize_milestone_stitch_job(jobs[name], job_name=name)

    try:
        from server_handlers.stitch_artifact_build import STITCH_ARTIFACT_ORCHESTRATOR_V1  # noqa: PLC0415
        from server_handlers.stitch_slot_edit_dispatch import (  # noqa: PLC0415
            STITCH_SLOT_EDIT_DISPATCH_V1,
            plan_stitch_save_dispatch,
        )

        dispatch: dict = {}
        stitch_store.mutate_state(upsert)
        post_state = stitch_store.read_state() or {}
        post_job = (post_state.get("jobs") or {}).get(name) or {}
        post_slots = _normalize_job_slots(
            post_job.get("slots") if isinstance(post_job, dict) else {},
        )
        dispatch = plan_stitch_save_dispatch(
            h,
            prev_slots=pre_slots,
            next_slots=post_slots,
            touched_keys=touched_keys,
            edit_kind_hint=edit_kind_hint,
        )
        ambient_keys = dispatch.get("ambient_rebuild_keys") or []
        mux_keys = dispatch.get("mux_rebuild_hint_keys") or []
        built_slots: dict = {}
        artifact_build: dict = {
            "code": STITCH_ARTIFACT_ORCHESTRATOR_V1,
            "async_artifact_code": STITCH_SAVE_ASYNC_ARTIFACTS_V1,
            "status": "idle",
            "ambient_rebuild_keys": ambient_keys,
            "mux_rebuild_keys": mux_keys,
        }
        if ambient_keys or mux_keys:
            from server_handlers.stitch_artifact_build import (  # noqa: PLC0415
                STITCH_ARTIFACT_ORCHESTRATOR_V1,
                build_poll_payload,
                submit_stitch_artifact_build_plan,
            )

            _pin = {
                "pinned_generation": getattr(h.app, "event_generation", None),
                "pinned_event_dir": h.app.event_dir,
                "pinned_video_role": (body or {}).get("scope_video_role", "intro"),
                "_handler": "handle_stitch_save_job",
            }
            queued = submit_stitch_artifact_build_plan(
                h,
                stitch_job_name=name,
                ambient_keys=ambient_keys,
                mux_keys=mux_keys,
                pin=_pin,
                trigger="save_job",
            )
            if queued:
                artifact_build = build_poll_payload(queued)
                artifact_build["status"] = queued.get("status") or "queued"
    finally:
        if orig_stitch_state is not None:
            h.app.stitch_state = orig_stitch_state
    saved_standalone = (
        (post_slots.get("standalone") or {})
        if isinstance(post_slots, dict)
        else {}
    )
    return h._send_json(200, {
        "ok": True,
        "name": name,
        "job_persisted": True,
        "saved_slots": post_slots,
        "saved_video_path": (saved_standalone.get("video_path") or "").strip(),
        "built_slots": built_slots,
        "edit_dispatch": dispatch,
        "artifact_build": artifact_build,
        "code": STITCH_AMBIENT_BAKE_ON_SAVE_V1,
        "async_artifact_code": STITCH_SAVE_ASYNC_ARTIFACTS_V1,
        "orchestrator_code": STITCH_ARTIFACT_ORCHESTRATOR_V1,
        "dispatch_code": STITCH_SLOT_EDIT_DISPATCH_V1,
        "single_owner_code": STITCH_SINGLE_OWNER_V1,
        "partition_code": STITCH_SCOPE_PARTITION_V1,
    })


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
    Output: {audio_url: "http://<Host>/api/stitch_editor/audio_file/<hash>", duration_ms: N}
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

    video_dur_ms = h._ffprobe_duration_ms(Path(abs_path))
    if video_dur_ms <= 0:
        return h._send_error_v59(
            400,
            error_code="STITCH_SLOT_VIDEO_UNREADABLE",
            error_message=f"cannot probe video duration: {video_path_str}",
            retry_safe=False,
            extra={"code": STITCH_SLOT_MEDIA_LINEAGE_DURABILITY_V1},
        )
    from credentials_lib.ffmpeg_stitch import (  # noqa: PLC0415
        ffprobe_stream_duration_s,
        stitch_audio_cache_is_valid,
    )

    video_stream_ms = int(round(ffprobe_stream_duration_s(Path(abs_path), "v") * 1000))
    audio_stream_ms = int(round(ffprobe_stream_duration_s(Path(abs_path), "a") * 1000))
    if video_stream_ms > 0 and audio_stream_ms > 0 and stitch_slot_av_drift_exceeds(
        video_stream_ms, audio_stream_ms,
    ):
        drift_ms = abs(video_stream_ms - audio_stream_ms)
        return h._send_error_v59(
            409,
            error_code="STITCH_SLOT_AV_DRIFT",
            error_message=(
                f"slot video/audio misaligned ({drift_ms}ms) — "
                "rebuild canonical intro tail or re-export from Beat Gen"
            ),
            retry_safe=True,
            extra={
                "code": STITCH_SLOT_MEDIA_LINEAGE_DURABILITY_V1,
                "video_dur_ms": video_stream_ms,
                "audio_dur_ms": audio_stream_ms,
                "drift_ms": drift_ms,
            },
        )
    expected_s = video_dur_ms / 1000.0

    from credentials_lib.stitch_cache_build import (  # noqa: PLC0415
        StitchCacheBuildBusy,
        atomic_ffmpeg_output,
        stitch_cache_build_lock,
    )

    try:
        with stitch_cache_build_lock(cache_dir):
            if audio_path.is_file() and not stitch_audio_cache_is_valid(
                audio_path, expected_s, min_ratio=STITCH_AUDIO_DUR_MIN_RATIO,
            ):
                try:
                    audio_path.unlink()
                except OSError:
                    pass

            if not audio_path.is_file():
                safe_ffmpeg_src = os.path.realpath(abs_path)
                cmd = [
                    "ffmpeg", "-y", "-i", safe_ffmpeg_src,
                    "-vn", "-ac", "1", "-ar", "44100", "-b:a", "128k",
                    str(audio_path.resolve()),
                ]
                try:
                    atomic_ffmpeg_output(
                        cmd,
                        audio_path,
                        expected_duration_s=expected_s,
                        validator=lambda p, exp: stitch_audio_cache_is_valid(
                            p, exp, min_ratio=STITCH_AUDIO_DUR_MIN_RATIO,
                        ),
                    )
                except subprocess.CalledProcessError as exc:
                    stderr = (exc.stderr or b"")[:400].decode("utf-8", errors="replace")
                    return h._send_error_v59(
                               500,
                               error_code="AUDIO_EXTRACTION_FAILED",
                               error_message="audio extraction failed",
                               retry_safe=True,
                               extra={"stderr": stderr},
                           )
                except RuntimeError as exc:
                    return h._send_error_v59(
                        500,
                        error_code="STITCH_SLOT_AUDIO_EXTRACT_TRUNCATED",
                        error_message=str(exc),
                        retry_safe=True,
                        extra={"code": STITCH_SLOT_MEDIA_LINEAGE_DURABILITY_V1},
                    )
    except StitchCacheBuildBusy as exc:
        return h._send_error_v59(
            409,
            error_code="STITCH_CACHE_BUILD_IN_PROGRESS",
            error_message=str(exc),
            retry_safe=True,
            extra={"code": STITCH_SLOT_MEDIA_ARTIFACTS_V1},
        )

    duration_ms = h._ffprobe_duration_ms(audio_path)
    if not stitch_audio_cache_is_valid(
        audio_path, expected_s, min_ratio=STITCH_AUDIO_DUR_MIN_RATIO,
    ):
        return h._send_error_v59(
            500,
            error_code="STITCH_SLOT_AUDIO_EXTRACT_TRUNCATED",
            error_message=(
                f"slot audio extract {duration_ms}ms ≠ video {video_dur_ms}ms — "
                "re-extract failed"
            ),
            retry_safe=True,
            extra={
                "code": STITCH_SLOT_MEDIA_LINEAGE_DURABILITY_V1,
                "duration_ms": duration_ms,
                "video_dur_ms": video_dur_ms,
            },
        )

    serve_fname = audio_fname
    # STITCH_AMBIENT_BAKE_ON_SAVE_V1 — waveform peaks are speech-only; ambient is composer bake.
    sfx_raw = body.get("sfx_cues")
    sfx_mixed = False
    mix_slot: dict = {}
    if isinstance(sfx_raw, list) and [c for c in sfx_raw if isinstance(c, dict)]:
        mix_slot["sfx_cues"] = [c for c in sfx_raw if isinstance(c, dict)]
    if mix_slot:
        _hydrate_slot_ambient_paths(h, [mix_slot])
        try:
            mixed_path = _mix_stitch_waveform_audio(
                h,
                audio_path,
                mix_slot,
                cache_dir,
                cache_key,
                expected_video_dur_ms=video_dur_ms,
            )
        except RuntimeError as exc:
            return h._send_error_v59(
                       500,
                       error_code="SLOT_AUDIO_MIX_FAILED",
                       error_message=str(exc),
                       retry_safe=True,
                       extra={"code": STITCH_SLOT_MEDIA_LINEAGE_DURABILITY_V1},
                   )
        if mixed_path is not None:
            serve_fname = mixed_path.name
            duration_ms = h._ffprobe_duration_ms(mixed_path)
            sfx_mixed = bool(mix_slot.get("_sfx_mixed"))
            if not stitch_audio_cache_is_valid(
                mixed_path, expected_s, min_ratio=STITCH_AUDIO_DUR_MIN_RATIO,
            ):
                return h._send_error_v59(
                    500,
                    error_code="STITCH_SLOT_AUDIO_MIX_TRUNCATED",
                    error_message=(
                        f"slot audio mix {duration_ms}ms ≠ video {video_dur_ms}ms"
                    ),
                    retry_safe=True,
                    extra={
                        "code": STITCH_SLOT_MEDIA_LINEAGE_DURABILITY_V1,
                        "duration_ms": duration_ms,
                        "video_dur_ms": video_dur_ms,
                    },
                )

    peaks_url = None
    peaks_duration_s = None
    peaks_hash = None
    try:
        from waveform_peaks import generate_peaks_from_audio, write_peaks_json

        serve_audio_path = cache_dir / serve_fname
        peaks_stem = serve_fname.replace("stitch_audio_", "").replace(".mp3", "")
        peaks_fname = f"stitch_peaks_{peaks_stem}.json"
        peaks_path = cache_dir / peaks_fname
        if serve_audio_path.is_file():
            if not peaks_path.is_file():
                peaks_payload = generate_peaks_from_audio(serve_audio_path)
                with stitch_cache_build_lock(cache_dir):
                    tmp_peaks = peaks_path.parent / (
                        f"{peaks_path.stem}.tmp.{os.getpid()}.json"
                    )
                    write_peaks_json(peaks_payload, tmp_peaks)
                    os.replace(tmp_peaks, peaks_path)
                peaks_duration_s = peaks_payload.get("duration_s")
            else:
                try:
                    import json as _json

                    peaks_duration_s = float(
                        _json.loads(peaks_path.read_text(encoding="utf-8")).get("duration_s") or 0,
                    )
                except (OSError, TypeError, ValueError):
                    peaks_payload = generate_peaks_from_audio(serve_audio_path)
                    with stitch_cache_build_lock(cache_dir):
                        tmp_peaks = peaks_path.parent / (
                            f"{peaks_path.stem}.tmp.{os.getpid()}.json"
                        )
                        write_peaks_json(peaks_payload, tmp_peaks)
                        os.replace(tmp_peaks, peaks_path)
                    peaks_duration_s = peaks_payload.get("duration_s")
            peaks_hash = peaks_stem
            peaks_url = _stitch_media_public_url(
                h, f"/api/stitch_editor/peaks_file/{peaks_fname}",
            )
    except StitchCacheBuildBusy as exc:
        return h._send_error_v59(
            409,
            error_code="STITCH_CACHE_BUILD_IN_PROGRESS",
            error_message=str(exc),
            retry_safe=True,
            extra={"code": STITCH_SLOT_MEDIA_ARTIFACTS_V1},
        )
    except Exception as exc:
        print(f"[stitch_audio_extract] peaks generation failed (non-fatal): {exc}", flush=True)

    mix_sig = None
    from server_handlers.stitch_media_artifacts import (  # noqa: PLC0415
        find_stitch_job_slot_for_video,
        persist_stitch_slot_media_artifacts,
    )
    from server_handlers.stitch_media_sig import compute_stitch_mix_sig_from_slot  # noqa: PLC0415

    job_slot = find_stitch_job_slot_for_video(h, video_path_str)
    if job_slot:
        job_name, slot_key = job_slot
        state = h.app.stitch_state.read_state() or {}
        job = (state.get("jobs") or {}).get(job_name) or {}
        slot = (job.get("slots") or {}).get(slot_key)
        if isinstance(slot, dict):
            mix_sig = compute_stitch_mix_sig_from_slot(h, slot)
            if peaks_hash:
                persist_stitch_slot_media_artifacts(
                    h,
                    job_name,
                    slot_key,
                    mix_sig=mix_sig,
                    waveform_peaks_hash=peaks_hash,
                    waveform_peaks_duration_s=peaks_duration_s,
                )

    return h._send_json(200, {
        "audio_url": _stitch_media_public_url(h, f"/api/stitch_editor/audio_file/{serve_fname}"),
        "peaks_url": peaks_url,
        "peaks_duration_s": peaks_duration_s,
        "peaks_hash": peaks_hash,
        "mix_sig": mix_sig,
        "duration_ms": duration_ms,
        "video_dur_ms": video_dur_ms,
        "ambient_mixed": bool(mix_slot.get("ambient_bed_path")),
        "sfx_mixed": sfx_mixed,
        "code": STITCH_SLOT_MEDIA_ARTIFACTS_V1,
    })


_STITCH_SLOT_ORDER = ["intro", "phase_a", "phase_b", "resolution"]
_DEFAULT_PHASE_TRANSITION_FADE_MS = 2800

# STITCH_CANONICAL_TRANSITIONS_V1 — module boundaries always fade-through-black like intro.
STITCH_CANONICAL_TRANSITIONS_V1 = "STITCH_CANONICAL_TRANSITIONS_V1"

# STITCH_CANONICAL_TRANSITION_SFX_V1 — magic/windy SFX span each dissolve (pipeline-injected).
STITCH_CANONICAL_TRANSITION_SFX_V1 = "STITCH_CANONICAL_TRANSITION_SFX_V1"
STITCH_TRANSITION_SFX_PRE_ROLL_MS = 500
STITCH_TRANSITION_SFX_POST_ROLL_MS = 500
STITCH_TRANSITION_SFX_VOLUME = STITCH_SFX_CUE_DEFAULT_VOLUME
STITCH_CANONICAL_BOUNDARY_SFX: dict[int, str] = {
    0: "magic_sound.mp3",   # intro → phase_a
    1: "windy_magic.mp3",   # phase_a → phase_b
    2: "magic_sound.mp3",   # phase_b → resolution
}


def module_boundary_visual_out_ms_by_pair(pair_count: int, default_out_ms: int) -> list[int]:
    """Per-boundary outgoing visual fade. Phase B→resolution uses 0 — no tail dimming."""
    return [
        0 if i == STITCH_PHASE_B_TO_RESOLUTION_PAIR_INDEX else int(default_out_ms)
        for i in range(max(0, pair_count))
    ]


def boundary_sfx_overlay_plan(
    clip_dur_ms: int,
    pair_ms: int,
    *,
    visual_out_ms: int = 600,
    visual_in_ms: int = 600,
    pre_ms: int = STITCH_TRANSITION_SFX_PRE_ROLL_MS,
    post_ms: int = STITCH_TRANSITION_SFX_POST_ROLL_MS,
) -> dict[str, int]:
    """Compute pipeline boundary SFX overlay windows (ms) for contract tests + UI markers."""
    from credentials_lib.ffmpeg_stitch import allocate_pair_fade_budget  # noqa: PLC0415

    out_ms, in_ms, black_ms = allocate_pair_fade_budget(
        pair_ms,
        visual_out_ms=visual_out_ms,
        visual_in_ms=visual_in_ms,
    )
    seg1_dur = pre_ms + out_ms
    seg1_offset = max(0, int(clip_dur_ms) - seg1_dur)
    total_span = pre_ms + out_ms + black_ms + in_ms + post_ms
    return {
        "pre_ms": pre_ms,
        "out_ms": out_ms,
        "black_ms": black_ms,
        "in_ms": in_ms,
        "post_ms": post_ms,
        "seg1_offset_ms": seg1_offset,
        "seg1_duration_ms": seg1_dur,
        "seg2_duration_ms": in_ms + post_ms,
        "total_span_ms": total_span,
    }

# STITCH_RESOLUTION_FINALE_V1 — tail fade-to-black + outtro3 on black; MP4 ends when outtro ends.
STITCH_RESOLUTION_FINALE_V1 = "STITCH_RESOLUTION_FINALE_V1"
STITCH_RESOLUTION_FINALE_OUTTRO_FILENAME = "outtro3.mp3"
STITCH_RESOLUTION_FINALE_FADE_OUT_MS = 500
STITCH_RESOLUTION_FINALE_OUTTRO_START_BEFORE_END_MS = 750
STITCH_RESOLUTION_FINALE_OUTTRO_PLAY_MS = 3250

# STITCH_MILESTONE_FINALE_V1 — standalone milestone bake uses outtro3 (same as resolution finale).
STITCH_MILESTONE_FINALE_V1 = "STITCH_MILESTONE_FINALE_V1"
STITCH_MILESTONE_FINALE_OUTTRO_FILENAME = STITCH_RESOLUTION_FINALE_OUTTRO_FILENAME
STITCH_MILESTONE_FINALE_FADE_OUT_MS = STITCH_RESOLUTION_FINALE_FADE_OUT_MS
STITCH_MILESTONE_FINALE_OUTTRO_START_BEFORE_END_MS = (
    STITCH_RESOLUTION_FINALE_OUTTRO_START_BEFORE_END_MS
)
STITCH_MILESTONE_FINALE_OUTTRO_PLAY_MS = STITCH_RESOLUTION_FINALE_OUTTRO_PLAY_MS


def resolution_finale_black_hold_ms() -> int:
    """Black tail after resolution content ends; outtro finishes when hold ends."""
    return max(
        0,
        STITCH_RESOLUTION_FINALE_OUTTRO_PLAY_MS
        - STITCH_RESOLUTION_FINALE_OUTTRO_START_BEFORE_END_MS,
    )


def milestone_finale_black_hold_ms() -> int:
    """Black tail after milestone content ends; outtro3 finishes when hold ends."""
    return max(
        0,
        STITCH_MILESTONE_FINALE_OUTTRO_PLAY_MS
        - STITCH_MILESTONE_FINALE_OUTTRO_START_BEFORE_END_MS,
    )


def resolve_canonical_finale_outtro_path(h, filename: str) -> str:
    """Resolve outtro SFX (transitions tier, then sfx, then project root)."""
    project_root = h._stitch_project_root()
    candidates = [
        project_root / "Production" / "assets" / "sound_library" / "transitions" / filename,
        project_root / "Production" / "assets" / "sound_library" / "sfx" / filename,
        project_root / filename,
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate.resolve())
    return ""


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


def canonical_stitch_transitions_for_pipeline(_existing=None) -> list[dict]:
    """Preview/bake always use dissolve / 2800ms / hard audio cut — ignore UI drift."""
    return default_stitch_transitions()


def resolve_canonical_boundary_sfx_path(h, filename: str) -> str:
    """Resolve library SFX under project root for pipeline boundary overlays."""
    project_root = h._stitch_project_root()
    candidates = [
        project_root / "Production" / "assets" / "sound_library" / "sfx" / filename,
        project_root / filename,
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate.resolve())
    return ""


def hydrate_stitch_pipeline_body(h, body: dict) -> dict:
    """Load ordered slots + transitions from stitch job when client sends {name} only."""
    _body = dict(body or {})
    job_name = _body.get("name") or ""
    job = None
    if job_name:
        try:
            _st = stitch_state_store_for_job(h, job_name).read_state()
            job = (_st.get("jobs") or {}).get(job_name)
        except Exception as exc:
            print(f"[stitch] WARN: job hydration read failed: {exc}")

    if job:
        _job_slots = job.get("slots")
        if isinstance(_job_slots, dict):
            strip_stale_pipeline_boundary_slot_cues(_job_slots)
            strip_stale_resolution_head_sfx_cues(_job_slots)

    slot_order = (
        STITCH_MILESTONE_SLOT_ORDER
        if is_milestone_stitch_job_name(job_name)
        else STITCH_SLOT_ORDER
    )

    if not _body.get("slots") and job:
        _slots_dict = job.get("slots") or {}
        if isinstance(_slots_dict, dict):
            _slots_list = [
                _slots_dict[k]
                for k in slot_order
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
            for slot in _body["slots"]:
                if isinstance(slot, dict):
                    normalize_slot_audio_mix_levels(slot)

    if _body.get("slots"):
        _hydrate_slot_ambient_paths(h, _body["slots"])
        strip_stale_pipeline_boundary_slot_cues(_body["slots"])
        strip_stale_resolution_head_sfx_cues(_body["slots"])
        for slot in _body["slots"]:
            if isinstance(slot, dict):
                normalize_slot_audio_mix_levels(slot)

    if "transitions" not in _body and job:
        _body["transitions"] = job.get("transitions") or []

    _body["transitions"] = canonical_stitch_transitions_for_pipeline(
        _body.get("transitions") or (job or {}).get("transitions"),
    )

    _coerce_stitch_pipeline_slots_to_list(_body)

    return _body


def _coerce_stitch_pipeline_slots_to_list(body: dict) -> None:
    """Preview/bake enumerate slots as a list; save-job merge payloads use dict keys."""
    slots = body.get("slots")
    if not isinstance(slots, dict):
        return
    job_name = (body.get("name") or "").strip()
    order = (
        STITCH_MILESTONE_SLOT_ORDER
        if job_name.startswith("milestone_")
        else STITCH_SLOT_ORDER
    )
    slot_key = (body.get("slot") or "").strip()
    if body.get("slot_preview") and slot_key and slot_key in slots:
        slot = slots[slot_key]
        body["slots"] = [slot] if isinstance(slot, dict) else []
        return
    body["slots"] = [
        slots[k] for k in order if isinstance(slots.get(k), dict)
    ]


def _hydrated_preview_slot_dict(hydrated: dict, slot_key: str) -> dict | None:
    """Slot dict used for preview ffmpeg mix (list or dict payload)."""
    slots = hydrated.get("slots")
    if isinstance(slots, list):
        for item in slots:
            if isinstance(item, dict):
                return item
        return None
    if isinstance(slots, dict):
        raw = slots.get(slot_key)
        return raw if isinstance(raw, dict) else None
    return None


def _persist_stitch_preview_slot_geometry(
    h,
    job_name: str,
    slot_key: str,
    hydrated_slot: dict,
) -> dict | None:
    """Write preview request geometry onto disk slot before mux artifact persist."""
    if not job_name or not slot_key or not isinstance(hydrated_slot, dict):
        return None
    stitch_store = stitch_state_store_for_job(h, job_name)
    merged: dict | None = None

    def update(state: dict) -> None:
        nonlocal merged
        job = (state.get("jobs") or {}).get(job_name)
        if not isinstance(job, dict):
            return
        slots = job.get("slots")
        if not isinstance(slots, dict):
            return
        prev = slots.get(slot_key)
        if not isinstance(prev, dict):
            prev = {}
        merged = {**prev}
        for field in (
            "sfx_cues",
            "ambient_bed",
            "ambient_volume",
            "ambient_bed_path",
            "trim_in_ms",
            "trim_out_ms",
            "video_path",
            "video_dur_ms",
        ):
            if field not in hydrated_slot:
                continue
            if field == "sfx_cues":
                prev_cues = prev.get("sfx_cues") if isinstance(prev.get("sfx_cues"), list) else []
                new_cues = hydrated_slot[field] if isinstance(hydrated_slot.get(field), list) else []
                if not new_cues and prev_cues:
                    continue
            merged[field] = hydrated_slot[field]
        slots[slot_key] = merged
        job["updated_at"] = datetime.now(timezone.utc).isoformat()

    stitch_store.mutate_state(update)
    return merged


def _preview_module_timing_from_hydrated(h, hydrated: dict) -> tuple[list[int], list[int]]:
    """Module seek timing for preview JSON (STITCH_MODULE_SEEK_V1) without full pipeline."""
    from credentials_lib.ffmpeg_stitch import (  # noqa: PLC0415
        DEFAULT_FADE_THROUGH_BLACK_VISUAL_IN_MS,
        DEFAULT_FADE_THROUGH_BLACK_VISUAL_OUT_MS,
        module_slot_start_offsets_ms,
    )

    slots = hydrated.get("slots") or []
    transitions = hydrated.get("transitions") or []
    slot_durations: list[int] = []
    for slot in slots:
        if not isinstance(slot, dict):
            continue
        dur = int(slot.get("mux_preview_duration_ms") or slot.get("video_dur_ms") or 0)
        video_path = (slot.get("video_path") or "").strip()
        if dur <= 0 and video_path:
            try:
                dur = int(h._ffprobe_duration_ms(h._stitch_resolve_path(video_path)))
            except (ValueError, TypeError, OSError):
                dur = 0
        slot_durations.append(max(0, dur))
    pair_fades_ms: list[int] = []
    for trans in transitions:
        if isinstance(trans, dict):
            pair_fades_ms.append(int(trans.get("fade_ms") or 0))
        else:
            pair_fades_ms.append(0)
    while len(pair_fades_ms) < max(0, len(slot_durations) - 1):
        pair_fades_ms.append(0)
    slot_start_offsets_ms = module_slot_start_offsets_ms(
        slot_durations,
        pair_fades_ms,
        visual_out_ms=DEFAULT_FADE_THROUGH_BLACK_VISUAL_OUT_MS,
        visual_in_ms=DEFAULT_FADE_THROUGH_BLACK_VISUAL_IN_MS,
    )
    return slot_durations, slot_start_offsets_ms


def handle_stitch_preview(h, body: dict)-> None:

    """POST /api/stitch_editor/preview — mux playback via artifact orchestrator (RC16).

    STITCH_ARTIFACT_ORCHESTRATOR_V1 — serialized ambient→mux; no parallel ffmpeg with
    save_job async tier. Explicit Review / warm paths block until build completes.
    """
    job_name = (body.get("name") or "").strip()
    from server_handlers.stitch_scope import assert_stitch_partition_scope  # noqa: PLC0415

    binding = assert_stitch_partition_scope(h, body, job_name=job_name)
    if binding is None:
        return
    job_name = binding.job_name
    stitch_store = binding.stitch_store
    orig_stitch_state = None
    if stitch_store is not h.app.stitch_state:
        orig_stitch_state = h.app.stitch_state
        h.app.stitch_state = stitch_store
    try:
        from server_handlers.stitch_artifact_build import (  # noqa: PLC0415
            STITCH_ARTIFACT_ORCHESTRATOR_V1,
            plan_playback_ladder_warm,
            submit_stitch_artifact_build_plan,
            wait_for_artifact_build,
        )

        hydrated = hydrate_stitch_pipeline_body(h, body)
        tag_stitch_pipeline_scope(hydrated)
        slot_durations, slot_start_offsets_ms = _preview_module_timing_from_hydrated(h, hydrated)
        slot_key = (body.get("slot") or "").strip()
        if not slot_key and isinstance(hydrated.get("slots"), list) and hydrated["slots"]:
            slot_key = (
                STITCH_MILESTONE_SLOT_ORDER[0]
                if is_milestone_stitch_job_name(job_name)
                else STITCH_SLOT_ORDER[0]
            )
        hydrated_slot = _hydrated_preview_slot_dict(hydrated, slot_key) if slot_key else None
        if hydrated_slot and slot_key:
            _persist_stitch_preview_slot_geometry(h, job_name, slot_key, hydrated_slot)

        state = stitch_store.read_state() or {}
        job = (state.get("jobs") or {}).get(job_name) or {}
        slots = job.get("slots") or {}
        slot = slots.get(slot_key) if slot_key else None
        if not isinstance(slot, dict):
            return h._send_error_v59(
                404,
                error_code="GENERIC_ERROR",
                error_message=f"Slot {slot_key!r} not found on job {job_name!r}",
                retry_safe=False,
            )

        hash_id = (slot.get("mux_preview_hash") or "").strip()
        preview_url = (slot.get("_mux_preview_url") or "").strip()
        if hash_id and preview_url:
            cache_path = h._stitch_cache_dir() / f"stitch_preview_{hash_id}.mp4"
            dur_ms = int(slot.get("mux_preview_duration_ms") or 0)
            if (
                cache_path.is_file()
                and stitch_cached_mp4_playable(
                    cache_path,
                    expected_s=dur_ms / 1000.0 if dur_ms > 0 else None,
                )
            ):
                from server_handlers.stitch_media_sig import compute_stitch_mix_sig_from_slot  # noqa: PLC0415
                from server_handlers.stitch_slot_edit_dispatch import slot_needs_ambient_rebuild  # noqa: PLC0415

                mux_cache_fresh = (slot.get("mix_sig") or "").strip() == compute_stitch_mix_sig_from_slot(h, slot)
                ambient_tier_ok = not slot_needs_ambient_rebuild(h, {}, slot)
                if mux_cache_fresh and ambient_tier_ok:
                    return h._send_json(200, {
                        "preview_url": _stitch_media_public_url(h, preview_url),
                        "mux_preview_hash": hash_id,
                        "duration_ms": dur_ms,
                        "slot_durations": slot_durations,
                        "slot_start_offsets_ms": slot_start_offsets_ms,
                        "video_playable": True,
                        "code": STITCH_SLOT_MEDIA_ARTIFACTS_V1,
                        "orchestrator_code": STITCH_ARTIFACT_ORCHESTRATOR_V1,
                        "cache_hit": True,
                    })

        ambient_keys, mux_keys = plan_playback_ladder_warm(h, job_name, slot_key)
        if not mux_keys:
            mux_keys = [slot_key]
        _pin = {
            "pinned_generation": getattr(h.app, "event_generation", None),
            "pinned_event_dir": h.app.event_dir,
            "pinned_video_role": (body or {}).get("scope_video_role", "intro"),
            "_handler": "handle_stitch_preview",
        }
        queued = submit_stitch_artifact_build_plan(
            h,
            stitch_job_name=job_name,
            ambient_keys=ambient_keys,
            mux_keys=mux_keys,
            pin=_pin,
            trigger="preview",
        )
        if queued:
            try:
                wait_for_artifact_build(h.app.event_dir, queued["build_id"], timeout_s=900.0)
            except RuntimeError as exc:
                return h._send_error_v59(
                    500,
                    error_code="GENERIC_ERROR",
                    error_message=str(exc),
                    retry_safe=True,
                    extra={"code": STITCH_ARTIFACT_ORCHESTRATOR_V1},
                )

        state = stitch_store.read_state() or {}
        slot = ((state.get("jobs") or {}).get(job_name) or {}).get("slots", {}).get(slot_key)
        if not isinstance(slot, dict):
            return h._send_error_v59(
                500,
                error_code="GENERIC_ERROR",
                error_message="preview orchestrator finished without slot state",
                retry_safe=True,
            )
        hash_id = (slot.get("mux_preview_hash") or "").strip()
        if not hash_id:
            return h._send_error_v59(
                500,
                error_code="GENERIC_ERROR",
                error_message="mux preview hash missing after orchestrator build",
                retry_safe=True,
                extra={"code": STITCH_ARTIFACT_ORCHESTRATOR_V1},
            )
        dur_ms = int(slot.get("mux_preview_duration_ms") or 0)
        out_path = h._stitch_cache_dir() / f"stitch_preview_{hash_id}.mp4"
        if not stitch_cached_mp4_playable(out_path, expected_s=dur_ms / 1000.0 if dur_ms > 0 else None):
            purge_stitch_cache_mp4(out_path)
            return h._send_error_v59(
                500,
                error_code="STITCH_PREVIEW_NOT_PLAYABLE",
                error_message=(
                    "stitch preview failed decode smoke test — "
                    f"rebuild slot or retry ({STITCH_SLOT_PREVIEW_V1})"
                ),
                retry_safe=True,
                extra={"code": STITCH_SLOT_PREVIEW_VIDEO_PLAYABLE_V1},
            )
        from server_handlers.stitch_media_sig import compute_stitch_mix_sig_from_slot  # noqa: PLC0415

        mix_sig = compute_stitch_mix_sig_from_slot(h, slot)
        return h._send_json(200, {
            "preview_url": _stitch_media_public_url(h, f"/api/stitch_editor/preview_file/{hash_id}"),
            "mux_preview_hash": hash_id,
            "mix_sig": mix_sig,
            "duration_ms": dur_ms,
            "slot_durations": slot_durations,
            "slot_start_offsets_ms": slot_start_offsets_ms,
            "video_playable": True,
            "code": STITCH_SLOT_MEDIA_ARTIFACTS_V1,
            "orchestrator_code": STITCH_ARTIFACT_ORCHESTRATOR_V1,
        })
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
    finally:
        if orig_stitch_state is not None:
            h.app.stitch_state = orig_stitch_state


def _persist_stitch_bake_job_pointer(h, stitch_job_name: str, job_id: str | None) -> None:
    """Persist active bake job id on stitch state for reload reattach."""
    store = stitch_state_store_for_job(h, stitch_job_name)

    def mutate(state: dict) -> None:
        job = state.setdefault("jobs", {}).setdefault(stitch_job_name, {})
        if job_id:
            job["active_bake_job_id"] = job_id
        else:
            job.pop("active_bake_job_id", None)

    store.mutate_state(mutate)


def _milestone_dir_for_stitch_job(h, job_name: str) -> Path | None:
    mid = milestone_id_from_stitch_job_name(job_name)
    if not mid:
        return None
    from lib.paths import runtime_production_root  # noqa: PLC0415

    return (runtime_production_root(h.app.event_dir) / "Milestones" / mid).resolve()


def _canonical_milestone_standalone_final_path(h, milestone_id: str) -> str | None:
    """Kid-facing milestone final on disk for footer preview."""
    from lib.milestone_store import load_milestone_state  # noqa: PLC0415

    milestone_dir = _milestone_dir_for_stitch_job(
        h, stitch_milestone_job_name(milestone_id),
    )
    if milestone_dir is None or not milestone_dir.is_dir():
        return None
    state = load_milestone_state(milestone_dir)
    canonical_name = (state.get("canonical_standalone_final_file") or "").strip()
    if not canonical_name:
        rel = ((state.get("videos") or {}).get("standalone") or {}).get("completed_mp4_path")
        if rel:
            target = (milestone_dir / str(rel)).resolve()
            if target.is_file() and str(target).startswith(str(milestone_dir.resolve())):
                return str(target)
        return None
    target = (milestone_dir / "assembled" / canonical_name).resolve()
    if not target.is_file():
        target = (milestone_dir / canonical_name).resolve()
    if target.is_file() and str(target).startswith(str(milestone_dir.resolve())):
        return str(target)
    return None


def _run_stitch_bake_core(
    h,
    body: dict,
    pin: dict,
    *,
    progress_cb=None,
) -> dict:
    """Execute stitch bake pipeline; returns ok payload or error dict (no HTTP)."""

    def _progress(message: str, *, phase: str | None = None) -> None:
        if progress_cb:
            progress_cb(message, phase=phase)

    from server_handlers.phases import ensure_phase_b_stitch_slot_for_bake  # noqa: PLC0415

    job_name = (body.get("name") or "untitled").strip()
    milestone_bake = is_milestone_stitch_job_name(job_name)
    if not milestone_bake:
        _progress("Refreshing Phase B delivery slot…", phase="encode")
        preflight = ensure_phase_b_stitch_slot_for_bake(h)
        if not preflight.get("ok", True):
            return {
                "ok": False,
                "error_code": "PHASE_B_BAKE_PREFLIGHT_FAILED",
                "error_message": preflight.get("error") or "Phase B bake preflight failed",
                "retry_safe": True,
            }

    stitch_store = stitch_state_store_for_job(h, job_name) if job_name else h.app.stitch_state
    orig_stitch_state = None
    if stitch_store is not h.app.stitch_state:
        orig_stitch_state = h.app.stitch_state
        h.app.stitch_state = stitch_store
    try:
        _body = hydrate_stitch_pipeline_body(h, body)
        _body["module_pipeline"] = True
        tag_stitch_pipeline_scope(_body)
        if not _body.get("slots"):
            return {
                "ok": False,
                "error_code": "STITCH_NO_SLOTS",
                "error_message": "No slots provided — assign videos to all stitch slots first",
                "retry_safe": False,
            }

        try:
            out_path, _durations, _slot_starts = h._stitch_build_pipeline(_body)
        except (ValueError, PermissionError) as exc:
            return {
                "ok": False,
                "error_code": "GENERIC_ERROR",
                "error_message": str(exc),
                "retry_safe": False,
            }
        except FileNotFoundError as exc:
            return {
                "ok": False,
                "error_code": "GENERIC_ERROR",
                "error_message": str(exc),
                "retry_safe": False,
            }
        except RuntimeError as exc:
            return {
                "ok": False,
                "error_code": "GENERIC_ERROR",
                "error_message": str(exc),
                "retry_safe": True,
            }

        from credentials_lib.ffmpeg_stitch import (  # noqa: PLC0415
            STITCH_EXPORT_AV_MAX_DRIFT_S,
            assert_stitch_export_clips_av_aligned,
            av_duration_drift_s,
        )

        # STITCH_MODULE_BAKE_AV_PARITY_V1 — block lean encode when pipeline master drifts.
        try:
            assert_stitch_export_clips_av_aligned([out_path])
        except ValueError as exc:
            return {
                "ok": False,
                "error_code": "STITCH_BAKE_AV_MISALIGNED",
                "error_message": str(exc),
                "retry_safe": True,
            }

        now_ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        exports_dir = h._stitch_exports_dir()
        bake_name = f"stitch_{job_name}_{now_ts}_final.mp4"
        bake_path = exports_dir / bake_name

        from video_delivery import (  # noqa: PLC0415
            MODULE_FINAL_LEAN_DELIVERY_CURRENT,
            MODULE_FINAL_LEAN_MAX_BITRATE_BPS,
            encode_module_final_lean,
        )

        _progress("Final delivery encode (VIDEO_QUALITY_V1)…", phase="encode")
        try:
            encode_module_final_lean(out_path, bake_path)
        except Exception as exc:
            bake_path.unlink(missing_ok=True)
            return {
                "ok": False,
                "error_code": "MODULE_FINAL_LEAN_DELIVERY_FAILED",
                "error_message": str(exc),
                "retry_safe": True,
            }

        try:
            vp = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=bit_rate",
                 "-of", "json", str(bake_path.resolve())],
                capture_output=True, timeout=10, check=True,
            )
            bitrate = int(json.loads(vp.stdout).get("format", {}).get("bit_rate", 0))
        except Exception:
            bitrate = 0

        if bitrate <= 0 or bitrate > MODULE_FINAL_LEAN_MAX_BITRATE_BPS:
            bake_path.unlink(missing_ok=True)
            return {
                "ok": False,
                "error_code": "MODULE_FINAL_LEAN_BITRATE_V1",
                "error_message": (
                    f"Final delivery bitrate {bitrate:,} bps exceeds "
                    f"{MODULE_FINAL_LEAN_MAX_BITRATE_BPS:,} bps cap"
                ),
                "retry_safe": False,
                "actual_bps": bitrate,
            }

        file_size = bake_path.stat().st_size
        size_mb = file_size / (1024 * 1024)
        if size_mb > 80.0:
            bake_path.unlink(missing_ok=True)
            return {
                "ok": False,
                "error_code": "SIZE_BUDGET_PER_MODULE_V1",
                "error_message": (
                    f"Final delivery {size_mb:.1f} MB exceeds 80 MB ceiling"
                ),
                "retry_safe": False,
                "actual_bytes": file_size,
            }

        bake_av_drift_s = av_duration_drift_s(bake_path)
        if bake_av_drift_s > STITCH_EXPORT_AV_MAX_DRIFT_S:
            bake_path.unlink(missing_ok=True)
            return {
                "ok": False,
                "error_code": "STITCH_BAKE_AV_MISALIGNED",
                "error_message": (
                    f"Final delivery A/V misaligned: drift {bake_av_drift_s:.3f}s "
                    f"(max {STITCH_EXPORT_AV_MAX_DRIFT_S}s) "
                    "(STITCH_MODULE_BAKE_AV_PARITY_V1)"
                ),
                "retry_safe": True,
            }

        from stitch_bake_finalize import (  # noqa: PLC0415
            default_stitch_state_path,
            finalize_milestone_stitch_bake,
            finalize_stitch_bake,
            resolve_m_and_event_numbers,
        )

        _progress("Pinning canonical + Directus…", phase="finalize")

        if not h._check_event_pin(pin, "stitch_bake_finalize"):
            return {
                "ok": False,
                "error_code": "EVENT_CHANGED_MID_JOB",
                "error_message": "event_changed_mid_job",
                "retry_safe": False,
                "orphaned_bake_path": str(bake_path),
            }

        slots = _body.get("slots") or []
        iter_notes = (
            f"Stitch editor bake ({MODULE_FINAL_LEAN_DELIVERY_CURRENT} VIDEO_QUALITY_V1). "
            f"Job: {job_name}. {len(slots)} slot(s), "
            f"{sum(len(s.get('sfx_cues') or []) for s in slots)} SFX cues."
        )
        try:
            if milestone_bake:
                milestone_dir = _milestone_dir_for_stitch_job(h, job_name)
                if milestone_dir is None or not milestone_dir.is_dir():
                    raise FileNotFoundError(f"milestone dir not found for job {job_name!r}")
                finalize_result = finalize_milestone_stitch_bake(
                    milestone_dir,
                    bake_path,
                    job_name=job_name,
                    iteration_notes=iter_notes,
                    notes=(
                        f"Stitch editor milestone bake {now_ts} "
                        f"({MODULE_FINAL_LEAN_DELIVERY_CURRENT}). Job: {job_name}."
                    ),
                    delivery_profile="module_final_lean",
                )
            else:
                m_number, event_num = resolve_m_and_event_numbers(Path(h.app.event_dir))
                finalize_result = finalize_stitch_bake(
                    Path(h.app.event_dir),
                    bake_path,
                    module_id=_resolve_module_id_for_state(h.app.state),
                    m_number=m_number,
                    event_num=event_num,
                    stitch_state_path=default_stitch_state_path(Path(h.app.event_dir)),
                    job_name=job_name,
                    iteration_notes=iter_notes,
                    notes=(
                        f"Stitch editor bake {now_ts} ({MODULE_FINAL_LEAN_DELIVERY_CURRENT}). "
                        f"Job: {job_name}. "
                        f"Slots: {[s.get('video_path', '?') for s in slots]}"
                    ),
                    delivery_profile="module_final_lean",
                )
        except Exception as reg_exc:
            print(f"[stitch-bake] canonical finalize failed: {reg_exc}", flush=True)
            return {
                "ok": False,
                "error_code": "STITCH_BAKE_CANONICAL_FAILED",
                "error_message": str(reg_exc),
                "retry_safe": True,
                "export_bake_path": str(bake_path),
            }

        asset_id = int(finalize_result.get("asset_id") or -1)
        canonical_path = finalize_result.get("canonical_path") or str(bake_path)

        def mutate(state: dict) -> None:
            j = state.setdefault("jobs", {}).setdefault(job_name, {})
            j["bake_path"] = canonical_path
            j["last_bake_job_id"] = pin.get("_bake_job_id")
            j.pop("active_bake_job_id", None)

        stitch_store.mutate_state(mutate)

        return {
            "ok": True,
            "asset_id": asset_id,
            "bake_name": bake_name,
            "bake_path": str(bake_path),
            "export_bake_path": str(bake_path),
            "canonical_path": canonical_path,
            "canonical_name": finalize_result.get("canonical_name"),
            "canonical_module_final_sha256": finalize_result.get("sha256"),
            "directus_approved": finalize_result.get("directus_approved"),
            "file_size_bytes": file_size,
            "bitrate_bps": bitrate,
            "delivery_profile": MODULE_FINAL_LEAN_DELIVERY_CURRENT,
            "code": (
                "STITCH_MILESTONE_BAKE_CANONICAL_V1"
                if milestone_bake
                else "STITCH_BAKE_CANONICAL_DIRECTUS_V1"
            ),
        }
    finally:
        if orig_stitch_state is not None:
            h.app.stitch_state = orig_stitch_state


def _execute_stitch_bake_job(
    h,
    *,
    job_id: str,
    stitch_job_name: str,
    body: dict,
    pin: dict,
    lock_path: Path,
) -> None:
    """Background worker: full bake pipeline with durable job-truth updates."""
    from stitch_bake_job_store import (  # noqa: PLC0415
        finalize_job,
        update_job_progress,
    )

    pin = dict(pin)
    pin["_bake_job_id"] = job_id
    fd = None
    try:
        import fcntl  # noqa: PLC0415

        fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR)
        fcntl.flock(fd, fcntl.LOCK_EX)

        update_job_progress(
            h.app.event_dir,
            job_id,
            status="running",
            phase="encode",
            message="Encoding final module MP4…",
        )

        def _job_progress(message: str, *, phase: str | None = None) -> None:
            update_job_progress(
                h.app.event_dir,
                job_id,
                status="running",
                phase=phase or "encode",
                message=message,
            )

        result = _run_stitch_bake_core(h, body, pin, progress_cb=_job_progress)
        if result.get("ok"):
            finalize_job(
                h.app.event_dir,
                job_id,
                "done",
                result=result,
            )
            _persist_stitch_bake_job_pointer(h, stitch_job_name, None)
            return

        finalize_job(
            h.app.event_dir,
            job_id,
            "failed",
            error=result.get("error_message") or "Bake failed",
            result={"error_code": result.get("error_code"), **result},
        )
        _persist_stitch_bake_job_pointer(h, stitch_job_name, None)
    except Exception as exc:
        traceback.print_exc()
        finalize_job(
            h.app.event_dir,
            job_id,
            "failed",
            error=str(exc),
            result={"error_code": "STITCH_BAKE_EXCEPTION"},
        )
        _persist_stitch_bake_job_pointer(h, stitch_job_name, None)
    finally:
        if fd is not None:
            try:
                import fcntl  # noqa: PLC0415

                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)
            except Exception:
                pass


def handle_stitch_bake(h, body: dict)-> None:

    """POST /api/stitch_editor/bake — submit async final MP4 bake (STITCH_BAKE_JOB_TRUTH_V1).

    LD-140: bake IS registered (unlike preview). LD-280: single atomic MP4.
    MODULE_FINAL_LEAN two-pass: master archive ungated; lean delivery ≤960k bps + ≤80MB.
    """
    from stitch_bake_job_store import (  # noqa: PLC0415
        STITCH_BAKE_JOB_TRUTH_V1,
        bake_lock_is_free,
        create_job,
        find_active_job_for_stitch_job,
        job_poll_payload,
        new_job_id,
        reconcile_stale_running_jobs,
    )

    # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return

    stitch_job_name = (body.get("name") or "untitled").strip()
    if not stitch_job_name:
        return h._send_error_v59(
            400,
            error_code="STITCH_JOB_NAME_REQUIRED",
            error_message="name required",
            retry_safe=False,
            extra={"code": STITCH_BAKE_JOB_TRUTH_V1},
        )

    # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — capture pin at entry; worker asserts at finalize.
    _pin = {
        "pinned_generation": h.app.event_generation,
        "pinned_event_dir": h.app.event_dir,
        "pinned_video_role": (body or {}).get("scope_video_role", "intro"),
        "_handler": '_handle_stitch_bake',
    }
    if not h._check_event_pin(_pin, '_handle_stitch_bake_pre_work'):
        return h._send_error_v59(
            423,
            error_code="EVENT_CHANGED_PRE_WORK",
            error_message="event_changed_pre_work",
            retry_safe=False,
            extra={
                "code": "ASYNC_JOB_GENERATION_PIN_V1",
                "handler": '_handle_stitch_bake',
                "hint": (
                    "Event changed between scope-guard and work start. "
                    "No work was done; client should re-hydrate scope and retry."
                ),
            },
        )

    bake_lock_path = h._stitch_cache_dir() / "stitch_bake.lock"
    bake_lock_path.touch(exist_ok=True)
    reconcile_stale_running_jobs(h.app.event_dir, bake_lock_path)

    existing = find_active_job_for_stitch_job(h.app.event_dir, stitch_job_name)
    if existing:
        payload = job_poll_payload(existing)
        payload.update({"ok": True, "reattach": True})
        return h._send_json(200, payload)

    if not bake_lock_is_free(bake_lock_path):
        return h._send_error_v59(
            409,
            error_code="BAKE_ALREADY_IN_PROGRESS",
            error_message="Bake already in progress",
            retry_safe=False,
            extra={"code": STITCH_BAKE_JOB_TRUTH_V1},
        )

    scope_body = h._scope_body(body)
    scope_event_id = (
        scope_body.get("scope_event_id")
        or scope_body.get("event_id")
        or h.app.event_dir.name
    )
    job_id = new_job_id()
    create_job(
        h.app.event_dir,
        job_id=job_id,
        stitch_job_name=stitch_job_name,
        scope_event_id=str(scope_event_id),
    )
    _persist_stitch_bake_job_pointer(h, stitch_job_name, job_id)

    worker = threading.Thread(
        target=_execute_stitch_bake_job,
        args=(h,),
        kwargs={
            "job_id": job_id,
            "stitch_job_name": stitch_job_name,
            "body": dict(body),
            "pin": _pin,
            "lock_path": bake_lock_path,
        },
        daemon=True,
        name=f"stitch-bake-{job_id}",
    )
    worker.start()

    job_record = find_active_job_for_stitch_job(h.app.event_dir, stitch_job_name) or {"job_id": job_id}
    payload = job_poll_payload(job_record)
    payload.update({"ok": True, "submitted": True})
    return h._send_json(202, payload)


def handle_stitch_bake_status(h)-> None:
    """GET /api/stitch_editor/bake/status?job_id=xxx — poll bake job truth."""
    from stitch_bake_job_store import (  # noqa: PLC0415
        STITCH_BAKE_JOB_TRUTH_V1,
        job_poll_payload,
        load_job,
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
            extra={"code": STITCH_BAKE_JOB_TRUTH_V1},
        )

    lock_path = h._stitch_cache_dir() / "stitch_bake.lock"
    reconcile_stale_running_jobs(h.app.event_dir, lock_path)

    job = load_job(h.app.event_dir, job_id)
    if not job:
        return h._send_error_v59(
            404,
            error_code="BAKE_JOB_NOT_FOUND",
            error_message=f"Bake job {job_id!r} not found",
            retry_safe=False,
            extra={"code": STITCH_BAKE_JOB_TRUTH_V1},
        )

    payload = job_poll_payload(job)
    payload["ok"] = True
    return h._send_json(200, payload)


