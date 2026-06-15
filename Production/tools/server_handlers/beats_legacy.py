"""Legacy beat handlers — V59 Phase 4 Pass 2.

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
    _GRAFT_DEDUP,
    _GRAFT_DEDUP_MAX,
)

# Project-internal modules imported the same way production_server.py does.
# Handler bodies may reference any of these by bare name.
from lib.atomic_json_write import atomic_json_write
from lib.v3_partition import _iter_v3_beats
from lib.paths import DROPBOX_ROOT

# V59 Phase 4 cross-review fix (CI follow-up):
# missing module-level references from extracted handler bodies.
from tools.production_server import (  # noqa: E402
    KLING_MAX_DURATION_SEC,
    TIER1A_DEBOUNCE_WINDOW_SEC,
    TIER1A_ENABLED,
)
import scope_router
from ffmpeg_utils import strip_audio as _strip_clip_audio
from lipsync_sender import LipSyncClient, COST_PER_LIPSYNC

# Late-resolvable private helpers from the host module.
from tools.production_server import (  # noqa: E402
    _async_log_text_update,
    _audit_log_path,
    _bg_module,
    _canonicalize_speaker,
    _find_beat_audio,
    _patch_storyboard_L_field,
    _resolve_beat_speaker,
    _resolve_module_id_for_state,
    _t1_enabled,
    _tier1a_async_log_debounce,
    _tier1a_debounce_should_skip,
    _tier1a_mark_regen_fired,
    _tier1a_should_audit,
    _tts_regenerate_for_beat,
    _write_sidecar_L_json,
    patch_state,
)

def handle_beat_accepted_bg(h)-> None:

    """GET /api/beat/accepted-bg?beat_id=X -> { ok, bg_url, bg_path }
    Returns the absolute server-URL for the currently accepted still image
    of a beat generator beat. Authoritative: reads sidecar + flux_options.
    """
    import urllib.parse as _up
    qs = _up.parse_qs(_up.urlparse(h.path).query)
    beat_id = (qs.get("beat_id") or [None])[0]
    if not beat_id:
        return h._send_error_v59(
                   400,
                   error_code="MISSING_BEAT_ID",
                   error_message="beat_id required",
                   retry_safe=False,
                   extra={"ok": False},
               )
    try:
        import os as _os
        bg = _bg_module()
        with bg._sidecar_lock:
            sidecar = bg.read_sidecar()
            sidecar = bg._migrate_sidecar(sidecar)
            _, beat = bg.find_beat(sidecar, beat_id)
        if not beat:
            return h._send_error_v59(
                       404,
                       error_code="GENERIC_ERROR",
                       error_message=f"beat {beat_id} not found",
                       retry_safe=False,
                       extra={"ok": False},
                   )
        key = beat.get("accepted_image_key")
        # Fall back to reference_image / bg_ref_image (drag-from-sources path)
        if not key:
            ref = beat.get("reference_image") or beat.get("bg_ref_image")
            if ref and _os.path.isfile(ref):
                import urllib.parse as _up3
                bg_url = f"/files?path={_up3.quote(ref)}"
                return h._send_json(200, {"ok": True, "bg_url": bg_url, "bg_path": ref})
        # Fall back to first populated flux_option
        if not key:
            for opt in beat.get("flux_options", []) or []:
                if opt and opt.get("key"):
                    key = opt["key"]
                    break
        if not key:
            return h._send_error_v59(
                       404,
                       error_code="GENERIC_ERROR",
                       error_message=f"No image found for beat {beat_id} — place an image in Option 1 first",
                       retry_safe=False,
                       extra={"ok": False},
                   )
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
            return h._send_error_v59(
                       404,
                       error_code="GENERIC_ERROR",
                       error_message=f"Image file not found for key={key}",
                       retry_safe=False,
                       extra={"ok": False},
                   )
        import urllib.parse as _up2
        bg_url = f"/files?path={_up2.quote(abs_path)}"
        return h._send_json(200, {"ok": True, "bg_url": bg_url, "bg_path": abs_path})
    except Exception as e:
        return h._send_error_v59(
                   500,
                   error_code="GENERIC_ERROR",
                   error_message=str(e),
                   retry_safe=True,
                   extra={"ok": False},
               )


def handle_beat_finalize(h, body: dict)-> None:

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
    scope_type, scope_root, err_st, err_body = h._resolve_scope_root(body)
    if err_st is not None:
        return h._send_json(err_st, err_body)

    scope_target_video = (body or {}).get("scope_target_video")
    if scope_target_video not in h.app.state._VALID_VIDEO_ROLES:
        return h._send_error_v59(
                   400,
                   error_code="SCOPE_TARGET_VIDEO_REQUIRED_MUST",
                   error_message="scope_target_video required + must be intro/resolution/standalone",
                   retry_safe=False,
                   extra={"ok": False, "code": "VIDEO_ROLE_INVALID", "got": scope_target_video, "valid": sorted(h.app.state._VALID_VIDEO_ROLES)},
               )

    beat_id = (body or {}).get("beat_id")
    if not beat_id:
        return h._send_error_v59(
                   400,
                   error_code="MISSING_BEAT_ID",
                   error_message="beat_id required",
                   retry_safe=False,
                   extra={"ok": False, "code": "BEAT_ID_MISSING"},
               )
    force_rebuild = bool((body or {}).get("force_rebuild", False))

    # LD-460 pin tuple at entry (v3 spec §3.5).
    _pin = {
        "pinned_generation": h.app.event_generation,
        "pinned_event_dir": h.app.event_dir,
        "pinned_video_role": scope_target_video,
        "_handler": "beat_finalize",
    }
    if not h._check_event_pin(_pin, "beat_finalize_pre_work"):
        return h._send_error_v59(
                   423,
                   error_code="EVENT_CHANGED_PRE_WORK",
                   error_message="event_changed_pre_work",
                   retry_safe=False,
                   extra={"code": "ASYNC_JOB_GENERATION_PIN_V1", "handler": "beat_finalize"},
               )

    # Lazy import the lib pipeline.
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "credentials_lib"))
        from ffmpeg_stitch import (  # type: ignore
            FINALIZE_RECIPE_VERSION as _FRV,
            NORMALIZATION_RECIPE_HASH as _NRH,
            compute_finalize_args_hash,
            normalize_for_concat,
            trim_normalized,
        )
    except ImportError as exc:
        return h._send_error_v59(
                   500,
                   error_code="GENERIC_ERROR",
                   error_message=f"lib/ffmpeg_stitch import failed: {exc}",
                   retry_safe=True,
                   extra={"ok": False},
               )

    # Snapshot state (slim — beats + image_overrides) at entry.
    state = h._read_scope_state(scope_type, scope_root)
    videos = state.get("videos") or {}
    partition = videos.get(scope_target_video) or {}
    beats = partition.get("beats") or {}
    if beat_id not in beats:
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=f"unknown beat {beat_id!r} in role {scope_target_video!r}",
                   retry_safe=False,
                   extra={"ok": False},
               )
    slim = {
        "beats": beats,
        "image_overrides": partition.get("image_overrides") or {},
    }

    # Resolve clips_dir per scope.
    if scope_type == "event":
        clips_dir = h.app.state.clips_dir
    else:
        clips_dir = scope_root / "animation_clips"

    # Compute hash + metadata. resolve_beat_file may raise FNF.
    try:
        digest, meta = compute_finalize_args_hash(slim, beat_id, clips_dir)
    except FileNotFoundError as exc:
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=str(exc),
                   retry_safe=False,
                   extra={"ok": False, "code": "BEAT_SOURCE_MISSING"},
               )

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
        if not h._check_event_pin(_pin, "beat_finalize_terminal"):
            return h._send_error_v59(
                       423,
                       error_code="EVENT_CHANGED_TERMINAL",
                       error_message="event_changed_terminal",
                       retry_safe=False,
                       extra={"code": "ASYNC_JOB_GENERATION_PIN_V1", "handler": "beat_finalize"},
                   )

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
                module_id=_resolve_module_id_for_state(h.app.state),
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

    return h._send_json(200, {
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


def serve_beat_audio(h, beat_id: str)-> None:

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
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=f"invalid beat_id: {beat_id!r}",
                   retry_safe=False,
               )

    audio_path = _find_beat_audio(h.app.event_dir, beat_id, app=h.app)
    if not audio_path or not audio_path.is_file():
        return h._send_error_v59(
                   404,
                   error_code="GENERIC_ERROR",
                   error_message=f"no TTS audio found for {beat_id}",
                   retry_safe=False,
                   extra={"hint": "regenerate audio via the 🎙 Regen Audio button or edit dialogue"},
               )

    suffix = audio_path.suffix.lower()
    ctype = {".mp3": "audio/mpeg", ".wav": "audio/wav"}.get(suffix, "application/octet-stream")
    size = audio_path.stat().st_size
    range_header = h.headers.get("Range")
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
            h.send_response(206)
            h.send_header("Content-Type", ctype)
            h.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            h.send_header("Accept-Ranges", "bytes")
            h.send_header("Content-Length", str(length))
            # No caching — always serve fresh (defeats the AU[]-stale bug
            # by making sure every play fetches the latest bytes).
            h.send_header("Cache-Control", "no-store, must-revalidate")
            # LOG_HYGIENE_SUPPRESS_CLIENT_CANCEL_TRACEBACKS (LD 2026-04-18):
            # Same as _serve_asset range path — suppress client-cancel spam.
            try:
                h.end_headers()
                h.wfile.write(chunk)
            except (BrokenPipeError, ConnectionResetError):
                print(f"beat audio stream canceled by client: {beat_id}", file=sys.stderr, flush=True)
            return

    body = audio_path.read_bytes()
    h._send_bytes(
        200, body, ctype,
        extra_headers={
            "Accept-Ranges": "bytes",
            "Cache-Control": "no-store, must-revalidate",
            "X-TTS-File": audio_path.name,  # for client-side diagnostics
        },
    )


def handle_beat_update_text(h, body: dict)-> None:

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
        scope = scope_router.resolve(body, h.app.event_dir.name)
    except scope_router.ScopeError as e:
        return h._send_error_v59(
            e.http_status,
            error_code=e.code.upper(),
            error_message=e.code,
            retry_safe=False,
            extra=e.detail or None,
        )
    beat_id = body.get("beat") or scope.beat_id
    new_text = body.get("text")
    if not beat_id or new_text is None:
        return h._send_error_v59(
                   400,
                   error_code="MISSING_BEAT_OR_TEXT",
                   error_message="missing 'beat' or 'text'",
                   retry_safe=False,
               )
    if not isinstance(new_text, str):
        return h._send_error_v59(
                   400,
                   error_code="INVALID_TEXT",
                   error_message="'text' must be a string",
                   retry_safe=False,
               )
    # Upper bound to prevent pathological payloads
    if len(new_text) > 5000:
        return h._send_error_v59(
                   400,
                   error_code="TEXT_EXCEEDS_CHARS",
                   error_message="text exceeds 5000 chars",
                   retry_safe=False,
               )

    try:
        beat_num = int(beat_id.split("_")[1])
    except (IndexError, ValueError):
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=f"unparseable beat_id: {beat_id!r}",
                   retry_safe=False,
               )

    # Step 1: detect if a TTS file exists (for stale-flag logic)
    tts_exists = _find_beat_audio(h.app.event_dir, beat_id, app=h.app) is not None

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
        # Clear cached end_frame_prompt when text changes — force re-derive on next Regen.
        # Without this, stale prompts override new stage directions in beat text.
        # Future-proofs FLUX Kontext restore: stale end_frame_prompts would otherwise
        # silently override Kim's text edits once FLUX is re-enabled.
        if old != _t:
            b["end_frame_prompt"] = ""
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
    h.app.state.mutate_video_state(scope.video_role, update_partition)
    old_text = _holder.get("old")

    # LD-459 UNIVERSAL_AUTOSAVE_V1 — regen the sidecar(s) after every
    # state mutation so v58 emergency rollback sees fresh dialogue via
    # /api/v2/storyboard/L.json. _write_sidecar_L_json mirrors to all
    # sibling storyboard_v*_prod.L.json so a server flag-flip remains safe.
    try:
        _write_sidecar_L_json(h.app, h.app.state.read_state())
    except Exception as exc:  # noqa: BLE001
        print(f"[update_text] WARN sidecar regen failed: "
              f"{type(exc).__name__}: {exc}", flush=True)

    # Step 3: patch the storyboard HTML L[] entry via the shared helper
    # (Tier 5 refactor, April 17 2026 — decisions 151 + 154 now share one
    # code path, so `assign_image` gets the same hardened write semantics
    # and there is ONE place to audit for server/HTML divergence.)
    patch_result = _patch_storyboard_L_field(
        h.app, beat_id, "t", new_text,
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
            return h._send_json(200, {
                "ok": True, "beat": beat_id, "saved_at": now_iso,
                "html_patched": False, "v59_shell": True,
                "text_modified_after_tts": tts_exists and old_text != new_text,
            })
        if reason == "not_in_storyboard":
            # No L[] entry to patch — state is still the source of truth.
            # Dialogue for this beat simply isn't in the storyboard rendering
            # pipeline (e.g., narration-only beats). Saved-to-state is fine.
            print(f"[update_text] {beat_id} NOT in storyboard L[] — state only")
            return h._send_json(200, {
                "ok": True, "beat": beat_id, "saved_at": now_iso,
                "html_patched": False,
                "text_modified_after_tts": tts_exists and old_text != new_text,
            })
        # Real error — return 500 with the detail from the helper.
        return h._send_error_v59(
                   500,
                   error_code="GENERIC_ERROR",
                   error_message=patch_result.get("error", "unknown HTML patch error"),
                   retry_safe=True,
                   extra={**{k: v for k, v in patch_result.items()
               if k in ("escaped_preview",)}},
               )

    print(f"[update_text] {beat_id} saved ({len(new_text)} chars) "
          f"html_patched=True tts_exists={tts_exists}")

    # Best-effort Directus audit log (Rule 18 Two-Write)
    try:
        _async_log_text_update(
            h.app.event_id, beat_id, old_text, new_text, tts_exists,
        )
    except Exception:
        pass  # fire-and-forget

    # ==================================================================
    # LD-803 TTS_NO_AUTO_REGEN_EXPLICIT_BUTTON_ONLY_V1 (2026-05-20):
    # TTS NEVER auto-regenerates on text edit. Regeneration fires
    # EXCLUSIVELY via the explicit Regen Audio button
    # (_handle_beat_regenerate_audio). This block formerly hosted the
    # synchronous Decision 181 auto-regen (hoisted by LD-734); both LDs
    # are superseded. The stale-TTS badge (text_modified_after_tts) is
    # the user-visible signal that audio is out of date and the user
    # should click Regen Audio.
    #
    # Tier 1A debounce helpers + TIER1A_ENABLED gating remain in
    # production_server.py (lines ~464-566, 726-736) — they are no longer
    # invoked from this auto-regen path but are retained because _t1_enabled()
    # is still consulted at production_server.py:2244 (broader runtime gate
    # beyond auto-regen) and Tier 3 widgets reference TIER1A_ENABLED via
    # patch_v38_tier3_widgets.py. The skip_tts_regen body flag is irrelevant
    # under LD-803 (regen is opt-IN via button, not opt-OUT via flag).
    # ==================================================================
    text_actually_changed = (old_text or "") != new_text
    tts_regen_result = {
        "ok": False,
        "skipped": True,
        "reason": "no_auto_regen_per_LD_803",
        "hint": "click 🎙 Regen Audio button to regenerate TTS",
    }

    h._send_json(200, {
        "ok": True,
        "beat": beat_id,
        "saved_at": now_iso,
        "html_patched": True,
        "text_modified_after_tts": (
            tts_exists and text_actually_changed
        ),
        "old_text_preview": (old_text or "")[:100],
        "tts_regen": tts_regen_result,
    })


def handle_beat_update_speaker(h, body: dict)-> None:

    """POST /api/beat/update_speaker {beat|beat_id, speaker, event_id?}"""
    try:
        scope = scope_router.resolve(body, h.app.event_dir.name)
    except scope_router.ScopeError as e:
        return h._send_error_v59(
            e.http_status,
            error_code=e.code.upper(),
            error_message=e.code,
            retry_safe=False,
            extra=e.detail or None,
        )
    beat_id = body.get("beat") or body.get("beat_id") or scope.beat_id
    new_speaker_raw = body.get("speaker")
    if not beat_id or new_speaker_raw is None:
        return h._send_error_v59(
                   400,
                   error_code="MISSING_BEAT_OR_SPEAKER",
                   error_message="missing 'beat' or 'speaker'",
                   retry_safe=False,
               )
    if not isinstance(new_speaker_raw, str):
        return h._send_error_v59(
                   400,
                   error_code="INVALID_SPEAKER",
                   error_message="'speaker' must be a string",
                   retry_safe=False,
               )
    new_speaker = new_speaker_raw.strip()
    if not new_speaker:
        return h._send_error_v59(
                   400,
                   error_code="INVALID_SPEAKER",
                   error_message="'speaker' must be a non-empty string",
                   retry_safe=False,
               )
    if len(new_speaker) > 100:
        return h._send_error_v59(
                   400,
                   error_code="SPEAKER_EXCEEDS_CHARS",
                   error_message="speaker exceeds 100 chars",
                   retry_safe=False,
               )

    canonical = _canonicalize_speaker(new_speaker) or new_speaker
    tts_exists = _find_beat_audio(h.app.event_dir, beat_id, app=h.app) is not None
    now_iso = datetime.now(timezone.utc).isoformat()
    _holder: dict = {}

    def update_partition(partition, _bid=beat_id, _spk=canonical, _stale=tts_exists, _ts=now_iso):
        beats = partition.setdefault("beats", {})
        b = beats.setdefault(_bid, {})
        old_top = b.get("speaker") or ""
        p1 = b.setdefault("phase_1", {})
        old_p1 = p1.get("speaker") or ""
        old_speaker = old_top or old_p1
        b["speaker"] = _spk
        p1["speaker"] = _spk
        if old_speaker != _spk:
            p1["speaker_mismatch"] = True
            p1["speaker_mismatch_set_at"] = _ts
            if _stale:
                b["text_modified_after_tts"] = True
        _holder["old"] = old_speaker
        _holder["changed"] = (old_speaker != _spk)

    h.app.state.mutate_video_state(scope.video_role, update_partition)

    try:
        _write_sidecar_L_json(h.app, h.app.state.read_state())
    except Exception as exc:  # noqa: BLE001
        print(f"[update_speaker] WARN sidecar regen failed: "
              f"{type(exc).__name__}: {exc}", flush=True)

    h._send_json(200, {
        "ok": True,
        "beat": beat_id,
        "speaker": canonical,
        "saved_at": now_iso,
        "changed": _holder.get("changed", False),
        "text_modified_after_tts": (
            tts_exists and _holder.get("changed", False)
        ),
    })


def handle_beat_done_toggle(h, body: dict)-> None:

    """V59 Phase 6 — toggle kim_done flag on a beat.

    Per spec line 120 — replaces LD-746 fabrication.
    Body: {"beat_id": "beat_05", "scope_video_role": "intro"} — scope keys injected by pathappPatch.
    """
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return

    beat_id = body.get("beat_id")
    if not beat_id:
        return h._send_error_v59(
            400,
            error_code="MISSING_BEAT_ID",
            error_message="body.beat_id is required",
            retry_safe=False,
            hint="Send {'beat_id': '<id>'} in the POST body",
        )
    video_role = (
        body.get("scope_video_role")
        or body.get("scope_target_video")
        or h.app.state.read_state().get("active_video", "intro")
    )
    toggled: dict = {"kim_done": False}

    def mutate(partition: dict) -> None:
        beat = partition.setdefault("beats", {}).setdefault(beat_id, {})
        beat["kim_done"] = not bool(beat.get("kim_done", False))
        toggled["kim_done"] = beat["kim_done"]

    h.app.state.mutate_video_state(video_role, mutate)
    return h._send_json(200, {
        "ok": True,
        "beat_id": beat_id,
        "video_role": video_role,
        "kim_done": toggled["kim_done"],
    })


def handle_beat_graft(h, body: dict)-> None:

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
        return h._send_error_v59(
                   400,
                   error_code="MUTATION_ID_REQUIRED",
                   error_message="mutation_id_required",
                   retry_safe=False,
               )
    if not isinstance(src, dict) or not isinstance(tgt, dict):
        return h._send_error_v59(
                   400,
                   error_code="SOURCE_TARGET_MUST_BE_OBJECTS",
                   error_message="source/target must be objects",
                   retry_safe=False,
               )
    for fld in ("event_id", "video_role", "beat_id"):
        if not src.get(fld):
            return h._send_error_v59(
                       400,
                       error_code="GENERIC_ERROR",
                       error_message=f"source.{fld}_required",
                       retry_safe=False,
                   )
    for fld in ("event_id", "video_role"):
        if not tgt.get(fld):
            return h._send_error_v59(
                       400,
                       error_code="GENERIC_ERROR",
                       error_message=f"target.{fld}_required",
                       retry_safe=False,
                   )
    for r in (src["video_role"], tgt["video_role"]):
        if r not in {"intro", "resolution", "standalone"}:
            return h._send_error_v59(
                       400,
                       error_code="VIDEO_ROLE_INVALID",
                       error_message="video_role_invalid",
                       retry_safe=False,
                       extra={"got": r},
                   )

    # 2) Idempotency dedup cache (mutation_id replay)
    if mutation_id in _GRAFT_DEDUP:
        cached = _GRAFT_DEDUP[mutation_id]
        _GRAFT_DEDUP.move_to_end(mutation_id)
        return h._send_json(200, {**cached, "status": "dedup"})

    # 3) Validate target scope (server is write-pinned to its event_dir)
    server_event = h.app.event_dir.name
    if tgt["event_id"] != server_event:
        return h._send_error_v59(
                   409,
                   error_code="SCOPE_MISMATCH",
                   error_message="scope_mismatch",
                   retry_safe=False,
                   extra={"expected_event_id": server_event, "got": tgt["event_id"]},
               )

    # 4) Cross-event source: require --source-event CLI flag
    cross_event = (src["event_id"] != tgt["event_id"])
    source_event_dir: Path | None = None
    if cross_event:
        seed = getattr(h.app, "source_event_dir", None)
        if seed is None or seed.name != src["event_id"]:
            return h._send_error_v59(
                       409,
                       error_code="CROSS_EVENT_REQUIRES_EXPLICIT_SOURCE",
                       error_message="cross_event_requires_explicit_source",
                       retry_safe=False,
                       extra={"hint": f"Restart server with --source-event Production/{src['event_id']} "
                    "to enable cross-event graft from this source."},
                   )
        source_event_dir = seed
    else:
        source_event_dir = h.app.event_dir

    # 5) Load source state and locate the source beat
    try:
        source_state_path = source_event_dir / "production_state.json"
        with open(source_state_path, "r", encoding="utf-8") as f:
            source_state = json.load(f)
    except FileNotFoundError:
        return h._send_error_v59(
                   404,
                   error_code="SOURCE_STATE_NOT_FOUND",
                   error_message="source_state_not_found",
                   retry_safe=False,
                   extra={"path": str(source_state_path)},
               )
    src_partition = (source_state.get("videos") or {}).get(src["video_role"], {}) or {}
    src_beats = src_partition.get("beats") or {}
    src_beat = src_beats.get(src["beat_id"])
    if src_beat is None:
        h._append_audit_log({
            "schema_version": 1, "action": "beat_graft_failed",
            "ts": datetime.now(timezone.utc).isoformat(),
            "mutation_id": mutation_id,
            "source": src, "target": tgt, "ok": False,
            "reason": "source_beat_not_found",
        })
        return h._send_error_v59(
                   404,
                   error_code="SOURCE_BEAT_NOT_FOUND",
                   error_message="source_beat_not_found",
                   retry_safe=False,
                   extra={"source": src},
               )

    # 6) Pre-render-only invariant (RR-1 mitigation)
    phase_1 = src_beat.get("phase_1") or {}
    if phase_1.get("status") == "completed":
        return h._send_error_v59(
                   400,
                   error_code="GRAFT_PRE_RENDER_ONLY",
                   error_message="graft_pre_render_only",
                   retry_safe=False,
                   extra={"reason": "source.phase_1.status==completed"},
               )
    for opt in (phase_1.get("options") or []):
        if isinstance(opt, dict):
            if opt.get("file") or opt.get("lipsync_task_id"):
                return h._send_error_v59(
                           400,
                           error_code="GRAFT_PRE_RENDER_ONLY",
                           error_message="graft_pre_render_only",
                           retry_safe=False,
                           extra={"reason": "source.phase_1.options[].file or lipsync_task_id non-empty"},
                       )

    # 7) Pre-image snapshots (atomic copy of full state(s))
    utc = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    pre_image_paths: list[str] = []
    try:
        seen_dirs: set[Path] = set()
        for ev_dir in (source_event_dir, h.app.event_dir):
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
        return h._send_error_v59(
                   503,
                   error_code="PRE_IMAGE_SNAPSHOT_FAILED",
                   error_message="pre_image_snapshot_failed",
                   retry_safe=True,
                   extra={"detail": f"{type(exc).__name__}: {exc}"},
               )

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
    target_state_path = h.app.event_dir / "production_state.json"
    try:
        with open(target_state_path, "r", encoding="utf-8") as f:
            target_state_pre = json.load(f)
    except FileNotFoundError:
        return h._send_error_v59(
                   500,
                   error_code="TARGET_STATE_NOT_FOUND",
                   error_message="target_state_not_found",
                   retry_safe=True,
               )
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
                "audit_log_path": str(_audit_log_path(h.app)),
                "target_display_order": tgt_partition_pre.get("display_order", []),
            }
            _GRAFT_DEDUP[mutation_id] = result
            while len(_GRAFT_DEDUP) > _GRAFT_DEDUP_MAX:
                _GRAFT_DEDUP.popitem(last=False)
            return h._send_json(200, result)

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
        h.app.state.mutate_video_state(tgt["video_role"], _insert_target)
    except Exception as exc:  # noqa: BLE001
        return h._send_error_v59(
                   500,
                   error_code="TARGET_WRITE_FAILED",
                   error_message="target_write_failed",
                   retry_safe=True,
                   extra={"detail": f"{type(exc).__name__}: {exc}", "pre_image_paths": pre_image_paths},
               )

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
                return h._send_error_v59(
                           500,
                           error_code="SOURCE_DELETE_FAILED",
                           error_message="source_delete_failed",
                           retry_safe=True,
                           extra={"detail": f"{type(exc).__name__}: {exc}", "pre_image_paths": pre_image_paths},
                       )
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
                h.app.state.mutate_video_state(src["video_role"], _delete_source)
            except Exception as exc:  # noqa: BLE001
                return h._send_error_v59(
                           500,
                           error_code="SOURCE_DELETE_FAILED_SAME_EVENT",
                           error_message="source_delete_failed_same_event",
                           retry_safe=True,
                           extra={"detail": f"{type(exc).__name__}: {exc}", "pre_image_paths": pre_image_paths},
                       )

    # 12) Audit log: file JSONL (durable) + Directus mirror (best-effort)
    target_state_after_path = h.app.event_dir / "production_state.json"
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
    h._append_audit_log(audit_row)
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
        "audit_log_path": str(_audit_log_path(h.app)),
        "target_display_order": post_partition.get("display_order", []),
        "beat_id": src["beat_id"],
    }
    _GRAFT_DEDUP[mutation_id] = result
    while len(_GRAFT_DEDUP) > _GRAFT_DEDUP_MAX:
        _GRAFT_DEDUP.popitem(last=False)
    return h._send_json(200, result)


def handle_beat_regenerate_audio(h, body: dict)-> None:

    """Explicit TTS regen trigger (decision 181 companion endpoint, April 17 2026).

    POST /api/beat/regenerate_audio {beat_id: "beat_NN"}
    (legacy alias: {beat: "beat_NN"} — back-compat per F-REGEN-AUDIO-001
    / prod_blockers id=124; matches precedent at production_server.py
    :11516 _handle_use_as_final).

    Forces ElevenLabs v3 TTS regen using the beat's CURRENT text in
    state (no need to re-edit text first). Useful when:
      - User wants to re-roll a voice take they don't like
      - Voice profile was updated and beats need re-rendering
      - Blur-triggered auto-regen failed and needs explicit retry

    Rule 11 source fidelity: the text in state is the source of truth;
    this endpoint ensures audio matches current state.text verbatim.
    """
    # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
    # LD-810 AUDIO_REGEN_SCOPE_AUTODISCOVER_V1 — allow_missing_video_role=True
    # so the autodiscover branch below (lines ~1225-1253) is reachable when
    # the caller omits scope_video_role. Without this flag the validator
    # returns VIDEO_ROLE_REQUIRED before autodiscover can fire, making the
    # LD-810 logic unreachable dead code.
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False,
                                 allow_missing_video_role=True):
        return

    # F-REGEN-AUDIO-001: v59 client (StoryboardTab.tsx:192) sends
    # {beat_id: ...}; legacy callers send {beat: ...}.
    beat_id = body.get("beat_id") or body.get("beat")
    if not beat_id:
        return h._send_error_v59(
                   400,
                   error_code="MISSING_BEAT",
                   error_message="missing 'beat'",
                   retry_safe=False,
               )

    # Blocker #148 fix (LD pending AUDIO_REGEN_SCOPE_AUTODISCOVER_V1, 2026-05-20):
    # If the caller didn't pass scope_video_role/scope_target_video, AND the
    # beat is not present in 'intro' (the legacy default), auto-discover by
    # scanning all video_roles. If found in exactly one, use that. If found
    # in zero or multiple, surface explicit 400 (ambiguous beat across
    # partitions) rather than silent failure with the legacy 'intro' default.
    state = h.app.state.read_state()
    _explicit_role = body.get("scope_video_role") or body.get("scope_target_video")
    if _explicit_role:
        video_role = _explicit_role
        beat_state = (((state.get("videos") or {}).get(video_role) or {}).get("beats") or {}).get(beat_id) or {}
    else:
        # No explicit scope. Try 'intro' first (legacy default); fall back
        # to autodiscovery across all roles.
        _intro_beats = ((state.get("videos") or {}).get("intro") or {}).get("beats") or {}
        if beat_id in _intro_beats:
            video_role = "intro"
            beat_state = _intro_beats[beat_id]
        else:
            _matching_roles = [
                r for r, partition in (state.get("videos") or {}).items()
                if beat_id in ((partition or {}).get("beats") or {})
            ]
            if len(_matching_roles) == 1:
                video_role = _matching_roles[0]
                beat_state = ((state.get("videos") or {}).get(video_role) or {}).get("beats", {}).get(beat_id, {})
                print(f"[regen_audio] {beat_id} scope_video_role autodiscovered: {video_role}")
            elif len(_matching_roles) > 1:
                return h._send_error_v59(
                           400,
                           error_code="AMBIGUOUS_BEAT_SCOPE",
                           error_message=f"beat {beat_id} exists in multiple partitions ({_matching_roles}); pass scope_video_role explicitly",
                           retry_safe=False,
                       )
            else:
                # Beat not found anywhere; default to 'intro' so downstream
                # error reporting stays consistent with the legacy path
                # (will hit 'no dialogue text in state OR storyboard' below).
                video_role = "intro"
                beat_state = {}
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
            html = h.app.storyboard_path.read_text(encoding="utf-8")
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
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=f"beat {beat_id} has no dialogue text in state OR "
                     f"storyboard — regen cannot proceed",
                   retry_safe=False,
               )
    # Persist the fallback-sourced text into state so downstream ops
    # (onblur, future regens, lipsync) see a consistent source of truth.
    if not beat_state.get("text"):
        def _seed_text(st, _bid=beat_id, _t=text):
            b = st.get("beats", {}).setdefault(_bid, {})
            b["text"] = _t
        h.app.state.mutate_state(_seed_text)

    # Load ElevenLabs key — CODE tree (credentials_lib is sibling Python).
    # Handler lives at Production/tools/server_handlers/, credentials_lib at
    # Production/tools/credentials_lib/ — go up one level first.
    try:
        _libdir = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "credentials_lib")
        )
        if _libdir not in sys.path:
            sys.path.insert(0, _libdir)
        from credentials import load_credentials  # type: ignore
        creds = load_credentials()
        el_key = creds.get("elevenlabs_key") or ""
    except Exception as exc:  # noqa: BLE001
        return h._send_error_v59(
                   500,
                   error_code="GENERIC_ERROR",
                   error_message=f"elevenlabs key load failed: {type(exc).__name__}: {exc}",
                   retry_safe=True,
               )
    if not el_key:
        return h._send_error_v59(
                   500,
                   error_code="ELEVENLABS_KEY_UNAVAILABLE_CANNOT_REGENERATE",
                   error_message="elevenlabs key unavailable — cannot regenerate audio",
                   retry_safe=True,
               )

    print(f"[regen_audio] {beat_id} explicit button trigger "
          f"({len(text)}c text in state)")
    try:
        result = _tts_regenerate_for_beat(h.app, beat_id, text, el_key, video_role=video_role)
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        return h._send_error_v59(
                   500,
                   error_code="GENERIC_ERROR",
                   error_message=f"TTS regen failure: {type(exc).__name__}: {exc}",
                   retry_safe=True,
                   extra={"beat": beat_id},
               )

    if result.get("ok"):
        print(f"[regen_audio] {beat_id} OK: {result['audio_file']} "
              f"({result['audio_duration_s']:.2f}s, {result['elapsed_s']:.1f}s call)")
        # Tier 3 (April 18 2026): explicit regen also clears the
        # speaker_mismatch stale-audio badge. Gated on _t1_enabled() so the
        # rollback flag MINDFULNEST_T1_ENABLED=0 reverts behavior.
        if TIER1A_ENABLED:
            _tier1a_mark_regen_fired(
                beat_id, app=h.app, regen_ok=_t1_enabled(),
            )

        # Fix B — TTS over-cap warning at regen time
        # (LD TTS_OVER_CAP_WARNING_AT_REGEN_V1, 2026-05-14). CLAUDE.md Rule
        # 8.5 + LD-400 lock Kling v3 at a 10s hard ceiling; if the new TTS
        # exceeds it, the next Animate click will be skipped server-side
        # with a Rule-8.5 reason string. Surface that NOW instead of at
        # animation submit time so Kim can shorten the script before
        # burning a click. Non-blocking: we DO NOT refuse the regen — Kim
        # may legitimately keep over-cap audio for non-Kling paths.
        duration_warning = None
        try:
            dur = float(result.get("audio_duration_s") or 0)
        except (TypeError, ValueError):
            dur = 0.0
        if dur > KLING_MAX_DURATION_SEC:
            duration_warning = {
                "audio_duration_s": dur,
                "kling_max_s": float(KLING_MAX_DURATION_SEC),
                "message": (
                    f"Audio is {dur:.2f}s but Kling v3 maximum is "
                    f"{KLING_MAX_DURATION_SEC}s — animation submission "
                    f"will be blocked. Shorten the script."
                ),
            }
            # Fire-and-forget activity log row (Rule 18 + Rule 35).
            try:
                from lib.directus import try_post_or_queue  # type: ignore
                try_post_or_queue("prod_activity_log", {
                    "action": "tts_duration_warning",
                    "performed_by": "production_server",
                    "details": {
                        "beat_id": beat_id,
                        "audio_duration_s": dur,
                        "kling_max_s": float(KLING_MAX_DURATION_SEC),
                        "char_count": len(text),
                        "voice_id": result.get("voice_id"),
                        "speaker": result.get("speaker"),
                        "rule_reference": "LD-400 LIPSYNC_MAX_DURATION_10S_NO_SILENCE_V1 + CLAUDE.md Rule 8.5",
                    },
                })
            except Exception as exc:  # noqa: BLE001
                print(f"[regen_audio] {beat_id} duration_warning activity log failed: {exc}")
            print(f"[regen_audio] {beat_id} OVER CAP: {dur:.2f}s > {KLING_MAX_DURATION_SEC}s")

        response = {
            "ok": True,
            "beat": beat_id,
            "tts_regen": result,
            "message": (f"Audio regenerated for {beat_id}: "
                        f"{result['audio_file']} ({result['audio_duration_s']:.2f}s)"),
        }
        if duration_warning is not None:
            response["duration_warning"] = duration_warning
        return h._send_json(200, response)

    # Fail-loud — surface the error.
    print(f"[regen_audio] {beat_id} FAILED: {result.get('error', 'unknown')}")
    return h._send_error_v59(
               500,
               error_code="GENERIC_ERROR",
               error_message=result.get("error", "TTS regen failed"),
               retry_safe=True,
               extra={"ok": False, "beat": beat_id, "tts_regen": result},
           )


def handle_beat_delay(h, body: dict)-> None:

    """Set audio delay (video lead-in) for a beat.
    POST {"beat": "beat_03", "audio_delay": 1.5}
                      OR {"beat_id": ..., "delay_seconds": 1.5}

    Per LD `BEAT_DELAY_BODY_KEY_BACKCOMPAT_V1` (2026-05-14): the v59
    client (StoryboardTab.tsx:260) sends `delay_seconds`; this handler
    originally read only `audio_delay`. Same key-mismatch class as
    F-REGEN-AUDIO-001 May 11 fix. Accept both to close the silent
    no-op (delay was getting persisted as 0 regardless of UI value).
    """
    # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return

    beat_id = body.get("beat") or body.get("beat_id")
    # Accept both v59-client `delay_seconds` and legacy `audio_delay`.
    raw_delay = body.get("audio_delay")
    if raw_delay is None:
        # BODY_KEY_ALLOW: delay_seconds (v59 client canonical per
        # LD `BEAT_DELAY_BODY_KEY_BACKCOMPAT_V1` — dual-key acceptance: v59 client
        # sends `delay_seconds`, pre-v59 callers send `audio_delay`; server reads
        # whichever is present. The BODY_KEY_ALLOW marker is the recognized
        # body_key_contract_check.py escape hatch; this is governance-grade.)
        raw_delay = body.get("delay_seconds", 0)
    delay = float(raw_delay)
    if not beat_id:
        return h._send_error_v59(
                   400,
                   error_code="MISSING_BEAT_BEAT_ID",
                   error_message="missing 'beat'/'beat_id'",
                   retry_safe=False,
               )
    if delay < 0 or delay > 10:
        return h._send_error_v59(
                   400,
                   error_code="INVALID_AUDIO_DELAY",
                   error_message="audio_delay must be 0-10 seconds",
                   retry_safe=False,
               )

    video_role = (body or {}).get("scope_video_role") or (body or {}).get("scope_target_video") or "intro"

    def update(state, _role=video_role):
        b = ((state.get("videos") or {}).get(_role) or {}).get("beats", {}).get(beat_id)
        if not b:
            return False
        b.setdefault("phase_1", {})["audio_delay"] = round(delay, 2)
        return True

    found = h.app.state.mutate_state(update)
    if not found:
        return h._send_error_v59(
                   404,
                   error_code="GENERIC_ERROR",
                   error_message=f"beat {beat_id} not found",
                   retry_safe=False,
               )
    h._send_json(200, {"beat": beat_id, "audio_delay": round(delay, 2)})


def handle_beat_trim(h, body: dict)-> None:

    """Set clip trim points for a beat.
    POST {"beat": "beat_07", "trim_start": 0, "trim_end": 3.5}
                      OR {"beat_id": ..., "trim_in": 0, "trim_out": 3.5}

    Per LD `BODY_KEY_BACKCOMPAT_TRIM_V1` (2026-05-14): the v59 client
    (StoryboardTab.tsx:267-269) sends `trim_in`/`trim_out`; this handler
    originally read only `trim_start`/`trim_end`. Same key-mismatch class
    as F-REGEN-AUDIO-001 + LD-693 (delay_slider). Accept both to close
    the silent no-op surfaced by the CI grep gate (LD-699).
    """
    # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return

    beat_id = body.get("beat") or body.get("beat_id")
    if not beat_id:
        return h._send_error_v59(
                   400,
                   error_code="MISSING_BEAT_BEAT_ID",
                   error_message="missing 'beat'/'beat_id'",
                   retry_safe=False,
               )
    # BODY_KEY_BACKCOMPAT_TRIM_V1 — accept trim_in/trim_out (client canonical)
    # AND trim_start/trim_end (legacy server keys). Server-key-first precedence
    # matches LD-693 (audio_delay over delay_seconds).
    raw_trim_start = body.get("trim_start")  # BODY_KEY_ALLOW: trim_start legacy server key, see LD BODY_KEY_BACKCOMPAT_TRIM_V1
    if raw_trim_start is None:
        raw_trim_start = body.get("trim_in", 0)
    trim_start = float(raw_trim_start)
    raw_trim_end = body.get("trim_end")  # BODY_KEY_ALLOW: trim_end legacy server key, see LD BODY_KEY_BACKCOMPAT_TRIM_V1
    if raw_trim_end is None:
        raw_trim_end = body.get("trim_out")  # null = use full clip
    trim_end = raw_trim_end
    # BUG FIX (2026-05-23): trim_back (relative seconds from end) replaces the client-side
    # trim_out computation which was wrong (used audio_duration instead of video_duration).
    # When trim_back is present it takes precedence and clears stale trim_end.
    # vendor_jobs.py reads trim_back and computes effective_end = raw_dur - trim_back.
    raw_trim_back = body.get("trim_back")  # BODY_KEY_ALLOW: trim_back (2026-05-23 back-trim fix)
    trim_back = float(raw_trim_back) if raw_trim_back is not None else None
    if trim_start < 0:
        return h._send_error_v59(
                   400,
                   error_code="TRIM_START_MUST_BE",
                   error_message="trim_start must be >= 0",
                   retry_safe=False,
               )
    if trim_back is not None and trim_back < 0:
        return h._send_error_v59(
                   400,
                   error_code="TRIM_BACK_MUST_BE",
                   error_message="trim_back must be >= 0",
                   retry_safe=False,
               )
    if trim_back is None and trim_end is not None:
        trim_end = float(trim_end)
        if trim_end <= trim_start:
            return h._send_error_v59(
                       400,
                       error_code="TRIM_END_MUST_BE_TRIM",
                       error_message="trim_end must be > trim_start",
                       retry_safe=False,
                   )

    video_role = (body or {}).get("scope_video_role") or (body or {}).get("scope_target_video") or "intro"

    def update(state, _role=video_role, _trim_back=trim_back):
        b = ((state.get("videos") or {}).get(_role) or {}).get("beats", {}).get(beat_id)
        if not b:
            return False
        p1 = b.setdefault("phase_1", {})
        p1["trim_start"] = round(trim_start, 2)
        if _trim_back is not None:
            # New canonical path: store relative back-trim; clear stale absolute trim_end.
            p1["trim_back"] = round(_trim_back, 2) if _trim_back > 0 else None
            p1["trim_end"] = None  # clear wrong absolute value from old client bug
        else:
            p1["trim_end"] = round(trim_end, 2) if trim_end is not None else None
        return True

    found = h.app.state.mutate_state(update)
    if not found:
        return h._send_error_v59(
                   404,
                   error_code="GENERIC_ERROR",
                   error_message=f"beat {beat_id} not found",
                   retry_safe=False,
               )
    result = {"beat": beat_id, "trim_start": round(trim_start, 2)}
    if trim_back is not None:
        result["trim_back"] = round(trim_back, 2) if trim_back > 0 else None
    elif trim_end is not None:
        result["trim_end"] = round(trim_end, 2)
    h._send_json(200, result)


def handle_beat_undo_final(h, body: dict) -> None:
    """Clear the `final` block on a beat regardless of source type.

    POST {beat|beat_id, scope_event_id, scope_video_role}
    Kim 2026-05-20 follow-up: originally LD-761 only allowed undo for
    still_image finals. Broadened to all source types (raw_option, lipsync,
    still_image) so Kim can un-finalize ANY beat and re-pick. The underlying
    media files (option mp4s, lipsync mp4, still mp4) stay on disk; only the
    `final` block on the beat is removed.
    """
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return

    beat_id = body.get("beat") or body.get("beat_id")  # BODY_KEY_ALLOW: beat legacy alias
    if not beat_id:
        return h._send_error_v59(
            400,
            error_code="MISSING_BEAT",
            error_message="beat required",
            retry_safe=False,
        )

    # [INFERRED — verify] Default video_role 'intro' when neither
    # scope_video_role nor scope_target_video is supplied. Mirrors the
    # default used in handle_beat_use_still_as_final, handle_beat_done_toggle,
    # and handle_beat_trim (beats_legacy.py:1297, 1502, 1574). v59 clients
    # always inject scope_target_video via pathappPatch; the default is the
    # legacy/pre-v59 fallback. Most events have 'intro' as their primary
    # video; resolution + standalone require explicit scope.
    video_role = (
        (body or {}).get("scope_video_role")
        or (body or {}).get("scope_target_video")
        or "intro"
    )
    outcome: dict = {"status": "missing"}

    def mutate(partition: dict) -> None:
        b = (partition.get("beats") or {}).get(beat_id)
        if not b:
            outcome["status"] = "missing"
            return
        final = b.get("final") or {}
        if not final:
            outcome["status"] = "nothing"
            return
        # Kim 2026-05-20 follow-up: broadened from still_image-only to all
        # source types. raw_option / lipsync / still_image — any final can
        # be undone (the underlying mp4 stays on disk).
        b.pop("final", None)
        outcome["status"] = "ok"
        outcome["prior_source"] = final.get("source")

    h.app.state.mutate_video_state(video_role, mutate)
    if outcome["status"] == "missing":
        return h._send_error_v59(
            404,
            error_code="GENERIC_ERROR",
            error_message=f"beat {beat_id} not found",
            retry_safe=False,
        )
    if outcome["status"] == "nothing":
        return h._send_error_v59(
            400,
            error_code="NOTHING_TO_UNDO",
            error_message="beat has no final block to undo",
            retry_safe=False,
        )

    try:
        from lib.directus import try_post_or_queue
        try_post_or_queue("prod_activity_log", {
            "action": "BEAT_UNDO_FINAL_V1",
            "performed_by": "handle_beat_undo_final",
            "details": {
                "event_id": str(h.app.event_id),
                "beat_id": beat_id,
                "video_role": video_role,
            },
        })
    except Exception as exc:  # noqa: BLE001
        print(
            f"[beat-undo-final] activity log write failed (non-blocking): {exc}",
            file=sys.stderr,
            flush=True,
        )

    return h._send_json(200, {"ok": True, "beat": beat_id})


def handle_beat_zoom(h, body: dict) -> None:
    """POST /api/beat/zoom — toggle slow Ken Burns zoom on a beat's final clip.

    Apply:  reads final.file, ffmpeg zoompan 1.0->1.15x center-zoom over full
            clip, writes {stem}_zoom.mp4, updates final.file + stores original
            in final.pre_zoom_file + sets final.zoom_applied = True.
    Undo:   if final.zoom_applied is True, restores final.file from pre_zoom_file.

    Body: { beat_id (or beat), scope_event_id (or event_id), scope_video_role }
    """
    import subprocess, pathlib

    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return

    beat_id = body.get("beat_id") or body.get("beat")
    if not beat_id:
        return h._send_error_v59(400, error_code="MISSING_BEAT_ID",
                                  error_message="beat_id required", retry_safe=False)

    video_role = (
        (body or {}).get("scope_video_role")
        or (body or {}).get("scope_target_video")
        or "intro"
    )

    event_dir = h.app.event_dir
    clips_dir = event_dir / "animation_clips"

    # --- read current final block (read-only snapshot) ---
    outcome: dict = {"status": "pending"}

    def _read(partition):
        b = (partition.get("beats") or {}).get(beat_id)
        if not b:
            outcome["status"] = "beat_missing"
            return
        outcome["final"] = dict(b.get("final") or {})
        outcome["status"] = "read_ok"

    h.app.state.mutate_video_state(video_role, _read)

    if outcome["status"] == "beat_missing":
        return h._send_error_v59(404, error_code="BEAT_NOT_FOUND",
                                  error_message=f"beat {beat_id!r} not found in {video_role}",
                                  retry_safe=False)

    final = outcome.get("final", {})
    zoom_applied = bool(final.get("zoom_applied"))

    # --- UNDO path ---
    if zoom_applied:
        pre_zoom = final.get("pre_zoom_file")
        if not pre_zoom:
            return h._send_error_v59(409, error_code="NO_PRE_ZOOM_FILE",
                                      error_message="zoom_applied=true but pre_zoom_file missing",
                                      retry_safe=False)

        def _undo(partition):
            b = (partition.get("beats") or {}).get(beat_id)
            if not b:
                return
            f = b.setdefault("final", {})
            f["file"] = pre_zoom
            f.pop("zoom_applied", None)
            f.pop("pre_zoom_file", None)
            f["file_exists"] = (clips_dir / pre_zoom).is_file()

        h.app.state.mutate_video_state(video_role, _undo)
        return h._send_json(200, {"ok": True, "action": "zoom_removed",
                                   "beat_id": beat_id, "final_file": pre_zoom})

    # --- APPLY path ---
    current_file = final.get("file")
    if not current_file:
        return h._send_error_v59(409, error_code="NO_FINAL_FILE",
                                  error_message="beat has no final.file to zoom",
                                  retry_safe=False)

    src_path = clips_dir / current_file
    if not src_path.is_file():
        return h._send_error_v59(404, error_code="FINAL_FILE_MISSING",
                                  error_message=f"{current_file} not on disk", retry_safe=False)

    # e.g. beat_03_lipsync.mp4 -> beat_03_lipsync_zoom.mp4
    stem = src_path.stem
    zoom_filename = f"{stem}_zoom.mp4"
    dst_path = clips_dir / zoom_filename
    tmp_path = dst_path.with_suffix(".tmp.mp4")

    # Get duration for per-clip zoom speed
    try:
        probe = subprocess.check_output(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(src_path)],
            stderr=subprocess.DEVNULL
        )
        duration_s = float(probe.decode().strip())
    except Exception as e:
        return h._send_error_v59(500, error_code="FFPROBE_FAILED",
                                  error_message=str(e), retry_safe=True)

    fps = 24
    total_frames = max(int(duration_s * fps), 1)
    # Zoom 1.0 -> 1.15 over full clip
    zoom_step = 0.15 / total_frames

    # Normalize to 1280x720 FIRST (same as NORMALIZATION_VF_EXPR in ffmpeg_stitch.py)
    # using force_original_aspect_ratio=decrease + pad so non-16:9 sources
    # (e.g. 720x544 ByteDance lipsync output) are letterboxed, not stretched.
    # Prior: scale=1280:720 with no AR guard → horizontal stretch on 720x544.
    vf = (
        f"scale=1280:720:force_original_aspect_ratio=decrease,"
        f"pad=1280:720:(ow-iw)/2:(oh-ih)/2,"
        f"setsar=1:1,"
        f"fps={fps},"
        f"zoompan=z='min(zoom+{zoom_step:.8f},1.15)':d=1"
        f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    )

    cmd = [
        "ffmpeg", "-y", "-i", str(src_path),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        str(tmp_path),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=120)
        if result.returncode != 0:
            err_tail = result.stderr.decode(errors="replace")[-600:]
            if tmp_path.exists():
                tmp_path.unlink()
            return h._send_error_v59(500, error_code="FFMPEG_FAILED",
                                      error_message=err_tail, retry_safe=True)
        tmp_path.rename(dst_path)
    except subprocess.TimeoutExpired:
        if tmp_path.exists():
            tmp_path.unlink()
        return h._send_error_v59(500, error_code="FFMPEG_TIMEOUT",
                                  error_message="ffmpeg timed out after 120s", retry_safe=True)
    except Exception as e:
        if tmp_path.exists():
            tmp_path.unlink()
        return h._send_error_v59(500, error_code="FFMPEG_ERROR",
                                  error_message=str(e), retry_safe=True)

    # Update state
    def _apply(partition):
        b = (partition.get("beats") or {}).get(beat_id)
        if not b:
            return
        f = b.setdefault("final", {})
        f["pre_zoom_file"] = current_file
        f["file"] = zoom_filename
        f["zoom_applied"] = True
        f["file_exists"] = dst_path.is_file()

    h.app.state.mutate_video_state(video_role, _apply)
    return h._send_json(200, {"ok": True, "action": "zoom_applied",
                               "beat_id": beat_id, "zoom_file": zoom_filename,
                               "duration_s": round(duration_s, 2)})


