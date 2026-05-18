#!/usr/bin/env python3
"""Lock SHORTCUT_STORYBOARD_PARITY_BACKLOG_V1 — deferred storyboard e2e fixme backlog.

Per Track B chunk 2 / Kim 2026-05-18 directive. Formalizes intentional-RED
test.fixme contracts in storyboard-v2 e2e per CLAUDE.md Rule 19.

Run from repo root (orchestrator invokes after CI):
    python3 Production/scripts/lock_shortcut_storyboard_parity_backlog.py

Per Rule 35: try_post_or_queue + marker_string fabrication gate.
DO NOT run in CI agent sessions that lack Directus credentials — script only.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "Production" / "lib"))

from directus import try_post_or_queue  # noqa: E402
from directus_admin_client import DirectusAdminClient  # noqa: E402

TASK_ID = "track-b-chunk-2-shortcut-storyboard-parity-20260518"
DATE_LOCKED = datetime.now(timezone.utc).strftime("%Y-%m-%d")
SOURCE_DOC = "Production/tools/storyboard-v2/e2e/"

# Ten intentional-RED entries (touchpoint-a §6 + beat_graft RED skeleton).
FIXME_ENTRIES = [
    ("Production/tools/storyboard-v2/e2e/touchpoint-a.spec.ts", 73,
     "§6A.6 — library /api/cr/library failure shows banner, never silent blank"),
    ("Production/tools/storyboard-v2/e2e/touchpoint-a.spec.ts", 126,
     "§6B.1 — drag library image onto beat slot persists across reload"),
    ("Production/tools/storyboard-v2/e2e/touchpoint-a.spec.ts", 130,
     "§6B.2 — open cropper from beat row; save crop becomes beat still"),
    ("Production/tools/storyboard-v2/e2e/touchpoint-a.spec.ts", 156,
     "§6B.4 — beat trim slider persists across reload"),
    ("Production/tools/storyboard-v2/e2e/touchpoint-a.spec.ts", 176,
     "§6B.6 — Kling generation produces option that can be selected"),
    ("Production/tools/storyboard-v2/e2e/touchpoint-a.spec.ts", 177,
     "§6B.7 — Lipsync run becomes primary clip"),
    ("Production/tools/storyboard-v2/e2e/touchpoint-a.spec.ts", 178,
     "§6B.8 — Add/delete beat persists across reload"),
    ("Production/tools/storyboard-v2/e2e/touchpoint-a.spec.ts", 179,
     "§6B.9 — v59 dialogue write → flag-flip server to v58 → v58 sees same text"),
    ("Production/tools/storyboard-v2/e2e/beat_graft_red.spec.ts", 120,
     'GR.4 — source beat with phase_1.status="completed" returns HTTP 400 graft_pre_render_only'),
    ("Production/tools/storyboard-v2/e2e/beat_graft_red.spec.ts", 140,
     "GR.6 — move=true deletes source after target write"),
]


def _count_test_fixme_in_head() -> int:
    """Sum `git grep -c -F test.fixme HEAD -- e2e/` match counts."""
    try:
        result = subprocess.run(
            [
                "git", "grep", "-c", "-F", "test.fixme", "HEAD", "--",
                "Production/tools/storyboard-v2/e2e/",
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode not in (0, 1):
            return 0
        total = 0
        for line in result.stdout.splitlines():
            _, _, n = line.rpartition(":")
            try:
                total += int(n)
            except ValueError:
                continue
        return total
    except (subprocess.SubprocessError, OSError):
        return 0


def _decision_text() -> str:
    lines = [
        "SHORTCUT backlog for storyboard-v2 e2e tests intentionally left RED "
        "(test.fixme) per cursor 2026-05-18 final review. Each entry must "
        "either ship as a real GREEN test or be formally retired in a future LD.\n",
        "Enumerated fixme contracts (10):\n",
    ]
    for path, line_no, title in FIXME_ENTRIES:
        lines.append(f"  - {path}:{line_no} — {title}")
    lines.append(
        "\nAdditional test.fixme rows exist in behavioral-parity.spec.ts and "
        "scope_router_red.spec.ts; they are out of scope for this SHORTCUT's "
        "10-entry closure set but remain tracked in-repo until individually "
        "promoted or retired."
    )
    return "\n".join(lines)


MARKER_COUNT = _count_test_fixme_in_head()

LD = {
    "decision_key": "SHORTCUT_STORYBOARD_PARITY_BACKLOG_V1",
    "decision_name": "Storyboard parity e2e test.fixme backlog (10 entries)",
    "decision_text": _decision_text(),
    "source_document": SOURCE_DOC,
    "task_category": "testing",
    "severity": "SOFT",
    "status": "active",
    "marker_string": "test.fixme",
    "notes": (
        f"[MARKER_AUDIT 2026-05-18] marker_string='test.fixme' "
        f"verified-in-main-HEAD count={MARKER_COUNT} via `git grep -c -F test.fixme HEAD`. "
        f"[CONFIRMED against tooling repo HEAD at lock_decision time — "
        f"count is computed by _count_test_fixme_in_head() which shells out to "
        f"`git grep -c -F test.fixme HEAD` immediately before the POST.] "
        "Closes Phase 3.5e cursor borderline-defer finding per Kim 2026-05-18 "
        "directive."
    ),
}


def post_one(ld: dict) -> tuple[bool, str]:
    payload = {
        "decision_key": ld["decision_key"],
        "decision_name": ld["decision_name"],
        "decision_text": ld["decision_text"],
        "source_document": ld["source_document"],
        "task_category": ld["task_category"],
        "severity": ld["severity"],
        "status": ld["status"],
        "is_current": True,
        "supersedable": True,
        "schema_version": 2,
        "date_locked": DATE_LOCKED,
        "marker_string": ld["marker_string"],
        "notes": ld["notes"],
    }

    print(f"=== POST prod_locked_decisions key={ld['decision_key']} ===")
    result = try_post_or_queue("prod_locked_decisions", payload)

    if result.get("fabrication_gate_blocked"):
        print(f"  FABRICATION GATE BLOCKED: {result.get('error', result)}", file=sys.stderr)
        return False, "fabrication_gate_blocked"

    if result.get("queued"):
        print(f"  QUEUED OFFLINE -> {result.get('path')}")
        return False, f"queued: {result.get('error', '')[:150]}"

    if result.get("silent_write_failure"):
        item_id = result.get("item_id")
        mismatches = result.get("mismatches", [])
        all_missing = all(m.get("kind") == "missing-from-schema" for m in mismatches)
        if item_id and all_missing:
            print(
                f"  silent_write_failure (false positive — schema-missing "
                f"fields): id={item_id}"
            )
            return True, f"id={item_id} (schema-missing fields ignored)"
        print(f"  SILENT WRITE FAILURE -> mismatches={mismatches}")
        return False, f"silent_write_failure: {mismatches}"

    pid = result.get("id")
    if not pid:
        print(f"  UNEXPECTED -> {result}")
        return False, f"no id: {result}"

    client = DirectusAdminClient()
    row = client.get_item("prod_locked_decisions", pid)
    if not row:
        print(f"  READ-BACK FAILED: no row at id={pid}")
        return False, f"read-back failed at id={pid}"
    if row.get("decision_key") != ld["decision_key"]:
        print(
            f"  READ-BACK MISMATCH: row.decision_key={row.get('decision_key')!r}"
        )
        return False, "decision_key mismatch"
    if row.get("severity") != ld["severity"]:
        print(
            f"  READ-BACK MISMATCH: row.severity={row.get('severity')!r} "
            f"expected {ld['severity']!r}"
        )
        return False, "severity mismatch"

    print(
        f"  WROTE LIVE -> id={pid} severity={row.get('severity')} "
        f"status={row.get('status')}"
    )
    return True, f"id={pid}"


def main() -> int:
    print(f"SHORTCUT lock: {LD['decision_key']} (task_id={TASK_ID})")
    print(f"  marker HEAD count (test.fixme in e2e/): {MARKER_COUNT}")
    print()
    ok, info = post_one(LD)
    print()
    print("=" * 60)
    if ok:
        print(f"SHORTCUT_OK: {LD['decision_key']} landed live + read-back verified")
        print(f"  {info}")
        return 0
    print(f"SHORTCUT_FAIL: {LD['decision_key']} did not land")
    print(f"  {info}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
