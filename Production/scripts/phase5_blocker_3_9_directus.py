#!/usr/bin/env python3
"""
Phase 5 Directus writes for Blocker #3 + #9 bundle.

Writes:
1. app_activity_log entry documenting workflow creation + Phase 5 test results.
2. PATCH prod_preflight_reviews id=13 with related_activity_log_id.
3. PATCH prod_locked_decisions LD-113 notes with workflow path + empirical finding.
4. POST new app_blockers rows for follow-up gaps surfaced during Phase 5:
   - Branch protection with required status check
   - iOS/Android bundle scan (post-EAS)
   - DevTelemetry.ts architectural fix (empty-stub export leak)
   - Workflow-file CODEOWNERS protection

Does NOT resolve app_blockers #3 or #9 — those remain open pending Kim's
decision on how to close the upstream DevTelemetry.ts leak surfaced by
Phase 5 positive-case test.

All entries embed task_id blocker-3-9-ci-telemetry-scan-20260417 per
Phase 0 Step 8 requirement.
"""

import json
import os
import sys
from datetime import datetime, timezone

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
TOOLS_DIR = os.path.normpath(os.path.join(THIS_DIR, "..", "tools"))
sys.path.insert(0, TOOLS_DIR)

from lib.credentials import load_credentials  # noqa: E402
from lib.directus import DirectusClient  # noqa: E402


TASK_ID = "blocker-3-9-ci-telemetry-scan-20260417"
PREFLIGHT_ROW_ID = 13


def main():
    creds = load_credentials()
    client = DirectusClient(creds["directus_url"], creds["directus_email"], creds["directus_password"])
    client.authenticate()
    print(f"[phase5] Authenticated: {creds['directus_url']}")

    # ------------------------------------------------------------------
    # 1. app_activity_log entry
    # ------------------------------------------------------------------
    activity_payload = {
        "feature_id": "stage2_ci_telemetry_scan",
        "action": (
            "Created .github/workflows/telemetry-scan.yml (Blocker #3 + #9 bundle). "
            "PR-gated on main, job-level NODE_ENV=production, Expo web export, "
            "strict grep -RFI for 4 markers, fails with clear message. "
            "Phase 5 local validation caught a REAL upstream leak: initDevTelemetry "
            "survives production bundle as empty-stub export due to unconditional "
            "ES module import in app/_layout.tsx. Blocker #3 + #9 NOT resolved "
            "pending Kim decision on closure path."
        ),
        "performed_by": "claude-opus-4-7-terminal",
        "details": {
            "task_id": TASK_ID,
            "preflight_row_id": PREFLIGHT_ROW_ID,
            "blockers_addressed": [3, 9],
            "blockers_resolved": [],
            "new_blockers_created": ["branch_protection_required", "ios_android_bundle_scan",
                                     "devtelemetry_export_leak", "workflow_codeowners"],
            "files_created": [
                "~/Projects/MindfulNest/.github/workflows/telemetry-scan.yml",
            ],
            "git_branch": "stage2/blocker-3-9-ci-telemetry-scan",
            "phase5_test_positive": {
                "result": "FAIL — initDevTelemetry caught in clean bundle",
                "evidence": "dist/_expo/static/js/web/entry-*.js:771  e.initDevTelemetry=function(){return}",
                "interpretation": "Metro strips function body (correct) but ES module export name survives (structural limitation).",
                "data_leak_markers_stripped_correctly": [
                    "__MINDFULNEST_DEV__", "window.__MINDFULNEST_DEV__", "[DevTelemetry]"
                ],
                "remaining_marker": "initDevTelemetry (empty no-op, function body stripped)",
            },
            "phase5_test_negative": {
                "result": "PASS — injected window.__MINDFULNEST_DEV__ into dist/index.html, grep exited with match",
                "evidence": "dist/index.html:38  <script>window.__MINDFULNEST_DEV__ = ...",
                "interpretation": "Grep flag set correct. Workflow would exit 1 in CI against real leaks.",
            },
            "locked_decisions_referenced": ["LD-113 STAGE2_GATE_CI_SAFETY_SCAN"],
            "handoff_deviations": [
                "Trigger: pull_request only (handoff said 'pull_request, push to main'); "
                "STOP-trigger #3 overrode handoff — Kim's PR-gated-only policy."
            ],
        },
    }
    res = client._request("POST", "/items/app_activity_log", data=activity_payload)
    activity_id = res["data"]["id"]
    print(f"[phase5] app_activity_log created: id={activity_id}")

    # ------------------------------------------------------------------
    # 2. PATCH prod_preflight_reviews id=13 with related_activity_log_id
    # ------------------------------------------------------------------
    client._request(
        "PATCH",
        f"/items/prod_preflight_reviews/{PREFLIGHT_ROW_ID}",
        data={"related_activity_log_id": activity_id},
    )
    print(f"[phase5] prod_preflight_reviews id={PREFLIGHT_ROW_ID} PATCHed with related_activity_log_id={activity_id}")

    # ------------------------------------------------------------------
    # 3. PATCH prod_locked_decisions LD-113 notes
    # ------------------------------------------------------------------
    ld113 = client._request(
        "GET",
        "/items/prod_locked_decisions",
        params={"filter[decision_key][_eq]": "STAGE2_GATE_CI_SAFETY_SCAN", "fields": "id,notes"},
    )
    ld113_rows = ld113.get("data", [])
    if ld113_rows:
        ld113_id = ld113_rows[0]["id"]
        existing_notes = ld113_rows[0].get("notes") or ""
        new_note = (
            f"\n\n--- Phase 5 update (task_id={TASK_ID}, activity_log={activity_id}) ---\n"
            f"Workflow created at ~/Projects/MindfulNest/.github/workflows/telemetry-scan.yml (feature branch "
            f"stage2/blocker-3-9-ci-telemetry-scan). PR-gated only. Bundles Blocker #9 (NODE_ENV verify).\n"
            f"Phase 5 positive-case local test FOUND a leak: initDevTelemetry survives in dist/ as empty-stub "
            f"export (Metro strips function body via __DEV__ guard but ES module export name persists "
            f"because app/_layout.tsx imports unconditionally at module top). The 3 data-leak markers "
            f"(__MINDFULNEST_DEV__, window.__MINDFULNEST_DEV__, [DevTelemetry]) correctly absent. "
            f"Negative-case test confirmed grep catches injected marker.\n"
            f"Blocker #3 + #9 remain OPEN pending Kim's closure decision (3 options: fix DevTelemetry.ts "
            f"architectural import pattern; refine marker list to exclude function names; accept empty stub)."
        )
        updated_notes = existing_notes + new_note
        client._request(
            "PATCH",
            f"/items/prod_locked_decisions/{ld113_id}",
            data={"notes": updated_notes},
        )
        print(f"[phase5] LD-113 (id={ld113_id}) notes PATCHed")
    else:
        print("[phase5] WARNING — LD-113 STAGE2_GATE_CI_SAFETY_SCAN not found")

    # ------------------------------------------------------------------
    # 4. New follow-up blockers (registered per Rule 19 escape-hatch discipline)
    # ------------------------------------------------------------------
    new_blockers = [
        {
            "feature_id": "stage2_ci_telemetry_scan",
            "title": "Branch protection required-status-check for telemetry-scan.yml",
            "description": (
                "Telemetry-scan.yml is PR-gated only. Kim must configure GitHub branch protection on `main` "
                "to require the 'Telemetry Leak Scan / Scan production web bundle for dev-telemetry markers' "
                "status check before merge. Without this, a direct push to main or an admin merge can bypass "
                "the gate entirely. Surfaced by Phase 0 architectural advocate + counter-safety C3. "
                f"Related task_id: {TASK_ID}."
            ),
            "severity": "high",
            "is_resolved": False,
        },
        {
            "feature_id": "stage2_ci_telemetry_scan",
            "title": "Extend telemetry scan to iOS + Android EAS bundles",
            "description": (
                "telemetry-scan.yml currently scans web bundle only via `expo export -p web`. "
                "Native iOS/Android bundles produced by EAS (eas.json 'production' profile sets "
                "NODE_ENV=production) are not scanned. When EAS build integration lands (post-Stage 2), "
                "add a second workflow or extend this one to download an EAS preview/production build "
                "artifact and grep for the same markers. "
                f"Related task_id: {TASK_ID}."
            ),
            "severity": "medium",
            "is_resolved": False,
        },
        {
            "feature_id": "dev_telemetry",
            "title": "DevTelemetry.ts leaks empty-stub exports to production bundle",
            "description": (
                "Phase 5 local test of telemetry-scan.yml against current main: "
                "dist/_expo/static/js/web/entry-*.js contains `e.initDevTelemetry=function(){return}`, "
                "`e.updateDevTelemetry=function(t){return}`, and `e.getDevTelemetry=u`. Metro correctly "
                "strips function bodies via __DEV__ guards (all reduce to `return`), but ES module "
                "exports survive because app/_layout.tsx:3 and app/index.tsx:4 import these at module top "
                "unconditionally. "
                "The actual data leak surfaces (window.__MINDFULNEST_DEV__ assignment, [DevTelemetry] "
                "console.log) ARE correctly stripped. "
                "Closure options: (a) refactor DevTelemetry.ts imports to CommonJS `require()` gated "
                "by `if (__DEV__)` at call sites so whole module is tree-shaken, or (b) split into "
                ".dev.ts / .prod.ts via Metro platform extensions. "
                "Blocker #3 + #9 cannot resolve green until this is fixed (option a/b) OR marker list "
                "is narrowed to data-leak strings only (drops function names). "
                f"Related task_id: {TASK_ID}."
            ),
            "severity": "high",
            "is_resolved": False,
        },
        {
            "feature_id": "stage2_ci_telemetry_scan",
            "title": "CODEOWNERS for .github/workflows/ + signed-commit policy",
            "description": (
                "Phase 0 safety-advocate: the scanner is worthless if an attacker or careless contributor "
                "can weaken it in the same PR. Add `.github/CODEOWNERS` requiring owner review on any "
                "`.github/workflows/*.yml` edit. Signed-commit policy deferred per Phase 0 counter-H5 "
                "(scope creep for this blocker) but tracked here. "
                f"Related task_id: {TASK_ID}."
            ),
            "severity": "medium",
            "is_resolved": False,
        },
    ]

    created_ids = []
    for b in new_blockers:
        res = client._request("POST", "/items/app_blockers", data=b)
        bid = res["data"]["id"]
        created_ids.append(bid)
        print(f"[phase5] app_blockers created: id={bid}  {b['title'][:80]}")

    print()
    print(f"[phase5] DONE.")
    print(f"[phase5]   activity_log id={activity_id}")
    print(f"[phase5]   preflight_row={PREFLIGHT_ROW_ID}  related_activity_log_id={activity_id}")
    print(f"[phase5]   new_blockers={created_ids}")
    print(f"[phase5]   Blocker #3 + #9 NOT resolved — pending Kim decision")


if __name__ == "__main__":
    main()
