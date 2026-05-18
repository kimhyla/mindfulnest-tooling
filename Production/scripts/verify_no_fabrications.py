#!/usr/bin/env python3
"""Phase 1.5 fabrication guard — codifies the LD-773 manifest.

Per V59 spec §Phase 1.5 (LD-794). Checks that the 8 fabricated LDs from the
2026-05-17 session audit (LD-773) remain absent from disk. If a fabricated
artifact ever reappears (e.g., a session re-creates the fake file), this
script fails the gate and surfaces the LD that authored the fabrication.

NEVER-DELETE protections (per spec):
- Production/lib/durable_job_registry.py — created by Phase 5 (real this time)
- Production/lib/state_repo.py — created by Phase 3 (already shipped)

This script does NOT actually delete anything — it only verifies absence. The
8 LDs in MANIFEST were already PATCHed in LD-773 with audit notes.

Usage:
    python3 Production/scripts/verify_no_fabrications.py

Exit codes:
    0 — all fabricated artifacts absent (good)
    1 — at least one fabricated artifact present (regression)
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = ROOT.parent

# (kind, target, owning_LD, status)
# kind: "file" — file existence check
# kind: "symbol" — git grep across Production/
MANIFEST = [
    ("file",   "Production/tools/teleport_glass_inserter.py",          "LD-741"),
    ("file",   "Production/scripts/check_storyboard_critical_features.sh", "LD-766"),
    ("file",   "Production/scripts/teleport_glass_kling_test.py",      "LD-737"),
    ("symbol", "guardOrToast",        "LD-739"),
    ("symbol", "guardOrToast",        "LD-740"),  # cascade
    ("symbol", "kim_done",            "LD-746"),
    ("symbol", "KimDone",             "LD-746"),
    ("symbol", "done_toggle",         "LD-746"),
    ("symbol", "SuggestParenthetical", "LD-767"),
]

# NEVER-DELETE files (these MUST exist when their phase has shipped; verifier
# does NOT assert on these — that's not its job). Listed for documentation.
NEVER_DELETE = [
    "Production/lib/state_repo.py",          # Phase 3 (shipped)
    "Production/lib/durable_job_registry.py",  # Phase 5 (pending)
]

# LD-744 IS in MANIFEST as a special case: durable_job_registry.py was
# fabricated in the 2026-05-17 session, but Phase 5 will create the real one.
# We track absence here. Once Phase 5 ships, this entry will be REMOVED from
# MANIFEST (the file legitimately exists; the LD itself was already superseded
# by LD-772 per audit).
_PENDING_PHASE_5 = ("file", "Production/lib/durable_job_registry.py", "LD-744")
# Add only if Phase 5 hasn't run yet; once shipped, remove this guard
if not (ROOT / "lib" / "durable_job_registry.py").exists():
    MANIFEST.insert(1, _PENDING_PHASE_5)


def _file_absent(rel: str) -> tuple[bool, str]:
    p = REPO_ROOT / rel
    if p.exists():
        return False, f"file present ({p.stat().st_size} bytes)"
    return True, "absent"


def _symbol_absent(sym: str) -> tuple[bool, str]:
    try:
        out = subprocess.check_output(
            ["git", "grep", "-l", sym, "Production/"],
            cwd=str(REPO_ROOT),
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except subprocess.CalledProcessError:
        # git grep exits 1 when no matches found — that's what we want
        return True, "no matches"
    if out:
        files = out.splitlines()
        return False, f"hits in {len(files)} file(s): {', '.join(files[:3])}"
    return True, "no matches"


def main() -> int:
    failures: list[dict] = []
    passes: list[dict] = []

    for kind, target, ld in MANIFEST:
        if kind == "file":
            ok, detail = _file_absent(target)
        elif kind == "symbol":
            ok, detail = _symbol_absent(target)
        else:
            print(f"  ? UNKNOWN kind={kind} target={target}", file=sys.stderr)
            continue
        row = {"kind": kind, "target": target, "ld": ld, "detail": detail}
        if ok:
            passes.append(row)
            print(f"  ✓ {ld:8s} {kind:6s} {target:60s} {detail}")
        else:
            failures.append(row)
            print(f"  ✗ {ld:8s} {kind:6s} {target:60s} {detail}", file=sys.stderr)

    print()
    print(f"FABRICATION_GUARD: passed={len(passes)} failed={len(failures)} total={len(MANIFEST)}")
    if failures:
        print(
            "FAIL — fabricated artifact reappeared. Either a session re-created the fake "
            "OR Phase 5 has shipped (in which case durable_job_registry.py should be removed "
            "from MANIFEST). Investigate the failed LD's history.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
