"""Phase B module lipsync — Kling V2 Avatar Pro (still + audio + frozen BG prompt).

Category replacement for Kling base-loop lipsync on Phase B. Validated probe:
``run_phase_b_single_shot_avatar_probe.py`` + Event_2 job fbb800405fb54c829e12e6b795f923f7.

Operator-locked prompt hash (shared anti-caption PROHIBIT + negative_prompt, 2026-06-29):
``333483939b2087b55dc537ff9c3807052ddc82c574efd516e3809a503b17c41a``
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
    / "cedric_still_wide_16x9_v1.png"
)

# Shared by Beat Gen Avatar Pro, Phase A, and Phase B — one PROHIBIT block for all Kling Avatar Pro submits.
AVATAR_PRO_PROHIBIT = (
    "PROHIBIT: no text, no subtitles, no captions, no lower-third graphics, no watermarks, "
    "no logos, no foreign characters, no Chinese characters, no on-screen writing, "
    "no letters, no numbers, no symbols, no glyphs, no UI overlays, "
    "no second character, no humans, no extra limbs, no background hallucinations. "
    "AUDIO-TO-TEXT PROHIBIT: do NOT burn spoken dialogue into the frame. No subtitles, "
    "no captions, no closed captions, no lower-third title cards, no decorative fantasy "
    "script lettering at the bottom of frame, no karaoke lyrics, no transcript overlay. "
    "No new text anywhere in the frame — only text already baked into the input still "
    "(on papers, labels, book spines) may appear, and it must stay perfectly frozen."
)

# WaveSpeed Kling Avatar Pro negative_prompt — wired in LipSyncClient.submit_avatar_pro().
AVATAR_PRO_NEGATIVE_PROMPT = (
    "text, subtitles, captions, lower third, watermark, burned-in dialogue, "
    "foreign characters, Chinese characters, letters, numbers, glyphs, decorative script, "
    "title card, transcript overlay, karaoke lyrics, fantasy lettering"
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
    "333483939b2087b55dc537ff9c3807052ddc82c574efd516e3809a503b17c41a"
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
