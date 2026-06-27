"""STITCH_SCOPE_PARTITION_V1 — stitch data-partition scope (no BG / sidecar activation).

Dedicated Event_N servers (Event_2 on :5112, Event_3 on :5113, …) intentionally
reject *production* milestone scope in ``assert_production_scope`` because
activating milestone Beat Gen paths runs sidecar isolation against shared global
SQLite and can delete Event beat rows (see milestone_scope.py).

Stitch mutations are different: they read/write ``Milestones/<id>/stitch_state.json``
keyed by job name. That partition must resolve from ``scope_milestone_id`` or
``milestone_<id>_stitch`` on dedicated event servers without activating BG.

Invariant: stitch handlers use ``assert_stitch_partition_scope`` — never
``assert_production_scope`` / ``_assert_event_scope`` alone for milestone jobs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lib.scope_context import (
    MILESTONE_VIDEO_ROLE,
    ScopeContext,
    normalize_milestone_video_role,
    resolve_scope_from_app,
    scope_body_with_milestone,
)

STITCH_SCOPE_PARTITION_V1 = "STITCH_SCOPE_PARTITION_V1"


@dataclass(frozen=True)
class StitchScopeBinding:
    """Resolved stitch store + job identity for one mutation."""

    ctx: ScopeContext
    stitch_store: Any
    job_name: str


def _milestone_id_from_stitch_job_name(job_name: str) -> str | None:
    prefix = "milestone_"
    suffix = "_stitch"
    if not (job_name.startswith(prefix) and job_name.endswith(suffix)):
        return None
    mid = job_name[len(prefix) : -len(suffix)].strip()
    return mid or None


def _is_milestone_stitch_job_name(job_name: str) -> bool:
    return _milestone_id_from_stitch_job_name(job_name) is not None


def _stitch_milestone_job_name(milestone_id: str) -> str:
    return f"milestone_{milestone_id}_stitch"


def _is_canonical_event_stitch_job_name(job_name: str) -> bool:
    import re

    return bool(re.match(r"^Event_\d+_stitch$", str(job_name or "").strip()))


def assert_stitch_partition_scope(
    handler,
    body: dict | None,
    *,
    job_name: str = "",
) -> StitchScopeBinding | None:
    """Resolve stitch partition + validate video role on the owning store.

    Does NOT call ``activate_bg_for_scope`` — safe on event-dedicated servers.
    Returns None after sending an HTTP error response.
    """
    from server_handlers.milestone_scope import stitch_state_for_scope  # noqa: PLC0415

    b = dict(body or {})
    name = (job_name or b.get("name") or "").strip()
    scoped = scope_body_with_milestone(b, handler.app)

    mid_from_job = _milestone_id_from_stitch_job_name(name) if name else None
    if mid_from_job:
        scoped["scope_milestone_id"] = mid_from_job

    ctx_result = resolve_scope_from_app(
        handler.app,
        scoped,
        default_video_role=MILESTONE_VIDEO_ROLE,
    )
    if isinstance(ctx_result, tuple):
        status, err = ctx_result
        handler._send_error_v59(
            status,
            error_code=str(err.get("error_code") or err.get("code") or "SCOPE_ERROR"),
            error_message=str(err.get("error_message") or err.get("error") or "scope error"),
            retry_safe=status >= 500,
            extra=err,
        )
        return None

    ctx = ctx_result
    server_event = handler.app.event_dir.name
    req_event = (scoped.get("event_id") or "").strip()
    if req_event and req_event != server_event:
        handler._send_error_v59(
            409,
            error_code="SCOPE_MISMATCH",
            error_message="scope_mismatch",
            retry_safe=False,
            extra={
                "code": "SCOPE_VALIDATION_V1",
                "expected_event_id": server_event,
                "got_event_id": req_event,
                "hint": (
                    "Dedicated event server serves one Event_N pin; "
                    "scope_event_id must match the server event_dir."
                ),
            },
        )
        return None

    resolved_job = name or ctx.stitch_job_name
    role = str(ctx.video_role or "").strip()
    if ctx.is_milestone:
        role = normalize_milestone_video_role(role)
        from lib.milestone_store import load_milestone_state  # noqa: PLC0415

        vids = (load_milestone_state(ctx.root_dir).get("videos") or {})
        if vids and role not in vids:
            handler._send_error_v59(
                400,
                error_code="VIDEO_ROLE_INVALID",
                error_message=f"video_role {role!r} not valid for milestone",
                retry_safe=False,
                extra={
                    "code": "VIDEO_ROLE_INVALID",
                    "got": role,
                    "valid": sorted(vids.keys()),
                    "partition_code": STITCH_SCOPE_PARTITION_V1,
                },
            )
            return None
    elif _is_canonical_event_stitch_job_name(resolved_job):
        # Event_N_stitch edits slot media only — never activate BG video partitions.
        # Do not map intro/resolution → standalone (normalize_milestone_video_role).
        if role not in handler.app.state._VALID_VIDEO_ROLES:
            handler._send_error_v59(
                400,
                error_code="VIDEO_ROLE_INVALID",
                error_message="video_role_invalid",
                retry_safe=False,
                extra={
                    "code": "VIDEO_ROLE_INVALID",
                    "got": role,
                    "valid": sorted(handler.app.state._VALID_VIDEO_ROLES),
                    "partition_code": STITCH_SCOPE_PARTITION_V1,
                    "event_stitch_scope": "STITCH_EVENT_STITCH_SCOPE_V1",
                },
            )
            return None
    else:
        role = normalize_milestone_video_role(role)
        if not handler.app.state.validate_video_role(role):
            handler._send_error_v59(
                400,
                error_code="VIDEO_ROLE_INVALID",
                error_message="video_role_invalid",
                retry_safe=False,
                extra={
                    "code": "VIDEO_ROLE_INVALID",
                    "got": role,
                    "valid": sorted(handler.app.state._VALID_VIDEO_ROLES),
                    "hint": (
                        "scope_video_role must exist in current event state.videos "
                        "for event stitch jobs."
                    ),
                    "partition_code": STITCH_SCOPE_PARTITION_V1,
                },
            )
            return None

    if name and ctx.is_milestone and _is_milestone_stitch_job_name(name):
        expected = _stitch_milestone_job_name(str(ctx.milestone_id))
        if name != expected:
            handler._send_error_v59(
                409,
                error_code="STITCH_JOB_NAME_MISMATCH",
                error_message=f"milestone stitch job {name!r} != {expected!r}",
                retry_safe=False,
                extra={"partition_code": STITCH_SCOPE_PARTITION_V1},
            )
            return None

    store = stitch_state_for_scope(handler.app, ctx)
    handler._stitch_partition_ctx = ctx
    return StitchScopeBinding(ctx=ctx, stitch_store=store, job_name=resolved_job)
