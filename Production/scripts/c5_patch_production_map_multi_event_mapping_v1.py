#!/usr/bin/env python3
"""C5 closure (post-redeploy-bug-triage) — PATCH existing LD
`PRODUCTION_MAP_MULTI_EVENT_MAPPING_V1` decision_text per Kim's REFINED
text (carryover #2, 2026-05-05).

Appends to existing decision_text; does not replace. Uses
DirectusAdminClient PATCH directly (no `lock_decision.py` patch CLI
because that path is single-field-overwrite, not append).

Per Rule 35: read-back verify on every write.

Run from repo root:
    python3 Production/scripts/c5_patch_production_map_multi_event_mapping_v1.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "Production" / "lib"))

from directus_admin_client import DirectusAdminClient  # noqa: E402

DECISION_KEY = "PRODUCTION_MAP_MULTI_EVENT_MAPPING_V1"
NOW_ISO = datetime.now(timezone.utc).isoformat()

# REFINED append text per Kim 2026-05-05 carryover #2 + Δ-C5 closure plan.
APPEND_TEXT = (
    "\n\n---\n\n"
    "PATCH 2026-05-05 (post-redeploy-bug-triage Δ-C5 closure):\n\n"
    "Per Kim 2026-05-05: confirmed 1:1 module-to-event cardinality — "
    "'one distinct module per event' (no multi-tenant events). Combined "
    "with the Production Map page header note ('author each by creating "
    "an Event' — implying authoring-order numbering) AND empirical "
    "smoke-verification 2026-05-05 that authored modules M1-M6 resolve "
    "to Event_1-Event_6 respectively (post Δ-C5.5 Python redeploy), the "
    "m_number=N → Event_N IDENTITY is established as the design contract, "
    "not an interim measure. The contract test below pins the identity; "
    "if a future authoring workflow ever creates a module out of N-order "
    "such that m_number ≠ event_number, the test will fail and a HARD "
    "upgrade to schema-backed lookup is the right next step at that "
    "point.\n\n"
    "CONTRACT TEST: "
    "Production/tools/tests/test_production_map_m_to_event_convention.py "
    "(4 tests, all GREEN 2026-05-05). Pins:\n"
    "  - M1 → Event_1 (when Event_1/ exists on disk)\n"
    "  - M2 → Event_2 (when Event_2/ exists on disk)\n"
    "  - M3 → None (when Event_3/ does NOT exist) — explicit guard "
    "against silent always-Event_1 fallback\n"
    "  - aggregate: every row resolves to either Event_<m_number> or "
    "None; no cross-row silent fallback to a different Event_<N>/\n\n"
    "ALSO: Δ-C5.5 closure — original Bug C symptom (uniform Event_1 "
    "across all rows) traced to a server-side Python deploy gap "
    "(Dropbox/Production/tools/production_server.py was the May 3 "
    "pre-S5.5g version; tooling-repo had the convention fix at "
    "production_server.py:8537-8548). Re-deploy 2026-05-05 synced "
    "tooling-repo → Dropbox; server restart loaded the fix; smoke "
    "passed with M1=Event_1, M2=Event_2, M3+=None.\n\n"
    "Bundle followup: spec §3.3 Part 1 (HARD upgrade to schema-backed "
    "`prod_modules.event_number`) DROPPED from the post-redeploy bundle. "
    "The SOFT convention is the design contract per cardinality 1:1.\n\n"
    f"PATCH applied: {NOW_ISO}"
)


def main() -> int:
    client = DirectusAdminClient()

    # Find LD by decision_key.
    print(f"=== fetch existing LD {DECISION_KEY} ===")
    rows = client._request(
        "GET",
        f"/items/prod_locked_decisions?filter[decision_key][_eq]={DECISION_KEY}&limit=1",
    )
    if not rows:
        print(f"FAIL: no LD with decision_key={DECISION_KEY}")
        return 1
    row = rows[0]
    ld_id = row.get("id")
    existing_text = row.get("decision_text") or ""
    print(f"  found id={ld_id}")
    print(f"  existing decision_text length: {len(existing_text)} chars")

    # Idempotency guard: don't double-append.
    if "post-redeploy-bug-triage Δ-C5 closure" in existing_text:
        print("  ALREADY PATCHED — refusing to double-append.")
        return 0

    new_text = existing_text + APPEND_TEXT
    print(f"  new decision_text length: {len(new_text)} chars (+{len(APPEND_TEXT)})")

    print()
    print(f"=== PATCH /items/prod_locked_decisions/{ld_id} ===")
    patched = client._request(
        "PATCH",
        f"/items/prod_locked_decisions/{ld_id}",
        data={"decision_text": new_text},
    )
    if not patched:
        print(f"FAIL: PATCH returned empty")
        return 1

    # Read-back verify.
    print()
    print("=== read-back verify ===")
    verify = client.get_item("prod_locked_decisions", ld_id)
    if not verify:
        print(f"FAIL: read-back returned no row at id={ld_id}")
        return 1
    verify_text = verify.get("decision_text") or ""
    if "post-redeploy-bug-triage Δ-C5 closure" not in verify_text:
        print(f"FAIL: append marker not found in read-back text")
        return 1
    print(f"  OK: id={ld_id} decision_text length={len(verify_text)} chars")
    print(f"  marker present: 'post-redeploy-bug-triage Δ-C5 closure'")
    print(f"  contract test ref present: "
          f"{'test_production_map_m_to_event_convention.py' in verify_text}")

    print()
    print("=" * 60)
    print(f"C5_PATCH_OK: {DECISION_KEY} (id={ld_id}) decision_text appended + read-back verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
