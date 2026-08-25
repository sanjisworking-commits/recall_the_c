"""Upgrade older local progress.db tables onto the user-scoped schema."""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from constitution_memorizer.learning.schemas import LearningUnit, LearningUnitType
from constitution_memorizer.progress.db import open_progress_db
from constitution_memorizer.progress.repository import ProgressRepository
from constitution_memorizer.progress.scheduler import ReminderEngine
from constitution_memorizer.progress.user_ids import LOCAL_USER_ID

UID = str(LOCAL_USER_ID)


def _legacy_modes_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE unit_modes_seen (
            learning_unit_id TEXT NOT NULL,
            mode TEXT NOT NULL,
            seen_at TEXT NOT NULL
        );
        CREATE TABLE app_settings (
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        INSERT INTO unit_modes_seen VALUES
            ('article-138-clause-2', 'read', '2026-08-05T05:57:54+00:00'),
            ('article-38-clause-1', 'read', '2026-08-07T03:51:57+00:00');
        INSERT INTO app_settings VALUES
            ('theme', 'light', '2026-08-01T00:00:00+00:00'),
            ('theme', 'light', '2026-08-02T00:00:00+00:00');
        """
    )
    conn.commit()
    conn.close()


def test_open_upgrades_legacy_modes_seen_and_settings(tmp_path: Path):
    db = tmp_path / "progress.db"
    _legacy_modes_db(db)

    conn = open_progress_db(db)
    modes_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name = 'unit_modes_seen'"
    ).fetchone()[0]
    assert "PRIMARY KEY" in modes_sql
    assert "user_id" in modes_sql
    settings_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name = 'app_settings'"
    ).fetchone()[0]
    assert "PRIMARY KEY" in settings_sql
    assert "user_id" in settings_sql

    rows = conn.execute(
        "SELECT user_id, learning_unit_id, mode FROM unit_modes_seen ORDER BY 2, 3"
    ).fetchall()
    assert [tuple(r) for r in rows] == [
        (UID, "article-138-clause-2", "read"),
        (UID, "article-38-clause-1", "read"),
    ]
    themes = conn.execute(
        "SELECT COUNT(*) FROM app_settings WHERE key = 'theme'"
    ).fetchone()[0]
    assert themes == 1

    repo = ProgressRepository(conn)
    seen = repo.mark_mode_seen(UID, "article-138-clause-2", "read")
    assert "read" in seen
    seen = repo.mark_mode_seen(UID, "article-138-clause-2", "cloze")
    assert seen == {"read", "cloze"}
    repo.set_setting(UID, "theme", "dark")
    assert repo.get_setting(UID, "theme") == "dark"


def test_fresh_db_mark_mode_seen_is_idempotent(tmp_path: Path):
    repo = ProgressRepository(open_progress_db(tmp_path / "fresh.db"))
    assert repo.mark_mode_seen(UID, "article-2", "read") == {"read"}
    assert repo.mark_mode_seen(UID, "article-2", "read") == {"read"}


def _legacy_progress_db(path: Path) -> None:
    """Pre-multiuser 8001 shape: no user_id columns."""
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE learning_unit_progress (
            learning_unit_id TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'new',
            times_completed INTEGER NOT NULL DEFAULT 0,
            last_completed TEXT,
            next_revision TEXT,
            interval_days INTEGER NOT NULL DEFAULT 0,
            ease_factor REAL NOT NULL DEFAULT 2.5,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE unit_modes_seen (
            learning_unit_id TEXT NOT NULL,
            mode TEXT NOT NULL,
            seen_at TEXT NOT NULL,
            PRIMARY KEY (learning_unit_id, mode)
        );
        CREATE TABLE app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE split_preference (
            parent_clause_id TEXT PRIMARY KEY,
            mode TEXT NOT NULL CHECK (mode IN ('whole', 'letters')),
            updated_at TEXT NOT NULL
        );
        CREATE TABLE article_gloss (
            article_number TEXT PRIMARY KEY,
            text TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE memory_entry (
            id TEXT PRIMARY KEY,
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
        CREATE TABLE memory_media (
            entry_id TEXT PRIMARY KEY,
            path TEXT NOT NULL,
            uploaded_at TEXT NOT NULL
        );
        INSERT INTO learning_unit_progress VALUES
            ('article-1-clause-1', 'review', 1, '2026-08-08', '2026-08-09',
             1, 2.5, '2026-08-08T00:00:00+00:00', '2026-08-08T00:00:00+00:00');
        INSERT INTO unit_modes_seen VALUES
            ('article-1-clause-1', 'read', '2026-08-08T00:00:00+00:00');
        INSERT INTO app_settings VALUES
            ('theme', 'light', '2026-08-08T00:00:00+00:00');
        INSERT INTO split_preference VALUES
            ('article-19-clause-1', 'letters', '2026-08-08T00:00:00+00:00');
        INSERT INTO article_gloss VALUES
            ('1', 'notes', '2026-08-08T00:00:00+00:00');
        INSERT INTO memory_entry VALUES
            ('mem-abc', 'Acronym', 'ABC', '', '2026-08-08', 'new', 0,
             NULL, NULL, 0, '2026-08-08T00:00:00+00:00', '2026-08-08T00:00:00+00:00');
        INSERT INTO memory_media VALUES
            ('mem-abc', 'memory/mem-abc.jpg', '2026-08-08T00:00:00+00:00');
        """
    )
    conn.commit()
    conn.close()


def test_open_migrates_legacy_sqlite_to_local_user(tmp_path: Path):
    db = tmp_path / "progress.db"
    _legacy_progress_db(db)

    conn = open_progress_db(db)
    progress_cols = [
        row["name"]
        for row in conn.execute("PRAGMA table_info(learning_unit_progress)")
    ]
    assert "user_id" in progress_cols
    kept = conn.execute(
        """
        SELECT user_id, status, times_completed, next_revision
        FROM learning_unit_progress
        WHERE learning_unit_id = 'article-1-clause-1'
        """
    ).fetchone()
    assert kept is not None
    assert kept["user_id"] == UID
    assert kept["status"] == "review"
    assert kept["times_completed"] == 1
    assert kept["next_revision"] == "2026-08-09"
    assert conn.execute(
        "SELECT mode FROM split_preference WHERE parent_clause_id = 'article-19-clause-1'"
    ).fetchone()[0] == "letters"
    assert conn.execute(
        "SELECT text FROM article_gloss WHERE article_number = '1'"
    ).fetchone()[0] == "notes"
    assert conn.execute(
        "SELECT storage_key FROM memory_media WHERE entry_id = 'mem-abc'"
    ).fetchone()[0] == "memory/mem-abc.jpg"

    repo = ProgressRepository(conn)
    created = repo.ensure_progress(UID, "article-2")
    assert created.learning_unit_id == "article-2"
    assert created.status == "new"
    seen = repo.mark_mode_seen(UID, "article-1-clause-1", "cloze")
    assert seen == {"read", "cloze"}
    repo.set_setting(UID, "theme", "dark")
    assert repo.get_setting(UID, "theme") == "dark"


def test_open_keeps_rows_for_distinct_users(tmp_path: Path):
    db = tmp_path / "progress.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE learning_unit_progress (
            user_id TEXT NOT NULL,
            learning_unit_id TEXT NOT NULL,
            status TEXT NOT NULL,
            times_completed INTEGER NOT NULL,
            last_completed TEXT,
            next_revision TEXT,
            interval_days INTEGER NOT NULL,
            ease_factor REAL NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (user_id, learning_unit_id)
        );
        INSERT INTO learning_unit_progress VALUES
            ('user-a', 'article-2', 'review', 1, '2026-08-01', '2026-08-02',
             1, 2.5, '2026-08-01T00:00:00+00:00', '2026-08-01T00:00:00+00:00'),
            ('user-b', 'article-2', 'review', 3, '2026-08-10', '2026-08-11',
             3, 2.5, '2026-08-10T00:00:00+00:00', '2026-08-10T00:00:00+00:00');
        """
    )
    conn.commit()
    conn.close()

    opened = open_progress_db(db)
    rows = opened.execute(
        """
        SELECT user_id, times_completed FROM learning_unit_progress
        WHERE learning_unit_id = 'article-2' ORDER BY user_id
        """
    ).fetchall()
    assert [(r["user_id"], r["times_completed"]) for r in rows] == [
        ("user-a", 1),
        ("user-b", 3),
    ]


def test_mark_done_after_legacy_sqlite_migrate(tmp_path: Path):
    db = tmp_path / "progress.db"
    _legacy_progress_db(db)
    unit = LearningUnit(
        id="article-2",
        type=LearningUnitType.ARTICLE,
        display_title="Article 2",
        text="Name and territory of the Union.",
        estimated_learning_time=30,
        revision_order=1,
    )
    engine = ReminderEngine.from_units(db, [unit])
    engine.mark_all_modes_seen("article-2")
    result = engine.mark_done("article-2", as_of=date(2026, 8, 13))
    assert result.progress.status == "review"
    assert result.progress.times_completed == 1


def _pre_gating_db(path: Path) -> None:
    """Current user-scoped schema, but rows written under visit-to-check
    (including a 'card' row) and no invalidation marker yet."""
    from constitution_memorizer.progress.db import SCHEMA_SQL

    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA_SQL)
    conn.executemany(
        "INSERT INTO unit_modes_seen VALUES (?, ?, ?, '2026-08-10T00:00:00+00:00')",
        [
            (UID, "article-1", mode)
            for mode in ("read", "cloze", "letters", "type", "recite", "card")
        ],
    )
    conn.commit()
    conn.close()


def _modes_for(conn: sqlite3.Connection, unit_id: str) -> set[str]:
    return {
        row[0]
        for row in conn.execute(
            "SELECT mode FROM unit_modes_seen WHERE user_id = ? AND learning_unit_id = ?",
            (UID, unit_id),
        )
    }


def test_open_invalidates_legacy_gated_modes(tmp_path: Path):
    db = tmp_path / "progress.db"
    _pre_gating_db(db)

    conn = open_progress_db(db)
    # v1 wipes cloze/type/recite/card; v2 wipes visit-generated letters/test.
    assert _modes_for(conn, "article-1") == {"read"}
    conn.close()


def test_invalidation_marker_preserves_new_gated_marks(tmp_path: Path):
    db = tmp_path / "progress.db"
    _pre_gating_db(db)

    conn = open_progress_db(db)
    repo = ProgressRepository(conn)
    repo.mark_mode_seen(UID, "article-1", "cloze")
    repo.mark_mode_seen(UID, "article-1", "letters")
    repo.mark_mode_seen(UID, "article-1", "test")
    conn.close()

    conn = open_progress_db(db)
    assert _modes_for(conn, "article-1") == {"read", "cloze", "letters", "test"}
    conn.close()


def test_invalidation_helper_is_idempotent(tmp_path: Path):
    from constitution_memorizer.progress.db import (
        _invalidate_legacy_gated_modes,
        _invalidate_legacy_letters_test_auto_seen,
    )

    db = tmp_path / "progress.db"
    _pre_gating_db(db)

    conn = open_progress_db(db)
    _invalidate_legacy_gated_modes(conn)
    _invalidate_legacy_gated_modes(conn)
    _invalidate_legacy_letters_test_auto_seen(conn)
    _invalidate_legacy_letters_test_auto_seen(conn)
    assert _modes_for(conn, "article-1") == {"read"}
    conn.close()


def test_v2_wipes_letters_and_test_keeps_earned_gated(tmp_path: Path):
    """v1 already applied; leftover visit-generated letters/test must still go."""
    from constitution_memorizer.progress.db import (
        SCHEMA_SQL,
        _GATED_MODES_MARKER_KEY,
    )

    db = tmp_path / "progress.db"
    conn = sqlite3.connect(db)
    conn.executescript(SCHEMA_SQL)
    conn.executemany(
        "INSERT INTO unit_modes_seen VALUES (?, ?, ?, '2026-08-10T00:00:00+00:00')",
        [
            (UID, "article-1", mode)
            for mode in ("read", "cloze", "letters", "type", "recite", "test")
        ],
    )
    conn.execute(
        "INSERT INTO app_settings VALUES (?, ?, '1', '2026-08-10T00:00:00+00:00')",
        (UID, _GATED_MODES_MARKER_KEY),
    )
    conn.commit()
    conn.close()

    conn = open_progress_db(db)
    assert _modes_for(conn, "article-1") == {"read", "cloze", "type", "recite"}
    conn.close()


def test_legacy_migrate_path_also_invalidates(tmp_path: Path):
    """Pre-multiuser DB (no user_id anywhere): migrate + strict invalidation."""
    db = tmp_path / "progress.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE learning_unit_progress (
            learning_unit_id TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'new',
            times_completed INTEGER NOT NULL DEFAULT 0,
            last_completed TEXT,
            next_revision TEXT,
            interval_days INTEGER NOT NULL DEFAULT 0,
            ease_factor REAL NOT NULL DEFAULT 2.5,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE unit_modes_seen (
            learning_unit_id TEXT NOT NULL,
            mode TEXT NOT NULL,
            seen_at TEXT NOT NULL
        );
        INSERT INTO unit_modes_seen VALUES
            ('article-1', 'read', '2026-08-10T00:00:00+00:00'),
            ('article-1', 'card', '2026-08-10T00:00:00+00:00'),
            ('article-1', 'recite', '2026-08-10T00:00:00+00:00');
        """
    )
    conn.commit()
    conn.close()

    conn = open_progress_db(db)
    assert _modes_for(conn, "article-1") == {"read"}
    conn.close()


def test_ladder_day15_reslots_interval_14(tmp_path: Path) -> None:
    """One-shot ladder correction: interval_days 14 → 15, dates untouched."""
    db = tmp_path / "progress.db"
    conn = open_progress_db(db)
    conn.execute(
        """
        INSERT INTO learning_unit_progress (
            user_id, learning_unit_id, status, times_completed, last_completed,
            next_revision, interval_days, ease_factor, created_at, updated_at
        )
        VALUES (?, 'clause-14', 'review', 4, '2026-08-10', '2026-08-24', 14, 2.5,
                '2026-08-01T00:00:00+00:00', '2026-08-10T00:00:00+00:00')
        """,
        (UID,),
    )
    # Simulate a pre-correction DB: clear the marker written at first open.
    conn.execute(
        "DELETE FROM app_settings WHERE user_id = ? AND key = 'ladder_day15_migrated_v1'",
        (UID,),
    )
    conn.commit()
    conn.close()

    conn = open_progress_db(db)
    row = conn.execute(
        "SELECT interval_days, next_revision FROM learning_unit_progress "
        "WHERE learning_unit_id = 'clause-14'"
    ).fetchone()
    assert int(row["interval_days"]) == 15
    assert str(row["next_revision"]) == "2026-08-24"  # scheduled date NOT shifted

    # Idempotent: a fresh 14 written AFTER the marker is user state, not legacy —
    # reopening must not touch it.
    conn.execute(
        "UPDATE learning_unit_progress SET interval_days = 14 "
        "WHERE learning_unit_id = 'clause-14'"
    )
    conn.commit()
    conn.close()
    conn = open_progress_db(db)
    row = conn.execute(
        "SELECT interval_days FROM learning_unit_progress "
        "WHERE learning_unit_id = 'clause-14'"
    ).fetchone()
    assert int(row["interval_days"]) == 14
    conn.close()


def test_fresh_db_creates_learning_plan_and_session_tables(tmp_path: Path):
    conn = open_progress_db(tmp_path / "fresh.db")
    names = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    assert "user_learning_plan" in names
    assert "study_session" in names
    assert "study_session_item" in names
    item_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name = 'study_session_item'"
    ).fetchone()[0]
    assert "pending" in item_sql
    assert "deferred" in item_sql
    conn.close()
