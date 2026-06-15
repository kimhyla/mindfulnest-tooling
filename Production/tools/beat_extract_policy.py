"""Cast, staging, and post-process policy for Claude Extract beats.

Kim decisions 2026-06-13: Lorelai (raccoon) + Arlo retired Luna/Chipper globally
for beat planning; inscription/runestone = still inserts (GPT stills).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_TOOLING_ROOT = Path(__file__).resolve().parent.parent
_GOLD_EVENT2 = (
    _TOOLING_ROOT / ".claude" / "skills" / "beat-extract-planner" / "EVENT2_INTRO_GOLD.md"
)

# Speaker aliases applied to all plan text fields (case-insensitive word boundaries).
_CAST_SPEAKER_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bGuide Bird\b", re.I), "Arlo"),
    (re.compile(r"\bAssistant Bird\b", re.I), "Arlo"),
    (re.compile(r"\bChipper\b", re.I), "Arlo"),
    (re.compile(r"\bPip\b", re.I), "Arlo"),
    (re.compile(r"\bLuna\b", re.I), "Lorelai"),
    (re.compile(r"\bOwl Peace Prize\b", re.I), "Lemur Peace Prize"),
    (re.compile(r"\bLuna the Owl\b", re.I), "Lorelai the raccoon"),
    (re.compile(r"\bowl archaeolog", re.I), "raccoon archaeolog"),
)

# Bird speakers keep wing vocabulary — human "hand" terms cause Kling hand hallucination.
_BIRD_KLING_SPEAKERS = frozenset(
    {"chipper", "guide bird", "assistant bird", "pip"},
)

# Gestural body-part terms → human animation vocabulary for Kling O3 (flipper/paw/talon).
# Non-human-only parts (tail, shell, beak, horns, ears, fur, wings on birds) are untouched.
_KLING_GESTURE_BODY_PART_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bflippers\b", re.I), "hands"),
    (re.compile(r"\bflipper\b", re.I), "hand"),
    (re.compile(r"\bpaws\b", re.I), "hands"),
    (re.compile(r"\bpaw\b", re.I), "hand"),
    (re.compile(r"\btalons\b", re.I), "hands"),
    (re.compile(r"\btalon\b", re.I), "hand"),
    (re.compile(r"\bwing-flutter\b", re.I), "hand flutter"),
    (re.compile(r"\bwing flutter\b", re.I), "hand flutter"),
)


def humanize_kling_body_parts(text: str, *, speaker: str = "") -> str:
    """Rewrite species-specific gesture terms to human body-part names for Kling staging.

    Kling animates micro-gestures more reliably with hand/arm language. @Image1 still
    locks species appearance. Bird characters (Chipper lineage) skip this — their
    prompts must not say "hand" (see CHIPPER_VIDEO_RELIABILITY_SPEC).
    """
    if not text or not str(text).strip():
        return text
    speaker_key = (speaker or "").strip().lower()
    if speaker_key in _BIRD_KLING_SPEAKERS:
        return text
    out = str(text)
    for pattern, repl in _KLING_GESTURE_BODY_PART_REPLACEMENTS:
        out = pattern.sub(repl, out)
    return out


def humanize_kling_body_parts_on_beat(beat: dict) -> bool:
    """Apply gesture humanization to sidecar beat text fields. Returns True if any field changed."""
    if not isinstance(beat, dict):
        return False
    speaker = str(beat.get("speaker") or "")
    changed = False
    for field in ("dialogue_text", "scene_notes", "kling_o3_prompt"):
        raw = beat.get(field)
        if raw in (None, ""):
            continue
        new_val = humanize_kling_body_parts(str(raw), speaker=speaker)
        if new_val != raw:
            beat[field] = new_val
            changed = True
    return changed


def humanize_kling_body_parts_on_plan_row(row: dict) -> bool:
    """Humanize gesture vocabulary on Beat Plan draft rows."""
    if not isinstance(row, dict):
        return False
    speaker = str(row.get("speaker") or "")
    changed = False
    for field in ("dialogue_text", "scene_notes", "skeleton_quote"):
        raw = row.get(field)
        if raw in (None, ""):
            continue
        new_val = humanize_kling_body_parts(str(raw), speaker=speaker)
        if new_val != raw:
            row[field] = new_val
            changed = True
    return changed


# Staging phrases to strip or flag on dialogue beats (Kling O3 solo medium-shot).
_BANNED_STAGING_RE = re.compile(
    r"\b("
    r"camera zoom|camera cut|cuts to|cut to|pan(?:s|ned)?|dolly|tracking shot|"
    r"wide establishing|pull(?:s|ed)? back|enters frame|walks across|crosses the room|"
    r"second character|companion bird|magnifying glass|cartwheel|mid-?air|spinning in"
    r")\b",
    re.I,
)

_STILL_INSERT_RE = re.compile(
    r"\b("
    r"inscription|runestone.*lit|mindfulnest.*lit|close-?up of.*stone|"
    r"carved text|on-?screen text|still insert|gpt still|pre-?made still"
    r")\b",
    re.I,
)

_SPEAKER_CANON = {
    "luna": "Lorelai",
    "lorelai": "Lorelai",
    "laurel": "Lorelai",
    "chipper": "Arlo",
    "guide bird": "Arlo",
    "pip": "Arlo",
    "assistant bird": "Arlo",
    "stage direction": "[Stage Direction]",
    "[stage direction]": "[Stage Direction]",
}


def apply_cast_text(text: str) -> str:
    if not text:
        return text
    out = text
    for pat, repl in _CAST_SPEAKER_REPLACEMENTS:
        out = pat.sub(repl, out)
    return out


def canon_plan_speaker(raw: str) -> str:
    key = (raw or "").strip()
    if not key:
        return "Character"
    return _SPEAKER_CANON.get(key.lower(), key)


_SPEAKER_WEAK_SUFFIX_RE = re.compile(r"\s+(?:says|speaks)\s*$", re.I)


def normalize_dialogue_speaker(raw: str) -> str:
    """Strip trailing ``says``/``speaks`` from parsed speaker labels (``Lorelai says:``)."""
    key = (raw or "").strip()
    if not key:
        return "Character"
    key = _SPEAKER_WEAK_SUFFIX_RE.sub("", key).strip()
    return canon_plan_speaker(key)


_DIALOGUE_SPEAKER_RE = re.compile(
    r"([A-Za-z][A-Za-z\s'-]*?)\s*(?:\[\[[^\]]+\]\]|\[[^\]]+\])*\s*:\s*",
    re.MULTILINE,
)


def extract_spoken_from_dialogue(dialogue: str) -> tuple[str | None, str]:
    """Parse ``scene… Speaker [[emo]]: "line" [staging]`` → speaker + spoken line only."""
    text = apply_cast_text((dialogue or "").strip())
    if not text:
        return None, ""

    quoted = list(re.finditer(r'"([^"]*)"', text))
    if quoted:
        spoken = quoted[-1].group(1).strip()
        prefix = text[: quoted[-1].start()]
        sm = _DIALOGUE_SPEAKER_RE.search(prefix.strip())
        speaker = normalize_dialogue_speaker(sm.group(1).strip()) if sm else None
        if spoken:
            return speaker, spoken

    spoken_matches = list(_DIALOGUE_SPEAKER_RE.finditer(text))
    if spoken_matches:
        m = spoken_matches[-1]
        speaker = normalize_dialogue_speaker(m.group(1).strip())
        tail = text[m.end() :].strip()
        stage_tail = re.search(r"\s+\[([^\]]+)\]\s*$", tail)
        if stage_tail:
            tail = tail[: stage_tail.start()].strip()
        if tail.startswith('"') and tail.endswith('"'):
            tail = tail[1:-1].strip()
        elif tail.startswith("'") and tail.endswith("'"):
            tail = tail[1:-1].strip()
        return speaker, tail

    return None, text


def infer_speaker_from_dialogue(dialogue: str) -> str | None:
    speaker, _spoken = extract_spoken_from_dialogue(dialogue)
    if speaker and speaker not in ("Character", "[Stage Direction]"):
        return speaker
    return None


_CORRUPT_CHARACTER_PREFIX_RE = re.compile(
    r"^Character\s+(?:\[\[[^\]]+\]\]|\[[^\]]+\]):\s*",
    re.I,
)


def _strip_bracket_emotion(emotion: str) -> str:
    emo = (emotion or "neutral").strip() or "neutral"
    if emo.startswith("[") and emo.endswith("]"):
        return emo[1:-1].strip() or "neutral"
    return emo


def repair_corrupted_plan_dialogue(dialogue: str, speaker: str) -> tuple[str, str]:
    """Heal approve-round-trip garbage like ``Character [[emo]]: Name [[emo]]: line``."""
    text = apply_cast_text((dialogue or "").strip())
    if not text:
        return speaker, text
    inferred, spoken = extract_spoken_from_dialogue(text)
    sp = canon_plan_speaker(speaker)
    if sp in ("Character", "") and inferred:
        sp = inferred
    if _CORRUPT_CHARACTER_PREFIX_RE.match(text) or "[[" in text:
        if spoken:
            return sp, spoken
    if inferred and spoken and len(spoken) < len(text) * 0.85:
        return sp, spoken
    return sp, text


def load_gold_example(arc_number: int, event_id: str, phase: str) -> str:
    if str(arc_number) == "1" and str(event_id) == "2" and str(phase) == "pre":
        try:
            if _GOLD_EVENT2.is_file():
                return _GOLD_EVENT2.read_text(encoding="utf-8")
        except OSError:
            pass
    return ""


def _simplify_staging(scene_notes: str, *, beat_type: str) -> tuple[str, list[str]]:
    """Return simplified scene_notes + lint warnings."""
    warnings: list[str] = []
    notes = (scene_notes or "").strip()
    if not notes:
        return notes, warnings
    if beat_type in ("stage_still", "stage_direction"):
        return apply_cast_text(notes), warnings
    if _BANNED_STAGING_RE.search(notes):
        warnings.append(f"banned staging simplified: {notes[:80]}...")
        # Keep emotional/face hints; drop obvious camera/locomotion clauses.
        parts = re.split(r"[.;]", notes)
        kept = []
        for p in parts:
            p = p.strip()
            if not p:
                continue
            if _BANNED_STAGING_RE.search(p):
                continue
            kept.append(p)
        notes = "; ".join(kept) if kept else "expression shifts subtly"
    return apply_cast_text(notes), warnings


def classify_beat_type(row: dict) -> str:
    bt = str(row.get("beat_type") or "dialogue").strip().lower()
    speaker = str(row.get("speaker") or "").strip().lower()
    scene = str(row.get("scene_notes") or "")
    dialogue = str(row.get("dialogue_text") or "").strip()
    combined = f"{scene} {dialogue}".lower()

    if bt in ("stage_still", "stage_direction", "dialogue"):
        if bt == "stage_direction" and _STILL_INSERT_RE.search(combined):
            return "stage_still"
        if bt == "stage_still":
            return "stage_still"
        if speaker in ("[stage direction]", "stage direction", "scene"):
            if _STILL_INSERT_RE.search(combined) or not dialogue:
                return "stage_still"
            return "stage_direction"
    if _STILL_INSERT_RE.search(combined) and not dialogue:
        return "stage_still"
    if speaker in ("[stage direction]", "stage direction"):
        return "stage_direction"
    return "dialogue"


def normalize_plan_row(row: dict, *, beat_index: int) -> tuple[dict, list[str]]:
    warnings: list[str] = []
    beat_type = classify_beat_type(row)
    speaker_raw = apply_cast_text(str(row.get("speaker") or "Character").strip())
    speaker = canon_plan_speaker(speaker_raw)
    if speaker == "Character":
        inferred = infer_speaker_from_dialogue(str(row.get("dialogue_text") or ""))
        if inferred:
            speaker = inferred
    if beat_type in ("stage_still", "stage_direction"):
        speaker = "[Stage Direction]"

    dialogue = apply_cast_text(str(row.get("dialogue_text") or "").strip())
    emotion = _strip_bracket_emotion(apply_cast_text(str(row.get("emotion") or "neutral").strip()) or "neutral")
    scene_notes, w = _simplify_staging(str(row.get("scene_notes") or ""), beat_type=beat_type)
    warnings.extend(w)

    if beat_type == "dialogue":
        speaker, dialogue = repair_corrupted_plan_dialogue(dialogue, speaker)
        if speaker == "Character":
            inferred = infer_speaker_from_dialogue(dialogue)
            if inferred:
                speaker = inferred

    if beat_type == "stage_still" and not scene_notes and dialogue:
        scene_notes, dialogue = dialogue, ""

    invented = bool(row.get("invented")) or dialogue.startswith("[CLAUDE INVENTED]")
    if "this child" in dialogue.lower():
        dialogue = re.sub(r"\bthis child\b", "{childName}", dialogue, flags=re.I)
        warnings.append("replaced 'this child' with {childName}")

    dialogue = humanize_kling_body_parts(dialogue, speaker=speaker)
    scene_notes = humanize_kling_body_parts(scene_notes, speaker=speaker)

    out = {
        "beat_index": beat_index,
        "beat_type": beat_type,
        "speaker": speaker,
        "dialogue_text": dialogue,
        "emotion": emotion,
        "scene_notes": scene_notes[:500],
        "skeleton_quote": apply_cast_text(str(row.get("skeleton_quote") or "").strip()),
        "invented": invented,
    }
    return out, warnings


def postprocess_beats_plan(beats_plan: list[dict]) -> tuple[list[dict], list[str]]:
    out: list[dict] = []
    warnings: list[str] = []
    for i, row in enumerate(beats_plan or [], start=1):
        if not isinstance(row, dict):
            continue
        normalized, row_warnings = normalize_plan_row(row, beat_index=i)
        out.append(normalized)
        warnings.extend(row_warnings)
    return out, warnings


def postprocess_plan_result(plan: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    story = apply_cast_text(str(plan.get("story_summary") or "").strip())
    beats, warnings = postprocess_beats_plan(plan.get("beats_plan") or [])
    return {
        **plan,
        "story_summary": story,
        "beats_plan": beats,
        "staging_warnings": warnings,
        "cast_policy": "Lorelai+Arlo (Luna/Chipper retired)",
        "gold_reference_used": bool(load_gold_example(
            meta.get("arc_number", 1), meta.get("event_id", ""), meta.get("phase", "pre"),
        )),
    }


def build_still_insert_prompt(beat: dict) -> str:
    desc = (beat.get("scene_notes") or beat.get("dialogue_text") or "Still insert").strip()
    return (
        "STILL INSERT — use pre-made GPT still from library; do not submit to Kling O3 Element.\n"
        f"{desc}\n\n"
        "Assign the still image in Beat Gen. No @Image1 character clip for this beat."
    )


_IMAGE1_SPEAKER_RE = re.compile(r"@Image1(?:\s+<<<voice_\d+>>>)?\s*\([^)]+\)", re.I)
_VOICE_LINE_RE = re.compile(
    r"((?:@Image1(?:\s+<<<voice_\d+>>>)?|Arlo|Lorelai|Tessa|Chipper)\s+(?:speaks|says)[^:]*:\s*)"
    r'("([^"]*)")',
    re.I | re.S,
)


def _format_emotion_tag(emotion: str) -> str:
    try:
        import kling_o3_prompt as o3p
    except ImportError:
        from tools import kling_o3_prompt as o3p  # type: ignore

    return o3p.format_emotion_tag(emotion)


def _clean_scene_notes(scene_notes: str) -> str:
    try:
        import kling_o3_prompt as o3p
    except ImportError:
        from tools import kling_o3_prompt as o3p  # type: ignore

    return o3p.strip_rooted_in_place(apply_cast_text((scene_notes or "").strip()))


def _kling_staging_speaker_label(speaker: str) -> str:
    """Kling-facing name for staging (Loral for Lorelai) — must match voice line + element_list."""
    try:
        from tools import kling_character_registry as reg

        return reg.kling_element_display_name(speaker) or (speaker or "").strip()
    except Exception:
        try:
            from tools import kling_o3_prompt as o3p

            return o3p._kling_display_name_for_speaker(speaker) or (speaker or "").strip()
        except Exception:
            return (speaker or "").strip()


def screen_direction_paragraph(speaker: str, scene_notes: str) -> str:
    """One sentence of on-screen staging — separate paragraph before the voice line."""
    scene = _clean_scene_notes(scene_notes)
    if not scene:
        return ""
    label = _kling_staging_speaker_label(speaker)
    if re.match(rf"^{re.escape(label)}\b", scene, re.I):
        line = scene
    elif speaker and re.match(rf"^{re.escape(speaker)}\b", scene, re.I):
        line = re.sub(rf"^{re.escape(speaker)}\b", label, scene, count=1, flags=re.I)
    else:
        line = f"{label} {scene.lstrip(',').strip()}"
    return line.rstrip(".") + "."


_O3_CLOSEUP_SCENE_RE = re.compile(
    r"\b(close[- ]?up|head and torso|head and shoulders|head and chest|bust(?:\s+shot)?|"
    r"waist[- ]?up|upper\s+body)\b",
    re.I,
)

_O3_DEFAULT_MEDIUM_CAMERA = (
    "Camera: static locked shot, no zoom, no dolly, no pan, no camera movement, "
    "stable eye-level medium shot."
)

_O3_CLOSEUP_CAMERA = (
    "Camera: static locked shot, stable eye-level close-up on @Image1 — "
    "head and torso fill the frame."
)


def _scene_notes_imply_closeup(scene: str) -> bool:
    return bool(_O3_CLOSEUP_SCENE_RE.search(scene))


def o3_element_framing_paragraph(speaker: str, scene_notes: str) -> str:
    """Element-bound O3 camera framing — close-ups use Camera line only (no speaker prefix)."""
    scene = _clean_scene_notes(scene_notes)
    if _scene_notes_imply_closeup(scene):
        return _O3_CLOSEUP_CAMERA
    if scene and re.match(r"^camera\s*:", scene, re.I):
        return scene.rstrip(".") + "."
    return _O3_DEFAULT_MEDIUM_CAMERA


def _staging_paragraph(speaker: str, scene_notes: str, emotion: str) -> str:
    """Turn plan scene_notes into screen-direction paragraph (no 'rooted in place')."""
    return screen_direction_paragraph(speaker, scene_notes)


def _inject_emotion_into_spoken(spoken: str, emotion: str) -> str:
    """Legacy helper — emotion belongs OUTSIDE quotes on the voice line, not here."""
    try:
        import kling_o3_prompt as o3p
    except ImportError:
        from tools import kling_o3_prompt as o3p  # type: ignore

    return o3p.strip_leading_emotion_tags_from_spoken((spoken or "").strip())


def _prompt_contains_staging(prompt: str, scene_notes: str) -> bool:
    scene = (scene_notes or "").strip().lower()
    if not scene:
        return True
    probe = scene[:24].lower()
    return probe in (prompt or "").lower()


def _prompt_spoken_matches_dialogue(prompt: str, dialogue: str) -> bool:
    dlg = re.sub(r"\s+", " ", (dialogue or "").strip().lower())
    if not dlg:
        return True
    m = _VOICE_LINE_RE.search(prompt or "")
    if not m:
        return dlg[:12] in (prompt or "").lower()
    spoken = re.sub(r"\s+", " ", m.group(2).strip().lower())
    spoken = re.sub(r"^\[[^\]]+\]\s*", "", spoken)
    return dlg[:16] in spoken or spoken[:16] in dlg


def postprocess_kling_author_row(plan_row: dict, prompt: str) -> dict[str, str]:
    """Merge approved plan emotion/staging into Phase B Kling prompt (deterministic)."""
    speaker = canon_plan_speaker(str(plan_row.get("speaker") or "Character").strip())
    beat_type = str(plan_row.get("beat_type") or "dialogue").lower()
    dialogue = apply_cast_text(str(plan_row.get("dialogue_text") or "").strip())
    emotion = apply_cast_text(str(plan_row.get("emotion") or "neutral").strip()) or "neutral"
    scene_notes = apply_cast_text(str(plan_row.get("scene_notes") or "").strip())

    if beat_type == "stage_still":
        return {
            "kling_o3_prompt": build_still_insert_prompt(plan_row),
            "emotion": emotion,
            "scene_notes": scene_notes[:500],
        }

    out = apply_cast_text((prompt or "").strip())
    if not out and beat_type == "stage_direction":
        out = (
            f"@Image1 ({speaker}) Scene beat. Scene from @Image2.\n\n"
            f"Camera: static locked shot, no zoom, no dolly, no pan, "
            f"no camera movement, stable eye-level medium shot.\n\n"
            f"{dialogue or scene_notes or 'Ambient storybook moment.'}"
        )
    if not out:
        return {
            "kling_o3_prompt": "",
            "emotion": emotion,
            "scene_notes": scene_notes[:500],
        }

    out = _IMAGE1_SPEAKER_RE.sub(f"@Image1 ({speaker})", out, count=1)
    out = re.sub(
        rf"(@Image1 \({re.escape(speaker)}\))\s+\w+\s+—",
        rf"\1 {speaker} —",
        out,
        count=1,
    )
    staging = _staging_paragraph(speaker, scene_notes, emotion)
    if staging and not _prompt_contains_staging(out, scene_notes):
        vm = _VOICE_LINE_RE.search(out)
        if vm:
            out = out[: vm.start()].rstrip() + f"\n\n{staging}\n\n" + out[vm.start() :].lstrip()
        else:
            out = out.rstrip() + f"\n\n{staging}\n"

    vm = _VOICE_LINE_RE.search(out)
    _inferred_speaker, spoken_only = extract_spoken_from_dialogue(dialogue)
    if speaker == "Character" and _inferred_speaker:
        speaker = _inferred_speaker
        out = _IMAGE1_SPEAKER_RE.sub(f"@Image1 ({speaker})", out, count=1)
        out = re.sub(
            rf"(@Image1 \({re.escape(speaker)}\))\s+\w+\s+—",
            rf"\1 {speaker} —",
            out,
            count=1,
        )
    spoken_for_voice = spoken_only or dialogue
    if vm and spoken_for_voice and not _prompt_spoken_matches_dialogue(out, spoken_for_voice):
        cleaned = _inject_emotion_into_spoken(
            _kling_o3_normalize_spoken(spoken_for_voice), emotion,
        )
        out = out[: vm.start(2)] + cleaned + out[vm.end(2) :]
    elif vm:
        inner = vm.group(2)
        cleaned = _inject_emotion_into_spoken(inner, emotion)
        if cleaned != inner:
            out = out[: vm.start(2)] + cleaned + out[vm.end(2) :]

    out = humanize_kling_body_parts(out, speaker=speaker)
    scene_notes = humanize_kling_body_parts(scene_notes, speaker=speaker)

    out = normalize_kling_o3_prompt_event1_quality(
        out.strip(),
        speaker=speaker,
        dialogue=dialogue,
        emotion=emotion,
        scene_notes=scene_notes,
    )

    return {
        "kling_o3_prompt": out.strip(),
        "emotion": emotion,
        "scene_notes": scene_notes[:500],
    }


def postprocess_kling_author_results(
    beats_plan: list[dict],
    prompt_by_index: dict[int, str],
) -> tuple[dict[int, str], list[dict]]:
    """Apply cast/staging/emotion enrichment for every plan row after Claude author."""
    enriched_prompts: dict[int, str] = dict(prompt_by_index)
    enriched_plan: list[dict] = []
    for row in beats_plan:
        idx = int(row.get("beat_index") or 0)
        if not idx:
            continue
        merged = postprocess_kling_author_row(row, prompt_by_index.get(idx, ""))
        if merged.get("kling_o3_prompt"):
            enriched_prompts[idx] = merged["kling_o3_prompt"]
        enriched_plan.append({**row, **merged})
    return enriched_prompts, enriched_plan


def _kling_o3_normalize_spoken(spoken: str) -> str:
    """Light dialogue normalize — full implementation lives in beat_generator."""
    s = (spoken or "").strip()
    s = re.sub(r"\s+", " ", re.sub(r"\([^)]*\)", " ", s)).strip()
    s = re.sub(r"\.{2,}", ".", s)
    s = re.sub(r"…+", ".", s)
    return s


def kling_staging_policy_block() -> str:
    return (
        "KLING O3 STAGING (mandatory for scene_notes on dialogue beats):\n"
        "- Static medium shot; micro-expression only (eyes widen, smile, hand flutter, shrug).\n"
        "- Gesture vocabulary: use human body-part names (hand, arm) — not flipper/paw/talon.\n"
        "- Keep non-human-only parts as-is (tail, shell, horns, beak on birds, etc.).\n"
        "- NO: camera zoom/cut/pan, walks across room, enters frame, second character on screen.\n"
        "- One speaker per beat; back-and-forth = separate beats.\n"
        "- beat_type stage_still for inscription/runestone/MindfulNest close-ups (GPT stills).\n"
        "- Preserve {childName} placeholders; never 'the child'.\n"
        "CAST (mandatory): Lorelai (raccoon), Arlo (guide), Tessa. Never Luna or Chipper.\n"
        "- Raccoon Peace Prize / Lemur Peace Prize is intentional humor.\n"
        "- Compress skeleton gags (magnifying glass, cartwheel, hover spin) unless essential.\n"
        "- Arlo explains Magic Hands via dialogue; module spell name optional on handoff.\n"
        "KLING O3 CANONICAL PROMPT SHAPE V2 (tooling enforces on approve + submit):\n"
        "1) @Image1 ({Speaker}). Scene from @Image2. — NO arc/event/beat labels in header.\n"
        "2) Screen direction paragraph from scene_notes (one sentence, e.g. Tessa stands near the MindfulNest).\n"
        "3) Voice line: {Name} speaks in a {delivery}: [emotion] \"dialogue with [pause] inside quotes\".\n"
        "   Emotion tags OUTSIDE quotes (Kling speaks bracket words aloud if inside quotes).\n"
        "4) Children's illustrated fantasy storybook style line (tooling default).\n"
        "5) Footer safety locks — tooling appends.\n"
        "NEVER describe species anatomy in prose. NO 'rooted in place' boilerplate.\n"
    )


# Claude-author drift: species taxonomy fights @Image1/Element (Event 2 Tessa regression).
_SPECIES_TAXONOMY_SENTENCE_RE = re.compile(
    r"\.\s*(?:Tessa|Lorelai|Arlo|Chipper)\s+is\s+a\s+[^.]+\.\s*",
    re.I,
)
_EXTRA_WAIST_FRAMING_RE = re.compile(
    r"\s*(?:Tessa|Lorelai|Arlo|Chipper)\s+shown from (?:the )?waist up[^.\n]*\.\s*",
    re.I,
)
_WEAK_SPEAKS_COLON_RE = re.compile(
    r"\b(Tessa|Lorelai|Laurel|Arlo|Chipper)\s+speaks:\s*",
    re.I,
)
_WEAK_SAYS_COLON_RE = re.compile(
    r"\b(Tessa|Lorelai|Laurel|Arlo|Chipper)\s+says:\s*",
    re.I,
)


def _event1_voice_line_upgrade(speaker: str, delivery: str) -> str:
    """Canonical weak-line upgrade prefix — must match element_name for Kling bind."""
    canon = (speaker or "").strip()
    try:
        from tools import kling_character_registry as reg

        display = reg.kling_element_display_name(speaker)
        if display:
            return f"{display} speaks in a {delivery}: "
    except Exception:
        pass
    return f"{canon} speaks in a {delivery}: "


def event1_kling_voice_delivery(speaker: str) -> str | None:
    """Event-1 delivery adjective phrase for canonical voice lines."""
    import beat_generator as bg

    canon = (speaker or "").strip()
    if canon == "Tessa":
        return bg.KLING_O3_TESSA_VOICE_DELIVERY
    if canon == "Chipper":
        return bg.KLING_O3_CHIPPER_VOICE_DELIVERY
    if canon in ("Lorelai", "Laurel", "Loral"):
        return bg.KLING_O3_LORELAI_VOICE_DELIVERY
    if canon == "Arlo":
        from tools import kling_o3_prompt as o3p

        return o3p.KLING_O3_ARLO_VOICE_DELIVERY
    return None


def normalize_kling_o3_prompt_event1_quality(
    prompt: str,
    *,
    speaker: str = "",
    dialogue: str = "",
    emotion: str = "",
    scene_notes: str = "",
) -> str:
    """Strip author species taxonomy; enforce Event-1 @Image1-trust prompt shape."""
    out = (prompt or "").strip()
    if not out:
        return out

    while _SPECIES_TAXONOMY_SENTENCE_RE.search(out):
        out = _SPECIES_TAXONOMY_SENTENCE_RE.sub(". ", out, count=1)
    out = re.sub(r"\.\s+\.", ".", out)
    out = _EXTRA_WAIST_FRAMING_RE.sub("\n\n", out)

    delivery = event1_kling_voice_delivery(speaker)
    if delivery:
        upgrade = _event1_voice_line_upgrade(speaker, delivery)
        if _WEAK_SPEAKS_COLON_RE.search(out):
            out = _WEAK_SPEAKS_COLON_RE.sub(upgrade, out, count=1)
        if _WEAK_SAYS_COLON_RE.search(out):
            out = _WEAK_SAYS_COLON_RE.sub(upgrade, out, count=1)

    import beat_generator as bg
    from tools import kling_o3_prompt as o3p

    out = bg.normalize_kling_o3_identity_footer(out)
    out = o3p.normalize_kling_speaker_names_in_prompt(out, speaker)

    beat_stub = {
        "speaker": speaker,
        "dialogue_text": dialogue,
        "emotion": emotion,
        "scene_notes": scene_notes,
        "kling_o3_prompt": out,
    }
    return bg.prepare_kling_o3_prompt_for_submit(beat_stub, out)


def heal_beat_kling_o3_prompt_event1_shape(beat: dict) -> bool:
    """Migrate-sidecar heal: rewrite stored prompts to Event-1 quality shape."""
    if not isinstance(beat, dict):
        return False
    import beat_generator as bg

    if bg.beat_is_still_insert(beat) or bg.beat_is_canonical_mirror_protected(beat):
        return False
    prompt = (beat.get("kling_o3_prompt") or "").strip()
    if not prompt or len(prompt) < 40:
        return False
    new = normalize_kling_o3_prompt_event1_quality(
        prompt,
        speaker=str(beat.get("speaker") or ""),
        dialogue=str(beat.get("dialogue_text") or ""),
        emotion=str(beat.get("emotion") or ""),
        scene_notes=str(beat.get("scene_notes") or ""),
    )
    if new != prompt:
        beat["kling_o3_prompt"] = new
        return True
    return False
