"""Beat Gen sidecar — SQLite WAL authority (BEATGEN_SIDECAR_SQLITE_AUTHORITY_SPEC_v1).

Local ``beatgen.db`` is write authority; Dropbox ``beat_generator_state.json`` is
mirror-only (via ``sidecar_mirror``).
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

SCHEMA_VERSION = 1
_META_KEYS = frozenset({"schema_version", "active_context", "_runtime", "_last_updated"})

_EVENT_FROM_BEAT_RE = re.compile(r"event[_]?(\d+)", re.I)


def default_db_path() -> Path:
    raw = os.environ.get("MN_BEATGEN_DB_PATH", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return Path.home() / ".mindfulnest" / "state" / "beatgen.db"


def sqlite_authority_enabled() -> bool:
    """Env override, else auto-on when DB file exists after migration."""
    env = os.environ.get("MN_SIDECAR_SQLITE_AUTHORITY", "").strip().lower()
    if env in ("0", "false", "no"):
        return False
    if env in ("1", "true", "yes"):
        return True
    return default_db_path().is_file()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _event_id_from_beat_id(beat_id: str) -> str:
    m = _EVENT_FROM_BEAT_RE.search(beat_id or "")
    if m:
        return f"Event_{m.group(1)}"
    return "Event_unknown"


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _json_loads(raw: str) -> Any:
    return json.loads(raw)


class BeatgenStore:
    """Thread-safe SQLite store for Beat Gen sidecar state."""

    _instance: BeatgenStore | None = None
    _instance_lock = threading.Lock()

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path or default_db_path()).expanduser().resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None

    @classmethod
    def get(cls, db_path: Path | str | None = None) -> BeatgenStore:
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls(db_path)
            return cls._instance

    @classmethod
    def reset_singleton_for_tests(cls) -> None:
        with cls._instance_lock:
            if cls._instance is not None:
                cls._instance.close()
            cls._instance = None

    def connect(self) -> sqlite3.Connection:
        with self._lock:
            if self._conn is not None:
                return self._conn
            try:
                self._conn = self._open_connection()
            except (sqlite3.DatabaseError, sqlite3.OperationalError) as exc:
                print(f"[beatgen_store] connect failed — recovering: {exc}", flush=True)
                self.recover_corrupt_database()
                self._conn = self._open_connection()
            return self._conn

    def _open_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=30.0,
            isolation_level=None,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema(conn)
        return conn

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def _init_schema(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_info (
              key   TEXT PRIMARY KEY,
              value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS beats (
              beat_id     TEXT PRIMARY KEY,
              event_id    TEXT NOT NULL,
              arc_key     TEXT NOT NULL,
              segment_key TEXT NOT NULL,
              beat_index  INTEGER NOT NULL,
              beat_json   TEXT NOT NULL,
              revision    INTEGER NOT NULL DEFAULT 0,
              updated_at  TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_beats_segment
              ON beats(arc_key, segment_key, beat_index);
            CREATE INDEX IF NOT EXISTS idx_beats_event ON beats(event_id);
            CREATE TABLE IF NOT EXISTS sidecar_meta (
              key   TEXT PRIMARY KEY,
              value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS segment_meta (
              arc_key     TEXT NOT NULL,
              segment_key TEXT NOT NULL,
              seg_json    TEXT NOT NULL,
              PRIMARY KEY (arc_key, segment_key)
            );
            """
        )
        row = conn.execute(
            "SELECT value FROM schema_info WHERE key='store_schema_version'",
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO schema_info(key, value) VALUES ('store_schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )

    def integrity_check(self) -> str:
        conn = self.connect()
        row = conn.execute("PRAGMA integrity_check").fetchone()
        return str(row[0]) if row else "unknown"

    def beat_count(self) -> int:
        conn = self.connect()
        row = conn.execute("SELECT COUNT(*) FROM beats").fetchone()
        return int(row[0]) if row else 0

    def recover_corrupt_database(self) -> None:
        """Drop malformed SQLite file so JSON bootstrap can rebuild authority."""
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None
            for suffix in ("-wal", "-shm"):
                aux = Path(f"{self.db_path}{suffix}")
                try:
                    aux.unlink(missing_ok=True)
                except OSError as exc:
                    print(f"[beatgen_store] could not remove {aux.name}: {exc}", flush=True)
            if self.db_path.is_file():
                corrupt = self.db_path.with_suffix(
                    f".corrupt.{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.bak",
                )
                try:
                    self.db_path.replace(corrupt)
                    print(f"[beatgen_store] quarantined corrupt DB -> {corrupt.name}", flush=True)
                except OSError as exc:
                    print(f"[beatgen_store] could not quarantine corrupt DB: {exc}", flush=True)
                    self.db_path.unlink(missing_ok=True)

    def import_from_dict(self, data: dict, *, replace: bool = True) -> int:
        """Import full sidecar JSON shape into SQLite. Returns beat count."""
        conn = self.connect()
        now = _utc_now_iso()
        count = 0
        with self._lock:
            conn.execute("BEGIN IMMEDIATE")
            try:
                if replace:
                    conn.execute("DELETE FROM beats")
                    conn.execute("DELETE FROM sidecar_meta")
                    conn.execute("DELETE FROM segment_meta")
                for key in _META_KEYS:
                    if key in data:
                        conn.execute(
                            "INSERT OR REPLACE INTO sidecar_meta(key, value) VALUES (?, ?)",
                            (key, _json_dumps(data[key])),
                        )
                arcs = data.get("arcs") or {}
                if not isinstance(arcs, dict):
                    arcs = {}
                for arc_key, arc in arcs.items():
                    if not isinstance(arc, dict):
                        continue
                    segments = arc.get("segments") or {}
                    if not isinstance(segments, dict):
                        continue
                    for segment_key, seg in segments.items():
                        if not isinstance(seg, dict):
                            continue
                        beats = seg.get("beats") or []
                        if not isinstance(beats, list):
                            continue
                        seg_meta = {k: v for k, v in seg.items() if k != "beats"}
                        if seg_meta:
                            conn.execute(
                                """
                                INSERT OR REPLACE INTO segment_meta(arc_key, segment_key, seg_json)
                                VALUES (?, ?, ?)
                                """,
                                (str(arc_key), str(segment_key), _json_dumps(seg_meta)),
                            )
                        for idx, beat in enumerate(beats):
                            if not isinstance(beat, dict):
                                continue
                            beat_id = str(beat.get("beat_id") or "").strip()
                            if not beat_id:
                                continue
                            conn.execute(
                                """
                                INSERT OR REPLACE INTO beats(
                                  beat_id, event_id, arc_key, segment_key, beat_index,
                                  beat_json, revision, updated_at
                                ) VALUES (?, ?, ?, ?, ?, ?, 0, ?)
                                """,
                                (
                                    beat_id,
                                    _event_id_from_beat_id(beat_id),
                                    str(arc_key),
                                    str(segment_key),
                                    int(idx),
                                    _json_dumps(beat),
                                    now,
                                ),
                            )
                            count += 1
                conn.execute(
                    "INSERT OR REPLACE INTO sidecar_meta(key, value) VALUES ('_last_updated', ?)",
                    (now,),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        return count

    def assemble_sidecar_dict(self) -> dict:
        with self._lock:
            conn = self.connect()
            meta: dict[str, Any] = {}
            for row in conn.execute("SELECT key, value FROM sidecar_meta"):
                key = str(row["key"])
                if key == "_last_updated":
                    meta[key] = row["value"]
                else:
                    try:
                        meta[key] = _json_loads(row["value"])
                    except json.JSONDecodeError:
                        meta[key] = row["value"]
            arcs: dict[str, dict] = defaultdict(lambda: {"segments": defaultdict(lambda: {"beats": []})})
            rows = conn.execute(
                """
                SELECT beat_id, arc_key, segment_key, beat_index, beat_json
                FROM beats
                ORDER BY arc_key, segment_key, beat_index
                """,
            ).fetchall()
            seg_meta_rows = {
                (str(r["arc_key"]), str(r["segment_key"])): _json_loads(r["seg_json"])
                for r in conn.execute("SELECT arc_key, segment_key, seg_json FROM segment_meta")
            }
            for row in rows:
                arc_key = str(row["arc_key"])
                segment_key = str(row["segment_key"])
                beat = _json_loads(row["beat_json"])
                seg = arcs[arc_key]["segments"][segment_key]
                extra = seg_meta_rows.get((arc_key, segment_key)) or {}
                for k, v in extra.items():
                    if k != "beats":
                        seg[k] = v
                while len(seg.setdefault("beats", [])) <= int(row["beat_index"]):
                    seg["beats"].append({})
                seg["beats"][int(row["beat_index"])] = beat
            out_arcs: dict[str, Any] = {}
            for arc_key, arc in arcs.items():
                segs: dict[str, Any] = {}
                for seg_key, seg in arc["segments"].items():
                    beats_list = [b for b in seg.get("beats", []) if b]
                    segs[seg_key] = {k: v for k, v in seg.items() if k != "beats"}
                    segs[seg_key]["beats"] = beats_list
                out_arcs[arc_key] = {"segments": segs}
            result = dict(meta)
            result["arcs"] = out_arcs
            if "schema_version" not in result:
                result["schema_version"] = 3
            return result

    def patch_beat(
        self,
        beat_id: str,
        mutator: Callable[[dict, dict], None],
        *,
        expected_attempt_id: str | None = None,
    ) -> tuple[bool, dict | None]:
        """Atomically read-modify-write one beat under store lock + BEGIN IMMEDIATE."""
        expected_event = _event_id_from_beat_id(beat_id)
        conn = self.connect()
        with self._lock:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT beat_json, event_id FROM beats WHERE beat_id=?",
                    (beat_id,),
                ).fetchone()
                if not row:
                    conn.execute("ROLLBACK")
                    return False, None
                if str(row["event_id"]) != expected_event:
                    raise ValueError(
                        f"beat_id {beat_id!r} event_id mismatch: row={row['event_id']!r} "
                        f"expected={expected_event!r}"
                    )
                beat = json.loads(row["beat_json"])
                if (
                    expected_attempt_id is not None
                    and beat.get("kling_o3_voice_fix_attempt_id") != expected_attempt_id
                ):
                    conn.execute("ROLLBACK")
                    return False, beat
                sidecar = self.assemble_sidecar_dict()
                _seg, sidecar_beat = _find_beat_in_dict(sidecar, beat_id)
                if sidecar_beat is None:
                    conn.execute("ROLLBACK")
                    return False, None
                sidecar_beat.clear()
                sidecar_beat.update(beat)
                mutator(sidecar_beat, sidecar)
                now = _utc_now_iso()
                conn.execute(
                    """
                    UPDATE beats SET beat_json=?, revision=revision+1, updated_at=?
                    WHERE beat_id=?
                    """,
                    (_json_dumps(sidecar_beat), now, beat_id),
                )
                for key in _META_KEYS:
                    if key in sidecar:
                        conn.execute(
                            "INSERT OR REPLACE INTO sidecar_meta(key, value) VALUES (?, ?)",
                            (key, _json_dumps(sidecar[key]) if key != "_last_updated" else sidecar[key]),
                        )
                conn.execute(
                    "INSERT OR REPLACE INTO sidecar_meta(key, value) VALUES ('_last_updated', ?)",
                    (now,),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        return True, sidecar_beat

    def delete_beat(self, beat_id: str) -> bool:
        """Remove one beat row and compact beat_index within its segment."""
        expected_event = _event_id_from_beat_id(beat_id)
        conn = self.connect()
        with self._lock:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    """
                    SELECT arc_key, segment_key, event_id
                    FROM beats WHERE beat_id=?
                    """,
                    (beat_id,),
                ).fetchone()
                if not row:
                    conn.execute("ROLLBACK")
                    return False
                if str(row["event_id"]) != expected_event:
                    raise ValueError(
                        f"beat_id {beat_id!r} event_id mismatch: row={row['event_id']!r} "
                        f"expected={expected_event!r}"
                    )
                arc_key = str(row["arc_key"])
                segment_key = str(row["segment_key"])
                conn.execute("DELETE FROM beats WHERE beat_id=?", (beat_id,))
                remaining = conn.execute(
                    """
                    SELECT beat_id FROM beats
                    WHERE arc_key=? AND segment_key=?
                    ORDER BY beat_index
                    """,
                    (arc_key, segment_key),
                ).fetchall()
                now = _utc_now_iso()
                for idx, rem in enumerate(remaining):
                    conn.execute(
                        """
                        UPDATE beats SET beat_index=?, updated_at=?
                        WHERE beat_id=?
                        """,
                        (idx, now, str(rem["beat_id"])),
                    )
                conn.execute(
                    "INSERT OR REPLACE INTO sidecar_meta(key, value) VALUES ('_last_updated', ?)",
                    (now,),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        return True

    def replace_full(self, data: dict) -> None:
        self.import_from_dict(data, replace=True)


def _find_beat_in_dict(sidecar: dict, beat_id: str) -> tuple[dict | None, dict | None]:
    for arc in (sidecar.get("arcs") or {}).values():
        if not isinstance(arc, dict):
            continue
        for seg in (arc.get("segments") or {}).values():
            if not isinstance(seg, dict):
                continue
            for beat in seg.get("beats") or []:
                if isinstance(beat, dict) and beat.get("beat_id") == beat_id:
                    return seg, beat
    return None, None


def beats_equal_by_id(left: dict, right: dict) -> bool:
    """Deep equality of sidecar dicts by beat_id set and beat JSON."""
    def index(data: dict) -> dict[str, str]:
        out: dict[str, str] = {}
        for arc in (data.get("arcs") or {}).values():
            if not isinstance(arc, dict):
                continue
            for seg in (arc.get("segments") or {}).values():
                if not isinstance(seg, dict):
                    continue
                for beat in seg.get("beats") or []:
                    if isinstance(beat, dict) and beat.get("beat_id"):
                        out[str(beat["beat_id"])] = _json_dumps(beat)
        return out

    a, b = index(left), index(right)
    if set(a) != set(b):
        return False
    return all(a[k] == b[k] for k in a)
