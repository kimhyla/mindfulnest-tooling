-- V59 Phase 9 — SQLite-backed beat storage schema.
-- Per spec §Phase 9 (LD-794). Shadow copy of production_state.json
-- videos.{intro,resolution,standalone}.beats[beat_id] partition.
--
-- One row per beat. The full beat JSON dict is stored in the `payload`
-- column as JSON text — SQLite is a fast indexed lookup + audit layer,
-- not a normalized relational store. This matches the spec's "normalized
-- beat dict equivalence" gate.

CREATE TABLE IF NOT EXISTS beats (
    event_id        TEXT NOT NULL,
    video_role      TEXT NOT NULL,         -- intro / resolution / standalone / legacy
    beat_id         TEXT NOT NULL,
    payload         TEXT NOT NULL,         -- full beat JSON dict
    payload_sha256  TEXT NOT NULL,         -- for shadow-drift detection
    migrated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (event_id, video_role, beat_id)
);

CREATE INDEX IF NOT EXISTS beats_event ON beats(event_id);
CREATE INDEX IF NOT EXISTS beats_role  ON beats(event_id, video_role);
CREATE INDEX IF NOT EXISTS beats_sha   ON beats(payload_sha256);

-- Audit table for every mutation (insert/update). Phase 9 only populates
-- it for migrate; downstream code (Phase 9.5 or later) can write per-mutation.
CREATE TABLE IF NOT EXISTS beats_audit (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id        TEXT NOT NULL,
    video_role      TEXT NOT NULL,
    beat_id         TEXT NOT NULL,
    operation       TEXT NOT NULL,         -- migrate_insert / mutate / down_migrate
    payload_before  TEXT,                  -- nullable for first migrate
    payload_after   TEXT,
    audit_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS beats_audit_beat ON beats_audit(event_id, beat_id);
