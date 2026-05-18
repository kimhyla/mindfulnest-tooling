"""Durable vendor-job registry — V59 Phase 5.

SQLite-backed table tracking every async vendor submission so the server
can resume in-flight jobs after a crash/restart. Without this, vendor jobs
submitted just before a restart are 'orphaned' — vendor completes, but no
poller knows to claim the result.

Per V59 spec §Phase 5 + LD-744 (the original LD was fabricated 2026-05-17
audit; this is the real implementation).

Schema (table `vendor_jobs`):
  id              INTEGER PRIMARY KEY AUTOINCREMENT
  beat_id         TEXT NOT NULL
  option_idx      INTEGER          -- nullable for non-option-keyed jobs (lipsync)
  task_id         TEXT NOT NULL    -- vendor's submission id
  vendor          TEXT NOT NULL    -- kling, bytedance, openai, bfl, elevenlabs, wavespeed
  video_role      TEXT NOT NULL    -- intro / resolution / standalone / legacy
  event_generation INTEGER NOT NULL -- monotonic counter; bumped on event switch
  submitted_epoch INTEGER NOT NULL
  status          TEXT NOT NULL    -- submitted / polling / completed / failed / cancelled
  last_polled_epoch INTEGER        -- nullable until first poll
  last_error      TEXT             -- nullable
  created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP

Indexes:
  CREATE INDEX vj_status ON vendor_jobs(status)
  CREATE INDEX vj_vendor ON vendor_jobs(vendor)
  CREATE UNIQUE INDEX vj_task_id ON vendor_jobs(task_id)
"""
from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "Event_1" / ".vendor_jobs.db"


class DurableJobRegistry:
    """Thread-safe SQLite-backed vendor-job tracker."""

    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._lock = threading.Lock()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(str(self.db_path), isolation_level=None, timeout=10)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
        return c

    def _init_db(self):
        with self._lock, self._conn() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS vendor_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    beat_id TEXT NOT NULL,
                    option_idx INTEGER,
                    task_id TEXT NOT NULL,
                    vendor TEXT NOT NULL,
                    video_role TEXT NOT NULL,
                    event_generation INTEGER NOT NULL,
                    submitted_epoch INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    last_polled_epoch INTEGER,
                    last_error TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS vj_status ON vendor_jobs(status);
                CREATE INDEX IF NOT EXISTS vj_vendor ON vendor_jobs(vendor);
                CREATE UNIQUE INDEX IF NOT EXISTS vj_task_id ON vendor_jobs(task_id);
            """)

    def submit(self, *, beat_id: str, vendor: str, task_id: str, video_role: str,
               event_generation: int, option_idx: Optional[int] = None) -> int:
        """Record a new vendor submission. Returns row id."""
        now = int(time.time())
        with self._lock, self._conn() as c:
            cur = c.execute(
                "INSERT INTO vendor_jobs (beat_id, option_idx, task_id, vendor, video_role, "
                "event_generation, submitted_epoch, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'submitted')",
                (beat_id, option_idx, task_id, vendor, video_role, event_generation, now),
            )
            return cur.lastrowid

    def mark(self, task_id: str, status: str, *, last_error: Optional[str] = None) -> None:
        """Update job status (polling/completed/failed/cancelled)."""
        now = int(time.time())
        with self._lock, self._conn() as c:
            c.execute(
                "UPDATE vendor_jobs SET status=?, last_polled_epoch=?, last_error=? "
                "WHERE task_id=?",
                (status, now, last_error, task_id),
            )

    def list_pending(self, *, vendor: Optional[str] = None,
                     event_generation: Optional[int] = None) -> list[dict]:
        """Return all jobs with status in ('submitted','polling') optionally filtered."""
        q = "SELECT * FROM vendor_jobs WHERE status IN ('submitted','polling')"
        params: list = []
        if vendor:
            q += " AND vendor=?"
            params.append(vendor)
        if event_generation is not None:
            q += " AND event_generation=?"
            params.append(event_generation)
        q += " ORDER BY submitted_epoch ASC"
        with self._conn() as c:
            rows = c.execute(q, params).fetchall()
            return [dict(r) for r in rows]

    def get(self, task_id: str) -> Optional[dict]:
        with self._conn() as c:
            row = c.execute(
                "SELECT * FROM vendor_jobs WHERE task_id=?", (task_id,)
            ).fetchone()
            return dict(row) if row else None

    def purge_stale(self, *, older_than_epoch: int) -> int:
        """Delete COMPLETED/FAILED/CANCELLED jobs older than threshold. Returns count deleted."""
        with self._lock, self._conn() as c:
            cur = c.execute(
                "DELETE FROM vendor_jobs WHERE status IN ('completed','failed','cancelled') "
                "AND submitted_epoch < ?",
                (older_than_epoch,),
            )
            return cur.rowcount

    def all_jobs(self) -> list[dict]:
        """Debugging — return every row."""
        with self._conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM vendor_jobs ORDER BY id").fetchall()]
