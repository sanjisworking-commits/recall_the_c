"""Playground revision lifecycle read models.

Initial six-mode completion lives in ``user_playground_mode_progress``.
Scheduled-rung methods live in ``user_playground_revision_mode_progress``.
``user_playground_progress`` is the schedule / Learned → Mastered row.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from constitution_memorizer.playground.learning.models import (
    MODE_STATUS_COMPLETED,
    MODE_STATUS_IN_PROGRESS,
    ModeProgressRow,
)
from constitution_memorizer.playground.learning.modes import (
    PLAYGROUND_LEARN_MODES,
    TOTAL_PLAYGROUND_MODES,
    next_learn_mode,
)
from constitution_memorizer.playground.revision import INTERVAL_LADDER

LIFECYCLE_LEARNED = "learned"
LIFECYCLE_REVIEW = "review"
LIFECYCLE_MASTERED = "mastered"
LIFECYCLE_ACTIVE = frozenset({LIFECYCLE_LEARNED, LIFECYCLE_REVIEW, LIFECYCLE_MASTERED})
REVISION_RUNGS: tuple[int, ...] = INTERVAL_LADDER
REVISION_RUNGS_SET: frozenset[int] = frozenset(REVISION_RUNGS)


class StaleRevisionError(Exception):
    """Client revision context does not match the persisted current rung."""


class RevisionNotDueError(Exception):
    """Scheduled revision must not advance before ``next_revision``."""


class RevisionRungError(ValueError):
    """rung_days is not on the official ladder."""


@dataclass(frozen=True)
class RevisionModeProgress:
    """Six-method fact for one scheduled rung. Does not overwrite M7 rows."""

    source_locator: str
    rung_days: int
    completed_modes: tuple[str, ...]
    in_progress_modes: tuple[str, ...]
    completed_count: int
    total_modes: int
    next_mode: str | None
    source_outdated: bool

    @property
    def all_methods_complete(self) -> bool:
        return self.completed_count >= self.total_modes


@dataclass(frozen=True)
class ProvisionRevisionState:
    """Lifecycle / schedule fact. No entitlement or roster fields."""

    source_locator: str
    status: str
    learned_at: str | None
    times_completed: int
    current_rung_days: int
    last_completed: str | None
    next_revision: str | None
    is_due: bool
    is_overdue: bool
    is_mastered: bool
    completed_revision_modes: tuple[str, ...]
    next_revision_mode: str | None
    source_outdated: bool
    days_overdue: int


@dataclass(frozen=True)
class DueRevisionFact:
    law_id: str
    source_locator: str
    status: str
    interval_days: int
    next_revision: str
    times_completed: int
    learned_at: str | None


@dataclass(frozen=True)
class ScheduledRevisionFact:
    law_id: str
    source_locator: str
    status: str
    interval_days: int
    next_revision: str


def require_revision_rung(rung_days: int) -> int:
    value = int(rung_days)
    if value not in REVISION_RUNGS_SET:
        raise RevisionRungError(f"unknown revision rung: {rung_days}")
    return value


def parse_iso_date(value: date | str | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    return date.fromisoformat(text[:10])


def days_overdue(next_revision: date | str | None, today: date) -> int:
    nxt = parse_iso_date(next_revision)
    if nxt is None or nxt >= today:
        return 0
    return (today - nxt).days


def overdue_label(days: int) -> str:
    if days <= 0:
        return "Due today"
    if days == 1:
        return "1 day overdue"
    return f"{days} days overdue"


def format_study_date(value: date | str | None) -> str:
    parsed = parse_iso_date(value)
    if parsed is None:
        return ""
    return f"{parsed.day} {parsed.strftime('%b')}"


def revision_is_mastered(status: str) -> bool:
    return str(status or "") == LIFECYCLE_MASTERED


def revision_is_due(
    *,
    status: str,
    next_revision: date | str | None,
    today: date,
) -> bool:
    if revision_is_mastered(status):
        return False
    nxt = parse_iso_date(next_revision)
    return nxt is not None and nxt <= today


def revision_is_overdue(
    *,
    status: str,
    next_revision: date | str | None,
    today: date,
) -> bool:
    if revision_is_mastered(status):
        return False
    nxt = parse_iso_date(next_revision)
    return nxt is not None and nxt < today


def empty_revision_mode_progress(
    source_locator: str, rung_days: int
) -> RevisionModeProgress:
    return RevisionModeProgress(
        source_locator=source_locator,
        rung_days=require_revision_rung(rung_days),
        completed_modes=(),
        in_progress_modes=(),
        completed_count=0,
        total_modes=TOTAL_PLAYGROUND_MODES,
        next_mode=PLAYGROUND_LEARN_MODES[0],
        source_outdated=False,
    )


def build_revision_mode_progress(
    source_locator: str,
    rung_days: int,
    rows: list[ModeProgressRow] | tuple[ModeProgressRow, ...],
    *,
    live_hash: str = "",
) -> RevisionModeProgress:
    require_revision_rung(rung_days)
    completed: list[str] = []
    in_progress: list[str] = []
    outdated = False
    seen: dict[str, ModeProgressRow] = {}
    for row in rows:
        if row.source_locator != source_locator:
            continue
        seen[row.mode] = row
        if live_hash and row.source_hash != live_hash:
            outdated = True
    for mode in PLAYGROUND_LEARN_MODES:
        row = seen.get(mode)
        if row is None:
            continue
        if row.status == MODE_STATUS_COMPLETED:
            completed.append(mode)
        elif row.status == MODE_STATUS_IN_PROGRESS:
            in_progress.append(mode)
    completed_t = tuple(completed)
    return RevisionModeProgress(
        source_locator=source_locator,
        rung_days=rung_days,
        completed_modes=completed_t,
        in_progress_modes=tuple(in_progress),
        completed_count=len(completed_t),
        total_modes=TOTAL_PLAYGROUND_MODES,
        next_mode=next_learn_mode(completed_t),
        source_outdated=outdated,
    )


def build_revision_state(
    progress,
    *,
    today: date,
    revision_modes: RevisionModeProgress | None = None,
    live_hash: str = "",
) -> ProvisionRevisionState | None:
    if progress is None:
        return None
    status = str(getattr(progress, "status", "") or "")
    if status not in LIFECYCLE_ACTIVE and not getattr(progress, "next_revision", None):
        return None
    nxt = getattr(progress, "next_revision", None)
    nxt_s = None if nxt is None else str(nxt)[:10]
    interval = int(getattr(progress, "interval_days", 0) or 0)
    mastered = revision_is_mastered(status)
    overdue_n = 0 if mastered else days_overdue(nxt_s, today)
    outdated = bool(getattr(progress, "source_outdated", False))
    if live_hash and getattr(progress, "source_hash", "") and progress.source_hash != live_hash:
        outdated = True
    if revision_modes is not None:
        completed = revision_modes.completed_modes
        next_mode = revision_modes.next_mode
        outdated = outdated or revision_modes.source_outdated
    else:
        completed = ()
        next_mode = PLAYGROUND_LEARN_MODES[0] if not mastered else None
    learned_at = getattr(progress, "learned_at", None)
    learned_s = None if learned_at is None else str(learned_at)[:10]
    last = getattr(progress, "last_completed", None)
    last_s = None if last is None else str(last)[:10]
    return ProvisionRevisionState(
        source_locator=str(progress.source_locator),
        status=status,
        learned_at=learned_s,
        times_completed=int(getattr(progress, "times_completed", 0) or 0),
        current_rung_days=interval,
        last_completed=last_s,
        next_revision=nxt_s,
        is_due=revision_is_due(status=status, next_revision=nxt_s, today=today),
        is_overdue=revision_is_overdue(status=status, next_revision=nxt_s, today=today),
        is_mastered=mastered,
        completed_revision_modes=completed,
        next_revision_mode=next_mode,
        source_outdated=outdated,
        days_overdue=overdue_n,
    )
