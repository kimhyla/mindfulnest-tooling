"""Persist last server-pinned event across restarts (EVENT_PIN_DURABILITY_V1)."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from lib.paths import EVENT_DIR, normalize_event_dir, runtime_production_root

PIN_FILENAME = "server_event_pin.json"
SCHEMA_VERSION = 1


def server_event_pin_path(prod_root: Path | str) -> Path:
    return Path(prod_root) / PIN_FILENAME


def read_persisted_event_pin(prod_root: Path | str) -> dict | None:
    path = server_event_pin_path(prod_root)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    event_id = str(data.get("event_id") or "").strip()
    if not event_id:
        return None
    return data


def write_persisted_event_pin(
    prod_root: Path | str,
    *,
    event_id: str,
    storyboard: str,
    event_dir: Path | str | None = None,
    source: str = "event_load",
) -> None:
    """Write atomic pin file under Production/ — survives server restart."""
    root = Path(prod_root)
    root.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "event_id": str(event_id).strip(),
        "storyboard": str(storyboard).strip(),
        "event_dir": str(event_dir or EVENT_DIR(event_id)),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
    }
    path = server_event_pin_path(root)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _discover_storyboard(event_dir: Path) -> str | None:
    requested = event_dir / "storyboard_v59_prod.html"
    if requested.is_file():
        return requested.name
    candidates = sorted(
        event_dir.glob("storyboard_v*_prod.html"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0].name if candidates else None


def resolve_startup_event(
    event_dir: Path | str,
    storyboard_name: str,
    event_id: str,
) -> tuple[Path, str, str, str]:
    """Return (event_dir, storyboard_name, event_id, pin_source).

    pin_source is one of: cli, persisted, cli_fallback_invalid_pin
    """
    cli_dir = normalize_event_dir(event_dir)
    cli_id = str(event_id).strip()
    cli_sb = str(storyboard_name).strip()
    prod_root = runtime_production_root(cli_dir)

    if os.environ.get("MN_EVENT_PIN_IGNORE", "").strip() in ("1", "true", "yes"):
        return cli_dir, cli_sb, cli_id, "cli"

    pin = read_persisted_event_pin(prod_root)
    if not pin:
        return cli_dir, cli_sb, cli_id, "cli"

    pinned_id = str(pin.get("event_id") or "").strip()
    if not pinned_id or pinned_id == cli_id:
        return cli_dir, cli_sb, cli_id, "cli"

    pinned_dir = normalize_event_dir(EVENT_DIR(pinned_id))
    if not pinned_dir.is_dir():
        return cli_dir, cli_sb, cli_id, "cli_fallback_invalid_pin"

    pinned_sb = str(pin.get("storyboard") or "").strip()
    if not pinned_sb or not (pinned_dir / pinned_sb).is_file():
        discovered = _discover_storyboard(pinned_dir)
        if not discovered:
            return cli_dir, cli_sb, cli_id, "cli_fallback_invalid_pin"
        pinned_sb = discovered

    return pinned_dir, pinned_sb, pinned_id, "persisted"
