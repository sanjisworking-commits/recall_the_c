"""SQLite device registry tables. Overlay and subscription schemas are untouched.

Postgres is the production migration authority (Alembic). SQLite files here are
ephemeral/dev/test databases: ``ensure_sqlite_schema`` creates the current
platform CHECK, and existing local files are rebuilt in place when the old
``web|android`` CHECK is still present. There is no separate production SQLite
migration chain.
"""

from __future__ import annotations

import sqlite3

_PLATFORM_CHECK = "CHECK (platform IN ('web', 'android', 'ios'))"

SCHEMA_SQL = f"""
CREATE TABLE IF NOT EXISTS user_device (
    id TEXT NOT NULL PRIMARY KEY,
    user_id TEXT NOT NULL,
    device_key_hash TEXT NOT NULL,
    platform TEXT NOT NULL
        {_PLATFORM_CHECK},
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

CREATE TABLE IF NOT EXISTS user_device_replacement (
    id TEXT NOT NULL PRIMARY KEY,
    user_id TEXT NOT NULL,
    revoked_device_id TEXT NOT NULL,
    replacement_device_id TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    platform TEXT,
    FOREIGN KEY (revoked_device_id) REFERENCES user_device(id),
    FOREIGN KEY (replacement_device_id) REFERENCES user_device(id)
);

CREATE INDEX IF NOT EXISTS user_device_replacement_user_occurred
    ON user_device_replacement (user_id, occurred_at);
"""


def _table_sql(conn: sqlite3.Connection, name: str) -> str | None:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
        (name,),
    ).fetchone()
    if row is None:
        return None
    if isinstance(row, sqlite3.Row):
        value = row["sql"]
    else:
        value = row[0]
    return str(value) if value is not None else None


def _ensure_ios_platform_check(conn: sqlite3.Connection) -> None:
    """Rebuild ``user_device`` when an older disposable SQLite CHECK is present."""

    sql = _table_sql(conn, "user_device")
    if not sql:
        return
    normalized = sql.lower().replace(" ", "")
    if "('web','android','ios')" in normalized:
        return
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.executescript(
        f"""
        CREATE TABLE user_device__ios (
            id TEXT NOT NULL PRIMARY KEY,
            user_id TEXT NOT NULL,
            device_key_hash TEXT NOT NULL,
            platform TEXT NOT NULL
                {_PLATFORM_CHECK},
            display_name TEXT,
            first_registered_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            revoked_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (user_id, device_key_hash)
        );
        INSERT INTO user_device__ios
            SELECT id, user_id, device_key_hash, platform, display_name,
                   first_registered_at, last_seen_at, revoked_at,
                   created_at, updated_at
            FROM user_device;
        DROP TABLE user_device;
        ALTER TABLE user_device__ios RENAME TO user_device;
        CREATE INDEX IF NOT EXISTS user_device_user
            ON user_device (user_id);
        CREATE INDEX IF NOT EXISTS user_device_user_active
            ON user_device (user_id, revoked_at);
        """
    )
    conn.execute("PRAGMA foreign_keys = ON")


def ensure_sqlite_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    _ensure_ios_platform_check(conn)
    conn.execute("PRAGMA busy_timeout = 8000")
    conn.commit()
