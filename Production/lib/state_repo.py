"""StateRepository abstraction — V59 Phase A.

Defines the contract that StateManager (and any future read/write site)
uses to access production_state.json. Phase A ships only the JSON-backed
implementation (JsonStateRepository) which preserves current behavior
byte-equivalent. Phase 4 will add SqliteStateRepository swappable behind
the same interface.

Per LD-794 V59 spec §Phase A. Authored 2026-05-18.
"""
from __future__ import annotations

import fcntl
import json
import os
import threading
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
            with open(lock_path, "r+", encoding="utf-8") as lf:
                fcntl.lockf(lf.fileno(), fcntl.LOCK_EX)
                try:
                    state = self.read()
                    new_state = fn(state)
                    atomic_json_write(str(self.state_path), new_state)
                    return new_state
                finally:
                    fcntl.lockf(lf.fileno(), fcntl.LOCK_UN)

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
