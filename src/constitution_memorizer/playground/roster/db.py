"""SQLite roster tables. Overlay schemas are unchanged.

Postgres is the production migration authority (Alembic). SQLite files here are
ephemeral/dev/test databases. Isolation is application-level ``user_id``.
"""

from __future__ import annotations

import sqlite3

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS user_playground_period (
    id TEXT NOT NULL PRIMARY KEY,
    user_id TEXT NOT NULL,
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    tier_snapshot TEXT,
    law_limit INTEGER,
    status TEXT NOT NULL
        CHECK (status IN ('draft', 'active', 'closed')),
    confirmed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (user_id, period_start)
);

CREATE INDEX IF NOT EXISTS user_playground_period_user
    ON user_playground_period (user_id);

CREATE TABLE IF NOT EXISTS user_playground_roster_item (
    id TEXT NOT NULL PRIMARY KEY,
    user_id TEXT NOT NULL,
    period_start TEXT NOT NULL,
    law_id TEXT NOT NULL,
    origin TEXT NOT NULL
        CHECK (origin IN ('new', 're_add', 'carry_forward')),
    carried_from_previous_period INTEGER NOT NULL DEFAULT 0,
    consumed_at TEXT,
    removed_at TEXT,
    declined_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (user_id, period_start, law_id)
);

CREATE INDEX IF NOT EXISTS user_playground_roster_item_user_period
    ON user_playground_roster_item (user_id, period_start);
"""


def ensure_sqlite_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    try:
        conn.execute("PRAGMA busy_timeout = 8000")
    except sqlite3.Error:
        pass
    conn.commit()
