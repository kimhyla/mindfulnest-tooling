"""Phase B module lipsync — Kling V2 Avatar Pro (still + audio + frozen BG prompt).

Category replacement for Kling base-loop lipsync on Phase B. Validated probe:
``run_phase_b_single_shot_avatar_probe.py`` + Event_2 job fbb800405fb54c829e12e6b795f923f7.
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

STATIC_BG_PROMPT = (
    "Cedric the elderly wizard sits at his wooden desk in a cozy firelit stone study, "
    "speaking warmly to camera. TRIPOD LOCK — absolutely static camera: zero pan, zero zoom, "
    "zero dolly, zero tilt, zero Ken Burns. The ENTIRE room background is frozen and unmoving for "
    "the full clip: stone walls, fireplace, flames, bookshelves, book spines, hanging herbs, "
    "red tapestry, mug steam pattern, wizard hat on desk, papers and bottles — all perfectly "
    "steady with no rippling, warping, or morphing. Only Cedric moves: natural lip sync to the "
    "audio, soft blinks, subtle breathing, small hand gestures. No new objects appear. "
    "No animals. No squirrels. No birds. No creatures in the background. No pop-in props. "
    "No background hallucinations."
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
