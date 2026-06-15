"""Shared end-frame prompt builder — extracted from production_server.py:8349-8484.

T1-Phase 1 of MAGIC_AND_ENDFRAME_FIXES_20260520_v1 spec (LD-814).

Purpose: both `_handle_add_options_startend` (Kling B+C generation) and the new
`/api/beat/preview_end_frame` endpoint must use IDENTICAL prompt-building logic.
Pulling the logic into this module prevents drift between the two call sites.

Per cursor R1 review: NO imports from production_server.py (cycle risk). The
caller is responsible for resolving + passing in `speaker_canonical` as a
string. The helper takes only primitive inputs.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Constants (extracted verbatim from production_server.py:8382-8417, 8439-8477)
# ---------------------------------------------------------------------------

_BG_LOCK = (
    "Keep the background COMPLETELY IDENTICAL to the input — "
    "every tree, leaf, light ray, and environment element must "
    "stay pixel-perfect unchanged. Do NOT alter, shift, blur, "
    "or recompose any background element whatsoever. "
)

_MOUTH_TAIL = (
    " Mouth at rest, natural mouth geometry preserved. "
    "Same cartoon 3D Pixar-style art, same outfit, same 4:3 "
    "composition, same lighting on the character."
)

_STAGE_VERBS = {
    "looks", "look", "looking", "glances", "glance", "faces", "face",
    "turns", "turn", "turns to", "tilts", "tilt", "leans", "lean",
    "reaches", "reach", "points", "point", "raises", "raise",
    "walks", "walk", "steps", "step", "moves", "move",
    "holds", "hold", "gestures", "gesture", "nods", "nod",
    "bows", "bow", "crouches", "crouch", "stands", "stand",
    "sits", "sit", "jumps", "jump", "lands", "land",
    "extends", "extend", "lowers", "lower", "lifts", "lift",
    "shrugs", "shrug", "waves", "wave", "claps", "clap",
    "places", "place", "grabs", "grab", "drops", "drop",
    "at", "toward", "forward", "backward", "sideways", "upward", "downward",
}

_TTS_TAGS = {"pause", "break", "breath", "sigh", "silence"}

_EMOTION_MAP: dict[str, str | None] = {
    "curious":    "curious expression, eyes wide and alert, slight questioning head tilt",
    "excited":    "excited expression, eyes bright and wide, alert eager posture",
    "happy":      "warm happy expression, eyes open and bright",
    "delighted":  "delighted expression, eyes open and bright, gentle smile",
    "sad":        "gentle sad expression, soft downward gaze, eyes half-lidded",
    "worried":    "worried expression, eyes wide, slight brow tension",
    "scared":     "scared expression, eyes wide, slight lean back",
    "surprised":  "surprised expression, eyes wide, slight lean back",
    "determined": "determined expression, eyes steady and focused",
    "relieved":   "relieved expression, eyes soft and open, relaxed posture",
    "neutral":    None,  # → fallback
}

_SAFE_NEUTRAL_POSE: dict[str, str] = {
    "Chipper": "head tilted gently to one side, attentive expression",
    "Arlo":    "ears perked gently, paws relaxed, warm attentive expression",
    "Tessa":   "head tilted gently, quiet attentive expression",
    "Luna":    "head turned slightly to one side, alert expression",
    "Benson":  "one ear tilted, head turned slightly, quiet attentive expression",
    "Ember":   "head turned slightly to one side, calm relaxed gaze",
    "Bork":    "hovering in a slightly tilted position, calm expression",
    "Bramble": "head turned slightly, grounded quiet presence",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_end_frame_prompt(
    beat: dict,
    speaker_canonical: str,
    addendum: str | None = None,
) -> str:
    """Construct the OpenAI/FLUX end-frame prompt for a beat.

    Logic priority (extracted verbatim from production_server.py:8349-8484):
      1. If beat["end_frame_prompt"] is explicitly set → use it as-is (caller
         override path; bypasses heuristics).
      2. Parenthetical stage direction in beat["text"] containing a known
         stage verb → "ONLY change the character: <direction>".
      3. [emotion] tag at start of beat["text"] (excluding TTS markers) →
         mapped expression description.
      4. Neutral fallback: SAFE_NEUTRAL_POSE per speaker (small head tilt;
         renderable by FLUX Kontext without hallucination risk).

    Addendum: if non-empty, appended after the canonical prompt with a clear
    delimiter ("\\n\\nKim addendum: ...") so the model can distinguish standing
    instructions from per-call corrections. One-shot per call — caller is
    responsible for not persisting addendum across calls (see spec §2 T1-Phase 6
    addendum auto-clear UX).

    Args:
        beat: the beat dict from state.json (must have "text" and ideally
            "speaker"; "end_frame_prompt" if explicitly configured).
        speaker_canonical: the canonicalized speaker name (Tessa / Luna /
            Chipper / etc). Caller resolves this via the same logic as
            production_server.py:_canonicalize_speaker — passed in as a string
            to avoid cycle imports (cursor R1 review 2026-05-20).
        addendum: optional one-shot prompt addendum from Kim (e.g. "ensure
            all accessories remain"). Appended verbatim if non-empty.

    Returns:
        The full end-frame prompt string ready to send to OpenAI gpt-image-1
        or FLUX Kontext.
    """
    end_frame_prompt = (beat.get("end_frame_prompt") or "").strip()

    if not end_frame_prompt:
        beat_text = (beat.get("text") or "").strip()

        # 1. (parenthetical) anywhere → stage direction only.
        _paren = re.search(r'\(([^)]{3,})\)', beat_text)
        if _paren:
            char_dir = _paren.group(1).strip()
            _paren_words = set(re.findall(r'\w+', char_dir.lower()))
            _is_stage_direction = bool(_paren_words & _STAGE_VERBS)
            if _is_stage_direction:
                end_frame_prompt = (
                    _BG_LOCK
                    + f"ONLY change the character: {char_dir}."
                    + _MOUTH_TAIL
                )

        # 2. [emotion] at start of text → map to expression description.
        if not end_frame_prompt:
            _start_tag = re.match(r'^\[([^\]]+)\]', beat_text)
            _emotion = _start_tag.group(1).lower().strip() if _start_tag else ""
            if _emotion and _emotion not in _TTS_TAGS and _emotion in _EMOTION_MAP:
                char_dir = _EMOTION_MAP[_emotion]
                if char_dir:
                    end_frame_prompt = (
                        _BG_LOCK
                        + f"ONLY change the character: {char_dir}."
                        + _MOUTH_TAIL
                    )

        # 3. Neutral fallback — safe static geometric pose per speaker.
        if not end_frame_prompt:
            _safe_pose = _SAFE_NEUTRAL_POSE.get(
                speaker_canonical,
                "head tilted gently, attentive expression",
            )
            end_frame_prompt = (
                _BG_LOCK
                + f"ONLY change the character: {_safe_pose}."
                + _MOUTH_TAIL
            )

    # Addendum: one-shot Kim correction appended AFTER canonical, BEFORE any
    # vendor-specific safety suffix (the caller may add Rule 8 mouth/beak
    # phrasing on top; this helper keeps the addendum cleanly between).
    if addendum:
        _add = addendum.strip()
        if _add:
            end_frame_prompt = f"{end_frame_prompt}\n\nKim addendum: {_add}"

    return end_frame_prompt
