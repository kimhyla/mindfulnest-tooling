"""Phase A module lipsync — Kling V2 Avatar Pro (Arlo wizard-desk still + voice stem).

Category replacement for ByteDance-on-base-clip (2026-06-24). Validated probe:
Event_2 ``phase_a_avatar_pro_probe/`` job ``4c1d0315b39845a9b2b80b54314d59f2`` (~10s).

Operator-locked prompt hash (Phase B parity restructure + shared anti-caption PROHIBIT, 2026-06-29).
"""
from __future__ import annotations

from pathlib import Path

from phase_a_arlo_contract import resolve_phase_a_arlo_idle_still
from phase_b_avatar_lipsync import AVATAR_PRO_PROHIBIT, AVATAR_USD_PER_SEC, estimate_avatar_pro_usd

PHASE_A_LIPSYNC_METHOD_AVATAR = "kling_avatar_pro_v1"
PHASE_A_LIPSYNC_ROUTE_SINGLE_FULL_STEM = "single_full_stem_v1"
PHASE_A_AVATAR_ROUTE_CODE = "PHASE_A_SINGLE_SHOT_STATIC_BG_V1"

PHASE_A_ARLO_MOTION = (
    "Only Arlo moves: natural lip sync to the audio, soft blinks, subtle breathing, "
    "small hand gestures. Preserve his blue neckerchief and green vest."
)

PHASE_A_BACKGROUND_FROZEN = (
    "The ENTIRE room background is frozen and unmoving for the full clip: stone walls, "
    "fireplace, flames, bookshelves, book spines, hanging herbs, red tapestry, wizard hat "
    "on desk, papers and bottles — all perfectly steady with no rippling, warping, or morphing. "
    "Any text visible on papers, labels, or book spines in the input still must stay perfectly "
    "frozen — do not add new text anywhere in the frame."
)

PHASE_A_SCENE_NEGATIVES = (
    "No new objects appear. No animals. No birds. No squirrels in the background. "
    "No creatures in the background. No pop-in props. No background hallucinations."
)

ARLO_WIZARD_DESK_PROMPT = (
    "Arlo the humanized cartoon squirrel stands at a wizard's wooden desk in a cozy "
    "firelit stone study, speaking warmly to camera. "
    "TRIPOD LOCK — absolutely static camera: zero pan, zero zoom, zero dolly, zero tilt, "
    "zero Ken Burns. "
    f"{PHASE_A_BACKGROUND_FROZEN} "
    f"{PHASE_A_ARLO_MOTION} "
    f"{PHASE_A_SCENE_NEGATIVES} "
    f"{AVATAR_PRO_PROHIBIT}"
)

PHASE_A_STATIC_BG_PROMPT_SHA256 = (
    "5ca2fb036694b6c148e14f183fa32a1e38b4f9dd8bc12cbd231974931919a744"
)


def resolve_phase_a_arlo_avatar_still(event_dir: Path, production_root: Path) -> Path:
    """Return canonical Arlo wizard-desk still PNG."""
    return resolve_phase_a_arlo_idle_still(event_dir, production_root)


__all__ = [
    "ARLO_WIZARD_DESK_PROMPT",
    "AVATAR_USD_PER_SEC",
    "PHASE_A_ARLO_MOTION",
    "PHASE_A_AVATAR_ROUTE_CODE",
    "PHASE_A_BACKGROUND_FROZEN",
    "PHASE_A_LIPSYNC_METHOD_AVATAR",
    "PHASE_A_LIPSYNC_ROUTE_SINGLE_FULL_STEM",
    "PHASE_A_SCENE_NEGATIVES",
    "PHASE_A_STATIC_BG_PROMPT_SHA256",
    "estimate_avatar_pro_usd",
    "resolve_phase_a_arlo_avatar_still",
]
