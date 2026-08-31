"""Phone Settings restyle: guest GET, groups, text size, cache pins."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import InMemorySessionStore
from constitution_memorizer.multiuser.settings import MultiUserSettings, clear_settings_cache
from constitution_memorizer.web.app import create_app

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"


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


def _client(tmp_path: Path) -> TestClient:
    clear_settings_cache()
    provider = FakeAuthProvider()
    provider.seed_google_user(
        user_id=UUID("11111111-1111-4111-8111-111111111111"),
        email="a@example.com",
        display_name="User A",
    )
    return TestClient(
        create_app(
            units_path=MINI_UNITS,
            db_path=tmp_path / "progress.db",
            multiuser=True,
            multiuser_settings=_settings(),
            auth_provider=provider,
            session_store=InMemorySessionStore(),
        )
    )


def _sign_in(client: TestClient) -> None:
    start = client.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state")
    client.get(f"/auth/callback?code=fake-google-code&state={state}", follow_redirects=False)


def test_guest_get_settings_renders_page(tmp_path: Path):
    client = _client(tmp_path)
    resp = client.get("/settings", follow_redirects=False)
    assert resp.status_code == 200
    html = resp.text
    assert 'data-mscreen="settings"' in html
    assert "Guest · progress on this device" in html
    assert 'href="/login"' in html
    assert "Sign in to sync" in html
    assert 'data-report-section="Settings"' in html
    assert "Bare Act text verbatim · Day 1 · 3 · 7 · 15 · 30 · 60" in html
    assert "data-text-size-step" in html
    assert "data-motion-toggle" in html
    assert "Sign out" not in html


def test_guest_settings_posts_stay_auth_gated(tmp_path: Path):
    client = _client(tmp_path)
    saved = client.post("/settings", follow_redirects=False)
    assert saved.status_code == 303
    assert saved.headers["location"].startswith("/login")
    plan = client.post(
        "/settings/learning-plan",
        data={"mode": "auto", "daily_target": "5"},
        follow_redirects=False,
    )
    assert plan.status_code == 303
    assert plan.headers["location"].startswith("/login")


def test_signed_in_settings_has_groups_and_handlers(tmp_path: Path):
    client = _client(tmp_path)
    _sign_in(client)
    html = client.get("/settings").text
    assert "Learning plan" in html
    assert 'data-settings-group="study"' in html
    assert 'data-settings-group="app"' in html
    assert 'data-settings-group="account"' in html
    assert "data-plan-autosubmit" in html
    assert "data-text-size-step" in html
    assert "data-motion-toggle" in html
    assert 'data-report-section="Settings"' in html
    assert "action=\"/logout\"" in html
    assert "Sign out" in html
    assert "confirm(" not in html.split("action=\"/logout\"")[1].split("</form>")[0]


def test_text_size_api_persists_for_signed_in(tmp_path: Path):
    client = _client(tmp_path)
    _sign_in(client)
    bad = client.post("/api/text-size", data={"size": "12"})
    assert bad.status_code == 400
    ok = client.post("/api/text-size", data={"size": "21"})
    assert ok.status_code == 200
    assert ok.json() == {"size": 21}
    store = client.app.state.session_store
    user_id = sorted(store._sessions.values(), key=lambda s: s.created_at)[-1].user.id
    assert client.app.state.engine.repo.get_setting(user_id, "text_size") == "21"


def test_guest_text_size_api_does_not_write(tmp_path: Path):
    client = _client(tmp_path)
    resp = client.post("/api/text-size", data={"size": "22"})
    assert resp.status_code == 200
    assert resp.json() == {"size": 22}


def test_settings_assets_and_hooks(tmp_path: Path):
    client = _client(tmp_path)
    html = client.get("/browse").text
    assert "styles.css?v=main46" in html
    assert "mobile.css?v=mob53" in html
    assert "app.js?v=main48" in html
    css = client.get("/static/mobile.css?v=mob53").text
    assert 'body[data-mscreen="settings"] .mobile-tabbar' in css
    assert 'body[data-mscreen="settings"] .settings-desk-copy' in css
    assert ".settings-toggle" in css
    styles = client.get("/static/styles.css?v=main46").text
    assert "--bare-size" in styles
    assert "var(--bare-size" in styles
    js = client.get("/static/app.js?v=main48").text
    assert "cm-text-size" in js
    assert "data-gcal-toggle" in js
    assert "data-plan-autosubmit" in js
    report = client.get("/static/report.js?v=report4").text
    assert "data-report-section" in report
