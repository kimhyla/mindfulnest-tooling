"""Scope activation helpers for production server handlers."""
from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Any

from lib.scope_context import (
    ScopeContext,
    normalize_milestone_video_role,
    resolve_scope_from_app,
    scope_body_with_milestone,
)


def _bg_module():
    from tools.production_server import _bg_module as _host_bg_module  # noqa: PLC0415

    return _host_bg_module()


# ThreadingHTTPServer + module-level init_bg_paths globals — serialize scope
# activation and Beat Gen reads/writes that depend on BG_* path constants.
_BG_SCOPE_LOCK = threading.RLock()


@contextmanager
def production_bg_scope_lock():
    """Hold while a handler uses beat_generator paths after scope activation."""
    bg = _bg_module()
    with bg.bg_scope_lock():
        yield


def rebind_bg_paths_from_app(app) -> None:
    """Re-init beat_generator path globals from pinned app scope (milestone XOR event).

    Handlers must not call ``init_bg_paths(app.event_dir)`` while milestone scope is
    active — that tears JSON-only milestone authority and reads stale global SQLite.
    """
    bg = _bg_module()
    if getattr(app, "scope_type", "event") == "milestone" and getattr(app, "milestone_dir", None):
        lib = getattr(app, "milestone_library_event_dir", None) or app.event_dir
        skel = None
        try:
            from lib.milestone_store import load_milestone_state, resolve_milestone_skeleton_ref

            mid = getattr(app, "active_milestone_id", None)
            state = load_milestone_state(app.milestone_dir)
            skel = resolve_milestone_skeleton_ref(state, mid) if mid else None
        except Exception:
            skel = None
        bg.set_milestone_skeleton_ref(skel)
        bg.init_bg_paths(
            lib,
            milestone_dir=app.milestone_dir,
            library_event_dir=lib,
        )
        return
    bg.set_milestone_skeleton_ref(None)
    bg.init_bg_paths(app.event_dir, clear_milestone_scope=True)


def parse_scope_query(handler) -> dict:
    qs = __import__("urllib").parse.parse_qs(__import__("urllib").parse.urlparse(handler.path).query)
    out: dict = {}
    for key in (
        "scope_event_id", "event_id", "scope_milestone_id", "milestone_id",
        "scope_video_role", "scope_target_video", "scope_arc_number", "arc_number",
        "scope_phase", "phase",
    ):
        vals = qs.get(key)
        if vals:
            out[key] = vals[0]
    return out


def resolve_scope(handler, body_or_qs: dict | None = None, *, default_video_role: str | None = None) -> ScopeContext | None:
    result = resolve_scope_from_app(handler.app, body_or_qs, default_video_role=default_video_role)
    if isinstance(result, tuple):
        status, err = result
        handler._send_error_v59(
            status,
            error_code=str(err.get("error_code") or err.get("code") or "SCOPE_ERROR"),
            error_message=str(err.get("error_message") or err.get("error") or "scope error"),
            retry_safe=status >= 500,
            extra=err,
        )
        return None
    return result


def activate_bg_for_scope(handler, ctx: ScopeContext, *, repair_sidecar: bool = True) -> None:
    bg = _bg_module()
    if ctx.is_milestone:
        skel = ctx.skeleton_ref or {}
        bg.set_milestone_skeleton_ref(skel)
        bg.init_bg_paths(
            ctx.library_event_dir,
            milestone_dir=ctx.root_dir,
            library_event_dir=ctx.library_event_dir,
        )
        if repair_sidecar:
            try:
                if bg.ensure_milestone_sidecar_isolated(persist=True):
                    print(
                        f"[milestone] pruned polluted sidecar segments for {ctx.milestone_id}",
                        flush=True,
                    )
            except Exception as exc:
                print(
                    f"[milestone] sidecar isolation failed for {ctx.milestone_id}: {exc}",
                    flush=True,
                )
    else:
        bg.set_milestone_skeleton_ref(None)
        bg.init_bg_paths(ctx.root_dir, clear_milestone_scope=True)


def assert_production_scope(
    handler,
    body: dict | None,
    *,
    allow_missing: bool = False,
    allow_missing_video_role: bool = False,
    repair_sidecar: bool = True,
) -> ScopeContext | None:
    """Unified scope gate — milestone XOR event. Returns ScopeContext or None (response sent)."""
    scoped = scope_body_with_milestone(body, handler.app)
    wants_milestone = bool(
        scoped.get("scope_milestone_id") or scoped.get("milestone_id")
    ) or getattr(handler.app, "scope_type", "event") == "milestone"
    # Dedicated event servers (Event_2 on :5112, Event_3 on :5113, …) must never
    # activate *production* milestone scope from a stale ?milestone= URL — that
    # path runs milestone sidecar isolation against the shared global sidecar/SQLite
    # store and can delete Event beat rows.
    #
    # Stitch mutations use STITCH_SCOPE_PARTITION_V1 (server_handlers/stitch_scope.py)
    # instead: resolve Milestones/<id>/stitch_state.json without BG activation.
    if wants_milestone and getattr(handler.app, "scope_type", "event") == "event":
        scoped.pop("scope_milestone_id", None)
        scoped.pop("milestone_id", None)
        wants_milestone = False
    if wants_milestone:
        mid = (
            scoped.get("scope_milestone_id")
            or scoped.get("milestone_id")
            or getattr(handler.app, "active_milestone_id", None)
        )
        if not mid:
            if allow_missing:
                return resolve_scope(handler, scoped, default_video_role="standalone")
            handler._send_error_v59(
                400,
                error_code="SCOPE_REQUIRED",
                error_message="scope_milestone_id required in milestone scope",
                retry_safe=False,
                extra={"code": "MILESTONE_SCOPE_REQUIRED"},
            )
            return None
        active = getattr(handler.app, "active_milestone_id", None)
        if getattr(handler.app, "scope_type", "event") == "milestone" and active and str(mid) != str(active):
            handler._send_error_v59(
                409,
                error_code="SCOPE_MISMATCH",
                error_message="milestone scope mismatch",
                retry_safe=False,
                extra={"expected_milestone_id": active, "got_milestone_id": mid},
            )
            return None
        ctx = resolve_scope(handler, scoped, default_video_role="standalone")
        if ctx is None:
            return None
        if not allow_missing_video_role:
            role = (
                scoped.get("scope_target_video")
                or scoped.get("scope_video_role")
                or ("standalone" if ctx.is_milestone else None)
            )
            if role:
                if ctx.is_milestone:
                    role = normalize_milestone_video_role(role)
                    from lib.milestone_store import load_milestone_state

                    vids = (load_milestone_state(ctx.root_dir).get("videos") or {})
                    if role not in vids:
                        handler._send_error_v59(
                            400,
                            error_code="VIDEO_ROLE_INVALID",
                            error_message=f"video_role {role!r} not valid for milestone",
                            retry_safe=False,
                            extra={"code": "VIDEO_ROLE_INVALID", "got": role, "valid": sorted(vids.keys())},
                        )
                        return None
                elif not handler.app.state.validate_video_role(role):
                    handler._send_error_v59(
                        400,
                        error_code="VIDEO_ROLE_INVALID",
                        error_message="video_role_invalid",
                        retry_safe=False,
                        extra={
                            "code": "VIDEO_ROLE_INVALID",
                            "got": role,
                            "valid": sorted(handler.app.state._VALID_VIDEO_ROLES),
                        },
                    )
                    return None
        activate_bg_for_scope(handler, ctx, repair_sidecar=repair_sidecar)
        handler._production_scope_ctx = ctx
        return ctx

    if not handler._assert_event_scope(scoped, allow_missing=allow_missing, allow_missing_video_role=allow_missing_video_role):
        return None
    ctx = resolve_scope(handler, scoped)
    if ctx is None:
        return None
    if not allow_missing_video_role:
        role = scoped.get("scope_target_video") or scoped.get("scope_video_role")
        if role and not handler.app.state.validate_video_role(role):
            handler._send_error_v59(
                400,
                error_code="VIDEO_ROLE_INVALID",
                error_message="video_role_invalid",
                retry_safe=False,
                extra={
                    "code": "VIDEO_ROLE_INVALID",
                    "got": role,
                    "valid": sorted(handler.app.state._VALID_VIDEO_ROLES),
                },
            )
            return None
    activate_bg_for_scope(handler, ctx, repair_sidecar=repair_sidecar)
    handler._production_scope_ctx = ctx
    return ctx


def milestone_bg_segment(ctx: ScopeContext) -> dict:
    skel = ctx.skeleton_ref or {}
    arc = int(skel.get("arc_number") or 1)
    event_id = str(skel.get("event_id") or ctx.milestone_id)
    phase = str(skel.get("phase") or "main")
    name = skel.get("display_name") or ctx.milestone_id
    bg = _bg_module()
    for seg in bg.get_segments(arc):
        if str(seg.get("event_id")) == event_id and seg.get("phase") == phase:
            name = seg.get("name") or name
            break
    return {
        "segment_index": 0,
        "name": name,
        "event_id": event_id,
        "event_type": "Milestone",
        "phase": phase,
        "milestone_id": ctx.milestone_id,
        "arc_number": arc,
        "scope_type": "milestone",
    }


def stitch_state_for_scope(app: Any, ctx: ScopeContext):
    from tools.production_server import StitchEditorState  # noqa: PLC0415

    if ctx.is_milestone:
        path = ctx.root_dir / "stitch_state.json"
        return StitchEditorState(path)
    return getattr(app, "_event_stitch_state", None) or app.stitch_state
