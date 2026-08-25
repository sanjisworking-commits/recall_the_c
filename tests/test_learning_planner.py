"""LearningPlanner capacity: full-ladder occupancy and unanchored Auto Plan."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from constitution_memorizer.learning.schemas import LearningUnit, LearningUnitType
from constitution_memorizer.progress.learning_plan import LearningPlan
from constitution_memorizer.progress.planner import project_new_capacity
from constitution_memorizer.progress.review_projection import (
    projected_reviews_after_new_completion,
)
from constitution_memorizer.progress.scheduler import INTERVAL_LADDER, ReminderEngine
from constitution_memorizer.progress.study_session import save_learning_plan


def _unit(unit_id: str, article: str, order: int) -> LearningUnit:
    return LearningUnit(
        id=unit_id,
        type=LearningUnitType.CLAUSE,
        article_number=article,
        display_title=f"Article {article}",
        text=f"Text for {unit_id}",
        estimated_learning_time=60,
        revision_order=order,
        tags=["Part III"],
    )


def test_projected_reviews_after_new_completion_uses_full_ladder():
    learned = date(2026, 8, 1)
    schedule = projected_reviews_after_new_completion(learned)
    assert [rung for _, rung in schedule] == list(INTERVAL_LADDER)
    assert schedule[0][0] == learned + timedelta(days=1)
    # Same walk as a real new unit: each later rung is added to the previous date.
    assert schedule[1][0] == schedule[0][0] + timedelta(days=3)


def test_full_ladder_collisions_block_every_rung_not_only_day_one(tmp_path: Path):
    engine = ReminderEngine.from_units(
        tmp_path / "progress.db",
        [_unit("u1", "14", 1)],
    )
    today = date(2026, 8, 1)
    plan = LearningPlan(
        user_id=str(engine.user_id),
        mode="auto",
        daily_target=5,
        activated_at=today,
        plan_prompt_dismissed_on=None,
        updated_at="",
    )
    capacity = project_new_capacity(
        engine,
        plan,
        today=today,
        horizon_end=today + timedelta(days=70),
        entitled=True,
        eligible_remaining=40,
    )
    assert capacity.get(today) == 5
    occupied = [when for when, _ in projected_reviews_after_new_completion(today)]
    assert occupied[0] == today + timedelta(days=1)
    assert occupied[1] > today + timedelta(days=1)
    for when in occupied:
        assert when not in capacity, f"NEW leaked onto review rung {when}"
    later = [day for day in sorted(capacity) if day > today]
    assert later, "later NEW days should reflow around the full collision set"
    assert later[0] != today + timedelta(days=1)
    assert occupied[1] not in capacity


def test_unanchored_auto_plan_emits_no_future_new(tmp_path: Path):
    engine = ReminderEngine.from_units(
        tmp_path / "progress.db",
        [_unit("u1", "14", 1)],
    )
    save_learning_plan(engine, mode="auto", daily_target=5)
    today = date(2026, 8, 1)
    plan = engine.repo.get_learning_plan(engine.user_id)
    assert plan.activated_at is None
    assert plan.is_unanchored_auto
    capacity = project_new_capacity(
        engine, plan, today=today, entitled=True, eligible_remaining=20
    )
    assert capacity == {}


def test_self_paced_emits_no_future_new(tmp_path: Path):
    engine = ReminderEngine.from_units(
        tmp_path / "progress.db",
        [_unit("u1", "14", 1)],
    )
    today = date(2026, 8, 1)
    plan = engine.repo.get_learning_plan(engine.user_id)
    assert plan.mode == "self_paced"
    assert (
        project_new_capacity(
            engine, plan, today=today, entitled=True, eligible_remaining=20
        )
        == {}
    )
