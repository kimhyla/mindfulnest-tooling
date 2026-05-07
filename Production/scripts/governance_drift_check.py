#!/usr/bin/env python3
"""
governance_drift_check.py — surface LDs that no governance file cites.

Per overnight deliverable G (2026-04-19). Read-mostly: queries
`prod_locked_decisions` for severity ∈ {HIGH, CRITICAL} and status = active,
greps `Production/governance/*.md` for the decision_key (and a few common
alias forms), and emits an `app_blockers` row at severity=MEDIUM for each
uncited LD with title `LD {key} not cited in any governance checklist`.

De-dupes against existing unresolved blockers so reruns are idempotent.

Usage:
    python3 Production/scripts/governance_drift_check.py
    python3 Production/scripts/governance_drift_check.py --dry-run
    python3 Production/scripts/governance_drift_check.py --min-severity CRITICAL
    python3 Production/scripts/governance_drift_check.py --json    # machine-readable
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "Production"))

from lib.directus_admin_client import DirectusAdminClient, DirectusAdminError  # noqa: E402

GOV_GLOB = "Production/governance/*.md"

SEVERITY_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}


def normalize_severity(sev: str | None) -> str:
    return (sev or "").strip().upper()


def gather_governance_text(root: Path) -> str:
    """Concatenate every governance .md file's text into one searchable blob."""
    parts: list[str] = []
    for p in sorted(root.glob(GOV_GLOB)):
        try:
            parts.append(p.read_text())
        except OSError:
            continue
    return "\n\n".join(parts)


def alias_forms(decision_key: str) -> list[str]:
    """Return search forms a governance file might use for a decision_key.

    Captures the canonical key, an LD-NN form (when key starts with `LD-`),
    and an `LD <id>` form. Conservative: false negatives are recoverable on
    re-run, false positives mute the blocker which is the worse outcome.
    """
    forms = {decision_key, decision_key.upper(), decision_key.lower()}
    m = re.match(r"LD[-\s]?(\d+)$", decision_key, re.IGNORECASE)
    if m:
        n = m.group(1)
        forms.update({f"LD-{n}", f"LD {n}", f"LD{n}"})
    return [f for f in forms if f]


def is_cited(decision_key: str, blob: str) -> bool:
    for form in alias_forms(decision_key):
        if form in blob:
            return True
    return False


def existing_open_blockers(client) -> set[str]:
    """Return titles of unresolved governance-drift blockers, to de-dupe."""
    rows = client.get_items(
        "app_blockers",
        filters={
            "is_resolved": {"_eq": False},
            "title": {"_starts_with": "LD "},
        },
        fields=["id", "title", "is_resolved"],
        limit=-1,
    )
    titles = set()
    for r in rows:
        t = r.get("title") or ""
        if "not cited in any governance checklist" in t:
            titles.add(t)
    return titles


def run_drift_check(min_severity: str = "HIGH", dry_run: bool = False, as_json: bool = False) -> dict:
    client = DirectusAdminClient()
    threshold = SEVERITY_RANK.get(min_severity.upper(), SEVERITY_RANK["HIGH"])

    lds = client.get_items(
        "prod_locked_decisions",
        filters={"status": {"_eq": "active"}},
        fields=["id", "decision_key", "severity", "decision_name"],
        limit=-1,
    )
    in_scope = [
        ld for ld in lds
        if SEVERITY_RANK.get(normalize_severity(ld.get("severity")), 0) >= threshold
        and ld.get("decision_key")
    ]

    blob = gather_governance_text(REPO_ROOT)
    if not blob:
        msg = f"governance corpus empty under {REPO_ROOT/GOV_GLOB} — abort"
        if as_json:
            print(json.dumps({"error": msg}))
        else:
            print(f"[drift] ERROR: {msg}")
        return {"error": msg}

    uncited = [ld for ld in in_scope if not is_cited(ld["decision_key"], blob)]
    cited = len(in_scope) - len(uncited)

    existing = existing_open_blockers(client) if not dry_run else set()
    created: list[dict] = []
    skipped_dupes: list[str] = []
    failed: list[dict] = []
    pending_path = REPO_ROOT / "pending_directus_writes.json"

    for ld in uncited:
        title = f"LD {ld['decision_key']} not cited in any governance checklist"
        if title in existing:
            skipped_dupes.append(title)
            continue
        if dry_run:
            created.append({"would_create": title, "severity": "medium", "ld_id": ld["id"]})
            continue
        payload = {
            "feature_id": "governance",
            "title": title,
            "description": (
                f"Active LD `{ld['decision_key']}` (severity={ld.get('severity')}) "
                f"is not cited in any file under Production/governance/*.md.\n\n"
                f"LD name: {ld.get('decision_name') or '(none)'}\n"
                f"Source: governance_drift_check.py (overnight deliverable G).\n\n"
                f"Action: either cite this LD in the relevant skill governance "
                f"file, or close the LD if it is no longer active. The drift "
                f"check re-runs weekly via weekly_preflight_audit.py."
            ),
            "severity": "medium",
            "is_resolved": False,
        }
        # Retry-once + pending fallback per overnight directive.
        try:
            row = client.post_item("app_blockers", payload)
            created.append({"id": row.get("id"), "title": title, "ld_id": ld["id"]})
            continue
        except DirectusAdminError as e:
            first_err = str(e)
        try:
            row = client.post_item("app_blockers", payload)
            created.append({"id": row.get("id"), "title": title, "ld_id": ld["id"], "retry": True})
            continue
        except DirectusAdminError as e2:
            failed.append({"title": title, "error_first": first_err, "error_retry": str(e2)})
            try:
                with open(pending_path, "a") as fp:
                    fp.write(json.dumps({
                        "collection": "app_blockers",
                        "payload": payload,
                        "error": str(e2),
                        "source": "governance_drift_check.py",
                    }) + "\n")
            except OSError:
                pass

    summary = {
        "min_severity": min_severity.upper(),
        "active_lds_in_scope": len(in_scope),
        "cited_count": cited,
        "uncited_count": len(uncited),
        "blockers_created": len(created),
        "blockers_skipped_dupes": len(skipped_dupes),
        "blockers_failed": len(failed),
        "dry_run": dry_run,
    }

    if as_json:
        print(json.dumps({"summary": summary, "created": created,
                          "skipped_dupes": skipped_dupes, "failed": failed}, indent=2))
    else:
        print(f"[drift] {summary}")
        if failed:
            for f in failed:
                print(f"[drift]   FAILED: {f['title']} → {f['error']}")
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="Report only; do not write blockers")
    ap.add_argument("--min-severity", default="HIGH", choices=["HIGH", "CRITICAL"],
                    help="Minimum severity to scan (default HIGH)")
    ap.add_argument("--json", action="store_true", help="Machine-readable JSON output")
    args = ap.parse_args()
    summary = run_drift_check(min_severity=args.min_severity, dry_run=args.dry_run, as_json=args.json)
    return 0 if "error" not in summary else 1


if __name__ == "__main__":
    raise SystemExit(main())
