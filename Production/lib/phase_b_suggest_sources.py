"""Phase B Suggest Script source loaders and deterministic therapeutic brief builder.

Loads per-module research dossiers + approved scripts from Production/, extracts
structured brief fields from dossier sections (not LLM invention), and merges
Arc Skeleton metadata (spell name, technique, domain) into module identity.
"""
from __future__ import annotations

import glob
import os
import re
from typing import Any

_MD_H2_SECTION = re.compile(
    r"^##\s+(.+?)\s*$",
    re.MULTILINE,
)
_SKELETON_WATCH_OUTS = re.compile(
    r"\*\*\(4\)\s+What the AI narrator should NOT do:\*\*\s*\n(.*?)(?:\n\*\*\(|^###|\Z)",
    re.IGNORECASE | re.MULTILINE | re.DOTALL,
)


def _version_score(path: str) -> tuple[int, int, str]:
    """Higher is better: version number, basename length, path."""
    base = os.path.basename(path)
    ver = 0
    m = re.search(r"v(\d+)(?:_\d+)?", base, re.IGNORECASE)
    if m:
        ver = int(m.group(1))
    penalized = -10_000 if "CORRECTED" in base.upper() else 0
    return ver, len(base) + penalized, path


def _pick_best_glob(production_dir: str, pattern: str) -> tuple[str, str]:
    paths = glob.glob(os.path.join(production_dir, pattern))
    if not paths:
        return "", ""
    best = max(paths, key=_version_score)
    return best, os.path.basename(best)


def load_phase_b_research_dossier(production_dir: str, m_number: int) -> dict[str, Any]:
    """Load highest-version ``M{n}_PHASE_B_RESEARCH_DOSSIER*.md``."""
    pattern = f"M{int(m_number)}_PHASE_B_RESEARCH_DOSSIER*.md"
    path, basename = _pick_best_glob(production_dir, pattern)
    entry: dict[str, Any] = {
        "filename": basename,
        "path": path,
        "chars": 0,
        "text": "",
    }
    if not path:
        return entry
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        entry["text"] = text
        entry["chars"] = len(text)
    except Exception:
        pass
    return entry


def load_phase_b_approved_script(production_dir: str, m_number: int) -> dict[str, Any]:
    """Load highest-version ``M{n}_PHASE_B_MEDITATION_SCRIPT*.md`` (skip CORRECTED dupes)."""
    pattern = f"M{int(m_number)}_PHASE_B_MEDITATION_SCRIPT*.md"
    path, basename = _pick_best_glob(production_dir, pattern)
    entry: dict[str, Any] = {
        "filename": basename,
        "path": path,
        "chars": 0,
        "text": "",
    }
    if not path:
        return entry
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        entry["text"] = text.strip()
        entry["chars"] = len(entry["text"])
    except Exception:
        pass
    return entry


def extract_md_section(text: str, heading_prefix: str) -> str:
    """Return body of first ``## {heading_prefix}`` section (prefix match, case-insensitive)."""
    if not text:
        return ""
    prefix = heading_prefix.strip().lower()
    matches = list(_MD_H2_SECTION.finditer(text))
    for i, m in enumerate(matches):
        title = (m.group(1) or "").strip()
        if not title.lower().startswith(prefix):
            continue
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        return text[start:end].strip()
    return ""


def _strip_md_inline(text: str) -> str:
    """Flatten ``**bold**`` and collapse whitespace for prompt-safe bullets."""
    out = re.sub(r"\*\*(.+?)\*\*", r"\1", text or "")
    return re.sub(r"\s+", " ", out).strip()


def extract_numbered_list_items(section_text: str) -> list[str]:
    """Pull numbered list items from a markdown section (full line per item)."""
    items: list[str] = []
    for line in (section_text or "").splitlines():
        line = line.strip()
        m = re.match(r"^\d+\.\s+(.+)$", line)
        if not m:
            continue
        item = _strip_md_inline(m.group(1))
        if item:
            items.append(item)
    return items


def extract_skeleton_watch_outs(therapeutic_note: str) -> list[str]:
    """Extract §(4) narrator watch-outs from a Therapeutic Note block."""
    if not therapeutic_note:
        return []
    m = _SKELETON_WATCH_OUTS.search(therapeutic_note)
    if not m:
        return []
    body = m.group(1) or ""
    items = []
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("- "):
            items.append(line[2:].strip())
        elif line.startswith("Do NOT"):
            items.append(line)
    return [i for i in items if i][:4]


def build_therapeutic_brief_from_sources(
    skeleton_meta: dict[str, Any],
    therapeutic_note: str,
    dossier_text: str,
) -> dict[str, list | str] | None:
    """Build brief deterministically from dossier + skeleton — no LLM invention."""
    spell = str(skeleton_meta.get("spell_name") or "").strip()
    technique = str(skeleton_meta.get("technique") or "").strip()
    creature = str(skeleton_meta.get("creature") or "").strip()

    recommended = extract_md_section(dossier_text, "Recommended Approach")
    incorporate = extract_md_section(dossier_text, "Elements to Incorporate")
    avoid = extract_md_section(dossier_text, "Elements to Avoid")
    metaphor = extract_md_section(dossier_text, "Phase A Metaphor")

    must_hits = extract_numbered_list_items(recommended)
    what_to_evoke = extract_numbered_list_items(incorporate)
    watch_outs = extract_numbered_list_items(avoid) + extract_skeleton_watch_outs(therapeutic_note)

    goal = ""
    if metaphor:
        first_para = metaphor.split("\n\n")[0].strip()
        goal = re.sub(r"\s+", " ", first_para)
    if not goal and recommended:
        first = recommended.split("\n\n")[0].strip()
        goal = re.sub(r"\s+", " ", first)
    if not goal and spell:
        goal = (
            f"Guide the child through the {spell} exercise "
            f"({technique or 'see Therapeutic Note'}) with {creature or 'the module creature'}."
        )

    if not goal and not must_hits:
        return None

    return {
        "goal": goal,
        "must_hits": must_hits[:10],
        "what_to_evoke": what_to_evoke[:8],
        "watch_outs": watch_outs[:8],
        "source": "dossier_extraction",
        "spell_name": spell,
    }


def format_dossier_prompt_section(dossier: dict[str, Any]) -> str:
    """Render research dossier for Claude Phase B prompt."""
    text = (dossier.get("text") or "").strip()
    fname = dossier.get("filename") or "unknown"
    if not text:
        return (
            "Phase B Research Dossier: (NOT FOUND — expected "
            f"Production/M{{N}}_PHASE_B_RESEARCH_DOSSIER*.md)\n"
        )
    return (
        "Phase B Research Dossier for THIS module (canonical clinical source — "
        "Recommended Approach defines ordered steps; Elements to Incorporate/Avoid "
        "are mandatory constraints; script MUST follow this dossier):\n"
        f"Source file: Production/{fname}\n"
        f"---\n{text}\n---\n"
    )


def format_therapeutic_brief_for_script_prompt(brief: dict[str, Any] | None) -> str:
    """Render structured brief as the mandatory Phase B script blueprint."""
    if not brief:
        return (
            "THERAPEUTIC BRIEF: (NOT AVAILABLE — derive steps from Research "
            "Dossier Recommended Approach only)\n"
        )
    goal = _strip_md_inline(str(brief.get("goal") or ""))
    must_hits = [_strip_md_inline(str(x)) for x in (brief.get("must_hits") or []) if str(x).strip()]
    evoke = [_strip_md_inline(str(x)) for x in (brief.get("what_to_evoke") or []) if str(x).strip()]
    watch = [_strip_md_inline(str(x)) for x in (brief.get("watch_outs") or []) if str(x).strip()]
    spell = _strip_md_inline(str(brief.get("spell_name") or ""))

    lines = [
        "THERAPEUTIC BRIEF (MANDATORY SCRIPT BLUEPRINT — the spoken script MUST "
        "implement every must_hit below, in order; do not substitute another "
        "technique or generic meditation):",
    ]
    if spell:
        lines.append(f"  Spell: {spell}")
    if goal:
        lines.append(f"  Goal: {goal}")
    if must_hits:
        lines.append("  Ordered steps (must_hits — each must appear in the script):")
        for i, step in enumerate(must_hits, 1):
            lines.append(f"    {i}. {step}")
    if evoke:
        lines.append("  What to evoke (weave into narration):")
        for item in evoke[:6]:
            lines.append(f"    - {item}")
    if watch:
        lines.append("  Watch-outs (do NOT do these):")
        for item in watch[:6]:
            lines.append(f"    - {item}")
    return "\n".join(lines) + "\n"


def format_skeleton_metadata_section(skeleton_meta: dict[str, Any]) -> str:
    """Render Arc Skeleton module metadata block."""
    if not skeleton_meta:
        return ""
    lines = [
        "Arc Skeleton module metadata (authoritative spell + technique identity):",
        f"  - Skeleton event id: {skeleton_meta.get('skeleton_event_id', '?')}",
        f"  - Event name: {skeleton_meta.get('event_name', '')}",
        f"  - Creature: {skeleton_meta.get('creature', '')}",
        f"  - Domain: {skeleton_meta.get('domain', '')}",
        f"  - Technique: {skeleton_meta.get('technique', '')}",
        f"  - Spell Name: {skeleton_meta.get('spell_name', '')}",
    ]
    return "\n".join(lines) + "\n"


def enrich_module_meta(module_meta: dict[str, Any], skeleton_meta: dict[str, Any]) -> dict[str, Any]:
    """Merge skeleton metadata; skeleton wins for spell/technique/domain naming."""
    out = dict(module_meta)
    if skeleton_meta.get("creature"):
        out["creature_name"] = skeleton_meta["creature"]
    if skeleton_meta.get("technique"):
        out["technique_name"] = skeleton_meta["technique"]
    if skeleton_meta.get("spell_name"):
        out["spell_name"] = skeleton_meta["spell_name"]
    if skeleton_meta.get("domain"):
        out["domain"] = skeleton_meta["domain"]
    if skeleton_meta.get("skeleton_event_id"):
        out["skeleton_event_id"] = skeleton_meta["skeleton_event_id"]
    return out
