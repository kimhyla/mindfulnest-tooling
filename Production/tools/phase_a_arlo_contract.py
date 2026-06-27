"""Phase A Arlo base-clip contract — canonical preset for all events.

Jun 22 2026: ``arlo_idle_wizard_desk_v4`` from NEW STYLE ARLO wizard-desk still +
locked-camera Kling idle (fireplace fire/smoke + gentle squirrel motion).
Prior v1–v3 coerced on read/submit.

Never use NEW STYLE CHARACTERS/BACKGROUND stills for Arlo idle — wrong asset class.
"""
from __future__ import annotations

from pathlib import Path

PHASE_A_ARLO_BASE_CLIP_CANONICAL = "arlo_idle_wizard_desk_v4"

# Close medium wizard-desk still (Jun 22) — Arlo large in frame.
PHASE_A_ARLO_CANONICAL_STILL_REL = (
    "NEW STYLE CHARACTERS/ARLO/ChatGPT Image Jun 22, 2026, 01_12_53 AM.png"
)
PHASE_A_ARLO_EVENT_STILL_NAME = "phase_a_arlo_canonical_still.png"

_DEPRECATED_EXACT = frozenset({
    "arlo_idle_wizard_desk_v1",
    "arlo_idle_wizard_desk_v2",
    "arlo_idle_wizard_desk_v3",
    "chipper_idle_closeup_v1",
    "chipper_idle_closeup_v2",
})

_DEPRECATED_PREFIXES = (
    "chipper_idle_",
    "placeholder_arlo_",
)


def phase_a_arlo_base_clip_deprecated(clip_id: str | None) -> bool:
    if not clip_id or not str(clip_id).strip():
        return True
    cid = str(clip_id).strip()
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
    """Reject fantasy BACKGROUND library stills mistaken for Arlo wizard desk."""
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
        f"No Arlo wizard-desk still under {event_dir} or {prod_root}/Arlo/poses"
    )


def install_phase_a_arlo_canonical_still(event_dir: Path, prod_root: Path) -> Path:
    """Copy global canonical still into event folder for operator visibility."""
    src = prod_root / PHASE_A_ARLO_CANONICAL_STILL_REL
    src = validate_phase_a_arlo_idle_still_path(src)
    dst = event_dir / PHASE_A_ARLO_EVENT_STILL_NAME
    dst.write_bytes(src.read_bytes())
    return dst
