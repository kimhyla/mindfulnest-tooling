"""StateRepository abstraction — V59 Phase A.

Defines the contract that StateManager (and any future read/write site)
uses to access production_state.json. Phase A ships only the JSON-backed
implementation (JsonStateRepository) which preserves current behavior
byte-equivalent. Phase 4 will add SqliteStateRepository swappable behind
the same interface.

Per LD-794 V59 spec §Phase A. Authored 2026-05-18.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Protocol

try:
    # When imported from server (sys.path includes Production/)
    from lib.atomic_json_write import atomic_json_write  # type: ignore[import]
except ImportError:  # pragma: no cover
    # When imported from repo root (pytest, scripts using REPO_ROOT/sys.path)
    from Production.lib.atomic_json_write import atomic_json_write

# Class-level registry of per-path in-process locks. Ensures multiple
# JsonStateRepository instances pointing at the same state file serialize
# correctly within one process. Cross-process serialization is handled by
# the sidecar .lock file + fcntl.lockf below.
_INPROC_LOCKS: dict[str, threading.Lock] = {}
_INPROC_LOCKS_GUARD = threading.Lock()


@contextmanager
def _exclusive_file_lock(lock_path: Path):
    """Cross-platform one-byte advisory lock for repository mutations."""
    if not lock_path.exists():
        lock_path.touch()
    with open(lock_path, "r+b") as lock_file:
        if lock_path.stat().st_size == 0:
            lock_file.write(b"\0")
            lock_file.flush()
        lock_file.seek(0)
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.lockf(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            lock_file.seek(0)
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.lockf(lock_file.fileno(), fcntl.LOCK_UN)


def _get_inproc_lock(path: Path) -> threading.Lock:
    key = str(path.resolve())
    with _INPROC_LOCKS_GUARD:
        lock = _INPROC_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _INPROC_LOCKS[key] = lock
        return lock


class StateRepository(Protocol):
    state_path: Path  # absolute path to production_state.json (or future SQLite file)

    def read(self) -> dict:
        """Return entire state document as a dict. Returns {} if file does not exist."""

    def write(self, obj: dict) -> None:
        """Atomically replace the entire state document."""

    def mutate(self, fn: Callable[[dict], dict]) -> dict:
        """Read-modify-write under an fcntl lock. fn receives current state, returns new state.
        Returns the post-mutation state.
        """

    def read_field(self, dotted_path: str, default: Any = None) -> Any:
        """Return nested field by dotted path, e.g. 'beats.beat_05.text'. Default if missing."""

    def write_field(self, dotted_path: str, value: Any) -> None:
        """Atomically set a nested field by dotted path."""


class JsonStateRepository:
    """JSON-file-backed StateRepository. Wraps the existing
    Production.lib.atomic_json_write helper + fcntl mutate pattern from
    production_server.StateManager.

    This class is intentionally a thin port — no new behavior, just a
    seam for Phase 4 to plug a SqliteStateRepository behind.
    """

    def __init__(self, state_path: Path) -> None:
        self.state_path = state_path

    def read(self) -> dict:
        if not self.state_path.exists():
            return {}
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise json.JSONDecodeError(
                f"{exc.msg} in {self.state_path}",
                exc.doc,
                exc.pos,
            ) from exc

    def write(self, obj: dict) -> None:
        atomic_json_write(str(self.state_path), obj)

    def mutate(self, fn: Callable[[dict], dict]) -> dict:
        """Atomic read-modify-write under both in-process and cross-process locks.

        The lock is held on a sidecar `.lock` file (NOT state_path itself),
        because atomic_json_write replaces state_path via rename — locks held
        on the original inode become orphaned and offer no serialization.
        Mirrors the pattern in production_server.StateManager (file_lock_path).
        """
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.state_path.with_suffix(self.state_path.suffix + ".lock")
        if not lock_path.exists():
            lock_path.touch()
        inproc_lock = _get_inproc_lock(self.state_path)
        with inproc_lock:
            with _exclusive_file_lock(lock_path):
                state = self.read()
                new_state = fn(state)
                atomic_json_write(str(self.state_path), new_state)
                return new_state

    def read_field(self, dotted_path: str, default: Any = None) -> Any:
        parts = dotted_path.split(".")
        obj: Any = self.read()
        for key in parts:
            if not isinstance(obj, dict) or key not in obj:
                return default
            obj = obj[key]
        return obj

    def write_field(self, dotted_path: str, value: Any) -> None:
        parts = dotted_path.split(".")

        def _mutator(state: dict) -> dict:
            cur = state
            for key in parts[:-1]:
                nxt = cur.get(key)
                if not isinstance(nxt, dict):
                    nxt = {}
                    cur[key] = nxt
                cur = nxt
            cur[parts[-1]] = value
            return state

        self.mutate(_mutator)


_SCHEMA_BEATS_PATH = Path(__file__).resolve().parent.parent / "db" / "schema_beats.sql"


def _serialize_beat_payload(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _beat_payload_sha256(serialized: str) -> str:
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class SqliteBeatRepository:
    """Beat-level shim for Phase 9 shadow. JSON remains source; SQLite shadows.

    Public API mirrors what a future SqliteStateRepository would provide:
      - get_beat(event_id, video_role, beat_id) -> dict | None
      - set_beat(event_id, video_role, beat_id, payload) -> None
      - mutate_beat(event_id, video_role, beat_id, fn) -> dict
      - list_beats(event_id, video_role=None) -> list[(role, beat_id, payload)]

    SHADOW DUAL-WRITE: every write hits BOTH the JSON state file (via the
    wrapped JsonStateRepository) AND the SQLite table. Reads default to
    JSON. A future cutover phase will flip reads to SQLite + add a
    drift-detect background job.
    """

    def __init__(
        self,
        event_id: str,
        json_repo: JsonStateRepository,
        db_path: Path,
    ) -> None:
        self.event_id = event_id
        self._json = json_repo
        self.db_path = db_path
        self._lock = threading.Lock()
        self._ensure_schema()

    def _conn(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), isolation_level=None, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._lock, self._conn() as conn:
            conn.executescript(_SCHEMA_BEATS_PATH.read_text(encoding="utf-8"))

    def _write_sqlite(
        self,
        video_role: str,
        beat_id: str,
        payload: dict,
        *,
        operation: str = "mutate",
        payload_before: str | None = None,
    ) -> None:
        serialized = _serialize_beat_payload(payload)
        sha = _beat_payload_sha256(serialized)
        with self._lock, self._conn() as conn:
            conn.execute("BEGIN")
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO beats "
                    "(event_id, video_role, beat_id, payload, payload_sha256, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
                    (self.event_id, video_role, beat_id, serialized, sha),
                )
                conn.execute(
                    "INSERT INTO beats_audit "
                    "(event_id, video_role, beat_id, operation, payload_before, payload_after) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        self.event_id,
                        video_role,
                        beat_id,
                        operation,
                        payload_before,
                        serialized,
                    ),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def _read_json_beat(self, video_role: str, beat_id: str) -> dict | None:
        state = self._json.read()
        if video_role == "legacy":
            beat = (state.get("beats") or {}).get(beat_id)
        else:
            videos = state.get("videos") or {}
            partition = videos.get(video_role) or {}
            beat = (partition.get("beats") or {}).get(beat_id)
        return beat if isinstance(beat, dict) else None

    def _mutate_json_beat(
        self,
        video_role: str,
        beat_id: str,
        fn: Callable[[dict], dict],
    ) -> dict:
        def _state_mutator(state: dict) -> dict:
            if video_role == "legacy":
                beats = state.setdefault("beats", {})
                current = beats.get(beat_id)
                if not isinstance(current, dict):
                    current = {}
                beats[beat_id] = fn(current)
            else:
                videos = state.setdefault("videos", {})
                partition = videos.setdefault(video_role, {})
                if not isinstance(partition, dict):
                    partition = {}
                    videos[video_role] = partition
                beats = partition.setdefault("beats", {})
                current = beats.get(beat_id)
                if not isinstance(current, dict):
                    current = {}
                beats[beat_id] = fn(current)
            return state

        new_state = self._json.mutate(_state_mutator)
        if video_role == "legacy":
            return (new_state.get("beats") or {})[beat_id]
        return (new_state["videos"][video_role]["beats"])[beat_id]

    def get_beat(self, event_id: str, video_role: str, beat_id: str) -> dict | None:
        if event_id != self.event_id:
            return None
        return self._read_json_beat(video_role, beat_id)

    def set_beat(
        self,
        event_id: str,
        video_role: str,
        beat_id: str,
        payload: dict,
    ) -> None:
        if event_id != self.event_id:
            raise ValueError(f"event_id mismatch: {event_id} != {self.event_id}")

        before = self._read_json_beat(video_role, beat_id)
        payload_before = _serialize_beat_payload(before) if before is not None else None

        def _replace(_current: dict) -> dict:
            return payload

        updated = self._mutate_json_beat(video_role, beat_id, _replace)
        self._write_sqlite(
            video_role,
            beat_id,
            updated,
            operation="mutate",
            payload_before=payload_before,
        )

    def mutate_beat(
        self,
        event_id: str,
        video_role: str,
        beat_id: str,
        fn: Callable[[dict], dict],
    ) -> dict:
        if event_id != self.event_id:
            raise ValueError(f"event_id mismatch: {event_id} != {self.event_id}")

        before = self._read_json_beat(video_role, beat_id)
        payload_before = _serialize_beat_payload(before) if before is not None else None
        updated = self._mutate_json_beat(video_role, beat_id, fn)
        self._write_sqlite(
            video_role,
            beat_id,
            updated,
            operation="mutate",
            payload_before=payload_before,
        )
        return updated

    def list_beats(
        self,
        event_id: str,
        video_role: str | None = None,
    ) -> list[tuple[str, str, dict]]:
        if event_id != self.event_id:
            return []
        try:
            from lib.v3_partition import _iter_v3_beats  # type: ignore[import]
        except ImportError:  # pragma: no cover
            from Production.lib.v3_partition import _iter_v3_beats

        rows = [
            (role, bid, beat)
            for role, bid, beat in _iter_v3_beats(self._json.read())
            if video_role is None or role == video_role
        ]
        return rows
