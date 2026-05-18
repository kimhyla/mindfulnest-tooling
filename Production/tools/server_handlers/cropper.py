"""Cropper + asset serve handlers — V59 Phase 4 Pass 2.

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
from server_handlers._path_security import (
    require_basename_under_dir,
    require_realpath_under_project,
)
import scope_router
from ffmpeg_utils import strip_audio as _strip_clip_audio
from lipsync_sender import LipSyncClient, COST_PER_LIPSYNC

# Late-resolvable private helpers from the host module.
from tools.production_server import (  # noqa: E402
    _bg_module,
    _resolve_module_id_for_state,
)

def handle_cr_library(h)-> None:

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
            # Normalize key: spaces → underscores for consistent matching
            # against _handle_assign_image / resolve_library_image_path.
            return {"key": os.path.splitext(fname)[0].replace(" ", "_"),
                    "filename": fname,
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
    return h._send_json(200, {"images": images})


def handle_cr_full_image(h)-> None:

    """GET /api/cr/full?abs_path=<encoded_path>
    Returns full-resolution base64 data URI for a single image.
    Used by the storyboard nav drop handler for Cropper and .lr row targets
    which need full-res images, not the 200x150 library thumbnails.
    Validates path is within the project directory for safety."""
    parsed = urllib.parse.urlparse(h.path)
    params = urllib.parse.parse_qs(parsed.query)
    abs_path = params.get("abs_path", [None])[0]
    if not abs_path:
        return h._send_error_v59(
                   400,
                   error_code="ABS_PATH_REQUIRED",
                   error_message="abs_path required",
                   retry_safe=False,
                   extra={"ok": False},
               )
    try:
        real_path = require_realpath_under_project(abs_path)
    except ValueError:
        return h._send_error_v59(
                   403,
                   error_code="PATH_OUTSIDE_PROJECT",
                   error_message="path outside project",
                   retry_safe=False,
                   extra={"ok": False},
               )
    safe_path = os.path.realpath(real_path)
    if not os.path.isfile(safe_path):
        return h._send_error_v59(
                   404,
                   error_code="FILE_NOT_FOUND",
                   error_message="file not found",
                   retry_safe=False,
                   extra={"ok": False},
               )
    ext = os.path.splitext(safe_path)[1].lower()
    mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".webp": "image/webp", ".gif": "image/gif"}
    mime = mime_map.get(ext, "image/png")
    with open(safe_path, "rb") as f:
        raw = f.read()
    data_uri = f"data:{mime};base64," + base64.b64encode(raw).decode()
    return h._send_json(200, {"ok": True, "data_uri": data_uri})


def handle_cr_library_delete(h, body: dict)-> None:

    """POST /api/cr/library/delete  body: {key: str, abs_path?: str, force?: bool}

    Hard-deletes a library image from sources/ OR crops/ after
    find_asset.py-style safety check (refuses if key is referenced in
    prod_assets.file_path unless force=True).

    Library at /api/cr/library returns FOUR tiers (per _handle_cr_library):
      - source           BG_STILLS_DIR + BG_STILLS_DIR/sources/
      - cropped          BG_STILLS_DIR/crops/
      - character_master Character_Assets/  (reference-only, 403 here)

    Resolution priority (LIB_DELETE_TIER_PATH_V1):
      1. If body['abs_path'] supplied AND realpath lives inside one of
         the registered library tier dirs (sources/, crops/), use it.
         Skips glob ambiguity. Character_Assets/ rejected at this gate.
      2. Otherwise multi-tier glob: sources/ first (back-compat), then
         crops/. Returns 404 with both dirs named on miss.

    Rule 19 compliance: every error path returns explicit JSON. If the
    filesystem file is missing at unlink time (race / stale Dropbox
    sync after a prior delete attempt), return 200 with a `warning`
    field — user-intent ("remove this library entry") is satisfied,
    audit visibility preserved via prod_activity_log details.warning.

    Per Phase 0 preflight 186 (LD LIB_MTIME_SORT_AND_DELETE_V1) +
    LD-pending LIB_DELETE_TIER_PATH_V1 (2026-05-16 crop-tier fix).
    Path safety mirrors _handle_cr_full_image L5195-5198.
    """
    # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return

    import glob as _glob
    key = (body or {}).get("key")
    if not key or not isinstance(key, str):
        return h._send_error_v59(
                   400,
                   error_code="KEY_REQUIRED",
                   error_message="key required",
                   retry_safe=False,
                   extra={"ok": False},
               )
    abs_path_hint = (body or {}).get("abs_path") or None

    # Tier dirs: sources/ AND crops/. Character_Assets/ is NEVER deleted
    # via this handler (reference assets — protected explicitly below).
    bg = _bg_module()
    sources_dir = os.path.join(bg.BG_STILLS_DIR, "sources")
    crops_dir = os.path.join(bg.BG_STILLS_DIR, "crops")
    if not os.path.isdir(sources_dir):
        return h._send_error_v59(
                   500,
                   error_code="SOURCES_DIR_NOT_FOUND",
                   error_message="sources_dir not found",
                   retry_safe=True,
                   extra={"ok": False},
               )
    # crops/ existence is not strictly required (older deployments may
    # have only sources/), but if a crop-key lookup falls back to glob
    # we'll skip the crops/ branch gracefully when the dir is absent.
    tier_dir_reals = []
    for td in (sources_dir, crops_dir):
        if os.path.isdir(td):
            tier_dir_reals.append(os.path.realpath(td))

    def _path_inside_tier_dirs(real: str) -> bool:
        """Realpath-containment: separator-anchored to defeat
        sibling-prefix escapes (CodeQL py/path-injection)."""
        for tier_real in tier_dir_reals:
            if real == tier_real or real.startswith(tier_real + os.sep):
                return True
        return False

    target = None

    # Path 1: client-supplied abs_path (canonical when present)
    if abs_path_hint:
        real_hint = os.path.realpath(abs_path_hint)
        if not _path_inside_tier_dirs(real_hint):
            # Could be Character_Assets/ (reference-protected) or an
            # arbitrary path outside the library tiers. Either way: 403.
            return h._send_error_v59(
                       403,
                       error_code="ABS_PATH_OUTSIDE_LIBRARY_TIER",
                       error_message="abs_path outside library tier dirs "
                    "(sources/, crops/). Character_Assets/ is "
                    "reference-only — never deleted via this endpoint.",
                       retry_safe=False,
                       extra={"ok": False},
                   )
        target = real_hint

    # Path 2: multi-tier glob fallback (no abs_path supplied)
    if target is None:
        candidates: list[str] = []
        for tier_dir in (sources_dir, crops_dir):
            if not os.path.isdir(tier_dir):
                continue
            for try_key in (key, key.replace("_", " "), key.replace(" ", "_")):
                pattern = os.path.join(tier_dir, _glob.escape(try_key) + ".*")
                for path in _glob.glob(pattern):
                    if path not in candidates:
                        candidates.append(path)

        if not candidates:
            return h._send_error_v59(
                       404,
                       error_code="GENERIC_ERROR",
                       error_message=f"key '{key}' not found in library tier dirs "
                    f"(sources/, crops/)",
                       retry_safe=False,
                       extra={"ok": False},
                   )

        # Pick the first candidate that passes tier-dir containment.
        for path in candidates:
            real = os.path.realpath(path)
            if _path_inside_tier_dirs(real):
                target = real
                break
        if not target:
            return h._send_error_v59(
                       403,
                       error_code="PATH_OUTSIDE_LIBRARY_TIER_DIRS",
                       error_message="path outside library tier dirs",
                       retry_safe=False,
                       extra={"ok": False},
                   )

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
        force = bool((body or {}).get("force"))
        if not force:
            # 422 (not 409) so the client doesn't misread this as a scope mismatch.
            # Real reason: this file is registered in prod_assets (Rule 34 / CC-23).
            return h._send_error_v59(
                       422,
                       error_code="GENERIC_ERROR",
                       error_message=f"'{key}' is registered in prod_assets (id={[r.get('id') for r in referenced]}) — deregister first to delete",
                       retry_safe=False,
                       extra={"ok": False, "code": "PROD_ASSETS_PROTECTED", "asset_ids": [r.get("id") for r in referenced]},
                   )
        # force=True: soft-deregister each prod_assets row (status→archived) then
        # hard-delete from disk. Audit trail preserved in Directus.
        try:
            for row in referenced:
                rid = row.get("id")
                if rid:
                    _c.delete_item("prod_assets", rid)
                    print(f"[lib-delete] deleted prod_assets id={rid} for key '{key}'")
        except Exception as e:
            return h._send_error_v59(
                       500,
                       error_code="GENERIC_ERROR",
                       error_message=f"Directus deregister failed: {e}",
                       retry_safe=True,
                       extra={"ok": False},
                   )

    # Hard delete. Rule 19 compliance: every error path returns explicit
    # JSON. LIB_DELETE_TIER_PATH_V1: FileNotFoundError at unlink time is
    # treated as soft-success because the user-intent ("remove this
    # library entry") is satisfied — the disk file is gone (race / stale
    # Dropbox sync / prior force-delete already ran). Audit visibility
    # preserved via the `warning` field in both response payload and
    # prod_activity_log details.warning, so weekly_preflight_audit can
    # surface a pattern of misses without the user seeing a hard error.
    file_already_gone = False
    safe_target = os.path.realpath(target)
    try:
        os.remove(safe_target)
    except FileNotFoundError:
        file_already_gone = True
    except OSError as e:
        return h._send_error_v59(
                   500,
                   error_code="GENERIC_ERROR",
                   error_message=f"os.remove failed: {e}",
                   retry_safe=True,
                   extra={"ok": False},
               )

    # Log to prod_activity_log (best-effort; non-blocking)
    details: dict = {"key": key, "deleted_path": target}
    if file_already_gone:
        details["warning"] = "file_already_gone_at_unlink"
    try:
        from lib.directus import try_post_or_queue
        try_post_or_queue("prod_activity_log", {
            "action": "library_image_deleted",
            "performed_by": "claude_lib_delete_handler",
            "details": details,
        })
    except Exception as e:
        print(f"[lib-delete] WARN: activity log failed: {e}")

    if file_already_gone:
        print(f"[lib-delete] WARN: target already gone at unlink: {target}", flush=True)
        return h._send_json(200, {
            "ok": True,
            "deleted": target,
            "warning": "file_already_gone_at_unlink",
        })
    print(f"[lib-delete] removed {target}", flush=True)
    return h._send_json(200, {"ok": True, "deleted": target})


def handle_cr_save_crop(h, body: dict)-> None:

    """POST /api/cr/save-crop {crop_png_b64, beat_id, source_key, event_id?}
    Rule 6 upscale + Rule 6.2 WebP delivery + registered_write two-write (BG-22).
    Returns { key, filename, thumb_b64, gallery_b64, asset_id }."""
    # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return
    crop_b64   = body.get("crop_png_b64", "")
    beat_id    = body.get("beat_id") or ""   # null/absent → "" (library-origin crop)
    source_key = body.get("source_key", "")
    if not crop_b64:
        return h._send_error_v59(
                   400,
                   error_code="MISSING_CROP_PNG_B64",
                   error_message="crop_png_b64 required",
                   retry_safe=False,
               )

    # Security (CodeQL py/path-injection alert #26): beat_id flows into
    # the on-disk filename via f-string. Validate if provided; fall back
    # to "lib" prefix for library-origin crops that have no beat context.
    import re as _re
    if beat_id:
        if "/" in beat_id or "\\" in beat_id or ".." in beat_id or beat_id.startswith("."):
            return h._send_error_v59(
                       400,
                       error_code="INVALID_BEAT_ID",
                       error_message="invalid beat_id",
                       retry_safe=False,
                   )
        if not _re.match(r"^[A-Za-z0-9][A-Za-z0-9_-]*$", beat_id):
            return h._send_error_v59(
                       400,
                       error_code="INVALID_BEAT_ID",
                       error_message="beat_id must match [A-Za-z0-9_-]+",
                       retry_safe=False,
                   )
    else:
        beat_id = "lib"  # library-origin crop; timestamp suffix keeps filename unique

    bg = _bg_module()
    try:
        crop_bytes = base64.b64decode(crop_b64)
    except Exception as e:
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=f"base64 decode failed: {e}",
                   retry_safe=False,
               )

    delivery_bytes, width, height, thumb_b64, gallery_b64 = bg.process_crop(crop_bytes)

    # Save to disk
    ts = int(time.time())
    filename   = f"crop_{beat_id}_{ts}.webp"
    crops_dir  = os.path.join(bg.BG_STILLS_DIR, "crops")
    os.makedirs(crops_dir, exist_ok=True)
    delivery_path = os.path.join(crops_dir, filename)
    safe_delivery_path = os.path.realpath(delivery_path)
    with open(safe_delivery_path, "wb") as f:
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
            module_id=_resolve_module_id_for_state(h.app.state),
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

    return h._send_json(200, {
        "key": key,
        "filename": filename,
        "thumb_b64": thumb_b64,
        "gallery_b64": gallery_b64,
        "asset_id": asset_id,
    })


def handle_cr_upload(h, body: dict)-> None:

    """POST /api/cr/upload {filename, image_b64, tier?}
    Saves a manually-uploaded image to the library.
    tier='source' -> BG_STILLS_DIR/sources/  (pre-crop images)
    tier='cropped' or absent -> BG_STILLS_DIR/crops/  (ready images)
    Returns { key, filename, thumb_b64, gallery_b64, tier, abs_path }."""
    # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return

    # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — capture pin at entry; terminal writes assert via _check_event_pin.
    _pin = {
        "pinned_generation": h.app.event_generation,
        "pinned_event_dir": h.app.event_dir,
        "pinned_video_role": (body or {}).get("scope_video_role", "intro"),
        "_handler": '_handle_cr_upload',
    }
    # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — pre-work pin check (S2).
    # If the event was swapped via /api/event/load between scope-guard
    # and work start, abort BEFORE any expensive work begins.
    if not h._check_event_pin(_pin, '_handle_cr_upload_pre_work'):
        return h._send_error_v59(
                   423,
                   error_code="EVENT_CHANGED_PRE_WORK",
                   error_message="event_changed_pre_work",
                   retry_safe=False,
                   extra={"code": "ASYNC_JOB_GENERATION_PIN_V1", "handler": '_handle_cr_upload', "hint": "Event changed between scope-guard and work start. "
                "No work was done; no orphan output. Client should "
                "re-hydrate scope and retry."},
               )

    filename  = body.get("filename", "")
    image_b64 = body.get("image_b64", "")
    tier      = body.get("tier", "cropped")

    if not filename or not image_b64:
        return h._send_error_v59(
                   400,
                   error_code="MISSING_FILENAME_OR_IMAGE_B64",
                   error_message="filename and image_b64 required",
                   retry_safe=False,
               )

    # Sanitize — basename only, no path traversal, valid extension
    filename = os.path.basename(filename)
    if not filename.lower().endswith((".png", ".webp", ".jpg", ".jpeg")):
        return h._send_error_v59(
                   400,
                   error_code="INVALID_FILENAME_EXTENSION",
                   error_message="filename must be .png, .webp, .jpg, or .jpeg",
                   retry_safe=False,
               )

    # Decode
    raw_b64 = image_b64
    if "," in raw_b64:
        raw_b64 = raw_b64.split(",", 1)[1]
    try:
        raw_bytes = base64.b64decode(raw_b64)
    except Exception as e:
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=f"base64 decode failed: {e}",
                   retry_safe=False,
               )

    bg = _bg_module()
    if tier == "source":
        dest_dir = os.path.join(bg.BG_STILLS_DIR, "sources")
    else:
        dest_dir = os.path.join(bg.BG_STILLS_DIR, "crops")
        tier = "cropped"

    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, filename)
    # LD-460 — terminal pin check before file write.
    if not h._check_event_pin(_pin, "cr_upload_write_bytes"):
        return h._send_error_v59(
                   423,
                   error_code="EVENT_CHANGED_MID_JOB",
                   error_message="event_changed_mid_job",
                   retry_safe=False,
                   extra={"code": "ASYNC_JOB_GENERATION_PIN_V1"},
               )
    safe_dest_path = os.path.realpath(dest_path)
    with open(safe_dest_path, "wb") as f:
        f.write(raw_bytes)

    ext = "webp" if filename.lower().endswith(".webp") else "png"
    gallery_b64 = f"data:image/{ext};base64,{base64.b64encode(raw_bytes).decode()}"
    key = os.path.splitext(filename)[0]

    print(f"[library] upload saved: {dest_path} tier={tier}")
    # CC-23 / Rule 34 — register upload in prod_assets (Two-Write Rule).
    # still_master for source images (pre-crop masters); still_delivery for crops.
    try:
        from registered_write import register_asset as _reg_upload  # type: ignore
        _asset_type = "still_master" if tier == "source" else "still_delivery"
        _reg_upload(
            file_path=dest_path,
            asset_type=_asset_type,
            module_id=_resolve_module_id_for_state(h.app.state),
            produced_by_skill="cr_upload_endpoint",
            iteration_notes=f"Manual upload via library panel (tier={tier})",
            tags=["library_upload", tier],
            role=tier,
        )
    except Exception as _reg_exc:
        print(f"[library] register_asset warning (non-fatal): {_reg_exc}")
    return h._send_json(200, {
        "ok": True,
        "key": key, "filename": filename,
        "thumb_b64": gallery_b64, "gallery_b64": gallery_b64,
        "tier": tier, "abs_path": dest_path,
    })


def serve_cropper(h)-> None:

    """Serve the latest cropper HTML from Event_1/."""
    # Find the latest cropper file
    croppers = sorted(
        h.app.event_dir.glob("image_selector_cropper_*.html"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not croppers:
        return h._send_error_v59(
                   404,
                   error_code="NO_CROPPER_HTML_FOUND_IN",
                   error_message="no cropper HTML found in event dir",
                   retry_safe=False,
               )
    body = croppers[0].read_bytes()
    print(f"[server] Serving cropper: {croppers[0].name}")
    h._send_bytes(200, body, "text/html; charset=utf-8")


def serve_asset(h, filename: str)-> None:

    # Sanitize — only serve files inside clips_dir (direct children only).
    try:
        target = require_basename_under_dir(filename, h.app.state.clips_dir)
    except ValueError as exc:
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=str(exc),
                   retry_safe=False,
               )
    safe = target.name
    safe_asset_path = os.path.realpath(str(target))
    if not os.path.isfile(safe_asset_path):
        return h._send_error_v59(
                   404,
                   error_code="GENERIC_ERROR",
                   error_message=f"asset not found: {safe}",
                   retry_safe=False,
               )
    suffix = target.suffix.lower()
    ctype = {
        ".mp4": "video/mp4",
        ".mp3": "audio/mpeg",
        ".webm": "video/webm",
        ".wav": "audio/wav",
    }.get(suffix, "application/octet-stream")

    size = os.path.getsize(safe_asset_path)
    range_header = h.headers.get("Range")
    if range_header:
        m = re.match(r"bytes=(\d+)-(\d*)", range_header)
        if m:
            start = int(m.group(1))
            end = int(m.group(2)) if m.group(2) else size - 1
            end = min(end, size - 1)
            length = end - start + 1
            with open(safe_asset_path, "rb") as f:
                f.seek(start)
                chunk = f.read(length)
            h.send_response(206)
            h.send_header("Content-Type", ctype)
            h.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            h.send_header("Accept-Ranges", "bytes")
            h.send_header("Content-Length", str(length))
            # LOG_HYGIENE_SUPPRESS_CLIENT_CANCEL_TRACEBACKS (LD 2026-04-18):
            # Chrome cancels preloaded <video> range requests aggressively
            # (element not .play()'d, scrolled out of view, etc.). This is
            # not a real failure. Catch only the two specific socket errors
            # — never the general Exception class — and return silently
            # with a single short log line. Everything else still raises.
            try:
                h.end_headers()
                h.wfile.write(chunk)
            except (BrokenPipeError, ConnectionResetError):
                print(f"asset stream canceled by client: {safe}", file=sys.stderr, flush=True)
            return

    with open(safe_asset_path, "rb") as f:
        body = f.read()
    h._send_bytes(
        200, body, ctype,
        extra_headers={"Accept-Ranges": "bytes"},
    )


