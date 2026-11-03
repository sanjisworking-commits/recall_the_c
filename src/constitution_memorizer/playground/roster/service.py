"""Current-period Playground roster. Routes must not reconstruct capacity."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date, datetime
from typing import Any
from uuid import UUID

from constitution_memorizer.entitlements.tier_model import (
    FREE_CHOICE_LIMIT,
    TIER_MODEL_MONTHLY,
    is_choice_model,
    normalize_tier_model,
)
from constitution_memorizer.playground.eligibility import is_playground_eligible_law
from constitution_memorizer.playground.roster.models import (
    DECISION_DECLINE,
    DECISION_KEEP,
    ORIGIN_NEW,
    ORIGIN_RE_ADD,
    PERIOD_STATUS_ACTIVE,
    PERIOD_STATUS_DRAFT,
    RESULT_ALREADY_ACTIVE,
    RESULT_FREE_CHOICES_EXHAUSTED,
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
    """Account-wide roster. Identity is ``user_id``, not device.

    ``tier_model`` (B1, §4.5): ``monthly`` keeps every behaviour of
    ``3719b9f``. ``choices`` makes the period tables a membership bucket and
    history only — no paid cap is ever computed from them (B1-F16), reads
    never create or rewrite a period (B1-F06/F15), active memberships carry
    across month boundaries automatically at the next save point (5-23) and
    Free capacity is the permanent-choice ledger (B1-F02..F04).
    """

    def __init__(self, repo: Any, *, tier_model: str = TIER_MODEL_MONTHLY) -> None:
        self._repo = repo
        self._tier_model = normalize_tier_model(tier_model)

    @property
    def tier_model(self) -> str:
        return self._tier_model

    @property
    def choices_model(self) -> bool:
        return is_choice_model(self._tier_model)

    def _commercial(self, snapshot: Any | None, *, local_owner: bool) -> tuple[str | None, int | None]:
        return _period_commercial(snapshot, local_owner=local_owner, tier_model=self._tier_model)

    def _ledger_account(self, snapshot: Any | None, *, local_owner: bool) -> bool:
        """Free account under ``choices``: capacity is the permanent ledger."""

        if not self.choices_model or local_owner or snapshot is None:
            return False
        if getattr(snapshot, "admin_override", False):
            return False
        return getattr(snapshot, "playground_choice_limit", None) is not None

    def _choice_limit(self, snapshot: Any | None) -> int:
        limit = getattr(snapshot, "playground_choice_limit", None)
        return int(limit) if limit is not None else FREE_CHOICE_LIMIT

    def _membership_start(self, user_id: UUID | str, now: datetime | None = None) -> date:
        """Period whose items are the current membership. Read-only.

        ``monthly``: this calendar month. ``choices``: this month's period if
        it exists, else the latest *active* period (memberships continue
        across a boundary until the next save point materialises the month).
        """

        start, _end = playground_month_bounds(now)
        if not self.choices_model:
            return start
        current = self._repo.get_period(user_id, start)
        if current is not None and current.status == PERIOD_STATUS_ACTIVE:
            return start
        # No active row for this month (none yet, or a pre-existing draft from
        # the retired Keep/decline flow): the latest active period still holds
        # the membership until the next save point promotes/creates the month.
        latest = self._repo.latest_active_period(user_id)
        if latest is not None and latest.period_start < start:
            return latest.period_start
        return start

    def choice_law_ids(self, user_id: UUID | str) -> frozenset[str]:
        """Permanent Free choices (ledger). Empty under ``monthly``."""

        if not self.choices_model:
            return frozenset()
        return frozenset(self._repo.list_choices(user_id))

    def is_choice_law(self, user_id: UUID | str, law_id: str) -> bool:
        if not self.choices_model:
            return False
        return bool(self._repo.has_choice(user_id, law_id))

    def ensure_current_period(
        self,
        user_id: UUID | str,
        snapshot: Any | None,
        *,
        now: datetime | None = None,
        local_owner: bool = False,
    ) -> PlaygroundPeriod:
        """Save-point only. Under ``choices`` a newly created month carries
        every active item of the latest active period (5-23)."""

        start, end = playground_month_bounds(now)
        tier, limit = self._commercial(snapshot, local_owner=local_owner)
        return self._repo.ensure_period(
            user_id,
            period_start=start,
            period_end=end,
            tier_snapshot=tier,
            law_limit=limit,
            now=now,
            carry_from_latest_active=self.choices_model,
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
        start = self._membership_start(user_id, now)
        return self._repo.list_items(user_id, start)

    def peek_period(
        self,
        user_id: UUID | str,
        period_start: date | None = None,
        *,
        now: datetime | None = None,
    ) -> PlaygroundPeriod | None:
        """Read an existing period. Never creates one."""

        if period_start is None:
            return self.get_current_period(user_id, now=now)
        return self._repo.get_period(user_id, period_start)

    def list_periods(self, user_id: UUID | str) -> list[PlaygroundPeriod]:
        return list(self._repo.list_periods(user_id))

    def list_items_for_period(
        self, user_id: UUID | str, period_start: date
    ) -> list[RosterItem]:
        return self._repo.list_items(user_id, period_start)

    def active_roster_items(
        self,
        user_id: UUID | str,
        *,
        now: datetime | None = None,
    ) -> list[RosterItem]:
        start = self._membership_start(user_id, now)
        period = self._repo.get_period(user_id, start)
        if period is None or period.status != PERIOD_STATUS_ACTIVE:
            return []
        return [item for item in self._repo.list_items(user_id, start) if item.is_active]

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

        start = self._membership_start(user_id, now)
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

    def peek_capacity(
        self,
        user_id: UUID | str,
        snapshot: Any | None,
        *,
        now: datetime | None = None,
        local_owner: bool = False,
    ) -> RosterCapacity:
        """Display capacity. Never inserts, updates, or reconciles a period.

        Missing current period → used 0 and the snapshot/catalogue limit.
        Existing period → stored limit and consumed count, unchanged.
        """

        start, end = playground_month_bounds(now)
        if self.choices_model:
            return self._choice_capacity(
                user_id, snapshot, local_owner=local_owner, now=now
            )
        period = self._repo.get_period(user_id, start)
        if period is None:
            tier, limit = self._commercial(snapshot, local_owner=local_owner)
            used = 0
            return RosterCapacity(
                period_start=start,
                period_end=end,
                law_limit=limit,
                used=used,
                remaining=remaining_capacity(limit, used),
                tier_snapshot=tier,
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

    def _choice_capacity(
        self,
        user_id: UUID | str,
        snapshot: Any | None,
        *,
        local_owner: bool,
        now: datetime | None,
    ) -> RosterCapacity:
        """``choices`` capacity, read-only. The stored period limit is never
        consulted (B1-F16 check 5): paid/admin/local are unlimited; a Free
        account's numbers are its permanent ledger."""

        start, end = playground_month_bounds(now)
        tier, _limit = self._commercial(snapshot, local_owner=local_owner)
        membership_start = self._membership_start(user_id, now)
        period = self._repo.get_period(user_id, membership_start)
        if period is not None:
            start, end = period.period_start, period.period_end
        if self._ledger_account(snapshot, local_owner=local_owner):
            limit = self._choice_limit(snapshot)
            used = int(self._repo.count_choices(user_id))
            return RosterCapacity(
                period_start=start,
                period_end=end,
                law_limit=limit,
                used=used,
                remaining=remaining_capacity(limit, used),
                tier_snapshot=tier,
                permanent=True,
            )
        used = self._repo.count_consumed(user_id, start) if period is not None else 0
        return RosterCapacity(
            period_start=start,
            period_end=end,
            law_limit=None,
            used=used,
            remaining=None,
            tier_snapshot=tier,
        )

    def capacity(
        self,
        user_id: UUID | str,
        snapshot: Any | None,
        *,
        now: datetime | None = None,
        local_owner: bool = False,
    ) -> RosterCapacity:
        """Mutating: ensures and reconciles the current period (save points).

        Read-only surfaces must use :meth:`peek_capacity`. Under ``choices``
        the returned numbers follow :meth:`_choice_capacity` after the period
        is ensured, so the stored row limit never surfaces (B1-F16).
        """

        period = self.ensure_current_period(
            user_id, snapshot, now=now, local_owner=local_owner
        )
        if self.choices_model:
            return self._choice_capacity(
                user_id, snapshot, local_owner=local_owner, now=now
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

    def capacity_for_request(
        self,
        user_id: UUID | str,
        snapshot: Any | None,
        *,
        now: datetime | None = None,
        local_owner: bool = False,
    ) -> RosterCapacity:
        """Capacity attached by the HTTP gate on every Playground request.

        ``monthly``: the mutating :meth:`capacity` exactly as at 3719b9f.
        ``choices``: read-only (B1-F06/F15) — a GET never creates or rewrites
        a period; the month is materialised at the next save point.
        """

        if self.choices_model:
            return self.peek_capacity(
                user_id, snapshot, now=now, local_owner=local_owner
            )
        return self.capacity(user_id, snapshot, now=now, local_owner=local_owner)

    def preview_add_law(
        self,
        user_id: UUID | str,
        law_id: str,
        snapshot: Any | None,
        *,
        now: datetime | None = None,
        local_owner: bool = False,
        can_consume_new_law: bool = True,
        mutate: bool = True,
    ) -> AddPreview:
        """Add decision for one law.

        ``monthly``: ensures the period as at 3719b9f. ``choices``: with
        ``mutate=False`` (every GET and the scope-step render) nothing is
        written; the decision is computed from the latest membership period,
        the snapshot and the ledger (B1-F06/F15).
        """

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
        if self.choices_model:
            return self._preview_add_law_choices(
                user_id,
                law_id,
                snapshot,
                now=now,
                local_owner=local_owner,
                can_consume_new_law=can_consume_new_law,
                mutate=mutate,
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

    def _preview_add_law_choices(
        self,
        user_id: UUID | str,
        law_id: str,
        snapshot: Any | None,
        *,
        now: datetime | None,
        local_owner: bool,
        can_consume_new_law: bool,
        mutate: bool,
    ) -> AddPreview:
        if mutate:
            period = self.ensure_current_period(
                user_id, snapshot, now=now, local_owner=local_owner
            )
        else:
            period = self._repo.get_period(user_id, self._membership_start(user_id, now))
        item = (
            self._repo.get_item(user_id, period.period_start, law_id)
            if period is not None
            else None
        )
        cap = self._choice_capacity(user_id, snapshot, local_owner=local_owner, now=now)
        ledger = self._ledger_account(snapshot, local_owner=local_owner)
        in_ledger = bool(ledger and self._repo.has_choice(user_id, law_id))
        used, remaining, limit = cap.used, cap.remaining, cap.law_limit

        def _preview(status: str, copy: str = "") -> AddPreview:
            return AddPreview(
                status=status,
                law_id=law_id,
                used=used,
                remaining=remaining,
                law_limit=limit,
                period=period,
                item=item,
                confirmation_copy=copy,
                choices_used=used if ledger else None,
                choice_limit=limit if ledger else None,
                in_ledger=in_ledger,
            )

        if item is not None and item.is_active:
            return _preview(RESULT_ALREADY_ACTIVE)
        if (item is not None and item.is_consumed and item.removed_at is not None) or in_ledger:
            # Eligibility is permanent; re-add restores membership at no cost.
            return _preview(RESULT_RE_ADD_CONFIRM, _readd_copy_choices(ledger))
        consume_block = getattr(snapshot, "playground_consume_block_reason", None)
        if ledger and (consume_block == RESULT_FREE_CHOICES_EXHAUSTED or remaining == 0):
            return _preview(RESULT_FREE_CHOICES_EXHAUSTED)
        if not can_consume_new_law:
            return _preview(RESULT_NEW_BLOCKED)
        if ledger:
            return _preview(
                RESULT_NEEDS_CONFIRM,
                free_choice_confirmation_copy(
                    limit=int(limit or 0), remaining_after=max(0, int(remaining or 0) - 1)
                ),
            )
        return _preview(RESULT_NEEDS_CONFIRM, add_confirmation_copy_choices())

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
        """Save point. Under ``choices``: the effective limit (never the stored
        row) is enforced, and a Free account's add is ledger-aware — one
        ledger row per new distinct law, appended in the same transaction as
        the roster item; a ledger law re-adds at no cost (B1-F03/F05/F18)."""

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
        if not self.choices_model:
            return self._repo.consume_law(
                user_id,
                period_start=period.period_start,
                law_id=law_id,
                law_limit=period.law_limit,
                allow_new=can_consume_new_law,
                origin_for_new=origin,
                now=now,
            )
        _tier, effective_limit = self._commercial(snapshot, local_owner=local_owner)
        ledger = self._ledger_account(snapshot, local_owner=local_owner)
        return self._repo.consume_law(
            user_id,
            period_start=period.period_start,
            law_id=law_id,
            law_limit=effective_limit,
            allow_new=can_consume_new_law,
            origin_for_new=origin,
            now=now,
            enforce_effective_limit=True,
            ledger=ledger,
            choice_limit=self._choice_limit(snapshot) if ledger else None,
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
        start = self._membership_start(user_id, now)
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


def _readd_copy_choices(ledger: bool) -> str:
    if ledger:
        return "Add this law back to your Playground? It is one of your chosen laws; no choice is used."
    return "Add this law back to your Playground?"


def add_confirmation_copy_choices() -> str:
    return "Add this law to your Playground?"


def free_choice_confirmation_copy(*, limit: int, remaining_after: int) -> str:
    noun = "choice" if remaining_after == 1 else "choices"
    return (
        f"This will use 1 of your {limit} permanent Playground law choices. "
        f"You'll have {remaining_after} {noun} remaining. Choices do not reset."
    )


def _period_commercial(
    snapshot: Any | None,
    *,
    local_owner: bool,
    tier_model: str = TIER_MODEL_MONTHLY,
) -> tuple[str | None, int | None]:
    """``(tier_snapshot, law_limit)`` written on a period row.

    ``monthly``: the snapshot's tier and limit as at 3719b9f (an unsubscribed
    or admin account yields ``(None, None)``). ``choices``: no cap is ever
    written — paid tiers are unlimited and a Free account's cap is the
    ledger, not the period — and a Free account is labelled ``"free"`` so the
    row's provenance is explicit (§4.10).
    """

    if local_owner:
        return None, None
    if snapshot is None:
        return None, None
    if getattr(snapshot, "admin_override", False):
        return None, None
    tier = getattr(snapshot, "tier", None)
    if is_choice_model(tier_model):
        if getattr(snapshot, "playground_choice_limit", None) is not None and not getattr(
            snapshot, "is_subscribed", False
        ):
            return "free", None
        return (str(tier) if tier else None), None
    limit = getattr(snapshot, "playground_law_limit", None)
    return (str(tier) if tier else None), limit
