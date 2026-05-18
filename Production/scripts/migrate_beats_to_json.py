#!/usr/bin/env python3
"""V59 Phase 9 — SQLite → JSON down-migration (rollback path).

Reads Production/Event_<X>/beats.db, reconstructs the
videos.{intro,resolution,standalone}.beats partitions, writes to a
SIDECAR file (production_state_from_sqlite.json). The caller decides
whether to swap it in (production_state.json) — this script never
touches the canonical state.json.

Usage:
    python3 Production/scripts/migrate_beats_to_json.py --event-dir Production/Event_1
    python3 Production/scripts/migrate_beats_to_json.py --event-dir Production/Event_1 --apply  # actually swaps
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
import time
from copy import deepcopy
from pathlib import Path

_SCRIPT_PATH = Path(__file__).resolve()
PRODUCTION_DIR = _SCRIPT_PATH.parents[1]

sys.path.insert(0, str(PRODUCTION_DIR))
from lib.state_repo import JsonStateRepository  # noqa: E402

V3_ROLES = ("intro", "resolution", "standalone")


def _connect_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), isolation_level=None, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def load_beats_rows(db_path: Path, event_id: str) -> list[tuple[str, str, dict]]:
    if not db_path.is_file():
        print(f"ERROR: beats db not found: {db_path}", file=sys.stderr)
        raise SystemExit(1)
    conn = _connect_db(db_path)
    try:
        rows = conn.execute(
            "SELECT video_role, beat_id, payload FROM beats WHERE event_id = ? "
            "ORDER BY video_role, beat_id",
            (event_id,),
        ).fetchall()
    finally:
        conn.close()

    out: list[tuple[str, str, dict]] = []
    for row in rows:
        try:
            beat = json.loads(row["payload"])
        except json.JSONDecodeError as exc:
            print(
                f"ERROR: corrupt payload for {row['video_role']}/{row['beat_id']}: {exc}",
                file=sys.stderr,
            )
            raise SystemExit(1) from exc
        if not isinstance(beat, dict):
            print(
                f"ERROR: payload for {row['video_role']}/{row['beat_id']} is not a dict",
                file=sys.stderr,
            )
            raise SystemExit(1)
        out.append((row["video_role"], row["beat_id"], beat))
    return out


def apply_beats_to_state(state: dict, rows: list[tuple[str, str, dict]]) -> dict:
    """Merge SQLite-derived beats into a state copy; preserve non-beat fields."""
    merged = deepcopy(state)
    videos = merged.setdefault("videos", {})
    for role in V3_ROLES:
        partition = videos.setdefault(role, {})
        if not isinstance(partition, dict):
            partition = {}
            videos[role] = partition
        partition["beats"] = {}

    legacy_beats: dict = {}
    for video_role, beat_id, beat_dict in rows:
        if video_role == "legacy":
            legacy_beats[beat_id] = beat_dict
        elif video_role in V3_ROLES:
            videos[video_role]["beats"][beat_id] = beat_dict
        else:
            partition = videos.setdefault(video_role, {})
            if not isinstance(partition, dict):
                partition = {}
                videos[video_role] = partition
            beats = partition.setdefault("beats", {})
            beats[beat_id] = beat_dict

    if legacy_beats:
        merged["beats"] = legacy_beats
    return merged


def resolve_event_id(state: dict, event_dir: Path) -> str:
    event_id = state.get("event_id")
    if isinstance(event_id, str) and event_id.strip():
        return event_id.strip()
    return event_dir.name


def down_migrate(
    event_dir: Path,
    *,
    apply: bool = False,
    db_path: Path | None = None,
) -> Path:
    """Write sidecar JSON; optionally apply via JsonStateRepository."""
    event_dir = event_dir.resolve()
    state_path = event_dir / "production_state.json"
    sidecar_path = event_dir / "production_state_from_sqlite.json"

    if not state_path.is_file():
        print(f"ERROR: missing {state_path}", file=sys.stderr)
        raise SystemExit(1)

    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"ERROR: malformed JSON in {state_path}: {exc}", file=sys.stderr)
        raise SystemExit(1)

    event_id = resolve_event_id(state, event_dir)
    beats_db = db_path or (event_dir / "beats.db")
    rows = load_beats_rows(beats_db, event_id)
    merged = apply_beats_to_state(state, rows)

    sidecar_path.write_text(
        json.dumps(merged, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"DOWN_MIGRATION_SIDECAR {sidecar_path} beats={len(rows)}")

    if apply:
        ts = time.strftime("%Y%m%d_%H%M%S")
        backup = event_dir / f"production_state.json.preApply_{ts}.bak"
        shutil.copy2(state_path, backup)
        print(f"BACKUP {backup}")
        repo = JsonStateRepository(state_path)
        repo.write(merged)
        print(f"APPLIED {state_path}")

    return sidecar_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Migrate production beats SQLite → JSON sidecar")
    parser.add_argument("--event-dir", type=Path, required=True)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Backup production_state.json and write merged beats via JsonStateRepository",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=None,
        help="Override beats.db path (default: <event-dir>/beats.db)",
    )
    args = parser.parse_args(argv)
    down_migrate(args.event_dir, apply=args.apply, db_path=args.db_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
