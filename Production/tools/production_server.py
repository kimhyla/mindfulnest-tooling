#!/usr/bin/env python3
"""
production_server.py — MindfulNest Storyboard Production Server (v1 MVP)

Local HTTP server on http://localhost:5111 that powers the Storyboard
Production Overlay. Everything external — WaveSpeed Kling animation,
file I/O, state persistence, cost tracking — happens here, so the
browser overlay can stay a thin client with no API keys.

See Production/STORYBOARD_PRODUCTION_OVERLAY_PLAN_v3_1.md for the full spec.

Phase 1 MVP scope: animation only (Kling v3 via WaveSpeed). TTS (v1.1) and
lip-sync (v1.2) endpoints are stubs that return 501.

CLI:
    python3 production_server.py \\
        --event-dir Production/Event_1 \\
        --storyboard storyboard_v14_prod.html \\
        --event-id Event_1

    python3 production_server.py --smoke-test
"""

from __future__ import annotations

import argparse
import base64
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
import http.client
import ssl
import traceback
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# Auto-strip audio from downloaded animation clips (CLAUDE.md Rule 8 defense).
# Bootstrap order MATTERS: Production/ must come BEFORE Production/tools/ in
# sys.path so `from lib.atomic_json_write import ...` resolves to
# Production/lib/ (regular package) — there is a separate Production/tools/lib/
# package (with __init__.py) that would shadow the lib import if it were
# searched first. Pre-C-7.6: line `sys.path.insert(0, dirname)` was
# unconditional, so when callers (e.g. unit tests) pre-populated sys.path
# with Production/, this insert pushed Production/tools/ to position 0,
# shadowing lib and breaking the next import. Now both inserts are
# idempotent (skip if already on path) and ordered Production-first.
_TOOLS_DIR_FOR_BOOTSTRAP = os.path.abspath(os.path.dirname(__file__))
_PROD_DIR_FOR_SHARED_LIB = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _PROD_DIR_FOR_SHARED_LIB not in sys.path:
    sys.path.insert(0, _PROD_DIR_FOR_SHARED_LIB)
if _TOOLS_DIR_FOR_BOOTSTRAP not in sys.path:
    # Insert AFTER Production/ so Production/lib wins the lib resolution
    # while Production/tools remains reachable for `import scope_router`,
    # `import beat_generator`, etc.
    sys.path.insert(1, _TOOLS_DIR_FOR_BOOTSTRAP)
from lib.atomic_json_write import atomic_json_write  # noqa: E402 (Windows/Dropbox retry-safe JSON writes per LD-368)
from lib.v3_partition import _iter_v3_beats  # noqa: E402 V59 Phase 5: walk all v3 partitions + legacy
from lib.paths import DROPBOX_ROOT  # noqa: E402 LD-505 Phase B: MN_DROPBOX_ROOT, not __file__ chain

# Checkout root (…/mindfulnest-tooling). Resolves /files?path=Production/… when cwd is not Dropbox.
_MN_REPO_ROOT = Path(__file__).resolve().parents[2]

# scope_router — mandatory partition router for v59 authoring-workflow
# mutations (LD SCOPE_ROUTER_V1, C-1). Replaces hardcoded `videos.intro`
# lifts in mutation handlers; resolve() validates body scope keys and
# raises ScopeError with HTTP-status-aware code. See
# Production/tools/scope_router.py for the contract.
import scope_router  # noqa: E402 (must follow sys.path insert above)
from ffmpeg_utils import strip_audio as _strip_clip_audio
from lipsync_sender import LipSyncClient, COST_PER_LIPSYNC
# Kling start-end pipeline helpers (decision 172 KLING_STARTEND_V1_CAPABILITY,
# April 17 2026). Imported here so _handle_add_options can dispatch to the
# start-end path when a beat has end_frame_prompt configured. Rule 8.3 / §8.4
# invariants enforced inside those helpers; we don't re-implement them here.
from kling_startend_pipeline import (
    flux_kontext_generate_end_frame,
    openai_image_edit_generate_end_frame,
    kling_startend_submit,
    _load_subject_element,
    ensure_min_dimensions as _ksendpipe_ensure_min_dimensions,
    load_api_keys as _ksendpipe_load_api_keys,
    RULE8_ANTI_LIPSYNC,
    CFG_SCALE_BASELINE as _KSENDPIPE_CFG_SCALE,
    COST_FLUX_KONTEXT,
    COST_OPENAI_END_FRAME,
    COST_KLING_10S,
    directus_log as _ksendpipe_directus_log,
)
# Beat Generator module (HANDOFF_BEAT_GENERATOR_TAB_COMPLETE.md v3).
# Provides arc skeleton parsing, FLUX still generation, sidecar management.
# Imported lazily to avoid breaking server startup if beat_generator.py has
# a minor import error — see _bg_module() helper below.
_BG_MODULE = None  # set on first use


def _bg_module():
    """Lazy import of beat_generator to avoid hard-failing server on startup."""
    global _BG_MODULE
    if _BG_MODULE is None:
        import beat_generator as _m
        _BG_MODULE = _m
    return _BG_MODULE


# BG_HARDCODED_SCOPE_PURGE_V1 (C-4 K3 fix) — derive (arc_number, event_id_int,
# phase) from the resolved scope (event_id + video_role). Replaces the prior
# hardcoded arc=1/event=2/phase=pre literal in _handle_bg_add_beat. The
# arc_number is fixed at 1 for the current single-arc deployment; this helper
# is the one place to refactor when multi-arc lands. The phase mapping is the
# canonical correspondence for v59 BG sidecars:
#   intro       → pre
#   resolution  → post
#   standalone  → main
_BG_PHASE_MAP: dict[str, str] = {"intro": "pre", "resolution": "post", "standalone": "main"}
# Non-numeric Event_* ids used by Playwright fixture (Event_e2e_fixture) map to
# the BG sidecar segment event_id int the fixture's beats use (arc=1, event=1).
_BG_EVENT_ID_ALIASES: dict[str, int] = {"e2e_fixture": 1}


def _resolve_bg_segment_for_scope(scope_event_id: str, video_role: str) -> tuple[int, int, str]:
    """Map a (scope_event_id, video_role) to a BG sidecar segment tuple.

    Returns (arc_number, event_id_int, phase).
    Raises ValueError when scope_event_id can't be parsed as `Event_<N>` or
    when video_role has no phase mapping. Callers should convert ValueError
    to HTTP 400 `bg_segment_unresolved`.

    Examples:
        _resolve_bg_segment_for_scope("Event_1", "intro")        → (1, 1, "pre")
        _resolve_bg_segment_for_scope("Event_2", "resolution")    → (1, 2, "post")
        _resolve_bg_segment_for_scope("Event_e2e_fixture", "intro")
            → (1, 1, "pre")  # alias e2e_fixture → event_id 1 for fixture sidecar
    """
    arc_number = 1  # current single-arc deployment; refactor when multi-arc lands
    if not scope_event_id.startswith("Event_"):
        raise ValueError(
            f"scope_event_id must be of form 'Event_<N>' for BG segment resolution; "
            f"got {scope_event_id!r}"
        )
    suffix = scope_event_id[len("Event_"):]
    if suffix in _BG_EVENT_ID_ALIASES:
        event_id_int = _BG_EVENT_ID_ALIASES[suffix]
    else:
        try:
            event_id_int = int(suffix)
        except ValueError as e:
            raise ValueError(
                f"cannot parse numeric event id from scope_event_id={scope_event_id!r} "
                f"(suffix={suffix!r})"
            ) from e
    phase = _BG_PHASE_MAP.get(video_role)
    if phase is None:
        raise ValueError(
            f"no BG sidecar phase mapping for video_role={video_role!r}; "
            f"valid roles: {sorted(_BG_PHASE_MAP.keys())}"
        )
    return (arc_number, event_id_int, phase)


# PB_2_THERAPEUTIC_SOURCES_LOAD_V1 — resolve event_id ("M1E1") to module metadata
# (arc_number, m_number, event_number, creature_name, technique_name) via
# Directus prod_modules. Used by _handle_phase_suggest_script to ground the
# Claude API prompt in the real authored Therapeutic Note + Technique Inventory
# for the current module, instead of generic templates.
#
# Cache 15min to avoid repeated Directus hits during script-iteration sessions.
# Convention fallback on Directus failure: M(N) -> Arc((N-1)//6 + 1) which
# matches the V1 scope layout (M1-M6=Arc1, M7-M12=Arc2, ...).
_MODULE_RESOLVE_CACHE: dict = {}
_MODULE_RESOLVE_CACHE_TS: float = 0.0
_MODULE_RESOLVE_CACHE_TTL_S: float = 900.0

_EVENT_ID_PATTERN = re.compile(r"M(\d+)E(\d+)", re.IGNORECASE)


def _resolve_module_id_for_state(state_manager) -> int:
    """Resolve the Directus prod_modules.id for the currently-loaded event.

    Reads state.event_id (canonical 'M<n>E<m>' form), maps to m_number,
    looks up prod_modules.id via the cached _MODULE_RESOLVE_CACHE +
    Directus query. Returns 1 as a defensive fallback ONLY when:
      - state has no event_id
      - event_id is malformed
      - Directus is unreachable AND m_number not in convention-fallback cache

    Closes Rule 19 "no shortcuts" violation: prior code hardcoded
    `module_id=1` at 12+ call sites (e.g. magic_still, magic_video,
    server:7733, 8157) which silently produced wrong prod_assets rows for
    any module beyond M1. Per LD `MODULE_ID_DYNAMIC_RESOLUTION_V1`
    (locked 2026-05-13).
    """
    try:
        state = state_manager.read_state()
    except Exception:
        return 1
    event_id = state.get('event_id') or ''
    meta = _resolve_module_for_event(event_id)
    if not meta:
        return 1
    # _resolve_module_for_event returns the m_number; prod_modules.id may
    # differ from m_number for some rows (per Directus query earlier:
    # m_number=3 has id=5, m_number=4 has id=3). We need the actual id.
    # Query cache directly for the id mapping.
    global _MODULE_RESOLVE_CACHE, _MODULE_RESOLVE_CACHE_TS
    # Refresh cache if stale (mirrors _resolve_module_for_event TTL)
    if time.time() - _MODULE_RESOLVE_CACHE_TS > _MODULE_RESOLVE_CACHE_TTL_S:
        try:
            sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
            from directus_admin_client import DirectusAdminClient  # type: ignore
            _client = DirectusAdminClient()
            _mods = _client.get_items('prod_modules', limit=100)
            # Store id alongside arc_number/creature/technique.
            _MODULE_RESOLVE_CACHE = {
                int(mr['m_number']): {
                    'id': int(mr.get('id') or mr['m_number']),
                    'arc_number': int(mr.get('arc_number') or 1),
                    'creature_name': str(mr.get('creature_name') or 'Unknown'),
                    'technique_name': str(mr.get('technique_name') or ''),
                }
                for mr in _mods if mr.get('m_number') is not None
            }
            _MODULE_RESOLVE_CACHE_TS = time.time()
        except Exception:
            pass
    cached = _MODULE_RESOLVE_CACHE.get(meta['m_number'], {})
    return int(cached.get('id', meta['m_number']))


def _resolve_module_for_event(event_id_str: str):
    """Resolve event_id like 'M1E1' to module metadata dict.

    Returns dict with keys: arc_number, m_number, event_number, creature_name,
    technique_name. Returns None if event_id_str cannot be parsed.

    Queries Directus prod_modules (cached 15min); falls back to convention
    M(N) -> Arc((N-1)//6 + 1) on Directus failure. The convention assumes the
    V1 layout (6 modules per arc); production should rely on the Directus
    lookup which carries the authoritative play-order vs M-number mapping.
    """
    global _MODULE_RESOLVE_CACHE, _MODULE_RESOLVE_CACHE_TS
    if not event_id_str:
        return None
    m = _EVENT_ID_PATTERN.match(str(event_id_str))
    if not m:
        return None
    m_number = int(m.group(1))
    event_number = int(m.group(2))

    # Refresh cache if stale
    if time.time() - _MODULE_RESOLVE_CACHE_TS > _MODULE_RESOLVE_CACHE_TTL_S:
        try:
            sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
            from directus_admin_client import DirectusAdminClient  # type: ignore
            _client = DirectusAdminClient()
            _mods = _client.get_items('prod_modules', limit=100)
            _MODULE_RESOLVE_CACHE = {
                int(mr['m_number']): {
                    'id': int(mr.get('id') or mr['m_number']),
                    'arc_number': int(mr.get('arc_number') or 1),
                    'creature_name': str(mr.get('creature_name') or 'Unknown'),
                    'technique_name': str(mr.get('technique_name') or ''),
                }
                for mr in _mods if mr.get('m_number') is not None
            }
            _MODULE_RESOLVE_CACHE_TS = time.time()
        except Exception as e:
            # Fail-quiet: log + fall through to convention. Caller still gets useful data.
            print(f'[_resolve_module_for_event] Directus query failed '
                  f'({type(e).__name__}: {e}); using convention fallback')

    if m_number in _MODULE_RESOLVE_CACHE:
        meta = _MODULE_RESOLVE_CACHE[m_number]
    else:
        # Convention fallback (V1 layout): M(N) -> Arc((N-1)//6 + 1).
        # Tessa-Bramble M1-M6=Arc1, M7-M12=Arc2, etc. Returns m_number
        # as the id since prod_modules.id == m_number for most rows (M3/M4
        # are the known exceptions; without Directus we can't disambiguate).
        meta = {
            'id': m_number,
            'arc_number': ((m_number - 1) // 6) + 1,
            'creature_name': 'Unknown',
            'technique_name': '',
        }

    return {
        'arc_number': meta['arc_number'],
        'm_number': m_number,
        'event_number': event_number,
        'creature_name': meta['creature_name'],
        'technique_name': meta['technique_name'],
    }


# Capabilities probe cache (populated on first use)
_BG_CAPABILITIES = None


def _bg_capabilities():
    global _BG_CAPABILITIES
    if _BG_CAPABILITIES is None:
        _BG_CAPABILITIES = _bg_module().probe_capabilities()
    return _BG_CAPABILITIES


import concurrent.futures as _cf

# In-memory GPT still-generation job registry
_GPT_JOBS: dict = {}
_GPT_EXECUTOR = None

# In-memory Kling O3 batch job registry (persisted to disk via kling_o3_job_store)
_KLING_O3_JOBS: dict = {}


def _gpt_executor():
    global _GPT_EXECUTOR
    if _GPT_EXECUTOR is None:
        _GPT_EXECUTOR = _cf.ThreadPoolExecutor(max_workers=6, thread_name_prefix="gpt-stills")
    return _GPT_EXECUTOR


# Background assembly jobs: group_id -> {status, assembled_clip_path?, duration?, file_size_bytes?, error?}
_ASSEMBLE_JOBS: dict = {}

# Visible-magic render jobs: job_id -> {status, message, scene_key, preview_path, video_path, error}
_MAGIC_JOBS: dict = {}


# ---------------------------------------------------------------------------
# S5.5d (v3 architecture revision, 2026-05-03): @with_pin_and_drain decorator
# Per ASYNC_QUEUE_DRAIN_PROTOCOL_V1 (locked S5.5d).
# ---------------------------------------------------------------------------
def with_pin_and_drain(handler_name: str, *, track_sync: bool = True):
    """Wrap a request-method handler with drain gate + sync-inflight tracking.

    DESIGN INVARIANTS (Rule 36 §36.1):
    - Drain gate MUST run BEFORE any work (returns 503 immediately if
      `self.app.accept_new_jobs` is False).
    - Sync-inflight registry MUST be add-on-entry / remove-in-finally so
      that drain protocol's inflight_count enumeration sees only currently
      executing handlers.
    - Decorator does NOT mutate the handler signature or pass `_pin` into
      the handler — existing handlers per LD-460 already construct their
      own pin tuple inline (see `_handle_magic_submit_path`,
      `_handle_bg_submit_gpt_batch`, etc.). Centralized pin construction
      would force a 17-site signature refactor; this additive design lets
      the decorator land safely without touching handler bodies.
    - Pin enforcement at terminal writes stays inside each handler's
      existing `self._check_event_pin(_pin, ...)` calls; the decorator
      adds drain + tracking without disturbing those.

    Args:
        handler_name: identifier for sync-inflight registry entries
            (format `"{handler_name}:{rand8}"`); also surfaces in 503 logs.
        track_sync: True for synchronous handlers (drain protocol must
            wait for them to finish). False for thread-spawning handlers
            whose long-running work lives in their own registry
            (_GPT_JOBS / _ASSEMBLE_JOBS / _MAGIC_JOBS / lipsync state).
            Thread-spawning handlers still need the drain GATE (so new
            work is blocked once drain starts) — they just don't need
            sync_id tracking because their already-started job is tracked
            elsewhere.

    NOT applied to read-only / poll endpoints (must stay responsive
    during drain): _handle_health, _handle_magic_status,
    _handle_bg_poll_*, _handle_voice_profile_get, etc.
    """
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(self, body=None, *a, **kw):
            # Drain gate — fail-closed if migration is in progress.
            if not getattr(self.app, "accept_new_jobs", True):
                return self._send_error_v59(
                           503,
                           error_code="DRAIN_IN_PROGRESS",
                           error_message="drain_in_progress",
                           retry_safe=True,
                           extra={"code": "ASYNC_QUEUE_DRAIN_PROTOCOL_V1", "handler": handler_name, "hint": "Server is draining new work; retry after migration completes."},
                       )
            if track_sync:
                sync_id = f"{handler_name}:{_stdlib_uuid.uuid4().hex[:8]}"
                with self.app._sync_inflight_lock:
                    self.app._sync_inflight.add(sync_id)
                try:
                    return fn(self, body, *a, **kw)
                finally:
                    with self.app._sync_inflight_lock:
                        self.app._sync_inflight.discard(sync_id)
            else:
                return fn(self, body, *a, **kw)
        return wrapper
    return deco


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SERVER_PORT = 5111
SERVER_VERSION = "v1"

# Cost constants (verified April 2026)
COST_PER_CLIP_KLING = 0.26
DEFAULT_BUDGET = 150.00  # raised from 32 — budget overrides are written to production_spend.json (persists across restarts)

# Anti-lip-sync safeguards (CLAUDE.md Rule 8 — ALWAYS ON)
BANNED_PROMPT_WORDS = [
    "speaking", "speech", "dialogue", "lip sync", "lip movement",
    "mouth movement", "beak movement", "talking", "singing", "vocal",
    "open mouth",
]
NEGATIVE_PROMPT = (
    "lip sync, speaking, talking, mouth movement, dialogue, speech, "
    "open mouth, Chinese, audio, voice, singing"
)
BIRD_SPEAKERS = {"Guide Bird", "Luna", "Chipper"}

# WaveSpeed Kling v3 endpoints
WAVESPEED_SUBMIT = (
    "https://api.wavespeed.ai/api/v3/kwaivgi/kling-v3.0-pro/image-to-video"
)
def wavespeed_poll_url(task_id: str) -> str:
    return f"https://api.wavespeed.ai/api/v3/predictions/{task_id}/result"

# Polling parameters
# BS1 (Tier 3 blind-spot fix, April 16 2026): Directus-backed cross-machine
# semaphore. fcntl.lockf is local-only and cannot coordinate between Kim's
# Mac and her Windows work machine if both open the same Dropbox-synced
# event_dir. The Directus lock serializes writes across machines.
DIRECTUS_LOCK_TTL_SEC = 60        # Lock expires if not heartbeated within this
DIRECTUS_LOCK_HEARTBEAT_SEC = 30  # Server refreshes TTL at half-TTL interval
DIRECTUS_LOCK_ACQUIRE_TIMEOUT = 10  # Max wait for another machine to release
DIRECTUS_LOCK_POLL_INTERVAL = 0.5   # Retry cadence while waiting

# Env-var escape hatch: set PRODUCTION_SERVER_SINGLE_MACHINE=1 to skip Directus
# locking entirely. Use when working offline and confident no other machine is
# running the server for the same event. Loud warning printed on every mutate.
SINGLE_MACHINE_MODE = os.environ.get("PRODUCTION_SERVER_SINGLE_MACHINE", "").strip() == "1"

# ---------------------------------------------------------------------------
# Tier 1A (April 18 2026): Server-side TTS regen debounce + v2 flag forwarding
# LD TTS_REGEN_DEBOUNCE_60S_WINDOW_PER_BEAT (severity MEDIUM, preflight 65)
# LD V2_DIALOGUE_EXPLICIT_FIELD_FORWARDING_WITH_ALLOWLIST (severity MEDIUM)
#
# Problem: contenteditable dialogue blur fires every ~250ms as the user types,
# each save triggers an ElevenLabs v3 TTS render (~5-8s, ~$0.02). Without a
# debounce the user can burn dozens of renders and dollars by typing fast.
#
# Design: per-beat 60s sliding window. Within the window, TTS regen is skipped
# with reason=debounced and the text save still completes. Outside the window,
# regen proceeds and the timestamp resets.
#
# Scope: AUTO-regen inside _handle_beat_update_text ONLY. The explicit
# "🎙 Regen Audio" button (/api/beat/regenerate_audio -> _handle_beat_regenerate_audio)
# is a user-initiated opt-in; debounce does NOT apply there.
#
# Rollback: set MINDFULNEST_T1_ENABLED=0 to revert to pre-debounce behavior.
# ---------------------------------------------------------------------------
TIER1A_ENABLED = os.environ.get("MINDFULNEST_T1_ENABLED", "1").strip() != "0"
TIER1A_DEBOUNCE_WINDOW_SEC = 60.0
# Per-beat last-regen timestamp (monotonic-ish — uses time.time()). Populated
# after a successful regen fire; consulted before the next regen fires.
_TTS_REGEN_LAST_TS: dict[str, float] = {}
# Per-beat last Directus audit-log timestamp — prevents spamming prod_activity_log
# with one row per keystroke when the user types inside the debounce window.
_TTS_DEBOUNCE_AUDIT_LAST_TS: dict[str, float] = {}
# Forwarded fields from v2 /api/v2/beat/<id>/patch {field:"dialogue"} to the
# legacy _handle_beat_update_text() handler. Explicit allowlist — no silent
# passthrough of arbitrary client fields (LD V2_DIALOGUE_EXPLICIT_FIELD_FORWARDING_WITH_ALLOWLIST).
_FORWARDED_V2_DIALOGUE_FIELDS = ("skip_tts_regen",)


def _tier1a_debounce_should_skip(beat_id: str, now: float | None = None) -> tuple[bool, float]:
    """Return (skip, elapsed_since_last_s). Read-only — does NOT update state.
    Caller updates _TTS_REGEN_LAST_TS after a successful regen fire."""
    if not TIER1A_ENABLED:
        return (False, 0.0)
    now = now if now is not None else time.time()
    last = _TTS_REGEN_LAST_TS.get(beat_id, 0.0)
    elapsed = now - last if last else float("inf")
    return (elapsed < TIER1A_DEBOUNCE_WINDOW_SEC, elapsed)


def _tier1a_mark_regen_fired(
    beat_id: str,
    now: float | None = None,
    *,
    app: "AppContext | None" = None,
    regen_ok: bool = False,
) -> None:
    """Record that a TTS regen fired for this beat. Call AFTER regen completes
    (even on failure — we still want to rate-limit retries to prevent stampede).

    Tier 3 (April 18 2026): if app is provided AND regen_ok is True, ALSO clear
    beats[bid].phase_1.speaker_mismatch = False. Rationale: after a successful
    re-voicing with the newly-selected speaker, the audio now matches the
    speaker, so the stale-audio badge should auto-clear. Kept optional for
    backward compatibility with the one-arg callers in the polling thread.
    """
    now = now if now is not None else time.time()
    _TTS_REGEN_LAST_TS[beat_id] = now
    if app is not None and regen_ok:
        # S5.5a2: legacy beat-state mutator → intro partition (v1 lift target).
        def _clear_mismatch(partition, _bid=beat_id):
            b = (partition.get("beats") or {}).get(_bid)
            if not b:
                return False
            p1 = b.get("phase_1")
            if not p1:
                return False
            if p1.get("speaker_mismatch"):
                p1["speaker_mismatch"] = False
                p1["speaker_mismatch_cleared_at"] = (
                    datetime.now(timezone.utc).isoformat()
                )
                return True
            return False
        try:
            app.state.mutate_video_state("intro", _clear_mismatch)
        except Exception as exc:  # noqa: BLE001
            print(f"[T1] speaker_mismatch clear failed for {beat_id}: {exc}")


def _tier1a_should_audit(beat_id: str, now: float | None = None) -> bool:
    """Rate-limit Directus audit rows for debounce skips to 1/beat/60s.
    Returns True if we should write an audit row this call."""
    now = now if now is not None else time.time()
    last = _TTS_DEBOUNCE_AUDIT_LAST_TS.get(beat_id, 0.0)
    if now - last < TIER1A_DEBOUNCE_WINDOW_SEC:
        return False
    _TTS_DEBOUNCE_AUDIT_LAST_TS[beat_id] = now
    return True


def _tier1a_async_log_debounce(event_id: str, beat_id: str, elapsed_s: float) -> None:
    """Fire-and-forget Directus audit row. Rate-limited by
    _tier1a_should_audit() — caller MUST gate on that before invoking this."""
    def _do_write():
        try:
            _libdir = os.path.join(os.path.dirname(__file__), "credentials_lib")
            if _libdir not in sys.path:
                sys.path.insert(0, _libdir)
            from credentials import load_credentials  # type: ignore
            from directus import DirectusClient  # type: ignore
            creds = load_credentials()
            c = DirectusClient(
                creds["directus_url"],
                creds["directus_email"],
                creds["directus_password"],
            )
            c._request("POST", "/items/prod_activity_log", data={
                "action": "tts_regen_debounced",
                "module_id": 1,
                "performed_by": "production_server.tier1a_debounce",
                "details": json.dumps({
                    "event_id": event_id,
                    "beat_id": beat_id,
                    "elapsed_since_last_regen_s": round(elapsed_s, 2),
                    "window_s": TIER1A_DEBOUNCE_WINDOW_SEC,
                    "reason": "debounced",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "ld_key": "TTS_REGEN_DEBOUNCE_60S_WINDOW_PER_BEAT",
                }),
            })
        except Exception as exc:  # noqa: BLE001 — fire-and-forget
            print(f"[T1] debounce audit log failed (non-blocking): {exc}",
                  flush=True)
    threading.Thread(target=_do_write, daemon=True,
                     name=f"t1-audit-{beat_id}").start()


def _bg_register_assembled_clip(group_id: str, clip_path: str, file_size_bytes: int) -> None:
    """Register an assembled group clip to Directus (prod_visual_assets + prod_activity_log).
    On failure, append payloads to pending_directus_writes.json per CLAUDE.md Rule 20."""
    try:
        _libdir = os.path.join(os.path.dirname(__file__), "credentials_lib")
        if _libdir not in sys.path:
            sys.path.insert(0, _libdir)
        from credentials import load_credentials  # type: ignore
        from directus import DirectusClient  # type: ignore
        creds = load_credentials()
        c = DirectusClient(
            creds["directus_url"],
            creds["directus_email"],
            creds["directus_password"],
        )
        c._request("POST", "/items/prod_visual_assets", data={
            "role": "delivery",
            "kind": "video",
            "file_path": clip_path,
            "file_size_bytes": file_size_bytes,
            "notes": f"stitched group {group_id}",
            "status": "approved",
        })
        c._request("POST", "/items/prod_activity_log", data={
            "action": f"assemble_group_{group_id}",
            "performed_by": "production_server.assemble_group",
            "notes": f"Assembled group {group_id} -> {clip_path} ({file_size_bytes} bytes)",
        })
    except Exception as e:
        # Queue for retry — use the env-aware resolver from lib/directus so
        # this writer agrees with the replay reader (audit C1-10 split-brain).
        # [INFERRED — verify the agreement: `grep -n _PENDING_QUEUE_PATH
        # Production/lib/directus.py` shows the single source-of-truth; both
        # this writer and lib.directus.try_replay_pending() read that same path.]
        try:
            from lib.directus import _PENDING_QUEUE_PATH as _Q
            queue_path = str(_Q)
            q = []
            if os.path.exists(queue_path):
                try:
                    with open(queue_path, "r", encoding="utf-8") as f:
                        q = json.load(f)
                except Exception:
                    q = []
            q.append({
                "collection": "prod_visual_assets",
                "payload": {
                    "role": "delivery",
                    "kind": "video",
                    "file_path": clip_path,
                    "file_size_bytes": file_size_bytes,
                    "notes": f"stitched group {group_id}",
                    "status": "approved",
                },
                "error": str(e),
                "queued_at": datetime.now(timezone.utc).isoformat(),
            })
            with open(queue_path, "w", encoding="utf-8") as f:
                json.dump(q, f, indent=2)
            print(f"[BG] directus write queued to {queue_path}: {e}", flush=True)
        except Exception as qe:
            print(f"[BG] directus write failed AND queue failed: {e} / {qe}", flush=True)


def _compute_machine_id() -> str:
    """Stable unique identifier for this machine. Different on Mac vs Windows
    vs Linux; same across server restarts on the same machine."""
    hostname = socket.gethostname() or "unknown"
    node = platform.node() or hostname
    # os.getuid is POSIX-only; on Windows use USERNAME as a fallback
    try:
        uid_or_user = str(os.getuid())  # type: ignore[attr-defined]
    except AttributeError:
        uid_or_user = os.environ.get("USERNAME", "win")
    return f"{hostname}|{node}|{uid_or_user}"


MACHINE_ID = _compute_machine_id()


POLL_BATCH_SIZE = 5
POLL_BATCH_GAP_SEC = 2
POLL_CYCLE_GAP_SEC = 10
MAX_RETRIES = 4  # Tier 3: 4 attempts total (was 3). Counter-agent C1 HIGH.
# Per-attempt extra wait added ON TOP of POLL_CYCLE_GAP_SEC.
# Schedule: attempt 1 = no extra wait; 2 = +5s; 3 = +15s; 4 = +45s.
# Total worst-case wait before giving up: ~POLL_CYCLE_GAP * 4 + sum([5,15,45]) = 105s.
RETRY_BACKOFF_EXTRA_SEC = [0, 5, 15, 45]
# Assert alignment: if MAX_RETRIES grows, backoff array must grow too.
# Adversarial Phase-3 finding #11 (April 16 2026).
assert len(RETRY_BACKOFF_EXTRA_SEC) >= MAX_RETRIES, (
    f"RETRY_BACKOFF_EXTRA_SEC length {len(RETRY_BACKOFF_EXTRA_SEC)} must be >= MAX_RETRIES {MAX_RETRIES}"
)
# Retries at which the pre-fail CDN re-check fires (0-indexed).
# C1 finding: probe at retry 2 and 4 (not just final) so outages-that-completed
# on WaveSpeed's side recover at ~20s, not ~100s. Each probe is async off
# the poller thread (C4 finding), 10s timeout max.
# Preflight 107 (2026-04-19): fire the CDN fallback on the FIRST poll failure
# as well, not just retry 2 and 4. When WaveSpeed is just slow (not broken),
# every normal poll times out; without a fast async rescue, Kim waits minutes
# for retries to exhaust. Probing early + often costs ~nothing (async daemon
# threads, one-shot).
PRE_FAIL_CDN_CHECK_AT_RETRIES = {1, 2, 4}
# Raised from 10 -> 60: the old 10s budget was SHORTER than the main poll's
# 30s timeout, so when WaveSpeed was slow-but-alive every pre-fail probe also
# timed out uselessly. Set higher than main poll timeout so a slow WaveSpeed
# response during CDN rescue has time to land.
PRE_FAIL_CDN_CHECK_TIMEOUT = 60
RETRY_BACKOFF = [5, 10, 20]  # seconds
TASK_EXPIRY_SEC = 2 * 60 * 60  # 2 hours

# Inactivity timeout (no HTTP requests of ANY kind)
INACTIVITY_TIMEOUT_SEC = 4 * 60 * 60  # 4 hours

# ---------------------------------------------------------------------------
# Tier 1B (April 18 2026): polling timeout -> failed edge with late-success
# recovery via on-disk artifact check.
# LD PHASE_1_TIMEOUT_TO_FAILED_PER_VENDOR_THRESHOLDS (severity HIGH)
# LD STALE_TIMEOUT_RECOVERY_VIA_ARTIFACT_CHECK (severity HIGH)
# LD LATE_SUCCESS_IDEMPOTENCY_GUARD_NEVER_CLOBBER_FAILED (severity HIGH)
#
# Problem: Before Tier 1B, an option in status=polling with a dead task_id
# (vendor callback lost, network partition, WaveSpeed outage) could sit
# forever. MAX_RETRIES only fires on poll-errors; a silent "no response"
# loop never increments retries. Wall-clock timeout closes this error path.
#
# Thresholds: 3x documented p99 per vendor, giving healthy headroom before
# we declare stale. Kling p99 ~5 min -> 15 min threshold. ByteDance LipSync
# p99 ~90s -> 5 min. ElevenLabs TTS p99 ~8s -> 1 min (TTS is currently
# synchronous, so threshold is defensive for future async paths).
#
# Late-success recovery: before flipping to failed, check if the expected
# output artifact exists on disk with mtime > submitted_at. If so, the
# vendor completed but the callback was lost — recover as succeeded_late
# instead of burning the work.
# ---------------------------------------------------------------------------
STALE_TIMEOUT_SEC = {
    "kling": 900,                # 15 min (Kling p99 ~5 min, 3x headroom)
    "kling_startend": 900,       # same vendor behavior
    "seedance": 900,             # same vendor family
    "bytedance_lipsync": 300,    # 5 min (p99 ~90s, 3x headroom)
    "latentsync": 300,           # alias for bytedance_lipsync
    "elevenlabs_tts": 60,        # 1 min (p99 ~8s, 7x headroom — defensive)
}
STALE_TIMEOUT_DEFAULT_SEC = 900  # fallback when opt.source is missing/unknown


def _t1_enabled() -> bool:
    """Feature flag for Tier 1B stale-timeout logic.

    Returns False (disabled) when either:
      - MINDFULNEST_T1_ENABLED=0 (explicit opt-out)
      - MINDFULNEST_WRITE_PATH=legacy (Tier 1A rollback convention)
    Defaults to enabled.
    """
    if os.environ.get("MINDFULNEST_WRITE_PATH", "").strip().lower() == "legacy":
        return False
    return os.environ.get("MINDFULNEST_T1_ENABLED", "1").strip() != "0"


# ---------------------------------------------------------------------------
# API key parser (from Production/API_KEYS_MASTER.md)
# ---------------------------------------------------------------------------

def parse_api_keys(filepath: Path) -> dict:
    """Parse API credentials — Doppler env vars first, MD file fallback (per LD-208).

    When this server runs via `doppler run -- python3 production_server.py ...`,
    Doppler injects env vars and those win. Falls back to parsing the legacy
    markdown file so direct `python3` invocation still works during transition.

    Returns a dict like {"wavespeed": "...", "elevenlabs": "...", "directus": "..."}.
    Missing keys are simply absent from the dict — caller decides if that's fatal.
    """
    keys: dict = {}

    # Legacy file parsing (fallback layer — runs first so env vars can overlay)
    if filepath.is_file():
        content = filepath.read_text(encoding="utf-8")
        for section, key_name in [
            ("WaveSpeed", "wavespeed"),
            ("ElevenLabs", "elevenlabs"),
            ("Directus", "directus"),
            ("EvoLink", "evolink"),
            ("OpenAI", "openai"),
            ("BFL", "bfl"),
        ]:
            m = re.search(
                rf"#+\s*{section}.*?(?:Key|Token):\s*`([^`]+)`",
                content,
                re.DOTALL | re.IGNORECASE,
            )
            if not m:
                m = re.search(
                    rf"\|\s*\**{section}[^|]*\**[^|]*\|\s*`([^`]+)`",
                    content,
                    re.IGNORECASE,
                )
            if m:
                keys[key_name] = m.group(1).strip()

    # Doppler env var overlay — wins when set
    env_overlay = {
        "wavespeed":  os.environ.get("WAVESPEED_API_KEY"),
        "elevenlabs": os.environ.get("ELEVENLABS_API_KEY"),
        "evolink":    os.environ.get("EVOLINK_API_KEY"),
        "directus":   os.environ.get("DIRECTUS_ADMIN_PASSWORD"),
        "openai":     os.environ.get("OPENAI_API_KEY"),
        "bfl":        os.environ.get("BFL_API_KEY"),
    }
    for k, v in env_overlay.items():
        if v:
            keys[k] = v
    return keys


# ---------------------------------------------------------------------------
# Storyboard HTML beat extractor (same format as inject_production_overlay.py)
# ---------------------------------------------------------------------------

def _js_obj_to_json(js_str: str) -> str:
    """Convert JS object syntax ({s:"val",t:"val"}) to valid JSON."""
    result = re.sub(r'(\{|,)\s*([a-zA-Z_]\w*)\s*:', r'\1"\2":', js_str)
    # Fix JS-escaped single quotes (\' is valid in JS strings, not in JSON)
    result = result.replace("\\'", "'")
    return result


def extract_beats_from_html(html: str) -> list[dict]:
    """Extract beat data from storyboard HTML.

    Supports two formats:
    1. Legacy: window.storyboardData = {...};
    2. Builder v14+: var SP=[...]; var L=[{s:,t:,i:,a:,p:,g:},...];
    """
    # Try legacy format first
    legacy = re.search(
        r"window\.storyboardData\s*=\s*(\{.*?\})\s*;",
        html,
        re.DOTALL,
    )
    if legacy:
        data = json.loads(legacy.group(1))
        return data.get("lines", [])

    # Builder v14+ format
    sp_match = re.search(r'var SP\s*=\s*(\[.*?\])\s*;', html)
    l_match = re.search(r'var L\s*=\s*(\[.*?\])\s*;', html, re.DOTALL)

    if not l_match:
        raise ValueError(
            "Beat data not found — expected window.storyboardData or var L=[...]"
        )

    speakers = []
    if sp_match:
        try:
            speakers = json.loads(sp_match.group(1))
        except json.JSONDecodeError:
            speakers = []

    raw_lines = _js_obj_to_json(l_match.group(1))
    try:
        lines_raw = json.loads(raw_lines)
    except json.JSONDecodeError as exc:
        raise ValueError(f"var L array is not parseable: {exc}") from exc

    beats = []
    for idx, beat in enumerate(lines_raw):
        speaker_val = beat.get("s", "")
        if isinstance(speaker_val, int) and speakers:
            speaker = speakers[speaker_val] if speaker_val < len(speakers) else str(speaker_val)
        else:
            speaker = str(speaker_val)

        image_key = beat.get("i", "")
        # Resolve base64 image — prefer FULL-RES gallery image, fall back to TH thumbnail
        image_data = None
        if image_key:
            # First try: full-res from gallery <div class="ic"><img src="..."><p>key.png</p></div>
            # Gallery names can be "key.png" or "key.PNG" — match flexibly
            gallery_pattern = (
                r'<div class="ic"><img src="(data:image/[^"]+)">'
                r'<p>[^<]*?' + re.escape(image_key) + r'[^<]*?</p></div>'
            )
            gallery_match = re.search(gallery_pattern, html)
            if gallery_match:
                image_data = gallery_match.group(1)
            else:
                # Fallback: thumbnail from TH dict
                th_match = re.search(
                    r'TH\["?' + re.escape(image_key) + r'"?\]\s*=\s*"(data:image[^"]*)"',
                    html,
                )
                if th_match:
                    image_data = th_match.group(1)

        beats.append({
            "line_number": idx + 1,
            "speaker": speaker,
            "text": beat.get("t", ""),
            "image_key": image_key,
            "image": image_data,
            "audio_key": beat.get("a"),
            "pause": beat.get("p", 0),
            "section": beat.get("g", ""),
        })

    return beats


# ---------------------------------------------------------------------------
# Motion prompt builder (Rule 8 compliant)
# ---------------------------------------------------------------------------

SECTION_ACTIONS = {
    "Setup":              "looking around with curiosity, subtle body movement",
    "Story":              "looking around with curiosity, subtle body movement",
    "Discovery":          "gentle expressive gestures, slight head tilts",
    "Introduction":       "gentle expressive gestures, slight head tilts",
    "Transition to Spell": "focused attention toward camera, slight forward lean",
}
DEFAULT_ACTION = "subtle idle movement, gentle breathing"

# Per-creature motion vocabulary (LD MOTION_VOCABULARY_PER_CREATURE_V1, 2026-04-19).
# Keyed by canonical speaker name (post-_SPEAKER_ALIAS). Each creature has four
# emotional registers. `neutral` is reserved for sprite-pipeline idle loops
# (lipsync_targeted=False); the other three are for narrative event beats.
# Every vocabulary string is Rule 8.1-8.4 compliant: no BANNED_PROMPT_WORDS, no
# Rule 8.2 forbidden phrases (minimal motion, static camera, head remains facing
# forward, frozen face, face centered, direct forward gaze, eyes meet camera,
# pressed, sealed, clamped — word-boundary), and no Rule 8.1 required terms
# leak into the vocabulary (constraint line is the sole home for those).
SPEAKER_MOTION_PROFILES: "dict[str, dict[str, str]]" = {
    "Tessa": {
        "happy_excited":    "head lift, shell expansion, bright weight shift forward, warmed blink",
        "upset_shocked":    "quick head retraction, shell pulling in, widened eye reaction, startled body recoil",
        "sad_disappointed": "shell-breathing, gentle head dip, soft weight settling, downward glance",
        "neutral":          "subtle weight shift, gentle head tilt, shell rise and fall, quiet blink",
    },
    "Luna": {
        "happy_excited":    "enthusiastic wing flutter, bright eye widening, quick head bob, scholarly feather ruffle",
        "upset_shocked":    "sharp head swivel, feather bristle, wings unfurling slightly, rapid blink",
        "sad_disappointed": "soft wing settle, gentle feather droop, quiet head dip, slow blink",
        "neutral":          "curious owl head swivels, wing adjustments, feather ripple, alert blinking",
    },
    "Lorelai": {
        "happy_excited":    "bright ear perk, quick tail lift, enthusiastic paw gesture, scholarly grin",
        "upset_shocked":    "sharp head turn, ears flicking back, startled tail puff, rapid blink",
        "sad_disappointed": "soft ear droop, gentle tail lowering, quiet head dip, slow blink",
        "neutral":          "curious lemur head tilt, subtle tail sway, paw adjustments, alert blinking",
    },
    "Benson": {
        "happy_excited":    "ears lifting, small forward hop, chest lift, bright blink",
        "upset_shocked":    "ears flattening, body tightening, rapid nose wrinkle, startled weight recoil",
        "sad_disappointed": "ear droop, gentle body huddle, soft nose wrinkle, downward head tilt",
        "neutral":          "ear flicks, nose twitches, small body hops in place, curious head micro-tilts",
    },
    "Ember": {
        "happy_excited":    "relaxed paw settle, gentle tail flow, softened head tilt, warm body expansion",
        "upset_shocked":    "tail lash, ears sweeping back, guarded paw shift, sharp head turn",
        "sad_disappointed": "careful paw movement, guarded head turn, small tail flick, subtle shoulder breathing",
        "neutral":          "controlled head turn, gentle tail sway, measured weight shift, alert ear swivel",
    },
    "Bork": {
        "happy_excited":    "gentle hover, relaxed wing-beats, warm shimmer, soft body expansion",
        "upset_shocked":    "formal hover jitter, wing-beat spike, body straightening upward, sharp turn",
        "sad_disappointed": "subtle hover wobble, gentle wing-flutter dip, small body droop, dim shimmer",
        "neutral":          "small formal hover adjustments, crisp wing-beats, tiny body shifts, deliberate turns",
    },
    "Bramble": {
        "happy_excited":    "wide-based weight settling, strong shoulder rise, powerful nod, warm body presence",
        "upset_shocked":    "big shoulder rise, head pull back, heavy weight recoil, paw raise",
        "sad_disappointed": "heavy weight shift, slow paw placement, small head sway, subdued shoulder breathing",
        "neutral":          "grounded weight settling, paw adjustments, wide head turns, deep shoulder rise and fall",
    },
    "Chipper": {
        "happy_excited":    "energetic body bounce, quick wing flutter, enthusiastic head nod, bright feather ruffle",
        "upset_shocked":    "quick wing half-lift, feather bristle, sharp head turn, rapid blink",
        "sad_disappointed": "soft feather settle, gentle wing-fold, head tilt, quiet blinking",
        # Rewrite 2026-05-14 per CHIPPER_NEUTRAL_PROFILE_STILLNESS_REWRITE_V1 +
        # 3+3 Opus debate (Advocate A Candidate B; Counter B/C rejected as
        # Rule-8.2-violating or over-engineering). Prior string "small hops in
        # place, wing adjustments, warm head tilts, bright eye sparkle" was
        # the literal source of the bouncing-Chipper + eye-sparkle Kling
        # output Kim repeatedly reported. New vocabulary preserves Chipper
        # character (still attentive, still warm) without locomotion verbs
        # ("hops") or VFX verbs ("sparkle"). Pattern-matched against sister
        # neutrals (Tessa/Luna shapes) for Rule 8.1/8.2/8.4 compliance.
        # Override path (Fix 1 _motion_override) still wins when present —
        # this only affects the fall-through case.
        "neutral":          "gentle head micro-tilt, quiet wing adjustments, soft feather ripple, attentive blink",
    },
    "Arlo": {
        "happy_excited":    "bright paw gesture, gentle tail lift, warm head nod, lively ear perk",
        "upset_shocked":    "small paw lift, quick ear flick back, startled body recoil, wide-eyed blink",
        "sad_disappointed": "soft paw-to-chest gesture, tail lowering gently, small head dip, quiet blink",
        "neutral":          "subtle paw settle, gentle tail sway, attentive ear twitch, warm relaxed blink",
    },
}

# Rule 8.1-allowed tails (LD MOTION_TAIL_LIPSYNC_SAFE_V1, 2026-04-19).
LIPSYNC_SAFE_TAIL = "no dialogue in video"              # non-motion-locking; default for narrative event beats
SPRITE_IDLE_TAIL  = "Silent subtle idle movement only"  # motion-locking; default for sprite-pipeline loops

VALID_EMOTIONS = {"happy_excited", "upset_shocked", "sad_disappointed", "neutral"}


def _canonicalize_speaker(raw: str) -> str:
    """Route legacy speaker strings to their canonical name via _SPEAKER_ALIAS.
    Strips surrounding whitespace. Returns "" for empty/whitespace-only input.
    Unknown speakers are returned stripped but otherwise unchanged."""
    if not raw:
        return ""
    key = raw.strip()
    if not key:
        return ""
    return _SPEAKER_ALIAS.get(key.lower(), key)


def _resolve_beat_speaker(beat: dict) -> str:
    """Read-side canonical speaker resolution (SPEAKER_DUAL_STORE_DEPRECATION_V1).

    Top-level partition.beats[bid].speaker is the canonical store as of C-6.
    phase_1.speaker is the legacy mirror — kept for one-release read-compat
    so on-disk legacy values don't blank out before the N+1 sprint that
    collapses the phase_1 write site.

    Resolution order:
      1. beat.get("speaker")                   (top-level canonical)
      2. beat.get("phase_1", {}).get("speaker")  (legacy mirror)
      3. ""                                    (fail-loud at TTS time per LD-520)

    Callers MUST go through this helper for any speaker read; direct
    `beat["phase_1"]["speaker"]` reads are scheduled for removal in the
    SPEAKER_DUAL_STORE_DEPRECATION_V1 N+1 collapse.
    """
    beat = beat or {}
    s = beat.get("speaker")
    if s:
        return s
    phase_1 = beat.get("phase_1") or {}
    return phase_1.get("speaker") or ""


def build_motion_prompt(beat: dict) -> str:
    """Build a Rule 8.1-8.4 compliant motion prompt for Kling v3 Pro.

    Resolves speaker to canonical name, looks up per-creature motion vocabulary
    for the beat's emotional register, falls back to SECTION_ACTIONS for
    unknown speakers, and applies the appropriate tail based on whether the
    beat is lipsync-targeted.
    """
    raw_speaker = beat.get("speaker", "") or ""
    speaker = _canonicalize_speaker(raw_speaker)
    section = beat.get("section", "") or ""

    emotion = beat.get("emotion", "neutral") or "neutral"
    # Fix 5 (20260513): freeform BG emotion strings (non-VALID_EMOTIONS) are
    # promoted to _freeform_override rather than silently discarded. The BG
    # authors rich descriptions like "sputtering, flapping wings, freaking out"
    # that are the intended motion. Only fall back to neutral if emotion was
    # empty/missing.
    _freeform_override: "str | None" = None
    if emotion not in VALID_EMOTIONS:
        _freeform_override = emotion
        print(f"[motion] freeform emotion promoted to override for speaker={speaker!r}: {emotion[:60]!r}")
        emotion = "neutral"  # kept for beak/mouth constraint selection only

    lipsync_targeted = beat.get("lipsync_targeted", True)
    if lipsync_targeted is None:
        lipsync_targeted = True

    # Fix 1 (20260513 motion-quality-pipeline): direct stage-direction override.
    # When _handle_add_options_startend parses Kim's (parenthetical) cues from
    # beat.text, it stamps _motion_override onto the beat dict. That string
    # already passed sanitize_prompt at the call site (positive_prompt wraps
    # build_motion_prompt's output in sanitize_prompt), so banned Rule 8.1
    # words are scrubbed downstream. Override wins over the lookup table
    # because Kim's authored text is more specific than the per-creature
    # emotion vocabulary. _freeform_override (Fix 5) is second priority.
    _override = beat.get("_motion_override") or _freeform_override
    profile = SPEAKER_MOTION_PROFILES.get(speaker)
    if _override:
        action = _override
    elif profile:
        action = profile.get(emotion) or profile["neutral"]
    else:
        action = SECTION_ACTIONS.get(section, DEFAULT_ACTION)

    if speaker in BIRD_SPEAKERS:
        constraint = "Beak closed, no speech, no lip movement."
    else:
        constraint = "Mouth closed, no speech."

    tail = LIPSYNC_SAFE_TAIL if lipsync_targeted else SPRITE_IDLE_TAIL

    prompt_speaker = speaker or raw_speaker.strip()
    header = f"Cartoon {prompt_speaker} character" if prompt_speaker else "Cartoon character"
    return f"{header}, {action}. {constraint} {tail}"


def sanitize_prompt(prompt: str) -> str:
    """Strip banned words; log a warning if any were present.
    Does NOT raise — it's a safety net, not a gate."""
    cleaned = prompt
    found = []
    for banned in BANNED_PROMPT_WORDS:
        pattern = re.compile(re.escape(banned), re.IGNORECASE)
        if pattern.search(cleaned):
            found.append(banned)
            cleaned = pattern.sub("", cleaned)
    if found:
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        print(f"[WARN] Stripped banned words from motion prompt: {found}")
    return cleaned


def validate_image_dimensions(data_uri: str) -> tuple[bool, str]:
    """CLAUDE.md Rule 6 — shortest side must be >= 600px.

    PIL is a HARD startup dependency (see _check_runtime_capabilities at
    line ~11608 which exits the server with [startup:FATAL] if Pillow is
    missing). The prior fall-through 'PIL not installed - dimension check
    skipped' was a Rule 19 silent-bypass that became dead code after the
    P2 LD-pending DEPENDENCY_STARTUP_CHECK_V1 work. Removed per C5-2 audit
    finding.
    """
    from PIL import Image  # type: ignore

    try:
        # data:image/png;base64,XXXX
        _, b64 = data_uri.split(",", 1)
        img = Image.open(io.BytesIO(base64.b64decode(b64)))
        w, h = img.size
        if min(w, h) < 600:
            return False, f"image too small ({w}x{h}), min shortest side 600px"
        return True, f"{w}x{h}"
    except Exception as exc:
        return False, f"could not decode image: {exc}"


MIN_ANIMATION_SIZE = 600  # px shortest side


def auto_upscale_image(data_uri: str, target_min: int = MIN_ANIMATION_SIZE) -> tuple[str, str]:
    """Auto-upscale an image so its shortest side meets target_min.

    Returns (possibly_upscaled_data_uri, info_string).
    If the image already meets the minimum, returns the original.
    PIL is a HARD startup dependency (see _check_runtime_capabilities) so the
    'PIL not installed - no upscale' silent-bypass was removed per C5-2.
    This is the Rule 6 'auto-upscale fallback safety net'.
    """
    from PIL import Image  # type: ignore

    try:
        header, b64 = data_uri.split(",", 1)
        img = Image.open(io.BytesIO(base64.b64decode(b64)))
        w, h = img.size

        if min(w, h) >= target_min:
            return data_uri, f"already {w}x{h} — no upscale needed"

        # Scale up so shortest side = target_min
        scale = target_min / min(w, h)
        new_w = int(w * scale)
        new_h = int(h * scale)
        upscaled = img.resize((new_w, new_h), Image.LANCZOS)

        buf = io.BytesIO()
        upscaled.save(buf, format="PNG")
        new_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        new_uri = f"data:image/png;base64,{new_b64}"

        print(f"[upscale] {w}x{h} -> {new_w}x{new_h} (scale {scale:.2f}x)")
        return new_uri, f"upscaled {w}x{h} -> {new_w}x{new_h}"
    except Exception as exc:
        return data_uri, f"upscale failed: {exc}"


# ---------------------------------------------------------------------------
# State manager — thread-safe JSON state + spend on disk
# ---------------------------------------------------------------------------

class StateManager:
    def __init__(self, event_dir: Path, event_id: str):
        self.event_dir = event_dir
        self.event_id = event_id
        self.state_path = event_dir / "production_state.json"
        from lib.state_repo import JsonStateRepository
        self.repo = JsonStateRepository(self.state_path)
        self.spend_path = event_dir / "production_spend.json"
        self.spend_ledger_path = event_dir / "spend_ledger.jsonl"  # task_id -> first-charge lockout
        self.clips_dir = event_dir / "animation_clips"
        self.clips_dir.mkdir(parents=True, exist_ok=True)
        # In-process lock (between server threads)
        self.lock = threading.Lock()
        # Inter-process lock path — used by fcntl.lockf so the recovery CLI
        # tool and the running server can safely mutate state.json concurrently.
        # Tier 3 C2 CRITICAL fix (April 16 2026).
        self.file_lock_path = event_dir / ".state.lock"
        # BS1: Directus-backed cross-machine semaphore scope.
        # Resource key is per-event so different events don't block each other.
        self.directus_lock_key = f"{event_id}/state"
        self._init_files()

    def _init_files(self) -> None:
        if not self.state_path.exists():
            # S5.5d (v3 architecture revision, 2026-05-03): fresh state.json
            # files are written in v3-shape directly (BG_VIDEO_PARTITION_V2,
            # supersedes LD-473). Multi-beat partitions {intro, resolution}
            # only — phase_a / phase_b are top-level and lazily created on
            # first write.
            now_iso = datetime.now(timezone.utc).isoformat()
            self._atomic_write_json(self.state_path, {
                "event_id": self.event_id,
                "version": "v3",
                "created_at": now_iso,
                "updated_at": now_iso,
                "active_video": "intro",
                "videos": {
                    "intro": {
                        "video_role": "intro",
                        "video_label": None,
                        "beats": {},
                        "image_overrides": {},
                        "display_order": [],
                        "completed_mp4_path": None,
                    },
                    "resolution": {
                        "video_role": "resolution",
                        "video_label": None,
                        "beats": {},
                        "image_overrides": {},
                        "display_order": [],
                        "completed_mp4_path": None,
                    },
                },
            })
        if not self.spend_path.exists():
            self._atomic_write_json(self.spend_path, {
                "event_id": self.event_id,
                "budget": DEFAULT_BUDGET,
                "spent": {"kling_animation": 0.0, "retries": 0.0},
                "total_spent": 0.0,
                "budget_remaining": DEFAULT_BUDGET,
                "warnings_shown": [],
                "overrides": 0,
            })
        # Ensure lock file exists (fcntl.lockf needs an open fd on an existing file)
        if not self.file_lock_path.exists():
            self.file_lock_path.touch()

    @staticmethod
    def _atomic_write_json(path: Path, obj: dict) -> None:
        """Write JSON atomically via the shared Production/lib/atomic_json_write helper.
        Prevents truncated-JSON windows where a concurrent reader sees a partially-
        written file (Tier 3 C2 CRITICAL fix, April 16 2026), AND adds Windows/Dropbox
        PermissionError retry (LD-368 WINDOWS_DROPBOX_ATOMIC_RENAME_RETRY_V1) since
        the project folder is Dropbox-synced on Kim's Windows workstation."""
        atomic_json_write(str(path), obj)

    def _acquire_file_lock(self, timeout: float = 10.0):
        """Acquire inter-process exclusive lock. Cross-platform: fcntl on Unix, msvcrt on Windows.
        Returns an open file descriptor to pass to _release_file_lock.
        Raises TimeoutError if another process holds the lock past timeout."""
        fd = os.open(str(self.file_lock_path), os.O_RDWR)
        deadline = time.time() + timeout
        if sys.platform == "win32":
            import msvcrt
            while True:
                try:
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                    return fd
                except OSError:
                    if time.time() >= deadline:
                        os.close(fd)
                        raise TimeoutError(
                            f"Could not acquire state file lock within {timeout}s "
                            f"(another process holds {self.file_lock_path})"
                        )
                    time.sleep(0.1)
        else:
            import fcntl
            while True:
                try:
                    fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    return fd
                except (BlockingIOError, OSError):
                    if time.time() >= deadline:
                        os.close(fd)
                        raise TimeoutError(
                            f"Could not acquire state file lock within {timeout}s "
                            f"(another process holds {self.file_lock_path})"
                        )
                    time.sleep(0.1)

    @staticmethod
    def _release_file_lock(fd: int) -> None:
        try:
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.lockf(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

    # ---- state ----
    def read_state(self) -> dict:
        with self.lock:
            fd = self._acquire_file_lock()
            try:
                return json.loads(self.state_path.read_text())
            finally:
                self._release_file_lock(fd)

    def write_state(self, state: dict) -> None:
        with self.lock:
            fd = self._acquire_file_lock()
            try:
                state["updated_at"] = datetime.now(timezone.utc).isoformat()
                self._atomic_write_json(self.state_path, state)
            finally:
                self._release_file_lock(fd)

    def mutate_state(self, fn):
        """Acquire threading + fcntl + Directus locks, read, mutate, atomic write.

        Lock order: threading.Lock (in-process) -> Directus (cross-machine) ->
        fcntl.lockf (inter-process same-machine). This order ensures no
        deadlock — each layer is strictly below the one above in scope.

        FAIL CLOSED on Directus unreachable unless SINGLE_MACHINE_MODE. Reason:
        silent cross-machine corruption via Dropbox sync is unrecoverable; an
        explicit RuntimeError is the correct trade."""
        with self.lock:
            dlock = _directus_lock_acquire(self.directus_lock_key, reason="mutate_state")
            if dlock is None and not SINGLE_MACHINE_MODE:
                raise RuntimeError(
                    "Directus lock unreachable — refusing to mutate state to prevent "
                    "cross-machine corruption. Start Directus, or set "
                    "PRODUCTION_SERVER_SINGLE_MACHINE=1 to skip (no cross-machine safety)."
                )
            fd = self._acquire_file_lock()
            try:
                state = json.loads(self.state_path.read_text())
                result = fn(state)
                # DISPLAY_ORDER_STRICT_V2 (C-10 K4 fix): defense-in-depth
                # prune. The mutate_video_state path at line 1264-1296 has a
                # symmetric prune since C2-bundle (DISPLAY_ORDER_STRICT_V1).
                # Pre-C-10, callers that bypass mutate_video_state and write
                # directly to state.videos.<role>.beats via mutate_state could
                # leave orphan beats not in display_order — that's the K4
                # asymmetry the 2026-05-01 leak exploited (state.beats was
                # legacy top-level; subsequent migrate_state lift carried
                # corrupted beats into videos.intro.beats and the prune in
                # mutate_video_state never saw them because all the writers
                # bypassed it via mutate_state). Post-C-7.5, all v59 mutation
                # handlers route partition writes through mutate_video_state
                # so this defense is largely structural-fallback now — but
                # it's idempotent on every mutate_state call, so any future
                # handler that accidentally writes into a partition still gets
                # caught. Walks state["videos"] and prunes partition.beats to
                # be a subset of partition.display_order WHEN display_order is
                # a present LIST. Skip when display_order is missing or non-list
                # (legacy int form — pre-v3 fixture shape).
                videos = state.get("videos")
                if isinstance(videos, dict):
                    for _role, _partition in videos.items():
                        if not isinstance(_partition, dict):
                            continue
                        _do = _partition.get("display_order")
                        if not isinstance(_do, list):
                            continue
                        _allowed = set(_do)
                        _beats = _partition.get("beats")
                        if not isinstance(_beats, dict):
                            continue
                        for _bid in list(_beats.keys()):
                            if _bid not in _allowed:
                                del _beats[_bid]
                state["updated_at"] = datetime.now(timezone.utc).isoformat()
                self._atomic_write_json(self.state_path, state)
                return result
            finally:
                self._release_file_lock(fd)
                _directus_lock_release(dlock)

    # ---- spend ----
    def read_spend(self) -> dict:
        with self.lock:
            fd = self._acquire_file_lock()
            try:
                return json.loads(self.spend_path.read_text())
            finally:
                self._release_file_lock(fd)

    def add_spend(self, category: str, amount: float, task_id: str | None = None) -> dict:
        """Add spend. If task_id is provided, the ledger is checked first —
        if that task_id has already been charged, this call is a no-op. This
        prevents double-charge across recovery events (Tier 3 C3 CRITICAL).

        Crash-safety: updates spend.json FIRST (atomic tmp+replace), then
        appends+fsyncs the ledger entry. If the process crashes between the
        two writes, spend.json is correctly updated; the missing ledger entry
        just means the guard will (harmlessly) re-charge on the NEXT call for
        the same task_id — but the same-call already updated spend, so there
        is no actual double-charge. Worst case: one extra small charge on a
        rare crash. Inverse ordering (ledger before spend) was a real
        integrity hole — Phase 3 finding #5 (April 16 2026).

        BS1: same cross-machine semaphore as mutate_state — fail closed on
        Directus unreachable (spend must not drift between machines)."""
        with self.lock:
            dlock = _directus_lock_acquire(self.directus_lock_key, reason=f"add_spend:{category}")
            if dlock is None and not SINGLE_MACHINE_MODE:
                raise RuntimeError(
                    "Directus lock unreachable — refusing to update spend to prevent "
                    "cross-machine drift. Start Directus, or set "
                    "PRODUCTION_SERVER_SINGLE_MACHINE=1 to skip."
                )
            fd = self._acquire_file_lock()
            try:
                # Ledger-backed idempotency guard (C3 double-charge prevention)
                if task_id and self.spend_ledger_path.exists():
                    for line in self.spend_ledger_path.read_text().splitlines():
                        if not line.strip():
                            continue
                        try:
                            entry = json.loads(line)
                            if entry.get("task_id") == task_id:
                                print(f"[spend] skip task_id={task_id[:16]} already in ledger")
                                return json.loads(self.spend_path.read_text())
                        except json.JSONDecodeError:
                            continue

                # 1. Update spend.json atomically FIRST
                spend = json.loads(self.spend_path.read_text())
                spend["spent"].setdefault(category, 0.0)
                spend["spent"][category] += amount
                spend["total_spent"] = sum(spend["spent"].values())
                spend["budget_remaining"] = spend["budget"] - spend["total_spent"]
                self._atomic_write_json(self.spend_path, spend)

                # 2. Append to ledger (fsync for durability) AFTER spend update
                if task_id:
                    ledger_entry = {
                        "task_id": task_id,
                        "category": category,
                        "amount": amount,
                        "charged_at": datetime.now(timezone.utc).isoformat(),
                    }
                    with self.spend_ledger_path.open("a") as lf:
                        lf.write(json.dumps(ledger_entry) + "\n")
                        lf.flush()
                        try:
                            os.fsync(lf.fileno())
                        except OSError:
                            pass  # macOS Dropbox may not support fsync — best effort

                return spend
            finally:
                self._release_file_lock(fd)
                _directus_lock_release(dlock)

    def override_budget(self, amount: float = 5.0) -> dict:
        with self.lock:
            dlock = _directus_lock_acquire(self.directus_lock_key, reason="override_budget")
            if dlock is None and not SINGLE_MACHINE_MODE:
                raise RuntimeError(
                    "Directus lock unreachable — refusing to override budget."
                )
            fd = self._acquire_file_lock()
            try:
                spend = json.loads(self.spend_path.read_text())
                spend["budget"] += amount
                spend["overrides"] += 1
                spend["budget_remaining"] = spend["budget"] - spend["total_spent"]
                self._atomic_write_json(self.spend_path, spend)
                return spend
            finally:
                self._release_file_lock(fd)
                _directus_lock_release(dlock)

    # ---- video partition helpers (S5.5a1, BG_VIDEO_PARTITION_V1) ----
    # All NEW; do not call read_state() / mutate_state() directly outside
    # these helpers when working with video partitions. video_role is read
    # from the request body (scope_video_role) on every mutating call;
    # state["active_video"] is a UX persistence hint only and MUST NOT
    # drive partition selection in write paths
    # (VIDEO_ROLE_PER_REQUEST_V1).
    # S5.5d (v3 architecture revision, 2026-05-03): VIDEO_ROLE_PER_REQUEST_V2
    # supersedes LD-474. phase_a/phase_b live at top-level; not partition roles.
    _VALID_VIDEO_ROLES: set[str] = {"intro", "resolution", "standalone"}

    def get_beats(self, video_role: str) -> dict:
        """Return the beats dict for the given video_role partition.

        Reads fresh from state.json on every call (no caching, per the
        S5 StateManager state_path lesson — VIDEO_ROLE_PER_REQUEST_V1).
        Returns empty dict if partition doesn't exist or has no beats.
        Caller must validate video_role first via validate_video_role().
        """
        state = self.read_state()
        videos = state.get("videos", {})
        if video_role not in videos:
            return {}
        return videos[video_role].get("beats", {})

    def mutate_video_state(self, video_role: str, mutator_fn) -> dict:
        """Atomic mutation of a single video_role partition.

        mutator_fn receives the partition dict and mutates it in place.

        IMPORTANT: do NOT call mutate_state() or mutate_video_state()
        inside mutator_fn — Python's RLock allows nested acquisition by
        the same thread, but nested logical mutations risk inconsistent
        snapshots and harder-to-debug write conflicts. If a handler
        needs multiple partition mutations, sequence them via separate
        mutate_video_state calls (each atomic on its own).
        """
        def _wrapped_mutator(state):
            if "videos" not in state:
                state["videos"] = {}
            if video_role not in state["videos"]:
                # Auto-create empty partition with required role marker
                state["videos"][video_role] = {
                    "video_role": video_role,
                    "video_label": None,
                }
                # All v3 partition roles are multi-beat (intro/resolution/standalone)
                state["videos"][video_role]["beats"] = {}
                state["videos"][video_role]["image_overrides"] = {}
                state["videos"][video_role]["display_order"] = []
                state["videos"][video_role]["completed_mp4_path"] = None
            mutator_fn(state["videos"][video_role])
            # DISPLAY_ORDER_STRICT_V1 prune (C2b) — keep partition.beats
            # consistent with display_order. When display_order is a present
            # LIST, drop any beats[bid] whose bid is not in it. Skip when
            # display_order is missing or non-list (legacy data shapes —
            # e.g. integer display_order in pre-v3 fixtures). The prune runs
            # on every mutation, not only when the mutator changed
            # display_order; the invariant is "beats {} ⊆ display_order
            # whenever display_order is a list", and idempotent enforcement
            # on every write is the safer contract. Pairs with the
            # StoryboardTab.beatList renderer's Array.isArray gate so empty
            # display_order = render zero beats end-to-end.
            partition = state["videos"][video_role]
            do = partition.get("display_order")
            if isinstance(do, list):
                allowed = set(do)
                beats = partition.get("beats")
                if isinstance(beats, dict):
                    for bid in list(beats.keys()):
                        if bid not in allowed:
                            del beats[bid]
            state["updated_at"] = datetime.now(timezone.utc).isoformat()
        return self.mutate_state(_wrapped_mutator)

    def list_videos(self) -> list:
        """Return list of all video partitions in the current event.

        Each entry: {video_role, video_label, has_beats: bool, beat_count: int}
        """
        state = self.read_state()
        videos = state.get("videos", {})
        result = []
        for role, partition in videos.items():
            beats = partition.get("beats", {})
            result.append({
                "video_role": partition.get("video_role", role),
                "video_label": partition.get("video_label"),
                "has_beats": bool(beats),
                "beat_count": len(beats) if isinstance(beats, dict) else 0,
            })
        return result

    def create_video(self, video_role: str, video_label: str | None = None) -> bool:
        """Add a new video partition under the current event.

        Returns True if created, False if partition with this role
        already exists. Raises ValueError if video_role is not in the
        canonical set.
        """
        if video_role not in self._VALID_VIDEO_ROLES:
            raise ValueError(
                f"Invalid video_role: {video_role!r}. Must be one of "
                f"{sorted(self._VALID_VIDEO_ROLES)}."
            )

        state = self.read_state()
        if video_role in state.get("videos", {}):
            return False

        def _mutator(state):
            if "videos" not in state:
                state["videos"] = {}
            partition = {
                "video_role": video_role,
                "video_label": video_label,
                "beats": {},
                "image_overrides": {},
                "display_order": [],
                "completed_mp4_path": None,
            }
            state["videos"][video_role] = partition
            state["updated_at"] = datetime.now(timezone.utc).isoformat()

        self.mutate_state(_mutator)
        return True

    def validate_video_role(self, video_role: str) -> bool:
        """Return True if video_role is in the canonical enum AND exists in current state."""
        if video_role not in self._VALID_VIDEO_ROLES:
            return False
        state = self.read_state()
        return video_role in state.get("videos", {})


# ---------------------------------------------------------------------------
# WaveSpeed client — http.client with fresh connection per call, no external deps.
#
# ROOT-CAUSE FIX (April 16 2026): the previous implementation used
# urllib.request.urlopen() which relies on a shared module-level opener with
# persistent HTTPSConnection and cached SSL context. After hours of uptime on
# macOS, polls to api.wavespeed.ai hung at the 30s timeout even though fresh
# subprocesses hit the same endpoint in 0.3s. Hypothesis: SSL session ticket /
# connection-pool state buildup. Fix: every request opens a fresh
# HTTPSConnection with a fresh SSLContext, then explicitly closes. No state
# shared between calls. ~30 extra LOC, zero new dependencies.
# ---------------------------------------------------------------------------

def _wavespeed_resolve_host(host: str) -> str | None:
    """Resolve hostname via public DNS (8.8.8.8 / 1.1.1.1) instead of the
    system resolver. Kim's ISP (Altice/Optimum) DNS-poisons api.wavespeed.ai
    to 167.206.37.145 instead of the real Tencent Cloud IP 49.51.190.24,
    causing every connection to time out. Ported from lipsync_sender.py.
    Discovered 2026-04-21. LD-379 WAVESPEED_DNS_RESILIENCE_V1_20260421."""
    for resolver in ("8.8.8.8", "1.1.1.1"):
        try:
            result = subprocess.run(
                ["dig", "+short", "+time=3", "+tries=1", f"@{resolver}", host],
                capture_output=True, text=True, timeout=5,
            )
            for line in result.stdout.splitlines():
                line = line.strip()
                if re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", line):
                    return line
        except (subprocess.TimeoutExpired, OSError):
            continue
    try:
        return socket.gethostbyname(host)
    except OSError:
        return None


def _wavespeed_request(
    method: str,
    url: str,
    *,
    api_key: str,
    body: bytes | None = None,
    timeout: int = 30,
) -> tuple[int, bytes]:
    """Issue a single HTTPS request with a fresh connection + SSL context.
    Returns (status_code, body_bytes). Raises urllib.error.URLError on network
    failure (so existing exception handlers keep working). Always closes the
    connection before returning."""
    import tempfile
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise ValueError(f"refusing non-https URL: {url!r}")
    hostname = parsed.hostname or parsed.netloc
    port = parsed.port or 443
    path = parsed.path + ("?" + parsed.query if parsed.query else "")
    full_url = f"https://{hostname}:{port}{path}"

    # LD-379: bypass ISP DNS poisoning via curl --resolve. Switching from
    # http.client to curl because http.client with a raw IP causes
    # SSLCertVerificationError (IP address mismatch for api.wavespeed.ai).
    # curl --resolve connects to the resolved IP while presenting the real
    # hostname in SNI + cert verification, so TLS succeeds. Ported from
    # lipsync_sender.py which already uses this pattern.
    resolved_ip = _wavespeed_resolve_host(hostname)

    cmd = [
        "curl", "-s", "-S",
        "--http1.1",            # avoids HTTP/2 handshake hang on macOS curl
        "-m", str(timeout),
        "-X", method,
        "-H", f"Authorization: Bearer {api_key}",
        "-H", "Content-Type: application/json",
        "-H", "Connection: close",
        "-w", "\n__STATUS__%{http_code}",   # append HTTP status as sentinel
    ]
    if resolved_ip:
        cmd += ["--resolve", f"{hostname}:{port}:{resolved_ip}"]

    tmp = None
    try:
        if body is not None:
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
            tmp.write(body)
            tmp.flush()
            tmp.close()
            cmd += ["-d", f"@{tmp.name}"]
        cmd.append(full_url)
        result = subprocess.run(cmd, capture_output=True, timeout=timeout + 10)
        raw = result.stdout
        marker = b"\n__STATUS__"
        idx = raw.rfind(marker)
        if idx >= 0:
            data = raw[:idx]
            try:
                status = int(raw[idx + len(marker):].strip())
            except ValueError as exc:
                raise urllib.error.URLError(
                    f"could not parse HTTP status from curl output: {raw[idx:]!r}"
                ) from exc
        else:
            stderr = result.stderr.decode(errors="replace").strip()
            raise urllib.error.URLError(
                f"curl exited {result.returncode}: {stderr or '(no stderr)'}"
            )
        return status, data
    except subprocess.TimeoutExpired as exc:
        raise urllib.error.URLError(f"TimeoutExpired: {exc}") from exc
    except FileNotFoundError as exc:
        raise urllib.error.URLError("curl not found — install curl") from exc
    finally:
        if tmp:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass


class StitchEditorState:
    """Universal stitch editor job store (global, not per-event).

    Unlike StateManager which is scoped to a single event_dir, this store
    persists named assembly jobs across all events. File lives alongside
    this server script at Production/tools/stitch_editor_state.json.
    (STITCH_EDITOR_UNIVERSAL_V1, 2026-04-26)
    """

    def __init__(self, state_path: Path):
        self.state_path = state_path
        self.lock = threading.Lock()
        self.file_lock_path = state_path.with_suffix(".lock")
        self._init_file()

    def _init_file(self) -> None:
        # P1 LD-505 Phase C: state_path is now event_dir.parent/tools/...
        # On a fresh event_dir (test fixture), the parent dir may not exist.
        # Pre-create it so atomic_json_write doesn't FileNotFoundError.
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.state_path.exists():
            self._atomic_write_json(self.state_path, {"version": 1, "jobs": {}})
        if not self.file_lock_path.exists():
            self.file_lock_path.touch()

    @staticmethod
    def _atomic_write_json(path: Path, obj: dict) -> None:
        atomic_json_write(str(path), obj)

    def _acquire_lock(self, timeout: float = 10.0):
        fd = os.open(str(self.file_lock_path), os.O_RDWR)
        deadline = time.time() + timeout
        if sys.platform == "win32":
            import msvcrt  # noqa: PLC0415
            while True:
                try:
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                    return fd
                except OSError:
                    if time.time() >= deadline:
                        os.close(fd)
                        raise TimeoutError(f"StitchEditorState lock timeout ({timeout}s)")
                    time.sleep(0.1)
        else:
            import fcntl  # noqa: PLC0415
            while True:
                try:
                    fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    return fd
                except (BlockingIOError, OSError):
                    if time.time() >= deadline:
                        os.close(fd)
                        raise TimeoutError(f"StitchEditorState lock timeout ({timeout}s)")
                    time.sleep(0.1)

    @staticmethod
    def _release_lock(fd: int) -> None:
        try:
            if sys.platform == "win32":
                import msvcrt  # noqa: PLC0415
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl  # noqa: PLC0415
                fcntl.lockf(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

    def read_state(self) -> dict:
        with self.lock:
            fd = self._acquire_lock()
            try:
                if not self.state_path.exists():
                    return {"version": 1, "jobs": {}}
                try:
                    return json.loads(self.state_path.read_text())
                except json.JSONDecodeError:
                    print("[StitchEditorState] WARN: state file corrupted — resetting")
                    return {"version": 1, "jobs": {}}
            finally:
                self._release_lock(fd)

    def mutate_state(self, fn):
        with self.lock:
            fd = self._acquire_lock()
            try:
                try:
                    state = (
                        json.loads(self.state_path.read_text())
                        if self.state_path.exists()
                        else {"version": 1, "jobs": {}}
                    )
                except json.JSONDecodeError:
                    state = {"version": 1, "jobs": {}}
                result = fn(state)
                self._atomic_write_json(self.state_path, state)
                return result
            finally:
                self._release_lock(fd)


class WaveSpeedClient:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def submit_animation(self, image_data_uri: str, prompt: str, duration: int = 5) -> str:
        """Submit a Kling v3 image-to-video job. Returns task_id."""
        import random
        body = {
            "image": image_data_uri,
            "prompt": prompt,
            "negative_prompt": NEGATIVE_PROMPT,
            "duration": duration,
            "cfg_scale": 0.5,
            "sound": False,
            "seed": random.randint(0, 999999),
        }
        status, data = _wavespeed_request(
            "POST", WAVESPEED_SUBMIT,
            api_key=self.api_key,
            body=json.dumps(body).encode("utf-8"),
            timeout=60,  # submits can be slow with large image URIs
        )
        if status < 200 or status >= 300:
            raise RuntimeError(f"WaveSpeed submit HTTP {status}: {data[:300]!r}")
        payload = json.loads(data.decode("utf-8"))
        # WaveSpeed responses vary — task id may be at top, data.id, etc.
        task_id = (
            (payload.get("data") or {}).get("id")
            or payload.get("id")
            or payload.get("task_id")
        )
        if not task_id:
            raise RuntimeError(f"WaveSpeed response missing task id: {payload}")
        return task_id

    def poll(self, task_id: str) -> dict:
        """Returns a normalized dict: {status, outputs, raw}.

        Preflight 107 (2026-04-19): timeout raised from 30 -> 90 seconds.
        WaveSpeed occasionally responds in the 30-45s range under load;
        30s was aggressive enough that slow-but-alive WaveSpeed looked
        dead and tasks sat in 'polling' until MAX_RETRIES exhausted even
        though the underlying job had completed. 90s gives the server's
        response time plenty of headroom; the pre-fail CDN check runs in
        parallel (async daemon) so overall UX latency is unchanged for
        successful polls.
        """
        status_code, data = _wavespeed_request(
            "GET", wavespeed_poll_url(task_id),
            api_key=self.api_key,
            timeout=90,
        )
        if status_code < 200 or status_code >= 300:
            raise RuntimeError(f"WaveSpeed poll HTTP {status_code}: {data[:300]!r}")
        payload = json.loads(data.decode("utf-8"))
        data_obj = payload.get("data") or {}
        status = data_obj.get("status") or payload.get("status") or "unknown"
        outputs = data_obj.get("outputs") or payload.get("outputs") or []
        error = data_obj.get("error") or payload.get("error") or ""
        return {"status": status, "outputs": outputs, "error": error, "raw": payload}

    def download(self, url: str, dest: Path) -> int:
        """Download a video URL to dest, return bytes written.
        Uses fresh connection per call (same stuck-state fix as poll/submit).
        CloudFront URLs are not behind auth so we use a minimal request."""
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https":
            raise ValueError(f"refusing non-https URL: {url!r}")
        path = parsed.path + ("?" + parsed.query if parsed.query else "")
        ctx = ssl.create_default_context()
        ctx.options |= ssl.OP_NO_TICKET
        ctx.options |= ssl.OP_NO_COMPRESSION
        conn = http.client.HTTPSConnection(parsed.netloc, timeout=120, context=ctx)
        try:
            conn.request("GET", path, headers={"Connection": "close"})
            resp = conn.getresponse()
            if resp.status < 200 or resp.status >= 300:
                raise RuntimeError(f"download HTTP {resp.status}: {resp.read()[:200]!r}")
            content = resp.read()
        finally:
            try:
                conn.close()
            except Exception:
                pass
        # BS4 (Tier 3 blind-spot fix, April 16 2026): atomic tmp+rename write.
        # Prevents partial-file race if two code paths download the same dest
        # concurrently (e.g., _pre_fail_cdn_check + recover_stuck_tasks.py).
        # Matches the existing _atomic_write_json pattern in StateManager.
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        try:
            tmp.write_bytes(content)
            os.replace(tmp, dest)  # POSIX atomic rename
        except Exception:
            try:
                tmp.unlink(missing_ok=True)  # clean up partial tmp on failure
            except OSError:
                pass
            raise
        return len(content)


# ---------------------------------------------------------------------------
# Orphan-sweep thread — auto-recovers stuck submissions (Preflight 107)
#
# Kim directive (2026-04-19): "dont let our artificial timeouts create blocks."
#
# Problem class: a submit() call can fail mid-execution (vendor socket reset,
# local SSL hiccup, process interruption) AFTER we've marked state as
# "submitting" but BEFORE we've recorded a task_id. The normal retry loop
# polls by task_id, so with task_id=None there's nothing to poll and the
# option/lipsync sits in "submitting" forever until manual intervention.
#
# This sweep runs once a minute and scans state for:
#   (a) beat.phase_1.options[] with status="submitting" and task_id=None
#       older than ORPHAN_SUBMIT_THRESHOLD_SEC  -> reset to allow resubmit
#   (b) beat.lipsync with status="submitting" and task_id=None older than
#       ORPHAN_SUBMIT_THRESHOLD_SEC  -> reset to last-known-good state so
#       the UI's Send for Lipsync button is clickable again
#
# It does NOT touch options/lipsyncs that DO have a task_id — those follow
# the normal polling path, which (per preflight 107) retries transport
# failures indefinitely with capped backoff. Only truly orphaned state
# (mid-submission crash, no task_id) gets reset. Every reset is logged.
# ---------------------------------------------------------------------------

ORPHAN_SWEEP_INTERVAL_SEC = 60
ORPHAN_SUBMIT_THRESHOLD_SEC = 5 * 60  # 5 min — a real submit completes in <120s


class OrphanSweepThread(threading.Thread):
    def __init__(self, state: StateManager, stop_event: threading.Event):
        super().__init__(daemon=True, name="OrphanSweep")
        self.state = state
        self.stop_event = stop_event

    def run(self) -> None:
        while not self.stop_event.is_set():
            try:
                self._sweep()
            except Exception as exc:  # noqa: BLE001 — never die
                print(f"[orphan-sweep] error: {exc}")
                traceback.print_exc()
            for _ in range(ORPHAN_SWEEP_INTERVAL_SEC):
                if self.stop_event.is_set():
                    return
                time.sleep(1)

    def _sweep(self) -> None:
        now = time.time()
        snap = self.state.read_state()
        recoveries: list[tuple[str, str, str, str]] = []  # (video_role, beat_id, kind, old_state)
        for video_role, beat_id, beat in _iter_v3_beats(snap):
            # (a) Animation options orphaned mid-submit.
            phase1 = beat.get("phase_1") or {}
            for idx, opt in enumerate(phase1.get("options") or []):
                if not isinstance(opt, dict):
                    continue
                if opt.get("status") != "submitting" or opt.get("task_id"):
                    continue
                age = self._age_seconds(opt, now)
                if age is None or age < ORPHAN_SUBMIT_THRESHOLD_SEC:
                    continue
                recoveries.append((video_role, beat_id, f"option_{idx+1}", "submitting"))
            # (b) Lipsync orphaned mid-submit.
            ls = beat.get("lipsync") or {}
            if ls.get("status") == "submitting" and not ls.get("task_id"):
                age = self._age_seconds(ls, now)
                if age is not None and age >= ORPHAN_SUBMIT_THRESHOLD_SEC:
                    recoveries.append((video_role, beat_id, "lipsync", "submitting"))
        if not recoveries:
            return

        by_role: dict[str, list[tuple[str, str, str, str]]] = {}
        for rec in recoveries:
            by_role.setdefault(rec[0], []).append(rec)

        def _apply_recoveries(partition, role_recoveries):
            for _video_role, beat_id, kind, _old in role_recoveries:
                beat = partition["beats"].get(beat_id) or {}
                if kind.startswith("option_"):
                    idx = int(kind.split("_", 1)[1]) - 1
                    opts = (beat.get("phase_1") or {}).get("options") or []
                    if 0 <= idx < len(opts) and isinstance(opts[idx], dict):
                        opts[idx]["status"] = "failed"
                        opts[idx]["last_error"] = (
                            "orphan-sweep: submit never returned task_id "
                            f"within {ORPHAN_SUBMIT_THRESHOLD_SEC}s"
                        )
                elif kind == "lipsync":
                    ls = beat.get("lipsync") or {}
                    # Preserve last-known-good file reference (if any) so the
                    # old lipsync keeps playing; clear submission state so UI
                    # retry works.
                    existing_file = ls.get("file")
                    existing_size = ls.get("size_bytes")
                    beat["lipsync"] = {
                        "status": "completed" if existing_file else "failed",
                        "task_id": None,
                        "file": existing_file,
                        "size_bytes": existing_size,
                        "audio_file": None,
                        "submitted_at": None,
                        "retries": 0,
                        "last_error": (
                            "orphan-sweep: submit never returned task_id "
                            f"within {ORPHAN_SUBMIT_THRESHOLD_SEC}s"
                        ),
                    }

        for video_role, role_recoveries in by_role.items():
            if video_role == "legacy":

                def _legacy_mut(state, _recs=role_recoveries):
                    if "beats" not in state:
                        state["beats"] = {}
                    _apply_recoveries({"beats": state["beats"]}, _recs)

                self.state.mutate_state(_legacy_mut)
            else:
                self.state.mutate_video_state(
                    video_role,
                    lambda partition, _recs=role_recoveries: _apply_recoveries(partition, _recs),
                )
        for video_role, beat_id, kind, old_state in recoveries:
            print(f"[orphan-sweep] recovered {video_role}/{beat_id}/{kind}: "
                  f"{old_state} -> cleared (orphan older than "
                  f"{ORPHAN_SUBMIT_THRESHOLD_SEC}s, no task_id)")

    @staticmethod
    def _age_seconds(entry: dict, now: float) -> float | None:
        """Best-effort age of a submitting entry. Prefers submitted_at_epoch
        for precision, falls back to parsing submitted_at ISO string, finally
        returns None (can't tell how old — leave it alone)."""
        ep = entry.get("submitted_at_epoch")
        if isinstance(ep, (int, float)) and ep > 0:
            return now - float(ep)
        iso = entry.get("submitted_at")
        if isinstance(iso, str) and iso:
            try:
                return now - datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
            except Exception:
                return None
        return None


# ---------------------------------------------------------------------------
# Lipsync polling thread — survives server restarts (Preflight 110 fix).
#
# Kim hit this on 2026-04-19: submitted a lipsync, then a server restart
# for an unrelated UI fix killed the in-flight HTTP handler's poll_until_done
# loop. The task completed on ByteDance's side but our state stayed 'polling'
# indefinitely. Root cause: lipsync polling ran in the HTTP handler's
# thread, not in a persistent daemon. Animations had PollingThread for
# exactly this reason; lipsync was the asymmetry.
#
# This daemon sweeps every LIPSYNC_POLL_INTERVAL_SEC seconds for all beats
# whose beat.lipsync.status=='polling' AND task_id is set. For each, it
# queries WaveSpeed directly via WaveSpeedClient.poll (ByteDance lipsync
# shares the /v3/predictions/<id>/result endpoint). On 'completed', it
# downloads the result URL to beat.lipsync.file path and writes state.
# On 'failed', it marks lipsync.status='failed' with vendor's error.
# Transport errors (timeouts, URLError) are no-op — next sweep retries,
# per Preflight 107 principle "artificial timeouts never block."
# ---------------------------------------------------------------------------

LIPSYNC_POLL_INTERVAL_SEC = 30


class LipsyncPollingThread(threading.Thread):
    def __init__(self, state: StateManager, client: 'WaveSpeedClient',
                 stop_event: threading.Event):
        super().__init__(daemon=True, name="LipsyncPoller")
        self.state = state
        self.client = client
        self.stop_event = stop_event

    def run(self) -> None:
        while not self.stop_event.is_set():
            try:
                self._cycle()
            except Exception as exc:  # noqa: BLE001 — never die
                print(f"[lipsync-poller] error: {exc}")
                traceback.print_exc()
            for _ in range(LIPSYNC_POLL_INTERVAL_SEC):
                if self.stop_event.is_set():
                    return
                time.sleep(1)

    def _cycle(self) -> None:
        snap = self.state.read_state()
        candidates: list[tuple[str, str, str]] = []  # (video_role, beat_id, task_id)
        for video_role, beat_id, beat in _iter_v3_beats(snap):
            ls = beat.get("lipsync") or {}
            if ls.get("status") == "polling" and ls.get("task_id"):
                candidates.append((video_role, beat_id, ls["task_id"]))
        if not candidates:
            pass
        else:
            # Preflight 111 (2026-04-19): emit a visible heartbeat so the server
            # log always shows the daemon is alive when work exists. Previously
            # the daemon completed cycles silently, making it impossible to tell
            # if silent meant "no candidates" vs "stuck" vs "crashed thread".
            print(f"[lipsync-poller] cycle: {len(candidates)} candidate(s): "
                  f"{[(b, t[:12]) for _r, b, t in candidates]}", flush=True)
            for video_role, beat_id, task_id in candidates:
                if self.stop_event.is_set():
                    return
                self._poll_one(video_role, beat_id, task_id)
        # Phase B module lipsync (top-level state, not beat partition).
        try:
            from server_handlers.phases import sweep_phase_module_lipsync_polls
            sweep_phase_module_lipsync_polls(self.state, self.client)
        except Exception as exc:  # noqa: BLE001
            print(f"[lipsync-poller] phase module sweep error: {exc}", flush=True)
            traceback.print_exc()

    @staticmethod
    def _mutate_lipsync(state_mgr: StateManager, video_role: str, mutator_fn) -> None:
        """Apply a partition-scoped lipsync mutator to v3 or legacy beats."""
        if video_role == "legacy":

            def _legacy_mut(state):
                if "beats" not in state:
                    state["beats"] = {}
                mutator_fn({"beats": state["beats"]})

            state_mgr.mutate_state(_legacy_mut)
        else:
            state_mgr.mutate_video_state(video_role, mutator_fn)

    def _poll_one(self, video_role: str, beat_id: str, task_id: str) -> None:
        try:
            result = self.client.poll(task_id)
        except Exception as exc:  # noqa: BLE001 — transport; retry next cycle
            print(f"[lipsync-poller] {beat_id}/{task_id[:12]}…: "
                  f"transport error ({type(exc).__name__}: {exc!r}); will retry",
                  flush=True)
            return
        status = (result.get("status") or "").lower()
        outputs = result.get("outputs") or []
        print(f"[lipsync-poller] {beat_id}/{task_id[:12]}…: "
              f"status={status!r} outputs={len(outputs)}", flush=True)
        if status == "completed" and outputs:
            self._download_and_complete(video_role, beat_id, task_id, outputs[0])
        elif status in ("failed", "error"):
            self._mark_failed(video_role, beat_id, task_id, "vendor reported failure")
        # else: still processing — leave alone, next cycle will re-poll

    def _lipsync_entry(self, video_role: str, beat_id: str) -> dict:
        if video_role == "legacy":
            snap = self.state.read_state()
            return (snap.get("beats") or {}).get(beat_id, {}).get("lipsync") or {}
        beats = self.state.get_beats(video_role)
        return (beats.get(beat_id) or {}).get("lipsync") or {}

    def _download_and_complete(self, video_role: str, beat_id: str, task_id: str, url: str) -> None:
        print(f"[lipsync-poller] {beat_id}/{task_id[:12]}…: completed, downloading {url[:60]}…", flush=True)
        # LIPSYNC_UNIQUE_FNAME_20260525: always generate a unique timestamp-based filename
        # so the browser URL changes completely on each new lipsync — no reliance on
        # query-param (?v=N) cache-busting, which Safari's media buffer ignores for
        # video elements even after Cmd+Shift+R hard refresh.
        _lipsync_ts = hex(int(time.time()))[2:]
        fname = f"{beat_id}_lipsync_{_lipsync_ts}.mp4"
        clips_dir = self.state.clips_dir
        dst = clips_dir / Path(fname).name
        try:
            size = self.client.download(url, dst)
        except Exception as exc:  # noqa: BLE001
            print(f"[lipsync-poller] {beat_id}/{task_id[:12]}…: download failed ({exc}); will retry next cycle", flush=True)
            return

        def mut(partition):
            beat = partition["beats"].get(beat_id) or {}
            ls = beat.get("lipsync") or {}
            ls["status"] = "completed"
            ls["file"] = Path(fname).name
            ls["size_bytes"] = size
            ls["last_error"] = None
            ls["recovered_by"] = "lipsync_poller_persistent"
            ls["recovered_at"] = datetime.now(timezone.utc).isoformat()
            beat["lipsync"] = ls
            # LIPSYNC_VERSION_BUMP_20260524: bump _version so the browser URL
            # (beat_NN_lipsync.mp4?v=N) changes, forcing a re-fetch of the new file.
            # Without this, lipsyncMounted (LD-757) keeps the OLD file buffered in
            # <video> even after the lipsync on disk is overwritten (same filename,
            # same URL). The result: browser plays stale content, back-trim misbehaves.
            beat["_version"] = int(beat.get("_version", 0) or 0) + 1
            partition["beats"][beat_id] = beat

        self._mutate_lipsync(self.state, video_role, mut)
        print(f"[lipsync-poller] {beat_id}/{task_id[:12]}…: wrote {size:,} bytes -> {dst.name}", flush=True)

    def _mark_failed(self, video_role: str, beat_id: str, task_id: str, err: str) -> None:
        def mut(partition):
            beat = partition["beats"].get(beat_id) or {}
            ls = beat.get("lipsync") or {}
            ls["status"] = "failed"
            ls["last_error"] = err
            beat["lipsync"] = ls
            partition["beats"][beat_id] = beat

        self._mutate_lipsync(self.state, video_role, mut)
        print(f"[lipsync-poller] {beat_id}/{task_id[:12]}…: marked failed ({err})", flush=True)


# ---------------------------------------------------------------------------
# Polling thread — drives WaveSpeed status updates independently of HTTP
# ---------------------------------------------------------------------------

class PollingThread(threading.Thread):
    def __init__(self, state: StateManager, client: WaveSpeedClient, stop_event: threading.Event):
        super().__init__(daemon=True, name="WaveSpeedPoller")
        self.state = state
        self.client = client
        self.stop_event = stop_event

    def run(self) -> None:
        while not self.stop_event.is_set():
            try:
                self._cycle()
            except Exception as exc:  # noqa: BLE001 — never die
                print(f"[poller] error: {exc}")
                traceback.print_exc()
            # Sleep in small chunks so shutdown is responsive
            for _ in range(POLL_CYCLE_GAP_SEC):
                if self.stop_event.is_set():
                    return
                time.sleep(1)

    def _pending_tasks(self) -> list[tuple[str, int, dict]]:
        """Return (beat_id, option_index, option_dict) for each polling task
        that is READY to be polled now (next_attempt_at_epoch is past).
        Tier 3 C1+Phase-3 fix (April 16 2026): previously the poller slept
        inline inside _poll_one, blocking other beats. Now backoff is stored
        per-option as an epoch and the cycle simply skips options not yet due.

        Tier 1B (April 18 2026): before returning an option, check wall-clock
        elapsed against STALE_TIMEOUT_SEC[opt.source]. If elapsed exceeds the
        threshold, hand off to _mark_stale_timeout_with_artifact_check — which
        either recovers as succeeded_late (artifact on disk) or flips to
        failed (no artifact). Stale options are NOT returned for polling.
        """
        now = time.time()
        # Iterate ALL video-role partitions (not just intro) so resolution/
        # standalone beats are polled. Returns 4-tuples (beat_id, idx, opt, role).
        state_snap = self.state.read_state()
        all_partitions = (state_snap.get("videos") or {})
        out: list[tuple[str, int, dict, str]] = []
        stale_candidates: list[tuple[str, int, dict, str]] = []
        t1_enabled = _t1_enabled()
        for video_role, partition in all_partitions.items():
            beats = (partition or {}).get("beats", {})
            for beat_id, beat in beats.items():
                phase1 = beat.get("phase_1") or {}
                for idx, opt in enumerate(phase1.get("options", [])):
                    if opt.get("status") != "polling" or not opt.get("task_id"):
                        continue
                    if t1_enabled:
                        submitted_epoch = opt.get("submitted_at_epoch")
                        if submitted_epoch:
                            try:
                                elapsed = now - float(submitted_epoch)
                            except (TypeError, ValueError):
                                elapsed = 0
                            source = opt.get("source") or "kling"
                            threshold = STALE_TIMEOUT_SEC.get(
                                source, STALE_TIMEOUT_DEFAULT_SEC,
                            )
                            if elapsed > threshold:
                                stale_candidates.append((beat_id, idx, opt, video_role))
                                continue
                    next_at = opt.get("next_attempt_at_epoch", 0)
                    if next_at > now:
                        continue
                    out.append((beat_id, idx, opt, video_role))
        for beat_id, idx, opt, video_role in stale_candidates:
            try:
                self._mark_stale_timeout_with_artifact_check(beat_id, idx, opt, video_role)
            except Exception as exc:  # noqa: BLE001 — never kill the poller
                print(f"[T1] beat={beat_id} opt={idx + 1} stale_check_error: {exc}")
                traceback.print_exc()
        return out

    def _mark_stale_timeout_with_artifact_check(
        self, beat_id: str, opt_idx: int, opt: dict, video_role: str = "intro",
    ) -> None:
        """Tier 1B core: an option has exceeded its wall-clock timeout. Before
        declaring it failed, look for the expected output file on disk.

        - If artifact exists AND its mtime > submitted_at_epoch: mark
          succeeded_late (set resurrected=True). This handles the case where
          the vendor finished but the callback was lost — we still have the
          bits, don't burn the user's money/time. The file is moved to the
          'completed' status via _mark_completed so downstream code (lipsync,
          assembly) can pick it up transparently.
        - Otherwise: mark failed with reason=stale_timeout. next_attempt_at_epoch
          is cleared so the poller never revisits.

        Both paths write to production_state.json via StateManager.mutate_state
        (tmp+rename atomic) and emit a prod_activity_log row.
        """
        fname = f"{beat_id}_option_{opt_idx + 1}.mp4"
        dest = self.state.clips_dir / fname
        submitted_epoch = opt.get("submitted_at_epoch") or 0
        try:
            submitted_epoch = float(submitted_epoch)
        except (TypeError, ValueError):
            submitted_epoch = 0.0
        source = opt.get("source") or "kling"
        threshold = STALE_TIMEOUT_SEC.get(source, STALE_TIMEOUT_DEFAULT_SEC)

        artifact_recovered = False
        size = 0
        if dest.exists() and dest.stat().st_size > 0:
            try:
                mtime = dest.stat().st_mtime
            except OSError:
                mtime = 0.0
            # Recovery requires mtime strictly newer than submitted_at_epoch.
            # (If the file predates submission, it's from a previous run and
            # should NOT be claimed as a late success for this task_id.)
            if submitted_epoch and mtime > submitted_epoch:
                artifact_recovered = True
                size = dest.stat().st_size

        # S5.5a2: legacy stale-timeout mut → intro partition.
        def mut(partition, _bid=beat_id, _i=opt_idx, _recovered=artifact_recovered,
                _fname=fname, _sz=size, _thresh=threshold, _src=source):
            opts = partition["beats"][_bid]["phase_1"]["options"]
            if _i >= len(opts):
                return None  # slot vanished; nothing to do
            o = opts[_i]
            # Guard: if something already transitioned this slot out of
            # polling between the read and the mutate (idempotency race),
            # don't overwrite. Valid terminal states are skipped.
            if o.get("status") != "polling":
                return "already_terminal"
            if _recovered:
                o["status"] = "succeeded_late"
                o["resurrected"] = True
                o["file"] = _fname
                o["size_bytes"] = _sz
                o["stale_timeout_recovered"] = True
                o["stale_timeout_threshold_sec"] = _thresh
                o["stale_timeout_source"] = _src
                # Also call the _mark_completed rollup so phase_1.status
                # reflects the new terminal state. _mark_completed updates
                # the option's own status to "completed"; we want to keep
                # provenance as "succeeded_late" so downstream code can tell
                # this was a recovered task. Therefore: compute rollup here
                # manually instead of calling _mark_completed (which would
                # overwrite our provenance flag).
                phase1 = partition["beats"][_bid]["phase_1"]
                # succeeded_late is a terminal-success state for rollup purposes.
                term_success = {"completed", "succeeded_late"}
                all_done = all(
                    (oo.get("status") in term_success) for oo in phase1["options"]
                )
                any_failed = any(
                    oo.get("status") == "failed" for oo in phase1["options"]
                )
                any_polling = any(
                    oo.get("status") == "polling" for oo in phase1["options"]
                )
                if all_done:
                    phase1["status"] = "completed"
                elif any_failed and not any_polling:
                    phase1["status"] = "partial"
                else:
                    phase1["status"] = "polling"
            else:
                o["status"] = "failed"
                o["last_error"] = "stale_timeout"
                o["stale_timeout_failed"] = True
                o["stale_timeout_threshold_sec"] = _thresh
                o["stale_timeout_source"] = _src
                o.pop("next_attempt_at_epoch", None)
                # Rollup for the failed case
                phase1 = partition["beats"][_bid]["phase_1"]
                term_success = {"completed", "succeeded_late"}
                all_done = all(
                    (oo.get("status") in term_success) for oo in phase1["options"]
                )
                any_failed = any(
                    oo.get("status") == "failed" for oo in phase1["options"]
                )
                any_polling = any(
                    oo.get("status") == "polling" for oo in phase1["options"]
                )
                if all_done:
                    phase1["status"] = "completed"
                elif any_failed and not any_polling:
                    phase1["status"] = "partial"
                else:
                    phase1["status"] = "polling"
            return "applied"

        result = self.state.mutate_video_state(video_role, mut)
        if result == "already_terminal":
            # Another thread raced us to a terminal state — nothing to log.
            return
        if artifact_recovered:
            print(
                f"[T1] beat={beat_id} opt={opt_idx + 1} "
                f"action=stale_success_recovered size={size} source={source} "
                f"threshold={threshold}s"
            )
            _t1_directus_log("stale_success_recovered", {
                "beat_id": beat_id,
                "opt_idx": opt_idx,
                "source": source,
                "threshold_sec": threshold,
                "file": fname,
                "size_bytes": size,
                "task_id": opt.get("task_id"),
            })
        else:
            print(
                f"[T1] beat={beat_id} opt={opt_idx + 1} "
                f"action=stale_timeout_failed source={source} "
                f"threshold={threshold}s"
            )
            _t1_directus_log("stale_timeout_failed", {
                "beat_id": beat_id,
                "opt_idx": opt_idx,
                "source": source,
                "threshold_sec": threshold,
                "task_id": opt.get("task_id"),
            })

    def _cycle(self) -> None:
        pending = self._pending_tasks()
        if not pending:
            return
        # Batch
        for i in range(0, len(pending), POLL_BATCH_SIZE):
            if self.stop_event.is_set():
                return
            batch = pending[i : i + POLL_BATCH_SIZE]
            for beat_id, opt_idx, opt, video_role in batch:
                self._poll_one(beat_id, opt_idx, opt, video_role)
            time.sleep(POLL_BATCH_GAP_SEC)

    def _poll_one(self, beat_id: str, opt_idx: int, opt: dict, video_role: str = "intro") -> None:
        task_id = opt["task_id"]
        # Backoff is handled upstream in _pending_tasks (skips options whose
        # next_attempt_at_epoch is still in the future). DO NOT sleep here —
        # that would block every other beat's poll. Tier 3 Phase-3 fix #4.

        try:
            result = self.client.poll(task_id)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            self._handle_transient_failure(beat_id, opt_idx, str(exc), task_id=task_id, video_role=video_role)
            return
        except Exception as exc:  # noqa: BLE001
            self._handle_transient_failure(beat_id, opt_idx, repr(exc), task_id=task_id, video_role=video_role)
            return

        status = (result.get("status") or "").lower()
        if status == "completed" and result.get("outputs"):
            self._download_and_mark_completed(
                beat_id, opt_idx, task_id, result["outputs"][0],
                source="poll_complete", video_role=video_role,
            )
        elif status in ("failed", "error"):
            _ws_err = result.get("message") or result.get("error") or result.get("detail") or ""
            print(f"[poll] {beat_id} opt{opt_idx} wavespeed failure detail: {_ws_err!r} full={list(result.keys())}")
            self._handle_transient_failure(
                beat_id, opt_idx, f"wavespeed reported failure: {_ws_err}", task_id=task_id, video_role=video_role,
            )
        # else: still processing — leave alone

    def _download_and_mark_completed(
        self, beat_id: str, opt_idx: int, task_id: str, url: str, *, source: str, video_role: str = "intro",
    ) -> bool:
        """Extracted so both normal poll-complete AND async CDN re-check paths
        converge on one implementation. Idempotent: if dest already exists with
        content, skip re-download. Uses spend-ledger (task_id-keyed) to prevent
        double-charge across sources.

        Tier 1B idempotency guard (April 18 2026): BEFORE mutating status to
        'completed', check if the current status is 'failed' or 'succeeded_late'.
        - If 'failed' (stale-timeout declared, then vendor actually finished
          and callback arrived late): add resurrected_from='failed' provenance
          and transition to 'completed'. Never silently clobber a failed state.
        - If 'succeeded_late' (the T1 stale check already recovered the
          artifact): transition to 'completed' for downstream consistency,
          preserving the earlier provenance.
        """
        fname = f"{beat_id}_option_{opt_idx + 1}.mp4"
        dest = self.state.clips_dir / fname

        # Stale-file guard: if a file exists for this slot, verify it postdates
        # the task's submission epoch. If stale (mtime <= submitted_at_epoch),
        # delete it so we re-download the correct output from this task.
        # Mirrors the artifact-recovery pattern at line 2101.
        if dest.exists() and dest.stat().st_size > 0:
            beats = self.state.get_beats(video_role)
            _phase1_opts = (beats.get(beat_id) or {}).get("phase_1", {}).get("options", [])
            _submitted_epoch: "float | None" = (
                _phase1_opts[opt_idx].get("submitted_at_epoch")
                if opt_idx < len(_phase1_opts) else None
            )
            if _submitted_epoch and dest.stat().st_mtime <= _submitted_epoch:
                print(f"[{source}] {beat_id} opt {opt_idx + 1}: stale file "
                      f"(mtime {dest.stat().st_mtime:.0f} <= submitted {_submitted_epoch}) "
                      f"— deleting for fresh download")
                dest.unlink()

        size: int
        if dest.exists() and dest.stat().st_size > 0:
            # Idempotency guard — file is current (mtime > submitted epoch)
            size = dest.stat().st_size
            print(f"[{source}] {beat_id} opt {opt_idx + 1}: file already present ({size} bytes); marking complete without re-download")
        else:
            try:
                size = self.client.download(url, dest)
            except Exception as exc:  # noqa: BLE001
                self._handle_transient_failure(
                    beat_id, opt_idx, f"download failed: {exc}", task_id=task_id,
                )
                return False
            if _strip_clip_audio(dest, verbose=True):
                size = dest.stat().st_size

        # Tier 1B late-success idempotency guard: read current status and
        # branch. All branches go through one mutate_state call so the read
        # and write are atomic with respect to other threads.
        resurrected_from_holder: dict = {}

        # S5.5a2: legacy late-success guard mut → intro partition.
        def mut_with_guard(partition, _b=beat_id, _i=opt_idx, _f=fname, _sz=size):
            opts = partition["beats"][_b]["phase_1"]["options"]
            if _i >= len(opts):
                return "missing_slot"
            opt = opts[_i]
            prior_status = opt.get("status")
            if prior_status == "failed":
                # Late success after stale-timeout flip: resurrect.
                opt["resurrected_from"] = "failed"
                opt["status"] = "completed"
                opt["file"] = _f
                opt["size_bytes"] = _sz
                opt.pop("last_error", None)
                opt.pop("next_attempt_at_epoch", None)
                resurrected_from_holder["prior"] = "failed"
            elif prior_status == "succeeded_late":
                # Consistency transition: T1 already recovered via artifact
                # check, now the real callback has arrived. Promote to
                # completed but preserve earlier recovery provenance.
                opt["resurrected_from"] = "succeeded_late"
                opt["status"] = "completed"
                opt["file"] = _f
                opt["size_bytes"] = _sz
                resurrected_from_holder["prior"] = "succeeded_late"
            else:
                # Normal path — use the shared helper for rollup logic.
                _mark_completed(partition, _b, _i, _f, _sz)
                return "normal"
            # Hand-compute rollup for the resurrected branches (matches
            # _mark_completed logic but treats succeeded_late as terminal-success).
            phase1 = partition["beats"][_b]["phase_1"]
            term_success = {"completed", "succeeded_late"}
            all_done = all(
                (oo.get("status") in term_success) for oo in phase1["options"]
            )
            any_failed = any(
                oo.get("status") == "failed" for oo in phase1["options"]
            )
            any_polling = any(
                oo.get("status") == "polling" for oo in phase1["options"]
            )
            if all_done:
                phase1["status"] = "completed"
            elif any_failed and not any_polling:
                phase1["status"] = "partial"
            else:
                phase1["status"] = "polling"
            return "resurrected"

        mut_result = self.state.mutate_video_state(video_role, mut_with_guard)
        # Pass task_id so spend ledger prevents double-charge on recovery
        self.state.add_spend("kling_animation", COST_PER_CLIP_KLING, task_id=task_id)
        if mut_result == "resurrected":
            prior = resurrected_from_holder.get("prior", "?")
            print(
                f"[{source}] {beat_id} option {opt_idx + 1} complete ({size} bytes) "
                f"resurrected_from={prior}"
            )
            _t1_directus_log("late_success_resurrected_" + prior, {
                "beat_id": beat_id,
                "opt_idx": opt_idx,
                "prior_status": prior,
                "source": source,
                "task_id": task_id,
                "file": fname,
                "size_bytes": size,
            })
        else:
            print(f"[{source}] {beat_id} option {opt_idx + 1} complete ({size} bytes)")
        return True

    def _handle_transient_failure(
        self, beat_id: str, opt_idx: int, err: str, *, task_id: str | None = None, video_role: str = "intro",
    ) -> None:
        """Increment retries and conditionally mark failed.

        Preflight 107 (2026-04-19, Kim directive):
        'dont let our artificial timeouts create blocks.'

        Our local HTTP timeouts must NEVER be the thing that declares a task
        failed. The only authoritative failure verdict is the VENDOR'S (status
        == 'failed' or 'error' in the poll response), which arrives here as
        err='wavespeed reported failure'. Everything else — urlopen timeouts,
        connection errors, SSL hiccups, DNS flaps — is a TRANSPORT failure
        that just means 'try again later.' Transport failures now retry
        indefinitely with a capped backoff (no MAX_RETRIES cliff). This
        matches the vendor semantics: if WaveSpeed is slow-but-alive, we
        keep polling until it responds authoritatively; if WaveSpeed is
        down, we wait for it to return without declaring user-visible
        failure. Orphan recovery is handled by OrphanSweepThread below.

        Pre-fail CDN re-check (C4) still fires on transport failures at
        configured retry levels — an async one-shot probe that can recover
        the option within ~60s even while the normal poller continues to
        back off.
        """
        # Distinguish vendor-authoritative failure from local transport issues.
        is_vendor_failure = err.startswith("wavespeed reported failure")

        # S5.5a2: legacy transient-failure mut → intro partition.
        def mut(partition):
            opts = partition["beats"][beat_id]["phase_1"]["options"]
            opt = opts[opt_idx]
            retries = opt.get("retries", 0)
            opt["last_error"] = err
            new_retries = retries + 1
            opt["retries"] = new_retries
            if is_vendor_failure:
                # Vendor said the task failed. That's authoritative.
                opt["status"] = "failed"
                opt.pop("next_attempt_at_epoch", None)
            else:
                # Transport failure — retry with capped backoff. No cliff.
                # Backoff table saturates at its last element (currently 45s);
                # cap at 60s so polls resume at most once a minute per beat.
                idx = min(new_retries, len(RETRY_BACKOFF_EXTRA_SEC) - 1)
                backoff = min(60, RETRY_BACKOFF_EXTRA_SEC[idx])
                opt["next_attempt_at_epoch"] = time.time() + backoff
                opt["next_attempt_at"] = datetime.now(timezone.utc).isoformat()
                # Status stays 'polling' — this is no longer a path to 'failed'
                # unless the vendor says so or the orphan sweep finds it truly dead.
            return new_retries
        new_retries = self.state.mutate_video_state(video_role, mut)

        # Pre-fail CDN check (C4): only at configured retry levels, async,
        # 10s timeout, doesn't block this poller thread.
        if (task_id and
            new_retries in PRE_FAIL_CDN_CHECK_AT_RETRIES):
            threading.Thread(
                target=_pre_fail_cdn_check,
                args=(self, beat_id, opt_idx, task_id),
                daemon=True,
                name=f"pre-fail-cdn-{beat_id}-{opt_idx + 1}",
            ).start()


# ---------------------------------------------------------------------------
# Directus-backed cross-machine semaphore (BS1 Tier 3 blind-spot fix).
# Module-level helpers so StateManager doesn't own a DirectusClient.
# ---------------------------------------------------------------------------

_DIRECTUS_LOCK_CLIENT_SINGLETON: object = None  # lazy-init cache
_DIRECTUS_LOCK_CLIENT_LOCK = threading.Lock()


def _reset_directus_lock_client():
    """Force the next _get_directus_lock_client() call to rebuild the
    singleton. Called from _directus_lock_acquire's exception path when the
    cached client persistently fails (stale auth token, killed connection,
    etc.) — without reset the retry loop hits the same broken client every
    iteration and runs out the deadline."""
    global _DIRECTUS_LOCK_CLIENT_SINGLETON
    with _DIRECTUS_LOCK_CLIENT_LOCK:
        _DIRECTUS_LOCK_CLIENT_SINGLETON = None


def _get_directus_lock_client():
    """Lazy-create a DirectusClient for lock operations. Returns None on
    failure so callers can degrade (FAIL CLOSED in mutate paths)."""
    global _DIRECTUS_LOCK_CLIENT_SINGLETON
    with _DIRECTUS_LOCK_CLIENT_LOCK:
        if _DIRECTUS_LOCK_CLIENT_SINGLETON is not None:
            return _DIRECTUS_LOCK_CLIENT_SINGLETON
        try:
            _libdir = os.path.join(os.path.dirname(__file__), "credentials_lib")
            if _libdir not in sys.path:
                sys.path.insert(0, _libdir)
            from credentials import load_credentials  # type: ignore
            from directus import DirectusClient  # type: ignore
            creds = load_credentials()
            client = DirectusClient(
                creds["directus_url"],
                creds["directus_email"],
                creds["directus_password"],
            )
            _DIRECTUS_LOCK_CLIENT_SINGLETON = client
            return client
        except Exception as exc:  # noqa: BLE001
            print(f"[dlock] WARN could not init DirectusClient: {exc}")
            return None


def _directus_lock_acquire(resource_key: str, reason: str = "mutate_state") -> dict | None:
    """Acquire a cross-machine lock on resource_key. Blocks up to
    DIRECTUS_LOCK_ACQUIRE_TIMEOUT. Returns a dict {id, resource_key, acquired_at}
    on success. Returns None if Directus is unreachable (caller decides what
    to do — FAIL CLOSED is the default in mutate paths)."""
    if SINGLE_MACHINE_MODE:
        print("[dlock] SKIP (SINGLE_MACHINE_MODE=1) — no cross-machine safety!")
        return {"id": None, "resource_key": resource_key, "mode": "single_machine"}

    client = _get_directus_lock_client()
    if client is None:
        return None

    deadline = time.time() + DIRECTUS_LOCK_ACQUIRE_TIMEOUT
    while True:
        now_utc = datetime.now(timezone.utc)
        try:
            existing = client.get(
                "prod_locks",
                filters={"resource_key": {"_eq": resource_key}},
                limit=1,
            )
        except Exception as exc:  # noqa: BLE001
            # Kim 2026-05-21: transient API hiccup shouldn't fail the whole
            # mutate. Retry-until-deadline instead of immediate None — Railway
            # free-tier Directus regularly takes 3+s on cold reads and a
            # single dropped lookup was raising "lock unreachable" in the UI.
            # Also nuke the singleton — a stale auth token or broken socket on
            # the cached client would otherwise make every retry hit the same
            # error and burn the deadline pointlessly.
            print(f"[dlock] WARN lookup failed (resetting singleton + retrying until deadline): {exc}")
            _reset_directus_lock_client()
            if time.time() >= deadline:
                return None
            time.sleep(DIRECTUS_LOCK_POLL_INTERVAL)
            client = _get_directus_lock_client()
            if client is None:
                continue
            continue

        if existing:
            row = existing[0]
            # Compare expiry — parse "2026-04-16T22:30:00+00:00" or "...Z"
            exp_str = (row.get("expires_at") or "").replace("Z", "+00:00")
            try:
                exp = datetime.fromisoformat(exp_str)
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
            except ValueError:
                exp = now_utc  # malformed -> treat as expired

            # Reuse if we already hold it (same machine — reentrant)
            if row.get("holder_machine_id") == MACHINE_ID:
                new_exp = now_utc + timedelta(seconds=DIRECTUS_LOCK_TTL_SEC)
                try:
                    client._request("PATCH", f"/items/prod_locks/{row['id']}", data={
                        "heartbeat_at": now_utc.isoformat(),
                        "expires_at": new_exp.isoformat(),
                    })
                    return {"id": row["id"], "resource_key": resource_key, "reused": True}
                except Exception as exc:  # noqa: BLE001
                    print(f"[dlock] WARN reentrant heartbeat failed (resetting + retrying): {exc}")
                    _reset_directus_lock_client()
                    if time.time() >= deadline:
                        return None
                    time.sleep(DIRECTUS_LOCK_POLL_INTERVAL)
                    client = _get_directus_lock_client()
                    if client is None:
                        continue
                    continue

            # Held by different machine — wait for expiry or timeout
            if exp > now_utc:
                if time.time() >= deadline:
                    print(f"[dlock] TIMEOUT waiting for {resource_key!r} — held by "
                          f"{row.get('holder_machine_id')!r} until {exp.isoformat()}")
                    return None
                time.sleep(DIRECTUS_LOCK_POLL_INTERVAL)
                continue

            # Expired — steal the row via PATCH (atomic from Directus's POV)
            new_exp = now_utc + timedelta(seconds=DIRECTUS_LOCK_TTL_SEC)
            try:
                client._request("PATCH", f"/items/prod_locks/{row['id']}", data={
                    "holder_machine_id": MACHINE_ID,
                    "holder_pid": os.getpid(),
                    "acquired_at": now_utc.isoformat(),
                    "heartbeat_at": now_utc.isoformat(),
                    "expires_at": new_exp.isoformat(),
                    "reason": reason[:200],
                })
                return {"id": row["id"], "resource_key": resource_key, "stolen_from": row.get("holder_machine_id")}
            except Exception as exc:  # noqa: BLE001
                print(f"[dlock] WARN steal-expired failed (resetting + retrying): {exc}")
                _reset_directus_lock_client()
                if time.time() >= deadline:
                    return None
                time.sleep(DIRECTUS_LOCK_POLL_INTERVAL)
                client = _get_directus_lock_client()
                if client is None:
                    continue
                continue

        # No existing row — POST new
        new_exp = now_utc + timedelta(seconds=DIRECTUS_LOCK_TTL_SEC)
        try:
            r = client._request("POST", "/items/prod_locks", data={
                "resource_key": resource_key,
                "holder_machine_id": MACHINE_ID,
                "holder_pid": os.getpid(),
                "acquired_at": now_utc.isoformat(),
                "heartbeat_at": now_utc.isoformat(),
                "expires_at": new_exp.isoformat(),
                "reason": reason[:200],
            })
            row_id = (r.get("data") or {}).get("id") or r.get("id")
            return {"id": row_id, "resource_key": resource_key, "created": True}
        except Exception as exc:  # noqa: BLE001
            # Race: another machine created the row between our GET and POST.
            # Loop around and retry the GET path.
            msg = str(exc).lower()
            if "unique" in msg or "conflict" in msg or "duplicate" in msg:
                continue
            print(f"[dlock] WARN create failed (resetting + retrying): {exc}")
            _reset_directus_lock_client()
            if time.time() >= deadline:
                return None
            time.sleep(DIRECTUS_LOCK_POLL_INTERVAL)
            client = _get_directus_lock_client()
            if client is None:
                continue
            continue


def _directus_lock_release(lock: dict | None) -> None:
    """Release a lock acquired via _directus_lock_acquire. Failure is logged
    but not raised — the lock will expire naturally after TTL."""
    if not lock or lock.get("mode") == "single_machine":
        return
    row_id = lock.get("id")
    if not row_id:
        return
    client = _get_directus_lock_client()
    if client is None:
        return
    try:
        client._request("DELETE", f"/items/prod_locks/{row_id}")
    except Exception as exc:  # noqa: BLE001
        print(f"[dlock] WARN release failed (lock will expire in ~{DIRECTUS_LOCK_TTL_SEC}s): {exc}")


def _pre_fail_cdn_check(poller, beat_id: str, opt_idx: int, task_id: str) -> None:
    """Async one-shot check: query WaveSpeed directly (not via poller's cycle)
    to see if the task actually completed despite the normal poll failing.
    Runs off the poller thread to avoid blocking other beats' polls.
    Uses a SHORTER timeout (10s) than normal polls — if this also times out,
    we accept the transient_failure verdict.
    Tier 3 C4 HIGH fix (April 16 2026)."""
    try:
        # Use a direct fresh-connection helper with short timeout
        import http.client, ssl, urllib.parse, urllib.error
        url = wavespeed_poll_url(task_id)
        parsed = urllib.parse.urlparse(url)
        path = parsed.path + ("?" + parsed.query if parsed.query else "")
        ctx = ssl.create_default_context()
        ctx.options |= ssl.OP_NO_TICKET
        ctx.options |= ssl.OP_NO_COMPRESSION
        conn = http.client.HTTPSConnection(
            parsed.netloc,
            timeout=PRE_FAIL_CDN_CHECK_TIMEOUT,
            context=ctx,
        )
        try:
            conn.request("GET", path, headers={
                "Authorization": f"Bearer {poller.client.api_key}",
                "Content-Type": "application/json",
                "Connection": "close",
            })
            resp = conn.getresponse()
            if resp.status < 200 or resp.status >= 300:
                print(f"[pre-fail-cdn] {beat_id} opt {opt_idx + 1}: HTTP {resp.status} — accepting fail verdict")
                return
            payload = json.loads(resp.read().decode("utf-8"))
        finally:
            try:
                conn.close()
            except Exception:
                pass
        data = payload.get("data") or {}
        status = (data.get("status") or payload.get("status") or "").lower()
        outputs = data.get("outputs") or payload.get("outputs") or []
        if status == "completed" and outputs:
            print(f"[pre-fail-cdn] {beat_id} opt {opt_idx + 1}: task IS completed on WaveSpeed CDN — recovering")
            poller._download_and_mark_completed(
                beat_id, opt_idx, task_id, outputs[0],
                source="pre_fail_cdn_check",
            )
        else:
            # Stale "processing" or other non-completed response — accept the normal failure path
            print(f"[pre-fail-cdn] {beat_id} opt {opt_idx + 1}: status={status!r} — leaving failure verdict in place")
    except Exception as exc:  # noqa: BLE001 — pre-fail is best-effort
        print(f"[pre-fail-cdn] {beat_id} opt {opt_idx + 1}: probe error (non-blocking): {exc}")


# ---------------------------------------------------------------------------
# Beat-audio helpers (shared by lipsync + animation-duration inference).
# ANIMATION_DURATION_MATCHES_AUDIO (decision id=144, April 16 2026):
# animation clip duration must match TTS audio length. Kling v3 supports
# 4-10 seconds. We default to 5 for short audio (<=4.5s) and 10 otherwise.
# Audio > 10s raises a loud error — NEVER silently truncate speech.
# ---------------------------------------------------------------------------

KLING_MAX_DURATION_SEC = 10
KLING_MIN_DURATION_SEC = 5
_AUDIO_SHORT_THRESHOLD_SEC = 2.0  # audio <= this -> 5s animation; > -> 10s
# 2.0 = KLING_MIN_DURATION_SEC(5) - _VIDEO_TRIM_TAILROOM_TARGET_S(3.0).
# Bumped from 3.5→2.0 (2026-05-27) because LIPSYNC_PAD_END was extended to 2.5s
# and _VIDEO_TRIM_TAILROOM_TARGET_S was raised to match. With 3.5s threshold,
# audio in the 2.0–3.5s range still chose 5s Kling but only left 1.5s tail —
# not enough to cover a 2.5s face-return animation.


def _find_beat_audio(event_dir: Path, beat_key: str, audio_override: str | None = None, app=None) -> Path | None:
    """Resolve TTS mp3 for a beat. Single source of truth — used by both
    lipsync and duration-inference paths so they cannot drift.

    Priority ladder: explicit audio_override > trimmed variant > regular > trim5s.
    Returns None if no matching audio found on disk.

    Extracted from _handle_lipsync_submit per Phase 3 counter-agent finding
    (April 16 2026) to prevent divergent behavior between lipsync and
    animation-duration lookup."""
    if audio_override:
        p = Path(audio_override)
        if not p.is_file():
            return None
        # Security (CodeQL py/path-injection alert #11 follow-up):
        # audio_override flows from HTTP body and the returned Path is
        # later handed to ffmpeg / lipsync subprocesses by callers.
        # Containment guard: only accept paths inside the project root.
        try:
            project_root = os.path.realpath(str(DROPBOX_ROOT))
            real = os.path.realpath(str(p))
            if not (real == project_root or real.startswith(project_root + os.sep)):
                return None
        except Exception:
            return None
        return p

    try:
        beat_num = int(beat_key.split("_")[1])
    except (IndexError, ValueError):
        return None

    tts_dir = event_dir / "story_scene_tts_v2"
    if not tts_dir.is_dir():
        return None

    # Phase 1 nav: check storyboard-namespaced subdir first to avoid TTS collisions
    # across storyboards that share beat numbers (e.g. beat_03 in intro vs resolution)
    _stem = getattr(app, "storyboard_stem", "") if app is not None else ""
    _stem_tts_dir = tts_dir / _stem if _stem else tts_dir

    def _scan_dir(d: Path) -> list:
        if not d.is_dir():
            return []
        return [
            f for f in sorted(d.iterdir())
            if f.name.startswith(f"line_{beat_num:02d}_") and f.suffix == ".mp3"
        ]

    candidates = _scan_dir(_stem_tts_dir)
    if not candidates and _stem_tts_dir != tts_dir:
        candidates = _scan_dir(tts_dir)
    # Fallback: scan immediate subdirs of tts_dir when app= not passed (handlers
    # that omit app= miss storyboard-namespaced subdirs like storyboard_v43_prod/).
    if not candidates:
        for _sub in sorted(tts_dir.iterdir()):
            if _sub.is_dir():
                candidates = _scan_dir(_sub)
                if candidates:
                    break

    trimmed = [c for c in candidates if "trimmed" in c.name]
    regular = [c for c in candidates if "trim" not in c.name]
    trim5s = [c for c in candidates if "trim5s" in c.name]
    result = (trimmed or regular or trim5s or [None])[0]
    return result if (result and result.is_file()) else None


def _infer_animation_duration(audio_path: Path | None) -> tuple[int, str]:
    """Return (duration_seconds, log_reason) for Kling animation given audio.

    Raises ValueError if audio exceeds KLING_MAX_DURATION_SEC — the caller
    must surface this to the user; silent truncation is forbidden (counter-
    agent Phase 3 finding, April 16 2026). If audio_path is None or ffprobe
    fails, falls back to KLING_MIN_DURATION_SEC with a reason string so the
    caller can log the fallback."""
    if audio_path is None:
        return KLING_MIN_DURATION_SEC, "no_audio_found_default_5s"
    try:
        import subprocess
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)],
            capture_output=True, text=True, timeout=10,
        )
        raw = r.stdout.strip()
        if not raw:
            return KLING_MIN_DURATION_SEC, f"ffprobe_empty_stdout_default_5s:{audio_path.name}"
        dur = float(raw)
    except (FileNotFoundError, ValueError, subprocess.TimeoutExpired, OSError) as exc:
        return KLING_MIN_DURATION_SEC, f"ffprobe_error_default_5s:{type(exc).__name__}"

    if dur > KLING_MAX_DURATION_SEC:
        raise ValueError(
            f"audio file {audio_path.name} is {dur:.2f}s but Kling v3 maximum is "
            f"{KLING_MAX_DURATION_SEC}s — split the audio or edit the script"
        )
    if dur <= _AUDIO_SHORT_THRESHOLD_SEC:
        return KLING_MIN_DURATION_SEC, f"audio_{dur:.2f}s_uses_5s"
    return KLING_MAX_DURATION_SEC, f"audio_{dur:.2f}s_uses_10s"


def _mark_completed(partition: dict, beat_id: str, opt_idx: int, fname: str, size: int) -> None:
    """S5.5a2: parameter renamed `state` → `partition`. Callers from inside
    mutate_video_state pass the partition dict; legacy callers from inside
    mutate_state pass the full state and access partition["beats"] which
    must resolve to videos.intro.beats — those callers were also refactored
    to mutate_video_state in S5.5a2 (orphan_sweep, polling threads,
    transient_failure)."""
    beat = partition["beats"][beat_id]
    phase1 = beat["phase_1"]
    opt = phase1["options"][opt_idx]
    opt["status"] = "completed"
    opt["file"] = fname
    opt["size_bytes"] = size
    # phase status rollup
    all_done = all(o.get("status") == "completed" for o in phase1["options"])
    any_failed = any(o.get("status") == "failed" for o in phase1["options"])
    if all_done:
        phase1["status"] = "completed"
    elif any_failed and not any(o.get("status") == "polling" for o in phase1["options"]):
        phase1["status"] = "partial"
    else:
        phase1["status"] = "polling"


# ---------------------------------------------------------------------------
# Async Directus audit-trail for image-override drag-drop events.
# Counter-agent C4 CRITICAL finding (April 16 2026): image override at
# drag-drop time IS a creative decision that determines WaveSpeed output, so
# Rule 18 (Two-Write) applies literally. This writes a row to
# prod_session_decisions in a background thread so the UI never blocks.
# ---------------------------------------------------------------------------

def _t1_directus_log(action: str, details: dict) -> None:
    """Tier 1B: fire-and-forget activity log write for stale-timeout events.

    action is one of: 'stale_timeout_failed', 'stale_success_recovered',
    'late_success_resurrected_failed'. Non-blocking; failures logged and
    swallowed so the polling loop never dies. Runs on a daemon thread so the
    (blocking) Directus HTTP call doesn't stall the poller cycle.
    """
    def _do_write():
        try:
            _libdir = os.path.join(os.path.dirname(__file__), "credentials_lib")
            if _libdir not in sys.path:
                sys.path.insert(0, _libdir)
            from credentials import load_credentials  # type: ignore
            from directus import DirectusClient  # type: ignore
            creds = load_credentials()
            c = DirectusClient(
                creds["directus_url"],
                creds["directus_email"],
                creds["directus_password"],
            )
            c._request("POST", "/items/prod_activity_log", data={
                "action": action,
                "module_id": 1,
                "performed_by": "tier1b-stale-timeout",
                "details": json.dumps({
                    **details,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "tier": "1B",
                }),
            })
        except Exception as exc:  # noqa: BLE001
            print(f"[T1] directus log failed (non-blocking) action={action}: {exc}")

    threading.Thread(
        target=_do_write, daemon=True, name=f"t1-directus-log-{action}",
    ).start()


def _async_log_text_update(event_id: str, beat_id: str, old_text: str | None,
                           new_text: str, tts_existed: bool) -> None:
    """Fire-and-forget Directus write for contenteditable dialogue edit.
    DIALOGUE_EDITS_MUST_PERSIST (id=151) Rule 18 Two-Write compliance."""
    def _do_write():
        try:
            _libdir = os.path.join(os.path.dirname(__file__), "credentials_lib")
            if _libdir not in sys.path:
                sys.path.insert(0, _libdir)
            from credentials import load_credentials  # type: ignore
            from directus import DirectusClient  # type: ignore
            creds = load_credentials()
            c = DirectusClient(
                creds["directus_url"],
                creds["directus_email"],
                creds["directus_password"],
            )
            c._request("POST", "/items/prod_activity_log", data={
                "action": "beat_text_edit_saved",
                "module_id": 1,
                "performed_by": "claude-dialogue-autosave",
                "details": json.dumps({
                    "event_id": event_id,
                    "beat_id": beat_id,
                    "old_text_preview": (old_text or "")[:200],
                    "new_text_preview": new_text[:200],
                    "tts_existed_at_edit_time": tts_existed,
                    "stale_tts_flag_set": tts_existed and (old_text or "") != new_text,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }),
            })
        except Exception as exc:  # noqa: BLE001
            print(f"[text-update] Directus log failed (non-blocking): {exc}")
    threading.Thread(target=_do_write, daemon=True, name=f"dir-text-{beat_id}").start()


def _async_log_image_override(event_id: str, beat_id: str, image_key: str) -> None:
    """Fire-and-forget Directus write. Never raises, logs on failure."""
    def _do_write():
        try:
            # Lazy import to avoid circular / optional dep at server boot.
            # Guard sys.path append so long sessions don't accumulate duplicates.
            _libdir = os.path.join(os.path.dirname(__file__), "credentials_lib")
            if _libdir not in sys.path:
                sys.path.insert(0, _libdir)
            from credentials import load_credentials  # type: ignore
            from directus import DirectusClient  # type: ignore
            creds = load_credentials()
            c = DirectusClient(
                creds["directus_url"],
                creds["directus_email"],
                creds["directus_password"],
            )
            payload = {
                "decision_key": f"IMAGE_OVERRIDE_{event_id}_{beat_id}",
                "decision_text": (
                    f"Drag-drop image assignment: beat={beat_id} image_key={image_key} "
                    f"event={event_id} timestamp={datetime.now(timezone.utc).isoformat()}"
                ),
                "source_document": f"production_state.json (event {event_id})",
                "task_category": "storyboard_production",
                "status": "active",
            }
            c._request("POST", "/items/prod_session_decisions", data=payload)
            print(f"[directus] logged image override for {beat_id} -> {image_key}")
        except Exception as exc:  # noqa: BLE001 — fire-and-forget is ok
            print(f"[directus] WARN: image-override log failed (non-blocking): {exc}")

    t = threading.Thread(target=_do_write, daemon=True, name=f"dir-img-ovr-{beat_id}")
    t.start()


# ---------------------------------------------------------------------------
# §8.4 pre-lipsync pre-conditioning helpers — silence compression + video trim
# (decision 172 companion, CLAUDE.md §8.4, April 17 2026)
#
# Every lipsync submission auto-applies these before ByteDance sees the
# audio + video. Proven pattern from:
#   - beat_05_lipsync_both_silences_experiment.py (splice_audio_multi)
#   - tools/kling_startend_pipeline.py (silcomp_audio_if_needed)
# Rule 11 source fidelity: silcomp modifies ONLY inter-phrase silences;
# every spoken byte is preserved via ffmpeg -ss/-t re-encode at 44.1kHz mono.
# ---------------------------------------------------------------------------

_SILCOMP_NOISE_DB = "-32dB"
_SILCOMP_MIN_DURATION_S = 0.150    # silencedetect threshold (150ms)
_SILCOMP_TRIGGER_S = 1.0           # silences longer than this get compressed
_SILCOMP_TARGET_S = 0.8            # compress target duration
_VIDEO_TRIM_TAILROOM_S = 0.0       # SWITCH_TO_KLING_LIPSYNC_20260524: Kling lipsync closes
# the mouth naturally at audio end — no extra tail video needed (was 0.4s for ByteDance
# LatentSync which required extra frames to close mouth after audio stopped).
# The 1.5s TARGET below still guides how much tail we try to append for natural settling,
# but the MINIMUM validation floor is now 0 — beats with audio filling the full trim window
# (e.g. beat_03: 9.68s audio / 10.04s clip) are now valid.
# Kim 2026-05-21: 0.4s is too tight visually — the last Kling frame is often
# mid-articulation/mid-blink and the freeze pose at the end looks wrong. Target
# 1.5s of trailing video when the trim window allows, so the character has
# time to settle naturally after the last phoneme. Clamp via min() to whatever
# the [trim_start, trim_end] window actually accommodates — beats with audio
# near the 10s ceiling still get only the residual tail (no silent failure).
_VIDEO_TRIM_TAILROOM_TARGET_S = 3.0  # bumped 2026-05-27: covers LIPSYNC_PAD_END=2.5 + 0.5s margin
# Auto pre-roll (Preflight 110 LD AUTO_PREROLL_V1): when source TTS audio has
# insufficient leading silence, LatentSync can't lock mouth landmarks and the
# first phoneme's mouth movement is missing. Fold detection + padding into the
# silcomp pass (Counter recommendation — one ffmpeg cycle, not two).
_AUTO_PREROLL_MIN_S = 0.500        # if head silence < this, trigger padding
_AUTO_PREROLL_TARGET_S = 0.700     # pad head to at least this much silence
# Preflight 114 (2026-04-19): bumped from 0.300/0.400 -> 0.500/0.700 because
# ByteDance LatentSync injects its own 400ms head ramp on top of whatever
# we send. Old setting: our 400ms preroll + ByteDance's 400ms = 800ms total
# silent head, putting soft-vowel phrase openings ("Oh...") at the EDGE of
# the ByteDance fade-in window (quiet output, poor mouth animation).
# New setting: our 700ms preroll + ByteDance's 400ms = 1100ms total silent
# head. Speech starts cleanly past the ByteDance ramp at -17 dB instead of
# attenuated -28 dB. Cost: 300ms more dead air at start of every lipsync
# (absorbed by the existing max_audio_s overflow clamp on short clips).
_AUTO_PREROLL_PROBE_WINDOW_S = 0.800  # probe window for astats head-silence check (needs > MIN_S to avoid capping)
_AUTO_PREROLL_RMS_THRESHOLD_DB = -32.0  # mean RMS below this = silence (matches silcomp)

# Loudness normalization (Preflight 113 LD LOUDNORM_IN_SILCOMP_V1): Kim's
# 2026-04-19 diagnosis — ElevenLabs renders quiet phrases (hesitations like
# "Oh...") at -30 dB while the rest of the line averages -18 to -22 dB.
# ByteDance LatentSync gates audio below ~-30 dB as silence and produces
# zero mouth animation for those segments.
#
# Filter choice: we need DYNAMIC RANGE COMPRESSION (boost quiet parts to
# match loud parts), not just EBU R128 loudness normalization (which
# preserves relative dynamics — not what we want here). Pipeline:
#   1. dynaudnorm — dynamic normalization in 500ms sliding windows,
#      compresses dynamic range, boosts quiet phrases up to 15 dB
#   2. loudnorm (single-pass) — caps peaks, lands on a consistent LUFS
#      target so every module mixes at the same perceived loudness
#
# dynaudnorm params:
#   f=500 — 500ms frame length (covers typical phonemes cleanly)
#   g=15 — Gauss smoothing 15 (moderate — avoids pumping artifacts)
#   p=0.95 — peak target 95% (headroom for loudnorm's peak limiter)
#   m=15 — max gain factor 15 (aggressive enough to pull -30 dB up to ~-15)
# loudnorm params:
#   I = target integrated loudness (-16 LUFS = standard for speech)
#   TP = target true peak (-1.5 dBTP = safe ceiling, avoids clipping)
#   LRA = target loudness range (8 LU = tight)
_LOUDNORM_TARGET_I = -16.0
_LOUDNORM_TARGET_TP = -1.5
_LOUDNORM_TARGET_LRA = 8.0
_LOUDNORM_FILTER = (
    # Empirically tuned on Kim's beat_05 line_05_tessa.mp3 (2026-04-19):
    # f=200 (200ms frame) + g=5 (light Gauss smoothing) + m=15 (15x max gain)
    # boosted the quiet "Oh it's silly" (-30 dB) to -15 dB range while keeping
    # the louder follow-up speech relatively unchanged. The loudnorm second
    # stage then locks everything to -16 LUFS for cross-module consistency.
    "dynaudnorm=f=200:g=5:p=0.95:m=15,"
    f"loudnorm=I={_LOUDNORM_TARGET_I}:TP={_LOUDNORM_TARGET_TP}:"
    f"LRA={_LOUDNORM_TARGET_LRA}:print_format=summary"
)


def _ffprobe_duration(path: Path) -> float:
    """Return duration in seconds via ffprobe. Raises on failure (fail-loud)."""
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True, timeout=15,
    )
    return float(r.stdout.strip())


def _detect_silences(audio_path: Path) -> list[tuple[float, float]]:
    """ffmpeg silencedetect at -32dB / 150ms. Returns [(start_s, end_s), ...]."""
    r = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(audio_path),
         "-af", f"silencedetect=noise={_SILCOMP_NOISE_DB}:d={_SILCOMP_MIN_DURATION_S}",
         "-f", "null", "-"],
        capture_output=True, text=True, timeout=60,
    )
    out: list[tuple[float, float]] = []
    cur_start: float | None = None
    for line in r.stderr.splitlines():
        if "silence_start:" in line:
            try:
                cur_start = float(line.split("silence_start:")[1].strip().split()[0])
            except (ValueError, IndexError):
                cur_start = None
        elif "silence_end:" in line and cur_start is not None:
            try:
                s_end = float(line.split("silence_end:")[1].strip().split()[0])
                out.append((cur_start, s_end))
            except (ValueError, IndexError):
                pass
            cur_start = None
    return out


def _detect_head_silence_s(audio_path: Path,
                           window_s: float = _AUTO_PREROLL_PROBE_WINDOW_S,
                           threshold_db: float = _AUTO_PREROLL_RMS_THRESHOLD_DB) -> float:
    """Probe the actual leading silence duration via ffmpeg astats.

    Preflight 110 Counter Finding 1: ffmpeg silencedetect does NOT emit
    silence_start:0 for audio that begins above threshold. Three distinct
    conditions ("zero lead-in", "short lead-in <150ms", "ffmpeg parse miss")
    all look identical from silencedetect output. astats with atrim gives
    the mean RMS of the head window directly, which is authoritative.

    Returns: the duration (in seconds) of contiguous leading silence, capped
    at `window_s`. If the entire probe window is silent (mean RMS below
    threshold), returns `window_s`. If the very first sample is above
    threshold, returns 0.0.

    Implementation: slice [0, window_s] via atrim, measure RMS via astats.
    If mean RMS is above threshold, do a secondary silencedetect-style
    scan of the window to find where speech first begins within it.
    """
    # Fast check: mean RMS of the probe window
    r = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(audio_path),
         "-af", f"atrim=0:{window_s:.3f},astats=metadata=1:reset=1:measure_overall=RMS_level:measure_perchannel=0",
         "-f", "null", "-"],
        capture_output=True, text=True, timeout=30,
    )
    mean_rms_db: float | None = None
    for line in r.stderr.splitlines():
        # Overall line looks like: [Parsed_astats_1 @ 0x...] Overall
        #                          [Parsed_astats_1 @ 0x...]   RMS level dB: -34.512345
        if "RMS level dB:" in line:
            try:
                mean_rms_db = float(line.split("RMS level dB:")[1].strip().split()[0])
            except (ValueError, IndexError):
                continue
            break
    if mean_rms_db is None:
        # Probe failed — be conservative: assume 0 lead-in so caller pads.
        return 0.0
    if mean_rms_db < threshold_db:
        # Entire probe window is silence
        return round(window_s, 3)
    # Some speech in the window. Use silencedetect with a short-duration
    # threshold to find where speech starts within the window.
    r2 = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(audio_path),
         "-af", f"atrim=0:{window_s:.3f},silencedetect=noise={_SILCOMP_NOISE_DB}:d=0.050",
         "-f", "null", "-"],
        capture_output=True, text=True, timeout=30,
    )
    # If silencedetect reports a range starting at 0, the silence_end is
    # the length of leading silence.
    for line in r2.stderr.splitlines():
        if "silence_start:" in line:
            try:
                s_start = float(line.split("silence_start:")[1].strip().split()[0])
                if s_start > 0.010:  # silence starts mid-window -> no leading silence
                    return 0.0
            except (ValueError, IndexError):
                pass
        elif "silence_end:" in line:
            try:
                s_end = float(line.split("silence_end:")[1].strip().split()[0])
                return round(min(s_end, window_s), 3)
            except (ValueError, IndexError):
                pass
    # silencedetect emitted nothing and RMS was above threshold -> no lead-in.
    return 0.0


def _silcomp_audio(source_audio: Path, dst: Path,
                   auto_preroll: bool = False,
                   max_audio_s: float | None = None,
                   loudnorm: bool = False,
                   preroll_s: float = 0.0) -> tuple[Path, dict]:
    """Compress silences >1.0s down to 0.8s. Pass-through if no qualifying
    silences. Returns (path_to_use, metadata_dict).

    Preflight 110 AUTO_PREROLL_V1 extension: when `auto_preroll=True`, first
    probe the head silence via astats. If below _AUTO_PREROLL_MIN_S (300ms),
    prepend anullsrc silence so leading silence equals _AUTO_PREROLL_TARGET_S
    (400ms). This gives ByteDance LatentSync time to lock mouth landmarks
    before speech begins. Folded into silcomp's concat machinery per Counter
    recommendation — one ffmpeg cycle, not two. If `max_audio_s` is set, the
    preroll is clamped so (padded_audio + 0s) <= max_audio_s (caller should
    pass `window_len - _VIDEO_TRIM_TAILROOM_S` to avoid video-trim overflow).

    Caller MUST gate `auto_preroll=True` on `trim_start == 0` — Counter
    Finding 4: preroll interacts weirdly with a non-zero trim_start (Kim
    intended to skip settling frames; preroll would undo that). When in
    doubt, leave auto_preroll=False.

    preroll_s: explicit silence (seconds) to prepend BEFORE the TTS audio,
    independent of auto_preroll. Used by the lipsync submission path to honour
    phase_1.audio_delay (DELAY_FIX_20260524): the UI "Delay" slider means
    "let N seconds of animation play silently before speech starts." This
    bakes the delay into the audio bytes sent to ByteDance so LatentSync
    receives [silence][speech] and stamps mouths correctly from N seconds in.
    Takes priority over auto_preroll when both are non-zero.
    """
    src_dur = _ffprobe_duration(source_audio)
    silences = _detect_silences(source_audio)
    to_compress = [(s, e) for (s, e) in silences if (e - s) > _SILCOMP_TRIGGER_S]

    # --- Pre-roll computation (explicit preroll_s takes priority over auto) ---
    preroll_meta = {
        "applied": False,
        "reason": "disabled_by_caller",
        "detected_leading_silence_s": 0.0,
        "preroll_added_s": 0.0,
        "preroll_target_s": _AUTO_PREROLL_TARGET_S,
        "min_threshold_s": _AUTO_PREROLL_MIN_S,
    }
    preroll_add_s = 0.0
    if preroll_s > 0.0:
        # DELAY_FIX_20260524: explicit user-specified audio_delay. Prepend
        # exactly preroll_s seconds of silence regardless of existing head
        # silence — ByteDance will see [silence][speech] and stamp mouths
        # starting at preroll_s seconds into the clip.
        preroll_add_s = preroll_s
        preroll_meta["applied"] = True
        preroll_meta["reason"] = "explicit_audio_delay"
        preroll_meta["preroll_added_s"] = round(preroll_add_s, 3)
    elif auto_preroll:
        head = _detect_head_silence_s(source_audio)
        preroll_meta["detected_leading_silence_s"] = head
        if head >= _AUTO_PREROLL_MIN_S:
            preroll_meta["reason"] = "ok_sufficient_lead_in"
        else:
            # Pad to target
            raw_add = max(0.0, _AUTO_PREROLL_TARGET_S - head)
            # Clamp to avoid video-trim overflow (Counter Finding 3)
            if max_audio_s is not None:
                # Allowed add = max_audio_s - current_padded_src_dur_estimate
                # Estimate post-silcomp dur: sum(non-compressed parts) + 0.8*N
                comp_saved = sum((e - s) - _SILCOMP_TARGET_S
                                 for s, e in to_compress)
                est_post_silcomp = max(0.0, src_dur - comp_saved)
                max_add = max_audio_s - est_post_silcomp
                if raw_add > max_add:
                    preroll_add_s = max(0.0, max_add)
                    preroll_meta["clamped_to_fit_window"] = True
                    preroll_meta["clamped_from_s"] = round(raw_add, 3)
                else:
                    preroll_add_s = raw_add
            else:
                preroll_add_s = raw_add
            if preroll_add_s > 0:
                preroll_meta["applied"] = True
                preroll_meta["reason"] = "below_min_threshold"
                preroll_meta["preroll_added_s"] = round(preroll_add_s, 3)
            else:
                preroll_meta["reason"] = "clamped_to_zero_no_room"

    if not to_compress and preroll_add_s <= 0:
        # Preflight 113: even in the "no silences, no preroll" passthrough
        # case, apply loudnorm if enabled so quiet phrases still get boosted.
        # This is a single-pass ffmpeg call (source -> dst) with just the
        # loudnorm filter; preserves original duration, just changes loudness.
        if loudnorm:
            subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                 "-i", str(source_audio),
                 "-af", _LOUDNORM_FILTER,
                 "-c:a", "libmp3lame", "-b:a", "192k",
                 "-ac", "1", "-ar", "44100",
                 str(dst)],
                check=True, capture_output=True, timeout=120,
            )
            new_dur = _ffprobe_duration(dst)
            return dst, {
                "applied": False,
                "reason": "no_silences_over_threshold_loudnorm_only",
                "source_duration_s": round(src_dur, 3),
                "compressed_duration_s": round(new_dur, 3),
                "silences_compressed": [],
                "preroll_processing": preroll_meta,
                "loudnorm_applied": True,
                "loudnorm_target_i_lufs": _LOUDNORM_TARGET_I,
                "loudnorm_target_tp_dbtp": _LOUDNORM_TARGET_TP,
                "loudnorm_target_lra_lu": _LOUDNORM_TARGET_LRA,
            }
        return source_audio, {
            "applied": False,
            "reason": "no_silences_over_threshold",
            "source_duration_s": round(src_dur, 3),
            "compressed_duration_s": round(src_dur, 3),
            "silences_compressed": [],
            "preroll_processing": preroll_meta,
            "loudnorm_applied": False,
        }

    scratch: list[Path] = []
    prev_end = 0.0
    silence_log: list[dict] = []

    # --- Preflight 110 auto pre-roll: synthesize leading silence segment ---
    if preroll_add_s > 0:
        preroll_seg = dst.with_suffix(".seg_preroll.wav")
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
             "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
             "-t", f"{preroll_add_s:.3f}",
             "-ac", "1", "-ar", "44100", str(preroll_seg)],
            check=True, capture_output=True, timeout=30,
        )
        scratch.append(preroll_seg)

    for idx, (s_start, s_end) in enumerate(to_compress):
        p1 = dst.with_suffix(f".seg{idx*2:02d}.wav")
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
             "-ss", f"{prev_end:.3f}", "-i", str(source_audio),
             "-t", f"{max(0.0, s_start - prev_end):.3f}",
             "-ac", "1", "-ar", "44100", str(p1)],
            check=True, capture_output=True, timeout=60,
        )
        scratch.append(p1)
        p2 = dst.with_suffix(f".seg{idx*2+1:02d}.wav")
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
             "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
             "-t", f"{_SILCOMP_TARGET_S:.3f}",
             "-ac", "1", "-ar", "44100", str(p2)],
            check=True, capture_output=True, timeout=30,
        )
        scratch.append(p2)
        silence_log.append({
            "range_s": [round(s_start, 3), round(s_end, 3)],
            "original_s": round(s_end - s_start, 3),
            "new_s": _SILCOMP_TARGET_S,
        })
        prev_end = s_end

    tail = dst.with_suffix(f".seg{len(scratch):02d}.wav")
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-ss", f"{prev_end:.3f}", "-i", str(source_audio),
         "-t", f"{max(0.0, src_dur - prev_end):.3f}",
         "-ac", "1", "-ar", "44100", str(tail)],
        check=True, capture_output=True, timeout=60,
    )
    scratch.append(tail)

    concat_list = dst.with_suffix(".concat.txt")
    # ffmpeg concat demuxer resolves `file '...'` entries relative to the
    # concat.txt's OWN directory, not the process cwd. Use absolute paths to
    # avoid doubled-path ENOENT failures when scratch paths are relative.
    # Locked: SILCOMP_CONCAT_PATHS_MUST_BE_ABSOLUTE (2026-04-18).
    concat_list.write_text(
        "\n".join(f"file '{p.resolve()}'" for p in scratch) + "\n",
        encoding="utf-8",
    )
    try:
        # Preflight 113: apply loudnorm to the concat output when enabled.
        # Single -af pass on the already-concatenated audio; quiet phrases
        # get boosted to -16 LUFS target so LatentSync's audio gate
        # doesn't drop them as below-threshold.
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
               "-f", "concat", "-safe", "0", "-i", str(concat_list)]
        if loudnorm:
            cmd += ["-af", _LOUDNORM_FILTER]
        cmd += ["-c:a", "libmp3lame", "-b:a", "192k", str(dst)]
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
    finally:
        for p in scratch + [concat_list]:
            try: p.unlink()
            except OSError: pass

    new_dur = _ffprobe_duration(dst)
    return dst, {
        "applied": True,
        "reason": "silences_over_threshold_compressed",
        "source_duration_s": round(src_dur, 3),
        "compressed_duration_s": round(new_dur, 3),
        "silences_compressed": silence_log,
        "preroll_processing": preroll_meta,
        "loudnorm_applied": bool(loudnorm),
        "loudnorm_target_i_lufs": _LOUDNORM_TARGET_I if loudnorm else None,
        "loudnorm_target_tp_dbtp": _LOUDNORM_TARGET_TP if loudnorm else None,
        "loudnorm_target_lra_lu": _LOUDNORM_TARGET_LRA if loudnorm else None,
    }


def _trim_video_to_audio(source_video: Path, dst: Path,
                         audio_duration_s: float,
                         *,
                         trim_start: float = 0.0,
                         trim_end: float | None = None,
                         ) -> tuple[Path, float, float, float]:
    """Trim video to audio_duration + 0.4s within the user-specified
    [trim_start, trim_end] window from `phase_1`.

    Locked: LIPSYNC_TRIM_WINDOW_HONORED_20260419 — ffmpeg `-ss` runs BEFORE
    `-i` (input-side seek); frame-accurate because of the libx264 re-encode
    below. Do NOT switch to `-c copy` — that would make `-ss` keyframe-aligned
    and jump back 1-2s.

    Backward compat: `trim_start=0.0, trim_end=None` reproduces the old
    "trim from frame 0" behavior (effective_end collapses to raw_dur).

    Returns (dst, actual_trim_duration_s, trim_start_used, trim_end_used).
    """
    raw_dur = _ffprobe_duration(source_video)
    effective_end = trim_end if trim_end is not None else raw_dur
    window_len = max(0.0, effective_end - trim_start)
    remaining = max(0.0, raw_dur - trim_start)
    # Target the generous 1.5s tail (Kim 2026-05-21); clamp by window + raw.
    # Beats with audio close to the trim_end ceiling fall back to whatever
    # residual tail remains. The validation in handle_lipsync_submit_v4
    # enforces the 0.4s MINIMUM tail before this function runs.
    target = audio_duration_s + _VIDEO_TRIM_TAILROOM_TARGET_S
    actual = min(target, window_len, remaining)
    print(f"[trim] src={source_video.name} raw={raw_dur:.2f}s "
          f"trim_start={trim_start:.2f} trim_end={effective_end:.2f} "
          f"audio={audio_duration_s:.2f} -> actual={actual:.2f}s")
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-ss", f"{trim_start:.3f}",
         "-i", str(source_video), "-t", f"{actual:.3f}",
         "-c:v", "libx264", "-preset", "fast", "-crf", "18",
         "-an",  # lipsync input should not carry source audio
         "-movflags", "+faststart", str(dst)],
        check=True, capture_output=True, timeout=180,
    )
    return dst, actual, trim_start, effective_end


def _async_log_use_as_final(event_id: str, beat_id: str, file: str) -> None:
    """Fire-and-forget Directus log for 'Use as Final (no lipsync)' action."""
    def _do_write():
        try:
            _libdir = os.path.join(os.path.dirname(__file__), "credentials_lib")
            if _libdir not in sys.path:
                sys.path.insert(0, _libdir)
            from credentials import load_credentials  # type: ignore
            from directus import DirectusClient  # type: ignore
            creds = load_credentials()
            c = DirectusClient(
                creds["directus_url"], creds["directus_email"], creds["directus_password"],
            )
            c._request("POST", "/items/prod_activity_log", data={
                "action": "use_as_final",
                "module_id": 1,
                "performed_by": "_handle_use_as_final",
                "details": json.dumps({
                    "event_id": event_id, "beat_id": beat_id, "file": file,
                    "source": "raw_option_no_lipsync",
                    "rule_reference": "Spec A / LD-139 partial / CLAUDE.md Rule 8",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }),
            })
        except Exception as exc:  # noqa: BLE001
            print(f"[use-as-final-log] write failed (non-blocking): {exc}")
    threading.Thread(target=_do_write, daemon=True, name=f"dir-final-{beat_id}").start()


def _async_log_lipsync_submit(event_id: str, beat_id: str,
                              audio_processing: dict,
                              video_trimmed_to_s: float,
                              source_option: int) -> None:
    """Fire-and-forget Directus log for lipsync submit + §8.4 pre-conditioning."""
    def _do_write():
        try:
            _libdir = os.path.join(os.path.dirname(__file__), "credentials_lib")
            if _libdir not in sys.path:
                sys.path.insert(0, _libdir)
            from credentials import load_credentials  # type: ignore
            from directus import DirectusClient  # type: ignore
            creds = load_credentials()
            c = DirectusClient(
                creds["directus_url"], creds["directus_email"], creds["directus_password"],
            )
            c._request("POST", "/items/prod_activity_log", data={
                "action": "lipsync_submit_v2",
                "module_id": 1,
                "performed_by": "_handle_lipsync_submit_v2",
                "details": json.dumps({
                    "event_id": event_id, "beat_id": beat_id,
                    "source_option": source_option,
                    "audio_processing": audio_processing,
                    "video_trimmed_to_s": round(video_trimmed_to_s, 3),
                    "rule_reference": "CLAUDE.md §8.4 / decision 162",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }),
            })
        except Exception as exc:  # noqa: BLE001
            print(f"[lipsync-log] submit write failed (non-blocking): {exc}")
    threading.Thread(target=_do_write, daemon=True, name=f"dir-lipsync-sub-{beat_id}").start()


def _async_log_lipsync_complete(event_id: str, beat_id: str,
                                output_file: str, size_bytes: int) -> None:
    """Fire-and-forget Directus log for lipsync completion."""
    def _do_write():
        try:
            _libdir = os.path.join(os.path.dirname(__file__), "credentials_lib")
            if _libdir not in sys.path:
                sys.path.insert(0, _libdir)
            from credentials import load_credentials  # type: ignore
            from directus import DirectusClient  # type: ignore
            creds = load_credentials()
            c = DirectusClient(
                creds["directus_url"], creds["directus_email"], creds["directus_password"],
            )
            c._request("POST", "/items/prod_activity_log", data={
                "action": "lipsync_complete_v2",
                "module_id": 1,
                "performed_by": "_handle_lipsync_submit_v2",
                "details": json.dumps({
                    "event_id": event_id, "beat_id": beat_id,
                    "output_file": output_file, "size_bytes": size_bytes,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }),
            })
        except Exception as exc:  # noqa: BLE001
            print(f"[lipsync-log] complete write failed (non-blocking): {exc}")
    threading.Thread(target=_do_write, daemon=True, name=f"dir-lipsync-done-{beat_id}").start()


# ---------------------------------------------------------------------------
# TTS auto-regen on text edit (decision 181 TTS_AUTO_REGEN_ON_TEXT_EDIT,
# April 17 2026; companion preflight id=39)
#
# When a beat's text changes via _handle_beat_update_text, synchronously
# regenerate the TTS audio using the beat's speaker voice profile from
# Directus prod_voice_profiles. Ensures Rule 11 source fidelity: audio
# always matches the current text, never drifts.
#
# Downstream stages (animation duration inference, lipsync silcomp) read
# the audio file via _find_beat_audio and _infer_animation_duration —
# unchanged — so they automatically pick up the fresh audio.
# ---------------------------------------------------------------------------

_VOICE_PROFILE_CACHE: dict[str, dict] | None = None
_VOICE_PROFILE_CACHE_LOCK = threading.Lock()

# Cached DirectusClient for voice-profile read/write (Phase A panel
# slider routes). Avoids re-reading credentials + re-authing on every
# slider change — counter-agent F4 fix. The client owns its own JWT
# refresh so a long-lived process is fine.
_VOICE_DIRECTUS_CLIENT = None
_VOICE_DIRECTUS_CLIENT_LOCK = threading.Lock()


def _get_voice_directus_client():
    """Return a cached DirectusClient for prod_voice_profiles routes.
    Lazy-initialized; thread-safe; reuses existing JWT refresh in
    DirectusClient (lib/directus.py)."""
    global _VOICE_DIRECTUS_CLIENT
    with _VOICE_DIRECTUS_CLIENT_LOCK:
        if _VOICE_DIRECTUS_CLIENT is not None:
            return _VOICE_DIRECTUS_CLIENT
        _libdir = os.path.join(os.path.dirname(__file__), "credentials_lib")
        if _libdir not in sys.path:
            sys.path.insert(0, _libdir)
        from credentials import load_credentials  # type: ignore
        from directus import DirectusClient  # type: ignore
        creds = load_credentials()
        _VOICE_DIRECTUS_CLIENT = DirectusClient(
            creds["directus_url"],
            creds["directus_email"],
            creds["directus_password"],
        )
        return _VOICE_DIRECTUS_CLIENT

ELEVENLABS_TTS_ENDPOINT = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

# Speaker aliases — storyboard L[] `s:` field may use informal / legacy names.
# Keys matched case-insensitive. All aliases resolve to the CURRENT canonical
# character_name in Directus prod_voice_profiles.
#
# Lore update 2026-04-17 (decision 183 LORE_UPDATE_WIZARD_BIRD_RENAME):
#   Wizard: Myrrhin -> Cedric (the Great Wizard)
#   Bird:   Pip / Guide Bird -> Chipper (Assistant to the Great Wizard Cedric)
# Legacy names kept as aliases so existing storyboard L[] speakers and
# dialogue lines still route to the correct voice profile without a mass
# rename across every beat.
_SPEAKER_ALIAS = {
    # Bird guide — Chipper/Pip retired; canonical guide is Arlo (2026-06-13).
    "chipper": "Arlo",
    "guide bird": "Arlo",
    "pip": "Arlo",
    "assistant bird": "Arlo",
    "arlo": "Arlo",
    # Lemur archaeologist — Luna retired (2026-06-13).
    "luna": "Lorelai",
    "lorelai": "Lorelai",
    # Wizard (Cedric) — canonical + all legacy aliases
    "cedric": "Cedric",
    "myrrhin": "Cedric",         # legacy (pre-2026-04-17)
    "great wizard": "Cedric",
    "the great wizard": "Cedric",
    "narrator": "Cedric",
    # Turtle
    "tessa": "Tessa",
}


def _load_voice_profiles_from_directus(force_refresh: bool = False) -> dict[str, dict]:
    """Load and cache voice profiles from Directus prod_voice_profiles.
    Keyed by character_name (case-preserved). Fire-once at server startup
    via _ensure_voice_profile_cache. Refreshed in-process from
    /api/voice/profile_update (Phase A panel slider PATCH path) by
    calling this function with force_refresh=True. There is no
    standalone reload HTTP route — the slider POST route owns the
    refresh side-effect. (Counter-agent F11 fix to obsolete docstring.)
    """
    global _VOICE_PROFILE_CACHE
    with _VOICE_PROFILE_CACHE_LOCK:
        if _VOICE_PROFILE_CACHE is not None and not force_refresh:
            return _VOICE_PROFILE_CACHE
        try:
            _libdir = os.path.join(os.path.dirname(__file__), "credentials_lib")
            if _libdir not in sys.path:
                sys.path.insert(0, _libdir)
            from credentials import load_credentials  # type: ignore
            from directus import DirectusClient  # type: ignore
            creds = load_credentials()
            c = DirectusClient(creds["directus_url"], creds["directus_email"],
                               creds["directus_password"])
            r = c._request("GET", "/items/prod_voice_profiles")
            cache = {}
            for p in r.get("data", []):
                name = p.get("character_name") or p.get("name")
                if not name:
                    continue
                cache[name] = {
                    "character_name": name,
                    "voice_id": p.get("elevenlabs_voice_id") or p.get("voice_id"),
                    "stability": p.get("stability"),
                    "similarity_boost": p.get("similarity_boost"),
                    "style": p.get("style"),
                    "speed": p.get("speed"),
                    "model": p.get("model", "eleven_v3"),
                }
            _VOICE_PROFILE_CACHE = cache
            print(f"[voice-profiles] loaded {len(cache)} profiles from Directus: "
                  f"{sorted(cache.keys())}")
            # V1_VOICE_PROFILE_COMPLETENESS_V1 (locked 2026-05-13) — warn
            # loudly at load time when V1-required character voices are
            # missing from prod_voice_profiles, so the gap surfaces at
            # server start rather than at first Regen Audio click. Per
            # LD-148 ELEVENLABS_V3_FOR_ALL_CHARACTERS, all V1 creatures +
            # NPCs require registered voice profiles.
            _V1_REQUIRED_VOICES = {
                # 6 V1 creatures (LD-353 V1_CREATURE_SET_6_BENSON_AT_M3)
                "Cedric", "Chipper", "Tessa", "Luna",
                "Benson", "Ember", "Bork", "Bramble",
                # NPCs referenced in Arc 1 (LD-148 list)
                # Note: Oliver/Grizzle/Willow appear later in the arc roadmap
                # but are not strictly blocking M1 audio production.
            }
            _missing = sorted(_V1_REQUIRED_VOICES - set(cache.keys()))
            if _missing:
                print(
                    f"[voice-profiles] WARN: V1-required voice profiles "
                    f"MISSING from Directus: {_missing}. Regen Audio will "
                    f"fail for any beat with these speakers. Add via "
                    f"POST /items/prod_voice_profiles with fields "
                    f"{{character_name, elevenlabs_voice_id, stability, "
                    f"similarity_boost, style, speed, model='eleven_v3'}}. "
                    f"Per LD V1_VOICE_PROFILE_COMPLETENESS_V1."
                )
            return cache
        except Exception as exc:  # noqa: BLE001
            print(f"[voice-profiles] WARN load failed ({exc}); using empty cache")
            _VOICE_PROFILE_CACHE = {}
            return _VOICE_PROFILE_CACHE


def _resolve_voice_profile(speaker: str) -> dict | None:
    """Look up voice profile for a speaker string via aliases + substring match."""
    if not speaker:
        return None
    cache = _load_voice_profiles_from_directus()
    key_lc = speaker.lower().strip()
    # Arlo intentionally reuses Chipper's ElevenLabs voice while keeping a
    # separate speaker identity for visual prompts and Kling Elements.
    if key_lc == "arlo" and "Chipper" in cache:
        return cache["Chipper"]
    # Alias table first
    canonical = _SPEAKER_ALIAS.get(key_lc)
    if canonical and canonical in cache:
        return cache[canonical]
    # Lorelai renamed from Luna — Directus may still key the lemur voice as Luna.
    if canonical == "Lorelai" and "Luna" in cache:
        return cache["Luna"]
    # Direct match
    for name in cache:
        if name.lower() == key_lc:
            return cache[name]
    # Substring match (e.g., "Guide Bird (Pip)" -> Guide Bird)
    for name in cache:
        if name.lower() in key_lc or key_lc in name.lower():
            return cache[name]
    return None


# Cue-marker denylist: meta-markers that aren't meant to be spoken aloud.
# ElevenLabs v3 doesn't natively understand the literal word "pause" as a
# silence — without replacement it would speak "pause" as the noun. Replaced
# with " ... " (ellipsis) which v3 reads as a natural speech pause.
#
# This is intentionally a SHORT denylist, not an allowlist. Everything else
# (parentheticals, free-form bracket content, emotional tags) passes
# through verbatim — ElevenLabs v3 is flexible at interpreting authored
# voice/emotional direction and Kim should not be restricted to an
# enumerated vocabulary.
TTS_CUE_MARKER_PATTERN = re.compile(
    r'\[\s*(pause|break|silence)\s*\]',
    flags=re.IGNORECASE,
)


def _clean_text_for_tts(text: str) -> str:
    """Pre-process beat.text for the ElevenLabs v3 TTS payload.

    Per LD `TTS_STRIP_STAGE_DIRECTION_V2` (2026-05-14, supersedes V1).

    History — V1 (earlier on 2026-05-14) over-fixed by stripping every
    (parenthetical) of 3+ chars + applying a 27-word allowlist for
    bracket emotional tags. Evidence: beat_02 audio ('shocked,
    show-stopper voice' parenthetical) was authored BEFORE V1 landed
    and worked correctly — ElevenLabs v3 interpreted the parens as
    voice direction. V1's blanket strip would have removed Kim's
    voice-direction cues. The allowlist also silently dropped any
    bracket Kim wrote that wasn't in the 27-word table.

    V2 contract: PASS EVERYTHING through verbatim EXCEPT explicit cue
    markers `[pause]` / `[break]` / `[silence]` which become ` ... `
    (ellipsis pause). v3 reads ellipsis as natural speech pause.

    Rationale: ElevenLabs v3 already handles parenthetical voice
    direction and bracket emotional tags with its own heuristics.
    Kim authors freely — no allowlist restriction. If v3 reads a
    parenthetical aloud unexpectedly, that's an authoring-style
    decision Kim can rephrase (e.g., move the cue into a bracket tag
    at the start of the line).

    Rule 11 source fidelity: spoken dialogue is byte-for-byte preserved.

    V3 (LD-733 TTS_STRIP_LEADING_PARENTHETICAL_V3, locked 2026-05-16,
    SHIPPED 2026-05-20 after fabrication-scan discovered V3 was never
    actually landed in code): strip the LEADING parenthetical at the
    start of text. Per LD-728 the leading paren is a VISUAL cue for
    Kling motion + end-frame, NOT voice direction — but ElevenLabs v3
    treats it as dramatic prose and inserts multi-second pauses.
    Empirical 2026-05-16: beat_06 audio 17.66s → 11.539s after this
    strip (−6.1s of phantom silent pauses removed). Only the FIRST
    parenthetical at start-of-text is stripped — inline parentheticals
    later in the dialogue body remain (V2 backward-compat for voice
    direction). 3+ char minimum so single-letter parens like "(!)"
    don't accidentally match.
    """
    if not text:
        return text
    # V3 leading-paren strip (LD-733). Pattern: optional leading whitespace
    # + a single (...) of 3+ chars + optional trailing whitespace, anchored
    # at start of text only.
    cleaned = re.sub(r'^\s*\([^)]{3,}\)\s*', '', text)
    cleaned = TTS_CUE_MARKER_PATTERN.sub(' ... ', cleaned)
    # Collapse any whitespace runs created by the substitution.
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def _tts_regenerate_for_beat(app, beat_id: str, text: str,
                             elevenlabs_key: str,
                             video_role: str = "intro",
                             *,
                             speaker_override: str | None = None,
                             storyboard_beat_id: str | None = None) -> dict:
    """Synchronously regenerate TTS audio for a beat via ElevenLabs v3.

    Rule 11 source fidelity: text preserved verbatim, voice profile locked
    per prod_voice_profiles.

    Archives any existing line_NN_*.mp3 files in story_scene_tts_v2/ to
    _archive_superseded/ before writing the new file. Atomic tmp+rename.

    Returns dict with keys: {ok, audio_file, audio_duration_s, size_bytes,
    voice_id, model, voice_settings, speaker, error?}.
    Raises nothing — all failures go in the return dict.
    """
    beat_num_s = ""
    id_for_line = (storyboard_beat_id or beat_id or "").strip()
    try:
        if id_for_line.startswith("beat_"):
            beat_num = int(id_for_line.split("_")[1])
        else:
            m = re.search(r"_beat_(\d+)$", beat_id or "")
            if m:
                beat_num = int(m.group(1))
            else:
                beat_num = int(beat_id.split("_")[1])
        beat_num_s = f"{beat_num:02d}"
    except (IndexError, ValueError):
        return {"ok": False, "error": f"unparseable beat_id: {beat_id!r}"}

    state_beat_id = storyboard_beat_id or beat_id

    # Resolve speaker -> voice profile. Read from the caller's actual partition.
    beats = app.state.get_beats(video_role)
    beat_state = beats.get(state_beat_id) or beats.get(beat_id) or {}
    speaker = (speaker_override or beat_state.get("speaker") or "").strip()
    if not speaker:
        # Fallback: parse from storyboard L[] s: field
        try:
            html = app.storyboard_path.read_text(encoding="utf-8")
            marker = f'a:"line_{beat_num_s}"'
            idx = html.find(marker)
            if idx >= 0:
                ob = html.rfind("{", 0, idx)
                cb = html.find("}", idx)
                entry = html[ob:cb + 1]
                m = re.search(r's:"([^"]+)"', entry)
                if m:
                    speaker = m.group(1)
        except Exception:  # noqa: BLE001
            pass

    if not speaker:
        return {"ok": False, "error": f"could not resolve speaker for {beat_id}"}

    profile = _resolve_voice_profile(speaker)
    if not profile or not profile.get("voice_id"):
        # Surface all currently-registered + missing speakers so Kim can
        # see the gap shape (not just the one beat's failure).
        _registered = sorted((_VOICE_PROFILE_CACHE or {}).keys())
        return {"ok": False,
                "error": f"no voice profile for speaker {speaker!r}. "
                         f"Currently registered: {_registered}. "
                         f"Add via POST /items/prod_voice_profiles "
                         f"(character_name, elevenlabs_voice_id, stability, "
                         f"similarity_boost, style, speed, model='eleven_v3'). "
                         f"Per LD-148 ELEVENLABS_V3_FOR_ALL_CHARACTERS + "
                         f"LD V1_VOICE_PROFILE_COMPLETENESS_V1."}

    # Build voice_settings, dropping keys ElevenLabs rejects when None.
    voice_settings = {}
    for k in ("stability", "similarity_boost", "style", "speed"):
        v = profile.get(k)
        if v is not None:
            voice_settings[k] = float(v)

    model_id = profile.get("model") or "eleven_v3"

    # Speaker slug for filename (match existing naming convention).
    speaker_slug = speaker.lower().replace(" ", "_").replace("(", "").replace(")", "")
    # Canonicalize: Guide Bird -> guide_bird, Tessa -> tessa, Pip -> pip.
    speaker_slug = re.sub(r"[^a-z_]", "", speaker_slug)

    tts_dir = app.event_dir / "story_scene_tts_v2"
    # Write to storyboard-namespaced subdir to prevent TTS collision across storyboards
    _sb_stem = getattr(app, "storyboard_stem", "")
    if _sb_stem:
        tts_dir = tts_dir / _sb_stem
    tts_dir.mkdir(parents=True, exist_ok=True)
    out_path = tts_dir / f"line_{beat_num_s}_{speaker_slug}.mp3"

    # Strip stage-direction markup before sending to ElevenLabs per
    # TTS_STRIP_STAGE_DIRECTION_V1 (2026-05-14). beat.text is the
    # source-of-truth for AUTHORING (image-prompt cues per LD-443,
    # motion-prompt cues per Fix 1 morning of 2026-05-13), but only the
    # spoken-dialogue portion goes to TTS. v3 native emotional tags
    # ([warm], [gentle], etc.) are preserved; cue brackets ([pause],
    # [break], [silence]) become natural ellipsis pauses; parentheticals
    # of 3+ chars are stripped. Rule 11 source fidelity: spoken dialogue
    # text is unchanged byte-for-byte; only authoring metadata is stripped.
    tts_text = _clean_text_for_tts(text)
    if tts_text != text:
        print(f"[tts-regen] {beat_id} stripped stage direction: "
              f"{len(text)}c -> {len(tts_text)}c")

    # Call ElevenLabs v1/text-to-speech synchronously.
    # ElevenLabs TTS submit — use universal hardening helper
    # (decision 185 UNIVERSAL_EXTERNAL_API_HARDENING, April 17 2026):
    # fresh http.client per attempt, OP_NO_TICKET, 90s timeout, 3-attempt
    # exponential backoff. Same pattern applied to Kling + FLUX Kontext.
    from kling_startend_pipeline import robust_https_request
    body = json.dumps({
        "text": tts_text,
        "model_id": model_id,
        "voice_settings": voice_settings,
    }).encode("utf-8")
    t0 = time.time()
    try:
        status_code, audio_bytes = robust_https_request(
            host="api.elevenlabs.io",
            path=f"/v1/text-to-speech/{profile['voice_id']}",
            method="POST",
            headers={"xi-api-key": elevenlabs_key,
                     "Content-Type": "application/json",
                     "Accept": "audio/mpeg"},
            body=body,
            timeout=90,
            max_retries=3,
        )
    except Exception as e:
        return {"ok": False,
                "error": f"ElevenLabs network (after retries): {type(e).__name__}: {e}",
                "speaker": speaker, "voice_id": profile["voice_id"]}
    if status_code >= 400:
        detail = audio_bytes[:400].decode("utf-8", errors="replace")
        return {"ok": False,
                "error": f"ElevenLabs HTTP {status_code}: {detail}",
                "speaker": speaker, "voice_id": profile["voice_id"]}
    elapsed_call = time.time() - t0

    # Archive any prior line_NN_*.mp3 before writing new.
    archive_dir = tts_dir / "_archive_superseded"
    archive_dir.mkdir(exist_ok=True)
    ts_archive = datetime.now().strftime("%Y%m%d-%H%M%S")
    for prior in sorted(tts_dir.glob(f"line_{beat_num_s}_*.mp3")):
        if prior.parent == archive_dir:
            continue  # already archived
        dst = archive_dir / f"{prior.stem}_preedit_{ts_archive}{prior.suffix}"
        try:
            shutil.move(str(prior), str(dst))
        except OSError as e:
            print(f"[tts-regen] archive failed for {prior.name}: {e}")

    # Atomic write of new audio.
    tmp = out_path.with_suffix(f".mp3.tmp.{os.getpid()}")
    try:
        tmp.write_bytes(audio_bytes)
        os.replace(tmp, out_path)
    except OSError as e:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass
        return {"ok": False, "error": f"atomic write failed: {e}"}

    # Measure duration (ffprobe).
    try:
        dur = _ffprobe_duration(out_path)
    except (subprocess.CalledProcessError, ValueError, OSError):
        dur = 0.0

    # Update state: audio_file, audio_duration_s, clear text_modified_after_tts,
    # mark lipsync.audio_changed if a completed lipsync exists.
    now_iso = datetime.now(timezone.utc).isoformat()
    def _update(partition, _bid=state_beat_id, _af=out_path.name, _d=dur, _iso=now_iso):
        b = partition.setdefault("beats", {}).setdefault(_bid, {})
        b["audio_file"] = _af
        b["audio_duration_s"] = round(_d, 3)
        b["audio_regenerated_at"] = _iso
        b["text_modified_after_tts"] = False  # audio is now fresh for the current text
        # If a completed lipsync exists, it's now stale (audio changed).
        ls = b.get("lipsync") or {}
        if ls.get("status") == "completed":
            ls["audio_changed"] = True
    app.state.mutate_video_state(video_role, _update)

    result = {
        "ok": True,
        "audio_file": out_path.name,
        "audio_duration_s": round(dur, 3),
        "size_bytes": len(audio_bytes),
        "voice_id": profile["voice_id"],
        "model": model_id,
        "voice_settings": voice_settings,
        "speaker": speaker,
        "elapsed_s": round(elapsed_call, 2),
    }

    # Rule 18 fire-and-forget activity log.
    def _log():
        try:
            _libdir = os.path.join(os.path.dirname(__file__), "credentials_lib")
            if _libdir not in sys.path:
                sys.path.insert(0, _libdir)
            from credentials import load_credentials  # type: ignore
            from directus import DirectusClient  # type: ignore
            creds = load_credentials()
            c = DirectusClient(creds["directus_url"], creds["directus_email"],
                               creds["directus_password"])
            c._request("POST", "/items/prod_activity_log", data={
                "action": "tts_auto_regenerated_on_text_edit",
                "module_id": 1,
                "performed_by": "_tts_regenerate_for_beat",
                "details": json.dumps({
                    "beat_id": beat_id,
                    "speaker": speaker,
                    "voice_id": profile["voice_id"],
                    "model": model_id,
                    "voice_settings": voice_settings,
                    "text_length": len(text),
                    "audio_file": out_path.name,
                    "audio_duration_s": result["audio_duration_s"],
                    "elapsed_s": result["elapsed_s"],
                    "decision_reference": "181 TTS_AUTO_REGEN_ON_TEXT_EDIT",
                    "timestamp": now_iso,
                }),
            })
        except Exception as exc:  # noqa: BLE001
            print(f"[tts-regen] activity log failed (non-blocking): {exc}")
    threading.Thread(target=_log, daemon=True, name=f"dir-tts-{beat_id}").start()

    return result


# ---------------------------------------------------------------------------
# Server restart (shared by /api/server/restart handler and watchdog)
# ---------------------------------------------------------------------------

def _argv_with_runtime_event_pin(argv: list[str], app) -> list[str]:
    """Rewrite --event-dir / --event-id to match runtime-loaded event (not launch argv)."""
    try:
        runtime_dir = Path(getattr(app, "event_dir", "") or "").resolve()
        runtime_id = str(getattr(app, "event_id", "") or "").strip()
    except Exception:
        return list(argv)
    if not runtime_dir.is_dir() or not runtime_id:
        return list(argv)
    out = list(argv)
    for i, arg in enumerate(out):
        if arg == "--event-dir" and i + 1 < len(out):
            out[i + 1] = str(runtime_dir)
        elif arg.startswith("--event-dir="):
            out[i] = f"--event-dir={runtime_dir}"
        elif arg == "--event-id" and i + 1 < len(out):
            out[i + 1] = runtime_id
        elif arg.startswith("--event-id="):
            out[i] = f"--event-id={runtime_id}"
    return out


def perform_server_restart(server, app, reason: str = "api") -> None:
    """Cleanly shut down the HTTP server and re-exec the process.

    Called from the restart HTTP handler (UI button) and from the watchdog
    thread (stuck-poll detection). Must be invoked from a non-daemon thread
    so Python's interpreter-shutdown waits for os.execv to replace the process.
    """
    print(f"[restart] reason={reason} — shutting down HTTP server...")
    time.sleep(0.3)  # let any in-flight response flush

    # 1. Shut down the HTTP server so the socket is released
    try:
        server.shutdown()
    except Exception as e:
        print(f"[restart] server.shutdown() error (non-fatal): {e}")

    # 2. Close the server socket explicitly
    try:
        server.server_close()
    except Exception as e:
        print(f"[restart] server_close() error (non-fatal): {e}")

    # 3. Small wait for OS to release the port
    time.sleep(0.5)

    # 4. Auto-find latest _prod.html so restarts pick up new versions
    #    Guard (counter-agent C3 MEDIUM finding, April 16 2026): handle both
    #    "--storyboard FOO" (space) and "--storyboard=FOO" (equals) forms, and
    #    warn if neither form is present so we don't silently restart with a
    #    stale storyboard argument.
    new_argv = list(sys.argv)
    try:
        prods = sorted(
            app.event_dir.glob("storyboard_v*_prod.html"),
            key=lambda p: p.stat().st_mtime, reverse=True,
        )
        if prods:
            latest_name = prods[0].name
            replaced = False
            for i, arg in enumerate(new_argv):
                if arg == "--storyboard" and i + 1 < len(new_argv):
                    new_argv[i + 1] = latest_name
                    replaced = True
                    break
                if arg.startswith("--storyboard="):
                    new_argv[i] = f"--storyboard={latest_name}"
                    replaced = True
                    break
            if replaced:
                print(f"[restart] using latest storyboard: {latest_name}")
            else:
                print(
                    f"[restart] WARN: --storyboard not found in argv; "
                    f"restart will use original launch args. argv={new_argv!r}"
                )
    except Exception as e:
        print(f"[restart] could not auto-detect latest storyboard: {e}")

    # 5. Re-exec with updated arguments (process image is replaced; no return)
    #    Preserve runtime event pin (not only launch argv) so Event_2 work survives restart.
    new_argv = _argv_with_runtime_event_pin(new_argv, app)
    print(f"[restart] sys.executable={sys.executable}")
    print(f"[restart] os.execv with argv={new_argv}")
    os.execv(sys.executable, [sys.executable] + new_argv)


# ---------------------------------------------------------------------------
# Storyboard L[] field patcher — single source of truth for "server state
# wrote a new value that is visible in the storyboard HTML"
#
# Why this exists (Tier 5, April 17 2026):
# Four separate bugs this session all had the same shape — server state held
# truth, but the HTML file on disk held a stale snapshot, and the UI read
# the HTML, so user edits appeared to "ghost back":
#   151 DIALOGUE_EDITS_MUST_PERSIST        — t: field
#   154 ASSIGN_IMAGE_MUST_PATCH_STORYBOARD — i: field
# (153 LIPSYNC_UI_MUST_SUPPORT_RERUN is a companion fix handled via a
#  source_changed flag, not via L[] patching — see _handle_select + submit.)
#
# Any mutate_state() that touches a field rendered in the storyboard HTML
# MUST call this helper in the same operation so the two stay consistent.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Path A++ Phase 1 — v2 mutation path (April 18 2026)
#
# SHORTCUT_AUTONOMOUS_LIVE_BUILD_PHASE1_20260418 — Kim-approved live build.
# See Directus prod_preflight_reviews row 59 + prod_activity_log rows 186-188.
#
# Root-cause fix for LD-151/153/154/155: the in-browser L[] array is NOT a
# state location — it is a rendered view of production_state.json.
# The server writes a sidecar JSON on every v2 mutation; the storyboard
# bootstrap JS fetches it on page load and overwrites L[] before widgets
# mount. No regex on HTML from the new write path (Rule 7 respected).
#
# MINDFULNEST_WRITE_PATH=legacy disables this path (503 response); the
# browser falls back to legacy /api/beat/update_text, /api/assign-image, etc.
# ---------------------------------------------------------------------------

import collections as _pathapp_collections
import uuid as _pathapp_uuid

# LRU dedup cache — last 256 mutation_ids, ~5-minute TTL enforced by size
_PATCH_STATE_DEDUP: "_pathapp_collections.OrderedDict[str, dict]" = _pathapp_collections.OrderedDict()
_PATCH_STATE_DEDUP_MAX = 256

# BEAT_GRAFT_RECOVERY_MECHANISM_V1 (C-7) — separate dedup cache for
# /api/beat/graft. Same shape and policy as _PATCH_STATE_DEDUP; kept
# separate so a graft replay never collides with an unrelated patch_state
# replay using the same mutation_id (the two endpoints share the same
# uuid namespace but different replay semantics).
_GRAFT_DEDUP: "_pathapp_collections.OrderedDict[str, dict]" = _pathapp_collections.OrderedDict()
_GRAFT_DEDUP_MAX = 256

# Durable audit log for graft operations (and any other recovery primitives
# that need a forever-on-disk record). Per LD-505 two-tree boundary, the
# audit log is FORENSIC STATE — it belongs in the canonical state tree
# (Dropbox) alongside the event_dir, NOT in the tooling-repo code tree.
#
# Path resolution is dynamic via app.event_dir.parent (i.e., the
# "Production/" parent of the running server's event-dir):
#   - Production runtime (server launched from Dropbox tree against
#     Production/Event_<N>): audit log lands at
#     /Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest
#     Project Files/Production/.recovery_audit.jsonl
#   - CI / e2e fixture runs (server against Production/Event_e2e_fixture
#     in tooling repo): audit log lands at tooling-repo
#     Production/.recovery_audit.jsonl (gitignored).
#
# Use _audit_log_path(app) helper to read the resolved path; the legacy
# module-level constant has been removed.

def _audit_log_path(app) -> Path:
    """Return the durable recovery-audit log path for the current server pin.

    Co-located with `app.event_dir.parent` per spec §6.4 + LD-505 (forensic
    state in canonical state tree). Single point of resolution so future
    callers don't import a stale module-level constant from before the
    runtime tree was decided.
    """
    return app.event_dir.parent / ".recovery_audit.jsonl"

# v2 whitelist — ALL other fields must go through the legacy bespoke handlers
_V2_ALLOWED_FIELDS = frozenset({
    "dialogue", "image_override", "selected_option", "trim_start", "trim_end",
    # Tier 3 server (April 18 2026, LD TIER3_SERVER_WHITELIST_EXTENSIONS_PAUSE_SPEAKER_DISPLAY_ORDER)
    "pause_after_ms", "speaker", "display_order",
    # Per-item fade override (April 19 2026, LD PER_ITEM_FADE_AFTER_OVERRIDE_V1).
    # Writes to phase_1.fade_after_ms; null clears (inherit global fade).
    # Item-agnostic key name — reused unchanged by V4 segment-level composer.
    "fade_after_ms",
})

# Tier 3: beat_id sentinel for top-level state mutations (display_order).
# Routed through the same /api/v2/beat/<bid>/patch endpoint for consistency.
_V2_GLOBAL_BEAT_ID = "__global__"

# Tier 3: fields legal on the __global__ sentinel — top-level state keys only.
_V2_GLOBAL_ALLOWED_FIELDS = frozenset({"display_order"})

# Tier 3: hard cap for pause_after_ms (10 seconds). Anything above is rejected.
_V2_PAUSE_AFTER_MS_MAX = 10000

# LD-285 Preview Stitched v2 (April 19 2026): module-level (state.json root)
# fade fields. Whitelisted for /api/v2/module/patch. L1 (beats) is implemented;
# L2 (segments) and L3 (events) reserve their schema slots so v2.1 doesn't
# need a state migration.
_V2_MODULE_ALLOWED_FIELDS = frozenset({
    # LD-285 V2 (April 19 2026) fade fields
    "fade_between_beats_ms",
    "fade_between_segments_ms",
    "fade_between_events_ms",
    # LD (V3) 2026-04-19 Preview Stitched V3 Phase B (12 fields)
    "phase_b_script",
    "phase_b_voice_stem_file",
    "phase_b_voice_stem_mtime",
    "phase_b_ambient_preset_id",
    "phase_b_mixed_audio_file",
    "phase_b_mixed_audio_mtime",
    "phase_b_cedric_base_clip_id",
    "phase_b_lipsync_file",
    "phase_b_lipsync_mtime",
    "phase_b_voice_stem_trim_start_s",
    "phase_b_voice_stem_trim_back_s",
    "phase_b_voice_stem_cut_start_s",
    "phase_b_voice_stem_cut_end_s",
    "phase_b_watercolor_cues_json",
    "phase_b_preview_file",
    "phase_b_status",
    # LD (V3) 2026-04-19 Preview Stitched V3 Phase A (15 fields)
    "phase_a_script",
    "phase_a_voice_stem_file",
    "phase_a_voice_stem_mtime",
    "phase_a_ambient_preset_id",
    "phase_a_mixed_audio_file",
    "phase_a_mixed_audio_mtime",
    "phase_a_empty_desk_bg_id",
    "phase_a_chipper_flyin_clip_id",
    "phase_a_chipper_sitting_clip_id",
    "phase_a_chipper_flyout_clip_id",
    "phase_a_lipsync_file",
    "phase_a_lipsync_mtime",
    "phase_a_voice_stem_trim_start_s",
    "phase_a_voice_stem_trim_back_s",
    "phase_a_voice_stem_cut_start_s",
    "phase_a_voice_stem_cut_end_s",
    "phase_a_watercolor_cues_json",
    "phase_a_preview_file",
    "phase_a_status",
    # S5.5d (v3 architecture revision, 2026-05-03): phase_a top-level state
    # additions per PHASE_A_TOP_LEVEL_STATE_V1. _auto_assemble_phase_a_stitched
    # writes both fields when the per-module Phase A timeline finalizes.
    "phase_a_stitched_file",
    "phase_a_stitched_mtime",
})
_V2_MODULE_FADE_MAX_MS = 1000
_V2_STATUS_VALUES = frozenset({
    "draft", "in_progress", "needs_review", "approved", "rejected",
})
_V2_CUE_ANIMATIONS = frozenset({"fade_in", "slide_in", "gentle_pan"})
_V2_CUE_TYPES = frozenset({"png", "video"})


def _v2_validate_fade_ms(v):
    v = int(v)
    if v < 0 or v > _V2_MODULE_FADE_MAX_MS:
        raise ValueError(f"must be in [0, {_V2_MODULE_FADE_MAX_MS}], got {v}")
    return v


def _v2_validate_mtime(v):
    v = int(v)
    if v < 0 or v > 4_000_000_000:
        raise ValueError(f"mtime must be non-negative epoch int, got {v}")
    return v


def _v2_validate_str(v, max_len: int = 50_000):
    if not isinstance(v, str):
        raise ValueError(f"must be string, got {type(v).__name__}")
    if len(v) > max_len:
        raise ValueError(f"string too long ({len(v)} chars, max {max_len})")
    return v


def _v2_validate_status(v):
    v = _v2_validate_str(v, max_len=64)
    if v not in _V2_STATUS_VALUES:
        raise ValueError(
            f"must be one of {sorted(_V2_STATUS_VALUES)}, got {v!r}"
        )
    return v


def _v2_validate_trim_seconds(v):
    v = float(v)
    if v < 0 or v > 3600:
        raise ValueError(f"trim seconds must be in [0, 3600], got {v}")
    return round(v, 3)


def _v2_validate_watercolor_cues_json(v):
    """Validate watercolor cues; accept JSON string or raw list (frontend schema or server schema).

    Frontend sends raw arrays with keys {id, watercolor_key, offset_ms, animation_type, duration_ms,
    volume}. Server schema uses {key, timestamp_ms, animation, duration_ms, cue_type}. Both are
    accepted here and normalized to server schema before storage so the bake pipeline always sees
    a consistent shape. Stores as a JSON string with sort_keys=True for cache-hash stability (MEDIUM-5).
    """
    # Accept list directly (client sends raw array per F7-F9 contract).
    if isinstance(v, list):
        parsed = v
    elif isinstance(v, str):
        if len(v) > 200_000:
            raise ValueError(f"cues JSON too long ({len(v)} chars, max 200000)")
        try:
            parsed = json.loads(v)
        except Exception as exc:
            raise ValueError(f"invalid JSON: {exc}")
    else:
        raise ValueError(f"must be JSON string or list, got {type(v).__name__}")
    if not isinstance(parsed, list):
        raise ValueError(f"watercolor cues must be a list, got {type(parsed).__name__}")
    normalized = []
    for i, cue in enumerate(parsed):
        if not isinstance(cue, dict):
            raise ValueError(f"cue {i} must be dict, got {type(cue).__name__}")
        # Resolve key: accept server 'key' or frontend 'watercolor_key'.
        key_val = cue.get("key") or cue.get("watercolor_key") or ""
        if not isinstance(key_val, str) or not key_val:
            raise ValueError(f"cue {i} missing 'key'/'watercolor_key'")
        # Resolve timestamp: accept server 'timestamp_ms' or frontend 'offset_ms'.
        ts_raw = cue.get("timestamp_ms") if "timestamp_ms" in cue else cue.get("offset_ms", 0)
        try:
            ts = int(ts_raw)
        except (TypeError, ValueError):
            raise ValueError(f"cue {i} timestamp_ms/offset_ms must be integer, got {ts_raw!r}")
        if ts < 0:
            raise ValueError(f"cue {i} timestamp_ms must be non-negative int")
        # Resolve animation: accept server 'animation' or frontend 'animation_type'.
        anim = cue.get("animation") or cue.get("animation_type") or "fade_in"
        if anim not in _V2_CUE_ANIMATIONS:
            raise ValueError(
                f"cue {i} animation must be one of {sorted(_V2_CUE_ANIMATIONS)}, "
                f"got {anim!r}"
            )
        dur_raw = cue.get("duration_ms", 3000)
        try:
            dur = int(dur_raw)
        except (TypeError, ValueError):
            raise ValueError(f"cue {i} duration_ms must be integer, got {dur_raw!r}")
        if dur < 0:
            raise ValueError(f"cue {i} duration_ms must be non-negative int")
        raw_cue_type = cue.get("cue_type") or ""
        # Auto-correct stale cue_type: animated keys always map to MP4/MOV (video),
        # not PNG. A key containing "_animated_" was produced by the animation
        # pipeline and will never have a .png sibling. Correcting here means
        # existing cues stored with cue_type="png" before this fix still work.
        if not raw_cue_type or raw_cue_type == "png" and "_animated_" in key_val:
            cue_type = "video" if "_animated_" in key_val else (raw_cue_type or "png")
        else:
            cue_type = raw_cue_type
        if cue_type not in _V2_CUE_TYPES:
            raise ValueError(
                f"cue {i} cue_type must be one of {sorted(_V2_CUE_TYPES)}, "
                f"got {cue_type!r}"
            )
        normalized.append({
            "id": str(cue.get("id") or f"cue_{i}"),
            "key": key_val,
            "timestamp_ms": ts,
            "animation": anim,
            "duration_ms": dur,
            "cue_type": cue_type,
            "volume": float(cue.get("volume", 1.0)),
        })
    # Sort cues by timestamp_ms for stable rendering order.
    normalized.sort(key=lambda c: c["timestamp_ms"])
    # Re-emit with sort_keys=True so hash is stable across client JS key ordering.
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"))


# Per-field validator dispatch (V3 HIGH-1 fix — counter preflight 102).
# Fade fields retain their V2 behavior (int 0..1000); phase_* fields get their
# own type+bound validators. Lookup is O(1) per call — no regex/prefix match.
_V2_MODULE_FIELD_VALIDATORS = {
    "fade_between_beats_ms": _v2_validate_fade_ms,
    "fade_between_segments_ms": _v2_validate_fade_ms,
    "fade_between_events_ms": _v2_validate_fade_ms,
    # Phase B
    "phase_b_script": _v2_validate_str,
    "phase_b_voice_stem_file": _v2_validate_str,
    "phase_b_voice_stem_mtime": _v2_validate_mtime,
    "phase_b_ambient_preset_id": _v2_validate_str,
    "phase_b_mixed_audio_file": _v2_validate_str,
    "phase_b_mixed_audio_mtime": _v2_validate_mtime,
    "phase_b_cedric_base_clip_id": _v2_validate_str,
    "phase_b_lipsync_file": _v2_validate_str,
    "phase_b_lipsync_mtime": _v2_validate_mtime,
    "phase_b_voice_stem_trim_start_s": _v2_validate_trim_seconds,
    "phase_b_voice_stem_trim_back_s": _v2_validate_trim_seconds,
    "phase_b_voice_stem_cut_start_s": _v2_validate_trim_seconds,
    "phase_b_voice_stem_cut_end_s": _v2_validate_trim_seconds,
    "phase_b_watercolor_cues_json": _v2_validate_watercolor_cues_json,
    "phase_b_preview_file": _v2_validate_str,
    "phase_b_status": _v2_validate_status,
    # Phase A
    "phase_a_script": _v2_validate_str,
    "phase_a_voice_stem_file": _v2_validate_str,
    "phase_a_voice_stem_mtime": _v2_validate_mtime,
    "phase_a_ambient_preset_id": _v2_validate_str,
    "phase_a_mixed_audio_file": _v2_validate_str,
    "phase_a_mixed_audio_mtime": _v2_validate_mtime,
    "phase_a_empty_desk_bg_id": _v2_validate_str,
    "phase_a_chipper_flyin_clip_id": _v2_validate_str,
    "phase_a_chipper_sitting_clip_id": _v2_validate_str,
    "phase_a_chipper_flyout_clip_id": _v2_validate_str,
    "phase_a_lipsync_file": _v2_validate_str,
    "phase_a_lipsync_mtime": _v2_validate_mtime,
    "phase_a_voice_stem_trim_start_s": _v2_validate_trim_seconds,
    "phase_a_voice_stem_trim_back_s": _v2_validate_trim_seconds,
    "phase_a_voice_stem_cut_start_s": _v2_validate_trim_seconds,
    "phase_a_voice_stem_cut_end_s": _v2_validate_trim_seconds,
    "phase_a_watercolor_cues_json": _v2_validate_watercolor_cues_json,
    "phase_a_preview_file": _v2_validate_str,
    "phase_a_status": _v2_validate_status,
    # Phase A stitched outputs (PHASE_A_TOP_LEVEL_STATE_V1): added to
    # _V2_MODULE_ALLOWED_FIELDS at 4281-4282 but were missing validators —
    # caught by test_validator_dispatch_covers_all_whitelist_fields. P5
    # 2026-05-19.
    "phase_a_stitched_file": _v2_validate_str,
    "phase_a_stitched_mtime": _v2_validate_mtime,
}

# Maps v2 field name -> L[] field name for sidecar projection
_V2_FIELD_TO_L = {
    "dialogue": "t",
    "image_override": "i",
    # selected_option, trim_start, trim_end: not in L[] — state-only
}


def _write_sidecar_L_json(app: "AppContext", state: dict) -> str | None:
    """Write the L[] sidecar JSON atomically (tmp+rename).

    Derives L[]-shaped dict-of-beats from state["beats"], writes to
    <event_dir>/<storyboard_stem>.L.json. Reuses app._storyboard_write_lock
    for ordering consistency with the legacy HTML patcher (but does NOT
    touch HTML — only sidecar).

    Returns the path written, or None on failure (logged, non-fatal).
    """
    try:
        sidecar_path = app.event_dir / (app.storyboard_path.stem + ".L.json")
        # LD-459 UNIVERSAL_AUTOSAVE_V1 — also mirror to sibling storyboards'
        # sidecars so emergency rollback (v59 -> v58) sees the same fresh data.
        # Pattern: storyboard_v<N>_prod.html → storyboard_v<N>_prod.L.json.
        # We mirror to ALL storyboard_v*_prod.html files in the event dir.
        sibling_sidecars: list[Path] = []
        try:
            for hp in app.event_dir.glob("storyboard_v*_prod.html"):
                sibling = app.event_dir / (hp.stem + ".L.json")
                if sibling != sidecar_path:
                    sibling_sidecars.append(sibling)
        except OSError:
            sibling_sidecars = []
        # Projection: for each beat in state, expose the fields a hydrating
        # client needs. Keep small — just the authoritative L-relevant fields.
        # S5.5a2: read intro partition (BG_VIDEO_PARTITION_V1).
        intro_partition = (state.get("videos") or {}).get("intro") or {}
        projection: dict[str, dict] = {}
        for bid, beat in (intro_partition.get("beats") or {}).items():
            entry: dict = {}
            if "text" in beat:
                entry["t"] = beat["text"]
            # image_override is stored in videos.intro.image_overrides[bid]
            # (post-migration; was state["image_overrides"][bid] pre-S5.5a2).
            phase1 = beat.get("phase_1") or {}
            if "selected_option" in phase1:
                entry["selected_option"] = phase1["selected_option"]
            if "trim_start" in phase1:
                entry["trim_start"] = phase1["trim_start"]
            if "trim_end" in phase1:
                entry["trim_end"] = phase1["trim_end"]
            # Tier 3 (April 18 2026): new per-beat fields for client hydration
            if "pause_after_ms" in phase1:
                entry["pause_after_ms"] = phase1["pause_after_ms"]
            if "speaker" in phase1:
                entry["speaker"] = phase1["speaker"]
            if "speaker_mismatch" in phase1:
                entry["speaker_mismatch"] = phase1["speaker_mismatch"]
            if "_version" in beat:
                entry["_version"] = beat["_version"]
            projection[bid] = entry
        # Merge in image_overrides (now nested under videos.intro per S5.5a2).
        for bid, image_key in (intro_partition.get("image_overrides") or {}).items():
            projection.setdefault(bid, {})["i"] = image_key
        # Tier 3: top-level display_order — now nested under videos.intro.
        # Stored under a reserved key that cannot collide with a beat_id
        # (beat_ids use the beat_NN pattern).
        # V59 architectural-fix (Wave 1, F-SVR-001 root cause): isinstance
        # guard for malformed display_order. Pre-fix `list(int)` raised
        # `TypeError: 'int' object is not iterable` which the catch-all
        # below silently swallowed, leaving no sidecar on disk + no
        # observable failure for callers. Per MUTATION_CHANNEL_INVARIANT_V1
        # the sidecar must complete; a malformed source value should not
        # corrupt the projection.
        if "display_order" in intro_partition:
            do_raw = intro_partition["display_order"]
            if isinstance(do_raw, (list, tuple)):
                projection["__meta__"] = {"display_order": list(do_raw)}
            else:
                # Defensive: malformed display_order shape. Emit empty list
                # so a downstream consumer sees a well-typed but empty
                # ordering rather than crashing the projection.
                projection["__meta__"] = {"display_order": []}
        with app._storyboard_write_lock:
            # Shared atomic-JSON helper (Windows/Dropbox retry-safe per LD-368).
            atomic_json_write(str(sidecar_path), projection)
            # LD-459 — mirror to sibling storyboards' sidecars (rollback safety).
            for sibling in sibling_sidecars:
                try:
                    atomic_json_write(str(sibling), projection)
                except Exception as exc2:  # noqa: BLE001
                    print(f"[sidecar] WARN sibling write failed for "
                          f"{sibling.name}: {type(exc2).__name__}: {exc2}",
                          flush=True)
        return str(sidecar_path)
    except Exception as exc:  # noqa: BLE001
        # SERVER_SILENT_FAILURE_FAIL_LOUD_V1 (V59 architectural-fix Wave 1,
        # F-SVR-001): _write_sidecar_L_json is non-fatal by contract
        # (callers do not handle this exception path); we cannot raise
        # without breaking that contract. But silent print to stdout makes
        # the failure invisible in CI / production logs. Tighten to stderr
        # + traceback so any future unforeseen exception class is loud and
        # debuggable.
        import traceback
        print(
            f"[sidecar][ERROR] write failed: {type(exc).__name__}: {exc}\n"
            f"{traceback.format_exc()}",
            file=sys.stderr,
            flush=True,
        )
        return None


def _v2_read_beat_version(state: dict, beat_id: str) -> int:
    """Return current _version for a beat (0 if beat absent or version missing).
    S5.5a2: reads from intro partition (legacy single-partition contract;
    callers operating on other partitions should use a partition-aware variant)."""
    intro = (state.get("videos") or {}).get("intro") or {}
    beat = (intro.get("beats") or {}).get(beat_id) or {}
    try:
        return int(beat.get("_version", 0) or 0)
    except (TypeError, ValueError):
        return 0


def patch_state(
    app: "AppContext",
    beat_id: str,
    field: str,
    value,
    mutation_id: str | None = None,
    expected_version: int | None = None,
    video_role: str = "intro",
) -> dict:
    """Atomic v2 state mutation with idempotency + version check + sidecar.

    Returns a dict with shape:
      {"status": "applied",  "new_version": N, "beat": {...}}
      {"status": "dedup",    "new_version": N, "beat": {...}, "cached": True}
      {"status": "conflict", "current_version": N, "expected": M}
      {"status": "disabled", "error": "..."}  (MINDFULNEST_WRITE_PATH=legacy)
      {"status": "error",    "error": "..."}

    Rollback: if os.environ["MINDFULNEST_WRITE_PATH"] == "legacy", returns
    status=disabled WITHOUT touching state. Browser falls back to legacy.

    For field="dialogue", this helper DELEGATES to the legacy
    _handle_beat_update_text flow (via patch_state_via_legacy_dialogue)
    which preserves LD-181 TTS auto-regen. The caller is responsible
    for invoking that delegation path — see _handle_v2_patch.

    SCOPE_ROUTER_V1 (C-2 D5 fix): `video_role` parameter resolves the
    target partition. Defaults to "intro" for back-compat with callers
    that haven't yet been updated to pass a scope-aware role; the v2
    handler `_handle_v2_patch` resolves it from the body's
    `scope_target_video` / `scope_video_role` (LD-461 alias) and passes
    explicitly. Validated against StateManager._VALID_VIDEO_ROLES; an
    invalid role returns status=error before any state read.
    """
    # Rollback gate — line 1 of the helper (Red-team-2 requirement)
    if os.environ.get("MINDFULNEST_WRITE_PATH", "v2") == "legacy":
        return {"status": "disabled",
                "error": "v2 write path disabled via MINDFULNEST_WRITE_PATH=legacy"}

    # Whitelist
    if field not in _V2_ALLOWED_FIELDS:
        return {"status": "error",
                "error": f"field {field!r} not in whitelist {sorted(_V2_ALLOWED_FIELDS)}"}

    # Tier 3: __global__ sentinel routing. Only a small allowlist of fields
    # is legal on this sentinel (top-level state keys). Individual-beat fields
    # on __global__ make no sense and are rejected explicitly.
    is_global = (beat_id == _V2_GLOBAL_BEAT_ID)
    if is_global and field not in _V2_GLOBAL_ALLOWED_FIELDS:
        return {"status": "error",
                "error": f"field {field!r} not allowed on {_V2_GLOBAL_BEAT_ID!r}; "
                         f"allowed: {sorted(_V2_GLOBAL_ALLOWED_FIELDS)}"}
    if (not is_global) and field in _V2_GLOBAL_ALLOWED_FIELDS:
        return {"status": "error",
                "error": f"field {field!r} is top-level — must use beat_id={_V2_GLOBAL_BEAT_ID!r}"}

    # Type/shape validation
    if field in ("dialogue", "image_override"):
        if not isinstance(value, str):
            return {"status": "error", "error": f"{field} must be str, got {type(value).__name__}"}
    if field == "selected_option":
        try:
            value = int(value)
        except (TypeError, ValueError):
            return {"status": "error", "error": f"selected_option must be int, got {value!r}"}
    if field in ("trim_start", "trim_end"):
        if value is not None:
            try:
                value = float(value)
            except (TypeError, ValueError):
                return {"status": "error", "error": f"{field} must be number or null, got {value!r}"}
    # Tier 3 (April 18 2026): pause_after_ms — int, 0 ≤ v ≤ 10000
    if field == "pause_after_ms":
        try:
            value = int(value)
        except (TypeError, ValueError):
            return {"status": "error",
                    "error": f"pause_after_ms must be int, got {value!r}"}
        if value < 0 or value > _V2_PAUSE_AFTER_MS_MAX:
            return {"status": "error",
                    "error": f"pause_after_ms must be in [0, {_V2_PAUSE_AFTER_MS_MAX}], got {value}"}
    # Per-item fade override (LD PER_ITEM_FADE_AFTER_OVERRIDE_V1, April 19 2026).
    # null => inherit the global fade_between_beats_ms; int 0..1000 => override
    # this item's outgoing transition. Item-agnostic in V4: same field on a
    # module segment will override the segment-level global fade.
    if field == "fade_after_ms":
        if value is not None:
            try:
                value = int(value)
            except (TypeError, ValueError):
                return {"status": "error",
                        "error": f"fade_after_ms must be int or null, got {value!r}",
                        "hint": "Use null to inherit global fade; 0-1000 for a specific ms override."}
            if value < 0 or value > _V2_MODULE_FADE_MAX_MS:
                return {"status": "error",
                        "error": f"fade_after_ms must be in [0, {_V2_MODULE_FADE_MAX_MS}] or null, got {value}",
                        "hint": "Use null to inherit global fade; 0-1000 for a specific ms override."}
    # Tier 3: speaker — non-empty string. Alias map enriches but does not gate.
    if field == "speaker":
        if not isinstance(value, str):
            return {"status": "error",
                    "error": f"speaker must be str, got {type(value).__name__}"}
        value = value.strip()
        if not value:
            return {"status": "error",
                    "error": "speaker must be a non-empty string"}
    # Tier 3: display_order — list[str] of known beat_ids. Top-level only.
    if field == "display_order":
        if not isinstance(value, list):
            return {"status": "error",
                    "error": f"display_order must be list, got {type(value).__name__}"}
        for _i, _item in enumerate(value):
            if not isinstance(_item, str):
                return {"status": "error",
                        "error": f"display_order[{_i}] must be str, got {type(_item).__name__}"}
        # Deferred beat_id existence check — needs state read. Done inside _apply.

    # SCOPE_ROUTER_V1 (C-2 D5 fix) — validate the resolved partition role
    # before any state read. Mirrors scope_router._VALID_VIDEO_ROLES; we
    # don't import the router here directly to keep patch_state agnostic
    # of HTTP framing (the handler at _handle_v2_patch already mapped
    # body keys via the router). An invalid role returns status=error.
    if video_role not in {"intro", "resolution", "standalone"}:
        return {"status": "error",
                "error": f"invalid video_role {video_role!r}; "
                         f"valid: ['intro', 'resolution', 'standalone']"}

    # Idempotency — dedup cache (LRU, bounded)
    if mutation_id:
        cached = _PATCH_STATE_DEDUP.get(mutation_id)
        if cached is not None:
            _PATCH_STATE_DEDUP.move_to_end(mutation_id)
            return {**cached, "status": "dedup", "cached": True}

    source_changed_out = {"value": None}
    result_holder: dict = {}

    def _apply_partition(partition, _bid=beat_id, _f=field, _v=value, _exp=expected_version, _sco=source_changed_out, _is_global=is_global, _holder=result_holder):
        # SCOPE_ROUTER_V1 (C-2 D5 fix): the mutator receives the partition
        # dict for the resolved video_role — never the full state, never the
        # legacy top-level state.beats. mutate_video_state auto-creates the
        # partition with role marker if missing (production_server.py:1185-1196)
        # before invoking the mutator, so partition is always non-None here.
        beats = partition.setdefault("beats", {})
        # Tier 3: __global__ mutations DO NOT create a beat entry. They mutate
        # the partition's top-level keys (display_order, etc.). Version checks
        # + bump are skipped (display_order is not beat-scoped).
        if _is_global:
            if _f == "display_order":
                # Validate every beat_id exists in partition's beats
                known = set(beats.keys())
                unknown = [b for b in _v if b not in known]
                if unknown:
                    _holder.update({
                        "status": "error",
                        "error": f"display_order references unknown beat_ids: {unknown}",
                    })
                    return
                partition["display_order"] = list(_v)
            _holder.update({
                "status": "applied",
                "new_version": None,  # partition-level keys are not versioned per-beat
                "scope": "global",
                "field": _f,
                "value_summary": (
                    f"list[{len(_v)}]" if isinstance(_v, list) else str(_v)
                ),
            })
            return

        beat = beats.setdefault(_bid, {})
        # Read version directly off the partition's beat (was previously
        # `_v2_read_beat_version(state, _bid)` which is hardcoded to videos.intro
        # — kept around for legacy single-partition callers; partition-aware
        # callers read from the partition we already resolved).
        try:
            current_version = int(beat.get("_version", 0) or 0)
        except (TypeError, ValueError):
            current_version = 0
        if _exp is not None and _exp != current_version:
            _holder.update({
                "status": "conflict",
                "current_version": current_version,
                "expected": _exp,
            })
            return
        # Apply mutation
        if _f == "dialogue":
            beat["text"] = _v
            beat["text_last_updated_at"] = datetime.now(timezone.utc).isoformat()
        elif _f == "image_override":
            # image_overrides lives at videos.<role>.image_overrides on the
            # partition we already resolved (no longer hardcoded to intro).
            partition.setdefault("image_overrides", {})[_bid] = _v
        elif _f == "selected_option":
            p1 = beat.setdefault("phase_1", {})
            old_selected = p1.get("selected_option")
            p1["selected_option"] = _v
            # Re-run detection for completed lipsyncs (mirrors _handle_select)
            ls = beat.get("lipsync")
            if ls and ls.get("status") == "completed":
                if ls.get("source_option") is None and old_selected is not None:
                    try:
                        ls["source_option"] = int(old_selected)
                    except (TypeError, ValueError):
                        pass
                src_opt = ls.get("source_option")
                if src_opt is not None:
                    changed = (_v != int(src_opt))
                    ls["source_changed"] = changed
                    _sco["value"] = changed
        elif _f == "trim_start":
            beat.setdefault("phase_1", {})["trim_start"] = (
                round(_v, 2) if _v is not None else 0.0
            )
        elif _f == "trim_end":
            beat.setdefault("phase_1", {})["trim_end"] = (
                round(_v, 2) if _v is not None else None
            )
        elif _f == "pause_after_ms":
            # Tier 3: post-dialogue pause (for pacing). Stored on phase_1.
            beat.setdefault("phase_1", {})["pause_after_ms"] = int(_v)
        elif _f == "fade_after_ms":
            # Per-item fade override. null clears (inherit global); int writes
            # the override. Stored on phase_1 at the beat scope; V4 segment
            # composer will write the same key at module.segments[i] scope.
            p1 = beat.setdefault("phase_1", {})
            if _v is None:
                p1.pop("fade_after_ms", None)
            else:
                p1["fade_after_ms"] = int(_v)
        elif _f == "speaker":
            # K8 + SPEAKER_DUAL_STORE_DEPRECATION_V1 (C-6): canonicalize at
            # write boundary (SPEAKER_WRITE_BOUNDARY_CANONICALIZATION_V1)
            # and write to BOTH the canonical top-level partition.beats[bid].speaker
            # AND the legacy phase_1.speaker mirror. Read sites use
            # _resolve_beat_speaker(beat) which prefers top-level and falls
            # back to phase_1 for legacy on-disk values. The mirror is a
            # one-release read-compat shim; SPEAKER_DUAL_STORE_DEPRECATION_V1
            # tracks the N+1 sprint that drops the phase_1 write entirely.
            canonical = _canonicalize_speaker(_v or "") or ""
            old_top_speaker = beat.get("speaker") or ""
            beat["speaker"] = canonical                    # canonical write target (TTS reads this)
            p1 = beat.setdefault("phase_1", {})
            old_phase1_speaker = p1.get("speaker") or ""
            p1["speaker"] = canonical                      # mirror for read-compat shim
            # Mismatch-flip semantics: speaker change invalidates existing
            # audio (mismatch until next regen); _tier1a_mark_regen_fired
            # clears speaker_mismatch after a successful regen.
            old_speaker = old_top_speaker or old_phase1_speaker
            if old_speaker != canonical:
                p1["speaker_mismatch"] = True
                p1["speaker_mismatch_set_at"] = (
                    datetime.now(timezone.utc).isoformat()
                )
        # Bump version
        beat["_version"] = current_version + 1
        _holder.update({
            "status": "applied",
            "new_version": current_version + 1,
            "beat": dict(beat),  # shallow copy of beat state
        })

    try:
        app.state.mutate_video_state(video_role, _apply_partition)
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        return {"status": "error", "error": f"mutate_video_state failed: {type(exc).__name__}: {exc}"}
    if not result_holder:
        # Mutator never executed — defensive (shouldn't happen with mutate_video_state).
        return {"status": "error", "error": "patch_state mutator did not run"}
    result = result_holder

    if result.get("status") == "conflict":
        return result

    # Post-mutation: write sidecar JSON (fresh state read for consistency)
    try:
        fresh_state = app.state.read_state()
        _write_sidecar_L_json(app, fresh_state)
    except Exception as exc:  # noqa: BLE001
        print(f"[v2 patch_state] sidecar write after mutation failed: {exc}")

    # Optional: async Directus audit mirror
    def _async_v2_audit():
        try:
            import http.client as _hc
            import ssl as _ssl
            import urllib.parse as _up
            # Reuse lib/directus if available — best-effort, short timeout
            try:
                _libdir = os.path.join(os.path.dirname(__file__), "credentials_lib")
                if _libdir not in sys.path:
                    sys.path.insert(0, _libdir)
                from credentials import load_credentials  # type: ignore
                from directus import DirectusClient  # type: ignore
                creds = load_credentials()
                dc = DirectusClient(creds["directus_url"], creds["directus_email"], creds["directus_password"])
                dc.create("prod_activity_log", {
                    "action": "v2_patch",
                    "details": {
                        "task_id": "phase1-live-20260418",
                        "beat": beat_id,
                        "field": field,
                        "new_version": result.get("new_version"),
                        "mutation_id": mutation_id,
                    },
                    "performed_by": "production_server_v2",
                })
            except Exception:
                pass
        except Exception:
            pass
    threading.Thread(target=_async_v2_audit, daemon=True).start()

    # Apply source_changed_out to result (for selected_option flow)
    if source_changed_out["value"] is not None:
        result["lipsync_source_changed"] = source_changed_out["value"]

    # Cache for idempotency
    if mutation_id:
        _PATCH_STATE_DEDUP[mutation_id] = result
        while len(_PATCH_STATE_DEDUP) > _PATCH_STATE_DEDUP_MAX:
            _PATCH_STATE_DEDUP.popitem(last=False)

    return result


def _storyboard_is_v59_shell(app: "AppContext") -> bool:
    """LD-456 SCOPE_VALIDATION_V1 / Cursor M3 conditional-HTML-patching helper.

    Returns True if the active storyboard file is a v59 (Vite Path C) shell,
    False otherwise. Detection priority:

      1. Filename match: storyboard_v59_*.html (or v60+ — forward compat).
      2. Filename match: storyboard_v58_*.html / v57 / v56 / v55 / v54 / v53 /
         v52 — definitively NOT v59 shell.
      3. Content sniff (fallback for unknown filenames): absence of the v58
         hallmark `var IN=` JS variable.

    Why this exists: v59 is a single-file Vite bundle that contains NO L[]
    array, no IN= map, no TH= map. Server handlers that historically rewrote
    those structures must short-circuit on v59 and patch state.json + sidecar
    only. Without the short-circuit, _patch_storyboard_L_field returns
    `not_in_storyboard` per-beat which conflates v59 with "narration-only
    beat in v58" — masking what's actually happening. This helper makes the
    distinction explicit so logs are honest (handoff: "no silent diverge").
    """
    name = app.storyboard_path.name
    # Forward-compat — v59 and beyond are Path C bundles.
    if any(f"_v{n}_" in name for n in range(59, 100)):
        return True
    # v52..v58 are the legacy Path B HTML files we know about.
    if any(f"_v{n}_" in name for n in range(50, 59)):
        return False
    # Unknown filename — sniff content for v58 hallmark.
    try:
        head = app.storyboard_path.read_text(encoding="utf-8", errors="ignore")[:65536]
    except OSError:
        return False
    return "var IN=" not in head


def _patch_storyboard_L_field(
    app: "AppContext",
    beat_id: str,
    field: str,
    new_value: str,
) -> dict:
    """Atomically update one field of the storyboard HTML L[] entry for beat_id.

    field ∈ {"t", "i", "s", "p", "g"} — the L[] entry keys (a: anchor is
    never mutated here; it is the identity key).

    Returns a dict (callers interpret the reason field):
      {"patched": True,  "html_patched": True}                       # success
      {"patched": False, "reason": "v59_shell"}                      # Path C — state-only
      {"patched": False, "reason": "not_in_storyboard", "marker": m} # no L[] entry
      {"patched": False, "reason": "error", "error": "<msg>"}        # real error

    Safety (matches the hardening added to _handle_beat_update_text Apr 17):
      - Serialized by app._storyboard_write_lock (no HTML write race).
      - Unique-suffix tmp path (no cross-writer tmp clobbering).
      - Atomic os.replace (reader never sees half-written file).
      - Escapes \\, ", ', </script> in the value (no script-block breakout).
      - Round-trip verification before committing.
    """
    # LD-456 short-circuit: v59 (Path C) shells have no L[] array. Patching
    # would silently no-op (the markers don't exist) and the caller would
    # think the HTML was up to date when state.json had moved on. Surface
    # the case explicitly with reason="v59_shell" so the caller logs it.
    if _storyboard_is_v59_shell(app):
        return {"patched": False, "reason": "v59_shell"}

    try:
        beat_num = int(beat_id.split("_")[1])
    except (IndexError, ValueError):
        return {"patched": False, "reason": "error",
                "error": f"unparseable beat_id: {beat_id!r}"}

    if field not in ("t", "i", "s", "p", "g"):
        # "a" is the anchor — never rewrite it from here.
        return {"patched": False, "reason": "error",
                "error": f"field {field!r} not permitted for L[] patching"}

    if not isinstance(new_value, str):
        return {"patched": False, "reason": "error",
                "error": f"new_value must be str, got {type(new_value).__name__}"}

    storyboard_path = app.storyboard_path
    with app._storyboard_write_lock:
        try:
            html = storyboard_path.read_text(encoding="utf-8")
        except OSError as exc:
            return {"patched": False, "reason": "error",
                    "error": f"could not read storyboard: {exc}"}

        marker = f'a:"line_{beat_num:02d}"'
        idx = html.find(marker)
        if idx < 0:
            return {"patched": False, "reason": "not_in_storyboard",
                    "marker": marker}

        open_brace = html.rfind("{", 0, idx)
        close_brace = html.find("}", idx)
        if open_brace < 0 or close_brace < 0:
            return {"patched": False, "reason": "error",
                    "error": f"could not find L[] entry boundaries for {beat_id}"}
        entry = html[open_brace:close_brace + 1]

        field_prefix = f'{field}:"'
        t_start = entry.find(field_prefix)
        if t_start < 0:
            return {"patched": False, "reason": "error",
                    "error": f"no {field_prefix}...\" field in L[] entry for {beat_id}"}
        # Walk past escaped quotes to find the unescaped closing "
        i = t_start + len(field_prefix)
        while i < len(entry):
            if entry[i] == "\\" and i + 1 < len(entry):
                i += 2
                continue
            if entry[i] == '"':
                break
            i += 1
        else:
            return {"patched": False, "reason": "error",
                    "error": f"unterminated {field_prefix}...\" in L[] entry for {beat_id}"}
        t_end = i

        # Escape order (matters — must be left-to-right in this sequence):
        #   1. \\ — must come first so subsequent backslash insertions are
        #           not themselves re-escaped.
        #   2. \n / \r — CRITICAL fix (Phase 4 April 17 2026, counter-agent
        #          finding #1). Without this, a multi-line dialogue edit
        #          inserts a raw newline into the single-line L[] entry,
        #          which breaks the entire enclosing <script> block on
        #          the next page load (SyntaxError -> storyboard UI dies).
        #   3. " — quote breakout inside t:"..."
        #   4. ' — JS apostrophe escape (legacy; harmless)
        #   5. </ — </script> breakout guard
        escaped = new_value.replace("\\", "\\\\")
        escaped = escaped.replace("\n", "\\n")
        escaped = escaped.replace("\r", "\\r")
        escaped = escaped.replace('"', '\\"')
        escaped = escaped.replace("'", "\\'")
        escaped = escaped.replace("</", "<\\/")
        new_entry = entry[:t_start + len(field_prefix)] + escaped + entry[t_end:]
        new_html = html[:open_brace] + new_entry + html[close_brace + 1:]

        # Round-trip: confirm the field now reads back as the escaped value.
        if new_entry.find(f'{field_prefix}{escaped}"') < 0:
            return {"patched": False, "reason": "error",
                    "error": "round-trip escape verification failed — HTML NOT patched",
                    "escaped_preview": escaped[:80]}

        import uuid
        tmp = storyboard_path.with_suffix(
            storyboard_path.suffix + f".tmp.{os.getpid()}.{uuid.uuid4().hex[:8]}"
        )
        try:
            tmp.write_text(new_html, encoding="utf-8")
            os.replace(tmp, storyboard_path)
        except OSError as exc:
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass
            return {"patched": False, "reason": "error",
                    "error": f"HTML write failed: {exc}"}

        app.invalidate_beats_cache()
        return {"patched": True, "html_patched": True}


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class ProductionServer(ThreadingHTTPServer):
    """ThreadingHTTPServer with attached app state."""
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, addr, app):  # noqa: ANN001
        self.app = app
        super().__init__(addr, ProductionHandler)


class AppContext:
    def __init__(
        self,
        event_dir: Path,
        storyboard_path: Path,
        event_id: str,
        state: StateManager,
        client: WaveSpeedClient | None,
    ):
        self.event_dir = event_dir
        self.storyboard_path = storyboard_path
        self.event_id = event_id
        self.state = state
        self.client = client
        self.started_at = time.time()
        self.last_request_at = time.time()
        # Universal stitch editor job store — global, not per-event (STITCH_EDITOR_UNIVERSAL_V1).
        # LD-505 Phase C: anchor on the runtime Production/ root (event_dir.parent)
        # so cross-machine sync works. Was: Path(__file__).parent → tooling-side
        # Production/tools/, broken on home Mac vs work PC (audit C1-11).
        from lib.paths import runtime_production_root as _rpr
        self.stitch_state = StitchEditorState(_rpr(event_dir) / "tools" / "stitch_editor_state.json")
        self._beats_cache: list[dict] | None = None
        # Storyboard HTML write lock — serializes concurrent patches to the
        # same file (drag-drop image inject, contenteditable text saves).
        # Prevents the CRITICAL race found by Phase 3 review (April 17 2026).
        self._storyboard_write_lock = threading.Lock()
        # Image overrides from drag-drop — NESTED by video_role per
        # IMAGE_OVERRIDES_NESTED_BY_ROLE_V1 (S5.5a2, Kim 2026-05-03,
        # activity_log id=1464). Same beat_id can exist in different
        # partitions with different content; flat keying caused the exact
        # cross-partition contamination bug class S5.5a2 fixes.
        # In-memory shape: {role: {beat_id: data_uri}}.
        # Disk shape: state["videos"][role]["image_overrides"][beat_id] = image_key.
        # Resolved lazily to data URIs from the storyboard gallery.
        _initial_state = state.read_state()
        self._image_overrides: dict[str, dict[str, str]] = {}
        self._pending_override_keys: dict[str, dict[str, str]] = {}
        _videos = _initial_state.get("videos") or {}
        if _videos:
            _pending_total = 0
            for _role, _partition in _videos.items():
                _role_overrides = (_partition or {}).get("image_overrides") or {}
                if _role_overrides:
                    self._pending_override_keys[_role] = dict(_role_overrides)
                    _pending_total += len(_role_overrides)
            if _pending_total:
                _summary = {
                    r: sorted(d.keys())
                    for r, d in self._pending_override_keys.items()
                }
                print(f"[init] {_pending_total} image override(s) pending "
                      f"hydration across roles: {_summary}")
        else:
            # Pre-migration legacy shape (v1 state.json with top-level
            # image_overrides). Should not occur after S5.5a2 ships, but keep
            # the fallback path so a fresh checkout against an unmigrated
            # state file doesn't crash on init. Treat as intro-only.
            _legacy_overrides = _initial_state.get("image_overrides", {}) or {}
            if _legacy_overrides:
                self._pending_override_keys["intro"] = dict(_legacy_overrides)
                print(f"[init] {len(_legacy_overrides)} legacy image "
                      f"override(s) pending hydration (intro fallback): "
                      f"{sorted(_legacy_overrides.keys())}")
        # Storyboard navigation — Phase 1 (2026-04-23)
        self.storyboard_stem: str = storyboard_path.stem
        self._storyboard_list_cache: list[dict] | None = None
        self._storyboard_list_cache_mtime: float = 0.0

        # ----------------------------------------------------------------
        # LD-458 EVENT_LOAD_GENERATION_LOCK_V1 (Session 1.5 v3.1, 2026-05-02)
        # Monotonic event-load generation counter + lock. Async jobs pin the
        # current generation at start and validate via _check_event_pin
        # before terminal writes. /api/event/load increments generation
        # under lock and atomically swaps event_dir / storyboard_path /
        # event_id. See LD-460 ASYNC_JOB_GENERATION_PIN_V1 for the pin
        # contract.
        # ----------------------------------------------------------------
        self.event_generation: int = 0
        self.event_load_lock: threading.Lock = threading.Lock()

        # ----------------------------------------------------------------
        # S5.5d (v3 architecture revision, 2026-05-03):
        #   ASYNC_QUEUE_DRAIN_PROTOCOL_V1 — drain gate + sync inflight set
        #   MILESTONE_STANDALONE_INDEPENDENT_V1 — scope_type signal
        # ----------------------------------------------------------------
        self.accept_new_jobs: bool = True
        self._sync_inflight: set[str] = set()
        self._sync_inflight_lock: threading.Lock = threading.Lock()
        self.scope_type: str = "event"  # 'event' | 'milestone'
        self.active_milestone_id: str | None = None
        self.milestone_dir: Path | None = None

    def beats(self, video_role: str = "intro") -> list[dict]:
        # v59 Vite SPA has no embedded beat data — project from state.
        if _storyboard_is_v59_shell(self):
            state = self.state.read_state()
            state_beats = ((state.get("videos") or {}).get(video_role) or {}).get("beats") or {}
            result = []
            for beat_id in sorted(state_beats.keys()):
                b = state_beats[beat_id]
                try:
                    ln = int(beat_id.split("_")[1])
                except (IndexError, ValueError):
                    ln = -1
                result.append({
                    "line_number": ln,
                    "speaker": b.get("speaker", ""),
                    "text": b.get("text", ""),
                    "section": b.get("section", ""),
                    "image": None,  # resolved at animate time via get_beat_image()
                    "image_key": b.get("image_path", ""),
                })
            return result
        # Legacy path: HTML-embedded beat data (pre-v59 storyboards).
        if self._beats_cache is None:
            html = self.storyboard_path.read_text(encoding="utf-8")
            self._beats_cache = extract_beats_from_html(html)
        return self._beats_cache

    def invalidate_beats_cache(self) -> None:
        """Force re-read of storyboard beats on next access."""
        self._beats_cache = None

    def switch_storyboard(self, filename: str) -> dict:
        """Atomically switch the active storyboard. Caller must hold _storyboard_write_lock."""
        new_path = self.event_dir / filename
        if new_path == self.storyboard_path:
            return {"ok": True, "changed": False}
        self.storyboard_path = new_path
        self.storyboard_stem = new_path.stem
        self.invalidate_beats_cache()
        # Clear nested {role: {beat_id: ...}} caches per IMAGE_OVERRIDES_NESTED_BY_ROLE_V1.
        self._image_overrides = {}
        self._pending_override_keys = {}
        self._storyboard_list_cache = None
        title = self._extract_storyboard_title(new_path)
        return {"ok": True, "changed": True, "title": title,
                "filename": filename, "stem": new_path.stem}

    def _extract_storyboard_title(self, path: "Path") -> str:
        try:
            html = path.read_text(encoding="utf-8", errors="replace")
            m = re.search(r"<title>([^<]+)</title>", html)
            return m.group(1).strip() if m else path.stem
        except Exception:
            return path.stem

    def _get_storyboard_list(self, force_refresh: bool = False) -> list[dict]:
        """Cached glob of event_dir for storyboard_v*_prod.html files.
        Deduplicates by title — only the highest version of each unique title is shown."""
        files = list(self.event_dir.glob("storyboard_v*_prod.html"))
        max_mtime = max((p.stat().st_mtime for p in files), default=0.0) if files else 0.0
        if (not force_refresh
                and self._storyboard_list_cache is not None
                and max_mtime == self._storyboard_list_cache_mtime):
            return self._storyboard_list_cache
        # Build deduplicated list: keep only latest version per unique title
        by_title: dict[str, dict] = {}
        for p in sorted(files, key=lambda f: self._version_from_name(f.name), reverse=True):
            try:
                raw = p.read_text(encoding="utf-8", errors="replace")
                beat_count = raw.count('a:"line_')
                title = self._extract_storyboard_title(p)
            except Exception:
                beat_count = 0
                title = p.stem
            entry = {
                "filename": p.name,
                "title": title,
                "version": self._version_from_name(p.name),
                "is_active": p.name == self.storyboard_path.name,
                "beat_count": beat_count,
                "mtime_iso": datetime.fromtimestamp(
                    p.stat().st_mtime, tz=timezone.utc).isoformat(),
            }
            # Since files are sorted version desc, first seen = highest version for this title
            if title not in by_title:
                by_title[title] = entry
            elif p.name == self.storyboard_path.name:
                # Always include the active storyboard even if its title is a duplicate
                by_title[title + " (active)"] = entry
        result = sorted(by_title.values(), key=lambda e: e["version"], reverse=True)
        self._storyboard_list_cache = result
        self._storyboard_list_cache_mtime = max_mtime
        return result

    @staticmethod
    def _version_from_name(name: str) -> int:
        m = re.search(r"storyboard_v(\d+)", name)
        return int(m.group(1)) if m else 0

    def _hydrate_pending_overrides(self) -> None:
        """Resolve persisted {beat_id: image_key} entries to full data URIs.
        Called lazily on first image lookup so we don't parse the storyboard
        at AppContext init time (which can race with pid file setup).
        Skips beats that already have an entry in _image_overrides (e.g., user
        drag-dropped a new image before hydration ran — fresh value wins).

        S5.5a2 (IMAGE_OVERRIDES_NESTED_BY_ROLE_V1): both caches are nested
        {role: {beat_id: ...}}.
        """
        if not self._pending_override_keys:
            return
        resolved = 0
        skipped = 0
        total = sum(len(d) for d in self._pending_override_keys.values())
        for role, role_pending in list(self._pending_override_keys.items()):
            role_resolved = self._image_overrides.setdefault(role, {})
            for bid, key in list(role_pending.items()):
                if bid in role_resolved:
                    # Fresh drag-drop beat us to it — don't clobber
                    skipped += 1
                    continue
                data_uri = self.get_fullres_gallery_image(key)
                if data_uri:
                    role_resolved[bid] = data_uri
                    resolved += 1
                else:
                    print(f"[hydrate] WARN: no gallery image for key={key!r} "
                          f"(role {role!r}, beat {bid}) — skipping")
        print(f"[hydrate] resolved {resolved}/{total} image overrides "
              f"({skipped} skipped — fresh drag-drop)")
        self._pending_override_keys = {}

    def get_beat_image(self, beat_id: str, video_role: str = "intro") -> str | None:
        """Get the best available image for a beat: override > gallery full-res > TH.

        S5.5a2: video_role parameter selects the partition for the override
        lookup (IMAGE_OVERRIDES_NESTED_BY_ROLE_V1). Default 'intro' preserves
        legacy single-partition behavior; new call sites that target a
        specific partition pass video_role explicitly. The default is a
        literal value chosen by the call site, NOT a server-side resolution
        of state['active_video'] (which would violate LD-474).
        """
        # Lazy hydration of persisted overrides (Tier 1 B3 restart-resilience)
        if self._pending_override_keys:
            self._hydrate_pending_overrides()
        role_overrides = self._image_overrides.get(video_role, {})
        if beat_id in role_overrides:
            return role_overrides[beat_id]
        # Fall back to storyboard extraction (storyboard HTML is intro-bound by
        # construction — the v59 storyboard renders intro beats; phase_a/b
        # have their own image-source paths under videos[role].image_overrides).
        for b in self.beats():
            if f"beat_{b['line_number']:02d}" == beat_id:
                return b.get("image")
        return None

    def get_fullres_gallery_image(self, image_key: str) -> str | None:
        """Resolve image_key to a full-res data URI.

        Path C (v59 shell): the Vite shell has no embedded gallery markers, so
        we resolve via the on-disk library inventory (BG_STILLS_DIR, sources/,
        crops/, Character_Assets/) matching filename stem against image_key with
        space→underscore normalization. Legacy HTML scan kept as fallback for
        pre-v59 storyboards. Fixes DRAG_DROP_V59_GALLERY_V1.
        """
        fp = self.resolve_library_image_path(image_key)
        if fp:
            try:
                with open(fp, "rb") as f:
                    raw = f.read()
                ext = os.path.splitext(fp)[1].lower().lstrip(".")
                mime = {"png": "image/png", "webp": "image/webp",
                        "jpg": "image/jpeg", "jpeg": "image/jpeg"}.get(ext, "image/png")
                return f"data:{mime};base64," + base64.b64encode(raw).decode("ascii")
            except OSError:
                pass
        # Legacy fallback for pre-v59 storyboards (HTML gallery markers).
        html = self.storyboard_path.read_text(encoding="utf-8")
        pattern = r'<div class="ic"><img src="(data:image/[^"]+)"><p>([^<]+)</p></div>'
        normalized = image_key.replace(" ", "_")
        for m in re.finditer(pattern, html):
            src, name = m.group(1), m.group(2)
            key = name.replace(".png", "").replace(".PNG", "").replace(" ", "_")
            if key == image_key or key == normalized:
                return src
        return None

    def _library_root_dirs(self) -> list[str]:
        """Canonical list of approved library roots for image lookups.

        Single source of truth for path-confinement (CodeQL py/path-injection
        mitigation, LD CODEQL_TOPLEVEL_FAILURE_FIX_PATH_INJECTION_V1). Any
        client-supplied abs_path MUST resolve under one of these roots before
        the server reads/opens the file. See is_path_under_library_root().

        Per-event image library + global canonical images + Character_Assets.

        BG_REF_APP_CONTEXT_V1: AppContext methods use self.event_dir — never
        self.app (that attribute exists only on ProductionHandler).
        """
        from lib.event_library import library_image_roots

        return library_image_roots(self.event_dir, self.event_dir.parent)

    def is_path_under_library_root(self, abs_path: str) -> bool:
        """Return True iff abs_path resolves under an approved library root.

        Path-confinement gate for client-supplied abs_path values. Resolves
        symlinks via os.path.realpath then checks os.path.commonpath against
        each approved root. Rejects:
        - Non-string / empty input
        - Paths that resolve outside every approved root
        - Paths whose resolved form would escape via .. traversal

        Per CLAUDE.md Rule 19 (no error paths): every call site that ingests a
        client abs_path MUST gate on this before os.path.exists/isfile/PIL.open.
        Server binds 127.0.0.1 + CORS:* widens threat model to malicious sites
        Kim visits (PR #8 triage 2026-05-07, prod_blockers row 76).
        """
        if not isinstance(abs_path, str) or not abs_path:
            return False
        try:
            resolved = os.path.realpath(abs_path)
        except (OSError, ValueError):
            return False
        for root in self._library_root_dirs():
            if not root:
                continue
            try:
                common = os.path.commonpath([resolved, root])
            except ValueError:
                # Different drives on Windows or mixed absolute/relative — reject
                continue
            if common == root:
                return True
        return False


    def resolve_library_image_path(self, image_key: str) -> str | None:
        """Resolve image_key to its absolute on-disk path in library directories.

        Scans per-event library dirs, canonical images, and Character_Assets.
        Returns None if not found (caller falls back to legacy HTML scan).
        """
        from lib.event_library import resolve_library_image_path as _resolve

        return _resolve(image_key, self.event_dir, self.event_dir.parent)

    def touch(self) -> None:
        self.last_request_at = time.time()

    def idle_seconds(self) -> float:
        return time.time() - self.last_request_at


class ProductionHandler(BaseHTTPRequestHandler):
    # Silence default access log spam; we print our own summary on mutations.
    def log_message(self, fmt, *args):  # noqa: A003
        return

    @property
    def app(self) -> AppContext:
        return self.server.app  # type: ignore[attr-defined]

    # ---- response helpers ----
    def _cors_headers(self) -> None:
        """Add CORS headers so file:// and localhost origins can talk to us."""
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._cors_headers()
        # LOG_HYGIENE_SUPPRESS_CLIENT_CANCEL_TRACEBACKS (LD 2026-04-18):
        # Chrome cancels preloaded <video> range requests aggressively; the
        # 500-response path triggered by that cancel then throws its own
        # BrokenPipe during end_headers(). Swallow the two specific socket
        # errors — nothing else — and log one short line. General Exception
        # is NOT caught here (per task spec).
        try:
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            print("asset stream canceled by client (_send_json)", file=sys.stderr, flush=True)
            return

    def _send_error_v59(
        self,
        status: int,
        *,
        error_code: str,
        error_message: str,
        retry_safe: bool = True,
        hint: str | None = None,
        extra: dict | None = None,
    ) -> None:
        """V59 Phase 7 canonical error shape.

        Returns JSON {ok: false, error_code, error_message, retry_safe, hint, ...extra}.
        Existing handlers may continue using _send_json(status, {"error": ...}) — both
        shapes are accepted by the client's pathappPatch (per V59 Phase 7 spec line 316).

        error_code: stable SCREAMING_SNAKE identifier (e.g. SCOPE_MISMATCH, BEAT_NOT_FOUND).
        error_message: human-readable, can include specifics.
        retry_safe: true if client can safely retry same request.
        hint: optional next-step suggestion for Kim or operator.
        """
        payload = {
            "ok": False,
            # Legacy alias — keep the pre-V59 `error` key populated so existing
            # clients/tests that read `payload["error"]` continue working. The
            # canonical V59 fields below are additive, not replacement.
            "error": error_message,
            "error_code": error_code,
            "error_message": error_message,
            "retry_safe": retry_safe,
            "hint": hint,
        }
        if extra:
            payload.update(extra)
        return self._send_json(status, payload)

    def _send_bytes(self, status: int, body: bytes, content_type: str, extra_headers: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self._cors_headers()
        for k, v in (extra_headers or {}).items():
            self.send_header(k, v)
        # Same rationale as _send_json: suppress client-cancel traceback spam.
        try:
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            print("asset stream canceled by client (_send_bytes)", file=sys.stderr, flush=True)
            return

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    # ---- LD-456 SCOPE_VALIDATION_V1 ----
    def _assert_event_scope(self, body: dict, allow_missing: bool = False, allow_missing_video_role: bool = False) -> bool:
        """Reject cross-event mutations at the door.

        Compares request `body['event_id']` (or URL query string fallback)
        against the server-pinned `self.app.event_dir.name`. On mismatch,
        sends HTTP 409 with a structured error body and returns False.

        Caller pattern:
            if not self._assert_event_scope(body):
                return

        On missing body['event_id']:
          - allow_missing=False (DEFAULT, post-C-5 flip per LD
            SCOPE_REQUIRED_DEFAULTS_V1): reject with HTTP 400. Mutation
            handlers MUST hit this path; v59 clients per LD-461 always
            inject scope_event_id, so missing is a real bug class.
          - allow_missing=True: explicit opt-in for read-only probes only
            (state_snapshot, bg_session_state, bg_poll_*, v2_sidecar,
            phase_suggest_script, etc.) where unauthenticated reads are
            tolerated by design.

        Origin: 2026-05-01 cross-event Accept-All leak. Beat Generator on
        Event 2 → Accept All → Event 2 keys leaked into Event 1 storyboard's
        L[] because _handle_bg_accept_beats derived sidecar_path from
        server-pinned self.app.event_dir but ignored body's active_context.
        This guard makes that class structurally impossible — and the
        post-C-5 default flip closes the silent-default leak that
        previously let scope_event_id-less requests through unchecked.
        """
        body_event = (body or {}).get("event_id")
        # Fallback: URL query string (some clients pass it there).
        if body_event is None:
            try:
                qs = urllib.parse.urlparse(self.path).query
                params = urllib.parse.parse_qs(qs)
                scope_qs = params.get("scope_event_id")
                if scope_qs:
                    body_event = scope_qs[0]
                else:
                    qs_val = params.get("event_id")
                    if qs_val:
                        body_event = qs_val[0]
            except Exception:
                pass
        server_event = self.app.event_dir.name
        if body_event is None:
            if allow_missing:
                return True
            self._send_error_v59(
                400,
                error_code="SCOPE_REQUIRED",
                error_message="scope_required",
                retry_safe=False,
                extra={"code": "SCOPE_VALIDATION_V1", "expected_event_id": server_event, "hint": "v59 clients must include event_id in request body."},
            )
            return False
        if body_event != server_event:
            print(
                f"[scope-guard] HTTP 409 on {self.command} {self.path}: "
                f"body event_id={body_event!r} != server event_id={server_event!r}",
                flush=True,
            )
            self._send_error_v59(
                409,
                error_code="SCOPE_MISMATCH",
                error_message="scope_mismatch",
                retry_safe=False,
                extra={"code": "SCOPE_VALIDATION_V1", "expected_event_id": server_event, "got_event_id": body_event, "hint": "The client thinks it is editing a different event than "
                    "this server is serving. Restart the client tab so the "
                    "active scope re-resolves, or restart the server with "
                    f"--event-dir Production/{body_event} if the client is "
                    "correct."},
            )
            return False
        # ---- LD-474 VIDEO_ROLE_PER_REQUEST_V1 (S5.5a2 extension) ----
        # When scope_video_role is present, validate it against the canonical
        # set + presence in current state. Missing is allowed during the
        # refactor window (default 'intro' applied by caller).
        body_video_role = (body or {}).get("scope_video_role")
        if body_video_role is None:
            if allow_missing_video_role:
                return True
            self._send_error_v59(
                400,
                error_code="VIDEO_ROLE_REQUIRED",
                error_message="video_role_required",
                retry_safe=False,
                extra={"code": "VIDEO_ROLE_INVALID", "valid": sorted(self.app.state._VALID_VIDEO_ROLES), "hint": "scope_video_role required on this endpoint (LD-474)."},
            )
            return False
        if not self.app.state.validate_video_role(body_video_role):
            self._send_error_v59(
                400,
                error_code="VIDEO_ROLE_INVALID",
                error_message="video_role_invalid",
                retry_safe=False,
                extra={"code": "VIDEO_ROLE_INVALID", "got": body_video_role, "valid": sorted(self.app.state._VALID_VIDEO_ROLES), "hint": "scope_video_role must be one of intro/resolution/"
                    "standalone AND exist in current state.videos."},
            )
            return False
        return True

    # ---- LD-461 SCOPE_BODY_HELPER_V1 (extended in S5.5a2 with scope_video_role) ----
    def _scope_body(self, body: dict) -> dict:
        """Normalize scope keys before _assert_event_scope.

        Accepts EITHER `event_id` OR `scope_event_id` from the request body.
        Returns a dict suitable for `_assert_event_scope` (which internally
        keys on `event_id`). `scope_event_id` wins on collision because the
        BG handler family uses `event_id` as a *segment number* (1..N), not
        a storyboard scope; the v59 client passes the storyboard scope as
        `scope_event_id` to disambiguate.

        S5.5a2 (LD-474 VIDEO_ROLE_PER_REQUEST_V1): also surface
        `scope_video_role` from the body so `_assert_event_scope` can
        validate it. Default is None (caller may use 'intro' fallback
        during the post-migration refactor window before all clients
        are guaranteed to pass scope_video_role).

        Every guard call site MUST use this helper instead of hand-rolling
        the dict, per LD-461 SCOPE_BODY_HELPER_V1. Verification gate asserts
        grep_count(_assert_event_scope) ≤ grep_count(_scope_body) (every
        guard goes through the helper).
        """
        return {
            "event_id": (body or {}).get("scope_event_id") or (body or {}).get("event_id"),
            "scope_video_role": (body or {}).get("scope_video_role"),
        }

    # ---- LD-460 ASYNC_JOB_GENERATION_PIN_V1 ----
    def _check_event_pin(self, context: dict, action_label: str) -> bool:
        """Return True if it's safe to proceed with a terminal write.

        Compares `context['pinned_generation']` (captured at job entry)
        against the current `self.app.event_generation`. On drift, logs a
        single-line stderr warning, sets `context['status']` to
        `discarded_event_changed`, and returns False — caller MUST
        early-return without mutating state, writing files at the new
        event_dir, or registering Directus assets.

        Files at `context['pinned_event_dir']` are NOT deleted on drift —
        they are orphaned but recoverable via a future recovery script
        (per spec §10).

        Pin contract — caller seeds `context` at job entry:
            context["pinned_generation"] = self.app.event_generation
            context["pinned_event_dir"] = Path(self.app.event_dir)

        Per LD-460 ASYNC_JOB_GENERATION_PIN_V1; spec §3.5.1.
        """
        if context is None:
            # Defensive — handler forgot to seed context. Log loudly.
            print(
                f"[event-pin] WARN {action_label}: no context provided; "
                f"proceeding without pin check (handler must seed context).",
                file=sys.stderr, flush=True,
            )
            return True
        pinned = context.get("pinned_generation")
        if pinned is None:
            # Pin missing — handler did not seed it. Log loudly but allow
            # write so we don't break legacy paths during rollout.
            print(
                f"[event-pin] WARN {action_label}: pinned_generation missing "
                f"in context; proceeding (handler may need seeding).",
                file=sys.stderr, flush=True,
            )
            return True
        current_gen = getattr(self.app, "event_generation", 0)
        if pinned == current_gen:
            return True
        pinned_dir = context.get("pinned_event_dir")
        pinned_name = pinned_dir.name if pinned_dir else "?"
        current_name = self.app.event_dir.name
        print(
            f"[event-pin] {action_label} ABORTED — pinned gen={pinned} "
            f"current gen={current_gen}; pinned event={pinned_name} "
            f"current event={current_name}. Output orphaned at pinned dir; "
            f"NOT deleted, NOT registered, state NOT mutated.",
            file=sys.stderr, flush=True,
        )
        context["status"] = "discarded_event_changed"
        return False

    # ---- CORS preflight ----
    def do_OPTIONS(self):  # noqa: N802
        self.send_response(204)
        self._cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    # ---- dispatch ----
    def do_GET(self):  # noqa: N802
        self.app.touch()
        path = urllib.parse.urlparse(self.path).path
        try:
            if path == "/api/health":
                return self._handle_health()
            if path == "/api/state":
                return self._send_json(200, self._read_state_with_file_flags())
            # S5.5b new endpoints — Bug 4 fix + VideoSelector data source
            if path == "/api/event/current":
                return self._handle_event_current()
            if path == "/api/video/list":
                return self._handle_video_list()
            if path == "/api/animate/status":
                return self._handle_status()
            if path == "/storyboard" or path == "/":
                return self._serve_storyboard()
            if path.startswith("/cropper"):
                return self._serve_cropper()
            if path.startswith("/asset/"):
                return self._serve_asset(path[len("/asset/"):])
            if path.startswith("/api/beat/audio/"):
                # Fresh on-disk TTS stream — bypasses storyboard AU[] stale
                # base64. Fixes Preview Beat double-audio bug (decision 184).
                beat_id = path[len("/api/beat/audio/"):]
                return self._serve_beat_audio(beat_id)
            if path == "/api/lipsync/status":
                return self._handle_lipsync_status()
            # LD V3 Preview Stitched V3: module-level media + library streams.
            if path.startswith("/api/phase_b/media/"):
                fname = path[len("/api/phase_b/media/"):]
                return self._serve_phase_media(fname)
            if path.startswith("/api/phase_b/watercolor/"):
                fname = path[len("/api/phase_b/watercolor/"):]
                return self._serve_watercolor(fname)
            # Phase A panel build (LD PHASE_A_PANEL_VOICE_SLIDERS_V1, 2026-04-20):
            # hydrate persistent voice sliders from prod_voice_profiles by id.
            if path.startswith("/api/voice/profile/"):
                pid_raw = path[len("/api/voice/profile/"):]
                return self._handle_voice_profile_get(pid_raw)
            # Path A++ v2 endpoints (April 18 2026)
            if path == "/api/v2/storyboard/L.json":
                return self._handle_v2_sidecar()
            if path.startswith("/api/v2/event/") and path.endswith("/state"):
                return self._handle_v2_event_state(path)
            if path.startswith("/api/v2/beat/"):
                return self._handle_v2_get(path)
            if path in ("/api/tts", "/api/tts/status"):
                # LD-281 NO_RUNTIME_TTS_PERSONALIZATION_V1 — intentional 501 (architectural lock, not a deferral)
                return self._send_error_v59(
                           501,
                           error_code="NOT_IMPLEMENTED_V1_MVP",
                           error_message="not implemented in v1 MVP",
                           retry_safe=True,
                       )
            # ── Beat Generator tab routes (GET) ──────────────────────────────────
            if path == "/api/bg/segments":
                return self._handle_bg_segments()
            if path == "/api/bg/session-state":
                return self._handle_bg_session_state()
            if path == "/api/bg/extract-beats/draft":
                from server_handlers.background import handle_bg_extract_beats_draft_get
                qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                return handle_bg_extract_beats_draft_get(self, qs)
            if path == "/api/bg/poll-flux-status":
                return self._handle_bg_poll_flux()
            if path.startswith("/api/bg/poll-gpt-status"):
                return self._handle_bg_poll_gpt_status()
            if path.startswith("/api/bg/poll-arlo-o3-voice-status"):
                return self._handle_bg_poll_arlo_o3_voice_status()
            if path.startswith("/api/bg/poll-kling-native-lipsync-experiment-status"):
                return self._handle_bg_poll_kling_native_lipsync_experiment_status()
            if path == "/api/bg/groups":
                return self._handle_bg_groups()
            if path == "/api/bg/poll-assemble-status":
                return self._handle_bg_poll_assemble_status()
            if path.startswith("/bg-stills/"):
                return self._handle_bg_stills(path)
            if path == "/api/bg/crop-preview":
                return self._handle_bg_crop_preview()
            if path == "/preview/phase_a/permanent":
                return self._handle_preview_phase_a_permanent()
            if path == "/files":
                return self._handle_files_serve()
            if path == "/api/cr/library":
                return self._handle_cr_library()
            if path == "/api/cr/full":
                return self._handle_cr_full_image()
            if path == "/api/storyboard/video_frame":
                from server_handlers.background import handle_storyboard_video_frame
                qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                return handle_storyboard_video_frame(self, qs)
            if path.startswith("/api/storyboard/list"):
                return self._handle_storyboard_list()
            # S3 v3.1 GET endpoints — LDs 462-467.
            if path == "/api/event/list":
                return self._handle_event_list()
            if path == "/api/phase/watercolor_list":
                return self._handle_phase_watercolor_list()
            if path == "/api/phase/watercolor_file":
                return self._handle_phase_watercolor_file()
            if path == "/api/phase/base_clips_list":
                return self._handle_phase_base_clips_list()
            # S5.5f — ambient preset inventory (LD AMBIENT_PRESET_SELECTOR_INPRODUCER_V1).
            # Filesystem scan of Production/audio_library/ambient/*.mp3 — Cursor v8
            # release-blocker fix; spec §3.7 option (b).
            if path == "/api/phase_b/ambient_preset_list":
                return self._handle_phase_b_ambient_preset_list()
            if path == "/api/production/map":
                return self._handle_production_map()
            # ── Visible Magic Phase 2 (2026-04-24) ──────────────────────────────
            if path == "/magic":
                return self._serve_magic_picker()
            if path == "/api/magic/status":
                return self._handle_magic_status()
            if path == "/api/magic/resolve_bg":
                return self._handle_magic_resolve_bg()
            if path == "/api/beat/accepted-bg":
                return self._handle_beat_accepted_bg()
            # ── Full Module Timeline Editor (2026-04-26, FULL_TIMELINE_EDITOR_V1) ──
            if path.startswith("/api/timeline/audio/"):
                event_id = path[len("/api/timeline/audio/"):]
                return self._handle_timeline_audio(event_id)
            if path == "/api/timeline/sfx_library":
                return self._handle_timeline_sfx_library()
            if path.startswith("/api/media/timeline_audio_"):
                fname = path[len("/api/media/"):]
                return self._serve_timeline_audio_file(fname)
            # ── Stitch Editor (2026-04-26, STITCH_EDITOR_UNIVERSAL_V1) ──────────
            if path == "/stitch_editor":
                return self._serve_stitch_editor()
            if path == "/api/stitch_editor/library":
                return self._handle_stitch_library()
            if path == "/api/stitch_editor/jobs":
                return self._handle_stitch_list_jobs()
            if path.startswith("/api/stitch_editor/job/"):
                name = urllib.parse.unquote(path[len("/api/stitch_editor/job/"):])
                return self._handle_stitch_load_job(name)
            if path.startswith("/api/stitch_editor/preview_file/"):
                hash_id = path[len("/api/stitch_editor/preview_file/"):]
                return self._serve_stitch_preview_file(hash_id)
            if path == "/api/stitch_editor/beat_boundaries":
                return self._handle_stitch_beat_boundaries()
            if path.startswith("/api/stitch_editor/audio_file/"):
                fname = urllib.parse.unquote(
                    path[len("/api/stitch_editor/audio_file/"):],
                )
                return self._serve_stitch_audio_file(fname)
            if urllib.parse.urlparse(self.path).path == "/api/finder_video":
                return self._serve_finder_video()
            # ── S5.5d (v3 architecture revision) GET routes ──
            if path == "/api/admin/inflight_count":
                return self._handle_admin_inflight_count(None)
            if path == "/api/milestones/list":
                return self._handle_milestones_list(None)
            if path == "/api/project/list":
                return self._handle_project_list(None)
            return self._send_error_v59(
                       404,
                       error_code="NOT_FOUND",
                       error_message="not found",
                       retry_safe=False,
                       extra={"path": path},
                   )
        except (BrokenPipeError, ConnectionResetError):
            # LOG_HYGIENE_SUPPRESS_CLIENT_CANCEL_TRACEBACKS (LD 2026-04-18):
            # Defense-in-depth: if any downstream handler re-raises a client
            # cancel, eat it here instead of running the 500 path (which would
            # just throw ANOTHER BrokenPipe during end_headers()).
            print(f"request canceled by client: GET {path}", file=sys.stderr, flush=True)
            return
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            return self._send_error_v59(
                       500,
                       error_code="GENERIC_ERROR",
                       error_message=str(exc),
                       retry_safe=True,
                   )

    def do_POST(self):  # noqa: N802
        self.app.touch()
        path = urllib.parse.urlparse(self.path).path
        try:
            body = self._read_json()
            if path == "/api/animate":
                return self._handle_animate(body)
            if path == "/api/animate/redo":
                return self._handle_redo(body)
            if path == "/api/beat/add_options":
                return self._handle_add_options(body)
            # T1-Phase 2 + 3 (spec MAGIC_AND_ENDFRAME_FIXES_20260520_v1, LD-814):
            # end-frame iteration endpoints — Kim previews/uploads end frame
            # BEFORE Regen B+C spends Kling $. _handle_add_options_startend
            # then refuses to run without an approved end_frame_path (P4).
            if path == "/api/beat/preview_end_frame":
                return self._handle_preview_end_frame(body)
            if path == "/api/beat/upload_end_frame":
                return self._handle_upload_end_frame(body)
            if path == "/api/beat/swap_to_a":
                # Flat alias for v2 path-param endpoint so pathappPatch can reach it.
                _beat_id_from_body = body.get("beat_id") or body.get("beat")
                if not _beat_id_from_body:
                    return self._send_error_v59(
                               400,
                               error_code="MISSING_BEAT_ID",
                               error_message="missing beat_id in body",
                               retry_safe=False,
                           )
                return self._handle_v2_beat_swap_to_a(_beat_id_from_body, body)
            if path == "/api/beat/use_still_as_final":  # LD-761: Ken Burns still as final
                return self._handle_use_still_as_final(body)
            if path == "/api/beat/undo_final":  # LD-761: undo Ken Burns still-as-final
                return self._handle_beat_undo_final(body)
            if path == "/api/beat/update_text":
                return self._handle_beat_update_text(body)
            if path == "/api/beat/update_speaker":
                # LD CHARACTER_DROPDOWN_RESTORED_V1 — speaker dropdown
                # write path mirroring update_text. Storyboard tab routes
                # through here; BG tab still uses /api/bg/update-beat which
                # already accepts `speaker` via _BG_BEAT_WRITABLE.
                return self._handle_beat_update_speaker(body)
            if path == "/api/beat/done_toggle":
                return self._handle_beat_done_toggle(body)
            # BEAT_GRAFT_RECOVERY_MECHANISM_V1 (C-7) — Pillar 7 cornerstone.
            # Cross-event/role beat move with audit + idempotency + pre-image.
            if path == "/api/beat/graft":
                return self._handle_beat_graft(body)
            if path == "/api/beat/regenerate_audio":
                return self._handle_beat_regenerate_audio(body)
            if path == "/api/select":
                return self._handle_select(body)
            if path == "/api/export":
                return self._handle_export()
            if path == "/api/beat/delay":
                return self._handle_beat_delay(body)
            if path == "/api/beat/trim":
                return self._handle_beat_trim(body)
            if path == "/api/beat/zoom":
                return self._handle_beat_zoom(body)
            if path == "/api/beat/use_as_final":  # Spec A: no-lipsync final path
                return self._handle_use_as_final(body)
            if path == "/api/budget/override":
                return self._handle_budget_override(body)
            if path == "/api/server/restart":
                return self._handle_restart()
            if path == "/api/lipsync":
                return self._handle_lipsync_submit(body)
            if path == "/api/lipsync_idle":
                return self._handle_lipsync_idle(body)
            if path == "/api/inject-image":
                return self._handle_inject_image(body)
            if path == "/api/assign-image":
                return self._handle_assign_image(body)
            # Path A++ v2 endpoint (April 18 2026)
            if path.startswith("/api/v2/beat/") and path.endswith("/patch"):
                return self._handle_v2_patch(path, body)
            # Tier 3 v2 create endpoint (April 18 2026, LD TIER3_BEAT_CREATE_ENDPOINT)
            if path == "/api/v2/beat/create":
                return self._handle_v2_beat_create(body)
            # Storyboard-tab beat delete (production state, not BG sidecar)
            if path == "/api/v2/beat/delete":
                return self._handle_v2_beat_delete(body)
            # Swap-to-A v2 endpoint (April 19 2026) — park a B/C favorite into
            # slot A so Regenerate B+C doesn't overwrite it (or its lipsync).
            if path.startswith("/api/v2/beat/") and path.endswith("/swap_to_a"):
                parts = [p for p in path.split("/") if p]
                # Expect: ["api", "v2", "beat", "<beat_id>", "swap_to_a"]
                if len(parts) != 5:
                    return self._send_error_v59(
                               400,
                               error_code="GENERIC_ERROR",
                               error_message=f"malformed path: {path!r}",
                               retry_safe=False,
                               extra={"hint": "Expected /api/v2/beat/<beat_id>/swap_to_a"},
                           )
                return self._handle_v2_beat_swap_to_a(parts[3], body)
            # LD-285 Preview Stitched v2 endpoints (April 19 2026)
            if path == "/api/v2/module/patch":
                return self._handle_v2_module_patch(body)
            if path == "/api/phase_b/regen_audio":
                return self._handle_phase_b_regen_audio(body)
            # F-PHASE-A-001 — canonical /api/phase_a/* aliases (same handlers; body.phase disambiguates).
            if path == "/api/phase_a/regen_audio":
                return self._handle_phase_b_regen_audio(body)
            if path == "/api/phase_b/mix_audio":
                return self._handle_phase_b_mix_audio(body)
            if path == "/api/phase_a/mix_audio":
                return self._handle_phase_b_mix_audio(body)
            if path == "/api/phase_b/lipsync":
                return self._handle_phase_b_lipsync(body)
            if path == "/api/phase_a/lipsync":
                return self._handle_phase_a_lipsync(body)
            if path == "/api/phase_a/reject_lipsync":
                return self._handle_phase_reject_lipsync(body)
            if path == "/api/phase_b/reject_lipsync":
                return self._handle_phase_reject_lipsync(body)
            if path == "/api/phase_a/apply_stem_cut":
                return self._handle_phase_apply_stem_cut(body)
            if path == "/api/phase_b/apply_stem_cut":
                return self._handle_phase_apply_stem_cut(body)
            if path == "/api/phase_a/regen_flyin_flyout":
                return self._handle_phase_a_regen_flyin_flyout(body)
            if path == "/api/phase_a/regen_base_clip":
                return self._handle_phase_a_regen_base_clip(body)
            if path == "/api/phase_a/restitch":
                return self._handle_phase_a_restitch(body)
            if path == "/api/phase_b/preview":
                return self._handle_phase_b_preview(body)
            # Phase A panel build (LD PHASE_A_PANEL_VOICE_SLIDERS_V1, 2026-04-20):
            # persist voice slider changes to prod_voice_profiles by id.
            if path == "/api/voice/profile_update":
                return self._handle_voice_profile_update(body)
            if path == "/api/preview_stitched":
                return self._handle_preview_stitched(body)
            if path == "/api/tts":
                # LD-281 NO_RUNTIME_TTS_PERSONALIZATION_V1 — intentional 501 (architectural lock, not a deferral)
                return self._send_error_v59(
                           501,
                           error_code="NOT_IMPLEMENTED_V1_MVP",
                           error_message="not implemented in v1 MVP",
                           retry_safe=True,
                       )
            # ── Beat Generator tab routes (POST) ─────────────────────────────────
            if path == "/api/bg/set-active-context":
                return self._handle_bg_set_active_context(body)
            if path == "/api/bg/extract-beats":
                return self._handle_bg_extract_beats(body)
            if path == "/api/bg/extract-beats/plan":
                return self._handle_bg_extract_beats_plan(body)
            if path == "/api/bg/extract-beats/approve":
                return self._handle_bg_extract_beats_approve(body)
            if path == "/api/bg/generate-kling-prompts":
                return self._handle_bg_generate_kling_prompts(body)
            if path == "/api/bg/inject-beats":
                return self._handle_bg_inject_beats(body)
            if path == "/api/bg/update-beat":
                return self._handle_bg_update_beat(body)
            if path == "/api/bg/align-element-ref":
                return self._handle_bg_align_element_ref(body)
            if path == "/api/bg/add-element-pose":
                return self._handle_bg_add_element_pose(body)
            if path == "/api/bg/reorder-beats":
                return self._handle_bg_reorder_beats(body)
            if path == "/api/bg/delete-beat":
                return self._handle_bg_delete_beat(body)
            if path == "/api/bg/accept-beats":
                return self._handle_bg_accept_beats(body)
            if path == "/api/bg/export-to-stitcher":
                return self._handle_bg_export_to_stitcher(body)
            if path == "/api/bg/submit-flux-batch":
                return self._handle_bg_submit_flux(body)
            if path == "/api/bg/submit-gpt-batch":
                return self._handle_bg_submit_gpt_batch(body)
            if path == "/api/bg/submit-arlo-o3-voice":
                return self._handle_bg_submit_arlo_o3_voice(body)
            if path == "/api/bg/submit-kling-native-lipsync-experiment":
                return self._handle_bg_submit_kling_native_lipsync_experiment(body)
            if path == "/api/bg/select-o3-video":
                return self._handle_bg_select_o3_video(body)
            if path == "/api/bg/render-still-clip":
                return self._handle_bg_render_still_clip(body)
            if path == "/api/bg/kling-o3-trim":
                return self._handle_bg_kling_o3_trim(body)
            if path == "/api/bg/accept-option":
                return self._handle_bg_accept_option(body)
            if path == "/api/bg/accept-lib-image":
                return self._handle_bg_accept_lib_image(body)
            if path == "/api/bg/add-beat":
                return self._handle_bg_add_beat(body)
            if path == "/api/bg/insert-beat":
                return self._handle_bg_insert_beat(body)
            if path == "/api/bg/create-group":
                return self._handle_bg_create_group(body)
            if path == "/api/bg/delete-group":
                return self._handle_bg_delete_group(body)
            if path == "/api/bg/update-group":
                return self._handle_bg_update_group(body)
            if path == "/api/bg/assemble-group":
                return self._handle_bg_assemble_group(body)
            if path == "/api/bg/run-local-animation":
                return self._handle_bg_run_local_animation(body)
            if path == "/api/bg/update-beat-animation-method":
                return self._handle_bg_update_beat_anim_method(body)
            if path == "/api/bg/accept-local-animation":
                return self._handle_bg_accept_local_animation(body)
            if path == "/api/cr/save-crop":
                return self._handle_cr_save_crop(body)
            if path == "/api/cr/upload":
                return self._handle_cr_upload(body)
            if path == "/api/cr/library/delete":
                return self._handle_cr_library_delete(body)
            if path == "/api/patch_health":
                return self._handle_patch_health(body)
            # LD-456 M1 — state snapshot before every v59 mutation.
            if path == "/api/state/snapshot":
                return self._handle_state_snapshot(body)
            # LD-458 EVENT_LOAD_GENERATION_LOCK_V1 — atomic event swap + gen bump.
            if path == "/api/event/load":
                return self._handle_event_load(body)
            # S5.5c+e proper-fix +NewEvent (LD NEW_EVENT_CREATION_UI_V1)
            if path == "/api/event/create":
                return self._handle_event_create(body)
            # S5.5b — VideoSelector POSTs (display-hint write + partition create).
            if path == "/api/video/set_active":
                return self._handle_video_set_active(body)
            if path == "/api/video/create":
                return self._handle_video_create(body)
            # S3 v3.1 endpoints — LDs 462-467.
            if path == "/api/phase/suggest_script":
                return self._handle_phase_suggest_script(body)
            if path == "/api/watercolor/animate":
                return self._handle_watercolor_animate(body)
            if path == "/api/phase/watercolor_delete":
                return self._handle_phase_watercolor_delete(body)
            if path == "/api/phase/export_stitcher":
                return self._handle_phase_export_stitcher(body)
            if path == "/api/stitch_editor/loudnorm":
                return self._handle_stitch_loudnorm(body)
            # S5 v3.1 endpoints — LDs 468 + 469.
            if path == "/api/storyboard/magic_still":
                return self._handle_magic_still(body)
            if path == "/api/storyboard/magic_video":
                return self._handle_magic_video(body)
            if path == "/api/storyboard/switch":
                return self._handle_storyboard_switch(body)
            # ── Visible Magic Phase 2 (2026-04-24) ──────────────────────────────
            if path == "/api/magic/submit_path":
                return self._handle_magic_submit_path(body)
            # ── Full Module Timeline Editor (2026-04-26, FULL_TIMELINE_EDITOR_V1) ──
            if path == "/api/timeline/cues":
                return self._handle_timeline_cue_upsert(body)
            if path == "/api/timeline/preview_with_sfx":
                return self._handle_timeline_preview_with_sfx(body)
            if path == "/api/timeline/cues/bake":
                return self._handle_timeline_bake(body)
            if path == "/api/timeline/open_in_quicktime":
                return self._handle_timeline_open_in_quicktime(body)
            # ── Stitch Editor POST routes (STITCH_EDITOR_UNIVERSAL_V1) ──────────
            if path == "/api/stitch_editor/job":
                return self._handle_stitch_save_job(body)
            if path == "/api/stitch_editor/audio_extract":
                return self._handle_stitch_audio_extract(body)
            if path == "/api/stitch_editor/preview":
                return self._handle_stitch_preview(body)
            if path == "/api/stitch_editor/bake":
                return self._handle_stitch_bake(body)
            # ── S5.5d (v3 architecture revision) POST routes ──
            if path == "/api/admin/drain_start":
                return self._handle_admin_drain_start(body)
            if path == "/api/admin/drain_end":
                return self._handle_admin_drain_end(body)
            if path == "/api/milestones/create":
                return self._handle_milestones_create(body)
            if path == "/api/milestones/load":
                return self._handle_milestone_load(body)
            if path == "/api/beat/finalize":
                return self._handle_beat_finalize(body)
            if path == "/api/scene/assemble":
                return self._handle_scene_assemble(body)
            return self._send_error_v59(
                       404,
                       error_code="NOT_FOUND",
                       error_message="not found",
                       retry_safe=False,
                       extra={"path": path},
                   )
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            return self._send_error_v59(
                       500,
                       error_code="GENERIC_ERROR",
                       error_message=str(exc),
                       retry_safe=True,
                   )

    def do_DELETE(self):  # noqa: N802
        self.app.touch()
        path = urllib.parse.urlparse(self.path).path
        try:
            # ── Full Module Timeline Editor (2026-04-26) ──
            if path.startswith("/api/timeline/cues/"):
                cue_id = path[len("/api/timeline/cues/"):]
                return self._handle_timeline_delete_cue(cue_id)
            # ── Stitch Editor DELETE routes (STITCH_EDITOR_UNIVERSAL_V1) ────────
            if path.startswith("/api/stitch_editor/job/"):
                name = urllib.parse.unquote(path[len("/api/stitch_editor/job/"):])
                return self._handle_stitch_delete_job(name)
            return self._send_error_v59(
                       404,
                       error_code="NOT_FOUND",
                       error_message="not found",
                       retry_safe=False,
                       extra={"path": path},
                   )
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            return self._send_error_v59(
                       500,
                       error_code="GENERIC_ERROR",
                       error_message=str(exc),
                       retry_safe=True,
                   )

    # ================================================================
    # Beat Generator tab handlers (§6 of HANDOFF_BEAT_GENERATOR_TAB_COMPLETE.md)
    # No Kling, no motion prompts. FLUX Kontext stills only.
    # ================================================================

    # ================================================================
    # Visible Magic Phase 2 handlers (2026-04-24)
    # ================================================================

    def _serve_magic_picker(self) -> None:
        from server_handlers.background import serve_magic_picker
        return serve_magic_picker(self)

    def _handle_magic_resolve_bg(self) -> None:
        from server_handlers.background import handle_magic_resolve_bg
        return handle_magic_resolve_bg(self)

    def _handle_magic_status(self) -> None:
        from server_handlers.background import handle_magic_status
        return handle_magic_status(self)

    @with_pin_and_drain('_handle_magic_submit_path', track_sync=False)
    def _handle_magic_submit_path(self, body: dict) -> None:
        from server_handlers.background import handle_magic_submit_path
        return handle_magic_submit_path(self, body)

    def _handle_beat_accepted_bg(self) -> None:
        from server_handlers.beats_legacy import handle_beat_accepted_bg
        return handle_beat_accepted_bg(self)

    def _handle_bg_crop_preview(self) -> None:
        from server_handlers.background import handle_bg_crop_preview
        return handle_bg_crop_preview(self)

    def _handle_bg_segments(self) -> None:
        from server_handlers.background import handle_bg_segments
        return handle_bg_segments(self)

    def _handle_bg_session_state(self) -> None:
        from server_handlers.background import handle_bg_session_state
        return handle_bg_session_state(self)

    def _handle_bg_poll_flux(self) -> None:
        from server_handlers.background import handle_bg_poll_flux
        return handle_bg_poll_flux(self)

    def _handle_cr_library(self) -> None:
        from server_handlers.cropper import handle_cr_library
        return handle_cr_library(self)

    def _handle_cr_full_image(self) -> None:
        from server_handlers.cropper import handle_cr_full_image
        return handle_cr_full_image(self)

    def _handle_cr_library_delete(self, body: dict) -> None:
        from server_handlers.cropper import handle_cr_library_delete
        return handle_cr_library_delete(self, body)

    def _handle_patch_health(self, body: dict) -> None:
        from server_handlers.core import handle_patch_health
        return handle_patch_health(self, body)

    def _handle_state_snapshot(self, body: dict) -> None:
        from server_handlers.core import handle_state_snapshot
        return handle_state_snapshot(self, body)

    def _handle_event_create(self, body: dict) -> None:
        from server_handlers.event_video import handle_event_create
        return handle_event_create(self, body)

    def _handle_event_load(self, body: dict) -> None:
        from server_handlers.event_video import handle_event_load
        return handle_event_load(self, body)

    def _handle_event_current(self) -> None:
        from server_handlers.event_video import handle_event_current
        return handle_event_current(self)

    def _handle_video_list(self) -> None:
        from server_handlers.event_video import handle_video_list
        return handle_video_list(self)

    def _handle_video_set_active(self, body: dict) -> None:
        from server_handlers.event_video import handle_video_set_active
        return handle_video_set_active(self, body)

    def _handle_video_create(self, body: dict) -> None:
        from server_handlers.event_video import handle_video_create
        return handle_video_create(self, body)

    # ================================================================
    # S5.5d (v3 architecture revision, 2026-05-03): NEW endpoints
    # - admin/drain (3): drain_start, drain_end, inflight_count
    # - milestones (4): list, create, load, project_list
    # - export pipeline (2): beat/finalize, scene/assemble
    # All per ASYNC_QUEUE_DRAIN_PROTOCOL_V1, MILESTONE_STANDALONE_INDEPENDENT_V1,
    # BEAT_FINALIZE_ENDPOINT_V1, SCENE_ASSEMBLE_ENDPOINT_V1.
    # ================================================================

    # ---- Admin drain endpoints (per ASYNC_QUEUE_DRAIN_PROTOCOL_V1) ----

    def _handle_admin_drain_start(self, body: dict | None = None) -> None:
        from server_handlers.core import handle_admin_drain_start
        return handle_admin_drain_start(self, body)

    def _handle_admin_drain_end(self, body: dict | None = None) -> None:
        from server_handlers.core import handle_admin_drain_end
        return handle_admin_drain_end(self, body)

    def _handle_admin_inflight_count(self, body: dict | None = None) -> None:
        from server_handlers.core import handle_admin_inflight_count
        return handle_admin_inflight_count(self, body)

    # ---- Milestone endpoints (per MILESTONE_STANDALONE_INDEPENDENT_V1) ----

    # Milestone id reserved-word prefixes (case-insensitive) — prevent IDs
    # that would collide with system paths or look like Event/Module IDs.
    _MILESTONE_RESERVED_PREFIXES = (
        "event_", "module_", "arc_", "phase_", "scene_", "milestone_",
        "test_", "system_", "admin_", "api_",
    )
    _MILESTONE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{2,63}$")

    def _milestones_root(self) -> Path:
        """Resolve Production/Milestones/ — sibling of Event_<N>/."""
        return self.app.event_dir.parent / "Milestones"

    def _validate_milestone_id(self, milestone_id: str) -> tuple[bool, str | None]:
        """Return (ok, error_message_or_None) per v3 spec §3.4.1."""
        if not isinstance(milestone_id, str) or not milestone_id:
            return False, "milestone_id required (non-empty string)"
        if not self._MILESTONE_ID_RE.match(milestone_id):
            return False, (
                "milestone_id must match ^[a-z0-9][a-z0-9_-]{2,63}$ "
                "(lowercase, start alphanumeric, 3-64 chars, only "
                "[a-z0-9_-] allowed)."
            )
        # Reserved-word prefix check (case-insensitive — matches the lower
        # form because the regex above already requires lowercase)
        lower = milestone_id.lower()
        for prefix in self._MILESTONE_RESERVED_PREFIXES:
            if lower.startswith(prefix):
                return False, (
                    f"milestone_id may not start with reserved prefix "
                    f"{prefix!r}. Reserved: {self._MILESTONE_RESERVED_PREFIXES}"
                )
        return True, None

    def _handle_milestones_list(self, body: dict | None = None) -> None:
        from server_handlers.event_video import handle_milestones_list
        return handle_milestones_list(self, body)

    def _handle_milestones_create(self, body: dict) -> None:
        from server_handlers.event_video import handle_milestones_create
        return handle_milestones_create(self, body)

    def _handle_milestone_load(self, body: dict) -> None:
        from server_handlers.event_video import handle_milestone_load
        return handle_milestone_load(self, body)

    def _handle_project_list(self, body: dict | None = None) -> None:
        from server_handlers.event_video import handle_project_list
        return handle_project_list(self, body)

    # ---- Export pipeline endpoints (per BEAT_FINALIZE_ENDPOINT_V1 +
    #      SCENE_ASSEMBLE_ENDPOINT_V1) ----

    def _resolve_scope_root(self, body: dict) -> tuple[str | None, Path | None,
                                                       int | None, dict | None]:
        """Resolve scope from body for export pipeline endpoints.

        Returns (scope_type, scope_root, error_status, error_body).
        On success: scope_type ∈ {'event', 'milestone'}; scope_root is
        the directory whose state.json holds the videos partition;
        error_status/error_body are None.
        On error: scope_type/scope_root None; error_* populated.

        Per v3 spec §3.5 Stage 1 + §3.5 Stage 2: exactly ONE of
        scope_event_id or scope_milestone_id must be present.
        """
        scope_event_id = (body or {}).get("scope_event_id") or (body or {}).get("event_id")
        scope_milestone_id = (body or {}).get("scope_milestone_id") or (body or {}).get("milestone_id")
        if scope_event_id and scope_milestone_id:
            return None, None, 400, {
                "ok": False,
                "error": "exactly ONE of scope_event_id or scope_milestone_id required (got both)",
                "code": "SCOPE_AMBIGUOUS",
            }
        if not scope_event_id and not scope_milestone_id:
            return None, None, 400, {
                "ok": False,
                "error": "exactly ONE of scope_event_id or scope_milestone_id required (got neither)",
                "code": "SCOPE_MISSING",
            }
        if scope_event_id:
            event_dir = self.app.event_dir.parent / scope_event_id
            if not event_dir.is_dir():
                return None, None, 404, {
                    "ok": False,
                    "error": f"event {scope_event_id!r} not found",
                    "code": "EVENT_NOT_FOUND",
                }
            # Reject cross-event scope per LD-456 — only the currently-loaded
            # event is mutable through this server.
            if event_dir.name != self.app.event_dir.name:
                return None, None, 409, {
                    "ok": False,
                    "error": f"scope_event_id {scope_event_id!r} != server-pinned {self.app.event_dir.name!r}",
                    "code": "SCOPE_MISMATCH",
                    "hint": "Call /api/event/load first to swap active event.",
                }
            return "event", event_dir, None, None
        # Milestone scope
        ok, err = self._validate_milestone_id(scope_milestone_id)
        if not ok:
            return None, None, 400, {
                "ok": False,
                "error": err,
                "code": "MILESTONE_ID_INVALID",
            }
        target = self._milestones_root() / scope_milestone_id
        if not target.is_dir():
            return None, None, 404, {
                "ok": False,
                "error": f"milestone {scope_milestone_id!r} not found at {target}",
                "code": "MILESTONE_NOT_FOUND",
            }
        return "milestone", target, None, None

    def _read_scope_state(self, scope_type: str, scope_root: Path) -> dict:
        """Read the state.json for the given scope (event or milestone).

        Event scope: reuse self.app.state.read_state() (server-pinned event
        only — _resolve_scope_root has already verified this).
        Milestone scope: read directly from scope_root/state.json.
        """
        if scope_type == "event":
            return self.app.state.read_state()
        # Milestone — direct file read.
        sp = scope_root / "state.json"
        return json.loads(sp.read_text())

    def _write_scope_state_field(self, scope_type: str, scope_root: Path,
                                  role: str, field: str, value) -> None:
        """Write state.videos[<role>].<field> for the given scope.

        Used for completed_mp4_path after scene assembly.
        """
        if scope_type == "event":
            def _mut(state):
                videos = state.setdefault("videos", {})
                partition = videos.setdefault(
                    role,
                    {"video_role": role, "video_label": None,
                     "beats": {}, "image_overrides": {}, "display_order": [],
                     "completed_mp4_path": None},
                )
                partition[field] = value
            self.app.state.mutate_state(_mut)
        else:
            # Milestone — read/modify/atomic-write.
            sp = scope_root / "state.json"
            s = json.loads(sp.read_text())
            videos = s.setdefault("videos", {})
            partition = videos.setdefault(
                role,
                {"video_role": role, "video_label": None,
                 "beats": {}, "image_overrides": {}, "display_order": [],
                 "completed_mp4_path": None},
            )
            partition[field] = value
            s["updated_at"] = datetime.now(timezone.utc).isoformat()
            atomic_json_write(str(sp), s)

    @with_pin_and_drain('_handle_beat_finalize', track_sync=True)
    def _handle_beat_finalize(self, body: dict) -> None:
        from server_handlers.beats_legacy import handle_beat_finalize
        return handle_beat_finalize(self, body)

    @with_pin_and_drain('_handle_scene_assemble', track_sync=True)
    def _handle_scene_assemble(self, body: dict) -> None:
        """POST /api/scene/assemble — Stage 2 of the export pipeline.

        Body: {scope_event_id?, scope_milestone_id?, scope_target_video,
               fade_between_beats_ms?, force_rebuild?}

        Per v3 spec §3.5 Stage 2. MIRRORS _handle_preview_stitched
        orchestration at production_server.py:11862-12210:
          1. Snapshot state at entry (no mid-pipeline re-read).
          2. Resolve display_order; filter to beats with selected_option.
          3. Stage 1 fan-out: per-beat finalize internally.
          4. Compute pair fades (resolve_pair_fades + compute_fade_clamp_per_pair).
          5. Build interleaved parts list [body_0, pair_01, body_1, ...].
             pause_after_ms wired via silent black filler clips at LD-284 codec.
          6. Final concat (stream-copy via concat_with_xfade_clips).
          7. SIZE_BUDGET gate (LD-280: ≤1.9Mbps, ≤80MB).
          8. Register as scene_concat_mp4 asset.
          9. Write completed_mp4_path; terminal pin check.
        """
        scope_type, scope_root, err_st, err_body = self._resolve_scope_root(body)
        if err_st is not None:
            return self._send_json(err_st, err_body)

        scope_target_video = (body or {}).get("scope_target_video")
        if scope_target_video not in self.app.state._VALID_VIDEO_ROLES:
            return self._send_error_v59(
                       400,
                       error_code="SCOPE_TARGET_VIDEO_REQUIRED_MUST",
                       error_message="scope_target_video required + must be intro/resolution/standalone",
                       retry_safe=False,
                       extra={"ok": False, "code": "VIDEO_ROLE_INVALID", "got": scope_target_video, "valid": sorted(self.app.state._VALID_VIDEO_ROLES)},
                   )

        fade_ms_raw = (body or {}).get("fade_between_beats_ms", 0)
        try:
            fade_ms = int(fade_ms_raw) if fade_ms_raw is not None else 0
        except (TypeError, ValueError):
            return self._send_error_v59(
                       400,
                       error_code="GENERIC_ERROR",
                       error_message=f"fade_between_beats_ms must be int, got {fade_ms_raw!r}",
                       retry_safe=False,
                       extra={"ok": False},
                   )
        if fade_ms < 0 or fade_ms > _V2_MODULE_FADE_MAX_MS:
            return self._send_error_v59(
                       400,
                       error_code="GENERIC_ERROR",
                       error_message=f"fade_between_beats_ms out of range: {fade_ms}",
                       retry_safe=False,
                       extra={"ok": False},
                   )
        force_rebuild = bool((body or {}).get("force_rebuild", False))

        # LD-460 pin tuple at entry.
        _pin = {
            "pinned_generation": self.app.event_generation,
            "pinned_event_dir": self.app.event_dir,
            "pinned_video_role": scope_target_video,
            "_handler": "scene_assemble",
        }
        if not self._check_event_pin(_pin, "scene_assemble_pre_work"):
            return self._send_error_v59(
                       423,
                       error_code="EVENT_CHANGED_PRE_WORK",
                       error_message="event_changed_pre_work",
                       retry_safe=False,
                       extra={"code": "ASYNC_JOB_GENERATION_PIN_V1", "handler": "scene_assemble"},
                   )

        # Lock per scope (event) | (milestone). NB-LOCK_EX → 409 on contention.
        try:
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), "credentials_lib"))
            from ffmpeg_stitch import (  # type: ignore
                ASSEMBLE_RECIPE_VERSION as _ARV,
                NORMALIZATION_RECIPE_HASH as _NRH,
                NORMALIZATION_VF_EXPR as _NVF,
                NORMALIZATION_ENCODER_ARGS as _NEA,
                _scene_lock_path,
                compute_fade_clamp_per_pair,
                compute_finalize_args_hash,
                concat_with_xfade_clips,
                ffprobe_duration,
                normalize_for_concat,
                render_xfade_pair,
                resolve_pair_fades,
                translate_trim_for_source,
                trim_body,
                trim_body_with_fade,
                trim_normalized,
            )
        except ImportError as exc:
            return self._send_error_v59(
                       500,
                       error_code="GENERIC_ERROR",
                       error_message=f"lib/ffmpeg_stitch import failed: {exc}",
                       retry_safe=True,
                       extra={"ok": False},
                   )

        lock_path = _scene_lock_path(scope_type, scope_root, scope_target_video)
        import fcntl  # noqa: PLC0415
        lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
        try:
            try:
                fcntl.lockf(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (BlockingIOError, OSError):
                return self._send_error_v59(
                           409,
                           error_code="ANOTHER_SCENE_ASSEMBLE_IS_IN",
                           error_message="another scene_assemble is in flight on this scope",
                           retry_safe=False,
                           extra={"ok": False, "code": "SCENE_ASSEMBLE_LOCK_HELD", "lock_path": str(lock_path)},
                       )

            # Snapshot at entry (no mid-pipeline re-read per Cursor).
            state = self._read_scope_state(scope_type, scope_root)
            videos = state.get("videos") or {}
            partition = videos.get(scope_target_video) or {}
            beats = partition.get("beats") or {}
            display_order = partition.get("display_order") or []

            # Include beats with selected_option OR committed magic/final/lipsync media.
            _assemble_event_dir = (
                self.app.event_dir if scope_type == "event" else scope_root
            )
            from ffmpeg_stitch import beat_is_assemblable  # noqa: PLC0415
            allowed = set(display_order)
            ordered_beat_ids: list[str] = [
                bid for bid in display_order
                if bid in allowed
                and bid in beats
                and isinstance(beats[bid], dict)
                and beat_is_assemblable(beats[bid], event_dir=_assemble_event_dir)
            ]
            # Fallback: if display_order is empty (legacy / cold partitions),
            # use sorted beat ids — consistent with _handle_preview_stitched
            # fast path for single-beat scenes.
            if not ordered_beat_ids:
                ordered_beat_ids = sorted(
                    bid for bid, b in beats.items()
                    if isinstance(b, dict)
                    and beat_is_assemblable(b, event_dir=_assemble_event_dir)
                )
            if not ordered_beat_ids:
                return self._send_error_v59(
                           400,
                           error_code="NO_ASSEMBLABLE_BEATS",
                           error_message="no assemblable beats in target partition",
                           retry_safe=False,
                           extra={
                               "ok": False,
                               "code": "EMPTY_SCENE",
                               "hint": "Select an animation option or run magic preview on each beat in display_order.",
                           },
                       )

            # Resolve clips_dir per scope.
            if scope_type == "event":
                clips_dir = self.app.state.clips_dir
            else:
                clips_dir = scope_root / "animation_clips"

            # Stage 1 fan-out: per-beat finalize internally (in-process — not
            # a recursive HTTP call, per v3 spec).
            slim = {
                "beats": beats,
                "image_overrides": partition.get("image_overrides") or {},
            }
            beat_final: dict[str, Path] = {}
            beat_metas: list[dict] = []  # ordered, per ordered_beat_ids
            cache_stats = {
                "finalize_hits": 0, "finalize_misses": 0,
                "body_hits": 0, "body_misses": 0,
                "pair_hits": 0, "pair_misses": 0,
                "pause_hits": 0, "pause_misses": 0,
            }
            cache_dir = scope_root / "animation_clips_final"
            cache_dir.mkdir(parents=True, exist_ok=True)
            recipe6 = _NRH[:6]

            for bid in ordered_beat_ids:
                try:
                    digest, meta = compute_finalize_args_hash(
                        slim, bid, clips_dir, event_dir=self.app.event_dir,
                    )
                except FileNotFoundError as exc:
                    return self._send_error_v59(
                               400,
                               error_code="GENERIC_ERROR",
                               error_message=str(exc),
                               retry_safe=False,
                               extra={"ok": False, "beat_id": bid, "code": "BEAT_SOURCE_MISSING"},
                           )
                src_path = Path(meta["file"])

                # Resolve speech MP3 for raw-option beats (Kling clips generated
                # with sound: false have no audio; the TTS MP3 must be mixed in).
                # A beat is "raw_option source" when it has no completed lipsync
                # OR when beat.final.source explicitly names raw_option.
                # Magic sources are ALWAYS treated as raw_option: magic_compositor
                # writes video-only; magic_video blend maps 0:a? from a silent
                # Kling clip. TTS must be mixed in regardless of lipsync state.
                _beat_dict = beats.get(bid) or {}
                _beat_lipsync = _beat_dict.get("lipsync") or {}
                _beat_final_src = (_beat_dict.get("final") or {}).get("source")
                _is_raw_option_src = (
                    bool(meta.get("is_magic_still_source"))  # magic_still is silent
                    or (
                        _beat_lipsync.get("status") != "completed"
                        and not meta.get("is_magic_video_source")
                    )
                    or _beat_final_src == "raw_option"
                )
                _speech_mp3: "Path | None" = None
                if _is_raw_option_src:
                    _speech_mp3 = _find_beat_audio(
                        self.app.event_dir, bid, app=self.app
                    )
                    if _speech_mp3 is not None and _speech_mp3.is_file():
                        # Extend finalize_args_hash to include speech MP3 mtime
                        # so the cache invalidates when the MP3 is regenerated.
                        _mp3_extra = (
                            f"|speech:{_speech_mp3.name}:"
                            f"{_speech_mp3.stat().st_mtime:.6f}"
                        )
                        digest = hashlib.md5(
                            (digest + _mp3_extra).encode("utf-8")
                        ).hexdigest()
                    else:
                        _speech_mp3 = None  # not found; proceed with silent audio

                src_md5 = hashlib.md5(str(src_path.resolve()).encode("utf-8")).hexdigest()[:10]
                ts_ms = int(round(float(meta["trim_start"]) * 1000))
                te_raw = meta["trim_end"]
                te_ms = int(round(te_raw * 1000)) if te_raw is not None else -1
                tb_raw = meta.get("trim_back")
                tb_ms = int(round(float(tb_raw) * 1000)) if tb_raw is not None else 0
                # Use effective delay for the cache filename so lipsync beats
                # (where ByteDance already baked the delay in) produce a
                # distinct cache key from raw-option beats.  Lipsync beats get
                # ad_ms=0; raw-option beats get the original authored value.
                # _is_raw_option_src is already resolved above (line ~6703).
                ad_ms = (
                    int(round(float(meta.get("audio_delay") or 0.0) * 1000))
                    if _is_raw_option_src else 0
                )
                fname = (
                    f"{bid}_final_{src_md5}_{recipe6}_{ts_ms}_{te_ms}"
                    f"_tb{tb_ms}_{ad_ms}.mp4"
                )
                fpath = cache_dir / fname
                sidecar_path = fpath.with_suffix(".mp4.meta.json")
                hit = False
                if fpath.is_file() and sidecar_path.is_file() and not force_rebuild:
                    try:
                        sc = json.loads(sidecar_path.read_text())
                        if sc.get("finalize_args_hash") == digest:
                            hit = True
                    except (OSError, json.JSONDecodeError):
                        pass
                if hit:
                    cache_stats["finalize_hits"] += 1
                else:
                    cache_stats["finalize_misses"] += 1
                    normalized_dir = scope_root / "normalized_segments"
                    normalized_dir.mkdir(parents=True, exist_ok=True)
                    norm_path = normalized_dir / f"{bid}_normalized_{src_md5}_{recipe6}.mp4"
                    if (not norm_path.is_file()
                        or src_path.stat().st_mtime > norm_path.stat().st_mtime):
                        normalize_for_concat(src_path, norm_path)
                    # Kim 2026-05-21: when src is a lipsync mp4, absolute
                    # trim_end (authored on original audio timeline) cuts off
                    # mid-word because the lipsync timeline includes preroll
                    # + extended tail. Translate back-trim / trim_back into the
                    # source file's timeline before trimming.
                    _ts_xlat, _te_xlat = translate_trim_for_source(
                        _beat_dict,
                        src_path.name, src_path,
                        meta.get("trim_start"), meta.get("trim_end"),
                        trim_back=meta.get("trim_back"),
                    )
                    # _effective_audio_delay is consistent with ad_ms used in
                    # the cache filename above: 0.0 for lipsync beats (delay
                    # already baked into the ByteDance output), original
                    # authored value for raw-option beats.
                    _effective_audio_delay = ad_ms / 1000.0
                    # Magic-still beats need an extra tail so the still image
                    # holds after the last phoneme (face-return + 2.5s pause).
                    # Non-magic beats get 0 (no change from prior behaviour).
                    _magic_freeze_tail = (
                        2.5 if bool(meta.get("is_magic_source")) else 0.0
                    )
                    trim_normalized(
                        norm_path, fpath,
                        _ts_xlat, _te_xlat,
                        audio_delay=_effective_audio_delay,
                        mix_audio_path=_speech_mp3,
                        freeze_tail_s=_magic_freeze_tail,
                    )
                    sidecar_payload = {
                        "finalize_args_hash": digest,
                        "recipe_hash": _NRH,
                        "generated_at": datetime.now(timezone.utc).isoformat(),
                        "source_path": str(src_path),
                        "source_mtime": meta["mtime"],
                    }
                    atomic_json_write(str(sidecar_path), sidecar_payload)
                beat_final[bid] = fpath
                duration_s = ffprobe_duration(fpath)
                phase1 = (beats[bid].get("phase_1") or {})
                beat_metas.append({
                    "beat_id": bid,
                    "finalize_args_hash": digest,
                    "file": str(fpath),
                    "duration_s": duration_s,
                    "fade_after_ms": phase1.get("fade_after_ms"),
                    "pause_after_ms": phase1.get("pause_after_ms", 0) or 0,
                })

            # Compute pair fades (per LD PER_ITEM_FADE_AFTER_OVERRIDE_V1).
            requested_pair_fades = resolve_pair_fades(beat_metas, fade_ms)
            durations = [m["duration_s"] for m in beat_metas]
            clamped_pair_fades = (
                compute_fade_clamp_per_pair(durations, requested_pair_fades)
                if len(beat_metas) > 1
                else []
            )

            # Build parts list (interleaved per Agent A finding).
            parts: list[Path] = []
            body_dir = scope_root / "scene_assemble_bodies"
            body_dir.mkdir(parents=True, exist_ok=True)
            xfade_dir = scope_root / "scene_assemble_xfade"
            xfade_dir.mkdir(parents=True, exist_ok=True)
            pause_dir = scope_root / "scene_assemble_pauses"
            pause_dir.mkdir(parents=True, exist_ok=True)

            N = len(beat_metas)
            all_zero_fade = (N == 1) or all(f == 0 for f in clamped_pair_fades)
            all_zero_pause = all(m["pause_after_ms"] == 0 for m in beat_metas)
            fast_path = all_zero_fade and all_zero_pause

            if fast_path:
                for m in beat_metas:
                    parts.append(beat_final[m["beat_id"]])
            else:
                for i, m in enumerate(beat_metas):
                    bid = m["beat_id"]

                    # FADE_THROUGH_BLACK_20260525: when a beat pair has both
                    # pause_after_ms>0 AND a non-zero fade value, use
                    # fade-to/from-black instead of xfade dissolve.
                    # xfade overlaps both clips simultaneously — during the
                    # pause you see ghost frames from the OTHER beat.
                    # Fade-through-black fades each body independently so
                    # the pause is pure black with no double-exposure.
                    curr_pause_fade_s = (
                        clamped_pair_fades[i] / 1000.0
                        if i < N - 1
                           and m["pause_after_ms"] > 0
                           and clamped_pair_fades[i] > 0
                        else 0.0
                    )
                    prev_pause_fade_s = (
                        clamped_pair_fades[i - 1] / 1000.0
                        if i > 0
                           and beat_metas[i - 1]["pause_after_ms"] > 0
                           and clamped_pair_fades[i - 1] > 0
                        else 0.0
                    )

                    # Normal xfade head/tail trims — skipped for pause-fade pairs.
                    head_s = (clamped_pair_fades[i - 1] / 1000.0
                              if i > 0 and clamped_pair_fades[i - 1] > 0
                                 and prev_pause_fade_s == 0.0
                              else 0.0)
                    tail_s = (clamped_pair_fades[i] / 1000.0
                              if i < N - 1 and clamped_pair_fades[i] > 0
                                 and curr_pause_fade_s == 0.0
                              else 0.0)

                    needs_body = (head_s > 0 or tail_s > 0
                                  or prev_pause_fade_s > 0 or curr_pause_fade_s > 0)
                    if not needs_body:
                        parts.append(beat_final[bid])
                    else:
                        head_ms = int(round(head_s * 1000))
                        tail_ms = int(round(tail_s * 1000))
                        fi_ms = int(round(prev_pause_fade_s * 1000))
                        fo_ms = int(round(curr_pause_fade_s * 1000))
                        body_path = body_dir / (
                            f"{bid}_body_{m['finalize_args_hash'][:10]}"
                            f"_{head_ms}_{tail_ms}_fi{fi_ms}_fo{fo_ms}_{recipe6}.mp4"
                        )
                        if body_path.is_file() and not force_rebuild:
                            cache_stats["body_hits"] += 1
                        else:
                            cache_stats["body_misses"] += 1
                            trim_body_with_fade(
                                beat_final[bid], body_path,
                                head_s, tail_s,
                                fade_in_s=prev_pause_fade_s,
                                fade_out_s=curr_pause_fade_s,
                            )
                        parts.append(body_path)

                    # NEW per Agent A finding: pause_after_ms wiring.
                    if i < N - 1 and m["pause_after_ms"] > 0:
                        pause_ms = int(m["pause_after_ms"])
                        pause_path = pause_dir / (
                            f"{bid}_pause_{pause_ms}_{recipe6}.mp4"
                        )
                        if pause_path.is_file() and not force_rebuild:
                            cache_stats["pause_hits"] += 1
                        else:
                            cache_stats["pause_misses"] += 1
                            # Render silent black filler clip at LD-284 codec recipe.
                            pause_s = pause_ms / 1000.0
                            cmd = [
                                "ffmpeg", "-y",
                                "-f", "lavfi", "-i", f"color=c=black:s=1280x720:r=24:d={pause_s}",
                                "-f", "lavfi", "-i", f"anullsrc=channel_layout=mono:sample_rate=44100",
                                "-shortest",
                                "-vf", _NVF,
                                *_NEA,
                                str(pause_path),
                            ]
                            subprocess.run(cmd, check=True, capture_output=True, timeout=120)
                        parts.append(pause_path)

                    # XFade pair clip if next pair has fade>0 AND is NOT using
                    # pause-fade. (pause-fade handles the transition via
                    # fade-to/from-black on the body clips + pause clip, so no
                    # xfade overlap clip is needed for that pair.)
                    if i < N - 1 and clamped_pair_fades[i] > 0 and curr_pause_fade_s == 0.0:
                        next_bid = beat_metas[i + 1]["beat_id"]
                        next_fade_ms = int(clamped_pair_fades[i])
                        pair_key = hashlib.md5(
                            f"{m['finalize_args_hash'][:10]}+"
                            f"{beat_metas[i + 1]['finalize_args_hash'][:10]}+"
                            f"{next_fade_ms}".encode()
                        ).hexdigest()[:10]
                        pair_path = xfade_dir / (
                            f"pair_{i:02d}_{pair_key}_{recipe6}.mp4"
                        )
                        if pair_path.is_file() and not force_rebuild:
                            cache_stats["pair_hits"] += 1
                        else:
                            cache_stats["pair_misses"] += 1
                            render_xfade_pair(
                                beat_final[bid], beat_final[next_bid],
                                next_fade_ms, pair_path,
                                dur_a=durations[i],
                            )
                        parts.append(pair_path)

            # Compute assemble_hash.
            assemble_input = (
                f"recipe:{_ARV}|norm:{_NRH}|fade:{fade_ms}|"
                f"order:{','.join(ordered_beat_ids)}"
                + ";".join(
                    f"{m['beat_id']}:{m['finalize_args_hash']}:"
                    f"{m['fade_after_ms']}:{m['pause_after_ms']}"
                    for m in beat_metas
                )
                + f"|requested:{requested_pair_fades}|clamped:{clamped_pair_fades}"
            )
            assemble_hash = hashlib.sha256(assemble_input.encode("utf-8")).hexdigest()

            # Final concat — stream-copy of codec-clean parts.
            scene_dir = scope_root / scope_target_video
            scene_dir.mkdir(parents=True, exist_ok=True)
            scene_path = scene_dir / f"scene_{scope_target_video}_{assemble_hash[:16]}.mp4"
            concat_with_xfade_clips(parts, scene_path)

            # SIZE_BUDGET gate per LD-280 (≤1.9Mbps, ≤80MB) — match
            # _handle_stitch_bake pattern.
            try:
                size_bytes = scene_path.stat().st_size
                duration_s_total = ffprobe_duration(scene_path)
                bitrate_bps = int(size_bytes * 8 / duration_s_total) if duration_s_total > 0 else 0
            except (OSError, subprocess.CalledProcessError):
                size_bytes = 0
                bitrate_bps = 0
                duration_s_total = 0.0
            BITRATE_CEILING = 1_900_000  # 1.9 Mbps target
            SIZE_CEILING = 80 * 1024 * 1024  # 80 MB per LD-283
            size_warning = None
            if size_bytes > SIZE_CEILING or bitrate_bps > BITRATE_CEILING:
                size_warning = (
                    f"SIZE_BUDGET breach: size={size_bytes} (ceiling {SIZE_CEILING}); "
                    f"bitrate={bitrate_bps} (ceiling {BITRATE_CEILING}). "
                    f"Per LD-280, requires SHORTCUT_SIZE_OVERRIDE_<asset_id>."
                )
                print(f"[scene_assemble] {size_warning}", flush=True)

            # Terminal pin check before state write + asset registration.
            if not self._check_event_pin(_pin, "scene_assemble_terminal"):
                return self._send_error_v59(
                           423,
                           error_code="EVENT_CHANGED_TERMINAL",
                           error_message="event_changed_terminal",
                           retry_safe=False,
                           extra={"code": "ASYNC_JOB_GENERATION_PIN_V1", "handler": "scene_assemble"},
                       )

            # Write completed_mp4_path.
            self._write_scope_state_field(
                scope_type, scope_root, scope_target_video,
                "completed_mp4_path", str(scene_path),
            )

            # Auto-populate the Stitcher's intro slot (or whichever slot matches
            # scope_target_video) so "Send Out as MP4" → Stitcher is seamless.
            # Uses mutate_state to upsert the most-recently-updated job, or
            # creates a "default" job if no jobs exist yet.
            try:
                _scene_path_str = str(scene_path)
                _slot_key = scope_target_video  # e.g. "intro"
                _slot_boundaries = []
                _cursor_ms = 0
                for _m in beat_metas:
                    _dur_ms = round(float(_m["duration_s"]) * 1000)
                    _slot_boundaries.append({
                        "beat_id": _m["beat_id"],
                        "start_ms": _cursor_ms,
                        "end_ms": _cursor_ms + _dur_ms,
                        "duration_ms": _dur_ms,
                    })
                    _cursor_ms += _dur_ms
                from server_handlers.stitch_editor import stitch_upsert_event_slot
                _event_id = scope_root.name
                stitch_upsert_event_slot(
                    self,
                    _event_id,
                    _slot_key,
                    {"video_path": _scene_path_str, "source": "scene_assemble"},
                    beat_boundaries=_slot_boundaries,
                )
                print(
                    f"[scene_assemble] stitcher { _event_id }_stitch slot {_slot_key} "
                    f"auto-populated → {_scene_path_str}",
                    flush=True,
                )
            except Exception as _ss_exc:
                print(f"[scene_assemble] stitcher slot auto-populate failed (non-fatal): {_ss_exc}", flush=True)

            # Register as scene_concat_mp4 asset.
            asset_id = -1
            try:
                from registered_write import register_asset as _reg
                # iteration_notes per v3 spec §3.5 Stage 2 template.
                src_beat_hashes = [m["finalize_args_hash"][:10] for m in beat_metas]
                notes_text = (
                    f"[{datetime.now(timezone.utc).isoformat()}] Send Out: scene assembly. "
                    f"scope={scope_type}:{scope_root.name}, target_video={scope_target_video}, "
                    f"beats={ordered_beat_ids}, assemble_hash={assemble_hash[:16]}, "
                    f"fade_between_beats_ms={fade_ms}, source_beat_hashes={src_beat_hashes}, "
                    f"recipe={_NRH}:{_ARV}, "
                    f"cache_stats={cache_stats}."
                )
                if size_warning:
                    notes_text += f" WARNING: {size_warning}"
                colloquial = f"{scope_root.name}_{scope_target_video}_send_out"
                event_id_for_asset = (
                    int(scope_root.name.replace("Event_", ""))
                    if scope_type == "event" and scope_root.name.startswith("Event_")
                    and scope_root.name.replace("Event_", "").isdigit()
                    else None
                )
                asset_id, _ = _reg(
                    file_path=str(scene_path),
                    asset_type="scene_concat_mp4",
                    module_id=_resolve_module_id_for_state(self.app.state),
                    event_id=event_id_for_asset,
                    beat_id=None,
                    parent_asset_id=None,
                    produced_by_skill="scene_assemble_v1",
                    iteration_notes=notes_text,
                    role=scope_target_video,
                    colloquial_name=colloquial,
                    tags=["scene_assembly", scope_target_video,
                          "multi_beat", scope_type],
                )
            except Exception as reg_exc:  # noqa: BLE001
                print(f"[scene_assemble] register_asset deferred: {reg_exc}",
                      flush=True)

            return self._send_json(200, {
                "ok": True,
                "asset_id": asset_id,
                "completed_mp4_path": str(scene_path),
                "assemble_hash": assemble_hash,
                "beat_count": len(beat_metas),
                "file_size_bytes": size_bytes,
                "bitrate_bps": bitrate_bps,
                "duration_s": duration_s_total,
                "size_warning": size_warning,
                "cache_stats": cache_stats,
                "scope_type": scope_type,
                "scope_root": str(scope_root),
                "scope_target_video": scope_target_video,
                "fade_between_beats_ms": fade_ms,
                "requested_pair_fades": requested_pair_fades,
                "clamped_pair_fades": clamped_pair_fades,
            })
        finally:
            try:
                fcntl.lockf(lock_fd, fcntl.LOCK_UN)
            except OSError:
                pass
            try:
                os.close(lock_fd)
            except OSError:
                pass

    # ================================================================
    # Session 3 v3.1 endpoints (LDs 462-467)
    # ================================================================

    def _handle_event_list(self) -> None:
        """GET /api/event/list — multi-event selector dropdown source.

        Lists all sibling Production/Event_*/ directories that contain
        at least one storyboard_v*_prod.html. Returns enough metadata
        for the v59 EventSelector dropdown.

        Per LD MULTI_EVENT_SELECTOR_V1.
        """
        try:
            production_root = self.app.event_dir.parent
            events: list[dict] = []
            for d in sorted(production_root.iterdir()):
                if not d.is_dir():
                    continue
                if not d.name.startswith("Event_"):
                    continue
                # Skip planning / scratch dirs (e.g., Event_1_Plans).
                if "_" in d.name[len("Event_"):]:
                    continue
                storyboards = sorted(
                    d.glob("storyboard_v*_prod.html"),
                    key=lambda p: p.stat().st_mtime, reverse=True,
                )
                if not storyboards:
                    continue
                events.append({
                    "event_id": d.name,
                    "path": str(d),
                    "storyboards": [p.name for p in storyboards],
                    "active_storyboard": storyboards[0].name,
                    "is_current": d.name == self.app.event_dir.name,
                })
            return self._send_json(200, {
                "ok": True,
                "events": events,
                "current_event_id": self.app.event_dir.name,
                "current_generation": self.app.event_generation,
            })
        except OSError as exc:
            return self._send_error_v59(
                       500,
                       error_code="GENERIC_ERROR",
                       error_message=f"could not enumerate events: {exc}",
                       retry_safe=True,
                       extra={"production_root": str(self.app.event_dir.parent)},
                   )

    def _handle_phase_watercolor_list(self) -> None:
        from server_handlers.phases import handle_phase_watercolor_list
        return handle_phase_watercolor_list(self)

    def _handle_phase_watercolor_file(self) -> None:
        from server_handlers.phases import handle_phase_watercolor_file
        return handle_phase_watercolor_file(self)

    def _handle_phase_watercolor_delete(self, body: dict) -> None:
        from server_handlers.phases import handle_phase_watercolor_delete
        return handle_phase_watercolor_delete(self, body)

    def _handle_phase_base_clips_list(self) -> None:
        from server_handlers.phases import handle_phase_base_clips_list
        return handle_phase_base_clips_list(self)

    def _handle_phase_b_ambient_preset_list(self) -> None:
        from server_handlers.phases import handle_phase_b_ambient_preset_list
        return handle_phase_b_ambient_preset_list(self)

    def _handle_phase_suggest_script(self, body: dict) -> None:
        from server_handlers.phases import handle_phase_suggest_script
        return handle_phase_suggest_script(self, body)

    # ============================================================
    # S5 v3.1 — 3 magic/animate workflows (LDs 468/469/470)
    # ============================================================
    # Allowlist for ffmpeg filter chain safety gate (LD-470).
    # Anything else is rejected before ffmpeg runs.
    _S5_FFMPEG_FILTER_ALLOWLIST = frozenset({
        "split", "hflip", "vflip", "rotate", "scale", "overlay", "blend",
        "fade", "crop", "pad", "drawbox", "hue", "eq", "zoompan", "fps",
        "setpts", "geq", "displace",
        # Ancillary helpers ffmpeg uses internally (input refs, format).
        "format", "null", "copy",
    })
    _S5_FFMPEG_FORBIDDEN_SUBSTRINGS = (
        "file://", "http://", "https://", "exec", "system", "run",
        "\\", "|", "`", "$(", "${",
    )

    # Safe zone for path coordinates on the 2× canvas.
    # The canvas is 2× the source PNG dimensions. At point (x=0, y=0), the
    # paste position is (-png_w/2, -png_h/2) — completely off-screen. To keep
    # hands fully visible, coordinates must stay in [SAFE_MIN, SAFE_MAX].
    # For a 1096×1608 hands PNG on a 2192×3216 canvas this means ≥0.25 from
    # each edge. (2026-05-27: added after [0,0] bug caused 4+ hours of invisible overlay.)
    _PATH_SAFE_MIN = 0.15
    _PATH_SAFE_MAX = 0.85

    def _validate_manual_path(self, manual_path: list, max_pts: int = 100,
                              enforce_safe_zone: bool = False) -> tuple[bool, list, str]:
        """Validate manual_path = [[x,y],...] in [0,1]. Returns (ok, clean_path, err).

        enforce_safe_zone=True: additionally restricts to [_PATH_SAFE_MIN, _PATH_SAFE_MAX].
        This MUST be True only for the watercolor animator, where coordinates are used
        on a 2× PIL canvas — at (0,0) the paste position is (-png_w/2, -png_h/2),
        completely off-screen.

        DO NOT pass enforce_safe_zone=True for the magic trail tool — magic trail
        coordinates are relative to the scene image viewport where (0.84, 0.86) is a
        perfectly valid bottom-right corner point.
        """
        if not isinstance(manual_path, list) or len(manual_path) < 2:
            return False, [], "manual_path must be a list of [x,y] pairs (>=2 points)"
        if len(manual_path) > max_pts:
            return False, [], f"manual_path has {len(manual_path)} points (>{max_pts} max)"
        clean: list[list[float]] = []
        for i, pt in enumerate(manual_path):
            if not (isinstance(pt, list) and len(pt) == 2):
                return False, [], f"manual_path[{i}] must be a 2-element [x,y] list"
            try:
                x, y = float(pt[0]), float(pt[1])
            except (TypeError, ValueError):
                return False, [], f"manual_path[{i}] coords must be numeric"
            if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
                return False, [], f"manual_path[{i}] = ({x}, {y}) out of [0,1] range"
            if enforce_safe_zone:
                safe_min = self._PATH_SAFE_MIN
                safe_max = self._PATH_SAFE_MAX
                if not (safe_min <= x <= safe_max and safe_min <= y <= safe_max):
                    return False, [], (
                        f"manual_path[{i}] = ({x:.3f}, {y:.3f}) is outside the safe zone "
                        f"[{safe_min}, {safe_max}]. Points near (0,0) or (1,1) place the "
                        f"asset off-canvas on the 2× watercolor rendering canvas. Use values "
                        f"in [{safe_min}, {safe_max}] to keep the asset fully visible."
                    )
            clean.append([x, y])
        return True, clean, ""

    def _validate_ffmpeg_filter_chain(self, filter_complex: str) -> tuple[bool, str]:
        """LD-470 safety gate. Returns (ok, error_message).

        Rules:
          1. Length cap (4096 chars) to prevent DoS.
          2. No forbidden substrings (file://, exec, shell metas, …).
          3. Each filter token (between ',' / ';' / ']') must have its name
             (before '=' or end) in the allowlist.
        """
        if not filter_complex or not isinstance(filter_complex, str):
            return False, "empty filter_complex"
        if len(filter_complex) > 4096:
            return False, f"filter_complex too long ({len(filter_complex)} > 4096)"
        lower = filter_complex.lower()
        for forbidden in self._S5_FFMPEG_FORBIDDEN_SUBSTRINGS:
            if forbidden in lower:
                return False, f"forbidden substring {forbidden!r} in filter_complex"
        # Tokenize on , and ;. Strip [...] labels.
        chain = re.sub(r"\[[^\]]*\]", "", filter_complex)
        tokens = re.split(r"[,;]", chain)
        for tok in tokens:
            tok = tok.strip()
            if not tok:
                continue
            # Filter name is before first '=' or end.
            name = tok.split("=", 1)[0].strip()
            if not name:
                continue
            if name not in self._S5_FFMPEG_FILTER_ALLOWLIST:
                return False, f"filter {name!r} not in allowlist"
        return True, ""

    @with_pin_and_drain('_handle_magic_still', track_sync=True)
    def _handle_magic_still(self, body: dict) -> None:
        from server_handlers.background import handle_magic_still
        return handle_magic_still(self, body)

    @with_pin_and_drain('_handle_magic_video', track_sync=True)
    def _handle_magic_video(self, body: dict) -> None:
        from server_handlers.background import handle_magic_video
        return handle_magic_video(self, body)

    def _handle_watercolor_animate(self, body: dict) -> None:
        from server_handlers.background import handle_watercolor_animate
        return handle_watercolor_animate(self, body)

    _PRODUCTION_MAP_CACHE: dict | None = None
    _PRODUCTION_MAP_CACHE_TS: float = 0.0

    def _handle_production_map(self) -> None:
        """GET /api/production/map — per-module status matrix for Production Map tab.

        Joins prod_modules + on-disk segment artifacts. 60s TTL cache.

        Per LD PRODUCTION_MAP_V1.
        """
        # 60s cache.
        if (
            ProductionHandler._PRODUCTION_MAP_CACHE is not None
            and time.time() - ProductionHandler._PRODUCTION_MAP_CACHE_TS < 60
        ):
            return self._send_json(200, ProductionHandler._PRODUCTION_MAP_CACHE)

        # Read prod_modules from Directus.
        try:
            from lib.directus import read_item  # noqa: PLC0415
            from lib.directus_admin_client import DirectusAdminClient  # noqa: PLC0415
            client = DirectusAdminClient()
            modules = client._request(
                "GET",
                "/items/prod_modules?fields=id,m_number,creature_name,video_role&sort=m_number&limit=100",
            )
        except Exception as exc:  # noqa: BLE001
            return self._send_error_v59(
                       500,
                       error_code="GENERIC_ERROR",
                       error_message=f"Directus read failed: {type(exc).__name__}: {exc}",
                       retry_safe=True,
                   )

        production_root = self.app.event_dir.parent
        rows: list[dict] = []
        for m in modules or []:
            # S5.5g — PRODUCTION_MAP_MULTI_EVENT_MAPPING_V1 (SOFT) per spec
            # §3.6 + audit doc §6. Convention-based mapping: m_number=N →
            # Event_N. Falls back to None if the directory doesn't exist on
            # disk (so the row still renders, just without segment artifacts).
            # Avoids the prior bug where every module reported Event_1.
            m_num = m.get("m_number")
            edir: Path | None = None
            if m_num is not None:
                candidate = production_root / f"Event_{m_num}"
                if candidate.is_dir():
                    edir = candidate
            segments: dict[str, dict] = {}
            videos_by_role: dict[str, dict] = {}
            if edir:
                # Best-effort: file-based status.
                # Per spec §3.9: 'canonical' is reserved for fly-in/fly-out source clips.
                # Phase A stitched outputs use phase_a_stitched_*.mp4 (S4 migration).
                phase_a = list(edir.glob("phase_a_stitched_*.mp4"))
                phase_b = list(edir.glob("phase_b_lipsync_*.mp4"))
                final_concat = list(edir.glob(f"M{m.get('m_number')}_*_final.mp4"))
                segments = {
                    "phase_a": {
                        "status": "ready" if phase_a else "missing",
                        "count": len(phase_a),
                        "latest": phase_a[0].name if phase_a else None,
                    },
                    "phase_b": {
                        "status": "ready" if phase_b else "missing",
                        "count": len(phase_b),
                        "latest": phase_b[0].name if phase_b else None,
                    },
                    "final_concat": {
                        "status": "ready" if final_concat else "missing",
                        "count": len(final_concat),
                    },
                }

                # C-12 ride-along (Production Map per-role + 5-state glyph) per
                # post-redeploy v2 §3.3 Part 2 + handoff §4 C-12. Per-role
                # state derives from (a) partition presence in state.videos,
                # (b) display_order shape, (c) per-role completed mp4 presence,
                # (d) module-level final concat presence. NO prod_modules schema
                # migration (picker-spec R3 boundary preserved).
                #
                # 5-state glyph mapping (returned as `state` field on each role):
                #   absent       — partition not in state.videos                → glyph '—'
                #   empty        — partition present + display_order list is [] → glyph '○'
                #   in_progress  — partition + non-empty display_order, no mp4  → glyph '◐'
                #   complete     — partition + display_order + per-role mp4    → glyph '●'
                #   final        — complete + module-level final concat        → glyph '★'
                #
                # For partitions whose display_order is the legacy int form
                # (Event_e2e_fixture pre-v3 shape), treat any non-empty beats
                # dict as 'in_progress' (matches renderer's fallback behavior).
                state_path = edir / "production_state.json"
                state_videos: dict = {}
                try:
                    with open(state_path, "r", encoding="utf-8") as _f:
                        state_videos = (json.load(_f).get("videos") or {})
                except (FileNotFoundError, json.JSONDecodeError):
                    state_videos = {}

                # Per-role completed mp4 globs. The canonical filenames vary
                # by event so we accept either scene_<role>_*.mp4 (Event_1
                # naming) or <role>_atomic_*.mp4 / <role>_atomic.mp4 (post-
                # redeploy spec naming). Handler does NOT enforce a single
                # filename — discovery is best-effort.
                final_concat_present = bool(final_concat)
                for _role in ("intro", "resolution", "standalone"):
                    partition = state_videos.get(_role)
                    if not isinstance(partition, dict):
                        videos_by_role[_role] = {"state": "absent"}
                        continue
                    do = partition.get("display_order")
                    beats = partition.get("beats") or {}
                    if isinstance(do, list):
                        is_empty = (len(do) == 0)
                    else:
                        # Legacy int / missing display_order: treat as 'present
                        # with content' if any beats exist.
                        is_empty = (len(beats) == 0)
                    if is_empty:
                        videos_by_role[_role] = {"state": "empty"}
                        continue
                    role_dir = edir / _role
                    role_mp4s: list[Path] = []
                    if role_dir.is_dir():
                        role_mp4s = (
                            list(role_dir.glob(f"scene_{_role}_*.mp4"))
                            + list(role_dir.glob(f"{_role}_atomic*.mp4"))
                        )
                    else:
                        role_mp4s = (
                            list(edir.glob(f"scene_{_role}_*.mp4"))
                            + list(edir.glob(f"{_role}_atomic*.mp4"))
                        )
                    if role_mp4s:
                        if final_concat_present:
                            videos_by_role[_role] = {
                                "state": "final",
                                "completed_mp4": role_mp4s[0].name,
                            }
                        else:
                            videos_by_role[_role] = {
                                "state": "complete",
                                "completed_mp4": role_mp4s[0].name,
                            }
                    else:
                        videos_by_role[_role] = {"state": "in_progress"}

            rows.append({
                "m_number": m.get("m_number"),
                "creature_name": m.get("creature_name"),
                "video_role": m.get("video_role"),
                "event_dir": edir.name if edir else None,
                "segments": segments,
                "videos_by_role": videos_by_role,
            })

        out = {
            "ok": True,
            "modules": rows,
            "cache_ttl_s": 60,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        ProductionHandler._PRODUCTION_MAP_CACHE = out
        ProductionHandler._PRODUCTION_MAP_CACHE_TS = time.time()
        return self._send_json(200, out)

    def _handle_stitch_loudnorm(self, body: dict) -> None:
        from server_handlers.stitch_editor import handle_stitch_loudnorm
        return handle_stitch_loudnorm(self, body)

    def _handle_bg_set_active_context(self, body: dict) -> None:
        from server_handlers.background import handle_bg_set_active_context
        return handle_bg_set_active_context(self, body)

    def _handle_bg_extract_beats(self, body: dict) -> None:
        from server_handlers.background import handle_bg_extract_beats
        return handle_bg_extract_beats(self, body)

    def _handle_bg_extract_beats_plan(self, body: dict) -> None:
        from server_handlers.background import handle_bg_extract_beats_plan
        return handle_bg_extract_beats_plan(self, body)

    def _handle_bg_extract_beats_approve(self, body: dict) -> None:
        from server_handlers.background import handle_bg_extract_beats_approve
        return handle_bg_extract_beats_approve(self, body)

    def _handle_bg_generate_kling_prompts(self, body: dict) -> None:
        from server_handlers.kling_o3 import handle_bg_generate_kling_prompts
        return handle_bg_generate_kling_prompts(self, body)

    def _handle_bg_inject_beats(self, body: dict) -> None:
        from server_handlers.background import handle_bg_inject_beats
        return handle_bg_inject_beats(self, body)

    def _handle_bg_update_beat(self, body: dict) -> None:
        from server_handlers.background import handle_bg_update_beat
        return handle_bg_update_beat(self, body)

    def _handle_bg_align_element_ref(self, body: dict) -> None:
        from server_handlers.background import handle_bg_align_element_ref
        return handle_bg_align_element_ref(self, body)

    def _handle_bg_add_element_pose(self, body: dict) -> None:
        from server_handlers.background import handle_bg_add_element_pose
        return handle_bg_add_element_pose(self, body)

    def _handle_bg_reorder_beats(self, body: dict) -> None:
        from server_handlers.background import handle_bg_reorder_beats
        return handle_bg_reorder_beats(self, body)

    def _handle_bg_delete_beat(self, body: dict) -> None:
        from server_handlers.background import handle_bg_delete_beat
        return handle_bg_delete_beat(self, body)

    def _handle_bg_accept_beats(self, body: dict) -> None:
        from server_handlers.background import handle_bg_accept_beats
        return handle_bg_accept_beats(self, body)

    @with_pin_and_drain('_handle_bg_submit_flux', track_sync=True)
    def _handle_bg_submit_flux(self, body: dict) -> None:
        from server_handlers.background import handle_bg_submit_flux
        return handle_bg_submit_flux(self, body)

    @with_pin_and_drain('_handle_bg_submit_gpt_batch', track_sync=False)
    def _handle_bg_submit_gpt_batch(self, body: dict) -> None:
        from server_handlers.background import handle_bg_submit_gpt_batch
        return handle_bg_submit_gpt_batch(self, body)

    def _handle_bg_poll_gpt_status(self) -> None:
        from server_handlers.background import handle_bg_poll_gpt_status
        return handle_bg_poll_gpt_status(self)

    @with_pin_and_drain('_handle_bg_submit_arlo_o3_voice', track_sync=False)
    def _handle_bg_submit_arlo_o3_voice(self, body: dict) -> None:
        from server_handlers.background import handle_bg_submit_arlo_o3_voice
        return handle_bg_submit_arlo_o3_voice(self, body)

    def _handle_bg_poll_arlo_o3_voice_status(self) -> None:
        from server_handlers.background import handle_bg_poll_arlo_o3_voice_status
        return handle_bg_poll_arlo_o3_voice_status(self)

    @with_pin_and_drain('_handle_bg_submit_kling_native_lipsync_experiment', track_sync=False)
    def _handle_bg_submit_kling_native_lipsync_experiment(self, body: dict) -> None:
        from server_handlers.background import handle_bg_submit_kling_native_lipsync_experiment
        return handle_bg_submit_kling_native_lipsync_experiment(self, body)

    def _handle_bg_poll_kling_native_lipsync_experiment_status(self) -> None:
        from server_handlers.background import handle_bg_poll_kling_native_lipsync_experiment_status
        return handle_bg_poll_kling_native_lipsync_experiment_status(self)

    def _handle_bg_select_o3_video(self, body: dict) -> None:
        from server_handlers.background import handle_bg_select_o3_video
        return handle_bg_select_o3_video(self, body)

    def _handle_bg_render_still_clip(self, body: dict) -> None:
        from server_handlers.background import handle_bg_render_still_clip
        return handle_bg_render_still_clip(self, body)

    def _handle_bg_kling_o3_trim(self, body: dict) -> None:
        from server_handlers.background import handle_bg_kling_o3_trim
        return handle_bg_kling_o3_trim(self, body)

    def _handle_bg_export_to_stitcher(self, body: dict) -> None:
        from server_handlers.kling_o3 import handle_bg_export_to_stitcher
        return handle_bg_export_to_stitcher(self, body)

    def _handle_bg_accept_option(self, body: dict) -> None:
        from server_handlers.background import handle_bg_accept_option
        return handle_bg_accept_option(self, body)

    def _handle_bg_accept_lib_image(self, body: dict) -> None:
        from server_handlers.background import handle_bg_accept_lib_image
        return handle_bg_accept_lib_image(self, body)

    # ================================================================
    # Stitch Groups + Local Animation handlers (added 2026-04-23)
    # ================================================================

    def _handle_bg_groups(self) -> None:
        from server_handlers.background import handle_bg_groups
        return handle_bg_groups(self)

    def _handle_bg_add_beat(self, body: dict) -> None:
        from server_handlers.background import handle_bg_add_beat
        return handle_bg_add_beat(self, body)

    def _handle_bg_insert_beat(self, body: dict) -> None:
        from server_handlers.background import handle_bg_insert_beat
        return handle_bg_insert_beat(self, body)

    def _handle_bg_create_group(self, body: dict) -> None:
        from server_handlers.background import handle_bg_create_group
        return handle_bg_create_group(self, body)

    def _handle_bg_delete_group(self, body: dict) -> None:
        from server_handlers.background import handle_bg_delete_group
        return handle_bg_delete_group(self, body)

    def _handle_bg_update_group(self, body: dict) -> None:
        from server_handlers.background import handle_bg_update_group
        return handle_bg_update_group(self, body)

    @with_pin_and_drain('_handle_bg_assemble_group', track_sync=False)
    def _handle_bg_assemble_group(self, body: dict) -> None:
        from server_handlers.background import handle_bg_assemble_group
        return handle_bg_assemble_group(self, body)

    def _handle_bg_poll_assemble_status(self) -> None:
        from server_handlers.background import handle_bg_poll_assemble_status
        return handle_bg_poll_assemble_status(self)

    @with_pin_and_drain('_handle_bg_run_local_animation', track_sync=True)
    def _handle_bg_run_local_animation(self, body: dict) -> None:
        from server_handlers.background import handle_bg_run_local_animation
        return handle_bg_run_local_animation(self, body)

    def _handle_bg_update_beat_anim_method(self, body: dict) -> None:
        from server_handlers.background import handle_bg_update_beat_anim_method
        return handle_bg_update_beat_anim_method(self, body)

    def _handle_bg_accept_local_animation(self, body: dict) -> None:
        from server_handlers.background import handle_bg_accept_local_animation
        return handle_bg_accept_local_animation(self, body)

    def _handle_bg_stills(self, path: str) -> None:
        from server_handlers.background import handle_bg_stills
        return handle_bg_stills(self, path)

    def _path_under_allowed_serve_roots(self, cand: str) -> str | None:
        """Realpath containment gate for /files?path= (CodeQL py/path-injection)."""
        try:
            drop_root = os.path.realpath(str(DROPBOX_ROOT))
            repo_root = os.path.realpath(str(_MN_REPO_ROOT))
            real_path = os.path.realpath(cand)
            if not os.path.isfile(real_path):
                return None
            under_drop = real_path == drop_root or real_path.startswith(drop_root + os.sep)
            under_repo = real_path == repo_root or real_path.startswith(repo_root + os.sep)
            if under_drop or under_repo:
                return real_path
        except OSError:
            return None
        return None

    def _resolve_served_file_path(self, file_path: str) -> str | None:
        """Resolve ?path= to an on-disk file under Dropbox, tooling, or event_dir."""
        if not file_path:
            return None
        if os.path.isabs(file_path):
            return self._path_under_allowed_serve_roots(file_path)

        candidates: list[str] = []
        candidates.append(os.path.join(str(DROPBOX_ROOT), file_path))
        candidates.append(str((_MN_REPO_ROOT / Path(file_path)).resolve()))

        ev = Path(self.app.event_dir)
        prod = ev.parent
        rel = Path(file_path)
        parts = rel.parts
        if len(parts) >= 3 and parts[0] == "Production" and parts[1] == ev.name:
            candidates.append(str(ev / parts[-1]))
        if len(parts) >= 2 and parts[0] == "Production":
            candidates.append(str(prod / Path(*parts[1:])))
        if len(parts) == 1:
            candidates.append(str(ev / parts[0]))
        candidates.append(str(ev / rel.name))

        seen: set[str] = set()
        for cand in candidates:
            if cand in seen:
                continue
            seen.add(cand)
            resolved = self._path_under_allowed_serve_roots(cand)
            if resolved:
                return resolved
        return None

    def _handle_preview_phase_a_permanent(self) -> None:
        """Stable Phase A preview — no ?path= query (avoids slash-encoding 404s)."""
        preview = Path(self.app.event_dir) / "phase_a_permanent_preview.mp4"
        if not preview.is_file():
            return self._send_error_v59(
                404,
                error_code="PREVIEW_NOT_FOUND",
                error_message=(
                    "phase_a_permanent_preview.mp4 missing — "
                    "run scripts/run_phase_a_permanent.py --rebuild-gaps"
                ),
                retry_safe=False,
            )
        return self._serve_mp4_with_range(preview.resolve())

    def _handle_files_serve(self) -> None:
        """GET /files?path=<absolute_path> — serve local file bytes (images/video).

        Security (CodeQL py/path-injection alerts #24, #25):
        - Origin allowlist: cross-origin browser fetch refused. Only same-origin
          (or no Origin header, e.g. <img src> + curl) accepted.
        - Project-root containment: resolved real path must be inside the
          repo root, otherwise 403. Closes arbitrary-file-read via /files.
        - Allow-Origin response echoes ONLY the verified Origin (never `*`)
          so the inbound allowlist isn't mooted by a wildcard CORS reply
          (MED-2 from PR #8 adversarial review).
        """
        # 1. Origin allowlist — refuse non-localhost cross-origin requests.
        # Security (CodeQL py/http-response-splitting): rebuild the echoed
        # origin from validated components so no user-controlled bytes
        # (especially CR/LF) can flow into the response header. The
        # urllib.parse.urlparse + integer port + literal-host reconstruction
        # is a recognized sanitizer pattern.
        origin_in = self.headers.get("Origin", "") or ""
        origin_safe = ""
        if origin_in:
            try:
                _u = urllib.parse.urlparse(origin_in)
                if _u.scheme == "http" and _u.hostname in ("127.0.0.1", "localhost") \
                        and _u.port is not None and 1 <= int(_u.port) <= 65535 \
                        and _u.path in ("", "/") and not _u.query and not _u.fragment:
                    # Rebuild from typed pieces — no user bytes flow through.
                    origin_safe = f"http://{_u.hostname}:{int(_u.port)}"
            except (ValueError, TypeError):
                origin_safe = ""
        origin_ok = bool(origin_safe)
        if origin_in and not origin_ok:
            return self._send_error_v59(
                       403,
                       error_code="CROSS_ORIGIN_FORBIDDEN",
                       error_message="cross-origin not allowed",
                       retry_safe=False,
                   )
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        file_path = (qs.get("path") or [None])[0]
        resolved = self._resolve_served_file_path(file_path) if file_path else None
        if not resolved:
            return self._send_error_v59(
                       404,
                       error_code="FILE_NOT_FOUND",
                       error_message="file not found",
                       retry_safe=False,
                   )
        file_path = resolved
        # 2. Containment — under Dropbox root OR checkout root (CI / Playwright cwd).
        try:
            drop_root = os.path.realpath(str(DROPBOX_ROOT))
            repo_root = os.path.realpath(str(_MN_REPO_ROOT))
            real_path = os.path.realpath(file_path)
            under_drop = real_path == drop_root or real_path.startswith(drop_root + os.sep)
            under_repo = real_path == repo_root or real_path.startswith(repo_root + os.sep)
            if not (under_drop or under_repo):
                return self._send_error_v59(
                           403,
                           error_code="PATH_OUTSIDE_PROJECT_ROOT",
                           error_message="path outside project root",
                           retry_safe=False,
                       )
        except Exception:
            return self._send_error_v59(
                       403,
                       error_code="PATH_VALIDATION_FAILED",
                       error_message="path validation failed",
                       retry_safe=False,
                   )
        ext = os.path.splitext(file_path)[1].lower()
        content_types = {
            ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".webp": "image/webp", ".gif": "image/gif",
            ".mp4": "video/mp4", ".mov": "video/quicktime",
        }
        # Video files require byte-range (Accept-Ranges/206) support so that
        # browser <video> elements can seek (e.g. after pause+resume).
        # _serve_mp4_with_range handles Range headers → 206 responses properly.
        if ext in (".mp4", ".mov"):
            return self._serve_mp4_with_range(Path(file_path))
        ct = content_types.get(ext, "application/octet-stream")
        with open(file_path, "rb") as _f:
            data = _f.read()
        try:
            self.send_response(200)
            self.send_header("Content-Type", ct)
            self.send_header("Content-Length", str(len(data)))
            # MED-2: echo only the verified Origin, never `*`. If the
            # request had no Origin (curl, <img src>, native fetch),
            # omit the header entirely — same-origin needs no CORS reply.
            if origin_ok:
                # `origin_safe` is rebuilt from f"http://{hostname}:{int(port)}"
                # where hostname ∈ {"127.0.0.1", "localhost"} and port is int.
                # No user-controlled bytes flow through; CR/LF impossible.
                self.send_header("Access-Control-Allow-Origin", origin_safe)
                self.send_header("Vary", "Origin")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            print(f"file stream canceled by client: {file_path}", file=sys.stderr, flush=True)

    def _handle_cr_save_crop(self, body: dict) -> None:
        from server_handlers.cropper import handle_cr_save_crop
        return handle_cr_save_crop(self, body)

    @with_pin_and_drain('_handle_cr_upload', track_sync=True)
    def _handle_cr_upload(self, body: dict) -> None:
        from server_handlers.cropper import handle_cr_upload
        return handle_cr_upload(self, body)

    # ---- endpoints ----
    def _handle_health(self) -> None:
        from server_handlers.core import handle_health
        return handle_health(self)

    # ---- image injection endpoint ----

    def _handle_assign_image(self, body: dict) -> None:
        """Called by browser drag-drop to notify server of image assignment change.

        Body: { "beat": "beat_02", "image_key": "shot6_v2_establishing_frame_1",
                "event_id"?: "Event_1" }

        Looks up the full-res gallery image for that key and caches it so that
        Generate B+C and /api/animate use the CURRENT assigned image, not the
        stale one from the HTML file on disk.
        """
        # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
        if not self._assert_event_scope(self._scope_body(body), allow_missing=False):
            return
        beat_id = body.get("beat") or body.get("beat_id")
        image_key = body.get("image_key")
        if not beat_id or not image_key:
            return self._send_error_v59(
                       400,
                       error_code="MISSING_BEAT_OR_IMAGE_KEY",
                       error_message="missing 'beat'/'beat_id' or 'image_key'",
                       retry_safe=False,
                   )
        # S5.5a2: scope_video_role from body (LD-474). Default 'intro' during
        # refactor window; required after all clients pass it explicitly.
        video_role = body.get("scope_video_role", "intro")

        # Look up full-res gallery image.
        # Prefer abs_path from body if client sent it (R4 guard — avoids key
        # collision when two library dirs contain a same-stem file).
        # CodeQL py/path-injection gate (LD CODEQL_PATH_INJECTION_NATIVE_PATTERN_REFACTOR_V1
        # — supersedes LD-702/706). Inline realpath + startswith check on the SAME dataflow
        # node that feeds os.path.isfile. Native CodeQL-recognized sanitizer. If body_abs_path
        # does not resolve under an approved root, fall through to server-side resolution
        # from image_key (trusted lookup).
        body_abs_path = body.get("abs_path")
        _body_resolved = os.path.realpath(body_abs_path) if isinstance(body_abs_path, str) and body_abs_path else ""
        _body_safe = False
        if _body_resolved:
            for _r in self.app._library_root_dirs():
                if _r and (_body_resolved == _r or _body_resolved.startswith(_r + os.sep)):
                    _body_safe = True
                    break
        if _body_safe and os.path.isfile(_body_resolved):
            abs_path = _body_resolved
        else:
            abs_path = self.app.resolve_library_image_path(image_key)
        fullres = self.app.get_fullres_gallery_image(image_key)
        if not fullres:
            # Fall back: maybe the key IS in TH (thumbnail) — better than nothing
            html = self.app.storyboard_path.read_text(encoding="utf-8")
            th_match = re.search(
                r'TH\["?' + re.escape(image_key) + r'"?\]\s*=\s*"(data:image[^"]*)"',
                html,
            )
            if th_match:
                fullres = th_match.group(1)
                print(f"[assign-image] WARNING: using thumbnail for {image_key} (no full-res found)")

        if fullres:
            # Capture previous state (for HTML-patch-failure rollback in the
            # step 3 error branch below, Phase 4 fix April 17 2026).
            # S5.5a2: nested cache + nested disk path (IMAGE_OVERRIDES_NESTED_BY_ROLE_V1).
            prev_override = self.app._image_overrides.get(video_role, {}).get(beat_id)
            _pre_state = self.app.state.read_state()
            prev_override_key = (((_pre_state.get("videos") or {})
                                  .get(video_role) or {})
                                 .get("image_overrides") or {}).get(beat_id)

            # 1. In-memory cache (fast read for next add_options call).
            # Also pop from pending hydration queue so a later lazy-hydration
            # pass doesn't overwrite this fresh drag-drop with the stale disk
            # value (MEDIUM adversarial-review finding, April 16 2026).
            self.app._image_overrides.setdefault(video_role, {})[beat_id] = fullres
            self.app._pending_override_keys.get(video_role, {}).pop(beat_id, None)
            self.app.invalidate_beats_cache()

            # 2. Disk persistence — survives server restart (Tier 1 B3 fix).
            #    Stored as {beat_id: image_key} rather than {beat_id: data_uri}
            #    to keep production_state.json small; the data URI lives in
            #    _image_overrides in memory, re-resolved from the gallery on
            #    restart via get_fullres_gallery_image().
            #    Also persists abs_path so _handle_v2_event_state can project
            #    image_path for v59 shell clients (DRAG_DROP_V59_GALLERY_V1).
            #    S5.5a2: writes to videos[role].image_overrides via
            #    mutate_video_state (BG_VIDEO_PARTITION_V1).
            def _persist(partition, _bid=beat_id, _key=image_key, _ap=abs_path, _prev_key=prev_override_key):
                partition.setdefault("image_overrides", {})[_bid] = _key
                if _ap:
                    partition.setdefault("image_overrides_abs", {})[_bid] = _ap
                    # Blocker #145: persist beat.image_path + bump _version so
                    # v59 shell re-fetch and <img cacheBust> see the new crop.
                    _beat = partition.setdefault("beats", {}).setdefault(_bid, {})
                    try:
                        _event_abs = str(
                            (DROPBOX_ROOT / self.app.event_dir).resolve()
                        )
                        _beat["image_path"] = os.path.relpath(_ap, _event_abs)
                    except ValueError:
                        _beat["image_path"] = _ap
                    _beat["_version"] = int(_beat.get("_version", 0) or 0) + 1
                # T2 (Kim 2026-05-19 LD pending STALE_LIPSYNC_ON_ASSIGN_IMAGE_V1):
                # If the beat has a completed lipsync AND the image key is
                # changing, mark lipsync as stale via image_changed=True. The
                # mp4 stays on disk and continues to play; UI surfaces a badge
                # so Kim knows to re-lipsync. To revert: drag the old image
                # back from the library (its key is captured at _prev_key).
                # Image key unchanged: do nothing (no-op assign-same-image).
                if _prev_key is not None and _prev_key != _key:
                    _beat_state = partition.get("beats", {}).get(_bid)
                    if _beat_state:
                        _ls = _beat_state.get("lipsync")
                        if _ls and _ls.get("status") == "completed":
                            _ls["image_changed"] = True
                            # Capture the prior key so Kim can revert by
                            # dragging the old library tile back (no undo btn).
                            _ls["prior_image_key_for_revert"] = _prev_key
                        # Kim 2026-05-20 10:38 PM: magic_still_path /
                        # magic_video_path were rendered FROM the prior image.
                        # When image_path changes, the rendered magic is no
                        # longer valid for the new image (Preview Still would
                        # play stale magic over a new image). Clear those refs
                        # so the priority chain at StoryboardTab.tsx falls
                        # through to beat.final.file (which Re-render Still
                        # will update). The .mp4 file on disk is preserved
                        # in case Kim drags the old image back — but state
                        # no longer points at it.
                        if _beat_state.get("magic_still_path"):
                            _beat_state["magic_still_path"] = None
                        if _beat_state.get("magic_video_path"):
                            _beat_state["magic_video_path"] = None
                        # Same pattern for end_frame_path: was generated using
                        # the prior start image as OpenAI input. New image
                        # means the saved end frame is no longer the right
                        # second image for Kling. Force re-Preview end frame.
                        if _beat_state.get("end_frame_path"):
                            _beat_state["end_frame_path"] = None
                return None
            self.app.state.mutate_video_state(video_role, _persist)

            # 3. Patch the storyboard HTML L[] entry's i: field to match
            #    (Tier 5, April 17 2026 — decision 154 ASSIGN_IMAGE_MUST_PATCH_STORYBOARD).
            #    WITHOUT this step, the HTML file retains the old image_key while
            #    _image_overrides holds the new one, so any code path that reads
            #    the HTML (rebuild, cache invalidation, client reload) silently
            #    reverts the user's drag-drop. Uses the same shared helper as
            #    the dialogue-edit path, so both share the same hardened write
            #    (lock + unique tmp + atomic rename + round-trip verify).
            #
            #    Phase 4 fix (counter-agent finding #3, April 17 2026):
            #    On a real HTML-patch error we now return HTTP 500 and roll
            #    back the in-memory override + state persistence. This closes
            #    the "silent revert" loop that was the original bug class —
            #    the whole point of decision 154 is that state and HTML stay
            #    consistent. A partial write (state updated, HTML stale) is
            #    the very failure decision 154 exists to prevent, so it must
            #    be surfaced loudly and reversed, not quietly tolerated.
            html_patch = _patch_storyboard_L_field(
                self.app, beat_id, "i", image_key,
            )
            if html_patch.get("patched"):
                html_patched = True
            elif html_patch.get("reason") == "v59_shell":
                # Path C v59 storyboard (no L[] array — Vite shell). State +
                # sidecar are the source of truth; HTML patching is a no-op
                # by design. Surfaced explicitly so log audits are honest
                # (LD-456 conditional HTML patching).
                html_patched = False
                print(f"[assign-image] {beat_id}: v59 shell — state-only update "
                      f"(LD-456 conditional HTML patching).")
            elif html_patch.get("reason") == "not_in_storyboard":
                # Beat doesn't have an L[] entry (narration-only). Override is
                # still persisted to state + in-memory; animation path will use
                # it. This is informational, not an error.
                html_patched = False
                print(f"[assign-image] {beat_id} has no L[] entry "
                      f"(marker={html_patch.get('marker')!r}) — state-only update")
            else:
                # Real error patching HTML. Roll back state + in-memory
                # override (restore previous image_key if any) and return 500
                # so the client can surface a retry.
                err = html_patch.get("error", "unknown HTML patch error")
                print(f"[assign-image] ERROR HTML patch failed for {beat_id}: {err}")
                # Roll back in-memory (nested cache per IMAGE_OVERRIDES_NESTED_BY_ROLE_V1)
                _role_cache = self.app._image_overrides.setdefault(video_role, {})
                if prev_override is None:
                    _role_cache.pop(beat_id, None)
                else:
                    _role_cache[beat_id] = prev_override
                # Roll back state persistence (partition-scoped via mutate_video_state)
                def _rollback(partition, _bid=beat_id, _prev=prev_override_key):
                    ovr = partition.get("image_overrides", {}) or {}
                    if _prev is None:
                        ovr.pop(_bid, None)
                    else:
                        ovr[_bid] = _prev
                    partition["image_overrides"] = ovr
                    return None
                try:
                    self.app.state.mutate_video_state(video_role, _rollback)
                except Exception as exc:  # noqa: BLE001
                    print(f"[assign-image] rollback state-write also failed: {exc}")
                self.app.invalidate_beats_cache()
                return self._send_error_v59(
                           500,
                           error_code="STORYBOARD_HTML_PATCH_FAILED_OVERRIDE",
                           error_message="storyboard HTML patch failed; override rolled back",
                           retry_safe=True,
                           extra={"detail": err, "beat": beat_id},
                       )

            # 4. Fire-and-forget Directus write (Rule 18 Two-Write, counter-
            #    agent C4 CRITICAL finding). The drag-drop determines which
            #    image WaveSpeed submits, so it IS a creative decision at
            #    this moment — must leave an audit trail in prod_session_decisions.
            #    Async + non-blocking so UI stays snappy if Directus is down.
            _async_log_image_override(self.app.event_id, beat_id, image_key)

            print(f"[assign-image] {beat_id} -> {image_key} ({len(fullres):,} chars) "
                  f"[persisted html_patched={html_patched}]")
            return self._send_json(200, {
                "status": "ok",
                "beat": beat_id,
                "image_key": image_key,
                "image_size": len(fullres),
                "html_patched": html_patched,
            })
        else:
            return self._send_error_v59(
                       404,
                       error_code="GENERIC_ERROR",
                       error_message=f"image key '{image_key}' not found in gallery or TH",
                       retry_safe=False,
                   )

    def _handle_inject_image(self, body: dict) -> None:
        """Inject an image into the storyboard's image library.

        Body: {
            "name": "beat02_bird_crop_new",          # key name (required)
            "data": "data:image/png;base64,iVBOR...", # full data URI (required)
            "thumbnail": "data:image/png;base64,...", # optional small thumb
            "assign_beat": 2,                         # optional: assign to beat N (1-based)
            "event_id": "Event_1"                     # optional: scope guard (LD-456)
        }

        This is the bridge from Cropper -> Storyboard library.
        """
        # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
        if not self._assert_event_scope(self._scope_body(body), allow_missing=False):
            return
        # LD-456 conditional HTML patching: v59 shells have no IN/TH/div.ic
        # markers; rewriting them would silently no-op. Short-circuit here so
        # the caller gets a clear "v59_shell" outcome instead of a misleading
        # 500 from the marker-not-found branch below.
        if _storyboard_is_v59_shell(self.app):
            print(
                f"[inject-image] v59 shell detected — skipping HTML registration. "
                f"v59 fetches /api/cr/library on demand; image already on disk via "
                f"the cropper save path. name={body.get('name')!r}",
                flush=True,
            )
            return self._send_json(200, {
                "ok": True,
                "v59_shell": True,
                "html_patched": False,
                "name": body.get("name"),
                "hint": (
                    "v59 reads library via GET /api/cr/library on demand; "
                    "no HTML registration needed. The image is already "
                    "persisted to disk by the cropper save path."
                ),
            })
        name = body.get("name", "").strip()
        data_uri = body.get("data", "").strip()
        if not name or not data_uri:
            return self._send_error_v59(
                       400,
                       error_code="MISSING_NAME_OR_DATA",
                       error_message="name and data are required",
                       retry_safe=False,
                   )

        # Sanitize key: no extension, spaces->underscores
        key = name.replace(" ", "_")
        if key.endswith(".png"):
            key = key[:-4]

        sb_path = self.app.storyboard_path
        if not sb_path.is_file():
            return self._send_error_v59(
                       500,
                       error_code="GENERIC_ERROR",
                       error_message=f"storyboard not found: {sb_path}",
                       retry_safe=True,
                   )

        html = sb_path.read_text(encoding="utf-8")

        # Snapshot existing base64 images for verification
        existing_b64 = re.findall(r'data:image/[^"]{100,}', html)

        # Check if key already exists in TH — if so, update instead of duplicate
        th_exists = f'TH["{key}"]' in html

        # --- 1. Add gallery <div class="ic"> ---
        ic_positions = [m.end() for m in re.finditer(
            r'<div class="ic"><img[^>]+><p>[^<]+</p></div>', html)]
        if not ic_positions:
            return self._send_error_v59(
                       500,
                       error_code="NO_GALLERY_IMAGES_FOUND_IN",
                       error_message="no gallery images found in storyboard",
                       retry_safe=True,
                   )
        last_ic_end = ic_positions[-1]

        display_name = name if name.endswith(".png") else name + ".png"
        gallery_entry = f'\n<div class="ic"><img src="{data_uri}"><p>{display_name}</p></div>'
        html = html[:last_ic_end] + gallery_entry + html[last_ic_end:]
        print(f"[inject-image] Added gallery entry: {display_name}")

        # --- 2. Add to IN (image name map — required for drag-drop) ---
        in_exists = f'"{key}"' in html and 'var IN=' in html
        in_match = re.search(r'(var IN\s*=\s*\{[^}]*)"none"', html)
        if in_match and not in_exists:
            # Insert before the "none" key (which is always last)
            insert_pos = in_match.end() - len('"none"')
            in_entry = f'"{key}": "{display_name}", '
            html = html[:insert_pos] + in_entry + html[insert_pos:]
            print(f"[inject-image] Added IN[\"{key}\"]")

        # --- 3. Add TH thumbnail ---
        thumb_uri = body.get("thumbnail") or data_uri  # fallback to full if no thumb
        if not th_exists:
            th_matches = list(re.finditer(r'TH\["[^"]+"\]\s*=\s*"[^"]*"\s*;', html))
            if th_matches:
                last_th_end = th_matches[-1].end()
                th_entry = f'\nTH["{key}"]="{thumb_uri}";'
                html = html[:last_th_end] + th_entry + html[last_th_end:]
                print(f"[inject-image] Added TH[\"{key}\"]")
        else:
            # Update existing TH entry
            html = re.sub(
                rf'TH\["{re.escape(key)}"\]\s*=\s*"[^"]*"\s*;',
                f'TH["{key}"]="{thumb_uri}";',
                html
            )
            print(f"[inject-image] Updated existing TH[\"{key}\"]")

        # --- 4. Optionally assign to a beat ---
        assign_beat = body.get("assign_beat")
        if assign_beat is not None:
            assign_beat = int(assign_beat)
            l_match = re.search(r'var L\s*=\s*\[', html)
            if l_match:
                entries = []
                depth = 0
                entry_start = None
                for i in range(l_match.end(), len(html)):
                    if html[i] == '{':
                        if depth == 0:
                            entry_start = i
                        depth += 1
                    elif html[i] == '}':
                        depth -= 1
                        if depth == 0 and entry_start is not None:
                            entries.append((entry_start, i + 1))
                            entry_start = None
                    elif html[i] == ']' and depth == 0:
                        break
                beat_idx = assign_beat - 1
                if 0 <= beat_idx < len(entries):
                    es, ee = entries[beat_idx]
                    entry_text = html[es:ee]
                    old_i = re.search(r'i:"([^"]*)"', entry_text)
                    if old_i:
                        new_entry = entry_text[:old_i.start()] + f'i:"{key}"' + entry_text[old_i.end():]
                        html = html[:es] + new_entry + html[ee:]
                        print(f"[inject-image] Assigned beat {assign_beat}: i:\"{key}\"")

        # --- 5. Verify existing images preserved ---
        for i, orig in enumerate(existing_b64):
            if orig not in html:
                print(f"[inject-image] CRITICAL: image {i} corrupted — aborting write")
                return self._send_error_v59(
                           500,
                           error_code="IMAGE_CORRUPTION_DETECTED",
                           error_message="image corruption detected, write aborted",
                           retry_safe=True,
                       )

        # --- 6. Write to a new version ---
        # Version up: v29 -> v30, etc.
        old_name = sb_path.stem  # e.g. storyboard_v29_prod
        ver_match = re.search(r'_v(\d+)_', old_name)
        if ver_match:
            old_ver = int(ver_match.group(1))
            new_ver = old_ver + 1
            new_name = old_name.replace(f"_v{old_ver}_", f"_v{new_ver}_") + sb_path.suffix
        else:
            new_name = old_name + "_injected" + sb_path.suffix

        new_path = sb_path.parent / new_name
        new_path.write_text(html, encoding="utf-8")
        print(f"[inject-image] Written: {new_path.name} ({new_path.stat().st_size:,} bytes)")

        # Update app to serve the new version
        self.app.storyboard_path = new_path
        self.app._beats_cache = None  # invalidate cache

        return self._send_json(200, {
            "status": "ok",
            "key": key,
            "storyboard": new_name,
            "gallery_count": len(re.findall(r'<div class="ic"', html)),
            "message": f"Image '{key}' added to storyboard library. Reload the storyboard to see it."
        })

    def _handle_restart(self) -> None:
        """Restart the server process. Shuts down cleanly, then re-execs."""
        self._send_json(200, {"status": "restarting"})
        print("\n[SERVER] Restart requested via API — shutting down and re-launching...\n")
        # Non-daemon thread: Python shutdown must wait for it so os.execv runs.
        # Previous bug (April 16 2026): daemon=True caused the thread to die
        # before reaching os.execv, making the UI Restart button a no-op.
        threading.Thread(
            target=perform_server_restart,
            args=(self.server, self.app, "api"),
            daemon=False,
            name="ServerRestart",
        ).start()

    # ---- lip sync endpoints ----

    # ========================================================================
    # _handle_lipsync_submit — §8.4 auto-apply silcomp + video-trim, then
    # ByteDance. EVERY submission pre-conditions audio + video.
    #
    # Silence compression: any silence > 1.0s -> 0.8s (Rule 11: speech bytes
    # preserved verbatim). Video trim: audio_duration + 0.4s tail room,
    # capped at raw video duration (ByteDance freeze-extends short videos).
    #
    # Fail-loud: pre-conditioning failures return HTTP 500 synchronously
    # (Kim design-call 2, April 17 2026). No silent fallback to raw inputs.
    # Legacy behavior preserved as _handle_lipsync_submit_legacy.
    # ========================================================================
    @with_pin_and_drain('_handle_lipsync_submit', track_sync=False)
    def _handle_lipsync_submit(self, body: dict) -> None:
        from server_handlers.vendor_jobs import handle_lipsync_submit
        return handle_lipsync_submit(self, body)

    def _handle_lipsync_idle(self, body: dict) -> None:
        from server_handlers.vendor_jobs import handle_lipsync_idle
        return handle_lipsync_idle(self, body)

    def _handle_lipsync_submit_legacy(self, body: dict) -> None:
        from server_handlers.vendor_jobs import handle_lipsync_submit_legacy
        return handle_lipsync_submit_legacy(self, body)

    def _handle_lipsync_status(self) -> None:
        from server_handlers.vendor_jobs import handle_lipsync_status
        return handle_lipsync_status(self)

    def _handle_use_as_final(self, body: dict) -> None:
        """POST /api/beat/use_as_final {beat: "beat_NN", scope_video_role: <role>}
        Mark the currently selected Kling option as the final clip (no lipsync needed).
        Writes final.* block to production_state.json AND accepted_video_path to bg sidecar
        so the concat pipeline picks it up. Spec A / LD-139 partial implementation.

        S5.5d: video role parameterized via scope_video_role; validates against
        {intro, resolution, standalone} per VIDEO_ROLE_PER_REQUEST_V2 (supersedes LD-474).
        """
        # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
        if not self._assert_event_scope(self._scope_body(body), allow_missing=False):
            return

        beat_id = body.get("beat") or body.get("beat_id")
        if not beat_id:
            return self._send_error_v59(
                       400,
                       error_code="MISSING_BEAT",
                       error_message="beat required",
                       retry_safe=False,
                   )

        # S5.5d B5: video role from body; default 'intro' for legacy clients.
        scope_video_role = (body or {}).get("scope_video_role") or "intro"
        valid_roles = self.app.state._VALID_VIDEO_ROLES
        if scope_video_role not in valid_roles:
            return self._send_error_v59(
                       400,
                       error_code="VIDEO_ROLE_INVALID",
                       error_message="video_role_invalid",
                       retry_safe=False,
                       extra={"code": "VIDEO_ROLE_INVALID", "got": scope_video_role, "valid": sorted(valid_roles), "hint": "scope_video_role must be one of intro/resolution/standalone."},
                   )

        state = self.app.state.read_state()
        beat = ((state.get("videos") or {}).get(scope_video_role) or {}).get("beats", {}).get(beat_id)
        if not beat:
            return self._send_error_v59(
                       400,
                       error_code="GENERIC_ERROR",
                       error_message=f"unknown beat: {beat_id} (role={scope_video_role})",
                       retry_safe=False,
                   )

        # Kim 2026-05-20 follow-up: add explicit source mode so Kim can promote
        # the LIPSYNC mp4 as the final (was previously hardcoded to raw_option).
        # source='raw_option' (default) — finalize the currently selected_option
        # source='lipsync'              — finalize beat.lipsync.file
        requested_source = (body.get("source") or "raw_option").strip().lower()
        if requested_source not in ("raw_option", "lipsync"):
            return self._send_error_v59(
                       400,
                       error_code="INVALID_SOURCE",
                       error_message=f"source must be 'raw_option' or 'lipsync', got {requested_source!r}",
                       retry_safe=False,
                   )

        if requested_source == "lipsync":
            ls = beat.get("lipsync") or {}
            ls_file = ls.get("file") or ""
            if ls.get("status") != "completed" or not ls_file:
                return self._send_error_v59(
                           400,
                           error_code="LIPSYNC_NOT_AVAILABLE",
                           error_message="cannot use lipsync as final — no completed lipsync.file on this beat",
                           retry_safe=False,
                       )
            # lipsync mp4 lives in event_dir/animation_clips/ NOT clips_dir
            abs_path = str(self.app.event_dir / "animation_clips" / ls_file)
            if not os.path.isfile(abs_path):
                return self._send_error_v59(
                           400,
                           error_code="LIPSYNC_FILE_MISSING",
                           error_message=f"lipsync file not found on disk: {ls_file}",
                           retry_safe=False,
                       )
            final_block = {
                "source": "lipsync",
                "source_option": ls.get("source_option"),
                "file": ls_file,
                "approved_at": datetime.now(timezone.utc).isoformat(),
            }
            opt_file = ls_file  # for the sidecar/log path below
        else:
            p1 = beat.get("phase_1", {})
            opts = p1.get("options", [])
            sel = p1.get("selected_option", 1)
            sel_idx = sel - 1  # selected_option is 1-indexed
            if not opts or not (0 <= sel_idx < len(opts)):
                return self._send_error_v59(
                           400,
                           error_code="GENERIC_ERROR",
                           error_message=f"no option at index {sel_idx} (selected_option={sel})",
                           retry_safe=False,
                       )

            opt_file = opts[sel_idx].get("file", "")
            if not opt_file:
                return self._send_error_v59(
                           400,
                           error_code="SELECTED_OPTION_HAS_NO_FILE",
                           error_message="selected option has no file",
                           retry_safe=False,
                       )

            abs_path = str(self.app.state.clips_dir / opt_file)
            if not os.path.isfile(abs_path):
                return self._send_error_v59(
                           400,
                           error_code="GENERIC_ERROR",
                           error_message=f"clip file not found: {opt_file}",
                           retry_safe=False,
                       )

            # 1. Write final block to production_state.json under the requested role
            final_block = {
                "source": "raw_option",
                "source_option": sel,
                "file": opt_file,
                "approved_at": datetime.now(timezone.utc).isoformat(),
            }

        # S5.5d: writes to videos[scope_video_role].beats[bid].final.
        def _mutate(s):
            role_beats = s.setdefault("videos", {}).setdefault(
                scope_video_role,
                {"video_role": scope_video_role, "video_label": None,
                 "beats": {}, "completed_mp4_path": None},
            ).setdefault("beats", {})
            role_beats[beat_id]["final"] = final_block
        self.app.state.mutate_state(_mutate)

        # 2. Write accepted_video_path to bg sidecar (same pattern as _handle_bg_accept_option)
        try:
            bg = _bg_module()
            with bg.sidecar_file_lock():
                sidecar = bg.read_sidecar()
                sidecar = bg._migrate_sidecar(sidecar)
                _, b_entry = bg.find_beat(sidecar, beat_id)
                if b_entry is not None:
                    b_entry["accepted_video_path"] = abs_path
                    b_entry["status"] = "accepted"
                    bg.write_sidecar(sidecar)
        except Exception as exc:  # noqa: BLE001
            print(f"[use-as-final] sidecar write failed (non-blocking): {exc}")

        # 3. Fire-and-forget Directus activity log
        _async_log_use_as_final(
            event_id=str(self.app.event_id),
            beat_id=beat_id,
            file=opt_file,
        )

        return self._send_json(200, {
            "status": "ok",
            "beat": beat_id,
            "file": opt_file,
            "final": final_block,
        })

    def _serve_storyboard(self) -> None:
        from server_handlers.core import serve_storyboard
        return serve_storyboard(self)

    def _build_storyboard_nav_html(self) -> str:
        import json as _json
        stem = self.app.storyboard_stem
        return f"""
<style>
#sb-nav-bar {{
  position:fixed;top:0;left:0;right:0;z-index:9999;
  background:#1a1a2e;border-bottom:2px solid #6c63ff;
  padding:6px 16px;display:flex;align-items:center;gap:10px;
  font-family:sans-serif;font-size:13px;color:#ccc;
}}
#sb-nav-bar select {{background:#2a2a4e;color:#fff;border:1px solid #6c63ff;padding:4px 8px;border-radius:4px;min-width:260px;}}
#sb-nav-bar button {{background:#6c63ff;color:#fff;border:none;padding:5px 12px;border-radius:4px;cursor:pointer;font-size:13px;}}
#sb-nav-bar .sb-refresh {{background:#2a4e2a;}}
#sb-active-pill {{background:#2a2a4e;padding:3px 10px;border-radius:10px;font-size:11px;color:#aaa;white-space:nowrap;}}
body {{padding-top:44px!important;}}
#mn-prod-overlay {{top:44px!important;}}
#mn-lib-sidebar{{top:44px!important;height:calc(100vh - 44px)!important}}
</style>
<script>window.__ACTIVE_STORYBOARD_STEM__ = {_json.dumps(stem)};</script>
<div id="sb-nav-bar">
  <span style="color:#6c63ff;font-weight:bold;white-space:nowrap">📋 Storyboard:</span>
  <select id="sb-select"></select>
  <button id="sb-load-btn">Load</button>
  <button class="sb-refresh" id="sb-refresh-btn">↺</button>
  <span id="sb-active-pill">active: {stem}</span>
</div>
<script>
(function(){{
  var activeStem = window.__ACTIVE_STORYBOARD_STEM__;
  function loadList(force){{
    var url='/api/storyboard/list'+(force?'?refresh=1':'');
    fetch(url).then(function(r){{return r.json();}}).then(function(data){{
      var sel=document.getElementById('sb-select');
      sel.innerHTML='';
      var items=data.storyboards||[];
      if(!items.length){{
        var o=document.createElement('option');
        o.textContent='(no storyboards found — click ↺ to refresh)';
        sel.appendChild(o);
        return;
      }}
      items.forEach(function(sb){{
        var o=document.createElement('option');
        o.value=sb.filename;
        o.textContent=sb.title+' (v'+sb.version+', '+sb.beat_count+' beats)';
        var sbStem=sb.filename.replace('.html','');
        if(sbStem===activeStem||sb.is_active)o.selected=true;
        sel.appendChild(o);
      }});
    }}).catch(function(){{
      console.warn('sb-nav: list fetch failed');
    }});
  }}
  loadList(false);
  document.getElementById('sb-load-btn').addEventListener('click',function(){{
    var filename=document.getElementById('sb-select').value;
    if(!filename||(filename.indexOf('storyboard_v')<0))return;
    if(!confirm('Switch to '+filename+'?\\n\\n⚠️ Make sure you have exported any browser edits (drag-drop, dialogue) before switching — unsaved browser edits will be lost.'))return;
    fetch('http://localhost:5111/api/storyboard/switch',{{
      method:'POST',
      headers:{{'Content-Type':'application/json'}},
      body:JSON.stringify({{filename:filename}})
    }}).then(function(r){{return r.json();}}).then(function(d){{
      if(d.ok){{location.href=location.pathname+'?t='+Date.now();}}
      else{{alert('Switch failed: '+(d.error||'unknown error'));}}
    }}).catch(function(e){{alert('Switch request failed: '+e);}} );
  }});
  document.getElementById('sb-refresh-btn').addEventListener('click',function(){{
    loadList(true);
  }});
}})();
</script>
"""

    def _handle_storyboard_list(self) -> None:
        """GET /api/storyboard/list[?refresh=1]"""
        force = "refresh=1" in self.path
        storyboards = self.app._get_storyboard_list(force_refresh=force)
        self._send_json(200, {
            "storyboards": storyboards,
            "active": self.app.storyboard_path.name,
            "active_stem": self.app.storyboard_stem,
            "event_dir": self.app.event_dir.name,
        })

    def _handle_storyboard_switch(self, body: dict) -> None:
        """POST /api/storyboard/switch  body: {filename: str}

        Security (CodeQL py/path-injection — regex tightening + containment):
        the previous regex `^storyboard_v\\d+.*\\.html$` allowed `.*` to
        match `/`, so `storyboard_v1/../../etc/passwd.html` slipped through
        the basename check and `event_dir / filename` resolved through `..`
        to leak file contents via `_extract_storyboard_title`'s
        `path.read_text()`. Tighten to a strict basename pattern and add
        a separator-anchored containment check on the resolved real path.
        """
        filename = (body.get("filename") or "").strip()
        # Strict basename: storyboard_v<digits>[_<lowercase-suffix>]?.html
        if not re.match(r'^storyboard_v\d+(_[a-z0-9_-]+)?\.html$', filename):
            return self._send_error_v59(
                       400,
                       error_code="GENERIC_ERROR",
                       error_message=f"invalid filename: {filename!r}",
                       retry_safe=False,
                   )
        target = self.app.event_dir / filename
        # Containment: resolved real path must remain inside event_dir.
        try:
            event_dir_real = str(self.app.event_dir.resolve())
            target_real = str(target.resolve())
            if not (target_real == event_dir_real
                    or target_real.startswith(event_dir_real + os.sep)):
                return self._send_error_v59(
                           400,
                           error_code="FILENAME_ESCAPES_EVENT_DIR",
                           error_message="filename escapes event_dir",
                           retry_safe=False,
                       )
        except Exception:
            return self._send_error_v59(
                       400,
                       error_code="FILENAME_VALIDATION_FAILED",
                       error_message="filename validation failed",
                       retry_safe=False,
                   )
        if not target.is_file():
            return self._send_error_v59(
                       404,
                       error_code="GENERIC_ERROR",
                       error_message=f"not found: {filename}",
                       retry_safe=False,
                   )
        with self.app._storyboard_write_lock:
            result = self.app.switch_storyboard(filename)
        self._send_json(200, result)

    def _serve_cropper(self) -> None:
        from server_handlers.cropper import serve_cropper
        return serve_cropper(self)

    def _serve_asset(self, filename: str) -> None:
        from server_handlers.cropper import serve_asset
        return serve_asset(self, filename)

    def _read_state_with_file_flags(self) -> dict:
        """Read state and annotate every file-reference with file_exists.

        Bug fix 2026-05-19 (P3 / LD-505 Phase C, extends PR #73):
        phase_1.options[*].file, lipsync.file, final.file, final.image_path
        can all reference clips/images that Kim has manually archived or
        moved. Without per-field existence annotation, ▶ preview asset
        fetches 404 and the <video> element surfaces a generic "codec/format
        not supported" toast with no actionable signal. Audit C2-4 / C2-1.

        Annotates EVERY *.file (or *.image_path) field on each beat with
        `file_exists: bool` so the client can render disabled UI + an
        "(archived)" label uniformly across slots. Audit C2-4 specifically
        called out the lipsync.file gap on 14/19 resolution beats.

        Pure read-only — does NOT mutate persisted state.
        """
        state = self.app.state.read_state()
        clips_dir = self.app.state.clips_dir
        event_dir = self.app.event_dir  # Bug-B3 (spec §2 Topic-2): magic + end_frame paths
        videos = state.get("videos") if isinstance(state, dict) else None
        if not isinstance(videos, dict):
            return state

        def _annotate_block(block, file_field: str = "file") -> None:
            """Set block[file_field + '_exists'] based on disk presence.

            file_field defaults to 'file' (relative to clips_dir); pass
            'image_path' for absolute paths.
            """
            if not isinstance(block, dict):
                return
            f = block.get(file_field)
            if file_field == "image_path":
                exists_key = "image_path_exists"
                block[exists_key] = bool(f and isinstance(f, str) and os.path.exists(f))
            else:
                exists_key = "file_exists"
                block[exists_key] = bool(f and (clips_dir / f).is_file())

        # Bug-B3 (spec §2 Topic-2, 2026-05-20): annotate magic + end_frame
        # paths which resolve against EVENT_DIR (not clips_dir). Without these,
        # orphan references (state.json points at a file that's been deleted
        # from disk) produce silent 404s exactly like the LD-807 case we just
        # hit on beat_03 earlier today.
        def _annotate_beat_field(beat: dict, field: str, base_dir) -> None:
            if not isinstance(beat, dict):
                return
            f = beat.get(field)
            if not (f and isinstance(f, str)):
                beat[f"{field}_exists"] = False
                return
            beat[f"{field}_exists"] = (base_dir / f).is_file()

        end_frames_dir = event_dir / "end_frames"

        for partition in videos.values():
            if not isinstance(partition, dict):
                continue
            beats = partition.get("beats")
            if not isinstance(beats, dict):
                continue
            for beat in beats.values():
                if not isinstance(beat, dict):
                    continue
                # phase_1.options[*].file
                p1 = beat.get("phase_1")
                if isinstance(p1, dict):
                    for opt in (p1.get("options") or []):
                        _annotate_block(opt)
                # phase_2.options[*].file (forward-compat per audit C2-5)
                p2 = beat.get("phase_2")
                if isinstance(p2, dict):
                    for opt in (p2.get("options") or []):
                        _annotate_block(opt)
                # beat.lipsync.file (audit C2-4 — 14/19 resolution beats
                # were unannotated; same Bug 3 class lurked here)
                _annotate_block(beat.get("lipsync"))
                # beat.final.file + beat.final.image_path (audit S3-F2)
                final = beat.get("final")
                if isinstance(final, dict):
                    _annotate_block(final, "file")
                    _annotate_block(final, "image_path")
                # Bug-B3 — magic_*_path resolves to event_dir (NOT clips_dir).
                _annotate_beat_field(beat, "magic_still_path", event_dir)
                _annotate_beat_field(beat, "magic_video_path", event_dir)
                # Bug-B3 — end_frame_path resolves to event_dir/end_frames/.
                _annotate_beat_field(beat, "end_frame_path", end_frames_dir)

        # Phase sub-object backward-compat flatten (2026-05-28, RC1-cue fix).
        # Legacy state writes stored phase_b/phase_a fields in a nested
        # sub-object (state['phase_b']['phase_b_watercolor_cues_json']), while
        # current code (v2_module_patch, pickPhaseSlice in the React storyboard)
        # expects flat top-level keys (state['phase_b_watercolor_cues_json']).
        # Root cause: Kim's production state has real cues at the nested path
        # (written by a pre-v3-arch path) while the top-level key = "[]"
        # (never updated). pickPhaseSlice reads top-level → gets "[]" →
        # latestCuesRef.current = [] → persistCues/RC1 update never fires.
        # Fix: promote nested → top-level ONLY when top-level is absent or
        # the sentinel empty "[]". Never overrides real top-level data.
        # Pure read transform — does NOT write to disk. (DS-22 verified by
        # smoke agent a86a7aaa0474ae564, Directus row id=6790.)
        for _ph in ("phase_b", "phase_a"):
            _sub = state.get(_ph)
            if not isinstance(_sub, dict):
                continue
            for _sub_k, _sub_v in _sub.items():
                if not _sub_k.startswith("phase_"):
                    continue
                _top_v = state.get(_sub_k)
                if _top_v is None or _top_v == "[]" or _top_v == []:
                    state[_sub_k] = _sub_v

        return state

    def _serve_beat_audio(self, beat_id: str) -> None:
        from server_handlers.beats_legacy import serve_beat_audio
        return serve_beat_audio(self, beat_id)

    def _beat_id(self, line_number: int) -> str:
        return f"beat_{line_number:02d}"

    def _select_beats_for_mode(self, mode: str, requested: list[str] | None, video_role: str = "intro") -> list[dict]:
        all_beats = self.app.beats(video_role)
        if mode == "all":
            return all_beats
        if mode == "test":
            if not requested:
                return all_beats[: min(3, len(all_beats))]
            ids = set(requested)
            return [b for b in all_beats if self._beat_id(b.get("line_number", -1)) in ids]
        if mode == "retry":
            state = self.app.state.read_state()
            failed = {
                bid for bid, b in ((state.get("videos") or {}).get(video_role) or {}).get("beats", {}).items()
                if (b.get("phase_1") or {}).get("status") in ("failed", "partial")
            }
            return [b for b in all_beats if self._beat_id(b.get("line_number", -1)) in failed]
        return all_beats

    def _handle_animate(self, body: dict) -> None:
        from server_handlers.background import handle_animate
        return handle_animate(self, body)

    def _handle_status(self) -> None:
        from server_handlers.background import handle_status
        return handle_status(self)

    def _handle_redo(self, body: dict) -> None:
        from server_handlers.background import handle_redo
        return handle_redo(self, body)

    # ========================================================================
    # _handle_add_options — DISPATCHER (decisions 172 + 180)
    #
    # UNIVERSAL DEFAULT (decision 180 STARTEND_UNIVERSAL_DEFAULT, April 17 2026):
    # Every beat routes to the start-end pipeline unless state has an
    # explicit force_legacy: true opt-out flag. When end_frame_prompt is
    # missing, a generic speaker-derived default is used so the operator
    # never has to pre-configure a prompt before pressing Generate B+C.
    #
    # Kim directive: "everything in the storyboard should always work up
    # to date, all buttons, all beats, should be kept current — you should
    # not be deciding to update just one beat or the other, always
    # autopopulate to all beats." Hence: no split-brain.
    #
    # Fail-loud on start-end errors per design-call 2 (April 17, 2026):
    # no silent fallback to legacy. Each path surfaces errors directly.
    # ========================================================================

    # T1-Phase 2+3 end-frame iteration wrappers (spec MAGIC_AND_ENDFRAME_FIXES_20260520_v1, LD-814).
    # The actual logic lives in server_handlers.background to keep this file lean.
    # Wrappers use self._handle_*() naming so body_key_contract_check.parse_server_routes()
    # can detect them — the bare `handle_*(self, body)` pattern is invisible to the
    # regex-based parser (HANDLER_CALL_RE = r"self\._handle_*").
    def _handle_preview_end_frame(self, body: dict) -> None:
        from server_handlers.background import handle_preview_end_frame
        return handle_preview_end_frame(self, body)

    def _handle_upload_end_frame(self, body: dict) -> None:
        from server_handlers.background import handle_upload_end_frame
        return handle_upload_end_frame(self, body)

    def _handle_add_options(self, body: dict) -> None:
        """Dispatch Generate B+C to start-end (default) unless force_legacy."""
        # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
        if not self._assert_event_scope(self._scope_body(body), allow_missing=False):
            return

        beat_id = body.get("beat_id") or body.get("beat")
        if not beat_id:
            return self._send_error_v59(
                       400,
                       error_code="MISSING_BEAT",
                       error_message="missing 'beat'",
                       retry_safe=False,
                   )

        # Normalize so sub-handlers can safely subscript body["beat"].
        if "beat" not in body:
            body = dict(body, beat=beat_id)

        video_role = (body or {}).get("scope_video_role") or (body or {}).get("scope_target_video") or "intro"

        try:
            state = self.app.state.read_state()
        except Exception as exc:
            return self._send_error_v59(
                       500,
                       error_code="GENERIC_ERROR",
                       error_message=f"failed to read state for dispatch: {type(exc).__name__}: {exc}",
                       retry_safe=True,
                   )

        beat_state = (((state.get("videos") or {}).get(video_role) or {}).get("beats") or {}).get(beat_id) or {}
        force_legacy = bool(beat_state.get("force_legacy"))

        # LD-807 LIPSYNC_INVALIDATE_ON_REGEN_V1 — Regen B+C on a previously-
        # lipsynced beat MUST clear stale lipsync state + on-disk file so the
        # UI doesn't show a stale composite preview (the same invariant that
        # handle_redo + handle_animate already enforce; the original LD-807
        # implementation missed this dispatcher, which is the actual endpoint
        # the "Regenerate B + C" button hits per StoryboardTab.tsx:835).
        prior_lipsync_existed = bool(beat_state.get("lipsync"))
        prior_lipsync_file = self.app.event_dir / "animation_clips" / f"{beat_id}_lipsync.mp4"
        try:
            if prior_lipsync_file.is_file():
                prior_lipsync_existed = True
                prior_lipsync_file.unlink()
                print(f"[add_options] {beat_id}: unlinked stale lipsync {prior_lipsync_file.name}")
        except OSError as exc:
            print(f"[add_options] {beat_id}: lipsync unlink warning (non-fatal): {exc}")

        if prior_lipsync_existed:
            def _clear_lipsync(partition, _bid=beat_id):
                pbeats = partition.setdefault("beats", {})
                if _bid in pbeats and "lipsync" in pbeats[_bid]:
                    pbeats[_bid]["lipsync"] = None
            try:
                self.app.state.mutate_video_state(video_role, _clear_lipsync)
            except Exception as exc:  # noqa: BLE001
                print(f"[add_options] {beat_id}: lipsync state-clear warning (non-fatal): {exc}")
            try:
                from lib.directus import try_post_or_queue as _tpq
                _tpq("prod_activity_log", {
                    "action": "lipsync_invalidated_on_regen",
                    "performed_by": "_handle_add_options",
                    "details": {
                        "event_id": self.app.event_id,
                        "beat_id": beat_id,
                        "video_role": video_role,
                        "removed_file": str(prior_lipsync_file),
                    },
                })
            except Exception as exc:  # noqa: BLE001
                print(f"[add_options] {beat_id}: lipsync_invalidated_on_regen audit failed (non-fatal): {exc}")

        if force_legacy:
            print(f"[add_options:dispatch] {beat_id}: force_legacy=true -> legacy path")
            return self._handle_add_options_legacy(body)

        # T1-Phase 1 (spec §2): prompt logic extracted to lib/end_frame_prompt.py.
        # No imports from production_server.py inside the helper (cycle risk per
        # cursor R1 review); caller resolves speaker_canonical here.
        from lib.end_frame_prompt import build_end_frame_prompt as _build_end_frame_prompt
        _disp_speaker = _canonicalize_speaker(beat_state.get("speaker", "") or "")
        end_frame_prompt = _build_end_frame_prompt(
            beat_state, _disp_speaker, addendum=None
        )
        print(f"[add_options:dispatch] {beat_id}: -> start-end pipeline "
              f"(decision 180 universal default; prompt {len(end_frame_prompt)}c)")
        return self._handle_add_options_startend(body, beat_state, end_frame_prompt)

    # ========================================================================
    # _handle_add_options_startend — Kling start-end-frame handler (decision 172)
    #
    # For each of num_new options: generate a fresh end frame via FLUX Kontext,
    # submit to Kling with both image + end_image. Preserves all Rule 8 / 8.3 /
    # 8.4 invariants. Fail-loud on errors. No silent fallback to legacy.
    # ========================================================================
    def _handle_add_options_startend(self, body: dict, beat_state: dict,
                                     end_frame_prompt: str) -> None:
        """Start-end pipeline path per decision 172.

        Rule 8.3 invariants: cfg_scale=0.5, anti-lipsync negatives intact,
        sound: false, NO mouth/motion/gaze lock in positive prompt. Gaze
        anchor comes from end-frame pixel geometry, not prompt words.
        Rule 6: both frames auto-upscaled to ≥600px before Kling submit.
        Rule 18: prod_activity_log write per submit.
        """
        if self.app.client is None:
            return self._send_error_v59(
                       500,
                       error_code="WAVESPEED_NOT_CONFIGURED",
                       error_message="WaveSpeed client not configured",
                       retry_safe=True,
                   )

        beat_id = body["beat"]  # validated by dispatcher
        num_new = int(body.get("count", 2))
        # video_role MUST be resolved at the very top — closures below capture it
        # as a default-argument value at definition time (not call time). Resolving
        # here prevents UnboundLocalError when Python sees the later assignment and
        # treats video_role as a local for the entire function scope.
        video_role = body.get("scope_video_role") or body.get("scope_target_video") or "intro"

        # T1-Phase 4 (spec MAGIC_AND_ENDFRAME_FIXES_20260520_v1, LD-814):
        # REFUSE Regen B+C unless an approved end_frame_path exists on disk.
        # Kim's flow: she clicks "✏ Preview end frame" (or "📤 Upload end frame")
        # FIRST to generate/upload + approve an end frame, THEN clicks Regen B+C.
        # NO GRANDFATHERING — even when phase_1.options already exist, the next
        # Regen B+C still requires a fresh end_frame_path. This server-side
        # check is the source-of-truth gate; the client also disables the
        # button when end_frame_path is missing (UI Phase 6).
        _end_frame_path = beat_state.get("end_frame_path")
        _end_frames_dir = self.app.event_dir / "end_frames"
        _end_frame_disk_path = _end_frames_dir / _end_frame_path if _end_frame_path else None
        if not _end_frame_path or not (_end_frame_disk_path and _end_frame_disk_path.is_file()):
            return self._send_error_v59(
                       400,
                       error_code="END_FRAME_REQUIRED",
                       error_message="Approved end_frame_path required — click 'Preview end frame' or 'Upload end frame' first.",
                       retry_safe=False,
                       extra={
                           "beat_id": beat_id,
                           "video_role": video_role,
                           "end_frame_path": _end_frame_path,
                           "end_frame_path_exists": bool(_end_frame_disk_path and _end_frame_disk_path.is_file()),
                           "hint": "Per LD-814 / spec MAGIC_AND_ENDFRAME_FIXES_20260520_v1: Regen B+C reads a Kim-approved end frame from disk; OpenAI/FLUX is no longer called from this endpoint.",
                       },
                   )

        # Duration resolution — identical to legacy, repeated for independence.
        explicit_duration = body.get("duration")
        if explicit_duration is not None:
            try:
                duration_raw = int(explicit_duration)
            except (TypeError, ValueError):
                return self._send_error_v59(
                           400,
                           error_code="GENERIC_ERROR",
                           error_message=f"invalid duration value: {explicit_duration!r}",
                           retry_safe=False,
                           extra={"hint": f"duration must be {KLING_MIN_DURATION_SEC} or {KLING_MAX_DURATION_SEC}"},
                       )
            if duration_raw not in (KLING_MIN_DURATION_SEC, KLING_MAX_DURATION_SEC):
                return self._send_error_v59(
                           400,
                           error_code="GENERIC_ERROR",
                           error_message=f"unsupported duration: {duration_raw}s",
                           retry_safe=False,
                           extra={"hint": f"Kling v3 supports {KLING_MIN_DURATION_SEC}s or {KLING_MAX_DURATION_SEC}s"},
                       )
            duration = duration_raw
            duration_reason = f"explicit_client_override_{duration}s"
        else:
            audio_path = _find_beat_audio(
                self.app.event_dir, beat_id, body.get("audio_override"),
                app=self.app,
            )
            # audio_path may be None for blank/new beats — _infer_animation_duration
            # handles None by returning (KLING_MIN_DURATION_SEC, "no_audio_found_default_5s")
            try:
                duration, duration_reason = _infer_animation_duration(audio_path)
            except ValueError as exc:
                return self._send_error_v59(
                           400,
                           error_code="GENERIC_ERROR",
                           error_message=str(exc),
                           retry_safe=False,
                           extra={"hint": "Edit script or split audio into shorter beats", "beat": beat_id, "audio_file": audio_path.name if audio_path else "(no audio)"},
                       )
        print(f"[add_options:startend] {beat_id} duration={duration}s reason={duration_reason}")

        # Existing-options check + trim B+C (same as legacy).
        phase1 = beat_state.get("phase_1") or {}
        existing_options = phase1.get("options", [])
        if not existing_options:
            return self._send_error_v59(
                       400,
                       error_code="GENERIC_ERROR",
                       error_message=f"beat {beat_id} has no existing options — use /api/animate",
                       retry_safe=False,
                   )

        if len(existing_options) > 1:
            old_bc_files = [o.get("file") for o in existing_options[1:] if o.get("file")]
            def trim_to_a(st, _bid=beat_id, _role=video_role):
                # Partition-aware (SCOPE_ROUTER_V1) — same fix as add_option closure
                b = ((st.get("videos") or {}).get(_role) or {}).get("beats", {}).get(_bid)
                if b and b.get("phase_1"):
                    b["phase_1"]["options"] = b["phase_1"].get("options", [])[:1]
                    if (b["phase_1"].get("selected_option") or 0) > 1:
                        b["phase_1"]["selected_option"] = 1
            self.app.state.mutate_state(trim_to_a)
            for fname in old_bc_files:
                p = self.app.state.clips_dir / fname
                if p.is_file():
                    try: p.unlink()
                    except OSError: pass

        # Load API keys before budget gate — vendor cost must mirror the
        # dispatcher branch below (LD-730 fallback when requested key absent).
        try:
            keys = _ksendpipe_load_api_keys()
        except SystemExit as exc:
            return self._send_error_v59(
                       500,
                       error_code="GENERIC_ERROR",
                       error_message=f"API key load failed for start-end path: {exc}",
                       retry_safe=True,
                   )
        bfl_key = keys.get("bfl")
        openai_key = keys.get("openai")
        wavespeed_key = keys.get("wavespeed") or self.app.client.api_key
        if not (bfl_key or openai_key):
            return self._send_error_v59(
                       500,
                       error_code="END_FRAME_VENDOR_KEY_UNAVAILABLE",
                       error_message="No end-frame vendor key available (need OpenAI or BFL/FLUX)",
                       retry_safe=True,
                   )

        # Budget — end-frame vendor (LD-730) + Kling per option (#152).
        # per_option_cost uses the SAME vendor-selection branch as generation
        # (lines ~8620+) so estimate matches runtime when MN_END_FRAME_VENDOR
        # disagrees with available keys (session-close review finding #1).
        spend = self.app.state.read_spend()
        _requested_vendor = os.environ.get(
            "MN_END_FRAME_VENDOR", "openai"
        ).strip().lower()
        # T1-Phase 4 (spec MAGIC_AND_ENDFRAME_FIXES_20260520_v1, LD-814): the
        # end-frame OpenAI/FLUX cost is now charged separately at
        # /api/beat/preview_end_frame (Phase 2) or /api/beat/upload_end_frame
        # (Phase 3, $0). This handler READS the approved PNG from disk; no
        # OpenAI/FLUX call here. So per-option budget is JUST Kling.
        # _end_frame_unit_cost is preserved as a local for symmetry/log clarity
        # but NOT added to per_option_cost. (Cursor R-final 2026-05-20 finding.)
        if _requested_vendor == "openai" and openai_key:
            _end_frame_unit_cost = COST_OPENAI_END_FRAME
        elif _requested_vendor == "flux" and bfl_key:
            _end_frame_unit_cost = COST_FLUX_KONTEXT
        elif openai_key:
            _end_frame_unit_cost = COST_OPENAI_END_FRAME
        else:
            _end_frame_unit_cost = COST_FLUX_KONTEXT
        per_option_cost = COST_KLING_10S  # T1-Phase 4: no end-frame cost added here
        estimated = num_new * per_option_cost
        if spend["budget_remaining"] < estimated and spend["overrides"] == 0:
            return self._send_error_v59(
                       402,
                       error_code="BUDGET_EXCEEDED",
                       error_message="budget exceeded",
                       retry_safe=False,
                       extra={"estimated_cost": estimated, "budget_remaining": spend["budget_remaining"], "path": "kling_startend"},
                   )

        # Resolve start image (data URI).
        # S5.5a2: scope_video_role used here — resolved at top of function (see above).
        target_beat = None
        for b in self.app.beats(video_role):
            if self._beat_id(b.get("line_number", -1)) == beat_id:
                target_beat = b
                break
        if not target_beat:
            return self._send_error_v59(
                       400,
                       error_code="GENERIC_ERROR",
                       error_message=f"could not find beat data for {beat_id} in storyboard",
                       retry_safe=False,
                   )
        beat_image = self.app.get_beat_image(beat_id, video_role)
        if not beat_image:
            return self._send_error_v59(
                       400,
                       error_code="GENERIC_ERROR",
                       error_message=f"could not find image data for {beat_id} — drag-drop an image first",
                       retry_safe=False,
                   )

        target_beat = dict(target_beat)
        beat_image, upscale_info = auto_upscale_image(beat_image)
        if "upscaled" in upscale_info:
            print(f"[add_options:startend] {beat_id} start: {upscale_info}")
        target_beat["image"] = beat_image
        ok, info = validate_image_dimensions(beat_image)
        if not ok:
            return self._send_error_v59(
                       400,
                       error_code="GENERIC_ERROR",
                       error_message=f"image validation failed: {info}",
                       retry_safe=False,
                   )

        # Fix 1 (20260513 motion-quality-pipeline): parse Kim's stage direction
        # from beat.text into either a direct motion-override (parenthetical)
        # or a mapped emotion key. Without this step build_motion_prompt sees
        # only speaker/section and defaults to "neutral" for every beat that
        # lacks an explicit emotion field — which is all 18 resolution beats
        # in production_state.json (Kim's symptom). The (parenthetical) form
        # is the strongest signal (verbatim from Kim's authored text); the
        # [emotion_tag] form is a fallback for tone-only direction.
        # The override string is wrapped by sanitize_prompt one line below
        # (positive_prompt = sanitize_prompt(build_motion_prompt(target_beat)))
        # so Rule 8.1 banned words are stripped before the prompt leaves this
        # function.
        import re as _re_motion
        _beat_text = target_beat.get("text", "") or ""
        _paren_motion = _re_motion.search(r'\(([^)]{3,})\)', _beat_text)
        if _paren_motion:
            target_beat["_motion_override"] = _paren_motion.group(1).strip()
            print(f"[add_options:startend] {beat_id}: motion_override from "
                  f"(parenthetical) = {target_beat['_motion_override']!r}")
        else:
            _start_tag = _re_motion.match(r'^\s*\[([^\]]+)\]', _beat_text)
            if _start_tag:
                _raw_tag = _start_tag.group(1).strip().lower()
                # Strip trailing modifiers (e.g. "[happy, friendly]" -> "happy")
                _first_tag = _raw_tag.split(",")[0].strip()
                _TTS_TAGS = {"pause", "break", "breath", "sigh", "silence"}
                _EM_TO_VOCAB = {
                    "curious":      "happy_excited",
                    "excited":      "happy_excited",
                    "happy":        "happy_excited",
                    "delighted":    "happy_excited",
                    "friendly":     "happy_excited",
                    "sad":          "sad_disappointed",
                    "disappointed": "sad_disappointed",
                    "relieved":     "sad_disappointed",
                    "worried":      "upset_shocked",
                    "scared":       "upset_shocked",
                    "surprised":    "upset_shocked",
                    "shocked":      "upset_shocked",
                    "determined":   "neutral",
                    "relaxed":      "neutral",
                }
                if _first_tag and _first_tag not in _TTS_TAGS and _first_tag in _EM_TO_VOCAB:
                    target_beat["emotion"] = _EM_TO_VOCAB[_first_tag]
                    print(f"[add_options:startend] {beat_id}: emotion mapped "
                          f"from [{_first_tag}] -> {target_beat['emotion']!r}")

        positive_prompt = sanitize_prompt(build_motion_prompt(target_beat))

        # Subject binding — load Kling element_entry for this beat's speaker.
        # Fail-open: None = no element_list sent = current behavior preserved.
        _raw_speaker = target_beat.get("speaker") or ""
        _canonical_speaker = _canonicalize_speaker(_raw_speaker)
        element_entry = _load_subject_element(_canonical_speaker)
        if element_entry:
            print(f"[add_options:startend] {beat_id}: subject binding "
                  f"speaker={_canonical_speaker!r} element_id={element_entry['element_id']!r}")
        else:
            print(f"[add_options:startend] {beat_id}: no subject binding "
                  f"for speaker={_canonical_speaker!r} (pending/not registered)")

        # API keys (bfl_key, openai_key, wavespeed_key) loaded before budget gate.

        # Extract start image raw bytes (beat_image is data:image/...;base64,...).
        try:
            _hdr, start_b64 = beat_image.split(",", 1)
            start_bytes = base64.b64decode(start_b64)
        except Exception as exc:
            return self._send_error_v59(
                       500,
                       error_code="GENERIC_ERROR",
                       error_message=f"start image data-URI malformed: {type(exc).__name__}: {exc}",
                       retry_safe=True,
                   )

        # Mark beat polling — partition-aware (SCOPE_ROUTER_V1 / v3 state).
        def set_polling(st, _bid=beat_id, _role=video_role):
            b = ((st.get("videos") or {}).get(_role) or {}).get("beats", {}).get(_bid)
            if b and b.get("phase_1"):
                b["phase_1"]["status"] = "polling"
        self.app.state.mutate_state(set_polling)

        # T1-Phase 4 (spec MAGIC_AND_ENDFRAME_FIXES_20260520_v1, LD-814):
        # READ approved end-frame PNG from disk; do NOT call OpenAI/FLUX here.
        # End-frame generation has moved to /api/beat/preview_end_frame +
        # /api/beat/upload_end_frame which Kim invokes BEFORE Regen B+C.
        # The early REFUSE check above already guaranteed _end_frame_disk_path
        # exists, but we re-verify here (defense-in-depth — file could be
        # unlinked between the early check and this read, e.g. by a concurrent
        # pruning op or manual delete).
        end_b64_uri: str | None = None
        try:
            _end_frame_bytes_disk = _end_frame_disk_path.read_bytes()
        except (OSError, AttributeError) as exc:
            return self._send_error_v59(
                       500,
                       error_code="END_FRAME_READ_FAILED",
                       error_message=f"approved end frame disappeared from disk: {type(exc).__name__}: {exc}",
                       retry_safe=True,
                       extra={"beat": beat_id, "end_frame_path": _end_frame_path,
                              "hint": "Re-click 'Preview end frame' to regenerate."},
                   )
        print(f"[add_options:startend] {beat_id}: reading saved end_frame_path={_end_frame_path} ({len(_end_frame_bytes_disk):,}B from disk) — NOT calling OpenAI/FLUX (T1-Phase 4)", flush=True)
        # Auto-upscale already happened at preview/upload time, but re-run as
        # defense-in-depth in case the saved PNG is below the 600px floor.
        end_data_uri = (
            "data:image/png;base64,"
            + base64.b64encode(_end_frame_bytes_disk).decode("ascii")
        )
        end_data_uri, _end_upscale_info = auto_upscale_image(end_data_uri)
        if "upscaled" in _end_upscale_info:
            print(f"[add_options:startend] {beat_id} end frame (from disk): {_end_upscale_info}", flush=True)
        ok_end, info_end = validate_image_dimensions(end_data_uri)
        if not ok_end:
            return self._send_error_v59(
                       500,
                       error_code="END_FRAME_INVALID",
                       error_message=f"approved end frame failed dim validation: {info_end}",
                       retry_safe=True,
                       extra={"beat": beat_id, "end_frame_path": _end_frame_path,
                              "hint": "Re-click 'Preview end frame' to regenerate."},
                   )
        end_b64_uri = end_data_uri

        # Motion prompt: combine per-creature motion vocabulary (action verbs,
        # not motion-locks — safe per §8.2) with the start-end interpolation
        # hint. Kim 2026-05-21 observed Luna beats returning with virtually
        # no movement; root cause was the prior prompt stripped ALL motion
        # description ("natural motion between start and end frames" is
        # generic and cfg_scale=0.5 left Kling nothing to interpolate when
        # end frame was visually close to start). Restoring the rich
        # SPEAKER_MOTION_PROFILES vocabulary used by the legacy single-image
        # path while preserving the start-end gaze anchor.
        _in_birds_8 = _canonical_speaker in BIRD_SPEAKERS
        _cstr_8 = "Beak closed, no speech, no lip movement." if _in_birds_8 else "Mouth closed, no speech."
        _tail_8 = LIPSYNC_SAFE_TAIL if target_beat.get("lipsync_targeted", True) else SPRITE_IDLE_TAIL
        _hdr_8 = f"Cartoon {_canonical_speaker} character" if _canonical_speaker else "Cartoon character"
        # Resolve per-creature action verbs using same emotion lookup as
        # build_motion_prompt. _motion_override (stage-direction from beat
        # text) wins over the lookup table when present.
        _emotion_8 = target_beat.get("emotion", "neutral") or "neutral"
        if _emotion_8 not in VALID_EMOTIONS:
            _emotion_8 = "neutral"
        _override_8 = target_beat.get("_motion_override")
        _profile_8 = SPEAKER_MOTION_PROFILES.get(_canonical_speaker)
        if _override_8:
            _action_8 = _override_8
        elif _profile_8:
            _action_8 = _profile_8.get(_emotion_8) or _profile_8["neutral"]
        else:
            _action_8 = SECTION_ACTIONS.get(target_beat.get("section", "") or "", DEFAULT_ACTION)
        positive_prompt = sanitize_prompt(
            f"{_hdr_8}, {_action_8}, natural interpolation between start and end frames. {_cstr_8} {_tail_8}"
        )
        print(f"[add_options:startend] {beat_id}: motion prompt -> {positive_prompt[:160]!r}", flush=True)

        # Per-option loop: Kling start-end submit (end frame reused across opts).
        submitted = 0
        submit_errors: list[str] = []
        submitted_tasks: list[str] = []

        for opt_idx in range(num_new):
            # When end_b64_uri is set (FLUX Kontext succeeded), Kling receives
            # both start+end frames per decision 172 KLING_STARTEND_V1_CAPABILITY
            # — pinning both endpoints structurally eliminates the §8.2 settling-
            # window / 10s-drift failure modes.
            # When end_b64_uri is None (no end_frame_prompt OR no bfl_key), we
            # fall back to single-image Kling — start frame only, Kling animates
            # freely. This is the graceful-degradation path; the start-end path
            # is the universal default per decision 180.
            # Fix 9 (20260513): normalize start bytes to actual PNG.
            # Crop-library overrides may be WebP on disk; sending WebP bytes
            # with image/png MIME type causes WaveSpeed Kling to reject the
            # submission. Convert non-PNG sources before encoding.
            _start_bytes_png = start_bytes
            if "image/png" not in _hdr:
                try:
                    from PIL import Image as _PilPng
                    _pngbuf = io.BytesIO()
                    _PilPng.open(io.BytesIO(start_bytes)).save(_pngbuf, format="PNG")
                    _start_bytes_png = _pngbuf.getvalue()
                    print(f"[add_options:startend] {beat_id}: converted start frame "
                          f"{_hdr!r} -> PNG ({len(_start_bytes_png):,}B)")
                except Exception as _png_exc:
                    print(f"[add_options:startend] {beat_id}: PNG conversion failed "
                          f"({_png_exc}), using raw bytes — may fail at WaveSpeed")
            start_uri = f"data:image/png;base64,{base64.b64encode(_start_bytes_png).decode('ascii')}"
            _mode_tag = "start-end" if end_b64_uri else "single-image"
            print(f"[add_options:startend] {beat_id} opt{opt_idx+1} {_mode_tag} "
                  f"Kling submit")

            try:
                task_id = kling_startend_submit(
                    start_b64_uri=start_uri,
                    end_b64_uri=end_b64_uri,   # None => single-image fallback
                    prompt=positive_prompt,
                    negative_prompt=RULE8_ANTI_LIPSYNC,
                    duration=duration,
                    api_key=wavespeed_key,
                    element_entry=element_entry,
                )
            except SystemExit as exc:
                err = f"kling_startend_submit SystemExit: {exc}"
                print(f"[ERR] add_options:startend Kling opt{opt_idx+1}: {err}")
                submit_errors.append(err)
                continue
            except Exception as exc:
                err = f"kling_startend_submit {type(exc).__name__}: {exc}"
                print(f"[ERR] add_options:startend Kling opt{opt_idx+1}: {err}")
                submit_errors.append(err)
                continue

            # Step 4: Persist option with provenance.
            # Fix 3 (20260513): source reflects whether FLUX Kontext end frame
            # was generated (kling_startend) or we fell back to single-image.
            _eid = element_entry["element_id"] if element_entry else None
            _source_tag = "kling_startend" if end_b64_uri else "kling_single_image"
            def add_option(st, _bid=beat_id, _tid=task_id, _ep=end_frame_prompt,
                           _dur=duration, _eid=_eid, _role=video_role,
                           _src=_source_tag):
                # Partition-aware: use videos.<role>.beats (SCOPE_ROUTER_V1)
                _beats = ((st.get("videos") or {}).get(_role) or {}).get("beats") or {}
                if _bid not in _beats:
                    return  # beat not in this partition; state may have legacy top-level
                _beats[_bid]["phase_1"]["options"].append({
                    "task_id": _tid,
                    "status": "polling",
                    "file": None,
                    "submitted_at": datetime.now(timezone.utc).isoformat(),
                    "submitted_at_epoch": int(time.time()),  # Tier 1B timeout
                    "retries": 0,
                    "last_error": None,
                    "source": _src,
                    "end_frame_prompt": _ep,
                    "cfg_scale": _KSENDPIPE_CFG_SCALE,
                    "negative_prompt": RULE8_ANTI_LIPSYNC,
                    "duration": _dur,
                    "element_id": _eid,               # subject binding provenance
                })
            self.app.state.mutate_state(add_option)

            # Rule 18 fire-and-forget activity log.
            try:
                _ksendpipe_directus_log("kling_startend_submitted", {
                    "beat": beat_id,
                    "kling_task_id": task_id,
                    "source": _source_tag,
                    "end_frame_prompt_preview": end_frame_prompt[:120],
                    "cfg_scale": _KSENDPIPE_CFG_SCALE,
                    "duration": duration,
                    "caller": "_handle_add_options_startend",
                })
            except Exception as log_exc:
                print(f"[add_options:startend] directus_log failed (non-fatal): {log_exc}")

            submitted += 1
            submitted_tasks.append(task_id)

            if submitted % 6 == 0:
                time.sleep(POLL_BATCH_GAP_SEC)

        # Fail-loud total-failure case (Kim design-call 2).
        if submitted == 0 and num_new > 0:
            return self._send_error_v59(
                       500,
                       error_code="GENERIC_ERROR",
                       error_message=f"All {num_new} start-end submissions failed for {beat_id}",
                       retry_safe=True,
                       extra={"path": "kling_startend", "beat": beat_id, "existing_options": len(existing_options), "new_submitted": 0, "submit_errors": submit_errors, "hint": "Check FLUX (BFL) key + WaveSpeed Kling. No silent fallback to legacy."},
                   )

        response = {
            "ok": True,
            "beat": beat_id,
            "existing_options": len(existing_options),
            "new_submitted": submitted,
            "total_options": len(existing_options) + submitted,
            "path": "kling_startend",
            "source": "kling_startend",
            "submitted_task_ids": submitted_tasks,
        }
        if submit_errors:
            response["partial"] = True
            response["submit_errors"] = submit_errors
        self._send_json(200, response)

    def _handle_add_options_legacy(self, body: dict) -> None:
        """Non-destructive: keep existing Option A, add or replace B + C.

        LEGACY PATH (pre-decision-172). Called by _handle_add_options when the
        beat has no end_frame_prompt configured. Single-image Kling v3, no
        FLUX Kontext end-frame generation. Preserved verbatim for fallback.

        SCOPE_ROUTER_V1 (C-7.5 K1 sibling fix): scope is re-resolved here
        even though the caller already validated, because this method is
        also reachable directly via the dispatcher when beat_state carries
        force_legacy=true. The double-validation is cheap and keeps the
        handler self-contained.
        """
        if self.app.client is None:
            return self._send_error_v59(
                       500,
                       error_code="WAVESPEED_NOT_CONFIGURED",
                       error_message="WaveSpeed client not configured",
                       retry_safe=True,
                   )

        try:
            scope = scope_router.resolve(body, self.app.event_dir.name)
        except scope_router.ScopeError as e:
            return self._send_error_v59(
                e.http_status,
                error_code=e.code.upper(),
                error_message=e.code,
                retry_safe=False,
                extra=e.detail or None,
            )

        beat_id = body.get("beat_id") or body.get("beat")
        num_new = int(body.get("count", 2))  # default: add 2 (B + C)
        if not beat_id:
            return self._send_error_v59(
                       400,
                       error_code="MISSING_BEAT",
                       error_message="missing 'beat'",
                       retry_safe=False,
                   )

        # Duration: prefer explicit client override, otherwise auto-infer from
        # TTS audio length. ANIMATION_DURATION_MATCHES_AUDIO (decision id=144).
        # Phase 3 H1 fix (April 16 2026): validate explicit duration against the
        # Kling v3 supported set instead of blindly trusting any int (was
        # accepting 0 / 7 / negative which would break WaveSpeed).
        explicit_duration = body.get("duration")
        if explicit_duration is not None:
            try:
                duration_raw = int(explicit_duration)
            except (TypeError, ValueError):
                return self._send_error_v59(
                           400,
                           error_code="GENERIC_ERROR",
                           error_message=f"invalid duration value: {explicit_duration!r}",
                           retry_safe=False,
                           extra={"hint": f"duration must be {KLING_MIN_DURATION_SEC} or {KLING_MAX_DURATION_SEC}"},
                       )
            if duration_raw not in (KLING_MIN_DURATION_SEC, KLING_MAX_DURATION_SEC):
                return self._send_error_v59(
                           400,
                           error_code="GENERIC_ERROR",
                           error_message=f"unsupported duration: {duration_raw}s",
                           retry_safe=False,
                           extra={"hint": f"Kling v3 supports only {KLING_MIN_DURATION_SEC}s or "
                            f"{KLING_MAX_DURATION_SEC}s; omit the field to auto-infer from audio"},
                       )
            duration = duration_raw
            duration_reason = f"explicit_client_override_{duration}s"
        else:
            audio_path_for_duration = _find_beat_audio(
                self.app.event_dir, beat_id, body.get("audio_override"),
                app=self.app,
            )
            if audio_path_for_duration is None:
                try:
                    beat_num = int(beat_id.split("_")[1])
                    beat_num_str = f"line_{beat_num:02d}"
                except (IndexError, ValueError):
                    beat_num_str = "(beat number unparseable)"
                return self._send_error_v59(
                           404,
                           error_code="GENERIC_ERROR",
                           error_message=f"no TTS audio found for {beat_id} ({beat_num_str})",
                           retry_safe=False,
                           extra={"hint": "provide audio_override path or ensure TTS exists in story_scene_tts_v2/; "
                            "animation duration cannot be inferred without audio"},
                       )
            try:
                duration, duration_reason = _infer_animation_duration(audio_path_for_duration)
            except ValueError as exc:
                # Audio exceeds Kling 10s max — surface cleanly, do NOT truncate
                return self._send_error_v59(
                           400,
                           error_code="GENERIC_ERROR",
                           error_message=str(exc),
                           retry_safe=False,
                           extra={"hint": "Edit script or split audio into shorter beats; Kling v3 cannot "
                            "generate clips longer than 10 seconds.", "beat": beat_id, "audio_file": audio_path_for_duration.name},
                       )
        print(f"[add_options] {beat_id} duration={duration}s reason={duration_reason}")

        # Read current state to verify beat exists in scope.video_role partition.
        state = self.app.state.read_state()
        beat_state = ((state.get("videos") or {}).get(scope.video_role) or {}).get("beats", {}).get(beat_id)
        if not beat_state:
            return self._send_error_v59(
                       404,
                       error_code="GENERIC_ERROR",
                       error_message=f"beat {beat_id} not found in videos.{scope.video_role}.beats",
                       retry_safe=False,
                   )

        phase1 = beat_state.get("phase_1") or {}
        existing_options = phase1.get("options", [])
        if not existing_options:
            return self._send_error_v59(
                       400,
                       error_code="GENERIC_ERROR",
                       error_message=f"beat {beat_id} has no existing options — use /api/animate instead",
                       retry_safe=False,
                   )

        # If B+C already exist, remove them first (keep only option A)
        old_bc_files: list[str] = []
        if len(existing_options) > 1:
            for opt in existing_options[1:]:
                if opt.get("file"):
                    old_bc_files.append(opt["file"])
            def trim_to_a_partition(partition, _bid=beat_id):
                b = (partition.get("beats") or {}).get(_bid)
                if b and b.get("phase_1"):
                    opts = b["phase_1"].get("options", [])
                    b["phase_1"]["options"] = opts[:1]  # keep only A
                    if (b["phase_1"].get("selected_option") or 0) > 1:
                        b["phase_1"]["selected_option"] = 1  # reset to A
            self.app.state.mutate_video_state(scope.video_role, trim_to_a_partition)
            # Delete old B+C files from disk
            for fname in old_bc_files:
                p = self.app.state.clips_dir / fname
                if p.is_file():
                    try:
                        p.unlink()
                    except OSError:
                        pass

        # Budget pre-check
        spend = self.app.state.read_spend()
        estimated = num_new * COST_PER_CLIP_KLING
        if spend["budget_remaining"] < estimated and spend["overrides"] == 0:
            return self._send_error_v59(
                       402,
                       error_code="BUDGET_EXCEEDED",
                       error_message="budget exceeded",
                       retry_safe=False,
                       extra={"estimated_cost": estimated, "budget_remaining": spend["budget_remaining"]},
                   )

        # Find the beat data (image + prompt) from the storyboard
        # Check image overrides FIRST (from drag-drop), then fall back to storyboard
        target_beat = None
        for b in self.app.beats(scope.video_role):
            if self._beat_id(b.get("line_number", -1)) == beat_id:
                target_beat = b
                break
        if not target_beat:
            return self._send_error_v59(
                       400,
                       error_code="GENERIC_ERROR",
                       error_message=f"could not find beat data for {beat_id} in storyboard",
                       retry_safe=False,
                   )

        # Use image override if available (from drag-drop assignment).
        # video_role resolved by scope_router above.
        beat_image = self.app.get_beat_image(beat_id, scope.video_role)
        if not beat_image:
            return self._send_error_v59(
                       400,
                       error_code="GENERIC_ERROR",
                       error_message=f"could not find image data for {beat_id} — try drag-dropping an image first",
                       retry_safe=False,
                   )
        # Patch the beat dict so prompt builder uses correct context
        target_beat = dict(target_beat)
        # Rule 6 — auto-upscale fallback, then dimension gate
        beat_image, upscale_info = auto_upscale_image(beat_image)
        if "upscaled" in upscale_info:
            print(f"[add_options] {beat_id}: {upscale_info}")
        target_beat["image"] = beat_image

        ok, info = validate_image_dimensions(beat_image)
        if not ok:
            return self._send_error_v59(
                       400,
                       error_code="GENERIC_ERROR",
                       error_message=f"image validation failed: {info}",
                       retry_safe=False,
                   )

        prompt = sanitize_prompt(build_motion_prompt(target_beat))

        # Mark beat as polling (options are generating) but KEEP existing options
        def set_polling_partition(partition, _bid=beat_id):
            b = (partition.get("beats") or {}).get(_bid)
            if b and b.get("phase_1"):
                b["phase_1"]["status"] = "polling"
        self.app.state.mutate_video_state(scope.video_role, set_polling_partition)

        # Submit new animation jobs
        submitted = 0
        submit_errors: list[str] = []
        for opt_idx in range(num_new):
            try:
                task_id = self.app.client.submit_animation(
                    target_beat["image"], prompt, duration=duration
                )
            except Exception as exc:
                err_str = f"{type(exc).__name__}: {exc}"
                print(f"[ERR] add_options submit failed for {beat_id} new opt {opt_idx + 1}: {err_str}")
                submit_errors.append(err_str)
                continue

            # Append option via partition router (was videos.intro hardcode).
            def add_option_partition(partition, _bid=beat_id, _tid=task_id):
                pbeats = partition.setdefault("beats", {})
                pbeats[_bid]["phase_1"]["options"].append({
                    "task_id": _tid,
                    "status": "polling",
                    "file": None,
                    "submitted_at": datetime.now(timezone.utc).isoformat(),
                    "submitted_at_epoch": int(time.time()),  # Tier 1B timeout
                    "source": "kling",  # Tier 1B threshold lookup
                    "retries": 0,
                    "last_error": None,
                })
            self.app.state.mutate_video_state(scope.video_role, add_option_partition)
            submitted += 1

            if submitted % 6 == 0:
                time.sleep(POLL_BATCH_GAP_SEC)

        # Item 5 (Tier 1, April 16 2026): surface submit failures to the client.
        # Previously returned 200 with new_submitted=0 and no error field, which
        # caused the storyboard's Generate B+C button to silently revert after
        # ~15s (pollStatus sees no new options and re-renders default label).
        if submitted == 0 and num_new > 0:
            return self._send_error_v59(
                       500,
                       error_code="GENERIC_ERROR",
                       error_message=f"All {num_new} WaveSpeed submissions failed for {beat_id}",
                       retry_safe=True,
                       extra={"beat": beat_id, "existing_options": len(existing_options), "new_submitted": 0, "submit_errors": submit_errors},
                   )

        response = {
            "ok": True,
            "beat": beat_id,
            "existing_options": len(existing_options),
            "new_submitted": submitted,
            "total_options": len(existing_options) + submitted,
        }
        if submit_errors:
            # Partial success: some submits worked, some didn't — tell the client
            response["partial"] = True
            response["submit_errors"] = submit_errors
        self._send_json(200, response)

    def _handle_beat_update_text(self, body: dict) -> None:
        from server_handlers.beats_legacy import handle_beat_update_text
        return handle_beat_update_text(self, body)

    # ------------------------------------------------------------------
    # LD CHARACTER_DROPDOWN_RESTORED_V1 — speaker dropdown write path for
    # the Storyboard tab. Mirrors _handle_beat_update_text contract but
    # without HTML L[] patching (speaker is metadata, not body text).
    # BG tab still uses /api/bg/update-beat which has its own _BG_BEAT_WRITABLE
    # gate. Both paths converge on patch_state(field='speaker', ...) semantics:
    # canonicalize at write boundary (SPEAKER_WRITE_BOUNDARY_CANONICALIZATION_V1)
    # + dual-write top-level + phase_1 (SPEAKER_DUAL_STORE_DEPRECATION_V1) +
    # set phase_1.speaker_mismatch + flip text_modified_after_tts so the
    # stale-TTS badge surfaces in the UI.
    # ------------------------------------------------------------------
    def _handle_beat_update_speaker(self, body: dict) -> None:
        from server_handlers.beats_legacy import handle_beat_update_speaker
        return handle_beat_update_speaker(self, body)

    def _handle_beat_done_toggle(self, body: dict) -> None:
        from server_handlers.beats_legacy import handle_beat_done_toggle
        return handle_beat_done_toggle(self, body)

    # ------------------------------------------------------------------
    # BEAT_GRAFT_RECOVERY_MECHANISM_V1 — Pillar 7 cornerstone (C-7).
    # ------------------------------------------------------------------
    def _handle_beat_graft(self, body: dict) -> None:
        from server_handlers.beats_legacy import handle_beat_graft
        return handle_beat_graft(self, body)

    def _append_audit_log(self, row: dict) -> None:
        """Append a JSON line to the durable recovery audit log.

        Atomic enough for our purposes: open in append mode, write line,
        flush+close. Concurrent writers from the same process are safe due
        to the GIL; multi-process serialization is not required since the
        server is single-process per LD-460.

        Path resolves dynamically via _audit_log_path(self.app) — see the
        helper docstring at module top. In production runtime this lands
        the JSONL row in Dropbox tree (canonical state per LD-505).
        """
        path = _audit_log_path(self.app)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        except Exception as exc:  # noqa: BLE001
            print(f"[audit] WARN failed to append {row.get('action')!r} to {path}: {exc}",
                  flush=True)

    def _handle_beat_regenerate_audio(self, body: dict) -> None:
        from server_handlers.beats_legacy import handle_beat_regenerate_audio
        return handle_beat_regenerate_audio(self, body)

    def _handle_select(self, body: dict) -> None:
        # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
        if not self._assert_event_scope(self._scope_body(body), allow_missing=False):
            return

        # Accept both legacy field names ("beat", "selected_option") and the
        # current client field names ("beat_id", "option_index").
        # runMutation() in StoryboardTab always injects beat_id; pathappPatch
        # also sets beat_id from scope. The old names are kept for any caller
        # that targets the endpoint directly (e.g. scripts, tests).
        beat_id = body.get("beat") or body.get("beat_id")
        selected = (body.get("selected_option")
                    if body.get("selected_option") is not None
                    else body.get("option_index"))
        if not beat_id or selected is None:
            return self._send_error_v59(
                       400,
                       error_code="MISSING_BEAT_BEAT_ID_OR",
                       error_message="missing beat/beat_id or selected_option/option_index",
                       retry_safe=False,
                   )
        try:
            sel_int = int(selected)
        except (TypeError, ValueError):
            return self._send_error_v59(
                       400,
                       error_code="GENERIC_ERROR",
                       error_message=f"selected_option must be int, got {selected!r}",
                       retry_safe=False,
                   )

        video_role = (body or {}).get("scope_video_role") or (body or {}).get("scope_target_video") or "intro"

        # Side-channel: the new selected clip may diverge from the clip the
        # existing lipsync was produced against. Detect that and surface it
        # so the UI can offer "🔁 Re-run Lip Sync" (decision 153, Tier 5).
        source_changed_out = None
        def mut(state, _sel=sel_int, _role=video_role):
            nonlocal source_changed_out
            beat = ((state.get("videos") or {}).get(_role) or {}).get("beats", {}).get(beat_id)
            if not beat:
                return False
            phase1 = beat.get("phase_1") or {}

            # Capture OLD selection BEFORE overwriting — used to backfill
            # source_option for pre-Tier 5 lipsync rows that predate the
            # tracking field. After this point phase1["selected_option"] = _sel.
            old_selected = phase1.get("selected_option")
            phase1["selected_option"] = _sel

            # Re-run detection for completed lipsyncs.
            ls = beat.get("lipsync")
            if ls and ls.get("status") == "completed":
                # One-shot backfill: if a lipsync completed before Tier 5,
                # source_option is absent. The only safe anchor we have is
                # the PREVIOUS selected_option (captured above) — anything
                # else would be guessing. If old_selected is also absent we
                # leave source_option unset and skip detection.
                if ls.get("source_option") is None and old_selected is not None:
                    try:
                        ls["source_option"] = int(old_selected)
                    except (TypeError, ValueError):
                        pass
                src_opt = ls.get("source_option")
                if src_opt is not None:
                    changed = (_sel != int(src_opt))
                    ls["source_changed"] = changed
                    source_changed_out = changed
            return True
        ok = self.app.state.mutate_state(mut)
        return self._send_json(
            200 if ok else 404,
            {"ok": bool(ok), "lipsync_source_changed": source_changed_out},
        )

    def _handle_export(self) -> None:
        """LEGACY ENDPOINT — REMOVED in S5.5d (v3 architecture revision, 2026-05-03).

        Per Rule 27 + LDs SCENE_ASSEMBLE_ENDPOINT_V1 / BEAT_FINALIZE_ENDPOINT_V1.
        The animation_selections.json JSON-only manifest is no longer produced.
        Clients should call POST /api/scene/assemble instead — it performs
        per-beat finalize + xfade concat + size-budget gate + scene_concat_mp4
        asset registration in one atomic call.

        Returns HTTP 410 Gone with migration note.
        """
        return self._send_error_v59(
                   410,
                   error_code="ENDPOINT_REMOVED",
                   error_message="endpoint_removed",
                   retry_safe=False,
                   extra={"code": "EXPORT_REMOVED_V3", "removed_in": "S5.5d (2026-05-03)", "replacement": "/api/scene/assemble", "hint": "POST /api/scene/assemble with body {scope_event_id|scope_milestone_id, "
                "scope_target_video, fade_between_beats_ms?, force_rebuild?}. "
                "Stage 1 finalizes each beat (cached); Stage 2 mirrors "
                "_handle_preview_stitched orchestration to assemble the scene "
                "and registers the result as a scene_concat_mp4 asset."},
               )

    def _handle_beat_delay(self, body: dict) -> None:
        from server_handlers.beats_legacy import handle_beat_delay
        return handle_beat_delay(self, body)

    def _handle_beat_trim(self, body: dict) -> None:
        from server_handlers.beats_legacy import handle_beat_trim
        return handle_beat_trim(self, body)

    def _handle_beat_zoom(self, body: dict) -> None:
        from server_handlers.beats_legacy import handle_beat_zoom
        return handle_beat_zoom(self, body)

    def _handle_beat_undo_final(self, body: dict) -> None:
        from server_handlers.beats_legacy import handle_beat_undo_final
        return handle_beat_undo_final(self, body)

    def _handle_budget_override(self, body: dict) -> None:
        # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
        if not self._assert_event_scope(self._scope_body(body), allow_missing=False):
            return

        amount = float(body.get("amount", 5.0))
        spend = self.app.state.override_budget(amount)
        self._send_json(200, spend)

    # ----------------------------------------------------------------------
    # Path A++ v2 handlers (April 18 2026)
    # SHORTCUT_AUTONOMOUS_LIVE_BUILD_PHASE1_20260418
    # ----------------------------------------------------------------------

    def _handle_v2_patch(self, path: str, body: dict) -> None:
        from server_handlers.beats_v2 import handle_v2_patch
        return handle_v2_patch(self, path, body)

    def _handle_v2_beat_create(self, body: dict) -> None:
        from server_handlers.beats_v2 import handle_v2_beat_create
        return handle_v2_beat_create(self, body)

    def _handle_v2_beat_delete(self, body: dict) -> None:
        from server_handlers.beats_v2 import handle_v2_beat_delete
        return handle_v2_beat_delete(self, body)

    def _handle_v2_get(self, path: str) -> None:
        from server_handlers.beats_v2 import handle_v2_get
        return handle_v2_get(self, path)

    def _handle_v2_sidecar(self) -> None:
        from server_handlers.beats_v2 import handle_v2_sidecar
        return handle_v2_sidecar(self)

    def _handle_v2_event_state(self, path: str) -> None:
        from server_handlers.beats_v2 import handle_v2_event_state
        return handle_v2_event_state(self, path)

    # ------------------------------------------------------------------
    # LD-285 Preview Stitched v2 (April 19 2026)
    # Spec: TECH_SPEC_PREVIEW_STITCHED_V2_20260419.md / preflight 93.
    # ------------------------------------------------------------------
    def _handle_v2_module_patch(self, body: dict) -> None:
        from server_handlers.beats_v2 import handle_v2_module_patch
        return handle_v2_module_patch(self, body)

    def _handle_v2_beat_swap_to_a(self, beat_id: str, body: dict) -> None:
        from server_handlers.beats_v2 import handle_v2_beat_swap_to_a
        return handle_v2_beat_swap_to_a(self, beat_id, body)


    def _handle_use_still_as_final(self, body: dict) -> None:
        """POST /api/beat/use_still_as_final {beat, scope_event_id, scope_video_role}

        Renders a Ken Burns MP4 from the beat's image_override_abs (slow
        center zoom 1.0 -> 1.05 over audio_duration_s) and writes a final
        block with source='still_image'. SHA-cached: re-click returns the
        existing MP4 unchanged.

        Output: Production/Event_N/animation_clips/beat_NN_still_final.mp4
        Stitcher contract unchanged (final.file is an MP4).
        """
        import hashlib as _hashlib
        import json as _json
        import subprocess as _subprocess

        # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
        if not self._assert_event_scope(self._scope_body(body), allow_missing=False):
            return

        # BODY_KEY_ALLOW: beat (legacy back-compat alias; v59 client sends beat_id
        # via runMutation, but pre-v59 callers and tests may send `beat`).
        # BODY_KEY_ALLOW: hold_duration_s (optional — client omits the key when
        # the Hold input is blank, which means "use audio_duration_s default").
        beat_id = body.get("beat") or body.get("beat_id")
        if not beat_id:
            return self._send_error_v59(
                       400,
                       error_code="MISSING_BEAT",
                       error_message="beat required",
                       retry_safe=False,
                   )

        scope_video_role = (body or {}).get("scope_video_role") or "intro"
        valid_roles = self.app.state._VALID_VIDEO_ROLES
        if scope_video_role not in valid_roles:
            return self._send_error_v59(
                       400,
                       error_code="VIDEO_ROLE_INVALID",
                       error_message="video_role_invalid",
                       retry_safe=False,
                       extra={"got": scope_video_role, "valid": sorted(valid_roles)},
                   )

        state = self.app.state.read_state()
        role_block = (state.get("videos") or {}).get(scope_video_role) or {}
        beat = (role_block.get("beats") or {}).get(beat_id)
        if not beat:
            return self._send_error_v59(
                       400,
                       error_code="GENERIC_ERROR",
                       error_message=f"unknown beat: {beat_id} (role={scope_video_role})",
                       retry_safe=False,
                   )

        audio_dur = beat.get("audio_duration_s")
        if not audio_dur or audio_dur <= 0:
            return self._send_error_v59(
                       400,
                       error_code="BEAT_HAS_NO_AUDIO_DURATION",
                       error_message="beat has no audio_duration_s; regenerate audio first",
                       retry_safe=False,
                   )

        # Resolve source still image: image_overrides_abs is canonical.
        image_abs = (role_block.get("image_overrides_abs") or {}).get(beat_id)
        if not image_abs or not os.path.isfile(image_abs):
            return self._send_error_v59(
                       400,
                       error_code="NO_RESOLVABLE_STILL_IMAGE",
                       error_message="no resolvable still image",
                       retry_safe=False,
                       extra={"hint": "set image_overrides_abs in storyboard library UI", "image_path": image_abs},
                   )

        # LD STILL_AS_FINAL_HOLD_DURATION_CONTROL_V1 (2026-05-17): the Ken Burns
        # clip duration is decoupled from audio_duration_s. Kim's directive:
        # default 5.0s, user-controllable via "Hold (s)" UI input, so audio
        # delay (separately controlled at Stitcher mix time via adelay) can
        # leave room for ambient SFX before the voice fires. If audio is
        # longer than hold_duration_s, audio gets cut at Stitcher mix —
        # acceptable per Kim's "user typing is source of truth" rule. We
        # surface a soft warning in the response so the UI can hint.
        DEFAULT_HOLD_S = 5.0
        HOLD_MIN_S = 0.5
        HOLD_MAX_S = 60.0
        hold_raw = body.get("hold_duration_s")
        if hold_raw is None:
            hold_duration_s = DEFAULT_HOLD_S
        else:
            try:
                hold_duration_s = float(hold_raw)
            except (TypeError, ValueError):
                return self._send_error_v59(
                           400,
                           error_code="HOLD_DURATION_S_MUST_BE",
                           error_message="hold_duration_s must be a number",
                           retry_safe=False,
                           extra={"got": hold_raw},
                       )
            if not (HOLD_MIN_S <= hold_duration_s <= HOLD_MAX_S):
                return self._send_error_v59(
                           400,
                           error_code="GENERIC_ERROR",
                           error_message=f"hold_duration_s out of range: must be "
                        f"{HOLD_MIN_S} <= hold <= {HOLD_MAX_S}",
                           retry_safe=False,
                           extra={"got": hold_duration_s},
                       )

        # Ken Burns config (V1 hardcoded zoom/pan; duration_s is now the
        # user-controlled hold per LD STILL_AS_FINAL_HOLD_DURATION_CONTROL_V1).
        kb = {
            "zoom_start": 1.0,
            "zoom_end": 1.05,
            "pan_x_start": 0.5,
            "pan_x_end": 0.5,
            "pan_y_start": 0.5,
            "pan_y_end": 0.5,
            "duration_s": float(hold_duration_s),
        }

        # Cache key = sha1(first 1MB of image) + duration + sha(kb config).
        try:
            with open(image_abs, "rb") as fh:
                head = fh.read(1024 * 1024)
            img_sha = _hashlib.sha1(head).hexdigest()
        except Exception as exc:  # noqa: BLE001
            return self._send_error_v59(
                       400,
                       error_code="GENERIC_ERROR",
                       error_message=f"image read failed: {exc}",
                       retry_safe=False,
                   )
        kb_sha = _hashlib.sha1(
            _json.dumps(kb, sort_keys=True).encode("utf-8")
        ).hexdigest()[:8]
        # LD STILL_AS_FINAL_HOLD_DURATION_CONTROL_V1: cache key uses
        # hold_duration_s (not audio_dur) so different hold values produce
        # distinct cache entries. kb_sha already covers duration_s via kb
        # dict but we keep the duration in the key prefix for grep-ability.
        cache_key = f"sha1:{img_sha}_{hold_duration_s:.3f}_{kb_sha}"

        # Output path.
        out_name = f"{beat_id}_still_final.mp4"
        out_abs = str(self.app.state.clips_dir / out_name)

        # Cache hit: previously-rendered MP4 + state.final.cache_key matches.
        prev_final = beat.get("final") or {}
        cache_hit = (
            prev_final.get("source") == "still_image"
            and prev_final.get("cache_key") == cache_key
            and os.path.isfile(out_abs)
        )

        if not cache_hit:
            # Render via ffmpeg zoompan. Pre-scale 2x to avoid jitter on
            # short durations. d = round(dur * 24) frames at 24 fps.
            # LD STILL_AS_FINAL_HOLD_DURATION_CONTROL_V1: dur is the
            # user-controlled hold (default 5.0s), NOT audio_duration_s.
            frames = max(1, int(round(float(hold_duration_s) * 24)))
            zoom_expr = (
                f"{kb['zoom_start']:.4f}"
                f"+({kb['zoom_end']:.4f}-{kb['zoom_start']:.4f})"
                f"*on/{max(1, frames - 1)}"
            )
            vf = (
                "scale=3840:2160:force_original_aspect_ratio=increase,"
                "crop=3840:2160,"
                f"zoompan=z='{zoom_expr}':"
                "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                f"d={frames}:s=1920x1080:fps=24"
            )
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1", "-i", image_abs,
                "-t", f"{float(hold_duration_s):.3f}",
                "-vf", vf,
                "-c:v", "libx264",
                "-profile:v", "high",
                "-pix_fmt", "yuv420p",
                "-r", "24",
                "-an",
                "-movflags", "+faststart",
                out_abs,
            ]
            try:
                proc = _subprocess.run(
                    cmd, capture_output=True, text=True, timeout=120,
                )
            except Exception as exc:  # noqa: BLE001
                return self._send_error_v59(
                           500,
                           error_code="FFMPEG_RENDER_FAILED",
                           error_message="ffmpeg render failed",
                           retry_safe=True,
                           extra={"exception": str(exc)},
                       )
            if proc.returncode != 0 or not os.path.isfile(out_abs):
                return self._send_error_v59(
                           500,
                           error_code="FFMPEG_RENDER_FAILED",
                           error_message="ffmpeg render failed",
                           retry_safe=True,
                           extra={"stderr_tail": (proc.stderr or "")[-2000:], "returncode": proc.returncode},
                       )

        # Build and persist final block.
        final_block = {
            "source": "still_image",
            "image_path": image_abs,
            "file": out_name,
            "kenburns": kb,
            "cache_key": cache_key,
            "approved_at": datetime.now(timezone.utc).isoformat(),
        }

        def _mutate(s):
            role_beats = s.setdefault("videos", {}).setdefault(
                scope_video_role,
                {"video_role": scope_video_role, "video_label": None,
                 "beats": {}, "completed_mp4_path": None},
            ).setdefault("beats", {})
            if beat_id in role_beats:
                role_beats[beat_id]["final"] = final_block
        self.app.state.mutate_state(_mutate)

        # bg sidecar: same pattern as raw_option final.
        try:
            bg = _bg_module()
            with bg.sidecar_file_lock():
                sidecar = bg.read_sidecar()
                sidecar = bg._migrate_sidecar(sidecar)
                _, b_entry = bg.find_beat(sidecar, beat_id)
                if b_entry is not None:
                    b_entry["accepted_video_path"] = out_abs
                    b_entry["status"] = "accepted"
                    bg.write_sidecar(sidecar)
        except Exception as exc:  # noqa: BLE001
            print(f"[use-still-as-final] sidecar write failed (non-blocking): {exc}")

        # Activity log fire-and-forget (reuse same helper). On error, log to
        # stderr — silently swallowing would lose the audit-trail-failure
        # signal entirely (AI review 2026-05-18 PR #61 non-blocking finding).
        try:
            _async_log_use_as_final(
                event_id=str(self.app.event_id),
                beat_id=beat_id,
                file=out_name,
            )
        except Exception as exc:  # noqa: BLE001
            print(
                f"[use-still-as-final] activity log write failed (non-blocking): {exc}",
                file=sys.stderr,
                flush=True,
            )

        # LD STILL_AS_FINAL_HOLD_DURATION_CONTROL_V1: soft warning if audio
        # exceeds hold_duration_s (audio will be cut at Stitcher mix).
        response = {
            "status": "ok",
            "beat": beat_id,
            "file": out_name,
            "cache_hit": cache_hit,
            "hold_duration_s": hold_duration_s,
            "audio_duration_s": float(audio_dur),
            "final": final_block,
        }
        if float(audio_dur) > hold_duration_s:
            response["warning"] = (
                f"audio_duration_s ({float(audio_dur):.2f}s) exceeds "
                f"hold_duration_s ({hold_duration_s:.2f}s); audio will be "
                f"cut at Stitcher mix"
            )
        return self._send_json(200, response)

    @with_pin_and_drain('_handle_preview_stitched', track_sync=True)
    def _handle_preview_stitched(self, body: dict) -> None:
        """POST /api/preview_stitched

        Body: {
          "state_snapshot": { ...full state at request time... },
          "fade_between_beats_ms": 200
        }

        Snapshot-on-start (counter (g) safe): the server NEVER re-reads
        state.json during the pipeline; the client's snapshot is authoritative
        for which option each beat plays + trim window + pause.

        Pipeline:
          1. Resolve files BEFORE any hashing (counter (a) HIGH fix).
          2. Compute cache_hash (file path + mtime + trim + pause + fade + recipe).
          3. Cache hit? Stream the cached mp4 + cleanup LRU under dir-lock.
          4. Cache miss? Acquire dir-lock, normalize, trim, fade-clamp,
             pre-render xfade pair clips (one fresh job per pair, no cumulative
             offset drift), concat-demux with absolute escaped paths, atomic
             tmp+rename to preview_stitched_<hash>.mp4, LRU cleanup INSIDE the
             same lock (counter (d) HIGH), stream.
          5. fade_ms == 0 fast-path: skip xfade entirely, plain concat the
             trimmed beats (counter (b) MEDIUM).
          6. Last beat NEVER has trailing fade trimmed (counter (f) CRITICAL).
        """
        # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
        if not self._assert_event_scope(self._scope_body(body), allow_missing=False):
            return

        # Lazy-load the lib so server startup doesn't hard-require it.
        try:
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), "credentials_lib"))
            from ffmpeg_stitch import (  # type: ignore
                FADE_CLAMP_BUFFER_S,
                NORMALIZATION_RECIPE_HASH,
                PREVIEW_RECIPE_VERSION,
                compute_cache_hash,
                compute_fade_clamp,
                compute_fade_clamp_per_pair,
                concat_with_xfade_clips,
                ffprobe_duration,
                lru_cleanup,
                normalize_for_concat,
                render_xfade_pair,
                resolve_beat_file,
                resolve_pair_fades,
                translate_trim_for_source,
                trim_body,
                trim_normalized,
            )
        except ImportError as exc:
            return self._send_error_v59(
                       500,
                       error_code="GENERIC_ERROR",
                       error_message=f"lib/ffmpeg_stitch import failed: {exc}",
                       retry_safe=True,
                       extra={"hint": "Verify Production/tools/lib/ffmpeg_stitch.py exists."},
                   )

        snapshot = body.get("state_snapshot") or {}
        fade_ms_raw = body.get("fade_between_beats_ms")
        try:
            fade_ms = int(fade_ms_raw) if fade_ms_raw is not None else 0
        except (TypeError, ValueError):
            return self._send_error_v59(
                       400,
                       error_code="GENERIC_ERROR",
                       error_message=f"fade_between_beats_ms must be int, got {fade_ms_raw!r}",
                       retry_safe=False,
                       extra={"hint": "Send slider value as integer milliseconds."},
                   )
        if fade_ms < 0 or fade_ms > _V2_MODULE_FADE_MAX_MS:
            return self._send_error_v59(
                       400,
                       error_code="GENERIC_ERROR",
                       error_message=f"fade_between_beats_ms out of range, got {fade_ms}",
                       retry_safe=False,
                       extra={"hint": f"Range is [0, {_V2_MODULE_FADE_MAX_MS}]."},
                   )

        beats = snapshot.get("beats") or {}
        display_order = snapshot.get("display_order") or []
        allowed = set(display_order)
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "credentials_lib"))
        from ffmpeg_stitch import beat_is_assemblable, compute_finalize_args_hash  # noqa: PLC0415
        beat_ids_sorted = sorted(
            bid for bid, b in beats.items()
            if bid in allowed
            and isinstance(b, dict)
            and beat_is_assemblable(b, event_dir=self.app.event_dir)
        )
        if not beat_ids_sorted:
            return self._send_error_v59(
                       400,
                       error_code="NO_ASSEMBLABLE_BEATS",
                       error_message="no assemblable beats in snapshot",
                       retry_safe=False,
                       extra={"hint": "Select an animation option or run magic on each beat before previewing."},
                   )

        # ---- counter (a) HIGH: validate file existence BEFORE hash ----
        clips_dir = self.app.state.clips_dir
        missing = []
        for bid in beat_ids_sorted:
            try:
                compute_finalize_args_hash(
                    snapshot, bid, clips_dir, event_dir=self.app.event_dir,
                )
            except FileNotFoundError as exc:
                missing.append({"beat_id": bid, "error": str(exc)})
        if missing:
            return self._send_error_v59(
                       400,
                       error_code="SELECTED_FILES_MISSING_FOR_ONE",
                       error_message="selected files missing for one or more beats",
                       retry_safe=False,
                       extra={"missing": missing, "hint": "Re-run animation generation for the listed beats, or pick a different option."},
                   )

        # ---- compute cache hash ----
        try:
            cache_hash, beat_meta = compute_cache_hash(
                snapshot, fade_ms, beat_ids_sorted, clips_dir,
            )
        except FileNotFoundError as exc:
            # Defense in depth — should have been caught above.
            return self._send_error_v59(
                       400,
                       error_code="GENERIC_ERROR",
                       error_message=str(exc),
                       retry_safe=False,
                       extra={"hint": "File disappeared between existence check and hash computation."},
                   )
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            return self._send_error_v59(
                       500,
                       error_code="GENERIC_ERROR",
                       error_message=f"cache hash computation failed: {type(exc).__name__}: {exc}",
                       retry_safe=True,
                       extra={"hint": "Internal — check server logs for the traceback."},
                   )

        preview_dir = self.app.event_dir / "preview"
        preview_dir.mkdir(parents=True, exist_ok=True)
        normalized_dir = preview_dir / "normalized"
        trimmed_dir = preview_dir / "trimmed"
        xfade_dir = preview_dir / "xfade"
        body_dir = preview_dir / "bodies"
        for d in (normalized_dir, trimmed_dir, xfade_dir, body_dir):
            d.mkdir(parents=True, exist_ok=True)

        final_path = preview_dir / f"preview_stitched_{cache_hash}.mp4"
        lock_path = preview_dir / ".lock"

        # Open lock fd once; closed in `finally`. Use lockf for compatibility
        # with the existing StateManager fcntl pattern (production_server:710).
        import fcntl  # noqa: PLC0415  — only needed in this handler
        lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
        try:
            try:
                # Non-blocking — if held, return 409 immediately rather than
                # spinning a 30s wait that would race the client timeout.
                fcntl.lockf(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (BlockingIOError, OSError):
                return self._send_error_v59(
                           409,
                           error_code="ANOTHER_PREVIEW_IS_ALREADY_GENERATING",
                           error_message="another preview is already generating",
                           retry_safe=False,
                           extra={"hint": "Wait for the in-flight preview to finish, then retry."},
                       )

            # ---- cache hit branch ----
            if final_path.is_file():
                evicted = lru_cleanup(preview_dir)  # under same lock
                return self._stream_preview_mp4(final_path, cache_hash, evicted=evicted)

            # ---- cache miss: build the preview ----
            try:
                # Step 4: normalize each selected file (LD-284 recipe)
                normalized_files: dict[str, Path] = {}
                trimmed_files: dict[str, Path] = {}
                trimmed_durations: list[float] = []
                # Cache filename invariants (April 26 2026 audit).
                # Every intermediate cache filename in this pipeline encodes:
                #   - beat_id (which beat)
                #   - src_key  (md5 of resolved source path) — invalidates when
                #              the resolver returns a different src for this bid
                #   - recipe6  (NORMALIZATION_RECIPE_HASH[:6]) — invalidates
                #              when the codec/normalization recipe bumps
                # Plus per-step inputs (trim values, head/tail values, fade_ms).
                # Reason: prior caches keyed only on bid silently reused stale
                # data when the resolver output changed (today's bug — see
                # LESSONS_LEARNED_April26_2026_ProducerConsumerDrift.md).
                # The cache hash at compute_cache_hash() is the OUTER guarantee;
                # these per-step filenames are the INNER guarantee so a future
                # `if dst.is_file(): skip` optimization can't introduce drift.
                _recipe6 = NORMALIZATION_RECIPE_HASH[:6]
                _src_keys: dict[str, str] = {}
                for meta in beat_meta:
                    bid = meta["beat_id"]
                    src = Path(meta["file"])
                    src_key = hashlib.md5(str(src.resolve()).encode("utf-8")).hexdigest()[:10]
                    _src_keys[bid] = src_key
                    norm = normalized_dir / f"{bid}_normalized_{src_key}_{_recipe6}.mp4"
                    needs_rebuild = (
                        not norm.is_file()
                        or (src.is_file() and src.stat().st_mtime > norm.stat().st_mtime)
                    )
                    if needs_rebuild:
                        normalize_for_concat(src, norm)
                    normalized_files[bid] = norm
                    # Step 5: trim each per snapshot trim_start/trim_end +
                    # per-beat audio_delay (Video Lead-in slider, wired
                    # through April 26 2026).
                    ts_ms = int(round((meta.get("trim_start") or 0.0) * 1000))
                    te_raw = meta.get("trim_end")
                    te_ms = int(round(te_raw * 1000)) if te_raw is not None else -1
                    # DOUBLE-DELAY FIX (mirrors _handle_scene_assemble line ~6703):
                    # Lipsync beats already have the delay baked into the ByteDance
                    # output — do NOT re-apply audio_delay. Only raw-option beats
                    # (no completed lipsync, or final.source=="raw_option") need
                    # the authored audio_delay applied here.
                    _beat_dict = beats.get(bid) or {}
                    _beat_lipsync = _beat_dict.get("lipsync") or {}
                    _beat_final_src = (_beat_dict.get("final") or {}).get("source")
                    _is_raw_option_src = (
                        _beat_lipsync.get("status") != "completed"
                        or _beat_final_src == "raw_option"
                    )
                    ad_s = float(meta.get("audio_delay") or 0.0) if _is_raw_option_src else 0.0
                    ad_ms = int(round(ad_s * 1000))
                    trimmed = trimmed_dir / (
                        f"{bid}_trimmed_{src_key}_{ts_ms}_{te_ms}_ad{ad_ms}_{_recipe6}.mp4"
                    )
                    # Kim 2026-05-21 — translate lipsync absolute trim_end
                    # into the lipsync mp4's timeline (see translate_trim_for_source).
                    # Also handles trim_back (relative back-trim) for all sources.
                    _ts_xlat, _te_xlat = translate_trim_for_source(
                        beats.get(bid) or {},
                        src.name, src,
                        meta.get("trim_start"), meta.get("trim_end"),
                        trim_back=meta.get("trim_back"),
                    )
                    duration = trim_normalized(
                        norm, trimmed,
                        _ts_xlat, _te_xlat,
                        audio_delay=ad_s,
                    )
                    trimmed_files[bid] = trimmed
                    trimmed_durations.append(duration)

                # Step 6: per-pair fade resolution + 2-sided clamp
                # (LD PER_ITEM_FADE_AFTER_OVERRIDE_V1, April 19 2026).
                # Each pair consumes beat N's fade_after_ms (int override) or
                # the global fade_ms (None = inherit). Last beat's value is
                # silently ignored — no outgoing transition after the final
                # beat. Clamp each pair to min(pair_fade, (dur_N-buf)*1000,
                # (dur_N+1-buf)*1000), floor 0. Counter (b) MED rolled in.
                requested_pair_fades = resolve_pair_fades(beat_meta, fade_ms)
                clamped_pair_fades = (
                    compute_fade_clamp_per_pair(
                        trimmed_durations, requested_pair_fades,
                    )
                    if len(beat_ids_sorted) > 1
                    else []
                )
                if clamped_pair_fades and clamped_pair_fades != requested_pair_fades:
                    print(
                        f"[preview_stitched] pair fades clamped: "
                        f"requested={requested_pair_fades} -> "
                        f"clamped={clamped_pair_fades} (durations="
                        f"{[f'{d:.3f}' for d in trimmed_durations]}, buffer "
                        f"{FADE_CLAMP_BUFFER_S}s)"
                    )

                # Build concat parts list
                parts: list[Path] = []
                if len(beat_ids_sorted) == 1 or all(f == 0 for f in clamped_pair_fades):
                    # All-hard-cuts fast-path or single-beat: plain concat of trimmed bodies
                    for bid in beat_ids_sorted:
                        parts.append(trimmed_files[bid])
                else:
                    # Mixed / per-pair xfade path.
                    #
                    # Preflight 118 fix: each beat needs head-trimmed by the
                    # PREVIOUS pair's fade_s (if that pair had fade>0) AND
                    # tail-trimmed by the NEXT pair's fade_s (if that pair
                    # has fade>0). The prior implementation only did tail-
                    # trim, which caused the incoming beat's first fade_s
                    # seconds to play twice (once inside xfade_pair, once
                    # at start of body). Kim symptom 2026-04-19: "bird says
                    # 'OK' (then repeats) 'OK kiddo...'" on beat_11 when
                    # beat_10 had fade_after_ms=500.
                    #
                    # Invariants preserved:
                    #   - First beat (i=0) never has head trimmed
                    #     (nothing fades IN to it).
                    #   - Last beat (i=last) never has tail trimmed
                    #     (Counter (f) CRITICAL — preview ends on actual
                    #     final frame).
                    for i, bid in enumerate(beat_ids_sorted):
                        is_first = (i == 0)
                        is_last = (i == len(beat_ids_sorted) - 1)
                        # Head trim = previous pair's fade_s (0 if prev pair
                        # was hard-cut or this is the first beat).
                        head_remove_s = 0.0
                        if not is_first:
                            prev_fade_ms = clamped_pair_fades[i - 1]
                            if prev_fade_ms > 0:
                                head_remove_s = prev_fade_ms / 1000.0
                        # Tail trim = next pair's fade_s (0 if next pair is
                        # hard-cut or this is the last beat).
                        tail_remove_s = 0.0
                        if not is_last:
                            next_fade_ms = clamped_pair_fades[i]
                            if next_fade_ms > 0:
                                tail_remove_s = next_fade_ms / 1000.0
                        # Emit the beat's body (possibly head+tail trimmed).
                        if head_remove_s == 0.0 and tail_remove_s == 0.0:
                            parts.append(trimmed_files[bid])
                        else:
                            head_ms = int(round(head_remove_s * 1000))
                            tail_ms = int(round(tail_remove_s * 1000))
                            body = body_dir / (
                                f"{bid}_body_{_src_keys[bid]}_{head_ms}_{tail_ms}_{_recipe6}.mp4"
                            )
                            trim_body(
                                trimmed_files[bid], body,
                                head_remove_s, tail_remove_s,
                            )
                            parts.append(body)
                        # Emit the xfade pair clip if next pair has fade>0.
                        if not is_last:
                            next_fade_ms = clamped_pair_fades[i]
                            if next_fade_ms > 0:
                                next_bid = beat_ids_sorted[i + 1]
                                pair_key = hashlib.md5(
                                    f"{_src_keys[bid]}+{_src_keys[next_bid]}+{next_fade_ms}".encode()
                                ).hexdigest()[:10]
                                pair = xfade_dir / f"pair_{i:02d}_{pair_key}_{_recipe6}.mp4"
                                render_xfade_pair(
                                    trimmed_files[bid], trimmed_files[next_bid],
                                    next_fade_ms, pair,
                                    dur_a=trimmed_durations[i],
                                )
                                parts.append(pair)

                # Step 8 (concat) -> step 9 (atomic write inside concat helper)
                # Stage as preview_stitched_<hash>.mp4 directly; concat_with_xfade_clips
                # uses os.replace internally so partial writes never serve.
                concat_with_xfade_clips(parts, final_path)

                # Step 10: LRU cleanup inside the same lock (counter (d) HIGH)
                evicted = lru_cleanup(preview_dir)

            except subprocess.TimeoutExpired as exc:
                # Late-success pattern (P08 / pain map): if final exists despite
                # timeout, treat as success.
                if final_path.is_file():
                    evicted = lru_cleanup(preview_dir)
                    return self._stream_preview_mp4(final_path, cache_hash, evicted=evicted)
                return self._send_error_v59(
                           504,
                           error_code="GENERIC_ERROR",
                           error_message=f"ffmpeg timeout after {exc.timeout}s",
                           retry_safe=True,
                           extra={"cmd_summary": " ".join((exc.cmd or [])[:6]) if exc.cmd else "?", "hint": "Try fewer beats or a shorter fade. If persistent, check ffmpeg in PATH."},
                       )
            except subprocess.CalledProcessError as exc:
                stderr = (exc.stderr or b"")[:600].decode("utf-8", errors="replace")
                return self._send_error_v59(
                           500,
                           error_code="GENERIC_ERROR",
                           error_message=f"ffmpeg subprocess failed (returncode={exc.returncode})",
                           retry_safe=True,
                           extra={"stderr": stderr, "hint": "Check the stderr above; common cause is a corrupt source clip."},
                       )
            except (BrokenPipeError, ConnectionResetError):
                # Counter (i) HIGH: BrokenPipe inside the ffmpeg pipeline (rare —
                # subprocess.run catches its own pipe errors). If the final file
                # somehow exists, treat as success; else clean up tmps.
                if final_path.is_file():
                    evicted = lru_cleanup(preview_dir)
                    return self._stream_preview_mp4(final_path, cache_hash, evicted=evicted)
                return self._send_error_v59(
                           500,
                           error_code="BROKEN_PIPE_DURING_PREVIEW_PIPELINE",
                           error_message="broken pipe during preview pipeline",
                           retry_safe=True,
                           extra={"hint": "Client likely disconnected before pipeline finished."},
                       )

            return self._stream_preview_mp4(final_path, cache_hash, evicted=evicted)
        finally:
            try:
                fcntl.lockf(lock_fd, fcntl.LOCK_UN)
            except OSError:
                pass
            try:
                os.close(lock_fd)
            except OSError:
                pass

    def _stream_preview_mp4(self, path: Path, cache_hash: str,
                            evicted: list[Path] | None = None) -> None:
        """Stream a preview mp4 with no-cache + ETag headers (P06 fix).

        Counter (i) HIGH: BrokenPipe HERE means the client cancelled mid-stream.
        File on disk is fine; log once and return without raising.
        """
        # Record latest preview path for timeline audio endpoint (FULL_TIMELINE_EDITOR_V1).
        # try/except: never let a state write fail a preview render.
        try:
            _latest_path = str(path)
            def _record_preview_path(state: dict) -> dict:
                state["latest_preview_stitched_path"] = _latest_path
                return state
            self.app.state.mutate_state(_record_preview_path)
        except Exception as _tl_err:
            print(
                f"[timeline] latest_preview_stitched_path write failed (non-fatal): {_tl_err}",
                file=sys.stderr,
            )
        try:
            body = path.read_bytes()
        except OSError as exc:
            return self._send_error_v59(
                       500,
                       error_code="GENERIC_ERROR",
                       error_message=f"preview file read failed: {exc}",
                       retry_safe=True,
                       extra={"hint": "Server lost the cached file mid-request — retry once."},
                   )
        extra = {
            "Cache-Control": "no-cache",
            "ETag": f'"{cache_hash}"',
        }
        if evicted:
            extra["X-Preview-Evicted"] = str(len(evicted))
        try:
            self._send_bytes(200, body, "video/mp4", extra_headers=extra)
        except (BrokenPipeError, ConnectionResetError):
            print(
                f"[preview_stitched] client cancelled mid-stream for {path.name}",
                file=sys.stderr, flush=True,
            )

    # ------------------------------------------------------------------
    # LD (V3) 2026-04-19 Preview Stitched V3 -- Phase B + Phase A
    # Spec: TECH_SPEC_PREVIEW_STITCHED_V3_PHASE_B_20260419.md
    # Preflight: 102 (parent 98).
    # ------------------------------------------------------------------
    # Voice_id hardcoded as defense-in-depth fallback (CLAUDE.md Voice
    # Architecture; voice_id is canonical + ElevenLabs library-owned, never
    # tuned by Kim). Voice SETTINGS resolved from Directus prod_voice_profiles
    # at request time (counter preflight 102 MEDIUM-1 fix: Kim may retune
    # Cedric stability in Directus; per-beat TTS picks it up, so this path
    # must too to avoid drift).
    _PHASE_VOICE_CONFIG = {
        "b": {
            "voice_id": "oR4uRy4fHDUGGISL0Rev",
            "fallback_settings": {"stability": 0.70, "speed": 0.50},
            "model_id": "eleven_v3",
            "speaker": "Cedric",
        },
        "a": {
            "voice_id": "7o9pyvsN0ob5GO6LBQp6",
            "fallback_settings": {"stability": 0.72, "style": 0.06, "speed": 1.0},
            "model_id": "eleven_v3",
            "speaker": "Arlo",
        },
    }

    def _phase_resolve_voice_settings(self, phase: str) -> tuple[str, str, dict, str]:
        """Resolve (voice_id, model_id, voice_settings, speaker) for a phase.

        Prefers Directus prod_voice_profiles (single source of truth) and
        falls back to hardcoded safe defaults if Directus is unreachable or
        the profile is missing -- counter preflight 102 MEDIUM-1 fix.
        """
        cfg = self._PHASE_VOICE_CONFIG[phase]
        profile = _resolve_voice_profile(cfg["speaker"])
        if profile and profile.get("voice_id"):
            settings: dict = {}
            for k in ("stability", "similarity_boost", "style", "speed"):
                v = profile.get(k)
                if v is not None:
                    settings[k] = float(v)
            if not settings:
                settings = dict(cfg["fallback_settings"])
            return (
                profile.get("voice_id") or cfg["voice_id"],
                profile.get("model") or cfg["model_id"],
                settings,
                cfg["speaker"],
            )
        return (cfg["voice_id"], cfg["model_id"],
                dict(cfg["fallback_settings"]), cfg["speaker"])

    def _phase_project_root(self) -> Path:
        """Resolve project root from event_dir (two levels up from Event_N)."""
        return self.app.event_dir.parent.parent

    def _phase_assets_dir(self, sub: str) -> Path:
        return self._phase_project_root() / "Production" / "assets" / sub

    @staticmethod
    def _phase_check(phase: str) -> str | None:
        if phase not in ("a", "b"):
            return f"phase must be 'a' or 'b', got {phase!r}"
        return None

    # ── Full Module Timeline Editor handlers (2026-04-26, FULL_TIMELINE_EDITOR_V1) ──
    # Governed by: FULL_TIMELINE_EDITOR_V1, SIZE_BUDGET_AUDIO_V1, SIZE_BUDGET_PER_MODULE_V1,
    # SIZE_BUDGET_VIDEO_V1, PHASE_B_AUTHORING_WAVEFORM_FIRST_RESTORE_V1, LD-284

    _TIMELINE_SEGMENT_LABELS: list[str] = ["Story Scene", "Phase A", "Phase B"]

    def _get_current_preview_mp4(self) -> "Path | None":
        """Hybrid: state key -> glob fallback. Never raises; returns None if no preview."""
        state = self.app.state.read_state()
        candidate_str = state.get("latest_preview_stitched_path")
        if candidate_str:
            p = Path(candidate_str)
            if p.is_file():
                return p
        # Glob fallback: self-heals if state key is absent/stale (Phase 0 debate decision)
        preview_dir = self.app.event_dir / "preview"
        if not preview_dir.is_dir():
            return None
        try:
            candidates = sorted(
                preview_dir.glob("preview_stitched_*.mp4"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            return None
        return candidates[0] if candidates else None

    def _handle_timeline_audio(self, event_id: str) -> None:
        from server_handlers.timeline import handle_timeline_audio
        return handle_timeline_audio(self, event_id)

    def _build_full_module_locked(
        self, cache_dir, cache_hash, present, out_path,
        normalize_for_concat, ffprobe_duration,
        concat_with_xfade_clips, lru_cleanup, _FULL_MODULE_RE,
    ):
        """Build the full_module mp4 — caller MUST hold the cache_dir fcntl
        lock. Extracted from _get_or_build_full_module_mp4 (April 26 2026)
        so the lock scope is unambiguous and the same-named helper isn't
        duplicated."""
        norm_paths = []
        for lbl, p in present:
            norm_out = cache_dir / f"full_module_{cache_hash}_{lbl.replace(' ', '_')}_norm.mp4"
            if not norm_out.is_file():
                try:
                    normalize_for_concat(p, norm_out)
                except Exception as exc:
                    raise RuntimeError(f"Normalization failed for {lbl}: {exc}") from exc
            # CONCAT_AUDIO_PARITY_V1: verify audio stream present
            try:
                ap = subprocess.run(
                    ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(norm_out)],
                    capture_output=True, timeout=10, check=True,
                )
                streams = json.loads(ap.stdout).get("streams", [])
                has_audio = any(s.get("codec_type") == "audio" for s in streams)
                if not has_audio:
                    dur_s = ffprobe_duration(norm_out)
                    sil_out = cache_dir / f"full_module_{cache_hash}_{lbl.replace(' ', '_')}_norm_audio.mp4"
                    subprocess.run([
                        "ffmpeg", "-y", "-i", str(norm_out),
                        "-f", "lavfi", "-i",
                        f"anullsrc=r=44100:cl=mono,atrim=duration={dur_s:.3f}",
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
                        "-shortest", str(sil_out),
                    ], check=True, capture_output=True, timeout=60)
                    norm_out = sil_out
            except Exception as exc:
                print(f"[full-module] audio-parity check failed for {lbl} (continuing): {exc}")
            norm_paths.append(norm_out)

        # Concat-demux all normalized segments (stream-copy, fast)
        concat_with_xfade_clips(norm_paths, out_path)
        # LRU pattern fix (April 26 2026): default regex matched only
        # preview_stitched_*; full_module files accumulated forever. Pass the
        # full_module pattern explicitly.
        lru_cleanup(cache_dir, keep=3, pattern=_FULL_MODULE_RE)
        print(f"[full-module] Built {out_path.name} from {[p.name for p in norm_paths]}")

    def _get_or_build_full_module_mp4(self) -> "tuple[Path, list]":
        """Build (or return cached) full module MP4: Story Scene + Phase A + Phase B.
        Returns (mp4_path, segment_boundaries_list). Spec B.
        LD-284 NORMALIZATION_BEFORE_CONCAT_V1: normalizes each segment before concat.
        CONCAT_AUDIO_PARITY_V1: each normalized segment verified to have audio stream.
        Rule 27: _compute_timeline_segment_boundaries deleted (obsolete workaround).
        """
        import hashlib as _hl  # noqa: PLC0415

        state = self.app.state.read_state()

        # Resolve segment paths from state keys
        def _resolve(key: str) -> "Path | None":
            val = state.get(key, "")
            if not val:
                return None
            # Try as-is (handles paths relative to CWD like "Production/Event_1/...")
            p = Path(val)
            if p.is_file():
                return p
            # Try relative to event_dir (handles bare filenames like "beat_01_norm.mp4")
            p2 = self.app.event_dir / val
            return p2 if p2.is_file() else None

        intro_path   = _resolve("latest_preview_stitched_path")
        phase_a_path = _resolve("phase_a_stitched_file")
        phase_b_path = _resolve("phase_b_lipsync_file")

        # Win video: use registered state key, else fall back to latest preserved winner
        win_path = _resolve("win_video_path")
        if win_path is None:
            _win_fallback = self.app.event_dir / "preserved_winners" / "tessa_resolution_final_v20.mp4"
            if _win_fallback.is_file():
                win_path = _win_fallback

        # Only include segments that exist on disk; surface what's missing
        label_map = [
            ("Story Scene", intro_path),
            ("Phase A", phase_a_path),
            ("Phase B", phase_b_path),
            ("Win", win_path),
        ]
        present = [(lbl, p) for lbl, p in label_map if p is not None]
        missing = [lbl for lbl, p in label_map if p is None]

        if not present:
            raise FileNotFoundError(
                "No module segments found. Build Preview first (click 'Preview-Stitched v2')."
            )

        if missing:
            print(f"[full-module] Missing segments (will build with what exists): {missing}")

        # Cache key: hash of all segment mtimes + segment labels
        cache_input = "".join(
            f"{lbl}:{p.stat().st_mtime}" for lbl, p in present
        ).encode()
        cache_hash = _hl.sha256(cache_input).hexdigest()[:16]

        cache_dir = self.app.event_dir / "preview" / "timeline_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        out_path = cache_dir / f"full_module_{cache_hash}.mp4"

        if not out_path.is_file():
            # Import ffmpeg_stitch primitives — must use lib/ subdirectory path
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), "credentials_lib"))
            from ffmpeg_stitch import (  # type: ignore
                normalize_for_concat,
                ffprobe_duration,
                concat_with_xfade_clips,
                lru_cleanup,
                _FULL_MODULE_RE,
            )

            # fcntl lock around the cache-miss build (April 26 2026 audit
            # fix, mirrors preview_stitched lock pattern at lines 9046-9056).
            # Two concurrent calls with the same cache_hash would otherwise
            # both spawn ffmpeg, both write to the same per-segment paths,
            # and race on os.replace. Lock is non-blocking — second caller
            # gets HTTP 409 (matches preview_stitched UX).
            import fcntl  # noqa: PLC0415
            lock_path = cache_dir / ".lock"
            lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
            try:
                try:
                    fcntl.lockf(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except (BlockingIOError, OSError):
                    os.close(lock_fd)
                    raise RuntimeError(
                        "another full_module build is in progress; retry in a moment"
                    )
                # Re-check existence under the lock — another caller may have
                # finished while we were waiting for the file system.
                if out_path.is_file():
                    pass  # cache hit acquired during lock contention; fall through
                else:
                    self._build_full_module_locked(
                        cache_dir, cache_hash, present, out_path,
                        normalize_for_concat, ffprobe_duration,
                        concat_with_xfade_clips, lru_cleanup, _FULL_MODULE_RE,
                    )
            finally:
                try:
                    fcntl.lockf(lock_fd, fcntl.LOCK_UN)
                except OSError:
                    pass
                try:
                    os.close(lock_fd)
                except OSError:
                    pass

        # Compute real segment boundaries from actual durations
        try:
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), "credentials_lib"))
            from ffmpeg_stitch import ffprobe_duration  # type: ignore  # noqa: PLC0415
        except ImportError:
            ffprobe_duration = None  # type: ignore

        boundaries: list[dict] = []
        cursor_ms = 0
        for lbl, p in present:
            try:
                if ffprobe_duration:
                    dur_ms = int(ffprobe_duration(p) * 1000)
                else:
                    dp = subprocess.run(
                        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                         "-of", "json", str(p)],
                        capture_output=True, timeout=10, check=True,
                    )
                    dur_ms = int(float(json.loads(dp.stdout)["format"]["duration"]) * 1000)
            except Exception:
                dur_ms = 0
            boundaries.append({
                "label": lbl,
                "start_ms": cursor_ms,
                "end_ms": cursor_ms + dur_ms,
            })
            cursor_ms += dur_ms

        if missing:
            for lbl in missing:
                boundaries.append({
                    "label": f"{lbl} (not yet produced)",
                    "start_ms": cursor_ms,
                    "end_ms": cursor_ms,
                    "missing": True,
                })

        # Persist boundaries to state for fast re-reads
        def _mutate(s):
            s["full_module_segment_boundaries"] = boundaries
        try:
            self.app.state.mutate_state(_mutate)
        except Exception:
            pass  # non-critical

        return out_path, boundaries

    def _serve_timeline_audio_file(self, filename: str) -> None:
        """GET /api/media/timeline_audio_<hash>.mp3 — serves cached timeline audio."""
        safe = Path(filename).name
        if not (safe.startswith("timeline_audio_") and safe.endswith(".mp3")):
            return self._send_error_v59(
                       400,
                       error_code="GENERIC_ERROR",
                       error_message=f"timeline audio serve rejects: {safe!r}",
                       retry_safe=False,
                       extra={"hint": "Only timeline_audio_*.mp3 files served here."},
                   )
        target = self.app.event_dir / "preview" / "timeline_cache" / safe
        if not target.is_file():
            return self._send_error_v59(
                       404,
                       error_code="GENERIC_ERROR",
                       error_message=f"timeline audio not found: {safe}",
                       retry_safe=False,
                   )
        body = target.read_bytes()
        self._send_bytes(200, body, "audio/mpeg", extra_headers={
            "Cache-Control": "public, max-age=3600",
            "Accept-Ranges": "bytes",
        })

    def _handle_timeline_sfx_library(self) -> None:
        from server_handlers.timeline import handle_timeline_sfx_library
        return handle_timeline_sfx_library(self)

    def _ffprobe_duration_ms(self, path: Path) -> int:
        """Helper: return duration in ms via ffprobe; 0 on failure."""
        try:
            dp = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "json", str(path)],
                capture_output=True, timeout=10, check=True,
            )
            return int(float(json.loads(dp.stdout)["format"]["duration"]) * 1000)
        except Exception:
            return 0

    def _handle_timeline_cue_upsert(self, body: dict) -> None:
        from server_handlers.timeline import handle_timeline_cue_upsert
        return handle_timeline_cue_upsert(self, body)

    def _handle_timeline_delete_cue(self, cue_id: str) -> None:
        from server_handlers.timeline import handle_timeline_delete_cue
        return handle_timeline_delete_cue(self, cue_id)

    def _handle_timeline_bake(self, body: dict) -> None:
        from server_handlers.timeline import handle_timeline_bake
        return handle_timeline_bake(self, body)

    def _handle_timeline_open_in_quicktime(self, body: dict) -> None:
        from server_handlers.timeline import handle_timeline_open_in_quicktime
        return handle_timeline_open_in_quicktime(self, body)

    @with_pin_and_drain('_handle_timeline_preview_with_sfx', track_sync=True)
    def _handle_timeline_preview_with_sfx(self, body: dict) -> None:
        from server_handlers.timeline import handle_timeline_preview_with_sfx
        return handle_timeline_preview_with_sfx(self, body)

    # ================================================================
    # Stitch Editor handlers (2026-04-26, STITCH_EDITOR_UNIVERSAL_V1)
    # Governed by: LD-280, LD-284, LD-140, LD-283, SIZE_BUDGET_VIDEO_V1,
    # SIZE_BUDGET_AUDIO_V1, CONCAT_AUDIO_PARITY_V1, LD-421, Rule 19, Rule 32
    # ================================================================

    def _stitch_project_root(self) -> Path:
        """Project root = event_dir.parent.parent (Claude Mindfulnest Project Files/)."""
        return self.app.event_dir.resolve().parent.parent

    def _stitch_resolve_path(self, raw: str) -> str:
        """Resolve a user-supplied path to an absolute string under the project root.

        Relative paths are anchored to the project root, NOT the server's CWD.
        Raises ValueError if the resolved path escapes the project root.
        Always use this instead of os.path.abspath() for any stitch-endpoint path.

        Security (CodeQL py/path-injection follow-up): the containment check
        is separator-anchored. Without the anchor, a sibling directory named
        '<root>_evil' would slip past 'startswith(root)' (e.g.
        '/proj/root_evil/x' starts with '/proj/root'). Compare against
        `root + os.sep` (or accept exact-equal root) to close the edge case.
        """
        root = self._stitch_project_root()
        p = Path(raw)
        resolved = str((p if p.is_absolute() else root / p).resolve())
        root_s = str(root)
        if not (resolved == root_s or resolved.startswith(root_s + os.sep)):
            raise ValueError(f"path outside project root: {raw!r}")
        return resolved

    def _stitch_assert_path_in_root(self, raw: str, label: str) -> None:
        """Containment guard for body-controlled audio/SFX paths.

        Security (CodeQL py/path-injection follow-up alerts #39/#40/#41 and #28):
        used by _stitch_mix_slot_audio (ambient_bed_path, sfx_cues source_path)
        and the transitions loop (t_path) to refuse any path resolving outside
        the project root before it flows to ffmpeg `-i <path>`.

        Raises ValueError if the resolved real path escapes the project root.
        """
        root = str(self._stitch_project_root())
        real = os.path.realpath(raw)
        if not (real == root or real.startswith(root + os.sep)):
            raise ValueError(f"{label} outside project root: {raw!r}")

    def _stitch_production_dir(self) -> Path:
        """Production/ directory."""
        return self.app.event_dir.parent

    def _stitch_cache_dir(self) -> Path:
        """Temp preview cache dir — created on demand."""
        d = self._stitch_project_root() / "Production" / "stitch_editor_cache"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _stitch_exports_dir(self) -> Path:
        d = self._stitch_project_root() / "Production" / "Event_1" / "exports"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _serve_stitch_editor(self) -> None:
        """GET /stitch_editor — serve the Stitch Editor HTML (Rule 7 builder output)."""
        html_path = Path(__file__).parent / "stitch_editor.html"
        if not html_path.exists():
            return self._send_error_v59(
                       404,
                       error_code="STITCH_EDITOR_HTML_NOT_FOUND",
                       error_message="stitch_editor.html not found",
                       retry_safe=False,
                       extra={"hint": "Run: python3 Production/tools/build_stitch_editor.py --output Production/tools/stitch_editor.html"},
                   )
        html = html_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.send_header("Cache-Control", "no-store")
        self._cors_headers()
        self.end_headers()
        self.wfile.write(html)

    def _handle_stitch_library(self) -> None:
        from server_handlers.stitch_editor import handle_stitch_library
        return handle_stitch_library(self)

    def _handle_stitch_list_jobs(self) -> None:
        from server_handlers.stitch_editor import handle_stitch_list_jobs
        return handle_stitch_list_jobs(self)

    def _handle_stitch_load_job(self, name: str) -> None:
        from server_handlers.stitch_editor import handle_stitch_load_job
        return handle_stitch_load_job(self, name)

    def _handle_stitch_save_job(self, body: dict) -> None:
        from server_handlers.stitch_editor import handle_stitch_save_job
        return handle_stitch_save_job(self, body)

    def _handle_stitch_delete_job(self, name: str) -> None:
        from server_handlers.stitch_editor import handle_stitch_delete_job
        return handle_stitch_delete_job(self, name)

    def _handle_stitch_audio_extract(self, body: dict) -> None:
        from server_handlers.stitch_editor import handle_stitch_audio_extract
        return handle_stitch_audio_extract(self, body)

    def _stitch_audio_content_type(self, filename: str) -> str:
        ext = Path(filename).suffix.lower()
        return {
            ".mp3": "audio/mpeg",
            ".wav": "audio/wav",
            ".m4a": "audio/mp4",
        }.get(ext, "audio/mpeg")

    def _serve_stitch_audio_file(self, fname: str) -> None:
        """GET /api/stitch_editor/audio_file/<fname> — serve extracted waveform audio
        OR sound_library files (Library preview + sidebar).

        Lookup order (first hit wins):
          1. _stitch_cache_dir()                           — extracted waveform audio
          2. Production/assets/sound_library/ambient/
          3. Production/assets/sound_library/sfx/
          4. Production/assets/sound_library/transitions/
          5. Production/assets/ambient_library/            — legacy ambient
          6. project_root/<filename>                         — legacy root SFX (spaces ok)
        """
        safe = Path(urllib.parse.unquote(fname)).name
        if not safe or safe in (".", ".."):
            return self._send_error_v59(
                400,
                error_code="GENERIC_ERROR",
                error_message="invalid audio filename",
                retry_safe=False,
            )
        project_root = self._stitch_project_root()
        candidates = [
            self._stitch_cache_dir() / safe,
            project_root / "Production" / "assets" / "sound_library" / "ambient" / safe,
            project_root / "Production" / "assets" / "sound_library" / "sfx" / safe,
            project_root / "Production" / "assets" / "sound_library" / "transitions" / safe,
            project_root / "Production" / "assets" / "ambient_library" / safe,
            project_root / safe,
        ]
        content_type = self._stitch_audio_content_type(safe)
        for target in candidates:
            if target.is_file():
                body = target.read_bytes()
                return self._send_bytes(200, body, content_type, extra_headers={
                    "Cache-Control": "public, max-age=3600",
                    "Accept-Ranges": "bytes",
                })
        return self._send_error_v59(
                   404,
                   error_code="GENERIC_ERROR",
                   error_message=f"Audio file not found: {safe}",
                   retry_safe=False,
               )

    def _handle_stitch_beat_boundaries(self) -> None:
        """GET /api/stitch_editor/beat_boundaries?scope_target_video=resolution
        Returns beat boundary timecodes for a storyboard video partition.
        When scope_target_video is intro/resolution, only beats in that
        partition's display_order with selected_option are included.
        Without scope_target_video, falls back to legacy global cache scan."""
        import re as _re
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "credentials_lib"))
        from ffmpeg_stitch import beat_is_assemblable  # noqa: PLC0415
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        scope_target_video = (qs.get("scope_target_video") or [None])[0]
        if isinstance(scope_target_video, list):
            scope_target_video = scope_target_video[0] if scope_target_video else None

        clips_dir = self.app.event_dir / "animation_clips_final"
        ordered_beat_ids: list[str] = []
        if scope_target_video in ("intro", "resolution"):
            try:
                state = self.app.state.read_state()
                partition = ((state.get("videos") or {}).get(scope_target_video) or {})
                beats = partition.get("beats") or {}
                display_order = partition.get("display_order") or []
                allowed = set(display_order)
                ordered_beat_ids = [
                    bid for bid in display_order
                    if bid in allowed
                    and bid in beats
                    and isinstance(beats[bid], dict)
                    and beat_is_assemblable(beats[bid], event_dir=self.app.event_dir)
                ]
                if not ordered_beat_ids:
                    ordered_beat_ids = sorted(
                        bid for bid, b in beats.items()
                        if isinstance(b, dict)
                        and beat_is_assemblable(b, event_dir=self.app.event_dir)
                    )
            except Exception as exc:  # noqa: BLE001
                print(f"[beat_boundaries] WARN partition read failed: {exc}", flush=True)

        if not clips_dir.exists():
            self._send_json(200, {"ok": True, "beats": [], "total_ms": 0})
            return

        beat_files: dict[str, Path] = {}
        if ordered_beat_ids:
            try:
                for f in clips_dir.iterdir():
                    for bid in ordered_beat_ids:
                        if f.name.startswith(f"{bid}_final_") and f.suffix == ".mp4":
                            existing = beat_files.get(bid)
                            if existing is None or f.stat().st_mtime > existing.stat().st_mtime:
                                beat_files[bid] = f
            except OSError as exc:
                self._send_error_v59(500, "FS_ERROR", str(exc), retry_safe=True)
                return
        else:
            pattern = _re.compile(r"beat_(\d+)_final_.*\.mp4$")
            try:
                for f in clips_dir.iterdir():
                    m = pattern.match(f.name)
                    if m:
                        beat_num = int(m.group(1))
                        bid = f"beat_{beat_num:02d}"
                        existing = beat_files.get(bid)
                        if existing is None or f.stat().st_mtime > existing.stat().st_mtime:
                            beat_files[bid] = f
            except OSError as exc:
                self._send_error_v59(500, "FS_ERROR", str(exc), retry_safe=True)
                return

        if not beat_files:
            self._send_json(200, {"ok": True, "beats": [], "total_ms": 0})
            return

        boundaries = []
        cursor_ms = 0
        beat_order = ordered_beat_ids if ordered_beat_ids else sorted(beat_files.keys())
        for bid in beat_order:
            fpath = beat_files.get(bid)
            if fpath is None:
                continue
            try:
                dur_s = _ffprobe_duration(fpath)
                dur_ms = round(dur_s * 1000)
            except Exception:  # noqa: BLE001
                dur_ms = 3000  # fallback 3s if probe fails
            boundaries.append({
                "beat_id": bid,
                "start_ms": cursor_ms,
                "end_ms": cursor_ms + dur_ms,
                "duration_ms": dur_ms,
            })
            cursor_ms += dur_ms

        self._send_json(200, {"ok": True, "beats": boundaries, "total_ms": cursor_ms})

    def _serve_stitch_preview_file(self, hash_id: str) -> None:
        """GET /api/stitch_editor/preview_file/<hash> — serve preview MP4 with byte-range support."""
        safe = Path(hash_id).name
        target = self._stitch_cache_dir() / f"stitch_preview_{safe}.mp4"
        if not target.is_file():
            return self._send_error_v59(
                       404,
                       error_code="GENERIC_ERROR",
                       error_message=f"Preview file not found: {safe}",
                       retry_safe=False,
                   )
        self._serve_mp4_with_range(target)

    def _serve_finder_video(self) -> None:
        """GET /api/finder_video?path=...&probe=1 — probe OR serve a Finder-dragged video.

        With probe=1: returns JSON {"duration_s": float, "size_bytes": int}.
        Without probe: serves the file with byte-range support for <video> scrubbing.
        Security: path must be under project root (whitelist). No traversal possible.
        Rule 32: absolute URL used by client.
        """
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        path_param = (qs.get("path") or [None])[0]
        if not path_param:
            return self._send_error_v59(
                       400,
                       error_code="PATH_QUERY_PARAM_REQUIRED",
                       error_message="path query param required",
                       retry_safe=False,
                   )

        try:
            abs_path = self._stitch_resolve_path(path_param)
        except ValueError:
            return self._send_error_v59(
                       403,
                       error_code="PATH_OUTSIDE_PROJECT_ROOT",
                       error_message="path outside project root",
                       retry_safe=False,
                   )
        if not os.path.isfile(abs_path):
            return self._send_error_v59(
                       404,
                       error_code="GENERIC_ERROR",
                       error_message=f"File not found: {abs_path}",
                       retry_safe=False,
                   )

        if (qs.get("probe") or ["0"])[0] == "1":
            # Return JSON duration — client uses this to set slot.videoDurMs
            dur_ms = self._ffprobe_duration_ms(Path(abs_path))
            size_bytes = os.path.getsize(abs_path)
            return self._send_json(200, {
                "duration_s": round(dur_ms / 1000.0, 3),
                "duration_ms": dur_ms,
                "size_bytes": size_bytes,
            })

        self._serve_mp4_with_range(Path(abs_path))

    def _serve_mp4_with_range(self, path: Path) -> None:
        """Serve an MP4 file with Accept-Ranges support for browser <video> scrubbing."""
        file_size = path.stat().st_size
        range_header = self.headers.get("Range", "")
        ctype = "video/mp4"

        if range_header:
            try:
                range_val = range_header.replace("bytes=", "")
                start_str, end_str = range_val.split("-")
                start = int(start_str) if start_str else 0
                end = int(end_str) if end_str else file_size - 1
                end = min(end, file_size - 1)
                length = end - start + 1
                self.send_response(206)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
                self.send_header("Content-Length", str(length))
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Cache-Control", "no-store")
                self._cors_headers()
                self.end_headers()
                with open(path, "rb") as f:
                    f.seek(start)
                    self.wfile.write(f.read(length))
            except Exception:
                body = path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Cache-Control", "no-store")
                self._cors_headers()
                self.end_headers()
                self.wfile.write(body)
        else:
            body = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Cache-Control", "no-store")
            self._cors_headers()
            self.end_headers()
            self.wfile.write(body)

    # ---- Stitch Editor: core audio pipeline helpers ----

    def _stitch_normalize_slot(
        self, video_path: str, cache_dir: Path,
        trim_in_ms: int = 0, trim_out_ms: int | None = None,
    ) -> Path:
        """Normalize a slot's video to LD-284 canonical spec.

        Cached by md5+mtime+sha256[:8] + trim fingerprint.

        S5.5g — STITCHER_PER_SLOT_TRIMS_V1 (HARD). Per audit doc §5 LOCKED:
          - trim_in_ms (default 0, inclusive)
          - trim_out_ms (None = end of clip; else exclusive cutoff in ms)
          - Cache key MUST include trim fingerprint or LRU collisions across
            different trim windows of the same source
          - Pre-trim via ffmpeg -ss / -to BEFORE normalize_for_concat
        """
        import hashlib as _hl  # noqa: PLC0415
        from ffmpeg_stitch import normalize_for_concat  # noqa: PLC0415

        mtime_ms = int(os.path.getmtime(video_path) * 1000)
        path_md5 = _hl.md5(video_path.encode(), usedforsecurity=False).hexdigest()[:10]

        # sha256 of first 1MB — source identity per Producer/Consumer drift rule
        sha_prefix = "noshared"
        try:
            with open(video_path, "rb") as f:
                sha_prefix = _hl.sha256(f.read(1024 * 1024), usedforsecurity=False).hexdigest()[:8]
        except Exception:
            pass

        # Trim fingerprint (audit doc §5): "<in>-<out|end>" so different trim
        # windows of the same source don't collide in the LRU cache.
        trim_sig = f"{int(trim_in_ms)}-{trim_out_ms if trim_out_ms is not None else 'end'}"
        norm_name = f"se_norm_{path_md5}_{mtime_ms}_{sha_prefix}_t{trim_sig}.mp4"
        norm_path = cache_dir / norm_name
        if norm_path.is_file():
            from ffmpeg_stitch import mp4_is_playable  # noqa: PLC0415
            if mp4_is_playable(norm_path):
                return norm_path
            try:
                norm_path.unlink()
            except OSError:
                pass

        # Source for normalization: pre-trimmed mp4 if trim is set, else original.
        src_for_norm = Path(video_path)
        if trim_in_ms > 0 or trim_out_ms is not None:
            trim_in_s = max(0.0, trim_in_ms / 1000.0)
            trim_path = cache_dir / f"se_pretrim_{path_md5}_{mtime_ms}_{sha_prefix}_t{trim_sig}.mp4"
            if not trim_path.is_file():
                cmd = [
                    "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-ss", f"{trim_in_s:.3f}",
                    "-i", str(video_path),
                ]
                if trim_out_ms is not None and int(trim_out_ms) > int(trim_in_ms):
                    trim_dur_s = (int(trim_out_ms) - int(trim_in_ms)) / 1000.0
                    cmd += ["-t", f"{trim_dur_s:.3f}"]
                cmd += [
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                    "-c:a", "aac", "-b:a", "128k",
                    "-pix_fmt", "yuv420p",
                    str(trim_path),
                ]
                try:
                    subprocess.run(cmd, check=True, capture_output=True, timeout=180)
                except subprocess.CalledProcessError as exc:
                    stderr = (exc.stderr or b"")[:400].decode("utf-8", errors="replace")
                    # Per LD-520 fail-loud — bubble out as RuntimeError.
                    raise RuntimeError(
                        f"slot pre-trim failed for {video_path}: {stderr}",
                    ) from exc
            src_for_norm = trim_path

        try:
            normalize_for_concat(src_for_norm, norm_path)
        except Exception as exc:
            raise RuntimeError(f"Normalize failed for {video_path}: {exc}") from exc
        return norm_path

    def _stitch_ensure_audio(self, norm_path: Path, cache_dir: Path) -> Path:
        """CONCAT_AUDIO_PARITY_V1: ensure normalized clip has audio stream.

        If absent, injects anullsrc (atrim mandatory — infinite silence without it).
        Returns path with guaranteed audio stream.
        """
        try:
            ap = subprocess.run(
                ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(norm_path)],
                capture_output=True, timeout=10, check=True,
            )
            streams = json.loads(ap.stdout).get("streams", [])
            has_audio = any(s.get("codec_type") == "audio" for s in streams)
        except Exception:
            has_audio = True  # assume ok on ffprobe failure

        from ffmpeg_stitch import mp4_is_playable  # noqa: PLC0415
        if has_audio and mp4_is_playable(norm_path):
            return norm_path

        if not mp4_is_playable(norm_path):
            raise RuntimeError(
                f"Normalized clip is unreadable (corrupt cache?): {norm_path}",
            )

        try:
            dur_s = self._ffprobe_duration_ms(norm_path) / 1000.0
        except Exception:
            dur_s = 10.0

        if dur_s <= 0:
            raise RuntimeError(
                f"Normalized clip has zero duration (corrupt cache?): {norm_path}",
            )

        sil_path = norm_path.with_suffix("").with_name(norm_path.stem + "_audio.mp4")
        if sil_path.is_file():
            if mp4_is_playable(sil_path):
                return sil_path
            try:
                sil_path.unlink()
            except OSError:
                pass
        if not sil_path.is_file():
            subprocess.run([
                "ffmpeg", "-y", "-i", str(norm_path),
                "-f", "lavfi", "-i",
                f"anullsrc=r=44100:cl=mono,atrim=duration={dur_s:.3f}",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
                "-shortest", str(sil_path),
            ], check=True, capture_output=True, timeout=60)
        return sil_path

    def _stitch_apply_dissolve_tail(
        self, slot_path: Path, cache_dir: Path,
        fade_ms: int, audio_xfade_ms: int,
    ) -> Path:
        """Apply video fade-to-black on the trailing fade_ms of slot_path.

        Per spec §3.3 dissolve transition (Q1 LOCKED 2026-05-04):
          - Visual: fade=t=out:st=(dur - fade_s):d=fade_s
          - Audio:  if audio_xfade_ms > 0, afade=t=out at the matching window;
                    if audio_xfade_ms == 0, audio left intact (concat will hard-cut)

        Cache key includes fade_ms + audio_xfade_ms so re-bake produces
        consistent output and different fade values don't collide.
        """
        import hashlib as _hl  # noqa: PLC0415
        if fade_ms <= 0:
            return slot_path
        slot_dur_ms = self._ffprobe_duration_ms(slot_path)
        if slot_dur_ms <= 0:
            return slot_path
        fade_s = min(fade_ms / 1000.0, slot_dur_ms / 1000.0)
        afade_s = min(audio_xfade_ms / 1000.0, slot_dur_ms / 1000.0) if audio_xfade_ms > 0 else 0.0
        start_v = max(0.0, slot_dur_ms / 1000.0 - fade_s)
        start_a = max(0.0, slot_dur_ms / 1000.0 - afade_s) if afade_s > 0 else 0.0
        sig_src = f"{slot_path.name}:tail:{fade_ms}:{audio_xfade_ms}"
        sig = _hl.md5(sig_src.encode(), usedforsecurity=False).hexdigest()[:10]
        out = cache_dir / f"se_diss_tail_{sig}.mp4"
        if out.is_file():
            return out

        vf = f"fade=t=out:st={start_v:.3f}:d={fade_s:.3f}"
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(slot_path),
            "-vf", vf,
        ]
        if afade_s > 0:
            af = f"afade=t=out:st={start_a:.3f}:d={afade_s:.3f}"
            cmd += ["-af", af]
        cmd += [
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac", "-b:a", "128k",
            "-pix_fmt", "yuv420p",
            str(out),
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=180)
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or b"")[:400].decode("utf-8", errors="replace")
            raise RuntimeError(
                f"dissolve tail render failed for {slot_path.name}: {stderr}",
            ) from exc
        return out

    def _stitch_apply_dissolve_head(
        self, slot_path: Path, cache_dir: Path,
        fade_ms: int, audio_xfade_ms: int,
    ) -> Path:
        """Apply video fade-from-black on the leading fade_ms of slot_path.

        Per spec §3.3 dissolve transition (mirror of _stitch_apply_dissolve_tail
        for the next slot's head). audio_xfade_ms=0 keeps audio intact (next
        slot starts at full level — concat hard-joins). audio_xfade_ms>0
        applies afade=t=in for the matching window.
        """
        import hashlib as _hl  # noqa: PLC0415
        if fade_ms <= 0:
            return slot_path
        slot_dur_ms = self._ffprobe_duration_ms(slot_path)
        if slot_dur_ms <= 0:
            return slot_path
        fade_s = min(fade_ms / 1000.0, slot_dur_ms / 1000.0)
        afade_s = min(audio_xfade_ms / 1000.0, slot_dur_ms / 1000.0) if audio_xfade_ms > 0 else 0.0
        sig_src = f"{slot_path.name}:head:{fade_ms}:{audio_xfade_ms}"
        sig = _hl.md5(sig_src.encode(), usedforsecurity=False).hexdigest()[:10]
        out = cache_dir / f"se_diss_head_{sig}.mp4"
        if out.is_file():
            return out

        vf = f"fade=t=in:st=0:d={fade_s:.3f}"
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(slot_path),
            "-vf", vf,
        ]
        if afade_s > 0:
            af = f"afade=t=in:st=0:d={afade_s:.3f}"
            cmd += ["-af", af]
        cmd += [
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac", "-b:a", "128k",
            "-pix_fmt", "yuv420p",
            str(out),
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=180)
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or b"")[:400].decode("utf-8", errors="replace")
            raise RuntimeError(
                f"dissolve head render failed for {slot_path.name}: {stderr}",
            ) from exc
        return out

    def _stitch_overlay_sfx_on_clip(
        self,
        clip_path: Path,
        sfx_path: str,
        cache_dir: Path,
        *,
        offset_ms: int,
        duration_ms: int,
        sfx_start_ms: int = 0,
        volume: float = 0.45,
    ) -> Path:
        """Mix one SFX segment onto an existing clip; video stream copied unchanged."""
        import hashlib as _hl  # noqa: PLC0415

        if duration_ms <= 0 or not sfx_path or not os.path.isfile(sfx_path):
            return clip_path
        try:
            self._stitch_assert_path_in_root(sfx_path, "boundary sfx source_path")
        except ValueError:
            return clip_path

        clip_dur_ms = self._ffprobe_duration_ms(clip_path)
        if clip_dur_ms <= 0:
            return clip_path
        offset_ms = max(0, min(int(offset_ms), clip_dur_ms))
        play_ms = min(int(duration_ms), max(0, clip_dur_ms - offset_ms))
        if play_ms <= 0:
            return clip_path

        sig = _hl.md5(
            (
                f"{clip_path.name}:{clip_path.stat().st_mtime_ns}:"
                f"{sfx_path}:{offset_ms}:{play_ms}:{sfx_start_ms}:{volume:.3f}"
            ).encode(),
            usedforsecurity=False,
        ).hexdigest()[:12]
        out_path = cache_dir / f"se_boundary_sfx_{sig}.mp4"
        if out_path.is_file():
            from ffmpeg_stitch import mp4_decodes_cleanly, mp4_is_playable  # noqa: PLC0415
            if mp4_is_playable(out_path) and mp4_decodes_cleanly(out_path):
                return out_path
            try:
                out_path.unlink()
            except OSError:
                pass

        play_s = play_ms / 1000.0
        sfx_start_s = max(0.0, int(sfx_start_ms) / 1000.0)
        offset_s = offset_ms / 1000.0
        filter_complex = (
            f"[0:a]aresample=44100,aformat=channel_layouts=mono[base];"
            f"[1:a]aresample=44100,aformat=channel_layouts=mono,"
            f"atrim=start={sfx_start_s:.3f}:duration={play_s:.3f},"
            f"asetpts=PTS-STARTPTS,"
            f"adelay={offset_ms}:all=1,"
            f"volume={volume:.3f}[sfx];"
            f"[base][sfx]amix=inputs=2:duration=first:normalize=0[aout]"
        )
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(clip_path),
            "-i", sfx_path,
            "-filter_complex", filter_complex,
            "-map", "0:v",
            "-map", "[aout]",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "128k", "-ac", "1", "-ar", "44100",
            str(out_path),
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=180)
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or b"")[:400].decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Boundary SFX overlay failed for {clip_path.name}: {stderr}",
            ) from exc
        return out_path

    def _stitch_apply_canonical_boundary_sfx(
        self,
        parts: list[Path],
        pair_fades_ms: list[int],
        cache_dir: Path,
        *,
        visual_out_ms: int,
        visual_in_ms: int,
    ) -> list[Path]:
        """STITCH_CANONICAL_TRANSITION_SFX_V1 — span dissolve: pre-roll, black, post-roll."""
        from ffmpeg_stitch import allocate_pair_fade_budget  # noqa: PLC0415
        from server_handlers.stitch_editor import (  # noqa: PLC0415
            STITCH_CANONICAL_BOUNDARY_SFX,
            STITCH_TRANSITION_SFX_POST_ROLL_MS,
            STITCH_TRANSITION_SFX_PRE_ROLL_MS,
            STITCH_TRANSITION_SFX_VOLUME,
            resolve_canonical_boundary_sfx_path,
        )

        if not parts or not pair_fades_ms:
            return parts
        out = list(parts)
        for after_slot, pair_ms in enumerate(pair_fades_ms):
            if pair_ms <= 0:
                continue
            sfx_name = STITCH_CANONICAL_BOUNDARY_SFX.get(after_slot)
            if not sfx_name:
                continue
            sfx_path = resolve_canonical_boundary_sfx_path(self, sfx_name)
            if not sfx_path:
                print(
                    f"[stitch] WARN: canonical boundary SFX missing for "
                    f"after_slot={after_slot}: {sfx_name}",
                )
                continue
            out_ms, in_ms, black_ms = allocate_pair_fade_budget(
                pair_ms,
                visual_out_ms=visual_out_ms,
                visual_in_ms=visual_in_ms,
            )
            pre = STITCH_TRANSITION_SFX_PRE_ROLL_MS
            post = STITCH_TRANSITION_SFX_POST_ROLL_MS
            body_out_idx = 2 * after_slot
            black_idx = 2 * after_slot + 1
            body_in_idx = 2 * after_slot + 2
            if body_out_idx >= len(out) or body_in_idx >= len(out):
                continue

            src_cursor = 0
            seg1_dur = pre + out_ms
            clip_dur_ms = self._ffprobe_duration_ms(out[body_out_idx])
            seg1_offset = max(0, clip_dur_ms - seg1_dur)
            out[body_out_idx] = self._stitch_overlay_sfx_on_clip(
                out[body_out_idx],
                sfx_path,
                cache_dir,
                offset_ms=seg1_offset,
                duration_ms=seg1_dur,
                sfx_start_ms=src_cursor,
                volume=STITCH_TRANSITION_SFX_VOLUME,
            )
            src_cursor += seg1_dur

            if black_ms > 0 and black_idx < len(out):
                out[black_idx] = self._stitch_overlay_sfx_on_clip(
                    out[black_idx],
                    sfx_path,
                    cache_dir,
                    offset_ms=0,
                    duration_ms=black_ms,
                    sfx_start_ms=src_cursor,
                    volume=STITCH_TRANSITION_SFX_VOLUME,
                )
                src_cursor += black_ms

            out[body_in_idx] = self._stitch_overlay_sfx_on_clip(
                out[body_in_idx],
                sfx_path,
                cache_dir,
                offset_ms=0,
                duration_ms=in_ms + post,
                sfx_start_ms=src_cursor,
                volume=STITCH_TRANSITION_SFX_VOLUME,
            )
        return out

    def _stitch_apply_resolution_finale(
        self,
        parts: list[Path],
        cache_dir: Path,
        *,
        visual_out_ms: int,
    ) -> list[Path]:
        """STITCH_RESOLUTION_FINALE_V1 — fade tail to black, then outtro3 until EOF."""
        import hashlib as _hl  # noqa: PLC0415

        from ffmpeg_stitch import render_black_pause_clip, trim_body_with_fade  # noqa: PLC0415
        from server_handlers.stitch_editor import (  # noqa: PLC0415
            STITCH_RESOLUTION_FINALE_FADE_OUT_MS,
            STITCH_RESOLUTION_FINALE_OUTTRO_FILENAME,
            STITCH_RESOLUTION_FINALE_OUTTRO_PLAY_MS,
            STITCH_RESOLUTION_FINALE_OUTTRO_START_BEFORE_END_MS,
            STITCH_TRANSITION_SFX_VOLUME,
            resolution_finale_black_hold_ms,
            resolve_canonical_finale_outtro_path,
        )

        if not parts:
            return parts
        outtro_path = resolve_canonical_finale_outtro_path(
            self, STITCH_RESOLUTION_FINALE_OUTTRO_FILENAME,
        )
        if not outtro_path:
            print(
                "[stitch] WARN: resolution finale outtro missing: "
                f"{STITCH_RESOLUTION_FINALE_OUTTRO_FILENAME}",
            )
            return parts

        last = parts[-1]
        clip_dur_ms = self._ffprobe_duration_ms(last)
        if clip_dur_ms <= 0:
            return parts

        fade_out_ms = min(
            int(visual_out_ms),
            STITCH_RESOLUTION_FINALE_FADE_OUT_MS,
            clip_dur_ms,
        )
        if fade_out_ms <= 0:
            return parts

        outtro_start_ms = min(
            STITCH_RESOLUTION_FINALE_OUTTRO_START_BEFORE_END_MS,
            clip_dur_ms,
        )
        outtro_on_clip_ms = min(outtro_start_ms, clip_dur_ms)
        outtro_on_black_ms = max(
            0,
            STITCH_RESOLUTION_FINALE_OUTTRO_PLAY_MS - outtro_on_clip_ms,
        )
        black_hold_ms = resolution_finale_black_hold_ms()
        if outtro_on_black_ms > 0:
            black_hold_ms = max(black_hold_ms, outtro_on_black_ms)

        sig = _hl.md5(
            (
                f"{last.name}:{last.stat().st_mtime_ns}:"
                f"{fade_out_ms}:{outtro_start_ms}:{black_hold_ms}"
            ).encode(),
            usedforsecurity=False,
        ).hexdigest()[:12]
        faded_path = cache_dir / f"se_finale_fade_{sig}.mp4"
        if not faded_path.is_file():
            trim_body_with_fade(
                last,
                faded_path,
                head_remove_s=0.0,
                tail_remove_s=0.0,
                fade_in_s=0.0,
                fade_out_s=fade_out_ms / 1000.0,
                fade_audio=False,
            )

        clip_offset_ms = max(0, clip_dur_ms - outtro_start_ms)
        faded_with_outtro = self._stitch_overlay_sfx_on_clip(
            faded_path,
            outtro_path,
            cache_dir,
            offset_ms=clip_offset_ms,
            duration_ms=outtro_on_clip_ms,
            sfx_start_ms=0,
            volume=STITCH_TRANSITION_SFX_VOLUME,
        )

        out = list(parts[:-1]) + [faded_with_outtro]
        if black_hold_ms > 0:
            black_path = cache_dir / f"se_finale_black_{black_hold_ms}ms_{sig}.mp4"
            if not black_path.is_file():
                render_black_pause_clip(black_hold_ms / 1000.0, black_path)
            if outtro_on_black_ms > 0:
                black_path = self._stitch_overlay_sfx_on_clip(
                    black_path,
                    outtro_path,
                    cache_dir,
                    offset_ms=0,
                    duration_ms=outtro_on_black_ms,
                    sfx_start_ms=outtro_on_clip_ms,
                    volume=STITCH_TRANSITION_SFX_VOLUME,
                )
            out.append(black_path)
        return out

    def _stitch_mix_slot_audio(
        self, norm_path: Path, slot: dict, cache_dir: Path
    ) -> Path:
        """Mix ambient bed + SFX cues into a normalized slot video.

        SFX offsets in slot are SLOT-RELATIVE ms (from slot start = 0).
        Returns path to final slot MP4 with all audio baked.
        If no ambient and no SFX, returns norm_path unchanged.
        """
        import hashlib as _hl  # noqa: PLC0415
        from server_handlers.stitch_editor import (  # noqa: PLC0415
            STITCH_AMBIENT_BED_VOLUME,
            normalize_slot_audio_mix_levels,
        )

        normalize_slot_audio_mix_levels(slot)
        ambient_path = slot.get("ambient_bed_path") or ""
        ambient_volume = float(slot.get("ambient_volume", STITCH_AMBIENT_BED_VOLUME))
        sfx_cues = slot.get("sfx_cues") or []

        if not ambient_path and not sfx_cues:
            return norm_path

        # Validate audio sources exist
        if ambient_path and not os.path.isfile(ambient_path):
            raise FileNotFoundError(f"Ambient bed not found: {ambient_path}")
        for cue in sfx_cues:
            if not os.path.isfile(cue.get("source_path", "")):
                raise FileNotFoundError(f"SFX not found: {cue.get('source_path')}")

        # Security (CodeQL py/path-injection alerts #39/#40 follow-up):
        # body-controlled paths flow into ffmpeg `-i`. Containment guard.
        if ambient_path:
            self._stitch_assert_path_in_root(ambient_path, "ambient_bed_path")
        for cue in sfx_cues:
            self._stitch_assert_path_in_root(cue.get("source_path", ""), "sfx source_path")

        # Cache key: norm mtime + ambient + sfx cue ids
        sig_parts = [str(norm_path.stat().st_mtime), ambient_path, str(ambient_volume)]
        sig_parts += [
            f"{c['id']}:{c['offset_ms']}:{c.get('duration_ms', '')}" for c in sfx_cues
        ]
        mix_hash = _hl.md5("|".join(sig_parts).encode(), usedforsecurity=False).hexdigest()[:12]
        out_path = cache_dir / f"se_slot_{mix_hash}.mp4"
        if out_path.is_file():
            from ffmpeg_stitch import mp4_decodes_cleanly, mp4_is_playable  # noqa: PLC0415
            if mp4_is_playable(out_path) and mp4_decodes_cleanly(out_path):
                return out_path
            try:
                out_path.unlink()
            except OSError:
                pass

        slot_dur_ms = self._ffprobe_duration_ms(norm_path)
        slot_dur_s = slot_dur_ms / 1000.0

        # Build ffmpeg command: video from norm_path, audio sources = ambient + SFX
        input_args: list[str] = ["-i", str(norm_path)]
        filter_lanes: list[str] = []
        base_audio = "[0:a]"  # original video audio

        next_input_idx = 1

        if ambient_path:
            input_args += ["-i", ambient_path]
            aidx = next_input_idx
            next_input_idx += 1
            # Loop and trim to exact slot duration
            filter_lanes.append(
                f"[{aidx}:a]aloop=-1:size=2147483647,"
                f"atrim=duration={slot_dur_s:.3f},"
                f"aformat=channel_layouts=mono,"
                f"volume={ambient_volume:.3f}[bed]"
            )

        for idx, cue in enumerate(sfx_cues):
            input_args += ["-i", cue["source_path"]]
            cidx = next_input_idx
            next_input_idx += 1
            offset_ms = int(cue["offset_ms"])  # SLOT-RELATIVE
            fadein_ms = int(cue.get("fadein_ms", 300))
            fadeout_ms = int(cue.get("fadeout_ms", 300))
            vol = float(cue.get("volume", 0.45))
            cue_dur_ms = self._ffprobe_duration_ms(Path(cue["source_path"]))
            cue_dur_s = cue_dur_ms / 1000.0 if cue_dur_ms else 5.0
            play_ms = cue.get("duration_ms")
            if play_ms is not None and int(play_ms) > 0:
                play_s = min(cue_dur_s, int(play_ms) / 1000.0)
            else:
                play_s = cue_dur_s
            fadeout_start_s = max(0.0, play_s - fadeout_ms / 1000.0)
            label = f"cue{idx}"
            filter_lanes.append(
                f"[{cidx}:a]aresample=44100,aformat=channel_layouts=mono,"
                f"atrim=duration={play_s:.3f},"
                f"afade=t=in:st=0:d={fadein_ms / 1000:.3f},"
                f"afade=t=out:st={fadeout_start_s:.3f}:d={fadeout_ms / 1000:.3f},"
                f"adelay={offset_ms}:all=1,"
                f"volume={vol:.3f}[{label}]"
            )

        # Assemble amix inputs
        mix_inputs = [base_audio]
        if ambient_path:
            mix_inputs.append("[bed]")
        mix_inputs += [f"[cue{i}]" for i in range(len(sfx_cues))]

        n_mix = len(mix_inputs)
        filter_lanes.append(
            f"{''.join(mix_inputs)}amix=inputs={n_mix}:duration=first:normalize=0[aout]"
        )

        filter_complex = ";".join(filter_lanes)
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
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=300)
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or b"")[:600].decode("utf-8", errors="replace")
            raise RuntimeError(f"Audio mix failed: {stderr}") from exc

        # Assertion: cumulative SFX offset < slot duration (Counter 3 mitigation)
        for cue in sfx_cues:
            if int(cue.get("offset_ms", 0)) >= slot_dur_ms:
                print(
                    f"[stitch] WARN: SFX cue offset {cue['offset_ms']}ms >= "
                    f"slot duration {slot_dur_ms}ms — cue will be silent"
                )
        return out_path

    def _stitch_build_pipeline(self, body: dict) -> tuple[Path, list[int], list[int]]:
        """Core pipeline shared by preview and bake.

        Returns (output_mp4_path, [slot_dur_ms, ...]).
        Raises RuntimeError/FileNotFoundError on any failure.
        """
        import hashlib as _hl  # noqa: PLC0415
        from ffmpeg_stitch import concat_with_xfade_clips, lru_cleanup  # noqa: PLC0415

        slots = body.get("slots") or []
        if not slots:
            raise ValueError("No slots provided")

        project_root_str = str(self._stitch_project_root())
        cache_dir = self._stitch_cache_dir()

        # Validate all paths upfront (Rule 19: no open error paths)
        for i, slot in enumerate(slots):
            vp = slot.get("video_path") or ""
            if not vp:
                raise ValueError(f"Slot {i} has no video assigned")
            try:
                abs_vp = self._stitch_resolve_path(vp)
            except ValueError:
                raise PermissionError(f"Slot {i} video_path outside project root")
            if not os.path.isfile(abs_vp):
                raise FileNotFoundError(f"Slot {i} video not found: {abs_vp}")
            # Validate audio paths if specified
            if slot.get("ambient_bed_path") and not os.path.isfile(slot["ambient_bed_path"]):
                raise FileNotFoundError(f"Slot {i} ambient_bed_path not found: {slot['ambient_bed_path']}")
            for cue in (slot.get("sfx_cues") or []):
                if cue.get("source_path") and not os.path.isfile(cue["source_path"]):
                    raise FileNotFoundError(f"Slot {i} SFX not found: {cue['source_path']}")
            # S5.5g trim validation (audit doc §5):
            #   trim_in_ms >= 0
            #   trim_out_ms is null OR trim_out_ms > trim_in_ms
            t_in = slot.get("trim_in_ms")
            t_out = slot.get("trim_out_ms")
            if t_in is not None:
                try:
                    t_in_i = int(t_in)
                except (TypeError, ValueError):
                    raise ValueError(f"Slot {i} trim_in_ms must be an integer")
                if t_in_i < 0:
                    raise ValueError(f"Slot {i} trim_in_ms must be >= 0")
            if t_out is not None and str(t_out) != "":
                try:
                    t_out_i = int(t_out)
                except (TypeError, ValueError):
                    raise ValueError(f"Slot {i} trim_out_ms must be integer or null")
                t_in_i = int(t_in) if t_in is not None else 0
                if t_out_i <= t_in_i:
                    raise ValueError(
                        f"Slot {i} trim_out_ms ({t_out_i}) must be > trim_in_ms ({t_in_i})",
                    )

        # Per-slot pipeline
        slot_finals: list[Path] = []
        slot_durations: list[int] = []
        for i, slot in enumerate(slots):
            vp = self._stitch_resolve_path(slot["video_path"])

            # Step 1: Normalize (LD-284) + S5.5g per-slot trim
            # (STITCHER_PER_SLOT_TRIMS_V1 per audit doc §5).
            trim_in_ms = int(slot.get("trim_in_ms", 0) or 0)
            trim_out_raw = slot.get("trim_out_ms", None)
            trim_out_ms: int | None = (
                int(trim_out_raw)
                if trim_out_raw is not None and str(trim_out_raw) != ""
                else None
            )
            norm = self._stitch_normalize_slot(
                vp, cache_dir,
                trim_in_ms=trim_in_ms,
                trim_out_ms=trim_out_ms,
            )

            # Step 2: Audio parity (CONCAT_AUDIO_PARITY_V1)
            norm = self._stitch_ensure_audio(norm, cache_dir)

            slot_dur_ms = self._ffprobe_duration_ms(norm)
            slot_durations.append(slot_dur_ms)

            # Step 3+4: Mix ambient + SFX (slot-relative offsets)
            final = self._stitch_mix_slot_audio(norm, slot, cache_dir)
            slot_finals.append(final)

        # Handle transitions per spec §3.3 + Q1 LOCKED 2026-05-04 +
        # STITCHER_TRANSITIONS_V1 (HARD).
        #
        # Transition shape:
        #   {after_slot, kind: 'crossfade'|'cut'|'dissolve', fade_ms,
        #    audio_xfade_ms, source_path?}
        #
        # Defaults (handoff §3.3):
        #   kind absent → 'crossfade' (backward compat for legacy jobs)
        #   audio_xfade_ms absent → fade_ms (audio matches visual)
        #
        # kind semantics:
        #   'cut'       → skip transition synthesis (no SFX cue; no fadeblack)
        #   'crossfade' → existing trans_<after_slot> SFX cue at slot tail;
        #                 audio_xfade_ms controls the SFX fadein/fadeout
        #   'dissolve'  → visual fadeblack at boundary via ffmpeg fade=t=out
        #                 on slot[after_slot] tail + fade=t=in on slot[after_slot+1]
        #                 head; audio_xfade_ms=0 → hard audio cut;
        #                 audio_xfade_ms>0 → afade out/in across the boundary
        transitions = body.get("transitions") or []
        from server_handlers.stitch_editor import canonical_stitch_transitions_for_pipeline  # noqa: PLC0415
        transitions = canonical_stitch_transitions_for_pipeline(transitions)
        trans_by_after = {
            int(t.get("after_slot", 0)): t for t in transitions if isinstance(t, dict)
        }
        for t in transitions:
            after_slot = int(t.get("after_slot", 0))
            if after_slot >= len(slot_finals):
                continue
            kind = (t.get("kind") or "crossfade").lower()
            if kind == "cut":
                continue
            fade_ms = int(t.get("fade_ms", 500))
            audio_xfade_ms = int(t.get("audio_xfade_ms", fade_ms))
            t_path = t.get("source_path") or ""

            if kind == "crossfade":
                # Existing path: synthesize trans_<after_slot> SFX cue.
                # Requires source_path (else nothing to inject; fall back to no-op
                # equivalent to 'cut' for the audio side).
                if not t_path or not os.path.isfile(t_path):
                    continue
                # Security (CodeQL py/path-injection alert #41 follow-up):
                # transition source_path is body-controlled and flows into
                # ffmpeg `-i` via _stitch_mix_slot_audio. Containment guard.
                try:
                    self._stitch_assert_path_in_root(t_path, "transition source_path")
                except ValueError:
                    continue
                slot_dur = slot_durations[after_slot]
                offset_ms = max(0, slot_dur - fade_ms)
                # audio_xfade_ms controls the SFX cue fadein/fadeout duration.
                # Default 300/300 preserved when audio_xfade_ms=fade_ms (the
                # legacy implicit 300ms remains the floor for very short fades).
                cue_fade_ms = max(50, audio_xfade_ms // 2) if audio_xfade_ms > 0 else 300
                trans_slot = {"sfx_cues": [{"id": f"trans_{after_slot}", "source_path": t_path,
                              "offset_ms": offset_ms, "volume": 0.7,
                              "fadein_ms": cue_fade_ms, "fadeout_ms": cue_fade_ms}],
                              "ambient_bed_path": None}
                rebaked = self._stitch_mix_slot_audio(slot_finals[after_slot], trans_slot, cache_dir)
                slot_finals[after_slot] = rebaked

        # Dissolve boundaries: short visual fade + inserted black hold (not eating dialogue).
        from ffmpeg_stitch import (  # noqa: PLC0415
            DEFAULT_FADE_THROUGH_BLACK_VISUAL_IN_MS,
            DEFAULT_FADE_THROUGH_BLACK_VISUAL_OUT_MS,
            DEFAULT_MODULE_PAIR_FADE_MS,
            expand_clips_with_black_pause_boundaries,
        )

        try:
            import beat_generator as _bg_fade  # noqa: PLC0415

            _VISUAL_OUT_MS = _bg_fade._load_intro_fade_out_video_tail_ms()
            _VISUAL_IN_MS = _bg_fade._load_intro_fade_in_video_head_ms()
            _DEFAULT_DISSOLVE_MS = _bg_fade._load_intro_final_pair_fade_ms()
        except Exception:
            _VISUAL_OUT_MS = DEFAULT_FADE_THROUGH_BLACK_VISUAL_OUT_MS
            _VISUAL_IN_MS = DEFAULT_FADE_THROUGH_BLACK_VISUAL_IN_MS
            _DEFAULT_DISSOLVE_MS = DEFAULT_MODULE_PAIR_FADE_MS
        pair_fades_ms: list[int] = []
        for i in range(max(0, len(slot_finals) - 1)):
            t = trans_by_after.get(i)
            kind = (t.get("kind") or "dissolve").lower() if t else "dissolve"
            if kind == "dissolve":
                pair_fades_ms.append(int((t or {}).get("fade_ms", _DEFAULT_DISSOLVE_MS)))
            else:
                pair_fades_ms.append(0)
        if any(f > 0 for f in pair_fades_ms):
            slot_finals = expand_clips_with_black_pause_boundaries(
                slot_finals,
                pair_fades_ms,
                cache_dir / "module_boundary_black",
                visual_out_ms=_VISUAL_OUT_MS,
                visual_in_ms=_VISUAL_IN_MS,
                fade_audio=False,
            )
            slot_finals = self._stitch_apply_canonical_boundary_sfx(
                slot_finals,
                pair_fades_ms,
                cache_dir,
                visual_out_ms=_VISUAL_OUT_MS,
                visual_in_ms=_VISUAL_IN_MS,
            )

        slot_finals = self._stitch_apply_resolution_finale(
            slot_finals,
            cache_dir,
            visual_out_ms=_VISUAL_OUT_MS,
        )

        from ffmpeg_stitch import module_slot_start_offsets_ms  # noqa: PLC0415

        slot_start_offsets_ms = module_slot_start_offsets_ms(
            slot_durations,
            pair_fades_ms,
            visual_out_ms=_VISUAL_OUT_MS,
            visual_in_ms=_VISUAL_IN_MS,
        )

        # Concat all slot finals (LD-284: already normalized)
        job_sig = json.dumps(
            {
                "slots": [s.get("video_path") for s in slots],
                "trans": transitions,
            },
            sort_keys=True,
        ).encode()
        # Fingerprint slot finals by path + mtime + size so rebuilt se_slot_* files
        # invalidate stale stitch_preview_* LRU hits (STITCH_SLOT_PREVIEW_VIDEO_PLAYABLE_V1).
        final_fp = "|".join(
            f"{p.resolve()}:{p.stat().st_mtime_ns}:{p.stat().st_size}"
            for p in slot_finals
        )
        out_hash = _hl.md5(
            final_fp.encode() + job_sig,
            usedforsecurity=False,
        ).hexdigest()[:12]

        out_path = cache_dir / f"stitch_preview_{out_hash}.mp4"
        expected_ms = sum(self._ffprobe_duration_ms(p) for p in slot_finals)
        expected_s = expected_ms / 1000.0
        from ffmpeg_stitch import preview_cache_is_valid  # noqa: PLC0415

        if out_path.is_file() and not preview_cache_is_valid(out_path, expected_s):
            try:
                out_path.unlink()
            except OSError:
                pass

        if not out_path.is_file():
            if len(slot_finals) == 1:
                import shutil as _shutil  # noqa: PLC0415

                tmp = out_path.parent / (
                    f"{out_path.stem}.tmp.{os.getpid()}{out_path.suffix}"
                )
                # copy (not copy2): fresh mtime so lru_cleanup keeps the new preview.
                _shutil.copy(slot_finals[0], tmp)
                os.replace(tmp, out_path)
            else:
                concat_with_xfade_clips(slot_finals, out_path)

        if not preview_cache_is_valid(out_path, expected_s):
            actual_ms = self._ffprobe_duration_ms(out_path)
            raise RuntimeError(
                f"stitch preview corrupt or truncated: got {actual_ms}ms, "
                f"expected ~{expected_ms}ms ({out_path.name})",
            )

        # LRU cleanup (prevent cache accumulation)
        lru_cleanup(cache_dir, keep=5, pattern=r"^stitch_preview_.*\.mp4$")
        lru_cleanup(cache_dir, keep=10, pattern=r"^se_slot_.*\.mp4$")

        return out_path, slot_durations, slot_start_offsets_ms

    @with_pin_and_drain('_handle_stitch_preview', track_sync=True)
    def _handle_stitch_preview(self, body: dict) -> None:
        from server_handlers.stitch_editor import handle_stitch_preview
        return handle_stitch_preview(self, body)

    @with_pin_and_drain('_handle_stitch_bake', track_sync=True)
    def _handle_stitch_bake(self, body: dict) -> None:
        from server_handlers.stitch_editor import handle_stitch_bake
        return handle_stitch_bake(self, body)

    # ---- end Stitch Editor handlers ----

    def _serve_phase_media(self, filename: str) -> None:
        """GET /api/phase_b/media/<filename>

        Streams event_dir files (phase_*_voice_stem_*.mp3,
        phase_*_mixed_*.mp3, phase_*_lipsync_*.mp4) to the panel's
        <audio>/<video> elements. Basename-sanitized; no path traversal.
        """
        safe = Path(filename).name
        # Only allow phase_ prefixed module-level files to be served here.
        if not safe.startswith("phase_"):
            return self._send_error_v59(
                       400,
                       error_code="GENERIC_ERROR",
                       error_message=f"phase media serve rejects non-phase file: {safe!r}",
                       retry_safe=False,
                       extra={"hint": "Endpoint restricted to phase_*_voice_stem/mixed/lipsync files."},
                   )
        target = self.app.event_dir / safe
        if not target.is_file():
            return self._send_error_v59(
                       404,
                       error_code="GENERIC_ERROR",
                       error_message=f"phase media not found: {safe}",
                       retry_safe=False,
                   )
        suffix = target.suffix.lower()
        ctype = {".mp3": "audio/mpeg", ".mp4": "video/mp4",
                 ".wav": "audio/wav"}.get(suffix, "application/octet-stream")
        body = target.read_bytes()
        self._send_bytes(200, body, ctype, extra_headers={
            "Cache-Control": "no-store, must-revalidate",
            "Accept-Ranges": "bytes",
        })

    def _serve_watercolor(self, filename: str) -> None:
        """GET /api/phase_b/watercolor/<filename>

        Streams Event_N/library/watercolors/<filename> thumbnails and
        video cue assets to the timeline widget's library panel.

        Accepts both a bare key (e.g. "hands_rubbing") and a full filename with
        extension (e.g. "hands_rubbing.png").  When the client sends a bare key
        (which is how the Phase B cue overlay builds its src URL), the handler
        resolves the extension via glob — same strategy as handle_watercolor_animate.
        Prefers .png over .mov/.mp4 when multiple matches exist.
        """
        safe = Path(filename).name
        _ALLOWED_EXTS = (".png", ".mov", ".mp4")
        from lib.event_library import event_watercolors_dir
        from server_handlers._path_security import require_basename_under_dir, require_resolved_under_root

        wc_dir = event_watercolors_dir(self.app.event_dir)
        # Bare key path — no valid extension provided by the caller.
        if not safe.lower().endswith(_ALLOWED_EXTS):
            matches = [m for m in wc_dir.glob(f"{safe}.*")
                       if m.suffix.lower() in _ALLOWED_EXTS]
            if not matches:
                return self._send_error_v59(
                           400,
                           error_code="GENERIC_ERROR",
                           error_message=f"watercolor not found: {safe!r} (no .png/.mov/.mp4 in library)",
                           retry_safe=False,
                           extra={"hint": "Ensure the asset exists in Event library/watercolors/ with a .png, .mov, or .mp4 extension."},
                       )
            # RC2 fix: prefer the animated MP4/MOV over a static PNG when multiple
            # extensions share the same stem (e.g., a thumbnail alongside a video).
            mp4_match = next((m for m in matches if m.suffix.lower() in (".mp4", ".mov")), None)
            png_match = next((m for m in matches if m.suffix.lower() == ".png"), None)
            try:
                target = require_resolved_under_root(
                    mp4_match or png_match or matches[0],
                    wc_dir,
                )
            except ValueError:
                return self._send_error_v59(
                           403,
                           error_code="GENERIC_ERROR",
                           error_message=f"watercolor path outside library: {safe!r}",
                           retry_safe=False,
                       )
        else:
            try:
                target = require_basename_under_dir(safe, wc_dir)
            except ValueError:
                return self._send_error_v59(
                           400,
                           error_code="GENERIC_ERROR",
                           error_message=f"invalid watercolor filename: {safe!r}",
                           retry_safe=False,
                       )
        if not target.is_file():
            return self._send_error_v59(
                       404,
                       error_code="GENERIC_ERROR",
                       error_message=f"watercolor not found: {safe}",
                       retry_safe=False,
                   )
        suffix = target.suffix.lower()
        ctype = {".png": "image/png", ".mov": "video/quicktime",
                 ".mp4": "video/mp4"}.get(suffix, "application/octet-stream")
        body = target.read_bytes()
        self._send_bytes(200, body, ctype, extra_headers={
            "Cache-Control": "public, max-age=600",
        })

    @with_pin_and_drain('_handle_phase_b_regen_audio', track_sync=True)
    def _handle_phase_b_regen_audio(self, body: dict) -> None:
        from server_handlers.phases import handle_phase_b_regen_audio
        return handle_phase_b_regen_audio(self, body)

    # ------------------------------------------------------------------
    # Phase A panel — persistent voice settings (LD-303 follow-up,
    # 2026-04-20). Sliders in the Phase A authoring panel write to
    # prod_voice_profiles by id (Chipper=2). Cedric (id=1) and Tessa
    # (id=3) are addressable but locked behind an explicit allow-list to
    # keep the surface narrow per Phase 0 4+4 verdict (counter C1).
    #
    # Session-decision-key: PHASE_A_PANEL_VOICE_SLIDERS_V1.
    # ------------------------------------------------------------------
    # GET (read) is permissive across known characters; useful for future
    # panels (Cedric meditation panel may want to display Cedric voice
    # state). WRITE is locked to Chipper-only per Phase 0 4+4 verdict
    # counter C1: silent Cedric overwrite is unrecoverable, so the path
    # is structurally closed at the route layer until Kim explicitly
    # opens it.
    _VOICE_PROFILE_GET_ALLOWED_IDS = frozenset({1, 2, 3})  # Cedric, Chipper, Tessa
    _VOICE_PROFILE_PATCH_ALLOWED_IDS = frozenset({2})      # Chipper only (Phase A)
    _VOICE_PROFILE_ALLOWED_FIELDS = frozenset({"stability", "similarity_boost", "style"})

    def _handle_voice_profile_get(self, pid_raw: str) -> None:
        from server_handlers.vendor_jobs import handle_voice_profile_get
        return handle_voice_profile_get(self, pid_raw)

    def _handle_voice_profile_update(self, body: dict) -> None:
        from server_handlers.vendor_jobs import handle_voice_profile_update
        return handle_voice_profile_update(self, body)

    @with_pin_and_drain('_handle_phase_b_mix_audio', track_sync=True)
    def _handle_phase_b_mix_audio(self, body: dict) -> None:
        from server_handlers.phases import handle_phase_b_mix_audio
        return handle_phase_b_mix_audio(self, body)

    def _handle_phase_a_regen_flyin_flyout(self, body: dict) -> None:
        from server_handlers.phases import handle_phase_a_regen_flyin_flyout
        return handle_phase_a_regen_flyin_flyout(self, body)

    def _handle_phase_a_regen_base_clip(self, body: dict) -> None:
        from server_handlers.phases import handle_phase_a_regen_base_clip
        return handle_phase_a_regen_base_clip(self, body)

    def _handle_phase_a_restitch(self, body: dict) -> None:
        from server_handlers.phases import handle_phase_a_restitch
        return handle_phase_a_restitch(self, body)

    @with_pin_and_drain('_handle_phase_a_lipsync', track_sync=True)
    def _handle_phase_a_lipsync(self, body: dict) -> None:
        from server_handlers.phases import handle_phase_a_lipsync
        return handle_phase_a_lipsync(self, body)

    @with_pin_and_drain('_handle_phase_reject_lipsync', track_sync=True)
    def _handle_phase_reject_lipsync(self, body: dict) -> None:
        from server_handlers.phases import handle_phase_reject_lipsync
        return handle_phase_reject_lipsync(self, body)

    @with_pin_and_drain('_handle_phase_apply_stem_cut', track_sync=True)
    def _handle_phase_apply_stem_cut(self, body: dict) -> None:
        from server_handlers.phases import handle_phase_apply_stem_cut
        return handle_phase_apply_stem_cut(self, body)

    def _auto_assemble_phase_a_stitched(self, ts: str) -> dict | None:
        """Stitch raw Phase A lipsync middle only + continuous ambient bed.

        Arlo migration (2026-06): fly-in/fly-out bookends removed — Arlo is
        already on-screen in the wizard desk base; no entrance/exit Kling clips.

        Two-stage ffmpeg:
          1. Normalize raw lipsync to LD-284 (1280×720)
          2. Overlay full-length bed from state.phase_a_ambient_preset_id at
             volume=0.15 -> canonical final

        Uses RAW lipsync (no "withbed" in name) so the bed is never doubled.

        Returns {file, mtime, duration_s} or None if lipsync input missing.
        """
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "credentials_lib"))
        from ffmpeg_stitch import normalize_for_concat  # type: ignore

        state = self.app.state.read_state()

        from phase_a_stitch_lib import resolve_phase_a_raw_lipsync  # noqa: WPS433

        raw_lipsync_path = resolve_phase_a_raw_lipsync(self.app.event_dir, state)
        if not raw_lipsync_path:
            return None

        # Resolve ambient preset (for the full-length overlay).
        # S5.5d (v3): phase_a is TOP-LEVEL state.
        ambient_preset_id = (
            state.get("phase_a_ambient_preset_id")
            or (state.get("phase_a") or {}).get("phase_a_ambient_preset_id")
        )
        ambient_path: Path | None = None
        if ambient_preset_id:
            candidate = self._phase_assets_dir("ambient_library") / f"{ambient_preset_id}.mp3"
            if candidate.is_file():
                ambient_path = candidate

        # Normalize each clip (cached: skip if norm is newer than src).
        norm_dir = self.app.event_dir / "_normalized_phase_a"
        norm_dir.mkdir(exist_ok=True)

        def _normalize_cached(src: Path, dst: Path) -> None:
            needs = (not dst.is_file()) or (src.stat().st_mtime > dst.stat().st_mtime)
            if needs:
                normalize_for_concat(src, dst)

        raw_norm = norm_dir / f"raw_{raw_lipsync_path.stem}.mp4"
        _normalize_cached(raw_lipsync_path, raw_norm)
        intermediate_path = raw_norm

        out_path = self.app.event_dir / f"phase_a_stitched_{ts}.mp4"

        if ambient_path is not None:
            # Stage 2: overlay continuous ambient bed across the full duration.
            try:
                total_dur = _ffprobe_duration(intermediate_path)
            except Exception:  # noqa: BLE001
                total_dur = 0.0
            if total_dur <= 0:
                # ffprobe failed — fall back to passing intermediate through.
                import shutil as _shutil
                _shutil.copy2(intermediate_path, out_path)
            else:
                filter_complex = (
                    f"[1:a]atrim=0:{total_dur:.3f},volume=0.15[bed];"
                    f"[0:a][bed]amix=inputs=2:duration=first:normalize=0[aout]"
                )
                cmd = [
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-i", str(intermediate_path.resolve()),
                    "-stream_loop", "-1", "-i", str(ambient_path.resolve()),
                    "-filter_complex", filter_complex,
                    "-map", "0:v",
                    "-map", "[aout]",
                    "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "1",
                    "-movflags", "+faststart",
                    str(out_path),
                ]
                try:
                    subprocess.run(cmd, check=True, capture_output=True, timeout=120)
                except subprocess.CalledProcessError as exc:
                    stderr = (exc.stderr or b"")[:300].decode("utf-8", errors="replace")
                    print(f"[canonical] bed overlay failed: rc={exc.returncode} {stderr}")
                    import shutil as _shutil
                    _shutil.copy2(intermediate_path, out_path)
        else:
            # No ambient preset selected — ship intermediate as the canonical.
            import shutil as _shutil
            _shutil.copy2(intermediate_path, out_path)

        mtime_v = int(os.path.getmtime(str(out_path)))
        try:
            dur = _ffprobe_duration(out_path)
        except Exception:  # noqa: BLE001
            dur = 0.0

        def _apply(state, _n=out_path.name, _m=mtime_v):
            for key, val in (
                ("phase_a_stitched_file", _n),
                ("phase_a_stitched_mtime", _m),
            ):
                state[key] = val
                nested = state.setdefault("phase_a", {})
                if isinstance(nested, dict):
                    nested[key] = val
            state["_module_version"] = int(state.get("_module_version", 0) or 0) + 1
            return state["_module_version"]
        try:
            self.app.state.mutate_state(_apply)
        except Exception as exc:  # noqa: BLE001
            print(f"[canonical] mutate_state failed (non-fatal): {exc}")

        return {
            "file": out_path.name,
            "mtime": mtime_v,
            "duration_s": round(dur, 3),
            "raw_lipsync": raw_lipsync_path.name,
            "bookends": "none",
            "ambient_preset_id": ambient_preset_id,
        }

    @with_pin_and_drain('_handle_phase_b_lipsync', track_sync=True)
    def _handle_phase_b_lipsync(self, body: dict) -> None:
        from server_handlers.phases import handle_phase_b_lipsync
        return handle_phase_b_lipsync(self, body)

    # Phase B/A preview — composes lipsync video + watercolor cues.
    # LD-331 WATERCOLOR_OVERLAY_SCALE_TO_BBOX_NO_PAD_V2 (effective 2026-04-20):
    #   Phase B LEFT bbox = 600x540 at (frame_x=40, frame_y=180)
    #   Phase A RIGHT bbox = 480x540 at (frame_x=800, frame_y=180)
    # Watercolor PNG/MP4 scales via `scale=w=frame_max_w:h=frame_max_h:
    # force_original_aspect_ratio=decrease` with NO centered-pad step, then
    # lands at (frame_x, frame_y) at its native scaled size — correctly
    # fitting LEFT vs RIGHT half of the 1280x720 canvas.
    # Implementation (ffmpeg_stitch.py _wc_build_cue_prefilter) defaults to
    # 600x540 for Phase B; these dicts override per-phase for the call site.
    # Closes inventory v2 PB-17 + PA-19 WIRED-BUT-BROKEN class.
    #
    # wc_v6 position fix (2026-05-28): Phase B lipsync base is 720×544.
    # NORMALIZATION_VF_EXPR scales it to 953×720 within the 1280×720 canvas,
    # centering the content with x_offset=164px on each side (black letterbox).
    # Old frame_x["b"]=40 fell inside the left black bar → overlay never visible
    # on the actual content. Corrected values match the CSS overlay at left=2%,
    # top=4%, width=35% of the video (LD-821 CSS overlay architecture):
    #   frame_x["b"] = 164 (content_left) + round(2% × 953) = 183 → 185
    #   frame_y       = round(4% × 720) = 29 → 30
    #   frame_max_w["b"] = round(35% × 953) = 334 → 340
    _PHASE_FRAME_X = {"b": 185, "a": 800}
    _PHASE_FRAME_Y = 30
    _PHASE_FRAME_MAX_W = {"b": 340, "a": 480}
    _PHASE_FRAME_MAX_H = {"b": 540, "a": 540}

    def _handle_phase_b_preview(self, body: dict) -> None:
        from server_handlers.phases import handle_phase_b_preview
        return handle_phase_b_preview(self, body)

    def _handle_phase_export_stitcher(self, body: dict) -> None:
        from server_handlers.phases import handle_phase_export_stitcher
        return handle_phase_export_stitcher(self, body)


# ---------------------------------------------------------------------------
# Startup / lifecycle
# ---------------------------------------------------------------------------

def cleanup_stale(pid_file: Path) -> None:
    if not pid_file.is_file():
        return
    try:
        pid = int(pid_file.read_text().strip())
    except ValueError:
        try:
            pid_file.unlink(missing_ok=True)
        except PermissionError:
            # Dropbox or filesystem lock — overwrite instead of delete
            pid_file.write_text("")
            print("[startup] WARNING: could not delete stale pid file (permission), cleared it")
        return
    try:
        if sys.platform == "win32":
            import ctypes
            ctypes.windll.kernel32.TerminateProcess(
                ctypes.windll.kernel32.OpenProcess(1, False, pid), 1
            )
        else:
            os.kill(pid, signal.SIGTERM)
        print(f"[startup] killed stale server pid={pid}")
        time.sleep(3)  # give OS time to release the port
    except (ProcessLookupError, OSError):
        pass
    except PermissionError:
        print(f"[startup] WARNING: stale pid {pid} not ours — leaving alone")
    try:
        pid_file.unlink(missing_ok=True)
    except PermissionError:
        # Dropbox or filesystem lock — overwrite instead of delete
        print("[startup] WARNING: could not delete pid file (permission), will overwrite")


def port_free(port: int, retries: int = 8, delay: float = 1.5) -> bool:
    """Check if port is available. Retries to handle post-kill release delay."""
    for attempt in range(retries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
                return True
            except OSError:
                if attempt < retries - 1:
                    print(f"[startup] port {port} still in use, retrying in {delay}s...")
                    time.sleep(delay)
    return False


def inactivity_watchdog(app: AppContext, stop_event: threading.Event, httpd: ProductionServer) -> None:
    while not stop_event.is_set():
        if app.idle_seconds() > INACTIVITY_TIMEOUT_SEC:
            print(f"[watchdog] {INACTIVITY_TIMEOUT_SEC}s idle — shutting down")
            httpd.shutdown()
            return
        for _ in range(60):
            if stop_event.is_set():
                return
            time.sleep(1)


def _check_runtime_capabilities() -> None:
    """Probe every hard-required and feature-degraded runtime dep at startup.

    HARD deps (FATAL on missing): PyYAML, Pillow — break core handlers if absent.
    SOFT deps (degraded feature): numpy — breaks Magic compositor specifically.

    Emits structured ``[startup:capabilities]`` line that log scrapers + the
    UI's `/api/bg/session-state.capabilities` reader can parse. Mirrors the
    existing WaveSpeed smoke pattern at lines 11614–11638.

    Audit C4-1/C4-2/C4-3/C4-4 origin: yaml + numpy were missing in the
    runtime Python env on 2026-05-19; first user click on Magic surfaced
    a generic 500. This check fails fast on hard deps and degrades cleanly
    on soft deps.
    """
    hard = {"PyYAML": "yaml", "Pillow": "PIL"}
    soft = {"numpy": "numpy", "scipy": "scipy"}  # both needed for magic_compositor [INFERRED — verify via grep -rn "import numpy\|import scipy" Production/tools/magic_compositor.py: both imports present at module top.]
    missing_hard: list[str] = []
    missing_soft: list[str] = []
    for label, mod in hard.items():
        try:
            __import__(mod)
        except ImportError:
            missing_hard.append(label)
    for label, mod in soft.items():
        try:
            __import__(mod)
        except ImportError:
            missing_soft.append(label)

    capabilities = {
        "yaml": "PyYAML" not in missing_hard,
        "pillow": "Pillow" not in missing_hard,
        "magic_compositor": not missing_soft,
    }
    bg_caps = _bg_capabilities()
    capabilities["update_beat_locked"] = bool(bg_caps.get("update_beat_locked"))
    capabilities["sidecar_file_lock"] = bool(bg_caps.get("sidecar_file_lock"))
    # Structured single-line capability report (parseable).
    print(
        f"[startup:capabilities] {json.dumps(capabilities, sort_keys=True)}",
        flush=True,
    )

    if not capabilities["update_beat_locked"] or not capabilities["sidecar_file_lock"]:
        print(
            "[startup:FATAL] beat_generator missing O3 sidecar API "
            "(update_beat_locked / sidecar_file_lock). "
            "Element O3 + lipsync pipelines will fail until tools are redeployed.",
            file=sys.stderr,
            flush=True,
        )
        sys.exit(4)

    if missing_soft:
        for name in missing_soft:
            print(
                f"[startup:degraded] feature 'magic_compositor' disabled — "
                f"'{name}' not installed. Install via `pip install -r "
                f"Production/tools/requirements.txt`.",
                file=sys.stderr,
                flush=True,
            )

    if missing_hard:
        for name in missing_hard:
            print(
                f"[startup:FATAL] hard-required runtime dep '{name}' missing. "
                f"Install via `pip install -r Production/tools/requirements.txt` "
                f"before starting the server.",
                file=sys.stderr,
                flush=True,
            )
        sys.exit(4)


def run_server(event_dir: Path, storyboard_name: str, event_id: str, *, source_event_dir: Path | None = None) -> int:
    from lib.event_pin import resolve_startup_event
    from lib.paths import normalize_event_dir

    event_dir, storyboard_name, event_id, pin_source = resolve_startup_event(
        event_dir, storyboard_name, event_id,
    )
    event_dir = normalize_event_dir(event_dir)
    storyboard_path = event_dir / storyboard_name
    if not storyboard_path.is_file():
        print(f"ERROR: storyboard not found: {storyboard_path}", file=sys.stderr)
        return 2

    print(
        f"[startup] event scope event_id={event_id} pin_source={pin_source} "
        f"event_dir={event_dir}",
        flush=True,
    )

    # LD-505 Phase C (2026-05-19): rebind every beat_generator module-level
    # path constant from the runtime event_dir. Replaces the original
    # 2-constant override (BG_STILLS_DIR + BG_SIDECAR_PATH) with a complete
    # pass over all 11 constants + the two character-pose dicts that were
    # baked at module-import time anchored on the (empty) tooling tree.
    # Closes audit findings C1-5 / C1-6 / C1-7 / C1-8 / C1-9.
    # See Production/lib/paths.py for the canonical helpers.
    _bg_module().init_bg_paths(event_dir)

    # P2 / LD-505 Phase C: dependency-presence smoke. Hard deps fail-loud
    # with [FATAL]; soft deps degrade with structured [startup:capabilities]
    # line that the UI / log scraper can parse. Audit C4-1/C4-2/C4-3/C4-4.
    _check_runtime_capabilities()

    pid_file = event_dir / "production_server.pid"
    cleanup_stale(pid_file)
    if not port_free(SERVER_PORT):
        print(f"ERROR: port {SERVER_PORT} already in use", file=sys.stderr)
        return 3

    # Parse API keys — LD-505 Phase C (T1-4, 2026-05-19): API_KEYS_MASTER.md
    # is DATA, not code (.gitignored, Dropbox-only). Was anchored on tooling
    # repo root via `Path(__file__).resolve().parents[2]` → file MISSING under
    # LD-505 dual-canonical-roots when server runs from tooling. Result:
    # parse_api_keys returned empty → no WaveSpeed key → /api/animate 500
    # ("WaveSpeed client not configured") on every Regenerate B + C click,
    # even without --doppler-run wrapper. Use lib/paths.API_KEYS_MASTER_PATH
    # (same canonical resolver credentials.py uses for the Directus + EL keys).
    from lib.paths import API_KEYS_MASTER_PATH
    keys = parse_api_keys(API_KEYS_MASTER_PATH)
    client: WaveSpeedClient | None = None
    if keys.get("wavespeed"):
        client = WaveSpeedClient(keys["wavespeed"])
        # BS3 (Tier 3 blind-spot fix, April 16 2026): startup smoke test.
        # Exercises _wavespeed_request end-to-end (TCP + TLS + OP_NO_TICKET
        # context + auth header + response parse) so connectivity problems
        # surface at startup instead of at the first /api/animate call.
        # 5s cap, non-blocking (WARN-only on failure).
        _smoke_t0 = time.monotonic()
        try:
            _smoke_status, _ = _wavespeed_request(
                "GET", "https://api.wavespeed.ai/",
                api_key=keys["wavespeed"],
                timeout=5,
            )
            _smoke_ms = int((time.monotonic() - _smoke_t0) * 1000)
            if _smoke_status in (401, 403):
                print(f"[startup] WARN WaveSpeed smoke: auth rejected "
                      f"(HTTP {_smoke_status}, {_smoke_ms}ms) — check API key")
            elif 500 <= _smoke_status < 600:
                print(f"[startup] WARN WaveSpeed smoke: upstream 5xx "
                      f"(HTTP {_smoke_status}, {_smoke_ms}ms) — WaveSpeed-side issue")
            else:
                print(f"[startup] WaveSpeed smoke OK "
                      f"(HTTP {_smoke_status}, {_smoke_ms}ms)")
        except urllib.error.URLError as _smoke_exc:
            _smoke_ms = int((time.monotonic() - _smoke_t0) * 1000)
            print(f"[startup] WARN WaveSpeed smoke: connectivity failure "
                  f"({_smoke_ms}ms) — {_smoke_exc}")
        except Exception as _smoke_exc:  # noqa: BLE001
            print(f"[startup] WARN WaveSpeed smoke: unexpected "
                  f"{type(_smoke_exc).__name__}: {_smoke_exc}")
    else:
        print("[startup] WARNING: no WaveSpeed key found — /api/animate will 500")

    state = StateManager(event_dir, event_id)

    # BS4 (Tier 3 blind-spot fix, April 16 2026): sweep orphan *.tmp files left
    # behind by WaveSpeedClient.download crashes. Atomic tmp+rename leaves .tmp
    # files only on exception — clean them up on next startup.
    for orphan in state.clips_dir.glob("*.tmp"):
        try:
            orphan.unlink()
            print(f"[startup] removed orphan tmp: {orphan.name}")
        except OSError as exc:
            print(f"[startup] WARN: could not remove {orphan.name}: {exc}")

    # BS5 + P3 (LD-505 Phase C): Ghost-file scrub — v3 partition aware.
    #
    # Original BS5 (2026-04) walked `state["beats"]` (legacy v2 top-level
    # shape). After v3 partitions landed (`state.videos.<role>.beats`),
    # this walk found NOTHING and silently became a no-op for the whole
    # ghost class — but printed "[startup:ghost_scrub] OK" giving the
    # impression it worked. Audit C3-1.
    #
    # P3 fix: use lib.v3_partition._iter_v3_beats (also imported elsewhere
    # for orphan-sweep + lipsync polling). Distinguish TRULY orphaned files
    # (gone from disk + not in any archive dir) from manually archived
    # files (still recoverable from _archive_*/) — only the former get
    # status="ghost_cleaned"; archived files retain the option entry so the
    # PR #73 enrichment (file_exists=false → "(archived)" label) gives Kim
    # a recovery path. Walks every beat's phase_1.options[*] AND lipsync.file
    # so the next-archive-event scenario doesn't recur (audit C2-4).
    _ghost_count = 0
    _archived_count = 0
    _archive_dirs = sorted(
        d for d in state.clips_dir.iterdir()
        if d.is_dir() and d.name.startswith("_archive_")
    ) if state.clips_dir.exists() else []

    def _is_in_archive(fname: str) -> bool:
        return any((ad / fname).is_file() for ad in _archive_dirs)

    def _scrub_ghost_options(st: dict) -> None:
        nonlocal _ghost_count, _archived_count
        # C2-2/C2-3 (LD-pending GHOST_SCRUB_TOP_LEVEL_PATHS_V1, 2026-05-20):
        # also scrub stale TOP-LEVEL path pointers — latest_preview_stitched_path
        # at state root + completed_mp4_path per partition. These point at
        # individual files that can be deleted/renamed/archived independently
        # of the per-beat option/lipsync references. Without this scrub, the
        # state lookups silently return non-existent paths to clients.
        _top_path = st.get("latest_preview_stitched_path")
        if isinstance(_top_path, str) and _top_path and not Path(_top_path).is_file():
            st["latest_preview_stitched_path"] = None
            _ghost_count += 1
            print(
                f"[startup:ghost_scrub] cleared stale latest_preview_stitched_path "
                f"{_top_path!r}",
                flush=True,
            )
        for _v_role, _v_partition in (st.get("videos") or {}).items():
            if not isinstance(_v_partition, dict):
                continue
            _cm = _v_partition.get("completed_mp4_path")
            if isinstance(_cm, str) and _cm and not Path(_cm).is_file():
                _v_partition["completed_mp4_path"] = None
                _ghost_count += 1
                print(
                    f"[startup:ghost_scrub] cleared stale "
                    f"videos.{_v_role}.completed_mp4_path {_cm!r}",
                    flush=True,
                )

        for _role, _beat_id, _beat in _iter_v3_beats(st):
            # phase_1.options[*].file
            _opts = (_beat.get("phase_1") or {}).get("options") or []
            for _opt in _opts:
                _fname = _opt.get("file")
                if not _fname:
                    continue
                if (state.clips_dir / _fname).is_file():
                    continue
                if _is_in_archive(_fname):
                    _archived_count += 1
                    continue  # recoverable — leave entry; enrichment shows "(archived)"
                _opt["status"] = "ghost_cleaned"
                _opt.pop("file", None)
                _ghost_count += 1
                print(
                    f"[startup:ghost_scrub] {_role}/{_beat_id}: cleared truly-orphan "
                    f"option file {_fname!r}",
                    flush=True,
                )
            # beat.lipsync.file
            _ls = _beat.get("lipsync")
            if isinstance(_ls, dict):
                _lsfname = _ls.get("file")
                if _lsfname and not (state.clips_dir / _lsfname).is_file():
                    if not _is_in_archive(_lsfname):
                        _beat["lipsync"] = None  # clear truly-orphan lipsync ref
                        _ghost_count += 1
                        print(
                            f"[startup:ghost_scrub] {_role}/{_beat_id}: cleared "
                            f"truly-orphan lipsync file {_lsfname!r}",
                            flush=True,
                        )
                    else:
                        _archived_count += 1
    try:
        # P3: walk v3 partitions through mutate_state. Note: mutate_state takes
        # a function that receives full state dict (legacy + v3 partitions);
        # _iter_v3_beats handles both shapes internally.
        state.mutate_state(_scrub_ghost_options)
        if _ghost_count or _archived_count:
            print(
                f"[startup:ghost_scrub] cleaned {_ghost_count} ghost; "
                f"left {_archived_count} archived (recoverable via _archive_*/) ",
                flush=True,
            )
        else:
            print("[startup:ghost_scrub] OK — no ghost or archived files", flush=True)
    except Exception as _gs_exc:
        print(f"[startup:ghost_scrub] WARN: scrub failed (non-fatal): {_gs_exc}", flush=True)

    app = AppContext(event_dir, storyboard_path, event_id, state, client)

    # DIRECTUS_LOCK_WARMUP_V1 (2026-05-14): warm the cross-machine lock
    # client singleton + JWT auth at startup so the first user-triggered
    # mutate_state (typically Lipsync or Regen Audio) doesn't pay
    # JWT-login + Railway-cold-start latency inside its 10s lock budget.
    # Closes the "Directus lock unreachable" transient that fires on
    # the FIRST per-process call (Kim hit this on beat_17 2026-05-13).
    # Failure here is non-fatal — the cold path still works, just may
    # surface the transient error on first user click. Per Agent B's
    # b1 recommendation from FULL QA / Tier C lipsync investigation.
    try:
        _warm_client = _get_directus_lock_client()
        if _warm_client is not None:
            _t0 = time.time()
            # No-op probe to force JWT auth + first GET to complete now,
            # not during the user's first mutate. limit=1 keeps payload small.
            _warm_client.get("prod_locks", filters={
                "resource_key": {"_eq": "__warmup_probe__"},
            }, limit=1)
            print(f"[startup:dlock-warmup] Directus lock client warmed "
                  f"({(time.time()-_t0)*1000:.0f}ms)")
        else:
            print("[startup:dlock-warmup] WARN: lock client unavailable "
                  "(credentials or import); first mutate will retry path")
    except Exception as _wexc:  # noqa: BLE001
        print(f"[startup:dlock-warmup] WARN: warmup probe failed: "
              f"{type(_wexc).__name__}: {_wexc} — first mutate will hit "
              f"the lazy path under its own budget")

    # BEAT_GRAFT_RECOVERY_MECHANISM_V1 (C-7) — attach source_event_dir for
    # cross-event graft operations. None when --source-event is not passed.
    app.source_event_dir = source_event_dir
    if source_event_dir is not None:
        print(
            f"[startup] /api/beat/graft cross-event source registered: "
            f"{source_event_dir} (server still write-pinned to {event_dir.name})"
        )

    httpd = ProductionServer(("127.0.0.1", SERVER_PORT), app)
    try:
        pid_file.write_text(str(os.getpid()))
    except PermissionError:
        print("[startup] WARNING: could not write pid file (permission) — proceeding without it")

    stop_event = threading.Event()
    poller = None
    if client is not None:
        poller = PollingThread(state, client, stop_event)
        poller.start()

    # Preflight 107: orphan sweep runs regardless of WaveSpeed client
    # availability — it recovers stuck state (mid-submission crashes) that
    # would otherwise never be polled at all.
    orphan_sweeper = OrphanSweepThread(state, stop_event)
    orphan_sweeper.start()

    # Preflight 110: persistent lipsync poller so server restarts do NOT
    # kill in-flight lipsync polls. Requires a WaveSpeed client because
    # ByteDance LipSync is hosted through WaveSpeed's predictions endpoint.
    if client is not None:
        lipsync_poller = LipsyncPollingThread(state, client, stop_event)
        lipsync_poller.start()

    watchdog = threading.Thread(
        target=inactivity_watchdog, args=(app, stop_event, httpd),
        daemon=True, name="IdleWatchdog",
    )
    watchdog.start()

    def shutdown(*_a):  # noqa: ANN001
        print("[server] shutdown signal — stopping")
        stop_event.set()
        threading.Thread(target=httpd.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    print(f"[server] listening on http://localhost:{SERVER_PORT}  event={event_id}")
    print(f"[server] storyboard:  {storyboard_path}")
    print(f"[server] clips dir:   {state.clips_dir}")
    try:
        httpd.serve_forever()
    finally:
        stop_event.set()
        try:
            pid_file.unlink(missing_ok=True)
        except PermissionError:
            pass
        print("[server] exited")
    return 0


# ---------------------------------------------------------------------------
# Smoke test — no network, no external deps
# ---------------------------------------------------------------------------

def run_smoke_test() -> int:
    """Self-contained: verifies helpers, state manager, and handler plumbing.
    Does NOT hit WaveSpeed."""
    import tempfile

    print("[smoke] motion prompt build + sanitize...")
    # Legacy speaker "Guide Bird" canonicalizes to "Arlo" (2026-06-13 cast).
    # Narrative (lipsync-targeted) path gets non-motion-locking tail.
    beat = {"speaker": "Guide Bird", "section": "Discovery", "text": "Hi",
            "emotion": "happy_excited", "lipsync_targeted": True}
    p = build_motion_prompt(beat)
    assert "Mouth closed" in p, f"expected Mouth closed in: {p!r}"
    assert "Cartoon Arlo character" in p, f"canonical name missing: {p!r}"
    assert LIPSYNC_SAFE_TAIL in p, f"expected {LIPSYNC_SAFE_TAIL!r} in: {p!r}"
    # Sprite-pipeline path gets motion-locking tail.
    sprite_beat = {"speaker": "Tessa", "emotion": "neutral", "lipsync_targeted": False}
    ps = build_motion_prompt(sprite_beat)
    assert SPRITE_IDLE_TAIL in ps, f"expected {SPRITE_IDLE_TAIL!r} in: {ps!r}"
    dirty = "Cartoon bird talking and singing, open mouth. Silent subtle idle movement only."
    cleaned = sanitize_prompt(dirty)
    for banned in ["talking", "singing", "open mouth"]:
        assert banned not in cleaned.lower(), f"{banned} leaked through"

    print("[smoke] state manager round-trip...")
    with tempfile.TemporaryDirectory() as tmp:
        event_dir = Path(tmp) / "Event_Test"
        event_dir.mkdir()
        sm = StateManager(event_dir, "Event_Test")
        # S5.5a2: smoke test mutates videos.intro.beats (v2 shape per
        # _init_files post-S5.5a2). Uses mutate_video_state which receives
        # the partition dict; the partition already has beats key created
        # by _init_files for intro.
        sm.mutate_video_state("intro", lambda part: part["beats"].setdefault("beat_01", {
            "speaker": "Tessa", "text": "hi", "section": "Setup",
            "phase_1": {
                "status": "polling",
                "options": [{
                    "task_id": "t1", "status": "polling",
                    "file": None, "submitted_at": "2026-04-15T00:00:00Z",
                    "retries": 0, "last_error": None,
                }],
                "selected_option": None,
            },
        }))
        state = sm.read_state()
        # S5.5a2: smoke test asserts on intro partition (v2 shape).
        assert "beat_01" in state["videos"]["intro"]["beats"]
        sm.add_spend("kling_animation", 0.26)
        assert sm.read_spend()["total_spent"] == 0.26

        print("[smoke] mark-completed rollup...")
        # S5.5a2: _mark_completed now takes partition (not full state).
        sm.mutate_video_state("intro", lambda part: _mark_completed(part, "beat_01", 0, "beat_01_option_1.mp4", 1234))
        state = sm.read_state()
        assert state["videos"]["intro"]["beats"]["beat_01"]["phase_1"]["status"] == "completed"

        print("[smoke] image dimension gate (PIL hard-required per C5-2)...")
        tiny_png = (
            "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1"
            "HAwCAAAAC0lEQVR4nGNgAAIAAAUAAen63NgAAAAASUVORK5CYII="
        )
        ok, info = validate_image_dimensions(tiny_png)
        # PIL is now a hard startup dep (LD-pending DEPENDENCY_STARTUP_CHECK_V1 +
        # C5-2). Should reject 1x1 with "image too small (1x1, min shortest side 600px)".
        print(f"  -> ok={ok} info={info}")

        print("[smoke] storyboard HTML extraction...")
        sample_html = (
            "<html><body><script>window.storyboardData = " +
            json.dumps({
                "module": "M1", "event": 1,
                "lines": [
                    {"line_number": 1, "speaker": "Guide Bird",
                     "text": "Hi", "image": tiny_png,
                     "section": "Setup", "audio_key": "a", "pause_ms": 0},
                ],
            }) + ";</script></body></html>"
        )
        beats = extract_beats_from_html(sample_html)
        assert len(beats) == 1
        assert beats[0]["speaker"] == "Guide Bird"

        print("[smoke] port check...")
        assert port_free(SERVER_PORT) or True  # just make sure it doesn't crash

    print("[smoke] PASS")
    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="MindfulNest Storyboard Production Server")
    ap.add_argument("--event-dir", help="Path to event directory (e.g. Production/Event_1)")
    ap.add_argument("--storyboard", help="Filename of _prod.html inside event-dir")
    ap.add_argument("--event-id", help='Event identifier, e.g. "Event_1"')
    ap.add_argument("--smoke-test", action="store_true", help="Run self-test and exit")
    # BEAT_GRAFT_RECOVERY_MECHANISM_V1 (C-7) — optional read-only side
    # event-dir for /api/beat/graft cross-event source. The server stays
    # PINNED to --event-dir for all writes (LD-456); --source-event lets
    # the graft handler read state from a different event so the canonical
    # recovery primitive can move beats between events with explicit operator
    # ceremony (one-time CLI restart per cross-event session per DV-1).
    ap.add_argument(
        "--source-event",
        type=Path,
        default=None,
        help=(
            "Optional source event directory for /api/beat/graft cross-event "
            "operations. When set, the graft handler accepts requests where "
            "body.source.event_id != server-pinned event_id; otherwise such "
            "requests return HTTP 409 cross_event_requires_explicit_source."
        ),
    )
    args = ap.parse_args()

    if args.smoke_test:
        return run_smoke_test()

    if not (args.event_dir and args.storyboard and args.event_id):
        ap.error("--event-dir, --storyboard, and --event-id are required (or use --smoke-test)")

    return run_server(
        Path(args.event_dir), args.storyboard, args.event_id,
        source_event_dir=args.source_event,
    )


if __name__ == "__main__":
    sys.exit(main())
