"""
Stillgen Phase 1 — 3 live BFL end-to-end batches.

Per HANDOFF_STILLGEN_PHASE1_READY_20260421.md §3.2 acceptance criteria + activity_log 1145
design:
  Batch 1: tessa   hero=51  live  approve
  Batch 2: chipper hero=50  dry-run → live-gen → reject
  Batch 3: tessa   hero=51  live  approve  (exercises cost accumulator)

Calls `stillgen_server.generate_master` / `approve_master` directly — bypasses the HTTP layer
because the HTTP wrapper is trivial (covered by unit tests) and a direct call keeps the test
runner synchronous + easier to debug.

Usage:
    python Production/scripts/stillgen_phase1_live_batches.py
Requires:
    DIRECTUS_EMAIL / DIRECTUS_PASSWORD env set (or API_KEYS_MASTER.md reachable at Mac path).
    BFL_API_KEY env OPTIONAL (falls back to API_KEYS_MASTER.md parse).
"""
from __future__ import annotations

import os
import sys
import time
import uuid
from datetime import datetime, timezone

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, os.pardir, os.pardir))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from Production.api import stillgen_server as S
from Production.lib.directus_admin_client import DirectusAdminClient


def _banner(msg: str) -> None:
    print("\n" + "=" * 72)
    print(f"  {msg}")
    print("=" * 72)


def main() -> int:
    c = DirectusAdminClient()

    results: list[dict] = []
    total_cost = 0.0
    started_spend = S._cost_read_today()
    print(f"[runner] day-to-date spend at start: ${started_spend:.4f}")

    # ------------- BATCH 1: Tessa, live, approve -------------
    _banner("BATCH 1: Tessa (hero 51), LIVE, approve")
    mid1 = f"live-batch-1-{uuid.uuid4().hex[:8]}"
    t0 = time.time()
    gen1 = S.generate_master({
        "character_id": "tessa",
        "pose_description": "standing at the edge of a forest clearing, looking thoughtful",
        "costume_hint": None,
        "hero_reference_asset_id": 51,
        "style_tier": None,
        "dry_run": False,
        "mutation_id": mid1,
    }, client=c)
    gen1_s = time.time() - t0
    print(f"  generate OK in {gen1_s:.1f}s  file_hash={gen1['file_hash'][:24]}..."
          f"  bfl_job={gen1.get('bfl_job_id')}  cost=${gen1['estimated_cost_usd']}")
    total_cost += gen1["estimated_cost_usd"]

    appr1 = S.approve_master({"mutation_id": mid1, "approved": True}, client=c)
    print(f"  approve OK: asset_id={appr1['asset_id']}  filepath={appr1['filepath']}")
    results.append({"batch": 1, "mutation_id": mid1, "gen_sec": gen1_s, "asset_id": appr1["asset_id"],
                    "bfl_job_id": gen1.get("bfl_job_id"), "cost": gen1["estimated_cost_usd"],
                    "sha256": gen1["file_hash"]})

    # ------------- BATCH 2: Chipper, dry-run -> live-gen -> reject -------------
    _banner("BATCH 2a: Chipper (hero 50), DRY-RUN")
    mid2_dry = f"live-batch-2-dry-{uuid.uuid4().hex[:8]}"
    dry = S.generate_master({
        "character_id": "chipper",
        "pose_description": "perched on a low branch, head tilted",
        "costume_hint": None,
        "hero_reference_asset_id": 50,
        "style_tier": None,
        "dry_run": True,
        "mutation_id": mid2_dry,
    }, client=c)
    print(f"  dry-run OK: status={dry['status']}  cost={dry['estimated_cost_usd']}"
          f"  dims={dry['dimensions']}")

    _banner("BATCH 2b: Chipper (hero 50), LIVE, reject")
    mid2 = f"live-batch-2-{uuid.uuid4().hex[:8]}"
    t0 = time.time()
    gen2 = S.generate_master({
        "character_id": "chipper",
        "pose_description": "perched on a low branch, head tilted",
        "costume_hint": None,
        "hero_reference_asset_id": 50,
        "style_tier": None,
        "dry_run": False,
        "mutation_id": mid2,
    }, client=c)
    gen2_s = time.time() - t0
    print(f"  generate OK in {gen2_s:.1f}s  file_hash={gen2['file_hash'][:24]}..."
          f"  bfl_job={gen2.get('bfl_job_id')}  cost=${gen2['estimated_cost_usd']}")
    total_cost += gen2["estimated_cost_usd"]

    appr2 = S.approve_master({"mutation_id": mid2, "approved": False}, client=c)
    print(f"  reject OK: status={appr2['status']}")
    results.append({"batch": 2, "mutation_id": mid2, "gen_sec": gen2_s,
                    "asset_id": None, "rejected": True,
                    "bfl_job_id": gen2.get("bfl_job_id"),
                    "cost": gen2["estimated_cost_usd"],
                    "sha256": gen2["file_hash"]})

    # ------------- BATCH 3: Tessa, live, approve, validates cost accumulator -------------
    _banner("BATCH 3: Tessa (hero 51), LIVE, approve (cost accumulator check)")
    mid3 = f"live-batch-3-{uuid.uuid4().hex[:8]}"
    pre_spend = S._cost_read_today()
    t0 = time.time()
    gen3 = S.generate_master({
        "character_id": "tessa",
        "pose_description": "kneeling beside a small stream, reaching to touch the water",
        "costume_hint": None,
        "hero_reference_asset_id": 51,
        "style_tier": None,
        "dry_run": False,
        "mutation_id": mid3,
    }, client=c)
    gen3_s = time.time() - t0
    post_spend = S._cost_read_today()
    print(f"  generate OK in {gen3_s:.1f}s  file_hash={gen3['file_hash'][:24]}..."
          f"  bfl_job={gen3.get('bfl_job_id')}  cost=${gen3['estimated_cost_usd']}"
          f"  pre_spend=${pre_spend:.4f}  post_spend=${post_spend:.4f}")
    assert post_spend > pre_spend, f"cost accumulator did not advance: {pre_spend} → {post_spend}"
    total_cost += gen3["estimated_cost_usd"]

    appr3 = S.approve_master({"mutation_id": mid3, "approved": True}, client=c)
    print(f"  approve OK: asset_id={appr3['asset_id']}  filepath={appr3['filepath']}")
    results.append({"batch": 3, "mutation_id": mid3, "gen_sec": gen3_s, "asset_id": appr3["asset_id"],
                    "bfl_job_id": gen3.get("bfl_job_id"), "cost": gen3["estimated_cost_usd"],
                    "sha256": gen3["file_hash"],
                    "cost_accumulator_validated": True})

    # ------------- Post-batch verification -------------
    _banner("Verification: reading approved rows back from Directus")
    for r in results:
        if r.get("asset_id"):
            row = c._request("GET", f"/items/{S.COLLECTION}/{r['asset_id']}")
            missing = [f for f in ("character_id", "is_current", "generated_by", "flux_model",
                                    "hero_reference_asset_id", "file_size_bytes", "role", "sha256",
                                    "generated_at", "bfl_job_id", "estimated_cost_usd")
                       if row.get(f) in (None, "")]
            if missing:
                print(f"  ASSET {r['asset_id']} MISSING fields: {missing}")
            else:
                print(f"  ASSET {r['asset_id']} verified — all provenance fields populated")
            r["directus_row_verified"] = not missing

    # ------------- Completion summary -------------
    _banner("SUMMARY")
    for r in results:
        print(f"  batch {r['batch']}: " + ", ".join(f"{k}={v}" for k, v in r.items()))
    print(f"\n  total BFL spend this run: ${total_cost:.4f}")
    print(f"  day-to-date spend now: ${S._cost_read_today():.4f}")

    # Completion activity log
    c.post_item("prod_activity_log", {
        "action": "stillgen_phase1_live_batches_complete",
        "details": {
            "task_id": "stillgen-phase1-endpoint-build-20260421",
            "run_at": datetime.now(timezone.utc).isoformat(),
            "total_cost_usd": round(total_cost, 4),
            "day_to_date_spend_usd": round(S._cost_read_today(), 4),
            "batches": results,
        },
        "performed_by": "claude",
    })
    print("\n[runner] logged completion to prod_activity_log")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
