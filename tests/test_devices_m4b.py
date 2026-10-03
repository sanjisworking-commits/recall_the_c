"""Milestone 4B: owner device management and audited admin reset.

Replacement-churn rate policy lives in test_devices_m4c.py.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import InMemorySessionStore, SESSION_COOKIE_NAME
from constitution_memorizer.devices.models import (
    DEVICE_PLATFORMS,
    PLATFORM_ANDROID,
    PLATFORM_IOS,
    PLATFORM_WEB,
    DeviceSummary,
    sort_device_summaries,
)
from constitution_memorizer.devices.service import DeviceService
from constitution_memorizer.devices.token import DEVICE_COOKIE_NAME, hash_device_token
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
    USER,
    _add_subscription,
    _authed_client,
    _csrf,
    _devices,
    _login,
    _make_app,
    _overlay_dump,
)

ADMIN = UUID("55555555-5555-4555-8555-555555555555")
OTHER = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
DEVICES_PATH = "/profile/security/devices"
RESET_PATH = f"/admin/users/{USER}/devices/reset"


def _active(client: TestClient):
    return [row for row in _devices(client).list_devices(USER) if not row.is_revoked]


def _state_dump(conn: sqlite3.Connection, user_id: UUID):
    uid = str(user_id)
    return {
        "subscription": [
            tuple(row)
            for row in conn.execute(
                "SELECT * FROM user_subscription WHERE user_id = ? ORDER BY id",
                (uid,),
            ).fetchall()
        ],
        "charges": [
            tuple(row)
            for row in conn.execute(
                """
                SELECT c.* FROM subscription_charge c
                JOIN user_subscription s ON s.id = c.user_subscription_id
                WHERE s.user_id = ?
                ORDER BY c.id
                """,
                (uid,),
            ).fetchall()
        ],
        "overlay": _overlay_dump(conn, user_id),
        "constitution": [
            tuple(row)
            for row in conn.execute(
                "SELECT * FROM learning_unit_progress WHERE user_id = ? "
                "ORDER BY learning_unit_id",
                (uid,),
            ).fetchall()
        ],
    }


def _admin_app(tmp_path: Path):
    conn = open_progress_db(tmp_path / "progress.db")
    repo = ProgressRepository(conn)
    provider = FakeAuthProvider()
    provider.seed_google_user(
        user_id=ADMIN, email="admin@recall.app", display_name="Admin"
    )
    provider.seed_google_user(
        user_id=USER, email="member@example.com", display_name="Member"
    )
    settings = MultiUserSettings(
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
        PLAYGROUND_DEVICE_HMAC_SECRET=HMAC_SECRET,
        PLAYGROUND_DEVICE_LIMIT="2",
    )
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "unused.db",
        multiuser=True,
        multiuser_settings=settings,
        auth_provider=provider,
        session_store=InMemorySessionStore(),
        progress_repo=repo,
    )
    client = TestClient(app)
    _login(client)
    repo.conn.execute(
        "INSERT INTO user_roles (user_id, role, created_at) VALUES (?, 'admin', ?)",
        (str(ADMIN), datetime.now(timezone.utc).isoformat()),
    )
    repo.conn.commit()
    return client, repo


def _seed_user_profile(repo: ProgressRepository, user_id: UUID, email: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    repo.conn.execute(
        """
        INSERT INTO user_profile (
            user_id, display_name, avatar_url, created_at, updated_at,
            email, phone, last_sign_in_at
        ) VALUES (?, ?, NULL, ?, ?, ?, NULL, ?)
        """,
        (str(user_id), "Member", now, now, email, now),
    )
    repo.conn.commit()


def test_guest_devices_page_redirects_to_login(tmp_path: Path):
    app, _repo = _make_app(tmp_path)
    guest = TestClient(app)
    response = guest.get(DEVICES_PATH, follow_redirects=False)
    assert response.status_code == 303
    location = unquote(response.headers.get("location", ""))
    assert "/login" in location
    assert "profile/security/devices" in location


def test_authenticated_users_can_open_devices_regardless_of_billing(tmp_path: Path):
    client, _repo = _authed_client(tmp_path)
    free = client.get(DEVICES_PATH)
    assert free.status_code == 200
    assert "Your devices" in free.text
    assert "0 of 2 devices" in free.text
    created = _add_subscription(client, status="active")
    assert client.get(DEVICES_PATH).status_code == 200
    client.app.state.subscriptions.update_subscription_state(
        USER, created.id, status="expired"
    )
    expired = client.get(DEVICES_PATH)
    assert expired.status_code == 200
    assert "Your devices" in expired.text


def test_profile_links_to_security_devices(tmp_path: Path):
    client, _repo = _authed_client(tmp_path)
    page = client.get("/profile")
    assert page.status_code == 200
    assert "Security" in page.text
    assert "Your devices" in page.text
    assert "Manage devices that can use Playground." in page.text
    assert f'href="{DEVICES_PATH}"' in page.text


def test_current_device_label_uses_hmac_not_user_agent(tmp_path: Path):
    app, _repo = _make_app(tmp_path)
    a, b, c = (TestClient(app) for _ in range(3))
    _login(a)
    _add_subscription(a)
    _login(b)
    _login(c)
    a.get("/playground", headers={"user-agent": "Mozilla/5.0 Chrome/120 Macintosh"})
    b.get("/playground", headers={"user-agent": "Mozilla/5.0 Chrome/120 Macintosh"})
    page_a = a.get(DEVICES_PATH)
    page_b = b.get(DEVICES_PATH)
    assert page_a.status_code == 200
    assert page_a.text.count("This device") == 1
    assert page_b.text.count("This device") == 1
    token_a = hash_device_token(HMAC_SECRET, a.cookies.get(DEVICE_COOKIE_NAME))
    a_id = next(
        row.id for row in _devices(a).list_devices(USER) if row.device_key_hash == token_a
    )
    assert f"confirm={a_id}" in page_a.text
    blocked = c.get("/playground")
    assert "device_limit" in blocked.text
    page_c = c.get(DEVICES_PATH)
    assert page_c.status_code == 200
    assert "This device" not in page_c.text
    assert "2 of 2 devices" in page_c.text


def test_ios_platform_renders_on_management_page(tmp_path: Path):
    client, _repo = _authed_client(tmp_path)
    repo = client.app.state.device_service._repo
    repo.register_if_under_cap(
        USER,
        device_key_hash=hash_device_token(HMAC_SECRET, "native-ios"),
        platform=PLATFORM_IOS,
        display_name="RecallC on iPhone",
        limit=2,
    )
    repo.register_if_under_cap(
        USER,
        device_key_hash=hash_device_token(HMAC_SECRET, "native-android"),
        platform=PLATFORM_ANDROID,
        display_name="RecallC on Android",
        limit=2,
    )
    page = client.get(DEVICES_PATH)
    assert "iOS" in page.text
    assert "Android" in page.text
    assert "invalid" not in page.text.lower()
    assert "RecallC on iPhone" in page.text


def test_safari_iphone_stays_platform_web(tmp_path: Path):
    client, _repo = _authed_client(tmp_path)
    _add_subscription(client)
    client.get(
        "/playground",
        headers={
            "user-agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 Safari/604.1"
            )
        },
    )
    rows = _active(client)
    assert len(rows) == 1
    assert rows[0].platform == PLATFORM_WEB
    page = client.get(DEVICES_PATH)
    assert "Web" in page.text
    assert "Safari on iPhone" in page.text


def test_device_summary_sort_order():
    now = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)
    older = now - timedelta(hours=2)
    newer = now - timedelta(hours=1)
    items = [
        DeviceSummary(
            id="revoked-old",
            platform=PLATFORM_WEB,
            platform_label="Web",
            display_name="Old",
            first_registered_at=older,
            last_seen_at=older,
            revoked_at=now,
            is_current=False,
            is_active=False,
        ),
        DeviceSummary(
            id="active-other",
            platform=PLATFORM_ANDROID,
            platform_label="Android",
            display_name="Other",
            first_registered_at=older,
            last_seen_at=newer,
            revoked_at=None,
            is_current=False,
            is_active=True,
        ),
        DeviceSummary(
            id="active-current",
            platform=PLATFORM_IOS,
            platform_label="iOS",
            display_name="Mine",
            first_registered_at=older,
            last_seen_at=older,
            revoked_at=None,
            is_current=True,
            is_active=True,
        ),
    ]
    ordered = sort_device_summaries(items)
    assert [row.id for row in ordered] == [
        "active-current",
        "active-other",
        "revoked-old",
    ]
    assert "device_key_hash" not in DeviceSummary.__dataclass_fields__
    assert DEVICE_PLATFORMS == {"web", "android", "ios"}


def test_current_revoked_installation_is_labelled_removed(tmp_path: Path):
    client, _repo = _authed_client(tmp_path)
    _add_subscription(client)
    client.get("/playground")
    device = _active(client)[0]
    _devices(client).revoke_device(USER, device.id)
    page = client.get(DEVICES_PATH)
    assert "This device · Removed" in page.text
    assert "Active devices" in page.text
    assert "Removed devices" in page.text
    assert "0 of 2 devices" in page.text


def test_remove_other_device_keeps_session_and_progress(tmp_path: Path):
    app, repo = _make_app(tmp_path)
    a, b = TestClient(app), TestClient(app)
    _login(a)
    _add_subscription(a)
    _login(b)
    activate_law(a.app.state.playground, USER, "ndps")
    before = _state_dump(repo.conn, USER)
    a.get("/playground")
    b.get("/playground")
    token_a = a.cookies.get(DEVICE_COOKIE_NAME)
    device_a = next(
        row
        for row in _devices(a).list_devices(USER)
        if row.device_key_hash == hash_device_token(HMAC_SECRET, token_a)
    )
    device_b = next(
        row for row in _devices(a).list_devices(USER) if row.id != device_a.id
    )
    csrf = _csrf(a)
    response = a.post(
        f"{DEVICES_PATH}/{device_b.id}/remove",
        data=csrf,
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].endswith(f"{DEVICES_PATH}?removed=1")
    refreshed = {row.id: row for row in _devices(a).list_devices(USER)}
    assert refreshed[device_b.id].revoked_at is not None
    assert refreshed[device_a.id].revoked_at is None
    assert a.cookies.get(SESSION_COOKIE_NAME)
    assert a.get("/profile").status_code == 200
    assert len(_active(a)) == 1
    assert _state_dump(repo.conn, USER) == before
    sessions = a.app.state.device_service._repo.list_sessions(USER, device_b.id)
    assert sessions
    assert all(row.revoked_at is not None for row in sessions)


def test_remove_current_device_signs_out_and_keeps_rtc_device(tmp_path: Path):
    client, repo = _authed_client(tmp_path)
    _add_subscription(client)
    activate_law(client.app.state.playground, USER, "ndps")
    before = _state_dump(repo.conn, USER)
    client.get("/playground")
    token = client.cookies.get(DEVICE_COOKIE_NAME)
    device = _active(client)[0]
    csrf = _csrf(client)
    confirm = client.get(f"{DEVICES_PATH}?confirm={device.id}")
    assert "Remove this device?" in confirm.text
    assert "signed out on this device" in confirm.text
    response = client.post(
        f"{DEVICES_PATH}/{device.id}/remove",
        data=csrf,
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "/signed-out" in response.headers.get("location", "")
    assert client.cookies.get(SESSION_COOKIE_NAME) in {None, ""}
    assert client.cookies.get(DEVICE_COOKIE_NAME) == token
    stored = _devices(client).get_device(USER, device.id)
    assert stored is not None and stored.revoked_at is not None
    sessions = client.app.state.device_service._repo.list_sessions(USER, device.id)
    assert sessions and all(row.revoked_at is not None for row in sessions)
    assert _state_dump(repo.conn, USER) == before
    _login(client)
    playground = client.get("/playground")
    assert "This device no longer has Playground access." in playground.text
    assert "device_revoked" in playground.text
    assert "Manage devices" in playground.text
    assert DEVICES_PATH in playground.text
    assert "Subscribe" not in playground.text
    assert "Upgrade" not in playground.text
    assert len(_active(client)) == 0
    assert client.cookies.get(DEVICE_COOKIE_NAME) == token


def test_owner_cannot_remove_another_users_device(tmp_path: Path):
    client, _repo = _authed_client(tmp_path)
    other_repo = client.app.state.device_service._repo
    created = other_repo.register_if_under_cap(
        OTHER,
        device_key_hash=hash_device_token(HMAC_SECRET, "other-token"),
        platform=PLATFORM_WEB,
        display_name="Other",
        limit=2,
    )
    assert created.device is not None
    response = client.post(
        f"{DEVICES_PATH}/{created.device.id}/remove",
        data=_csrf(client),
        follow_redirects=False,
    )
    assert response.status_code == 404
    still = other_repo.get_by_id(OTHER, created.device.id)
    assert still is not None and still.revoked_at is None


def test_remove_requires_csrf(tmp_path: Path):
    client, _repo = _authed_client(tmp_path)
    _add_subscription(client)
    client.get("/playground")
    device = _active(client)[0]
    response = client.post(
        f"{DEVICES_PATH}/{device.id}/remove",
        data={},
        follow_redirects=False,
    )
    assert response.status_code == 403
    assert _active(client)[0].id == device.id


def test_unsubscribed_user_can_remove_a_device(tmp_path: Path):
    app, _repo = _make_app(tmp_path)
    a, b = TestClient(app), TestClient(app)
    _login(a)
    sub = _add_subscription(a)
    _login(b)
    a.get("/playground")
    b.get("/playground")
    device_b = next(
        row
        for row in _devices(a).list_devices(USER)
        if row.device_key_hash
        == hash_device_token(HMAC_SECRET, b.cookies.get(DEVICE_COOKIE_NAME))
    )
    a.app.state.subscriptions.update_subscription_state(USER, sub.id, status="expired")
    a.app.state.subscriptions.mark_not_current(USER, sub.id)
    page = a.get(DEVICES_PATH)
    assert page.status_code == 200
    response = a.post(
        f"{DEVICES_PATH}/{device_b.id}/remove",
        data=_csrf(a),
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert _devices(a).get_device(USER, device_b.id).is_revoked


def test_replacement_from_management_page(tmp_path: Path):
    app, repo = _make_app(tmp_path)
    a, b, c = (TestClient(app) for _ in range(3))
    _login(a)
    _add_subscription(a)
    _login(b)
    _login(c)
    activate_law(a.app.state.playground, USER, "ndps")
    before = _state_dump(repo.conn, USER)
    a.get("/playground")
    b.get("/playground")
    blocked = c.get("/playground")
    assert "Device limit reached" in blocked.text
    assert "Your subscription supports Playground on up to 2 registered devices." in blocked.text
    assert "Manage devices" in blocked.text
    assert "Back to Constitution" in blocked.text
    assert f'href="{DEVICES_PATH}"' in blocked.text
    assert "Upgrade" not in blocked.text
    assert "Subscribe" not in blocked.text
    assert "Get Max" not in blocked.text
    manage = c.get(DEVICES_PATH)
    assert manage.status_code == 200
    assert "This device" not in manage.text
    device_b = next(
        row
        for row in _devices(a).list_devices(USER)
        if row.device_key_hash
        == hash_device_token(HMAC_SECRET, b.cookies.get(DEVICE_COOKIE_NAME))
    )
    removed = c.post(
        f"{DEVICES_PATH}/{device_b.id}/remove",
        data=_csrf(c),
        follow_redirects=False,
    )
    assert removed.status_code == 303
    allowed = c.get("/playground")
    assert allowed.status_code == 200
    assert "device_limit" not in allowed.text
    rows = {row.id: row for row in _devices(a).list_devices(USER)}
    assert rows[device_b.id].is_revoked
    active = [row for row in rows.values() if not row.is_revoked]
    assert len(active) == 2
    token_c = hash_device_token(HMAC_SECRET, c.cookies.get(DEVICE_COOKIE_NAME))
    assert any(row.device_key_hash == token_c for row in active)
    token_a = hash_device_token(HMAC_SECRET, a.cookies.get(DEVICE_COOKIE_NAME))
    assert any(row.device_key_hash == token_a for row in active)
    assert _state_dump(repo.conn, USER) == before


def test_revoked_gate_offers_manage_devices_not_subscribe(tmp_path: Path):
    client, _repo = _authed_client(tmp_path)
    _add_subscription(client)
    client.get("/playground")
    _devices(client).revoke_device(USER, _active(client)[0].id)
    page = client.get("/playground")
    assert "This device no longer has Playground access." in page.text
    assert "Manage devices" in page.text
    assert DEVICES_PATH in page.text
    assert "Subscribe" not in page.text
    assert "Upgrade" not in page.text
    assert "register again" not in page.text.lower()


def test_admin_reset_revokes_devices_and_writes_audit(tmp_path: Path):
    client, repo = _admin_app(tmp_path)
    _seed_user_profile(repo, USER, "member@example.com")
    service: DeviceService = client.app.state.device_service
    service.ensure_current_device(
        USER, "token-a", auth_session_id="sess-a", commercially_eligible=True
    )
    service.ensure_current_device(
        USER, "token-b", auth_session_id="sess-b", commercially_eligible=True
    )
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
    assert len([row for row in service.list_devices(USER) if not row.is_revoked]) == 2
    response = client.post(
        f"/admin/users/{USER}/devices/reset",
        data={"csrf_token": client.cookies.get("rtc_csrf"), "reason": "lost phone"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    rows = service.list_devices(USER)
    assert rows and all(row.is_revoked for row in rows)
    for device in rows:
        bindings = service._repo.list_sessions(USER, device.id)
        assert bindings and all(row.revoked_at is not None for row in bindings)
    assert _state_dump(repo.conn, USER) == before
    audit = repo.conn.execute(
        "SELECT * FROM admin_audit_log WHERE action = 'reset_devices'"
    ).fetchone()
    assert audit is not None
    assert audit["admin_user_id"] == str(ADMIN)
    assert audit["target_user_id"] == str(USER)
    assert audit["target_type"] == "user_device"
    assert audit["reason"] == "lost phone"
    before_state = json.loads(audit["before_state"])
    after_state = json.loads(audit["after_state"])
    assert before_state["active_device_count"] == 2
    assert after_state["active_device_count"] == 0
    blob = json.dumps({"before": before_state, "after": after_state})
    assert "device_key_hash" not in blob
    assert HMAC_SECRET not in blob
    assert "token-a" not in blob
    assert client.get("/admin").status_code == 200


def test_non_admin_cannot_reset_devices(tmp_path: Path):
    client, _repo = _authed_client(tmp_path)
    response = client.post(
        RESET_PATH,
        data={"csrf_token": client.cookies.get("rtc_csrf"), "reason": "nope"},
        follow_redirects=False,
    )
    assert response.status_code == 404


def test_admin_reset_requires_reason_and_csrf(tmp_path: Path):
    client, repo = _admin_app(tmp_path)
    _seed_user_profile(repo, USER, "member@example.com")
    csrf = client.cookies.get("rtc_csrf")
    missing_reason = client.post(
        f"/admin/users/{USER}/devices/reset",
        data={"csrf_token": csrf, "reason": "  "},
        follow_redirects=False,
    )
    assert missing_reason.status_code == 400
    missing_csrf = client.post(
        f"/admin/users/{USER}/devices/reset",
        data={"reason": "lost phone"},
        follow_redirects=False,
    )
    assert missing_csrf.status_code == 403


def test_admin_reset_audit_failure_rolls_back(tmp_path: Path):
    from constitution_memorizer.devices.db import ensure_sqlite_schema
    from constitution_memorizer.devices.repository import SqliteDeviceRepository

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
    service.ensure_current_device(
        USER, "keep-a", auth_session_id="s-a", commercially_eligible=True
    )
    service.ensure_current_device(
        USER, "keep-b", auth_session_id="s-b", commercially_eligible=True
    )
    conn.execute("DROP TABLE admin_audit_log")
    conn.commit()
    with pytest.raises(Exception):
        service.reset_devices_audited(
            USER, admin_user_id=ADMIN, reason="support reset"
        )
    remaining = [row for row in service.list_devices(USER) if not row.is_revoked]
    assert len(remaining) == 2


def test_no_unrevoke_ui():
    root = Path(__file__).resolve().parents[1]
    devices = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (root / "src/constitution_memorizer/devices").glob("*.py")
    )
    assert "Restore device" not in devices
    assert "undo remove" not in devices.lower()
    assert "/reset-device-limit" not in devices
    html = (root / "src/constitution_memorizer/web/templates/devices.html").read_text(
        encoding="utf-8"
    )
    assert "support@" not in html
    assert "WhatsApp" not in html
    access = (root / "src/constitution_memorizer/playground/access.py").read_text(
        encoding="utf-8"
    )
    assert "Get Max" not in access
    assert "Upgrade" not in access
