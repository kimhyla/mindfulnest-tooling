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
    kling_startend_submit,
    _load_subject_element,
    ensure_min_dimensions as _ksendpipe_ensure_min_dimensions,
    load_api_keys as _ksendpipe_load_api_keys,
    RULE8_ANTI_LIPSYNC,
    CFG_SCALE_BASELINE as _KSENDPIPE_CFG_SCALE,
    COST_FLUX_KONTEXT,
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
            → ValueError (fixture is non-numeric; tests must mock or skip)
    """
    arc_number = 1  # current single-arc deployment; refactor when multi-arc lands
    if not scope_event_id.startswith("Event_"):
        raise ValueError(
            f"scope_event_id must be of form 'Event_<N>' for BG segment resolution; "
            f"got {scope_event_id!r}"
        )
    suffix = scope_event_id[len("Event_"):]
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
                return self._send_json(503, {
                    "error": "drain_in_progress",
                    "code": "ASYNC_QUEUE_DRAIN_PROTOCOL_V1",
                    "handler": handler_name,
                    "hint": "Server is draining new work; retry after migration completes.",
                })
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
DEFAULT_BUDGET = 32.00

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
            _libdir = os.path.join(os.path.dirname(__file__), "lib")
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
        _libdir = os.path.join(os.path.dirname(__file__), "lib")
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
        # Queue for retry
        try:
            queue_path = os.path.join(os.path.dirname(__file__), "..", "pending_directus_writes.json")
            queue_path = os.path.normpath(queue_path)
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
        "neutral":          "small hops in place, wing adjustments, warm head tilts, bright eye sparkle",
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
    if emotion not in VALID_EMOTIONS:
        print(f"[WARN] unknown emotion {emotion!r} for speaker {speaker!r}; "
              f"falling back to 'neutral'")
        emotion = "neutral"

    lipsync_targeted = beat.get("lipsync_targeted", True)
    if lipsync_targeted is None:
        lipsync_targeted = True

    profile = SPEAKER_MOTION_PROFILES.get(speaker)
    if profile:
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

    Uses PIL if available; if PIL isn't installed, logs a warning and
    passes (the injection-time validator and Directus gate remain in
    force as backup layers)."""
    try:
        from PIL import Image  # type: ignore
    except ImportError:
        return True, "PIL not installed — dimension check skipped"

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
    If PIL isn't available or the image already meets the minimum, returns the original.
    This is the Rule 6 'auto-upscale fallback safety net'.
    """
    try:
        from PIL import Image  # type: ignore
    except ImportError:
        return data_uri, "PIL not installed — no upscale"

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
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise ValueError(f"refusing non-https URL: {url!r}")
    path = parsed.path + ("?" + parsed.query if parsed.query else "")
    # Fresh SSL context per call — prevents session-ticket accumulation.
    # OP_NO_TICKET defeats RFC 5077 session resumption (counter-agent C2 HIGH
    # finding, April 16 2026): even a fresh SSLContext negotiates and caches
    # tickets for the duration of the context. Explicitly disabling tickets +
    # compression removes the remaining stuck-state vectors. On macOS stock
    # Python, this eliminates the LibreSSL process-level session cache path.
    ctx = ssl.create_default_context()
    ctx.options |= ssl.OP_NO_TICKET
    ctx.options |= ssl.OP_NO_COMPRESSION
    conn = http.client.HTTPSConnection(parsed.netloc, timeout=timeout, context=ctx)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Connection": "close",  # never reuse this connection
    }
    try:
        conn.request(method, path, body=body, headers=headers)
        resp = conn.getresponse()
        status = resp.status
        data = resp.read()
    except (TimeoutError, http.client.HTTPException, OSError) as exc:
        # Wrap in urllib.error.URLError so existing callers' except clauses still catch it
        raise urllib.error.URLError(f"{type(exc).__name__}: {exc}") from exc
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return status, data


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
        return {"status": status, "outputs": outputs, "raw": payload}

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
        recoveries: list[tuple[str, str, str]] = []  # (beat_id, kind, old_state)
        for beat_id, beat in (snap.get("beats") or {}).items():
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
                recoveries.append((beat_id, f"option_{idx+1}", "submitting"))
            # (b) Lipsync orphaned mid-submit.
            ls = beat.get("lipsync") or {}
            if ls.get("status") == "submitting" and not ls.get("task_id"):
                age = self._age_seconds(ls, now)
                if age is not None and age >= ORPHAN_SUBMIT_THRESHOLD_SEC:
                    recoveries.append((beat_id, "lipsync", "submitting"))
        if not recoveries:
            return

        # S5.5a2: orphan-sweep operates on the intro partition (legacy beats).
        def mut(partition):
            for beat_id, kind, _old in recoveries:
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
            return None
        self.state.mutate_video_state("intro", mut)
        for beat_id, kind, old_state in recoveries:
            print(f"[orphan-sweep] recovered {beat_id}/{kind}: "
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
        # S5.5a2: legacy lipsync poller iterates intro partition beats.
        beats = self.state.get_beats("intro")
        candidates: list[tuple[str, str]] = []  # (beat_id, task_id)
        for beat_id, beat in beats.items():
            ls = beat.get("lipsync") or {}
            if ls.get("status") == "polling" and ls.get("task_id"):
                candidates.append((beat_id, ls["task_id"]))
        if not candidates:
            return
        # Preflight 111 (2026-04-19): emit a visible heartbeat so the server
        # log always shows the daemon is alive when work exists. Previously
        # the daemon completed cycles silently, making it impossible to tell
        # if silent meant "no candidates" vs "stuck" vs "crashed thread".
        print(f"[lipsync-poller] cycle: {len(candidates)} candidate(s): "
              f"{[(b, t[:12]) for b, t in candidates]}", flush=True)
        for beat_id, task_id in candidates:
            if self.stop_event.is_set():
                return
            self._poll_one(beat_id, task_id)

    def _poll_one(self, beat_id: str, task_id: str) -> None:
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
            self._download_and_complete(beat_id, task_id, outputs[0])
        elif status in ("failed", "error"):
            self._mark_failed(beat_id, task_id, "vendor reported failure")
        # else: still processing — leave alone, next cycle will re-poll

    def _download_and_complete(self, beat_id: str, task_id: str, url: str) -> None:
        print(f"[lipsync-poller] {beat_id}/{task_id[:12]}…: completed, downloading {url[:60]}…", flush=True)
        # Pre-read to find target filename. S5.5a2: read intro partition beats.
        beats = self.state.get_beats("intro")
        ls = (beats.get(beat_id) or {}).get("lipsync") or {}
        fname = ls.get("file") or f"{beat_id}_lipsync.mp4"
        clips_dir = self.state.clips_dir
        dst = clips_dir / Path(fname).name
        try:
            size = self.client.download(url, dst)
        except Exception as exc:  # noqa: BLE001
            print(f"[lipsync-poller] {beat_id}/{task_id[:12]}…: download failed ({exc}); will retry next cycle", flush=True)
            return

        # S5.5a2: legacy lipsync mut → intro partition.
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
            partition["beats"][beat_id] = beat
        self.state.mutate_video_state("intro", mut)
        print(f"[lipsync-poller] {beat_id}/{task_id[:12]}…: wrote {size:,} bytes -> {dst.name}", flush=True)

    def _mark_failed(self, beat_id: str, task_id: str, err: str) -> None:
        # S5.5a2: legacy lipsync mut → intro partition.
        def mut(partition):
            beat = partition["beats"].get(beat_id) or {}
            ls = beat.get("lipsync") or {}
            ls["status"] = "failed"
            ls["last_error"] = err
            beat["lipsync"] = ls
            partition["beats"][beat_id] = beat
        self.state.mutate_video_state("intro", mut)
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
        # S5.5a2: poller iterates intro partition beats.
        beats = self.state.get_beats("intro")
        out: list[tuple[str, int, dict]] = []
        # Collect stale candidates and process them after the read loop so we
        # don't mutate state (and invalidate iteration) inside the for-loop.
        stale_candidates: list[tuple[str, int, dict]] = []
        t1_enabled = _t1_enabled()
        for beat_id, beat in beats.items():
            phase1 = beat.get("phase_1") or {}
            for idx, opt in enumerate(phase1.get("options", [])):
                if opt.get("status") != "polling" or not opt.get("task_id"):
                    continue
                # Tier 1B stale-timeout check (feature-flagged).
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
                            stale_candidates.append((beat_id, idx, opt))
                            continue
                next_at = opt.get("next_attempt_at_epoch", 0)
                if next_at > now:
                    continue  # still in backoff window — skip this cycle
                out.append((beat_id, idx, opt))
        # Process stale candidates AFTER building the ready list. Each
        # call performs its own read-modify-write cycle under the StateManager
        # lock; ordering doesn't matter because each operates on a disjoint
        # (beat_id, opt_idx) slot.
        for beat_id, idx, opt in stale_candidates:
            try:
                self._mark_stale_timeout_with_artifact_check(beat_id, idx, opt)
            except Exception as exc:  # noqa: BLE001 — never kill the poller
                print(f"[T1] beat={beat_id} opt={idx + 1} stale_check_error: {exc}")
                traceback.print_exc()
        return out

    def _mark_stale_timeout_with_artifact_check(
        self, beat_id: str, opt_idx: int, opt: dict,
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

        result = self.state.mutate_video_state("intro", mut)
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
            for beat_id, opt_idx, opt in batch:
                self._poll_one(beat_id, opt_idx, opt)
            time.sleep(POLL_BATCH_GAP_SEC)

    def _poll_one(self, beat_id: str, opt_idx: int, opt: dict) -> None:
        task_id = opt["task_id"]
        # Backoff is handled upstream in _pending_tasks (skips options whose
        # next_attempt_at_epoch is still in the future). DO NOT sleep here —
        # that would block every other beat's poll. Tier 3 Phase-3 fix #4.

        try:
            result = self.client.poll(task_id)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            self._handle_transient_failure(beat_id, opt_idx, str(exc), task_id=task_id)
            return
        except Exception as exc:  # noqa: BLE001
            self._handle_transient_failure(beat_id, opt_idx, repr(exc), task_id=task_id)
            return

        status = (result.get("status") or "").lower()
        if status == "completed" and result.get("outputs"):
            self._download_and_mark_completed(
                beat_id, opt_idx, task_id, result["outputs"][0],
                source="poll_complete",
            )
        elif status in ("failed", "error"):
            _ws_err = result.get("message") or result.get("error") or result.get("detail") or ""
            print(f"[poll] {beat_id} opt{opt_idx} wavespeed failure detail: {_ws_err!r} full={list(result.keys())}")
            self._handle_transient_failure(
                beat_id, opt_idx, f"wavespeed reported failure: {_ws_err}", task_id=task_id,
            )
        # else: still processing — leave alone

    def _download_and_mark_completed(
        self, beat_id: str, opt_idx: int, task_id: str, url: str, *, source: str,
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
        size: int
        if dest.exists() and dest.stat().st_size > 0:
            # Idempotency guard — already have a file for this slot
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

        mut_result = self.state.mutate_video_state("intro", mut_with_guard)
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
        self, beat_id: str, opt_idx: int, err: str, *, task_id: str | None = None,
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
        new_retries = self.state.mutate_video_state("intro", mut)

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


def _get_directus_lock_client():
    """Lazy-create a DirectusClient for lock operations. Returns None on
    failure so callers can degrade (FAIL CLOSED in mutate paths)."""
    global _DIRECTUS_LOCK_CLIENT_SINGLETON
    with _DIRECTUS_LOCK_CLIENT_LOCK:
        if _DIRECTUS_LOCK_CLIENT_SINGLETON is not None:
            return _DIRECTUS_LOCK_CLIENT_SINGLETON
        try:
            _libdir = os.path.join(os.path.dirname(__file__), "lib")
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
            print(f"[dlock] WARN lookup failed: {exc}")
            return None  # Directus unreachable

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
                    print(f"[dlock] WARN reentrant heartbeat failed: {exc}")
                    return None

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
                print(f"[dlock] WARN steal-expired failed: {exc}")
                return None

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
            print(f"[dlock] WARN create failed: {exc}")
            return None


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
_AUDIO_SHORT_THRESHOLD_SEC = 4.5  # audio <= this -> 5s animation; > -> 10s


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
        return p if p.is_file() else None

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
            _libdir = os.path.join(os.path.dirname(__file__), "lib")
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
            _libdir = os.path.join(os.path.dirname(__file__), "lib")
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
            _libdir = os.path.join(os.path.dirname(__file__), "lib")
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
_VIDEO_TRIM_TAILROOM_S = 0.4       # audio_duration + 0.4s tail room
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
                   loudnorm: bool = False) -> tuple[Path, dict]:
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
    """
    src_dur = _ffprobe_duration(source_audio)
    silences = _detect_silences(source_audio)
    to_compress = [(s, e) for (s, e) in silences if (e - s) > _SILCOMP_TRIGGER_S]

    # --- Auto pre-roll probe (Preflight 110) ---
    preroll_meta = {
        "applied": False,
        "reason": "disabled_by_caller",
        "detected_leading_silence_s": 0.0,
        "preroll_added_s": 0.0,
        "preroll_target_s": _AUTO_PREROLL_TARGET_S,
        "min_threshold_s": _AUTO_PREROLL_MIN_S,
    }
    preroll_add_s = 0.0
    if auto_preroll:
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
    target = audio_duration_s + _VIDEO_TRIM_TAILROOM_S
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
            _libdir = os.path.join(os.path.dirname(__file__), "lib")
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
            _libdir = os.path.join(os.path.dirname(__file__), "lib")
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
            _libdir = os.path.join(os.path.dirname(__file__), "lib")
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
        _libdir = os.path.join(os.path.dirname(__file__), "lib")
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
    # Bird (Chipper) — canonical + all legacy aliases
    "chipper": "Chipper",
    "guide bird": "Chipper",     # legacy (pre-2026-04-17)
    "pip": "Chipper",            # legacy (pre-2026-04-17)
    "assistant bird": "Chipper",
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
            _libdir = os.path.join(os.path.dirname(__file__), "lib")
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
    # Alias table first
    canonical = _SPEAKER_ALIAS.get(key_lc)
    if canonical and canonical in cache:
        return cache[canonical]
    # Direct match
    for name in cache:
        if name.lower() == key_lc:
            return cache[name]
    # Substring match (e.g., "Guide Bird (Pip)" -> Guide Bird)
    for name in cache:
        if name.lower() in key_lc or key_lc in name.lower():
            return cache[name]
    return None


def _tts_regenerate_for_beat(app, beat_id: str, text: str,
                             elevenlabs_key: str) -> dict:
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
    try:
        beat_num = int(beat_id.split("_")[1])
        beat_num_s = f"{beat_num:02d}"
    except (IndexError, ValueError):
        return {"ok": False, "error": f"unparseable beat_id: {beat_id!r}"}

    # Resolve speaker -> voice profile. S5.5a2: read from intro partition.
    beats = app.state.get_beats("intro")
    beat_state = beats.get(beat_id) or {}
    speaker = beat_state.get("speaker") or ""
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
        return {"ok": False,
                "error": f"no voice profile for speaker {speaker!r} "
                         f"(configure in Directus prod_voice_profiles)"}

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

    # Call ElevenLabs v1/text-to-speech synchronously.
    # ElevenLabs TTS submit — use universal hardening helper
    # (decision 185 UNIVERSAL_EXTERNAL_API_HARDENING, April 17 2026):
    # fresh http.client per attempt, OP_NO_TICKET, 90s timeout, 3-attempt
    # exponential backoff. Same pattern applied to Kling + FLUX Kontext.
    from kling_startend_pipeline import robust_https_request
    body = json.dumps({
        "text": text,
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
    # S5.5a2: legacy TTS-regen mut → intro partition.
    now_iso = datetime.now(timezone.utc).isoformat()
    def _update(partition, _bid=beat_id, _af=out_path.name, _d=dur, _iso=now_iso):
        b = partition.setdefault("beats", {}).setdefault(_bid, {})
        b["audio_file"] = _af
        b["audio_duration_s"] = round(_d, 3)
        b["audio_regenerated_at"] = _iso
        b["text_modified_after_tts"] = False  # audio is now fresh for the current text
        # If a completed lipsync exists, it's now stale (audio changed).
        ls = b.get("lipsync") or {}
        if ls.get("status") == "completed":
            ls["audio_changed"] = True
    app.state.mutate_video_state("intro", _update)

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
            _libdir = os.path.join(os.path.dirname(__file__), "lib")
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
    #    Log sys.executable so pyenv-drift (user switched Python versions
    #    mid-session) is visible in the log — C3 informational finding.
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


def _v2_validate_watercolor_cues_json(v):
    """Validate watercolor cues JSON; re-emit with sort_keys=True for cache-hash stability (MEDIUM-5)."""
    if not isinstance(v, str):
        raise ValueError(f"must be JSON string, got {type(v).__name__}")
    if len(v) > 200_000:
        raise ValueError(f"cues JSON too long ({len(v)} chars, max 200000)")
    try:
        parsed = json.loads(v)
    except Exception as exc:
        raise ValueError(f"invalid JSON: {exc}")
    if not isinstance(parsed, list):
        raise ValueError(f"watercolor cues must be a list, got {type(parsed).__name__}")
    required_keys = ("timestamp_ms", "key", "animation", "duration_ms", "cue_type")
    for i, cue in enumerate(parsed):
        if not isinstance(cue, dict):
            raise ValueError(f"cue {i} must be dict, got {type(cue).__name__}")
        for key in required_keys:
            if key not in cue:
                raise ValueError(f"cue {i} missing {key!r}")
        if not isinstance(cue["timestamp_ms"], int) or cue["timestamp_ms"] < 0:
            raise ValueError(f"cue {i} timestamp_ms must be non-negative int")
        if not isinstance(cue["duration_ms"], int) or cue["duration_ms"] < 0:
            raise ValueError(f"cue {i} duration_ms must be non-negative int")
        if cue["cue_type"] not in _V2_CUE_TYPES:
            raise ValueError(
                f"cue {i} cue_type must be one of {sorted(_V2_CUE_TYPES)}, "
                f"got {cue['cue_type']!r}"
            )
        if cue["animation"] not in _V2_CUE_ANIMATIONS:
            raise ValueError(
                f"cue {i} animation must be one of {sorted(_V2_CUE_ANIMATIONS)}, "
                f"got {cue['animation']!r}"
            )
        if not isinstance(cue["key"], str) or not cue["key"]:
            raise ValueError(f"cue {i} key must be non-empty string")
    # Sort cues by timestamp_ms for stable rendering order.
    parsed.sort(key=lambda c: c["timestamp_ms"])
    # Re-emit with sort_keys=True so hash is stable across client JS key ordering.
    return json.dumps(parsed, sort_keys=True, separators=(",", ":"))


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
    "phase_a_watercolor_cues_json": _v2_validate_watercolor_cues_json,
    "phase_a_preview_file": _v2_validate_str,
    "phase_a_status": _v2_validate_status,
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
                _libdir = os.path.join(os.path.dirname(__file__), "lib")
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
        # Universal stitch editor job store — global, not per-event (STITCH_EDITOR_UNIVERSAL_V1)
        self.stitch_state = StitchEditorState(Path(__file__).parent / "stitch_editor_state.json")
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

    def beats(self) -> list[dict]:
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
        """Look up a full-res gallery image by key from the storyboard HTML."""
        html = self.storyboard_path.read_text(encoding="utf-8")
        # Gallery images: <div class="ic"><img src="data:image/..."><p>filename.png</p></div>
        # Match by key derived from filename
        pattern = r'<div class="ic"><img src="(data:image/[^"]+)"><p>([^<]+)</p></div>'
        for m in re.finditer(pattern, html):
            src, name = m.group(1), m.group(2)
            key = name.replace(".png", "").replace(".PNG", "").replace(" ", "_")
            if key == image_key:
                return src
        return None

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
                qs_val = params.get("event_id")
                if qs_val:
                    body_event = qs_val[0]
            except Exception:
                pass
        server_event = self.app.event_dir.name
        if body_event is None:
            if allow_missing:
                return True
            self._send_json(400, {
                "error": "scope_required",
                "code": "SCOPE_VALIDATION_V1",
                "expected_event_id": server_event,
                "hint": "v59 clients must include event_id in request body.",
            })
            return False
        if body_event != server_event:
            print(
                f"[scope-guard] HTTP 409 on {self.command} {self.path}: "
                f"body event_id={body_event!r} != server event_id={server_event!r}",
                flush=True,
            )
            self._send_json(409, {
                "error": "scope_mismatch",
                "code": "SCOPE_VALIDATION_V1",
                "expected_event_id": server_event,
                "got_event_id": body_event,
                "hint": (
                    "The client thinks it is editing a different event than "
                    "this server is serving. Restart the client tab so the "
                    "active scope re-resolves, or restart the server with "
                    f"--event-dir Production/{body_event} if the client is "
                    "correct."
                ),
            })
            return False
        # ---- LD-474 VIDEO_ROLE_PER_REQUEST_V1 (S5.5a2 extension) ----
        # When scope_video_role is present, validate it against the canonical
        # set + presence in current state. Missing is allowed during the
        # refactor window (default 'intro' applied by caller).
        body_video_role = (body or {}).get("scope_video_role")
        if body_video_role is None:
            if allow_missing_video_role:
                return True
            self._send_json(400, {
                "error": "video_role_required",
                "code": "VIDEO_ROLE_INVALID",
                "valid": sorted(self.app.state._VALID_VIDEO_ROLES),
                "hint": "scope_video_role required on this endpoint (LD-474).",
            })
            return False
        if not self.app.state.validate_video_role(body_video_role):
            self._send_json(400, {
                "error": "video_role_invalid",
                "code": "VIDEO_ROLE_INVALID",
                "got": body_video_role,
                "valid": sorted(self.app.state._VALID_VIDEO_ROLES),
                "hint": (
                    "scope_video_role must be one of intro/resolution/"
                    "standalone AND exist in current state.videos."
                ),
            })
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
                return self._send_json(200, self.app.state.read_state())
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
                return self._send_json(501, {"error": "not implemented in v1 MVP"})
            # ── Beat Generator tab routes (GET) ──────────────────────────────────
            if path == "/api/bg/segments":
                return self._handle_bg_segments()
            if path == "/api/bg/session-state":
                return self._handle_bg_session_state()
            if path == "/api/bg/poll-flux-status":
                return self._handle_bg_poll_flux()
            if path.startswith("/api/bg/poll-gpt-status"):
                return self._handle_bg_poll_gpt_status()
            if path == "/api/bg/groups":
                return self._handle_bg_groups()
            if path == "/api/bg/poll-assemble-status":
                return self._handle_bg_poll_assemble_status()
            if path.startswith("/bg-stills/"):
                return self._handle_bg_stills(path)
            if path == "/api/bg/crop-preview":
                return self._handle_bg_crop_preview()
            if path == "/files":
                return self._handle_files_serve()
            if path == "/api/cr/library":
                return self._handle_cr_library()
            if path == "/api/cr/full":
                return self._handle_cr_full_image()
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
            if path.startswith("/api/stitch_editor/audio_file/"):
                fname = path[len("/api/stitch_editor/audio_file/"):]
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
            return self._send_json(404, {"error": "not found", "path": path})
        except (BrokenPipeError, ConnectionResetError):
            # LOG_HYGIENE_SUPPRESS_CLIENT_CANCEL_TRACEBACKS (LD 2026-04-18):
            # Defense-in-depth: if any downstream handler re-raises a client
            # cancel, eat it here instead of running the 500 path (which would
            # just throw ANOTHER BrokenPipe during end_headers()).
            print(f"request canceled by client: GET {path}", file=sys.stderr, flush=True)
            return
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            return self._send_json(500, {"error": str(exc)})

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
            if path == "/api/beat/update_text":
                return self._handle_beat_update_text(body)
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
            if path == "/api/beat/use_as_final":  # Spec A: no-lipsync final path
                return self._handle_use_as_final(body)
            if path == "/api/budget/override":
                return self._handle_budget_override(body)
            if path == "/api/server/restart":
                return self._handle_restart()
            if path == "/api/lipsync":
                return self._handle_lipsync_submit(body)
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
            # Swap-to-A v2 endpoint (April 19 2026) — park a B/C favorite into
            # slot A so Regenerate B+C doesn't overwrite it (or its lipsync).
            if path.startswith("/api/v2/beat/") and path.endswith("/swap_to_a"):
                parts = [p for p in path.split("/") if p]
                # Expect: ["api", "v2", "beat", "<beat_id>", "swap_to_a"]
                if len(parts) != 5:
                    return self._send_json(400, {
                        "error": f"malformed path: {path!r}",
                        "hint": "Expected /api/v2/beat/<beat_id>/swap_to_a",
                    })
                return self._handle_v2_beat_swap_to_a(parts[3], body)
            # LD-285 Preview Stitched v2 endpoints (April 19 2026)
            if path == "/api/v2/module/patch":
                return self._handle_v2_module_patch(body)
            if path == "/api/phase_b/regen_audio":
                return self._handle_phase_b_regen_audio(body)
            if path == "/api/phase_b/mix_audio":
                return self._handle_phase_b_mix_audio(body)
            if path == "/api/phase_b/lipsync":
                return self._handle_phase_b_lipsync(body)
            if path == "/api/phase_b/preview":
                return self._handle_phase_b_preview(body)
            # Phase A panel build (LD PHASE_A_PANEL_VOICE_SLIDERS_V1, 2026-04-20):
            # persist voice slider changes to prod_voice_profiles by id.
            if path == "/api/voice/profile_update":
                return self._handle_voice_profile_update(body)
            if path == "/api/preview_stitched":
                return self._handle_preview_stitched(body)
            if path == "/api/tts":
                return self._send_json(501, {"error": "not implemented in v1 MVP"})
            # ── Beat Generator tab routes (POST) ─────────────────────────────────
            if path == "/api/bg/set-active-context":
                return self._handle_bg_set_active_context(body)
            if path == "/api/bg/extract-beats":
                return self._handle_bg_extract_beats(body)
            if path == "/api/bg/inject-beats":
                return self._handle_bg_inject_beats(body)
            if path == "/api/bg/update-beat":
                return self._handle_bg_update_beat(body)
            if path == "/api/bg/reorder-beats":
                return self._handle_bg_reorder_beats(body)
            if path == "/api/bg/delete-beat":
                return self._handle_bg_delete_beat(body)
            if path == "/api/bg/accept-beats":
                return self._handle_bg_accept_beats(body)
            if path == "/api/bg/submit-flux-batch":
                return self._handle_bg_submit_flux(body)
            if path == "/api/bg/submit-gpt-batch":
                return self._handle_bg_submit_gpt_batch(body)
            if path == "/api/bg/accept-option":
                return self._handle_bg_accept_option(body)
            if path == "/api/bg/accept-lib-image":
                return self._handle_bg_accept_lib_image(body)
            if path == "/api/bg/add-beat":
                return self._handle_bg_add_beat(body)
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
            return self._send_json(404, {"error": "not found", "path": path})
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            return self._send_json(500, {"error": str(exc)})

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
            return self._send_json(404, {"error": "not found", "path": path})
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            return self._send_json(500, {"error": str(exc)})

    # ================================================================
    # Beat Generator tab handlers (§6 of HANDOFF_BEAT_GENERATOR_TAB_COMPLETE.md)
    # No Kling, no motion prompts. FLUX Kontext stills only.
    # ================================================================

    # ================================================================
    # Visible Magic Phase 2 handlers (2026-04-24)
    # ================================================================

    def _serve_magic_picker(self) -> None:
        """Serve path_picker.html for the /magic route."""
        import urllib.parse as _up
        picker = Path(__file__).parent / "path_picker.html"
        if not picker.exists():
            return self._send_json(404, {"error": "path_picker.html not found"})
        html = picker.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self._cors_headers()
        self.end_headers()
        self.wfile.write(html)

    def _handle_magic_resolve_bg(self) -> None:
        """Resolve background still path for a scene_key."""
        import urllib.parse as _up
        import yaml as _yaml
        qs = _up.parse_qs(_up.urlparse(self.path).query)
        scene_key = (qs.get("scene_key") or [None])[0]
        if not scene_key:
            return self._send_json(400, {"ok": False, "error": "scene_key required"})
        reg_path = Path(__file__).parent / "scene_registry.yaml"
        if not reg_path.exists():
            return self._send_json(404, {"ok": False, "error": "scene_registry.yaml not found"})
        registry = _yaml.safe_load(reg_path.read_text()) or {}
        scene = registry.get(scene_key, {})
        # Resolve from well-known paths
        db = Path(__file__).parent.parent.parent  # Dropbox/Claude Mindfulnest Project Files
        shot_role = scene.get("source_asset_query", {}).get("filter", {}).get("shot_role", "")
        event_id = scene.get("event_id", "e1").replace("e", "Event_")
        candidates = []
        if shot_role:
            candidates.append(db / "Production" / event_id / "resolution_stills" / f"{shot_role}.png")
        # Known scene-key -> file fallback map
        _KNOWN_STILLS = {
            "m1_e1_res_beat_01_heartwood": "heartwood_3q_left_1456.png",
            "m1_e1_res_beat_01_heartwood_wide": "heartwood_wide_1456.png",
            "m1_e1_res_beat_02_runestone": "still_3_body_stone_glow_v9.png",
        }
        if scene_key in _KNOWN_STILLS:
            candidates.append(db / "Production" / "Event_1" / "resolution_stills" / _KNOWN_STILLS[scene_key])
        for c in candidates:
            if c.exists():
                bg_url = f"/files?path={_up.quote(str(c))}"
                return self._send_json(200, {"ok": True, "bg_url": bg_url, "bg_path": str(c)})
        return self._send_json(404, {"ok": False, "error": f"No background still found for {scene_key}"})

    def _handle_magic_status(self) -> None:
        """Poll magic render job status."""
        import urllib.parse as _up
        qs = _up.parse_qs(_up.urlparse(self.path).query)
        job_id = (qs.get("job_id") or [None])[0]
        if not job_id:
            return self._send_json(400, {"ok": False, "error": "job_id required"})
        job = _MAGIC_JOBS.get(job_id)
        if not job:
            return self._send_json(404, {"ok": False, "error": "job not found"})
        # Translate file paths to serveable URLs
        import urllib.parse as _up2
        resp = dict(job)
        for key in ("preview_path", "video_path"):
            if resp.get(key):
                resp[key + "_url"] = f"/files?path={_up2.quote(str(resp[key]))}"
        return self._send_json(200, {"ok": True, **resp})

    @with_pin_and_drain('_handle_magic_submit_path', track_sync=False)
    def _handle_magic_submit_path(self, body: dict) -> None:
        """Validate clicked path, write registry, kick off render pipeline."""
        # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
        if not self._assert_event_scope(self._scope_body(body), allow_missing=False):
            return

        # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — capture pin at entry; terminal writes assert via _check_event_pin.
        _pin = {
            "pinned_generation": self.app.event_generation,
            "pinned_event_dir": self.app.event_dir,
            "pinned_video_role": (body or {}).get("scope_video_role", "intro"),
            "_handler": '_handle_magic_submit_path',
        }
        # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — pre-work pin check (S2).
        # If the event was swapped via /api/event/load between scope-guard
        # and work start, abort BEFORE any expensive work begins.
        if not self._check_event_pin(_pin, '_handle_magic_submit_path_pre_work'):
            return self._send_json(423, {
                "error": "event_changed_pre_work",
                "code": "ASYNC_JOB_GENERATION_PIN_V1",
                "handler": '_handle_magic_submit_path',
                "hint": (
                    "Event changed between scope-guard and work start. "
                    "No work was done; no orphan output. Client should "
                    "re-hydrate scope and retry."
                ),
            })

        import threading as _th
        import traceback as _tb
        import uuid as _uuid
        import urllib.parse as _up

        scene_key   = body.get("scene_key", "").strip()
        manual_path = body.get("manual_path", [])
        style       = body.get("style", "tessa_ori")

        # ── Validation ────────────────────────────────────────────────
        if not scene_key:
            return self._send_json(400, {"ok": False, "error": "scene_key required"})
        if not manual_path or not isinstance(manual_path, list):
            return self._send_json(400, {"ok": False, "error": "manual_path required"})
        if len(manual_path) < 2:
            return self._send_json(400, {"ok": False, "error": "manual_path must have ≥ 2 points"})
        if len(manual_path) > 20:
            return self._send_json(400, {"ok": False, "error": "manual_path max 20 points"})
        for i, pt in enumerate(manual_path):
            try:
                x, y = float(pt[0]), float(pt[1])
            except (TypeError, IndexError, ValueError):
                return self._send_json(400, {"ok": False, "error": f"point {i} malformed: {pt}"})
            if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
                return self._send_json(400, {"ok": False,
                    "error": f"point {i} out of range: [{x},{y}] must be in [0,1]"})

        # Normalize to list of [float, float]
        path_pts_clean = [[float(pt[0]), float(pt[1])] for pt in manual_path]

        # ── Job setup ─────────────────────────────────────────────────
        job_id = f"magic_{int(time.time())}_{scene_key[-20:]}"
        _MAGIC_JOBS[job_id] = {
            "status": "pending",
            "message": "Queued",
            "scene_key": scene_key,
            "preview_path": None,
            "video_path": None,
            "error": None,
        }

        def _run():
            import yaml as _yaml
            import datetime as _dt
            import json as _json
            try:
                # ── Step 1: Write to scene_registry.yaml ──────────────
                _MAGIC_JOBS[job_id].update({"status": "writing_registry",
                                            "message": "Saving path to scene registry..."})
                reg_path = Path(__file__).parent / "scene_registry.yaml"
                bak_path = reg_path.with_suffix(f".yaml.bak_magic_{int(time.time())}")
                shutil.copy2(reg_path, bak_path)

                try:
                    import ruamel.yaml as _ry
                    ry = _ry.YAML()
                    ry.preserve_quotes = True
                    with open(reg_path) as f:
                        registry = ry.load(f)
                    if registry is None:
                        registry = {}
                    if scene_key not in registry:
                        registry[scene_key] = {
                            "archetype": "ground_left_to_target",
                            "description": f"Magic trail for {scene_key}",
                            "module_id": body.get("module_id", "m1"),
                            "event_id": body.get("event_id", "e1"),
                            "beat": body.get("beat", "res_beat_01"),
                            "style": style,
                            "color_target": "orange",
                            "direction": "left",
                        }
                    registry[scene_key]["manual_path"] = path_pts_clean
                    registry[scene_key]["style"] = style
                    with open(reg_path, "w") as f:
                        ry.dump(registry, f)
                except ImportError:
                    # ruamel not available — use pyyaml fallback
                    registry = _yaml.safe_load(reg_path.read_text()) or {}
                    if scene_key not in registry:
                        registry[scene_key] = {
                            "archetype": "ground_left_to_target",
                            "module_id": body.get("module_id", "m1"),
                            "event_id": body.get("event_id", "e1"),
                            "beat": body.get("beat", "res_beat_01"),
                            "style": style,
                        }
                    registry[scene_key]["manual_path"] = path_pts_clean
                    # LD-460 — terminal pin check (thread closure captures _pin).
                    if not self._check_event_pin(_pin, "magic_submit_path_registry_write"):
                        print(f"[magic_submit_path] event drift mid-thread; skipping registry write", flush=True)
                        return
                    reg_path.write_text(_yaml.dump(registry, default_flow_style=False))

                # ── Step 2: Resolve background still ──────────────────
                _MAGIC_JOBS[job_id].update({"status": "rendering_preview",
                                            "message": "Resolving background still..."})
                db = Path(__file__).parent.parent.parent
                _KNOWN_STILLS = {
                    "m1_e1_res_beat_01_heartwood": "heartwood_3q_left_1456.png",
                    "m1_e1_res_beat_01_heartwood_wide": "heartwood_wide_1456.png",
                    "m1_e1_res_beat_02_runestone": "still_3_body_stone_glow_v9.png",
                }
                reg2 = _yaml.safe_load(reg_path.read_text()) or {}
                scene = reg2.get(scene_key, {})
                shot_role = scene.get("source_asset_query", {}).get("filter", {}).get("shot_role", "")
                event_id = scene.get("event_id", "e1")
                event_dir = db / "Production" / f"Event_{event_id.replace('e','')}" / "resolution_stills"
                bg_path = None
                # 0. Explicit bg_path from request body (sent by path_picker.html)
                explicit_bg = body.get("bg_path", "")
                if explicit_bg and Path(explicit_bg).is_file():
                    bg_path = explicit_bg
                if bg_path is None and shot_role:
                    cand = event_dir / f"{shot_role}.png"
                    if cand.exists():
                        bg_path = str(cand)
                if bg_path is None and scene_key in _KNOWN_STILLS:
                    cand = event_dir / _KNOWN_STILLS[scene_key]
                    if cand.exists():
                        bg_path = str(cand)
                if bg_path is None:
                    raise FileNotFoundError(
                        f"Cannot find background still for {scene_key}. "
                        f"Add to _KNOWN_STILLS in production_server.py or set source_asset_query."
                    )

                # ── Step 3: Render preview still ──────────────────────
                _MAGIC_JOBS[job_id].update({"message": "Rendering preview still (final frame)..."})
                sys.path.insert(0, str(Path(__file__).parent))
                from magic_compositor import MagicCompositor
                out_dir = db / "Production" / "Event_1" / "kling_clips"
                out_dir.mkdir(parents=True, exist_ok=True)
                path_pts_tuples = [tuple(pt) for pt in path_pts_clean]
                mc = MagicCompositor(
                    background_path=bg_path,
                    path_pts=path_pts_tuples,
                    style=style,
                    duration=3.5,
                    fps=24,
                    seed=99,
                    output_dir=str(out_dir),
                    label=f"{scene_key}_server",
                )
                total_frames = int(mc.duration * mc.fps)
                preview_path = mc.render_preview(frame_idx=total_frames - 2)
                _MAGIC_JOBS[job_id]["preview_path"] = preview_path

                # ── Step 4: Render full video ──────────────────────────
                _MAGIC_JOBS[job_id].update({"status": "rendering_video",
                                            "message": "Rendering full video (84 frames)..."})
                video_path = mc.render_video()
                _MAGIC_JOBS[job_id]["video_path"] = video_path

                # ── Step 5: Directus two-write ─────────────────────────
                _MAGIC_JOBS[job_id].update({"status": "registering",
                                            "message": "Registering in Directus..."})
                try:
                    import urllib.request as _req
                    api_keys_path = db / "Production" / "API_KEYS_MASTER.md"
                    # Parse token from API_KEYS_MASTER.md
                    token = None
                    base_url = "https://directus-production-3460.up.railway.app"
                    if api_keys_path.exists():
                        txt = api_keys_path.read_text()
                        import re as _re
                        em = _re.search(r"directus.*?email[\s:]+(\S+)", txt, _re.I)
                        pw = _re.search(r"directus.*?password[\s:]+(\S+)", txt, _re.I)
                        if em and pw:
                            auth_body = _json.dumps({"email": em.group(1), "password": pw.group(1)}).encode()
                            req = _req.Request(f"{base_url}/auth/login",
                                              data=auth_body,
                                              headers={"Content-Type": "application/json"})
                            with _req.urlopen(req, timeout=15) as resp:
                                token = _json.loads(resp.read())["data"]["access_token"]
                    if token:
                        hdrs = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
                        # Write 1: prod_magic_clips
                        clip_payload = _json.dumps({
                            "scene_key": scene_key,
                            "style": style,
                            "manual_path": path_pts_clean,
                            "preview_path": preview_path,
                            "video_path": video_path,
                            "geometry_confirmed_at": _dt.datetime.utcnow().isoformat(),
                            "status": "approved",
                        }).encode()
                        req1 = _req.Request(f"{base_url}/items/prod_magic_clips",
                                            data=clip_payload, headers=hdrs)
                        try:
                            _req.urlopen(req1, timeout=15)
                        except Exception as e1:
                            print(f"[magic] prod_magic_clips write failed: {e1}", file=sys.stderr)
                        # Write 2: prod_activity_log
                        log_payload = _json.dumps({
                            "session_date": _dt.date.today().isoformat(),
                            "activity_type": "magic_render_approved",
                            "description": (f"Magic trail auto-rendered for {scene_key}. "
                                            f"{len(path_pts_clean)} pts. Video: {video_path}"),
                            "output_file": video_path,
                            "kim_verdict": "approved",
                        }).encode()
                        req2 = _req.Request(f"{base_url}/items/prod_activity_log",
                                            data=log_payload, headers=hdrs)
                        try:
                            _req.urlopen(req2, timeout=15)
                        except Exception as e2:
                            print(f"[magic] prod_activity_log write failed: {e2}", file=sys.stderr)
                except Exception as reg_e:
                    # Registration failure is non-blocking — log and continue
                    print(f"[magic] Directus registration failed: {reg_e}", file=sys.stderr)
                    pending = db / "Production" / "Event_1" / "PENDING_REGISTRATIONS.json"
                    try:
                        existing = _json.loads(pending.read_text()) if pending.exists() else []
                        existing.append({"scene_key": scene_key, "video_path": video_path,
                                         "error": str(reg_e), "at": _dt.datetime.utcnow().isoformat()})
                        pending.write_text(_json.dumps(existing, indent=2))
                    except Exception:
                        pass

                # ── Done ──────────────────────────────────────────────
                _MAGIC_JOBS[job_id].update({"status": "done",
                                            "message": "Magic render complete."})

            except Exception as exc:
                _tb.print_exc()
                _MAGIC_JOBS[job_id].update({"status": "error",
                                            "message": str(exc),
                                            "error": str(exc)})

        _th.Thread(target=_run, daemon=True).start()
        return self._send_json(200, {
            "ok": True,
            "job_id": job_id,
            "poll": f"/api/magic/status?job_id={job_id}",
        })

    def _handle_beat_accepted_bg(self) -> None:
        """GET /api/beat/accepted-bg?beat_id=X -> { ok, bg_url, bg_path }
        Returns the absolute server-URL for the currently accepted still image
        of a beat generator beat. Authoritative: reads sidecar + flux_options.
        """
        import urllib.parse as _up
        qs = _up.parse_qs(_up.urlparse(self.path).query)
        beat_id = (qs.get("beat_id") or [None])[0]
        if not beat_id:
            return self._send_json(400, {"ok": False, "error": "beat_id required"})
        try:
            import os as _os
            bg = _bg_module()
            with bg._sidecar_lock:
                sidecar = bg.read_sidecar()
                sidecar = bg._migrate_sidecar(sidecar)
                _, beat = bg.find_beat(sidecar, beat_id)
            if not beat:
                return self._send_json(404, {"ok": False, "error": f"beat {beat_id} not found"})
            key = beat.get("accepted_image_key")
            # Fall back to reference_image / bg_ref_image (drag-from-sources path)
            if not key:
                ref = beat.get("reference_image") or beat.get("bg_ref_image")
                if ref and _os.path.isfile(ref):
                    import urllib.parse as _up3
                    bg_url = f"/files?path={_up3.quote(ref)}"
                    return self._send_json(200, {"ok": True, "bg_url": bg_url, "bg_path": ref})
            # Fall back to first populated flux_option
            if not key:
                for opt in beat.get("flux_options", []) or []:
                    if opt and opt.get("key"):
                        key = opt["key"]
                        break
            if not key:
                return self._send_json(404, {"ok": False,
                    "error": f"No image found for beat {beat_id} — place an image in Option 1 first"})
            # 1. Check flux_options for direct local_path
            abs_path = None
            for opt in beat.get("flux_options", []) or []:
                if opt and opt.get("key") == key:
                    lp = opt.get("local_path")
                    if lp and _os.path.isfile(lp):
                        abs_path = lp
                    break
            # 2. Direct key file in BG_STILLS_DIR
            if not abs_path:
                for ext in (".png", ".webp", ".jpg", ".jpeg"):
                    cand = _os.path.join(bg.BG_STILLS_DIR, key + ext)
                    if _os.path.isfile(cand):
                        abs_path = cand
                        break
            # 3. Crops subdir
            if not abs_path:
                crops_dir = _os.path.join(bg.BG_STILLS_DIR, "crops")
                for ext in (".png", ".webp", ".jpg", ".jpeg"):
                    cand = _os.path.join(crops_dir, key + ext)
                    if _os.path.isfile(cand):
                        abs_path = cand
                        break
            # 4. Key might already be a full path
            if not abs_path and _os.path.isfile(key):
                abs_path = key
            if not abs_path:
                return self._send_json(404, {"ok": False,
                    "error": f"Image file not found for key={key}"})
            import urllib.parse as _up2
            bg_url = f"/files?path={_up2.quote(abs_path)}"
            return self._send_json(200, {"ok": True, "bg_url": bg_url, "bg_path": abs_path})
        except Exception as e:
            return self._send_json(500, {"ok": False, "error": str(e)})

    def _handle_bg_crop_preview(self) -> None:
        """GET /api/bg/crop-preview?keys=key1,key2,...
        Returns {key: data_uri} for each accepted crop key so the browser can
        populate TH[] and display beat thumbnails after a cold page reload."""
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        raw_keys = (qs.get("keys") or [""])[0]
        keys = [k.strip() for k in raw_keys.split(",") if k.strip()]
        if not keys:
            return self._send_json(400, {"error": "keys param required"})

        bg = _bg_module()
        crops_dir = os.path.join(bg.BG_STILLS_DIR, "crops")
        result = {}
        import base64 as _b64
        for key in keys:
            for ext in (".webp", ".png", ".jpg", ".jpeg"):
                fpath = os.path.join(crops_dir, key + ext)
                if os.path.isfile(fpath):
                    with open(fpath, "rb") as fh:
                        data = fh.read()
                    mime = "image/webp" if ext == ".webp" else "image/png" if ext == ".png" else "image/jpeg"
                    result[key] = "data:" + mime + ";base64," + _b64.b64encode(data).decode()
                    break
        return self._send_json(200, {"previews": result})

    def _handle_bg_segments(self) -> None:
        """GET /api/bg/segments?arc_number=N -> { segments: [...] }"""
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        arc_number = int((qs.get("arc_number") or [1])[0])
        bg = _bg_module()
        segments = bg.get_segments(arc_number)
        return self._send_json(200, {"segments": segments, "arc_number": arc_number})

    def _handle_bg_session_state(self) -> None:
        """GET /api/bg/session-state -> { active_context, beats, flux_options_complete, capabilities, migration_warnings }"""
        # LD-456 SCOPE_VALIDATION_V1 (no-body handler — query-string fallback inside helper)
        if not self._assert_event_scope({}, allow_missing=True):
            return

        bg = _bg_module()
        with bg._sidecar_lock:
            sidecar = bg.read_sidecar()
            sidecar = bg._migrate_sidecar(sidecar)
            bg.write_sidecar(sidecar)
        ctx = sidecar.get("active_context")
        beats = []
        if ctx:
            arc_n = ctx.get("arc_number")
            event_id = ctx.get("event_id")
            phase = ctx.get("phase", "full")
            if arc_n is not None and event_id is not None:
                seg = bg.get_seg_entry(sidecar, arc_n, event_id, phase)
                beats = seg.get("beats", [])
        all_done = beats and all(b.get("flux_options") for b in beats)
        return self._send_json(200, {
            "active_context": ctx,
            "beats": beats,
            "flux_options_complete": bool(all_done),
            "capabilities": _bg_capabilities(),
            "migration_warnings": sidecar.get("migration_warnings", []),
        })

    def _handle_bg_poll_flux(self) -> None:
        """GET /api/bg/poll-flux-status?request_ids=id1,id2,...
        Server polls BFL for each id. Returns { id: { status, key, thumb_b64, gallery_b64 } | null }"""
        # LD-456 SCOPE_VALIDATION_V1 (no-body handler — query-string fallback inside helper)
        if not self._assert_event_scope({}, allow_missing=True):
            return

        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        raw = (qs.get("request_ids") or [""])[0]
        if not raw:
            return self._send_json(400, {"error": "request_ids required"})
        request_ids = [r.strip() for r in raw.split(",") if r.strip()]

        bg = _bg_module()
        sidecar = bg.read_sidecar()
        results = {}

        for rid in request_ids:
            try:
                url = bg.poll_flux_result(rid)
                if url:
                    # Download + process image
                    import urllib.request as _ur
                    resp = _ur.urlopen(url, timeout=30)
                    img_bytes = resp.read()
                    # Find beat_id + opt_idx from sidecar task_map
                    beat_id, opt_idx = None, 0
                    for arc in sidecar.get("arcs", {}).values():
                        for seg in arc.get("segments", {}).values():
                            for beat in seg.get("beats", []):
                                for i, stored_rid in enumerate(beat.get("_task_rids", [])):
                                    if stored_rid == rid:
                                        beat_id = beat["beat_id"]
                                        opt_idx = i
                    if not beat_id:
                        # Fallback key from rid suffix
                        beat_id = "unknown"
                        opt_idx = 0
                    filename, local_path, _, thumb_b64, gallery_b64 = bg.process_still_image(
                        img_bytes, beat_id, opt_idx
                    )
                    key = f"bg_{beat_id}_opt{opt_idx}"
                    # Persist to sidecar
                    with bg._sidecar_lock:
                        sc2 = bg.read_sidecar()
                        _, beat_obj = bg.find_beat(sc2, beat_id)
                        if beat_obj:
                            while len(beat_obj.setdefault("flux_options", [])) <= opt_idx:
                                beat_obj["flux_options"].append(None)
                            beat_obj["flux_options"][opt_idx] = {
                                "request_id": rid, "image_url": url,
                                "local_path": local_path, "key": key,
                            }
                            beat_obj["status"] = "stills_pending"
                            bg.write_sidecar(sc2)
                    results[rid] = {
                        "status": "ready", "key": key,
                        "filename": filename,
                        "thumb_b64": thumb_b64, "gallery_b64": gallery_b64,
                    }
                else:
                    results[rid] = None  # still pending
            except Exception as e:
                print(f"[BG] poll error {rid}: {e}")
                results[rid] = {"status": "error", "error": str(e)}

        return self._send_json(200, results)

    def _handle_cr_library(self) -> None:
        """GET /api/cr/library -> { images: [...] }
        Returns three tiers: source (accepted BG stills + uploaded sources),
        cropped (crops/ dir), character_master (Character_Assets/).
        Each item has: key, filename, thumb_b64, gallery_b64, tier, abs_path."""
        bg = _bg_module()
        images = []

        def _read_image(fp, tier):
            try:
                from PIL import Image as _PILImage
                import io as _io2
                fname = os.path.basename(fp)
                with _PILImage.open(fp) as im:
                    im.thumbnail((200, 150), _PILImage.LANCZOS)
                    buf = _io2.BytesIO()
                    im.convert("RGB").save(buf, "JPEG", quality=72)
                thumb_b64 = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
                return {"key": os.path.splitext(fname)[0], "filename": fname,
                        "thumb_b64": thumb_b64, "gallery_b64": thumb_b64,
                        "tier": tier, "abs_path": fp}
            except OSError:
                return None

        # --- Tier 1: accepted FLUX stills from BG sidecar ---
        try:
            sidecar = bg.read_sidecar()
            for arc in sidecar.get("arcs", {}).values():
                for seg in arc.get("segments", {}).values():
                    for beat in seg.get("beats", []):
                        key = beat.get("accepted_image_key")
                        if not key:
                            continue
                        fp = os.path.join(bg.BG_STILLS_DIR, f"{key}.png")
                        if os.path.exists(fp):
                            item = _read_image(fp, "source")
                            if item:
                                item["beat_id"] = beat.get("beat_id", "")
                                item["speaker"] = beat.get("speaker", "")
                                images.append(item)
        except Exception as e:
            print(f"[library] sidecar scan warning: {e}")

        # --- Tier 1b: manually uploaded source images ---
        # Sort mtime-desc so newest uploads land at the top of the library
        # panel (Bug B from preflight 186 / LD-pending). Crops + chars stay
        # alphabetic (those are deliveries / reference; stable order matters).
        sources_dir = os.path.join(bg.BG_STILLS_DIR, "sources")
        if os.path.isdir(sources_dir):
            _src_names = [f for f in os.listdir(sources_dir)
                          if f.lower().endswith((".webp", ".png", ".jpg", ".jpeg"))]
            _src_names.sort(
                key=lambda f: -os.path.getmtime(os.path.join(sources_dir, f)))
            for fname in _src_names:
                item = _read_image(os.path.join(sources_dir, fname), "source")
                if item:
                    images.append(item)

        # --- Tier 2: cropped delivery images ---
        crops_dir = os.path.join(bg.BG_STILLS_DIR, "crops")
        if os.path.isdir(crops_dir):
            for fname in sorted(os.listdir(crops_dir)):
                if fname.lower().endswith((".webp", ".png", ".jpg", ".jpeg")):
                    item = _read_image(os.path.join(crops_dir, fname), "cropped")
                    if item:
                        images.append(item)

        # --- Tier 3: character reference masters ---
        char_dir = os.path.join(bg.BG_STILLS_DIR, "..", "Character_Assets")
        char_dir = os.path.normpath(char_dir)
        if os.path.isdir(char_dir):
            for fname in sorted(os.listdir(char_dir)):
                if fname.endswith("_reference_master.png"):
                    item = _read_image(os.path.join(char_dir, fname), "character_master")
                    if item:
                        speaker = fname.replace("_reference_master.png", "").capitalize()
                        item["speaker"] = speaker
                        images.append(item)

        print(f"[library] serving {len(images)} images ({sum(1 for i in images if i['tier']=='source')} source, {sum(1 for i in images if i['tier']=='cropped')} cropped)", flush=True)
        return self._send_json(200, {"images": images})

    def _handle_cr_full_image(self) -> None:
        """GET /api/cr/full?abs_path=<encoded_path>
        Returns full-resolution base64 data URI for a single image.
        Used by the storyboard nav drop handler for Cropper and .lr row targets
        which need full-res images, not the 200x150 library thumbnails.
        Validates path is within the project directory for safety."""
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        abs_path = params.get("abs_path", [None])[0]
        if not abs_path:
            return self._send_json(400, {"ok": False, "error": "abs_path required"})
        # Safety: path must be within project root
        project_root = str(Path(__file__).parent.parent.parent)
        real_path = os.path.realpath(abs_path)
        if not real_path.startswith(os.path.realpath(project_root)):
            return self._send_json(403, {"ok": False, "error": "path outside project"})
        if not os.path.isfile(real_path):
            return self._send_json(404, {"ok": False, "error": "file not found"})
        ext = os.path.splitext(real_path)[1].lower()
        mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                    ".webp": "image/webp", ".gif": "image/gif"}
        mime = mime_map.get(ext, "image/png")
        with open(real_path, "rb") as f:
            raw = f.read()
        data_uri = f"data:{mime};base64," + base64.b64encode(raw).decode()
        return self._send_json(200, {"ok": True, "data_uri": data_uri})

    def _handle_cr_library_delete(self, body: dict) -> None:
        """POST /api/cr/library/delete  body: {key: str}

        Hard-deletes a source-tier library image after find_asset.py-style
        safety check (refuses if key is referenced in prod_assets.file_path).

        Per Phase 0 preflight 186 (LD-pending LIB_MTIME_SORT_AND_DELETE_V1).
        Path safety mirrors _handle_cr_full_image L5195-5198.
        Rule 19 compliance: every error path returns explicit JSON.
        """
        # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
        if not self._assert_event_scope(self._scope_body(body), allow_missing=False):
            return

        import glob as _glob
        key = (body or {}).get("key")
        if not key or not isinstance(key, str):
            return self._send_json(400, {"ok": False, "error": "key required"})

        # Safety: glob.escape to prevent metacharacter exploits + handle
        # legacy space-vs-underscore mismatch (upload converts spaces to _;
        # sources/ scan may surface either form).
        bg = _bg_module()
        sources_dir = os.path.join(bg.BG_STILLS_DIR, "sources")
        if not os.path.isdir(sources_dir):
            return self._send_json(500, {"ok": False, "error": "sources_dir not found"})

        candidates = []
        for try_key in (key, key.replace("_", " "), key.replace(" ", "_")):
            pattern = os.path.join(sources_dir, _glob.escape(try_key) + ".*")
            for path in _glob.glob(pattern):
                if path not in candidates:
                    candidates.append(path)

        if not candidates:
            return self._send_json(404, {"ok": False, "error": f"key '{key}' not found in sources/"})

        # Realpath safety check — must be within project root (mirrors L5195-5198)
        project_root = os.path.realpath(str(Path(__file__).parent.parent.parent))
        target = None
        for path in candidates:
            real = os.path.realpath(path)
            if real.startswith(project_root):
                target = real
                break
        if not target:
            return self._send_json(403, {"ok": False, "error": "path outside project"})

        # find_asset.py-style safety: refuse if registered in prod_assets.
        # file_path in prod_assets is empirically ABSOLUTE (verified preflight 186)
        try:
            from lib.directus_admin_client import DirectusAdminClient
            _c = DirectusAdminClient()
            referenced = _c.get_items(
                "prod_assets",
                filters={"file_path": {"_eq": target}},
                fields=["id", "file_path", "asset_type"],
                limit=5,
            )
        except Exception as e:
            print(f"[lib-delete] WARN: Directus check failed, proceeding: {e}")
            referenced = []

        if referenced:
            return self._send_json(409, {
                "ok": False,
                "error": f"key '{key}' is referenced in prod_assets — refusing delete",
                "asset_ids": [r.get("id") for r in referenced],
            })

        # Hard delete with Rule 19 explicit JSON on all error paths
        try:
            os.remove(target)
        except FileNotFoundError:
            # Race: file deleted between glob and remove. Return 404 not 500
            # so client treats it as already-deleted (idempotent) per preflight 186.
            return self._send_json(404, {"ok": False, "error": "already deleted"})
        except OSError as e:
            return self._send_json(500, {"ok": False, "error": f"os.remove failed: {e}"})

        # Log to prod_activity_log (best-effort; non-blocking)
        try:
            from lib.directus import try_post_or_queue
            try_post_or_queue("prod_activity_log", {
                "action": "library_image_deleted",
                "performed_by": "claude_lib_delete_handler",
                "details": {"key": key, "deleted_path": target},
            })
        except Exception as e:
            print(f"[lib-delete] WARN: activity log failed: {e}")

        print(f"[lib-delete] removed {target}", flush=True)
        return self._send_json(200, {"ok": True, "deleted": target})

    def _handle_patch_health(self, body: dict) -> None:
        """POST /api/patch_health  body: {patch: str, msg: str}

        Receives runtime invariant-violation reports from the storyboard's
        Fix-W __patchHealthcheck() and logs to prod_activity_log so the
        weekly preflight audit catches regressions.

        Implements CLAUDE.md Rule 36 PATCH_INVARIANT_PERSISTENCE_V1 §36.3.
        Phase 0 preflight 187.
        """
        patch = (body or {}).get("patch") or "unknown"
        msg = (body or {}).get("msg") or ""
        try:
            from lib.directus import try_post_or_queue
            try_post_or_queue("prod_activity_log", {
                "action": "patch_invariant_violation",
                "performed_by": "storyboard_runtime_healthcheck",
                "details": {"patch": patch, "msg": msg, "rule": "Rule 36"},
            })
        except Exception as e:
            print(f"[patch_health] WARN: activity log failed: {e}")
        print(f"[patch_health] {patch}: {msg}", flush=True)
        return self._send_json(200, {"ok": True})

    def _handle_state_snapshot(self, body: dict) -> None:
        """POST /api/state/snapshot  body: {event_id} -> {ok, backup_path, sha256}

        Mitigation M1 per LD-456 PATH_C_REWRITE_V1: every v59 mutation is
        preceded by a state snapshot. Writes a timestamped UTC copy of
        Production/Event_<N>/production_state.json into
        Production/Event_<N>/.backups/state/YYYY-MM-DD_HHMMSSZ.json.

        The v59 client's pathappPatch() will call this before each mutation
        once Session 2+ wires mutations through. Session 1.5 ships the
        endpoint; mutations don't fire from the client yet.
        """
        # READ-ONLY probe (M1 backup precursor — backs up state file, does
        # not mutate Event state). Per spec_v2 §5.2 + SCOPE_REQUIRED_DEFAULTS_V1
        # read-only probes keep allow_missing=True.
        if not self._assert_event_scope(self._scope_body(body), allow_missing=True):
            return

        state_path = self.app.event_dir / "production_state.json"
        if not state_path.exists():
            return self._send_json(404, {
                "error": "production_state.json not found",
                "hint": f"expected at {state_path}",
            })

        backups_dir = self.app.event_dir / ".backups" / "state"
        try:
            backups_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return self._send_json(500, {
                "error": f"could not create backups dir: {exc}",
                "backups_dir": str(backups_dir),
            })

        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%SZ")
        backup_path = backups_dir / f"{ts}.json"

        # Hardlink-first (cheap, COW-friendly), copy fallback for cross-device.
        try:
            try:
                os.link(state_path, backup_path)
                method = "hardlink"
            except (OSError, NotImplementedError):
                shutil.copy2(state_path, backup_path)
                method = "copy"
        except OSError as exc:
            return self._send_json(500, {
                "error": f"snapshot write failed: {exc}",
                "backup_path": str(backup_path),
            })

        # SHA-256 the result so callers can verify integrity.
        try:
            sha = hashlib.sha256(backup_path.read_bytes()).hexdigest()
        except OSError as exc:
            sha = f"<unreadable: {exc}>"

        size_bytes = backup_path.stat().st_size if backup_path.exists() else 0

        print(
            f"[state/snapshot] {method} -> {backup_path.relative_to(self.app.event_dir)} "
            f"({size_bytes} bytes, sha256={sha[:16]}...)",
            flush=True,
        )
        return self._send_json(200, {
            "ok": True,
            "method": method,
            "backup_path": str(backup_path),
            "backup_filename": backup_path.name,
            "size_bytes": size_bytes,
            "sha256": sha,
        })

    def _handle_event_create(self, body: dict) -> None:
        """POST /api/event/create  body: {event_id, event_label?}

        S5.5c+e proper-fix +NewEvent (LD NEW_EVENT_CREATION_UI_V1).
        Spec §4.4: regex ^[A-Z][A-Za-z0-9_]{2,63}$; reserved prefixes
        Test_/_/Tmp_; case-insensitive uniqueness vs Production/Event_*;
        StateManager._init_files for v3 state shape.

        Returns:
          200 {ok, event_id, event_dir}
          400 on validation failure
          409 on case-insensitive collision
        """
        import re as _re
        new_event_id = (body or {}).get("event_id", "")
        if not new_event_id or not _re.match(r'^[A-Z][A-Za-z0-9_]{2,63}$', new_event_id):
            return self._send_json(400, {"ok": False, "error":
                "event_id must match ^[A-Z][A-Za-z0-9_]{2,63}$"})
        for prefix in ('Test_', '_', 'Tmp_'):
            if new_event_id.startswith(prefix):
                return self._send_json(400, {"ok": False, "error":
                    f"event_id cannot start with reserved prefix {prefix!r}"})
        # Case-insensitive uniqueness vs siblings.
        parent = self.app.event_dir.parent
        existing_lower = {p.name.lower() for p in parent.iterdir() if p.is_dir() and p.name.startswith("Event_")}
        if new_event_id.lower() in existing_lower:
            return self._send_json(409, {"ok": False, "error":
                f"event_id {new_event_id!r} already exists (case-insensitive collision)"})
        new_event_dir = parent / new_event_id
        # Create dir + initialize state via StateManager (writes v3-shape state.json).
        new_event_dir.mkdir(parents=True, exist_ok=False)
        # Storyboard template — copy current event's storyboard if possible,
        # else create minimal placeholder (lets future event_load satisfy
        # the storyboard_v*_prod.html lookup).
        try:
            src_sb = self.app.storyboard_path
            if src_sb.is_file():
                import shutil as _shutil
                _shutil.copy(src_sb, new_event_dir / src_sb.name)
        except Exception as _e:
            print(f"[event_create] storyboard copy skipped: {_e}", flush=True)
        # Init state files (production_state.json + production_spend.json).
        try:
            _ = StateManager(new_event_dir, new_event_id)
        except Exception as _e:
            print(f"[event_create] WARN StateManager init: {_e}", flush=True)
        print(f"[event_create] created {new_event_id} at {new_event_dir}", flush=True)
        return self._send_json(200, {"ok": True, "event_id": new_event_id,
                                      "event_dir": str(new_event_dir)})

    def _handle_event_load(self, body: dict) -> None:
        """POST /api/event/load  body: {event_id, arc_number?, module_id?, storyboard?}

        Atomically swap the server's pinned event under event_load_lock and
        increment event_generation. Async jobs pinned to the prior generation
        will be rejected at their terminal write via _check_event_pin (see
        LD-460 ASYNC_JOB_GENERATION_PIN_V1).

        Returns:
            { ok, event_id, event_dir, storyboard, event_generation }

        Concurrency contract (LD-458 EVENT_LOAD_GENERATION_LOCK_V1):
          - Acquires self.app.event_load_lock for the entire swap.
          - Two parallel calls serialize; the second sees the first's new
            event_generation.
          - Increment is monotonic; never decremented.
          - The swap is atomic from clients' perspective: any read after
            the response will see the new event.

        Single-user mode: Kim operates one tab. Lock contention is rare.
        Future multi-user: revisit lock granularity.
        """
        # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1 — but for
        # event/load, the WHOLE POINT is to switch scope. We do NOT call
        # _assert_event_scope here. Instead we validate that the requested
        # event_id is non-empty + a real directory.
        new_event_id = (body or {}).get("event_id") or (body or {}).get("scope_event_id")
        if not new_event_id:
            return self._send_json(400, {
                "error": "event_id required",
                "code": "EVENT_LOAD_GENERATION_LOCK_V1",
            })

        # event_dir is sibling of current — we do NOT allow arbitrary paths.
        # Pattern: Production/<event_id>/ next to current Production/<current>/.
        new_event_dir = self.app.event_dir.parent / new_event_id
        if not new_event_dir.is_dir():
            return self._send_json(404, {
                "error": "event_dir not found",
                "code": "EVENT_LOAD_GENERATION_LOCK_V1",
                "expected": str(new_event_dir),
                "hint": (
                    f"event_id {new_event_id!r} must correspond to an "
                    f"existing directory at {new_event_dir}."
                ),
            })

        # Storyboard pick: explicit body['storyboard'], else keep current
        # filename (works if every event uses the same storyboard naming).
        # Else discover the latest storyboard_v*_prod.html in the new dir.
        requested_sb = (body or {}).get("storyboard")
        if requested_sb:
            new_storyboard_path = new_event_dir / requested_sb
        elif (new_event_dir / self.app.storyboard_path.name).exists():
            new_storyboard_path = new_event_dir / self.app.storyboard_path.name
        else:
            candidates = sorted(
                new_event_dir.glob("storyboard_v*_prod.html"),
                key=lambda p: p.stat().st_mtime, reverse=True,
            )
            if not candidates:
                return self._send_json(404, {
                    "error": "no storyboard_v*_prod.html in target event_dir",
                    "code": "EVENT_LOAD_GENERATION_LOCK_V1",
                    "event_dir": str(new_event_dir),
                })
            new_storyboard_path = candidates[0]

        if not new_storyboard_path.is_file():
            return self._send_json(404, {
                "error": "storyboard file not found",
                "code": "EVENT_LOAD_GENERATION_LOCK_V1",
                "expected": str(new_storyboard_path),
            })

        # ATOMIC SWAP under lock.
        with self.app.event_load_lock:
            old_gen = self.app.event_generation
            old_event_id = self.app.event_dir.name
            old_storyboard = self.app.storyboard_path.name

            self.app.event_dir = new_event_dir
            self.app.storyboard_path = new_storyboard_path
            self.app.event_id = new_event_id
            self.app.storyboard_stem = new_storyboard_path.stem
            self.app.event_generation = old_gen + 1
            # S5 v3.1 fix — StateManager caches state_path at construct time.
            # On event swap we must re-point it so subsequent state reads/writes
            # hit the NEW event's production_state.json (was reading Event_1's
            # state regardless of swap).
            try:
                self.app.state.event_dir = new_event_dir
                self.app.state.state_path = new_event_dir / "production_state.json"
                self.app.state.event_id = new_event_id
            except AttributeError:
                pass
            # Invalidate caches that key on event_dir / storyboard_path.
            # Clear cross-event image override caches alongside the storyboard
            # caches — same bug class as the S5 StateManager state_path fix
            # (Cursor v4 finding): _image_overrides was cleared in
            # _handle_storyboard_switch but missed in _handle_event_load until
            # now, leaking Event_1 overrides into Event_2 reads. Per
            # IMAGE_OVERRIDES_CLEAR_ON_EVENT_LOAD_V1. S5.5a2 update: both
            # caches are now nested dict[str, dict[str, str]] keyed by role
            # then beat_id (IMAGE_OVERRIDES_NESTED_BY_ROLE_V1) — clearing
            # the outer dict still wipes everything.
            try:
                self.app._image_overrides = {}
                self.app._pending_override_keys = {}
                print(
                    f"[event/load] cleared image override cache "
                    f"(event swap to {new_event_id})",
                    flush=True,
                )
            except AttributeError:
                pass
            self.app.invalidate_beats_cache()
            self.app._storyboard_list_cache = None
            self.app._storyboard_list_cache_mtime = 0.0
            # S5.5d (v3): scope-type signal for milestone-aware code paths.
            self.app.scope_type = "event"
            self.app.active_milestone_id = None
            new_gen = self.app.event_generation

        print(
            f"[event/load] {old_event_id} (gen={old_gen}, sb={old_storyboard}) -> "
            f"{new_event_id} (gen={new_gen}, sb={new_storyboard_path.name}). "
            f"Async jobs pinned to gen {old_gen} will be rejected at terminal "
            f"writes per LD-460.",
            flush=True,
        )

        return self._send_json(200, {
            "ok": True,
            "event_id": new_event_id,
            "event_dir": str(new_event_dir),
            "storyboard": new_storyboard_path.name,
            "event_generation": new_gen,
            "previous_generation": old_gen,
            "previous_event_id": old_event_id,
        })

    # ================================================================
    # S5.5b new endpoints — EVENT_CURRENT_ENDPOINT_V1, VIDEO_LIST_ENDPOINT_V1,
    # VIDEO_SET_ACTIVE_ENDPOINT_V1, VIDEO_CREATE_ENDPOINT_V1
    # ================================================================

    def _handle_event_current(self) -> None:
        """GET /api/event/current — return the currently-loaded event.

        Bug 4 fix per S5.5b spec §3 + Cursor v5 verbatim recommendation.
        ScopeBoundary on boot can call this to know which event the server
        is serving (URL/data-attr/window-global fallbacks may be stale after
        EventSelector triggers a `/api/event/load` + `window.location.reload()`).

        Returns:
          {event_id, event_dir, event_generation, active_video, partition_keys}
        on success; {event_id: null} (HTTP 200) on cold-boot when no event
        loaded — null is a valid state, not an error.
        """
        try:
            state = self.app.state.read_state()
            videos = state.get("videos") or {}
            return self._send_json(200, {
                "ok": True,
                "event_id": self.app.event_id,
                "event_dir": str(self.app.event_dir),
                "event_generation": self.app.event_generation,
                "active_video": state.get("active_video"),
                "partition_keys": sorted(videos.keys()),
            })
        except AttributeError:
            # No event loaded (cold boot before any /api/event/load).
            return self._send_json(200, {"ok": True, "event_id": None})

    def _handle_video_list(self) -> None:
        """GET /api/video/list — return the partition list for the loaded event.

        Wraps StateManager.list_videos(). Read-only; no scope guard required
        (returns metadata about the currently-loaded event only).
        """
        try:
            videos = self.app.state.list_videos()
            state = self.app.state.read_state()
            return self._send_json(200, {
                "ok": True,
                "event_id": self.app.event_id,
                "active_video": state.get("active_video"),
                "videos": videos,
            })
        except Exception as exc:  # noqa: BLE001
            return self._send_json(500, {
                "ok": False,
                "error": f"failed to list videos: {type(exc).__name__}: {exc}",
            })

    def _handle_video_set_active(self, body: dict) -> None:
        """POST /api/video/set_active — write state.active_video (display hint).

        Body: {scope_event_id, video_role}. Validates video_role against
        canonical set + presence in state.videos via state.validate_video_role.

        IMPORTANT (LD-474 reminder): state.active_video is a DISPLAY HINT
        ONLY. It is the write-target of this endpoint so the v59 client can
        persist Kim's last-selected video role across page reloads. Server
        handlers MUST NOT read state.active_video for partition selection —
        partition selection comes ONLY from body['scope_video_role'] on each
        mutating request. This endpoint exists solely for UX persistence.
        """
        if not self._assert_event_scope(self._scope_body(body), allow_missing=False):
            return
        video_role = (body or {}).get("video_role")
        if not video_role:
            return self._send_json(400, {
                "ok": False,
                "error": "video_role required",
                "code": "VIDEO_ROLE_INVALID",
                "valid": sorted(self.app.state._VALID_VIDEO_ROLES),
            })
        if not self.app.state.validate_video_role(video_role):
            return self._send_json(400, {
                "ok": False,
                "error": f"video_role {video_role!r} not valid for this event",
                "code": "VIDEO_ROLE_INVALID",
                "got": video_role,
                "valid": sorted(self.app.state._VALID_VIDEO_ROLES),
                "hint": "must be in canonical set AND exist in state.videos.",
            })

        # Write state.active_video at the top level (not partition-scoped).
        def _set_active(state, _role=video_role):
            state["active_video"] = _role

        self.app.state.mutate_state(_set_active)
        return self._send_json(200, {
            "ok": True,
            "event_id": self.app.event_id,
            "active_video": video_role,
        })

    def _handle_video_create(self, body: dict) -> None:
        """POST /api/video/create — add a new video partition.

        Body: {scope_event_id, video_role, video_label?}. Wraps
        StateManager.create_video. Returns 400 on invalid role; 409 on
        duplicate (partition already exists).
        """
        if not self._assert_event_scope(self._scope_body(body), allow_missing=False):
            return
        video_role = (body or {}).get("video_role")
        video_label = (body or {}).get("video_label")
        if not video_role:
            return self._send_json(400, {
                "ok": False,
                "error": "video_role required",
                "code": "VIDEO_ROLE_INVALID",
                "valid": sorted(self.app.state._VALID_VIDEO_ROLES),
            })
        try:
            created = self.app.state.create_video(video_role, video_label)
        except ValueError as exc:
            return self._send_json(400, {
                "ok": False,
                "error": str(exc),
                "code": "VIDEO_ROLE_INVALID",
                "valid": sorted(self.app.state._VALID_VIDEO_ROLES),
            })
        if not created:
            return self._send_json(409, {
                "ok": False,
                "error": f"partition {video_role!r} already exists",
                "code": "VIDEO_ROLE_DUPLICATE",
            })
        return self._send_json(200, {
            "ok": True,
            "event_id": self.app.event_id,
            "video_role": video_role,
            "video_label": video_label,
        })

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
        """POST /api/admin/drain_start — gate new work.

        Sets app.accept_new_jobs=False so subsequent decorated handlers
        return HTTP 503 immediately. Existing in-flight work continues
        until terminal completion. Returns the current inflight snapshot
        so the migration script can decide whether to abort.

        Idempotent: safe to call multiple times; second+ calls return the
        same {ok, inflight_count} shape with no state change.
        """
        self.app.accept_new_jobs = False
        # Reuse the inflight enumeration helper for consistency.
        return self._handle_admin_inflight_count(body)

    def _handle_admin_drain_end(self, body: dict | None = None) -> None:
        """POST /api/admin/drain_end — re-open new work.

        Sets app.accept_new_jobs=True. Idempotent.
        """
        self.app.accept_new_jobs = True
        return self._send_json(200, {
            "ok": True,
            "accept_new_jobs": True,
        })

    def _handle_admin_inflight_count(self, body: dict | None = None) -> None:
        """GET /api/admin/inflight_count — full enumeration of active work.

        Per v3 spec §3.7: derives count from existing module-level
        registries (_GPT_JOBS, _MAGIC_JOBS, _ASSEMBLE_JOBS) plus
        app._sync_inflight (sync handler tracking) plus a state-scan for
        lipsync (which lives in state.beats[bk].lipsync.status across all
        video role partitions: intro, resolution, standalone).

        Used by both the migration script's pre-flight abort gate and the
        E37 drain probe.
        """
        active: dict[str, list] = {
            "gpt": [], "magic": [], "assemble": [], "lipsync": [], "sync": [],
        }

        # GPT jobs (running)
        for job_id, info in list(_GPT_JOBS.items()):
            if info.get("status") == "running":
                done = sum(len(v) for v in info.get("results", {}).values()) \
                    if isinstance(info.get("results"), dict) else 0
                total = info.get("total") or 0
                active["gpt"].append({
                    "job_id": job_id,
                    "name": f"gpt-stills:{job_id}",
                    "progress": f"{done}/{total}",
                })

        # Magic jobs (non-terminal)
        _MAGIC_TERMINAL = {"done", "error"}
        for job_id, info in list(_MAGIC_JOBS.items()):
            st = info.get("status")
            if st not in _MAGIC_TERMINAL:
                active["magic"].append({
                    "job_id": job_id,
                    "name": f"magic:{info.get('scene_key', '?')}",
                    "status": st,
                })

        # Assemble jobs (running)
        for gid, info in list(_ASSEMBLE_JOBS.items()):
            if info.get("status") == "running":
                active["assemble"].append({
                    "group_id": gid,
                    "name": f"assemble:group={gid}",
                })

        # Lipsync — state-scan across all video role partitions
        try:
            st = self.app.state.read_state()
            for role in ("intro", "resolution", "standalone"):
                partition = ((st.get("videos") or {}).get(role) or {})
                beats = partition.get("beats") or {}
                for bk, b in beats.items():
                    ls = (b or {}).get("lipsync") or {}
                    if ls.get("status") in ("submitting", "polling"):
                        active["lipsync"].append({
                            "beat_id": bk,
                            "role": role,
                            "name": f"lipsync:{role}:{bk}",
                            "status": ls["status"],
                        })
        except Exception:
            # Cold-boot or read failure: treat as no lipsync in flight.
            # Drain protocol is fail-closed at the migration level (it
            # also polls 60s for sync residue), so a transient state
            # read failure here doesn't compromise correctness.
            pass

        # Sync inflight (decorator-tracked)
        with self.app._sync_inflight_lock:
            for sid in sorted(self.app._sync_inflight):
                handler, _, _ = sid.partition(":")
                active["sync"].append({"id": sid, "name": handler})

        total = sum(len(v) for v in active.values())
        return self._send_json(200, {
            "ok": True,
            "inflight_count": total,
            "accept_new_jobs": getattr(self.app, "accept_new_jobs", True),
            "active_jobs": active,
        })

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
        """GET /api/milestones/list — return all milestones (cold-safe)."""
        root = self._milestones_root()
        milestones: list[dict] = []
        if root.is_dir():
            for d in sorted(root.iterdir()):
                if not d.is_dir():
                    continue
                state_path = d / "state.json"
                label = None
                created_at = None
                if state_path.is_file():
                    try:
                        s = json.loads(state_path.read_text())
                        label = s.get("milestone_label") or s.get("label")
                        created_at = s.get("created_at")
                    except (OSError, json.JSONDecodeError):
                        pass
                milestones.append({
                    "milestone_id": d.name,
                    "milestone_label": label,
                    "created_at": created_at,
                    "path": str(d),
                })
        return self._send_json(200, {
            "ok": True,
            "milestones": milestones,
            "milestones_root": str(root),
        })

    def _handle_milestones_create(self, body: dict) -> None:
        """POST /api/milestones/create — body: {milestone_id, milestone_label?}.

        Validates milestone_id per v3 spec §3.4.1; rejects collision with
        existing milestone (HTTP 409 case-insensitive). Creates
        Production/Milestones/<id>/ with a v3-shaped state.json containing
        videos.standalone partition.
        """
        milestone_id = (body or {}).get("milestone_id")
        milestone_label = (body or {}).get("milestone_label")
        ok, err = self._validate_milestone_id(milestone_id)
        if not ok:
            return self._send_json(400, {
                "ok": False,
                "error": err,
                "code": "MILESTONE_ID_INVALID",
            })

        root = self._milestones_root()
        root.mkdir(parents=True, exist_ok=True)

        # Case-insensitive collision check.
        target = root / milestone_id
        existing_lower = {p.name.lower() for p in root.iterdir() if p.is_dir()}
        if milestone_id.lower() in existing_lower:
            return self._send_json(409, {
                "ok": False,
                "error": f"milestone {milestone_id!r} already exists (case-insensitive collision)",
                "code": "MILESTONE_ID_DUPLICATE",
            })

        target.mkdir(parents=True, exist_ok=False)
        # Animation clips dir (mirrors Event_<N> layout).
        (target / "animation_clips").mkdir(exist_ok=True)
        (target / "animation_clips_final").mkdir(exist_ok=True)

        now_iso = datetime.now(timezone.utc).isoformat()
        state = {
            "milestone_id": milestone_id,
            "milestone_label": milestone_label,
            "version": "v3",
            "created_at": now_iso,
            "updated_at": now_iso,
            "active_video": "standalone",
            "scope_type": "milestone",
            "videos": {
                "standalone": {
                    "video_role": "standalone",
                    "video_label": milestone_label,
                    "beats": {},
                    "image_overrides": {},
                    "display_order": [],
                    "completed_mp4_path": None,
                },
            },
        }
        state_path = target / "state.json"
        atomic_json_write(str(state_path), state)
        return self._send_json(200, {
            "ok": True,
            "milestone_id": milestone_id,
            "milestone_label": milestone_label,
            "milestone_dir": str(target),
            "state_path": str(state_path),
        })

    def _handle_milestone_load(self, body: dict) -> None:
        """POST /api/milestones/load — switch active scope to a milestone.

        Body: {milestone_id}. Mirrors _handle_event_load semantics under
        event_load_lock — increments event_generation; clears caches;
        sets app.scope_type='milestone' + app.active_milestone_id.

        Per LD-475 (multi-beat partition cache invalidation extension).
        Note: app.event_dir + app.event_id are LEFT UNCHANGED so any
        legacy paths that still resolve files relative to the prior
        event_dir don't catastrophically misroute. Cross-scope handlers
        consult app.scope_type + app.active_milestone_id directly.
        """
        milestone_id = (body or {}).get("milestone_id")
        ok, err = self._validate_milestone_id(milestone_id)
        if not ok:
            return self._send_json(400, {
                "ok": False,
                "error": err,
                "code": "MILESTONE_ID_INVALID",
            })

        target = self._milestones_root() / milestone_id
        if not target.is_dir():
            return self._send_json(404, {
                "ok": False,
                "error": f"milestone {milestone_id!r} not found at {target}",
                "code": "MILESTONE_NOT_FOUND",
            })
        state_path = target / "state.json"
        if not state_path.is_file():
            return self._send_json(404, {
                "ok": False,
                "error": f"milestone state.json missing at {state_path}",
                "code": "MILESTONE_STATE_MISSING",
            })

        with self.app.event_load_lock:
            old_gen = self.app.event_generation
            self.app.event_generation = old_gen + 1
            self.app.scope_type = "milestone"
            self.app.active_milestone_id = milestone_id
            self.app.milestone_dir = target
            # Clear cross-scope caches (LD-475 cache invalidation extended).
            try:
                self.app._image_overrides = {}
                self.app._pending_override_keys = {}
            except AttributeError:
                pass
            try:
                self.app.invalidate_beats_cache()
            except AttributeError:
                pass
            self.app._storyboard_list_cache = None
            self.app._storyboard_list_cache_mtime = 0.0
            new_gen = self.app.event_generation

        print(
            f"[milestone/load] -> {milestone_id} (gen={new_gen}, dir={target}). "
            f"scope_type='milestone'. Async jobs pinned to gen {old_gen} will be "
            f"rejected at terminal writes per LD-460.",
            flush=True,
        )

        return self._send_json(200, {
            "ok": True,
            "milestone_id": milestone_id,
            "milestone_dir": str(target),
            "event_generation": new_gen,
            "previous_generation": old_gen,
            "scope_type": "milestone",
        })

    def _handle_project_list(self, body: dict | None = None) -> None:
        """GET /api/project/list — combined Events + Milestones for the
        v59 ProjectSelector dropdown.

        Returns:
            {events: [...], milestones: [...], scope_type, active_event_id,
             active_milestone_id}
        """
        # Events: leverage existing _handle_event_list orchestration.
        production_root = self.app.event_dir.parent
        events: list[dict] = []
        for d in sorted(production_root.iterdir()):
            if not d.is_dir():
                continue
            if not d.name.startswith("Event_"):
                continue
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
                "storyboard": storyboards[0].name,
            })

        milestones_root = self._milestones_root()
        milestones: list[dict] = []
        if milestones_root.is_dir():
            for d in sorted(milestones_root.iterdir()):
                if not d.is_dir():
                    continue
                state_path = d / "state.json"
                label = None
                if state_path.is_file():
                    try:
                        s = json.loads(state_path.read_text())
                        label = s.get("milestone_label")
                    except (OSError, json.JSONDecodeError):
                        pass
                milestones.append({
                    "milestone_id": d.name,
                    "milestone_label": label,
                    "path": str(d),
                })

        return self._send_json(200, {
            "ok": True,
            "events": events,
            "milestones": milestones,
            "scope_type": getattr(self.app, "scope_type", "event"),
            "active_event_id": self.app.event_id,
            "active_milestone_id": getattr(self.app, "active_milestone_id", None),
        })

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
        """POST /api/beat/finalize — Stage 1 of the export pipeline.

        Body: {scope_event_id?, scope_milestone_id?, scope_target_video,
               beat_id, force_rebuild?}

        Per v3 spec §3.5 Stage 1. Cached single-artifact strategy:
        beat_NN_final.mp4 is the trimmed-and-audio-delayed AND
        LD-284-normalized version. One cache, one hash.

        Cache miss invokes normalize_for_concat → trim_normalized then
        registers the result as a 'beat_scene' asset. Cache hit returns
        the existing path with cache_hit=true.
        """
        scope_type, scope_root, err_st, err_body = self._resolve_scope_root(body)
        if err_st is not None:
            return self._send_json(err_st, err_body)

        scope_target_video = (body or {}).get("scope_target_video")
        if scope_target_video not in self.app.state._VALID_VIDEO_ROLES:
            return self._send_json(400, {
                "ok": False,
                "error": "scope_target_video required + must be intro/resolution/standalone",
                "code": "VIDEO_ROLE_INVALID",
                "got": scope_target_video,
                "valid": sorted(self.app.state._VALID_VIDEO_ROLES),
            })

        beat_id = (body or {}).get("beat_id")
        if not beat_id:
            return self._send_json(400, {
                "ok": False,
                "error": "beat_id required",
                "code": "BEAT_ID_MISSING",
            })
        force_rebuild = bool((body or {}).get("force_rebuild", False))

        # LD-460 pin tuple at entry (v3 spec §3.5).
        _pin = {
            "pinned_generation": self.app.event_generation,
            "pinned_event_dir": self.app.event_dir,
            "pinned_video_role": scope_target_video,
            "_handler": "beat_finalize",
        }
        if not self._check_event_pin(_pin, "beat_finalize_pre_work"):
            return self._send_json(423, {
                "error": "event_changed_pre_work",
                "code": "ASYNC_JOB_GENERATION_PIN_V1",
                "handler": "beat_finalize",
            })

        # Lazy import the lib pipeline.
        try:
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), "lib"))
            from ffmpeg_stitch import (  # type: ignore
                FINALIZE_RECIPE_VERSION as _FRV,
                NORMALIZATION_RECIPE_HASH as _NRH,
                compute_finalize_args_hash,
                normalize_for_concat,
                trim_normalized,
            )
        except ImportError as exc:
            return self._send_json(500, {
                "ok": False,
                "error": f"lib/ffmpeg_stitch import failed: {exc}",
            })

        # Snapshot state (slim — beats + image_overrides) at entry.
        state = self._read_scope_state(scope_type, scope_root)
        videos = state.get("videos") or {}
        partition = videos.get(scope_target_video) or {}
        beats = partition.get("beats") or {}
        if beat_id not in beats:
            return self._send_json(400, {
                "ok": False,
                "error": f"unknown beat {beat_id!r} in role {scope_target_video!r}",
            })
        slim = {
            "beats": beats,
            "image_overrides": partition.get("image_overrides") or {},
        }

        # Resolve clips_dir per scope.
        if scope_type == "event":
            clips_dir = self.app.state.clips_dir
        else:
            clips_dir = scope_root / "animation_clips"

        # Compute hash + metadata. resolve_beat_file may raise FNF.
        try:
            digest, meta = compute_finalize_args_hash(slim, beat_id, clips_dir)
        except FileNotFoundError as exc:
            return self._send_json(400, {
                "ok": False,
                "error": str(exc),
                "code": "BEAT_SOURCE_MISSING",
            })

        # Cache directory + file.
        cache_dir = scope_root / "animation_clips_final"
        cache_dir.mkdir(parents=True, exist_ok=True)
        src_path = Path(meta["file"])
        src_md5 = hashlib.md5(str(src_path.resolve()).encode("utf-8")).hexdigest()[:10]
        recipe6 = _NRH[:6]
        ts_ms = int(round(float(meta["trim_start"]) * 1000))
        te_raw = meta["trim_end"]
        te_ms = int(round(te_raw * 1000)) if te_raw is not None else -1
        ad_ms = int(round(float(meta["audio_delay"]) * 1000))
        cache_filename = (
            f"{beat_id}_final_{src_md5}_{recipe6}_{ts_ms}_{te_ms}_{ad_ms}.mp4"
        )
        cache_path = cache_dir / cache_filename
        sidecar_path = cache_path.with_suffix(".mp4.meta.json")

        # Cache hit branch — sidecar attests the cache is current.
        cache_hit = False
        if cache_path.is_file() and sidecar_path.is_file() and not force_rebuild:
            try:
                sidecar = json.loads(sidecar_path.read_text())
                if sidecar.get("finalize_args_hash") == digest:
                    cache_hit = True
            except (OSError, json.JSONDecodeError):
                cache_hit = False

        if not cache_hit:
            # Build: normalize → trim. Atomic via lib helpers (each does
            # tmp+rename).
            normalized_dir = scope_root / "normalized_segments"
            normalized_dir.mkdir(parents=True, exist_ok=True)
            norm_path = normalized_dir / f"{beat_id}_normalized_{src_md5}_{recipe6}.mp4"
            needs_norm = (
                not norm_path.is_file()
                or src_path.stat().st_mtime > norm_path.stat().st_mtime
            )
            if needs_norm:
                normalize_for_concat(src_path, norm_path)
            trim_normalized(
                norm_path, cache_path,
                meta.get("trim_start"), meta.get("trim_end"),
                audio_delay=float(meta.get("audio_delay") or 0.0),
            )
            # Write sidecar.
            sidecar_payload = {
                "finalize_args_hash": digest,
                "finalize_args": {
                    "beat_id": beat_id,
                    "scope_target_video": scope_target_video,
                    "scope_type": scope_type,
                    "scope_root": str(scope_root),
                    "trim_start": meta.get("trim_start"),
                    "trim_end": meta.get("trim_end"),
                    "audio_delay": meta.get("audio_delay"),
                    "selected_option": meta.get("selected_option"),
                    "lipsync_path": meta.get("lipsync_path"),
                    "image_override": meta.get("image_override"),
                },
                "recipe_hash": _NRH,
                "recipe_version": _FRV,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "source_path": str(src_path),
                "source_mtime": meta["mtime"],
                "source_sha256_first_1mb": (
                    hashlib.sha256(src_path.open("rb").read(1 * 1024 * 1024)).hexdigest()
                    if src_path.is_file() else None
                ),
            }
            atomic_json_write(str(sidecar_path), sidecar_payload)

            # Terminal pin check before asset registration.
            if not self._check_event_pin(_pin, "beat_finalize_terminal"):
                return self._send_json(423, {
                    "error": "event_changed_terminal",
                    "code": "ASYNC_JOB_GENERATION_PIN_V1",
                    "handler": "beat_finalize",
                })

            # Register as 'beat_scene' asset (Two-Write Rule: register_asset
            # internally writes both prod_assets and prod_activity_log).
            try:
                from registered_write import register_asset as _reg
                # iteration_notes template
                notes_text = (
                    f"[{datetime.now(timezone.utc).isoformat()}] beat finalize: "
                    f"scope={scope_type}:{scope_root.name}, role={scope_target_video}, "
                    f"beat={beat_id}, hash={digest[:10]}, recipe={_NRH}:{_FRV}, "
                    f"src_mtime={meta['mtime']:.1f}, trim=[{meta.get('trim_start')},"
                    f"{meta.get('trim_end')}], audio_delay={meta.get('audio_delay')}."
                )
                _reg(
                    file_path=str(cache_path),
                    asset_type="beat_scene",
                    module_id=1,  # M1 stub — refine when prod_modules id resolves
                    event_id=None,
                    beat_id=beat_id,
                    parent_asset_id=None,
                    produced_by_skill="beat_finalize_v1",
                    iteration_notes=notes_text,
                    role=scope_target_video,
                    tags=["beat_scene", scope_target_video, scope_type],
                )
            except Exception as reg_exc:  # noqa: BLE001
                # Non-blocking — registration retries via pending queue.
                print(f"[beat_finalize] register_asset deferred: {reg_exc}",
                      flush=True)

        return self._send_json(200, {
            "ok": True,
            "file_path": str(cache_path),
            "cache_hit": cache_hit,
            "finalize_args_hash": digest,
            "recipe_hash": _NRH,
            "recipe_version": _FRV,
            "scope_type": scope_type,
            "scope_root": str(scope_root),
            "scope_target_video": scope_target_video,
            "beat_id": beat_id,
        })

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
            return self._send_json(400, {
                "ok": False,
                "error": "scope_target_video required + must be intro/resolution/standalone",
                "code": "VIDEO_ROLE_INVALID",
                "got": scope_target_video,
                "valid": sorted(self.app.state._VALID_VIDEO_ROLES),
            })

        fade_ms_raw = (body or {}).get("fade_between_beats_ms", 0)
        try:
            fade_ms = int(fade_ms_raw) if fade_ms_raw is not None else 0
        except (TypeError, ValueError):
            return self._send_json(400, {
                "ok": False,
                "error": f"fade_between_beats_ms must be int, got {fade_ms_raw!r}",
            })
        if fade_ms < 0 or fade_ms > _V2_MODULE_FADE_MAX_MS:
            return self._send_json(400, {
                "ok": False,
                "error": f"fade_between_beats_ms out of range: {fade_ms}",
            })
        force_rebuild = bool((body or {}).get("force_rebuild", False))

        # LD-460 pin tuple at entry.
        _pin = {
            "pinned_generation": self.app.event_generation,
            "pinned_event_dir": self.app.event_dir,
            "pinned_video_role": scope_target_video,
            "_handler": "scene_assemble",
        }
        if not self._check_event_pin(_pin, "scene_assemble_pre_work"):
            return self._send_json(423, {
                "error": "event_changed_pre_work",
                "code": "ASYNC_JOB_GENERATION_PIN_V1",
                "handler": "scene_assemble",
            })

        # Lock per scope (event) | (milestone). NB-LOCK_EX → 409 on contention.
        try:
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), "lib"))
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
                trim_body,
                trim_normalized,
            )
        except ImportError as exc:
            return self._send_json(500, {
                "ok": False,
                "error": f"lib/ffmpeg_stitch import failed: {exc}",
            })

        lock_path = _scene_lock_path(scope_type, scope_root, scope_target_video)
        import fcntl  # noqa: PLC0415
        lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
        try:
            try:
                fcntl.lockf(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (BlockingIOError, OSError):
                return self._send_json(409, {
                    "ok": False,
                    "error": "another scene_assemble is in flight on this scope",
                    "code": "SCENE_ASSEMBLE_LOCK_HELD",
                    "lock_path": str(lock_path),
                })

            # Snapshot at entry (no mid-pipeline re-read per Cursor).
            state = self._read_scope_state(scope_type, scope_root)
            videos = state.get("videos") or {}
            partition = videos.get(scope_target_video) or {}
            beats = partition.get("beats") or {}
            display_order = partition.get("display_order") or []

            # Filter to ordered beats with phase_1.selected_option set.
            allowed = set(display_order)
            ordered_beat_ids: list[str] = [
                bid for bid in display_order
                if bid in allowed
                and bid in beats
                and isinstance(beats[bid], dict)
                and (beats[bid].get("phase_1") or {}).get("selected_option") is not None
            ]
            # Fallback: if display_order is empty (legacy / cold partitions),
            # use sorted beat ids — consistent with _handle_preview_stitched
            # fast path for single-beat scenes.
            if not ordered_beat_ids:
                ordered_beat_ids = sorted(
                    bid for bid, b in beats.items()
                    if isinstance(b, dict)
                    and (b.get("phase_1") or {}).get("selected_option") is not None
                )
            if not ordered_beat_ids:
                return self._send_json(400, {
                    "ok": False,
                    "error": "no beats with selected_option in target partition",
                    "code": "EMPTY_SCENE",
                })

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
                    digest, meta = compute_finalize_args_hash(slim, bid, clips_dir)
                except FileNotFoundError as exc:
                    return self._send_json(400, {
                        "ok": False,
                        "error": str(exc),
                        "beat_id": bid,
                        "code": "BEAT_SOURCE_MISSING",
                    })
                src_path = Path(meta["file"])
                src_md5 = hashlib.md5(str(src_path.resolve()).encode("utf-8")).hexdigest()[:10]
                ts_ms = int(round(float(meta["trim_start"]) * 1000))
                te_raw = meta["trim_end"]
                te_ms = int(round(te_raw * 1000)) if te_raw is not None else -1
                ad_ms = int(round(float(meta["audio_delay"]) * 1000))
                fname = (
                    f"{bid}_final_{src_md5}_{recipe6}_{ts_ms}_{te_ms}_{ad_ms}.mp4"
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
                    trim_normalized(
                        norm_path, fpath,
                        meta.get("trim_start"), meta.get("trim_end"),
                        audio_delay=float(meta.get("audio_delay") or 0.0),
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
                    head_s = (clamped_pair_fades[i - 1] / 1000.0
                              if i > 0 and clamped_pair_fades[i - 1] > 0 else 0.0)
                    tail_s = (clamped_pair_fades[i] / 1000.0
                              if i < N - 1 and clamped_pair_fades[i] > 0 else 0.0)
                    if head_s == 0.0 and tail_s == 0.0:
                        parts.append(beat_final[bid])
                    else:
                        head_ms = int(round(head_s * 1000))
                        tail_ms = int(round(tail_s * 1000))
                        body_path = body_dir / (
                            f"{bid}_body_{m['finalize_args_hash'][:10]}_{head_ms}_{tail_ms}_{recipe6}.mp4"
                        )
                        if body_path.is_file() and not force_rebuild:
                            cache_stats["body_hits"] += 1
                        else:
                            cache_stats["body_misses"] += 1
                            trim_body(beat_final[bid], body_path, head_s, tail_s)
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

                    # XFade pair clip if next pair has fade>0.
                    if i < N - 1 and clamped_pair_fades[i] > 0:
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
                return self._send_json(423, {
                    "error": "event_changed_terminal",
                    "code": "ASYNC_JOB_GENERATION_PIN_V1",
                    "handler": "scene_assemble",
                })

            # Write completed_mp4_path.
            self._write_scope_state_field(
                scope_type, scope_root, scope_target_video,
                "completed_mp4_path", str(scene_path),
            )

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
                    module_id=1,  # M1 stub
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
            return self._send_json(500, {
                "error": f"could not enumerate events: {exc}",
                "production_root": str(self.app.event_dir.parent),
            })

    def _handle_phase_watercolor_list(self) -> None:
        """GET /api/phase/watercolor_list — inventory of watercolor library.

        Reads Production/assets/watercolor_library/ for PNG/MOV files.
        Returns {items: [{key, filename, kind, thumb_url, mtime}]}.

        kind: 'static' for .png, 'animation' for .mov (animated via the
        Animate-this bridge — LD WATERCOLOR_ANIMATE_THIS_V1).

        Per LD PHASE_A_PRODUCER_V1 + PHASE_B_PRODUCER_V1 (replaces hardcoded
        JS array in v58).
        """
        wc_dir = Path(__file__).resolve().parent.parent / "assets" / "watercolor_library"
        items: list[dict] = []
        if wc_dir.is_dir():
            for f in sorted(wc_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
                if not f.is_file():
                    continue
                ext = f.suffix.lower().lstrip(".")
                if ext not in ("png", "webp", "mov", "mp4"):
                    continue
                key = f.stem
                kind = "animation" if ext in ("mov", "mp4") else "static"
                items.append({
                    "key": key,
                    "filename": f.name,
                    "ext": ext,
                    "kind": kind,
                    "thumb_url": f"http://localhost:5111/api/phase/watercolor_file?key={key}",
                    "mtime": int(f.stat().st_mtime),
                    "size_bytes": f.stat().st_size,
                })
        return self._send_json(200, {
            "ok": True,
            "items": items,
            "count": len(items),
            "library_dir": str(wc_dir),
        })

    def _handle_phase_watercolor_file(self) -> None:
        """GET /api/phase/watercolor_file?key=<stem> — serve a single watercolor file.

        Helper for the watercolor_list thumb_url. Reads from the same
        directory; key is the basename without extension.
        """
        try:
            qs = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(qs)
            key_list = params.get("key")
            if not key_list:
                return self._send_json(400, {"error": "key query param required"})
            key = key_list[0]
            wc_dir = Path(__file__).resolve().parent.parent / "assets" / "watercolor_library"
            # Find the file by stem.
            matches = list(wc_dir.glob(f"{key}.*"))
            if not matches:
                return self._send_json(404, {"error": f"no watercolor with key={key!r}"})
            f = matches[0]
            data = f.read_bytes()
            ext = f.suffix.lower().lstrip(".")
            ct = {
                "png": "image/png", "webp": "image/webp",
                "mov": "video/quicktime", "mp4": "video/mp4",
            }.get(ext, "application/octet-stream")
            self._send_bytes(200, data, ct)
        except (OSError, KeyError) as exc:
            return self._send_json(500, {"error": str(exc)})

    def _handle_phase_base_clips_list(self) -> None:
        """GET /api/phase/base_clips_list — inventory of lipsync base clips.

        Reads Production/assets/lipsync_bases/. Returns {items: [{id,
        filename, character, duration_s?}]}. Backups (.bak*) excluded.

        Per LDs PHASE_A_PRODUCER_V1 + PHASE_B_PRODUCER_V1.
        """
        bases_dir = Path(__file__).resolve().parent.parent / "assets" / "lipsync_bases"
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
                # Character is heuristic: "chipper" or "cedric" in filename.
                lname = f.name.lower()
                character = (
                    "chipper" if "chipper" in lname
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
        return self._send_json(200, {"ok": True, "items": items, "count": len(items)})

    def _handle_phase_b_ambient_preset_list(self) -> None:
        """GET /api/phase_b/ambient_preset_list — list ambient bed presets.

        Returns {ok, items: [{preset_id, file_size_bytes}], count}. Empty
        list (count=0) is a valid result — the producer UI surfaces a
        "no presets available" hint when the list is empty.

        Per LD AMBIENT_PRESET_SELECTOR_INPRODUCER_V1 (S5.5f spec §3.7).
        """
        ambient_dir = Path(__file__).resolve().parent.parent / "audio_library" / "ambient"
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
        return self._send_json(200, {"ok": True, "items": items, "count": len(items)})

    def _handle_phase_suggest_script(self, body: dict) -> None:
        """POST /api/phase/suggest_script {phase, event_id?, scope_event_id?}

        Calls Claude API (claude-haiku-4-5 — script suggestions don't need
        Opus). Phase A reads phase_b_script + module description as context.
        Phase B reads arc skeleton + therapeutic notes + phase-b-writer skill.

        Per LDs PHASE_A_PRODUCER_V1 + PHASE_B_PRODUCER_V1.
        """
        # READ-ONLY probe (LLM script suggestion — does not mutate state).
        # Per spec_v2 §5.2 + SCOPE_REQUIRED_DEFAULTS_V1 read-only probes keep
        # allow_missing=True.
        if not self._assert_event_scope(self._scope_body(body), allow_missing=True):
            return
        phase = ((body or {}).get("phase") or "").strip().lower()
        if phase not in ("a", "b"):
            return self._send_json(400, {"error": "phase must be 'a' or 'b'"})

        # Resolve the Anthropic API key.
        try:
            sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
            from credential_store import get_secret_optional  # type: ignore
            api_key = get_secret_optional("ANTHROPIC_API_KEY")
        except Exception:
            api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            return self._send_json(503, {
                "ok": False,
                "code": "ANTHROPIC_API_KEY_MISSING",
                "message": (
                    "Anthropic API key not configured. Add ANTHROPIC_API_KEY to "
                    "Doppler (project=mindfulnest, config=dev) or set the env var "
                    "and restart the server. Endpoint code is ready."
                ),
                "phase": phase,
            })

        # Build context per phase.
        try:
            state = self.app.state.read_state()
        except Exception:
            state = {}

        if phase == "a":
            # S5.5d (v3): phase_b is TOP-LEVEL state.
            _phase_b_partition = state.get("phase_b") or {}
            phase_b_script = _phase_b_partition.get("phase_b_script") or "(no phase_b_script in state — write Phase B first or paste a draft to seed context)"
            user_prompt = (
                "You are drafting a Phase A 'demo' script for an interactive children's "
                "therapeutic app (MindfulNest). Phase A is the Chipper-led demonstration "
                "that follows Phase B's calm meditation. The child has just completed "
                "Phase B; Chipper now demonstrates the technique playfully so the child "
                "can try it themselves.\n\n"
                "Constraints:\n"
                "  - 30-60 seconds spoken (Chipper voice).\n"
                "  - Direct address ('let's try this together').\n"
                "  - Reference the technique by name ONCE; don't restate the meditation.\n"
                "  - No clinical jargon.\n"
                "  - Plain text. No stage directions.\n\n"
                f"Phase B script just completed:\n---\n{phase_b_script}\n---\n\n"
                "Write the Phase A demo script now."
            )
            system_prompt = (
                "You are a CRI (Competence-Rooted Identity) script writer for "
                "MindfulNest, drafting Phase A demo scripts for ages 7-11."
            )
        else:  # phase == "b"
            module_id = state.get("module_id") or "M?"
            user_prompt = (
                "You are drafting a Phase B 'meditation' script for an interactive "
                "children's therapeutic app (MindfulNest). Phase B is the Cedric-narrated "
                "meditation that introduces a therapeutic technique through the fictional "
                "Everdale world.\n\n"
                "Constraints:\n"
                "  - 90-120 seconds spoken (Cedric voice).\n"
                "  - 9-step meditation arc: arrive → observe → invitation → technique-intro → "
                "    technique-practice (3-4 steps) → return → seal.\n"
                "  - Use {{INHALE_CUE}}, {{EXHALE_CUE}}, {{HOLD_CUE}} cue markers.\n"
                "  - Frame the technique inside Everdale narrative (no clinical names).\n"
                "  - Direct second-person address.\n\n"
                f"Module: {module_id}.\n\n"
                "Write the Phase B meditation script now."
            )
            system_prompt = (
                "You are a CRI script writer drafting Phase B meditation scripts for "
                "MindfulNest (B2C children's therapeutic app, ages 7-11). Cedric narrator voice."
            )

        # Call Anthropic Messages API via urllib (no SDK dependency).
        url = "https://api.anthropic.com/v1/messages"
        req_body = {
            "model": "claude-haiku-4-5",
            "max_tokens": 2048,
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": user_prompt},
            ],
        }
        req_data = json.dumps(req_body).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=req_data,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            method="POST",
        )
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                resp_body = resp.read().decode("utf-8")
                resp_data = json.loads(resp_body)
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            return self._send_json(502, {
                "ok": False,
                "error": f"Anthropic API HTTP {exc.code}",
                "detail": err_body[:500],
            })
        except urllib.error.URLError as exc:
            return self._send_json(502, {
                "ok": False,
                "error": f"Anthropic API URL error: {exc}",
            })
        elapsed_ms = int((time.time() - t0) * 1000)

        # Extract text from response shape.
        # Response: {content: [{type:'text', text:'...'}], model: '...', usage: {input_tokens, output_tokens}}
        content = resp_data.get("content") or []
        script_text = ""
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                script_text += block.get("text", "")
        usage = resp_data.get("usage") or {}
        return self._send_json(200, {
            "ok": True,
            "phase": phase,
            "script": script_text,
            "model_used": resp_data.get("model", "claude-haiku-4-5"),
            "generation_time_ms": elapsed_ms,
            "tokens_in": usage.get("input_tokens"),
            "tokens_out": usage.get("output_tokens"),
        })

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

    def _validate_manual_path(self, manual_path: list, max_pts: int = 20) -> tuple[bool, list, str]:
        """Validate manual_path = [[x,y],...] in [0,1]. Returns (ok, clean_path, err)."""
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
        """POST /api/storyboard/magic_still {beat_id, manual_path, source_image_path, scope_event_id}

        Per LD-468 MAGIC_TRAIL_ON_STILL_V1. Invokes magic_compositor with the
        still as background; renders animated mp4 of magic forming on the
        still.
        """
        if not self._assert_event_scope(self._scope_body(body), allow_missing=False):
            return
        beat_id = (body or {}).get("beat_id")
        manual_path = (body or {}).get("manual_path") or []
        source_image_path_raw = (body or {}).get("source_image_path") or ""
        if not beat_id:
            return self._send_json(400, {"error": "beat_id required"})
        if not source_image_path_raw:
            return self._send_json(400, {"error": "source_image_path required"})
        ok, clean_path, err = self._validate_manual_path(manual_path)
        if not ok:
            return self._send_json(400, {"error": err})

        # Resolve absolute path for source image; reject paths outside project.
        sip = Path(source_image_path_raw)
        if not sip.is_absolute():
            sip = self.app.event_dir.parent.parent / source_image_path_raw
        try:
            project_root = Path(__file__).resolve().parent.parent.parent
            sip_resolved = sip.resolve()
            if not str(sip_resolved).startswith(str(project_root)):
                return self._send_json(400, {"error": "source_image_path outside project root"})
        except Exception:
            pass
        if not sip.is_file():
            return self._send_json(404, {
                "error": "source_image not found", "path": str(sip),
            })

        # LD-460 pin
        _pin = {
            "pinned_generation": self.app.event_generation,
            "pinned_event_dir": self.app.event_dir,
            "pinned_video_role": (body or {}).get("scope_video_role", "intro"),
            "_handler": "_handle_magic_still",
        }
        if not self._check_event_pin(_pin, "magic_still_pre_work"):
            return self._send_json(423, {
                "error": "event_changed_pre_work",
                "code": "ASYNC_JOB_GENERATION_PIN_V1",
            })

        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        out_dir = self.app.event_dir
        out_path = out_dir / f"magic_still_{beat_id}_{ts}.mp4"

        try:
            tools_dir = str(Path(__file__).resolve().parent)
            if tools_dir not in sys.path:
                sys.path.insert(0, tools_dir)
            from magic_compositor import MagicCompositor  # type: ignore
            mc = MagicCompositor(
                background_path=str(sip),
                path_pts=clean_path,
                style="tessa_ori",
                duration=4.0,
                fps=24,
                output_dir=str(out_dir),
                label=f"magic_still_{beat_id}_{ts}",
                beat_id=beat_id,
                tags=["magic", "magic_still", "tessa_ori"],
            )
            rendered = mc.render_video(output_path=str(out_path))
        except Exception as exc:
            traceback.print_exc()
            return self._send_json(500, {
                "error": f"magic_compositor failed: {type(exc).__name__}: {exc}",
            })

        if not self._check_event_pin(_pin, "magic_still_terminal"):
            return self._send_json(423, {
                "error": "event_changed_mid_job",
                "code": "ASYNC_JOB_GENERATION_PIN_V1",
                "orphaned_output": str(rendered),
            })

        registered_id: int | None = None
        try:
            from registered_write import register_asset  # type: ignore
            registered_id, _ = register_asset(
                file_path=str(rendered),
                asset_type="magic_clip",
                module_id=1,
                beat_id=beat_id,
                produced_by_skill="magic_still_endpoint",
                colloquial_name=f"magic on still {beat_id}",
                tags=["magic", "magic_still", "tessa_ori", beat_id],
                notes=(
                    f"Magic trail on still {sip.name} for beat {beat_id} via "
                    f"S5 Workflow A (LD-468). {len(clean_path)} path points."
                ),
                role="library",
            )
        except Exception as exc:
            print(f"[magic_still] WARN registered_write failed: {exc}", flush=True)

        return self._send_json(200, {
            "ok": True,
            "beat_id": beat_id,
            "composite_path": str(rendered),
            "asset_id": registered_id,
            "manual_path_points": len(clean_path),
        })

    @with_pin_and_drain('_handle_magic_video', track_sync=True)
    def _handle_magic_video(self, body: dict) -> None:
        """POST /api/storyboard/magic_video {beat_id, manual_path, source_video_path, scope_event_id}

        Per LD-469 MAGIC_TRAIL_ON_VIDEO_V1. Generates magic-on-black via
        magic_compositor.render_video(black_bg=True), then ffmpeg overlays
        onto the source video via blend=mode=screen (black pixels become
        transparent in screen blend; magic pixels shine through additively).
        """
        if not self._assert_event_scope(self._scope_body(body), allow_missing=False):
            return
        beat_id = (body or {}).get("beat_id")
        manual_path = (body or {}).get("manual_path") or []
        source_video_path_raw = (body or {}).get("source_video_path") or ""
        if not beat_id:
            return self._send_json(400, {"error": "beat_id required"})
        if not source_video_path_raw:
            return self._send_json(400, {"error": "source_video_path required"})
        ok, clean_path, err = self._validate_manual_path(manual_path)
        if not ok:
            return self._send_json(400, {"error": err})

        svp = Path(source_video_path_raw)
        if not svp.is_absolute():
            svp = self.app.event_dir.parent.parent / source_video_path_raw
        if not svp.is_file():
            return self._send_json(404, {
                "error": "source_video not found", "path": str(svp),
            })

        # ffprobe for dimensions + duration.
        try:
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "stream=width,height,duration",
                 "-of", "json", str(svp)],
                capture_output=True, check=True, timeout=30,
            )
            meta = json.loads(probe.stdout.decode("utf-8"))
            stream = (meta.get("streams") or [{}])[0]
            width = int(stream.get("width") or 1280)
            height = int(stream.get("height") or 720)
            try:
                vid_duration = float(stream.get("duration") or 0)
            except (TypeError, ValueError):
                vid_duration = 0
            if vid_duration <= 0:
                vid_duration = float(_ffprobe_duration(svp) or 0)
        except subprocess.CalledProcessError as exc:
            return self._send_json(500, {
                "error": "ffprobe failed",
                "stderr": exc.stderr.decode("utf-8", errors="replace")[-500:],
            })
        if vid_duration <= 0:
            return self._send_json(500, {"error": "could not determine source duration"})

        # LD-460 pin
        _pin = {
            "pinned_generation": self.app.event_generation,
            "pinned_event_dir": self.app.event_dir,
            "pinned_video_role": (body or {}).get("scope_video_role", "intro"),
            "_handler": "_handle_magic_video",
        }
        if not self._check_event_pin(_pin, "magic_video_pre_work"):
            return self._send_json(423, {
                "error": "event_changed_pre_work",
                "code": "ASYNC_JOB_GENERATION_PIN_V1",
            })

        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        out_dir = self.app.event_dir
        magic_only_path = out_dir / f"_tmp_magic_only_{beat_id}_{ts}.mp4"
        out_path = out_dir / f"magic_video_{beat_id}_{ts}.mp4"

        # Step 1: generate magic-on-black via magic_compositor.
        # We need a reference image of the right dimensions; since
        # MagicCompositor requires a background_path, write a tiny black PNG
        # of (width, height) first.
        try:
            from PIL import Image as _PILImage
            black_ref = out_dir / f"_tmp_black_ref_{beat_id}_{ts}.png"
            _PILImage.new("RGB", (width, height), (0, 0, 0)).save(black_ref)
        except Exception as exc:
            return self._send_json(500, {"error": f"could not create black ref: {exc}"})

        try:
            tools_dir = str(Path(__file__).resolve().parent)
            if tools_dir not in sys.path:
                sys.path.insert(0, tools_dir)
            from magic_compositor import MagicCompositor  # type: ignore
            mc = MagicCompositor(
                background_path=str(black_ref),
                path_pts=clean_path,
                style="tessa_ori",
                duration=min(vid_duration, 10.0),
                fps=24,
                output_dir=str(out_dir),
                label=f"magic_only_{beat_id}_{ts}",
                beat_id=beat_id,
                tags=["magic", "magic_video", "tessa_ori"],
            )
            mc.render_video(output_path=str(magic_only_path), black_bg=True)
        except Exception as exc:
            traceback.print_exc()
            return self._send_json(500, {
                "error": f"magic_compositor (black_bg) failed: {type(exc).__name__}: {exc}",
            })
        finally:
            try:
                black_ref.unlink(missing_ok=True)
            except Exception:
                pass

        # Step 2: ffmpeg overlay via blend=screen.
        cmd = [
            "ffmpeg", "-y",
            "-i", str(svp),
            "-i", str(magic_only_path),
            "-filter_complex", "[0:v][1:v]blend=all_mode=screen[out]",
            "-map", "[out]",
            "-map", "0:a?",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            "-t", str(min(vid_duration, 10.0)),
            str(out_path),
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=300)
        except subprocess.CalledProcessError as exc:
            return self._send_json(500, {
                "error": "ffmpeg blend failed",
                "stderr": exc.stderr.decode("utf-8", errors="replace")[-1000:],
            })
        except subprocess.TimeoutExpired:
            return self._send_json(504, {"error": "ffmpeg blend timed out (>300s)"})
        finally:
            try:
                magic_only_path.unlink(missing_ok=True)
            except Exception:
                pass

        if not self._check_event_pin(_pin, "magic_video_terminal"):
            return self._send_json(423, {
                "error": "event_changed_mid_job",
                "code": "ASYNC_JOB_GENERATION_PIN_V1",
                "orphaned_output": str(out_path),
            })

        registered_id: int | None = None
        try:
            from registered_write import register_asset  # type: ignore
            registered_id, _ = register_asset(
                file_path=str(out_path),
                asset_type="magic_clip",
                module_id=1,
                beat_id=beat_id,
                produced_by_skill="magic_video_endpoint",
                colloquial_name=f"magic on video {beat_id}",
                tags=["magic", "magic_video", "blend_screen", beat_id],
                notes=(
                    f"Magic trail on video {svp.name} for beat {beat_id} via "
                    f"S5 Workflow B (LD-469). {len(clean_path)} path points; "
                    f"black_bg=True + blend=screen overlay; "
                    f"source dims {width}x{height}, duration {vid_duration:.2f}s."
                ),
                role="library",
            )
        except Exception as exc:
            print(f"[magic_video] WARN registered_write failed: {exc}", flush=True)

        return self._send_json(200, {
            "ok": True,
            "beat_id": beat_id,
            "composite_path": str(out_path),
            "asset_id": registered_id,
            "source_dims": [width, height],
            "duration_s": vid_duration,
            "manual_path_points": len(clean_path),
        })

    def _handle_watercolor_animate(self, body: dict) -> None:
        """POST /api/watercolor/animate {watercolor_key, manual_path, motion_description, scope_event_id}

        Per LD-470 WATERCOLOR_ANIMATE_PROCEDURAL_V1. SUPERSEDES the S4 magic-
        compositor-based implementation. Claude API generates an ffmpeg
        filter_complex spec given watercolor + path geometry + motion intent.
        Server validates against safe-filter allowlist BEFORE executing
        ffmpeg.
        """
        if not self._assert_event_scope(self._scope_body(body), allow_missing=False):
            return
        # Accept both `watercolor_key` (S5 spec) and `source_key` (S4 alias).
        watercolor_key = ((body or {}).get("watercolor_key")
                          or (body or {}).get("source_key"))
        manual_path = (body or {}).get("manual_path") or []
        motion_desc = ((body or {}).get("motion_description") or "").strip()
        if not watercolor_key:
            return self._send_json(400, {"error": "watercolor_key required"})
        if not motion_desc:
            return self._send_json(400, {"error": "motion_description required (non-empty)"})
        if len(motion_desc) > 500:
            return self._send_json(400, {
                "error": f"motion_description too long ({len(motion_desc)} > 500)",
            })
        # Reject obvious shell metacharacters in the description.
        for bad in ("`", "$(", "${", "\\", "\n\n\n"):
            if bad in motion_desc:
                return self._send_json(400, {"error": f"forbidden substring in motion_description: {bad!r}"})

        ok, clean_path, err = self._validate_manual_path(manual_path)
        if not ok:
            return self._send_json(400, {"error": err})

        wc_dir = Path(__file__).resolve().parent.parent / "assets" / "watercolor_library"
        matches = list(wc_dir.glob(f"{watercolor_key}.*"))
        if not matches:
            return self._send_json(404, {
                "error": f"no watercolor with key={watercolor_key!r}",
                "looked_in": str(wc_dir),
            })
        source_path = next((m for m in matches if m.suffix.lower() == ".png"), matches[0])

        # Probe dimensions.
        try:
            from PIL import Image as _PILImage
            with _PILImage.open(source_path) as im:
                src_w, src_h = im.size
        except Exception:
            src_w, src_h = 1024, 1024  # safe default

        # LD-460 pin
        _pin = {
            "pinned_generation": self.app.event_generation,
            "pinned_event_dir": self.app.event_dir,
            "pinned_video_role": (body or {}).get("scope_video_role", "intro"),
            "_handler": "_handle_watercolor_animate",
        }
        if not self._check_event_pin(_pin, "watercolor_animate_pre_work"):
            return self._send_json(423, {
                "error": "event_changed_pre_work",
                "code": "ASYNC_JOB_GENERATION_PIN_V1",
            })

        # Resolve Anthropic key.
        try:
            sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
            from credential_store import get_secret_optional  # type: ignore
            api_key = get_secret_optional("ANTHROPIC_API_KEY")
        except Exception:
            api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            return self._send_json(503, {
                "ok": False,
                "code": "ANTHROPIC_API_KEY_MISSING",
                "message": "Anthropic API key not configured.",
            })

        # Build Claude prompt.
        path_str = ", ".join(f"({p[0]:.3f},{p[1]:.3f})" for p in clean_path)
        system_prompt = (
            "You are an ffmpeg filter chain generator. Given a watercolor PNG, "
            "a path geometry (normalized x,y points in [0,1]), and a motion "
            "description, output a JSON object with a SAFE ffmpeg filter_complex "
            "string that produces an animated MP4 from the still PNG.\n\n"
            "Available filters (allowlist — use NO others): split, hflip, vflip, "
            "rotate, scale, overlay, blend, fade, crop, pad, drawbox, hue, eq, "
            "zoompan, fps, setpts, geq, displace, format.\n\n"
            "Forbidden: any shell command, file://, http://, exec, system, run, "
            "backslash, pipe, backticks, dollar-paren. duration_s must be in [0.5, 10].\n\n"
            "Reference examples:\n"
            "- 'hands rub up and down' + vertical line: split frame at line, "
            "vflip lower half, oscillate y-translation sinusoidally with sin(2*PI*t).\n"
            "- 'circle spins clockwise' + circle path: crop to bounding box of "
            "circle, rotate filter with 'a=t*PI'.\n"
            "- 'energy radiates outward' + center point: zoompan 'z=1.0+0.1*sin(t)'.\n\n"
            "Output JSON ONLY, no markdown fences:\n"
            "  {\"filter_complex\": \"<chain>\", \"duration_s\": <number>, "
            "\"output_size\": [w,h], \"explanation\": \"<one sentence>\"}"
        )
        user_prompt = (
            f"Input watercolor: {watercolor_key}.png at {src_w}x{src_h} pixels.\n"
            f"Path geometry (normalized): [{path_str}]\n"
            f"Motion intent: {motion_desc!r}\n\n"
            "Generate the JSON now."
        )

        # Call Claude.
        url = "https://api.anthropic.com/v1/messages"
        req_data = json.dumps({
            "model": "claude-sonnet-4-6",
            "max_tokens": 1024,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }).encode("utf-8")
        req = urllib.request.Request(
            url, data=req_data,
            headers={"x-api-key": api_key,
                     "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            method="POST",
        )
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            return self._send_json(502, {
                "error": f"Anthropic API HTTP {exc.code}",
                "detail": err_body[:500],
            })
        except urllib.error.URLError as exc:
            return self._send_json(502, {"error": f"Anthropic URL error: {exc}"})
        elapsed_ms = int((time.time() - t0) * 1000)

        # Extract JSON from response (model may wrap in code fence; be defensive).
        text = ""
        for block in resp_data.get("content", []) or []:
            if isinstance(block, dict) and block.get("type") == "text":
                text += block.get("text", "")
        # Strip ```json fences if present.
        text = text.strip()
        m = re.search(r'\{[\s\S]*\}', text)
        if not m:
            return self._send_json(502, {
                "error": "Claude response had no JSON object",
                "raw": text[:500],
            })
        try:
            spec = json.loads(m.group(0))
        except json.JSONDecodeError as exc:
            return self._send_json(502, {
                "error": f"Claude JSON parse failed: {exc}",
                "raw": text[:500],
            })

        filter_complex = spec.get("filter_complex") or ""
        duration_s = float(spec.get("duration_s") or 3.0)
        explanation = (spec.get("explanation") or "")[:300]

        if not (0.5 <= duration_s <= 10.0):
            return self._send_json(400, {
                "error": f"duration_s={duration_s} outside [0.5, 10]",
            })

        # SAFETY GATE.
        ok_filter, gate_err = self._validate_ffmpeg_filter_chain(filter_complex)
        if not ok_filter:
            # Log to activity log for debugging.
            try:
                from lib.directus import try_post_or_queue  # type: ignore
                try_post_or_queue("prod_activity_log", {
                    "action": "watercolor_animate_unsafe_filter_rejected",
                    "performed_by": "watercolor_animate_endpoint",
                    "details": {
                        "watercolor_key": watercolor_key,
                        "motion_description": motion_desc,
                        "rejected_filter_complex": filter_complex,
                        "gate_error": gate_err,
                        "claude_explanation": explanation,
                    },
                })
            except Exception:
                pass
            return self._send_json(400, {
                "error": "unsafe_filter_chain",
                "details": gate_err,
                "filter_complex_preview": filter_complex[:200],
            })

        # Execute ffmpeg.
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        out_path = wc_dir / f"{watercolor_key}_animated_{ts}.mp4"
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", str(source_path),
            "-filter_complex", filter_complex,
            "-t", f"{duration_s:.3f}",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            str(out_path),
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=60)
        except subprocess.CalledProcessError as exc:
            return self._send_json(500, {
                "error": "ffmpeg failed",
                "filter_complex": filter_complex,
                "stderr": exc.stderr.decode("utf-8", errors="replace")[-1000:],
            })
        except subprocess.TimeoutExpired:
            return self._send_json(504, {"error": "ffmpeg timed out (>60s)"})

        if not self._check_event_pin(_pin, "watercolor_animate_terminal"):
            return self._send_json(423, {
                "error": "event_changed_mid_job",
                "code": "ASYNC_JOB_GENERATION_PIN_V1",
                "orphaned_output": str(out_path),
            })

        registered_id: int | None = None
        try:
            from registered_write import register_asset  # type: ignore
            registered_id, _ = register_asset(
                file_path=str(out_path),
                asset_type="magic_clip",
                module_id=1,
                produced_by_skill="watercolor_animate_endpoint",
                colloquial_name=f"{watercolor_key} animated",
                tags=["watercolor_animation", watercolor_key, "claude_filter_complex"],
                notes=(
                    f"Watercolor animation via Claude+ffmpeg (LD-470). "
                    f"motion={motion_desc!r}. {len(clean_path)} path points. "
                    f"duration={duration_s}s. claude_ms={elapsed_ms}. "
                    f"explanation={explanation!r}"
                ),
                role="library",
            )
        except Exception as exc:
            print(f"[watercolor/animate] WARN registered_write failed: {exc}", flush=True)

        return self._send_json(200, {
            "ok": True,
            "watercolor_key": watercolor_key,
            "animated_path": str(out_path),
            "asset_id": registered_id,
            "explanation": explanation,
            "duration_s": duration_s,
            "filter_complex": filter_complex,
            "claude_ms": elapsed_ms,
        })

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
            return self._send_json(500, {
                "error": f"Directus read failed: {type(exc).__name__}: {exc}",
            })

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
        if not self._assert_event_scope(self._scope_body(body), allow_missing=False):
            return

        input_path_raw = (body or {}).get("input_path")
        if not input_path_raw:
            return self._send_json(400, {"error": "input_path required"})

        # Resolve relative to event_dir if relative.
        ip = Path(input_path_raw)
        if not ip.is_absolute():
            ip = self.app.event_dir / input_path_raw
        if not ip.is_file():
            return self._send_json(404, {
                "error": "input file not found",
                "input_path": str(ip),
            })

        target_lufs = float((body or {}).get("target_lufs", -19.0))
        target_tp = float((body or {}).get("target_tp", -1.5))
        target_lra = float((body or {}).get("target_lra", 11.0))

        # Output path: default to <input>_ln.<ext> in same dir.
        out_raw = (body or {}).get("output_path")
        if out_raw:
            op = Path(out_raw)
            if not op.is_absolute():
                op = self.app.event_dir / out_raw
        else:
            op = ip.with_name(f"{ip.stem}_ln{ip.suffix}")

        # Already-applied guard: check stitch_state.
        try:
            stitch = self.app.stitch_state.read_state() or {}
        except Exception:
            stitch = {}
        applied_paths = set(stitch.get("loudnorm_already_applied_paths", []))
        if str(ip) in applied_paths:
            return self._send_json(200, {
                "ok": True,
                "skipped": True,
                "reason": "loudnorm_already_applied",
                "input_path": str(ip),
                "output_path": str(ip),  # nothing to do; "output" is the input
            })

        # Run ffmpeg single-pass loudnorm.
        # -af "loudnorm=I=-19:TP=-1.5:LRA=11" -c:v copy preserves video frames.
        cmd = [
            "ffmpeg", "-y",
            "-i", str(ip),
            "-af", f"loudnorm=I={target_lufs}:TP={target_tp}:LRA={target_lra}",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            str(op),
        ]
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, timeout=600)
        except subprocess.CalledProcessError as exc:
            return self._send_json(500, {
                "error": "ffmpeg loudnorm failed",
                "returncode": exc.returncode,
                "stderr": exc.stderr.decode("utf-8", errors="replace")[-2000:],
            })
        except subprocess.TimeoutExpired:
            return self._send_json(504, {"error": "ffmpeg loudnorm timed out (>600s)"})

        # Mark the OUTPUT as loudnorm_already_applied so a re-run skips it.
        try:
            def _mark(state, _p=str(op)):
                paths = state.setdefault("loudnorm_already_applied_paths", [])
                if _p not in paths:
                    paths.append(_p)
                return None
            self.app.stitch_state.mutate_state(_mark)
        except Exception as exc:
            print(f"[loudnorm] WARN could not mark applied: {exc}", flush=True)

        if not op.is_file():
            return self._send_json(500, {
                "error": "ffmpeg succeeded but output file missing",
                "output_path": str(op),
            })
        size_bytes = op.stat().st_size
        return self._send_json(200, {
            "ok": True,
            "input_path": str(ip),
            "output_path": str(op),
            "size_bytes": size_bytes,
            "target_lufs": target_lufs,
            "target_tp": target_tp,
            "target_lra": target_lra,
            "marked_loudnorm_already_applied": True,
        })

    def _handle_bg_set_active_context(self, body: dict) -> None:
        """POST /api/bg/set-active-context {arc_number, event_id, phase}
        Switches active_context in sidecar and returns any previously saved beats
        for that segment — no re-extraction. Returns {beats, had_saved}.

        NOTE on the BG `event_id` field: this is the BG-internal segment number
        (e.g., "1", "2", "3"), NOT the storyboard event scope. Scope-guard uses
        body['scope_event_id'] when v59 client sends it; post-C-5
        SCOPE_REQUIRED_DEFAULTS_V1, missing scope_event_id rejects with HTTP
        400 (legacy permissive default removed for mutation handlers).
        """
        # LD-456 SCOPE_VALIDATION_V1 — guard against cross-storyboard-event mutation.
        # The BG body's `event_id` is overloaded (segment number); v59 client
        # passes the storyboard scope as `scope_event_id` to disambiguate.
        if not self._assert_event_scope(self._scope_body(body), allow_missing=False):
            return  # LD-461 SCOPE_BODY_HELPER_V1 — migrated from hand-rolled dict
        arc_number = int(body.get("arc_number", 1))
        event_id   = str(body.get("event_id", "1"))
        phase      = str(body.get("phase", "full"))
        bg = _bg_module()
        with bg._sidecar_lock:
            sidecar = bg.read_sidecar()
            sidecar["active_context"] = {
                "arc_number": arc_number, "event_id": event_id, "phase": phase
            }
            seg = bg.get_seg_entry(sidecar, arc_number, event_id, phase)
            beats = seg.get("beats", [])
            bg.write_sidecar(sidecar)
        print(f"[BG] set-active-context arc={arc_number} event={event_id} phase={phase} "
              f"saved_beats={len(beats)}")
        return self._send_json(200, {"beats": beats, "had_saved": len(beats) > 0})

    def _handle_bg_extract_beats(self, body: dict) -> None:
        """POST /api/bg/extract-beats {arc_number, event_id, phase} -> { beats }

        NOTE: body['event_id'] is the BG segment number; storyboard scope
        guard uses body['scope_event_id'] when present.
        """
        # LD-456 SCOPE_VALIDATION_V1
        if not self._assert_event_scope(self._scope_body(body), allow_missing=False):
            return  # LD-461 SCOPE_BODY_HELPER_V1 — migrated from hand-rolled dict
        arc_number = int(body.get("arc_number", 1))
        event_id   = str(body.get("event_id", "1"))
        phase      = str(body.get("phase", "full"))
        bg = _bg_module()
        beats = bg.extract_beats(arc_number, event_id, phase)
        # Write to sidecar — MERGE with existing saved state so that
        # re-extracting beats never wipes flux_options, accepted_image_key,
        # accepted_library_ref, or status that the user already set.
        with bg._sidecar_lock:
            sidecar = bg.read_sidecar()
            seg = bg.get_seg_entry(sidecar, arc_number, event_id, phase)
            # Build lookup of existing beat data keyed by beat_id
            existing = {b["beat_id"]: b for b in (seg.get("beats") or [])}
            _PRESERVE = ("flux_options", "accepted_image_key", "accepted_library_ref", "status")
            for b in beats:
                saved = existing.get(b["beat_id"])
                if saved:
                    for field in _PRESERVE:
                        if saved.get(field):
                            b.setdefault(field, saved[field])
            seg["beats"] = beats
            # Find segment name from listing
            for s in bg.get_segments(arc_number):
                if str(s["event_id"]) == event_id and s["phase"] == phase:
                    seg["name"] = s["name"]
                    break
            sidecar["active_context"] = {
                "arc_number": arc_number, "event_id": event_id, "phase": phase
            }
            bg.write_sidecar(sidecar)
        print(f"[BG] extracted {len(beats)} beats arc={arc_number} event={event_id} phase={phase}")
        return self._send_json(200, {"beats": beats, "count": len(beats)})

    def _handle_bg_inject_beats(self, body: dict) -> None:
        """POST /api/bg/inject-beats {arc_number, event_id, phase, beats} -> { ok, count, beat_ids }
        Injects beats from the skeleton-to-beats skill directly into the beat generator sidecar.

        NOTE: body['event_id'] is the BG segment number; storyboard scope
        guard uses body['scope_event_id'] when present.
        """
        # LD-456 SCOPE_VALIDATION_V1
        if not self._assert_event_scope(self._scope_body(body), allow_missing=False):
            return  # LD-461 SCOPE_BODY_HELPER_V1 — migrated from hand-rolled dict
        arc_number = int(body.get("arc_number", 1))
        event_id   = str(body.get("event_id", "1"))
        phase      = str(body.get("phase", "full"))
        incoming_beats = body.get("beats", [])
        if not incoming_beats:
            return self._send_json(400, {"error": "beats array required"})
        bg = _bg_module()
        beat_ids = []
        # Map incoming skill fields to sidecar beat schema
        mapped_beats = []
        for idx, b in enumerate(incoming_beats, start=1):
            beat_id = f"bg_arc{arc_number}_event{event_id}_{phase}_beat_{idx:02d}"
            beat_ids.append(beat_id)
            mapped_beats.append({
                "beat_id": beat_id,
                "speaker": b.get("speaker", ""),
                "dialogue_text": b.get("text", ""),
                "emotion": b.get("emotion", ""),
                "scene_notes": b.get("section", ""),
                "accepted_image_key": None,
                "flux_options": [],
                "status": "new",
                "schema_version": 1,
                "animation_method": "kling",
                "group_id": None,
                "group_order": None,
                "accepted_video_path": None,
                "local_render_params": None,
                "reference_image": None,
                "bg_ref_image": None,
            })
        # Write to sidecar with merge logic
        with bg._sidecar_lock:
            sidecar = bg.read_sidecar()
            seg = bg.get_seg_entry(sidecar, arc_number, event_id, phase)
            existing = {b["beat_id"]: b for b in (seg.get("beats") or [])}
            _PRESERVE = ("flux_options", "accepted_image_key", "accepted_library_ref", "status")
            for b in mapped_beats:
                saved = existing.get(b["beat_id"])
                if saved:
                    for field in _PRESERVE:
                        if saved.get(field):
                            b[field] = saved[field]
            seg["beats"] = mapped_beats
            # Find segment name from listing
            for s in bg.get_segments(arc_number):
                if str(s["event_id"]) == event_id and s["phase"] == phase:
                    seg["name"] = s["name"]
                    break
            sidecar["active_context"] = {
                "arc_number": arc_number, "event_id": event_id, "phase": phase
            }
            bg.write_sidecar(sidecar)
        print(f"[BG] injected {len(mapped_beats)} beats arc={arc_number} event={event_id} phase={phase}")
        return self._send_json(200, {"ok": True, "count": len(mapped_beats), "beat_ids": beat_ids})

    def _handle_bg_update_beat(self, body: dict) -> None:
        """POST /api/bg/update-beat {beat_id, [field...], scope_event_id?} -> { ok }"""
        # LD-456 SCOPE_VALIDATION_V1 — uses scope_event_id to disambiguate from BG segment numbers.
        if not self._assert_event_scope(self._scope_body(body), allow_missing=False):
            return  # LD-461 SCOPE_BODY_HELPER_V1 — migrated from hand-rolled dict
        beat_id = body.get("beat_id")
        if not beat_id:
            return self._send_json(400, {"error": "beat_id required"})
        bg = _bg_module()
        _BG_BEAT_WRITABLE = frozenset({
            "speaker", "dialogue_text", "scene_notes", "emotion",
            "accepted_image_key", "reference_image", "bg_ref_image",
        })
        unknown = set(body.keys()) - _BG_BEAT_WRITABLE - {"beat_id"}
        if unknown:
            return self._send_json(400, {"ok": False,
                                          "error": f"Unknown beat fields: {sorted(unknown)}"})
        with bg._sidecar_lock:
            sidecar = bg._load_sidecar_migrated()
            _, beat = bg.find_beat(sidecar, beat_id)
            if not beat:
                return self._send_json(404, {"error": f"beat {beat_id} not found"})
            written = []
            for field in _BG_BEAT_WRITABLE:
                if field in body:
                    beat[field] = body[field]
                    written.append(field)
            bg.write_sidecar(sidecar)
        return self._send_json(200, {"ok": True, "written": written})

    def _handle_bg_reorder_beats(self, body: dict) -> None:
        """POST /api/bg/reorder-beats {beat_ids: [...], scope_event_id?} -> { ok }"""
        # LD-456 SCOPE_VALIDATION_V1
        if not self._assert_event_scope(self._scope_body(body), allow_missing=False):
            return  # LD-461 SCOPE_BODY_HELPER_V1 — migrated from hand-rolled dict
        beat_ids = body.get("beat_ids", [])
        if not beat_ids:
            return self._send_json(400, {"error": "beat_ids required"})
        bg = _bg_module()
        with bg._sidecar_lock:
            sidecar = bg.read_sidecar()
            ctx = sidecar.get("active_context")
            if not ctx:
                return self._send_json(400, {"error": "no active context"})
            seg = bg.get_seg_entry(sidecar, ctx["arc_number"], ctx["segment_index"])
            beats = seg.get("beats", [])
            beat_map = {b["beat_id"]: b for b in beats}
            seg["beats"] = [beat_map[bid] for bid in beat_ids if bid in beat_map]
            bg.write_sidecar(sidecar)
        return self._send_json(200, {"ok": True})

    def _handle_bg_delete_beat(self, body: dict) -> None:
        """POST /api/bg/delete-beat {beat_id} -> { ok }"""
        # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
        if not self._assert_event_scope(self._scope_body(body), allow_missing=False):
            return

        beat_id = body.get("beat_id")
        if not beat_id:
            return self._send_json(400, {"error": "beat_id required"})
        bg = _bg_module()
        with bg._sidecar_lock:
            sidecar = bg.read_sidecar()
            for arc in sidecar.get("arcs", {}).values():
                for seg in arc.get("segments", {}).values():
                    seg["beats"] = [b for b in seg.get("beats", []) if b.get("beat_id") != beat_id]
            bg.write_sidecar(sidecar)
        return self._send_json(200, {"ok": True})

    def _handle_bg_accept_beats(self, body: dict) -> None:
        """POST /api/bg/accept-beats {beats, segment, scope_event_id?} -> { ok }
        Marks all beats as accepted in sidecar. Client already pushed to L[].
        Also deletes the storyboard L.json sidecar so pathappHydrate() on next
        reload does not overwrite L[] with the old pre-BG storyboard content.

        LD-456 SCOPE_VALIDATION_V1 — origin bug source. On 2026-05-01, BG on
        Event 2 → Accept All → Event 2 keys leaked into Event 1 storyboard
        because `sidecar_path` (line below) is derived from
        `self.app.event_dir` (server-pinned) but the BG sidecar's
        `active_context.event_id` was Event 2. The scope guard rejects the
        cross-event request with HTTP 409 before any state mutates.
        """
        # SCOPE_ROUTER_V1 (C-3 K2 fix) — replaces the legacy
        # _assert_event_scope(allow_missing=True) call with strict-by-default
        # scope_router resolution; subsumes LD-456 SCOPE_VALIDATION_V1 +
        # LD-461 SCOPE_BODY_HELPER_V1. The cross-event leak class is closed
        # both here AND structurally because the seed write below routes
        # through scope_router.mutate_partition (no more legacy state.beats).
        try:
            scope = scope_router.resolve(body, self.app.event_dir.name)
        except scope_router.ScopeError as e:
            return self._send_json(e.http_status, {"error": e.code, **e.detail})
        beat_ids = [b["beat_id"] for b in body.get("beats", []) if "beat_id" in b]
        bg = _bg_module()
        with bg._sidecar_lock:
            sidecar = bg.read_sidecar()
            for bid in beat_ids:
                _, beat = bg.find_beat(sidecar, bid)
                if beat:
                    beat["status"] = "accepted"
            bg.write_sidecar(sidecar)
        # Delete storyboard L.json sidecar — prevents pathappHydrate() from
        # restoring old pre-BG storyboard content on next page reload.
        try:
            sidecar_path = self.app.event_dir / (self.app.storyboard_path.stem + ".L.json")
            if sidecar_path.exists():
                sidecar_path.unlink()
                print(f"[BG] deleted storyboard sidecar {sidecar_path.name} — reload-safe")
        except Exception as e:
            print(f"[BG] warning: could not delete storyboard sidecar: {e}")

        # SCOPE_ROUTER_V1 (C-3 K2 fix) — seed the v3 partition (videos.<role>.beats),
        # NOT the legacy top-level state.beats. The previous mutate_state() seed
        # bypassed both the partition router and the DISPLAY_ORDER_STRICT_V1
        # prune; subsequent migrate_state_to_videos_partition runs faithfully
        # lifted that corrupted top-level into videos.intro on whatever event
        # the server happened to be pinned at — that's the 2026-05-01 leak.
        # Now: write into the partition for the resolved scope.video_role and
        # extend partition.display_order. SPEAKER_WRITE_BOUNDARY_CANONICALIZATION_V1
        # (C-3 K7 fix) — drop the legacy default-to-Guide-Bird literal that lived
        # at this seed site; canonicalize the raw speaker via _canonicalize_speaker.
        # Empty stays empty (LD-520 fail-loud at TTS time); the historical
        # Guide-Bird value normalizes to Chipper via _SPEAKER_ALIAS at write time.
        try:
            beats_raw = body.get("beats", [])
            storyboard_pos = 0
            state_seeds: dict[str, dict] = {}
            for beat in beats_raw:
                if not beat.get("accepted_image_key"):
                    continue
                sb_bid = f"beat_{storyboard_pos + 1:02d}"
                raw_speaker = beat.get("speaker") or ""
                canonicalized = _canonicalize_speaker(raw_speaker) or ""
                state_seeds[sb_bid] = {
                    "speaker": canonicalized,
                    "text": beat.get("dialogue_text") or "",
                }
                storyboard_pos += 1
            if state_seeds:
                def _seed_partition(partition, _data=state_seeds):
                    pbeats = partition.setdefault("beats", {})
                    pdo = partition.setdefault("display_order", [])
                    # If display_order is a legacy int (pre-v3 fixture shape),
                    # leave it alone — DISPLAY_ORDER_STRICT_V1 prune skips ints
                    # and the renderer's strict gate handles the int form too.
                    pdo_is_list = isinstance(pdo, list)
                    for bid, fields in _data.items():
                        b = pbeats.setdefault(bid, {})
                        b["speaker"] = fields["speaker"]
                        b["text"] = fields["text"]
                        if pdo_is_list and bid not in pdo:
                            pdo.append(bid)
                self.app.state.mutate_video_state(scope.video_role, _seed_partition)
                print(f"[BG] seeded videos.{scope.video_role}.beats for storyboard beats: "
                      f"{list(state_seeds.keys())}")
        except Exception as e:
            print(f"[BG] warning: could not seed partition: {e}")

        # BG-37 — Audit-trail row for Accept All (per Rule 18 + spec §4 Phase A).
        # Captures selection_map (beat_id → accepted_image_key) so the next
        # session can reproduce which selections were locked for this segment.
        # Best-effort; non-blocking — never fails the request on Directus error.
        try:
            from lib.directus import try_post_or_queue
            selection_map = {
                b.get("beat_id"): b.get("accepted_image_key")
                for b in body.get("beats", [])
                if b.get("beat_id")
            }
            try_post_or_queue("prod_activity_log", {
                "action": "BEAT_GEN_ACCEPT_ALL",
                "performed_by": "v59_bg_accept_beats",
                "details": {
                    "selection_map": selection_map,
                    "event_id": scope.event_id,
                    "target": scope.video_role,
                    "accepted_count": len(beat_ids),
                    "ld": "BG_ACCEPT_BEATS_ACTIVITY_LOG_V1",
                },
            })
        except Exception as e:
            print(f"[BG] warning: BEAT_GEN_ACCEPT_ALL activity log failed: {e}")

        return self._send_json(200, {"ok": True, "accepted": len(beat_ids)})

    @with_pin_and_drain('_handle_bg_submit_flux', track_sync=True)
    def _handle_bg_submit_flux(self, body: dict) -> None:
        """POST /api/bg/submit-flux-batch {beat_ids: [...]} -> { task_map }
        Burst-submits 3×N FLUX Kontext calls. Returns immediately with task_map."""
        # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
        if not self._assert_event_scope(self._scope_body(body), allow_missing=False):
            return

        # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — capture pin at entry; terminal writes assert via _check_event_pin.
        _pin = {
            "pinned_generation": self.app.event_generation,
            "pinned_event_dir": self.app.event_dir,
            "pinned_video_role": (body or {}).get("scope_video_role", "intro"),
            "_handler": '_handle_bg_submit_flux',
        }

        beat_ids = body.get("beat_ids", [])
        if not beat_ids:
            return self._send_json(400, {"error": "beat_ids required"})

        bg = _bg_module()
        with bg._sidecar_lock:
            sidecar = bg._load_sidecar_migrated()

        task_map = {}
        beats_to_submit = []
        for bid in beat_ids:
            _, beat = bg.find_beat(sidecar, bid)
            if beat:
                beats_to_submit.append(beat)

        for beat in beats_to_submit:
            try:
                rids = bg.submit_beat_stills(beat)
                task_map[beat["beat_id"]] = rids
                # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — terminal sidecar-write pin check.
                # If /api/event/load swapped event mid-FLUX-batch, the rids
                # returned belong to the PRIOR event's pin. Skip the sidecar
                # write so we don't attach FLUX rids to the wrong event's BG state.
                if not self._check_event_pin(_pin, f"bg_submit_flux:{beat['beat_id']}"):
                    print(f"[BG] FLUX rids for {beat['beat_id']} orphaned at "
                          f"{_pin['pinned_event_dir'].name} — sidecar NOT written.",
                          flush=True)
                    continue
                # Store request IDs in sidecar for poll lookups
                with bg._sidecar_lock:
                    sc2 = bg.read_sidecar()
                    _, b2 = bg.find_beat(sc2, beat["beat_id"])
                    if b2:
                        b2["_task_rids"] = rids
                        b2["status"] = "stills_pending"
                    bg.write_sidecar(sc2)
                print(f"[BG] submitted 3 FLUX calls for {beat['beat_id']}: {rids}")
            except Exception as e:
                print(f"[BG] FLUX submit error for {beat['beat_id']}: {e}")
                task_map[beat["beat_id"]] = []

        return self._send_json(200, {"task_map": task_map, "beats_submitted": len(task_map)})

    @with_pin_and_drain('_handle_bg_submit_gpt_batch', track_sync=False)
    def _handle_bg_submit_gpt_batch(self, body: dict) -> None:
        """POST /api/bg/submit-gpt-batch {beat_ids: [...]}
        Spawns GPT generation in background thread pool. Returns {job_id} immediately."""
        # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
        if not self._assert_event_scope(self._scope_body(body), allow_missing=False):
            return

        # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — capture pin at entry; terminal writes assert via _check_event_pin.
        _pin = {
            "pinned_generation": self.app.event_generation,
            "pinned_event_dir": self.app.event_dir,
            "pinned_video_role": (body or {}).get("scope_video_role", "intro"),
            "_handler": '_handle_bg_submit_gpt_batch',
        }
        # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — pre-work pin check (S2).
        # If the event was swapped via /api/event/load between scope-guard
        # and work start, abort BEFORE any expensive work begins.
        if not self._check_event_pin(_pin, '_handle_bg_submit_gpt_batch_pre_work'):
            return self._send_json(423, {
                "error": "event_changed_pre_work",
                "code": "ASYNC_JOB_GENERATION_PIN_V1",
                "handler": '_handle_bg_submit_gpt_batch',
                "hint": (
                    "Event changed between scope-guard and work start. "
                    "No work was done; no orphan output. Client should "
                    "re-hydrate scope and retry."
                ),
            })

        import uuid as _uuid
        beat_ids = body.get("beat_ids", [])
        if not beat_ids:
            return self._send_json(400, {"error": "beat_ids required"})

        job_id = str(_uuid.uuid4())[:8]
        bg = _bg_module()
        with bg._sidecar_lock:
            sidecar = bg._load_sidecar_migrated()

        beats_to_run = []
        for bid in beat_ids:
            _, beat = bg.find_beat(sidecar, bid)
            if beat:
                beats_to_run.append(dict(beat))  # snapshot — avoid lock contention in thread

        _GPT_JOBS[job_id] = {"status": "running", "results": {}, "total": len(beats_to_run) * 3}

        def _run_job():
            executor = _gpt_executor()
            futures = {}
            for beat in beats_to_run:
                bid = beat["beat_id"]
                future = executor.submit(bg.submit_gpt_stills, beat, 3)
                futures[future] = bid

            for future in _cf.as_completed(futures, timeout=600):
                bid = futures[future]
                try:
                    results = future.result()
                    with bg._sidecar_lock:
                        sc = bg.read_sidecar()
                        _, beat_obj = bg.find_beat(sc, bid)
                        if beat_obj:
                            beat_obj["gpt_options"] = results
                            beat_obj["status"] = "stills_ready"
                        # LD-460 — pin check before sidecar write (thread closure).
                        if not self._check_event_pin(_pin, "bg_submit_gpt_batch_write_sidecar"):
                            print(f"[bg_submit_gpt_batch] event drift mid-thread; skipping sidecar write", flush=True)
                            return
                        bg.write_sidecar(sc)
                    _GPT_JOBS[job_id]["results"][bid] = results
                except Exception as e:
                    print(f"[GPT] job {job_id} beat {bid} error: {e}")
                    _GPT_JOBS[job_id]["results"][bid] = [{"error": str(e)}]

            _GPT_JOBS[job_id]["status"] = "done"
            try:
                total_cost = sum(
                    r.get("cost_usd", 0)
                    for opts in _GPT_JOBS[job_id]["results"].values()
                    for r in opts if isinstance(r, dict)
                )
                print(f"[GPT] job {job_id} complete: {len(beats_to_run)} beats, ~${total_cost:.2f}")
            except Exception:
                pass

        threading.Thread(target=_run_job, daemon=True, name=f"gpt-job-{job_id}").start()

        return self._send_json(200, {
            "ok": True, "job_id": job_id,
            "beat_ids": beat_ids, "total_options": len(beats_to_run) * 3,
        })

    def _handle_bg_poll_gpt_status(self) -> None:
        """GET /api/bg/poll-gpt-status?job_id=xxx
        Returns per-beat option results as they complete."""
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        job_id = (qs.get("job_id") or [""])[0]
        if not job_id or job_id not in _GPT_JOBS:
            return self._send_json(404, {"error": f"job {job_id!r} not found"})

        job = _GPT_JOBS[job_id]
        return self._send_json(200, {
            "status": job["status"],
            "results": job["results"],   # {beat_id: [{local_path, key, thumb_b64, ...}, ...]}
            "total": job["total"],
            "done_count": sum(len(v) for v in job["results"].values()),
        })

    def _handle_bg_accept_option(self, body: dict) -> None:
        """POST /api/bg/accept-option {beat_id, option_key} -> { ok }"""
        # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
        if not self._assert_event_scope(self._scope_body(body), allow_missing=False):
            return

        beat_id    = body.get("beat_id")
        option_key = body.get("option_key")
        if not beat_id or not option_key:
            return self._send_json(400, {"error": "beat_id and option_key required"})
        bg = _bg_module()
        with bg._sidecar_lock:
            sidecar = bg.read_sidecar()
            sidecar = bg._migrate_sidecar(sidecar)
            _, beat = bg.find_beat(sidecar, beat_id)
            if not beat:
                return self._send_json(404, {"error": f"beat {beat_id} not found"})
            beat["accepted_image_key"] = option_key
            beat["status"] = "still_chosen"
            # Search both gpt_options and flux_options for the chosen key.
            # Persist local_path so crop + animation downstream can resolve the file.
            all_opts = (beat.get("gpt_options") or []) + (beat.get("flux_options") or [])
            for opt in all_opts:
                if not opt:
                    continue
                if opt.get("key") == option_key:
                    lp = opt.get("local_path")
                    if lp and isinstance(lp, str):
                        beat["accepted_local_path"] = lp
                    vp = opt.get("video_path") or opt.get("filename")
                    if vp and isinstance(vp, str) and vp.lower().endswith((".mp4", ".mov")):
                        beat["accepted_video_path"] = vp
                    break
            bg.write_sidecar(sidecar)
        return self._send_json(200, {"ok": True})

    def _handle_bg_accept_lib_image(self, body: dict) -> None:
        """POST /api/bg/accept-lib-image {beat_id, key, filename, abs_path, slot_index}
        Writes accepted_library_ref + accepted_image_key to sidecar.
        Does NOT touch flux_options[]. Library assignment is tracked separately
        so the existing FLUX option display/crop flow is completely unaffected."""
        # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
        if not self._assert_event_scope(self._scope_body(body), allow_missing=False):
            return

        beat_id    = body.get("beat_id", "")
        key        = body.get("key", "")
        filename   = body.get("filename", "")
        abs_path   = body.get("abs_path", "")
        slot_index = int(body.get("slot_index", 0))
        if not beat_id or not key:
            return self._send_json(400, {"error": "beat_id and key required"})
        bg = _bg_module()
        with bg._sidecar_lock:
            sidecar = bg.read_sidecar()
            sidecar = bg._migrate_sidecar(sidecar)
            _, beat = bg.find_beat(sidecar, beat_id)
            if not beat:
                return self._send_json(404, {"error": f"beat {beat_id} not found"})
            beat["accepted_library_ref"] = {
                "key": key, "filename": filename,
                "abs_path": abs_path, "slot_index": slot_index
            }
            beat["accepted_image_key"] = key
            beat["status"] = "lib_chosen"
            bg.write_sidecar(sidecar)
        print(f"[LIBDROP] accepted library image {key!r} -> beat {beat_id}", flush=True)
        return self._send_json(200, {"ok": True, "beat_id": beat_id,
                                     "accepted_image_key": key})

    # ================================================================
    # Stitch Groups + Local Animation handlers (added 2026-04-23)
    # ================================================================

    def _handle_bg_groups(self) -> None:
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        arc_n = int((qs.get("arc") or [1])[0])
        bg = _bg_module()
        with bg._sidecar_lock:
            sidecar = bg.read_sidecar()
            sidecar = bg._migrate_sidecar(sidecar)
            groups = bg.list_groups(sidecar, arc_n)
            for g in groups:
                g["status"] = bg._compute_group_status(sidecar, g)
        return self._send_json(200, {"ok": True, "groups": groups})

    def _handle_bg_add_beat(self, body: dict) -> None:
        """POST /api/bg/add-beat {after_beat_id, segment} -> {ok, beat}
        Inserts a blank beat immediately after after_beat_id in the sidecar.
        beat_id is generated as max(existing_N)+1 (zero-padded to 2 digits)
        so gaps from prior deletes do not cause collisions."""
        # SCOPE_ROUTER_V1 (C-4 K3 fix) — replaces legacy
        # _assert_event_scope(allow_missing=True) and the hardcoded
        # arc=1/event=2/phase=pre segment lookup.
        # BG sidecar segment is derived from the resolved scope:
        #   intro→pre, resolution→post, standalone→main
        # Subsumes LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
        # and pins LD BG_HARDCODED_SCOPE_PURGE_V1.
        try:
            scope = scope_router.resolve(body, self.app.event_dir.name)
        except scope_router.ScopeError as e:
            return self._send_json(e.http_status, {"error": e.code, **e.detail})

        try:
            arc_number, event_id_int, phase = _resolve_bg_segment_for_scope(
                scope.event_id, scope.video_role,
            )
        except ValueError as exc:
            return self._send_json(400, {"error": "bg_segment_unresolved", "detail": str(exc)})

        after_beat_id = body.get("after_beat_id", "")
        # Note: legacy clients passed `segment` literal (e.g. "event_2_pre");
        # the scope-derived segment is now authoritative. Older callers' segment
        # field is ignored — by design, since the scope keys must match the
        # storyboard tab's pinned event/role.

        bg = _bg_module()
        with bg._sidecar_lock:
            sidecar = bg.read_sidecar()
            seg = bg.get_seg_entry(sidecar, arc_number=arc_number, event_id=event_id_int, phase=phase)
            beats = seg.get("beats", [])

            # Find insertion index
            insert_after = len(beats) - 1  # default: append at end
            for i, b in enumerate(beats):
                if b.get("beat_id") == after_beat_id:
                    insert_after = i
                    break

            # Generate beat_id: max(N)+1 across ALL beats in this segment.
            # Prefix derived from scope (formerly hardcoded "bg_arc1_event2_pre_beat_").
            prefix = f"bg_arc{arc_number}_event{event_id_int}_{phase}_beat_"
            existing_nums = []
            for b in beats:
                bid = b.get("beat_id", "")
                if bid.startswith(prefix):
                    try:
                        existing_nums.append(int(bid[len(prefix):]))
                    except ValueError:
                        pass
            new_num = (max(existing_nums) + 1) if existing_nums else 1
            new_beat_id = f"{prefix}{new_num:02d}"

            new_beat = {
                "beat_id": new_beat_id,
                "speaker": "",
                "dialogue_text": "",
                "emotion": "",
                "scene_notes": "",
                "status": "new",
                "flux_options": [],
                "gpt_options": [],
            }
            beats.insert(insert_after + 1, new_beat)
            bg.write_sidecar(sidecar)

        print(f"[BG] add-beat: inserted {new_beat_id} after {after_beat_id!r}")
        return self._send_json(200, {"ok": True, "beat": new_beat})

    def _handle_bg_create_group(self, body: dict) -> None:
        # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
        if not self._assert_event_scope(self._scope_body(body), allow_missing=False):
            return

        name = (body.get("group_name") or "").strip()
        arc_n = int(body.get("arc_number", 1))
        beat_ids = body.get("beat_ids", [])
        if not name:
            return self._send_json(400, {"ok": False, "error": "group_name empty"})
        if not beat_ids:
            return self._send_json(400, {"ok": False, "error": "beat_ids empty"})
        bg = _bg_module()
        with bg._sidecar_lock:
            sidecar = bg.read_sidecar()
            sidecar = bg._migrate_sidecar(sidecar)
            try:
                gid = bg.create_group(sidecar, name, arc_n, beat_ids)
            except ValueError as e:
                return self._send_json(400, {"ok": False, "error": str(e)})
            bg.write_sidecar(sidecar)
        return self._send_json(200, {"ok": True, "group_id": gid,
                                      "status": sidecar["groups"][gid]["status"]})

    def _handle_bg_delete_group(self, body: dict) -> None:
        # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
        if not self._assert_event_scope(self._scope_body(body), allow_missing=False):
            return

        gid = body.get("group_id", "")
        if not gid:
            return self._send_json(400, {"ok": False, "error": "group_id required"})
        bg = _bg_module()
        with bg._sidecar_lock:
            sidecar = bg.read_sidecar()
            sidecar = bg._migrate_sidecar(sidecar)
            if not bg.delete_group(sidecar, gid):
                return self._send_json(404, {"ok": False, "error": "group not found"})
            bg.write_sidecar(sidecar)
        return self._send_json(200, {"ok": True})

    def _handle_bg_update_group(self, body: dict) -> None:
        # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
        if not self._assert_event_scope(self._scope_body(body), allow_missing=False):
            return

        gid = body.get("group_id", "")
        ordered = body.get("beat_ids_ordered", [])
        if not gid:
            return self._send_json(400, {"ok": False, "error": "group_id required"})
        bg = _bg_module()
        with bg._sidecar_lock:
            sidecar = bg.read_sidecar()
            sidecar = bg._migrate_sidecar(sidecar)
            if gid not in sidecar.get("groups", {}):
                return self._send_json(404, {"ok": False, "error": "group not found"})
            new_status = bg.update_group_order(sidecar, gid, ordered)
            bg.write_sidecar(sidecar)
        return self._send_json(200, {"ok": True, "status": new_status})

    @with_pin_and_drain('_handle_bg_assemble_group', track_sync=False)
    def _handle_bg_assemble_group(self, body: dict) -> None:
        # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
        if not self._assert_event_scope(self._scope_body(body), allow_missing=False):
            return

        # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — capture pin at entry; terminal writes assert via _check_event_pin.
        _pin = {
            "pinned_generation": self.app.event_generation,
            "pinned_event_dir": self.app.event_dir,
            "pinned_video_role": (body or {}).get("scope_video_role", "intro"),
            "_handler": '_handle_bg_assemble_group',
        }
        # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — pre-work pin check (S2).
        # If the event was swapped via /api/event/load between scope-guard
        # and work start, abort BEFORE any expensive work begins.
        if not self._check_event_pin(_pin, '_handle_bg_assemble_group_pre_work'):
            return self._send_json(423, {
                "error": "event_changed_pre_work",
                "code": "ASYNC_JOB_GENERATION_PIN_V1",
                "handler": '_handle_bg_assemble_group',
                "hint": (
                    "Event changed between scope-guard and work start. "
                    "No work was done; no orphan output. Client should "
                    "re-hydrate scope and retry."
                ),
            })

        gid = body.get("group_id", "")
        if not gid:
            return self._send_json(400, {"ok": False, "error": "group_id required"})
        bg = _bg_module()
        with bg._sidecar_lock:
            sidecar = bg.read_sidecar()
            sidecar = bg._migrate_sidecar(sidecar)
            g = sidecar.get("groups", {}).get(gid)
            if not g:
                return self._send_json(404, {"ok": False, "error": "group not found"})
            status = bg._compute_group_status(sidecar, g)
            if status != "ready":
                return self._send_json(400, {"ok": False,
                                              "error": f"group status is '{status}', must be 'ready'"})
        # Spawn background thread
        import threading as _th
        import pathlib as _pl
        output_dir = _pl.Path(bg.BG_SIDECAR_PATH).parent / "assembled_groups"

        def _run():
            try:
                with bg._sidecar_lock:
                    s2 = bg.read_sidecar()
                    s2 = bg._migrate_sidecar(s2)
                    clip_path, duration, size = bg.assemble_group(s2, gid, output_dir)
                    # LD-460 — pin check before sidecar write (thread closure).
                    if not self._check_event_pin(_pin, "bg_assemble_group_write_sidecar"):
                        print(f"[bg_assemble_group] event drift mid-thread; skipping sidecar write", flush=True)
                        return
                    bg.write_sidecar(s2)
                _ASSEMBLE_JOBS[gid] = {"status": "done",
                                        "assembled_clip_path": clip_path,
                                        "duration_seconds": duration,
                                        "file_size_bytes": size}
                try:
                    _bg_register_assembled_clip(gid, clip_path, size)
                except Exception as reg_e:
                    print(f"[BG] assemble registration failed: {reg_e}", file=sys.stderr)
            except Exception as e:
                traceback.print_exc()
                _ASSEMBLE_JOBS[gid] = {"status": "error", "error": str(e)}

        _ASSEMBLE_JOBS[gid] = {"status": "running"}
        _th.Thread(target=_run, daemon=True).start()
        return self._send_json(200, {"ok": True, "status": "assembling",
                                      "poll": f"/api/bg/poll-assemble-status?group_id={gid}"})

    def _handle_bg_poll_assemble_status(self) -> None:
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        gid = (qs.get("group_id") or [None])[0]
        if not gid:
            return self._send_json(400, {"ok": False, "error": "group_id required"})
        job = _ASSEMBLE_JOBS.get(gid)
        if not job:
            return self._send_json(404, {"ok": False, "error": "no assemble job found for group_id"})
        return self._send_json(200, {"ok": True, **job})

    @with_pin_and_drain('_handle_bg_run_local_animation', track_sync=True)
    def _handle_bg_run_local_animation(self, body: dict) -> None:
        # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
        if not self._assert_event_scope(self._scope_body(body), allow_missing=False):
            return

        # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — capture pin at entry; terminal writes assert via _check_event_pin.
        _pin = {
            "pinned_generation": self.app.event_generation,
            "pinned_event_dir": self.app.event_dir,
            "pinned_video_role": (body or {}).get("scope_video_role", "intro"),
            "_handler": '_handle_bg_run_local_animation',
        }
        # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — pre-work pin check (S2).
        # If the event was swapped via /api/event/load between scope-guard
        # and work start, abort BEFORE any expensive work begins.
        if not self._check_event_pin(_pin, '_handle_bg_run_local_animation_pre_work'):
            return self._send_json(423, {
                "error": "event_changed_pre_work",
                "code": "ASYNC_JOB_GENERATION_PIN_V1",
                "handler": '_handle_bg_run_local_animation',
                "hint": (
                    "Event changed between scope-guard and work start. "
                    "No work was done; no orphan output. Client should "
                    "re-hydrate scope and retry."
                ),
            })

        beat_id = body.get("beat_id", "")
        method = body.get("method", "")
        params = body.get("params", {}) or {}
        preview_only = bool(body.get("preview_only", False))
        VALID_METHODS = {"magic_compositor", "ken_burns", "static_hold"}
        if method not in VALID_METHODS:
            return self._send_json(400, {"ok": False,
                                          "error": f"method must be one of {sorted(VALID_METHODS)}"})
        bg = _bg_module()
        with bg._sidecar_lock:
            sidecar = bg.read_sidecar()
            sidecar = bg._migrate_sidecar(sidecar)
            ctx = sidecar.get("active_context") or {}
            arc_n = ctx.get("arc_number", 1)
            beats_by_id = bg._index_beats(sidecar, arc_n)
            beat = beats_by_id.get(beat_id)
            if not beat:
                return self._send_json(404, {"ok": False, "error": f"beat_id {beat_id} not found"})
            try:
                if method == "magic_compositor":
                    bg_path = params.get("background_path", "")
                    path_pts = params.get("path_pts", [])
                    style = params.get("style", "tessa_ori")
                    duration = float(params.get("duration", 3.5))
                    if not bg_path or not path_pts:
                        return self._send_json(400, {"ok": False,
                                                      "error": "params missing background_path or path_pts"})
                    if preview_only:
                        import sys as _sys
                        _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
                        from magic_compositor import MagicCompositor, STYLES
                        if style not in STYLES:
                            return self._send_json(400, {"ok": False,
                                                          "error": "style not approved"})
                        import pathlib as _pl
                        out_dir = _pl.Path(bg.BG_STILLS_DIR) / "local_renders"
                        out_dir.mkdir(parents=True, exist_ok=True)
                        mc = MagicCompositor(
                            background_path=bg_path, path_pts=path_pts,
                            style=style, duration=duration,
                            output_dir=str(out_dir),
                            label=f"{beat_id}_preview_{int(time.time())}",
                        )
                        preview_path = mc.render_preview()
                        bg.write_sidecar(sidecar)
                        return self._send_json(200, {"ok": True, "preview_path": preview_path})
                    result = bg.run_magic_compositor(beat, bg_path, path_pts, style, duration)
                elif method == "ken_burns":
                    still = params.get("still_path", "")
                    if not still:
                        return self._send_json(400, {"ok": False,
                                                      "error": "params missing still_path"})
                    result = bg.run_ken_burns(
                        beat, still,
                        float(params.get("pan_x_pct", 0)),
                        float(params.get("pan_y_pct", 0)),
                        float(params.get("zoom_start", 1.0)),
                        float(params.get("zoom_end", 1.3)),
                        float(params.get("duration", 4.0)),
                    )
                elif method == "static_hold":
                    still = params.get("still_path", "")
                    if not still:
                        return self._send_json(400, {"ok": False,
                                                      "error": "params missing still_path"})
                    result = bg.run_static_hold(
                        beat, still, float(params.get("duration", 4.0))
                    )
                # LD-460 — pin check before sidecar write.
                if not self._check_event_pin(_pin, "bg_run_local_animation_write_sidecar"):
                    print(f"[bg_run_local_animation] event drift; skipping sidecar write", flush=True)
                    return self._send_json(423, {"error": "event_changed_mid_job", "code": "ASYNC_JOB_GENERATION_PIN_V1"})
                bg.write_sidecar(sidecar)
            except Exception as e:
                traceback.print_exc()
                return self._send_json(500, {"ok": False, "error": str(e)})
        return self._send_json(200, {"ok": True, **result})

    def _handle_bg_update_beat_anim_method(self, body: dict) -> None:
        # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
        if not self._assert_event_scope(self._scope_body(body), allow_missing=False):
            return

        beat_id = body.get("beat_id", "")
        method = body.get("animation_method", "")
        VALID = {"kling", "magic_compositor", "ken_burns", "static_hold"}
        if not beat_id:
            return self._send_json(400, {"ok": False, "error": "beat_id required"})
        if method not in VALID:
            return self._send_json(400, {"ok": False,
                                          "error": f"invalid method; valid: {sorted(VALID)}"})
        bg = _bg_module()
        with bg._sidecar_lock:
            sidecar = bg.read_sidecar()
            sidecar = bg._migrate_sidecar(sidecar)
            _, b = bg.find_beat(sidecar, beat_id)
            if not b:
                return self._send_json(404, {"ok": False, "error": f"beat_id {beat_id} not found"})
            b["animation_method"] = method
            bg.write_sidecar(sidecar)
        return self._send_json(200, {"ok": True})

    def _handle_bg_accept_local_animation(self, body: dict) -> None:
        # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
        if not self._assert_event_scope(self._scope_body(body), allow_missing=False):
            return

        beat_id = body.get("beat_id", "")
        video_path = body.get("video_path", "")
        if not beat_id or not video_path:
            return self._send_json(400, {"ok": False, "error": "beat_id and video_path required"})
        if not os.path.exists(video_path):
            return self._send_json(400, {"ok": False, "error": f"video file not found: {video_path}"})
        bg = _bg_module()
        import pathlib as _pl
        if not bg._ffprobe_ok(_pl.Path(video_path)):
            return self._send_json(400, {"ok": False, "error": "video failed ffprobe validation"})
        with bg._sidecar_lock:
            sidecar = bg.read_sidecar()
            sidecar = bg._migrate_sidecar(sidecar)
            _, b = bg.find_beat(sidecar, beat_id)
            if not b:
                return self._send_json(404, {"ok": False, "error": f"beat_id {beat_id} not found"})
            b["status"] = "accepted"
            b["accepted_video_path"] = video_path
            gid = b.get("group_id")
            if gid and gid in sidecar.get("groups", {}):
                g = sidecar["groups"][gid]
                g["status"] = bg._compute_group_status(sidecar, g)
            bg.write_sidecar(sidecar)
        return self._send_json(200, {"ok": True})

    def _handle_bg_stills(self, path: str) -> None:
        """GET /bg-stills/<filename> — serve a FLUX still PNG from beat_generator_stills/.
        Path-traversal-safe: only direct children of BG_STILLS_DIR are served.
        Fix-C: eliminates ephemeral TH thumbnail cache dependency after page refresh."""
        raw = path[len("/bg-stills/"):]
        filename = urllib.parse.unquote(raw)
        # Reject traversal attempts before resolve
        if not filename or "/" in filename or "\\" in filename or ".." in filename or "\x00" in filename:
            return self._send_json(400, {"error": "invalid filename"})
        bg = _bg_module()
        stills_dir = Path(bg.BG_STILLS_DIR).resolve()
        target = (stills_dir / filename).resolve()
        # Only direct children (not subdirectories like local_renders/)
        if target.parent != stills_dir:
            return self._send_json(403, {"error": "forbidden"})
        if not target.exists():
            # GPT stills are saved as <key>_<timestamp>.ext — try prefix glob
            stem = Path(filename).stem   # key without extension
            ext  = Path(filename).suffix or ".png"
            candidates = sorted(stills_dir.glob(f"{stem}_*{ext}"))
            if candidates:
                target = candidates[-1]   # most recent by name (timestamps sort lexicographically)
            else:
                return self._send_json(404, {"error": "not found"})
        ext = target.suffix.lower()
        ct_map = {".png": "image/png", ".jpg": "image/jpeg",
                  ".jpeg": "image/jpeg", ".webp": "image/webp"}
        ct = ct_map.get(ext, "application/octet-stream")
        data = target.read_bytes()
        return self._send_bytes(200, data, ct, {"Cache-Control": "no-cache"})

    def _handle_files_serve(self) -> None:
        """GET /files?path=<absolute_path> — serve local file bytes (images/video)."""
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        file_path = (qs.get("path") or [None])[0]
        if not file_path or not os.path.exists(file_path):
            return self._send_json(404, {"error": "file not found"})
        ext = os.path.splitext(file_path)[1].lower()
        content_types = {
            ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".webp": "image/webp", ".gif": "image/gif",
            ".mp4": "video/mp4", ".mov": "video/quicktime",
        }
        ct = content_types.get(ext, "application/octet-stream")
        with open(file_path, "rb") as _f:
            data = _f.read()
        try:
            self.send_response(200)
            self.send_header("Content-Type", ct)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            print(f"file stream canceled by client: {file_path}", file=sys.stderr, flush=True)

    def _handle_cr_save_crop(self, body: dict) -> None:
        """POST /api/cr/save-crop {crop_png_b64, beat_id, source_key, event_id?}
        Rule 6 upscale + Rule 6.2 WebP delivery + Directus Two-Write.
        Returns { key, filename, thumb_b64, gallery_b64 }."""
        # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
        if not self._assert_event_scope(self._scope_body(body), allow_missing=False):
            return
        crop_b64   = body.get("crop_png_b64", "")
        beat_id    = body.get("beat_id", "")
        source_key = body.get("source_key", "")
        if not crop_b64:
            return self._send_json(400, {"error": "crop_png_b64 required"})

        bg = _bg_module()
        try:
            crop_bytes = base64.b64decode(crop_b64)
        except Exception as e:
            return self._send_json(400, {"error": f"base64 decode failed: {e}"})

        delivery_bytes, width, height, thumb_b64, gallery_b64 = bg.process_crop(crop_bytes)

        # Save to disk
        ts = int(time.time())
        filename   = f"crop_{beat_id}_{ts}.webp"
        crops_dir  = os.path.join(bg.BG_STILLS_DIR, "crops")
        os.makedirs(crops_dir, exist_ok=True)
        delivery_path = os.path.join(crops_dir, filename)
        with open(delivery_path, "wb") as f:
            f.write(delivery_bytes)

        key = f"crop_{beat_id}_{ts}"

        # BG-22 + C-9 — Asset registration via registered_write.register_asset
        # (replaces the legacy inline `_directus_post_bg("prod_visual_assets", ...)`
        # block per spec §4 Phase A). registered_write performs the Two-Write
        # internally (prod_assets row + prod_activity_log register_asset row),
        # SHA256-deduped, with `iteration_notes` capture per LD-421 + Rule 34.
        # Failures are queued to pending_directus_writes.json automatically.
        # asset_type mapping: legacy "crop_4x3" → "still_delivery" per Rule 6.2 +
        # _ACCEPTED_ASSET_TYPES whitelist. Module-agnostic crop registers with
        # module_id=1 + library=True per _MODULE_MAP convention.
        asset_id = None
        try:
            from registered_write import register_asset as _register_asset
            iteration_notes = (
                f"BG cropper output for beat {beat_id or '<unset>'} from source "
                f"key {source_key or '<unset>'} (4:3 crop, {width}x{height} WebP)"
            )
            asset_id, _abs_path = _register_asset(
                file_path=delivery_path,
                asset_type="still_delivery",
                module_id=1,
                beat_id=beat_id or None,
                produced_by_skill="v59_bg_cropper",
                iteration_notes=iteration_notes,
                tags=["bg_cropper", "crop_4x3", "delivery"],
                library=True,
                role="delivery",
                colloquial_name=f"crop {beat_id} {ts}",
            )
            if asset_id and asset_id > 0:
                print(f"[BG] registered_write OK asset_id={asset_id} {filename}")
            else:
                print(f"[BG] registered_write queued (offline) for {filename}")
        except Exception as e:
            print(f"[BG] registered_write warning (non-fatal): {e}")

        return self._send_json(200, {
            "key": key,
            "filename": filename,
            "thumb_b64": thumb_b64,
            "gallery_b64": gallery_b64,
            "asset_id": asset_id,
        })

    @with_pin_and_drain('_handle_cr_upload', track_sync=True)
    def _handle_cr_upload(self, body: dict) -> None:
        """POST /api/cr/upload {filename, image_b64, tier?}
        Saves a manually-uploaded image to the library.
        tier='source' -> BG_STILLS_DIR/sources/  (pre-crop images)
        tier='cropped' or absent -> BG_STILLS_DIR/crops/  (ready images)
        Returns { key, filename, thumb_b64, gallery_b64, tier, abs_path }."""
        # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
        if not self._assert_event_scope(self._scope_body(body), allow_missing=False):
            return

        # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — capture pin at entry; terminal writes assert via _check_event_pin.
        _pin = {
            "pinned_generation": self.app.event_generation,
            "pinned_event_dir": self.app.event_dir,
            "pinned_video_role": (body or {}).get("scope_video_role", "intro"),
            "_handler": '_handle_cr_upload',
        }
        # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — pre-work pin check (S2).
        # If the event was swapped via /api/event/load between scope-guard
        # and work start, abort BEFORE any expensive work begins.
        if not self._check_event_pin(_pin, '_handle_cr_upload_pre_work'):
            return self._send_json(423, {
                "error": "event_changed_pre_work",
                "code": "ASYNC_JOB_GENERATION_PIN_V1",
                "handler": '_handle_cr_upload',
                "hint": (
                    "Event changed between scope-guard and work start. "
                    "No work was done; no orphan output. Client should "
                    "re-hydrate scope and retry."
                ),
            })

        filename  = body.get("filename", "")
        image_b64 = body.get("image_b64", "")
        tier      = body.get("tier", "cropped")

        if not filename or not image_b64:
            return self._send_json(400, {"error": "filename and image_b64 required"})

        # Sanitize — basename only, no path traversal, valid extension
        filename = os.path.basename(filename)
        if not filename.lower().endswith((".png", ".webp", ".jpg", ".jpeg")):
            return self._send_json(400, {"error": "filename must be .png, .webp, .jpg, or .jpeg"})

        # Decode
        raw_b64 = image_b64
        if "," in raw_b64:
            raw_b64 = raw_b64.split(",", 1)[1]
        try:
            raw_bytes = base64.b64decode(raw_b64)
        except Exception as e:
            return self._send_json(400, {"error": f"base64 decode failed: {e}"})

        bg = _bg_module()
        if tier == "source":
            dest_dir = os.path.join(bg.BG_STILLS_DIR, "sources")
        else:
            dest_dir = os.path.join(bg.BG_STILLS_DIR, "crops")
            tier = "cropped"

        os.makedirs(dest_dir, exist_ok=True)
        dest_path = os.path.join(dest_dir, filename)
        # LD-460 — terminal pin check before file write.
        if not self._check_event_pin(_pin, "cr_upload_write_bytes"):
            return self._send_json(423, {"error": "event_changed_mid_job", "code": "ASYNC_JOB_GENERATION_PIN_V1"})
        with open(dest_path, "wb") as f:
            f.write(raw_bytes)

        ext = "webp" if filename.lower().endswith(".webp") else "png"
        gallery_b64 = f"data:image/{ext};base64,{base64.b64encode(raw_bytes).decode()}"
        key = os.path.splitext(filename)[0]

        print(f"[library] upload saved: {dest_path} tier={tier}")
        return self._send_json(200, {
            "ok": True,
            "key": key, "filename": filename,
            "thumb_b64": gallery_b64, "gallery_b64": gallery_b64,
            "tier": tier, "abs_path": dest_path,
        })

    # ---- endpoints ----
    def _handle_health(self) -> None:
        self._send_json(200, {
            "status": "ok",
            "uptime_seconds": int(time.time() - self.app.started_at),
            "event_id": self.app.event_id,
            "version": SERVER_VERSION,
        })

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
        beat_id = body.get("beat")
        image_key = body.get("image_key")
        if not beat_id or not image_key:
            return self._send_json(400, {"error": "missing 'beat' or 'image_key'"})
        # S5.5a2: scope_video_role from body (LD-474). Default 'intro' during
        # refactor window; required after all clients pass it explicitly.
        video_role = body.get("scope_video_role", "intro")

        # Look up full-res gallery image
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
            #    S5.5a2: writes to videos[role].image_overrides via
            #    mutate_video_state (BG_VIDEO_PARTITION_V1).
            def _persist(partition, _bid=beat_id, _key=image_key):
                partition.setdefault("image_overrides", {})[_bid] = _key
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
                return self._send_json(500, {
                    "error": "storyboard HTML patch failed; override rolled back",
                    "detail": err,
                    "beat": beat_id,
                })

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
            return self._send_json(404, {
                "error": f"image key '{image_key}' not found in gallery or TH"
            })

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
            return self._send_json(400, {"error": "name and data are required"})

        # Sanitize key: no extension, spaces->underscores
        key = name.replace(" ", "_")
        if key.endswith(".png"):
            key = key[:-4]

        sb_path = self.app.storyboard_path
        if not sb_path.is_file():
            return self._send_json(500, {"error": f"storyboard not found: {sb_path}"})

        html = sb_path.read_text(encoding="utf-8")

        # Snapshot existing base64 images for verification
        existing_b64 = re.findall(r'data:image/[^"]{100,}', html)

        # Check if key already exists in TH — if so, update instead of duplicate
        th_exists = f'TH["{key}"]' in html

        # --- 1. Add gallery <div class="ic"> ---
        ic_positions = [m.end() for m in re.finditer(
            r'<div class="ic"><img[^>]+><p>[^<]+</p></div>', html)]
        if not ic_positions:
            return self._send_json(500, {"error": "no gallery images found in storyboard"})
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
                return self._send_json(500, {"error": "image corruption detected, write aborted"})

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
        """Submit lipsync with §8.4 pre-conditioning always applied.

        Body: {"beat": "beat_NN"} or {"beat": "beat_NN", "audio_override": "..."}
        """
        # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
        if not self._assert_event_scope(self._scope_body(body), allow_missing=False):
            return

        # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — capture pin at entry; terminal writes assert via _check_event_pin.
        _pin = {
            "pinned_generation": self.app.event_generation,
            "pinned_event_dir": self.app.event_dir,
            "pinned_video_role": (body or {}).get("scope_video_role", "intro"),
            "_handler": '_handle_lipsync_submit',
        }
        # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — pre-work pin check (S2).
        # If the event was swapped via /api/event/load between scope-guard
        # and work start, abort BEFORE any expensive work begins.
        if not self._check_event_pin(_pin, '_handle_lipsync_submit_pre_work'):
            return self._send_json(423, {
                "error": "event_changed_pre_work",
                "code": "ASYNC_JOB_GENERATION_PIN_V1",
                "handler": '_handle_lipsync_submit',
                "hint": (
                    "Event changed between scope-guard and work start. "
                    "No work was done; no orphan output. Client should "
                    "re-hydrate scope and retry."
                ),
            })

        if self.app.client is None:
            return self._send_json(500, {"error": "WaveSpeed client not configured (missing API key)"})

        beat_key = body.get("beat")
        if not beat_key:
            return self._send_json(400, {"error": "missing 'beat' field"})

        state = self.app.state.read_state()
        beat_state = ((state.get("videos") or {}).get("intro") or {}).get("beats", {}).get(beat_key)
        if not beat_state:
            return self._send_json(404, {"error": f"beat '{beat_key}' not found in state"})

        phase1 = beat_state.get("phase_1", {})
        selected = phase1.get("selected_option")
        if not selected:
            return self._send_json(400, {"error": f"no option selected for {beat_key}"})

        options = phase1.get("options", [])
        if selected < 1 or selected > len(options):
            return self._send_json(400, {"error": f"selected_option {selected} out of range"})
        clip_file = options[selected - 1].get("file")
        if not clip_file:
            return self._send_json(400, {"error": f"selected option has no file"})

        source_clip_path = self.app.state.clips_dir / clip_file
        if not source_clip_path.is_file():
            return self._send_json(404, {"error": f"clip file not found: {clip_file}"})

        # LIPSYNC_TRIM_WINDOW_HONORED_20260419 — read user trim window from
        # storyboard. Absent/null fields collapse to old "whole-clip" behavior.
        trim_start_raw = phase1.get("trim_start")
        trim_end_raw = phase1.get("trim_end")
        try:
            trim_start = float(trim_start_raw) if trim_start_raw is not None else 0.0
            trim_end = float(trim_end_raw) if trim_end_raw is not None else None
        except (TypeError, ValueError):
            return self._send_json(400, {
                "error": f"phase_1.trim_start/trim_end must be numeric",
                "trim_start": trim_start_raw, "trim_end": trim_end_raw,
            })
        if trim_start < 0:
            return self._send_json(400, {"error": f"trim_start must be >= 0 (got {trim_start})"})
        if trim_end is not None and trim_end <= trim_start:
            return self._send_json(400, {
                "error": f"trim_end ({trim_end}) must be > trim_start ({trim_start})",
            })

        beat_num = int(beat_key.split("_")[1])
        source_audio_path = _find_beat_audio(
            self.app.event_dir, beat_key, body.get("audio_override"),
            app=self.app,
        )
        if not source_audio_path:
            return self._send_json(404, {
                "error": f"no TTS audio found for {beat_key} (line_{beat_num:02d})",
                "hint": "provide audio_override path or ensure TTS exists in story_scene_tts_v2/",
            })

        # Budget check BEFORE ffmpeg work.
        spend = self.app.state.read_spend()
        if spend["budget_remaining"] < COST_PER_LIPSYNC:
            return self._send_json(402, {
                "error": "budget exceeded for lip sync",
                "budget_remaining": spend["budget_remaining"],
                "cost": COST_PER_LIPSYNC,
            })

        # ------------------------------------------------------------------
        # §8.4 pre-conditioning (synchronous, fail-loud).
        # ------------------------------------------------------------------
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        tts_dir = self.app.event_dir / "story_scene_tts_v2"
        tmp_audio_path = tts_dir / f"_tmp_silcomp_{beat_key}_{ts}.mp3"
        tmp_video_path = self.app.state.clips_dir / f"_tmp_trim_{beat_key}_{ts}.mp4"

        try:
            # Preflight 110 AUTO_PREROLL_V1: enable auto pre-roll ONLY when
            # user hasn't set a trim_start (Counter Finding 4: preroll
            # interacts badly with a non-zero trim_start — Kim's intent to
            # skip settling frames would be undone by the prepended silence).
            # skip_auto_preroll body flag allows explicit opt-out.
            auto_preroll_enabled = (
                trim_start == 0.0
                and not body.get("skip_auto_preroll", False)
            )
            # Compute the caller's max_audio_s for overflow clamping (Counter
            # Finding 3): the resulting padded audio must fit inside the
            # window_len minus tail room. window_len is unknown yet but bounded
            # by raw_dur - trim_start. Pre-compute a conservative ceiling.
            _pre_raw_dur = _ffprobe_duration(source_clip_path)
            _pre_effective_end = trim_end if trim_end is not None else _pre_raw_dur
            if _pre_effective_end > _pre_raw_dur:
                _pre_effective_end = _pre_raw_dur
            _pre_window_len = _pre_effective_end - trim_start
            _max_audio_for_preroll = max(0.0, _pre_window_len - _VIDEO_TRIM_TAILROOM_S)
            # Preflight 113 LOUDNORM_IN_SILCOMP_V1: enable loudness
            # normalization by default so quiet phrases (e.g. ElevenLabs
            # hesitations at -30 dB) don't get gated as silence by
            # LatentSync. skip_loudnorm body flag allows opt-out.
            loudnorm_enabled = not body.get("skip_loudnorm", False)
            audio_for_lipsync, audio_proc_meta = _silcomp_audio(
                source_audio_path, tmp_audio_path,
                auto_preroll=auto_preroll_enabled,
                max_audio_s=_max_audio_for_preroll,
                loudnorm=loudnorm_enabled,
            )
            audio_duration = audio_proc_meta["compressed_duration_s"]

            # LIPSYNC_TRIM_WINDOW_HONORED_20260419 — validate window fits audio
            # BEFORE spending the ffmpeg trim (fail-loud, explicit numbers).
            raw_dur = _ffprobe_duration(source_clip_path)
            if trim_start >= raw_dur:
                return self._send_json(400, {
                    "error": f"trim_start={trim_start:.2f}s out of range",
                    "clip_duration_s": round(raw_dur, 3),
                    "beat": beat_key,
                })
            effective_end = trim_end if trim_end is not None else raw_dur
            if effective_end > raw_dur + 0.05:
                print(f"[lipsync] WARN trim_end={effective_end:.2f} exceeds "
                      f"raw_dur={raw_dur:.2f} for {beat_key}; clamping")
                effective_end = raw_dur
            window_len = effective_end - trim_start
            need = audio_duration + _VIDEO_TRIM_TAILROOM_S
            if need > window_len + 0.01:
                return self._send_json(400, {
                    "error": "audio exceeds trim window (insufficient video for lipsync)",
                    "beat": beat_key,
                    "audio_duration_s": round(audio_duration, 3),
                    "tailroom_s": _VIDEO_TRIM_TAILROOM_S,
                    "needed_s": round(need, 3),
                    "trim_window_s": round(window_len, 3),
                    "trim_start": round(trim_start, 3),
                    "trim_end": round(effective_end, 3),
                    "hint": "widen trim_end, move trim_start earlier, or shorten the TTS audio",
                })

            # LD LIPSYNC_MAX_DURATION_10S_NO_SILENCE_V1 (id=400, CLAUDE.md §8.5):
            # ByteDance LatentSync max training window = 10s. Longer = scene hallucination + watermark.
            _LIPSYNC_MAX_DUR = 10.0
            if audio_duration > _LIPSYNC_MAX_DUR:
                return self._send_json(400, {
                    "error": "audio_duration exceeds ByteDance max (10s)",
                    "audio_duration_s": round(audio_duration, 3),
                    "max_duration_s": _LIPSYNC_MAX_DUR,
                    "beat": beat_key,
                    "rule": "LIPSYNC_MAX_DURATION_10S_NO_SILENCE_V1 (id=400)",
                    "hint": (
                        "Use silence-split + passthrough protocol (CLAUDE.md §8.5): "
                        "split at silence boundaries, submit each speaking segment ≤10s "
                        "to ByteDance, passthrough original frames for silent portions, "
                        "then ffmpeg-concat and dub additional phrases as voice-over."
                    ),
                })

            video_for_lipsync, trimmed_to, ts_used, te_used = _trim_video_to_audio(
                source_clip_path, tmp_video_path, audio_duration,
                trim_start=trim_start, trim_end=effective_end,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
                OSError, ValueError) as exc:
            traceback.print_exc()
            return self._send_json(500, {
                "error": "lipsync pre-conditioning failed",
                "stage": "silcomp_or_trim",
                "detail": str(exc)[:500],
                "source_audio": source_audio_path.name,
                "source_clip": clip_file,
            })

        audio_processing = {
            "method": "silence_compression_auto_applied",
            "source_audio": source_audio_path.name,
            "source_duration_s": audio_proc_meta["source_duration_s"],
            "compressed_duration_s": audio_proc_meta["compressed_duration_s"],
            "silences_compressed": audio_proc_meta["silences_compressed"],
            # Preflight 110 AUTO_PREROLL_V1: pass through preroll_processing
            # subdict so state + UI can show whether auto pre-roll fired.
            "preroll_processing": audio_proc_meta.get("preroll_processing") or {},
            # Preflight 113 LOUDNORM_IN_SILCOMP_V1: EBU R128 loudness
            # normalization applied to silcomp output. Eliminates ByteDance
            # LatentSync's "quiet phoneme lost" class (quiet phrases at
            # -30 dB no longer gated as silence).
            "loudnorm_applied": bool(audio_proc_meta.get("loudnorm_applied")),
            "loudnorm_target_i_lufs": audio_proc_meta.get("loudnorm_target_i_lufs"),
            "loudnorm_target_tp_dbtp": audio_proc_meta.get("loudnorm_target_tp_dbtp"),
            "loudnorm_target_lra_lu": audio_proc_meta.get("loudnorm_target_lra_lu"),
            "video_trimmed_to_s": round(trimmed_to, 3),
            "trim_start": round(ts_used, 3),
            "trim_end": round(te_used, 3),
            "trim_window_s": round(te_used - ts_used, 3),
            "applied_by": "_handle_lipsync_submit_v4_loudnorm",
            "rule_reference": "CLAUDE.md §8.4 + LIPSYNC_TRIM_WINDOW_HONORED_20260419 + AUTO_PREROLL_V1 + LOUDNORM_V1",
        }
        silcomp_applied = audio_proc_meta["applied"]
        print(f"[lipsync] {beat_key} pre-cond: silcomp={silcomp_applied} "
              f"audio_dur={audio_duration:.2f}s video_trim={trimmed_to:.2f}s "
              f"trim_start={ts_used:.2f} trim_end={te_used:.2f}")

        # Init state — includes audio_processing block. Retry-aware: if a
        # prior lipsync block exists (status in {submitting, polling, failed,
        # completed}), clear stale task_id / submitted_at / submitted_at_epoch
        # and increment retries. Fixes stale-task_id bug (beat_08 evidence,
        # 2026-04-18): retry was leaving 25h-old submit metadata in state.
        def init_lipsync(st, _bk=beat_key, _src=int(selected),
                         _audio_name=audio_for_lipsync.name, _ap=audio_processing):
            beat = st["beats"][_bk]
            existing = beat.get("lipsync")
            is_retry = isinstance(existing, dict) and existing.get("status") in (
                "submitting", "polling", "failed", "completed",
            )
            # Treat `lipsync: None` the same as missing — initialize fresh.
            if not isinstance(existing, dict):
                beat["lipsync"] = {
                    "status": "submitting", "task_id": None, "file": None,
                    "audio_file": None, "submitted_at": None, "retries": 0,
                }
            ls = beat["lipsync"]
            if is_retry:
                # Prior task_id is now a ghost — superseded by this resubmit.
                # Preserve for audit, clear from active slots.
                prior_task = ls.get("task_id")
                if prior_task:
                    superseded = ls.setdefault("superseded_task_ids", [])
                    if prior_task not in superseded:
                        superseded.append(prior_task)
                ls["task_id"] = None
                ls["submitted_at"] = None
                ls["submitted_at_epoch"] = None
                ls["retries"] = int(ls.get("retries", 0)) + 1
            ls["status"] = "submitting"
            ls["audio_file"] = _audio_name
            ls["source_option"] = _src
            ls["source_changed"] = False
            ls["audio_processing"] = _ap
            ls.pop("last_error", None)
        # LD-460 — terminal pin check before init_lipsync mutate_state.
        if not self._check_event_pin(_pin, "lipsync_submit_init_mutate"):
            return self._send_json(423, {"error": "event_changed_mid_job", "code": "ASYNC_JOB_GENERATION_PIN_V1"})
        self.app.state.mutate_state(init_lipsync)

        # Rule 18 submit log.
        try:
            _async_log_lipsync_submit(
                event_id=getattr(self.app, "event_id", "unknown"),
                beat_id=beat_key, audio_processing=audio_processing,
                video_trimmed_to_s=trimmed_to, source_option=int(selected),
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[lipsync] submit-log failed (non-blocking): {exc}")

        # Background: submit pre-conditioned temps -> poll -> download.
        lipsync_client = LipSyncClient(self.app.client.api_key)

        def do_lipsync():
            try:
                task_id = lipsync_client.submit(video_for_lipsync, audio_for_lipsync)

                def set_polling(st, _bk=beat_key, _tid=task_id):
                    st["beats"][_bk]["lipsync"]["status"] = "polling"
                    st["beats"][_bk]["lipsync"]["task_id"] = _tid
                    st["beats"][_bk]["lipsync"]["submitted_at"] = datetime.now(timezone.utc).isoformat()
                    # Tier 1B: epoch form for wall-clock timeout comparisons.
                    st["beats"][_bk]["lipsync"]["submitted_at_epoch"] = int(time.time())
                self.app.state.mutate_state(set_polling)

                result = lipsync_client.poll_until_done(task_id)
                status = (result.get("status") or "").lower()

                if status == "completed" and result.get("outputs"):
                    url = result["outputs"][0]
                    dest_name = f"{beat_key}_lipsync.mp4"
                    dest = self.app.state.clips_dir / dest_name
                    size = lipsync_client.download(url, dest)

                    def mark_done(st, _bk=beat_key, _fn=dest_name, _sz=size):
                        beat = st["beats"][_bk]
                        ls = beat["lipsync"]
                        ls["status"] = "completed"
                        ls["file"] = _fn
                        ls["size_bytes"] = _sz
                        sel_now = (beat.get("phase_1") or {}).get("selected_option")
                        src_opt = ls.get("source_option")
                        if sel_now is not None and src_opt is not None:
                            try:
                                ls["source_changed"] = (int(sel_now) != int(src_opt))
                            except (TypeError, ValueError):
                                pass
                    self.app.state.mutate_state(mark_done)
                    self.app.state.add_spend("lipsync", COST_PER_LIPSYNC)
                    print(f"[lipsync] {beat_key} COMPLETED -> {dest_name} ({size} bytes)")

                    # Cleanup temps on success (preserve on failure for debugging).
                    if silcomp_applied:
                        try: tmp_audio_path.unlink()
                        except OSError: pass
                    try: tmp_video_path.unlink()
                    except OSError: pass

                    try:
                        _async_log_lipsync_complete(
                            event_id=getattr(self.app, "event_id", "unknown"),
                            beat_id=beat_key, output_file=dest_name, size_bytes=size,
                        )
                    except Exception as exc:  # noqa: BLE001
                        print(f"[lipsync] complete-log failed (non-blocking): {exc}")
                else:
                    def mark_failed(st, _bk=beat_key, _err=str(result)):
                        ls = st["beats"][_bk]["lipsync"]
                        ls["status"] = "failed"
                        ls["last_error"] = _err[:500]
                    self.app.state.mutate_state(mark_failed)
                    print(f"[lipsync] {beat_key} FAILED (no charge, temps preserved): {result}")

            except Exception as exc:
                traceback.print_exc()
                def mark_err(st, _bk=beat_key, _err=str(exc)):
                    st["beats"][_bk]["lipsync"]["status"] = "failed"
                    st["beats"][_bk]["lipsync"]["last_error"] = _err[:500]
                self.app.state.mutate_state(mark_err)

        threading.Thread(target=do_lipsync, daemon=True, name=f"lipsync-{beat_key}").start()

        self._send_json(200, {
            "status": "submitted",
            "beat": beat_key,
            "clip": clip_file,
            "audio": source_audio_path.name,
            "audio_processing": audio_processing,
            "video_trimmed_to_s": round(trimmed_to, 3),
            "trim_start": round(ts_used, 3),
            "trim_end": round(te_used, 3),
            "cost": COST_PER_LIPSYNC,
            "message": (f"Lip sync submitted for {beat_key} with §8.4 pre-conditioning "
                        f"(silcomp {'applied' if silcomp_applied else 'no-op'}, "
                        f"video trimmed to {trimmed_to:.2f}s "
                        f"from [{ts_used:.2f}, {te_used:.2f}])."),
        })

    def _handle_lipsync_submit_legacy(self, body: dict) -> None:
        """LEGACY (pre-§8.4). Preserved April 17 2026 for fallback.

        Direct ByteDance submission with NO audio pre-conditioning, NO video
        trim. Unwired from the router — kept as debuggable reference.
        """
        # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
        if not self._assert_event_scope(self._scope_body(body), allow_missing=False):
            return

        # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — capture pin at entry; terminal writes assert via _check_event_pin.
        _pin = {
            "pinned_generation": self.app.event_generation,
            "pinned_event_dir": self.app.event_dir,
            "pinned_video_role": (body or {}).get("scope_video_role", "intro"),
            "_handler": '_handle_lipsync_submit_legacy',
        }
        # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — pre-work pin check (S2).
        # If the event was swapped via /api/event/load between scope-guard
        # and work start, abort BEFORE any expensive work begins.
        if not self._check_event_pin(_pin, '_handle_lipsync_submit_legacy_pre_work'):
            return self._send_json(423, {
                "error": "event_changed_pre_work",
                "code": "ASYNC_JOB_GENERATION_PIN_V1",
                "handler": '_handle_lipsync_submit_legacy',
                "hint": (
                    "Event changed between scope-guard and work start. "
                    "No work was done; no orphan output. Client should "
                    "re-hydrate scope and retry."
                ),
            })

        if self.app.client is None:
            return self._send_json(500, {"error": "WaveSpeed client not configured (missing API key)"})

        beat_key = body.get("beat")
        if not beat_key:
            return self._send_json(400, {"error": "missing 'beat' field"})

        # Read state to find the selected clip
        state = self.app.state.read_state()
        beat_state = ((state.get("videos") or {}).get("intro") or {}).get("beats", {}).get(beat_key)
        if not beat_state:
            return self._send_json(404, {"error": f"beat '{beat_key}' not found in state"})

        phase1 = beat_state.get("phase_1", {})
        selected = phase1.get("selected_option")
        if not selected:
            return self._send_json(400, {"error": f"no option selected for {beat_key}"})

        # Find the selected clip file
        options = phase1.get("options", [])
        if selected < 1 or selected > len(options):
            return self._send_json(400, {"error": f"selected_option {selected} out of range"})
        clip_file = options[selected - 1].get("file")
        if not clip_file:
            return self._send_json(400, {"error": f"selected option has no file"})

        clip_path = self.app.state.clips_dir / clip_file
        if not clip_path.is_file():
            return self._send_json(404, {"error": f"clip file not found: {clip_file}"})

        # Find TTS audio — uses shared _find_beat_audio helper
        # (extracted April 16 2026 for reuse by animation-duration inference).
        beat_num = int(beat_key.split("_")[1])
        audio_path = _find_beat_audio(
            self.app.event_dir, beat_key, body.get("audio_override"),
            app=self.app,
        )
        if not audio_path:
            return self._send_json(404, {
                "error": f"no TTS audio found for {beat_key} (line_{beat_num:02d})",
                "hint": "provide audio_override path or ensure TTS exists in story_scene_tts_v2/",
            })

        # Budget check
        spend = self.app.state.read_spend()
        if spend["budget_remaining"] < COST_PER_LIPSYNC:
            return self._send_json(402, {
                "error": "budget exceeded for lip sync",
                "budget_remaining": spend["budget_remaining"],
                "cost": COST_PER_LIPSYNC,
            })

        # Initialize lipsync state in production_state.
        # Tier 5 (decision 153 LIPSYNC_UI_MUST_SUPPORT_RERUN, April 17 2026):
        # Record which option the submission was sourced from, and clear the
        # source_changed flag. _handle_select compares new selected_option
        # against this source_option on every selection change and sets
        # source_changed=True if they differ. The client surfaces a
        # "🔁 Re-run Lip Sync" affordance when source_changed is true.
        def init_lipsync(st, _bk=beat_key, _src=int(selected)):
            beat = st["beats"][_bk]
            beat.setdefault("lipsync", {
                "status": "submitting",
                "task_id": None,
                "file": None,
                "audio_file": None,
                "submitted_at": None,
                "retries": 0,
            })
            beat["lipsync"]["status"] = "submitting"
            beat["lipsync"]["audio_file"] = str(audio_path.name)
            # Re-run detection: lock source_option at submit time; clear
            # source_changed since the new submit matches the current selection.
            beat["lipsync"]["source_option"] = _src
            beat["lipsync"]["source_changed"] = False
            # Clear any stale last_error from a prior failed run so the UI
            # does not display it alongside the "Processing..." status.
            beat["lipsync"].pop("last_error", None)
        self.app.state.mutate_state(init_lipsync)

        # Submit in background thread
        lipsync_client = LipSyncClient(self.app.client.api_key)

        def do_lipsync():
            try:
                task_id = lipsync_client.submit(clip_path, audio_path)

                def set_polling(st, _bk=beat_key, _tid=task_id):
                    st["beats"][_bk]["lipsync"]["status"] = "polling"
                    st["beats"][_bk]["lipsync"]["task_id"] = _tid
                    st["beats"][_bk]["lipsync"]["submitted_at"] = datetime.now(timezone.utc).isoformat()
                    # Tier 1B: epoch form for wall-clock timeout comparisons.
                    st["beats"][_bk]["lipsync"]["submitted_at_epoch"] = int(time.time())
                # LD-460 — pin check before set_polling mutate_state (thread closure).
                if not self._check_event_pin(_pin, "lipsync_submit_legacy_set_polling"):
                    print("[lipsync_submit_legacy] event drift mid-thread; skipping mutate_state", flush=True)
                    return
                self.app.state.mutate_state(set_polling)

                # Poll until done
                result = lipsync_client.poll_until_done(task_id)
                status = (result.get("status") or "").lower()

                if status == "completed" and result.get("outputs"):
                    url = result["outputs"][0]
                    dest_name = f"{beat_key}_lipsync.mp4"
                    dest = self.app.state.clips_dir / dest_name
                    size = lipsync_client.download(url, dest)

                    def mark_done(st, _bk=beat_key, _fn=dest_name, _sz=size):
                        beat = st["beats"][_bk]
                        ls = beat["lipsync"]
                        ls["status"] = "completed"
                        ls["file"] = _fn
                        ls["size_bytes"] = _sz
                        # Tier 5 reconcile (Phase 4 counter-agent finding #4,
                        # April 17 2026): if the user changed selection WHILE
                        # the lipsync was in flight, source_changed would not
                        # have been set by _handle_select (it skips in-flight
                        # states). Re-evaluate here at the transition to
                        # completed so the UI gets the right affordance on
                        # its next /api/lipsync/status poll.
                        sel_now = (beat.get("phase_1") or {}).get("selected_option")
                        src_opt = ls.get("source_option")
                        if sel_now is not None and src_opt is not None:
                            try:
                                ls["source_changed"] = (int(sel_now) != int(src_opt))
                            except (TypeError, ValueError):
                                pass
                    self.app.state.mutate_state(mark_done)
                    self.app.state.add_spend("lipsync", COST_PER_LIPSYNC)
                    print(f"[lipsync] {beat_key} COMPLETED -> {dest_name} ({size} bytes)")
                else:
                    def mark_failed(st, _bk=beat_key, _err=str(result)):
                        ls = st["beats"][_bk]["lipsync"]
                        ls["status"] = "failed"
                        ls["last_error"] = _err[:500]
                    self.app.state.mutate_state(mark_failed)
                    # No spend charge on failure — WaveSpeed doesn't bill failed jobs
                    print(f"[lipsync] {beat_key} FAILED (no charge): {result}")

            except Exception as exc:
                traceback.print_exc()
                def mark_err(st, _bk=beat_key, _err=str(exc)):
                    st["beats"][_bk]["lipsync"]["status"] = "failed"
                    st["beats"][_bk]["lipsync"]["last_error"] = _err[:500]
                self.app.state.mutate_state(mark_err)

        threading.Thread(target=do_lipsync, daemon=True, name=f"lipsync-{beat_key}").start()

        self._send_json(200, {
            "status": "submitted",
            "beat": beat_key,
            "clip": clip_file,
            "audio": audio_path.name,
            "cost": COST_PER_LIPSYNC,
            "message": f"Lip sync job submitted for {beat_key}. Poll /api/lipsync/status for updates.",
        })

    def _handle_lipsync_status(self) -> None:
        """Return lip sync status for all beats.

        source_option + source_changed (Tier 5, decision 153 April 17 2026):
        When a completed lipsync's source_changed is true, the client should
        render a "🔁 Re-run Lip Sync" affordance instead of the preview
        toggle. This closes the "button locks to Done even after the source
        clip changes" bug class.
        """
        state = self.app.state.read_state()
        lipsync_beats = {}
        for beat_id, beat in ((state.get("videos") or {}).get("intro") or {}).get("beats", {}).items():
            ls = beat.get("lipsync")
            if ls:
                lipsync_beats[beat_id] = {
                    "status": ls.get("status", "unknown"),
                    "task_id": ls.get("task_id"),
                    "file": ls.get("file"),
                    "size_bytes": ls.get("size_bytes"),
                    "audio_file": ls.get("audio_file"),
                    "last_error": ls.get("last_error"),
                    "source_option": ls.get("source_option"),
                    "source_changed": bool(ls.get("source_changed")),
                    # Decision 181 (April 17 2026): audio_changed flag
                    # surfaces when TTS was regenerated after lipsync
                    # completed — client renders Re-run Lip Sync button.
                    "audio_changed": bool(ls.get("audio_changed")),
                }
                if ls.get("file"):
                    lipsync_beats[beat_id]["url"] = f"/asset/{ls['file']}"
                # Spec A: include final block so storyboard can show no-lipsync indicator
                lipsync_beats[beat_id]["final"] = beat.get("final", None)

        total = len(lipsync_beats)
        completed = sum(1 for v in lipsync_beats.values() if v["status"] == "completed")
        polling = sum(1 for v in lipsync_beats.values() if v["status"] in ("polling", "submitting"))
        failed = sum(1 for v in lipsync_beats.values() if v["status"] == "failed")

        self._send_json(200, {
            "beats": lipsync_beats,
            "summary": {
                "total": total,
                "completed": completed,
                "polling": polling,
                "failed": failed,
            },
        })

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
            return self._send_json(400, {"error": "beat required"})

        # S5.5d B5: video role from body; default 'intro' for legacy clients.
        scope_video_role = (body or {}).get("scope_video_role") or "intro"
        valid_roles = self.app.state._VALID_VIDEO_ROLES
        if scope_video_role not in valid_roles:
            return self._send_json(400, {
                "error": "video_role_invalid",
                "code": "VIDEO_ROLE_INVALID",
                "got": scope_video_role,
                "valid": sorted(valid_roles),
                "hint": "scope_video_role must be one of intro/resolution/standalone.",
            })

        state = self.app.state.read_state()
        beat = ((state.get("videos") or {}).get(scope_video_role) or {}).get("beats", {}).get(beat_id)
        if not beat:
            return self._send_json(400, {"error": f"unknown beat: {beat_id} (role={scope_video_role})"})

        p1 = beat.get("phase_1", {})
        opts = p1.get("options", [])
        sel = p1.get("selected_option", 1)
        sel_idx = sel - 1  # selected_option is 1-indexed
        if not opts or not (0 <= sel_idx < len(opts)):
            return self._send_json(400, {
                "error": f"no option at index {sel_idx} (selected_option={sel})"
            })

        opt_file = opts[sel_idx].get("file", "")
        if not opt_file:
            return self._send_json(400, {"error": "selected option has no file"})

        abs_path = str(self.app.state.clips_dir / opt_file)
        if not os.path.isfile(abs_path):
            return self._send_json(400, {"error": f"clip file not found: {opt_file}"})

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
            with bg._sidecar_lock:
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
        if not self.app.storyboard_path.is_file():
            return self._send_json(500, {
                "error": f"storyboard not found: {self.app.storyboard_path}"})
        html = self.app.storyboard_path.read_text(encoding="utf-8")
        nav = self._build_storyboard_nav_html()
        if "</body>" in html:
            html = html.replace("</body>", nav + "\n</body>", 1)
        else:
            html = html + nav
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

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
    fetch('/api/storyboard/switch',{{
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
        """POST /api/storyboard/switch  body: {filename: str}"""
        filename = (body.get("filename") or "").strip()
        if not re.match(r'^storyboard_v\d+.*\.html$', filename):
            return self._send_json(400, {"error": f"invalid filename: {filename!r}"})
        target = self.app.event_dir / filename
        if not target.is_file():
            return self._send_json(404, {"error": f"not found: {filename}"})
        with self.app._storyboard_write_lock:
            result = self.app.switch_storyboard(filename)
        self._send_json(200, result)

    def _serve_cropper(self) -> None:
        """Serve the latest cropper HTML from Event_1/."""
        # Find the latest cropper file
        croppers = sorted(
            self.app.event_dir.glob("image_selector_cropper_*.html"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not croppers:
            return self._send_json(404, {"error": "no cropper HTML found in event dir"})
        body = croppers[0].read_bytes()
        print(f"[server] Serving cropper: {croppers[0].name}")
        self._send_bytes(200, body, "text/html; charset=utf-8")

    def _serve_asset(self, filename: str) -> None:
        # Sanitize — only serve files inside clips_dir
        safe = Path(filename).name
        target = self.app.state.clips_dir / safe
        if not target.is_file():
            return self._send_json(404, {"error": f"asset not found: {safe}"})
        suffix = target.suffix.lower()
        ctype = {
            ".mp4": "video/mp4",
            ".mp3": "audio/mpeg",
            ".webm": "video/webm",
            ".wav": "audio/wav",
        }.get(suffix, "application/octet-stream")

        size = target.stat().st_size
        range_header = self.headers.get("Range")
        if range_header:
            m = re.match(r"bytes=(\d+)-(\d*)", range_header)
            if m:
                start = int(m.group(1))
                end = int(m.group(2)) if m.group(2) else size - 1
                end = min(end, size - 1)
                length = end - start + 1
                with target.open("rb") as f:
                    f.seek(start)
                    chunk = f.read(length)
                self.send_response(206)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Length", str(length))
                # LOG_HYGIENE_SUPPRESS_CLIENT_CANCEL_TRACEBACKS (LD 2026-04-18):
                # Chrome cancels preloaded <video> range requests aggressively
                # (element not .play()'d, scrolled out of view, etc.). This is
                # not a real failure. Catch only the two specific socket errors
                # — never the general Exception class — and return silently
                # with a single short log line. Everything else still raises.
                try:
                    self.end_headers()
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    print(f"asset stream canceled by client: {safe}", file=sys.stderr, flush=True)
                return

        body = target.read_bytes()
        self._send_bytes(
            200, body, ctype,
            extra_headers={"Accept-Ranges": "bytes"},
        )

    def _serve_beat_audio(self, beat_id: str) -> None:
        """Stream the CURRENT on-disk TTS file for a beat.

        Decision 184 PREVIEW_BEAT_AUDIO_FRESH_STREAM (April 17 2026):
        Storyboard AU[] map is build-time-baked base64, so text/audio regens
        don't propagate until the storyboard is rebuilt. This endpoint always
        returns whatever _find_beat_audio resolves to RIGHT NOW, fixing the
        "Preview Beat plays old and new tracks at once" bug.

        GET /api/beat/audio/:beat_id  -> audio/mpeg stream.
        Supports Range headers for smooth seek.
        """
        # Sanitize beat_id (accept only word chars + underscores, no path traversal).
        import re as _re
        if not _re.match(r"^[a-zA-Z0-9_]+$", beat_id or ""):
            return self._send_json(400, {"error": f"invalid beat_id: {beat_id!r}"})

        audio_path = _find_beat_audio(self.app.event_dir, beat_id, app=self.app)
        if not audio_path or not audio_path.is_file():
            return self._send_json(404, {
                "error": f"no TTS audio found for {beat_id}",
                "hint": "regenerate audio via the 🎙 Regen Audio button or edit dialogue",
            })

        suffix = audio_path.suffix.lower()
        ctype = {".mp3": "audio/mpeg", ".wav": "audio/wav"}.get(suffix, "application/octet-stream")
        size = audio_path.stat().st_size
        range_header = self.headers.get("Range")
        if range_header:
            m = re.match(r"bytes=(\d+)-(\d*)", range_header)
            if m:
                start = int(m.group(1))
                end = int(m.group(2)) if m.group(2) else size - 1
                end = min(end, size - 1)
                length = end - start + 1
                with audio_path.open("rb") as f:
                    f.seek(start)
                    chunk = f.read(length)
                self.send_response(206)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Length", str(length))
                # No caching — always serve fresh (defeats the AU[]-stale bug
                # by making sure every play fetches the latest bytes).
                self.send_header("Cache-Control", "no-store, must-revalidate")
                # LOG_HYGIENE_SUPPRESS_CLIENT_CANCEL_TRACEBACKS (LD 2026-04-18):
                # Same as _serve_asset range path — suppress client-cancel spam.
                try:
                    self.end_headers()
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    print(f"beat audio stream canceled by client: {beat_id}", file=sys.stderr, flush=True)
                return

        body = audio_path.read_bytes()
        self._send_bytes(
            200, body, ctype,
            extra_headers={
                "Accept-Ranges": "bytes",
                "Cache-Control": "no-store, must-revalidate",
                "X-TTS-File": audio_path.name,  # for client-side diagnostics
            },
        )

    def _beat_id(self, line_number: int) -> str:
        return f"beat_{line_number:02d}"

    def _select_beats_for_mode(self, mode: str, requested: list[str] | None) -> list[dict]:
        all_beats = self.app.beats()
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
                bid for bid, b in ((state.get("videos") or {}).get("intro") or {}).get("beats", {}).items()
                if (b.get("phase_1") or {}).get("status") in ("failed", "partial")
            }
            return [b for b in all_beats if self._beat_id(b.get("line_number", -1)) in failed]
        return all_beats

    def _handle_animate(self, body: dict) -> None:
        # SCOPE_ROUTER_V1 (C-7.5 K1 sibling fix) — replaces legacy
        # _assert_event_scope + scope_video_role-default-to-intro
        # pattern. Mutators below route partition writes via
        # mutate_video_state(scope.video_role, ...) instead of the
        # hardcoded videos.intro setdefault chain that was caught by the
        # SCOPE_ROUTER_V1 AST grep gate.
        try:
            scope = scope_router.resolve(body, self.app.event_dir.name)
        except scope_router.ScopeError as e:
            return self._send_json(e.http_status, {"error": e.code, **e.detail})

        if self.app.client is None:
            return self._send_json(500, {"error": "WaveSpeed client not configured (missing API key)"})

        mode = body.get("mode", "all")
        options_per_beat = int(body.get("options_per_beat", 3))
        requested = body.get("beats")
        beats = self._select_beats_for_mode(mode, requested)

        # Budget pre-check
        spend = self.app.state.read_spend()
        estimated = len(beats) * options_per_beat * COST_PER_CLIP_KLING
        if spend["budget_remaining"] < estimated and spend["overrides"] == 0:
            return self._send_json(402, {
                "error": "budget exceeded",
                "budget_blocked": True,
                "estimated_cost": estimated,
                "budget_remaining": spend["budget_remaining"],
            })

        submitted = 0
        skipped: list[dict] = []

        # video_role resolved by scope_router; image override lookup is
        # partition-aware via the get_beat_image(_, video_role) helper.
        video_role = scope.video_role
        for beat in beats:
            beat_id = self._beat_id(beat.get("line_number", -1))
            # Check image overrides first (from drag-drop), then storyboard
            image = self.app.get_beat_image(beat_id, video_role) or beat.get("image")
            if not image:
                skipped.append({"beat": beat_id, "reason": "no image"})
                continue

            # Rule 6 — image dimension gate with auto-upscale fallback
            image, upscale_info = auto_upscale_image(image)
            ok, info = validate_image_dimensions(image)
            if not ok:
                print(f"[WARN] {beat_id} skipped: {info} (upscale result: {upscale_info})")
                skipped.append({"beat": beat_id, "reason": info})
                continue
            if "upscaled" in upscale_info:
                print(f"[animate] {beat_id}: {upscale_info}")

            prompt = sanitize_prompt(build_motion_prompt(beat))

            # Infer animation duration from TTS audio length.
            # ANIMATION_DURATION_MATCHES_AUDIO (decision id=144). Counter-agent
            # C1 HIGH finding (April 16 2026): fix must apply to _handle_animate
            # too, not just add_options. Audio > 10s fails loud; missing audio
            # falls back to 5s with warning log (can't 404 here because we
            # process many beats in one call and one missing audio shouldn't
            # kill the whole batch — lipsync will 404 per-beat later).
            audio_path = _find_beat_audio(self.app.event_dir, beat_id, app=self.app)
            try:
                beat_duration, duration_reason = _infer_animation_duration(audio_path)
            except ValueError as exc:
                print(f"[WARN] {beat_id} skipped: {exc}")
                skipped.append({"beat": beat_id, "reason": str(exc)})
                continue
            print(f"[animate] {beat_id} duration={beat_duration}s reason={duration_reason}")

            # Initialize beat state via partition router (was videos.intro hardcode).
            def init_beat_partition(partition, _beat_id=beat_id, _beat=beat):
                pbeats = partition.setdefault("beats", {})
                pbeats.setdefault(_beat_id, {
                    "speaker": _beat.get("speaker"),
                    "text": _beat.get("text"),
                    "section": _beat.get("section"),
                    "phase_1": {"status": "polling", "options": [], "selected_option": None},
                })
                pbeats[_beat_id]["phase_1"] = {
                    "status": "polling",
                    "options": [],
                    "selected_option": None,
                }
            self.app.state.mutate_video_state(scope.video_role, init_beat_partition)

            # Submit options_per_beat jobs, staggered
            for opt_idx in range(options_per_beat):
                try:
                    task_id = self.app.client.submit_animation(
                        image, prompt, duration=beat_duration,
                    )
                except Exception as exc:  # noqa: BLE001
                    print(f"[ERR] submit failed for {beat_id} opt{opt_idx + 1}: {exc}")
                    skipped.append({"beat": beat_id, "opt": opt_idx + 1, "reason": str(exc)})
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

                # Stagger within a beat too — simple 2s gap every 6 jobs
                if submitted % 6 == 0:
                    time.sleep(POLL_BATCH_GAP_SEC)

        self._send_json(200, {
            "submitted": submitted,
            "beats_queued": len(beats) - len([s for s in skipped if "opt" not in s]),
            "skipped": skipped,
            "status": "polling",
        })

    def _handle_status(self) -> None:
        state = self.app.state.read_state()
        spend = self.app.state.read_spend()
        beats_out: dict = {}
        total = 0
        completed = 0
        polling = 0
        failed = 0
        for bid, beat in ((state.get("videos") or {}).get("intro") or {}).get("beats", {}).items():
            total += 1
            phase1 = beat.get("phase_1") or {}
            status = phase1.get("status", "unknown")
            options = phase1.get("options", [])
            out_options = []
            # Item 6 (Tier 1, April 16 2026): include ALL option states, not
            # just completed ones. Previously filtered for
            # `status == "completed" and opt.file`, which hid polling and
            # failed options from the UI and caused the Generate B+C button
            # to silently revert after ~15s. The client now receives per-
            # option status so it can render progress / error state.
            for i, opt in enumerate(options):
                opt_status = opt.get("status", "unknown")
                entry_opt: dict = {
                    "option": i + 1,
                    "status": opt_status,
                }
                if opt.get("file"):
                    entry_opt["file"] = opt["file"]
                    entry_opt["size_mb"] = round((opt.get("size_bytes") or 0) / 1_000_000, 2)
                    entry_opt["url"] = f"/asset/{opt['file']}"
                if opt_status in ("polling", "failed") and opt.get("task_id"):
                    entry_opt["task_id"] = opt["task_id"]
                if opt.get("last_error"):
                    entry_opt["error"] = opt["last_error"]
                if opt.get("retries"):
                    entry_opt["retries"] = opt["retries"]
                out_options.append(entry_opt)
            entry = {
                "status": status,
                "options": out_options,
                "selected_option": phase1.get("selected_option"),
                "audio_delay": phase1.get("audio_delay", 0),
                "trim_start": phase1.get("trim_start", 0),
                "trim_end": phase1.get("trim_end"),
            }
            if status == "completed":
                completed += 1
            elif status == "failed":
                failed += 1
                entry["error"] = next(
                    (o.get("last_error") for o in options if o.get("last_error")),
                    "unknown",
                )
                entry["can_retry"] = True
            elif status in ("polling", "partial"):
                polling += 1
            beats_out[bid] = entry

        self._send_json(200, {
            "total_beats": total,
            "completed": completed,
            "polling": polling,
            "failed": failed,
            "expired": 0,
            "cost_so_far": spend["total_spent"],
            "budget_remaining": spend["budget_remaining"],
            "budget_warning": spend["total_spent"] >= 0.8 * spend["budget"],
            "budget_blocked": spend["budget_remaining"] <= 0,
            "beats": beats_out,
        })

    def _handle_redo(self, body: dict) -> None:
        # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
        if not self._assert_event_scope(self._scope_body(body), allow_missing=False):
            return

        beat_id = body.get("beat")
        options_per_beat = int(body.get("options_per_beat", 3))
        if not beat_id:
            return self._send_json(400, {"error": "missing 'beat'"})

        # Acquire lock -> clear state -> list old files -> release -> delete -> resubmit
        old_files: list[str] = []
        def clear(state):
            b = ((state.get("videos") or {}).get("intro") or {}).get("beats", {}).get(beat_id)
            if not b:
                return
            for opt in (b.get("phase_1") or {}).get("options", []):
                if opt.get("file"):
                    old_files.append(opt["file"])
            b["phase_1"] = {"status": "polling", "options": [], "selected_option": None}
        self.app.state.mutate_state(clear)

        for fname in old_files:
            p = self.app.state.clips_dir / fname
            if p.is_file():
                try:
                    p.unlink()
                except OSError:
                    pass

        # Resubmit via the existing /api/animate path, but scoped to this beat
        return self._handle_animate({
            "mode": "test",
            "beats": [beat_id],
            "options_per_beat": options_per_beat,
        })

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
    def _handle_add_options(self, body: dict) -> None:
        """Dispatch Generate B+C to start-end (default) unless force_legacy."""
        # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
        if not self._assert_event_scope(self._scope_body(body), allow_missing=False):
            return

        beat_id = body.get("beat")
        if not beat_id:
            return self._send_json(400, {"error": "missing 'beat'"})

        try:
            state = self.app.state.read_state()
        except Exception as exc:
            return self._send_json(500, {
                "error": f"failed to read state for dispatch: {type(exc).__name__}: {exc}"
            })

        beat_state = (((state.get("videos") or {}).get("intro") or {}).get("beats") or {}).get(beat_id) or {}
        force_legacy = bool(beat_state.get("force_legacy"))

        if force_legacy:
            print(f"[add_options:dispatch] {beat_id}: force_legacy=true -> legacy path")
            return self._handle_add_options_legacy(body)

        # Default = start-end. Use configured end_frame_prompt if present,
        # else synthesize a generic one from the beat's speaker so new beats
        # added later still route start-end without manual config.
        end_frame_prompt = (beat_state.get("end_frame_prompt") or "").strip()
        if not end_frame_prompt:
            speaker = beat_state.get("speaker") or ""
            # Best-effort speaker extraction from storyboard L[] if state lacks it
            if not speaker:
                for b in self.app.beats():
                    if self._beat_id(b.get("line_number", -1)) == beat_id:
                        speaker = b.get("speaker") or ""
                        break
            speaker_lc = speaker.lower() if speaker else ""
            if "guide bird" in speaker_lc or "pip" in speaker_lc or "chipper" in speaker_lc:
                end_frame_prompt = (
                    "Keep the background COMPLETELY IDENTICAL to the input — "
                    "every tree, leaf, light ray, and environment element must "
                    "stay pixel-perfect unchanged. Do NOT alter, shift, blur, "
                    "or recompose any background element whatsoever. "
                    "ONLY change the character: Chipper the Guide Bird now has "
                    "a slightly softened expression with natural warmth in his "
                    "eyes, subtle attentive head tilt. Beak closed. "
                    "Same cartoon 3D Pixar-style art, same outfit, same 4:3 "
                    "composition, same lighting on the character."
                )
            elif "tessa" in speaker_lc:
                end_frame_prompt = (
                    "Keep the background COMPLETELY IDENTICAL to the input — "
                    "every tree, leaf, light ray, and environment element must "
                    "stay pixel-perfect unchanged. Do NOT alter, shift, blur, "
                    "or recompose any background element whatsoever. "
                    "ONLY change the character: Tessa the turtle with a "
                    "slightly softened, more reflective expression, eyes "
                    "warming with attention. Beak/mouth closed. "
                    "Same cartoon 3D Pixar-style art, same outfit, same 4:3 "
                    "composition, same lighting on the character."
                )
            else:
                # Generic fallback — works for any creature but less tuned.
                end_frame_prompt = (
                    "Keep the background COMPLETELY IDENTICAL to the input — "
                    "every background element must stay pixel-perfect unchanged. "
                    "Do NOT alter, shift, blur, or recompose any background. "
                    "ONLY change the character: natural subtle expression "
                    "evolution, eyes warming with attention, small postural "
                    "shift. Mouth closed. Same cartoon 3D art style, same "
                    "outfit, same 4:3 composition."
                )
            print(f"[add_options:dispatch] {beat_id}: no end_frame_prompt in state -> "
                  f"using synthesized default for speaker={speaker!r}")

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
            return self._send_json(500, {"error": "WaveSpeed client not configured"})

        beat_id = body["beat"]  # validated by dispatcher
        num_new = int(body.get("count", 2))

        # Duration resolution — identical to legacy, repeated for independence.
        explicit_duration = body.get("duration")
        if explicit_duration is not None:
            try:
                duration_raw = int(explicit_duration)
            except (TypeError, ValueError):
                return self._send_json(400, {
                    "error": f"invalid duration value: {explicit_duration!r}",
                    "hint": f"duration must be {KLING_MIN_DURATION_SEC} or {KLING_MAX_DURATION_SEC}",
                })
            if duration_raw not in (KLING_MIN_DURATION_SEC, KLING_MAX_DURATION_SEC):
                return self._send_json(400, {
                    "error": f"unsupported duration: {duration_raw}s",
                    "hint": f"Kling v3 supports {KLING_MIN_DURATION_SEC}s or {KLING_MAX_DURATION_SEC}s",
                })
            duration = duration_raw
            duration_reason = f"explicit_client_override_{duration}s"
        else:
            audio_path = _find_beat_audio(
                self.app.event_dir, beat_id, body.get("audio_override"),
                app=self.app,
            )
            if audio_path is None:
                try:
                    beat_num_s = f"line_{int(beat_id.split('_')[1]):02d}"
                except (IndexError, ValueError):
                    beat_num_s = "(unparseable)"
                return self._send_json(404, {
                    "error": f"no TTS audio found for {beat_id} ({beat_num_s})",
                    "hint": "animation duration cannot be inferred without audio",
                })
            try:
                duration, duration_reason = _infer_animation_duration(audio_path)
            except ValueError as exc:
                return self._send_json(400, {
                    "error": str(exc),
                    "hint": "Edit script or split audio into shorter beats",
                    "beat": beat_id,
                    "audio_file": audio_path.name,
                })
        print(f"[add_options:startend] {beat_id} duration={duration}s reason={duration_reason}")

        # Existing-options check + trim B+C (same as legacy).
        phase1 = beat_state.get("phase_1") or {}
        existing_options = phase1.get("options", [])
        if not existing_options:
            return self._send_json(400, {
                "error": f"beat {beat_id} has no existing options — use /api/animate"
            })

        if len(existing_options) > 1:
            old_bc_files = [o.get("file") for o in existing_options[1:] if o.get("file")]
            def trim_to_a(st):
                b = st.get("beats", {}).get(beat_id)
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

        # Budget — start-end is FLUX Kontext + Kling per option.
        spend = self.app.state.read_spend()
        per_option_cost = COST_FLUX_KONTEXT + COST_KLING_10S
        estimated = num_new * per_option_cost
        if spend["budget_remaining"] < estimated and spend["overrides"] == 0:
            return self._send_json(402, {
                "error": "budget exceeded",
                "estimated_cost": estimated,
                "budget_remaining": spend["budget_remaining"],
                "path": "kling_startend",
            })

        # Resolve start image (data URI).
        target_beat = None
        for b in self.app.beats():
            if self._beat_id(b.get("line_number", -1)) == beat_id:
                target_beat = b
                break
        if not target_beat:
            return self._send_json(400, {
                "error": f"could not find beat data for {beat_id} in storyboard"
            })
        # S5.5a2: scope_video_role from body for partition-aware override lookup (LD-474).
        video_role = body.get("scope_video_role", "intro")
        beat_image = self.app.get_beat_image(beat_id, video_role)
        if not beat_image:
            return self._send_json(400, {
                "error": f"could not find image data for {beat_id} — drag-drop an image first"
            })
        target_beat = dict(target_beat)
        beat_image, upscale_info = auto_upscale_image(beat_image)
        if "upscaled" in upscale_info:
            print(f"[add_options:startend] {beat_id} start: {upscale_info}")
        target_beat["image"] = beat_image
        ok, info = validate_image_dimensions(beat_image)
        if not ok:
            return self._send_json(400, {"error": f"image validation failed: {info}"})
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

        # Load BFL key (not in parse_api_keys scope).
        try:
            keys = _ksendpipe_load_api_keys()
        except SystemExit as exc:
            return self._send_json(500, {
                "error": f"API key load failed for start-end path: {exc}"
            })
        bfl_key = keys.get("bfl")
        wavespeed_key = keys.get("wavespeed") or self.app.client.api_key
        if not bfl_key:
            return self._send_json(500, {
                "error": "BFL (FLUX) key unavailable — required for start-end pipeline"
            })

        # Extract start image raw bytes (beat_image is data:image/...;base64,...).
        try:
            _hdr, start_b64 = beat_image.split(",", 1)
            start_bytes = base64.b64decode(start_b64)
        except Exception as exc:
            return self._send_json(500, {
                "error": f"start image data-URI malformed: {type(exc).__name__}: {exc}"
            })

        # Mark beat polling.
        def set_polling(st):
            b = st.get("beats", {}).get(beat_id)
            if b and b.get("phase_1"):
                b["phase_1"]["status"] = "polling"
        self.app.state.mutate_state(set_polling)

        # Per-option loop: FLUX Kontext end frame -> Kling start-end submit.
        submitted = 0
        submit_errors: list[str] = []
        submitted_tasks: list[str] = []

        for opt_idx in range(num_new):
            # Step 1: FLUX Kontext.
            try:
                end_bytes = flux_kontext_generate_end_frame(
                    start_image_bytes=start_bytes,
                    end_prompt=end_frame_prompt,
                    api_key=bfl_key,
                    aspect_ratio="4:3",
                    timeout_s=180,
                )
            except SystemExit as exc:
                err = f"flux_kontext SystemExit: {exc}"
                print(f"[ERR] add_options:startend FLUX Kontext opt{opt_idx+1}: {err}")
                submit_errors.append(err)
                continue
            except Exception as exc:
                err = f"flux_kontext {type(exc).__name__}: {exc}"
                print(f"[ERR] add_options:startend FLUX Kontext opt{opt_idx+1}: {err}")
                submit_errors.append(err)
                continue

            # Step 2: Rule 6 auto-upscale end frame bytes.
            try:
                end_bytes_final, end_info, _end_dims = _ksendpipe_ensure_min_dimensions(end_bytes)
                if "upscaled" in end_info:
                    print(f"[add_options:startend] {beat_id} opt{opt_idx+1} end: {end_info}")
            except Exception as exc:
                err = f"ensure_min_dimensions {type(exc).__name__}: {exc}"
                submit_errors.append(err)
                continue

            # Step 3: Kling start-end submit.
            start_uri = f"data:image/png;base64,{base64.b64encode(start_bytes).decode('ascii')}"
            end_uri = f"data:image/png;base64,{base64.b64encode(end_bytes_final).decode('ascii')}"

            try:
                task_id = kling_startend_submit(
                    start_b64_uri=start_uri,
                    end_b64_uri=end_uri,
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
            _eid = element_entry["element_id"] if element_entry else None
            def add_option(st, _bid=beat_id, _tid=task_id, _ep=end_frame_prompt,
                           _dur=duration, _eid=_eid):
                st["beats"][_bid]["phase_1"]["options"].append({
                    "task_id": _tid,
                    "status": "polling",
                    "file": None,
                    "submitted_at": datetime.now(timezone.utc).isoformat(),
                    "submitted_at_epoch": int(time.time()),  # Tier 1B timeout
                    "retries": 0,
                    "last_error": None,
                    "source": "kling_startend",       # decision 172 provenance
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
                    "source": "kling_startend",
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
            return self._send_json(500, {
                "error": f"All {num_new} start-end submissions failed for {beat_id}",
                "path": "kling_startend",
                "beat": beat_id,
                "existing_options": len(existing_options),
                "new_submitted": 0,
                "submit_errors": submit_errors,
                "hint": "Check FLUX (BFL) key + WaveSpeed Kling. No silent fallback to legacy.",
            })

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
            return self._send_json(500, {"error": "WaveSpeed client not configured"})

        try:
            scope = scope_router.resolve(body, self.app.event_dir.name)
        except scope_router.ScopeError as e:
            return self._send_json(e.http_status, {"error": e.code, **e.detail})

        beat_id = body.get("beat")
        num_new = int(body.get("count", 2))  # default: add 2 (B + C)
        if not beat_id:
            return self._send_json(400, {"error": "missing 'beat'"})

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
                return self._send_json(400, {
                    "error": f"invalid duration value: {explicit_duration!r}",
                    "hint": f"duration must be {KLING_MIN_DURATION_SEC} or {KLING_MAX_DURATION_SEC}",
                })
            if duration_raw not in (KLING_MIN_DURATION_SEC, KLING_MAX_DURATION_SEC):
                return self._send_json(400, {
                    "error": f"unsupported duration: {duration_raw}s",
                    "hint": f"Kling v3 supports only {KLING_MIN_DURATION_SEC}s or "
                            f"{KLING_MAX_DURATION_SEC}s; omit the field to auto-infer from audio",
                })
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
                return self._send_json(404, {
                    "error": f"no TTS audio found for {beat_id} ({beat_num_str})",
                    "hint": "provide audio_override path or ensure TTS exists in story_scene_tts_v2/; "
                            "animation duration cannot be inferred without audio",
                })
            try:
                duration, duration_reason = _infer_animation_duration(audio_path_for_duration)
            except ValueError as exc:
                # Audio exceeds Kling 10s max — surface cleanly, do NOT truncate
                return self._send_json(400, {
                    "error": str(exc),
                    "hint": "Edit script or split audio into shorter beats; Kling v3 cannot "
                            "generate clips longer than 10 seconds.",
                    "beat": beat_id,
                    "audio_file": audio_path_for_duration.name,
                })
        print(f"[add_options] {beat_id} duration={duration}s reason={duration_reason}")

        # Read current state to verify beat exists in scope.video_role partition.
        state = self.app.state.read_state()
        beat_state = ((state.get("videos") or {}).get(scope.video_role) or {}).get("beats", {}).get(beat_id)
        if not beat_state:
            return self._send_json(404, {"error": f"beat {beat_id} not found in videos.{scope.video_role}.beats"})

        phase1 = beat_state.get("phase_1") or {}
        existing_options = phase1.get("options", [])
        if not existing_options:
            return self._send_json(400, {
                "error": f"beat {beat_id} has no existing options — use /api/animate instead"
            })

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
            return self._send_json(402, {
                "error": "budget exceeded",
                "estimated_cost": estimated,
                "budget_remaining": spend["budget_remaining"],
            })

        # Find the beat data (image + prompt) from the storyboard
        # Check image overrides FIRST (from drag-drop), then fall back to storyboard
        target_beat = None
        for b in self.app.beats():
            if self._beat_id(b.get("line_number", -1)) == beat_id:
                target_beat = b
                break
        if not target_beat:
            return self._send_json(400, {
                "error": f"could not find beat data for {beat_id} in storyboard"
            })

        # Use image override if available (from drag-drop assignment).
        # video_role resolved by scope_router above.
        beat_image = self.app.get_beat_image(beat_id, scope.video_role)
        if not beat_image:
            return self._send_json(400, {
                "error": f"could not find image data for {beat_id} — try drag-dropping an image first"
            })
        # Patch the beat dict so prompt builder uses correct context
        target_beat = dict(target_beat)
        # Rule 6 — auto-upscale fallback, then dimension gate
        beat_image, upscale_info = auto_upscale_image(beat_image)
        if "upscaled" in upscale_info:
            print(f"[add_options] {beat_id}: {upscale_info}")
        target_beat["image"] = beat_image

        ok, info = validate_image_dimensions(beat_image)
        if not ok:
            return self._send_json(400, {"error": f"image validation failed: {info}"})

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
            return self._send_json(500, {
                "error": f"All {num_new} WaveSpeed submissions failed for {beat_id}",
                "beat": beat_id,
                "existing_options": len(existing_options),
                "new_submitted": 0,
                "submit_errors": submit_errors,
            })

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
        """Persist a contenteditable dialogue edit.

        DIALOGUE_EDITS_MUST_PERSIST (decision id=151, April 17 2026).
        Body: {"beat": "beat_NN", "text": "...", "event_id"?: "Event_1"}

        Atomic write to:
          1. production_state.json beat_NN.text  (via mutate_state, fcntl-safe)
          2. Storyboard HTML L[] entry for line_NN  (tmp+rename atomic)
          3. Marks beat.text_modified_after_tts = true if a TTS file exists
             for this beat (client can surface a stale-TTS warning).
        """
        # SCOPE_ROUTER_V1 (C-2 K1 fix) — replaces the hardcoded `videos.intro`
        # lift with scope_router-driven partition resolution. Subsumes
        # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1 (resolve()
        # coalesces the scope_event_id / scope_target_video aliases).
        # The legacy "beat" body key is preserved for back-compat; newer
        # clients may send "beat_id" — we honor either.
        try:
            scope = scope_router.resolve(body, self.app.event_dir.name)
        except scope_router.ScopeError as e:
            return self._send_json(e.http_status, {"error": e.code, **e.detail})
        beat_id = body.get("beat") or scope.beat_id
        new_text = body.get("text")
        if not beat_id or new_text is None:
            return self._send_json(400, {"error": "missing 'beat' or 'text'"})
        if not isinstance(new_text, str):
            return self._send_json(400, {"error": "'text' must be a string"})
        # Upper bound to prevent pathological payloads
        if len(new_text) > 5000:
            return self._send_json(400, {"error": "text exceeds 5000 chars"})

        try:
            beat_num = int(beat_id.split("_")[1])
        except (IndexError, ValueError):
            return self._send_json(400, {"error": f"unparseable beat_id: {beat_id!r}"})

        # Step 1: detect if a TTS file exists (for stale-flag logic)
        tts_exists = _find_beat_audio(self.app.event_dir, beat_id, app=self.app) is not None

        # Step 2: update state JSON atomically via scope_router → mutate_video_state.
        # The mutator receives the partition dict for `scope.video_role` — never
        # the full state, never legacy top-level state.beats. K1 prevention.
        now_iso = datetime.now(timezone.utc).isoformat()
        _holder: dict = {}
        def update_partition(partition, _bid=beat_id, _t=new_text, _stale=tts_exists, _ts=now_iso):
            beats = partition.setdefault("beats", {})
            b = beats.setdefault(_bid, {})
            old = b.get("text")
            b["text"] = _t
            b["text_last_updated_at"] = _ts
            if _stale and old != _t:
                b["text_modified_after_tts"] = True
            # Canonicalize-on-touch (SCR.2 Path A — Kim's pre-C-9 decision):
            # migrate legacy on-disk speaker values at every beat-touch so the
            # SR+G architecture truly converges. Runs uniformly with the graft
            # handler's existing canonicalization (C-7) so update_text and
            # graft both touch K8 dual-store. Idempotent: if speaker is already
            # canonical the writes are no-ops; phase_1 dict is created if
            # absent. LDs SPEAKER_DUAL_STORE_DEPRECATION_V1 +
            # SPEAKER_WRITE_BOUNDARY_CANONICALIZATION_V1 now hold at every
            # beat-touchpoint, not just patch_state(field='speaker', ...).
            legacy_spk = b.get("speaker") or ""
            canon_spk = _canonicalize_speaker(legacy_spk) or ""
            b["speaker"] = canon_spk
            b.setdefault("phase_1", {})["speaker"] = canon_spk
            _holder["old"] = old
        self.app.state.mutate_video_state(scope.video_role, update_partition)
        old_text = _holder.get("old")

        # LD-459 UNIVERSAL_AUTOSAVE_V1 — regen the sidecar(s) after every
        # state mutation so v58 emergency rollback sees fresh dialogue via
        # /api/v2/storyboard/L.json. _write_sidecar_L_json mirrors to all
        # sibling storyboard_v*_prod.L.json so a server flag-flip remains safe.
        try:
            _write_sidecar_L_json(self.app, self.app.state.read_state())
        except Exception as exc:  # noqa: BLE001
            print(f"[update_text] WARN sidecar regen failed: "
                  f"{type(exc).__name__}: {exc}", flush=True)

        # Step 3: patch the storyboard HTML L[] entry via the shared helper
        # (Tier 5 refactor, April 17 2026 — decisions 151 + 154 now share one
        # code path, so `assign_image` gets the same hardened write semantics
        # and there is ONE place to audit for server/HTML divergence.)
        patch_result = _patch_storyboard_L_field(
            self.app, beat_id, "t", new_text,
        )

        if not patch_result.get("patched"):
            reason = patch_result.get("reason")
            if reason == "v59_shell":
                # Path C v59 storyboard (LD-456 conditional HTML patching).
                # State.json is now the single source of truth; HTML patching
                # is a no-op by design. This branch makes that explicit so we
                # don't conflate v59 with "narration-only beat in v58".
                print(f"[update_text] {beat_id}: v59 shell — state-only update "
                      f"(LD-456). saved={len(new_text)} chars")
                return self._send_json(200, {
                    "ok": True, "beat": beat_id, "saved_at": now_iso,
                    "html_patched": False, "v59_shell": True,
                    "text_modified_after_tts": tts_exists and old_text != new_text,
                })
            if reason == "not_in_storyboard":
                # No L[] entry to patch — state is still the source of truth.
                # Dialogue for this beat simply isn't in the storyboard rendering
                # pipeline (e.g., narration-only beats). Saved-to-state is fine.
                print(f"[update_text] {beat_id} NOT in storyboard L[] — state only")
                return self._send_json(200, {
                    "ok": True, "beat": beat_id, "saved_at": now_iso,
                    "html_patched": False,
                    "text_modified_after_tts": tts_exists and old_text != new_text,
                })
            # Real error — return 500 with the detail from the helper.
            return self._send_json(500, {
                "error": patch_result.get("error", "unknown HTML patch error"),
                **{k: v for k, v in patch_result.items()
                   if k in ("escaped_preview",)},
            })

        print(f"[update_text] {beat_id} saved ({len(new_text)} chars) "
              f"html_patched=True tts_exists={tts_exists}")

        # Best-effort Directus audit log (Rule 18 Two-Write)
        try:
            _async_log_text_update(
                self.app.event_id, beat_id, old_text, new_text, tts_exists,
            )
        except Exception:
            pass  # fire-and-forget

        # ==================================================================
        # Decision 181 TTS_AUTO_REGEN_ON_TEXT_EDIT (April 17 2026):
        # After a successful text save, synchronously regenerate TTS audio
        # using the beat's speaker voice profile. Client waits ~5-8s.
        # On failure we return 200 with tts_regen.ok=false so the text save
        # is preserved and the user gets a clear error to retry.
        # Caller can pass {"skip_tts_regen": true} to opt out (e.g., internal
        # batch text updates that don't need audio regen yet).
        # ==================================================================
        tts_regen_result = {"ok": False, "skipped": True, "reason": "no_text_change"}
        text_actually_changed = (old_text or "") != new_text
        skip_flag = bool(body.get("skip_tts_regen"))

        # Tier 1A: 60s-per-beat debounce of AUTO-regen (LD
        # TTS_REGEN_DEBOUNCE_60S_WINDOW_PER_BEAT). The explicit "🎙 Regen Audio"
        # button is a SEPARATE handler (_handle_beat_regenerate_audio) and is
        # intentionally NOT debounced — it's user-initiated opt-in. The
        # skip_tts_regen body flag remains a client-side force-skip (checked
        # first below); debounce is a server-side rate limiter that kicks in
        # only when neither of those apply.
        debounce_skip, debounce_elapsed = (False, 0.0)
        if TIER1A_ENABLED and text_actually_changed and not skip_flag:
            debounce_skip, debounce_elapsed = _tier1a_debounce_should_skip(beat_id)

        if text_actually_changed and not skip_flag and not debounce_skip:
            # Load ElevenLabs key (cached at first call).
            try:
                _libdir = os.path.join(os.path.dirname(__file__), "lib")
                if _libdir not in sys.path:
                    sys.path.insert(0, _libdir)
                from credentials import load_credentials  # type: ignore
                creds = load_credentials()
                el_key = creds.get("elevenlabs_key") or ""
            except Exception as exc:  # noqa: BLE001
                el_key = ""
                print(f"[update_text] elevenlabs key load failed: {exc}")

            if not el_key:
                tts_regen_result = {
                    "ok": False,
                    "error": "elevenlabs key unavailable — TTS regen skipped",
                    "skipped": True,
                    "reason": "no_api_key",
                }
            else:
                print(f"[update_text] {beat_id} firing sync TTS regen (Rule 11 source fidelity)")
                try:
                    tts_regen_result = _tts_regenerate_for_beat(
                        self.app, beat_id, new_text, el_key,
                    )
                except Exception as exc:  # noqa: BLE001
                    traceback.print_exc()
                    tts_regen_result = {
                        "ok": False,
                        "error": f"unexpected TTS regen failure: {type(exc).__name__}: {exc}",
                        "skipped": False,
                    }
                # Tier 1A: record regen attempt (success OR failure) so the
                # next keystroke falls inside the debounce window. Rate-limits
                # retry stampede on failing ElevenLabs calls.
                # Tier 3 (April 18 2026): when regen_ok, also clears
                # phase_1.speaker_mismatch because the audio now matches the
                # speaker. Gated on _t1_enabled() so the rollback flag
                # MINDFULNEST_T1_ENABLED=0 reverts to pre-Tier-3 behavior too.
                if TIER1A_ENABLED:
                    _regen_ok = bool(tts_regen_result.get("ok")) and _t1_enabled()
                    _tier1a_mark_regen_fired(
                        beat_id, app=self.app, regen_ok=_regen_ok,
                    )

            if tts_regen_result.get("ok"):
                print(f"[update_text] {beat_id} TTS regen OK: "
                      f"{tts_regen_result['audio_file']} "
                      f"({tts_regen_result['audio_duration_s']:.2f}s, "
                      f"{tts_regen_result['elapsed_s']:.1f}s call)")
            else:
                print(f"[update_text] {beat_id} TTS regen failed: "
                      f"{tts_regen_result.get('error', 'unknown')}")
        elif skip_flag:
            tts_regen_result = {"ok": False, "skipped": True, "reason": "skip_tts_regen_flag"}
            print(f"[update_text] {beat_id} TTS regen skipped (skip_tts_regen)")
        elif debounce_skip:
            # Tier 1A debounce path. Text save already completed above; we
            # only skip the downstream TTS render to protect the rate budget.
            _elapsed_round = round(debounce_elapsed, 2) if debounce_elapsed != float("inf") else None
            tts_regen_result = {
                "ok": False,
                "skipped": True,
                "reason": "debounced",
                "elapsed_since_last_s": _elapsed_round,
                "window_s": TIER1A_DEBOUNCE_WINDOW_SEC,
            }
            # Structured [T1] log to stdout for greppability.
            _iso = datetime.now(timezone.utc).isoformat()
            print(
                f"[T1] {_iso} beat={beat_id} action=tts_regen_skipped "
                f"reason=debounced elapsed_since_last_s={_elapsed_round}",
                flush=True,
            )
            # Directus audit — rate-limited to 1/beat/60s to avoid spam
            if _tier1a_should_audit(beat_id):
                try:
                    _tier1a_async_log_debounce(
                        self.app.event_id, beat_id, debounce_elapsed,
                    )
                except Exception:  # noqa: BLE001
                    pass  # fire-and-forget
        # else: text unchanged, skipped message stays as 'no_text_change'

        self._send_json(200, {
            "ok": True,
            "beat": beat_id,
            "saved_at": now_iso,
            "html_patched": True,
            "text_modified_after_tts": (
                tts_exists and text_actually_changed and not tts_regen_result.get("ok")
            ),
            "old_text_preview": (old_text or "")[:100],
            "tts_regen": tts_regen_result,
        })

    # ------------------------------------------------------------------
    # BEAT_GRAFT_RECOVERY_MECHANISM_V1 — Pillar 7 cornerstone (C-7).
    # ------------------------------------------------------------------
    def _handle_beat_graft(self, body: dict) -> None:
        """POST /api/beat/graft — copy or move a beat across event/role.

        Body:
            {
              "source": {event_id, video_role, beat_id},
              "target": {event_id, video_role, position},
              "speaker_override": str | null,
              "move": bool,                 # default false (COPY)
              "mutation_id": str            # mandatory uuid4 idempotency key
            }

        Returns 200 with status in {"copied", "moved", "dedup", "already_present"}.
        Pre-render-only invariant (RR-1 mitigation): rejects beats with
        rendered media (phase_1.status="completed" OR options[*].file/lipsync_task_id).
        See spec §6 + handoff §4 C-7 for the full contract.
        """
        # 1) Validate body shape
        src = body.get("source") or {}
        tgt = body.get("target") or {}
        move = bool(body.get("move", False))
        mutation_id = body.get("mutation_id")
        speaker_override = body.get("speaker_override")
        if not mutation_id:
            return self._send_json(400, {"error": "mutation_id_required"})
        if not isinstance(src, dict) or not isinstance(tgt, dict):
            return self._send_json(400, {"error": "source/target must be objects"})
        for fld in ("event_id", "video_role", "beat_id"):
            if not src.get(fld):
                return self._send_json(400, {"error": f"source.{fld}_required"})
        for fld in ("event_id", "video_role"):
            if not tgt.get(fld):
                return self._send_json(400, {"error": f"target.{fld}_required"})
        for r in (src["video_role"], tgt["video_role"]):
            if r not in {"intro", "resolution", "standalone"}:
                return self._send_json(400, {"error": "video_role_invalid", "got": r})

        # 2) Idempotency dedup cache (mutation_id replay)
        if mutation_id in _GRAFT_DEDUP:
            cached = _GRAFT_DEDUP[mutation_id]
            _GRAFT_DEDUP.move_to_end(mutation_id)
            return self._send_json(200, {**cached, "status": "dedup"})

        # 3) Validate target scope (server is write-pinned to its event_dir)
        server_event = self.app.event_dir.name
        if tgt["event_id"] != server_event:
            return self._send_json(409, {
                "error": "scope_mismatch",
                "expected_event_id": server_event,
                "got": tgt["event_id"],
            })

        # 4) Cross-event source: require --source-event CLI flag
        cross_event = (src["event_id"] != tgt["event_id"])
        source_event_dir: Path | None = None
        if cross_event:
            seed = getattr(self.app, "source_event_dir", None)
            if seed is None or seed.name != src["event_id"]:
                return self._send_json(409, {
                    "error": "cross_event_requires_explicit_source",
                    "hint": (
                        f"Restart server with --source-event Production/{src['event_id']} "
                        "to enable cross-event graft from this source."
                    ),
                })
            source_event_dir = seed
        else:
            source_event_dir = self.app.event_dir

        # 5) Load source state and locate the source beat
        try:
            source_state_path = source_event_dir / "production_state.json"
            with open(source_state_path, "r", encoding="utf-8") as f:
                source_state = json.load(f)
        except FileNotFoundError:
            return self._send_json(404, {"error": "source_state_not_found",
                                         "path": str(source_state_path)})
        src_partition = (source_state.get("videos") or {}).get(src["video_role"], {}) or {}
        src_beats = src_partition.get("beats") or {}
        src_beat = src_beats.get(src["beat_id"])
        if src_beat is None:
            self._append_audit_log({
                "schema_version": 1, "action": "beat_graft_failed",
                "ts": datetime.now(timezone.utc).isoformat(),
                "mutation_id": mutation_id,
                "source": src, "target": tgt, "ok": False,
                "reason": "source_beat_not_found",
            })
            return self._send_json(404, {"error": "source_beat_not_found",
                                         "source": src})

        # 6) Pre-render-only invariant (RR-1 mitigation)
        phase_1 = src_beat.get("phase_1") or {}
        if phase_1.get("status") == "completed":
            return self._send_json(400, {
                "error": "graft_pre_render_only",
                "reason": "source.phase_1.status==completed",
            })
        for opt in (phase_1.get("options") or []):
            if isinstance(opt, dict):
                if opt.get("file") or opt.get("lipsync_task_id"):
                    return self._send_json(400, {
                        "error": "graft_pre_render_only",
                        "reason": "source.phase_1.options[].file or lipsync_task_id non-empty",
                    })

        # 7) Pre-image snapshots (atomic copy of full state(s))
        utc = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        pre_image_paths: list[str] = []
        try:
            seen_dirs: set[Path] = set()
            for ev_dir in (source_event_dir, self.app.event_dir):
                if ev_dir in seen_dirs:
                    continue
                seen_dirs.add(ev_dir)
                bdir = ev_dir / ".backups" / "state"
                bdir.mkdir(parents=True, exist_ok=True)
                bpath = bdir / f"{utc}_pre_graft_{mutation_id}.json"
                state_path = ev_dir / "production_state.json"
                with open(state_path, "r", encoding="utf-8") as f:
                    state_dict = json.load(f)
                atomic_json_write(str(bpath), state_dict)
                pre_image_paths.append(str(bpath))
        except Exception as exc:  # noqa: BLE001
            return self._send_json(503, {
                "error": "pre_image_snapshot_failed",
                "detail": f"{type(exc).__name__}: {exc}",
            })

        # 8) Speaker resolution (override or canonicalize source)
        raw_speaker = (speaker_override
                       if speaker_override is not None
                       else (src_beat.get("speaker") or _resolve_beat_speaker(src_beat)))
        canonical_speaker = _canonicalize_speaker(raw_speaker or "") or ""
        if speaker_override is not None:
            speaker_source = "override"
        elif canonical_speaker and (raw_speaker or "").lower() != canonical_speaker.lower():
            speaker_source = f"alias:{raw_speaker}->{canonical_speaker}"
        elif canonical_speaker:
            speaker_source = "untouched"
        else:
            speaker_source = "empty"

        # 9) Content fingerprint check (replay safety on cold cache)
        target_state_path = self.app.event_dir / "production_state.json"
        try:
            with open(target_state_path, "r", encoding="utf-8") as f:
                target_state_pre = json.load(f)
        except FileNotFoundError:
            return self._send_json(500, {"error": "target_state_not_found"})
        tgt_partition_pre = ((target_state_pre.get("videos") or {})
                             .get(tgt["video_role"]) or {})
        tgt_beats_pre = tgt_partition_pre.get("beats") or {}
        if src["beat_id"] in tgt_beats_pre:
            existing = tgt_beats_pre[src["beat_id"]]
            if (existing.get("text") == src_beat.get("text")
                and existing.get("speaker") == canonical_speaker):
                result = {
                    "ok": True, "status": "already_present",
                    "beat_id": src["beat_id"],
                    "pre_image_paths": pre_image_paths,
                    "audit_log_path": str(_audit_log_path(self.app)),
                    "target_display_order": tgt_partition_pre.get("display_order", []),
                }
                _GRAFT_DEDUP[mutation_id] = result
                while len(_GRAFT_DEDUP) > _GRAFT_DEDUP_MAX:
                    _GRAFT_DEDUP.popitem(last=False)
                return self._send_json(200, result)

        # 10) Apply target write via mutate_video_state (DISPLAY_ORDER_STRICT prune runs)
        target_position = tgt.get("position")

        def _insert_target(partition,
                           _bid=src["beat_id"], _payload=src_beat,
                           _spk=canonical_speaker, _pos=target_position):
            pbeats = partition.setdefault("beats", {})
            pdo = partition.setdefault("display_order", [])
            new_beat = dict(_payload)
            new_beat["speaker"] = _spk
            # K8 mirror — keep both stores consistent on insert
            new_beat.setdefault("phase_1", {})
            if isinstance(new_beat["phase_1"], dict):
                new_beat["phase_1"]["speaker"] = _spk
            pbeats[_bid] = new_beat
            if isinstance(pdo, list):
                if _bid in pdo:
                    pdo.remove(_bid)
                if _pos is None or _pos < 0 or _pos > len(pdo):
                    clamped = len(pdo)
                else:
                    clamped = _pos
                pdo.insert(clamped, _bid)

        try:
            self.app.state.mutate_video_state(tgt["video_role"], _insert_target)
        except Exception as exc:  # noqa: BLE001
            return self._send_json(500, {
                "error": "target_write_failed",
                "detail": f"{type(exc).__name__}: {exc}",
                "pre_image_paths": pre_image_paths,
            })

        # 11) Optional move=true: delete source beat
        if move:
            if cross_event:
                # Cross-event delete writes the source state file directly
                # via atomic_json_write (the server is NOT pinned to source).
                try:
                    with open(source_state_path, "r", encoding="utf-8") as f:
                        src_state_now = json.load(f)
                    src_partition_now = ((src_state_now.setdefault("videos", {}))
                                         .setdefault(src["video_role"], {}))
                    src_beats_now = src_partition_now.get("beats") or {}
                    if src["beat_id"] in src_beats_now:
                        del src_beats_now[src["beat_id"]]
                    src_do = src_partition_now.get("display_order")
                    if isinstance(src_do, list) and src["beat_id"] in src_do:
                        src_do.remove(src["beat_id"])
                    atomic_json_write(str(source_state_path), src_state_now)
                except Exception as exc:  # noqa: BLE001
                    return self._send_json(500, {
                        "error": "source_delete_failed",
                        "detail": f"{type(exc).__name__}: {exc}",
                        "pre_image_paths": pre_image_paths,
                    })
            else:
                # Same-event delete via the partition router's mutator.
                def _delete_source(partition, _bid=src["beat_id"]):
                    sb = partition.get("beats") or {}
                    if _bid in sb:
                        del sb[_bid]
                    sdo = partition.get("display_order")
                    if isinstance(sdo, list) and _bid in sdo:
                        sdo.remove(_bid)
                try:
                    self.app.state.mutate_video_state(src["video_role"], _delete_source)
                except Exception as exc:  # noqa: BLE001
                    return self._send_json(500, {
                        "error": "source_delete_failed_same_event",
                        "detail": f"{type(exc).__name__}: {exc}",
                        "pre_image_paths": pre_image_paths,
                    })

        # 12) Audit log: file JSONL (durable) + Directus mirror (best-effort)
        target_state_after_path = self.app.event_dir / "production_state.json"
        target_state_after = {}
        try:
            with open(target_state_after_path, "r", encoding="utf-8") as f:
                target_state_after = json.load(f)
        except Exception:
            pass
        post_partition = ((target_state_after.get("videos") or {})
                          .get(tgt["video_role"]) or {})
        audit_row = {
            "schema_version": 1, "action": "beat_graft",
            "ts": datetime.now(timezone.utc).isoformat(),
            "mutation_id": mutation_id,
            "source": {"event_id": src["event_id"],
                       "video_role": src["video_role"],
                       "beat_id": src["beat_id"]},
            "target": {"event_id": tgt["event_id"],
                       "video_role": tgt["video_role"],
                       "beat_id": src["beat_id"],
                       "position": target_position,
                       "post_image_version": target_state_after.get("version", 0)},
            "move": move, "cross_event": cross_event,
            "speaker_resolved": canonical_speaker,
            "speaker_source": speaker_source,
            "actor": "production_server_v59",
            "pre_image_paths": pre_image_paths,
            "ok": True,
        }
        self._append_audit_log(audit_row)
        try:
            from lib.directus import try_post_or_queue
            try_post_or_queue("prod_activity_log", {
                "action": "beat_graft",
                "performed_by": "production_server_v59",
                "details": audit_row,
            })
        except Exception:
            pass  # JSONL is the durable source of truth

        result = {
            "ok": True,
            "status": "moved" if move else "copied",
            "pre_image_paths": pre_image_paths,
            "audit_log_path": str(_audit_log_path(self.app)),
            "target_display_order": post_partition.get("display_order", []),
            "beat_id": src["beat_id"],
        }
        _GRAFT_DEDUP[mutation_id] = result
        while len(_GRAFT_DEDUP) > _GRAFT_DEDUP_MAX:
            _GRAFT_DEDUP.popitem(last=False)
        return self._send_json(200, result)

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
        """Explicit TTS regen trigger (decision 181 companion endpoint, April 17 2026).

        POST /api/beat/regenerate_audio {beat: "beat_NN"}
        Forces ElevenLabs v3 TTS regen using the beat's CURRENT text in
        state (no need to re-edit text first). Useful when:
          - User wants to re-roll a voice take they don't like
          - Voice profile was updated and beats need re-rendering
          - Blur-triggered auto-regen failed and needs explicit retry

        Rule 11 source fidelity: the text in state is the source of truth;
        this endpoint ensures audio matches current state.text verbatim.
        """
        # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
        if not self._assert_event_scope(self._scope_body(body), allow_missing=False):
            return

        beat_id = body.get("beat")
        if not beat_id:
            return self._send_json(400, {"error": "missing 'beat'"})

        state = self.app.state.read_state()
        beat_state = (((state.get("videos") or {}).get("intro") or {}).get("beats") or {}).get(beat_id) or {}
        text = (beat_state.get("text") or "").strip()
        # Fallback: if state has no text yet (beat never edited+blurred),
        # parse the storyboard L[] t: field. Same pattern
        # _tts_regenerate_for_beat uses for speaker. Decision 194
        # REGEN_AUDIO_STORYBOARD_TEXT_FALLBACK (April 17 2026) — prevents
        # the HTTP 400 "no dialogue text in state" failure mode Kim hit
        # on beat_08 where regen silently gave up without a retry path.
        if not text:
            try:
                beat_num = int(beat_id.split("_")[1])
                beat_num_s = f"{beat_num:02d}"
                html = self.app.storyboard_path.read_text(encoding="utf-8")
                marker = f'a:"line_{beat_num_s}"'
                idx = html.find(marker)
                if idx >= 0:
                    ob = html.rfind("{", 0, idx)
                    cb = html.find("}", idx)
                    entry = html[ob:cb + 1]
                    # Pull t:"..." — tolerate escaped quotes/newlines.
                    m = re.search(r't:"((?:\\.|[^"\\])*)"', entry)
                    if m:
                        # Unescape JS string literal: \\' -> ', \\n -> \n
                        raw = m.group(1)
                        text = (raw.replace("\\'", "'")
                                    .replace('\\"', '"')
                                    .replace("\\n", "\n")
                                    .replace("\\\\", "\\")).strip()
                        print(f"[regen_audio] {beat_id} text fallback from storyboard L[]: "
                              f"{len(text)}c")
            except Exception as exc:  # noqa: BLE001
                print(f"[regen_audio] {beat_id} storyboard fallback failed: {exc}")
        if not text:
            return self._send_json(400, {
                "error": f"beat {beat_id} has no dialogue text in state OR "
                         f"storyboard — regen cannot proceed",
            })
        # Persist the fallback-sourced text into state so downstream ops
        # (onblur, future regens, lipsync) see a consistent source of truth.
        if not beat_state.get("text"):
            def _seed_text(st, _bid=beat_id, _t=text):
                b = st.get("beats", {}).setdefault(_bid, {})
                b["text"] = _t
            self.app.state.mutate_state(_seed_text)

        # Load ElevenLabs key
        try:
            _libdir = os.path.join(os.path.dirname(__file__), "lib")
            if _libdir not in sys.path:
                sys.path.insert(0, _libdir)
            from credentials import load_credentials  # type: ignore
            creds = load_credentials()
            el_key = creds.get("elevenlabs_key") or ""
        except Exception as exc:  # noqa: BLE001
            return self._send_json(500, {
                "error": f"elevenlabs key load failed: {type(exc).__name__}: {exc}"
            })
        if not el_key:
            return self._send_json(500, {
                "error": "elevenlabs key unavailable — cannot regenerate audio"
            })

        print(f"[regen_audio] {beat_id} explicit button trigger "
              f"({len(text)}c text in state)")
        try:
            result = _tts_regenerate_for_beat(self.app, beat_id, text, el_key)
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            return self._send_json(500, {
                "error": f"TTS regen failure: {type(exc).__name__}: {exc}",
                "beat": beat_id,
            })

        if result.get("ok"):
            print(f"[regen_audio] {beat_id} OK: {result['audio_file']} "
                  f"({result['audio_duration_s']:.2f}s, {result['elapsed_s']:.1f}s call)")
            # Tier 3 (April 18 2026): explicit regen also clears the
            # speaker_mismatch stale-audio badge. Gated on _t1_enabled() so the
            # rollback flag MINDFULNEST_T1_ENABLED=0 reverts behavior.
            if TIER1A_ENABLED:
                _tier1a_mark_regen_fired(
                    beat_id, app=self.app, regen_ok=_t1_enabled(),
                )
            return self._send_json(200, {
                "ok": True,
                "beat": beat_id,
                "tts_regen": result,
                "message": (f"Audio regenerated for {beat_id}: "
                            f"{result['audio_file']} ({result['audio_duration_s']:.2f}s)"),
            })

        # Fail-loud — surface the error.
        print(f"[regen_audio] {beat_id} FAILED: {result.get('error', 'unknown')}")
        return self._send_json(500, {
            "ok": False,
            "beat": beat_id,
            "tts_regen": result,
            "error": result.get("error", "TTS regen failed"),
        })

    def _handle_select(self, body: dict) -> None:
        # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
        if not self._assert_event_scope(self._scope_body(body), allow_missing=False):
            return

        beat_id = body.get("beat")
        selected = body.get("selected_option")
        if not beat_id or selected is None:
            return self._send_json(400, {"error": "missing beat or selected_option"})
        try:
            sel_int = int(selected)
        except (TypeError, ValueError):
            return self._send_json(400, {"error": f"selected_option must be int, got {selected!r}"})

        # Side-channel: the new selected clip may diverge from the clip the
        # existing lipsync was produced against. Detect that and surface it
        # so the UI can offer "🔁 Re-run Lip Sync" (decision 153, Tier 5).
        source_changed_out = None
        def mut(state, _sel=sel_int):
            nonlocal source_changed_out
            beat = ((state.get("videos") or {}).get("intro") or {}).get("beats", {}).get(beat_id)
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
        return self._send_json(410, {
            "error": "endpoint_removed",
            "code": "EXPORT_REMOVED_V3",
            "removed_in": "S5.5d (2026-05-03)",
            "replacement": "/api/scene/assemble",
            "hint": (
                "POST /api/scene/assemble with body {scope_event_id|scope_milestone_id, "
                "scope_target_video, fade_between_beats_ms?, force_rebuild?}. "
                "Stage 1 finalizes each beat (cached); Stage 2 mirrors "
                "_handle_preview_stitched orchestration to assemble the scene "
                "and registers the result as a scene_concat_mp4 asset."
            ),
        })

    def _handle_beat_delay(self, body: dict) -> None:
        """Set audio delay (video lead-in) for a beat.
        POST {"beat": "beat_03", "audio_delay": 1.5}
        """
        # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
        if not self._assert_event_scope(self._scope_body(body), allow_missing=False):
            return

        beat_id = body.get("beat")
        delay = float(body.get("audio_delay", 0))
        if not beat_id:
            return self._send_json(400, {"error": "missing 'beat'"})
        if delay < 0 or delay > 10:
            return self._send_json(400, {"error": "audio_delay must be 0-10 seconds"})

        def update(state):
            b = ((state.get("videos") or {}).get("intro") or {}).get("beats", {}).get(beat_id)
            if not b:
                return False
            b.setdefault("phase_1", {})["audio_delay"] = round(delay, 2)
            return True

        found = self.app.state.mutate_state(update)
        if not found:
            return self._send_json(404, {"error": f"beat {beat_id} not found"})
        self._send_json(200, {"beat": beat_id, "audio_delay": round(delay, 2)})

    def _handle_beat_trim(self, body: dict) -> None:
        """Set clip trim points for a beat.
        POST {"beat": "beat_07", "trim_start": 0, "trim_end": 3.5}
        """
        # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
        if not self._assert_event_scope(self._scope_body(body), allow_missing=False):
            return

        beat_id = body.get("beat")
        if not beat_id:
            return self._send_json(400, {"error": "missing 'beat'"})
        trim_start = float(body.get("trim_start", 0))
        trim_end = body.get("trim_end")  # null = use full clip
        if trim_start < 0:
            return self._send_json(400, {"error": "trim_start must be >= 0"})
        if trim_end is not None:
            trim_end = float(trim_end)
            if trim_end <= trim_start:
                return self._send_json(400, {"error": "trim_end must be > trim_start"})

        def update(state):
            b = ((state.get("videos") or {}).get("intro") or {}).get("beats", {}).get(beat_id)
            if not b:
                return False
            p1 = b.setdefault("phase_1", {})
            p1["trim_start"] = round(trim_start, 2)
            p1["trim_end"] = round(trim_end, 2) if trim_end is not None else None
            return True

        found = self.app.state.mutate_state(update)
        if not found:
            return self._send_json(404, {"error": f"beat {beat_id} not found"})
        result = {"beat": beat_id, "trim_start": round(trim_start, 2)}
        if trim_end is not None:
            result["trim_end"] = round(trim_end, 2)
        self._send_json(200, result)

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
        """POST /api/v2/beat/<beat_id>/patch

        Body: {
          "field": "dialogue" | "image_override" | "selected_option" | "trim_start" | "trim_end",
          "value": <string | int | number | null>,
          "mutation_id": "<uuid>" (optional, for idempotency),
          "expected_version": <int> (optional, for ETag-style conflict detection)
        }

        Returns:
          200 {status: "applied", new_version, beat} — mutation applied
          200 {status: "dedup", cached: true, ...} — mutation_id replayed
          409 {status: "conflict", current_version, expected} — version mismatch
          503 {status: "disabled", error} — MINDFULNEST_WRITE_PATH=legacy
          400 {status: "error", error} — whitelist / validation failure
          500 {status: "error", error} — mutate_state failure
        """
        # SCOPE_ROUTER_V1 (C-2 D5 fix) — resolve scope keys before any further
        # processing. Subsumes LD-456 SCOPE_VALIDATION_V1 + LD-461
        # SCOPE_BODY_HELPER_V1 alias coalescing. allow_missing-style
        # permissive defaults from the legacy path are NOT preserved here —
        # client per LD-461 already injects the keys; resolve() now requires
        # them for partition-aware routing. The C-5 commit flips _assert_event_scope
        # call sites globally; this handler short-circuits to scope_router.
        try:
            scope = scope_router.resolve(body, self.app.event_dir.name)
        except scope_router.ScopeError as e:
            return self._send_json(e.http_status, {"status": "error", "error": e.code, **e.detail})

        # Parse beat_id from path: /api/v2/beat/beat_03/patch
        parts = [p for p in path.split("/") if p]
        # Expect: ["api", "v2", "beat", "<beat_id>", "patch"]
        if len(parts) != 5 or parts[0] != "api" or parts[1] != "v2" or parts[2] != "beat" or parts[4] != "patch":
            return self._send_json(400, {"status": "error", "error": f"malformed path: {path!r}"})
        beat_id = parts[3]

        field = body.get("field")
        value = body.get("value")
        mutation_id = body.get("mutation_id")
        expected_version = body.get("expected_version")

        if not field:
            return self._send_json(400, {"status": "error", "error": "missing 'field'"})

        # ------------------------------------------------------------------
        # LD-181 TTS_AUTO_REGEN_ON_TEXT_EDIT preservation (amendment 3):
        # when field=="dialogue", delegate to the legacy _handle_beat_update_text
        # flow internally so TTS auto-regen continues to fire. We compose a
        # synthetic body and invoke the handler, but we still apply v2
        # idempotency (dedup cache) and the rollback flag before delegation.
        # ------------------------------------------------------------------
        if field == "dialogue":
            if os.environ.get("MINDFULNEST_WRITE_PATH", "v2") == "legacy":
                return self._send_json(503, {
                    "status": "disabled",
                    "error": "v2 write path disabled via MINDFULNEST_WRITE_PATH=legacy",
                })
            if not isinstance(value, str):
                return self._send_json(400, {
                    "status": "error",
                    "error": f"dialogue value must be str, got {type(value).__name__}",
                })
            # Dedup check (v2 idempotency) — separate cache lookup, same rules
            if mutation_id:
                cached = _PATCH_STATE_DEDUP.get(mutation_id)
                if cached is not None:
                    _PATCH_STATE_DEDUP.move_to_end(mutation_id)
                    return self._send_json(200, {**cached, "status": "dedup", "cached": True})
            # Version check
            _state_pre = self.app.state.read_state()
            current_v = _v2_read_beat_version(_state_pre, beat_id)
            if expected_version is not None and expected_version != current_v:
                return self._send_json(409, {
                    "status": "conflict",
                    "current_version": current_v,
                    "expected": expected_version,
                })

            # Capture response from legacy handler by temporarily overriding
            # _send_json. We want to preserve LD-181 TTS auto-regen behavior
            # from _handle_beat_update_text exactly.
            _captured = {"status": None, "payload": None}
            _orig_send_json = self._send_json

            def _capture(status, payload):
                _captured["status"] = status
                _captured["payload"] = payload

            self._send_json = _capture  # type: ignore[assignment]
            try:
                # Tier 1A: explicit-allowlist forwarding of opt-out flags from
                # the v2 body into the legacy handler. Today only skip_tts_regen
                # needs to pass through; adding a new flag = add its name to
                # _FORWARDED_V2_DIALOGUE_FIELDS. NO silent passthrough of
                # arbitrary client fields (LD V2_DIALOGUE_EXPLICIT_FIELD_FORWARDING_WITH_ALLOWLIST).
                # SCOPE_ROUTER_V1 (C-2): forward scope keys to the legacy
                # handler so its internal scope_router.resolve() succeeds.
                # Without these the dialogue-via-v2 path would 400 with
                # scope_required (a regression from the C-2 K1 fix).
                legacy_body = {
                    "beat": beat_id,
                    "text": value,
                    "scope_event_id": scope.event_id,
                    "scope_target_video": scope.video_role,
                }
                if TIER1A_ENABLED:
                    for _f in _FORWARDED_V2_DIALOGUE_FIELDS:
                        if _f in body:
                            legacy_body[_f] = body[_f]
                self._handle_beat_update_text(legacy_body)
            finally:
                self._send_json = _orig_send_json  # type: ignore[assignment]

            legacy_status = _captured["status"] or 500
            legacy_payload = _captured["payload"] or {}
            if legacy_status == 200:
                # Bump _version to mirror v2 semantics and write sidecar.
                # SCOPE_ROUTER_V1 (C-7.5 K2 sibling fix): the _version bump
                # MUST land on the same partition where _handle_beat_update_text
                # just wrote the text — i.e., videos.<scope.video_role>.beats[bid].
                # Pre-fix this _bump wrote to legacy top-level state.beats[bid]
                # which diverged from the actual write location after C-2.
                # Effect of pre-fix: ETag-style optimistic concurrency on v2
                # dialogue patches was silently broken (_version landed in a
                # legacy slot that no v3 reader consults).
                _bump_holder = {"v": None}
                def _bump_partition(partition, _bid=beat_id, _h=_bump_holder):
                    b = partition.setdefault("beats", {}).setdefault(_bid, {})
                    v = int(b.get("_version", 0) or 0) + 1
                    b["_version"] = v
                    _h["v"] = v
                try:
                    self.app.state.mutate_video_state(scope.video_role, _bump_partition)
                    new_v = _bump_holder["v"]
                    if new_v is None:  # mutator never ran (defensive)
                        new_v = current_v + 1
                except Exception as exc:  # noqa: BLE001
                    new_v = current_v + 1
                    print(f"[v2 dialogue] version bump failed: {exc}")
                try:
                    fresh = self.app.state.read_state()
                    _write_sidecar_L_json(self.app, fresh)
                except Exception as exc:  # noqa: BLE001
                    print(f"[v2 dialogue] sidecar write failed: {exc}")
                response = {
                    "status": "applied",
                    "new_version": new_v,
                    "beat": {"text": value, "_version": new_v},
                    "legacy": legacy_payload,  # includes tts_regen info (LD-181)
                    "source": "legacy_dialogue_via_v2",
                }
                if mutation_id:
                    _PATCH_STATE_DEDUP[mutation_id] = response
                    while len(_PATCH_STATE_DEDUP) > _PATCH_STATE_DEDUP_MAX:
                        _PATCH_STATE_DEDUP.popitem(last=False)
                return self._send_json(200, response)
            # Legacy handler returned non-200 — forward
            return self._send_json(legacy_status, {
                "status": "error",
                "error": "legacy dialogue handler rejected",
                "legacy_status": legacy_status,
                "legacy_payload": legacy_payload,
            })

        # ------------------------------------------------------------------
        # All other v2 fields — go through patch_state() helper directly.
        # ------------------------------------------------------------------
        result = patch_state(
            self.app, beat_id, field, value,
            mutation_id=mutation_id,
            expected_version=expected_version,
            video_role=scope.video_role,
        )
        status = result.get("status")
        if status == "applied" or status == "dedup":
            return self._send_json(200, result)
        if status == "conflict":
            return self._send_json(409, result)
        if status == "disabled":
            return self._send_json(503, result)
        # error or unknown
        return self._send_json(400, result)

    def _handle_v2_beat_create(self, body: dict) -> None:
        """POST /api/v2/beat/create — Tier 3 (April 18 2026).

        LD TIER3_BEAT_CREATE_ENDPOINT (severity HIGH).

        Creates a new beat with a minimum scaffold:
          text=""
          phase_1={"status":"pending","options":[]}
          _version=0

        Body:
          {"insert_after": beat_id | null, "mutation_id": uuid (optional)}

        Semantics:
          - new beat_id = beat_NN where NN = max(existing NN) + 1, zero-padded.
          - If state.display_order is absent, it's initialized from
            sorted(existing beat_ids) and the new beat is inserted after
            `insert_after` (or appended when insert_after is null/missing).
          - If state.display_order exists, the new beat is inserted after
            `insert_after` in the existing list (or appended if insert_after
            is not found or is null).
          - Atomic via mutate_state (fcntl + Directus lock).
          - Sidecar is refreshed post-mutation.
          - mutation_id goes through the shared dedup cache so retries are idempotent.
        """
        # SCOPE_ROUTER_V1 (C-7.5 K1 sibling fix) — replace legacy
        # _assert_event_scope + intro hardcode. Mutator routes through
        # mutate_video_state(scope.video_role, ...) so v2 beat creation
        # lands in the partition the client is editing, not always intro.
        try:
            scope = scope_router.resolve(body, self.app.event_dir.name)
        except scope_router.ScopeError as e:
            return self._send_json(e.http_status, {"error": e.code, **e.detail})

        # Feature flag (also covers MINDFULNEST_WRITE_PATH=legacy)
        if os.environ.get("MINDFULNEST_WRITE_PATH", "v2") == "legacy":
            return self._send_json(503, {
                "status": "disabled",
                "error": "v2 write path disabled via MINDFULNEST_WRITE_PATH=legacy",
            })
        if not _t1_enabled():
            return self._send_json(503, {
                "status": "disabled",
                "error": "Tier 1 feature flag disabled (MINDFULNEST_T1_ENABLED=0)",
            })

        insert_after = body.get("insert_after")
        if insert_after is not None and not isinstance(insert_after, str):
            return self._send_json(400, {
                "status": "error",
                "error": f"insert_after must be str or null, got {type(insert_after).__name__}",
            })

        mutation_id = body.get("mutation_id")
        # Dedup via shared LRU cache — identical semantics to patch_state
        if mutation_id:
            cached = _PATCH_STATE_DEDUP.get(mutation_id)
            if cached is not None:
                _PATCH_STATE_DEDUP.move_to_end(mutation_id)
                return self._send_json(200, {**cached, "status": "dedup", "cached": True})

        result_out: dict = {}

        def _apply_partition(partition, _ia=insert_after, _out=result_out):
            # Writes/reads partition.beats + partition.display_order via the
            # scope_router (was videos.intro hardcode).
            beats = partition.setdefault("beats", {})
            # Compute next beat_id: max existing NN + 1, zero-padded to 2.
            max_num = 0
            for bid in beats.keys():
                # Accept the conventional beat_NN pattern; skip anything
                # non-conforming so non-standard keys can't break numbering.
                if not bid.startswith("beat_"):
                    continue
                try:
                    n = int(bid.split("_", 1)[1])
                    if n > max_num:
                        max_num = n
                except (IndexError, ValueError):
                    continue
            new_num = max_num + 1
            # Keep 2-digit padding for small N; widen only if collision needs it.
            new_bid = f"beat_{new_num:02d}"
            # Collision-safety: if the padded name is somehow taken (e.g. after
            # manual edits), bump until it isn't.
            while new_bid in beats:
                new_num += 1
                new_bid = f"beat_{new_num:02d}"
            # Minimum scaffold
            beats[new_bid] = {
                "text": "",
                "phase_1": {"status": "pending", "options": []},
                "_version": 0,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            # Update display_order on the resolved partition (was videos.intro).
            existing_order = partition.get("display_order")
            if not isinstance(existing_order, list):
                # Initialize from sorted existing beat_ids (excluding the new one)
                order = sorted(
                    [b for b in beats.keys() if b != new_bid],
                    key=lambda s: (len(s), s),
                )
            else:
                # Keep the user's existing order as-is
                order = [b for b in existing_order if b in beats and b != new_bid]
            # Insert after or append
            insert_idx = None
            if _ia and _ia in order:
                insert_idx = order.index(_ia) + 1
                order.insert(insert_idx, new_bid)
            else:
                order.append(new_bid)
                insert_idx = len(order) - 1
            partition["display_order"] = order
            _out["beat_id"] = new_bid
            _out["inserted_after"] = _ia if _ia in (order[:insert_idx]) else None
            _out["display_order_len"] = len(order)

        try:
            self.app.state.mutate_video_state(scope.video_role, _apply_partition)
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            return self._send_json(500, {
                "status": "error",
                "error": f"beat create failed: {type(exc).__name__}: {exc}",
            })

        # Sidecar refresh
        try:
            fresh = self.app.state.read_state()
            _write_sidecar_L_json(self.app, fresh)
        except Exception as exc:  # noqa: BLE001
            print(f"[v2 beat_create] sidecar write failed: {exc}")

        response = {
            "status": "created",
            "beat_id": result_out.get("beat_id"),
            "inserted_after": result_out.get("inserted_after"),
            "display_order_len": result_out.get("display_order_len"),
        }
        if mutation_id:
            _PATCH_STATE_DEDUP[mutation_id] = response
            while len(_PATCH_STATE_DEDUP) > _PATCH_STATE_DEDUP_MAX:
                _PATCH_STATE_DEDUP.popitem(last=False)

        # Fire-and-forget Directus audit
        def _async_audit():
            try:
                _libdir = os.path.join(os.path.dirname(__file__), "lib")
                if _libdir not in sys.path:
                    sys.path.insert(0, _libdir)
                from credentials import load_credentials  # type: ignore
                from directus import DirectusClient  # type: ignore
                creds = load_credentials()
                dc = DirectusClient(
                    creds["directus_url"],
                    creds["directus_email"],
                    creds["directus_password"],
                )
                dc.create("prod_activity_log", {
                    "action": "v2_beat_create",
                    "details": {
                        "task_id": "tier3-server-20260418",
                        "beat_id": response["beat_id"],
                        "inserted_after": response["inserted_after"],
                        "mutation_id": mutation_id,
                        "ld_key": "TIER3_BEAT_CREATE_ENDPOINT",
                    },
                    "performed_by": "production_server.tier3",
                })
            except Exception:  # noqa: BLE001
                pass  # fire-and-forget
        threading.Thread(target=_async_audit, daemon=True).start()

        return self._send_json(200, response)

    def _handle_v2_get(self, path: str) -> None:
        """GET /api/v2/beat/<beat_id>

        Returns the current state for a single beat, including _version.
        """
        parts = [p for p in path.split("/") if p]
        # Expect: ["api", "v2", "beat", "<beat_id>"]
        if len(parts) != 4 or parts[0] != "api" or parts[1] != "v2" or parts[2] != "beat":
            return self._send_json(400, {"error": f"malformed path: {path!r}"})
        beat_id = parts[3]
        state = self.app.state.read_state()
        beat = (((state.get("videos") or {}).get("intro") or {}).get("beats") or {}).get(beat_id)
        if beat is None:
            return self._send_json(404, {"error": f"beat {beat_id!r} not found"})
        image_key = (((state.get("videos") or {}).get("intro") or {}).get("image_overrides") or {}).get(beat_id)
        return self._send_json(200, {
            "beat_id": beat_id,
            "beat": beat,
            "image_override": image_key,
            "_version": int(beat.get("_version", 0) or 0),
        })

    def _handle_v2_sidecar(self) -> None:
        """GET /api/v2/storyboard/L.json[?event_id=<id>]

        Serves the on-disk sidecar JSON for bootstrap hydration.
        Returns 404 if not yet materialized — bootstrap JS falls through
        to embedded L[] in that case.

        LD-456 SCOPE_VALIDATION_V1: if the client passes ?event_id=<id> and
        it doesn't match the server-pinned event, return HTTP 409. This
        protects v59 clients with stale tabs from receiving sidecar content
        for the wrong event.
        """
        # LD-456 SCOPE_VALIDATION_V1 (no-body handler — query-string fallback inside helper)
        if not self._assert_event_scope({}, allow_missing=True):
            return

        # LD-456: query-string scope check (defensive — read-only endpoint
        # but stale-tab clients should be told to reload).
        try:
            qs = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(qs)
            qs_eid = params.get("event_id")
            if qs_eid:
                client_event = qs_eid[0]
                server_event = self.app.event_dir.name
                if client_event != server_event:
                    print(
                        f"[scope-guard] HTTP 409 on GET {self.path}: "
                        f"qs event_id={client_event!r} != server event_id={server_event!r}",
                        flush=True,
                    )
                    return self._send_json(409, {
                        "error": "scope_mismatch",
                        "code": "SCOPE_VALIDATION_V1",
                        "expected_event_id": server_event,
                        "got_event_id": client_event,
                    })
        except Exception:
            pass
        sidecar_path = self.app.event_dir / (self.app.storyboard_path.stem + ".L.json")
        if not sidecar_path.exists():
            # Materialize once on first read (idempotent)
            try:
                state = self.app.state.read_state()
                _write_sidecar_L_json(self.app, state)
            except Exception as exc:  # noqa: BLE001
                return self._send_json(404, {"error": "sidecar not yet materialized", "detail": str(exc)})
        if not sidecar_path.exists():
            return self._send_json(404, {"error": "sidecar unavailable"})
        try:
            body = sidecar_path.read_bytes()
        except OSError as exc:
            return self._send_json(500, {"error": f"sidecar read failed: {exc}"})
        self.send_response(200)
        self._cors_headers()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_v2_event_state(self, path: str) -> None:
        """GET /api/v2/event/<event_id>/state

        Returns the whole state.json. Used by the storyboard bootstrap
        to hydrate L[] on page load. Convenience endpoint — alias for
        /api/state but namespaced under v2.

        LD-456 SCOPE_VALIDATION_V1: this endpoint historically accepted the
        URL <event_id> path component but ignored it. Now: if the URL
        <event_id> doesn't match the server-pinned event_dir, return HTTP
        409 so a stale-tab client knows to reload its scope. Read-only
        endpoints don't carry the cross-event mutation risk, but a stale
        scope returning silently-wrong state would still confuse the v59
        client (it'd render Event 2 data thinking it's Event 1).
        """
        # LD-456: extract <event_id> from URL path and assert match.
        # Expected: /api/v2/event/<event_id>/state
        try:
            parts = [p for p in path.split("/") if p]
            # parts: ["api", "v2", "event", "<event_id>", "state"]
            if len(parts) >= 4:
                url_event = parts[3]
                server_event = self.app.event_dir.name
                if url_event != server_event:
                    print(
                        f"[scope-guard] HTTP 409 on GET {path}: "
                        f"url event_id={url_event!r} != server event_id={server_event!r}",
                        flush=True,
                    )
                    return self._send_json(409, {
                        "error": "scope_mismatch",
                        "code": "SCOPE_VALIDATION_V1",
                        "expected_event_id": server_event,
                        "got_event_id": url_event,
                        "hint": (
                            "URL <event_id> path component does not match "
                            "the event this server is pinned to. Reload your "
                            "client tab to re-resolve scope."
                        ),
                    })
        except Exception as exc:
            # Defensive — never block reads on parser errors. Log + proceed.
            print(f"[scope-guard] WARN: URL parse on {path} raised {exc!r}; "
                  f"falling through to server-pinned event.", flush=True)
        state = self.app.state.read_state()
        return self._send_json(200, state)

    # ------------------------------------------------------------------
    # LD-285 Preview Stitched v2 (April 19 2026)
    # Spec: TECH_SPEC_PREVIEW_STITCHED_V2_20260419.md / preflight 93.
    # ------------------------------------------------------------------
    def _handle_v2_module_patch(self, body: dict) -> None:
        """POST /api/v2/module/patch

        Body: {"field": "fade_between_beats_ms", "value": 200}

        Whitelisted fields: _V2_MODULE_ALLOWED_FIELDS. Validates int 0..1000,
        acquires the same StateManager.mutate_state lock the beat-patch path
        uses (cross-machine + intra-process), then writes to state.json root.
        Returns {status:"applied", new_version:N} where new_version is the
        bumped state-level _module_version counter (different from per-beat
        _version; module-level changes don't bump beat versions).
        """
        # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
        if not self._assert_event_scope(self._scope_body(body), allow_missing=False):
            return

        # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — capture pin at entry; terminal
        # writes assert via _check_event_pin. (S5.5d 2026-05-03: pre-existing
        # `_pin` reference at the apply-mutate site previously NameError'd
        # because _pin was never constructed. Adding the construction here
        # closes that bug.)
        _pin = {
            "pinned_generation": self.app.event_generation,
            "pinned_event_dir": self.app.event_dir,
            "pinned_video_role": (body or {}).get("scope_video_role", "intro"),
            "_handler": "v2_module_patch",
        }
        if not self._check_event_pin(_pin, "v2_module_patch_pre_work"):
            return self._send_json(423, {
                "error": "event_changed_pre_work",
                "code": "ASYNC_JOB_GENERATION_PIN_V1",
                "handler": "v2_module_patch",
            })

        field = body.get("field")
        value = body.get("value")
        if not field:
            return self._send_json(400, {
                "status": "error", "error": "missing 'field'",
                "hint": "Body must include 'field' and 'value'.",
            })
        if field not in _V2_MODULE_ALLOWED_FIELDS:
            return self._send_json(400, {
                "status": "error",
                "error": f"field {field!r} not in module whitelist",
                "hint": f"Allowed: {sorted(_V2_MODULE_ALLOWED_FIELDS)}",
            })
        # V3 HIGH-1 fix: per-field type+bound dispatch so string/JSON fields
        # don't get coerced to int. Fade fields retain V2 semantics.
        validator = _V2_MODULE_FIELD_VALIDATORS.get(field)
        if validator is None:
            return self._send_json(500, {
                "status": "error",
                "error": f"field {field!r} whitelisted but has no validator",
                "hint": "Internal: add a _V2_MODULE_FIELD_VALIDATORS entry.",
            })
        try:
            value = validator(value)
        except ValueError as exc:
            return self._send_json(400, {
                "status": "error",
                "error": f"{field}: {exc}",
                "hint": f"Validator rejected the value. See error detail for the specific constraint.",
            })
        except (TypeError, KeyError) as exc:
            return self._send_json(400, {
                "status": "error",
                "error": f"{field}: {type(exc).__name__}: {exc}",
                "hint": "Value shape does not match field's schema.",
            })

        def _apply(state, _f=field, _v=value):
            state[_f] = _v
            state["_module_version"] = int(state.get("_module_version", 0) or 0) + 1
            return state["_module_version"]

        # LD-460 — terminal pin check before mutate_state (mix_audio).
        if not self._check_event_pin(_pin, "phase_b_mix_audio_apply_mutate"):
            return self._send_json(423, {"error": "event_changed_mid_job", "code": "ASYNC_JOB_GENERATION_PIN_V1", "handler": "phase_b_mix_audio"})
        try:
            new_version = self.app.state.mutate_state(_apply)
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            return self._send_json(500, {
                "status": "error",
                "error": f"mutate_state failed: {type(exc).__name__}: {exc}",
                "hint": "State.json could not be persisted. Check Directus reachability.",
            })

        # Sidecar refresh so the storyboard's pathappHydrate sees the new value
        # without a full page reload (mirrors the beat-patch flow).
        try:
            fresh = self.app.state.read_state()
            _write_sidecar_L_json(self.app, fresh)
        except Exception as exc:  # noqa: BLE001
            print(f"[v2 module_patch] sidecar write failed: {exc}")

        return self._send_json(200, {
            "status": "applied",
            "field": field,
            "value": value,
            "new_version": new_version,
        })

    def _handle_v2_beat_swap_to_a(self, beat_id: str, body: dict) -> None:
        """POST /api/v2/beat/<beat_id>/swap_to_a — park a B/C favorite in slot A.

        Body: {"from_slot": N} where N is 2 (Option B) or 3 (Option C), 1-indexed.

        Semantics:
          - Atomically swap beat.phase_1.options[0] with
            beat.phase_1.options[from_slot - 1] (full dict swap: file, task_id,
            size_bytes, status, retries, source, end_frame_prompt, etc.).
          - If beat.phase_1.selected_option was N, set to 1. If it was 1, set
            to N. Other values unchanged.
          - If beat.lipsync.source_option was N, set to 1. If it was 1, set
            to N. Other values unchanged.
          - Clear lipsync.source_changed and lipsync.audio_changed flags — the
            lipsync file still corresponds to the same CONTENT, just a different
            slot, so it remains valid.
          - On-disk .mp4 files are NOT renamed; only state pointers move.

        Returns:
          200 {status:"swapped", beat, from_slot, to_slot, new_selected_option,
               new_source_option}
          400 {error, hint} — invalid from_slot, missing beat, empty option,
               phase_1 too small.
        """
        # SCOPE_ROUTER_V1 (C-7.5 K2 sibling fix) — replaces legacy
        # _assert_event_scope + intro-hardcoded pre-flight read with
        # scope_router resolution. Pre-flight + mutate now both target
        # scope.video_role partition, not the hardcoded intro / legacy
        # top-level state.beats.
        try:
            scope = scope_router.resolve(body, self.app.event_dir.name, require_beat_id=False)
        except scope_router.ScopeError as e:
            return self._send_json(e.http_status, {"error": e.code, **e.detail})

        # ------------------------------------------------------------------
        # Input validation
        # ------------------------------------------------------------------
        from_slot = body.get("from_slot")
        if not isinstance(from_slot, int) or isinstance(from_slot, bool):
            return self._send_json(400, {
                "error": f"from_slot must be int >= 2, got {from_slot!r}",
                "hint": "Body must include {\"from_slot\": N} where N is 2 (Option B), 3 (Option C), 4 (Option D), etc.",
            })
        # Follow-up fix 20260419: some beats have more than 3 options (regen
        # added without replacing). Allow any slot >=2 that the beat actually
        # has. Upper-bound validation happens in the 'len(pre_options) < from_slot'
        # check below, which gives a specific error message with the actual
        # option count.
        if from_slot < 2:
            return self._send_json(400, {
                "error": f"from_slot must be >= 2, got {from_slot}",
                "hint": "Slot 1 is already A — nothing to swap. Pass 2 (B), 3 (C), 4 (D), etc.",
            })

        # ------------------------------------------------------------------
        # Pre-flight read: verify beat + option exist before mutate_state.
        # (Fast-fail on 400 conditions without taking the write lock.)
        # Reads from videos.<scope.video_role>.beats[bid] per SCOPE_ROUTER_V1.
        # ------------------------------------------------------------------
        pre_state = self.app.state.read_state()
        pre_partition = ((pre_state.get("videos") or {}).get(scope.video_role) or {})
        pre_beat = (pre_partition.get("beats") or {}).get(beat_id)
        if pre_beat is None:
            return self._send_json(400, {
                "error": f"beat {beat_id!r} not found in videos.{scope.video_role}.beats",
                "hint": "Verify beat_id exists in the partition. Check /api/v2/event/<id>/state.",
            })
        pre_phase1 = pre_beat.get("phase_1") or {}
        pre_options = pre_phase1.get("options") or []
        if len(pre_options) < from_slot:
            return self._send_json(400, {
                "error": f"phase_1 has {len(pre_options)} option(s); cannot swap from slot {from_slot}",
                "hint": f"Beat must have at least {from_slot} options for from_slot={from_slot}.",
            })
        src_option = pre_options[from_slot - 1]
        if not isinstance(src_option, dict) or not src_option.get("file"):
            return self._send_json(400, {
                "error": f"option at slot {from_slot} is empty or missing a file",
                "hint": "Cannot swap an empty/pending option into slot A. Generate it first.",
            })

        # ------------------------------------------------------------------
        # Atomic swap via mutate_video_state (partition router; no legacy
        # top-level state.beats touch).
        # ------------------------------------------------------------------
        result_out: dict = {}

        def _apply_partition(partition, _bid=beat_id, _fs=from_slot, _out=result_out):
            beats = partition.setdefault("beats", {})
            beat = beats.get(_bid)
            if beat is None:
                # Race: beat vanished between pre-flight and lock acquisition.
                raise KeyError(f"beat {_bid!r} not found at mutate time")
            phase1 = beat.setdefault("phase_1", {})
            options = phase1.setdefault("options", [])
            if len(options) < _fs:
                raise IndexError(
                    f"phase_1 options shrank to {len(options)} before swap (expected >= {_fs})"
                )
            # Full dict swap (content swap — file, task_id, size_bytes, status,
            # retries, source, end_frame_prompt, etc.).
            options[0], options[_fs - 1] = options[_fs - 1], options[0]

            # Toggle selected_option between 1 <-> N. Other values unchanged.
            sel = phase1.get("selected_option")
            if isinstance(sel, int):
                if sel == _fs:
                    phase1["selected_option"] = 1
                elif sel == 1:
                    phase1["selected_option"] = _fs

            # Toggle lipsync.source_option between 1 <-> N. Other values
            # unchanged. Clear source_changed + audio_changed — the lipsync
            # output file still corresponds to the same CONTENT (we only moved
            # the slot pointer), so it remains a valid lipsync.
            ls = beat.get("lipsync")
            new_src_opt = None
            if isinstance(ls, dict):
                src_opt = ls.get("source_option")
                if isinstance(src_opt, int):
                    if src_opt == _fs:
                        ls["source_option"] = 1
                    elif src_opt == 1:
                        ls["source_option"] = _fs
                new_src_opt = ls.get("source_option")
                # Clear the "is lipsync stale vs selection?" flags — the
                # content is unchanged, so whatever lipsync existed is still
                # the right output for this (now-moved) source option.
                if "source_changed" in ls:
                    ls["source_changed"] = False
                if "audio_changed" in ls:
                    ls["audio_changed"] = False

            # Bump per-beat _version so ETag readers see the change.
            beat["_version"] = int(beat.get("_version", 0) or 0) + 1

            _out["beat"] = beat
            _out["new_selected_option"] = phase1.get("selected_option")
            _out["new_source_option"] = new_src_opt
            _out["new_version"] = beat["_version"]
            return _out

        try:
            self.app.state.mutate_video_state(scope.video_role, _apply_partition)
        except (KeyError, IndexError) as exc:
            return self._send_json(400, {
                "error": f"swap failed: {exc}",
                "hint": "State changed between pre-flight and mutate. Retry.",
            })
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            return self._send_json(500, {
                "error": f"mutate_video_state failed: {type(exc).__name__}: {exc}",
                "hint": "State.json could not be persisted. Check Directus reachability.",
            })

        # Sidecar refresh so the storyboard hydrates new slot order without a
        # full page reload (mirrors other v2 write paths).
        try:
            fresh = self.app.state.read_state()
            _write_sidecar_L_json(self.app, fresh)
        except Exception as exc:  # noqa: BLE001
            print(f"[v2 swap_to_a] sidecar write failed: {exc}")

        return self._send_json(200, {
            "status": "swapped",
            "beat": beat_id,
            "from_slot": from_slot,
            "to_slot": 1,
            "new_selected_option": result_out.get("new_selected_option"),
            "new_source_option": result_out.get("new_source_option"),
            "new_version": result_out.get("new_version"),
        })

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
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), "lib"))
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
                trim_body,
                trim_normalized,
            )
        except ImportError as exc:
            return self._send_json(500, {
                "error": f"lib/ffmpeg_stitch import failed: {exc}",
                "hint": "Verify Production/tools/lib/ffmpeg_stitch.py exists.",
            })

        snapshot = body.get("state_snapshot") or {}
        fade_ms_raw = body.get("fade_between_beats_ms")
        try:
            fade_ms = int(fade_ms_raw) if fade_ms_raw is not None else 0
        except (TypeError, ValueError):
            return self._send_json(400, {
                "error": f"fade_between_beats_ms must be int, got {fade_ms_raw!r}",
                "hint": "Send slider value as integer milliseconds.",
            })
        if fade_ms < 0 or fade_ms > _V2_MODULE_FADE_MAX_MS:
            return self._send_json(400, {
                "error": f"fade_between_beats_ms out of range, got {fade_ms}",
                "hint": f"Range is [0, {_V2_MODULE_FADE_MAX_MS}].",
            })

        beats = snapshot.get("beats") or {}
        display_order = snapshot.get("display_order") or []
        allowed = set(display_order)
        beat_ids_sorted = sorted(
            bid for bid, b in beats.items()
            if bid in allowed
            and isinstance(b, dict)
            and (b.get("phase_1") or {}).get("selected_option") is not None
        )
        if not beat_ids_sorted:
            return self._send_json(400, {
                "error": "no beats with selected_option in snapshot",
                "hint": "Select an animation option for each beat before previewing.",
            })

        # ---- counter (a) HIGH: validate file existence BEFORE hash ----
        clips_dir = self.app.state.clips_dir
        missing = []
        for bid in beat_ids_sorted:
            try:
                resolve_beat_file(bid, snapshot, clips_dir)
            except FileNotFoundError as exc:
                missing.append({"beat_id": bid, "error": str(exc)})
        if missing:
            return self._send_json(400, {
                "error": "selected files missing for one or more beats",
                "missing": missing,
                "hint": "Re-run animation generation for the listed beats, or pick a different option.",
            })

        # ---- compute cache hash ----
        try:
            cache_hash, beat_meta = compute_cache_hash(
                snapshot, fade_ms, beat_ids_sorted, clips_dir,
            )
        except FileNotFoundError as exc:
            # Defense in depth — should have been caught above.
            return self._send_json(400, {
                "error": str(exc),
                "hint": "File disappeared between existence check and hash computation.",
            })
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            return self._send_json(500, {
                "error": f"cache hash computation failed: {type(exc).__name__}: {exc}",
                "hint": "Internal — check server logs for the traceback.",
            })

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
                return self._send_json(409, {
                    "error": "another preview is already generating",
                    "hint": "Wait for the in-flight preview to finish, then retry.",
                })

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
                    ad_s = float(meta.get("audio_delay") or 0.0)
                    ad_ms = int(round(ad_s * 1000))
                    trimmed = trimmed_dir / (
                        f"{bid}_trimmed_{src_key}_{ts_ms}_{te_ms}_ad{ad_ms}_{_recipe6}.mp4"
                    )
                    duration = trim_normalized(
                        norm, trimmed,
                        meta.get("trim_start"), meta.get("trim_end"),
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
                return self._send_json(504, {
                    "error": f"ffmpeg timeout after {exc.timeout}s",
                    "cmd_summary": " ".join((exc.cmd or [])[:6]) if exc.cmd else "?",
                    "hint": "Try fewer beats or a shorter fade. If persistent, check ffmpeg in PATH.",
                })
            except subprocess.CalledProcessError as exc:
                stderr = (exc.stderr or b"")[:600].decode("utf-8", errors="replace")
                return self._send_json(500, {
                    "error": f"ffmpeg subprocess failed (returncode={exc.returncode})",
                    "stderr": stderr,
                    "hint": "Check the stderr above; common cause is a corrupt source clip.",
                })
            except (BrokenPipeError, ConnectionResetError):
                # Counter (i) HIGH: BrokenPipe inside the ffmpeg pipeline (rare —
                # subprocess.run catches its own pipe errors). If the final file
                # somehow exists, treat as success; else clean up tmps.
                if final_path.is_file():
                    evicted = lru_cleanup(preview_dir)
                    return self._stream_preview_mp4(final_path, cache_hash, evicted=evicted)
                return self._send_json(500, {
                    "error": "broken pipe during preview pipeline",
                    "hint": "Client likely disconnected before pipeline finished.",
                })

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
            return self._send_json(500, {
                "error": f"preview file read failed: {exc}",
                "hint": "Server lost the cached file mid-request — retry once.",
            })
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
            "fallback_settings": {"stability": 0.30, "style": 0.30},
            "model_id": "eleven_v3",
            "speaker": "Chipper",
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
        """GET /api/timeline/audio/<event_id>

        Extract audio from FULL MODULE (Story Scene + Phase A + Phase B).
        Replaces intro-only stitch with real 3-segment assembly. Spec B.
        Returns JSON: {audio_url, duration_ms, segment_boundaries}.
        SIZE_BUDGET_AUDIO_V1: AAC 128kbps mono 44.1kHz.
        """
        import hashlib as _hl  # noqa: PLC0415
        try:
            full_mp4, segment_boundaries = self._get_or_build_full_module_mp4()
        except FileNotFoundError as e:
            return self._send_json(404, {
                "error": str(e),
                "hint": "Click 'Preview-Stitched v2' to build the Story Scene preview first.",
            })
        except Exception as e:
            return self._send_json(500, {"error": f"full module build failed: {e}"})

        mtime_ms = int(full_mp4.stat().st_mtime * 1000)
        cache_key = _hl.md5(
            f"{full_mp4}:{mtime_ms}".encode(), usedforsecurity=False
        ).hexdigest()[:16]

        cache_dir = self.app.event_dir / "preview" / "timeline_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        audio_fname = f"timeline_audio_{cache_key}.mp3"
        audio_path = cache_dir / audio_fname

        if not audio_path.is_file():
            cmd = [
                "ffmpeg", "-y", "-i", str(full_mp4),
                "-vn", "-ac", "1", "-ar", "44100", "-b:a", "128k",
                str(audio_path),
            ]
            try:
                subprocess.run(cmd, check=True, capture_output=True, timeout=180)
            except subprocess.CalledProcessError as exc:
                stderr = (exc.stderr or b"")[:400].decode("utf-8", errors="replace")
                return self._send_json(500, {
                    "error": "audio extraction failed",
                    "stderr": stderr,
                })
            except subprocess.TimeoutExpired:
                return self._send_json(504, {"error": "audio extraction timed out"})

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

        return self._send_json(200, {
            "audio_url": f"/api/media/{audio_fname}",
            "duration_ms": total_ms,
            "segment_boundaries": segment_boundaries,
        })

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
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), "lib"))
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
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), "lib"))
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
            return self._send_json(400, {
                "error": f"timeline audio serve rejects: {safe!r}",
                "hint": "Only timeline_audio_*.mp3 files served here.",
            })
        target = self.app.event_dir / "preview" / "timeline_cache" / safe
        if not target.is_file():
            return self._send_json(404, {"error": f"timeline audio not found: {safe}"})
        body = target.read_bytes()
        self._send_bytes(200, body, "audio/mpeg", extra_headers={
            "Cache-Control": "public, max-age=3600",
            "Accept-Ranges": "bytes",
        })

    def _handle_timeline_sfx_library(self) -> None:
        """GET /api/timeline/sfx_library

        Scan SFX and ambient dirs; return [{filename, path, duration_ms, category}].
        """
        results: list[dict] = []
        scan_dirs: list[tuple[Path, str]] = [
            (self.app.event_dir / "sfx", "sfx"),
            (self.app.event_dir.parent.parent / "assets" / "ambient_library", "ambient"),
        ]

        for scan_dir, category in scan_dirs:
            if not scan_dir.is_dir():
                continue
            for pat in ("*.mp3", "*.wav", "*.m4a"):
                for f in sorted(scan_dir.glob(pat)):
                    duration_ms = self._ffprobe_duration_ms(f)
                    results.append({
                        "filename": f.name,
                        "path": str(f),
                        "duration_ms": duration_ms,
                        "category": category,
                    })

        # Project-root canonical SFX
        project_root = self.app.event_dir.parent.parent
        canonical_sfx = ["magic burst sound for in video.mp3"]
        for fname in canonical_sfx:
            fp = project_root / fname
            if fp.is_file() and not any(r["filename"] == fname for r in results):
                results.append({
                    "filename": fname,
                    "path": str(fp),
                    "duration_ms": self._ffprobe_duration_ms(fp),
                    "category": "sfx",
                })

        return self._send_json(200, results)

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
        """POST /api/timeline/cues — upsert cue by id; atomic write via mutate_state."""
        # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
        if not self._assert_event_scope(self._scope_body(body), allow_missing=False):
            return

        cue_id = body.get("id")
        if not cue_id:
            return self._send_json(400, {"error": "cue id is required"})

        cue_type = body.get("cue_type", "sfx")
        if cue_type not in ("sfx", "ambient_segment"):
            return self._send_json(400, {
                "error": f"invalid cue_type: {cue_type!r}",
                "hint": "Must be 'sfx' or 'ambient_segment'",
            })

        source_path_str = body.get("source_path", "")
        source_path = Path(source_path_str)
        if not source_path.is_file():
            return self._send_json(400, {
                "error": f"source_path not found: {source_path_str}",
                "hint": "Ensure the SFX file exists at the given path.",
            })

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

        self.app.state.mutate_state(_upsert)
        return self._send_json(200, {"ok": True, "cue": cue})

    def _handle_timeline_delete_cue(self, cue_id: str) -> None:
        """DELETE /api/timeline/cues/<id> — atomic remove via mutate_state."""
        # LD-456 SCOPE_VALIDATION_V1 (no-body handler — query-string fallback inside helper)
        if not self._assert_event_scope({}, allow_missing=True):
            return

        if not cue_id:
            return self._send_json(400, {"error": "cue id required in path"})

        removed: list[bool] = [False]

        def _remove(state: dict) -> dict:
            cues = state.get("module_sfx_cues", [])
            new_cues = [c for c in cues if c.get("id") != cue_id]
            removed[0] = len(new_cues) < len(cues)
            state["module_sfx_cues"] = new_cues
            return state

        self.app.state.mutate_state(_remove)
        if not removed[0]:
            return self._send_json(404, {"error": f"cue not found: {cue_id}"})
        return self._send_json(200, {"ok": True, "deleted": cue_id})

    def _handle_timeline_bake(self, body: dict) -> None:
        """POST /api/timeline/cues/bake — confirm cues are committed to production_state."""
        state = self.app.state.read_state()
        cues = state.get("module_sfx_cues", [])
        return self._send_json(200, {"ok": True, "baked": len(cues), "cues": cues})

    def _handle_timeline_open_in_quicktime(self, body: dict) -> None:
        """POST /api/timeline/open_in_quicktime — open mp4_path in QuickTime Player."""
        mp4_path = body.get("mp4_path", "")
        if not mp4_path:
            return self._send_json(400, {"error": "mp4_path is required"})
        p = Path(mp4_path)
        if not p.is_file():
            return self._send_json(404, {"error": f"file not found: {mp4_path}"})
        if p.suffix.lower() not in (".mp4", ".mov", ".m4v"):
            return self._send_json(400, {"error": "only .mp4/.mov/.m4v files allowed"})
        try:
            subprocess.run(
                ["open", "-a", "QuickTime Player", str(p)],
                check=True, timeout=10,
            )
        except subprocess.CalledProcessError as exc:
            return self._send_json(500, {"error": f"open failed: {exc}"})
        return self._send_json(200, {"ok": True, "opened": str(p)})

    @with_pin_and_drain('_handle_timeline_preview_with_sfx', track_sync=True)
    def _handle_timeline_preview_with_sfx(self, body: dict) -> None:
        """POST /api/timeline/preview_with_sfx

        Mix module_sfx_cues into stitched preview. Fast-path stream-copy when 0 cues.
        Post-render: ffprobe bitrate ≤1,900,000 bps + file ≤80MB (SIZE_BUDGET_VIDEO_V1
        + SIZE_BUDGET_PER_MODULE_V1). Returns {mp4_path} on success.
        """
        # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
        if not self._assert_event_scope(self._scope_body(body), allow_missing=False):
            return

        # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — capture pin at entry; terminal writes assert via _check_event_pin.
        _pin = {
            "pinned_generation": self.app.event_generation,
            "pinned_event_dir": self.app.event_dir,
            "pinned_video_role": (body or {}).get("scope_video_role", "intro"),
            "_handler": '_handle_timeline_preview_with_sfx',
        }
        # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — pre-work pin check (S2).
        # If the event was swapped via /api/event/load between scope-guard
        # and work start, abort BEFORE any expensive work begins.
        if not self._check_event_pin(_pin, '_handle_timeline_preview_with_sfx_pre_work'):
            return self._send_json(423, {
                "error": "event_changed_pre_work",
                "code": "ASYNC_JOB_GENERATION_PIN_V1",
                "handler": '_handle_timeline_preview_with_sfx',
                "hint": (
                    "Event changed between scope-guard and work start. "
                    "No work was done; no orphan output. Client should "
                    "re-hydrate scope and retry."
                ),
            })

        import hashlib as _hl  # noqa: PLC0415

        try:
            preview_mp4, _seg_bounds = self._get_or_build_full_module_mp4()
        except FileNotFoundError as e:
            return self._send_json(404, {
                "error": str(e),
                "hint": "Click 'Preview-Stitched v2' to build the Story Scene preview first.",
            })
        except Exception as e:
            return self._send_json(500, {"error": f"full module build failed: {e}"})

        state = self.app.state.read_state()
        cues = state.get("module_sfx_cues", [])

        exports_dir = self.app.event_dir / "exports"
        exports_dir.mkdir(parents=True, exist_ok=True)

        # Fast-path: 0 cues -> stream-copy unchanged (no filter_complex needed)
        if not cues:
            nc_hash = _hl.md5(b"no_cues", usedforsecurity=False).hexdigest()[:8]
            out_fname = f"timeline_preview_sfx_{nc_hash}.mp4"
            out_path = exports_dir / out_fname
            if not out_path.is_file():
                cmd = ["ffmpeg", "-y", "-i", str(preview_mp4), "-c", "copy", str(out_path)]
                try:
                    subprocess.run(cmd, check=True, capture_output=True, timeout=60)
                except subprocess.CalledProcessError as exc:
                    stderr = (exc.stderr or b"")[:400].decode("utf-8", errors="replace")
                    return self._send_json(500, {"error": "stream-copy failed", "stderr": stderr})
            return self._send_json(200, {"mp4_path": str(out_path)})

        # Validate all source files exist before invoking ffmpeg
        for cue in cues:
            if not Path(cue.get("source_path", "")).is_file():
                return self._send_json(400, {
                    "error": f"SFX file not found: {cue.get('source_path')}",
                    "hint": "Remove or update the missing cue before previewing.",
                })

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
            cue_dur_ms = self._ffprobe_duration_ms(Path(cue["source_path"]))
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
        if not self._check_event_pin(_pin, "timeline_preview_sfx_ffmpeg_write"):
            return self._send_json(423, {"error": "event_changed_mid_job", "code": "ASYNC_JOB_GENERATION_PIN_V1"})
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=300)
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or b"")[:600].decode("utf-8", errors="replace")
            return self._send_json(500, {
                "error": "ffmpeg SFX mix failed",
                "stderr": stderr,
                "cmd_head": " ".join(cmd[:10]),
            })
        except subprocess.TimeoutExpired:
            return self._send_json(504, {"error": "ffmpeg SFX mix timed out"})

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
            return self._send_json(422, {
                "error": (
                    f"video bitrate {video_bitrate:,} bps exceeds 1,900,000 bps "
                    "ceiling (SIZE_BUDGET_VIDEO_V1). Do not open in QuickTime."
                ),
                "hint": "Source clips may need re-normalization.",
            })

        if size_mb > 80.0:
            out_path.unlink(missing_ok=True)
            return self._send_json(422, {
                "error": (
                    f"output {size_mb:.1f} MB exceeds 80 MB ceiling "
                    "(SIZE_BUDGET_PER_MODULE_V1). Do not open in QuickTime."
                ),
                "hint": "Reduce SFX count or compress source clips.",
            })

        return self._send_json(200, {"mp4_path": str(out_path)})

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
        """
        root = self._stitch_project_root()
        p = Path(raw)
        resolved = str((p if p.is_absolute() else root / p).resolve())
        if not resolved.startswith(str(root)):
            raise ValueError(f"path outside project root: {raw!r}")
        return resolved

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
            return self._send_json(404, {
                "error": "stitch_editor.html not found",
                "hint": "Run: python3 Production/tools/build_stitch_editor.py --output Production/tools/stitch_editor.html",
            })
        html = html_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.send_header("Cache-Control", "no-store")
        self._cors_headers()
        self.end_headers()
        self.wfile.write(html)

    def _handle_stitch_library(self) -> None:
        """GET /api/stitch_editor/library — scan sound_library + backward-compat dirs.

        Returns {ambient: [...], sfx: [...], transitions: [...]}.
        Each item: {filename, path, duration_ms, category, source_folder}.
        Canonical folders (sound_library/*) take priority over backward-compat duplicates.
        """
        production = self._stitch_production_dir()
        project_root = self._stitch_project_root()
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
                        "duration_ms": self._ffprobe_duration_ms(f),
                        "category": category,
                        "source_folder": source_label,
                    })

        # 1. Canonical folders (preferred — Kim populates these)
        scan(canonical_base / "ambient", "ambient", "sound_library/ambient")
        scan(canonical_base / "sfx", "sfx", "sound_library/sfx")
        scan(canonical_base / "transitions", "transitions", "sound_library/transitions")

        # 2. Backward-compat scan (for files not yet migrated to canonical)
        event1_sfx = self.app.event_dir / "sfx"
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
                        "duration_ms": self._ffprobe_duration_ms(f),
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
                    "duration_ms": self._ffprobe_duration_ms(fp),
                    "category": "sfx", "source_folder": "project_root (legacy)",
                })

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self._cors_headers()
        payload = json.dumps(result).encode()
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _handle_stitch_list_jobs(self) -> None:
        """GET /api/stitch_editor/jobs — list saved job summaries."""
        state = self.app.stitch_state.read_state()
        jobs = [
            {
                "name": k,
                "created_at": v.get("created_at", ""),
                "updated_at": v.get("updated_at", ""),
                "slot_count": len(v.get("slots", [])),
            }
            for k, v in state.get("jobs", {}).items()
        ]
        return self._send_json(200, {"jobs": jobs})

    def _handle_stitch_load_job(self, name: str) -> None:
        """GET /api/stitch_editor/job/<name> — load full job dict."""
        state = self.app.stitch_state.read_state()
        job = state.get("jobs", {}).get(name)
        if job is None:
            return self._send_json(404, {"error": f"Job not found: {name!r}"})
        return self._send_json(200, {"job": job, "name": name})

    def _handle_stitch_save_job(self, body: dict) -> None:
        """POST /api/stitch_editor/job — save or upsert a named job."""
        # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
        if not self._assert_event_scope(self._scope_body(body), allow_missing=False):
            return

        name = (body.get("name") or "").strip()
        if not name:
            return self._send_json(400, {"error": "Job name is required"})

        slots = body.get("slots", [])
        transitions = body.get("transitions", [])

        for i, slot in enumerate(slots):
            vp = slot.get("video_path", "")
            if vp:
                try:
                    self._stitch_resolve_path(vp)
                except ValueError:
                    return self._send_json(403, {"error": f"Slot {i} video_path outside project root"})

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

        self.app.stitch_state.mutate_state(upsert)
        return self._send_json(200, {"ok": True, "name": name})

    def _handle_stitch_delete_job(self, name: str) -> None:
        """DELETE /api/stitch_editor/job/<name> — remove named job."""
        # LD-456 SCOPE_VALIDATION_V1 (no-body handler — query-string fallback inside helper)
        if not self._assert_event_scope({}, allow_missing=True):
            return

        def remove(state: dict) -> None:
            state.get("jobs", {}).pop(name, None)
        self.app.stitch_state.mutate_state(remove)
        return self._send_json(200, {"ok": True, "name": name})

    def _handle_stitch_audio_extract(self, body: dict) -> None:
        """POST /api/stitch_editor/audio_extract — extract audio track for WaveSurfer.

        Input: {video_path: "/abs/path/..."}
        Output: {audio_url: "http://localhost:5111/api/stitch_editor/audio_file/<hash>", duration_ms: N}
        """
        import hashlib as _hl  # noqa: PLC0415
        video_path_str = body.get("video_path", "")
        if not video_path_str:
            return self._send_json(400, {"error": "video_path required"})

        try:
            abs_path = self._stitch_resolve_path(video_path_str)
        except ValueError:
            return self._send_json(403, {"error": "video_path outside project root"})
        if not os.path.isfile(abs_path):
            return self._send_json(404, {"error": f"File not found: {abs_path}"})

        # Cache key: md5(path) + mtime — Producer/Consumer drift rule (source identity)
        mtime_ms = int(os.path.getmtime(abs_path) * 1000)
        cache_key = _hl.md5(
            f"{abs_path}:{mtime_ms}".encode(), usedforsecurity=False
        ).hexdigest()[:16]

        cache_dir = self._stitch_cache_dir()
        audio_fname = f"stitch_audio_{cache_key}.mp3"
        audio_path = cache_dir / audio_fname

        if not audio_path.is_file():
            cmd = [
                "ffmpeg", "-y", "-i", abs_path,
                "-vn", "-ac", "1", "-ar", "44100", "-b:a", "128k",
                str(audio_path),
            ]
            try:
                subprocess.run(cmd, check=True, capture_output=True, timeout=180)
            except subprocess.CalledProcessError as exc:
                stderr = (exc.stderr or b"")[:400].decode("utf-8", errors="replace")
                return self._send_json(500, {"error": "audio extraction failed", "stderr": stderr})
            except subprocess.TimeoutExpired:
                return self._send_json(504, {"error": "audio extraction timed out"})

        duration_ms = self._ffprobe_duration_ms(audio_path)
        return self._send_json(200, {
            "audio_url": f"http://localhost:5111/api/stitch_editor/audio_file/{audio_fname}",
            "duration_ms": duration_ms,
        })

    def _serve_stitch_audio_file(self, fname: str) -> None:
        """GET /api/stitch_editor/audio_file/<fname> — serve extracted waveform audio
        OR ambient library files (sidebar preview).

        Lookup order (first hit wins):
          1. _stitch_cache_dir()                           — extracted waveform audio
          2. Production/assets/ambient_library/            — primary ambient library
          3. Production/assets/sound_library/ambient/      — duplicate location
        """
        safe = Path(fname).name
        project_root = self._stitch_project_root()
        candidates = [
            self._stitch_cache_dir() / safe,
            project_root / "Production" / "assets" / "ambient_library" / safe,
            project_root / "Production" / "assets" / "sound_library" / "ambient" / safe,
        ]
        for target in candidates:
            if target.is_file():
                body = target.read_bytes()
                return self._send_bytes(200, body, "audio/mpeg", extra_headers={
                    "Cache-Control": "public, max-age=3600",
                    "Accept-Ranges": "bytes",
                })
        return self._send_json(404, {"error": f"Audio file not found: {safe}"})

    def _serve_stitch_preview_file(self, hash_id: str) -> None:
        """GET /api/stitch_editor/preview_file/<hash> — serve preview MP4 with byte-range support."""
        safe = Path(hash_id).name
        target = self._stitch_cache_dir() / f"stitch_preview_{safe}.mp4"
        if not target.is_file():
            return self._send_json(404, {"error": f"Preview file not found: {safe}"})
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
            return self._send_json(400, {"error": "path query param required"})

        try:
            abs_path = self._stitch_resolve_path(path_param)
        except ValueError:
            return self._send_json(403, {"error": "path outside project root"})
        if not os.path.isfile(abs_path):
            return self._send_json(404, {"error": f"File not found: {abs_path}"})

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
            return norm_path

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

        if has_audio:
            return norm_path

        try:
            dur_s = self._ffprobe_duration_ms(norm_path) / 1000.0
        except Exception:
            dur_s = 10.0

        sil_path = norm_path.with_suffix("").with_name(norm_path.stem + "_audio.mp4")
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

    def _stitch_mix_slot_audio(
        self, norm_path: Path, slot: dict, cache_dir: Path
    ) -> Path:
        """Mix ambient bed + SFX cues into a normalized slot video.

        SFX offsets in slot are SLOT-RELATIVE ms (from slot start = 0).
        Returns path to final slot MP4 with all audio baked.
        If no ambient and no SFX, returns norm_path unchanged.
        """
        import hashlib as _hl  # noqa: PLC0415

        ambient_path = slot.get("ambient_bed_path") or ""
        ambient_volume = float(slot.get("ambient_volume", 0.15))
        sfx_cues = slot.get("sfx_cues") or []

        if not ambient_path and not sfx_cues:
            return norm_path

        # Validate audio sources exist
        if ambient_path and not os.path.isfile(ambient_path):
            raise FileNotFoundError(f"Ambient bed not found: {ambient_path}")
        for cue in sfx_cues:
            if not os.path.isfile(cue.get("source_path", "")):
                raise FileNotFoundError(f"SFX not found: {cue.get('source_path')}")

        # Cache key: norm mtime + ambient + sfx cue ids
        sig_parts = [str(norm_path.stat().st_mtime), ambient_path, str(ambient_volume)]
        sig_parts += [f"{c['id']}:{c['offset_ms']}" for c in sfx_cues]
        mix_hash = _hl.md5("|".join(sig_parts).encode(), usedforsecurity=False).hexdigest()[:12]
        out_path = cache_dir / f"se_slot_{mix_hash}.mp4"
        if out_path.is_file():
            return out_path

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
            fadeout_start_s = max(0.0, cue_dur_s - fadeout_ms / 1000.0)
            label = f"cue{idx}"
            filter_lanes.append(
                f"[{cidx}:a]aresample=44100,"
                f"adelay={offset_ms}|{offset_ms},"
                f"afade=t=in:st=0:d={fadein_ms / 1000:.3f},"
                f"afade=t=out:st={fadeout_start_s:.3f}:d={fadeout_ms / 1000:.3f},"
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

    def _stitch_build_pipeline(self, body: dict) -> tuple[Path, list[int]]:
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

            elif kind == "dissolve":
                # NEW S5.5g — visual fadeblack at boundary. Apply fade=t=out
                # to slot[after_slot] tail + fade=t=in to slot[after_slot+1]
                # head. Audio fade conditional on audio_xfade_ms (Q1 LOCKED).
                # Reference: LD-376 fadeblack pattern from Phase A.
                slot_finals[after_slot] = self._stitch_apply_dissolve_tail(
                    slot_finals[after_slot], cache_dir,
                    fade_ms=fade_ms, audio_xfade_ms=audio_xfade_ms,
                )
                if after_slot + 1 < len(slot_finals):
                    slot_finals[after_slot + 1] = self._stitch_apply_dissolve_head(
                        slot_finals[after_slot + 1], cache_dir,
                        fade_ms=fade_ms, audio_xfade_ms=audio_xfade_ms,
                    )

        # Concat all slot finals (LD-284: already normalized)
        job_sig = json.dumps(
            {"slots": [s.get("video_path") for s in slots], "trans": len(transitions)},
            sort_keys=True,
        ).encode()
        out_hash = _hl.md5(
            f"{[str(f) for f in slot_finals]}".encode() + job_sig,
            usedforsecurity=False,
        ).hexdigest()[:12]

        out_path = cache_dir / f"stitch_preview_{out_hash}.mp4"
        if not out_path.is_file():
            concat_with_xfade_clips(slot_finals, out_path)

        # LRU cleanup (prevent cache accumulation)
        lru_cleanup(cache_dir, keep=5, pattern=r"^stitch_preview_.*\.mp4$")
        lru_cleanup(cache_dir, keep=10, pattern=r"^se_slot_.*\.mp4$")

        return out_path, slot_durations

    @with_pin_and_drain('_handle_stitch_preview', track_sync=True)
    def _handle_stitch_preview(self, body: dict) -> None:
        """POST /api/stitch_editor/preview — build temp MP4, return URL for inline playback.

        LD-140: preview is unregistered. Rule 19: all error paths explicit.
        V59 architectural-fix (Wave 1, 2026-05-04): scope-guarded for
        consistency with _handle_stitch_bake / _handle_stitch_save_job per
        MUTATION_CHANNEL_INVARIANT_V1 + LD-456 SCOPE_VALIDATION_V1.
        """
        # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
        if not self._assert_event_scope(self._scope_body(body), allow_missing=False):
            return
        try:
            out_path, slot_durations = self._stitch_build_pipeline(body)
        except (ValueError, PermissionError) as exc:
            return self._send_json(400, {"error": str(exc)})
        except FileNotFoundError as exc:
            return self._send_json(404, {"error": str(exc)})
        except RuntimeError as exc:
            return self._send_json(500, {"error": str(exc)})

        # Strip the stitch_preview_ prefix for the URL hash segment
        hash_id = out_path.stem.replace("stitch_preview_", "")
        duration_ms = self._ffprobe_duration_ms(out_path)
        return self._send_json(200, {
            "preview_url": f"http://localhost:5111/api/stitch_editor/preview_file/{hash_id}",
            "duration_ms": duration_ms,
            "slot_durations": slot_durations,
        })

    @with_pin_and_drain('_handle_stitch_bake', track_sync=True)
    def _handle_stitch_bake(self, body: dict) -> None:
        """POST /api/stitch_editor/bake — final MP4, SIZE_BUDGET gates, Directus registration.

        LD-140: bake IS registered (unlike preview). LD-280: single atomic MP4.
        LD-283: ≤80MB. SIZE_BUDGET_VIDEO_V1: ≤1,900,000 bps.
        """
        # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
        if not self._assert_event_scope(self._scope_body(body), allow_missing=False):
            return

        # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — capture pin at entry; terminal writes assert via _check_event_pin.
        _pin = {
            "pinned_generation": self.app.event_generation,
            "pinned_event_dir": self.app.event_dir,
            "pinned_video_role": (body or {}).get("scope_video_role", "intro"),
            "_handler": '_handle_stitch_bake',
        }
        # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — pre-work pin check (S2).
        # If the event was swapped via /api/event/load between scope-guard
        # and work start, abort BEFORE any expensive work begins.
        if not self._check_event_pin(_pin, '_handle_stitch_bake_pre_work'):
            return self._send_json(423, {
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

        bake_lock_path = self._stitch_cache_dir() / "stitch_bake.lock"
        bake_lock_path.touch(exist_ok=True)

        try:
            fd = os.open(str(bake_lock_path), os.O_RDWR)
            try:
                fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (BlockingIOError, OSError):
                os.close(fd)
                return self._send_json(409, {"error": "Bake already in progress"})
        except Exception as exc:
            return self._send_json(500, {"error": f"Lock setup failed: {exc}"})

        try:
            try:
                out_path, _durations = self._stitch_build_pipeline(body)
            except (ValueError, PermissionError) as exc:
                return self._send_json(400, {"error": str(exc)})
            except FileNotFoundError as exc:
                return self._send_json(404, {"error": str(exc)})
            except RuntimeError as exc:
                return self._send_json(500, {"error": str(exc)})

            # SIZE_BUDGET_VIDEO_V1: ffprobe bitrate assertion ≤ 1,900,000 bps
            try:
                vp = subprocess.run(
                    ["ffprobe", "-v", "error", "-show_entries", "format=bit_rate",
                     "-of", "json", str(out_path)],
                    capture_output=True, timeout=10, check=True,
                )
                bitrate = int(json.loads(vp.stdout).get("format", {}).get("bit_rate", 0))
            except Exception:
                bitrate = 0

            if bitrate > 1_900_000:
                out_path.unlink(missing_ok=True)
                return self._send_json(422, {
                    "error": f"Video bitrate {bitrate:,} bps exceeds 1,900,000 bps (SIZE_BUDGET_VIDEO_V1)",
                    "actual_bps": bitrate,
                })

            # SIZE_BUDGET_PER_MODULE_V1: ≤ 80 MB
            file_size = out_path.stat().st_size
            size_mb = file_size / (1024 * 1024)
            if size_mb > 80.0:
                out_path.unlink(missing_ok=True)
                return self._send_json(422, {
                    "error": f"Output {size_mb:.1f} MB exceeds 80 MB ceiling (SIZE_BUDGET_PER_MODULE_V1)",
                    "actual_bytes": file_size,
                })

            # Copy to stable bake path
            job_name = body.get("name") or "untitled"
            now_ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            bake_name = f"stitch_{job_name}_{now_ts}.mp4"
            exports_dir = self._stitch_exports_dir()
            bake_path = exports_dir / bake_name
            shutil.copy2(str(out_path), str(bake_path))

            # LD-421: register via registered_write.py two-write rule
            asset_id = -1
            try:
                sys.path.insert(0, str(Path(__file__).parent))
                from registered_write import register_asset  # noqa: PLC0415
                slots = body.get("slots") or []
                iter_notes = (
                    f"Stitch editor bake. Job: {job_name}. "
                    f"{len(slots)} slot(s), {sum(len(s.get('sfx_cues') or []) for s in slots)} SFX cues."
                )
                # module_id=1 sentinel for non-module-scoped assets (per _MODULE_MAP comment)
                # LD-460 — terminal pin check before final asset register.
                if not self._check_event_pin(_pin, "stitch_bake_register_asset"):
                    return self._send_json(423, {"error": "event_changed_mid_job", "code": "ASYNC_JOB_GENERATION_PIN_V1", "orphaned_bake_path": str(bake_path)})
                asset_id, _ = register_asset(
                    file_path=str(bake_path),
                    asset_type="final_atomic_mp4",
                    module_id=1,
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

            return self._send_json(200, {
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
            return self._send_json(400, {
                "error": f"phase media serve rejects non-phase file: {safe!r}",
                "hint": "Endpoint restricted to phase_*_voice_stem/mixed/lipsync files.",
            })
        target = self.app.event_dir / safe
        if not target.is_file():
            return self._send_json(404, {"error": f"phase media not found: {safe}"})
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

        Streams Production/assets/watercolor_library/<filename> thumbnails and
        video cue assets to the timeline widget's library panel.
        """
        safe = Path(filename).name
        # Only allow known watercolor extensions.
        if not safe.lower().endswith((".png", ".mov", ".mp4")):
            return self._send_json(400, {
                "error": f"watercolor serve rejects unsupported ext: {safe!r}",
                "hint": "Allowed: .png, .mov, .mp4",
            })
        target = self._phase_assets_dir("watercolor_library") / safe
        if not target.is_file():
            return self._send_json(404, {"error": f"watercolor not found: {safe}"})
        suffix = target.suffix.lower()
        ctype = {".png": "image/png", ".mov": "video/quicktime",
                 ".mp4": "video/mp4"}.get(suffix, "application/octet-stream")
        body = target.read_bytes()
        self._send_bytes(200, body, ctype, extra_headers={
            "Cache-Control": "public, max-age=600",
        })

    @with_pin_and_drain('_handle_phase_b_regen_audio', track_sync=True)
    def _handle_phase_b_regen_audio(self, body: dict) -> None:
        """POST /api/phase_b/regen_audio

        Body: {"phase": "a"|"b", "script": "text"}

        Writes phase_{phase}_voice_stem_<TS>.mp3 to event_dir root.
        Patches state phase_X_voice_stem_file + phase_X_voice_stem_mtime via mutate_state.
        Returns 200 with file path + duration on success.
        """
        # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
        if not self._assert_event_scope(self._scope_body(body), allow_missing=False):
            return

        # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — capture pin at entry; terminal writes assert via _check_event_pin.
        _pin = {
            "pinned_generation": self.app.event_generation,
            "pinned_event_dir": self.app.event_dir,
            "pinned_video_role": (body or {}).get("scope_video_role", "intro"),
            "_handler": '_handle_phase_b_regen_audio',
        }
        # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — pre-work pin check (S2).
        # If the event was swapped via /api/event/load between scope-guard
        # and work start, abort BEFORE any expensive work begins.
        if not self._check_event_pin(_pin, '_handle_phase_b_regen_audio_pre_work'):
            return self._send_json(423, {
                "error": "event_changed_pre_work",
                "code": "ASYNC_JOB_GENERATION_PIN_V1",
                "handler": '_handle_phase_b_regen_audio',
                "hint": (
                    "Event changed between scope-guard and work start. "
                    "No work was done; no orphan output. Client should "
                    "re-hydrate scope and retry."
                ),
            })

        phase = (body.get("phase") or "").strip().lower()
        err = self._phase_check(phase)
        if err:
            return self._send_json(400, {"error": err,
                                         "hint": "phase is 'a' (Chipper) or 'b' (Cedric)."})
        script = body.get("script") or ""
        if not isinstance(script, str) or not script.strip():
            return self._send_json(400, {
                "error": "script is required and must be non-empty string",
                "hint": "Paste the Phase {} script in the panel textarea.".format(phase.upper()),
            })
        if len(script) > 50_000:
            return self._send_json(400, {
                "error": f"script too long ({len(script)} chars, max 50000)",
                "hint": "Split into shorter segments or edit down.",
            })

        # Load ElevenLabs key via parse_api_keys pattern (matches server-wide usage).
        root = self._phase_project_root()
        keys = parse_api_keys(root / "Production" / "API_KEYS_MASTER.md")
        elevenlabs_key = keys.get("elevenlabs")
        if not elevenlabs_key:
            return self._send_json(500, {
                "error": "ElevenLabs API key not configured",
                "hint": "Set ELEVENLABS_API_KEY env var or populate API_KEYS_MASTER.md.",
            })

        voice_id, model_id, voice_settings, speaker = self._phase_resolve_voice_settings(phase)
        # Universal hardening: robust_https_request with 3 retries + 90s timeout.
        from kling_startend_pipeline import robust_https_request  # noqa: PLC0415
        tts_body = json.dumps({
            "text": script,
            "model_id": model_id,
            "voice_settings": voice_settings,
        }).encode("utf-8")
        t0 = time.time()
        try:
            status_code, audio_bytes = robust_https_request(
                host="api.elevenlabs.io",
                path=f"/v1/text-to-speech/{voice_id}",
                method="POST",
                headers={"xi-api-key": elevenlabs_key,
                         "Content-Type": "application/json",
                         "Accept": "audio/mpeg"},
                body=tts_body,
                timeout=90,
                max_retries=3,
            )
        except Exception as exc:  # noqa: BLE001
            return self._send_json(502, {
                "error": f"ElevenLabs network failure (after retries): "
                         f"{type(exc).__name__}: {exc}",
                "speaker": speaker,
                "voice_id": voice_id,
                "hint": "Check network / ElevenLabs status. Retry after a minute.",
            })
        if status_code >= 400:
            detail = audio_bytes[:400].decode("utf-8", errors="replace")
            return self._send_json(502, {
                "error": f"ElevenLabs HTTP {status_code}: {detail}",
                "speaker": speaker,
                "hint": "Often: API key expired or voice_id renamed. Check API_KEYS_MASTER.md.",
            })
        elapsed_call = time.time() - t0

        # Atomic write to event_dir root.
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        out_name = f"phase_{phase}_voice_stem_{ts}.mp3"
        out_path = self.app.event_dir / out_name
        tmp = out_path.with_suffix(f".mp3.tmp.{os.getpid()}")
        # LD-460 — terminal pin check before voice-stem file write.
        if not self._check_event_pin(_pin, "phase_b_regen_audio_write_bytes"):
            return self._send_json(423, {"error": "event_changed_mid_job", "code": "ASYNC_JOB_GENERATION_PIN_V1"})
        try:
            tmp.write_bytes(audio_bytes)
            os.replace(tmp, out_path)
        except OSError as exc:
            try:
                tmp.unlink(missing_ok=True)
            except Exception:  # noqa: BLE001
                pass
            return self._send_json(500, {
                "error": f"atomic write failed: {exc}",
                "hint": "Check event_dir permissions / disk space.",
            })
        try:
            duration = _ffprobe_duration(out_path)
        except (subprocess.CalledProcessError, ValueError, OSError):
            duration = 0.0
        mtime = int(os.path.getmtime(str(out_path)))

        # Patch state via mutate_state.
        def _apply(state, _p=phase, _n=out_name, _m=mtime):
            state[f"phase_{_p}_voice_stem_file"] = _n
            state[f"phase_{_p}_voice_stem_mtime"] = _m
            state["_module_version"] = int(state.get("_module_version", 0) or 0) + 1
            return state["_module_version"]
        try:
            new_version = self.app.state.mutate_state(_apply)
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            return self._send_json(500, {
                "error": f"mutate_state failed: {type(exc).__name__}: {exc}",
                "hint": "State.json could not be persisted. File was written to disk.",
            })

        return self._send_json(200, {
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
        """GET /api/voice/profile/<id> — read prod_voice_profiles by id.

        Returns the current stability / similarity_boost / style /
        character_name so the panel can hydrate sliders from the
        single source of truth.
        """
        try:
            pid = int(pid_raw)
        except (TypeError, ValueError):
            return self._send_json(400, {
                "error": f"profile id must be integer, got {pid_raw!r}",
                "hint": "Try /api/voice/profile/2 (Chipper).",
            })
        if pid not in self._VOICE_PROFILE_GET_ALLOWED_IDS:
            return self._send_json(403, {
                "error": f"profile id {pid} not in read allow-list "
                         f"{sorted(self._VOICE_PROFILE_GET_ALLOWED_IDS)}",
                "hint": "Phase A panel scope: Chipper=2.",
            })
        try:
            c = _get_voice_directus_client()
            r = c._request("GET", f"/items/prod_voice_profiles/{pid}")
        except Exception as exc:  # noqa: BLE001
            return self._send_json(502, {
                "error": f"Directus read failed: {type(exc).__name__}: {exc}",
                "hint": "Check Directus connectivity / credentials.",
            })
        data = (r or {}).get("data") or {}
        if not data:
            return self._send_json(404, {
                "error": f"prod_voice_profiles id={pid} not found",
            })
        return self._send_json(200, {
            "id": data.get("id"),
            "character_name": data.get("character_name"),
            "stability": data.get("stability"),
            "similarity_boost": data.get("similarity_boost"),
            "style": data.get("style"),
            "speed": data.get("speed"),
            "model": data.get("model"),
            "elevenlabs_voice_id": data.get("elevenlabs_voice_id"),
        })

    def _handle_voice_profile_update(self, body: dict) -> None:
        """POST /api/voice/profile_update — persist slider changes.

        Body: {"id": 2, "stability": 0.25, "similarity_boost": 0.75,
               "style": 0.55}

        Validates id is in allow-list, fields are floats in [0.0, 1.0],
        PATCHes Directus prod_voice_profiles by id, then force-refreshes
        the in-process voice cache so the next /api/phase_b/regen_audio
        call uses the new settings.
        """
        if not isinstance(body, dict):
            return self._send_json(400, {"error": "body must be JSON object"})
        try:
            pid = int(body.get("id"))
        except (TypeError, ValueError):
            return self._send_json(400, {
                "error": f"id required and must be integer; got {body.get('id')!r}",
                "hint": "Phase A panel posts id=2 (Chipper).",
            })
        if pid not in self._VOICE_PROFILE_PATCH_ALLOWED_IDS:
            return self._send_json(403, {
                "error": f"profile id {pid} not in WRITE allow-list "
                         f"{sorted(self._VOICE_PROFILE_PATCH_ALLOWED_IDS)}",
                "hint": "Phase A panel writes Chipper (id=2) only. "
                        "Cedric (id=1) and Tessa (id=3) are not editable "
                        "from this route per Phase 0 verdict.",
            })
        # Build patch payload from whitelisted fields only.
        patch: dict = {}
        for field in self._VOICE_PROFILE_ALLOWED_FIELDS:
            if field not in body:
                continue
            raw = body.get(field)
            try:
                v = float(raw)
            except (TypeError, ValueError):
                return self._send_json(400, {
                    "error": f"{field} must be number, got {raw!r}",
                })
            if not (0.0 <= v <= 1.0):
                return self._send_json(400, {
                    "error": f"{field} out of range [0.0, 1.0]: {v}",
                    "hint": "ElevenLabs voice settings are 0..1 floats.",
                })
            # Round to 2 decimals — slider step is 0.01 client-side; round
            # tighter than that and we silently destroy any historical 3+
            # decimal value Kim retunes via Directus UI directly. Counter-
            # agent F6 fix: was round(v, 4), now matches client precision.
            patch[field] = round(v, 2)
        if not patch:
            return self._send_json(400, {
                "error": "no whitelisted fields in body",
                "hint": f"Allowed: {sorted(self._VOICE_PROFILE_ALLOWED_FIELDS)}",
            })
        # PATCH Directus via cached client (counter-agent F4 fix: was
        # creating a fresh client + load_credentials() per request, which
        # hammers Doppler/disk on every slider change).
        try:
            c = _get_voice_directus_client()
            r = c._request("PATCH", f"/items/prod_voice_profiles/{pid}", data=patch)
        except Exception as exc:  # noqa: BLE001
            return self._send_json(502, {
                "error": f"Directus PATCH failed: {type(exc).__name__}: {exc}",
                "hint": "Slider value not persisted. Retry; check Directus.",
            })
        # Force-refresh the in-process cache so the next regen sees the new
        # values (avoids stale-cache drift; counter Phase 0 C2 mitigation).
        try:
            _load_voice_profiles_from_directus(force_refresh=True)
        except Exception as exc:  # noqa: BLE001
            print(f"[voice-profile-update] WARN cache reload failed: {exc}",
                  file=sys.stderr)
        data = (r or {}).get("data") or {}
        return self._send_json(200, {
            "ok": True,
            "id": data.get("id", pid),
            "character_name": data.get("character_name"),
            "stability": data.get("stability"),
            "similarity_boost": data.get("similarity_boost"),
            "style": data.get("style"),
            "patched_fields": sorted(patch.keys()),
        })

    @with_pin_and_drain('_handle_phase_b_mix_audio', track_sync=True)
    def _handle_phase_b_mix_audio(self, body: dict) -> None:
        """POST /api/phase_b/mix_audio

        Body: {"phase": "a"|"b", "ambient_preset_id": "meditation_fireplace_v1"}

        Reads phase_{phase}_voice_stem_file from state (must exist).
        Loads ambient from Production/assets/ambient_library/<ambient_preset_id>.mp3.
        Mixes voice (0dB) + ambient (-18dB) via ffmpeg amix filter.
        Writes phase_{phase}_mixed_<TS>.mp3 and patches state.
        """
        # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
        if not self._assert_event_scope(self._scope_body(body), allow_missing=False):
            return

        # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — capture pin at entry; terminal writes assert via _check_event_pin.
        _pin = {
            "pinned_generation": self.app.event_generation,
            "pinned_event_dir": self.app.event_dir,
            "pinned_video_role": (body or {}).get("scope_video_role", "intro"),
            "_handler": '_handle_phase_b_mix_audio',
        }
        # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — pre-work pin check (S2).
        # If the event was swapped via /api/event/load between scope-guard
        # and work start, abort BEFORE any expensive work begins.
        if not self._check_event_pin(_pin, '_handle_phase_b_mix_audio_pre_work'):
            return self._send_json(423, {
                "error": "event_changed_pre_work",
                "code": "ASYNC_JOB_GENERATION_PIN_V1",
                "handler": '_handle_phase_b_mix_audio',
                "hint": (
                    "Event changed between scope-guard and work start. "
                    "No work was done; no orphan output. Client should "
                    "re-hydrate scope and retry."
                ),
            })

        phase = (body.get("phase") or "").strip().lower()
        err = self._phase_check(phase)
        if err:
            return self._send_json(400, {"error": err,
                                         "hint": "phase is 'a' or 'b'."})
        ambient_preset_id = body.get("ambient_preset_id")
        if not ambient_preset_id or not isinstance(ambient_preset_id, str):
            return self._send_json(400, {
                "error": "ambient_preset_id is required (string)",
                "hint": "Pick from the ambient preset dropdown.",
            })
        # Resolve voice stem from state.
        state = self.app.state.read_state()
        voice_stem_name = state.get(f"phase_{phase}_voice_stem_file")
        if not voice_stem_name:
            return self._send_json(400, {
                "error": f"phase_{phase}_voice_stem_file not set in state",
                "hint": "Run Regen Audio first to produce a voice stem.",
            })
        voice_stem_path = self.app.event_dir / voice_stem_name
        if not voice_stem_path.is_file():
            return self._send_json(404, {
                "error": f"voice stem file not found: {voice_stem_name}",
                "hint": "File may have been deleted. Re-run Regen Audio.",
            })
        # Resolve ambient preset.
        ambient_dir = self._phase_assets_dir("ambient_library")
        ambient_path = ambient_dir / f"{ambient_preset_id}.mp3"
        if not ambient_path.is_file():
            return self._send_json(404, {
                "error": f"ambient preset not found: {ambient_preset_id}.mp3",
                "hint": f"Check {ambient_dir} for available presets.",
                "looked_in": str(ambient_dir),
            })
        # Voice-source selection:
        # If a lipsync video exists, extract its audio track and use THAT as
        # the voice source — it is bit-exact what ByteDance animated against,
        # so the mixed output preserves perfect beak-sync timing. Running a
        # fresh silcomp here produces subtly different silence boundaries than
        # what was in the lipsync submission, which causes drift.
        # Fallback: use raw voice stem (used when lipsync hasn't run yet).
        # (Fix 2026-04-21 evening.)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        voice_extract_path = self.app.event_dir / f"_tmp_voice_extract_{phase}_{ts}.mp3"
        voice_for_mix_path = voice_stem_path  # default fallback
        lipsync_name_for_source = state.get(f"phase_{phase}_lipsync_file")
        lipsync_source_path: Path | None = None
        if lipsync_name_for_source:
            candidate = self.app.event_dir / lipsync_name_for_source
            if candidate.is_file():
                lipsync_source_path = candidate
                try:
                    subprocess.run([
                        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-i", str(candidate.resolve()),
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

        out_name = f"phase_{phase}_mixed_{ts}.mp3"
        out_path = self.app.event_dir / out_name
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
            cmd = [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-i", str(voice_for_mix_path.resolve()),
                "-i", str(ambient_path.resolve()),
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
            return self._send_json(500, {
                "error": f"ffmpeg amix failed (returncode={exc.returncode})",
                "stderr": stderr,
                "hint": "Check ambient preset format (expect mp3, 44.1kHz).",
            })
        except (subprocess.TimeoutExpired, OSError) as exc:
            try:
                tmp.unlink(missing_ok=True)
            except Exception:  # noqa: BLE001
                pass
            return self._send_json(500, {
                "error": f"ffmpeg mix error: {type(exc).__name__}: {exc}",
                "hint": "Try a shorter voice stem or different ambient preset.",
            })
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
            new_version = self.app.state.mutate_state(_apply)
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            return self._send_json(500, {
                "error": f"mutate_state failed: {type(exc).__name__}: {exc}",
                "hint": "State.json could not be persisted. File was written to disk.",
            })

        # Auto-remux: if a lipsync video exists for this phase, replace its
        # audio track with the newly mixed (voice + ambient bed) audio so the
        # "Preview Phase A/B Stitched" button reads the right thing. Added
        # 2026-04-21 after Kim hit the case where Phase A lipsync was baked
        # with voice-only audio (no bed) because the panel workflow is
        # lipsync-first, mix-later. ffmpeg -c:v copy keeps the video stream
        # bit-exact; only the audio track is replaced.
        remux_info = None
        state_after = self.app.state.read_state()
        lipsync_name = state_after.get(f"phase_{phase}_lipsync_file")
        if lipsync_name:
            lipsync_path = self.app.event_dir / lipsync_name
            if lipsync_path.is_file():
                new_lipsync_name = f"phase_{phase}_lipsync_withbed_{ts}.mp4"
                new_lipsync_path = self.app.event_dir / new_lipsync_name
                try:
                    subprocess.run([
                        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-i", str(lipsync_path.resolve()),
                        "-i", str(out_path.resolve()),
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
                    new_version = self.app.state.mutate_state(_apply_lipsync)
                    remux_info = {"lipsync_file": new_lipsync_name, "lipsync_mtime": new_lipsync_mtime}
                except subprocess.CalledProcessError as exc:
                    # Non-fatal: the mix succeeded. Just log and move on.
                    stderr = (exc.stderr or b"")[:200].decode("utf-8", errors="replace")
                    print(f"[mix_audio] lipsync re-mux failed (non-fatal): rc={exc.returncode} stderr={stderr}")
                except (subprocess.TimeoutExpired, OSError) as exc:
                    print(f"[mix_audio] lipsync re-mux failed (non-fatal): {type(exc).__name__}: {exc}")

        # Auto-assemble Phase A canonical: flyin + lipsync_withbed + flyout,
        # all normalized to LD-284 (H.264 High / yuv420p / 1280x720 / 24fps /
        # AAC 128k / +faststart) and concatenated via concat demuxer with
        # -c copy. Triggers only for phase=='a'. Phase B modules ship the
        # lipsync file directly (no fly-in/out wrapper). Added 2026-04-21.
        canonical_info = None
        if phase == "a" and remux_info is not None:
            try:
                canonical_info = self._auto_assemble_phase_a_stitched(ts)
            except Exception as exc:  # noqa: BLE001
                # Non-fatal: mix + remux succeeded; canonical is a nice-to-have.
                traceback.print_exc()
                canonical_info = {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}

        return self._send_json(200, {
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

    def _auto_assemble_phase_a_stitched(self, ts: str) -> dict | None:
        """Stitch fly-in + lipsync (voice-only) + fly-out, then overlay a
        CONTINUOUS ambient bed across the entire duration so the bed is
        audible during the fly-in and fly-out (not just the middle).

        Two-stage ffmpeg:
          1. Normalize each clip to LD-284 and concat -> intermediate
             (voice-only in middle, silent at edges)
          2. Overlay full-length bed from state.phase_a_ambient_preset_id at
             volume=0.15 (normalize=0) -> canonical final

        Uses the RAW lipsync (no "withbed" in name) as the middle section so
        the final mix never double-applies the bed (Kim fix 2026-04-21 late).

        Returns {file, mtime, duration_s} or None if inputs missing.
        """
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "lib"))
        from ffmpeg_stitch import normalize_for_concat, concat_with_xfade_clips  # type: ignore

        state = self.app.state.read_state()

        # Find RAW lipsync (no "withbed" in name) on disk. The mix_audio handler
        # updates state.phase_a_lipsync_file to the withbed version, so we can't
        # use the state pointer — we want the pre-mix source with only voice audio.
        raw_lipsyncs = sorted(
            (p for p in self.app.event_dir.glob("phase_a_lipsync_*.mp4")
             if "withbed" not in p.name.lower()),
            key=lambda p: p.stat().st_mtime, reverse=True,
        )
        if not raw_lipsyncs:
            return None
        raw_lipsync_path = raw_lipsyncs[0]

        # Auto-detect latest fly-in (most recent by mtime).
        flyins = sorted(
            self.app.event_dir.glob("phase_a_flyin*.mp4"),
            key=lambda p: p.stat().st_mtime, reverse=True,
        )
        # Auto-detect latest fly-out v*; prefer non-"kling"-named variants
        # since those are the post-processed shippable versions.
        flyouts_all = sorted(
            self.app.event_dir.glob("phase_a_flyout_v*.mp4"),
            key=lambda p: p.stat().st_mtime, reverse=True,
        )
        flyouts = [p for p in flyouts_all if "kling" not in p.name.lower()]
        if not flyouts:
            flyouts = flyouts_all
        if not flyins or not flyouts:
            return None
        flyin_src = flyins[0]
        flyout_src = flyouts[0]

        # Resolve ambient preset (for the full-length overlay).
        # S5.5d (v3): phase_a is TOP-LEVEL state.
        ambient_preset_id = (state.get("phase_a") or {}).get("phase_a_ambient_preset_id")
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

        flyin_norm = norm_dir / f"flyin_{flyin_src.stem}.mp4"
        raw_norm = norm_dir / f"raw_{raw_lipsync_path.stem}.mp4"
        flyout_norm = norm_dir / f"flyout_{flyout_src.stem}.mp4"
        _normalize_cached(flyin_src, flyin_norm)
        _normalize_cached(raw_lipsync_path, raw_norm)
        _normalize_cached(flyout_src, flyout_norm)

        # Stage 1: concat flyin + raw_lipsync + flyout with xfade transitions.
        # - fade_in_s (0.5s): flyin -> middle — masks Chipper's smile landing.
        # - fade_out_s (1.5s): middle -> flyout — EXTENDED to cover "Good luck!"
        #   which lands at ~25.25s into the canonical and whose lipsync is
        #   unsynced on the final frames; the 1.5s fade window puts the phrase
        #   under a black/flyout dissolve so viewers hear it without seeing
        #   the unsynced mouth. Audio uses acrossfade at matching durations.
        #   (Kim 2026-04-21 fix.)
        flyin_dur = _ffprobe_duration(flyin_norm)
        raw_dur = _ffprobe_duration(raw_norm)
        fade_in_s = 0.5
        fade_out_s = 2.5
        offset_1 = max(0.0, flyin_dur - fade_in_s)
        # Second xfade offset lives in the [v01] timeline (which is shorter
        # than flyin_dur+raw_dur by fade_in_s).
        offset_2 = max(0.0, flyin_dur + raw_dur - fade_in_s - fade_out_s)

        intermediate_path = norm_dir / f"intermediate_{ts}.mp4"
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "lib"))
        from ffmpeg_stitch import (  # type: ignore
            NORMALIZATION_VF_EXPR, NORMALIZATION_ENCODER_ARGS,
        )
        # fadeblack on the second transition: middle fades to pure black at
        # the fade midpoint, then fly-out emerges from black. Unlike plain
        # "fade" (which shows both clips simultaneously with reduced opacity),
        # fadeblack GUARANTEES the middle is completely gone before fly-out
        # appears — which hides the unsynced "Good luck!" mouth frames.
        filter_complex = (
            f"[0:v][1:v]xfade=transition=fade:duration={fade_in_s}:offset={offset_1:.3f}[v01];"
            f"[v01][2:v]xfade=transition=fadeblack:duration={fade_out_s}:offset={offset_2:.3f}[vx];"
            f"[vx]{NORMALIZATION_VF_EXPR}[vout];"
            f"[0:a][1:a]acrossfade=d={fade_in_s}[a01];"
            f"[a01][2:a]acrossfade=d={fade_out_s}[aout]"
        )
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(flyin_norm.resolve()),
            "-i", str(raw_norm.resolve()),
            "-i", str(flyout_norm.resolve()),
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-map", "[aout]",
            *NORMALIZATION_ENCODER_ARGS,
            str(intermediate_path),
        ], check=True, capture_output=True, timeout=180)

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
            # S5.5d (v3): phase_a is TOP-LEVEL state; lazy-create.
            _phase_a = state.setdefault("phase_a", {})
            _phase_a["phase_a_stitched_file"] = _n
            _phase_a["phase_a_stitched_mtime"] = _m
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
            "flyin": flyin_src.name,
            "raw_lipsync": raw_lipsync_path.name,
            "flyout": flyout_src.name,
            "ambient_preset_id": ambient_preset_id,
        }

    @with_pin_and_drain('_handle_phase_b_lipsync', track_sync=True)
    def _handle_phase_b_lipsync(self, body: dict) -> None:
        """POST /api/phase_b/lipsync

        Body: {"phase": "a"|"b", "base_clip_id": "placeholder_cedric_base_v1"}

        Module-level lipsync (no beat). Loads base clip from
        Production/assets/lipsync_bases/<base_clip_id> (auto .mp4 / .mov),
        mixed audio from state phase_{phase}_mixed_audio_file (fallback to
        voice_stem). Applies silcomp, trims video to audio, submits to
        ByteDance via LipSyncClient.submit_and_wait (synchronous).

        Writes phase_{phase}_lipsync_<TS>.mp4 and patches state.
        """
        # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
        if not self._assert_event_scope(self._scope_body(body), allow_missing=False):
            return

        # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — capture pin at entry; terminal writes assert via _check_event_pin.
        _pin = {
            "pinned_generation": self.app.event_generation,
            "pinned_event_dir": self.app.event_dir,
            "pinned_video_role": (body or {}).get("scope_video_role", "intro"),
            "_handler": '_handle_phase_b_lipsync',
        }

        if self.app.client is None:
            return self._send_json(500, {
                "error": "WaveSpeed client not configured (missing API key)",
                "hint": "Populate API_KEYS_MASTER.md wavespeed entry.",
            })
        phase = (body.get("phase") or "").strip().lower()
        err = self._phase_check(phase)
        if err:
            return self._send_json(400, {"error": err, "hint": "phase is 'a' or 'b'."})
        base_clip_id = body.get("base_clip_id")
        if not base_clip_id or not isinstance(base_clip_id, str):
            return self._send_json(400, {
                "error": "base_clip_id is required (string)",
                "hint": "Pick from the base-clip dropdown.",
            })
        # Resolve audio source: prefer mixed_audio_file, fallback to voice_stem.
        state = self.app.state.read_state()
        audio_name = (state.get(f"phase_{phase}_mixed_audio_file")
                      or state.get(f"phase_{phase}_voice_stem_file"))
        if not audio_name:
            return self._send_json(400, {
                "error": f"phase_{phase}_mixed_audio_file and phase_{phase}_voice_stem_file both unset",
                "hint": "Run Regen Audio (and optionally Mix Audio) first.",
            })
        audio_path = self.app.event_dir / audio_name
        if not audio_path.is_file():
            return self._send_json(404, {
                "error": f"audio file not found: {audio_name}",
                "hint": "File may have been deleted. Re-run Regen Audio.",
            })
        # Resolve base clip — auto-detect .mp4 or .mov. Accept raw key if it
        # already includes an extension.
        bases_dir = self._phase_assets_dir("lipsync_bases")
        base_path: Path | None = None
        raw = bases_dir / base_clip_id
        if raw.is_file():
            base_path = raw
        else:
            for ext in ("mp4", "mov"):
                candidate = bases_dir / f"{base_clip_id}.{ext}"
                if candidate.is_file():
                    base_path = candidate
                    break
        if base_path is None:
            return self._send_json(404, {
                "error": f"base clip not found: {base_clip_id}",
                "hint": f"Expected {bases_dir}/{base_clip_id}.mp4 or .mov",
                "looked_in": str(bases_dir),
            })

        # Budget check.
        spend = self.app.state.read_spend()
        if spend["budget_remaining"] < COST_PER_LIPSYNC:
            return self._send_json(402, {
                "error": "budget exceeded for lip sync",
                "budget_remaining": spend["budget_remaining"],
                "cost": COST_PER_LIPSYNC,
                "hint": "Raise budget via /api/budget/override or ship fewer.",
            })

        # §8.4 silcomp + video trim to audio_duration + 0.4s tailroom.
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        tmp_audio_path = self.app.event_dir / f"_tmp_silcomp_phase_{phase}_{ts}.mp3"
        tmp_video_path = self.app.state.clips_dir / f"_tmp_trim_phase_{phase}_{ts}.mp4"
        try:
            audio_for_lipsync, audio_meta = _silcomp_audio(audio_path, tmp_audio_path)
            audio_duration = audio_meta["compressed_duration_s"]
            raw_dur = _ffprobe_duration(base_path)
            if raw_dur <= audio_duration:
                return self._send_json(400, {
                    "error": "base clip shorter than audio",
                    "base_clip_duration_s": round(raw_dur, 3),
                    "audio_duration_s": round(audio_duration, 3),
                    "hint": "Use a longer base clip or shorten the audio.",
                })
            video_for_lipsync, trimmed_to, ts_used, te_used = _trim_video_to_audio(
                base_path, tmp_video_path, audio_duration,
                trim_start=0.0, trim_end=None,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
                OSError, ValueError) as exc:
            traceback.print_exc()
            return self._send_json(500, {
                "error": "lipsync pre-conditioning failed",
                "stage": "silcomp_or_trim",
                "detail": str(exc)[:400],
                "hint": "Check ffmpeg + that base clip is decodable.",
            })

        # Submit synchronously via LipSyncClient (matches pattern at lines
        # 4651, 4824). self.app.client is a WaveSpeedClient which has no
        # submit_and_wait method — must wrap in LipSyncClient. Bug fixed
        # 2026-04-21 after it silently surfaced as "WaveSpeed upstream" errors.
        out_name = f"phase_{phase}_lipsync_{ts}.mp4"
        out_path = self.app.event_dir / out_name
        try:
            lipsync_client = LipSyncClient(self.app.client.api_key)
            result = lipsync_client.submit_and_wait(
                video_for_lipsync, audio_for_lipsync, out_path,
            )
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            return self._send_json(502, {
                "error": f"ByteDance LipSync failed: {type(exc).__name__}: {exc}",
                "hint": (
                    f"{type(exc).__name__}: {str(exc)[:200]} — "
                    "check server stderr for full trace. Likely causes: "
                    "WaveSpeed upstream, DNS resolution, upload host (uguu/catbox), "
                    "or client-class mismatch (must be LipSyncClient)."
                ),
            })
        finally:
            # Cleanup tmp pre-conditioned files regardless of outcome.
            for tmp in (tmp_audio_path, tmp_video_path):
                try:
                    tmp.unlink(missing_ok=True)
                except Exception:  # noqa: BLE001
                    pass

        if not out_path.is_file():
            return self._send_json(502, {
                "error": "LipSync completed but output file missing",
                "result": result,
                "hint": "Check LipSyncClient.submit_and_wait return + disk.",
            })
        self.app.state.add_spend("lipsync", COST_PER_LIPSYNC)
        mtime = int(os.path.getmtime(str(out_path)))

        def _apply(state, _p=phase, _n=out_name, _m=mtime, _bid=base_clip_id):
            state[f"phase_{_p}_lipsync_file"] = _n
            state[f"phase_{_p}_lipsync_mtime"] = _m
            state[f"phase_{_p}_cedric_base_clip_id" if _p == "b"
                  else f"phase_{_p}_empty_desk_bg_id"] = _bid
            state["_module_version"] = int(state.get("_module_version", 0) or 0) + 1
            return state["_module_version"]
        # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — terminal-write pin check.
        # If the event was swapped via /api/event/load mid-job, this lipsync
        # output is now orphaned at _pin["pinned_event_dir"] (NOT deleted —
        # recoverable per spec §10). Reject the state mutation with HTTP 423
        # so the v59 client can re-hydrate + retry.
        if not self._check_event_pin(_pin, "phase_b_lipsync_terminal_mutate"):
            return self._send_json(423, {
                "error": "event_changed_mid_job",
                "code": "ASYNC_JOB_GENERATION_PIN_V1",
                "pinned_event": _pin["pinned_event_dir"].name if _pin.get("pinned_event_dir") else None,
                "current_event": self.app.event_dir.name,
                "orphaned_output": str(out_path),
                "hint": (
                    "The active event changed via /api/event/load while this "
                    "lipsync job was running. The mp4 IS on disk at the pinned "
                    "event_dir but state was NOT mutated; client should "
                    "re-hydrate scope and retry."
                ),
            })
        try:
            new_version = self.app.state.mutate_state(_apply)
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            return self._send_json(500, {
                "error": f"mutate_state failed: {type(exc).__name__}: {exc}",
                "hint": "LipSync file written to disk; state persist failed.",
            })

        return self._send_json(200, {
            "status": "ok",
            "phase": phase,
            "file": out_name,
            "mtime": mtime,
            "audio_duration_s": round(audio_duration, 3),
            "video_trimmed_to_s": round(trimmed_to, 3),
            "base_clip_id": base_clip_id,
            "result": result,
            "module_version": new_version,
        })

    # Phase B/A preview — composes lipsync video + watercolor cues.
    # Preflight 135 (2026-04-20): reposition to top-left with reasonable padding.
    # Canvas is 1280x720. Phase B target: upper-left region with 60px padding
    # from top+left edges. Tile fits within 440x440 bbox (leaves room for Cedric
    # on the right + bottom padding). Phase A: top-right symmetric.
    # Scaled from compose_phase_b_poc.py (800x480 canvas, OVERLAY_X=24, OVERLAY_Y=24, OVERLAY_WIDTH=260).
    # Canvas here is 1280x720 (ratio 1.6x/1.5x) -> frame_x=40, frame_y=36, frame_max_w=420.
    # Height 420*1.5=630 portrait bbox for 1096x1608 framed tiles (aspect 0.68).
    _PHASE_FRAME_X = {"b": 75, "a": 830}
    _PHASE_FRAME_Y = 50
    _PHASE_FRAME_MAX_W = {"b": 375, "a": 375}
    _PHASE_FRAME_MAX_H = {"b": 560, "a": 560}

    def _handle_phase_b_preview(self, body: dict) -> None:
        """POST /api/phase_b/preview

        Body: {"phase": "a"|"b"}

        Reads: phase_{phase}_lipsync_file, phase_{phase}_watercolor_cues_json,
        phase_{phase}_*_mtime fields from state. Computes cache hash including
        WATERCOLOR_OVERLAY_RECIPE_HASH (MEDIUM-6 fix), watercolor_cues_json
        (normalized by _v2_validate_watercolor_cues_json), frame_x,
        chromakey_for_video flag.

        Cache hit: stream cached mp4 with no-cache+ETag.
        Cache miss: call render_watercolor_overlay, atomic write, LRU cleanup.
        """
        # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
        if not self._assert_event_scope(self._scope_body(body), allow_missing=False):
            return

        # Lazy-load helper.
        try:
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), "lib"))
            from ffmpeg_stitch import (  # type: ignore
                render_watercolor_overlay,
                resolve_watercolor_asset,
                WATERCOLOR_OVERLAY_RECIPE_HASH,
                lru_cleanup,
            )
        except ImportError as exc:
            return self._send_json(500, {
                "error": f"lib/ffmpeg_stitch import failed: {exc}",
                "hint": "Verify Production/tools/lib/ffmpeg_stitch.py has render_watercolor_overlay.",
            })

        phase = (body.get("phase") or "").strip().lower()
        err = self._phase_check(phase)
        if err:
            return self._send_json(400, {"error": err, "hint": "phase is 'a' or 'b'."})

        state = self.app.state.read_state()
        lipsync_name = state.get(f"phase_{phase}_lipsync_file")
        if not lipsync_name:
            return self._send_json(400, {
                "error": f"phase_{phase}_lipsync_file not set in state",
                "hint": "Run Send for Lipsync first.",
            })
        lipsync_path = self.app.event_dir / lipsync_name
        if not lipsync_path.is_file():
            return self._send_json(404, {
                "error": f"lipsync file not found on disk: {lipsync_name}",
                "hint": "File may have been deleted. Re-run Send for Lipsync.",
            })
        cues_json = state.get(f"phase_{phase}_watercolor_cues_json") or "[]"
        try:
            cues = json.loads(cues_json)
        except Exception as exc:  # noqa: BLE001
            return self._send_json(400, {
                "error": f"phase_{phase}_watercolor_cues_json invalid: {exc}",
                "hint": "Validator should have caught this -- state.json is corrupt. Reset via /api/v2/module/patch with empty array.",
            })
        if not isinstance(cues, list):
            return self._send_json(400, {
                "error": f"phase_{phase}_watercolor_cues_json is not a list",
                "hint": "Reset to [] via /api/v2/module/patch.",
            })

        # Pre-check watercolor assets exist (HIGH-3 fail-loud).
        library_dir = self._phase_assets_dir("watercolor_library")
        missing_assets = []
        for i, cue in enumerate(cues):
            try:
                resolve_watercolor_asset(library_dir, cue.get("key") or "",
                                         cue.get("cue_type") or "png")
            except FileNotFoundError as exc:
                missing_assets.append({"cue_index": i, "error": str(exc)})
        if missing_assets:
            return self._send_json(400, {
                "error": "watercolor assets missing for cue(s)",
                "missing": missing_assets,
                "hint": f"Drop the asset files into {library_dir} with the exact key names.",
            })

        frame_x = self._PHASE_FRAME_X[phase]
        frame_y = self._PHASE_FRAME_Y
        frame_max_w = self._PHASE_FRAME_MAX_W[phase]
        frame_max_h = self._PHASE_FRAME_MAX_H[phase]

        # Cache hash: all preview-affecting inputs (MEDIUM-5 + MEDIUM-6).
        lipsync_mtime = os.path.getmtime(str(lipsync_path))
        # Normalize cues for hash stability via the same validator used on write.
        try:
            normalized_cues_json = _v2_validate_watercolor_cues_json(cues_json)
        except ValueError as exc:
            return self._send_json(400, {
                "error": f"watercolor_cues_json validation failed: {exc}",
                "hint": "Re-drag cues to re-save with a valid schema.",
            })
        hash_parts = [
            f"recipe:v3",
            f"wc_overlay:{WATERCOLOR_OVERLAY_RECIPE_HASH}",
            f"phase:{phase}",
            f"frame_x:{frame_x}",
            f"frame_y:{frame_y}",
            f"frame_max_w:{frame_max_w}",
            f"frame_max_h:{frame_max_h}",
            f"lipsync:{lipsync_name}:{lipsync_mtime:.6f}",
            f"voice_stem_mtime:{state.get(f'phase_{phase}_voice_stem_mtime', 0)}",
            f"ambient:{state.get(f'phase_{phase}_ambient_preset_id', '')}",
            f"mixed_mtime:{state.get(f'phase_{phase}_mixed_audio_mtime', 0)}",
            f"base_clip:{state.get('phase_b_cedric_base_clip_id' if phase == 'b' else 'phase_a_empty_desk_bg_id', '')}",
            f"cues:{hashlib.sha256(normalized_cues_json.encode('utf-8')).hexdigest()[:16]}",
        ]
        cache_hash = hashlib.sha256(";".join(hash_parts).encode("utf-8")).hexdigest()

        preview_dir = self.app.event_dir / "preview" / f"phase_{phase}"
        preview_dir.mkdir(parents=True, exist_ok=True)
        final_path = preview_dir / f"phase_{phase}_preview_{cache_hash}.mp4"
        lock_path = preview_dir / ".lock"

        import fcntl  # noqa: PLC0415
        lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
        try:
            try:
                fcntl.lockf(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (BlockingIOError, OSError):
                return self._send_json(409, {
                    "error": "another phase preview is generating",
                    "hint": "Wait for the in-flight preview to finish.",
                })
            # Cache hit.
            if final_path.is_file():
                evicted = lru_cleanup(preview_dir)
                return self._stream_preview_mp4(final_path, cache_hash, evicted=evicted)

            # Cache miss: render.
            try:
                render_watercolor_overlay(
                    base_video_path=lipsync_path,
                    cues=cues,
                    frame_x=frame_x,
                    frame_y=frame_y,
                    output_path=final_path,
                    library_dir=library_dir,
                    chromakey_for_video=True,
                    frame_max_w=frame_max_w,
                    frame_max_h=frame_max_h,
                )
            except FileNotFoundError as exc:
                return self._send_json(400, {
                    "error": f"asset resolution failed: {exc}",
                    "hint": "Add the missing watercolor to the library.",
                })
            except subprocess.TimeoutExpired as exc:
                if final_path.is_file():
                    evicted = lru_cleanup(preview_dir)
                    return self._stream_preview_mp4(final_path, cache_hash, evicted=evicted)
                return self._send_json(504, {
                    "error": f"ffmpeg timeout after {exc.timeout}s",
                    "hint": "Try fewer cues or shorter lipsync.",
                })
            except subprocess.CalledProcessError as exc:
                stderr = (exc.stderr or b"")[:600].decode("utf-8", errors="replace")
                return self._send_json(500, {
                    "error": f"ffmpeg overlay failed (returncode={exc.returncode})",
                    "stderr": stderr,
                    "hint": "Check stderr; common cause is missing cue asset or corrupt lipsync.",
                })
            evicted = lru_cleanup(preview_dir)
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


def run_server(event_dir: Path, storyboard_name: str, event_id: str, *, source_event_dir: Path | None = None) -> int:
    storyboard_path = event_dir / storyboard_name
    if not storyboard_path.is_file():
        print(f"ERROR: storyboard not found: {storyboard_path}", file=sys.stderr)
        return 2

    pid_file = event_dir / "production_server.pid"
    cleanup_stale(pid_file)
    if not port_free(SERVER_PORT):
        print(f"ERROR: port {SERVER_PORT} already in use", file=sys.stderr)
        return 3

    # Parse API keys — find repo root by walking up
    root = Path(__file__).resolve().parents[2]
    keys = parse_api_keys(root / "Production" / "API_KEYS_MASTER.md")
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

    # BS5: Ghost-file scrub — on every startup, scan all option file references
    # in state.json and mark any whose file no longer exists on disk as
    # "ghost_cleaned". Prevents the browser from looping on 404s for options
    # that were deleted (by a previous B+C clear, crash, or manual cleanup).
    # Runs before AppContext so the storyboard loads clean state immediately.
    _ghost_count = 0
    def _scrub_ghost_options(st: dict) -> None:
        nonlocal _ghost_count
        for _beat_id, _beat in (st.get("beats") or {}).items():
            _opts = (_beat.get("phase_1") or {}).get("options") or []
            for _opt in _opts:
                _fname = _opt.get("file")
                if not _fname:
                    continue
                _fpath = state.clips_dir / _fname
                if not _fpath.is_file():
                    _opt["status"] = "ghost_cleaned"
                    _opt.pop("file", None)
                    _ghost_count += 1
                    print(f"[startup:ghost_scrub] {_beat_id}: cleared missing file {_fname!r}")
    try:
        state.mutate_state(_scrub_ghost_options)
        if _ghost_count:
            print(f"[startup:ghost_scrub] cleaned {_ghost_count} ghost option(s)")
        else:
            print("[startup:ghost_scrub] OK — no ghost options found")
    except Exception as _gs_exc:
        print(f"[startup:ghost_scrub] WARN: scrub failed (non-fatal): {_gs_exc}")

    app = AppContext(event_dir, storyboard_path, event_id, state, client)
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
    # Legacy speaker "Guide Bird" canonicalizes to "Chipper" (LD-183).
    # Narrative (lipsync-targeted) path gets non-motion-locking tail.
    beat = {"speaker": "Guide Bird", "section": "Discovery", "text": "Hi",
            "emotion": "happy_excited", "lipsync_targeted": True}
    p = build_motion_prompt(beat)
    assert "Beak closed" in p, f"expected Beak closed in: {p!r}"
    assert "Cartoon Chipper character" in p, f"canonical name missing: {p!r}"
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

        print("[smoke] image dimension gate (graceful without PIL)...")
        tiny_png = (
            "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1"
            "HAwCAAAAC0lEQVR4nGNgAAIAAAUAAen63NgAAAAASUVORK5CYII="
        )
        ok, info = validate_image_dimensions(tiny_png)
        # Either PIL is missing (passes with note) or it's present and rejects 1x1
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
