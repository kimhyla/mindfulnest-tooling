"""
Canonical filesystem roots for MN runtime + tooling separation (LD-505 Phase B + C).

``MN_DROPBOX_ROOT`` is the synced project/media tree ("Claude Mindfulnest Project Files").
Production code shipped from this repo must not infer that tree via ``Path(__file__)``.

Phase C (2026-05-19): adds `runtime_production_root(event_dir)`, `BgPaths`, and
`bg_paths(event_dir)` so handler modules can derive every data path from the
running server's `event_dir` instead of `__file__`. Closes audit findings
C1-1..C1-13 (see /tmp/v59_full_qa_audit_20260519.md).
"""

from __future__ import annotations

import os
import platform
from dataclasses import dataclass
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


# ---------------------------------------------------------------------------
# Phase C (2026-05-19) — runtime-data-root helpers + BgPaths
# ---------------------------------------------------------------------------

def runtime_production_root(event_dir: Path | str) -> Path:
    """Derive the runtime ``Production/`` directory from a server's event_dir.

    The server is launched with ``--event-dir <path>/Production/Event_<N>``;
    the parent of that path IS the runtime ``Production/`` root regardless of
    whether the server happens to be running from the tooling tree or directly
    from the Dropbox tree. Use this for ALL data-path computations — never
    derive runtime data paths from ``__file__`` (see audit C1).
    """
    return Path(event_dir).parent


@dataclass(frozen=True)
class BgPaths:
    """All beat_generator data locations, anchored on the runtime ``Production/`` root.

    Instantiated at server startup via :func:`bg_paths(event_dir)`. Every
    constant here was previously derived from ``Path(__file__)`` in
    beat_generator.py and broke under LD-505 dual-canonical-roots (audit C1-5,
    C1-6, C1-7, C1-8, C1-9).
    """
    prod_root: Path           # runtime Production/
    stills_dir: Path          # Production/beat_generator_stills/
    sidecar_path: Path        # Production/beat_generator_state.json
    char_assets: Path         # Production/Character_Assets/
    skeleton_base: Path       # <project_root>/Arc Skeletons/
    canon_base: Path          # <project_root>/Canon/
    local_stills_dir: Path    # Production/beat_generator_stills/local_renders/
    project_root: Path        # parent of Production/ (Dropbox project root)


def bg_paths(event_dir: Path | str) -> BgPaths:
    """Build the BgPaths bundle for a given event_dir."""
    prod = runtime_production_root(event_dir)
    project = prod.parent
    return BgPaths(
        prod_root=prod,
        stills_dir=prod / "beat_generator_stills",
        sidecar_path=prod / "beat_generator_state.json",
        char_assets=prod / "Character_Assets",
        skeleton_base=project / "Arc Skeletons",
        canon_base=project / "Canon",
        local_stills_dir=prod / "beat_generator_stills" / "local_renders",
        project_root=project,
    )


def character_pose_paths(event_dir: Path | str) -> dict[str, str]:
    """Per-event character master/pose paths, anchored on the runtime root.

    Returns a mapping `{character_name: absolute_path_str}` for the default
    master still used by FLUX still generation. Replaces beat_generator.py's
    module-level `_CHARACTER_POSE_MAP` literal which was anchored on
    `_PROD_CHARS` derived from `__file__`.

    NOTE: Keys mirror beat_generator.py:127-134 exactly. Do not rename.
    [INFERRED — verify line numbers may drift as beat_generator.py evolves;
    keep symbol-grep `_PROD_CHARS` in beat_generator.py as the durable check.]
    """
    bp = bg_paths(event_dir)
    return {
        "Tessa":   str(bp.prod_root / "Tessa"   / "poses" / "tessa_neutral.png"),
        "Chipper": str(bp.char_assets / "generated_masters" / "master_chipper_live-batch-2-761a7da1.png"),
        "Arlo":    str(bp.prod_root / "Arlo"    / "poses" / "arlo_canonical_neutral_vest.png"),
        "Luna":    str(bp.prod_root / "Luna"    / "Luna v2 Master 4.png"),
        "Benson":  str(bp.prod_root / "Benson"  / "poses" / "benson_kontext_swap_v1.png"),
        "Ember":   str(bp.prod_root / "Ember"   / "poses" / "ember_HERO.png"),
        "Bork":    str(bp.prod_root / "Bork"    / "poses" / "bork_pose_neutral.png"),
        "Bramble": str(bp.prod_root / "Bramble" / "poses" / "bramble_HERO.png"),
        "Cedric":  str(bp.char_assets / "MYRRHIN_MASTER_STILL_v1.png"),
    }
