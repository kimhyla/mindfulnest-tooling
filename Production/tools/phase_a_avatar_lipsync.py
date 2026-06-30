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
    "small hand gestures. Both front paws stay fully visible with distinct fingers "
    "and claws exactly as in the input still — never shorten, fuse, or remove paws. "
    "Preserve his blue neckerchief and green vest."
)

PHASE_A_ARLO_PAW_NEGATIVES = (
    "No stump paws, no mitten hands, no missing paws, no fused fingers, no amputated "
    "hands, no pawless arms, no disappearing claws."
)

PHASE_A_AVATAR_NEGATIVE_PROMPT = (
    "stump paws, mitten hands, missing paws, fused fingers, amputated hands, pawless, "
    "text, subtitles, captions, lower third, watermark, burned-in dialogue, "
    "foreign characters, Chinese characters, letters, numbers, glyphs, decorative script, "
    "title card, transcript overlay, karaoke lyrics, fantasy lettering"
)

PHASE_A_BACKGROUND_FROZEN = (
    "The ENTIRE room background is frozen and unmoving for the full clip: stone walls, "
    "fireplace, flames, bookshelves, hanging herbs, red tapestry, wizard hat "
    "on desk, papers and bottles — all perfectly steady with no rippling, warping, or morphing. "
    "The input still is text-free — no labels, captions, or writing anywhere. "
    "Do not add any text, letters, numbers, or symbols anywhere in the frame."
)

PHASE_A_SCENE_NEGATIVES = (
    "No new objects appear. No animals. No birds. No squirrels in the background. "
    "No creatures in the background. No pop-in props. No background hallucinations."
)

ARLO_WIZARD_DESK_PROMPT = (
    "Arlo the humanized cartoon squirrel stands at a wizard's wooden desk in a cozy "
    "firelit stone study. Lip-sync only — match mouth movement to the separate audio "
    "track; this is NOT a tutorial, presenter, explainer, or captioned video. "
    "TRIPOD LOCK — absolutely static camera: zero pan, zero zoom, zero dolly, zero tilt, "
    "zero Ken Burns. "
    f"{PHASE_A_BACKGROUND_FROZEN} "
    f"{PHASE_A_ARLO_MOTION} "
    f"{PHASE_A_ARLO_PAW_NEGATIVES} "
    f"{PHASE_A_SCENE_NEGATIVES} "
    f"{AVATAR_PRO_PROHIBIT}"
)

PHASE_A_STATIC_BG_PROMPT_SHA256 = (
    "70c9a61c13c788da601124bb472c4926ac58e84403d11daef89f72578f45949a"
)


def resolve_phase_a_arlo_avatar_still(event_dir: Path, production_root: Path) -> Path:
    """Return canonical Arlo wizard-desk still PNG."""
    return resolve_phase_a_arlo_idle_still(event_dir, production_root)


__all__ = [
    "ARLO_WIZARD_DESK_PROMPT",
    "AVATAR_USD_PER_SEC",
    "PHASE_A_ARLO_MOTION",
    "PHASE_A_ARLO_PAW_NEGATIVES",
    "PHASE_A_AVATAR_NEGATIVE_PROMPT",
    "PHASE_A_AVATAR_ROUTE_CODE",
    "PHASE_A_BACKGROUND_FROZEN",
    "PHASE_A_LIPSYNC_METHOD_AVATAR",
    "PHASE_A_LIPSYNC_ROUTE_SINGLE_FULL_STEM",
    "PHASE_A_SCENE_NEGATIVES",
    "PHASE_A_STATIC_BG_PROMPT_SHA256",
    "estimate_avatar_pro_usd",
    "resolve_phase_a_arlo_avatar_still",
]
