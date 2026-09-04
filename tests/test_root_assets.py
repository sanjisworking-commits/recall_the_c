"""Root paths browsers request without being told to.

`/favicon.ico`, the two Apple touch-icon spellings and `/sw.js` were 404s that
each paid for a session lookup first — and on a stale cookie, redirected to
/session-expired. An icon request could spend the user's one-shot expiry
redirect.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.guest import ROOT_ASSET_PATHS
from constitution_memorizer.auth.sessions import InMemorySessionStore
from constitution_memorizer.multiuser.settings import (
    MultiUserSettings,
    clear_settings_cache,
)
from constitution_memorizer.web.app import create_app

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
USER = UUID("11111111-1111-4111-8111-111111111111")

ASSET_PATHS = (
    "/sw.js",
    "/favicon.ico",
    "/apple-touch-icon.png",
    "/apple-touch-icon-precomposed.png",
)


class CountingSessionStore(InMemorySessionStore):
    def __init__(self) -> None:
        super().__init__()
        self.get_calls = 0

    def get(self, session_id: str):
        self.get_calls += 1
        return super().get(session_id)


@pytest.fixture(autouse=True)
def _clear_settings():
    clear_settings_cache()
    yield
    clear_settings_cache()


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


def _client(tmp_path: Path) -> tuple[TestClient, CountingSessionStore]:
    provider = FakeAuthProvider()
    provider.seed_google_user(
        user_id=USER, email="a@example.com", display_name="A"
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
    return client, store


@pytest.mark.parametrize("path", ASSET_PATHS)
def test_root_assets_are_served(tmp_path: Path, path: str):
    client, _ = _client(tmp_path)
    response = client.get(path)
    assert response.status_code == 200
    assert response.content


def test_service_worker_only_unregisters(tmp_path: Path):
    client, _ = _client(tmp_path)
    response = client.get("/sw.js")
    assert "javascript" in response.headers["content-type"]
    assert "no-cache" in response.headers.get("cache-control", "")
    body = response.text
    assert "unregister" in body
    # Never wipe Cache Storage: we do not know which caches an orphaned worker
    # owns, and the origin's caches are not ours to clear.
    assert "caches.keys" not in body
    assert "caches.delete" not in body


def test_icons_are_images(tmp_path: Path):
    client, _ = _client(tmp_path)
    for path in ASSET_PATHS[1:]:
        response = client.get(path)
        assert response.headers["content-type"] == "image/png", path
        assert response.content[:8] == b"\x89PNG\r\n\x1a\n", path


@pytest.mark.parametrize("path", ASSET_PATHS)
def test_root_assets_skip_the_session_lookup(tmp_path: Path, path: str):
    client, store = _client(tmp_path)
    start = client.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state")
    client.get(
        f"/auth/callback?code=fake-google-code&state={state}",
        follow_redirects=False,
    )
    before = store.get_calls
    assert client.get(path).status_code == 200
    assert store.get_calls == before, path
    # A real page still looks the session up — the fast path is not too wide.
    client.get("/browse")
    assert store.get_calls > before


@pytest.mark.parametrize("path", ASSET_PATHS)
def test_a_stale_cookie_gets_the_asset_not_the_expiry_page(
    tmp_path: Path, path: str
):
    """The bug this fixes: an icon request consuming /session-expired."""
    client, _ = _client(tmp_path)
    client.cookies.set("rtc_session", "long-since-deleted")
    response = client.get(path, follow_redirects=False)
    assert response.status_code == 200, path
    assert "session-expired" not in response.headers.get("location", "")


def test_the_three_exempt_lists_share_one_definition():
    """They have to agree; keeping three copies is how they stop agreeing."""
    from constitution_memorizer.auth import guest, routes
    from constitution_memorizer.web import app as web_app

    for path in ASSET_PATHS:
        assert path in ROOT_ASSET_PATHS
        assert not guest.requires_auth(path, "GET")
        assert guest.is_guest_public_get(path, "GET")
    for module in (routes, web_app):
        text = Path(module.__file__).read_text(encoding="utf-8")
        assert "ROOT_ASSET_PATHS" in text, module.__name__


def test_templates_declare_the_touch_icon():
    templates = Path(
        "src/constitution_memorizer/web/templates"
    ).resolve()
    for name in (
        "base.html",
        "landing.html",
        "landing_light.html",
        "login.html",
        "pricing.html",
        "auth_callback.html",
    ):
        text = (templates / name).read_text(encoding="utf-8")
        assert 'rel="apple-touch-icon"' in text, name
        assert 'rel="icon"' in text, name
