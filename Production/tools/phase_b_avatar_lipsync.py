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

# Shared by Beat Gen Avatar Pro, Phase A, and Phase B — one PROHIBIT block for all Kling Avatar Pro submits.
AVATAR_PRO_PROHIBIT = (
    "PROHIBIT: no text, no subtitles, no captions, no lower-third graphics, no watermarks, "
    "no logos, no foreign characters, no Chinese characters, no on-screen writing, "
    "no letters, no numbers, no symbols, no glyphs, no UI overlays, "
    "no second character, no humans, no extra limbs, no background hallucinations."
)

# Phase B Cedric study — freeze the room (including hearth); Cedric stays freely animated.
PHASE_B_CEDRIC_MOTION = (
    "Cedric is warmly animated and expressive throughout — natural lip sync to the audio with full "
    "facial performance: eyebrow raises, eye contact, smiles, thoughtful pauses, head tilts, leaning "
    "toward camera when engaged. Generous upper-body and hand gestures: he may lift his wooden mug, "
    "gesture openly, emphasize points, shift posture at the desk — lively storyteller energy, not "
    "stiff or minimal. Stay seated at the desk; do not stand, walk, or leave frame."
)

# Mug steam only — never use fire/flame vocabulary near the mug (Kling bleeds hearth fire into the cup).
PHASE_B_MUG_STEAM_LOCK = (
    "The wooden mug holds coffee. ONLY pale white translucent steam wisps may rise from the mug — "
    "slow, gentle, repeating curls of vapor only. The mug contents stay dark liquid coffee: "
    "NEVER orange, NEVER yellow, NEVER red, NEVER glowing, NEVER burning, NEVER on fire, "
    "NEVER flame, NEVER embers, NEVER sparks inside or above the cup."
)

PHASE_B_BACKGROUND_IDLE_LOCK = (
    "BACKGROUND IDLE LOCK — the room is a completely frozen set. Every background surface and prop "
    "stays perfectly still and unchanged for the entire duration: stone walls, fireplace, hearth, "
    "fire, flames, embers, logs, bookshelves, book spines, hanging herbs, red tapestry, wizard hat "
    "on desk, papers, bottles, desk wood grain — all frozen exactly as in the input still with "
    "zero rippling, warping, morphing, flickering, evolving textures, or developing patterns. "
    "Do NOT animate the fireplace or hearth — no smoke drift, no flame movement, no fire changes. "
    f"Besides Cedric, ONLY one gentle ambient loop is allowed in the whole room: "
    f"{PHASE_B_MUG_STEAM_LOCK} "
    "Zero pop-in, zero fade-in, zero materialization, zero new objects, zero animals, "
    "zero creatures, zero second characters, zero new pixels appearing in the background. "
    "Nothing pops up, grows, spreads, develops, or changes anywhere in the background. "
    "The set stays a calm idle portrait — Cedric alone drives character motion."
)

PHASE_B_FIRE_PROHIBIT = (
    "PROHIBIT FIRE BLEED: no flames in the mug, no fire in the coffee, no burning liquid, "
    "no torch in hand, no orange fire above the cup, no conflating mug steam with hearth fire."
)

_STATIC_BG_BODY = (
    "Cedric the elderly wizard sits at his wooden desk in a cozy warmly lit stone study, "
    "speaking warmly to camera. "
    f"{PHASE_B_CEDRIC_MOTION} "
    "TRIPOD LOCK — absolutely static camera: zero pan, zero zoom, zero dolly, zero tilt, "
    "zero Ken Burns. "
    f"{PHASE_B_BACKGROUND_IDLE_LOCK} "
    f"{PHASE_B_FIRE_PROHIBIT}"
)

STATIC_BG_PROMPT = f"{_STATIC_BG_BODY} {AVATAR_PRO_PROHIBIT}"


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
