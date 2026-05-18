"""scope_router — single mandatory partition router for v59 authoring-workflow.

Per STORYBOARD_V59_AUTHORING_WORKFLOW_SPEC_v2.md §4 (architecture SR+G v1):
all beat-touching mutation handlers MUST consume scope keys via this module
and route partition writes through `mutate_partition`. This module is the
counterpart to LD-461 (scope-body helper, client-side scope injection):
LD-461 makes the client INJECT the keys; this module makes the server USE
them as the single source of truth for which `videos.<role>` partition gets
the write.

Subsumes the prevention claims for K1 (hardcoded `videos.intro` lift in
beat-update handlers), K2 (top-level legacy `state["beats"]` writes), K3
(hardcoded BG segment), and D5 (`patch_state` intro_partition hardcode).
The K6 mitigation (strict default `allow_missing=False`) ride-alongs at
the call sites, not here — this module returns 400/409 on missing or
mismatched scope regardless of caller defaults.

LDs governing this file (filed in C-8 per spec §9):
  - SCOPE_ROUTER_V1                         HARD  (this module is the gate)
  - SCOPE_REQUIRED_DEFAULTS_V1              HARD  (call sites flip defaults)
  - DISPLAY_ORDER_STRICT_V2                 HARD  (mutate_partition wraps the
                                                  symmetric prune; C-10 lands
                                                  the mutate_state belt-+-suspenders)
  - BG_HARDCODED_SCOPE_PURGE_V1             HARD  (C-4 ride-along)
  - SPEAKER_WRITE_BOUNDARY_CANONICALIZATION_V1 HARD (C-3+C-6 ride-along)
  - BEAT_GRAFT_RECOVERY_MECHANISM_V1        HARD  (C-7 cornerstone; the
                                                  `graft` function lands then)

AST-grep CI gate (sibling of LD-519 MUTATION_CHANNEL_INVARIANT_V1) bans:
  - `state.setdefault("videos", {}).setdefault("intro"` outside this module
    and `StateManager`
  - direct `state.setdefault("beats"` (top-level legacy) outside this module
    and `StateManager`
  - literal `arc_number=1, event_id=2, phase="pre"` in handlers (K3-specific)

The gate lives in `.github/workflows/playwright_e2e.yml` and trips CI red
on any future handler that bypasses the router.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional


# Authoritative set of v59 video roles. Mirrors `StateManager._VALID_VIDEO_ROLES`
# at `production_server.py:1155` — kept in sync by ratchet review of any change.
_VALID_VIDEO_ROLES: frozenset[str] = frozenset({"intro", "resolution", "standalone"})


@dataclass(frozen=True)
class ResolvedScope:
    """Frozen scope-key tuple proven against state at request time.

    `event_id` is the server-pinned event_dir name (e.g. `Event_1`,
    `Event_e2e_fixture`); `video_role` is one of `_VALID_VIDEO_ROLES`.
    `beat_id` and `mutation_id` are optional convenience carriers — handlers
    that require either MUST request them via `require_beat_id` or read
    `body['mutation_id']` themselves.
    """

    event_id: str
    video_role: str
    beat_id: Optional[str] = None
    mutation_id: Optional[str] = None


class ScopeError(Exception):
    """Raised by `resolve` when the body fails scope validation.

    Carries the HTTP status, structured error code, and a detail dict the
    handler should surface to the client verbatim. Code values are stable
    contract surface (clients gate retry/UX behavior on them):

      - `scope_required`           400  body lacks `event_id` / `scope_event_id`
      - `scope_mismatch`           409  body event_id != server-pinned event
      - `video_role_required`      400  body lacks `scope_target_video` / `scope_video_role`
      - `video_role_invalid`       400  role not in _VALID_VIDEO_ROLES
      - `beat_id_required`         400  caller asked for require_beat_id and body has none
    """

    def __init__(self, code: str, http_status: int, detail: Optional[dict] = None):
        self.code = code
        self.http_status = http_status
        self.detail = detail or {}
        super().__init__(f"{code} (HTTP {http_status}): {self.detail}")


def resolve(
    body: Optional[dict],
    server_event_dir_name: str,
    *,
    require_beat_id: bool = False,
) -> ResolvedScope:
    """Validate body's scope keys against the server pin.

    Coalesces the LD-461 client-side aliases:
      - `event_id`           ← `scope_event_id`
      - `video_role`         ← `scope_target_video` (preferred) | `scope_video_role`

    The legacy `event_id` / `scope_video_role` accept-paths are retained for
    backward compatibility per LD-461; new clients SHOULD send the
    `scope_event_id` / `scope_target_video` forms.

    Raises `ScopeError` with structured code + HTTP status.

    NOTE: the snippet below is DOCSTRING illustration only — not executable
    at module import time. It is meant to be copy-pasted INSIDE a
    `def _handle_X(self, body)` method on `ProductionHandler`, where
    `self._send_error_v59` and `self.app` are bound. Handlers should
    convert this error to a JSON response via the following pattern::

        # (inside a ProductionHandler method, NOT at module scope)
        try:
            scope = scope_router.resolve(body, self.app.event_dir.name)
        except scope_router.ScopeError as e:
            return self._send_error_v59(
                e.http_status,
                error_code=e.code.upper(),
                error_message=e.code,
                retry_safe=False,
                extra=e.detail or None,
            )
    """
    body = body or {}

    # event_id — `scope_event_id` (LD-461 canonical) wins; bare `event_id`
    # is the v58/early-v59 alias.
    event_id = body.get("scope_event_id") or body.get("event_id")
    if event_id is None:
        raise ScopeError(
            "scope_required",
            400,
            {"hint": "v59 clients must include scope_event_id (LD-461)."},
        )
    if event_id != server_event_dir_name:
        raise ScopeError(
            "scope_mismatch",
            409,
            {
                "expected_event_id": server_event_dir_name,
                "got": event_id,
                "hint": (
                    "Server is pinned to the named event for the lifetime of "
                    "this process; cross-event mutations require an explicit "
                    "--source-event flag at startup and the /api/beat/graft "
                    "endpoint (LD BEAT_GRAFT_RECOVERY_MECHANISM_V1, C-7)."
                ),
            },
        )

    # video_role — `scope_target_video` (LD-461 canonical) wins; the historic
    # `scope_video_role` alias is preserved for older callers.
    video_role = body.get("scope_target_video") or body.get("scope_video_role")
    if video_role is None:
        raise ScopeError(
            "video_role_required",
            400,
            {"hint": "v59 clients must include scope_target_video (LD-461)."},
        )
    if video_role not in _VALID_VIDEO_ROLES:
        raise ScopeError(
            "video_role_invalid",
            400,
            {"valid": sorted(_VALID_VIDEO_ROLES), "got": video_role},
        )

    # beat_id — optional unless caller asked.
    beat_id = body.get("beat_id")
    if require_beat_id and not beat_id:
        raise ScopeError(
            "beat_id_required",
            400,
            {"hint": "Handler requires beat_id; body lacks one."},
        )

    mutation_id = body.get("mutation_id")

    return ResolvedScope(
        event_id=event_id,
        video_role=video_role,
        beat_id=beat_id,
        mutation_id=mutation_id,
    )


def mutate_partition(
    state_manager,
    scope: ResolvedScope,
    mutator_fn: Callable[[dict], None],
) -> None:
    """Single allowed entry to partition writes.

    Wraps `StateManager.mutate_video_state(scope.video_role, mutator_fn)`.
    The DISPLAY_ORDER_STRICT prune lives inside `mutate_video_state` (see
    `production_server.py:1198-1217`); `mutator_fn` receives the partition
    dict (NOT the full state), so handler code cannot accidentally lift a
    different role's partition or write to the legacy top-level `state["beats"]`.

    Direct `state_manager.mutate_state` calls touching `state["videos"][...]
    ` are banned by the AST-grep CI gate. Handlers that need to mutate
    non-partition top-level fields (e.g. `version`, `event_id`, app-level
    metadata) call `mutate_state` directly with a mutator that does not
    touch `state["videos"]` — the C-10 defense-in-depth prune in
    `mutate_state` catches accidental partition touches.
    """
    state_manager.mutate_video_state(scope.video_role, mutator_fn)


# graft() lands in C-7 (per spec §6 + handoff §4 C-7). Until then this
# module exposes only resolve + mutate_partition; the cornerstone endpoint
# /api/beat/graft is explicitly not yet available.
