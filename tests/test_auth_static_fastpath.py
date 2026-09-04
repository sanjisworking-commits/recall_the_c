"""Auth middleware skips session lookup for static assets and /health."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import InMemorySessionStore
from constitution_memorizer.multiuser.settings import MultiUserSettings, clear_settings_cache
from constitution_memorizer.web.app import create_app

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"


class CountingSessionStore(InMemorySessionStore):
    def __init__(self) -> None:
        super().__init__()
        self.get_calls = 0

    def get(self, session_id: str):
        self.get_calls += 1
        return super().get(session_id)


def _settings() -> MultiUserSettings:
    return MultiUserSettings(
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
    )


def _authed_client(tmp_path: Path) -> tuple[TestClient, CountingSessionStore]:
    clear_settings_cache()
    provider = FakeAuthProvider()
    provider.seed_google_user(
        user_id=UUID("11111111-1111-4111-8111-111111111111"),
        email="a@example.com",
        display_name="User A",
    )
    store = CountingSessionStore()
    client = TestClient(
        create_app(
            units_path=MINI_UNITS,
            db_path=tmp_path / "progress.db",
            multiuser=True,
            multiuser_settings=_settings(),
            auth_provider=provider,
            session_store=store,
        )
    )
    start = client.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state")
    client.get(
        f"/auth/callback?code=fake-google-code&state={state}",
        follow_redirects=False,
    )
    return client, store


def test_static_and_health_skip_session_store(tmp_path: Path):
    client, store = _authed_client(tmp_path)
    after_login = store.get_calls

    js = client.get("/static/app.js")
    assert js.status_code == 200
    assert store.get_calls == after_login

    css = client.get("/static/styles.css")
    assert css.status_code == 200
    assert store.get_calls == after_login

    health = client.get("/health")
    assert health.status_code == 200
    assert store.get_calls == after_login

    sitemap = client.get("/sitemap.xml")
    assert sitemap.status_code == 200
    assert store.get_calls == after_login

    robots = client.get("/robots.txt")
    assert robots.status_code == 200
    assert store.get_calls == after_login

    browse = client.get("/browse")
    assert browse.status_code == 200
    assert store.get_calls > after_login
    clear_settings_cache()


def test_auth_middleware_fastpath_is_before_session_lookup():
    from constitution_memorizer.auth import routes

    text = Path(routes.__file__).read_text(encoding="utf-8")
    gate = text.split("async def multiuser_auth_gate", 1)[1]
    # The exempt set moved into auth.guest.ROOT_ASSET_PATHS so the three lists
    # that must agree about it share one definition.
    fast = gate.index('path in ROOT_ASSET_PATHS or path.startswith("/static/")')
    lookup = gate.index("get_optional_current_user(request)")
    assert fast < lookup
    assert "return await call_next(request)" in gate[:lookup]
