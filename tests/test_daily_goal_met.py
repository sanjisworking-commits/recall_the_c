"""daily_goal_met facts: written only when the required path is genuinely done.

Streak is derived from consecutive goal_date rows. Distinct from day_streak(),
which counts any completion date on progress rows. Schema-gap degrades.
"""

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
from constitution_memorizer.web.completion import with_params
from constitution_memorizer.web.dashboard import day_streak
from constitution_memorizer.web.service import (
    daily_goal_streak,
    maybe_record_daily_goal_met,
)

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


def _sign_in(client: TestClient) -> None:
    start = client.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state")
    client.get(
        f"/auth/callback?code=fake-google-code&state={state}",
        follow_redirects=False,
    )


def _engine(client: TestClient) -> ReminderEngine:
    engine = client.app.state.engine
    store = getattr(client.app.state, "session_store", None)
    sessions = getattr(store, "_sessions", None) if store is not None else None
    if sessions:
        newest = sorted(sessions.values(), key=lambda s: s.created_at)[-1]
        return engine.for_user(newest.user.id)
    return engine


def _make_due(client: TestClient, unit_ids: list[str]) -> None:
    eng = _engine(client)
    today = date.today()
    for offset, unit_id in enumerate(unit_ids):
        eng.repo.upsert_progress(
            eng.user_id,
            unit_id=unit_id,
            status="review",
            times_completed=1,
            last_completed=today - timedelta(days=1),
            next_revision=today - timedelta(days=len(unit_ids) - offset),
            interval_days=1,
        )
    eng._invalidate_progress_cache()


def _start(client: TestClient) -> tuple[str, str]:
    resp = client.post("/revision/start", follow_redirects=False)
    assert resp.status_code == 303, resp.text
    parts = urlsplit(resp.headers["location"])
    session_id = parse_qs(parts.query).get("session", [""])[0]
    path = parts.path.removesuffix("/choose")
    return session_id, path.rsplit("/", 1)[-1]


def _finish(client: TestClient, unit_id: str, session_id: str = "") -> str:
    complete_all_modes(client, MINI_UNITS, unit_id)
    action = with_params(f"/learn/{unit_id}/done", {"session": session_id})
    resp = client.post(action, follow_redirects=False)
    assert resp.status_code == 303, resp.text
    return resp.headers["location"]


def _goal_count(eng: ReminderEngine) -> int:
    row = eng.repo.conn.execute(
        "SELECT COUNT(*) AS n FROM daily_goal_met"
    ).fetchone()
    return int(row["n"])


def _drop_daily_goal_table(client: TestClient) -> None:
    conn = _engine(client).repo.conn
    conn.execute("DROP TABLE IF EXISTS daily_goal_met")
    conn.commit()


def test_sqlite_mirror_creates_daily_goal_met(tmp_path: Path):
    client = _client(tmp_path)
    eng = _engine(client)
    row = eng.repo.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='daily_goal_met'"
    ).fetchone()
    assert row is not None
    columns = {
        info["name"]
        for info in eng.repo.conn.execute("PRAGMA table_info(daily_goal_met)").fetchall()
    }
    assert columns == {"user_id", "goal_date", "met_at"}


def test_completing_every_revision_item_records_one_fact(tmp_path: Path):
    client = _client(tmp_path)
    eng = _engine(client)
    _make_due(client, ["clause-1", "article-end"])
    session_id, first = _start(client)
    assert first == "clause-1"
    _finish(client, "clause-1", session_id)
    assert _goal_count(eng) == 0
    assert not eng.is_daily_goal_met(date.today())

    location = _finish(client, "article-end", session_id)
    assert urlsplit(location).path in ("/", "/dashboard")
    assert _goal_count(eng) == 1
    assert eng.is_daily_goal_met(date.today())


def test_second_done_is_idempotent(tmp_path: Path):
    client = _client(tmp_path)
    eng = _engine(client)
    _make_due(client, ["clause-1", "article-end"])
    session_id, _first = _start(client)
    _finish(client, "clause-1", session_id)
    _finish(client, "article-end", session_id)
    assert _goal_count(eng) == 1

    complete_all_modes(client, MINI_UNITS, "article-end")
    again = client.post(
        with_params("/learn/article-end/done", {"session": session_id}),
        follow_redirects=False,
    )
    assert again.status_code == 303
    assert _goal_count(eng) == 1


def test_skip_remaining_does_not_record_the_goal(tmp_path: Path):
    client = _client(tmp_path)
    eng = _engine(client)
    session = eng.create_study_session(
        session_id="day-mix",
        kind="day_plan",
        plan_date=date.today(),
        unit_ids=["clause-1", "article-end"],
    )
    _finish(client, "clause-1", session.id)
    assert _goal_count(eng) == 0

    skip = client.post(
        with_params("/learn/article-end/skip", {"session": session.id}),
        follow_redirects=False,
    )
    assert skip.status_code == 303
    refreshed = eng.get_study_session(session.id)
    assert refreshed is not None
    assert refreshed.item_for("article-end").status == "deferred"
    maybe_record_daily_goal_met(eng, session=refreshed)
    assert _goal_count(eng) == 0
    assert not eng.is_daily_goal_met(date.today())


def test_get_dashboard_does_not_write_a_goal_fact(tmp_path: Path):
    client = _client(tmp_path, multiuser=True)
    _sign_in(client)
    _make_due(client, ["clause-1"])
    eng = _engine(client)
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert _goal_count(eng) == 0
    assert eng.active_study_session(kind="revision") is None


def test_missing_table_degrades_and_done_still_redirects(tmp_path: Path):
    client = _client(tmp_path)
    _make_due(client, ["clause-1"])
    session_id, first = _start(client)
    assert first == "clause-1"
    _drop_daily_goal_table(client)

    location = _finish(client, "clause-1", session_id)
    assert urlsplit(location).path == "/"
    tables = {
        row["name"]
        for row in _engine(client).repo.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "daily_goal_met" not in tables


def test_streak_is_derived_from_consecutive_facts(tmp_path: Path):
    client = _client(tmp_path)
    eng = _engine(client)
    today = date.today()
    assert daily_goal_streak(eng, as_of=today) == 0

    eng.record_daily_goal_met(today - timedelta(days=3))
    assert daily_goal_streak(eng, as_of=today) == 0

    eng.record_daily_goal_met(today - timedelta(days=1))
    assert daily_goal_streak(eng, as_of=today) == 1

    eng.record_daily_goal_met(today)
    eng.record_daily_goal_met(today - timedelta(days=2))
    assert daily_goal_streak(eng, as_of=today) == 4


def test_streak_schema_gap_is_zero(tmp_path: Path):
    client = _client(tmp_path)
    eng = _engine(client)
    eng.record_daily_goal_met(date.today())
    _drop_daily_goal_table(client)
    assert daily_goal_streak(eng) == 0


def test_daily_goal_streak_is_not_day_streak(tmp_path: Path):
    """A lone Done still advances day_streak; the goal streak needs the path."""
    client = _client(tmp_path)
    eng = _engine(client)
    _make_due(client, ["clause-1", "article-end"])
    session_id, _first = _start(client)
    _finish(client, "clause-1", session_id)
    assert day_streak(eng) >= 1
    assert daily_goal_streak(eng) == 0
    assert _goal_count(eng) == 0


def test_unrelated_errors_still_raise(tmp_path: Path):
    from constitution_memorizer.web.service import _is_missing_optional_schema

    assert not _is_missing_optional_schema(
        Exception('relation "learning_unit_progress" does not exist')
    )
    assert not _is_missing_optional_schema(Exception("connection refused"))
