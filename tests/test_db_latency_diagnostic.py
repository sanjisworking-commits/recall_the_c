"""Phase 1 (request latency): DB round-trip diagnostic + region reporting.

measure_db_rtt uses the existing pool to time connection acquisition and a run
of sequential SELECT 1 calls, and reports Railway/database regions from the
environment without ever exposing credentials.
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest

from constitution_memorizer.admin.db_diagnostics import (
    _percentile,
    measure_db_rtt,
    region_info,
)


class _FakeCursor:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None

    def execute(self, sql, params=None):
        assert sql == "SELECT 1"

    def fetchone(self):
        return (1,)


class _FakeConn:
    def __init__(self) -> None:
        self.cursor_calls = 0

    def cursor(self, row_factory=None):
        self.cursor_calls += 1
        return _FakeCursor()


class _FakePool:
    def __init__(self) -> None:
        self.conn = _FakeConn()
        self.borrows = 0

    @contextmanager
    def connection(self):
        self.borrows += 1
        yield self.conn


def test_percentile_interpolates():
    vals = [1.0, 2.0, 3.0, 4.0]
    assert _percentile(vals, 0.5) == 2.5
    assert _percentile([], 0.5) is None
    assert _percentile([7.0], 0.95) == 7.0


def test_measure_db_rtt_runs_samples_on_one_connection():
    pool = _FakePool()
    report = measure_db_rtt(pool, samples=20)

    assert report.available is True
    assert report.reason is None
    assert report.samples == 20
    # One borrowed connection; 1 first-query + 20 sampled = 21 cursor uses.
    assert pool.borrows == 1
    assert pool.conn.cursor_calls == 21
    for field in (report.acquire_ms, report.first_query_ms, report.p50_ms, report.p95_ms):
        assert field is not None and field >= 0.0
    assert report.min_ms <= report.p50_ms <= report.p95_ms <= report.max_ms


def test_measure_db_rtt_without_pool_is_unavailable():
    report = measure_db_rtt(None)
    assert report.available is False
    assert "no_pool" in report.reason
    assert report.samples == 0
    assert report.p95_ms is None


def test_region_info_reads_env_without_credentials(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RAILWAY_REGION", "us-west1")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://secretuser:secretpass@aws-0-ap-south-1.pooler.supabase.com:5432/db",
    )
    monkeypatch.delenv("DATABASE_REGION", raising=False)
    monkeypatch.delenv("SUPABASE_REGION", raising=False)

    railway, database, host = region_info()
    assert railway == "us-west1"
    # Host is a region hint; credentials must never appear.
    assert host == "aws-0-ap-south-1.pooler.supabase.com"
    assert "secretuser" not in (host or "")
    assert "secretpass" not in (host or "")


def test_db_latency_report_serializes_to_json_dict():
    report = measure_db_rtt(_FakePool(), samples=3)
    payload = report.as_dict()
    assert payload["available"] is True
    assert payload["samples"] == 3
    assert set(payload).issuperset(
        {"acquire_ms", "first_query_ms", "p50_ms", "p95_ms", "railway_region"}
    )


# ── Admin endpoint wiring ─────────────────────────────────────────────────────

from datetime import datetime, timezone  # noqa: E402
from pathlib import Path  # noqa: E402
from uuid import UUID  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from constitution_memorizer.auth.fake_provider import FakeAuthProvider  # noqa: E402
from constitution_memorizer.auth.sessions import InMemorySessionStore  # noqa: E402
from constitution_memorizer.multiuser.settings import (  # noqa: E402
    MultiUserSettings,
    clear_settings_cache,
)
from constitution_memorizer.progress.db import open_progress_db  # noqa: E402
from constitution_memorizer.progress.repository import ProgressRepository  # noqa: E402
from constitution_memorizer.web.app import create_app  # noqa: E402

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
_ADMIN = UUID("44444444-4444-4444-8444-444444444444")


def _admin_client(tmp_path: Path):
    clear_settings_cache()
    conn = open_progress_db(tmp_path / "progress.db")
    repo = ProgressRepository(conn)
    provider = FakeAuthProvider()
    provider.seed_google_user(
        user_id=_ADMIN, email="admin@example.com", display_name="Admin"
    )
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "unused.db",
        multiuser=True,
        multiuser_settings=MultiUserSettings(
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
            ADMIN_ENABLED="true",
        ),
        auth_provider=provider,
        session_store=InMemorySessionStore(),
        progress_repo=repo,
    )
    client = TestClient(app)
    start = client.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state")
    client.get(
        f"/auth/callback?code=fake-google-code&state={state}", follow_redirects=False
    )
    return client, repo


def test_admin_db_latency_endpoint_reports_no_pool_on_sqlite(tmp_path: Path):
    client, repo = _admin_client(tmp_path)
    repo.conn.execute(
        "INSERT INTO user_roles (user_id, role, created_at) VALUES (?, 'admin', ?)",
        (str(_ADMIN), datetime.now(timezone.utc).isoformat()),
    )
    repo.conn.commit()

    resp = client.get("/admin/diagnostics/db-latency")
    assert resp.status_code == 200
    body = resp.json()
    # SQLite test app has no pool; the endpoint still answers cleanly.
    assert body["available"] is False
    assert "no_pool" in body["reason"]
    clear_settings_cache()


def test_admin_db_latency_endpoint_hidden_from_non_admin(tmp_path: Path):
    client, _repo = _admin_client(tmp_path)  # signed in, but no admin role
    resp = client.get("/admin/diagnostics/db-latency")
    assert resp.status_code == 404
    clear_settings_cache()
