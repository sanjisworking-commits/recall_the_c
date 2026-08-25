"""Native-client bearer auth for the /api/v1 surface (Step 7).

Supabase verification is mocked via FakeAuthProvider — no real network calls.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from constitution_memorizer.auth.bearer import clear_bearer_cache
from constitution_memorizer.auth.dependencies import (
    get_optional_current_user,
    require_csrf,
)
from constitution_memorizer.auth.exceptions import InvalidCredentialsError
from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import (
    SESSION_COOKIE_NAME,
    InMemorySessionStore,
)
from constitution_memorizer.multiuser.settings import (
    MultiUserSettings,
    clear_settings_cache,
)
from constitution_memorizer.web.app import create_app

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
USER_ID = UUID("22222222-2222-4222-8222-222222222222")
GOOD_TOKEN = "supabase-access-token-good"


@pytest.fixture(autouse=True)
def _isolate():
    clear_settings_cache()
    clear_bearer_cache()
    yield
    clear_settings_cache()
    clear_bearer_cache()


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


def _client(tmp_path: Path, provider: FakeAuthProvider) -> TestClient:
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "progress.db",
        multiuser=True,
        multiuser_settings=_settings(),
        auth_provider=provider,
        session_store=InMemorySessionStore(),
    )
    return TestClient(app)


def _provider_with_token() -> FakeAuthProvider:
    provider = FakeAuthProvider()
    user = provider.seed_google_user(
        user_id=USER_ID,
        email="mobile@example.com",
        display_name="Mobile User",
    )
    provider.tokens[GOOD_TOKEN] = user
    return provider


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --------------------------------------------------------------------------- #
# /api/v1/me                                                                   #
# --------------------------------------------------------------------------- #


def test_me_valid_bearer_resolves_correct_user(tmp_path: Path):
    client = _client(tmp_path, _provider_with_token())
    resp = client.get("/api/v1/me", headers=_bearer(GOOD_TOKEN))
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["user"]["id"] == str(USER_ID)
    assert body["user"]["email"] == "mobile@example.com"
    assert body["user"]["display_name"] == "Mobile User"


def test_me_requires_authentication(tmp_path: Path):
    client = _client(tmp_path, _provider_with_token())
    resp = client.get("/api/v1/me")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Authentication required"


def test_me_rejects_invalid_bearer(tmp_path: Path):
    client = _client(tmp_path, _provider_with_token())
    resp = client.get("/api/v1/me", headers=_bearer("not-a-real-token"))
    assert resp.status_code == 401


def test_me_rejects_failed_verification(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A token the provider rejects (e.g. expired) must fail cleanly as 401."""
    provider = _provider_with_token()

    def _raise(_token: str):
        raise InvalidCredentialsError("expired")

    monkeypatch.setattr(provider, "verify_access_token", _raise)
    client = _client(tmp_path, provider)
    resp = client.get("/api/v1/me", headers=_bearer(GOOD_TOKEN))
    assert resp.status_code == 401


def test_me_rejects_malformed_authorization_header(tmp_path: Path):
    client = _client(tmp_path, _provider_with_token())
    resp = client.get("/api/v1/me", headers={"Authorization": GOOD_TOKEN})  # no scheme
    assert resp.status_code == 401


# --------------------------------------------------------------------------- #
# POST /api/v1/auth/bootstrap                                                  #
# --------------------------------------------------------------------------- #


def test_auth_bootstrap_maps_to_recallc_user_and_persists_profile(tmp_path: Path):
    provider = _provider_with_token()
    client = _client(tmp_path, provider)
    resp = client.post("/api/v1/auth/bootstrap", headers=_bearer(GOOD_TOKEN))
    assert resp.status_code == 200
    assert resp.json()["user"]["id"] == str(USER_ID)
    # The Supabase identity was mapped to a durable RecallC profile row.
    profile = client.app.state.engine.repo.get_profile(USER_ID)
    assert profile is not None


def test_auth_bootstrap_requires_bearer(tmp_path: Path):
    client = _client(tmp_path, _provider_with_token())
    assert client.post("/api/v1/auth/bootstrap").status_code == 401
    assert (
        client.post("/api/v1/auth/bootstrap", headers=_bearer("bad")).status_code == 401
    )


def test_auth_bootstrap_rejects_cookie_only(tmp_path: Path):
    """Bootstrap is native-only: a valid browser cookie session must NOT
    authenticate it (only an actual Supabase bearer token may), even though the
    same cookie authenticates the general /api/v1/me endpoint."""
    provider = _provider_with_token()
    client = _client(tmp_path, provider)
    # Full browser Google login → sets rtc_session cookie on the client.
    start = client.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state")
    cb = client.get(
        f"/auth/callback?code=fake-google-code&state={state}",
        follow_redirects=False,
    )
    assert cb.status_code == 303
    assert SESSION_COOKIE_NAME in cb.cookies
    # The cookie authenticates /me ...
    assert client.get("/api/v1/me").status_code == 200
    # ... but NOT bootstrap (no bearer header present).
    assert client.post("/api/v1/auth/bootstrap").status_code == 401


# --------------------------------------------------------------------------- #
# Browser cookie flow is unchanged                                            #
# --------------------------------------------------------------------------- #


def test_existing_cookie_auth_still_works(tmp_path: Path):
    provider = _provider_with_token()
    client = _client(tmp_path, provider)
    # Full browser Google login → sets rtc_session cookie.
    start = client.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state")
    cb = client.get(
        f"/auth/callback?code=fake-google-code&state={state}",
        follow_redirects=False,
    )
    assert cb.status_code == 303
    assert SESSION_COOKIE_NAME in cb.cookies
    # Existing browser surface still renders.
    assert client.get("/dashboard").status_code == 200
    # And the same cookie session authenticates the new API too (cookie OR bearer).
    me = client.get("/api/v1/me")
    assert me.status_code == 200
    assert me.json()["ok"] is True


# --------------------------------------------------------------------------- #
# Bearer must not weaken browser CSRF                                          #
# --------------------------------------------------------------------------- #


def _bare_request(app, *, authorization: str | None = None) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if authorization is not None:
        headers.append((b"authorization", authorization.encode()))
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/settings",
        "query_string": b"",
        "headers": headers,
        "app": app,
        "state": {},
    }
    return Request(scope)


def test_bearer_auth_does_not_grant_csrf_exemption(tmp_path: Path):
    """A bearer-authenticated request has no cookie session, so it must NOT
    satisfy require_csrf — it never sets auth_session and carries no rtc_csrf
    cookie, so CSRF still fails closed exactly as for an anonymous request."""
    provider = _provider_with_token()
    client = _client(tmp_path, provider)
    request = _bare_request(client.app, authorization=f"Bearer {GOOD_TOKEN}")

    user = get_optional_current_user(request)
    assert user is not None and user.id == USER_ID
    # Bearer resolution must not install a cookie session (the CSRF anchor).
    assert getattr(request.state, "auth_session", None) is None

    with pytest.raises(HTTPException) as exc:
        require_csrf(request, csrf_token=None)
    assert exc.value.status_code == 403
