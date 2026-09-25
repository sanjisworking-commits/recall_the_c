"""User-owned Playground state. Isolation is application-level (user_id)."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timezone
from uuid import UUID

from constitution_memorizer.progress.user_ids import as_user_id
from constitution_memorizer.playground.learning.models import (
    MODE_STATUS_COMPLETED,
    ModeProgressRow,
)
from constitution_memorizer.playground.learning.modes import (
    PLAYGROUND_LEARN_MODES,
    PLAYGROUND_LEARN_MODES_SET,
    TOTAL_PLAYGROUND_MODES,
)
from constitution_memorizer.playground.lifecycle import (
    LIFECYCLE_LEARNED,
    LIFECYCLE_MASTERED,
    LIFECYCLE_REVIEW,
    REVISION_RUNGS,
    DueRevisionFact,
    RevisionNotDueError,
    ScheduledRevisionFact,
    StaleRevisionError,
    require_revision_rung,
)
from constitution_memorizer.playground.revision import (
    advance_interval,
    next_revision_date,
)
from constitution_memorizer.playground.roster.period import playground_today


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _date_iso(value: date | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _require_learn_mode(mode: str) -> str:
    if mode not in PLAYGROUND_LEARN_MODES_SET:
        raise ValueError(f"unknown playground mode: {mode}")
    return mode


def _mode_from_row(row) -> ModeProgressRow:
    rung = None
    keys = row.keys()
    if "rung_days" in keys and row["rung_days"] is not None:
        rung = int(row["rung_days"])
    return ModeProgressRow(
        source_locator=row["source_locator"],
        mode=row["mode"],
        status=row["status"],
        attempt_count=int(row["attempt_count"] or 0),
        first_started_at=row["first_started_at"],
        last_attempt_at=row["last_attempt_at"],
        completed_at=row["completed_at"],
        source_version=row["source_version"],
        source_hash=row["source_hash"],
        rung_days=rung,
    )


@dataclass(frozen=True)
class PlaygroundItem:
    """Activation row. ``law_source_hash`` is a historical column name.

    It stores the registry runtime identity token
    (``BareActSpec.source_hash`` or, when that is absent, ``filename``).
    A filename fallback is not a cryptographic hash and is never obtained
    by reading the runtime JSON file.
    """

    law_id: str
    status: str
    added_at: str
    last_activity_at: str
    source_version: str
    law_source_hash: str


@dataclass(frozen=True)
class PlaygroundSelection:
    source_locator: str
    selected_at: str
    source_version: str
    source_hash: str


@dataclass(frozen=True)
class PlaygroundProgress:
    source_locator: str
    status: str
    cloze_done: bool
    times_completed: int
    last_completed: str | None
    next_revision: str | None
    interval_days: int
    source_version: str
    source_hash: str
    source_outdated: bool = False
    learned_at: str | None = None


@dataclass(frozen=True)
class PlaygroundSummary:
    """Dashboard/roster-summary row. No statutory text. No Act hydration."""

    law_id: str
    status: str
    added_at: str
    last_activity_at: str
    source_version: str
    law_source_hash: str
    selected_count: int
    learning_count: int
    learned_count: int
    to_learn_count: int
    due_count: int
    mastered_count: int


def playground_summary_sql(
    placeholder: str, *, law_ids: list[str] | tuple[str, ...] | None = None
) -> str:
    """One aggregate query: items + selection counts + selected-progress counts.

    Placeholders, in order: user_id, as_of, user_id, user_id[, law_id...].
    Subqueries are grouped by law_id so joins cannot cartesian-inflate counts.
    When ``law_ids`` is set, the outer query is restricted to those laws so
    cost scales with current-roster size rather than lifetime overlay history.
    """
    ph = placeholder
    extra = ""
    if law_ids:
        extra = " AND i.law_id IN (" + ", ".join(ph for _ in law_ids) + ")"
    return f"""
            SELECT
                i.law_id, i.status, i.added_at, i.last_activity_at,
                i.source_version, i.law_source_hash,
                COALESCE(sel.selected_count, 0) AS selected_count,
                COALESCE(prog.learning_count, 0) AS learning_count,
                COALESCE(prog.learned_count, 0) AS learned_count,
                COALESCE(prog.due_count, 0) AS due_count,
                COALESCE(prog.mastered_count, 0) AS mastered_count
            FROM user_playground_item AS i
            LEFT JOIN (
                SELECT law_id, COUNT(*) AS selected_count
                FROM user_playground_selection
                WHERE user_id = {ph}
                GROUP BY law_id
            ) AS sel ON sel.law_id = i.law_id
            LEFT JOIN (
                SELECT s.law_id,
                    COUNT(DISTINCT CASE
                        WHEN m.status = 'completed'
                         AND (p.status IS NULL
                              OR p.status NOT IN ('learned', 'review', 'mastered'))
                        THEN s.source_locator
                    END) AS learning_count,
                    COUNT(DISTINCT CASE
                        WHEN p.status IN ('learned', 'review')
                        THEN s.source_locator
                    END) AS learned_count,
                    COUNT(DISTINCT CASE
                        WHEN p.status != 'mastered'
                         AND p.next_revision IS NOT NULL
                         AND p.next_revision <= {ph}
                        THEN s.source_locator
                    END) AS due_count,
                    COUNT(DISTINCT CASE
                        WHEN p.status = 'mastered'
                        THEN s.source_locator
                    END) AS mastered_count
                FROM user_playground_selection AS s
                LEFT JOIN user_playground_progress AS p
                  ON p.user_id = s.user_id
                 AND p.law_id = s.law_id
                 AND p.source_locator = s.source_locator
                LEFT JOIN user_playground_mode_progress AS m
                  ON m.user_id = s.user_id
                 AND m.law_id = s.law_id
                 AND m.source_locator = s.source_locator
                 AND m.status = 'completed'
                WHERE s.user_id = {ph}
                GROUP BY s.law_id
            ) AS prog ON prog.law_id = i.law_id
            WHERE i.user_id = {ph}{extra}
            ORDER BY i.added_at ASC
            """


def summary_from_row(row, *, added_at: str, last_activity_at: str) -> PlaygroundSummary:
    selected = int(row["selected_count"] or 0)
    learning = int(row["learning_count"] or 0) if "learning_count" in row.keys() else 0
    learned = int(row["learned_count"] or 0)
    due = int(row["due_count"] or 0)
    mastered = int(row["mastered_count"] or 0) if "mastered_count" in row.keys() else 0
    return PlaygroundSummary(
        law_id=row["law_id"],
        status=row["status"],
        added_at=added_at,
        last_activity_at=last_activity_at,
        source_version=row["source_version"],
        law_source_hash=row["law_source_hash"],
        selected_count=selected,
        learning_count=learning,
        learned_count=learned,
        to_learn_count=max(0, selected - learned - mastered),
        due_count=due,
        mastered_count=mastered,
    )


PROGRESS_COLUMNS = """
            source_locator, status, cloze_done, times_completed,
                   last_completed, next_revision, interval_days,
                   source_version, source_hash, learned_at
"""

REVISION_MODE_COLUMNS = """
            source_locator, mode, status, attempt_count,
                   first_started_at, last_attempt_at, completed_at,
                   source_version, source_hash, rung_days
"""


class SqlitePlaygroundRepository:
    def __init__(self, conn) -> None:
        self.conn = conn

    @contextmanager
    def _immediate(self):
        previous = self.conn.isolation_level
        self.conn.commit()
        self.conn.isolation_level = None
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        finally:
            self.conn.isolation_level = previous

    def get_item(self, user_id: UUID | str, law_id: str) -> PlaygroundItem | None:
        row = self.conn.execute(
            """
            SELECT law_id, status, added_at, last_activity_at,
                   source_version, law_source_hash
            FROM user_playground_item
            WHERE user_id = ? AND law_id = ?
            """,
            (as_user_id(user_id), law_id),
        ).fetchone()
        if row is None:
            return None
        return PlaygroundItem(
            law_id=row["law_id"],
            status=row["status"],
            added_at=row["added_at"],
            last_activity_at=row["last_activity_at"],
            source_version=row["source_version"],
            law_source_hash=row["law_source_hash"],
        )

    def list_items(self, user_id: UUID | str) -> list[PlaygroundItem]:
        rows = self.conn.execute(
            """
            SELECT law_id, status, added_at, last_activity_at,
                   source_version, law_source_hash
            FROM user_playground_item
            WHERE user_id = ?
            ORDER BY added_at ASC
            """,
            (as_user_id(user_id),),
        ).fetchall()
        return [
            PlaygroundItem(
                law_id=row["law_id"],
                status=row["status"],
                added_at=row["added_at"],
                last_activity_at=row["last_activity_at"],
                source_version=row["source_version"],
                law_source_hash=row["law_source_hash"],
            )
            for row in rows
        ]

    def add_item(
        self,
        user_id: UUID | str,
        law_id: str,
        *,
        source_version: str,
        law_source_hash: str,
    ) -> PlaygroundItem:
        existing = self.get_item(user_id, law_id)
        now = _utc_now_iso()
        if existing is not None:
            self.conn.execute(
                """
                UPDATE user_playground_item
                SET last_activity_at = ?
                WHERE user_id = ? AND law_id = ?
                """,
                (now, as_user_id(user_id), law_id),
            )
            self.conn.commit()
            return self.get_item(user_id, law_id)  # type: ignore[return-value]
        self.conn.execute(
            """
            INSERT INTO user_playground_item (
                user_id, law_id, status, added_at, last_activity_at,
                source_version, law_source_hash
            ) VALUES (?, ?, 'in_playground', ?, ?, ?, ?)
            """,
            (as_user_id(user_id), law_id, now, now, source_version, law_source_hash),
        )
        self.conn.commit()
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
        sql = playground_summary_sql("?", law_ids=law_ids)
        params: tuple = (uid, as_of.isoformat(), uid, uid)
        if law_ids:
            params = params + tuple(law_ids)
        rows = self.conn.execute(sql, params).fetchall()
        return [
            summary_from_row(
                row,
                added_at=row["added_at"],
                last_activity_at=row["last_activity_at"],
            )
            for row in rows
        ]

    def list_selection(self, user_id: UUID | str, law_id: str) -> list[PlaygroundSelection]:
        rows = self.conn.execute(
            """
            SELECT source_locator, selected_at, source_version, source_hash
            FROM user_playground_selection
            WHERE user_id = ? AND law_id = ?
            ORDER BY source_locator
            """,
            (as_user_id(user_id), law_id),
        ).fetchall()
        return [
            PlaygroundSelection(
                source_locator=row["source_locator"],
                selected_at=row["selected_at"],
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
        """rows: (locator, source_version, source_hash)."""
        uid = as_user_id(user_id)
        now = _utc_now_iso()
        self.conn.execute(
            "DELETE FROM user_playground_selection WHERE user_id = ? AND law_id = ?",
            (uid, law_id),
        )
        self.conn.executemany(
            """
            INSERT INTO user_playground_selection (
                user_id, law_id, source_locator, selected_at,
                source_version, source_hash
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [(uid, law_id, loc, now, ver, digest) for loc, ver, digest in rows],
        )
        self.conn.execute(
            """
            UPDATE user_playground_item
            SET last_activity_at = ?, status = CASE
                WHEN ? > 0 THEN 'learning'
                ELSE 'in_playground'
            END
            WHERE user_id = ? AND law_id = ?
            """,
            (now, len(rows), uid, law_id),
        )
        self.conn.commit()

    def get_progress(
        self, user_id: UUID | str, law_id: str, source_locator: str
    ) -> PlaygroundProgress | None:
        row = self.conn.execute(
            """
            SELECT source_locator, status, cloze_done, times_completed,
                   last_completed, next_revision, interval_days,
                   source_version, source_hash, learned_at
            FROM user_playground_progress
            WHERE user_id = ? AND law_id = ? AND source_locator = ?
            """,
            (as_user_id(user_id), law_id, source_locator),
        ).fetchone()
        if row is None:
            return None
        return self._progress_from_row(row)

    def list_progress(self, user_id: UUID | str, law_id: str) -> list[PlaygroundProgress]:
        rows = self.conn.execute(
            """
            SELECT source_locator, status, cloze_done, times_completed,
                   last_completed, next_revision, interval_days,
                   source_version, source_hash, learned_at
            FROM user_playground_progress
            WHERE user_id = ? AND law_id = ?
            """,
            (as_user_id(user_id), law_id),
        ).fetchall()
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
        now = _utc_now_iso()
        existing = self.get_progress(user_id, law_id, source_locator)
        outdated = live_hash != source_hash if existing is None else live_hash != existing.source_hash
        if existing is None:
            interval = 1
            nxt = next_revision_date(as_of, interval)
            self.conn.execute(
                """
                INSERT INTO user_playground_progress (
                    user_id, law_id, source_locator, status, cloze_done,
                    times_completed, last_completed, next_revision, interval_days,
                    source_version, source_hash, updated_at
                ) VALUES (?, ?, ?, 'review', 1, 1, ?, ?, ?, ?, ?, ?)
                """,
                (
                    uid,
                    law_id,
                    source_locator,
                    _date_iso(as_of),
                    _date_iso(nxt),
                    interval,
                    source_version,
                    live_hash,
                    now,
                ),
            )
        elif existing.cloze_done and existing.next_revision and as_of.isoformat() < existing.next_revision:
            self.conn.execute(
                """
                UPDATE user_playground_progress
                SET cloze_done = 1, updated_at = ?
                WHERE user_id = ? AND law_id = ? AND source_locator = ?
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
            self.conn.execute(
                """
                UPDATE user_playground_progress
                SET cloze_done = 1,
                    times_completed = times_completed + 1,
                    last_completed = ?,
                    next_revision = ?,
                    interval_days = ?,
                    status = ?,
                    source_version = ?,
                    source_hash = ?,
                    updated_at = ?
                WHERE user_id = ? AND law_id = ? AND source_locator = ?
                """,
                (
                    _date_iso(as_of),
                    _date_iso(nxt),
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
        self.conn.execute(
            """
            UPDATE user_playground_item
            SET last_activity_at = ?, status = 'revising'
            WHERE user_id = ? AND law_id = ?
            """,
            (now, uid, law_id),
        )
        self.conn.commit()
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
        row = self.conn.execute(
            """
            SELECT source_locator, mode, status, attempt_count,
                   first_started_at, last_attempt_at, completed_at,
                   source_version, source_hash
            FROM user_playground_mode_progress
            WHERE user_id = ? AND law_id = ? AND source_locator = ? AND mode = ?
            """,
            (as_user_id(user_id), law_id, source_locator, mode),
        ).fetchone()
        if row is None:
            return None
        return _mode_from_row(row)

    def list_mode_progress(
        self,
        user_id: UUID | str,
        law_id: str,
        source_locator: str | None = None,
    ) -> list[ModeProgressRow]:
        uid = as_user_id(user_id)
        if source_locator:
            rows = self.conn.execute(
                """
                SELECT source_locator, mode, status, attempt_count,
                       first_started_at, last_attempt_at, completed_at,
                       source_version, source_hash
                FROM user_playground_mode_progress
                WHERE user_id = ? AND law_id = ? AND source_locator = ?
                """,
                (uid, law_id, source_locator),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """
                SELECT source_locator, mode, status, attempt_count,
                       first_started_at, last_attempt_at, completed_at,
                       source_version, source_hash
                FROM user_playground_mode_progress
                WHERE user_id = ? AND law_id = ?
                """,
                (uid, law_id),
            ).fetchall()
        return [_mode_from_row(row) for row in rows]

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
        now = _utc_now_iso()
        self.conn.execute(
            """
            INSERT INTO user_playground_mode_progress (
                user_id, law_id, source_locator, mode, status, attempt_count,
                first_started_at, last_attempt_at, completed_at,
                source_version, source_hash, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'in_progress', 0, ?, ?, NULL, ?, ?, ?, ?)
            ON CONFLICT (user_id, law_id, source_locator, mode) DO UPDATE SET
                status = CASE
                    WHEN user_playground_mode_progress.status = 'completed'
                    THEN 'completed'
                    ELSE 'in_progress'
                END,
                first_started_at = COALESCE(
                    user_playground_mode_progress.first_started_at, excluded.first_started_at
                ),
                last_attempt_at = excluded.last_attempt_at,
                updated_at = excluded.updated_at
            """,
            (uid, law_id, source_locator, mode, now, now, source_version, source_hash, now, now),
        )
        self._touch_item_learning(uid, law_id, now)
        self.conn.commit()
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
        now = _utc_now_iso()
        today = as_of or playground_today()
        with self._immediate():
            self._upsert_mode_completed(
                uid,
                law_id,
                source_locator,
                mode,
                now=now,
                source_version=source_version,
                source_hash=source_hash,
            )
            self._mark_learned_if_ready(
                uid,
                law_id,
                source_locator,
                as_of=today,
                now=now,
                source_version=source_version,
                source_hash=source_hash,
            )
            self._touch_item_learning(uid, law_id, now)
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
        now = _utc_now_iso()
        today = as_of or playground_today()
        with self._immediate():
            self._mark_learned_if_ready(
                uid,
                law_id,
                source_locator,
                as_of=today,
                now=now,
                source_version=source_version,
                source_hash=source_hash,
            )
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
        row = self.conn.execute(
            f"""
            SELECT {REVISION_MODE_COLUMNS}
            FROM user_playground_revision_mode_progress
            WHERE user_id = ? AND law_id = ? AND source_locator = ?
              AND rung_days = ? AND mode = ?
            """,
            (as_user_id(user_id), law_id, source_locator, rung_days, mode),
        ).fetchone()
        if row is None:
            return None
        return _mode_from_row(row)

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
            WHERE user_id = ? AND law_id = ?
            """
        params: list = [uid, law_id]
        if source_locator:
            sql += " AND source_locator = ?"
            params.append(source_locator)
        if rung_days is not None:
            require_revision_rung(rung_days)
            sql += " AND rung_days = ?"
            params.append(rung_days)
        rows = self.conn.execute(sql, tuple(params)).fetchall()
        return [_mode_from_row(row) for row in rows]

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
        now = _utc_now_iso()
        today = as_of or playground_today()
        with self._immediate():
            lifecycle = self._lock_progress(uid, law_id, source_locator)
            rung = self._assert_revision_writable(lifecycle, today, claimed_rung)
            self.conn.execute(
                """
                INSERT INTO user_playground_revision_mode_progress (
                    user_id, law_id, source_locator, rung_days, mode, status, attempt_count,
                    first_started_at, last_attempt_at, completed_at,
                    source_version, source_hash, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'in_progress', 0, ?, ?, NULL, ?, ?, ?, ?)
                ON CONFLICT (user_id, law_id, source_locator, rung_days, mode) DO UPDATE SET
                    status = CASE
                        WHEN user_playground_revision_mode_progress.status = 'completed'
                        THEN 'completed'
                        ELSE 'in_progress'
                    END,
                    first_started_at = COALESCE(
                        user_playground_revision_mode_progress.first_started_at,
                        excluded.first_started_at
                    ),
                    last_attempt_at = excluded.last_attempt_at,
                    updated_at = excluded.updated_at
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
            self._touch_item_learning(uid, law_id, now)
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
        now = _utc_now_iso()
        today = as_of or playground_today()
        with self._immediate():
            lifecycle = self._lock_progress(uid, law_id, source_locator)
            rung, may_advance = self._revision_write_plan(
                uid, law_id, source_locator, mode, lifecycle, today, claimed_rung
            )
            self._upsert_revision_mode_completed(
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
                    uid, law_id, source_locator, rung
                )
                if completed >= TOTAL_PLAYGROUND_MODES:
                    self._advance_rung_once(
                        uid,
                        law_id,
                        source_locator,
                        current_rung=rung,
                        as_of=today,
                        now=now,
                        source_version=source_version,
                        source_hash=source_hash,
                    )
                self._touch_item_after_revision(uid, law_id, now)
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
            WHERE user_id = ?
              AND status != 'mastered'
              AND next_revision IS NOT NULL
              AND next_revision <= ?
            """
        params: list = [uid, as_of.isoformat()]
        if active_law_ids is not None:
            sql += " AND law_id IN (" + ", ".join("?" for _ in active_law_ids) + ")"
            params.extend(active_law_ids)
        sql += " ORDER BY next_revision ASC, law_id ASC, source_locator ASC"
        rows = self.conn.execute(sql, tuple(params)).fetchall()
        return [
            DueRevisionFact(
                law_id=row["law_id"],
                source_locator=row["source_locator"],
                status=row["status"],
                interval_days=int(row["interval_days"] or 0),
                next_revision=str(row["next_revision"])[:10],
                times_completed=int(row["times_completed"] or 0),
                learned_at=None if row["learned_at"] is None else str(row["learned_at"])[:10],
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
            WHERE user_id = ?
              AND next_revision IS NOT NULL
              AND next_revision >= ?
              AND next_revision <= ?
            """
        params: list = [uid, start_date.isoformat(), end_date.isoformat()]
        if active_law_ids is not None:
            sql += " AND law_id IN (" + ", ".join("?" for _ in active_law_ids) + ")"
            params.extend(active_law_ids)
        sql += " ORDER BY next_revision ASC, law_id ASC, source_locator ASC"
        rows = self.conn.execute(sql, tuple(params)).fetchall()
        return [
            ScheduledRevisionFact(
                law_id=row["law_id"],
                source_locator=row["source_locator"],
                status=row["status"],
                interval_days=int(row["interval_days"] or 0),
                next_revision=str(row["next_revision"])[:10],
            )
            for row in rows
        ]

    def _upsert_mode_completed(
        self,
        uid: str,
        law_id: str,
        source_locator: str,
        mode: str,
        *,
        now: str,
        source_version: str,
        source_hash: str,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO user_playground_mode_progress (
                user_id, law_id, source_locator, mode, status, attempt_count,
                first_started_at, last_attempt_at, completed_at,
                source_version, source_hash, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'completed', 1, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (user_id, law_id, source_locator, mode) DO UPDATE SET
                status = 'completed',
                attempt_count = user_playground_mode_progress.attempt_count + 1,
                first_started_at = COALESCE(
                    user_playground_mode_progress.first_started_at, excluded.first_started_at
                ),
                last_attempt_at = excluded.last_attempt_at,
                completed_at = COALESCE(
                    user_playground_mode_progress.completed_at, excluded.completed_at
                ),
                updated_at = excluded.updated_at
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
        uid: str,
        law_id: str,
        source_locator: str,
        *,
        as_of: date,
        now: str,
        source_version: str,
        source_hash: str,
    ) -> None:
        modes = tuple(PLAYGROUND_LEARN_MODES)
        placeholders = ", ".join("?" for _ in modes)
        count_row = self.conn.execute(
            f"""
            SELECT COUNT(*) AS n
            FROM user_playground_mode_progress
            WHERE user_id = ? AND law_id = ? AND source_locator = ?
              AND status = 'completed' AND mode IN ({placeholders})
            """,
            (uid, law_id, source_locator) + modes,
        ).fetchone()
        if int(count_row["n"] if count_row["n"] is not None else count_row[0]) < TOTAL_PLAYGROUND_MODES:
            return
        nxt = next_revision_date(as_of, REVISION_RUNGS[0])
        self.conn.execute(
            """
            INSERT INTO user_playground_progress (
                user_id, law_id, source_locator, status, cloze_done,
                times_completed, last_completed, next_revision, interval_days,
                source_version, source_hash, updated_at, learned_at
            ) VALUES (?, ?, ?, 'learned', 1, 0, NULL, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (user_id, law_id, source_locator) DO NOTHING
            """,
            (
                uid,
                law_id,
                source_locator,
                _date_iso(nxt),
                REVISION_RUNGS[0],
                source_version,
                source_hash,
                now,
                _date_iso(as_of),
            ),
        )

    def _lock_progress(
        self, uid: str, law_id: str, source_locator: str
    ) -> PlaygroundProgress | None:
        row = self.conn.execute(
            f"""
            SELECT {PROGRESS_COLUMNS}
            FROM user_playground_progress
            WHERE user_id = ? AND law_id = ? AND source_locator = ?
            """,
            (uid, law_id, source_locator),
        ).fetchone()
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
        uid: str,
        law_id: str,
        source_locator: str,
        rung_days: int,
        mode: str,
    ) -> bool:
        row = self.conn.execute(
            """
            SELECT status
            FROM user_playground_revision_mode_progress
            WHERE user_id = ? AND law_id = ? AND source_locator = ?
              AND rung_days = ? AND mode = ?
            """,
            (uid, law_id, source_locator, rung_days, mode),
        ).fetchone()
        return row is not None and str(row["status"]) == MODE_STATUS_COMPLETED

    def _revision_write_plan(
        self,
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
                uid, law_id, source_locator, int(claimed_rung), mode
            )
        ):
            return int(claimed_rung), False
        return self._assert_revision_writable(lifecycle, today, claimed_rung), True

    def _upsert_revision_mode_completed(
        self,
        uid: str,
        law_id: str,
        source_locator: str,
        rung_days: int,
        mode: str,
        *,
        now: str,
        source_version: str,
        source_hash: str,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO user_playground_revision_mode_progress (
                user_id, law_id, source_locator, rung_days, mode, status, attempt_count,
                first_started_at, last_attempt_at, completed_at,
                source_version, source_hash, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'completed', 1, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (user_id, law_id, source_locator, rung_days, mode) DO UPDATE SET
                status = 'completed',
                attempt_count = user_playground_revision_mode_progress.attempt_count + 1,
                first_started_at = COALESCE(
                    user_playground_revision_mode_progress.first_started_at,
                    excluded.first_started_at
                ),
                last_attempt_at = excluded.last_attempt_at,
                completed_at = COALESCE(
                    user_playground_revision_mode_progress.completed_at,
                    excluded.completed_at
                ),
                updated_at = excluded.updated_at
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
        self, uid: str, law_id: str, source_locator: str, rung_days: int
    ) -> int:
        modes = tuple(PLAYGROUND_LEARN_MODES)
        placeholders = ", ".join("?" for _ in modes)
        row = self.conn.execute(
            f"""
            SELECT COUNT(*) AS n
            FROM user_playground_revision_mode_progress
            WHERE user_id = ? AND law_id = ? AND source_locator = ?
              AND rung_days = ? AND status = 'completed' AND mode IN ({placeholders})
            """,
            (uid, law_id, source_locator, rung_days) + modes,
        ).fetchone()
        return int(row["n"] if row["n"] is not None else row[0])

    def _advance_rung_once(
        self,
        uid: str,
        law_id: str,
        source_locator: str,
        *,
        current_rung: int,
        as_of: date,
        now: str,
        source_version: str,
        source_hash: str,
    ) -> None:
        nxt_interval = advance_interval(current_rung)
        if nxt_interval is None:
            status = LIFECYCLE_MASTERED
            interval = current_rung
            nxt: str | None = None
            item_status = "mastered"
        else:
            status = LIFECYCLE_REVIEW
            interval = nxt_interval
            nxt = _date_iso(next_revision_date(as_of, interval))
            item_status = "revising"
        self.conn.execute(
            """
            UPDATE user_playground_progress
            SET times_completed = times_completed + 1,
                last_completed = ?,
                next_revision = ?,
                interval_days = ?,
                status = ?,
                source_version = ?,
                source_hash = ?,
                updated_at = ?
            WHERE user_id = ? AND law_id = ? AND source_locator = ?
              AND interval_days = ?
              AND status != 'mastered'
            """,
            (
                _date_iso(as_of),
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
        self.conn.execute(
            """
            UPDATE user_playground_item
            SET last_activity_at = ?, status = ?
            WHERE user_id = ? AND law_id = ?
            """,
            (now, item_status, uid, law_id),
        )

    def _touch_item_after_revision(self, uid: str, law_id: str, now: str) -> None:
        self.conn.execute(
            """
            UPDATE user_playground_item
            SET last_activity_at = ?,
                status = CASE
                    WHEN status = 'mastered' THEN status
                    ELSE 'revising'
                END
            WHERE user_id = ? AND law_id = ?
            """,
            (now, uid, law_id),
        )

    def _touch_item_learning(self, uid: str, law_id: str, now: str) -> None:
        self.conn.execute(
            """
            UPDATE user_playground_item
            SET last_activity_at = ?,
                status = CASE
                    WHEN status IN ('revising', 'mastered') THEN status
                    ELSE 'learning'
                END
            WHERE user_id = ? AND law_id = ?
            """,
            (now, uid, law_id),
        )

    def _progress_from_row(self, row) -> PlaygroundProgress:
        learned = row["learned_at"] if "learned_at" in row.keys() else None
        return PlaygroundProgress(
            source_locator=row["source_locator"],
            status=row["status"],
            cloze_done=bool(row["cloze_done"]),
            times_completed=int(row["times_completed"]),
            last_completed=row["last_completed"],
            next_revision=row["next_revision"],
            interval_days=int(row["interval_days"]),
            source_version=row["source_version"],
            source_hash=row["source_hash"],
            learned_at=None if learned is None else str(learned)[:10],
        )
