"""Rolling NEW-learning capacity around ReminderEngine review projections."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from constitution_memorizer.planner.models import PlannedDay, auto_is_projectable
from constitution_memorizer.progress.repository import UserLearningPlan
from constitution_memorizer.progress.scheduler import INTERVAL_LADDER, ReminderEngine, advance_interval
from constitution_memorizer.web.calendar_view import remaining_review_schedule

# How far past the requested window to keep simulating so a late-month NEW day
# still plants its D+1 review on the next month's grid.
_TAIL_DAYS = 60


def _reviews_from_learn_date(learn_date: date, count: int) -> dict[date, int]:
    """Hypothetical review occupancy produced by ``count`` new units learned on ``learn_date``."""
    occupancy: dict[date, int] = defaultdict(int)
    if count <= 0:
        return occupancy
    current = INTERVAL_LADDER[0]
    cursor = learn_date + timedelta(days=current)
    occupancy[cursor] += count
    while True:
        nxt = advance_interval(current)
        if nxt is None:
            break
        cursor = cursor + timedelta(days=nxt)
        occupancy[cursor] += count
        current = nxt
    return occupancy


def _learning_session_on(engine: ReminderEngine, day: date) -> bool:
    """True when today's Auto or Plan-my-day session already exists (any status)."""
    from constitution_memorizer.web.service import _is_missing_study_session_table

    for kind in ("auto_learning", "day_plan"):
        try:
            if engine.study_session_for_day(kind=kind, plan_date=day) is not None:
                return True
        except Exception as error:  # noqa: BLE001
            if _is_missing_study_session_table(error):
                return False
            raise
    return False


def _actual_review_occupancy(engine: ReminderEngine, *, as_of: date) -> dict[date, int]:
    occupied: dict[date, int] = defaultdict(int)
    due_today = 0
    for row in engine.list_all_progress():
        if row.status == "review" and row.next_revision is not None and row.next_revision <= as_of:
            due_today += 1
        for when, _rung in remaining_review_schedule(row):
            if when > as_of:
                occupied[when] += 1
    if due_today:
        occupied[as_of] += due_today
    return occupied


class LearningPlanner:
    """Future NEW capacity only. Never assigns clause IDs months in advance."""

    def project(
        self,
        engine: ReminderEngine,
        plan: UserLearningPlan,
        *,
        as_of: date,
        until: date,
        remaining_unseen: int,
        auto_entitled: bool = True,
    ) -> list[PlannedDay]:
        occupied = _actual_review_occupancy(engine, as_of=as_of)
        remaining = max(0, remaining_unseen)
        can_plan = auto_entitled and auto_is_projectable(plan)
        target = plan.daily_target if can_plan else None
        today_session_used = _learning_session_on(engine, as_of)
        sim_end = until + timedelta(days=_TAIL_DAYS)
        cursor = as_of
        days: list[PlannedDay] = []
        while cursor <= sim_end:
            reviews = occupied.get(cursor, 0)
            new_capacity = 0
            if reviews > 0:
                kind: str = "review"
            elif cursor == as_of and today_session_used:
                # Today's Auto / Plan-my-day session already consumed the slot.
                kind = "empty"
            elif can_plan and target and remaining > 0:
                kind = "new"
                new_capacity = min(int(target), remaining)
                remaining -= new_capacity
                for when, count in _reviews_from_learn_date(cursor, new_capacity).items():
                    occupied[when] += count
            else:
                kind = "empty"
            if cursor <= until:
                days.append(
                    PlannedDay(
                        day=cursor,
                        kind=kind,  # type: ignore[arg-type]
                        review_count=reviews,
                        new_capacity=new_capacity,
                    )
                )
            cursor += timedelta(days=1)
        return days

    def next_learning_day(
        self,
        engine: ReminderEngine,
        plan: UserLearningPlan,
        *,
        as_of: date,
        remaining_unseen: int,
        auto_entitled: bool = True,
        horizon_days: int = 120,
    ) -> date | None:
        until = as_of + timedelta(days=horizon_days)
        for day in self.project(
            engine,
            plan,
            as_of=as_of,
            until=until,
            remaining_unseen=remaining_unseen,
            auto_entitled=auto_entitled,
        ):
            if day.kind == "new" and day.new_capacity > 0:
                return day.day
        return None
