"""Playground overlay tables (SQLite). Constitution schemas are not altered."""

from __future__ import annotations

import sqlite3

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS user_playground_item (
    user_id TEXT NOT NULL,
    law_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'in_playground',
    added_at TEXT NOT NULL,
    last_activity_at TEXT NOT NULL,
    source_version TEXT NOT NULL,
    law_source_hash TEXT NOT NULL,
    PRIMARY KEY (user_id, law_id)
);

CREATE TABLE IF NOT EXISTS user_playground_selection (
    user_id TEXT NOT NULL,
    law_id TEXT NOT NULL,
    source_locator TEXT NOT NULL,
    selected_at TEXT NOT NULL,
    source_version TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    PRIMARY KEY (user_id, law_id, source_locator)
);

CREATE TABLE IF NOT EXISTS user_playground_progress (
    user_id TEXT NOT NULL,
    law_id TEXT NOT NULL,
    source_locator TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new',
    cloze_done INTEGER NOT NULL DEFAULT 0,
    times_completed INTEGER NOT NULL DEFAULT 0,
    last_completed TEXT,
    next_revision TEXT,
    interval_days INTEGER NOT NULL DEFAULT 0,
    source_version TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    learned_at TEXT,
    PRIMARY KEY (user_id, law_id, source_locator)
);

CREATE TABLE IF NOT EXISTS user_playground_mode_progress (
    user_id TEXT NOT NULL,
    law_id TEXT NOT NULL,
    source_locator TEXT NOT NULL,
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    first_started_at TEXT,
    last_attempt_at TEXT,
    completed_at TEXT,
    source_version TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, law_id, source_locator, mode),
    CHECK (mode IN ('read', 'cloze', 'letters', 'type', 'recite', 'test')),
    CHECK (status IN ('in_progress', 'completed'))
);

CREATE TABLE IF NOT EXISTS user_playground_revision_mode_progress (
    user_id TEXT NOT NULL,
    law_id TEXT NOT NULL,
    source_locator TEXT NOT NULL,
    rung_days INTEGER NOT NULL,
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    first_started_at TEXT,
    last_attempt_at TEXT,
    completed_at TEXT,
    source_version TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, law_id, source_locator, rung_days, mode),
    CHECK (rung_days IN (1, 3, 7, 15, 30, 60)),
    CHECK (mode IN ('read', 'cloze', 'letters', 'type', 'recite', 'test')),
    CHECK (status IN ('in_progress', 'completed'))
);

CREATE INDEX IF NOT EXISTS user_playground_mode_progress_user_law
    ON user_playground_mode_progress (user_id, law_id, source_locator);

CREATE INDEX IF NOT EXISTS user_playground_progress_due
    ON user_playground_progress (user_id, next_revision, status);

CREATE INDEX IF NOT EXISTS user_playground_revision_mode_progress_user_law
    ON user_playground_revision_mode_progress (
        user_id, law_id, source_locator, rung_days
    );
"""

BACKFILL_CLOZE_SQL = """
INSERT INTO user_playground_mode_progress (
    user_id, law_id, source_locator, mode, status, attempt_count,
    first_started_at, last_attempt_at, completed_at,
    source_version, source_hash, created_at, updated_at
)
SELECT
    user_id,
    law_id,
    source_locator,
    'cloze',
    'completed',
    CASE WHEN times_completed < 1 THEN 1 ELSE times_completed END,
    COALESCE(updated_at, last_completed),
    COALESCE(updated_at, last_completed),
    COALESCE(last_completed, updated_at),
    source_version,
    source_hash,
    COALESCE(updated_at, last_completed),
    COALESCE(updated_at, last_completed)
FROM user_playground_progress
WHERE cloze_done != 0
ON CONFLICT (user_id, law_id, source_locator, mode) DO NOTHING;
"""


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}


def _ensure_progress_columns(conn: sqlite3.Connection) -> None:
    if "user_playground_progress" not in {
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }:
        return
    cols = _column_names(conn, "user_playground_progress")
    if "learned_at" not in cols:
        conn.execute("ALTER TABLE user_playground_progress ADD COLUMN learned_at TEXT")


def backfill_sqlite_cloze_mode_progress(conn: sqlite3.Connection) -> None:
    conn.execute(BACKFILL_CLOZE_SQL)
    conn.commit()


def ensure_sqlite_schema(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.executescript(SCHEMA_SQL)
    _ensure_progress_columns(conn)
    conn.commit()
    backfill_sqlite_cloze_mode_progress(conn)
