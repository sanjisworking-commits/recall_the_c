"""Postgres monthly roster. Isolation is application-level (ENABLE RLS, no policies).

Capacity consume locks the period row with SELECT ... FOR UPDATE, then re-reads
the roster item and re-counts consumed rows before insert.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from constitution_memorizer.playground.roster.decisions import plan_rollover_batch
from constitution_memorizer.playground.roster.models import (
    ORIGIN_CARRY_FORWARD,
    ORIGIN_NEW,
    ORIGIN_RE_ADD,
    PERIOD_STATUS_ACTIVE,
    PERIOD_STATUS_CLOSED,
    PERIOD_STATUS_DRAFT,
    RESULT_ALREADY_ACTIVE,
    RESULT_NEW_BLOCKED,
    RESULT_OK,
    RESULT_RE_ADDED,
    RESULT_ROSTER_FULL,
    ConsumeResult,
    PlaygroundPeriod,
    RolloverResult,
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
                period = self._ensure_period_locked(
                    cur,
                    uid,
                    period_start=period_start,
                    period_end=period_end,
                    tier_snapshot=tier_snapshot,
                    law_limit=law_limit,
                    clock=clock,
                )
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
        origin_for_new: str = ORIGIN_NEW,
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
                        SET removed_at = NULL, declined_at = NULL, origin = %s,
                            updated_at = %s
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
                        SET consumed_at = %s, removed_at = NULL, declined_at = NULL,
                            origin = %s, updated_at = %s
                        WHERE user_id = %s AND period_start = %s AND law_id = %s
                        """,
                        (clock, origin_for_new, clock, uid, period_start, law_id),
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
                                origin_for_new,
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

    def _ensure_period_locked(
        self,
        cur: Any,
        uid: str,
        *,
        period_start: date,
        period_end: date,
        tier_snapshot: str | None,
        law_limit: int | None,
        clock: datetime,
    ) -> PlaygroundPeriod:
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
                _PERIOD_SELECT + " WHERE user_id = %s AND period_start = %s FOR UPDATE",
                (uid, period_start),
            )
            existing = cur.fetchone()
            self._close_older_active(cur, uid, period_start, clock)
            return period_from_mapping(existing)
        period = period_from_mapping(existing)
        used = self._count_consumed_locked(cur, uid, period_start)
        hold_draft = (
            period.status == PERIOD_STATUS_DRAFT
            and law_limit is not None
            and used > law_limit
        )
        if hold_draft:
            cur.execute(
                """
                UPDATE user_playground_period
                SET tier_snapshot = %s, law_limit = %s, updated_at = %s
                WHERE user_id = %s AND period_start = %s
                """,
                (tier_snapshot, law_limit, clock, uid, period_start),
            )
            cur.execute(
                _PERIOD_SELECT + " WHERE user_id = %s AND period_start = %s",
                (uid, period_start),
            )
            return period_from_mapping(cur.fetchone())
        confirmed = clock if period.confirmed_at is None else period.confirmed_at
        cur.execute(
            """
            UPDATE user_playground_period
            SET tier_snapshot = %s, law_limit = %s, status = %s,
                confirmed_at = %s, updated_at = %s
            WHERE user_id = %s AND period_start = %s
            """,
            (
                tier_snapshot,
                law_limit,
                PERIOD_STATUS_ACTIVE,
                confirmed,
                clock,
                uid,
                period_start,
            ),
        )
        self._close_older_active(cur, uid, period_start, clock)
        cur.execute(
            _PERIOD_SELECT + " WHERE user_id = %s AND period_start = %s",
            (uid, period_start),
        )
        return period_from_mapping(cur.fetchone())

    def _close_older_active(
        self, cur: Any, uid: str, period_start: date, clock: datetime
    ) -> None:
        cur.execute(
            """
            UPDATE user_playground_period
            SET status = %s, updated_at = %s
            WHERE user_id = %s AND status = %s AND period_start < %s
            """,
            (PERIOD_STATUS_CLOSED, clock, uid, PERIOD_STATUS_ACTIVE, period_start),
        )

    def apply_rollover(
        self,
        user_id: UUID | str,
        *,
        period_start: date,
        period_end: date,
        tier_snapshot: str | None,
        law_limit: int | None,
        activate: bool,
        keep_ids: list[str],
        decline_ids: list[str],
        allowed_ids: frozenset[str],
        allow_new_keep: bool,
        now: datetime | None = None,
    ) -> RolloverResult:
        uid = as_user_id(user_id)
        clock = _utc_now(now)
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=self._dict_row) as cur:
                cur.execute(
                    _PERIOD_SELECT
                    + " WHERE user_id = %s AND period_start = %s FOR UPDATE",
                    (uid, period_start),
                )
                existing = cur.fetchone()
                period = period_from_mapping(existing) if existing is not None else None
                status = (
                    period.status
                    if period is not None
                    else (PERIOD_STATUS_ACTIVE if activate else PERIOD_STATUS_DRAFT)
                )
                cur.execute(
                    _ITEM_SELECT + " WHERE user_id = %s AND period_start = %s",
                    (uid, period_start),
                )
                items = {
                    row["law_id"]: item_from_mapping(row) for row in cur.fetchall()
                }
                used = self._count_consumed_locked(cur, uid, period_start)
                plan = plan_rollover_batch(
                    period_status=status,
                    law_limit=law_limit,
                    items=items,
                    used=used,
                    keep_ids=list(keep_ids),
                    decline_ids=list(decline_ids),
                    allowed_ids=set(allowed_ids),
                    allow_new_keep=allow_new_keep,
                )
                if not plan.ok or (period is None and not plan.writes):
                    conn.rollback()
                    return RolloverResult(
                        status=plan.status,
                        used=0 if period is None else used,
                        remaining=remaining_capacity(law_limit, 0 if period is None else used),
                        period=period,
                        adjustment_required=(
                            period is not None
                            and period.status == PERIOD_STATUS_DRAFT
                            and law_limit is not None
                            and used > law_limit
                        ),
                    )
                if period is None:
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
                            PERIOD_STATUS_ACTIVE if activate else PERIOD_STATUS_DRAFT,
                            clock if activate else None,
                            clock,
                            clock,
                        ),
                    )
                    cur.execute(
                        _PERIOD_SELECT
                        + " WHERE user_id = %s AND period_start = %s FOR UPDATE",
                        (uid, period_start),
                    )
                    cur.fetchone()
                for write in plan.writes:
                    self._write_rollover_decision(
                        cur,
                        uid,
                        period_start,
                        write.law_id,
                        keep=write.keep,
                        clock=clock,
                    )
                used_now = self._count_consumed_locked(cur, uid, period_start)
                over = law_limit is not None and used_now > law_limit
                if activate and not over:
                    cur.execute(
                        """
                        UPDATE user_playground_period
                        SET tier_snapshot = %s, law_limit = %s, status = %s,
                            confirmed_at = COALESCE(confirmed_at, %s), updated_at = %s
                        WHERE user_id = %s AND period_start = %s
                        """,
                        (
                            tier_snapshot,
                            law_limit,
                            PERIOD_STATUS_ACTIVE,
                            clock,
                            clock,
                            uid,
                            period_start,
                        ),
                    )
                    self._close_older_active(cur, uid, period_start, clock)
                else:
                    cur.execute(
                        """
                        UPDATE user_playground_period
                        SET tier_snapshot = %s, law_limit = %s, updated_at = %s
                        WHERE user_id = %s AND period_start = %s
                        """,
                        (tier_snapshot, law_limit, clock, uid, period_start),
                    )
                cur.execute(
                    _PERIOD_SELECT + " WHERE user_id = %s AND period_start = %s",
                    (uid, period_start),
                )
                stored = period_from_mapping(cur.fetchone())
                conn.commit()
                return RolloverResult(
                    status=RESULT_OK,
                    used=used_now,
                    remaining=remaining_capacity(stored.law_limit, used_now),
                    period=stored,
                    adjustment_required=stored.status == PERIOD_STATUS_DRAFT and over,
                )

    def _write_rollover_decision(
        self,
        cur: Any,
        uid: str,
        period_start: date,
        law_id: str,
        *,
        keep: bool,
        clock: datetime,
    ) -> None:
        consumed = clock if keep else None
        declined = None if keep else clock
        cur.execute(
            """
            INSERT INTO user_playground_roster_item (
                id, user_id, period_start, law_id, origin,
                carried_from_previous_period, consumed_at, removed_at,
                declined_at, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, true, %s, NULL, %s, %s, %s)
            ON CONFLICT (user_id, period_start, law_id) DO UPDATE
            SET origin = EXCLUDED.origin,
                carried_from_previous_period = true,
                consumed_at = EXCLUDED.consumed_at,
                removed_at = NULL,
                declined_at = EXCLUDED.declined_at,
                updated_at = EXCLUDED.updated_at
            """,
            (
                str(uuid4()),
                uid,
                period_start,
                law_id,
                ORIGIN_CARRY_FORWARD,
                consumed,
                declined,
                clock,
                clock,
            ),
        )

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
