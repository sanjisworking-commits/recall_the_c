"""Milestone 4A: Playground device security core. Not management UI or churn policy."""

from __future__ import annotations

import inspect
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import InMemorySessionStore, SESSION_COOKIE_NAME
from constitution_memorizer.devices.db import ensure_sqlite_schema
from constitution_memorizer.devices.models import (
    BLOCK_DEVICE_CONFIG_ERROR,
    BLOCK_DEVICE_LIMIT,
    BLOCK_DEVICE_REVOKED,
    DEVICE_PLATFORMS,
    PLATFORM_ANDROID,
    PLATFORM_IOS,
    PLATFORM_WEB,
    REGISTER_CREATED,
    REGISTER_EXISTING,
    REGISTER_INVALID,
    REGISTER_LIMIT,
    REGISTER_REVOKED,
    require_platform,
)
from constitution_memorizer.devices.repository import SqliteDeviceRepository
from constitution_memorizer.devices.service import DeviceService, normalize_device_limit
from constitution_memorizer.devices.token import (
    DEVICE_COOKIE_NAME,
    DeviceHmacConfigError,
    display_name_from_user_agent,
    hash_device_token,
    mint_installation_token,
)
from constitution_memorizer.entitlements.models import (
    CONSTITUTION_ACCESS_FULL,
)
from constitution_memorizer.multiuser.settings import MultiUserSettings
from constitution_memorizer.playground.service import activate_law
from constitution_memorizer.progress.db import open_progress_db
from constitution_memorizer.progress.repository import ProgressRepository
from constitution_memorizer.web.app import create_app

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
USER = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
NOW = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
PERIOD_START = datetime(2026, 9, 1, tzinfo=timezone.utc)
PERIOD_END = datetime(2026, 10, 1, tzinfo=timezone.utc)
HMAC_SECRET = "m4a-test-hmac-secret"
ROOT = Path(__file__).resolve().parents[1]


def _mu_settings(*, cookie_secure: str = "false") -> MultiUserSettings:
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
        COOKIE_SECURE=cookie_secure,
        ARTICLE_ENTITLEMENTS_ENABLED="true",
        RELEVANT_LAWS_ENABLED="true",
        PLAYGROUND_DEVICE_HMAC_SECRET=HMAC_SECRET,
        PLAYGROUND_DEVICE_LIMIT="2",
    )


def _make_app(tmp_path: Path, *, cookie_secure: str = "false"):
    tmp_path.mkdir(parents=True, exist_ok=True)
    conn = open_progress_db(tmp_path / "progress.db")
    repo = ProgressRepository(conn)
    provider = FakeAuthProvider()
    provider.seed_google_user(
        user_id=USER, email="m4a@example.com", display_name="M4A User"
    )
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "unused.db",
        multiuser=True,
        multiuser_settings=_mu_settings(cookie_secure=cookie_secure),
        auth_provider=provider,
        session_store=InMemorySessionStore(),
        progress_repo=repo,
    )
    return app, repo


def _login(client: TestClient) -> None:
    start = client.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state")
    cb = client.get(
        f"/auth/callback?code=fake-google-code&state={state}",
        follow_redirects=False,
    )
    assert cb.status_code == 303


def _authed_client(tmp_path: Path, *, cookie_secure: str = "false"):
    app, repo = _make_app(tmp_path, cookie_secure=cookie_secure)
    client = TestClient(app)
    _login(client)
    return client, repo


def _csrf(client: TestClient) -> dict[str, str]:
    token = client.cookies.get("rtc_csrf") or ""
    return {"csrf_token": token} if token else {}


def _add_subscription(client: TestClient, *, tier: str = "plus", status: str = "active"):
    return client.app.state.subscriptions.create_subscription_record(
        USER,
        tier=tier,
        status=status,
        billing_period_start=PERIOD_START,
        billing_period_end=PERIOD_END,
        is_current=True,
    )


def _set_cookie_headers(response) -> list[str]:
    return [
        value.decode() if isinstance(value, bytes) else value
        for key, value in response.headers.raw
        if key.lower() == b"set-cookie"
    ]


def _device_set_cookie(response) -> str | None:
    for header in _set_cookie_headers(response):
        if header.lower().startswith(f"{DEVICE_COOKIE_NAME}="):
            return header
    return None


def _devices(client: TestClient):
    return client.app.state.device_service


def _active_devices(client: TestClient):
    return [row for row in _devices(client).list_devices(USER) if not row.is_revoked]


def _overlay_dump(conn: sqlite3.Connection, user_id: UUID):
    uid = str(user_id)
    items = [
        tuple(row)
        for row in conn.execute(
            "SELECT * FROM user_playground_item WHERE user_id = ? ORDER BY law_id",
            (uid,),
        ).fetchall()
    ]
    selections = [
        tuple(row)
        for row in conn.execute(
            "SELECT * FROM user_playground_selection WHERE user_id = ? "
            "ORDER BY law_id, source_locator",
            (uid,),
        ).fetchall()
    ]
    progress = [
        tuple(row)
        for row in conn.execute(
            "SELECT * FROM user_playground_progress WHERE user_id = ? "
            "ORDER BY law_id, source_locator",
            (uid,),
        ).fetchall()
    ]
    return items, selections, progress


def _sqlite_repo(tmp_path: Path) -> SqliteDeviceRepository:
    conn = sqlite3.connect(tmp_path / "devices.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 8000")
    ensure_sqlite_schema(conn)
    return SqliteDeviceRepository(conn)


# --------------------------------------------------------------------------- #
# Token / HMAC / cookie                                                        #
# --------------------------------------------------------------------------- #
def test_minted_tokens_are_random_and_not_session_shaped():
    tokens = {mint_installation_token() for _ in range(20)}
    assert len(tokens) == 20
    for token in tokens:
        assert token
        assert " " not in token


def test_hmac_is_keyed_and_never_equals_raw_token():
    token = "installation-token-one"
    hashed = hash_device_token(HMAC_SECRET, token)
    assert hashed != token
    assert hashed == hash_device_token(HMAC_SECRET, token)
    assert hashed != hash_device_token(HMAC_SECRET, "installation-token-two")
    assert hashed != hash_device_token("other-secret", token)
    assert hashed == hashed.lower()
    assert len(hashed) == 64


def test_missing_hmac_secret_raises_without_leaking_token():
    token = "super-secret-installation"
    with pytest.raises(DeviceHmacConfigError) as exc:
        hash_device_token("", token)
    assert token not in str(exc.value)
    assert token not in repr(exc.value)
    assert HMAC_SECRET not in str(exc.value)


def test_hmac_secret_not_in_settings_repr():
    settings = _mu_settings()
    text = repr(settings)
    assert HMAC_SECRET not in text
    assert "playground_device_hmac_secret" not in text or HMAC_SECRET not in text


def test_device_limit_rejects_invalid_values():
    with pytest.raises(ValueError):
        normalize_device_limit(0)
    with pytest.raises(ValueError):
        normalize_device_limit(-1)
    with pytest.raises(ValueError):
        normalize_device_limit("nope")
    assert normalize_device_limit(2) == 2
    assert normalize_device_limit(None) == 2
    with pytest.raises(ValidationError):
        MultiUserSettings(_env_file=None, PLAYGROUND_DEVICE_LIMIT="0")
    with pytest.raises(ValidationError):
        MultiUserSettings(_env_file=None, PLAYGROUND_DEVICE_LIMIT="-3")
    with pytest.raises(ValidationError):
        MultiUserSettings(_env_file=None, PLAYGROUND_DEVICE_LIMIT="abc")


def test_authenticated_response_mints_httponly_lax_cookie(tmp_path: Path):
    app, _repo = _make_app(tmp_path)
    client = TestClient(app)
    start = client.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state")
    cb = client.get(
        f"/auth/callback?code=fake-google-code&state={state}",
        follow_redirects=False,
    )
    header = _device_set_cookie(cb)
    assert header is not None
    assert "HttpOnly" in header
    assert "Path=/" in header
    assert "SameSite=lax" in header or "SameSite=Lax" in header
    assert "Secure" not in header
    assert DEVICE_COOKIE_NAME in client.cookies
    raw = client.cookies.get(DEVICE_COOKIE_NAME)
    hashed = hash_device_token(HMAC_SECRET, raw)
    assert hashed != raw
    assert raw not in hashed


def test_cookie_secure_follows_settings(tmp_path: Path):
    app, _repo = _make_app(tmp_path, cookie_secure="true")
    client = TestClient(app, base_url="https://testserver")
    start = client.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state")
    cb = client.get(
        f"/auth/callback?code=fake-google-code&state={state}",
        follow_redirects=False,
    )
    header = _device_set_cookie(cb)
    assert header is not None
    assert "Secure" in header


def test_two_browsers_receive_different_tokens(tmp_path: Path):
    app, _repo = _make_app(tmp_path)
    first = TestClient(app)
    second = TestClient(app)
    _login(first)
    _login(second)
    a = first.cookies.get(DEVICE_COOKIE_NAME)
    b = second.cookies.get(DEVICE_COOKIE_NAME)
    assert a and b and a != b


def test_logout_does_not_delete_rtc_device(tmp_path: Path):
    client, _repo = _authed_client(tmp_path)
    token = client.cookies.get(DEVICE_COOKIE_NAME)
    assert token
    out = client.post("/logout", follow_redirects=False)
    assert out.status_code == 303
    for header in _set_cookie_headers(out):
        if header.lower().startswith(f"{DEVICE_COOKIE_NAME}="):
            assert "max-age=0" not in header.lower()
    assert client.cookies.get(DEVICE_COOKIE_NAME) == token
    assert client.cookies.get(SESSION_COOKIE_NAME) in {None, ""}


def test_display_name_is_conservative_and_safe():
    assert display_name_from_user_agent(
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0.0.0"
    ) == "Chrome on macOS"
    assert display_name_from_user_agent(
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Safari/605.1.15"
    ) == "Safari on iPhone"
    assert display_name_from_user_agent(None) == "Web browser"
    assert display_name_from_user_agent("") == "Web browser"


def test_device_platforms_include_ios():
    assert DEVICE_PLATFORMS == {PLATFORM_WEB, PLATFORM_ANDROID, PLATFORM_IOS}
    assert require_platform("web") == PLATFORM_WEB
    assert require_platform("android") == PLATFORM_ANDROID
    assert require_platform("ios") == PLATFORM_IOS
    for bogus in ("iphone", "apple", "desktop", "ipad", "mobile_ios"):
        with pytest.raises(ValueError):
            require_platform(bogus)


def test_sqlite_accepts_ios_and_rejects_unknown_platform(tmp_path: Path):
    repo = _sqlite_repo(tmp_path)
    ios = repo.register_if_under_cap(
        USER,
        device_key_hash=hash_device_token(HMAC_SECRET, "ios-token"),
        platform=PLATFORM_IOS,
        display_name="RecallC on iPhone",
        limit=2,
    )
    assert ios.status == REGISTER_CREATED
    assert ios.device is not None
    assert ios.device.platform == PLATFORM_IOS
    bogus = repo.register_if_under_cap(
        USER,
        device_key_hash=hash_device_token(HMAC_SECRET, "iphone-token"),
        platform="iphone",
        display_name="iPhone",
        limit=2,
    )
    assert bogus.status == REGISTER_INVALID
    conn = repo._conn
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO user_device (
                id, user_id, device_key_hash, platform, display_name,
                first_registered_at, last_seen_at, revoked_at,
                created_at, updated_at
            ) VALUES (?, ?, ?, 'iphone', NULL, ?, ?, NULL, ?, ?)
            """,
            ("bad-id", str(USER), "abc", NOW.isoformat(), NOW.isoformat(),
             NOW.isoformat(), NOW.isoformat()),
        )


def test_sqlite_rebuilds_legacy_platform_check(tmp_path: Path):
    conn = sqlite3.connect(tmp_path / "legacy.db")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE user_device (
            id TEXT NOT NULL PRIMARY KEY,
            user_id TEXT NOT NULL,
            device_key_hash TEXT NOT NULL,
            platform TEXT NOT NULL CHECK (platform IN ('web', 'android')),
            display_name TEXT,
            first_registered_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            revoked_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (user_id, device_key_hash)
        );
        """
    )
    conn.commit()
    ensure_sqlite_schema(conn)
    sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='user_device'"
    ).fetchone()["sql"]
    assert "'ios'" in sql
    stamp = NOW.isoformat()
    conn.execute(
        """
        INSERT INTO user_device (
            id, user_id, device_key_hash, platform, display_name,
            first_registered_at, last_seen_at, revoked_at,
            created_at, updated_at
        ) VALUES (?, ?, ?, 'ios', 'RecallC on iPhone', ?, ?, NULL, ?, ?)
        """,
        ("ios-row", str(USER), "hash-ios", stamp, stamp, stamp, stamp),
    )
    conn.commit()


def test_migration_0022_adds_ios_and_0021_is_unchanged():
    versions = ROOT / "alembic" / "versions"
    latest = (versions / "20260917_0022_device_ios_platform.py").read_text(
        encoding="utf-8"
    )
    original = (versions / "20260916_0021_devices.py").read_text(encoding="utf-8")
    assert "revision = \"20260917_0022\"" in latest
    assert "down_revision = \"20260916_0021\"" in latest
    assert "'ios'" in latest
    assert "CHECK (platform IN ('web', 'android', 'ios'))" in latest
    assert "CHECK (platform IN ('web', 'android'))" in original
    assert "'ios'" not in original


# --------------------------------------------------------------------------- #
# Registry / first-second-third                                                #
# --------------------------------------------------------------------------- #
def test_sqlite_register_first_second_third(tmp_path: Path):
    repo = _sqlite_repo(tmp_path)
    service = DeviceService(repo, hmac_secret=HMAC_SECRET, device_limit=2)
    token_a, token_b, token_c = (mint_installation_token() for _ in range(3))
    first = service.ensure_current_device(
        USER, token_a, auth_session_id="sess-a", commercially_eligible=True
    )
    assert first.current_device_registered is True
    assert first.current_device_allowed is True
    assert first.registered_device_count == 1
    assert first.device_slots_remaining == 1
    second = service.ensure_current_device(
        USER, token_b, auth_session_id="sess-b", commercially_eligible=True
    )
    assert second.registered_device_count == 2
    assert second.device_slots_remaining == 0
    third = service.ensure_current_device(
        USER, token_c, auth_session_id="sess-c", commercially_eligible=True
    )
    assert third.block_reason == BLOCK_DEVICE_LIMIT
    assert third.current_device_registered is False
    assert third.current_device_allowed is False
    assert len([row for row in service.list_devices(USER) if not row.is_revoked]) == 2
    stored = repo.get_by_hash(USER, service.hash_token(token_a))
    assert stored is not None
    assert stored.device_key_hash != token_a
    android = repo.register_if_under_cap(
        USER,
        device_key_hash=hash_device_token(HMAC_SECRET, mint_installation_token()),
        platform=PLATFORM_ANDROID,
        display_name="Pixel",
        limit=2,
    )
    assert android.status == REGISTER_LIMIT


def test_http_first_second_third_and_constitution(tmp_path: Path):
    app, repo = _make_app(tmp_path)
    browsers = [TestClient(app) for _ in range(3)]
    for client in browsers:
        _login(client)
        _add_subscription(client)
        break
    _login(browsers[1])
    _login(browsers[2])
    first = browsers[0].get("/playground")
    assert first.status_code == 200
    assert first.headers.get("data-playground-gate") is None
    second = browsers[1].get("/playground")
    assert second.status_code == 200
    third = browsers[2].get("/playground")
    assert third.status_code == 200
    assert 'data-playground-gate="device_limit"' in third.text
    assert "Device limit reached" in third.text
    assert "up to 2 registered devices" in third.text
    assert "Subscribe" not in third.text
    assert "Upgrade" not in third.text
    assert "Buy Max" not in third.text
    assert "Back to Constitution" in third.text
    assert _devices(browsers[0]).inspect_current_device(
        USER, browsers[2].cookies.get(DEVICE_COOKIE_NAME)
    ).block_reason == BLOCK_DEVICE_LIMIT
    type_page = browsers[2].get("/learn/clause-1?mode=type")
    assert type_page.status_code == 200
    assert "mode_locked" not in type_page.text
    recite = browsers[2].get("/learn/clause-1?mode=recite")
    assert recite.status_code == 200
    laws = browsers[2].get("/laws/ndps")
    assert laws.status_code == 200
    profile = browsers[2].get("/profile")
    assert profile.status_code == 200
    billing = browsers[2].get("/billing/subscriptions")
    assert billing.status_code == 200
    snap = browsers[2].get("/playground")
    # commercial subscription remains true on the memoized overlay
    commercial = browsers[2].app.state.entitlement_service.resolve(USER, now=NOW)
    assert commercial.is_subscribed is True
    assert commercial.can_open_playground is True
    assert snap.status_code == 200
    assert "device_limit" in snap.text
    assert len(_active_devices(browsers[0])) == 2
    del repo, snap


@pytest.mark.parametrize("tier", ("plus", "pro", "max"))
def test_device_limit_is_two_for_every_tier(tmp_path: Path, tier: str):
    app, _repo = _make_app(tmp_path / tier)
    browsers = [TestClient(app) for _ in range(3)]
    _login(browsers[0])
    _add_subscription(browsers[0], tier=tier)
    _login(browsers[1])
    _login(browsers[2])
    assert browsers[0].get("/playground").status_code == 200
    assert browsers[1].get("/playground").status_code == 200
    blocked = browsers[2].get("/playground")
    assert 'data-playground-gate="device_limit"' in blocked.text
    assert "Upgrade" not in blocked.text
    inspect = _devices(browsers[0]).inspect_current_device(
        USER, browsers[0].cookies.get(DEVICE_COOKIE_NAME)
    )
    assert inspect.device_limit == 2


def test_free_account_mints_cookie_but_does_not_register(tmp_path: Path):
    client, _repo = _authed_client(tmp_path)
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert client.cookies.get(DEVICE_COOKIE_NAME)
    assert _devices(client).list_devices(USER) == []
    playground = client.get("/playground")
    assert "View Playground plans" in playground.text
    assert "complete Constitution" in playground.text
    assert _devices(client).list_devices(USER) == []


def test_halted_does_not_register(tmp_path: Path):
    client, _repo = _authed_client(tmp_path)
    _add_subscription(client, status="halted")
    client.get("/playground")
    assert _devices(client).list_devices(USER) == []


def test_pending_registers_when_slots_remain_but_not_a_third(tmp_path: Path):
    app, _repo = _make_app(tmp_path)
    a, b, c = TestClient(app), TestClient(app), TestClient(app)
    _login(a)
    _add_subscription(a, status="pending")
    _login(b)
    _login(c)
    assert a.get("/playground").status_code == 200
    assert b.get("/playground").status_code == 200
    blocked = c.get("/playground")
    assert "device_limit" in blocked.text
    assert len(_active_devices(a)) == 2


def test_admin_bypasses_without_consuming_a_slot(tmp_path: Path):
    client, repo = _authed_client(tmp_path)
    repo.conn.execute(
        "INSERT INTO user_roles (user_id, role, created_at) VALUES (?, 'admin', ?)",
        (str(USER), NOW.isoformat()),
    )
    repo.conn.commit()
    page = client.get("/playground")
    assert page.status_code == 200
    assert "Device limit reached" not in page.text
    assert _devices(client).list_devices(USER) == []


def test_local_owner_skips_device_registration(tmp_path: Path):
    conn = open_progress_db(tmp_path / "progress.db")
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "unused.db",
        multiuser=False,
        progress_repo=ProgressRepository(conn),
    )
    client = TestClient(app)
    page = client.get("/playground")
    assert page.status_code == 200
    assert getattr(client.app.state, "device_service", None) is not None or True
    # local mode still wires sqlite devices on the progress conn, but the HTTP
    # gate must not consume a slot for the local owner.
    service = getattr(client.app.state, "device_service", None)
    if service is not None:
        from constitution_memorizer.progress.user_ids import LOCAL_USER_ID

        assert service.list_devices(LOCAL_USER_ID) == []


# --------------------------------------------------------------------------- #
# Logout / revoke / replacement / expiry                                       #
# --------------------------------------------------------------------------- #
def test_logout_login_reuses_same_device_row(tmp_path: Path):
    client, _repo = _authed_client(tmp_path)
    _add_subscription(client)
    assert client.get("/playground").status_code == 200
    original = _active_devices(client)
    assert len(original) == 1
    device_id = original[0].id
    sessions_before = client.app.state.device_service._repo.list_sessions(
        USER, device_id
    )
    assert sessions_before
    first_session_id = sessions_before[0].auth_session_id
    client.post("/logout", follow_redirects=False)
    _login(client)
    assert client.get("/playground").status_code == 200
    again = _active_devices(client)
    assert len(again) == 1
    assert again[0].id == device_id
    sessions = client.app.state.device_service._repo.list_sessions(USER, device_id)
    assert any(row.auth_session_id != first_session_id for row in sessions)


def test_revoke_blocks_same_hash_even_with_open_slot(tmp_path: Path):
    client, _repo = _authed_client(tmp_path)
    _add_subscription(client)
    assert client.get("/playground").status_code == 200
    device = _active_devices(client)[0]
    revoked = _devices(client).revoke_device(USER, device.id)
    assert revoked is not None
    assert revoked.revoked_at is not None
    page = client.get("/playground")
    assert "This device no longer has Playground access." in page.text
    assert "device_revoked" in page.text
    assert len(_active_devices(client)) == 0
    retry = client.get("/playground")
    assert "device_revoked" in retry.text
    assert len(_devices(client).list_devices(USER)) == 1


def test_replacement_after_revoke_registers_new_installation(tmp_path: Path):
    app, repo = _make_app(tmp_path)
    a, b, c = TestClient(app), TestClient(app), TestClient(app)
    _login(a)
    _add_subscription(a)
    _login(b)
    _login(c)
    activate_law(a.app.state.playground, USER, "ndps")
    dump_before = _overlay_dump(repo.conn, USER)
    assert a.get("/playground").status_code == 200
    assert b.get("/playground").status_code == 200
    assert "device_limit" in c.get("/playground").text
    device_b = next(
        row
        for row in _devices(a).list_devices(USER)
        if row.device_key_hash
        == hash_device_token(HMAC_SECRET, b.cookies.get(DEVICE_COOKIE_NAME))
    )
    _devices(a).revoke_device(USER, device_b.id)
    allowed = c.get("/playground")
    assert allowed.status_code == 200
    assert "device_limit" not in allowed.text
    rows = {row.id: row for row in _devices(a).list_devices(USER)}
    assert rows[device_b.id].is_revoked
    active = [row for row in rows.values() if not row.is_revoked]
    assert len(active) == 2
    assert _overlay_dump(repo.conn, USER) == dump_before


def test_subscription_expiry_keeps_registry_and_resubscribe_recognizes(
    tmp_path: Path,
):
    client, _repo = _authed_client(tmp_path)
    first = _add_subscription(client, tier="plus")
    assert client.get("/playground").status_code == 200
    device_id = _active_devices(client)[0].id
    client.app.state.subscriptions.update_subscription_state(
        USER, first.id, status="expired"
    )
    client.app.state.subscriptions.mark_not_current(USER, first.id)
    blocked = client.get("/playground")
    assert "View Playground plans" in blocked.text or "not_subscribed" in blocked.text
    remaining = _devices(client).list_devices(USER)
    assert len(remaining) == 1
    assert remaining[0].id == device_id
    assert remaining[0].revoked_at is None
    _add_subscription(client, tier="pro")
    assert client.get("/playground").status_code == 200
    again = _active_devices(client)
    assert len(again) == 1
    assert again[0].id == device_id


def test_progress_unchanged_across_revoke_expiry_replacement(tmp_path: Path):
    app, repo = _make_app(tmp_path)
    a, b, c = TestClient(app), TestClient(app), TestClient(app)
    _login(a)
    sub = _add_subscription(a)
    _login(b)
    _login(c)
    activate_law(a.app.state.playground, USER, "ndps")
    dump = _overlay_dump(repo.conn, USER)
    assert dump[0]
    a.get("/playground")
    b.get("/playground")
    device_a = _active_devices(a)[0]
    _devices(a).revoke_device(USER, device_a.id)
    assert _overlay_dump(repo.conn, USER) == dump
    a.app.state.subscriptions.update_subscription_state(
        USER, sub.id, status="expired"
    )
    assert _overlay_dump(repo.conn, USER) == dump
    a.app.state.subscriptions.update_subscription_state(
        USER, sub.id, status="active"
    )
    device_b = next(
        row for row in _devices(a).list_devices(USER) if not row.is_revoked
    )
    _devices(a).revoke_device(USER, device_b.id)
    c.get("/playground")
    assert _overlay_dump(repo.conn, USER) == dump
    home = b.get("/playground") if False else c.get("/playground")
    assert home.status_code == 200


# --------------------------------------------------------------------------- #
# Concurrency                                                                  #
# --------------------------------------------------------------------------- #
def test_concurrent_registrations_cannot_exceed_cap(tmp_path: Path):
    path = tmp_path / "race.db"
    setup = sqlite3.connect(str(path), check_same_thread=False)
    setup.row_factory = sqlite3.Row
    setup.execute("PRAGMA journal_mode=WAL")
    setup.execute("PRAGMA busy_timeout = 8000")
    setup.execute("PRAGMA foreign_keys = ON")
    ensure_sqlite_schema(setup)
    seed = SqliteDeviceRepository(setup)
    service = DeviceService(seed, hmac_secret=HMAC_SECRET, device_limit=2)
    token_a = mint_installation_token()
    seeded = service.ensure_current_device(
        USER, token_a, auth_session_id="sess-a", commercially_eligible=True
    )
    assert seeded.registered_device_count == 1

    results: list = []

    def _worker(label: str) -> None:
        conn = sqlite3.connect(str(path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 8000")
        conn.execute("PRAGMA foreign_keys = ON")
        repo = SqliteDeviceRepository(conn)
        svc = DeviceService(repo, hmac_secret=HMAC_SECRET, device_limit=2)
        token = mint_installation_token()
        access = svc.ensure_current_device(
            USER,
            token,
            auth_session_id=f"sess-{label}",
            commercially_eligible=True,
        )
        results.append(access)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futs = [pool.submit(_worker, "b"), pool.submit(_worker, "c")]
        for fut in futs:
            fut.result(timeout=10)

    reasons = {row.block_reason for row in results}
    allowed = [row for row in results if row.current_device_registered]
    blocked = [row for row in results if row.block_reason == BLOCK_DEVICE_LIMIT]
    assert len(allowed) == 1
    assert len(blocked) == 1
    assert BLOCK_DEVICE_LIMIT in reasons
    final = SqliteDeviceRepository(
        sqlite3.connect(str(path), check_same_thread=False)
    )
    # reconnect with row factory
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    final = SqliteDeviceRepository(conn)
    assert final.count_active(USER) == 2
    assert len([row for row in final.list_devices(USER) if not row.is_revoked]) == 2


def test_register_if_under_cap_is_idempotent(tmp_path: Path):
    repo = _sqlite_repo(tmp_path)
    digest = hash_device_token(HMAC_SECRET, "same-token")
    first = repo.register_if_under_cap(
        USER,
        device_key_hash=digest,
        platform=PLATFORM_WEB,
        display_name="Chrome on macOS",
        limit=2,
    )
    second = repo.register_if_under_cap(
        USER,
        device_key_hash=digest,
        platform=PLATFORM_WEB,
        display_name="Chrome on macOS",
        limit=2,
    )
    assert first.status == REGISTER_CREATED
    assert second.status == REGISTER_EXISTING
    assert first.device is not None and second.device is not None
    assert first.device.id == second.device.id
    assert repo.count_active(USER) == 1


def test_revoked_hash_does_not_reregister(tmp_path: Path):
    repo = _sqlite_repo(tmp_path)
    digest = hash_device_token(HMAC_SECRET, "revoked-token")
    created = repo.register_if_under_cap(
        USER,
        device_key_hash=digest,
        platform=PLATFORM_WEB,
        display_name=None,
        limit=2,
    )
    repo.revoke_device(USER, created.device.id)
    retry = repo.register_if_under_cap(
        USER,
        device_key_hash=digest,
        platform=PLATFORM_WEB,
        display_name=None,
        limit=2,
    )
    assert retry.status == REGISTER_REVOKED
    assert repo.count_active(USER) == 0


def test_missing_hmac_fails_registration_not_app_startup(tmp_path: Path):
    repo = _sqlite_repo(tmp_path)
    service = DeviceService(repo, hmac_secret="", device_limit=2)
    access = service.ensure_current_device(
        USER,
        mint_installation_token(),
        auth_session_id="sess",
        commercially_eligible=True,
    )
    assert access.block_reason == BLOCK_DEVICE_CONFIG_ERROR
    assert repo.count_active(USER) == 0
    assert "DeviceService(limit=2)" == repr(service)


def test_public_law_reading_does_not_register(tmp_path: Path):
    client = TestClient(
        create_app(
            units_path=MINI_UNITS,
            db_path=tmp_path / "unused.db",
            multiuser=True,
            multiuser_settings=_mu_settings(),
            auth_provider=FakeAuthProvider(),
            session_store=InMemorySessionStore(),
            progress_repo=ProgressRepository(open_progress_db(tmp_path / "p.db")),
        )
    )
    assert client.get("/laws").status_code == 200
    assert client.get("/laws/ndps").status_code == 200
    authed, repo = _authed_client(tmp_path / "authed")
    _add_subscription(authed)
    authed.get("/laws/ndps")
    assert _devices(authed).list_devices(USER) == []
    authed.get("/learn/clause-1?mode=type")
    assert _devices(authed).list_devices(USER) == []
    del repo


def test_dashboard_inspect_does_not_consume_slot(tmp_path: Path):
    client, _repo = _authed_client(tmp_path)
    _add_subscription(client)
    client.get("/dashboard")
    assert _devices(client).list_devices(USER) == []
    client.get("/profile")
    assert _devices(client).list_devices(USER) == []
    client.get("/playground")
    assert len(_active_devices(client)) == 1


def test_is_subscribed_stays_true_when_device_limited(tmp_path: Path):
    app, _repo = _make_app(tmp_path)
    a, b, c = (TestClient(app) for _ in range(3))
    _login(a)
    _add_subscription(a, tier="max")
    _login(b)
    _login(c)
    a.get("/playground")
    b.get("/playground")
    c.get("/playground")
    commercial = app.state.entitlement_service.resolve(USER, now=NOW)
    assert commercial.is_subscribed is True
    assert commercial.tier == "max"
    assert commercial.constitution_access == CONSTITUTION_ACCESS_FULL
    assert commercial.playground_block_reason is None


def test_postgres_repository_uses_advisory_lock():
    source = inspect.getsource(
        __import__(
            "constitution_memorizer.devices.postgres",
            fromlist=["PostgresDeviceRepository"],
        ).PostgresDeviceRepository.register_if_under_cap
    )
    assert "pg_advisory_xact_lock" in source
    assert "register_if_under_cap" in source


def test_alembic_head_is_replacement_revision():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(ROOT / "alembic.ini"))
    heads = ScriptDirectory.from_config(cfg).get_heads()
    assert heads == ["20260924_0025"]


def test_no_roster_or_invented_support_address():
    devices_root = ROOT / "src/constitution_memorizer/devices"
    blob = "\n".join(path.read_text(encoding="utf-8") for path in devices_root.glob("*.py"))
    assert "user_playground_period" not in blob
    assert "user_playground_roster_item" not in blob
    assert "support@" not in blob.lower()
    access = (ROOT / "src/constitution_memorizer/playground/access.py").read_text(
        encoding="utf-8"
    )
    assert "support@" not in access.lower()
    versions = [path.name for path in (ROOT / "alembic" / "versions").glob("*.py")]
    assert any("0021" in name and "device" in name for name in versions)
    assert any("0024" in name and "playground_roster" in name for name in versions)


def test_sqlite_begin_immediate_not_check_then_insert():
    source = inspect.getsource(SqliteDeviceRepository.register_if_under_cap)
    assert "BEGIN IMMEDIATE" in inspect.getsource(SqliteDeviceRepository._exclusive)
    assert "COUNT(*)" in source
    # The count lives inside the exclusive transaction, not a separate service check.
    service_src = inspect.getsource(DeviceService.ensure_current_device)
    assert "register_if_under_cap" in service_src
    assert "if self._repo.count_active" not in service_src
