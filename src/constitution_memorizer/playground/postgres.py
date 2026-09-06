"""Postgres Playground overlay. Isolation is application-level (ENABLE RLS, no policies)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID

from constitution_memorizer.playground.repository import (
    PlaygroundItem,
    PlaygroundProgress,
    PlaygroundSelection,
)
from constitution_memorizer.playground.revision import advance_interval, next_revision_date
from constitution_memorizer.progress.user_ids import as_user_id


def _as_iso(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _as_iso_opt(value: Any) -> str | None:
    if value is None:
        return None
    return _as_iso(value)


class PostgresPlaygroundRepository:
    def __init__(self, pool: Any) -> None:
        from psycopg.rows import dict_row

        self._pool = pool
        self._dict_row = dict_row

    def get_item(self, user_id: UUID | str, law_id: str) -> PlaygroundItem | None:
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=self._dict_row) as cur:
                cur.execute(
                    """
                    SELECT law_id, status, added_at, last_activity_at,
                           source_version, law_source_hash
                    FROM user_playground_item
                    WHERE user_id = %s AND law_id = %s
                    """,
                    (as_user_id(user_id), law_id),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return self._item_from_row(row)

    def list_items(self, user_id: UUID | str) -> list[PlaygroundItem]:
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=self._dict_row) as cur:
                cur.execute(
                    """
                    SELECT law_id, status, added_at, last_activity_at,
                           source_version, law_source_hash
                    FROM user_playground_item
                    WHERE user_id = %s
                    ORDER BY added_at ASC
                    """,
                    (as_user_id(user_id),),
                )
                rows = cur.fetchall()
        return [self._item_from_row(row) for row in rows]

    def add_item(
        self,
        user_id: UUID | str,
        law_id: str,
        *,
        source_version: str,
        law_source_hash: str,
    ) -> PlaygroundItem:
        existing = self.get_item(user_id, law_id)
        now = datetime.now(timezone.utc)
        if existing is not None:
            with self._pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE user_playground_item
                        SET last_activity_at = %s
                        WHERE user_id = %s AND law_id = %s
                        """,
                        (now, as_user_id(user_id), law_id),
                    )
                    conn.commit()
            return self.get_item(user_id, law_id)  # type: ignore[return-value]
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO user_playground_item (
                        user_id, law_id, status, added_at, last_activity_at,
                        source_version, law_source_hash
                    ) VALUES (%s, %s, 'in_playground', %s, %s, %s, %s)
                    """,
                    (
                        as_user_id(user_id),
                        law_id,
                        now,
                        now,
                        source_version,
                        law_source_hash,
                    ),
                )
                conn.commit()
        return self.get_item(user_id, law_id)  # type: ignore[return-value]

    def list_selection(self, user_id: UUID | str, law_id: str) -> list[PlaygroundSelection]:
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=self._dict_row) as cur:
                cur.execute(
                    """
                    SELECT source_locator, selected_at, source_version, source_hash
                    FROM user_playground_selection
                    WHERE user_id = %s AND law_id = %s
                    ORDER BY source_locator
                    """,
                    (as_user_id(user_id), law_id),
                )
                rows = cur.fetchall()
        return [
            PlaygroundSelection(
                source_locator=row["source_locator"],
                selected_at=_as_iso(row["selected_at"]),
                source_version=row["source_version"],
                source_hash=row["source_hash"],
            )
            for row in rows
        ]

    def replace_selection(
        self,
        user_id: UUID | str,
        law_id: str,
        rows: list[tuple[str, str, str]],
    ) -> None:
        uid = as_user_id(user_id)
        now = datetime.now(timezone.utc)
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM user_playground_selection WHERE user_id = %s AND law_id = %s",
                    (uid, law_id),
                )
                for loc, ver, digest in rows:
                    cur.execute(
                        """
                        INSERT INTO user_playground_selection (
                            user_id, law_id, source_locator, selected_at,
                            source_version, source_hash
                        ) VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (uid, law_id, loc, now, ver, digest),
                    )
                cur.execute(
                    """
                    UPDATE user_playground_item
                    SET last_activity_at = %s, status = CASE
                        WHEN %s > 0 THEN 'learning'
                        ELSE 'in_playground'
                    END
                    WHERE user_id = %s AND law_id = %s
                    """,
                    (now, len(rows), uid, law_id),
                )
                conn.commit()

    def get_progress(
        self, user_id: UUID | str, law_id: str, source_locator: str
    ) -> PlaygroundProgress | None:
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=self._dict_row) as cur:
                cur.execute(
                    """
                    SELECT source_locator, status, cloze_done, times_completed,
                           last_completed, next_revision, interval_days,
                           source_version, source_hash
                    FROM user_playground_progress
                    WHERE user_id = %s AND law_id = %s AND source_locator = %s
                    """,
                    (as_user_id(user_id), law_id, source_locator),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return self._progress_from_row(row)

    def list_progress(self, user_id: UUID | str, law_id: str) -> list[PlaygroundProgress]:
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=self._dict_row) as cur:
                cur.execute(
                    """
                    SELECT source_locator, status, cloze_done, times_completed,
                           last_completed, next_revision, interval_days,
                           source_version, source_hash
                    FROM user_playground_progress
                    WHERE user_id = %s AND law_id = %s
                    """,
                    (as_user_id(user_id), law_id),
                )
                rows = cur.fetchall()
        return [self._progress_from_row(row) for row in rows]

    def complete_cloze(
        self,
        user_id: UUID | str,
        law_id: str,
        source_locator: str,
        *,
        source_version: str,
        source_hash: str,
        as_of: date,
        live_hash: str,
    ) -> PlaygroundProgress:
        uid = as_user_id(user_id)
        now = datetime.now(timezone.utc)
        existing = self.get_progress(user_id, law_id, source_locator)
        outdated = (
            live_hash != source_hash if existing is None else live_hash != existing.source_hash
        )
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                if existing is None:
                    interval = 1
                    nxt = next_revision_date(as_of, interval)
                    cur.execute(
                        """
                        INSERT INTO user_playground_progress (
                            user_id, law_id, source_locator, status, cloze_done,
                            times_completed, last_completed, next_revision, interval_days,
                            source_version, source_hash, updated_at
                        ) VALUES (%s, %s, %s, 'review', 1, 1, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            uid,
                            law_id,
                            source_locator,
                            as_of,
                            nxt,
                            interval,
                            source_version,
                            live_hash,
                            now,
                        ),
                    )
                elif (
                    existing.cloze_done
                    and existing.next_revision
                    and as_of.isoformat() < existing.next_revision
                ):
                    cur.execute(
                        """
                        UPDATE user_playground_progress
                        SET cloze_done = 1, updated_at = %s
                        WHERE user_id = %s AND law_id = %s AND source_locator = %s
                        """,
                        (now, uid, law_id, source_locator),
                    )
                else:
                    nxt_interval = advance_interval(existing.interval_days)
                    if nxt_interval is None:
                        status = "mastered"
                        interval = existing.interval_days
                        nxt: date | None = None
                    else:
                        status = "review"
                        interval = nxt_interval
                        nxt = next_revision_date(as_of, interval)
                    cur.execute(
                        """
                        UPDATE user_playground_progress
                        SET cloze_done = 1,
                            times_completed = times_completed + 1,
                            last_completed = %s,
                            next_revision = %s,
                            interval_days = %s,
                            status = %s,
                            source_version = %s,
                            source_hash = %s,
                            updated_at = %s
                        WHERE user_id = %s AND law_id = %s AND source_locator = %s
                        """,
                        (
                            as_of,
                            nxt,
                            interval,
                            status,
                            source_version,
                            live_hash,
                            now,
                            uid,
                            law_id,
                            source_locator,
                        ),
                    )
                cur.execute(
                    """
                    UPDATE user_playground_item
                    SET last_activity_at = %s, status = 'revising'
                    WHERE user_id = %s AND law_id = %s
                    """,
                    (now, uid, law_id),
                )
                conn.commit()
        row = self.get_progress(user_id, law_id, source_locator)
        assert row is not None
        return PlaygroundProgress(
            source_locator=row.source_locator,
            status=row.status,
            cloze_done=row.cloze_done,
            times_completed=row.times_completed,
            last_completed=row.last_completed,
            next_revision=row.next_revision,
            interval_days=row.interval_days,
            source_version=row.source_version,
            source_hash=row.source_hash,
            source_outdated=outdated or live_hash != row.source_hash,
        )

    def _item_from_row(self, row: dict[str, Any]) -> PlaygroundItem:
        return PlaygroundItem(
            law_id=row["law_id"],
            status=row["status"],
            added_at=_as_iso(row["added_at"]),
            last_activity_at=_as_iso(row["last_activity_at"]),
            source_version=row["source_version"],
            law_source_hash=row["law_source_hash"],
        )

    def _progress_from_row(self, row: dict[str, Any]) -> PlaygroundProgress:
        return PlaygroundProgress(
            source_locator=row["source_locator"],
            status=row["status"],
            cloze_done=bool(row["cloze_done"]),
            times_completed=int(row["times_completed"]),
            last_completed=_as_iso_opt(row["last_completed"]),
            next_revision=_as_iso_opt(row["next_revision"]),
            interval_days=int(row["interval_days"]),
            source_version=row["source_version"],
            source_hash=row["source_hash"],
        )
