"""Shared Postgres ConnectionPool: lifecycle, cursor row factories, timing logs."""

from __future__ import annotations

import inspect
import logging
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import UUID

from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import InMemorySessionStore, PostgresSessionStore
from constitution_memorizer.multiuser.settings import MultiUserSettings, clear_settings_cache
from constitution_memorizer.progress.pg_pool import (
    POOL_MAX_SIZE,
    POOL_MIN_SIZE,
    POOL_OPEN_TIMEOUT_SECONDS,
    make_connection_pool,
)
from constitution_memorizer.progress.postgres_repository import PostgresProgressRepository
from constitution_memorizer.reports.contact_repository import PostgresContactMessageRepository
from constitution_memorizer.reports.repository import PostgresIssueReportRepository
from constitution_memorizer.web.app import create_app

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
USER_ID = UUID("11111111-1111-4111-8111-111111111111")
ROOT = Path(__file__).resolve().parents[1]


def _settings(**overrides) -> MultiUserSettings:
    base = {
        "APP_ENV": "test",
        "MULTIUSER_ENABLED": "true",
        "AUTH_GOOGLE_ENABLED": "true",
        "AUTH_PHONE_ENABLED": "true",
        "SESSION_SECRET": "test-secret",
        "SUPABASE_URL": "http://example.invalid",
        "SUPABASE_ANON_KEY": "anon",
        "DATABASE_URL": "postgresql://user:pass@127.0.0.1:5432/db",
        "COOKIE_SECURE": "false",
        "MEMORY_LOG_ENABLED": "false",
    }
    base.update({k: str(v) for k, v in overrides.items()})
    return MultiUserSettings(_env_file=None, **base)


class SharedFakeConnection:
    """One pooled connection reused by Progress then SessionStore."""

    def __init__(self, *, dict_row: dict, tuple_row: tuple) -> None:
        self.row_factory = None
        self.dict_row = dict_row
        self.tuple_row = tuple_row
        self.execute_rows: list[object] = []

    def cursor(self, row_factory=None):
        conn = self

        class _Cursor:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def execute(self, sql, params=None):
                return self

            def fetchone(self):
                if row_factory is None:
                    return conn.tuple_row
                return conn.dict_row

            def fetchall(self):
                row = self.fetchone()
                return [] if row is None else [row]

        return _Cursor()

    def execute(self, sql, params=None):
        if self.row_factory is not None:
            raise AssertionError(
                "pooled connection row_factory was mutated; "
                "SessionStore expected default tuple rows"
            )
        self.execute_rows.append(self.tuple_row)
        return _FakeResult(self.tuple_row)

    def commit(self) -> None:
        return None


class _FakeResult:
    def __init__(self, row: object) -> None:
        self._row = row

    def fetchone(self):
        return self._row

    def fetchall(self):
        return [] if self._row is None else [self._row]


class SharedFakePool:
    def __init__(self, conn: SharedFakeConnection) -> None:
        self._conn = conn
        self.checkouts = 0
        self.checkins = 0

    @contextmanager
    def connection(self):
        self.checkouts += 1
        try:
            yield self._conn
        finally:
            self.checkins += 1


def test_make_connection_pool_starts_closed_with_tuple_defaults():
    pool = make_connection_pool("postgresql://user:pass@127.0.0.1:1/db")
    assert pool.closed is True
    assert pool.min_size == POOL_MIN_SIZE == 1
    assert pool.max_size == POOL_MAX_SIZE == 5
    assert inspect.signature(pool.open).parameters["wait"]
    source = inspect.getsource(make_connection_pool)
    assert "open=False" in source
    assert "row_factory" not in source.split("return", 1)[-1]


def test_progress_dict_cursor_does_not_leak_into_session_store():
    """Progress uses dict_row on the cursor only; SessionStore still gets tuples."""
    now = datetime.now(timezone.utc)
    dict_row = {
        "learning_unit_id": "unit-1",
        "status": "new",
        "times_completed": 0,
        "last_completed": None,
        "next_revision": None,
        "interval_days": 1,
        "ease_factor": 2.5,
        "created_at": now,
        "updated_at": now,
    }
    tuple_row = (
        "session-abc",
        str(USER_ID),
        "access-token",
        "refresh-token",
        "csrf-token",
        "Ada",
        "ada@example.com",
        None,
        None,
        "google",
        now + timedelta(days=1),
        now,
    )
    conn = SharedFakeConnection(dict_row=dict_row, tuple_row=tuple_row)
    pool = SharedFakePool(conn)

    with patch("psycopg.connect", side_effect=AssertionError("use the pool")):
        progress = PostgresProgressRepository(pool)
        record = progress.get_progress(USER_ID, "unit-1")
        assert record is not None
        assert record.learning_unit_id == "unit-1"
        assert conn.row_factory is None
        assert pool.checkouts == 1
        assert pool.checkins == 1

        store = PostgresSessionStore(pool)
        session = store.get("session-abc")
        assert session is not None
        assert session.session_id == "session-abc"
        assert session.user.email == "ada@example.com"
        assert conn.execute_rows == [tuple_row]
        assert isinstance(conn.execute_rows[0], tuple)
        assert conn.row_factory is None
        assert pool.checkouts == 2
        assert pool.checkins == 2


def test_repos_do_not_assign_connection_row_factory():
    paths = [
        ROOT / "src/constitution_memorizer/progress/postgres_repository.py",
        ROOT / "src/constitution_memorizer/auth/sessions.py",
        ROOT / "src/constitution_memorizer/reports/repository.py",
        ROOT / "src/constitution_memorizer/reports/contact_repository.py",
        ROOT / "src/constitution_memorizer/progress/pg_pool.py",
        ROOT / "src/constitution_memorizer/web/app.py",
    ]
    for path in paths:
        source = path.read_text(encoding="utf-8")
        assert "conn.row_factory" not in source, path.name
        assert "connection.row_factory" not in source, path.name


def test_progress_and_reports_use_cursor_row_factory():
    progress_src = inspect.getsource(PostgresProgressRepository._cursor)
    assert "cursor(row_factory=" in progress_src
    assert "conn.row_factory" not in progress_src
    issue_src = inspect.getsource(PostgresIssueReportRepository.create_report)
    assert "cursor(row_factory=dict_row)" in issue_src
    contact_src = inspect.getsource(PostgresContactMessageRepository.create_message)
    assert "cursor(row_factory=dict_row)" in contact_src
    session_src = inspect.getsource(PostgresSessionStore.get)
    assert "conn.execute" in session_src
    assert "row_factory" not in session_src


def test_sqlite_app_pool_is_none(tmp_path: Path):
    clear_settings_cache()
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "progress.db",
        multiuser=False,
        multiuser_settings=_settings(DATABASE_URL="", MULTIUSER_ENABLED="false"),
    )
    assert app.state.db_pool is None
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
    clear_settings_cache()


def test_create_app_shares_one_closed_pool_across_postgres_repos(tmp_path: Path):
    clear_settings_cache()
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "progress.db",
        multiuser=True,
        multiuser_settings=_settings(),
        auth_provider=FakeAuthProvider(),
    )
    pool = app.state.db_pool
    assert pool is not None
    assert pool.closed is True
    assert pool.min_size == 1
    assert pool.max_size == 5
    assert app.state.engine.repo._pool is pool
    assert app.state.session_store._pool is pool
    assert app.state.issue_report_repo._pool is pool
    assert app.state.contact_message_repo._pool is pool
    clear_settings_cache()


def test_lifespan_opens_pool_before_traffic_and_closes_on_shutdown(tmp_path: Path):
    clear_settings_cache()
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "progress.db",
        multiuser=False,
        multiuser_settings=_settings(DATABASE_URL="", MULTIUSER_ENABLED="false"),
    )
    fake_pool = MagicMock()
    app.state.db_pool = fake_pool
    with TestClient(app) as client:
        fake_pool.open.assert_called_once_with(
            wait=True, timeout=POOL_OPEN_TIMEOUT_SECONDS
        )
        assert client.get("/health").status_code == 200
    fake_pool.close.assert_called_once()
    clear_settings_cache()


def test_injected_postgres_repos_do_not_open_a_pool(tmp_path: Path):
    clear_settings_cache()
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "progress.db",
        multiuser=True,
        multiuser_settings=_settings(),
        auth_provider=FakeAuthProvider(),
        session_store=InMemorySessionStore(),
        progress_repo=MagicMock(),
        issue_report_repo=MagicMock(),
        contact_message_repo=MagicMock(),
        access_store=MagicMock(),
        admin_repo=MagicMock(),
        calendar_store=MagicMock(),
    )
    assert app.state.db_pool is None
    clear_settings_cache()


def _timing_messages(caplog: logging.LogCaptureFixture) -> list[str]:
    return [
        record.getMessage()
        for record in caplog.records
        if "duration_ms" in record.getMessage()
    ]


def test_request_timing_logs_skip_health_and_static(
    tmp_path: Path, caplog: logging.LogCaptureFixture
):
    clear_settings_cache()
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "progress.db",
        multiuser=False,
        multiuser_settings=_settings(DATABASE_URL="", MULTIUSER_ENABLED="false"),
    )
    with TestClient(app) as client:
        with caplog.at_level(logging.INFO, logger="uvicorn.error"):
            caplog.clear()
            assert client.get("/health").status_code == 200
            assert _timing_messages(caplog) == []

            caplog.clear()
            assert client.get("/healthz").status_code == 200
            assert _timing_messages(caplog) == []

            caplog.clear()
            static = client.get("/static/styles.css")
            assert static.status_code == 200
            assert _timing_messages(caplog) == []

            caplog.clear()
            login = client.get("/login?error=session")
            assert login.status_code == 200
            messages = _timing_messages(caplog)
            assert len(messages) == 1
            message = messages[0]
            assert "method=GET" in message
            assert "path=/login" in message
            assert "status=200" in message
            assert "duration_ms=" in message
            assert "error=session" not in message
            assert "ada@" not in message
            assert "token" not in message.lower()
            assert all(
                record.name == "uvicorn.error"
                for record in caplog.records
                if "duration_ms" in record.getMessage()
            )
    clear_settings_cache()


def test_request_timing_uses_uvicorn_error_logger():
    """Railway shows Uvicorn's logger; app-module INFO is not in access logs."""
    from constitution_memorizer.web import app as web_app

    assert web_app.timing_logger.name == "uvicorn.error"
    source = inspect.getsource(web_app.create_app)
    assert "timing_logger.info(" in source
    assert 'logging.getLogger("uvicorn.error")' in Path(
        web_app.__file__
    ).read_text(encoding="utf-8")


def test_pool_open_timeout_is_fifteen_seconds():
    assert POOL_OPEN_TIMEOUT_SECONDS == 15.0
