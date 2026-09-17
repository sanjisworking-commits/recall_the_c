"""Current-period Playground roster. Routes must not reconstruct capacity."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from constitution_memorizer.playground.eligibility import is_playground_eligible_law
from constitution_memorizer.playground.roster.models import (
    RESULT_ALREADY_ACTIVE,
    RESULT_INELIGIBLE,
    RESULT_NEEDS_CONFIRM,
    RESULT_NEW_BLOCKED,
    RESULT_RE_ADD_CONFIRM,
    RESULT_ROSTER_FULL,
    AddPreview,
    ConsumeResult,
    PlaygroundPeriod,
    RosterCapacity,
    RosterItem,
    remaining_capacity,
)
from constitution_memorizer.playground.roster.period import (
    playground_month_bounds,
    playground_month_name,
)


class RosterService:
    """Account-wide monthly roster. Identity is ``user_id``, not device."""

    def __init__(self, repo: Any) -> None:
        self._repo = repo

    def ensure_current_period(
        self,
        user_id: UUID | str,
        snapshot: Any | None,
        *,
        now: datetime | None = None,
        local_owner: bool = False,
    ) -> PlaygroundPeriod:
        start, end = playground_month_bounds(now)
        tier, limit = _period_commercial(snapshot, local_owner=local_owner)
        return self._repo.ensure_period(
            user_id,
            period_start=start,
            period_end=end,
            tier_snapshot=tier,
            law_limit=limit,
            now=now,
        )

    def get_current_period(
        self,
        user_id: UUID | str,
        *,
        now: datetime | None = None,
    ) -> PlaygroundPeriod | None:
        start, _end = playground_month_bounds(now)
        return self._repo.get_period(user_id, start)

    def get_current_roster(
        self,
        user_id: UUID | str,
        *,
        now: datetime | None = None,
    ) -> list[RosterItem]:
        start, _end = playground_month_bounds(now)
        return self._repo.list_items(user_id, start)

    def active_roster_items(
        self,
        user_id: UUID | str,
        *,
        now: datetime | None = None,
    ) -> list[RosterItem]:
        return [item for item in self.get_current_roster(user_id, now=now) if item.is_active]

    def removed_roster_items(
        self,
        user_id: UUID | str,
        *,
        now: datetime | None = None,
    ) -> list[RosterItem]:
        return [
            item
            for item in self.get_current_roster(user_id, now=now)
            if item.is_consumed and item.removed_at is not None
        ]

    def is_law_active_this_period(
        self,
        user_id: UUID | str,
        law_id: str,
        *,
        now: datetime | None = None,
    ) -> bool:
        item = self._current_item(user_id, law_id, now=now)
        return bool(item is not None and item.is_active)

    def already_consumed_this_period(
        self,
        user_id: UUID | str,
        law_id: str,
        *,
        now: datetime | None = None,
    ) -> bool:
        item = self._current_item(user_id, law_id, now=now)
        return bool(item is not None and item.is_consumed)

    def capacity(
        self,
        user_id: UUID | str,
        snapshot: Any | None,
        *,
        now: datetime | None = None,
        local_owner: bool = False,
    ) -> RosterCapacity:
        period = self.ensure_current_period(
            user_id, snapshot, now=now, local_owner=local_owner
        )
        used = self._repo.count_consumed(user_id, period.period_start)
        return RosterCapacity(
            period_start=period.period_start,
            period_end=period.period_end,
            law_limit=period.law_limit,
            used=used,
            remaining=remaining_capacity(period.law_limit, used),
            tier_snapshot=period.tier_snapshot,
        )

    def preview_add_law(
        self,
        user_id: UUID | str,
        law_id: str,
        snapshot: Any | None,
        *,
        now: datetime | None = None,
        local_owner: bool = False,
        can_consume_new_law: bool = True,
    ) -> AddPreview:
        if not is_playground_eligible_law(law_id):
            return AddPreview(
                status=RESULT_INELIGIBLE,
                law_id=law_id,
                used=0,
                remaining=None,
                law_limit=None,
                period=None,
                item=None,
            )
        period = self.ensure_current_period(
            user_id, snapshot, now=now, local_owner=local_owner
        )
        item = self._repo.get_item(user_id, period.period_start, law_id)
        used = self._repo.count_consumed(user_id, period.period_start)
        remaining = remaining_capacity(period.law_limit, used)
        month = playground_month_name(period.period_start)
        if item is not None and item.is_active:
            return AddPreview(
                status=RESULT_ALREADY_ACTIVE,
                law_id=law_id,
                used=used,
                remaining=remaining,
                law_limit=period.law_limit,
                period=period,
                item=item,
            )
        if item is not None and item.is_consumed and item.removed_at is not None:
            return AddPreview(
                status=RESULT_RE_ADD_CONFIRM,
                law_id=law_id,
                used=used,
                remaining=remaining,
                law_limit=period.law_limit,
                period=period,
                item=item,
                confirmation_copy=_readd_copy(month),
            )
        if not can_consume_new_law:
            return AddPreview(
                status=RESULT_NEW_BLOCKED,
                law_id=law_id,
                used=used,
                remaining=remaining,
                law_limit=period.law_limit,
                period=period,
                item=item,
            )
        if remaining == 0:
            return AddPreview(
                status=RESULT_ROSTER_FULL,
                law_id=law_id,
                used=used,
                remaining=0,
                law_limit=period.law_limit,
                period=period,
                item=item,
            )
        return AddPreview(
            status=RESULT_NEEDS_CONFIRM,
            law_id=law_id,
            used=used,
            remaining=remaining,
            law_limit=period.law_limit,
            period=period,
            item=item,
            confirmation_copy=add_confirmation_copy(
                month_name=month, law_limit=period.law_limit
            ),
        )

    def confirm_add_law(
        self,
        user_id: UUID | str,
        law_id: str,
        snapshot: Any | None,
        *,
        now: datetime | None = None,
        local_owner: bool = False,
        can_consume_new_law: bool = True,
    ) -> ConsumeResult:
        if not is_playground_eligible_law(law_id):
            return ConsumeResult(
                status=RESULT_INELIGIBLE,
                item=None,
                used=0,
                remaining=None,
            )
        period = self.ensure_current_period(
            user_id, snapshot, now=now, local_owner=local_owner
        )
        return self._repo.consume_law(
            user_id,
            period_start=period.period_start,
            law_id=law_id,
            law_limit=period.law_limit,
            allow_new=can_consume_new_law,
            now=now,
        )

    def remove_law_this_period(
        self,
        user_id: UUID | str,
        law_id: str,
        snapshot: Any | None,
        *,
        now: datetime | None = None,
        local_owner: bool = False,
    ) -> RosterItem | None:
        period = self.ensure_current_period(
            user_id, snapshot, now=now, local_owner=local_owner
        )
        return self._repo.remove_law(
            user_id,
            period_start=period.period_start,
            law_id=law_id,
            now=now,
        )

    def readd_law_this_period(
        self,
        user_id: UUID | str,
        law_id: str,
        snapshot: Any | None,
        *,
        now: datetime | None = None,
        local_owner: bool = False,
        can_consume_new_law: bool = True,
    ) -> ConsumeResult:
        return self.confirm_add_law(
            user_id,
            law_id,
            snapshot,
            now=now,
            local_owner=local_owner,
            can_consume_new_law=can_consume_new_law,
        )

    def _current_item(
        self,
        user_id: UUID | str,
        law_id: str,
        *,
        now: datetime | None = None,
    ) -> RosterItem | None:
        start, _end = playground_month_bounds(now)
        return self._repo.get_item(user_id, start, law_id)


def add_confirmation_copy(*, month_name: str, law_limit: int | None) -> str:
    if law_limit is None:
        return f"Add this law to your {month_name} Playground?"
    return f"This will use 1 of your {law_limit} law spaces for {month_name}."


def roster_full_body(*, month_name: str, law_limit: int) -> str:
    return (
        f"You've used all {law_limit} law spaces for {month_name}. "
        "Your current Playground laws remain available."
    )


def _readd_copy(month_name: str) -> str:
    return f"Add this law to your {month_name} Playground?"


def _period_commercial(
    snapshot: Any | None, *, local_owner: bool
) -> tuple[str | None, int | None]:
    if local_owner:
        return None, None
    if snapshot is None:
        return None, None
    if getattr(snapshot, "admin_override", False):
        return None, None
    tier = getattr(snapshot, "tier", None)
    limit = getattr(snapshot, "playground_law_limit", None)
    return (str(tier) if tier else None), limit
