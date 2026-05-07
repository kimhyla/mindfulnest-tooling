#!/usr/bin/env python3
"""Δ-architecture-tighten — PATCH LD `DISPLAY_ORDER_STRICT_V1` (id=530).

Per Kim 2026-05-05: clean_orphan_beats_v3.py removed from enforcement
chain; server-side write-time prune in mutate_video_state is the
correct mechanism. PATCH appends the architectural-tighten note to
the existing decision_text (does not replace).

Mirrors c5_patch_production_map_multi_event_mapping_v1.py pattern:
DirectusAdminClient PATCH directly with data= kwarg + read-back
verify. Idempotent: refuses to double-append if the marker phrase
is already in the row.

Run from repo root:
    python3 Production/scripts/c2_tighten_patch_display_order_strict_v1.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "Production" / "lib"))

from directus_admin_client import DirectusAdminClient  # noqa: E402

DECISION_KEY = "DISPLAY_ORDER_STRICT_V1"
NOW_ISO = datetime.now(timezone.utc).isoformat()

# Append text per Kim 2026-05-05 (verbatim from inline message).
APPEND_TEXT = (
    "\n\n---\n\n"
    "[ARCHITECTURAL TIGHTEN 2026-05-05 per Kim] Removed "
    "clean_orphan_beats_v3.py from enforcement chain. The server prune in "
    "mutate_video_state catches orphans at write-time, which is more "
    "correct than after-the-fact cleanup. Pre-existing damage is handled "
    "by one-shot data migrations under Production/scripts/.oneshot/.\n\n"
    "Final enforcement remains defense-in-depth at two layers:\n"
    "(1) StoryboardTab.tsx renderer Array.isArray gate (read-time honor)\n"
    "(2) production_server.py mutate_video_state prune (write-time enforce)\n\n"
    "Cleanup script removal commit follows this PATCH on branch "
    "claude/post-redeploy-bug-triage. Bundle paused at this commit pending "
    "tech-spec on authoring workflow architecture (Kim 2026-05-05; chip "
    "spawned for next-session execution).\n\n"
    f"PATCH applied: {NOW_ISO}"
)

MARKER = "ARCHITECTURAL TIGHTEN 2026-05-05"


def main() -> int:
    client = DirectusAdminClient()

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

    if MARKER in existing_text:
        print(f"  ALREADY PATCHED — refusing to double-append.")
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

    print()
    print("=== read-back verify ===")
    verify = client.get_item("prod_locked_decisions", ld_id)
    if not verify:
        print(f"FAIL: read-back returned no row at id={ld_id}")
        return 1
    verify_text = verify.get("decision_text") or ""
    if MARKER not in verify_text:
        print(f"FAIL: marker {MARKER!r} not found in read-back text")
        return 1
    # Quote a fragment around the marker so the verification output
    # captures Kim's requested phrase visibly.
    idx = verify_text.find(MARKER)
    fragment_start = max(0, idx - 30)
    fragment_end = min(len(verify_text), idx + 200)
    fragment = verify_text[fragment_start:fragment_end].replace("\n", " ")
    print(f"  OK: id={ld_id} decision_text length={len(verify_text)} chars")
    print(f"  marker fragment: ...{fragment}...")

    print()
    print("=" * 60)
    print(f"C2_TIGHTEN_PATCH_OK: {DECISION_KEY} (id={ld_id}) appended + read-back verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
