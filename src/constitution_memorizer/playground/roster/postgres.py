"""Postgres monthly roster. Isolation is application-level (ENABLE RLS, no policies).

Capacity consume locks the period row with SELECT ... FOR UPDATE, then re-reads
the roster item and re-counts consumed rows before insert.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from constitution_memorizer.playground.roster.models import (
    ORIGIN_NEW,
    ORIGIN_RE_ADD,
    PERIOD_STATUS_ACTIVE,
    PERIOD_STATUS_CLOSED,
    RESULT_ALREADY_ACTIVE,
    RESULT_NEW_BLOCKED,
    RESULT_OK,
    RESULT_RE_ADDED,
    RESULT_ROSTER_FULL,
    ConsumeResult,
    PlaygroundPeriod,
    RosterItem,
    remaining_capacity,
)
from constitution_memorizer.playground.roster.repository import (
    item_from_mapping,
    period_from_mapping,
)
from constitution_memorizer.progress.user_ids import as_user_id

_PERIOD_SELECT = """
SELECT id, user_id, period_start, period_end, tier_snapshot, law_limit,
       status, confirmed_at, created_at, updated_at
FROM user_playground_period
"""

_ITEM_SELECT = """
SELECT id, user_id, period_start, law_id, origin, carried_from_previous_period,
       consumed_at, removed_at, declined_at, created_at, updated_at
FROM user_playground_roster_item
"""


def _utc_now(now: datetime | None = None) -> datetime:
    clock = now or datetime.now(timezone.utc)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=timezone.utc)
    return clock.replace(microsecond=0)


class PostgresRosterRepository:
    """Production consume: lock the period row, re-count, then insert."""

    def __init__(self, pool: Any) -> None:
        from psycopg.rows import dict_row

        self._pool = pool
        self._dict_row = dict_row

    def get_period(
        self, user_id: UUID | str, period_start: date
    ) -> PlaygroundPeriod | None:
        uid = as_user_id(user_id)
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=self._dict_row) as cur:
                cur.execute(
                    _PERIOD_SELECT + " WHERE user_id = %s AND period_start = %s",
                    (uid, period_start),
                )
                row = cur.fetchone()
        return period_from_mapping(row) if row is not None else None

    def list_periods(self, user_id: UUID | str) -> list[PlaygroundPeriod]:
        uid = as_user_id(user_id)
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=self._dict_row) as cur:
                cur.execute(
                    _PERIOD_SELECT + " WHERE user_id = %s ORDER BY period_start ASC",
                    (uid,),
                )
                rows = cur.fetchall()
        return [period_from_mapping(row) for row in rows]

    def ensure_period(
        self,
        user_id: UUID | str,
        *,
        period_start: date,
        period_end: date,
        tier_snapshot: str | None,
        law_limit: int | None,
        now: datetime | None = None,
    ) -> PlaygroundPeriod:
        uid = as_user_id(user_id)
        clock = _utc_now(now)
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=self._dict_row) as cur:
                cur.execute(
                    """
                    UPDATE user_playground_period
                    SET status = %s, updated_at = %s
                    WHERE user_id = %s AND status = %s AND period_start < %s
                    """,
                    (PERIOD_STATUS_CLOSED, clock, uid, PERIOD_STATUS_ACTIVE, period_start),
                )
                cur.execute(
                    _PERIOD_SELECT + " WHERE user_id = %s AND period_start = %s FOR UPDATE",
                    (uid, period_start),
                )
                existing = cur.fetchone()
                if existing is None:
                    cur.execute(
                        """
                        INSERT INTO user_playground_period (
                            id, user_id, period_start, period_end, tier_snapshot,
                            law_limit, status, confirmed_at, created_at, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (user_id, period_start) DO NOTHING
                        """,
                        (
                            str(uuid4()),
                            uid,
                            period_start,
                            period_end,
                            tier_snapshot,
                            law_limit,
                            PERIOD_STATUS_ACTIVE,
                            clock,
                            clock,
                            clock,
                        ),
                    )
                    cur.execute(
                        _PERIOD_SELECT
                        + " WHERE user_id = %s AND period_start = %s FOR UPDATE",
                        (uid, period_start),
                    )
                    existing = cur.fetchone()
                period = period_from_mapping(existing)
                sets: list[str] = []
                params: list[Any] = []
                if period.tier_snapshot != tier_snapshot or period.law_limit != law_limit:
                    sets.extend(["tier_snapshot = %s", "law_limit = %s"])
                    params.extend([tier_snapshot, law_limit])
                if period.status != PERIOD_STATUS_ACTIVE:
                    sets.append("status = %s")
                    params.append(PERIOD_STATUS_ACTIVE)
                    if period.confirmed_at is None:
                        sets.append("confirmed_at = %s")
                        params.append(clock)
                if sets:
                    sets.append("updated_at = %s")
                    params.append(clock)
                    params.extend([uid, period_start])
                    cur.execute(
                        f"""
                        UPDATE user_playground_period
                        SET {", ".join(sets)}
                        WHERE user_id = %s AND period_start = %s
                        """,
                        params,
                    )
                    cur.execute(
                        _PERIOD_SELECT
                        + " WHERE user_id = %s AND period_start = %s",
                        (uid, period_start),
                    )
                    existing = cur.fetchone()
                    period = period_from_mapping(existing)
                conn.commit()
                return period

    def get_item(
        self, user_id: UUID | str, period_start: date, law_id: str
    ) -> RosterItem | None:
        uid = as_user_id(user_id)
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=self._dict_row) as cur:
                cur.execute(
                    _ITEM_SELECT
                    + " WHERE user_id = %s AND period_start = %s AND law_id = %s",
                    (uid, period_start, law_id),
                )
                row = cur.fetchone()
        return item_from_mapping(row) if row is not None else None

    def list_items(
        self, user_id: UUID | str, period_start: date
    ) -> list[RosterItem]:
        uid = as_user_id(user_id)
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=self._dict_row) as cur:
                cur.execute(
                    _ITEM_SELECT
                    + """
                    WHERE user_id = %s AND period_start = %s
                    ORDER BY created_at ASC, law_id ASC
                    """,
                    (uid, period_start),
                )
                rows = cur.fetchall()
        return [item_from_mapping(row) for row in rows]

    def count_consumed(self, user_id: UUID | str, period_start: date) -> int:
        uid = as_user_id(user_id)
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=self._dict_row) as cur:
                cur.execute(
                    """
                    SELECT COUNT(DISTINCT law_id) AS n
                    FROM user_playground_roster_item
                    WHERE user_id = %s AND period_start = %s
                      AND consumed_at IS NOT NULL
                    """,
                    (uid, period_start),
                )
                row = cur.fetchone()
        return int(row["n"] if row is not None else 0)

    def consume_law(
        self,
        user_id: UUID | str,
        *,
        period_start: date,
        law_id: str,
        law_limit: int | None,
        allow_new: bool,
        now: datetime | None = None,
    ) -> ConsumeResult:
        from psycopg.errors import UniqueViolation

        uid = as_user_id(user_id)
        clock = _utc_now(now)
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=self._dict_row) as cur:
                cur.execute(
                    _PERIOD_SELECT
                    + " WHERE user_id = %s AND period_start = %s FOR UPDATE",
                    (uid, period_start),
                )
                period_row = cur.fetchone()
                if period_row is None:
                    conn.commit()
                    return ConsumeResult(
                        status=RESULT_NEW_BLOCKED,
                        item=None,
                        used=0,
                        remaining=remaining_capacity(law_limit, 0),
                        period=None,
                    )
                period = period_from_mapping(period_row)
                cur.execute(
                    _ITEM_SELECT
                    + " WHERE user_id = %s AND period_start = %s AND law_id = %s",
                    (uid, period_start, law_id),
                )
                item_row = cur.fetchone()
                item = item_from_mapping(item_row) if item_row is not None else None
                used = self._count_consumed_locked(cur, uid, period_start)
                remaining = remaining_capacity(period.law_limit, used)
                if (
                    item is not None
                    and item.consumed_at is not None
                    and item.removed_at is None
                ):
                    conn.commit()
                    return ConsumeResult(
                        status=RESULT_ALREADY_ACTIVE,
                        item=item,
                        used=used,
                        remaining=remaining,
                        period=period,
                    )
                if (
                    item is not None
                    and item.consumed_at is not None
                    and item.removed_at is not None
                ):
                    cur.execute(
                        """
                        UPDATE user_playground_roster_item
                        SET removed_at = NULL, origin = %s, updated_at = %s
                        WHERE user_id = %s AND period_start = %s AND law_id = %s
                        """,
                        (ORIGIN_RE_ADD, clock, uid, period_start, law_id),
                    )
                    cur.execute(
                        _ITEM_SELECT
                        + " WHERE user_id = %s AND period_start = %s AND law_id = %s",
                        (uid, period_start, law_id),
                    )
                    refreshed = item_from_mapping(cur.fetchone())
                    conn.commit()
                    return ConsumeResult(
                        status=RESULT_RE_ADDED,
                        item=refreshed,
                        used=used,
                        remaining=remaining,
                        period=period,
                    )
                if not allow_new:
                    conn.commit()
                    return ConsumeResult(
                        status=RESULT_NEW_BLOCKED,
                        item=item,
                        used=used,
                        remaining=remaining,
                        period=period,
                    )
                cap = period.law_limit
                if cap is not None and used >= cap:
                    conn.commit()
                    return ConsumeResult(
                        status=RESULT_ROSTER_FULL,
                        item=item,
                        used=used,
                        remaining=0,
                        period=period,
                    )
                if item is not None:
                    cur.execute(
                        """
                        UPDATE user_playground_roster_item
                        SET consumed_at = %s, removed_at = NULL, origin = %s,
                            updated_at = %s
                        WHERE user_id = %s AND period_start = %s AND law_id = %s
                        """,
                        (clock, ORIGIN_NEW, clock, uid, period_start, law_id),
                    )
                else:
                    try:
                        cur.execute(
                            """
                            INSERT INTO user_playground_roster_item (
                                id, user_id, period_start, law_id, origin,
                                carried_from_previous_period, consumed_at,
                                removed_at, declined_at, created_at, updated_at
                            ) VALUES (%s, %s, %s, %s, %s, false, %s, NULL, NULL, %s, %s)
                            """,
                            (
                                str(uuid4()),
                                uid,
                                period_start,
                                law_id,
                                ORIGIN_NEW,
                                clock,
                                clock,
                                clock,
                            ),
                        )
                    except UniqueViolation:
                        conn.rollback()
                        with conn.cursor(row_factory=self._dict_row) as retry:
                            retry.execute(
                                _PERIOD_SELECT
                                + " WHERE user_id = %s AND period_start = %s FOR UPDATE",
                                (uid, period_start),
                            )
                            period_row = retry.fetchone()
                            period = period_from_mapping(period_row)
                            retry.execute(
                                _ITEM_SELECT
                                + " WHERE user_id = %s AND period_start = %s AND law_id = %s",
                                (uid, period_start, law_id),
                            )
                            existing = retry.fetchone()
                            stored = (
                                item_from_mapping(existing)
                                if existing is not None
                                else None
                            )
                            used = self._count_consumed_locked(
                                retry, uid, period_start
                            )
                            conn.commit()
                            if stored is not None and stored.consumed_at is not None:
                                status = (
                                    RESULT_ALREADY_ACTIVE
                                    if stored.removed_at is None
                                    else RESULT_RE_ADDED
                                )
                                return ConsumeResult(
                                    status=status,
                                    item=stored,
                                    used=used,
                                    remaining=remaining_capacity(
                                        period.law_limit, used
                                    ),
                                    period=period,
                                )
                        raise
                cur.execute(
                    _ITEM_SELECT
                    + " WHERE user_id = %s AND period_start = %s AND law_id = %s",
                    (uid, period_start, law_id),
                )
                stored_item = item_from_mapping(cur.fetchone())
                used = self._count_consumed_locked(cur, uid, period_start)
                conn.commit()
                return ConsumeResult(
                    status=RESULT_OK,
                    item=stored_item,
                    used=used,
                    remaining=remaining_capacity(period.law_limit, used),
                    period=period,
                )

    def remove_law(
        self,
        user_id: UUID | str,
        *,
        period_start: date,
        law_id: str,
        now: datetime | None = None,
    ) -> RosterItem | None:
        uid = as_user_id(user_id)
        clock = _utc_now(now)
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=self._dict_row) as cur:
                cur.execute(
                    _PERIOD_SELECT
                    + " WHERE user_id = %s AND period_start = %s FOR UPDATE",
                    (uid, period_start),
                )
                cur.execute(
                    _ITEM_SELECT
                    + " WHERE user_id = %s AND period_start = %s AND law_id = %s",
                    (uid, period_start, law_id),
                )
                item_row = cur.fetchone()
                if item_row is None:
                    conn.commit()
                    return None
                item = item_from_mapping(item_row)
                if item.consumed_at is None or item.removed_at is not None:
                    conn.commit()
                    return item
                cur.execute(
                    """
                    UPDATE user_playground_roster_item
                    SET removed_at = %s, updated_at = %s
                    WHERE user_id = %s AND period_start = %s AND law_id = %s
                    """,
                    (clock, clock, uid, period_start, law_id),
                )
                cur.execute(
                    _ITEM_SELECT
                    + " WHERE user_id = %s AND period_start = %s AND law_id = %s",
                    (uid, period_start, law_id),
                )
                refreshed = item_from_mapping(cur.fetchone())
                conn.commit()
                return refreshed

    def _count_consumed_locked(self, cur: Any, uid: str, period_start: date) -> int:
        cur.execute(
            """
            SELECT COUNT(DISTINCT law_id) AS n
            FROM user_playground_roster_item
            WHERE user_id = %s AND period_start = %s AND consumed_at IS NOT NULL
            """,
            (uid, period_start),
        )
        row = cur.fetchone()
        return int(row["n"] if row is not None else 0)
