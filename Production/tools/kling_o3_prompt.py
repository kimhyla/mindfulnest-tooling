"""Locked Kling O3 voice delivery phrases — beat-to-beat consistency.

Same Element + kling_voice_id gives the same clone; these prompt locks keep
delivery steady and prevent bubbly/hyper reads (Chipper fix reused for Arlo).
"""

from __future__ import annotations

import re

KLING_O3_CHIPPER_VOICE_DELIVERY = (
    "warm calm conversational pace, steady and natural, clear delivery, "
    "brisk but not rushed, not bubbly or hyper, not slow, not dramatic, not childlike or baby-talk"
)

# Arlo shares Chipper1 create-voice today; use identical delivery lock until Arlo gets his own clone.
KLING_O3_ARLO_VOICE_DELIVERY = KLING_O3_CHIPPER_VOICE_DELIVERY

KLING_O3_TESSA_VOICE_DELIVERY = (
    "warm gentle conversational pace, soft and vulnerable but clear, natural delivery, "
    "steady and not slow, not dragging, not whispered, not childlike or baby-talk"
)

KLING_O3_LORELAI_VOICE_DELIVERY = (
    "warm excited conversational pace, clear scholarly delivery, measured deliberate cadence, "
    "slower steady rhythm, not rushed or frantic, not hyper or sputtering, "
    "not dragging, not childlike or baby-talk"
)

_DELIVERY_BY_SPEAKER: dict[str, str] = {
    "Chipper": KLING_O3_CHIPPER_VOICE_DELIVERY,
    "Arlo": KLING_O3_ARLO_VOICE_DELIVERY,
    "Tessa": KLING_O3_TESSA_VOICE_DELIVERY,
    "Lorelai": KLING_O3_LORELAI_VOICE_DELIVERY,
    "Laurel": KLING_O3_LORELAI_VOICE_DELIVERY,
}

_VOICE_SPEAKER_NAMES = "|".join(re.escape(name) for name in _DELIVERY_BY_SPEAKER)
_BRACKET_PERFORMANCE_TAG_RE = re.compile(
    rf"\b(?:{_VOICE_SPEAKER_NAMES})\s+\[[^\]]+\]\s*:",
    re.I,
)
_SPEAKS_BRACKET_TAG_RE = re.compile(r"\bspeaks\s*\[[^\]]+\]\s*:", re.I)
_VOICE_LINE_VERB_RE = re.compile(r"\b(speaks|says)\b", re.I)

# Performance tags stay inside quoted dialogue; emotion tags go OUTSIDE quotes (Kling reads
# bracket words aloud when they sit inside "…").
_PERFORMANCE_TAG_WORDS = frozenset({"pause", "break", "silence"})

_ROOTED_IN_PLACE_RE = re.compile(r",?\s*rooted in place\.?", re.I)
_NO_LOCOMOTION_RE = re.compile(r",?\s*no locomotion\.?", re.I)


def strip_rooted_in_place(text: str) -> str:
    """Remove banned staging boilerplate from scene_notes / prompts."""
    s = text or ""
    s = _ROOTED_IN_PLACE_RE.sub("", s)
    s = _NO_LOCOMOTION_RE.sub("", s)
    s = re.sub(r"\s*—\s*,", " ", s)
    s = re.sub(r"\s+", " ", s).strip(" ,.;—")
    return s


def format_emotion_tag(emotion: str) -> str:
    emo = (emotion or "").strip()
    if not emo or emo.lower() == "neutral":
        return ""
    if emo.startswith("[") and emo.endswith("]"):
        return emo
    return f"[{emo}]"


def strip_leading_emotion_tags_from_spoken(spoken: str) -> str:
    """Move mis-placed [emotion] tags out of quoted dialogue (keep [pause] etc.)."""
    s = (spoken or "").strip()
    while True:
        m = re.match(r"^\[([^\]]+)\]\s*", s)
        if not m:
            break
        inner = m.group(1).strip().lower()
        if inner in _PERFORMANCE_TAG_WORDS:
            break
        s = s[m.end() :].strip()
    return s


def delivery_for_speaker(speaker: str) -> str | None:
    """Canonical O3 delivery phrase for a locked speaker, if any."""
    canon = (speaker or "").strip()
    if canon == "Laurel":
        canon = "Lorelai"
    return _DELIVERY_BY_SPEAKER.get(canon)


def voice_line_has_bracket_performance_tags(line: str) -> bool:
    """Detect author bracket delivery tags on the voice line (not canonical lock)."""
    text = (line or "").strip()
    if not text:
        return False
    if _SPEAKS_BRACKET_TAG_RE.search(text):
        return True
    if _BRACKET_PERFORMANCE_TAG_RE.search(text):
        return True
    return False


def voice_line_has_canonical_delivery(speaker: str, line: str) -> bool:
    """True when the line uses speaks-in-a plus the speaker's canonical delivery lock."""
    delivery = delivery_for_speaker(speaker)
    if not delivery:
        return True
    lower = (line or "").lower()
    if "speaks in a" not in lower:
        return False
    return delivery.lower() in lower


def _voice_line_candidate_score(line: str) -> int:
    """Rank prompt lines — prefer explicit dialogue delivery over staging 'speaks to camera'."""
    text = (line or "").strip()
    if not text:
        return 0
    if voice_line_has_bracket_performance_tags(text):
        return 100
    low = text.lower()
    if "<<<voice_" in low:
        return 90
    if re.search(r":\s*[\"']", text):
        return 80
    if "speaks in a" in low:
        return 70
    if _VOICE_LINE_VERB_RE.search(text):
        return 10
    return 0


def _find_voice_delivery_line(lines: list[str]) -> tuple[int, str] | None:
    """Return (index, line) for the strongest voice-delivery candidate in the prompt."""
    best_idx = -1
    best_score = 0
    for idx, line in enumerate(lines):
        score = _voice_line_candidate_score(line)
        if score > best_score:
            best_score = score
            best_idx = idx
    if best_idx < 0 or best_score <= 0:
        return None
    return best_idx, lines[best_idx]


def _is_voice_candidate_line(line: str) -> bool:
    return _voice_line_candidate_score(line) > 0


def _prompt_needs_locked_voice_upgrade(speaker: str, prompt: str) -> bool:
    """True when an Element-bound prompt still uses non-canonical delivery wording."""
    text = (prompt or "").strip()
    if not text or not delivery_for_speaker(speaker):
        return False
    if _prompt_needs_kling_name_normalization(speaker, text):
        return True
    lower = text.lower()
    if "<<<voice_" in lower:
        return True
    lines = text.splitlines()
    found = _find_voice_delivery_line(lines)
    if not found:
        return False
    _idx, voice_line = found
    if voice_line_has_bracket_performance_tags(voice_line):
        return True
    if not voice_line_has_canonical_delivery(speaker, voice_line):
        return True
    if not _voice_line_matches_kling_display_name(speaker, voice_line):
        return True
    return False


def _kling_display_name_for_speaker(speaker: str) -> str | None:
    try:
        from tools import kling_character_registry as reg

        return reg.kling_element_display_name(speaker)
    except Exception:
        return None


def _voice_line_matches_kling_display_name(speaker: str, voice_line: str) -> bool:
    display = _kling_display_name_for_speaker(speaker)
    if not display:
        return True
    return bool(re.search(rf"\b{re.escape(display)}\s+(?:speaks|says)\b", voice_line, re.I))


def _prompt_needs_kling_name_normalization(speaker: str, prompt: str) -> bool:
    display = _kling_display_name_for_speaker(speaker)
    if not display:
        return False
    text = prompt or ""
    if re.search(r"@Image1\s*\(\s*Character\s*\)", text, re.I):
        return True
    if display == (speaker or "").strip():
        return False
    if re.search(r"@Image1\s*\(\s*Lorelai\s*\)", text, re.I):
        return True
    if re.search(r"\bLorelai\s+(?:speaks|says)\b", text, re.I):
        return True
    lines = text.splitlines()
    found = _find_voice_delivery_line(lines)
    if found and not _voice_line_matches_kling_display_name(speaker, found[1]):
        return True
    return False


def normalize_kling_speaker_names_in_prompt(prompt: str, speaker: str) -> str:
    """Map registry speaker names to Kling Element display names (Lorelai → Laurel)."""
    display = _kling_display_name_for_speaker(speaker)
    if not display:
        return prompt
    out = prompt or ""
    out = re.sub(r"@Image1\s*\(\s*Character\s*\)", f"@Image1 ({display})", out, flags=re.I)
    try:
        from tools import kling_character_registry as reg

        reg_key = reg.resolve_registry_key(speaker) or (speaker or "").strip()
        if reg_key in reg._KLING_ELEMENT_DISPLAY_NAME:
            out = re.sub(r"@Image1\s*\(\s*Lorelai\s*\)", f"@Image1 ({display})", out, flags=re.I)
            out = re.sub(
                r"\bLorelai(\s+(?:speaks|says|looks|bursts|cries|whispers|shouts)\b)",
                rf"{display}\1",
                out,
                flags=re.I,
            )
            # Staging lines like "Lorelai Close-up …" do not match verb patterns above.
            out = re.sub(r"(?m)^Lorelai\s+", f"{display} ", out)
    except Exception:
        pass
    return out


def prompt_staging_leaks_registry_speaker_name(speaker: str, prompt: str) -> bool:
    """True when registry key (e.g. Lorelai) appears in pre-voice staging body."""
    try:
        from tools import kling_character_registry as reg

        reg_key = reg.resolve_registry_key(speaker) or (speaker or "").strip()
        display = _kling_display_name_for_speaker(speaker) or reg_key
    except Exception:
        return False
    if not reg_key or reg_key == display:
        return False
    text = prompt or ""
    m = re.search(r"\b(?:speaks|says)\b", text, re.I)
    head = text[: m.start()] if m else text
    return bool(re.search(rf"\b{re.escape(reg_key)}\b", head, re.I))


def _voice_line_display_name(speaker: str, element_name: str | None) -> str:
    """Must match element_list element_name so Kling binds Element voice (not generic TTS)."""
    canon = (speaker or "").strip()
    return (element_name or canon or "Character").strip()


def voice_block(speaker: str, spoken: str, emotion: str = "") -> str:
    """Return the canonical O3 voice line for a speaker (Element-bound delivery).

    KLING_O3_CANONICAL_PROMPT_SHAPE_V2: emotion tag BEFORE opening quote, never inside:
      Tessa speaks in a {delivery}: [curious] "Oh, hello. [pause] What's your name?"
    """
    canon = (speaker or "Character").strip()
    delivery = delivery_for_speaker(canon)
    element_name = canon
    try:
        from tools import kling_character_registry as reg

        element_name = reg.kling_element_display_name(canon) or reg.get_element_name(canon) or canon
    except Exception:
        pass
    voice_name = _voice_line_display_name(canon, element_name)
    spoken = strip_leading_emotion_tags_from_spoken(spoken)
    tag = format_emotion_tag(emotion)
    if delivery:
        if tag:
            return f'{voice_name} speaks in a {delivery}: {tag} "{spoken}"'
        return f'{voice_name} speaks in a {delivery}: "{spoken}"'
    if tag:
        return (
            f'{voice_name} speaks clearly at a natural pace, steady and not bubbly or hyper: '
            f'{tag} "{spoken}"'
        )
    return (
        f'{voice_name} speaks clearly at a natural pace, steady and not bubbly or hyper: "{spoken}"'
    )


def inject_locked_voice_line(
    prompt: str, speaker: str, spoken: str, emotion: str = "",
) -> str:
    """Replace legacy <<<voice_N>>> / author verb lines with Element locked delivery."""
    locked = voice_block(speaker, spoken, emotion=emotion)
    lines = prompt.splitlines()
    found = _find_voice_delivery_line(lines)
    if found is not None:
        idx, line = found
        low = line.lower()
        if voice_line_has_canonical_delivery(speaker, line) and "speaks in a" in low:
            # Keep canonical delivery wording only when the speaker prefix matches
            # Element display name (Laurel). Pronouns like "She speaks" must not
            # survive auto-heal — Kling binds voice from the name on this line.
            if not _voice_line_matches_kling_display_name(speaker, line):
                lines[idx] = locked
            else:
                colon = re.search(r":\s*", line)
                if colon:
                    head = line[: colon.end()].rstrip()
                    lines[idx] = f'{head} "{spoken}"'
                else:
                    lines[idx] = locked
        else:
            lines[idx] = locked
        return "\n".join(lines)
    out: list[str] = []
    replaced = False
    for line in lines:
        if not replaced and _is_voice_candidate_line(line):
            out.append(locked)
            replaced = True
        else:
            out.append(line)
    if replaced:
        return "\n".join(out)
    marker = "Children's illustrated"
    idx = prompt.find(marker)
    if idx < 0:
        return f"{prompt.rstrip()}\n\n{locked}\n"
    return f"{prompt[:idx].rstrip()}\n\n{locked}\n\n{prompt[idx:]}"


def upgrade_element_bound_voice_prompt(
    speaker: str,
    prompt: str,
    *,
    extract_spoken,
) -> tuple[str, str, bool]:
    """Auto-fix legacy <<<voice_N>>> and author-only voice lines before O3 submit."""
    text = (prompt or "").strip()
    if not text:
        return text, "", False
    try:
        from tools import kling_character_registry as reg

        if not reg.is_speaker_voice_ready(speaker):
            spoken = extract_spoken(text) or ""
            return text, spoken, False
    except Exception:
        spoken = extract_spoken(text) or ""
        return text, spoken, False

    spoken = extract_spoken(text) or ""
    lower = text.lower()
    needs_upgrade = (
        "<<<voice_" in lower
        or not re.search(r"\b(?:speaks|says)\b", text, re.I)
        or _prompt_needs_locked_voice_upgrade(speaker, text)
        or _prompt_needs_kling_name_normalization(speaker, text)
    )
    if not needs_upgrade or not spoken:
        normalized_only = normalize_kling_speaker_names_in_prompt(text, speaker)
        if normalized_only != text:
            return normalized_only, spoken, True
        return text, spoken, False

    upgraded = inject_locked_voice_line(text, speaker, spoken)
    upgraded = normalize_kling_speaker_names_in_prompt(upgraded, speaker)
    return upgraded, spoken, upgraded != text


def validate_element_bound_voice_prompt(speaker: str, prompt: str) -> list[str]:
    """Hard gates before O3 Pro + element_list — prompt box is law for delivery wording."""
    errors: list[str] = []
    try:
        from tools import kling_character_registry as reg

        if not reg.is_speaker_voice_ready(speaker):
            return errors
    except Exception:
        return errors
    text = (prompt or "").strip()
    lower = text.lower()
    if not text:
        errors.append("empty prompt")
        return errors
    display = _kling_display_name_for_speaker(speaker)
    if display and re.search(r"@Image1\s*\(\s*Character\s*\)", text, re.I):
        errors.append(
            f"prompt @Image1 header must use Element display name ({display}), not 'Character'"
        )
    elif display and re.search(r"@Image1\s*\(\s*Lorelai\s*\)", text, re.I):
        errors.append(
            f"prompt @Image1 header must use Element display name ({display}), not 'Lorelai'"
        )
    if "<<<voice_" in lower:
        errors.append("prompt contains <<<voice_N>>> (generic Kling TTS tags)")
    lines = text.splitlines()
    found = _find_voice_delivery_line(lines)
    voice_line = found[1] if found else ""
    if voice_line and voice_line_has_bracket_performance_tags(voice_line):
        errors.append(
            "prompt voice line uses bracket performance tags (use speaks in a {delivery})"
        )
    if not found or not _VOICE_LINE_VERB_RE.search(voice_line):
        if not voice_line and not any(
            voice_line_has_bracket_performance_tags(line) for line in lines
        ):
            errors.append("prompt missing voice line (speaks/says …)")
        elif not voice_line:
            errors.append("prompt missing voice line (speaks/says …)")
    delivery = delivery_for_speaker(speaker)
    if delivery and voice_line:
        voice_lower = voice_line.lower()
        if "speaks in a" not in voice_lower:
            errors.append("prompt voice line must use 'speaks in a {canonical delivery}'")
        elif delivery.lower() not in voice_lower:
            errors.append("prompt voice line missing canonical delivery lock")
        if display and not _voice_line_matches_kling_display_name(speaker, voice_line):
            if re.search(r"\bLorelai\s+(?:speaks|says)\b", voice_line, re.I):
                errors.append(
                    "prompt voice line must use 'Laurel' (Kling display name), not 'Lorelai'"
                )
            else:
                errors.append(
                    f"prompt voice line name must match Element display name ({display})"
                )
    if prompt_staging_leaks_registry_speaker_name(speaker, text):
        errors.append(
            f"prompt staging before voice line must use Kling display name ({display!r}), "
            f"not registry speaker name — misalignment causes generic/wrong Kling TTS"
        )
    try:
        from tools import beat_generator as bg

        if bg.prompt_voice_quote_has_performance_staging(text):
            errors.append(
                "prompt voice quote contains performance staging ([Faces camera…]); "
                "keep staging out of spoken quotes"
            )
        # Body staging is auto-rebuilt by normalize_o3_element_bound_prompt / prepare
        # before submit — do not block the operator on healable author prose here.
    except Exception:
        pass
    return errors


def validate_element_list_alignment(
    speaker: str,
    element_entry: dict | None,
    prompt: str,
) -> list[str]:
    """Fail closed when element_list payload would not bind Element voice on Kling."""
    errors: list[str] = []
    if not element_entry:
        return errors
    try:
        from tools import kling_character_registry as reg

        if not reg.is_speaker_voice_ready(speaker):
            return errors
    except Exception:
        return errors
    display = _kling_display_name_for_speaker(speaker)
    element_name = str(element_entry.get("element_name") or "").strip()
    if display and element_name and element_name != display:
        errors.append(
            f"element_list element_name must be {display!r}, not {element_name!r} "
            "(misalignment causes generic male Kling TTS)"
        )
    voice_id = str(element_entry.get("voice_id") or "").strip()
    try:
        from tools import kling_character_registry as reg

        bound = reg.get_bound_voice_id(speaker)
        if bound and voice_id and voice_id != bound:
            errors.append(
                f"element_list voice_id {voice_id} does not match registry {bound}"
            )
    except Exception:
        pass
    errors.extend(validate_element_bound_voice_prompt(speaker, prompt))
    return errors
