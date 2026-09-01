"""Bundled request bootstrap seeds caches and collapses Postgres round trips."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import InMemorySessionStore
from constitution_memorizer.learning.schemas import LearningUnitsDocument
from constitution_memorizer.multiuser.settings import MultiUserSettings, clear_settings_cache
from constitution_memorizer.progress.db import open_progress_db
from constitution_memorizer.progress.postgres_repository import PostgresProgressRepository
from constitution_memorizer.progress.repository import (
    DEFAULT_NEWS_ARTICLES,
    DEFAULT_THEME,
    LEARN_MODES,
    ProgressRepository,
)
from constitution_memorizer.progress.scheduler import ReminderEngine
from constitution_memorizer.utils.json_io import read_json
from constitution_memorizer.web.app import create_app

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
USER = UUID("11111111-1111-4111-8111-111111111111")
USER_EMAIL = "a@example.com"


class CountingProgressRepo:
    def __init__(self, inner: ProgressRepository) -> None:
        self.inner = inner
        self.reset_counts()

    def __getattr__(self, name: str):
        return getattr(self.inner, name)

    def reset_counts(self) -> None:
        self.get_progress_calls = 0
        self.list_all_progress_calls = 0
        self.list_due_calls = 0
        self.count_by_status_calls = 0
        self.get_profile_calls = 0
        self.list_split_preferences_calls = 0
        self.get_split_preference_calls = 0
        self.get_theme_calls = 0
        self.get_news_articles_raw_calls = 0
        self.get_setting_calls = 0
        self.modes_seen_calls = 0
        self.load_request_bootstrap_calls = 0
        self.get_notification_frequency_calls = 0
        self.claimed_articles_calls = 0
        self.latest_paid_billing_order_calls = 0
        self.claim_article_calls = 0
        self.set_setting_calls = 0
        self.get_gloss_calls = 0
        self.list_daily_goal_dates_calls = 0
        self.last_bootstrap_kwargs = None

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

    def get_theme(self, user_id):
        self.get_theme_calls += 1
        return self.inner.get_theme(user_id)

    def get_news_articles_raw(self, user_id):
        self.get_news_articles_raw_calls += 1
        return self.inner.get_news_articles_raw(user_id)

    def get_setting(self, user_id, key: str):
        self.get_setting_calls += 1
        return self.inner.get_setting(user_id, key)

    def modes_seen(self, user_id, unit_id: str):
        self.modes_seen_calls += 1
        return self.inner.modes_seen(user_id, unit_id)

    def get_notification_frequency(self, user_id):
        self.get_notification_frequency_calls += 1
        return self.inner.get_notification_frequency(user_id)

    def claimed_articles(self, user_id):
        self.claimed_articles_calls += 1
        return self.inner.claimed_articles(user_id)

    def latest_paid_billing_order(self, user_id):
        self.latest_paid_billing_order_calls += 1
        return self.inner.latest_paid_billing_order(user_id)

    def claim_article(self, user_id, article_number):
        self.claim_article_calls += 1
        return self.inner.claim_article(user_id, article_number)

    def set_setting(self, user_id, key: str, value: str):
        self.set_setting_calls += 1
        return self.inner.set_setting(user_id, key, value)

    def get_gloss(self, user_id, article_number: str):
        self.get_gloss_calls += 1
        return self.inner.get_gloss(user_id, article_number)

    def list_daily_goal_dates(self, user_id, *, until, limit: int = 400):
        self.list_daily_goal_dates_calls += 1
        return self.inner.list_daily_goal_dates(user_id, until=until, limit=limit)

    def load_request_bootstrap(self, user_id, **kwargs):
        self.load_request_bootstrap_calls += 1
        self.last_bootstrap_kwargs = dict(kwargs)
        return self.inner.load_request_bootstrap(user_id, **kwargs)


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


def _catalog() -> dict:
    doc = LearningUnitsDocument.model_validate(read_json(MINI_UNITS))
    return {u.id: u for u in doc.units}


def _seeded_engine(tmp_path: Path) -> tuple[CountingProgressRepo, ReminderEngine]:
    conn = open_progress_db(tmp_path / "progress.db")
    repo = CountingProgressRepo(ProgressRepository(conn))
    engine = ReminderEngine.from_repository(repo, _catalog(), user_id=USER)
    engine.mark_all_modes_seen("clause-1")
    engine.mark_done("clause-1", as_of=date(2026, 7, 20))
    engine.set_split_preference("clause-2", "letters")
    engine.set_theme("dark")
    engine.set_news_articles_raw("14,21")
    engine._invalidate_progress_cache()
    engine._invalidate_split_cache()
    engine._invalidate_theme_cache()
    engine._invalidate_news_cache()
    repo.reset_counts()
    return repo, engine


def test_bootstrap_seeds_caches_and_matches_uncached(tmp_path: Path):
    repo, engine = _seeded_engine(tmp_path)
    as_of = date(2026, 7, 21)
    uncached = ReminderEngine.from_repository(repo.inner, engine.units, user_id=USER)
    expected_due = [row.learning_unit_id for row in uncached.due_today(as_of=as_of)]
    expected_stats = uncached.stats()
    expected_theme = uncached.get_theme()
    expected_news = uncached.get_news_articles_raw()
    repo.reset_counts()

    bundle = engine.bootstrap_request(include_news=True)
    assert repo.load_request_bootstrap_calls == 1
    repo.reset_counts()

    assert engine.get_theme() == expected_theme == "dark"
    assert engine.get_news_articles_raw() == expected_news == "14,21"
    assert engine.get_progress("clause-1") is not None
    assert engine.get_split_preference("clause-2") == "letters"
    assert [row.learning_unit_id for row in engine.due_today(as_of=as_of)] == expected_due
    assert engine.stats()["review"] == expected_stats["review"]
    assert engine.stats()["tracked"] == expected_stats["tracked"]
    assert bundle.theme == "dark"
    assert repo.get_theme_calls == 0
    assert repo.get_news_articles_raw_calls == 0
    assert repo.list_all_progress_calls == 0
    assert repo.list_split_preferences_calls == 0
    assert repo.list_due_calls == 0
    assert repo.count_by_status_calls == 0
    assert repo.get_split_preference_calls == 0
    assert repo.load_request_bootstrap_calls == 0


def test_empty_bootstrap_does_not_fallback(tmp_path: Path):
    conn = open_progress_db(tmp_path / "empty.db")
    repo = CountingProgressRepo(ProgressRepository(conn))
    engine = ReminderEngine.from_repository(repo, _catalog(), user_id=USER)
    engine.bootstrap_request(include_news=True)
    repo.reset_counts()
    assert engine._progress_cache == {}
    assert engine._split_cache == {}
    assert engine.get_theme() == DEFAULT_THEME
    assert engine.get_news_articles_raw() == DEFAULT_NEWS_ARTICLES
    assert engine.due_today(as_of=date(2026, 7, 21)) == []
    assert engine.stats()["tracked"] == 0
    assert repo.list_all_progress_calls == 0
    assert repo.list_due_calls == 0
    assert repo.count_by_status_calls == 0
    assert repo.get_theme_calls == 0
    assert repo.get_news_articles_raw_calls == 0


def test_loaded_empty_news_cache_does_not_query(tmp_path: Path):
    conn = open_progress_db(tmp_path / "news.db")
    repo = CountingProgressRepo(ProgressRepository(conn))
    engine = ReminderEngine.from_repository(repo, _catalog(), user_id=USER)
    engine._news_cache = ""
    assert engine.get_news_articles_raw() == ""
    assert repo.get_news_articles_raw_calls == 0
    assert repo.get_setting_calls == 0
    engine._news_cache = None
    assert engine.get_news_articles_raw() == DEFAULT_NEWS_ARTICLES
    assert repo.get_news_articles_raw_calls == 1


def _counting_client(
    tmp_path: Path, **settings_overrides
) -> tuple[TestClient, CountingProgressRepo]:
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
        multiuser_settings=_settings(**settings_overrides),
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


def test_authenticated_dashboard_one_bootstrap(tmp_path: Path):
    client, repo = _counting_client(tmp_path)
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert "Welcome, Test." in resp.text or "Good morning, Test." in resp.text
    assert repo.load_request_bootstrap_calls == 1
    assert repo.get_profile_calls == 0
    assert repo.list_all_progress_calls == 0
    assert repo.list_split_preferences_calls == 0
    assert repo.get_theme_calls == 0
    assert repo.list_due_calls == 0
    assert repo.modes_seen_calls == 0


def test_authenticated_browse_one_bootstrap(tmp_path: Path):
    client, repo = _counting_client(tmp_path)
    resp = client.get("/browse")
    assert resp.status_code == 200
    assert repo.load_request_bootstrap_calls == 1
    assert repo.list_all_progress_calls == 0
    assert repo.list_split_preferences_calls == 0
    assert repo.get_news_articles_raw_calls == 0
    assert repo.get_theme_calls == 0
    assert repo.list_due_calls == 0


def test_guest_browse_does_not_bootstrap(tmp_path: Path):
    conn = open_progress_db(tmp_path / "progress.db")
    repo = CountingProgressRepo(ProgressRepository(conn))
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "unused.db",
        multiuser=True,
        multiuser_settings=_settings(),
        auth_provider=FakeAuthProvider(),
        session_store=InMemorySessionStore(),
        progress_repo=repo,
    )
    client = TestClient(app)
    resp = client.get("/browse")
    assert resp.status_code == 200
    assert repo.load_request_bootstrap_calls == 0
    assert 'aria-label="' not in resp.text or "due or overdue" not in resp.text


def _guest_client(tmp_path: Path) -> tuple[TestClient, CountingProgressRepo]:
    conn = open_progress_db(tmp_path / "progress.db")
    repo = CountingProgressRepo(ProgressRepository(conn))
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "unused.db",
        multiuser=True,
        multiuser_settings=_settings(),
        auth_provider=FakeAuthProvider(),
        session_store=InMemorySessionStore(),
        progress_repo=repo,
    )
    return TestClient(app), repo


def test_guest_browse_article_does_not_bootstrap(tmp_path: Path):
    client, repo = _guest_client(tmp_path)
    resp = client.get("/browse/article/20")
    assert resp.status_code == 200
    assert repo.load_request_bootstrap_calls == 0
    assert "Learn this Article" in resp.text


def test_authenticated_browse_article_one_bootstrap(
    tmp_path: Path, caplog: logging.LogCaptureFixture
):
    client, repo = _counting_client(tmp_path, ARTICLE_ENTITLEMENTS_ENABLED="true")
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        caplog.clear()
        resp = client.get("/browse/article/20")
    assert resp.status_code == 200
    assert "Learn this Article" in resp.text
    assert repo.load_request_bootstrap_calls == 1
    assert repo.last_bootstrap_kwargs is not None
    assert repo.last_bootstrap_kwargs.get("include_news") is True
    assert repo.last_bootstrap_kwargs.get("include_account") is True
    assert repo.list_all_progress_calls == 0
    assert repo.list_split_preferences_calls == 0
    assert repo.get_theme_calls == 0
    assert repo.get_news_articles_raw_calls == 0
    assert repo.claimed_articles_calls == 0
    assert repo.get_setting_calls == 0
    assert repo.get_gloss_calls == 1
    line = _breakdown_messages(caplog)[0]
    assert "path=/browse/article/20" in line
    assert "request_bootstrap_n=1" in line
    assert "gloss_read_n=1" in line
    assert "access_override_n=1" in line
    assert "progress_preload_" not in line
    assert "split_prefs_" not in line
    assert "news_setting_" not in line
    assert "theme_" not in line
    assert "free_articles_backfill_check_" not in line
    assert "claimed_articles_" not in line


def _assert_progress_query_shape(repo: CountingProgressRepo) -> None:
    assert repo.load_request_bootstrap_calls == 1
    assert repo.last_bootstrap_kwargs is not None
    assert repo.last_bootstrap_kwargs.get("include_account") is not True
    assert repo.list_all_progress_calls == 0
    assert repo.list_split_preferences_calls == 0
    assert repo.get_theme_calls == 0
    assert repo.count_by_status_calls == 0
    assert repo.list_daily_goal_dates_calls == 1


def test_authenticated_progress_one_bootstrap(
    tmp_path: Path, caplog: logging.LogCaptureFixture
):
    client, repo = _counting_client(tmp_path)
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        caplog.clear()
        resp = client.get("/progress")
    assert resp.status_code == 200
    _assert_progress_query_shape(repo)
    line = _breakdown_messages(caplog)[0]
    assert "path=/progress" in line
    assert "request_bootstrap_n=1" in line
    assert "progress_dashboard_n=1" in line
    assert "progress_continue_n=1" in line
    assert "progress_stats_n=1" in line
    assert "progress_articles_n=1" in line
    assert "progress_map_n=1" in line
    assert "progress_recent_n=1" in line
    assert "daily_goal_read_n=1" in line
    assert "progress_preload_" not in line
    assert "split_prefs_" not in line
    assert "theme_" not in line


def test_authenticated_progress_mastered_matches_progress_shape(
    tmp_path: Path, caplog: logging.LogCaptureFixture
):
    client, repo = _counting_client(tmp_path)
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        caplog.clear()
        resp = client.get("/progress/mastered")
    assert resp.status_code == 200
    _assert_progress_query_shape(repo)
    line = _breakdown_messages(caplog)[0]
    assert "path=/progress/mastered" in line
    assert "request_bootstrap_n=1" in line
    assert "progress_dashboard_n=1" in line
    assert "progress_continue_n=1" in line
    assert "daily_goal_read_n=1" in line
    assert "progress_preload_" not in line
    assert "split_prefs_" not in line
    assert "theme_" not in line


def test_blank_profile_still_redirects_to_welcome(tmp_path: Path):
    client, repo = _counting_client(tmp_path)
    repo.inner.upsert_profile(USER, display_name="   ", avatar_url=None)
    repo.reset_counts()
    resp = client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/welcome"
    assert repo.load_request_bootstrap_calls == 1


def test_signed_in_calendar_one_bootstrap(
    tmp_path: Path, caplog: logging.LogCaptureFixture
):
    client, repo = _counting_client(tmp_path)
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        caplog.clear()
        resp = client.get("/calendar")
    assert resp.status_code == 200
    assert repo.load_request_bootstrap_calls == 1
    assert repo.list_all_progress_calls == 0
    assert repo.get_theme_calls == 0
    line = _breakdown_messages(caplog)[0]
    assert "path=/calendar" in line
    assert "request_bootstrap_n=1" in line
    assert "progress_preload_" not in line
    assert "theme_" not in line


def test_guest_calendar_redirects_without_bootstrap(tmp_path: Path):
    conn = open_progress_db(tmp_path / "progress.db")
    repo = CountingProgressRepo(ProgressRepository(conn))
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "unused.db",
        multiuser=True,
        multiuser_settings=_settings(),
        auth_provider=FakeAuthProvider(),
        session_store=InMemorySessionStore(),
        progress_repo=repo,
    )
    client = TestClient(app)
    resp = client.get("/calendar", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/login")
    assert repo.load_request_bootstrap_calls == 0


def test_single_user_calendar_bootstraps(
    tmp_path: Path, caplog: logging.LogCaptureFixture
):
    conn = open_progress_db(tmp_path / "progress.db")
    repo = CountingProgressRepo(ProgressRepository(conn))
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "unused.db",
        progress_repo=repo,
    )
    client = TestClient(app)
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        caplog.clear()
        resp = client.get("/calendar")
    assert resp.status_code == 200
    assert repo.load_request_bootstrap_calls == 1
    assert repo.list_all_progress_calls == 0
    line = _breakdown_messages(caplog)[0]
    assert "request_bootstrap_n=1" in line
    assert "progress_preload_" not in line
    assert "theme_" not in line


def test_dashboard_browse_breakdown_has_single_bootstrap(
    tmp_path: Path, caplog: logging.LogCaptureFixture
):
    client, _repo = _counting_client(tmp_path)
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        caplog.clear()
        assert client.get("/dashboard").status_code == 200
        dash = _breakdown_messages(caplog)
        caplog.clear()
        assert client.get("/browse").status_code == 200
        browse = _breakdown_messages(caplog)
    assert len(dash) == 1
    assert "auth_session_n=1" in dash[0]
    assert "request_bootstrap_n=1" in dash[0]
    assert "dashboard_prep_n=1" in dash[0]
    assert "progress_preload_" not in dash[0]
    assert "split_prefs_" not in dash[0]
    assert "theme_" not in dash[0]
    assert len(browse) == 1
    assert "request_bootstrap_n=1" in browse[0]
    assert "news_setting_" not in browse[0]
    assert "theme_" not in browse[0]


class _FakeCursor:
    def __init__(self, conn: "_FakeConnection") -> None:
        self.conn = conn
        self.closed = False
        self._kind: str | None = None

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, *exc: object) -> None:
        self.closed = True

    def execute(self, sql: str, params=None) -> None:
        self.conn.events.append(("execute", sql, params))
        text = " ".join(sql.split()).lower()
        if "learning_unit_progress" in text:
            self._kind = "progress"
        elif "split_preference" in text:
            self._kind = "split"
        elif "app_settings" in text:
            self._kind = "settings"
        elif "user_profile" in text:
            self._kind = "profile"
        elif "unit_modes_seen" in text:
            self._kind = "modes"
        elif "user_free_articles" in text:
            self._kind = "claims"
        elif "billing_orders" in text:
            self._kind = "billing"
        else:
            self._kind = "other"

    def fetchall(self):
        self.conn.events.append(("fetchall", self._kind))
        return list(self.conn.results.get(self._kind, []))

    def fetchone(self):
        self.conn.events.append(("fetchone", self._kind))
        rows = self.conn.results.get(self._kind, [])
        return rows[0] if rows else None


class _FakeConnection:
    def __init__(self, results: dict[str, list]) -> None:
        self.results = results
        self.events: list[tuple] = []
        self.cursors: list[_FakeCursor] = []
        self.pipeline_entries = 0

    def cursor(self, row_factory=None):
        cur = _FakeCursor(self)
        self.cursors.append(cur)
        return cur

    @contextmanager
    def pipeline(self):
        self.pipeline_entries += 1
        self.events.append(("pipeline_enter",))
        yield
        self.events.append(("pipeline_exit",))

    def __enter__(self) -> "_FakeConnection":
        return self

    def __exit__(self, *exc: object) -> None:
        return None


class _FakePool:
    def __init__(self, conn: _FakeConnection) -> None:
        self.conn = conn
        self.borrows = 0

    @contextmanager
    def connection(self):
        self.borrows += 1
        yield self.conn


def _progress_row() -> dict:
    return {
        "learning_unit_id": "clause-1",
        "status": "review",
        "times_completed": 1,
        "last_completed": date(2026, 7, 20),
        "next_revision": date(2026, 7, 21),
        "interval_days": 1,
        "ease_factor": 2.5,
        "created_at": "2026-07-20T00:00:00+00:00",
        "updated_at": "2026-07-20T00:00:00+00:00",
    }


def test_postgres_pipeline_queues_executes_before_fetch(monkeypatch: pytest.MonkeyPatch):
    conn = _FakeConnection(
        {
            "progress": [_progress_row()],
            "split": [{"parent_clause_id": "clause-2", "mode": "letters"}],
            "settings": [
                {"key": "theme", "value": "dark"},
                {"key": "news_articles", "value": "14"},
            ],
            "profile": [
                {
                    "user_id": USER,
                    "display_name": "Ada",
                    "avatar_url": None,
                    "created_at": "2026-07-20T00:00:00+00:00",
                    "updated_at": "2026-07-20T00:00:00+00:00",
                }
            ],
        }
    )
    pool = _FakePool(conn)
    monkeypatch.setattr(
        "constitution_memorizer.progress.postgres_repository._pipeline_supported",
        lambda: True,
    )
    repo = PostgresProgressRepository(pool)
    bundle = repo.load_request_bootstrap(USER, include_profile=True, include_news=True)
    assert pool.borrows == 1
    assert conn.pipeline_entries == 1
    kinds = [event[0] for event in conn.events]
    first_fetch = next(
        i for i, kind in enumerate(kinds) if kind in {"fetchall", "fetchone"}
    )
    assert kinds[:first_fetch].count("execute") == 4
    assert "fetchall" not in kinds[:first_fetch]
    assert "fetchone" not in kinds[:first_fetch]
    assert all(cur.closed for cur in conn.cursors)
    assert len(bundle.progress) == 1
    assert bundle.progress[0].learning_unit_id == "clause-1"
    assert bundle.split_preferences == {"clause-2": "letters"}
    assert bundle.theme == "dark"
    assert bundle.news_articles_raw == "14"
    assert bundle.profile is not None
    assert bundle.profile["display_name"] == "Ada"
    assert bundle.settings == {"theme": "dark", "news_articles": "14"}
    assert bundle.modes_seen_by_unit is None
    assert bundle.account is None


def test_postgres_fallback_without_pipeline_preserves_semantics(
    monkeypatch: pytest.MonkeyPatch,
):
    conn = _FakeConnection(
        {
            "progress": [],
            "split": [],
            "settings": [],
        }
    )
    pool = _FakePool(conn)
    monkeypatch.setattr(
        "constitution_memorizer.progress.postgres_repository._pipeline_supported",
        lambda: False,
    )
    repo = PostgresProgressRepository(pool)
    bundle = repo.load_request_bootstrap(USER, include_news=True)
    assert pool.borrows == 1
    assert conn.pipeline_entries == 0
    assert bundle.progress == []
    assert bundle.split_preferences == {}
    assert bundle.theme == DEFAULT_THEME
    assert bundle.news_articles_raw == DEFAULT_NEWS_ARTICLES
    assert bundle.profile is None
    assert bundle.settings == {}
    assert all(cur.closed for cur in conn.cursors)


def test_sqlite_bootstrap_settings_modes_and_account(tmp_path: Path):
    repo, engine = _seeded_engine(tmp_path)
    engine.set_setting("user_timezone", "Asia/Kolkata")
    engine.set_notification_frequency("twice")
    engine.mark_mode_seen("clause-1", "read")
    engine.claim_article("20")
    engine._invalidate_settings_cache()
    engine._invalidate_modes_cache()
    engine._invalidate_account_cache()
    repo.reset_counts()

    bundle = engine.bootstrap_request(include_modes=True, include_account=True)
    assert bundle.settings is not None
    assert bundle.settings.get("theme") == "dark"
    assert bundle.settings.get("user_timezone") == "Asia/Kolkata"
    assert bundle.settings.get("notification_frequency") == "twice"
    assert bundle.modes_seen_by_unit is not None
    assert "read" in bundle.modes_seen_by_unit.get("clause-1", frozenset())
    assert bundle.account is not None
    assert "20" in bundle.account.claimed_articles
    assert bundle.account.latest_paid_billing_order is None


def test_sqlite_include_flags_skip_optional_packs(tmp_path: Path):
    repo, engine = _seeded_engine(tmp_path)
    bundle = engine.bootstrap_request()
    assert bundle.modes_seen_by_unit is None
    assert bundle.account is None
    assert bundle.settings is not None


def test_postgres_optional_packs_share_pipeline(monkeypatch: pytest.MonkeyPatch):
    conn = _FakeConnection(
        {
            "progress": [],
            "split": [],
            "settings": [],
            "modes": [{"learning_unit_id": "clause-1", "mode": "read"}],
            "claims": [{"article_number": "20"}],
            "billing": [],
        }
    )
    pool = _FakePool(conn)
    monkeypatch.setattr(
        "constitution_memorizer.progress.postgres_repository._pipeline_supported",
        lambda: True,
    )
    repo = PostgresProgressRepository(pool)
    bundle = repo.load_request_bootstrap(
        USER, include_modes=True, include_account=True
    )
    assert pool.borrows == 1
    assert conn.pipeline_entries == 1
    kinds = [event[0] for event in conn.events]
    first_fetch = next(
        i for i, kind in enumerate(kinds) if kind in {"fetchall", "fetchone"}
    )
    assert kinds[:first_fetch].count("execute") == 6
    sql = " ".join(event[1] for event in conn.events if event[0] == "execute")
    assert "unit_modes_seen" in sql
    assert "user_free_articles" in sql
    assert "billing_orders" in sql
    assert bundle.modes_seen_by_unit == {"clause-1": frozenset({"read"})}
    assert bundle.account is not None
    assert bundle.account.claimed_articles == frozenset({"20"})
    assert bundle.account.latest_paid_billing_order is None


def test_postgres_skips_modes_and_account_sql_when_not_requested(
    monkeypatch: pytest.MonkeyPatch,
):
    conn = _FakeConnection({"progress": [], "split": [], "settings": []})
    pool = _FakePool(conn)
    monkeypatch.setattr(
        "constitution_memorizer.progress.postgres_repository._pipeline_supported",
        lambda: True,
    )
    repo = PostgresProgressRepository(pool)
    bundle = repo.load_request_bootstrap(USER)
    sql = " ".join(event[1] for event in conn.events if event[0] == "execute")
    assert "unit_modes_seen" not in sql
    assert "user_free_articles" not in sql
    assert "billing_orders" not in sql
    assert bundle.modes_seen_by_unit is None
    assert bundle.account is None


def test_engine_settings_and_account_caches_skip_repo(tmp_path: Path):
    repo, engine = _seeded_engine(tmp_path)
    engine.set_setting("user_timezone", "Asia/Kolkata")
    engine.set_setting("gcal_revision_time", "21:00")
    engine.set_setting("free_articles_backfilled", "1")
    engine.set_notification_frequency("hourly")
    engine.mark_mode_seen("clause-1", "cloze")
    engine._invalidate_settings_cache()
    engine._invalidate_modes_cache()
    engine._invalidate_account_cache()
    engine.bootstrap_request(include_news=True, include_modes=True, include_account=True)
    repo.reset_counts()

    assert engine.get_theme() == "dark"
    assert engine.get_news_articles_raw() == "14,21"
    assert engine.get_notification_frequency() == "hourly"
    assert engine.get_setting("user_timezone") == "Asia/Kolkata"
    assert engine.get_setting("gcal_revision_time") == "21:00"
    assert "cloze" in engine.modes_seen("clause-1")
    assert engine.latest_paid_billing_order() is None
    engine.claimed_articles()
    assert engine._backfill_checked is True
    assert repo.get_theme_calls == 0
    assert repo.get_news_articles_raw_calls == 0
    assert repo.get_notification_frequency_calls == 0
    assert repo.get_setting_calls == 0
    assert repo.modes_seen_calls == 0
    assert repo.claimed_articles_calls == 0
    assert repo.latest_paid_billing_order_calls == 0


def test_mark_done_clears_bootstrapped_modes_cache(tmp_path: Path):
    repo, engine = _seeded_engine(tmp_path)
    for mode in LEARN_MODES:
        engine.mark_mode_seen("clause-1", mode)
    engine.bootstrap_request(include_modes=True)
    assert engine.modes_seen("clause-1")
    engine.mark_done("clause-1", as_of=date(2026, 8, 15), require_all_modes=False)
    repo.reset_counts()
    assert engine.modes_seen("clause-1") == set()
    assert repo.modes_seen_calls == 0


def test_seeded_claimed_cache_still_runs_grandfather(tmp_path: Path):
    conn = open_progress_db(tmp_path / "progress.db")
    repo = CountingProgressRepo(ProgressRepository(conn))
    engine = ReminderEngine.from_repository(repo, _catalog(), user_id=USER)
    for mode in LEARN_MODES:
        engine.mark_mode_seen("clause-1", mode)
    engine.mark_done("clause-1", as_of=date(2026, 8, 15), require_all_modes=False)
    # No backfill flag yet. Account bootstrap seeds current (empty) claims.
    engine = engine.for_user(USER)
    bundle = engine.bootstrap_request(include_account=True)
    assert bundle.account is not None
    repo.reset_counts()
    claimed = engine.claimed_articles()
    assert "20" in claimed
    assert engine.get_setting("free_articles_backfilled") == "1"
    assert repo.claimed_articles_calls == 0
    assert repo.get_setting_calls == 0
    assert repo.inner.get_setting(USER, "free_articles_backfilled") == "1"


def test_grandfather_backfill_uses_bootstrap_caches_without_reread(tmp_path: Path):
    conn = open_progress_db(tmp_path / "progress.db")
    repo = CountingProgressRepo(ProgressRepository(conn))
    engine = ReminderEngine.from_repository(repo, _catalog(), user_id=USER)
    for mode in LEARN_MODES:
        engine.mark_mode_seen("clause-1", mode)
    engine.mark_done("clause-1", as_of=date(2026, 8, 15), require_all_modes=False)
    engine.set_setting("free_articles_backfilled", "0")
    engine = engine.for_user(USER)
    bundle = engine.bootstrap_request(include_account=True)
    assert bundle.account is not None
    assert engine._settings_cache.get("free_articles_backfilled") != "1"
    assert engine._progress_cache is not None
    assert engine._claimed_cache is not None
    assert engine._backfill_checked is False
    repo.reset_counts()

    claimed = engine.claimed_articles()

    assert "20" in claimed
    assert "20" in engine._claimed_cache
    assert engine.get_setting("free_articles_backfilled") == "1"
    assert engine._settings_cache.get("free_articles_backfilled") == "1"
    assert engine._backfill_checked is True
    assert repo.list_all_progress_calls == 0
    assert repo.claimed_articles_calls == 0
    assert repo.get_setting_calls == 0
    assert repo.claim_article_calls >= 1
    assert repo.set_setting_calls >= 1
    assert repo.inner.get_setting(USER, "free_articles_backfilled") == "1"

    repo.reset_counts()
    claimed_again = engine.claimed_articles()
    assert claimed_again == claimed
    assert repo.list_all_progress_calls == 0
    assert repo.claimed_articles_calls == 0
    assert repo.get_setting_calls == 0
    assert repo.claim_article_calls == 0
    assert repo.set_setting_calls == 0


def test_authenticated_dashboard_entitlements_use_account_pack(tmp_path: Path):
    conn = open_progress_db(tmp_path / "progress.db")
    repo = CountingProgressRepo(ProgressRepository(conn))
    provider = FakeAuthProvider()
    provider.seed_google_user(
        user_id=USER, email=USER_EMAIL, display_name="Test User"
    )
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "unused.db",
        multiuser=True,
        multiuser_settings=_settings(ARTICLE_ENTITLEMENTS_ENABLED="true"),
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
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert repo.load_request_bootstrap_calls == 1
    assert repo.last_bootstrap_kwargs is not None
    assert repo.last_bootstrap_kwargs.get("include_profile") is True
    assert repo.last_bootstrap_kwargs.get("include_modes") is True
    assert repo.last_bootstrap_kwargs.get("include_account") is True
    assert repo.modes_seen_calls == 0
    assert repo.claimed_articles_calls == 0
    assert repo.latest_paid_billing_order_calls == 0
    assert repo.get_setting_calls == 0


def test_browse_and_calendar_include_account_when_entitlements_on(tmp_path: Path):
    conn = open_progress_db(tmp_path / "progress.db")
    repo = CountingProgressRepo(ProgressRepository(conn))
    provider = FakeAuthProvider()
    provider.seed_google_user(
        user_id=USER, email=USER_EMAIL, display_name="Test User"
    )
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "unused.db",
        multiuser=True,
        multiuser_settings=_settings(ARTICLE_ENTITLEMENTS_ENABLED="true"),
        auth_provider=provider,
        session_store=InMemorySessionStore(),
        progress_repo=repo,
    )
    client = TestClient(app)
    start = client.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state")
    client.get(
        f"/auth/callback?code=fake-google-code&state={state}",
        follow_redirects=False,
    )
    repo.reset_counts()
    assert client.get("/browse").status_code == 200
    assert repo.load_request_bootstrap_calls == 1
    assert repo.last_bootstrap_kwargs is not None
    assert repo.last_bootstrap_kwargs.get("include_news") is True
    assert repo.last_bootstrap_kwargs.get("include_account") is True
    assert repo.claimed_articles_calls == 0
    repo.reset_counts()
    assert client.get("/browse/article/20").status_code == 200
    assert repo.load_request_bootstrap_calls == 1
    assert repo.last_bootstrap_kwargs is not None
    assert repo.last_bootstrap_kwargs.get("include_news") is True
    assert repo.last_bootstrap_kwargs.get("include_account") is True
    assert repo.claimed_articles_calls == 0
    assert repo.get_gloss_calls == 1
    repo.reset_counts()
    assert client.get("/calendar").status_code == 200
    assert repo.load_request_bootstrap_calls == 1
    assert repo.last_bootstrap_kwargs is not None
    assert repo.last_bootstrap_kwargs.get("include_account") is True
    assert repo.claimed_articles_calls == 0


def test_preload_account_claims_skips_followup_selects(tmp_path: Path):
    repo, engine = _seeded_engine(tmp_path)
    engine.set_setting("free_articles_backfilled", "1")
    engine._invalidate_settings_cache()
    engine._invalidate_account_cache()
    repo.reset_counts()
    engine.preload_account_claims()
    assert repo.get_setting_calls == 1
    assert repo.claimed_articles_calls == 1
    assert repo.load_request_bootstrap_calls == 0
    repo.reset_counts()
    assert engine.claimed_articles() == set()
    assert repo.get_setting_calls == 0
    assert repo.claimed_articles_calls == 0
