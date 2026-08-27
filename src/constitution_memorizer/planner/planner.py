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
    from constitution_memorizer.web.service import _is_missing_optional_schema

    for kind in ("auto_learning", "day_plan"):
        try:
            if engine.study_session_for_day(kind=kind, plan_date=day) is not None:
                return True
        except Exception as error:  # noqa: BLE001
            if _is_missing_optional_schema(error):
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
    """Read-model of the persisted Auto window plus actual review occupancy."""

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
        from constitution_memorizer.planner.roadmap import WINDOW_DAYS, roadmap_horizon
        from constitution_memorizer.web.service import _is_missing_optional_schema

        occupied = _actual_review_occupancy(engine, as_of=as_of)
        hypothetical: dict[date, int] = defaultdict(int)
        can_plan = auto_entitled and auto_is_projectable(plan)
        window_end = roadmap_horizon(as_of)
        persisted: dict[date, list[str]] = {}
        if can_plan:
            try:
                for day in engine.list_auto_plan_window(as_of, min(until, window_end)):
                    persisted[day.plan_date] = [
                        item.learning_unit_id for item in day.items
                    ]
            except Exception as error:  # noqa: BLE001
                if not _is_missing_optional_schema(error):
                    raise
        today_session_ids: list[str] | None = None
        try:
            session = engine.study_session_for_day(kind="auto_learning", plan_date=as_of)
            if session is not None:
                today_session_ids = [item.learning_unit_id for item in session.items]
        except Exception as error:  # noqa: BLE001
            if not _is_missing_optional_schema(error):
                raise

        skipped: set[str] = set()
        pending: set[str] = set()
        try:
            session = engine.study_session_for_day(kind="auto_learning", plan_date=as_of)
            if session is not None:
                skipped = {
                    item.learning_unit_id
                    for item in session.items
                    if item.status == "deferred"
                }
                pending = {
                    item.learning_unit_id
                    for item in session.items
                    if item.status == "pending"
                }
        except Exception as error:  # noqa: BLE001
            if not _is_missing_optional_schema(error):
                raise

        from constitution_memorizer.planner.eligibility import is_unlearned

        if can_plan:
            for day, unit_ids in persisted.items():
                if day < as_of:
                    continue
                ids = today_session_ids if day == as_of and today_session_ids is not None else unit_ids
                for unit_id in ids:
                    if day == as_of and today_session_ids is not None:
                        if unit_id in skipped or unit_id not in pending:
                            continue
                    if not is_unlearned(engine, unit_id):
                        continue
                    for when, count in _reviews_from_learn_date(day, 1).items():
                        hypothetical[when] += count

        days: list[PlannedDay] = []
        cursor = as_of
        while cursor <= until:
            actual = occupied.get(cursor, 0)
            projected = hypothetical.get(cursor, 0) if cursor <= window_end else 0
            reviews = actual + projected
            new_capacity = 0
            if reviews > 0:
                kind: str = "review"
            elif cursor > window_end or not can_plan:
                kind = "empty"
            else:
                ids = persisted.get(cursor, [])
                if cursor == as_of and today_session_ids is not None:
                    ids = today_session_ids
                new_capacity = len(ids)
                kind = "new" if new_capacity else "empty"
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
