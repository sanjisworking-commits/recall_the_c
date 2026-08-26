"""Multi-user auth flows with FakeAuthProvider (no Google/SMS)."""

from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.auth.exceptions import AuthConfigError, InvalidCredentialsError
from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.phone import mask_phone, normalize_e164
from constitution_memorizer.auth.sessions import (
    CSRF_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    InMemorySessionStore,
)
from constitution_memorizer.multiuser.settings import MultiUserSettings, clear_settings_cache
from constitution_memorizer.web.app import create_app

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"


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


def _multi_client(tmp_path: Path, provider: FakeAuthProvider | None = None) -> TestClient:
    provider = provider or FakeAuthProvider()
    provider.seed_google_user(
        user_id=UUID("11111111-1111-4111-8111-111111111111"),
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
    return TestClient(app)


def test_normalize_and_mask_phone():
    assert normalize_e164("+91 98765 43210") == "+919876543210"
    assert normalize_e164("9876543210") == "+919876543210"
    with pytest.raises(InvalidCredentialsError):
        normalize_e164("12345")
    assert mask_phone("+919876543210") == "+91******3210"


def test_load_env_file_sets_supabase_vars(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from constitution_memorizer.multiuser.settings import load_env_file

    env = tmp_path / ".env"
    env.write_text(
        "SUPABASE_URL=https://rzkolfpivlpkctvtggre.supabase.co\n"
        "SUPABASE_ANON_KEY=test-anon\n"
        "MULTIUSER_ENABLED=true\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "")
    monkeypatch.delenv("MULTIUSER_ENABLED", raising=False)
    loaded = load_env_file(env, override=True)
    assert loaded == env
    assert os.environ["SUPABASE_URL"] == "https://rzkolfpivlpkctvtggre.supabase.co"
    assert os.environ["SUPABASE_ANON_KEY"] == "test-anon"
    # Avoid leaking multi-user flags into later single-user tests.
    monkeypatch.delenv("MULTIUSER_ENABLED", raising=False)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)


def test_staging_requires_auth_method():
    with pytest.raises(AuthConfigError):
        MultiUserSettings(
            _env_file=None,
            APP_ENV="staging",
            AUTH_GOOGLE_ENABLED="false",
            AUTH_PHONE_ENABLED="false",
            DATABASE_URL="postgresql://x",
            SUPABASE_URL="http://x",
            SUPABASE_ANON_KEY="x",
            SESSION_SECRET="x",
        ).validate_for_startup()


def test_login_page_feature_flags(tmp_path: Path):
    provider = FakeAuthProvider()
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "p.db",
        multiuser=True,
        multiuser_settings=_settings(AUTH_GOOGLE_ENABLED="false"),
        auth_provider=provider,
        session_store=InMemorySessionStore(),
    )
    client = TestClient(app)
    html = client.get("/login").text
    assert 'href="/auth/google/start"' not in html
    assert "Mobile number" in html or "national_number" in html


def test_login_phone_otp_shows_unavailable_tag(tmp_path: Path):
    """Phone OTP stays visible while registration is pending, but is not submittable."""
    provider = FakeAuthProvider()
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "p.db",
        multiuser=True,
        multiuser_settings=_settings(AUTH_PHONE_ENABLED="false"),
        auth_provider=provider,
        session_store=InMemorySessionStore(),
    )
    client = TestClient(app)
    html = client.get("/login").text
    assert "Continue with Google" in html
    assert "Mobile number" in html
    assert "not currently available" in html
    assert 'data-phone-unavailable' in html
    assert 'data-send-otp' not in html
    assert 'action="/auth/phone/send"' not in html
    assert 'data-phone-form' not in html

    csrf = client.cookies.get(CSRF_COOKIE_NAME)
    send = client.post(
        "/auth/phone/send",
        data={
            "national_number": "9876543210",
            "country_code": "+91",
            "csrf_token": csrf,
            "next": "/dashboard",
        },
        follow_redirects=False,
    )
    assert send.status_code == 303
    assert "phone_disabled" in send.headers["location"]
    verify = client.post(
        "/auth/phone/verify",
        data={
            "phone": "+919876543210",
            "otp": "123456",
            "csrf_token": csrf,
        },
        follow_redirects=False,
    )
    assert verify.status_code == 303
    assert "phone_disabled" in verify.headers["location"]


def test_google_oauth_callback_sets_session(tmp_path: Path):
    provider = FakeAuthProvider()
    client = _multi_client(tmp_path, provider)
    start = client.get("/auth/google/start", follow_redirects=False)
    assert start.status_code == 303
    state = start.cookies.get("rtc_oauth_state")
    assert state
    assert start.cookies.get("rtc_pkce_verifier")
    cb = client.get(
        f"/auth/callback?code=fake-google-code&state={state}",
        follow_redirects=False,
    )
    assert cb.status_code == 303
    assert cb.headers["location"].startswith("/auth/transition")
    assert SESSION_COOKIE_NAME in cb.cookies
    dash = client.get("/dashboard")
    assert dash.status_code == 200
    assert "Welcome, User." in dash.text or "Good morning, User." in dash.text


def test_oauth_callback_accepts_code_with_cookie_only(tmp_path: Path):
    """Supabase PKCE may omit state in the query; the start cookie is enough CSRF."""
    provider = FakeAuthProvider()
    client = _multi_client(tmp_path, provider)
    start = client.get("/auth/google/start", follow_redirects=False)
    assert start.cookies.get("rtc_oauth_state")
    cb = client.get(
        "/auth/callback?code=fake-google-code",
        follow_redirects=False,
    )
    assert cb.status_code == 303
    assert cb.headers["location"].startswith("/auth/transition")


def test_oauth_callback_bridge_when_no_query_tokens(tmp_path: Path):
    client = _multi_client(tmp_path)
    page = client.get("/auth/callback")
    assert page.status_code == 200
    assert "Completing sign-in" in page.text
    assert "access_token" in page.text


def test_oauth_callback_rejects_bad_state(tmp_path: Path):
    client = _multi_client(tmp_path)
    start = client.get("/auth/google/start", follow_redirects=False)
    assert start.status_code == 303
    resp = client.get("/auth/callback?code=fake-google-code&state=nope", follow_redirects=False)
    assert resp.status_code == 303
    assert "oauth_state" in resp.headers["location"]


def test_phone_otp_flow(tmp_path: Path):
    provider = FakeAuthProvider()
    client = _multi_client(tmp_path, provider)
    login = client.get("/login")
    csrf = login.cookies.get(CSRF_COOKIE_NAME)
    send = client.post(
        "/auth/phone/send",
        data={"phone": "+14155552671", "csrf_token": csrf},
        follow_redirects=False,
    )
    assert send.status_code == 303
    assert "otp=1" in send.headers["location"]
    assert provider.sent_otps == ["+14155552671"]

    login2 = client.get("/login?otp=1&phone=%2B14155552671")
    csrf2 = login2.cookies.get(CSRF_COOKIE_NAME)
    verify = client.post(
        "/auth/phone/verify",
        data={"phone": "+14155552671", "otp": "123456", "csrf_token": csrf2},
        follow_redirects=False,
    )
    assert verify.status_code == 303
    # Phone users without display_name land on welcome.
    assert verify.headers["location"] == "/welcome"


def test_otp_expired_vs_incorrect(tmp_path: Path):
    provider = FakeAuthProvider()
    client = _multi_client(tmp_path, provider)
    login = client.get("/login")
    csrf = login.cookies.get(CSRF_COOKIE_NAME)
    client.post(
        "/auth/phone/send",
        data={"phone": "+14155552671", "csrf_token": csrf},
        follow_redirects=False,
    )
    expired = client.post(
        "/auth/phone/verify",
        data={"phone": "+14155552671", "otp": "000000", "csrf_token": csrf},
        follow_redirects=False,
    )
    assert "otp_expired" in expired.headers["location"]
    expired_page = client.get(expired.headers["location"])
    assert "This code has expired" in expired_page.text

    bad = client.post(
        "/auth/phone/verify",
        data={"phone": "+14155552671", "otp": "111111", "csrf_token": csrf},
        follow_redirects=False,
    )
    assert "bad_otp" in bad.headers["location"]
    bad_page = client.get(bad.headers["location"])
    assert "not accepted" in bad_page.text


def test_otp_resent_banner(tmp_path: Path):
    provider = FakeAuthProvider()
    client = _multi_client(tmp_path, provider)
    login = client.get("/login")
    csrf = login.cookies.get(CSRF_COOKIE_NAME)
    client.post(
        "/auth/phone/send",
        data={"phone": "+919876543210", "csrf_token": csrf},
        follow_redirects=False,
    )
    # Bypass resend cooldown so the second send succeeds in the test.
    client.app.state.otp_limiter._by_phone.clear()
    resent = client.post(
        "/auth/phone/send",
        data={
            "phone": "+919876543210",
            "csrf_token": csrf,
            "resend": "1",
        },
        follow_redirects=False,
    )
    assert resent.status_code == 303
    assert "resent=1" in resent.headers["location"]
    page = client.get(resent.headers["location"])
    assert "New code sent" in page.text


def test_otp_too_many_attempts_banner(tmp_path: Path):
    provider = FakeAuthProvider()
    client = _multi_client(tmp_path, provider)
    login = client.get("/login")
    csrf = login.cookies.get(CSRF_COOKIE_NAME)
    client.post(
        "/auth/phone/send",
        data={"phone": "+919876543210", "csrf_token": csrf},
        follow_redirects=False,
    )
    for _ in range(5):
        client.post(
            "/auth/phone/verify",
            data={"phone": "+919876543210", "otp": "111111", "csrf_token": csrf},
            follow_redirects=False,
        )
    blocked = client.post(
        "/auth/phone/verify",
        data={"phone": "+919876543210", "otp": "111111", "csrf_token": csrf},
        follow_redirects=False,
    )
    assert "too_many_attempts" in blocked.headers["location"]
    page = client.get(blocked.headers["location"])
    assert "Too many attempts" in page.text


def test_protected_route_redirects(tmp_path: Path):
    client = _multi_client(tmp_path)
    # Progress/dashboard show inline guest gates (200). Calendar still redirects.
    prog = client.get("/progress")
    assert prog.status_code == 200
    assert "Sign in to save your learning" in prog.text
    cal = client.get("/calendar", follow_redirects=False)
    assert cal.status_code == 303
    assert cal.headers["location"].startswith("/login")


def test_logout_clears_session(tmp_path: Path):
    provider = FakeAuthProvider()
    client = _multi_client(tmp_path, provider)
    start = client.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state")
    client.get(f"/auth/callback?code=fake-google-code&state={state}", follow_redirects=False)
    assert client.get("/dashboard").status_code == 200
    out = client.post("/logout", follow_redirects=False)
    assert out.status_code == 303
    assert out.headers["location"] == "/signed-out"
    gate = client.get("/dashboard")
    assert gate.status_code == 200
    assert "Sign in to save your learning" in gate.text
