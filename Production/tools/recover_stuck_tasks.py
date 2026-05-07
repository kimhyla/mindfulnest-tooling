#!/usr/bin/env python3
"""
recover_stuck_tasks.py — Manual WaveSpeed task recovery for MindfulNest.

When `production_server.py` marks a task `failed` after retries exhausted but
WaveSpeed actually completed the task on its CDN, this tool pulls the output
from CDN and patches state to mark the option completed. Use when the built-in
pre-fail CDN re-check (PollingThread) didn't catch the recovery — typically
because the outage persisted through `MAX_RETRIES * (cycle + backoff)`.

Runs as a SEPARATE process from the server. State mutations are concurrency-safe
via StateManager's fcntl.lockf inter-process lock. The spend ledger
(spend_ledger.jsonl) prevents double-charge even if this tool runs simultaneously
with a regenerate.

USAGE:
    # Preview what would be recovered (no writes):
    python3 Production/tools/recover_stuck_tasks.py --event-dir Production/Event_1 --all-failed --dry-run

    # Recover a specific beat's failed options (SAFE — refuses if completed options exist
    # for that beat):
    python3 Production/tools/recover_stuck_tasks.py --event-dir Production/Event_1 --beat beat_03

    # Recover ALL failed options across all beats, skipping those already recovered
    # and those in beats that have completed-or-selected options:
    python3 Production/tools/recover_stuck_tasks.py --event-dir Production/Event_1 --all-failed

    # Override the winner-lock and force-recover a beat even if it has completed options
    # (destructive — will overwrite the existing beat_NN_option_M.mp4 file):
    python3 Production/tools/recover_stuck_tasks.py --event-dir Production/Event_1 --force-beat beat_03

SAFEGUARDS (counter-agent C3 CRITICAL findings, April 16 2026):
    1. Idempotency: skip any option where `recovered_from_cdn_at` is already set.
       Re-running the tool is a no-op on already-recovered entries.
    2. Winner-lock: `--all-failed` will NOT touch any beat that has a
       `selected_option` set. Use `--force-beat` to override.
    3. Spend ledger: StateManager.add_spend is task_id-keyed; double-charge is
       prevented even if recovery runs concurrently with normal poll completion.

RULE 18 (TWO-WRITE) COMPLIANCE:
    Each recovered option writes:
      (a) Filesystem — downloads MP4, audio-strip, patches production_state.json
      (b) Directus  — POST prod_activity_log with activity_type=recovery_cdn_pull
    If Directus is unreachable, the file write still happens (so Kim's work isn't
    blocked) but a warning is printed; a prod_activity_log replay can be done later
    via the runbook.
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

# Import server-side primitives (reuse, never duplicate — see Advocate #3 maintainability).
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from production_server import (  # noqa: E402
    StateManager,
    WaveSpeedClient,
    wavespeed_poll_url,
    _mark_completed,
    COST_PER_CLIP_KLING,
    _wavespeed_request,
)
from ffmpeg_utils import strip_audio as _strip_clip_audio  # noqa: E402


# -------------------------------------------------------------------------
# CDN fetch — query WaveSpeed predictions endpoint for ground truth
# -------------------------------------------------------------------------

def cdn_check(api_key: str, task_id: str, timeout: int = 15) -> dict:
    """Direct ground-truth query to WaveSpeed. Returns:
        {"status": "completed"|"failed"|"processing"|"unknown", "outputs": [url, ...]}
    Never raises — on network error returns status=unknown so caller can decide."""
    try:
        url = wavespeed_poll_url(task_id)
        status_code, body = _wavespeed_request(
            "GET", url, api_key=api_key, timeout=timeout,
        )
        if status_code < 200 or status_code >= 300:
            return {"status": "unknown", "outputs": [], "error": f"HTTP {status_code}"}
        payload = json.loads(body.decode("utf-8"))
        data = payload.get("data") or {}
        return {
            "status": (data.get("status") or payload.get("status") or "unknown").lower(),
            "outputs": data.get("outputs") or payload.get("outputs") or [],
        }
    except Exception as exc:  # noqa: BLE001
        return {"status": "unknown", "outputs": [], "error": str(exc)}


# -------------------------------------------------------------------------
# Directus activity-log (best-effort)
# -------------------------------------------------------------------------

def log_recovery_activity(
    event_id: str,
    beat_id: str,
    opt_idx: int,
    task_id: str,
    file_name: str,
    bytes_written: int,
    source: str,
) -> bool:
    """Fire POST to prod_activity_log. Returns True on success, False on any failure.
    Non-blocking: recovery proceeds even if Directus is unreachable."""
    try:
        sys.path.insert(0, str(SCRIPT_DIR / "lib"))
        from credentials import load_credentials  # type: ignore
        from directus import DirectusClient  # type: ignore
        creds = load_credentials()
        c = DirectusClient(
            creds["directus_url"], creds["directus_email"], creds["directus_password"]
        )
        # MUST authenticate explicitly — _request does not auto-auth.
        # (Adversarial review Phase 3 finding #2, April 16 2026.)
        c.authenticate()
        payload = {
            "activity_type": "recovery_cdn_pull",
            "module_id": event_id,
            "details": json.dumps({
                "beat_id": beat_id,
                "option_index": opt_idx + 1,
                "task_id": task_id,
                "file_name": file_name,
                "bytes_written": bytes_written,
                "source": source,
                "tool": "recover_stuck_tasks.py",
                "recovered_at": datetime.now(timezone.utc).isoformat(),
            }),
        }
        c._request("POST", "/items/prod_activity_log", data=payload)
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[directus] WARN recovery log failed (non-blocking): {exc}")
        return False


# -------------------------------------------------------------------------
# Target selection — which options to attempt recovery on
# -------------------------------------------------------------------------

def select_targets(
    state: dict,
    *,
    beat_filter: str | None,
    force_beat: str | None,
    all_failed: bool,
) -> list[tuple[str, int, dict, str]]:
    """Return list of (beat_id, opt_idx, opt_dict, policy) where policy indicates
    whether the beat passed the winner-lock safeguard.

    Safeguards applied:
      1. Skip options with `recovered_from_cdn_at` already set (idempotency).
      2. For --all-failed and --beat: skip beats with any selected_option set
         (winner-lock). Only --force-beat overrides this.
      3. Only consider options with status == "failed" AND task_id present.
    """
    targets: list[tuple[str, int, dict, str]] = []
    beats = state.get("beats", {})
    for bid, beat in beats.items():
        if beat_filter and bid != beat_filter and bid != force_beat:
            continue
        if force_beat and bid != force_beat:
            continue
        if not beat_filter and not force_beat and not all_failed:
            continue

        phase1 = beat.get("phase_1") or {}
        options = phase1.get("options", [])
        has_selected = phase1.get("selected_option") is not None
        has_any_completed = any(o.get("status") == "completed" for o in options)

        # Winner-lock: only --force-beat allows touching beats with completed options
        winner_locked = has_selected or has_any_completed
        if winner_locked and force_beat != bid:
            # Skip unless forced — print reason
            n_failed = sum(1 for o in options if o.get("status") == "failed")
            if n_failed > 0:
                print(f"[skip] {bid}: {n_failed} failed option(s) found but beat is winner-locked "
                      f"(selected={phase1.get('selected_option')} any_completed={has_any_completed}). "
                      f"Use --force-beat {bid} to override.")
            continue

        for idx, opt in enumerate(options):
            if opt.get("status") != "failed":
                continue
            if not opt.get("task_id"):
                continue
            if opt.get("recovered_from_cdn_at"):
                # Idempotency: already recovered in a prior run
                continue
            policy = "force" if force_beat == bid else "normal"
            targets.append((bid, idx, opt, policy))
    return targets


# -------------------------------------------------------------------------
# Main recovery operation
# -------------------------------------------------------------------------

def recover_one(
    sm: StateManager,
    client: WaveSpeedClient,
    event_id: str,
    beat_id: str,
    opt_idx: int,
    opt: dict,
    *,
    dry_run: bool,
) -> str:
    """Recover one option. Returns a status string describing the outcome."""
    task_id = opt["task_id"]
    print(f"\n[recover] {beat_id} option {opt_idx + 1} task={task_id[:16]}...")

    # Step 1: WaveSpeed ground-truth query
    check = cdn_check(client.api_key, task_id)
    print(f"  cdn_check: status={check['status']} outputs={len(check.get('outputs', []))}")
    if check["status"] != "completed" or not check.get("outputs"):
        if check["status"] == "unknown":
            return "ERROR_UNREACHABLE"
        return f"SKIP_STATUS_{check['status']}"
    cdn_url = check["outputs"][0]

    if dry_run:
        print(f"  [dry-run] would download {cdn_url} → clips/{beat_id}_option_{opt_idx + 1}.mp4")
        return "DRY_RUN_WOULD_RECOVER"

    # Step 2: Download MP4 (with idempotency — if file already exists, use it)
    fname = f"{beat_id}_option_{opt_idx + 1}.mp4"
    dest = sm.clips_dir / fname
    if dest.exists() and dest.stat().st_size > 0:
        size = dest.stat().st_size
        print(f"  [idempotent] file already exists ({size:,} bytes) — skipping download")
    else:
        try:
            size = client.download(cdn_url, dest)
            print(f"  downloaded: {size:,} bytes → {fname}")
        except Exception as exc:  # noqa: BLE001
            print(f"  [error] download failed: {exc}")
            return "ERROR_DOWNLOAD"

        # Step 3: Audio strip (same as normal poll completion)
        if _strip_clip_audio(dest, verbose=False):
            size = dest.stat().st_size
            print(f"  audio stripped: new size {size:,} bytes")

    # Step 4: Atomic state patch via fcntl-safe mutate
    def _patch(state, _bid=beat_id, _i=opt_idx, _tid=task_id, _f=fname, _sz=size):
        opts = state["beats"][_bid]["phase_1"]["options"]
        opt = opts[_i]
        opt["status"] = "completed"
        opt["file"] = _f
        opt["size_bytes"] = _sz
        opt["last_error"] = None
        opt["recovered_from_cdn_at"] = datetime.now(timezone.utc).isoformat()
        # Also keep the canonical completion fields that _mark_completed writes
        _mark_completed(state, _bid, _i, _f, _sz)
        return None
    sm.mutate_state(_patch)
    print(f"  state patched — option marked completed")

    # Step 5: Spend — task_id-keyed ledger prevents double-charge
    sm.add_spend("kling_animation", COST_PER_CLIP_KLING, task_id=task_id)
    print(f"  spend logged (task_id={task_id[:16]}, ledger idempotent)")

    # Step 6: Directus audit trail (Rule 18 — best-effort)
    log_recovery_activity(
        event_id, beat_id, opt_idx, task_id, fname, size, source="recover_stuck_tasks.py",
    )

    return "RECOVERED"


def main() -> int:
    p = argparse.ArgumentParser(
        description="Recover WaveSpeed tasks that completed on CDN but were marked failed locally.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--event-dir", required=True, type=Path,
                   help="Path to event dir (contains production_state.json)")
    p.add_argument("--event-id", default=None,
                   help="Event ID for activity log (default: read from state file)")
    # Target-selection flags are mutually exclusive (Phase 3 review fix #7)
    target = p.add_mutually_exclusive_group(required=True)
    target.add_argument("--beat", default=None,
                        help="Single beat to target (safeguards apply)")
    target.add_argument("--force-beat", default=None,
                        help="Force-recover a beat's failed options EVEN IF the beat has completed "
                             "or selected options (destructive — requires explicit intent)")
    target.add_argument("--all-failed", action="store_true",
                        help="Target all failed options in non-winner-locked beats")
    p.add_argument("--dry-run", action="store_true",
                   help="Print what would be done without writing anything")
    p.add_argument("--yes", action="store_true",
                   help="Skip per-beat confirmation prompt")
    args = p.parse_args()

    event_dir: Path = args.event_dir
    if not event_dir.exists():
        print(f"[error] event_dir does not exist: {event_dir}")
        return 1
    state_path = event_dir / "production_state.json"
    if not state_path.exists():
        print(f"[error] production_state.json not found at {state_path}")
        return 1

    # Load API key
    sys.path.insert(0, str(SCRIPT_DIR / "lib"))
    try:
        from credentials import load_credentials  # type: ignore
        creds = load_credentials()
        api_key = creds.get("wavespeed_key") or creds.get("wavespeed_api_key")
        if not api_key:
            print("[error] wavespeed_api_key missing from credentials")
            return 1
    except Exception as exc:
        print(f"[error] cannot load credentials: {exc}")
        return 1

    # Read state (fcntl-safe)
    event_id = args.event_id
    if event_id is None:
        event_id = json.loads(state_path.read_text()).get("event_id", "unknown")

    sm = StateManager(event_dir, event_id)
    client = WaveSpeedClient(api_key)
    state = sm.read_state()

    targets = select_targets(
        state,
        beat_filter=args.beat,
        force_beat=args.force_beat,
        all_failed=args.all_failed,
    )

    if not targets:
        print("[ok] no failed options meet recovery criteria (nothing to do).")
        return 0

    print(f"\n=== Recovery plan: {len(targets)} option(s) ===")
    for bid, idx, opt, policy in targets:
        tid = opt.get("task_id", "")
        print(f"  {bid} opt {idx + 1}  task={tid[:16]}  policy={policy}  last_error={opt.get('last_error','')[:60]}")

    if not args.yes and not args.dry_run:
        try:
            ans = input("\nProceed? [y/N]: ").strip().lower()
        except EOFError:
            ans = ""
        if ans != "y":
            print("[abort] no changes made.")
            return 1

    # Execute
    outcomes = {}
    for bid, idx, opt, _policy in targets:
        outcome = recover_one(
            sm, client, event_id, bid, idx, opt, dry_run=args.dry_run,
        )
        outcomes[f"{bid}/opt{idx + 1}"] = outcome

    print("\n=== Summary ===")
    for key, outcome in outcomes.items():
        print(f"  {key}: {outcome}")
    n_recovered = sum(1 for v in outcomes.values() if v == "RECOVERED")
    n_dry = sum(1 for v in outcomes.values() if v == "DRY_RUN_WOULD_RECOVER")
    n_skip = sum(1 for v in outcomes.values() if v.startswith("SKIP"))
    n_err = sum(1 for v in outcomes.values() if v.startswith("ERROR"))
    print(f"\nrecovered={n_recovered}  dry_run_planned={n_dry}  skipped={n_skip}  errors={n_err}")
    return 0 if n_err == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
