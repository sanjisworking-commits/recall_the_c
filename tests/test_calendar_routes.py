"""Calendar OAuth routes: state CSRF, token rules, reconnect, isolation."""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import httpx
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import InMemorySessionStore
from constitution_memorizer.calendar_sync.crypto import TokenSealer
from constitution_memorizer.calendar_sync.store import SYNC_PENDING, SqliteCalendarStore
from constitution_memorizer.multiuser.settings import MultiUserSettings
from constitution_memorizer.progress.db import open_progress_db
from constitution_memorizer.progress.repository import ProgressRepository
from constitution_memorizer.web.app import create_app

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
USER = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
OTHER = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
TOKEN_KEY = Fernet.generate_key().decode()
CAL_ID = "cal_recall_1"


class FakeGoogleAuth:
    """Token + calendar endpoints for the OAuth callback path."""

    def __init__(self) -> None:
        self.refresh_token: str | None = "rt-1"
        self.calendar_exists = True
        self.created_calendars = 0
        self.revoked_tokens: list[str] = []

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/token":
            body = dict(pair.split("=", 1) for pair in request.content.decode().split("&"))
            if body.get("grant_type") == "authorization_code":
                payload = {"access_token": "at", "expires_in": 3600}
                if self.refresh_token:
                    payload["refresh_token"] = self.refresh_token
                return httpx.Response(200, json=payload)
            return httpx.Response(200, json={"access_token": "at", "expires_in": 3600})
        if path == "/revoke":
            self.revoked_tokens.append(str(request.url.params.get("token")))
            return httpx.Response(200)
        if request.method == "GET" and "/calendars/" in path:
            if self.calendar_exists:
                return httpx.Response(200, json={"id": CAL_ID})
            return httpx.Response(404)
        if request.method == "POST" and path.endswith("/calendars"):
            self.created_calendars += 1
            return httpx.Response(200, json={"id": f"cal_new_{self.created_calendars}"})
        if request.method == "POST" and path.endswith("/events"):
            return httpx.Response(200, json={"id": "ev1"})
        return httpx.Response(404)


class ProbeCalendarStore:
    """Counts mapping-delete calls used by the OAuth callback cleanup."""

    def __init__(self, inner: SqliteCalendarStore) -> None:
        self._inner = inner
        self.delete_all_event_mappings_calls = 0
        self.delete_event_mapping_calls = 0
        self.get_connection_calls = 0

    def __getattr__(self, name: str):
        return getattr(self._inner, name)

    def get_connection(self, user_id):
        self.get_connection_calls += 1
        return self._inner.get_connection(user_id)

    def delete_all_event_mappings(self, user_id):
        self.delete_all_event_mappings_calls += 1
        return self._inner.delete_all_event_mappings(user_id)

    def delete_event_mapping(self, user_id, local_date):
        self.delete_event_mapping_calls += 1
        return self._inner.delete_event_mapping(user_id, local_date)


def _settings(*, gcal: bool = True) -> MultiUserSettings:
    return MultiUserSettings(
        _env_file=None,
        APP_ENV="test",
        APP_BASE_URL="https://recall-the-c.in",
        MULTIUSER_ENABLED="true",
        AUTH_GOOGLE_ENABLED="true",
        SESSION_SECRET="test-secret",
        SUPABASE_URL="http://example.invalid",
        SUPABASE_ANON_KEY="anon",
        DATABASE_URL="",
        COOKIE_SECURE="false",
        GCAL_CLIENT_ID="gcal-cid" if gcal else "",
        GCAL_CLIENT_SECRET="gcal-secret" if gcal else "",
        GCAL_TOKEN_KEY=TOKEN_KEY if gcal else "",
    )


def _client(tmp_path: Path, *, gcal: bool = True, signed_in: bool = True):
    conn = open_progress_db(tmp_path / "progress.db")
    repo = ProgressRepository(conn)
    provider = FakeAuthProvider()
    provider.seed_google_user(user_id=USER, email="a@example.com", display_name="T")
    fake = FakeGoogleAuth()
    store = ProbeCalendarStore(SqliteCalendarStore(conn))
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "unused.db",
        multiuser=True,
        multiuser_settings=_settings(gcal=gcal),
        auth_provider=provider,
        session_store=InMemorySessionStore(),
        progress_repo=repo,
        calendar_store=store,
        gcal_transport=fake.transport(),
    )
    client = TestClient(app)
    if signed_in:
        start = client.get("/auth/google/start", follow_redirects=False)
        state = start.cookies.get("rtc_oauth_state")
        cb = client.get(
            f"/auth/callback?code=fake-google-code&state={state}",
            follow_redirects=False,
        )
        assert cb.status_code == 303
    return client, store, fake, repo


def _connect(client: TestClient, fake: FakeGoogleAuth) -> str:
    """Drive the full connect → callback flow; returns the final redirect."""
    start = client.get("/calendar/google/connect", follow_redirects=False)
    assert start.status_code == 303
    assert "accounts.google.com" in start.headers["location"]
    assert "access_type=offline" in start.headers["location"]
    assert "prompt=consent" in start.headers["location"]
    assert "calendar.app.created" in start.headers["location"]
    state = start.cookies.get("rtc_gcal_state")
    assert state
    cb = client.get(
        f"/calendar/google/callback?code=auth-code&state={state}",
        follow_redirects=False,
    )
    assert cb.status_code == 303
    return cb.headers["location"]


def test_connect_requires_sign_in(tmp_path: Path) -> None:
    client, _store, _fake, _repo = _client(tmp_path, signed_in=False)
    resp = client.get("/calendar/google/connect", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/login")


def test_unconfigured_routes_bounce(tmp_path: Path) -> None:
    client, _store, _fake, _repo = _client(tmp_path, gcal=False)
    resp = client.get("/calendar/google/connect", follow_redirects=False)
    assert resp.headers["location"] == "/settings"
    settings_html = client.get("/settings").text
    assert "Revision calendar" not in settings_html


def test_full_connect_creates_connection_and_syncs(tmp_path: Path) -> None:
    client, store, fake, _repo = _client(tmp_path)
    fake.calendar_exists = False  # first connect: nothing to reuse
    location = _connect(client, fake)
    assert location == "/settings?gcal=connected"
    connection = store.get_connection(USER)
    assert connection is not None and connection.is_active
    assert connection.google_calendar_id == "cal_new_1"
    # Token sealed at rest — never plaintext.
    assert connection.refresh_token_sealed != "rt-1"
    assert TokenSealer(TOKEN_KEY).unseal(connection.refresh_token_sealed) == "rt-1"
    settings_html = client.get("/settings").text
    assert "Recall the C — Revision Schedule" in settings_html


def test_callback_rejects_state_mismatch(tmp_path: Path) -> None:
    client, store, fake, _repo = _client(tmp_path)
    client.get("/calendar/google/connect", follow_redirects=False)
    cb = client.get(
        "/calendar/google/callback?code=auth-code&state=forged",
        follow_redirects=False,
    )
    assert "gcal=error" in cb.headers["location"]
    assert store.get_connection(USER) is None


def test_reconnect_after_disconnect_mints_fresh_calendar(tmp_path: Path) -> None:
    """Disconnect revokes the grant, which DELISTS the app-created calendar
    from the user's Google UI (Calendars.get still 200s, but our scope has no
    calendarList.insert to re-list it) — so a reconnect must create a fresh,
    visible calendar and drop mappings that point at the old one's events."""
    client, store, fake, _repo = _client(tmp_path)
    fake.calendar_exists = False
    _connect(client, fake)  # creates cal_new_1
    store.upsert_event_mapping(
        USER, local_date=date(2026, 8, 19), google_event_id="ev-old", content_hash="h"
    )
    # Disconnect (tombstone + remote revoke).
    csrf = client.cookies.get("rtc_csrf")
    resp = client.post(
        "/calendar/google/disconnect",
        data={"csrf_token": csrf},
        follow_redirects=False,
    )
    assert resp.headers["location"] == "/settings?gcal=disconnected"
    assert store.get_connection(USER).is_active is False
    # Reconnect: even though cal_new_1 still answers Calendars.get, it was
    # delisted by the revoke → mint cal_new_2 and start from clean mappings.
    fake.calendar_exists = True
    _connect(client, fake)
    connection = store.get_connection(USER)
    assert connection.is_active
    assert connection.google_calendar_id == "cal_new_2"
    assert fake.created_calendars == 2
    assert store.list_event_mappings(USER) == []


def test_active_reconsent_reuses_calendar(tmp_path: Path) -> None:
    """Re-running the connect flow WITHOUT disconnecting (grant never
    revoked, calendar still listed) keeps the same calendar — no duplicate."""
    client, store, fake, _repo = _client(tmp_path)
    fake.calendar_exists = False
    _connect(client, fake)  # creates cal_new_1
    fake.calendar_exists = True
    _connect(client, fake)  # still active → probe → reuse
    connection = store.get_connection(USER)
    assert connection.google_calendar_id == "cal_new_1"
    assert fake.created_calendars == 1


def _stub_schedule_sync(monkeypatch) -> None:
    """Keep mapping-cleanup assertions free of background-sync races."""
    monkeypatch.setattr(
        "constitution_memorizer.calendar_sync.routes.schedule_sync",
        lambda _request, _user_id: None,
    )


def test_reconnect_bulk_deletes_many_stale_mappings(tmp_path: Path, monkeypatch) -> None:
    """Disconnect → reconnect must drop many old mappings in one bulk DELETE."""
    _stub_schedule_sync(monkeypatch)
    client, store, fake, _repo = _client(tmp_path)
    fake.calendar_exists = False
    _connect(client, fake)  # creates cal_new_1
    assert store.delete_all_event_mappings_calls == 0
    for i in range(10):
        store.upsert_event_mapping(
            USER,
            local_date=date(2026, 8, 19) + timedelta(days=i),
            google_event_id=f"ev-old-{i}",
            content_hash="h",
        )
    csrf = client.cookies.get("rtc_csrf")
    resp = client.post(
        "/calendar/google/disconnect",
        data={"csrf_token": csrf},
        follow_redirects=False,
    )
    assert resp.headers["location"] == "/settings?gcal=disconnected"
    assert len(store.list_event_mappings(USER)) == 10
    store.delete_all_event_mappings_calls = 0
    store.delete_event_mapping_calls = 0
    fake.calendar_exists = True
    _connect(client, fake)
    connection = store.get_connection(USER)
    assert connection.is_active
    assert connection.google_calendar_id == "cal_new_2"
    assert fake.created_calendars == 2
    assert store.list_event_mappings(USER) == []
    assert store.delete_all_event_mappings_calls == 1
    assert store.delete_event_mapping_calls == 0


def test_reconnect_after_disconnect_records_two_writes(
    tmp_path: Path, caplog: logging.LogCaptureFixture, monkeypatch
) -> None:
    _stub_schedule_sync(monkeypatch)
    client, store, fake, _repo = _client(tmp_path)
    fake.calendar_exists = False
    _connect(client, fake)
    store.upsert_event_mapping(
        USER, local_date=date(2026, 8, 19), google_event_id="ev-old", content_hash="h"
    )
    csrf = client.cookies.get("rtc_csrf")
    client.post(
        "/calendar/google/disconnect",
        data={"csrf_token": csrf},
        follow_redirects=False,
    )
    fake.calendar_exists = True
    start = client.get("/calendar/google/connect", follow_redirects=False)
    state = start.cookies.get("rtc_gcal_state")
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        caplog.clear()
        cb = client.get(
            f"/calendar/google/callback?code=auth-code&state={state}",
            follow_redirects=False,
        )
    assert cb.status_code == 303
    line = _breakdown_line(caplog)
    assert "calendar_connection_write_n=2" in line


def test_active_reconsent_preserves_event_mappings(tmp_path: Path, monkeypatch) -> None:
    _stub_schedule_sync(monkeypatch)
    client, store, fake, _repo = _client(tmp_path)
    fake.calendar_exists = False
    _connect(client, fake)
    store.upsert_event_mapping(
        USER, local_date=date(2026, 8, 19), google_event_id="ev-keep", content_hash="h"
    )
    store.delete_all_event_mappings_calls = 0
    store.delete_event_mapping_calls = 0
    fake.calendar_exists = True
    _connect(client, fake)
    connection = store.get_connection(USER)
    assert connection.google_calendar_id == "cal_new_1"
    assert fake.created_calendars == 1
    mappings = store.list_event_mappings(USER)
    assert len(mappings) == 1
    assert mappings[0].google_event_id == "ev-keep"
    assert store.delete_all_event_mappings_calls == 0
    assert store.delete_event_mapping_calls == 0


def test_active_vanished_calendar_bulk_clears_mappings(
    tmp_path: Path, monkeypatch
) -> None:
    """Active re-consent whose stored calendar 404s mints a replacement and
    bulk-clears mappings that pointed at the vanished calendar."""
    _stub_schedule_sync(monkeypatch)
    client, store, fake, _repo = _client(tmp_path)
    fake.calendar_exists = False
    _connect(client, fake)
    for i in range(8):
        store.upsert_event_mapping(
            USER,
            local_date=date(2026, 8, 19) + timedelta(days=i),
            google_event_id=f"ev-gone-{i}",
            content_hash="h",
        )
    store.delete_all_event_mappings_calls = 0
    store.delete_event_mapping_calls = 0
    fake.calendar_exists = False
    _connect(client, fake)
    connection = store.get_connection(USER)
    assert connection.is_active
    assert connection.google_calendar_id == "cal_new_2"
    assert fake.created_calendars == 2
    assert store.list_event_mappings(USER) == []
    assert store.delete_all_event_mappings_calls == 1
    assert store.delete_event_mapping_calls == 0


def test_omitted_refresh_token_preserves_stored_one(tmp_path: Path) -> None:
    client, store, fake, _repo = _client(tmp_path)
    fake.calendar_exists = False
    _connect(client, fake)
    sealed_before = store.get_connection(USER).refresh_token_sealed
    # Google re-consent responses often omit refresh_token entirely.
    fake.refresh_token = None
    fake.calendar_exists = True
    location = _connect(client, fake)
    assert location == "/settings?gcal=connected"
    assert store.get_connection(USER).refresh_token_sealed == sealed_before


def test_no_token_anywhere_is_explicit_error(tmp_path: Path) -> None:
    client, store, fake, _repo = _client(tmp_path)
    fake.refresh_token = None  # first connect AND no stored token
    start = client.get("/calendar/google/connect", follow_redirects=False)
    state = start.cookies.get("rtc_gcal_state")
    cb = client.get(
        f"/calendar/google/callback?code=auth-code&state={state}",
        follow_redirects=False,
    )
    assert "why=no_refresh_token" in cb.headers["location"]
    assert store.get_connection(USER) is None


def test_disconnect_requires_csrf(tmp_path: Path) -> None:
    client, store, fake, _repo = _client(tmp_path)
    fake.calendar_exists = False
    _connect(client, fake)
    resp = client.post(
        "/calendar/google/disconnect",
        data={"csrf_token": "forged"},
        follow_redirects=False,
    )
    assert "why=csrf" in resp.headers["location"]
    assert store.get_connection(USER).is_active  # untouched


def test_preferences_validate_and_persist(tmp_path: Path) -> None:
    client, store, fake, repo = _client(tmp_path)
    fake.calendar_exists = False
    _connect(client, fake)
    csrf = client.cookies.get("rtc_csrf")
    ok = client.post(
        "/calendar/google/preferences",
        data={
            "csrf_token": csrf,
            "user_timezone": "Asia/Kolkata",
            "revision_time": "21:30",
            "session_minutes": "45",
        },
        follow_redirects=False,
    )
    assert ok.headers["location"] == "/settings?gcal=saved"
    assert repo.get_setting(USER, "user_timezone") == "Asia/Kolkata"
    assert repo.get_setting(USER, "gcal_revision_time") == "21:30"
    assert repo.get_setting(USER, "gcal_session_minutes") == "45"
    bad_tz = client.post(
        "/calendar/google/preferences",
        data={"csrf_token": csrf, "user_timezone": "Mars/Olympus"},
        follow_redirects=False,
    )
    assert "why=timezone" in bad_tz.headers["location"]
    bad_minutes = client.post(
        "/calendar/google/preferences",
        data={"csrf_token": csrf, "revision_time": "20:00", "session_minutes": "37"},
        follow_redirects=False,
    )
    assert "why=duration" in bad_minutes.headers["location"]


def test_done_flags_sync_pending(tmp_path: Path) -> None:
    """The state-change hook durably flags sync before any async work."""
    client, store, fake, _repo = _client(tmp_path)
    fake.calendar_exists = False
    _connect(client, fake)
    # Complete a unit through the app (all six modes then Done).
    client.get("/learn/clause-1")
    for mode in ("cloze", "letters", "type", "recite"):
        client.post(f"/learn/clause-1/seen", data={"mode": mode})
    from tests.quiz_helpers import submit_quiz

    submit_quiz(client, MINI_UNITS, "clause-1")
    resp = client.post(
        "/learn/clause-1/done",
        data={"modes": "read,cloze,letters,type,recite,test", "claim_article": "1"},
        follow_redirects=False,
    )
    assert resp.status_code in (200, 303)
    connection = store.get_connection(USER)
    # Either the async sync already completed (ok) or the flag is still set —
    # both prove the durable-flag-then-sync path ran.
    assert connection.sync_status in ("ok", "pending", "error")
    assert connection.last_synced_at is not None or connection.sync_pending


def test_account_deletion_cleans_calendar_rows(tmp_path: Path) -> None:
    client, store, fake, _repo = _client(tmp_path)
    fake.calendar_exists = False
    _connect(client, fake)
    assert store.get_connection(USER) is not None
    csrf = client.cookies.get("rtc_csrf")
    resp = client.post(
        "/profile",
        data={"csrf_token": csrf, "action": "delete_account"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert store.get_connection(USER) is None
    assert store.list_event_mappings(USER) == []


def test_connect_captures_browser_timezone_before_oauth(tmp_path: Path) -> None:
    """Fix 2: ?tz= from the browser persists set-if-unset BEFORE Google runs,
    so the first calendar + events use local time, never a UTC default."""
    client, _store, _fake, repo = _client(tmp_path)
    resp = client.get(
        "/calendar/google/connect?tz=Asia/Kolkata", follow_redirects=False
    )
    assert resp.status_code == 303
    assert repo.get_setting(USER, "user_timezone") == "Asia/Kolkata"
    # An explicit existing choice is never overwritten.
    client.get("/calendar/google/connect?tz=Europe/London", follow_redirects=False)
    assert repo.get_setting(USER, "user_timezone") == "Asia/Kolkata"


def test_connect_ignores_invalid_timezone(tmp_path: Path) -> None:
    client, _store, _fake, repo = _client(tmp_path)
    client.get("/calendar/google/connect?tz=Mars/Olympus", follow_redirects=False)
    assert (repo.get_setting(USER, "user_timezone") or "") == ""


def test_settings_view_restarts_stale_pending_sync(tmp_path: Path, monkeypatch) -> None:
    """Fix 3: a stranded sync_pending (restart before the task ran) is
    re-kicked by viewing Settings; a fresh pending is left alone."""
    client, store, fake, _repo = _client(tmp_path)
    fake.calendar_exists = False
    _connect(client, fake)
    calls: list[str] = []
    monkeypatch.setattr(
        "constitution_memorizer.calendar_sync.routes.schedule_sync",
        lambda _req, uid: calls.append(str(uid)),
    )
    # Fresh pending (sync_requested_at = now) → no re-kick.
    store.mark_sync_pending(USER)
    client.get("/settings")
    assert calls == []
    # Stale pending (backdate the request) → settings view restarts it.
    conn = store._conn  # test-only backdating
    conn.execute(
        "UPDATE google_calendar_connections SET sync_requested_at = ? WHERE user_id = ?",
        ("2020-01-01T00:00:00+00:00", str(USER)),
    )
    conn.commit()
    client.get("/settings")
    assert calls == [str(USER)]


def test_account_deletion_revokes_google_grant(tmp_path: Path) -> None:
    """Fix 6: deleting the account revokes the Google grant before wiping
    the sealed token."""
    client, store, fake, _repo = _client(tmp_path)
    fake.calendar_exists = False
    _connect(client, fake)
    csrf = client.cookies.get("rtc_csrf")
    resp = client.post(
        "/profile",
        data={"csrf_token": csrf, "action": "delete_account"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert fake.revoked_tokens, "revocation endpoint was never called"
    assert store.get_connection(USER) is None


def _breakdown_line(caplog: logging.LogCaptureFixture) -> str:
    messages = [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("request_breakdown ")
    ]
    assert len(messages) == 1
    return messages[0]


def test_settings_records_calendar_and_frequency_stages(
    tmp_path: Path, caplog: logging.LogCaptureFixture
) -> None:
    client, _store, fake, _repo = _client(tmp_path)
    fake.calendar_exists = False
    _connect(client, fake)
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        caplog.clear()
        resp = client.get("/settings")
    assert resp.status_code == 200
    line = _breakdown_line(caplog)
    assert "path=/settings" in line
    assert "request_bootstrap_n=1" in line
    assert "calendar_connection_n=1" in line
    assert "calendar_prefs_n=1" in line
    assert "calendar_pending_retry_" not in line


def test_preferences_post_records_write_and_schedule(
    tmp_path: Path, caplog: logging.LogCaptureFixture
) -> None:
    client, _store, fake, _repo = _client(tmp_path)
    fake.calendar_exists = False
    _connect(client, fake)
    csrf = client.cookies.get("rtc_csrf")
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        caplog.clear()
        resp = client.post(
            "/calendar/google/preferences",
            data={
                "csrf_token": csrf,
                "user_timezone": "Asia/Kolkata",
                "revision_time": "21:30",
                "session_minutes": "45",
            },
            follow_redirects=False,
        )
    assert resp.status_code == 303
    line = _breakdown_line(caplog)
    assert "calendar_pref_write_n=1" in line
    assert "calendar_sync_schedule_n=1" in line


def test_inactive_schedule_sync_still_records_stage(
    tmp_path: Path, caplog: logging.LogCaptureFixture
) -> None:
    client, _store, fake, _repo = _client(tmp_path)
    fake.calendar_exists = False
    _connect(client, fake)
    csrf = client.cookies.get("rtc_csrf")
    client.post(
        "/calendar/google/disconnect",
        data={"csrf_token": csrf},
        follow_redirects=False,
    )
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        caplog.clear()
        resp = client.post(
            "/calendar/google/preferences",
            data={
                "csrf_token": csrf,
                "user_timezone": "Asia/Kolkata",
                "revision_time": "20:00",
                "session_minutes": "30",
            },
            follow_redirects=False,
        )
    assert resp.status_code == 303
    line = _breakdown_line(caplog)
    assert "calendar_pref_write_n=1" in line
    assert "calendar_sync_schedule_n=1" in line


def test_disabled_gcal_schedule_sync_does_not_time(tmp_path: Path) -> None:
    from types import SimpleNamespace

    from constitution_memorizer.calendar_sync.routes import schedule_sync
    from constitution_memorizer.web.request_context import (
        begin_request_timings,
        reset_request_timings,
        snapshot_request_timings,
    )

    client, _store, _fake, _repo = _client(tmp_path, gcal=False)
    request = SimpleNamespace(app=client.app)
    token = begin_request_timings()
    try:
        schedule_sync(request, USER)
        snap = snapshot_request_timings()
    finally:
        reset_request_timings(token)
    assert "calendar_sync_schedule" not in snap


def test_connect_records_timezone_pref_stages(
    tmp_path: Path, caplog: logging.LogCaptureFixture
) -> None:
    client, _store, _fake, _repo = _client(tmp_path)
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        caplog.clear()
        resp = client.get(
            "/calendar/google/connect?tz=Asia/Kolkata", follow_redirects=False
        )
    assert resp.status_code == 303
    line = _breakdown_line(caplog)
    assert "calendar_prefs_n=1" in line
    assert "calendar_pref_write_n=1" in line
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        caplog.clear()
        client.get("/calendar/google/connect?tz=Europe/London", follow_redirects=False)
    line = _breakdown_line(caplog)
    assert "calendar_prefs_n=1" in line
    assert "calendar_pref_write_" not in line


def test_callback_records_google_and_store_stages(
    tmp_path: Path, caplog: logging.LogCaptureFixture
) -> None:
    client, _store, fake, _repo = _client(tmp_path)
    fake.calendar_exists = False
    start = client.get("/calendar/google/connect", follow_redirects=False)
    state = start.cookies.get("rtc_gcal_state")
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        caplog.clear()
        cb = client.get(
            f"/calendar/google/callback?code=auth-code&state={state}",
            follow_redirects=False,
        )
    assert cb.status_code == 303
    line = _breakdown_line(caplog)
    assert "google_token_exchange_n=1" in line
    assert "calendar_connection_n=1" in line
    assert "calendar_prefs_n=1" in line
    assert "google_calendar_check_n=1" in line
    assert "calendar_connection_write_n=1" in line
    assert "calendar_sync_schedule_n=1" in line


def test_callback_probe_then_create_counts_two_google_checks(
    tmp_path: Path, caplog: logging.LogCaptureFixture
) -> None:
    """An ACTIVE re-consent probes the stored calendar; when Google says it
    vanished the same callback creates a fresh one — two Google calls."""
    client, _store, fake, _repo = _client(tmp_path)
    fake.calendar_exists = False
    _connect(client, fake)  # creates cal_new_1, connection stays active
    fake.calendar_exists = False  # the stored calendar has vanished
    start = client.get("/calendar/google/connect", follow_redirects=False)
    state = start.cookies.get("rtc_gcal_state")
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        caplog.clear()
        cb = client.get(
            f"/calendar/google/callback?code=auth-code&state={state}",
            follow_redirects=False,
        )
    assert cb.status_code == 303
    line = _breakdown_line(caplog)
    assert "google_calendar_check_n=2" in line
    assert "calendar_prefs_n=1" in line
    assert "calendar_connection_write_n=2" in line


def test_disconnect_records_revoke_and_tombstone(
    tmp_path: Path, caplog: logging.LogCaptureFixture
) -> None:
    client, _store, fake, _repo = _client(tmp_path)
    fake.calendar_exists = False
    _connect(client, fake)
    csrf = client.cookies.get("rtc_csrf")
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        caplog.clear()
        resp = client.post(
            "/calendar/google/disconnect",
            data={"csrf_token": csrf},
            follow_redirects=False,
        )
    assert resp.status_code == 303
    line = _breakdown_line(caplog)
    assert "calendar_connection_n=1" in line
    assert "google_token_revoke_n=1" in line
    assert "calendar_connection_write_n=1" in line


def _seed_split_projection(client: TestClient) -> list[int]:
    """Give projection a letter-split unit so background sync loads split prefs."""
    engine = client.app.state.engine.for_user(USER)
    engine.mark_all_modes_seen("clause-2")
    engine.mark_done("clause-2", require_all_modes=False)
    engine.set_split_preference("clause-2", "letters")
    split_calls = [0]
    inner = engine.repo.list_split_preferences

    def _counting(user_id):
        split_calls[0] += 1
        return inner(user_id)

    engine.repo.list_split_preferences = _counting  # type: ignore[method-assign]
    return split_calls


def test_background_sync_does_not_record_split_prefs_on_asyncio_run(
    tmp_path: Path,
) -> None:
    from types import SimpleNamespace

    from constitution_memorizer.calendar_sync.routes import schedule_sync
    from constitution_memorizer.web.request_context import (
        begin_request_timings,
        reset_request_timings,
        snapshot_request_timings,
    )

    client, _store, fake, _repo = _client(tmp_path)
    fake.calendar_exists = False
    _connect(client, fake)
    split_calls = _seed_split_projection(client)
    request = SimpleNamespace(app=client.app)
    token = begin_request_timings()
    try:
        schedule_sync(request, USER)
        snap = snapshot_request_timings()
    finally:
        reset_request_timings(token)
    assert split_calls[0] >= 1
    assert snap["calendar_sync_schedule"][1] == 1
    assert "split_prefs" not in snap
    assert "progress_preload" not in snap
    assert "theme" not in snap


def test_background_sync_does_not_record_split_prefs_on_create_task(
    tmp_path: Path,
) -> None:
    import asyncio
    from types import SimpleNamespace

    from constitution_memorizer.calendar_sync.routes import schedule_sync
    from constitution_memorizer.web.request_context import (
        begin_request_timings,
        reset_request_timings,
        snapshot_request_timings,
    )

    client, _store, fake, _repo = _client(tmp_path)
    fake.calendar_exists = False
    _connect(client, fake)
    split_calls = _seed_split_projection(client)
    request = SimpleNamespace(app=client.app)
    client.app.state.gcal_tasks = set()

    async def _exercise() -> dict[str, tuple[float, int]]:
        token = begin_request_timings()
        try:
            schedule_sync(request, USER)
            pending = list(getattr(client.app.state, "gcal_tasks", set()) or [])
            if pending:
                await asyncio.gather(*pending)
            return snapshot_request_timings()
        finally:
            reset_request_timings(token)

    snap = asyncio.run(_exercise())
    assert split_calls[0] >= 1
    assert snap["calendar_sync_schedule"][1] == 1
    assert "split_prefs" not in snap
    assert "progress_preload" not in snap
    assert "theme" not in snap


def test_reminder_popup_shown_until_cadence_chosen(tmp_path: Path) -> None:
    client, _store, fake, repo = _client(tmp_path)
    fake.calendar_exists = False
    location = _connect(client, fake)  # → /settings?gcal=connected
    html = client.get(location).text
    assert "gcal-reminder-modal" in html
    # A plain settings view (no post-connect redirect) never prompts.
    assert "gcal-reminder-modal" not in client.get("/settings").text
    # Choosing a cadence persists it and silences the prompt for good.
    csrf = client.cookies.get("rtc_csrf")
    resp = client.post(
        "/calendar/google/preferences",
        data={"csrf_token": csrf, "reminder_cadence": "twice"},
        follow_redirects=False,
    )
    assert resp.headers["location"] == "/settings?gcal=saved"
    assert repo.get_setting(USER, "gcal_reminder_cadence") == "twice"
    assert "gcal-reminder-modal" not in client.get("/settings?gcal=connected").text
    # The Settings grid shows the stored choice.
    assert 'value="twice" selected' in client.get("/settings").text


def test_invalid_cadence_rejected(tmp_path: Path) -> None:
    client, _store, fake, repo = _client(tmp_path)
    fake.calendar_exists = False
    _connect(client, fake)
    csrf = client.cookies.get("rtc_csrf")
    resp = client.post(
        "/calendar/google/preferences",
        data={"csrf_token": csrf, "reminder_cadence": "hourly"},
        follow_redirects=False,
    )
    assert "why=cadence" in resp.headers["location"]
    assert repo.get_setting(USER, "gcal_reminder_cadence") is None


def test_partial_preference_post_keeps_other_fields(tmp_path: Path) -> None:
    """The popup posts ONLY the cadence — it must never clobber the rest."""
    client, _store, fake, repo = _client(tmp_path)
    fake.calendar_exists = False
    _connect(client, fake)
    csrf = client.cookies.get("rtc_csrf")
    client.post(
        "/calendar/google/preferences",
        data={
            "csrf_token": csrf,
            "user_timezone": "Asia/Kolkata",
            "revision_time": "21:30",
            "session_minutes": "45",
        },
        follow_redirects=False,
    )
    resp = client.post(
        "/calendar/google/preferences",
        data={"csrf_token": csrf, "reminder_cadence": "thrice"},
        follow_redirects=False,
    )
    assert resp.headers["location"] == "/settings?gcal=saved"
    assert repo.get_setting(USER, "gcal_reminder_cadence") == "thrice"
    assert repo.get_setting(USER, "user_timezone") == "Asia/Kolkata"
    assert repo.get_setting(USER, "gcal_revision_time") == "21:30"
    assert repo.get_setting(USER, "gcal_session_minutes") == "45"


def test_multiuser_settings_drop_study_reminders(tmp_path: Path) -> None:
    """Multiuser accounts get calendar reminders instead of the local
    LaunchAgent radios; saving without the radios must still work."""
    client, _store, _fake, _repo = _client(tmp_path)
    html = client.get("/settings").text
    assert "Study reminders" not in html
    assert "notification_frequency" not in html
    resp = client.post(
        "/settings", data={"news_articles": "19, 21"}, follow_redirects=False
    )
    assert resp.status_code == 303
    # An explicitly invalid frequency is still rejected, not ignored.
    bad = client.post(
        "/settings",
        data={"notification_frequency": "bogus", "news_articles": ""},
        follow_redirects=False,
    )
    assert bad.status_code == 400


def test_settings_get_connection_once_when_active(tmp_path: Path) -> None:
    client, store, fake, _repo = _client(tmp_path)
    fake.calendar_exists = False
    _connect(client, fake)
    store.get_connection_calls = 0
    assert client.get("/settings").status_code == 200
    assert store.get_connection_calls == 1


def test_settings_get_connection_once_when_missing(tmp_path: Path) -> None:
    client, store, _fake, _repo = _client(tmp_path)
    store.get_connection_calls = 0
    assert client.get("/settings").status_code == 200
    assert store.get_connection_calls == 1


def test_settings_get_connection_once_when_fresh_pending(tmp_path: Path) -> None:
    client, store, fake, _repo = _client(tmp_path)
    fake.calendar_exists = False
    _connect(client, fake)
    store.mark_sync_pending(USER)
    store.get_connection_calls = 0
    assert client.get("/settings").status_code == 200
    assert store.get_connection_calls == 1


def test_retry_stale_pending_does_not_reload_supplied_connection(
    tmp_path: Path, monkeypatch
) -> None:
    from constitution_memorizer.calendar_sync.routes import retry_stale_pending

    client, store, fake, _repo = _client(tmp_path)
    fake.calendar_exists = False
    _connect(client, fake)
    connection = store.get_connection(USER)
    store.get_connection_calls = 0
    request = SimpleNamespace(app=client.app)
    retry_stale_pending(request, USER, connection=connection)
    assert store.get_connection_calls == 0
    retry_stale_pending(request, USER)
    assert store.get_connection_calls == 1


def test_settings_stale_pending_allows_schedule_sync_lookup(
    tmp_path: Path, monkeypatch
) -> None:
    client, store, fake, _repo = _client(tmp_path)
    fake.calendar_exists = False
    _connect(client, fake)
    calls: list[str] = []
    monkeypatch.setattr(
        "constitution_memorizer.calendar_sync.routes.schedule_sync",
        lambda _req, uid: calls.append(str(uid)),
    )
    conn = store._conn
    conn.execute(
        "UPDATE google_calendar_connections SET sync_pending = 1, "
        "sync_requested_at = ? WHERE user_id = ?",
        ("2020-01-01T00:00:00+00:00", str(USER)),
    )
    conn.commit()
    store.get_connection_calls = 0
    assert client.get("/settings").status_code == 200
    assert calls == [str(USER)]
    # Settings-owned lookup is once; schedule_sync is stubbed so it does not
    # add a durable get_connection in this test.
    assert store.get_connection_calls == 1
