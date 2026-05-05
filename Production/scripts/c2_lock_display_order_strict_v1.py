#!/usr/bin/env python3
"""C2-bundle closure — write HARD LD `DISPLAY_ORDER_STRICT_V1`.

Per spec v2 §6.2 + handoff §3 C2-bundle. The LD pins the
display_order=[] semantics across the renderer (C2a), the server prune
(C2b), and the cleanup script (C2c) — three parts, ONE root cause per
Cursor R7.

Schema-mapped per DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md live enums
(severity HARD/SOFT post 2026-05-04 migration).

Per Rule 35: try_post_or_queue + read-back verify.

Run from repo root:
    python3 Production/scripts/c2_lock_display_order_strict_v1.py
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

TASK_ID = "post-redeploy-bug-triage-c2-bundle-20260505"
DATE_LOCKED = datetime.now(timezone.utc).strftime("%Y-%m-%d")
SOURCE_DOC = (
    "STORYBOARD_V59_POST_REDEPLOY_BUG_FIX_SPEC_v2.md (Cursor APPROVED 2026-05-05)"
)

LD = {
    "decision_key": "DISPLAY_ORDER_STRICT_V1",
    "decision_name": (
        "Empty display_order means render zero beats; legacy fallthrough "
        "only on absent or non-list display_order"
    ),
    "decision_text": (
        "When `videos.<role>.display_order` is a present LIST, both the "
        "client renderer (StoryboardTab.beatList) and the server prune "
        "(StateManager.mutate_video_state) MUST honor it strictly:\n"
        "  - List with content → render exactly those beat_ids, in order\n"
        "  - Empty list `[]`     → render ZERO beats; drop any orphans "
        "from beats{}\n\n"
        "Only when display_order is genuinely missing — undefined, OR a "
        "non-list legacy value (e.g. integer partition-ordering from "
        "pre-v3 fixtures like display_order=1) — does the renderer fall "
        "through to the legacy Object.entries(beats) sorted-by-beat_id "
        "path. The server prune SKIPS in those legacy cases (preserves "
        "all beats).\n\n"
        "WHY: prevents the orphan-beat surfacing failure that produced "
        "Bug B (Event_2/intro/beats had `beat_04` 'MindfulNest...' even "
        "with `display_order=[]`; pre-fix StoryboardTab fell through to "
        "Object.entries and rendered the orphan). Same root cause "
        "produces orphan accumulation in storage if the server doesn't "
        "prune on mutation. The cleanup script handles the bulk pass for "
        "already-existing orphans.\n\n"
        "IMPLEMENTATION (3 parts, all in one commit per Cursor R7):\n"
        "  C2a — StoryboardTab.tsx beatList: `Array.isArray(partition.display_order)` "
        "gate. Defensive form of spec v2 §2.3 Part 1's `!== undefined` check; "
        "correctly handles non-list legacy display_order=integer.\n"
        "  C2b — production_server.py StateManager.mutate_video_state: post-mutator "
        "prune step. When display_order is a list, drop any beats[bid] "
        "whose bid isn't in it. Atomic via existing mutate_state channel "
        "(LD-519 mutation channel invariant respected).\n"
        "  C2c — Production/scripts/clean_orphan_beats_v3.py: bulk pass over "
        "Production/Event_*/production_state.json AND Production/Milestones/*/state.json "
        "(per spec §2.3 Part 3 + Kim 2026-05-05 amendment A — Milestones "
        "walk is no-op while tree empty). Three safety guards: (1) "
        "pre-image backup at <state_dir>/.backups/state/preimage_<UTC>_clean_orphan_beats.json, "
        "(2) scoped mode required for first --apply, (3) "
        "prod_activity_log row per scope with full removed_beat_payload "
        "for forensic recovery.\n\n"
        "CONTRACT ENFORCEMENT (3 test files, all GREEN against current main):\n"
        "  - e2e: Production/tools/storyboard-v2/e2e/storyboard-v59-display-order-empty.spec.ts "
        "(4 tests — list/empty/undefined cases + DS-7 retroactive Event_2 shape)\n"
        "  - pytest: Production/tools/tests/test_production_state_mutate_video_state.py "
        "(5 tests — prune drops orphans; empty list drops all; legacy-skip "
        "for undefined; legacy-skip for non-list integer; idempotent on "
        "consistent partitions)\n"
        "  - pytest: Production/tools/tests/test_clean_orphan_beats_v3.py "
        "(5 tests — dry-run, --apply --event golden with backup + activity "
        "log assertions, --all rejection without scoped marker, two "
        "legacy-skip cases)\n\n"
        "ANY future refactor that:\n"
        "  - Replaces the Array.isArray gate with a less-strict check "
        "(e.g. truthy `if (partition.display_order)`)\n"
        "  - Removes the post-mutator prune in mutate_video_state\n"
        "  - Drops the cleanup script's safety guards (backup, scoped "
        "mode, activity log)\n"
        "...will fail at least one of the contract tests above.\n\n"
        "POST-COMMIT OPERATIONAL: Kim 2026-05-05 authorized running "
        "`python3 Production/scripts/clean_orphan_beats_v3.py --apply "
        "--event 2` to evict the live orphan beat_04 from Dropbox tree's "
        "Event_2/intro. Pre-image backup + prod_activity_log row "
        "preserve forensic record per Cursor R3."
    ),
    "task_category": "storyboard",
    "severity": "HARD",
    "scope_domain": "production",
    "enforcement_type": "test",
    "enforcement_artifact_ref": (
        "Production/tools/storyboard-v2/e2e/storyboard-v59-display-order-empty.spec.ts; "
        "Production/tools/tests/test_production_state_mutate_video_state.py; "
        "Production/tools/tests/test_clean_orphan_beats_v3.py"
    ),
    "past_failure_prevented": (
        "Pre-fix StoryboardTab.beatList read `partition.display_order ?? []` "
        "then `if (order.length > 0)`. When display_order was `[]` the "
        "code fell through to Object.entries(beats) and rendered every "
        "beat key in beats{}. Two semantically distinct cases — 'no "
        "display_order field' (legacy) and 'explicitly empty display_order' "
        "(modern post-prune) — collapsed together. Live Event_2 carried "
        "an unauthored beat_04 'MindfulNest...' with display_order=[]; "
        "pre-fix UI rendered it as a real authored beat, breaking the "
        "what-you-see-is-what-you-authored expectation. Server-side, "
        "mutate_video_state never pruned beats{} on display_order changes, "
        "so orphans accumulated indefinitely."
    ),
}


def post_one(ld: dict) -> tuple[bool, str]:
    payload = {
        "decision_key": ld["decision_key"],
        "decision_name": ld["decision_name"],
        "decision_text": ld["decision_text"],
        "source_document": SOURCE_DOC,
        "task_category": ld["task_category"],
        "severity": ld["severity"],
        "scope_domain": ld["scope_domain"],
        "enforcement_type": ld["enforcement_type"],
        "enforcement_artifact_ref": ld["enforcement_artifact_ref"],
        "past_failure_prevented": ld["past_failure_prevented"],
        "status": "active",
        "is_current": True,
        "supersedable": True,
        "schema_version": 2,
        "date_locked": DATE_LOCKED,
        "notes": json.dumps({
            "task_id": TASK_ID,
            "session": "post-redeploy-bug-triage",
            "session_date": DATE_LOCKED,
            "commit_label": "C2-bundle",
            "parts": ["C2a renderer", "C2b server prune", "C2c cleanup script"],
        }),
    }

    print(f"=== POST prod_locked_decisions key={ld['decision_key']} ===")
    result = try_post_or_queue("prod_locked_decisions", payload)

    if result.get("queued"):
        print(f"  QUEUED OFFLINE -> {result.get('path')}")
        return False, f"queued: {result.get('error', '')[:150]}"

    if result.get("silent_write_failure"):
        item_id = result.get("item_id")
        mismatches = result.get("mismatches", [])
        all_missing = all(
            m.get("kind") == "missing-from-schema" for m in mismatches
        )
        if item_id and all_missing:
            print(f"  silent_write_failure (false positive — schema-missing "
                  f"fields): id={item_id}")
            return True, f"id={item_id} (schema-missing fields ignored)"
        print(f"  SILENT WRITE FAILURE -> mismatches={mismatches}")
        return False, f"silent_write_failure: {mismatches}"

    pid = result.get("id")
    if not pid:
        print(f"  UNEXPECTED -> {result}")
        return False, f"no id: {result}"

    # Read-back verify per Rule 35.
    client = DirectusAdminClient()
    row = client.get_item("prod_locked_decisions", pid)
    if not row:
        print(f"  READ-BACK FAILED: no row at id={pid}")
        return False, f"read-back failed at id={pid}"
    if row.get("decision_key") != ld["decision_key"]:
        print(f"  READ-BACK MISMATCH: row.decision_key="
              f"{row.get('decision_key')!r}")
        return False, "decision_key mismatch"
    if row.get("severity") != ld["severity"]:
        print(f"  READ-BACK MISMATCH: row.severity={row.get('severity')!r} "
              f"expected {ld['severity']!r}")
        return False, "severity mismatch"

    print(f"  WROTE LIVE -> id={pid} severity={row.get('severity')} "
          f"status={row.get('status')}")
    return True, f"id={pid}"


def main() -> int:
    print(f"C2-bundle closure: writing 1 LD (task_id={TASK_ID})")
    print()
    ok, info = post_one(LD)
    print()
    print("=" * 60)
    if ok:
        print(f"C2_LD_OK: {LD['decision_key']} landed live + read-back verified")
        print(f"  {info}")
        return 0
    print(f"C2_LD_FAIL: {LD['decision_key']} did not land")
    print(f"  {info}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
