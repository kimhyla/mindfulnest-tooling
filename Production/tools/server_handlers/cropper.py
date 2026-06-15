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
from lib.event_library import (
    arc_number_from_event_id,
    canonical_images_dir,
    canonical_meta_for_arc,
    ensure_event_library_dirs,
    event_images_crops_dir,
    event_images_sources_dir,
    event_watercolors_dir,
    is_canonical_image_path,
)
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


def _library_asset_name_from_source_key(source_key: str) -> str | None:
    """Derive prod_assets.asset_name from cropper source_key (URL, path, or bare key)."""
    if not source_key or not isinstance(source_key, str):
        return None
    if source_key.startswith("data:"):
        return None
    if "abs_path=" in source_key:
        try:
            parsed = urllib.parse.urlparse(source_key)
            qs = urllib.parse.parse_qs(parsed.query)
            abs_path = qs.get("abs_path", [None])[0]
            if abs_path:
                fname = os.path.basename(abs_path)
                return os.path.splitext(fname)[0].replace(" ", "_")
        except Exception:
            pass
    base = os.path.basename(source_key.split("?")[0])
    if base:
        return os.path.splitext(base)[0].replace(" ", "_")
    return source_key.replace(" ", "_") or None


def _resolve_parent_asset_id_from_source_key(source_key: str) -> int | None:
    """Rule 6.2 — link delivery crop to still_master parent via asset_name."""
    asset_name = _library_asset_name_from_source_key(source_key)
    if not asset_name:
        return None
    try:
        from lib.directus_admin_client import DirectusAdminClient
        client = DirectusAdminClient()
    except Exception as e:
        print(f"[BG] WARN: parent_asset_id lookup skipped: {e}")
        return None
    name_variants = {asset_name, asset_name.replace("_", " "), asset_name.replace(" ", "_")}
    for name in name_variants:
        if not name:
            continue
        try:
            rows = client.get_items(
                "prod_assets",
                filters={
                    "_and": [
                        {"asset_type": {"_eq": "still_master"}},
                        {"asset_name": {"_eq": name}},
                    ]
                },
                fields=["id"],
                limit=1,
            )
        except Exception as e:
            print(f"[BG] WARN: parent_asset_id lookup failed for {name!r}: {e}")
            continue
        if rows:
            pid = rows[0].get("id")
            if isinstance(pid, int) and pid > 0:
                return pid
    return None


def _enrich_library_items_prod_assets(images: list) -> None:
    """LD-738 — annotate library items with is_master / has_crop from prod_assets."""
    for item in images:
        item["is_master"] = False
        item["has_crop"] = False
    if not images:
        return
    path_keys: list[str] = []
    for item in images:
        fp = item.get("abs_path")
        if fp:
            try:
                path_keys.append(os.path.realpath(fp))
            except OSError:
                pass
    if not path_keys:
        return
    try:
        from lib.directus_admin_client import DirectusAdminClient
        client = DirectusAdminClient()
    except Exception as e:
        print(f"[library] WARN: Directus enrich skipped: {e}")
        return
    path_to_row: dict[str, dict] = {}
    chunk = 80
    for i in range(0, len(path_keys), chunk):
        batch = path_keys[i : i + chunk]
        try:
            rows = client.get_items(
                "prod_assets",
                filters={"file_path": {"_in": batch}},
                fields=["id", "file_path", "asset_type", "asset_name", "parent_asset_id"],
                limit=-1,
            )
        except Exception as e:
            print(f"[library] WARN: prod_assets batch lookup failed: {e}")
            continue
        for row in rows or []:
            fp = row.get("file_path")
            if not fp:
                continue
            try:
                path_to_row[os.path.realpath(fp)] = row
            except OSError:
                pass
    master_ids: list[int] = []
    for row in path_to_row.values():
        if row.get("asset_type") == "still_master":
            mid = row.get("id")
            if isinstance(mid, int) and mid > 0:
                master_ids.append(mid)
    masters_with_crop: set[int] = set()
    for i in range(0, len(master_ids), chunk):
        batch_ids = master_ids[i : i + chunk]
        try:
            children = client.get_items(
                "prod_assets",
                filters={"parent_asset_id": {"_in": batch_ids}},
                fields=["parent_asset_id"],
                limit=-1,
            )
        except Exception as e:
            print(f"[library] WARN: parent_asset_id crop lookup failed: {e}")
            continue
        for child in children or []:
            pid = child.get("parent_asset_id")
            if isinstance(pid, int):
                masters_with_crop.add(pid)
    for item in images:
        fp = item.get("abs_path")
        if not fp:
            continue
        try:
            real_fp = os.path.realpath(fp)
        except OSError:
            continue
        row = path_to_row.get(real_fp)
        if not row:
            continue
        if row.get("asset_type"):
            item["asset_type"] = row["asset_type"]
        if row.get("asset_name"):
            item["asset_name"] = row["asset_name"]
        is_master = row.get("asset_type") == "still_master"
        item["is_master"] = is_master
        if is_master:
            mid = row.get("id")
            item["has_crop"] = isinstance(mid, int) and mid in masters_with_crop


def handle_cr_library(h)-> None:

    """GET /api/cr/library -> { images: [...] }
    Returns tiers: source (accepted BG stills + uploaded sources),
    cropped (crops/ dir), character_master (Character_Assets/; reference-only
    for deletes), canonical (global registry injected per arc).
    Scoped to the server's active event_dir image library."""
    bg = _bg_module()
    prod_root = h.app.event_dir.parent
    arc_number = arc_number_from_event_id(h.app.event_id)
    images = []
    seen_keys: set[str] = set()

    def _read_image(fp, tier, extra: dict | None = None):
        try:
            from PIL import Image as _PILImage
            import io as _io2
            fname = os.path.basename(fp)
            with _PILImage.open(fp) as im:
                im.thumbnail((200, 150), _PILImage.LANCZOS)
                buf = _io2.BytesIO()
                im.convert("RGB").save(buf, "JPEG", quality=72)
            thumb_b64 = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
            key = os.path.splitext(fname)[0].replace(" ", "_")
            item = {"key": key,
                    "filename": fname,
                    "thumb_b64": thumb_b64, "gallery_b64": thumb_b64,
                    "tier": tier, "abs_path": fp}
            if extra:
                item.update(extra)
            return item
        except OSError:
            return None

    def _append(item: dict | None) -> None:
        if not item:
            return
        key = item.get("key")
        if not key or key in seen_keys:
            return
        seen_keys.add(key)
        images.append(item)

    # --- Tier 1: accepted FLUX stills from BG sidecar (event library) ---
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
                            _append(item)
    except Exception as e:
        print(f"[library] sidecar scan warning: {e}")

    # --- Tier 1b: manually uploaded source images (event-scoped) ---
    element_source_hashes: set[str] = set()
    reg = None
    try:
        from tools import kling_character_registry as reg

        for char_name in (reg.load_character_subjects().get("characters") or {}):
            for ep in reg.element_image_paths(char_name):
                eh = reg.file_sha256(ep)
                if eh:
                    element_source_hashes.add(eh)
    except Exception as e:
        print(f"[library] element hash scan warning: {e}", flush=True)

    sources_dir = str(event_images_sources_dir(h.app.event_dir))
    if os.path.isdir(sources_dir):
        _src_names = [f for f in os.listdir(sources_dir)
                      if f.lower().endswith((".webp", ".png", ".jpg", ".jpeg"))]
        _src_names.sort(
            key=lambda f: -os.path.getmtime(os.path.join(sources_dir, f)))
        for fname in _src_names:
            fp = os.path.join(sources_dir, fname)
            item = _read_image(fp, "source")
            if item and element_source_hashes and reg is not None:
                src_hash = reg.file_sha256(fp)
                if src_hash and src_hash in element_source_hashes:
                    item["element_pose_contaminated"] = True
                    item["contamination_warning"] = (
                        "Bytes match an Element pose file (legacy overwrite). "
                        "Delete this tile and re-upload your original still."
                    )
            _append(item)

    # --- Tier 2: cropped delivery images (event-scoped) ---
    crops_dir = str(event_images_crops_dir(h.app.event_dir))
    if os.path.isdir(crops_dir):
        for fname in sorted(os.listdir(crops_dir)):
            if fname.lower().endswith((".webp", ".png", ".jpg", ".jpeg")):
                _append(_read_image(os.path.join(crops_dir, fname), "cropped"))

    # --- Tier 3: character reference masters (global reference) ---
    char_dir = str(prod_root / "Character_Assets")
    if os.path.isdir(char_dir):
        for fname in sorted(os.listdir(char_dir)):
            if fname.endswith("_reference_master.png"):
                item = _read_image(os.path.join(char_dir, fname), "character_master")
                if item:
                    speaker = fname.replace("_reference_master.png", "").capitalize()
                    item["speaker"] = speaker
                    _append(item)

    # --- Tier 3b: Element registration poses (Production/<Char>/poses/) ---
    try:
        from tools import kling_character_registry as reg

        seen_pose: set[str] = set()
        for char_name, cfg in (reg.load_character_subjects().get("characters") or {}).items():
            if cfg.get("status") != "active" or not cfg.get("element_id"):
                continue
            rels: list[str] = []
            frontal = cfg.get("frontal_image")
            if frontal:
                rels.append(str(frontal))
            rels.extend(str(r) for r in (cfg.get("refer_images") or []))
            for rel in rels:
                fp = prod_root / rel
                if not fp.is_file():
                    continue
                real_fp = os.path.realpath(str(fp))
                if real_fp in seen_pose:
                    continue
                seen_pose.add(real_fp)
                item = _read_image(real_fp, "element_pose", extra={
                    "speaker": char_name,
                    "tags": ["element", "char_ref"],
                    "asset_type": "element_pose",
                    "display_name": fp.name,
                })
                _append(item)
    except Exception as e:
        print(f"[library] element pose scan warning: {e}", flush=True)

    # --- Tier 4: canonical images (global, arc-filtered) ---
    can_dir = canonical_images_dir(prod_root)
    for meta in canonical_meta_for_arc(prod_root, arc_number):
        filename = meta.get("filename")
        if not filename:
            continue
        fp = can_dir / filename
        if not fp.is_file():
            print(f"[library] canonical missing on disk: {fp}", flush=True)
            continue
        item = _read_image(str(fp), "canonical", extra={
            "display_name": meta.get("display_name"),
            "tags": meta.get("tags") or ["canonical"],
            "asset_type": "canonical_image",
        })
        _append(item)

    _enrich_library_items_prod_assets(images)

    print(
        f"[library] event={h.app.event_id} arc={arc_number} serving {len(images)} images "
        f"({sum(1 for i in images if i['tier']=='source')} source, "
        f"{sum(1 for i in images if i['tier']=='cropped')} cropped, "
        f"{sum(1 for i in images if i['tier']=='canonical')} canonical)",
        flush=True,
    )
    return h._send_json(200, {"images": images, "event_id": h.app.event_id})


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

    Library at /api/cr/library returns three tiers (per handle_cr_library):
      - source           BG_STILLS_DIR + BG_STILLS_DIR/sources/
      - cropped          BG_STILLS_DIR/crops/
      - character_master Character_Assets/  (reference-only, 403 here)
    Sidecar metadata may accompany items; not a separate delete tier.

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
    if abs_path_hint and is_canonical_image_path(abs_path_hint, h.app.event_dir.parent):
        return h._send_error_v59(
            403,
            error_code="CANONICAL_IMAGE_PROTECTED",
            error_message="canonical images cannot be deleted",
            retry_safe=False,
            extra={"ok": False},
        )

    # Tier dirs: sources/ AND crops/. Character_Assets/ is NEVER deleted
    # via this handler (reference assets — protected explicitly below).
    bg = _bg_module()
    prod_root = h.app.event_dir.parent
    sources_dir = str(event_images_sources_dir(h.app.event_dir))
    crops_dir = str(event_images_crops_dir(h.app.event_dir))
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
    parent_asset_id = _resolve_parent_asset_id_from_source_key(source_key)
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
            parent_asset_id=parent_asset_id,
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
    tier='watercolor' -> assets/watercolor_library/  (Phase A/B overlay PNGs)
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
    file_b64  = body.get("file_b64", "") or image_b64
    tier      = body.get("tier", "cropped")

    audio_tiers = ("sfx", "ambient", "transitions")
    if tier in audio_tiers:
        if not filename or not file_b64:
            return h._send_error_v59(
                400,
                error_code="MISSING_FILENAME_OR_FILE_B64",
                error_message="filename and file_b64 required for audio upload",
                retry_safe=False,
            )
        filename = os.path.basename(filename)
        if not filename.lower().endswith((".mp3", ".wav", ".m4a")):
            return h._send_error_v59(
                400,
                error_code="INVALID_FILENAME_EXTENSION",
                error_message="audio filename must be .mp3, .wav, or .m4a",
                retry_safe=False,
            )
        raw_b64 = file_b64.split(",", 1)[1] if "," in file_b64 else file_b64
        try:
            raw_bytes = base64.b64decode(raw_b64)
        except Exception as e:
            return h._send_error_v59(
                400,
                error_code="GENERIC_ERROR",
                error_message=f"base64 decode failed: {e}",
                retry_safe=False,
            )
        from server_handlers.phases import _data_root  # noqa: PLC0415

        dest_dir = _data_root(h) / "assets" / "sound_library" / tier
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / filename
        if not h._check_event_pin(_pin, "cr_upload_write_bytes"):
            return h._send_error_v59(
                423,
                error_code="EVENT_CHANGED_MID_JOB",
                error_message="event_changed_mid_job",
                retry_safe=False,
                extra={"code": "ASYNC_JOB_GENERATION_PIN_V1"},
            )
        dest_path.write_bytes(raw_bytes)
        print(f"[library] audio upload saved: {dest_path} tier={tier}", flush=True)
        return h._send_json(200, {
            "ok": True,
            "key": dest_path.stem,
            "filename": filename,
            "tier": tier,
            "abs_path": str(dest_path),
            "asset_type": "audio" if tier == "ambient" else tier,
        })

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
    elif tier == "watercolor":
        dest_dir = str(event_watercolors_dir(h.app.event_dir))
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
        _asset_type = (
            "still_master" if tier == "source"
            else "watercolor_static" if tier == "watercolor"
            else "still_delivery"
        )
        _reg_upload(
            file_path=dest_path,
            asset_type=_asset_type,
            module_id=_resolve_module_id_for_state(h.app.state),
            produced_by_skill="cr_upload_endpoint",
            iteration_notes=f"Manual upload via library panel (tier={tier})",
            tags=["library_upload", tier] + (["watercolor"] if tier == "watercolor" else []),
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
            # ASSET_NO_STORE_20260524: prevent browser from serving stale video
            # content when lipsync files are overwritten in-place (same filename,
            # same ?v= param). Without no-store, lipsyncMounted (LD-757) keeps the
            # old buffered file alive indefinitely, causing trim to misbehave.
            h.send_header("Cache-Control", "no-store")
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
        extra_headers={"Accept-Ranges": "bytes", "Cache-Control": "no-store"},
    )


