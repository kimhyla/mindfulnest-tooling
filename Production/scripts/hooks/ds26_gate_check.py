"""
DS-26 Mechanical Gate — stop-hook style checker for subagent output (spec v3-E).

Normative design: Production/docs/DS_26_MECHANICAL_GATE_TECH_SPEC_v3.md
§3.4-A declaration regex, §3.4.1-A verify_gate_evidence, §3.7-A spawn-tool names, §6.0-A.

Uses DirectusAdminClient (DS-30) when verifying Directus evidence — never urllib/requests here.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal, Optional, Sequence

_PRODUCTION_ROOT = Path(__file__).resolve().parents[2]
if str(_PRODUCTION_ROOT) not in sys.path:
    sys.path.insert(0, str(_PRODUCTION_ROOT))

from lib.directus_admin_client import DirectusAdminClient

from scripts.hooks.ds26_handoff_parser import (
    LegacyHandoffNotSupported,
    compare_handoff_to_template,
    compare_handoffs,
    parse_handoff,
)

# --- §3.4-A (v3 permissive alternation) ---------------------------------------

DECLARATION_RE = re.compile(
    r"(?i)HALT\s+gate\s+scan\s*:\s*(\d+)\s+gate(?:s|\(s\))?\s+detected",
)

# --- §3.4.1-A.2 + §6.0-A ------------------------------------------------------

BROAD_DIRECTUS_HINT_RE = re.compile(
    r"(?i)\b(?:LD[\s\-]?\d+|prod_\w+|items/prod_\w+)",
)

DIRECTUS_REF_RE = re.compile(
    r"(?:"
    r"LD[\s\-]?(?P<ld_id>\d+)"
    r"|"
    r"prod_(?P<coll1>\w+)\s*(?:id\s*=\s*|row\s+|/)(?P<row1>\d+)"
    r"|"
    r"items/prod_(?P<coll2>\w+)/(?P<row2>\d+)"
    r")",
    re.IGNORECASE,
)

# --- §3.7-A -------------------------------------------------------------------

SUBAGENT_SPAWN_TOOL_NAMES: set[str] = {"Agent", "Task", "subagent"}

# --- Optional gate / HALT extensions (declarations beyond canonical N-detect) -

_MET_NOT_MET_RE = re.compile(
    r"(?i)HALT\s+gate\s+scan\s*:\s*\d+\s+gate(?:s|\(s\))?\s+detected\s*,\s*"
    r"(\d+)\s+met\s*,\s*(\d+)\s+not\s+met",
)
_HALTED_SENTINEL_RE = re.compile(r"(?i)\bHALTED\b")

# T13 — implicit handoff file reference without `handoff_path` passed to checker.
_HANDOFF_REF_RE = re.compile(r"(?i)\bHANDOFF[_A-Z0-9-]+\.md\b")


def is_subagent_spawn_call(tool_call: dict[str, Any]) -> bool:
    """§3.7-A — extensible spawn-tool name set."""
    name = tool_call.get("name")
    return isinstance(name, str) and name in SUBAGENT_SPAWN_TOOL_NAMES


def match_directus_reference(evidence_source: str) -> Optional[re.Match[str]]:
    """
    §3.4.1-A v3-E: MODE 1 fullmatch on stripped; MODE 2 search ONLY if '\\n' in evidence.

    (Top §0.1 v3-E row: MODE 2 gated to multi-line so F-FRAG-1 single-line `LD-578xyz`
    never partially resolves via substring search.)
    """
    stripped = evidence_source.strip()
    fm = DIRECTUS_REF_RE.fullmatch(stripped)
    if fm is not None:
        return fm
    if "\n" not in evidence_source:
        return None
    return DIRECTUS_REF_RE.search(evidence_source)


def resolve_collection_and_row(match: re.Match[str]) -> Optional[tuple[str, int]]:
    """§3.4.1-A.2 — map match to (collection_suffix, row_id) for prod_{collection}."""
    if match.group("ld_id") is not None:
        return ("locked_decisions", int(match.group("ld_id")))
    c1, r1 = match.group("coll1"), match.group("row1")
    if c1 is not None and r1 is not None:
        return (c1, int(r1))
    c2, r2 = match.group("coll2"), match.group("row2")
    if c2 is not None and r2 is not None:
        return (c2, int(r2))
    return None


def directus_row_evidence_verified(row: Any) -> bool:
    """
    §3.4.1-A.3 / §6.0-A — truthy non-empty row; explicit None/{}/[];
    v3-E wrapper envelopes for {data: null}, {data: []}, {data: {}}.
    """
    if row is None:
        return False
    if isinstance(row, dict) and len(row) == 0:
        return False
    if isinstance(row, list) and len(row) == 0:
        return False
    if isinstance(row, dict) and "data" in row:
        inner = row["data"]
        if inner is None:
            return False
        if isinstance(inner, (dict, list)) and len(inner) == 0:
            return False
    return True


def default_text_presence_check(evidence_source: str, assistant_turns: Sequence[str]) -> bool:
    """Non-Directus: best-effort substring presence across assistant turns."""
    ev = evidence_source.strip()
    if not ev:
        return False
    for turn in assistant_turns:
        if ev in turn:
            return True
    return False


def default_activity_log_cites_gate(parsed_gate: dict[str, Any], _writes: Any) -> bool:
    return False


def default_halt_row_cites_gate(parsed_gate: dict[str, Any], _writes: Any) -> bool:
    return False


def verify_gate_evidence(
    parsed_gate: dict[str, Any],
    client: Optional[DirectusAdminClient],
    surface_checklist: list[str],
    *,
    assistant_turns: Sequence[str] = (),
    text_presence_check: Callable[[str, Sequence[str]], bool] = default_text_presence_check,
    activity_log_cites_gate: Callable[[dict[str, Any], Any], bool] = default_activity_log_cites_gate,
    halt_row_cites_gate: Callable[[dict[str, Any], Any], bool] = default_halt_row_cites_gate,
    session_window_writes: Any = None,
) -> bool:
    """
    §3.4.1-A.3 — single normative fail mode (no silent text-presence for Directus hints).
    """
    evidence_source = str(parsed_gate.get("evidence_source", "") or "")
    gate_index = parsed_gate.get("gate_index", "?")

    if not BROAD_DIRECTUS_HINT_RE.search(evidence_source):
        return (
            text_presence_check(evidence_source, assistant_turns)
            or activity_log_cites_gate(parsed_gate, session_window_writes)
            or halt_row_cites_gate(parsed_gate, session_window_writes)
        )

    precise_match = match_directus_reference(evidence_source)
    resolved = resolve_collection_and_row(precise_match) if precise_match else None
    if resolved is None:
        surface_checklist.append(
            f"UNVERIFIED_DIRECTUS_REF gate={gate_index} "
            f"evidence_source={evidence_source!r} "
            f"reason=broad_hint_matched_but_precise_regex_did_not_parse"
        )
        return False

    coll_suffix, row_id = resolved
    collection = f"prod_{coll_suffix}"

    if client is None:
        surface_checklist.append(
            f"UNVERIFIED_DIRECTUS_REF gate={gate_index} "
            f"evidence_source={evidence_source!r} "
            f"reason=directus_probe_failed exc=NoClient"
        )
        return False

    try:
        row = client.get_item(collection, row_id)
    except Exception as exc:
        surface_checklist.append(
            f"UNVERIFIED_DIRECTUS_REF gate={gate_index} "
            f"evidence_source={evidence_source!r} "
            f"reason=directus_probe_failed exc={type(exc).__name__}"
        )
        return False

    if not directus_row_evidence_verified(row):
        return False
    return True


# --- Gate checklist extraction ------------------------------------------------

_GATE_EVIDENCE_HEADER = re.compile(
    r"(?im)^Gate\s+(\d+)\s*[—\-:]\s*Evidence\s*:\s*",
)
_TABLE_GATE_ROW = re.compile(
    r"(?im)^\|\s*(\d+)\s*\|\s*[^|\n]+\|\s*([^|\n]+)\s*\|",
)


def extract_gate_evidence_map(text: str) -> dict[int, str]:
    """Pull gate_index → evidence_source from `Gate N — Evidence:` lines or markdown table."""
    result: dict[int, str] = {}
    hdr_matches = list(_GATE_EVIDENCE_HEADER.finditer(text))
    for i, m in enumerate(hdr_matches):
        gidx = int(m.group(1))
        start = m.end()
        end = hdr_matches[i + 1].start() if i + 1 < len(hdr_matches) else len(text)
        result[gidx] = text[start:end].strip()
    for m in _TABLE_GATE_ROW.finditer(text):
        gidx = int(m.group(1))
        if gidx not in result:
            cell = m.group(2).strip()
            if cell and not cell.startswith("---"):
                result[gidx] = cell
    return result


def parse_declaration_count(text: str) -> Optional[int]:
    """Return declared N from last HALT gate scan line, or None."""
    matches = DECLARATION_RE.findall(text)
    if not matches:
        return None
    return int(matches[-1])


Verdict = Literal["PASS", "FAIL", "SILENT_SKIP"]


@dataclass
class Ds26GateCheckResult:
    verdict: Verdict
    declaration_count: Optional[int]
    expected_gate_indices: list[int]
    evidence_entries_parsed: dict[int, str]
    failures: list[str] = field(default_factory=list)
    surface_checklist: list[str] = field(default_factory=list)
    met_not_met: Optional[tuple[int, int]] = None
    warnings: list[str] = field(default_factory=list)
    handoff_format_version: Optional[str] = None


def parse_met_not_met(text: str) -> Optional[tuple[int, int]]:
    m = _MET_NOT_MET_RE.search(text)
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)))


def should_skip_false_positive_guard(
    *,
    candidate_handoffs: int = 0,
    tool_calls: Optional[Sequence[dict[str, Any]]] = None,
    session_complete_writes: int = 0,
) -> bool:
    """§3.7 — skip when no handoff context, no subagent spawn, no complete writes."""
    if candidate_handoffs > 0:
        return False
    if session_complete_writes > 0:
        return False
    tc = tool_calls or ()
    return not any(is_subagent_spawn_call(c) for c in tc if isinstance(c, dict))


def check_ds26_mechanical_gate(
    subagent_output: str,
    *,
    client: Optional[DirectusAdminClient] = None,
    assistant_turns: Optional[Sequence[str]] = None,
    tool_calls: Optional[Sequence[dict[str, Any]]] = None,
    candidate_handoffs: int = 1,
    session_complete_writes: int = 0,
    handoff_gate_count: Optional[int] = None,
    handoff_path: Optional[str] = None,
    prior_handoff_path: Optional[str] = None,
    handoff_template_path: Optional[str] = None,
    forbid_complete_writes_when_halted: bool = False,
    session_window_writes: Any = None,
    text_presence_check: Callable[[str, Sequence[str]], bool] = default_text_presence_check,
    activity_log_cites_gate: Callable[[dict[str, Any], Any], bool] = default_activity_log_cites_gate,
    halt_row_cites_gate: Callable[[dict[str, Any], Any], bool] = default_halt_row_cites_gate,
) -> Ds26GateCheckResult:
    """
    Stop-hook entry: scan for declaration, require N checklist evidence rows, verify each.

    When ``candidate_handoffs == 0`` and no spawn tools / complete writes, returns SILENT_SKIP.
    """
    failures: list[str] = []
    checklist: list[str] = []
    warnings: list[str] = []
    handoff_fmt: Optional[str] = None

    if should_skip_false_positive_guard(
        candidate_handoffs=candidate_handoffs,
        tool_calls=tool_calls,
        session_complete_writes=session_complete_writes,
    ):
        return Ds26GateCheckResult(
            verdict="SILENT_SKIP",
            declaration_count=None,
            expected_gate_indices=[],
            evidence_entries_parsed={},
        )

    if handoff_path is None and _HANDOFF_REF_RE.search(subagent_output):
        warnings.append("HANDOFF_REFERENCE_MISSING_ARG")

    hp = None
    if handoff_path:
        try:
            hp = parse_handoff(handoff_path)
        except LegacyHandoffNotSupported as exc:
            checklist.append(f"UNVERIFIED reason=legacy_handoff_unsupported detail={exc}")
            return Ds26GateCheckResult(
                verdict="FAIL",
                declaration_count=parse_declaration_count(subagent_output),
                expected_gate_indices=[],
                evidence_entries_parsed=extract_gate_evidence_map(subagent_output)
                if parse_declaration_count(subagent_output)
                else {},
                failures=["legacy_handoff_unsupported"],
                surface_checklist=checklist,
                warnings=warnings,
            )
        handoff_fmt = hp.handoff_format_version

        if prior_handoff_path:
            try:
                prior_hp = parse_handoff(prior_handoff_path)
            except LegacyHandoffNotSupported as exc:
                checklist.append(f"UNVERIFIED reason=legacy_handoff_unsupported prior detail={exc}")
                return Ds26GateCheckResult(
                    verdict="FAIL",
                    declaration_count=None,
                    expected_gate_indices=[],
                    evidence_entries_parsed={},
                    failures=["legacy_handoff_unsupported"],
                    surface_checklist=checklist,
                    warnings=warnings,
                    handoff_format_version=handoff_fmt,
                )
            dual = compare_handoffs(hp, prior_hp)
            if dual.gate_count_drift:
                decl_d = parse_declaration_count(subagent_output)
                return Ds26GateCheckResult(
                    verdict="FAIL",
                    declaration_count=decl_d,
                    expected_gate_indices=list(range(1, decl_d + 1)) if decl_d is not None else [],
                    evidence_entries_parsed=extract_gate_evidence_map(subagent_output)
                    if decl_d is not None
                    else {},
                    failures=["HANDOFF_GATE_COUNT_DRIFT"],
                    surface_checklist=checklist,
                    warnings=warnings,
                    handoff_format_version=handoff_fmt,
                )

        if handoff_template_path:
            comp = compare_handoff_to_template(hp, handoff_template_path)
            if not comp.matches_template:
                decl_t = parse_declaration_count(subagent_output)
                return Ds26GateCheckResult(
                    verdict="FAIL",
                    declaration_count=decl_t,
                    expected_gate_indices=list(range(1, decl_t + 1)) if decl_t is not None else [],
                    evidence_entries_parsed=extract_gate_evidence_map(subagent_output)
                    if decl_t is not None
                    else {},
                    failures=["HANDOFF_TEMPLATE_GATE_COUNT_MISMATCH"],
                    surface_checklist=checklist,
                    warnings=warnings,
                    handoff_format_version=handoff_fmt,
                )

    effective_handoff_count: Optional[int] = handoff_gate_count
    if hp is not None and hp.declared_gate_count is not None:
        effective_handoff_count = hp.declared_gate_count

    turns: Sequence[str] = assistant_turns if assistant_turns is not None else (subagent_output,)

    declared = parse_declaration_count(subagent_output)
    if declared is None:
        return Ds26GateCheckResult(
            verdict="FAIL",
            declaration_count=None,
            expected_gate_indices=[],
            evidence_entries_parsed={},
            failures=["MISSING_DECLARATION"],
            surface_checklist=checklist,
            warnings=warnings,
            handoff_format_version=handoff_fmt,
        )

    if effective_handoff_count is not None and declared != effective_handoff_count:
        return Ds26GateCheckResult(
            verdict="FAIL",
            declaration_count=declared,
            expected_gate_indices=list(range(1, declared + 1)),
            evidence_entries_parsed=extract_gate_evidence_map(subagent_output),
            failures=["COUNT_MISMATCH"],
            surface_checklist=checklist,
            warnings=warnings,
            handoff_format_version=handoff_fmt,
        )

    met_pair = parse_met_not_met(subagent_output)
    evidence_map = extract_gate_evidence_map(subagent_output)

    if declared == 0:
        if evidence_map:
            failures.append("EVIDENCE_UNEXPECTED_FOR_ZERO_GATES")
        return Ds26GateCheckResult(
            verdict="FAIL" if failures else "PASS",
            declaration_count=0,
            expected_gate_indices=[],
            evidence_entries_parsed=evidence_map,
            failures=failures,
            surface_checklist=checklist,
            met_not_met=met_pair,
            warnings=warnings,
            handoff_format_version=handoff_fmt,
        )

    expected_indices = list(range(1, declared + 1))
    for idx in expected_indices:
        if idx not in evidence_map:
            failures.append(f"EVIDENCE_MISSING_FOR_GATE_{idx}")

    if len(evidence_map) < declared:
        return Ds26GateCheckResult(
            verdict="FAIL",
            declaration_count=declared,
            expected_gate_indices=expected_indices,
            evidence_entries_parsed=evidence_map,
            failures=failures,
            surface_checklist=checklist,
            met_not_met=met_pair,
            warnings=warnings,
            handoff_format_version=handoff_fmt,
        )

    all_ok = True
    for idx in expected_indices:
        ev = evidence_map[idx]
        pg = {"evidence_source": ev, "gate_index": idx}
        checklist_before = len(checklist)
        ok = verify_gate_evidence(
            pg,
            client,
            checklist,
            assistant_turns=turns,
            text_presence_check=text_presence_check,
            activity_log_cites_gate=activity_log_cites_gate,
            halt_row_cites_gate=halt_row_cites_gate,
            session_window_writes=session_window_writes,
        )
        if not ok:
            all_ok = False
            new_items = checklist[checklist_before:]
            if any("UNVERIFIED_DIRECTUS_REF" in x for x in new_items):
                failures.append(f"UNVERIFIED_DIRECTUS_REF_GATE_{idx}")
            elif BROAD_DIRECTUS_HINT_RE.search(ev):
                failures.append(f"FAIL_EVIDENCE_MISSING_FOR_GATE_{idx}")
            else:
                failures.append(f"TEXT_EVIDENCE_NOT_FOUND_FOR_GATE_{idx}")

    if forbid_complete_writes_when_halted and met_pair is not None:
        _met, not_met = met_pair
        if not_met > 0 and _HALTED_SENTINEL_RE.search(subagent_output):
            if session_complete_writes > 0:
                failures.append("HALT_DECLARED_BUT_PROCEEDED")
                all_ok = False

    verdict: Verdict = "PASS" if all_ok and not failures else "FAIL"
    return Ds26GateCheckResult(
        verdict=verdict,
        declaration_count=declared,
        expected_gate_indices=expected_indices,
        evidence_entries_parsed=evidence_map,
        failures=sorted(set(failures)),
        surface_checklist=checklist,
        met_not_met=met_pair,
        warnings=warnings,
        handoff_format_version=handoff_fmt,
    )


def run_ds26_gate_check(
    subagent_output: str,
    *,
    client: Optional[DirectusAdminClient] = None,
    **kwargs: Any,
) -> Ds26GateCheckResult:
    """Public alias for hook wiring — forwards to :func:`check_ds26_mechanical_gate`."""
    return check_ds26_mechanical_gate(subagent_output, client=client, **kwargs)
