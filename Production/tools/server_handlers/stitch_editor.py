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
# Canonical under-speech ambient level (all stitch slots — waveform, preview, bake).
STITCH_AMBIENT_BED_VOLUME = 0.15
STITCH_SFX_CUE_DEFAULT_VOLUME = 0.45
STITCH_SFX_CUE_DEFAULT_FADEIN_MS = 300
STITCH_SFX_CUE_DEFAULT_FADEOUT_MS = 1200
# Bust pre-2026-06-13 mix cache: stereo ambient bed + mono speech made amix drop SFX lanes;
# afade after adelay also silenced cues in the 3-way mix — fade must run before delay.
STITCH_WAVEFORM_MIX_MONO_V1 = "mono_v2"
# Canonical ambient bed preset_id per stitch slot (filename stem under sound_library/ambient/).
STITCH_DEFAULT_AMBIENT_BEDS: dict[str, str] = {
    "intro": "Intro video ambient bed",
    "phase_a": "ambient bed pretty option2",
    "phase_b": "ambient bed pretty option",
    "resolution": "ambien bed pretty option4",
}
# Canonical teleport whoosh — auto-placed on intro Send-to-Stitcher (removable in UI).
STITCH_INTRO_DEFAULT_WHOOSH_FILENAME = "whoosh sound.mp3"
STITCH_INTRO_DEFAULT_WHOOSH_PLAY_MS = 3104
# Re-probe when stored duration differs from on-disk file by more than this (ms).
STITCH_VIDEO_DUR_DRIFT_TOLERANCE_MS = 500
# STITCH_SLOT_MEDIA_LINEAGE_DURABILITY_V1 — export/sync must not serve truncated audio extracts.
STITCH_SLOT_MEDIA_LINEAGE_DURABILITY_V1 = "STITCH_SLOT_MEDIA_LINEAGE_DURABILITY_V1"
# STITCH_SLOT_EXPORT_FULL_MEDIA_V1 — all four tab exports must upsert full playable slot video.
STITCH_SLOT_EXPORT_FULL_MEDIA_V1 = "STITCH_SLOT_EXPORT_FULL_MEDIA_V1"
STITCH_AUDIO_DUR_MIN_RATIO = 0.85


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
        normalize_slot_audio_mix_levels(dst)
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


def _slot_has_whoosh_cue(slot: dict) -> bool:
    for cue in slot.get("sfx_cues") or []:
        if not isinstance(cue, dict):
            continue
        label = f"{cue.get('name', '')} {cue.get('source_path', '')}".lower()
        if "whoosh" in label:
            return True
    return False


def ensure_stitch_intro_default_whoosh_cue(h, slot: dict) -> bool:
    """Ensure intro tail whoosh exists until the operator explicitly deletes it."""
    if not isinstance(slot, dict) or not (slot.get("video_path") or "").strip():
        return False
    if slot.get("intro_whoosh_default_dismissed"):
        return False
    if _slot_has_whoosh_cue(slot):
        return False
    whoosh_path = _resolve_stitch_intro_whoosh_path(h)
    if not whoosh_path:
        return False
    sync_stitch_slot_video_dur_ms(h, slot, force=True)
    video_dur_ms = int(slot.get("video_dur_ms") or 0)
    if video_dur_ms <= 0:
        return False
    file_dur_ms = h._ffprobe_duration_ms(Path(whoosh_path))
    play_ms = STITCH_INTRO_DEFAULT_WHOOSH_PLAY_MS
    if file_dur_ms and file_dur_ms < play_ms:
        play_ms = int(file_dur_ms)
    play_ms = max(500, min(play_ms, video_dur_ms))
    offset_ms = max(0, video_dur_ms - play_ms)
    import secrets as _secrets  # noqa: PLC0415

    cue = {
        "id": f"cue_{_secrets.token_hex(4)}",
        "source_path": whoosh_path,
        "name": STITCH_INTRO_DEFAULT_WHOOSH_FILENAME,
        "offset_ms": offset_ms,
        "duration_ms": play_ms,
        "volume": STITCH_SFX_CUE_DEFAULT_VOLUME,
        "fadein_ms": STITCH_SFX_CUE_DEFAULT_FADEIN_MS,
        "fadeout_ms": STITCH_SFX_CUE_DEFAULT_FADEOUT_MS,
        "auto_default": True,
    }
    slot["sfx_cues"] = list(slot.get("sfx_cues") or []) + [cue]
    return True


# Back-compat alias (tests + external imports).
apply_stitch_intro_default_whoosh_cue = ensure_stitch_intro_default_whoosh_cue


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


def ensure_job_slot_defaults(h, slots) -> bool:
    """Sync durations, ambient presets, intro whoosh, and phase_a canonical path."""
    if not isinstance(slots, dict):
        return False
    changed = False
    for slot_key in STITCH_SLOT_ORDER:
        slot = slots.get(slot_key)
        if not isinstance(slot, dict):
            continue
        if slot_key == "phase_a" and sync_stitch_phase_a_from_phase_tab(h, slot):
            changed = True
        if sync_stitch_slot_video_dur_ms(h, slot):
            changed = True
        if apply_stitch_slot_default_ambient_preset(slot_key, slot):
            changed = True
        if slot_key == "intro" and ensure_stitch_intro_default_whoosh_cue(h, slot):
            changed = True
        normalize_slot_audio_mix_levels(slot)
    return changed


def collect_stitch_job_slot_warnings(h, slots) -> dict[str, list[str]]:
    if not isinstance(slots, dict):
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

    normalize_slot_audio_mix_levels(slot)
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
    sig_parts += [
        f"{c.get('id', i)}:{c.get('offset_ms', 0)}:{c.get('duration_ms', '')}:"
        f"{c.get('volume', STITCH_SFX_CUE_DEFAULT_VOLUME)}:"
        f"{c.get('source_path', '')}"
        for i, c in enumerate(sfx_cues)
    ]
    mix_hash = _hl.md5("|".join(sig_parts).encode(), usedforsecurity=False).hexdigest()[:12]
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
        filter_lanes.append(
            f"[{aidx}:a]aloop=-1:size=2147483647,"
            f"atrim=duration={slot_dur_s:.3f},"
            f"aformat=channel_layouts=mono,"
            f"volume={ambient_volume:.3f}[bed]"
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
        f"{''.join(mix_inputs)}amix=inputs={n_mix}:duration=first:normalize=0[aout]"
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
    try:
        subprocess.run(mix_cmd, check=True, capture_output=True, timeout=180)
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
) -> tuple[str, int, list[str]]:
    """Upsert one slot into the canonical per-event stitch job.

    STITCH_SLOT_EXPORT_FULL_MEDIA_V1: every caller (Beat Gen intro/resolution,
    Phase A/B export, scene assemble) must pass video_path; full file is probed,
    playability-checked, and video_dur_ms is written before persist.
    """
    if slot_key not in STITCH_SLOT_ORDER:
        raise ValueError(f"invalid stitch slot key: {slot_key!r}")

    new_video_path = (slot_patch.get("video_path") or "").strip()
    if not new_video_path:
        raise ValueError(
            f"{slot_key}: video_path required for stitch export "
            f"({STITCH_SLOT_EXPORT_FULL_MEDIA_V1})",
        )

    probed_ms, export_warnings = stitch_slot_export_media_preflight(
        h,
        new_video_path,
        slot_key,
        beat_boundaries=beat_boundaries,
    )
    patched = dict(slot_patch)
    patched["video_dur_ms"] = probed_ms

    now_iso = datetime.now(timezone.utc).isoformat()
    job_name = stitch_event_job_name(event_id)

    def upsert(state: dict) -> None:
        stitch_migrate_legacy_to_canonical(state, event_id)
        jobs = state.setdefault("jobs", {})
        job = jobs[job_name]
        if not isinstance(job.get("slots"), dict):
            job["slots"] = {}
        slot = job["slots"].setdefault(slot_key, {})
        old_video_path = (slot.get("video_path") or "").strip()
        slot.update(patched)
        new_path = (slot.get("video_path") or "").strip()
        video_path_changed = bool(new_path and new_path != old_video_path)
        sync_stitch_slot_video_dur_ms(h, slot, force=True)
        stored_ms = int(slot.get("video_dur_ms") or 0)
        if abs(stored_ms - probed_ms) > STITCH_VIDEO_DUR_DRIFT_TOLERANCE_MS:
            slot["video_dur_ms"] = probed_ms
        apply_stitch_slot_default_ambient_preset(slot_key, slot)
        if video_path_changed and slot_key == "intro":
            slot.pop("intro_whoosh_default_dismissed", None)
        if slot_key == "intro":
            ensure_stitch_intro_default_whoosh_cue(h, slot)
        normalize_slot_audio_mix_levels(slot)
        if beat_boundaries is not None:
            slot["beat_boundaries"] = enrich_beat_boundaries(beat_boundaries)
        job["updated_at"] = now_iso

    h.app.stitch_state.mutate_state(upsert)
    return job_name, probed_ms, export_warnings


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
            normalize_job_slots_audio(slots)
            defaults_changed = ensure_job_slot_defaults(h, slots)
            for slot in slots.values():
                if isinstance(slot, dict) and slot.get("beat_boundaries"):
                    slot["beat_boundaries"] = enrich_beat_boundaries(
                        slot["beat_boundaries"],
                    )
            live_slots = (job.get("slots") if isinstance(job, dict) else None)
            if defaults_changed or _job_canonical_audio_needs_persist(live_slots, slots):

                def persist_defaults(state: dict) -> None:
                    _persist_stitch_job_canonical_audio(state, name, slots)

                h.app.stitch_state.mutate_state(persist_defaults)
    payload = {"job": response_job, "name": name}
    if isinstance(response_job, dict):
        slots = response_job.get("slots")
        if isinstance(slots, dict):
            warnings = collect_stitch_job_slot_warnings(h, slots)
            if warnings:
                payload["slot_warnings"] = warnings
    return h._send_json(200, payload)


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
                    normalize_slot_audio_mix_levels(merged)
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
                    base_slots[slot_key] = merged
            slots_out = base_slots
        elif not slot_items and existing.get("slots"):
            # Malformed save without merge_slots — preserve existing slots.
            slots_out = _normalize_job_slots(existing.get("slots"))
        else:
            slots_out = slots
        if isinstance(slots_out, dict):
            ensure_job_slot_defaults(h, slots_out)
        normalize_job_slots_audio(slots_out if isinstance(slots_out, dict) else {})
        jobs[name] = {
            "created_at": existing.get("created_at", now_iso),
            "updated_at": now_iso,
            "slots": slots_out,
            "transitions": canonical_stitch_transitions_for_pipeline(
                transitions or existing.get("transitions"),
            ),
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

    video_dur_ms = h._ffprobe_duration_ms(Path(abs_path))
    if video_dur_ms <= 0:
        return h._send_error_v59(
            400,
            error_code="STITCH_SLOT_VIDEO_UNREADABLE",
            error_message=f"cannot probe video duration: {video_path_str}",
            retry_safe=False,
            extra={"code": STITCH_SLOT_MEDIA_LINEAGE_DURABILITY_V1},
        )
    expected_s = video_dur_ms / 1000.0

    from credentials_lib.ffmpeg_stitch import stitch_audio_cache_is_valid  # noqa: PLC0415

    if audio_path.is_file() and not stitch_audio_cache_is_valid(
        audio_path, expected_s, min_ratio=STITCH_AUDIO_DUR_MIN_RATIO,
    ):
        try:
            audio_path.unlink()
        except OSError:
            pass

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
    mix_slot: dict = {}
    ambient_bed = (body.get("ambient_bed") or "").strip()
    if ambient_bed:
        mix_slot["ambient_bed"] = ambient_bed
    sfx_raw = body.get("sfx_cues")
    sfx_mixed = False
    if isinstance(sfx_raw, list):
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

    return h._send_json(200, {
        "audio_url": f"http://localhost:5111/api/stitch_editor/audio_file/{serve_fname}",
        "duration_ms": duration_ms,
        "video_dur_ms": video_dur_ms,
        "ambient_mixed": bool(mix_slot.get("ambient_bed_path")),
        "sfx_mixed": sfx_mixed,
        "code": STITCH_SLOT_MEDIA_LINEAGE_DURABILITY_V1,
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

# STITCH_RESOLUTION_FINALE_V1 — tail fade-to-black + outtro3 on black; MP4 ends when outtro ends.
STITCH_RESOLUTION_FINALE_V1 = "STITCH_RESOLUTION_FINALE_V1"
STITCH_RESOLUTION_FINALE_OUTTRO_FILENAME = "outtro3.mp3"
STITCH_RESOLUTION_FINALE_FADE_OUT_MS = 500
STITCH_RESOLUTION_FINALE_OUTTRO_START_BEFORE_END_MS = 750
STITCH_RESOLUTION_FINALE_OUTTRO_PLAY_MS = 3250


def resolution_finale_black_hold_ms() -> int:
    """Black tail after resolution content ends; outtro finishes when hold ends."""
    return max(
        0,
        STITCH_RESOLUTION_FINALE_OUTTRO_PLAY_MS
        - STITCH_RESOLUTION_FINALE_OUTTRO_START_BEFORE_END_MS,
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
            for slot in _body["slots"]:
                if isinstance(slot, dict):
                    normalize_slot_audio_mix_levels(slot)

    if _body.get("slots"):
        _hydrate_slot_ambient_paths(h, _body["slots"])
        for slot in _body["slots"]:
            if isinstance(slot, dict):
                normalize_slot_audio_mix_levels(slot)

    if "transitions" not in _body and job:
        _body["transitions"] = job.get("transitions") or []

    _body["transitions"] = canonical_stitch_transitions_for_pipeline(
        _body.get("transitions") or (job or {}).get("transitions"),
    )

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


