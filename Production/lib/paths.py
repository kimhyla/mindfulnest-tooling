"""
Canonical filesystem roots for MN runtime + tooling separation (LD-505 Phase B).

``MN_DROPBOX_ROOT`` is the synced project/media tree ("Claude Mindfulnest Project Files").
Production code shipped from this repo must not infer that tree via ``Path(__file__)``.
"""

from __future__ import annotations

import os
import platform
from pathlib import Path


_MAC_DROPBOX_DEFAULT = "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files"
_WIN_DROPBOX_DEFAULT = r"C:\Users\ECDS Clinical\Dropbox\Claude Mindfulnest Project Files"


def _candidate_dropbox_pair() -> tuple[Path, Path]:
    mac_p = Path(_MAC_DROPBOX_DEFAULT)
    win_p = Path(_WIN_DROPBOX_DEFAULT)
    return (win_p, mac_p) if platform.system() == "Windows" else (mac_p, win_p)


def _resolve_dropbox_root() -> Path:
    """Resolve Dropbox project root.

    Priority: ``MN_DROPBOX_ROOT`` → ``MINDFULNEST_PROJECT_ROOT`` (legacy parity) → platform
    default that exists → nominal Mac default string (training / missing mounts).
    """
    for env_key in ("MN_DROPBOX_ROOT", "MINDFULNEST_PROJECT_ROOT"):
        raw = os.environ.get(env_key)
        if raw:
            return Path(raw)
    primary, secondary = _candidate_dropbox_pair()
    if primary.exists():
        return primary
    if secondary.exists():
        return secondary
    return Path(_MAC_DROPBOX_DEFAULT)


DROPBOX_ROOT: Path = _resolve_dropbox_root()


def _resolve_tooling_root() -> Path:
    env = os.environ.get("MN_TOOLING_ROOT")
    if env:
        return Path(env)
    # Production/lib/paths.py → parents[2] == mindfulnest-tooling repository root.
    return Path(__file__).resolve().parent.parent.parent


TOOLING_ROOT: Path = _resolve_tooling_root()


def EVENT_DIR(event_id: str | int) -> Path:
    """``DROPBOX_ROOT / 'Production' / 'Event_<id>'`` — accepts ``1`` or ``Event_1``."""
    e = str(event_id).strip()
    folder = e if e.startswith("Event_") else f"Event_{e}"
    return DROPBOX_ROOT / "Production" / folder


API_KEYS_MASTER_PATH: Path = DROPBOX_ROOT / "Production" / "API_KEYS_MASTER.md"
