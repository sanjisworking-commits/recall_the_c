"""Eligible unseen units for a day's learning mix.

Filters live here so ``LearningMixSelector`` can stay a pure function over an
already-built candidate list. Entitlement rules are parent-Article scoped and
do not need a FastAPI Request.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from datetime import date

from constitution_memorizer.learning.schemas import LearningUnit, LearningUnitType
from constitution_memorizer.planner.models import MixCandidate
from constitution_memorizer.planner.relationships import candidates_from_units
from constitution_memorizer.progress.scheduler import ReminderEngine


def _unit_visible_for_preference(engine: ReminderEngine, unit: LearningUnit) -> bool:
    """Same rule as web.service.unit_visible_for_preference, kept Request-free."""
    if unit.type == LearningUnitType.SUBCLAUSE and unit.parent_clause_id:
        mode = engine.get_split_preference(unit.parent_clause_id) or "whole"
        return mode == "letters"
    if unit.allows_letter_split:
        mode = engine.get_split_preference(unit.id) or "whole"
        if mode == "letters":
            return False
    return True

AllowFn = Callable[[MixCandidate, Sequence[MixCandidate]], bool]


def is_unlearned(engine: ReminderEngine, unit_id: str) -> bool:
    row = engine.get_progress(unit_id)
    if row is None:
        return True
    if row.times_completed > 0:
        return False
    return row.status == "new"


def active_queued_unit_ids(
    engine: ReminderEngine,
    *,
    as_of: date,
) -> set[str]:
    blocked: set[str] = set()
    for kind in ("revision", "auto_learning", "day_plan"):
        session = engine.active_study_session(kind=kind, plan_date=as_of)
        if session is None:
            continue
        for item in session.items:
            if item.status == "pending":
                blocked.add(item.learning_unit_id)
    return blocked


def article_slot_policy(
    *,
    claimed: set[str],
    remaining_slots: int,
    entitlements_on: bool,
) -> AllowFn:
    """Limit DISTINCT newly introduced Articles to remaining Free claim slots.

    When entitlements are off, everything already in the candidate set is allowed.
    Claimed Articles never consume a slot. An unclaimed Article already present
    in the mix can still add sibling units.
    """

    claimed_keys = {str(item) for item in claimed}

    def allow(candidate: MixCandidate, selected: Sequence[MixCandidate]) -> bool:
        if not entitlements_on:
            return True
        article = candidate.article_number
        if not article:
            return True
        if article in claimed_keys:
            return True
        introduced = {
            item.article_number
            for item in selected
            if item.article_number and item.article_number not in claimed_keys
        }
        if article in introduced:
            return True
        return len(introduced) < remaining_slots

    return allow


def eligible_units(
    engine: ReminderEngine,
    *,
    as_of: date,
    claimed: set[str] | None = None,
    remaining_slots: int | None = None,
    entitlements_on: bool = False,
) -> list[LearningUnit]:
    """Unseen, visible, entitlement-aware units that can join a new-learning mix."""
    queued = active_queued_unit_ids(engine, as_of=as_of)
    claimed_keys = {str(item) for item in (claimed or set())}
    slots = 0 if remaining_slots is None else max(0, remaining_slots)
    units: list[LearningUnit] = []
    for unit in engine.units.values():
        if unit.type == LearningUnitType.PART_OVERVIEW:
            continue
        if unit.id in queued:
            continue
        if not is_unlearned(engine, unit.id):
            continue
        if not _unit_visible_for_preference(engine, unit):
            continue
        if entitlements_on:
            article = unit.article_number
            if article and article not in claimed_keys and slots <= 0:
                continue
        units.append(unit)
    units.sort(key=lambda item: (item.revision_order, item.id))
    return units


def eligible_candidates(
    engine: ReminderEngine,
    *,
    as_of: date,
    claimed: set[str] | None = None,
    remaining_slots: int | None = None,
    entitlements_on: bool = False,
) -> list[MixCandidate]:
    return candidates_from_units(
        eligible_units(
            engine,
            as_of=as_of,
            claimed=claimed,
            remaining_slots=remaining_slots,
            entitlements_on=entitlements_on,
        )
    )


def remaining_unseen_count(
    engine: ReminderEngine,
    *,
    as_of: date,
    claimed: set[str] | None = None,
    remaining_slots: int | None = None,
    entitlements_on: bool = False,
) -> int:
    return len(
        eligible_units(
            engine,
            as_of=as_of,
            claimed=claimed,
            remaining_slots=remaining_slots,
            entitlements_on=entitlements_on,
        )
    )
