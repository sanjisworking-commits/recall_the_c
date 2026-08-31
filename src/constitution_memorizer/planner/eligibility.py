"""Eligible unseen units for a day's learning mix.

Filters live here so ``LearningMixSelector`` can stay a pure function over an
already-built candidate list. Entitlement rules are parent-Article scoped and
do not need a FastAPI Request.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import date

from constitution_memorizer.learning.schemas import LearningUnit, LearningUnitType
from constitution_memorizer.planner.models import MixCandidate
from constitution_memorizer.planner.relationships import candidates_from_units
from constitution_memorizer.progress.repository import ProgressRecord, SplitMode
from constitution_memorizer.progress.scheduler import ReminderEngine

_PATH_TYPES = {
    LearningUnitType.ARTICLE,
    LearningUnitType.CLAUSE,
    LearningUnitType.SCHEDULE_ENTRY,
}


def genuinely_completed(
    progress: Mapping[str, ProgressRecord], unit_id: str
) -> bool:
    """True when persisted progress proves a real Done, not a planned slot."""
    row = progress.get(unit_id)
    if row is None:
        return False
    return row.times_completed > 0 or row.status in {"review", "mastered"}


def visible_learning_path(
    article_number: str,
    units: Mapping[str, LearningUnit],
    splits: Mapping[str, SplitMode],
) -> list[str]:
    """Ordered learnable siblings for one Article under the current split path.

    Clause order is ``revision_order`` (Bare Act walk), not label-string sort.
    Letter children follow ``child_unit_ids``. A multi-clause Article root is
    omitted so it cannot become a prerequisite for clause (1).
    """
    article_key = (article_number or "").strip().lower()
    if not article_key:
        return []
    members = [
        unit
        for unit in units.values()
        if unit.type in _PATH_TYPES
        and (unit.article_number or "").strip().lower() == article_key
    ]
    if any(unit.type == LearningUnitType.CLAUSE for unit in members):
        members = [
            unit for unit in members if unit.type != LearningUnitType.ARTICLE
        ]
    members.sort(key=lambda unit: (unit.revision_order, unit.id))
    path: list[str] = []
    for unit in members:
        if unit.allows_letter_split and splits.get(unit.id) == "letters":
            for child_id in unit.child_unit_ids:
                if child_id in units:
                    path.append(child_id)
        else:
            path.append(unit.id)
    return path


def sequential_prerequisites_satisfied(
    unit: LearningUnit,
    *,
    units: Mapping[str, LearningUnit],
    progress: Mapping[str, ProgressRecord],
    splits: Mapping[str, SplitMode],
) -> bool:
    """Automatic NEW scheduling preserves sibling order: a later sibling is
    unlocked only after every earlier sibling in the active learning path has
    genuine persisted completion. Planned/pending/deferred siblings do not
    count.
    """
    article = unit.article_number
    if not article:
        return True
    path = visible_learning_path(article, units, splits)
    if unit.id not in path:
        return True
    for pred_id in path:
        if pred_id == unit.id:
            return True
        if not genuinely_completed(progress, pred_id):
            return False
    return True


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


def _unit_eligible_for_mix(engine: ReminderEngine, unit: LearningUnit) -> bool:
    """Mixes wait for a whole/letters choice before queuing a split-capable unit."""
    if not _unit_visible_for_preference(engine, unit):
        return False
    if unit.allows_letter_split and engine.get_split_preference(unit.id) is None:
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
    exclude_ids: set[str] | None = None,
) -> list[LearningUnit]:
    """Unseen, visible, entitlement-aware units that can join a new-learning mix."""
    queued = active_queued_unit_ids(engine, as_of=as_of)
    if exclude_ids:
        queued = queued | set(exclude_ids)
    claimed_keys = {str(item) for item in (claimed or set())}
    slots = 0 if remaining_slots is None else max(0, remaining_slots)
    progress = engine._ensure_progress_cache()
    splits = engine._ensure_split_cache()
    catalog = engine.units
    units: list[LearningUnit] = []
    for unit in catalog.values():
        if unit.type == LearningUnitType.PART_OVERVIEW:
            continue
        if unit.id in queued:
            continue
        if not is_unlearned(engine, unit.id):
            continue
        if not _unit_eligible_for_mix(engine, unit):
            continue
        if entitlements_on:
            article = unit.article_number
            if article and article not in claimed_keys and slots <= 0:
                continue
        if not sequential_prerequisites_satisfied(
            unit, units=catalog, progress=progress, splits=splits
        ):
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
    exclude_ids: set[str] | None = None,
) -> list[MixCandidate]:
    return candidates_from_units(
        eligible_units(
            engine,
            as_of=as_of,
            claimed=claimed,
            remaining_slots=remaining_slots,
            entitlements_on=entitlements_on,
            exclude_ids=exclude_ids,
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
