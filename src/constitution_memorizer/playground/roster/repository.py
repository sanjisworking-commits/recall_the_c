"""SQLite monthly roster. Owner methods always require ``user_id``.

Capacity consume uses BEGIN IMMEDIATE. Do not count outside the transaction.
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import date, datetime, timezone
from typing import Any, Iterator, Protocol
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
from constitution_memorizer.progress.user_ids import as_user_id


def _utc_now(now: datetime | None = None) -> datetime:
    clock = now or datetime.now(timezone.utc)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=timezone.utc)
    return clock.replace(microsecond=0)


def _parse_dt(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _parse_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _dt_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.replace(microsecond=0).isoformat()


def _date_iso(value: date) -> str:
    return value.isoformat()


def period_from_mapping(row: Any) -> PlaygroundPeriod:
    mapping = dict(row)
    limit = mapping.get("law_limit")
    return PlaygroundPeriod(
        id=str(mapping["id"]),
        user_id=str(mapping["user_id"]),
        period_start=_parse_date(mapping["period_start"]),
        period_end=_parse_date(mapping["period_end"]),
        tier_snapshot=mapping.get("tier_snapshot"),
        law_limit=int(limit) if limit is not None else None,
        status=str(mapping["status"]),
        confirmed_at=_parse_dt(mapping.get("confirmed_at")),
        created_at=_parse_dt(mapping["created_at"]),  # type: ignore[arg-type]
        updated_at=_parse_dt(mapping["updated_at"]),  # type: ignore[arg-type]
    )


def item_from_mapping(row: Any) -> RosterItem:
    mapping = dict(row)
    carried = mapping.get("carried_from_previous_period")
    return RosterItem(
        id=str(mapping["id"]),
        user_id=str(mapping["user_id"]),
        period_start=_parse_date(mapping["period_start"]),
        law_id=str(mapping["law_id"]),
        origin=str(mapping["origin"]),
        carried_from_previous_period=bool(carried),
        consumed_at=_parse_dt(mapping.get("consumed_at")),
        removed_at=_parse_dt(mapping.get("removed_at")),
        declined_at=_parse_dt(mapping.get("declined_at")),
        created_at=_parse_dt(mapping["created_at"]),  # type: ignore[arg-type]
        updated_at=_parse_dt(mapping["updated_at"]),  # type: ignore[arg-type]
    )


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


class RosterRepository(Protocol):
    def get_period(
        self, user_id: UUID | str, period_start: date
    ) -> PlaygroundPeriod | None: ...

    def list_periods(self, user_id: UUID | str) -> list[PlaygroundPeriod]: ...

    def ensure_period(
        self,
        user_id: UUID | str,
        *,
        period_start: date,
        period_end: date,
        tier_snapshot: str | None,
        law_limit: int | None,
        now: datetime | None = None,
    ) -> PlaygroundPeriod: ...

    def get_item(
        self, user_id: UUID | str, period_start: date, law_id: str
    ) -> RosterItem | None: ...

    def list_items(
        self, user_id: UUID | str, period_start: date
    ) -> list[RosterItem]: ...

    def count_consumed(self, user_id: UUID | str, period_start: date) -> int: ...

    def consume_law(
        self,
        user_id: UUID | str,
        *,
        period_start: date,
        law_id: str,
        law_limit: int | None,
        allow_new: bool,
        now: datetime | None = None,
    ) -> ConsumeResult: ...

    def remove_law(
        self,
        user_id: UUID | str,
        *,
        period_start: date,
        law_id: str,
        now: datetime | None = None,
    ) -> RosterItem | None: ...


class SqliteRosterRepository:
    """SQLite persistence. Consume uses BEGIN IMMEDIATE, not check-then-insert."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._lock = threading.Lock()
        try:
            self._conn.execute("PRAGMA busy_timeout = 8000")
        except sqlite3.Error:
            pass

    def get_period(
        self, user_id: UUID | str, period_start: date
    ) -> PlaygroundPeriod | None:
        uid = as_user_id(user_id)
        row = self._conn.execute(
            _PERIOD_SELECT + " WHERE user_id = ? AND period_start = ?",
            (uid, _date_iso(period_start)),
        ).fetchone()
        return period_from_mapping(row) if row is not None else None

    def list_periods(self, user_id: UUID | str) -> list[PlaygroundPeriod]:
        uid = as_user_id(user_id)
        rows = self._conn.execute(
            _PERIOD_SELECT + " WHERE user_id = ? ORDER BY period_start ASC",
            (uid,),
        ).fetchall()
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
        stamp = _dt_iso(clock)
        start = _date_iso(period_start)
        end = _date_iso(period_end)
        with self._exclusive():
            self._conn.execute(
                """
                UPDATE user_playground_period
                SET status = ?, updated_at = ?
                WHERE user_id = ? AND status = ? AND period_start < ?
                """,
                (PERIOD_STATUS_CLOSED, stamp, uid, PERIOD_STATUS_ACTIVE, start),
            )
            existing = self._conn.execute(
                _PERIOD_SELECT + " WHERE user_id = ? AND period_start = ?",
                (uid, start),
            ).fetchone()
            if existing is None:
                period_id = str(uuid4())
                try:
                    self._conn.execute(
                        """
                        INSERT INTO user_playground_period (
                            id, user_id, period_start, period_end, tier_snapshot,
                            law_limit, status, confirmed_at, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            period_id,
                            uid,
                            start,
                            end,
                            tier_snapshot,
                            law_limit,
                            PERIOD_STATUS_ACTIVE,
                            stamp,
                            stamp,
                            stamp,
                        ),
                    )
                except sqlite3.IntegrityError:
                    pass
                existing = self._conn.execute(
                    _PERIOD_SELECT + " WHERE user_id = ? AND period_start = ?",
                    (uid, start),
                ).fetchone()
            period = period_from_mapping(existing)
            updates: list[str] = []
            params: list[Any] = []
            if period.tier_snapshot != tier_snapshot or period.law_limit != law_limit:
                updates.extend(["tier_snapshot = ?", "law_limit = ?"])
                params.extend([tier_snapshot, law_limit])
            if period.status != PERIOD_STATUS_ACTIVE:
                updates.append("status = ?")
                params.append(PERIOD_STATUS_ACTIVE)
                if period.confirmed_at is None:
                    updates.append("confirmed_at = ?")
                    params.append(stamp)
            if updates:
                updates.append("updated_at = ?")
                params.append(stamp)
                params.extend([uid, start])
                self._conn.execute(
                    f"""
                    UPDATE user_playground_period
                    SET {", ".join(updates)}
                    WHERE user_id = ? AND period_start = ?
                    """,
                    params,
                )
                existing = self._conn.execute(
                    _PERIOD_SELECT + " WHERE user_id = ? AND period_start = ?",
                    (uid, start),
                ).fetchone()
                period = period_from_mapping(existing)
            return period

    def get_item(
        self, user_id: UUID | str, period_start: date, law_id: str
    ) -> RosterItem | None:
        uid = as_user_id(user_id)
        row = self._conn.execute(
            _ITEM_SELECT + " WHERE user_id = ? AND period_start = ? AND law_id = ?",
            (uid, _date_iso(period_start), law_id),
        ).fetchone()
        return item_from_mapping(row) if row is not None else None

    def list_items(
        self, user_id: UUID | str, period_start: date
    ) -> list[RosterItem]:
        uid = as_user_id(user_id)
        rows = self._conn.execute(
            _ITEM_SELECT
            + " WHERE user_id = ? AND period_start = ? ORDER BY created_at ASC, law_id ASC",
            (uid, _date_iso(period_start)),
        ).fetchall()
        return [item_from_mapping(row) for row in rows]

    def count_consumed(self, user_id: UUID | str, period_start: date) -> int:
        uid = as_user_id(user_id)
        row = self._conn.execute(
            """
            SELECT COUNT(DISTINCT law_id) AS n
            FROM user_playground_roster_item
            WHERE user_id = ? AND period_start = ? AND consumed_at IS NOT NULL
            """,
            (uid, _date_iso(period_start)),
        ).fetchone()
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
        uid = as_user_id(user_id)
        start = _date_iso(period_start)
        clock = _utc_now(now)
        stamp = _dt_iso(clock)
        with self._exclusive():
            period_row = self._conn.execute(
                _PERIOD_SELECT + " WHERE user_id = ? AND period_start = ?",
                (uid, start),
            ).fetchone()
            if period_row is None:
                return ConsumeResult(
                    status=RESULT_NEW_BLOCKED,
                    item=None,
                    used=0,
                    remaining=remaining_capacity(law_limit, 0),
                    period=None,
                )
            period = period_from_mapping(period_row)
            item_row = self._conn.execute(
                _ITEM_SELECT
                + " WHERE user_id = ? AND period_start = ? AND law_id = ?",
                (uid, start, law_id),
            ).fetchone()
            item = item_from_mapping(item_row) if item_row is not None else None
            used = self._count_consumed_locked(uid, start)
            remaining = remaining_capacity(period.law_limit, used)
            if item is not None and item.consumed_at is not None and item.removed_at is None:
                return ConsumeResult(
                    status=RESULT_ALREADY_ACTIVE,
                    item=item,
                    used=used,
                    remaining=remaining,
                    period=period,
                )
            if item is not None and item.consumed_at is not None and item.removed_at is not None:
                self._conn.execute(
                    """
                    UPDATE user_playground_roster_item
                    SET removed_at = NULL, origin = ?, updated_at = ?
                    WHERE user_id = ? AND period_start = ? AND law_id = ?
                    """,
                    (ORIGIN_RE_ADD, stamp, uid, start, law_id),
                )
                refreshed = item_from_mapping(
                    self._conn.execute(
                        _ITEM_SELECT
                        + " WHERE user_id = ? AND period_start = ? AND law_id = ?",
                        (uid, start, law_id),
                    ).fetchone()
                )
                return ConsumeResult(
                    status=RESULT_RE_ADDED,
                    item=refreshed,
                    used=used,
                    remaining=remaining,
                    period=period,
                )
            if not allow_new:
                return ConsumeResult(
                    status=RESULT_NEW_BLOCKED,
                    item=item,
                    used=used,
                    remaining=remaining,
                    period=period,
                )
            cap = period.law_limit
            if cap is not None and used >= cap:
                return ConsumeResult(
                    status=RESULT_ROSTER_FULL,
                    item=item,
                    used=used,
                    remaining=0,
                    period=period,
                )
            if item is not None:
                self._conn.execute(
                    """
                    UPDATE user_playground_roster_item
                    SET consumed_at = ?, removed_at = NULL, origin = ?,
                        updated_at = ?
                    WHERE user_id = ? AND period_start = ? AND law_id = ?
                    """,
                    (stamp, ORIGIN_NEW, stamp, uid, start, law_id),
                )
            else:
                try:
                    self._conn.execute(
                        """
                        INSERT INTO user_playground_roster_item (
                            id, user_id, period_start, law_id, origin,
                            carried_from_previous_period, consumed_at, removed_at,
                            declined_at, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, 0, ?, NULL, NULL, ?, ?)
                        """,
                        (
                            str(uuid4()),
                            uid,
                            start,
                            law_id,
                            ORIGIN_NEW,
                            stamp,
                            stamp,
                            stamp,
                        ),
                    )
                except sqlite3.IntegrityError:
                    existing = self._conn.execute(
                        _ITEM_SELECT
                        + " WHERE user_id = ? AND period_start = ? AND law_id = ?",
                        (uid, start, law_id),
                    ).fetchone()
                    stored = item_from_mapping(existing) if existing is not None else None
                    used = self._count_consumed_locked(uid, start)
                    if stored is not None and stored.consumed_at is not None:
                        if stored.removed_at is None:
                            return ConsumeResult(
                                status=RESULT_ALREADY_ACTIVE,
                                item=stored,
                                used=used,
                                remaining=remaining_capacity(period.law_limit, used),
                                period=period,
                            )
                    raise
            stored_row = self._conn.execute(
                _ITEM_SELECT + " WHERE user_id = ? AND period_start = ? AND law_id = ?",
                (uid, start, law_id),
            ).fetchone()
            stored_item = item_from_mapping(stored_row)
            used = self._count_consumed_locked(uid, start)
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
        start = _date_iso(period_start)
        clock = _utc_now(now)
        stamp = _dt_iso(clock)
        with self._exclusive():
            item_row = self._conn.execute(
                _ITEM_SELECT
                + " WHERE user_id = ? AND period_start = ? AND law_id = ?",
                (uid, start, law_id),
            ).fetchone()
            if item_row is None:
                return None
            item = item_from_mapping(item_row)
            if item.consumed_at is None:
                return item
            if item.removed_at is not None:
                return item
            self._conn.execute(
                """
                UPDATE user_playground_roster_item
                SET removed_at = ?, updated_at = ?
                WHERE user_id = ? AND period_start = ? AND law_id = ?
                """,
                (stamp, stamp, uid, start, law_id),
            )
            refreshed = self._conn.execute(
                _ITEM_SELECT
                + " WHERE user_id = ? AND period_start = ? AND law_id = ?",
                (uid, start, law_id),
            ).fetchone()
            return item_from_mapping(refreshed)

    def _count_consumed_locked(self, uid: str, period_start: str) -> int:
        row = self._conn.execute(
            """
            SELECT COUNT(DISTINCT law_id) AS n
            FROM user_playground_roster_item
            WHERE user_id = ? AND period_start = ? AND consumed_at IS NOT NULL
            """,
            (uid, period_start),
        ).fetchone()
        return int(row["n"] if row is not None else 0)

    @contextmanager
    def _exclusive(self) -> Iterator[None]:
        with self._lock:
            started = False
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                started = True
            except sqlite3.OperationalError as exc:
                if "within a transaction" not in str(exc).lower():
                    raise
                started = False
            try:
                yield
                self._conn.commit()
            except Exception:
                if started:
                    try:
                        self._conn.rollback()
                    except sqlite3.Error:
                        pass
                raise
