"""PostgreSQL implementations of user-scoped progress/memory repositories."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import ExitStack, contextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterator
from uuid import UUID

from constitution_memorizer.progress.repository import (
    DEFAULT_NEWS_ARTICLES,
    DEFAULT_NOTIFICATION_FREQUENCY,
    DEFAULT_THEME,
    LEARN_MODES_SET,
    NEWS_ARTICLES_KEY,
    NOTIFICATION_FREQUENCY_KEY,
    NOTIFICATION_LAST_SLOT_KEY,
    THEME_KEY,
    VALID_DAILY_TARGETS,
    VALID_NOTIFICATION_FREQUENCIES,
    VALID_THEMES,
    AccountBootstrap,
    AutoPlanDay,
    AutoPlanItem,
    AutoPlanSnapshot,
    BillingOrder,
    CompletionProgress,
    CompletionState,
    LearningPlanMode,
    PlannerReadBundle,
    UserLearningPlan,
    _auto_plan_days_from_rows,
    _billing_order_from_row,
    _date_iso,
    _effective_on_for_upsert,
    _modes_by_unit_from_rows,
    _news_from_raw,
    _row_to_learning_plan,
    _sessions_by_kind_for_day,
    _sessions_from_joined_rows,
    _theme_from_raw,
    NotificationFrequency,
    ProgressRecord,
    ProgressStatus,
    RequestBootstrap,
    SplitMode,
    StudyItemStatus,
    StudySession,
    StudySessionKind,
    ThemePreference,
    _STUDY_SESSION_COLUMNS,
    _study_session_from_rows,
)
from constitution_memorizer.progress.user_ids import as_user_id


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _row_progress(row: Any) -> ProgressRecord:
    return ProgressRecord(
        learning_unit_id=row["learning_unit_id"],
        status=row["status"],
        times_completed=int(row["times_completed"]),
        last_completed=row["last_completed"],
        next_revision=row["next_revision"],
        interval_days=int(row["interval_days"]),
        ease_factor=float(row["ease_factor"]),
        created_at=row["created_at"].isoformat()
        if hasattr(row["created_at"], "isoformat")
        else str(row["created_at"]),
        updated_at=row["updated_at"].isoformat()
        if hasattr(row["updated_at"], "isoformat")
        else str(row["updated_at"]),
    )


def _pg_write_auto_plan_days(cur: Any, uid: Any, days: Sequence[AutoPlanDay], *, now: datetime) -> None:
    for day in days:
        cur.execute(
            """
            INSERT INTO auto_plan_day (
                user_id, plan_date, daily_target, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id, plan_date) DO UPDATE SET
                daily_target = EXCLUDED.daily_target,
                updated_at = EXCLUDED.updated_at
            """,
            (uid, day.plan_date, int(day.daily_target), now, now),
        )
        cur.execute(
            "DELETE FROM auto_plan_item WHERE user_id = %s AND plan_date = %s",
            (uid, day.plan_date),
        )
        for item in day.items:
            cur.execute(
                """
                INSERT INTO auto_plan_item (
                    user_id, plan_date, learning_unit_id, position, created_at
                ) VALUES (%s, %s, %s, %s, %s)
                """,
                (uid, day.plan_date, item.learning_unit_id, int(item.position), now),
            )


def _pg_clear_auto_plan_from(cur: Any, uid: Any, as_of: date) -> None:
    cur.execute(
        "DELETE FROM auto_plan_item WHERE user_id = %s AND plan_date >= %s",
        (uid, as_of),
    )
    cur.execute(
        "DELETE FROM auto_plan_day WHERE user_id = %s AND plan_date >= %s",
        (uid, as_of),
    )


def _pg_delete_auto_plan_after(cur: Any, uid: Any, horizon: date) -> None:
    cur.execute(
        "DELETE FROM auto_plan_item WHERE user_id = %s AND plan_date > %s",
        (uid, horizon),
    )
    cur.execute(
        "DELETE FROM auto_plan_day WHERE user_id = %s AND plan_date > %s",
        (uid, horizon),
    )


def _pg_replace_auto_plan_window(
    cur: Any,
    uid: Any,
    as_of: date,
    horizon: date,
    days: Sequence[AutoPlanDay],
) -> None:
    for day in days:
        if day.plan_date < as_of:
            raise ValueError("cannot write auto_plan_date before as_of")
    cur.execute(
        """
        DELETE FROM auto_plan_item
        WHERE user_id = %s AND plan_date >= %s AND plan_date <= %s
        """,
        (uid, as_of, horizon),
    )
    cur.execute(
        """
        DELETE FROM auto_plan_day
        WHERE user_id = %s AND plan_date >= %s AND plan_date <= %s
        """,
        (uid, as_of, horizon),
    )
    _pg_delete_auto_plan_after(cur, uid, horizon)
    _pg_write_auto_plan_days(cur, uid, days, now=_utc_now())


def _pg_load_auto_plan_snapshot(cur: Any, uid: Any, plan_row: Any) -> AutoPlanSnapshot:
    cur.execute(
        "SELECT * FROM learning_unit_progress WHERE user_id = %s",
        (uid,),
    )
    progress_rows = cur.fetchall()
    cur.execute(
        "SELECT parent_clause_id, mode FROM split_preference WHERE user_id = %s",
        (uid,),
    )
    split_rows = cur.fetchall()
    cur.execute(
        f"""
        SELECT {_STUDY_SESSION_COLUMNS}
        FROM study_session s
        LEFT JOIN study_session_item i ON i.session_id = s.id
        WHERE s.user_id = %s
        ORDER BY s.plan_date ASC, s.kind ASC, s.created_at ASC, i.position ASC
        """,
        (uid,),
    )
    session_rows = cur.fetchall()
    cur.execute(
        """
        SELECT user_id, plan_date, daily_target, created_at, updated_at
        FROM auto_plan_day
        WHERE user_id = %s
        ORDER BY plan_date
        """,
        (uid,),
    )
    day_rows = cur.fetchall()
    cur.execute(
        """
        SELECT user_id, plan_date, learning_unit_id, position, created_at
        FROM auto_plan_item
        WHERE user_id = %s
        ORDER BY plan_date, position
        """,
        (uid,),
    )
    item_rows = cur.fetchall()
    cur.execute(
        "SELECT article_number FROM user_free_articles WHERE user_id = %s",
        (uid,),
    )
    claimed_rows = cur.fetchall()
    return AutoPlanSnapshot(
        user_id=str(uid),
        plan=_row_to_learning_plan(plan_row),
        progress=tuple(_row_progress(row) for row in progress_rows),
        split_preferences={
            str(row["parent_clause_id"]): row["mode"] for row in split_rows
        },
        sessions=tuple(_sessions_from_joined_rows(session_rows)),
        days=tuple(_auto_plan_days_from_rows(day_rows, item_rows)),
        claimed_articles=frozenset(str(row["article_number"]) for row in claimed_rows),
    )


def _row_profile(row: Any) -> dict[str, str | None]:
    created = row["created_at"]
    updated = row["updated_at"]
    return {
        "user_id": str(row["user_id"]),
        "display_name": row["display_name"],
        "avatar_url": row["avatar_url"],
        "created_at": created.isoformat()
        if hasattr(created, "isoformat")
        else str(created) if created is not None else None,
        "updated_at": updated.isoformat()
        if hasattr(updated, "isoformat")
        else str(updated) if updated is not None else None,
    }


def _pipeline_capability() -> tuple[bool, str | None]:
    """Probe psycopg pipeline support without catching SQL or connection errors.

    Returns ``(True, None)`` when ``conn.pipeline()`` should be used.
    Returns ``(False, reason)`` only for a narrow capability miss (the
    installed Pipeline API reports unsupported, or the probe callable is
    present and returns false). A missing probe on a build that still
    exposes ``Connection.pipeline`` is treated as supported so we attempt
    the real API rather than silently taking six sequential round trips.
    """
    from psycopg import Pipeline

    checker = getattr(Pipeline, "is_supported", None) or getattr(
        Pipeline, "has_pipeline", None
    )
    if checker is None:
        return True, None
    if checker():
        return True, None
    name = getattr(checker, "__name__", "pipeline_capability")
    return False, f"{name}_false"


def _pipeline_supported() -> bool:
    supported, _reason = _pipeline_capability()
    return supported


_BOOTSTRAP_PROGRESS_SQL = """
SELECT * FROM learning_unit_progress
WHERE user_id = %s
ORDER BY learning_unit_id ASC
"""
_BOOTSTRAP_SPLIT_SQL = (
    "SELECT parent_clause_id, mode FROM split_preference WHERE user_id = %s"
)
_BOOTSTRAP_SETTINGS_SQL = (
    "SELECT key, value FROM app_settings WHERE user_id = %s"
)
_BOOTSTRAP_PROFILE_SQL = """
SELECT user_id, display_name, avatar_url, created_at, updated_at
FROM user_profile WHERE user_id = %s
"""
_BOOTSTRAP_MODES_SQL = (
    "SELECT learning_unit_id, mode FROM unit_modes_seen WHERE user_id = %s"
)
_BOOTSTRAP_CLAIMS_SQL = (
    "SELECT article_number FROM user_free_articles WHERE user_id = %s"
)
_BOOTSTRAP_BILLING_SQL = """
SELECT * FROM billing_orders
WHERE user_id = %s AND status = 'paid'
ORDER BY paid_at DESC LIMIT 1
"""
_PLANNER_PLAN_SQL = """
SELECT mode, daily_target, activated_at, prompt_dismissed_on,
       last_anchor_theme, target_effective_on, updated_at
FROM user_learning_plan
WHERE user_id = %s
"""
_PLANNER_SESSIONS_SQL = f"""
SELECT {_STUDY_SESSION_COLUMNS}
FROM study_session s
LEFT JOIN study_session_item i ON i.session_id = s.id
WHERE s.user_id = %s AND s.plan_date = %s
  AND s.kind IN ('revision', 'auto_learning', 'day_plan')
ORDER BY s.kind, s.created_at ASC, s.id ASC, i.position ASC
"""
_PLANNER_AUTO_DAY_SQL = """
SELECT user_id, plan_date, daily_target, created_at, updated_at
FROM auto_plan_day
WHERE user_id = %s AND plan_date >= %s AND plan_date <= %s
ORDER BY plan_date
"""
_PLANNER_AUTO_ITEM_SQL = """
SELECT user_id, plan_date, learning_unit_id, position, created_at
FROM auto_plan_item
WHERE user_id = %s AND plan_date >= %s AND plan_date <= %s
ORDER BY plan_date, position
"""
_PLANNER_AUTO_TAIL_SQL = """
SELECT 1 FROM auto_plan_day
WHERE user_id = %s AND plan_date > %s
LIMIT 1
"""
_PLANNER_GOAL_SQL = """
SELECT goal_date FROM daily_goal_met
WHERE user_id = %s AND goal_date <= %s
ORDER BY goal_date DESC
LIMIT %s
"""
_COMPLETION_PROGRESS_SQL = """
SELECT * FROM learning_unit_progress
WHERE user_id = %s AND learning_unit_id = %s
"""
_COMPLETION_MODES_SQL = """
SELECT mode FROM unit_modes_seen
WHERE user_id = %s AND learning_unit_id = %s
"""
_MARK_MODE_SEEN_SQL = """
WITH touched AS (
    INSERT INTO unit_modes_seen (user_id, learning_unit_id, mode, seen_at)
    VALUES (%s, %s, %s, %s)
    ON CONFLICT (user_id, learning_unit_id, mode) DO UPDATE SET
        seen_at = EXCLUDED.seen_at
    RETURNING mode
)
SELECT mode
FROM unit_modes_seen
WHERE user_id = %s
  AND learning_unit_id = %s
UNION
SELECT mode
FROM touched
"""
_COMMIT_COMPLETION_SQL = """
WITH upserted AS (
    INSERT INTO learning_unit_progress (
        user_id, learning_unit_id, status, times_completed,
        last_completed, next_revision, interval_days, ease_factor,
        created_at, updated_at
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (user_id, learning_unit_id) DO UPDATE SET
        status = EXCLUDED.status,
        times_completed = EXCLUDED.times_completed,
        last_completed = EXCLUDED.last_completed,
        next_revision = EXCLUDED.next_revision,
        interval_days = EXCLUDED.interval_days,
        ease_factor = EXCLUDED.ease_factor,
        updated_at = EXCLUDED.updated_at
    RETURNING *
),
_cleared AS (
    DELETE FROM unit_modes_seen
    WHERE user_id = %s AND learning_unit_id = %s
)
SELECT * FROM upserted
"""


class PostgresProgressRepository:
    """psycopg-backed progress repository. Every query includes user_id."""

    def __init__(self, pool: Any) -> None:
        from psycopg.rows import dict_row

        self._pool = pool
        self._dict_row = dict_row

    @contextmanager
    def _cursor(self) -> Iterator[tuple[Any, Any]]:
        """Borrow a pooled connection; dict rows only on this cursor."""
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=self._dict_row) as cur:
                yield conn, cur

    def get_progress(self, user_id: UUID | str, unit_id: str) -> ProgressRecord | None:
        with self._cursor() as (_conn, cur):
            cur.execute(
                """
                SELECT * FROM learning_unit_progress
                WHERE user_id = %s AND learning_unit_id = %s
                """,
                (as_user_id(user_id), unit_id),
            )
            row = cur.fetchone()
        return _row_progress(row) if row else None

    def ensure_progress(self, user_id: UUID | str, unit_id: str) -> ProgressRecord:
        existing = self.get_progress(user_id, unit_id)
        if existing is not None:
            return existing
        now = _utc_now()
        with self._cursor() as (conn, cur):
            cur.execute(
                """
                INSERT INTO learning_unit_progress (
                    user_id, learning_unit_id, status, times_completed,
                    last_completed, next_revision, interval_days, ease_factor,
                    created_at, updated_at
                ) VALUES (%s, %s, 'new', 0, NULL, NULL, 0, 2.5, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (as_user_id(user_id), unit_id, now, now),
            )
            conn.commit()
        record = self.get_progress(user_id, unit_id)
        assert record is not None
        return record

    def upsert_progress(
        self,
        user_id: UUID | str,
        *,
        unit_id: str,
        status: ProgressStatus,
        times_completed: int,
        last_completed: date | None,
        next_revision: date | None,
        interval_days: int,
        ease_factor: float = 2.5,
    ) -> ProgressRecord:
        now = _utc_now()
        with self._cursor() as (conn, cur):
            cur.execute(
                """
                INSERT INTO learning_unit_progress (
                    user_id, learning_unit_id, status, times_completed,
                    last_completed, next_revision, interval_days, ease_factor,
                    created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id, learning_unit_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    times_completed = EXCLUDED.times_completed,
                    last_completed = EXCLUDED.last_completed,
                    next_revision = EXCLUDED.next_revision,
                    interval_days = EXCLUDED.interval_days,
                    ease_factor = EXCLUDED.ease_factor,
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    as_user_id(user_id),
                    unit_id,
                    status,
                    times_completed,
                    last_completed,
                    next_revision,
                    interval_days,
                    ease_factor,
                    now,
                    now,
                ),
            )
            conn.commit()
        record = self.get_progress(user_id, unit_id)
        assert record is not None
        return record

    def list_due(
        self,
        user_id: UUID | str,
        as_of: date,
        *,
        include_new: bool = False,
    ) -> list[ProgressRecord]:
        with self._cursor() as (_conn, cur):
            cur.execute(
                """
                SELECT * FROM learning_unit_progress
                WHERE user_id = %s
                  AND status = 'review'
                  AND next_revision IS NOT NULL
                  AND next_revision <= %s
                ORDER BY next_revision ASC, learning_unit_id ASC
                """,
                (as_user_id(user_id), as_of),
            )
            due = [_row_progress(r) for r in cur.fetchall()]
            if include_new:
                cur.execute(
                    """
                    SELECT * FROM learning_unit_progress
                    WHERE user_id = %s AND status = 'new'
                    ORDER BY learning_unit_id ASC
                    """,
                    (as_user_id(user_id),),
                )
                due.extend(_row_progress(r) for r in cur.fetchall())
        return due

    def list_all_progress(self, user_id: UUID | str) -> list[ProgressRecord]:
        with self._cursor() as (_conn, cur):
            cur.execute(
                """
                SELECT * FROM learning_unit_progress
                WHERE user_id = %s
                ORDER BY learning_unit_id ASC
                """,
                (as_user_id(user_id),),
            )
            rows = cur.fetchall()
        return [_row_progress(r) for r in rows]

    def count_by_status(self, user_id: UUID | str) -> dict[str, int]:
        with self._cursor() as (_conn, cur):
            cur.execute(
                """
                SELECT status, COUNT(*) AS n
                FROM learning_unit_progress
                WHERE user_id = %s
                GROUP BY status
                """,
                (as_user_id(user_id),),
            )
            rows = cur.fetchall()
        return {str(r["status"]): int(r["n"]) for r in rows}

    def get_split_preference(
        self, user_id: UUID | str, parent_clause_id: str
    ) -> SplitMode | None:
        with self._cursor() as (_conn, cur):
            cur.execute(
                """
                SELECT mode FROM split_preference
                WHERE user_id = %s AND parent_clause_id = %s
                """,
                (as_user_id(user_id), parent_clause_id),
            )
            row = cur.fetchone()
        return None if row is None else row["mode"]

    def set_split_preference(
        self, user_id: UUID | str, parent_clause_id: str, mode: SplitMode
    ) -> None:
        with self._cursor() as (conn, cur):
            cur.execute(
                """
                INSERT INTO split_preference (user_id, parent_clause_id, mode, updated_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_id, parent_clause_id) DO UPDATE SET
                    mode = EXCLUDED.mode,
                    updated_at = EXCLUDED.updated_at
                """,
                (as_user_id(user_id), parent_clause_id, mode, _utc_now()),
            )
            conn.commit()

    def list_split_preferences(self, user_id: UUID | str) -> dict[str, SplitMode]:
        with self._cursor() as (_conn, cur):
            cur.execute(
                "SELECT parent_clause_id, mode FROM split_preference WHERE user_id = %s",
                (as_user_id(user_id),),
            )
            rows = cur.fetchall()
        return {str(r["parent_clause_id"]): r["mode"] for r in rows}

    def delete_progress(self, user_id: UUID | str, unit_id: str) -> None:
        with self._cursor() as (conn, cur):
            cur.execute(
                """
                DELETE FROM learning_unit_progress
                WHERE user_id = %s AND learning_unit_id = %s
                """,
                (as_user_id(user_id), unit_id),
            )
            conn.commit()

    def delete_all_progress(self, user_id: UUID | str) -> None:
        uid = as_user_id(user_id)
        with self._cursor() as (conn, cur):
            cur.execute(
                "DELETE FROM learning_unit_progress WHERE user_id = %s", (uid,)
            )
            cur.execute("DELETE FROM split_preference WHERE user_id = %s", (uid,))
            conn.commit()

    def delete_split_preference(
        self, user_id: UUID | str, parent_clause_id: str
    ) -> None:
        with self._cursor() as (conn, cur):
            cur.execute(
                """
                DELETE FROM split_preference
                WHERE user_id = %s AND parent_clause_id = %s
                """,
                (as_user_id(user_id), parent_clause_id),
            )
            conn.commit()

    def get_gloss(self, user_id: UUID | str, article_number: str) -> str | None:
        with self._cursor() as (_conn, cur):
            cur.execute(
                """
                SELECT text FROM article_gloss
                WHERE user_id = %s AND article_number = %s
                """,
                (as_user_id(user_id), article_number),
            )
            row = cur.fetchone()
        return None if row is None else str(row["text"])

    def upsert_gloss(
        self, user_id: UUID | str, article_number: str, text: str
    ) -> None:
        with self._cursor() as (conn, cur):
            cur.execute(
                """
                INSERT INTO article_gloss (user_id, article_number, text, updated_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_id, article_number) DO UPDATE SET
                    text = EXCLUDED.text,
                    updated_at = EXCLUDED.updated_at
                """,
                (as_user_id(user_id), article_number, text, _utc_now()),
            )
            conn.commit()

    def delete_gloss(self, user_id: UUID | str, article_number: str) -> None:
        with self._cursor() as (conn, cur):
            cur.execute(
                """
                DELETE FROM article_gloss
                WHERE user_id = %s AND article_number = %s
                """,
                (as_user_id(user_id), article_number),
            )
            conn.commit()

    # ------------------------------------------------------------------ #
    # Free-Article entitlement slots (parent Article level)               #
    # ------------------------------------------------------------------ #
    def claimed_articles(self, user_id: UUID | str) -> set[str]:
        with self._cursor() as (_conn, cur):
            cur.execute(
                "SELECT article_number FROM user_free_articles WHERE user_id = %s",
                (as_user_id(user_id),),
            )
            rows = cur.fetchall()
        return {str(row["article_number"]) for row in rows}

    def claimed_articles_with_dates(self, user_id: UUID | str) -> dict[str, str]:
        """Claimed parent Articles mapped to their claimed_at ISO timestamp."""
        with self._cursor() as (_conn, cur):
            cur.execute(
                "SELECT article_number, claimed_at FROM user_free_articles WHERE user_id = %s",
                (as_user_id(user_id),),
            )
            rows = cur.fetchall()
        return {str(row["article_number"]): str(row["claimed_at"]) for row in rows}

    def is_article_claimed(self, user_id: UUID | str, article_number: str) -> bool:
        with self._cursor() as (_conn, cur):
            cur.execute(
                "SELECT 1 FROM user_free_articles WHERE user_id = %s AND article_number = %s",
                (as_user_id(user_id), str(article_number)),
            )
            row = cur.fetchone()
        return row is not None

    def claim_article(self, user_id: UUID | str, article_number: str) -> None:
        """Idempotently claim a parent Article as one of the user's Free Articles."""
        with self._cursor() as (conn, cur):
            cur.execute(
                """
                INSERT INTO user_free_articles (user_id, article_number, claimed_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, article_number) DO NOTHING
                """,
                (as_user_id(user_id), str(article_number), _utc_now()),
            )
            conn.commit()

    # ------------------------------------------------------------------ #
    # Study sessions (revision / auto-learning / day-plan queues)         #
    # ------------------------------------------------------------------ #
    def create_study_session(
        self,
        user_id: UUID | str,
        *,
        session_id: str,
        kind: StudySessionKind,
        plan_date: date,
        unit_ids: list[str],
    ) -> StudySession:
        existing = self.get_study_session(user_id, session_id)
        if existing is not None:
            return existing
        existing_day = self.study_session_for_day(
            user_id, kind=kind, plan_date=plan_date
        )
        if existing_day is not None:
            return existing_day
        now = _utc_now()
        uid = as_user_id(user_id)
        ordered: list[str] = []
        for unit_id in unit_ids:
            if unit_id not in ordered:
                ordered.append(unit_id)
        inserted_id: str | None = None
        with self._cursor() as (conn, cur):
            try:
                cur.execute(
                    """
                    INSERT INTO study_session (
                        id, user_id, kind, plan_date, status, created_at, completed_at
                    ) VALUES (%s, %s, %s, %s, 'active', %s, NULL)
                    ON CONFLICT (user_id, kind, plan_date) DO NOTHING
                    RETURNING id
                    """,
                    (session_id, uid, kind, plan_date, now),
                )
                row = cur.fetchone()
                if row is not None:
                    inserted_id = str(row["id"])
                    if ordered:
                        cur.executemany(
                            """
                            INSERT INTO study_session_item (
                                session_id, learning_unit_id, position, status, completed_at
                            ) VALUES (%s, %s, %s, 'pending', NULL)
                            """,
                            [
                                (inserted_id, unit, index)
                                for index, unit in enumerate(ordered)
                            ],
                        )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        if inserted_id is None:
            winner = self.study_session_for_day(
                user_id, kind=kind, plan_date=plan_date
            ) or self.get_study_session(user_id, session_id)
            if winner is not None:
                return winner
            raise RuntimeError("study session create-or-get lost the race and found nothing")
        session = self.get_study_session(user_id, inserted_id)
        assert session is not None
        return session

    def get_study_session(
        self, user_id: UUID | str, session_id: str
    ) -> StudySession | None:
        with self._cursor() as (_conn, cur):
            cur.execute(
                f"""
                SELECT {_STUDY_SESSION_COLUMNS}
                FROM study_session s
                LEFT JOIN study_session_item i ON i.session_id = s.id
                WHERE s.user_id = %s AND s.id = %s
                ORDER BY i.position ASC
                """,
                (as_user_id(user_id), session_id),
            )
            rows = cur.fetchall()
        return _study_session_from_rows(rows)

    def active_study_session(
        self,
        user_id: UUID | str,
        *,
        kind: StudySessionKind,
        plan_date: date | None = None,
    ) -> StudySession | None:
        clause = "" if plan_date is None else " AND s.plan_date = %s"
        params: list[Any] = [as_user_id(user_id), kind]
        if plan_date is not None:
            params.append(plan_date)
        with self._cursor() as (_conn, cur):
            cur.execute(
                f"""
                SELECT {_STUDY_SESSION_COLUMNS}
                FROM study_session s
                LEFT JOIN study_session_item i ON i.session_id = s.id
                WHERE s.user_id = %s AND s.kind = %s AND s.status = 'active'{clause}
                ORDER BY s.created_at DESC, s.id DESC, i.position ASC
                """,
                params,
            )
            rows = cur.fetchall()
        if not rows:
            return None
        newest = rows[0]["session_id"]
        return _study_session_from_rows(
            [row for row in rows if row["session_id"] == newest]
        )

    def study_session_for_day(
        self,
        user_id: UUID | str,
        *,
        kind: StudySessionKind,
        plan_date: date,
    ) -> StudySession | None:
        with self._cursor() as (_conn, cur):
            cur.execute(
                f"""
                SELECT {_STUDY_SESSION_COLUMNS}
                FROM study_session s
                LEFT JOIN study_session_item i ON i.session_id = s.id
                WHERE s.user_id = %s AND s.kind = %s AND s.plan_date = %s
                ORDER BY s.created_at ASC, s.id ASC, i.position ASC
                """,
                (as_user_id(user_id), kind, plan_date),
            )
            rows = cur.fetchall()
        if not rows:
            return None
        keeper = rows[0]["session_id"]
        return _study_session_from_rows(
            [row for row in rows if row["session_id"] == keeper]
        )

    def study_sessions_for_day(
        self, user_id: UUID | str, plan_date: date
    ) -> dict[str, StudySession | None]:
        with self._cursor() as (_conn, cur):
            cur.execute(
                f"""
                SELECT {_STUDY_SESSION_COLUMNS}
                FROM study_session s
                LEFT JOIN study_session_item i ON i.session_id = s.id
                WHERE s.user_id = %s AND s.plan_date = %s
                  AND s.kind IN ('revision', 'auto_learning', 'day_plan')
                ORDER BY s.kind, s.created_at ASC, s.id ASC, i.position ASC
                """,
                (as_user_id(user_id), plan_date),
            )
            rows = cur.fetchall()
        return _sessions_by_kind_for_day(rows)

    def record_daily_goal_met(self, user_id: UUID | str, goal_date: date) -> None:
        with self._cursor() as (conn, cur):
            cur.execute(
                """
                INSERT INTO daily_goal_met (user_id, goal_date, met_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, goal_date) DO NOTHING
                """,
                (as_user_id(user_id), goal_date, _utc_now()),
            )
            conn.commit()

    def clear_daily_goal_met(self, user_id: UUID | str) -> None:
        """Drop every daily-goal fact for this user — the streak's source."""
        with self._cursor() as (conn, cur):
            cur.execute(
                "DELETE FROM daily_goal_met WHERE user_id = %s",
                (as_user_id(user_id),),
            )
            conn.commit()

    def is_daily_goal_met(self, user_id: UUID | str, goal_date: date) -> bool:
        with self._cursor() as (_conn, cur):
            cur.execute(
                """
                SELECT 1 FROM daily_goal_met
                WHERE user_id = %s AND goal_date = %s
                """,
                (as_user_id(user_id), goal_date),
            )
            return cur.fetchone() is not None

    def list_daily_goal_dates(
        self, user_id: UUID | str, *, until: date, limit: int = 400
    ) -> list[date]:
        with self._cursor() as (_conn, cur):
            cur.execute(
                """
                SELECT goal_date FROM daily_goal_met
                WHERE user_id = %s AND goal_date <= %s
                ORDER BY goal_date DESC
                LIMIT %s
                """,
                (as_user_id(user_id), until, limit),
            )
            rows = cur.fetchall()
        out: list[date] = []
        for row in rows:
            raw = row["goal_date"]
            out.append(raw if isinstance(raw, date) else date.fromisoformat(str(raw)))
        return out

    def set_study_item_status(
        self,
        user_id: UUID | str,
        *,
        session_id: str,
        unit_id: str,
        status: StudyItemStatus,
    ) -> None:
        completed_at = _utc_now() if status == "completed" else None
        with self._cursor() as (conn, cur):
            cur.execute(
                """
                UPDATE study_session_item
                SET status = %s, completed_at = %s
                WHERE session_id = %s AND learning_unit_id = %s
                  AND session_id IN (SELECT id FROM study_session WHERE user_id = %s)
                """,
                (status, completed_at, session_id, unit_id, as_user_id(user_id)),
            )
            conn.commit()

    def replace_study_session_unit(
        self,
        user_id: UUID | str,
        *,
        session_id: str,
        old_unit_id: str,
        new_unit_ids: list[str],
    ) -> StudySession | None:
        session = self.get_study_session(user_id, session_id)
        if session is None:
            return None
        current = session.item_for(old_unit_id)
        if current is None or current.status != "pending":
            return session
        existing = {item.learning_unit_id for item in session.items}
        ordered: list[str] = []
        for unit_id in new_unit_ids:
            if not unit_id or unit_id == old_unit_id:
                continue
            if unit_id in existing and unit_id != old_unit_id:
                continue
            if unit_id not in ordered:
                ordered.append(unit_id)
        if not ordered:
            return session
        shift = len(ordered) - 1
        uid = as_user_id(user_id)
        with self._cursor() as (conn, cur):
            try:
                if shift > 0:
                    cur.execute(
                        """
                        UPDATE study_session_item
                        SET position = position + %s
                        WHERE session_id = %s
                          AND position > %s
                          AND session_id IN (SELECT id FROM study_session WHERE user_id = %s)
                        """,
                        (shift, session_id, current.position, uid),
                    )
                cur.execute(
                    """
                    DELETE FROM
                        study_session_item
                    WHERE session_id = %s AND learning_unit_id = %s
                      AND session_id IN (SELECT id FROM study_session WHERE user_id = %s)
                    """,
                    (session_id, old_unit_id, uid),
                )
                cur.executemany(
                    """
                    INSERT INTO study_session_item (
                        session_id, learning_unit_id, position, status, completed_at
                    ) VALUES (%s, %s, %s, 'pending', NULL)
                    """,
                    [
                        (session_id, unit_id, current.position + index)
                        for index, unit_id in enumerate(ordered)
                    ],
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return self.get_study_session(user_id, session_id)

    def complete_study_session(self, user_id: UUID | str, session_id: str) -> None:
        with self._cursor() as (conn, cur):
            cur.execute(
                """
                UPDATE study_session
                SET status = 'complete', completed_at = %s
                WHERE id = %s AND user_id = %s
                """,
                (_utc_now(), session_id, as_user_id(user_id)),
            )
            conn.commit()

    def delete_all_study_sessions(self, user_id: UUID | str) -> None:
        """Drop every study session for this user, items included."""
        uid = as_user_id(user_id)
        with self._cursor() as (conn, cur):
            cur.execute(
                """
                DELETE FROM study_session_item
                WHERE session_id IN (SELECT id FROM study_session WHERE user_id = %s)
                """,
                (uid,),
            )
            cur.execute("DELETE FROM study_session WHERE user_id = %s", (uid,))
            conn.commit()

    def delete_learning_plan(self, user_id: UUID | str) -> None:
        """Forget the stored plan; get_learning_plan falls back to Self-paced."""
        with self._cursor() as (conn, cur):
            cur.execute(
                "DELETE FROM user_learning_plan WHERE user_id = %s",
                (as_user_id(user_id),),
            )
            conn.commit()

    def get_learning_plan(self, user_id: UUID | str) -> UserLearningPlan:
        with self._cursor() as (_conn, cur):
            cur.execute(
                """
                SELECT mode, daily_target, activated_at, prompt_dismissed_on,
                       last_anchor_theme, target_effective_on, updated_at
                FROM user_learning_plan
                WHERE user_id = %s
                """,
                (as_user_id(user_id),),
            )
            row = cur.fetchone()
        return _row_to_learning_plan(row)

    def upsert_learning_plan(
        self,
        user_id: UUID | str,
        *,
        mode: LearningPlanMode,
        daily_target: int | None,
        prompt_dismissed_on: date | None = None,
        last_anchor_theme: str | None = None,
        as_of: date | None = None,
    ) -> UserLearningPlan:
        if mode == "auto":
            if daily_target not in VALID_DAILY_TARGETS:
                raise ValueError("auto mode requires daily_target of 3, 5, or 7")
        else:
            daily_target = None
        now = _utc_now()
        uid = as_user_id(user_id)
        current = self.get_learning_plan(user_id)
        dismissed = (
            prompt_dismissed_on
            if prompt_dismissed_on is not None
            else current.prompt_dismissed_on
        )
        theme = (
            last_anchor_theme
            if last_anchor_theme is not None
            else current.last_anchor_theme
        )
        effective_on = _effective_on_for_upsert(
            current, mode=mode, daily_target=daily_target, as_of=as_of
        )
        with self._cursor() as (conn, cur):
            cur.execute(
                """
                INSERT INTO user_learning_plan (
                    user_id, mode, daily_target, activated_at,
                    prompt_dismissed_on, last_anchor_theme, target_effective_on,
                    updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    mode = EXCLUDED.mode,
                    daily_target = EXCLUDED.daily_target,
                    prompt_dismissed_on = EXCLUDED.prompt_dismissed_on,
                    last_anchor_theme = EXCLUDED.last_anchor_theme,
                    target_effective_on = EXCLUDED.target_effective_on,
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    uid,
                    mode,
                    daily_target,
                    current.activated_at,
                    dismissed,
                    theme,
                    effective_on,
                    now,
                ),
            )
            conn.commit()
        return self.get_learning_plan(user_id)

    def activate_learning_plan(
        self, user_id: UUID | str, as_of: date
    ) -> UserLearningPlan:
        now = _utc_now()
        with self._cursor() as (conn, cur):
            cur.execute(
                """
                UPDATE user_learning_plan
                SET activated_at = %s, updated_at = %s
                WHERE user_id = %s
                  AND mode = 'auto'
                  AND activated_at IS NULL
                """,
                (as_of, now, as_user_id(user_id)),
            )
            conn.commit()
        return self.get_learning_plan(user_id)

    def dismiss_plan_prompt(
        self, user_id: UUID | str, as_of: date
    ) -> UserLearningPlan:
        now = _utc_now()
        uid = as_user_id(user_id)
        current = self.get_learning_plan(user_id)
        with self._cursor() as (conn, cur):
            cur.execute(
                """
                INSERT INTO user_learning_plan (
                    user_id, mode, daily_target, activated_at,
                    prompt_dismissed_on, last_anchor_theme, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    prompt_dismissed_on = EXCLUDED.prompt_dismissed_on,
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    uid,
                    current.mode,
                    current.daily_target,
                    current.activated_at,
                    as_of,
                    current.last_anchor_theme,
                    now,
                ),
            )
            conn.commit()
        return self.get_learning_plan(user_id)

    def set_last_anchor_theme(
        self, user_id: UUID | str, theme: str | None
    ) -> None:
        now = _utc_now()
        uid = as_user_id(user_id)
        current = self.get_learning_plan(user_id)
        with self._cursor() as (conn, cur):
            cur.execute(
                """
                INSERT INTO user_learning_plan (
                    user_id, mode, daily_target, activated_at,
                    prompt_dismissed_on, last_anchor_theme, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    last_anchor_theme = EXCLUDED.last_anchor_theme,
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    uid,
                    current.mode,
                    current.daily_target,
                    current.activated_at,
                    current.prompt_dismissed_on,
                    theme,
                    now,
                ),
            )
            conn.commit()

    def list_auto_plan_window(
        self, user_id: UUID | str, start: date, until: date
    ) -> list[AutoPlanDay]:
        uid = as_user_id(user_id)
        with self._pool.connection() as conn:
            with ExitStack() as stack:
                day_cur = stack.enter_context(conn.cursor(row_factory=self._dict_row))
                item_cur = stack.enter_context(conn.cursor(row_factory=self._dict_row))

                def _queue() -> None:
                    day_cur.execute(_PLANNER_AUTO_DAY_SQL, (uid, start, until))
                    item_cur.execute(_PLANNER_AUTO_ITEM_SQL, (uid, start, until))

                if _pipeline_supported():
                    with conn.pipeline():
                        _queue()
                else:
                    _queue()
                day_rows = day_cur.fetchall()
                item_rows = item_cur.fetchall()
        return _auto_plan_days_from_rows(day_rows, item_rows)

    def list_auto_plan_day(
        self, user_id: UUID | str, plan_date: date
    ) -> AutoPlanDay | None:
        days = self.list_auto_plan_window(user_id, plan_date, plan_date)
        return days[0] if days else None

    def replace_auto_plan_day(
        self,
        user_id: UUID | str,
        plan_date: date,
        daily_target: int,
        unit_ids: Sequence[str],
    ) -> AutoPlanDay:
        day = AutoPlanDay(
            plan_date=plan_date,
            daily_target=int(daily_target),
            items=tuple(
                AutoPlanItem(
                    plan_date=plan_date,
                    learning_unit_id=unit_id,
                    position=index,
                )
                for index, unit_id in enumerate(unit_ids)
            ),
        )
        uid = as_user_id(user_id)
        with self._cursor() as (conn, cur):
            _pg_write_auto_plan_days(cur, uid, [day], now=_utc_now())
            conn.commit()
        stored = self.list_auto_plan_day(user_id, plan_date)
        assert stored is not None
        return stored

    def clear_future_auto_plan(self, user_id: UUID | str, as_of: date) -> None:
        uid = as_user_id(user_id)
        with self._cursor() as (conn, cur):
            _pg_clear_auto_plan_from(cur, uid, as_of)
            conn.commit()

    def delete_auto_plan_after(self, user_id: UUID | str, horizon: date) -> None:
        uid = as_user_id(user_id)
        with self._cursor() as (conn, cur):
            _pg_delete_auto_plan_after(cur, uid, horizon)
            conn.commit()

    def replace_auto_plan_window_atomic(
        self,
        user_id: UUID | str,
        as_of: date,
        horizon: date,
        days: Sequence[AutoPlanDay],
    ) -> None:
        uid = as_user_id(user_id)
        with self._pool.connection() as conn:
            with conn.transaction():
                with conn.cursor(row_factory=self._dict_row) as cur:
                    cur.execute(
                        """
                        SELECT user_id FROM user_learning_plan
                        WHERE user_id = %s FOR UPDATE
                        """,
                        (uid,),
                    )
                    _pg_replace_auto_plan_window(cur, uid, as_of, horizon, days)

    def apply_auto_plan_reconcile(
        self,
        user_id: UUID | str,
        as_of: date,
        horizon: date,
        builder: Callable[[AutoPlanSnapshot], Sequence[AutoPlanDay] | None],
    ) -> None:
        uid = as_user_id(user_id)
        with self._pool.connection() as conn:
            with conn.transaction():
                with conn.cursor(row_factory=self._dict_row) as cur:
                    cur.execute(
                        """
                        INSERT INTO user_learning_plan (user_id, mode, updated_at)
                        VALUES (%s, 'self_paced', %s)
                        ON CONFLICT (user_id) DO NOTHING
                        """,
                        (uid, _utc_now()),
                    )
                    cur.execute(
                        """
                        SELECT mode, daily_target, activated_at, prompt_dismissed_on,
                               last_anchor_theme, target_effective_on, updated_at
                        FROM user_learning_plan
                        WHERE user_id = %s
                        FOR UPDATE
                        """,
                        (uid,),
                    )
                    plan_row = cur.fetchone()
                    snapshot = _pg_load_auto_plan_snapshot(cur, uid, plan_row)
                    days = builder(snapshot)
                    if days is None:
                        _pg_clear_auto_plan_from(cur, uid, as_of)
                    else:
                        _pg_replace_auto_plan_window(cur, uid, as_of, horizon, days)

    # ------------------------------------------------------------------ #
    # Billing orders (Razorpay Standard Checkout)                         #
    # ------------------------------------------------------------------ #
    def create_billing_order(
        self,
        user_id: UUID | str,
        *,
        order_id: str,
        plan_days: int,
        amount_paise: int,
        currency: str = "INR",
    ) -> None:
        with self._cursor() as (conn, cur):
            cur.execute(
                """
                INSERT INTO billing_orders (
                    order_id, user_id, plan_days, amount_paise, currency,
                    status, created_at
                )
                VALUES (%s, %s, %s, %s, %s, 'created', %s)
                """,
                (
                    order_id,
                    as_user_id(user_id),
                    int(plan_days),
                    int(amount_paise),
                    currency,
                    _utc_now(),
                ),
            )
            conn.commit()

    def get_billing_order(
        self, user_id: UUID | str, order_id: str
    ) -> BillingOrder | None:
        with self._cursor() as (_conn, cur):
            cur.execute(
                "SELECT * FROM billing_orders WHERE order_id = %s AND user_id = %s",
                (order_id, as_user_id(user_id)),
            )
            row = cur.fetchone()
        return _billing_order_from_row(row) if row is not None else None

    def latest_paid_billing_order(self, user_id: UUID | str) -> BillingOrder | None:
        with self._cursor() as (_conn, cur):
            cur.execute(
                """
                SELECT * FROM billing_orders
                WHERE user_id = %s AND status = 'paid'
                ORDER BY paid_at DESC LIMIT 1
                """,
                (as_user_id(user_id),),
            )
            row = cur.fetchone()
        return _billing_order_from_row(row) if row is not None else None

    def mark_billing_order_paid(
        self,
        user_id: UUID | str,
        *,
        order_id: str,
        payment_id: str,
        grant_id: str,
        access_ends_at: str,
    ) -> bool:
        """Mark a created order paid and grant paid access in ONE transaction.

        Returns False (writing nothing) when the order is already paid, so a
        replayed verify callback never double-grants.
        """
        uid = as_user_id(user_id)
        now = _utc_now()
        with self._cursor() as (conn, cur):
            cur.execute(
                """
                UPDATE billing_orders
                SET status = 'paid', razorpay_payment_id = %s, paid_at = %s
                WHERE order_id = %s AND user_id = %s AND status = 'created'
                """,
                (payment_id, now, order_id, uid),
            )
            if cur.rowcount == 0:
                conn.rollback()
                return False
            cur.execute(
                """
                INSERT INTO access_grants (
                    id, user_id, source, starts_at, ends_at, reason, created_at
                )
                VALUES (%s, %s, 'payment', %s, %s, %s, %s)
                """,
                (grant_id, uid, now, access_ends_at, f"razorpay:{order_id}", now),
            )
            conn.commit()
        return True

    def get_setting(self, user_id: UUID | str, key: str) -> str | None:
        with self._cursor() as (_conn, cur):
            cur.execute(
                "SELECT value FROM app_settings WHERE user_id = %s AND key = %s",
                (as_user_id(user_id), key),
            )
            row = cur.fetchone()
        return None if row is None else str(row["value"])

    def set_setting(self, user_id: UUID | str, key: str, value: str) -> None:
        with self._cursor() as (conn, cur):
            cur.execute(
                """
                INSERT INTO app_settings (user_id, key, value, updated_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_id, key) DO UPDATE SET
                    value = EXCLUDED.value,
                    updated_at = EXCLUDED.updated_at
                """,
                (as_user_id(user_id), key, value, _utc_now()),
            )
            conn.commit()

    def get_theme(self, user_id: UUID | str) -> ThemePreference:
        raw = self.get_setting(user_id, THEME_KEY)
        return raw if raw in VALID_THEMES else DEFAULT_THEME  # type: ignore[return-value]

    def set_theme(self, user_id: UUID | str, theme: ThemePreference) -> None:
        self.set_setting(user_id, THEME_KEY, theme)

    def get_notification_frequency(self, user_id: UUID | str) -> NotificationFrequency:
        raw = self.get_setting(user_id, NOTIFICATION_FREQUENCY_KEY)
        return (
            raw
            if raw in VALID_NOTIFICATION_FREQUENCIES
            else DEFAULT_NOTIFICATION_FREQUENCY
        )  # type: ignore[return-value]

    def set_notification_frequency(
        self, user_id: UUID | str, frequency: NotificationFrequency
    ) -> None:
        self.set_setting(user_id, NOTIFICATION_FREQUENCY_KEY, frequency)

    def get_notification_last_slot(self, user_id: UUID | str) -> datetime | None:
        raw = self.get_setting(user_id, NOTIFICATION_LAST_SLOT_KEY)
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            return None

    def set_notification_last_slot(self, user_id: UUID | str, when: datetime) -> None:
        self.set_setting(
            user_id,
            NOTIFICATION_LAST_SLOT_KEY,
            when.replace(microsecond=0).isoformat(),
        )

    def get_news_articles_raw(self, user_id: UUID | str) -> str:
        raw = self.get_setting(user_id, NEWS_ARTICLES_KEY)
        return DEFAULT_NEWS_ARTICLES if raw is None else raw

    def set_news_articles_raw(self, user_id: UUID | str, value: str) -> None:
        self.set_setting(user_id, NEWS_ARTICLES_KEY, value.strip())

    def mark_mode_seen(self, user_id: UUID | str, unit_id: str, mode: str) -> set[str]:
        uid = as_user_id(user_id)
        with self._cursor() as (conn, cur):
            cur.execute(
                _MARK_MODE_SEEN_SQL,
                (uid, unit_id, mode, _utc_now(), uid, unit_id),
            )
            rows = cur.fetchall()
            conn.commit()
        return {str(r["mode"]) for r in rows}

    def modes_seen(self, user_id: UUID | str, unit_id: str) -> set[str]:
        with self._cursor() as (_conn, cur):
            cur.execute(
                """
                SELECT mode FROM unit_modes_seen
                WHERE user_id = %s AND learning_unit_id = %s
                """,
                (as_user_id(user_id), unit_id),
            )
            rows = cur.fetchall()
        return {str(r["mode"]) for r in rows}

    def clear_modes_seen(self, user_id: UUID | str, unit_id: str) -> None:
        with self._cursor() as (conn, cur):
            cur.execute(
                "DELETE FROM unit_modes_seen WHERE user_id = %s AND learning_unit_id = %s",
                (as_user_id(user_id), unit_id),
            )
            conn.commit()

    def clear_all_modes_seen(self, user_id: UUID | str) -> None:
        with self._cursor() as (conn, cur):
            cur.execute(
                "DELETE FROM unit_modes_seen WHERE user_id = %s",
                (as_user_id(user_id),),
            )
            conn.commit()

    def modes_complete(self, user_id: UUID | str, unit_id: str) -> bool:
        return self.modes_seen(user_id, unit_id) >= LEARN_MODES_SET

    def upsert_profile(
        self,
        user_id: UUID | str,
        *,
        display_name: str | None,
        avatar_url: str | None,
    ) -> None:
        now = _utc_now()
        with self._cursor() as (conn, cur):
            cur.execute(
                """
                INSERT INTO user_profile (user_id, display_name, avatar_url, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    display_name = EXCLUDED.display_name,
                    avatar_url = EXCLUDED.avatar_url,
                    updated_at = EXCLUDED.updated_at
                """,
                (as_user_id(user_id), display_name, avatar_url, now, now),
            )
            conn.commit()

    def record_identity(
        self,
        user_id: UUID | str,
        *,
        email: str | None,
        phone: str | None,
    ) -> None:
        """Refresh the identity directory at sign-in.

        Never clobbers display_name/avatar (owned by /welcome and /profile);
        a null email/phone from the provider keeps the last known value.
        """
        now = _utc_now()
        with self._cursor() as (conn, cur):
            cur.execute(
                """
                INSERT INTO user_profile (
                    user_id, display_name, avatar_url, created_at, updated_at,
                    email, phone, last_sign_in_at
                ) VALUES (%s, NULL, NULL, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    email = COALESCE(EXCLUDED.email, user_profile.email),
                    phone = COALESCE(EXCLUDED.phone, user_profile.phone),
                    last_sign_in_at = EXCLUDED.last_sign_in_at
                """,
                (as_user_id(user_id), now, now, email, phone, now),
            )
            conn.commit()

    def get_profile(self, user_id: UUID | str) -> dict[str, str | None] | None:
        with self._cursor() as (_conn, cur):
            cur.execute(
                """
                SELECT user_id, display_name, avatar_url, created_at, updated_at
                FROM user_profile WHERE user_id = %s
                """,
                (as_user_id(user_id),),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return _row_profile(row)

    def needs_welcome(self, user_id: UUID | str) -> bool:
        profile = self.get_profile(user_id)
        if profile is None:
            return True
        name = (profile.get("display_name") or "").strip()
        return not name

    def load_request_bootstrap(
        self,
        user_id: UUID | str,
        *,
        include_profile: bool = False,
        include_news: bool = False,
        include_modes: bool = False,
        include_account: bool = False,
    ) -> RequestBootstrap:
        uid = as_user_id(user_id)
        with self._pool.connection() as conn:
            with ExitStack() as stack:
                progress_cur = stack.enter_context(
                    conn.cursor(row_factory=self._dict_row)
                )
                split_cur = stack.enter_context(conn.cursor(row_factory=self._dict_row))
                settings_cur = stack.enter_context(
                    conn.cursor(row_factory=self._dict_row)
                )
                profile_cur = (
                    stack.enter_context(conn.cursor(row_factory=self._dict_row))
                    if include_profile
                    else None
                )
                modes_cur = (
                    stack.enter_context(conn.cursor(row_factory=self._dict_row))
                    if include_modes
                    else None
                )
                claims_cur = (
                    stack.enter_context(conn.cursor(row_factory=self._dict_row))
                    if include_account
                    else None
                )
                billing_cur = (
                    stack.enter_context(conn.cursor(row_factory=self._dict_row))
                    if include_account
                    else None
                )

                def _queue() -> None:
                    progress_cur.execute(_BOOTSTRAP_PROGRESS_SQL, (uid,))
                    split_cur.execute(_BOOTSTRAP_SPLIT_SQL, (uid,))
                    settings_cur.execute(_BOOTSTRAP_SETTINGS_SQL, (uid,))
                    if profile_cur is not None:
                        profile_cur.execute(_BOOTSTRAP_PROFILE_SQL, (uid,))
                    if modes_cur is not None:
                        modes_cur.execute(_BOOTSTRAP_MODES_SQL, (uid,))
                    if claims_cur is not None:
                        claims_cur.execute(_BOOTSTRAP_CLAIMS_SQL, (uid,))
                    if billing_cur is not None:
                        billing_cur.execute(_BOOTSTRAP_BILLING_SQL, (uid,))

                if _pipeline_supported():
                    with conn.pipeline():
                        _queue()
                else:
                    _queue()

                progress_rows = progress_cur.fetchall()
                split_rows = split_cur.fetchall()
                settings_rows = settings_cur.fetchall()
                profile_row = (
                    profile_cur.fetchone() if profile_cur is not None else None
                )
                mode_rows = modes_cur.fetchall() if modes_cur is not None else None
                claim_rows = claims_cur.fetchall() if claims_cur is not None else None
                billing_row = (
                    billing_cur.fetchone() if billing_cur is not None else None
                )

        settings = {str(row["key"]): str(row["value"]) for row in settings_rows}
        account = None
        if include_account:
            claimed = frozenset(
                str(row["article_number"]) for row in (claim_rows or [])
            )
            order = (
                _billing_order_from_row(billing_row)
                if billing_row is not None
                else None
            )
            account = AccountBootstrap(
                claimed_articles=claimed,
                latest_paid_billing_order=order,
            )
        return RequestBootstrap(
            progress=[_row_progress(r) for r in progress_rows],
            split_preferences={
                str(r["parent_clause_id"]): r["mode"] for r in split_rows
            },
            theme=_theme_from_raw(settings.get(THEME_KEY)),
            news_articles_raw=(
                _news_from_raw(settings.get(NEWS_ARTICLES_KEY)) if include_news else None
            ),
            profile=_row_profile(profile_row)
            if include_profile and profile_row is not None
            else None,
            settings=settings,
            modes_seen_by_unit=(
                _modes_by_unit_from_rows(mode_rows) if mode_rows is not None else None
            ),
            account=account,
        )

    def load_planner_read_bundle(
        self,
        user_id: UUID | str,
        *,
        as_of: date,
        auto_start: date,
        auto_until: date,
        horizon: date,
        daily_goal_until: date,
        daily_goal_limit: int = 400,
    ) -> PlannerReadBundle:
        """Pipeline independent planner reads on one borrowed connection."""
        uid = as_user_id(user_id)
        pipelined, fallback_reason = _pipeline_capability()
        with self._pool.connection() as conn:
            with ExitStack() as stack:
                plan_cur = stack.enter_context(conn.cursor(row_factory=self._dict_row))
                session_cur = stack.enter_context(
                    conn.cursor(row_factory=self._dict_row)
                )
                day_cur = stack.enter_context(conn.cursor(row_factory=self._dict_row))
                item_cur = stack.enter_context(conn.cursor(row_factory=self._dict_row))
                tail_cur = stack.enter_context(conn.cursor(row_factory=self._dict_row))
                goal_cur = stack.enter_context(conn.cursor(row_factory=self._dict_row))

                def _queue() -> None:
                    plan_cur.execute(_PLANNER_PLAN_SQL, (uid,))
                    session_cur.execute(_PLANNER_SESSIONS_SQL, (uid, as_of))
                    day_cur.execute(_PLANNER_AUTO_DAY_SQL, (uid, auto_start, auto_until))
                    item_cur.execute(
                        _PLANNER_AUTO_ITEM_SQL, (uid, auto_start, auto_until)
                    )
                    tail_cur.execute(_PLANNER_AUTO_TAIL_SQL, (uid, horizon))
                    goal_cur.execute(
                        _PLANNER_GOAL_SQL, (uid, daily_goal_until, daily_goal_limit)
                    )

                if pipelined:
                    with conn.pipeline():
                        _queue()
                else:
                    _queue()

                plan_row = plan_cur.fetchone()
                session_rows = session_cur.fetchall()
                day_rows = day_cur.fetchall()
                item_rows = item_cur.fetchall()
                tail_row = tail_cur.fetchone()
                goal_rows = goal_cur.fetchall()

        goals: list[date] = []
        for row in goal_rows:
            raw = row["goal_date"]
            goals.append(raw if isinstance(raw, date) else date.fromisoformat(str(raw)))
        return PlannerReadBundle(
            as_of=as_of,
            learning_plan=_row_to_learning_plan(plan_row),
            sessions_by_kind=_sessions_by_kind_for_day(session_rows),
            auto_plan_days=tuple(_auto_plan_days_from_rows(day_rows, item_rows)),
            auto_start=auto_start,
            auto_until=auto_until,
            horizon=horizon,
            has_auto_plan_tail=tail_row is not None,
            daily_goal_dates=tuple(goals),
            pipelined=pipelined,
            pipeline_fallback_reason=fallback_reason,
        )

    def load_completion_state(
        self, user_id: UUID | str, unit_id: str
    ) -> CompletionState:
        uid = as_user_id(user_id)
        with self._pool.connection() as conn:
            with ExitStack() as stack:
                progress_cur = stack.enter_context(
                    conn.cursor(row_factory=self._dict_row)
                )
                modes_cur = stack.enter_context(conn.cursor(row_factory=self._dict_row))
                split_cur = stack.enter_context(conn.cursor(row_factory=self._dict_row))

                def _queue() -> None:
                    progress_cur.execute(_COMPLETION_PROGRESS_SQL, (uid, unit_id))
                    modes_cur.execute(_COMPLETION_MODES_SQL, (uid, unit_id))
                    split_cur.execute(_BOOTSTRAP_SPLIT_SQL, (uid,))

                if _pipeline_supported():
                    with conn.pipeline():
                        _queue()
                else:
                    _queue()

                progress_row = progress_cur.fetchone()
                mode_rows = modes_cur.fetchall()
                split_rows = split_cur.fetchall()

        return CompletionState(
            progress=_row_progress(progress_row) if progress_row is not None else None,
            modes_seen={str(r["mode"]) for r in mode_rows},
            split_preferences={
                str(r["parent_clause_id"]): r["mode"] for r in split_rows
            },
        )

    def commit_completion(
        self,
        user_id: UUID | str,
        unit_id: str,
        progress: CompletionProgress,
        *,
        claim_article: str | None = None,
    ) -> ProgressRecord:
        """Persist Done atomically; optionally claim a Free Article with it.

        The claim insert shares the transaction with the progress upsert and
        modes reset — one commit, all-or-nothing.
        """
        now = _utc_now()
        uid = as_user_id(user_id)
        with self._cursor() as (conn, cur):
            if claim_article:
                cur.execute(
                    """
                    INSERT INTO user_free_articles (user_id, article_number, claimed_at)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (user_id, article_number) DO NOTHING
                    """,
                    (uid, str(claim_article), now),
                )
            cur.execute(
                _COMMIT_COMPLETION_SQL,
                (
                    uid,
                    unit_id,
                    progress.status,
                    progress.times_completed,
                    progress.last_completed,
                    progress.next_revision,
                    progress.interval_days,
                    progress.ease_factor,
                    now,
                    now,
                    uid,
                    unit_id,
                ),
            )
            row = cur.fetchone()
            conn.commit()
        assert row is not None
        return _row_progress(row)
