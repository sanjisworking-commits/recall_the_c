"""Rolling NEW-learning capacity around existing revision occupancy."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Callable

from constitution_memorizer.learning.schemas import LearningUnitType
from constitution_memorizer.progress.learning_plan import LearningPlan, default_learning_plan
from constitution_memorizer.progress.local_date import user_today
from constitution_memorizer.progress.review_projection import (
    projected_reviews_after_new_completion,
    remaining_review_schedule,
)
from constitution_memorizer.progress.scheduler import ReminderEngine
from constitution_memorizer.web.service import unit_visible_for_preference

ArticleAllowed = Callable[[str | None], bool]


def _default_allowed(_article: str | None) -> bool:
    return True


def revision_occupancy(
    engine: ReminderEngine,
    *,
    today: date,
) -> dict[date, int]:
    """How many visible reviews fall on each date (overdue rolls onto today)."""
    occupancy: dict[date, int] = defaultdict(int)
    for row in engine.list_all_progress():
        unit = engine.get_unit(row.learning_unit_id)
        if unit is None or unit.type == LearningUnitType.PART_OVERVIEW:
            continue
        if not unit_visible_for_preference(engine, unit):
            continue
        if row.status != "review" or row.next_revision is None:
            continue
        if row.next_revision <= today:
            occupancy[today] += 1
        for when, _rung in remaining_review_schedule(row):
            if when > today:
                occupancy[when] += 1
    return occupancy


def project_new_capacity(
    engine: ReminderEngine,
    plan: LearningPlan | None = None,
    *,
    today: date | None = None,
    horizon_end: date | None = None,
    entitled: bool = True,
    eligible_remaining: int | None = None,
    article_allowed: ArticleAllowed | None = None,
) -> dict[date, int]:
    """Future NEW capacity keyed by local date. Empty when unanchored/self-paced."""
    today = today or user_today(engine)
    if horizon_end is None:
        horizon_end = today + timedelta(days=62)
    plan = plan or engine.repo.get_learning_plan(engine.user_id)
    if not entitled or not plan.is_anchored or not plan.daily_target:
        return {}
    remaining = (
        eligible_remaining
        if eligible_remaining is not None
        else count_eligible_new_units(engine, article_allowed=article_allowed)
    )
    occupancy = revision_occupancy(engine, today=today)
    capacity: dict[date, int] = {}
    cursor = today
    target = int(plan.daily_target)
    while cursor <= horizon_end and remaining > 0:
        if occupancy.get(cursor, 0) > 0:
            cursor += timedelta(days=1)
            continue
        batch = min(target, remaining)
        if batch <= 0:
            break
        capacity[cursor] = batch
        remaining -= batch
        for when, _rung in projected_reviews_after_new_completion(cursor):
            occupancy[when] += batch
        cursor += timedelta(days=1)
    return capacity


def count_eligible_new_units(
    engine: ReminderEngine,
    *,
    article_allowed: ArticleAllowed | None = None,
    exclude_unit_ids: set[str] | None = None,
) -> int:
    from constitution_memorizer.progress.mix_selector import eligible_new_units

    return len(
        eligible_new_units(
            engine,
            article_allowed=article_allowed or _default_allowed,
            exclude_unit_ids=exclude_unit_ids,
        )
    )


def load_plan(engine: ReminderEngine) -> LearningPlan:
    try:
        return engine.repo.get_learning_plan(engine.user_id)
    except Exception:  # noqa: BLE001 — missing table in old fixtures
        return default_learning_plan(str(engine.user_id))
