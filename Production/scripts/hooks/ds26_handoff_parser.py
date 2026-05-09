"""
Parse HANDOFF_*.md files for DS-26 gate-count and evidence checklist (v2 MVP).

Normative companion: Production/docs/HANDOFF_TEMPLATE_v2.md
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# Verbatim v2 marker (first line of the blockquote in HALT gates §A).
_V2_AUTONOMOUS_REMINDER = "Autonomous mode does not bypass HALT gates per DS-26."

_HALT_HEADER = re.compile(r"(?im)^##\s+HALT\s+gates\s*$")
_TABLE_GATE_NUM = re.compile(r"(?m)^\|\s*(\d+)\s*\|")
_NO_GATES_BOILERPLATE = re.compile(r"No HALT gates", re.I)


class LegacyHandoffNotSupported(Exception):
    """Raised when the file is missing v2 HALT-gates structure (treat as legacy v1)."""


@dataclass
class HandoffParseResult:
    declared_gate_count: Optional[int]
    evidence_checklist: list[dict[str, Any]]
    handoff_format_version: str
    parse_errors: list[str] = field(default_factory=list)


@dataclass
class ComparisonResult:
    matches_template: bool
    template_gate_count: Optional[int]
    handoff_gate_count: Optional[int]
    messages: list[str] = field(default_factory=list)


@dataclass
class DualHandoffResult:
    prior_gate_count: Optional[int]
    current_gate_count: Optional[int]
    gate_count_drift: bool
    messages: list[str] = field(default_factory=list)


def _read_text(path: str) -> str:
    return Path(path).expanduser().read_text(encoding="utf-8")


def _halts_section(text: str) -> Optional[str]:
    m = _HALT_HEADER.search(text)
    if not m:
        return None
    start = m.end()
    rest = text[start:]
    m2 = re.search(r"(?m)^##\s+", rest)
    if m2:
        return rest[: m2.start()]
    return rest


def _gate_indices_from_section(section: str) -> list[int]:
    nums: list[int] = []
    for line in section.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        mm = re.match(r"^\|\s*(\d+)\s*\|", line)
        if mm:
            n = int(mm.group(1))
            if n > 0:
                nums.append(n)
    return sorted(set(nums))


def _evidence_checklist_from_section(section: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in section.splitlines():
        if not line.strip().startswith("|"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 4:
            continue
        idx_cell = parts[1]
        if not idx_cell.isdigit():
            continue
        gate_idx = int(idx_cell)
        if gate_idx <= 0:
            continue
        evidence = parts[3] if len(parts) > 3 else ""
        if evidence.startswith("---"):
            continue
        rows.append({"gate_index": gate_idx, "evidence_source": evidence, "raw_row": line.strip()})
    return rows


def parse_handoff(path: str) -> HandoffParseResult:
    text = _read_text(path)
    errs: list[str] = []

    section = _halts_section(text)
    if section is None:
        raise LegacyHandoffNotSupported("missing ## HALT gates section")

    if _V2_AUTONOMOUS_REMINDER not in text:
        raise LegacyHandoffNotSupported("missing v2 autonomous-mode reminder paragraph")

    declared: Optional[int]
    if _NO_GATES_BOILERPLATE.search(section):
        declared = 0
        checklist: list[dict[str, Any]] = []
    else:
        gnums = _gate_indices_from_section(section)
        checklist = _evidence_checklist_from_section(section)
        if gnums:
            declared = len(gnums)
        else:
            declared = None
            errs.append("gate_table_not_found_or_empty")

    return HandoffParseResult(
        declared_gate_count=declared,
        evidence_checklist=checklist,
        handoff_format_version="v2",
        parse_errors=errs,
    )


def _example_block_gate_count(template_text: str) -> tuple[Optional[int], list[str]]:
    msgs: list[str] = []
    key = "## HALT gates — example"
    i = template_text.find(key)
    if i < 0:
        return None, ["template_missing_halts_example_header"]
    j = template_text.find("```markdown", i)
    if j < 0:
        return None, ["template_missing_markdown_example_fence"]
    j += len("```markdown")
    k = template_text.find("```", j)
    if k < 0:
        return None, ["template_unclosed_markdown_fence"]
    block = template_text[j:k]
    gnums = _gate_indices_from_section(block)
    if not gnums:
        return None, ["template_example_has_no_numbered_gate_rows"]
    return len(gnums), msgs


def compare_handoff_to_template(handoff: HandoffParseResult, template_path: str) -> ComparisonResult:
    template_text = _read_text(template_path)
    tcount, msgs = _example_block_gate_count(template_text)
    hcount = handoff.declared_gate_count

    if tcount is None:
        return ComparisonResult(
            matches_template=False,
            template_gate_count=None,
            handoff_gate_count=hcount,
            messages=msgs + ["cannot_determine_template_gate_count"],
        )
    if hcount is None:
        return ComparisonResult(
            matches_template=False,
            template_gate_count=tcount,
            handoff_gate_count=None,
            messages=["handoff_gate_count_unknown"],
        )
    ok = hcount == tcount
    out_msgs = list(msgs)
    if not ok:
        out_msgs.append(f"gate_count_mismatch handoff={hcount} template_example={tcount}")
    return ComparisonResult(
        matches_template=ok,
        template_gate_count=tcount,
        handoff_gate_count=hcount,
        messages=out_msgs,
    )


def compare_handoffs(current: HandoffParseResult, prior: HandoffParseResult) -> DualHandoffResult:
    a, b = current.declared_gate_count, prior.declared_gate_count
    drift = False
    msgs: list[str] = []
    if a is not None and b is not None and a != b:
        drift = True
        msgs.append(f"gate_count_drift prior={b} current={a}")
    elif a is None or b is None:
        msgs.append("gate_count_comparison_incomplete_missing_count")
    return DualHandoffResult(
        prior_gate_count=b,
        current_gate_count=a,
        gate_count_drift=drift,
        messages=msgs,
    )
