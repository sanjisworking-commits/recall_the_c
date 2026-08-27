"""Rolling 15-day Auto roadmap: occupancy, compaction, early revision, entitlements."""

from __future__ import annotations

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
from constitution_memorizer.web.service import user_today

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
    assert c in _window_ids(engine, today)
    progress_c = engine.get_progress(c)
    assert progress_c is None or progress_c.times_completed == 0


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
