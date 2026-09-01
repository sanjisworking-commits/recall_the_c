"""Request-scoped ReminderEngine caches avoid per-unit get_progress N+1."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import InMemorySessionStore
from constitution_memorizer.learning.schemas import LearningUnitsDocument
from constitution_memorizer.multiuser.settings import MultiUserSettings, clear_settings_cache
from constitution_memorizer.progress.repository import ProgressRepository
from constitution_memorizer.progress.scheduler import ReminderEngine
from constitution_memorizer.progress.db import open_progress_db
from constitution_memorizer.utils.json_io import read_json
from constitution_memorizer.web.app import create_app

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
USER = UUID("11111111-1111-4111-8111-111111111111")


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


def _catalog() -> dict:
    doc = LearningUnitsDocument.model_validate(read_json(MINI_UNITS))
    return {u.id: u for u in doc.units}


def test_dashboard_style_iteration_uses_one_list_all_progress(tmp_path: Path):
    conn = open_progress_db(tmp_path / "progress.db")
    inner = ProgressRepository(conn)
    repo = CountingProgressRepo(inner)
    catalog = _catalog()
    unit_ids = list(catalog)[:8]
    assert len(unit_ids) >= 3

    seed = ReminderEngine.from_repository(repo, catalog, user_id=USER)
    for unit_id in unit_ids[:3]:
        seed.mark_all_modes_seen(unit_id)
        seed.mark_done(unit_id, as_of=date(2026, 8, 1))

    # Fresh request-bound engine (as auth middleware does via for_user).
    app_engine = ReminderEngine.from_repository(repo, catalog, user_id=uuid4())
    bound = app_engine.for_user(USER)
    repo.get_progress_calls = 0
    repo.list_all_progress_calls = 0

    # Simulate Dashboard/Browse/Progress iterating every unit.
    for unit_id in catalog:
        bound.get_progress(unit_id)

    assert repo.get_progress_calls == 0
    assert repo.list_all_progress_calls == 1
    # Second pass must not reload.
    for unit_id in catalog:
        bound.get_progress(unit_id)
    assert repo.list_all_progress_calls == 1


def test_for_user_starts_with_empty_cache(tmp_path: Path):
    conn = open_progress_db(tmp_path / "progress.db")
    repo = CountingProgressRepo(ProgressRepository(conn))
    catalog = _catalog()
    root = ReminderEngine.from_repository(repo, catalog, user_id=USER)
    # Warm root cache.
    root.get_progress(next(iter(catalog)))
    assert repo.list_all_progress_calls == 1

    bound = root.for_user(USER)
    assert bound._progress_cache is None
    assert bound._split_cache is None
    bound.get_progress(next(iter(catalog)))
    assert repo.list_all_progress_calls == 2


def test_write_updates_progress_cache_without_stale_reads(tmp_path: Path):
    conn = open_progress_db(tmp_path / "progress.db")
    repo = CountingProgressRepo(ProgressRepository(conn))
    catalog = _catalog()
    unit_id = next(iter(catalog))
    engine = ReminderEngine.from_repository(repo, catalog, user_id=USER)
    assert engine.get_progress(unit_id) is None
    engine.mark_all_modes_seen(unit_id)
    result = engine.mark_done(unit_id, as_of=date(2026, 8, 1))
    cached = engine.get_progress(unit_id)
    assert cached is not None
    assert cached.status == result.progress.status
    assert cached.times_completed == result.progress.times_completed
    # No per-get_progress repo hits after cache warm + write store.
    before = repo.get_progress_calls
    assert engine.get_progress(unit_id) is not None
    assert repo.get_progress_calls == before


def test_split_preference_cache_and_invalidation(tmp_path: Path):
    conn = open_progress_db(tmp_path / "progress.db")
    repo = CountingProgressRepo(ProgressRepository(conn))
    catalog = _catalog()
    parent = next(
        (u.id for u in catalog.values() if u.allows_letter_split),
        next(iter(catalog)),
    )
    engine = ReminderEngine.from_repository(repo, catalog, user_id=USER)
    assert engine.get_split_preference(parent) is None
    assert repo.list_split_preferences_calls == 1
    assert repo.get_split_preference_calls == 0

    engine.set_split_preference(parent, "letters")
    assert engine.get_split_preference(parent) == "letters"
    assert repo.list_split_preferences_calls == 1

    engine.delete_split_preference(parent)
    assert engine.get_split_preference(parent) is None

    engine.reset_all_personal_data()
    assert engine._progress_cache is None
    assert engine._split_cache is None


def _seed_due_engine(tmp_path: Path) -> tuple[CountingProgressRepo, ReminderEngine]:
    conn = open_progress_db(tmp_path / "progress.db")
    repo = CountingProgressRepo(ProgressRepository(conn))
    catalog = _catalog()
    engine = ReminderEngine.from_repository(repo, catalog, user_id=USER)
    engine.mark_all_modes_seen("clause-1")
    engine.mark_done("clause-1", as_of=date(2026, 7, 20))
    engine._invalidate_progress_cache()
    repo.list_all_progress_calls = 0
    repo.list_due_calls = 0
    repo.count_by_status_calls = 0
    return repo, engine


def test_uncached_due_today_uses_list_due_and_matches_cache(tmp_path: Path):
    repo, engine = _seed_due_engine(tmp_path)
    as_of = date(2026, 7, 21)
    assert engine._progress_cache is None
    uncached = engine.due_today(as_of=as_of)
    assert repo.list_due_calls == 1
    assert [row.learning_unit_id for row in uncached] == ["clause-1"]

    engine.preload_progress()
    assert repo.list_all_progress_calls == 1
    cached = engine.due_today(as_of=as_of)
    cached_new = engine.due_today(as_of=as_of, include_new=True)
    uncached_new = ReminderEngine.from_repository(
        repo.inner, engine.units, user_id=USER
    ).due_today(as_of=as_of, include_new=True)
    assert repo.list_due_calls == 1
    assert [row.learning_unit_id for row in cached] == [
        row.learning_unit_id for row in uncached
    ]
    assert [row.learning_unit_id for row in cached_new] == [
        row.learning_unit_id for row in uncached_new
    ]


def test_cached_due_today_and_stats_skip_targeted_queries(tmp_path: Path):
    repo, engine = _seed_due_engine(tmp_path)
    engine.preload_progress()
    repo.list_due_calls = 0
    repo.count_by_status_calls = 0
    first = engine.due_today(as_of=date(2026, 7, 21))
    second = engine.due_today(as_of=date(2026, 7, 21))
    stats = engine.stats()
    assert first == second
    assert first[0].learning_unit_id == "clause-1"
    assert repo.list_due_calls == 0
    assert repo.count_by_status_calls == 0
    assert stats["review"] == 1
    assert stats["tracked"] == 1


def test_empty_loaded_cache_does_not_query_due_or_stats(tmp_path: Path):
    conn = open_progress_db(tmp_path / "empty.db")
    repo = CountingProgressRepo(ProgressRepository(conn))
    engine = ReminderEngine.from_repository(repo, _catalog(), user_id=USER)
    engine._progress_cache = {}
    assert engine.due_today(as_of=date(2026, 7, 21)) == []
    stats = engine.stats()
    assert repo.list_due_calls == 0
    assert repo.count_by_status_calls == 0
    assert stats["new"] == 0
    assert stats["review"] == 0
    assert stats["mastered"] == 0
    assert stats["tracked"] == 0


def test_uncached_stats_uses_count_by_status(tmp_path: Path):
    repo, engine = _seed_due_engine(tmp_path)
    assert engine._progress_cache is None
    stats = engine.stats()
    assert repo.count_by_status_calls == 1
    engine.preload_progress()
    cached = engine.stats()
    assert repo.count_by_status_calls == 1
    assert cached["review"] == stats["review"]
    assert cached["tracked"] == stats["tracked"]


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


def _counting_client(tmp_path: Path) -> tuple[TestClient, CountingProgressRepo]:
    conn = open_progress_db(tmp_path / "progress.db")
    repo = CountingProgressRepo(ProgressRepository(conn))
    provider = FakeAuthProvider()
    provider.seed_google_user(
        user_id=USER,
        email="a@example.com",
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
    # Login's _establish_session also reads the profile; measure the page only.
    repo.reset_counts()
    return client, repo


def test_authenticated_dashboard_one_profile_and_one_progress_list(tmp_path: Path):
    client, repo = _counting_client(tmp_path)
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert repo.load_request_bootstrap_calls == 1
    assert repo.get_profile_calls == 0
    assert repo.list_all_progress_calls == 0
    assert repo.list_due_calls == 0
    assert repo.count_by_status_calls == 0


def test_authenticated_browse_index_one_progress_list_no_list_due(tmp_path: Path):
    client, repo = _counting_client(tmp_path)
    resp = client.get("/browse")
    assert resp.status_code == 200
    assert repo.load_request_bootstrap_calls == 1
    assert repo.list_all_progress_calls == 0
    assert repo.list_due_calls == 0


def test_authenticated_browse_article_does_not_require_bulk_progress(tmp_path: Path):
    client, repo = _counting_client(tmp_path)
    resp = client.get("/browse/article/20")
    assert resp.status_code == 200
    assert repo.load_request_bootstrap_calls == 1
    assert repo.list_all_progress_calls == 0
