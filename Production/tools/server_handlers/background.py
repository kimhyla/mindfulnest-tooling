"""Background / magic / animate handlers — V59 Phase 4 Pass 2.

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
    _ASSEMBLE_JOBS,
    _GPT_JOBS,
    _MAGIC_JOBS,
    _SPEAKER_ALIAS,
)

# V59 Phase 4 path-depth correction: extracted modules are one level
# deeper than production_server.py. _PSERVER_TOOLS_DIR is for CODE-tree
# lookups (sibling Python modules, sys.path inserts). NOT used for data
# paths — those come from _data_root(h) per LD-505 Phase C (2026-05-19).
_PSERVER_TOOLS_DIR = Path(__file__).resolve().parent.parent  # Production/tools/


def _data_root(h) -> Path:
    """Runtime ``Production/`` root, anchored on the running server's event_dir.

    Replaces the LD-505-broken `_PSERVER_PRODUCTION_DIR = Path(__file__)...`
    which resolved to the (empty) tooling tree. Audit C1-1 / C1-2 / C1-7.
    """
    return Path(h.app.event_dir).parent


# Project-internal modules imported the same way production_server.py does.
# Handler bodies may reference any of these by bare name.
from lib.atomic_json_write import atomic_json_write
from lib.v3_partition import _iter_v3_beats
from lib.paths import DROPBOX_ROOT

# V59 Phase 4 cross-review fix (CI follow-up):
# missing module-level references from extracted handler bodies.
from tools.production_server import (  # noqa: E402
    COST_PER_CLIP_KLING,
    POLL_BATCH_GAP_SEC,
)
import scope_router
from ffmpeg_utils import strip_audio as _strip_clip_audio
from lipsync_sender import LipSyncClient, COST_PER_LIPSYNC
from server_handlers._path_security import (
    VIDEO_EXTENSIONS,
    require_media_under_project,
    require_path_under_anchor,
    require_realpath_under_project,
)

# Late-resolvable private helpers from the host module.
from tools.production_server import (  # noqa: E402
    _bg_capabilities,
    _bg_module,
    _bg_register_assembled_clip,
    _canonicalize_speaker,
    _ffprobe_duration,
    _find_beat_audio,
    _gpt_executor,
    _infer_animation_duration,
    _resolve_bg_segment_for_scope,
    _resolve_module_id_for_state,
    auto_upscale_image,
    build_motion_prompt,
    main,
    sanitize_prompt,
    validate_image_dimensions,
)

def serve_magic_picker(h)-> None:

    """Serve path_picker.html for the /magic route.

    Bug fix 2026-05-19: path_picker.html lives at Production/tools/path_picker.html
    (NOT Production/path_picker.html). The original constant after the Phase 4
    handler split was wrong — _PSERVER_PRODUCTION_DIR points to Production/ but
    the file is one level deeper at Production/tools/. Use _PSERVER_TOOLS_DIR.
    """
    import urllib.parse as _up
    picker = _PSERVER_TOOLS_DIR / "path_picker.html"
    if not picker.exists():
        return h._send_error_v59(
                   404,
                   error_code="PATH_PICKER_HTML_NOT_FOUND",
                   error_message="path_picker.html not found",
                   retry_safe=False,
               )
    html = picker.read_bytes()
    h.send_response(200)
    h.send_header("Content-Type", "text/html; charset=utf-8")
    h.send_header("Content-Length", str(len(html)))
    h._cors_headers()
    h.end_headers()
    h.wfile.write(html)


def handle_magic_resolve_bg(h)-> None:

    """Resolve background still path for a scene_key."""
    import urllib.parse as _up
    import yaml as _yaml
    qs = _up.parse_qs(_up.urlparse(h.path).query)
    scene_key = (qs.get("scene_key") or [None])[0]
    if not scene_key:
        return h._send_error_v59(
                   400,
                   error_code="SCENE_KEY_REQUIRED",
                   error_message="scene_key required",
                   retry_safe=False,
                   extra={"ok": False},
               )
    reg_path = _data_root(h) / "scene_registry.yaml"
    if not reg_path.exists():
        return h._send_error_v59(
                   404,
                   error_code="SCENE_REGISTRY_YAML_NOT_FOUND",
                   error_message="scene_registry.yaml not found",
                   retry_safe=False,
                   extra={"ok": False},
               )
    registry = _yaml.safe_load(reg_path.read_text()) or {}
    scene = registry.get(scene_key, {})
    # Resolve from well-known paths
    db = DROPBOX_ROOT
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
            return h._send_json(200, {"ok": True, "bg_url": bg_url, "bg_path": str(c)})
    return h._send_error_v59(
               404,
               error_code="GENERIC_ERROR",
               error_message=f"No background still found for {scene_key}",
               retry_safe=False,
               extra={"ok": False},
           )


def handle_magic_status(h)-> None:

    """Poll magic render job status."""
    import urllib.parse as _up
    qs = _up.parse_qs(_up.urlparse(h.path).query)
    job_id = (qs.get("job_id") or [None])[0]
    if not job_id:
        return h._send_error_v59(
                   400,
                   error_code="JOB_ID_REQUIRED",
                   error_message="job_id required",
                   retry_safe=False,
                   extra={"ok": False},
               )
    job = _MAGIC_JOBS.get(job_id)
    if not job:
        return h._send_error_v59(
                   404,
                   error_code="JOB_NOT_FOUND",
                   error_message="job not found",
                   retry_safe=False,
                   extra={"ok": False},
               )
    # Translate file paths to serveable URLs
    import urllib.parse as _up2
    resp = dict(job)
    for key in ("preview_path", "video_path"):
        if resp.get(key):
            resp[key + "_url"] = f"/files?path={_up2.quote(str(resp[key]))}"
    return h._send_json(200, {"ok": True, **resp})


def handle_magic_submit_path(h, body: dict)-> None:

    """Validate clicked path, write registry, kick off render pipeline."""
    # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return

    # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — capture pin at entry; terminal writes assert via _check_event_pin.
    _pin = {
        "pinned_generation": h.app.event_generation,
        "pinned_event_dir": h.app.event_dir,
        "pinned_video_role": (body or {}).get("scope_video_role", "intro"),
        "_handler": '_handle_magic_submit_path',
    }
    # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — pre-work pin check (S2).
    # If the event was swapped via /api/event/load between scope-guard
    # and work start, abort BEFORE any expensive work begins.
    if not h._check_event_pin(_pin, '_handle_magic_submit_path_pre_work'):
        return h._send_error_v59(
                   423,
                   error_code="EVENT_CHANGED_PRE_WORK",
                   error_message="event_changed_pre_work",
                   retry_safe=False,
                   extra={"code": "ASYNC_JOB_GENERATION_PIN_V1", "handler": '_handle_magic_submit_path', "hint": "Event changed between scope-guard and work start. "
                "No work was done; no orphan output. Client should "
                "re-hydrate scope and retry."},
               )

    import threading as _th
    import traceback as _tb
    import uuid as _uuid
    import urllib.parse as _up

    scene_key   = body.get("scene_key", "").strip()
    manual_path = body.get("manual_path", [])
    style       = body.get("style", "tessa_ori")

    # ── Validation ────────────────────────────────────────────────
    if not scene_key:
        return h._send_error_v59(
                   400,
                   error_code="SCENE_KEY_REQUIRED",
                   error_message="scene_key required",
                   retry_safe=False,
                   extra={"ok": False},
               )
    if not manual_path or not isinstance(manual_path, list):
        return h._send_error_v59(
                   400,
                   error_code="MANUAL_PATH_REQUIRED",
                   error_message="manual_path required",
                   retry_safe=False,
                   extra={"ok": False},
               )
    if len(manual_path) < 2:
        return h._send_error_v59(
                   400,
                   error_code="MANUAL_PATH_MUST_HAVE_POINTS",
                   error_message="manual_path must have ≥ 2 points",
                   retry_safe=False,
                   extra={"ok": False},
               )
    if len(manual_path) > 20:
        return h._send_error_v59(
                   400,
                   error_code="MANUAL_PATH_MAX_POINTS",
                   error_message="manual_path max 20 points",
                   retry_safe=False,
                   extra={"ok": False},
               )
    for i, pt in enumerate(manual_path):
        try:
            x, y = float(pt[0]), float(pt[1])
        except (TypeError, IndexError, ValueError):
            return h._send_error_v59(
                       400,
                       error_code="GENERIC_ERROR",
                       error_message=f"point {i} malformed: {pt}",
                       retry_safe=False,
                       extra={"ok": False},
                   )
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            return h._send_error_v59(
                       400,
                       error_code="GENERIC_ERROR",
                       error_message=f"point {i} out of range: [{x},{y}] must be in [0,1]",
                       retry_safe=False,
                       extra={"ok": False},
                   )

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
            reg_path = _data_root(h) / "scene_registry.yaml"
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
                if not h._check_event_pin(_pin, "magic_submit_path_registry_write"):
                    print(f"[magic_submit_path] event drift mid-thread; skipping registry write", flush=True)
                    return
                reg_path.write_text(_yaml.dump(registry, default_flow_style=False))

            # ── Step 2: Resolve background still ──────────────────
            _MAGIC_JOBS[job_id].update({"status": "rendering_preview",
                                        "message": "Resolving background still..."})
            db = DROPBOX_ROOT
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
            explicit_bg_raw = body.get("bg_path", "")
            if explicit_bg_raw:
                try:
                    explicit_bg = require_realpath_under_project(explicit_bg_raw)
                except ValueError:
                    raise FileNotFoundError(
                        f"bg_path outside project root: {explicit_bg_raw!r}"
                    ) from None
                safe_explicit_bg = os.path.realpath(explicit_bg)
                if os.path.isfile(safe_explicit_bg):
                    bg_path = safe_explicit_bg
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
            # magic_compositor lives at Production/tools/magic_compositor.py
            # (CODE tree). Use _PSERVER_TOOLS_DIR to be explicit about
            # code-vs-data intent per LD-505 Phase C lint guard.
            sys.path.insert(0, str(_PSERVER_TOOLS_DIR))
            from magic_compositor import MagicCompositor
            # LD-505 Phase C anchor — derive kling_clips dir from the scene's
            # event_id (resolved above from scene_registry.yaml), not the
            # legacy hardcoded "Event_1". Same idiom as event_dir on line 387.
            # [CONFIRMED against this function: event_id is set on line 386
            # from reg2 scene metadata; event_dir already uses this pattern.]
            out_dir = db / "Production" / f"Event_{event_id.replace('e','')}" / "kling_clips"
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
    return h._send_json(200, {
        "ok": True,
        "job_id": job_id,
        "poll": f"/api/magic/status?job_id={job_id}",
    })


def handle_magic_still(h, body: dict)-> None:

    """POST /api/storyboard/magic_still {beat_id, manual_path, source_image_path, scope_event_id}

    Per LD-468 MAGIC_TRAIL_ON_STILL_V1. Invokes magic_compositor with the
    still as background; renders animated mp4 of magic forming on the
    still.
    """
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return
    beat_id = (body or {}).get("beat_id")
    manual_path = (body or {}).get("manual_path") or []
    source_image_path_raw = (body or {}).get("source_image_path") or ""
    if not beat_id:
        return h._send_error_v59(
                   400,
                   error_code="MISSING_BEAT_ID",
                   error_message="beat_id required",
                   retry_safe=False,
               )
    if not source_image_path_raw:
        return h._send_error_v59(
                   400,
                   error_code="SOURCE_IMAGE_PATH_REQUIRED",
                   error_message="source_image_path required",
                   retry_safe=False,
               )
    ok, clean_path, err = h._validate_manual_path(manual_path)
    if not ok:
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=err,
                   retry_safe=False,
               )

    # Resolve absolute path for source image; reject paths outside project.
    # Security (CodeQL py/path-injection — separator-anchored containment +
    # no swallowed exception): naive startswith(root) lets sibling
    # '<root>_evil/...' slip past, and `except Exception: pass` silently
    # skipped the check on resolve() failures (long paths, broken symlinks).
    # Reject in BOTH failure modes; never let a path with unverified
    # containment flow into ffmpeg.
    sip = Path(source_image_path_raw)
    if not sip.is_absolute():
        sip = h.app.event_dir.parent.parent / source_image_path_raw
    # Sanitize beat_id BEFORE it flows into the on-disk filename via
    # f-string. Mirrors _handle_cr_save_crop (line ~10091-10095) — closes
    # MED-4 (magic_compositor.py label sanitizer is mooted when callers
    # pass an explicit output_path constructed from raw beat_id).
    if "/" in beat_id or "\\" in beat_id or ".." in beat_id or beat_id.startswith("."):
        return h._send_error_v59(
                   400,
                   error_code="INVALID_BEAT_ID",
                   error_message="invalid beat_id",
                   retry_safe=False,
               )
    import re as _re_mid_a
    if not _re_mid_a.match(r"^[A-Za-z0-9][A-Za-z0-9_-]*$", beat_id):
        return h._send_error_v59(
                   400,
                   error_code="INVALID_BEAT_ID",
                   error_message="beat_id must match [A-Za-z0-9_-]+",
                   retry_safe=False,
               )
    try:
        sip = require_path_under_anchor(str(sip), h.app.event_dir.parent.parent)
    except ValueError:
        return h._send_error_v59(
                   400,
                   error_code="SOURCE_IMAGE_PATH_OUTSIDE_PROJECT",
                   error_message="source_image_path outside project root",
                   retry_safe=False,
               )
    safe_sip = os.path.realpath(str(sip))
    if not os.path.isfile(safe_sip):
        return h._send_error_v59(
                   404,
                   error_code="SOURCE_IMAGE_NOT_FOUND",
                   error_message="source_image not found",
                   retry_safe=False,
                   extra={"path": safe_sip},
               )

    # LD-460 pin
    _pin = {
        "pinned_generation": h.app.event_generation,
        "pinned_event_dir": h.app.event_dir,
        "pinned_video_role": (body or {}).get("scope_video_role", "intro"),
        "_handler": "_handle_magic_still",
    }
    if not h._check_event_pin(_pin, "magic_still_pre_work"):
        return h._send_error_v59(
                   423,
                   error_code="EVENT_CHANGED_PRE_WORK",
                   error_message="event_changed_pre_work",
                   retry_safe=False,
                   extra={"code": "ASYNC_JOB_GENERATION_PIN_V1"},
               )

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = h.app.event_dir
    out_path = out_dir / f"magic_still_{beat_id}_{ts}.mp4"

    try:
        tools_dir = str(_PSERVER_TOOLS_DIR)
        if tools_dir not in sys.path:
            sys.path.insert(0, tools_dir)
        from magic_compositor import MagicCompositor  # type: ignore
        mc = MagicCompositor(
            background_path=safe_sip,
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
        return h._send_error_v59(
                   500,
                   error_code="GENERIC_ERROR",
                   error_message=f"magic_compositor failed: {type(exc).__name__}: {exc}",
                   retry_safe=True,
               )

    if not h._check_event_pin(_pin, "magic_still_terminal"):
        return h._send_error_v59(
                   423,
                   error_code="EVENT_CHANGED_MID_JOB",
                   error_message="event_changed_mid_job",
                   retry_safe=False,
                   extra={"code": "ASYNC_JOB_GENERATION_PIN_V1", "orphaned_output": str(rendered)},
               )

    registered_id: int | None = None
    try:
        from registered_write import register_asset  # type: ignore
        registered_id, _ = register_asset(
            file_path=str(rendered),
            asset_type="magic_clip",
            module_id=_resolve_module_id_for_state(h.app.state),
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

    # MAG-1 fix: write magic_still_path back into state.beats[beat_id] so
    # the client UI can render the "has magic" indicator + serve the
    # composite on next page load. Idempotent — re-rendering overwrites.
    magic_filename = Path(rendered).name
    try:
        scope = scope_router.resolve(body, h.app.event_dir.name)

        def _set_magic_still(partition: dict) -> None:
            beats = partition.setdefault("beats", {})
            beat = beats.setdefault(beat_id, {})
            beat["magic_still_path"] = magic_filename

        scope_router.mutate_partition(h.app.state, scope, _set_magic_still)
    except Exception as exc:
        print(f"[magic_still] WARN state writeback failed: {exc}", flush=True)

    return h._send_json(200, {
        "ok": True,
        "beat_id": beat_id,
        "composite_path": str(rendered),
        "magic_still_path": magic_filename,
        "asset_id": registered_id,
        "manual_path_points": len(clean_path),
    })


def handle_magic_video(h, body: dict)-> None:

    """POST /api/storyboard/magic_video {beat_id, manual_path, source_video_path, scope_event_id}

    Per LD-469 MAGIC_TRAIL_ON_VIDEO_V1. Generates magic-on-black via
    magic_compositor.render_video(black_bg=True), then ffmpeg overlays
    onto the source video via blend=mode=screen (black pixels become
    transparent in screen blend; magic pixels shine through additively).
    """
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return
    beat_id = (body or {}).get("beat_id")
    manual_path = (body or {}).get("manual_path") or []
    source_video_path_raw = (body or {}).get("source_video_path") or ""
    if not beat_id:
        return h._send_error_v59(
                   400,
                   error_code="MISSING_BEAT_ID",
                   error_message="beat_id required",
                   retry_safe=False,
               )
    if not source_video_path_raw:
        return h._send_error_v59(
                   400,
                   error_code="SOURCE_VIDEO_PATH_REQUIRED",
                   error_message="source_video_path required",
                   retry_safe=False,
               )
    ok, clean_path, err = h._validate_manual_path(manual_path)
    if not ok:
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=err,
                   retry_safe=False,
               )

    svp = Path(source_video_path_raw)
    if not svp.is_absolute():
        svp = h.app.event_dir.parent.parent / source_video_path_raw
    # Security (CodeQL py/path-injection alert #16 — separator-anchored
    # containment + no swallowed exception): naive startswith(root) lets
    # sibling '<root>_evil/...' slip past, and `except Exception: pass`
    # silently skipped the check on resolve() failures (long paths,
    # broken symlinks). Reject in BOTH failure modes; never let a path
    # with unverified containment flow into ffmpeg.
    if "/" in beat_id or "\\" in beat_id or ".." in beat_id or beat_id.startswith("."):
        return h._send_error_v59(
                   400,
                   error_code="INVALID_BEAT_ID",
                   error_message="invalid beat_id",
                   retry_safe=False,
               )
    import re as _re_mid_b
    if not _re_mid_b.match(r"^[A-Za-z0-9][A-Za-z0-9_-]*$", beat_id):
        return h._send_error_v59(
                   400,
                   error_code="INVALID_BEAT_ID",
                   error_message="beat_id must match [A-Za-z0-9_-]+",
                   retry_safe=False,
               )
    try:
        svp = require_path_under_anchor(str(svp), h.app.event_dir.parent.parent)
    except ValueError:
        return h._send_error_v59(
                   400,
                   error_code="SOURCE_VIDEO_PATH_OUTSIDE_PROJECT",
                   error_message="source_video_path outside project root",
                   retry_safe=False,
               )
    safe_svp_check = os.path.realpath(str(svp))
    if not os.path.isfile(safe_svp_check):
        return h._send_error_v59(
                   404,
                   error_code="SOURCE_VIDEO_NOT_FOUND",
                   error_message="source_video not found",
                   retry_safe=False,
                   extra={"path": safe_svp_check},
               )
    try:
        ffmpeg_src = require_media_under_project(
            str(svp), extensions=VIDEO_EXTENSIONS,
        )
    except ValueError as exc:
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=str(exc),
                   retry_safe=False,
               )

    safe_ffmpeg_src = os.path.realpath(ffmpeg_src)

    # ffprobe for dimensions + duration.
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height,duration",
             "-of", "json", safe_ffmpeg_src],
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
            vid_duration = float(_ffprobe_duration(Path(safe_ffmpeg_src)) or 0)
    except subprocess.CalledProcessError as exc:
        return h._send_error_v59(
                   500,
                   error_code="FFPROBE_FAILED",
                   error_message="ffprobe failed",
                   retry_safe=True,
                   extra={"stderr": exc.stderr.decode("utf-8", errors="replace")[-500:]},
               )
    if vid_duration <= 0:
        return h._send_error_v59(
                   500,
                   error_code="SOURCE_DURATION_UNAVAILABLE",
                   error_message="could not determine source duration",
                   retry_safe=True,
               )

    # LD-460 pin
    _pin = {
        "pinned_generation": h.app.event_generation,
        "pinned_event_dir": h.app.event_dir,
        "pinned_video_role": (body or {}).get("scope_video_role", "intro"),
        "_handler": "_handle_magic_video",
    }
    if not h._check_event_pin(_pin, "magic_video_pre_work"):
        return h._send_error_v59(
                   423,
                   error_code="EVENT_CHANGED_PRE_WORK",
                   error_message="event_changed_pre_work",
                   retry_safe=False,
                   extra={"code": "ASYNC_JOB_GENERATION_PIN_V1"},
               )

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = h.app.event_dir
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
        return h._send_error_v59(
                   500,
                   error_code="GENERIC_ERROR",
                   error_message=f"could not create black ref: {exc}",
                   retry_safe=True,
               )

    try:
        tools_dir = str(_PSERVER_TOOLS_DIR)
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
        return h._send_error_v59(
                   500,
                   error_code="GENERIC_ERROR",
                   error_message=f"magic_compositor (black_bg) failed: {type(exc).__name__}: {exc}",
                   retry_safe=True,
               )
    finally:
        try:
            black_ref.unlink(missing_ok=True)
        except Exception:
            pass

    # Step 2: ffmpeg overlay via blend=screen.
    cmd = [
        "ffmpeg", "-y",
        "-i", safe_ffmpeg_src,
        "-i", str(magic_only_path.resolve()),
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
        return h._send_error_v59(
                   500,
                   error_code="FFMPEG_BLEND_FAILED",
                   error_message="ffmpeg blend failed",
                   retry_safe=True,
                   extra={"stderr": exc.stderr.decode("utf-8", errors="replace")[-1000:]},
               )
    except subprocess.TimeoutExpired:
        return h._send_error_v59(
                   504,
                   error_code="FFMPEG_BLEND_TIMED_OUT",
                   error_message="ffmpeg blend timed out (>300s)",
                   retry_safe=True,
               )
    finally:
        try:
            magic_only_path.unlink(missing_ok=True)
        except Exception:
            pass

    if not h._check_event_pin(_pin, "magic_video_terminal"):
        return h._send_error_v59(
                   423,
                   error_code="EVENT_CHANGED_MID_JOB",
                   error_message="event_changed_mid_job",
                   retry_safe=False,
                   extra={"code": "ASYNC_JOB_GENERATION_PIN_V1", "orphaned_output": str(out_path)},
               )

    registered_id: int | None = None
    try:
        from registered_write import register_asset  # type: ignore
        registered_id, _ = register_asset(
            file_path=str(out_path),
            asset_type="magic_clip",
            module_id=_resolve_module_id_for_state(h.app.state),
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

    # MAG-1 fix: write magic_video_path back into state.beats[beat_id].
    # Same pattern as magic_still — see _handle_magic_still for rationale.
    magic_filename = Path(out_path).name
    try:
        scope = scope_router.resolve(body, h.app.event_dir.name)

        def _set_magic_video(partition: dict) -> None:
            beats = partition.setdefault("beats", {})
            beat = beats.setdefault(beat_id, {})
            beat["magic_video_path"] = magic_filename

        scope_router.mutate_partition(h.app.state, scope, _set_magic_video)
    except Exception as exc:
        print(f"[magic_video] WARN state writeback failed: {exc}", flush=True)

    return h._send_json(200, {
        "ok": True,
        "beat_id": beat_id,
        "composite_path": str(out_path),
        "magic_video_path": magic_filename,
        "asset_id": registered_id,
        "source_dims": [width, height],
        "duration_s": vid_duration,
        "manual_path_points": len(clean_path),
    })


def handle_bg_crop_preview(h)-> None:

    """GET /api/bg/crop-preview?keys=key1,key2,...
    Returns {key: data_uri} for each accepted crop key so the browser can
    populate TH[] and display beat thumbnails after a cold page reload."""
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(h.path).query)
    raw_keys = (qs.get("keys") or [""])[0]
    keys = [k.strip() for k in raw_keys.split(",") if k.strip()]
    if not keys:
        return h._send_error_v59(
                   400,
                   error_code="KEYS_PARAM_REQUIRED",
                   error_message="keys param required",
                   retry_safe=False,
               )

    # Security (CodeQL py/path-injection alerts #12, #13): reject any key
    # containing path separators, leading dot, or '..' to prevent traversal
    # outside crops_dir. Allow [A-Za-z0-9._-]+ basename only.
    import re as _re
    _SAFE_KEY = _re.compile(r"^[A-Za-z0-9_-][A-Za-z0-9._-]*$")
    for k in keys:
        if ".." in k or "/" in k or "\\" in k or k.startswith(".") or not _SAFE_KEY.match(k):
            return h._send_error_v59(
                       400,
                       error_code="GENERIC_ERROR",
                       error_message=f"invalid key: {k!r}",
                       retry_safe=False,
                   )

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
    return h._send_json(200, {"previews": result})


def handle_bg_segments(h)-> None:

    """GET /api/bg/segments?arc_number=N -> { segments: [...] }"""
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(h.path).query)
    arc_number = int((qs.get("arc_number") or [1])[0])
    bg = _bg_module()
    segments = bg.get_segments(arc_number)
    return h._send_json(200, {"segments": segments, "arc_number": arc_number})


def handle_bg_session_state(h)-> None:

    """GET /api/bg/session-state -> { active_context, beats, flux_options_complete,
    capabilities, migration_warnings, scope_active_context }

    LD-545 Option B: beats are derived from the request's scope_event_id /
    scope_arc_number / scope_phase, NOT from sidecar's active_context. The
    active_context is still returned for client visibility (BG segment
    dropdown becomes a secondary filter), but beats lookup is scope-
    canonical to fix Bug 2 (Add Beat → wrong segment) + Bug 4 (BG ref
    drop UI doesn't refresh) [CONFIRMED against
    V59_STORYBOARD_SIDEFIX_MORNING_REPORT_20260508.md §3 + LD-545
    decision_text].

    Rule 35 N/A here: bg.write_sidecar() is a LOCAL atomic JSON file
    write (json.dump + os.replace, [CONFIRMED against
    beat_generator.py:313 def write_sidecar — verified at PR-author
    time via grep]). It does NOT touch any Directus prod_* collection.
    Rule 35's try_post_or_queue requirement applies only to Directus
    writes.
    """
    # LD-456 SCOPE_VALIDATION_V1 (no-body handler — query-string fallback inside helper)
    if not h._assert_event_scope({}, allow_missing=True):
        return

    # Parse scope from query string. _assert_event_scope already validated
    # presence + match against h.app.event_dir; we re-parse here to
    # extract the values we need for segment derivation.
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(h.path).query)
    def _q(name: str, default=None):
        v = qs.get(name)
        return v[0] if v else default
    scope_event_id = _q("scope_event_id") or _q("event_id")
    scope_arc_raw = _q("scope_arc_number") or _q("arc_number")
    scope_phase = _q("scope_phase")  # may be None — derived from video role

    bg = _bg_module()
    with bg._sidecar_lock:
        sidecar = bg.read_sidecar()
        sidecar = bg._migrate_sidecar(sidecar)
        bg.write_sidecar(sidecar)
    ctx = sidecar.get("active_context")

    # LD-545 Option B — scope-derived segment.
    # Build the scope-canonical context. Fall back to sidecar's
    # active_context fields ONLY when the corresponding scope param
    # is missing (e.g. legacy clients that don't pass scope yet).
    scope_arc = None
    if scope_arc_raw is not None:
        try:
            scope_arc = int(scope_arc_raw)
        except (TypeError, ValueError):
            scope_arc = None
    if scope_arc is None and ctx:
        scope_arc = ctx.get("arc_number")
    if scope_event_id is None and ctx:
        scope_event_id = ctx.get("event_id")
    if scope_phase is None:
        # Phase derivation: prefer scope; fall back to sidecar ctx.phase;
        # final fallback "full". [CONFIRMED against _handle_bg_add_beat
        # SCOPE_ROUTER_V1 docstring at line ~9682] SCOPE_ROUTER_V1 maps
        # video roles intro→pre, resolution→post, standalone→main; here
        # we just pass through what client sent or what sidecar last
        # persisted.
        scope_phase = (ctx.get("phase") if ctx else None) or "full"

    scope_active_context = None
    beats = []
    if scope_arc is not None and scope_event_id is not None:
        seg = bg.get_seg_entry(sidecar, scope_arc, scope_event_id, scope_phase)
        beats = seg.get("beats", [])
        scope_active_context = {
            "arc_number": scope_arc,
            "event_id": scope_event_id,
            "phase": scope_phase,
        }

    # Migration warning if scope and sidecar's active_context disagree
    # (debug aid — surfaces the divergence Bug 2 + Bug 4 trip on).
    warnings = list(sidecar.get("migration_warnings", []))
    if ctx and scope_active_context and (
        ctx.get("arc_number") != scope_active_context["arc_number"]
        or ctx.get("event_id") != scope_active_context["event_id"]
        or (ctx.get("phase") or "full") != scope_active_context["phase"]
    ):
        warnings.append({
            "type": "scope_active_context_divergence",
            "message": (
                "scope_event_id derived segment differs from sidecar.active_context — "
                "scope is canonical per LD-545 Option B"
            ),
            "scope": scope_active_context,
            "active_context": ctx,
        })

    all_done = beats and all(b.get("flux_options") for b in beats)
    return h._send_json(200, {
        # `active_context` retained for backward compat (BG segment
        # dropdown reads it as secondary filter).
        "active_context": ctx,
        # New field per LD-545: the scope-derived context that beats
        # were actually computed from. Clients should treat this as
        # canonical for the rendered beats list.
        "scope_active_context": scope_active_context,
        "beats": beats,
        "flux_options_complete": bool(all_done),
        "capabilities": _bg_capabilities(),
        "migration_warnings": warnings,
    })


def handle_bg_poll_flux(h)-> None:

    """GET /api/bg/poll-flux-status?request_ids=id1,id2,...
    Server polls BFL for each id. Returns { id: { status, key, thumb_b64, gallery_b64 } | null }"""
    # LD-456 SCOPE_VALIDATION_V1 (no-body handler — query-string fallback inside helper)
    if not h._assert_event_scope({}, allow_missing=True):
        return

    qs = urllib.parse.parse_qs(urllib.parse.urlparse(h.path).query)
    raw = (qs.get("request_ids") or [""])[0]
    if not raw:
        return h._send_error_v59(
                   400,
                   error_code="REQUEST_IDS_REQUIRED",
                   error_message="request_ids required",
                   retry_safe=False,
               )
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

    return h._send_json(200, results)


def handle_bg_set_active_context(h, body: dict)-> None:

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
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
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
    return h._send_json(200, {"beats": beats, "had_saved": len(beats) > 0})


def handle_bg_extract_beats(h, body: dict)-> None:

    """POST /api/bg/extract-beats {arc_number, event_id, phase} -> { beats }

    NOTE: body['event_id'] is the BG segment number; storyboard scope
    guard uses body['scope_event_id'] when present.
    """
    # LD-456 SCOPE_VALIDATION_V1
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
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
    return h._send_json(200, {"beats": beats, "count": len(beats)})


def handle_bg_inject_beats(h, body: dict)-> None:

    """POST /api/bg/inject-beats {arc_number, event_id, phase, beats} -> { ok, count, beat_ids }
    Injects beats from the skeleton-to-beats skill directly into the beat generator sidecar.

    NOTE: body['event_id'] is the BG segment number; storyboard scope
    guard uses body['scope_event_id'] when present.
    """
    # LD-456 SCOPE_VALIDATION_V1
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return  # LD-461 SCOPE_BODY_HELPER_V1 — migrated from hand-rolled dict
    arc_number = int(body.get("arc_number", 1))
    event_id   = str(body.get("event_id", "1"))
    phase      = str(body.get("phase", "full"))
    incoming_beats = body.get("beats", [])
    if not incoming_beats:
        return h._send_error_v59(
                   400,
                   error_code="MISSING_BEATS_ARRAY",
                   error_message="beats array required",
                   retry_safe=False,
               )
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
    return h._send_json(200, {"ok": True, "count": len(mapped_beats), "beat_ids": beat_ids})


def handle_bg_update_beat(h, body: dict)-> None:

    """POST /api/bg/update-beat {beat_id, [field...], scope_event_id?} -> { ok }"""
    # LD-456 SCOPE_VALIDATION_V1 — uses scope_event_id to disambiguate from BG segment numbers.
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return  # LD-461 SCOPE_BODY_HELPER_V1 — migrated from hand-rolled dict
    beat_id = body.get("beat_id")
    if not beat_id:
        return h._send_error_v59(
                   400,
                   error_code="MISSING_BEAT_ID",
                   error_message="beat_id required",
                   retry_safe=False,
               )
    bg = _bg_module()
    _BG_BEAT_WRITABLE = frozenset({
        "speaker", "dialogue_text", "scene_notes", "emotion",
        "accepted_image_key", "reference_image", "bg_ref_image",
    })
    # BUG1FIX-20260507 — exclude scope/metadata keys that pathappPatch
    # auto-injects per LD-461 SCOPE_BODY_HELPER_V1 + LD-474
    # VIDEO_ROLE_PER_REQUEST_V1. They are required for the scope guard
    # at line ~9161 above, but are not writable beat fields. Without
    # this exclusion the BG-ref drop body 400s with
    # "Unknown beat fields: ['scope_event_id', ...]" because the
    # whitelist gate runs after the scope guard consumed those same keys.
    _BG_BEAT_SCOPE_KEYS = frozenset({
        "beat_id",
        "event_id", "scope_event_id",
        "scope_video_role", "scope_target_video",
        "scope_milestone_id",
        "scope_version",
    })
    unknown = set(body.keys()) - _BG_BEAT_WRITABLE - _BG_BEAT_SCOPE_KEYS
    if unknown:
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=f"Unknown beat fields: {sorted(unknown)}",
                   retry_safe=False,
                   extra={"ok": False},
               )
    # 2026-05-11 Rule 26 fix — when client drops a library image into
    # the Char ref / BG ref slot, server-side PIL thumbnail generation
    # ensures BgRefSlot displays the IMAGE (not the lib_key string).
    # Mirrors _handle_bg_accept_lib_image's thumbnail pattern.
    thumb_b64 = None
    with bg._sidecar_lock:
        sidecar = bg._load_sidecar_migrated()
        _, beat = bg.find_beat(sidecar, beat_id)
        if not beat:
            return h._send_error_v59(
                       404,
                       error_code="GENERIC_ERROR",
                       error_message=f"beat {beat_id} not found",
                       retry_safe=False,
                   )
        written = []
        for field in _BG_BEAT_WRITABLE:
            if field in body:
                value = body[field]
                # For reference_image / bg_ref_image: if abs_path is set
                # and the file exists, render a PIL thumbnail and inject
                # thumb_b64 so BgRefSlot can <img src=...> after refresh.
                if field in ("reference_image", "bg_ref_image") and isinstance(value, dict):
                    abs_path = value.get("abs_path") or ""
                    # CodeQL py/path-injection gate (LD CODEQL_PATH_INJECTION_NATIVE_PATTERN_REFACTOR_V1
                    # — supersedes LD-702/706). Inline realpath + startswith check on the SAME
                    # dataflow node that feeds os.path.exists / PIL.open. CodeQL's path-injection
                    # query recognizes realpath + startswith(ROOT + os.sep) as a native sanitizer;
                    # bool-returning helpers (is_path_under_library_root) get stripped by CodeQL's
                    # interprocedural analysis. Same safety guarantee, native signal.
                    _abs_resolved = os.path.realpath(abs_path) if isinstance(abs_path, str) and abs_path else ""
                    _safe = False
                    if _abs_resolved:
                        for _r in h.app._library_root_dirs():
                            if _r and (_abs_resolved == _r or _abs_resolved.startswith(_r + os.sep)):
                                _safe = True
                                break
                    if _safe and _abs_resolved:
                        _safe_open_path = os.path.realpath(_abs_resolved)
                    else:
                        _safe_open_path = ""
                    if _safe and _safe_open_path and os.path.exists(_safe_open_path) and not value.get("thumb_b64"):
                        try:
                            from PIL import Image as _PILImage
                            import io as _io_thumb
                            with _PILImage.open(_safe_open_path) as im:
                                im.thumbnail((200, 150), _PILImage.LANCZOS)
                                buf = _io_thumb.BytesIO()
                                im.convert("RGB").save(buf, "JPEG", quality=72)
                            _t = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
                            value = dict(value)
                            value["thumb_b64"] = _t
                            thumb_b64 = _t
                        except (OSError, ImportError) as _thumb_err:
                            print(f"[REFDROP] thumbnail skipped for {_abs_resolved!r}: {_thumb_err}", flush=True)
                beat[field] = value
                written.append(field)
        bg.write_sidecar(sidecar)
    return h._send_json(200, {"ok": True, "written": written, "thumb_b64": thumb_b64})


def handle_bg_reorder_beats(h, body: dict)-> None:

    """POST /api/bg/reorder-beats {beat_ids: [...], scope_event_id?} -> { ok }

    LD-545 Option B: segment is derived from scope_event_id /
    scope_arc_number / scope_phase in the body, NOT from sidecar's
    active_context. Falls back to active_context only when the
    corresponding scope key is missing (legacy clients).

    Rule 35 N/A: bg.write_sidecar() called below is a LOCAL atomic JSON
    file write (json.dump + os.replace, see beat_generator.py:313). NOT
    a Directus prod_* write. try_post_or_queue requirement does not
    apply.
    """
    # LD-456 SCOPE_VALIDATION_V1
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return  # LD-461 SCOPE_BODY_HELPER_V1 — migrated from hand-rolled dict
    beat_ids = body.get("beat_ids", [])
    if not beat_ids:
        return h._send_error_v59(
                   400,
                   error_code="MISSING_BEAT_IDS",
                   error_message="beat_ids required",
                   retry_safe=False,
               )
    bg = _bg_module()
    with bg._sidecar_lock:
        sidecar = bg.read_sidecar()
        ctx = sidecar.get("active_context")

        # LD-545 Option B — derive segment from request scope; fall
        # back to active_context only when scope is absent.
        scope_event_id = body.get("scope_event_id")
        if scope_event_id is None:
            scope_event_id = body.get("event_id")
        scope_arc_raw = body.get("scope_arc_number")
        if scope_arc_raw is None:
            scope_arc_raw = body.get("arc_number")
        scope_arc = None
        if scope_arc_raw is not None:
            try:
                scope_arc = int(scope_arc_raw)
            except (TypeError, ValueError):
                scope_arc = None
        scope_phase = body.get("scope_phase")
        if scope_arc is None and ctx:
            scope_arc = ctx.get("arc_number")
        if scope_event_id is None and ctx:
            scope_event_id = ctx.get("event_id")
        if scope_phase is None:
            scope_phase = (ctx.get("phase") if ctx else None) or "full"

        if scope_arc is None or scope_event_id is None:
            return h._send_error_v59(
                       400,
                       error_code="NO_SCOPE_OR_ACTIVE_CONTEXT",
                       error_message="no scope or active context",
                       retry_safe=False,
                   )

        scope_active_context = {
            "arc_number": scope_arc,
            "event_id": scope_event_id,
            "phase": scope_phase,
        }

        # Surface divergence between scope and sidecar.active_context
        # so the client can detect Bug 2 / Bug 4 style drift.
        if ctx and (
            ctx.get("arc_number") != scope_active_context["arc_number"]
            or ctx.get("event_id") != scope_active_context["event_id"]
            or (ctx.get("phase") or "full") != scope_active_context["phase"]
        ):
            warnings = list(sidecar.get("migration_warnings", []))
            warnings.append({
                "type": "scope_active_context_divergence",
                "message": (
                    "reorder-beats scope differs from sidecar.active_context — "
                    "scope is canonical per LD-545 Option B"
                ),
                "scope": scope_active_context,
                "active_context": ctx,
            })
            sidecar["migration_warnings"] = warnings

        # get_seg_entry signature: (sidecar, arc_number, event_id, phase="full")
        # — see beat_generator.get_seg_entry. The legacy two-arg form using
        # `segment_index` was incorrect and is replaced here.
        seg = bg.get_seg_entry(sidecar, scope_arc, scope_event_id, scope_phase)
        beats = seg.get("beats", [])
        beat_map = {b["beat_id"]: b for b in beats}
        seg["beats"] = [beat_map[bid] for bid in beat_ids if bid in beat_map]
        bg.write_sidecar(sidecar)
    return h._send_json(200, {"ok": True})


def handle_bg_delete_beat(h, body: dict)-> None:

    """POST /api/bg/delete-beat {beat_id} -> { ok }"""
    # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return

    beat_id = body.get("beat_id")
    if not beat_id:
        return h._send_error_v59(
                   400,
                   error_code="MISSING_BEAT_ID",
                   error_message="beat_id required",
                   retry_safe=False,
               )
    bg = _bg_module()
    with bg._sidecar_lock:
        sidecar = bg.read_sidecar()
        for arc in sidecar.get("arcs", {}).values():
            for seg in arc.get("segments", {}).values():
                seg["beats"] = [b for b in seg.get("beats", []) if b.get("beat_id") != beat_id]
        bg.write_sidecar(sidecar)
    return h._send_json(200, {"ok": True})


def handle_bg_accept_beats(h, body: dict)-> None:

    """POST /api/bg/accept-beats {beats, segment, scope_event_id?} -> { ok }
    Marks all beats as accepted in sidecar. Client already pushed to L[].
    Also deletes the storyboard L.json sidecar so pathappHydrate() on next
    reload does not overwrite L[] with the old pre-BG storyboard content.

    LD-456 SCOPE_VALIDATION_V1 — origin bug source. On 2026-05-01, BG on
    Event 2 → Accept All → Event 2 keys leaked into Event 1 storyboard
    because `sidecar_path` (line below) is derived from
    `h.app.event_dir` (server-pinned) but the BG sidecar's
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
        scope = scope_router.resolve(body, h.app.event_dir.name)
    except scope_router.ScopeError as e:
        return h._send_error_v59(
            e.http_status,
            error_code=e.code.upper(),
            error_message=e.code,
            retry_safe=False,
            extra=e.detail or None,
        )
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
        sidecar_path = h.app.event_dir / (h.app.storyboard_path.stem + ".L.json")
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
    # BG→Storyboard image-assignment transfer (2-Opus debate locked design).
    # Extends the existing speaker/text seed to also write image_overrides +
    # image_overrides_abs into the storyboard partition AND warm the in-memory
    # _image_overrides cache so animate/add_options calls don't read None
    # before lazy-hydration fires. The audit row below references these
    # via the outer-scope mirrors.
    _overwrite_log: dict[str, dict] = {}
    _warmed_count = 0
    _image_seeds: dict[str, str] = {}
    try:
        beats_raw = body.get("beats", [])
        # Build BG beat lookup for abs_path fallback (sidecar already written above).
        _bg_sidecar_snap = _bg_module().read_sidecar()
        _bg_beat_map: dict[str, dict] = {}
        # Sidecar structure: arcs → <arc_id> → segments → <seg_id> → beats
        # (NOT top-level segments — top-level key is "arcs")
        for _arc in _bg_sidecar_snap.get("arcs", {}).values():
            for _seg in _arc.get("segments", {}).values():
                for _b in _seg.get("beats", []):
                    _id = _b.get("beat_id") or _b.get("id", "")
                    if _id:
                        _bg_beat_map[_id] = _b
        storyboard_pos = 0
        state_seeds: dict[str, dict] = {}
        for beat in beats_raw:
            if not beat.get("accepted_image_key"):
                continue
            sb_bid = f"beat_{storyboard_pos + 1:02d}"
            raw_speaker = beat.get("speaker") or ""
            canonicalized = _canonicalize_speaker(raw_speaker) or ""
            # Resolve abs_path: primary = resolve_library_image_path (always
            # absolute, always current); fallback = BG sidecar
            # accepted_library_ref.abs_path. Never trust accepted_local_path
            # raw — may be relative path.
            image_key = beat.get("accepted_image_key")
            abs_path = None
            try:
                _resolved = h.app.resolve_library_image_path(image_key)
                if _resolved and os.path.isfile(_resolved):
                    abs_path = str(_resolved)
            except Exception:
                pass
            if not abs_path:
                _bg_beat = _bg_beat_map.get(beat.get("beat_id", ""), {})
                # Try accepted_local_path FIRST — authoritative for option-
                # accepted beats (set by bg_accept_option). accepted_library_ref
                # may be stale from a prior library drag that was later
                # overridden by an option selection.
                _local = _bg_beat.get("accepted_local_path")
                if _local:
                    _norm = _local if os.path.isabs(_local) else str(
                        h.app.event_dir.parent.parent / _local)
                    if os.path.isfile(_norm):
                        abs_path = _norm
                if not abs_path:
                    # Fallback: accepted_library_ref.abs_path (library drag).
                    _ref = _bg_beat.get("accepted_library_ref") or {}
                    _sidecar_abs = _ref.get("abs_path")
                    if _sidecar_abs and os.path.isfile(_sidecar_abs):
                        abs_path = _sidecar_abs
            state_seeds[sb_bid] = {
                "speaker": canonicalized,
                "text": beat.get("dialogue_text") or "",
                "image_key": image_key,
                "abs_path": abs_path,   # may be None — handled gracefully in partition seed
                "emotion": beat.get("emotion") or "",  # Fix 4: propagate BG sidecar emotion
                "scene_notes": beat.get("scene_notes") or "",  # Fix 6: stored for future motion use
            }
            storyboard_pos += 1
        if state_seeds:
            def _seed_partition(partition, _data=state_seeds, _owlog=_overwrite_log):
                pbeats = partition.setdefault("beats", {})
                pdo    = partition.setdefault("display_order", [])
                p_ov   = partition.setdefault("image_overrides", {})       # NEW
                p_abs  = partition.setdefault("image_overrides_abs", {})   # NEW
                # If display_order is a legacy int (pre-v3 fixture shape),
                # leave it alone — DISPLAY_ORDER_STRICT_V1 prune skips ints
                # and the renderer's strict gate handles the int form too.
                pdo_is_list = isinstance(pdo, list)
                for bid, fields in _data.items():
                    b = pbeats.setdefault(bid, {})
                    b["speaker"] = fields["speaker"]
                    b["text"]    = fields["text"]
                    # Fix 4: only write emotion if non-empty (don't overwrite existing with "")
                    if fields.get("emotion"):
                        b["emotion"] = fields["emotion"]
                    # Fix 6: propagate scene_notes for future motion-hint use
                    if fields.get("scene_notes"):
                        b["scene_notes"] = fields["scene_notes"]
                    if fields.get("image_key"):                            # NEW
                        prev = p_ov.get(bid)
                        if prev and prev != fields["image_key"]:
                            _owlog[bid] = {"prev_key": prev, "new_key": fields["image_key"]}
                        p_ov[bid] = fields["image_key"]
                    if fields.get("abs_path"):                             # NEW
                        p_abs[bid] = fields["abs_path"]
                    if pdo_is_list and bid not in pdo:
                        pdo.append(bid)
            h.app.state.mutate_video_state(scope.video_role, _seed_partition)
            # Warm in-memory cache so animate/add_options calls don't read None.
            _pending = h.app._pending_override_keys.get(scope.video_role, {})
            for sb_bid, fields in state_seeds.items():
                _ikey = fields.get("image_key")
                if not _ikey:
                    continue
                _image_seeds[sb_bid] = _ikey
                try:
                    _fullres = h.app.get_fullres_gallery_image(_ikey)
                    if _fullres:
                        h.app._image_overrides.setdefault(scope.video_role, {})[sb_bid] = _fullres
                        _warmed_count += 1
                except Exception:
                    pass
                _pending.pop(sb_bid, None)   # clear lazy-hydrate marker
            h.app.invalidate_beats_cache()
            print(f"[BG] seeded videos.{scope.video_role}.beats for storyboard beats: "
                  f"{list(state_seeds.keys())} (image_overrides={len(_image_seeds)}, "
                  f"warmed={_warmed_count}, overwrites={len(_overwrite_log)})")
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
                "image_overrides_seeded": _image_seeds,
                "image_overrides_warmed": _warmed_count,
                "image_override_overwrites": _overwrite_log,
                "ld": "BG_ACCEPT_BEATS_ACTIVITY_LOG_V1",
            },
        })
    except Exception as e:
        print(f"[BG] warning: BEAT_GEN_ACCEPT_ALL activity log failed: {e}")

    return h._send_json(200, {"ok": True, "accepted": len(beat_ids)})


def handle_bg_submit_flux(h, body: dict)-> None:

    """POST /api/bg/submit-flux-batch {beat_ids: [...]} -> { task_map }
    Burst-submits 3×N FLUX Kontext calls. Returns immediately with task_map."""
    # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return

    # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — capture pin at entry; terminal writes assert via _check_event_pin.
    _pin = {
        "pinned_generation": h.app.event_generation,
        "pinned_event_dir": h.app.event_dir,
        "pinned_video_role": (body or {}).get("scope_video_role", "intro"),
        "_handler": '_handle_bg_submit_flux',
    }

    beat_ids = body.get("beat_ids", [])
    if not beat_ids:
        return h._send_error_v59(
                   400,
                   error_code="MISSING_BEAT_IDS",
                   error_message="beat_ids required",
                   retry_safe=False,
               )

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
            if not h._check_event_pin(_pin, f"bg_submit_flux:{beat['beat_id']}"):
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

    return h._send_json(200, {"task_map": task_map, "beats_submitted": len(task_map)})


def handle_bg_submit_gpt_batch(h, body: dict)-> None:

    """POST /api/bg/submit-gpt-batch {beat_ids: [...]}
    Spawns GPT generation in background thread pool. Returns {job_id} immediately."""
    # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return

    # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — capture pin at entry; terminal writes assert via _check_event_pin.
    _pin = {
        "pinned_generation": h.app.event_generation,
        "pinned_event_dir": h.app.event_dir,
        "pinned_video_role": (body or {}).get("scope_video_role", "intro"),
        "_handler": '_handle_bg_submit_gpt_batch',
    }
    # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — pre-work pin check (S2).
    # If the event was swapped via /api/event/load between scope-guard
    # and work start, abort BEFORE any expensive work begins.
    if not h._check_event_pin(_pin, '_handle_bg_submit_gpt_batch_pre_work'):
        return h._send_error_v59(
                   423,
                   error_code="EVENT_CHANGED_PRE_WORK",
                   error_message="event_changed_pre_work",
                   retry_safe=False,
                   extra={"code": "ASYNC_JOB_GENERATION_PIN_V1", "handler": '_handle_bg_submit_gpt_batch', "hint": "Event changed between scope-guard and work start. "
                "No work was done; no orphan output. Client should "
                "re-hydrate scope and retry."},
               )

    import uuid as _uuid
    beat_ids = body.get("beat_ids", [])
    if not beat_ids:
        return h._send_error_v59(
                   400,
                   error_code="MISSING_BEAT_IDS",
                   error_message="beat_ids required",
                   retry_safe=False,
               )

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
                    if not h._check_event_pin(_pin, "bg_submit_gpt_batch_write_sidecar"):
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

    return h._send_json(200, {
        "ok": True, "job_id": job_id,
        "beat_ids": beat_ids, "total_options": len(beats_to_run) * 3,
    })


def handle_bg_poll_gpt_status(h)-> None:

    """GET /api/bg/poll-gpt-status?job_id=xxx
    Returns per-beat option results as they complete."""
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(h.path).query)
    job_id = (qs.get("job_id") or [""])[0]
    if not job_id or job_id not in _GPT_JOBS:
        return h._send_error_v59(
                   404,
                   error_code="GENERIC_ERROR",
                   error_message=f"job {job_id!r} not found",
                   retry_safe=False,
               )

    job = _GPT_JOBS[job_id]
    return h._send_json(200, {
        "status": job["status"],
        "results": job["results"],   # {beat_id: [{local_path, key, thumb_b64, ...}, ...]}
        "total": job["total"],
        "done_count": sum(len(v) for v in job["results"].values()),
    })


def handle_bg_accept_option(h, body: dict)-> None:

    """POST /api/bg/accept-option {beat_id, option_key} -> { ok }"""
    # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return

    beat_id    = body.get("beat_id")
    option_key = body.get("option_key")
    if not beat_id or not option_key:
        return h._send_error_v59(
                   400,
                   error_code="MISSING_BEAT_ID_OR_OPTION_KEY",
                   error_message="beat_id and option_key required",
                   retry_safe=False,
               )
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
                   )
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
    return h._send_json(200, {"ok": True})


def handle_bg_accept_lib_image(h, body: dict)-> None:

    """POST /api/bg/accept-lib-image {beat_id, key, filename, abs_path, slot_index}
    Writes accepted_library_ref + accepted_image_key to sidecar.
    Does NOT touch flux_options[]. Library assignment is tracked separately
    so the existing FLUX option display/crop flow is completely unaffected."""
    # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return

    beat_id    = body.get("beat_id", "")
    key        = body.get("key", "")
    filename   = body.get("filename", "")
    abs_path   = body.get("abs_path", "")
    slot_index = int(body.get("slot_index", 0))
    if not beat_id or not key:
        return h._send_error_v59(
                   400,
                   error_code="MISSING_BEAT_ID_OR_KEY",
                   error_message="beat_id and key required",
                   retry_safe=False,
               )
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
                   )
        beat["accepted_library_ref"] = {
            "key": key, "filename": filename,
            "abs_path": abs_path, "slot_index": slot_index
        }
        beat["accepted_image_key"] = key
        beat["status"] = "lib_chosen"

        # Generate PIL thumbnail from abs_path and inject into gpt_options[slot_index]
        # so BgOptionTile renders thumb_b64 after drop (Layer 5 of six-layer verify).
        # Mirrors _read_image at production_server.py ~line 6192.
        thumb_b64 = None
        try:
            # CodeQL py/path-injection gate (LD CODEQL_PATH_INJECTION_NATIVE_PATTERN_REFACTOR_V1
            # — supersedes LD-702/706). Inline realpath + startswith check on the SAME dataflow
            # node that feeds os.path.exists / PIL.open. Native CodeQL-recognized sanitizer.
            _abs_resolved = os.path.realpath(abs_path) if isinstance(abs_path, str) and abs_path else ""
            _safe = False
            if _abs_resolved:
                for _r in h.app._library_root_dirs():
                    if _r and (_abs_resolved == _r or _abs_resolved.startswith(_r + os.sep)):
                        _safe = True
                        break
            _safe_open_path = os.path.realpath(_abs_resolved) if _safe and _abs_resolved else ""
            if _safe and _safe_open_path and os.path.exists(_safe_open_path):
                from PIL import Image as _PILImage
                import io as _io_thumb
                with _PILImage.open(_safe_open_path) as im:
                    im.thumbnail((200, 150), _PILImage.LANCZOS)
                    buf = _io_thumb.BytesIO()
                    im.convert("RGB").save(buf, "JPEG", quality=72)
                thumb_b64 = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
        except (OSError, ImportError) as _thumb_err:
            print(f"[LIBDROP] thumbnail skipped for {abs_path!r}: {_thumb_err}", flush=True)
            thumb_b64 = None

        if thumb_b64:
            opts = beat.get("gpt_options") or []
            option_entry = {
                "key": key,
                "thumb_b64": thumb_b64,
                "source": "library_drop",
                "local_path": abs_path,
                "filename": filename,
            }
            if slot_index < len(opts) and isinstance(opts[slot_index], dict):
                opts[slot_index].update(option_entry)
            else:
                # Pad with None up to slot_index, then place the entry.
                while len(opts) < slot_index:
                    opts.append(None)
                if slot_index < len(opts):
                    opts[slot_index] = option_entry
                else:
                    opts.append(option_entry)
            beat["gpt_options"] = opts

        bg.write_sidecar(sidecar)
    print(f"[LIBDROP] accepted library image {key!r} -> beat {beat_id} (thumb={'yes' if thumb_b64 else 'no'})", flush=True)
    return h._send_json(200, {"ok": True, "beat_id": beat_id,
                                 "accepted_image_key": key,
                                 "thumb_b64": thumb_b64,
                                 "slot_index": slot_index})


def handle_bg_groups(h)-> None:

    qs = urllib.parse.parse_qs(urllib.parse.urlparse(h.path).query)
    arc_n = int((qs.get("arc") or [1])[0])
    bg = _bg_module()
    with bg._sidecar_lock:
        sidecar = bg.read_sidecar()
        sidecar = bg._migrate_sidecar(sidecar)
        groups = bg.list_groups(sidecar, arc_n)
        for g in groups:
            g["status"] = bg._compute_group_status(sidecar, g)
    return h._send_json(200, {"ok": True, "groups": groups})


def handle_bg_add_beat(h, body: dict)-> None:

    """POST /api/bg/add-beat {after_beat_id, segment} -> {ok, beat}
    Inserts a blank beat immediately after after_beat_id in the sidecar.
    beat_id is generated as max(existing_N)+1 (zero-padded to 2 digits)
    so gaps from prior deletes do not cause collisions.

    Segment derivation per BG_ADD_BEAT_ACTIVE_CONTEXT_V1 (locked
    2026-05-13): the BG tab is a MULTI-SEGMENT authoring tool by
    design — its segment dropdown lets the user select any arc/event/
    phase regardless of which event the storyboard tool is pinned to.
    Segment for this write is therefore derived from (in priority):
      1. Client's explicit `segment` field (e.g. "event_2_pre")
      2. Sidecar `active_context` (server-side memory of last BG dropdown choice)
      3. Storyboard scope-router fallback (only when BG sidecar has no
         active_context yet — first-use case).
    This supersedes the K3 BG_HARDCODED_SCOPE_PURGE_V1 storyboard-pin
    constraint for BG-add-beat ONLY — storyboard-pin remains canonical
    for partition writes per scope_router.mutate_partition; BG sidecar
    is a separate authoring surface keyed by (arc, event_id_int, phase).
    """
    # Scope still validated for security (event_id must match running server).
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

    # Segment derivation — priority 1: client's explicit `segment` field.
    # Format "event_<N>_<phase>" matches what BgTab.tsx sends at line ~303.
    segment_raw = (body or {}).get("segment", "")
    arc_number: int | None = None
    event_id_int: int | None = None
    phase: str | None = None
    if segment_raw:
        seg_match = re.match(r"^event_(\d+)_(\w+)$", segment_raw)
        if seg_match:
            event_id_int = int(seg_match.group(1))
            phase = seg_match.group(2)
            # BG sidecar is single-arc today; arc derives from scope.
            # When multi-arc lands, the client should pass arc in segment.
            arc_number = 1

    # Priority 2: sidecar active_context (BG dropdown's persisted choice).
    if event_id_int is None or phase is None:
        bg_module = _bg_module()
        with bg_module._sidecar_lock:
            _ctx_sidecar = bg_module.read_sidecar()
            _ctx = _ctx_sidecar.get("active_context") or {}
        if _ctx:
            try:
                arc_number = int(_ctx.get("arc_number", 1))
                event_id_int = int(_ctx.get("event_id", 0)) or None
                phase = _ctx.get("phase") or None
            except (TypeError, ValueError):
                pass

    # Priority 3: scope-router fallback (first-use case where BG sidecar
    # has no active_context yet — usually only triggers in fresh sidecars).
    if event_id_int is None or phase is None:
        try:
            arc_number, event_id_int, phase = _resolve_bg_segment_for_scope(
                scope.event_id, scope.video_role,
            )
        except ValueError as exc:
            return h._send_error_v59(
                       400,
                       error_code="BG_SEGMENT_UNRESOLVED",
                       error_message="bg_segment_unresolved",
                       retry_safe=False,
                       extra={"detail": str(exc), "hint": "No BG segment could be derived: client did not "
                    "send `segment` field, sidecar has no active_context, "
                    "and storyboard scope is unparseable. Pick a segment "
                    "in the BG dropdown before adding a beat."},
                   )

    after_beat_id = body.get("after_beat_id", "")

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

    print(
        f"[BG] add-beat: inserted {new_beat_id} into "
        f"arc{arc_number}/event_{event_id_int}_{phase} "
        f"after {after_beat_id!r} (segment_source="
        f"{'client_field' if segment_raw else 'sidecar_ctx_or_scope'})"
    )
    return h._send_json(200, {
        "ok": True,
        "beat": new_beat,
        "segment": f"event_{event_id_int}_{phase}",
        "arc_number": arc_number,
    })


def handle_bg_create_group(h, body: dict)-> None:

    # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return

    name = (body.get("group_name") or "").strip()
    arc_n = int(body.get("arc_number", 1))
    beat_ids = body.get("beat_ids", [])
    if not name:
        return h._send_error_v59(
                   400,
                   error_code="GROUP_NAME_EMPTY",
                   error_message="group_name empty",
                   retry_safe=False,
                   extra={"ok": False},
               )
    if not beat_ids:
        return h._send_error_v59(
                   400,
                   error_code="BEAT_IDS_EMPTY",
                   error_message="beat_ids empty",
                   retry_safe=False,
                   extra={"ok": False},
               )
    bg = _bg_module()
    with bg._sidecar_lock:
        sidecar = bg.read_sidecar()
        sidecar = bg._migrate_sidecar(sidecar)
        try:
            gid = bg.create_group(sidecar, name, arc_n, beat_ids)
        except ValueError as e:
            return h._send_error_v59(
                       400,
                       error_code="GENERIC_ERROR",
                       error_message=str(e),
                       retry_safe=False,
                       extra={"ok": False},
                   )
        bg.write_sidecar(sidecar)
    return h._send_json(200, {"ok": True, "group_id": gid,
                                  "status": sidecar["groups"][gid]["status"]})


def handle_bg_delete_group(h, body: dict)-> None:

    # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return

    gid = body.get("group_id", "")
    if not gid:
        return h._send_error_v59(
                   400,
                   error_code="GROUP_ID_REQUIRED",
                   error_message="group_id required",
                   retry_safe=False,
                   extra={"ok": False},
               )
    bg = _bg_module()
    with bg._sidecar_lock:
        sidecar = bg.read_sidecar()
        sidecar = bg._migrate_sidecar(sidecar)
        if not bg.delete_group(sidecar, gid):
            return h._send_error_v59(
                       404,
                       error_code="GROUP_NOT_FOUND",
                       error_message="group not found",
                       retry_safe=False,
                       extra={"ok": False},
                   )
        bg.write_sidecar(sidecar)
    return h._send_json(200, {"ok": True})


def handle_bg_update_group(h, body: dict)-> None:

    # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return

    gid = body.get("group_id", "")
    ordered = body.get("beat_ids_ordered", [])
    if not gid:
        return h._send_error_v59(
                   400,
                   error_code="GROUP_ID_REQUIRED",
                   error_message="group_id required",
                   retry_safe=False,
                   extra={"ok": False},
               )
    bg = _bg_module()
    with bg._sidecar_lock:
        sidecar = bg.read_sidecar()
        sidecar = bg._migrate_sidecar(sidecar)
        if gid not in sidecar.get("groups", {}):
            return h._send_error_v59(
                       404,
                       error_code="GROUP_NOT_FOUND",
                       error_message="group not found",
                       retry_safe=False,
                       extra={"ok": False},
                   )
        new_status = bg.update_group_order(sidecar, gid, ordered)
        bg.write_sidecar(sidecar)
    return h._send_json(200, {"ok": True, "status": new_status})


def handle_bg_assemble_group(h, body: dict)-> None:

    # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return

    # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — capture pin at entry; terminal writes assert via _check_event_pin.
    _pin = {
        "pinned_generation": h.app.event_generation,
        "pinned_event_dir": h.app.event_dir,
        "pinned_video_role": (body or {}).get("scope_video_role", "intro"),
        "_handler": '_handle_bg_assemble_group',
    }
    # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — pre-work pin check (S2).
    # If the event was swapped via /api/event/load between scope-guard
    # and work start, abort BEFORE any expensive work begins.
    if not h._check_event_pin(_pin, '_handle_bg_assemble_group_pre_work'):
        return h._send_error_v59(
                   423,
                   error_code="EVENT_CHANGED_PRE_WORK",
                   error_message="event_changed_pre_work",
                   retry_safe=False,
                   extra={"code": "ASYNC_JOB_GENERATION_PIN_V1", "handler": '_handle_bg_assemble_group', "hint": "Event changed between scope-guard and work start. "
                "No work was done; no orphan output. Client should "
                "re-hydrate scope and retry."},
               )

    gid = body.get("group_id", "")
    if not gid:
        return h._send_error_v59(
                   400,
                   error_code="GROUP_ID_REQUIRED",
                   error_message="group_id required",
                   retry_safe=False,
                   extra={"ok": False},
               )
    bg = _bg_module()
    with bg._sidecar_lock:
        sidecar = bg.read_sidecar()
        sidecar = bg._migrate_sidecar(sidecar)
        g = sidecar.get("groups", {}).get(gid)
        if not g:
            return h._send_error_v59(
                       404,
                       error_code="GROUP_NOT_FOUND",
                       error_message="group not found",
                       retry_safe=False,
                       extra={"ok": False},
                   )
        status = bg._compute_group_status(sidecar, g)
        if status != "ready":
            return h._send_error_v59(
                       400,
                       error_code="GENERIC_ERROR",
                       error_message=f"group status is '{status}', must be 'ready'",
                       retry_safe=False,
                       extra={"ok": False},
                   )
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
                if not h._check_event_pin(_pin, "bg_assemble_group_write_sidecar"):
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
    return h._send_json(200, {"ok": True, "status": "assembling",
                                  "poll": f"/api/bg/poll-assemble-status?group_id={gid}"})


def handle_bg_poll_assemble_status(h)-> None:

    qs = urllib.parse.parse_qs(urllib.parse.urlparse(h.path).query)
    gid = (qs.get("group_id") or [None])[0]
    if not gid:
        return h._send_error_v59(
                   400,
                   error_code="GROUP_ID_REQUIRED",
                   error_message="group_id required",
                   retry_safe=False,
                   extra={"ok": False},
               )
    job = _ASSEMBLE_JOBS.get(gid)
    if not job:
        return h._send_error_v59(
                   404,
                   error_code="NO_ASSEMBLE_JOB_FOUND_FOR",
                   error_message="no assemble job found for group_id",
                   retry_safe=False,
                   extra={"ok": False},
               )
    return h._send_json(200, {"ok": True, **job})


def handle_bg_run_local_animation(h, body: dict)-> None:

    # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return

    # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — capture pin at entry; terminal writes assert via _check_event_pin.
    _pin = {
        "pinned_generation": h.app.event_generation,
        "pinned_event_dir": h.app.event_dir,
        "pinned_video_role": (body or {}).get("scope_video_role", "intro"),
        "_handler": '_handle_bg_run_local_animation',
    }
    # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — pre-work pin check (S2).
    # If the event was swapped via /api/event/load between scope-guard
    # and work start, abort BEFORE any expensive work begins.
    if not h._check_event_pin(_pin, '_handle_bg_run_local_animation_pre_work'):
        return h._send_error_v59(
                   423,
                   error_code="EVENT_CHANGED_PRE_WORK",
                   error_message="event_changed_pre_work",
                   retry_safe=False,
                   extra={"code": "ASYNC_JOB_GENERATION_PIN_V1", "handler": '_handle_bg_run_local_animation', "hint": "Event changed between scope-guard and work start. "
                "No work was done; no orphan output. Client should "
                "re-hydrate scope and retry."},
               )

    beat_id = body.get("beat_id", "")
    method = body.get("method", "")
    params = body.get("params", {}) or {}
    preview_only = bool(body.get("preview_only", False))
    VALID_METHODS = {"magic_compositor", "ken_burns", "static_hold"}
    if method not in VALID_METHODS:
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=f"method must be one of {sorted(VALID_METHODS)}",
                   retry_safe=False,
                   extra={"ok": False},
               )
    bg = _bg_module()
    with bg._sidecar_lock:
        sidecar = bg.read_sidecar()
        sidecar = bg._migrate_sidecar(sidecar)
        ctx = sidecar.get("active_context") or {}
        # LD-545 Option B — derive arc from scope; fall back to ctx for legacy.
        # arc_n here is only a performance hint for `_index_beats`. The
        # outer claim that "[INFERRED — verify against find_beat usage in
        # beat_generator.py] beat_id is unique across arcs per the
        # find_beat lookup convention" is not formally proven in code —
        # the [INFERRED — verify] tag covers the entire claim including
        # the sub-clause about uniqueness. find_beat at beat_generator.py
        # iterates all arcs/segments and returns first match, so duplicate
        # beat_ids across arcs would silently pick whichever arc/segment
        # comes first — supporting the convention even if not enforced.
        # We still prefer the scope-derived value to keep handlers
        # consistent regardless of beat_id uniqueness.
        scope_arc_raw = body.get("scope_arc_number")
        if scope_arc_raw is None:
            scope_arc_raw = body.get("arc_number")
        scope_arc = None
        if scope_arc_raw is not None:
            try:
                scope_arc = int(scope_arc_raw)
            except (TypeError, ValueError):
                scope_arc = None
        if scope_arc is None:
            scope_arc = ctx.get("arc_number", 1)
        arc_n = scope_arc
        beats_by_id = bg._index_beats(sidecar, arc_n)
        beat = beats_by_id.get(beat_id)
        if not beat:
            return h._send_error_v59(
                       404,
                       error_code="GENERIC_ERROR",
                       error_message=f"beat_id {beat_id} not found",
                       retry_safe=False,
                       extra={"ok": False},
                   )
        try:
            if method == "magic_compositor":
                bg_path = params.get("background_path", "")
                path_pts = params.get("path_pts", [])
                style = params.get("style", "tessa_ori")
                duration = float(params.get("duration", 3.5))
                if not bg_path or not path_pts:
                    return h._send_error_v59(
                               400,
                               error_code="PARAMS_MISSING_BACKGROUND_PATH_OR",
                               error_message="params missing background_path or path_pts",
                               retry_safe=False,
                               extra={"ok": False},
                           )
                if preview_only:
                    import sys as _sys
                    _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
                    from magic_compositor import MagicCompositor, STYLES
                    if style not in STYLES:
                        return h._send_error_v59(
                                   400,
                                   error_code="STYLE_NOT_APPROVED",
                                   error_message="style not approved",
                                   retry_safe=False,
                                   extra={"ok": False},
                               )
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
                    return h._send_json(200, {"ok": True, "preview_path": preview_path})
                result = bg.run_magic_compositor(beat, bg_path, path_pts, style, duration)
            elif method == "ken_burns":
                still = params.get("still_path", "")
                if not still:
                    return h._send_error_v59(
                               400,
                               error_code="PARAMS_MISSING_STILL_PATH",
                               error_message="params missing still_path",
                               retry_safe=False,
                               extra={"ok": False},
                           )
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
                    return h._send_error_v59(
                               400,
                               error_code="PARAMS_MISSING_STILL_PATH",
                               error_message="params missing still_path",
                               retry_safe=False,
                               extra={"ok": False},
                           )
                result = bg.run_static_hold(
                    beat, still, float(params.get("duration", 4.0))
                )
            # LD-460 — pin check before sidecar write.
            if not h._check_event_pin(_pin, "bg_run_local_animation_write_sidecar"):
                print(f"[bg_run_local_animation] event drift; skipping sidecar write", flush=True)
                return h._send_error_v59(
                           423,
                           error_code="EVENT_CHANGED_MID_JOB",
                           error_message="event_changed_mid_job",
                           retry_safe=False,
                           extra={"code": "ASYNC_JOB_GENERATION_PIN_V1"},
                       )
            bg.write_sidecar(sidecar)
        except Exception as e:
            traceback.print_exc()
            return h._send_error_v59(
                       500,
                       error_code="GENERIC_ERROR",
                       error_message=str(e),
                       retry_safe=True,
                       extra={"ok": False},
                   )
    return h._send_json(200, {"ok": True, **result})


def handle_bg_update_beat_anim_method(h, body: dict)-> None:

    # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return

    beat_id = body.get("beat_id", "")
    method = body.get("animation_method", "")
    VALID = {"kling", "magic_compositor", "ken_burns", "static_hold"}
    if not beat_id:
        return h._send_error_v59(
                   400,
                   error_code="MISSING_BEAT_ID",
                   error_message="beat_id required",
                   retry_safe=False,
                   extra={"ok": False},
               )
    if method not in VALID:
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=f"invalid method; valid: {sorted(VALID)}",
                   retry_safe=False,
                   extra={"ok": False},
               )
    bg = _bg_module()
    with bg._sidecar_lock:
        sidecar = bg.read_sidecar()
        sidecar = bg._migrate_sidecar(sidecar)
        _, b = bg.find_beat(sidecar, beat_id)
        if not b:
            return h._send_error_v59(
                       404,
                       error_code="GENERIC_ERROR",
                       error_message=f"beat_id {beat_id} not found",
                       retry_safe=False,
                       extra={"ok": False},
                   )
        b["animation_method"] = method
        bg.write_sidecar(sidecar)
    return h._send_json(200, {"ok": True})


def handle_bg_accept_local_animation(h, body: dict)-> None:

    # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return

    beat_id = body.get("beat_id", "")
    video_path = body.get("video_path", "")
    if not beat_id or not video_path:
        return h._send_error_v59(
                   400,
                   error_code="BEAT_ID_AND_VIDEO_PATH",
                   error_message="beat_id and video_path required",
                   retry_safe=False,
                   extra={"ok": False},
               )
    try:
        video_path = require_media_under_project(
            video_path, extensions=VIDEO_EXTENSIONS,
        )
    except ValueError as exc:
        return h._send_error_v59(
                   403,
                   error_code="GENERIC_ERROR",
                   error_message=str(exc),
                   retry_safe=False,
                   extra={"ok": False},
               )
    except FileNotFoundError:
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=f"video file not found: {video_path}",
                   retry_safe=False,
                   extra={"ok": False},
               )
    safe_video_path = os.path.realpath(video_path)
    bg = _bg_module()
    import pathlib as _pl
    if not bg._ffprobe_ok(_pl.Path(safe_video_path)):
        return h._send_error_v59(
                   400,
                   error_code="VIDEO_FAILED_FFPROBE_VALIDATION",
                   error_message="video failed ffprobe validation",
                   retry_safe=False,
                   extra={"ok": False},
               )
    with bg._sidecar_lock:
        sidecar = bg.read_sidecar()
        sidecar = bg._migrate_sidecar(sidecar)
        _, b = bg.find_beat(sidecar, beat_id)
        if not b:
            return h._send_error_v59(
                       404,
                       error_code="GENERIC_ERROR",
                       error_message=f"beat_id {beat_id} not found",
                       retry_safe=False,
                       extra={"ok": False},
                   )
        b["status"] = "accepted"
        b["accepted_video_path"] = safe_video_path
        gid = b.get("group_id")
        if gid and gid in sidecar.get("groups", {}):
            g = sidecar["groups"][gid]
            g["status"] = bg._compute_group_status(sidecar, g)
        bg.write_sidecar(sidecar)
    return h._send_json(200, {"ok": True})


def handle_bg_stills(h, path: str)-> None:

    """GET /bg-stills/<filename> — serve a FLUX still PNG from beat_generator_stills/.
    Path-traversal-safe: only direct children of BG_STILLS_DIR are served.
    Fix-C: eliminates ephemeral TH thumbnail cache dependency after page refresh."""
    raw = path[len("/bg-stills/"):]
    filename = urllib.parse.unquote(raw)
    # Reject traversal attempts before resolve
    if not filename or "/" in filename or "\\" in filename or ".." in filename or "\x00" in filename:
        return h._send_error_v59(
                   400,
                   error_code="INVALID_FILENAME",
                   error_message="invalid filename",
                   retry_safe=False,
               )
    bg = _bg_module()
    stills_dir = Path(bg.BG_STILLS_DIR).resolve()
    target = (stills_dir / filename).resolve()
    # Only direct children (not subdirectories like local_renders/)
    if target.parent != stills_dir:
        return h._send_error_v59(
                   403,
                   error_code="FORBIDDEN",
                   error_message="forbidden",
                   retry_safe=False,
               )
    if not target.exists():
        # GPT stills are saved as <key>_<timestamp>.ext — try prefix glob
        stem = Path(filename).stem   # key without extension
        ext  = Path(filename).suffix or ".png"
        candidates = sorted(stills_dir.glob(f"{stem}_*{ext}"))
        if candidates:
            target = candidates[-1]   # most recent by name (timestamps sort lexicographically)
        else:
            return h._send_error_v59(
                       404,
                       error_code="NOT_FOUND",
                       error_message="not found",
                       retry_safe=False,
                   )
    ext = target.suffix.lower()
    ct_map = {".png": "image/png", ".jpg": "image/jpeg",
              ".jpeg": "image/jpeg", ".webp": "image/webp"}
    ct = ct_map.get(ext, "application/octet-stream")
    data = target.read_bytes()
    return h._send_bytes(200, data, ct, {"Cache-Control": "no-cache"})


def handle_animate(h, body: dict)-> None:

    # SCOPE_ROUTER_V1 (C-7.5 K1 sibling fix) — replaces legacy
    # _assert_event_scope + scope_video_role-default-to-intro
    # pattern. Mutators below route partition writes via
    # mutate_video_state(scope.video_role, ...) instead of the
    # hardcoded videos.intro setdefault chain that was caught by the
    # SCOPE_ROUTER_V1 AST grep gate.
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

    if h.app.client is None:
        return h._send_error_v59(
                   500,
                   error_code="WAVESPEED_NOT_CONFIGURED",
                   error_message="WaveSpeed client not configured (missing API key)",
                   retry_safe=True,
               )

    mode = body.get("mode", "all")
    options_per_beat = int(body.get("options_per_beat", 3))
    requested = body.get("beats")
    # Per-beat Animate button sends beat_id (singular) without a mode or
    # beats list — auto-scope to just that beat so a single-beat click does
    # not trigger a batch-all run that hits the budget gate (S5.5f fix).
    if not requested and body.get("beat_id"):
        requested = [body["beat_id"]]
        if mode == "all":
            mode = "test"
    beats = h._select_beats_for_mode(mode, requested, scope.video_role)

    # Budget pre-check
    spend = h.app.state.read_spend()
    estimated = len(beats) * options_per_beat * COST_PER_CLIP_KLING
    if spend["budget_remaining"] < estimated and spend["overrides"] == 0:
        return h._send_error_v59(
                   402,
                   error_code="BUDGET_EXCEEDED",
                   error_message="budget exceeded",
                   retry_safe=False,
                   extra={"budget_blocked": True, "estimated_cost": estimated, "budget_remaining": spend["budget_remaining"]},
               )

    submitted = 0
    skipped: list[dict] = []

    # video_role resolved by scope_router; image override lookup is
    # partition-aware via the get_beat_image(_, video_role) helper.
    video_role = scope.video_role
    for beat in beats:
        beat_id = h._beat_id(beat.get("line_number", -1))
        # Check image overrides first (from drag-drop), then storyboard
        image = h.app.get_beat_image(beat_id, video_role) or beat.get("image")
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
        audio_path = _find_beat_audio(h.app.event_dir, beat_id, app=h.app)
        try:
            beat_duration, duration_reason = _infer_animation_duration(audio_path)
        except ValueError as exc:
            print(f"[WARN] {beat_id} skipped: {exc}")
            skipped.append({"beat": beat_id, "reason": str(exc)})
            continue
        print(f"[animate] {beat_id} duration={beat_duration}s reason={duration_reason}")

        # Initialize beat state via partition router (was videos.intro hardcode).
        # Blocker #146 (LD-pending LIPSYNC_INVALIDATE_ON_REGEN_V1): also clear
        # any prior `beat.lipsync` state AND unlink the on-disk
        # {beat_id}_lipsync.mp4 file. Stale lipsync MP4 from a prior regen
        # cycle creates a "partial-lipsync perception bug" (#147) — the
        # beat looks lipsynced even though state.lipsync is null and the
        # video has just been regenerated. Cleanup is best-effort on the
        # disk file (file may not exist; unlink races with concurrent
        # readers are tolerated since the next lipsync will overwrite).
        prior_lipsync_file = h.app.event_dir / "animation_clips" / f"{beat_id}_lipsync.mp4"
        prior_lipsync_existed = False
        try:
            if prior_lipsync_file.is_file():
                prior_lipsync_existed = True
                prior_lipsync_file.unlink()
                print(f"[animate] {beat_id}: unlinked stale lipsync {prior_lipsync_file.name}")
        except OSError as exc:  # noqa: BLE001
            print(f"[animate] {beat_id}: lipsync unlink warning (non-fatal): {exc}")

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
            # Clear lipsync state (Blocker #146) — paired with the disk
            # unlink above. Setting to None rather than deleting the key so
            # downstream code can still distinguish "explicitly cleared" from
            # "never existed".
            if "lipsync" in pbeats[_beat_id]:
                pbeats[_beat_id]["lipsync"] = None
        h.app.state.mutate_video_state(scope.video_role, init_beat_partition)

        # Best-effort Directus audit log of the invalidation. Fire-and-forget.
        if prior_lipsync_existed:
            try:
                from lib.directus import try_post_or_queue as _tpq
                _tpq("prod_activity_log", {
                    "action": "lipsync_invalidated_on_regen",
                    "performed_by": "handle_animate",
                    "details": {
                        "event_id": h.app.event_id,
                        "beat_id": beat_id,
                        "video_role": scope.video_role,
                        "removed_file": str(prior_lipsync_file),
                    },
                })
            except Exception as exc:  # noqa: BLE001
                print(f"[animate] {beat_id}: lipsync_invalidated_on_regen audit failed (non-fatal): {exc}")

        # Submit options_per_beat jobs, staggered
        for opt_idx in range(options_per_beat):
            try:
                task_id = h.app.client.submit_animation(
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
            h.app.state.mutate_video_state(scope.video_role, add_option_partition)
            submitted += 1

            # Stagger within a beat too — simple 2s gap every 6 jobs
            if submitted % 6 == 0:
                time.sleep(POLL_BATCH_GAP_SEC)

    print(f"[animate] done: submitted={submitted} skipped={len(skipped)} "
          f"role={scope.video_role} details={skipped[:5]}")
    h._send_json(200, {
        "submitted": submitted,
        "beats_queued": len(beats) - len([s for s in skipped if "opt" not in s]),
        "skipped": skipped,
        "status": "polling",
    })


def handle_status(h)-> None:

    # Resolve video_role from query string (GET requests pass scope via QS).
    # When only beat_id is provided (per-beat poll from the Animate button),
    # search across all partitions for that specific beat — the client does
    # not inject scope_video_role into apiGet calls (only pathappPatch does).
    _qs = urllib.parse.parse_qs(urllib.parse.urlparse(h.path).query)
    beat_id_filter = (_qs.get("beat_id") or [None])[0]
    explicit_role = (_qs.get("scope_video_role") or _qs.get("scope_target_video") or [None])[0]
    state = h.app.state.read_state()
    spend = h.app.state.read_spend()
    beats_out: dict = {}
    total = 0
    completed = 0
    polling = 0
    failed = 0
    # Build the beat source: explicit role > beat_id cross-partition search > intro fallback.
    if explicit_role:
        beats_src = ((state.get("videos") or {}).get(explicit_role) or {}).get("beats", {})
    elif beat_id_filter:
        # Find the partition that has this beat with phase_1 data (polling options).
        beats_src = {}
        for _role, _partition in (state.get("videos") or {}).items():
            _b = (_partition or {}).get("beats", {}).get(beat_id_filter)
            if _b and (_b.get("phase_1") or {}).get("options"):
                beats_src = {beat_id_filter: _b}
                break
        if not beats_src:
            # Fallback: just return the beat from whichever partition has it
            for _role, _partition in (state.get("videos") or {}).items():
                _b = (_partition or {}).get("beats", {}).get(beat_id_filter)
                if _b:
                    beats_src = {beat_id_filter: _b}
                    break
    else:
        beats_src = ((state.get("videos") or {}).get("intro") or {}).get("beats", {})
    for bid, beat in beats_src.items():
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

    h._send_json(200, {
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


def handle_redo(h, body: dict)-> None:

    # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return

    beat_id = body.get("beat_id") or body.get("beat")
    options_per_beat = int(body.get("options_per_beat", 3))
    if not beat_id:
        return h._send_error_v59(
                   400,
                   error_code="MISSING_BEAT",
                   error_message="missing 'beat'",
                   retry_safe=False,
               )

    video_role = (body or {}).get("scope_video_role") or (body or {}).get("scope_target_video") or "intro"

    # Acquire lock -> clear state -> list old files -> release -> delete -> resubmit
    # Blocker #146 (LIPSYNC_INVALIDATE_ON_REGEN_V1): also clear b["lipsync"]
    # and stage its file for unlink, so handle_redo + handle_animate both
    # share the same invalidation semantics (idempotent if both fire).
    old_files: list[str] = []
    prior_lipsync_existed = False
    def clear(state, _role=video_role):
        nonlocal prior_lipsync_existed
        b = ((state.get("videos") or {}).get(_role) or {}).get("beats", {}).get(beat_id)
        if not b:
            return
        for opt in (b.get("phase_1") or {}).get("options", []):
            if opt.get("file"):
                old_files.append(opt["file"])
        b["phase_1"] = {"status": "polling", "options": [], "selected_option": None}
        if b.get("lipsync"):
            prior_lipsync_existed = True
            b["lipsync"] = None
    h.app.state.mutate_state(clear)

    for fname in old_files:
        p = h.app.state.clips_dir / fname
        if p.is_file():
            try:
                p.unlink()
            except OSError:
                pass

    # Blocker #146: unlink stale {beat_id}_lipsync.mp4 (paired with the
    # state-clear above).
    prior_lipsync_file = h.app.event_dir / "animation_clips" / f"{beat_id}_lipsync.mp4"
    try:
        if prior_lipsync_file.is_file():
            prior_lipsync_existed = True
            prior_lipsync_file.unlink()
            print(f"[redo] {beat_id}: unlinked stale lipsync {prior_lipsync_file.name}")
    except OSError as exc:
        print(f"[redo] {beat_id}: lipsync unlink warning (non-fatal): {exc}")

    if prior_lipsync_existed:
        try:
            from lib.directus import try_post_or_queue as _tpq
            _tpq("prod_activity_log", {
                "action": "lipsync_invalidated_on_regen",
                "performed_by": "handle_redo",
                "details": {
                    "event_id": h.app.event_id,
                    "beat_id": beat_id,
                    "video_role": video_role,
                    "removed_file": str(prior_lipsync_file),
                },
            })
        except Exception as exc:  # noqa: BLE001
            print(f"[redo] {beat_id}: lipsync_invalidated_on_regen audit failed (non-fatal): {exc}")

    # Resubmit via the existing /api/animate path, but scoped to this beat.
    # Forward scope_video_role/scope_target_video so the resubmit hits the
    # same partition as the cleared beat (was hardcoded "intro" pre-fix).
    forwarded = {
        "mode": "test",
        "beats": [beat_id],
        "options_per_beat": options_per_beat,
    }
    if (body or {}).get("scope_video_role"):
        forwarded["scope_video_role"] = body["scope_video_role"]
    if (body or {}).get("scope_target_video"):
        forwarded["scope_target_video"] = body["scope_target_video"]
    if (body or {}).get("scope_event_id"):
        forwarded["scope_event_id"] = body["scope_event_id"]
    return h._handle_animate(forwarded)


def handle_watercolor_animate(h, body: dict)-> None:

    """POST /api/watercolor/animate {watercolor_key, manual_path, motion_description, scope_event_id}

    Per LD-470 WATERCOLOR_ANIMATE_PROCEDURAL_V1. SUPERSEDES the S4 magic-
    compositor-based implementation. Claude API generates an ffmpeg
    filter_complex spec given watercolor + path geometry + motion intent.
    Server validates against safe-filter allowlist BEFORE executing
    ffmpeg.
    """
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return
    # Accept both `watercolor_key` (S5 spec) and `source_key` (S4 alias).
    watercolor_key = ((body or {}).get("watercolor_key")
                      or (body or {}).get("source_key"))
    manual_path = (body or {}).get("manual_path") or []
    motion_desc = ((body or {}).get("motion_description") or "").strip()
    if not watercolor_key:
        return h._send_error_v59(
                   400,
                   error_code="WATERCOLOR_KEY_REQUIRED",
                   error_message="watercolor_key required",
                   retry_safe=False,
               )
    if not motion_desc:
        return h._send_error_v59(
                   400,
                   error_code="MOTION_DESCRIPTION_REQUIRED_NON_EMPTY",
                   error_message="motion_description required (non-empty)",
                   retry_safe=False,
               )
    if len(motion_desc) > 500:
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=f"motion_description too long ({len(motion_desc)} > 500)",
                   retry_safe=False,
               )
    # Reject obvious shell metacharacters in the description.
    for bad in ("`", "$(", "${", "\\", "\n\n\n"):
        if bad in motion_desc:
            return h._send_error_v59(
                       400,
                       error_code="GENERIC_ERROR",
                       error_message=f"forbidden substring in motion_description: {bad!r}",
                       retry_safe=False,
                   )

    ok, clean_path, err = h._validate_manual_path(manual_path)
    if not ok:
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=err,
                   retry_safe=False,
               )

    wc_dir = _data_root(h) / "assets" / "watercolor_library"
    matches = list(wc_dir.glob(f"{watercolor_key}.*"))
    if not matches:
        return h._send_error_v59(
                   404,
                   error_code="GENERIC_ERROR",
                   error_message=f"no watercolor with key={watercolor_key!r}",
                   retry_safe=False,
                   extra={"looked_in": str(wc_dir)},
               )
    source_path = next((m for m in matches if m.suffix.lower() == ".png"), matches[0])
    try:
        wc_root = wc_dir.resolve()
        source_path = source_path.resolve()
        source_path.relative_to(wc_root)
    except ValueError:
        return h._send_error_v59(
                   500,
                   error_code="WATERCOLOR_SOURCE_PATH_OUTSIDE_LIBRARY",
                   error_message="watercolor source path outside library dir",
                   retry_safe=True,
               )
    safe_ffmpeg_still = os.path.realpath(str(source_path))

    # Probe dimensions.
    try:
        from PIL import Image as _PILImage
        with _PILImage.open(safe_ffmpeg_still) as im:
            src_w, src_h = im.size
    except Exception:
        src_w, src_h = 1024, 1024  # safe default

    # LD-460 pin
    _pin = {
        "pinned_generation": h.app.event_generation,
        "pinned_event_dir": h.app.event_dir,
        "pinned_video_role": (body or {}).get("scope_video_role", "intro"),
        "_handler": "_handle_watercolor_animate",
    }
    if not h._check_event_pin(_pin, "watercolor_animate_pre_work"):
        return h._send_error_v59(
                   423,
                   error_code="EVENT_CHANGED_PRE_WORK",
                   error_message="event_changed_pre_work",
                   retry_safe=False,
                   extra={"code": "ASYNC_JOB_GENERATION_PIN_V1"},
               )

    # Resolve Anthropic key.
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
        return h._send_error_v59(
                   502,
                   error_code="GENERIC_ERROR",
                   error_message=f"Anthropic API HTTP {exc.code}",
                   retry_safe=True,
                   extra={"detail": err_body[:500]},
               )
    except urllib.error.URLError as exc:
        return h._send_error_v59(
                   502,
                   error_code="GENERIC_ERROR",
                   error_message=f"Anthropic URL error: {exc}",
                   retry_safe=True,
               )
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
        return h._send_error_v59(
                   502,
                   error_code="CLAUDE_RESPONSE_HAD_NO_JSON",
                   error_message="Claude response had no JSON object",
                   retry_safe=True,
                   extra={"raw": text[:500]},
               )
    try:
        spec = json.loads(m.group(0))
    except json.JSONDecodeError as exc:
        return h._send_error_v59(
                   502,
                   error_code="GENERIC_ERROR",
                   error_message=f"Claude JSON parse failed: {exc}",
                   retry_safe=True,
                   extra={"raw": text[:500]},
               )

    filter_complex = spec.get("filter_complex") or ""
    duration_s = float(spec.get("duration_s") or 3.0)
    explanation = (spec.get("explanation") or "")[:300]

    if not (0.5 <= duration_s <= 10.0):
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=f"duration_s={duration_s} outside [0.5, 10]",
                   retry_safe=False,
               )

    # SAFETY GATE.
    ok_filter, gate_err = h._validate_ffmpeg_filter_chain(filter_complex)
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
        return h._send_error_v59(
                   400,
                   error_code="UNSAFE_FILTER_CHAIN",
                   error_message="unsafe_filter_chain",
                   retry_safe=False,
                   extra={"details": gate_err, "filter_complex_preview": filter_complex[:200]},
               )

    # Execute ffmpeg.
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = wc_dir / f"{watercolor_key}_animated_{ts}.mp4"
    ffmpeg_out = str(out_path.resolve())
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", safe_ffmpeg_still,
        "-filter_complex", filter_complex,
        "-t", f"{duration_s:.3f}",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        ffmpeg_out,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=60)
    except subprocess.CalledProcessError as exc:
        return h._send_error_v59(
                   500,
                   error_code="FFMPEG_FAILED",
                   error_message="ffmpeg failed",
                   retry_safe=True,
                   extra={"filter_complex": filter_complex, "stderr": exc.stderr.decode("utf-8", errors="replace")[-1000:]},
               )
    except subprocess.TimeoutExpired:
        return h._send_error_v59(
                   504,
                   error_code="FFMPEG_TIMED_OUT",
                   error_message="ffmpeg timed out (>60s)",
                   retry_safe=True,
               )

    if not h._check_event_pin(_pin, "watercolor_animate_terminal"):
        return h._send_error_v59(
                   423,
                   error_code="EVENT_CHANGED_MID_JOB",
                   error_message="event_changed_mid_job",
                   retry_safe=False,
                   extra={"code": "ASYNC_JOB_GENERATION_PIN_V1", "orphaned_output": str(out_path)},
               )

    registered_id: int | None = None
    try:
        from registered_write import register_asset  # type: ignore
        registered_id, _ = register_asset(
            file_path=str(out_path),
            asset_type="magic_clip",
            module_id=_resolve_module_id_for_state(h.app.state),
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

    return h._send_json(200, {
        "ok": True,
        "watercolor_key": watercolor_key,
        "animated_path": str(out_path),
        "asset_id": registered_id,
        "explanation": explanation,
        "duration_s": duration_s,
        "filter_complex": filter_complex,
        "claude_ms": elapsed_ms,
    })


