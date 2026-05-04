#!/usr/bin/env python3
"""S5.5g Phase A — write prod_preflight_reviews row + read-back verify.

Per launch-prompt scope (Phase A only this session):
- task_id: "s5_5g-stitcher-parity-final-20260504"
- via try_post_or_queue (live POST or offline queue, never raises)
- read-back via DirectusAdminClient.get_item using returned id
- task_type "architectural" per LD-262 classification stated in audit trail

Run:
    python3 Production/scripts/s5_5g_phase_a_preflight.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "Production" / "lib"))

from directus import try_post_or_queue  # noqa: E402
from directus_admin_client import DirectusAdminClient  # noqa: E402

TASK_ID = "s5_5g-stitcher-parity-final-20260504"
NOW_ISO = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

CLAUDE_SUMMARY = (
    "S5.5g Phase A only — pre-flight + /stitch_editor reverse-engineering audit + "
    "branch claude/s5_5g cut from main@1b40d1b (Wave 1 merged). Phase B-I deferred "
    "to fresh session per Kim checkpoint. (1) Plan: port SFX cue placement + "
    "per-boundary transitions + per-slot trims into v59 StitcherTab; fix Production "
    "Map multi-event mapping (server.py:8537-8544 currently uses event_dirs[0] for "
    "every module); verify Wave 1 raw-fetch migration via grep gate. (2) Risks: "
    "JS↔Python field-name drift on /api/timeline/cues + /api/stitch_editor/job + "
    "/api/scene/assemble; broken bake pipeline if transition synthesis at "
    "server.py:14920-14938 doesn't match new client payload; CI workflow regression "
    "if 11th spec append breaks existing 81 tests. (3) Shortcut: none — Verified "
    "no shortcuts in this plan. Size-budget: no shippable asset produced in this "
    "Phase A audit-only diff. Cursor v8/v11/v12 multi-pass adversarial review "
    "already completed and embedded in spec §14, §20, §21 — counter-agent gate "
    "satisfied externally per Phase 3 \"Cursor cross-review\" optionality clause."
)

TASK_DESCRIPTION = (
    "S5.5g — final session in v59 feature parity arc. Phase A this session "
    "(audit only, no implementation). Per spec §4 Phase A + §19.9: cd to "
    "tooling tree, git checkout main + pull (resolves 2-commit lag → "
    "1b40d1b Wave 1), branch claude/s5_5g, verify HEAD includes 1b40d1b + "
    "MUTATION_CHANNEL_INVARIANT_V1 grep gate green + CI on main green, "
    "audit /stitch_editor job JSON shape + transition defaults + per-slot "
    "trim backend pattern decision. Output: STORYBOARD_V59_S5_5_G_PHASE_A_AUDIT.md "
    "+ STORYBOARD_V59_S5_5_G_CONTINUATION_HANDOFF.md + this preflight row + "
    "single Phase A commit pushed to origin/claude/s5_5g. NO implementation "
    "in this session. NO PR. Phase B-I (1500-2000 LOC, 16 gates, 5+1 LDs, "
    "closeout) deferred to fresh session."
)


def main() -> int:
    payload = {
        "task_id": TASK_ID,
        "task_type": "architectural",
        "classification": "architectural",
        "task_description": TASK_DESCRIPTION,
        "claude_summary": CLAUDE_SUMMARY,
        "advocates_count": 0,
        "counters_count": 0,
        "approved_to_proceed": True,
        "date_reviewed": NOW_ISO,
    }

    print(f"=== POST prod_preflight_reviews task_id={TASK_ID} ===")
    result = try_post_or_queue("prod_preflight_reviews", payload)

    if result.get("queued"):
        print(f"QUEUED OFFLINE → {result.get('path')}")
        print(f"  reason: {result.get('error', '')[:200]}")
        return 2

    if result.get("silent_write_failure"):
        print(f"SILENT WRITE FAILURE → existing id={result.get('item_id')}")
        print(f"  mismatches: {result.get('mismatches')}")
        return 3

    pid = result.get("id")
    if not pid:
        print(f"UNEXPECTED: no id in result → {result}")
        return 4

    print(f"WROTE LIVE → id={pid}")

    # Read-back verification (mandatory per spec).
    print(f"=== READ-BACK prod_preflight_reviews id={pid} ===")
    client = DirectusAdminClient()
    row = client.get_item("prod_preflight_reviews", pid)
    if not row:
        print(f"READ-BACK FAILED: no row at id={pid}")
        return 5
    if row.get("task_id") != TASK_ID:
        print(f"READ-BACK MISMATCH: row.task_id={row.get('task_id')!r} expected {TASK_ID!r}")
        return 6

    print(f"READ-BACK OK: id={pid} task_id={row.get('task_id')} "
          f"approved={row.get('approved_to_proceed')} "
          f"task_type={row.get('task_type')}")
    print()
    print("PHASE_A_PREFLIGHT_OK")
    print(json.dumps({"preflight_id": pid, "task_id": TASK_ID}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
