"""
CLAUDE.md Rule 8 §8.1 + §8.2 prompt validator.

Closes the §8.1 banned-word + §8.2 do-not-stack class of failures structurally.
Used by the Kling MCP server's animation tools to reject malformed prompts at
the tool boundary before any vendor API call is made.

Three documented incidents motivated this validator:
- 2026-04-14 Seedance Chinese-phoneme lipsync (banned-word check would NOT
  have caught this, but Rule 8.1 mandates Kling default which prevents it).
- 2026-04-17 Option D LatentSync starvation (cfg=0.75 + stacked gaze/mouth/
  motion locks — exactly the §8.2 do-not-stack rule. THIS validator catches.).
- 2026-04-24 Chinese watermark + scene hallucination (LD-400 §8.5 violation
  — covered by `bytedance_lipsync` tool's auto-router, NOT this validator).

Severity: HIGH. The validator is part of the structural-enforcement contract
locked at LD-660 + LD-663 (Directus MCP precedent) and the upcoming Kling MCP
LD `WAVESPEED_KLING_MCP_PHASE1_V1`.

INVARIANTS (Rule 36):
- LEVER_PATTERNS classifies positive-prompt phrases into 4 lever categories
  per CLAUDE.md §8.2 do-not-stack rule. Any change to category names OR regex
  patterns must update the spec + LD-162 reference + matching tests.
- BANNED_WORDS is per CLAUDE.md §8.1 (the master list). Adding/removing
  requires CLAUDE.md amendment.
- The §8.3 endpoint-anchor exception (`has_endframe_pixel_anchor=True`) is
  the ONE allowed combination per §8.2 amended rule. Loosening this further
  re-introduces the LatentSync starvation incident class.
"""

from __future__ import annotations

import re
from typing import Optional

# CLAUDE.md §8.1 — banned in motion prompts (positive OR via prompt-side
# leakage). These trigger speech animation in most video models.
BANNED_WORDS: frozenset[str] = frozenset({
    "speaking",
    "speech",
    "dialogue",
    "lip sync",
    "lip movement",
    "mouth movement",
    "beak movement",
    "talking",
    "singing",
    "vocal",
})

# CLAUDE.md §8.1 — required mouth/beak constraint per character type.
REQUIRED_MOUTH_CONSTRAINT: dict[str, str] = {
    "bird": "Beak closed, no speech, no lip movement",
    "turtle": "Mouth closed, no speech",
    "mammal": "Mouth closed, no speech",
    "fox": "Mouth closed, no speech",
    "bunny": "Mouth closed, no speech",
    "bear": "Mouth closed, no speech",
    "firefly": "no speech",  # Bork is a firefly — no mouth, just no audio
}

# CLAUDE.md §8.1 — required tail phrase. One of these must appear.
REQUIRED_TAIL_PHRASES: tuple[str, ...] = (
    "Silent subtle idle movement only",
    "no dialogue in video",
)

# CLAUDE.md §8.2 — do-not-stack lever categories. Stacking ANY TWO of these
# (when lipsync_targeted=True and NOT has_endframe_pixel_anchor) is forbidden.
LEVER_PATTERNS: dict[str, list[str]] = {
    "gaze_lock": [
        r"\beyes?\s+(meet|on|locked\s+to|facing)\s+camera",
        r"\b(face|head)\s+centered",
        r"\bdirect\s+forward\s+gaze",
        r"\bcamera[-\s]facing\s+(throughout|gaze)",
        r"\b(eye\s+contact|eyes\s+meet\s+(viewer|camera))",
    ],
    "mouth_lock_intensifier": [
        # Beyond the §8.1 baseline ("beak closed" / "mouth closed") — these
        # intensifiers (pressed/sealed/tight/clamped) flatten the mouth pixel
        # region and starve LatentSync per LD-162.
        r"\bbeak\s+(pressed|sealed|tight|clamped)",
        r"\bmouth\s+(pressed|sealed|tight|clamped)",
        r"\blips?\s+(pressed|sealed|tight|clamped)",
    ],
    "motion_lock": [
        r"\bminimal\s+motion\b",
        r"\bstatic\s+camera\b",
        r"\bhead\s+(remains|stays)\s+facing\b",
        r"\bno\s+head\s+movement\b",
        r"\bfrozen\s+face\b",
        r"\bdon'?t\s+move\s+(head|face)\b",
        r"\bhead\s+held\s+still\b",
    ],
}

# Compiled patterns (compile once at import).
_COMPILED: dict[str, list[re.Pattern[str]]] = {
    cat: [re.compile(p, re.IGNORECASE) for p in patterns]
    for cat, patterns in LEVER_PATTERNS.items()
}


def detect_banned_words(prompt: str) -> list[str]:
    """Return list of §8.1 banned words found in `prompt`, NEGATION-AWARE.

    A banned word is "present" only if it appears in the prompt NOT preceded by
    a negation marker. The §8.1 *required* mouth constraints contain "no speech",
    "no lip movement", etc. — those are negations of the banned words and MUST
    NOT trigger detection. Without negation-awareness, a clean §8.1-compliant
    prompt would falsely fail validation.

    Negation markers: "no ", "without ", "zero " (case-insensitive). Word
    boundaries enforced via \\b on both sides where the banned phrase is a
    single word; for multi-word banned phrases (e.g., "lip sync") the regex
    handles the whole phrase.
    """
    if not isinstance(prompt, str) or not prompt:
        return []
    p = prompt.lower()
    found: set[str] = set()
    for w in BANNED_WORDS:
        # Build a regex: NOT preceded by negation marker, then the banned word
        # bounded by word breaks (or end-of-string).
        # Negative lookbehind for fixed-width: "no ", "without ", "zero ".
        # Use multiple lookbehind alternatives via separate patterns and OR.
        # `\b<word>\b` — word boundary on both sides.
        word_pattern = re.escape(w)
        # Negative lookbehind alternatives (each is fixed-width)
        # "no " = 3 chars, "zero " = 5 chars, "without " = 8 chars.
        # Python re requires fixed-width lookbehinds, so combine alternatives:
        pattern = (
            r"(?<!\bno\s)(?<!\bwithout\s)(?<!\bzero\s)\b"
            + word_pattern
            + r"\b"
        )
        # Note: re.escape handles spaces in multi-word banned phrases like
        # "lip sync" — the \b at boundaries works because the phrase is
        # bracketed by non-word boundaries in normal English text.
        if re.search(pattern, p):
            found.add(w)
    return sorted(found)


def detect_levers(positive_prompt: str) -> list[str]:
    """Return list of §8.2 lever category names triggered by phrases in `positive_prompt`.

    Pure regex scan; no semantic interpretation. Names are stable identifiers
    referenced by spec §3 and LD-162.
    """
    if not isinstance(positive_prompt, str) or not positive_prompt:
        return []
    triggered: list[str] = []
    for cat, regexes in _COMPILED.items():
        if any(r.search(positive_prompt) for r in regexes):
            triggered.append(cat)
    return triggered


def validate_motion_prompt(
    positive_prompt: str,
    character_type: Optional[str] = None,
) -> dict:
    """Validate a Kling motion prompt against CLAUDE.md §8.1.

    Args:
        positive_prompt: The positive prompt text passed to Kling.
        character_type: Optional — if set to a key in REQUIRED_MOUTH_CONSTRAINT,
            checks the prompt for the required mouth/beak constraint phrase.

    Returns:
        {
            "ok": bool,
            "banned_words": list[str],     # §8.1 violations
            "missing_mouth_constraint": Optional[str],  # if character_type set
            "has_required_tail": bool,     # §8.1 tail check
            "violation": Optional[str],    # human-readable summary
        }

    Does NOT raise. Caller decides whether to refuse based on `ok`.
    """
    banned = detect_banned_words(positive_prompt)

    missing_mouth: Optional[str] = None
    if character_type and character_type.lower() in REQUIRED_MOUTH_CONSTRAINT:
        required = REQUIRED_MOUTH_CONSTRAINT[character_type.lower()]
        # Match the constraint loosely — exact match is too strict because the
        # required phrase is a fragment, not always literally present. Look
        # for any of the key phrases.
        key_phrases = [p.strip() for p in required.split(",")]
        if not any(kp.lower() in positive_prompt.lower() for kp in key_phrases):
            missing_mouth = required

    has_tail = any(
        tail.lower() in positive_prompt.lower() for tail in REQUIRED_TAIL_PHRASES
    )

    ok = not banned and missing_mouth is None and has_tail
    violation: Optional[str] = None
    if not ok:
        bits = []
        if banned:
            bits.append(f"banned_words: {banned}")
        if missing_mouth:
            bits.append(f"missing_mouth_constraint: {missing_mouth!r}")
        if not has_tail:
            bits.append(f"missing_tail: one of {REQUIRED_TAIL_PHRASES!r} required")
        violation = "; ".join(bits)

    return {
        "ok": ok,
        "banned_words": banned,
        "missing_mouth_constraint": missing_mouth,
        "has_required_tail": has_tail,
        "violation": violation,
    }


def validate_lipsync_prompt(
    positive_prompt: str,
    cfg_scale: float = 0.5,
    has_endframe_pixel_anchor: bool = False,
    character_type: Optional[str] = None,
) -> dict:
    """Validate a lipsync-targeted Kling prompt against §8.1 + §8.2 do-not-stack.

    The §8.2 do-not-stack rule: on a lipsync-targeted clip, may not combine
    ANY TWO of: cfg_scale > 0.5, gaze_lock, mouth_lock_intensifier, motion_lock.

    The §8.3 endpoint-anchor exception: when both endpoints have natural 3D
    mouth geometry (start_image + end_image with non-flat mouths), pixel-level
    anchoring is the ONE allowed exception — caller passes
    `has_endframe_pixel_anchor=True` to acknowledge this. Even with the
    exception, the §8.1 motion-prompt baseline still applies.

    Returns:
        {
            "ok": bool,
            "levers": list[str],           # which lever categories triggered
            "lever_count": int,            # total lever count incl. cfg
            "cfg_violation": bool,         # cfg > 0.5 with lipsync_target
            "motion_validation": dict,     # nested validate_motion_prompt result
            "violation": Optional[str],    # human-readable summary
        }

    Does NOT raise. Caller decides.
    """
    motion = validate_motion_prompt(positive_prompt, character_type=character_type)

    levers = detect_levers(positive_prompt)
    cfg_violation = cfg_scale > 0.5

    # Stacking detection — count distinct levers including cfg as one lever.
    lever_total = len(levers) + (1 if cfg_violation else 0)

    # Per §8.3: pixel anchor allows the ONE combination of pixel-gaze-lock with
    # §8.1 negatives. We treat has_endframe_pixel_anchor=True as suppressing
    # gaze_lock from the count (the anchor IS the gaze lock — it's been moved
    # to pixel-level in start/end frames, not positive prompt).
    if has_endframe_pixel_anchor and "gaze_lock" in levers:
        # Allowed: drop gaze_lock from the count
        lever_total -= 1
        levers = [l for l in levers if l != "gaze_lock"]

    do_not_stack_violation = lever_total >= 2

    ok = motion["ok"] and not do_not_stack_violation
    violation: Optional[str] = motion.get("violation")
    if do_not_stack_violation:
        bits = [f"do_not_stack: {lever_total} levers triggered: {levers}"]
        if cfg_violation:
            bits.append(f"cfg_scale={cfg_scale} > 0.5")
        bits.append(
            "Per CLAUDE.md §8.2 + LD-162, lipsync-targeted clips may not "
            "combine ANY TWO of: cfg>0.5, gaze_lock, mouth_lock_intensifier, "
            "motion_lock. Reduce to at most ONE lever."
        )
        v = "; ".join(bits)
        violation = (violation + " | " + v) if violation else v

    return {
        "ok": ok,
        "levers": levers,
        "lever_count": lever_total,
        "cfg_violation": cfg_violation,
        "motion_validation": motion,
        "violation": violation,
    }
