"""Claude-powered Extract beats — plan (Phase A) and Kling prompt author (Phase B).

Per Production/docs/TECH_SPEC_CLAUDE_SUGGEST_BEATS_v1.md
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from beat_extract_policy import (
    build_still_insert_prompt,
    kling_staging_policy_block,
    load_gold_example,
    postprocess_beats_plan,
    postprocess_kling_author_results,
    postprocess_plan_result,
)

CLAUDE_SONNET_MODEL = "claude-sonnet-4-6"
PLAN_TIMEOUT_S = 90
AUTHOR_TIMEOUT_S = 120
AUTHOR_DIALOGUE_BATCH_SIZE = 8

_TOOLING_ROOT = Path(__file__).resolve().parent.parent
_PLANNER_SKILL = _TOOLING_ROOT / ".claude" / "skills" / "beat-extract-planner" / "SKILL.md"
_KLING_AUTHOR_SKILL = _TOOLING_ROOT / ".claude" / "skills" / "beat-kling-prompt-author" / "SKILL.md"


def _strip_markdown_fences(text: str) -> str:
    t = (text or "").strip()
    if not t.startswith("```"):
        return t
    lines = t.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _extract_json_blob(text: str) -> str:
    """Return the outermost {...} or [...] substring when Claude adds preamble."""
    t = _strip_markdown_fences(text)
    for opener, closer in (("{", "}"), ("[", "]")):
        start = t.find(opener)
        if start < 0:
            continue
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(t)):
            ch = t[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    return t[start : i + 1]
    return t


def _normalize_json_text(text: str) -> str:
    return (
        text.replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2018", "'")
        .replace("\u2019", "'")
    )


def _parse_claude_json(raw: str) -> dict | list:
    text = _normalize_json_text(_extract_json_blob(raw))
    try:
        return json.loads(text)
    except json.JSONDecodeError as first_err:
        # Common Claude slip: trailing commas before } or ].
        import re

        repaired = re.sub(r",(\s*[}\]])", r"\1", text)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            raise first_err from None


def _anthropic_text(resp: dict) -> str:
    parts: list[str] = []
    for block in resp.get("content") or []:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text") or "")
    return "".join(parts)


def _anthropic_tool_input(resp: dict, tool_name: str) -> dict | None:
    for block in resp.get("content") or []:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "tool_use" and block.get("name") == tool_name:
            inp = block.get("input")
            if isinstance(inp, dict):
                return inp
    return None


def _call_anthropic(
    api_key: str,
    system: str,
    user: str,
    *,
    max_tokens: int,
    timeout: int,
    tools: list[dict] | None = None,
    tool_choice: dict | None = None,
) -> tuple[dict, int]:
    from server_handlers.phases import _call_anthropic_urllib

    req_body: dict[str, Any] = {
        "model": CLAUDE_SONNET_MODEL,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    if tools:
        req_body["tools"] = tools
    if tool_choice:
        req_body["tool_choice"] = tool_choice
    resp, elapsed_ms = _call_anthropic_urllib(api_key, req_body, timeout=timeout)
    return resp, elapsed_ms


_BEAT_PLAN_TOOL = {
    "name": "submit_beat_plan",
    "description": "Submit the approved beat plan JSON for this segment.",
    "input_schema": {
        "type": "object",
        "properties": {
            "story_summary": {"type": "string"},
            "beats_plan": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "beat_index": {"type": "integer"},
                        "beat_type": {
                            "type": "string",
                            "enum": ["dialogue", "stage_still"],
                            "description": "dialogue = Kling O3 clip; stage_still = GPT still insert. Legacy stage_direction coerces to dialogue on normalize.",
                        },
                        "speaker": {"type": "string"},
                        "dialogue_text": {"type": "string"},
                        "emotion": {"type": "string"},
                        "scene_notes": {"type": "string"},
                        "skeleton_quote": {"type": "string"},
                        "invented": {"type": "boolean"},
                    },
                    "required": [
                        "beat_index",
                        "beat_type",
                        "speaker",
                        "dialogue_text",
                        "emotion",
                        "scene_notes",
                    ],
                },
            },
        },
        "required": ["story_summary", "beats_plan"],
    },
}

_KLING_AUTHOR_TOOL = {
    "name": "submit_kling_prompts",
    "description": "Submit Kling O3 prompts for each dialogue beat.",
    "input_schema": {
        "type": "object",
        "properties": {
            "beats": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "beat_index": {"type": "integer"},
                        "kling_o3_prompt": {"type": "string"},
                        "emotion": {"type": "string"},
                        "scene_notes": {"type": "string"},
                    },
                    "required": ["beat_index", "kling_o3_prompt", "emotion", "scene_notes"],
                },
            },
        },
        "required": ["beats"],
    },
}


def _parse_structured_response(resp: dict, *, tool_name: str) -> dict:
    tool_input = _anthropic_tool_input(resp, tool_name)
    if tool_input is not None:
        return tool_input
    parsed = _parse_claude_json(_anthropic_text(resp))
    if not isinstance(parsed, dict):
        raise ValueError(f"Claude {tool_name} response must be a JSON object")
    return parsed


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
        # Gold Tessa intro first — Event-1 personality density reference.
        for beat in beats:
            if beat.get("beat_id") == "bg_arc1_event1_pre_tessa_o3_canonical":
                prompt = (beat.get("kling_o3_prompt") or "").strip()
                if len(prompt) >= 120:
                    examples.append(
                        f"--- GOLD Tessa intro ({beat.get('beat_id')}) ---\n{prompt[:2200]}"
                    )
                break
        for beat in beats:
            prompt = (beat.get("kling_o3_prompt") or "").strip()
            if len(prompt) < 120:
                continue
            if beat.get("intro_beat_role"):
                continue
            if beat.get("beat_id") == "bg_arc1_event1_pre_tessa_o3_canonical":
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
        "stable eye-level close-up — close up view of character, seen from the torso up.\n\n"
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
    gold = load_gold_example(
        meta.get("arc_number", 1), meta.get("event_id", ""), meta.get("phase", "pre"),
    )
    phase = meta.get("phase") or "pre"
    soft_target = "6–15" if phase in ("pre", "full") else "3–8"
    system = (
        f"{skill}\n\n"
        f"{kling_staging_policy_block()}\n\n"
        + (f"GOLD REFERENCE (match this density and style):\n{gold}\n\n" if gold else "")
        + "Call submit_beat_plan with story_summary and beats_plan.\n"
        "Use Lorelai (raccoon), Tessa, Arlo, or [Stage Direction]. "
        "Use beat_type stage_still for inscription/runestone still inserts.\n"
        "beats_plan scene_notes = ONE sentence of on-screen staging only (gesture/expression). "
        "Put every spoken line in dialogue_text only — never repeat dialogue in scene_notes, "
        "and never put Voice line:, @Image1, or storybook-style tails in scene_notes.\n"
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
        api_key,
        system,
        user,
        max_tokens=4096,
        timeout=PLAN_TIMEOUT_S,
        tools=[_BEAT_PLAN_TOOL],
        tool_choice={"type": "tool", "name": "submit_beat_plan"},
    )
    parsed = _parse_structured_response(resp, tool_name="submit_beat_plan")
    if not isinstance(parsed, dict):
        raise ValueError("Claude plan response must be a JSON object")
    beats_plan = parsed.get("beats_plan") or []
    if not isinstance(beats_plan, list) or not beats_plan:
        raise ValueError("beats_plan must be a non-empty array")
    raw = {
        "story_summary": str(parsed.get("story_summary") or "").strip(),
        "beats_plan": beats_plan,
        "model_used": CLAUDE_SONNET_MODEL,
        "generation_time_ms": elapsed_ms,
    }
    processed = postprocess_plan_result(raw, meta)
    return processed


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

    prompt_by_index: dict[int, str] = {}
    author_fields: dict[int, dict] = {}
    dialogue_beats: list[dict] = []
    for row in beats_plan:
        idx = int(row.get("beat_index") or 0)
        bt = str(row.get("beat_type") or "dialogue").lower()
        if bt == "stage_still":
            if idx:
                prompt_by_index[idx] = build_still_insert_prompt(row)
            continue
        if idx:
            dialogue_beats.append(row)

    elapsed_ms = 0
    author_warnings: list[str] = []

    def _missing_dialogue_rows() -> list[dict]:
        return [
            row for row in dialogue_beats
            if int(row.get("beat_index") or 0) not in prompt_by_index
        ]

    def _run_author_batches(rows: list[dict], *, label: str) -> None:
        nonlocal elapsed_ms
        if not rows:
            return
        batch_size = AUTHOR_DIALOGUE_BATCH_SIZE
        total_batches = (len(rows) + batch_size - 1) // batch_size
        for batch_start in range(0, len(rows), batch_size):
            batch = rows[batch_start:batch_start + batch_size]
            batch_num = batch_start // batch_size + 1
            print(
                f"[BG] kling-author {label} batch {batch_num}/{total_batches} "
                f"beats={len(batch)} idx={batch[0].get('beat_index')}..{batch[-1].get('beat_index')}",
                flush=True,
            )
            plan_json = json.dumps(
                {"story_summary": story_summary, "beats_plan": batch},
                ensure_ascii=False,
                indent=2,
            )
            user = (
                f"Segment: arc {meta.get('arc_number')} event {meta.get('event_id')} "
                f"phase {meta.get('phase')}\n\n"
                f"Approved dialogue beats only ({label} batch {batch_num}):\n"
                f"{plan_json}\n"
            )
            resp, batch_ms = _call_anthropic(
                api_key,
                system,
                user,
                max_tokens=8192,
                timeout=AUTHOR_TIMEOUT_S,
                tools=[_KLING_AUTHOR_TOOL],
                tool_choice={"type": "tool", "name": "submit_kling_prompts"},
            )
            elapsed_ms += batch_ms
            parsed = _parse_structured_response(resp, tool_name="submit_kling_prompts")
            beats_out = parsed.get("beats") or []
            if not isinstance(beats_out, list) or not beats_out:
                author_warnings.append(
                    f"Claude returned no prompts for {label} batch starting "
                    f"beat_index {batch[0].get('beat_index')} — tooling will synthesize gaps",
                )
                continue
            for row in beats_out:
                if not isinstance(row, dict):
                    continue
                idx = int(row.get("beat_index") or 0)
                prompt = str(row.get("kling_o3_prompt") or "").strip()
                if idx and prompt:
                    prompt_by_index[idx] = prompt
                if idx:
                    author_fields[idx] = row

    if dialogue_beats:
        system = (
            f"{skill}\n\n"
            f"{kling_staging_policy_block()}\n\n"
            "Few-shot approved prompts:\n"
            f"{few_shot}\n\n"
            "Call submit_kling_prompts with one entry per dialogue beat_index in THIS batch.\n"
            "Include every beat_index you can; tooling fills any gaps from the approved plan.\n"
            "Include emotion and scene_notes on every beat; tooling rebuilds final shape on approve.\n"
            "Author draft: @Image1 ({Speaker}). Scene from @Image2. + screen direction + voice line.\n"
            "Emotion tags OUTSIDE quotes: Tessa speaks in a …: [curious] \"Hello. [pause] Hi!\"\n"
        )
        _run_author_batches(dialogue_beats, label="primary")
        missing_after_primary = _missing_dialogue_rows()
        if missing_after_primary:
            print(
                f"[BG] kling-author retry missing={len(missing_after_primary)} "
                f"idx={[r.get('beat_index') for r in missing_after_primary]}",
                flush=True,
            )
            _run_author_batches(missing_after_primary, label="retry")
        still_missing = _missing_dialogue_rows()
        if still_missing:
            author_warnings.append(
                "Claude omitted "
                f"{len(still_missing)} dialogue prompt(s) after retry — "
                "tooling will synthesize from the approved plan",
            )

    merged_plan: list[dict] = []
    for row in beats_plan:
        idx = int(row.get("beat_index") or 0)
        extra = author_fields.get(idx) or {}
        merged = dict(row)
        if extra.get("emotion"):
            merged["emotion"] = extra["emotion"]
        if extra.get("scene_notes"):
            from beat_extract_policy import strip_plan_scene_notes_for_editor

            merged["scene_notes"] = strip_plan_scene_notes_for_editor(
                str(extra["scene_notes"]),
                dialogue_text=str(merged.get("dialogue_text") or ""),
                beat_type=str(merged.get("beat_type") or "dialogue"),
            )
        merged_plan.append(merged)

    prompt_by_index, enriched_plan, postprocess_warnings = postprocess_kling_author_results(
        merged_plan, prompt_by_index,
    )
    author_warnings.extend(postprocess_warnings)
    return {
        "prompt_by_index": prompt_by_index,
        "beats_plan_enriched": enriched_plan,
        "model_used": CLAUDE_SONNET_MODEL,
        "generation_time_ms": elapsed_ms,
        "author_warnings": author_warnings,
    }


def normalize_beats_plan(beats_plan: list[dict]) -> list[dict]:
    """Validate, apply cast policy, and normalize beats_plan from UI or Claude."""
    processed, _warnings = postprocess_beats_plan(beats_plan)
    return processed
