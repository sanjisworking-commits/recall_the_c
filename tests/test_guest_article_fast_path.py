"""Phase 2 (request latency): guest Article pages must not read a personal gloss.

A guest has no Explain-it-back gloss, yet the route used to call
``get_gloss`` unconditionally — one Postgres round trip (~230 ms in
production) spent fetching nothing. These tests pin that a guest performs zero
gloss repository calls while an authenticated user still loads a saved gloss.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import InMemorySessionStore
from constitution_memorizer.multiuser.settings import (
    MultiUserSettings,
    clear_settings_cache,
)
from constitution_memorizer.progress import repository as repo_mod
from constitution_memorizer.web.app import create_app

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
UID = UUID("11111111-1111-4111-8111-111111111111")


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


def _client(tmp_path: Path) -> TestClient:
    provider = FakeAuthProvider()
    provider.seed_google_user(user_id=UID, email="a@example.com", display_name="User A")
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "progress.db",
        multiuser=True,
        multiuser_settings=_settings(),
        auth_provider=provider,
        session_store=InMemorySessionStore(),
    )
    return TestClient(app)


def _login(client: TestClient) -> None:
    start = client.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state")
    client.get(
        f"/auth/callback?code=fake-google-code&state={state}",
        follow_redirects=False,
    )


def _spy_gloss_reads(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Record every ``ProgressRepository.get_gloss`` call, delegating to the real
    implementation so behavior is unchanged."""
    calls: list[tuple[str, str]] = []
    real = repo_mod.ProgressRepository.get_gloss

    def wrapped(self, user_id, article_number):  # type: ignore[no-untyped-def]
        calls.append((str(user_id), str(article_number)))
        return real(self, user_id, article_number)

    monkeypatch.setattr(repo_mod.ProgressRepository, "get_gloss", wrapped)
    return calls


def test_guest_article_performs_zero_gloss_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    client = _client(tmp_path)
    calls = _spy_gloss_reads(monkeypatch)

    resp = client.get("/browse/article/20")
    assert resp.status_code == 200
    assert calls == [], f"guest Article read the gloss repo: {calls}"


def test_guest_article_renders_public_content_with_empty_explainer(tmp_path: Path):
    client = _client(tmp_path)
    resp = client.get("/browse/article/20")
    assert resp.status_code == 200
    # Public Article content still renders for a guest.
    assert "Article 20" in resp.text
    # Explain-it-back textarea is present but empty (no saved gloss value).
    assert "data-gloss-input" in resp.text
    assert "></textarea>" in resp.text


def test_authenticated_article_still_loads_saved_gloss(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    client = _client(tmp_path)
    _login(client)

    engine = client.app.state.engine.for_user(UID)
    engine.upsert_gloss("20", "My own paraphrase of Article 20")

    calls = _spy_gloss_reads(monkeypatch)
    resp = client.get("/browse/article/20")
    assert resp.status_code == 200
    assert "My own paraphrase of Article 20" in resp.text
    assert calls, "authenticated Article did not read the saved gloss"
    assert all(art == "20" for _uid, art in calls)
