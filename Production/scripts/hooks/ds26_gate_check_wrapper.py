"""
DS-26 mechanical gate check + prod_activity_log row (LD-597 + Rule 35).

Posts only LD-597-allowed top-level fields; verifies persistence via get_item.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, Optional

_PRODUCTION_ROOT = Path(__file__).resolve().parents[2]
if str(_PRODUCTION_ROOT) not in sys.path:
    sys.path.insert(0, str(_PRODUCTION_ROOT))

from lib.directus_admin_client import DirectusAdminClient

from scripts.hooks.ds26_gate_check import Ds26GateCheckResult, check_ds26_mechanical_gate

_ACTIVITY_FORBIDDEN_TOP_LEVEL = frozenset(
    {
        "task_description",
        "metadata",
        "task_id",
        "status",
        "timestamp",
        "task_name",
    }
)


class Rule35ReadBackFailure(Exception):
    """POST succeeded but read-back did not match the written payload (Rule 35)."""


def _gate_verification_counts(
    result: Ds26GateCheckResult,
) -> tuple[int, int, int, list[str]]:
    """Return (gates_declared, gates_verified, gates_unverified, unverified_refs)."""
    d = result.declaration_count or 0
    unverified_refs = [x for x in result.surface_checklist if "UNVERIFIED_DIRECTUS_REF" in x]
    if result.verdict == "PASS":
        return d, d, 0, unverified_refs
    if result.verdict == "SILENT_SKIP":
        return 0, 0, 0, unverified_refs

    failed_gates: set[int] = set()
    for f in result.failures:
        m = re.search(r"GATE_(\d+)", f)
        if m:
            failed_gates.add(int(m.group(1)))

    if failed_gates:
        gu = len(failed_gates)
    else:
        gu = d if d else 1
    gv = max(0, d - gu)
    return d, gv, gu, unverified_refs


def _normalize_activity_row(row: Any) -> dict[str, Any]:
    if not isinstance(row, dict):
        return {}
    return {
        "action": row.get("action"),
        "details": row.get("details"),
        "performed_by": row.get("performed_by"),
        "module_id": row.get("module_id"),
    }


def run_ds26_gate_check_with_activity_log(
    session_output: str,
    *,
    client: DirectusAdminClient,
    session_id: str,
    handoff_path: Optional[str] = None,
    performed_by: str = "ds26_gate_check_wrapper",
    module_id: str = "ds26",
    **gate_kwargs: Any,
) -> dict[str, Any]:
    """
    Run :func:`check_ds26_mechanical_gate`, POST ``prod_activity_log``, read back (Rule 35).

    Returns a wrapper result dict with keys: ``gate_result``, ``activity_log_id``, ``posted_row``.
    """
    gate_result = check_ds26_mechanical_gate(
        session_output,
        client=client,
        handoff_path=handoff_path,
        **gate_kwargs,
    )

    gd, gv, gu, unverified_refs = _gate_verification_counts(gate_result)
    details: dict[str, Any] = {
        "verdict": gate_result.verdict,
        "gates_declared": gd,
        "gates_verified": gv,
        "gates_unverified": gu,
        "unverified_refs": unverified_refs,
        "handoff_format_version": gate_result.handoff_format_version,
        "session_id": session_id,
    }

    payload: dict[str, Any] = {
        "action": "DS_26_GATE_CHECK_RESULT",
        "details": details,
        "performed_by": performed_by,
        "module_id": module_id,
    }

    bad = _ACTIVITY_FORBIDDEN_TOP_LEVEL.intersection(payload.keys())
    if bad:
        raise ValueError(f"LD-597 violation: forbidden keys in activity payload: {sorted(bad)}")

    created = client.post_item("prod_activity_log", payload)
    if not isinstance(created, dict) or "id" not in created:
        raise Rule35ReadBackFailure(f"unexpected post_item response shape: {created!r}")

    new_id = created["id"]
    read_row = client.get_item("prod_activity_log", new_id)

    posted_norm = _normalize_activity_row(payload)
    read_norm = _normalize_activity_row(read_row)
    if posted_norm != read_norm:
        raise Rule35ReadBackFailure(f"read-back mismatch posted={posted_norm!r} read={read_norm!r}")

    return {
        "gate_result": gate_result,
        "activity_log_id": new_id,
        "posted_row": payload,
    }
