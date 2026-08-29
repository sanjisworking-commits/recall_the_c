"""Planner read-bundle: Dashboard/Calendar must not repeat plan/session/window reads."""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import InMemorySessionStore
from constitution_memorizer.learning.schemas import LearningUnitsDocument
from constitution_memorizer.multiuser.settings import MultiUserSettings, clear_settings_cache
from constitution_memorizer.planner.planner import LearningPlanner
from constitution_memorizer.planner.roadmap import reconcile_auto_roadmap, roadmap_horizon
from constitution_memorizer.progress.db import open_progress_db
from constitution_memorizer.progress.repository import ProgressRepository
from constitution_memorizer.progress.scheduler import ReminderEngine
from constitution_memorizer.utils.json_io import read_json
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.request_context import (
    begin_request_timings,
    record_request_timing,
    reset_request_timings,
    snapshot_request_timings,
)
from constitution_memorizer.web.dashboard import build_dashboard_context
from constitution_memorizer.web.calendar_view import build_calendar_month

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
USER = UUID("11111111-1111-4111-8111-111111111111")
USER_EMAIL = "planner-perf@example.com"


class CountingPlannerRepo:
    """Counts planner repository reads. Other methods pass through."""

    def __init__(self, inner: ProgressRepository) -> None:
        self.inner = inner
        self.reset_counts()

    def __getattr__(self, name: str):
        return getattr(self.inner, name)

    def reset_counts(self) -> None:
        self.load_planner_read_bundle_calls = 0
        self.get_learning_plan_calls = 0
        self.study_session_for_day_calls = 0
        self.study_sessions_for_day_calls = 0
        self.active_study_session_calls = 0
        self.list_auto_plan_window_calls = 0
        self.list_daily_goal_dates_calls = 0

    def load_planner_read_bundle(self, user_id, **kwargs):
        self.load_planner_read_bundle_calls += 1
        return self.inner.load_planner_read_bundle(user_id, **kwargs)

    def get_learning_plan(self, user_id):
        self.get_learning_plan_calls += 1
        return self.inner.get_learning_plan(user_id)

    def study_session_for_day(self, user_id, **kwargs):
        self.study_session_for_day_calls += 1
        return self.inner.study_session_for_day(user_id, **kwargs)

    def study_sessions_for_day(self, user_id, plan_date):
        self.study_sessions_for_day_calls += 1
        return self.inner.study_sessions_for_day(user_id, plan_date)

    def active_study_session(self, user_id, **kwargs):
        self.active_study_session_calls += 1
        return self.inner.active_study_session(user_id, **kwargs)

    def list_auto_plan_window(self, user_id, start, until):
        self.list_auto_plan_window_calls += 1
        return self.inner.list_auto_plan_window(user_id, start, until)

    def list_daily_goal_dates(self, user_id, **kwargs):
        self.list_daily_goal_dates_calls += 1
        return self.inner.list_daily_goal_dates(user_id, **kwargs)


@pytest.fixture(autouse=True)
def _clear_settings():
    clear_settings_cache()
    yield
    clear_settings_cache()


def _settings(**overrides) -> MultiUserSettings:
    base = {
        "APP_ENV": "test",
        "MULTIUSER_ENABLED": "true",
        "AUTH_GOOGLE_ENABLED": "true",
        "AUTH_PHONE_ENABLED": "true",
        "SESSION_SECRET": "test-secret",
        "SUPABASE_URL": "http://example.invalid",
        "SUPABASE_ANON_KEY": "anon",
        "DATABASE_URL": "",
        "COOKIE_SECURE": "false",
    }
    base.update({k: str(v) for k, v in overrides.items()})
    return MultiUserSettings(_env_file=None, **base)


def _units():
    return {
        unit.id: unit
        for unit in LearningUnitsDocument.model_validate(read_json(MINI_UNITS)).units
    }


def _engine_with_repo(repo: CountingPlannerRepo) -> ReminderEngine:
    return ReminderEngine.from_repository(repo, _units(), user_id=USER)


def _counting_client(tmp_path: Path) -> tuple[TestClient, CountingPlannerRepo, ReminderEngine]:
    conn = open_progress_db(tmp_path / "progress.db")
    repo = CountingPlannerRepo(ProgressRepository(conn))
    provider = FakeAuthProvider()
    provider.seed_google_user(
        user_id=USER,
        email=USER_EMAIL,
        display_name="Test User",
    )
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "unused.db",
        multiuser=True,
        multiuser_settings=_settings(),
        auth_provider=provider,
        session_store=InMemorySessionStore(),
        progress_repo=repo,
    )
    client = TestClient(app)
    start = client.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state")
    cb = client.get(
        f"/auth/callback?code=fake-google-code&state={state}",
        follow_redirects=False,
    )
    assert cb.status_code == 303
    repo.reset_counts()
    engine = app.state.engine.for_user(USER)
    return client, repo, engine


def _seed_fresh_auto(engine: ReminderEngine, as_of: date) -> None:
    engine.upsert_learning_plan(mode="auto", daily_target=3, as_of=as_of)
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


def test_study_sessions_for_day_returns_all_kinds(tmp_path: Path):
    conn = open_progress_db(tmp_path / "progress.db")
    repo = ProgressRepository(conn)
    today = date(2026, 8, 28)
    repo.create_study_session(
        USER,
        session_id="rev1",
        kind="revision",
        plan_date=today,
        unit_ids=["clause-1"],
    )
    repo.create_study_session(
        USER,
        session_id="auto1",
        kind="auto_learning",
        plan_date=today,
        unit_ids=["clause-2"],
    )
    sessions = repo.study_sessions_for_day(USER, today)
    assert set(sessions) == {"revision", "auto_learning", "day_plan"}
    assert sessions["revision"] is not None
    assert sessions["auto_learning"] is not None
    assert sessions["day_plan"] is None
    assert sessions["revision"].id == "rev1"


def test_project_fetches_today_auto_session_once(tmp_path: Path):
    conn = open_progress_db(tmp_path / "progress.db")
    repo = CountingPlannerRepo(ProgressRepository(conn))
    engine = _engine_with_repo(repo)
    today = date(2026, 8, 28)
    _seed_fresh_auto(engine, today)
    repo.reset_counts()
    LearningPlanner().project(
        engine,
        engine.get_learning_plan(),
        as_of=today,
        until=today,
        remaining_unseen=10,
        auto_entitled=True,
    )
    assert repo.study_session_for_day_calls <= 1


def test_dashboard_normal_auto_uses_one_planner_bundle(tmp_path: Path):
    client, repo, engine = _counting_client(tmp_path)
    today = date.today()
    _seed_fresh_auto(engine, today)
    repo.reset_counts()
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert repo.load_planner_read_bundle_calls == 1
    assert repo.get_learning_plan_calls == 0
    assert repo.study_session_for_day_calls == 0
    assert repo.study_sessions_for_day_calls == 0
    assert repo.active_study_session_calls == 0
    assert repo.list_auto_plan_window_calls == 0
    assert repo.list_daily_goal_dates_calls == 0


def test_calendar_reuses_planner_snapshot(tmp_path: Path):
    client, repo, engine = _counting_client(tmp_path)
    today = date.today()
    _seed_fresh_auto(engine, today)
    repo.reset_counts()
    resp = client.get("/calendar")
    assert resp.status_code == 200
    assert repo.load_planner_read_bundle_calls == 1
    assert repo.get_learning_plan_calls == 0
    assert repo.study_session_for_day_calls == 0
    assert repo.list_auto_plan_window_calls == 0


def test_dashboard_breakdown_includes_planner_stages(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    client, repo, engine = _counting_client(tmp_path)
    today = date.today()
    _seed_fresh_auto(engine, today)
    repo.reset_counts()
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        caplog.clear()
        resp = client.get("/dashboard")
    assert resp.status_code == 200
    lines = [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("request_breakdown ")
    ]
    assert lines
    line = lines[0]
    assert "learning_plan_read_n=1" in line
    assert "study_sessions_read_n=1" in line
    assert "auto_plan_read_n=1" in line
    assert "daily_goal_read_n=1" in line
    assert "learning_plan_reads=1" in line
    assert "study_session_reads=1" in line
    assert "auto_plan_reads=1" in line
    assert "daily_goal_reads=1" in line
    assert "db_reads=" in line


def test_build_dashboard_context_does_not_repeat_plan_reads(tmp_path: Path):
    conn = open_progress_db(tmp_path / "progress.db")
    repo = CountingPlannerRepo(ProgressRepository(conn))
    engine = _engine_with_repo(repo)
    today = date.today()
    _seed_fresh_auto(engine, today)
    repo.reset_counts()
    ctx = build_dashboard_context(engine, display_label="Priya", as_of=today)
    assert ctx["plan_mode"] == "auto"
    assert repo.load_planner_read_bundle_calls == 1
    assert repo.get_learning_plan_calls == 0
    assert repo.study_session_for_day_calls == 0
    assert repo.list_auto_plan_window_calls == 0


def test_build_calendar_month_does_not_repeat_window_reads(tmp_path: Path):
    conn = open_progress_db(tmp_path / "progress.db")
    repo = CountingPlannerRepo(ProgressRepository(conn))
    engine = _engine_with_repo(repo)
    today = date.today()
    _seed_fresh_auto(engine, today)
    repo.reset_counts()
    build_calendar_month(
        engine, year=today.year, month=today.month, today=today, auto_entitled=True
    )
    assert repo.load_planner_read_bundle_calls == 1
    assert repo.list_auto_plan_window_calls == 0
    assert repo.study_session_for_day_calls == 0


def test_new_planner_timing_stages_are_whitelisted():
    token = begin_request_timings()
    try:
        for stage in (
            "learning_plan_read",
            "study_sessions_read",
            "auto_plan_read",
            "roadmap_freshness",
            "planner_project",
            "daily_goal_read",
            "calendar_build",
        ):
            record_request_timing(stage, 0.0)
        snapshot = snapshot_request_timings()
        assert snapshot["planner_project"][1] == 1
        assert snapshot["calendar_build"][1] == 1
    finally:
        reset_request_timings(token)


def test_roadmap_horizon_covers_persisted_new_window():
    today = date(2026, 8, 28)
    assert (roadmap_horizon(today) - today).days == 14
