"""CRUD for learning_unit_progress, split_preference, and app_settings (user-scoped)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Literal
from uuid import UUID

from constitution_memorizer.progress.user_ids import as_user_id

SplitMode = Literal["whole", "letters"]
ProgressStatus = Literal["new", "review", "mastered"]
NotificationFrequency = Literal["twice", "thrice", "hourly"]

NOTIFICATION_FREQUENCY_KEY = "notification_frequency"
NOTIFICATION_LAST_SLOT_KEY = "notification_last_slot"
DEFAULT_NOTIFICATION_FREQUENCY: NotificationFrequency = "thrice"
VALID_NOTIFICATION_FREQUENCIES: frozenset[str] = frozenset(
    ("twice", "thrice", "hourly")
)

THEME_KEY = "theme"
ThemePreference = Literal["auto", "dark", "light"]
DEFAULT_THEME: ThemePreference = "auto"
VALID_THEMES: frozenset[str] = frozenset(("auto", "dark", "light"))

NEWS_ARTICLES_KEY = "news_articles"
DEFAULT_NEWS_ARTICLES = "19"

# First-login onboarding tour. Absent = never offered (pre-existing accounts);
# "active" is set once, when /welcome first saves a display name.
ONBOARDING_KEY = "onboarding_status"
OnboardingStatus = Literal["active", "skipped", "completed"]
VALID_ONBOARDING_STATUSES: frozenset[str] = frozenset(
    ("active", "skipped", "completed")
)

# Study sessions. `kind` is open from the start: revision is the first of
# three queue-shaped features and they differ only in how the snapshot is built.
StudySessionKind = Literal["revision", "auto_learning", "day_plan"]
StudySessionStatus = Literal["active", "complete"]
# 'deferred' is what makes Again tomorrow expressible — the item leaves the
# queue without becoming a completed revision.
StudyItemStatus = Literal["pending", "completed", "deferred"]

LearningPlanMode = Literal["self_paced", "auto"]
DailyNewTarget = Literal[3, 5, 7]
VALID_DAILY_TARGETS: frozenset[int] = frozenset((3, 5, 7))
DEFAULT_LEARNING_PLAN_MODE: LearningPlanMode = "self_paced"

LEARN_MODES: tuple[str, ...] = ("read", "cloze", "letters", "type", "recite", "test")
LEARN_MODES_SET: frozenset[str] = frozenset(LEARN_MODES)

# Canonical partition of the learn modes (this module is the single owner;
# web/ modules and app.js mirror these — keep them in sync).
# Auto-seen: marked complete just by opening the tab / GET.
AUTO_SEEN_MODES: tuple[str, ...] = ("read",)
AUTO_SEEN_MODES_SET: frozenset[str] = frozenset(AUTO_SEEN_MODES)
# Gated: require a completed in-mode attempt before they count.
# Test is gated via POST /quiz only — /seen must reject it.
GATED_MODES: tuple[str, ...] = ("cloze", "letters", "type", "recite", "test")
GATED_MODES_SET: frozenset[str] = frozenset(GATED_MODES)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _date_iso(value: date | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


@dataclass(frozen=True)
class ProgressRecord:

    learning_unit_id: str
    status: ProgressStatus
    times_completed: int
    last_completed: date | None
    next_revision: date | None
    interval_days: int
    ease_factor: float
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class RequestBootstrap:
    """Bundled request-start reads (progress, prefs, settings, optional packs)."""

    progress: list[ProgressRecord]
    split_preferences: dict[str, SplitMode]
    theme: ThemePreference
    news_articles_raw: str | None = None
    profile: dict[str, str | None] | None = None
    settings: dict[str, str] | None = None
    modes_seen_by_unit: dict[str, frozenset[str]] | None = None
    account: AccountBootstrap | None = None


@dataclass(frozen=True)
class CompletionState:
    """Snapshot for one Done: this unit's progress/modes plus the user's split prefs."""

    progress: ProgressRecord | None
    modes_seen: set[str]
    split_preferences: dict[str, SplitMode]


@dataclass(frozen=True)
class CompletionProgress:
    """Engine-owned Done write command. Repository owns created_at / updated_at."""

    status: ProgressStatus
    times_completed: int
    last_completed: date | None
    next_revision: date | None
    interval_days: int
    ease_factor: float


@dataclass(frozen=True)
class StudySessionItem:
    """One unit in a session's snapshot, in the order it was queued."""

    learning_unit_id: str
    position: int
    status: StudyItemStatus
    completed_at: str | None = None


@dataclass(frozen=True)
class StudySession:
    """A snapshotted queue of learning units, walked once and resumable.

    The snapshot is the point: completing a unit pushes its ``next_revision``
    forward, so the due list it was built from stops being recoverable the
    moment the first item is done. Items travel with the session because every
    caller that has one needs them, and a second roundtrip per Learn GET is
    real latency against a remote database.
    """

    id: str
    kind: StudySessionKind
    plan_date: date
    status: StudySessionStatus
    created_at: str
    completed_at: str | None
    items: tuple[StudySessionItem, ...]

    def item_for(self, unit_id: str) -> StudySessionItem | None:
        for item in self.items:
            if item.learning_unit_id == unit_id:
                return item
        return None

    def contains(self, unit_id: str) -> bool:
        return self.item_for(unit_id) is not None

    @property
    def pending(self) -> tuple[StudySessionItem, ...]:
        return tuple(i for i in self.items if i.status == "pending")

    @property
    def remaining(self) -> int:
        return len(self.pending)

    @property
    def completed_count(self) -> int:
        return sum(1 for i in self.items if i.status == "completed")

    def next_pending_after(self, unit_id: str | None) -> str | None:
        """The next still-pending unit, resuming from ``unit_id``'s position.

        Wraps to the front so a unit skipped earlier in the walk is not
        stranded: the queue is exhausted only when nothing is pending.
        """
        current = self.item_for(unit_id) if unit_id else None
        start = current.position if current is not None else -1
        after = [i for i in self.pending if i.position > start]
        if after:
            return after[0].learning_unit_id
        head = [i for i in self.pending if i.learning_unit_id != unit_id]
        return head[0].learning_unit_id if head else None

    def position_of(self, unit_id: str) -> int | None:
        """1-based place in the queue, for "Revision 2 of 6"."""
        for index, item in enumerate(self.items, start=1):
            if item.learning_unit_id == unit_id:
                return index
        return None


@dataclass(frozen=True)
class UserLearningPlan:
    """Persistent Self-paced vs Auto preference. Not a study queue."""

    mode: LearningPlanMode = DEFAULT_LEARNING_PLAN_MODE
    daily_target: int | None = None
    activated_at: date | None = None
    prompt_dismissed_on: date | None = None
    last_anchor_theme: str | None = None
    updated_at: str | None = None

    @property
    def is_auto(self) -> bool:
        return self.mode == "auto" and self.daily_target in VALID_DAILY_TARGETS

    @property
    def is_active_auto(self) -> bool:
        return self.is_auto and self.activated_at is not None


@dataclass(frozen=True)
class BillingOrder:
    """One Razorpay order: created at checkout, paid after verified signature."""

    order_id: str
    user_id: str
    plan_days: int
    amount_paise: int
    currency: str
    status: str  # 'created' | 'paid'
    razorpay_payment_id: str | None
    created_at: str
    paid_at: str | None


def _billing_order_from_row(row: object) -> BillingOrder:
    return BillingOrder(
        order_id=str(row["order_id"]),  # type: ignore[index]
        user_id=str(row["user_id"]),  # type: ignore[index]
        plan_days=int(row["plan_days"]),  # type: ignore[index]
        amount_paise=int(row["amount_paise"]),  # type: ignore[index]
        currency=str(row["currency"]),  # type: ignore[index]
        status=str(row["status"]),  # type: ignore[index]
        razorpay_payment_id=(
            str(row["razorpay_payment_id"])  # type: ignore[index]
            if row["razorpay_payment_id"] is not None  # type: ignore[index]
            else None
        ),
        created_at=str(row["created_at"]),  # type: ignore[index]
        paid_at=(
            str(row["paid_at"])  # type: ignore[index]
            if row["paid_at"] is not None  # type: ignore[index]
            else None
        ),
    )


@dataclass(frozen=True)
class AccountBootstrap:
    """Optional account/commerce snapshot. ``None`` pack means not loaded."""

    claimed_articles: frozenset[str]
    latest_paid_billing_order: BillingOrder | None


def _theme_from_raw(raw: str | None) -> ThemePreference:
    return raw if raw in VALID_THEMES else DEFAULT_THEME  # type: ignore[return-value]


def _news_from_raw(raw: str | None) -> str:
    return DEFAULT_NEWS_ARTICLES if raw is None else raw


def _frequency_from_raw(raw: str | None) -> NotificationFrequency:
    if raw in VALID_NOTIFICATION_FREQUENCIES:
        return raw  # type: ignore[return-value]
    return DEFAULT_NOTIFICATION_FREQUENCY


def _modes_by_unit_from_rows(rows) -> dict[str, frozenset[str]]:
    grouped: dict[str, set[str]] = {}
    for row in rows:
        unit_id = str(row["learning_unit_id"])  # type: ignore[index]
        grouped.setdefault(unit_id, set()).add(str(row["mode"]))  # type: ignore[index]
    return {unit_id: frozenset(modes) for unit_id, modes in grouped.items()}


def _parse_date(value: date | datetime | str | None) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


# One SELECT list, shared by SQLite and Postgres: the session and its items
# come back in a single roundtrip, aliased so neither table's `id`, `status`
# or `completed_at` shadows the other's.
_STUDY_SESSION_COLUMNS = """
    s.id AS session_id,
    s.kind AS kind,
    s.plan_date AS plan_date,
    s.status AS session_status,
    s.created_at AS session_created_at,
    s.completed_at AS session_completed_at,
    i.learning_unit_id AS learning_unit_id,
    i.position AS position,
    i.status AS item_status,
    i.completed_at AS item_completed_at
"""


def _as_text(value: object) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _study_session_from_rows(rows: list) -> StudySession | None:
    """Rebuild one session from its LEFT JOINed rows (empty queue = one row)."""
    if not rows:
        return None
    head = rows[0]
    items = tuple(
        StudySessionItem(
            learning_unit_id=str(row["learning_unit_id"]),
            position=int(row["position"]),
            status=row["item_status"],
            completed_at=_as_text(row["item_completed_at"]),
        )
        for row in rows
        if row["learning_unit_id"] is not None
    )
    plan_date = head["plan_date"]
    return StudySession(
        id=str(head["session_id"]),
        kind=head["kind"],
        plan_date=(
            plan_date if isinstance(plan_date, date) else date.fromisoformat(str(plan_date))
        ),
        status=head["session_status"],
        created_at=str(_as_text(head["session_created_at"])),
        completed_at=_as_text(head["session_completed_at"]),
        items=tuple(sorted(items, key=lambda i: i.position)),
    )


def _row_to_progress(row: sqlite3.Row) -> ProgressRecord:
    return ProgressRecord(
        learning_unit_id=row["learning_unit_id"],
        status=row["status"],  # type: ignore[arg-type]
        times_completed=int(row["times_completed"]),
        last_completed=_parse_date(row["last_completed"]),
        next_revision=_parse_date(row["next_revision"]),
        interval_days=int(row["interval_days"]),
        ease_factor=float(row["ease_factor"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_learning_plan(row: object | None) -> UserLearningPlan:
    if row is None:
        return UserLearningPlan()
    mapping = row
    target = mapping["daily_target"]  # type: ignore[index]
    return UserLearningPlan(
        mode=mapping["mode"] or DEFAULT_LEARNING_PLAN_MODE,  # type: ignore[index]
        daily_target=int(target) if target is not None else None,
        activated_at=_parse_date(mapping["activated_at"]),  # type: ignore[index]
        prompt_dismissed_on=_parse_date(mapping["prompt_dismissed_on"]),  # type: ignore[index]
        last_anchor_theme=mapping["last_anchor_theme"],  # type: ignore[index]
        updated_at=_as_text(mapping["updated_at"]),  # type: ignore[index]
    )


class ProgressRepository:
    """SQLite-backed user-scoped progress and preference store."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn

    def get_progress(self, user_id: UUID | str, unit_id: str) -> ProgressRecord | None:
        uid = as_user_id(user_id)
        row = self._conn.execute(
            """
            SELECT * FROM learning_unit_progress
            WHERE user_id = ? AND learning_unit_id = ?
            """,
            (uid, unit_id),
        ).fetchone()
        return _row_to_progress(row) if row else None

    def ensure_progress(self, user_id: UUID | str, unit_id: str) -> ProgressRecord:
        existing = self.get_progress(user_id, unit_id)
        if existing is not None:
            return existing
        now = _utc_now_iso()
        uid = as_user_id(user_id)
        self._conn.execute(
            """
            INSERT INTO learning_unit_progress (
                user_id, learning_unit_id, status, times_completed, last_completed,
                next_revision, interval_days, ease_factor, created_at, updated_at
            ) VALUES (?, ?, 'new', 0, NULL, NULL, 0, 2.5, ?, ?)
            """,
            (uid, unit_id, now, now),
        )
        self._conn.commit()
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
        now = _utc_now_iso()
        uid = as_user_id(user_id)
        existing = self.get_progress(user_id, unit_id)
        if existing is None:
            self._conn.execute(
                """
                INSERT INTO learning_unit_progress (
                    user_id, learning_unit_id, status, times_completed, last_completed,
                    next_revision, interval_days, ease_factor, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    uid,
                    unit_id,
                    status,
                    times_completed,
                    _date_iso(last_completed),
                    _date_iso(next_revision),
                    interval_days,
                    ease_factor,
                    now,
                    now,
                ),
            )
        else:
            self._conn.execute(
                """
                UPDATE learning_unit_progress
                SET status = ?, times_completed = ?, last_completed = ?,
                    next_revision = ?, interval_days = ?, ease_factor = ?,
                    updated_at = ?
                WHERE user_id = ? AND learning_unit_id = ?
                """,
                (
                    status,
                    times_completed,
                    _date_iso(last_completed),
                    _date_iso(next_revision),
                    interval_days,
                    ease_factor,
                    now,
                    uid,
                    unit_id,
                ),
            )
        self._conn.commit()
        record = self.get_progress(user_id, unit_id)
        assert record is not None
        return record

    def delete_progress(self, user_id: UUID | str, unit_id: str) -> None:
        self._conn.execute(
            "DELETE FROM learning_unit_progress WHERE user_id = ? AND learning_unit_id = ?",
            (as_user_id(user_id), unit_id),
        )
        self._conn.commit()

    def delete_all_progress(self, user_id: UUID | str) -> None:
        uid = as_user_id(user_id)
        self._conn.execute("DELETE FROM learning_unit_progress WHERE user_id = ?", (uid,))
        self._conn.execute("DELETE FROM split_preference WHERE user_id = ?", (uid,))
        self._conn.commit()

    def list_due(
        self,
        user_id: UUID | str,
        as_of: date,
        *,
        include_new: bool = False,
    ) -> list[ProgressRecord]:
        uid = as_user_id(user_id)
        rows = self._conn.execute(
            """
            SELECT * FROM learning_unit_progress
            WHERE user_id = ?
              AND status = 'review'
              AND next_revision IS NOT NULL
              AND next_revision <= ?
            ORDER BY next_revision ASC, learning_unit_id ASC
            """,
            (uid, _date_iso(as_of)),
        ).fetchall()
        due = [_row_to_progress(r) for r in rows]
        if include_new:
            new_rows = self._conn.execute(
                """
                SELECT * FROM learning_unit_progress
                WHERE user_id = ? AND status = 'new'
                ORDER BY learning_unit_id ASC
                """,
                (uid,),
            ).fetchall()
            due.extend(_row_to_progress(r) for r in new_rows)
        return due

    def list_all_progress(self, user_id: UUID | str) -> list[ProgressRecord]:
        rows = self._conn.execute(
            """
            SELECT * FROM learning_unit_progress
            WHERE user_id = ?
            ORDER BY learning_unit_id ASC
            """,
            (as_user_id(user_id),),
        ).fetchall()
        return [_row_to_progress(r) for r in rows]

    def count_by_status(self, user_id: UUID | str) -> dict[str, int]:
        rows = self._conn.execute(
            """
            SELECT status, COUNT(*) AS n
            FROM learning_unit_progress
            WHERE user_id = ?
            GROUP BY status
            """,
            (as_user_id(user_id),),
        ).fetchall()
        return {str(r["status"]): int(r["n"]) for r in rows}

    def get_split_preference(
        self, user_id: UUID | str, parent_clause_id: str
    ) -> SplitMode | None:
        row = self._conn.execute(
            """
            SELECT mode FROM split_preference
            WHERE user_id = ? AND parent_clause_id = ?
            """,
            (as_user_id(user_id), parent_clause_id),
        ).fetchone()
        if row is None:
            return None
        return row["mode"]  # type: ignore[return-value]

    def set_split_preference(
        self,
        user_id: UUID | str,
        parent_clause_id: str,
        mode: SplitMode,
    ) -> None:
        if mode not in ("whole", "letters"):
            raise ValueError(f"Invalid split preference mode: {mode}")
        now = _utc_now_iso()
        self._conn.execute(
            """
            INSERT INTO split_preference (user_id, parent_clause_id, mode, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, parent_clause_id) DO UPDATE SET
                mode = excluded.mode,
                updated_at = excluded.updated_at
            """,
            (as_user_id(user_id), parent_clause_id, mode, now),
        )
        self._conn.commit()

    def delete_split_preference(self, user_id: UUID | str, parent_clause_id: str) -> None:
        self._conn.execute(
            "DELETE FROM split_preference WHERE user_id = ? AND parent_clause_id = ?",
            (as_user_id(user_id), parent_clause_id),
        )
        self._conn.commit()

    def list_split_preferences(self, user_id: UUID | str) -> dict[str, SplitMode]:
        rows = self._conn.execute(
            "SELECT parent_clause_id, mode FROM split_preference WHERE user_id = ?",
            (as_user_id(user_id),),
        ).fetchall()
        return {str(r["parent_clause_id"]): r["mode"] for r in rows}  # type: ignore[misc]

    def get_gloss(self, user_id: UUID | str, article_number: str) -> str | None:
        row = self._conn.execute(
            """
            SELECT text FROM article_gloss
            WHERE user_id = ? AND article_number = ?
            """,
            (as_user_id(user_id), article_number),
        ).fetchone()
        if row is None:
            return None
        return str(row["text"])

    def upsert_gloss(self, user_id: UUID | str, article_number: str, text: str) -> None:
        now = _utc_now_iso()
        self._conn.execute(
            """
            INSERT INTO article_gloss (user_id, article_number, text, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, article_number) DO UPDATE SET
                text = excluded.text,
                updated_at = excluded.updated_at
            """,
            (as_user_id(user_id), article_number, text, now),
        )
        self._conn.commit()

    def delete_gloss(self, user_id: UUID | str, article_number: str) -> None:
        self._conn.execute(
            "DELETE FROM article_gloss WHERE user_id = ? AND article_number = ?",
            (as_user_id(user_id), article_number),
        )
        self._conn.commit()

    # ------------------------------------------------------------------ #
    # Free-Article entitlement slots (parent Article level)               #
    # ------------------------------------------------------------------ #
    def claimed_articles(self, user_id: UUID | str) -> set[str]:
        rows = self._conn.execute(
            "SELECT article_number FROM user_free_articles WHERE user_id = ?",
            (as_user_id(user_id),),
        ).fetchall()
        return {str(r["article_number"]) for r in rows}

    def claimed_articles_with_dates(self, user_id: UUID | str) -> dict[str, str]:
        """Claimed parent Articles mapped to their claimed_at ISO timestamp."""
        rows = self._conn.execute(
            "SELECT article_number, claimed_at FROM user_free_articles WHERE user_id = ?",
            (as_user_id(user_id),),
        ).fetchall()
        return {str(r["article_number"]): str(r["claimed_at"]) for r in rows}

    def is_article_claimed(self, user_id: UUID | str, article_number: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM user_free_articles WHERE user_id = ? AND article_number = ?",
            (as_user_id(user_id), str(article_number)),
        ).fetchone()
        return row is not None

    def claim_article(self, user_id: UUID | str, article_number: str) -> None:
        """Idempotently claim a parent Article as one of the user's Free Articles."""
        self._conn.execute(
            """
            INSERT INTO user_free_articles (user_id, article_number, claimed_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, article_number) DO NOTHING
            """,
            (as_user_id(user_id), str(article_number), _utc_now_iso()),
        )
        self._conn.commit()

    # ------------------------------------------------------------------ #
    # Study sessions (revision / auto-learning / day-plan queues)         #
    # ------------------------------------------------------------------ #
    def create_study_session(
        self,
        user_id: UUID | str,
        *,
        session_id: str,
        kind: StudySessionKind,
        plan_date: date,
        unit_ids: list[str],
    ) -> StudySession:
        """Atomic create-or-get for one (user, kind, plan_date) snapshot.

        On a unique-day conflict the winner's existing session is returned and
        no items are written against the losing ``session_id``.
        """
        existing = self.get_study_session(user_id, session_id)
        if existing is not None:
            return existing
        existing_day = self.study_session_for_day(
            user_id, kind=kind, plan_date=plan_date
        )
        if existing_day is not None:
            return existing_day
        now = _utc_now_iso()
        uid = as_user_id(user_id)
        ordered: list[str] = []
        for unit_id in unit_ids:
            if unit_id not in ordered:
                ordered.append(unit_id)
        try:
            self._conn.execute(
                """
                INSERT INTO study_session (
                    id, user_id, kind, plan_date, status, created_at, completed_at
                ) VALUES (?, ?, ?, ?, 'active', ?, NULL)
                """,
                (session_id, uid, kind, _date_iso(plan_date), now),
            )
        except sqlite3.IntegrityError:
            self._conn.rollback()
            winner = self.study_session_for_day(
                user_id, kind=kind, plan_date=plan_date
            ) or self.get_study_session(user_id, session_id)
            if winner is not None:
                return winner
            raise
        if ordered:
            self._conn.executemany(
                """
                INSERT INTO study_session_item (
                    session_id, learning_unit_id, position, status, completed_at
                ) VALUES (?, ?, ?, 'pending', NULL)
                """,
                [(session_id, unit_id, index) for index, unit_id in enumerate(ordered)],
            )
        self._conn.commit()
        session = self.get_study_session(user_id, session_id)
        assert session is not None
        return session

    def get_study_session(
        self, user_id: UUID | str, session_id: str
    ) -> StudySession | None:
        rows = self._conn.execute(
            f"""
            SELECT {_STUDY_SESSION_COLUMNS}
            FROM study_session s
            LEFT JOIN study_session_item i ON i.session_id = s.id
            WHERE s.user_id = ? AND s.id = ?
            ORDER BY i.position ASC
            """,
            (as_user_id(user_id), session_id),
        ).fetchall()
        return _study_session_from_rows(rows)

    def active_study_session(
        self,
        user_id: UUID | str,
        *,
        kind: StudySessionKind,
        plan_date: date | None = None,
    ) -> StudySession | None:
        """The user's newest active session of this kind (optionally for a day)."""
        clause = "" if plan_date is None else " AND s.plan_date = ?"
        params: list[object] = [as_user_id(user_id), kind]
        if plan_date is not None:
            params.append(_date_iso(plan_date))
        rows = self._conn.execute(
            f"""
            SELECT {_STUDY_SESSION_COLUMNS}
            FROM study_session s
            LEFT JOIN study_session_item i ON i.session_id = s.id
            WHERE s.user_id = ? AND s.kind = ? AND s.status = 'active'{clause}
            ORDER BY s.created_at DESC, s.id DESC, i.position ASC
            """,
            params,
        ).fetchall()
        if not rows:
            return None
        newest = rows[0]["session_id"]
        return _study_session_from_rows(
            [row for row in rows if row["session_id"] == newest]
        )

    def study_session_for_day(
        self,
        user_id: UUID | str,
        *,
        kind: StudySessionKind,
        plan_date: date,
    ) -> StudySession | None:
        """The unique session for this user/kind/local date, active or complete."""
        rows = self._conn.execute(
            f"""
            SELECT {_STUDY_SESSION_COLUMNS}
            FROM study_session s
            LEFT JOIN study_session_item i ON i.session_id = s.id
            WHERE s.user_id = ? AND s.kind = ? AND s.plan_date = ?
            ORDER BY s.created_at ASC, s.id ASC, i.position ASC
            """,
            (as_user_id(user_id), kind, _date_iso(plan_date)),
        ).fetchall()
        if not rows:
            return None
        keeper = rows[0]["session_id"]
        return _study_session_from_rows(
            [row for row in rows if row["session_id"] == keeper]
        )

    def set_study_item_status(
        self,
        user_id: UUID | str,
        *,
        session_id: str,
        unit_id: str,
        status: StudyItemStatus,
    ) -> None:
        completed_at = _utc_now_iso() if status == "completed" else None
        self._conn.execute(
            """
            UPDATE study_session_item
            SET status = ?, completed_at = ?
            WHERE session_id = ? AND learning_unit_id = ?
              AND session_id IN (SELECT id FROM study_session WHERE user_id = ?)
            """,
            (status, completed_at, session_id, unit_id, as_user_id(user_id)),
        )
        self._conn.commit()

    def replace_study_session_unit(
        self,
        user_id: UUID | str,
        *,
        session_id: str,
        old_unit_id: str,
        new_unit_ids: list[str],
    ) -> StudySession | None:
        """Swap one pending queue item for one or more units, keeping order.

        Used when a split-capable parent in a session is resolved to Letters:
        the parent row is replaced by its letter children at the same position.
        """
        session = self.get_study_session(user_id, session_id)
        if session is None:
            return None
        current = session.item_for(old_unit_id)
        if current is None or current.status != "pending":
            return session
        existing = {item.learning_unit_id for item in session.items}
        ordered: list[str] = []
        for unit_id in new_unit_ids:
            if not unit_id or unit_id == old_unit_id:
                continue
            if unit_id in existing and unit_id != old_unit_id:
                continue
            if unit_id not in ordered:
                ordered.append(unit_id)
        if not ordered:
            return session
        shift = len(ordered) - 1
        uid = as_user_id(user_id)
        try:
            if shift > 0:
                self._conn.execute(
                    """
                    UPDATE study_session_item
                    SET position = position + ?
                    WHERE session_id = ?
                      AND position > ?
                      AND session_id IN (SELECT id FROM study_session WHERE user_id = ?)
                    """,
                    (shift, session_id, current.position, uid),
                )
            self._conn.execute(
                """
                DELETE FROM
                    study_session_item
                WHERE session_id = ? AND learning_unit_id = ?
                  AND session_id IN (SELECT id FROM study_session WHERE user_id = ?)
                """,
                (session_id, old_unit_id, uid),
            )
            self._conn.executemany(
                """
                INSERT INTO study_session_item (
                    session_id, learning_unit_id, position, status, completed_at
                ) VALUES (?, ?, ?, 'pending', NULL)
                """,
                [
                    (session_id, unit_id, current.position + index)
                    for index, unit_id in enumerate(ordered)
                ],
            )
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        return self.get_study_session(user_id, session_id)

    def complete_study_session(self, user_id: UUID | str, session_id: str) -> None:
        self._conn.execute(
            """
            UPDATE study_session
            SET status = 'complete', completed_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (_utc_now_iso(), session_id, as_user_id(user_id)),
        )
        self._conn.commit()

    # ------------------------------------------------------------------ #
    # Learning plan preference (Self-paced / Auto 3/5/7)                  #
    # ------------------------------------------------------------------ #
    def get_learning_plan(self, user_id: UUID | str) -> UserLearningPlan:
        row = self._conn.execute(
            """
            SELECT mode, daily_target, activated_at, prompt_dismissed_on,
                   last_anchor_theme, updated_at
            FROM user_learning_plan
            WHERE user_id = ?
            """,
            (as_user_id(user_id),),
        ).fetchone()
        return _row_to_learning_plan(row)

    def upsert_learning_plan(
        self,
        user_id: UUID | str,
        *,
        mode: LearningPlanMode,
        daily_target: int | None,
        prompt_dismissed_on: date | None = None,
        last_anchor_theme: str | None = None,
    ) -> UserLearningPlan:
        if mode == "auto":
            if daily_target not in VALID_DAILY_TARGETS:
                raise ValueError("auto mode requires daily_target of 3, 5, or 7")
        else:
            daily_target = None
        now = _utc_now_iso()
        uid = as_user_id(user_id)
        current = self.get_learning_plan(user_id)
        dismissed = (
            prompt_dismissed_on
            if prompt_dismissed_on is not None
            else current.prompt_dismissed_on
        )
        theme = (
            last_anchor_theme
            if last_anchor_theme is not None
            else current.last_anchor_theme
        )
        self._conn.execute(
            """
            INSERT INTO user_learning_plan (
                user_id, mode, daily_target, activated_at,
                prompt_dismissed_on, last_anchor_theme, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                mode = excluded.mode,
                daily_target = excluded.daily_target,
                prompt_dismissed_on = excluded.prompt_dismissed_on,
                last_anchor_theme = excluded.last_anchor_theme,
                updated_at = excluded.updated_at
            """,
            (
                uid,
                mode,
                daily_target,
                _date_iso(current.activated_at),
                _date_iso(dismissed),
                theme,
                now,
            ),
        )
        self._conn.commit()
        return self.get_learning_plan(user_id)

    def activate_learning_plan(
        self, user_id: UUID | str, as_of: date
    ) -> UserLearningPlan:
        """Set activated_at once, on first persisted NEW Done while Auto is on."""
        uid = as_user_id(user_id)
        now = _utc_now_iso()
        self._conn.execute(
            """
            UPDATE user_learning_plan
            SET activated_at = ?, updated_at = ?
            WHERE user_id = ?
              AND mode = 'auto'
              AND activated_at IS NULL
            """,
            (_date_iso(as_of), now, uid),
        )
        self._conn.commit()
        return self.get_learning_plan(user_id)

    def dismiss_plan_prompt(
        self, user_id: UUID | str, as_of: date
    ) -> UserLearningPlan:
        uid = as_user_id(user_id)
        now = _utc_now_iso()
        current = self.get_learning_plan(user_id)
        self._conn.execute(
            """
            INSERT INTO user_learning_plan (
                user_id, mode, daily_target, activated_at,
                prompt_dismissed_on, last_anchor_theme, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                prompt_dismissed_on = excluded.prompt_dismissed_on,
                updated_at = excluded.updated_at
            """,
            (
                uid,
                current.mode,
                current.daily_target,
                _date_iso(current.activated_at),
                _date_iso(as_of),
                current.last_anchor_theme,
                now,
            ),
        )
        self._conn.commit()
        return self.get_learning_plan(user_id)

    def set_last_anchor_theme(
        self, user_id: UUID | str, theme: str | None
    ) -> None:
        uid = as_user_id(user_id)
        now = _utc_now_iso()
        current = self.get_learning_plan(user_id)
        self._conn.execute(
            """
            INSERT INTO user_learning_plan (
                user_id, mode, daily_target, activated_at,
                prompt_dismissed_on, last_anchor_theme, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                last_anchor_theme = excluded.last_anchor_theme,
                updated_at = excluded.updated_at
            """,
            (
                uid,
                current.mode,
                current.daily_target,
                _date_iso(current.activated_at),
                _date_iso(current.prompt_dismissed_on),
                theme,
                now,
            ),
        )
        self._conn.commit()

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
        self._conn.execute(
            """
            INSERT INTO billing_orders (
                order_id, user_id, plan_days, amount_paise, currency,
                status, created_at
            )
            VALUES (?, ?, ?, ?, ?, 'created', ?)
            """,
            (
                order_id,
                as_user_id(user_id),
                int(plan_days),
                int(amount_paise),
                currency,
                _utc_now_iso(),
            ),
        )
        self._conn.commit()

    def get_billing_order(
        self, user_id: UUID | str, order_id: str
    ) -> BillingOrder | None:
        row = self._conn.execute(
            "SELECT * FROM billing_orders WHERE order_id = ? AND user_id = ?",
            (order_id, as_user_id(user_id)),
        ).fetchone()
        return _billing_order_from_row(row) if row is not None else None

    def latest_paid_billing_order(self, user_id: UUID | str) -> BillingOrder | None:
        row = self._conn.execute(
            """
            SELECT * FROM billing_orders
            WHERE user_id = ? AND status = 'paid'
            ORDER BY paid_at DESC LIMIT 1
            """,
            (as_user_id(user_id),),
        ).fetchone()
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

        The 'payment'-source access_grants row rides the same commit as the
        order update so either both persist or neither does. Returns False
        (and writes nothing) when the order is already paid — a replayed
        verify callback never double-grants.
        """
        uid = as_user_id(user_id)
        now = _utc_now_iso()
        cursor = self._conn.execute(
            """
            UPDATE billing_orders
            SET status = 'paid', razorpay_payment_id = ?, paid_at = ?
            WHERE order_id = ? AND user_id = ? AND status = 'created'
            """,
            (payment_id, now, order_id, uid),
        )
        if cursor.rowcount == 0:
            self._conn.rollback()
            return False
        self._conn.execute(
            """
            INSERT INTO access_grants (
                id, user_id, source, starts_at, ends_at, reason, created_at
            )
            VALUES (?, ?, 'payment', ?, ?, ?, ?)
            """,
            (grant_id, uid, now, access_ends_at, f"razorpay:{order_id}", now),
        )
        self._conn.commit()
        return True

    def get_setting(self, user_id: UUID | str, key: str) -> str | None:
        row = self._conn.execute(
            "SELECT value FROM app_settings WHERE user_id = ? AND key = ?",
            (as_user_id(user_id), key),
        ).fetchone()
        if row is None:
            return None
        return str(row["value"])

    def set_setting(self, user_id: UUID | str, key: str, value: str) -> None:
        now = _utc_now_iso()
        self._conn.execute(
            """
            INSERT INTO app_settings (user_id, key, value, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
            """,
            (as_user_id(user_id), key, value, now),
        )
        self._conn.commit()

    def get_notification_frequency(self, user_id: UUID | str) -> NotificationFrequency:
        raw = self.get_setting(user_id, NOTIFICATION_FREQUENCY_KEY)
        if raw in VALID_NOTIFICATION_FREQUENCIES:
            return raw  # type: ignore[return-value]
        return DEFAULT_NOTIFICATION_FREQUENCY

    def set_notification_frequency(
        self, user_id: UUID | str, frequency: NotificationFrequency
    ) -> None:
        if frequency not in VALID_NOTIFICATION_FREQUENCIES:
            raise ValueError(f"Invalid notification frequency: {frequency}")
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

    def get_theme(self, user_id: UUID | str) -> ThemePreference:
        raw = self.get_setting(user_id, THEME_KEY)
        if raw in VALID_THEMES:
            return raw  # type: ignore[return-value]
        return DEFAULT_THEME

    def set_theme(self, user_id: UUID | str, theme: ThemePreference) -> None:
        if theme not in VALID_THEMES:
            raise ValueError(f"Invalid theme: {theme}")
        self.set_setting(user_id, THEME_KEY, theme)

    def get_news_articles_raw(self, user_id: UUID | str) -> str:
        raw = self.get_setting(user_id, NEWS_ARTICLES_KEY)
        if raw is None:
            return DEFAULT_NEWS_ARTICLES
        return raw

    def set_news_articles_raw(self, user_id: UUID | str, value: str) -> None:
        self.set_setting(user_id, NEWS_ARTICLES_KEY, value.strip())

    def mark_mode_seen(self, user_id: UUID | str, unit_id: str, mode: str) -> set[str]:
        if mode not in LEARN_MODES_SET:
            raise ValueError(f"Invalid learn mode: {mode}")
        now = _utc_now_iso()
        self._conn.execute(
            """
            INSERT INTO unit_modes_seen (user_id, learning_unit_id, mode, seen_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, learning_unit_id, mode) DO UPDATE SET
                seen_at = excluded.seen_at
            """,
            (as_user_id(user_id), unit_id, mode, now),
        )
        self._conn.commit()
        return self.modes_seen(user_id, unit_id)

    def modes_seen(self, user_id: UUID | str, unit_id: str) -> set[str]:
        rows = self._conn.execute(
            """
            SELECT mode FROM unit_modes_seen
            WHERE user_id = ? AND learning_unit_id = ?
            """,
            (as_user_id(user_id), unit_id),
        ).fetchall()
        return {str(r["mode"]) for r in rows}

    def clear_modes_seen(self, user_id: UUID | str, unit_id: str) -> None:
        self._conn.execute(
            "DELETE FROM unit_modes_seen WHERE user_id = ? AND learning_unit_id = ?",
            (as_user_id(user_id), unit_id),
        )
        self._conn.commit()

    def clear_all_modes_seen(self, user_id: UUID | str) -> None:
        self._conn.execute(
            "DELETE FROM unit_modes_seen WHERE user_id = ?",
            (as_user_id(user_id),),
        )
        self._conn.commit()

    def modes_complete(self, user_id: UUID | str, unit_id: str) -> bool:
        return self.modes_seen(user_id, unit_id) >= LEARN_MODES_SET

    def upsert_profile(
        self,
        user_id: UUID | str,
        *,
        display_name: str | None,
        avatar_url: str | None,
    ) -> None:
        now = _utc_now_iso()
        uid = as_user_id(user_id)
        existing = self.get_profile(user_id)
        if existing is None:
            self._conn.execute(
                """
                INSERT INTO user_profile (user_id, display_name, avatar_url, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (uid, display_name, avatar_url, now, now),
            )
        else:
            self._conn.execute(
                """
                UPDATE user_profile
                SET display_name = ?, avatar_url = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (display_name, avatar_url, now, uid),
            )
        self._conn.commit()

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
        now = _utc_now_iso()
        self._conn.execute(
            """
            INSERT INTO user_profile (
                user_id, display_name, avatar_url, created_at, updated_at,
                email, phone, last_sign_in_at
            ) VALUES (?, NULL, NULL, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                email = COALESCE(excluded.email, user_profile.email),
                phone = COALESCE(excluded.phone, user_profile.phone),
                last_sign_in_at = excluded.last_sign_in_at
            """,
            (as_user_id(user_id), now, now, email, phone, now),
        )
        self._conn.commit()

    def get_profile(self, user_id: UUID | str) -> dict[str, str | None] | None:
        row = self._conn.execute(
            """
            SELECT user_id, display_name, avatar_url, created_at, updated_at
            FROM user_profile WHERE user_id = ?
            """,
            (as_user_id(user_id),),
        ).fetchone()
        if row is None:
            return None
        return {
            "user_id": str(row["user_id"]),
            "display_name": row["display_name"],
            "avatar_url": row["avatar_url"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

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
        settings_rows = self._conn.execute(
            "SELECT key, value FROM app_settings WHERE user_id = ?",
            (uid,),
        ).fetchall()
        settings = {str(row["key"]): str(row["value"]) for row in settings_rows}
        modes: dict[str, frozenset[str]] | None = None
        if include_modes:
            mode_rows = self._conn.execute(
                "SELECT learning_unit_id, mode FROM unit_modes_seen WHERE user_id = ?",
                (uid,),
            ).fetchall()
            modes = _modes_by_unit_from_rows(mode_rows)
        account: AccountBootstrap | None = None
        if include_account:
            account = AccountBootstrap(
                claimed_articles=frozenset(self.claimed_articles(user_id)),
                latest_paid_billing_order=self.latest_paid_billing_order(user_id),
            )
        return RequestBootstrap(
            progress=self.list_all_progress(user_id),
            split_preferences=self.list_split_preferences(user_id),
            theme=_theme_from_raw(settings.get(THEME_KEY)),
            news_articles_raw=(
                _news_from_raw(settings.get(NEWS_ARTICLES_KEY)) if include_news else None
            ),
            profile=self.get_profile(user_id) if include_profile else None,
            settings=settings,
            modes_seen_by_unit=modes,
            account=account,
        )

    def load_completion_state(
        self, user_id: UUID | str, unit_id: str
    ) -> CompletionState:
        return CompletionState(
            progress=self.get_progress(user_id, unit_id),
            modes_seen=self.modes_seen(user_id, unit_id),
            split_preferences=self.list_split_preferences(user_id),
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

        The claim rides in the same transaction so either the Article claim,
        the progress row, and the modes reset all land — or none do.
        """
        now = _utc_now_iso()
        uid = as_user_id(user_id)
        try:
            if claim_article:
                self._conn.execute(
                    """
                    INSERT INTO user_free_articles (user_id, article_number, claimed_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(user_id, article_number) DO NOTHING
                    """,
                    (uid, str(claim_article), now),
                )
            self._conn.execute(
                """
                INSERT INTO learning_unit_progress (
                    user_id, learning_unit_id, status, times_completed, last_completed,
                    next_revision, interval_days, ease_factor, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, learning_unit_id) DO UPDATE SET
                    status = excluded.status,
                    times_completed = excluded.times_completed,
                    last_completed = excluded.last_completed,
                    next_revision = excluded.next_revision,
                    interval_days = excluded.interval_days,
                    ease_factor = excluded.ease_factor,
                    updated_at = excluded.updated_at
                """,
                (
                    uid,
                    unit_id,
                    progress.status,
                    progress.times_completed,
                    _date_iso(progress.last_completed),
                    _date_iso(progress.next_revision),
                    progress.interval_days,
                    progress.ease_factor,
                    now,
                    now,
                ),
            )
            self._conn.execute(
                "DELETE FROM unit_modes_seen WHERE user_id = ? AND learning_unit_id = ?",
                (uid, unit_id),
            )
            row = self._conn.execute(
                """
                SELECT * FROM learning_unit_progress
                WHERE user_id = ? AND learning_unit_id = ?
                """,
                (uid, unit_id),
            ).fetchone()
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        assert row is not None
        return _row_to_progress(row)


# Backward-compatible alias used by docs/plan wording.
SQLiteProgressRepository = ProgressRepository
