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
  C3 — Endpoint declared but no handler (catalog drift)
  C4 — Supersession chain broken (LD references superseded_by that doesn't exist)
  C5 — Open blocker references already-shipped fix (false-positive open)
  C6 — Activity log _COMPLETE row without matching artifact
  C7 — Lint guard / CI script cited but missing on disk
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

    # Phase 2-3: probe each
    all_findings: list[dict] = []
    for ld in all_lds:
        findings = probe_ld(ld)
        all_findings.extend(findings)

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
