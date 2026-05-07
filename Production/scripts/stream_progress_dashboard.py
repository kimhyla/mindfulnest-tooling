"""MindfulNest Stream Progress Dashboard.

Live computation of per-stream / per-gate progress across the 9-stream × 5-gate
matrix defined in MINDFULNEST_MASTER_TECHNICAL_SPEC_v6.md §0.1 + §2.

Built per Production/specs/STREAM_PROGRESS_DASHBOARD_SPEC_v1.md
(md5 62bb0dd9e55caeb2d25abacfafc97f01).

Source-of-truth contract per spec §3:
- v6 §2 = stream definitions (frozen narrative).
- This dashboard = live progress (Directus + filesystem computation).
- prod_blockers (is_resolved=false) = current blockers.
- prod_activity_log = audit trail.

Per Rule 18 (urllib not curl), Rule 19 (no shortcuts / no silent failures),
Rule 24 (confidence annotations), Rule 31 (Directus before disk for registered
assets), Rule 35 (schema-verification before any prod_* write).

Re-run on demand: python3 Production/scripts/stream_progress_dashboard.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform as _platform
import re
import subprocess
import sys
import time
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# -----------------------------------------------------------------------------
# Bootstrap: put Production/ on sys.path so lib/ imports resolve
# -----------------------------------------------------------------------------
_THIS_FILE = Path(__file__).resolve()
PROD_ROOT = _THIS_FILE.parents[1]  # Production/
PROJECT_ROOT = PROD_ROOT.parent  # Claude Mindfulnest Project Files/
sys.path.insert(0, str(PROD_ROOT))

from lib.directus_admin_client import (  # noqa: E402
    DirectusAdminClient,
    DirectusAdminError,
)
from lib.directus import try_post_or_queue, read_item  # noqa: E402

# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------

STREAMS = ["A", "B", "C", "D1", "D2", "E", "F", "G", "H"]
GATES = ["G0", "G1", "G2", "G3", "G4"]
ALL_STREAMS = list(STREAMS)

# Per-stream display name
STREAM_NAMES = {
    "A": "Content production",
    "B": "Single-MP4 assembly pipeline",
    "C": "App code",
    "D1": "Backend services",
    "D2": "Web surfaces",
    "E": "Admin / launch prep",
    "F": "Content deployment",
    "G": "Operations & compliance",
    "H": "Engagement & communications",
}

# iOS repo path; configurable via env var per spec §15 risk mitigation
IOS_REPO = Path(os.environ.get("MINDFULNEST_REPO_PATH") or (PROJECT_ROOT / "MindfulNest"))

# Output directory
DASHBOARDS_DIR = PROD_ROOT / "dashboards"

# Schema-confirm: collections whose fields we read or write
REQUIRED_COLLECTIONS = {
    # collection_name : set of field_names this script will reference
    "prod_activity_log": {"id", "action", "details", "performed_by", "created_at"},
    "prod_blockers": {"id", "title", "description", "severity", "is_resolved", "created_at"},
    "prod_locked_decisions": {"id", "decision_key", "status", "is_current"},
    "prod_reference_docs": {"id", "doc_title", "file_path", "doc_version", "doc_category",
                            "status", "is_current", "has_locked_decisions"},
    "prod_modules": {"id"},
    "prod_assets": {"id", "notes"},
    "coppa_data_flows": {"id", "status"},
}

# Color palette per spec §9
COLOR = {
    "GREEN": "#22c55e",
    "YELLOW": "#eab308",
    "RED": "#ef4444",
    "GREY": "#9ca3af",
    "BLUE": "#3b82f6",
    "DARK": "#1f2937",
    "BG": "#f9fafb",
    "CARD": "#ffffff",
}

# Stub heuristic per Judgment Call 2 (spec §17): file < 50 lines OR contains
# stub markers ⇒ STUB; else IMPLEMENTED
STUB_MARKERS = ("# STUB", "// STUB", "NOT IMPLEMENTED")
STUB_LINE_THRESHOLD = 50


# -----------------------------------------------------------------------------
# Confidence annotation helpers (Rule 24)
# -----------------------------------------------------------------------------

def confirmed(source: str) -> str:
    return f"<span class='conf conf-confirmed' title='source: {source}'>[CONFIRMED]</span>"


def inferred(reason: str = "") -> str:
    title = f"reason: {reason}" if reason else "synthesized — verify"
    return f"<span class='conf conf-inferred' title='{title}'>[INFERRED]</span>"


def guessed(reason: str = "") -> str:
    return f"<span class='conf conf-guessed' title='{reason}'>[GUESSED]</span>"


# -----------------------------------------------------------------------------
# Probe layer (spec §6 architecture diagram)
# -----------------------------------------------------------------------------

class DirectusContext:
    """Lazily-initialized Directus connectivity wrapper.

    Tracks latency, queued-write state, and a per-collection schema cache so
    schema-confirm can be a one-pass startup operation without re-fetching
    fields per probe.
    """

    def __init__(self, verbose: bool = False) -> None:
        self.verbose = verbose
        self.client: DirectusAdminClient | None = None
        self.unreachable: bool = False
        self.auth_failed: bool = False
        self.latency_ms: int = 0
        self.schema_mismatches: list[str] = []
        self.schema_known: dict[str, set[str]] = {}

    def connect(self) -> None:
        t0 = time.time()
        try:
            self.client = DirectusAdminClient()
            # Cheap call to force login; surfaces auth failures up front.
            _ = self.client.get_items("prod_activity_log", limit=1, fields=["id"])
            self.latency_ms = int((time.time() - t0) * 1000)
        except DirectusAdminError as e:
            if e.status in (401, 403):
                self.auth_failed = True
            else:
                self.unreachable = True
            self.latency_ms = int((time.time() - t0) * 1000)
        except (urllib.error.URLError, RuntimeError):
            self.unreachable = True
            self.latency_ms = int((time.time() - t0) * 1000)

    def confirm_schema(self) -> None:
        """Per Rule 35: confirm field names match before any prod_* write."""
        if self.client is None or self.unreachable or self.auth_failed:
            return
        for collection, expected in REQUIRED_COLLECTIONS.items():
            try:
                fields = self.client.fields(collection) or []
                names = {f.get("field") for f in fields if isinstance(f, dict)}
                self.schema_known[collection] = names
                missing = expected - names
                if missing:
                    self.schema_mismatches.append(
                        f"{collection}: missing fields {sorted(missing)}"
                    )
            except DirectusAdminError as e:
                self.schema_mismatches.append(f"{collection}: schema fetch failed ({e.status})")

    def probe(self, collection: str, filters: dict | None = None,
              fields: list[str] | None = None, sort: str | None = None,
              limit: int = -1) -> tuple[list[dict] | None, str | None]:
        """Run a Directus query. Return (rows, error_message)."""
        if self.client is None or self.unreachable:
            return None, "DIRECTUS UNREACHABLE"
        if self.auth_failed:
            return None, "AUTH FAILED"
        try:
            rows = self.client.get_items(collection, filters=filters, fields=fields,
                                         sort=sort, limit=limit)
            return rows, None
        except DirectusAdminError as e:
            return None, f"directus_{e.status}"


def file_probe(path: Path, must_have_lines: int | None = None) -> tuple[str, str]:
    """Filesystem existence check.

    Returns (status, detail) where status is one of:
      GREEN   — exists and (no line floor, or line count >= floor)
      YELLOW  — exists but below line floor
      RED     — does not exist
    """
    if not path.exists():
        return "RED", f"missing: {path}"
    if must_have_lines is not None:
        try:
            n = sum(1 for _ in path.open(encoding="utf-8", errors="replace"))
        except OSError as e:
            return "RED", f"unreadable: {e}"
        if n < must_have_lines:
            return "YELLOW", f"{path.name}: {n} lines < {must_have_lines}"
        return "GREEN", f"{path.name}: {n} lines"
    return "GREEN", f"exists: {path.name}"


def file_content_probe(path: Path, patterns: list[str],
                       require_all: bool = True,
                       case_insensitive: bool = False) -> tuple[str, str]:
    """File-existence + content-pattern check.

    Patterns are substrings (not regex). Returns GREEN if all (or any, when
    require_all=False) patterns are present.
    """
    if not path.exists():
        return "RED", f"missing: {path}"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return "RED", f"unreadable: {e}"
    if case_insensitive:
        haystack = text.lower()
        needles = [p.lower() for p in patterns]
    else:
        haystack = text
        needles = patterns
    hits = [n for n in needles if n in haystack]
    if require_all:
        if len(hits) == len(needles):
            return "GREEN", f"{path.name}: all {len(needles)} patterns present"
        missing = [n for n in needles if n not in hits]
        return "RED", f"{path.name}: missing {missing}"
    if hits:
        return "GREEN", f"{path.name}: {len(hits)}/{len(needles)} patterns present"
    return "RED", f"{path.name}: zero patterns matched"


def file_stub_probe(path: Path) -> tuple[str, str]:
    """Stub-heuristic: STUB if file < 50 lines OR contains stub marker.

    Returns:
      GREEN  — file exists and is "implemented" (line >= 50 + no stub marker)
      YELLOW — file exists but matches stub heuristic (counts 0.5 toward gate)
      RED    — file missing
    """
    if not path.exists():
        return "RED", f"missing: {path}"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return "RED", f"unreadable: {e}"
    n_lines = text.count("\n") + (0 if text.endswith("\n") else 1)
    has_marker = any(m in text for m in STUB_MARKERS)
    if n_lines < STUB_LINE_THRESHOLD or has_marker:
        return "YELLOW", (f"{path.name}: STUB ({n_lines} lines, "
                          f"marker={'yes' if has_marker else 'no'})")
    return "GREEN", f"{path.name}: implemented ({n_lines} lines)"


def repo_path(rel: str) -> tuple[Path, bool]:
    """Resolve a path inside the iOS repo. Returns (full_path, repo_exists)."""
    return IOS_REPO / rel, IOS_REPO.exists()


# -----------------------------------------------------------------------------
# Artifact-prover registry — verbatim from spec §7 (52 rows)
# -----------------------------------------------------------------------------
#
# Each row carries: id / artifact / streams / gate / prover_type / prover_spec
# and a `prover` callable that returns (status, detail). Rationale + Alternatives
# columns from spec §7 live in inline comments above their row so they remain
# auditable but are not load-bearing in code.
#
# Status conventions:
#   GREEN        = artifact is implemented / confirmed done
#   YELLOW       = stub or partial; 0.5 toward gate completion (Judgment Call 2)
#   RED          = missing / failed
#   MISSING-REPO = iOS repo not present locally (special case for C/D1 cells)
#
# Prover types:
#   FS       = file_probe (existence + optional line floor)
#   FS-STUB  = file_stub_probe (STUB heuristic)
#   DIR      = directus_probe
#   COMP     = composite (multiple provers)


def _wrap_repo(path: str, prover):
    """Wrap a prover so MissingRepo short-circuits to MISSING-REPO state."""
    def runner(ctx, dctx):
        full, exists = repo_path(path)
        if not exists:
            return "MISSING-REPO", f"iOS repo absent: {IOS_REPO}"
        return prover(full, ctx, dctx)
    return runner


def _prove_lds_in_cursor_rules(ctx, dctx):
    files = [
        ".cursor/rules/architecture.mdc",
        ".cursor/rules/coppa.mdc",
        ".cursor/rules/playback.mdc",
        ".cursor/rules/fidget.mdc",
    ]
    # Spec: "exists ... AND each contains string LD-280, LD-281...LD-450"
    # iOS repo is the canonical location for .cursor/rules per LD-280 family.
    full_paths = [IOS_REPO / f for f in files]
    if not IOS_REPO.exists():
        return "MISSING-REPO", f"iOS repo absent: {IOS_REPO}"
    missing = [p for p in full_paths if not p.exists()]
    if missing:
        return "RED", f"missing {[p.name for p in missing]}"
    # Content-spot-check: all four files should reference at least one LD in 280-289 + 450
    needles = [f"LD-{n}" for n in (280, 281, 282, 283, 284, 285, 286, 287, 288, 289, 450)]
    for p in full_paths:
        text = p.read_text(encoding="utf-8", errors="replace")
        if not any(n in text for n in needles):
            return "YELLOW", f"{p.name}: no LD-280..450 reference"
    return "GREEN", "all four .cursor/rules files exist with LD references"


def _prove_player_lifecycle_contract(ctx, dctx):
    return file_probe(PROD_ROOT / "contracts" / "PLAYER_LIFECYCLE_CONTRACT.md", must_have_lines=50)


def _prove_manifest_schema_v1(ctx, dctx):
    p = PROD_ROOT / "contracts" / "MANIFEST_SCHEMA_V1.json"
    if not p.exists():
        return "RED", f"missing: {p.name}"
    return file_content_probe(p, ["source_hash", "output_hash"], require_all=True)


def _prove_assemble_module_contract(ctx, dctx):
    return file_stub_probe(PROD_ROOT / "contracts" / "ASSEMBLE_MODULE_CONTRACT.md")


def _prove_cache_download_state_machine(ctx, dctx):
    return file_stub_probe(PROD_ROOT / "contracts" / "CACHE_DOWNLOAD_STATE_MACHINE.md")


def _prove_entitlement_state_machine(ctx, dctx):
    return file_stub_probe(PROD_ROOT / "contracts" / "ENTITLEMENT_STATE_MACHINE.md")


def _prove_kws_state_machine(ctx, dctx):
    return file_stub_probe(PROD_ROOT / "contracts" / "KWS_STATE_MACHINE.md")


def _prove_r2_deployment_contract(ctx, dctx):
    return file_stub_probe(PROD_ROOT / "contracts" / "R2_DEPLOYMENT_CONTRACT.md")


def _prove_cf_deploy_contract(ctx, dctx):
    return file_stub_probe(PROD_ROOT / "contracts" / "CF_DEPLOY_CONTRACT.md")


def _prove_stripe_recovery_contract(ctx, dctx):
    return file_stub_probe(PROD_ROOT / "contracts" / "STRIPE_RECOVERY_CONTRACT.md")


def _prove_commission_fraud_surface(ctx, dctx):
    return file_stub_probe(PROD_ROOT / "contracts" / "COMMISSION_FRAUD_SURFACE.md")


def _prove_coppa_data_flows(ctx, dctx):
    rows, err = dctx.probe("coppa_data_flows", fields=["id", "status"], limit=200)
    if err:
        return "RED", err
    rows = rows or []
    populated = [r for r in rows if r.get("status")]
    if len(populated) >= 8:
        return "GREEN", f"{len(populated)} rows with status set (>=8)"
    return "YELLOW", f"only {len(populated)} of {len(rows)} rows populated (need >=8)"


def _prove_with_coppa_guard(ctx, dctx):
    return _wrap_repo(
        "functions/src/middleware/withCoppaGuard.ts",
        lambda full, c, d: file_probe(full),
    )(ctx, dctx)


def _prove_ast_policy_scan(ctx, dctx):
    return _wrap_repo(
        "scripts/qa/ast-policy-scan.mjs",
        lambda full, c, d: file_stub_probe(full),
    )(ctx, dctx)


def _prove_husky_assets_block(ctx, dctx):
    return _wrap_repo(
        ".husky/pre-commit",
        lambda full, c, d: file_content_probe(full, ["assets", "50"], require_all=True),
    )(ctx, dctx)


def _prove_sentry_crashlytics(ctx, dctx):
    rows, err = dctx.probe(
        "prod_blockers",
        filters={"_and": [
            {"is_resolved": {"_eq": False}},
            {"_or": [
                {"title": {"_contains": "Sentry"}},
                {"title": {"_contains": "Crashlytics"}},
            ]},
        ]},
        fields=["id", "title"], limit=50,
    )
    if err:
        return "RED", err
    rows = rows or []
    if not rows:
        return "GREEN", "no open Sentry/Crashlytics blockers"
    return "RED", f"{len(rows)} open blocker(s): {[r.get('title') for r in rows][:3]}"


def _prove_app_check_enforce(ctx, dctx):
    rows, err = dctx.probe(
        "prod_blockers",
        filters={"_and": [
            {"is_resolved": {"_eq": False}},
            {"title": {"_contains": "App Check"}},
        ]},
        fields=["id", "title"], limit=50,
    )
    if err:
        return "RED", err
    rows = rows or []
    if not rows:
        return "GREEN", "no open App Check blockers"
    return "RED", f"{len(rows)} open: {[r.get('title') for r in rows][:3]}"


def _prove_tsconfig_strict(ctx, dctx):
    return _wrap_repo(
        "tsconfig.json",
        lambda full, c, d: file_content_probe(
            full, ['"strict": true', '"noUncheckedIndexedAccess": true'], require_all=True),
    )(ctx, dctx)


def _prove_zod_schemas(ctx, dctx):
    rows, err = dctx.probe(
        "prod_blockers",
        filters={"_and": [
            {"is_resolved": {"_eq": False}},
            {"_or": [
                {"title": {"_contains": "Zod"}},
                {"title": {"_contains": "schema validation"}},
            ]},
        ]},
        fields=["id", "title"], limit=50,
    )
    if err:
        return "RED", err
    rows = rows or []
    if not rows:
        return "GREEN", "no open Zod / schema-validation blockers"
    return "RED", f"{len(rows)} open: {[r.get('title') for r in rows][:3]}"


def _prove_assemble_module_py(ctx, dctx):
    return file_probe(PROD_ROOT / "tools" / "assemble_module.py")


def _prove_r2_cache_headers(ctx, dctx):
    p = PROD_ROOT / "scripts" / "r2_upload.py"
    if not p.exists():
        return "RED", f"missing: {p.name}"
    return file_content_probe(p, ["immutable", "no-cache"], require_all=True)


def _prove_r2_range_probe(ctx, dctx):
    return _wrap_repo(
        "scripts/qa/r2-range-cache-probe.mjs",
        lambda full, c, d: file_stub_probe(full),
    )(ctx, dctx)


def _prove_r2_atomic_publish(ctx, dctx):
    return file_probe(PROD_ROOT / "scripts" / "r2_atomic_publish.py")


def _prove_invariants_ts(ctx, dctx):
    return _wrap_repo(
        "src/runtime/invariants.ts",
        lambda full, c, d: file_probe(full, must_have_lines=100),
    )(ctx, dctx)


def _prove_player_prewarming(ctx, dctx):
    full, exists = repo_path("app/module/[moduleId].tsx")
    if not exists:
        return "MISSING-REPO", f"iOS repo absent: {IOS_REPO}"
    if not full.exists():
        return "RED", f"missing: {full.name}"
    text = full.read_text(encoding="utf-8", errors="replace")
    if re.search(r"pre.?warm", text, re.IGNORECASE):
        return "GREEN", "pre-warm reference present"
    return "RED", "no pre-warm reference"


def _prove_perf_telemetry(ctx, dctx):
    return _wrap_repo(
        "lib/telemetry/playback_timestamps.ts",
        lambda full, c, d: file_probe(full),
    )(ctx, dctx)


def _prove_netinfo(ctx, dctx):
    return _wrap_repo(
        "lib/downloadManager.ts",
        lambda full, c, d: file_content_probe(full, ["@react-native-community/netinfo"]),
    )(ctx, dctx)


def _prove_save_resume(ctx, dctx):
    return _wrap_repo(
        "lib/playback/saveResume.ts",
        lambda full, c, d: file_content_probe(full, ["bounds", "duration_ms"], require_all=False),
    )(ctx, dctx)


def _prove_ipad9_maestro(ctx, dctx):
    return _wrap_repo(
        ".maestro/iPad9_30min_flow.yaml",
        lambda full, c, d: file_probe(full),
    )(ctx, dctx)


def _prove_staging_firebaserc(ctx, dctx):
    return _wrap_repo(
        ".firebaserc",
        lambda full, c, d: file_content_probe(full, ["staging"]),
    )(ctx, dctx)


def _prove_ld450_endurance(ctx, dctx):
    rows, err = dctx.probe(
        "prod_activity_log",
        filters={"action": {"_contains": "ld450_endurance"}},
        fields=["id", "action", "details"], sort="-created_at", limit=10,
    )
    if err:
        return "RED", err
    rows = rows or []
    if not rows:
        return "RED", "no ld450_endurance activity rows"
    return "YELLOW", f"{len(rows)} activity row(s); pending iPad 9 procurement"


def _prove_kws_state_full(ctx, dctx):
    s1, d1 = file_stub_probe(PROD_ROOT / "contracts" / "KWS_STATE_MACHINE.md")
    rows, err = dctx.probe(
        "prod_blockers",
        filters={"_and": [
            {"is_resolved": {"_eq": False}}, {"title": {"_contains": "KWS"}},
        ]},
        fields=["id", "title"], limit=50,
    )
    if err:
        return "RED", f"{d1}; directus: {err}"
    open_blockers = rows or []
    if s1 == "RED":
        return "RED", d1
    if open_blockers:
        return "YELLOW", f"{d1}; {len(open_blockers)} open blocker(s)"
    return s1, f"{d1}; 0 open KWS blockers"


def _prove_entitlement_state_full(ctx, dctx):
    s1, d1 = file_stub_probe(PROD_ROOT / "contracts" / "ENTITLEMENT_STATE_MACHINE.md")
    rows, err = dctx.probe(
        "prod_blockers",
        filters={"_and": [
            {"is_resolved": {"_eq": False}}, {"title": {"_contains": "entitlement"}},
        ]},
        fields=["id", "title"], limit=50,
    )
    if err:
        return "RED", f"{d1}; directus: {err}"
    open_blockers = rows or []
    if s1 == "RED":
        return "RED", d1
    if open_blockers:
        return "YELLOW", f"{d1}; {len(open_blockers)} open blocker(s)"
    return s1, f"{d1}; 0 open entitlement blockers"


def _prove_remote_config_kill_switches(ctx, dctx):
    rows, err = dctx.probe(
        "prod_activity_log",
        filters={"_and": [
            {"action": {"_contains": "kill_switch"}},
        ]},
        fields=["id", "action", "details"], limit=50,
    )
    if err:
        return "RED", err
    rows = rows or []
    tested = [r for r in rows if "tested" in json.dumps(r.get("details") or {})]
    if len(tested) >= 5:
        return "GREEN", f"{len(tested)} tested kill_switch rows"
    return "RED", f"only {len(tested)} tested (need >=5)"


def _prove_postmark(ctx, dctx):
    rows1, err1 = dctx.probe(
        "prod_locked_decisions",
        filters={"_and": [
            {"decision_key": {"_eq": "STREAM_H_EMAIL_POSTMARK_V1"}},
            {"status": {"_eq": "active"}},
        ]},
        fields=["id"], limit=5,
    )
    rows2, err2 = dctx.probe(
        "prod_activity_log",
        filters={"action": {"_contains": "postmark_template"}},
        fields=["id"], limit=20,
    )
    if err1 or err2:
        return "RED", err1 or err2
    has_ld = bool(rows1)
    n_templates = len(rows2 or [])
    if has_ld and n_templates >= 5:
        return "GREEN", f"LD active + {n_templates} template rows"
    if has_ld:
        return "YELLOW", f"LD active but only {n_templates} template rows (need >=5)"
    return "RED", "STREAM_H_EMAIL_POSTMARK_V1 not active"


def _prove_runbooks_tabletoped(ctx, dctx):
    files = [
        PROD_ROOT / "contracts" / "RUNBOOK_AI_COACH_UNSAFE_OUTPUT.md",
        PROD_ROOT / "contracts" / "RUNBOOK_CDN_OUTAGE.md",
        PROD_ROOT / "contracts" / "RUNBOOK_KWS_FAILURE.md",
    ]
    missing = [p for p in files if not p.exists()]
    rows, err = dctx.probe(
        "prod_activity_log",
        filters={"action": {"_contains": "tabletop"}},
        fields=["id"], limit=20,
    )
    if err:
        return "RED", err
    n = len(rows or [])
    if missing:
        return "RED", f"missing runbooks: {[p.name for p in missing]}; tabletops={n}"
    if n >= 3:
        return "GREEN", f"3 runbooks present; {n} tabletop rows"
    return "YELLOW", f"3 runbooks present; only {n} tabletop rows (need >=3)"


def _prove_eas_update(ctx, dctx):
    return _wrap_repo(
        "eas.json",
        lambda full, c, d: file_content_probe(full, ["channel", "rollback"], require_all=True),
    )(ctx, dctx)


def _prove_chipper_moments(ctx, dctx):
    rows, err = dctx.probe(
        "prod_assets",
        filters={"notes": {"_contains": "chipper_moment"}},
        fields=["id", "notes"], limit=200,
    )
    if err:
        return "RED", err
    n = len(rows or [])
    if n >= 8:
        return "GREEN", f"{n} chipper_moment assets"
    return "RED", f"only {n} of 8 chipper_moment assets registered"


def _prove_ai_coach_safety_triple(ctx, dctx):
    rows1, err1 = dctx.probe(
        "prod_blockers",
        filters={"_and": [
            {"is_resolved": {"_eq": False}},
            {"title": {"_contains": "AI Coach"}},
            {"title": {"_contains": "safety"}},
        ]},
        fields=["id"], limit=20,
    )
    rows2, err2 = dctx.probe(
        "prod_activity_log",
        filters={"action": {"_contains": "coach_safety"}},
        fields=["id"], limit=20,
    )
    if err1 or err2:
        return "RED", err1 or err2
    n_open = len(rows1 or [])
    n_log = len(rows2 or [])
    if n_open == 0 and n_log >= 3:
        return "GREEN", f"0 open + {n_log} coach_safety rows"
    return "RED", f"{n_open} open blocker(s); {n_log} coach_safety rows (need 0 + >=3)"


def _prove_stripe_webhook_idempotent(ctx, dctx):
    return _wrap_repo(
        "functions/src/stripe/webhook.ts",
        lambda full, c, d: file_content_probe(full, ["event.id", "dedupe"], require_all=True),
    )(ctx, dctx)


def _prove_stripe_coppa_recovery(ctx, dctx):
    rows, err = dctx.probe(
        "prod_locked_decisions",
        filters={"_and": [
            {"decision_key": {"_contains": "STRIPE_RECOVERY"}},
            {"status": {"_eq": "active"}},
        ]},
        fields=["id", "decision_key"], limit=10,
    )
    if err:
        return "RED", err
    n = len(rows or [])
    if n >= 1:
        return "GREEN", f"{n} active STRIPE_RECOVERY LD(s)"
    return "RED", "no active STRIPE_RECOVERY LD"


def _prove_affonso(ctx, dctx):
    rows1, err1 = dctx.probe(
        "prod_blockers",
        filters={"_and": [
            {"is_resolved": {"_eq": False}}, {"title": {"_contains": "Affonso"}},
        ]},
        fields=["id"], limit=20,
    )
    rows2, err2 = dctx.probe(
        "prod_activity_log",
        filters={"action": {"_contains": "affonso_attribution"}},
        fields=["id"], limit=10,
    )
    if err1 or err2:
        return "RED", err1 or err2
    n_open = len(rows1 or [])
    n_log = len(rows2 or [])
    if n_open == 0 and n_log >= 1:
        return "GREEN", f"0 open + {n_log} affonso_attribution row(s)"
    return "RED", f"{n_open} open blocker(s); {n_log} attribution rows"


def _prove_commission_fraud(ctx, dctx):
    p = PROD_ROOT / "contracts" / "COMMISSION_FRAUD_SURFACE.md"
    if not p.exists():
        return "RED", f"missing: {p.name}"
    return file_content_probe(p, ["rate_limit", "clawback"], require_all=True)


def _prove_composite_index(ctx, dctx):
    return _wrap_repo(
        "firestore.indexes.json",
        lambda full, c, d: file_probe(full),
    )(ctx, dctx)


def _prove_tabletop_stripe(ctx, dctx):
    rows, err = dctx.probe(
        "prod_activity_log",
        filters={"action": {"_contains": "tabletop_stripe"}},
        fields=["id"], limit=10,
    )
    if err:
        return "RED", err
    n = len(rows or [])
    if n >= 1:
        return "GREEN", f"{n} tabletop_stripe row(s)"
    return "RED", "no tabletop_stripe rows"


def _prove_parent_coppa_portal(ctx, dctx):
    p = PROJECT_ROOT / "mindfulnest-parent-dashboard"
    if not p.exists():
        return "RED", "mindfulnest-parent-dashboard/ absent"
    needles = ["/review", "/delete", "/revoke"]
    # Search all .ts/.tsx/.js/.jsx files for the route declarations
    found = {n: False for n in needles}
    for sub in p.rglob("*"):
        if sub.is_file() and sub.suffix in {".ts", ".tsx", ".js", ".jsx"}:
            try:
                text = sub.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for n in needles:
                if n in text:
                    found[n] = True
    if all(found.values()):
        return "GREEN", "all 3 routes present"
    missing = [n for n, ok in found.items() if not ok]
    return "RED", f"missing routes: {missing}"


def _prove_retention_scheduler(ctx, dctx):
    return _wrap_repo(
        "functions/src/coppa_retention_scheduler.ts",
        lambda full, c, d: file_probe(full),
    )(ctx, dctx)


def _prove_right_to_delete(ctx, dctx):
    return _wrap_repo(
        "functions/src/right_to_delete.ts",
        lambda full, c, d: file_probe(full),
    )(ctx, dctx)


def _prove_app_store_evidence(ctx, dctx):
    rows, err = dctx.probe(
        "prod_reference_docs",
        filters={"doc_category": {"_eq": "app_store_evidence"}},
        fields=["id"], limit=20,
    )
    if err:
        return "RED", err
    n = len(rows or [])
    if n >= 5:
        return "GREEN", f"{n} app_store_evidence reference docs"
    return "RED", f"only {n} of 5 app_store_evidence reference docs"


def _prove_cf_deploy_contract_full(ctx, dctx):
    p = PROD_ROOT / "contracts" / "CF_DEPLOY_CONTRACT.md"
    if not p.exists():
        return "RED", f"missing: {p.name}"
    return file_content_probe(p, ["maintenance_mode", "force_update_required"], require_all=True)


def _prove_release_artifact_audit(ctx, dctx):
    return _wrap_repo(
        "scripts/qa/release_artifact_audit.mjs",
        lambda full, c, d: file_probe(full),
    )(ctx, dctx)


def _prove_cursor_ci_tiers(ctx, dctx):
    full_yaml, exists = repo_path(".github/workflows/zero-error-qa.yml")
    full_pkg, _ = repo_path("package.json")
    if not exists:
        return "MISSING-REPO", f"iOS repo absent: {IOS_REPO}"
    if not full_yaml.exists():
        return "RED", f"missing: {full_yaml.name}"
    if not full_pkg.exists():
        return "RED", "missing package.json"
    text = full_pkg.read_text(encoding="utf-8", errors="replace")
    needed = ["qa:tier-a", "qa:tier-b", "qa:tier-c"]
    missing = [n for n in needed if n not in text]
    if missing:
        return "YELLOW", f"workflow exists; package.json missing scripts {missing}"
    return "GREEN", "workflow + 3 tier scripts present"


# ---- Registry --------------------------------------------------------------
ARTIFACT_REGISTRY: list[dict] = [
    # 1
    {"id": 1, "artifact": "LDs 280–289 + LD-450 in .cursor/rules/",
     "streams": ALL_STREAMS, "gate": "G0", "prover_type": "FS",
     "prover_spec": "exists .cursor/rules/architecture.mdc AND coppa.mdc AND playback.mdc AND fidget.mdc; each contains string LD-280, LD-281...LD-450",
     "prover": _prove_lds_in_cursor_rules},
    # 2
    {"id": 2, "artifact": "Production/contracts/PLAYER_LIFECYCLE_CONTRACT.md",
     "streams": ["C"], "gate": "G0", "prover_type": "FS",
     "prover_spec": "exists Production/contracts/PLAYER_LIFECYCLE_CONTRACT.md AND > 50 lines",
     "prover": _prove_player_lifecycle_contract},
    # 3
    {"id": 3, "artifact": "Production/contracts/MANIFEST_SCHEMA_V1.json",
     "streams": ["B", "C", "F"], "gate": "G0", "prover_type": "COMP",
     "prover_spec": "FS exists Production/contracts/MANIFEST_SCHEMA_V1.json AND content includes both source_hash AND output_hash keys",
     "prover": _prove_manifest_schema_v1},
    # 4
    {"id": 4, "artifact": "Production/contracts/ASSEMBLE_MODULE_CONTRACT.md",
     "streams": ["B"], "gate": "G0", "prover_type": "FS-STUB",
     "prover_spec": "exists Production/contracts/ASSEMBLE_MODULE_CONTRACT.md",
     "prover": _prove_assemble_module_contract},
    # 5
    {"id": 5, "artifact": "Production/contracts/CACHE_DOWNLOAD_STATE_MACHINE.md",
     "streams": ["C"], "gate": "G0", "prover_type": "FS-STUB",
     "prover_spec": "exists Production/contracts/CACHE_DOWNLOAD_STATE_MACHINE.md",
     "prover": _prove_cache_download_state_machine},
    # 6
    {"id": 6, "artifact": "Production/contracts/ENTITLEMENT_STATE_MACHINE.md",
     "streams": ["D1"], "gate": "G0", "prover_type": "FS-STUB",
     "prover_spec": "exists Production/contracts/ENTITLEMENT_STATE_MACHINE.md",
     "prover": _prove_entitlement_state_machine},
    # 7
    {"id": 7, "artifact": "Production/contracts/KWS_STATE_MACHINE.md",
     "streams": ["D1"], "gate": "G0", "prover_type": "FS-STUB",
     "prover_spec": "exists Production/contracts/KWS_STATE_MACHINE.md",
     "prover": _prove_kws_state_machine},
    # 8
    {"id": 8, "artifact": "Production/contracts/R2_DEPLOYMENT_CONTRACT.md",
     "streams": ["F"], "gate": "G0", "prover_type": "FS-STUB",
     "prover_spec": "exists Production/contracts/R2_DEPLOYMENT_CONTRACT.md",
     "prover": _prove_r2_deployment_contract},
    # 9
    {"id": 9, "artifact": "Production/contracts/CF_DEPLOY_CONTRACT.md",
     "streams": ["D1"], "gate": "G4", "prover_type": "FS-STUB",
     "prover_spec": "exists Production/contracts/CF_DEPLOY_CONTRACT.md",
     "prover": _prove_cf_deploy_contract},
    # 10
    {"id": 10, "artifact": "Production/contracts/STRIPE_RECOVERY_CONTRACT.md",
     "streams": ["D1"], "gate": "G3", "prover_type": "FS-STUB",
     "prover_spec": "exists Production/contracts/STRIPE_RECOVERY_CONTRACT.md",
     "prover": _prove_stripe_recovery_contract},
    # 11
    {"id": 11, "artifact": "Production/contracts/COMMISSION_FRAUD_SURFACE.md",
     "streams": ["D1"], "gate": "G3", "prover_type": "FS-STUB",
     "prover_spec": "exists Production/contracts/COMMISSION_FRAUD_SURFACE.md",
     "prover": _prove_commission_fraud_surface},
    # 12
    {"id": 12, "artifact": "coppa_data_flows Directus collection populated",
     "streams": ["D1"], "gate": "G0", "prover_type": "DIR",
     "prover_spec": "coppa_data_flows filter status != null AND row count >= 8",
     "prover": _prove_coppa_data_flows},
    # 13
    {"id": 13, "artifact": "withCoppaGuard() middleware exists",
     "streams": ["D1"], "gate": "G0", "prover_type": "FS",
     "prover_spec": "exists MindfulNest/functions/src/middleware/withCoppaGuard.ts",
     "prover": _prove_with_coppa_guard},
    # 14
    {"id": 14, "artifact": "Pre-commit AST scan (scripts/qa/ast-policy-scan.mjs)",
     "streams": ALL_STREAMS, "gate": "G0", "prover_type": "FS-STUB",
     "prover_spec": "exists MindfulNest/scripts/qa/ast-policy-scan.mjs",
     "prover": _prove_ast_policy_scan},
    # 15
    {"id": 15, "artifact": "Pre-commit hook: /assets size 50MB block",
     "streams": ALL_STREAMS, "gate": "G0", "prover_type": "FS",
     "prover_spec": "exists MindfulNest/.husky/pre-commit AND content includes assets AND 50",
     "prover": _prove_husky_assets_block},
    # 16
    {"id": 16, "artifact": "Sentry + Crashlytics enabled",
     "streams": ["D1"], "gate": "G0", "prover_type": "DIR",
     "prover_spec": "prod_blockers filter (title contains Sentry OR Crashlytics) AND is_resolved=false returns 0 rows",
     "prover": _prove_sentry_crashlytics},
    # 17
    {"id": 17, "artifact": "App Check enforceAppCheck: true",
     "streams": ["D1"], "gate": "G0", "prover_type": "DIR",
     "prover_spec": "prod_blockers filter (title contains App Check) AND is_resolved=false returns 0 rows",
     "prover": _prove_app_check_enforce},
    # 18
    {"id": 18, "artifact": "TypeScript strict: true + noUncheckedIndexedAccess",
     "streams": ["C"], "gate": "G0", "prover_type": "FS",
     "prover_spec": "exists MindfulNest/tsconfig.json AND content includes \"strict\": true AND \"noUncheckedIndexedAccess\": true",
     "prover": _prove_tsconfig_strict},
    # 19
    {"id": 19, "artifact": "Zod schemas at every Firestore read boundary",
     "streams": ["C", "D1"], "gate": "G0", "prover_type": "DIR",
     "prover_spec": "prod_blockers filter (title contains Zod OR schema validation) returns 0 open",
     "prover": _prove_zod_schemas},
    # 20
    {"id": 20, "artifact": "assemble_module.py output validator",
     "streams": ["B"], "gate": "G1", "prover_type": "FS",
     "prover_spec": "exists Production/tools/assemble_module.py",
     "prover": _prove_assemble_module_py},
    # 21
    {"id": 21, "artifact": "R2 cache headers explicit",
     "streams": ["F"], "gate": "G1", "prover_type": "FS",
     "prover_spec": "exists Production/scripts/r2_upload.py AND content includes immutable AND no-cache",
     "prover": _prove_r2_cache_headers},
    # 22
    {"id": 22, "artifact": "R2 range-request probe (scripts/qa/r2-range-cache-probe.mjs)",
     "streams": ["F"], "gate": "G1", "prover_type": "FS-STUB",
     "prover_spec": "exists MindfulNest/scripts/qa/r2-range-cache-probe.mjs",
     "prover": _prove_r2_range_probe},
    # 23
    {"id": 23, "artifact": "Atomic deploy gate (manifest URL flips after R2 sync)",
     "streams": ["F"], "gate": "G1", "prover_type": "FS",
     "prover_spec": "exists Production/scripts/r2_atomic_publish.py",
     "prover": _prove_r2_atomic_publish},
    # 24
    {"id": 24, "artifact": "Runtime invariant assertions (13 patterns)",
     "streams": ["C"], "gate": "G1", "prover_type": "FS",
     "prover_spec": "exists MindfulNest/src/runtime/invariants.ts AND line count >= 100",
     "prover": _prove_invariants_ts},
    # 25
    {"id": 25, "artifact": "Player pre-warming wired",
     "streams": ["C"], "gate": "G1", "prover_type": "FS",
     "prover_spec": "exists MindfulNest/app/module/[moduleId].tsx AND content includes pre.?warm (case-insensitive regex)",
     "prover": _prove_player_prewarming},
    # 26
    {"id": 26, "artifact": "Performance telemetry instrumented (12 timestamps)",
     "streams": ["C"], "gate": "G1", "prover_type": "FS",
     "prover_spec": "exists MindfulNest/lib/telemetry/playback_timestamps.ts",
     "prover": _prove_perf_telemetry},
    # 27
    {"id": 27, "artifact": "NetInfo connectivity listener wired",
     "streams": ["C"], "gate": "G1", "prover_type": "FS",
     "prover_spec": "exists MindfulNest/lib/downloadManager.ts AND content includes @react-native-community/netinfo",
     "prover": _prove_netinfo},
    # 28
    {"id": 28, "artifact": "Save-and-resume bounds check",
     "streams": ["C"], "gate": "G1", "prover_type": "FS",
     "prover_spec": "exists MindfulNest/lib/playback/saveResume.ts AND content includes bounds OR duration_ms",
     "prover": _prove_save_resume},
    # 29
    {"id": 29, "artifact": "Physical iPad 9 in CI (Maestro flow)",
     "streams": ALL_STREAMS, "gate": "G1", "prover_type": "FS",
     "prover_spec": "exists MindfulNest/.maestro/iPad9_30min_flow.yaml",
     "prover": _prove_ipad9_maestro},
    # 30
    {"id": 30, "artifact": "Staging environment with real R2 bucket",
     "streams": ["F", "G"], "gate": "G1", "prover_type": "FS",
     "prover_spec": "exists MindfulNest/.firebaserc AND content contains staging",
     "prover": _prove_staging_firebaserc},
    # 31
    {"id": 31, "artifact": "LD-450 endurance gate POC",
     "streams": ["A", "C"], "gate": "G1", "prover_type": "DIR",
     "prover_spec": "prod_activity_log filter action contains ld450_endurance order by created_at desc; check status in details JSON",
     "prover": _prove_ld450_endurance},
    # 32
    {"id": 32, "artifact": "KWS state machine + 24h TTL",
     "streams": ["D1"], "gate": "G2", "prover_type": "COMP",
     "prover_spec": "FS exists Production/contracts/KWS_STATE_MACHINE.md AND DIR prod_blockers filter (title contains KWS) returns 0 open",
     "prover": _prove_kws_state_full},
    # 33
    {"id": 33, "artifact": "Entitlement state machine end-to-end",
     "streams": ["D1"], "gate": "G2", "prover_type": "COMP",
     "prover_spec": "FS exists Production/contracts/ENTITLEMENT_STATE_MACHINE.md AND DIR prod_blockers filter (title contains entitlement) returns 0 open",
     "prover": _prove_entitlement_state_full},
    # 34
    {"id": 34, "artifact": "Remote Config kill switches deployed + tested",
     "streams": ["D1"], "gate": "G2", "prover_type": "DIR",
     "prover_spec": "prod_activity_log filter action contains kill_switch AND details contains tested returns >= 5 rows (one per switch)",
     "prover": _prove_remote_config_kill_switches},
    # 35
    {"id": 35, "artifact": "Postmark transactional email minimum",
     "streams": ["H"], "gate": "G2", "prover_type": "DIR",
     "prover_spec": "prod_locked_decisions filter decision_key=STREAM_H_EMAIL_POSTMARK_V1 AND status=active returns 1 AND prod_activity_log filter action contains postmark_template returns >= 5 rows",
     "prover": _prove_postmark},
    # 36
    {"id": 36, "artifact": "3 runbooks tabletoped (G2 set)",
     "streams": ["G"], "gate": "G2", "prover_type": "COMP",
     "prover_spec": "FS exists Production/contracts/RUNBOOK_AI_COACH_UNSAFE_OUTPUT.md AND RUNBOOK_CDN_OUTAGE.md AND RUNBOOK_KWS_FAILURE.md AND DIR prod_activity_log filter action contains tabletop returns >= 3",
     "prover": _prove_runbooks_tabletoped},
    # 37
    {"id": 37, "artifact": "EAS Update channel + manual approval gate + tested rollback",
     "streams": ["C"], "gate": "G2", "prover_type": "FS",
     "prover_spec": "exists MindfulNest/eas.json AND content includes channel AND rollback",
     "prover": _prove_eas_update},
    # 38
    {"id": 38, "artifact": "Chipper Moments §6.16 illustrations + voice lines baked",
     "streams": ["A"], "gate": "G2", "prover_type": "DIR",
     "prover_spec": "prod_assets filter notes contains chipper_moment returns >= 8 rows",
     "prover": _prove_chipper_moments},
    # 39
    {"id": 39, "artifact": "AI Coach safety triple (token budget + classifier + PII scrubber)",
     "streams": ["D1"], "gate": "G2", "prover_type": "COMP",
     "prover_spec": "DIR prod_blockers filter (title contains AI Coach AND title contains safety) returns 0 open AND prod_activity_log filter action contains coach_safety returns >= 3",
     "prover": _prove_ai_coach_safety_triple},
    # 40
    {"id": 40, "artifact": "Stripe webhook idempotency hardening",
     "streams": ["D1"], "gate": "G3", "prover_type": "FS",
     "prover_spec": "exists MindfulNest/functions/src/stripe/webhook.ts AND content includes event.id AND dedupe",
     "prover": _prove_stripe_webhook_idempotent},
    # 41
    {"id": 41, "artifact": "Stripe-paid-but-COPPA-pending recovery flow",
     "streams": ["D1"], "gate": "G3", "prover_type": "DIR",
     "prover_spec": "prod_locked_decisions filter decision_key contains STRIPE_RECOVERY AND status=active returns >= 1",
     "prover": _prove_stripe_coppa_recovery},
    # 42
    {"id": 42, "artifact": "Affonso integration + idempotency keys + commission clawback",
     "streams": ["D1"], "gate": "G3", "prover_type": "COMP",
     "prover_spec": "DIR prod_blockers filter (title contains Affonso AND is_resolved=false) returns 0 AND prod_activity_log filter action contains affonso_attribution returns >= 1",
     "prover": _prove_affonso},
    # 43
    {"id": 43, "artifact": "Therapist commission fraud surface",
     "streams": ["D1"], "gate": "G3", "prover_type": "FS",
     "prover_spec": "exists Production/contracts/COMMISSION_FRAUD_SURFACE.md AND content includes rate_limit AND clawback",
     "prover": _prove_commission_fraud},
    # 44
    {"id": 44, "artifact": "Composite-index audit (firestore.indexes.json)",
     "streams": ["C"], "gate": "G3", "prover_type": "FS",
     "prover_spec": "exists MindfulNest/firestore.indexes.json",
     "prover": _prove_composite_index},
    # 45
    {"id": 45, "artifact": "Tabletop on Stripe disputed charge + refund + clawback",
     "streams": ["G"], "gate": "G3", "prover_type": "DIR",
     "prover_spec": "prod_activity_log filter action contains tabletop_stripe returns >= 1",
     "prover": _prove_tabletop_stripe},
    # 46
    {"id": 46, "artifact": "Parent COPPA portal (review/delete/revoke)",
     "streams": ["D2"], "gate": "G4", "prover_type": "FS",
     "prover_spec": "exists mindfulnest-parent-dashboard/ AND content includes routes for /review, /delete, /revoke",
     "prover": _prove_parent_coppa_portal},
    # 47
    {"id": 47, "artifact": "6-month-post-program retention scheduler",
     "streams": ["D1"], "gate": "G4", "prover_type": "FS",
     "prover_spec": "exists MindfulNest/functions/src/coppa_retention_scheduler.ts",
     "prover": _prove_retention_scheduler},
    # 48
    {"id": 48, "artifact": "Right-to-delete pipeline",
     "streams": ["D1"], "gate": "G4", "prover_type": "FS",
     "prover_spec": "exists MindfulNest/functions/src/right_to_delete.ts",
     "prover": _prove_right_to_delete},
    # 49
    {"id": 49, "artifact": "App Store evidence pack as Directus collection",
     "streams": ["E"], "gate": "G4", "prover_type": "DIR",
     "prover_spec": "Directus collection app_store_evidence_pack exists OR prod_reference_docs filter doc_category=app_store_evidence returns >= 5",
     "prover": _prove_app_store_evidence},
    # 50
    {"id": 50, "artifact": "CF deploy contract enforced",
     "streams": ["D1"], "gate": "G4", "prover_type": "FS",
     "prover_spec": "exists Production/contracts/CF_DEPLOY_CONTRACT.md AND content includes maintenance_mode AND force_update_required",
     "prover": _prove_cf_deploy_contract_full},
    # 51
    {"id": 51, "artifact": "Release artifact audit script",
     "streams": ["E"], "gate": "G4", "prover_type": "FS",
     "prover_spec": "exists MindfulNest/scripts/qa/release_artifact_audit.mjs",
     "prover": _prove_release_artifact_audit},
    # 52
    {"id": 52, "artifact": "Cursor's CI Tier A/B/C structure",
     "streams": ALL_STREAMS, "gate": "G4", "prover_type": "FS-STUB",
     "prover_spec": "exists MindfulNest/.github/workflows/zero-error-qa.yml AND MindfulNest/package.json includes scripts qa:tier-a, qa:tier-b, qa:tier-c",
     "prover": _prove_cursor_ci_tiers},
]


# -----------------------------------------------------------------------------
# Per-cell status compute
# -----------------------------------------------------------------------------

def run_provers(dctx: DirectusContext) -> list[dict]:
    """Execute every prover and collect status + detail per artifact."""
    results = []
    for row in ARTIFACT_REGISTRY:
        try:
            status, detail = row["prover"](None, dctx)
        except Exception as e:  # noqa: BLE001 — never crash the dashboard on a prover bug
            status, detail = "RED", f"prover crashed: {type(e).__name__}: {e}"
        results.append({**row, "status": status, "detail": detail})
    return results


def _status_score(status: str) -> float:
    """Numeric score for completion math. STUB counts as 0.5 per Judgment Call 2."""
    return {
        "GREEN": 1.0,
        "YELLOW": 0.5,  # STUB / partial
        "RED": 0.0,
        "MISSING-REPO": 0.0,
        "GREY": 0.0,  # NOT-SCOPED
    }.get(status, 0.0)


def cell_status(artifacts: list[dict]) -> tuple[str, int, int]:
    """Aggregate a (stream, gate) cell. Returns (status, n_done_equiv, n_total).

    Status rules:
      GREY  — no artifacts in this cell (NOT-SCOPED)
      RED   — any artifact RED and zero GREEN
      YELLOW — partial completion or any YELLOW/MISSING-REPO present
      GREEN — all artifacts GREEN
    """
    if not artifacts:
        return "GREY", 0, 0
    n = len(artifacts)
    n_green = sum(1 for a in artifacts if a["status"] == "GREEN")
    n_yellow = sum(1 for a in artifacts if a["status"] == "YELLOW")
    n_missing_repo = sum(1 for a in artifacts if a["status"] == "MISSING-REPO")
    if n_green == n:
        return "GREEN", n, n
    if n_green == 0 and n_yellow == 0 and n_missing_repo == 0:
        return "RED", 0, n
    return "YELLOW", n_green, n


def per_stream_completion(results: list[dict]) -> dict[str, float]:
    """% complete per stream = (GREEN + 0.5×YELLOW) / total artifacts in stream."""
    out = {}
    for s in STREAMS:
        owned = [r for r in results if s in r["streams"]]
        if not owned:
            out[s] = 0.0
            continue
        score = sum(_status_score(r["status"]) for r in owned)
        out[s] = round(score / len(owned), 4)
    return out


def per_gate_completion(results: list[dict]) -> dict[str, float]:
    out = {}
    for g in GATES:
        owned = [r for r in results if r["gate"] == g]
        if not owned:
            out[g] = 0.0
            continue
        score = sum(_status_score(r["status"]) for r in owned)
        out[g] = round(score / len(owned), 4)
    return out


def cell_counts(results: list[dict]) -> dict[str, int]:
    counts = {"GREEN": 0, "YELLOW": 0, "RED": 0, "GREY_NOT_SCOPED": 0,
              "STUB": 0, "MISSING_REPO": 0}
    for r in results:
        s = r["status"]
        if s == "GREEN":
            counts["GREEN"] += 1
        elif s == "YELLOW":
            counts["YELLOW"] += 1
            if r["prover_type"] == "FS-STUB":
                counts["STUB"] += 1
        elif s == "RED":
            counts["RED"] += 1
        elif s == "MISSING-REPO":
            counts["MISSING_REPO"] += 1
            counts["RED"] += 1  # missing-repo also displays as effectively-red for cell math
        elif s == "GREY":
            counts["GREY_NOT_SCOPED"] += 1
    return counts


# -----------------------------------------------------------------------------
# HTML render (spec §9)
# -----------------------------------------------------------------------------

def _safe(s: str | None) -> str:
    if s is None:
        return ""
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _status_color(status: str) -> str:
    return {
        "GREEN": COLOR["GREEN"],
        "YELLOW": COLOR["YELLOW"],
        "RED": COLOR["RED"],
        "MISSING-REPO": COLOR["RED"],
        "GREY": COLOR["GREY"],
    }.get(status, COLOR["GREY"])


def render_html(results: list[dict],
                per_stream: dict[str, float],
                per_gate: dict[str, float],
                blockers: list[dict],
                latest_activity: list[dict],
                dctx: DirectusContext,
                run_ts_utc: str,
                queued_writes_count: int) -> str:
    """f-string accumulator. No templating engine."""
    counts = cell_counts(results)

    parts: list[str] = []
    parts.append(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>MindfulNest Stream Progress Dashboard — {run_ts_utc}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         background: {COLOR['BG']}; color: {COLOR['DARK']}; margin: 0;
         padding: 24px; }}
  .card {{ background: {COLOR['CARD']}; border: 1px solid #e5e7eb; border-radius: 10px;
           padding: 18px 22px; margin-bottom: 18px;
           box-shadow: 0 1px 2px rgba(0,0,0,.04); }}
  h1 {{ margin: 0 0 6px; font-size: 22px; }}
  h2 {{ margin: 0 0 10px; font-size: 17px; color: #374151; }}
  h3 {{ margin: 14px 0 6px; font-size: 14px; color: #4b5563; }}
  .subtitle {{ color: #6b7280; font-size: 13px; }}
  .conf {{ font-size: 10px; padding: 1px 5px; border-radius: 3px; margin-left: 4px;
          font-weight: 600; }}
  .conf-confirmed {{ background: #dcfce7; color: #166534; }}
  .conf-inferred  {{ background: #fef9c3; color: #854d0e; }}
  .conf-guessed   {{ background: #fee2e2; color: #991b1b; }}
  .matrix {{ border-collapse: collapse; margin-top: 8px; width: 100%; }}
  .matrix th, .matrix td {{ border: 1px solid #e5e7eb; padding: 8px;
                             text-align: center; font-size: 13px; }}
  .matrix th {{ background: #f3f4f6; }}
  .pill {{ display: inline-block; padding: 2px 7px; border-radius: 999px;
           color: white; font-size: 11px; font-weight: 600; }}
  .bar {{ display: inline-block; width: 60%; height: 10px; background: #e5e7eb;
          border-radius: 5px; vertical-align: middle; margin-right: 8px;
          overflow: hidden; }}
  .bar-fill {{ display: block; height: 100%; }}
  .stream-card {{ display: grid; grid-template-columns: 80px 1fr 100px;
                  gap: 12px; padding: 8px 0; border-bottom: 1px dashed #e5e7eb; }}
  .stream-card:last-child {{ border-bottom: none; }}
  .stream-id {{ font-weight: 700; }}
  .banner-critical {{ background: #fef2f2; border: 2px solid {COLOR['RED']};
                      color: #991b1b; }}
  .banner-warn {{ background: #fefce8; border: 1px solid {COLOR['YELLOW']};
                  color: #854d0e; }}
  .legend {{ font-size: 11px; color: #6b7280; }}
  table.detail {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
  table.detail th, table.detail td {{ border-bottom: 1px solid #f3f4f6;
    padding: 6px 8px; text-align: left; vertical-align: top; }}
  code {{ font-size: 12px; background: #f3f4f6; padding: 1px 4px; border-radius: 3px; }}
</style>
</head>
<body>
<div class="card">
  <h1>MindfulNest Stream Progress Dashboard</h1>
  <div class="subtitle">
    Generated <strong>{_safe(run_ts_utc)} UTC</strong> &middot;
    Sources: Directus + filesystem &middot;
    Directus latency: <strong>{dctx.latency_ms} ms</strong> &middot;
    Queued offline writes: <strong>{queued_writes_count}</strong>
  </div>
  <div class="legend" style="margin-top:6px;">
    Confidence tags: {confirmed("source")} from direct lookup,
    {inferred("synthesis")} from heuristics (verify),
    {guessed("low confidence")} below threshold. Per CLAUDE.md Rule 24.
  </div>
</div>
""")

    # Schema + reachability banners (degraded modes per spec §12)
    if dctx.unreachable:
        parts.append(f"""
<div class="card banner-warn">
  <strong>Directus unreachable.</strong> All Directus-derived cells fall back to
  filesystem-only signals. Activity log queued offline. {inferred("connection")}
</div>
""")
    if dctx.auth_failed:
        parts.append(f"""
<div class="card banner-critical">
  <strong>Directus AUTH FAILED.</strong> Check API_KEYS_MASTER.md.
  Activity_log write halted.
</div>
""")
    if dctx.schema_mismatches:
        items = "".join(f"<li><code>{_safe(s)}</code></li>" for s in dctx.schema_mismatches)
        parts.append(f"""
<div class="card banner-critical">
  <h2>SCHEMA MISMATCH &middot; Rule 35 self-violation in dashboard</h2>
  <ul>{items}</ul>
</div>
""")

    # Overall progress
    parts.append('<div class="card"><h2>Overall progress (per gate)</h2>')
    for g in GATES:
        pct = per_gate.get(g, 0.0) * 100
        parts.append(
            f'<h3>{g} &middot; {pct:.1f}% '
            f'{confirmed("Directus + filesystem provers")}</h3>'
            f'<span class="bar"><span class="bar-fill" '
            f'style="width:{pct:.1f}%; background:{_status_color("GREEN" if pct>=95 else "YELLOW" if pct>0 else "RED")};"></span></span>'
            f'<span style="font-size:12px; color:#6b7280;">'
            f'{int(pct)}% complete (artifact-weighted; STUB counts 0.5)</span>'
        )
    g0_pct = per_gate.get("G0", 0.0)
    if g0_pct < 0.95:
        parts.append(f'<div style="color:{COLOR["RED"]}; font-weight:600; margin-top:10px;">'
                     '⚠ G0 NOT COMPLETE — cannot start G1 work per LD-445'
                     f' {confirmed("LD-445 STREAM_G_TRIGGER_REVOKED_V1")}</div>')
    parts.append('</div>')

    # Stream × Gate matrix
    parts.append('<div class="card"><h2>Stream × Gate matrix</h2>')
    parts.append('<table class="matrix"><thead><tr><th>Stream</th>')
    for g in GATES:
        parts.append(f'<th>{g}</th>')
    parts.append('<th>%</th></tr></thead><tbody>')
    for s in STREAMS:
        parts.append(f'<tr><td style="text-align:left; font-weight:600;">'
                     f'{s} &middot; {_safe(STREAM_NAMES[s])}</td>')
        for g in GATES:
            cell_arts = [r for r in results if s in r["streams"] and r["gate"] == g]
            cs, n_done, n_total = cell_status(cell_arts)
            color = _status_color(cs)
            label = f"{n_done}/{n_total}" if n_total else "—"
            parts.append("\n")
            parts.append(
                f'<td style="background:{color}33; color:{COLOR["DARK"]};">'
                f'<span class="pill" style="background:{color};">{label}</span>'
                f'</td>'
            )
        pct = per_stream.get(s, 0.0) * 100
        parts.append(f'\n<td>{pct:.1f}%</td></tr>\n')
    parts.append('</tbody></table>')
    parts.append('<p class="legend">Cell = (artifacts GREEN) / (artifacts in cell). '
                 f'Color: green=all done, yellow=partial, red=none, grey=not scoped. '
                 f'{confirmed("ARTIFACT_REGISTRY 52 rows")}</p>')
    parts.append('</div>')

    # Per-stream cards
    parts.append('<div class="card"><h2>Per-stream cards</h2>')
    for s in STREAMS:
        owned = [r for r in results if s in r["streams"]]
        pct = per_stream.get(s, 0.0) * 100
        n_green = sum(1 for r in owned if r["status"] == "GREEN")
        n_yellow = sum(1 for r in owned if r["status"] == "YELLOW")
        parts.append(f"""<div class="stream-card">
  <div class="stream-id">{s}</div>
  <div>
    <strong>{_safe(STREAM_NAMES[s])}</strong>
    <div class="legend">live: {n_green} GREEN / {n_yellow} YELLOW / {len(owned)} total</div>
  </div>
  <div style="text-align:right;">
    <div style="font-size:18px; font-weight:600;">{pct:.1f}%</div>
  </div>
</div>""")
    parts.append('</div>')

    # G0 artifacts detail
    parts.append('<div class="card"><h2>G0 artifacts detail</h2>')
    parts.append('<table class="detail"><thead><tr>'
                 '<th>#</th><th>Artifact</th><th>Streams</th><th>Status</th>'
                 '<th>Detail</th></tr></thead><tbody>')
    for r in [r for r in results if r["gate"] == "G0"]:
        color = _status_color(r["status"])
        parts.append(
            f'\n<tr>'
            f'\n  <td>{r["id"]}</td>'
            f'\n  <td>{_safe(r["artifact"])}</td>'
            f'\n  <td>{",".join(r["streams"]) if len(r["streams"])<=4 else "All"}</td>'
            f'\n  <td><span class="pill" style="background:{color};">{r["status"]}</span></td>'
            f'\n  <td><code>{_safe(r["detail"])[:120]}</code></td>'
            f'\n</tr>'
        )
    parts.append('\n</tbody></table></div>\n')

    # Dependency warnings
    parts.append('<div class="card"><h2>Dependency warnings</h2>')
    parts.append('<ul>')
    g0 = per_gate.get("G0", 0.0)
    parts.append(f'<li>🚫 G1 work blocked until G0 hits 95% (currently {g0*100:.1f}%) '
                 f'{confirmed("LD-445")}</li>')
    parts.append('<li>🚫 Stream C catalog wiring: blocked by G0 contracts (PLAYER_LIFECYCLE, '
                 f'MANIFEST_SCHEMA_V1) {inferred("v6 §2.1 dependency DAG")}</li>')
    parts.append('<li>🚫 Stream F upload pipeline: blocked by Manifest Schema v1 '
                 f'{confirmed("v6 §5.4 + §14.13")}</li>')
    parts.append('<li>🚫 Stream D2-MVP: blocked by G2 (KWS + entitlement) '
                 f'{confirmed("LD-433 + LD-432")}</li>')
    parts.append(f'<li>✓ Stream A content production: parallel-safe {confirmed("v6 §2")}</li>')
    parts.append(f'<li>✓ G0 foundation work: unblocked, START NOW per LD-445</li>')
    parts.append('</ul></div>')

    # Open blockers
    parts.append('<div class="card"><h2>Open blockers (severity high+)</h2>')
    if blockers:
        parts.append('<table class="detail"><thead><tr><th>#</th><th>Severity</th>'
                     '<th>Title</th></tr></thead><tbody>')
        for b in blockers[:20]:
            sev = (b.get("severity") or "").lower()
            parts.append(
                f'\n<tr>'
                f'\n  <td>#{b.get("id")}</td>'
                f'\n  <td>{_safe(sev)}</td>'
                f'\n  <td>{_safe(b.get("title") or "")}</td>'
                f'\n</tr>'
            )
        parts.append('</tbody></table>')
    else:
        parts.append('<p class="legend">No open high+ blockers '
                     f'{confirmed("prod_blockers query")}</p>')
    parts.append('</div>')

    # Latest activity
    parts.append('<div class="card"><h2>Latest activity (last 5)</h2>')
    if latest_activity:
        parts.append('<table class="detail"><thead><tr><th>id</th><th>created_at</th>'
                     '<th>action</th><th>by</th></tr></thead><tbody>')
        for a in latest_activity[:5]:
            parts.append(
                f'\n<tr>'
                f'\n  <td>#{a.get("id")}</td>'
                f'\n  <td>{_safe(a.get("created_at") or "")}</td>'
                f'\n  <td>{_safe(a.get("action") or "")}</td>'
                f'\n  <td>{_safe(a.get("performed_by") or "")}</td>'
                f'\n</tr>'
            )
        parts.append('</tbody></table>')
    else:
        parts.append('<p class="legend">(unavailable)</p>')
    parts.append('</div>')

    # Footer
    parts.append(f"""<div class="card">
  <div class="subtitle">
    Re-run: <code>python3 Production/scripts/stream_progress_dashboard.py</code><br/>
    Spec: <code>Production/specs/STREAM_PROGRESS_DASHBOARD_SPEC_v1.md</code>
    (md5 <code>62bb0dd9e55caeb2d25abacfafc97f01</code>)
  </div>
</div>
</body></html>
""")
    return "".join(parts)


# -----------------------------------------------------------------------------
# Output / browser open / activity log
# -----------------------------------------------------------------------------

def _md5(path: Path) -> str:
    if not path.exists():
        return "(missing)"
    h = hashlib.md5()
    h.update(path.read_bytes())
    return h.hexdigest()


def _open_in_browser(path: Path) -> None:
    system = _platform.system()
    try:
        if system == "Darwin":
            subprocess.run(["open", str(path)], check=False)
            subprocess.run(["osascript", "-e", 'tell application "Safari" to activate'],
                           check=False)
        elif system == "Windows":
            subprocess.run(["cmd", "/c", "start", "", str(path)], check=False, shell=False)
        else:
            subprocess.run(["xdg-open", str(path)], check=False)
    except OSError as e:
        print(f"Browser open failed: {e}. Open manually: {path}")


def _pending_queue_depth() -> int:
    p = PROJECT_ROOT / "pending_directus_writes.json"
    if not p.exists():
        return 0
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return len(data) if isinstance(data, list) else 0
    except (json.JSONDecodeError, OSError):
        return 0


def write_activity_log(dctx: DirectusContext, html_path: Path,
                       per_stream: dict[str, float],
                       per_gate: dict[str, float],
                       results: list[dict],
                       blockers: list[dict],
                       run_ts: str) -> dict:
    if dctx.auth_failed or dctx.unreachable:
        # Per spec §12: queue offline; do not silently drop.
        from lib.directus import queue_write_offline
        path = queue_write_offline(
            "prod_activity_log",
            {"action": "dashboard_render",
             "performed_by": "stream_progress_dashboard.py",
             "details": {"run_timestamp": run_ts, "html_output_path": str(html_path),
                         "directus_unreachable": dctx.unreachable,
                         "auth_failed": dctx.auth_failed}},
            reason="directus_unreachable_or_auth",
        )
        return {"queued": True, "path": str(path)}

    counts = cell_counts(results)

    payload = {
        "action": "dashboard_render",
        "performed_by": "stream_progress_dashboard.py",
        "details": {
            "run_timestamp": run_ts,
            "html_output_path": str(html_path.relative_to(PROJECT_ROOT))
                if str(html_path).startswith(str(PROJECT_ROOT)) else str(html_path),
            "directus_latency_ms": dctx.latency_ms,
            "queued_writes_at_run": _pending_queue_depth(),
            "cell_counts": counts,
            "stream_completion": per_stream,
            "gate_completion": per_gate,
            "open_blockers_count": len(blockers),
            "schema_mismatches": dctx.schema_mismatches,
        },
    }
    return try_post_or_queue("prod_activity_log", payload)


def maybe_register_reference_doc(dctx: DirectusContext) -> dict:
    """Idempotent registration of this script in prod_reference_docs (Rule 15)."""
    if dctx.client is None or dctx.unreachable or dctx.auth_failed:
        return {"skipped": True, "reason": "directus offline"}
    try:
        rows = dctx.client.get_items(
            "prod_reference_docs",
            filters={"file_path": {"_eq": "Production/scripts/stream_progress_dashboard.py"}},
            fields=["id"], limit=5,
        )
    except DirectusAdminError as e:
        return {"skipped": True, "reason": f"query failed: {e}"}
    if rows:
        return {"skipped": True, "reason": "already registered", "id": rows[0]["id"]}
    payload = {
        "doc_title": "Stream Progress Dashboard",
        "doc_version": "v1",
        "doc_category": "infrastructure",
        "file_path": "Production/scripts/stream_progress_dashboard.py",
        "status": "active",
        "is_current": True,
        "has_locked_decisions": False,
        "notes": ('Live canonical answer to "where are we in the parallel streams?" per '
                  'STREAM_PROGRESS_DASHBOARD_SPEC_v1 §3 source-of-truth contract.'),
    }
    return try_post_or_queue("prod_reference_docs", payload)


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="MindfulNest Stream Progress Dashboard")
    parser.add_argument("--no-open", action="store_true", help="Do not open browser")
    parser.add_argument("--no-log", action="store_true",
                        help="Do not write to prod_activity_log")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    run_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    run_slug = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")

    # Connect + schema-confirm
    dctx = DirectusContext(verbose=args.verbose)
    dctx.connect()
    dctx.confirm_schema()

    # Per spec §12 / §13 step 5: schema mismatch is a Rule 35 self-violation —
    # surface but do NOT halt unless catastrophic. We emit a banner and continue
    # so Kim still gets a dashboard view.

    # Run all 52 provers
    results = run_provers(dctx)

    # Aggregate
    per_stream = per_stream_completion(results)
    per_gate = per_gate_completion(results)

    # Sidebar data
    blockers, _ = dctx.probe(
        "prod_blockers",
        filters={"_and": [
            {"is_resolved": {"_eq": False}},
            {"_or": [{"severity": {"_eq": "high"}},
                     {"severity": {"_eq": "medium"}}]},
        ]},
        fields=["id", "title", "severity", "is_resolved"],
        sort="-id", limit=20,
    )
    blockers = blockers or []

    activity, _ = dctx.probe(
        "prod_activity_log",
        fields=["id", "action", "performed_by", "created_at"],
        sort="-id", limit=5,
    )
    activity = activity or []

    # Render
    queued = _pending_queue_depth()
    html = render_html(results, per_stream, per_gate,
                       blockers, activity, dctx, run_ts, queued)

    # Write
    DASHBOARDS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DASHBOARDS_DIR / f"stream_progress_{run_slug}.html"
    out_path.write_text(html, encoding="utf-8")

    # Activity log
    log_result = {"skipped": True, "reason": "--no-log"}
    if not args.no_log:
        log_result = write_activity_log(dctx, out_path, per_stream, per_gate,
                                        results, blockers, run_ts)

    # Idempotent reference-doc registration
    ref_result = maybe_register_reference_doc(dctx)

    # Browser open
    if not args.no_open:
        _open_in_browser(out_path)

    # One-line stdout summary
    counts = cell_counts(results)
    print(f"Dashboard at {out_path}. "
          f"{counts['RED']} RED / {counts['YELLOW']} YELLOW / {counts['GREEN']} GREEN / "
          f"{counts['GREY_NOT_SCOPED']} NOT-SCOPED. "
          f"Directus: {'auth-failed' if dctx.auth_failed else 'unreachable' if dctx.unreachable else 'ok'}.")
    print(f"  activity_log: {log_result}")
    print(f"  reference_doc: {ref_result}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
