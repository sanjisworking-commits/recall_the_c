"""SQLite device registry tables. Overlay and subscription schemas are untouched."""

from __future__ import annotations

import sqlite3

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS user_device (
    id TEXT NOT NULL PRIMARY KEY,
    user_id TEXT NOT NULL,
    device_key_hash TEXT NOT NULL,
    platform TEXT NOT NULL
        CHECK (platform IN ('web', 'android')),
    display_name TEXT,
    first_registered_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    revoked_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (user_id, device_key_hash)
);

CREATE INDEX IF NOT EXISTS user_device_user
    ON user_device (user_id);

CREATE INDEX IF NOT EXISTS user_device_user_active
    ON user_device (user_id, revoked_at);

CREATE TABLE IF NOT EXISTS user_device_session (
    id TEXT NOT NULL PRIMARY KEY,
    user_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    auth_session_id TEXT NOT NULL,
    started_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    revoked_at TEXT,
    UNIQUE (user_id, auth_session_id),
    FOREIGN KEY (device_id) REFERENCES user_device(id)
);

CREATE INDEX IF NOT EXISTS user_device_session_device
    ON user_device_session (device_id);

CREATE INDEX IF NOT EXISTS user_device_session_user
    ON user_device_session (user_id);
"""


def ensure_sqlite_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.execute("PRAGMA busy_timeout = 8000")
    conn.commit()
