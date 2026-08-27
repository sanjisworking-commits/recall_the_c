"""SQLite connection and schema for learning progress (user-scoped)."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from constitution_memorizer.progress.user_ids import LOCAL_USER_ID

logger = logging.getLogger(__name__)

# One-shot strict migration for the gated-completion model: rows written for
# these modes under the old visit-to-check model are unearned, so they are
# deleted at rollout ('card' is retired outright, never renamed to 'test').
_GATED_MODES_MARKER_KEY = "gated_modes_invalidated_v1"
_LEGACY_GATED_MODES = ("cloze", "type", "recite", "card")
# v2: Letters and Test were still auto-seen on GET after v1. Those visit
# rows are not proof of spoken Letters or a graded quiz.
_GATED_MODES_V2_MARKER_KEY = "gated_modes_invalidated_v2"
_LEGACY_AUTO_SEEN_GATED_MODES = ("letters", "test")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS learning_unit_progress (
    user_id TEXT NOT NULL,
    learning_unit_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new',
    times_completed INTEGER NOT NULL DEFAULT 0,
    last_completed TEXT,
    next_revision TEXT,
    interval_days INTEGER NOT NULL DEFAULT 0,
    ease_factor REAL NOT NULL DEFAULT 2.5,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, learning_unit_id)
);

CREATE TABLE IF NOT EXISTS split_preference (
    user_id TEXT NOT NULL,
    parent_clause_id TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('whole', 'letters')),
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, parent_clause_id)
);

CREATE TABLE IF NOT EXISTS article_gloss (
    user_id TEXT NOT NULL,
    article_number TEXT NOT NULL,
    text TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, article_number)
);

CREATE TABLE IF NOT EXISTS app_settings (
    user_id TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, key)
);

CREATE TABLE IF NOT EXISTS unit_modes_seen (
    user_id TEXT NOT NULL,
    learning_unit_id TEXT NOT NULL,
    mode TEXT NOT NULL,
    seen_at TEXT NOT NULL,
    PRIMARY KEY (user_id, learning_unit_id, mode)
);

CREATE TABLE IF NOT EXISTS user_free_articles (
    user_id TEXT NOT NULL,
    article_number TEXT NOT NULL,
    claimed_at TEXT NOT NULL,
    PRIMARY KEY (user_id, article_number)
);

CREATE TABLE IF NOT EXISTS user_profile (
    user_id TEXT PRIMARY KEY,
    display_name TEXT,
    avatar_url TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    email TEXT,
    phone TEXT,
    last_sign_in_at TEXT
);

CREATE TABLE IF NOT EXISTS user_roles (
    user_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin')),
    created_at TEXT NOT NULL,
    created_by TEXT,
    PRIMARY KEY (user_id, role)
);

CREATE TABLE IF NOT EXISTS access_grants (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'admin_grant'
        CHECK (source IN ('admin_grant', 'promotion', 'payment')),
    starts_at TEXT NOT NULL,
    ends_at TEXT,
    reason TEXT,
    granted_by TEXT,
    created_at TEXT NOT NULL,
    revoked_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_access_grants_user ON access_grants(user_id);

CREATE TABLE IF NOT EXISTS billing_orders (
    order_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    plan_days INTEGER NOT NULL,
    amount_paise INTEGER NOT NULL,
    currency TEXT NOT NULL DEFAULT 'INR',
    status TEXT NOT NULL DEFAULT 'created'
        CHECK (status IN ('created', 'paid')),
    razorpay_payment_id TEXT,
    created_at TEXT NOT NULL,
    paid_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_billing_orders_user ON billing_orders(user_id);

CREATE TABLE IF NOT EXISTS google_calendar_connections (
    user_id TEXT PRIMARY KEY,
    google_calendar_id TEXT,
    refresh_token_sealed TEXT,
    sync_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (sync_status IN ('ok', 'error', 'pending', 'disconnected')),
    sync_pending INTEGER NOT NULL DEFAULT 0,
    sync_requested_at TEXT,
    last_synced_at TEXT,
    last_error TEXT,
    connected_at TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS google_calendar_events (
    user_id TEXT NOT NULL,
    local_date TEXT NOT NULL,
    google_event_id TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    last_synced_at TEXT NOT NULL,
    PRIMARY KEY (user_id, local_date)
);

CREATE INDEX IF NOT EXISTS idx_gcal_events_user ON google_calendar_events(user_id);

CREATE TABLE IF NOT EXISTS admin_audit_log (
    id TEXT PRIMARY KEY,
    admin_user_id TEXT NOT NULL,
    action TEXT NOT NULL,
    target_user_id TEXT,
    target_type TEXT,
    target_id TEXT,
    before_state TEXT,
    after_state TEXT,
    reason TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_admin
    ON admin_audit_log(admin_user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_audit_target
    ON admin_audit_log(target_user_id, created_at);

CREATE TABLE IF NOT EXISTS app_session (
    session_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    access_token TEXT NOT NULL,
    refresh_token TEXT NOT NULL,
    csrf_token TEXT NOT NULL,
    display_name TEXT,
    email TEXT,
    phone TEXT,
    avatar_url TEXT,
    provider TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_progress_user
    ON learning_unit_progress(user_id);
CREATE INDEX IF NOT EXISTS idx_progress_user_next_revision
    ON learning_unit_progress(user_id, next_revision);
CREATE INDEX IF NOT EXISTS idx_progress_user_unit
    ON learning_unit_progress(user_id, learning_unit_id);
CREATE INDEX IF NOT EXISTS idx_modes_seen_user_unit
    ON unit_modes_seen(user_id, learning_unit_id);
CREATE INDEX IF NOT EXISTS idx_session_user
    ON app_session(user_id);

CREATE TABLE IF NOT EXISTS memory_entry (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    title TEXT NOT NULL,
    acronym TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    logged_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new',
    interval_days INTEGER NOT NULL DEFAULT 0,
    last_completed TEXT,
    next_revision TEXT,
    times_completed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memory_media (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    entry_id TEXT NOT NULL,
    storage_key TEXT NOT NULL,
    uploaded_at TEXT NOT NULL,
    UNIQUE(entry_id),
    FOREIGN KEY (entry_id) REFERENCES memory_entry(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_memory_user
    ON memory_entry(user_id);
CREATE INDEX IF NOT EXISTS idx_memory_user_created
    ON memory_entry(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_memory_user_next_revision
    ON memory_entry(user_id, next_revision);
CREATE INDEX IF NOT EXISTS idx_memory_media_user
    ON memory_media(user_id);

CREATE TABLE IF NOT EXISTS study_session (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    kind TEXT NOT NULL
        CHECK (kind IN ('revision', 'auto_learning', 'day_plan')),
    plan_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'complete')),
    created_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS study_session_item (
    session_id TEXT NOT NULL,
    learning_unit_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'completed', 'deferred')),
    completed_at TEXT,
    PRIMARY KEY (session_id, learning_unit_id),
    FOREIGN KEY (session_id) REFERENCES study_session(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_study_session_user_kind
    ON study_session(user_id, kind, status);
CREATE INDEX IF NOT EXISTS idx_study_session_item_order
    ON study_session_item(session_id, position);

CREATE TABLE IF NOT EXISTS user_learning_plan (
    user_id TEXT PRIMARY KEY,
    mode TEXT NOT NULL DEFAULT 'self_paced'
        CHECK (mode IN ('self_paced', 'auto')),
    daily_target INTEGER
        CHECK (daily_target IS NULL OR daily_target IN (3, 5, 7)),
    activated_at TEXT,
    prompt_dismissed_on TEXT,
    last_anchor_theme TEXT,
    target_effective_on TEXT,
    updated_at TEXT NOT NULL,
    CHECK (
        (mode = 'self_paced')
        OR (mode = 'auto' AND daily_target IS NOT NULL)
    )
);

CREATE TABLE IF NOT EXISTS auto_plan_day (
    user_id TEXT NOT NULL,
    plan_date TEXT NOT NULL,
    daily_target INTEGER NOT NULL CHECK (daily_target IN (3, 5, 7)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, plan_date)
);

CREATE TABLE IF NOT EXISTS auto_plan_item (
    user_id TEXT NOT NULL,
    plan_date TEXT NOT NULL,
    learning_unit_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (user_id, plan_date, learning_unit_id),
    UNIQUE (user_id, plan_date, position),
    FOREIGN KEY (user_id, plan_date)
        REFERENCES auto_plan_day(user_id, plan_date) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_auto_plan_item_user_date
    ON auto_plan_item(user_id, plan_date, position);
"""

# Pre-multiuser tables only: _migrate_legacy renames each of these aside,
# re-runs SCHEMA_SQL, copies the rows back under a user_id, then drops the
# renamed copy. A table that never existed before multiuser (study_session,
# study_session_item) must stay OUT of this list — SCHEMA_SQL's CREATE TABLE
# IF NOT EXISTS leaves it alone, whereas listing it would rename it away and
# drop it with no copy step to bring the rows back.
_LEGACY_TABLES = (
    "learning_unit_progress",
    "split_preference",
    "article_gloss",
    "app_settings",
    "unit_modes_seen",
    "memory_entry",
    "memory_media",
)


def connect(db_path: Path | str) -> sqlite3.Connection:
    """Open a SQLite connection with row factory and foreign keys on."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _column_names(conn: sqlite3.Connection, table: str) -> list[str]:
    if not _table_exists(conn, table):
        return []
    return [str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})")]


def _pk_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    info = conn.execute(f"PRAGMA table_info({table})").fetchall()
    ranked = [(int(row["pk"]), str(row["name"])) for row in info if row["pk"]]
    ranked.sort()
    return [name for _pk, name in ranked]


def _has_unique_on(conn: sqlite3.Connection, table: str, columns: list[str]) -> bool:
    if _pk_columns(conn, table) == columns:
        return True
    for index in conn.execute(f"PRAGMA index_list({table})").fetchall():
        if not index["unique"]:
            continue
        index_cols = [
            str(row["name"])
            for row in conn.execute(f"PRAGMA index_info({index['name']})").fetchall()
        ]
        if index_cols == columns:
            return True
    return False


def _legacy_schema(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='learning_unit_progress'"
    ).fetchone()
    if row is None or not row["sql"]:
        return False
    return "user_id" not in str(row["sql"])


def _migrate_legacy(conn: sqlite3.Connection) -> None:
    """One-time migrate pre-multiuser tables into user-scoped schema."""
    uid = str(LOCAL_USER_ID)
    conn.execute("PRAGMA foreign_keys = OFF")
    for name in _LEGACY_TABLES:
        if _table_exists(conn, name):
            conn.execute(f"ALTER TABLE {name} RENAME TO {name}_legacy")
    conn.executescript(SCHEMA_SQL)
    if _table_exists(conn, "learning_unit_progress_legacy"):
        conn.execute(
            f"""
            INSERT INTO learning_unit_progress (
                user_id, learning_unit_id, status, times_completed, last_completed,
                next_revision, interval_days, ease_factor, created_at, updated_at
            )
            SELECT '{uid}', learning_unit_id, status, times_completed, last_completed,
                   next_revision, interval_days, ease_factor, created_at, updated_at
            FROM learning_unit_progress_legacy
            """
        )
    if _table_exists(conn, "split_preference_legacy"):
        conn.execute(
            f"""
            INSERT INTO split_preference (user_id, parent_clause_id, mode, updated_at)
            SELECT '{uid}', parent_clause_id, mode, updated_at FROM split_preference_legacy
            """
        )
    if _table_exists(conn, "article_gloss_legacy"):
        conn.execute(
            f"""
            INSERT INTO article_gloss (user_id, article_number, text, updated_at)
            SELECT '{uid}', article_number, text, updated_at FROM article_gloss_legacy
            """
        )
    if _table_exists(conn, "app_settings_legacy"):
        conn.execute(
            f"""
            INSERT INTO app_settings (user_id, key, value, updated_at)
            SELECT '{uid}', key, value, updated_at FROM app_settings_legacy
            """
        )
    if _table_exists(conn, "unit_modes_seen_legacy"):
        conn.execute(
            f"""
            INSERT INTO unit_modes_seen (user_id, learning_unit_id, mode, seen_at)
            SELECT '{uid}', learning_unit_id, mode, seen_at FROM unit_modes_seen_legacy
            """
        )
    if _table_exists(conn, "memory_entry_legacy"):
        conn.execute(
            f"""
            INSERT INTO memory_entry (
                id, user_id, title, acronym, notes, logged_date, status, interval_days,
                last_completed, next_revision, times_completed, created_at, updated_at
            )
            SELECT id, '{uid}', title, acronym, notes, logged_date, status, interval_days,
                   last_completed, next_revision, times_completed, created_at, updated_at
            FROM memory_entry_legacy
            """
        )
    if _table_exists(conn, "memory_media_legacy"):
        cols = _column_names(conn, "memory_media_legacy")
        path_sql = "storage_key" if "storage_key" in cols else "path"
        if "path" in cols and "storage_key" in cols:
            path_sql = "COALESCE(NULLIF(storage_key, ''), path)"
        conn.execute(
            f"""
            INSERT INTO memory_media (id, user_id, entry_id, storage_key, uploaded_at)
            SELECT entry_id, '{uid}', entry_id, {path_sql}, uploaded_at
            FROM memory_media_legacy
            """
        )
    for name in _LEGACY_TABLES:
        conn.execute(f"DROP TABLE IF EXISTS {name}_legacy")
    conn.execute("PRAGMA foreign_keys = ON")
    # Must run before this function's own commit — init_db returns right
    # after _migrate_legacy, so a later call would be left uncommitted.
    _invalidate_legacy_gated_modes(conn)
    _invalidate_legacy_letters_test_auto_seen(conn)
    _migrate_ladder_day15(conn)
    conn.commit()


_LADDER_DAY15_MARKER_KEY = "ladder_day15_migrated_v1"


def _migrate_ladder_day15(conn: sqlite3.Connection) -> None:
    """Re-slot interval_days 14 → 15 (idempotent, one-shot).

    The Constitution ladder's fourth rung was corrected from Day 14 to Day 15.
    Without this, ``advance_interval(14)`` would round a unit UP to the new 15
    rung — repeating the two-week interval instead of advancing to 30. Stored
    ``next_revision`` dates are deliberately untouched: already-scheduled
    reviews keep their dates. Postgres gets the same UPDATE via alembic.
    """
    marker = conn.execute(
        "SELECT 1 FROM app_settings WHERE user_id = ? AND key = ?",
        (str(LOCAL_USER_ID), _LADDER_DAY15_MARKER_KEY),
    ).fetchone()
    if marker is not None:
        return
    conn.execute(
        "UPDATE learning_unit_progress SET interval_days = 15 WHERE interval_days = 14"
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO app_settings (user_id, key, value, updated_at)
        VALUES (?, ?, '1', ?)
        """,
        (
            str(LOCAL_USER_ID),
            _LADDER_DAY15_MARKER_KEY,
            datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        ),
    )
    logger.info("Re-slotted interval_days 14 -> 15 (ladder day-15 correction)")


def _invalidate_legacy_gated_modes(conn: sqlite3.Connection) -> None:
    """Delete pre-gating cloze/type/recite/card marks (idempotent, one-shot).

    unit_modes_seen is current-cycle state, so this only touches cycles in
    progress at rollout; a marker row keeps reruns from wiping marks earned
    under the new gates. Postgres gets the same DELETE via alembic.
    """
    marker = conn.execute(
        "SELECT 1 FROM app_settings WHERE user_id = ? AND key = ?",
        (str(LOCAL_USER_ID), _GATED_MODES_MARKER_KEY),
    ).fetchone()
    if marker is not None:
        return
    placeholders = ", ".join("?" for _ in _LEGACY_GATED_MODES)
    conn.execute(
        f"DELETE FROM unit_modes_seen WHERE mode IN ({placeholders})",
        _LEGACY_GATED_MODES,
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO app_settings (user_id, key, value, updated_at)
        VALUES (?, ?, '1', ?)
        """,
        (
            str(LOCAL_USER_ID),
            _GATED_MODES_MARKER_KEY,
            datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        ),
    )
    logger.info("Invalidated legacy gated-mode seen rows (strict migration)")


def _invalidate_legacy_letters_test_auto_seen(conn: sqlite3.Connection) -> None:
    """Delete visit-generated letters/test marks (idempotent, one-shot).

    After v1, Letters and Test were still auto-seen on GET. Spoken Letters
    and /quiz-only Test must not inherit those rows. A v2 marker keeps
    reruns from wiping marks earned under the new gates.
    """
    marker = conn.execute(
        "SELECT 1 FROM app_settings WHERE user_id = ? AND key = ?",
        (str(LOCAL_USER_ID), _GATED_MODES_V2_MARKER_KEY),
    ).fetchone()
    if marker is not None:
        return
    placeholders = ", ".join("?" for _ in _LEGACY_AUTO_SEEN_GATED_MODES)
    conn.execute(
        f"DELETE FROM unit_modes_seen WHERE mode IN ({placeholders})",
        _LEGACY_AUTO_SEEN_GATED_MODES,
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO app_settings (user_id, key, value, updated_at)
        VALUES (?, ?, '1', ?)
        """,
        (
            str(LOCAL_USER_ID),
            _GATED_MODES_V2_MARKER_KEY,
            datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        ),
    )
    logger.info("Invalidated legacy letters/test auto-seen rows (v2)")


def _rebuild_unit_modes_seen(conn: sqlite3.Connection) -> None:
    uid = str(LOCAL_USER_ID)
    cols = _column_names(conn, "unit_modes_seen")
    has_user = "user_id" in cols
    conn.execute("DROP INDEX IF EXISTS idx_modes_seen_unit")
    conn.execute("DROP INDEX IF EXISTS idx_modes_seen_user_unit")
    conn.execute(
        """
        CREATE TABLE unit_modes_seen_new (
            user_id TEXT NOT NULL,
            learning_unit_id TEXT NOT NULL,
            mode TEXT NOT NULL,
            seen_at TEXT NOT NULL,
            PRIMARY KEY (user_id, learning_unit_id, mode)
        )
        """
    )
    if has_user:
        conn.execute(
            """
            INSERT OR REPLACE INTO unit_modes_seen_new
                (user_id, learning_unit_id, mode, seen_at)
            SELECT user_id, learning_unit_id, mode, MAX(seen_at)
            FROM unit_modes_seen
            GROUP BY user_id, learning_unit_id, mode
            """
        )
    else:
        conn.execute(
            f"""
            INSERT OR REPLACE INTO unit_modes_seen_new
                (user_id, learning_unit_id, mode, seen_at)
            SELECT '{uid}', learning_unit_id, mode, MAX(seen_at)
            FROM unit_modes_seen
            GROUP BY learning_unit_id, mode
            """
        )
    conn.execute("DROP TABLE unit_modes_seen")
    conn.execute("ALTER TABLE unit_modes_seen_new RENAME TO unit_modes_seen")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_modes_seen_user_unit "
        "ON unit_modes_seen(user_id, learning_unit_id)"
    )


def _rebuild_app_settings(conn: sqlite3.Connection) -> None:
    uid = str(LOCAL_USER_ID)
    cols = _column_names(conn, "app_settings")
    has_user = "user_id" in cols
    conn.execute(
        """
        CREATE TABLE app_settings_new (
            user_id TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (user_id, key)
        )
        """
    )
    if has_user:
        conn.execute(
            """
            INSERT OR REPLACE INTO app_settings_new (user_id, key, value, updated_at)
            SELECT user_id, key, value, updated_at
            FROM app_settings
            WHERE rowid IN (
                SELECT MAX(rowid) FROM app_settings GROUP BY user_id, key
            )
            """
        )
    else:
        conn.execute(
            f"""
            INSERT OR REPLACE INTO app_settings_new (user_id, key, value, updated_at)
            SELECT '{uid}', key, value, updated_at
            FROM app_settings
            WHERE rowid IN (SELECT MAX(rowid) FROM app_settings GROUP BY key)
            """
        )
    conn.execute("DROP TABLE app_settings")
    conn.execute("ALTER TABLE app_settings_new RENAME TO app_settings")


def _ensure_profile_identity_columns(conn: sqlite3.Connection) -> None:
    """Add email/phone/last_sign_in_at to pre-0006 user_profile tables.

    CREATE TABLE IF NOT EXISTS never alters an existing table, so local DBs
    created before the admin foundation need the columns added in place.
    """
    cols = _column_names(conn, "user_profile")
    if not cols:
        return
    for column in ("email", "phone", "last_sign_in_at"):
        if column not in cols:
            conn.execute(f"ALTER TABLE user_profile ADD COLUMN {column} TEXT")


def _repair_partial_legacy(conn: sqlite3.Connection) -> None:
    """Fix 8001 tables that exist without user_id or without a PRIMARY KEY.

    ``CREATE TABLE IF NOT EXISTS`` never alters those older shapes, so Done /
    mark_mode_seen upserts 500 until they match the user-scoped schema.
    """
    if _table_exists(conn, "unit_modes_seen") and (
        "user_id" not in _column_names(conn, "unit_modes_seen")
        or not _has_unique_on(
            conn, "unit_modes_seen", ["user_id", "learning_unit_id", "mode"]
        )
    ):
        _rebuild_unit_modes_seen(conn)
        logger.info("Rebuilt unit_modes_seen into user-scoped schema")
    if _table_exists(conn, "app_settings") and (
        "user_id" not in _column_names(conn, "app_settings")
        or not _has_unique_on(conn, "app_settings", ["user_id", "key"])
    ):
        _rebuild_app_settings(conn)
        logger.info("Rebuilt app_settings into user-scoped schema")
    _widen_access_grants_sources(conn)


def _widen_access_grants_sources(conn: sqlite3.Connection) -> None:
    """Rebuild access_grants whose CHECK predates the 'payment' source.

    SQLite cannot ALTER a CHECK constraint, and CREATE TABLE IF NOT EXISTS
    never touches the existing shape — without this, the first verified
    Razorpay payment would fail its grant INSERT. Idempotent: detected via
    the stored DDL.
    """
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='access_grants'"
    ).fetchone()
    if row is None or "'payment'" in str(row["sql"]):
        return
    conn.execute("DROP INDEX IF EXISTS idx_access_grants_user")
    conn.execute("ALTER TABLE access_grants RENAME TO access_grants_old")
    conn.execute(
        """
        CREATE TABLE access_grants (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'admin_grant'
                CHECK (source IN ('admin_grant', 'promotion', 'payment')),
            starts_at TEXT NOT NULL,
            ends_at TEXT,
            reason TEXT,
            granted_by TEXT,
            created_at TEXT NOT NULL,
            revoked_at TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO access_grants
        SELECT id, user_id, source, starts_at, ends_at, reason, granted_by,
               created_at, revoked_at
        FROM access_grants_old
        """
    )
    conn.execute("DROP TABLE access_grants_old")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_access_grants_user ON access_grants(user_id)"
    )
    logger.info("Widened access_grants sources to include 'payment'")


def _dedupe_study_sessions(conn: sqlite3.Connection) -> None:
    """Keep the oldest session per (user_id, kind, plan_date) so the unique index can land."""
    if not _table_exists(conn, "study_session"):
        return
    conn.execute(
        """
        DELETE FROM study_session_item
        WHERE session_id IN (
            SELECT s.id
            FROM study_session s
            WHERE EXISTS (
                SELECT 1
                FROM study_session k
                WHERE k.user_id = s.user_id
                  AND k.kind = s.kind
                  AND k.plan_date = s.plan_date
                  AND (
                      k.created_at < s.created_at
                      OR (k.created_at = s.created_at AND k.id < s.id)
                  )
            )
        )
        """
    )
    conn.execute(
        """
        DELETE FROM study_session
        WHERE id IN (
            SELECT s.id
            FROM study_session s
            WHERE EXISTS (
                SELECT 1
                FROM study_session k
                WHERE k.user_id = s.user_id
                  AND k.kind = s.kind
                  AND k.plan_date = s.plan_date
                  AND (
                      k.created_at < s.created_at
                      OR (k.created_at = s.created_at AND k.id < s.id)
                  )
            )
        )
        """
    )


def _ensure_study_session_day_unique(conn: sqlite3.Connection) -> None:
    """CREATE TABLE IF NOT EXISTS never adds a unique index to an existing table."""
    if not _table_exists(conn, "study_session"):
        return
    _dedupe_study_sessions(conn)
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_study_session_user_kind_date
            ON study_session(user_id, kind, plan_date)
        """
    )


def _ensure_auto_plan_tables(conn: sqlite3.Connection) -> None:
    """Add target_effective_on and auto_plan_* tables to existing local DBs.

    ``CREATE TABLE IF NOT EXISTS`` never alters ``user_learning_plan``, so the
    audit column has to be added in place the same way as profile identity.
    """
    cols = _column_names(conn, "user_learning_plan")
    if cols and "target_effective_on" not in cols:
        conn.execute(
            "ALTER TABLE user_learning_plan ADD COLUMN target_effective_on TEXT"
        )
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS auto_plan_day (
            user_id TEXT NOT NULL,
            plan_date TEXT NOT NULL,
            daily_target INTEGER NOT NULL CHECK (daily_target IN (3, 5, 7)),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (user_id, plan_date)
        );
        CREATE TABLE IF NOT EXISTS auto_plan_item (
            user_id TEXT NOT NULL,
            plan_date TEXT NOT NULL,
            learning_unit_id TEXT NOT NULL,
            position INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (user_id, plan_date, learning_unit_id),
            UNIQUE (user_id, plan_date, position),
            FOREIGN KEY (user_id, plan_date)
                REFERENCES auto_plan_day(user_id, plan_date) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_auto_plan_item_user_date
            ON auto_plan_item(user_id, plan_date, position);
        """
    )


def init_db(conn: sqlite3.Connection) -> None:
    """Create progress tables if missing; migrate legacy single-user schema."""
    if _legacy_schema(conn):
        _migrate_legacy(conn)
        _ensure_study_session_day_unique(conn)
        _ensure_auto_plan_tables(conn)
        conn.commit()
        return
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        _repair_partial_legacy(conn)
        _ensure_profile_identity_columns(conn)
        conn.executescript(SCHEMA_SQL)
        _ensure_study_session_day_unique(conn)
        _ensure_auto_plan_tables(conn)
        _invalidate_legacy_gated_modes(conn)
        _invalidate_legacy_letters_test_auto_seen(conn)
        _migrate_ladder_day15(conn)
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
    conn.commit()


def open_progress_db(db_path: Path | str) -> sqlite3.Connection:
    """Connect and ensure schema exists."""
    conn = connect(db_path)
    init_db(conn)
    return conn
