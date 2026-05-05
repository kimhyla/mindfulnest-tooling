#!/usr/bin/env python3
"""C2c — Clean orphan beats from production_state.json + milestone state.json
per HARD LD `DISPLAY_ORDER_STRICT_V1`.

The contract: when `videos.<role>.display_order` is a present LIST, any
`beats[bid]` whose bid is NOT in the list is an orphan and gets dropped.
Pairs with the C2a renderer fix (Array.isArray gate) and C2b server prune
in `mutate_video_state`. This script is the bulk cleanup pass over
already-existing on-disk state files; the C2b prune handles the
forward-looking case (every future mutation maintains the invariant).

USAGE
    python3 clean_orphan_beats_v3.py [--apply] [--event <event_id>]
                                     [--milestone <milestone_id>] [--all]

DEFAULT: dry-run; prints orphan summary without mutating.

SAFETY GUARDS (Cursor R3):
  1. PRE-IMAGE BACKUP — before any --apply, copy the state file to
     `<state_dir>/.backups/state/preimage_<UTC>_clean_orphan_beats.json`.
     Path returned in stdout for manual rollback.
  2. SCOPED MODE — `--event <id>` or `--milestone <id>` required for
     first live run. `--all` is permitted only after at least one scoped
     `--apply` has been verified (state-tracked via marker file at
     ~/.claude/mindfulnest-cache/clean_orphan_beats_v3_scoped_run_marker.json).
  3. AUDIT LOG — per mutated event/milestone, ONE prod_activity_log row:
     {action: "clean_orphan_beats_v3", details: {summary, event_id /
     milestone_id, video_role, removed_beat_ids, removed_beat_payload
     (FULL beat object), preimage_backup_path, applied_at,
     tags=["beat_cleanup","DISPLAY_ORDER_STRICT_V1"]}}.

LOGIC
  - Walk Production/Event_*/production_state.json AND
    Production/Milestones/*/state.json (per spec §2.3 Part 3 + Kim's
    amendment A 2026-05-05 — Milestones walk is a no-op while the tree
    is empty; spec-as-written stays).
  - For each `videos.<role>` partition where `display_order` is a
    present LIST: drop `beats[bid]` for any bid not in `display_order`.
  - SKIP partitions where `display_order` is undefined or non-list
    (legacy data shapes — e.g. integer `display_order` in pre-v3
    fixtures).
  - Atomic writes via direct atomic_json_write (the in-process
    StateManager lock is a no-op outside the server). The state file's
    file-lock is honored to avoid corruption if the server is also
    running.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Imports: production_server provides atomic_json_write + the file-lock
# helpers; lib/directus provides try_post_or_queue.
_THIS = Path(__file__).resolve()
_REPO_ROOT = _THIS.parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT / "Production" / "tools"))
sys.path.insert(0, str(_REPO_ROOT / "Production" / "lib"))

from production_server import atomic_json_write  # noqa: E402

# Lazy import of try_post_or_queue (only when --apply, so dry-run on a
# machine without Directus credentials still works).
TRY_POST_OR_QUEUE = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


MARKER_DIR = Path(os.path.expanduser("~/.claude/mindfulnest-cache"))
MARKER_FILE = MARKER_DIR / "clean_orphan_beats_v3_scoped_run_marker.json"


def production_root() -> Path:
    """Resolve the Production/ directory.

    Convention: this script lives at Production/scripts/clean_orphan_beats_v3.py
    so Production/ is the parent of the parent. The script's effective
    "production root" is two levels up — but the runtime callable from
    Dropbox tree where data lives. Caller can override via env var
    MINDFULNEST_PRODUCTION_ROOT for tests.
    """
    override = os.environ.get("MINDFULNEST_PRODUCTION_ROOT")
    if override:
        return Path(override)
    return _THIS.parent.parent  # Production/


def _walk_event_state_paths(prod_root: Path) -> list[Path]:
    """Production/Event_<id>/production_state.json — events only."""
    return sorted(prod_root.glob("Event_*/production_state.json"))


def _walk_milestone_state_paths(prod_root: Path) -> list[Path]:
    """Production/Milestones/<milestone_id>/state.json — milestones only.

    Per Kim's amendment A 2026-05-05: tree currently empty; walk is a
    no-op. Spec-as-written stays.
    """
    milestones_root = prod_root / "Milestones"
    if not milestones_root.is_dir():
        return []
    return sorted(milestones_root.glob("*/state.json"))


def _scope_label_from_path(state_path: Path, kind: str) -> str:
    """Return a human-readable scope id for the state file."""
    if kind == "event":
        # .../Production/Event_<id>/production_state.json → Event_<id>
        return state_path.parent.name
    # .../Production/Milestones/<id>/state.json → milestone:<id>
    return f"milestone:{state_path.parent.name}"


def _identify_orphans(state: dict) -> list[dict]:
    """For each videos.<role> partition, find orphan beats.

    Returns list of {role, beat_id, payload, display_order} entries —
    one per orphan beat. Skips partitions where display_order is not a
    present list.
    """
    orphans: list[dict] = []
    videos = (state or {}).get("videos") or {}
    if not isinstance(videos, dict):
        return orphans
    for role, part in videos.items():
        if not isinstance(part, dict):
            continue
        do = part.get("display_order")
        if not isinstance(do, list):
            continue
        beats = part.get("beats")
        if not isinstance(beats, dict):
            continue
        allowed = set(do)
        for bid, payload in beats.items():
            if bid not in allowed:
                orphans.append({
                    "role": role,
                    "beat_id": bid,
                    "payload": payload,
                    "display_order_snapshot": list(do),
                })
    return orphans


def _format_dry_run(state_path: Path, scope_label: str, orphans: list[dict]) -> str:
    if not orphans:
        return f"  {scope_label}: clean (no orphans).\n"
    lines = [f"  {scope_label}: {len(orphans)} orphan(s)"]
    for o in orphans:
        text = (o.get("payload") or {}).get("text") or ""
        text_preview = text[:60].replace("\n", " ")
        if len(text) > 60:
            text_preview += "…"
        lines.append(
            f"    - role={o['role']} beat_id={o['beat_id']} "
            f"text={text_preview!r}"
        )
    return "\n".join(lines) + "\n"


def _backup_preimage(state_path: Path) -> Path:
    """Copy state file to <state_dir>/.backups/state/preimage_<UTC>_clean_orphan_beats.json.

    Returns the backup path. Raises if backup write fails — callers
    must NOT proceed with --apply if backup fails.
    """
    backup_dir = state_path.parent / ".backups" / "state"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"preimage_{_utc_stamp()}_clean_orphan_beats.json"
    backup_path.write_bytes(state_path.read_bytes())
    return backup_path


def _apply_prune(state_path: Path, orphans: list[dict]) -> dict:
    """Drop orphan beats in-place + atomically write back.

    Reads the current state (NOT the snapshot used for orphan ID — to
    avoid clobbering concurrent edits), prunes again, writes atomically.
    The double-prune is intentional — guards against state mutating
    between dry-run scan and --apply write.
    """
    current = json.loads(state_path.read_text(encoding="utf-8"))
    videos = current.get("videos") or {}
    removed_count = 0
    for o in orphans:
        role = o["role"]
        bid = o["beat_id"]
        part = videos.get(role) or {}
        beats = part.get("beats") or {}
        if bid in beats:
            del beats[bid]
            removed_count += 1
    current["updated_at"] = _now_iso()
    atomic_json_write(str(state_path), current)
    return {"removed_count": removed_count, "post_prune_state": current}


def _scoped_run_marker_present() -> bool:
    return MARKER_FILE.is_file()


def _write_scoped_run_marker(scope_label: str, removed_count: int) -> None:
    MARKER_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "last_scoped_apply": _now_iso(),
        "scope_label": scope_label,
        "removed_count": removed_count,
    }
    MARKER_FILE.write_text(json.dumps(payload, indent=2))


def _write_activity_log(scope_label: str, scope_kind: str, removed_per_role: dict,
                       preimage_path: Path) -> dict:
    """Write ONE prod_activity_log row per mutated scope.

    Returns the result dict from try_post_or_queue (or {"queued": True} if
    Directus is unreachable). The script does NOT fail on activity-log
    write errors — the on-disk prune already happened; we want a record
    of it but the row write must not block recovery.
    """
    global TRY_POST_OR_QUEUE
    if TRY_POST_OR_QUEUE is None:
        from directus import try_post_or_queue  # noqa: PLC0415
        TRY_POST_OR_QUEUE = try_post_or_queue

    # Flatten removed_per_role into removed_beat_ids + removed_beat_payload.
    removed_beat_ids: list[str] = []
    removed_beat_payload: list[dict] = []
    for role, items in removed_per_role.items():
        for o in items:
            removed_beat_ids.append(f"{role}:{o['beat_id']}")
            removed_beat_payload.append({
                "role": role,
                "beat_id": o["beat_id"],
                "payload": o["payload"],
                "display_order_at_prune": o["display_order_snapshot"],
            })

    summary = (
        f"clean_orphan_beats_v3 evicted {len(removed_beat_ids)} beat(s) "
        f"from {scope_label} ({scope_kind})"
    )
    details = {
        "summary": summary,
        "scope_kind": scope_kind,
        "scope_label": scope_label,
        "removed_beat_ids": removed_beat_ids,
        "removed_beat_payload": removed_beat_payload,
        "preimage_backup_path": str(preimage_path),
        "applied_at": _now_iso(),
        "tags": ["beat_cleanup", "DISPLAY_ORDER_STRICT_V1"],
    }
    payload = {
        "action": "clean_orphan_beats_v3",
        "performed_by": "claude_code_terminal_session",
        "details": details,
    }
    return TRY_POST_OR_QUEUE("prod_activity_log", payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="clean_orphan_beats_v3",
        description=(
            "Clean orphan beats whose ids aren't in their partition's "
            "display_order. Default dry-run."
        ),
    )
    parser.add_argument("--apply", action="store_true",
                        help="apply mutations (default: dry-run only)")
    parser.add_argument("--event", default=None,
                        help="restrict to one Event_<id> directory")
    parser.add_argument("--milestone", default=None,
                        help="restrict to one Milestones/<id>/ directory")
    parser.add_argument("--all", action="store_true", dest="all_scope",
                        help="cover every event AND milestone (requires "
                             "prior scoped --apply marker)")
    args = parser.parse_args(argv)

    if args.event and args.milestone:
        print("ERROR: --event and --milestone are mutually exclusive.",
              file=sys.stderr)
        return 2
    if args.all_scope and (args.event or args.milestone):
        print("ERROR: --all conflicts with --event/--milestone.", file=sys.stderr)
        return 2
    if args.apply and not (args.event or args.milestone or args.all_scope):
        print("ERROR: --apply requires --event <id> OR --milestone <id> "
              "OR --all (after scoped run).", file=sys.stderr)
        return 2
    if args.apply and args.all_scope and not _scoped_run_marker_present():
        print("ERROR: --all --apply refused — no prior scoped --apply "
              f"marker found at {MARKER_FILE}. Run with --apply --event "
              "<id> at least once first.", file=sys.stderr)
        return 3

    prod_root = production_root()

    # Build the target list.
    targets: list[tuple[Path, str, str]] = []  # (state_path, kind, scope_label)
    if args.event:
        candidate = prod_root / f"Event_{args.event}" / "production_state.json"
        if not candidate.is_file():
            # Allow user to pass either "2" or "Event_2" — try both.
            alt = prod_root / args.event / "production_state.json"
            if alt.is_file():
                candidate = alt
            else:
                print(f"ERROR: no production_state.json at {candidate} "
                      f"or {alt}.", file=sys.stderr)
                return 4
        targets.append((candidate, "event", _scope_label_from_path(candidate, "event")))
    elif args.milestone:
        candidate = prod_root / "Milestones" / args.milestone / "state.json"
        if not candidate.is_file():
            print(f"ERROR: no state.json at {candidate}.", file=sys.stderr)
            return 4
        targets.append((candidate, "milestone",
                        _scope_label_from_path(candidate, "milestone")))
    else:
        # --all OR default dry-run scan.
        for p in _walk_event_state_paths(prod_root):
            targets.append((p, "event", _scope_label_from_path(p, "event")))
        for p in _walk_milestone_state_paths(prod_root):
            targets.append((p, "milestone",
                            _scope_label_from_path(p, "milestone")))

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"clean_orphan_beats_v3 — mode={mode}, targets={len(targets)}")
    print(f"  production_root={prod_root}")
    if MARKER_FILE.is_file():
        print(f"  scoped-run marker present: {MARKER_FILE}")
    print()

    total_orphans = 0
    total_removed = 0
    apply_results: list[dict] = []

    for state_path, kind, scope_label in targets:
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"  {scope_label}: SKIP (could not read state: "
                  f"{type(exc).__name__}: {exc})")
            continue
        orphans = _identify_orphans(state)
        total_orphans += len(orphans)
        print(_format_dry_run(state_path, scope_label, orphans), end="")

        if not args.apply or not orphans:
            continue

        # APPLY path.
        try:
            preimage = _backup_preimage(state_path)
            print(f"    pre-image backup: {preimage}")
        except OSError as exc:
            print(f"    BACKUP FAILED: {type(exc).__name__}: {exc}; "
                  f"refusing to apply.", file=sys.stderr)
            continue

        prune_result = _apply_prune(state_path, orphans)
        total_removed += prune_result["removed_count"]
        print(f"    pruned {prune_result['removed_count']} orphan(s)")

        # Group orphans by role for the activity-log row.
        by_role: dict[str, list[dict]] = {}
        for o in orphans:
            by_role.setdefault(o["role"], []).append(o)
        try:
            log_result = _write_activity_log(scope_label, kind, by_role, preimage)
            if log_result.get("queued"):
                print(f"    activity log: QUEUED OFFLINE → "
                      f"{log_result.get('path')}")
            elif log_result.get("id"):
                print(f"    activity log: id={log_result.get('id')}")
            else:
                print(f"    activity log: {log_result}")
        except Exception as exc:  # noqa: BLE001
            print(f"    activity log WRITE FAILED (non-blocking): "
                  f"{type(exc).__name__}: {exc}", file=sys.stderr)
        apply_results.append({"scope_label": scope_label, "removed": prune_result["removed_count"]})

    print()
    print("=" * 60)
    if args.apply:
        print(f"APPLIED: {total_removed} orphan(s) removed across "
              f"{len(apply_results)} scope(s).")
        # Write/update the scoped-run marker if a scoped --apply succeeded.
        if (args.event or args.milestone) and total_removed > 0:
            scope_id = args.event or args.milestone
            _write_scoped_run_marker(scope_id, total_removed)
            print(f"  scoped-run marker updated: {MARKER_FILE}")
    else:
        print(f"DRY-RUN: {total_orphans} orphan(s) found across "
              f"{len(targets)} scope(s). Re-run with --apply --event <id> "
              "to evict.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
