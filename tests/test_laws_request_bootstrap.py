"""One batched read for authenticated Laws pages.

Production measured a warm authenticated /laws at 656 ms, of which
theme_ms=217.7, onboarding_setting_ms=217.1 and nav_due_ms=217.5 — three
independent cross-region reads for chrome the page barely uses. Guests, who
short-circuit all three, ran the same routes in single-digit ms.

These tests pin the shape rather than a duration: one bootstrap for a signed-in
request, none at all for a guest.
"""

from __future__ import annotations

import logging
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
from constitution_memorizer.progress.db import open_progress_db
from constitution_memorizer.progress.repository import ProgressRepository
from constitution_memorizer.web.app import create_app

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
USER = UUID("11111111-1111-4111-8111-111111111111")

LAWS_PATHS = (
    "/laws",
    "/laws/ndps",
    "/laws/ndps/section/1",
    "/laws/ndps/schedule/psychotropic-substances",
)


class CountingRepo:
    """Counts the reads the shared template context would make on its own."""

    def __init__(self, inner: ProgressRepository) -> None:
        self.inner = inner
        self.reset()

    def __getattr__(self, name: str):
        return getattr(self.inner, name)

    def reset(self) -> None:
        self.bootstrap_calls = 0
        self.bootstrap_kwargs: list[dict] = []
        self.get_theme_calls = 0
        self.get_setting_calls = 0
        self.list_due_calls = 0
        self.list_all_progress_calls = 0
        self.list_split_preferences_calls = 0
        self.get_split_preference_calls = 0
        self.claimed_articles_calls = 0
        self.modes_seen_calls = 0

    def load_request_bootstrap(self, user_id, **kwargs):
        self.bootstrap_calls += 1
        self.bootstrap_kwargs.append(dict(kwargs))
        return self.inner.load_request_bootstrap(user_id, **kwargs)

    def get_theme(self, user_id):
        self.get_theme_calls += 1
        return self.inner.get_theme(user_id)

    def get_setting(self, user_id, key):
        self.get_setting_calls += 1
        return self.inner.get_setting(user_id, key)

    def list_due(self, user_id, as_of, *, include_new: bool = False):
        self.list_due_calls += 1
        return self.inner.list_due(user_id, as_of, include_new=include_new)

    def list_all_progress(self, user_id):
        self.list_all_progress_calls += 1
        return self.inner.list_all_progress(user_id)

    def list_split_preferences(self, user_id):
        self.list_split_preferences_calls += 1
        return self.inner.list_split_preferences(user_id)

    def get_split_preference(self, user_id, parent_clause_id: str):
        self.get_split_preference_calls += 1
        return self.inner.get_split_preference(user_id, parent_clause_id)

    def claimed_articles(self, user_id):
        self.claimed_articles_calls += 1
        return self.inner.claimed_articles(user_id)

    def modes_seen(self, user_id, unit_id):
        self.modes_seen_calls += 1
        return self.inner.modes_seen(user_id, unit_id)

    @property
    def independent_context_reads(self) -> int:
        """Reads the context processor made outside any bootstrap."""
        return (
            self.get_theme_calls
            + self.get_setting_calls
            + self.list_due_calls
            + self.list_all_progress_calls
            + self.list_split_preferences_calls
            + self.get_split_preference_calls
        )


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


def _client(tmp_path: Path, *, signed_in: bool) -> tuple[TestClient, CountingRepo]:
    conn = open_progress_db(tmp_path / "progress.db")
    repo = CountingRepo(ProgressRepository(conn))
    provider = FakeAuthProvider()
    provider.seed_google_user(
        user_id=USER, email="a@example.com", display_name="A"
    )
    client = TestClient(
        create_app(
            units_path=MINI_UNITS,
            db_path=tmp_path / "unused.db",
            multiuser=True,
            multiuser_settings=_settings(),
            auth_provider=provider,
            session_store=InMemorySessionStore(),
            progress_repo=repo,
        )
    )
    if signed_in:
        start = client.get("/auth/google/start", follow_redirects=False)
        state = start.cookies.get("rtc_oauth_state")
        client.get(
            f"/auth/callback?code=fake-google-code&state={state}",
            follow_redirects=False,
        )
    for path in LAWS_PATHS:  # warm the Act cache and Jinja compilation
        client.get(path)
    repo.reset()
    return client, repo


def _breakdowns(caplog: logging.LogCaptureFixture) -> list[str]:
    return [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("request_breakdown ")
    ]


# ── Guest fast path must not change ───────────────────────────────────────


@pytest.mark.parametrize("path", LAWS_PATHS)
def test_guest_laws_never_bootstraps(tmp_path: Path, path: str):
    client, repo = _client(tmp_path, signed_in=False)
    assert client.get(path).status_code == 200
    assert repo.bootstrap_calls == 0, path
    assert repo.independent_context_reads == 0, path


def test_guest_output_is_byte_identical_to_before_the_change(tmp_path: Path):
    """Nothing about a guest request changed, including the rendered page."""
    client, repo = _client(tmp_path, signed_in=False)
    first = {path: client.get(path).text for path in LAWS_PATHS}
    second = {path: client.get(path).text for path in LAWS_PATHS}
    assert first == second
    assert repo.bootstrap_calls == 0


# ── Authenticated: one bootstrap, no independent reads ────────────────────


@pytest.mark.parametrize("path", LAWS_PATHS)
def test_authenticated_laws_bootstraps_exactly_once(tmp_path: Path, path: str):
    client, repo = _client(tmp_path, signed_in=True)
    assert client.get(path).status_code == 200
    assert repo.bootstrap_calls == 1, path
    # theme, onboarding and the due count all come from the seeded caches.
    assert repo.get_theme_calls == 0, path
    assert repo.get_setting_calls == 0, path
    assert repo.list_due_calls == 0, path
    assert repo.list_all_progress_calls == 0, path
    assert repo.list_split_preferences_calls == 0, path
    assert repo.get_split_preference_calls == 0, path


@pytest.mark.parametrize("path", LAWS_PATHS)
def test_no_optional_packs_are_requested(tmp_path: Path, path: str):
    """Laws needs none of them; asking would trade three reads for a bigger one."""
    client, repo = _client(tmp_path, signed_in=True)
    client.get(path)
    assert len(repo.bootstrap_kwargs) == 1, path
    kwargs = repo.bootstrap_kwargs[0]
    for pack in ("include_account", "include_modes", "include_news", "include_profile"):
        assert kwargs.get(pack, False) is False, f"{path}: {pack}"
    assert repo.claimed_articles_calls == 0, path
    assert repo.modes_seen_calls == 0, path


def test_the_bootstrap_is_scoped_to_laws(tmp_path: Path):
    """Not a global middleware: an unrelated authenticated page is untouched."""
    client, repo = _client(tmp_path, signed_in=True)
    client.get("/tables")
    assert repo.bootstrap_calls == 0


# ── Instrumentation from #180 must survive ────────────────────────────────


def test_authenticated_breakdown_shows_one_bootstrap_and_no_db_waits(
    tmp_path: Path, caplog: logging.LogCaptureFixture
):
    client, _repo = _client(tmp_path, signed_in=True)
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        caplog.clear()
        assert client.get("/laws/ndps").status_code == 200
    line = _breakdowns(caplog)[0]
    assert "auth_state=authed" in line
    assert "request_bootstrap_n=1" in line
    assert "bare_act_cache=hit" in line
    assert "template_ms=" in line
    # These three stages are recorded only on the repo path, so their absence
    # is the proof that no independent read happened. nav_due stays, timed at
    # its call site — it is now cache work, the same shape /browse has.
    assert "theme_ms" not in line
    assert "onboarding_setting_ms" not in line
    assert "split_prefs_ms" not in line


def test_guest_breakdown_is_unchanged(
    tmp_path: Path, caplog: logging.LogCaptureFixture
):
    client, _repo = _client(tmp_path, signed_in=False)
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        caplog.clear()
        assert client.get("/laws/ndps").status_code == 200
    line = _breakdowns(caplog)[0]
    assert "auth_state=guest" in line
    assert "request_bootstrap" not in line
    assert "theme_ms" not in line
    assert "onboarding_setting_ms" not in line
    assert "nav_due_ms" not in line


# ── Same values, same pages ───────────────────────────────────────────────


@pytest.mark.parametrize("path", LAWS_PATHS)
def test_context_values_survive_the_bootstrap(tmp_path: Path, path: str):
    """Same values, same templates — only the number of reads changed."""
    client, _repo = _client(tmp_path, signed_in=True)
    html = client.get(path).text
    assert 'data-theme-preference="' in html
    assert "data-mscreen=" in html
    assert "is-authed" in html


def test_bare_act_content_is_untouched(tmp_path: Path):
    client, _repo = _client(tmp_path, signed_in=True)
    chapters = client.get("/laws/ndps").text
    assert "The Narcotic Drugs and Psychotropic Substances Act, 1985" in chapters
    assert chapters.count("<details") == 8
    section = client.get("/laws/ndps/section/1").text
    assert "Short title, extent and commencement" in section
    assert "to all citizens of India outside India" in section
    schedule = client.get(
        "/laws/ndps/schedule/psychotropic-substances"
    ).text
    assert schedule.count("<tr>") == 163  # header + 162 entries
