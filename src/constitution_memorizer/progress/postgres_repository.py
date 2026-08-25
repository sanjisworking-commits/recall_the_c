"""PostgreSQL implementations of user-scoped progress/memory repositories."""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from datetime import date, datetime, timezone
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
    VALID_NOTIFICATION_FREQUENCIES,
    VALID_THEMES,
    AccountBootstrap,
    BillingOrder,
    CompletionProgress,
    CompletionState,
    _billing_order_from_row,
    _modes_by_unit_from_rows,
    _news_from_raw,
    _theme_from_raw,
    NotificationFrequency,
    ProgressRecord,
    ProgressStatus,
    RequestBootstrap,
    SplitMode,
    ThemePreference,
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


def _pipeline_supported() -> bool:
    from psycopg import Pipeline

    checker = getattr(Pipeline, "has_pipeline", None) or getattr(
        Pipeline, "is_supported", None
    )
    return bool(checker()) if checker is not None else False


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

    def get_learning_plan(self, user_id: UUID | str):
        from constitution_memorizer.progress.learning_plan import (
            default_learning_plan,
            learning_plan_from_row,
        )

        uid = as_user_id(user_id)
        with self._cursor() as (_conn, cur):
            cur.execute(
                "SELECT * FROM user_learning_plan WHERE user_id = %s",
                (uid,),
            )
            row = cur.fetchone()
        if row is None:
            return default_learning_plan(uid)
        return learning_plan_from_row(row, uid)

    def upsert_learning_plan(
        self,
        user_id: UUID | str,
        *,
        mode: str,
        daily_target: int | None,
        activated_at: date | None = None,
        plan_prompt_dismissed_on: date | None = None,
    ):
        from constitution_memorizer.progress.learning_plan import (
            learning_plan_from_row,
            validate_mode,
            validate_target,
        )

        uid = as_user_id(user_id)
        mode = validate_mode(mode)
        target = validate_target(daily_target)
        now = _utc_now()
        with self._cursor() as (conn, cur):
            cur.execute(
                """
                INSERT INTO user_learning_plan (
                    user_id, mode, daily_target, activated_at,
                    plan_prompt_dismissed_on, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    mode = EXCLUDED.mode,
                    daily_target = EXCLUDED.daily_target,
                    activated_at = EXCLUDED.activated_at,
                    plan_prompt_dismissed_on = EXCLUDED.plan_prompt_dismissed_on,
                    updated_at = EXCLUDED.updated_at
                """,
                (uid, mode, target, activated_at, plan_prompt_dismissed_on, now),
            )
            conn.commit()
            cur.execute(
                "SELECT * FROM user_learning_plan WHERE user_id = %s",
                (uid,),
            )
            row = cur.fetchone()
        assert row is not None
        return learning_plan_from_row(row, uid)

    def _session_with_items(self, row):
        from constitution_memorizer.progress.study_models import (
            study_session_from_row,
            study_session_item_from_row,
        )

        if row is None:
            return None
        with self._cursor() as (_conn, cur):
            cur.execute(
                """
                SELECT * FROM study_session_item
                WHERE session_id = %s
                ORDER BY position
                """,
                (str(row["id"]),),
            )
            items = cur.fetchall()
        return study_session_from_row(
            row, tuple(study_session_item_from_row(item) for item in items)
        )

    def get_study_session(self, user_id: UUID | str, session_id: str):
        with self._cursor() as (_conn, cur):
            cur.execute(
                """
                SELECT * FROM study_session
                WHERE id = %s AND user_id = %s
                """,
                (session_id, as_user_id(user_id)),
            )
            row = cur.fetchone()
        return self._session_with_items(row)

    def get_active_revision_session(self, user_id: UUID | str):
        with self._cursor() as (_conn, cur):
            cur.execute(
                """
                SELECT * FROM study_session
                WHERE user_id = %s AND kind = 'revision' AND status = 'active'
                """,
                (as_user_id(user_id),),
            )
            row = cur.fetchone()
        return self._session_with_items(row)

    def get_active_learning_session(self, user_id: UUID | str, plan_date: date):
        with self._cursor() as (_conn, cur):
            cur.execute(
                """
                SELECT * FROM study_session
                WHERE user_id = %s AND plan_date = %s AND status = 'active'
                  AND kind IN ('auto_learning', 'one_day_learning')
                """,
                (as_user_id(user_id), plan_date),
            )
            row = cur.fetchone()
        return self._session_with_items(row)

    def insert_study_session(
        self,
        user_id: UUID | str,
        *,
        session_id: str,
        kind: str,
        plan_date: date,
        unit_ids: list[str],
    ):
        from constitution_memorizer.progress.study_models import VALID_KINDS

        if kind not in VALID_KINDS:
            raise ValueError(f"Invalid study session kind: {kind}")
        uid = as_user_id(user_id)
        now = _utc_now()
        try:
            with self._cursor() as (conn, cur):
                cur.execute(
                    """
                    INSERT INTO study_session (
                        id, user_id, kind, plan_date, status, created_at, completed_at
                    ) VALUES (%s, %s, %s, %s, 'active', %s, NULL)
                    """,
                    (session_id, uid, kind, plan_date, now),
                )
                for position, unit_id in enumerate(unit_ids):
                    cur.execute(
                        """
                        INSERT INTO study_session_item (
                            session_id, position, learning_unit_id, state,
                            completed_at, deferred_at
                        ) VALUES (%s, %s, %s, 'pending', NULL, NULL)
                        """,
                        (session_id, position, unit_id),
                    )
                conn.commit()
        except Exception:
            existing = self.get_study_session(uid, session_id)
            if existing is not None:
                return existing
            if kind == "revision":
                existing = self.get_active_revision_session(uid)
            else:
                existing = self.get_active_learning_session(uid, plan_date)
            if existing is not None:
                return existing
            raise
        loaded = self.get_study_session(uid, session_id)
        assert loaded is not None
        return loaded

    def set_study_session_status(
        self,
        user_id: UUID | str,
        session_id: str,
        status: str,
        *,
        completed_at: datetime | None = None,
    ) -> None:
        from constitution_memorizer.progress.study_models import VALID_STATUSES

        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid study session status: {status}")
        now = _utc_now()
        stamp = completed_at
        if status == "completed" and stamp is None:
            stamp = now
        with self._cursor() as (conn, cur):
            cur.execute(
                """
                UPDATE study_session
                SET status = %s, completed_at = %s
                WHERE id = %s AND user_id = %s
                """,
                (status, stamp, session_id, as_user_id(user_id)),
            )
            conn.commit()

    def abandon_stale_sessions(self, user_id: UUID | str, local_today: date) -> int:
        with self._cursor() as (conn, cur):
            cur.execute(
                """
                UPDATE study_session
                SET status = 'abandoned'
                WHERE user_id = %s AND status = 'active' AND plan_date < %s
                """,
                (as_user_id(user_id), local_today),
            )
            count = cur.rowcount or 0
            conn.commit()
        return int(count)

    def abandon_unstarted_learning_sessions(self, user_id: UUID | str) -> int:
        with self._cursor() as (conn, cur):
            cur.execute(
                """
                UPDATE study_session
                SET status = 'abandoned'
                WHERE user_id = %s
                  AND status = 'active'
                  AND kind IN ('auto_learning', 'one_day_learning')
                  AND NOT EXISTS (
                      SELECT 1 FROM study_session_item
                      WHERE study_session_item.session_id = study_session.id
                        AND study_session_item.state = 'completed'
                  )
                """,
                (as_user_id(user_id),),
            )
            count = cur.rowcount or 0
            conn.commit()
        return int(count)

    def set_session_item_state(
        self,
        user_id: UUID | str,
        session_id: str,
        unit_id: str,
        state: str,
        *,
        completed_at: datetime | None = None,
        deferred_at: datetime | None = None,
    ):
        from constitution_memorizer.progress.study_models import VALID_ITEM_STATES

        if state not in VALID_ITEM_STATES:
            raise ValueError(f"Invalid session item state: {state}")
        session = self.get_study_session(user_id, session_id)
        if session is None:
            return None
        now = _utc_now()
        with self._cursor() as (conn, cur):
            cur.execute(
                """
                UPDATE study_session_item
                SET state = %s, completed_at = %s, deferred_at = %s
                WHERE session_id = %s AND learning_unit_id = %s
                """,
                (
                    state,
                    completed_at if state == "completed" else None,
                    deferred_at if state == "deferred" else None,
                    session_id,
                    unit_id,
                ),
            )
            if state in ("completed", "deferred"):
                cur.execute(
                    """
                    SELECT COUNT(*) AS n FROM study_session_item
                    WHERE session_id = %s AND state = 'pending'
                    """,
                    (session_id,),
                )
                pending = cur.fetchone()
                if pending is not None and int(pending["n"]) == 0:
                    cur.execute(
                        """
                        UPDATE study_session
                        SET status = 'completed', completed_at = %s
                        WHERE id = %s AND user_id = %s AND status = 'active'
                        """,
                        (now, session_id, as_user_id(user_id)),
                    )
            conn.commit()
        return self.get_study_session(user_id, session_id)

