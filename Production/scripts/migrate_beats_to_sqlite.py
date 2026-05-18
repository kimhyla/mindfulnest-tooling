#!/usr/bin/env python3
"""V59 Phase 9 — JSON → SQLite beats migration.

Reads Production/Event_<X>/production_state.json, walks the v3 partitions
videos.{intro,resolution,standalone}.beats (+ legacy top-level for back-
compat), writes each beat as a row into Production/Event_<X>/beats.db.

The migration is transactional: either every beat lands or none do.

This is a ONE-WAY shadow migration tonight. The JSON file remains the
source of truth. SQLite is populated for the 24-hour shadow window, after
which (separate session) reads can flip to SQLite.

Usage:
    python3 Production/scripts/migrate_beats_to_sqlite.py --event-dir Production/Event_1
    python3 Production/scripts/migrate_beats_to_sqlite.py --event-dir Production/Event_1 --dry-run
    python3 Production/scripts/migrate_beats_to_sqlite.py --event-dir Production/Event_1 --verify

Exit codes:
    0 — migration + verify passed
    1 — pre-flight fail (state.json missing/malformed) OR verify mismatch
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

_SCRIPT_PATH = Path(__file__).resolve()
PRODUCTION_DIR = _SCRIPT_PATH.parents[1]
SCHEMA_PATH = PRODUCTION_DIR / "db" / "schema_beats.sql"

sys.path.insert(0, str(PRODUCTION_DIR))
from lib.v3_partition import _iter_v3_beats  # noqa: E402

VOLATILE_KEYS = frozenset({
    "_volatile_timestamp",
    "etag",
    "last_modified",
    "served_at",
    "audio_regenerated_at",
})


def normalize_beat_dict(obj: Any) -> Any:
    """Recursively sort keys and strip volatile timestamp/etag fields."""
    if isinstance(obj, dict):
        return {
            k: normalize_beat_dict(v)
            for k, v in sorted(obj.items())
            if k not in VOLATILE_KEYS
        }
    if isinstance(obj, list):
        return [normalize_beat_dict(item) for item in obj]
    return obj


def serialize_beat(beat_dict: dict) -> str:
    return json.dumps(beat_dict, sort_keys=True, separators=(",", ":"))


def payload_sha256(serialized: str) -> str:
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def resolve_event_id(state: dict, event_dir: Path) -> str:
    event_id = state.get("event_id")
    if isinstance(event_id, str) and event_id.strip():
        return event_id.strip()
    return event_dir.name


def beats_db_path(event_dir: Path, *, dry_run: bool) -> Path:
    if dry_run:
        return event_dir / ".beats_shadow.db"
    return event_dir / "beats.db"


def _connect_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), isolation_level=None, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))


def load_state(event_dir: Path) -> dict:
    state_path = event_dir / "production_state.json"
    if not state_path.is_file():
        print(f"ERROR: missing {state_path}", file=sys.stderr)
        raise SystemExit(1)
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"ERROR: malformed JSON in {state_path}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def source_beats_map(state: dict) -> dict[tuple[str, str], dict]:
    """Map (video_role, beat_id) -> normalized beat dict from JSON source."""
    out: dict[tuple[str, str], dict] = {}
    for role, beat_id, beat in _iter_v3_beats(state):
        out[(role, beat_id)] = normalize_beat_dict(beat)
    return out


def migrate_beats(
    conn: sqlite3.Connection,
    *,
    event_id: str,
    state: dict,
) -> int:
    """Transactional insert of all beats. Returns row count."""
    beats = list(_iter_v3_beats(state))
    conn.execute("BEGIN")
    try:
        for video_role, beat_id, beat_dict in beats:
            serialized = serialize_beat(beat_dict)
            sha = payload_sha256(serialized)
            conn.execute(
                "INSERT OR REPLACE INTO beats "
                "(event_id, video_role, beat_id, payload, payload_sha256, updated_at) "
                "VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
                (event_id, video_role, beat_id, serialized, sha),
            )
            conn.execute(
                "INSERT INTO beats_audit "
                "(event_id, video_role, beat_id, operation, payload_before, payload_after) "
                "VALUES (?, ?, ?, 'migrate_insert', NULL, ?)",
                (event_id, video_role, beat_id, serialized),
            )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return len(beats)


def verify_beats(
    db_path: Path,
    state: dict,
    *,
    event_id: str | None = None,
) -> int:
    """Compare SQLite payloads to normalized JSON source. Returns exit code."""
    expected = source_beats_map(state)
    resolved_event_id = event_id or resolve_event_id(state, db_path.parent)

    if not db_path.is_file():
        print(f"ERROR: beats db not found: {db_path}", file=sys.stderr)
        return 1

    conn = _connect_db(db_path)
    try:
        rows = conn.execute(
            "SELECT video_role, beat_id, payload FROM beats WHERE event_id = ?",
            (resolved_event_id,),
        ).fetchall()
    finally:
        conn.close()

    if len(rows) != len(expected):
        print(
            f"VERIFY_FAIL row_count db={len(rows)} json={len(expected)}",
            file=sys.stderr,
        )
        return 1

    for row in rows:
        key = (row["video_role"], row["beat_id"])
        if key not in expected:
            print(f"VERIFY_FAIL unexpected row {key}", file=sys.stderr)
            return 1
        try:
            payload = json.loads(row["payload"])
        except json.JSONDecodeError as exc:
            print(f"VERIFY_FAIL corrupt payload for {key}: {exc}", file=sys.stderr)
            return 1
        got = normalize_beat_dict(payload)
        want = expected[key]
        if got != want:
            print(f"VERIFY_FAIL beat mismatch {key}", file=sys.stderr)
            print(f"  expected: {json.dumps(want, sort_keys=True)}", file=sys.stderr)
            print(f"  got:      {json.dumps(got, sort_keys=True)}", file=sys.stderr)
            return 1

    for key in expected:
        if not any((r["video_role"], r["beat_id"]) == key for r in rows):
            print(f"VERIFY_FAIL missing row {key}", file=sys.stderr)
            return 1

    print(f"MIGRATION_VERIFY_PASSED event_id={resolved_event_id} beats={len(rows)}")
    return 0


def run_migration(
    event_dir: Path,
    *,
    dry_run: bool = False,
    verify_only: bool = False,
    no_verify: bool = False,
) -> int:
    event_dir = event_dir.resolve()
    state = load_state(event_dir)
    event_id = resolve_event_id(state, event_dir)
    db_path = beats_db_path(event_dir, dry_run=dry_run)

    if verify_only:
        return verify_beats(db_path, state, event_id=event_id)

    conn = _connect_db(db_path)
    try:
        init_schema(conn)
        count = migrate_beats(conn, event_id=event_id, state=state)
    finally:
        conn.close()

    print(f"MIGRATION_COMPLETE event_id={event_id} beats={count} db={db_path}")

    if no_verify:
        return 0
    return verify_beats(db_path, state, event_id=event_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Migrate production beats JSON → SQLite")
    parser.add_argument(
        "--event-dir",
        type=Path,
        required=True,
        help="Event directory containing production_state.json",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Write to .beats_shadow.db instead of beats.db",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify existing db against JSON without migrating",
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Skip post-migration verify",
    )
    args = parser.parse_args(argv)
    return run_migration(
        args.event_dir,
        dry_run=args.dry_run,
        verify_only=args.verify,
        no_verify=args.no_verify,
    )


if __name__ == "__main__":
    raise SystemExit(main())
