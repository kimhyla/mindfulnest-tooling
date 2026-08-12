"""Phase A Arlo base-clip contract — canonical preset for all events.

Send for Lipsync is PHASE_A_ARLO_LAYERED_ROUTE_V2 only: Kim Gate0 pinned
headshot idle + headshot plate chroma composite (1280×720 delivery).

Base-clip ID is compatibility metadata only — it does not select the layered
render asset. Speak always uses ``arlo_gesture_idle_kim_gate0_pinned_15s_v1.mp4``.

Canonical metadata ID: ``arlo_idle_kim_gate0_headshot_v1``.
Prior wizard-desk / chipper IDs coerce to that on read/submit.
"""
from __future__ import annotations

from pathlib import Path

PHASE_A_ARLO_BASE_CLIP_CANONICAL = "arlo_idle_kim_gate0_headshot_v1"

# Optional still path for offline Gate0 / archive helpers (not Send).
PHASE_A_ARLO_CANONICAL_STILL_REL = (
    "NEW STYLE CHARACTERS/ARLO/"
    "arlo_still_green_headshot_openmouth_trimmed_1920x1080_v1.png"
)
PHASE_A_ARLO_EVENT_STILL_NAME = "phase_a_arlo_canonical_still.png"

_DEPRECATED_EXACT = frozenset({
    "arlo_idle_wizard_desk_v1",
    "arlo_idle_wizard_desk_v2",
    "arlo_idle_wizard_desk_v3",
    "arlo_idle_wizard_desk_v4",
    "arlo_idle_wizard_desk_v5",
    "arlo_idle_wizard_desk_v6",
    "arlo_idle_wizard_desk_v7",
    "arlo_idle_wizard_desk_v8",
    "chipper_idle_closeup_v1",
    "chipper_idle_closeup_v2",
})

_DEPRECATED_PREFIXES = (
    "chipper_idle_",
    "placeholder_arlo_",
    "arlo_idle_wizard_desk_",
)


def phase_a_arlo_base_clip_deprecated(clip_id: str | None) -> bool:
    if not clip_id or not str(clip_id).strip():
        return True
    cid = str(clip_id).strip()
    if cid == PHASE_A_ARLO_BASE_CLIP_CANONICAL:
        return False
    if cid in _DEPRECATED_EXACT:
        return True
    return any(cid.startswith(p) for p in _DEPRECATED_PREFIXES)


def coerce_phase_a_arlo_base_clip_id(clip_id: str | None) -> str:
    if phase_a_arlo_base_clip_deprecated(clip_id):
        return PHASE_A_ARLO_BASE_CLIP_CANONICAL
    return str(clip_id).strip()


def _path_has_background_folder(path: Path) -> bool:
    return any(part.upper() == "BACKGROUND" for part in path.parts)


def validate_phase_a_arlo_idle_still_path(path: Path) -> Path:
    """Reject fantasy BACKGROUND library stills mistaken for Arlo assets."""
    p = path.expanduser().resolve()
    if not p.is_file():
        raise FileNotFoundError(f"Arlo idle still missing: {p}")
    if _path_has_background_folder(p) and "arlo" not in p.name.lower():
        raise ValueError(
            f"Refusing Arlo idle still from BACKGROUND folder (wrong asset): {p}"
        )
    return p


def phase_a_arlo_idle_still_candidates(event_dir: Path, prod_root: Path) -> list[Path]:
    return [
        prod_root / PHASE_A_ARLO_CANONICAL_STILL_REL,
        event_dir / PHASE_A_ARLO_EVENT_STILL_NAME,
        event_dir / "phase_a_arlo_wizard_desk_v1.png",
        prod_root / "Arlo" / "poses" / "arlo_wizard_room_neutral_vest.png",
        prod_root / "Arlo" / "poses" / "arlo_wizard_room_desk_v1.png",
        prod_root / "Arlo" / "poses" / "arlo_canonical_neutral_vest.png",
    ]


def resolve_phase_a_arlo_idle_still(
    event_dir: Path,
    prod_root: Path,
    explicit: Path | str | None = None,
) -> Path:
    if explicit is not None:
        return validate_phase_a_arlo_idle_still_path(Path(explicit))
    for candidate in phase_a_arlo_idle_still_candidates(event_dir, prod_root):
        if candidate.is_file():
            return validate_phase_a_arlo_idle_still_path(candidate)
    raise FileNotFoundError(
        f"No Arlo still under {event_dir} or {prod_root} "
        f"(expected {PHASE_A_ARLO_CANONICAL_STILL_REL})"
    )


def install_phase_a_arlo_canonical_still(event_dir: Path, prod_root: Path) -> Path:
    """Copy global canonical still into event folder for operator visibility."""
    src = prod_root / PHASE_A_ARLO_CANONICAL_STILL_REL
    src = validate_phase_a_arlo_idle_still_path(src)
    dst = event_dir / PHASE_A_ARLO_EVENT_STILL_NAME
    dst.write_bytes(src.read_bytes())
    return dst
