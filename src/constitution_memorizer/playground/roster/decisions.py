"""Pure Keep/decline planner. Repositories apply the result inside one transaction."""

from __future__ import annotations

from dataclasses import dataclass

from constitution_memorizer.playground.roster.models import (
    PERIOD_STATUS_DRAFT,
    RESULT_INVALID_CANDIDATE,
    RESULT_NEW_BLOCKED,
    RESULT_OK,
    RESULT_ROSTER_FULL,
    RESULT_SLOT_LOCKED,
    RosterItem,
    remaining_capacity,
)


@dataclass(frozen=True)
class RolloverWrite:
    """One target-period decision. ``keep`` reserves or consumes; decline does not."""

    law_id: str
    keep: bool


@dataclass(frozen=True)
class RolloverBatchPlan:
    status: str
    writes: tuple[RolloverWrite, ...]
    used: int
    remaining: int | None

    @property
    def ok(self) -> bool:
        return self.status == RESULT_OK


def _consumes_slot(item: RosterItem | None) -> bool:
    return item is not None and item.consumed_at is not None


def plan_rollover_batch(
    *,
    period_status: str,
    law_limit: int | None,
    items: dict[str, RosterItem],
    used: int,
    keep_ids: list[str],
    decline_ids: list[str],
    allowed_ids: set[str],
    allow_new_keep: bool,
) -> RolloverBatchPlan:
    """Plan one batch. Over-cap and pending Keep reject the whole batch.

    An empty submission is a no-op even when an existing draft is over the
    current limit. That over-cap state is an adjustment, not a partial write.
    Draft Keep→decline releases a reservation. An active consumed row cannot
    be declined here: that would refund a live slot.
    """

    current = remaining_capacity(law_limit, used)
    if not keep_ids and not decline_ids:
        return RolloverBatchPlan(RESULT_OK, (), used, current)
    if len(keep_ids) != len(set(keep_ids)) or len(decline_ids) != len(set(decline_ids)):
        return RolloverBatchPlan(RESULT_INVALID_CANDIDATE, (), used, current)
    if set(keep_ids) & set(decline_ids):
        return RolloverBatchPlan(RESULT_INVALID_CANDIDATE, (), used, current)
    if any(law_id not in allowed_ids for law_id in (*keep_ids, *decline_ids)):
        return RolloverBatchPlan(RESULT_INVALID_CANDIDATE, (), used, current)

    writes: list[RolloverWrite] = []
    releases = 0
    adds = 0
    draft = period_status == PERIOD_STATUS_DRAFT
    for law_id in decline_ids:
        item = items.get(law_id)
        if _consumes_slot(item):
            if not draft:
                return RolloverBatchPlan(RESULT_SLOT_LOCKED, (), used, current)
            releases += 1
            writes.append(RolloverWrite(law_id, keep=False))
            continue
        if item is not None and item.declined_at is not None:
            continue
        writes.append(RolloverWrite(law_id, keep=False))
    for law_id in keep_ids:
        item = items.get(law_id)
        if _consumes_slot(item):
            if item is not None and item.removed_at is not None:
                writes.append(RolloverWrite(law_id, keep=True))
            continue
        if not allow_new_keep:
            return RolloverBatchPlan(RESULT_NEW_BLOCKED, (), used, current)
        adds += 1
        writes.append(RolloverWrite(law_id, keep=True))
    resulting = used - releases + adds
    if law_limit is not None and resulting > law_limit:
        return RolloverBatchPlan(
            RESULT_ROSTER_FULL, (), used, remaining_capacity(law_limit, used)
        )
    return RolloverBatchPlan(
        RESULT_OK,
        tuple(writes),
        resulting,
        remaining_capacity(law_limit, resulting),
    )
