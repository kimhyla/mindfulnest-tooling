"""Phase B module lipsync — Kling V2 Avatar Pro (still + audio + frozen BG prompt).

Category replacement for Kling base-loop lipsync on Phase B. Validated probe:
``run_phase_b_single_shot_avatar_probe.py`` + Event_2 job fbb800405fb54c829e12e6b795f923f7.

Operator-locked prompt hash (Event_3 insert clips, 2026-06-29):
``fe0da7a34aa2beb206bc84d25da47e78736aecd8e51575766b1570caa4420851``
Subtle Cedric motion only — NOT lively storyteller / generous gestures.
"""
from __future__ import annotations

from pathlib import Path

PHASE_B_LIPSYNC_METHOD_AVATAR = "kling_avatar_pro_v1"
PHASE_B_LIPSYNC_ROUTE_SINGLE_FULL_STEM = "single_full_stem_v1"
PHASE_B_AVATAR_ROUTE_CODE = "PHASE_B_SINGLE_SHOT_STATIC_BG_V1"

# Measured WaveSpeed bill: $2.9257 / 26.074467s (2026-06-23 Avatar chunk-0).
AVATAR_USD_PER_SEC = 0.1122

CANONICAL_CEDRIC_STILL_REL = (
    Path("NEW STYLE CHARACTERS")
    / "CEDRIC"
    / "ChatGPT Image Jun 21, 2026, 10_45_20 PM.png"
)

# Shared by Beat Gen Avatar Pro, Phase A, and Phase B — one PROHIBIT block for all Kling Avatar Pro submits.
AVATAR_PRO_PROHIBIT = (
    "PROHIBIT: no text, no subtitles, no captions, no lower-third graphics, no watermarks, "
    "no logos, no foreign characters, no Chinese characters, no on-screen writing, "
    "no letters, no numbers, no symbols, no glyphs, no UI overlays, "
    "no second character, no humans, no extra limbs, no background hallucinations."
)

# Event_3 operator-approved subtle motion + frozen room (mug steam static).
PHASE_B_CEDRIC_MOTION = (
    "Only Cedric moves: natural lip sync to the audio, soft blinks, subtle breathing, "
    "small hand gestures."
)

PHASE_B_BACKGROUND_FROZEN = (
    "The ENTIRE room background is frozen and unmoving for the full clip: stone walls, "
    "fireplace, flames, bookshelves, book spines, hanging herbs, red tapestry, wooden mug, "
    "coffee in the mug, wizard hat on desk, papers and bottles — all perfectly steady with "
    "no rippling, warping, or morphing. Do NOT animate steam, vapor, smoke, or wisps from "
    "the mug — the mug and coffee stay exactly as in the input still."
)

PHASE_B_SCENE_NEGATIVES = (
    "No new objects appear. No animals. No squirrels. No birds. No creatures in the "
    "background. No pop-in props. No background hallucinations."
)

# Legacy aliases — older tests/imports.
PHASE_B_MUG_STEAM_LOCK = (
    "Do NOT animate steam, vapor, smoke, or wisps from the mug — the mug and coffee stay "
    "exactly as in the input still."
)
PHASE_B_BACKGROUND_IDLE_LOCK = PHASE_B_BACKGROUND_FROZEN
PHASE_B_FIRE_PROHIBIT = ""

STATIC_BG_PROMPT = (
    "Cedric the elderly wizard sits at his wooden desk in a cozy firelit stone study, "
    "speaking warmly to camera. "
    "TRIPOD LOCK — absolutely static camera: zero pan, zero zoom, zero dolly, zero tilt, "
    "zero Ken Burns. "
    f"{PHASE_B_BACKGROUND_FROZEN} "
    f"{PHASE_B_CEDRIC_MOTION} "
    f"{PHASE_B_SCENE_NEGATIVES} "
    f"{AVATAR_PRO_PROHIBIT}"
)

PHASE_B_STATIC_BG_PROMPT_SHA256 = (
    "fe0da7a34aa2beb206bc84d25da47e78736aecd8e51575766b1570caa4420851"
)


def estimate_avatar_pro_usd(audio_duration_s: float) -> float:
    """Preflight budget gate — linear per-second from measured Avatar Pro bill."""
    return max(0.0, float(audio_duration_s)) * AVATAR_USD_PER_SEC


def resolve_phase_b_cedric_still(production_root: Path) -> Path:
    """Return canonical Cedric still PNG under Production root."""
    root = Path(production_root).expanduser().resolve()
    still = root / CANONICAL_CEDRIC_STILL_REL
    if not still.is_file():
        raise FileNotFoundError(f"canonical Cedric still missing: {still}")
    return still
