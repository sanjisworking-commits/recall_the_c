"""Postgres Playground overlay. Isolation is application-level (ENABLE RLS, no policies)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID

from constitution_memorizer.playground.repository import (
    PlaygroundItem,
    PlaygroundProgress,
    PlaygroundSelection,
    PlaygroundSummary,
    PROGRESS_COLUMNS,
    REVISION_MODE_COLUMNS,
    playground_summary_sql,
    summary_from_row,
    _require_learn_mode,
)
from constitution_memorizer.playground.learning.models import (
    MODE_STATUS_COMPLETED,
    ModeProgressRow,
)
from constitution_memorizer.playground.learning.modes import (
    PLAYGROUND_LEARN_MODES,
    TOTAL_PLAYGROUND_MODES,
)
from constitution_memorizer.playground.lifecycle import (
    LIFECYCLE_MASTERED,
    LIFECYCLE_REVIEW,
    REVISION_RUNGS,
    DueRevisionFact,
    RevisionNotDueError,
    ScheduledRevisionFact,
    StaleRevisionError,
    require_revision_rung,
)
from constitution_memorizer.playground.revision import advance_interval, next_revision_date
from constitution_memorizer.playground.roster.period import playground_today
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

    def list_playground_summaries(
        self,
        user_id: UUID | str,
        *,
        as_of: date,
        law_ids: list[str] | tuple[str, ...] | None = None,
    ) -> list[PlaygroundSummary]:
        if law_ids is not None and len(law_ids) == 0:
            return []
        uid = as_user_id(user_id)
        sql = playground_summary_sql("%s", law_ids=law_ids)
        params: tuple = (uid, as_of, uid, uid)
        if law_ids:
            params = params + tuple(law_ids)
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=self._dict_row) as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
        return [
            summary_from_row(
                row,
                added_at=_as_iso(row["added_at"]),
                last_activity_at=_as_iso(row["last_activity_at"]),
            )
            for row in rows
        ]

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
                if rows:
                    cur.executemany(
                        """
                        INSERT INTO user_playground_selection (
                            user_id, law_id, source_locator, selected_at,
                            source_version, source_hash
                        ) VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        [
                            (uid, law_id, loc, now, ver, digest)
                            for loc, ver, digest in rows
                        ],
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
                           source_version, source_hash, learned_at
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
                           source_version, source_hash, learned_at
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
            learned_at=row.learned_at,
        )

    def get_mode_progress(
        self,
        user_id: UUID | str,
        law_id: str,
        source_locator: str,
        mode: str,
    ) -> ModeProgressRow | None:
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=self._dict_row) as cur:
                cur.execute(
                    """
                    SELECT source_locator, mode, status, attempt_count,
                           first_started_at, last_attempt_at, completed_at,
                           source_version, source_hash
                    FROM user_playground_mode_progress
                    WHERE user_id = %s AND law_id = %s AND source_locator = %s AND mode = %s
                    """,
                    (as_user_id(user_id), law_id, source_locator, mode),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return self._mode_from_row(row)

    def list_mode_progress(
        self,
        user_id: UUID | str,
        law_id: str,
        source_locator: str | None = None,
    ) -> list[ModeProgressRow]:
        uid = as_user_id(user_id)
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=self._dict_row) as cur:
                if source_locator:
                    cur.execute(
                        """
                        SELECT source_locator, mode, status, attempt_count,
                               first_started_at, last_attempt_at, completed_at,
                               source_version, source_hash
                        FROM user_playground_mode_progress
                        WHERE user_id = %s AND law_id = %s AND source_locator = %s
                        """,
                        (uid, law_id, source_locator),
                    )
                else:
                    cur.execute(
                        """
                        SELECT source_locator, mode, status, attempt_count,
                               first_started_at, last_attempt_at, completed_at,
                               source_version, source_hash
                        FROM user_playground_mode_progress
                        WHERE user_id = %s AND law_id = %s
                        """,
                        (uid, law_id),
                    )
                rows = cur.fetchall()
        return [self._mode_from_row(row) for row in rows]

    def start_mode(
        self,
        user_id: UUID | str,
        law_id: str,
        source_locator: str,
        mode: str,
        *,
        source_version: str,
        source_hash: str,
    ) -> ModeProgressRow:
        _require_learn_mode(mode)
        uid = as_user_id(user_id)
        now = datetime.now(timezone.utc)
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO user_playground_mode_progress (
                        user_id, law_id, source_locator, mode, status, attempt_count,
                        first_started_at, last_attempt_at, completed_at,
                        source_version, source_hash, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, 'in_progress', 0, %s, %s, NULL, %s, %s, %s, %s)
                    ON CONFLICT (user_id, law_id, source_locator, mode) DO UPDATE SET
                        status = CASE
                            WHEN user_playground_mode_progress.status = 'completed'
                            THEN 'completed'
                            ELSE 'in_progress'
                        END,
                        first_started_at = COALESCE(
                            user_playground_mode_progress.first_started_at,
                            EXCLUDED.first_started_at
                        ),
                        last_attempt_at = EXCLUDED.last_attempt_at,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (
                        uid,
                        law_id,
                        source_locator,
                        mode,
                        now,
                        now,
                        source_version,
                        source_hash,
                        now,
                        now,
                    ),
                )
                cur.execute(
                    """
                    UPDATE user_playground_item
                    SET last_activity_at = %s,
                        status = CASE
                            WHEN status IN ('revising', 'mastered') THEN status
                            ELSE 'learning'
                        END
                    WHERE user_id = %s AND law_id = %s
                    """,
                    (now, uid, law_id),
                )
                conn.commit()
        row = self.get_mode_progress(user_id, law_id, source_locator, mode)
        assert row is not None
        return row

    def complete_mode(
        self,
        user_id: UUID | str,
        law_id: str,
        source_locator: str,
        mode: str,
        *,
        source_version: str,
        source_hash: str,
        as_of: date | None = None,
    ) -> ModeProgressRow:
        """Complete one initial-learning mode.

        Persistence uses
        ON CONFLICT (user_id, law_id, source_locator, mode)
        then counts six modes and may write Learned once.
        """
        return self.complete_learning_mode_and_transition_if_ready(
            user_id,
            law_id,
            source_locator,
            mode,
            source_version=source_version,
            source_hash=source_hash,
            as_of=as_of,
        )

    def complete_learning_mode_and_transition_if_ready(
        self,
        user_id: UUID | str,
        law_id: str,
        source_locator: str,
        mode: str,
        *,
        source_version: str,
        source_hash: str,
        as_of: date | None = None,
    ) -> ModeProgressRow:
        _require_learn_mode(mode)
        uid = as_user_id(user_id)
        now = datetime.now(timezone.utc)
        today = as_of or playground_today()
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=self._dict_row) as cur:
                self._upsert_mode_completed(
                    cur,
                    uid,
                    law_id,
                    source_locator,
                    mode,
                    now=now,
                    source_version=source_version,
                    source_hash=source_hash,
                )
                self._mark_learned_if_ready(
                    cur,
                    uid,
                    law_id,
                    source_locator,
                    as_of=today,
                    now=now,
                    source_version=source_version,
                    source_hash=source_hash,
                )
                self._touch_item_learning(cur, uid, law_id, now)
            conn.commit()
        row = self.get_mode_progress(user_id, law_id, source_locator, mode)
        assert row is not None
        return row

    def mark_learned_if_ready(
        self,
        user_id: UUID | str,
        law_id: str,
        source_locator: str,
        *,
        as_of: date | None = None,
        source_version: str,
        source_hash: str,
    ) -> PlaygroundProgress | None:
        uid = as_user_id(user_id)
        now = datetime.now(timezone.utc)
        today = as_of or playground_today()
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=self._dict_row) as cur:
                self._mark_learned_if_ready(
                    cur,
                    uid,
                    law_id,
                    source_locator,
                    as_of=today,
                    now=now,
                    source_version=source_version,
                    source_hash=source_hash,
                )
            conn.commit()
        return self.get_progress(user_id, law_id, source_locator)

    def get_revision_progress(
        self, user_id: UUID | str, law_id: str, source_locator: str
    ) -> PlaygroundProgress | None:
        return self.get_progress(user_id, law_id, source_locator)

    def list_revision_progress(
        self, user_id: UUID | str, law_id: str
    ) -> list[PlaygroundProgress]:
        return self.list_progress(user_id, law_id)

    def get_revision_mode_progress(
        self,
        user_id: UUID | str,
        law_id: str,
        source_locator: str,
        rung_days: int,
        mode: str,
    ) -> ModeProgressRow | None:
        require_revision_rung(rung_days)
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=self._dict_row) as cur:
                cur.execute(
                    f"""
                    SELECT {REVISION_MODE_COLUMNS}
                    FROM user_playground_revision_mode_progress
                    WHERE user_id = %s AND law_id = %s AND source_locator = %s
                      AND rung_days = %s AND mode = %s
                    """,
                    (as_user_id(user_id), law_id, source_locator, rung_days, mode),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return self._mode_from_row(row)

    def list_revision_mode_progress(
        self,
        user_id: UUID | str,
        law_id: str,
        source_locator: str | None = None,
        rung_days: int | None = None,
    ) -> list[ModeProgressRow]:
        uid = as_user_id(user_id)
        sql = f"""
            SELECT {REVISION_MODE_COLUMNS}
            FROM user_playground_revision_mode_progress
            WHERE user_id = %s AND law_id = %s
            """
        params: list[Any] = [uid, law_id]
        if source_locator:
            sql += " AND source_locator = %s"
            params.append(source_locator)
        if rung_days is not None:
            require_revision_rung(rung_days)
            sql += " AND rung_days = %s"
            params.append(rung_days)
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=self._dict_row) as cur:
                cur.execute(sql, tuple(params))
                rows = cur.fetchall()
        return [self._mode_from_row(row) for row in rows]

    def start_revision_mode(
        self,
        user_id: UUID | str,
        law_id: str,
        source_locator: str,
        mode: str,
        *,
        source_version: str,
        source_hash: str,
        as_of: date | None = None,
        claimed_rung: int | None = None,
    ) -> ModeProgressRow:
        _require_learn_mode(mode)
        uid = as_user_id(user_id)
        now = datetime.now(timezone.utc)
        today = as_of or playground_today()
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=self._dict_row) as cur:
                lifecycle = self._lock_progress(cur, uid, law_id, source_locator)
                rung = self._assert_revision_writable(lifecycle, today, claimed_rung)
                cur.execute(
                    """
                    INSERT INTO user_playground_revision_mode_progress (
                        user_id, law_id, source_locator, rung_days, mode, status,
                        attempt_count, first_started_at, last_attempt_at, completed_at,
                        source_version, source_hash, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, 'in_progress', 0, %s, %s, NULL, %s, %s, %s, %s)
                    ON CONFLICT (user_id, law_id, source_locator, rung_days, mode) DO UPDATE SET
                        status = CASE
                            WHEN user_playground_revision_mode_progress.status = 'completed'
                            THEN 'completed'
                            ELSE 'in_progress'
                        END,
                        first_started_at = COALESCE(
                            user_playground_revision_mode_progress.first_started_at,
                            EXCLUDED.first_started_at
                        ),
                        last_attempt_at = EXCLUDED.last_attempt_at,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (
                        uid,
                        law_id,
                        source_locator,
                        rung,
                        mode,
                        now,
                        now,
                        source_version,
                        source_hash,
                        now,
                        now,
                    ),
                )
                self._touch_item_learning(cur, uid, law_id, now)
            conn.commit()
        row = self.get_revision_mode_progress(
            user_id, law_id, source_locator, rung, mode
        )
        assert row is not None
        return row

    def complete_revision_mode(
        self,
        user_id: UUID | str,
        law_id: str,
        source_locator: str,
        mode: str,
        *,
        source_version: str,
        source_hash: str,
        as_of: date | None = None,
        claimed_rung: int | None = None,
    ) -> ModeProgressRow:
        return self.complete_revision_mode_and_advance_if_ready(
            user_id,
            law_id,
            source_locator,
            mode,
            source_version=source_version,
            source_hash=source_hash,
            as_of=as_of,
            claimed_rung=claimed_rung,
        )

    def complete_revision_mode_and_advance_if_ready(
        self,
        user_id: UUID | str,
        law_id: str,
        source_locator: str,
        mode: str,
        *,
        source_version: str,
        source_hash: str,
        as_of: date | None = None,
        claimed_rung: int | None = None,
    ) -> ModeProgressRow:
        _require_learn_mode(mode)
        uid = as_user_id(user_id)
        now = datetime.now(timezone.utc)
        today = as_of or playground_today()
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=self._dict_row) as cur:
                lifecycle = self._lock_progress(cur, uid, law_id, source_locator)
                rung, may_advance = self._revision_write_plan(
                    cur, uid, law_id, source_locator, mode, lifecycle, today, claimed_rung
                )
                self._upsert_revision_mode_completed(
                    cur,
                    uid,
                    law_id,
                    source_locator,
                    rung,
                    mode,
                    now=now,
                    source_version=source_version,
                    source_hash=source_hash,
                )
                if may_advance:
                    completed = self._count_revision_modes(
                        cur, uid, law_id, source_locator, rung
                    )
                    if completed >= TOTAL_PLAYGROUND_MODES:
                        self._advance_rung_once(
                            cur,
                            uid,
                            law_id,
                            source_locator,
                            current_rung=rung,
                            as_of=today,
                            now=now,
                            source_version=source_version,
                            source_hash=source_hash,
                        )
                    self._touch_item_after_revision(cur, uid, law_id, now)
            conn.commit()
        row = self.get_revision_mode_progress(
            user_id, law_id, source_locator, rung, mode
        )
        assert row is not None
        return row

    def list_due_revisions(
        self,
        user_id: UUID | str,
        as_of: date,
        active_law_ids: list[str] | tuple[str, ...] | None,
    ) -> list[DueRevisionFact]:
        if active_law_ids is not None and len(active_law_ids) == 0:
            return []
        uid = as_user_id(user_id)
        sql = """
            SELECT law_id, source_locator, status, interval_days,
                   next_revision, times_completed, learned_at
            FROM user_playground_progress
            WHERE user_id = %s
              AND status != 'mastered'
              AND next_revision IS NOT NULL
              AND next_revision <= %s
            """
        params: list[Any] = [uid, as_of]
        if active_law_ids is not None:
            sql += " AND law_id IN (" + ", ".join("%s" for _ in active_law_ids) + ")"
            params.extend(active_law_ids)
        sql += " ORDER BY next_revision ASC, law_id ASC, source_locator ASC"
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=self._dict_row) as cur:
                cur.execute(sql, tuple(params))
                rows = cur.fetchall()
        return [
            DueRevisionFact(
                law_id=row["law_id"],
                source_locator=row["source_locator"],
                status=row["status"],
                interval_days=int(row["interval_days"] or 0),
                next_revision=_as_iso(row["next_revision"])[:10],
                times_completed=int(row["times_completed"] or 0),
                learned_at=_as_iso_opt(row["learned_at"]),
            )
            for row in rows
        ]

    def list_revision_schedule(
        self,
        user_id: UUID | str,
        start_date: date,
        end_date: date,
        active_law_ids: list[str] | tuple[str, ...] | None,
    ) -> list[ScheduledRevisionFact]:
        if active_law_ids is not None and len(active_law_ids) == 0:
            return []
        uid = as_user_id(user_id)
        sql = """
            SELECT law_id, source_locator, status, interval_days, next_revision
            FROM user_playground_progress
            WHERE user_id = %s
              AND next_revision IS NOT NULL
              AND next_revision >= %s
              AND next_revision <= %s
            """
        params: list[Any] = [uid, start_date, end_date]
        if active_law_ids is not None:
            sql += " AND law_id IN (" + ", ".join("%s" for _ in active_law_ids) + ")"
            params.extend(active_law_ids)
        sql += " ORDER BY next_revision ASC, law_id ASC, source_locator ASC"
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=self._dict_row) as cur:
                cur.execute(sql, tuple(params))
                rows = cur.fetchall()
        return [
            ScheduledRevisionFact(
                law_id=row["law_id"],
                source_locator=row["source_locator"],
                status=row["status"],
                interval_days=int(row["interval_days"] or 0),
                next_revision=_as_iso(row["next_revision"])[:10],
            )
            for row in rows
        ]

    def _upsert_mode_completed(
        self,
        cur,
        uid: str,
        law_id: str,
        source_locator: str,
        mode: str,
        *,
        now: datetime,
        source_version: str,
        source_hash: str,
    ) -> None:
        cur.execute(
            """
            INSERT INTO user_playground_mode_progress (
                user_id, law_id, source_locator, mode, status, attempt_count,
                first_started_at, last_attempt_at, completed_at,
                source_version, source_hash, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, 'completed', 1, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id, law_id, source_locator, mode) DO UPDATE SET
                status = 'completed',
                attempt_count = user_playground_mode_progress.attempt_count + 1,
                first_started_at = COALESCE(
                    user_playground_mode_progress.first_started_at,
                    EXCLUDED.first_started_at
                ),
                last_attempt_at = EXCLUDED.last_attempt_at,
                completed_at = COALESCE(
                    user_playground_mode_progress.completed_at,
                    EXCLUDED.completed_at
                ),
                updated_at = EXCLUDED.updated_at
            """,
            (
                uid,
                law_id,
                source_locator,
                mode,
                now,
                now,
                now,
                source_version,
                source_hash,
                now,
                now,
            ),
        )

    def _mark_learned_if_ready(
        self,
        cur,
        uid: str,
        law_id: str,
        source_locator: str,
        *,
        as_of: date,
        now: datetime,
        source_version: str,
        source_hash: str,
    ) -> None:
        modes = tuple(PLAYGROUND_LEARN_MODES)
        placeholders = ", ".join("%s" for _ in modes)
        cur.execute(
            f"""
            SELECT COUNT(*) AS n
            FROM user_playground_mode_progress
            WHERE user_id = %s AND law_id = %s AND source_locator = %s
              AND status = 'completed' AND mode IN ({placeholders})
            """,
            (uid, law_id, source_locator) + modes,
        )
        count_row = cur.fetchone()
        n = int(count_row["n"] if count_row["n"] is not None else 0)
        if n < TOTAL_PLAYGROUND_MODES:
            return
        nxt = next_revision_date(as_of, REVISION_RUNGS[0])
        cur.execute(
            """
            INSERT INTO user_playground_progress (
                user_id, law_id, source_locator, status, cloze_done,
                times_completed, last_completed, next_revision, interval_days,
                source_version, source_hash, updated_at, learned_at
            ) VALUES (%s, %s, %s, 'learned', 1, 0, NULL, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id, law_id, source_locator) DO NOTHING
            """,
            (
                uid,
                law_id,
                source_locator,
                nxt,
                REVISION_RUNGS[0],
                source_version,
                source_hash,
                now,
                as_of,
            ),
        )

    def _lock_progress(
        self, cur, uid: str, law_id: str, source_locator: str
    ) -> PlaygroundProgress | None:
        cur.execute(
            f"""
            SELECT {PROGRESS_COLUMNS}
            FROM user_playground_progress
            WHERE user_id = %s AND law_id = %s AND source_locator = %s
            FOR UPDATE
            """,
            (uid, law_id, source_locator),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return self._progress_from_row(row)

    def _assert_revision_writable(
        self,
        lifecycle: PlaygroundProgress | None,
        today: date,
        claimed_rung: int | None,
    ) -> int:
        if lifecycle is None or lifecycle.status == LIFECYCLE_MASTERED:
            raise StaleRevisionError("stale_revision")
        if not lifecycle.next_revision:
            raise StaleRevisionError("stale_revision")
        current = int(lifecycle.interval_days or 0)
        if current not in REVISION_RUNGS:
            raise StaleRevisionError("stale_revision")
        if claimed_rung is not None and int(claimed_rung) != current:
            raise StaleRevisionError("stale_revision")
        if today.isoformat() < str(lifecycle.next_revision)[:10]:
            raise RevisionNotDueError("not_due")
        return current

    def _revision_mode_completed_on_rung(
        self,
        cur,
        uid: str,
        law_id: str,
        source_locator: str,
        rung_days: int,
        mode: str,
    ) -> bool:
        cur.execute(
            """
            SELECT status
            FROM user_playground_revision_mode_progress
            WHERE user_id = %s AND law_id = %s AND source_locator = %s
              AND rung_days = %s AND mode = %s
            """,
            (uid, law_id, source_locator, rung_days, mode),
        )
        row = cur.fetchone()
        return row is not None and str(row["status"]) == MODE_STATUS_COMPLETED

    def _revision_write_plan(
        self,
        cur,
        uid: str,
        law_id: str,
        source_locator: str,
        mode: str,
        lifecycle: PlaygroundProgress | None,
        today: date,
        claimed_rung: int | None,
    ) -> tuple[int, bool]:
        if (
            claimed_rung is not None
            and lifecycle is not None
            and int(claimed_rung) != int(lifecycle.interval_days or 0)
            and self._revision_mode_completed_on_rung(
                cur, uid, law_id, source_locator, int(claimed_rung), mode
            )
        ):
            return int(claimed_rung), False
        return self._assert_revision_writable(lifecycle, today, claimed_rung), True

    def _upsert_revision_mode_completed(
        self,
        cur,
        uid: str,
        law_id: str,
        source_locator: str,
        rung_days: int,
        mode: str,
        *,
        now: datetime,
        source_version: str,
        source_hash: str,
    ) -> None:
        cur.execute(
            """
            INSERT INTO user_playground_revision_mode_progress (
                user_id, law_id, source_locator, rung_days, mode, status, attempt_count,
                first_started_at, last_attempt_at, completed_at,
                source_version, source_hash, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, 'completed', 1, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id, law_id, source_locator, rung_days, mode) DO UPDATE SET
                status = 'completed',
                attempt_count = user_playground_revision_mode_progress.attempt_count + 1,
                first_started_at = COALESCE(
                    user_playground_revision_mode_progress.first_started_at,
                    EXCLUDED.first_started_at
                ),
                last_attempt_at = EXCLUDED.last_attempt_at,
                completed_at = COALESCE(
                    user_playground_revision_mode_progress.completed_at,
                    EXCLUDED.completed_at
                ),
                updated_at = EXCLUDED.updated_at
            """,
            (
                uid,
                law_id,
                source_locator,
                rung_days,
                mode,
                now,
                now,
                now,
                source_version,
                source_hash,
                now,
                now,
            ),
        )

    def _count_revision_modes(
        self, cur, uid: str, law_id: str, source_locator: str, rung_days: int
    ) -> int:
        modes = tuple(PLAYGROUND_LEARN_MODES)
        placeholders = ", ".join("%s" for _ in modes)
        cur.execute(
            f"""
            SELECT COUNT(*) AS n
            FROM user_playground_revision_mode_progress
            WHERE user_id = %s AND law_id = %s AND source_locator = %s
              AND rung_days = %s AND status = 'completed' AND mode IN ({placeholders})
            """,
            (uid, law_id, source_locator, rung_days) + modes,
        )
        row = cur.fetchone()
        return int(row["n"] if row["n"] is not None else 0)

    def _advance_rung_once(
        self,
        cur,
        uid: str,
        law_id: str,
        source_locator: str,
        *,
        current_rung: int,
        as_of: date,
        now: datetime,
        source_version: str,
        source_hash: str,
    ) -> None:
        nxt_interval = advance_interval(current_rung)
        if nxt_interval is None:
            status = LIFECYCLE_MASTERED
            interval = current_rung
            nxt: date | None = None
            item_status = "mastered"
        else:
            status = LIFECYCLE_REVIEW
            interval = nxt_interval
            nxt = next_revision_date(as_of, interval)
            item_status = "revising"
        cur.execute(
            """
            UPDATE user_playground_progress
            SET times_completed = times_completed + 1,
                last_completed = %s,
                next_revision = %s,
                interval_days = %s,
                status = %s,
                source_version = %s,
                source_hash = %s,
                updated_at = %s
            WHERE user_id = %s AND law_id = %s AND source_locator = %s
              AND interval_days = %s
              AND status != 'mastered'
            """,
            (
                as_of,
                nxt,
                interval,
                status,
                source_version,
                source_hash,
                now,
                uid,
                law_id,
                source_locator,
                current_rung,
            ),
        )
        cur.execute(
            """
            UPDATE user_playground_item
            SET last_activity_at = %s, status = %s
            WHERE user_id = %s AND law_id = %s
            """,
            (now, item_status, uid, law_id),
        )

    def _touch_item_after_revision(self, cur, uid: str, law_id: str, now: datetime) -> None:
        cur.execute(
            """
            UPDATE user_playground_item
            SET last_activity_at = %s,
                status = CASE
                    WHEN status = 'mastered' THEN status
                    ELSE 'revising'
                END
            WHERE user_id = %s AND law_id = %s
            """,
            (now, uid, law_id),
        )

    def _touch_item_learning(self, cur, uid: str, law_id: str, now: datetime) -> None:
        cur.execute(
            """
            UPDATE user_playground_item
            SET last_activity_at = %s,
                status = CASE
                    WHEN status IN ('revising', 'mastered') THEN status
                    ELSE 'learning'
                END
            WHERE user_id = %s AND law_id = %s
            """,
            (now, uid, law_id),
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
        learned = _as_iso_opt(row.get("learned_at"))
        nxt = _as_iso_opt(row["next_revision"])
        last = _as_iso_opt(row["last_completed"])
        return PlaygroundProgress(
            source_locator=row["source_locator"],
            status=row["status"],
            cloze_done=bool(row["cloze_done"]),
            times_completed=int(row["times_completed"]),
            last_completed=None if last is None else last[:10],
            next_revision=None if nxt is None else nxt[:10],
            interval_days=int(row["interval_days"]),
            source_version=row["source_version"],
            source_hash=row["source_hash"],
            learned_at=None if learned is None else learned[:10],
        )

    def _mode_from_row(self, row: dict[str, Any]) -> ModeProgressRow:
        rung = row.get("rung_days")
        return ModeProgressRow(
            source_locator=row["source_locator"],
            mode=row["mode"],
            status=row["status"],
            attempt_count=int(row["attempt_count"] or 0),
            first_started_at=_as_iso_opt(row["first_started_at"]),
            last_attempt_at=_as_iso_opt(row["last_attempt_at"]),
            completed_at=_as_iso_opt(row["completed_at"]),
            source_version=row["source_version"],
            source_hash=row["source_hash"],
            rung_days=None if rung is None else int(rung),
        )
