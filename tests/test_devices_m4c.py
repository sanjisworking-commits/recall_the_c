"""Milestone 4C: replacement-churn policy (3 replacements / rolling 30 days)."""

from __future__ import annotations

import inspect
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import InMemorySessionStore
from constitution_memorizer.devices.db import ensure_sqlite_schema
from constitution_memorizer.devices.models import (
    ACTION_CLEAR_DEVICE_REPLACEMENT_LIMIT,
    BLOCK_DEVICE_REPLACEMENT_LIMIT,
    DEVICE_REPLACEMENT_LIMIT,
    DEVICE_REPLACEMENT_WINDOW_DAYS,
    REGISTER_REPLACEMENT_LIMIT,
)
from constitution_memorizer.devices.repository import SqliteDeviceRepository
from constitution_memorizer.devices.service import DeviceService
from constitution_memorizer.devices.token import DEVICE_COOKIE_NAME, hash_device_token
from constitution_memorizer.entitlements.models import CONSTITUTION_ACCESS_FULL
from constitution_memorizer.multiuser.settings import MultiUserSettings
from constitution_memorizer.playground.service import activate_law
from constitution_memorizer.progress.db import open_progress_db
from constitution_memorizer.progress.repository import ProgressRepository
from constitution_memorizer.web.app import create_app
from tests.test_devices_m4a import (
    HMAC_SECRET,
    MINI_UNITS,
    PERIOD_END,
    PERIOD_START,
    ROOT,
    USER,
    _add_subscription,
    _authed_client,
    _csrf,
    _devices,
    _login,
    _make_app,
    _mu_settings,
    _overlay_dump,
    _sqlite_repo,
)
from tests.test_devices_m4b import (
    ADMIN,
    DEVICES_PATH,
    _admin_app,
    _seed_user_profile,
    _state_dump,
)

NOW = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
SUPPORT = "support-m4c@example.test"


def _svc(tmp_path: Path) -> DeviceService:
    return DeviceService(_sqlite_repo(tmp_path), hmac_secret=HMAC_SECRET, device_limit=2)


def _ensure(service: DeviceService, token: str, *, now: datetime = NOW):
    return service.ensure_current_device(
        USER,
        token,
        auth_session_id=f"sess-{token}",
        commercially_eligible=True,
        now=now,
    )


def _count(service: DeviceService, *, now: datetime = NOW) -> int:
    return service.count_recent_replacements(USER, now=now)


def _active_ids(service: DeviceService) -> list[str]:
    return [row.id for row in service.list_devices(USER) if not row.is_revoked]


def _hashes(service: DeviceService) -> set[str]:
    return {row.device_key_hash for row in service.list_devices(USER)}


def _cycle_three_replacements(service: DeviceService, *, now: datetime = NOW):
    """A+B originals, then B→C, C→D, D→E. Leaves A+E active, count=3."""

    first = _ensure(service, "tok-a", now=now)
    second = _ensure(service, "tok-b", now=now)
    assert first.current_device_registered and second.current_device_registered
    assert _count(service, now=now) == 0
    service.revoke_device(USER, second.current_device_id, now=now)
    third = _ensure(service, "tok-c", now=now)
    assert third.current_device_registered
    assert _count(service, now=now) == 1
    service.revoke_device(USER, third.current_device_id, now=now)
    fourth = _ensure(service, "tok-d", now=now)
    assert _count(service, now=now) == 2
    service.revoke_device(USER, fourth.current_device_id, now=now)
    fifth = _ensure(service, "tok-e", now=now)
    assert fifth.current_device_registered
    assert _count(service, now=now) == 3
    return first, fifth


def _make_app_email(tmp_path: Path, **extra):
    tmp_path.mkdir(parents=True, exist_ok=True)
    conn = open_progress_db(tmp_path / "progress.db")
    repo = ProgressRepository(conn)
    provider = FakeAuthProvider()
    provider.seed_google_user(
        user_id=USER, email="m4c@example.com", display_name="M4C User"
    )
    settings_kwargs = dict(
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
        RELEVANT_LAWS_ENABLED="true",
        PLAYGROUND_DEVICE_HMAC_SECRET=HMAC_SECRET,
        PLAYGROUND_DEVICE_LIMIT="2",
    )
    settings_kwargs.update(extra)
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "unused.db",
        multiuser=True,
        multiuser_settings=MultiUserSettings(**settings_kwargs),
        auth_provider=provider,
        session_store=InMemorySessionStore(),
        progress_repo=repo,
    )
    return app, repo


# --------------------------------------------------------------------------- #
# Policy constants                                                             #
# --------------------------------------------------------------------------- #
def test_locked_replacement_policy_constants():
    assert DEVICE_REPLACEMENT_WINDOW_DAYS == 30
    assert DEVICE_REPLACEMENT_LIMIT == 3
    assert BLOCK_DEVICE_REPLACEMENT_LIMIT == "device_replacement_limit"
    assert ACTION_CLEAR_DEVICE_REPLACEMENT_LIMIT == "clear_device_replacement_limit"


def test_support_email_optional_at_boot_and_validates_when_set():
    ok = MultiUserSettings(_env_file=None, SUPPORT_EMAIL="")
    assert ok.support_email == ""
    valid = MultiUserSettings(_env_file=None, SUPPORT_EMAIL="ops@example.test")
    assert valid.support_email == "ops@example.test"
    with pytest.raises(ValidationError):
        MultiUserSettings(_env_file=None, SUPPORT_EMAIL="not-an-email")
    with pytest.raises(ValidationError):
        MultiUserSettings(_env_file=None, SUPPORT_EMAIL="support@")
    boot = _mu_settings()
    assert boot.support_email == ""


def test_migration_0023_adds_replacement_and_leaves_0021_0022():
    versions = ROOT / "alembic" / "versions"
    latest = (versions / "20260917_0023_device_replacement.py").read_text(
        encoding="utf-8"
    )
    ios = (versions / "20260917_0022_device_ios_platform.py").read_text(encoding="utf-8")
    original = (versions / "20260916_0021_devices.py").read_text(encoding="utf-8")
    assert 'revision = "20260917_0023"' in latest
    assert 'down_revision = "20260917_0022"' in latest
    assert "user_device_replacement" in latest
    assert "user_id, occurred_at" in latest
    assert "ENABLE ROW LEVEL SECURITY" in latest
    assert "rtc_device" not in latest
    assert "device_key_hash" not in latest
    assert "user_device_replacement" not in original
    assert "user_device_replacement" not in ios
    assert 'revision = "20260917_0022"' in ios


def test_sqlite_schema_creates_replacement_table(tmp_path: Path):
    repo = _sqlite_repo(tmp_path)
    cols = {
        row["name"]
        for row in repo._conn.execute("PRAGMA table_info(user_device_replacement)")
    }
    assert cols >= {
        "id",
        "user_id",
        "revoked_device_id",
        "replacement_device_id",
        "occurred_at",
        "created_at",
        "platform",
    }
    assert "device_key_hash" not in cols
    indexes = [
        dict(row)
        for row in repo._conn.execute(
            "PRAGMA index_list(user_device_replacement)"
        )
    ]
    assert any("user_occurred" in row["name"] for row in indexes)


# --------------------------------------------------------------------------- #
# Counting                                                                     #
# --------------------------------------------------------------------------- #
def test_originals_are_not_replacements_then_fourth_is_blocked(tmp_path: Path):
    service = _svc(tmp_path)
    first, fifth = _cycle_three_replacements(service)
    assert _count(service) == 3
    service.revoke_device(USER, fifth.current_device_id, now=NOW)
    blocked = _ensure(service, "tok-f")
    assert blocked.current_device_registered is False
    assert blocked.block_reason == BLOCK_DEVICE_REPLACEMENT_LIMIT
    assert _count(service) == 3
    digest_f = hash_device_token(HMAC_SECRET, "tok-f")
    assert digest_f not in _hashes(service)
    repo = service._repo
    outcome = repo.register_if_under_cap(
        USER,
        device_key_hash=digest_f,
        platform="web",
        display_name=None,
        limit=2,
        now=NOW,
    )
    assert outcome.status == REGISTER_REPLACEMENT_LIMIT
    assert outcome.device is None
    assert first.current_device_id in _active_ids(service)


def test_rolling_window_drops_event_older_than_30_days(tmp_path: Path):
    service = _svc(tmp_path)
    t = lambda days: NOW - timedelta(days=days)
    a = _ensure(service, "tok-a", now=t(40))
    b = _ensure(service, "tok-b", now=t(40))
    service.revoke_device(USER, b.current_device_id, now=t(31))
    c = _ensure(service, "tok-c", now=t(31))
    service.revoke_device(USER, c.current_device_id, now=t(20))
    d = _ensure(service, "tok-d", now=t(20))
    service.revoke_device(USER, d.current_device_id, now=t(10))
    e = _ensure(service, "tok-e", now=t(10))
    assert _count(service, now=NOW) == 2
    service.revoke_device(USER, e.current_device_id, now=NOW)
    allowed = _ensure(service, "tok-f", now=NOW)
    assert allowed.current_device_registered is True
    assert allowed.block_reason is None
    assert _count(service, now=NOW) == 3
    assert a.current_device_id in _active_ids(service)


def test_non_events_do_not_increment_replacement_count(tmp_path: Path):
    client, repo = _authed_client(tmp_path)
    service = _devices(client)
    first_sub = _add_subscription(client)
    assert client.get("/playground").status_code == 200
    assert _count(service) == 0
    client.post("/logout", follow_redirects=False)
    _login(client)
    assert client.get("/playground").status_code == 200
    assert _count(service) == 0
    assert client.get("/playground").status_code == 200
    assert client.get("/playground").status_code == 200
    assert _count(service) == 0
    assert client.get(DEVICES_PATH).status_code == 200
    assert _count(service) == 0
    client.app.state.subscriptions.update_subscription_state(
        USER, first_sub.id, status="expired"
    )
    client.app.state.subscriptions.mark_not_current(USER, first_sub.id)
    _add_subscription(client, tier="pro")
    assert client.get("/playground").status_code == 200
    assert _count(service) == 0
    app, _ = _make_app(tmp_path / "third")
    a, b, c = TestClient(app), TestClient(app), TestClient(app)
    _login(a)
    _add_subscription(a)
    _login(b)
    _login(c)
    assert a.get("/playground").status_code == 200
    assert b.get("/playground").status_code == 200
    blocked = c.get("/playground")
    assert "device_limit" in blocked.text
    other = _devices(a)
    assert _count(other) == 0
    device_b = next(
        row
        for row in other.list_devices(USER)
        if row.device_key_hash
        == hash_device_token(HMAC_SECRET, b.cookies.get(DEVICE_COOKIE_NAME))
    )
    other.revoke_device(USER, device_b.id)
    assert _count(other) == 0
    del repo


def test_existing_registered_device_stays_allowed_at_churn_cap(tmp_path: Path):
    service = _svc(tmp_path)
    first, fifth = _cycle_three_replacements(service)
    allowed = service.inspect_current_device(USER, "tok-a")
    assert allowed.current_device_registered is True
    assert allowed.current_device_allowed is True
    assert allowed.block_reason is None
    capped = service.inspect_current_device(USER, "tok-new")
    assert capped.block_reason == "device_limit"
    service.revoke_device(USER, fifth.current_device_id, now=NOW)
    blocked = service.inspect_current_device(USER, "tok-new")
    assert blocked.block_reason == BLOCK_DEVICE_REPLACEMENT_LIMIT
    still_a = service.ensure_current_device(
        USER, "tok-a", auth_session_id="sess-a", commercially_eligible=True, now=NOW
    )
    assert still_a.current_device_allowed is True
    assert still_a.block_reason is None
    assert first.current_device_id in _active_ids(service)


def test_concurrent_replacements_cannot_exceed_three(tmp_path: Path):
    path = tmp_path / "race.db"
    setup = sqlite3.connect(str(path), check_same_thread=False)
    setup.row_factory = sqlite3.Row
    setup.execute("PRAGMA journal_mode=WAL")
    setup.execute("PRAGMA busy_timeout = 8000")
    setup.execute("PRAGMA foreign_keys = ON")
    ensure_sqlite_schema(setup)
    seed = SqliteDeviceRepository(setup)
    service = DeviceService(seed, hmac_secret=HMAC_SECRET, device_limit=2)
    a = _ensure(service, "tok-a")
    b = _ensure(service, "tok-b")
    service.revoke_device(USER, b.current_device_id, now=NOW)
    c = _ensure(service, "tok-c")
    service.revoke_device(USER, c.current_device_id, now=NOW)
    d = _ensure(service, "tok-d")
    service.revoke_device(USER, d.current_device_id, now=NOW)
    assert a.current_device_registered
    assert _count(service) == 2
    assert len(_active_ids(service)) == 1

    results: list = []

    def _worker(label: str) -> None:
        conn = sqlite3.connect(str(path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 8000")
        conn.execute("PRAGMA foreign_keys = ON")
        repo = SqliteDeviceRepository(conn)
        svc = DeviceService(repo, hmac_secret=HMAC_SECRET, device_limit=2)
        access = svc.ensure_current_device(
            USER,
            f"race-{label}",
            auth_session_id=f"sess-{label}",
            commercially_eligible=True,
            now=NOW,
        )
        results.append(access)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futs = [pool.submit(_worker, "x"), pool.submit(_worker, "y")]
        for fut in futs:
            fut.result(timeout=10)

    allowed = [row for row in results if row.current_device_registered]
    assert len(allowed) == 1
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    final = SqliteDeviceRepository(conn)
    final_service = DeviceService(final, hmac_secret=HMAC_SECRET, device_limit=2)
    assert _count(final_service) == 3
    assert final.count_active(USER) <= 2


def test_registration_counts_replacements_inside_lock():
    sqlite_src = inspect.getsource(SqliteDeviceRepository.register_if_under_cap)
    assert "REGISTER_REPLACEMENT_LIMIT" in sqlite_src
    assert "_count_recent_locked" in sqlite_src
    assert "_unpaired_revoked_locked" in sqlite_src
    pg_src = inspect.getsource(
        __import__(
            "constitution_memorizer.devices.postgres",
            fromlist=["PostgresDeviceRepository"],
        ).PostgresDeviceRepository.register_if_under_cap
    )
    assert "pg_advisory_xact_lock" in pg_src
    assert "REGISTER_REPLACEMENT_LIMIT" in pg_src
    ensure_src = inspect.getsource(DeviceService.ensure_current_device)
    assert "count_recent_replacements" not in ensure_src
    assert "register_if_under_cap" in ensure_src


# --------------------------------------------------------------------------- #
# HTTP gate / SUPPORT_EMAIL                                                    #
# --------------------------------------------------------------------------- #
def test_replacement_limit_gate_with_configured_support_email(tmp_path: Path):
    app, repo = _make_app_email(tmp_path, SUPPORT_EMAIL=SUPPORT)
    clients = [TestClient(app) for _ in range(6)]
    a, b, c, d, e, f = clients
    for client in clients:
        _login(client)
    _add_subscription(a)
    activate_law(app.state.playground, USER, "ndps")
    before = _state_dump(repo.conn, USER)
    assert a.get("/playground").status_code == 200
    assert b.get("/playground").status_code == 200
    service = _devices(a)

    def _row_for(client: TestClient):
        digest = hash_device_token(
            HMAC_SECRET, client.cookies.get(DEVICE_COOKIE_NAME)
        )
        return next(
            row for row in service.list_devices(USER) if row.device_key_hash == digest
        )

    service.revoke_device(USER, _row_for(b).id)
    assert c.get("/playground").status_code == 200
    service.revoke_device(USER, _row_for(c).id)
    assert d.get("/playground").status_code == 200
    service.revoke_device(USER, _row_for(d).id)
    assert e.get("/playground").status_code == 200
    service.revoke_device(USER, _row_for(e).id)
    blocked = f.get("/playground")
    assert blocked.status_code == 200
    assert 'data-playground-gate="device_replacement_limit"' in blocked.text
    assert "Too many recent device changes" in blocked.text
    assert "Contact support" in blocked.text
    assert f"mailto:{SUPPORT}" in blocked.text
    assert "Back to Constitution" in blocked.text
    assert "/dashboard" in blocked.text
    lower = blocked.text.lower()
    assert "3 replacements" not in lower
    assert "30-day" not in lower
    assert "30 days" not in lower
    assert SUPPORT in blocked.text
    assert "Subscribe" not in blocked.text
    assert "Upgrade" not in blocked.text
    assert a.get("/playground").status_code == 200
    assert _count(service) == 3
    digest_f = hash_device_token(
        HMAC_SECRET, f.cookies.get(DEVICE_COOKIE_NAME)
    )
    assert digest_f not in {row.device_key_hash for row in service.list_devices(USER)}
    assert _state_dump(repo.conn, USER) == before
    commercial = app.state.entitlement_service.resolve(USER, now=NOW)
    assert commercial.is_subscribed is True
    assert commercial.tier == "plus"
    assert commercial.constitution_access == CONSTITUTION_ACCESS_FULL
    laws = f.get("/laws")
    assert laws.status_code == 200


def test_replacement_limit_gate_omits_support_when_email_missing(tmp_path: Path):
    app, _repo = _make_app_email(
        tmp_path, LEGAL_SUPPORT_EMAIL="legal@example.test"
    )
    clients = [TestClient(app) for _ in range(6)]
    a, b, c, d, e, f = clients
    for client in clients:
        _login(client)
    _add_subscription(a)
    assert a.get("/playground").status_code == 200
    assert b.get("/playground").status_code == 200
    service = _devices(a)

    def _row_for(client: TestClient):
        digest = hash_device_token(
            HMAC_SECRET, client.cookies.get(DEVICE_COOKIE_NAME)
        )
        return next(
            row for row in service.list_devices(USER) if row.device_key_hash == digest
        )

    service.revoke_device(USER, _row_for(b).id)
    assert c.get("/playground").status_code == 200
    service.revoke_device(USER, _row_for(c).id)
    assert d.get("/playground").status_code == 200
    service.revoke_device(USER, _row_for(d).id)
    assert e.get("/playground").status_code == 200
    service.revoke_device(USER, _row_for(e).id)
    blocked = f.get("/playground")
    assert "Too many recent device changes" in blocked.text
    assert "Back to Constitution" in blocked.text
    assert "Contact support" not in blocked.text
    assert "mailto:" not in blocked.text
    assert "legal@example.test" not in blocked.text
    assert "SUPPORT_EMAIL" not in blocked.text
    assert "support@" not in blocked.text.lower()


# --------------------------------------------------------------------------- #
# Admin recovery                                                               #
# --------------------------------------------------------------------------- #
def test_admin_reset_does_not_erase_replacement_history(tmp_path: Path):
    client, repo = _admin_app(tmp_path)
    _seed_user_profile(repo, USER, "member@example.com")
    service: DeviceService = client.app.state.device_service
    _cycle_three_replacements(service)
    assert _count(service) == 3
    viewed = client.get(f"/admin/users/{USER}")
    assert viewed.status_code == 200
    assert "Reset Playground devices" in viewed.text
    assert _count(service) == 3
    devices_before = [(row.id, row.revoked_at is not None) for row in service.list_devices(USER)]
    response = client.post(
        f"/admin/users/{USER}/devices/reset",
        data={"csrf_token": client.cookies.get("rtc_csrf"), "reason": "lost phone"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert _count(service) == 3
    assert all(row.is_revoked for row in service.list_devices(USER))
    assert len(service.list_devices(USER)) == len(devices_before)
    blocked = service.ensure_current_device(
        USER, "tok-after-reset", auth_session_id="sess-n", commercially_eligible=True
    )
    assert blocked.block_reason == BLOCK_DEVICE_REPLACEMENT_LIMIT


def test_admin_clears_replacement_lock_with_audit(tmp_path: Path):
    client, repo = _admin_app(tmp_path)
    _seed_user_profile(repo, USER, "member@example.com")
    service: DeviceService = client.app.state.device_service
    first, fifth = _cycle_three_replacements(service)
    client.app.state.subscriptions.create_subscription_record(
        USER,
        tier="plus",
        status="active",
        billing_period_start=PERIOD_START,
        billing_period_end=PERIOD_END,
        is_current=True,
    )
    activate_law(client.app.state.playground, USER, "ndps")
    before = _state_dump(repo.conn, USER)
    devices_before = [
        (row.id, row.revoked_at, row.device_key_hash) for row in service.list_devices(USER)
    ]
    page = client.get(f"/admin/users/{USER}")
    assert page.status_code == 200
    assert "Clear replacement lock" in page.text
    assert "clear_device_replacement_limit" in page.text
    response = client.post(
        f"/admin/users/{USER}/devices/clear-replacement-limit",
        data={
            "csrf_token": client.cookies.get("rtc_csrf"),
            "reason": "verified owner replacement lockout",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert _count(service) == 0
    devices_after = [
        (row.id, row.revoked_at, row.device_key_hash) for row in service.list_devices(USER)
    ]
    assert devices_after == devices_before
    assert _state_dump(repo.conn, USER) == before
    audit = repo.conn.execute(
        "SELECT * FROM admin_audit_log WHERE action = 'clear_device_replacement_limit'"
    ).fetchone()
    assert audit is not None
    assert audit["admin_user_id"] == str(ADMIN)
    assert audit["target_user_id"] == str(USER)
    assert audit["target_type"] == "user_device_replacement"
    assert audit["reason"] == "verified owner replacement lockout"
    before_state = json.loads(audit["before_state"])
    after_state = json.loads(audit["after_state"])
    assert before_state["recent_replacement_count"] == 3
    assert after_state["recent_replacement_count"] == 0
    blob = json.dumps({"before": before_state, "after": after_state})
    assert "device_key_hash" not in blob
    assert HMAC_SECRET not in blob
    assert "tok-a" not in blob
    service.revoke_device(USER, fifth.current_device_id, now=NOW)
    allowed = _ensure(service, "tok-after-clear")
    assert allowed.current_device_registered is True
    assert _count(service) == 1
    assert first.current_device_id in _active_ids(service)


def test_non_admin_cannot_clear_replacement_lock(tmp_path: Path):
    client, _repo = _authed_client(tmp_path)
    response = client.post(
        f"/admin/users/{USER}/devices/clear-replacement-limit",
        data={**_csrf(client), "reason": "nope"},
        follow_redirects=False,
    )
    assert response.status_code == 404


def test_admin_clear_requires_reason_and_csrf(tmp_path: Path):
    client, repo = _admin_app(tmp_path)
    _seed_user_profile(repo, USER, "member@example.com")
    csrf = client.cookies.get("rtc_csrf")
    missing_reason = client.post(
        f"/admin/users/{USER}/devices/clear-replacement-limit",
        data={"csrf_token": csrf, "reason": "  "},
        follow_redirects=False,
    )
    assert missing_reason.status_code == 400
    missing_csrf = client.post(
        f"/admin/users/{USER}/devices/clear-replacement-limit",
        data={"reason": "verified"},
        follow_redirects=False,
    )
    assert missing_csrf.status_code == 403


def test_admin_clear_audit_failure_rolls_back(tmp_path: Path):
    conn = sqlite3.connect(tmp_path / "devices.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    ensure_sqlite_schema(conn)
    conn.execute(
        """
        CREATE TABLE admin_audit_log (
            id TEXT PRIMARY KEY,
            admin_user_id TEXT NOT NULL,
            action TEXT NOT NULL,
            target_user_id TEXT,
            target_type TEXT,
            target_id TEXT,
            before_state TEXT,
            after_state TEXT,
            reason TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    repo = SqliteDeviceRepository(conn)
    service = DeviceService(repo, hmac_secret=HMAC_SECRET, device_limit=2)
    _cycle_three_replacements(service)
    assert _count(service) == 3
    conn.execute("DROP TABLE admin_audit_log")
    conn.commit()
    with pytest.raises(Exception):
        service.clear_device_replacement_limit_audited(
            USER, admin_user_id=ADMIN, reason="support recovery"
        )
    assert _count(service) == 3


def test_no_m5_roster_schema_from_churn_batch():
    devices = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "src/constitution_memorizer/devices").glob("*.py")
    )
    access = (ROOT / "src/constitution_memorizer/playground/access.py").read_text(
        encoding="utf-8"
    )
    migration = (
        ROOT / "alembic" / "versions" / "20260917_0023_device_replacement.py"
    ).read_text(encoding="utf-8")
    blob = devices + access + migration
    assert "user_playground_period" not in blob
    assert "user_playground_roster_item" not in blob
    assert "/playground/roster" not in blob
    versions = [path.name for path in (ROOT / "alembic" / "versions").glob("*.py")]
    assert not any("playground_period" in name for name in versions)
    env = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "SUPPORT_EMAIL=" in env
    assert "support@recall" not in env.lower()
