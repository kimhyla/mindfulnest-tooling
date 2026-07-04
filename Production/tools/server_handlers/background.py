"""Background / magic / animate handlers — V59 Phase 4 Pass 2.

Handlers extracted from production_server.py.
Each function takes the live `ProductionHandler` instance as `h`.
"""
from __future__ import annotations

import argparse
import base64
import collections as _pathapp_collections
import concurrent.futures as _cf
import copy
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

_ARLO_O3_JOBS: dict[str, dict] = {}
_STILL_RENDER_BUSY: set[str] = set()
_NATIVE_LIPSYNC_JOBS: dict[str, dict] = {}
_O3_JOB_METADATA_LAST_STAMP: dict[str, float] = {}
_O3_JOB_METADATA_STAMP_INTERVAL_S = 30.0
_O3_LOG_TAIL_BYTES = 16384

# V59 Phase 4 path-depth correction: extracted modules are one level
# deeper than production_server.py. _PSERVER_TOOLS_DIR is for CODE-tree
# lookups (sibling Python modules, sys.path inserts). NOT used for data
# paths — those come from _data_root(h) per LD-505 Phase C (2026-05-19).
_PSERVER_TOOLS_DIR = Path(__file__).resolve().parent.parent  # Production/tools/


class _BgSidecarAbort(Exception):
    """Abort sidecar mutator — map to HTTP response in handler except block."""

    __slots__ = (
        "status", "error_code", "error_message", "retry_safe", "extra", "json_payload",
    )

    def __init__(
        self,
        *,
        status: int,
        error_code: str = "",
        error_message: str = "",
        retry_safe: bool = False,
        extra: dict | None = None,
        json_payload: dict | None = None,
    ):
        self.status = status
        self.error_code = error_code
        self.error_message = error_message
        self.retry_safe = retry_safe
        self.extra = extra
        self.json_payload = json_payload


def _bg_abort_from_sidecar(h, exc: _BgSidecarAbort):
    if exc.json_payload is not None:
        return h._send_json(exc.status, exc.json_payload)
    return h._send_error_v59(
        exc.status,
        error_code=exc.error_code,
        error_message=exc.error_message,
        retry_safe=exc.retry_safe,
        extra=exc.extra,
    )


def _magic_canvas_dims(width: int, height: int) -> tuple[int, int]:
    """Even W×H matching MagicCompositor libx264 crop (magic_compositor.py ~235)."""
    w, h = int(width), int(height)
    return w - (w % 2), h - (h % 2)


def _data_root(h) -> Path:
    """Runtime ``Production/`` root, anchored on the running server's event_dir.

    Replaces the LD-505-broken `_PSERVER_PRODUCTION_DIR = Path(__file__)...`
    which resolved to the (empty) tooling tree. Audit C1-1 / C1-2 / C1-7.

    Always ``resolve()`` so O3 subprocess env (``MN_PROD_ROOT`` + ``cwd``) never
    double-applies a relative ``Production/`` segment (Production/Production/ sidecar).
    """
    from lib.paths import runtime_production_root

    return runtime_production_root(h.app.event_dir)


# Project-internal modules imported the same way production_server.py does.
# Handler bodies may reference any of these by bare name.
from lib.atomic_json_write import atomic_json_write
from lib.v3_partition import _iter_v3_beats
from lib.paths import DROPBOX_ROOT
from lib.event_library import event_watercolors_dir

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
    _BG_PHASE_MAP,
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
    # Canonical location is Production/tools/scene_registry.yaml per
    # VISIBLE_MAGIC_TECH_SPEC_v1.md + magic_compositor.py:520 — NOT
    # Production/scene_registry.yaml. _data_root(h) is event_dir.parent =
    # Production/, so the subdir 'tools' is required.
    reg_path = _data_root(h) / "tools" / "scene_registry.yaml"
    if not reg_path.exists():
        return h._send_error_v59(
                   404,
                   error_code="SCENE_REGISTRY_YAML_NOT_FOUND",
                   error_message="scene_registry.yaml not found",
                   retry_safe=False,
                   extra={"ok": False, "expected_path": str(reg_path)},
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
        "pinned_video_role": (body or {}).get("scope_video_role") or (body or {}).get("scope_target_video"),
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
            # Canonical location is Production/tools/scene_registry.yaml
            # (see VISIBLE_MAGIC_TECH_SPEC_v1.md + magic_compositor.py:520).
            reg_path = _data_root(h) / "tools" / "scene_registry.yaml"
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
            import magic_render_contract as mrc  # type: ignore
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
                **mrc.production_magic_compositor_kwargs(),
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


def _load_scene_registry(h) -> dict:
    reg_path = _data_root(h) / "tools" / "scene_registry.yaml"
    if not reg_path.exists():
        return {}
    import yaml as _yaml
    return _yaml.safe_load(reg_path.read_text()) or {}


def _resolve_magic_style(h, beat_id: str, body: dict, manual_path: list, sidecar: dict) -> str:
    bg = _bg_module()
    video_role = (body or {}).get("scope_video_role") or (body or {}).get("scope_target_video") or "intro"
    production_state = h.app.state.read_state()
    registry = _load_scene_registry(h)
    return bg.resolve_magic_style_for_render(
        beat_id,
        sidecar=sidecar,
        production_state=production_state,
        video_role=video_role,
        manual_path=manual_path,
        scene_registry=registry,
        event_id=h.app.event_id,
    )


def _persist_magic_scene_registry(
    h,
    *,
    beat_id: str,
    manual_path: list,
    style: str,
    video_role: str = "resolution",
) -> None:
    """Best-effort YAML persist so scene_registry tracks last approved path + style."""
    try:
        reg_path = _data_root(h) / "tools" / "scene_registry.yaml"
        if not reg_path.exists():
            return
        import yaml as _yaml
        from magic_render_contract import resolve_magic_scene_registry_keys

        registry = _yaml.safe_load(reg_path.read_text()) or {}
        keys = resolve_magic_scene_registry_keys(
            beat_id,
            event_id=h.app.event_id,
            video_role=video_role,
        )
        scene_key = keys[0] if keys else f"m1_e1_res_{beat_id}"
        scene = registry.setdefault(scene_key, {})
        scene["manual_path"] = manual_path
        scene["style"] = style
        reg_path.write_text(_yaml.safe_dump(registry, sort_keys=False))
    except Exception as exc:  # noqa: BLE001
        print(f"[magic] WARN scene_registry persist failed beat={beat_id}: {exc}", flush=True)


def _persist_magic_fields_to_bg_sidecar(
    h,
    *,
    request_beat_id: str,
    video_role: str,
    fields: dict,
) -> None:
    """Mirror magic_* writeback onto Beat Gen sidecar (best-effort)."""
    try:
        bg = _bg_module()
        arc, evt, phase = _resolve_bg_segment_for_scope(h.app.event_id, video_role)

        def _persist(sidecar: dict) -> None:
            bg.persist_magic_fields_on_bg_sidecar(
                sidecar,
                arc_number=arc,
                event_id=str(evt),
                phase=phase,
                request_beat_id=request_beat_id,
                fields=fields,
            )

        bg.mutate_sidecar_locked(_persist)
    except Exception as exc:  # noqa: BLE001
        print(f"[BG] magic sidecar persist failed beat={request_beat_id}: {exc}", flush=True)


def _sync_bg_partition_display_order_for_scope(h, video_role: str) -> None:
    """BG_PARTITION_DISPLAY_ORDER_SYNC_V1 — partition display_order from BG segment rows."""
    try:
        arc, evt, phase = _resolve_bg_segment_for_scope(h.app.event_id, video_role)
        bg = _bg_module()
        sidecar = bg.read_sidecar()
        synced = bg.sync_storyboard_partition_display_order_from_bg_segment(
            h.app.state,
            video_role,
            sidecar,
            arc,
            str(evt),
            phase,
        )
        if synced:
            print(
                f"[BG] synced videos.{video_role}.display_order from segment "
                f"arc={arc} event={evt} phase={phase} beats={len(synced)}",
                flush=True,
            )
    except Exception as exc:  # noqa: BLE001
        print(f"[BG] WARN partition display_order sync skipped: {exc}", flush=True)


def _video_role_for_bg_phase(phase: str) -> str:
    for role, ph in _BG_PHASE_MAP.items():
        if ph == phase:
            return role
    return "resolution"


def _magic_sidecar_field_matches(
    h,
    *,
    request_beat_id: str,
    video_role: str,
    field: str,
    expected: str,
) -> bool:
    """Read-back on Beat Gen sidecar when partition verify fails."""
    try:
        bg = _bg_module()
        arc, evt, phase = _resolve_bg_segment_for_scope(h.app.event_id, video_role)
        sidecar = bg.read_sidecar()
        _, beat_obj = bg.find_beat(sidecar, request_beat_id)
        if not beat_obj:
            seg = bg.get_seg_entry(sidecar, arc, str(evt), phase)
            for row in seg.get("beats") or []:
                if row.get("beat_id") == request_beat_id:
                    beat_obj = row
                    break
        return bool(beat_obj) and beat_obj.get(field) == expected
    except Exception:
        return False


def _magic_partition_writeback_ensure_display_order(partition: dict, sb_beat_id: str) -> None:
    """DISPLAY_ORDER_STRICT_V1: display_order=[] prunes every beats[bid] post-mutate.

    Beat Gen resolution partitions often have display_order=[] until extract-beats
    seeds storyboard rows; magic writeback must register sb_beat_id before prune runs.
    """
    pdo = partition.get("display_order")
    if isinstance(pdo, list) and sb_beat_id not in pdo:
        pdo.append(sb_beat_id)


_MAGIC_STILL_CLEAR_FIELDS = (
    "magic_still_path",
    "magic_manual_path",
    "magic_path_authored_against",
)

_MAGIC_VIDEO_CLEAR_FIELDS = (
    "magic_video_path",
    "magic_manual_path",
    "magic_path_authored_against",
)


def write_magic_delivery(
    h,
    *,
    body: dict,
    request_beat_id: str,
    partition_fields: dict,
    verify_field: str,
    expected_value: str,
    log_tag: str,
    magic_style: str | None = None,
    clean_path: list | None = None,
    persist_scene_registry: bool = False,
    invalidate_scratch: bool = False,
    verify_absent: bool = False,
) -> tuple[str | None, str, dict] | None:
    """MAGIC_WRITE_AUTHORITY_V1 — single partition+sidecar writeback for magic delivery.

    Returns (partition_written, sb_beat_id, sidecar_fields) on success.
    On failure sends error response via h._send_error_v59 and returns None.
    """
    _video_role_body = (body or {}).get("scope_video_role") or (body or {}).get("scope_target_video") or "intro"
    bg = _bg_module()
    _production_state = h.app.state.read_state()
    _sidecar_for_map = bg.read_sidecar()
    sb_beat_id = bg.storyboard_beat_id_for_bg_beat(
        request_beat_id,
        sidecar=_sidecar_for_map,
        production_state=_production_state,
        video_role=_video_role_body,
    ) or request_beat_id
    _sync_bg_partition_display_order_for_scope(h, _video_role_body)
    _production_state = h.app.state.read_state()
    sb_beat_id = bg.storyboard_beat_id_for_bg_beat(
        request_beat_id,
        sidecar=_sidecar_for_map,
        production_state=_production_state,
        video_role=_video_role_body,
    ) or request_beat_id
    scope = None
    try:
        scope = scope_router.resolve(body, h.app.event_dir.name)

        def _apply(partition: dict) -> None:
            _magic_partition_writeback_ensure_display_order(partition, sb_beat_id)
            beat = partition.setdefault("beats", {}).setdefault(sb_beat_id, {})
            for key, val in partition_fields.items():
                if val is None:
                    beat.pop(key, None)
                else:
                    beat[key] = val

        scope_router.mutate_partition(h.app.state, scope, _apply)
    except Exception as exc:  # noqa: BLE001
        print(f"[{log_tag}] WARN state writeback failed: {exc}", flush=True)

    if scope is None:
        h._send_error_v59(
            500,
            error_code="STATE_WRITEBACK_VERIFY_FAILED",
            error_message="scope_router.resolve failed before mutate_partition; cannot verify writeback",
            retry_safe=True,
            extra={"hint": f"Check server log [{log_tag}] WARN state writeback failed message."},
        )
        return None

    partition_written: str | None = None
    _video_role_written = getattr(scope, "video_role", None)
    sidecar_fields = dict(partition_fields)
    try:
        _state_after = h.app.state.read_state()
        if _video_role_written:
            _beat_after = (
                (((_state_after.get("videos") or {}).get(_video_role_written) or {})
                 .get("beats") or {}).get(sb_beat_id) or {}
            )
            if verify_absent:
                verified = not _beat_after.get(verify_field)
            else:
                verified = _beat_after.get(verify_field) == expected_value
            if verified:
                partition_written = _video_role_written
                print(
                    f"[{log_tag}] state writeback verified: videos.{_video_role_written}"
                    f".beats.{sb_beat_id}.{verify_field}={expected_value!r}",
                    flush=True,
                )
            else:
                print(
                    f"[{log_tag}] STATE_WRITEBACK_VERIFY_FAILED: expected "
                    f"videos.{_video_role_written}.beats.{sb_beat_id}.{verify_field}="
                    f"{expected_value!r}, got {_beat_after.get(verify_field)!r}",
                    flush=True,
                )
                h._send_error_v59(
                    500,
                    error_code="STATE_WRITEBACK_VERIFY_FAILED",
                    error_message=f"{verify_field} was not persisted at the expected partition",
                    retry_safe=True,
                    extra={
                        "expected_partition": _video_role_written,
                        "expected_beat_id": sb_beat_id,
                        f"expected_{verify_field}": expected_value,
                        f"got_{verify_field}": _beat_after.get(verify_field),
                    },
                )
                return None
    except Exception as exc:  # noqa: BLE001
        print(f"[{log_tag}] STATE_WRITEBACK_VERIFY_CRASHED: {type(exc).__name__}: {exc}", flush=True)
        h._send_error_v59(
            500,
            error_code="STATE_WRITEBACK_VERIFY_FAILED",
            error_message=f"state writeback verify crashed: {type(exc).__name__}: {exc}",
            retry_safe=True,
        )
        return None

    if _video_role_written:
        _persist_magic_fields_to_bg_sidecar(
            h,
            request_beat_id=request_beat_id,
            video_role=_video_role_written,
            fields=sidecar_fields,
        )
        if persist_scene_registry and clean_path is not None and magic_style:
            _persist_magic_scene_registry(
                h,
                beat_id=request_beat_id,
                manual_path=clean_path,
                style=magic_style,
                video_role=_video_role_written,
            )
        if invalidate_scratch:
            try:
                bg.invalidate_magic_still_tts_scratch(str(request_beat_id), h.app.event_dir)
            except Exception as exc:  # noqa: BLE001
                print(f"[{log_tag}] WARN scratch invalidate failed: {exc}", flush=True)

    return partition_written, sb_beat_id, sidecar_fields


def _bg_beat_id_for_storyboard_beat(h, sb_beat_id: str, video_role: str) -> str | None:
    """Reverse map storyboard beat_0N → Beat Gen beat_id via display_order index."""
    try:
        bg = _bg_module()
        arc, evt, phase = _resolve_bg_segment_for_scope(h.app.event_id, video_role)
        state = h.app.state.read_state()
        partition = (state.get("videos") or {}).get(video_role) or {}
        display_order = partition.get("display_order")
        if not isinstance(display_order, list) or sb_beat_id not in display_order:
            return None
        idx = display_order.index(sb_beat_id)
        seg = bg.get_seg_entry(bg.read_sidecar(), arc, str(evt), phase)
        beats = seg.get("beats") or []
        if idx < len(beats):
            return str(beats[idx].get("beat_id") or "") or None
    except Exception:
        return None
    return None


def mirror_magic_clear_to_sidecar_after_image_assign(
    h,
    *,
    sb_beat_id: str,
    video_role: str,
) -> None:
    """Assign-image clears partition magic refs — mirror nulls onto BG sidecar."""
    bg_beat_id = _bg_beat_id_for_storyboard_beat(h, sb_beat_id, video_role)
    if not bg_beat_id:
        return
    _persist_magic_fields_to_bg_sidecar(
        h,
        request_beat_id=bg_beat_id,
        video_role=video_role,
        fields={"magic_still_path": None, "magic_video_path": None},
    )


def handle_clear_magic_still(h, body: dict) -> None:
    """POST /api/storyboard/clear_magic_still — drop magic-on-still from partition + sidecar."""
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return
    beat_id = (body or {}).get("beat_id")
    if not beat_id:
        return h._send_error_v59(
            400,
            error_code="MISSING_BEAT_ID",
            error_message="beat_id required",
            retry_safe=False,
        )
    wb = write_magic_delivery(
        h,
        body=body,
        request_beat_id=str(beat_id),
        partition_fields={key: None for key in _MAGIC_STILL_CLEAR_FIELDS},
        verify_field="magic_still_path",
        expected_value="",
        log_tag="clear_magic_still",
        verify_absent=True,
        invalidate_scratch=True,
    )
    if wb is None:
        return
    partition_written, sb_beat_id, _ = wb
    return h._send_json(200, {
        "ok": True,
        "beat_id": beat_id,
        "storyboard_beat_id": sb_beat_id,
        "partition_written": partition_written,
        "cleared_fields": list(_MAGIC_STILL_CLEAR_FIELDS),
    })


def handle_magic_still(h, body: dict)-> None:

    """POST /api/storyboard/magic_still {beat_id, manual_path, source_image_path, scope_event_id, scope_video_role}

    Per LD-468 MAGIC_TRAIL_ON_STILL_V1. Invokes magic_compositor with the
    still as background; renders animated mp4 of magic forming on the
    still.
    """
    # Bug-A3 (spec §2 Topic-2, 2026-05-20): scope_video_role REQUIRED. The
    # previous default-to-'intro' silently wrote magic_still_path to the wrong
    # partition (Kim hit this on resolution beat_01 — magic_still_path landed
    # on videos.intro.beats.beat_01 instead). _assert_event_scope's default
    # allow_missing_video_role=False already returns 400 VIDEO_ROLE_REQUIRED.
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return
    beat_id = (body or {}).get("beat_id")
    manual_path = (body or {}).get("manual_path") or []
    source_image_path_raw = (body or {}).get("source_image_path") or ""
    path_authored_against = (body or {}).get("path_authored_against") or None
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
    # Bug-A3 (spec §2 Topic-2, 2026-05-20): NO 'intro' default — _assert_event_scope
    # at line 548 already enforced presence of scope_video_role; if we get here
    # without it, something has gone deeply wrong upstream and we surface it
    # (rather than silently writing to wrong partition).
    _pin = {
        "pinned_generation": h.app.event_generation,
        "pinned_event_dir": h.app.event_dir,
        "pinned_video_role": (body or {}).get("scope_video_role") or (body or {}).get("scope_target_video"),
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

    # Canonical magic_still clip is silent — TTS is mixed at stitch export
    # (materialize_magic_still_with_tts_export). Default 4.0s for tessa_ori floor
    # trails; nest orbital scenes pin 6.083s via scene_registry.yaml.
    registry = _load_scene_registry(h)
    _video_role_for_dur = (body or {}).get("scope_video_role") or (body or {}).get("scope_target_video") or "resolution"
    magic_still_duration = _bg_module().resolve_magic_still_render_duration(
        beat_id,
        scene_registry=registry,
        fallback=4.0,
        event_id=h.app.event_id,
        video_role=_video_role_for_dur,
    )

    try:
        tools_dir = str(_PSERVER_TOOLS_DIR)
        if tools_dir not in sys.path:
            sys.path.insert(0, tools_dir)
        from magic_compositor import MagicCompositor  # type: ignore
        import magic_render_contract as mrc  # type: ignore
        # MAGIC_RENDER_CONTRACT_V2_STILL — see Production/docs/HOW_TO_MAKE_VISIBLE_MAGIC.md
        _sidecar_style = _bg_module().read_sidecar()
        magic_style = _resolve_magic_style(h, beat_id, body, clean_path, _sidecar_style)
        mc = MagicCompositor(
            background_path=safe_sip,
            path_pts=clean_path,
            style=magic_style,
            duration=magic_still_duration,
            fps=24,
            output_dir=str(out_dir),
            label=f"magic_still_{beat_id}_{ts}",
            beat_id=beat_id,
            tags=["magic", "magic_still", magic_style],
            **mrc.production_magic_compositor_kwargs(
                path_authored_against=path_authored_against,
            ),
        )
        rendered = mc.render_ld469_on_background(output_path=str(out_path))
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
                f"LD-469 screen_rgb (same contract as magic_video). "
                f"{len(clean_path)} path points; path_interp=polyline; gain=1.0."
            ),
            role="library",
        )
    except Exception as exc:
        print(f"[magic_still] WARN registered_write failed: {exc}", flush=True)

    magic_filename = Path(rendered).name
    magic_sidecar_fields = {
        "magic_still_path": magic_filename,
        "magic_manual_path": clean_path,
        **({"magic_path_authored_against": path_authored_against} if path_authored_against else {}),
    }
    wb = write_magic_delivery(
        h,
        body=body,
        request_beat_id=beat_id,
        partition_fields=magic_sidecar_fields,
        verify_field="magic_still_path",
        expected_value=magic_filename,
        log_tag="magic_still",
        magic_style=magic_style,
        clean_path=clean_path,
        persist_scene_registry=True,
        invalidate_scratch=True,
    )
    if wb is None:
        return
    partition_written, sb_beat_id, _ = wb

    return h._send_json(200, {
        "ok": True,
        "beat_id": beat_id,
        "composite_path": str(rendered),
        "magic_still_path": magic_filename,
        "partition_written": partition_written,
        "asset_id": registered_id,
        "manual_path_points": len(clean_path),
    })


def handle_magic_video(h, body: dict)-> None:

    """POST /api/storyboard/magic_video {beat_id, manual_path, source_video_path, scope_event_id, scope_video_role}

    Per LD-469 MAGIC_TRAIL_ON_VIDEO_V1. Generates magic-on-black via
    magic_compositor.render_video(black_bg=True), then ffmpeg overlays
    onto the source video via blend=mode=screen (black pixels become
    transparent in screen blend; magic pixels shine through additively).
    """
    # Bug-A3 (spec §2 Topic-2, 2026-05-20): scope_video_role REQUIRED.
    # _assert_event_scope default allow_missing_video_role=False enforces 400 on missing.
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return
    beat_id = (body or {}).get("beat_id")
    manual_path = (body or {}).get("manual_path") or []
    source_video_path_raw = (body or {}).get("source_video_path") or ""
    path_authored_against = (body or {}).get("path_authored_against") or None
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

    # MAGIC_VIDEO_TRIM_CUT_SOURCE_V1 — composite on trimmed/cut O3 clip (not raw delivery).
    try:
        bg_trim = _bg_module()
        sidecar_trim = bg_trim.read_sidecar()
        _, bg_beat_trim = bg_trim.find_beat(sidecar_trim, beat_id)
        if bg_beat_trim is not None:
            resolved_src = bg_trim.resolve_magic_video_source_path(
                bg_beat_trim,
                h.app.event_dir,
                ffmpeg_src,
            )
            resolved_str = str(resolved_src)
            if os.path.realpath(resolved_str) != os.path.realpath(ffmpeg_src):
                print(
                    f"[magic_video] trim/cut source {Path(resolved_str).name} beat={beat_id}",
                    flush=True,
                )
                ffmpeg_src = require_media_under_project(
                    resolved_str, extensions=VIDEO_EXTENSIONS,
                )
    except Exception as exc:
        print(f"[magic_video] trim/cut resolve skipped for {beat_id}: {exc}", flush=True)

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
        comp_w, comp_h = _magic_canvas_dims(width, height)
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

    # LD-828: path must be drawn on the lipsync frame surface, not the still crop.
    if path_authored_against:
        try:
            aw = int(path_authored_against.get("width") or 0)
            ah = int(path_authored_against.get("height") or 0)
        except (TypeError, ValueError):
            aw, ah = 0, 0
        aw, ah = _magic_canvas_dims(aw, ah)
        if aw > 0 and ah > 0 and (aw != comp_w or ah != comp_h):
            return h._send_error_v59(
                       400,
                       error_code="PATH_SURFACE_MISMATCH",
                       error_message=(
                           f"path was drawn on {aw}x{ah} but source video is {comp_w}x{comp_h}. "
                           "Re-open Magic on video and draw on the lipsync frame (not the still crop)."
                       ),
                       retry_safe=False,
                       extra={"authored_dims": [aw, ah], "video_dims": [comp_w, comp_h]},
                   )

    # LD-460 pin
    # Bug-A3 (spec §2 Topic-2, 2026-05-20): NO 'intro' default — handle_magic_video
    # also requires scope_video_role explicit at the route boundary (same bug
    # class as magic_still).
    _pin = {
        "pinned_generation": h.app.event_generation,
        "pinned_event_dir": h.app.event_dir,
        "pinned_video_role": (body or {}).get("scope_video_role") or (body or {}).get("scope_target_video"),
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
    # NOTE: magic_only_path is no longer written to disk — compositing is done
    # entirely in Python/numpy to avoid ffmpeg yuv420p blend color corruption
    # (ffmpeg blend=screen on YUV chroma channels Cb/Cr produces magenta artifacts
    # because neutral black has Cb=128,Cr=128 in YUV, not 0,0 as screen blend assumes).
    out_path = out_dir / f"magic_video_{beat_id}_{ts}.mp4"

    # Step 1: build MagicCompositor (no render to disk).
    # We still need a black PNG ref so MagicCompositor can read image dimensions.
    try:
        from PIL import Image as _PILImage
        import numpy as _np_mv  # avoid clobbering outer np imports
        _req_id = _stdlib_uuid.uuid4().hex[:8]
        black_ref = out_dir / f"_tmp_black_ref_{beat_id}_{ts}_{_req_id}.png"
        _PILImage.new("RGB", (comp_w, comp_h), (0, 0, 0)).save(black_ref)
    except Exception as exc:
        return h._send_error_v59(
                   500,
                   error_code="GENERIC_ERROR",
                   error_message=f"could not create black ref: {exc}",
                   retry_safe=True,
               )

    mc = None
    try:
        tools_dir = str(_PSERVER_TOOLS_DIR)
        if tools_dir not in sys.path:
            sys.path.insert(0, tools_dir)
        from magic_compositor import MagicCompositor, composite_screen_rgb  # type: ignore
        import magic_render_contract as mrc  # type: ignore
        # MAGIC_RENDER_CONTRACT_V2_VIDEO — see Production/docs/HOW_TO_MAKE_VISIBLE_MAGIC.md
        _sidecar_style = _bg_module().read_sidecar()
        magic_style = _resolve_magic_style(h, beat_id, body, clean_path, _sidecar_style)
        mc = MagicCompositor(
            background_path=str(black_ref),
            path_pts=clean_path,
            style=magic_style,
            duration=min(vid_duration, 10.0),
            fps=24,
            output_dir=str(out_dir),
            label=f"magic_only_{beat_id}_{ts}",
            beat_id=beat_id,
            tags=["magic", "magic_video", magic_style],
            **mrc.production_magic_compositor_kwargs(
                path_authored_against=path_authored_against,
            ),
        )
        _composite_screen_rgb = composite_screen_rgb
        # DO NOT call mc.render_video() — we composite directly in Step 2.
    except Exception as exc:
        traceback.print_exc()
        return h._send_error_v59(
                   500,
                   error_code="GENERIC_ERROR",
                   error_message=f"magic_compositor init failed: {type(exc).__name__}: {exc}",
                   retry_safe=True,
               )
    finally:
        try:
            black_ref.unlink(missing_ok=True)
        except Exception:
            pass

    # Lock decode/encode to compositor canvas (may differ from raw ffprobe on odd dims).
    comp_w, comp_h = mc.W, mc.H

    # Step 2: Python-numpy RGB screen composite piped to ffmpeg for h264 encoding.
    #
    # LD-469 semantics (beat 1 approved 2026-06-05): trail at gain=1.0 on black,
    # then screen onto source.  ffmpeg blend=screen on YUV produces magenta; decode
    # to RGB24, composite in numpy, encode back with audio copy.
    #
    # INVARIANTS:
    #   - decode_proc reads safe_ffmpeg_src → raw RGB24 bytes on stdout
    #   - encode_proc reads raw RGB24 on stdin → h264 yuv420p + audio from source
    #   - mc._make_trail(frame_idx) returns float32 (H,W,3) trail in [0,255]
    #   - screen blend: 255 - (255-bg)*(255-trail)/255
    frame_size = comp_w * comp_h * 3  # bytes per RGB24 frame

    mc_n_frames = mc.n_frames  # set by MagicCompositor.__init__ from duration*fps

    # LD-469: magic-on-video renders trail at full brightness (black_bg semantics).
    # Calibrating gain on the black ref attenuates the ambient pool → blocky 1px squares.
    mc._gain = 1.0

    print(
        f"[magic_video] compositing {len(clean_path)} path pts on {comp_w}x{comp_h} "
        f"(authored={path_authored_against}, gain=1.0, blend=screen_rgb)",
        flush=True,
    )

    decode_cmd = [
        "ffmpeg",
        "-i", safe_ffmpeg_src,
        # fps=24 normalises source frame-rate to exactly match encode_cmd's -r 24.
        # Without this, a 25fps source produces floor(duration*25)=172 frames while
        # encode_cmd's -t duration @ 24fps only consumes floor(duration*24)=165 frames,
        # causing encode_proc to close stdin early and raising BrokenPipeError on
        # the 166th encode_proc.stdin.write() call.
        #
        # VFR safety (cursor review finding — HIGH severity): fps=24 alone is not
        # sufficient for variable-framerate sources (Kling / ByteDance LipSync outputs
        # are often VFR). The fps filter with VFR input can over- or under-count frames
        # relative to the -t boundary. Adding -frames:v as a hard frame-count cap
        # guarantees the decode side emits exactly floor(duration*24) frames regardless
        # of source framerate type (CFR or VFR), eliminating residual BrokenPipeError
        # risk on VFR inputs.
        "-vf", f"scale={comp_w}:{comp_h},fps=24,format=rgb24",
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-vcodec", "rawvideo",
        "-an",                              # no audio in decode stream
        "-t", str(min(vid_duration, 10.0)),
        "-frames:v", str(int(min(vid_duration, 10.0) * 24)),  # hard cap: exact frame count
        "pipe:1",
    ]
    encode_cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo", "-vcodec", "rawvideo",
        "-s", f"{comp_w}x{comp_h}", "-r", "24", "-pix_fmt", "rgb24",
        "-i", "pipe:0",                     # composited RGB frames on stdin
        "-i", safe_ffmpeg_src,              # original source for audio
        "-map", "0:v",
        "-map", "1:a?",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        "-t", str(min(vid_duration, 10.0)),
        str(out_path),
    ]
    decode_proc = None
    encode_proc = None
    try:
        decode_proc = subprocess.Popen(
            decode_cmd,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        encode_proc = subprocess.Popen(
            encode_cmd,
            stdin=subprocess.PIPE, stderr=subprocess.PIPE,
        )

        frame_idx = 0
        path_lum_sampled = False
        while True:
            raw = decode_proc.stdout.read(frame_size)
            if len(raw) < frame_size:
                break
            bg_arr = _np_mv.frombuffer(raw, dtype=_np_mv.uint8).reshape(comp_h, comp_w, 3).astype(_np_mv.float32)

            if not path_lum_sampled:
                mc.set_path_luminance_from_array(bg_arr)
                path_lum_sampled = True

            # Map lipsync frame_idx → magic compositor frame (same fps+duration, so 1:1)
            mc_frame_idx = min(frame_idx, mc_n_frames - 1)
            trail = mc._make_trail(mc_frame_idx)

            result = _composite_screen_rgb(bg_arr, trail)
            encode_proc.stdin.write(result.tobytes())
            frame_idx += 1

        # Drain + wait for both processes.
        # IMPORTANT (Python 3.12): Do NOT explicitly close encode_proc.stdin before
        # calling communicate(). communicate() internally calls self.stdin.flush() then
        # self.stdin.close() (subprocess.py:2067). If stdin is already closed, flush()
        # raises ValueError: flush of closed file. Let communicate() own the close.
        decode_proc.stdout.close()
        _, decode_stderr = decode_proc.communicate(timeout=60)
        _, encode_stderr = encode_proc.communicate(timeout=300)

        if decode_proc.returncode not in (0, None):
            print(f"[magic_video] decode stderr: {decode_stderr.decode('utf-8', errors='replace')[-500:]}", flush=True)
            raise subprocess.CalledProcessError(decode_proc.returncode, decode_cmd, stderr=decode_stderr)
        if encode_proc.returncode not in (0, None):
            raise subprocess.CalledProcessError(encode_proc.returncode, encode_cmd, stderr=encode_stderr)

        print(f"[magic_video] composite OK: {frame_idx} frames, out={out_path.name}", flush=True)

    except BrokenPipeError:
        # encode_proc closed its stdin (exited after its -t limit).
        # This normally means the fps=24 normalisation above wasn't in place OR
        # decode produced a few extra frames past the encode window.
        # IMPORTANT: encode_proc may have already written a complete valid MP4.
        # Try to recover by waiting for encode_proc to exit and checking the file.
        traceback.print_exc()
        enc_stderr_broken = b""
        if encode_proc is not None:
            try:
                encode_proc.stdin.close()
            except Exception:
                pass
            try:
                # Do NOT call communicate() here — stdin was just explicitly closed,
                # so communicate()'s internal flush() would raise ValueError (Python 3.12).
                # Use wait() + stderr.read() instead.
                #
                # Deadlock fix (cursor review finding — MEDIUM severity): if wait()
                # raises TimeoutExpired and the broad except swallows it, stderr.read()
                # then blocks forever (process still running, pipe write-end still open).
                # Fix: catch TimeoutExpired specifically, kill the process, then read.
                try:
                    encode_proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    encode_proc.kill()
                    encode_proc.wait()  # reap after kill (no timeout needed — SIGKILL is unconditional)
                enc_stderr_broken = encode_proc.stderr.read() if encode_proc.stderr else b""
            except Exception:
                pass
        file_ok = out_path.exists() and out_path.stat().st_size > 1024
        if file_ok:
            print(
                f"[magic_video] BrokenPipeError after {frame_idx} frames but "
                f"out_path exists ({out_path.stat().st_size} bytes) — treating as success.",
                flush=True,
            )
            # Fall through to normal success path (post-except block).
            # We need to let the finally block run, then continue. Use a flag.
        else:
            return h._send_error_v59(
                       500,
                       error_code="ENCODE_EXITED_EARLY",
                       error_message=(
                           f"encode_proc exited after {frame_idx} frames "
                           f"(fps mismatch? source fps != 24fps). "
                           f"Check fps=24 filter in decode_cmd."
                       ),
                       retry_safe=True,
                       extra={
                           "encode_stderr": enc_stderr_broken.decode("utf-8", errors="replace")[-500:],
                           "frames_written": frame_idx,
                       },
                   )
    except subprocess.CalledProcessError as exc:
        return h._send_error_v59(
                   500,
                   error_code="FFMPEG_BLEND_FAILED",
                   error_message="magic_video composite+encode failed",
                   retry_safe=True,
                   extra={"stderr": (exc.stderr or b"").decode("utf-8", errors="replace")[-1000:]},
               )
    except subprocess.TimeoutExpired:
        return h._send_error_v59(
                   504,
                   error_code="FFMPEG_BLEND_TIMED_OUT",
                   error_message="magic_video composite+encode timed out (>300s)",
                   retry_safe=True,
               )
    except Exception as exc:
        traceback.print_exc()
        # Read encode_proc stderr to diagnose why it may have exited early.
        enc_stderr_generic = b""
        if encode_proc is not None and encode_proc.returncode is not None:
            try:
                enc_stderr_generic = encode_proc.stderr.read()
            except Exception:
                pass
        return h._send_error_v59(
                   500,
                   error_code="GENERIC_ERROR",
                   error_message=f"magic_video composite failed: {type(exc).__name__}: {exc}",
                   retry_safe=True,
                   extra={
                       "encode_stderr_snippet": enc_stderr_generic.decode("utf-8", errors="replace")[-500:] if enc_stderr_generic else "",
                   },
               )
    finally:
        # Kill subprocesses if still running (e.g. early-return paths above)
        for proc in (decode_proc, encode_proc):
            if proc is not None:
                try:
                    if proc.returncode is None:
                        proc.kill()
                        proc.wait()
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
                f"path_interp=polyline, gain=1.0, rgb_screen composite; "
                f"source dims {comp_w}x{comp_h}, duration {vid_duration:.2f}s."
            ),
            role="library",
        )
    except Exception as exc:
        print(f"[magic_video] WARN registered_write failed: {exc}", flush=True)

    magic_filename = Path(out_path).name
    magic_sidecar_fields = {
        "magic_video_path": magic_filename,
        "magic_manual_path": clean_path,
        **({"magic_path_authored_against": path_authored_against} if path_authored_against else {}),
    }
    wb = write_magic_delivery(
        h,
        body=body,
        request_beat_id=beat_id,
        partition_fields=magic_sidecar_fields,
        verify_field="magic_video_path",
        expected_value=magic_filename,
        log_tag="magic_video",
        magic_style=magic_style,
        clean_path=clean_path,
        persist_scene_registry=True,
    )
    if wb is None:
        return
    partition_written, sb_beat_id, _ = wb

    return h._send_json(200, {
        "ok": True,
        "beat_id": beat_id,
        "composite_path": str(out_path),
        "magic_video_path": magic_filename,
        "partition_written": partition_written,
        "asset_id": registered_id,
        "source_dims": [comp_w, comp_h],
        "path_authored_against": path_authored_against,
        "duration_s": vid_duration,
        "manual_path_points": len(clean_path),
    })


def handle_storyboard_video_frame(h, query: dict) -> None:
    """GET /api/storyboard/video_frame?path=<encoded>&t=0
    Returns PNG bytes of frame at time t of the given video using server-side ffmpeg.
    """
    import subprocess as _sp
    raw_path = query.get("path", "")
    if isinstance(raw_path, list):
        raw_path = raw_path[0] if raw_path else ""
    if not raw_path:
        return h._send_error_v59(400, error_code="PATH_REQUIRED",
                                 error_message="path required", retry_safe=False)
    p = Path(raw_path)
    if not p.is_absolute():
        p = Path(h.app.event_dir).parent.parent / raw_path
    safe = os.path.realpath(str(p))
    project_root = os.path.realpath(str(Path(h.app.event_dir).parent.parent))
    if not safe.startswith(project_root):
        return h._send_error_v59(403, error_code="PATH_OUT_OF_ROOT",
                                 error_message="path outside project root", retry_safe=False)
    t_raw = query.get("t", "0")
    if isinstance(t_raw, list):
        t_raw = t_raw[0] if t_raw else "0"
    try:
        t = float(t_raw or 0)
    except (ValueError, TypeError):
        t = 0.0
    # LD-828: match MagicCompositor + handle_magic_video canvas (even dims + scale).
    try:
        probe = _sp.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "json", safe],
            capture_output=True, check=True, timeout=15,
        )
        meta = json.loads(probe.stdout.decode("utf-8"))
        stream = (meta.get("streams") or [{}])[0]
        fw = int(stream.get("width") or 1280)
        fh = int(stream.get("height") or 720)
        fw, fh = _magic_canvas_dims(fw, fh)
    except (_sp.CalledProcessError, json.JSONDecodeError, ValueError, TypeError):
        fw, fh = 1280, 720
    cmd = ["ffmpeg", "-y", "-ss", str(t), "-i", safe,
           "-vf", f"scale={fw}:{fh}",
           "-vframes", "1", "-f", "image2pipe", "-vcodec", "png", "pipe:1"]
    try:
        result = _sp.run(cmd, capture_output=True, timeout=10, check=False)
        if result.returncode != 0 or not result.stdout:
            return h._send_error_v59(500, error_code="FFMPEG_FRAME_EXTRACT_FAILED",
                                     error_message=result.stderr.decode('utf-8', errors='replace')[-500:],
                                     retry_safe=True)
        h.send_response(200)
        h.send_header("Content-Type", "image/png")
        h.send_header("Content-Length", str(len(result.stdout)))
        h.send_header("Cache-Control", "no-store")
        h.end_headers()
        h.wfile.write(result.stdout)
    except _sp.TimeoutExpired:
        return h._send_error_v59(504, error_code="FFMPEG_FRAME_EXTRACT_TIMEOUT",
                                 error_message="ffmpeg timed out extracting frame",
                                 retry_safe=True)


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
    from server_handlers.milestone_scope import (
        assert_production_scope,
        milestone_bg_segment,
        parse_scope_query,
    )

    qs_body = parse_scope_query(h)
    ctx = assert_production_scope(
        h, qs_body, allow_missing=True, allow_missing_video_role=True,
    )
    if ctx is None:
        return
    if ctx.is_milestone:
        seg = milestone_bg_segment(ctx)
        return h._send_json(200, {
            "segments": [seg],
            "arc_number": seg["arc_number"],
            "scope_type": "milestone",
            "milestone_id": ctx.milestone_id,
        })

    qs = urllib.parse.parse_qs(urllib.parse.urlparse(h.path).query)
    arc_number = int((qs.get("arc_number") or [1])[0])
    bg = _bg_module()
    segments = bg.get_segments(arc_number)
    return h._send_json(200, {"segments": segments, "arc_number": arc_number})


def _o3_gallery_repair_runtime_key(event_id: str) -> str:
    ev = str(event_id or "").strip()
    if ev.isdigit():
        ev = f"Event_{ev}"
    elif ev and not ev.startswith("Event_"):
        ev = f"Event_{ev}"
    return f"o3_gallery_repair_done_{ev}"


def _o3_admin_reconcile_runtime_key(event_id: str) -> str:
    ev = str(event_id or "").strip()
    if ev.isdigit():
        ev = f"Event_{ev}"
    elif ev and not ev.startswith("Event_"):
        ev = f"Event_{ev}"
    return f"o3_admin_reconcile_done_{ev}"


def _run_o3_admin_reconcile(h, scope_event_id: str | None = None, *, force: bool = False) -> dict:
    """Explicit admin/startup reconcile — intent locks, log pointers, stuck beats."""
    bg = _bg_module()
    prod_root = _data_root(h)
    raw_event = scope_event_id or f"Event_{getattr(h.app, 'event_id', '')}"
    event_num = bg.normalize_bg_event_id(raw_event)
    event_dir = prod_root / f"Event_{event_num}"
    reconcile_key = _o3_admin_reconcile_runtime_key(str(event_num))
    counts = {"intent_locks": 0, "log_pointers": 0, "stuck_beats": 0}
    changed = 0

    sidecar_probe = bg.read_sidecar_for_poll_snapshot(lock_timeout_s=5)
    runtime_probe = sidecar_probe.get("_runtime") or {}
    if not force and runtime_probe.get(reconcile_key):
        return {"ok": True, "skipped": True, "counts": counts, "changed": 0}

    last_err: Exception | None = None
    for attempt in range(12):
        try:

            def _commit(sidecar: dict) -> None:
                nonlocal changed
                bg.ensure_sidecar_schema_defaults(sidecar)
                runtime = sidecar.setdefault("_runtime", {})
                if not force and runtime.get(reconcile_key):
                    return
                from o3_generation_intent import (
                    reconcile_stale_o3_intent_locks,
                    reconcile_stale_o3_intent_locks_all_events,
                )

                if force:
                    counts["intent_locks"] = reconcile_stale_o3_intent_locks_all_events(sidecar, prod_root)
                elif event_dir.is_dir():
                    counts["intent_locks"] = reconcile_stale_o3_intent_locks(sidecar, event_dir)
                counts["log_pointers"] = reconcile_stale_o3_job_log_pointers_all_events(sidecar)
                counts["stuck_beats"] = reconcile_stuck_o3_voice_beats(sidecar)
                changed = sum(counts.values())
                runtime[reconcile_key] = datetime.now(timezone.utc).isoformat()

            bg.mutate_sidecar_locked(_commit, timeout_s=15)
            return {"ok": True, "skipped": False, "counts": counts, "changed": changed}
        except TimeoutError as exc:
            last_err = exc
            if attempt >= 11:
                print("[BG] o3 admin reconcile skipped — sidecar lock busy", flush=True)
                return {"ok": False, "error": "sidecar lock busy", "counts": counts, "changed": 0}
            time.sleep(min(4.0, 0.15 * (2 ** attempt)))
        except OSError as exc:
            last_err = exc
            if not bg.sidecar_io_transient(exc) or attempt >= 11:
                print(f"[BG] o3 admin reconcile failed: {exc}", flush=True)
                return {"ok": False, "error": str(exc), "counts": counts, "changed": 0}
            time.sleep(min(4.0, 0.15 * (2 ** attempt)))
        except Exception as exc:
            print(f"[BG] o3 admin reconcile failed: {exc}", flush=True)
            return {"ok": False, "error": str(exc), "counts": counts, "changed": 0}
    if last_err:
        return {"ok": False, "error": str(last_err), "counts": counts, "changed": 0}
    return {"ok": False, "error": "o3 admin reconcile exhausted retries", "counts": counts, "changed": 0}


def _o3_startup_admin_reconcile_transient(error: str | None) -> bool:
    text = str(error or "")
    return (
        "sidecar lock busy" in text
        or "Resource deadlock avoided" in text
        or "[Errno 11]" in text
        or "[Errno 35]" in text
    )


def run_blocking_o3_startup(app) -> None:
    """Blocking O3 reconcile before HTTP serves traffic (v2 lifecycle spec)."""
    h_stub = type("_H", (), {"app": app})()
    prod_root = _data_root(h_stub)
    scope_event_id = f"Event_{getattr(app, 'event_id', '')}".strip()
    from o3_generation_intent import run_blocking_o3_startup_reconcile

    result = run_blocking_o3_startup_reconcile(prod_root, scope_event_id)
    if result.get("closed"):
        print(f"[startup:o3-blocking-reconcile] closed={result['closed']}", flush=True)
    if result.get("errors"):
        raise RuntimeError(f"O3 startup reconcile errors: {result['errors']}")
    # PARALLEL_EVENT_ISOLATION_V1 — event-scoped admin reconcile only (not all Event_N).
    admin: dict = {"ok": False}
    for attempt in range(12):
        admin = _run_o3_admin_reconcile(h_stub, scope_event_id, force=False)
        if admin.get("ok"):
            break
        if not _o3_startup_admin_reconcile_transient(admin.get("error")) or attempt >= 11:
            raise RuntimeError(f"O3 admin reconcile failed at startup: {admin}")
        delay = min(4.0, 0.15 * (2 ** attempt))
        print(
            f"[startup:o3-blocking-reconcile] retry {attempt + 1}/12 after {admin.get('error')} "
            f"(sleep {delay:.2f}s)",
            flush=True,
        )
        time.sleep(delay)
    print(f"[startup:o3-blocking-reconcile] admin counts={admin.get('counts')}", flush=True)


def schedule_o3_admin_reconcile_at_startup(app, *, force: bool = False) -> None:
    """Deprecated async path — v2 uses run_blocking_o3_startup before serve_forever."""
    del force


def handle_bg_o3_admin_reconcile(h, body: dict) -> None:
    """POST /api/bg/o3/admin-reconcile { force?: bool } — explicit O3 lifecycle heal."""
    if not h._assert_event_scope(h._scope_body(body), allow_missing=True, allow_missing_video_role=True):
        return
    force = bool(body.get("force"))
    scope_event_id = body.get("scope_event_id") or body.get("event_id")
    result = _run_o3_admin_reconcile(h, scope_event_id, force=force)
    return h._send_json(200, result)


def _gallery_repair_beat_delta(before: dict, after: dict) -> dict[str, object]:
    """Fields changed by additive disk reconcile — applied under a short lock only."""
    delta: dict[str, object] = {}
    for key in set(before) | set(after):
        if before.get(key) != after.get(key):
            delta[key] = after.get(key)
    return delta


def _plan_o3_gallery_repair_for_event(
    sidecar: dict,
    event_dir: Path,
) -> list[tuple[str, dict[str, object]]]:
    """Disk-heavy gallery reconcile — must run outside sidecar lock (P4 SQLite authority)."""
    from o3_job_status_contract import clear_o3_pointer_if_terminal

    bg = _bg_module()
    pending: list[tuple[str, dict[str, object]]] = []
    for beat in _iter_bg_beats(sidecar):
        beat_id = str(beat.get("beat_id") or "").strip()
        if not beat_id:
            continue
        beat_event_dirs = bg.resolve_o3_lifecycle_event_dir_candidates(
            beat_id, server_event_dir=event_dir,
        )
        beat_work = copy.deepcopy(beat)
        beat_changed = False
        for beat_event in beat_event_dirs:
            if not beat_event.is_dir():
                continue
            if bg.reconcile_beat_gallery_from_disk(beat_work, beat_event):
                beat_changed = True
            elif clear_o3_pointer_if_terminal(beat_work, beat_event):
                beat_changed = True
        if beat_changed:
            delta = _gallery_repair_beat_delta(beat, beat_work)
            if delta:
                pending.append((beat_id, delta))
    return pending


def _run_o3_gallery_repair_for_event(h, scope_event_id: str, *, force: bool = False) -> int:
    """One-shot additive gallery repair per event — disk scan outside lock, short commit."""
    bg = _bg_module()
    prod_root = _data_root(h)
    event_num = bg.normalize_bg_event_id(scope_event_id)
    event_dir = prod_root / f"Event_{event_num}"
    if not event_dir.is_dir():
        return 0
    repair_key = _o3_gallery_repair_runtime_key(str(event_num))
    sidecar_probe = bg.read_sidecar_for_poll_snapshot(lock_timeout_s=5)
    runtime_probe = sidecar_probe.get("_runtime") or {}
    if not force and runtime_probe.get(repair_key):
        return 0
    pending = _plan_o3_gallery_repair_for_event(sidecar_probe, event_dir)
    changed = 0
    try:

        def _commit(sidecar: dict) -> None:
            nonlocal changed
            bg.ensure_sidecar_schema_defaults(sidecar)
            runtime = sidecar.setdefault("_runtime", {})
            if not force and runtime.get(repair_key):
                return
            for beat_id, delta in pending:
                _, beat = bg.find_beat(sidecar, beat_id)
                if not beat:
                    continue
                beat.update(delta)
                changed += 1
            runtime[repair_key] = datetime.now(timezone.utc).isoformat()

        bg.mutate_sidecar_locked(_commit, timeout_s=10)
        return changed
    except TimeoutError:
        print("[BG] o3 gallery repair skipped — sidecar lock busy", flush=True)
        return 0
    except Exception as exc:
        print(f"[BG] o3 gallery repair failed: {exc}", flush=True)
        return 0


def _compose_o3_session_terminal_view(
    h,
    beats: list,
    sidecar: dict,
) -> list[dict]:
    """Read-only terminal/disk merge for session GET response — no sidecar persist."""
    if not beats:
        return []
    from o3_session_terminal_reconcile import compose_session_terminal_view

    return compose_session_terminal_view(
        beats,
        sidecar,
        server_event_dir=Path(h.app.event_dir),
        library_event_dir=getattr(h.app, "milestone_library_event_dir", None),
        scope_type=str(getattr(h.app, "scope_type", "event") or "event"),
    )


def _apply_o3_session_terminal_reconcile(
    h,
    beats: list,
    sidecar: dict,
    *,
    scope_arc: int | None,
    scope_event_id: str | None,
    scope_phase: str | None,
) -> list[dict]:
    """Persist terminal/disk gallery merges for scope beats; reload beats when changed."""
    if not beats:
        return []
    from o3_session_terminal_reconcile import plan_session_terminal_reconcile

    pending, outcomes = plan_session_terminal_reconcile(
        beats,
        sidecar,
        orphan_recovery=_try_orphan_o3_delivery_recovery,
        server_event_dir=Path(h.app.event_dir),
        library_event_dir=getattr(h.app, "milestone_library_event_dir", None),
        scope_type=str(getattr(h.app, "scope_type", "event") or "event"),
    )
    if not pending:
        return outcomes
    bg = _bg_module()
    try:

        def _commit(sc: dict) -> None:
            bg.ensure_sidecar_schema_defaults(sc)
            for beat_id, delta in pending:
                _, beat = bg.find_beat(sc, beat_id)
                if beat:
                    beat.update(delta)

        bg.mutate_sidecar_locked(_commit, timeout_s=10)
    except TimeoutError:
        print("[BG] session terminal reconcile skipped — sidecar lock busy", flush=True)
        return []
    except Exception as exc:
        print(f"[BG] session terminal reconcile failed: {exc}", flush=True)
        return []
    if scope_arc is not None and scope_event_id is not None and scope_phase is not None:
        try:
            fresh = bg.read_sidecar_for_poll_snapshot(lock_timeout_s=5)
            bg.ensure_sidecar_schema_defaults(fresh)
            seg = bg.get_seg_entry(fresh, scope_arc, scope_event_id, scope_phase)
            beats[:] = seg.get("beats", [])
        except Exception as exc:
            print(f"[BG] session terminal reconcile reload failed: {exc}", flush=True)
    return outcomes


def _normalize_o3_event_dirs(
    event_dirs: Path | list[Path] | tuple[Path, ...],
) -> list[Path]:
    """Coerce single Event dir or candidate list — Path is not iterable (Py3.12+)."""
    if isinstance(event_dirs, Path):
        return [event_dirs]
    return [Path(p) for p in event_dirs]


def _resolve_beat_job_busy_for_session(
    beat: dict,
    event_dirs: Path | list[Path] | tuple[Path, ...],
) -> bool:
    """Single server busy truth — pipeline-specific (still_insert vs O3/GPT)."""
    from o3_job_status_contract import beat_job_busy_in_event_dirs

    event_dirs = _normalize_o3_event_dirs(event_dirs)
    beat_id = str(beat.get("beat_id") or "").strip()
    bg = _bg_module()
    if bg.beat_is_still_insert(beat):
        return bool(beat_id and beat_id in _STILL_RENDER_BUSY)
    busy = beat_job_busy_in_event_dirs(beat, event_dirs, in_memory_jobs=_ARLO_O3_JOBS)
    if beat_id in _STILL_RENDER_BUSY:
        busy = True
    return busy


def _o3_job_scope_dirs(h) -> tuple[Path, Path | None, str]:
    """(server_event_dir, library_event_dir|None, scope_type) for O3 job lifecycle I/O."""
    server = Path(getattr(h.app, "event_dir", _data_root(h) / "Event_1"))
    scope_type = str(getattr(h.app, "scope_type", "event") or "event")
    lib_raw = getattr(h.app, "milestone_library_event_dir", None)
    library = Path(lib_raw).expanduser().resolve() if lib_raw else None
    return server, library, scope_type


def _o3_job_event_dir_candidates(h, beat_id: str) -> list[Path]:
    from o3_generation_intent import resolve_o3_job_event_dir_candidates

    server, library, scope_type = _o3_job_scope_dirs(h)
    return resolve_o3_job_event_dir_candidates(
        beat_id,
        server_event_dir=server,
        library_event_dir=library,
        scope_type=scope_type,
    )


def _o3_job_event_dir(h, beat_id: str) -> Path:
    from o3_generation_intent import resolve_o3_job_event_dir

    server, library, scope_type = _o3_job_scope_dirs(h)
    return resolve_o3_job_event_dir(
        beat_id,
        server_event_dir=server,
        library_event_dir=library,
        scope_type=scope_type,
    )


def _enrich_beats_job_busy(
    beats: list,
    prod_root: Path,
    h,
    *,
    session_read_only: bool = False,
) -> None:
    from o3_job_status_contract import (
        clear_o3_pointer_if_terminal,
        resolve_o3_job_id_for_lifecycle,
    )
    from o3_generation_intent import observe_and_close_stale_o3_attempt

    bg = _bg_module()
    for beat in beats:
        beat_id = str(beat.get("beat_id") or "").strip()
        if not beat_id:
            beat["job_busy"] = False
            beat["o3_current_job_id"] = None
            continue
        beat_event_dirs = _o3_job_event_dir_candidates(h, beat_id)
        beat_event = beat_event_dirs[0]
        if session_read_only:
            from o3_job_status_contract import resolve_o3_current_job_id

            busy = _resolve_beat_job_busy_for_session(beat, beat_event_dirs)
            beat["job_busy"] = busy
            beat["o3_current_job_id"] = resolve_o3_current_job_id(beat) if busy else None
            continue
        if not bg.beat_is_still_insert(beat):
            for ev in beat_event_dirs:
                if clear_o3_pointer_if_terminal(beat, ev):
                    break
        job_id = resolve_o3_job_id_for_lifecycle(beat)
        if job_id and not bg.beat_is_still_insert(beat):
            for ev in beat_event_dirs:
                if observe_and_close_stale_o3_attempt(
                    job_id,
                    beat_id,
                    ev,
                    in_memory_jobs=_ARLO_O3_JOBS,
                    close_stale_running=not session_read_only,
                ):
                    if not session_read_only:
                        try:
                            snap = bg.read_sidecar_for_poll_snapshot(lock_timeout_s=5.0)
                            _, fresh = bg.find_beat(snap, beat_id)
                            if fresh:
                                beat.update({k: v for k, v in fresh.items() if not k.startswith("_")})
                        except Exception:
                            pass
                    break
        busy = _resolve_beat_job_busy_for_session(beat, beat_event_dirs)
        beat["job_busy"] = busy
        from o3_job_status_contract import resolve_o3_current_job_id

        beat["o3_current_job_id"] = resolve_o3_current_job_id(beat) if busy else None


def _beat_o3_operator_lock_active(beat: dict, event_dir: Path) -> bool:
    from o3_job_status_contract import beat_job_busy

    beat_id = str(beat.get("beat_id") or "").strip()
    if beat_id and beat_id in _STILL_RENDER_BUSY:
        return True
    return beat_job_busy(beat, event_dir, in_memory_jobs=_ARLO_O3_JOBS)


def _operator_job_busy_error(message: str) -> dict:
    return {
        "status": 409,
        "error_code": "BEAT_JOB_BUSY",
        "error_message": message,
        "retry_safe": True,
    }


def schedule_operator_workbench_migrate_at_startup(app) -> None:
    """Persist one-time operator workbench heals (library→bg_ref backfill, etc.)."""
    import threading

    def _run() -> None:
        try:
            bg = _bg_module()
            from operator_workbench_contract import migrate_operator_workbench_sidecar

            changed = False

            def _apply(sc: dict) -> bool:
                nonlocal changed
                if migrate_operator_workbench_sidecar(sc):
                    changed = True
                return changed

            try:
                bg.mutate_sidecar_locked(_apply, timeout_s=30)
            except TimeoutError:
                print("[startup:operator-workbench-migrate] skipped — sidecar lock busy", flush=True)
                return
            if changed:
                print("[startup:operator-workbench-migrate] persisted operator workbench heals", flush=True)
        except Exception as exc:
            print(f"[startup:operator-workbench-migrate] failed: {exc}", flush=True)

    threading.Thread(
        target=_run,
        daemon=True,
        name="operator-workbench-migrate",
    ).start()


def schedule_o3_gallery_repair_at_startup(app, *, force: bool = False) -> None:
    """Background additive gallery repair once per event — off session GET hot path."""
    import threading

    scope_event_id = f"Event_{getattr(app, 'event_id', '')}".strip()
    if not scope_event_id or scope_event_id == "Event_":
        return
    h_stub = type("_GalleryRepairHandler", (), {"app": app})()

    def _run() -> None:
        try:
            changed = _run_o3_gallery_repair_for_event(h_stub, scope_event_id, force=force)
            if changed:
                print(
                    f"[startup:o3-gallery-repair] {scope_event_id}: repaired {changed} beat(s)",
                    flush=True,
                )
        except Exception as exc:
            print(f"[startup:o3-gallery-repair] {scope_event_id} failed: {exc}", flush=True)

    threading.Thread(
        target=_run,
        daemon=True,
        name=f"o3-gallery-repair-{getattr(app, 'event_id', 'unknown')}",
    ).start()


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
    # scope_video_role is parsed below from query; do not require it at assert gate.
    from server_handlers.milestone_scope import assert_production_scope, parse_scope_query

    qs_body = parse_scope_query(h)
    pctx = assert_production_scope(
        h,
        qs_body,
        allow_missing=True,
        allow_missing_video_role=True,
        repair_sidecar=False,
    )
    if pctx is None:
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
    scope_video_role = _q("scope_video_role") or _q("scope_target_video") or _q("video")

    if pctx.is_milestone:
        skel = pctx.skeleton_ref or {}
        scope_arc_raw = str(skel.get("arc_number") or 1)
        scope_event_id = str(skel.get("event_id"))
        scope_phase = str(skel.get("phase") or "full")
        scope_video_role = scope_video_role or "standalone"

    bg = _bg_module()
    if scope_event_id is not None:
        scope_event_id = bg.normalize_bg_event_id(scope_event_id)
    force_reconcile_o3 = str(_q("force_reconcile_o3") or "").strip().lower() in ("1", "true", "yes")
    if force_reconcile_o3 and scope_event_id is not None:
        import threading
        threading.Thread(
            target=_run_o3_gallery_repair_for_event,
            args=(h, scope_event_id),
            kwargs={"force": True},
            daemon=True,
        ).start()
    # Session GET is read-only — gallery repair runs at startup or force_reconcile_o3=1 only.
    sidecar = bg.read_sidecar_for_poll_snapshot(lock_timeout_s=5)
    bg.ensure_sidecar_schema_defaults(sidecar)
    event_dir = Path(getattr(h.app, "event_dir", "") or "")
    if force_reconcile_o3 and event_dir.is_dir():
        runtime = sidecar.setdefault("_runtime", {})
        o3_reconcile_changed = bg.reconcile_kling_o3_sidecar(sidecar, event_dir)
        if o3_reconcile_changed:
            try:
                bg.mutate_sidecar_locked(
                    lambda sc: bg.reconcile_kling_o3_sidecar(sc, event_dir),
                    timeout_s=15,
                )
            except TimeoutError:
                print("[BG] force_reconcile_o3 skipped — sidecar lock busy", flush=True)
        runtime["last_o3_disk_reconcile_at"] = datetime.now(timezone.utc).isoformat()
        sidecar = bg.read_sidecar_for_poll_snapshot(lock_timeout_s=5)
        bg.ensure_sidecar_schema_defaults(sidecar)
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
        # Phase derivation: prefer scope video role (intro→pre, resolution→post,
        # standalone→main); fall back to sidecar ctx.phase only for legacy clients
        # that send neither scope_phase nor scope_video_role. This prevents the
        # Beat Generator tab from showing stale resolution/post beats while the
        # page URL/dropdown is on video=intro.
        scope_phase = _BG_PHASE_MAP.get(scope_video_role or "")
    if scope_phase is None:
        # Legacy fallback: sidecar ctx.phase; final fallback "full".
        # final fallback "full". [CONFIRMED against _handle_bg_add_beat
        # SCOPE_ROUTER_V1 docstring at line ~9682] SCOPE_ROUTER_V1 maps
        # video roles intro→pre, resolution→post, standalone→main; here
        # we just pass through what client sent or what sidecar last
        # persisted.
        scope_phase = (ctx.get("phase") if ctx else None) or "full"

    scope_active_context = None
    beats = []
    approved_roots = None
    if scope_arc is not None and scope_event_id is not None:
        seg = bg.get_seg_entry(sidecar, scope_arc, scope_event_id, scope_phase)
        beats = seg.get("beats", [])
        lib_ev = pctx.library_event_dir if pctx.is_milestone else h.app.event_dir
        from lib.event_library import library_image_roots
        approved_roots = library_image_roots(lib_ev, h.app.event_dir.parent)
        scope_active_context = {
            "arc_number": scope_arc,
            "event_id": scope_event_id,
            "phase": scope_phase,
        }
        if pctx.is_milestone:
            scope_active_context["milestone_id"] = pctx.milestone_id
            scope_active_context["scope_type"] = "milestone"

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

    o3_terminal_outcomes: list[dict] = []
    if beats:
        try:
            o3_terminal_outcomes = _compose_o3_session_terminal_view(
                h,
                beats,
                sidecar,
            )
        except Exception as exc:
            print(f"[BG] session terminal compose failed: {exc}", flush=True)

    all_done = beats and all(b.get("flux_options") for b in beats)
    video_role = scope_video_role or ""
    if not video_role and scope_phase:
        for role, phase in _BG_PHASE_MAP.items():
            if phase == scope_phase:
                video_role = role
                break
    if beats and video_role:
        try:
            production_state = h.app.state.read_state()
            from operator_workbench_contract import enrich_beats_for_session_response

            beats = enrich_beats_for_session_response(
                beats,
                sidecar,
                event_id=str(scope_event_id or ""),
                phase=str(scope_phase or "full"),
                approved_roots=approved_roots if scope_arc is not None else None,
                production_state=production_state,
                video_role=video_role,
                event_dir=pctx.root_dir if pctx.is_milestone else h.app.event_dir,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[BG] operator session enrich failed: {exc}", flush=True)
    if beats:
        _enrich_beats_job_busy(beats, _data_root(h), h, session_read_only=True)
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
        "o3_terminal_outcomes": o3_terminal_outcomes,
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
                def _persist_flux(b: dict, _sc: dict) -> None:
                    while len(b.setdefault("flux_options", [])) <= opt_idx:
                        b["flux_options"].append(None)
                    b["flux_options"][opt_idx] = {
                        "request_id": rid, "image_url": url,
                        "local_path": local_path, "key": key,
                    }
                    b["status"] = "stills_pending"

                bg.update_beat_locked(beat_id, _persist_flux)
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


def _log_bg_segment_preserve_activity(
    scope_event_id: str,
    video_role: str,
    outgoing: dict,
) -> None:
    """Best-effort Directus audit when a BG segment is snapshotted on video switch."""
    import threading

    def _do_write() -> None:
        try:
            # CODE tree — credentials_lib sibling under Production/tools/
            _libdir = str(_PSERVER_TOOLS_DIR / "credentials_lib")
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
                "action": "bg_segment_preserved_on_video_switch",
                "performed_by": "production_server.video_set_active",
                "notes": (
                    f"{scope_event_id} {video_role}: "
                    f"{outgoing.get('beat_count', 0)} beats, "
                    f"{outgoing.get('preserved_clip_count', 0)} clips preserved"
                ),
                "details": json.dumps({
                    "scope_event_id": scope_event_id,
                    "video_role": video_role,
                    **outgoing,
                }),
            })
        except Exception as exc:  # noqa: BLE001
            print(f"[BG] directus preserve log failed (non-blocking): {exc}", flush=True)

    threading.Thread(
        target=_do_write,
        daemon=True,
        name=f"bg-preserve-log-{video_role}",
    ).start()


def switch_bg_context_for_video_role(
    h,
    scope_event_id: str,
    from_video_role: str | None,
    to_video_role: str,
) -> dict:
    """Switch Beat Gen sidecar context when the storyboard video role changes.

    On switch away from a role:
      - Rolling Kling O3 segment preserve (clips + manifest under
        ``kling_o3_clips/_preserved/segments/``).
      - Best-effort Directus ``prod_activity_log`` row for restore audit.

    On switch into a role:
      - Updates sidecar ``active_context`` to the scope-canonical segment.
      - Intro-only: ensures canonical mirror tail beat(s) exist (position-
        based penultimate/ultimate export fades apply at Send-to-Stitcher).
    """
    bg = _bg_module()
    event_dir = h.app.event_dir
    outgoing: dict = {}

    if from_video_role and from_video_role != to_video_role:
        try:
            arc_o, evt_o, phase_o = _resolve_bg_segment_for_scope(
                scope_event_id, from_video_role,
            )
            evt_o_str = str(evt_o)
            beat_count = 0

            def _preserve_outgoing(sidecar: dict) -> None:
                nonlocal beat_count, outgoing
                seg_o = bg.get_seg_entry(sidecar, arc_o, evt_o_str, phase_o)
                beat_count = len(seg_o.get("beats") or [])
                preserved = bg.preserve_kling_o3_segment_beats(
                    sidecar,
                    arc_o,
                    evt_o_str,
                    phase_o,
                    event_dir,
                    reason=f"video_switch_{from_video_role}_to_{to_video_role}",
                )
                outgoing = {
                    "video_role": from_video_role,
                    "segment_key": bg.kling_o3_preserved_segment_key(
                        arc_o, evt_o_str, phase_o,
                    ),
                    "preserved_clip_count": preserved,
                    "beat_count": beat_count,
                    "preserve_dir": str(
                        bg.kling_o3_preserved_segment_dir(
                            event_dir, arc_o, evt_o_str, phase_o,
                        ).resolve()
                    ),
                }

            bg.mutate_sidecar_locked(_preserve_outgoing)
            if beat_count > 0:
                _log_bg_segment_preserve_activity(scope_event_id, from_video_role, outgoing)
        except ValueError as exc:
            print(f"[BG] skip outgoing preserve on video switch: {exc}", flush=True)

    arc_t, evt_t, phase_t = _resolve_bg_segment_for_scope(scope_event_id, to_video_role)
    evt_t_str = str(evt_t)
    beat_label = f"arc{arc_t}_event{evt_t}_{phase_t}"

    target_beats: list = []
    scope_active_context: dict = {}

    def _switch_incoming(sidecar: dict) -> None:
        nonlocal target_beats, scope_active_context
        sidecar["active_context"] = {
            "arc_number": arc_t,
            "event_id": evt_t_str,
            "phase": phase_t,
        }
        seg = bg.get_seg_entry(sidecar, arc_t, evt_t_str, phase_t)
        beats = list(seg.get("beats") or [])
        if phase_t == "pre":
            bg.append_intro_canonical_tail_beats(beats, beat_label, phase_t)
            bg.finalize_intro_canonical_tail_beats(
                beats, evt_t_str, phase_t, sidecar=sidecar,
            )
            seg["beats"] = beats
        target_beats = seg.get("beats") or []
        scope_active_context = dict(sidecar["active_context"])

    bg.mutate_sidecar_locked(_switch_incoming)

    print(
        f"[BG] video-role switch {from_video_role!r} -> {to_video_role!r} "
        f"arc={arc_t} event={evt_t_str} phase={phase_t} "
        f"outgoing_beats={outgoing.get('beat_count', 0)} "
        f"target_beats={len(target_beats)}",
        flush=True,
    )
    return {
        "outgoing": outgoing,
        "scope_active_context": scope_active_context,
        "beats": target_beats,
        "had_saved": len(target_beats) > 0,
        "target_video_role": to_video_role,
    }


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
    from server_handlers.milestone_scope import assert_production_scope

    pctx = assert_production_scope(h, body, allow_missing=False)
    if pctx is None:
        return
    if pctx.is_milestone:
        skel = pctx.skeleton_ref or {}
        arc_number = int(skel.get("arc_number") or 1)
        event_id = str(skel.get("event_id"))
        phase = str(skel.get("phase") or "full")
    else:
        arc_number = int(body.get("arc_number", 1))
        event_id = str(body.get("event_id", "1"))
        phase = str(body.get("phase", "full"))
    bg = _bg_module()
    beats: list = []

    def _set_ctx(sidecar: dict) -> None:
        nonlocal beats
        sidecar["active_context"] = {
            "arc_number": arc_number, "event_id": event_id, "phase": phase,
        }
        seg = bg.get_seg_entry(sidecar, arc_number, event_id, phase)
        beats = seg.get("beats", [])

    bg.mutate_sidecar_locked(_set_ctx)
    print(f"[BG] set-active-context arc={arc_number} event={event_id} phase={phase} "
          f"saved_beats={len(beats)}")
    return h._send_json(200, {"beats": beats, "had_saved": len(beats) > 0})


def handle_bg_extract_beats(h, body: dict)-> None:
    """POST /api/bg/extract-beats — deprecated alias for /extract-beats/plan."""
    return handle_bg_extract_beats_plan(h, body)


def handle_bg_extract_beats_plan(h, body: dict) -> None:
    """POST /api/bg/extract-beats/plan — Phase A: Claude beat plan (no sidecar beat write)."""
    from server_handlers.milestone_scope import assert_production_scope

    pctx = assert_production_scope(h, body, allow_missing=False)
    if pctx is None:
        return
    if pctx.is_milestone:
        skel = pctx.skeleton_ref or {}
        arc_number = int(skel.get("arc_number") or 1)
        event_id = str(skel.get("event_id"))
        phase = str(skel.get("phase") or "full")
    else:
        arc_number = int(body.get("arc_number", 1))
        event_id = str(body.get("event_id", "1"))
        phase = str(body.get("phase", "full"))
    bg = _bg_module()
    section = bg.slice_skeleton_section(arc_number, event_id, phase)
    if not (section.get("text") or "").strip():
        return h._send_json(422, {
            "ok": False,
            "code": "SKELETON_SECTION_EMPTY",
            "message": (
                f"No skeleton section for arc={arc_number} event={event_id} phase={phase}"
            ),
            "section_meta": section,
            "retry_safe": True,
        })

    from claude_extract_beats import (
        claude_plan_beats,
        normalize_beats_plan,
        resolve_anthropic_api_key,
    )

    api_key = resolve_anthropic_api_key()
    if not api_key:
        return h._send_json(503, {
            "ok": False,
            "code": "ANTHROPIC_API_KEY_MISSING",
            "message": (
                "Anthropic API key not configured. Add ANTHROPIC_API_KEY to Doppler "
                "(project=mindfulnest, config=dev) or set the env var and restart the server."
            ),
            "retry_safe": False,
        })

    meta = {
        "arc_number": arc_number,
        "event_id": event_id,
        "phase": phase,
        "event_name": section.get("event_name"),
        "m_number": section.get("m_number"),
        "section_label": section.get("section_label"),
        "slice_method": section.get("slice_method"),
    }
    try:
        plan_result = claude_plan_beats(section["text"], meta=meta, api_key=api_key)
    except Exception as exc:
        print(f"[BG] extract-beats/plan Claude error: {exc}")
        traceback.print_exc()
        msg = str(exc)
        return h._send_json(502, {
            "ok": False,
            "error_code": "CLAUDE_PLAN_FAILED",
            "error_message": msg,
            "code": "CLAUDE_PLAN_FAILED",
            "message": msg,
            "retry_safe": True,
        })

    beats_plan = normalize_beats_plan(plan_result.get("beats_plan") or [])
    story_summary = plan_result.get("story_summary") or ""
    seg_name = None
    for s in bg.get_segments(arc_number):
        if str(s["event_id"]) == event_id and s["phase"] == phase:
            seg_name = s["name"]
            break
    try:
        draft = None

        def _plan(sidecar: dict) -> None:
            nonlocal draft
            draft = bg.persist_beat_plan_draft(
                sidecar, arc_number, event_id, phase,
                story_summary, beats_plan,
                source="extract_plan",
                extra={
                    "model_used": plan_result.get("model_used"),
                    "generation_time_ms": plan_result.get("generation_time_ms"),
                    "section_meta": section,
                },
            )
            seg = bg.get_seg_entry(sidecar, arc_number, event_id, phase)
            seg["slice_method"] = section.get("slice_method")
            if seg_name:
                seg["name"] = seg_name
            sidecar["active_context"] = {
                "arc_number": arc_number, "event_id": event_id, "phase": phase,
            }

        bg.mutate_sidecar_locked(_plan)
    except OSError as exc:
        msg = f"Could not save beat plan draft: {exc}"
        print(f"[BG] extract-beats/plan sidecar write error: {exc}")
        return h._send_json(503, {
            "ok": False,
            "error_code": "SIDECAR_WRITE_FAILED",
            "error_message": msg,
            "code": "SIDECAR_WRITE_FAILED",
            "message": msg,
            "retry_safe": True,
            "story_summary": story_summary,
            "beats_plan": beats_plan,
        })

    print(
        f"[BG] extract-beats/plan arc={arc_number} event={event_id} phase={phase} "
        f"beats={len(beats_plan)} slice={section.get('slice_method')}"
    )
    return h._send_json(200, {
        "ok": True,
        "story_summary": story_summary,
        "beats_plan": beats_plan,
        "section_meta": section,
        "slice_method": section.get("slice_method"),
        "model_used": plan_result.get("model_used"),
        "generation_time_ms": plan_result.get("generation_time_ms"),
        "staging_warnings": plan_result.get("staging_warnings") or [],
        "cast_policy": plan_result.get("cast_policy"),
        "sources_loaded": {
            "skeleton_section_chars": section.get("char_count", 0),
            "arc_number": arc_number,
            "event_id": event_id,
            "phase": phase,
            "m_number": section.get("m_number"),
        },
    })


def handle_bg_extract_beats_approve(h, body: dict) -> None:
    """POST /api/bg/extract-beats/approve — Phase B: Kling prompts + sidecar write."""
    from server_handlers.milestone_scope import assert_production_scope

    pctx = assert_production_scope(h, body, allow_missing=False)
    if pctx is None:
        return
    if pctx.is_milestone:
        skel = pctx.skeleton_ref or {}
        arc_number = int(skel.get("arc_number") or 1)
        event_id = str(skel.get("event_id"))
        phase = str(skel.get("phase") or "full")
    else:
        arc_number = int(body.get("arc_number", 1))
        event_id = str(body.get("event_id", "1"))
        phase = str(body.get("phase", "full"))
    force = bool(body.get("force"))
    story_summary = str(body.get("story_summary") or "").strip()
    beats_plan_raw = body.get("beats_plan") or []
    if not beats_plan_raw:
        return h._send_error_v59(
            400,
            error_code="MISSING_BEATS_PLAN",
            error_message="beats_plan array required",
            retry_safe=False,
        )

    from claude_extract_beats import (
        claude_author_kling_prompts,
        normalize_beats_plan,
        resolve_anthropic_api_key,
    )

    api_key = resolve_anthropic_api_key()
    if not api_key:
        return h._send_json(503, {
            "ok": False,
            "code": "ANTHROPIC_API_KEY_MISSING",
            "message": "Anthropic API key not configured.",
            "retry_safe": False,
        })

    beats_plan = normalize_beats_plan(beats_plan_raw)
    bg = _bg_module()
    try:
        bg.mutate_sidecar_locked(
            lambda sc: bg.persist_beat_plan_draft(
                sc, arc_number, event_id, phase,
                story_summary, beats_plan,
                source="modal_pre_approve",
            ),
        )
    except OSError as exc:
        return h._send_error_v59(
            503,
            error_code="SIDECAR_WRITE_FAILED",
            error_message=f"Could not save beat plan draft before approve: {exc}",
            retry_safe=True,
        )

    section = bg.slice_skeleton_section(arc_number, event_id, phase)
    dialogue_count = len([
        r for r in beats_plan
        if str(r.get("beat_type") or "dialogue").lower() not in ("stage_still", "stage_direction")
    ])
    print(
        f"[BG] extract-beats/approve starting arc={arc_number} event={event_id} phase={phase} "
        f"plan_beats={len(beats_plan)} dialogue_beats={dialogue_count}",
        flush=True,
    )
    meta = {
        "arc_number": arc_number,
        "event_id": event_id,
        "phase": phase,
        "event_name": section.get("event_name"),
        "m_number": section.get("m_number"),
    }
    try:
        author_result = claude_author_kling_prompts(
            story_summary, beats_plan, meta=meta, api_key=api_key,
        )
    except Exception as exc:
        print(f"[BG] extract-beats/approve Claude error: {exc}")
        traceback.print_exc()
        return h._send_json(502, {
            "ok": False,
            "code": "CLAUDE_AUTHOR_FAILED",
            "message": str(exc),
            "retry_safe": True,
        })

    prompt_by_index = author_result.get("prompt_by_index") or {}
    beats_plan_final = author_result.get("beats_plan_enriched") or beats_plan
    audit_scope_ids = bg._beat_ids_for_extract_plan(
        beats_plan_final,
        arc_number=arc_number,
        event_id=event_id,
        phase=phase,
    )
    beats: list = []
    author_audit: list = []

    def _approve(sidecar: dict) -> None:
        nonlocal beats, author_audit
        beats = bg.apply_approved_extract_plan(
            sidecar, arc_number, event_id, phase,
            story_summary, beats_plan_final, prompt_by_index,
            force=force,
        )
        bg.resync_kling_author_prompts_pre_audit(beats)
        author_audit = bg.audit_kling_author_enrichment(
            beats, scope_beat_ids=audit_scope_ids,
        )
        if author_audit:
            raise _BgSidecarAbort(
                status=502,
                json_payload={
                    "ok": False,
                    "code": "KLING_AUTHOR_AUDIT_FAILED",
                    "message": (
                        "Kling author enrichment did not stick — beats were NOT saved. "
                        "Re-open the plan and Approve again; report if this repeats."
                    ),
                    "author_audit": author_audit,
                    "author_dialogue_beats": len([
                        r for r in beats_plan
                        if str(r.get("beat_type") or "dialogue").lower() not in (
                            "stage_still", "stage_direction",
                        )
                    ]),
                    "retry_safe": True,
                },
            )
        sidecar["active_context"] = {
            "arc_number": arc_number, "event_id": event_id, "phase": phase,
        }

    try:
        bg.mutate_sidecar_locked(_approve)
    except _BgSidecarAbort as exc:
        print(
            f"[BG] extract-beats/approve AUTHOR AUDIT FAILED arc={arc_number} "
            f"event={event_id} phase={phase}: {author_audit}",
            flush=True,
        )
        return _bg_abort_from_sidecar(h, exc)

    print(
        f"[BG] extract-beats/approve arc={arc_number} event={event_id} phase={phase} "
        f"beats={len(beats)} force={force}"
    )
    _sync_bg_partition_display_order_for_scope(h, _video_role_for_bg_phase(phase))
    author_warnings = list(author_result.get("author_warnings") or [])
    return h._send_json(200, {
        "ok": True,
        "beats": beats,
        "count": len(beats),
        "model_used": author_result.get("model_used"),
        "generation_time_ms": author_result.get("generation_time_ms"),
        "author_dialogue_beats": len(author_result.get("prompt_by_index") or {}),
        "author_warnings": author_warnings,
        "kling_author_applied": True,
    })


def handle_bg_extract_beats_draft_get(h, qs: dict) -> None:
    """GET /api/bg/extract-beats/draft — reload beat plan draft for segment."""
    from server_handlers.milestone_scope import assert_production_scope, parse_scope_query

    qs_body = parse_scope_query(h)
    pctx = assert_production_scope(
        h, qs_body, allow_missing=True, allow_missing_video_role=True,
    )
    if pctx is None:
        return
    if pctx.is_milestone:
        skel = pctx.skeleton_ref or {}
        arc_number = int(skel.get("arc_number") or 1)
        event_id = str(skel.get("event_id"))
        phase = str(skel.get("phase") or "full")
    else:
        scope_event = (qs.get("scope_event_id") or qs.get("event_id") or [""])[0]
        scope_body = {
            "scope_event_id": scope_event,
            "event_id": scope_event,
            "scope_video_role": (qs.get("scope_video_role") or [""])[0],
        }
        if not h._assert_event_scope(scope_body, allow_missing=True):
            return
        try:
            arc_number = int((qs.get("arc_number") or ["1"])[0])
        except ValueError:
            arc_number = 1
        event_id = str((qs.get("event_id") or ["1"])[0])
        phase = str((qs.get("phase") or ["full"])[0])
    bg = _bg_module()
    draft: dict = {}
    try:
        sidecar = bg.read_sidecar()
        seg = bg.get_seg_entry(sidecar, arc_number, event_id, phase)
        draft = seg.get("beat_plan_draft") or {}
        story_summary = (
            (draft.get("story_summary") if isinstance(draft, dict) else None)
            or seg.get("beat_plan_story_summary")
            or ""
        )
        beats_plan = (draft.get("beats_plan") if isinstance(draft, dict) else None) or []
        reconstructed = False
        if not beats_plan:
            beats = seg.get("beats") or []
            if beats:
                beats_plan = bg.segment_beats_to_plan_rows(beats)
                reconstructed = bool(beats_plan)
    except OSError as exc:
        return h._send_error_v59(
            503,
            error_code="SIDECAR_READ_FAILED",
            error_message=str(exc),
            retry_safe=True,
        )
    if not beats_plan:
        return h._send_json(200, {"ok": True, "beat_plan_draft": None, "beats_plan": []})
    from beat_extract_policy import normalize_plan_row

    repaired_plan: list[dict] = []
    for i, row in enumerate(beats_plan, start=1):
        if not isinstance(row, dict):
            continue
        beat_index = int(row.get("beat_index") or i)
        normalized, _warnings = normalize_plan_row(row, beat_index=beat_index)
        repaired_plan.append(normalized)
    beats_plan = repaired_plan
    payload = {
        "ok": True,
        "story_summary": story_summary,
        "beats_plan": beats_plan,
        "reconstructed_from_beats": reconstructed,
    }
    if draft:
        payload["beat_plan_draft"] = draft
    return h._send_json(200, payload)


def handle_bg_extract_beats_draft_save(h, body: dict) -> None:
    """POST /api/bg/extract-beats/draft/save — persist modal beat plan edits to sidecar."""
    from server_handlers.milestone_scope import assert_production_scope

    pctx = assert_production_scope(h, body, allow_missing=False)
    if pctx is None:
        return
    if pctx.is_milestone:
        skel = pctx.skeleton_ref or {}
        arc_number = int(skel.get("arc_number") or 1)
        event_id = str(skel.get("event_id"))
        phase = str(skel.get("phase") or "full")
    else:
        arc_number = int(body.get("arc_number", 1))
        event_id = str(body.get("event_id", "1"))
        phase = str(body.get("phase", "full"))
    story_summary = str(body.get("story_summary") or "").strip()
    beats_plan_raw = body.get("beats_plan") or []
    if not beats_plan_raw:
        return h._send_error_v59(
            400,
            error_code="MISSING_BEATS_PLAN",
            error_message="beats_plan array required",
            retry_safe=False,
        )

    from claude_extract_beats import normalize_beats_plan

    beats_plan = normalize_beats_plan(beats_plan_raw)
    bg = _bg_module()
    try:
        draft = None

        def _save_draft(sidecar: dict) -> None:
            nonlocal draft
            draft = bg.persist_beat_plan_draft(
                sidecar, arc_number, event_id, phase,
                story_summary, beats_plan,
                source=str(body.get("source") or "modal_autosave"),
            )
            sidecar["active_context"] = {
                "arc_number": arc_number, "event_id": event_id, "phase": phase,
            }

        bg.mutate_sidecar_locked(_save_draft)
    except OSError as exc:
        return h._send_error_v59(
            503,
            error_code="SIDECAR_WRITE_FAILED",
            error_message=f"Could not save beat plan draft: {exc}",
            retry_safe=True,
        )

    print(
        f"[BG] extract-beats/draft/save arc={arc_number} event={event_id} phase={phase} "
        f"beats={len(draft.get('beats_plan') or [])}",
        flush=True,
    )
    _sync_bg_partition_display_order_for_scope(h, _video_role_for_bg_phase(phase))
    return h._send_json(200, {
        "ok": True,
        "story_summary": draft.get("story_summary") or "",
        "beats_plan": draft.get("beats_plan") or [],
        "beat_plan_draft": draft,
        "saved_at": draft.get("updated_at"),
        "count": len(draft.get("beats_plan") or []),
    })


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
    def _inject(sidecar: dict) -> None:
        seg = bg.get_seg_entry(sidecar, arc_number, event_id, phase)
        existing = {b["beat_id"]: b for b in (seg.get("beats") or [])}
        _PRESERVE = (
            "flux_options", "gpt_options",
            "bg_gpt_batch_job_id", "bg_gpt_batch_job_started_at",
            "accepted_image_key", "accepted_library_ref", "accepted_local_path", "accepted_video_path",
            "status", "reference_image", "bg_ref_image",
            "kling_o3_status", "kling_o3_video_path", "kling_o3_options",
            "kling_o3_selected_option_key", "kling_o3_selected_at", "kling_o3_task_id",
            "kling_o3_trim_start", "kling_o3_trim_back", "kling_o3_trim_end",
            "kling_o3_prompt", "kling_o3_duration", "kling_o3_duration_locked",
            "kling_o3_generation", "kling_o3_model", "kling_o3_submit_response", "kling_o3_poll_result",
            "kling_o3_completed_at", "kling_o3_error",
            "kling_o3_voice_fix_status", "kling_o3_voice_fix_audio_path",
            "kling_o3_voice_fix_attempt_id", "kling_o3_voice_fix_phase",
            "kling_o3_voice_fix_error_code", "kling_o3_voice_fix_updated_at",
            "kling_o3_voice_fix_ui_job_id", "kling_o3_voice_fix_job_log_path",
            "kling_o3_voice_fix_job_started_at", "kling_o3_voice_fix_job_pid",
            "kling_o3_voice_fix_job_completed_at", "kling_o3_voice_fix_job_result",
            "kling_o3_voice_fix_lipsync_audio_path",
            "kling_o3_voice_fix_lipsync_padding",
            "kling_o3_voice_fix_voice_id", "kling_o3_voice_fix_spoken_text",
            "kling_o3_voice_fix_audio_duration_s",
            "kling_o3_voice_fix_task_id", "kling_o3_voice_fix_result",
            "kling_o3_voice_fix_base_video_path",
            "kling_o3_voice_fix_silent_video_path",
            "kling_o3_voice_fix_lipsync_input_path",
            "kling_o3_voice_fix_lipsync_input_profile",
            "kling_o3_voice_fix_provider_contract",
            "kling_o3_voice_fix_lipsync_transport",
            "kling_o3_voice_fix_url_preflight",
            "kling_o3_voice_fix_url_transport_error",
            "kling_o3_voice_fix_lipsync_quality",
            "kling_o3_voice_fix_output_profile",
            "kling_o3_voice_fix_lipsync_audio_check",
            "kling_o3_voice_fix_output_duration_s",
            "kling_o3_voice_fix_completed_at",
            "kling_o3_voice_fix_error",
            "arlo_visual_quality",
        )
        for b in mapped_beats:
            saved = existing.get(b["beat_id"])
            if saved:
                for field in _PRESERVE:
                    if field in saved and saved[field] is not None:
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

    bg.mutate_sidecar_locked(_inject)
    print(f"[BG] injected {len(mapped_beats)} beats arc={arc_number} event={event_id} phase={phase}")
    return h._send_json(200, {"ok": True, "count": len(mapped_beats), "beat_ids": beat_ids})


# Prompt / dialogue / slot edits must not re-run Element @Image1 gate — only identity fields.
_BG_ELEMENT_CHAR_REF_SYNC_FIELDS = frozenset({"speaker", "reference_image"})


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
        "kling_o3_prompt", "kling_o3_prompt_still",
        "accepted_image_key", "reference_image", "bg_ref_image",
        "kling_o3_replace_slot_index",
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
    written: list[str] = []
    element_ref_warning = None
    element_ref_registered = None
    identity_fields_written: set[str] = set()
    pre_reg_result: dict | None = None
    pre_reg_gate_ok: bool | None = None
    pre_reg_gate_err: str | None = None
    if "reference_image" in body:
        try:
            snap = bg.read_sidecar_for_poll_snapshot(lock_timeout_s=2.0)
            bg.ensure_sidecar_schema_defaults(snap)
            _, beat_pre = bg.find_beat(snap, str(beat_id))
            if beat_pre:
                pre_work = copy.deepcopy(beat_pre)
                ref_val = body.get("reference_image")
                if isinstance(ref_val, dict):
                    bg.apply_user_beat_ref_update(pre_work, "reference_image", ref_val)
                speaker_pre = str(pre_work.get("speaker") or "").strip()
                try:
                    from credentials import load_credentials  # type: ignore
                except ImportError:
                    from tools.credentials_lib.credentials import load_credentials  # type: ignore
                creds_pre = load_credentials()
                ws_key_pre = creds_pre.get("wavespeed_key") or creds_pre.get("wavespeed")
                if bg.element_char_ref_required_for_beat(pre_work, snap):
                    needs_register_pre = pre_work.get("element_char_ref_ok") is False
                    if not needs_register_pre and ws_key_pre and speaker_pre:
                        from tools import kling_character_registry as reg

                        char_path_pre = bg.resolve_beat_char_ref_path(pre_work) or ""
                        if char_path_pre:
                            strict_ok, _ = reg.char_ref_matches_element_images(
                                char_path_pre, speaker_pre, allow_pose_dir_fallback=False,
                            )
                            needs_register_pre = not strict_ok
                    if needs_register_pre and ws_key_pre and speaker_pre:
                        pre_reg_result = bg.try_register_dropped_char_ref_on_element(
                            pre_work, ws_key_pre,
                        )
                        if pre_reg_result.get("ok"):
                            bg.sync_element_char_ref_status(pre_work, heal_mismatch=False, sidecar=snap)
                            gate = pre_work.get("element_char_ref_ok")
                            if isinstance(gate, bool):
                                pre_reg_gate_ok = gate
                                pre_reg_gate_err = pre_work.get("element_char_ref_error")
                            if pre_work.get("element_char_ref_ok"):
                                try:
                                    from tools import kling_character_registry as reg

                                    display = reg.kling_element_display_name(speaker_pre) or speaker_pre
                                except Exception:
                                    display = speaker_pre
                                action = pre_reg_result.get("action") or "registered"
                                pose = pre_reg_result.get("pose_rel") or ""
                                element_ref_registered = (
                                    f"Registered on {display} Element ({action})"
                                    + (f" — {pose}" if pose else "")
                                    + ". Generate unlocked."
                                )
                else:
                    bg.sync_element_char_ref_status(pre_work, heal_mismatch=False, sidecar=snap)
        except Exception as exc:
            print(f"[bg_update_beat] pre-lock element registration: {exc}", flush=True)
    event_dir = Path(getattr(h.app, "event_dir", _data_root(h)))
    if not event_dir.is_absolute():
        event_dir = _data_root(h) / event_dir
    written: list = []
    identity_fields_written: set = set()
    beat: dict | None = None
    pre_reg_result: dict | None = None

    def _patch_beat(b: dict, sidecar: dict) -> None:
        nonlocal written, identity_fields_written, thumb_b64, element_ref_warning
        nonlocal element_ref_registered, pre_reg_result, pre_reg_gate_ok, pre_reg_gate_err
        operator_fields_requested = {f for f in _BG_BEAT_WRITABLE if f in body}
        prompt_save_unchanged = (
            operator_fields_requested == {"kling_o3_prompt"}
            and str(body.get("kling_o3_prompt") or "").strip()
            == str(b.get("kling_o3_prompt") or "").strip()
        )
        if operator_fields_requested and not prompt_save_unchanged:
            try:
                from o3_generation_intent import OPERATOR_MUTABLE_FIELDS

                if _beat_o3_operator_lock_active(b, event_dir):
                    blocked = sorted(OPERATOR_MUTABLE_FIELDS & operator_fields_requested)
                    if (
                        "kling_o3_prompt" in blocked
                        and "kling_o3_prompt" in body
                    ):
                        new_prompt = str(body.get("kling_o3_prompt") or "").strip()
                        old_prompt = str(b.get("kling_o3_prompt") or "").strip()
                        if new_prompt == old_prompt:
                            blocked = [f for f in blocked if f != "kling_o3_prompt"]
                    if blocked:
                        raise _BgSidecarAbort(
                            status=409,
                            error_code="INTENT_JOB_ACTIVE",
                            error_message=(
                                "O3 generation intent is active — "
                                f"cannot modify {', '.join(blocked)} until the job finishes."
                            ),
                            retry_safe=True,
                        )
            except _BgSidecarAbort:
                raise
            except Exception:
                if _beat_o3_operator_lock_active(b, event_dir):
                    raise _BgSidecarAbort(
                        status=409,
                        error_code="INTENT_JOB_ACTIVE",
                        error_message="O3 job is running — beat fields are locked until it finishes.",
                        retry_safe=True,
                    )
        written = []
        for field in _BG_BEAT_WRITABLE:
            if field in body:
                value = body[field]
                if field == "kling_o3_replace_slot_index":
                    try:
                        value = max(0, min(2, int(value)))
                    except (TypeError, ValueError):
                        raise _BgSidecarAbort(
                            status=400,
                            error_code="INVALID_REPLACE_SLOT",
                            error_message="kling_o3_replace_slot_index must be 0, 1, or 2",
                            retry_safe=False,
                        )
                if field in bg.BEAT_REF_LOCK_FIELDS and isinstance(value, dict):
                    abs_path = value.get("abs_path") or ""
                    if not value.get("thumb_b64"):
                        from lib.event_library import ref_image_thumb_b64

                        _t = ref_image_thumb_b64(abs_path, h.app._library_root_dirs())
                        if _t:
                            value = dict(value)
                            value["thumb_b64"] = _t
                            thumb_b64 = _t
                if field in bg.BEAT_REF_LOCK_FIELDS:
                    bg.apply_user_beat_ref_update(b, field, value)
                    if (
                        field == "bg_ref_image"
                        and isinstance(value, dict)
                        and bg.beat_is_still_insert(b)
                        and value.get("abs_path")
                    ):
                        from operator_workbench_contract import write_still_scene_source
                        from pathlib import Path as _Path

                        ap = str(value.get("abs_path") or "")
                        write_still_scene_source(
                            b,
                            key=str(value.get("key") or _Path(ap).stem),
                            filename=str(value.get("filename") or _Path(ap).name),
                            abs_path=ap,
                            slot_index=0,
                            thumb_b64=value.get("thumb_b64"),
                            source="ref_slot_drop",
                        )
                elif field == "speaker" and isinstance(value, str):
                    old_speaker = str(b.get("speaker") or "").strip()
                    b[field] = _canonicalize_speaker(value)
                    if old_speaker != str(b.get("speaker") or "").strip():
                        bg.realign_beat_char_ref_for_speaker_change(
                            b, old_speaker=old_speaker,
                        )
                elif field not in ("kling_o3_prompt", "kling_o3_prompt_still"):
                    b[field] = value
                written.append(field)
                if field == "speaker":
                    sp = str(b.get("speaker") or "").strip()
                    if sp and bg._speaker_has_element_bound_voice(sp):
                        from beat_extract_policy import kling_face_scene_notes

                        notes = str(b.get("scene_notes") or "")
                        healed_notes = kling_face_scene_notes(sp, notes)
                        if healed_notes != notes:
                            b["scene_notes"] = healed_notes
                if field == "kling_o3_prompt" and isinstance(value, str):
                    text = value.strip()
                    if text:
                        from beat_extract_policy import strip_auto_injected_continuity_blocks

                        cleaned = strip_auto_injected_continuity_blocks(text)
                        if cleaned != text:
                            text = cleaned
                            value = cleaned
                        bg.stamp_o3_prompt_box_law(b, text)
                        b.pop("kling_o3_prior_beat_context", None)
                        b.pop("beat_continuity_v1", None)
                    else:
                        bg.clear_o3_prompt_box_law(b)
                        b.pop("kling_o3_prior_beat_context", None)
                        b.pop("beat_continuity_v1", None)
                    bg.sync_beat_dialogue_from_kling_prompt(b)
                    bg.sync_beat_scene_notes_from_kling_prompt(b)
                if field == "kling_o3_prompt_still" and isinstance(value, str):
                    bg.set_beat_still_prompt(b, value)
        identity_fields_written = set(written) & _BG_ELEMENT_CHAR_REF_SYNC_FIELDS
        if isinstance(pre_reg_gate_ok, bool):
            b["element_char_ref_ok"] = pre_reg_gate_ok
            if pre_reg_gate_ok:
                b.pop("element_char_ref_error", None)
            elif pre_reg_gate_err:
                b["element_char_ref_error"] = pre_reg_gate_err
        elif identity_fields_written:
            bg.sync_element_char_ref_status(b, heal_mismatch=False, sidecar=sidecar)
        if (
            "reference_image" in written
            and pre_reg_result is not None
            and not pre_reg_result.get("ok")
            and b.get("element_char_ref_ok") is False
            and bg.element_char_ref_required_for_beat(b, sidecar)
        ):
            detail = (b.get("element_char_ref_error") or "").strip()
            element_ref_warning = (
                "Char ref saved on this beat, but Element registration failed. "
                "Try Add to Element from library preview (Loral), or drop the pose again."
                + (f" ({detail})" if detail else "")
            )

    try:
        ok, beat = bg.update_beat_locked(beat_id, _patch_beat)
    except _BgSidecarAbort as exc:
        return _bg_abort_from_sidecar(h, exc)
    except TimeoutError as exc:
        return h._send_error_v59(
            503,
            error_code="SIDECAR_LOCK_TIMEOUT",
            error_message=str(exc) or "sidecar lock busy — retry shortly",
            retry_safe=True,
        )
    except OSError as exc:
        if bg.sidecar_io_transient(exc):
            return h._send_error_v59(
                503,
                error_code="SIDECAR_IO_TRANSIENT",
                error_message=str(exc) or "Dropbox sync blocked save — retry shortly",
                retry_safe=True,
                extra={"errno": getattr(exc, "errno", None)},
            )
        raise
    if not ok:
        return h._send_error_v59(
            404,
            error_code="BEAT_NOT_FOUND",
            error_message=f"beat {beat_id} not found",
            retry_safe=False,
        )
    payload = {
        "ok": True,
        "written": written,
        "thumb_b64": thumb_b64,
        "element_ref_warning": element_ref_warning,
        "element_ref_registered": element_ref_registered,
    }
    # Prompt-only saves must not push gate fields — UI keeps prior registration state.
    if identity_fields_written:
        payload["element_char_ref_ok"] = beat.get("element_char_ref_ok")
        payload["element_char_ref_error"] = beat.get("element_char_ref_error")
    return h._send_json(200, payload)


def handle_bg_align_element_ref(h, body: dict) -> None:
    """POST /api/bg/align-element-ref {beat_id} -> canonical Element pose for speaker."""
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
    thumb_b64 = None
    sidecar_probe = bg._load_sidecar_migrated()
    _, beat_probe = bg.find_beat(sidecar_probe, beat_id)
    if not beat_probe:
        return h._send_error_v59(
            404,
            error_code="BEAT_NOT_FOUND",
            error_message=f"beat {beat_id} not found",
            retry_safe=False,
        )
    if beat_probe.get("reference_image_locked") and body.get("force") is not True:
        return h._send_error_v59(
            409,
            error_code="REFERENCE_IMAGE_LOCKED",
            error_message=(
                "Char ref is locked to your library upload. Clear the ref first, "
                "then use Use Element pose — or reconcile will run automatically on O3 submit."
            ),
            retry_safe=False,
        )
    speaker = str(beat_probe.get("speaker") or "").strip()
    try:
        from credentials import load_credentials  # type: ignore
    except ImportError:
        from tools.credentials_lib.credentials import load_credentials  # type: ignore
    creds = load_credentials()
    ws_key = creds.get("wavespeed_key") or creds.get("wavespeed")
    reconciled = False
    if speaker and ws_key:
        char_path = bg.resolve_beat_char_ref_path(beat_probe) or ""
        if char_path:
            try:
                from tools import kling_character_registry as reg

                if reg.is_speaker_voice_ready(speaker):
                    result = reg.reconcile_char_ref_with_element(
                        speaker, char_path, ws_key,
                    )
                    reconciled = bool(result.get("reconciled"))
            except Exception:
                pass

    aligned = False
    beat: dict | None = None

    def _align_patch(b: dict, _sidecar: dict) -> None:
        nonlocal aligned, thumb_b64, reconciled
        if reconciled:
            bg.sync_element_char_ref_status(b, heal_mismatch=False)
            if b.get("element_char_ref_ok"):
                ref = b.get("reference_image")
                if isinstance(ref, dict) and ref.get("abs_path") and not ref.get("thumb_b64"):
                    from lib.event_library import ref_image_thumb_b64

                    _t = ref_image_thumb_b64(ref["abs_path"], h.app._library_root_dirs())
                    if _t:
                        b["reference_image"] = dict(ref)
                        b["reference_image"]["thumb_b64"] = _t
                        thumb_b64 = _t
                return
        if b.get("reference_image_locked"):
            b["reference_image_locked"] = False
        aligned = bg.align_beat_reference_to_element(b)
        bg.sync_element_char_ref_status(b, heal_mismatch=False)
        ref = b.get("reference_image")
        if isinstance(ref, dict):
            abs_path = ref.get("abs_path") or ""
            if abs_path and not ref.get("thumb_b64"):
                from lib.event_library import ref_image_thumb_b64

                _t = ref_image_thumb_b64(abs_path, h.app._library_root_dirs())
                if _t:
                    b["reference_image"] = dict(ref)
                    b["reference_image"]["thumb_b64"] = _t
                    thumb_b64 = _t

    ok, beat = bg.update_beat_locked(beat_id, _align_patch)
    if not ok:
        return h._send_error_v59(
            404,
            error_code="BEAT_NOT_FOUND",
            error_message=f"beat {beat_id} not found",
            retry_safe=False,
        )
    if reconciled and beat and beat.get("element_char_ref_ok"):
        return h._send_json(200, {
            "ok": True,
            "aligned": False,
            "reconciled": True,
            "reference_image": beat.get("reference_image"),
            "thumb_b64": thumb_b64,
            "element_char_ref_ok": beat.get("element_char_ref_ok"),
            "element_char_ref_error": beat.get("element_char_ref_error"),
        })
    return h._send_json(200, {
        "ok": True,
        "aligned": aligned,
        "reference_image": beat.get("reference_image"),
        "thumb_b64": thumb_b64,
        "element_char_ref_ok": beat.get("element_char_ref_ok"),
        "element_char_ref_error": beat.get("element_char_ref_error"),
    })


def handle_bg_add_element_pose(h, body: dict) -> None:
    """POST /api/bg/add-element-pose — register beat/library PNG as Element pose."""
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return
    beat_id = body.get("beat_id")
    speaker = (body.get("speaker") or "").strip()
    abs_path = (body.get("abs_path") or "").strip()
    bg = _bg_module()

    sidecar_probe = bg._load_sidecar_migrated()
    beat = None
    if beat_id:
        _, beat = bg.find_beat(sidecar_probe, beat_id)
        if not beat:
            return h._send_error_v59(
                404,
                error_code="BEAT_NOT_FOUND",
                error_message=f"beat {beat_id} not found",
                retry_safe=False,
            )
        if not speaker:
            speaker = (beat.get("speaker") or "").strip()
    if beat:
        from operator_workbench_contract import materialize_char_ref_abs_path

        abs_path = materialize_char_ref_abs_path(beat, abs_path)
    if not speaker:
        return h._send_error_v59(
            400,
            error_code="MISSING_SPEAKER",
            error_message="speaker or beat_id with speaker required",
            retry_safe=False,
        )
    if not abs_path or not os.path.isfile(abs_path):
        return h._send_error_v59(
            400,
            error_code="MISSING_POSE_SOURCE",
            error_message="abs_path to pose PNG required (or beat with reference_image)",
            retry_safe=False,
        )

    try:
        from credentials import load_credentials  # type: ignore
    except ImportError:
        from tools.credentials_lib.credentials import load_credentials  # type: ignore
    creds = load_credentials()
    wavespeed_key = creds.get("wavespeed_key") or creds.get("wavespeed")
    if not wavespeed_key:
        return h._send_error_v59(
            503,
            error_code="WAVESPEED_NOT_CONFIGURED",
            error_message="WAVESPEED_API_KEY not configured",
            retry_safe=False,
        )

    try:
        from tools import kling_character_registry as reg

        from server_handlers.milestone_scope import rebind_bg_paths_from_app

        rebind_bg_paths_from_app(h.app)
        result = reg.add_element_pose(speaker, abs_path, wavespeed_key)
    except Exception as exc:
        return h._send_error_v59(
            500,
            error_code="ADD_ELEMENT_POSE_FAILED",
            error_message=str(exc),
            retry_safe=True,
        )

    thumb_b64 = None
    element_char_ref_ok = None
    if beat_id:

        def _pose_patch(b: dict, _sc: dict) -> None:
            nonlocal thumb_b64, element_char_ref_ok
            ref = b.get("reference_image")
            if isinstance(ref, dict) and (ref.get("abs_path") or "") == abs_path:
                bg.ensure_beat_element_char_ref_for_o3(b, wavespeed_key)
                element_char_ref_ok = b.get("element_char_ref_ok")
                if not ref.get("thumb_b64"):
                    from lib.event_library import ref_image_thumb_b64

                    _t = ref_image_thumb_b64(abs_path, h.app._library_root_dirs())
                    if _t:
                        b["reference_image"] = dict(ref)
                        b["reference_image"]["thumb_b64"] = _t
                        thumb_b64 = _t

        bg.update_beat_locked(beat_id, _pose_patch)

    payload = dict(result)
    if element_char_ref_ok is not None:
        payload["element_char_ref_ok"] = element_char_ref_ok
    if thumb_b64:
        payload["thumb_b64"] = thumb_b64
    return h._send_json(200, payload)


def handle_bg_set_element_identity(h, body: dict) -> None:
    """POST /api/bg/set-element-identity — sole path to update Element frontal_image."""
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return
    beat_id = body.get("beat_id")
    speaker = (body.get("speaker") or "").strip()
    abs_path = (body.get("abs_path") or "").strip()
    bg = _bg_module()

    sidecar_probe = bg._load_sidecar_migrated()
    beat = None
    if beat_id:
        _, beat = bg.find_beat(sidecar_probe, beat_id)
        if not beat:
            return h._send_error_v59(
                404,
                error_code="BEAT_NOT_FOUND",
                error_message=f"beat {beat_id} not found",
                retry_safe=False,
            )
        if not speaker:
            speaker = (beat.get("speaker") or "").strip()
    if beat:
        from operator_workbench_contract import materialize_char_ref_abs_path

        abs_path = materialize_char_ref_abs_path(beat, abs_path)
    if not speaker:
        return h._send_error_v59(
            400,
            error_code="MISSING_SPEAKER",
            error_message="speaker or beat_id with speaker required",
            retry_safe=False,
        )
    if not abs_path or not os.path.isfile(abs_path):
        return h._send_error_v59(
            400,
            error_code="MISSING_POSE_SOURCE",
            error_message="abs_path to pose PNG required (or beat with reference_image)",
            retry_safe=False,
        )

    try:
        from credentials import load_credentials  # type: ignore
    except ImportError:
        from tools.credentials_lib.credentials import load_credentials  # type: ignore
    creds = load_credentials()
    wavespeed_key = creds.get("wavespeed_key") or creds.get("wavespeed")
    if not wavespeed_key:
        return h._send_error_v59(
            503,
            error_code="WAVESPEED_NOT_CONFIGURED",
            error_message="WAVESPEED_API_KEY not configured",
            retry_safe=False,
        )

    try:
        from tools import kling_character_registry as reg

        from server_handlers.milestone_scope import rebind_bg_paths_from_app

        rebind_bg_paths_from_app(h.app)
        result = reg.set_element_identity(speaker, abs_path, wavespeed_key)
    except reg.ElementVisualCanonicalError as exc:
        return h._send_error_v59(
            409,
            error_code="ELEMENT_VISUAL_CANONICAL_ERROR",
            error_message=str(exc),
            retry_safe=False,
        )
    except Exception as exc:
        return h._send_error_v59(
            500,
            error_code="SET_ELEMENT_IDENTITY_FAILED",
            error_message=str(exc),
            retry_safe=True,
        )

    healed_beat_ids: list[str] = []

    def _fleet_heal(sc: dict) -> None:
        nonlocal healed_beat_ids
        healed_beat_ids = bg.heal_event_beats_to_canonical_frontal(
            sc,
            str(result.get("character") or speaker),
            str(result.get("pose_abs_path") or abs_path),
            pose_rel=str(result.get("pose_rel") or ""),
            wavespeed_key=wavespeed_key,
        )

    try:
        bg.mutate_sidecar_locked(
            _fleet_heal,
            caller="handle_bg_set_element_identity_fleet_heal",
        )
    except Exception:
        healed_beat_ids = []

    thumb_b64 = None
    element_char_ref_ok = None
    if beat_id:

        def _identity_patch(b: dict, _sc: dict) -> None:
            nonlocal thumb_b64, element_char_ref_ok
            b["reference_image_locked"] = True
            ref = b.get("reference_image")
            if isinstance(ref, dict) and (ref.get("abs_path") or "") == abs_path:
                bg.ensure_beat_element_char_ref_for_o3(b, wavespeed_key)
                element_char_ref_ok = b.get("element_char_ref_ok")
                if not ref.get("thumb_b64"):
                    from lib.event_library import ref_image_thumb_b64

                    _t = ref_image_thumb_b64(abs_path, h.app._library_root_dirs())
                    if _t:
                        b["reference_image"] = dict(ref)
                        b["reference_image"]["thumb_b64"] = _t
                        thumb_b64 = _t
            else:
                bg.ensure_beat_element_char_ref_for_o3(b, wavespeed_key)
                element_char_ref_ok = b.get("element_char_ref_ok")

        bg.update_beat_locked(beat_id, _identity_patch)

    payload = dict(result)
    if healed_beat_ids:
        payload["healed_beat_ids"] = healed_beat_ids
    if element_char_ref_ok is not None:
        payload["element_char_ref_ok"] = element_char_ref_ok
    if thumb_b64:
        payload["thumb_b64"] = thumb_b64
    return h._send_json(200, payload)


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
    sidecar_probe = bg.read_sidecar()
    sidecar_probe = bg._migrate_sidecar(sidecar_probe)
    ctx = sidecar_probe.get("active_context")
    scope_event_id = body.get("scope_event_id")
    if scope_event_id is None:
        scope_event_id = body.get("event_id")
    if scope_event_id is not None:
        scope_event_id = bg.normalize_bg_event_id(scope_event_id)
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

    seg_probe = bg.get_seg_entry(sidecar_probe, scope_arc, scope_event_id, scope_phase)
    existing_beats = seg_probe.get("beats", [])
    existing_ids = {b.get("beat_id") for b in existing_beats if b.get("beat_id")}
    incoming_ids = [bid for bid in beat_ids if bid]
    if len(incoming_ids) != len(existing_ids):
        return h._send_error_v59(
            400,
            error_code="REORDER_BEAT_COUNT_MISMATCH",
            error_message=(
                f"beat_ids must include every beat in the segment "
                f"({len(existing_ids)} expected, got {len(incoming_ids)})"
            ),
            retry_safe=False,
        )
    if set(incoming_ids) != existing_ids:
        return h._send_error_v59(
            400,
            error_code="REORDER_BEAT_SET_MISMATCH",
            error_message="beat_ids must be a reorder of the existing segment beats only",
            retry_safe=False,
        )

    def _reorder(sidecar: dict) -> None:
        ctx_l = sidecar.get("active_context")
        if ctx_l and (
            ctx_l.get("arc_number") != scope_active_context["arc_number"]
            or ctx_l.get("event_id") != scope_active_context["event_id"]
            or (ctx_l.get("phase") or "full") != scope_active_context["phase"]
        ):
            warnings = list(sidecar.get("migration_warnings", []))
            warnings.append({
                "type": "scope_active_context_divergence",
                "message": (
                    "reorder-beats scope differs from sidecar.active_context — "
                    "scope is canonical per LD-545 Option B"
                ),
                "scope": scope_active_context,
                "active_context": ctx_l,
            })
            sidecar["migration_warnings"] = warnings
        seg = bg.get_seg_entry(sidecar, scope_arc, scope_event_id, scope_phase)
        beats = seg.get("beats", [])
        beat_map = {b["beat_id"]: b for b in beats}
        seg["beats"] = [beat_map[bid] for bid in beat_ids if bid in beat_map]

    bg.mutate_sidecar_locked(_reorder, migrate=True)
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

    ok = bg.delete_beat_locked(str(beat_id), caller="handle_bg_delete_beat", migrate=True)
    if not ok:
        return h._send_error_v59(
            404,
            error_code="BEAT_NOT_FOUND",
            error_message=f"beat not found: {beat_id}",
            retry_safe=False,
        )
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

    def _accept(sidecar: dict) -> None:
        for bid in beat_ids:
            _, beat = bg.find_beat(sidecar, bid)
            if beat:
                beat["status"] = "accepted"

    bg.mutate_sidecar_locked(_accept)
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
            _bg_beat = _bg_beat_map.get(beat.get("beat_id", ""), {})
            video_path = (
                _bg_beat.get("kling_o3_video_path")
                or beat.get("kling_o3_video_path")
                or _bg_beat.get("accepted_video_path")
                or beat.get("accepted_video_path")
            )
            if not beat.get("accepted_image_key") and not video_path:
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
                "video_path": video_path or "",
                "bg_beat_id": beat.get("beat_id") or "",
                # Prefer BG sidecar trim state. The UI also sends these fields,
                # but sidecar is the durable source if the client payload is
                # stale or came from an older bundle.
                "kling_o3_trim_start": _bg_beat.get("kling_o3_trim_start", beat.get("kling_o3_trim_start")),
                "kling_o3_trim_back": _bg_beat.get("kling_o3_trim_back", beat.get("kling_o3_trim_back")),
                "kling_o3_trim_end": _bg_beat.get("kling_o3_trim_end", beat.get("kling_o3_trim_end")),
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
                clips_dir = h.app.event_dir / "animation_clips"
                clips_dir.mkdir(parents=True, exist_ok=True)
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
                    if fields.get("video_path"):
                        src = Path(fields["video_path"]).expanduser()
                        if src.is_file():
                            try:
                                from video_delivery import encode_delivery_video
                                bg_mod = _bg_module()
                            except Exception as _delivery_exc:
                                raise RuntimeError(f"video_delivery import failed: {_delivery_exc}") from _delivery_exc
                            bg_source = _bg_beat_map.get(fields.get("bg_beat_id") or "", {})
                            quality = bg_source.get("arlo_visual_quality") or {}
                            lipsync_quality = quality.get("lipsync_master_quality") or bg_source.get("kling_o3_voice_fix_lipsync_quality") or {}
                            min_dim = int(
                                lipsync_quality.get("delivery_min_dimension")
                                or lipsync_quality.get("min_dimension")
                                or 0
                            )
                            if min_dim and min_dim < 720:
                                raise RuntimeError(
                                    f"{fields.get('bg_beat_id')} kid-facing delivery is sub-720p "
                                    f"({lipsync_quality.get('delivery_width') or lipsync_quality.get('width')}"
                                    f"x{lipsync_quality.get('delivery_height') or lipsync_quality.get('height')}); "
                                    "regenerate before sending to Stitcher."
                                )
                            legacy_lipsync_master = quality.get("lipsync_master_video_path")
                            if not min_dim and legacy_lipsync_master and os.path.isfile(str(legacy_lipsync_master)):
                                _probe = subprocess.run(
                                    [
                                        "ffprobe", "-v", "error", "-select_streams", "v:0",
                                        "-show_entries", "stream=width,height", "-of", "json",
                                        str(legacy_lipsync_master),
                                    ],
                                    capture_output=True, text=True, timeout=30,
                                )
                                if _probe.returncode == 0:
                                    try:
                                        _stream = (json.loads(_probe.stdout).get("streams") or [{}])[0]
                                        _w = int(_stream.get("width") or 0)
                                        _h = int(_stream.get("height") or 0)
                                    except Exception:
                                        _w = _h = 0
                                    if _w and _h and min(_w, _h) < 720:
                                        raise RuntimeError(
                                            f"{fields.get('bg_beat_id')} lipsync master is sub-720p "
                                            f"({_w}x{_h}); regenerate before sending to Stitcher."
                                        )
                            trim_meta = {
                                "kling_o3_video_path": str(src),
                                "kling_o3_trim_start": fields.get("kling_o3_trim_start"),
                                "kling_o3_trim_back": fields.get("kling_o3_trim_back"),
                                "kling_o3_trim_end": fields.get("kling_o3_trim_end"),
                            }
                            if bg_mod.kling_o3_trim_is_active(trim_meta, video_path=src):
                                trim_src = clips_dir / f"{bid}_{src.stem}_trimmed_source.mp4"
                                src = bg_mod.materialize_kling_o3_trimmed_clip(trim_meta, trim_src, source_path=src)
                            if src.stem.endswith("_delivery"):
                                dst = clips_dir / f"{bid}_{src.name}"
                                if not dst.is_file() or src.stat().st_mtime > dst.stat().st_mtime:
                                    bg.copy_file_durable(src, dst)
                            else:
                                dst = clips_dir / f"{bid}_{src.stem}_delivery.mp4"
                                bg.copy_file_durable(src, dst)
                                encode_delivery_video(src, dst, include_audio=True, sharpen=True)
                            b["final"] = {
                                "source": "beat_generator_o3_video",
                                "file": dst.name,
                                "approved_at": datetime.now(timezone.utc).isoformat(),
                            }
                            b["lipsync"] = {
                                "status": "completed",
                                "file": dst.name,
                                "audio_processing": {"trim_start": 0.0},
                            }
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
        "pinned_video_role": (body or {}).get("scope_video_role") or (body or {}).get("scope_target_video"),
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
            def _stamp_rids(b: dict, _sc: dict) -> None:
                b["_task_rids"] = rids
                b["status"] = "stills_pending"

            bg.update_beat_locked(beat["beat_id"], _stamp_rids)
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
        "pinned_video_role": (body or {}).get("scope_video_role") or (body or {}).get("scope_target_video"),
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
    sidecar = bg._load_sidecar_migrated()

    beats_to_run = []
    for bid in beat_ids:
        _, beat = bg.find_beat(sidecar, bid)
        if beat:
            beats_to_run.append(dict(beat))  # snapshot — avoid lock contention in thread

    _GPT_JOBS[job_id] = {"status": "running", "results": {}, "total": len(beats_to_run) * 3}
    started_at = datetime.now(timezone.utc).isoformat()
    def _stamp_gpt_batch(sidecar: dict) -> None:
        for beat in beats_to_run:
            _, beat_obj = bg.find_beat(sidecar, beat["beat_id"])
            if beat_obj:
                beat_obj["bg_gpt_batch_job_id"] = job_id
                beat_obj["bg_gpt_batch_job_started_at"] = started_at
                beat_obj["status"] = "stills_pending"

    bg.mutate_sidecar_locked(_stamp_gpt_batch, migrate=True)

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
                if not h._check_event_pin(_pin, "bg_submit_gpt_batch_write_sidecar"):
                    print(f"[bg_submit_gpt_batch] event drift mid-thread; skipping sidecar write", flush=True)
                    return

                def _write_gpt(b: dict, _sc: dict) -> None:
                    b["gpt_options"] = results
                    b["status"] = "stills_ready"
                    b.pop("bg_gpt_batch_job_id", None)
                    b["bg_gpt_batch_job_completed_at"] = datetime.now(timezone.utc).isoformat()

                bg.update_beat_locked(bid, _write_gpt)
                _GPT_JOBS[job_id]["results"][bid] = results
            except Exception as e:
                print(f"[GPT] job {job_id} beat {bid} error: {e}")
                _GPT_JOBS[job_id]["results"][bid] = [{"error": str(e)}]
                if not h._check_event_pin(_pin, "bg_submit_gpt_batch_error_sidecar"):
                    print(f"[bg_submit_gpt_batch] event drift mid-thread; skipping error sidecar write", flush=True)
                    return

                def _write_gpt_err(b: dict, _sc: dict) -> None:
                    b["status"] = "stills_failed"
                    b["gpt_error"] = str(e)[-1000:]
                    b.pop("bg_gpt_batch_job_id", None)
                    b["bg_gpt_batch_job_completed_at"] = datetime.now(timezone.utc).isoformat()

                bg.update_beat_locked(bid, _write_gpt_err)

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


_O3_SUBMIT_REATTACH_TERMINAL_FAILURES = frozenset({
    "approved", "failed", "failed_o3", "failed_provider_fetch", "failed_provider_sub720",
})


def _o3_submit_reattach_response_if_running(h, beat_id: str, beat: dict, event_dir: Path) -> bool:
    """If an O3 job is already live for this beat, respond 200 deduped (reattach UI)."""
    from o3_generation_intent import (
        intent_event_dir_for_beat,
        load_generation_intent,
        submitted_audit_from_intent,
    )
    from o3_job_status_contract import beat_job_busy

    bid = str(beat_id or "").strip()
    if not bid or not beat:
        return False
    busy = beat_job_busy(beat, event_dir)
    existing_job_id = str(
        beat.get("o3_current_job_id")
        or beat.get("kling_o3_voice_fix_ui_job_id")
        or "",
    ).strip()
    if not existing_job_id:
        return False
    existing_status = str(beat.get("kling_o3_voice_fix_status") or "")
    if existing_status in _O3_SUBMIT_REATTACH_TERMINAL_FAILURES:
        return False
    existing_job = _ARLO_O3_JOBS.get(existing_job_id)
    existing_proc = existing_job.get("proc") if existing_job else None
    pid_running = beat.get("kling_o3_voice_fix_job_pid") is not None and _pid_is_running(
        int(beat.get("kling_o3_voice_fix_job_pid") or 0),
    )
    proc_running = (
        existing_proc
        and existing_job.get("status") == "running"
        and existing_proc.poll() is None
    )
    if not busy and not proc_running and not pid_running:
        return False
    dedup_submitted: dict = {}
    dedup_intent: dict | None = None
    try:
        intent_event_d = intent_event_dir_for_beat(bid, event_dir)
        intent_file = intent_event_d / "arlo_o3_jobs" / f"{existing_job_id}_intent.json"
        if intent_file.is_file():
            dedup_intent = load_generation_intent(intent_file)
            dedup_submitted = submitted_audit_from_intent(dedup_intent)
    except Exception:
        pass
    h._send_json(200, {
        "ok": True,
        "job_id": existing_job_id,
        "beat_id": bid,
        "log_path": beat.get("kling_o3_voice_fix_job_log_path"),
        "deduped": True,
        "submitted": dedup_submitted,
        "intent": dedup_intent,
        "message": "O3 voice generation is already running for this beat.",
    })
    return True


def handle_bg_submit_arlo_o3_voice(h, body: dict) -> None:
    """POST /api/bg/submit-arlo-o3-voice {beat_id}.

    Routes by ``resolve_o3_generate_mode``:
    - ``avatar_pro``: ElevenLabs TTS + Avatar Pro → 720 delivery (default speak beats)
    - ``voice_first``: ElevenLabs TTS + silent O3 + lipsync → 720 delivery (env rollback)
    - ``element_native``: O3 Pro Element + native audio (env rollback)
    """
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
    job_id = str(_stdlib_uuid.uuid4())[:8]
    attempt_id = _stdlib_uuid.uuid4().hex
    prod = _data_root(h)
    script: Path | None = None
    o3_generate_mode = "element_native"
    # Ref snapshot durability: POST body carries the operator ref box at Generate
    # click. build_generation_intent resolves char/bg via resolve_o3_submit_refs
    # (ref box wins over sidecar when both differ).
    event_dir = _o3_job_event_dir(h, str(beat_id))
    log_path = event_dir / "arlo_o3_jobs" / f"{job_id}_{beat_id}.log"
    started_at = datetime.now(timezone.utc).isoformat()
    bg = _bg_module()
    intent_path: Path | None = None
    committed_intent: dict | None = None
    submit_creds: dict | None = None
    try:
        from o3_generation_intent import (
            IntentCommitError,
            build_generation_intent,
            intent_event_dir_for_beat,
            sidecar_fields_from_intent,
            submitted_audit_from_intent,
            write_generation_intent,
        )

        sidecar_snap = bg.read_sidecar_for_poll_snapshot(lock_timeout_s=5.0)
        bg.ensure_sidecar_schema_defaults(sidecar_snap)
        _, beat_snap = bg.find_beat(sidecar_snap, str(beat_id))
        if not beat_snap:
            return h._send_error_v59(
                404,
                error_code="BEAT_NOT_FOUND",
                error_message=f"beat {beat_id} not found",
                retry_safe=False,
            )
        work_beat = copy.deepcopy(beat_snap)
        generation_mode = bg.resolve_beat_generation_mode(work_beat, sidecar_snap)
        if generation_mode == bg.PIPELINE_MODE_STILL:
            return h._send_error_v59(
                400,
                error_code="STILL_INSERT_BEAT",
                error_message=(
                    "O3 voice submit does not apply to still_insert beats — "
                    "use render-still-clip."
                ),
                retry_safe=False,
            )
        body_mode = str(
            body.get("generation_mode") or body.get("o3_generate_mode") or "",
        ).strip().lower()
        if body_mode in (
            bg.O3_GENERATE_MODE_VOICE_FIRST,
            bg.O3_GENERATE_MODE_ELEMENT_NATIVE,
            bg.O3_GENERATE_MODE_AVATAR,
        ):
            work_beat["o3_generate_mode"] = body_mode
        generation_mode = bg.resolve_beat_generation_mode(work_beat, sidecar_snap)
        ok_prompt, prompt_code, prompt_msg = bg.validate_o3_submit_prompt_for_mode(
            str(body.get("kling_o3_prompt") or ""),
            generation_mode,
        )
        if not ok_prompt:
            return h._send_error_v59(
                400,
                error_code=prompt_code,
                error_message=prompt_msg,
                retry_safe=False,
            )
        if _o3_submit_reattach_response_if_running(h, str(beat_id), beat_snap, event_dir):
            return
        o3_generate_mode = generation_mode
        if o3_generate_mode == bg.O3_GENERATE_MODE_AVATAR and bg.beatgen_avatar_pro_disabled():
            return h._send_error_v59(
                400,
                error_code="BEATGEN_AVATAR_DISABLED",
                error_message=(
                    "Beat Gen Avatar Pro is disabled — server is pinned to Kling Element native O3."
                ),
                retry_safe=False,
            )
        work_beat["o3_generate_mode"] = o3_generate_mode
        work_beat["kling_o3_generate_mode"] = o3_generate_mode
        if o3_generate_mode == bg.O3_GENERATE_MODE_VOICE_FIRST:
            script = _PSERVER_TOOLS_DIR / "arlo_o3_voice_pipeline.py"
            if not script.is_file():
                script = prod / "tools" / "arlo_o3_voice_pipeline.py"
        elif o3_generate_mode == bg.O3_GENERATE_MODE_AVATAR:
            script = _PSERVER_TOOLS_DIR / "arlo_avatar_beat_pipeline.py"
            if not script.is_file():
                script = prod / "tools" / "arlo_avatar_beat_pipeline.py"
        else:
            script = _PSERVER_TOOLS_DIR / "kling_o3_element_beat_pipeline.py"
            if not script.is_file():
                script = prod / "tools" / "kling_o3_element_beat_pipeline.py"
        if not script or not script.is_file():
            return h._send_error_v59(
                500,
                error_code="O3_PIPELINE_MISSING",
                error_message=f"O3 pipeline script missing for mode={o3_generate_mode}: {script}",
                retry_safe=False,
            )
        try:
            from credentials import load_credentials  # type: ignore
        except ImportError:
            from tools.credentials_lib.credentials import load_credentials  # type: ignore
        creds = load_credentials()
        submit_creds = creds
        if o3_generate_mode == "voice_first":
            from lipsync_public_host import (
                lipsync_public_host_block_message,
                lipsync_public_host_ready,
            )

            if not lipsync_public_host_ready(creds=creds):
                return h._send_error_v59(
                    503,
                    error_code="LIPSYNC_HOSTING_NOT_CONFIGURED",
                    error_message=lipsync_public_host_block_message(),
                    retry_safe=False,
                )
        ws_key = creds.get("wavespeed_key") or creds.get("wavespeed")
        # WaveSpeed / Element registration — never under sidecar_file_lock.
        committed_intent = build_generation_intent(
            beat=work_beat,
            sidecar=sidecar_snap,
            body=body,
            beat_id=str(beat_id),
            event_dir=event_dir,
            job_id=job_id,
            attempt_id=attempt_id,
            log_path=log_path,
            pipeline_script=script,
            wavespeed_key=ws_key,
        )
        if getattr(h.app, "scope_type", "event") == "milestone" and getattr(h.app, "milestone_dir", None):
            mdir = Path(h.app.milestone_dir).expanduser().resolve()
            lib = getattr(h.app, "milestone_library_event_dir", None) or h.app.event_dir
            scope_payload: dict = {
                "scope_type": "milestone",
                "milestone_id": str(getattr(h.app, "active_milestone_id", "") or ""),
                "milestone_dir": str(mdir),
                "library_event_dir": str(Path(lib).expanduser().resolve()),
            }
            try:
                from lib.milestone_store import load_milestone_state, resolve_milestone_skeleton_ref

                skel = resolve_milestone_skeleton_ref(
                    load_milestone_state(mdir),
                    str(getattr(h.app, "active_milestone_id", "") or ""),
                )
                if skel:
                    scope_payload["skeleton_ref"] = skel
            except Exception:
                pass
            committed_intent["runtime_scope"] = scope_payload
        intent_event = intent_event_dir_for_beat(str(beat_id), event_dir)
        intent_path = intent_event / "arlo_o3_jobs" / f"{job_id}_intent.json"

        def _commit_o3(b: dict, sidecar: dict) -> None:
            bg.ensure_sidecar_schema_defaults(sidecar)
            existing_job_id = str(b.get("kling_o3_voice_fix_ui_job_id") or "")
            existing_status = str(b.get("kling_o3_voice_fix_status") or "")
            if existing_job_id and existing_status not in {
                "approved", "failed", "failed_o3", "failed_provider_fetch", "failed_provider_sub720",
            }:
                b.pop("kling_o3_voice_fix_ui_job_id", None)
            b.update(sidecar_fields_from_intent(committed_intent))
            bg.stamp_o3_prompt_box_law(
                b,
                str((committed_intent.get("prompt") or {}).get("verbatim") or ""),
            )
            bg.sync_beat_dialogue_from_kling_prompt(b)
            b["status"] = "o3_voice_job_starting"
            b["kling_o3_voice_fix_status"] = "job_starting"
            b["kling_o3_voice_fix_phase"] = "queued"
            b["kling_o3_voice_fix_attempt_id"] = attempt_id
            b["kling_o3_voice_fix_ui_job_id"] = job_id
            b["kling_o3_voice_fix_job_log_path"] = str(log_path)
            b["kling_o3_voice_fix_job_started_at"] = started_at
            b["kling_o3_voice_fix_updated_at"] = started_at
            b.pop("kling_o3_voice_fix_error", None)
            b.pop("kling_o3_voice_fix_error_code", None)
            b.pop("kling_o3_voice_fix_job_completed_at", None)

        ok, _ = bg.update_beat_locked(str(beat_id), _commit_o3)
        if not ok:
            return h._send_error_v59(
                404,
                error_code="BEAT_NOT_FOUND",
                error_message=f"beat {beat_id} not found",
                retry_safe=False,
            )
        intent_path = write_generation_intent(committed_intent, event_dir)
        from o3_generation_intent import (
            intent_event_dir_for_beat as _intent_ev_dir,
            write_running_terminal_at_submit,
        )

        write_running_terminal_at_submit(
            job_id,
            _intent_ev_dir(str(beat_id), event_dir),
            intent_id=str((committed_intent or {}).get("intent_id") or ""),
            beat_id=str(beat_id),
        )
    except TimeoutError as exc:
        return h._send_error_v59(
            503,
            error_code="SIDECAR_LOCK_TIMEOUT",
            error_message=str(exc) or "sidecar lock busy — retry shortly",
            retry_safe=True,
        )
    except IntentCommitError as exc:
        if exc.error_code == "BEAT_JOB_BUSY":
            try:
                sidecar_retry = bg.read_sidecar_for_poll_snapshot(lock_timeout_s=2.0)
                _, beat_retry = bg.find_beat(sidecar_retry, str(beat_id))
                if beat_retry and _o3_submit_reattach_response_if_running(
                    h, str(beat_id), beat_retry, event_dir,
                ):
                    return
            except Exception:
                pass
        return h._send_error_v59(
            exc.http_status,
            error_code=exc.error_code,
            error_message=exc.error_message,
            retry_safe=exc.retry_safe,
            extra={"detail": exc.detail} if exc.detail else None,
        )
    except Exception as exc:
        if isinstance(exc, (BrokenPipeError, ConnectionResetError)):
            raise
        return h._send_error_v59(
            500,
            error_code="O3_INTENT_COMMIT_FAILED",
            error_message=f"Could not commit generation intent: {exc}",
            retry_safe=True,
        )
    cmd = [
        sys.executable, "-u", str(script),
        "--beat-id", str(beat_id),
        "--attempt-id", attempt_id,
    ]
    if body.get("no_sharpen"):
        cmd.append("--no-sharpen")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_fh = open(log_path, "w", encoding="utf-8")
    subprocess_env = os.environ.copy()
    subprocess_env["MN_PROD_ROOT"] = str(prod)
    subprocess_env["MN_O3_ATTEMPT_ID"] = attempt_id
    subprocess_env["MN_O3_JOB_LOG"] = str(log_path)
    if intent_path:
        subprocess_env["MN_O3_INTENT_PATH"] = str(intent_path)
    if body.get("accept_voice_drift"):
        subprocess_env["MN_ACCEPT_VOICE_DRIFT"] = "1"
    subprocess_env["MN_TOOLING_TOOLS"] = str(_PSERVER_TOOLS_DIR)
    if o3_generate_mode == "voice_first":
        subprocess_env["MN_LIPSYNC_STAGING_EVENT_DIR"] = str(event_dir)
        subprocess_env["MN_LIPSYNC_STAGING_TOKEN"] = attempt_id
        public_base = os.environ.get("MN_LIPSYNC_PUBLIC_BASE_URL", "").strip()
        if not public_base:
            event_name = event_dir.name
            if event_name.startswith("Event_"):
                try:
                    port = 5110 + int(event_name.replace("Event_", ""))
                    public_base = f"http://localhost:{port}"
                except ValueError:
                    public_base = ""
        if public_base:
            try:
                from lipsync_staging import is_public_staging_base
            except ImportError:
                is_public_staging_base = lambda _base: True  # noqa: E731
            if is_public_staging_base(public_base):
                subprocess_env["MN_LIPSYNC_STAGING_PUBLIC_BASE"] = public_base.rstrip("/")
            else:
                print(
                    f"[bg_o3] voice_first: skip localhost staging base {public_base!r}; "
                    "lipsync will use R2/ephemeral public hosts",
                    flush=True,
                )
        from lipsync_public_host import inject_lipsync_r2_env

        inject_lipsync_r2_env(subprocess_env, submit_creds)
    _pp = subprocess_env.get("PYTHONPATH", "")
    subprocess_env["PYTHONPATH"] = os.pathsep.join(
        p for p in (str(_PSERVER_TOOLS_DIR), str(prod / "tools"), str(prod), _pp) if p
    )
    from o3_subprocess_bootstrap import inject_o3_subprocess_scope_env

    inject_o3_subprocess_scope_env(subprocess_env, h.app)
    proc = subprocess.Popen(
        cmd,
        cwd=str(prod),
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
        env=subprocess_env,
    )
    _ARLO_O3_JOBS[job_id] = {
        "status": "running",
        "beat_id": str(beat_id),
        "pid": proc.pid,
        "proc": proc,
        "log_path": str(log_path),
        "started_at": started_at,
        "attempt_id": attempt_id,
        "intent_id": (committed_intent or {}).get("intent_id"),
        "intent_path": str(intent_path) if intent_path else None,
        "result": None,
        "error": None,
    }
    try:
        from o3_generation_intent import (
            intent_event_dir_for_beat as _spawn_ev_dir,
            touch_o3_job_heartbeat,
            write_o3_job_pid,
        )

        spawn_ev = _spawn_ev_dir(str(beat_id), event_dir)
        write_o3_job_pid(job_id, spawn_ev, proc.pid)
        touch_o3_job_heartbeat(job_id, spawn_ev)
    except Exception as exc:
        print(f"[bg_o3_job] warning: could not write pid/heartbeat for {job_id}: {exc}", flush=True)
    try:
        def _stamp_running_job(b: dict, _sidecar: dict) -> None:
            if str(b.get("beat_id") or "") != str(beat_id):
                return
            if b.get("kling_o3_voice_fix_attempt_id") not in (None, attempt_id):
                return
            b["status"] = "o3_voice_job_running"
            b["kling_o3_voice_fix_status"] = "job_running"
            b["kling_o3_voice_fix_phase"] = "subprocess"
            b["kling_o3_voice_fix_attempt_id"] = attempt_id
            b["kling_o3_voice_fix_ui_job_id"] = job_id
            b["kling_o3_voice_fix_job_log_path"] = str(log_path)
            b["kling_o3_voice_fix_job_started_at"] = started_at
            b["kling_o3_voice_fix_job_pid"] = proc.pid
            b["kling_o3_voice_fix_updated_at"] = datetime.now(timezone.utc).isoformat()
            b.pop("kling_o3_voice_fix_error", None)
            b.pop("kling_o3_voice_fix_error_code", None)
            b.pop("kling_o3_voice_fix_job_completed_at", None)

        ok, _ = bg.update_beat_locked(
            str(beat_id),
            _stamp_running_job,
            expected_attempt_id=attempt_id,
        )
        if not ok:
            print(f"[bg_o3_job] warning: could not persist running job metadata for {beat_id}", flush=True)
    except Exception as exc:
        print(f"[bg_o3_job] warning: could not persist job metadata for {beat_id}: {exc}", flush=True)
    submitted = submitted_audit_from_intent(committed_intent) if committed_intent else {}
    return h._send_json(200, {
        "ok": True,
        "job_id": job_id,
        "beat_id": beat_id,
        "log_path": str(log_path),
        "attempt_id": attempt_id,
        "intent_id": (committed_intent or {}).get("intent_id"),
        "o3_generate_mode": o3_generate_mode,
        "pipeline_script": str(script),
        "generation_slot": submitted.get("generation_slot"),
        "submitted": submitted,
        "intent": committed_intent,
    })


def _event_dir_for_beat_id(beat_id: str) -> Path:
    """Derive Production/Event_N from bg_arc1_event2_pre_beat_27 style ids."""
    return _bg_module().event_dir_for_beat_id(beat_id)


_event_dir_from_beat_id = _event_dir_for_beat_id


def _enriched_beat_snapshot_for_o3_poll(
    beat_id: str,
    event_dir: Path,
    *,
    migrate: bool = False,
) -> dict | None:
    """Single-beat API payload — avoids full session-state migrate on O3 poll done."""
    bg = _bg_module()
    try:
        sidecar = bg.read_sidecar_for_poll_snapshot(lock_timeout_s=5.0)
    except Exception as exc:
        print(f"[bg_o3_poll] sidecar read failed for {beat_id}: {exc}", flush=True)
        return None
    if migrate:
        sidecar = bg._migrate_sidecar(sidecar, heal_trim=False, heavy_heal=False)
    else:
        bg.ensure_sidecar_schema_defaults(sidecar)
    _, beat = bg.find_beat(sidecar, str(beat_id))
    if not beat:
        return None
    try:
        from o3_job_truth import resolve_beat_o3_truth

        truth = resolve_beat_o3_truth(
            str(beat_id),
            event_dir,
            dict(beat),
            sidecar=sidecar,
            orphan_recovery=_try_orphan_o3_delivery_recovery,
        )
        beat_work = truth.get("reconciled_beat") or dict(beat)
        _truth_keys = (
            "status",
            "kling_o3_status",
            "kling_o3_voice_fix_status",
            "kling_o3_video_path",
            "kling_o3_generation",
            "kling_o3_options",
        )
        if any(beat.get(k) != beat_work.get(k) for k in _truth_keys):
            def _commit(sc: dict) -> None:
                bg.ensure_sidecar_schema_defaults(sc)
                _, live = bg.find_beat(sc, str(beat_id))
                if live:
                    live.update({k: beat_work[k] for k in _truth_keys if k in beat_work})

            try:
                bg.mutate_sidecar_locked(_commit, timeout_s=5)
                sidecar = bg.read_sidecar_for_poll_snapshot(lock_timeout_s=5.0)
                _, beat = bg.find_beat(sidecar, str(beat_id))
            except Exception as exc:
                print(f"[bg_o3_poll] truth persist skipped for {beat_id}: {exc}", flush=True)
                beat = beat_work
    except Exception as exc:
        print(f"[bg_o3_poll] truth reconcile failed for {beat_id}: {exc}", flush=True)
    snap = bg.enrich_beat_kling_o3_pinned(dict(beat), event_dir)
    from o3_job_status_contract import clear_o3_pointer_if_terminal

    clear_o3_pointer_if_terminal(snap, event_dir)
    try:
        slots = bg.build_fixed_o3_ui_slots(snap, sidecar=sidecar)
        snap["kling_o3_ui_slots"] = [
            dict(s) if isinstance(s, dict) else None for s in slots
        ]
    except Exception:
        pass
    try:
        from operator_workbench_contract import enrich_beat_operator_derived

        event_id_h, phase_h = bg.segment_event_phase_for_beat(sidecar, str(beat_id)) or ("", "full")
        snap["_derived"] = enrich_beat_operator_derived(
            snap,
            sidecar,
            event_id=str(event_id_h or ""),
            phase=str(phase_h or "full"),
            approved_roots=None,
        )
        derived = snap["_derived"]
        if derived.get("element_char_ref_ok") is not None:
            snap["element_char_ref_ok"] = derived["element_char_ref_ok"]
        if derived.get("element_char_ref_error"):
            snap["element_char_ref_error"] = derived["element_char_ref_error"]
    except Exception as exc:
        print(f"[bg_o3_poll] operator derived enrich failed for {beat_id}: {exc}", flush=True)
    from o3_job_status_contract import beat_job_busy

    beat_event_dirs = bg.resolve_o3_lifecycle_event_dir_candidates(
        str(beat_id), server_event_dir=event_dir,
    )
    try:
        snap["job_busy"] = _resolve_beat_job_busy_for_session(snap, beat_event_dirs)
    except Exception as exc:
        print(f"[bg_o3_poll] job_busy resolve failed for {beat_id}: {exc}", flush=True)
        snap["job_busy"] = False
        snap["o3_current_job_id"] = None
    else:
        from o3_job_status_contract import resolve_o3_current_job_id

        snap["o3_current_job_id"] = resolve_o3_current_job_id(snap) if snap["job_busy"] else None
    return snap


def _minimal_sidecar_beat_for_o3_poll(beat_id: str, event_dir: Path) -> dict | None:
    """Lightweight beat row when full disk enrich fails — keeps poll/select from going beat-less."""
    bg = _bg_module()
    try:
        sidecar = bg.read_sidecar_for_poll_snapshot(lock_timeout_s=5.0)
    except Exception as exc:
        print(f"[bg_o3_poll] minimal sidecar read failed for {beat_id}: {exc}", flush=True)
        return None
    bg.ensure_sidecar_schema_defaults(sidecar)
    _, beat = bg.find_beat(sidecar, str(beat_id))
    if not beat:
        return None
    snap = {k: v for k, v in dict(beat).items() if not str(k).startswith("_")}
    beat_event_dirs = bg.resolve_o3_lifecycle_event_dir_candidates(
        str(beat_id), server_event_dir=event_dir,
    )
    try:
        snap["job_busy"] = _resolve_beat_job_busy_for_session(snap, beat_event_dirs)
    except Exception as exc:
        print(f"[bg_o3_poll] minimal job_busy failed for {beat_id}: {exc}", flush=True)
        snap["job_busy"] = False
    from o3_job_status_contract import resolve_o3_current_job_id

    snap["o3_current_job_id"] = resolve_o3_current_job_id(snap) if snap.get("job_busy") else None
    return snap


def _o3_poll_payload_with_beat_snapshot(payload: dict, event_dir: Path) -> dict:
    """Attach enriched sidecar beat on O3 poll so UI shows running state + terminal clip."""
    payload = _enrich_o3_poll_with_intent(payload, event_dir)
    if payload.get("status") not in ("running", "done", "failed", "done_with_warning"):
        return payload
    beat_id = str(payload.get("beat_id") or "").strip()
    if not beat_id:
        return payload
    try:
        snap = _enriched_beat_snapshot_for_o3_poll(beat_id, event_dir, migrate=False)
    except Exception as exc:
        print(f"[bg_o3_poll] beat snapshot failed for {beat_id}: {exc}", flush=True)
        snap = _minimal_sidecar_beat_for_o3_poll(beat_id, event_dir)
    if not snap:
        return payload
    out = dict(payload)
    out["beat"] = snap
    return out


def _enrich_o3_poll_with_intent(payload: dict, event_dir: Path) -> dict:
    from o3_generation_intent import (
        intent_path_for_job,
        intent_poll_subset,
        load_generation_intent,
        load_intent_terminal,
        terminal_path_for_job,
    )

    job_id = str(payload.get("job_id") or "").strip()
    if not job_id:
        return payload
    out = dict(payload)
    intent_path = intent_path_for_job(job_id, event_dir)
    if intent_path.is_file():
        try:
            intent = load_generation_intent(intent_path)
            out["intent"] = intent_poll_subset(intent)
        except (OSError, json.JSONDecodeError, ValueError):
            pass
    terminal_path = terminal_path_for_job(job_id, event_dir)
    terminal = load_intent_terminal(terminal_path)
    if terminal:
        out["terminal"] = terminal
        status = str(terminal.get("status") or "").strip()
        if status == "done_with_warning":
            out["status"] = "done_with_warning"
            out["warning"] = terminal.get("warning")
        elif status in ("done", "failed"):
            out["status"] = status
        elif status == "cancelled":
            out["status"] = "cancelled"
    return out


def _finalize_o3_job_after_subprocess_exit(job: dict, event_dir: Path) -> None:
    """Mark in-memory O3 job done/failed; recover delivery mp4 when sidecar persist failed."""
    from o3_generation_intent import load_intent_terminal, terminal_path_for_job, write_intent_terminal

    proc = job.get("proc")
    if not proc or job.get("status") != "running":
        return
    rc = proc.poll()
    if rc is None:
        return
    job_id = str(job.get("job_id") or "")
    if not job_id:
        for key, row in _ARLO_O3_JOBS.items():
            if row is job:
                job_id = key
                break
    job["ended_at"] = datetime.now(timezone.utc).isoformat()
    job["exit_code"] = rc
    log_path = job.get("log_path")
    beat_id = str(job.get("beat_id") or "")
    log_text = ""
    if log_path and Path(str(log_path)).is_file():
        log_text = Path(str(log_path)).read_text(encoding="utf-8", errors="replace")
    terminal_path = terminal_path_for_job(job_id, event_dir) if job_id else None
    terminal = load_intent_terminal(terminal_path) if terminal_path else None
    if terminal and str(terminal.get("status") or "") in {"done", "failed", "done_with_warning", "cancelled"}:
        job["status"] = str(terminal.get("status"))
        if terminal.get("status") == "failed":
            job["error"] = (terminal.get("failure") or {}).get("message") or "O3 job failed"
        else:
            job["result"] = {
                "ok": True,
                "beat_id": beat_id,
                "video": (terminal.get("delivered") or {}).get("video_path"),
                "terminal": True,
            }
            if terminal.get("status") == "done_with_warning":
                job["warning"] = terminal.get("warning")
        return
    if rc == 0:
        job["status"] = "done"
        job["result"] = _parse_o3_pipeline_result_from_log(log_path)
        return
    from o3_job_status_contract import voice_fix_is_terminal_failure

    voice_fix, voice_err = _sidecar_voice_fix_for_beat(beat_id)
    if voice_fix_is_terminal_failure(voice_fix):
        job["status"] = "failed"
        job["error"] = _summarize_o3_job_error(voice_err or log_text[-4000:])
        if job_id and event_dir:
            try:
                write_intent_terminal(job_id, event_dir, {
                    "status": "failed",
                    "phase_last": "subprocess_voice_fix_terminal",
                    "sidecar_persist_ok": True,
                    "failure": {"message": job["error"]},
                })
            except OSError:
                pass
        return
    recovered = None
    if beat_id and (
        _sidecar_io_error_text(log_text)
        or _parse_o3_pipeline_result_from_log(log_path)
    ):
        recovered = _try_orphan_o3_delivery_recovery(beat_id, event_dir, log_path)
    if recovered:
        job["status"] = "done"
        job["result"] = {
            "ok": True,
            "beat_id": beat_id,
            "video": recovered.get("delivery_path"),
            "recovered_from_sidecar_io_error": True,
        }
        if job_id:
            try:
                write_intent_terminal(job_id, event_dir, {
                    "status": "done",
                    "sidecar_persist_ok": True,
                    "delivered": {"video_path": recovered.get("delivery_path")},
                })
            except OSError:
                pass
        job.pop("error", None)
        return
    job["status"] = "failed"
    job["error"] = _summarize_o3_job_error(log_text[-4000:])
    if job_id and event_dir:
        try:
            write_intent_terminal(job_id, event_dir, {
                "status": "failed",
                "phase_last": "subprocess_exit",
                "sidecar_persist_ok": bool(voice_fix_is_terminal_failure(voice_fix)),
                "failure": {"message": job["error"]},
            })
        except OSError:
            pass


def handle_bg_poll_arlo_o3_voice_status(h) -> None:
    """GET /api/bg/poll-arlo-o3-voice-status?job_id=..."""
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(h.path).query)
    job_id = (qs.get("job_id") or [""])[0]
    if not job_id or job_id not in _ARLO_O3_JOBS:
        event_dir = Path(h.app.event_dir)
        if not event_dir.is_absolute():
            event_dir = _data_root(h) / event_dir
        recovered = _recover_o3_job_from_intent_terminal(job_id, event_dir)
        if not recovered:
            recovered = _recover_o3_job_from_sidecar(job_id)
        if recovered:
            event_dir = Path(h.app.event_dir)
            if not event_dir.is_absolute():
                event_dir = _data_root(h) / event_dir
            try:
                body = _o3_poll_payload_with_beat_snapshot(recovered, event_dir)
            except TimeoutError as exc:
                print(f"[bg_o3_poll] recovered job snapshot lock timeout for {job_id}: {exc}", flush=True)
                body = recovered
            return h._send_json(200, body)
        return h._send_error_v59(
            404,
            error_code="ARLO_JOB_NOT_FOUND",
            error_message=(
                f"O3 job {job_id} is not in server memory (likely after restart). "
                "Refresh Beat Gen — sidecar will rehydrate active jobs."
            ),
            retry_safe=True,
        )
    job = _ARLO_O3_JOBS[job_id]
    event_dir = Path(h.app.event_dir)
    if not event_dir.is_absolute():
        event_dir = _data_root(h) / event_dir
    if job.get("status") == "running":
        _ensure_o3_job_metadata(job_id, job)
        proc = job.get("proc")
        pid = job.get("pid")
        pid_gone = pid is not None and not _pid_is_running(int(pid))
        if proc is not None and not pid_gone:
            _finalize_o3_job_after_subprocess_exit(job, event_dir)
        elif pid_gone or proc is None:
            _promote_o3_job_from_log_if_terminal(job, event_dir)
        if job.get("status") in ("done", "failed", "done_with_warning"):
            _clear_o3_job_metadata(
                job_id,
                status=job["status"],
                result=job.get("result"),
                error=job.get("error"),
            )
        elif job.get("status") == "running":
            beat_id = str(job.get("beat_id") or "")
            log_path = job.get("log_path")
            if beat_id and log_path:
                from o3_generation_intent import load_intent_terminal, terminal_path_for_job

                terminal = load_intent_terminal(terminal_path_for_job(str(job_id), event_dir))
                terminal_done = str((terminal or {}).get("status") or "") in (
                    "done",
                    "done_with_warning",
                    "failed",
                )
                log_tail = _tail_read_text(log_path)
                if (
                    terminal_done
                    or '"phase": "done"' in log_tail
                    or _parse_o3_pipeline_result_from_log(log_path, tail_bytes=_O3_LOG_TAIL_BYTES)
                ):
                    if _promote_o3_job_from_log_if_terminal(job, event_dir):
                        _clear_o3_job_metadata(
                            job_id,
                            status=job["status"],
                            result=job.get("result"),
                            error=job.get("error"),
                        )
    payload = {k: v for k, v in job.items() if k != "proc"}
    payload = _enrich_o3_poll_with_intent(payload, event_dir)
    try:
        payload = _o3_poll_payload_with_beat_snapshot(payload, event_dir)
    except TimeoutError as exc:
        print(f"[bg_o3_poll] beat snapshot lock timeout for {job_id}: {exc}", flush=True)
    return h._send_json(200, payload)


def handle_bg_submit_kling_native_lipsync_experiment(h, body: dict) -> None:
    """POST /api/bg/submit-kling-native-lipsync-experiment {beat_id, route}.

    This launches an isolated proof job only. It never approves, selects, or
    promotes a clip.
    """
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return
    beat_id = str(body.get("beat_id") or "").strip()
    route = str(body.get("route") or "native_kling_identify_face_advanced_lipsync").strip()
    if not beat_id:
        return h._send_error_v59(
            400,
            error_code="MISSING_BEAT_ID",
            error_message="beat_id required",
            retry_safe=False,
        )
    if not route:
        return h._send_error_v59(
            400,
            error_code="MISSING_ROUTE",
            error_message="route required",
            retry_safe=False,
        )
    prod = _data_root(h)
    script = prod / "tools" / "kling_native_lipsync_experiment.py"
    attempt_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + _stdlib_uuid.uuid4().hex[:8]
    job_id = "native_lipsync_" + attempt_id
    started_at = datetime.now(timezone.utc).isoformat()
    event_dir = Path(h.app.event_dir)
    output_dir = event_dir / "kling_native_lipsync_experiments" / beat_id / attempt_id
    log_path = output_dir / "run.log"
    manifest_path = output_dir / "manifest.json"

    try:
        bg = _bg_module()
        sidecar_probe = bg.read_sidecar()
        sidecar_probe = bg._migrate_sidecar(sidecar_probe)
        _, beat_probe = bg.find_beat(sidecar_probe, beat_id)
        if not beat_probe:
            return h._send_error_v59(
                404,
                error_code="BEAT_NOT_FOUND",
                error_message=f"beat {beat_id} not found",
                retry_safe=False,
            )
        o3_job_id = str(beat_probe.get("kling_o3_voice_fix_ui_job_id") or "")
        o3_status = str(beat_probe.get("kling_o3_voice_fix_status") or "").lower()
        if o3_job_id and o3_status not in {"approved", "failed", "failed_o3", "failed_provider_fetch", "failed_provider_sub720"}:
            existing_o3 = _ARLO_O3_JOBS.get(o3_job_id)
            existing_proc = existing_o3.get("proc") if existing_o3 else None
            if existing_proc and existing_o3.get("status") == "running" and existing_proc.poll() is None:
                return h._send_error_v59(
                    409,
                    error_code="O3_JOB_RUNNING",
                    error_message="Cannot test native lipsync while O3 voice generation is running for this beat.",
                    retry_safe=True,
                )
        existing_job_id = str(beat_probe.get("kling_native_lipsync_experiment_ui_job_id") or "")
        existing_status = str(beat_probe.get("kling_native_lipsync_experiment_status") or "").lower()
        if existing_job_id and existing_status == "running":
            existing = _NATIVE_LIPSYNC_JOBS.get(existing_job_id)
            existing_proc = existing.get("proc") if existing else None
            if existing_proc and existing_proc.poll() is None:
                return h._send_json(200, {
                    "ok": True,
                    "job_id": existing_job_id,
                    "beat_id": beat_id,
                    "route": route,
                    "deduped": True,
                    "log_path": beat_probe.get("kling_native_lipsync_experiment_log_path"),
                    "message": "Native Kling LipSync experiment is already running for this beat.",
                })

        def _stamp_native(b: dict, _sc: dict) -> None:
            b["kling_native_lipsync_experiment_status"] = "running"
            b["kling_native_lipsync_experiment_route"] = route
            b["kling_native_lipsync_experiment_attempt_id"] = attempt_id
            b["kling_native_lipsync_experiment_started_at"] = started_at
            b["kling_native_lipsync_experiment_ui_job_id"] = job_id
            b["kling_native_lipsync_experiment_log_path"] = str(log_path)
            b.pop("kling_native_lipsync_experiment_error", None)
            b.pop("kling_native_lipsync_experiment_error_code", None)

        ok, _ = bg.update_beat_locked(beat_id, _stamp_native)
        if not ok:
            return h._send_error_v59(
                404,
                error_code="BEAT_NOT_FOUND",
                error_message=f"beat {beat_id} not found",
                retry_safe=False,
            )
    except Exception as exc:
        if isinstance(exc, (BrokenPipeError, ConnectionResetError)):
            raise
        return h._send_error_v59(
            500,
            error_code="NATIVE_LIPSYNC_METADATA_FAILED",
            error_message=f"Could not persist experiment metadata: {exc}",
            retry_safe=True,
        )

    cmd = [
        sys.executable, "-u", str(script),
        "--beat-id", beat_id,
        "--route", route,
        "--attempt-id", attempt_id,
    ]
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_fh = open(log_path, "w", encoding="utf-8")
    proc = subprocess.Popen(
        cmd,
        cwd=str(prod),
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    _NATIVE_LIPSYNC_JOBS[job_id] = {
        "status": "running",
        "beat_id": beat_id,
        "route": route,
        "pid": proc.pid,
        "proc": proc,
        "log_path": str(log_path),
        "manifest_path": str(manifest_path),
        "started_at": started_at,
        "attempt_id": attempt_id,
        "result": None,
        "error": None,
    }
    return h._send_json(200, {
        "ok": True,
        "job_id": job_id,
        "beat_id": beat_id,
        "route": route,
        "attempt_id": attempt_id,
        "log_path": str(log_path),
    })


def _read_native_lipsync_manifest(path: str | Path | None) -> dict | None:
    if not path:
        return None
    manifest = Path(path)
    if not manifest.is_file():
        return None
    try:
        parsed = json.loads(manifest.read_text(encoding="utf-8"))
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def handle_bg_poll_kling_native_lipsync_experiment_status(h) -> None:
    """GET /api/bg/poll-kling-native-lipsync-experiment-status?job_id=..."""
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(h.path).query)
    job_id = (qs.get("job_id") or [""])[0]
    if not job_id or job_id not in _NATIVE_LIPSYNC_JOBS:
        return h._send_error_v59(
            404,
            error_code="NATIVE_LIPSYNC_JOB_NOT_FOUND",
            error_message=f"unknown native lipsync job_id: {job_id}",
            retry_safe=True,
        )
    job = _NATIVE_LIPSYNC_JOBS[job_id]
    proc = job.get("proc")
    if proc and job["status"] == "running":
        rc = proc.poll()
        if rc is not None:
            job["ended_at"] = datetime.now(timezone.utc).isoformat()
            job["exit_code"] = rc
            manifest = _read_native_lipsync_manifest(job.get("manifest_path"))
            job["result"] = manifest
            if manifest and manifest.get("status") == "passed":
                job["status"] = "done"
            else:
                job["status"] = "failed"
                if manifest and manifest.get("error"):
                    job["error"] = manifest.get("error")
                else:
                    job["error"] = "Native Kling LipSync experiment failed; no production clip was changed."
    payload = {k: v for k, v in job.items() if k != "proc"}
    return h._send_json(200, payload)


def _tail_read_text(path: str | Path | None, *, max_bytes: int = _O3_LOG_TAIL_BYTES) -> str:
    """Read only the tail of a growing O3 job log — poll must not slurp multi-MB files."""
    if not path:
        return ""
    p = Path(path)
    if not p.is_file():
        return ""
    try:
        size = p.stat().st_size
    except OSError:
        return ""
    if size <= max_bytes:
        return p.read_text(encoding="utf-8", errors="replace")
    try:
        with open(p, "rb") as fh:
            fh.seek(max(0, size - max_bytes))
            chunk = fh.read()
    except OSError:
        return ""
    text = chunk.decode("utf-8", errors="replace")
    if size > max_bytes and "\n" in text:
        text = text.split("\n", 1)[-1]
    return text


def _parse_o3_pipeline_result_from_log(
    log_path: str | Path | None,
    *,
    tail_bytes: int | None = _O3_LOG_TAIL_BYTES,
) -> dict | None:
    """Parse subprocess log — Arlo lipsync returns ``{"ok": true}``; element pipeline ``phase: done``."""
    if not log_path:
        return None
    path = Path(log_path)
    if not path.is_file():
        return None
    if tail_bytes is None:
        log_text = path.read_text(encoding="utf-8", errors="replace")
    else:
        log_text = _tail_read_text(path, max_bytes=int(tail_bytes))
    for line in reversed(log_text.splitlines()):
        stripped = line.strip()
        if not stripped.startswith("{"):
            continue
        try:
            parsed = json.loads(stripped)
        except Exception:
            continue
        if not isinstance(parsed, dict):
            continue
        if parsed.get("ok"):
            return parsed
        if parsed.get("phase") == "done" and parsed.get("video"):
            delivery = parsed.get("delivery") or {}
            return {
                "ok": True,
                "beat_id": parsed.get("beat_id"),
                "video": parsed.get("video"),
                "raw_probe": parsed.get("raw"),
                "delivery_probe": delivery,
                "duration_s": delivery.get("duration_s"),
            }
        if parsed.get("phase") == "sidecar_recovered" and parsed.get("video"):
            return {
                "ok": True,
                "beat_id": parsed.get("beat_id"),
                "video": parsed.get("video"),
                "recovered_from_sidecar_io_error": True,
            }
        if parsed.get("phase") == "delivery_encode" and parsed.get("dst"):
            dst = str(parsed["dst"])
            if Path(dst).is_file():
                return {
                    "ok": True,
                    "beat_id": parsed.get("beat_id"),
                    "video": dst,
                    "recovered_from_delivery_encode": True,
                }
    return None


def _summarize_o3_job_error(error: str | None) -> str:
    text = str(error or "").strip()
    if not text:
        return "O3 voice job failed; no provider error was returned."
    runtime_marker = "RuntimeError:"
    if runtime_marker in text:
        text = text.split(runtime_marker)[-1].strip()
    if "Kling LipSync returned sub-720p output" in text:
        first = text.splitlines()[0].strip()
        return f"{first} Previous approved clip was kept active."
    if "Could not download the input" in text:
        return (
            "WaveSpeed could not download the temporary lipsync URL and data-URI lipsync fallback "
            "did not complete; previous approved clip was kept active."
        )
    if "No lipsync input host returned byte-complete public files" in text:
        return (
            "No lipsync input host returned byte-complete public files. "
            "The job was stopped before WaveSpeed submission; previous approved clip was kept active."
        )
    if "non-public host" in text.lower() or "unsafe url" in text.lower():
        return (
            "WaveSpeed rejected the lipsync staging URL (localhost is not public). "
            "Previous approved clip was kept active; retry after R2 staging is configured."
        )
    if "queued timeout" in text.lower() or "queued_timeout" in text.lower():
        return (
            "WaveSpeed queued the lipsync job too long and timed out. "
            "Previous approved clip was kept active."
        )
    if "Poll HTTP 502" in text or "502 Bad Gateway" in text:
        return (
            "WaveSpeed gateway returned 502 while polling the O3 job — transient provider outage. "
            "Previous approved clip was kept active; click Generate again in a minute."
        )
    if any(token in text for token in ("Poll HTTP 503", "Poll HTTP 504", "Poll HTTP 500", "Poll HTTP 429")):
        return (
            "WaveSpeed returned a transient gateway error while polling the O3 job. "
            "Previous approved clip was kept active; retry shortly."
        )
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return (lines[-1] if lines else text)[:500]



def _iter_bg_beats(sidecar: dict):
    for arc in (sidecar.get("arcs") or {}).values():
        for seg in (arc.get("segments") or {}).values():
            for beat in seg.get("beats") or []:
                if isinstance(beat, dict):
                    yield beat


def _sidecar_voice_fix_for_beat(beat_id: str) -> tuple[str, str]:
    """Read voice-fix state from sidecar — event/beat agnostic."""
    if not beat_id:
        return "", ""
    try:
        bg = _bg_module()
        sidecar = bg.read_sidecar()
        sidecar = bg._migrate_sidecar(sidecar)
        _, beat = bg.find_beat(sidecar, str(beat_id))
        if not beat:
            return "", ""
        return (
            str(beat.get("kling_o3_voice_fix_status") or ""),
            str(beat.get("kling_o3_voice_fix_error") or ""),
        )
    except Exception as exc:
        print(f"[bg_o3_job] sidecar voice_fix read failed for {beat_id}: {exc}", flush=True)
    return "", ""


def _pid_is_running(pid_value) -> bool:
    try:
        pid = int(pid_value or 0)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


_STUCK_O3_JOB_STATUS_PREFIXES = ("o3_voice_job_", "o3_element_")
_STUCK_O3_CLEAR_FIELDS = (
    "kling_o3_voice_fix_ui_job_id",
    "kling_o3_voice_fix_job_pid",
    "kling_o3_voice_fix_job_started_at",
    "kling_o3_voice_fix_attempt_id",
    "kling_o3_voice_fix_error",
    "kling_o3_voice_fix_error_code",
    "kling_o3_voice_fix_phase",
    "kling_o3_voice_fix_job_completed_at",
    "o3_active_intent_id",
    "o3_active_intent_job_id",
)


def _reconcile_must_preserve_active_o3_job(beat: dict) -> bool:
    """True when a live redo owns this beat — reconcile must not clear attempt_id/ui_job_id."""
    from o3_job_status_contract import voice_fix_is_terminal_failure

    voice_fix = str(beat.get("kling_o3_voice_fix_status") or "")
    if voice_fix == "approved":
        pid = beat.get("kling_o3_voice_fix_job_pid")
        return pid is not None and _pid_is_running(int(pid))
    if voice_fix_is_terminal_failure(voice_fix):
        return False
    if _beat_o3_job_looks_running(beat):
        return True
    pid = beat.get("kling_o3_voice_fix_job_pid")
    if pid is not None and _pid_is_running(int(pid)):
        return True
    return False


def _beat_has_stale_o3_job_pointers(beat: dict) -> bool:
    return any(
        beat.get(key)
        for key in (
            "kling_o3_voice_fix_job_pid",
            "kling_o3_voice_fix_ui_job_id",
            "kling_o3_voice_fix_job_started_at",
        )
    )


def _clear_stale_o3_job_pointers(beat: dict) -> None:
    for key in _STUCK_O3_CLEAR_FIELDS:
        beat.pop(key, None)


def _beat_o3_job_looks_running(beat: dict) -> bool:
    """Stuck-reconcile heuristic only — not an operator gate (see ``_beat_o3_operator_lock_active``)."""
    from o3_job_status_contract import beat_o3_voice_job_running

    return beat_o3_voice_job_running(beat)


_O3_TERMINAL_POINTER_FIELDS = (
    "kling_o3_voice_fix_ui_job_id",
    "kling_o3_voice_fix_job_pid",
    "kling_o3_voice_fix_job_started_at",
    "kling_o3_voice_fix_attempt_id",
    "kling_o3_voice_fix_phase",
    "o3_active_intent_id",
    "o3_active_intent_job_id",
)


def reconcile_o3_terminal_attempt_fields_all_events(sidecar: dict) -> int:
    """Stamp terminal failed/done onto beats; clear stale intent locks (all Event_*)."""
    from o3_generation_intent import (
        _clear_beat_intent_lock_fields,
        intent_event_dir_for_beat,
        job_id_from_beat,
        load_intent_terminal,
        terminal_path_for_job,
    )
    from o3_job_status_contract import INTENT_TERMINAL_STATUSES, beat_o3_operator_busy

    changed = 0
    for beat in _iter_bg_beats(sidecar):
        beat_id = str(beat.get("beat_id") or "").strip()
        try:
            event_dir = intent_event_dir_for_beat(beat_id) if beat_id else None
        except Exception:
            event_dir = _event_dir_from_beat_id(beat_id) if beat_id else None
        if beat_o3_operator_busy(beat, event_dir, in_memory_jobs=_ARLO_O3_JOBS):
            continue
        beat_id = str(beat.get("beat_id") or "").strip()
        if not beat_id:
            continue
        from o3_job_status_contract import resolve_o3_current_job_id

        job_id = str(
            resolve_o3_current_job_id(beat)
            or beat.get("kling_o3_voice_fix_ui_job_id")
            or job_id_from_beat(beat)
            or "",
        ).strip()
        if not job_id:
            continue
        try:
            event_dir = intent_event_dir_for_beat(beat_id)
        except Exception:
            event_dir = _event_dir_from_beat_id(beat_id)
        term_path = terminal_path_for_job(job_id, event_dir)
        if not term_path.is_file():
            continue
        try:
            terminal = load_intent_terminal(term_path)
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        status = str(terminal.get("status") or "")
        if status not in INTENT_TERMINAL_STATUSES:
            continue
        if status == "failed":
            fail_msg = str((terminal.get("failure") or {}).get("message") or "")
            if fail_msg:
                beat["kling_o3_voice_fix_error"] = fail_msg
                beat["kling_o3_last_attempt_failed_at"] = terminal.get("terminal_at")
        elif status == "cancelled":
            from o3_generation_intent import heal_o3_beat_after_aborted_attempt

            heal_o3_beat_after_aborted_attempt(beat)
        _clear_beat_intent_lock_fields(beat)
        for key in _O3_TERMINAL_POINTER_FIELDS:
            beat.pop(key, None)
        beat.pop("kling_o3_voice_fix_job_log_path", None)
        changed += 1
    return changed


def reconcile_stale_o3_job_log_pointers_all_events(sidecar: dict) -> int:
    """Clear job log/poll pointers when the linked terminal is cancelled/failed but clip kept."""
    from o3_generation_intent import (
        heal_o3_beat_after_aborted_attempt,
        intent_event_dir_for_beat,
        job_id_from_beat,
        load_intent_terminal,
        terminal_path_for_job,
    )
    from o3_job_status_contract import beat_o3_operator_busy

    changed = 0
    for beat in _iter_bg_beats(sidecar):
        beat_id = str(beat.get("beat_id") or "").strip()
        try:
            event_dir = intent_event_dir_for_beat(beat_id) if beat_id else None
        except Exception:
            event_dir = _event_dir_from_beat_id(beat_id) if beat_id else None
        if beat_o3_operator_busy(beat, event_dir, in_memory_jobs=_ARLO_O3_JOBS):
            continue
        job_id = job_id_from_beat(beat)
        if not beat_id or not job_id:
            continue
        try:
            event_dir = intent_event_dir_for_beat(beat_id)
        except Exception:
            event_dir = _event_dir_from_beat_id(beat_id)
        term_path = terminal_path_for_job(job_id, event_dir)
        if not term_path.is_file():
            continue
        try:
            terminal = load_intent_terminal(term_path)
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        if str(terminal.get("status") or "") not in {"cancelled", "failed"}:
            continue
        if heal_o3_beat_after_aborted_attempt(beat):
            changed += 1
    return changed


def _sidecar_io_error_text(error: str | None) -> bool:
    text = str(error or "")
    return "Resource deadlock avoided" in text or "[Errno 11]" in text or "[Errno 35]" in text


def _try_orphan_o3_delivery_recovery(
    beat_id: str,
    event_dir: Path,
    log_path: str | Path | None,
    *,
    make_active: bool = True,
) -> dict | None:
    """Recover delivery mp4 when Kling finished but sidecar finalize hit Dropbox errno 11/35."""
    if not beat_id:
        return None
    try:
        bg = _bg_module()
        recovered = bg.recover_orphan_o3_delivery(
            str(beat_id),
            event_dir,
            log_path=log_path,
            make_active=make_active,
        )
        if recovered.get("recovered"):
            print(
                f"[o3_orphan_recovery] beat_id={beat_id} "
                f"video={recovered.get('delivery_path') or recovered.get('video_path')} "
                f"recovered={recovered.get('recovered')}",
                flush=True,
            )
            return recovered
    except Exception as exc:
        print(f"[bg_o3_job] orphan recovery failed for {beat_id}: {exc}", flush=True)
    return None


def _beat_candidate_for_stuck_o3_reconcile(beat: dict) -> bool:
    """Session-state stuck heal scans only beats with job pointers or terminal drift."""
    status = str(beat.get("status") or "")
    voice_fix = str(beat.get("kling_o3_voice_fix_status") or "")
    kling_status = str(beat.get("kling_o3_status") or "")
    if voice_fix == "approved" or kling_status == "approved":
        return bool(
            _beat_has_stale_o3_job_pointers(beat)
            or any(status.startswith(p) for p in _STUCK_O3_JOB_STATUS_PREFIXES)
        )
    if beat.get("kling_o3_voice_fix_ui_job_id"):
        return True
    if voice_fix.startswith("failed") or voice_fix in {"job_running", "job_starting"}:
        return True
    if status.startswith("o3_"):
        return True
    if beat.get("kling_o3_voice_fix_job_pid") is not None:
        return True
    return False


def reconcile_stale_lipsync_hosting_failures(sidecar: dict) -> int:
    """Clear pre-R2 hosting failures once lipsync public host is configured.

    Beats that kept an approved O3 clip after a failed lipsync upload attempt should
    not show stale \"configure R2\" errors after R2 is live on this machine.
    """
    try:
        from lipsync_public_host import (
            is_stale_lipsync_hosting_failure,
            lipsync_public_host_ready,
        )
    except ImportError:
        return 0
    creds = None
    try:
        try:
            from credentials import load_credentials  # type: ignore
        except ImportError:
            from tools.credentials_lib.credentials import load_credentials  # type: ignore
        creds = load_credentials()
    except Exception:
        creds = None
    if not lipsync_public_host_ready(creds=creds):
        return 0
    changed = 0
    for beat in _iter_bg_beats(sidecar):
        voice_fix = str(beat.get("kling_o3_voice_fix_status") or "")
        if not voice_fix.startswith("failed"):
            continue
        if not is_stale_lipsync_hosting_failure(str(beat.get("kling_o3_voice_fix_error") or "")):
            continue
        if str(beat.get("kling_o3_status") or "") != "approved":
            continue
        video_path = str(beat.get("kling_o3_video_path") or "")
        if not video_path or not Path(video_path).is_file():
            continue
        if _beat_o3_job_looks_running(beat):
            continue
        beat["kling_o3_voice_fix_status"] = "approved"
        beat.pop("kling_o3_voice_fix_error", None)
        beat.pop("kling_o3_voice_fix_error_code", None)
        beat.pop("kling_o3_voice_fix_url_transport_error", None)
        changed += 1
    return changed


def reconcile_stuck_o3_voice_beats(sidecar: dict) -> int:
    """Clear beats stuck in running UI state after a dead subprocess or stale error."""
    changed = 0
    for beat in _iter_bg_beats(sidecar):
        if not _beat_candidate_for_stuck_o3_reconcile(beat):
            continue
        status = str(beat.get("status") or "")
        voice_fix = str(beat.get("kling_o3_voice_fix_status") or "")
        kling_status = str(beat.get("kling_o3_status") or "")

        # Pipeline finished and sidecar is terminal — drop stale subprocess pointers.
        # Invariant: never clear pointers while a redo is actively running (kling_o3_status
        # may still be "approved" from the prior generation until the new clip lands).
        if voice_fix == "approved" or kling_status == "approved":
            if _reconcile_must_preserve_active_o3_job(beat):
                continue
            if _beat_has_stale_o3_job_pointers(beat) or status.startswith(_STUCK_O3_JOB_STATUS_PREFIXES):
                _clear_stale_o3_job_pointers(beat)
                video_path = str(beat.get("kling_o3_video_path") or "")
                if video_path and Path(video_path).is_file() and (
                    voice_fix == "approved" or kling_status == "approved"
                ):
                    from kling_stitch_readiness import align_beat_active_delivery_clip  # noqa: PLC0415

                    align_beat_active_delivery_clip(
                        beat,
                        video_path,
                        mark_voice_fix_approved=True,
                    )
                changed += 1
            else:
                from o3_generation_intent import heal_o3_beat_after_aborted_attempt
                from o3_job_status_contract import voice_fix_is_terminal_failure

                if voice_fix_is_terminal_failure(voice_fix) and heal_o3_beat_after_aborted_attempt(beat):
                    changed += 1
            continue

        pid = beat.get("kling_o3_voice_fix_job_pid")
        pid_dead = pid is not None and not _pid_is_running(int(pid))
        voice_failed = voice_fix.startswith("failed")

        # Subprocess exited but sidecar never got final persist (server restart / poll miss).
        if pid_dead and _beat_o3_job_looks_running(beat):
            log_path = beat.get("kling_o3_voice_fix_job_log_path")
            log_text = _tail_read_text(log_path) if log_path else ""
            is_element_job = (
                "o3_element_native_voice" in log_text
                or '"element_id"' in log_text
                or beat.get("kling_o3_mode") == "o3_element_native_voice"
            )
            log_result = _parse_o3_pipeline_result_from_log(log_path)
            video_path = str((log_result or {}).get("video") or "")
            if log_result and video_path and Path(video_path).is_file() and is_element_job:
                now = datetime.now(timezone.utc).isoformat()
                from kling_stitch_readiness import align_beat_active_delivery_clip  # noqa: PLC0415

                align_beat_active_delivery_clip(
                    beat,
                    video_path,
                    mark_voice_fix_approved=True,
                )
                beat["kling_o3_voice_fix_phase"] = "finalize"
                beat["kling_o3_voice_fix_completed_at"] = now
                beat["kling_o3_completed_at"] = beat.get("kling_o3_completed_at") or now
                _clear_stale_o3_job_pointers(beat)
                changed += 1
                continue
            if is_element_job and _sidecar_io_error_text(log_text):
                event_dir = _event_dir_from_beat_id(str(beat.get("beat_id") or ""))
                if _try_orphan_o3_delivery_recovery(str(beat.get("beat_id") or ""), event_dir, log_path):
                    _clear_stale_o3_job_pointers(beat)
                    changed += 1
                    continue
            if is_element_job and '"phase": "done"' in log_text and pid_dead:
                event_dir = _event_dir_from_beat_id(str(beat.get("beat_id") or ""))
                if _try_orphan_o3_delivery_recovery(str(beat.get("beat_id") or ""), event_dir, log_path):
                    _clear_stale_o3_job_pointers(beat)
                    changed += 1
                    continue

        if voice_failed and _sidecar_io_error_text(str(beat.get("kling_o3_voice_fix_error") or "")):
            log_path = beat.get("kling_o3_voice_fix_job_log_path")
            event_dir = _event_dir_from_beat_id(str(beat.get("beat_id") or ""))
            if _try_orphan_o3_delivery_recovery(str(beat.get("beat_id") or ""), event_dir, log_path):
                _clear_stale_o3_job_pointers(beat)
                changed += 1
                continue

        if not any(status.startswith(p) for p in _STUCK_O3_JOB_STATUS_PREFIXES):
            if not (voice_failed and beat.get("kling_o3_voice_fix_ui_job_id")):
                continue
        missing_api_error = "update_beat_locked" in str(beat.get("kling_o3_voice_fix_error") or "")
        stale_process = voice_failed and (pid_dead or missing_api_error)
        if not stale_process and not (voice_failed and beat.get("kling_o3_voice_fix_ui_job_id") and pid_dead):
            if not (voice_failed and status.startswith("o3_") and pid_dead):
                continue
        _clear_stale_o3_job_pointers(beat)
        if beat.get("kling_o3_video_path") and kling_status == "approved":
            beat["status"] = "approved"
            beat["kling_o3_voice_fix_status"] = "approved"
        elif voice_failed:
            beat["status"] = "accepted"
        changed += 1
    return changed


def _beat_matches_o3_ui_job_id(beat: dict, job_id: str) -> bool:
    """Match in-memory poll id to sidecar — ui_job_id or arlo_o3_jobs log filename."""
    if not job_id:
        return False
    if beat.get("kling_o3_voice_fix_ui_job_id") == job_id:
        return True
    log_path = str(beat.get("kling_o3_voice_fix_job_log_path") or "")
    if not log_path:
        return False
    # .../arlo_o3_jobs/{job_id}_bg_arc1_event2_pre_beat_03.log
    return f"/{job_id}_" in log_path or log_path.endswith(f"/{job_id}.log")


def _promote_o3_job_from_log_if_terminal(job: dict, event_dir: Path) -> bool:
    """Mark in-memory O3 job done when log shows delivery but proc handle is stale."""
    if job.get("status") != "running":
        return False
    log_path = job.get("log_path")
    beat_id = str(job.get("beat_id") or "")
    if not beat_id or not log_path:
        return False
    from o3_job_status_contract import voice_fix_is_terminal_failure

    voice_fix, voice_err = _sidecar_voice_fix_for_beat(beat_id)
    if voice_fix_is_terminal_failure(voice_fix):
        job["status"] = "failed"
        job["ended_at"] = datetime.now(timezone.utc).isoformat()
        job["error"] = _summarize_o3_job_error(voice_err or "O3 voice job failed")
        job.pop("result", None)
        return True
    log_result = _parse_o3_pipeline_result_from_log(log_path)
    if not log_result:
        return False
    video = str(log_result.get("video") or "")
    if not video or not Path(video).is_file():
        return False
    recovered = _try_orphan_o3_delivery_recovery(beat_id, event_dir, log_path)
    job["status"] = "done"
    job["ended_at"] = datetime.now(timezone.utc).isoformat()
    job["result"] = {
        "ok": True,
        "beat_id": beat_id,
        "video": recovered.get("delivery_path") if recovered else video,
        "recovered_from_log": True,
    }
    job.pop("error", None)
    return True


def _resolve_intent_log_path(job_id: str, intent: dict, event_dir: Path) -> Path | None:
    """Log file for an O3 intent — runtime field or ``arlo_o3_jobs/{job_id}_{beat_id}.log``."""
    log_path = Path(str((intent.get("runtime") or {}).get("log_path") or ""))
    if log_path.is_file():
        return log_path
    beat_id = str(intent.get("beat_id") or "").strip()
    if beat_id:
        alt = event_dir / "arlo_o3_jobs" / f"{job_id}_{beat_id}.log"
        if alt.is_file():
            return alt
    return log_path if log_path.is_file() else None


def _recover_o3_job_from_intent_terminal(job_id: str, event_dir: Path) -> dict | None:
    """Rebuild poll payload from intent + terminal on disk after server restart."""
    from o3_generation_intent import (
        INTENT_TERMINAL_STATUSES,
        intent_path_for_job,
        intent_poll_subset,
        load_generation_intent,
        load_intent_terminal,
        terminal_path_for_job,
        _pipeline_done_from_log,
    )

    intent_path = intent_path_for_job(job_id, event_dir)
    if not intent_path.is_file():
        return None
    try:
        intent = load_generation_intent(intent_path)
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    beat_id = str(intent.get("beat_id") or "").strip()
    log_path = _resolve_intent_log_path(job_id, intent, event_dir)
    terminal = load_intent_terminal(terminal_path_for_job(job_id, event_dir))
    if terminal:
        status = str(terminal.get("status") or "").strip()
        from o3_generation_intent import (
            INTENT_RUNNING_STATUS,
            close_o3_attempt,
            o3_subprocess_is_live,
            O3_JOB_LOST_FAILURE_MESSAGE,
        )
        if status == INTENT_RUNNING_STATUS:
            if beat_id and not o3_subprocess_is_live(job_id, beat_id, event_dir):
                close_o3_attempt(
                    job_id,
                    beat_id,
                    event_dir,
                    "failed",
                    reason=O3_JOB_LOST_FAILURE_MESSAGE,
                    phase_last="poll_intent_running_recovery",
                    intent=intent,
                    persist_beat=True,
                )
                return {
                    "status": "failed",
                    "job_id": job_id,
                    "beat_id": beat_id,
                    "log_path": str(log_path) if log_path else None,
                    "error": O3_JOB_LOST_FAILURE_MESSAGE,
                    "recovered": True,
                    "intent_zombie_recovery": True,
                    "intent": intent_poll_subset(intent),
                }
            return {
                "status": "running",
                "job_id": job_id,
                "beat_id": beat_id,
                "log_path": str(log_path) if log_path else None,
                "recovered": True,
                "intent_running_recovery": True,
                "intent": intent_poll_subset(intent),
            }
        if status in INTENT_TERMINAL_STATUSES:
            body: dict = {
                "status": "done_with_warning" if status == "done_with_warning" else status,
                "job_id": job_id,
                "beat_id": beat_id,
                "log_path": str(log_path) if log_path else None,
                "recovered": True,
                "intent_terminal_recovery": True,
                "intent": intent_poll_subset(intent),
            }
            if status in ("done", "done_with_warning"):
                delivered = terminal.get("delivered") or {}
                video = str(delivered.get("video_path") or "")
                if not video and log_path:
                    done_row = _pipeline_done_from_log(log_path)
                    video = str((done_row or {}).get("video") or "")
                if beat_id and log_path and not video:
                    recovered = _try_orphan_o3_delivery_recovery(beat_id, event_dir, log_path)
                    if recovered:
                        video = str(recovered.get("delivery_path") or "")
                if video:
                    body["result"] = {"ok": True, "beat_id": beat_id, "video": video}
                if status == "done_with_warning":
                    body["warning"] = terminal.get("warning")
            elif status == "failed":
                fail = terminal.get("failure") or {}
                if log_path and log_path.is_file():
                    done_row = _pipeline_done_from_log(log_path)
                    video = str((done_row or {}).get("video") or "").strip()
                    if done_row and video:
                        body["status"] = "done"
                        body["result"] = {"ok": True, "beat_id": beat_id, "video": video}
                        body.pop("error", None)
                        body["intent_false_failed_recovery"] = True
                        return body
                if beat_id:
                    voice_fix, _ = _sidecar_voice_fix_for_beat(beat_id)
                    if voice_fix == "approved":
                        try:
                            bg = _bg_module()
                            sidecar = bg.read_sidecar()
                            _, beat_row = bg.find_beat(sidecar, beat_id)
                            video = str((beat_row or {}).get("kling_o3_video_path") or "").strip()
                        except Exception:
                            video = ""
                        if video and Path(video).is_file():
                            body["status"] = "done"
                            body["result"] = {"ok": True, "beat_id": beat_id, "video": video}
                            body.pop("error", None)
                            body["intent_false_failed_recovery"] = True
                            return body
                body["error"] = str(fail.get("message") or "O3 job failed")
            elif status == "cancelled":
                body["error"] = str(
                    (terminal.get("failure") or {}).get("message") or "O3 job cancelled"
                )
            return body
    if log_path and log_path.is_file():
        done_row = _pipeline_done_from_log(log_path)
        if done_row:
            video = str(done_row.get("video") or "")
            if beat_id and not video:
                recovered = _try_orphan_o3_delivery_recovery(beat_id, event_dir, log_path)
                if recovered:
                    video = str(recovered.get("delivery_path") or "")
            return {
                "status": "done",
                "job_id": job_id,
                "beat_id": beat_id,
                "log_path": str(log_path),
                "result": {"ok": True, "beat_id": beat_id, "video": video},
                "recovered": True,
                "intent_log_recovery": True,
                "intent": intent_poll_subset(intent),
            }
        if beat_id:
            from o3_generation_intent import (
                close_o3_attempt,
                o3_subprocess_is_live,
                O3_JOB_LOST_FAILURE_MESSAGE,
            )
            if o3_subprocess_is_live(job_id, beat_id, event_dir):
                return {
                    "status": "running",
                    "job_id": job_id,
                    "beat_id": beat_id,
                    "log_path": str(log_path) if log_path else None,
                    "recovered": True,
                    "intent_running_recovery": True,
                    "intent": intent_poll_subset(intent),
                }
            close_o3_attempt(
                job_id,
                beat_id,
                event_dir,
                "failed",
                reason=O3_JOB_LOST_FAILURE_MESSAGE,
                phase_last="poll_intent_orphan_recovery",
                intent=intent,
                persist_beat=True,
            )
            return {
                "status": "failed",
                "job_id": job_id,
                "beat_id": beat_id,
                "log_path": str(log_path) if log_path else None,
                "error": O3_JOB_LOST_FAILURE_MESSAGE,
                "recovered": True,
                "intent_zombie_recovery": True,
                "intent": intent_poll_subset(intent),
            }
    return None


def _recover_o3_job_from_sidecar(job_id: str) -> dict | None:
    if not job_id:
        return None
    try:
        bg = _bg_module()
        sidecar = bg.read_sidecar()
        sidecar = bg._migrate_sidecar(sidecar)
        for beat in _iter_bg_beats(sidecar):
            if not _beat_matches_o3_ui_job_id(beat, job_id):
                continue
            log_path = beat.get("kling_o3_voice_fix_job_log_path")
            voice_fix = str(beat.get("kling_o3_voice_fix_status") or "")
            from o3_job_status_contract import voice_fix_is_terminal_failure

            if voice_fix_is_terminal_failure(voice_fix):
                beat.pop("kling_o3_voice_fix_ui_job_id", None)
                bg.update_beat_locked(str(beat.get("beat_id")), lambda b, _s: b.pop("kling_o3_voice_fix_ui_job_id", None))
                return {
                    "status": "failed",
                    "beat_id": beat.get("beat_id"),
                    "job_id": job_id,
                    "log_path": log_path,
                    "error": _summarize_o3_job_error(
                        beat.get("kling_o3_voice_fix_error") or "O3 voice job failed"
                    ),
                    "recovered": True,
                }
            from o3_job_status_contract import O3_VOICE_FIX_RUNNING_STATUSES

            if voice_fix in O3_VOICE_FIX_RUNNING_STATUSES:
                return {
                    "status": "running",
                    "beat_id": beat.get("beat_id"),
                    "job_id": job_id,
                    "log_path": beat.get("kling_o3_voice_fix_job_log_path"),
                    "started_at": beat.get("kling_o3_voice_fix_job_started_at"),
                    "recovered": True,
                }
            result = _parse_o3_pipeline_result_from_log(log_path)
            if result or voice_fix == "approved":
                beat_id = str(beat.get("beat_id") or "")
                voice_fix = str(beat.get("kling_o3_voice_fix_status") or "")
                if result and voice_fix != "approved" and beat_id:
                    event_dir = _event_dir_from_beat_id(beat_id)
                    _try_orphan_o3_delivery_recovery(beat_id, event_dir, log_path)
                return {
                    "status": "done",
                    "beat_id": beat.get("beat_id"),
                    "job_id": job_id,
                    "log_path": log_path,
                    "started_at": beat.get("kling_o3_voice_fix_job_started_at"),
                    "result": result,
                    "recovered": True,
                }
            if beat.get("kling_o3_voice_fix_status") == "failed":
                err_text = str(beat.get("kling_o3_voice_fix_error") or "")
                log_path = beat.get("kling_o3_voice_fix_job_log_path")
                if _sidecar_io_error_text(err_text):
                    event_dir = _event_dir_from_beat_id(str(beat.get("beat_id") or ""))
                    if _try_orphan_o3_delivery_recovery(
                        str(beat.get("beat_id") or ""),
                        event_dir,
                        log_path,
                    ):
                        result = _parse_o3_pipeline_result_from_log(log_path)
                        return {
                            "status": "done",
                            "beat_id": beat.get("beat_id"),
                            "job_id": job_id,
                            "log_path": log_path,
                            "result": result,
                            "recovered": True,
                            "orphan_sidecar_recovery": True,
                        }
                _bid = str(beat.get("beat_id") or "")
                bg.update_beat_locked(_bid, lambda b, _s: b.pop("kling_o3_voice_fix_ui_job_id", None))
                return {
                    "status": "failed",
                    "beat_id": beat.get("beat_id"),
                    "job_id": job_id,
                    "log_path": beat.get("kling_o3_voice_fix_job_log_path"),
                    "error": _summarize_o3_job_error(beat.get("kling_o3_voice_fix_error") or "O3 job failed"),
                    "recovered": True,
                }
            pid = beat.get("kling_o3_voice_fix_job_pid")
            if pid and not _pid_is_running(pid):
                log_path = beat.get("kling_o3_voice_fix_job_log_path")
                event_dir = _event_dir_from_beat_id(str(beat.get("beat_id") or ""))
                if _try_orphan_o3_delivery_recovery(
                    str(beat.get("beat_id") or ""),
                    event_dir,
                    log_path,
                ):
                    result = _parse_o3_pipeline_result_from_log(log_path)
                    return {
                        "status": "done",
                        "beat_id": beat.get("beat_id"),
                        "job_id": job_id,
                        "log_path": log_path,
                        "result": result,
                        "recovered": True,
                        "orphan_sidecar_recovery": True,
                    }
                _bid = str(beat.get("beat_id") or "")
                _fail_msg = "O3 job process is no longer running and no completion result was recorded."
                _now = datetime.now(timezone.utc).isoformat()

                def _stale_fail(b: dict, _s: dict) -> None:
                    b.pop("kling_o3_voice_fix_ui_job_id", None)
                    b["kling_o3_voice_fix_status"] = "failed"
                    b["kling_o3_voice_fix_error_code"] = "STALE_JOB_PROCESS_GONE"
                    b["kling_o3_voice_fix_error"] = _fail_msg
                    b["kling_o3_voice_fix_job_completed_at"] = _now

                bg.update_beat_locked(_bid, _stale_fail)
                return {
                    "status": "failed",
                    "beat_id": beat.get("beat_id"),
                    "job_id": job_id,
                    "log_path": beat.get("kling_o3_voice_fix_job_log_path"),
                    "error": _summarize_o3_job_error(beat.get("kling_o3_voice_fix_error")),
                    "recovered": True,
                }
            return {
                "status": "running",
                "beat_id": beat.get("beat_id"),
                "job_id": job_id,
                "log_path": beat.get("kling_o3_voice_fix_job_log_path"),
                "started_at": beat.get("kling_o3_voice_fix_job_started_at"),
                "recovered": True,
            }
    except Exception as exc:
        print(f"[bg_o3_job] recover failed for {job_id}: {exc}", flush=True)
    return None


def _ensure_o3_job_metadata(job_id: str, job: dict) -> None:
    """Keep in-memory running jobs recoverable after refresh/server restarts.

    The pipeline subprocess writes detailed phase state, but the UI rehydrates
    active jobs from sidecar fields. If those fields are lost by a concurrent
    sidecar write, the backend may still know the job is running while a hard
    refresh shows the beat as idle. Re-stamp the lightweight job pointer on
    live polls (throttled) so the sidecar remains the durable source of truth.
    """
    try:
        beat_id = job.get("beat_id")
        if not beat_id:
            return
        now = time.monotonic()
        last = _O3_JOB_METADATA_LAST_STAMP.get(str(job_id), 0.0)
        if now - last < _O3_JOB_METADATA_STAMP_INTERVAL_S:
            return
        bg = _bg_module()
        def _stamp(b: dict, _sc: dict) -> None:
            current_attempt = b.get("kling_o3_voice_fix_attempt_id")
            if current_attempt and job.get("attempt_id") and current_attempt != job.get("attempt_id"):
                return
            st = str(b.get("kling_o3_voice_fix_status") or "").lower()
            terminal_statuses = {"approved", "failed", "failed_o3", "failed_provider_fetch", "failed_provider_sub720"}
            if st in terminal_statuses:
                return
            updates = {
                "kling_o3_voice_fix_ui_job_id": job_id,
                "kling_o3_voice_fix_job_log_path": job.get("log_path"),
                "kling_o3_voice_fix_job_started_at": job.get("started_at"),
                "kling_o3_voice_fix_attempt_id": job.get("attempt_id"),
                "kling_o3_voice_fix_phase": "subprocess",
                "kling_o3_voice_fix_updated_at": datetime.now(timezone.utc).isoformat(),
            }
            for key, value in updates.items():
                if value and b.get(key) != value:
                    b[key] = value
            b.pop("kling_o3_voice_fix_error", None)
            b.pop("kling_o3_voice_fix_job_completed_at", None)
            if st in {"", "job_starting"}:
                b["kling_o3_voice_fix_status"] = "job_running"

        bg.update_beat_locked(str(beat_id), _stamp)
        _O3_JOB_METADATA_LAST_STAMP[str(job_id)] = now
    except Exception as exc:
        print(f"[bg_o3_job] ensure metadata failed for {job_id}: {exc}", flush=True)


def _clear_o3_job_metadata(job_id: str, *, status: str, result: dict | None = None, error: str | None = None) -> None:
    try:
        bg = _bg_module()
        def _clear(sidecar: dict) -> None:
            for beat in _iter_bg_beats(sidecar):
                if beat.get("kling_o3_voice_fix_ui_job_id") != job_id:
                    continue
                if status == "done":
                    beat.pop("kling_o3_voice_fix_ui_job_id", None)
                    beat.pop("kling_o3_voice_fix_job_pid", None)
                    beat.pop("kling_o3_voice_fix_job_started_at", None)
                    beat["kling_o3_voice_fix_job_completed_at"] = datetime.now(timezone.utc).isoformat()
                    beat["kling_o3_voice_fix_phase"] = "done"
                    if result:
                        beat["kling_o3_voice_fix_job_result"] = result
                elif status == "failed":
                    beat.pop("kling_o3_voice_fix_ui_job_id", None)
                    beat.pop("kling_o3_voice_fix_job_pid", None)
                    beat.pop("kling_o3_voice_fix_job_started_at", None)
                    beat["kling_o3_voice_fix_status"] = "failed"
                    beat["kling_o3_voice_fix_error_code"] = beat.get("kling_o3_voice_fix_error_code") or "SUBPROCESS_FAILED"
                    beat["kling_o3_voice_fix_phase"] = "failed"
                    if error:
                        beat["kling_o3_voice_fix_error"] = _summarize_o3_job_error(str(error))
                    try:
                        bg.restore_active_kling_o3_after_failed_redo(beat)
                    except Exception:
                        pass

        bg.mutate_sidecar_locked(_clear)
    except Exception as exc:
        print(f"[bg_o3_job] clear metadata failed for {job_id}: {exc}", flush=True)


def _bg_o3_trim_audit(h, audit_event: str, *, beat_id: str | None = None, **fields: object) -> None:
    """Read-only Beat Gen O3 trim audit — stdout + event-dir JSONL (no sidecar writes)."""
    row: dict[str, object] = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "event": audit_event,
    }
    if beat_id:
        row["beat_id"] = beat_id
    for key, val in fields.items():
        if val is not None and val != "":
            row[key] = val
    line = json.dumps(row, default=str)
    print(f"[bg_o3_trim_audit] {line}", flush=True)
    try:
        event_dir = Path(h.app.event_dir)
        if not event_dir.is_absolute():
            event_dir = _data_root(h) / event_dir
        log_path = event_dir / "_bg_o3_trim_audit.jsonl"
        with open(log_path, "a", encoding="utf-8") as audit_f:
            audit_f.write(line + "\n")
    except OSError:
        pass


def _bg_o3_trim_slot_context(
    bg,
    beat: dict | None,
    *,
    slot_index: object,
    req_video_path: str | None,
) -> dict[str, object]:
    """Snapshot slot/path alignment for trim forensics (read-only)."""
    if not isinstance(beat, dict):
        return {}
    ctx: dict[str, object] = {
        "active_video": Path(str(beat.get("kling_o3_video_path") or "")).name or None,
        "kling_o3_status": beat.get("kling_o3_status"),
    }
    if slot_index is None:
        return ctx
    try:
        si = int(slot_index)
        slots = bg.build_fixed_o3_ui_slots(beat)
        slot_opt = slots[si] if 0 <= si <= 2 else None
        slot_vp = str((slot_opt or {}).get("video_path") or "").strip()
        req_vp = str(req_video_path or "").strip()
        ctx["slot_index"] = si
        ctx["slot_video"] = Path(slot_vp).name if slot_vp else None
        ctx["req_video"] = Path(req_vp).name if req_vp else None
        if req_vp and slot_vp:
            ctx["path_match"] = slot_vp == req_vp
            if slot_vp != req_vp:
                direct = bg.find_o3_option_by_video_path(beat, req_vp)
                ctx["direct_lookup"] = "ok" if direct else "missing"
        registered = [
            Path(str(o.get("video_path") or "")).name
            for o in (beat.get("kling_o3_options") or [])
            if isinstance(o, dict) and o.get("video_path")
        ]
        ctx["registered_count"] = len(registered)
        if req_vp and req_vp not in {
            str(o.get("video_path") or "").strip()
            for o in (beat.get("kling_o3_options") or [])
            if isinstance(o, dict)
        }:
            alias = bg.find_o3_option_by_video_path(beat, req_vp)
            ctx["req_in_options"] = bool(alias)
        else:
            ctx["req_in_options"] = bool(req_vp)
    except (TypeError, ValueError) as exc:
        ctx["slot_context_error"] = str(exc)
    return ctx


def handle_bg_kling_o3_trim(h, body: dict) -> None:
    """POST /api/bg/kling-o3-trim — set/clear cut-out or legacy front/back trim on O3 clip."""
    import copy
    from urllib.parse import quote

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
    preview_only = bool(body.get("preview_only") or body.get("preview"))
    slot_index = body.get("slot_index")
    req_video_path = str(body.get("video_path") or "").strip() or None
    raw_cut_start = body.get("cut_start_s")
    raw_cut_end = body.get("cut_end_s")
    raw_trim_start = body.get("trim_start")
    raw_trim_back = body.get("trim_back")
    use_option_trim = (
        slot_index is not None
        and raw_cut_start is None
        and raw_cut_end is None
    )
    use_cut = slot_index is not None and not use_option_trim and (
        raw_cut_start is not None or raw_cut_end is not None
    )

    bg = _bg_module()
    trim_mode = (
        "option_trim" if use_option_trim else ("cut" if use_cut else "beat_trim")
    )
    event_label = Path(str(getattr(h.app, "event_dir", "") or "")).name or "unknown"
    _bg_o3_trim_audit(
        h,
        "REQUEST",
        beat_id=str(beat_id),
        scope_event=event_label,
        preview_only=preview_only,
        clear=bool(body.get("clear")),
        mode=trim_mode,
        slot_index=slot_index,
        req_video=Path(req_video_path).name if req_video_path else None,
        trim_start=raw_trim_start,
        trim_back=raw_trim_back,
        cut_start_s=raw_cut_start,
        cut_end_s=raw_cut_end,
    )
    try:
        sidecar_snap = bg.read_sidecar_for_poll_snapshot(lock_timeout_s=2)
        sidecar_snap = bg._migrate_sidecar(sidecar_snap)
        _, beat_snap = bg.find_beat(sidecar_snap, beat_id)
        slot_ctx = _bg_o3_trim_slot_context(
            bg,
            beat_snap,
            slot_index=slot_index,
            req_video_path=req_video_path,
        )
        if slot_ctx:
            _bg_o3_trim_audit(h, "SLOT_CONTEXT", beat_id=str(beat_id), **slot_ctx)
    except Exception as exc:
        _bg_o3_trim_audit(
            h,
            "SLOT_CONTEXT_SKIP",
            beat_id=str(beat_id),
            reason=str(exc),
        )

    def _files_url_for_disk_path(abs_path: Path, event_dir: Path) -> str | None:
        if not abs_path.is_file():
            return None
        prod_root = _data_root(h) / "Production"
        try:
            rel = abs_path.resolve().relative_to(prod_root)
            rel_str = f"Production/{rel.as_posix()}"
        except ValueError:
            try:
                rel = abs_path.resolve().relative_to(event_dir.resolve())
                rel_str = f"Production/{event_dir.name}/{rel.as_posix()}"
            except ValueError:
                rel_str = str(abs_path.resolve())
        mtime = int(abs_path.stat().st_mtime)
        return f"/files?path={quote(rel_str)}&v={mtime}"

    def _trim_baked_preview_url(persisted_beat: dict) -> str | None:
        """After Apply Cut bake, serve the stable export artifact — no second ffmpeg encode."""
        event_dir = Path(h.app.event_dir)
        if not event_dir.is_absolute():
            event_dir = _data_root(h) / event_dir
        baked: str | None = None
        if slot_index is not None:
            opt = bg.find_o3_option_by_slot_index(
                persisted_beat,
                int(slot_index),
                video_path=req_video_path,
            )
            if isinstance(opt, dict):
                baked = str(opt.get("kling_o3_baked_path") or "").strip() or None
        if not baked:
            baked = str(persisted_beat.get("kling_o3_baked_path") or "").strip() or None
        if not baked:
            return None
        return _files_url_for_disk_path(Path(baked), event_dir)

    def _trim_preview_url(work_beat: dict) -> str | None:
        vp = work_beat.get("kling_o3_video_path") or ""
        if not vp or not Path(vp).is_file():
            return None
        event_dir = Path(h.app.event_dir)
        if not event_dir.is_absolute():
            event_dir = _data_root(h) / event_dir
        dest = bg.kling_o3_ui_trim_preview_path(beat_id, event_dir, work_beat)
        try:
            if bg.beat_has_o3_sidecar_cut(work_beat):
                bg.materialize_o3_cut_out_clip(work_beat, dest, source_path=Path(vp))
            elif bg.kling_o3_trim_is_active(work_beat):
                bg.materialize_kling_o3_trimmed_clip(work_beat, dest, source_path=Path(vp))
            else:
                bg.copy_file_durable(vp, dest)
        except Exception as exc:
            print(f"[bg_o3_trim] preview materialize failed for {beat_id}: {exc}", flush=True)
            return None
        if not dest.is_file():
            return None
        return _files_url_for_disk_path(dest, event_dir)

    result: dict = {}

    def _reject_unchanged_trim_preview(
        trim_start_val: float,
        trim_back_val: float | None,
        payload: dict,
    ) -> None:
        raw = payload.get("raw_duration_s")
        eff = payload.get("effective_duration_s")
        if not bg.o3_trim_shortening_requested(trim_start_val, trim_back_val):
            return
        if bg.o3_trim_effective_is_shorter(float(raw or 0), eff):
            return
        raise ValueError(
            "Preview would be full clip — adjust handles and Apply Cut first",
        )

    def _apply_cut_to_work_beat(work_beat: dict) -> dict | None:
        """Apply per-option cut to an in-memory beat copy. Returns error response or None."""
        nonlocal result
        bg.refresh_o3_ui_slot_layout(work_beat)
        if body.get("clear"):
            if slot_index is None:
                return h._send_error_v59(
                    400,
                    error_code="MISSING_SLOT_INDEX",
                    error_message="slot_index required to clear per-option cut",
                    retry_safe=False,
                )
            bg.clear_o3_option_cut(
                work_beat,
                slot_index=int(slot_index),
                video_path=req_video_path,
            )
            result = {
                "cut_start_s": 0.0,
                "cut_end_s": 0.0,
                "effective_duration_s": None,
                "slot_index": int(slot_index),
            }
            return None
        if slot_index is None:
            return h._send_error_v59(
                400,
                error_code="MISSING_SLOT_INDEX",
                error_message="slot_index required for per-option cut",
                retry_safe=False,
            )
        try:
            cut_start = float(raw_cut_start or 0)
            cut_end = float(raw_cut_end or 0)
        except (TypeError, ValueError):
            return h._send_error_v59(
                400,
                error_code="INVALID_CUT",
                error_message="cut_start_s/cut_end_s must be numeric",
                retry_safe=False,
            )
        try:
            result = bg.set_o3_option_cut(
                work_beat,
                slot_index=int(slot_index),
                cut_start_s=cut_start,
                cut_end_s=cut_end,
                video_path=req_video_path,
            )
        except ValueError as exc:
            _bg_o3_trim_audit(
                h,
                "FAIL",
                beat_id=str(beat_id),
                preview_only=preview_only,
                error_code="CUT_VALIDATION",
                error_message=str(exc),
                slot_index=slot_index,
                req_video=Path(req_video_path).name if req_video_path else None,
            )
            return h._send_error_v59(
                400,
                error_code="CUT_VALIDATION",
                error_message=str(exc),
                retry_safe=False,
            )
        opt_for_preview = bg.find_o3_option_by_slot_index(
            work_beat,
            int(slot_index),
            video_path=req_video_path,
        )
        if isinstance(opt_for_preview, dict) and opt_for_preview.get("video_path"):
            work_beat["kling_o3_video_path"] = opt_for_preview["video_path"]
            bg.mirror_beat_cut_from_option(work_beat, opt_for_preview)
        return None

    def _apply_option_trim_to_work_beat(work_beat: dict) -> dict | None:
        """Apply per-option front/back trim (start + end crop) on an in-memory beat copy."""
        nonlocal result
        bg.refresh_o3_ui_slot_layout(work_beat)
        if body.get("clear"):
            if slot_index is None:
                return h._send_error_v59(
                    400,
                    error_code="MISSING_SLOT_INDEX",
                    error_message="slot_index required to clear per-option trim",
                    retry_safe=False,
                )
            try:
                result = bg.restore_o3_option_untrimmed_video(
                    work_beat,
                    slot_index=int(slot_index),
                    video_path=req_video_path,
                )
            except ValueError as exc:
                _bg_o3_trim_audit(
                    h,
                    "FAIL",
                    beat_id=str(beat_id),
                    preview_only=preview_only,
                    error_code="TRIM_RESTORE_FAILED",
                    error_message=str(exc),
                    slot_index=slot_index,
                    req_video=Path(req_video_path).name if req_video_path else None,
                )
                return h._send_error_v59(
                    400,
                    error_code="TRIM_RESTORE_FAILED",
                    error_message=str(exc),
                    retry_safe=False,
                )
            bg.invalidate_kling_o3_trim_scratch(beat_id, Path(h.app.event_dir))
            return None
        if slot_index is None:
            return h._send_error_v59(
                400,
                error_code="MISSING_SLOT_INDEX",
                error_message="slot_index required for per-option trim",
                retry_safe=False,
            )
        if raw_trim_start is None:
            raw_trim_start_local = body.get("trim_in", 0)
        else:
            raw_trim_start_local = raw_trim_start
        try:
            trim_start = float(raw_trim_start_local or 0)
            trim_back = None if raw_trim_back is None else float(raw_trim_back)
        except (TypeError, ValueError):
            return h._send_error_v59(
                400,
                error_code="INVALID_TRIM",
                error_message="trim_start/trim_back must be numeric",
                retry_safe=False,
            )
        try:
            result = bg.set_o3_option_trim(
                work_beat,
                slot_index=int(slot_index),
                trim_start=trim_start,
                trim_back=trim_back,
                video_path=req_video_path,
            )
        except ValueError as exc:
            _bg_o3_trim_audit(
                h,
                "FAIL",
                beat_id=str(beat_id),
                preview_only=preview_only,
                error_code="TRIM_VALIDATION",
                error_message=str(exc),
                slot_index=slot_index,
                req_video=Path(req_video_path).name if req_video_path else None,
                trim_start=trim_start,
                trim_back=trim_back,
            )
            return h._send_error_v59(
                400,
                error_code="TRIM_VALIDATION",
                error_message=str(exc),
                retry_safe=False,
            )
        opt_for_preview = bg.find_o3_option_by_slot_index(
            work_beat,
            int(slot_index),
            video_path=req_video_path,
        )
        if isinstance(opt_for_preview, dict) and opt_for_preview.get("video_path"):
            work_beat["kling_o3_video_path"] = opt_for_preview["video_path"]
            bg.mirror_beat_trim_from_option(work_beat, opt_for_preview)
        return None

    # Preview path: snapshot read + ffmpeg only — must not wait on sidecar write lock.
    if preview_only:
        sidecar = bg.read_sidecar_for_poll_snapshot(lock_timeout_s=5)
        sidecar = bg._migrate_sidecar(sidecar)
        _, beat = bg.find_beat(sidecar, beat_id)
        if not beat:
            return h._send_error_v59(
                404,
                error_code="BEAT_NOT_FOUND",
                error_message=f"beat {beat_id} not found",
                retry_safe=False,
            )
        work_beat = copy.deepcopy(beat)
        if use_cut:
            err = _apply_cut_to_work_beat(work_beat)
            if err is not None:
                return err
        elif use_option_trim:
            err = _apply_option_trim_to_work_beat(work_beat)
            if err is not None:
                return err
        elif body.get("clear"):
            bg.clear_kling_o3_beat_trim(work_beat)
            bg.clear_o3_cut_fields(work_beat)
            result = {
                "trim_start": 0.0,
                "trim_back": None,
                "effective_duration_s": None,
            }
        else:
            raw_trim_start = body.get("trim_start")
            if raw_trim_start is None:
                raw_trim_start = body.get("trim_in", 0)
            raw_trim_back = body.get("trim_back")
            try:
                trim_start = float(raw_trim_start or 0)
                trim_back = None if raw_trim_back is None else float(raw_trim_back)
            except (TypeError, ValueError):
                return h._send_error_v59(
                    400,
                    error_code="INVALID_TRIM",
                    error_message="trim_start/trim_back must be numeric",
                    retry_safe=False,
                )
            try:
                result = bg.set_kling_o3_beat_trim(
                    work_beat,
                    trim_start=trim_start,
                    trim_back=trim_back,
                )
            except ValueError as exc:
                _bg_o3_trim_audit(
                    h,
                    "FAIL",
                    beat_id=str(beat_id),
                    preview_only=True,
                    error_code="TRIM_VALIDATION",
                    error_message=str(exc),
                    trim_start=trim_start,
                    trim_back=trim_back,
                )
                return h._send_error_v59(
                    400,
                    error_code="TRIM_VALIDATION",
                    error_message=str(exc),
                    retry_safe=False,
                )
        preview_url = _trim_preview_url(work_beat)
        if preview_url:
            result["preview_video_url"] = preview_url
        try:
            if use_option_trim and not body.get("clear"):
                _reject_unchanged_trim_preview(
                    float(raw_trim_start or body.get("trim_in") or 0),
                    None if raw_trim_back is None else float(raw_trim_back),
                    result,
                )
            elif not use_cut and not body.get("clear"):
                ts = float(body.get("trim_start") or body.get("trim_in") or 0)
                tb = body.get("trim_back")
                tb_val = None if tb is None else float(tb)
                _reject_unchanged_trim_preview(ts, tb_val, result)
        except ValueError as exc:
            _bg_o3_trim_audit(
                h,
                "FAIL",
                beat_id=str(beat_id),
                preview_only=True,
                error_code="TRIM_PREVIEW_UNCHANGED",
                error_message=str(exc),
                slot_index=slot_index,
                trim_start=raw_trim_start,
                trim_back=raw_trim_back,
                raw_duration_s=result.get("raw_duration_s"),
                effective_duration_s=result.get("effective_duration_s"),
            )
            return h._send_error_v59(
                400,
                error_code="TRIM_PREVIEW_UNCHANGED",
                error_message=str(exc),
                retry_safe=False,
            )
        _bg_o3_trim_audit(
            h,
            "PREVIEW_OK",
            beat_id=str(beat_id),
            preview_only=True,
            mode=trim_mode,
            slot_index=slot_index,
            trim_start=result.get("trim_start"),
            trim_back=result.get("trim_back"),
            raw_duration_s=result.get("raw_duration_s"),
            effective_duration_s=result.get("effective_duration_s"),
            has_preview_url=bool(result.get("preview_video_url")),
        )
        return h._send_json(200, {"ok": True, "beat_id": beat_id, **result})

    from server_handlers.milestone_scope import production_bg_scope_lock, rebind_bg_paths_from_app

    try:
        with production_bg_scope_lock():
            rebind_bg_paths_from_app(h.app)
            sidecar = bg.read_sidecar_for_poll_snapshot(lock_timeout_s=10)
        sidecar = bg._migrate_sidecar(sidecar)
        _, beat = bg.find_beat(sidecar, beat_id)
        if not beat:
            return h._send_error_v59(
                404,
                error_code="BEAT_NOT_FOUND",
                error_message=f"beat {beat_id} not found",
                retry_safe=False,
            )
        before_beat_export = {
            "kling_o3_video_path": beat.get("kling_o3_video_path"),
            "kling_o3_selected_option_key": beat.get("kling_o3_selected_option_key"),
        }
        work_beat = copy.deepcopy(beat)
        if use_cut:
            bg.refresh_o3_ui_slot_layout(work_beat)
            if not preview_only:
                bg.refresh_o3_ui_slot_layout(beat)
            if body.get("clear"):
                if slot_index is None:
                    return h._send_error_v59(
                        400,
                        error_code="MISSING_SLOT_INDEX",
                        error_message="slot_index required to clear per-option cut",
                        retry_safe=False,
                    )
                bg.clear_o3_option_cut(
                    work_beat,
                    slot_index=int(slot_index),
                    video_path=req_video_path,
                )
                if not preview_only:
                    bg.clear_o3_option_cut(
                        beat,
                        slot_index=int(slot_index),
                        video_path=req_video_path,
                    )
                    bg.invalidate_kling_o3_trim_scratch(beat_id, Path(h.app.event_dir))
                result = {
                    "cut_start_s": 0.0,
                    "cut_end_s": 0.0,
                    "effective_duration_s": None,
                    "slot_index": int(slot_index),
                }
            else:
                if slot_index is None:
                    return h._send_error_v59(
                        400,
                        error_code="MISSING_SLOT_INDEX",
                        error_message="slot_index required for per-option cut",
                        retry_safe=False,
                    )
                try:
                    cut_start = float(raw_cut_start or 0)
                    cut_end = float(raw_cut_end or 0)
                except (TypeError, ValueError):
                    return h._send_error_v59(
                        400,
                        error_code="INVALID_CUT",
                        error_message="cut_start_s/cut_end_s must be numeric",
                        retry_safe=False,
                    )
                try:
                    result = bg.set_o3_option_cut(
                        work_beat,
                        slot_index=int(slot_index),
                        cut_start_s=cut_start,
                        cut_end_s=cut_end,
                        video_path=req_video_path,
                    )
                except ValueError as exc:
                    _bg_o3_trim_audit(
                        h,
                        "FAIL",
                        beat_id=str(beat_id),
                        preview_only=preview_only,
                        error_code="CUT_VALIDATION",
                        error_message=str(exc),
                        slot_index=slot_index,
                        req_video=Path(req_video_path).name if req_video_path else None,
                    )
                    return h._send_error_v59(
                        400,
                        error_code="CUT_VALIDATION",
                        error_message=str(exc),
                        retry_safe=False,
                    )
                opt_for_preview = bg.find_o3_option_by_slot_index(
                    work_beat,
                    int(slot_index),
                    video_path=req_video_path,
                )
                if isinstance(opt_for_preview, dict) and opt_for_preview.get("video_path"):
                    work_beat["kling_o3_video_path"] = opt_for_preview["video_path"]
                    bg.mirror_beat_cut_from_option(work_beat, opt_for_preview)
                if not preview_only:
                    opt = bg.find_o3_option_by_slot_index(
                        beat,
                        int(slot_index),
                        video_path=req_video_path,
                    )
                    src_opt = bg.find_o3_option_by_slot_index(
                        work_beat,
                        int(slot_index),
                        video_path=req_video_path,
                    )
                    if isinstance(opt, dict) and isinstance(src_opt, dict):
                        opt["cut_start_s"] = src_opt.get("cut_start_s")
                        opt["cut_end_s"] = src_opt.get("cut_end_s")
                    bg.hydrate_beat_cut_from_active_option(beat)
                    bg.prune_stale_kling_o3_trim_scratch(
                        beat_id,
                        Path(h.app.event_dir),
                        beat,
                    )
        elif use_option_trim:
            bg.refresh_o3_ui_slot_layout(work_beat)
            bg.refresh_o3_ui_slot_layout(beat)
            if not preview_only and body.get("clear"):
                try:
                    result = bg.restore_o3_option_untrimmed_video(
                        beat,
                        slot_index=int(slot_index),
                        video_path=req_video_path,
                    )
                except ValueError as exc:
                    return h._send_error_v59(
                        400,
                        error_code="TRIM_RESTORE_FAILED",
                        error_message=str(exc),
                        retry_safe=False,
                    )
                bg.invalidate_kling_o3_trim_scratch(beat_id, Path(h.app.event_dir))
            else:
                err = _apply_option_trim_to_work_beat(work_beat)
                if err is not None:
                    return err
                if not preview_only:
                    opt = bg.find_o3_option_by_slot_index(
                        beat,
                        int(slot_index),
                        video_path=req_video_path,
                    )
                    src_opt = bg.find_o3_option_by_slot_index(
                        work_beat,
                        int(slot_index),
                        video_path=req_video_path,
                    )
                    if isinstance(opt, dict) and isinstance(src_opt, dict):
                        if src_opt.get("trim_start_s") is not None:
                            opt["trim_start_s"] = src_opt.get("trim_start_s")
                        else:
                            opt.pop("trim_start_s", None)
                        if src_opt.get("trim_back_s") is not None:
                            opt["trim_back_s"] = src_opt.get("trim_back_s")
                        else:
                            opt.pop("trim_back_s", None)
                        bg.clear_o3_cut_fields(opt)
                    # Mirror trim from the slot being edited — not hydrate from active,
                    # which can resolve to a different row via o3_untrimmed_video_path.
                    if isinstance(opt, dict) and bg.option_has_o3_trim(opt):
                        bg.mirror_beat_trim_from_option(beat, opt)
                    else:
                        bg.hydrate_beat_trim_from_active_option(beat)
                    bg.prune_stale_kling_o3_trim_scratch(
                        beat_id,
                        Path(h.app.event_dir),
                        beat,
                    )
                    effective_req_video = req_video_path
                    if not body.get("clear"):
                        if (
                            bg.beat_is_still_insert(beat)
                            and isinstance(opt, dict)
                            and bg.option_has_o3_trim(opt)
                        ):
                            try:
                                slot_vp = str(opt.get("video_path") or "").strip()
                                bake_si = bg.bake_still_insert_trim_into_clip(
                                    beat,
                                    source_path=slot_vp or None,
                                )
                                result["trim_baked"] = bool(bake_si.get("baked"))
                                if bake_si.get("video_path"):
                                    result["video_path"] = bake_si["video_path"]
                                    effective_req_video = str(bake_si["video_path"])
                                    result["trim_start"] = 0.0
                                    result["trim_back"] = None
                                    if bake_si.get("baked"):
                                        raw_dur = bg._ffprobe_duration(Path(bake_si["video_path"]))
                                        if raw_dur > 0:
                                            result["raw_duration_s"] = round(raw_dur, 3)
                                            result["effective_duration_s"] = round(raw_dur, 3)
                            except Exception as exc:
                                _bg_o3_trim_audit(
                                    h,
                                    "FAIL",
                                    beat_id=str(beat_id),
                                    preview_only=preview_only,
                                    error_code="STILL_TRIM_BAKE_FAILED",
                                    error_message=str(exc),
                                    slot_index=slot_index,
                                    req_video=Path(req_video_path).name if req_video_path else None,
                                )
                                return h._send_error_v59(
                                    500,
                                    error_code="STILL_TRIM_BAKE_FAILED",
                                    error_message=str(exc),
                                    retry_safe=True,
                                )
                        try:
                            bake = bg.bake_o3_active_export_clip(
                                beat,
                                Path(h.app.event_dir),
                                slot_index=int(slot_index),
                                video_path=effective_req_video,
                            )
                            result["export_baked"] = bool(bake.get("baked"))
                            if bake.get("baked_path"):
                                result["baked_path"] = bake["baked_path"]
                            opt_bake = bg.find_o3_option_by_slot_index(
                                beat,
                                int(slot_index),
                                video_path=effective_req_video,
                            )
                            if isinstance(opt_bake, dict):
                                if bake.get("baked_path"):
                                    opt_bake["kling_o3_baked_path"] = bake["baked_path"]
                                    opt_bake["kling_o3_baked_token"] = bake.get("baked_token")
                                else:
                                    bg.clear_o3_baked_fields(opt_bake)
                        except Exception as exc:
                            _bg_o3_trim_audit(
                                h,
                                "FAIL",
                                beat_id=str(beat_id),
                                preview_only=preview_only,
                                error_code="O3_TRIM_BAKE_FAILED",
                                error_message=str(exc),
                                slot_index=slot_index,
                                req_video=Path(effective_req_video).name if effective_req_video else None,
                            )
                            return h._send_error_v59(
                                500,
                                error_code="O3_TRIM_BAKE_FAILED",
                                error_message=str(exc),
                                retry_safe=True,
                            )
        elif body.get("clear"):
            bg.clear_kling_o3_beat_trim(work_beat)
            if not preview_only:
                bg.clear_kling_o3_beat_trim(beat)
                bg.clear_o3_cut_fields(beat)
                bg.invalidate_kling_o3_trim_scratch(beat_id, Path(h.app.event_dir))
            result = {
                "trim_start": 0.0,
                "trim_back": None,
                "effective_duration_s": None,
            }
        else:
            raw_trim_start = body.get("trim_start")
            if raw_trim_start is None:
                raw_trim_start = body.get("trim_in", 0)
            raw_trim_back = body.get("trim_back")
            try:
                trim_start = float(raw_trim_start or 0)
                trim_back = None if raw_trim_back is None else float(raw_trim_back)
            except (TypeError, ValueError):
                return h._send_error_v59(
                    400,
                    error_code="INVALID_TRIM",
                    error_message="trim_start/trim_back must be numeric",
                    retry_safe=False,
                )
            if trim_start < 0 or (trim_back is not None and trim_back < 0):
                return h._send_error_v59(
                    400,
                    error_code="INVALID_TRIM_RANGE",
                    error_message="trim_start and trim_back must be >= 0",
                    retry_safe=False,
                )
            try:
                result = bg.set_kling_o3_beat_trim(
                    work_beat,
                    trim_start=trim_start,
                    trim_back=trim_back,
                )
            except ValueError as exc:
                _bg_o3_trim_audit(
                    h,
                    "FAIL",
                    beat_id=str(beat_id),
                    preview_only=preview_only,
                    error_code="TRIM_VALIDATION",
                    error_message=str(exc),
                    trim_start=trim_start,
                    trim_back=trim_back,
                )
                return h._send_error_v59(
                    400,
                    error_code="TRIM_VALIDATION",
                    error_message=str(exc),
                    retry_safe=False,
                )
            if not preview_only:
                beat["kling_o3_trim_start"] = work_beat.get("kling_o3_trim_start")
                beat["kling_o3_trim_back"] = work_beat.get("kling_o3_trim_back")
                beat.pop("kling_o3_trim_end", None)
                vp_trim = str(beat.get("kling_o3_video_path") or "").strip()
                opt_trim = bg.find_o3_option_by_video_path(beat, vp_trim) if vp_trim else None
                if isinstance(opt_trim, dict):
                    bg.mirror_option_trim_from_beat(beat, opt_trim)
                bg.prune_stale_kling_o3_trim_scratch(
                    beat_id,
                    Path(h.app.event_dir),
                    beat,
                )
        if not preview_only:
            if (
                not body.get("clear")
                and not use_cut
                and bg.beat_is_still_insert(beat)
                and bg.still_insert_trim_pending(beat)
                and not result.get("trim_baked")
            ):
                try:
                    bake = bg.bake_still_insert_trim_into_clip(beat)
                    result["trim_baked"] = bool(bake.get("baked"))
                    if bake.get("video_path"):
                        result["video_path"] = bake["video_path"]
                        result["trim_start"] = 0.0
                        result["trim_back"] = None
                except Exception as exc:
                    return h._send_error_v59(
                        500,
                        error_code="STILL_TRIM_BAKE_FAILED",
                        error_message=str(exc),
                        retry_safe=True,
                    )
            beat_commit = copy.deepcopy(beat)

            def _commit_trim(b: dict, _sc: dict) -> None:
                b.clear()
                b.update(beat_commit)

            ok, _ = bg.update_beat_locked(
                beat_id,
                _commit_trim,
                caller="handle_bg_kling_o3_trim",
            )
            if not ok:
                return h._send_error_v59(
                    404,
                    error_code="BEAT_NOT_FOUND",
                    error_message=f"beat {beat_id} not found",
                    retry_safe=False,
                )
            from bg_o3_stitch_invalidation import (  # noqa: PLC0415
                invalidate_stitch_slot_for_bg_o3_selection_change,
            )

            for line in invalidate_stitch_slot_for_bg_o3_selection_change(
                h,
                beat_id=str(beat_id),
                sidecar=sidecar,
                before_beat=before_beat_export,
                after_beat=beat_commit,
                reason="bg_o3_trim_bake",
            ):
                print(f"[bg_o3_stitch_invalidate] {line}", flush=True)
    except TimeoutError as exc:
        _bg_o3_trim_audit(
            h,
            "FAIL",
            beat_id=str(beat_id),
            preview_only=preview_only,
            error_code="SIDECAR_LOCK_TIMEOUT",
            error_message=str(exc) or "sidecar lock busy",
        )
        return h._send_error_v59(
            503,
            error_code="SIDECAR_LOCK_TIMEOUT",
            error_message=str(exc) or "sidecar lock busy — retry shortly",
            retry_safe=True,
        )
    except OSError as exc:
        if bg.sidecar_io_transient(exc):
            return h._send_error_v59(
                503,
                error_code="SIDECAR_IO_TRANSIENT",
                error_message=str(exc) or "Dropbox sync blocked trim save — retry shortly",
                retry_safe=True,
                extra={"errno": getattr(exc, "errno", None)},
            )
        raise
    preview_url: str | None = None
    if preview_only or body.get("clear"):
        preview_url = _trim_preview_url(work_beat)
    else:
        preview_url = _trim_baked_preview_url(beat) or _trim_preview_url(work_beat)
    if preview_url:
        result["preview_video_url"] = preview_url
    elif (
        not preview_only
        and not body.get("clear")
        and (
            bg.kling_o3_trim_is_active(work_beat)
            or bg.beat_has_o3_sidecar_cut(work_beat)
        )
    ):
        return h._send_error_v59(
            500,
            error_code="O3_TRIM_PREVIEW_FAILED",
            error_message=(
                "Trim saved but preview clip could not be built — "
                "wait a moment and press Retry or Preview Cut"
            ),
            retry_safe=True,
            extra={"beat_id": beat_id},
        )
    _bg_o3_trim_audit(
        h,
        "APPLY_OK" if not preview_only else "PREVIEW_OK",
        beat_id=str(beat_id),
        preview_only=preview_only,
        mode=trim_mode,
        slot_index=slot_index,
        trim_start=result.get("trim_start"),
        trim_back=result.get("trim_back"),
        raw_duration_s=result.get("raw_duration_s"),
        effective_duration_s=result.get("effective_duration_s"),
        trim_baked=result.get("trim_baked"),
        export_baked=result.get("export_baked"),
        has_preview_url=bool(result.get("preview_video_url")),
    )
    return h._send_json(200, {"ok": True, "beat_id": beat_id, **result})


def _resolve_o3_select_option(
    beat: dict,
    beat_id: str,
    option_key: str,
) -> tuple[dict | None, list, str | None]:
    """Resolve O3 gallery option + on-disk path for select-o3-video (no sidecar lock)."""
    from o3_gallery_option_identity import (  # noqa: PLC0415
        O3GalleryOptionAmbiguousError,
        normalize_o3_gallery_options,
        resolve_o3_gallery_option_or_path,
    )

    options = [o for o in (beat.get("kling_o3_options") or []) if isinstance(o, dict)]
    for line in normalize_o3_gallery_options(beat):
        print(f"[bg_select_o3] {line}", flush=True)
    options = [o for o in (beat.get("kling_o3_options") or []) if isinstance(o, dict)]
    try:
        opt, video_path = resolve_o3_gallery_option_or_path(beat, option_key)
    except O3GalleryOptionAmbiguousError as exc:
        print(f"[bg_select_o3] gallery authority blocked: {exc}", flush=True)
        return None, options, None
    return opt, options, video_path


def _repair_o3_select_before_resolve(h, beat_id: str, option_key: str) -> None:
    """Reconcile milestone clip dirs and upsert a missing gallery row before select rejects."""
    bg = _bg_module()
    candidates = _o3_job_event_dir_candidates(h, beat_id)
    now = datetime.now(timezone.utc).isoformat()

    def _repair(b: dict, _sc: dict) -> None:
        if str(b.get("beat_id") or "") != str(beat_id):
            return
        for ev in candidates:
            bg.reconcile_o3_disk_deliveries_for_beat(b, ev)
        options = [o for o in (b.get("kling_o3_options") or []) if isinstance(o, dict)]
        if any(o.get("key") == option_key for o in options):
            for o in options:
                if o.get("key") != option_key:
                    continue
                vp = str(o.get("video_path") or "")
                if vp and Path(vp).is_file():
                    return
                found = bg.find_o3_video_path_for_option_key(beat_id, option_key, candidates)
                if found:
                    o["video_path"] = str(found.resolve())
                return
        found = bg.find_o3_video_path_for_option_key(beat_id, option_key, candidates)
        if not found:
            return
        vp = str(found.resolve())
        path_l = vp.lower()
        if "_pov_" in path_l:
            label = "POV wand wiper (O3 i2v)"
            source = "pov_wand_wiper"
        elif "_still_insert_" in path_l:
            label = "still insert clip"
            source = "still_insert_ken_burns"
        else:
            label = bg._canonical_o3_option_label(vp)
            source = "o3_select_disk_repair"
        slot = 0
        for idx, opt in enumerate(bg.normalize_kling_o3_option_slots(b)):
            if opt is None:
                slot = idx
                break
        bg.assign_kling_o3_option_to_slot(
            b,
            slot,
            video_path=vp,
            label=label,
            source=source,
            now=now,
            make_active=False,
        )

    try:
        ok, _beat = bg.update_beat_locked(beat_id, _repair)
        if not ok:
            print(f"[bg_select_o3] gallery repair skipped — beat {beat_id} not found", flush=True)
    except OSError as exc:
        print(f"[bg_select_o3] gallery repair I/O failed for {beat_id}: {exc}", flush=True)


def _apply_still_draft_pointer(
    beat: dict,
    *,
    beat_id: str,
    option_key: str,
    options: list,
    video_path: str,
    sidecar: dict,
    opt: dict | None,
    event_dir: Path,
) -> None:
    """Still+TTS draft — switch active clip for preview/trim without stitch approve."""
    bg = _bg_module()
    now = datetime.now(timezone.utc).isoformat()
    beat["kling_o3_video_path"] = video_path
    beat["kling_o3_status"] = "still_rendered"
    beat["status"] = "draft"
    beat["kling_o3_selected_option_key"] = option_key
    beat["kling_o3_selected_at"] = now
    beat.pop("kling_o3_still_stitch_approved", None)
    beat.pop("kling_o3_still_stitch_approved_at", None)
    bg.heal_invalid_o3_cut_all_options(beat)
    bg.hydrate_beat_cut_from_active_option(beat)
    from o3_gallery_option_identity import gallery_option_key_for_path, normalize_o3_gallery_options  # noqa: PLC0415

    for o in options:
        vp = str(o.get("video_path") or "").strip()
        if vp:
            o["key"] = gallery_option_key_for_path(beat_id, vp, o)
        o["active"] = (o.get("key") == option_key or o.get("video_path") == video_path)
    beat["kling_o3_options"] = options
    for line in normalize_o3_gallery_options(beat):
        print(f"[bg_still_draft] {line}", flush=True)
    bg.sync_o3_selection_pipeline_fields(beat, sidecar, option=opt)
    bg.persist_o3_disk_enrich_on_beat(beat, event_dir)


def _apply_o3_video_selection(
    beat: dict,
    *,
    beat_id: str,
    option_key: str,
    opt: dict | None,
    options: list,
    video_path: str,
    sidecar: dict,
    event_dir: Path,
) -> None:
    """Mutate one beat for select-o3-video — caller uses update_beat_locked."""
    bg = _bg_module()
    now = datetime.now(timezone.utc).isoformat()
    from kling_stitch_readiness import finalize_kling_delivery_clip  # noqa: PLC0415

    if bg.beat_is_still_insert(beat):
        finalize_kling_delivery_clip(beat, video_path, still_insert=True)
        beat["kling_o3_still_stitch_approved"] = True
        beat["kling_o3_still_stitch_approved_at"] = now
    else:
        finalize_kling_delivery_clip(beat, video_path, still_insert=False)
    beat["kling_o3_selected_option_key"] = option_key
    beat["kling_o3_selected_at"] = now
    bg.heal_invalid_o3_cut_all_options(beat)
    bg.hydrate_beat_cut_from_active_option(beat)
    bg.hydrate_beat_trim_from_active_option(beat)
    bg.invalidate_kling_o3_trim_scratch(beat_id, event_dir)
    from o3_gallery_option_identity import gallery_option_key_for_path, normalize_o3_gallery_options  # noqa: PLC0415

    for o in options:
        vp = str(o.get("video_path") or "").strip()
        if vp:
            o["key"] = gallery_option_key_for_path(beat_id, vp, o)
        o["active"] = (o.get("key") == option_key or o.get("video_path") == video_path)
    beat["kling_o3_options"] = options
    for line in normalize_o3_gallery_options(beat):
        print(f"[bg_select_o3] {line}", flush=True)
    bg.sync_o3_selection_pipeline_fields(beat, sidecar, option=opt)
    bg.persist_o3_disk_enrich_on_beat(beat, event_dir)


def handle_bg_import_delivery_clip(h, body: dict) -> None:
    """POST /api/bg/import-delivery-clip — single-writer agent path for shipping beats.

    Body: beat_id, delivery_mp4_path, slot_index?, label?, source?, make_active?,
    generation?, scope_event_id?
    """
    from beatgen_scope import BeatGenScopeError, scope_from_current_globals  # noqa: PLC0415

    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return
    beat_id = (body.get("beat_id") or "").strip()
    delivery_path = (body.get("delivery_mp4_path") or body.get("delivery_mp4") or "").strip()
    if not beat_id or not delivery_path:
        return h._send_error_v59(
            400,
            error_code="MISSING_IMPORT_FIELDS",
            error_message="beat_id and delivery_mp4_path required",
            retry_safe=False,
        )
    src = Path(delivery_path).expanduser()
    if not src.is_file():
        return h._send_error_v59(
            404,
            error_code="DELIVERY_MP4_NOT_FOUND",
            error_message=f"delivery mp4 not found: {delivery_path}",
            retry_safe=False,
        )
    try:
        slot_index = int(body.get("slot_index") if body.get("slot_index") is not None else 0)
    except (TypeError, ValueError):
        slot_index = 0
    slot_index = max(0, min(2, slot_index))
    label = str(body.get("label") or "imported delivery clip").strip()
    source = (body.get("source") or "").strip() or None
    make_active = body.get("make_active", True)
    if isinstance(make_active, str):
        make_active = make_active.strip().lower() in ("1", "true", "yes")
    generation_raw = body.get("generation")
    generation = int(generation_raw) if generation_raw is not None else None

    bg = _bg_module()
    event_dir = _o3_job_event_dir(h, beat_id)
    scope = scope_from_current_globals(bg)
    try:
        ok, beat = bg.import_delivery_clip_to_beat(
            beat_id=beat_id,
            delivery_mp4=src,
            slot_index=slot_index,
            label=label,
            source=source,
            make_active=bool(make_active),
            generation=generation,
            event_dir=event_dir,
            scope=scope,
            caller="handle_bg_import_delivery_clip",
        )
    except BeatGenScopeError as exc:
        return h._send_error_v59(
            409,
            error_code=getattr(exc, "error_code", "BEATGEN_SCOPE_MISMATCH"),
            error_message=str(exc),
            retry_safe=False,
            extra=getattr(exc, "extra", {}),
        )
    except FileNotFoundError as exc:
        return h._send_error_v59(
            404,
            error_code="DELIVERY_MP4_NOT_FOUND",
            error_message=str(exc),
            retry_safe=False,
        )
    if not ok or not beat:
        return h._send_error_v59(
            404,
            error_code="BEAT_NOT_FOUND",
            error_message=f"beat {beat_id} not found",
            retry_safe=False,
        )
    h._send_json(
        200,
        {
            "ok": True,
            "beat_id": beat_id,
            "beat": beat,
            "slot_index": slot_index,
            "video_path": beat.get("kling_o3_video_path"),
            "kling_o3_status": beat.get("kling_o3_status"),
        },
    )


def handle_bg_select_o3_video(h, body: dict) -> None:
    """POST /api/bg/select-o3-video {beat_id, option_key}.

    Non-destructive O3 resend support: each generated O3 lipsync is stored in
    beat.kling_o3_options. Selecting one changes only the active pointer; it
    does not delete the other generated clips.
    """
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return
    beat_id = body.get("beat_id")
    option_key = body.get("option_key")
    if not beat_id or not option_key:
        return h._send_error_v59(
            400,
            error_code="MISSING_BEAT_ID_OR_OPTION_KEY",
            error_message="beat_id and option_key required",
            retry_safe=False,
        )
    bg = _bg_module()
    sidecar_probe = bg.read_sidecar_for_poll_snapshot(lock_timeout_s=5)
    sidecar_probe = bg._migrate_sidecar(sidecar_probe)
    _, beat_probe = bg.find_beat(sidecar_probe, beat_id)
    if not beat_probe:
        return h._send_error_v59(
            404,
            error_code="BEAT_NOT_FOUND",
            error_message=f"beat {beat_id} not found",
            retry_safe=False,
        )
    opt_probe, _options_probe, video_path = _resolve_o3_select_option(
        beat_probe, str(beat_id), str(option_key)
    )
    if not video_path or not Path(video_path).is_file():
        _repair_o3_select_before_resolve(h, str(beat_id), str(option_key))
        sidecar_probe = bg.read_sidecar_for_poll_snapshot(lock_timeout_s=5)
        sidecar_probe = bg._migrate_sidecar(sidecar_probe)
        _, beat_probe = bg.find_beat(sidecar_probe, beat_id)
        if beat_probe:
            opt_probe, _options_probe, video_path = _resolve_o3_select_option(
                beat_probe, str(beat_id), str(option_key)
            )
    if not video_path or not Path(video_path).is_file():
        return h._send_error_v59(
            404,
            error_code="O3_VIDEO_OPTION_NOT_FOUND",
            error_message=f"O3 video option {option_key!r} missing on disk",
            retry_safe=False,
        )
    event_dir = _o3_job_event_dir(h, str(beat_id))
    pipeline_mismatch = False
    active_clip_pipeline = None
    sidecar = sidecar_probe
    beat = beat_probe
    raw_still_approve = body.get("still_approve")
    if raw_still_approve is None:
        still_approve = not bg.beat_is_still_insert(beat_probe)
    elif isinstance(raw_still_approve, str):
        still_approve = raw_still_approve.strip().lower() in ("1", "true", "yes")
    else:
        still_approve = bool(raw_still_approve)
    try:

        def _select(b: dict, sidecar: dict) -> None:
            nonlocal video_path, pipeline_mismatch, active_clip_pipeline
            before_beat = {
                "kling_o3_video_path": b.get("kling_o3_video_path"),
                "kling_o3_selected_option_key": b.get("kling_o3_selected_option_key"),
            }
            opt, options, vp = _resolve_o3_select_option(
                b, str(beat_id), str(option_key),
            )
            if not vp or not Path(vp).is_file():
                raise _BgSidecarAbort(
                    status=404,
                    error_code="O3_VIDEO_OPTION_NOT_FOUND",
                    error_message=f"O3 video option {option_key!r} missing on disk",
                    retry_safe=False,
                )
            video_path = str(vp)
            if bg.beat_is_still_insert(b) and not still_approve:
                _apply_still_draft_pointer(
                    b,
                    beat_id=str(beat_id),
                    option_key=str(option_key),
                    opt=opt,
                    options=options,
                    video_path=video_path,
                    sidecar=sidecar,
                    event_dir=event_dir,
                )
            else:
                _apply_o3_video_selection(
                    b,
                    beat_id=str(beat_id),
                    option_key=str(option_key),
                    opt=opt,
                    options=options,
                    video_path=video_path,
                    sidecar=sidecar,
                    event_dir=event_dir,
                )
            from bg_o3_stitch_invalidation import (  # noqa: PLC0415
                invalidate_stitch_slot_for_bg_o3_selection_change,
            )

            for line in invalidate_stitch_slot_for_bg_o3_selection_change(
                h,
                beat_id=str(beat_id),
                sidecar=sidecar,
                before_beat=before_beat,
                after_beat=b,
                reason="bg_o3_select",
            ):
                print(f"[bg_o3_stitch_invalidate] {line}", flush=True)
            pipeline_mismatch = bool(b.get("kling_o3_selection_pipeline_mismatch"))
            active_clip_pipeline = b.get("kling_o3_active_clip_pipeline")

        ok, beat = bg.update_beat_locked(
            beat_id,
            _select,
            caller="handle_bg_select_o3_video",
        )
        if not ok:
            return h._send_error_v59(
                404,
                error_code="BEAT_NOT_FOUND",
                error_message=f"beat {beat_id} not found",
                retry_safe=False,
            )
    except _BgSidecarAbort as exc:
        return _bg_abort_from_sidecar(h, exc)
    except TimeoutError as exc:
        return h._send_error_v59(
            503,
            error_code="SIDECAR_LOCK_TIMEOUT",
            error_message=str(exc) or "sidecar lock busy — retry shortly",
            retry_safe=True,
        )
    except OSError as exc:
        if bg.sidecar_io_transient(exc):
            return h._send_error_v59(
                503,
                error_code="SIDECAR_IO_TRANSIENT",
                error_message=str(exc) or "sidecar I/O transient failure",
                retry_safe=True,
                extra={"errno": getattr(exc, "errno", None)},
            )
        raise
    payload = {
        "ok": True,
        "beat_id": beat_id,
        "option_key": option_key,
        "video_path": video_path,
    }
    if pipeline_mismatch:
        payload["pipeline_mismatch"] = True
        payload["generation_mode"] = bg.resolve_beat_generation_mode(beat, sidecar)
        payload["active_clip_pipeline"] = active_clip_pipeline
        payload["pipeline_mismatch_message"] = (
            f"Selected clip is {active_clip_pipeline or 'unknown'} but beat is set to "
            f"{payload['generation_mode']} — voice will not match Generate until you switch clip or mode."
        )
    try:
        snap = _enriched_beat_snapshot_for_o3_poll(
            str(beat_id),
            _o3_job_event_dir(h, str(beat_id)),
            migrate=False,
        )
    except Exception as exc:
        print(f"[bg_select_o3] beat snapshot failed for {beat_id}: {exc}", flush=True)
        snap = _minimal_sidecar_beat_for_o3_poll(
            str(beat_id), _o3_job_event_dir(h, str(beat_id)),
        )
    if snap:
        payload["beat"] = snap
    return h._send_json(200, payload)


def _load_elevenlabs_key():
    try:
        # CODE tree — sibling credentials_lib import path (not event data root).
        _libdir = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "credentials_lib"),
        )
        if _libdir not in sys.path:
            sys.path.insert(0, _libdir)
        from credentials import load_credentials  # type: ignore

        creds = load_credentials()
        return creds.get("elevenlabs_key") or ""
    except Exception as exc:  # noqa: BLE001
        print(f"[still-clip] elevenlabs key load failed: {exc}")
        return ""


def _ensure_still_insert_tts(h, beat: dict, sidecar: dict, production_state: dict, video_role: str) -> dict:
    """Generate TTS for embedded still-insert dialogue; regen when dialogue changes."""
    from tools.production_server import _tts_regenerate_for_beat

    beat_id = beat.get("beat_id") or ""
    bg = _bg_module()
    tts_info = bg.extract_still_insert_tts(beat)
    if not tts_info:
        return {"ok": False, "error": "no spoken line in still-insert dialogue"}

    current_text = (tts_info.get("fingerprint") or tts_info.get("tts_text") or tts_info["text"]).strip()
    cached_text = (beat.get("still_tts_source_text") or "").strip()
    existing = bg.resolve_bg_beat_tts_audio_path(
        h.app.event_dir,
        beat,
        sidecar=sidecar,
        production_state=production_state,
        video_role=video_role,
    )
    if (
        existing is not None
        and existing.is_file()
        and cached_text
        and cached_text == current_text
    ):
        return {
            "ok": True,
            "audio_file": existing.name,
            "skipped": True,
            "unchanged": True,
        }

    sb_id = bg.storyboard_beat_id_for_bg_beat(
        beat_id,
        sidecar=sidecar,
        production_state=production_state,
        video_role=video_role,
    ) or bg.storyboard_beat_id_from_bg_beat(beat_id)
    if not sb_id:
        return {"ok": False, "error": f"could not map {beat_id} to storyboard beat id"}

    el_key = _load_elevenlabs_key()
    if not el_key:
        return {"ok": False, "error": "elevenlabs key unavailable"}

    voice_profile = bg.resolve_still_insert_elevenlabs_profile(tts_info["speaker"])
    if voice_profile:
        print(
            f"[still-clip] TTS regen for {beat_id} ({sb_id}) speaker={tts_info['speaker']!r} "
            f"voice={voice_profile.get('voice_id')} speed={voice_profile.get('speed')} "
            f"({len(current_text)}c delivery_tags={len(tts_info.get('delivery') or [])})",
            flush=True,
        )
    else:
        print(
            f"[still-clip] TTS regen for {beat_id} ({sb_id}) speaker={tts_info['speaker']!r} "
            f"({len(current_text)}c delivery_tags={len(tts_info.get('delivery') or [])})",
            flush=True,
        )
    if (beat.get("speaker") or "").strip() in ("Character", "") and tts_info.get("speaker"):
        beat["speaker"] = tts_info["speaker"]
    result = _tts_regenerate_for_beat(
        h.app,
        beat_id,
        tts_info["tts_text"],
        el_key,
        video_role=video_role,
        speaker_override=tts_info["speaker"],
        storyboard_beat_id=sb_id,
        voice_profile_override=voice_profile,
    )
    if result.get("ok") and result.get("audio_file"):
        beat["audio_file"] = result["audio_file"]
        beat["still_tts_source_text"] = current_text
    return result


def handle_bg_set_pipeline(h, body: dict) -> None:
    """POST /api/bg/set-pipeline — per-beat generation mode toggle.

    Accepts ``generation_mode`` (still_insert | avatar_pro | voice_first | element_native) or
    legacy ``pipeline`` (still_insert | kling_o3_omni).
    """
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return
    beat_id = (body.get("beat_id") or "").strip()
    generation_mode = str(
        body.get("generation_mode") or body.get("o3_generate_mode") or "",
    ).strip().lower()
    pipeline = str(body.get("pipeline") or body.get("mode") or "").strip()
    if not beat_id:
        return h._send_error_v59(
            400,
            error_code="MISSING_BEAT_ID",
            error_message="beat_id required",
            retry_safe=False,
        )
    bg = _bg_module()
    if not generation_mode and not pipeline:
        return h._send_error_v59(
            400,
            error_code="MISSING_PIPELINE",
            error_message=(
                "generation_mode (still_insert | avatar_pro | voice_first | element_native) "
                "or pipeline (still_insert | kling_o3_omni) required"
            ),
            retry_safe=False,
        )
    if generation_mode and generation_mode not in bg.VALID_GENERATION_MODES:
        return h._send_error_v59(
            400,
            error_code="INVALID_GENERATION_MODE",
            error_message=f"generation_mode must be one of {sorted(bg.VALID_GENERATION_MODES)}",
            retry_safe=False,
        )
    if generation_mode == bg.O3_GENERATE_MODE_AVATAR and bg.beatgen_avatar_pro_disabled():
        return h._send_error_v59(
            400,
            error_code="BEATGEN_AVATAR_DISABLED",
            error_message=(
                "Beat Gen Avatar Pro is disabled — use Element native O3 or Voice-first. "
                "Phase B module lipsync still uses Avatar Pro on the Phase B tab."
            ),
            retry_safe=False,
        )
    if not generation_mode:
        if pipeline == bg.PIPELINE_MODE_STILL:
            generation_mode = bg.PIPELINE_MODE_STILL
        elif pipeline == bg.PIPELINE_MODE_O3:
            generation_mode = ""
        else:
            return h._send_error_v59(
                400,
                error_code="INVALID_PIPELINE",
                error_message="pipeline must be still_insert or kling_o3_omni",
                retry_safe=False,
            )
    event_dir = Path(getattr(h.app, "event_dir", _data_root(h)))
    if not event_dir.is_absolute():
        event_dir = _data_root(h) / event_dir
    changed = False
    beat: dict | None = None

    def _set_pipeline(b: dict, sidecar: dict) -> None:
        nonlocal changed
        try:
            if _beat_o3_operator_lock_active(b, event_dir):
                raise _BgSidecarAbort(
                    status=409,
                    error_code="INTENT_JOB_ACTIVE",
                    error_message="O3 generation intent is active — pipeline locked until the job finishes.",
                    retry_safe=True,
                )
        except _BgSidecarAbort:
            raise
        except Exception:
            if _beat_o3_operator_lock_active(b, event_dir):
                raise _BgSidecarAbort(
                    status=409,
                    error_code="INTENT_JOB_ACTIVE",
                    error_message="O3 job is running — pipeline locked until it finishes.",
                    retry_safe=True,
                )
        event_id, phase = bg.segment_event_phase_for_beat(sidecar, beat_id)
        if not event_id or not phase:
            ctx = sidecar.get("active_context") or {}
            event_id = bg.normalize_bg_event_id(ctx.get("event_id") or "")
            phase = ctx.get("phase") or "pre"
        try:
            if generation_mode:
                changed = bg.set_beat_generation_mode(
                    b,
                    generation_mode,
                    event_id=str(event_id),
                    phase=str(phase),
                    sidecar=sidecar,
                )
            else:
                changed = bg.set_beat_pipeline_mode(
                    b, bg.PIPELINE_MODE_O3, event_id=str(event_id), phase=str(phase),
                )
        except bg.PipelineToggleError as exc:
            raise _BgSidecarAbort(
                status=400 if exc.code != "INTENT_JOB_ACTIVE" else 409,
                error_code=exc.code,
                error_message=exc.message,
                retry_safe=exc.code == "INTENT_JOB_ACTIVE",
            ) from exc
        bg.enrich_beat_generation_mode(b, sidecar)

    try:
        ok, beat = bg.update_beat_locked(beat_id, _set_pipeline)
    except _BgSidecarAbort as exc:
        return _bg_abort_from_sidecar(h, exc)
    if not ok:
        return h._send_error_v59(
            404,
            error_code="BEAT_NOT_FOUND",
            error_message=f"beat {beat_id} not found",
            retry_safe=False,
        )
    return h._send_json(200, {
        "ok": True,
        "beat_id": beat_id,
        "pipeline": beat.get("pipeline"),
        "beat_render_mode": beat.get("beat_render_mode"),
        "beat_type": beat.get("beat_type"),
        "kling_o3_prompt": beat.get("kling_o3_prompt"),
        "kling_o3_prompt_still": beat.get("kling_o3_prompt_still"),
        "o3_generate_mode": beat.get("o3_generate_mode"),
        "generation_mode": beat.get("generation_mode"),
        "changed": changed,
        "element_char_ref_ok": beat.get("element_char_ref_ok"),
        "element_char_ref_error": beat.get("element_char_ref_error"),
    })


def handle_bg_render_still_clip(h, body: dict) -> None:
    """POST /api/bg/render-still-clip — Ken Burns / static hold still → O3 slot mp4."""
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return
    beat_id = (body.get("beat_id") or "").strip()
    if not beat_id:
        return h._send_error_v59(
            400,
            error_code="MISSING_BEAT_ID",
            error_message="beat_id required",
            retry_safe=False,
        )
    method = str(body.get("method") or "ken_burns").strip()
    if method not in ("ken_burns", "static_hold"):
        return h._send_error_v59(
            400,
            error_code="INVALID_STILL_RENDER_METHOD",
            error_message="method must be ken_burns or static_hold",
            retry_safe=False,
        )
    video_role = (
        (body.get("scope_target_video") or body.get("scope_video_role") or "intro") or "intro"
    ).strip()
    bg = _bg_module()
    try:
        requested_duration = float(body.get("duration") or bg.STILL_INSERT_DEFAULT_DURATION_S)
    except (TypeError, ValueError):
        requested_duration = bg.STILL_INSERT_DEFAULT_DURATION_S
    try:
        slot_index = int(body.get("slot_index") or 0)
    except (TypeError, ValueError):
        slot_index = 0
    production_state = h.app.state.read_state()

    import copy

    sidecar = bg.read_sidecar()
    sidecar = bg._migrate_sidecar(sidecar)
    _, beat = bg.find_beat(sidecar, beat_id)
    if not beat:
        return h._send_error_v59(
            404,
            error_code="BEAT_NOT_FOUND",
            error_message=f"beat {beat_id} not found",
            retry_safe=False,
        )
    if not bg.beat_is_still_insert(beat):
        return h._send_error_v59(
            400,
            error_code="NOT_STILL_INSERT_BEAT",
            error_message="render-still-clip only applies to still_insert beats",
            retry_safe=False,
        )
    if bg.resolve_still_source_abs_path(beat) is None:
        return h._send_error_v59(
            400,
            error_code="STILL_SOURCE_MISSING",
            error_message="No still image — drop a library image in option 1 or set char/BG ref first",
            retry_safe=False,
        )
    _STILL_RENDER_BUSY.add(beat_id)
    try:
        work_beat = copy.deepcopy(beat)
        dialogue_override = (body.get("dialogue_text") or "").strip()
        if dialogue_override:
            work_beat["dialogue_text"] = dialogue_override
        prompt_override = (body.get("kling_o3_prompt") or "").strip()
        if prompt_override:
            work_beat["kling_o3_prompt"] = prompt_override
            bg.stamp_o3_prompt_box_law(work_beat, prompt_override)
        bg.sync_beat_dialogue_from_kling_prompt(work_beat)
        work_sidecar = sidecar

        tts_result: dict = {"ok": False, "skipped": True}
        try:
            tts_result = _ensure_still_insert_tts(
                h, work_beat, work_sidecar, production_state, video_role,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[still-clip] TTS ensure failed: {exc}")
            tts_result = {"ok": False, "error": str(exc)}

        if not tts_result.get("ok") and not tts_result.get("unchanged"):
            work_beat.pop("audio_file", None)
            work_beat.pop("still_tts_source_text", None)
            return h._send_error_v59(
                422,
                error_code="STILL_TTS_FAILED",
                error_message=(
                    tts_result.get("error")
                    or "Still+TTS requires dialogue audio before the clip can be built"
                ),
                retry_safe=True,
            )

        duration = bg.resolve_still_insert_render_duration(
            work_beat,
            _o3_job_event_dir(h, beat_id),
            sidecar=work_sidecar,
            production_state=production_state,
            video_role=video_role,
            fallback=requested_duration,
        )
        print(
            f"[still-clip] {beat_id} render duration={duration:.2f}s "
            f"(requested={requested_duration:.2f}s, tts_ok={tts_result.get('ok')})",
            flush=True,
        )

        clip_event_dir = _o3_job_event_dir(h, beat_id)
        try:
            result = bg.render_still_insert_o3_clip(
                work_beat,
                clip_event_dir,
                method=method,
                duration=duration,
                slot_index=slot_index,
                sidecar=work_sidecar,
                production_state=production_state,
                video_role=video_role,
            )
        except ValueError as exc:
            return h._send_error_v59(
                400,
                error_code="STILL_SOURCE_MISSING",
                error_message=str(exc),
                retry_safe=False,
            )
        except Exception as exc:
            return h._send_error_v59(
                500,
                error_code="STILL_CLIP_RENDER_FAILED",
                error_message=str(exc),
                retry_safe=True,
            )

        _STILL_RENDER_FIELDS = (
            "kling_o3_options", "kling_o3_video_path", "kling_o3_status", "status",
            "kling_o3_selected_option_key", "kling_o3_selected_at",
            "kling_o3_trim_start", "kling_o3_trim_back", "kling_o3_trim_end",
            "local_render_params", "audio_file", "still_tts_source_text", "dialogue_text",
            "kling_o3_prompt", "o3_prompt_box_law", "o3_prompt_box_law_at",
            "accepted_library_ref", "accepted_image_key", "gpt_options", "bg_ref_image",
        )

        def _apply_render(target, _sidecar):
            for field in _STILL_RENDER_FIELDS:
                if field in work_beat:
                    target[field] = work_beat[field]

        try:
            ok, updated_beat = bg.update_beat_locked(
                beat_id,
                _apply_render,
                caller="handle_bg_render_still_clip",
            )
            if not ok:
                return h._send_error_v59(
                    404,
                    error_code="BEAT_NOT_FOUND",
                    error_message=f"beat {beat_id} not found on write-back",
                    retry_safe=False,
                )
        except OSError as exc:
            return h._send_error_v59(
                503,
                error_code="SIDECAR_WRITE_FAILED",
                error_message=str(exc),
                retry_safe=True,
            )
        event_dir = clip_event_dir
        if not event_dir.is_absolute():
            event_dir = _data_root(h) / event_dir
        response = {
            "ok": True,
            "beat_id": beat_id,
            **result,
            "tts_ok": bool(tts_result.get("ok")),
            "tts_error": None if tts_result.get("ok") else tts_result.get("error"),
            "tts_skipped": bool(tts_result.get("skipped")),
            "tts_regenerated": bool(tts_result.get("ok") and not tts_result.get("skipped")),
            "tts_unchanged": bool(tts_result.get("unchanged")),
        }
        try:
            snap = _enriched_beat_snapshot_for_o3_poll(beat_id, event_dir, migrate=False)
            if snap:
                # Terminal still-clip response — render finished; never leave job_busy latched.
                snap["job_busy"] = False
                response["beat"] = snap
        except Exception as exc:
            print(f"[still-clip] beat snapshot failed for {beat_id}: {exc}", flush=True)
        return h._send_json(200, response)
    finally:
        _STILL_RENDER_BUSY.discard(beat_id)


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

    def _accept_opt(b: dict, _sc: dict) -> None:
        b["accepted_image_key"] = option_key
        b["status"] = "still_chosen"
        all_opts = (b.get("gpt_options") or []) + (b.get("flux_options") or [])
        for opt in all_opts:
            if not opt:
                continue
            if opt.get("key") == option_key:
                lp = opt.get("local_path")
                if lp and isinstance(lp, str):
                    b["accepted_local_path"] = lp
                vp = opt.get("video_path") or opt.get("filename")
                if vp and isinstance(vp, str) and vp.lower().endswith((".mp4", ".mov")):
                    b["accepted_video_path"] = vp
                break

    ok, _ = bg.update_beat_locked(beat_id, _accept_opt)
    if not ok:
        return h._send_error_v59(
            404,
            error_code="GENERIC_ERROR",
            error_message=f"beat {beat_id} not found",
            retry_safe=False,
        )
    return h._send_json(200, {"ok": True})


def _lib_drop_thumb_b64_from_path(h, abs_path: str) -> str | None:
    """PIL thumbnail for library drop — must run outside sidecar file lock."""
    try:
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
            return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except (OSError, ImportError) as _thumb_err:
        print(f"[LIBDROP] thumbnail skipped for {abs_path!r}: {_thumb_err}", flush=True)
    return None


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
    sidecar_probe = bg.read_sidecar()
    bg.ensure_sidecar_schema_defaults(sidecar_probe)
    _, beat_probe = bg.find_beat(sidecar_probe, beat_id)
    if not beat_probe:
        return h._send_error_v59(
            404,
            error_code="GENERIC_ERROR",
            error_message=f"beat {beat_id} not found",
            retry_safe=False,
        )
    event_dir = Path(getattr(h.app, "event_dir", _data_root(h)))
    if not event_dir.is_absolute():
        event_dir = _data_root(h) / event_dir
    if _beat_o3_operator_lock_active(beat_probe, event_dir):
        return h._send_error_v59(
            409,
            error_code="INTENT_JOB_ACTIVE",
            error_message="O3 job is running — library drop is locked until it finishes.",
            retry_safe=True,
        )

    thumb_b64 = _lib_drop_thumb_b64_from_path(h, abs_path)

    def _apply_lib_drop(b: dict, _sidecar: dict) -> None:
        from operator_workbench_contract import write_still_scene_source

        if bg.beat_is_still_insert(b):
            write_still_scene_source(
                b,
                key=key,
                filename=filename,
                abs_path=abs_path,
                slot_index=slot_index,
                thumb_b64=thumb_b64,
                source="library_drop",
            )
            return
        b["accepted_library_ref"] = {
            "key": key, "filename": filename,
            "abs_path": abs_path, "slot_index": slot_index,
        }
        b["accepted_image_key"] = key
        b["status"] = "lib_chosen"
        opts = b.get("gpt_options") or []
        option_entry: dict = {
            "key": key,
            "source": "library_drop",
            "local_path": abs_path,
            "filename": filename,
        }
        if thumb_b64:
            option_entry["thumb_b64"] = thumb_b64
        if slot_index < len(opts) and isinstance(opts[slot_index], dict):
            opts[slot_index].update(option_entry)
        else:
            while len(opts) < slot_index:
                opts.append(None)
            if slot_index < len(opts):
                opts[slot_index] = option_entry
            else:
                opts.append(option_entry)
        b["gpt_options"] = opts

    try:
        ok, _beat = bg.update_beat_locked(beat_id, _apply_lib_drop)
    except OSError as exc:
        if bg.sidecar_io_transient(exc):
            return h._send_error_v59(
                503,
                error_code="SIDECAR_IO_TRANSIENT",
                error_message=f"Dropbox sync blocked library save ({exc}); retry shortly.",
                retry_safe=True,
            )
        raise
    if not ok:
        return h._send_error_v59(
            404,
            error_code="GENERIC_ERROR",
            error_message=f"beat {beat_id} not found",
            retry_safe=False,
        )
    print(f"[LIBDROP] accepted library image {key!r} -> beat {beat_id} (thumb={'yes' if thumb_b64 else 'no'})", flush=True)
    return h._send_json(200, {"ok": True, "beat_id": beat_id,
                                 "accepted_image_key": key,
                                 "thumb_b64": thumb_b64,
                                 "slot_index": slot_index})


def handle_bg_groups(h)-> None:

    qs = urllib.parse.parse_qs(urllib.parse.urlparse(h.path).query)
    arc_n = int((qs.get("arc") or [1])[0])
    bg = _bg_module()
    sidecar = bg.read_sidecar()
    sidecar = bg._migrate_sidecar(sidecar)
    groups = bg.list_groups(sidecar, arc_n)
    for g in groups:
        g["status"] = bg._compute_group_status(sidecar, g)
    return h._send_json(200, {"ok": True, "groups": groups})


def _resolve_bg_insert_segment(h, body: dict):
    """Return (scope, arc_number, event_id_int, phase, segment_raw) or error response."""
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

    segment_raw = (body or {}).get("segment", "")
    arc_number: int | None = None
    event_id_int: int | None = None
    phase: str | None = None
    if segment_raw:
        seg_match = re.match(r"^event_(\d+)_(\w+)$", segment_raw)
        if seg_match:
            event_id_int = int(seg_match.group(1))
            phase = seg_match.group(2)
            arc_number = 1

    if event_id_int is None or phase is None:
        bg_module = _bg_module()
        _ctx_sidecar = bg_module.read_sidecar()
        _ctx = _ctx_sidecar.get("active_context") or {}
        if _ctx:
            try:
                arc_number = int(_ctx.get("arc_number", 1))
                event_id_int = int(_ctx.get("event_id", 0)) or None
                phase = _ctx.get("phase") or None
            except (TypeError, ValueError):
                pass

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
                extra={
                    "detail": str(exc),
                    "hint": (
                        "No BG segment could be derived: client did not send `segment`, "
                        "sidecar has no active_context, and storyboard scope is unparseable."
                    ),
                },
            )

    return scope, int(arc_number or 1), int(event_id_int), str(phase), segment_raw


def _allocate_bg_beat_id(
    beats: list,
    *,
    arc_number: int,
    event_id_int: int,
    phase: str,
) -> str:
    prefix = f"bg_arc{arc_number}_event{event_id_int}_{phase}_beat_"
    existing_nums: list[int] = []
    for b in beats:
        bid = b.get("beat_id", "")
        if bid.startswith(prefix):
            try:
                existing_nums.append(int(bid[len(prefix):]))
            except ValueError:
                pass
    new_num = (max(existing_nums) + 1) if existing_nums else 1
    return f"{prefix}{new_num:02d}"


def handle_bg_add_beat(h, body: dict) -> None:
    """Deprecated blank-row insert — use POST /api/bg/insert-beat with plan_row."""
    return h._send_error_v59(
        410,
        error_code="INSERT_BEAT_FORM_REQUIRED",
        error_message=(
            "Blank add-beat is removed. Use POST /api/bg/insert-beat with "
            "speaker, dialogue_text, and scene_notes in plan_row."
        ),
        retry_safe=False,
        extra={"replacement_endpoint": "/api/bg/insert-beat"},
    )


def handle_bg_insert_beat(h, body: dict) -> None:
    """POST /api/bg/insert-beat — materialize one beat via extract builder (form-first)."""
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return
    resolved = _resolve_bg_insert_segment(h, body)
    if not isinstance(resolved, tuple):
        return resolved
    _scope, arc_number, event_id_int, phase, segment_raw = resolved

    plan_row = (body or {}).get("plan_row")
    if not isinstance(plan_row, dict):
        return h._send_error_v59(
            400,
            error_code="INSERT_PLAN_INVALID",
            error_message="plan_row object required",
            retry_safe=False,
        )

    from beat_extract_policy import normalize_plan_row

    normalized, norm_warnings = normalize_plan_row(plan_row, beat_index=99)
    speaker = str(normalized.get("speaker") or "").strip()
    beat_type = str(normalized.get("beat_type") or "dialogue").lower()
    dialogue = str(normalized.get("dialogue_text") or "").strip()

    if beat_type not in ("stage_still", "stage_direction"):
        if not speaker or speaker == "Character":
            return h._send_error_v59(
                400,
                error_code="INSERT_PLAN_INVALID",
                error_message="speaker required (not Character)",
                retry_safe=False,
            )
        if not dialogue:
            return h._send_error_v59(
                400,
                error_code="INSERT_PLAN_INVALID",
                error_message="dialogue_text required for dialogue beats",
                retry_safe=False,
            )

    after_beat_id = str((body or {}).get("after_beat_id") or "")

    bg = _bg_module()
    event_id_str = str(event_id_int)
    new_beat: dict = {}
    new_beat_id = ""
    element_ref_registered = None
    element_ref_warning = None

    def _insert(sidecar: dict) -> None:
        nonlocal new_beat, new_beat_id, element_ref_registered, element_ref_warning
        seg = bg.get_seg_entry(
            sidecar, arc_number=arc_number, event_id=event_id_int, phase=phase,
        )
        beats = seg.get("beats", [])
        insert_after = len(beats) - 1
        for i, b in enumerate(beats):
            if b.get("beat_id") == after_beat_id:
                insert_after = i
                break
        new_beat_id = _allocate_bg_beat_id(
            beats,
            arc_number=arc_number,
            event_id_int=event_id_int,
            phase=phase,
        )
        try:
            new_beat = bg.materialize_sidecar_beat_from_plan_row(
                normalized,
                beat_id=new_beat_id,
                arc_number=arc_number,
                event_id=event_id_str,
                phase=phase,
                sidecar=sidecar,
            )
        except ValueError as exc:
            raise _BgSidecarAbort(
                status=400,
                error_code="INSERT_PLAN_INVALID",
                error_message=str(exc),
                retry_safe=False,
            ) from exc
        if speaker:
            try:
                from credentials import load_credentials  # type: ignore
            except ImportError:
                from tools.credentials_lib.credentials import load_credentials  # type: ignore
            creds = load_credentials()
            ws_key = creds.get("wavespeed_key") or creds.get("wavespeed")
            if ws_key:
                reg_result = bg.maybe_auto_register_beat_char_ref(new_beat, ws_key)
                if reg_result.get("ok") and not reg_result.get("skipped"):
                    if new_beat.get("element_char_ref_ok"):
                        try:
                            from tools import kling_character_registry as reg

                            display = reg.kling_element_display_name(speaker) or speaker
                        except Exception:
                            display = speaker
                        action = reg_result.get("action") or "registered"
                        pose = reg_result.get("pose_rel") or ""
                        element_ref_registered = (
                            f"Registered on {display} Element ({action})"
                            + (f" — {pose}" if pose else "")
                            + ". Generate unlocked."
                        )
        if new_beat.get("element_char_ref_ok") is False and bg.element_char_ref_required_for_beat(new_beat, sidecar):
            detail = (new_beat.get("element_char_ref_error") or "").strip()
            element_ref_warning = (
                "Char ref saved on this beat, but Element registration failed. "
                "Try Add to Element from library preview (Loral), or drop the pose again."
                + (f" ({detail})" if detail else "")
            )
        beats.insert(insert_after + 1, new_beat)

    try:
        bg.mutate_sidecar_locked(_insert, migrate=True)
    except _BgSidecarAbort as exc:
        return _bg_abort_from_sidecar(h, exc)

    print(
        f"[BG] insert-beat: materialized {new_beat_id} speaker={speaker!r} into "
        f"arc{arc_number}/event_{event_id_int}_{phase} after {after_beat_id!r}",
        flush=True,
    )
    return h._send_json(200, {
        "ok": True,
        "beat": new_beat,
        "beat_id": new_beat_id,
        "segment": f"event_{event_id_int}_{phase}",
        "arc_number": arc_number,
        "warnings": norm_warnings,
        "element_char_ref_ok": new_beat.get("element_char_ref_ok"),
        "element_char_ref_error": new_beat.get("element_char_ref_error"),
        "element_ref_registered": element_ref_registered,
        "element_ref_warning": element_ref_warning,
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
    gid = ""
    group_status = ""

    def _create(sidecar: dict) -> None:
        nonlocal gid, group_status
        try:
            gid = bg.create_group(sidecar, name, arc_n, beat_ids)
        except ValueError as e:
            raise _BgSidecarAbort(
                status=400,
                error_code="GENERIC_ERROR",
                error_message=str(e),
                retry_safe=False,
                extra={"ok": False},
            ) from e
        group_status = sidecar["groups"][gid]["status"]

    try:
        bg.mutate_sidecar_locked(_create, migrate=True)
    except _BgSidecarAbort as exc:
        return _bg_abort_from_sidecar(h, exc)
    return h._send_json(200, {"ok": True, "group_id": gid, "status": group_status})


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

    def _delete_group(sidecar: dict) -> None:
        if not bg.delete_group(sidecar, gid):
            raise _BgSidecarAbort(
                status=404,
                error_code="GROUP_NOT_FOUND",
                error_message="group not found",
                retry_safe=False,
                extra={"ok": False},
            )

    try:
        bg.mutate_sidecar_locked(_delete_group, migrate=True)
    except _BgSidecarAbort as exc:
        return _bg_abort_from_sidecar(h, exc)
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
    new_status = ""

    def _update_group(sidecar: dict) -> None:
        nonlocal new_status
        if gid not in sidecar.get("groups", {}):
            raise _BgSidecarAbort(
                status=404,
                error_code="GROUP_NOT_FOUND",
                error_message="group not found",
                retry_safe=False,
                extra={"ok": False},
            )
        new_status = bg.update_group_order(sidecar, gid, ordered)

    try:
        bg.mutate_sidecar_locked(_update_group, migrate=True)
    except _BgSidecarAbort as exc:
        return _bg_abort_from_sidecar(h, exc)
    return h._send_json(200, {"ok": True, "status": new_status})


def handle_bg_assemble_group(h, body: dict)-> None:

    # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return

    # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — capture pin at entry; terminal writes assert via _check_event_pin.
    _pin = {
        "pinned_generation": h.app.event_generation,
        "pinned_event_dir": h.app.event_dir,
        "pinned_video_role": (body or {}).get("scope_video_role") or (body or {}).get("scope_target_video"),
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
    sidecar_probe = bg.read_sidecar()
    sidecar_probe = bg._migrate_sidecar(sidecar_probe)
    g = sidecar_probe.get("groups", {}).get(gid)
    if not g:
        return h._send_error_v59(
            404,
            error_code="GROUP_NOT_FOUND",
            error_message="group not found",
            retry_safe=False,
            extra={"ok": False},
        )
    status = bg._compute_group_status(sidecar_probe, g)
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
            if not h._check_event_pin(_pin, "bg_assemble_group_write_sidecar"):
                print(f"[bg_assemble_group] event drift mid-thread; skipping sidecar write", flush=True)
                return
            _asm_result: dict = {}

            def _assemble(sidecar: dict) -> None:
                clip_path, duration, size = bg.assemble_group(sidecar, gid, output_dir)
                _asm_result.update(
                    clip_path=clip_path, duration=duration, size=size,
                )

            bg.mutate_sidecar_locked(_assemble, migrate=True)
            clip_path = _asm_result["clip_path"]
            duration = _asm_result["duration"]
            size = _asm_result["size"]
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
        "pinned_video_role": (body or {}).get("scope_video_role") or (body or {}).get("scope_target_video"),
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
    ok, _ = bg.update_beat_locked(
        beat_id,
        lambda b, _sc: b.__setitem__("animation_method", method),
    )
    if not ok:
        return h._send_error_v59(
            404,
            error_code="GENERIC_ERROR",
            error_message=f"beat_id {beat_id} not found",
            retry_safe=False,
            extra={"ok": False},
        )
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
    def _accept_local(sidecar: dict) -> None:
        _, b = bg.find_beat(sidecar, beat_id)
        if not b:
            raise _BgSidecarAbort(
                status=404,
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

    try:
        bg.mutate_sidecar_locked(_accept_local, migrate=True)
    except _BgSidecarAbort as exc:
        return _bg_abort_from_sidecar(h, exc)
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

    # Read state snapshot once for per-beat end_frame_path lookups.
    # When a beat has an approved end frame on disk, the first Animate uses
    # kling_startend_submit (start+end) instead of legacy single-image Kling,
    # matching what Regen B+C does (Rule 8.3 §8.3 universal default).
    try:
        _animate_full_state = h.app.state.read_state()
    except Exception:
        _animate_full_state = {}
    _animate_state_beats: dict = (
        ((_animate_full_state.get("videos") or {}).get(video_role) or {}).get("beats") or {}
    )
    _animate_end_frames_dir = h.app.event_dir / "end_frames"

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

        # Check if this beat has an approved end_frame_path on disk.
        # If yes, route through kling_startend_submit (Rule 8.3) so the first
        # Animate click honours Kim's chosen second image, same as Regen B+C.
        _state_beat = _animate_state_beats.get(beat_id) or {}
        _end_frame_path = _state_beat.get("end_frame_path")
        _end_frame_disk = _animate_end_frames_dir / _end_frame_path if _end_frame_path else None
        _use_startend = bool(
            _end_frame_path and _end_frame_disk and _end_frame_disk.is_file()
        )
        if _use_startend:
            print(f"[animate] {beat_id}: end_frame found ({_end_frame_path}) → start-end pipeline")
        else:
            print(f"[animate] {beat_id}: no end_frame → legacy single-image Kling")

        # Submit options_per_beat jobs, staggered
        for opt_idx in range(options_per_beat):
            if _use_startend:
                # ── Start-end path (Rule 8.3) ──────────────────────────────
                # Uses the pre-approved end_frame PNG from disk + kling_startend_submit,
                # identical to _handle_add_options_startend.
                try:
                    from kling_startend_pipeline import kling_startend_submit as _ks_submit  # type: ignore
                    from tools.production_server import (  # type: ignore
                        RULE8_ANTI_LIPSYNC,
                        SPEAKER_MOTION_PROFILES,
                        VALID_EMOTIONS,
                        LIPSYNC_SAFE_TAIL,
                        BIRD_SPEAKERS,
                        SECTION_ACTIONS,
                        DEFAULT_ACTION,
                        _load_subject_element,
                    )
                    # Build start URI — normalize to PNG (WebP from crop-lib would fail WaveSpeed)
                    _start_hdr, _start_b64 = image.split(",", 1)
                    _start_bytes = base64.b64decode(_start_b64)
                    if "image/png" not in _start_hdr:
                        from PIL import Image as _PilImg  # type: ignore
                        _pbuf = io.BytesIO()
                        _PilImg.open(io.BytesIO(_start_bytes)).save(_pbuf, format="PNG")
                        _start_bytes = _pbuf.getvalue()
                    start_uri = (
                        f"data:image/png;base64,{base64.b64encode(_start_bytes).decode('ascii')}"
                    )
                    # Build end URI from approved disk PNG
                    _end_bytes = _end_frame_disk.read_bytes()  # type: ignore[union-attr]
                    end_uri = (
                        f"data:image/png;base64,{base64.b64encode(_end_bytes).decode('ascii')}"
                    )
                    # Build motion prompt (mirrors _handle_add_options_startend logic)
                    _canonical = _canonicalize_speaker(beat.get("speaker", "") or "")
                    _in_birds = _canonical in BIRD_SPEAKERS
                    _cstr = (
                        "Beak closed, no speech, no lip movement."
                        if _in_birds else "Mouth closed, no speech."
                    )
                    _hdr_p = f"Cartoon {_canonical} character" if _canonical else "Cartoon character"
                    _emotion = beat.get("emotion", "neutral") or "neutral"
                    if _emotion not in VALID_EMOTIONS:
                        _emotion = "neutral"
                    _profile = SPEAKER_MOTION_PROFILES.get(_canonical)
                    if _profile:
                        _action = _profile.get(_emotion) or _profile["neutral"]
                    else:
                        _action = SECTION_ACTIONS.get(beat.get("section", "") or "", DEFAULT_ACTION)
                    _se_prompt = sanitize_prompt(
                        f"{_hdr_p}, {_action}, natural interpolation between start and end frames."
                        f" {_cstr} {LIPSYNC_SAFE_TAIL}"
                    )
                    _elem = _load_subject_element(_canonical)
                    task_id = _ks_submit(
                        start_b64_uri=start_uri,
                        end_b64_uri=end_uri,
                        prompt=_se_prompt,
                        negative_prompt=RULE8_ANTI_LIPSYNC,
                        duration=beat_duration,
                        api_key=h.app.client.api_key,
                        element_entry=_elem,
                    )
                    _source_tag = "kling_startend"
                    print(
                        f"[animate] {beat_id} opt{opt_idx + 1}: start-end submitted "
                        f"task_id={task_id} end_frame={_end_frame_path}"
                    )
                except (SystemExit, Exception) as exc:  # noqa: BLE001
                    print(f"[ERR] animate start-end failed for {beat_id} opt{opt_idx + 1}: {exc}")
                    skipped.append({"beat": beat_id, "opt": opt_idx + 1, "reason": f"start-end: {exc}"})
                    continue
            else:
                # ── Legacy single-image path ───────────────────────────────
                try:
                    task_id = h.app.client.submit_animation(
                        image, prompt, duration=beat_duration,
                    )
                    _source_tag = "kling"
                except Exception as exc:  # noqa: BLE001
                    print(f"[ERR] submit failed for {beat_id} opt{opt_idx + 1}: {exc}")
                    skipped.append({"beat": beat_id, "opt": opt_idx + 1, "reason": str(exc)})
                    continue

            # Append option via partition router (was videos.intro hardcode).
            def add_option_partition(partition, _bid=beat_id, _tid=task_id, _src=_source_tag):
                pbeats = partition.setdefault("beats", {})
                pbeats[_bid]["phase_1"]["options"].append({
                    "task_id": _tid,
                    "status": "polling",
                    "file": None,
                    "submitted_at": datetime.now(timezone.utc).isoformat(),
                    "submitted_at_epoch": int(time.time()),  # Tier 1B timeout
                    "source": _src,  # Tier 1B threshold lookup; "kling_startend" when end frame used
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

    # Bug-2 hardening (Kim 2026-05-20): if the downstream Kling submit would
    # FAIL (e.g. WaveSpeed client missing keys, scenario that surfaced when
    # kling_startend_pipeline.py:155 was looking up the wrong API_KEYS_MASTER
    # path), do NOT clear existing phase_1.options first — that produces
    # data loss with no recovery. Pre-flight check: if h.app.client is None
    # or no scope-event-id, bail BEFORE mutating state.
    if h.app.client is None:
        return h._send_error_v59(
                   500,
                   error_code="WAVESPEED_NOT_CONFIGURED",
                   error_message="WaveSpeed client not configured (API key missing or load failed)",
                   retry_safe=True,
                   extra={"hint": "Check API_KEYS_MASTER.md is reachable; restart server if path drift fixed since startup."},
               )

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

    Per WATERCOLOR_ANIMATE_PIL_RENDERER_V1 + WATERCOLOR_ANIMATE_PROCEDURAL_TECH_SPEC_v2.
    Deterministic PIL frame renderer (supersedes Claude+ffmpeg LD-470).

    motion_description: parsed server-side for oscillation frequency/style (NOT Claude).
    manual_path: rub axis + compositor placement reference (normalized 0-1).

    Encode: fixed white frame + center-split hand pigment rub (wc_v13).
    See LESSONS_LEARNED_20260528_PHASE_B_WATERCOLOR_ANIMATE_V1.md.
    """
    # Watercolor animation is a Phase B asset — it is NOT partitioned by
    # intro/resolution/standalone video role.  Requiring scope_video_role here
    # caused video_role_invalid when Kim's event uses the 'resolution' role
    # (no 'intro' partition in state.videos) and the magic picker URL omitted
    # the param.  allow_missing_video_role=True keeps event-scope enforcement
    # while dropping the video-role gate for this endpoint.
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False,
                                 allow_missing_video_role=True):
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

    # wc_v8: tight-crop encode auto-expands canvas to fit the path — only reject
    # coordinates that are literally out of [0,1]. Magic trail callers do NOT use this flag.
    ok, clean_path, err = h._validate_manual_path(manual_path, enforce_safe_zone=False)
    if not ok:
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=err,
                   retry_safe=False,
               )

    wc_dir = event_watercolors_dir(h.app.event_dir)
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
        "pinned_video_role": (body or {}).get("scope_video_role") or (body or {}).get("scope_target_video"),
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

    # ── Deterministic PIL Frame Renderer (replaces Claude API + filter_complex) ──────
    # May 27 regression (169d570): replaced LD-470 Claude+ffmpeg with whole-PNG
    # path translation — lost the center-split opposite rub that LD-470 specified.
    # wc_v11: bake LD-470 semantics directly — fixed paper layer + split hand halves
    # oscillating in opposite directions along the path axis.
    # ─────────────────────────────────────────────────────────────────────────────────
    import tempfile as _tempfile

    # Duration: scale with path density (short path → 2s, long path → 5s cap).
    duration_s = max(2.0, min(5.0, len(clean_path) * 0.4))
    fps_anim = 24

    # ── Oscillation frequency from motion description ────────────────────────
    # motion_desc drives animation style: fast rubbing, gentle drift, or default.
    # Kim's description is READ HERE — this is what drives the animation logic.
    import math as _math
    _motion_lower = motion_desc.lower()
    if any(w in _motion_lower for w in [
        "rub", "friction", "heat", "warm", "brisk", "quick", "fast",
        "opposite", "back and forth", "back-and-forth", "reverse",
        "up and down", "up-and-down", "to and fro", "rapidly", "briskly",
    ]):
        _osc_freq = 2.5   # brisk rubbing: ~5 full cycles per 2s
    elif any(w in _motion_lower for w in [
        "gentle", "slow", "soft", "drift", "float", "sway",
        "pulse", "breathe", "subtle", "calm", "easy",
    ]):
        _osc_freq = 0.75  # gentle drift: ~1.5 cycles per 2s
    else:
        _osc_freq = 1.5   # moderate default oscillation

    # Ensure at least 3 full oscillation cycles; extend duration if needed.
    duration_s = max(duration_s, min(5.0, 3.0 / _osc_freq))

    n_frames = max(1, int(duration_s * fps_anim))
    elapsed_ms = 0   # no API call
    explanation = (
        f"PIL center-split rub ({_osc_freq}Hz), "
        f"{len(clean_path)} path pts, motion={motion_desc!r}, "
        f"fixed frame + hand-pigment split rub (LD-470 wc_v13)"
    )

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = wc_dir / f"{watercolor_key}_animated_{ts}.mp4"
    # Atomic write: encode to .tmp.mp4, rename when complete.
    # Prevents corrupt MP4 from appearing in the library if the server restarts
    # or the encode errors mid-write. (2026-05-27: LOW fix from audit)
    out_path_tmp = out_path.with_suffix(".tmp.mp4")

    try:
        from PIL import Image as _PILImage  # already confirmed available at startup

        with _PILImage.open(safe_ffmpeg_still) as _wc_src:
            _w, _h = _wc_src.size
            # libx264 requires even dimensions.
            _w = _w if _w % 2 == 0 else _w - 1
            _h = _h if _h % 2 == 0 else _h - 1
            _wc_rgba = _wc_src.convert("RGBA").crop((0, 0, _w, _h))

        _r, _g, _b, _a_orig = _wc_rgba.split()

        # LD-470 center-split rub (deterministic replacement for Claude+ffmpeg).
        # Original spec: split at center seam, oscillate halves in opposite
        # directions along the path axis — NOT translate the whole PNG blob.
        _dir_x = float(clean_path[-1][0]) - float(clean_path[0][0])
        _dir_y = float(clean_path[-1][1]) - float(clean_path[0][1])
        _dir_len = _math.hypot(_dir_x, _dir_y) or 1.0
        _dir_x /= _dir_len
        _dir_y /= _dir_len
        _rub_px = max(16, min(int(_h * 0.05), int(_w * 0.05), 56))
        _pad = max(8, _w // 32)
        _crop_w = (_w + 2 * _rub_px + 2 * _pad) // 2 * 2 or 2
        _crop_h = (_h + 2 * _rub_px + 2 * _pad) // 2 * 2 or 2
        _base_x = _pad + _rub_px
        _base_y = _pad + _rub_px

        # Pixel classification — only true hand pigment may move.
        # wc_v13: prior logic used "not pure white (>245)" as hand, which swept
        # in cream paper texture + black border (~222k px). Splitting those with
        # the hand halves sheared the entire white card (v2-class "frame slice").
        _hand_mask = _PILImage.new("L", (_w, _h), 0)
        _fixed_mask = _PILImage.new("L", (_w, _h), 0)
        _src_px = _wc_rgba.load()
        _hb_min_x, _hb_min_y, _hb_max_x, _hb_max_y = _w, _h, 0, 0
        _hand_px = _hand_mask.load()
        _fixed_px = _fixed_mask.load()
        for _yy in range(_h):
            for _xx in range(_w):
                _pr, _pg, _pb, _pa = _src_px[_xx, _yy]
                if _pa < 20:
                    continue
                _hb_min_x = min(_hb_min_x, _xx)
                _hb_min_y = min(_hb_min_y, _yy)
                _hb_max_x = max(_hb_max_x, _xx)
                _hb_max_y = max(_hb_max_y, _yy)
                _is_border = _pr < 80 and _pg < 80 and _pb < 80
                _is_white = _pr > 245 and _pg > 245 and _pb > 245
                _is_cream = (
                    (_pr + _pg + _pb) > 700
                    and (max(_pr, _pg, _pb) - min(_pr, _pg, _pb)) < 35
                )
                if _is_border or _is_white or _is_cream:
                    _fixed_px[_xx, _yy] = _pa
                else:
                    _hand_px[_xx, _yy] = _pa
        _fixed_rgba = _PILImage.new("RGBA", (_w, _h), (0, 0, 0, 0))
        _fixed_rgba.paste(_wc_rgba, mask=_fixed_mask)

        # Solid white underlay for hand-rub gaps (under pigment only).
        _matte_x0 = max(0, _hb_min_x - 2)
        _matte_y0 = max(0, _hb_min_y - 2)
        _matte_x1 = min(_w - 1, _hb_max_x + 2)
        _matte_y1 = min(_h - 1, _hb_max_y + 2)
        _matte_w = (_matte_x1 - _matte_x0 + 1) // 2 * 2 or 2
        _matte_h = (_matte_y1 - _matte_y0 + 1) // 2 * 2 or 2
        _white_underlay = _PILImage.new("RGB", (_matte_w, _matte_h), (255, 255, 255))
        _underlay_x = _base_x + _matte_x0
        _underlay_y = _base_y + _matte_y0

        # Split ONLY hand pigment at prayer-hands seam (hand bbox center).
        _hand_min_x, _hand_min_y, _hand_max_x, _hand_max_y = _w, _h, 0, 0
        for _yy in range(_h):
            for _xx in range(_w):
                if _hand_px[_xx, _yy]:
                    _hand_min_x = min(_hand_min_x, _xx)
                    _hand_min_y = min(_hand_min_y, _yy)
                    _hand_max_x = max(_hand_max_x, _xx)
                    _hand_max_y = max(_hand_max_y, _yy)
        _split_vertical = abs(_dir_y) >= abs(_dir_x)
        if _split_vertical:
            _split_at = max(
                _hand_min_x + 1,
                min((_hand_min_x + _hand_max_x) // 2, _hand_max_x - 1),
            )
        else:
            _split_at = max(
                _hand_min_y + 1,
                min((_hand_min_y + _hand_max_y) // 2, _hand_max_y - 1),
            )

        _half_a_mask = _PILImage.new("L", (_w, _h), 0)
        _half_b_mask = _PILImage.new("L", (_w, _h), 0)
        _ha_px = _half_a_mask.load()
        _hb_px = _half_b_mask.load()
        for _yy in range(_h):
            for _xx in range(_w):
                _a = _hand_px[_xx, _yy]
                if not _a:
                    continue
                if _split_vertical:
                    if _xx < _split_at:
                        _ha_px[_xx, _yy] = _a
                    else:
                        _hb_px[_xx, _yy] = _a
                elif _yy < _split_at:
                    _ha_px[_xx, _yy] = _a
                else:
                    _hb_px[_xx, _yy] = _a

        _half_a_rgba = _PILImage.new("RGBA", (_w, _h), (0, 0, 0, 0))
        _half_a_rgba.paste(_wc_rgba, mask=_half_a_mask)
        _half_b_rgba = _PILImage.new("RGBA", (_w, _h), (0, 0, 0, 0))
        _half_b_rgba.paste(_wc_rgba, mask=_half_b_mask)

        with _tempfile.TemporaryDirectory() as _fdir:
            for _fi in range(n_frames):
                _time_s = _fi / fps_anim
                _t = 0.5 - 0.5 * _math.cos(2 * _math.pi * _osc_freq * _time_s)
                _offset = (_t - 0.5) * 2.0 * _rub_px
                _dx_a = int(_dir_x * _offset)
                _dy_a = int(_dir_y * _offset)
                _dx_b = -_dx_a
                _dy_b = -_dy_a

                _frame_bg = _PILImage.new(
                    "RGB", (_crop_w, _crop_h), (255, 0, 255),
                )
                # Layer 1: solid white under hand-rub gaps.
                _frame_bg.paste(_white_underlay, (_underlay_x, _underlay_y))
                # Layer 2: fixed paper + cream texture + border (never moves).
                _frame_bg.paste(_fixed_rgba, (_base_x, _base_y), mask=_fixed_mask)
                # Layer 3+4: hand pigment halves rub in opposite directions.
                _frame_bg.paste(
                    _half_a_rgba,
                    (_base_x + _dx_a, _base_y + _dy_a),
                    mask=_half_a_mask,
                )
                _frame_bg.paste(
                    _half_b_rgba,
                    (_base_x + _dx_b, _base_y + _dy_b),
                    mask=_half_b_mask,
                )
                _frame_bg.save(f"{_fdir}/frame_{_fi:04d}.png", "PNG")

            _encode_cmd = [
                "ffmpeg", "-y",
                "-framerate", str(fps_anim),
                "-i", f"{_fdir}/frame_%04d.png",
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                str(out_path_tmp),
            ]
            try:
                subprocess.run(_encode_cmd, check=True, capture_output=True, timeout=120)
                # Atomic rename: only appears as a valid MP4 once fully written.
                import os as _os
                _os.rename(str(out_path_tmp), str(out_path))
            except subprocess.CalledProcessError as _enc_exc:
                # Clean up partial tmp file on encode failure.
                try:
                    out_path_tmp.unlink(missing_ok=True)
                except Exception:
                    pass
                return h._send_error_v59(
                           500,
                           error_code="FFMPEG_ENCODE_FAILED",
                           error_message="ffmpeg encode failed",
                           retry_safe=True,
                           extra={"stderr": _enc_exc.stderr.decode("utf-8", errors="replace")[-500:]},
                       )
            except subprocess.TimeoutExpired:
                try:
                    out_path_tmp.unlink(missing_ok=True)
                except Exception:
                    pass
                return h._send_error_v59(
                           504,
                           error_code="FFMPEG_ENCODE_TIMED_OUT",
                           error_message="ffmpeg encode timed out (>120s)",
                           retry_safe=True,
                       )

    except Exception as _pil_exc:
        return h._send_error_v59(
                   500,
                   error_code="PIL_RENDER_FAILED",
                   error_message=f"PIL frame render failed: {_pil_exc}",
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
            tags=["watercolor_animation", watercolor_key, "pil_center_split_rub"],
            notes=(
                f"Watercolor animation via PIL frame renderer (replaces Claude+ffmpeg LD-470). "
                f"motion={motion_desc!r}. {len(clean_path)} path points. "
                f"duration={duration_s}s. {explanation}"
            ),
            role="library",
        )
    except Exception as exc:
        print(f"[watercolor/animate] WARN registered_write failed: {exc}", flush=True)

    # State writeback — record animated override at top-level state key
    # "watercolor_animated_overrides" (a flat dict: {key: filename}).
    # NOTE: actual watercolor cues live at
    #   state["phase_b"]["phase_b_watercolor_cues_json"] (JSON string, see phases.py).
    # The consumer (handle_phase_watercolor_file) uses a disk glob for
    # {key}_animated_*.mp4 (newest by mtime) — no state dependency needed there.
    # This writeback is supplementary: lets assembly/rendering scripts find the
    # canonical animated file without a disk glob.
    animated_filename = Path(out_path).name

    def _set_watercolor_animated(state):
        overrides = state.setdefault("watercolor_animated_overrides", {})
        overrides[watercolor_key] = {
            "path": animated_filename,
            "asset_id": registered_id,
        }

    try:
        h.app.state.mutate_state(_set_watercolor_animated)
    except Exception as exc:
        print(f"[watercolor/animate] WARN state writeback failed: {exc}", flush=True)
        return h._send_error_v59(500, error_code="STATE_WRITEBACK_FAILED",
                                 error_message=f"animated OK but state writeback failed: {exc}",
                                 retry_safe=True,
                                 extra={"animated_path": str(out_path), "asset_id": registered_id})

    # DS-22 read-back verify
    try:
        _state_after = h.app.state.read_state()
        _overrides_after = _state_after.get("watercolor_animated_overrides") or {}
        _hit = (_overrides_after.get(watercolor_key) or {}).get("path") == animated_filename
        if not _hit:
            return h._send_error_v59(500, error_code="STATE_WRITEBACK_VERIFY_FAILED",
                                     error_message="watercolor_animated_overrides not visible after writeback",
                                     retry_safe=True,
                                     extra={"expected_path": animated_filename, "expected_key": watercolor_key})
        print(f"[watercolor/animate] state writeback verified for key={watercolor_key}: {animated_filename}", flush=True)
    except Exception as exc:
        return h._send_error_v59(500, error_code="STATE_WRITEBACK_VERIFY_FAILED",
                                 error_message=f"verify crashed: {type(exc).__name__}: {exc}", retry_safe=True)

    return h._send_json(200, {
        "ok": True,
        "watercolor_key": watercolor_key,
        "animated_path": str(out_path),
        "asset_id": registered_id,
        "explanation": explanation,
        "duration_s": duration_s,
        "renderer": "pil_center_split_rub",
        "osc_freq_hz": _osc_freq,
    })




# ============================================================================
# Topic 1: End-frame iteration UI (spec MAGIC_AND_ENDFRAME_FIXES_20260520_v1)
# LD-814 governs.
# ============================================================================

def _prune_end_frames(beat_dir: Path, beat_id: str, keep: int = 3) -> list[Path]:
    """T1-Phase 5: keep only the `keep` most-recent {beat_id}_endframe_*.png
    files in beat_dir; unlink the rest.

    Returns list of pruned paths for logging. Errors during unlink are
    swallowed individually (best-effort cleanup) but the pattern itself is
    deterministic — sort by mtime desc, drop after `keep`.
    """
    if not beat_dir.is_dir():
        return []
    candidates = sorted(
        beat_dir.glob(f"{beat_id}_endframe_*.png"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    pruned: list[Path] = []
    for p in candidates[keep:]:
        try:
            p.unlink()
            pruned.append(p)
        except OSError as exc:
            print(f"[prune_end_frames] {beat_id}: warning unlinking {p.name}: {exc}", flush=True)
    return pruned


def _save_end_frame_and_persist(
    h,
    body: dict,
    beat_id: str,
    video_role: str,
    end_frame_bytes: bytes,
    log_tag: str,
) -> dict:
    """Shared finisher for both preview_end_frame + upload_end_frame.

    Writes PNG to event_dir/end_frames/, mutates state with end_frame_path,
    DS-22 read-back verify, prunes oldest beyond keep=3.

    Returns dict to send to client (NOT yet sent — caller wraps).
    Raises Exception on hard failure (caller handles).
    """
    from datetime import datetime as _dt

    # Auto-upscale + validate (mirror _handle_add_options_startend pattern)
    from production_server import (  # type: ignore
        auto_upscale_image,
        validate_image_dimensions,
    )
    end_data_uri = (
        "data:image/png;base64,"
        + base64.b64encode(end_frame_bytes).decode("ascii")
    )
    end_data_uri, _upscale_info = auto_upscale_image(end_data_uri)
    if "upscaled" in _upscale_info:
        print(f"[{log_tag}] {beat_id} end frame: {_upscale_info}", flush=True)
    ok_dim, info_dim = validate_image_dimensions(end_data_uri)
    if not ok_dim:
        raise ValueError(f"end frame validation failed: {info_dim}")

    # Decode the final (possibly-upscaled) PNG bytes from data URI back out.
    _hdr, _b64 = end_data_uri.split(",", 1)
    final_png_bytes = base64.b64decode(_b64)

    # Save to event_dir/end_frames/
    end_frames_dir = h.app.event_dir / "end_frames"
    end_frames_dir.mkdir(parents=True, exist_ok=True)
    ts = _dt.utcnow().strftime("%Y%m%dT%H%M%SZ")
    filename = f"{beat_id}_endframe_{ts}.png"
    out_path = end_frames_dir / filename
    out_path.write_bytes(final_png_bytes)
    print(f"[{log_tag}] {beat_id}: end frame saved -> {out_path.name} ({len(final_png_bytes):,}B)", flush=True)

    # Mutate state.end_frame_path via scope_router (partition-aware).
    scope = None
    try:
        scope = scope_router.resolve(body, h.app.event_dir.name)

        def _set_end_frame(partition: dict) -> None:
            beats = partition.setdefault("beats", {})
            beat = beats.setdefault(beat_id, {})
            beat["end_frame_path"] = filename

        scope_router.mutate_partition(h.app.state, scope, _set_end_frame)
    except Exception as exc:  # noqa: BLE001
        # Mirror magic_still pattern: log + continue, but DS-22 verify below
        # OUTSIDE this catch will propagate state failures.
        print(f"[{log_tag}] {beat_id}: state writeback WARN: {exc}", flush=True)

    # DS-22 read-back verify (spec Bug-A4 pattern — OUTSIDE swallow-all).
    partition_written: str | None = None
    if scope is not None:
        _video_role_written = getattr(scope, "video_role", None)
        if _video_role_written:
            _state_after = h.app.state.read_state()
            _beat_after = (((_state_after.get("videos") or {}).get(_video_role_written) or {})
                          .get("beats") or {}).get(beat_id) or {}
            if _beat_after.get("end_frame_path") == filename:
                partition_written = _video_role_written
                print(f"[{log_tag}] {beat_id}: state verified videos.{_video_role_written}.beats.{beat_id}.end_frame_path={filename}", flush=True)
            else:
                # Cleanup the orphan PNG we just wrote (state didn't persist).
                try:
                    out_path.unlink()
                except OSError:
                    pass
                raise RuntimeError(
                    f"STATE_WRITEBACK_VERIFY_FAILED: expected videos.{_video_role_written}.beats.{beat_id}.end_frame_path={filename!r}, got {_beat_after.get('end_frame_path')!r}"
                )

    # Prune: keep last 3.
    pruned = _prune_end_frames(end_frames_dir, beat_id, keep=3)
    if pruned:
        print(f"[{log_tag}] {beat_id}: pruned {len(pruned)} old end_frame(s): {[p.name for p in pruned]}", flush=True)

    end_frame_url = (
        f"/files?path=Production/{h.app.event_dir.name}/end_frames/"
        + urllib.parse.quote(filename)
    )
    return {
        "ok": True,
        "beat_id": beat_id,
        "end_frame_path": filename,
        "end_frame_url": end_frame_url,
        "partition_written": partition_written,
        "size_bytes": len(final_png_bytes),
        "pruned_count": len(pruned),
    }


def handle_preview_end_frame(h, body: dict) -> None:
    """POST /api/beat/preview_end_frame
    Body: {scope_event_id, scope_video_role, beat_id, prompt_addendum?}

    T1-Phase 2 of spec MAGIC_AND_ENDFRAME_FIXES_20260520_v1.

    Generates a single end-frame image via OpenAI gpt-image-1 (or FLUX per
    LD-730 vendor selection) and saves to event_dir/end_frames/. Sets
    beat.end_frame_path. Idempotent: each call OVERWRITES end_frame_path
    with the new filename; the previous PNG is retained per keep-last-3
    pruning policy.

    Required: scope_video_role (no 'intro' default — same Bug-A3 discipline).
    """
    import urllib.parse as _up_local  # noqa: F401 — imported for shared finisher
    # Scope validation (no scope_video_role default).
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return

    beat_id = (body or {}).get("beat_id") or (body or {}).get("beat")
    if not beat_id:
        return h._send_error_v59(400, error_code="MISSING_BEAT_ID",
                                 error_message="beat_id required", retry_safe=False)
    # Same beat_id discipline as magic_still (line ~584).
    import re as _re_pre
    if "/" in beat_id or "\\" in beat_id or ".." in beat_id or beat_id.startswith("."):
        return h._send_error_v59(400, error_code="INVALID_BEAT_ID",
                                 error_message="invalid beat_id", retry_safe=False)
    if not _re_pre.match(r"^[A-Za-z0-9][A-Za-z0-9_-]*$", beat_id):
        return h._send_error_v59(400, error_code="INVALID_BEAT_ID",
                                 error_message="beat_id must match [A-Za-z0-9_-]+", retry_safe=False)

    video_role = (body or {}).get("scope_video_role") or (body or {}).get("scope_target_video")
    if not video_role:
        return h._send_error_v59(400, error_code="VIDEO_ROLE_REQUIRED",
                                 error_message="scope_video_role required", retry_safe=False)

    prompt_addendum = (body or {}).get("prompt_addendum") or None

    # Resolve beat state + speaker for prompt build.
    state = h.app.state.read_state()
    beat_state = (((state.get("videos") or {}).get(video_role) or {}).get("beats") or {}).get(beat_id) or {}
    if not beat_state:
        return h._send_error_v59(404, error_code="BEAT_NOT_FOUND",
                                 error_message=f"beat {beat_id} not found in videos.{video_role}.beats",
                                 retry_safe=False)

    # Resolve start image — needed by both OpenAI + FLUX (start_image_bytes input).
    beat_image = h.app.get_beat_image(beat_id, video_role)
    if not beat_image:
        return h._send_error_v59(400, error_code="START_IMAGE_REQUIRED",
                                 error_message=f"beat {beat_id} has no assigned image — drag-drop a start image first",
                                 retry_safe=False)

    # beat_image is data:image/...;base64,...
    try:
        _hdr, start_b64 = beat_image.split(",", 1)
        start_bytes = base64.b64decode(start_b64)
    except Exception as exc:
        return h._send_error_v59(500, error_code="START_IMAGE_MALFORMED",
                                 error_message=f"start image data-URI malformed: {type(exc).__name__}: {exc}",
                                 retry_safe=True)

    # Build prompt via shared helper (caller canonicalizes speaker — no
    # production_server.py imports inside lib helper per cursor R1).
    from production_server import _canonicalize_speaker as _cs  # type: ignore
    from lib.end_frame_prompt import build_end_frame_prompt
    speaker_canonical = _cs(beat_state.get("speaker", "") or "")
    end_frame_prompt = build_end_frame_prompt(beat_state, speaker_canonical, addendum=prompt_addendum)
    print(f"[preview_end_frame] {beat_id} prompt ({len(end_frame_prompt)} chars): {end_frame_prompt[:160]!r}...", flush=True)

    # Vendor selection (mirror _handle_add_options_startend logic).
    import os as _os
    from production_server import parse_api_keys  # type: ignore
    from lib.paths import API_KEYS_MASTER_PATH
    keys = parse_api_keys(API_KEYS_MASTER_PATH)
    bfl_key = keys.get("bfl")
    openai_key = keys.get("openai")
    if not (bfl_key or openai_key):
        return h._send_error_v59(500, error_code="END_FRAME_VENDOR_KEY_UNAVAILABLE",
                                 error_message="No end-frame vendor key available (need OpenAI or BFL/FLUX)",
                                 retry_safe=True)

    _requested = _os.environ.get("MN_END_FRAME_VENDOR", "openai").strip().lower()
    from kling_startend_pipeline import (  # type: ignore
        openai_image_edit_generate_end_frame as _openai_fn,
        flux_kontext_generate_end_frame as _flux_fn,
    )
    if _requested == "openai" and openai_key:
        _vendor_used = "openai"; _fn = _openai_fn; _key = openai_key
    elif _requested == "flux" and bfl_key:
        _vendor_used = "flux"; _fn = _flux_fn; _key = bfl_key
    elif openai_key:
        _vendor_used = "openai (fallback)"; _fn = _openai_fn; _key = openai_key
    else:
        _vendor_used = "flux (fallback)"; _fn = _flux_fn; _key = bfl_key
    print(f"[preview_end_frame] {beat_id}: vendor={_vendor_used}", flush=True)

    try:
        end_bytes = _fn(start_image_bytes=start_bytes, end_prompt=end_frame_prompt, api_key=_key)
    except SystemExit as exc:
        return h._send_error_v59(500, error_code="END_FRAME_GENERATION_FAILED",
                                 error_message=f"end-frame vendor SystemExit: {exc}",
                                 retry_safe=True, extra={"beat": beat_id})
    except Exception as exc:
        return h._send_error_v59(500, error_code="END_FRAME_GENERATION_FAILED",
                                 error_message=f"end-frame generation failed: {type(exc).__name__}: {exc}",
                                 retry_safe=True, extra={"beat": beat_id})

    try:
        resp = _save_end_frame_and_persist(h, body, beat_id, video_role, end_bytes, log_tag="preview_end_frame")
    except RuntimeError as exc:
        # State writeback verify failure surfaces here.
        return h._send_error_v59(500, error_code="STATE_WRITEBACK_VERIFY_FAILED",
                                 error_message=str(exc), retry_safe=True,
                                 extra={"beat": beat_id, "video_role": video_role})
    except Exception as exc:
        return h._send_error_v59(500, error_code="GENERIC_ERROR",
                                 error_message=f"end-frame save failed: {type(exc).__name__}: {exc}",
                                 retry_safe=True, extra={"beat": beat_id})

    return h._send_json(200, resp)


def handle_upload_end_frame(h, body: dict) -> None:
    """POST /api/beat/upload_end_frame
    Body: {scope_event_id, scope_video_role, beat_id, file_b64, mime}

    T1-Phase 3 of spec MAGIC_AND_ENDFRAME_FIXES_20260520_v1.

    Accepts a base64-encoded PNG/JPG/WEBP that Kim manually downloaded from
    chatgpt.com (or anywhere). Decodes, converts to PNG via PIL if not
    already, and saves as the beat's end_frame_path. No OpenAI/FLUX call.
    """
    # Scope validation.
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return

    beat_id = (body or {}).get("beat_id") or (body or {}).get("beat")
    if not beat_id:
        return h._send_error_v59(400, error_code="MISSING_BEAT_ID",
                                 error_message="beat_id required", retry_safe=False)
    import re as _re_up
    if "/" in beat_id or "\\" in beat_id or ".." in beat_id or beat_id.startswith("."):
        return h._send_error_v59(400, error_code="INVALID_BEAT_ID",
                                 error_message="invalid beat_id", retry_safe=False)
    if not _re_up.match(r"^[A-Za-z0-9][A-Za-z0-9_-]*$", beat_id):
        return h._send_error_v59(400, error_code="INVALID_BEAT_ID",
                                 error_message="beat_id must match [A-Za-z0-9_-]+", retry_safe=False)

    video_role = (body or {}).get("scope_video_role") or (body or {}).get("scope_target_video")
    if not video_role:
        return h._send_error_v59(400, error_code="VIDEO_ROLE_REQUIRED",
                                 error_message="scope_video_role required", retry_safe=False)

    file_b64 = (body or {}).get("file_b64") or ""
    mime = ((body or {}).get("mime") or "image/png").lower()
    if not file_b64:
        return h._send_error_v59(400, error_code="FILE_REQUIRED",
                                 error_message="file_b64 required (base64-encoded image bytes)", retry_safe=False)
    if mime not in ("image/png", "image/jpeg", "image/jpg", "image/webp"):
        return h._send_error_v59(400, error_code="INVALID_MIME",
                                 error_message=f"mime must be image/png|jpeg|webp; got {mime!r}",
                                 retry_safe=False)

    try:
        raw_bytes = base64.b64decode(file_b64)
    except Exception as exc:
        return h._send_error_v59(400, error_code="INVALID_BASE64",
                                 error_message=f"file_b64 not valid base64: {type(exc).__name__}",
                                 retry_safe=False)
    if len(raw_bytes) < 100:
        return h._send_error_v59(400, error_code="FILE_TOO_SMALL",
                                 error_message=f"decoded file is only {len(raw_bytes)}B — looks like an empty upload",
                                 retry_safe=False)

    # Convert non-PNG to PNG via PIL.
    png_bytes: bytes
    if mime == "image/png":
        png_bytes = raw_bytes
    else:
        try:
            from PIL import Image
            import io
            _img = Image.open(io.BytesIO(raw_bytes)).convert("RGB")
            _out = io.BytesIO()
            _img.save(_out, format="PNG")
            png_bytes = _out.getvalue()
            print(f"[upload_end_frame] {beat_id}: converted {mime} -> PNG ({len(raw_bytes):,}B -> {len(png_bytes):,}B)", flush=True)
        except Exception as exc:
            return h._send_error_v59(500, error_code="IMAGE_CONVERSION_FAILED",
                                     error_message=f"PIL conversion failed: {type(exc).__name__}: {exc}",
                                     retry_safe=False)

    try:
        resp = _save_end_frame_and_persist(h, body, beat_id, video_role, png_bytes, log_tag="upload_end_frame")
    except RuntimeError as exc:
        return h._send_error_v59(500, error_code="STATE_WRITEBACK_VERIFY_FAILED",
                                 error_message=str(exc), retry_safe=True,
                                 extra={"beat": beat_id, "video_role": video_role})
    except Exception as exc:
        return h._send_error_v59(500, error_code="GENERIC_ERROR",
                                 error_message=f"end-frame save failed: {type(exc).__name__}: {exc}",
                                 retry_safe=True, extra={"beat": beat_id})

    return h._send_json(200, resp)
