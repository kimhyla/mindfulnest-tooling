#!/usr/bin/env python3
"""Directus registration for LIPSYNC_TRIM_WINDOW_HONORED_20260419.

One-shot script staged by the autonomous overnight run because Claude's
permission system denied the External-System-Write during autonomous mode.
Kim (or a later session with explicit authorization) runs this to register:

  1. prod_preflight_reviews row (routine+, parent_preflight_id=68)
  2. prod_locked_decisions row (LIPSYNC_TRIM_WINDOW_HONORED_20260419, MEDIUM)
  3. prod_activity_log companion row

Uses the canonical credential loader (urllib, never curl — CLAUDE.md Rule 18
+ handoff Phase 4 constraint). Safe to re-run — duplicate decision_key
collides with UNIQUE constraint, and Directus returns a 400 that this
script logs and exits 0 for idempotency.

Run from project root:

    cd "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files"
    python3 Production/scripts/register_lipsync_trim_fix_20260419.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add Production/tools/lib to sys.path so we can use the canonical client.
_HERE = Path(__file__).resolve().parent
_TOOLS_LIB = _HERE.parent / "tools" / "lib"
sys.path.insert(0, str(_TOOLS_LIB))

from credentials import load_credentials  # type: ignore
from directus import DirectusClient, DirectusError  # type: ignore


TASK_ID = "lipsync-trim-window-fix-20260419"
DECISION_KEY = "LIPSYNC_TRIM_WINDOW_HONORED_20260419"


SYNTHESIS = (
    "4-agent Phase 0 (2 advocates + 2 counters) per routine+ classification. "
    "Advocate A designed _trim_video_to_audio signature change (keyword-only "
    "kwargs with defaults matching old behavior), caller update in "
    "_handle_lipsync_submit, and retry state reset in init_lipsync. "
    "Advocate B enumerated edge cases: trim_start unset / trim_end null / "
    "both unset / window < audio / window > clip / float precision / first-time "
    "vs retry / ffmpeg input-side seek correctness. "
    "Counter 1 read production_state.json and confirmed beats 09 "
    "(trim_start=1.4) and 10 (trim_start=0.3) currently have completed "
    "lipsyncs generated under the old 'trim from 0' behavior — hitting Retry "
    "post-fix WILL produce different output than the on-disk file. This is "
    "INTENDED (prior silent-ignore was the bug; Kim set those trim values "
    "expecting them to apply). Counter 2 argued for minimum-viable scope "
    "(ship primary bug only, defer retry reset); overridden per handoff's "
    "explicit 'bundle both' directive + Counter 1 evidence that retry is the "
    "user-visible vector. "
    "Ship decision: bundle primary (trim honor) + secondary (retry state "
    "reset). Reject as scope creep: tailroom bump 0.4->0.6, CAS poller check, "
    "startup warnings for beats 09/10 — documented as follow-ups in "
    "LIPSYNC_TRIM_FIX_COMPLETE_20260419.md. "
    "Phase 3 counter-review: 10/10 PASS. Tests: 86/86 green (78 existing + 8 new)."
)


DECISION_TEXT = (
    "Lipsync pipeline honors phase_1.trim_start and phase_1.trim_end when "
    "trimming source video for ByteDance LipSync submission.\n\n"
    "Signature: _trim_video_to_audio(source, dst, audio_dur, *, "
    "trim_start=0.0, trim_end=None) -> (dst, actual, ts_used, te_used). "
    "Passes ffmpeg `-ss <trim_start>` BEFORE `-i` (input-side seek — "
    "frame-accurate because `-c:v libx264 -preset fast -crf 18` re-encodes "
    "every frame; switching to `-c copy` would break this invariant).\n\n"
    "Duration formula: actual = min(audio_duration + 0.4s tailroom, "
    "trim_end - trim_start, raw_dur - trim_start).\n\n"
    "Backward compat: omitting trim kwargs reproduces the old 'trim from "
    "frame 0' behavior (effective_end collapses to raw_dur). Verified: "
    "raw_dur=10 audio=5.2 -> old actual=5.6; new with defaults=5.6.\n\n"
    "Fail-loud HTTP 400 conditions:\n"
    "  - trim_start >= raw_dur (clip shorter than seek point)\n"
    "  - trim_end <= trim_start (zero/inverted window)\n"
    "  - audio + 0.4s tailroom > (trim_end - trim_start) (window too small "
    "for audio — response body includes audio_duration_s, tailroom_s, "
    "needed_s, trim_window_s, trim_start, trim_end, and a 'hint' field).\n"
    "trim_end > raw_dur + 0.05 is silently clamped with a WARN log "
    "(accommodates UI rounding).\n\n"
    "Retry state reset: when init_lipsync finds existing beat.lipsync dict "
    "with status in {submitting, polling, failed, completed}, it clears "
    "task_id, submitted_at, submitted_at_epoch; increments retries; appends "
    "prior task_id to superseded_task_ids[] (dedup'd) for audit. First-time "
    "submissions (lipsync missing or None) preserve retries=0 and do not "
    "touch stale fields.\n\n"
    "EXPECTED BEHAVIOR CHANGE: beats currently on disk with completed "
    "lipsync AND non-zero phase_1.trim_start will produce DIFFERENT lipsync "
    "output on retry vs the file on disk. As of 2026-04-18, affected beats "
    "are beat_09 (trim_start=1.4) and beat_10 (trim_start=0.3). The prior "
    "behavior silently ignored Kim's trim values; this fix honors them."
)


def main() -> int:
    creds = load_credentials()
    client = DirectusClient(
        creds["directus_url"], creds["directus_email"], creds["directus_password"],
    )
    client.authenticate()
    print("[directus] authenticated")

    now = datetime.now(timezone.utc).isoformat()

    # Step gates — 2026-04-19 initial run registered decision=276 and
    # activity=457 successfully; preflight failed on missing task_type.
    # Gate env vars let Kim re-run ONLY the steps that failed without
    # creating duplicates. Defaults preserve the original all-three flow.
    do_preflight = os.environ.get("SKIP_PREFLIGHT") != "1"
    do_decision = os.environ.get("SKIP_DECISION") != "1"
    do_activity = os.environ.get("SKIP_ACTIVITY") != "1"

    # 1) prod_preflight_reviews
    preflight_id = _register_preflight(client, now) if do_preflight else None
    if not do_preflight:
        print("[directus] prod_preflight_reviews: SKIPPED per SKIP_PREFLIGHT=1")

    # 2) prod_locked_decisions
    if do_decision:
        decision_id = _register_decision(client, now)
    else:
        decision_id = os.environ.get("EXISTING_DECISION_ID", "skipped")
        print(f"[directus] prod_locked_decisions: SKIPPED "
              f"(use EXISTING_DECISION_ID={decision_id})")

    # 3) prod_activity_log companion
    if do_activity:
        activity_id = _register_activity(client, now, preflight_id, decision_id)
    else:
        activity_id = os.environ.get("EXISTING_ACTIVITY_ID", "skipped")
        print(f"[directus] prod_activity_log: SKIPPED "
              f"(use EXISTING_ACTIVITY_ID={activity_id})")

    print(json.dumps({
        "task_id": TASK_ID,
        "decision_key": DECISION_KEY,
        "preflight_id": preflight_id,
        "decision_id": decision_id,
        "activity_id": activity_id,
    }, indent=2))
    return 0


def _register_preflight(client, now):
    # Schema requires `task_type` (confirmed 2026-04-19 run: 400 Validation
    # failed for field "task_type". Value is required.). Read from env or
    # default to a conservative value; Kim can override via:
    #   PREFLIGHT_TASK_TYPE=<value> python3 Production/scripts/register_...py
    task_type = os.environ.get("PREFLIGHT_TASK_TYPE", "bugfix")
    task_description = os.environ.get(
        "PREFLIGHT_TASK_DESCRIPTION",
        "Fix lipsync pipeline so that _trim_video_to_audio honors "
        "phase_1.trim_start and phase_1.trim_end set by the storyboard UI, "
        "plus reset stale task_id / submitted_at / submitted_at_epoch on "
        "retry (with superseded_task_ids[] audit trail). Bundle both bugs "
        "per handoff. Fail-loud HTTP 400 when audio + 0.4s tailroom exceeds "
        "trim window. Backward-compat via keyword-only defaults. "
        "86/86 tests green (78 existing + 8 new).",
    )
    body = {
        "task_id": TASK_ID,
        "task_type": task_type,
        "task_description": task_description,
        "classification": "routine+",
        "advocates_count": 2,
        "counters_count": 2,
        "parent_preflight_id": 68,
        "approved_to_proceed": True,
        "claude_summary": SYNTHESIS,
        "date_reviewed": now,
    }
    try:
        r = client._request("POST", "/items/prod_preflight_reviews", data=body)
        pid = r.get("data", {}).get("id")
        print(f"[directus] prod_preflight_reviews id={pid}")
        return pid
    except DirectusError as exc:
        print(f"[directus] preflight full-body failed: {exc.status} {exc.detail[:300]}",
              file=sys.stderr)
        # Fallback to minimal payload if schema differs
        minimal = {
            "task_id": TASK_ID,
            "task_type": task_type,
            "task_description": task_description,
            "classification": "routine+",
            "claude_summary": SYNTHESIS,
        }
        try:
            r = client._request("POST", "/items/prod_preflight_reviews", data=minimal)
            pid = r.get("data", {}).get("id")
            print(f"[directus] prod_preflight_reviews (minimal) id={pid}")
            return pid
        except DirectusError as e2:
            print(f"[directus] minimal preflight also failed: {e2.detail[:300]}",
                  file=sys.stderr)
            return None


def _register_decision(client, now):
    body = {
        "decision_key": DECISION_KEY,
        "decision_name": "Lipsync honors storyboard trim window",
        "decision_text": DECISION_TEXT,
        "source_document": "Production/tools/production_server.py::_handle_lipsync_submit + _trim_video_to_audio",
        "task_category": "production_server",
        "severity": "MEDIUM",
        "date_locked": now,
        "status": "active",
    }
    try:
        r = client._request("POST", "/items/prod_locked_decisions", data=body)
        did = r.get("data", {}).get("id")
        print(f"[directus] prod_locked_decisions id={did} key={DECISION_KEY}")
        return did
    except DirectusError as exc:
        msg = (exc.detail or "").lower()
        if "duplicate" in msg or "unique" in msg or exc.status == 400:
            print(f"[directus] decision already registered (idempotent skip): "
                  f"{exc.detail[:200]}")
            return "already_registered"
        print(f"[directus] decision failed: {exc.status} {exc.detail[:300]}",
              file=sys.stderr)
        raise


def _register_activity(client, now, preflight_id, decision_id):
    body = {
        "action": "lipsync_trim_window_fix_shipped",
        "module_id": 1,
        "performed_by": "claude_autonomous_overnight",
        "details": json.dumps({
            "task_id": TASK_ID,
            "decision_key": DECISION_KEY,
            "preflight_id": preflight_id,
            "decision_id": decision_id,
            "files_modified": [
                "Production/tools/production_server.py",
                "Production/tools/tests/test_lipsync_trim_window.py",
            ],
            "backup": "Production/tools/production_server.py.bak_lipsync_trim_20260418_210002",
            "tests": "86/86 green (78 existing + 8 new)",
            "beats_affected_on_retry": ["beat_09", "beat_10"],
            "rule_refs": "CLAUDE.md Rule 7 Path B, Rule 18 (LD registration), Rule 19 (Hardened Session)",
            "timestamp": now,
        }),
    }
    try:
        r = client._request("POST", "/items/prod_activity_log", data=body)
        aid = r.get("data", {}).get("id")
        print(f"[directus] prod_activity_log id={aid}")
        return aid
    except DirectusError as exc:
        print(f"[directus] activity failed: {exc.status} {exc.detail[:300]}",
              file=sys.stderr)
        return None


if __name__ == "__main__":
    sys.exit(main())
