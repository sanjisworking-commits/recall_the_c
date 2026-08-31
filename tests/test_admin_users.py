"""Admin users search, identity capture, grant/revoke, audit atomicity."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.admin.repository import SqliteAdminRepository
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
ADMIN = UUID("55555555-5555-4555-8555-555555555555")
MEMBER = UUID("66666666-6666-4666-8666-666666666666")


@pytest.fixture(autouse=True)
def _fresh_settings():
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
        ARTICLE_ENTITLEMENTS_ENABLED="true",
        ADMIN_ENABLED="true",
    )


def _admin_client(tmp_path: Path) -> tuple[TestClient, ProgressRepository]:
    conn = open_progress_db(tmp_path / "progress.db")
    repo = ProgressRepository(conn)
    provider = FakeAuthProvider()
    provider.seed_google_user(
        user_id=ADMIN, email="admin@recall.app", display_name="Sanjana"
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
    repo.conn.execute(
        "INSERT INTO user_roles (user_id, role, created_at) VALUES (?, 'admin', ?)",
        (str(ADMIN), datetime.now(timezone.utc).isoformat()),
    )
    repo.conn.commit()
    return client, repo


def _seed_member(
    repo: ProgressRepository,
    *,
    user_id: UUID = MEMBER,
    name: str | None = "Ananya Rao",
    email: str | None = "ananya.rao@gmail.com",
    phone: str | None = "+919820041772",
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    repo.conn.execute(
        """
        INSERT INTO user_profile (
            user_id, display_name, avatar_url, created_at, updated_at,
            email, phone, last_sign_in_at
        ) VALUES (?, ?, NULL, ?, ?, ?, ?, ?)
        """,
        (str(user_id), name, now, now, email, phone, now),
    )
    repo.conn.commit()


def _csrf(client: TestClient) -> str:
    return client.cookies.get("rtc_csrf")


# ----------------------------------------------------------------------- #
# Identity capture                                                        #
# ----------------------------------------------------------------------- #
def test_sign_in_records_identity(tmp_path: Path) -> None:
    _client, repo = _admin_client(tmp_path)
    row = repo.conn.execute(
        "SELECT email, phone, last_sign_in_at FROM user_profile WHERE user_id = ?",
        (str(ADMIN),),
    ).fetchone()
    assert row is not None
    assert row["email"] == "admin@recall.app"
    assert row["last_sign_in_at"] is not None


def test_record_identity_never_clobbers_display_name(tmp_path: Path) -> None:
    conn = open_progress_db(tmp_path / "p.db")
    repo = ProgressRepository(conn)
    repo.upsert_profile(MEMBER, display_name="Chosen Name", avatar_url=None)
    repo.record_identity(MEMBER, email="m@example.com", phone=None)
    profile = repo.get_profile(MEMBER)
    assert profile is not None and profile["display_name"] == "Chosen Name"
    row = conn.execute(
        "SELECT email FROM user_profile WHERE user_id = ?", (str(MEMBER),)
    ).fetchone()
    assert row["email"] == "m@example.com"
    # A provider that stops sending email keeps the last known value.
    repo.record_identity(MEMBER, email=None, phone="+91111")
    row = conn.execute(
        "SELECT email, phone FROM user_profile WHERE user_id = ?", (str(MEMBER),)
    ).fetchone()
    assert row["email"] == "m@example.com" and row["phone"] == "+91111"


# ----------------------------------------------------------------------- #
# Search                                                                  #
# ----------------------------------------------------------------------- #
def test_search_by_uuid_email_phone_name(tmp_path: Path) -> None:
    client, repo = _admin_client(tmp_path)
    _seed_member(repo)
    for q in (str(MEMBER), "ananya.rao@gmail", "+919820", "Ananya"):
        page = client.get("/admin/users", params={"q": q})
        assert page.status_code == 200, q
        assert "Ananya Rao" in page.text, q
    miss = client.get("/admin/users", params={"q": "zzz-no-such"})
    assert "No user matches that." in miss.text


def test_empty_query_lists_recent_sign_ins(tmp_path: Path) -> None:
    client, repo = _admin_client(tmp_path)
    _seed_member(repo)
    page = client.get("/admin/users")
    assert page.status_code == 200
    assert "most recent sign-ins" in page.text
    assert "Ananya Rao" in page.text and "Sanjana" in page.text


# ----------------------------------------------------------------------- #
# User detail fact string                                                 #
# ----------------------------------------------------------------------- #
def test_detail_fact_string_for_free_grant_admin(tmp_path: Path) -> None:
    client, repo = _admin_client(tmp_path)
    _seed_member(repo)

    free = client.get(f"/admin/users/{MEMBER}")
    assert "level=free · is_subscribed=false · access_source=free" in free.text

    csrf = _csrf(client)
    resp = client.post(
        f"/admin/users/{MEMBER}/grants",
        data={
            "csrf_token": csrf,
            "source": "admin_grant",
            "indefinite": "1",
            "reason": "beta tester",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    granted = client.get(f"/admin/users/{MEMBER}")
    assert (
        "level=subscribed · is_subscribed=false · access_source=admin_grant"
        in granted.text
    )

    own = client.get(f"/admin/users/{ADMIN}")
    assert "level=subscribed · is_subscribed=false · access_source=admin" in own.text
    assert "Administrator" in own.text


# ----------------------------------------------------------------------- #
# Grant + revoke                                                          #
# ----------------------------------------------------------------------- #
def test_grant_creates_row_and_audit_atomically(tmp_path: Path) -> None:
    client, repo = _admin_client(tmp_path)
    _seed_member(repo)
    csrf = _csrf(client)
    resp = client.post(
        f"/admin/users/{MEMBER}/grants",
        data={
            "csrf_token": csrf,
            "source": "promotion",
            "ends_on": "2027-03-01",
            "reason": "NLU pilot cohort",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    grant = repo.conn.execute(
        "SELECT * FROM access_grants WHERE user_id = ?", (str(MEMBER),)
    ).fetchone()
    assert grant["source"] == "promotion"
    # Day granularity stored end-of-day UTC.
    assert grant["ends_at"].startswith("2027-03-01T23:59:59")
    assert grant["granted_by"] == str(ADMIN)

    audit = repo.conn.execute(
        "SELECT * FROM admin_audit_log WHERE action = 'grant_access'"
    ).fetchone()
    assert audit is not None
    assert audit["target_user_id"] == str(MEMBER)
    assert audit["before_state"] is None
    assert '"source": "promotion"' in audit["after_state"]


def test_grant_validation_errors(tmp_path: Path) -> None:
    client, repo = _admin_client(tmp_path)
    _seed_member(repo)
    csrf = _csrf(client)

    no_reason = client.post(
        f"/admin/users/{MEMBER}/grants",
        data={"csrf_token": csrf, "source": "admin_grant", "indefinite": "1", "reason": "  "},
    )
    assert no_reason.status_code == 400

    bad_source = client.post(
        f"/admin/users/{MEMBER}/grants",
        data={"csrf_token": csrf, "source": "payment", "indefinite": "1", "reason": "x"},
    )
    assert bad_source.status_code == 400

    no_date = client.post(
        f"/admin/users/{MEMBER}/grants",
        data={"csrf_token": csrf, "source": "admin_grant", "reason": "x"},
    )
    assert no_date.status_code == 400

    past_date = client.post(
        f"/admin/users/{MEMBER}/grants",
        data={
            "csrf_token": csrf,
            "source": "admin_grant",
            "ends_on": "2020-01-01",
            "reason": "x",
        },
    )
    assert past_date.status_code == 400

    missing_csrf = client.post(
        f"/admin/users/{MEMBER}/grants",
        data={"source": "admin_grant", "indefinite": "1", "reason": "x"},
    )
    assert missing_csrf.status_code == 403
    assert (
        repo.conn.execute("SELECT COUNT(*) AS n FROM access_grants").fetchone()["n"]
        == 0
    )


def test_revoke_sets_revoked_at_and_audits(tmp_path: Path) -> None:
    client, repo = _admin_client(tmp_path)
    _seed_member(repo)
    csrf = _csrf(client)
    client.post(
        f"/admin/users/{MEMBER}/grants",
        data={
            "csrf_token": csrf,
            "source": "admin_grant",
            "indefinite": "1",
            "reason": "support",
        },
        follow_redirects=False,
    )
    grant_id = repo.conn.execute("SELECT id FROM access_grants").fetchone()["id"]
    resp = client.post(
        f"/admin/grants/{grant_id}/revoke",
        data={"csrf_token": csrf},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    row = repo.conn.execute(
        "SELECT revoked_at FROM access_grants WHERE id = ?", (grant_id,)
    ).fetchone()
    assert row["revoked_at"] is not None
    audit = repo.conn.execute(
        "SELECT before_state, after_state FROM admin_audit_log WHERE action = 'revoke_grant'"
    ).fetchone()
    assert '"revoked_at": null' in audit["before_state"]
    assert '"revoked_at": "' in audit["after_state"]
    # Second revoke of the same grant: nothing left to revoke.
    again = client.post(
        f"/admin/grants/{grant_id}/revoke",
        data={"csrf_token": csrf},
        follow_redirects=False,
    )
    assert again.status_code == 404


def test_audit_failure_rolls_back_grant(tmp_path: Path) -> None:
    # The invariant on both backends: if the audit insert fails, the
    # mutation must not exist either.
    conn = open_progress_db(tmp_path / "p.db")
    repo = SqliteAdminRepository(conn)
    conn.execute("DROP TABLE admin_audit_log")
    conn.commit()
    with pytest.raises(Exception):
        repo.create_grant(
            user_id=MEMBER,
            source="admin_grant",
            ends_at=None,
            reason="test",
            granted_by=ADMIN,
        )
    count = conn.execute("SELECT COUNT(*) AS n FROM access_grants").fetchone()["n"]
    assert count == 0


# ----------------------------------------------------------------------- #
# /admin/access filters                                                   #
# ----------------------------------------------------------------------- #
def test_access_page_scheduled_filter(tmp_path: Path) -> None:
    client, repo = _admin_client(tmp_path)
    _seed_member(repo)
    now = datetime.now(timezone.utc).replace(microsecond=0)

    def _grant(starts: datetime, ends: datetime | None, revoked: datetime | None = None):
        repo.conn.execute(
            """
            INSERT INTO access_grants (
                id, user_id, source, starts_at, ends_at, reason,
                granted_by, created_at, revoked_at
            ) VALUES (?, ?, 'admin_grant', ?, ?, 'seeded', ?, ?, ?)
            """,
            (
                str(uuid4()),
                str(MEMBER),
                starts.isoformat(),
                ends.isoformat() if ends else None,
                str(ADMIN),
                now.isoformat(),
                revoked.isoformat() if revoked else None,
            ),
        )
        repo.conn.commit()

    _grant(now - timedelta(days=1), None)                     # active
    _grant(now + timedelta(days=3), now + timedelta(days=30)) # scheduled
    _grant(now - timedelta(days=60), now - timedelta(days=30))# ended
    _grant(now - timedelta(days=1), None, revoked=now)        # revoked → ended bucket

    scheduled = client.get("/admin/access", params={"state": "scheduled"})
    assert scheduled.text.count("SCHEDULED") >= 1
    assert "ACTIVE" not in scheduled.text

    ended = client.get("/admin/access", params={"state": "ended"})
    assert "ENDED" in ended.text and "REVOKED" in ended.text

    active = client.get("/admin/access", params={"state": "active"})
    assert "ACTIVE" in active.text and "SCHEDULED" not in active.text


def test_sign_in_survives_identity_capture_failure(tmp_path: Path) -> None:
    # Deploy-ordering hazard: new code against a database that has not run
    # migration 0006 yet. Identity capture must degrade, never break auth.
    conn = open_progress_db(tmp_path / "progress.db")

    class _Missing0006Repo(ProgressRepository):
        def record_identity(self, user_id, *, email, phone):
            raise RuntimeError(
                'column "email" of relation "user_profile" does not exist'
            )

    repo = _Missing0006Repo(conn)
    provider = FakeAuthProvider()
    provider.seed_google_user(
        user_id=ADMIN, email="admin@recall.app", display_name="Admin"
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
    assert cb.status_code == 303  # sign-in completed despite the failure
    assert client.get("/dashboard").status_code == 200
