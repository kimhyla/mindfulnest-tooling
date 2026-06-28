"""Beat Gen Truth Stack — scope object, resolvers, single-writer gates, observability."""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterator, Literal

logger = logging.getLogger("beatgen.scope")

_EVENT_NUM_RE = re.compile(r"event(\d+)([a-z]+)?_", re.I)
_MILESTONE_SEG_RE = re.compile(r"event(\d+[a-z]+)", re.I)


class BeatGenScopeError(Exception):
    """Fail-closed scope validation — maps to HTTP 409 in handlers."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "BEATGEN_SCOPE_MISMATCH",
        **extra: Any,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.extra = extra


class BeatGenSingleWriterError(BeatGenScopeError):
    """External process attempted a direct sidecar write — use HTTP on dedicated port."""

    def __init__(self, message: str, **extra: Any) -> None:
        super().__init__(message, error_code="BEATGEN_SINGLE_WRITER", **extra)


@dataclass(frozen=True)
class BeatGenScope:
    kind: Literal["event_production", "milestone_arc"]
    event_id: str | None
    event_dir: Path | None
    milestone_id: str | None
    db_path: Path | None
    sidecar_authority: Path


def event_id_from_beat_id(beat_id: str) -> str | None:
    """``bg_arc1_event3_pre_beat_10`` → ``Event_3`` (production beats only)."""
    m = _EVENT_NUM_RE.search(str(beat_id or ""))
    if not m:
        return None
    if m.group(2):
        return None
    return f"Event_{int(m.group(1))}"


def milestone_segment_key_from_beat_id(beat_id: str) -> str | None:
    """``bg_arc1_event3b_full_beat_12`` → ``event3b_full``."""
    m = _MILESTONE_SEG_RE.search(str(beat_id or ""))
    if not m:
        return None
    return m.group(0).lower()


def port_from_event_id(event_id: str) -> int:
    """Dedicated port rule: Event_N → 5110 + N."""
    raw = str(event_id or "").strip()
    if raw.lower().startswith("event_"):
        raw = raw.split("_", 1)[1]
    if not raw.isdigit():
        raise BeatGenScopeError(f"invalid event_id for port: {event_id!r}")
    return 5110 + int(raw)


def beatgen_db_path_for_event(event_id: str) -> Path:
    slug = "".join(str(event_id or "").split("_")).lower()
    return Path.home() / ".mindfulnest" / "state" / f"beatgen_{slug}.db"


def storyboard_url_for_beat(beat_id: str) -> str:
    event_id = event_id_from_beat_id(beat_id)
    if not event_id:
        raise BeatGenScopeError(f"cannot resolve storyboard URL for beat_id={beat_id!r}")
    port = port_from_event_id(event_id)
    return f"http://localhost:{port}/?event={event_id}"


def legacy_global_db_path() -> Path:
    return Path.home() / ".mindfulnest" / "state" / "beatgen.db"


def assert_beat_id_matches_scope(beat_id: str, scope: BeatGenScope) -> None:
    bid = str(beat_id or "").strip()
    if scope.kind == "event_production":
        expected = event_id_from_beat_id(bid)
        if not expected:
            raise BeatGenScopeError(
                f"beat_id {bid!r} is not an event production id",
                beat_id=bid,
                scope_kind=scope.kind,
            )
        if scope.event_id and expected != scope.event_id:
            raise BeatGenScopeError(
                f"beat_id {bid!r} belongs to {expected}, scope is {scope.event_id}",
                beat_id=bid,
                scope_event_id=scope.event_id,
                beat_event_id=expected,
            )
        return
    seg = milestone_segment_key_from_beat_id(bid)
    if not seg:
        raise BeatGenScopeError(
            f"beat_id {bid!r} is not a milestone arc id",
            beat_id=bid,
            scope_kind=scope.kind,
        )


def assert_clip_path_matches_scope(video_path: str | Path, scope: BeatGenScope) -> None:
    if scope.kind != "event_production" or not scope.event_dir:
        return
    resolved = Path(video_path).expanduser().resolve()
    event_root = Path(scope.event_dir).expanduser().resolve()
    clips = event_root / "kling_o3_clips"
    try:
        resolved.relative_to(clips)
    except ValueError as exc:
        raise BeatGenScopeError(
            f"clip path {resolved} is not under {clips}",
            video_path=str(resolved),
            scope_event_dir=str(event_root),
        ) from exc


def assert_db_path_matches_beat(beat_id: str) -> None:
    """Refuse production beat writes when SQLite file ≠ beatgen_eventN.db."""
    if os.environ.get("MN_BEATGEN_TEST_ALLOW_DIRECT_WRITE") == "1":
        return
    event_id = event_id_from_beat_id(beat_id)
    if not event_id:
        return
    scoped = os.environ.get("MN_BEATGEN_DB_PATH", "").strip()
    expected = beatgen_db_path_for_event(event_id)
    actual = Path(scoped).expanduser().resolve() if scoped else legacy_global_db_path().resolve()
    if actual.name != expected.name:
        raise BeatGenScopeError(
            f"MN_BEATGEN_DB_PATH={actual} does not match {event_id} (expected basename {expected.name})",
            beat_id=beat_id,
            bound_db=str(actual),
            expected_db=str(expected),
            scope_event_id=event_id,
        )


def assert_direct_write_allowed(*, beat_id: str | None = None, caller: str = "unknown") -> None:
    """Single-writer gate — only production_server may mutate shipping beats directly."""
    if os.environ.get("MN_BEATGEN_TEST_ALLOW_DIRECT_WRITE") == "1":
        return
    if os.environ.get("MN_BEATGEN_SERVER_WRITER") == "1":
        return
    if os.environ.get("MN_BEATGEN_ALLOW_DIRECT_WRITE") == "1":
        return
    if beat_id and event_id_from_beat_id(beat_id):
        raise BeatGenSingleWriterError(
            "Direct Beat Gen writes for production beats are forbidden outside "
            "production_server. POST to /api/bg/import-delivery-clip on the "
            f"dedicated port ({storyboard_url_for_beat(beat_id)}).",
            beat_id=beat_id,
            caller=caller,
        )


def log_beatgen_mutation(
    *,
    operation: str,
    beat_id: str,
    scope: BeatGenScope | None,
    caller: str,
    extra: dict[str, Any] | None = None,
) -> None:
    payload = {
        "operation": operation,
        "beat_id": beat_id,
        "caller": caller,
        "scope": asdict(scope) if scope else None,
        **(extra or {}),
    }
    if scope:
        payload["scope_event_id"] = scope.event_id
        payload["db_path"] = str(scope.db_path) if scope.db_path else None
    logger.info("[beatgen_mutation] %s", json.dumps(payload, default=str))


def scope_from_current_globals(bg_module) -> BeatGenScope:
    """Build scope from beat_generator module globals (server after init_bg_paths)."""
    event_dir_raw = getattr(bg_module, "_BG_EVENT_DIR", None)
    milestone_only = getattr(bg_module, "_MILESTONE_SIDECAR_JSON_ONLY", False)
    milestone_bind = getattr(bg_module, "_MILESTONE_SCOPE_BIND", None)
    sidecar_path = Path(getattr(bg_module, "BG_SIDECAR_PATH", "") or "")
    db_raw = os.environ.get("MN_BEATGEN_DB_PATH", "").strip()
    db_path = Path(db_raw).expanduser().resolve() if db_raw else None

    if milestone_only and milestone_bind:
        mdir, _lib = milestone_bind
        milestone_id = Path(mdir).name
        return BeatGenScope(
            kind="milestone_arc",
            event_id=None,
            event_dir=Path(event_dir_raw) if event_dir_raw else None,
            milestone_id=milestone_id,
            db_path=None,
            sidecar_authority=sidecar_path,
        )

    event_dir = Path(event_dir_raw).expanduser().resolve() if event_dir_raw else None
    event_id = event_dir.name if event_dir else None
    if event_id and not event_id.startswith("Event_"):
        event_id = f"Event_{event_id}"
    return BeatGenScope(
        kind="event_production",
        event_id=event_id,
        event_dir=event_dir,
        milestone_id=None,
        db_path=db_path,
        sidecar_authority=sidecar_path,
    )


def scope_from_app(app) -> BeatGenScope:
    """Truth Stack Layer 1 — typed scope from server-pinned app (not ambient globals)."""
    scope_type = getattr(app, "scope_type", "event") or "event"
    event_dir = getattr(app, "event_dir", None)
    if scope_type == "milestone":
        milestone_id = getattr(app, "active_milestone_id", None)
        mdir = getattr(app, "milestone_dir", None)
        sidecar = Path(mdir) / "beat_generator_sidecar.json" if mdir else Path("beat_generator_sidecar.json")
        return BeatGenScope(
            kind="milestone_arc",
            event_id=None,
            event_dir=Path(event_dir).expanduser().resolve() if event_dir else None,
            milestone_id=str(milestone_id) if milestone_id else None,
            db_path=None,
            sidecar_authority=sidecar.expanduser().resolve(),
        )
    if not event_dir:
        raise BeatGenScopeError("app.event_dir missing for event_production scope")
    return build_event_production_scope(event_dir)


def scope_to_env_json(scope: BeatGenScope) -> str:
    """Serialize BeatGenScope for O3 subprocess env (MN_BEATGEN_SCOPE_JSON)."""
    payload = {
        "kind": scope.kind,
        "event_id": scope.event_id,
        "event_dir": str(scope.event_dir) if scope.event_dir else None,
        "milestone_id": scope.milestone_id,
        "db_path": str(scope.db_path) if scope.db_path else None,
        "sidecar_authority": str(scope.sidecar_authority),
    }
    return json.dumps(payload)


def scope_from_env_json(raw: str | None) -> BeatGenScope | None:
    """Deserialize scope from MN_BEATGEN_SCOPE_JSON."""
    text = (raw or "").strip()
    if not text:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    kind = data.get("kind")
    if kind not in ("event_production", "milestone_arc"):
        return None
    return BeatGenScope(
        kind=kind,
        event_id=data.get("event_id"),
        event_dir=Path(data["event_dir"]).expanduser().resolve() if data.get("event_dir") else None,
        milestone_id=data.get("milestone_id"),
        db_path=Path(data["db_path"]).expanduser().resolve() if data.get("db_path") else None,
        sidecar_authority=Path(data["sidecar_authority"]).expanduser().resolve(),
    )


def build_event_production_scope(event_dir: Path | str, *, event_id: str | None = None) -> BeatGenScope:
    root = Path(event_dir).expanduser().resolve()
    eid = event_id or root.name
    if not str(eid).startswith("Event_"):
        eid = f"Event_{eid}"
    db_path = beatgen_db_path_for_event(str(eid))
    sidecar = root / "beat_generator_sidecar.json"
    return BeatGenScope(
        kind="event_production",
        event_id=str(eid),
        event_dir=root,
        milestone_id=None,
        db_path=db_path,
        sidecar_authority=sidecar,
    )


@contextmanager
def beatgen_scope_ctx(scope: BeatGenScope, bg_module) -> Iterator[BeatGenScope]:
    """Bind beat_generator globals to ``scope`` for the duration of a write."""
    prev_db = os.environ.get("MN_BEATGEN_DB_PATH")
    if scope.kind == "event_production" and scope.db_path:
        os.environ["MN_BEATGEN_DB_PATH"] = str(scope.db_path)
    try:
        if scope.kind == "milestone_arc" and scope.milestone_id and scope.event_dir:
            bg_module.init_bg_paths(
                str(scope.event_dir),
                milestone_dir=str(scope.sidecar_authority.parent),
                library_event_dir=str(scope.event_dir),
            )
        elif scope.event_dir:
            bg_module.init_bg_paths(str(scope.event_dir), clear_milestone_scope=True)
        yield scope
    finally:
        if prev_db is None:
            os.environ.pop("MN_BEATGEN_DB_PATH", None)
        else:
            os.environ["MN_BEATGEN_DB_PATH"] = prev_db


# Truth Stack Layer 1 alias (spec naming)
beatgen_scope = beatgen_scope_ctx


def run_in_beatgen_scope(app, bg_module, fn, /, *args, **kwargs):
    """Enter typed BeatGenScope for async workers and subprocess callbacks."""
    scope = scope_from_app(app)
    with beatgen_scope_ctx(scope, bg_module):
        return fn(*args, **kwargs)


def http_import_delivery_clip(
    *,
    beat_id: str,
    delivery_mp4: Path | str,
    slot_index: int = 0,
    label: str = "imported delivery clip",
    source: str | None = None,
    make_active: bool = True,
    generation: int | None = None,
    timeout_s: float = 120.0,
) -> dict[str, Any]:
    """Agent/CLI single-writer path — POST to dedicated event server."""
    event_id = event_id_from_beat_id(beat_id)
    if not event_id:
        raise BeatGenScopeError(f"beat_id {beat_id!r} is not a production event beat")
    port = port_from_event_id(event_id)
    url = f"http://localhost:{port}/api/bg/import-delivery-clip"
    body: dict[str, Any] = {
        "beat_id": beat_id,
        "delivery_mp4_path": str(Path(delivery_mp4).expanduser().resolve()),
        "slot_index": slot_index,
        "label": label,
        "make_active": make_active,
        "scope_event_id": event_id,
    }
    if source:
        body["source"] = source
    if generation is not None:
        body["generation"] = generation
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise BeatGenScopeError(
            f"import-delivery-clip HTTP {exc.code}: {detail}",
            http_status=exc.code,
            url=url,
        ) from exc
