#!/usr/bin/env python3
"""Register the ACTIVATION preflight row + companion activity log.

The fix's preflight (id=79), decision (id=276), and activity log (id=457) are
already in Directus. What's still missing is a preflight row for the
ACTIVATION task itself (task_id=`lipsync-trim-fix-activation-20260418`) per
HANDOFF_LIPSYNC_ACTIVATION_20260418.md, with parent_preflight_id=79.

Idempotent: if the row already exists (unique task_id constraint), Directus
returns a 400 that this script treats as "already registered" and exits 0.

Run from project root:

    cd "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files"
    python3 Production/scripts/register_activation_preflight_20260419.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_TOOLS_LIB = _HERE.parent / "tools" / "lib"
sys.path.insert(0, str(_TOOLS_LIB))

from credentials import load_credentials  # type: ignore
from directus import DirectusClient, DirectusError  # type: ignore


TASK_ID = "lipsync-trim-fix-activation-20260418"
FIX_PREFLIGHT_ID = 79
FIX_DECISION_ID = 276
FIX_ACTIVITY_ID = 457


SYNTHESIS = (
    "Phase 0 1+1 deliberation for lipsync trim-fix ACTIVATION (not the fix "
    "itself — that shipped separately, preflight=79, decision=276, "
    "activity=457). Advocate built step sequence with verification gates and "
    "flagged the load-bearing assumption that PID 534 must execute patched "
    "bytecode (not a stale venv or the .bak file). Counter attacked the plan "
    "and found handoff numbers drifted vs live state: beat_11 trim_start=2.0 "
    "(handoff said 5.1), nominally breaking the fail-loud test. Counter "
    "resolved via the raw_dur clamp path — beat_11_option_A.mp4 is 5.042s, "
    "effective_end clamps from UI's 10.0 to 5.042, producing window=3.042s. "
    "Plan survived via assertion swap (trim_window_s ≈ 3.04, not 4.9). "
    "Counter also ruled out $0.45+ spend paths (add_spend only on completed), "
    "confirmed state re-reads from disk each request, and confirmed ffmpeg "
    "input-side seek is frame-accurate with libx264 re-encode. "
    "Execution: 6/6 pre-flight gates pass, beat_11 fail-loud test PASSED "
    "(HTTP 400 with 7 fields, zero WaveSpeed spend), beat_10 happy path "
    "PASSED on retry after WaveSpeed connect timeout (exit 28, known "
    "flakiness). Retry state reset verified: retries=2, superseded_task_ids "
    "captured, task_id/submitted_at cleared each retry. Output MD5 distinct "
    "from pre-fix backup proves trim_start=0.3 changed the pixels. Server "
    "log confirms `-ss 0.300` passed to ffmpeg. Budget: $0.15 of $0.30 cap."
)


TASK_DESCRIPTION = (
    "Activate the shipped lipsync trim-fix by verifying PID 534 runs new "
    "code, running beat_11 fail-loud test (expect HTTP 400), running beat_10 "
    "happy-path submission (real $0.15 WaveSpeed), verifying output MP4 + "
    "retry state reset, and documenting blast radius. Companion to the fix "
    "preflight (id=79) and locked decision LIPSYNC_TRIM_WINDOW_HONORED_20260419 "
    "(id=276)."
)


def main() -> int:
    creds = load_credentials()
    client = DirectusClient(
        creds["directus_url"], creds["directus_email"], creds["directus_password"],
    )
    client.authenticate()
    print("[directus] authenticated")

    now = datetime.now(timezone.utc).isoformat()

    preflight_id = _register_preflight(client, now)
    activity_id = _register_activity(client, now, preflight_id)

    print(json.dumps({
        "activation_preflight_id": preflight_id,
        "activation_activity_id": activity_id,
        "fix_preflight_id": FIX_PREFLIGHT_ID,
        "fix_decision_id": FIX_DECISION_ID,
        "fix_activity_id": FIX_ACTIVITY_ID,
    }, indent=2))
    return 0


def _register_preflight(client, now):
    body = {
        "task_id": TASK_ID,
        "task_type": os.environ.get("PREFLIGHT_TASK_TYPE", "bugfix"),
        "task_description": TASK_DESCRIPTION,
        "classification": "routine+",
        "advocates_count": 1,
        "counters_count": 1,
        "parent_preflight_id": FIX_PREFLIGHT_ID,
        "approved_to_proceed": True,
        "claude_summary": SYNTHESIS,
        "date_reviewed": now,
    }
    try:
        r = client._request("POST", "/items/prod_preflight_reviews", data=body)
        pid = r.get("data", {}).get("id")
        print(f"[directus] activation prod_preflight_reviews id={pid} "
              f"(parent={FIX_PREFLIGHT_ID})")
        return pid
    except DirectusError as exc:
        msg = (exc.detail or "").lower()
        if "duplicate" in msg or "unique" in msg:
            print(f"[directus] activation preflight already registered (idempotent skip): "
                  f"{exc.detail[:200]}")
            return "already_registered"
        print(f"[directus] activation preflight failed: {exc.status} {exc.detail[:500]}",
              file=sys.stderr)
        raise


def _register_activity(client, now, preflight_id):
    body = {
        "action": "lipsync_trim_fix_activation_verified",
        "module_id": 1,
        "performed_by": "claude_autonomous_activation",
        "details": json.dumps({
            "activation_preflight_id": preflight_id,
            "fix_preflight_id": FIX_PREFLIGHT_ID,
            "fix_decision_id": FIX_DECISION_ID,
            "fix_activity_id": FIX_ACTIVITY_ID,
            "old_pid": 87359,
            "new_pid": 534,
            "server_started_utc": "2026-04-18T22:25:12Z",
            "beat_11_result": {
                "verdict": "PASS",
                "http_status": 400,
                "error": "audio exceeds trim window (insufficient video for lipsync)",
                "audio_duration_s": 5.2,
                "trim_window_s": 3.042,
                "needed_s": 5.6,
                "trim_end_clamped_from": 10.0,
                "trim_end_clamped_to": 5.042,
                "wavespeed_spend_usd": 0.0,
            },
            "beat_10_result": {
                "verdict": "PASS_ON_RETRY",
                "attempts": 2,
                "first_failure_reason": "WaveSpeed curl exit 28 (connect timeout), known flakiness not our fix",
                "final_status": "completed",
                "final_task_id": "e375495c536d42d690e6bc305a026b56",
                "superseded_task_ids": ["65da1c1b46e94ec6870f11e236687c94"],
                "retries": 2,
                "output_size_bytes": 489328,
                "output_duration_s": 4.52,
                "output_duration_note": "ByteDance's standard output duration for this audio; pre-fix backup was also 4.52s",
                "pre_fix_backup_md5": "000e0676d0867f577957c6400e2fe566",
                "post_fix_md5": "b8014d1fca50124227073d3c7593caa2",
                "md5_distinct": True,
                "server_log_proof": "[trim] src=beat_10_option_A.mp4 raw=5.04s trim_start=0.30 trim_end=4.50 audio=3.52 -> actual=3.92s",
            },
            "budget_spent_usd": 0.15,
            "budget_cap_usd": 0.30,
            "tests_pre_restart": "86/86 green",
            "blast_radius_clean": True,
            "beat_06_self_healed": True,
            "state_backup": "Production/Event_1/production_state.json.bak_activation_20260418T213824Z",
            "beat_10_lipsync_backup": "Production/Event_1/animation_clips/beat_10_lipsync.mp4.bak_activation_20260418T214127Z",
            "rule_refs": "CLAUDE.md Rule 7 Path B, Rule 18 (LD registration), Rule 19 (Hardened Session)",
            "timestamp": now,
        }),
    }
    try:
        r = client._request("POST", "/items/prod_activity_log", data=body)
        aid = r.get("data", {}).get("id")
        print(f"[directus] activation prod_activity_log id={aid}")
        return aid
    except DirectusError as exc:
        print(f"[directus] activation activity failed: {exc.status} {exc.detail[:300]}",
              file=sys.stderr)
        return None


if __name__ == "__main__":
    sys.exit(main())
