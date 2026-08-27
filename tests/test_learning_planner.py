"""LearningPlanner: read-model of the persisted 15-day Auto window."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from constitution_memorizer.learning.schemas import LearningUnit, LearningUnitType
from constitution_memorizer.planner.planner import LearningPlanner
from constitution_memorizer.planner.roadmap import reconcile_auto_roadmap, roadmap_horizon
from constitution_memorizer.progress.scheduler import INTERVAL_LADDER, ReminderEngine, advance_interval


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


def _catalog(count: int = 40) -> list[LearningUnit]:
    return [_unit(f"u{i}", str(14 + i), i) for i in range(1, count + 1)]


def _fill(engine: ReminderEngine, today: date, *, target: int = 5) -> None:
    engine.upsert_learning_plan(mode="auto", daily_target=target, as_of=today)
    reconcile_auto_roadmap(
        engine,
        engine.get_learning_plan(),
        as_of=today,
        auto_entitled=True,
        claimed=set(),
        remaining_slots=99,
        entitlements_on=False,
    )


def test_selecting_auto_immediately_fills_window(tmp_path: Path):
    engine = ReminderEngine.from_units(tmp_path / "progress.db", _catalog())
    today = date(2026, 8, 1)
    _fill(engine, today, target=5)
    plan = engine.get_learning_plan()
    assert plan.activated_at is None
    days = LearningPlanner().project(
        engine,
        plan,
        as_of=today,
        until=today + timedelta(days=40),
        remaining_unseen=20,
        auto_entitled=True,
    )
    by_day = {day.day: day for day in days}
    assert by_day[today].kind == "new"
    assert by_day[today].new_capacity == 5
    beyond = today + timedelta(days=15)
    assert by_day[beyond].new_capacity == 0
    assert by_day[beyond].kind != "new"


def test_self_paced_emits_no_future_new(tmp_path: Path):
    engine = ReminderEngine.from_units(tmp_path / "progress.db", [_unit("u1", "14", 1)])
    today = date(2026, 8, 1)
    plan = engine.get_learning_plan()
    days = LearningPlanner().project(
        engine,
        plan,
        as_of=today,
        until=today + timedelta(days=20),
        remaining_unseen=20,
    )
    assert all(day.new_capacity == 0 for day in days)


def test_activated_auto_blocks_new_on_every_review_rung(tmp_path: Path):
    engine = ReminderEngine.from_units(tmp_path / "progress.db", _catalog())
    today = date(2026, 8, 1)
    _fill(engine, today, target=5)
    plan = engine.get_learning_plan()
    days = LearningPlanner().project(
        engine,
        plan,
        as_of=today,
        until=today + timedelta(days=70),
        remaining_unseen=40,
        auto_entitled=True,
    )
    by_day = {day.day: day for day in days}
    assert by_day[today].kind == "new"
    assert by_day[today].new_capacity == 5
    cursor = today
    current = INTERVAL_LADDER[0]
    occupied = [cursor + timedelta(days=current)]
    while True:
        nxt = advance_interval(current)
        if nxt is None:
            break
        occupied.append(occupied[-1] + timedelta(days=nxt))
        current = nxt
    horizon = roadmap_horizon(today)
    for when in occupied:
        if when in by_day and today <= when <= horizon:
            assert by_day[when].kind == "review", when
            assert by_day[when].new_capacity == 0
    assert by_day[today + timedelta(days=15)].new_capacity == 0
    assert by_day[today + timedelta(days=15)].kind != "new"


def test_calendar_marks_new_and_review_capacity(tmp_path: Path):
    from constitution_memorizer.web.calendar_view import build_calendar_month

    engine = ReminderEngine.from_units(tmp_path / "progress.db", _catalog())
    today = date(2026, 8, 1)
    _fill(engine, today, target=3)
    view = build_calendar_month(
        engine, year=2026, month=8, today=today, auto_entitled=True
    )
    day1 = next(d for d in view.days if d.day == 1)
    assert any(c.kind == "new_planned" and c.label.startswith("NEW ·") for c in day1.chips)
    assert any(c.kind == "new_planned" and c.unit_id for c in day1.chips)
    day2 = next(d for d in view.days if d.day == 2)
    assert any(c.kind == "review_capacity" and c.label.startswith("REVIEW ·") for c in day2.chips)
    assert day2.dominant_kind in {"scheduled", "due"}
    assert day1.dominant_kind == "new"


def test_lapse_stops_new_generation_without_wiping_history(tmp_path: Path):
    engine = ReminderEngine.from_units(tmp_path / "progress.db", _catalog())
    today = date(2026, 8, 1)
    _fill(engine, today, target=5)
    engine.activate_learning_plan(today)
    plan = engine.get_learning_plan()
    entitled = LearningPlanner().project(
        engine, plan, as_of=today, until=today + timedelta(days=10), remaining_unseen=10
    )
    lapsed = LearningPlanner().project(
        engine,
        plan,
        as_of=today,
        until=today + timedelta(days=10),
        remaining_unseen=10,
        auto_entitled=False,
    )
    assert any(day.new_capacity for day in entitled)
    assert all(day.new_capacity == 0 for day in lapsed)
    assert engine.get_learning_plan().activated_at == today


def test_todays_learning_session_consumes_new_capacity(tmp_path: Path):
    from constitution_memorizer.web.calendar_view import build_calendar_month

    engine = ReminderEngine.from_units(tmp_path / "progress.db", _catalog())
    today = date(2026, 8, 1)
    _fill(engine, today, target=5)
    planned = engine.list_auto_plan_day(today)
    assert planned is not None
    original = [item.learning_unit_id for item in planned.items]
    engine.create_study_session(
        session_id="auto-today",
        kind="auto_learning",
        plan_date=today,
        unit_ids=["u1"],
    )
    reconcile_auto_roadmap(
        engine,
        engine.get_learning_plan(),
        as_of=today,
        auto_entitled=True,
        claimed=set(),
        remaining_slots=99,
        entitlements_on=False,
    )
    session = engine.study_session_for_day(kind="auto_learning", plan_date=today)
    assert [item.learning_unit_id for item in session.items] == ["u1"]
    plan = engine.get_learning_plan()
    days = LearningPlanner().project(
        engine,
        plan,
        as_of=today,
        until=today + timedelta(days=10),
        remaining_unseen=20,
        auto_entitled=True,
    )
    today_plan = next(day for day in days if day.day == today)
    assert today_plan.new_capacity == 1
    assert today_plan.kind == "new"
    later_new = [day for day in days if day.day > today and day.kind == "new"]
    assert later_new
    view = build_calendar_month(
        engine, year=2026, month=8, today=today, auto_entitled=True
    )
    day1 = next(d for d in view.days if d.day == 1)
    assert any(c.unit_id == "u1" for c in day1.chips)
