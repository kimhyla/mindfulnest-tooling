#!/usr/bin/env python3
"""Register Phase 0 preflight row for Preview Stitched V3 — Phase B + Phase A.

Writes (or PATCHes, depending on --approve flag) a prod_preflight_reviews row
for task_id `preview_stitched_v3_phase_b_a_implementation_20260419`. Parent
preflight is 98 (zoomed-out 4+4 debate, 2026-04-19).

Idempotent: duplicate task_id => 400 => exits 0 with "already_registered".
On --approve, PATCHes the existing row to set approved_to_proceed=true.

Run from project root:

    python3 Production/scripts/register_preview_stitched_v3_preflight_20260419.py
    python3 Production/scripts/register_preview_stitched_v3_preflight_20260419.py --approve
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_TOOLS_LIB = _HERE.parent / "tools" / "lib"
sys.path.insert(0, str(_TOOLS_LIB))

from credentials import load_credentials  # type: ignore
from directus import DirectusClient, DirectusError  # type: ignore


TASK_ID = "preview_stitched_v3_phase_b_a_implementation_20260419"
PARENT_PREFLIGHT_ID = 98


TASK_DESCRIPTION = (
    "Implement Preview Stitched V3 -- Phase B + Phase A authoring panels as "
    "storyboard extension per TECH_SPEC_PREVIEW_STITCHED_V3_PHASE_B_20260419.md. "
    "Governed files: production_server.py, storyboard_v38_prod.html (via Path B "
    "patcher). New files: patch_v38_phase_b.py, test_phase_b_panel.py. Extends: "
    "lib/ffmpeg_stitch.py (new render_watercolor_overlay helper with "
    "frame_x/frame_y params + chromakey branch per C4). Ships Phase A with "
    "placeholder assets; real assets arrive via parallel session "
    "HANDOFF_PHASE_A_ASSET_GENERATION_20260419.md and swap via state field."
)


CLAUDE_SUMMARY = (
    "Convergence from ffmpeg overlay 4+4 debate (parent preflight 98): A1 linear "
    "filter_complex wins on fidelity + integration (C2, C4) for meditation's "
    "breath-cued watercolor overlay use case; A4 Python compositor is 2-3x "
    "faster but loses on sub-frame timing precision and native easing. C4 "
    "required parameterization of the overlay helper (single function serves "
    "Phase A frame_x=800 and Phase B frame_x=40) plus a chromakey branch for "
    "cue_type=video (Chipper fallback when Kling alpha channel unavailable). "
    "Preview fidelity documented as +/-50ms approximation; exact parity deferred "
    "to V4 if Kim reports visual drift. "
    "Advocate + counter spawned in parallel per routine+ classification. "
    "Advocate confirms all 25 state fields, 4 endpoints, render_watercolor_overlay "
    "signature, chromakey branch, 15 tests, and patcher clone plan are "
    "implementable as specified. Counter stress-tested: (a) whitelist round-trip "
    "(new fields added to _V2_MODULE_ALLOWED_FIELDS, JSON-string validation); "
    "(b) cache hash completeness on watercolor cue edits; (c) lipsync cache "
    "invalidation on base_clip_mtime; (d) rollback reversibility; (e) Phase A "
    "placeholder resolution with .mov extension vs spec's .mp4; (f) WaveSurfer.js "
    "60KB inline bundle vs base64 image regex collision risk. Any HIGH/MEDIUM "
    "findings resolved before Phase 1.3 begins."
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--approve", action="store_true",
                    help="PATCH existing row to set approved_to_proceed=true")
    ap.add_argument("--approval-note", type=str, default="",
                    help="Short note to append to claude_summary on approval")
    args = ap.parse_args()

    creds = load_credentials()
    client = DirectusClient(
        creds["directus_url"], creds["directus_email"], creds["directus_password"],
    )
    client.authenticate()
    print("[directus] authenticated")

    now = datetime.now(timezone.utc).isoformat()

    if args.approve:
        pid = _patch_approved(client, args.approval_note)
        print(json.dumps({"preflight_id": pid, "approved": True}, indent=2))
        return 0

    pid = _register_preflight(client, now)
    print(json.dumps({"preflight_id": pid, "approved": False}, indent=2))
    return 0


def _register_preflight(client, now):
    body = {
        "task_id": TASK_ID,
        "task_type": "routine",
        "task_description": TASK_DESCRIPTION,
        "classification": "routine+",
        "advocates_count": 1,
        "counters_count": 1,
        "parent_preflight_id": PARENT_PREFLIGHT_ID,
        "approved_to_proceed": False,
        "claude_summary": CLAUDE_SUMMARY,
        "date_reviewed": now,
    }
    try:
        r = client._request("POST", "/items/prod_preflight_reviews", data=body)
        pid = r.get("data", {}).get("id")
        print(f"[directus] prod_preflight_reviews id={pid} "
              f"(parent={PARENT_PREFLIGHT_ID})")
        return pid
    except DirectusError as exc:
        msg = (exc.detail or "").lower()
        if "duplicate" in msg or "unique" in msg:
            print(f"[directus] preflight already registered (idempotent skip): "
                  f"{exc.detail[:200]}")
            # Look up existing id for approval path
            r = client._request(
                "GET",
                f"/items/prod_preflight_reviews?filter[task_id][_eq]={TASK_ID}&fields=id",
            )
            data = r.get("data") or []
            if data:
                return data[0].get("id")
            return "already_registered"
        print(f"[directus] preflight failed: {exc.status} {exc.detail[:500]}",
              file=sys.stderr)
        raise


def _patch_approved(client, approval_note):
    # Find existing row
    r = client._request(
        "GET",
        f"/items/prod_preflight_reviews?filter[task_id][_eq]={TASK_ID}&fields=id,claude_summary",
    )
    data = r.get("data") or []
    if not data:
        print(f"[directus] no row found for task_id={TASK_ID} -- register first",
              file=sys.stderr)
        return None
    pid = data[0]["id"]
    existing_summary = data[0].get("claude_summary") or ""
    new_summary = existing_summary
    if approval_note:
        new_summary = existing_summary + "\n\n[APPROVED] " + approval_note
    body = {"approved_to_proceed": True}
    if approval_note:
        body["claude_summary"] = new_summary
    try:
        r = client._request("PATCH", f"/items/prod_preflight_reviews/{pid}", data=body)
        print(f"[directus] PATCHed preflight id={pid} approved_to_proceed=true")
        return pid
    except DirectusError as exc:
        print(f"[directus] approve failed: {exc.status} {exc.detail[:500]}",
              file=sys.stderr)
        raise


if __name__ == "__main__":
    sys.exit(main())
