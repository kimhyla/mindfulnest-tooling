"""Vendor jobs (lipsync + voice profile) handlers — V59 Phase 4 Pass 2.

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

# V59 Phase 4 cross-review fix (body_key_contract CI failure):
# missing module-level variable references that need re-import.
from tools.production_server import (  # noqa: E402
    _VIDEO_TRIM_TAILROOM_S,
)

# Project-internal modules imported the same way production_server.py does.
# Handler bodies may reference any of these by bare name.
from lib.atomic_json_write import atomic_json_write
from lib.v3_partition import _iter_v3_beats
from lib.paths import DROPBOX_ROOT
import scope_router
from ffmpeg_utils import strip_audio as _strip_clip_audio
from lipsync_sender import LipSyncClient, COST_PER_LIPSYNC

# Late-resolvable private helpers from the host module.
from tools.production_server import (  # noqa: E402
    _async_log_lipsync_complete,
    _async_log_lipsync_submit,
    _ffprobe_duration,
    _find_beat_audio,
    _get_voice_directus_client,
    _load_voice_profiles_from_directus,
    _silcomp_audio,
    _trim_video_to_audio,
)

def handle_lipsync_submit(h, body: dict)-> None:

    """Submit lipsync with §8.4 pre-conditioning always applied.

    Body: {"beat": "beat_NN"} or {"beat": "beat_NN", "audio_override": "..."}
    """
    # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return

    # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — capture pin at entry; terminal writes assert via _check_event_pin.
    _pin = {
        "pinned_generation": h.app.event_generation,
        "pinned_event_dir": h.app.event_dir,
        "pinned_video_role": (body or {}).get("scope_video_role", "intro"),
        "_handler": '_handle_lipsync_submit',
    }
    # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — pre-work pin check (S2).
    # If the event was swapped via /api/event/load between scope-guard
    # and work start, abort BEFORE any expensive work begins.
    if not h._check_event_pin(_pin, '_handle_lipsync_submit_pre_work'):
        return h._send_error_v59(
                   423,
                   error_code="EVENT_CHANGED_PRE_WORK",
                   error_message="event_changed_pre_work",
                   retry_safe=False,
                   extra={"code": "ASYNC_JOB_GENERATION_PIN_V1", "handler": '_handle_lipsync_submit', "hint": "Event changed between scope-guard and work start. "
                "No work was done; no orphan output. Client should "
                "re-hydrate scope and retry."},
               )

    if h.app.client is None:
        return h._send_error_v59(
                   500,
                   error_code="WAVESPEED_NOT_CONFIGURED",
                   error_message="WaveSpeed client not configured (missing API key)",
                   retry_safe=True,
               )

    beat_key = body.get("beat") or body.get("beat_id")
    if not beat_key:
        return h._send_error_v59(
                   400,
                   error_code="MISSING_BEAT_BEAT_ID_FIELD",
                   error_message="missing 'beat'/'beat_id' field",
                   retry_safe=False,
               )

    video_role = (body or {}).get("scope_video_role") or (body or {}).get("scope_target_video") or "intro"

    state = h.app.state.read_state()
    beat_state = ((state.get("videos") or {}).get(video_role) or {}).get("beats", {}).get(beat_key)
    if not beat_state:
        return h._send_error_v59(
                   404,
                   error_code="GENERIC_ERROR",
                   error_message=f"beat '{beat_key}' not found in state",
                   retry_safe=False,
               )

    phase1 = beat_state.get("phase_1", {})
    selected = phase1.get("selected_option")
    if not selected:
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=f"no option selected for {beat_key}",
                   retry_safe=False,
               )

    options = phase1.get("options", [])
    if selected < 1 or selected > len(options):
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=f"selected_option {selected} out of range",
                   retry_safe=False,
               )
    clip_file = options[selected - 1].get("file")
    if not clip_file:
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=f"selected option has no file",
                   retry_safe=False,
               )

    source_clip_path = h.app.state.clips_dir / clip_file
    if not source_clip_path.is_file():
        return h._send_error_v59(
                   404,
                   error_code="GENERIC_ERROR",
                   error_message=f"clip file not found: {clip_file}",
                   retry_safe=False,
               )

    # LIPSYNC_TRIM_WINDOW_HONORED_20260419 — read user trim window from
    # storyboard. Absent/null fields collapse to old "whole-clip" behavior.
    # DELAY_FIX_20260522: UI "Delay" button writes phase_1.audio_delay, but
    # lipsync was only reading phase_1.trim_start — these map to the same
    # concept (video offset before audio starts). Fall back to audio_delay
    # so the delay is honoured at lipsync submission time.
    trim_start_raw = phase1.get("trim_start") if phase1.get("trim_start") is not None \
                     else phase1.get("audio_delay")
    trim_end_raw = phase1.get("trim_end")
    try:
        trim_start = float(trim_start_raw) if trim_start_raw is not None else 0.0
        trim_end = float(trim_end_raw) if trim_end_raw is not None else None
    except (TypeError, ValueError):
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=f"phase_1.trim_start/trim_end must be numeric",
                   retry_safe=False,
                   extra={"trim_start": trim_start_raw, "trim_end": trim_end_raw},
               )
    if trim_start < 0:
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=f"trim_start must be >= 0 (got {trim_start})",
                   retry_safe=False,
               )
    if trim_end is not None and trim_end <= trim_start:
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=f"trim_end ({trim_end}) must be > trim_start ({trim_start})",
                   retry_safe=False,
               )

    beat_num = int(beat_key.split("_")[1])
    source_audio_path = _find_beat_audio(
        h.app.event_dir, beat_key, body.get("audio_override"),
        app=h.app,
    )
    if not source_audio_path:
        return h._send_error_v59(
                   404,
                   error_code="GENERIC_ERROR",
                   error_message=f"no TTS audio found for {beat_key} (line_{beat_num:02d})",
                   retry_safe=False,
                   extra={"hint": "provide audio_override path or ensure TTS exists in story_scene_tts_v2/"},
               )

    # Budget check BEFORE ffmpeg work.
    spend = h.app.state.read_spend()
    if spend["budget_remaining"] < COST_PER_LIPSYNC:
        return h._send_error_v59(
                   402,
                   error_code="BUDGET_EXCEEDED_FOR_LIP_SYNC",
                   error_message="budget exceeded for lip sync",
                   retry_safe=False,
                   extra={"budget_remaining": spend["budget_remaining"], "cost": COST_PER_LIPSYNC},
               )

    # ------------------------------------------------------------------
    # §8.4 pre-conditioning (synchronous, fail-loud).
    # ------------------------------------------------------------------
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    tts_dir = h.app.event_dir / "story_scene_tts_v2"
    tmp_audio_path = tts_dir / f"_tmp_silcomp_{beat_key}_{ts}.mp3"
    tmp_video_path = h.app.state.clips_dir / f"_tmp_trim_{beat_key}_{ts}.mp4"

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
            return h._send_error_v59(
                       400,
                       error_code="GENERIC_ERROR",
                       error_message=f"trim_start={trim_start:.2f}s out of range",
                       retry_safe=False,
                       extra={"clip_duration_s": round(raw_dur, 3), "beat": beat_key},
                   )
        effective_end = trim_end if trim_end is not None else raw_dur
        # BUG FIX (2026-05-23): trim_back (relative seconds from end) overrides trim_end.
        # Client stores trim_back = user's typed value; server computes correct absolute end.
        trim_back_sec = phase1.get("trim_back")
        if trim_back_sec is not None:
            effective_end = max(trim_start + 0.01, raw_dur - float(trim_back_sec))
            print(f"[lipsync] trim_back={trim_back_sec:.2f}→effective_end={effective_end:.2f} "
                  f"(raw_dur={raw_dur:.2f})")
        elif effective_end > raw_dur + 0.05:
            print(f"[lipsync] WARN trim_end={effective_end:.2f} exceeds "
                  f"raw_dur={raw_dur:.2f} for {beat_key}; clamping")
            effective_end = raw_dur
        need = audio_duration + _VIDEO_TRIM_TAILROOM_S
        # BUG FIX (2026-05-23): the client computes trim_end = audio_duration - back_trim
        # instead of video_duration - back_trim. When audio is short relative to the
        # video clip (e.g. 6.88s audio on a 10s clip), this makes trim_end smaller than
        # audio_duration + tailroom and causes a spurious AUDIO_EXCEEDS_TRIM_WINDOW error.
        # Auto-extend effective_end to fit the audio when the RAW video has enough room.
        # Only fails now if the SOURCE VIDEO itself is too short for the audio.
        if need > effective_end - trim_start + 0.10:
            extended = trim_start + need
            if extended <= raw_dur + 0.10:
                print(f"[lipsync] auto-extending trim_end {effective_end:.2f}→{extended:.2f} "
                      f"(client trim_end too tight; raw_dur={raw_dur:.2f}, need={need:.2f})")
                effective_end = min(extended, raw_dur)
        window_len = effective_end - trim_start
        if need > window_len + 0.10:  # 100ms tolerance: Kling clips encode at ~10.042s not exactly 10.000s
            return h._send_error_v59(
                       400,
                       error_code="AUDIO_EXCEEDS_TRIM_WINDOW_INSUFFICIENT",
                       error_message="audio exceeds trim window (insufficient video for lipsync)",
                       retry_safe=False,
                       extra={"beat": beat_key, "audio_duration_s": round(audio_duration, 3), "tailroom_s": _VIDEO_TRIM_TAILROOM_S, "needed_s": round(need, 3), "trim_window_s": round(window_len, 3), "trim_start": round(trim_start, 3), "trim_end": round(effective_end, 3), "hint": "widen trim_end, move trim_start earlier, or shorten the TTS audio"},
                   )

        # LD LIPSYNC_MAX_DURATION_10S_NO_SILENCE_V1 (id=400, CLAUDE.md §8.5):
        # ByteDance LatentSync max training window = 10s. Longer = scene hallucination + watermark.
        _LIPSYNC_MAX_DUR = 10.0
        if audio_duration > _LIPSYNC_MAX_DUR:
            return h._send_error_v59(
                       400,
                       error_code="AUDIO_DURATION_EXCEEDS_BYTEDANCE_MAX",
                       error_message="audio_duration exceeds ByteDance max (10s)",
                       retry_safe=False,
                       extra={"audio_duration_s": round(audio_duration, 3), "max_duration_s": _LIPSYNC_MAX_DUR, "beat": beat_key, "rule": "LIPSYNC_MAX_DURATION_10S_NO_SILENCE_V1 (id=400)", "hint": "Use silence-split + passthrough protocol (CLAUDE.md §8.5): "
                    "split at silence boundaries, submit each speaking segment ≤10s "
                    "to ByteDance, passthrough original frames for silent portions, "
                    "then ffmpeg-concat and dub additional phrases as voice-over."},
                   )

        video_for_lipsync, trimmed_to, ts_used, te_used = _trim_video_to_audio(
            source_clip_path, tmp_video_path, audio_duration,
            trim_start=trim_start, trim_end=effective_end,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
            OSError, ValueError) as exc:
        traceback.print_exc()
        return h._send_error_v59(
                   500,
                   error_code="LIPSYNC_PRE_CONDITIONING_FAILED",
                   error_message="lipsync pre-conditioning failed",
                   retry_safe=True,
                   extra={"stage": "silcomp_or_trim", "detail": str(exc)[:500], "source_audio": source_audio_path.name, "source_clip": clip_file},
               )

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
                     _audio_name=audio_for_lipsync.name, _ap=audio_processing,
                     _role=video_role):
        beat = ((st.get("videos") or {}).get(_role) or {}).get("beats", {})[_bk]
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
    if not h._check_event_pin(_pin, "lipsync_submit_init_mutate"):
        return h._send_error_v59(
                   423,
                   error_code="EVENT_CHANGED_MID_JOB",
                   error_message="event_changed_mid_job",
                   retry_safe=False,
                   extra={"code": "ASYNC_JOB_GENERATION_PIN_V1"},
               )
    h.app.state.mutate_state(init_lipsync)

    # Rule 18 submit log.
    try:
        _async_log_lipsync_submit(
            event_id=getattr(h.app, "event_id", "unknown"),
            beat_id=beat_key, audio_processing=audio_processing,
            video_trimmed_to_s=trimmed_to, source_option=int(selected),
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[lipsync] submit-log failed (non-blocking): {exc}")

    # Background: submit pre-conditioned temps -> poll -> download.
    lipsync_client = LipSyncClient(h.app.client.api_key)

    def do_lipsync():
        try:
            task_id = lipsync_client.submit(video_for_lipsync, audio_for_lipsync)

            def set_polling(st, _bk=beat_key, _tid=task_id, _role=video_role):
                _ls = (((st.get("videos") or {}).get(_role) or {}).get("beats", {}).get(_bk) or {}).get("lipsync") or {}
                _ls["status"] = "polling"
                _ls["task_id"] = _tid
                _ls["submitted_at"] = datetime.now(timezone.utc).isoformat()
                _ls["submitted_at_epoch"] = int(time.time())
            h.app.state.mutate_state(set_polling)

            result = lipsync_client.poll_until_done(task_id)
            status = (result.get("status") or "").lower()

            if status == "completed" and result.get("outputs"):
                url = result["outputs"][0]
                dest_name = f"{beat_key}_lipsync.mp4"
                dest = h.app.state.clips_dir / dest_name
                size = lipsync_client.download(url, dest)

                # FACE-COMPOSITE: blend ByteDance output (face/beak lipsync region only)
                # with the original Kling source (clean wings/body). ByteDance LatentSync
                # was trained on human anatomy — cartoon wings in gesture poses get
                # "corrected" to look like human arms/hands. Masking the composite to the
                # face ellipse preserves lipsync where it matters and keeps wings clean.
                #
                # Enabled by default. Disable per beat: phase_1.lipsync_face_mask = false
                # Override mask (fraction of frame): phase_1.lipsync_face_mask =
                #   {"cx": 0.50, "cy": 0.42, "rx": 0.28, "ry": 0.26, "blur_px": 40}
                #
                # maskedmerge semantics: mask=255 (white) → use ByteDance pixel (face);
                #                        mask=0   (black) → use source pixel (wings/body)
                _face_mask_cfg = phase1.get("lipsync_face_mask", True)  # ON by default
                if _face_mask_cfg is not False:
                    _fc_src_tmp  = h.app.state.clips_dir / f"_tmp_{beat_key}_fc_src_{ts}.mp4"
                    _fc_out_tmp  = h.app.state.clips_dir / f"_tmp_{beat_key}_fc_out_{ts}.mp4"
                    _fc_mask_png = h.app.state.clips_dir / f"_tmp_{beat_key}_fc_mask_{ts}.png"
                    try:
                        from PIL import Image, ImageFilter, ImageDraw
                        # Probe ByteDance output for exact dimensions + fps
                        _fc_probe = subprocess.run(
                            ["ffprobe", "-v", "error", "-select_streams", "v:0",
                             "-show_entries", "stream=width,height,r_frame_rate",
                             "-of", "csv=p=0", str(dest)],
                            capture_output=True, text=True, timeout=10,
                        )
                        _fc_w, _fc_h, _fc_fps_str = 720, 544, "25"
                        _fc_dur = _ffprobe_duration(dest)
                        _fc_pparts = _fc_probe.stdout.strip().split(",")
                        if len(_fc_pparts) >= 3:
                            try:
                                _fc_w = int(_fc_pparts[0])
                                _fc_h = int(_fc_pparts[1])
                                _frac = _fc_pparts[2].strip()
                                if "/" in _frac:
                                    _n, _d = _frac.split("/", 1)
                                    _fc_fps_str = f"{int(_n)/max(int(_d),1):.6f}"
                                else:
                                    _fc_fps_str = _frac
                            except (ValueError, ZeroDivisionError):
                                pass
                        # Read mask config (per-beat override or defaults for Chipper)
                        if isinstance(_face_mask_cfg, dict):
                            _fc_cx_p = float(_face_mask_cfg.get("cx", 0.50))
                            _fc_cy_p = float(_face_mask_cfg.get("cy", 0.42))
                            _fc_rx_p = float(_face_mask_cfg.get("rx", 0.28))
                            _fc_ry_p = float(_face_mask_cfg.get("ry", 0.26))
                            _fc_blur = int(_face_mask_cfg.get("blur_px", 40))
                        else:
                            _fc_cx_p, _fc_cy_p = 0.50, 0.42
                            _fc_rx_p, _fc_ry_p = 0.28, 0.26
                            _fc_blur = 40
                        _fc_cx = int(_fc_cx_p * _fc_w)
                        _fc_cy = int(_fc_cy_p * _fc_h)
                        _fc_rx = int(_fc_rx_p * _fc_w)
                        _fc_ry = int(_fc_ry_p * _fc_h)
                        # Build soft elliptical face mask image
                        _fc_mask_img = Image.new("L", (_fc_w, _fc_h), 0)
                        _fc_mask_draw = ImageDraw.Draw(_fc_mask_img)
                        _fc_mask_draw.ellipse(
                            [_fc_cx - _fc_rx, _fc_cy - _fc_ry,
                             _fc_cx + _fc_rx, _fc_cy + _fc_ry], fill=255)
                        _fc_mask_img = _fc_mask_img.filter(
                            ImageFilter.GaussianBlur(radius=_fc_blur))
                        _fc_mask_img.save(str(_fc_mask_png))
                        # Scale original source to ByteDance dimensions + fps, video-only
                        subprocess.run([
                            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                            "-ss", "0", "-t", f"{_fc_dur:.3f}",
                            "-i", str(source_clip_path),
                            "-vf", (f"scale={_fc_w}:{_fc_h}:flags=lanczos,"
                                    f"fps={_fc_fps_str},format=yuv420p"),
                            "-an",
                            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                            str(_fc_src_tmp),
                        ], check=True, capture_output=True, timeout=120)
                        # Composite: source wings + ByteDance face, audio from ByteDance
                        subprocess.run([
                            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                            "-i", str(_fc_src_tmp),            # [0] base: clean source
                            "-i", str(dest),                   # [1] overlay: ByteDance
                            "-loop", "1", "-i", str(_fc_mask_png),  # [2] static mask
                            "-filter_complex",
                            f"[2:v]scale={_fc_w}:{_fc_h}[msk];"
                            "[0:v][1:v][msk]maskedmerge[v]",
                            "-map", "[v]", "-map", "1:a",
                            "-t", f"{_fc_dur:.3f}",
                            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                            "-pix_fmt", "yuv420p", "-c:a", "copy",
                            str(_fc_out_tmp),
                        ], check=True, capture_output=True, timeout=120)
                        _fc_out_tmp.replace(dest)
                        size = dest.stat().st_size
                        print(f"[lipsync] {beat_key} face-composite OK: "
                              f"cx={_fc_cx_p:.2f} cy={_fc_cy_p:.2f} "
                              f"rx={_fc_rx_p:.2f} ry={_fc_ry_p:.2f} "
                              f"blur={_fc_blur}px @ {_fc_w}×{_fc_h}")
                    except Exception as _fce:
                        print(f"[lipsync] {beat_key} face-composite FAILED (non-fatal): {_fce}")
                        import traceback as _tb2; _tb2.print_exc()
                    finally:
                        for _f in (_fc_src_tmp, _fc_out_tmp, _fc_mask_png):
                            try: _f.unlink()
                            except (OSError, UnboundLocalError): pass

                # TAIL-APPEND: preserve original Kling animation frames that
                # come after the lipsync trim window. Without this, the
                # character freezes on the last lipsync frame for the
                # remainder of the beat's hold duration.
                # e.g. 1.52s audio + 1.5s trim target = 3.02s sent to
                # ByteDance; original clip is 5.04s → 2.02s of natural
                # Kling motion was discarded. We concat it back on.
                #
                # FIX 2026-05-23: ByteDance downscales the video (e.g. 1660×1244
                # Kling → 720×544 ByteDance) and outputs 25fps not 24fps. The tail
                # extracted from the Kling source must be scaled+fps-matched to the
                # ByteDance output params, and a silent stereo audio track added
                # (Kling clips are video-only; ByteDance output has stereo AAC).
                # Without this, the concat demuxer fails on stream-param mismatch.
                _tail_start_s = trimmed_to
                _tail_avail_s = raw_dur - _tail_start_s
                if _tail_avail_s > 0.15:
                    _tail_tmp = h.app.state.clips_dir / f"_tmp_{beat_key}_tail_{ts}.mp4"
                    _concat_txt = h.app.state.clips_dir / f"_tmp_{beat_key}_clist_{ts}.txt"
                    _ls_ext = h.app.state.clips_dir / f"_tmp_{beat_key}_ls_ext_{ts}.mp4"
                    try:
                        # 0. Probe ByteDance output for its actual width/height/fps
                        #    so the tail is encoded to exactly matching params.
                        _ls_probe = subprocess.run(
                            ["ffprobe", "-v", "error",
                             "-select_streams", "v:0",
                             "-show_entries", "stream=width,height,r_frame_rate",
                             "-of", "csv=p=0",
                             str(dest)],
                            capture_output=True, text=True, timeout=10,
                        )
                        _ls_w, _ls_h, _ls_fps_str = 720, 544, "25"
                        _probe_parts = _ls_probe.stdout.strip().split(",")
                        if len(_probe_parts) >= 3:
                            try:
                                _ls_w = int(_probe_parts[0])
                                _ls_h = int(_probe_parts[1])
                                # r_frame_rate is "25/1" or "3097600/119173" — convert to decimal
                                _fps_frac = _probe_parts[2].strip()
                                if "/" in _fps_frac:
                                    _n, _d = _fps_frac.split("/", 1)
                                    _ls_fps_str = f"{int(_n)/max(int(_d),1):.6f}"
                                else:
                                    _ls_fps_str = _fps_frac
                            except (ValueError, ZeroDivisionError):
                                pass  # fall back to 720×544 25fps defaults
                        # 1. Extract tail from original Kling clip, scaled to match
                        #    ByteDance output dimensions + fps. Add silent stereo
                        #    audio (anullsrc) because Kling clips are video-only but
                        #    ByteDance output carries stereo AAC.
                        subprocess.run([
                            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                            "-ss", f"{_tail_start_s:.3f}",
                            "-i", str(source_clip_path),
                            "-f", "lavfi", "-t", f"{_tail_avail_s + 0.1:.3f}",
                            "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                            "-filter_complex",
                            f"[0:v]scale={_ls_w}:{_ls_h}:flags=lanczos,"
                            f"fps={_ls_fps_str},format=yuv420p[vout]",
                            "-map", "[vout]", "-map", "1:a",
                            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                            "-c:a", "aac", "-b:a", "128k", "-ac", "2", "-ar", "44100",
                            "-shortest",
                            str(_tail_tmp),
                        ], check=True, capture_output=True, timeout=60)
                        # 2. Write concat list
                        _concat_txt.write_text(
                            f"file '{dest.resolve()}'\nfile '{_tail_tmp.resolve()}'\n"
                        )
                        # 3. Concat (copy — streams now have matching params)
                        subprocess.run([
                            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                            "-f", "concat", "-safe", "0", "-i", str(_concat_txt),
                            "-c", "copy", str(_ls_ext),
                        ], check=True, capture_output=True, timeout=120)
                        # 4. Replace lipsync dest with extended version
                        _ls_ext.replace(dest)
                        size = dest.stat().st_size
                        print(f"[lipsync] {beat_key} tail-append OK: "
                              f"+{_tail_avail_s:.2f}s "
                              f"(scaled {_ls_w}×{_ls_h}@{_ls_fps_str}fps) "
                              f"→ total {_ffprobe_duration(dest):.2f}s")
                    except Exception as _te:
                        print(f"[lipsync] {beat_key} tail-append FAILED (non-fatal): {_te}")
                        import traceback as _tb; _tb.print_exc()
                    finally:
                        for _f in (_tail_tmp, _concat_txt, _ls_ext):
                            try: _f.unlink()
                            except OSError: pass

                # HOLD-LAST-FRAME: if phase_1.lipsync_hold_tail_s is set, freeze
                # the last video frame for that many seconds after the tail ends.
                # Use case: explosion/whiteout clips where the final frame should
                # linger visually (e.g. beat_11 whiteout — set hold=2.5 so the
                # full-screen burst is held for 2.5s before cut).
                _hold_s = phase1.get("lipsync_hold_tail_s")
                if _hold_s and float(_hold_s) > 0.05:
                    _held_out = h.app.state.clips_dir / f"_tmp_{beat_key}_held_{ts}.mp4"
                    try:
                        subprocess.run([
                            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                            "-i", str(dest),
                            "-vf", f"tpad=stop_mode=clone:stop_duration={float(_hold_s):.2f}",
                            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                            "-pix_fmt", "yuv420p",
                            "-c:a", "aac", "-b:a", "128k", "-ac", "2", "-ar", "44100",
                            str(_held_out),
                        ], check=True, capture_output=True, timeout=120)
                        _held_out.replace(dest)
                        size = dest.stat().st_size
                        print(f"[lipsync] {beat_key} hold-last-frame OK: "
                              f"+{float(_hold_s):.1f}s → total {_ffprobe_duration(dest):.2f}s")
                    except Exception as _he:
                        print(f"[lipsync] {beat_key} hold-last-frame FAILED (non-fatal): {_he}")
                    finally:
                        try: _held_out.unlink()
                        except (OSError, UnboundLocalError): pass

                def mark_done(st, _bk=beat_key, _fn=dest_name, _sz=size, _role=video_role):
                    beat = ((st.get("videos") or {}).get(_role) or {}).get("beats", {})[_bk]
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
                    # Auto-promote 🏁 FINAL to lipsync: lipsync IS the canonical
                    # stitcher source once it completes. Preserve prior final in
                    # auto_promoted_from for audit/undo trail.
                    prior_final = beat.get("final") or {}
                    if prior_final.get("source") != "lipsync":
                        beat["final"] = {
                            "source": "lipsync",
                            "source_option": src_opt,
                            "file": _fn,
                            "approved_at": datetime.now(timezone.utc).isoformat(),
                            "auto_promoted_from": (
                                {k: prior_final.get(k) for k in ("source", "source_option", "file", "image_path")}
                                if prior_final else None
                            ),
                        }
                h.app.state.mutate_state(mark_done)
                h.app.state.add_spend("lipsync", COST_PER_LIPSYNC)
                print(f"[lipsync] {beat_key} COMPLETED -> {dest_name} ({size} bytes)")

                # Cleanup temps on success (preserve on failure for debugging).
                if silcomp_applied:
                    try: tmp_audio_path.unlink()
                    except OSError: pass
                try: tmp_video_path.unlink()
                except OSError: pass

                try:
                    _async_log_lipsync_complete(
                        event_id=getattr(h.app, "event_id", "unknown"),
                        beat_id=beat_key, output_file=dest_name, size_bytes=size,
                    )
                except Exception as exc:  # noqa: BLE001
                    print(f"[lipsync] complete-log failed (non-blocking): {exc}")
            else:
                def mark_failed(st, _bk=beat_key, _err=str(result), _role=video_role):
                    ls = (((st.get("videos") or {}).get(_role) or {}).get("beats", {}).get(_bk) or {}).get("lipsync") or {}
                    ls["status"] = "failed"
                    ls["last_error"] = _err[:500]
                h.app.state.mutate_state(mark_failed)
                print(f"[lipsync] {beat_key} FAILED (no charge, temps preserved): {result}")

        except Exception as exc:
            traceback.print_exc()
            def mark_err(st, _bk=beat_key, _err=str(exc), _role=video_role):
                _ls = (((st.get("videos") or {}).get(_role) or {}).get("beats", {}).get(_bk) or {}).get("lipsync") or {}
                _ls["status"] = "failed"
                _ls["last_error"] = _err[:500]
            h.app.state.mutate_state(mark_err)

    threading.Thread(target=do_lipsync, daemon=True, name=f"lipsync-{beat_key}").start()

    h._send_json(200, {
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


def handle_lipsync_submit_legacy(h, body: dict)-> None:

    """LEGACY (pre-§8.4). Preserved April 17 2026 for fallback.

    Direct ByteDance submission with NO audio pre-conditioning, NO video
    trim. Unwired from the router — kept as debuggable reference.
    """
    # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return

    # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — capture pin at entry; terminal writes assert via _check_event_pin.
    _pin = {
        "pinned_generation": h.app.event_generation,
        "pinned_event_dir": h.app.event_dir,
        "pinned_video_role": (body or {}).get("scope_video_role", "intro"),
        "_handler": '_handle_lipsync_submit_legacy',
    }
    # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — pre-work pin check (S2).
    # If the event was swapped via /api/event/load between scope-guard
    # and work start, abort BEFORE any expensive work begins.
    if not h._check_event_pin(_pin, '_handle_lipsync_submit_legacy_pre_work'):
        return h._send_error_v59(
                   423,
                   error_code="EVENT_CHANGED_PRE_WORK",
                   error_message="event_changed_pre_work",
                   retry_safe=False,
                   extra={"code": "ASYNC_JOB_GENERATION_PIN_V1", "handler": '_handle_lipsync_submit_legacy', "hint": "Event changed between scope-guard and work start. "
                "No work was done; no orphan output. Client should "
                "re-hydrate scope and retry."},
               )

    if h.app.client is None:
        return h._send_error_v59(
                   500,
                   error_code="WAVESPEED_NOT_CONFIGURED",
                   error_message="WaveSpeed client not configured (missing API key)",
                   retry_safe=True,
               )

    beat_key = body.get("beat") or body.get("beat_id")
    if not beat_key:
        return h._send_error_v59(
                   400,
                   error_code="MISSING_BEAT_BEAT_ID_FIELD",
                   error_message="missing 'beat'/'beat_id' field",
                   retry_safe=False,
               )

    video_role = (body or {}).get("scope_video_role") or (body or {}).get("scope_target_video") or "intro"

    # Read state to find the selected clip
    state = h.app.state.read_state()
    beat_state = ((state.get("videos") or {}).get(video_role) or {}).get("beats", {}).get(beat_key)
    if not beat_state:
        return h._send_error_v59(
                   404,
                   error_code="GENERIC_ERROR",
                   error_message=f"beat '{beat_key}' not found in state",
                   retry_safe=False,
               )

    phase1 = beat_state.get("phase_1", {})
    selected = phase1.get("selected_option")
    if not selected:
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=f"no option selected for {beat_key}",
                   retry_safe=False,
               )

    # Find the selected clip file
    options = phase1.get("options", [])
    if selected < 1 or selected > len(options):
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=f"selected_option {selected} out of range",
                   retry_safe=False,
               )
    clip_file = options[selected - 1].get("file")
    if not clip_file:
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=f"selected option has no file",
                   retry_safe=False,
               )

    clip_path = h.app.state.clips_dir / clip_file
    if not clip_path.is_file():
        return h._send_error_v59(
                   404,
                   error_code="GENERIC_ERROR",
                   error_message=f"clip file not found: {clip_file}",
                   retry_safe=False,
               )

    # Find TTS audio — uses shared _find_beat_audio helper
    # (extracted April 16 2026 for reuse by animation-duration inference).
    beat_num = int(beat_key.split("_")[1])
    audio_path = _find_beat_audio(
        h.app.event_dir, beat_key, body.get("audio_override"),
        app=h.app,
    )
    if not audio_path:
        return h._send_error_v59(
                   404,
                   error_code="GENERIC_ERROR",
                   error_message=f"no TTS audio found for {beat_key} (line_{beat_num:02d})",
                   retry_safe=False,
                   extra={"hint": "provide audio_override path or ensure TTS exists in story_scene_tts_v2/"},
               )

    # Budget check
    spend = h.app.state.read_spend()
    if spend["budget_remaining"] < COST_PER_LIPSYNC:
        return h._send_error_v59(
                   402,
                   error_code="BUDGET_EXCEEDED_FOR_LIP_SYNC",
                   error_message="budget exceeded for lip sync",
                   retry_safe=False,
                   extra={"budget_remaining": spend["budget_remaining"], "cost": COST_PER_LIPSYNC},
               )

    # Initialize lipsync state in production_state.
    # Tier 5 (decision 153 LIPSYNC_UI_MUST_SUPPORT_RERUN, April 17 2026):
    # Record which option the submission was sourced from, and clear the
    # source_changed flag. _handle_select compares new selected_option
    # against this source_option on every selection change and sets
    # source_changed=True if they differ. The client surfaces a
    # "🔁 Re-run Lip Sync" affordance when source_changed is true.
    def init_lipsync(st, _bk=beat_key, _src=int(selected), _role=video_role):
        beat = ((st.get("videos") or {}).get(_role) or {}).get("beats", {})[_bk]
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
    h.app.state.mutate_state(init_lipsync)

    # Submit in background thread
    lipsync_client = LipSyncClient(h.app.client.api_key)

    def do_lipsync():
        try:
            task_id = lipsync_client.submit(clip_path, audio_path)

            def set_polling(st, _bk=beat_key, _tid=task_id, _role=video_role):
                _ls = (((st.get("videos") or {}).get(_role) or {}).get("beats", {}).get(_bk) or {}).get("lipsync") or {}
                _ls["status"] = "polling"
                _ls["task_id"] = _tid
                _ls["submitted_at"] = datetime.now(timezone.utc).isoformat()
                _ls["submitted_at_epoch"] = int(time.time())
            # LD-460 — pin check before set_polling mutate_state (thread closure).
            if not h._check_event_pin(_pin, "lipsync_submit_legacy_set_polling"):
                print("[lipsync_submit_legacy] event drift mid-thread; skipping mutate_state", flush=True)
                return
            h.app.state.mutate_state(set_polling)

            # Poll until done
            result = lipsync_client.poll_until_done(task_id)
            status = (result.get("status") or "").lower()

            if status == "completed" and result.get("outputs"):
                url = result["outputs"][0]
                dest_name = f"{beat_key}_lipsync.mp4"
                dest = h.app.state.clips_dir / dest_name
                size = lipsync_client.download(url, dest)

                def mark_done(st, _bk=beat_key, _fn=dest_name, _sz=size, _role=video_role):
                    beat = ((st.get("videos") or {}).get(_role) or {}).get("beats", {})[_bk]
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
                    # Auto-promote 🏁 FINAL to lipsync (legacy path parity).
                    prior_final = beat.get("final") or {}
                    if prior_final.get("source") != "lipsync":
                        beat["final"] = {
                            "source": "lipsync",
                            "source_option": src_opt,
                            "file": _fn,
                            "approved_at": datetime.now(timezone.utc).isoformat(),
                            "auto_promoted_from": (
                                {k: prior_final.get(k) for k in ("source", "source_option", "file", "image_path")}
                                if prior_final else None
                            ),
                        }
                h.app.state.mutate_state(mark_done)
                h.app.state.add_spend("lipsync", COST_PER_LIPSYNC)
                print(f"[lipsync] {beat_key} COMPLETED -> {dest_name} ({size} bytes)")
            else:
                def mark_failed(st, _bk=beat_key, _err=str(result), _role=video_role):
                    ls = (((st.get("videos") or {}).get(_role) or {}).get("beats", {}).get(_bk) or {}).get("lipsync") or {}
                    ls["status"] = "failed"
                    ls["last_error"] = _err[:500]
                h.app.state.mutate_state(mark_failed)
                # No spend charge on failure — WaveSpeed doesn't bill failed jobs
                print(f"[lipsync] {beat_key} FAILED (no charge): {result}")

        except Exception as exc:
            traceback.print_exc()
            def mark_err(st, _bk=beat_key, _err=str(exc), _role=video_role):
                _ls = (((st.get("videos") or {}).get(_role) or {}).get("beats", {}).get(_bk) or {}).get("lipsync") or {}
                _ls["status"] = "failed"
                _ls["last_error"] = _err[:500]
            h.app.state.mutate_state(mark_err)

    threading.Thread(target=do_lipsync, daemon=True, name=f"lipsync-{beat_key}").start()

    h._send_json(200, {
        "status": "submitted",
        "beat": beat_key,
        "clip": clip_file,
        "audio": audio_path.name,
        "cost": COST_PER_LIPSYNC,
        "message": f"Lip sync job submitted for {beat_key}. Poll /api/lipsync/status for updates.",
    })


def handle_lipsync_status(h)-> None:

    """Return lip sync status for all beats.

    source_option + source_changed (Tier 5, decision 153 April 17 2026):
    When a completed lipsync's source_changed is true, the client should
    render a "🔁 Re-run Lip Sync" affordance instead of the preview
    toggle. This closes the "button locks to Done even after the source
    clip changes" bug class.
    """
    state = h.app.state.read_state()
    lipsync_beats = {}
    # v3 state: scan ALL video partitions (intro, resolution, …), not just intro.
    for _role, partition in (state.get("videos") or {}).items():
        for beat_id, beat in (partition.get("beats") or {}).items():
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

    h._send_json(200, {
        "beats": lipsync_beats,
        "summary": {
            "total": total,
            "completed": completed,
            "polling": polling,
            "failed": failed,
        },
    })


def handle_voice_profile_get(h, pid_raw: str)-> None:

    """GET /api/voice/profile/<id> — read prod_voice_profiles by id.

    Returns the current stability / similarity_boost / style /
    character_name so the panel can hydrate sliders from the
    single source of truth.
    """
    try:
        pid = int(pid_raw)
    except (TypeError, ValueError):
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=f"profile id must be integer, got {pid_raw!r}",
                   retry_safe=False,
                   extra={"hint": "Try /api/voice/profile/2 (Chipper)."},
               )
    if pid not in h._VOICE_PROFILE_GET_ALLOWED_IDS:
        return h._send_error_v59(
                   403,
                   error_code="GENERIC_ERROR",
                   error_message=f"profile id {pid} not in read allow-list "
                     f"{sorted(h._VOICE_PROFILE_GET_ALLOWED_IDS)}",
                   retry_safe=False,
                   extra={"hint": "Phase A panel scope: Chipper=2."},
               )
    try:
        c = _get_voice_directus_client()
        r = c._request("GET", f"/items/prod_voice_profiles/{pid}")
    except Exception as exc:  # noqa: BLE001
        return h._send_error_v59(
                   502,
                   error_code="GENERIC_ERROR",
                   error_message=f"Directus read failed: {type(exc).__name__}: {exc}",
                   retry_safe=True,
                   extra={"hint": "Check Directus connectivity / credentials."},
               )
    data = (r or {}).get("data") or {}
    if not data:
        return h._send_error_v59(
                   404,
                   error_code="GENERIC_ERROR",
                   error_message=f"prod_voice_profiles id={pid} not found",
                   retry_safe=False,
               )
    return h._send_json(200, {
        "id": data.get("id"),
        "character_name": data.get("character_name"),
        "stability": data.get("stability"),
        "similarity_boost": data.get("similarity_boost"),
        "style": data.get("style"),
        "speed": data.get("speed"),
        "model": data.get("model"),
        "elevenlabs_voice_id": data.get("elevenlabs_voice_id"),
    })


def handle_voice_profile_update(h, body: dict)-> None:

    """POST /api/voice/profile_update — persist slider changes.

    Body: {"id": 2, "stability": 0.25, "similarity_boost": 0.75,
           "style": 0.55}

    Validates id is in allow-list, fields are floats in [0.0, 1.0],
    PATCHes Directus prod_voice_profiles by id, then force-refreshes
    the in-process voice cache so the next /api/phase_b/regen_audio
    call uses the new settings.
    """
    if not isinstance(body, dict):
        return h._send_error_v59(
                   400,
                   error_code="INVALID_REQUEST_BODY",
                   error_message="body must be JSON object",
                   retry_safe=False,
               )
    try:
        pid = int(body.get("id"))
    except (TypeError, ValueError):
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=f"id required and must be integer; got {body.get('id')!r}",
                   retry_safe=False,
                   extra={"hint": "Phase A panel posts id=2 (Chipper)."},
               )
    if pid not in h._VOICE_PROFILE_PATCH_ALLOWED_IDS:
        return h._send_error_v59(
                   403,
                   error_code="GENERIC_ERROR",
                   error_message=f"profile id {pid} not in WRITE allow-list "
                     f"{sorted(h._VOICE_PROFILE_PATCH_ALLOWED_IDS)}",
                   retry_safe=False,
                   extra={"hint": "Phase A panel writes Chipper (id=2) only. "
                    "Cedric (id=1) and Tessa (id=3) are not editable "
                    "from this route per Phase 0 verdict."},
               )
    # Build patch payload from whitelisted fields only.
    patch: dict = {}
    for field in h._VOICE_PROFILE_ALLOWED_FIELDS:
        if field not in body:
            continue
        raw = body.get(field)
        try:
            v = float(raw)
        except (TypeError, ValueError):
            return h._send_error_v59(
                       400,
                       error_code="GENERIC_ERROR",
                       error_message=f"{field} must be number, got {raw!r}",
                       retry_safe=False,
                   )
        if not (0.0 <= v <= 1.0):
            return h._send_error_v59(
                       400,
                       error_code="GENERIC_ERROR",
                       error_message=f"{field} out of range [0.0, 1.0]: {v}",
                       retry_safe=False,
                       extra={"hint": "ElevenLabs voice settings are 0..1 floats."},
                   )
        # Round to 2 decimals — slider step is 0.01 client-side; round
        # tighter than that and we silently destroy any historical 3+
        # decimal value Kim retunes via Directus UI directly. Counter-
        # agent F6 fix: was round(v, 4), now matches client precision.
        patch[field] = round(v, 2)
    if not patch:
        return h._send_error_v59(
                   400,
                   error_code="NO_WHITELISTED_FIELDS_IN_BODY",
                   error_message="no whitelisted fields in body",
                   retry_safe=False,
                   extra={"hint": f"Allowed: {sorted(h._VOICE_PROFILE_ALLOWED_FIELDS)}"},
               )
    # PATCH Directus via cached client (counter-agent F4 fix: was
    # creating a fresh client + load_credentials() per request, which
    # hammers Doppler/disk on every slider change).
    try:
        c = _get_voice_directus_client()
        r = c._request("PATCH", f"/items/prod_voice_profiles/{pid}", data=patch)
    except Exception as exc:  # noqa: BLE001
        return h._send_error_v59(
                   502,
                   error_code="GENERIC_ERROR",
                   error_message=f"Directus PATCH failed: {type(exc).__name__}: {exc}",
                   retry_safe=True,
                   extra={"hint": "Slider value not persisted. Retry; check Directus."},
               )
    # Force-refresh the in-process cache so the next regen sees the new
    # values (avoids stale-cache drift; counter Phase 0 C2 mitigation).
    try:
        _load_voice_profiles_from_directus(force_refresh=True)
    except Exception as exc:  # noqa: BLE001
        print(f"[voice-profile-update] WARN cache reload failed: {exc}",
              file=sys.stderr)
    data = (r or {}).get("data") or {}
    return h._send_json(200, {
        "ok": True,
        "id": data.get("id", pid),
        "character_name": data.get("character_name"),
        "stability": data.get("stability"),
        "similarity_boost": data.get("similarity_boost"),
        "style": data.get("style"),
        "patched_fields": sorted(patch.keys()),
    })


