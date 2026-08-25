"""First-login onboarding tour: status lifecycle + template wiring."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import (
    CSRF_COOKIE_NAME,
    InMemorySessionStore,
)
from constitution_memorizer.multiuser.settings import (
    MultiUserSettings,
    clear_settings_cache,
)
from constitution_memorizer.progress.repository import ONBOARDING_KEY
from constitution_memorizer.web.app import create_app

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"

GOOGLE_USER_ID = UUID("11111111-1111-4111-8111-111111111111")


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


def _client(tmp_path: Path, provider: FakeAuthProvider | None = None):
    provider = provider or FakeAuthProvider()
    provider.seed_google_user(
        user_id=GOOGLE_USER_ID,
        email="a@example.com",
        display_name="User A",
    )
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "progress.db",
        multiuser=True,
        multiuser_settings=_settings(),
        auth_provider=provider,
        session_store=InMemorySessionStore(),
    )
    return TestClient(app), app, provider


def _sign_in_phone(client: TestClient, provider: FakeAuthProvider) -> None:
    """Fresh phone user: no display_name, so /welcome is required."""
    login = client.get("/login")
    csrf = login.cookies.get(CSRF_COOKIE_NAME)
    client.post(
        "/auth/phone/send",
        data={"phone": "+14155552671", "csrf_token": csrf},
        follow_redirects=False,
    )
    login2 = client.get("/login?otp=1&phone=%2B14155552671")
    csrf2 = login2.cookies.get(CSRF_COOKIE_NAME)
    verify = client.post(
        "/auth/phone/verify",
        data={"phone": "+14155552671", "otp": "123456", "csrf_token": csrf2},
        follow_redirects=False,
    )
    assert verify.status_code == 303
    assert verify.headers["location"] == "/welcome"


def _post_welcome(client: TestClient, name: str = "Aarav") -> None:
    page = client.get("/welcome")
    csrf = page.cookies.get(CSRF_COOKIE_NAME) or client.cookies.get(CSRF_COOKIE_NAME)
    resp = client.post(
        "/welcome",
        data={"display_name": name, "csrf_token": csrf},
        follow_redirects=False,
    )
    assert resp.status_code == 303


def _phone_user_id(app):
    repo = app.state.engine.repo
    for uid in _all_profile_ids(repo):
        if uid != GOOGLE_USER_ID:
            return uid
    raise AssertionError("phone user not found")


def _all_profile_ids(repo):
    rows = repo._conn.execute("SELECT user_id FROM user_profile").fetchall()
    return [UUID(str(r["user_id"])) for r in rows]


def test_first_welcome_activates_tour(tmp_path: Path):
    client, app, provider = _client(tmp_path)
    _sign_in_phone(client, provider)
    _post_welcome(client)
    uid = _phone_user_id(app)
    assert app.state.engine.repo.get_setting(uid, ONBOARDING_KEY) == "active"

    dash = client.get("/dashboard")
    assert dash.status_code == 200
    assert 'data-onboarding="active"' in dash.text
    assert "/static/onboarding.js" in dash.text
    assert "/static/onboarding.css" in dash.text


def test_welcome_edit_never_restarts_tour(tmp_path: Path):
    client, app, provider = _client(tmp_path)
    _sign_in_phone(client, provider)
    _post_welcome(client)
    uid = _phone_user_id(app)
    app.state.engine.repo.set_setting(uid, ONBOARDING_KEY, "completed")
    _post_welcome(client, name="Aarav 2")
    assert app.state.engine.repo.get_setting(uid, ONBOARDING_KEY) == "completed"


def test_onboarding_state_endpoint_xhr(tmp_path: Path):
    client, app, provider = _client(tmp_path)
    _sign_in_phone(client, provider)
    _post_welcome(client)
    uid = _phone_user_id(app)

    resp = client.post(
        "/onboarding/state",
        data={"status": "skipped"},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "status": "skipped"}
    assert app.state.engine.repo.get_setting(uid, ONBOARDING_KEY) == "skipped"

    dash = client.get("/dashboard")
    assert 'data-onboarding="skipped"' in dash.text
    assert "/static/onboarding.js" not in dash.text

    bad = client.post(
        "/onboarding/state",
        data={"status": "nonsense"},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert bad.status_code == 400


def test_onboarding_state_get(tmp_path: Path):
    client, app, provider = _client(tmp_path)
    # Guests get 401 — the client treats that as "no tour".
    anon = client.get("/onboarding/state")
    assert anon.status_code == 401

    _sign_in_phone(client, provider)
    _post_welcome(client)
    resp = client.get("/onboarding/state")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "status": "active"}

    client.post(
        "/onboarding/state",
        data={"status": "completed"},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    resp = client.get("/onboarding/state")
    assert resp.json() == {"ok": True, "status": "completed"}


def test_settings_offers_replay_after_skip(tmp_path: Path):
    client, app, provider = _client(tmp_path)
    _sign_in_phone(client, provider)
    _post_welcome(client)
    client.post(
        "/onboarding/state",
        data={"status": "skipped"},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    settings_page = client.get("/settings")
    assert settings_page.status_code == 200
    assert "Replay the tour" in settings_page.text

    csrf = settings_page.cookies.get(CSRF_COOKIE_NAME) or client.cookies.get(
        CSRF_COOKIE_NAME
    )
    replay = client.post(
        "/onboarding/state",
        data={"status": "active", "csrf_token": csrf},
        follow_redirects=False,
    )
    assert replay.status_code == 303
    assert replay.headers["location"] == "/dashboard"
    uid = _phone_user_id(app)
    assert app.state.engine.repo.get_setting(uid, ONBOARDING_KEY) == "active"


def test_existing_user_without_welcome_gets_no_tour(tmp_path: Path):
    client, app, provider = _client(tmp_path)
    start = client.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state")
    client.get(f"/auth/callback?code=fake-google-code&state={state}")
    dash = client.get("/dashboard")
    assert dash.status_code == 200
    assert "data-onboarding=" not in dash.text
    assert "/static/onboarding.js" not in dash.text


def test_guest_cannot_post_onboarding_state(tmp_path: Path):
    client, app, provider = _client(tmp_path)
    resp = client.post(
        "/onboarding/state",
        data={"status": "skipped"},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert resp.status_code == 401


def test_onboarding_plan_locked_for_free_user(tmp_path: Path):
    client, app, provider = _client(tmp_path)
    _sign_in_phone(client, provider)
    _post_welcome(client)
    resp = client.get("/onboarding/plan", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/dashboard"


def test_onboarding_plan_page_for_local_owner(tmp_path: Path):
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "progress.db",
    )
    client = TestClient(app)
    resp = client.get("/onboarding/plan")
    assert resp.status_code == 200
    assert "Set a learning plan" in resp.text
    assert "Auto Plan" in resp.text
    saved = client.post(
        "/onboarding/plan",
        data={"learning_plan_mode": "auto", "daily_target": "5"},
        follow_redirects=False,
    )
    assert saved.status_code == 303
    from constitution_memorizer.progress.study_session import get_learning_plan

    plan = get_learning_plan(app.state.engine)
    assert plan.mode == "auto"
    assert plan.daily_target == 5
    assert plan.activated_at is None
