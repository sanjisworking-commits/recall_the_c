"""Rolling 15-day Auto roadmap: occupancy, compaction, early revision, entitlements."""

from __future__ import annotations

import sqlite3
import threading
from datetime import date, timedelta
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import InMemorySessionStore
from constitution_memorizer.learning.schemas import LearningUnit, LearningUnitType
from constitution_memorizer.multiuser.settings import MultiUserSettings, clear_settings_cache
from constitution_memorizer.planner.planner import LearningPlanner
from constitution_memorizer.planner.roadmap import (
    WINDOW_DAYS,
    auto_roadmap_needs_reconcile,
    reconcile_auto_roadmap,
    roadmap_horizon,
)
from constitution_memorizer.progress.repository import (
    AutoPlanDay,
    AutoPlanItem,
    ProgressRepository,
)
from constitution_memorizer.progress.scheduler import (
    INTERVAL_LADDER,
    ModesIncompleteError,
    ReminderEngine,
    advance_interval,
)
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.calendar_view import build_calendar_month
from constitution_memorizer.web.service import ensure_auto_roadmap, user_today
from tests.quiz_helpers import complete_all_modes

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"


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


def _catalog(count: int = 80) -> list[LearningUnit]:
    return [_unit(f"u{i}", str(100 + i), i) for i in range(1, count + 1)]


def _engine(tmp_path: Path, count: int = 80) -> ReminderEngine:
    return ReminderEngine.from_units(tmp_path / "progress.db", _catalog(count))


def _reconcile(engine: ReminderEngine, as_of: date, *, target: int = 3) -> None:
    plan = engine.get_learning_plan()
    if not plan.is_auto:
        engine.upsert_learning_plan(mode="auto", daily_target=target, as_of=as_of)
        plan = engine.get_learning_plan()
    reconcile_auto_roadmap(
        engine,
        plan,
        as_of=as_of,
        auto_entitled=True,
        claimed=set(),
        remaining_slots=99,
        entitlements_on=False,
    )


def _ids_on(engine: ReminderEngine, day: date) -> list[str]:
    planned = engine.list_auto_plan_day(day)
    if planned is None:
        return []
    return [item.learning_unit_id for item in planned.items]


def _window_ids(engine: ReminderEngine, as_of: date) -> list[str]:
    horizon = roadmap_horizon(as_of)
    ids: list[str] = []
    for day in engine.list_auto_plan_window(as_of, horizon):
        ids.extend(item.learning_unit_id for item in day.items)
    return ids


def _fingerprint(engine: ReminderEngine, as_of: date):
    horizon = roadmap_horizon(as_of)
    return [
        (
            day.plan_date,
            day.daily_target,
            day.updated_at,
            tuple((item.learning_unit_id, item.position) for item in day.items),
        )
        for day in engine.list_auto_plan_window(as_of, horizon)
    ]


def _downgrade_to_schema_0014(conn: sqlite3.Connection) -> None:
    """True 0014: no auto_plan_* tables and no target_effective_on column."""
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("DROP TABLE IF EXISTS auto_plan_item")
    conn.execute("DROP TABLE IF EXISTS auto_plan_day")
    cols = [
        str(row[1]) for row in conn.execute("PRAGMA table_info(user_learning_plan)")
    ]
    if "target_effective_on" in cols:
        try:
            conn.execute(
                "ALTER TABLE user_learning_plan DROP COLUMN target_effective_on"
            )
        except sqlite3.OperationalError:
            conn.execute(
                """
                CREATE TABLE user_learning_plan_0014 (
                    user_id TEXT PRIMARY KEY,
                    mode TEXT NOT NULL DEFAULT 'self_paced'
                        CHECK (mode IN ('self_paced', 'auto')),
                    daily_target INTEGER
                        CHECK (daily_target IS NULL OR daily_target IN (3, 5, 7)),
                    activated_at TEXT,
                    prompt_dismissed_on TEXT,
                    last_anchor_theme TEXT,
                    updated_at TEXT NOT NULL,
                    CHECK (
                        (mode = 'self_paced')
                        OR (mode = 'auto' AND daily_target IS NOT NULL)
                    )
                )
                """
            )
            conn.execute(
                """
                INSERT INTO user_learning_plan_0014 (
                    user_id, mode, daily_target, activated_at,
                    prompt_dismissed_on, last_anchor_theme, updated_at
                )
                SELECT user_id, mode, daily_target, activated_at,
                       prompt_dismissed_on, last_anchor_theme, updated_at
                FROM user_learning_plan
                """
            )
            conn.execute("DROP TABLE user_learning_plan")
            conn.execute(
                "ALTER TABLE user_learning_plan_0014 RENAME TO user_learning_plan"
            )
    conn.execute("PRAGMA foreign_keys = ON")
    conn.commit()
    remaining = [
        str(row[1]) for row in conn.execute("PRAGMA table_info(user_learning_plan)")
    ]
    assert "target_effective_on" not in remaining
    tables = {
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert "auto_plan_day" not in tables
    assert "auto_plan_item" not in tables


def test_interval_ladder_unchanged():
    assert INTERVAL_LADDER == (1, 3, 7, 15, 30, 60)
    assert advance_interval(7) == 15
    assert advance_interval(15) == 30


def test_a_window_is_fifteen_days_and_has_no_new_on_day_15(tmp_path: Path):
    engine = _engine(tmp_path)
    today = date(2026, 9, 1)
    _reconcile(engine, today, target=3)
    horizon = roadmap_horizon(today)
    assert (horizon - today).days == WINDOW_DAYS - 1
    days = engine.list_auto_plan_window(today, horizon)
    assert days
    assert max(day.plan_date for day in days) <= horizon
    beyond = today + timedelta(days=15)
    assert engine.list_auto_plan_day(beyond) is None
    planned = LearningPlanner().project(
        engine,
        engine.get_learning_plan(),
        as_of=today,
        until=beyond,
        remaining_unseen=80,
        auto_entitled=True,
    )
    by_day = {day.day: day for day in planned}
    assert by_day[beyond].new_capacity == 0
    assert by_day[beyond].kind != "new"


def test_b_fills_to_daily_target_on_empty_days(tmp_path: Path):
    engine = _engine(tmp_path)
    today = date(2026, 9, 1)
    _reconcile(engine, today, target=5)
    assert len(_ids_on(engine, today)) == 5


def test_c_review_collision_zeroes_new(tmp_path: Path):
    engine = _engine(tmp_path)
    today = date(2026, 9, 1)
    _reconcile(engine, today, target=3)
    first = _ids_on(engine, today)
    assert first
    engine.mark_all_modes_seen(first[0])
    engine.mark_done(first[0], as_of=today, require_all_modes=True)
    _reconcile(engine, today, target=3)
    plus_one = today + timedelta(days=1)
    assert _ids_on(engine, plus_one) == []
    planned = LearningPlanner().project(
        engine,
        engine.get_learning_plan(),
        as_of=today,
        until=plus_one,
        remaining_unseen=80,
        auto_entitled=True,
    )
    by_day = {day.day: day for day in planned}
    assert by_day[plus_one].kind == "review"
    assert by_day[plus_one].new_capacity == 0
    assert by_day[plus_one].review_count >= 1


def test_d_review_count_is_uncapped(tmp_path: Path):
    engine = _engine(tmp_path, count=20)
    today = date(2026, 9, 1)
    for i in range(1, 7):
        engine.repo.upsert_progress(
            engine.user_id,
            unit_id=f"u{i}",
            status="review",
            times_completed=1,
            last_completed=today - timedelta(days=1),
            next_revision=today,
            interval_days=1,
        )
    _reconcile(engine, today, target=3)
    assert _ids_on(engine, today) == []
    planned = LearningPlanner().project(
        engine,
        engine.get_learning_plan(),
        as_of=today,
        until=today,
        remaining_unseen=80,
        auto_entitled=True,
    )
    assert planned[0].kind == "review"
    assert planned[0].review_count == 6


def test_i_double_reconcile_is_stable(tmp_path: Path):
    engine = _engine(tmp_path)
    today = date(2026, 9, 1)
    _reconcile(engine, today, target=3)
    first = [
        (day.plan_date, tuple(item.learning_unit_id for item in day.items))
        for day in engine.list_auto_plan_window(today, roadmap_horizon(today))
    ]
    _reconcile(engine, today, target=3)
    second = [
        (day.plan_date, tuple(item.learning_unit_id for item in day.items))
        for day in engine.list_auto_plan_window(today, roadmap_horizon(today))
    ]
    assert first == second


def test_rolling_horizon_preserves_past_rows(tmp_path: Path):
    engine = _engine(tmp_path)
    day0 = date(2026, 9, 1)
    _reconcile(engine, day0, target=3)
    historical = engine.list_auto_plan_day(day0)
    assert historical is not None
    snapshot = (
        historical.daily_target,
        tuple((item.learning_unit_id, item.position) for item in historical.items),
    )
    _reconcile(engine, day0 + timedelta(days=1), target=3)
    kept = engine.list_auto_plan_day(day0)
    assert kept is not None
    assert (
        kept.daily_target,
        tuple((item.learning_unit_id, item.position) for item in kept.items),
    ) == snapshot


def test_manual_learn_reflow_of_future_new(tmp_path: Path):
    engine = _engine(tmp_path)
    today = date(2026, 9, 5)
    _reconcile(engine, today, target=3)
    future = today + timedelta(days=4)
    while _ids_on(engine, future) == [] and future <= roadmap_horizon(today):
        future += timedelta(days=1)
    assigned = _ids_on(engine, future)
    assert assigned
    victim = assigned[0]
    engine.mark_all_modes_seen(victim)
    engine.mark_done(victim, as_of=today, require_all_modes=True)
    _reconcile(engine, today, target=3)
    assert victim not in _ids_on(engine, future)
    assert engine.get_progress(victim).last_completed == today


def test_no_review_plus_new_coexistence(tmp_path: Path):
    engine = _engine(tmp_path)
    today = date(2026, 9, 1)
    _reconcile(engine, today, target=3)
    occupied = {
        item.day: item
        for item in LearningPlanner().project(
            engine,
            engine.get_learning_plan(),
            as_of=today,
            until=roadmap_horizon(today),
            remaining_unseen=80,
            auto_entitled=True,
        )
    }
    for day in engine.list_auto_plan_window(today, roadmap_horizon(today)):
        if day.items:
            assert occupied[day.plan_date].kind != "review"


def test_today_session_immutability(tmp_path: Path):
    engine = _engine(tmp_path)
    today = date(2026, 9, 1)
    _reconcile(engine, today, target=3)
    original = _ids_on(engine, today)
    engine.create_study_session(
        session_id="sess-today",
        kind="auto_learning",
        plan_date=today,
        unit_ids=original,
    )
    later = today + timedelta(days=2)
    while not _ids_on(engine, later):
        later += timedelta(days=1)
    future_unit = _ids_on(engine, later)[0]
    engine.mark_all_modes_seen(future_unit)
    engine.mark_done(future_unit, as_of=today, require_all_modes=True)
    _reconcile(engine, today, target=5)
    session = engine.study_session_for_day(kind="auto_learning", plan_date=today)
    assert [item.learning_unit_id for item in session.items] == original
    assert _ids_on(engine, today) == original


def test_plan_change_3_to_5_history_safe(tmp_path: Path):
    engine = _engine(tmp_path)
    day0 = date(2026, 9, 10)
    _reconcile(engine, day0, target=3)
    unit = _ids_on(engine, day0)[0]
    engine.mark_all_modes_seen(unit)
    engine.mark_done(unit, as_of=day0, require_all_modes=True)
    engine.create_study_session(
        session_id="hist",
        kind="auto_learning",
        plan_date=day0,
        unit_ids=_ids_on(engine, day0),
    )
    engine.complete_study_session("hist")
    before_progress = engine.get_progress(unit)
    before_session = engine.study_session_for_day(kind="auto_learning", plan_date=day0)
    today = date(2026, 9, 12)
    engine.upsert_learning_plan(mode="auto", daily_target=5, as_of=today)
    _reconcile(engine, today, target=5)
    after = engine.get_progress(unit)
    assert after.times_completed == before_progress.times_completed
    assert after.interval_days == before_progress.interval_days
    assert after.next_revision == before_progress.next_revision
    assert after.status == before_progress.status
    kept = engine.study_session_for_day(kind="auto_learning", plan_date=day0)
    assert [i.learning_unit_id for i in kept.items] == [
        i.learning_unit_id for i in before_session.items
    ]
    plan = engine.get_learning_plan()
    assert plan.daily_target == 5
    assert plan.target_effective_on == today
    if _ids_on(engine, today):
        assert len(_ids_on(engine, today)) == 5


def test_plan_change_7_to_3_future_capped(tmp_path: Path):
    engine = _engine(tmp_path)
    today = date(2026, 9, 12)
    past = date(2026, 9, 10)
    engine.upsert_learning_plan(mode="auto", daily_target=7, as_of=past)
    _reconcile(engine, past, target=7)
    engine.create_study_session(
        session_id="seven",
        kind="auto_learning",
        plan_date=past,
        unit_ids=_ids_on(engine, past),
    )
    engine.upsert_learning_plan(mode="auto", daily_target=3, as_of=today)
    _reconcile(engine, today, target=3)
    kept = engine.study_session_for_day(kind="auto_learning", plan_date=past)
    assert len(kept.items) == 7
    for day in engine.list_auto_plan_window(today, roadmap_horizon(today)):
        assert len(day.items) <= 3


def test_today_not_started_rebuilds_to_new_target(tmp_path: Path):
    engine = _engine(tmp_path)
    today = date(2026, 9, 12)
    _reconcile(engine, today, target=3)
    assert len(_ids_on(engine, today)) == 3
    engine.upsert_learning_plan(mode="auto", daily_target=5, as_of=today)
    _reconcile(engine, today, target=5)
    assert len(_ids_on(engine, today)) == 5


def test_today_started_does_not_append(tmp_path: Path):
    engine = _engine(tmp_path)
    today = date(2026, 9, 12)
    _reconcile(engine, today, target=3)
    original = _ids_on(engine, today)
    engine.create_study_session(
        session_id="started",
        kind="auto_learning",
        plan_date=today,
        unit_ids=original,
    )
    engine.upsert_learning_plan(mode="auto", daily_target=5, as_of=today)
    _reconcile(engine, today, target=5)
    assert _ids_on(engine, today) == original
    session = engine.study_session_for_day(kind="auto_learning", plan_date=today)
    assert [i.learning_unit_id for i in session.items] == original


def test_today_complete_stays_complete(tmp_path: Path):
    engine = _engine(tmp_path)
    today = date(2026, 9, 12)
    _reconcile(engine, today, target=3)
    ids = _ids_on(engine, today)
    engine.create_study_session(
        session_id="done-today",
        kind="auto_learning",
        plan_date=today,
        unit_ids=ids,
    )
    engine.complete_study_session("done-today")
    engine.upsert_learning_plan(mode="auto", daily_target=7, as_of=today)
    _reconcile(engine, today, target=7)
    session = engine.study_session_for_day(kind="auto_learning", plan_date=today)
    assert session.status == "complete"
    assert [i.learning_unit_id for i in session.items] == ids


def test_revision_collision_after_target_change(tmp_path: Path):
    engine = _engine(tmp_path)
    today = date(2026, 9, 1)
    _reconcile(engine, today, target=3)
    engine.repo.upsert_progress(
        engine.user_id,
        unit_id="u80",
        status="review",
        times_completed=1,
        last_completed=today - timedelta(days=1),
        next_revision=today + timedelta(days=3),
        interval_days=3,
    )
    engine.upsert_learning_plan(mode="auto", daily_target=7, as_of=today)
    _reconcile(engine, today, target=7)
    assert _ids_on(engine, today + timedelta(days=3)) == []


def test_user_isolation(tmp_path: Path):
    catalog = _catalog()
    conn = ReminderEngine.from_units(tmp_path / "p.db", catalog).repo._conn
    repo = ProgressRepository(conn)
    user_a = uuid4()
    user_b = uuid4()
    eng_a = ReminderEngine.from_repository(repo, {u.id: u for u in catalog}, user_id=user_a)
    eng_b = ReminderEngine.from_repository(repo, {u.id: u for u in catalog}, user_id=user_b)
    today = date(2026, 9, 1)
    _reconcile(eng_a, today, target=5)
    _reconcile(eng_b, today, target=3)
    assert len(_ids_on(eng_a, today)) == 5
    assert len(_ids_on(eng_b, today)) == 3
    _reconcile(eng_a, today, target=7)
    assert len(_ids_on(eng_b, today)) == 3


def test_complete_revision_early_anchors_from_scheduled_due(tmp_path: Path):
    engine = _engine(tmp_path, count=3)
    today = date(2026, 9, 9)
    due = date(2026, 9, 12)
    engine.repo.upsert_progress(
        engine.user_id,
        unit_id="u1",
        status="review",
        times_completed=3,
        last_completed=date(2026, 9, 5),
        next_revision=due,
        interval_days=7,
    )
    engine.mark_all_modes_seen("u1")
    result = engine.complete_revision_early("u1", as_of=today)
    assert result.progress.next_revision == date(2026, 9, 27)
    assert result.progress.next_revision != today + timedelta(days=15)
    assert result.progress.interval_days == 15
    assert engine.modes_seen("u1") == set()


def test_complete_revision_early_requires_modes(tmp_path: Path):
    engine = _engine(tmp_path, count=3)
    today = date(2026, 9, 9)
    engine.repo.upsert_progress(
        engine.user_id,
        unit_id="u1",
        status="review",
        times_completed=3,
        last_completed=date(2026, 9, 5),
        next_revision=date(2026, 9, 12),
        interval_days=7,
    )
    try:
        engine.complete_revision_early("u1", as_of=today)
        raise AssertionError("expected ModesIncompleteError")
    except ModesIncompleteError:
        pass
    assert engine.get_progress("u1").next_revision == date(2026, 9, 12)


def test_later_anchors_preserved_after_early_consume(tmp_path: Path):
    engine = _engine(tmp_path, count=3)
    today = date(2026, 9, 9)
    engine.repo.upsert_progress(
        engine.user_id,
        unit_id="u1",
        status="review",
        times_completed=3,
        last_completed=date(2026, 9, 5),
        next_revision=date(2026, 9, 12),
        interval_days=7,
    )
    engine.mark_all_modes_seen("u1")
    engine.complete_revision_early("u1", as_of=today)
    row = engine.get_progress("u1")
    from constitution_memorizer.web.calendar_view import remaining_review_schedule

    remaining = [when for when, _rung in remaining_review_schedule(row)]
    assert remaining[0] == date(2026, 9, 27)
    assert remaining[1] == date(2026, 10, 27)
    assert remaining[2] == date(2026, 12, 26)


def test_vacancy_moves_later_bundle_forward(tmp_path: Path):
    engine = _engine(tmp_path)
    today = date(2026, 9, 1)
    _reconcile(engine, today, target=3)
    first = _ids_on(engine, today)
    later = today + timedelta(days=2)
    while later <= roadmap_horizon(today) and not _ids_on(engine, later):
        later += timedelta(days=1)
    later_ids = _ids_on(engine, later)
    assert later_ids
    for unit_id in first:
        engine.mark_all_modes_seen(unit_id)
        engine.mark_done(unit_id, as_of=today, require_all_modes=True)
    _reconcile(engine, today, target=3)
    moved = _ids_on(engine, today)
    assert moved
    assert set(first).isdisjoint(moved)
    assert set(later_ids) & set(moved)


def test_missed_new_does_not_plant_reviews(tmp_path: Path):
    engine = _engine(tmp_path)
    day0 = date(2026, 9, 1)
    _reconcile(engine, day0, target=3)
    missed = _ids_on(engine, day0)
    historical = tuple(
        (item.learning_unit_id, item.position)
        for item in engine.list_auto_plan_day(day0).items
    )
    nxt = day0 + timedelta(days=1)
    _reconcile(engine, nxt, target=3)
    kept = engine.list_auto_plan_day(day0)
    assert tuple((i.learning_unit_id, i.position) for i in kept.items) == historical
    front = _ids_on(engine, nxt)
    assert front[:3] == missed
    for unit_id in missed:
        row = engine.get_progress(unit_id)
        assert row is None or row.times_completed == 0


def test_skip_today_requeues_without_fake_reviews(tmp_path: Path):
    engine = _engine(tmp_path)
    today = date(2026, 9, 1)
    _reconcile(engine, today, target=3)
    ids = _ids_on(engine, today)
    a, b, c = ids
    engine.create_study_session(
        session_id="skip-sess",
        kind="auto_learning",
        plan_date=today,
        unit_ids=ids,
    )
    engine.mark_all_modes_seen(a)
    engine.mark_done(a, as_of=today, require_all_modes=True)
    engine.set_study_item_status(session_id="skip-sess", unit_id=a, status="completed")
    engine.mark_all_modes_seen(b)
    engine.mark_done(b, as_of=today, require_all_modes=True)
    engine.set_study_item_status(session_id="skip-sess", unit_id=b, status="completed")
    engine.set_study_item_status(session_id="skip-sess", unit_id=c, status="deferred")
    _reconcile(engine, today, target=3)
    session = engine.study_session_for_day(kind="auto_learning", plan_date=today)
    skipped = next(i for i in session.items if i.learning_unit_id == c)
    assert skipped.status == "deferred"
    progress_c = engine.get_progress(c)
    assert progress_c is None or progress_c.times_completed == 0
    future_days = [
        day.plan_date
        for day in engine.list_auto_plan_window(today + timedelta(days=1), roadmap_horizon(today))
        if c in {item.learning_unit_id for item in day.items}
    ]
    assert len(future_days) == 1
    assert future_days[0] > today
    assert c in _ids_on(engine, today)
    future_ids = [
        item.learning_unit_id
        for day in engine.list_auto_plan_window(
            today + timedelta(days=1), roadmap_horizon(today)
        )
        for item in day.items
    ]
    assert future_ids.count(c) == 1
    planned = LearningPlanner().project(
        engine,
        engine.get_learning_plan(),
        as_of=today,
        until=roadmap_horizon(today),
        remaining_unseen=80,
        auto_entitled=True,
    )
    plus_one = today + timedelta(days=1)
    by_day = {day.day: day for day in planned}
    # Done A/B plant a +1 review; skipped C must not add a second fake one.
    assert by_day[plus_one].review_count == 2


def test_reconciler_never_writes_before_as_of(tmp_path: Path):
    engine = _engine(tmp_path)
    past = date(2026, 9, 1)
    today = date(2026, 9, 3)
    engine.replace_auto_plan_day(past, 3, ["u1", "u2", "u3"])
    before = [
        (row["learning_unit_id"], row["position"], row["plan_date"])
        for row in engine.repo.conn.execute(
            "SELECT learning_unit_id, position, plan_date FROM auto_plan_item WHERE plan_date < ?",
            (today.isoformat(),),
        ).fetchall()
    ]
    _reconcile(engine, today, target=5)
    after = [
        (row["learning_unit_id"], row["position"], row["plan_date"])
        for row in engine.repo.conn.execute(
            "SELECT learning_unit_id, position, plan_date FROM auto_plan_item WHERE plan_date < ?",
            (today.isoformat(),),
        ).fetchall()
    ]
    assert before == after
    past_day = AutoPlanDay(
        plan_date=past,
        daily_target=3,
        items=(AutoPlanItem(plan_date=past, learning_unit_id="u9", position=0),),
    )
    try:
        engine.replace_auto_plan_window_atomic(today, roadmap_horizon(today), [past_day])
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_queue_dedupe_historical_and_deferred(tmp_path: Path):
    engine = _engine(tmp_path)
    today = date(2026, 9, 3)
    engine.replace_auto_plan_day(date(2026, 9, 1), 3, ["u1", "u2", "u3"])
    engine.replace_auto_plan_day(date(2026, 9, 2), 3, ["u1", "u4", "u5"])
    engine.create_study_session(
        session_id="def",
        kind="auto_learning",
        plan_date=date(2026, 9, 2),
        unit_ids=["u1", "u4", "u5"],
    )
    engine.set_study_item_status(session_id="def", unit_id="u1", status="deferred")
    _reconcile(engine, today, target=3)
    window = _window_ids(engine, today)
    assert window.count("u1") == 1
    assert len(window) == len(set(window))


def test_no_duplicate_ids_in_mutable_window(tmp_path: Path):
    engine = _engine(tmp_path)
    today = date(2026, 9, 1)
    _reconcile(engine, today, target=7)
    window = _window_ids(engine, today)
    assert len(window) == len(set(window))
    for day in engine.list_auto_plan_window(today, roadmap_horizon(today)):
        positions = [item.position for item in day.items]
        assert positions == list(range(len(positions)))


def test_concurrent_reconcile_does_not_duplicate(tmp_path: Path):
    path = tmp_path / "shared.db"
    catalog = _catalog()
    today = date(2026, 9, 1)
    bootstrap = ReminderEngine.from_units(path, catalog)
    bootstrap.upsert_learning_plan(mode="auto", daily_target=3, as_of=today)
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            eng = ReminderEngine.from_units(path, catalog)
            _reconcile(eng, today, target=3)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    final = ReminderEngine.from_units(path, catalog)
    window = _window_ids(final, today)
    assert len(window) == len(set(window))
    for day in final.list_auto_plan_window(today, roadmap_horizon(today)):
        positions = [item.position for item in day.items]
        assert positions == list(range(len(positions)))


def test_free_user_cannot_persist_auto_via_settings(tmp_path: Path):
    clear_settings_cache()
    client = TestClient(
        create_app(
            units_path=MINI_UNITS,
            db_path=tmp_path / "progress.db",
            multiuser=True,
            multiuser_settings=MultiUserSettings(
                _env_file=None,
                APP_ENV="test",
                MULTIUSER_ENABLED="true",
                AUTH_GOOGLE_ENABLED="true",
                AUTH_PHONE_ENABLED="true",
                SESSION_SECRET="test-secret",
                SUPABASE_URL="http://example.invalid",
                SUPABASE_ANON_KEY="anon",
                DATABASE_URL="",
                COOKIE_SECURE="false",
                ARTICLE_ENTITLEMENTS_ENABLED="true",
                ADMIN_ENABLED="false",
            ),
            auth_provider=FakeAuthProvider(),
            session_store=InMemorySessionStore(),
        )
    )
    start = client.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state")
    client.get(
        f"/auth/callback?code=fake-google-code&state={state}", follow_redirects=False
    )
    client.post(
        "/settings/learning-plan",
        data={"mode": "auto", "daily_target": "5"},
        follow_redirects=False,
    )
    store = client.app.state.session_store
    user_id = sorted(store._sessions.values(), key=lambda s: s.created_at)[-1].user.id
    eng = client.app.state.engine.for_user(user_id)
    assert not eng.get_learning_plan().is_auto
    today = user_today(eng)
    assert eng.list_auto_plan_window(today, roadmap_horizon(today)) == []


def test_practice_seen_does_not_persist_modes(tmp_path: Path):
    client = TestClient(
        create_app(
            units_path=MINI_UNITS,
            db_path=tmp_path / "progress.db",
            multiuser=False,
        )
    )
    eng = client.app.state.engine
    today = user_today(eng)
    eng.repo.upsert_progress(
        eng.user_id,
        unit_id="clause-1",
        status="review",
        times_completed=3,
        last_completed=today - timedelta(days=3),
        next_revision=today + timedelta(days=3),
        interval_days=7,
    )
    before = set(eng.modes_seen("clause-1"))
    page = client.get("/learn/clause-1")
    assert "Your next revision is scheduled" in page.text
    seen = client.post(
        "/learn/clause-1/seen",
        data={"mode": "cloze"},
        headers={"Accept": "application/json"},
    )
    assert seen.json().get("persisted") is False
    assert eng.modes_seen("clause-1") == before
    practice = client.post(
        "/learn/clause-1/seen?revision_intent=practice",
        data={"mode": "cloze", "revision_intent": "practice"},
        headers={"Accept": "application/json"},
    )
    assert practice.json().get("persisted") is False
    assert eng.modes_seen("clause-1") == before
    client.post(
        "/learn/clause-1/done?revision_intent=practice",
        data={"revision_intent": "practice"},
        follow_redirects=False,
    )
    assert eng.get_progress("clause-1").next_revision == today + timedelta(days=3)


def test_early_consume_done_clears_modes(tmp_path: Path):
    engine = _engine(tmp_path, count=3)
    today = date(2026, 9, 9)
    engine.repo.upsert_progress(
        engine.user_id,
        unit_id="u1",
        status="review",
        times_completed=3,
        last_completed=date(2026, 9, 5),
        next_revision=date(2026, 9, 12),
        interval_days=7,
    )
    engine.mark_all_modes_seen("u1")
    engine.complete_revision_early("u1", as_of=today)
    assert engine.modes_seen("u1") == set()
    assert engine.get_progress("u1").next_revision == date(2026, 9, 27)


def _split_catalog() -> list[LearningUnit]:
    parent = LearningUnit(
        id="parent-x",
        type=LearningUnitType.CLAUSE,
        article_number="14",
        display_title="Article 14",
        text="Parent X whole text.",
        estimated_learning_time=60,
        revision_order=1,
        tags=["Part III"],
        allows_letter_split=True,
        child_unit_ids=["x-a", "x-b"],
    )
    child_a = LearningUnit(
        id="x-a",
        type=LearningUnitType.SUBCLAUSE,
        parent_id="parent-x",
        parent_clause_id="parent-x",
        article_number="14",
        display_title="Article 14(a)",
        text="Letter a.",
        estimated_learning_time=60,
        revision_order=2,
        tags=["Part III"],
    )
    child_b = LearningUnit(
        id="x-b",
        type=LearningUnitType.SUBCLAUSE,
        parent_id="parent-x",
        parent_clause_id="parent-x",
        article_number="14",
        display_title="Article 14(b)",
        text="Letter b.",
        estimated_learning_time=60,
        revision_order=3,
        tags=["Part III"],
    )
    fillers = _catalog(40)
    return [parent, child_a, child_b, *fillers]


def test_letters_preference_removes_future_parent(tmp_path: Path):
    engine = ReminderEngine.from_units(tmp_path / "progress.db", _split_catalog())
    today = date(2026, 9, 1)
    engine.set_split_preference("parent-x", "whole")
    _reconcile(engine, today, target=3)
    future = today + timedelta(days=2)
    while future <= roadmap_horizon(today) and not _ids_on(engine, future):
        future += timedelta(days=1)
    # parent-x plus two companions that are not parent-x. Prepending it to a
    # raw slice duplicated it whenever the planner had already put it on this
    # day, which auto_plan_item's UNIQUE constraint then rejected.
    companions = [uid for uid in _ids_on(engine, future) if uid != "parent-x"][:2]
    planted = ["parent-x", *(companions or ["u1", "u2"])]
    assert len(planted) == len(set(planted))
    engine.replace_auto_plan_day(future, 3, planted)
    assert "parent-x" in _ids_on(engine, future)
    past = today - timedelta(days=1)
    engine.replace_auto_plan_day(past, 3, ["parent-x"])
    engine.create_study_session(
        session_id="hist-parent",
        kind="auto_learning",
        plan_date=past,
        unit_ids=["parent-x"],
    )
    engine.complete_study_session("hist-parent")
    historical = engine.list_auto_plan_day(past)
    engine.set_split_preference("parent-x", "letters")
    _reconcile(engine, today, target=3)
    future_ids = [
        item.learning_unit_id
        for day in engine.list_auto_plan_window(
            today + timedelta(days=1), roadmap_horizon(today)
        )
        for item in day.items
    ]
    assert "parent-x" not in future_ids
    children = {"x-a", "x-b"}
    present_children = children & set(future_ids)
    assert not ({"parent-x"} & present_children)
    kept = engine.list_auto_plan_day(past)
    assert kept is not None
    assert [item.learning_unit_id for item in kept.items] == [
        item.learning_unit_id for item in historical.items
    ]
    hist_session = engine.study_session_for_day(kind="auto_learning", plan_date=past)
    assert [item.learning_unit_id for item in hist_session.items] == ["parent-x"]


def test_whole_preference_restores_future_parent_visibility(tmp_path: Path):
    engine = ReminderEngine.from_units(tmp_path / "progress.db", _split_catalog())
    today = date(2026, 9, 1)
    engine.set_split_preference("parent-x", "letters")
    _reconcile(engine, today, target=3)
    future_ids = _window_ids(engine, today)
    assert "parent-x" not in future_ids
    engine.set_split_preference("parent-x", "whole")
    _reconcile(engine, today, target=3)
    restored = _window_ids(engine, today)
    children = {"x-a", "x-b"}
    assert not (children & set(restored)) or "parent-x" not in restored
    # Whole mode: parent is mix-eligible; letter children are not visible.
    for unit_id in restored:
        unit = engine.get_unit(unit_id)
        assert unit is not None
        if unit.type == LearningUnitType.SUBCLAUSE:
            raise AssertionError(unit_id)


def test_hypothetical_reviews_do_not_leak_beyond_window(tmp_path: Path):
    engine = _engine(tmp_path)
    today = date(2026, 9, 1)
    _reconcile(engine, today, target=3)
    window_end = roadmap_horizon(today)
    beyond = today + timedelta(days=15)
    assert beyond > window_end
    planned = LearningPlanner().project(
        engine,
        engine.get_learning_plan(),
        as_of=today,
        until=date(2026, 12, 31),
        remaining_unseen=80,
        auto_entitled=True,
    )
    by_day = {day.day: day for day in planned}
    # +15 rung from a Sep 1 NEW lands on Sep 27 — outside the 15-day window.
    leak = date(2026, 9, 27)
    assert leak > window_end
    assert by_day[leak].kind != "review"
    view = build_calendar_month(
        engine, year=2026, month=9, today=today, auto_entitled=True
    )
    day27 = next(d for d in view.days if d.day == 27)
    assert not any("projected review" in (chip.title or "") for chip in day27.chips)
    engine.repo.upsert_progress(
        engine.user_id,
        unit_id="u80",
        status="review",
        times_completed=1,
        last_completed=today,
        next_revision=leak,
        interval_days=15,
    )
    engine._invalidate_progress_cache()
    planned_after = LearningPlanner().project(
        engine,
        engine.get_learning_plan(),
        as_of=today,
        until=date(2026, 12, 31),
        remaining_unseen=80,
        auto_entitled=True,
    )
    after = {day.day: day for day in planned_after}
    assert after[leak].kind == "review"
    assert after[leak].review_count >= 1
    view_after = build_calendar_month(
        engine, year=2026, month=9, today=today, auto_entitled=True
    )
    day27_after = next(d for d in view_after.days if d.day == 27)
    assert any(chip.kind in {"scheduled", "due"} for chip in day27_after.chips)
    assert not any(
        "projected review" in (chip.title or "") for chip in day27_after.chips
    )


def test_empty_review_day_is_not_stale(tmp_path: Path):
    engine = _engine(tmp_path)
    today = date(2026, 9, 1)
    _reconcile(engine, today, target=3)
    first = _ids_on(engine, today)[0]
    engine.mark_all_modes_seen(first)
    engine.mark_done(first, as_of=today, require_all_modes=True)
    _reconcile(engine, today, target=3)
    plus_one = today + timedelta(days=1)
    assert _ids_on(engine, plus_one) == []
    assert engine.list_auto_plan_day(plus_one) is not None
    assert (
        auto_roadmap_needs_reconcile(
            engine,
            engine.get_learning_plan(),
            as_of=today,
            auto_entitled=True,
        )
        is False
    )


def test_calendar_get_is_idempotent_when_current(tmp_path: Path):
    db = tmp_path / "progress.db"
    client = TestClient(
        create_app(units_path=MINI_UNITS, db_path=db, multiuser=False)
    )
    eng = client.app.state.engine
    today = user_today(eng)
    eng.upsert_learning_plan(mode="auto", daily_target=3, as_of=today)
    reconcile_auto_roadmap(
        eng,
        eng.get_learning_plan(),
        as_of=today,
        auto_entitled=True,
        claimed=set(),
        remaining_slots=99,
        entitlements_on=False,
    )
    first = _ids_on(eng, today)
    if first:
        eng.mark_all_modes_seen(first[0])
        eng.mark_done(first[0], as_of=today, require_all_modes=True)
        reconcile_auto_roadmap(
            eng,
            eng.get_learning_plan(),
            as_of=today,
            auto_entitled=True,
            claimed=set(),
            remaining_slots=99,
            entitlements_on=False,
        )
    plus_one = today + timedelta(days=1)
    assert eng.list_auto_plan_day(plus_one) is not None
    before = _fingerprint(eng, today)
    first_get = client.get("/calendar")
    assert first_get.status_code == 200
    mid = _fingerprint(eng, today)
    second_get = client.get("/calendar")
    assert second_get.status_code == 200
    after = _fingerprint(eng, today)
    assert before == mid == after


def test_dashboard_get_is_idempotent_when_current(tmp_path: Path):
    clear_settings_cache()
    db = tmp_path / "progress.db"
    client = TestClient(
        create_app(
            units_path=MINI_UNITS,
            db_path=db,
            multiuser=True,
            multiuser_settings=MultiUserSettings(
                _env_file=None,
                APP_ENV="test",
                MULTIUSER_ENABLED="true",
                AUTH_GOOGLE_ENABLED="true",
                AUTH_PHONE_ENABLED="true",
                SESSION_SECRET="test-secret",
                SUPABASE_URL="http://example.invalid",
                SUPABASE_ANON_KEY="anon",
                DATABASE_URL="",
                COOKIE_SECURE="false",
            ),
            auth_provider=FakeAuthProvider(),
            session_store=InMemorySessionStore(),
        )
    )
    start = client.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state")
    client.get(
        f"/auth/callback?code=fake-google-code&state={state}", follow_redirects=False
    )
    store = client.app.state.session_store
    user_id = sorted(store._sessions.values(), key=lambda s: s.created_at)[-1].user.id
    eng = client.app.state.engine.for_user(user_id)
    today = user_today(eng)
    eng.upsert_learning_plan(mode="auto", daily_target=3, as_of=today)
    reconcile_auto_roadmap(
        eng,
        eng.get_learning_plan(),
        as_of=today,
        auto_entitled=True,
        claimed=set(),
        remaining_slots=99,
        entitlements_on=False,
    )
    before = _fingerprint(eng, today)
    first_get = client.get("/dashboard")
    assert first_get.status_code == 200
    mid = _fingerprint(eng, today)
    second_get = client.get("/dashboard")
    assert second_get.status_code == 200
    after = _fingerprint(eng, today)
    assert before == mid == after


def test_day_rollover_extends_horizon_once(tmp_path: Path):
    engine = _engine(tmp_path)
    day0 = date(2026, 9, 1)
    _reconcile(engine, day0, target=3)
    plan = engine.get_learning_plan()
    assert (
        auto_roadmap_needs_reconcile(
            engine, plan, as_of=day0, auto_entitled=True
        )
        is False
    )
    day1 = day0 + timedelta(days=1)
    assert (
        auto_roadmap_needs_reconcile(
            engine, plan, as_of=day1, auto_entitled=True
        )
        is True
    )
    ensure_auto_roadmap(
        engine,
        as_of=day1,
        auto_entitled=True,
        claimed=set(),
        remaining_slots=99,
        entitlements_on=False,
        force=False,
    )
    assert engine.list_auto_plan_day(day0) is not None
    assert engine.list_auto_plan_day(roadmap_horizon(day1)) is not None
    assert engine.list_auto_plan_day(roadmap_horizon(day1) + timedelta(days=1)) is None
    assert (
        auto_roadmap_needs_reconcile(
            engine, engine.get_learning_plan(), as_of=day1, auto_entitled=True
        )
        is False
    )
    before = _fingerprint(engine, day1)
    ensure_auto_roadmap(
        engine,
        as_of=day1,
        auto_entitled=True,
        claimed=set(),
        remaining_slots=99,
        entitlements_on=False,
        force=False,
    )
    assert _fingerprint(engine, day1) == before


def test_done_survives_schema_0014_without_roadmap_column(tmp_path: Path):
    db = tmp_path / "progress.db"
    client = TestClient(
        create_app(units_path=MINI_UNITS, db_path=db, multiuser=False)
    )
    eng = client.app.state.engine
    today = user_today(eng)
    eng.upsert_learning_plan(mode="auto", daily_target=3, as_of=today)
    _downgrade_to_schema_0014(eng.repo.conn)
    complete_all_modes(client, MINI_UNITS, "clause-1")
    resp = client.post("/learn/clause-1/done", follow_redirects=False)
    assert resp.status_code == 303
    progress = eng.get_progress("clause-1")
    assert progress is not None
    assert progress.times_completed >= 1
    assert progress.last_completed == today
    cols = [
        str(row[1])
        for row in eng.repo.conn.execute("PRAGMA table_info(user_learning_plan)")
    ]
    assert "target_effective_on" not in cols



# ── Recall Mix on the Auto path ─────────────────────────────────────────────
#
# Auto used to fill each day straight from the carryover queue and only call
# the selector for whatever capacity was left over — passing the full target as
# the quota and then truncating. A day was therefore a queue prefix plus a
# truncated mix, never a composed one. These pin the fix.

from constitution_memorizer.planner.graph import CuratedRelationshipGraph  # noqa: E402
from constitution_memorizer.planner.relationships import build_candidate  # noqa: E402
from constitution_memorizer.planner.selector import classify  # noqa: E402


def _banded_graph() -> CuratedRelationshipGraph:
    """Articles 101-140 in three curated clusters, so bands are legible."""
    meta = {}
    for i in range(1, 81):
        article = str(100 + i)
        cluster = "alpha" if i <= 20 else ("beta" if i <= 40 else "gamma")
        meta[article] = {"primary_cluster": cluster, "clusters": [cluster]}
    return CuratedRelationshipGraph(
        {
            "families": {"core": {"label": "Core"}},
            "clusters": {
                "alpha": {
                    "family": "core",
                    "same_cluster_bucket": "close",
                    "related_clusters": ["beta"],
                    "explore_clusters": ["gamma"],
                },
                "beta": {
                    "family": "core",
                    "same_cluster_bucket": "close",
                    "related_clusters": ["alpha"],
                    "explore_clusters": ["gamma"],
                },
                "gamma": {
                    "family": None,
                    "same_cluster_bucket": "close",
                    "related_clusters": ["beta"],
                    "explore_clusters": ["alpha"],
                },
            },
            "article_metadata": meta,
            "unit_metadata": {},
            "article_edges": [],
            "unit_edges": [],
        }
    )


def _day_buckets(engine: ReminderEngine, day: date, graph) -> dict[str, int]:
    ids = _ids_on(engine, day)
    assert ids, f"no plan for {day}"
    anchor = build_candidate(engine.units[ids[0]])
    counts: dict[str, int] = {}
    for unit_id in ids[1:]:
        pick = classify(anchor, build_candidate(engine.units[unit_id]), graph=graph)
        key = pick.effective_bucket or "unclassified"
        counts[key] = counts.get(key, 0) + 1
    return counts


def test_auto_day_is_a_composed_mix(tmp_path: Path, monkeypatch):
    """Today's Auto day is anchor + 2 close + 1 related + 1 explore."""
    graph = _banded_graph()
    monkeypatch.setattr(
        "constitution_memorizer.planner.selector.curated_graph", lambda *a, **k: graph
    )
    engine = _engine(tmp_path)
    today = date(2026, 9, 3)
    _reconcile(engine, today, target=5)
    assert _day_buckets(engine, today, graph) == {"close": 2, "related": 1, "explore": 1}


def test_carryover_leads_the_day_and_nothing_is_dropped(tmp_path: Path):
    """Owed work keeps its place at the head of the day.

    Composition *around* a partial carryover is pinned in
    test_learning_selector.py, at the level where it can be constructed: with
    a real pool the carryover queue is normally deeper than the daily target,
    so a day is either entirely owed work or entirely fresh, and the composed
    middle case is rare. What this holds is the part that always applies —
    the oldest commitment leads, the day never exceeds target, and re-planning
    loses nothing.
    """
    engine = _engine(tmp_path)
    today = date(2026, 9, 3)
    _reconcile(engine, today, target=5)
    first_day = _ids_on(engine, today)
    assert len(first_day) == 5

    tomorrow = today + timedelta(days=1)
    _reconcile(engine, tomorrow, target=5)
    carried = _ids_on(engine, tomorrow)
    assert len(carried) == 5
    # Position 0 is the oldest commitment — which is what makes the persisted
    # anchor theme the day's real anchor.
    assert carried[0] in first_day
    # Re-planning re-flows the window; it never silently discards owed units.
    assert set(first_day) <= set(_window_ids(engine, tomorrow))


def test_auto_day_does_not_double_spend_the_free_article_cap(tmp_path: Path):
    """Carryover is checked against the slot policy, not trusted.

    _window_unit_eligible only knows whether *a* Free slot remains; it cannot
    count how many distinct new Articles a day has already introduced. Trusting
    the queue therefore let one day spend the cap twice.
    """
    engine = _engine(tmp_path)
    today = date(2026, 9, 3)

    def _run(as_of: date) -> None:
        plan = engine.get_learning_plan()
        if not plan.is_auto:
            engine.upsert_learning_plan(mode="auto", daily_target=5, as_of=as_of)
            plan = engine.get_learning_plan()
        reconcile_auto_roadmap(
            engine,
            plan,
            as_of=as_of,
            auto_entitled=True,
            claimed=set(),
            remaining_slots=1,
            entitlements_on=True,
        )

    # The first reconcile has an empty queue, so the selector's allow policy
    # was always applied. The leak is on the *second*: the queue is populated,
    # and the old code drained it without counting distinct Articles.
    _run(today)
    tomorrow = today + timedelta(days=1)
    _run(tomorrow)
    articles = {
        engine.units[unit_id].article_number for unit_id in _ids_on(engine, tomorrow)
    }
    assert len(articles) <= 1, articles


def test_reconcile_does_not_persist_the_projected_theme_chain(tmp_path: Path):
    """The projection's recency chain is in-memory on purpose.

    Reconcile runs on ordinary reads. Persisting day 12's hypothetical anchor
    would let anchor input drift on GET traffic and make the window
    non-deterministic. Only a started session records an anchor.
    """
    engine = _engine(tmp_path)
    today = date(2026, 9, 3)
    _reconcile(engine, today, target=5)
    before = engine.get_learning_plan().last_anchor_theme
    first = _fingerprint(engine, today)
    _reconcile(engine, today, target=5)
    assert engine.get_learning_plan().last_anchor_theme == before
    assert _fingerprint(engine, today) == first
