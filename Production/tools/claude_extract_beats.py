"""Claude-powered Extract beats — plan (Phase A) and Kling prompt author (Phase B).

Per Production/docs/TECH_SPEC_CLAUDE_SUGGEST_BEATS_v1.md
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

CLAUDE_SONNET_MODEL = "claude-sonnet-4-6"
PLAN_TIMEOUT_S = 90
AUTHOR_TIMEOUT_S = 120

_TOOLING_ROOT = Path(__file__).resolve().parent.parent
_PLANNER_SKILL = _TOOLING_ROOT / ".claude" / "skills" / "beat-extract-planner" / "SKILL.md"
_KLING_AUTHOR_SKILL = _TOOLING_ROOT / ".claude" / "skills" / "beat-kling-prompt-author" / "SKILL.md"


def _parse_claude_json(raw: str) -> dict | list:
    text = (raw or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return json.loads(text)


def _anthropic_text(resp: dict) -> str:
    parts: list[str] = []
    for block in resp.get("content") or []:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text") or "")
    return "".join(parts)


def _call_anthropic(api_key: str, system: str, user: str, *, max_tokens: int, timeout: int) -> tuple[dict, int]:
    from server_handlers.phases import _call_anthropic_urllib

    req_body = {
        "model": CLAUDE_SONNET_MODEL,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    resp, elapsed_ms = _call_anthropic_urllib(api_key, req_body, timeout=timeout)
    return resp, elapsed_ms


def _load_skill(path: Path, fallback: str) -> str:
    try:
        if path.is_file():
            return path.read_text(encoding="utf-8")
    except OSError:
        pass
    return fallback


def _few_shot_kling_examples() -> str:
    """Pull 2–3 Event 1 intro kling_o3_prompt strings from live sidecar when available."""
    try:
        import beat_generator as bg

        sidecar = bg.read_sidecar()
        seg = bg.get_seg_entry(sidecar, 1, "1", "pre")
        beats = seg.get("beats") or []
        examples: list[str] = []
        for beat in beats:
            prompt = (beat.get("kling_o3_prompt") or "").strip()
            if len(prompt) < 120:
                continue
            if beat.get("intro_beat_role"):
                continue
            examples.append(
                f"--- beat {beat.get('beat_id')} ({beat.get('speaker')}) ---\n{prompt[:1800]}"
            )
            if len(examples) >= 3:
                break
        if examples:
            return "\n\n".join(examples)
    except Exception:
        pass
    return (
        "@Image1 (Arlo) Arlo — Discovery. Scene from @Image2.\n\n"
        "Camera: static locked shot, no zoom, no dolly, no pan, no camera movement, "
        "stable eye-level medium shot.\n\n"
        "Arlo speaks in a warm natural conversational pace: \"Hello.... Are you OK...?\"\n\n"
        "Children's illustrated fantasy storybook style, warm golden forest light."
    )


def resolve_anthropic_api_key() -> str | None:
    try:
        import sys
        from pathlib import Path as _P

        repo_root = _P(__file__).resolve().parent.parent.parent
        sys.path.insert(0, str(repo_root / "lib"))
        from credential_store import get_secret_optional  # type: ignore

        key = get_secret_optional("ANTHROPIC_API_KEY")
        if key:
            return key
    except Exception:
        pass
    return os.environ.get("ANTHROPIC_API_KEY")


def claude_plan_beats(
    section_text: str,
    *,
    meta: dict[str, Any],
    api_key: str,
) -> dict[str, Any]:
    """Phase A — story summary + beats_plan[] (no kling_o3_prompt)."""
    skill = _load_skill(
        _PLANNER_SKILL,
        "You are a MindfulNest beat planner. Return JSON with story_summary and beats_plan.",
    )
    phase = meta.get("phase") or "pre"
    soft_target = "6–15" if phase in ("pre", "full") else "3–8"
    system = (
        f"{skill}\n\n"
        "Return ONLY valid JSON — no markdown fences, no preamble.\n"
        "Schema:\n"
        "{\n"
        '  "story_summary": "<plot + cute/funny + must-haves>",\n'
        '  "beats_plan": [\n'
        "    {\n"
        '      "beat_index": 1,\n'
        '      "beat_type": "dialogue" | "stage_direction",\n'
        '      "speaker": "Character name or [Stage Direction]",\n'
        '      "dialogue_text": "verbatim skeleton quote or [CLAUDE INVENTED] bridge",\n'
        '      "emotion": "short delivery phrase",\n'
        '      "scene_notes": "staging / camera / action notes for Phase B",\n'
        '      "skeleton_quote": "optional verbatim excerpt",\n'
        '      "invented": false\n'
        "    }\n"
        "  ]\n"
        "}\n"
    )
    user = (
        f"Segment: arc {meta.get('arc_number')} event {meta.get('event_id')} phase {phase}\n"
        f"Event name: {meta.get('event_name', '')}\n"
        f"Module: {meta.get('m_number') or 'n/a'}\n"
        f"Soft beat target: {soft_target} beats (minimum necessary — compress/reorder freely).\n\n"
        f"Sliced skeleton section ({meta.get('section_label', 'unknown')}):\n"
        f"---\n{section_text}\n---\n"
    )
    resp, elapsed_ms = _call_anthropic(
        api_key, system, user, max_tokens=4096, timeout=PLAN_TIMEOUT_S,
    )
    parsed = _parse_claude_json(_anthropic_text(resp))
    if not isinstance(parsed, dict):
        raise ValueError("Claude plan response must be a JSON object")
    beats_plan = parsed.get("beats_plan") or []
    if not isinstance(beats_plan, list) or not beats_plan:
        raise ValueError("beats_plan must be a non-empty array")
    return {
        "story_summary": str(parsed.get("story_summary") or "").strip(),
        "beats_plan": beats_plan,
        "model_used": CLAUDE_SONNET_MODEL,
        "generation_time_ms": elapsed_ms,
    }


def claude_author_kling_prompts(
    story_summary: str,
    beats_plan: list[dict],
    *,
    meta: dict[str, Any],
    api_key: str,
) -> dict[str, Any]:
    """Phase B — approved plan → kling_o3_prompt per beat."""
    import beat_generator as bg

    skill = _load_skill(
        _KLING_AUTHOR_SKILL,
        "You author Event-1-quality Kling O3 prompts for MindfulNest beats.",
    )
    few_shot = _few_shot_kling_examples()
    system = (
        f"{skill}\n\n"
        f"Reference camera lock (include verbatim in every prompt):\n{bg.KLING_O3_CAMERA_LOCK}\n\n"
        "Few-shot approved prompts:\n"
        f"{few_shot}\n\n"
        "Return ONLY valid JSON:\n"
        "{\n"
        '  "beats": [\n'
        "    {\n"
        '      "beat_index": 1,\n'
        '      "kling_o3_prompt": "<full multi-line prompt>"\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "Every beat_index from the plan must appear exactly once."
    )
    plan_json = json.dumps(
        {"story_summary": story_summary, "beats_plan": beats_plan},
        ensure_ascii=False,
        indent=2,
    )
    user = (
        f"Segment: arc {meta.get('arc_number')} event {meta.get('event_id')} "
        f"phase {meta.get('phase')}\n\n"
        f"Approved beat plan:\n{plan_json}\n"
    )
    resp, elapsed_ms = _call_anthropic(
        api_key, system, user, max_tokens=8192, timeout=AUTHOR_TIMEOUT_S,
    )
    parsed = _parse_claude_json(_anthropic_text(resp))
    if not isinstance(parsed, dict):
        raise ValueError("Claude author response must be a JSON object")
    beats_out = parsed.get("beats") or []
    if not isinstance(beats_out, list) or not beats_out:
        raise ValueError("beats array required in author response")
    prompt_by_index: dict[int, str] = {}
    for row in beats_out:
        if not isinstance(row, dict):
            continue
        idx = int(row.get("beat_index") or 0)
        prompt = str(row.get("kling_o3_prompt") or "").strip()
        if idx and prompt:
            prompt_by_index[idx] = prompt
    if len(prompt_by_index) < len(beats_plan):
        raise ValueError(
            f"Claude returned {len(prompt_by_index)} prompts for {len(beats_plan)} beats"
        )
    return {
        "prompt_by_index": prompt_by_index,
        "model_used": CLAUDE_SONNET_MODEL,
        "generation_time_ms": elapsed_ms,
    }


def normalize_beats_plan(beats_plan: list[dict]) -> list[dict]:
    """Validate and normalize beats_plan from UI or Claude."""
    out: list[dict] = []
    for i, row in enumerate(beats_plan, start=1):
        if not isinstance(row, dict):
            continue
        beat_type = str(row.get("beat_type") or "dialogue").strip().lower()
        if beat_type not in ("dialogue", "stage_direction"):
            beat_type = "stage_direction" if row.get("speaker") in (
                "[Stage Direction]", "Scene", "Narrator",
            ) else "dialogue"
        speaker = str(row.get("speaker") or "Character").strip()
        if beat_type == "stage_direction" and speaker == "Character":
            speaker = "[Stage Direction]"
        dialogue = str(row.get("dialogue_text") or "").strip()
        invented = bool(row.get("invented")) or dialogue.startswith("[CLAUDE INVENTED]")
        out.append({
            "beat_index": int(row.get("beat_index") or i),
            "beat_type": beat_type,
            "speaker": speaker,
            "dialogue_text": dialogue,
            "emotion": str(row.get("emotion") or "neutral").strip() or "neutral",
            "scene_notes": str(row.get("scene_notes") or "").strip(),
            "skeleton_quote": str(row.get("skeleton_quote") or "").strip(),
            "invented": invented,
        })
    out.sort(key=lambda b: b["beat_index"])
    for j, beat in enumerate(out, start=1):
        beat["beat_index"] = j
    return out
