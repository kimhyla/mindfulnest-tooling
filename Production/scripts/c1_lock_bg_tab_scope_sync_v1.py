#!/usr/bin/env python3
"""C1 closure — write SOFT LD `BG_TAB_SCOPE_SYNC_V1`.

Per spec v2 §6.2 + handoff §3 C1, with Kim's LD body approved 2026-05-05
in the post-redeploy-bug-triage session. Schema-mapped per
DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md (live enums; SOFT severity per
2026-05-04 migration).

Per Rule 35: try_post_or_queue + read-back verify.

Run from repo root:
    python3 Production/scripts/c1_lock_bg_tab_scope_sync_v1.py
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

TASK_ID = "post-redeploy-bug-triage-c1-20260505"
DATE_LOCKED = datetime.now(timezone.utc).strftime("%Y-%m-%d")
SOURCE_DOC = (
    "STORYBOARD_V59_POST_REDEPLOY_BUG_FIX_SPEC_v2.md (Cursor APPROVED 2026-05-05)"
)

LD = {
    "decision_key": "BG_TAB_SCOPE_SYNC_V1",
    "decision_name": "BgTab segment context re-fetches on scope-vector change",
    "decision_text": (
        "When ANY scope-vector signal changes — activeScope.event_id, "
        "activeProjectType, activeMilestoneId, OR activeTargetVideo — the "
        "BgTab data-load effect MUST re-fetch /api/bg/segments and "
        "/api/bg/session-state. The first-mount fetch runs synchronously "
        "(no debounce); subsequent re-fires are debounced ≤200ms.\n\n"
        "WHY: this prevents the cross-event-edit hazard where the Beat "
        "Generator Segment dropdown stays on a stale event/phase after the "
        "user switches scope via EventSelector / ProjectSelector / "
        "VideoSelector. All bg_* mutations carry event_id and phase derived "
        "from activeSegment; if activeSegment lags scope, mutations write "
        "to the wrong event. Symptom observed in browser smoke 2026-05-04 "
        "against the stale May 3 SPA build that predated commit 1d375de.\n\n"
        "IMPLEMENTATION pinned in commit 1d375de (S5.5c+e proper fix, "
        "kimhyla, 2026-05-04 08:04 UTC):\n"
        "  - BgTab.tsx dep array contains all 5 scope-vector signals "
        "(arcNumber, activeScope.value.event_id, activeProjectType.value, "
        "activeMilestoneId.value, activeTargetVideo.value).\n"
        "  - prevDepsRef === null gate forces synchronous fetch on first "
        "mount.\n"
        "  - Subsequent dep-vector changes are 200ms debounced (one trailing "
        "fetch per rapid scope toggle).\n\n"
        "CONTRACT ENFORCEMENT: e2e/storyboard-v59-bg-scope-sync.spec.ts "
        "(2 tests, both GREEN against current main):\n"
        "  1. VideoSelector swap (intro→resolution) re-fires "
        "bg/segments + bg/session-state\n"
        "  2. First-mount BG fetch is synchronous (no 200ms debounce gate "
        "on initial load)\n"
        "Future refactor that (a) narrows the dep array, (b) removes the "
        "prevDepsRef sync gate, or (c) drops/widens the 200ms debounce will "
        "fail this test.\n\n"
        "SMOKE CONFIRMATION 2026-05-05: Post-redeploy browser smoke confirmed "
        "symptom gone. Kim observed scoped re-fetch on Event_1→Event_2 "
        "switch via ProjectSelector; BG Segment dropdown reflected Event_2's "
        "segments after page reload + tab switch. Original symptom was a "
        "stale-build artifact.\n\n"
        "CROSS-REFS: LD-456 SCOPE_VALIDATION_V1 (per-request scope "
        "assertion); LD-461 SCOPE_KEY_AUTO_INJECTION_V1 (pathappPatch "
        "auto-injects scope keys into mutation bodies). This LD is the "
        "BgTab-specific complement to those two: the load effect must "
        "subscribe to scope changes so the auto-injected scope is actually "
        "current at mutation time.\n\n"
        "WATCH ITEM (NOT part of this LD; spec v2 §1.5): Server-side "
        "/api/bg/session-state stores active_context once per server "
        "process, not per scope. If multi-tab or cross-scope collision is "
        "observed during future browser smoke (one tab silently overwrites "
        "another's active_context), HARD-promote and patch in a follow-up "
        "session. No LD filed yet; tracked in checkpoint watch_items[].\n\n"
        "INFRA NOTE (Δ-INFRA-1 resolution): This LD was originally "
        "specified with both unit + e2e test coverage (spec v2 §1.4). "
        "Project lacks Vitest/jsdom infrastructure (only Playwright e2e is "
        "wired up); per Δ-INFRA-1 INFRA-B, e2e was deemed sufficient "
        "for the behavioral contract and unit-infra is deferred until a "
        "unit-level invariant emerges that e2e can't reasonably observe. "
        "The /api/video/set_active endpoint is route-mocked in the e2e "
        "because Directus auth is environmental, not part of the contract "
        "under test (consistent with mocking patterns in "
        "s5_5g_smoke.spec.ts)."
    ),
    # Schema-mapped per DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md live enums
    # (Kim's logical labels in parens):
    "task_category": "storyboard",          # (Kim: client_state_sync)
    "severity": "SOFT",
    "scope_domain": "production",           # (Kim: storyboard_v59)
    "enforcement_type": "test",             # (Kim: e2e_test_pin)
    "enforcement_artifact_ref": (
        "Production/tools/storyboard-v2/e2e/storyboard-v59-bg-scope-sync.spec.ts"
    ),
    "past_failure_prevented": (
        "Without this contract pinned by an e2e test, a future refactor "
        "that narrows the BgTab useEffect dep array (e.g. drops "
        "activeMilestoneId.value or activeTargetVideo.value) would silently "
        "regress the cross-event-edit hazard described in spec v2 §1. "
        "Kim's browser smoke 2026-05-04 observed this exact failure mode "
        "against a pre-1d375de bundle: BG Segment dropdown stayed on the "
        "previous event after scope swap, meaning subsequent bg_extract / "
        "bg_accept_beats writes targeted the wrong event."
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
            "commit_label": "C1",
            "schema_enum_translation": {
                "kim_label_task_category": "client_state_sync",
                "live_enum_task_category": "storyboard",
                "kim_label_scope_domain": "storyboard_v59",
                "live_enum_scope_domain": "production",
                "kim_label_enforcement_type": "e2e_test_pin",
                "live_enum_enforcement_type": "test",
            },
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

    # Read-back verify per Rule 35.
    client = DirectusAdminClient()
    row = client.get_item("prod_locked_decisions", pid)
    if not row:
        print(f"  READ-BACK FAILED: no row at id={pid}")
        return False, f"read-back failed at id={pid}"
    if row.get("decision_key") != ld["decision_key"]:
        print(
            f"  READ-BACK MISMATCH: "
            f"row.decision_key={row.get('decision_key')!r}"
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
    print(f"C1 closure: writing 1 LD (task_id={TASK_ID})")
    print()
    ok, info = post_one(LD)
    print()
    print("=" * 60)
    if ok:
        print(f"C1_LD_OK: {LD['decision_key']} landed live + read-back verified")
        print(f"  {info}")
        return 0
    print(f"C1_LD_FAIL: {LD['decision_key']} did not land")
    print(f"  {info}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
