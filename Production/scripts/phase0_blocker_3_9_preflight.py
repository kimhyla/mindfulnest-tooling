#!/usr/bin/env python3
"""
Phase 0 Pre-Flight row for Blocker #3 + #9 bundle
(CI telemetry leak scan + NODE_ENV=production verify).

Writes one row to prod_preflight_reviews with task_id
blocker-3-9-ci-telemetry-scan-20260417, then reads it
back to confirm the write (Phase 0 Step 6).

Idempotent: if a row with this task_id already exists,
reports and exits cleanly.
"""

import json
import os
import sys
from datetime import datetime, timezone

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
TOOLS_DIR = os.path.normpath(os.path.join(THIS_DIR, "..", "tools"))
sys.path.insert(0, TOOLS_DIR)

from credentials_lib.credentials import load_credentials  # noqa: E402
from credentials_lib.directus import DirectusClient, DirectusError  # noqa: E402


TASK_ID = "blocker-3-9-ci-telemetry-scan-20260417"

TASK_DESCRIPTION = (
    "Create ~/Projects/MindfulNest/.github/workflows/telemetry-scan.yml "
    "(bundle of Blocker #3 CI telemetry leak scan + Blocker #9 NODE_ENV=production verify). "
    "PR-gated only (STOP-trigger #3 overrides handoff push-to-main spec). "
    "Sets NODE_ENV=production at job level with verify step, runs npx expo export -p web, "
    "then grep -RF -I over dist/ (restricted to *.js/*.html/*.map) for four forbidden markers: "
    "__MINDFULNEST_DEV__, window.__MINDFULNEST_DEV__, [DevTelemetry], initDevTelemetry. "
    "Fails with exit 1 on any match."
)

CLAUDE_SUMMARY = (
    "1) WHAT: Create .github/workflows/telemetry-scan.yml as the repo's first GitHub Actions workflow "
    "(PR-gated, pull_request event only). Workflow sets NODE_ENV=production at job level, runs a pre-build verify step, "
    "runs `npx expo export -p web` to produce dist/, then strict `grep -RF -I` for four dev-telemetry markers "
    "(__MINDFULNEST_DEV__, window.__MINDFULNEST_DEV__, [DevTelemetry], initDevTelemetry) restricted to text file globs; "
    "fails job with exit 1 + neutral top-level message on any match. Bundles Blocker #3 (scan) + #9 (NODE_ENV verify) per handoff. "
    "2) OPEN ERROR PATHS: (a) marker false-negative if minifier mangles names (Metro typically preserves global property strings but not guaranteed); "
    "(b) web-only scope — iOS/Android EAS bundles bypass this workflow; (c) PR-gated non-binding until branch protection with required status check is configured (not in scope); "
    "(d) workflow file itself unprotected until CODEOWNERS added (follow-up); (e) sourcemaps .map included in scan, but if export emits compressed .map.gz that is not covered. "
    "3) SHORTCUTS: Verified: no shortcuts in this plan. PR-only trigger is narrowing per Kim's STOP-trigger, not weakening. Full 4-marker spec implementation. "
    "Remaining error paths (a-e) documented in Phase 6 blind-spot report with follow-up blockers registered in Directus."
)

ADVOCATES = [
    {
        "angle": "speed_efficiency",
        "summary": (
            "Lean by construction: ubuntu-latest + setup-node@v4 + npm ci + expo export -p web + grep -RF = ~3 min. "
            "Zero bespoke code, grep -RF is GNU coreutils primitive, adding markers is one-line edit. "
            "Wins vs alternatives: custom scanner (+200 LOC), ESLint rule (wrong layer - source not bundle), "
            "TS transform (slow/brittle), pre-commit (bypassable). "
            "Suggested improvement: cache Expo/Metro transform cache via actions/cache@v4 for ~60s savings. "
            "[REJECTED by synthesis — see counter C1]"
        ),
    },
    {
        "angle": "safety_security",
        "summary": (
            "Three-layer defense in depth: Layer 1 __DEV__ guard (human error), Layer 2 NODE_ENV=production (infra error), "
            "Layer 3 CI grep on dist (ground truth). Strict grep -RF correct choice — [DevTelemetry] under -E would be regex "
            "character class -> silent false negative. Case sensitivity avoids false-positive fatigue. "
            "PR-gated catches leaks BEFORE merge (COPPA-compliant posture). NODE_ENV pre-check ensures grep's negative result is meaningful. "
            "Suggested addition: signed commits + CODEOWNERS on workflow file itself. [DEFERRED — scope creep per counter H5]"
        ),
    },
    {
        "angle": "maintainability_clarity",
        "summary": (
            "Optimize for Kim re-reading in 6 months. Explicit plain-English step names, comment blocks per phase. "
            "Keep 4 markers inline — externalization adds indirection for N=1 workflow. "
            "Suggested investments: .github/workflows/README.md [REJECTED as scope creep, counter M2], "
            "plain-English error messages [PARTIAL — neutral top summary + specifics in job logs per counter H5], "
            "top-of-file comment block with purpose/trigger/failure/blocker (6 lines). "
            "Primary win: the top-of-file comment block."
        ),
    },
    {
        "angle": "architectural_integrity",
        "summary": (
            "Plan honors 3-layer architecture in principle. Layer 3 proves Layers 1+2 produced clean bundle — responsibilities stacked correctly. "
            "Gap identified: LD-112 HTTP endpoint markers not scanned. Suggested expansion: add react-native-http-bridge, 8082, startHTTPServer. "
            "[REJECTED by synthesis — see counter C3: speculative (Blocker #2 not yet implemented), false-positive-prone (8082), "
            "tree-shaking would elide import strings anyway, and violates Rule 19 STOP trigger on scope creep.] "
            "PR-gated scope acceptable IF branch-protection follow-up tracked [ACCEPTED — new blocker queued]. "
            "Bundle #3+#9 into one file: architecturally correct, same concern."
        ),
    },
]

COUNTERS = [
    {
        "angle": "counter_to_speed",
        "summary": (
            "CRITICAL C1: Metro cache key (package-lock + app.json + metro.config) omits src/** — stale cache could return OLD bundle bytes, "
            "greening regressions. FIX: drop cache entirely, full expo export every PR. "
            "HIGH: grep -RF on dist scans PNG/WOFF/sourcemaps -> binary noise/false positives. FIX: add -I flag + restrict globs to *.js/*.html/*.map. "
            "HIGH: expo export -p web on SDK 54 + new arch is 2-4 min cold, not 60-90s. Budget 5-7 min realistic. "
            "MEDIUM: npm ci on ~1500 Expo deps is 60-90s, not 30-45. "
            "LOW: missing negative-path test — covered by handoff's manual test step."
        ),
    },
    {
        "angle": "counter_to_safety",
        "summary": (
            "CRITICAL C2: Layers 1 and 2 share NODE_ENV plumbing as common root — NOT independent. "
            "If NODE_ENV doesn't thread through Metro correctly, BOTH __DEV__ guard and build-level strip fail together. "
            "Layer 3 becomes load-bearing. ACKNOWLEDGED in synthesis — Blocker #9 verify is precisely the mechanism that converts NODE_ENV hope->check. "
            "HIGH: sourcemaps (.map) preserve original identifiers. FIX: include .map in scan. "
            "HIGH: PR-gate non-binding without required-status-check branch protection (not yet configured). Track as new follow-up blocker. "
            "MEDIUM: marker list may be incomplete — 4-marker spec is per handoff, stay to spec per Rule 19, log in blind spots."
        ),
    },
    {
        "angle": "counter_to_maintainability",
        "summary": (
            "HIGH H5: plain-English fail messages on public PR could leak scanner surface. "
            "MITIGATION: repo is private (gh auth confirmed kimhyla/mindfulnest), lower exposure; neutral top-level summary + specifics in job log. "
            "HIGH M2: README.md is scope creep not authorized by Blocker #3+#9. DROPPED from scope. "
            "MEDIUM: checkout->setup-node->cache->build->assert pattern does NOT generalize to Maestro tier-1 (needs macOS runner, xcrun simctl, .app bundle). "
            "Don't oversell as template. LOW: 6-line top-of-file comment fine; trim blocker-ID/owner which belongs in Directus (keep purpose/trigger/failure)."
        ),
    },
    {
        "angle": "counter_to_architectural",
        "summary": (
            "CRITICAL C3: scanning for LD-112 markers pre-emptively is speculative — Blocker #2 not yet implemented. REJECTED. "
            "HIGH: 8082 literal is false-positive guaranteed — Metro default is 8081 but 8082 appears as numeric literals/minified indices/timestamps. REJECTED. "
            "HIGH: react-native-http-bridge import string may not survive tree-shaking if __DEV__ guarded — scan would pass vacuously. REJECTED. "
            "MEDIUM: branch-protection follow-up must be NAMED tracked blocker, not hand-waved. ADDRESSED — will register in Phase 5. "
            "MEDIUM: expanding marker set violates Rule 19 STOP trigger on scope creep. Stay at 4 markers. "
            "LOW: bundle #3+#9 couples debugging — mitigated by distinct step names within single workflow."
        ),
    },
]

SYNTHESIS = (
    "All CRITICAL findings addressed:\n"
    "C1 (counter-to-speed): Metro cache DROPPED. Full expo export every PR (5-7 min budget).\n"
    "C2 (counter-to-safety): Layers 1+2 share NODE_ENV as common root — accepted architectural reality. "
    "Layer 3 documented as load-bearing. Blocker #9 NODE_ENV verify converts build-config assumption into a check.\n"
    "C3 (counter-to-architectural): LD-112 marker expansion REJECTED. Stay to exact 4 handoff markers. "
    "Future blocker queued for post-Blocker-#2 HTTP endpoint scan.\n"
    "\n"
    "HIGH findings addressed:\n"
    "- grep gets -I flag + globs restricted to *.js/*.html/*.map.\n"
    "- Sourcemap .map files INCLUDED in scan scope.\n"
    "- Wall-clock budget revised to 5-7 min (not 3).\n"
    "- Branch-protection tracked as new follow-up blocker (BRANCH_PROTECTION_REQUIRED_STATUS_CHECK) — to be registered in Phase 5.\n"
    "- Fail message uses neutral top-level summary; specifics remain visible in job logs (repo is private — kimhyla/mindfulnest).\n"
    "- README.md DROPPED from scope.\n"
    "- Signed-commits/CODEOWNERS DEFERRED to separate blocker.\n"
    "\n"
    "Approved to proceed to Phase 1."
)

PAYLOAD = {
    "task_id": TASK_ID,
    "task_type": "architectural",
    "task_description": TASK_DESCRIPTION,
    "claude_summary": CLAUDE_SUMMARY,
    "agent_advocates": ADVOCATES,
    "agent_counters": COUNTERS,
    "synthesis": SYNTHESIS,
    "approved_to_proceed": True,
    "approved_at": datetime.now(timezone.utc).isoformat(),
}


def main():
    creds = load_credentials()
    client = DirectusClient(
        creds["directus_url"],
        creds["directus_email"],
        creds["directus_password"],
    )
    client.authenticate()
    print(f"[phase0] Authenticated: {creds['directus_url']}")

    # Idempotency check
    existing = client._request(
        "GET",
        "/items/prod_preflight_reviews",
        params={"filter[task_id][_eq]": TASK_ID, "limit": 1},
    )
    if existing.get("data"):
        row = existing["data"][0]
        print(f"[phase0] Row for task_id={TASK_ID} already exists (id={row.get('id')}). Skipping POST.")
        print(f"[phase0] approved_to_proceed={row.get('approved_to_proceed')}")
        return

    # POST
    print(f"[phase0] POST /items/prod_preflight_reviews task_id={TASK_ID}")
    result = client._request("POST", "/items/prod_preflight_reviews", data=PAYLOAD)
    new_id = result["data"]["id"]
    print(f"[phase0] Created row id={new_id}")

    # Readback (Step 6)
    readback = client._request(
        "GET",
        "/items/prod_preflight_reviews",
        params={"filter[task_id][_eq]": TASK_ID, "limit": 1},
    )
    rows = readback.get("data", [])
    if not rows:
        print(f"[phase0] ERROR — readback returned 0 rows for task_id={TASK_ID}")
        sys.exit(2)

    row = rows[0]
    print(f"[phase0] READBACK OK: id={row['id']} task_id={row['task_id']} "
          f"task_type={row['task_type']} approved={row['approved_to_proceed']}")
    print(f"[phase0] DONE — Phase 0 Step 6 confirmed. Proceed to Phase 1.")


if __name__ == "__main__":
    main()
