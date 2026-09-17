"""Roster types. Overlay rows are not membership."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

PLAYGROUND_TIMEZONE_NAME = "Asia/Kolkata"

PERIOD_STATUS_DRAFT = "draft"
PERIOD_STATUS_ACTIVE = "active"
PERIOD_STATUS_CLOSED = "closed"
PERIOD_STATUSES: frozenset[str] = frozenset(
    {PERIOD_STATUS_DRAFT, PERIOD_STATUS_ACTIVE, PERIOD_STATUS_CLOSED}
)

ORIGIN_NEW = "new"
ORIGIN_RE_ADD = "re_add"
ORIGIN_CARRY_FORWARD = "carry_forward"
ROSTER_ORIGINS: frozenset[str] = frozenset(
    {ORIGIN_NEW, ORIGIN_RE_ADD, ORIGIN_CARRY_FORWARD}
)

RESULT_OK = "ok"
RESULT_ALREADY_ACTIVE = "already_active"
RESULT_RE_ADDED = "re_added"
RESULT_ROSTER_FULL = "roster_full"
RESULT_NEW_BLOCKED = "new_law_temporarily_unavailable"
RESULT_INELIGIBLE = "ineligible"
RESULT_NEEDS_CONFIRM = "needs_confirm"
RESULT_RE_ADD_CONFIRM = "re_add"

ROSTER_ADD_CONFIRM = "add"

BLOCK_ROSTER_FULL = "roster_full"
BLOCK_PROGRESS_SAVED = "progress_saved"


def remaining_capacity(law_limit: int | None, used: int) -> int | None:
    """Finite remaining slots, or None when the period is unlimited."""

    if law_limit is None:
        return None
    return max(0, int(law_limit) - int(used))


def is_roster_item_active(item: RosterItem | None) -> bool:
    if item is None:
        return False
    return item.consumed_at is not None and item.removed_at is None


def is_roster_item_consumed(item: RosterItem | None) -> bool:
    return item is not None and item.consumed_at is not None


@dataclass(frozen=True)
class PlaygroundPeriod:
    """One Asia/Kolkata calendar month for one account. ``period_end`` is exclusive."""

    id: str
    user_id: str
    period_start: date
    period_end: date
    tier_snapshot: str | None
    law_limit: int | None
    status: str
    confirmed_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class RosterItem:
    """Current-period law membership. Unique per user + period + law, not lifetime."""

    id: str
    user_id: str
    period_start: date
    law_id: str
    origin: str
    carried_from_previous_period: bool
    consumed_at: datetime | None
    removed_at: datetime | None
    declined_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @property
    def is_active(self) -> bool:
        return self.consumed_at is not None and self.removed_at is None

    @property
    def is_consumed(self) -> bool:
        return self.consumed_at is not None


@dataclass(frozen=True)
class ConsumeResult:
    """Atomic consume / re-add outcome. ``remaining`` is None when unlimited."""

    status: str
    item: RosterItem | None
    used: int
    remaining: int | None
    period: PlaygroundPeriod | None = None

    @property
    def ok(self) -> bool:
        return self.status in {RESULT_OK, RESULT_ALREADY_ACTIVE, RESULT_RE_ADDED}


@dataclass(frozen=True)
class AddPreview:
    """Read-side add decision. Does not consume a slot."""

    status: str
    law_id: str
    used: int
    remaining: int | None
    law_limit: int | None
    period: PlaygroundPeriod | None
    item: RosterItem | None
    confirmation_copy: str = ""


@dataclass(frozen=True)
class RosterCapacity:
    period_start: date
    period_end: date
    law_limit: int | None
    used: int
    remaining: int | None
    tier_snapshot: str | None
