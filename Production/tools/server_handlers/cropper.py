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
    baseline_images_dir,
    ensure_event_library_dirs,
    event_images_crops_dir,
    event_images_sources_dir,
    event_watercolors_dir,
    is_baseline_image_path,
    is_canonical_image_path,
    list_baseline_meta,
)
from lib.library_panel_contract import attach_panel_tabs_all, row_matches_panel_filter
from lib.watercolor_assets import list_watercolor_items, upload_watercolor_filename
from server_handlers._path_security import (
    require_basename_under_dir,
    require_realpath_under_project,
)
import scope_router
from ffmpeg_utils import strip_audio as _strip_clip_audio
from lipsync_sender import LipSyncClient, COST_PER_LIPSYNC

# In-process library list cache — disk is authority; fingerprint invalidates on upload/delete.
_LIBRARY_LIST_CACHE: dict[str, tuple[str, dict]] = {}

_CLOUD_IO_TRANSIENT_ERRNOS = frozenset({11, 35})


def _cloud_path_mtime(path: str, *, default: float = 0.0) -> float:
    """Dropbox/FUSE-safe mtime — errno 11/35 retry (LIBRARY_CLOUD_IO_V1)."""
    last: OSError | None = None
    for attempt in range(5):
        try:
            return os.path.getmtime(path)
        except OSError as exc:
            last = exc
            if exc.errno not in _CLOUD_IO_TRANSIENT_ERRNOS or attempt >= 4:
                break
            time.sleep(0.12 * (attempt + 1))
    if last:
        raise last
    return default


def _cloud_listdir(path: str) -> list[str]:
    """Dropbox/FUSE-safe listdir — errno 11/35 retry (LIBRARY_CLOUD_IO_V1)."""
    last: OSError | None = None
    for attempt in range(5):
        try:
            return os.listdir(path)
        except OSError as exc:
            last = exc
            if exc.errno not in _CLOUD_IO_TRANSIENT_ERRNOS or attempt >= 4:
                break
            time.sleep(0.12 * (attempt + 1))
    if last:
        raise last
    return []


def _cloud_is_file(path: Path | str) -> bool:
    """Dropbox/FUSE-safe is_file — errno 11/35 retry (LIBRARY_CLOUD_IO_V1)."""
    p = Path(path)
    for attempt in range(5):
        try:
            return p.is_file()
        except OSError as exc:
            if exc.errno not in _CLOUD_IO_TRANSIENT_ERRNOS or attempt >= 4:
                return False
            time.sleep(0.12 * (attempt + 1))
    return False


def _library_list_cache_key(library_event_dir: Path, app_event_id: str) -> str:
    return f"{library_event_dir.name}:{app_event_id}"


def _library_list_fingerprint(library_event_dir: Path, prod_root: Path) -> str:
    parts: list[str] = []
    for label, path in (
        ("reg", prod_root / "baseline_image_registry.json"),
        ("chars", prod_root / "character_subjects.json"),
        ("sources", Path(event_images_sources_dir(library_event_dir))),
        ("crops", Path(event_images_crops_dir(library_event_dir))),
    ):
        try:
            if path.is_file():
                parts.append(f"{label}:{path.stat().st_mtime_ns}")
            elif path.is_dir():
                latest = 0
                for entry in path.iterdir():
                    if entry.is_file():
                        latest = max(latest, entry.stat().st_mtime_ns)
                parts.append(f"{label}:dir:{latest}")
            else:
                parts.append(f"{label}:missing")
        except OSError:
            parts.append(f"{label}:err")
    return "|".join(parts)


def invalidate_cr_library_cache(library_event_id: str | None = None) -> None:
    """Drop cached GET /api/cr/library payloads after upload/delete."""
    if library_event_id is None:
        _LIBRARY_LIST_CACHE.clear()
        return
    prefix = f"{library_event_id}:"
    for key in list(_LIBRARY_LIST_CACHE):
        if key.startswith(prefix):
            _LIBRARY_LIST_CACHE.pop(key, None)


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


def _crop_source_display_stem(source_key: str) -> str | None:
    """Human-readable source label for crop filenames (ChatGPT upload names, etc.)."""
    source_real = _source_abs_path_from_source_key(source_key)
    if source_real:
        return os.path.splitext(os.path.basename(source_real))[0]
    if source_key and not source_key.startswith("data:"):
        base = os.path.basename(source_key.split("?")[0])
        if base:
            return os.path.splitext(base)[0]
    return None


def _library_key_from_filename(filename: str) -> str:
    return os.path.splitext(filename)[0].replace(" ", "_")


def _safe_crop_filename_stem(display_stem: str) -> str:
    """Filesystem-safe stem — preserves readability, drops path chars."""
    stem = re.sub(r"[^\w\s\-,.()]+", "", display_stem).strip()
    stem = re.sub(r"\s+", "_", stem)
    stem = stem.strip("._")[:72]
    return stem or "crop"


def _crop_delivery_names(source_key: str, beat_id: str, ts: int) -> tuple[str, str, str]:
    """Return (filename, library_key, display_name) for a saved delivery crop."""
    display_stem = _crop_source_display_stem(source_key)
    if display_stem:
        file_stem = _safe_crop_filename_stem(display_stem)
        filename = f"{file_stem}_crop_{ts}.webp"
        key = _library_key_from_filename(filename)
        return filename, key, f"{display_stem} (4:3 crop)"
    filename = f"crop_{beat_id}_{ts}.webp"
    return filename, f"crop_{beat_id}_{ts}", f"Crop {beat_id}"


def _source_abs_path_from_source_key(source_key: str) -> str | None:
    """Realpath for cropper source_key when it is a /api/cr/full?abs_path= URL."""
    if not source_key or not isinstance(source_key, str):
        return None
    if "abs_path=" not in source_key:
        return None
    try:
        parsed = urllib.parse.urlparse(source_key)
        qs = urllib.parse.parse_qs(parsed.query)
        abs_path = qs.get("abs_path", [None])[0]
        if abs_path:
            return os.path.realpath(abs_path)
    except (OSError, ValueError):
        return None
    return None


def _resolve_parent_asset_id_from_source_key(source_key: str) -> int | None:
    """Rule 6.2 — link delivery crop to still_master parent via asset_name."""
    try:
        from lib.directus_admin_client import DirectusAdminClient
        client = DirectusAdminClient()
    except Exception as e:
        print(f"[BG] WARN: parent_asset_id lookup skipped: {e}")
        return None
    # Prefer exact file_path match — asset_name normalization (spaces vs underscores)
    # misses ChatGPT-style upload names.
    source_real = _source_abs_path_from_source_key(source_key)
    if source_real:
        try:
            rows = client.get_items(
                "prod_assets",
                filters={
                    "_and": [
                        {"asset_type": {"_eq": "still_master"}},
                        {"file_path": {"_eq": source_real}},
                    ]
                },
                fields=["id"],
                limit=1,
            )
        except Exception as e:
            print(f"[BG] WARN: parent_asset_id file_path lookup failed: {e}")
            rows = []
        if rows:
            pid = rows[0].get("id")
            if isinstance(pid, int) and pid > 0:
                return pid
    asset_name = _library_asset_name_from_source_key(source_key)
    if not asset_name:
        return None
    raw_stem = None
    if source_real:
        raw_stem = os.path.splitext(os.path.basename(source_real))[0]
    name_variants = {
        asset_name,
        asset_name.replace("_", " "),
        asset_name.replace(" ", "_"),
    }
    if raw_stem:
        name_variants.add(raw_stem)
        name_variants.add(raw_stem.replace(" ", "_"))
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


def _enrich_has_crop_from_disk(images: list, library_event_dir: str | Path) -> None:
    """DIRECTUS_HAS_CROP_DISK_FALLBACK_V1 — stem match in library/images/crops/."""
    library_event_dir = Path(library_event_dir)
    crops_dir = library_event_dir / "library" / "images" / "crops"
    if not crops_dir.is_dir():
        return
    crop_stems = {p.stem.lower() for p in crops_dir.iterdir() if p.is_file()}
    if not crop_stems:
        return
    for item in images:
        if not isinstance(item, dict):
            continue
        if item.get("has_crop"):
            continue
        is_master = bool(item.get("is_master")) or str(item.get("asset_type") or "") == "still_master"
        if not is_master:
            continue
        fp = str(item.get("abs_path") or item.get("file_path") or "")
        if not fp:
            continue
        master_stem = Path(fp).stem.lower()
        if not master_stem:
            continue
        for crop_stem in crop_stems:
            if crop_stem == master_stem or master_stem in crop_stem or crop_stem.startswith(master_stem[:12]):
                item["has_crop"] = True
                item["has_crop_source"] = "disk_stem_match"
                break


def _enrich_library_items_prod_assets(images: list, *, library_event_dir: str | Path | None = None) -> None:
    """LD-738 — annotate library items with is_master / has_crop from prod_assets."""
    import concurrent.futures

    for item in images:
        item["is_master"] = False
        item["has_crop"] = False
    if not images:
        return

    def _run() -> None:
        _enrich_library_items_prod_assets_inner(images)

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            fut = pool.submit(_run)
            fut.result(timeout=10.0)
    except concurrent.futures.TimeoutError:
        print("[library] WARN: Directus enrich skipped — timed out after 10s", flush=True)
    except Exception as e:
        print(f"[library] WARN: Directus enrich skipped: {e}", flush=True)
    if library_event_dir is not None:
        _enrich_has_crop_from_disk(images, library_event_dir)


def _enrich_library_items_prod_assets_inner(images: list) -> None:
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
        # Never overwrite disk-scan tier/asset_type — Directus prod_assets types
        # (e.g. watercolor_static) are not the library panel BS3 filter keys.
        if row.get("asset_type"):
            item["prod_asset_type"] = row["asset_type"]
            if not item.get("asset_type"):
                item["asset_type"] = row["asset_type"]
        if row.get("asset_name"):
            item["asset_name"] = row["asset_name"]
        is_master = row.get("asset_type") == "still_master" or item.get("asset_type") == "still_master"
        item["is_master"] = is_master
        if is_master:
            mid = row.get("id")
            item["has_crop"] = isinstance(mid, int) and mid in masters_with_crop


def _resolve_cr_library_scope(
    h,
    body_or_qs: dict | None = None,
    *,
    allow_missing: bool = True,
    allow_missing_video_role: bool = True,
    repair_sidecar: bool = True,
):
    """Activate Beat Gen + return ScopeContext for library CR handlers.

    Milestone Beat Gen uploads land on ``library_event_dir`` (skeleton-linked
    Event_N), not the server-pinned ``event_dir``. List/upload/delete/crop must
    use the same roots (``init_bg_paths`` via ``assert_production_scope``).
    """
    from server_handlers.milestone_scope import assert_production_scope, parse_scope_query

    scoped = dict(body_or_qs or {})
    if not body_or_qs:
        scoped.update(parse_scope_query(h))
    return assert_production_scope(
        h,
        scoped,
        allow_missing=allow_missing,
        allow_missing_video_role=allow_missing_video_role,
        repair_sidecar=repair_sidecar,
    )


def _cr_thumb_url(abs_path: str) -> str:
    return "/api/cr/thumb?abs_path=" + urllib.parse.quote(abs_path, safe="")


def _materialize_cr_thumb_jpeg(safe_path: str) -> bytes | None:
    """200×150 JPEG for one library tile — used by GET /api/cr/thumb only.

    Caller must pass an APFS-local path (CR_THUMB_HOT_SERVE_V1 via
    ensure_hot_serve_file in handle_cr_thumb).
    """
    try:
        from PIL import Image as _PILImage
        import io as _io2

        with _PILImage.open(safe_path) as im:
            im.thumbnail((200, 150), _PILImage.LANCZOS)
            buf = _io2.BytesIO()
            im.convert("RGB").save(buf, "JPEG", quality=72)
            return buf.getvalue()
    except OSError:
        return None


def _read_image_meta(fp, tier, extra: dict | None = None):
    """Library list row — metadata only; thumbs load via GET /api/cr/thumb."""
    try:
        if not os.path.isfile(fp):
            return None
        fname = os.path.basename(fp)
        key = os.path.splitext(fname)[0].replace(" ", "_")
        item = {
            "key": key,
            "filename": fname,
            "tier": tier,
            "abs_path": fp,
            "thumb_url": _cr_thumb_url(fp),
        }
        if extra:
            item.update(extra)
        attach_panel_tabs_all([item])
        return item
    except OSError:
        return None


def _cr_library_panel_query(h) -> str | None:
    parsed = urllib.parse.urlparse(h.path)
    params = urllib.parse.parse_qs(parsed.query)
    panel = (params.get("panel") or [None])[0]
    if not panel or not isinstance(panel, str):
        return None
    panel = panel.strip()
    return panel or None


def _cr_library_response_images(images: list, panel: str | None) -> list:
    if not panel:
        return images
    return [i for i in images if row_matches_panel_filter(i, panel)]


def handle_cr_thumb(h) -> None:
    """GET /api/cr/thumb?abs_path=<encoded_path> — single on-demand library thumbnail."""
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
    # CR_THUMB_HOT_SERVE_V1 — isfile/open on Dropbox masters can errno 11/35;
    # materialize to APFS (or serve warmed cache) before decoding.
    try:
        from media_playback_cache import ensure_hot_serve_file

        local = ensure_hot_serve_file(
            safe_path,
            event_dir=getattr(h.app, "event_dir", None),
        )
    except OSError:
        return h._send_error_v59(
            503,
            error_code="THUMB_MATERIALIZE_FAILED",
            error_message="Dropbox File Provider busy — local thumb cache not ready; retry",
            retry_safe=True,
            extra={"ok": False},
        )
    if not Path(local).is_file():
        return h._send_error_v59(
            404,
            error_code="FILE_NOT_FOUND",
            error_message="file not found",
            retry_safe=False,
            extra={"ok": False},
        )
    body = _materialize_cr_thumb_jpeg(str(local))
    if body is None:
        return h._send_error_v59(
            500,
            error_code="THUMB_GENERATION_FAILED",
            error_message="could not generate thumbnail",
            retry_safe=True,
            extra={"ok": False},
        )
    return h._send_bytes(
        200,
        body,
        "image/jpeg",
        {"Cache-Control": "private, max-age=3600"},
    )


def handle_cr_library(h)-> None:

    """GET /api/cr/library -> { images: [...], metadata_only: true }
    Returns tiers: source (accepted BG stills + uploaded sources),
    cropped (crops/ dir), character_master (Character_Assets/; reference-only
    for deletes), element_pose (Kling Element registration poses).
    Every row includes panel_tabs (LIBRARY_PANEL_CLASSIFICATION_V1).
    Optional query panel=images|watercolors|… filters server-side.
    Canonical registry images are intentionally excluded — use canonical_images/
    directly, not the event/milestone library panel.
    List rows are metadata-only (thumb_url per item); thumbnails load via
    GET /api/cr/thumb on demand — never inline base64 in the list payload.
    Scoped to the active scope's library_event_dir (milestone skeleton library
    or pinned event dir)."""
    from server_handlers.milestone_scope import production_bg_scope_lock

    with production_bg_scope_lock():
        ctx = _resolve_cr_library_scope(h, repair_sidecar=False)
    if ctx is None:
        return
    bg = _bg_module()
    library_event_dir = ctx.library_event_dir
    prod_root = ctx.prod_root
    panel_filter = _cr_library_panel_query(h)
    cache_key = _library_list_cache_key(library_event_dir, str(h.app.event_id))
    fp = _library_list_fingerprint(library_event_dir, prod_root)
    cached = _LIBRARY_LIST_CACHE.get(cache_key)
    if cached and cached[0] == fp:
        payload = dict(cached[1])
        payload["images"] = _cr_library_response_images(payload.get("images") or [], panel_filter)
        if panel_filter:
            payload["panel_filter"] = panel_filter
        return h._send_json(200, payload)
    skel_arc = (ctx.skeleton_ref or {}).get("arc_number")
    arc_number = int(skel_arc) if skel_arc is not None else arc_number_from_event_id(library_event_dir.name)
    images = []
    seen_keys: set[str] = set()

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
        sidecar = bg.read_sidecar_for_poll_snapshot(lock_timeout_s=2.0)
        for arc in sidecar.get("arcs", {}).values():
            for seg in arc.get("segments", {}).values():
                for beat in seg.get("beats", []):
                    key = beat.get("accepted_image_key")
                    if not key:
                        continue
                    fp = os.path.join(bg.BG_STILLS_DIR, f"{key}.png")
                    if os.path.exists(fp):
                        item = _read_image_meta(fp, "source")
                        if item:
                            item["beat_id"] = beat.get("beat_id", "")
                            item["speaker"] = beat.get("speaker", "")
                            _append(item)
    except Exception as e:
        print(f"[library] sidecar scan warning: {e}")

    # --- Tier 1b: manually uploaded source images (event-scoped) ---
    element_source_hashes: set[str] = set()
    reg = None
    sources_dir = str(event_images_sources_dir(library_event_dir))
    _src_names: list[str] = []
    if os.path.isdir(sources_dir):
        _src_names = [f for f in _cloud_listdir(sources_dir)
                      if f.lower().endswith((".webp", ".png", ".jpg", ".jpeg"))]
    if _src_names:
        try:
            from tools import kling_character_registry as reg

            for char_name in (reg.load_character_subjects().get("characters") or {}):
                for ep in reg.element_image_paths(char_name):
                    eh = reg.file_sha256(ep)
                    if eh:
                        element_source_hashes.add(eh)
        except Exception as e:
            print(f"[library] element hash scan warning: {e}", flush=True)

    if os.path.isdir(sources_dir):
        _src_names.sort(
            key=lambda f: -_cloud_path_mtime(os.path.join(sources_dir, f)))
        for fname in _src_names:
            fp = os.path.join(sources_dir, fname)
            item = _read_image_meta(fp, "source")
            if item and element_source_hashes and reg is not None:
                src_hash = reg.file_sha256(fp)
                if src_hash and src_hash in element_source_hashes:
                    item["element_pose_contaminated"] = True
                    item["contamination_warning"] = (
                        "Bytes match an Element pose file (legacy overwrite). "
                        "Delete this tile and re-upload your original still."
                    )
            _append(item)

    # --- Tier 0: shared baseline BG stills (global, event-local key wins) ---
    baseline_dir = baseline_images_dir(prod_root)
    for meta in list_baseline_meta(prod_root):
        filename = meta.get("filename")
        if not filename:
            continue
        fp = baseline_dir / filename
        if not _cloud_is_file(fp):
            print(f"[library] baseline missing on disk: {fp}", flush=True)
            continue
        key = meta.get("key") or os.path.splitext(filename)[0]
        if key in seen_keys:
            continue
        tags = list(meta.get("tags") or ["baseline", "shared"])
        if "baseline" not in tags:
            tags.append("baseline")
        item = _read_image_meta(str(fp), "source", extra={
            "key": key,
            "display_name": meta.get("display_name") or key,
            "tags": tags,
            "shared_baseline": True,
            "asset_type": "still_master",
        })
        _append(item)

    # --- Tier 2: cropped delivery images (event-scoped) ---
    crops_dir = str(event_images_crops_dir(library_event_dir))
    if os.path.isdir(crops_dir):
        for fname in sorted(_cloud_listdir(crops_dir)):
            if fname.lower().endswith((".webp", ".png", ".jpg", ".jpeg")):
                _append(_read_image_meta(os.path.join(crops_dir, fname), "cropped"))

    # --- Tier 3: character reference masters (global reference) ---
    char_dir = str(prod_root / "Character_Assets")
    if os.path.isdir(char_dir):
        for fname in sorted(_cloud_listdir(char_dir)):
            if fname.endswith("_reference_master.png"):
                item = _read_image_meta(os.path.join(char_dir, fname), "character_master")
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
                if not _cloud_is_file(fp):
                    continue
                real_fp = os.path.realpath(str(fp))
                if real_fp in seen_pose:
                    continue
                seen_pose.add(real_fp)
                item = _read_image_meta(real_fp, "element_pose", extra={
                    "speaker": char_name,
                    "tags": ["element", "char_ref"],
                    "asset_type": "element_pose",
                    "display_name": fp.name,
                })
                _append(item)
    except Exception as e:
        print(f"[library] element pose scan warning: {e}", flush=True)

    # --- Tier 4: Phase A/B watercolor overlays (library/watercolors/) ---
    wc_items = list_watercolor_items(event_watercolors_dir(library_event_dir))
    for wc in wc_items:
        row = {
            "key": wc["key"],
            "filename": wc["filename"],
            "tier": "watercolor",
            "abs_path": wc["abs_path"],
            "thumb_url": wc["thumb_url"],
            "tags": wc.get("tags") or ["watercolor"],
            "asset_type": wc.get("asset_type") or "watercolor_static",
            "display_name": wc["key"],
            "kind": wc.get("kind"),
        }
        attach_panel_tabs_all([row])
        _append(row)

    attach_panel_tabs_all(images)
    _enrich_library_items_prod_assets(images, library_event_dir=library_event_dir)
    attach_panel_tabs_all(images)

    response_images = _cr_library_response_images(images, panel_filter)

    print(
        f"[library] scope={ctx.scope_type} library_event={library_event_dir.name} "
        f"pinned_event={h.app.event_id} arc={arc_number} serving {len(response_images)} images "
        f"({sum(1 for i in response_images if i['tier']=='source')} source, "
        f"{sum(1 for i in response_images if i.get('shared_baseline'))} baseline, "
        f"{sum(1 for i in response_images if i['tier']=='cropped')} cropped, "
        f"{sum(1 for i in response_images if i['tier']=='watercolor')} watercolor)"
        f"{f' panel={panel_filter}' if panel_filter else ''}",
        flush=True,
    )
    payload = {
        "images": response_images,
        "metadata_only": True,
        "event_id": h.app.event_id,
        "library_event_id": library_event_dir.name,
        "scope_type": ctx.scope_type,
    }
    if panel_filter:
        payload["panel_filter"] = panel_filter
    cache_payload = {
        "images": images,
        "metadata_only": True,
        "event_id": h.app.event_id,
        "library_event_id": library_event_dir.name,
        "scope_type": ctx.scope_type,
    }
    return h._send_json(200, _store_cr_library_cache(cache_key, fp, cache_payload, payload))


def _store_cr_library_cache(
    cache_key: str,
    fingerprint: str,
    cache_payload: dict,
    response_payload: dict | None = None,
) -> dict:
    _LIBRARY_LIST_CACHE[cache_key] = (fingerprint, cache_payload)
    return response_payload if response_payload is not None else cache_payload


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
    ctx = _resolve_cr_library_scope(h, body, allow_missing=False)
    if ctx is None:
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
    if abs_path_hint and is_baseline_image_path(abs_path_hint, h.app.event_dir.parent):
        return h._send_error_v59(
            403,
            error_code="BASELINE_IMAGE_PROTECTED",
            error_message="shared baseline images cannot be deleted",
            retry_safe=False,
            extra={"ok": False},
        )

    # Tier dirs: sources/ AND crops/. Character_Assets/ is NEVER deleted
    # via this handler (reference assets — protected explicitly below).
    prod_root = h.app.event_dir.parent
    # Scoped library tiers — same roots as handle_cr_library list/upload.
    sources_dir = str(event_images_sources_dir(ctx.library_event_dir))
    crops_dir = str(event_images_crops_dir(ctx.library_event_dir))
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
        invalidate_cr_library_cache(ctx.library_event_dir.name)
        return h._send_json(200, {
            "ok": True,
            "deleted": target,
            "warning": "file_already_gone_at_unlink",
        })
    print(f"[lib-delete] removed {target}", flush=True)
    invalidate_cr_library_cache(ctx.library_event_dir.name)
    return h._send_json(200, {"ok": True, "deleted": target})


def handle_cr_save_crop(h, body: dict)-> None:

    """POST /api/cr/save-crop {crop_png_b64, beat_id, source_key, event_id?}
    Rule 6 upscale + Rule 6.2 WebP delivery + registered_write two-write (BG-22).
    CROP_SAVE_LIBRARY_VISIBILITY_V1 — friendly names, parent link, library_item row.
    Returns { key, filename, display_name, library_item, parent_library_key, ... }."""
    ctx = _resolve_cr_library_scope(h, body, allow_missing=False)
    if ctx is None:
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

    # Save to disk — name from source when available (CROP_SAVE_LIBRARY_VISIBILITY_V1).
    ts = int(time.time())
    filename, key, display_name = _crop_delivery_names(source_key, beat_id, ts)
    crops_dir  = str(event_images_crops_dir(ctx.library_event_dir))
    os.makedirs(crops_dir, exist_ok=True)
    delivery_path = os.path.join(crops_dir, filename)
    safe_delivery_path = os.path.realpath(delivery_path)
    with open(safe_delivery_path, "wb") as f:
        f.write(delivery_bytes)

    source_real = _source_abs_path_from_source_key(source_key)
    parent_library_key = (
        _library_key_from_filename(os.path.basename(source_real))
        if source_real
        else None
    )

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
            colloquial_name=display_name,
        )
        if asset_id and asset_id > 0:
            print(f"[BG] registered_write OK asset_id={asset_id} {filename}")
        else:
            print(f"[BG] registered_write queued (offline) for {filename}")
    except Exception as e:
        print(f"[BG] registered_write warning (non-fatal): {e}")

    invalidate_cr_library_cache(ctx.library_event_dir.name)

    library_row = {
        "key": key,
        "filename": filename,
        "display_name": display_name,
        "tier": "cropped",
        "abs_path": safe_delivery_path,
        "thumb_url": _cr_thumb_url(safe_delivery_path),
        "panel_tabs": ["images"],
        "asset_type": "still_delivery",
        "is_master": False,
        "has_crop": False,
    }
    attach_panel_tabs_all([library_row])

    return h._send_json(200, {
        "ok": True,
        "key": key,
        "filename": filename,
        "display_name": display_name,
        "tier": "cropped",
        "abs_path": safe_delivery_path,
        "thumb_url": library_row.get("thumb_url"),
        "panel_tabs": library_row.get("panel_tabs") or ["images"],
        "asset_type": "still_delivery",
        "thumb_b64": thumb_b64,
        "gallery_b64": gallery_b64,
        "asset_id": asset_id,
        "parent_asset_id": parent_asset_id,
        "parent_library_key": parent_library_key,
        "library_item": library_row,
    })


def handle_cr_upload(h, body: dict)-> None:
    from server_handlers.milestone_scope import production_bg_scope_lock

    with production_bg_scope_lock():
        _handle_cr_upload_body(h, body)


def _handle_cr_upload_body(h, body: dict)-> None:

    """POST /api/cr/upload {filename, image_b64, tier?}
    Saves a manually-uploaded image to the library.
    tier='source' -> BG_STILLS_DIR/sources/  (pre-crop images)
    tier='watercolor' -> assets/watercolor_library/  (Phase A/B overlay PNGs)
    tier='cropped' or absent -> BG_STILLS_DIR/crops/  (ready images)
    Returns { key, filename, thumb_b64, gallery_b64, tier, abs_path }."""
    ctx = _resolve_cr_library_scope(h, body, allow_missing=False)
    if ctx is None:
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

    if tier == "source":
        dest_dir = str(event_images_sources_dir(ctx.library_event_dir))
    elif tier == "watercolor":
        dest_dir = str(event_watercolors_dir(ctx.library_event_dir))
        filename = upload_watercolor_filename(filename)
    else:
        dest_dir = str(event_images_crops_dir(ctx.library_event_dir))
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
    # Library panel refreshes via GET /api/cr/library — omit multi-MB base64 echoes
    # that can stall or reset browser fetch on phone-camera uploads.
    _SLIM_UPLOAD_B64_MAX = 512 * 1024
    if len(raw_bytes) <= _SLIM_UPLOAD_B64_MAX:
        gallery_b64 = f"data:image/{ext};base64,{base64.b64encode(raw_bytes).decode()}"
    else:
        gallery_b64 = None

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
    invalidate_cr_library_cache(ctx.library_event_dir.name)
    return h._send_json(200, {
        "ok": True,
        "key": key, "filename": filename,
        "thumb_b64": gallery_b64, "gallery_b64": gallery_b64,
        "tier": tier, "abs_path": dest_path,
        "slim_response": gallery_b64 is None,
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


