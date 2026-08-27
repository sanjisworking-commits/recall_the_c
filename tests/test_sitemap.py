"""Public /sitemap.xml and /robots.txt for search-engine crawlers."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import InMemorySessionStore, SESSION_COOKIE_NAME
from constitution_memorizer.multiuser.settings import MultiUserSettings, clear_settings_cache
from constitution_memorizer.web.app import create_app

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
PRODUCTION_ORIGIN = "https://recall-the-c.in"
SITEMAP_HEADER = "Sitemap: https://recall-the-c.in/sitemap.xml"


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


def _multiuser_client(tmp_path: Path) -> TestClient:
    clear_settings_cache()
    return TestClient(
        create_app(
            units_path=MINI_UNITS,
            db_path=tmp_path / "progress.db",
            multiuser=True,
            multiuser_settings=_settings(),
            auth_provider=FakeAuthProvider(),
            session_store=InMemorySessionStore(),
        )
    )


def test_sitemap_is_public_xml(tmp_path: Path):
    client = _multiuser_client(tmp_path)
    resp = client.get("/sitemap.xml", follow_redirects=False)
    assert resp.status_code == 200
    content_type = resp.headers.get("content-type", "")
    assert "xml" in content_type.lower()
    body = resp.text
    assert PRODUCTION_ORIGIN in body
    assert "<urlset" in body
    assert f"{PRODUCTION_ORIGIN}/" in body
    clear_settings_cache()


def test_sitemap_does_not_require_authentication(tmp_path: Path):
    client = _multiuser_client(tmp_path)
    resp = client.get("/sitemap.xml", follow_redirects=False)
    assert resp.status_code == 200
    assert "/login" not in (resp.headers.get("location") or "")
    stale = client.get(
        "/sitemap.xml",
        cookies={SESSION_COOKIE_NAME: "not-a-real-session"},
        follow_redirects=False,
    )
    assert stale.status_code == 200
    assert "/session-expired" not in (stale.headers.get("location") or "")
    clear_settings_cache()


def test_robots_declares_production_sitemap(tmp_path: Path):
    client = _multiuser_client(tmp_path)
    resp = client.get("/robots.txt", follow_redirects=False)
    assert resp.status_code == 200
    content_type = resp.headers.get("content-type", "")
    assert "text/plain" in content_type.lower()
    assert SITEMAP_HEADER in resp.text
    clear_settings_cache()


def test_sitemap_and_robots_work_in_single_user_mode(tmp_path: Path):
    client = TestClient(
        create_app(
            units_path=MINI_UNITS,
            db_path=tmp_path / "progress.db",
            multiuser=False,
        )
    )
    sitemap = client.get("/sitemap.xml", follow_redirects=False)
    robots = client.get("/robots.txt", follow_redirects=False)
    assert sitemap.status_code == 200
    assert "xml" in sitemap.headers.get("content-type", "").lower()
    assert PRODUCTION_ORIGIN in sitemap.text
    assert robots.status_code == 200
    assert SITEMAP_HEADER in robots.text
