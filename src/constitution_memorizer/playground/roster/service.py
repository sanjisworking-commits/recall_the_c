"""Current-period Playground roster. Routes must not reconstruct capacity."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from constitution_memorizer.playground.eligibility import is_playground_eligible_law
from constitution_memorizer.playground.roster.models import (
    DECISION_DECLINE,
    DECISION_KEEP,
    ORIGIN_NEW,
    ORIGIN_RE_ADD,
    PERIOD_STATUS_ACTIVE,
    PERIOD_STATUS_DRAFT,
    RESULT_ALREADY_ACTIVE,
    RESULT_INELIGIBLE,
    RESULT_NEEDS_CONFIRM,
    RESULT_NEW_BLOCKED,
    RESULT_RE_ADD_CONFIRM,
    RESULT_ROSTER_FULL,
    AddPreview,
    CarryForwardCandidate,
    ConsumeResult,
    PlaygroundPeriod,
    RolloverPlan,
    RolloverResult,
    RosterCapacity,
    RosterItem,
    remaining_capacity,
)
from constitution_memorizer.playground.roster.period import (
    next_playground_month_bounds,
    playground_month_bounds,
    playground_month_name,
    shift_playground_month,
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
        start, _end = playground_month_bounds(now)
        period = self._repo.get_period(user_id, start)
        if period is None or period.status != PERIOD_STATUS_ACTIVE:
            return []
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
        """Active roster membership. A draft period does not authorize learning."""

        start, _end = playground_month_bounds(now)
        period = self._repo.get_period(user_id, start)
        if period is None or period.status != PERIOD_STATUS_ACTIVE:
            return False
        item = self._repo.get_item(user_id, start, law_id)
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
        has_historical_overlay: bool = False,
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
        origin = ORIGIN_RE_ADD if has_historical_overlay else ORIGIN_NEW
        return self._repo.consume_law(
            user_id,
            period_start=period.period_start,
            law_id=law_id,
            law_limit=period.law_limit,
            allow_new=can_consume_new_law,
            origin_for_new=origin,
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

    def list_carry_forward_candidates(
        self,
        user_id: UUID | str,
        *,
        source_start,
        target_start,
        has_overlay: Callable[[str], bool],
    ) -> list[CarryForwardCandidate]:
        """Consumed laws from one source period that still have overlay history.

        ``removed_at`` on the source period does not drop the candidate.
        A non-adjacent older period is not consulted.
        """

        source_items = [
            item
            for item in self._repo.list_items(user_id, source_start)
            if item.consumed_at is not None
        ]
        target = {
            item.law_id: item for item in self._repo.list_items(user_id, target_start)
        }
        candidates: list[CarryForwardCandidate] = []
        for item in source_items:
            if not is_playground_eligible_law(item.law_id):
                continue
            if not has_overlay(item.law_id):
                continue
            decision = target.get(item.law_id)
            target_decision, consumed, declined = _target_decision(decision)
            candidates.append(
                CarryForwardCandidate(
                    law_id=item.law_id,
                    previously_removed=item.removed_at is not None,
                    target_decision=target_decision,
                    target_consumed=consumed,
                    target_declined=declined,
                )
            )
        return candidates

    def get_rollover_plan(
        self,
        user_id: UUID | str,
        snapshot: Any | None,
        *,
        has_overlay: Callable[[str], bool],
        now: datetime | None = None,
        local_owner: bool = False,
    ) -> RolloverPlan:
        """Read the rollover target. Does not insert a period or a decision."""

        current_start, current_end = playground_month_bounds(now)
        previous_start = shift_playground_month(current_start, -1)
        current_candidates = self.list_carry_forward_candidates(
            user_id,
            source_start=previous_start,
            target_start=current_start,
            has_overlay=has_overlay,
        )
        unresolved = [row for row in current_candidates if row.target_decision is None]
        current_period = self._repo.get_period(user_id, current_start)
        _tier, limit_now = _period_commercial(snapshot, local_owner=local_owner)
        used_now = (
            self._repo.count_consumed(user_id, current_start)
            if current_period is not None
            else 0
        )
        # An over-cap draft still owns this month until the user drops Keeps.
        # An already-active period that is over a lowered limit stays on M5-A rules.
        current_needs_adjustment = (
            current_period is not None
            and current_period.status == PERIOD_STATUS_DRAFT
            and limit_now is not None
            and used_now > limit_now
        )
        if unresolved or current_needs_adjustment:
            source_start, source_end = previous_start, current_start
            target_start, target_end = current_start, current_end
            candidates = tuple(current_candidates)
            manages_current = True
        else:
            target_start, target_end = next_playground_month_bounds(now)
            source_start, source_end = current_start, current_end
            candidates = tuple(
                self.list_carry_forward_candidates(
                    user_id,
                    source_start=source_start,
                    target_start=target_start,
                    has_overlay=has_overlay,
                )
            )
            manages_current = False
        period = self._repo.get_period(user_id, target_start)
        tier, limit = _period_commercial(snapshot, local_owner=local_owner)
        used = self._repo.count_consumed(user_id, target_start) if period is not None else 0
        return RolloverPlan(
            source_period_start=source_start,
            source_period_end=source_end,
            target_period_start=target_start,
            target_period_end=target_end,
            target_status=period.status if period is not None else None,
            month_name=playground_month_name(target_start),
            tier_snapshot=tier,
            law_limit=limit,
            used=used,
            remaining=remaining_capacity(limit, used),
            candidates=candidates,
            adjustment_required=limit is not None and used > limit,
            manages_current_period=manages_current,
        )

    def confirm_carry_forward(
        self,
        user_id: UUID | str,
        keep_ids: Sequence[str],
        decline_ids: Sequence[str],
        snapshot: Any | None,
        *,
        has_overlay: Callable[[str], bool],
        now: datetime | None = None,
        local_owner: bool = False,
        can_consume_new_law: bool = True,
    ) -> RolloverResult:
        """Apply one Keep/decline batch. Does not touch overlay rows."""

        plan = self.get_rollover_plan(
            user_id,
            snapshot,
            has_overlay=has_overlay,
            now=now,
            local_owner=local_owner,
        )
        tier, limit = _period_commercial(snapshot, local_owner=local_owner)
        allow_new = can_consume_new_law
        if snapshot is not None and not local_owner:
            allow_new = allow_new and bool(
                getattr(snapshot, "can_consume_new_playground_law", True)
            )
        return self._repo.apply_rollover(
            user_id,
            period_start=plan.target_period_start,
            period_end=plan.target_period_end,
            tier_snapshot=tier,
            law_limit=limit,
            activate=plan.manages_current_period,
            keep_ids=list(keep_ids),
            decline_ids=list(decline_ids),
            allowed_ids=frozenset(candidate.law_id for candidate in plan.candidates),
            allow_new_keep=allow_new,
            now=now,
        )

    def activate_due_draft(
        self,
        user_id: UUID | str,
        snapshot: Any | None,
        *,
        now: datetime | None = None,
        local_owner: bool = False,
    ) -> PlaygroundPeriod:
        """Promote a within-cap draft when its month is current. Holds an over-cap draft."""

        return self.ensure_current_period(
            user_id, snapshot, now=now, local_owner=local_owner
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


def _target_decision(
    item: RosterItem | None,
) -> tuple[str | None, bool, bool]:
    if item is None:
        return None, False, False
    if item.consumed_at is not None:
        return DECISION_KEEP, True, False
    if item.declined_at is not None:
        return DECISION_DECLINE, False, True
    return None, False, False


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
