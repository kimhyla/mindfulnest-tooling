#!/usr/bin/env python3
"""
Schema Vocab Migration v3 implementation script (handoff v2.5 / spec v9).

Spec authority (v9 sha256 0f5bbf0554e40e56c035e6a9c0bdd6871af4256a06795b06139640293143a894):
    Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v9.md
Handoff authority (v2.5):
    Production/docs/HANDOFF_SCHEMA_MIGRATION_V3_IMPLEMENTATION_20260508.md

LDs in flight: 586, 588, 590, 591, 592, 593, 595, 596, 597, 598, 601, 602,
611 (v8 amendment), and v9-self LD SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V9_SCRIPT_DOC_SYNC_V1.

Subcommands:
    phase-0          Run Phase 0 (Steps 0/0.4/0.5/1/2/3): canonical root
                     assert + cached export + snapshot + dry-run + rollback
                     rehearsal + Phase 0 marker.
    phase-1          Run Phase 1 (Rule 4 scope_domain remap, ~35 rows).
    phase-2          Run Phase 2 (Rule 2 severity lowercase -> UPPER, ~37
                     rows).
    phase-3          Run Phase 3 admin-UI mechanical detection.
    phase-4          Run Phase 4 (Rule 3b task_category synonym remap,
                     ~56 rows; INVESTIGATE-class rows excluded from
                     auto-PATCH per spec §3.3).
    phase-5          Phase 5 attempt (gated on PHASE_5_ENABLED env var).
    phase-6          Phase 6 final audit + mutex release.
    all              Run 0->1->2->3->4->5->6 in dependency order.
    dry-run-only     Run Phase 0 Steps 0/0.4/1/2 (skips 0.5 rehearsal +
                     Phase 0 marker). Used by the through-Phase-F session
                     scope per the implementation handoff (Kim direction
                     2026-05-08: HALT before Phase G rehearsal).

Operational discipline (verbatim from handoff):
    - Rule 35 read-back-after-write on every Directus PATCH/POST.
    - Rule 24 confidence tags throughout activity-log details payloads.
    - DS-8 try_post_or_queue for every write so Directus offline is
      tolerated.
    - LD-597 anti-confusion: do NOT include task_description in any
      prod_activity_log payload.
    - Spec v9 §9.4 (preserves v7 verbatim) JSON-string-aware state-machine
      extractor for any prod_blockers STRUCTURED_DETAILS_JSON parsing.
    - Spec v9 §6 Gate 11.2 runtime payload-key validator before every
      prod_blockers POST/PATCH.
    - Spec v9 §3 + §4 + cleanup-report mapping tables for Rules 1/2/3b/4.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
import random
import socket
import sys
import time
from pathlib import Path
from typing import Any, Optional

# Allow `python3 Production/scripts/migrate_schema_vocab_v1.py ...` from the
# canonical root without needing a PYTHONPATH gymnastics step.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from Production.lib.directus import try_post_or_queue  # noqa: E402
from Production.lib.directus_admin_client import (  # noqa: E402
    DirectusAdminClient,
    DirectusAdminError,
)

# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------

CANONICAL_ROOT_DROPBOX = (
    "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files"
)
CANONICAL_ROOT_PROJECTS = "/Users/kimberlysmith/Projects"

# v9 update 2026-05-09 per LD-NEW (this session;
# SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V9_SCRIPT_DOC_SYNC_V1); rule_4 EXPECTED
# 29->35 reconciles dry-run actuals; SCRIPT_VERSION v7->v9; SPEC_V7_* renamed
# SPEC_V9_*. Script-doc sync per Cursor's v8 review HIGH 2 finding (script
# was citing v7 constants while v8 doc was authoritative).
SCRIPT_VERSION = "migrate_schema_vocab_v1.py@2026-05-09-v9"
SPEC_V9_SHA256 = (
    "0f5bbf0554e40e56c035e6a9c0bdd6871af4256a06795b06139640293143a894"
)
HANDOFF_PATH = (
    f"{CANONICAL_ROOT_DROPBOX}/Production/docs/"
    "HANDOFF_SCHEMA_MIGRATION_V3_IMPLEMENTATION_20260508.md"
)
SPEC_V9_PATH = (
    f"{CANONICAL_ROOT_DROPBOX}/Production/docs/"
    "SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v9.md"
)

# Backwards-compat aliases for existing references in this file (sidecar
# JSON keys, dry-run report banner, activity-log spec_version). Removing the
# legacy names entirely would touch ~6 unrelated sites; aliasing keeps the
# v9 update surgically minimal while pointing all references at v9 values.
# Future v10+ pass can fully rename if Kim authorizes a wider sweep.
SPEC_V7_SHA256 = SPEC_V9_SHA256
SPEC_V7_PATH = SPEC_V9_PATH

EXPORT_DIR = Path(CANONICAL_ROOT_DROPBOX) / "Production/exports"
DOCS_DIR = Path(CANONICAL_ROOT_DROPBOX) / "Production/docs"
LOCAL_LOCK_PATH = Path.home() / ".claude/mindfulnest-cache/schema_vocab_migration.lock"

DRIFT_THRESHOLD_PCT = 25  # mechanical halt #2 threshold; v1 heuristic

EXPECTED_ROW_COUNTS: dict[str, int] = {
    "rule_1_severity_high_critical_to_hard": 320,
    "rule_2_severity_lowercase_to_upper": 37,
    # Rule 3b: spec §4's ~110 estimate conflated synonyms (mechanically
    # remappable) with INVESTIGATE-class (per-row Kim triage per spec §3.3
    # verdict; NOT auto-PATCHed). Per Kim's authorization 2026-05-09 (drift
    # halt #1 resolution dialog), the script's 56-row mechanical-only
    # expectation is correct; INVESTIGATE-class stays in the dry-run
    # triage queue.
    "rule_3b_task_category_remap": 56,
    # v9 update 2026-05-09 per LD-NEW (this session); 29->35 reconciles
    # dry-run actuals; spec v8 §3.4 + v9 §4 dual-baseline table authoritative;
    # see LD-611 (v8 amendment) + LD-NEW v9 (this session script-doc sync).
    "rule_4_scope_domain_remap": 35,
}

# Phase K — the 7 task_category enum values that Phase 3 admin-UI work adds
# to prod_locked_decisions.task_category. F3-fix per LD-602: this list is the
# AUTHORITATIVE one (matches Phase K body in the handoff). The earlier wrong
# list (ci_cd / schema / production / tooling) did NOT exist in the live
# schema and was a documentation defect.
REQUIRED_TASK_CATEGORY_VALUES_PHASE_3: set[str] = {
    "app_architecture",
    "infrastructure",
    "security",
    "governance",
    "production_tool_ui",
    "data_model",
    "visual_production",
}

# Pre-filed canonical Phase 3 row id (filed 2026-05-08, severity=high
# lowercase). Phase K hit-path idempotently auto-resolves; miss-path
# references this id verbatim and does NOT autofile a duplicate.
PHASE_3_BLOCKER_ID = 101

# Spec v7 §6 Gate 11.2 — runtime validator constants.
ALLOWED_PROD_BLOCKERS_KEYS: set[str] = {
    "id",
    "module_id",
    "severity",
    "title",
    "description",
    "is_resolved",
    "created_at",
    "resolved_at",
}

# Spec v7 §9.4 + LD-596 non-blocker E — resolution-text append cap on
# prod_blockers.description on release PATCH.
RESOLUTION_APPEND_MAX_CHARS = 256

# Spec v7 §9.4 + LD-596 non-blocker E — acquisition payload schema version.
PAYLOAD_SCHEMA_VERSION = "v1"

# Rule 4 (Phase 1) — scope_domain remap mapping per spec v2 §3.4 / cleanup
# report §1.3. The 29-row baseline; live drift may add a few rows beyond
# this set; the loop iterates on whatever is non-canonical at runtime.
RULE_4_CANONICAL_SCOPE_DOMAINS: set[str] = {
    "content",
    "production",
    "app-dev",
    "infra",
    "cross-cutting",
}
RULE_4_SCOPE_DOMAIN_REMAP: dict[str, str] = {
    "app": "app-dev",
    "infrastructure": "infra",
    "stillgen": "production",
    "governance": "cross-cutting",
    "video_pipeline": "production",
    "audio_pipeline": "production",
    "image_pipeline": "production",
    "ci_pipeline": "infra",
    "claude_session_behavior": "cross-cutting",
    "payments": "app-dev",
    "beat_generator": "production",
    # Drift observed live 2026-05-08 (not in spec table; mapped by Phase F
    # extension based on cleanup-report semantics). Flagged as
    # "spec-extension" in the dry-run report per Kim's authorization
    # 2026-05-09 (Rule 4 drift extensions dialog).
    "production-server": "infra",
    "production_pipeline": "production",
    "audio_production": "production",
}

# Keys NOT in the verbatim spec §3.4 mapping table — added based on live
# observation. Flagged in dry-run report as "spec-extension".
RULE_4_SPEC_EXTENSIONS: set[str] = {
    "production-server",
    "production_pipeline",
    "audio_production",
}

# Rule 2 (Phase 2) — severity lowercase -> UPPER mapping per spec v2 §3.2.
RULE_2_SEVERITY_LOWER_TO_UPPER: dict[str, str] = {
    "high": "HIGH",
    "medium": "MEDIUM",
    "low": "LOW",
    "critical": "CRITICAL",
    "MED": "MEDIUM",
}

# Rule 1 (Phase 5) — severity HIGH/CRITICAL -> HARD per spec v2 §3.1. NOT
# executed this session; gated on PHASE_5_ENABLED env var per spec §3.1.
RULE_1_SEVERITY_HIGH_CRITICAL_TO_HARD: dict[str, str] = {
    "HIGH": "HARD",
    "CRITICAL": "HARD",
}

# Rule 3b (Phase 4) — task_category synonym remap per spec v2 §3.3 table.
# Only maps that are pure synonyms (no per-row triage required). SPLIT and
# INVESTIGATE rows are NOT touched mechanically — flagged in dry-run for
# manual review per spec §3.3 verdict.
RULE_3B_TASK_CATEGORY_SYNONYM_REMAP: dict[str, str] = {
    "architectural": "app_architecture",
    "audio_production": "audio",
    "video_production": "video",
    "production_server_infrastructure": "infrastructure",
    "production_server": "infrastructure",
}

# Rule 3b INVESTIGATE-class values: NOT auto-PATCHed; surfaced in dry-run
# for Kim's manual triage per spec §3.3.
RULE_3B_INVESTIGATE_VALUES: set[str] = {
    "production_infrastructure",
    "production_pipeline",
    "tools",
    "feature",
}

# -----------------------------------------------------------------------------
# Spec v7 §9.4 — JSON-string-aware state-machine extractor (LD-598).
# Replaces v6's brace-counter (which mis-handled `}` inside JSON string
# values per Cursor AMEND_V3 Blocker F). DO NOT REPLACE WITH A SIMPLER
# IMPLEMENTATION — the state machine is correct by construction.
# -----------------------------------------------------------------------------


def extract_structured_payload(description: str) -> Optional[dict]:
    """v7 JSON-string-aware extractor. Returns None gracefully on parse
    failure (caller posts STALE_MUTEX_PARSE_FAILURE activity-log row per
    spec v7 §9.4).
    """
    marker = "STRUCTURED_DETAILS_JSON:"
    idx = description.find(marker)
    if idx == -1:
        return None
    start = description.find("{", idx)
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    end: Optional[int] = None
    for i in range(start, len(description)):
        ch = description[i]
        if escape:
            escape = False  # consume the escaped character regardless of value
            continue
        if ch == "\\":
            if in_string:
                escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if not in_string:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
    if end is None:
        return None
    try:
        return json.loads(description[start:end])
    except json.JSONDecodeError:
        return None


# -----------------------------------------------------------------------------
# Spec v7 §6 Gate 11.2 — runtime payload-key validator (LD-596).
# -----------------------------------------------------------------------------


def validate_prod_blockers_payload(payload: dict) -> None:
    """Reject any prod_blockers POST/PATCH payload whose keys leak outside
    the 8 live fields. Called immediately before every client.post_item /
    client.patch_item targeting prod_blockers. Bypasses are not possible at
    runtime regardless of how the payload dict was constructed (literal,
    computed key, helper wrapper, token concat).
    """
    extra = set(payload.keys()) - ALLOWED_PROD_BLOCKERS_KEYS
    if extra:
        raise RuntimeError(
            f"prod_blockers payload contains non-existent fields: {extra}. "
            f"Allowed keys: {sorted(ALLOWED_PROD_BLOCKERS_KEYS)}. "
            "See SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v7.md §9.4 + §6 Gate 11.2."
        )


# -----------------------------------------------------------------------------
# Activity-log helper — every write goes through try_post_or_queue per
# DS-8 + Rule 35. LD-597: no task_description; details is JSON dict.
# -----------------------------------------------------------------------------


def post_activity_log(
    action: str,
    details: dict,
    performed_by: str = "migrate_schema_vocab_v1.py",
) -> dict:
    """POST a prod_activity_log row via try_post_or_queue. Returns the
    Directus row dict on success or the offline-queue / silent-write
    sentinel on failure paths.
    """
    payload = {
        "action": action,
        "performed_by": performed_by,
        "details": details,
    }
    return try_post_or_queue("prod_activity_log", payload)


def _utcnow_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


# -----------------------------------------------------------------------------
# Phase C — Step 0: canonical-root assertion (DS-27 v2 dual-canonical).
# -----------------------------------------------------------------------------


def assert_canonical_root() -> None:
    """Halt if cwd is inside any .claude/worktrees/ tree, anchored elsewhere
    that does not match either canonical root, or the git root drifts from
    the cwd-anchor canonical root.
    """
    cwd = Path.cwd().resolve()
    cwd_str = str(cwd)
    if ".claude/worktrees/" in cwd_str:
        post_activity_log(
            "PHASE_0_BLOCKED_BY_WORKTREE_CONFUSION",
            {
                "cwd": cwd_str,
                "halt_reason": (
                    "DS-27 v2 dual-canonical hard rule: refuse to operate "
                    "inside a worktree subdirectory."
                ),
                "remediation": (
                    "Re-invoke from the canonical root: "
                    f"cd {CANONICAL_ROOT_DROPBOX!r}"
                ),
            },
        )
        sys.stderr.write(
            f"PHASE_0_BLOCKED_BY_WORKTREE_CONFUSION: cwd={cwd_str}\n"
            f"Re-invoke from {CANONICAL_ROOT_DROPBOX!r}.\n"
        )
        sys.exit(2)
    if not (
        cwd_str.startswith(CANONICAL_ROOT_DROPBOX)
        or cwd_str.startswith(CANONICAL_ROOT_PROJECTS)
    ):
        post_activity_log(
            "PHASE_0_BLOCKED_BY_NON_CANONICAL_ROOT",
            {
                "cwd": cwd_str,
                "expected_one_of": [
                    CANONICAL_ROOT_DROPBOX,
                    CANONICAL_ROOT_PROJECTS,
                ],
            },
        )
        sys.stderr.write(
            f"PHASE_0_BLOCKED_BY_NON_CANONICAL_ROOT: cwd={cwd_str}\n"
        )
        sys.exit(2)
    post_activity_log(
        "PHASE_0_STEP_0_CANONICAL_ROOT_OK",
        {"cwd": cwd_str, "spec_version": SPEC_V7_SHA256},
    )


# -----------------------------------------------------------------------------
# Phase D — Step 0.4: cached canonical-export.
# -----------------------------------------------------------------------------


def _today_compact() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d")


def _today_dashed() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")


def cached_export_paths() -> tuple[Path, Path]:
    """Return (jsonl_path, sidecar_path) for today's cached export.
    Uses dashed YYYY-MM-DD per existing convention so re-runs match the
    earlier same-day file.
    """
    date = _today_dashed()
    jsonl = EXPORT_DIR / f"prod_locked_decisions_{date}.jsonl"
    sidecar = EXPORT_DIR / f"prod_locked_decisions_{date}.metadata.json"
    return jsonl, sidecar


def compute_schema_hash(client: DirectusAdminClient) -> str:
    """SHA256 of the sorted field-name list for prod_locked_decisions."""
    field_meta = client.fields("prod_locked_decisions")
    names = sorted(f.get("field") for f in field_meta if f.get("field"))
    return hashlib.sha256(json.dumps(names).encode("utf-8")).hexdigest()


def write_cached_export(client: DirectusAdminClient) -> dict:
    """Generate Production/exports/prod_locked_decisions_<DATE>.jsonl + the
    metadata sidecar per spec v7 §4 v3 schema. RE-USE if existing export's
    row count + schema hash both match live; otherwise SUPERSEDE.
    """
    jsonl, sidecar = cached_export_paths()
    schema_hash = compute_schema_hash(client)
    rows = client.get_items(
        "prod_locked_decisions",
        filters={"status": {"_neq": "superseded"}},
        limit=-1,
    )

    # Re-use vs supersede decision per handoff §3.1 Phase D rule.
    reuse = False
    if jsonl.exists() and sidecar.exists():
        try:
            existing_meta = json.loads(sidecar.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing_meta = {}
        if (
            existing_meta.get("total_active_rows") == len(rows)
            and existing_meta.get("schema_hash") == schema_hash
        ):
            reuse = True

    if not reuse:
        # Supersede: write fresh JSONL + sidecar.
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        with jsonl.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        meta = {
            "export_version": "v3",
            "export_taken_at": _utcnow_iso(),
            "directus_url": (
                "https://directus-production-3460.up.railway.app"
            ),
            "total_active_rows": len(rows),
            "schema_hash": schema_hash,
            "deterministic_sample_method": "random.seed(42); random.sample",
            "intended_consumer": (
                "schema_vocab_migration_v3_implementation_phases_C_through_F"
            ),
            "spec_v7_sha256": SPEC_V7_SHA256,
            "spec_v7_path": SPEC_V7_PATH,
            "supersedes_prior_export": (
                str(jsonl) if jsonl.exists() else None
            ),
        }
        sidecar.write_text(
            json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    artifact = {
        "jsonl_path": str(jsonl),
        "sidecar_path": str(sidecar),
        "row_count": len(rows),
        "schema_hash": schema_hash,
        "reused": reuse,
    }
    post_activity_log(
        "SCHEMA_MIGRATION_V3_STEP_0_4_CACHED_EXPORT", artifact
    )
    return artifact


# -----------------------------------------------------------------------------
# Phase E — Step 1: row-restoration snapshot.
# -----------------------------------------------------------------------------


def _row_matches_rule_4(row: dict) -> bool:
    sd = row.get("scope_domain")
    return bool(sd) and sd not in RULE_4_CANONICAL_SCOPE_DOMAINS


def _row_matches_rule_2(row: dict) -> bool:
    sev = row.get("severity")
    return sev in RULE_2_SEVERITY_LOWER_TO_UPPER


def _row_matches_rule_1(row: dict) -> bool:
    sev = row.get("severity")
    return sev in RULE_1_SEVERITY_HIGH_CRITICAL_TO_HARD


def _row_matches_rule_3b(row: dict) -> bool:
    tc = row.get("task_category")
    return tc in RULE_3B_TASK_CATEGORY_SYNONYM_REMAP


def write_snapshot(rows: list[dict]) -> dict:
    """Snapshot every row any rule plans to touch. Per-rule target-id sets
    + invariants + snapshot_hash."""
    rule_4_ids = sorted(r["id"] for r in rows if _row_matches_rule_4(r))
    rule_2_ids = sorted(r["id"] for r in rows if _row_matches_rule_2(r))
    rule_1_ids = sorted(r["id"] for r in rows if _row_matches_rule_1(r))
    rule_3b_ids = sorted(r["id"] for r in rows if _row_matches_rule_3b(r))

    # Union of all touched ids across Phases 1+2+3b+5 (Phase 3a is schema
    # change, no row mutations).
    union_ids = sorted(set(rule_4_ids) | set(rule_2_ids) | set(rule_3b_ids) | set(rule_1_ids))
    by_id = {r["id"]: r for r in rows}
    touched_rows = [by_id[i] for i in union_ids if i in by_id]

    date = _today_compact()
    snapshot_path = DOCS_DIR / f"SCHEMA_VOCAB_MIGRATION_SNAPSHOT_{date}.jsonl"
    sidecar_path = (
        DOCS_DIR / f"SCHEMA_VOCAB_MIGRATION_SNAPSHOT_{date}.metadata.json"
    )

    with snapshot_path.open("w", encoding="utf-8") as f:
        for r in touched_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())

    invariants = {
        "snapshot_version": "v3",
        "snapshot_taken_at": _utcnow_iso(),
        "row_count": len(touched_rows),
        "id_uniqueness": len(set(union_ids)) == len(union_ids),
        "all_touched_ids_present": (
            sorted({r["id"] for r in touched_rows}) == union_ids
        ),
        "per_rule_target_ids": {
            "rule_1_severity_high_critical_to_hard": rule_1_ids,
            "rule_2_severity_lowercase_to_upper": rule_2_ids,
            "rule_3b_task_category_remap": rule_3b_ids,
            "rule_4_scope_domain_remap": rule_4_ids,
        },
        "spec_v7_sha256": SPEC_V7_SHA256,
        "spec_v7_path": SPEC_V7_PATH,
    }
    invariants["snapshot_hash"] = hashlib.sha256(
        json.dumps(invariants, sort_keys=True).encode("utf-8")
    ).hexdigest()

    sidecar_path.write_text(
        json.dumps(invariants, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    artifact = {
        "snapshot_path": str(snapshot_path),
        "sidecar_path": str(sidecar_path),
        "row_count": invariants["row_count"],
        "id_uniqueness": invariants["id_uniqueness"],
        "all_touched_ids_present": invariants["all_touched_ids_present"],
        "per_rule_target_counts": {
            k: len(v) for k, v in invariants["per_rule_target_ids"].items()
        },
        "snapshot_hash": invariants["snapshot_hash"],
    }
    post_activity_log("SCHEMA_MIGRATION_V3_STEP_1_SNAPSHOT_COMPLETE", artifact)
    return artifact


# -----------------------------------------------------------------------------
# Phase F — Step 2: dry-run report + drift check (mechanical halt #2).
# -----------------------------------------------------------------------------


def write_dry_run_report(rows: list[dict], snapshot_meta: dict) -> dict:
    """Render the dry-run report markdown, evaluate drift against
    EXPECTED_ROW_COUNTS, and fire mechanical halt #2 if any rule drifts
    over DRIFT_THRESHOLD_PCT.
    """
    rule_4_ids = snapshot_meta["per_rule_target_counts"][
        "rule_4_scope_domain_remap"
    ]
    rule_2_ids = snapshot_meta["per_rule_target_counts"][
        "rule_2_severity_lowercase_to_upper"
    ]
    rule_1_ids = snapshot_meta["per_rule_target_counts"][
        "rule_1_severity_high_critical_to_hard"
    ]
    rule_3b_ids = snapshot_meta["per_rule_target_counts"][
        "rule_3b_task_category_remap"
    ]

    actual_counts = {
        "rule_1_severity_high_critical_to_hard": rule_1_ids,
        "rule_2_severity_lowercase_to_upper": rule_2_ids,
        "rule_3b_task_category_remap": rule_3b_ids,
        "rule_4_scope_domain_remap": rule_4_ids,
    }

    drift = {}
    violating_rules = []
    for rule, expected in EXPECTED_ROW_COUNTS.items():
        actual = actual_counts.get(rule, 0)
        delta = actual - expected
        pct = abs(delta) / expected * 100 if expected else 0
        drift[rule] = {
            "expected": expected,
            "actual": actual,
            "delta": delta,
            "pct_drift": round(pct, 2),
        }
        if pct > DRIFT_THRESHOLD_PCT:
            violating_rules.append(rule)

    by_id = {r["id"]: r for r in rows}

    def sample(ids: list[int], k: int = 5) -> list[dict]:
        random.seed(42)
        chosen = random.sample(ids, min(k, len(ids))) if ids else []
        return [
            {
                "id": i,
                "decision_key": by_id.get(i, {}).get("decision_key"),
                "severity": by_id.get(i, {}).get("severity"),
                "scope_domain": by_id.get(i, {}).get("scope_domain"),
                "task_category": by_id.get(i, {}).get("task_category"),
            }
            for i in chosen
        ]

    # Resolve target-ids per rule from the snapshot's per_rule_target_ids
    # (cached in invariants metadata if exposed; we re-derive here from rows).
    rule_4_target_ids = sorted(r["id"] for r in rows if _row_matches_rule_4(r))
    rule_2_target_ids = sorted(r["id"] for r in rows if _row_matches_rule_2(r))
    rule_1_target_ids = sorted(r["id"] for r in rows if _row_matches_rule_1(r))
    rule_3b_target_ids = sorted(
        r["id"] for r in rows if _row_matches_rule_3b(r)
    )

    samples = {
        "rule_1": sample(rule_1_target_ids),
        "rule_2": sample(rule_2_target_ids),
        "rule_3b": sample(rule_3b_target_ids),
        "rule_4": sample(rule_4_target_ids),
    }

    # INVESTIGATE-class task_category values present live (Rule 3b triage).
    investigate_present: dict[str, int] = {}
    for r in rows:
        tc = r.get("task_category")
        if tc in RULE_3B_INVESTIGATE_VALUES:
            investigate_present[tc] = investigate_present.get(tc, 0) + 1

    date = _today_compact()
    report_path = DOCS_DIR / f"SCHEMA_VOCAB_MIGRATION_DRY_RUN_{date}.md"

    lines: list[str] = []
    lines.append(f"# Schema Vocab Migration — Dry-Run Report ({date})")
    lines.append("")
    lines.append(f"- Spec authority: v7 sha256 `{SPEC_V7_SHA256}`")
    lines.append(f"- Handoff: `{HANDOFF_PATH}`")
    lines.append(f"- Snapshot: `{snapshot_meta['snapshot_path']}`")
    lines.append(
        f"- Snapshot hash: `{snapshot_meta['snapshot_hash']}`"
    )
    lines.append(f"- Total touched rows (union): {snapshot_meta['row_count']}")
    lines.append("")
    lines.append("## §1 — Drift evaluation (mechanical halt #2 threshold)")
    lines.append("")
    lines.append("| Rule | Expected | Actual | Delta | %drift | <=25%? |")
    lines.append("|---|---|---|---|---|---|")
    for rule, d in drift.items():
        ok = "OK" if d["pct_drift"] <= DRIFT_THRESHOLD_PCT else "**DRIFT**"
        lines.append(
            f"| {rule} | {d['expected']} | {d['actual']} | "
            f"{d['delta']:+d} | {d['pct_drift']}% | {ok} |"
        )
    lines.append("")
    if violating_rules:
        lines.append(
            f"### MECHANICAL HALT #2 FIRED — drift > {DRIFT_THRESHOLD_PCT}%"
        )
        lines.append("")
        for r in violating_rules:
            lines.append(f"- {r}: {drift[r]}")
        lines.append("")
    else:
        lines.append(f"All rules within {DRIFT_THRESHOLD_PCT}% drift threshold. No halt fires.")
        lines.append("")

    lines.append("## §2 — Sample of 5 ids per rule (deterministic seed=42)")
    lines.append("")
    for rule_label, items in samples.items():
        lines.append(f"### {rule_label}")
        if not items:
            lines.append("(no target rows)")
            lines.append("")
            continue
        lines.append("| id | decision_key | severity | scope_domain | task_category |")
        lines.append("|---|---|---|---|---|")
        for it in items:
            lines.append(
                f"| {it['id']} | {it['decision_key']} | "
                f"{it['severity']} | {it['scope_domain']} | "
                f"{it['task_category']} |"
            )
        lines.append("")

    lines.append("## §3 — Rule-3b INVESTIGATE-class triage queue")
    lines.append("")
    if investigate_present:
        lines.append(
            "These task_category values are present live but require "
            "per-row Kim triage per spec §3.3 verdict — NOT auto-PATCHed:"
        )
        for tc, n in sorted(investigate_present.items()):
            lines.append(f"- `{tc}`: {n} row(s)")
    else:
        lines.append("(none present live)")
    lines.append("")

    lines.append("## §4 — Computed target-value mappings")
    lines.append("")
    lines.append("### Rule 4 (scope_domain remap)")
    lines.append("")
    lines.append("| Old | New | Live count touched | Origin |")
    lines.append("|---|---|---|---|")
    rule_4_observed: dict[str, int] = {}
    for r in rows:
        if _row_matches_rule_4(r):
            rule_4_observed[r["scope_domain"]] = (
                rule_4_observed.get(r["scope_domain"], 0) + 1
            )
    for old, count in sorted(rule_4_observed.items()):
        new = RULE_4_SCOPE_DOMAIN_REMAP.get(old, "(no mapping — manual review)")
        origin = (
            "spec-extension (Kim 2026-05-09)"
            if old in RULE_4_SPEC_EXTENSIONS
            else "spec §3.4"
        )
        lines.append(f"| {old} | {new} | {count} | {origin} |")
    lines.append("")

    lines.append("### Rule 2 (severity lowercase -> UPPER)")
    lines.append("")
    lines.append("| Old | New | Live count touched |")
    lines.append("|---|---|---|")
    rule_2_observed: dict[str, int] = {}
    for r in rows:
        if _row_matches_rule_2(r):
            rule_2_observed[r["severity"]] = (
                rule_2_observed.get(r["severity"], 0) + 1
            )
    for old, count in sorted(rule_2_observed.items()):
        new = RULE_2_SEVERITY_LOWER_TO_UPPER.get(old, "(no mapping — manual review)")
        lines.append(f"| {old} | {new} | {count} |")
    lines.append("")

    lines.append("### Rule 3b (task_category synonym remap)")
    lines.append("")
    lines.append("| Old | New | Live count touched |")
    lines.append("|---|---|---|")
    rule_3b_observed: dict[str, int] = {}
    for r in rows:
        if _row_matches_rule_3b(r):
            rule_3b_observed[r["task_category"]] = (
                rule_3b_observed.get(r["task_category"], 0) + 1
            )
    for old, count in sorted(rule_3b_observed.items()):
        new = RULE_3B_TASK_CATEGORY_SYNONYM_REMAP.get(old, "(no mapping)")
        lines.append(f"| {old} | {new} | {count} |")
    lines.append("")

    lines.append("### Rule 1 (severity HIGH/CRITICAL -> HARD)")
    lines.append("")
    lines.append("(Phase 5 deferred this session per spec §3.1; no PATCHes.)")
    lines.append("")
    lines.append("| Old | New | Live count touched |")
    lines.append("|---|---|---|")
    rule_1_observed: dict[str, int] = {}
    for r in rows:
        if _row_matches_rule_1(r):
            rule_1_observed[r["severity"]] = (
                rule_1_observed.get(r["severity"], 0) + 1
            )
    for old, count in sorted(rule_1_observed.items()):
        lines.append(
            f"| {old} | {RULE_1_SEVERITY_HIGH_CRITICAL_TO_HARD[old]} | {count} |"
        )
    lines.append("")

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    artifact = {
        "report_path": str(report_path),
        "drift": drift,
        "violating_rules": violating_rules,
        "investigate_present": investigate_present,
        "rule_4_observed": rule_4_observed,
        "rule_2_observed": rule_2_observed,
        "rule_3b_observed": rule_3b_observed,
        "rule_1_observed": rule_1_observed,
    }

    if violating_rules:
        # mechanical halt #2 — autofile prod_blockers + activity-log + exit.
        autofile_payload = {
            "title": f"SCHEMA_VOCAB_MIGRATION_DRIFT_{date}",
            "severity": "high",  # lowercase per LD-593
            "is_resolved": False,
            "description": (
                f"Mechanical halt #2 — drift > {DRIFT_THRESHOLD_PCT}% for "
                f"rules: {violating_rules}.\n\n"
                f"STRUCTURED_DETAILS_JSON: "
                + json.dumps(
                    {
                        "schema_version": PAYLOAD_SCHEMA_VERSION,
                        "per_rule_expected_vs_actual": drift,
                        "threshold_pct": DRIFT_THRESHOLD_PCT,
                        "violating_rules": violating_rules,
                        "report_path": str(report_path),
                    }
                )
            ),
        }
        validate_prod_blockers_payload(autofile_payload)
        try_post_or_queue("prod_blockers", autofile_payload)
        post_activity_log(
            "PHASE_0_BLOCKED_BY_DRIFT",
            {
                "drift": drift,
                "violating_rules": violating_rules,
                "report_path": str(report_path),
            },
        )
        sys.stderr.write(
            f"PHASE_0_BLOCKED_BY_DRIFT: {violating_rules} | report: {report_path}\n"
        )
        sys.exit(2)

    post_activity_log(
        "SCHEMA_MIGRATION_V3_STEP_2_DRY_RUN_COMPLETE", artifact
    )
    return artifact


# -----------------------------------------------------------------------------
# Phase G — Step 0.5: rollback rehearsal (mechanical halt #1).
# -----------------------------------------------------------------------------


def _compute_target_for_row(row: dict) -> tuple[Optional[str], Optional[str]]:
    """Return (field, target_value) for the row's applicable rule. None if
    no rule applies (defensive — caller should pre-filter).
    """
    sev = row.get("severity")
    sd = row.get("scope_domain")
    tc = row.get("task_category")
    if sev in RULE_1_SEVERITY_HIGH_CRITICAL_TO_HARD:
        # Rule 1 (Phase 5) — only relevant in rehearsal if PHASE_5_ENABLED.
        # For pre-Phase-5 rehearsal we still PATCH+revert as the mechanic
        # is the same; this confirms the migration path is reversible.
        return "severity", RULE_1_SEVERITY_HIGH_CRITICAL_TO_HARD[sev]
    if sev in RULE_2_SEVERITY_LOWER_TO_UPPER:
        return "severity", RULE_2_SEVERITY_LOWER_TO_UPPER[sev]
    if tc in RULE_3B_TASK_CATEGORY_SYNONYM_REMAP:
        return "task_category", RULE_3B_TASK_CATEGORY_SYNONYM_REMAP[tc]
    if sd and sd not in RULE_4_CANONICAL_SCOPE_DOMAINS:
        return "scope_domain", RULE_4_SCOPE_DOMAIN_REMAP.get(sd, sd)
    return None, None


def rollback_rehearsal(client: DirectusAdminClient, snapshot_meta: dict) -> dict:
    """5-row deterministic rollback rehearsal (random.seed(42)). Each row:
    PATCH-to-target -> read-back-verify -> revert -> read-back-verify.
    Net effect on data: ZERO. mechanical halt #1 fires if any row fails.
    """
    # Combine all per-rule target ids from the snapshot.
    all_target_ids: list[int] = []
    for ids in snapshot_meta.get("per_rule_target_counts", {}).values():
        if isinstance(ids, list):
            all_target_ids.extend(ids)
    # Fallback: re-derive from snapshot file if per_rule_target_counts only
    # holds counts (current implementation). We compute deterministically.
    # The Phase E `write_snapshot` emits per_rule_target_ids only inside the
    # sidecar metadata file; load it here from the sidecar JSON so the
    # rehearsal is independent of in-memory state.
    sidecar_path = Path(snapshot_meta["sidecar_path"])
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    union: set[int] = set()
    for rule, ids in sidecar.get("per_rule_target_ids", {}).items():
        if isinstance(ids, list):
            union.update(int(i) for i in ids)
    sampled_ids = sorted(union)
    random.seed(42)
    sampled = random.sample(sampled_ids, min(5, len(sampled_ids))) if sampled_ids else []

    results: list[dict] = []
    for sid in sampled:
        row_result: dict[str, Any] = {"id": sid, "passed": False}
        try:
            pre = client.get_item("prod_locked_decisions", sid)
            field, target = _compute_target_for_row(pre)
            if field is None or target is None:
                row_result["error"] = "no rule applies"
                results.append(row_result)
                continue
            pre_value = pre.get(field)
            row_result.update(
                {"field": field, "pre": pre_value, "target": target}
            )
            # PATCH to target
            client.patch_item(
                "prod_locked_decisions", sid, {field: target}
            )
            intermediate = client.get_item("prod_locked_decisions", sid)
            if intermediate.get(field) != target:
                row_result["intermediate_mismatch"] = intermediate.get(field)
                results.append(row_result)
                continue
            # Revert
            client.patch_item(
                "prod_locked_decisions", sid, {field: pre_value}
            )
            post = client.get_item("prod_locked_decisions", sid)
            if post.get(field) != pre_value:
                row_result["post_mismatch"] = post.get(field)
                results.append(row_result)
                continue
            row_result["passed"] = True
        except DirectusAdminError as e:
            row_result["error"] = str(e)
        results.append(row_result)

    all_passed = bool(results) and all(r.get("passed") for r in results)
    date = _today_compact()
    report_path = (
        DOCS_DIR / f"SCHEMA_VOCAB_MIGRATION_ROLLBACK_REHEARSAL_{date}.md"
    )

    lines: list[str] = []
    lines.append(f"# Rollback Rehearsal Report ({date})")
    lines.append("")
    lines.append(f"All passed: **{all_passed}**")
    lines.append("")
    lines.append("| id | field | pre | target | passed |")
    lines.append("|---|---|---|---|---|")
    for r in results:
        lines.append(
            f"| {r.get('id')} | {r.get('field')} | "
            f"{r.get('pre')} | {r.get('target')} | "
            f"{'YES' if r.get('passed') else 'NO'} |"
        )
    lines.append("")
    lines.append("## Per-row detail")
    for r in results:
        lines.append(f"- {json.dumps(r, default=str)}")

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    artifact = {
        "report_path": str(report_path),
        "all_passed": all_passed,
        "sampled_ids": sampled,
        "rehearsal_results": results,
    }

    if not all_passed:
        post_activity_log(
            "PHASE_0_BLOCKED_BY_REHEARSAL_FAIL", artifact
        )
        sys.stderr.write(
            f"PHASE_0_BLOCKED_BY_REHEARSAL_FAIL: report: {report_path}\n"
        )
        sys.exit(2)

    post_activity_log(
        "SCHEMA_MIGRATION_V3_STEP_0_5_REHEARSAL_PASSED", artifact
    )
    return artifact


# -----------------------------------------------------------------------------
# Phase H — Step 3: Phase 0 marker.
# -----------------------------------------------------------------------------


def write_phase_0_marker(
    cached: dict, snapshot: dict, dry_run: dict, rehearsal: Optional[dict]
) -> dict:
    payload = {
        "cached_export": cached,
        "snapshot": snapshot,
        "dry_run": dry_run,
        "rehearsal": rehearsal,
    }
    return post_activity_log(
        "SCHEMA_VOCAB_MIGRATION_PHASE_0_COMPLETE", payload
    )


# -----------------------------------------------------------------------------
# §9.4 remote mutex helpers.
# -----------------------------------------------------------------------------


def _hostname() -> str:
    return socket.gethostname()


def acquire_remote_mutex(client: DirectusAdminClient) -> int:
    """Acquire the §9.4 remote mutex. Returns the row id on success;
    halts with PHASE_1_BLOCKED_BY_MUTEX_CONTENTION if another host holds.
    """
    host = _hostname()
    existing = client.get_items(
        "prod_blockers",
        filters={
            "is_resolved": {"_eq": False},
            "title": {"_starts_with": "SCHEMA_MIGRATION_LOCK_HELD_BY_"},
        },
    )
    for lock in existing:
        if lock.get("title") != f"SCHEMA_MIGRATION_LOCK_HELD_BY_{host}":
            post_activity_log(
                "PHASE_1_BLOCKED_BY_MUTEX_CONTENTION",
                {"contender_row": lock, "current_host": host},
            )
            sys.stderr.write(
                "PHASE_1_BLOCKED_BY_MUTEX_CONTENTION: another host holds "
                f"the migration mutex: {lock.get('title')}\n"
            )
            sys.exit(2)

    structured_payload = {
        "schema_version": PAYLOAD_SCHEMA_VERSION,
        "host": host,
        "pid": os.getpid(),
        "started_at": _utcnow_iso(),
        "script_version": SCRIPT_VERSION,
    }
    description_text = (
        f"Schema vocab migration in progress on host {host}; "
        f"PID={os.getpid()}.\n\n"
        f"STRUCTURED_DETAILS_JSON: {json.dumps(structured_payload)}"
    )
    acquisition_payload = {
        "title": f"SCHEMA_MIGRATION_LOCK_HELD_BY_{host}",
        "severity": "critical",  # lowercase per LD-593, Gate 11.1
        "is_resolved": False,
        "description": description_text,
    }
    validate_prod_blockers_payload(acquisition_payload)  # Gate 11.2
    result = try_post_or_queue("prod_blockers", acquisition_payload)
    if "id" not in result:
        sys.stderr.write(
            f"PHASE_1_BLOCKED_BY_MUTEX_POST_FAILED: {result}\n"
        )
        post_activity_log(
            "MUTEX_POST_HTTP_500_LIKELY_CASE_VIOLATION_OR_OFFLINE",
            {"acquisition_result": result},
        )
        sys.exit(2)
    return int(result["id"])


def release_remote_mutex(
    client: DirectusAdminClient, mutex_id: int, resolution_text: str
) -> dict:
    existing = client.get_item("prod_blockers", mutex_id)
    existing_description = existing.get("description", "") or ""
    suffix = f" | RESOLVED: {resolution_text}"
    if len(suffix) > RESOLUTION_APPEND_MAX_CHARS:
        suffix = (
            suffix[: RESOLUTION_APPEND_MAX_CHARS - len("[truncated]")]
            + "[truncated]"
        )
    new_description = f"{existing_description.rstrip()}{suffix}"
    patch_payload = {
        "is_resolved": True,
        "description": new_description,
        "resolved_at": _utcnow_iso(),
    }
    validate_prod_blockers_payload(patch_payload)  # Gate 11.2
    return client.patch_item("prod_blockers", mutex_id, patch_payload)


# -----------------------------------------------------------------------------
# Local lockfile (defense-in-depth).
# -----------------------------------------------------------------------------


def acquire_local_lock() -> int:
    LOCAL_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(LOCAL_LOCK_PATH), os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        post_activity_log(
            "PHASE_1_BLOCKED_BY_LOCAL_LOCK_CONTENTION",
            {"local_lock_path": str(LOCAL_LOCK_PATH)},
        )
        sys.stderr.write(
            "PHASE_1_BLOCKED_BY_LOCAL_LOCK_CONTENTION: another process holds "
            f"{LOCAL_LOCK_PATH}\n"
        )
        sys.exit(2)
    return fd


def release_local_lock(fd: int) -> None:
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
    try:
        LOCAL_LOCK_PATH.unlink()
    except FileNotFoundError:
        pass


# -----------------------------------------------------------------------------
# Checkpoint protocol (§5.0).
# -----------------------------------------------------------------------------


def _checkpoint_path() -> Path:
    date = _today_dashed()
    return EXPORT_DIR / f"schema_migration_checkpoint_{date}.jsonl"


def append_checkpoint(entry: dict) -> None:
    path = _checkpoint_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def read_last_committed(phase: int) -> int:
    path = _checkpoint_path()
    if not path.exists():
        return -1
    last = -1
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("phase") == phase:
                    rid = obj.get("last_committed_row_id")
                    if isinstance(rid, int) and rid > last:
                        last = rid
    except OSError:
        return -1
    return last


# -----------------------------------------------------------------------------
# Per-row PATCH loop helper for Phases I/J/L.
# -----------------------------------------------------------------------------


def execute_per_row_patch_loop(
    client: DirectusAdminClient,
    phase: int,
    rule_descriptor: str,
    target_field: str,
    rows: list[dict],
    target_value_fn,
    snapshot_hash: str,
    expected_count: int,
    activity_log_action: str,
) -> dict:
    """Generic per-row PATCH loop with read-back per Rule 35 + checkpoint
    append per §5.0. Halts mechanically on Directus offline or PATCH+
    read-back mismatch.
    """
    last_committed = read_last_committed(phase)
    rows_in_scope = [r for r in rows if r["id"] > last_committed]
    rows_processed = 0
    samples: list[dict] = []
    for row in rows_in_scope:
        rid = row["id"]
        pre_value = row.get(target_field)
        target = target_value_fn(row)
        if target is None or target == pre_value:
            continue
        try:
            client.patch_item(
                "prod_locked_decisions", rid, {target_field: target}
            )
            post = client.get_item("prod_locked_decisions", rid)
        except DirectusAdminError as e:
            post_activity_log(
                f"PHASE_{phase}_BLOCKED_BY_DIRECTUS_OFFLINE",
                {"row_id": rid, "error": str(e)},
            )
            sys.stderr.write(
                f"PHASE_{phase}_BLOCKED_BY_DIRECTUS_OFFLINE: id={rid} {e}\n"
            )
            sys.exit(2)
        if post.get(target_field) != target:
            post_activity_log(
                f"PHASE_{phase}_BLOCKED_BY_PATCH_VERIFY_FAIL",
                {
                    "row_id": rid,
                    "field": target_field,
                    "target": target,
                    "observed": post.get(target_field),
                },
            )
            sys.stderr.write(
                f"PHASE_{phase}_BLOCKED_BY_PATCH_VERIFY_FAIL: id={rid}\n"
            )
            sys.exit(2)
        post_activity_log(
            activity_log_action,
            {
                "row_id": rid,
                "field": target_field,
                "pre": pre_value,
                "post": target,
                "rule": rule_descriptor,
            },
        )
        append_checkpoint(
            {
                "phase": phase,
                "rule": rule_descriptor,
                "last_committed_row_id": rid,
                "timestamp": _utcnow_iso(),
                "snapshot_hash": snapshot_hash,
                "rows_processed_in_phase": rows_processed + 1,
                "expected_rows_in_phase": expected_count,
            }
        )
        rows_processed += 1
        if len(samples) < 5:
            samples.append(
                {
                    "id": rid,
                    "field": target_field,
                    "pre": pre_value,
                    "post": target,
                }
            )

    return {
        "phase": phase,
        "rule": rule_descriptor,
        "rows_processed": rows_processed,
        "expected": expected_count,
        "samples": samples,
    }


def write_phase_report(phase: int, rule: str, summary: dict) -> str:
    date = _today_compact()
    path = (
        DOCS_DIR / f"SCHEMA_VOCAB_MIGRATION_PHASE_{phase}_REPORT_{date}.md"
    )
    lines: list[str] = []
    lines.append(f"# Schema Vocab Migration — Phase {phase} Report ({date})")
    lines.append("")
    lines.append(f"- Rule: {rule}")
    lines.append(
        f"- Rows processed: {summary['rows_processed']} "
        f"(expected ~{summary['expected']})"
    )
    lines.append("")
    lines.append("## Sample (first 5 PATCHes)")
    lines.append("")
    lines.append("| id | field | pre | post |")
    lines.append("|---|---|---|---|")
    for s in summary.get("samples", []):
        lines.append(
            f"| {s['id']} | {s['field']} | {s['pre']} | {s['post']} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


# -----------------------------------------------------------------------------
# Phase 1 — Rule 4 scope_domain remap.
# -----------------------------------------------------------------------------


def run_phase_1(client: DirectusAdminClient, snapshot_hash: str) -> dict:
    rows = client.get_items(
        "prod_locked_decisions",
        filters={"status": {"_neq": "superseded"}},
        limit=-1,
    )
    targets = [r for r in rows if _row_matches_rule_4(r)]

    def target_fn(row: dict) -> Optional[str]:
        sd = row.get("scope_domain")
        if sd in RULE_4_SCOPE_DOMAIN_REMAP:
            return RULE_4_SCOPE_DOMAIN_REMAP[sd]
        return None  # leave non-mapped non-canonical for manual review

    summary = execute_per_row_patch_loop(
        client,
        phase=1,
        rule_descriptor="rule_4_scope_domain_remap",
        target_field="scope_domain",
        rows=targets,
        target_value_fn=target_fn,
        snapshot_hash=snapshot_hash,
        expected_count=EXPECTED_ROW_COUNTS["rule_4_scope_domain_remap"],
        activity_log_action="SCHEMA_VOCAB_MIGRATION_PHASE_1_PATCH",
    )
    summary["report_path"] = write_phase_report(1, "scope_domain_remap", summary)
    post_activity_log("SCHEMA_MIGRATION_V3_PHASE_1_COMPLETE", summary)
    return summary


# -----------------------------------------------------------------------------
# Phase 2 — Rule 2 severity lowercase -> UPPER.
# -----------------------------------------------------------------------------


def run_phase_2(client: DirectusAdminClient, snapshot_hash: str) -> dict:
    rows = client.get_items(
        "prod_locked_decisions",
        filters={"status": {"_neq": "superseded"}},
        limit=-1,
    )
    targets = [r for r in rows if _row_matches_rule_2(r)]

    def target_fn(row: dict) -> Optional[str]:
        sev = row.get("severity")
        return RULE_2_SEVERITY_LOWER_TO_UPPER.get(sev)

    summary = execute_per_row_patch_loop(
        client,
        phase=2,
        rule_descriptor="rule_2_severity_lowercase_to_upper",
        target_field="severity",
        rows=targets,
        target_value_fn=target_fn,
        snapshot_hash=snapshot_hash,
        expected_count=EXPECTED_ROW_COUNTS["rule_2_severity_lowercase_to_upper"],
        activity_log_action="SCHEMA_VOCAB_MIGRATION_PHASE_2_PATCH",
    )
    summary["report_path"] = write_phase_report(
        2, "severity_lower_to_upper", summary
    )
    post_activity_log("SCHEMA_MIGRATION_V3_PHASE_2_COMPLETE", summary)
    return summary


# -----------------------------------------------------------------------------
# Phase 3 — admin-UI mechanical detection.
# -----------------------------------------------------------------------------


def run_phase_3(client: DirectusAdminClient) -> dict:
    field_meta = client.fields("prod_locked_decisions")
    tc_field = next(
        (f for f in field_meta if f.get("field") == "task_category"), None
    )
    if tc_field is None:
        post_activity_log(
            "PHASE_3_BLOCKED_BY_SCHEMA_TASK_CATEGORY_FIELD_MISSING",
            {"reason": "task_category field absent in fields() response"},
        )
        sys.exit(2)
    choices = {
        c.get("value")
        for c in tc_field.get("meta", {}).get("options", {}).get("choices", [])
        if c.get("value")
    }
    missing = REQUIRED_TASK_CATEGORY_VALUES_PHASE_3 - choices
    present = REQUIRED_TASK_CATEGORY_VALUES_PHASE_3 & choices

    if missing:
        try:
            blocker = client.get_item("prod_blockers", PHASE_3_BLOCKER_ID)
        except DirectusAdminError as e:
            blocker = {"error": str(e)}
        post_activity_log(
            "PHASE_3_BLOCKED_BY_TASK_CATEGORY_ENUM_INCOMPLETE",
            {
                "prod_blockers_id": PHASE_3_BLOCKER_ID,
                "missing_enum_values": sorted(missing),
                "present_enum_values": sorted(present),
                "canonical_blocker_state": {
                    "title": blocker.get("title")
                    if isinstance(blocker, dict)
                    else None,
                    "is_resolved": blocker.get("is_resolved")
                    if isinstance(blocker, dict)
                    else None,
                },
            },
        )
        sys.stderr.write(
            f"PHASE_3_BLOCKED_BY_TASK_CATEGORY_ENUM_INCOMPLETE: "
            f"missing={sorted(missing)} | "
            f"prod_blockers id={PHASE_3_BLOCKER_ID}\n"
        )
        sys.exit(2)

    blocker = client.get_item("prod_blockers", PHASE_3_BLOCKER_ID)
    auto_resolved_this_run = False
    if not blocker.get("is_resolved"):
        patch_payload = {
            "is_resolved": True,
            "resolved_at": _utcnow_iso(),
        }
        validate_prod_blockers_payload(patch_payload)
        client.patch_item("prod_blockers", PHASE_3_BLOCKER_ID, patch_payload)
        after = client.get_item("prod_blockers", PHASE_3_BLOCKER_ID)
        if not after.get("is_resolved"):
            post_activity_log(
                "PHASE_3_BLOCKED_BY_PATCH_VERIFY_FAIL",
                {"row_id": PHASE_3_BLOCKER_ID, "after": after},
            )
            sys.exit(2)
        auto_resolved_this_run = True

    summary = {
        "prod_blockers_id": PHASE_3_BLOCKER_ID,
        "verified_enum_values": sorted(REQUIRED_TASK_CATEGORY_VALUES_PHASE_3),
        "auto_resolved": auto_resolved_this_run,
    }
    post_activity_log(
        "PHASE_3_PASSED_TASK_CATEGORY_ENUM_VERIFIED", summary
    )
    return summary


# -----------------------------------------------------------------------------
# Phase 4 — Rule 3b task_category synonym remap.
# -----------------------------------------------------------------------------


def run_phase_4(client: DirectusAdminClient, snapshot_hash: str) -> dict:
    rows = client.get_items(
        "prod_locked_decisions",
        filters={"status": {"_neq": "superseded"}},
        limit=-1,
    )
    targets = [r for r in rows if _row_matches_rule_3b(r)]

    def target_fn(row: dict) -> Optional[str]:
        tc = row.get("task_category")
        return RULE_3B_TASK_CATEGORY_SYNONYM_REMAP.get(tc)

    summary = execute_per_row_patch_loop(
        client,
        phase=4,
        rule_descriptor="rule_3b_task_category_remap",
        target_field="task_category",
        rows=targets,
        target_value_fn=target_fn,
        snapshot_hash=snapshot_hash,
        expected_count=EXPECTED_ROW_COUNTS["rule_3b_task_category_remap"],
        activity_log_action="SCHEMA_VOCAB_MIGRATION_PHASE_4_PATCH",
    )
    summary["report_path"] = write_phase_report(
        4, "task_category_remap", summary
    )
    post_activity_log("SCHEMA_MIGRATION_V3_PHASE_4_COMPLETE", summary)
    return summary


# -----------------------------------------------------------------------------
# Phase 5 — gated halt (env-var only path; not authorized this session).
# -----------------------------------------------------------------------------


def run_phase_5(client: DirectusAdminClient, snapshot_hash: str) -> dict:
    if os.environ.get("PHASE_5_ENABLED") != "true":
        artifact = {
            "reason": (
                "PHASE_5_ENABLED env var not set to 'true'; Phase 5 deferred "
                "per spec §3.1."
            ),
            "expected": True,
            "next_step": (
                "Set PHASE_5_ENABLED=true and file LD "
                "SCHEMA_VOCAB_MIGRATION_PHASE_5_AUTHORIZED_V1 to dispatch "
                "Phase 5."
            ),
        }
        post_activity_log("PHASE_5_GATED_NO_FLAG", artifact)
        return artifact

    # Phase 5 path NOT authorized by this handoff — defensive halt.
    ld_rows = client.get_items(
        "prod_locked_decisions",
        filters={
            "decision_key": {
                "_eq": "SCHEMA_VOCAB_MIGRATION_PHASE_5_AUTHORIZED_V1"
            }
        },
    )
    if not ld_rows:
        post_activity_log(
            "PHASE_5_BLOCKED_NO_LD",
            {
                "reason": (
                    "PHASE_5_ENABLED=true but LD "
                    "SCHEMA_VOCAB_MIGRATION_PHASE_5_AUTHORIZED_V1 not found."
                )
            },
        )
        sys.exit(2)

    rows = client.get_items(
        "prod_locked_decisions",
        filters={"status": {"_neq": "superseded"}},
        limit=-1,
    )
    targets = [r for r in rows if _row_matches_rule_1(r)]

    def target_fn(row: dict) -> Optional[str]:
        sev = row.get("severity")
        return RULE_1_SEVERITY_HIGH_CRITICAL_TO_HARD.get(sev)

    summary = execute_per_row_patch_loop(
        client,
        phase=5,
        rule_descriptor="rule_1_severity_high_critical_to_hard",
        target_field="severity",
        rows=targets,
        target_value_fn=target_fn,
        snapshot_hash=snapshot_hash,
        expected_count=EXPECTED_ROW_COUNTS[
            "rule_1_severity_high_critical_to_hard"
        ],
        activity_log_action="SCHEMA_VOCAB_MIGRATION_PHASE_5_PATCH",
    )
    summary["report_path"] = write_phase_report(
        5, "severity_high_critical_to_hard", summary
    )
    post_activity_log("SCHEMA_MIGRATION_V3_PHASE_5_COMPLETE", summary)
    return summary


# -----------------------------------------------------------------------------
# Phase 6 — final audit + mutex release.
# -----------------------------------------------------------------------------


def run_phase_6(
    client: DirectusAdminClient,
    snapshot_meta: dict,
    mutex_id: Optional[int],
    phase_5_deferred: bool,
) -> dict:
    rows = client.get_items(
        "prod_locked_decisions",
        filters={"status": {"_neq": "superseded"}},
        limit=-1,
    )

    rule_4_residual = sum(1 for r in rows if _row_matches_rule_4(r))
    rule_2_residual = sum(1 for r in rows if _row_matches_rule_2(r))
    rule_3b_residual = sum(1 for r in rows if _row_matches_rule_3b(r))
    rule_1_residual = sum(1 for r in rows if _row_matches_rule_1(r))

    date = _today_compact()
    report_path = (
        DOCS_DIR / f"SCHEMA_VOCAB_MIGRATION_PHASE_6_REPORT_{date}.md"
    )
    lines: list[str] = []
    lines.append(f"# Schema Vocab Migration — Phase 6 Final Audit ({date})")
    lines.append("")
    lines.append(f"- Total active rows post-migration: {len(rows)}")
    lines.append(f"- Snapshot row_count (pre): {snapshot_meta['row_count']}")
    lines.append(f"- Phase 5 deferred this session: {phase_5_deferred}")
    lines.append("")
    lines.append("## Per-rule residuals")
    lines.append("")
    lines.append("| Rule | Pre | Residual (post) | Expected post |")
    lines.append("|---|---|---|---|")
    pre_4 = snapshot_meta["per_rule_target_counts"][
        "rule_4_scope_domain_remap"
    ]
    pre_2 = snapshot_meta["per_rule_target_counts"][
        "rule_2_severity_lowercase_to_upper"
    ]
    pre_3b = snapshot_meta["per_rule_target_counts"][
        "rule_3b_task_category_remap"
    ]
    pre_1 = snapshot_meta["per_rule_target_counts"][
        "rule_1_severity_high_critical_to_hard"
    ]
    lines.append(f"| 4 | {pre_4} | {rule_4_residual} | 0 |")
    lines.append(f"| 2 | {pre_2} | {rule_2_residual} | 0 |")
    lines.append(f"| 3b | {pre_3b} | {rule_3b_residual} | 0 |")
    expected_post_1 = pre_1 if phase_5_deferred else 0
    lines.append(f"| 1 | {pre_1} | {rule_1_residual} | {expected_post_1} |")
    lines.append("")

    if mutex_id is not None:
        release_remote_mutex(
            client,
            mutex_id,
            f"Phase 6 final audit complete; report at {report_path}",
        )

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    summary = {
        "report_path": str(report_path),
        "phase_5_deferred": phase_5_deferred,
        "rules_executed": [2, 3, 4] if phase_5_deferred else [1, 2, 3, 4],
        "mutex_released": mutex_id is not None,
        "post_residuals": {
            "rule_4": rule_4_residual,
            "rule_2": rule_2_residual,
            "rule_3b": rule_3b_residual,
            "rule_1": rule_1_residual,
        },
    }
    post_activity_log("SCHEMA_MIGRATION_V3_PHASE_6_COMPLETE", summary)
    return summary


# -----------------------------------------------------------------------------
# Phase 0 orchestration.
# -----------------------------------------------------------------------------


def run_phase_0(
    client: DirectusAdminClient, skip_rehearsal: bool
) -> dict:
    """Phase 0 = Steps 0/0.4/1/2 (always) + 0.5 (rehearsal — skipped when
    skip_rehearsal=True per Kim's HALT-before-G direction) + 3 (Phase 0
    marker; only if rehearsal ran).
    """
    assert_canonical_root()
    cached = write_cached_export(client)
    rows = client.get_items(
        "prod_locked_decisions",
        filters={"status": {"_neq": "superseded"}},
        limit=-1,
    )
    snapshot = write_snapshot(rows)

    # Phase F dry-run report uses the in-memory rows + snapshot metadata.
    # The snapshot metadata for per_rule_target_ids lives in the sidecar
    # (so the dry-run pulls counts from there for the table), but the
    # body of the report iterates over rows directly to compute per-rule
    # counts and samples.
    snapshot_meta_with_counts = dict(snapshot)
    sidecar_path = Path(snapshot["sidecar_path"])
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    snapshot_meta_with_counts["per_rule_target_counts"] = {
        k: len(v) for k, v in sidecar.get("per_rule_target_ids", {}).items()
    }
    dry_run = write_dry_run_report(rows, snapshot_meta_with_counts)

    rehearsal: Optional[dict] = None
    if not skip_rehearsal:
        rehearsal = rollback_rehearsal(client, snapshot)
        write_phase_0_marker(cached, snapshot, dry_run, rehearsal)
    else:
        post_activity_log(
            "SCHEMA_MIGRATION_V3_PHASE_0_DRY_RUN_PATH_COMPLETE",
            {
                "cached": cached,
                "snapshot": {
                    "snapshot_path": snapshot["snapshot_path"],
                    "sidecar_path": snapshot["sidecar_path"],
                    "snapshot_hash": snapshot["snapshot_hash"],
                    "row_count": snapshot["row_count"],
                },
                "dry_run": {
                    "report_path": dry_run["report_path"],
                    "drift": dry_run["drift"],
                    "violating_rules": dry_run["violating_rules"],
                },
                "rehearsal_status": (
                    "SKIPPED — Kim direction: HALT before Phase G rehearsal"
                ),
            },
        )

    return {
        "cached": cached,
        "snapshot": snapshot,
        "dry_run": dry_run,
        "rehearsal": rehearsal,
    }


# -----------------------------------------------------------------------------
# CLI entrypoint.
# -----------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="migrate_schema_vocab_v1.py",
        description=(
            "Schema vocab migration v3 implementation script (spec v7 / "
            "handoff v2.4)."
        ),
    )
    p.add_argument(
        "--skip-rehearsal",
        action="store_true",
        help=(
            "Skip Phase 0 Step 0.5 rollback rehearsal. Used by Kim's "
            "HALT-before-G direction this session."
        ),
    )
    sub = p.add_subparsers(dest="subcommand", required=True)
    for name in (
        "phase-0",
        "phase-1",
        "phase-2",
        "phase-3",
        "phase-4",
        "phase-5",
        "phase-6",
        "all",
        "dry-run-only",
    ):
        sub.add_parser(name)
    return p


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    client = DirectusAdminClient()

    if args.subcommand == "dry-run-only":
        run_phase_0(client, skip_rehearsal=True)
        return 0

    if args.subcommand == "phase-0":
        run_phase_0(client, skip_rehearsal=args.skip_rehearsal)
        return 0

    if args.subcommand in (
        "phase-1",
        "phase-2",
        "phase-3",
        "phase-4",
        "phase-5",
        "phase-6",
        "all",
    ):
        # Mutating phases require Phase 0 artifacts to exist.
        date = _today_compact()
        snapshot_path = (
            DOCS_DIR / f"SCHEMA_VOCAB_MIGRATION_SNAPSHOT_{date}.jsonl"
        )
        sidecar_path = (
            DOCS_DIR
            / f"SCHEMA_VOCAB_MIGRATION_SNAPSHOT_{date}.metadata.json"
        )
        if not snapshot_path.exists() or not sidecar_path.exists():
            sys.stderr.write(
                "Phase 0 snapshot artifacts missing; run phase-0 first.\n"
            )
            return 2
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        snapshot_hash = sidecar["snapshot_hash"]
        snapshot_meta_for_phase_6 = {
            "row_count": sidecar["row_count"],
            "per_rule_target_counts": {
                k: len(v) for k, v in sidecar.get("per_rule_target_ids", {}).items()
            },
            "snapshot_path": str(snapshot_path),
            "sidecar_path": str(sidecar_path),
        }

        local_lock_fd: Optional[int] = None
        mutex_id: Optional[int] = None
        try:
            local_lock_fd = acquire_local_lock()
            mutex_id = acquire_remote_mutex(client)

            if args.subcommand == "phase-1":
                run_phase_1(client, snapshot_hash)
            elif args.subcommand == "phase-2":
                run_phase_2(client, snapshot_hash)
            elif args.subcommand == "phase-3":
                run_phase_3(client)
            elif args.subcommand == "phase-4":
                run_phase_4(client, snapshot_hash)
            elif args.subcommand == "phase-5":
                run_phase_5(client, snapshot_hash)
            elif args.subcommand == "phase-6":
                phase_5_deferred = (
                    os.environ.get("PHASE_5_ENABLED") != "true"
                )
                run_phase_6(
                    client,
                    snapshot_meta_for_phase_6,
                    mutex_id,
                    phase_5_deferred,
                )
                # Phase 6 already released the mutex; clear so finally
                # block does not double-release.
                mutex_id = None
            elif args.subcommand == "all":
                run_phase_1(client, snapshot_hash)
                run_phase_2(client, snapshot_hash)
                run_phase_3(client)
                run_phase_4(client, snapshot_hash)
                phase_5_result = run_phase_5(client, snapshot_hash)
                phase_5_deferred = (
                    phase_5_result.get("reason", "").startswith(
                        "PHASE_5_ENABLED"
                    )
                    if phase_5_result
                    else True
                )
                run_phase_6(
                    client,
                    snapshot_meta_for_phase_6,
                    mutex_id,
                    phase_5_deferred,
                )
                mutex_id = None
        finally:
            if mutex_id is not None:
                try:
                    release_remote_mutex(
                        client,
                        mutex_id,
                        "session ended without explicit Phase 6 release",
                    )
                except Exception as e:  # noqa: BLE001
                    post_activity_log(
                        "MUTEX_RELEASE_FAILED_IN_FINALLY",
                        {"mutex_id": mutex_id, "error": str(e)},
                    )
            if local_lock_fd is not None:
                release_local_lock(local_lock_fd)
        return 0

    parser.error(f"unknown subcommand: {args.subcommand}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
