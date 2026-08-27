"""New-learning sessions: Skip, stale links, activation, create-or-get."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import InMemorySessionStore
from constitution_memorizer.multiuser.settings import MultiUserSettings, clear_settings_cache
from constitution_memorizer.progress.scheduler import ReminderEngine
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.completion import session_entry_mode, with_params
from constitution_memorizer.web.dashboard import build_dashboard_context

from tests.quiz_helpers import complete_all_modes

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"


def _client(tmp_path: Path, *, multiuser: bool = False) -> TestClient:
    kwargs: dict = {
        "units_path": MINI_UNITS,
        "db_path": tmp_path / "progress.db",
        "multiuser": multiuser,
    }
    if multiuser:
        clear_settings_cache()
        kwargs["multiuser_settings"] = MultiUserSettings(
            _env_file=None,
            APP_ENV="test",
            MULTIUSER_ENABLED="true",
            AUTH_GOOGLE_ENABLED="true",
            SESSION_SECRET="test-secret",
            SUPABASE_URL="http://example.invalid",
            SUPABASE_ANON_KEY="anon",
            DATABASE_URL="",
            COOKIE_SECURE="false",
        )
        kwargs["auth_provider"] = FakeAuthProvider()
        kwargs["session_store"] = InMemorySessionStore()
    return TestClient(create_app(**kwargs))


def _engine(client: TestClient) -> ReminderEngine:
    engine = client.app.state.engine
    store = getattr(client.app.state, "session_store", None)
    sessions = getattr(store, "_sessions", None) if store is not None else None
    if sessions:
        newest = sorted(sessions.values(), key=lambda s: s.created_at)[-1]
        return engine.for_user(newest.user.id)
    return engine


def _session_of(location: str) -> str:
    return parse_qs(urlsplit(location).query).get("session", [""])[0]


def _start_day_plan(client: TestClient, target: int = 3) -> tuple[str, str]:
    resp = client.post("/learning/plan-my-day", data={"target": target}, follow_redirects=False)
    assert resp.status_code == 303, resp.text
    parts = urlsplit(resp.headers["location"])
    session_id = parse_qs(parts.query).get("session", [""])[0]
    path = parts.path.removesuffix("/choose")
    return session_id, path.rsplit("/", 1)[-1]


def test_skip_on_unlearned_item_does_not_write_review_progress(tmp_path: Path):
    client = _client(tmp_path)
    eng = _engine(client)
    session = eng.create_study_session(
        session_id="day-mix",
        kind="day_plan",
        plan_date=date.today(),
        unit_ids=["clause-1", "article-end"],
    )
    before = eng.get_progress("clause-1")
    assert before is None or before.status == "new"

    page = client.get(f"/learn/clause-1?session={session.id}")
    assert page.status_code == 200
    assert "Skip for today" in page.text
    assert "Again tomorrow" not in page.text

    skip = client.post(
        with_params("/learn/clause-1/skip", {"session": session.id}),
        follow_redirects=False,
    )
    assert skip.status_code == 303
    after = eng.get_progress("clause-1")
    assert after is None or (
        after.status == "new"
        and after.times_completed == 0
        and after.next_revision is None
    )
    refreshed = eng.get_study_session(session.id)
    assert refreshed is not None
    item = refreshed.item_for("clause-1")
    assert item is not None
    assert item.status == "deferred"


def test_yesterday_session_cannot_drive_todays_navigation(tmp_path: Path):
    client = _client(tmp_path)
    eng = _engine(client)
    yesterday = date.today() - timedelta(days=1)
    stale = eng.create_study_session(
        session_id="yesterday-mix",
        kind="day_plan",
        plan_date=yesterday,
        unit_ids=["clause-1", "clause-2"],
    )
    page = client.get(f"/learn/clause-1?session={stale.id}")
    assert page.status_code == 200
    assert 'data-session-id="yesterday-mix"' not in page.text
    assert "Learning 1 of" not in page.text
    assert "Skip for today" not in page.text
    assert "Again tomorrow" in page.text

    complete_all_modes(client, MINI_UNITS, "clause-1")
    done = client.post(
        with_params("/learn/clause-1/done", {"session": stale.id}),
        follow_redirects=False,
    )
    assert done.status_code == 303
    location = done.headers["location"]
    assert _session_of(location) == ""
    refreshed = eng.get_study_session(stale.id)
    assert refreshed is not None
    assert refreshed.item_for("clause-1").status == "pending"


def test_activated_at_is_not_written_on_start(tmp_path: Path):
    client = _client(tmp_path)
    eng = _engine(client)
    eng.upsert_learning_plan(mode="auto", daily_target=3)
    assert eng.get_learning_plan().activated_at is None

    start = client.post("/learning/start", follow_redirects=False)
    assert start.status_code == 303
    assert eng.get_learning_plan().activated_at is None
    parts = urlsplit(start.headers["location"])
    session_id = parse_qs(parts.query).get("session", [""])[0]
    first = parts.path.removesuffix("/choose").rsplit("/", 1)[-1]
    assert session_id

    complete_all_modes(client, MINI_UNITS, first)
    client.post(
        with_params(f"/learn/{first}/done", {"session": session_id}),
        follow_redirects=False,
    )
    plan = eng.get_learning_plan()
    assert plan.activated_at == date.today()


def test_create_or_get_conflict_returns_one_session(tmp_path: Path):
    engine = ReminderEngine.from_paths(tmp_path / "progress.db", MINI_UNITS)
    today = date.today()
    first = engine.create_study_session(
        session_id="winner",
        kind="day_plan",
        plan_date=today,
        unit_ids=["clause-1", "article-end"],
    )
    loser = engine.create_study_session(
        session_id="loser",
        kind="day_plan",
        plan_date=today,
        unit_ids=["clause-2"],
    )
    assert loser.id == first.id
    assert [item.learning_unit_id for item in loser.items] == ["clause-1", "article-end"]
    assert engine.get_study_session("loser") is None


def test_revision_completed_copy_excludes_manual_new_learning(tmp_path: Path):
    client = _client(tmp_path)
    eng = _engine(client)
    today = date.today()
    session = eng.create_study_session(
        session_id="rev-today",
        kind="revision",
        plan_date=today,
        unit_ids=["clause-1", "article-end"],
    )
    eng.set_study_item_status(
        session_id=session.id, unit_id="clause-1", status="completed"
    )
    eng.set_study_item_status(
        session_id=session.id, unit_id="article-end", status="deferred"
    )
    eng.complete_study_session(session.id)
    eng.mark_all_modes_seen("clause-1")
    eng.mark_done("clause-1", as_of=today)
    eng.mark_all_modes_seen("clause-2")
    eng.mark_done("clause-2", as_of=today)

    ctx = build_dashboard_context(eng, display_label="Priya", as_of=today)
    assert ctx["revision_completed_today"] == 1
    assert ctx["completed_today"] >= 2
    assert ctx["revision_completed_today"] != ctx["completed_today"]


def test_session_entry_mode_is_kind_generic():
    assert session_entry_mode("revision") == "read"
    assert session_entry_mode("auto_learning") == "read"
    assert session_entry_mode("day_plan") == "read"


def test_plan_my_day_creates_a_same_day_session(tmp_path: Path):
    client = _client(tmp_path)
    session_id, first = _start_day_plan(client, target=3)
    assert session_id
    session = _engine(client).get_study_session(session_id)
    assert session is not None
    assert session.kind == "day_plan"
    assert session.plan_date == date.today()
    assert first in {item.learning_unit_id for item in session.items}


def test_learn_start_does_not_create_on_get(tmp_path: Path):
    client = _client(tmp_path)
    client.get("/learn/clause-1")
    client.get("/learn/clause-1?flow=auto")
    eng = _engine(client)
    assert eng.active_study_session(kind="auto_learning", plan_date=date.today()) is None
    assert eng.active_study_session(kind="day_plan", plan_date=date.today()) is None
