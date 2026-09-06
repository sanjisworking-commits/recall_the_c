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
    PRIMARY KEY (user_id, law_id, source_locator)
);
"""


def ensure_sqlite_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()
