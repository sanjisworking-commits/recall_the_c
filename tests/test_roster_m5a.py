"""Milestone 5A: monthly Playground roster (period, capacity, same-month)."""

from __future__ import annotations

import inspect
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from alembic.config import Config
from alembic.script import ScriptDirectory

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import InMemorySessionStore
from constitution_memorizer.entitlements.models import CONSTITUTION_ACCESS_FULL, EntitlementSnapshot
from constitution_memorizer.multiuser.settings import MultiUserSettings
from constitution_memorizer.playground.db import ensure_sqlite_schema as ensure_overlay_schema
from constitution_memorizer.playground.eligibility import is_playground_eligible_law
from constitution_memorizer.playground.roster.db import ensure_sqlite_schema as ensure_roster_schema
from constitution_memorizer.playground.roster.models import (
    RESULT_ALREADY_ACTIVE,
    RESULT_INELIGIBLE,
    RESULT_NEW_BLOCKED,
    RESULT_OK,
    RESULT_RE_ADDED,
    RESULT_ROSTER_FULL,
)
from constitution_memorizer.playground.roster.period import (
    PLAYGROUND_TZ,
    date_in_period,
    playground_month_bounds,
    playground_month_name,
)
from constitution_memorizer.playground.roster.postgres import PostgresRosterRepository
from constitution_memorizer.playground.roster.repository import SqliteRosterRepository
from constitution_memorizer.playground.roster.service import RosterService
from constitution_memorizer.playground.service import activate_law, selection_rows
from constitution_memorizer.playground.source import source_hash
from constitution_memorizer.playground.urls import (
    add_path,
    law_path,
    learn_complete_path,
    learn_path,
    roster_path,
    sections_path,
)
from constitution_memorizer.progress.db import open_progress_db
from constitution_memorizer.progress.repository import ProgressRepository
from constitution_memorizer.progress.user_ids import LOCAL_USER_ID
from constitution_memorizer.web import bare_acts
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.bare_acts import clear_bare_act_cache, get_bare_act

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
USER = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
NOW = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[1]
HMAC_SECRET = "m5a-test-hmac-secret"


def _snap(
    *,
    tier: str | None = "plus",
    limit: int | None = 10,
    admin: bool = False,
    consume: bool = True,
    billing_start: datetime | None = None,
    billing_end: datetime | None = None,
) -> EntitlementSnapshot:
    return EntitlementSnapshot(
        is_authenticated=True,
        subscription_status="active",
        tier=None if admin else tier,
        is_subscribed=not admin,
        admin_override=admin,
        can_use_constitution_learn=True,
        constitution_access=CONSTITUTION_ACCESS_FULL,
        can_read_laws=True,
        can_open_playground=True,
        can_consume_new_playground_law=consume,
        playground_law_limit=None if admin else limit,
        playground_block_reason=None,
        billing_period_start=billing_start,
        billing_period_end=billing_end,
        legacy_status=None,
    )


def _roster(tmp_path: Path) -> tuple[RosterService, sqlite3.Connection]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(tmp_path / "roster.db"), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout = 8000")
    ensure_overlay_schema(conn)
    ensure_roster_schema(conn)
    return RosterService(SqliteRosterRepository(conn)), conn


def _allow_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    from constitution_memorizer.playground.roster import service as roster_service

    real = roster_service.is_playground_eligible_law

    def wrapped(law_id: str) -> bool:
        if str(law_id).startswith("stub-"):
            return True
        return real(law_id)

    monkeypatch.setattr(roster_service, "is_playground_eligible_law", wrapped)


def _mu_settings() -> MultiUserSettings:
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
        PLAYGROUND_DEVICE_HMAC_SECRET=HMAC_SECRET,
        PLAYGROUND_DEVICE_LIMIT="2",
    )


def _authed_client(tmp_path: Path) -> TestClient:
    tmp_path.mkdir(parents=True, exist_ok=True)
    conn = open_progress_db(tmp_path / "progress.db")
    provider = FakeAuthProvider()
    provider.seed_google_user(
        user_id=USER, email="m5a@example.com", display_name="M5A"
    )
    client = TestClient(
        create_app(
            units_path=MINI_UNITS,
            db_path=tmp_path / "unused.db",
            multiuser=True,
            multiuser_settings=_mu_settings(),
            auth_provider=provider,
            session_store=InMemorySessionStore(),
            progress_repo=ProgressRepository(conn),
        )
    )
    start = client.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state")
    client.get(
        f"/auth/callback?code=fake-google-code&state={state}",
        follow_redirects=False,
    )
    return client


def _csrf(client: TestClient) -> dict[str, str]:
    token = client.cookies.get("rtc_csrf") or ""
    return {"csrf_token": token} if token else {}


def _subscribe(
    client: TestClient,
    *,
    tier: str = "plus",
    status: str = "active",
    start: datetime | None = None,
    end: datetime | None = None,
):
    return client.app.state.subscriptions.create_subscription_record(
        USER,
        tier=tier,
        status=status,
        billing_period_start=start or datetime(2026, 9, 15, tzinfo=timezone.utc),
        billing_period_end=end or datetime(2026, 10, 15, tzinfo=timezone.utc),
        is_current=True,
    )


def _confirm_add(client: TestClient, law_id: str):
    payload = dict(_csrf(client))
    payload["confirm"] = "add"
    preview = client.post(add_path(law_id), data=_csrf(client), follow_redirects=False)
    if preview.status_code == 303 and "/playground/roster" in (
        preview.headers.get("location") or ""
    ):
        return client.post(add_path(law_id), data=payload, follow_redirects=False)
    return preview


def _hydrate_spy(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    hydrated: list[str] = []
    real = bare_acts._load_cached

    def wrapped(slug: str, identity: str):
        hydrated.append(slug)
        return real(slug, identity)

    wrapped.cache_clear = real.cache_clear  # type: ignore[attr-defined]
    monkeypatch.setattr(bare_acts, "_load_cached", wrapped)
    return hydrated


def _seed_overlay(client: TestClient, law_id: str, number: str = "1") -> None:
    playground = client.app.state.playground
    activate_law(playground, USER, law_id)
    act = get_bare_act(law_id)
    assert act is not None
    playground.replace_selection(
        USER, law_id, selection_rows(law_id, [number], entire=False, act=act)
    )
    loc = f"{law_id}:section:{number}"
    section = act.section(number)
    assert section is not None
    playground.complete_cloze(
        USER,
        law_id,
        loc,
        source_version="1",
        source_hash=source_hash(section),
        as_of=NOW.date(),
        live_hash=source_hash(section),
    )


def test_september_and_october_bounds_are_exclusive():
    start, end = playground_month_bounds(datetime(2026, 9, 16, 12, tzinfo=timezone.utc))
    assert start == date(2026, 9, 1)
    assert end == date(2026, 10, 1)
    assert date_in_period(date(2026, 9, 1), start, end)
    assert date_in_period(date(2026, 9, 30), start, end)
    assert not date_in_period(date(2026, 10, 1), start, end)
    oct_start, oct_end = playground_month_bounds(
        datetime(2026, 10, 1, 0, 0, tzinfo=PLAYGROUND_TZ)
    )
    assert oct_start == date(2026, 10, 1)
    assert oct_end == date(2026, 11, 1)


def test_december_january_year_boundary():
    dec = playground_month_bounds(datetime(2026, 12, 31, 18, 29, tzinfo=timezone.utc))
    jan = playground_month_bounds(datetime(2026, 12, 31, 18, 30, tzinfo=timezone.utc))
    assert dec == (date(2026, 12, 1), date(2027, 1, 1))
    assert jan == (date(2027, 1, 1), date(2027, 2, 1))


def test_utc_ist_boundary_is_not_utc_month():
    still_september = playground_month_bounds(
        datetime(2026, 9, 30, 18, 29, tzinfo=timezone.utc)
    )
    october = playground_month_bounds(
        datetime(2026, 9, 30, 18, 30, tzinfo=timezone.utc)
    )
    assert still_september[0] == date(2026, 9, 1)
    assert october[0] == date(2026, 10, 1)
    assert playground_month_name(still_september[0]) == "September"
    assert playground_month_name(october[0]) == "October"


def test_billing_period_does_not_change_roster_month(tmp_path: Path):
    service, _conn = _roster(tmp_path)
    snap = _snap(
        billing_start=datetime(2026, 9, 15, tzinfo=timezone.utc),
        billing_end=datetime(2026, 10, 15, tzinfo=timezone.utc),
    )
    sept = service.ensure_current_period(
        USER, snap, now=datetime(2026, 9, 20, tzinfo=timezone.utc)
    )
    oct_ = service.ensure_current_period(
        USER, snap, now=datetime(2026, 10, 2, tzinfo=timezone.utc)
    )
    assert sept.period_start == date(2026, 9, 1)
    assert sept.period_end == date(2026, 10, 1)
    assert oct_.period_start == date(2026, 10, 1)
    assert oct_.period_end == date(2026, 11, 1)
    stored_sept = service._repo.get_period(USER, date(2026, 9, 1))
    assert stored_sept is not None
    assert stored_sept.status == "closed"
    assert oct_.status == "active"


def test_annual_billing_span_still_opens_monthly_periods(tmp_path: Path):
    service, _conn = _roster(tmp_path)
    snap = _snap(
        billing_start=datetime(2026, 1, 15, tzinfo=timezone.utc),
        billing_end=datetime(2027, 1, 15, tzinfo=timezone.utc),
    )
    months = []
    for month in (9, 10, 11):
        period = service.ensure_current_period(
            USER, snap, now=datetime(2026, month, 10, tzinfo=timezone.utc)
        )
        months.append(period.period_start)
    assert months == [date(2026, 9, 1), date(2026, 10, 1), date(2026, 11, 1)]
    assert len({row.id for row in service._repo.list_periods(USER)}) == 3


def test_one_period_per_user_month_and_same_law_next_month(tmp_path: Path, monkeypatch):
    _allow_stubs(monkeypatch)
    service, conn = _roster(tmp_path)
    snap = _snap()
    sept = datetime(2026, 9, 10, tzinfo=timezone.utc)
    oct_ = datetime(2026, 10, 10, tzinfo=timezone.utc)
    service.ensure_current_period(USER, snap, now=sept)
    first = service.confirm_add_law(USER, "stub-1", snap, now=sept)
    second = service.confirm_add_law(USER, "stub-1", snap, now=sept)
    assert first.status == RESULT_OK
    assert second.status == RESULT_ALREADY_ACTIVE
    assert first.used == 1
    later = service.confirm_add_law(USER, "stub-1", snap, now=oct_)
    assert later.status == RESULT_OK
    rows = conn.execute(
        "SELECT period_start, law_id FROM user_playground_roster_item ORDER BY period_start"
    ).fetchall()
    assert [row["period_start"] for row in rows] == ["2026-09-01", "2026-10-01"]
    periods = conn.execute(
        "SELECT period_start FROM user_playground_period ORDER BY period_start"
    ).fetchall()
    assert [row["period_start"] for row in periods] == ["2026-09-01", "2026-10-01"]


def test_ineligible_and_constitution_never_consume(tmp_path: Path):
    service, conn = _roster(tmp_path)
    snap = _snap()
    for law_id in ("article-14", "uapa-1967", "ipc"):
        result = service.confirm_add_law(USER, law_id, snap, now=NOW)
        assert result.status == RESULT_INELIGIBLE
    assert conn.execute("SELECT COUNT(*) AS n FROM user_playground_roster_item").fetchone()[
        "n"
    ] == 0
    assert is_playground_eligible_law("ndps") is True


def test_plus_pro_max_and_admin_capacity(tmp_path: Path, monkeypatch):
    _allow_stubs(monkeypatch)
    service, _conn = _roster(tmp_path)
    plus = _snap(tier="plus", limit=10)
    for i in range(10):
        assert service.confirm_add_law(USER, f"stub-{i}", plus, now=NOW).ok
    blocked = service.confirm_add_law(USER, "stub-10", plus, now=NOW)
    assert blocked.status == RESULT_ROSTER_FULL
    assert blocked.used == 10
    assert blocked.remaining == 0

    pro_user = UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee")
    pro = _snap(tier="pro", limit=30)
    for i in range(30):
        assert service.confirm_add_law(pro_user, f"stub-{i}", pro, now=NOW).ok
    assert service.confirm_add_law(pro_user, "stub-30", pro, now=NOW).status == RESULT_ROSTER_FULL

    max_user = UUID("ffffffff-ffff-4fff-8fff-ffffffffffff")
    max_snap = _snap(tier="max", limit=None)
    for i in range(31):
        result = service.confirm_add_law(max_user, f"stub-{i}", max_snap, now=NOW)
        assert result.ok
        assert result.remaining is None
    cap = service.capacity(max_user, max_snap, now=NOW)
    assert cap.law_limit is None
    assert cap.used == 31
    assert cap.remaining is None

    admin = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
    admin_snap = _snap(admin=True)
    period = service.ensure_current_period(admin, admin_snap, now=NOW)
    assert period.tier_snapshot is None
    assert period.law_limit is None
    assert service.confirm_add_law(admin, "stub-0", admin_snap, now=NOW).ok


def test_remove_does_not_refund_and_readd_is_free(tmp_path: Path, monkeypatch):
    _allow_stubs(monkeypatch)
    service, _conn = _roster(tmp_path)
    snap = _snap()
    for i in range(10):
        service.confirm_add_law(USER, f"stub-{i}", snap, now=NOW)
    service.remove_law_this_period(USER, "stub-0", snap, now=NOW)
    cap = service.capacity(USER, snap, now=NOW)
    assert cap.used == 10
    assert cap.remaining == 0
    assert service.is_law_active_this_period(USER, "stub-0", now=NOW) is False
    readd = service.readd_law_this_period(USER, "stub-0", snap, now=NOW)
    assert readd.status == RESULT_RE_ADDED
    assert readd.used == 10
    assert service.is_law_active_this_period(USER, "stub-0", now=NOW) is True
    other = service.confirm_add_law(USER, "stub-new", snap, now=NOW)
    assert other.status == RESULT_ROSTER_FULL


def test_pending_blocks_new_but_allows_current_readd(tmp_path: Path, monkeypatch):
    _allow_stubs(monkeypatch)
    service, _conn = _roster(tmp_path)
    active = _snap(consume=True)
    service.confirm_add_law(USER, "stub-1", active, now=NOW)
    service.remove_law_this_period(USER, "stub-1", active, now=NOW)
    pending = _snap(consume=False)
    readd = service.confirm_add_law(
        USER, "stub-1", pending, now=NOW, can_consume_new_law=False
    )
    assert readd.status == RESULT_RE_ADDED
    blocked = service.confirm_add_law(
        USER, "stub-2", pending, now=NOW, can_consume_new_law=False
    )
    assert blocked.status == RESULT_NEW_BLOCKED


def test_upgrade_and_downgrade_reconcile_limit(tmp_path: Path, monkeypatch):
    _allow_stubs(monkeypatch)
    service, _conn = _roster(tmp_path)
    plus = _snap(tier="plus", limit=10)
    for i in range(10):
        service.confirm_add_law(USER, f"stub-{i}", plus, now=NOW)
    pro = _snap(tier="pro", limit=30)
    period = service.ensure_current_period(USER, pro, now=NOW)
    assert period.law_limit == 30
    assert service.confirm_add_law(USER, "stub-extra", pro, now=NOW).ok
    down = _snap(tier="plus", limit=10)
    lowered = service.ensure_current_period(USER, down, now=NOW)
    assert lowered.law_limit == 10
    cap = service.capacity(USER, down, now=NOW)
    assert cap.used == 11
    assert cap.remaining == 0
    assert service.is_law_active_this_period(USER, "stub-0", now=NOW) is True
    assert service.confirm_add_law(USER, "stub-more", down, now=NOW).status == RESULT_ROSTER_FULL


def test_concurrent_finite_cap_one_roster_full(tmp_path: Path, monkeypatch):
    _allow_stubs(monkeypatch)
    path = tmp_path / "race.db"
    setup = sqlite3.connect(str(path), check_same_thread=False)
    setup.row_factory = sqlite3.Row
    setup.execute("PRAGMA journal_mode=WAL")
    setup.execute("PRAGMA busy_timeout = 8000")
    ensure_overlay_schema(setup)
    ensure_roster_schema(setup)
    seed = RosterService(SqliteRosterRepository(setup))
    snap = _snap()
    seed.ensure_current_period(USER, snap, now=NOW)
    for i in range(9):
        assert seed.confirm_add_law(USER, f"stub-{i}", snap, now=NOW).ok

    results: list = []

    def worker(law_id: str) -> None:
        conn = sqlite3.connect(str(path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 8000")
        service = RosterService(SqliteRosterRepository(conn))
        results.append(service.confirm_add_law(USER, law_id, snap, now=NOW))

    with ThreadPoolExecutor(max_workers=2) as pool:
        futs = [pool.submit(worker, "stub-x"), pool.submit(worker, "stub-y")]
        for fut in futs:
            fut.result(timeout=10)
    statuses = sorted(row.status for row in results)
    assert RESULT_OK in statuses
    assert RESULT_ROSTER_FULL in statuses
    final = sqlite3.connect(str(path))
    final.row_factory = sqlite3.Row
    count = final.execute(
        """
        SELECT COUNT(DISTINCT law_id) AS n FROM user_playground_roster_item
        WHERE consumed_at IS NOT NULL
        """
    ).fetchone()["n"]
    assert count == 10


def test_concurrent_same_law_is_one_row(tmp_path: Path, monkeypatch):
    _allow_stubs(monkeypatch)
    path = tmp_path / "same.db"
    setup = sqlite3.connect(str(path), check_same_thread=False)
    setup.row_factory = sqlite3.Row
    setup.execute("PRAGMA journal_mode=WAL")
    setup.execute("PRAGMA busy_timeout = 8000")
    ensure_overlay_schema(setup)
    ensure_roster_schema(setup)
    seed = RosterService(SqliteRosterRepository(setup))
    snap = _snap()
    seed.ensure_current_period(USER, snap, now=NOW)
    results: list = []

    def worker() -> None:
        conn = sqlite3.connect(str(path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 8000")
        service = RosterService(SqliteRosterRepository(conn))
        results.append(service.confirm_add_law(USER, "ndps", snap, now=NOW))

    with ThreadPoolExecutor(max_workers=2) as pool:
        futs = [pool.submit(worker), pool.submit(worker)]
        for fut in futs:
            fut.result(timeout=10)
    assert all(row.ok for row in results)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT law_id FROM user_playground_roster_item").fetchall()
    assert [row["law_id"] for row in rows] == ["ndps"]


def test_postgres_consume_locks_period_row():
    source = inspect.getsource(PostgresRosterRepository)
    assert "FOR UPDATE" in source
    assert "COUNT(DISTINCT law_id)" in source
    sqlite_src = inspect.getsource(SqliteRosterRepository)
    assert "BEGIN IMMEDIATE" in inspect.getsource(SqliteRosterRepository._exclusive)
    assert "COUNT(DISTINCT law_id)" in sqlite_src


def test_alembic_head_and_rls():
    cfg = Config(str(ROOT / "alembic.ini"))
    heads = ScriptDirectory.from_config(cfg).get_heads()
    assert heads == ["20260925_0026"]
    text = (
        ROOT / "alembic" / "versions" / "20260917_0024_playground_roster.py"
    ).read_text(encoding="utf-8")
    assert "user_playground_period" in text
    assert "user_playground_roster_item" in text
    assert "UNIQUE (user_id, period_start, law_id)" in text
    assert "UNIQUE (user_id, period_start)" in text
    assert "ENABLE ROW LEVEL SECURITY" in text
    assert "user_playground_law_entitlement" not in text
    sqlite_mod = __import__(
        "constitution_memorizer.playground.roster.db", fromlist=["SCHEMA_SQL"]
    )
    assert "UNIQUE (user_id, period_start, law_id)" in sqlite_mod.SCHEMA_SQL


def test_confirm_add_consume_and_skip_second_slot(tmp_path: Path):
    client = _authed_client(tmp_path)
    _subscribe(client)
    preview = client.post(add_path("ndps"), data=_csrf(client), follow_redirects=False)
    assert preview.status_code == 303
    assert preview.headers["location"] == roster_path(add="ndps")
    assert client.app.state.playground.get_item(USER, "ndps") is None
    page = client.get(roster_path(add="ndps"))
    assert page.status_code == 200
    assert "This will use 1 of your 10 law spaces for September." in page.text
    added = _confirm_add(client, "ndps")
    assert added.status_code == 303
    assert added.headers["location"] == sections_path("ndps")
    again = client.post(add_path("ndps"), data=_csrf(client), follow_redirects=False)
    assert again.headers["location"] == sections_path("ndps")
    cap = client.app.state.roster.capacity(
        USER, client.app.state.entitlement_service.resolve(USER, now=NOW), now=NOW
    )
    assert cap.used == 1


def test_two_devices_share_account_roster(tmp_path: Path):
    first = _authed_client(tmp_path)
    _subscribe(first)
    app = first.app
    second = TestClient(app)
    start = second.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state")
    second.get(
        f"/auth/callback?code=fake-google-code&state={state}",
        follow_redirects=False,
    )
    first.get("/playground")
    second.get("/playground")
    added = _confirm_add(first, "ndps")
    assert added.status_code == 303
    home_b = second.get("/playground")
    assert "Narcotic" in home_b.text
    cap_a = app.state.roster.capacity(
        USER, app.state.entitlement_service.resolve(USER, now=NOW), now=NOW
    )
    cap_b = app.state.roster.capacity(
        USER, app.state.entitlement_service.resolve(USER, now=NOW), now=NOW
    )
    assert cap_a.used == cap_b.used == 1
    items = app.state.roster.active_roster_items(USER, now=NOW)
    assert [row.law_id for row in items] == ["ndps"]


def test_remove_readd_progress_and_full_gate(tmp_path: Path):
    client = _authed_client(tmp_path)
    _subscribe(client)
    _confirm_add(client, "ndps")
    client.post(
        sections_path("ndps"),
        data={**_csrf(client), "section": "1"},
        follow_redirects=False,
    )
    client.post(learn_complete_path("ndps", "1"), data=_csrf(client))
    overlay = client.app.state.playground
    before_item = overlay.get_item(USER, "ndps")
    before_sel = overlay.list_selection(USER, "ndps")
    before_prog = overlay.list_progress(USER, "ndps")
    roster = client.app.state.roster
    snap = client.app.state.entitlement_service.resolve(USER, now=NOW)
    for law_id in ("bns", "bnss"):
        roster.confirm_add_law(USER, law_id, snap, now=NOW)
    from constitution_memorizer.playground.roster import service as roster_service

    real = roster_service.is_playground_eligible_law

    def wrapped(law_id: str) -> bool:
        if str(law_id).startswith("stub-"):
            return True
        return real(law_id)

    roster_service.is_playground_eligible_law = wrapped  # type: ignore[method-assign]
    try:
        for i in range(7):
            roster.confirm_add_law(USER, f"stub-{i}", snap, now=NOW)
    finally:
        roster_service.is_playground_eligible_law = real  # type: ignore[method-assign]
    cap = roster.capacity(USER, snap, now=NOW)
    assert cap.used == 10
    removed = client.post(
        "/playground/roster/ndps/remove",
        data=_csrf(client),
        follow_redirects=False,
    )
    assert removed.status_code == 303
    assert roster.capacity(USER, snap, now=NOW).used == 10
    assert roster.is_law_active_this_period(USER, "ndps", now=NOW) is False
    assert overlay.get_item(USER, "ndps") == before_item
    assert overlay.list_selection(USER, "ndps") == before_sel
    assert [
        (row.source_locator, row.times_completed) for row in overlay.list_progress(USER, "ndps")
    ] == [(row.source_locator, row.times_completed) for row in before_prog]
    blocked = client.get(learn_path("ndps", "1"))
    assert "Progress saved" in blocked.text or "Add to this month" in blocked.text
    readd = _confirm_add(client, "ndps")
    assert readd.status_code == 303
    assert roster.is_law_active_this_period(USER, "ndps", now=NOW) is True
    learn = client.get(learn_path("ndps", "1"))
    assert learn.status_code == 200
    assert roster.capacity(USER, snap, now=NOW).used == 10


def test_historical_overlay_is_not_learnable_until_roster(tmp_path: Path, monkeypatch):
    client = _authed_client(tmp_path)
    _subscribe(client)
    _seed_overlay(client, "ndps")
    clear_bare_act_cache()
    hydrated = _hydrate_spy(monkeypatch)
    blocked = client.get(learn_path("ndps", "1"))
    assert "ndps" not in hydrated
    assert "Progress saved" in blocked.text
    _confirm_add(client, "ndps")
    hydrated.clear()
    allowed = client.get(learn_path("ndps", "1"))
    assert allowed.status_code == 200
    assert "ndps" in hydrated
    client.post(
        "/playground/roster/ndps/remove",
        data=_csrf(client),
        follow_redirects=False,
    )
    hydrated.clear()
    again = client.get(learn_path("ndps", "1"))
    assert "ndps" not in hydrated
    assert "Progress saved" in again.text
    assert client.app.state.playground.get_item(USER, "ndps") is not None


def test_pending_current_roster_vs_historical(tmp_path: Path):
    client = _authed_client(tmp_path)
    sub = _subscribe(client)
    _confirm_add(client, "ndps")
    client.post(
        sections_path("ndps"),
        data={**_csrf(client), "section": "1"},
        follow_redirects=False,
    )
    _seed_overlay(client, "bns")
    client.app.state.subscriptions.update_subscription_state(
        USER, sub.id, status="pending"
    )
    assert client.get(learn_path("ndps", "1")).status_code == 200
    bns = client.get(learn_path("bns", "1"))
    assert "temporarily unavailable" in bns.text.lower()
    assert client.app.state.roster.is_law_active_this_period(USER, "bns") is False
    client.post(
        "/playground/roster/ndps/remove",
        data=_csrf(client),
        follow_redirects=False,
    )
    readd = _confirm_add(client, "ndps")
    assert readd.status_code == 303
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps") is True
    new_law = client.post(
        add_path("bnss"),
        data={**_csrf(client), "confirm": "add"},
        follow_redirects=False,
    )
    assert new_law.status_code == 303
    assert client.app.state.roster.is_law_active_this_period(USER, "bnss") is False


def test_full_roster_does_not_close_playground(tmp_path: Path):
    client = _authed_client(tmp_path)
    _subscribe(client, tier="plus")
    _confirm_add(client, "ndps")
    client.post(
        sections_path("ndps"),
        data={**_csrf(client), "section": "1"},
        follow_redirects=False,
    )
    roster = client.app.state.roster
    snap = client.app.state.entitlement_service.resolve(USER, now=NOW)
    from constitution_memorizer.playground.roster import service as roster_service

    real = roster_service.is_playground_eligible_law

    def wrapped(law_id: str) -> bool:
        if str(law_id).startswith("stub-"):
            return True
        return real(law_id)

    roster_service.is_playground_eligible_law = wrapped  # type: ignore[method-assign]
    try:
        for i in range(9):
            roster.confirm_add_law(USER, f"stub-{i}", snap, now=NOW)
    finally:
        roster_service.is_playground_eligible_law = real  # type: ignore[method-assign]
    home = client.get("/playground")
    assert home.status_code == 200
    assert "My Playground" in home.text
    assert client.get(law_path("ndps")).status_code == 200
    assert client.get(learn_path("ndps", "1")).status_code == 200
    done = client.post(learn_complete_path("ndps", "1"), data=_csrf(client))
    assert done.status_code == 200
    assert done.json()["ok"] is True
    blocked = _confirm_add(client, "bns")
    location = blocked.headers.get("location", roster_path(add="bns"))
    follow = client.get(location)
    assert "Playground full" in follow.text or "roster_full" in follow.text
    snap2 = client.app.state.entitlement_service.resolve(USER, now=NOW)
    assert snap2.can_open_playground is True


def test_zero_hydration_home_roster_preview_and_blocked(tmp_path: Path, monkeypatch):
    client = _authed_client(tmp_path)
    _subscribe(client)
    _seed_overlay(client, "ndps")
    clear_bare_act_cache()
    hydrated = _hydrate_spy(monkeypatch)
    client.get("/playground")
    client.get("/playground/roster")
    client.get(roster_path(add="bns"))
    client.get(learn_path("ndps", "1"))
    client.post(add_path("bns"), data=_csrf(client), follow_redirects=False)
    assert hydrated == []
    _confirm_add(client, "ndps")
    hydrated.clear()
    workspace = client.get(law_path("ndps"))
    assert workspace.status_code == 200
    assert "ndps" in hydrated
    assert "bns" not in hydrated
    assert "bnss" not in hydrated


def test_max_confirm_copy_has_no_denominator(tmp_path: Path):
    client = _authed_client(tmp_path)
    _subscribe(client, tier="max")
    page = client.get(roster_path(add="ndps"))
    assert "Add NDPS Act to September Playground?" in page.text or "Add this law to your September Playground?" in page.text
    assert "1 of your" not in page.text


def test_local_owner_uses_roster_not_overlay_alone(tmp_path: Path):
    client = TestClient(create_app(units_path=MINI_UNITS, db_path=tmp_path / "p.db"))
    preview = client.post(add_path("ndps"), follow_redirects=False)
    assert "/playground/roster" in (preview.headers.get("location") or "")
    assert client.app.state.playground.get_item(LOCAL_USER_ID, "ndps") is None
    confirmed = client.post(
        add_path("ndps"), data={"confirm": "add"}, follow_redirects=False
    )
    assert confirmed.status_code == 303
    assert client.app.state.roster.is_law_active_this_period(LOCAL_USER_ID, "ndps")
    cap = client.app.state.roster.capacity(LOCAL_USER_ID, None, local_owner=True)
    assert cap.law_limit is None
    assert cap.remaining is None


def test_roster_next_get_does_not_consume(tmp_path: Path):
    client = _authed_client(tmp_path)
    _subscribe(client)
    _confirm_add(client, "ndps")
    before = client.app.state.roster.capacity(
        USER, client.app.state.entitlement_service.resolve(USER, now=NOW), now=NOW
    ).used
    page = client.get("/playground/roster/next")
    assert page.status_code == 200
    assert "Playground" in page.text
    after = client.app.state.roster.capacity(
        USER, client.app.state.entitlement_service.resolve(USER, now=NOW), now=NOW
    ).used
    assert after == before


def test_no_lifetime_entitlement_table():
    versions = ROOT / "alembic" / "versions"
    blob = "\n".join(path.read_text(encoding="utf-8") for path in versions.glob("*.py"))
    assert "user_playground_law_entitlement" not in blob
