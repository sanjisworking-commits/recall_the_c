"""Request-scoped diagnostic timings for Dashboard and Browse."""

from __future__ import annotations

import logging
from pathlib import Path
from time import perf_counter
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import InMemorySessionStore
from constitution_memorizer.multiuser.settings import MultiUserSettings, clear_settings_cache
from constitution_memorizer.progress.db import open_progress_db
from constitution_memorizer.progress.repository import ProgressRepository
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.request_context import (
    begin_request_timings,
    record_request_timing,
    reset_request_timings,
    snapshot_request_timings,
)


class CountingProgressRepo:
    """Wraps a real SQLite repo and counts get_progress / list_all_progress."""

    def __init__(self, inner: ProgressRepository) -> None:
        self.inner = inner
        self.get_progress_calls = 0
        self.list_all_progress_calls = 0
        self.list_due_calls = 0
        self.count_by_status_calls = 0
        self.get_profile_calls = 0
        self.list_split_preferences_calls = 0
        self.get_split_preference_calls = 0
        self.load_request_bootstrap_calls = 0

    def __getattr__(self, name: str):
        return getattr(self.inner, name)

    def get_progress(self, user_id, unit_id: str):
        self.get_progress_calls += 1
        return self.inner.get_progress(user_id, unit_id)

    def list_all_progress(self, user_id):
        self.list_all_progress_calls += 1
        return self.inner.list_all_progress(user_id)

    def list_due(self, user_id, as_of, *, include_new: bool = False):
        self.list_due_calls += 1
        return self.inner.list_due(user_id, as_of, include_new=include_new)

    def count_by_status(self, user_id):
        self.count_by_status_calls += 1
        return self.inner.count_by_status(user_id)

    def get_profile(self, user_id):
        self.get_profile_calls += 1
        return self.inner.get_profile(user_id)

    def list_split_preferences(self, user_id):
        self.list_split_preferences_calls += 1
        return self.inner.list_split_preferences(user_id)

    def get_split_preference(self, user_id, parent_clause_id: str):
        self.get_split_preference_calls += 1
        return self.inner.get_split_preference(user_id, parent_clause_id)

    def load_request_bootstrap(self, user_id, **kwargs):
        self.load_request_bootstrap_calls += 1
        return self.inner.load_request_bootstrap(user_id, **kwargs)

    def reset_counts(self) -> None:
        self.get_progress_calls = 0
        self.list_all_progress_calls = 0
        self.list_due_calls = 0
        self.count_by_status_calls = 0
        self.get_profile_calls = 0
        self.list_split_preferences_calls = 0
        self.get_split_preference_calls = 0
        self.load_request_bootstrap_calls = 0

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
USER = UUID("11111111-1111-4111-8111-111111111111")
USER_EMAIL = "a@example.com"


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


def test_record_timing_noops_outside_request():
    started = perf_counter()
    record_request_timing("profile", started)
    assert snapshot_request_timings() == {}


def test_roadmap_sync_stage_is_whitelisted():
    token = begin_request_timings()
    try:
        record_request_timing("roadmap_sync", perf_counter() - 0.01)
        total_ms, count = snapshot_request_timings()["roadmap_sync"]
        assert count == 1
        assert total_ms > 0
    finally:
        reset_request_timings(token)


def test_unknown_stage_is_rejected():
    with pytest.raises(ValueError, match="Unknown request timing stage"):
        record_request_timing("not_a_stage", perf_counter())
    token = begin_request_timings()
    try:
        with pytest.raises(ValueError, match="Unknown request timing stage"):
            record_request_timing("sql", perf_counter())
        assert snapshot_request_timings() == {}
    finally:
        reset_request_timings(token)


def test_repeated_stages_accumulate_duration_and_count():
    token = begin_request_timings()
    try:
        record_request_timing("theme", perf_counter() - 0.01)
        record_request_timing("theme", perf_counter() - 0.02)
        snapshot = snapshot_request_timings()
        total_ms, count = snapshot["theme"]
        assert count == 2
        assert total_ms > 0
    finally:
        reset_request_timings(token)


def test_snapshot_is_independent_copy():
    token = begin_request_timings()
    try:
        record_request_timing("profile", perf_counter() - 0.01)
        snapshot = snapshot_request_timings()
        record_request_timing("profile", perf_counter() - 0.01)
        live = snapshot_request_timings()
        assert snapshot["profile"][1] == 1
        assert live["profile"][1] == 2
        snapshot["profile"] = (0.0, 99)
        assert snapshot_request_timings()["profile"][1] == 2
    finally:
        reset_request_timings(token)
    after_reset = snapshot_request_timings()
    assert after_reset == {}
    assert snapshot["profile"] == (0.0, 99)


def _counting_client(tmp_path: Path) -> tuple[TestClient, CountingProgressRepo]:
    conn = open_progress_db(tmp_path / "progress.db")
    repo = CountingProgressRepo(ProgressRepository(conn))
    provider = FakeAuthProvider()
    provider.seed_google_user(
        user_id=USER,
        email=USER_EMAIL,
        display_name="Test User",
    )
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "unused.db",
        multiuser=True,
        multiuser_settings=_settings(),
        auth_provider=provider,
        session_store=InMemorySessionStore(),
        progress_repo=repo,
    )
    client = TestClient(app)
    start = client.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state")
    cb = client.get(
        f"/auth/callback?code=fake-google-code&state={state}",
        follow_redirects=False,
    )
    assert cb.status_code == 303
    repo.reset_counts()
    return client, repo


def _breakdown_messages(caplog: logging.LogCaptureFixture) -> list[str]:
    return [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("request_breakdown ")
    ]


def test_authenticated_dashboard_keeps_one_profile_and_progress(tmp_path: Path):
    client, repo = _counting_client(tmp_path)
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert repo.load_request_bootstrap_calls == 1
    assert repo.get_profile_calls == 0
    assert repo.list_all_progress_calls == 0
    assert repo.list_due_calls == 0
    assert repo.count_by_status_calls == 0


def test_authenticated_browse_keeps_one_progress_list(tmp_path: Path):
    client, repo = _counting_client(tmp_path)
    resp = client.get("/browse")
    assert resp.status_code == 200
    assert repo.load_request_bootstrap_calls == 1
    assert repo.list_all_progress_calls == 0
    assert repo.list_due_calls == 0


def test_authenticated_dashboard_breakdown_includes_auth_session(
    tmp_path: Path, caplog: logging.LogCaptureFixture
):
    client, _repo = _counting_client(tmp_path)
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        caplog.clear()
        resp = client.get("/dashboard")
    assert resp.status_code == 200
    messages = _breakdown_messages(caplog)
    assert len(messages) == 1
    line = messages[0]
    assert "path=/dashboard" in line
    assert "auth_session_n=1" in line
    assert "request_bootstrap_n=1" in line
    assert "progress_preload_" not in line
    assert "split_prefs_" not in line
    assert "news_setting_" not in line
    assert "theme_" not in line
    assert "dashboard_build_n=" in line
    assert "template_n=" in line


def test_health_and_static_emit_no_timing_or_breakdown(
    tmp_path: Path, caplog: logging.LogCaptureFixture
):
    client, _repo = _counting_client(tmp_path)
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        caplog.clear()
        assert client.get("/health").status_code == 200
        assert client.get("/static/styles.css").status_code == 200
        joined = " ".join(record.getMessage() for record in caplog.records)
    assert "request method=" not in joined
    assert "request_breakdown" not in joined


def test_breakdown_logs_omit_sensitive_data(
    tmp_path: Path, caplog: logging.LogCaptureFixture
):
    client, _repo = _counting_client(tmp_path)
    session_cookie = client.cookies.get("rtc_session") or ""
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        caplog.clear()
        dash = client.get("/dashboard?done=clause-1")
        browse = client.get("/browse")
    assert dash.status_code == 200
    assert browse.status_code == 200
    joined = "\n".join(record.getMessage() for record in caplog.records)
    assert "request_breakdown" in joined
    assert "path=/dashboard" in joined
    assert "path=/browse" in joined
    assert "done=clause-1" not in joined
    assert "?" not in joined
    assert str(USER) not in joined
    assert USER_EMAIL not in joined
    assert "DATABASE_URL" not in joined
    assert "postgresql://" not in joined
    if session_cookie:
        assert session_cookie not in joined
    assert "cookie" not in joined.lower()
    assert "token" not in joined.lower()
    assert "phone" not in joined.lower()
