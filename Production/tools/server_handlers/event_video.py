"""Event / video / milestone handlers — V59 Phase 4 Pass 1 module 2.

Handlers extracted from production_server.py for:
- /api/event/create, /api/event/load, /api/event/current
- /api/video/list, /api/video/set_active, /api/video/create
- /api/milestones/list, /api/milestones/create, /api/milestones/load
- /api/project/list

Each function takes the live `ProductionHandler` instance as `h`.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from lib.atomic_json_write import atomic_json_write

# V59 Phase 4 cross-review fix (CI follow-up):
# StateManager class referenced by event_create body for fresh state init.
from tools.production_server import (  # noqa: E402
    StateManager,
    _bg_module,
)


def handle_event_create(h, body: dict) -> None:
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
    from production_server import StateManager

    import re as _re
    new_event_id = (body or {}).get("event_id", "")
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
    from lib.event_library import ensure_event_library_dirs
    ensure_event_library_dirs(new_event_dir)
    # Storyboard template — copy current event's storyboard if possible,
    # else create minimal placeholder (lets future event_load satisfy
    # the storyboard_v*_prod.html lookup).
    try:
        src_sb = h.app.storyboard_path
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
    return h._send_json(200, {"ok": True, "event_id": new_event_id,
                                  "event_dir": str(new_event_dir)})


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
        _bg_module().init_bg_paths(new_event_dir)
        # S5.5d (v3): scope-type signal for milestone-aware code paths.
        h.app.scope_type = "event"
        h.app.active_milestone_id = None
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

    Returns:
      {event_id, event_dir, event_generation, active_video, partition_keys}
    on success; {event_id: null} (HTTP 200) on cold-boot when no event
    loaded — null is a valid state, not an error.
    """
    try:
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
    """POST /api/milestones/create — body: {milestone_id, milestone_label?}.

    Validates milestone_id per v3 spec §3.4.1; rejects collision with
    existing milestone (HTTP 409 case-insensitive). Creates
    Production/Milestones/<id>/ with a v3-shaped state.json containing
    videos.standalone partition.
    """
    milestone_id = (body or {}).get("milestone_id")
    milestone_label = (body or {}).get("milestone_label")
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
    return h._send_json(200, {
        "ok": True,
        "milestone_id": milestone_id,
        "milestone_label": milestone_label,
        "milestone_dir": str(target),
        "state_path": str(state_path),
    })


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

    with h.app.event_load_lock:
        old_gen = h.app.event_generation
        h.app.event_generation = old_gen + 1
        h.app.scope_type = "milestone"
        h.app.active_milestone_id = milestone_id
        h.app.milestone_dir = target
        # Clear cross-scope caches (LD-475 cache invalidation extended).
        try:
            h.app._image_overrides = {}
            h.app._pending_override_keys = {}
        except AttributeError:
            pass
        try:
            h.app.invalidate_beats_cache()
        except AttributeError:
            pass
        h.app._storyboard_list_cache = None
        h.app._storyboard_list_cache_mtime = 0.0
        new_gen = h.app.event_generation

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
