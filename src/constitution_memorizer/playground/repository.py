"""User-owned Playground state. Isolation is application-level (user_id)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from uuid import UUID

from constitution_memorizer.progress.user_ids import as_user_id
from constitution_memorizer.playground.revision import (
    advance_interval,
    next_revision_date,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _date_iso(value: date | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


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
    learned_count: int
    to_learn_count: int
    due_count: int


def playground_summary_sql(placeholder: str) -> str:
    """One aggregate query: items + selection counts + selected-progress counts.

    Placeholders, in order: user_id, as_of, user_id, user_id.
    Subqueries are grouped by law_id so joins cannot cartesian-inflate counts.
    """
    ph = placeholder
    return f"""
            SELECT
                i.law_id, i.status, i.added_at, i.last_activity_at,
                i.source_version, i.law_source_hash,
                COALESCE(sel.selected_count, 0) AS selected_count,
                COALESCE(prog.learned_count, 0) AS learned_count,
                COALESCE(prog.due_count, 0) AS due_count
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
                        WHEN p.cloze_done != 0 THEN s.source_locator
                    END) AS learned_count,
                    COUNT(DISTINCT CASE
                        WHEN p.cloze_done != 0
                         AND p.status != 'mastered'
                         AND p.next_revision IS NOT NULL
                         AND p.next_revision <= {ph}
                        THEN s.source_locator
                    END) AS due_count
                FROM user_playground_selection AS s
                LEFT JOIN user_playground_progress AS p
                  ON p.user_id = s.user_id
                 AND p.law_id = s.law_id
                 AND p.source_locator = s.source_locator
                WHERE s.user_id = {ph}
                GROUP BY s.law_id
            ) AS prog ON prog.law_id = i.law_id
            WHERE i.user_id = {ph}
            ORDER BY i.added_at ASC
            """


def summary_from_row(row, *, added_at: str, last_activity_at: str) -> PlaygroundSummary:
    selected = int(row["selected_count"] or 0)
    learned = int(row["learned_count"] or 0)
    due = int(row["due_count"] or 0)
    return PlaygroundSummary(
        law_id=row["law_id"],
        status=row["status"],
        added_at=added_at,
        last_activity_at=last_activity_at,
        source_version=row["source_version"],
        law_source_hash=row["law_source_hash"],
        selected_count=selected,
        learned_count=learned,
        to_learn_count=max(0, selected - learned),
        due_count=due,
    )


class SqlitePlaygroundRepository:
    def __init__(self, conn) -> None:
        self.conn = conn

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
        self, user_id: UUID | str, *, as_of: date
    ) -> list[PlaygroundSummary]:
        uid = as_user_id(user_id)
        rows = self.conn.execute(
            playground_summary_sql("?"),
            (uid, as_of.isoformat(), uid, uid),
        ).fetchall()
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
                   source_version, source_hash
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
                   source_version, source_hash
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
        )

    def _progress_from_row(self, row) -> PlaygroundProgress:
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
        )
