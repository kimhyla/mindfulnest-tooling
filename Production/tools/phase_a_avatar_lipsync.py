"""Phase A module lipsync — Kling V2 Avatar Pro (Arlo wizard-desk still + voice stem).

Category replacement for ByteDance-on-base-clip (2026-06-24). Validated probe:
Event_2 ``phase_a_avatar_pro_probe/`` job ``4c1d0315b39845a9b2b80b54314d59f2`` (~10s).
"""
from __future__ import annotations

from pathlib import Path

from phase_a_arlo_contract import resolve_phase_a_arlo_idle_still
from phase_b_avatar_lipsync import AVATAR_USD_PER_SEC, estimate_avatar_pro_usd

PHASE_A_LIPSYNC_METHOD_AVATAR = "kling_avatar_pro_v1"
PHASE_A_LIPSYNC_ROUTE_SINGLE_FULL_STEM = "single_full_stem_v1"
PHASE_A_AVATAR_ROUTE_CODE = "PHASE_A_SINGLE_SHOT_STATIC_BG_V1"

ARLO_WIZARD_DESK_PROMPT = (
    "Arlo the humanized cartoon squirrel stands at a wizard's wooden desk in a cozy "
    "firelit stone study, speaking warmly to camera. TRIPOD LOCK — absolutely static camera: "
    "zero pan, zoom, dolly, or tilt. The ENTIRE room background is frozen: stone walls, "
    "fireplace, flames, bookshelves, hanging herbs, wizard hat, papers, bottles — all "
    "perfectly steady. Only Arlo moves: natural lip sync, soft blinks, subtle breathing, "
    "small hand gestures. Preserve his blue neckerchief and green vest. No new objects. "
    "No birds. No background hallucinations."
)


def resolve_phase_a_arlo_avatar_still(event_dir: Path, production_root: Path) -> Path:
    """Return canonical Arlo wizard-desk still PNG."""
    return resolve_phase_a_arlo_idle_still(event_dir, production_root)


__all__ = [
    "ARLO_WIZARD_DESK_PROMPT",
    "AVATAR_USD_PER_SEC",
    "PHASE_A_AVATAR_ROUTE_CODE",
    "PHASE_A_LIPSYNC_METHOD_AVATAR",
    "PHASE_A_LIPSYNC_ROUTE_SINGLE_FULL_STEM",
    "estimate_avatar_pro_usd",
    "resolve_phase_a_arlo_avatar_still",
]
