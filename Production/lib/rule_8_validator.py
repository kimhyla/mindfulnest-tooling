"""Rule 8 lipsync-safety validator.

Per LD-722 STORYBOARD_TTS_KLING_PROMPT_SEPARATION_DEFERRED_V1 §reopen-condition (c):
"verify Production/lib/rule_8_validator.py is present + tracked in git before Phase 1".

Per CLAUDE.md Rule 8 (Motion Prompt Lip-Sync Prevention) §8.1: motion prompts sent to
Kling MUST NOT contain banned-words that trigger speech/lipsync animation:
  speaking, speech, dialogue, lip sync, lip movement, mouth movement,
  beak movement, talking, singing, vocal

Required clamps:
  - Bird speakers: "Beak closed, no speech, no lip movement"
  - Turtle/mammal speakers: "Mouth closed, no speech"
  - Trailing: "Silent subtle idle movement only" OR "no dialogue in video"

API parameters (validated separately at submit-time, not here):
  - sound: false
  - negative_prompt: anti-lipsync list
  - cfg_scale: 0.5

Use:
    from lib.rule_8_validator import validate_motion_prompt, Rule8ValidationError
    try:
        validate_motion_prompt(text, speaker="Tessa")
    except Rule8ValidationError as e:
        # surface to UI
        ...
"""
from __future__ import annotations

import re
from dataclasses import dataclass


# ────────────────────────────────────────────────────────────────────────
# Banned words per §8.1 (case-insensitive, word-boundary)
# ────────────────────────────────────────────────────────────────────────
BANNED_MOTION_WORDS = (
    "speaking",
    "speech",
    "dialogue",
    "lip sync",
    "lip movement",
    "lip-sync",
    "lipsync",
    "mouth movement",
    "beak movement",
    "talking",
    "singing",
    "vocal",
)

# ────────────────────────────────────────────────────────────────────────
# Speaker → required mouth/beak clamp (§8.1)
# ────────────────────────────────────────────────────────────────────────
# Birds: beak; turtles/mammals: mouth.
# HARMONIZED 2026-05-20 with production_server.py:423 to prevent
# validator-disagreement (cursor-review finding #6). Luna inclusion
# is a known anatomical mismatch (turtle, not bird) but production_server
# treats Luna as bird-class for Kling beak-clamp purposes. See
# DEVIATION_SYSTEMIC_AUDIT_LUNA_BIRD_CLASSIFICATION_20260520 for
# Kim-workflow question on whether to reclassify.
BIRD_SPEAKERS = {"Guide Bird", "Luna", "Chipper"}
# All others default to "mouth closed".

REQUIRED_TRAILER_OPTIONS = (
    "silent subtle idle movement only",
    "no dialogue in video",
    "no dialogue",
)


@dataclass
class Rule8ValidationError(Exception):
    """Raised when a motion prompt violates Rule 8 / §8.1."""

    reason: str
    banned_terms_found: list[str]
    speaker: str | None = None

    def __str__(self) -> str:  # noqa: D401
        return f"Rule8 violation ({self.speaker or 'unknown speaker'}): {self.reason}"


def _find_banned(text: str) -> list[str]:
    lowered = text.lower()
    found: list[str] = []
    for word in BANNED_MOTION_WORDS:
        # Word-boundary for single-word terms; substring for multi-word
        if " " in word:
            if word in lowered:
                found.append(word)
        else:
            if re.search(rf"\b{re.escape(word)}\b", lowered):
                found.append(word)
    return found


def _has_required_clamp(text: str, speaker: str | None) -> bool:
    lowered = text.lower()
    if speaker in BIRD_SPEAKERS:
        return "beak closed" in lowered or "beak at rest" in lowered
    return "mouth closed" in lowered or "mouth at rest" in lowered


def _has_required_trailer(text: str) -> bool:
    lowered = text.lower()
    return any(opt in lowered for opt in REQUIRED_TRAILER_OPTIONS)


def validate_motion_prompt(text: str, speaker: str | None = None,
                            strict_trailer: bool = False) -> None:
    """Raise Rule8ValidationError if motion prompt violates §8.1.

    Args:
        text: candidate motion prompt string
        speaker: canonical speaker name (e.g. "Tessa", "Chipper") — drives
            bird-vs-mammal clamp requirement
        strict_trailer: if True, also require trailing silence cue
            ("Silent subtle idle movement only" / "no dialogue in video"). Default
            False (clamp is the load-bearing check; trailer is style).

    Raises:
        Rule8ValidationError on any violation.
    """
    if not isinstance(text, str) or not text.strip():
        raise Rule8ValidationError(
            reason="empty motion prompt",
            banned_terms_found=[],
            speaker=speaker,
        )

    banned = _find_banned(text)
    if banned:
        raise Rule8ValidationError(
            reason=f"banned terms found: {banned}",
            banned_terms_found=banned,
            speaker=speaker,
        )

    if speaker and not _has_required_clamp(text, speaker):
        kind = "beak closed" if speaker in BIRD_SPEAKERS else "mouth closed"
        raise Rule8ValidationError(
            reason=f"missing required clamp for {speaker!r}: must include '{kind}'",
            banned_terms_found=[],
            speaker=speaker,
        )

    if strict_trailer and not _has_required_trailer(text):
        raise Rule8ValidationError(
            reason="missing required trailer (e.g. 'Silent subtle idle movement only' or 'no dialogue in video')",
            banned_terms_found=[],
            speaker=speaker,
        )


def is_valid(text: str, speaker: str | None = None, strict_trailer: bool = False) -> bool:
    """Boolean wrapper for validate_motion_prompt."""
    try:
        validate_motion_prompt(text, speaker=speaker, strict_trailer=strict_trailer)
        return True
    except Rule8ValidationError:
        return False
