"""Production scope resolution — event XOR milestone (MILESTONE_BG_SCOPE_ROUTER_V1).

Single front door for handlers that need to know which on-disk root owns beats,
sidecar, stitch jobs, and library paths.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal


ScopeType = Literal["event", "milestone"]

MILESTONE_VIDEO_ROLE = "standalone"
_EVENT_PARTITION_ROLES = frozenset({"intro", "resolution", "phase_a", "phase_b"})


def normalize_milestone_video_role(role: str | None) -> str:
    """Milestones are single-slot; event partition roles map to standalone."""
    cleaned = str(role or "").strip()
    if not cleaned or cleaned in _EVENT_PARTITION_ROLES:
        return MILESTONE_VIDEO_ROLE
    return cleaned


@dataclass(frozen=True)
class ScopeContext:
    scope_type: ScopeType
    root_dir: Path
    scope_id: str
    video_role: str
    generation: int
    library_event_dir: Path
    prod_root: Path
    # Milestone-only
    milestone_id: str | None = None
    skeleton_ref: dict[str, Any] | None = None

    @property
    def is_milestone(self) -> bool:
        return self.scope_type == "milestone"

    @property
    def stitch_job_name(self) -> str:
        if self.is_milestone:
            return f"milestone_{self.milestone_id}_stitch"
        return f"{self.scope_id}_stitch"


def milestones_root(prod_root: Path) -> Path:
    return prod_root / "Milestones"


def resolve_scope_from_app(
    app: Any,
    body_or_qs: dict | None = None,
    *,
    default_video_role: str | None = None,
) -> ScopeContext | tuple[int, dict]:
    """Build ScopeContext from server app + optional request body/query dict.

    Returns ScopeContext on success, or (http_status, error_body) on failure.
    """
    from lib.milestone_store import load_milestone_state, resolve_milestone_skeleton_ref

    body = body_or_qs or {}
    prod_root = Path(app.event_dir).parent
    generation = int(getattr(app, "event_generation", 1))

    scope_milestone_id = (
        body.get("scope_milestone_id")
        or body.get("milestone_id")
    )
    # Legacy v59 clients always send event_id on mutations; when milestone scope
    # is explicit, event_id is metadata — not a second scope anchor.
    scope_event_id = body.get("scope_event_id")
    if not scope_milestone_id:
        scope_event_id = scope_event_id or body.get("event_id")

    app_scope = getattr(app, "scope_type", "event")
    app_milestone = getattr(app, "active_milestone_id", None)

    if scope_milestone_id and scope_event_id:
        # Storyboard scope event_id is directory name; BG may pass segment number —
        # only treat as ambiguous when scope_event_id looks like Event_*.
        ev = str(scope_event_id)
        if ev.startswith("Event_") or ev == app.event_dir.name:
            return 400, {
                "ok": False,
                "error": "exactly ONE of scope_event_id or scope_milestone_id required (got both)",
                "code": "SCOPE_AMBIGUOUS",
            }

    if scope_milestone_id or (app_scope == "milestone" and app_milestone):
        mid = str(scope_milestone_id or app_milestone)
        mdir = milestones_root(prod_root) / mid
        if not mdir.is_dir():
            return 404, {
                "ok": False,
                "error": f"milestone {mid!r} not found at {mdir}",
                "code": "MILESTONE_NOT_FOUND",
            }
        state = load_milestone_state(mdir)
        skel = resolve_milestone_skeleton_ref(state, mid)
        lib_ev_name = str(state.get("library_event_id") or f"Event_{skel.get('arc_number', 1)}")
        lib_dir = prod_root / lib_ev_name
        if not lib_dir.is_dir():
            lib_dir = Path(app.event_dir)
        role = normalize_milestone_video_role(
            body.get("scope_target_video")
            or body.get("scope_video_role")
            or state.get("active_video")
            or default_video_role
            or MILESTONE_VIDEO_ROLE
        )
        return ScopeContext(
            scope_type="milestone",
            root_dir=mdir,
            scope_id=mid,
            milestone_id=mid,
            video_role=str(role),
            generation=generation,
            library_event_dir=lib_dir,
            prod_root=prod_root,
            skeleton_ref=skel,
        )

    # Event scope
    pinned = app.event_dir.name
    ev = str(scope_event_id or pinned)
    if ev != pinned and not str(scope_event_id or "").isdigit():
        # Allow BG segment numbers without Event_ prefix — not a scope switch.
        if str(scope_event_id or "").startswith("Event_") and ev != pinned:
            return 409, {
                "ok": False,
                "error_code": "SCOPE_MISMATCH",
                "error_message": "scope_mismatch",
                "code": "SCOPE_VALIDATION_V1",
                "expected_event_id": pinned,
                "got_event_id": ev,
            }
    role = (
        body.get("scope_target_video")
        or body.get("scope_video_role")
        or default_video_role
        or "intro"
    )
    return ScopeContext(
        scope_type="event",
        root_dir=Path(app.event_dir),
        scope_id=pinned,
        video_role=str(role),
        generation=generation,
        library_event_dir=Path(app.event_dir),
        prod_root=prod_root,
        milestone_id=None,
        skeleton_ref=None,
    )


def scope_body_with_milestone(body: dict | None, app: Any) -> dict:
    """Extend _scope_body normalization with milestone + video role keys."""
    b = dict(body or {})
    out = {
        "event_id": b.get("scope_event_id") or b.get("event_id"),
        "scope_video_role": b.get("scope_video_role") or b.get("scope_target_video"),
        "scope_milestone_id": b.get("scope_milestone_id") or b.get("milestone_id"),
        "scope_target_video": b.get("scope_target_video") or b.get("scope_video_role"),
    }
    if getattr(app, "scope_type", "event") == "milestone" and not out["scope_milestone_id"]:
        out["scope_milestone_id"] = getattr(app, "active_milestone_id", None)
    return out
