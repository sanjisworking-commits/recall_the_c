"""Settings + onboarding for Self-paced / Auto Plan."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import CSRF_COOKIE_NAME, InMemorySessionStore
from constitution_memorizer.multiuser.settings import MultiUserSettings, clear_settings_cache
from constitution_memorizer.progress.scheduler import ReminderEngine
from constitution_memorizer.web.app import create_app

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"


def _client(tmp_path: Path, *, entitlements: bool = False) -> TestClient:
    clear_settings_cache()
    settings = MultiUserSettings(
        _env_file=None,
        APP_ENV="test",
        MULTIUSER_ENABLED="true",
        AUTH_GOOGLE_ENABLED="true",
        SESSION_SECRET="test-secret",
        SUPABASE_URL="http://example.invalid",
        SUPABASE_ANON_KEY="anon",
        DATABASE_URL="",
        COOKIE_SECURE="false",
        ARTICLE_ENTITLEMENTS_ENABLED="true" if entitlements else "false",
    )
    return TestClient(
        create_app(
            units_path=MINI_UNITS,
            db_path=tmp_path / "progress.db",
            multiuser=True,
            multiuser_settings=settings,
            auth_provider=FakeAuthProvider(),
            session_store=InMemorySessionStore(),
        )
    )


def _sign_in(client: TestClient) -> None:
    start = client.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state")
    client.get(f"/auth/callback?code=fake-google-code&state={state}", follow_redirects=False)


def _engine(client: TestClient) -> ReminderEngine:
    engine = client.app.state.engine
    store = getattr(client.app.state, "session_store", None)
    sessions = getattr(store, "_sessions", None) if store is not None else None
    newest = sorted(sessions.values(), key=lambda s: s.created_at)[-1]
    return engine.for_user(newest.user.id)


def test_settings_shows_learning_plan_and_saves_auto(tmp_path: Path):
    client = _client(tmp_path)
    _sign_in(client)
    page = client.get("/settings")
    assert page.status_code == 200
    assert "Learning plan" in page.text
    assert "Self-paced" in page.text
    assert "Auto Plan" in page.text
    saved = client.post(
        "/settings/learning-plan",
        data={"mode": "auto", "daily_target": "5"},
        follow_redirects=False,
    )
    assert saved.status_code == 303
    plan = _engine(client).get_learning_plan()
    assert plan.mode == "auto"
    assert plan.daily_target == 5
    assert plan.activated_at is None
    again = client.get("/settings")
    assert "Plan started" in again.text
    assert "Not started" in again.text


def test_onboarding_plan_saves_self_paced(tmp_path: Path):
    client = _client(tmp_path)
    _sign_in(client)
    page = client.get("/onboarding/plan")
    assert page.status_code == 200
    assert "Set a learning plan" in page.text
    csrf = client.cookies.get(CSRF_COOKIE_NAME) or ""
    resp = client.post(
        "/onboarding/plan",
        data={"mode": "self_paced", "csrf_token": csrf},
        follow_redirects=False,
    )
    assert resp.headers["location"] == "/dashboard"
    plan = _engine(client).get_learning_plan()
    assert plan.mode == "self_paced"
    assert plan.activated_at is None


def test_free_account_cannot_enable_auto_plan(tmp_path: Path):
    client = _client(tmp_path, entitlements=True)
    _sign_in(client)
    page = client.get("/settings")
    assert "Part of unlocking every Article" in page.text
    client.post(
        "/settings/learning-plan",
        data={"mode": "auto", "daily_target": "7"},
        follow_redirects=False,
    )
    plan = _engine(client).get_learning_plan()
    assert plan.mode == "self_paced"
    start = client.post("/learning/start", follow_redirects=False)
    assert start.status_code == 303
    assert start.headers["location"] in ("/dashboard", "/")
