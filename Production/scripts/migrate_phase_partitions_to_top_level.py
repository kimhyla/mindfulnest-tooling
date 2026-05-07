#!/usr/bin/env python3
"""
Migrate Production/Event_*/production_state.json from v2 (partitioned with
phase_a/b inside `state.videos`) to v3 (phase_a/b lifted to top-level;
videos.win renamed to videos.resolution).

Per STORYBOARD_V59_PHASE_AB_REVISION_SPEC_v3.md §3.1 + §4 Phase A.

Source-of-truth facts this script enforces:
  - Pre-state shape: state.version == "v2", state.videos has subset of
    {intro, phase_a, phase_b, win}.
  - Post-state shape: state.version == "v3", state.videos has only
    {intro, resolution} (subset; some events may have only intro);
    state.phase_a + state.phase_b live at top level when present;
    each multi-beat partition has completed_mp4_path: null.
  - is_already_migrated() strict 7-field invariant: all 7 conditions must
    hold (per Cursor v6 Q2 / spec Phase A.2).
  - Drain integration (--apply): POST /api/admin/drain_start;
    GET /api/admin/inflight_count; ABORT if non-empty; 60s sync residue
    poll; snapshot; apply; drain_end. Per Decision 4 = Option A.

Modes:
    --dry-run   Print proposed migration per file. No writes. Exit 0 on
                clean dry-run; non-zero on schema violation or collision.
    --apply     Apply with drain + snapshot + atomic write. Calls server
                /api/admin/drain_start, /api/admin/inflight_count,
                /api/admin/drain_end (per v3 §3.7 + Phase C0).
    --validate  Verify all event state.json files are at version=v3 with
                top-level phase_a/b (when applicable) and videos has
                {intro, resolution} only. Exit 0 if all migrated.

Snapshot location:
    Production/Event_<N>/.backups/state/<UTC_TS>_pre_phase_revision.json
    sha256 logged to stdout.

Cursor v6 Q2 strict invariant (is_already_migrated must hold ALL 7):
    1. state["version"] == "v3"
    2. "resolution" in state["videos"]
    3. "win" not in state["videos"]
    4. "phase_a" not in state["videos"]
    5. "phase_b" not in state["videos"]
    6. top-level state["phase_a"] exists OR explicitly absent (NOT both)
    7. top-level state["phase_b"] exists OR explicitly absent (NOT both)

Reference: STORYBOARD_V59_PHASE_AB_REVISION_SPEC_v3.md §3.1, §4.A.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_DIR = PROJECT_ROOT / "Production"
SERVER_BASE = os.environ.get("MN_SERVER", "http://127.0.0.1:5111")

# Multi-beat roles in v3 schema
MULTI_BEAT_ROLES_V3 = ("intro", "resolution", "standalone")

# Phase scalar fields (lift targets)
PHASE_A_SCALARS = (
    "phase_a_script",
    "phase_a_voice_stem_file", "phase_a_voice_stem_mtime",
    "phase_a_lipsync_file", "phase_a_lipsync_mtime",
    "phase_a_empty_desk_bg_id",
    "phase_a_chipper_flyin_clip_id", "phase_a_chipper_sitting_clip_id", "phase_a_chipper_flyout_clip_id",
    "phase_a_mixed_audio_file", "phase_a_mixed_audio_mtime",
    "phase_a_ambient_preset_id",
    "phase_a_watercolor_cues_json",
    "phase_a_stitched_file", "phase_a_stitched_mtime",
    "phase_a_status",
)

PHASE_B_SCALARS = (
    "phase_b_script",
    "phase_b_voice_stem_file", "phase_b_voice_stem_mtime",
    "phase_b_ambient_preset_id",
    "phase_b_mixed_audio_file", "phase_b_mixed_audio_mtime",
    "phase_b_cedric_base_clip_id",
    "phase_b_lipsync_file", "phase_b_lipsync_mtime",
    "phase_b_watercolor_cues_json",
    "phase_b_preview_file",
    "phase_b_status",
)


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _utc_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def find_event_state_files() -> List[Path]:
    if not PRODUCTION_DIR.exists():
        return []
    out = []
    for d in sorted(PRODUCTION_DIR.iterdir()):
        if d.is_dir() and d.name.startswith("Event_"):
            sf = d / "production_state.json"
            if sf.exists():
                out.append(sf)
    return out


def is_already_migrated(state: dict) -> Tuple[bool, str]:
    """Cursor v6 Q2 strict 7-field invariant.

    Returns (True, '') if FULLY migrated to v3.
    Returns (False, reason) if NOT migrated. Mixed-version state returns False
    with explicit mismatch reason for fail-closed handling at caller.
    """
    if state.get("version") != "v3":
        return (False, f"version is {state.get('version')!r}, want 'v3'")
    videos = state.get("videos") or {}
    if "resolution" not in videos:
        return (False, "videos.resolution missing")
    if "win" in videos:
        return (False, "videos.win still present (must be renamed to resolution)")
    if "phase_a" in videos:
        return (False, "videos.phase_a still present (must be lifted to top level)")
    if "phase_b" in videos:
        return (False, "videos.phase_b still present (must be lifted to top level)")
    # phase_a top-level: present is fine (lifted), absent is fine (event never had one)
    # but "absent at top AND present in videos" was already checked above
    return (True, "")


def is_pristine_v2(state: dict) -> Tuple[bool, str]:
    """True if state matches the expected v2 source shape."""
    if state.get("version") != "v2":
        return (False, f"version is {state.get('version')!r}, want 'v2'")
    videos = state.get("videos") or {}
    if "intro" not in videos and "win" not in videos:
        return (False, "neither videos.intro nor videos.win present")
    # Top-level phase_a/b should NOT exist in v2 (would indicate prior partial migration)
    if "phase_a" in state:
        return (False, "top-level phase_a already present in v2 state (pre-migrated mid-state?)")
    if "phase_b" in state:
        return (False, "top-level phase_b already present in v2 state (pre-migrated mid-state?)")
    return (True, "")


def detect_collisions(state: dict) -> List[str]:
    """If we're about to LIFT a key from videos.phase_a to top-level state.phase_a
    and that key already exists at top-level with different value, abort.

    For v3 migration, the lift target is the WHOLE phase_a/phase_b dict (not
    individual scalars), so collision check is: top-level phase_a/phase_b
    already present AND not equal to videos.phase_a/phase_b.
    """
    issues = []
    videos = state.get("videos") or {}
    for phase_key in ("phase_a", "phase_b"):
        if phase_key in state and phase_key in videos:
            top_val = state.get(phase_key)
            videos_val = videos.get(phase_key)
            if top_val != videos_val:
                issues.append(
                    f"top-level state.{phase_key} differs from videos.{phase_key} "
                    f"(top has {len(top_val) if isinstance(top_val, dict) else 'non-dict'} keys; "
                    f"videos has {len(videos_val) if isinstance(videos_val, dict) else 'non-dict'} keys)"
                )
    return issues


def _strip_phase_role_meta(phase_dict: dict) -> dict:
    """Remove video_role + video_label markers when lifting phase to top-level.
    They were partition-membership markers; top-level form doesn't need them."""
    out = dict(phase_dict)
    out.pop("video_role", None)
    out.pop("video_label", None)
    return out


def migrate_state(state: dict) -> Tuple[dict, List[str]]:
    """Apply v2 → v3 transformation in memory. Returns (new_state, change_log).

    Idempotent: returns input unchanged + empty log if already migrated.
    """
    log = []
    out = json.loads(json.dumps(state))  # deep copy

    # Idempotency check first
    done, _ = is_already_migrated(out)
    if done:
        return (out, ["already_v3 — no changes"])

    # Bump version
    out["version"] = "v3"
    log.append("version v2 -> v3")

    videos = out.setdefault("videos", {})

    # Lift phase_a
    if "phase_a" in videos:
        phase_a = videos.pop("phase_a")
        phase_a_clean = _strip_phase_role_meta(phase_a)
        if "phase_a" in out and out["phase_a"] != phase_a_clean:
            # Should have been caught by detect_collisions; defensive belt-and-suspenders.
            raise RuntimeError(
                f"COLLISION during lift: top-level state.phase_a already differs "
                f"from videos.phase_a. Aborted. Inspect state file manually."
            )
        out["phase_a"] = phase_a_clean
        log.append(f"lifted videos.phase_a -> state.phase_a ({len(phase_a_clean)} keys)")

    # Lift phase_b
    if "phase_b" in videos:
        phase_b = videos.pop("phase_b")
        phase_b_clean = _strip_phase_role_meta(phase_b)
        if "phase_b" in out and out["phase_b"] != phase_b_clean:
            raise RuntimeError(
                f"COLLISION during lift: top-level state.phase_b already differs "
                f"from videos.phase_b."
            )
        out["phase_b"] = phase_b_clean
        log.append(f"lifted videos.phase_b -> state.phase_b ({len(phase_b_clean)} keys)")

    # Rename videos.win -> videos.resolution
    if "win" in videos:
        if "resolution" in videos and videos["resolution"] != videos["win"]:
            raise RuntimeError(
                "COLLISION: videos.resolution already exists and differs from videos.win. "
                "Cannot safely rename. Manual reconciliation required."
            )
        videos["resolution"] = videos.pop("win")
        # Update video_role within partition body
        if isinstance(videos["resolution"], dict):
            videos["resolution"]["video_role"] = "resolution"
        log.append("renamed videos.win -> videos.resolution (and updated inner video_role)")

    # Add completed_mp4_path: null to each multi-beat partition (idempotent)
    for role in ("intro", "resolution"):
        part = videos.get(role)
        if isinstance(part, dict) and "completed_mp4_path" not in part:
            part["completed_mp4_path"] = None
            log.append(f"seeded videos.{role}.completed_mp4_path = null")

    # Active_video coercion: if it pointed to "win", point to "resolution"
    if out.get("active_video") == "win":
        out["active_video"] = "resolution"
        log.append("coerced active_video: 'win' -> 'resolution'")

    # Update updated_at
    out["updated_at"] = _utc_iso()

    return (out, log)


# ── Drain protocol ──────────────────────────────────────────────────────────

def _http_get(path: str, timeout: float = 5.0) -> Tuple[int, dict]:
    url = SERVER_BASE.rstrip("/") + path
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
        try:
            return (resp.status, json.loads(body.decode("utf-8")))
        except json.JSONDecodeError:
            return (resp.status, {"raw": body.decode("utf-8", errors="replace")})


def _http_post(path: str, payload: Optional[dict] = None, timeout: float = 5.0) -> Tuple[int, dict]:
    url = SERVER_BASE.rstrip("/") + path
    data = json.dumps(payload or {}).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST",
                                  headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
        try:
            return (resp.status, json.loads(body.decode("utf-8")))
        except json.JSONDecodeError:
            return (resp.status, {"raw": body.decode("utf-8", errors="replace")})


def _format_inflight_summary(active: dict) -> str:
    lines = []
    for cls in ("gpt", "magic", "assemble", "lipsync", "sync"):
        for j in active.get(cls, []):
            name = j.get("name") if isinstance(j, dict) else str(j)
            extra = ""
            if isinstance(j, dict) and j.get("progress"):
                extra = f" ({j['progress']})"
            lines.append(f"  [{cls}] {name}{extra}")
    return "\n".join(lines) if lines else "  (none)"


def drain_then_apply(do_apply_func) -> int:
    """Per v3 §3.7 + Phase C0 + Decision 4 = Option A.

    Returns 0 on clean apply; non-zero on abort/timeout. NEVER applies
    when inflight_count > 0 at drain_start (no auto-timeout for
    thread-tracked jobs).
    """
    print(f"[drain] POST {SERVER_BASE}/api/admin/drain_start ...")
    try:
        st, body = _http_post("/api/admin/drain_start")
    except (urllib.error.URLError, ConnectionError) as e:
        print(f"[drain] FAIL: server unreachable at {SERVER_BASE}: {e}")
        print("        Is production_server.py running on the expected port?")
        return 2
    if st != 200:
        print(f"[drain] FAIL: drain_start returned HTTP {st}: {body}")
        return 2

    # Pre-flight enumeration
    try:
        st2, body2 = _http_get("/api/admin/inflight_count")
    except Exception as e:
        print(f"[drain] FAIL: inflight_count request failed: {e}")
        _http_post("/api/admin/drain_end")  # best-effort re-open
        return 2
    if st2 != 200:
        print(f"[drain] FAIL: inflight_count returned HTTP {st2}: {body2}")
        _http_post("/api/admin/drain_end")
        return 2

    inflight = body2.get("inflight_count", 0)
    if inflight > 0:
        active = body2.get("active_jobs") or {}
        print(f"[drain] ABORT: in-flight jobs detected (count={inflight})")
        print(_format_inflight_summary(active))
        print("[drain] Wait for jobs to complete or cancel them, then retry.")
        try:
            _http_post("/api/admin/drain_end")
        except Exception:
            pass
        return 3

    # 60s sync residue poll (fail-closed)
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            st3, body3 = _http_get("/api/admin/inflight_count")
        except Exception:
            time.sleep(1.0)
            continue
        if body3.get("inflight_count", 0) == 0:
            break
        time.sleep(1.0)
    else:
        try:
            st_final, body_final = _http_get("/api/admin/inflight_count")
            active = body_final.get("active_jobs") or {}
        except Exception:
            active = {}
        print(f"[drain] FAIL (60s timeout): sync residue still in-flight")
        print(_format_inflight_summary(active))
        try:
            _http_post("/api/admin/drain_end")
        except Exception:
            pass
        return 4

    # Apply
    print("[drain] inflight_count=0; proceeding with migration apply ...")
    try:
        rc = do_apply_func()
    finally:
        try:
            _http_post("/api/admin/drain_end")
            print("[drain] drain_end posted; server resumed accepting jobs")
        except Exception as e:
            print(f"[drain] WARNING: drain_end failed: {e} — manual retry needed")
    return rc


# ── Modes ───────────────────────────────────────────────────────────────────

def cmd_dry_run(only_event: Optional[str]) -> int:
    files = find_event_state_files()
    if only_event:
        files = [f for f in files if f.parent.name == only_event]
        if not files:
            print(f"FAIL: no Event_*/production_state.json matched --event {only_event}")
            return 1

    overall_rc = 0
    for sf in files:
        print(f"\n--- {sf.relative_to(PROJECT_ROOT)} ---")
        try:
            with sf.open("rb") as f:
                raw = f.read()
            state = json.loads(raw.decode("utf-8"))
        except Exception as e:
            print(f"  FAIL: read/parse error: {e}")
            overall_rc = 1
            continue

        # Check pre-state validity
        already, reason_done = is_already_migrated(state)
        if already:
            print(f"  ALREADY v3 — would be no-op")
            continue

        pristine, reason_pristine = is_pristine_v2(state)
        if not pristine:
            # Not v3 AND not pristine v2 — half-state. Fail closed.
            print(f"  FAIL (half-state / mixed): {reason_pristine}")
            print(f"        also not yet v3: {reason_done}")
            overall_rc = 1
            continue

        # Check collisions
        cols = detect_collisions(state)
        if cols:
            print(f"  FAIL (collision):")
            for c in cols:
                print(f"    - {c}")
            overall_rc = 1
            continue

        # Run migration in memory
        try:
            new_state, log = migrate_state(state)
        except RuntimeError as e:
            print(f"  FAIL (migration runtime): {e}")
            overall_rc = 1
            continue

        for line in log:
            print(f"  • {line}")

        # Verify post-state
        done2, _ = is_already_migrated(new_state)
        if not done2:
            print(f"  FAIL: post-migration state failed strict invariant")
            overall_rc = 1
            continue

        # Top-level phase_a/b sanity
        for pk in ("phase_a", "phase_b"):
            if pk in new_state:
                print(f"  -> top-level {pk}: {len(new_state[pk])} keys")

        # Multi-beat partitions
        new_videos = new_state.get("videos") or {}
        print(f"  -> videos keys after: {sorted(new_videos.keys())}")
    if overall_rc == 0:
        print("\n=== DRY-RUN PASS — all events would migrate cleanly ===")
    else:
        print("\n=== DRY-RUN FAIL — see issues above ===")
    return overall_rc


def cmd_apply(only_event: Optional[str], skip_drain: bool = False) -> int:
    """Snapshot + atomic write for each event state file. Wrapped in drain
    protocol unless --skip-drain (only allowed when server is not running)."""

    def _do_apply() -> int:
        files = find_event_state_files()
        if only_event:
            files = [f for f in files if f.parent.name == only_event]
            if not files:
                print(f"FAIL: no Event_*/production_state.json matched --event {only_event}")
                return 1

        # Phase 1: pre-flight on ALL files. Abort if ANY would fail.
        proposals: List[Tuple[Path, dict, dict, List[str]]] = []
        for sf in files:
            with sf.open("rb") as f:
                raw = f.read()
            state = json.loads(raw.decode("utf-8"))
            already, _ = is_already_migrated(state)
            if already:
                print(f"  SKIP (already v3): {sf.relative_to(PROJECT_ROOT)}")
                continue
            pristine, reason = is_pristine_v2(state)
            if not pristine:
                print(f"FAIL (mid-state): {sf.relative_to(PROJECT_ROOT)}: {reason}")
                return 1
            cols = detect_collisions(state)
            if cols:
                print(f"FAIL (collision): {sf.relative_to(PROJECT_ROOT)}:")
                for c in cols:
                    print(f"  - {c}")
                return 1
            try:
                new_state, log = migrate_state(state)
            except RuntimeError as e:
                print(f"FAIL (migration): {sf.relative_to(PROJECT_ROOT)}: {e}")
                return 1
            proposals.append((sf, state, new_state, log))

        if not proposals:
            print("Nothing to migrate — all events already at v3.")
            return 0

        # Phase 2: snapshot + write each
        ts = _utc_ts()
        for sf, old_state, new_state, log in proposals:
            event_dir = sf.parent
            backup_dir = event_dir / ".backups" / "state"
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup_path = backup_dir / f"{ts}_pre_phase_revision.json"

            # Snapshot
            snap_bytes = json.dumps(old_state, indent=2, sort_keys=False).encode("utf-8")
            backup_path.write_bytes(snap_bytes)
            snap_sha = _sha256_bytes(snap_bytes)
            print(f"  SNAPSHOT: {backup_path.relative_to(PROJECT_ROOT)} sha256={snap_sha}")

            # Atomic write
            new_bytes = json.dumps(new_state, indent=2, sort_keys=False).encode("utf-8")
            tmp_path = sf.with_suffix(sf.suffix + ".tmp")
            tmp_path.write_bytes(new_bytes)
            os.replace(tmp_path, sf)
            print(f"  WROTE: {sf.relative_to(PROJECT_ROOT)} ({len(log)} ops)")
            for line in log:
                print(f"    • {line}")

        return 0

    if skip_drain:
        print("[apply] --skip-drain set; bypassing drain protocol.")
        print("[apply]   Use ONLY when production_server.py is not running.")
        return _do_apply()
    return drain_then_apply(_do_apply)


def cmd_validate(only_event: Optional[str]) -> int:
    files = find_event_state_files()
    if only_event:
        files = [f for f in files if f.parent.name == only_event]
    rc = 0
    for sf in files:
        try:
            state = json.loads(sf.read_bytes().decode("utf-8"))
        except Exception as e:
            print(f"FAIL parse: {sf.relative_to(PROJECT_ROOT)}: {e}")
            rc = 1
            continue
        ok, reason = is_already_migrated(state)
        rel = sf.relative_to(PROJECT_ROOT)
        if ok:
            print(f"OK v3: {rel}")
        else:
            print(f"FAIL: {rel}: {reason}")
            rc = 1
    return rc


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    g.add_argument("--validate", action="store_true")
    p.add_argument("--event", default=None, help="Restrict to Event_<N> dir name")
    p.add_argument("--skip-drain", action="store_true",
                   help="In --apply mode, bypass drain protocol (server must not be running)")
    args = p.parse_args(argv)

    if args.dry_run:
        return cmd_dry_run(args.event)
    if args.apply:
        return cmd_apply(args.event, skip_drain=args.skip_drain)
    if args.validate:
        return cmd_validate(args.event)
    return 1


if __name__ == "__main__":
    sys.exit(main())
