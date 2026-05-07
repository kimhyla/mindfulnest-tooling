#!/usr/bin/env python3
"""
Migrate Production/Event_*/production_state.json from v1 (flat) to v2
(partitioned by video_role).

S5.5a1 v2 — written + dry-run tested in S5.5a1; --apply mode reserved
for S5.5a2 where it lands ATOMICALLY with the handler refactor (per
Cursor v5 Q1 release-blocker — applying the lift without simultaneously
refactoring the ~30 handlers that read state.beats would break the
server). This script is safe to run in --dry-run mode against a live
server; --apply mode is NOT — see the user warning printed at start of
--apply mode.

Schema design and lift rules: see STORYBOARD_V59_S5_5_A1_SPEC_v2.md §3.1.
LD lock: BG_VIDEO_PARTITION_V1 (registered in S5.5a1 Phase E).

Usage:
    python3 Production/scripts/migrate_state_to_videos_partition.py [--dry-run|--apply|--validate] [--event Event_N]

Modes:
    --dry-run   (default) Print proposed lift per file. No writes. Exit 0
                if all dry-run lifts produce zero orphan top-level fields;
                non-zero on any orphan or schema violation.
    --apply     Apply migration with snapshot + atomic write. RESERVED FOR
                S5.5a2 — application without a synchronized handler refactor
                will crash the server on next event load. Prints user warning
                + 5s confirm.
    --validate  Verify all event state.json files are at version=v2 with the
                videos key. Exit 0 if all migrated; non-zero otherwise.

Idempotency: a state.json that already has version=v2 + videos.intro is
left untouched ("already migrated"). A state.json with the videos key
but version!=v2 is treated as a partial migration → script halts with a
non-zero exit and instructs manual snapshot restoration.

Author: claude_code_terminal_session, S5.5a1 v2, 2026-05-03.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Resolve project root from __file__ location (script lives in Production/scripts/).
# This makes the script work from any cwd — including Production/tools/ per
# verification gate #7 in spec v2 §8.
_SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = _SCRIPT_PATH.parents[2]  # …/Claude Mindfulnest Project Files/
PRODUCTION_DIR = PROJECT_ROOT / "Production"

# Make Production/lib importable for atomic_json_write.
sys.path.insert(0, str(PRODUCTION_DIR))
from lib.atomic_json_write import atomic_json_write  # noqa: E402


# ---------------------------------------------------------------------------
# Lift rules (spec v2 §3.1)
# ---------------------------------------------------------------------------

TOP_LEVEL_KEEP: set[str] = {
    "event_id",
    "version",
    "created_at",
    "updated_at",
    "_module_version",
    "module_sfx_cues",
    "latest_preview_stitched_path",
    "full_module_segment_boundaries",
    "fade_between_beats_ms",
    "active_video",  # NEW field added at top level (default = "intro")
}

# Fields lifted to videos.intro.{key}
INTRO_LIFT: dict[str, str] = {
    "beats": "beats",
    "image_overrides": "image_overrides",
    "display_order": "display_order",
}

PHASE_A_RE = re.compile(r"^phase_a_")
PHASE_B_RE = re.compile(r"^phase_b_")

V2_VERSION_TAG = "v2"


# ---------------------------------------------------------------------------
# Idempotency + classification
# ---------------------------------------------------------------------------


def is_already_migrated(state: dict) -> bool:
    """Strong idempotency: version=v2 AND videos key AND intro partition."""
    if state.get("version") != V2_VERSION_TAG:
        return False
    videos = state.get("videos")
    if not isinstance(videos, dict):
        return False
    if "intro" not in videos:
        return False
    return True


def is_partial_migration(state: dict) -> bool:
    """Detect interrupted migration: has videos key but version still v1.
    Fail closed in this case — manual inspection required, restore from
    snapshot under .backups/state/."""
    return ("videos" in state) and (state.get("version") != V2_VERSION_TAG)


# ---------------------------------------------------------------------------
# Lift logic
# ---------------------------------------------------------------------------


def classify_field(field_name: str) -> tuple[str, str]:
    """Classify a top-level field by lift rule.

    Returns (target_partition, new_key):
      - ("top", field_name)            — stays at top level
      - ("intro", new_key)              — lifted to videos.intro.<new_key>
      - ("phase_a", field_name)         — lifted to videos.phase_a.<field_name>
      - ("phase_b", field_name)         — lifted to videos.phase_b.<field_name>
      - ("orphan", field_name)          — no rule matched; fail closed
    """
    if field_name in TOP_LEVEL_KEEP:
        return ("top", field_name)
    if field_name in INTRO_LIFT:
        return ("intro", INTRO_LIFT[field_name])
    if PHASE_A_RE.match(field_name):
        return ("phase_a", field_name)
    if PHASE_B_RE.match(field_name):
        return ("phase_b", field_name)
    return ("orphan", field_name)


def build_v2_state(v1_state: dict) -> tuple[dict, list[str]]:
    """Construct the v2-shape dict from a v1-shape dict per the lift rules.

    Returns (v2_state, orphans) — orphans is a list of top-level field
    names that didn't match any lift rule. Caller fails closed on any
    orphans.
    """
    v2: dict = {}
    orphans: list[str] = []

    # Initialize the empty win partition (Rule 4 — placeholder for future work).
    videos: dict[str, dict] = {
        "win": {
            "video_role": "win",
            "video_label": None,
            "beats": {},
            "image_overrides": {},
        }
    }

    intro_partition: dict = {
        "video_role": "intro",
        "video_label": None,
    }
    phase_a_partition: dict = {
        "video_role": "phase_a",
        "video_label": None,
    }
    phase_b_partition: dict = {
        "video_role": "phase_b",
        "video_label": None,
    }
    intro_has_data = False
    phase_a_has_data = False
    phase_b_has_data = False

    for key, value in v1_state.items():
        target, new_key = classify_field(key)
        if target == "top":
            v2[key] = value
        elif target == "intro":
            intro_partition[new_key] = value
            intro_has_data = True
        elif target == "phase_a":
            phase_a_partition[new_key] = value
            phase_a_has_data = True
        elif target == "phase_b":
            phase_b_partition[new_key] = value
            phase_b_has_data = True
        else:
            orphans.append(key)

    # Only include partitions that actually had data lifted into them
    # (besides the always-present win placeholder).
    if intro_has_data:
        # Ensure intro has beats + image_overrides + display_order even if
        # one was missing in v1 (display_order default = []; beats /
        # image_overrides default = {}).
        intro_partition.setdefault("beats", {})
        intro_partition.setdefault("image_overrides", {})
        intro_partition.setdefault("display_order", [])
        videos["intro"] = intro_partition

    if phase_a_has_data:
        phase_a_partition.setdefault("phase_a_status", "draft")
        videos["phase_a"] = phase_a_partition

    if phase_b_has_data:
        phase_b_partition.setdefault("phase_b_status", "draft")
        videos["phase_b"] = phase_b_partition

    # Bump version + add active_video default + attach videos
    v2["version"] = V2_VERSION_TAG
    v2.setdefault("active_video", "intro")
    v2["videos"] = videos
    v2["updated_at"] = datetime.now(timezone.utc).isoformat()

    return v2, orphans


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def discover_state_files(event_filter: str | None = None) -> list[Path]:
    """Find Production/Event_*/production_state.json files. Optionally filter
    to a single event by name (e.g. 'Event_1')."""
    pattern = "Event_*/production_state.json"
    files = sorted(PRODUCTION_DIR.glob(pattern))
    if event_filter:
        files = [p for p in files if p.parent.name == event_filter]
    return files


def load_state(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------


def run_dry_run(files: list[Path]) -> int:
    print(f"\n=== DRY-RUN MODE ({len(files)} state.json file(s)) ===")
    print("No writes will occur. Reports proposed lift per file.\n")

    any_orphans = False
    for path in files:
        rel = path.relative_to(PROJECT_ROOT)
        print(f"--- {rel} ---")
        state = load_state(path)

        if is_already_migrated(state):
            print(f"  SKIP: already migrated (version=v2, videos.intro present)")
            continue

        if is_partial_migration(state):
            print(
                f"  FAIL CLOSED: videos key present but version != v2 "
                f"(version={state.get('version')!r}). Manual inspection required."
            )
            return 2

        v2_state, orphans = build_v2_state(state)
        if orphans:
            any_orphans = True
            print(f"  ORPHAN FIELDS (no lift rule): {sorted(orphans)}")
            continue

        print(f"  v1 top-level keys: {len(state)}")
        videos = v2_state["videos"]
        for role, partition in videos.items():
            field_keys = sorted(
                k for k in partition.keys()
                if k not in {"video_role", "video_label"}
            )
            beat_count = (
                len(partition.get("beats", {}))
                if isinstance(partition.get("beats"), dict) else 0
            )
            print(
                f"  videos.{role}: video_label={partition.get('video_label')!r}, "
                f"fields={field_keys}, beats={beat_count}"
            )
        top_level_kept = sorted(k for k in v2_state.keys() if k != "videos")
        print(f"  top-level kept: {top_level_kept}")
        print(f"  --> would write version={V2_VERSION_TAG}")

    if any_orphans:
        print("\nDRY-RUN FAILED: orphan top-level field(s) detected. "
              "Update lift rules or add to TOP_LEVEL_KEEP, then re-run.")
        return 1

    print("\nDRY-RUN PASS: lift rules cover all top-level fields in all files.")
    return 0


def _confirm_apply() -> bool:
    print("\n" + "=" * 72)
    print(
        "  ⚠️  APPLY MODE — this writes to Production/Event_*/production_state.json"
    )
    print("=" * 72)
    print(
        "  Before proceeding:\n"
        "    1. Stop the v59 server (pkill -f production_server.py)\n"
        "    2. Close any text editors with state.json files open\n"
        "    3. Pause Dropbox sync if you can\n"
        "    4. Confirm no background scripts are writing to the state files\n"
        "\n"
        "  Type 'apply migration' to continue, anything else to abort:"
    )
    answer = input("  > ").strip().lower()
    return answer == "apply migration"


def run_apply(files: list[Path]) -> int:
    if not _confirm_apply():
        print("Aborted.")
        return 1

    print(f"\n=== APPLY MODE ({len(files)} state.json file(s)) ===\n")

    written = 0
    skipped = 0
    for path in files:
        rel = path.relative_to(PROJECT_ROOT)
        print(f"--- {rel} ---")
        state = load_state(path)

        if is_already_migrated(state):
            print(f"  SKIP: already migrated")
            skipped += 1
            continue

        if is_partial_migration(state):
            print(
                f"  FAIL CLOSED: videos key present but version != v2. "
                f"Manual inspection required. ABORTING entire migration."
            )
            return 2

        v2_state, orphans = build_v2_state(state)
        if orphans:
            print(
                f"  FAIL CLOSED: orphan top-level fields {sorted(orphans)}. "
                f"ABORTING entire migration."
            )
            return 1

        # Snapshot first
        backups_dir = path.parent / ".backups" / "state"
        backups_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        snapshot_path = backups_dir / f"{ts}_pre_videos_migration.json"
        shutil.copy2(path, snapshot_path)
        print(f"  snapshot: {snapshot_path.relative_to(PROJECT_ROOT)}")

        # Atomic write
        atomic_json_write(str(path), v2_state)

        # Read-back verify
        readback = load_state(path)
        if not is_already_migrated(readback):
            print(
                f"  ERROR: read-back of {rel} does not pass is_already_migrated. "
                f"Restore from snapshot: {snapshot_path}"
            )
            return 3

        print(f"  WROTE: version=v2, videos.{sorted(v2_state['videos'].keys())}")
        written += 1

    print(f"\nAPPLY DONE: {written} migrated, {skipped} already migrated.")
    return 0


def run_validate(files: list[Path]) -> int:
    print(f"\n=== VALIDATE MODE ({len(files)} state.json file(s)) ===\n")
    failures: list[str] = []
    for path in files:
        rel = path.relative_to(PROJECT_ROOT)
        state = load_state(path)
        if is_already_migrated(state):
            print(f"  OK: {rel} (version=v2, videos.intro present)")
        else:
            print(f"  NOT MIGRATED: {rel} (version={state.get('version')!r})")
            failures.append(str(rel))
    if failures:
        print(f"\nVALIDATE FAILED: {len(failures)} file(s) not at v2.")
        return 1
    print("\nVALIDATE PASS: all event state.json files are at version=v2.")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[2])
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--dry-run", action="store_true", default=True,
        help="(default) Print proposed lift per file. No writes."
    )
    mode_group.add_argument(
        "--apply", action="store_true",
        help="Apply migration with snapshot + atomic write. RESERVED FOR S5.5a2."
    )
    mode_group.add_argument(
        "--validate", action="store_true",
        help="Verify all event state.json files are at version=v2."
    )
    parser.add_argument(
        "--event", type=str, default=None,
        help="Filter to a single event directory (e.g. 'Event_1')."
    )
    args = parser.parse_args(argv)

    files = discover_state_files(event_filter=args.event)
    if not files:
        msg = "No state.json files found"
        if args.event:
            msg += f" for --event {args.event!r}"
        print(msg + ".")
        return 1

    if args.apply:
        return run_apply(files)
    if args.validate:
        return run_validate(files)
    return run_dry_run(files)


if __name__ == "__main__":
    sys.exit(main())
