"""Persist active milestone scope across server restart (MILESTONE_SCOPE_PERSIST_V1)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from lib.paths import runtime_production_root

SCHEMA_VERSION = 1
FILENAME = "server_milestone_scope.json"


def milestone_scope_path(prod_root: Path | str) -> Path:
    return Path(prod_root) / FILENAME


def read_persisted_milestone_scope(prod_root: Path | str, *, event_id: str) -> dict | None:
    path = milestone_scope_path(prod_root)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    if str(data.get("event_id") or "").strip() != str(event_id).strip():
        return None
    if str(data.get("scope_type") or "") != "milestone":
        return None
    mid = str(data.get("active_milestone_id") or "").strip()
    if not mid:
        return None
    return data


def write_persisted_milestone_scope(
    prod_root: Path | str,
    *,
    event_id: str,
    milestone_id: str,
    source: str = "milestone_load",
) -> None:
    root = Path(prod_root)
    root.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "event_id": str(event_id).strip(),
        "scope_type": "milestone",
        "active_milestone_id": str(milestone_id).strip(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
    }
    path = milestone_scope_path(root)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def clear_persisted_milestone_scope(prod_root: Path | str) -> None:
    path = milestone_scope_path(prod_root)
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def restore_milestone_scope_on_startup(app) -> bool:
    """Re-activate milestone scope from disk after launchd respawn."""
    try:
        prod_root = runtime_production_root(app.event_dir)
        pin = read_persisted_milestone_scope(prod_root, event_id=app.event_id)
        if not pin:
            return False
        mid = str(pin.get("active_milestone_id") or "").strip()
        if not mid:
            return False
        from server_handlers.event_video import apply_milestone_scope_to_app

        apply_milestone_scope_to_app(app, mid, source="startup_restore")
        print(
            f"[startup] restored milestone scope {mid!r} for {app.event_id}",
            flush=True,
        )
        return True
    except Exception as exc:
        print(f"[startup] milestone scope restore skipped: {exc}", flush=True)
        return False
