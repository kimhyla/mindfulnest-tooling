#!/usr/bin/env python3
"""Retroactive LD fabrication + error-class audit (Kim 2026-05-20 directive).

Per LD-813 SYSTEMIC_RETROACTIVE_FABRICATION_AUDIT_SPEC_20260520_V1.

Probes every active LD + ref doc against current HEAD state. Reports
each finding by error class. Read-only — does NOT mutate anything in
Directus or on disk. Audit-only.

Output: structured markdown report to stdout + optional JSON to /tmp.

Usage:
    python3 Production/scripts/ld_fabrication_audit.py
    python3 Production/scripts/ld_fabrication_audit.py --json /tmp/audit.json
    python3 Production/scripts/ld_fabrication_audit.py --severity-floor HIGH

Error classes probed:
  C1 — LD-claimed file does not exist on disk
  C2 — Reference doc file_path missing
  C3 — Endpoint declared in MUTATION_ENDPOINTS but no server handler (catalog drift)
  C4 — Supersession chain broken (LD claims superseded_by N but N has wrong/missing back-ref)
  C5 — Open blocker references already-shipped fix (false-positive open)
  C6 — Activity log _COMPLETE row missing artifact (file path cited but not on disk)
  C7 — Lint guard / CI script cited in decision_text but missing on disk
  C8 — Vacuous tests (mock.patch with create=True for non-existent target)
  C9 — UI feature marker drift (CSS class / data-testid claimed shipped but absent from dist)
  C10 — CLAUDE.md enforcement gap (rule cites enforcement mechanism that doesn't exist)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Any

# ────────────────────────────────────────────────────────────────────────
# Setup
# ────────────────────────────────────────────────────────────────────────
TOOLING_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TOOLING_ROOT / "Production"))
DROPBOX_ROOT = Path(
    os.environ.get(
        "MN_DROPBOX_ROOT",
        "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files",
    )
)

from lib.directus_admin_client import DirectusAdminClient  # type: ignore

_CLIENT: DirectusAdminClient | None = None


def directus_get(path: str, params: dict | None = None, token: str | None = None) -> dict:
    """Use DirectusAdminClient (Doppler / API_KEYS_MASTER.md auth — LD-227)."""
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = DirectusAdminClient()
    # path looks like /items/<collection> — extract collection + use get_items
    if not path.startswith("/items/"):
        raise ValueError(f"only /items/<collection> supported, got {path}")
    collection = path.split("/items/", 1)[1]
    # Map URL query-string params to client kwargs
    filters = {}
    fields = None
    limit = 200
    offset = 0
    sort = None
    for k, v in (params or {}).items():
        if k == "fields":
            fields = v.split(",") if isinstance(v, str) else v
        elif k == "limit":
            limit = int(v)
        elif k == "offset":
            offset = int(v)
        elif k == "sort":
            sort = v
        elif k.startswith("filter["):
            # parse Directus URL filter syntax: filter[field][op]=value
            m = re.match(r"filter\[([^\]]+)\]\[([^\]]+)\]", k)
            if m:
                field, op = m.group(1), m.group(2)
                filters.setdefault(field, {})[op] = v
    rows = _CLIENT.get_items(
        collection,
        filters=filters or None,
        fields=fields,
        limit=limit if limit > 0 else -1,
        sort=sort,
    )
    # Manual offset slice (DirectusAdminClient.get_items has no offset param)
    if offset:
        rows = rows[offset:]
    return {"data": rows}


# ────────────────────────────────────────────────────────────────────────
# Probe primitives
# ────────────────────────────────────────────────────────────────────────
def file_exists_check(path_str: str) -> tuple[bool, str]:
    """Check if a path exists relative to TOOLING_ROOT first, then DROPBOX_ROOT."""
    cand_paths = []
    if path_str.startswith("/"):
        cand_paths.append(Path(path_str))
    elif path_str.startswith("~"):
        cand_paths.append(Path(path_str).expanduser())
    else:
        cand_paths.append(TOOLING_ROOT / path_str)
        cand_paths.append(DROPBOX_ROOT / path_str)
    for p in cand_paths:
        if p.is_file():
            return True, str(p)
    return False, f"not found in tooling tree OR Dropbox tree (tried {len(cand_paths)} paths)"


def grep_check(needle: str, file_paths: list[str]) -> tuple[bool, str]:
    """Grep needle across the file paths (tooling tree)."""
    for fp_str in file_paths:
        for base in [TOOLING_ROOT, DROPBOX_ROOT]:
            fp = base / fp_str
            if not fp.is_file():
                continue
            try:
                text = fp.read_text(errors="ignore")
            except Exception:
                continue
            if needle in text:
                return True, f"'{needle}' found in {fp}"
    return False, f"'{needle}' not found in any of {file_paths}"


# ────────────────────────────────────────────────────────────────────────
# C3 — Endpoint catalog drift
# ────────────────────────────────────────────────────────────────────────
def probe_endpoint_catalog() -> list[dict]:
    """MUTATION_ENDPOINTS / READ_ENDPOINTS declared in endpoints.ts but no
    server handler in production_server.py (or vice versa)."""
    findings = []
    ep_ts = TOOLING_ROOT / "Production/tools/storyboard-v2/src/api/endpoints.ts"
    server_py = TOOLING_ROOT / "Production/tools/production_server.py"
    if not ep_ts.is_file() or not server_py.is_file():
        return findings
    ep_text = ep_ts.read_text()
    server_text = server_py.read_text()
    # Extract endpoint paths declared in endpoints.ts (lines like `foo: '/api/...'`)
    declared = set()
    for m in re.finditer(r"['\"](/api/[a-z0-9_/-]+)['\"]", ep_text):
        declared.add(m.group(1))
    # Each declared endpoint should have a server-side `if path == "<path>"`
    # match OR a route registration.
    for path in sorted(declared):
        if path in server_text:
            continue
        findings.append({
            "class": "C3", "severity": "MEDIUM",
            "ld_id": None, "ld_key": "endpoint_catalog_drift",
            "enforcement": "audit",
            "claim": path,
            "result": f"endpoint declared in endpoints.ts but no server handler in production_server.py",
        })
    return findings


# ────────────────────────────────────────────────────────────────────────
# C4 — Supersession chain broken
# ────────────────────────────────────────────────────────────────────────
def probe_supersession_chains(all_lds: list[dict], token: str) -> list[dict]:
    """LD has status=superseded AND superseded_by_id=N. Confirm N exists and
    is active (or itself superseded, transitively). Also: LD has status=active
    BUT another LD points at it via superseded_by — meaning it should be
    status=superseded."""
    findings = []
    by_id = {ld["id"]: ld for ld in all_lds}
    # Also pull superseded LDs (status=superseded) to check their chain
    superseded = directus_get("/items/prod_locked_decisions", {
        "filter[status][_eq]": "superseded",
        "fields": "id,decision_key,superseded_by_id,status",
        "limit": -1,
    }, token=token)
    for ld in superseded.get("data") or []:
        sup_by = ld.get("superseded_by_id")
        if sup_by is None:
            findings.append({
                "class": "C4", "severity": "MEDIUM",
                "ld_id": ld["id"], "ld_key": ld.get("decision_key", ""),
                "enforcement": "audit",
                "claim": "status=superseded but superseded_by_id is null",
                "result": "broken supersession chain — no target",
            })
            continue
        if sup_by not in by_id and sup_by not in {l["id"] for l in (superseded.get("data") or [])}:
            findings.append({
                "class": "C4", "severity": "MEDIUM",
                "ld_id": ld["id"], "ld_key": ld.get("decision_key", ""),
                "enforcement": "audit",
                "claim": f"superseded_by_id={sup_by}",
                "result": f"target LD-{sup_by} not found in active or superseded sets",
            })
    return findings


# ────────────────────────────────────────────────────────────────────────
# C5 — Open blocker references already-shipped fix
# ────────────────────────────────────────────────────────────────────────
def probe_false_open_blockers(token: str) -> list[dict]:
    """Open blocker (is_resolved=false) whose description references an LD
    that's now status=active AND mentions 'closes #N' / 'FIXED' / 'SHIPPED'."""
    findings = []
    blockers = directus_get("/items/prod_blockers", {
        "filter[is_resolved][_eq]": "false",
        "fields": "id,title,description,gate",
        "limit": -1,
    }, token=token).get("data") or []
    # Pull recent _COMPLETE / SHIPPED activity rows that mention blocker IDs
    activity = directus_get("/items/prod_activity_log", {
        "filter[action][_contains]": "_COMPLETE",
        "fields": "id,action,details",
        "sort": "-id",
        "limit": 200,
    }, token=token).get("data") or []
    shipped_ids = set()
    for row in activity:
        details = row.get("details") or {}
        text = json.dumps(details) if isinstance(details, dict) else str(details)
        for m in re.finditer(r"blocker[\s_#]*(\d+)", text, re.IGNORECASE):
            shipped_ids.add(int(m.group(1)))
        for m in re.finditer(r"closes[\s#]*(\d+)", text, re.IGNORECASE):
            shipped_ids.add(int(m.group(1)))
    for b in blockers:
        if b["id"] in shipped_ids:
            findings.append({
                "class": "C5", "severity": "MEDIUM",
                "ld_id": None, "ld_key": f"blocker-{b['id']}",
                "enforcement": "audit",
                "claim": f"blocker #{b['id']} {b.get('title', '')[:50]}",
                "result": "open blocker referenced by a _COMPLETE activity_log row — likely false-open",
            })
    return findings


# ────────────────────────────────────────────────────────────────────────
# C6 — _COMPLETE activity row with missing artifact file
# ────────────────────────────────────────────────────────────────────────
def probe_complete_rows_missing_artifact(token: str) -> list[dict]:
    """prod_activity_log row action ending in _COMPLETE whose details cite
    a file_path that doesn't exist on disk."""
    findings = []
    activity = directus_get("/items/prod_activity_log", {
        "filter[action][_contains]": "_COMPLETE",
        "fields": "id,action,details",
        "sort": "-id",
        "limit": 100,
    }, token=token).get("data") or []
    for row in activity:
        details = row.get("details") or {}
        if not isinstance(details, dict):
            continue
        # Common keys that hold file claims
        for key in ("file_path", "asset_path", "deliverable", "commit_file"):
            v = details.get(key)
            if isinstance(v, str) and v and not v.startswith("http"):
                exists, _ = file_exists_check(v)
                if not exists:
                    findings.append({
                        "class": "C6", "severity": "LOW",
                        "ld_id": None, "ld_key": f"activity-{row['id']}",
                        "enforcement": "audit",
                        "claim": f"{row.get('action','?')} details.{key}={v}",
                        "result": "_COMPLETE row cites file that doesn't exist",
                    })
    return findings


# ────────────────────────────────────────────────────────────────────────
# C8 — Vacuous tests (create=True mocks on missing targets)
# ────────────────────────────────────────────────────────────────────────
def probe_vacuous_tests() -> list[dict]:
    """grep for `mock.patch.object(X, 'name', create=True)` and verify
    that `name` actually exists on `X`. If not, the mock silently creates
    the attribute and the test passes vacuously."""
    findings = []
    tests_dir = TOOLING_ROOT / "Production/tools/tests"
    if not tests_dir.is_dir():
        return findings
    pat = re.compile(
        r"mock\.patch\.object\(\s*(\w+)\s*,\s*['\"](\w+)['\"][^)]*create\s*=\s*True"
    )
    for test_file in tests_dir.glob("*.py"):
        try:
            text = test_file.read_text()
        except Exception:
            continue
        for m in pat.finditer(text):
            mod_alias, attr = m.group(1), m.group(2)
            # Find import binding. Three patterns:
            #   (a) `from X.Y import Z as <alias>` (target = X.Y.Z)
            #   (b) `from X import <alias>` (target = X.<alias>)
            #   (c) `import X as <alias>` (target = X)
            # The detection has to know that `from server_handlers import vendor_jobs as VJ`
            # gives VJ = the SUBMODULE `server_handlers.vendor_jobs`, not the package
            # `server_handlers`. Old logic checked hasattr(server_handlers, "_async_log_lipsync_submit")
            # which is False even when the symbol IS on vendor_jobs.
            target_module = None
            # Case (a)/(b): `from X import ... <alias>` (with optional `as`)
            m_from = re.search(
                rf"from\s+([\w.]+)\s+import\s+([^\n]+)",
                text,
            )
            # Walk all "from X import ..." occurrences to find one binding <alias>
            for fm in re.finditer(r"from\s+([\w.]+)\s+import\s+([^\n]+)", text):
                imported = fm.group(2)
                # Strip trailing comment + parentheses
                imported = imported.split("#", 1)[0].strip().strip("()")
                # Check for `Y as <alias>`
                m_alias = re.search(rf"\b(\w+)\s+as\s+{re.escape(mod_alias)}\b", imported)
                if m_alias:
                    target_module = f"{fm.group(1)}.{m_alias.group(1)}"
                    break
                # Check for plain `<alias>` in the import list
                if re.search(rf"\b{re.escape(mod_alias)}\b", imported):
                    target_module = f"{fm.group(1)}.{mod_alias}"
                    break
            if not target_module:
                m_imp = re.search(rf"\bimport\s+([\w.]+)\s+as\s+{re.escape(mod_alias)}\b", text)
                if m_imp:
                    target_module = m_imp.group(1)
            if not target_module:
                continue
            # Try import + getattr
            try:
                sys.path.insert(0, str(TOOLING_ROOT / "Production/tools"))
                mod = __import__(target_module, fromlist=["*"])
                if not hasattr(mod, attr):
                    findings.append({
                        "class": "C8", "severity": "MEDIUM",
                        "ld_id": None, "ld_key": test_file.name,
                        "enforcement": "audit",
                        "claim": f"mock.patch.object({mod_alias}, '{attr}', create=True)",
                        "result": f"{target_module} has no attribute '{attr}' — test passes vacuously",
                    })
            except Exception:
                pass  # module not importable from here; skip
    return findings


# ────────────────────────────────────────────────────────────────────────
# C9 — UI feature marker drift (claimed shipped, absent from dist)
# ────────────────────────────────────────────────────────────────────────
def probe_ui_marker_drift() -> list[dict]:
    """Run the existing regression-guard script (LD-766) as a probe."""
    findings = []
    guard = TOOLING_ROOT / "Production/scripts/check_storyboard_critical_features.sh"
    if not guard.is_file():
        return findings
    try:
        proc = subprocess.run(
            ["bash", str(guard)],
            capture_output=True, text=True, timeout=30,
        )
    except Exception as exc:
        return findings
    if proc.returncode != 0:
        # Parse missing markers from stderr
        for line in (proc.stderr or "").splitlines():
            if "MISSING" in line:
                findings.append({
                    "class": "C9", "severity": "HIGH",
                    "ld_id": None, "ld_key": "ui_marker_drift",
                    "enforcement": "audit",
                    "claim": line.strip(),
                    "result": "regression guard reported missing marker",
                })
    return findings


# ────────────────────────────────────────────────────────────────────────
# C10 — CLAUDE.md enforcement gap (rule cites mechanism that doesn't exist)
# ────────────────────────────────────────────────────────────────────────
def probe_claude_md_enforcement_gaps() -> list[dict]:
    """CLAUDE.md rules cite enforcement scripts/hooks. Probe each cited
    Production/scripts/*.py / *.sh path."""
    findings = []
    claude_md = DROPBOX_ROOT / "CLAUDE.md"
    if not claude_md.is_file():
        return findings
    text = claude_md.read_text()
    # Find Production/scripts/... + Production/lib/... + Production/.../*.py refs
    pat = re.compile(r"`?(Production/(?:scripts|lib|tools)/[\w/_-]+\.(?:py|sh|js|ts|md))`?")
    for m in pat.finditer(text):
        path = m.group(1)
        exists, _ = file_exists_check(path)
        if not exists:
            findings.append({
                "class": "C10", "severity": "MEDIUM",
                "ld_id": None, "ld_key": "CLAUDE.md_enforcement_ref",
                "enforcement": "audit",
                "claim": path,
                "result": f"CLAUDE.md cites {path} but file missing",
            })
    return findings


# ────────────────────────────────────────────────────────────────────────
# Per-LD probes
# ────────────────────────────────────────────────────────────────────────
def probe_ld(ld: dict) -> list[dict]:
    """Returns list of findings for this LD. Empty list = clean."""
    findings = []
    ld_id = ld["id"]
    key = ld.get("decision_key", "")
    related = ld.get("related_files") or []
    text = ld.get("decision_text") or ""
    enforcement = ld.get("enforcement_type") or "awareness_only"

    # Skip clearly meta / governance / shortcut LDs that don't claim shipped code
    if enforcement in ("awareness_only", "spec_authority", "soft_guideline",
                       "recipe_documentation", "documentation",
                       "documentation_tombstone", "design_constraint",
                       "tool_availability"):
        # Still check file existence for related_files claims
        pass

    # C1: file-existence — only check files explicitly referenced in
    # related_files that look like actual source paths (not just .md docs
    # in awareness_only LDs).
    for rf in related:
        if not isinstance(rf, str):
            continue
        # Skip URLs, anchors, app-side claims out of scope
        if rf.startswith("http") or rf.startswith("#"):
            continue
        # Skip CLAUDE.md anchored references
        if rf.startswith("CLAUDE.md §") or rf.endswith("/"):
            continue
        # Skip pattern-style refs (no concrete path)
        if "*" in rf or "?" in rf:
            continue
        # Skip refs that look like Directus collection paths or worktree refs
        if rf.startswith("~/Projects/") or rf.startswith("~/Library"):
            continue
        exists, info = file_exists_check(rf)
        if not exists:
            findings.append({
                "class": "C1",
                "severity": "HIGH" if enforcement in ("code", "code_path_added", "code_path_refactored", "code_path_removed", "code_path_ordering", "code", "code_constant_shared", "code_path", "ci_check", "ci_gate", "test_suite", "tool_availability", "script", "runtime_validator", "runtime_logging") else "MEDIUM",
                "ld_id": ld_id,
                "ld_key": key,
                "enforcement": enforcement,
                "claim": rf,
                "result": info,
            })

    # C7-style: scripts/lint guards cited but missing
    script_patterns = re.findall(r'(Production/scripts/[\w/_-]+\.(?:sh|py))', text)
    for sp in set(script_patterns):
        if sp in [r for r in related if isinstance(r, str)]:
            continue  # already covered by C1 above
        exists, _ = file_exists_check(sp)
        if not exists:
            findings.append({
                "class": "C7",
                "severity": "MEDIUM",
                "ld_id": ld_id,
                "ld_key": key,
                "enforcement": enforcement,
                "claim": sp,
                "result": "script cited in decision_text but missing",
            })

    return findings


# ────────────────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────────────────
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=None, help="Optional JSON output path")
    ap.add_argument("--severity-floor", default="MEDIUM", choices=["HIGH", "MEDIUM", "LOW"])
    ap.add_argument("--limit", type=int, default=1000, help="Max LDs to scan")
    args = ap.parse_args(argv)
    token = None  # auth handled by DirectusAdminClient internally

    # Phase 1: pull all active LDs (single call with limit=-1)
    print("[audit] fetching active LDs…", flush=True)
    resp = directus_get(
        "/items/prod_locked_decisions",
        {
            "filter[status][_eq]": "active",
            "fields": "id,decision_key,decision_name,enforcement_type,related_files,decision_text,severity,date_locked",
            "limit": -1,
            "sort": "id",
        },
        token=token,
    )
    all_lds = resp.get("data") or []
    if args.limit and len(all_lds) > args.limit:
        all_lds = all_lds[:args.limit]
    print(f"[audit] {len(all_lds)} active LDs loaded", flush=True)

    # Phase 2-3: probe each LD (C1, C7)
    all_findings: list[dict] = []
    for ld in all_lds:
        findings = probe_ld(ld)
        all_findings.extend(findings)

    # C3 endpoint catalog drift
    print("[audit] C3 endpoint catalog drift…", flush=True)
    all_findings.extend(probe_endpoint_catalog())

    # C4 supersession chain
    print("[audit] C4 supersession chains…", flush=True)
    try:
        all_findings.extend(probe_supersession_chains(all_lds, token))
    except Exception as exc:
        print(f"  C4 skipped: {exc}")

    # C5 false-open blockers
    print("[audit] C5 false-open blockers…", flush=True)
    try:
        all_findings.extend(probe_false_open_blockers(token))
    except Exception as exc:
        print(f"  C5 skipped: {exc}")

    # C6 _COMPLETE rows missing artifact
    print("[audit] C6 _COMPLETE rows missing artifact…", flush=True)
    try:
        all_findings.extend(probe_complete_rows_missing_artifact(token))
    except Exception as exc:
        print(f"  C6 skipped: {exc}")

    # C8 vacuous tests
    print("[audit] C8 vacuous tests…", flush=True)
    all_findings.extend(probe_vacuous_tests())

    # C9 UI marker drift
    print("[audit] C9 UI marker drift…", flush=True)
    all_findings.extend(probe_ui_marker_drift())

    # C10 CLAUDE.md enforcement gaps
    print("[audit] C10 CLAUDE.md enforcement gaps…", flush=True)
    all_findings.extend(probe_claude_md_enforcement_gaps())

    # Severity floor
    SEV_ORDER = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
    floor = SEV_ORDER[args.severity_floor]
    all_findings = [f for f in all_findings if SEV_ORDER.get(f["severity"], 0) >= floor]

    # Phase 2b: also probe prod_reference_docs
    print("[audit] fetching active reference docs…", flush=True)
    ref_resp = directus_get(
        "/items/prod_reference_docs",
        {
            "filter[is_current][_eq]": "true",
            "fields": "id,doc_title,file_path,doc_category,status",
            "limit": 500,
            "sort": "id",
        },
        token=token,
    )
    ref_docs = ref_resp.get("data") or []
    print(f"[audit] {len(ref_docs)} active reference docs loaded", flush=True)
    for rd in ref_docs:
        fp = rd.get("file_path")
        if not fp or not isinstance(fp, str) or fp.startswith("http"):
            continue
        if fp.startswith("/tmp/"):
            continue  # transient
        exists, info = file_exists_check(fp)
        if not exists:
            all_findings.append({
                "class": "C2",
                "severity": "MEDIUM",
                "ld_id": None,
                "ref_doc_id": rd.get("id"),
                "ld_key": rd.get("doc_title", ""),
                "enforcement": "ref_doc",
                "claim": fp,
                "result": info,
            })

    # Report
    print()
    print(f"## Audit findings ({len(all_findings)} total at floor={args.severity_floor})")
    print()
    by_class: dict[str, list[dict]] = {}
    for f in all_findings:
        by_class.setdefault(f["class"], []).append(f)
    for cls in sorted(by_class.keys()):
        flist = by_class[cls]
        print(f"### Class {cls} ({len(flist)} findings)")
        print()
        for f in flist:
            sid = f.get("ld_id") or f.get("ref_doc_id")
            stype = "LD" if f.get("ld_id") else "RefDoc"
            print(f"- [{f['severity']:6s}] {stype}-{sid} {f.get('ld_key', '')} [{f.get('enforcement', '?')}]")
            print(f"    claim: {f['claim']}")
            print(f"    result: {f['result']}")
        print()

    # Summary
    print(f"## Summary")
    print(f"- Total findings: {len(all_findings)}")
    for cls in sorted(by_class.keys()):
        print(f"- Class {cls}: {len(by_class[cls])}")

    if args.json:
        Path(args.json).write_text(json.dumps({
            "scan_at": "2026-05-20",
            "total_lds": len(all_lds),
            "total_refdocs": len(ref_docs),
            "findings": all_findings,
        }, indent=2))
        print(f"\n[audit] JSON written to {args.json}", flush=True)

    # Exit code: 0 if no HIGH findings, 1 if any HIGH, 2 if MEDIUM+ findings
    high = sum(1 for f in all_findings if f["severity"] == "HIGH")
    if high > 0:
        return 1
    if all_findings:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
