#!/usr/bin/env python3
"""
patch_invariant_audit.py — Phase 0 detection script for fragile patterns
in MindfulNest Path B IIFE patches accumulated in storyboard tools.

Implements CLAUDE.md Rule 36 PATCH_INVARIANT_PERSISTENCE_V1 §36.2.

Greps a target storyboard HTML for prior patches' fragile selectors
(body>X, querySelector single-result, hardcoded [0] on collection results,
:nth-child / :first-child, etc.) and INVARIANT blocks. Reports findings.

Exit code:
  0  = clean (no fragile patterns OR all fragile patterns have explicit
       // FRAGILE-ACCEPTED: justification comment within 5 lines)
  1  = fragile patterns found without opt-in justification — author of
       new patch should review before adding their own selectors that
       might further constrain those invariants

USAGE:
  python3 Production/scripts/patch_invariant_audit.py <storyboard.html>
  python3 Production/scripts/patch_invariant_audit.py <storyboard.html> --json

Phase 0 preflight 187 (LD-pending PATCH_INVARIANT_PERSISTENCE_V1).
"""
import argparse
import json
import re
import sys
from pathlib import Path

# Patterns that have caused regressions in MindfulNest patch history.
# Each pattern has: regex, severity, description, mitigation.
FRAGILE_PATTERNS = [
    {
        "name": "body>X selector",
        "regex": re.compile(r"body\s*>\s*[a-zA-Z][\w.-]*"),
        "severity": "HIGH",
        "description": (
            "Parent-relative selector requires the matched element to be "
            "a DIRECT child of <body>. Future patches may move/clone the "
            "element to other parents, silently breaking this rule."
        ),
        "mitigation": (
            "Prefer class-only selector (e.g., `.foo`) and use specificity "
            "for narrowing. If body-anchored is genuinely required, add "
            "// FRAGILE-ACCEPTED: comment and document why."
        ),
    },
    {
        "name": "querySelector single-result",
        # Match querySelector( but NOT querySelectorAll( — negative lookahead
        "regex": re.compile(r"querySelector\((?!All)"),
        "severity": "MED",
        "description": (
            "Single-result querySelector returns only the FIRST match. "
            "Future patches may create additional instances of the same "
            "selector, which this code will silently ignore."
        ),
        "mitigation": (
            "Prefer querySelectorAll().forEach when the count of matches "
            "could grow. If single-result is genuinely intended, assert "
            "the count: `console.assert(qsa.length === 1, ...)`."
        ),
    },
    {
        "name": "hardcoded [0] on collection",
        "regex": re.compile(r"\.querySelectorAll\([^)]+\)\[0\]"),
        "severity": "MED",
        "description": (
            "Indexing [0] on a collection assumes single-element result. "
            "Same fragility as querySelector single-result."
        ),
        "mitigation": "Use querySelector() if single intended; or iterate.",
    },
    {
        "name": ":nth-child / :first-child",
        "regex": re.compile(r":(?:nth-child|first-child|last-child)\b"),
        "severity": "MED",
        "description": (
            "Position-based selectors break if siblings are added/reordered. "
            "Use class-based or attribute-based selectors instead."
        ),
        "mitigation": "Prefer .my-class or [data-role='foo']",
    },
    {
        "name": "parentNode.parentNode chain",
        "regex": re.compile(r"\.parentNode\.parentNode"),
        "severity": "MED",
        "description": (
            "Multi-step parent traversal assumes specific DOM nesting. "
            "Use closest('.target-class') instead."
        ),
        "mitigation": "Replace with elem.closest('.target-class')",
    },
]

# Opt-in marker that suppresses a finding within 5 lines
ACCEPTED_MARKER = re.compile(r"//\s*FRAGILE-ACCEPTED:")
INVARIANT_BLOCK = re.compile(r"//\s*INVARIANTS:")


def audit(html_path: Path) -> dict:
    text = html_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    findings = []
    invariants_found = []

    for i, line in enumerate(lines):
        # Track INVARIANT blocks for reporting
        if INVARIANT_BLOCK.search(line):
            block = []
            j = i
            while j < len(lines) and j < i + 20:
                if lines[j].strip().startswith("//"):
                    block.append(lines[j].strip())
                    j += 1
                else:
                    break
            invariants_found.append({"line": i + 1, "block": block})

        for pat in FRAGILE_PATTERNS:
            if pat["regex"].search(line):
                # Look for FRAGILE-ACCEPTED in surrounding 5 lines
                context_start = max(0, i - 5)
                context_end = min(len(lines), i + 6)
                context = lines[context_start:context_end]
                accepted = any(ACCEPTED_MARKER.search(cl) for cl in context)

                findings.append({
                    "line": i + 1,
                    "pattern": pat["name"],
                    "severity": pat["severity"],
                    "match": line.strip()[:200],
                    "accepted": accepted,
                    "description": pat["description"],
                    "mitigation": pat["mitigation"],
                })

    unacknowledged = [f for f in findings if not f["accepted"]]
    return {
        "file": str(html_path),
        "total_findings": len(findings),
        "unacknowledged": len(unacknowledged),
        "invariants_blocks_found": len(invariants_found),
        "findings": findings,
        "invariants": invariants_found,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("path", help="Storyboard HTML to audit")
    p.add_argument("--json", action="store_true", help="JSON output")
    args = p.parse_args()
    target = Path(args.path)
    if not target.exists():
        print(f"ERROR: {target} not found", file=sys.stderr)
        return 2

    report = audit(target)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"\n=== Patch Invariant Audit: {target.name} ===")
        print(f"Total findings: {report['total_findings']}")
        print(f"Unacknowledged: {report['unacknowledged']}")
        print(f"INVARIANT blocks found: {report['invariants_blocks_found']}")
        if report["unacknowledged"]:
            print(f"\nUNACKNOWLEDGED FRAGILE PATTERNS:")
            severity_counts = {}
            for f in report["findings"]:
                if not f["accepted"]:
                    severity_counts[f["severity"]] = severity_counts.get(f["severity"], 0) + 1
            for sev in ("HIGH", "MED", "LOW"):
                if sev in severity_counts:
                    print(f"  {sev}: {severity_counts[sev]}")
            print(f"\nFirst 5 unacknowledged findings:")
            shown = 0
            for f in report["findings"]:
                if f["accepted"] or shown >= 5:
                    continue
                print(f"  [L{f['line']:>5}] [{f['severity']}] {f['pattern']}")
                print(f"           {f['match']}")
                shown += 1
            print(f"\nMitigation: see CLAUDE.md Rule 36 PATCH_INVARIANT_PERSISTENCE_V1.")
            print(f"To suppress a specific finding, add `// FRAGILE-ACCEPTED: <reason>`")
            print(f"comment within 5 lines of the pattern.")

    # Exit code: 1 if any unacknowledged HIGH or MED, 0 otherwise
    has_unacknowledged_warning = any(
        not f["accepted"] and f["severity"] in ("HIGH", "MED")
        for f in report["findings"]
    )
    return 1 if has_unacknowledged_warning else 0


if __name__ == "__main__":
    sys.exit(main())
