"""SQLite monthly roster. Owner methods always require ``user_id``.

Capacity consume uses BEGIN IMMEDIATE. Do not count outside the transaction.
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import date, datetime, timezone
from typing import Any, Callable, Iterator, Protocol
from uuid import UUID, uuid4

from constitution_memorizer.playground.repo_counters import count_playground_repo_call
from constitution_memorizer.playground.roster.decisions import plan_rollover_batch
from constitution_memorizer.playground.roster.models import (
    CHOICE_SOURCE_FREE_ADD,
    ORIGIN_CARRY_FORWARD,
    ORIGIN_NEW,
    ORIGIN_RE_ADD,
    PERIOD_STATUS_ACTIVE,
    PERIOD_STATUS_CLOSED,
    PERIOD_STATUS_DRAFT,
    RESULT_ALREADY_ACTIVE,
    RESULT_FREE_CHOICES_EXHAUSTED,
    RESULT_NEW_BLOCKED,
    RESULT_OK,
    RESULT_RE_ADDED,
    RESULT_ROSTER_FULL,
    mark_save_rolled_back,
    ConsumeResult,
    PlaygroundPeriod,
    RolloverResult,
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
        carry_from_latest_active: bool = False,
    ) -> PlaygroundPeriod: ...

    def latest_active_period(self, user_id: UUID | str) -> PlaygroundPeriod | None: ...

    # Permanent-choice ledger (``choices`` model). Read-only here; the only
    # writer is ``consume_law(ledger=True)``.
    def count_choices(self, user_id: UUID | str) -> int: ...

    def has_choice(self, user_id: UUID | str, law_id: str) -> bool: ...

    def list_choices(self, user_id: UUID | str) -> list[str]: ...

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
        origin_for_new: str = ORIGIN_NEW,
        now: datetime | None = None,
        enforce_effective_limit: bool = False,
        ledger: bool = False,
        choice_limit: int | None = None,
        choice_source: str = CHOICE_SOURCE_FREE_ADD,
        within: Callable[[Any], None] | None = None,
    ) -> ConsumeResult: ...

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
    ) -> RolloverResult: ...

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

    @count_playground_repo_call(kind="read", domain="roster")
    def get_period(
        self, user_id: UUID | str, period_start: date
    ) -> PlaygroundPeriod | None:
        uid = as_user_id(user_id)
        with self._lock:
            row = self._conn.execute(
                _PERIOD_SELECT + " WHERE user_id = ? AND period_start = ?",
                (uid, _date_iso(period_start)),
            ).fetchone()
        return period_from_mapping(row) if row is not None else None

    @count_playground_repo_call(kind="read", domain="roster")
    def list_periods(self, user_id: UUID | str) -> list[PlaygroundPeriod]:
        uid = as_user_id(user_id)
        with self._lock:
            rows = self._conn.execute(
                _PERIOD_SELECT + " WHERE user_id = ? ORDER BY period_start ASC",
                (uid,),
            ).fetchall()
        return [period_from_mapping(row) for row in rows]

    @count_playground_repo_call(kind="write")
    def ensure_period(
        self,
        user_id: UUID | str,
        *,
        period_start: date,
        period_end: date,
        tier_snapshot: str | None,
        law_limit: int | None,
        now: datetime | None = None,
        carry_from_latest_active: bool = False,
    ) -> PlaygroundPeriod:
        uid = as_user_id(user_id)
        clock = _utc_now(now)
        stamp = _dt_iso(clock)
        start = _date_iso(period_start)
        end = _date_iso(period_end)
        with self._exclusive():
            return self._ensure_period_locked(
                uid,
                start=start,
                end=end,
                tier_snapshot=tier_snapshot,
                law_limit=law_limit,
                stamp=stamp,
                carry=carry_from_latest_active,
            )

    @count_playground_repo_call(kind="read", domain="roster")
    def latest_active_period(self, user_id: UUID | str) -> PlaygroundPeriod | None:
        uid = as_user_id(user_id)
        row = self._conn.execute(
            _PERIOD_SELECT
            + " WHERE user_id = ? AND status = ? ORDER BY period_start DESC LIMIT 1",
            (uid, PERIOD_STATUS_ACTIVE),
        ).fetchone()
        return period_from_mapping(row) if row is not None else None

    @count_playground_repo_call(kind="read", domain="roster")
    def count_choices(self, user_id: UUID | str) -> int:
        return self._count_choices_locked(as_user_id(user_id))

    @count_playground_repo_call(kind="read", domain="roster")
    def has_choice(self, user_id: UUID | str, law_id: str) -> bool:
        return self._has_choice_locked(as_user_id(user_id), law_id)

    @count_playground_repo_call(kind="read", domain="roster")
    def list_choices(self, user_id: UUID | str) -> list[str]:
        rows = self._conn.execute(
            "SELECT law_id FROM user_playground_choice WHERE user_id = ? ORDER BY chosen_at ASC, law_id ASC",
            (as_user_id(user_id),),
        ).fetchall()
        return [str(row["law_id"]) for row in rows]

    def _count_choices_locked(self, uid: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(DISTINCT law_id) AS n FROM user_playground_choice WHERE user_id = ?",
            (uid,),
        ).fetchone()
        return int(row["n"] if row is not None else 0)

    def _has_choice_locked(self, uid: str, law_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM user_playground_choice WHERE user_id = ? AND law_id = ? LIMIT 1",
            (uid, law_id),
        ).fetchone()
        return row is not None

    def _record_choice_locked(self, uid: str, law_id: str, *, source: str, stamp: str) -> bool:
        """Append one ledger row. Never updates or deletes. Returns True if new."""

        before = self._has_choice_locked(uid, law_id)
        if before:
            return False
        self._conn.execute(
            """
            INSERT OR IGNORE INTO user_playground_choice (id, user_id, law_id, chosen_at, source)
            VALUES (?, ?, ?, ?, ?)
            """,
            (str(uuid4()), uid, law_id, stamp, source),
        )
        return True

    def _carry_active_items_locked(self, uid: str, start: str, stamp: str) -> None:
        """Copy every *active* item of the latest earlier active period into
        ``start`` as ``carry_forward`` (decision 5-23). Removed laws are not
        carried (B1-F17). Caller holds the exclusive transaction."""

        source = self._conn.execute(
            _PERIOD_SELECT
            + " WHERE user_id = ? AND status = ? AND period_start < ?"
            " ORDER BY period_start DESC LIMIT 1",
            (uid, PERIOD_STATUS_ACTIVE, start),
        ).fetchone()
        if source is None:
            return
        source_start = _date_iso(period_from_mapping(source).period_start)
        rows = self._conn.execute(
            _ITEM_SELECT
            + " WHERE user_id = ? AND period_start = ?"
            " AND consumed_at IS NOT NULL AND removed_at IS NULL",
            (uid, source_start),
        ).fetchall()
        for row in rows:
            self._conn.execute(
                """
                INSERT OR IGNORE INTO user_playground_roster_item (
                    id, user_id, period_start, law_id, origin,
                    carried_from_previous_period, consumed_at, removed_at,
                    declined_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 1, ?, NULL, NULL, ?, ?)
                """,
                (
                    str(uuid4()),
                    uid,
                    start,
                    str(row["law_id"]),
                    ORIGIN_CARRY_FORWARD,
                    stamp,
                    stamp,
                    stamp,
                ),
            )

    @count_playground_repo_call(kind="read", domain="roster")
    def get_item(
        self, user_id: UUID | str, period_start: date, law_id: str
    ) -> RosterItem | None:
        uid = as_user_id(user_id)
        with self._lock:
            row = self._conn.execute(
                _ITEM_SELECT + " WHERE user_id = ? AND period_start = ? AND law_id = ?",
                (uid, _date_iso(period_start), law_id),
            ).fetchone()
        return item_from_mapping(row) if row is not None else None

    @count_playground_repo_call(kind="read", domain="roster")
    def list_items(
        self, user_id: UUID | str, period_start: date
    ) -> list[RosterItem]:
        uid = as_user_id(user_id)
        with self._lock:
            rows = self._conn.execute(
                _ITEM_SELECT
                + " WHERE user_id = ? AND period_start = ? ORDER BY created_at ASC, law_id ASC",
                (uid, _date_iso(period_start)),
            ).fetchall()
        return [item_from_mapping(row) for row in rows]

    @count_playground_repo_call(kind="read", domain="roster")
    def count_consumed(self, user_id: UUID | str, period_start: date) -> int:
        uid = as_user_id(user_id)
        with self._lock:
            row = self._conn.execute(
                """
                SELECT COUNT(DISTINCT law_id) AS n
                FROM user_playground_roster_item
                WHERE user_id = ? AND period_start = ? AND consumed_at IS NOT NULL
                """,
                (uid, _date_iso(period_start)),
            ).fetchone()
        return int(row["n"] if row is not None else 0)

    @count_playground_repo_call(kind="write")
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
        enforce_effective_limit: bool = False,
        ledger: bool = False,
        choice_limit: int | None = None,
        choice_source: str = CHOICE_SOURCE_FREE_ADD,
        within: Callable[[Any], None] | None = None,
    ) -> ConsumeResult:
        """Atomic consume / re-add.

        ``within`` (5-19 / B1-F08): a callable run on this same open
        transaction after the roster item (and ledger row) are written and
        before the commit — the overlay membership and the selection. If it
        raises, everything in the transaction rolls back together and the
        error propagates; it is not run on blocked or already-active
        outcomes. ``ConsumeResult.within_applied`` says whether it ran.

        ``enforce_effective_limit`` makes the cap the caller's ``law_limit``
        (the resolver's effective limit) instead of the stored row value, so a
        stale 10/30 on an old period row cannot block an unlimited tier
        (B1-F16 check 3). ``ledger`` turns on the permanent Free-choice
        ledger: a law already in the ledger is re-added at no cost; a new law
        is refused with ``free_choices_exhausted`` at ``choice_limit``;
        otherwise one ledger row is appended in the same transaction as the
        roster item (B1-F03/F05/F18).
        """

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
            cap = law_limit if enforce_effective_limit else period.law_limit
            remaining = remaining_capacity(cap, used)
            choices_used = self._count_choices_locked(uid) if ledger else None
            in_ledger = self._has_choice_locked(uid, law_id) if ledger else False
            if ledger:
                used = int(choices_used or 0)
                remaining = remaining_capacity(choice_limit, used)

            def _result(
                status: str,
                row: RosterItem | None,
                *,
                recorded: bool = False,
                applied: bool = False,
            ) -> ConsumeResult:
                used_now = self._count_choices_locked(uid) if ledger else self._count_consumed_locked(uid, start)
                return ConsumeResult(
                    status=status,
                    item=row,
                    used=used_now,
                    remaining=remaining_capacity(choice_limit if ledger else cap, used_now),
                    period=period,
                    choices_used=used_now if ledger else None,
                    choice_limit=choice_limit if ledger else None,
                    choice_recorded=recorded,
                    within_applied=applied,
                )

            def _apply_within() -> bool:
                # Same connection, same ``BEGIN IMMEDIATE``: the overlay write
                # commits or rolls back with the roster item (B1-F08).
                if within is None:
                    return False
                within(self._conn)
                return True

            if item is not None and item.consumed_at is not None and item.removed_at is None:
                return _result(RESULT_ALREADY_ACTIVE, item)
            if item is not None and item.consumed_at is not None and item.removed_at is not None:
                self._conn.execute(
                    """
                    UPDATE user_playground_roster_item
                    SET removed_at = NULL, declined_at = NULL, origin = ?, updated_at = ?
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
                return _result(RESULT_RE_ADDED, refreshed, applied=_apply_within())
            readd_free = bool(ledger and in_ledger)
            if not readd_free:
                # Ledger exhaustion is reported as such even though the
                # resolver also cleared ``allow_new`` for it (B1-F02).
                if ledger and choice_limit is not None and int(choices_used or 0) >= choice_limit:
                    return _result(RESULT_FREE_CHOICES_EXHAUSTED, item)
                if not allow_new:
                    return _result(RESULT_NEW_BLOCKED, item)
                if cap is not None and self._count_consumed_locked(uid, start) >= cap:
                    return _result(RESULT_ROSTER_FULL, item)
            origin = ORIGIN_RE_ADD if readd_free else origin_for_new
            if item is not None:
                self._conn.execute(
                    """
                    UPDATE user_playground_roster_item
                    SET consumed_at = ?, removed_at = NULL, declined_at = NULL,
                        origin = ?, updated_at = ?
                    WHERE user_id = ? AND period_start = ? AND law_id = ?
                    """,
                    (stamp, origin, stamp, uid, start, law_id),
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
                            origin,
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
            recorded = False
            if ledger and not readd_free:
                recorded = self._record_choice_locked(
                    uid, law_id, source=choice_source, stamp=stamp
                )
            applied = _apply_within()
            return _result(
                RESULT_RE_ADDED if readd_free else RESULT_OK,
                stored_item,
                recorded=recorded,
                applied=applied,
            )

    @count_playground_repo_call(kind="write")
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

    def _ensure_period_locked(
        self,
        uid: str,
        *,
        start: str,
        end: str,
        tier_snapshot: str | None,
        law_limit: int | None,
        stamp: str | None,
        carry: bool = False,
    ) -> PlaygroundPeriod:
        """Insert or reconcile one period. Caller holds ``BEGIN IMMEDIATE``.

        A prepared draft whose Keep count exceeds the reconciled limit stays
        ``draft``. It is not promoted and older active periods are left as
        they are. Every other current-month visit promotes or stays active
        and closes older active periods.
        """

        existing = self._conn.execute(
            _PERIOD_SELECT + " WHERE user_id = ? AND period_start = ?",
            (uid, start),
        ).fetchone()
        if existing is None:
            try:
                self._conn.execute(
                    """
                    INSERT INTO user_playground_period (
                        id, user_id, period_start, period_end, tier_snapshot,
                        law_limit, status, confirmed_at, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid4()),
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
            if carry:
                self._carry_active_items_locked(uid, start, stamp or "")
            self._close_older_active(uid, start, stamp)
            row = self._conn.execute(
                _PERIOD_SELECT + " WHERE user_id = ? AND period_start = ?",
                (uid, start),
            ).fetchone()
            return period_from_mapping(row)
        period = period_from_mapping(existing)
        used = self._count_consumed_locked(uid, start)
        hold_draft = (
            period.status == PERIOD_STATUS_DRAFT
            and law_limit is not None
            and used > law_limit
        )
        if hold_draft:
            self._conn.execute(
                """
                UPDATE user_playground_period
                SET tier_snapshot = ?, law_limit = ?, updated_at = ?
                WHERE user_id = ? AND period_start = ?
                """,
                (tier_snapshot, law_limit, stamp, uid, start),
            )
            row = self._conn.execute(
                _PERIOD_SELECT + " WHERE user_id = ? AND period_start = ?",
                (uid, start),
            ).fetchone()
            return period_from_mapping(row)
        confirmed = stamp if period.confirmed_at is None else _dt_iso(period.confirmed_at)
        if carry and period.status == PERIOD_STATUS_DRAFT:
            # Promoting a pre-existing draft under ``choices``: every active
            # item of the latest active period continues (5-23); decisions
            # already recorded on the draft are left as they are.
            self._carry_active_items_locked(uid, start, stamp or "")
        self._conn.execute(
            """
            UPDATE user_playground_period
            SET tier_snapshot = ?, law_limit = ?, status = ?, confirmed_at = ?,
                updated_at = ?
            WHERE user_id = ? AND period_start = ?
            """,
            (
                tier_snapshot,
                law_limit,
                PERIOD_STATUS_ACTIVE,
                confirmed,
                stamp,
                uid,
                start,
            ),
        )
        self._close_older_active(uid, start, stamp)
        row = self._conn.execute(
            _PERIOD_SELECT + " WHERE user_id = ? AND period_start = ?",
            (uid, start),
        ).fetchone()
        return period_from_mapping(row)

    def _close_older_active(self, uid: str, start: str, stamp: str | None) -> None:
        self._conn.execute(
            """
            UPDATE user_playground_period
            SET status = ?, updated_at = ?
            WHERE user_id = ? AND status = ? AND period_start < ?
            """,
            (PERIOD_STATUS_CLOSED, stamp, uid, PERIOD_STATUS_ACTIVE, start),
        )

    @count_playground_repo_call(kind="write")
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
        start = _date_iso(period_start)
        end = _date_iso(period_end)
        stamp = _dt_iso(_utc_now(now))

        class _Abort(Exception):
            def __init__(self, result: RolloverResult) -> None:
                self.result = result

        try:
            with self._exclusive():
                existing = self._conn.execute(
                    _PERIOD_SELECT + " WHERE user_id = ? AND period_start = ?",
                    (uid, start),
                ).fetchone()
                period = period_from_mapping(existing) if existing is not None else None
                status = (
                    period.status
                    if period is not None
                    else (PERIOD_STATUS_ACTIVE if activate else PERIOD_STATUS_DRAFT)
                )
                item_rows = self._conn.execute(
                    _ITEM_SELECT + " WHERE user_id = ? AND period_start = ?",
                    (uid, start),
                ).fetchall()
                items = {row["law_id"]: item_from_mapping(row) for row in item_rows}
                used = self._count_consumed_locked(uid, start)
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
                if not plan.ok:
                    raise _Abort(
                        RolloverResult(
                            status=plan.status,
                            used=used,
                            remaining=remaining_capacity(law_limit, used),
                            period=period,
                            adjustment_required=(
                                period is not None
                                and period.status == PERIOD_STATUS_DRAFT
                                and law_limit is not None
                                and used > law_limit
                            ),
                        )
                    )
                if period is None and not plan.writes:
                    raise _Abort(
                        RolloverResult(
                            status=RESULT_OK,
                            used=0,
                            remaining=remaining_capacity(law_limit, 0),
                            period=None,
                        )
                    )
                if period is None:
                    self._conn.execute(
                        """
                        INSERT INTO user_playground_period (
                            id, user_id, period_start, period_end, tier_snapshot,
                            law_limit, status, confirmed_at, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            str(uuid4()),
                            uid,
                            start,
                            end,
                            tier_snapshot,
                            law_limit,
                            PERIOD_STATUS_DRAFT if not activate else PERIOD_STATUS_ACTIVE,
                            stamp if activate else None,
                            stamp,
                            stamp,
                        ),
                    )
                for write in plan.writes:
                    self._write_rollover_decision(
                        uid, start, write.law_id, keep=write.keep, stamp=stamp
                    )
                used_now = self._count_consumed_locked(uid, start)
                over = law_limit is not None and used_now > law_limit
                if activate and not over:
                    self._conn.execute(
                        """
                        UPDATE user_playground_period
                        SET tier_snapshot = ?, law_limit = ?, status = ?,
                            confirmed_at = COALESCE(confirmed_at, ?), updated_at = ?
                        WHERE user_id = ? AND period_start = ?
                        """,
                        (
                            tier_snapshot,
                            law_limit,
                            PERIOD_STATUS_ACTIVE,
                            stamp,
                            stamp,
                            uid,
                            start,
                        ),
                    )
                    self._close_older_active(uid, start, stamp)
                else:
                    self._conn.execute(
                        """
                        UPDATE user_playground_period
                        SET tier_snapshot = ?, law_limit = ?, updated_at = ?
                        WHERE user_id = ? AND period_start = ?
                        """,
                        (tier_snapshot, law_limit, stamp, uid, start),
                    )
                row = self._conn.execute(
                    _PERIOD_SELECT + " WHERE user_id = ? AND period_start = ?",
                    (uid, start),
                ).fetchone()
                stored = period_from_mapping(row)
                return RolloverResult(
                    status=RESULT_OK,
                    used=used_now,
                    remaining=remaining_capacity(stored.law_limit, used_now),
                    period=stored,
                    adjustment_required=stored.status == PERIOD_STATUS_DRAFT and over,
                )
        except _Abort as exc:
            return exc.result

    def _write_rollover_decision(
        self,
        uid: str,
        start: str,
        law_id: str,
        *,
        keep: bool,
        stamp: str | None,
    ) -> None:
        consumed = stamp if keep else None
        declined = None if keep else stamp
        existing = self._conn.execute(
            _ITEM_SELECT + " WHERE user_id = ? AND period_start = ? AND law_id = ?",
            (uid, start, law_id),
        ).fetchone()
        if existing is None:
            self._conn.execute(
                """
                INSERT INTO user_playground_roster_item (
                    id, user_id, period_start, law_id, origin,
                    carried_from_previous_period, consumed_at, removed_at,
                    declined_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 1, ?, NULL, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    uid,
                    start,
                    law_id,
                    ORIGIN_CARRY_FORWARD,
                    consumed,
                    declined,
                    stamp,
                    stamp,
                ),
            )
            return
        self._conn.execute(
            """
            UPDATE user_playground_roster_item
            SET origin = ?, carried_from_previous_period = 1,
                consumed_at = ?, removed_at = NULL, declined_at = ?, updated_at = ?
            WHERE user_id = ? AND period_start = ? AND law_id = ?
            """,
            (
                ORIGIN_CARRY_FORWARD,
                consumed,
                declined,
                stamp,
                uid,
                start,
                law_id,
            ),
        )

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
            except Exception as exc:
                # Failure *before commit began*: a successful rollback of
                # this still-active transaction is evidence (B1-F07).
                if started:
                    try:
                        self._conn.rollback()
                    except sqlite3.Error:
                        raise  # no rollback evidence: the caller re-reads
                    mark_save_rolled_back(exc)
                raise
            try:
                self._conn.commit()
            except Exception:
                # Commit had begun: the transaction may or may not be
                # durable. Never mark; a later rollback() returning
                # normally proves nothing once commit started.
                if started:
                    try:
                        self._conn.rollback()
                    except sqlite3.Error:
                        pass
                raise
