"""Study session records persisted by the progress repositories."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal

StudyKind = Literal["revision", "auto_learning", "one_day_learning"]
StudyStatus = Literal["active", "completed", "abandoned"]
ItemState = Literal["pending", "completed", "deferred"]

VALID_KINDS: frozenset[str] = frozenset(
    ("revision", "auto_learning", "one_day_learning")
)
VALID_STATUSES: frozenset[str] = frozenset(("active", "completed", "abandoned"))
VALID_ITEM_STATES: frozenset[str] = frozenset(("pending", "completed", "deferred"))


@dataclass(frozen=True)
class StudySessionItem:
    session_id: str
    position: int
    learning_unit_id: str
    state: ItemState
    completed_at: str | None
    deferred_at: str | None


@dataclass(frozen=True)
class StudySession:
    id: str
    user_id: str
    kind: StudyKind
    plan_date: date
    status: StudyStatus
    created_at: str
    completed_at: str | None
    items: tuple[StudySessionItem, ...] = field(default_factory=tuple)

    @property
    def pending_items(self) -> tuple[StudySessionItem, ...]:
        return tuple(item for item in self.items if item.state == "pending")

    @property
    def completed_items(self) -> tuple[StudySessionItem, ...]:
        return tuple(item for item in self.items if item.state == "completed")

    @property
    def pending_count(self) -> int:
        return len(self.pending_items)

    @property
    def completed_count(self) -> int:
        return len(self.completed_items)

    def item_for(self, unit_id: str) -> StudySessionItem | None:
        for item in self.items:
            if item.learning_unit_id == unit_id:
                return item
        return None

    def next_pending(self, *, after_unit_id: str | None = None) -> StudySessionItem | None:
        pending = self.pending_items
        if not pending:
            return None
        if after_unit_id is None:
            return pending[0]
        current = self.item_for(after_unit_id)
        if current is None:
            return pending[0]
        for item in pending:
            if item.position > current.position:
                return item
        return None


def _as_date(value: object) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return date.fromisoformat(str(value)[:10])


def study_session_item_from_row(row: object) -> StudySessionItem:
    state_raw = str(row["state"] or "pending")  # type: ignore[index]
    state: ItemState = (
        state_raw if state_raw in VALID_ITEM_STATES else "pending"
    )  # type: ignore[assignment]
    completed = row["completed_at"]  # type: ignore[index]
    deferred = row["deferred_at"]  # type: ignore[index]
    return StudySessionItem(
        session_id=str(row["session_id"]),  # type: ignore[index]
        position=int(row["position"]),  # type: ignore[index]
        learning_unit_id=str(row["learning_unit_id"]),  # type: ignore[index]
        state=state,
        completed_at=None if completed is None else str(completed),
        deferred_at=None if deferred is None else str(deferred),
    )


def study_session_from_row(
    row: object, items: tuple[StudySessionItem, ...] = ()
) -> StudySession:
    kind_raw = str(row["kind"])  # type: ignore[index]
    kind: StudyKind = kind_raw if kind_raw in VALID_KINDS else "revision"  # type: ignore[assignment]
    status_raw = str(row["status"] or "active")  # type: ignore[index]
    status: StudyStatus = (
        status_raw if status_raw in VALID_STATUSES else "active"
    )  # type: ignore[assignment]
    completed = row["completed_at"]  # type: ignore[index]
    return StudySession(
        id=str(row["id"]),  # type: ignore[index]
        user_id=str(row["user_id"]),  # type: ignore[index]
        kind=kind,
        plan_date=_as_date(row["plan_date"]),  # type: ignore[index]
        status=status,
        created_at=str(row["created_at"]),  # type: ignore[index]
        completed_at=None if completed is None else str(completed),
        items=items,
    )
