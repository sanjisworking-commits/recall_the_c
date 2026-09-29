"""Persistence for Google Calendar connections and per-date event mappings.

Domain-owned store with dual SQLite/Postgres implementations (admin-store
pattern) so ``ReminderRepositoryProtocol`` stays untouched. All rows are
user-scoped; disconnect tombstones the connection (keeps the row and the
app-created ``google_calendar_id``, clears the sealed token) so a later
reconnect can reuse the same calendar via ``Calendars.get``.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Protocol
from uuid import UUID

from constitution_memorizer.progress.user_ids import as_user_id

SYNC_OK = "ok"
SYNC_ERROR = "error"
SYNC_PENDING = "pending"
SYNC_DISCONNECTED = "disconnected"


@dataclass(frozen=True)
class CalendarConnection:
    user_id: str
    google_calendar_id: str | None
    refresh_token_sealed: str | None
    sync_status: str
    sync_pending: bool
    sync_requested_at: datetime | None
    last_synced_at: datetime | None
    last_error: str | None
    connected_at: datetime | None

    @property
    def is_active(self) -> bool:
        return (
            self.sync_status != SYNC_DISCONNECTED
            and self.refresh_token_sealed is not None
        )


@dataclass(frozen=True)
class EventMapping:
    local_date: date
    google_event_id: str
    content_hash: str


class CalendarStore(Protocol):
    def get_connection(self, user_id: UUID | str) -> CalendarConnection | None: ...

    def upsert_connection(
        self,
        user_id: UUID | str,
        *,
        google_calendar_id: str | None,
        refresh_token_sealed: str | None,
        sync_status: str,
    ) -> None: ...

    def set_refresh_token(
        self, user_id: UUID | str, refresh_token_sealed: str | None
    ) -> None: ...

    def set_calendar_id(self, user_id: UUID | str, google_calendar_id: str) -> None: ...

    def mark_sync_pending(self, user_id: UUID | str) -> None: ...

    def mark_sync_pending_if_active(self, user_id: UUID | str) -> bool: ...

    def mark_sync_result(
        self, user_id: UUID | str, *, ok: bool, error: str | None = None
    ) -> None: ...

    def tombstone(self, user_id: UUID | str) -> None: ...

    def list_event_mappings(self, user_id: UUID | str) -> list[EventMapping]: ...

    def upsert_event_mapping(
        self,
        user_id: UUID | str,
        *,
        local_date: date,
        google_event_id: str,
        content_hash: str,
    ) -> None: ...

    def delete_event_mapping(self, user_id: UUID | str, local_date: date) -> None: ...

    def delete_all_event_mappings(self, user_id: UUID | str) -> None: ...

    def delete_user_data(self, user_id: UUID | str) -> None: ...


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _parse_ts(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _parse_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return date.fromisoformat(str(value)[:10])


def _row_connection(row: Any) -> CalendarConnection:
    return CalendarConnection(
        user_id=str(row["user_id"]),
        google_calendar_id=(
            str(row["google_calendar_id"])
            if row["google_calendar_id"] is not None
            else None
        ),
        refresh_token_sealed=(
            str(row["refresh_token_sealed"])
            if row["refresh_token_sealed"] is not None
            else None
        ),
        sync_status=str(row["sync_status"]),
        sync_pending=bool(row["sync_pending"]),
        sync_requested_at=_parse_ts(row["sync_requested_at"]),
        last_synced_at=_parse_ts(row["last_synced_at"]),
        last_error=(
            str(row["last_error"]) if row["last_error"] is not None else None
        ),
        connected_at=_parse_ts(row["connected_at"]),
    )


class SqliteCalendarStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get_connection(self, user_id: UUID | str) -> CalendarConnection | None:
        row = self._conn.execute(
            "SELECT * FROM google_calendar_connections WHERE user_id = ?",
            (as_user_id(user_id),),
        ).fetchone()
        return _row_connection(row) if row is not None else None

    def upsert_connection(
        self,
        user_id: UUID | str,
        *,
        google_calendar_id: str | None,
        refresh_token_sealed: str | None,
        sync_status: str,
    ) -> None:
        now = _utcnow().isoformat()
        self._conn.execute(
            """
            INSERT INTO google_calendar_connections (
                user_id, google_calendar_id, refresh_token_sealed, sync_status,
                sync_pending, connected_at, updated_at
            )
            VALUES (?, ?, ?, ?, 0, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                google_calendar_id = COALESCE(excluded.google_calendar_id,
                                              google_calendar_connections.google_calendar_id),
                refresh_token_sealed = excluded.refresh_token_sealed,
                sync_status = excluded.sync_status,
                last_error = NULL,
                connected_at = excluded.connected_at,
                updated_at = excluded.updated_at
            """,
            (
                as_user_id(user_id),
                google_calendar_id,
                refresh_token_sealed,
                sync_status,
                now,
                now,
            ),
        )
        self._conn.commit()

    def set_refresh_token(
        self, user_id: UUID | str, refresh_token_sealed: str | None
    ) -> None:
        self._conn.execute(
            "UPDATE google_calendar_connections SET refresh_token_sealed = ?, "
            "updated_at = ? WHERE user_id = ?",
            (refresh_token_sealed, _utcnow().isoformat(), as_user_id(user_id)),
        )
        self._conn.commit()

    def set_calendar_id(self, user_id: UUID | str, google_calendar_id: str) -> None:
        self._conn.execute(
            "UPDATE google_calendar_connections SET google_calendar_id = ?, "
            "updated_at = ? WHERE user_id = ?",
            (google_calendar_id, _utcnow().isoformat(), as_user_id(user_id)),
        )
        self._conn.commit()

    def mark_sync_pending(self, user_id: UUID | str) -> None:
        now = _utcnow().isoformat()
        self._conn.execute(
            "UPDATE google_calendar_connections SET sync_pending = 1, "
            "sync_requested_at = ?, updated_at = ? WHERE user_id = ?",
            (now, now, as_user_id(user_id)),
        )
        self._conn.commit()

    def mark_sync_pending_if_active(self, user_id: UUID | str) -> bool:
        now = _utcnow().isoformat()
        cur = self._conn.execute(
            "UPDATE google_calendar_connections SET sync_pending = 1, "
            "sync_requested_at = ?, updated_at = ? "
            "WHERE user_id = ? AND sync_status != ? "
            "AND refresh_token_sealed IS NOT NULL",
            (now, now, as_user_id(user_id), SYNC_DISCONNECTED),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def mark_sync_result(
        self, user_id: UUID | str, *, ok: bool, error: str | None = None
    ) -> None:
        now = _utcnow().isoformat()
        if ok:
            self._conn.execute(
                "UPDATE google_calendar_connections SET sync_pending = 0, "
                "sync_status = ?, last_synced_at = ?, last_error = NULL, "
                "updated_at = ? WHERE user_id = ?",
                (SYNC_OK, now, now, as_user_id(user_id)),
            )
        else:
            # sync_pending stays 1 → the flag survives crashes and keeps the
            # sync retryable from the next trigger / settings view.
            self._conn.execute(
                "UPDATE google_calendar_connections SET sync_status = ?, "
                "last_error = ?, updated_at = ? WHERE user_id = ?",
                (SYNC_ERROR, (error or "")[:500] or None, now, as_user_id(user_id)),
            )
        self._conn.commit()

    def tombstone(self, user_id: UUID | str) -> None:
        """Disconnect: keep the row, calendar id AND event mappings.

        The events themselves remain in the user's Google calendar, so the
        mappings must survive the disconnect — wiping them would make every
        date look "missing" on reconnect and duplicate every event. Only
        account deletion (delete_user_data) removes mappings.
        """
        uid = as_user_id(user_id)
        self._conn.execute(
            "UPDATE google_calendar_connections SET refresh_token_sealed = NULL, "
            "sync_status = ?, sync_pending = 0, last_error = NULL, updated_at = ? "
            "WHERE user_id = ?",
            (SYNC_DISCONNECTED, _utcnow().isoformat(), uid),
        )
        self._conn.commit()

    def list_event_mappings(self, user_id: UUID | str) -> list[EventMapping]:
        rows = self._conn.execute(
            "SELECT local_date, google_event_id, content_hash "
            "FROM google_calendar_events WHERE user_id = ?",
            (as_user_id(user_id),),
        ).fetchall()
        return [
            EventMapping(
                local_date=_parse_date(r["local_date"]),
                google_event_id=str(r["google_event_id"]),
                content_hash=str(r["content_hash"]),
            )
            for r in rows
        ]

    def upsert_event_mapping(
        self,
        user_id: UUID | str,
        *,
        local_date: date,
        google_event_id: str,
        content_hash: str,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO google_calendar_events (
                user_id, local_date, google_event_id, content_hash, last_synced_at
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, local_date) DO UPDATE SET
                google_event_id = excluded.google_event_id,
                content_hash = excluded.content_hash,
                last_synced_at = excluded.last_synced_at
            """,
            (
                as_user_id(user_id),
                local_date.isoformat(),
                google_event_id,
                content_hash,
                _utcnow().isoformat(),
            ),
        )
        self._conn.commit()

    def delete_event_mapping(self, user_id: UUID | str, local_date: date) -> None:
        self._conn.execute(
            "DELETE FROM google_calendar_events WHERE user_id = ? AND local_date = ?",
            (as_user_id(user_id), local_date.isoformat()),
        )
        self._conn.commit()

    def delete_all_event_mappings(self, user_id: UUID | str) -> None:
        self._conn.execute(
            "DELETE FROM google_calendar_events WHERE user_id = ?",
            (as_user_id(user_id),),
        )
        self._conn.commit()

    def delete_user_data(self, user_id: UUID | str) -> None:
        """Account deletion: remove everything, including the tombstone."""
        uid = as_user_id(user_id)
        self._conn.execute(
            "DELETE FROM google_calendar_events WHERE user_id = ?", (uid,)
        )
        self._conn.execute(
            "DELETE FROM google_calendar_connections WHERE user_id = ?", (uid,)
        )
        self._conn.commit()


class PostgresCalendarStore:
    def __init__(self, pool: Any) -> None:
        from psycopg.rows import dict_row

        self._pool = pool
        self._dict_row = dict_row

    def _fetchone(self, sql: str, params: tuple) -> Any:
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=self._dict_row) as cur:
                cur.execute(sql, params)
                return cur.fetchone()

    def _fetchall(self, sql: str, params: tuple) -> list[Any]:
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=self._dict_row) as cur:
                cur.execute(sql, params)
                return cur.fetchall()

    def _execute(self, statements: list[tuple[str, tuple]]) -> None:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                for sql, params in statements:
                    cur.execute(sql, params)
            conn.commit()

    def get_connection(self, user_id: UUID | str) -> CalendarConnection | None:
        row = self._fetchone(
            "SELECT * FROM google_calendar_connections WHERE user_id = %s",
            (as_user_id(user_id),),
        )
        return _row_connection(row) if row is not None else None

    def upsert_connection(
        self,
        user_id: UUID | str,
        *,
        google_calendar_id: str | None,
        refresh_token_sealed: str | None,
        sync_status: str,
    ) -> None:
        now = _utcnow()
        self._execute(
            [
                (
                    """
                    INSERT INTO google_calendar_connections (
                        user_id, google_calendar_id, refresh_token_sealed,
                        sync_status, sync_pending, connected_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, FALSE, %s, %s)
                    ON CONFLICT (user_id) DO UPDATE SET
                        google_calendar_id = COALESCE(EXCLUDED.google_calendar_id,
                            google_calendar_connections.google_calendar_id),
                        refresh_token_sealed = EXCLUDED.refresh_token_sealed,
                        sync_status = EXCLUDED.sync_status,
                        last_error = NULL,
                        connected_at = EXCLUDED.connected_at,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (
                        as_user_id(user_id),
                        google_calendar_id,
                        refresh_token_sealed,
                        sync_status,
                        now,
                        now,
                    ),
                )
            ]
        )

    def set_refresh_token(
        self, user_id: UUID | str, refresh_token_sealed: str | None
    ) -> None:
        self._execute(
            [
                (
                    "UPDATE google_calendar_connections SET refresh_token_sealed = %s, "
                    "updated_at = %s WHERE user_id = %s",
                    (refresh_token_sealed, _utcnow(), as_user_id(user_id)),
                )
            ]
        )

    def set_calendar_id(self, user_id: UUID | str, google_calendar_id: str) -> None:
        self._execute(
            [
                (
                    "UPDATE google_calendar_connections SET google_calendar_id = %s, "
                    "updated_at = %s WHERE user_id = %s",
                    (google_calendar_id, _utcnow(), as_user_id(user_id)),
                )
            ]
        )

    def mark_sync_pending(self, user_id: UUID | str) -> None:
        now = _utcnow()
        self._execute(
            [
                (
                    "UPDATE google_calendar_connections SET sync_pending = TRUE, "
                    "sync_requested_at = %s, updated_at = %s WHERE user_id = %s",
                    (now, now, as_user_id(user_id)),
                )
            ]
        )

    def mark_sync_pending_if_active(self, user_id: UUID | str) -> bool:
        now = _utcnow()
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE google_calendar_connections SET sync_pending = TRUE, "
                    "sync_requested_at = %s, updated_at = %s "
                    "WHERE user_id = %s AND sync_status <> %s "
                    "AND refresh_token_sealed IS NOT NULL",
                    (now, now, as_user_id(user_id), SYNC_DISCONNECTED),
                )
                changed = cur.rowcount > 0
            conn.commit()
        return changed

    def mark_sync_result(
        self, user_id: UUID | str, *, ok: bool, error: str | None = None
    ) -> None:
        now = _utcnow()
        if ok:
            self._execute(
                [
                    (
                        "UPDATE google_calendar_connections SET sync_pending = FALSE, "
                        "sync_status = %s, last_synced_at = %s, last_error = NULL, "
                        "updated_at = %s WHERE user_id = %s",
                        (SYNC_OK, now, now, as_user_id(user_id)),
                    )
                ]
            )
        else:
            self._execute(
                [
                    (
                        "UPDATE google_calendar_connections SET sync_status = %s, "
                        "last_error = %s, updated_at = %s WHERE user_id = %s",
                        (
                            SYNC_ERROR,
                            (error or "")[:500] or None,
                            now,
                            as_user_id(user_id),
                        ),
                    )
                ]
            )

    def tombstone(self, user_id: UUID | str) -> None:
        """Disconnect keeps event mappings — see SqliteCalendarStore.tombstone."""
        uid = as_user_id(user_id)
        self._execute(
            [
                (
                    "UPDATE google_calendar_connections SET refresh_token_sealed = NULL, "
                    "sync_status = %s, sync_pending = FALSE, last_error = NULL, "
                    "updated_at = %s WHERE user_id = %s",
                    (SYNC_DISCONNECTED, _utcnow(), uid),
                ),
            ]
        )

    def list_event_mappings(self, user_id: UUID | str) -> list[EventMapping]:
        rows = self._fetchall(
            "SELECT local_date, google_event_id, content_hash "
            "FROM google_calendar_events WHERE user_id = %s",
            (as_user_id(user_id),),
        )
        return [
            EventMapping(
                local_date=_parse_date(r["local_date"]),
                google_event_id=str(r["google_event_id"]),
                content_hash=str(r["content_hash"]),
            )
            for r in rows
        ]

    def upsert_event_mapping(
        self,
        user_id: UUID | str,
        *,
        local_date: date,
        google_event_id: str,
        content_hash: str,
    ) -> None:
        self._execute(
            [
                (
                    """
                    INSERT INTO google_calendar_events (
                        user_id, local_date, google_event_id, content_hash,
                        last_synced_at
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (user_id, local_date) DO UPDATE SET
                        google_event_id = EXCLUDED.google_event_id,
                        content_hash = EXCLUDED.content_hash,
                        last_synced_at = EXCLUDED.last_synced_at
                    """,
                    (
                        as_user_id(user_id),
                        local_date,
                        google_event_id,
                        content_hash,
                        _utcnow(),
                    ),
                )
            ]
        )

    def delete_event_mapping(self, user_id: UUID | str, local_date: date) -> None:
        self._execute(
            [
                (
                    "DELETE FROM google_calendar_events "
                    "WHERE user_id = %s AND local_date = %s",
                    (as_user_id(user_id), local_date),
                )
            ]
        )

    def delete_all_event_mappings(self, user_id: UUID | str) -> None:
        self._execute(
            [
                (
                    "DELETE FROM google_calendar_events WHERE user_id = %s",
                    (as_user_id(user_id),),
                )
            ]
        )

    def delete_user_data(self, user_id: UUID | str) -> None:
        uid = as_user_id(user_id)
        self._execute(
            [
                ("DELETE FROM google_calendar_events WHERE user_id = %s", (uid,)),
                (
                    "DELETE FROM google_calendar_connections WHERE user_id = %s",
                    (uid,),
                ),
            ]
        )
