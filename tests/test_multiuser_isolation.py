"""Two-user isolation for progress, memory, settings, and sessions."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import SESSION_COOKIE_NAME, InMemorySessionStore
from constitution_memorizer.multiuser.settings import MultiUserSettings, clear_settings_cache
from constitution_memorizer.progress.db import open_progress_db
from constitution_memorizer.progress.memory import MemoryRepository
from constitution_memorizer.progress.repository import ProgressRepository
from constitution_memorizer.progress.scheduler import ReminderEngine
from constitution_memorizer.web.app import create_app

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
USER_A = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
USER_B = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")


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


def _login(client: TestClient, provider: FakeAuthProvider, email: str) -> None:
    provider.seed_google_user(email=email, display_name=email, user_id=USER_A if email.startswith("a") else USER_B)
    # Replace google_users to only the target for this login
    provider.google_users = {
        email: provider.google_users[email],
    }
    start = client.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state")
    client.get(
        f"/auth/callback?code=fake-google-code&state={state}",
        follow_redirects=False,
    )


def test_repository_user_scoping(tmp_path: Path):
    conn = open_progress_db(tmp_path / "p.db")
    repo = ProgressRepository(conn)
    repo.upsert_progress(
        USER_A,
        unit_id="clause-1",
        status="review",
        times_completed=1,
        last_completed=date(2026, 7, 1),
        next_revision=date(2026, 7, 2),
        interval_days=1,
    )
    repo.upsert_progress(
        USER_B,
        unit_id="clause-1",
        status="mastered",
        times_completed=6,
        last_completed=date(2026, 7, 1),
        next_revision=None,
        interval_days=60,
    )
    assert repo.get_progress(USER_A, "clause-1").status == "review"
    assert repo.get_progress(USER_B, "clause-1").status == "mastered"
    assert len(repo.list_due(USER_A, date(2026, 7, 2))) == 1
    assert len(repo.list_due(USER_B, date(2026, 7, 2))) == 0
    repo.set_setting(USER_A, "theme", "dark")
    repo.set_setting(USER_B, "theme", "light")
    assert repo.get_theme(USER_A) == "dark"
    assert repo.get_theme(USER_B) == "light"


def test_two_user_due_lists_and_progress(tmp_path: Path):
    db = tmp_path / "progress.db"
    engine = ReminderEngine.from_paths(db, MINI_UNITS)
    a = engine.for_user(USER_A)
    b = engine.for_user(USER_B)
    a.mark_all_modes_seen("clause-1")
    a.mark_done("clause-1", as_of=date(2026, 7, 1))
    assert a.due_unit_ids(as_of=date(2026, 7, 2)) == ["clause-1"]
    assert b.due_unit_ids(as_of=date(2026, 7, 2)) == []
    b.mark_all_modes_seen("clause-2")
    b.mark_done("clause-2", as_of=date(2026, 7, 1))
    assert "clause-2" in b.due_unit_ids(as_of=date(2026, 7, 2))
    assert "clause-2" not in a.due_unit_ids(as_of=date(2026, 7, 2))


def test_memory_ownership_404(tmp_path: Path):
    provider = FakeAuthProvider()
    store = InMemorySessionStore()
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "progress.db",
        multiuser=True,
        multiuser_settings=_settings(MEMORY_LOG_ENABLED="true"),
        auth_provider=provider,
        session_store=store,
    )
    client_a = TestClient(app)
    client_b = TestClient(app)

    provider.seed_google_user(user_id=USER_A, email="a@example.com", display_name="A")
    start = client_a.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state")
    client_a.get(f"/auth/callback?code=fake-google-code&state={state}", follow_redirects=False)
    created = client_a.post(
        "/memory",
        data={"title": "A private list", "acronym": "APL"},
        follow_redirects=False,
    )
    entry_id = created.headers["location"].rsplit("/", 1)[-1]

    provider.google_users.clear()
    provider.seed_google_user(user_id=USER_B, email="b@example.com", display_name="B")
    start_b = client_b.get("/auth/google/start", follow_redirects=False)
    state_b = start_b.cookies.get("rtc_oauth_state")
    client_b.get(
        f"/auth/callback?code=fake-google-code&state={state_b}",
        follow_redirects=False,
    )
    assert client_b.get(f"/memory/{entry_id}").status_code == 404
    assert client_b.get(f"/memory/media/{entry_id}").status_code == 404
    assert client_a.get(f"/memory/{entry_id}").status_code == 200


def test_logout_a_does_not_invalidate_b(tmp_path: Path):
    provider = FakeAuthProvider()
    store = InMemorySessionStore()
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "progress.db",
        multiuser=True,
        multiuser_settings=_settings(),
        auth_provider=provider,
        session_store=store,
    )
    client_a = TestClient(app)
    client_b = TestClient(app)

    provider.seed_google_user(user_id=USER_A, email="a@example.com")
    start = client_a.get("/auth/google/start", follow_redirects=False)
    client_a.get(
        f"/auth/callback?code=fake-google-code&state={start.cookies.get('rtc_oauth_state')}",
        follow_redirects=False,
    )
    provider.google_users.clear()
    provider.seed_google_user(user_id=USER_B, email="b@example.com")
    start_b = client_b.get("/auth/google/start", follow_redirects=False)
    client_b.get(
        f"/auth/callback?code=fake-google-code&state={start_b.cookies.get('rtc_oauth_state')}",
        follow_redirects=False,
    )
    assert client_a.get("/dashboard").status_code == 200
    assert client_b.get("/dashboard").status_code == 200
    client_a.post("/logout", follow_redirects=False)
    # Guests see an inline gate (not a redirect wall); B remains signed in.
    gate = client_a.get("/dashboard")
    assert gate.status_code == 200
    assert "Sign in to save 3 Articles to Recall for free" in gate.text
    assert client_b.get("/dashboard").status_code == 200
    assert (
        "Sign in to save 3 Articles to Recall for free"
        not in client_b.get("/dashboard").text
    )


def test_url_cannot_spoof_user(tmp_path: Path):
    """Progress is always read from the session user, not query/form user ids."""
    db = tmp_path / "progress.db"
    repo = ProgressRepository(open_progress_db(db))
    repo.set_setting(USER_A, "theme", "dark")
    repo.set_setting(USER_B, "theme", "light")

    provider = FakeAuthProvider()
    provider.seed_google_user(user_id=USER_A, email="a@example.com")
    app = create_app(
        units_path=MINI_UNITS,
        db_path=db,
        multiuser=True,
        multiuser_settings=_settings(),
        auth_provider=provider,
        session_store=InMemorySessionStore(),
    )
    client = TestClient(app)
    start = client.get("/auth/google/start", follow_redirects=False)
    client.get(
        f"/auth/callback?code=fake-google-code&state={start.cookies.get('rtc_oauth_state')}",
        follow_redirects=False,
    )
    # Attempt to pass another user id — ignored.
    client.post("/api/theme", data={"theme": "auto", "user_id": str(USER_B)})
    assert repo.get_theme(USER_A) == "auto"
    assert repo.get_theme(USER_B) == "light"
