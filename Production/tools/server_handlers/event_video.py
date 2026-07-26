"""Event / video / milestone handlers — V59 Phase 4 Pass 1 module 2.

Handlers extracted from production_server.py for:
- /api/event/create, /api/event/load, /api/event/current, /api/event/provision_server
- /api/video/list, /api/video/set_active, /api/video/create
- /api/milestones/list, /api/milestones/create, /api/milestones/load
- /api/project/list

Each function takes the live `ProductionHandler` instance as `h`.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from lib.atomic_json_write import atomic_json_write
from lib.event_server_provision import (
    provision_dedicated_event_server,
    provision_dedicated_event_server_background,
)
from lib.server_port_guard import dedicated_port_for_event_id

# V59 Phase 4 cross-review fix (CI follow-up):
# StateManager class referenced by event_create body for fresh state init.
from tools.production_server import (  # noqa: E402
    StateManager,
    _bg_module,
)


def handle_event_create(h, body: dict) -> None:
    """POST /api/event/create  body: {event_id, event_label?, unexpected?}

    S5.5c+e proper-fix +NewEvent (LD NEW_EVENT_CREATION_UI_V1).
    Constrained creation (2026-07-04): validates against production event map;
    requires unexpected: true when ID is not an expected next slot.
    """
    from production_server import StateManager
    from server_handlers.production_map import (
        backfill_prod_module_from_slot,
        validate_creation_allowed,
    )
    from lib.directus_admin_client import DirectusAdminClient

    import re as _re
    new_event_id = (body or {}).get("event_id", "")
    unexpected = bool((body or {}).get("unexpected"))

    # Constrained creation validation (forward-only, soft-warn).
    try:
        client = DirectusAdminClient()
        prod_modules = client._request(
            "GET",
            "/items/prod_modules?fields=id,m_number,creature_name,spell_name,technique_name&limit=200",
        )
        allowed, err_payload, matched = validate_creation_allowed(
            kind="event",
            requested_id=new_event_id,
            unexpected=unexpected,
            production_root=h.app.event_dir.parent,
            prod_modules=prod_modules,
            bg_module=_bg_module(),
        )
        if not allowed and err_payload:
            return h._send_json(422, err_payload)
    except Exception as _val_exc:
        print(f"[event_create] WARN constrained validation skipped: {_val_exc}", flush=True)
        matched = None
        prod_modules = []
        client = None

    if not new_event_id or not _re.match(r'^[A-Z][A-Za-z0-9_]{2,63}$', new_event_id):
        return h._send_error_v59(
                   400,
                   error_code="EVENT_ID_MUST_MATCH_A",
                   error_message="event_id must match ^[A-Z][A-Za-z0-9_]{2,63}$",
                   retry_safe=False,
                   extra={"ok": False},
               )
    for prefix in ('Test_', '_', 'Tmp_'):
        if new_event_id.startswith(prefix):
            return h._send_error_v59(
                       400,
                       error_code="GENERIC_ERROR",
                       error_message=f"event_id cannot start with reserved prefix {prefix!r}",
                       retry_safe=False,
                       extra={"ok": False},
                   )
    # Case-insensitive uniqueness vs siblings.
    parent = h.app.event_dir.parent
    existing_lower = {p.name.lower() for p in parent.iterdir() if p.is_dir() and p.name.startswith("Event_")}
    if new_event_id.lower() in existing_lower:
        return h._send_error_v59(
                   409,
                   error_code="GENERIC_ERROR",
                   error_message=f"event_id {new_event_id!r} already exists (case-insensitive collision)",
                   retry_safe=False,
                   extra={"ok": False},
               )
    new_event_dir = parent / new_event_id
    # Create dir + initialize state via StateManager (writes v3-shape state.json).
    new_event_dir.mkdir(parents=True, exist_ok=False)
    from lib.event_library import ensure_event_library_dirs, seed_event_watercolors_if_empty

    ensure_event_library_dirs(new_event_dir)
    try:
        seeded = seed_event_watercolors_if_empty(new_event_dir, prod_root=parent)
        if seeded:
            print(
                f"[event_create] seeded {seeded} watercolor(s) into {new_event_id}",
                flush=True,
            )
    except OSError as _wc_err:
        print(f"[event_create] watercolor seed skipped: {_wc_err}", flush=True)
    # Storyboard template — EVENT_SWITCH_STORYBOARD_BUNDLE_SYNC_V1
    try:
        from lib.event_storyboard_bundle_sync import sync_event_storyboard_bundle

        boot = sync_event_storyboard_bundle(
            new_event_dir,
            fallback_source=h.app.storyboard_path if h.app.storyboard_path.is_file() else None,
            force=True,
        )
        if boot.copied:
            print(f"[event_create] storyboard bundle copied from {boot.source}", flush=True)
        elif not boot.ok:
            print(f"[event_create] storyboard copy skipped: {boot.error}", flush=True)
    except Exception as _e:
        print(f"[event_create] storyboard copy skipped: {_e}", flush=True)
    # Init state files (production_state.json + production_spend.json).
    # Numbered Event_N folders store skeleton-backed M-form (Event_3 → M4E1).
    try:
        from lib.module_event_id import canonical_module_event_id

        state_event_id = (
            canonical_module_event_id(new_event_id, production_folder_id=new_event_id)
            or new_event_id
        )
        _ = StateManager(new_event_dir, state_event_id)
    except Exception as _e:
        print(f"[event_create] WARN StateManager init: {_e}", flush=True)
    print(f"[event_create] created {new_event_id} at {new_event_dir}", flush=True)
    # EVENT_STITCH_JOB_BOOTSTRAP_V1 — register canonical stitch job before first Send to Stitcher.
    if dedicated_port_for_event_id(new_event_id) is not None:
        try:
            from server_handlers.stitch_editor import ensure_event_stitch_job_registered

            boot = ensure_event_stitch_job_registered(
                h,
                new_event_id,
                hydrate_from_disk=False,
            )
            if boot.get("changed"):
                print(f"[event_create] stitch bootstrap {boot}", flush=True)
        except Exception as _stitch_boot_exc:
            print(
                f"[event_create] WARN stitch job bootstrap: {_stitch_boot_exc}",
                flush=True,
            )
    # Backfill prod_modules from map on expected-slot creation (Judgment Call 1).
    if matched and client is not None:
        try:
            arc_number, slot = matched
            prod_by_m = {
                int(r["m_number"]): r for r in (prod_modules or []) if r.get("m_number") is not None
            }
            backfill_prod_module_from_slot(
                slot,
                arc_number=arc_number,
                prod_modules_by_m=prod_by_m,
                client=client,
            )
        except Exception as _bf_exc:
            print(f"[event_create] WARN prod_modules backfill: {_bf_exc}", flush=True)
    # EVENT_DEDICATED_SERVER_PROVISION_V1 — kickstart launchd (client awaits provision API).
    if dedicated_port_for_event_id(new_event_id) is not None:
        threading.Thread(
            target=provision_dedicated_event_server_background,
            args=(new_event_id,),
            daemon=True,
            name=f"provision-{new_event_id}",
        ).start()
    return h._send_json(200, {"ok": True, "event_id": new_event_id,
                                  "event_dir": str(new_event_dir)})


def handle_event_provision_server(h, body: dict) -> None:
    """POST /api/event/provision_server — idempotent launchd for Event_N (EVENT_DEDICATED_SERVER_PROVISION_V1)."""
    event_id = str((body or {}).get("event_id") or "").strip()
    if not event_id:
        return h._send_error_v59(
            400,
            error_code="EVENT_ID_REQUIRED",
            error_message="event_id required",
            retry_safe=False,
            extra={"ok": False},
        )
    bundle_sync = None
    try:
        from lib.event_storyboard_bundle_sync import sync_event_storyboard_bundle

        event_dir = h.app.event_dir.parent / event_id
        if event_dir.is_dir():
            bundle_sync = sync_event_storyboard_bundle(
                event_dir,
                fallback_source=h.app.storyboard_path if h.app.storyboard_path.is_file() else None,
            )
            if bundle_sync.copied:
                print(
                    f"[event_provision_server] storyboard bundle synced for {event_id}",
                    flush=True,
                )
    except Exception as _sync_exc:
        print(f"[event_provision_server] WARN bundle sync: {_sync_exc}", flush=True)
    result = provision_dedicated_event_server(event_id)
    status = 200 if result.ok else 503
    payload = result.to_json()
    payload["ok"] = result.ok
    if bundle_sync is not None:
        payload["storyboard_bundle_sync"] = bundle_sync.to_json()
    if not result.ok:
        payload["error_code"] = "EVENT_SERVER_PROVISION_FAILED"
        payload["error_message"] = result.error or "provision failed"
    return h._send_json(status, payload)


def handle_event_load(h, body: dict) -> None:
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
        return h._send_error_v59(
                   400,
                   error_code="EVENT_ID_REQUIRED",
                   error_message="event_id required",
                   retry_safe=False,
                   extra={"code": "EVENT_LOAD_GENERATION_LOCK_V1"},
               )

    # DEDICATED_PORT_SCOPE_TRUTH_V1 — reject before path validation so clients get 409 not 404.
    from lib.server_port_guard import port_to_event_id

    server_port = getattr(h.app, "server_port", None)
    cli_pin = str(getattr(h.app, "cli_pinned_event_id", "") or h.app.event_id or "").strip()
    port_event = port_to_event_id(server_port) if server_port is not None else None
    if port_event and new_event_id != port_event:
        return h._send_error_v59(
            409,
            error_code="DEDICATED_PORT_PIN_IMMUTABLE",
            error_message=(
                f"port {server_port} is dedicated to {port_event}; "
                f"event/load to {new_event_id!r} rejected"
            ),
            retry_safe=False,
            extra={
                "ok": False,
                "code": "DEDICATED_PORT_PIN_IMMUTABLE",
                "server_port": server_port,
                "expected_event_id": port_event,
                "got_event_id": new_event_id,
            },
        )
    if cli_pin and port_event and cli_pin == port_event and new_event_id != cli_pin:
        return h._send_error_v59(
            409,
            error_code="DEDICATED_PORT_PIN_IMMUTABLE",
            error_message=(
                f"server CLI pin is {cli_pin}; event/load to {new_event_id!r} rejected"
            ),
            retry_safe=False,
            extra={
                "ok": False,
                "code": "DEDICATED_PORT_PIN_IMMUTABLE",
                "expected_event_id": cli_pin,
                "got_event_id": new_event_id,
            },
        )

    # event_dir is sibling of current — we do NOT allow arbitrary paths.
    # Pattern: Production/<event_id>/ next to current Production/<current>/.
    from lib.paths import normalize_event_dir, runtime_production_root

    prod_root = runtime_production_root(h.app.event_dir)
    new_event_dir = normalize_event_dir(prod_root / new_event_id)
    if not new_event_dir.is_dir():
        return h._send_error_v59(
                   404,
                   error_code="EVENT_DIR_NOT_FOUND",
                   error_message="event_dir not found",
                   retry_safe=False,
                   extra={"code": "EVENT_LOAD_GENERATION_LOCK_V1", "expected": str(new_event_dir), "hint": f"event_id {new_event_id!r} must correspond to an "
                f"existing directory at {new_event_dir}."},
               )

    # Storyboard pick: explicit body['storyboard'], else keep current
    # filename (works if every event uses the same storyboard naming).
    # Else discover the latest storyboard_v*_prod.html in the new dir.
    requested_sb = (body or {}).get("storyboard")
    if requested_sb:
        new_storyboard_path = new_event_dir / requested_sb
    elif (new_event_dir / h.app.storyboard_path.name).exists():
        new_storyboard_path = new_event_dir / h.app.storyboard_path.name
    else:
        candidates = sorted(
            new_event_dir.glob("storyboard_v*_prod.html"),
            key=lambda p: p.stat().st_mtime, reverse=True,
        )
        if not candidates:
            return h._send_error_v59(
                       404,
                       error_code="NO_STORYBOARD_V_PROD_HTML",
                       error_message="no storyboard_v*_prod.html in target event_dir",
                       retry_safe=False,
                       extra={"code": "EVENT_LOAD_GENERATION_LOCK_V1", "event_dir": str(new_event_dir)},
                   )
        new_storyboard_path = candidates[0]

    if not new_storyboard_path.is_file():
        return h._send_error_v59(
                   404,
                   error_code="STORYBOARD_FILE_NOT_FOUND",
                   error_message="storyboard file not found",
                   retry_safe=False,
                   extra={"code": "EVENT_LOAD_GENERATION_LOCK_V1", "expected": str(new_storyboard_path)},
               )

    # EVENT_LOAD_IDEMPOTENT_REPIN_V1 — if this port already serves exactly the
    # requested event scope, answer without the swap. The full path below runs
    # a sidecar reconcile that walks kling_o3_clips on Dropbox under
    # event_load_lock; after a fleet restart that walk takes minutes, and every
    # client retry (deploy g.5 pin, UI reload) queued another full walk behind
    # the lock — the queue grew faster than it drained, so event/load appeared
    # hung forever while /api/event/current answered fine. A no-op re-pin must
    # not pay for a scope change it isn't making, and must not take the lock
    # (taking it would queue behind the very pileup this exists to avoid; the
    # attribute reads are benign — a racing real swap just means the caller
    # re-pins against the post-swap scope on retry). Generation is unchanged:
    # nothing swapped, so async jobs pinned to it stay valid (LD-460).
    def _same_path(a, b) -> bool:
        try:
            return Path(a).resolve() == Path(b).resolve()
        except OSError:
            return False

    if (
        _same_path(h.app.event_dir, new_event_dir)
        and _same_path(h.app.storyboard_path, new_storyboard_path)
        and getattr(h.app, "scope_type", "event") == "event"
        and getattr(h.app, "active_milestone_id", None) is None
    ):
        return h._send_json(200, {
            "ok": True,
            "event_id": new_event_id,
            "event_dir": str(new_event_dir),
            "storyboard": new_storyboard_path.name,
            "event_generation": h.app.event_generation,
            "previous_generation": h.app.event_generation,
            "previous_event_id": new_event_id,
            "already_loaded": True,
        })

    # ATOMIC SWAP under lock.
    with h.app.event_load_lock:
        old_gen = h.app.event_generation
        old_event_id = h.app.event_dir.name
        old_storyboard = h.app.storyboard_path.name

        h.app.event_dir = new_event_dir
        h.app.storyboard_path = new_storyboard_path
        h.app.event_id = new_event_id
        h.app.storyboard_stem = new_storyboard_path.stem
        h.app.event_generation = old_gen + 1
        # S5 v3.1 fix — StateManager caches state_path at construct time.
        # On event swap we must re-point it so subsequent state reads/writes
        # hit the NEW event's production_state.json (was reading Event_1's
        # state regardless of swap).
        try:
            h.app.state.event_dir = new_event_dir
            h.app.state.state_path = new_event_dir / "production_state.json"
            h.app.state.event_id = new_event_id
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
            h.app._image_overrides = {}
            h.app._pending_override_keys = {}
            print(
                f"[event/load] cleared image override cache "
                f"(event swap to {new_event_id})",
                flush=True,
            )
        except AttributeError:
            pass
        h.app.invalidate_beats_cache()
        h.app._storyboard_list_cache = None
        h.app._storyboard_list_cache_mtime = 0.0
        # Rebind BG stills/sidecar paths so /api/cr/library and Beat Gen scan
        # the loaded event's beat_generator_stills/, not the startup pin.
        # S5.5d (v3): scope-type signal for milestone-aware code paths.
        h.app.scope_type = "event"
        h.app.active_milestone_id = None
        h.app.milestone_dir = None
        h.app.milestone_library_event_dir = None
        from lib.milestone_scope_persist import clear_persisted_milestone_scope
        from lib.paths import runtime_production_root

        clear_persisted_milestone_scope(runtime_production_root(new_event_dir))
        _bg_module().init_bg_paths(new_event_dir, clear_milestone_scope=True)
        # EVENT_LOAD_SIDECAR_RECONCILE_V1 — milestone beats must not occupy event SQLite;
        # restore completed event segments from kling_o3_clips/_preserved on disk.
        try:
            bg = _bg_module()
            rep = bg.reconcile_event_sidecar_after_milestone_exit(
                new_event_dir, new_event_id,
            )
            if rep.get("restored_segments") or rep.get("removed_segments"):
                print(f"[event/load] sidecar reconcile {rep}", flush=True)
        except Exception as exc:
            print(f"[event/load] WARN: sidecar reconcile failed: {exc}", flush=True)
        new_gen = h.app.event_generation
        try:
            from lib.event_pin import write_persisted_event_pin

            write_persisted_event_pin(
                runtime_production_root(new_event_dir),
                event_id=new_event_id,
                storyboard=new_storyboard_path.name,
                event_dir=new_event_dir,
                source="event_load",
            )
        except Exception as exc:
            print(f"[event/load] WARN: could not persist event pin: {exc}", flush=True)

    print(
        f"[event/load] {old_event_id} (gen={old_gen}, sb={old_storyboard}) -> "
        f"{new_event_id} (gen={new_gen}, sb={new_storyboard_path.name}). "
        f"Async jobs pinned to gen {old_gen} will be rejected at terminal "
        f"writes per LD-460.",
        flush=True,
    )

    return h._send_json(200, {
        "ok": True,
        "event_id": new_event_id,
        "event_dir": str(new_event_dir),
        "storyboard": new_storyboard_path.name,
        "event_generation": new_gen,
        "previous_generation": old_gen,
        "previous_event_id": old_event_id,
    })


def handle_event_current(h) -> None:
    """GET /api/event/current — return the currently-loaded event.

    Bug 4 fix per S5.5b spec §3 + Cursor v5 verbatim recommendation.
    ScopeBoundary on boot can call this to know which event the server
    is serving (URL/data-attr/window-global fallbacks may be stale after
    EventSelector triggers a `/api/event/load` + `window.location.reload()`).

    SCOPE_RESTART_RECONCILE_V1: HTTP 503 until app.scope_ready (startup pin complete).

    Returns:
      {event_id, event_dir, event_generation, active_video, partition_keys}
    on success; {event_id: null} (HTTP 200) on cold-boot when no event
    loaded — null is a valid state, not an error.
    """
    if not getattr(h.app, "scope_ready", True):
        return h._send_error_v59(
            503,
            error_code="SCOPE_NOT_READY",
            error_message="scope_not_ready",
            retry_safe=True,
            hint="Server is starting — retry event/current shortly.",
            extra={"ok": False, "event_id": None},
        )
    try:
        if getattr(h.app, "scope_type", "event") == "milestone" and getattr(h.app, "active_milestone_id", None):
            from lib.milestone_store import ensure_milestone_runtime_fields, load_milestone_state

            mdir = h.app.milestone_dir or (h._milestones_root() / h.app.active_milestone_id)
            state = ensure_milestone_runtime_fields(mdir) if mdir.is_dir() else {}
            videos = state.get("videos") or {}
            return h._send_json(200, {
                "ok": True,
                "event_id": h.app.event_id,
                "event_dir": str(h.app.event_dir),
                "event_generation": h.app.event_generation,
                "active_video": state.get("active_video") or "standalone",
                "partition_keys": sorted(videos.keys()) if videos else ["standalone"],
                "scope_type": "milestone",
                "active_milestone_id": h.app.active_milestone_id,
                "milestone_label": state.get("milestone_label"),
                "milestone_dir": str(mdir),
            })
        state = h.app.state.read_state()
        videos = state.get("videos") or {}
        return h._send_json(200, {
            "ok": True,
            "event_id": h.app.event_id,
            "event_dir": str(h.app.event_dir),
            "event_generation": h.app.event_generation,
            "active_video": state.get("active_video"),
            "partition_keys": sorted(videos.keys()),
            "scope_type": getattr(h.app, "scope_type", "event"),
            "active_milestone_id": getattr(h.app, "active_milestone_id", None),
        })
    except AttributeError:
        # No event loaded (cold boot before any /api/event/load).
        return h._send_json(200, {"ok": True, "event_id": None})


def handle_video_list(h) -> None:
    """GET /api/video/list — return the partition list for the loaded event.

    Wraps StateManager.list_videos(). Read-only; no scope guard required
    (returns metadata about the currently-loaded event only).
    """
    try:
        videos = h.app.state.list_videos()
        state = h.app.state.read_state()
        return h._send_json(200, {
            "ok": True,
            "event_id": h.app.event_id,
            "active_video": state.get("active_video"),
            "videos": videos,
        })
    except Exception as exc:  # noqa: BLE001
        return h._send_error_v59(
                   500,
                   error_code="GENERIC_ERROR",
                   error_message=f"failed to list videos: {type(exc).__name__}: {exc}",
                   retry_safe=True,
                   extra={"ok": False},
               )


def handle_video_set_active(h, body: dict) -> None:
    """POST /api/video/set_active — persist active video + switch Beat Gen context.

    Body: {scope_event_id, video_role}. Validates video_role against
    canonical set + presence in state.videos via state.validate_video_role.

    Writes ``state.active_video`` (display hint for reload UX) AND atomically:
      - preserves outgoing BG segment (Kling O3 clips + sidecar beats)
      - switches sidecar ``active_context`` to the target segment
      - intro-only: seeds canonical mirror tail when loading intro

    Partition selection on other handlers still comes ONLY from
    ``body['scope_video_role']`` per LD-474 — not from ``state.active_video``.
    """
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return
    video_role = (body or {}).get("video_role")
    if not video_role:
        return h._send_error_v59(
                   400,
                   error_code="VIDEO_ROLE_REQUIRED",
                   error_message="video_role required",
                   retry_safe=False,
                   extra={"ok": False, "code": "VIDEO_ROLE_INVALID", "valid": sorted(h.app.state._VALID_VIDEO_ROLES)},
               )
    if not h.app.state.validate_video_role(video_role):
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=f"video_role {video_role!r} not valid for this event",
                   retry_safe=False,
                   extra={"ok": False, "code": "VIDEO_ROLE_INVALID", "got": video_role, "valid": sorted(h.app.state._VALID_VIDEO_ROLES), "hint": "must be in canonical set AND exist in state.videos."},
               )

    scope_event_id = h._scope_body(body).get("scope_event_id") or h.app.event_id
    prior_state = h.app.state.read_state()
    from_video_role = prior_state.get("active_video")

    from server_handlers.background import switch_bg_context_for_video_role

    bg_switch = switch_bg_context_for_video_role(
        h,
        scope_event_id,
        from_video_role if isinstance(from_video_role, str) else None,
        video_role,
    )

    # Write state.active_video at the top level (not partition-scoped).
    def _set_active(state, _role=video_role):
        state["active_video"] = _role

    h.app.state.mutate_state(_set_active)
    return h._send_json(200, {
        "ok": True,
        "event_id": h.app.event_id,
        "active_video": video_role,
        "bg_switch": bg_switch,
    })


def handle_video_create(h, body: dict) -> None:
    """POST /api/video/create — add a new video partition.

    Body: {scope_event_id, video_role, video_label?}. Wraps
    StateManager.create_video. Returns 400 on invalid role; 409 on
    duplicate (partition already exists).
    """
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return
    video_role = (body or {}).get("video_role")
    video_label = (body or {}).get("video_label")
    if not video_role:
        return h._send_error_v59(
                   400,
                   error_code="VIDEO_ROLE_REQUIRED",
                   error_message="video_role required",
                   retry_safe=False,
                   extra={"ok": False, "code": "VIDEO_ROLE_INVALID", "valid": sorted(h.app.state._VALID_VIDEO_ROLES)},
               )
    try:
        created = h.app.state.create_video(video_role, video_label)
    except ValueError as exc:
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=str(exc),
                   retry_safe=False,
                   extra={"ok": False, "code": "VIDEO_ROLE_INVALID", "valid": sorted(h.app.state._VALID_VIDEO_ROLES)},
               )
    if not created:
        return h._send_error_v59(
                   409,
                   error_code="GENERIC_ERROR",
                   error_message=f"partition {video_role!r} already exists",
                   retry_safe=False,
                   extra={"ok": False, "code": "VIDEO_ROLE_DUPLICATE"},
               )
    return h._send_json(200, {
        "ok": True,
        "event_id": h.app.event_id,
        "video_role": video_role,
        "video_label": video_label,
    })


def handle_milestones_list(h, body: dict | None = None) -> None:
    """GET /api/milestones/list — return all milestones (cold-safe)."""
    root = h._milestones_root()
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
    return h._send_json(200, {
        "ok": True,
        "milestones": milestones,
        "milestones_root": str(root),
    })


def handle_milestones_create(h, body: dict) -> None:
    """POST /api/milestones/create — body: {milestone_id, milestone_label?, unexpected?}.

    Validates milestone_id per v3 spec §3.4.1; constrained creation checks production
    event map (2026-07-04). Requires unexpected: true for unplanned IDs.
    """
    from server_handlers.production_map import validate_creation_allowed

    milestone_id = (body or {}).get("milestone_id")
    milestone_label = (body or {}).get("milestone_label")
    unexpected = bool((body or {}).get("unexpected"))

    try:
        from lib.directus_admin_client import DirectusAdminClient

        client = DirectusAdminClient()
        prod_modules = client._request(
            "GET",
            "/items/prod_modules?fields=id,m_number,creature_name,spell_name&limit=200",
        )
        allowed, err_payload, _matched = validate_creation_allowed(
            kind="milestone",
            requested_id=str(milestone_id or ""),
            unexpected=unexpected,
            production_root=h.app.event_dir.parent,
            prod_modules=prod_modules,
        )
        if not allowed and err_payload:
            return h._send_json(422, err_payload)
    except Exception as _val_exc:
        print(f"[milestones_create] WARN constrained validation skipped: {_val_exc}", flush=True)

    ok, err = h._validate_milestone_id(milestone_id)
    if not ok:
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=err,
                   retry_safe=False,
                   extra={"ok": False, "code": "MILESTONE_ID_INVALID"},
               )

    root = h._milestones_root()
    root.mkdir(parents=True, exist_ok=True)

    # Case-insensitive collision check.
    target = root / milestone_id
    existing_lower = {p.name.lower() for p in root.iterdir() if p.is_dir()}
    if milestone_id.lower() in existing_lower:
        return h._send_error_v59(
                   409,
                   error_code="GENERIC_ERROR",
                   error_message=f"milestone {milestone_id!r} already exists (case-insensitive collision)",
                   retry_safe=False,
                   extra={"ok": False, "code": "MILESTONE_ID_DUPLICATE"},
               )

    target.mkdir(parents=True, exist_ok=False)
    # Animation clips dir (mirrors Event_<N> layout).
    (target / "animation_clips").mkdir(exist_ok=True)
    (target / "animation_clips_final").mkdir(exist_ok=True)
    from lib.event_library import ensure_event_library_dirs

    skel = (body or {}).get("skeleton_ref")
    if not isinstance(skel, dict):
        from lib.milestone_store import resolve_milestone_skeleton_ref

        skel = resolve_milestone_skeleton_ref({}, milestone_id)
    lib_event = (body or {}).get("library_event_id") or skel.get("library_event_id")
    if lib_event:
        lib_dir = root.parent / str(lib_event)
        if lib_dir.is_dir():
            ensure_event_library_dirs(lib_dir)

    now_iso = datetime.now(timezone.utc).isoformat()
    state = {
        "milestone_id": milestone_id,
        "milestone_label": milestone_label,
        "version": "v3",
        "created_at": now_iso,
        "updated_at": now_iso,
        "active_video": "standalone",
        "scope_type": "milestone",
        "skeleton_ref": {
            "arc_number": int(skel.get("arc_number") or 1),
            "event_id": str(skel.get("event_id")),
            "phase": str(skel.get("phase") or "full"),
        },
        "library_event_id": lib_event,
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
    return h._send_json(200, {
        "ok": True,
        "milestone_id": milestone_id,
        "milestone_label": milestone_label,
        "milestone_dir": str(target),
        "state_path": str(state_path),
    })


def apply_milestone_scope_to_app(app, milestone_id: str, *, source: str = "milestone_load") -> int:
    """Switch app to milestone scope (shared by HTTP handler + startup restore)."""
    target = app.event_dir.parent / "Milestones" / milestone_id
    if not target.is_dir():
        raise FileNotFoundError(f"milestone {milestone_id!r} not found at {target}")
    state_path = target / "state.json"
    if not state_path.is_file():
        raise FileNotFoundError(f"milestone state.json missing at {state_path}")

    with app.event_load_lock:
        app.event_generation = app.event_generation + 1
        app.scope_type = "milestone"
        app.active_milestone_id = milestone_id
        app.milestone_dir = target
        from lib.milestone_store import ensure_milestone_runtime_fields

        mstate = ensure_milestone_runtime_fields(target)
        skel = mstate.get("skeleton_ref") or {}
        lib_name = mstate.get("library_event_id") or f"Event_{skel.get('arc_number', 1)}"
        lib_dir = app.event_dir.parent / str(lib_name)
        app.milestone_library_event_dir = lib_dir if lib_dir.is_dir() else app.event_dir
        _bg_module().init_bg_paths(
            app.milestone_library_event_dir,
            milestone_dir=target,
            library_event_dir=app.milestone_library_event_dir,
        )
        bg = _bg_module()
        try:
            def _heal_continuity(sidecar: dict) -> None:
                if bg.heal_sidecar_beat_continuity(sidecar):
                    print(
                        f"[milestone/{source}] beat continuity healed for {milestone_id}",
                        flush=True,
                    )

            bg.mutate_sidecar_locked(_heal_continuity)
        except Exception as exc:
            print(
                f"[milestone/{source}] beat continuity heal skipped for {milestone_id}: {exc}",
                flush=True,
            )
        try:
            app._image_overrides = {}
            app._pending_override_keys = {}
        except AttributeError:
            pass
        try:
            app.invalidate_beats_cache()
        except AttributeError:
            pass
        app._storyboard_list_cache = None
        app._storyboard_list_cache_mtime = 0.0
        new_gen = app.event_generation

    from lib.milestone_scope_persist import write_persisted_milestone_scope
    from lib.paths import runtime_production_root

    write_persisted_milestone_scope(
        runtime_production_root(app.event_dir),
        event_id=app.event_id,
        milestone_id=milestone_id,
        source=source,
    )
    return new_gen


def handle_milestone_load(h, body: dict) -> None:
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
    ok, err = h._validate_milestone_id(milestone_id)
    if not ok:
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=err,
                   retry_safe=False,
                   extra={"ok": False, "code": "MILESTONE_ID_INVALID"},
               )

    target = h._milestones_root() / milestone_id
    if not target.is_dir():
        return h._send_error_v59(
                   404,
                   error_code="GENERIC_ERROR",
                   error_message=f"milestone {milestone_id!r} not found at {target}",
                   retry_safe=False,
                   extra={"ok": False, "code": "MILESTONE_NOT_FOUND"},
               )
    state_path = target / "state.json"
    if not state_path.is_file():
        return h._send_error_v59(
                   404,
                   error_code="GENERIC_ERROR",
                   error_message=f"milestone state.json missing at {state_path}",
                   retry_safe=False,
                   extra={"ok": False, "code": "MILESTONE_STATE_MISSING"},
               )

    old_gen = h.app.event_generation
    try:
        new_gen = apply_milestone_scope_to_app(h.app, milestone_id, source="load")
    except FileNotFoundError as exc:
        return h._send_error_v59(
            404,
            error_code="GENERIC_ERROR",
            error_message=str(exc),
            retry_safe=False,
            extra={"ok": False, "code": "MILESTONE_NOT_FOUND"},
        )

    print(
        f"[milestone/load] -> {milestone_id} (gen={new_gen}, dir={target}). "
        f"scope_type='milestone'. Async jobs pinned to gen {old_gen} will be "
        f"rejected at terminal writes per LD-460.",
        flush=True,
    )

    return h._send_json(200, {
        "ok": True,
        "milestone_id": milestone_id,
        "milestone_dir": str(target),
        "event_generation": new_gen,
        "previous_generation": old_gen,
        "scope_type": "milestone",
    })


def handle_project_list(h, body: dict | None = None) -> None:
    """GET /api/project/list — combined Events + Milestones for the
    v59 ProjectSelector dropdown.

    Returns:
        {events: [...], milestones: [...], scope_type, active_event_id,
         active_milestone_id}
    """
    # Events: leverage existing _handle_event_list orchestration.
    production_root = h.app.event_dir.parent
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

    milestones_root = h._milestones_root()
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

    return h._send_json(200, {
        "ok": True,
        "events": events,
        "milestones": milestones,
        "scope_type": getattr(h.app, "scope_type", "event"),
        "active_event_id": h.app.event_id,
        "active_milestone_id": getattr(h.app, "active_milestone_id", None),
    })
