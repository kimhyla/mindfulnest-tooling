#!/usr/bin/env python3
"""
One-shot writer for the governance-bundle-20260416 preflight audit row.
Phase 0 4+4 advocate+counter debate captured for prod_preflight_reviews.
"""

import sys, os, json
THIS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(THIS, "..", "tools")))

from credentials_lib.credentials import load_credentials
from credentials_lib.directus import DirectusClient

TASK_ID = "governance-bundle-20260416"
TASK_TYPE = "architectural"
TASK_DESCRIPTION = (
    "Bundled governed-file edits from Kim: "
    "(E1) insert Rule 21 'Numerical Decision-Gate Governance' into CLAUDE.md after Rule 20; "
    "(E2) add 1-line SUPERSEDED banner to 4 animation-stack docs "
    "(VISUAL_AND_ANIMATION_PIPELINE_LOCKED_DECISIONS_APRIL10_2026.md, "
    "APP_DEV_AUTOMATION_ARCHITECTURE_v1.md, "
    "SESSION_DECISIONS_April10_2026_PRODUCTION_STRATEGY.md, "
    "HANDOFF_STAGE2_REMAINING_BLOCKERS_April16_2026.md); "
    "(E3) replace fabricated iOS cache + unsourced WebView audio-latency claims in "
    "APP_DEV_AUTOMATION_ARCHITECTURE_v1.md Part 1B Capacitor row with 3 technical reasons "
    "(WKWebView Web-Audio/rAF sync, HEVC composition bugs, IndexedDB purge). "
    "Cross-reference task_id architecture-reconciliation-v1-20260416."
)

CLAUDE_SUMMARY = (
    "Bundle plugs the governance hole surfaced by today's architecture reconciliation v2 "
    "(fabricated 45ms/50MB/200-500ms numerical claims used as decision gates). "
    "Rule 21 + prod_numerical_claims registry + banners + targeted Capacitor fix all "
    "land in one atomic governed-file operation under terminal CLI (Rule 19). "
    "Agent debate approved the intent but surfaced 4 blocking details requiring Kim clarification "
    "before write; preflight held at approved_to_proceed=false pending her response."
)

ADVOCATES = [
    {
        "agent": "A1",
        "angle": "rule_alignment",
        "finding": "Rule 21 creates scope friction with Rule 19 (app-code scope) and overlaps Rule 18 (two-write auto-registration). Cross-reference to 'Rule 19 error path' is incoherent since Rule 19 is explicitly scoped to shipping code, not documentation claims.",
        "severity": "MEDIUM",
        "recommendation": "proceed-with-change",
        "suggested_change": "Consider renumbering as 19.A sub-rule OR anchor the cross-reference to Rule 18 auto-registration machinery instead of Rule 19. Clarify whether prod_numerical_claims is auto-populated by Rule 18 cascade or manually maintained."
    },
    {
        "agent": "A2",
        "angle": "banner_cascade_completeness",
        "finding": "4 target files are correctly identified but cascade is incomplete — VISUAL_PIPELINE_MASTER_PLAN_v5.md, TECHNICAL_PIPELINE_RESEARCH_AND_RECOMMENDATIONS_April2026.md, and SPINE_RESEARCH_SUMMARY docs all reference the same obsolete animation-stack decisions. Banner wording 'may be obsolete' is generic enough to mislead in mixed-content files.",
        "severity": "HIGH",
        "recommendation": "proceed-with-change",
        "suggested_change": "Expand cascade to 6+ files or create a single cascade index doc. For mixed-content files (APP_DEV_AUTOMATION, SESSION_DECISIONS_April10), scope the banner ('Animation-stack decisions in Part 1B & Decision #6 only. Rest of document is current.')."
    },
    {
        "agent": "A3",
        "angle": "technical_correctness_of_capacitor_replacements",
        "finding": "3 replacement reasons (WKWebView Web-Audio/rAF thread separation, HEVC composition bugs, IndexedDB purging under storage pressure) are technically plausible and directly tied to this app's clinical requirements (breathing circle sync, transparent creature loops, offline therapy access). Substantively stronger than the struck fabricated numbers.",
        "severity": "LOW",
        "recommendation": "proceed",
        "suggested_change": "None — replacement content is sound. But see C3 for sourcing concern."
    },
    {
        "agent": "A4",
        "angle": "governance_precedent_fit",
        "finding": "Bundle fits the April 16 institutional pattern: Rule 19 Hardened Protocol + Rule 20 Auto-Capture + weekly preflight audit. Directly addresses documented failure modes from today's architecture reconciliation (fabricated 45ms + ~25 other unsourced gate numbers). Severity hierarchy (critical structural prevention / high tactical fix) is correct.",
        "severity": "APPROVED",
        "recommendation": "proceed",
        "suggested_change": "None — governance scoping is correct."
    }
]

COUNTERS = [
    {
        "agent": "C1",
        "angle": "rule_21_self_application_paradox",
        "finding": "(a) Rule 21 itself contains numerical claims (e.g., 'April 16, 2026' creation date) that arguably violate the rule — semantic-identifier vs empirical-claim ambiguity. (b) Option (c) 'ASSUMPTION NEEDS VERIFICATION MAY BE WRONG' label is a documentation gate not a blocking gate — a number labeled compliant can still ship. (c) 'Decision criterion' scope is undefined — version numbers? cost estimates? FPS targets? all count?",
        "severity": "HIGH",
        "recommendation": "proceed-with-change",
        "suggested_change": "Narrow scope to 'empirical or quantitative claim used to gate code behavior, feature toggles, pipeline acceptance, or performance targets' — excluding semantic identifiers (dates, version numbers, entity counts). Tighten option (c) so labeled claims cannot reach production without re-validation."
    },
    {
        "agent": "C2",
        "angle": "banner_ambiguity_and_scope_creep",
        "finding": "'MAY be obsolete' is non-actionable hedging. Target file #4 HANDOFF_STAGE2_REMAINING_BLOCKERS_April16_2026.md has essentially NO animation-stack content (single incidental mention in test-tier categorization context). Placing the banner there is a false positive that pollutes the signal. Files #2 and #3 have mostly non-animation content but banner under title implies whole-document supersession.",
        "severity": "HIGH",
        "recommendation": "proceed-with-change",
        "suggested_change": "(1) Drop banner from HANDOFF_STAGE2 (no animation content). (2) For mixed-content files, scope banner to animation sections specifically or split into 2 lines: generic supersession + explicit list of which sections remain locked. (3) Define 'Gate 2' inline."
    },
    {
        "agent": "C3",
        "angle": "edit_3_irony_trap",
        "finding": "Edit 3 replaces 2 unsourced claims with 3 new claims. The 3 new claims are plausible but UNSOURCED per Rule 21's own standard (no Apple radar links, no WebKit issue URLs, no Kim test data). Edit 1 introduces the rule that Edit 3 immediately violates in the same bundle. Per reconciliation doc D4, the approved label is 'ASSUMPTION NEEDS VERIFICATION MAY BE WRONG' — the 3 reasons should carry it, or citations should be added.",
        "severity": "CRITICAL",
        "recommendation": "proceed-with-change",
        "suggested_change": "Either (a) add inline citations for each of the 3 reasons, or (b) label each with 'ASSUMPTION NEEDS VERIFICATION MAY BE WRONG' per D4 convention, or (c) commit to a 7-day grace period with due-date registered in prod_numerical_claims. Ship but tag."
    },
    {
        "agent": "C4",
        "angle": "registry_dependency",
        "finding": "OVERTURNED on verification. C4 claimed prod_numerical_claims was never built and Rule 21 was a forward reference — based on reconciliation doc's '⏳ queued' status. DIRECTUS VERIFICATION shows the collection EXISTS with a well-designed schema (claim_key, claim_text, current_value, unit, category, status, source, used_as_gate, impact_if_wrong, recommended_action, date_flagged, date_verified, related_docs). The 'queued' status in the doc must have been closed in the Cowork session. Finding downgraded from CRITICAL/BLOCK to INFO.",
        "severity": "INFO",
        "recommendation": "proceed",
        "suggested_change": "Update MINDFULNEST_ARCHITECTURE_RECONCILIATION_v2.md line 171 status from '⏳' to '✅' to reflect actual state. Consider seeding the registry with the 5 known fabricated/flagged numbers (45ms, $2.82 TTS, $0.58 AI Coach, 15-22wk timeline, 50MB cache) as initial entries."
    }
]

SYNTHESIS = (
    "Advocate consensus: intent is sound and fits governance precedent (A4 APPROVED). "
    "3 MEDIUM/HIGH advocate concerns (scope boundary with Rule 19, cascade incompleteness, banner wording) "
    "do not block but should inform final wording. "
    "Counter-agent C4's CRITICAL/BLOCK recommendation was overturned by direct Directus verification — "
    "prod_numerical_claims DOES exist with a good schema. "
    "Remaining counter findings that BLOCK execution without Kim clarification: "
    "(1) Edit 3 number mismatch — Kim's prompt says strike '200MB iOS cache limit' but file line 60 "
    "actually says '50MB iOS cache limit'. Need her confirmation of intent. "
    "(2) Edit 3 format — current cell is a compact markdown table row; 3 long technical reasons as prose "
    "do not fit a table cell. Need format direction (bulleted table cell vs dedicated subsection vs footnote). "
    "(3) Banner on HANDOFF_STAGE2 — file has essentially zero animation-stack content (1 incidental mention "
    "in test-tier context). Placing banner there would be a false positive. C2 flagged; recommend drop from scope. "
    "(4) Rule-21 self-compliance for Edit 3 — new technical reasons are unsourced per D4 approved convention "
    "should they carry 'ASSUMPTION NEEDS VERIFICATION MAY BE WRONG' label? "
    "Held at approved_to_proceed=false pending Kim's response to these 4 items. Schema caveats from C1 "
    "(scope definition) and A1 (Rule 18 anchor) flagged as non-blocking refinements for future consideration."
)

def main():
    creds = load_credentials()
    cli = DirectusClient(creds["directus_url"], creds["directus_email"], creds["directus_password"])
    cli.authenticate()

    payload = {
        "task_id": TASK_ID,
        "task_type": TASK_TYPE,
        "task_description": TASK_DESCRIPTION,
        "claude_summary": CLAUDE_SUMMARY,
        "agent_advocates": ADVOCATES,
        "agent_counters": COUNTERS,
        "synthesis": SYNTHESIS,
        "approved_to_proceed": False,
    }

    existing = cli.get("prod_preflight_reviews", filters={"task_id": {"_eq": TASK_ID}})
    if existing:
        row_id = existing[0]["id"]
        result = cli.update("prod_preflight_reviews", row_id, payload)
        print(f"[preflight] PATCHED existing row id={row_id} for task_id={TASK_ID}")
    else:
        result = cli.create("prod_preflight_reviews", payload)
        print(f"[preflight] CREATED new row id={result.get('id')} for task_id={TASK_ID}")

    print(f"[preflight] approved_to_proceed=False (held pending Kim clarification on 4 items)")

if __name__ == "__main__":
    main()
