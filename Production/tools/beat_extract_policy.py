"""Cast, staging, and post-process policy for Claude Extract beats.

Kim decisions 2026-06-13: Lorelai (lemur) + Arlo retired Luna/Chipper globally
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
    (re.compile(r"\bLuna the Owl\b", re.I), "Lorelai the lemur"),
    (re.compile(r"\bowl archaeolog", re.I), "lemur archaeolog"),
)

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
        notes = "; ".join(kept) if kept else "expression shift, rooted in place"
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
    if beat_type in ("stage_still", "stage_direction"):
        speaker = "[Stage Direction]"

    dialogue = apply_cast_text(str(row.get("dialogue_text") or "").strip())
    emotion = apply_cast_text(str(row.get("emotion") or "neutral").strip()) or "neutral"
    scene_notes, w = _simplify_staging(str(row.get("scene_notes") or ""), beat_type=beat_type)
    warnings.extend(w)

    if beat_type == "stage_still" and not scene_notes and dialogue:
        scene_notes, dialogue = dialogue, ""

    invented = bool(row.get("invented")) or dialogue.startswith("[CLAUDE INVENTED]")
    if "this child" in dialogue.lower():
        dialogue = re.sub(r"\bthis child\b", "{childName}", dialogue, flags=re.I)
        warnings.append("replaced 'this child' with {childName}")

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


def kling_staging_policy_block() -> str:
    return (
        "KLING O3 STAGING (mandatory for scene_notes on dialogue beats):\n"
        "- Static medium shot; micro-expression only (eyes widen, smile, wing-flutter, shrug).\n"
        "- NO: camera zoom/cut/pan, walks across room, enters frame, second character on screen.\n"
        "- One speaker per beat; back-and-forth = separate beats.\n"
        "- beat_type stage_still for inscription/runestone/MindfulNest close-ups (GPT stills).\n"
        "- Preserve {childName} placeholders; never 'the child'.\n"
        "CAST (mandatory): Lorelai (lemur), Arlo (guide), Tessa. Never Luna or Chipper.\n"
        "- Lemur Peace Prize is intentional humor.\n"
        "- Compress skeleton gags (magnifying glass, cartwheel, hover spin) unless essential.\n"
        "- Arlo explains Magic Hands via dialogue; module spell name optional on handoff.\n"
    )
