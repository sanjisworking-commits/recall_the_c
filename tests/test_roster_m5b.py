"""Milestone 5B: carry-forward rollover and later-month historical reactivation."""

from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from alembic.config import Config
from alembic.script import ScriptDirectory

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import InMemorySessionStore
from constitution_memorizer.entitlements.models import CONSTITUTION_ACCESS_FULL, EntitlementSnapshot
from constitution_memorizer.multiuser.settings import MultiUserSettings
from constitution_memorizer.playground.db import ensure_sqlite_schema as ensure_overlay_schema
from constitution_memorizer.playground.repository import SqlitePlaygroundRepository
from constitution_memorizer.playground.roster.db import ensure_sqlite_schema as ensure_roster_schema
from constitution_memorizer.playground.roster.models import (
    ORIGIN_CARRY_FORWARD,
    ORIGIN_NEW,
    ORIGIN_RE_ADD,
    PERIOD_STATUS_ACTIVE,
    PERIOD_STATUS_CLOSED,
    PERIOD_STATUS_DRAFT,
    RESULT_INVALID_CANDIDATE,
    RESULT_NEW_BLOCKED,
    RESULT_OK,
    RESULT_ROSTER_FULL,
)
from constitution_memorizer.playground.roster.period import (
    next_playground_month_bounds,
    playground_month_bounds,
    previous_playground_month_bounds,
    shift_playground_month,
)
from constitution_memorizer.playground.roster.postgres import PostgresRosterRepository
from constitution_memorizer.playground.roster.repository import SqliteRosterRepository
from constitution_memorizer.playground.roster.service import RosterService
from constitution_memorizer.playground import routes as playground_routes
from constitution_memorizer.playground.roster import service as roster_service
from constitution_memorizer.playground.urls import learn_path, roster_next_path
from constitution_memorizer.progress.db import open_progress_db
from constitution_memorizer.progress.repository import ProgressRepository
from constitution_memorizer.progress.user_ids import as_user_id
from constitution_memorizer.web import bare_acts
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.bare_acts import clear_bare_act_cache

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
USER = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
OTHER = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
HMAC_SECRET = "m5b-test-hmac-secret"
SEP_25 = datetime(2026, 9, 25, 6, 30, tzinfo=timezone.utc)
OCT_1 = datetime(2026, 9, 30, 18, 30, tzinfo=timezone.utc)
NOV_1 = datetime(2026, 10, 31, 18, 30, tzinfo=timezone.utc)
ANNUAL_START = datetime(2026, 1, 15, tzinfo=timezone.utc)
ANNUAL_END = datetime(2027, 1, 15, tzinfo=timezone.utc)


def test_month_shift_handles_year_and_month_lengths():
    assert shift_playground_month(datetime(2026, 1, 1).date(), -1).isoformat() == "2025-12-01"
    assert shift_playground_month(datetime(2026, 12, 1).date(), 1).isoformat() == "2027-01-01"
    prev, prev_end = previous_playground_month_bounds(SEP_25)
    assert (prev.isoformat(), prev_end.isoformat()) == ("2026-08-01", "2026-09-01")
    nxt, nxt_end = next_playground_month_bounds(SEP_25)
    assert (nxt.isoformat(), nxt_end.isoformat()) == ("2026-10-01", "2026-11-01")
    assert playground_month_bounds(OCT_1)[0].isoformat() == "2026-10-01"


def _snap(
    *,
    tier: str | None = "plus",
    limit: int | None = 10,
    admin: bool = False,
    consume: bool = True,
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
        billing_period_start=ANNUAL_START,
        billing_period_end=ANNUAL_END,
        legacy_status=None,
    )


def _open(tmp_path: Path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(tmp_path / "roster.db"), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    ensure_overlay_schema(conn)
    ensure_roster_schema(conn)
    roster = RosterService(SqliteRosterRepository(conn))
    overlay = SqlitePlaygroundRepository(conn)
    return roster, overlay, conn


def _has(overlay, user, law_id: str) -> bool:
    return overlay.get_item(user, law_id) is not None


def _allow_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    real = roster_service.is_playground_eligible_law

    def wrapped(law_id: str) -> bool:
        if str(law_id).startswith("stub-"):
            return True
        return real(law_id)

    monkeypatch.setattr(roster_service, "is_playground_eligible_law", wrapped)


def _seed_overlay(overlay, user, law_id: str) -> None:
    overlay.add_item(user, law_id, source_version="v1", law_source_hash="hash-v1")


def _consume(roster, overlay, user, snap, law_id: str, when: datetime, *, removed: bool = False) -> None:
    _seed_overlay(overlay, user, law_id)
    roster.confirm_add_law(
        user,
        law_id,
        snap,
        now=when,
        has_historical_overlay=True,
    )
    if removed:
        roster.remove_law_this_period(user, law_id, snap, now=when)


def _fingerprint(overlay, user, law_id: str):
    item = overlay.get_item(user, law_id)
    selection = [
        (row.source_locator, row.source_version, row.source_hash)
        for row in overlay.list_selection(user, law_id)
    ]
    progress = [
        (
            row.source_locator,
            row.status,
            row.cloze_done,
            row.times_completed,
            row.last_completed,
            row.next_revision,
            row.interval_days,
            row.source_version,
            row.source_hash,
        )
        for row in overlay.list_progress(user, law_id)
    ]
    return (
        None if item is None else (item.source_version, item.law_source_hash, item.status),
        tuple(selection),
        tuple(progress),
    )


def _plant_progress(conn, user, law_id: str) -> None:
    uid = as_user_id(user)
    conn.execute(
        """
        INSERT INTO user_playground_progress (
            user_id, law_id, source_locator, status, cloze_done, times_completed,
            last_completed, next_revision, interval_days, source_version,
            source_hash, updated_at
        ) VALUES (?, ?, 'ndps:s:1', 'review', 1, 2, '2026-09-20', '2026-09-27', 7, 'v1', 'hash-v1', '2026-09-20')
        """,
        (uid, law_id),
    )
    conn.commit()


def test_candidates_include_removed_and_skip_overlay_only(tmp_path: Path, monkeypatch):
    _allow_stubs(monkeypatch)
    roster, overlay, conn = _open(tmp_path)
    snap = _snap()
    _consume(roster, overlay, USER, snap, "ndps", SEP_25)
    _consume(roster, overlay, USER, snap, "bns", SEP_25, removed=True)
    _seed_overlay(overlay, USER, "bnss")
    conn.execute(
        """
        INSERT INTO user_playground_roster_item (
            id, user_id, period_start, law_id, origin, carried_from_previous_period,
            consumed_at, removed_at, declined_at, created_at, updated_at
        ) VALUES (?, ?, '2026-09-01', 'not-a-law', 'new', 0, '2026-09-01T00:00:00+00:00',
                  NULL, NULL, '2026-09-01T00:00:00+00:00', '2026-09-01T00:00:00+00:00')
        """,
        (str(uuid4()), as_user_id(USER)),
    )
    conn.commit()
    _seed_overlay(overlay, USER, "not-a-law")
    plan = roster.get_rollover_plan(
        USER, snap, has_overlay=lambda law: _has(overlay, USER, law), now=OCT_1
    )
    found = {row.law_id: row for row in plan.candidates}
    assert set(found) == {"ndps", "bns"}
    assert found["bns"].previously_removed is True
    assert plan.manages_current_period is True
    assert plan.used == 0
    assert plan.month_name == "October"


def test_get_plan_does_not_carry_or_create_a_draft(tmp_path: Path, monkeypatch):
    _allow_stubs(monkeypatch)
    roster, overlay, _conn = _open(tmp_path)
    snap = _snap()
    for i in range(10):
        _consume(roster, overlay, USER, snap, f"stub-{i}", SEP_25)
    before = len(roster._repo.list_periods(USER))
    plan = roster.get_rollover_plan(
        USER, snap, has_overlay=lambda law: _has(overlay, USER, law), now=SEP_25
    )
    assert plan.month_name == "October"
    assert plan.target_status is None
    assert plan.used == 0
    assert len(roster._repo.list_periods(USER)) == before
    october = roster._repo.get_period(USER, plan.target_period_start)
    assert october is None


def test_keep_and_decline_capacity_then_free_spaces(tmp_path: Path, monkeypatch):
    _allow_stubs(monkeypatch)
    roster, overlay, _conn = _open(tmp_path)
    snap = _snap()
    laws = [f"stub-{i}" for i in range(10)]
    for law_id in laws:
        _consume(roster, overlay, USER, snap, law_id, SEP_25)
    kept = laws[:6]
    declined = laws[6:]
    result = roster.confirm_carry_forward(
        USER,
        kept,
        declined,
        snap,
        has_overlay=lambda law: _has(overlay, USER, law),
        now=SEP_25,
    )
    assert result.ok
    assert result.period is not None
    assert result.period.status == PERIOD_STATUS_DRAFT
    assert result.used == 6
    assert result.remaining == 4
    september = roster.get_current_period(USER, now=SEP_25)
    assert september is not None and september.status == PERIOD_STATUS_ACTIVE
    assert roster.is_law_active_this_period(USER, "stub-0", now=SEP_25)
    october_items = {
        item.law_id: item
        for item in roster.get_current_roster(USER, now=OCT_1)
    }
    assert october_items["stub-0"].origin == ORIGIN_CARRY_FORWARD
    assert october_items["stub-0"].carried_from_previous_period is True
    assert october_items["stub-0"].consumed_at is not None
    assert october_items["stub-9"].declined_at is not None
    assert october_items["stub-9"].consumed_at is None
    promoted = roster.activate_due_draft(USER, snap, now=OCT_1)
    assert promoted.status == PERIOD_STATUS_ACTIVE
    closed = roster._repo.get_period(USER, september.period_start)
    assert closed is not None and closed.status == PERIOD_STATUS_CLOSED
    assert roster.is_law_active_this_period(USER, "stub-0", now=OCT_1)
    assert roster.is_law_active_this_period(USER, "stub-9", now=OCT_1) is False
    for i in range(4):
        added = roster.confirm_add_law(
            USER, f"stub-new-{i}", snap, now=OCT_1, has_historical_overlay=False
        )
        assert added.ok
        assert added.item is not None and added.item.origin == ORIGIN_NEW
    blocked = roster.confirm_add_law(USER, "stub-new-4", snap, now=OCT_1)
    assert blocked.status == RESULT_ROSTER_FULL


def test_no_preparation_then_current_month_decisions(tmp_path: Path, monkeypatch):
    _allow_stubs(monkeypatch)
    roster, overlay, _conn = _open(tmp_path)
    snap = _snap()
    _consume(roster, overlay, USER, snap, "ndps", SEP_25)
    opened = roster.ensure_current_period(USER, snap, now=OCT_1)
    assert opened.status == PERIOD_STATUS_ACTIVE
    assert opened.period_start.isoformat() == "2026-10-01"
    assert roster.capacity(USER, snap, now=OCT_1).used == 0
    plan = roster.get_rollover_plan(
        USER, snap, has_overlay=lambda law: _has(overlay, USER, law), now=OCT_1
    )
    assert plan.manages_current_period is True
    assert [row.law_id for row in plan.candidates] == ["ndps"]
    kept = roster.confirm_carry_forward(
        USER,
        ["ndps"],
        [],
        snap,
        has_overlay=lambda law: _has(overlay, USER, law),
        now=OCT_1,
    )
    assert kept.used == 1
    assert kept.period is not None and kept.period.status == PERIOD_STATUS_ACTIVE
    done = roster.get_rollover_plan(
        USER, snap, has_overlay=lambda law: _has(overlay, USER, law), now=OCT_1
    )
    assert done.manages_current_period is False
    assert done.month_name == "November"


def test_gap_month_is_not_carry_forward(tmp_path: Path, monkeypatch):
    _allow_stubs(monkeypatch)
    roster, overlay, _conn = _open(tmp_path)
    snap = _snap()
    _consume(roster, overlay, USER, snap, "ndps", SEP_25)
    roster.ensure_current_period(USER, snap, now=NOV_1)
    plan = roster.get_rollover_plan(
        USER, snap, has_overlay=lambda law: _has(overlay, USER, law), now=NOV_1
    )
    assert [row.law_id for row in plan.candidates] == []
    assert plan.month_name == "December"
    added = roster.confirm_add_law(
        USER, "ndps", snap, now=NOV_1, has_historical_overlay=True
    )
    assert added.ok
    assert added.item is not None
    assert added.item.origin == ORIGIN_RE_ADD
    assert added.used == 1
    september = roster._repo.get_item(USER, playground_month_bounds(SEP_25)[0], "ndps")
    november = roster._repo.get_item(USER, playground_month_bounds(NOV_1)[0], "ndps")
    assert september is not None and november is not None
    assert september.id != november.id


def test_removed_law_keeps_progress_and_later_add_resumes(tmp_path: Path, monkeypatch):
    _allow_stubs(monkeypatch)
    roster, overlay, conn = _open(tmp_path)
    snap = _snap()
    _consume(roster, overlay, USER, snap, "ndps", SEP_25, removed=True)
    overlay.replace_selection(USER, "ndps", [("ndps:s:1", "v1", "hash-v1")])
    _plant_progress(conn, USER, "ndps")
    before = _fingerprint(overlay, USER, "ndps")
    roster.confirm_carry_forward(
        USER,
        [],
        ["ndps"],
        snap,
        has_overlay=lambda law: _has(overlay, USER, law),
        now=OCT_1,
    )
    assert _fingerprint(overlay, USER, "ndps") == before
    assert roster.is_law_active_this_period(USER, "ndps", now=OCT_1) is False
    roster.ensure_current_period(USER, snap, now=NOV_1)
    resumed = roster.confirm_add_law(
        USER, "ndps", snap, now=NOV_1, has_historical_overlay=True
    )
    assert resumed.item is not None and resumed.item.origin == ORIGIN_RE_ADD
    assert resumed.used == 1
    after = _fingerprint(overlay, USER, "ndps")
    assert after[1] == before[1]
    assert after[2] == before[2]
    assert after[0][0:2] == before[0][0:2]


def test_draft_revision_and_downgrade_upgrade(tmp_path: Path, monkeypatch):
    _allow_stubs(monkeypatch)
    roster, overlay, _conn = _open(tmp_path)
    pro = _snap(tier="pro", limit=30)
    laws = [f"stub-{i}" for i in range(15)]
    for law_id in laws:
        _consume(roster, overlay, USER, pro, law_id, SEP_25)
    prepared = roster.confirm_carry_forward(
        USER,
        laws,
        [],
        pro,
        has_overlay=lambda law: _has(overlay, USER, law),
        now=SEP_25,
    )
    assert prepared.period is not None and prepared.period.status == PERIOD_STATUS_DRAFT
    assert prepared.used == 15
    plus = _snap(tier="plus", limit=10)
    held = roster.activate_due_draft(USER, plus, now=OCT_1)
    assert held.status == PERIOD_STATUS_DRAFT
    assert held.law_limit == 10
    plan = roster.get_rollover_plan(
        USER, plus, has_overlay=lambda law: _has(overlay, USER, law), now=OCT_1
    )
    assert plan.adjustment_required is True
    assert plan.manages_current_period is True
    fixed = roster.confirm_carry_forward(
        USER,
        [],
        laws[10:],
        plus,
        has_overlay=lambda law: _has(overlay, USER, law),
        now=OCT_1,
    )
    assert fixed.ok
    assert fixed.used == 10
    assert fixed.period is not None and fixed.period.status == PERIOD_STATUS_ACTIVE
    upgraded = _snap(tier="pro", limit=30)
    roster.ensure_current_period(USER, upgraded, now=OCT_1)
    period = roster.get_current_period(USER, now=OCT_1)
    assert period is not None and period.law_limit == 30
    assert roster.is_law_active_this_period(USER, "stub-0", now=OCT_1)


def test_upgrade_before_activation_keeps_prior_decisions(tmp_path: Path, monkeypatch):
    _allow_stubs(monkeypatch)
    roster, overlay, _conn = _open(tmp_path)
    plus = _snap()
    laws = [f"stub-{i}" for i in range(12)]
    for law_id in laws:
        _consume(roster, overlay, USER, _snap(tier="pro", limit=30), law_id, SEP_25)
    roster.confirm_carry_forward(
        USER,
        laws[:8],
        [],
        plus,
        has_overlay=lambda law: _has(overlay, USER, law),
        now=SEP_25,
    )
    pro = _snap(tier="pro", limit=30)
    more = roster.confirm_carry_forward(
        USER,
        laws[8:],
        [],
        pro,
        has_overlay=lambda law: _has(overlay, USER, law),
        now=SEP_25,
    )
    assert more.ok
    assert more.used == 12
    assert more.period is not None and more.period.law_limit == 30
    assert more.period.status == PERIOD_STATUS_DRAFT


def test_pending_blocks_keep_and_allows_decline(tmp_path: Path, monkeypatch):
    _allow_stubs(monkeypatch)
    roster, overlay, _conn = _open(tmp_path)
    snap = _snap()
    _consume(roster, overlay, USER, snap, "ndps", SEP_25)
    _consume(roster, overlay, USER, snap, "bns", SEP_25)
    roster.confirm_carry_forward(
        USER,
        ["ndps"],
        ["bns"],
        snap,
        has_overlay=lambda law: _has(overlay, USER, law),
        now=OCT_1,
    )
    assert roster.is_law_active_this_period(USER, "ndps", now=OCT_1)
    pending = _snap(consume=False)
    blocked = roster.confirm_carry_forward(
        USER,
        ["ndps"],
        [],
        pending,
        has_overlay=lambda law: _has(overlay, USER, law),
        now=OCT_1,
        can_consume_new_law=False,
    )
    assert blocked.status == RESULT_NEW_BLOCKED
    declined = roster.confirm_carry_forward(
        USER,
        [],
        ["ndps"],
        pending,
        has_overlay=lambda law: _has(overlay, USER, law),
        now=OCT_1,
    )
    assert declined.ok
    assert roster.capacity(USER, pending, now=NOV_1).used == 0


def test_user_isolation_and_concurrency(tmp_path: Path, monkeypatch):
    _allow_stubs(monkeypatch)
    roster, overlay, conn = _open(tmp_path)
    wide = _snap(tier="pro", limit=30)
    snap = _snap(limit=1)
    _consume(roster, overlay, USER, wide, "stub-a", SEP_25)
    _consume(roster, overlay, USER, wide, "stub-b", SEP_25)
    outsider = roster.confirm_carry_forward(
        OTHER,
        ["stub-a"],
        [],
        snap,
        has_overlay=lambda law: _has(overlay, USER, law),
        now=OCT_1,
    )
    assert outsider.status == RESULT_INVALID_CANDIDATE
    assert roster._repo.get_period(OTHER, playground_month_bounds(OCT_1)[0]) is None

    def keep(law_id: str):
        return roster.confirm_carry_forward(
            USER,
            [law_id],
            [],
            snap,
            has_overlay=lambda _law: True,
            now=OCT_1,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(keep, ["stub-a", "stub-b"]))
    assert sorted(result.status for result in results) == [RESULT_OK, RESULT_ROSTER_FULL]
    assert roster.capacity(USER, snap, now=OCT_1).used == 1
    rows = conn.execute(
        "SELECT law_id FROM user_playground_roster_item WHERE period_start = '2026-10-01' AND consumed_at IS NOT NULL"
    ).fetchall()
    assert len(rows) == 1


def test_same_candidate_keep_is_one_row(tmp_path: Path, monkeypatch):
    _allow_stubs(monkeypatch)
    roster, overlay, conn = _open(tmp_path)
    snap = _snap()
    _consume(roster, overlay, USER, snap, "ndps", SEP_25)

    def keep(_n: int):
        return roster.confirm_carry_forward(
            USER,
            ["ndps"],
            [],
            snap,
            has_overlay=lambda _law: True,
            now=OCT_1,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(keep, [1, 2]))
    assert all(result.ok for result in results)
    rows = conn.execute(
        "SELECT law_id FROM user_playground_roster_item WHERE period_start = '2026-10-01'"
    ).fetchall()
    assert [row["law_id"] for row in rows] == ["ndps"]


def test_annual_span_rollover_matches_monthly_cadence(tmp_path: Path, monkeypatch):
    _allow_stubs(monkeypatch)
    roster, overlay, _conn = _open(tmp_path)
    snap = _snap()
    assert snap.billing_period_end == ANNUAL_END
    _consume(roster, overlay, USER, snap, "ndps", SEP_25)
    _consume(roster, overlay, USER, snap, "bns", SEP_25)
    september = roster.confirm_carry_forward(
        USER,
        ["ndps"],
        ["bns"],
        snap,
        has_overlay=lambda law: _has(overlay, USER, law),
        now=SEP_25,
    )
    assert september.period is not None
    assert september.period.period_start.isoformat() == "2026-10-01"
    assert september.used == 1
    roster.activate_due_draft(USER, snap, now=OCT_1)
    october = roster.confirm_carry_forward(
        USER,
        [],
        ["ndps"],
        snap,
        has_overlay=lambda law: _has(overlay, USER, law),
        now=OCT_1,
    )
    assert october.period is not None
    assert october.period.period_start.isoformat() == "2026-11-01"
    assert october.used == 0
    assert october.period.status == PERIOD_STATUS_DRAFT


def test_admin_rollover_is_unlimited_and_explicit(tmp_path: Path):
    roster, overlay, _conn = _open(tmp_path)
    admin = _snap(admin=True)
    _seed_overlay(overlay, USER, "ndps")
    _seed_overlay(overlay, USER, "bns")
    roster.confirm_add_law(USER, "ndps", admin, now=SEP_25, has_historical_overlay=True)
    roster.confirm_add_law(USER, "bns", admin, now=SEP_25, has_historical_overlay=True)
    plan = roster.get_rollover_plan(
        USER, admin, has_overlay=lambda law: _has(overlay, USER, law), now=SEP_25
    )
    assert plan.law_limit is None
    assert plan.used == 0
    kept = roster.confirm_carry_forward(
        USER,
        ["ndps"],
        ["bns"],
        admin,
        has_overlay=lambda law: _has(overlay, USER, law),
        now=SEP_25,
    )
    assert kept.ok and kept.remaining is None and kept.used == 1


def test_postgres_rollover_locks_period_row():
    import inspect

    body = inspect.getsource(PostgresRosterRepository.apply_rollover)
    assert "FOR UPDATE" in body
    sqlite_body = inspect.getsource(SqliteRosterRepository.apply_rollover)
    assert "BEGIN IMMEDIATE" in inspect.getsource(SqliteRosterRepository._exclusive)
    assert "plan_rollover_batch" in sqlite_body


def test_alembic_head_unchanged():
    cfg = Config(str(ROOT / "alembic.ini"))
    assert ScriptDirectory.from_config(cfg).get_heads() == ["20260925_0026"]


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


def _client(tmp_path: Path) -> TestClient:
    conn = open_progress_db(tmp_path / "progress.db")
    provider = FakeAuthProvider()
    provider.seed_google_user(user_id=USER, email="m5b@example.com", display_name="M5B")
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
    client.app.state.subscriptions.create_subscription_record(
        USER,
        tier="plus",
        status="active",
        billing_period_start=ANNUAL_START,
        billing_period_end=ANNUAL_END,
        is_current=True,
    )
    return client


def _freeze(monkeypatch: pytest.MonkeyPatch, when: datetime) -> None:
    import constitution_memorizer.playground.roster.period as period_mod

    real_bounds = period_mod.playground_month_bounds

    def bounds(now=None):
        return real_bounds(when if now is None else now)

    monkeypatch.setattr(period_mod, "playground_month_bounds", bounds)
    monkeypatch.setattr(roster_service, "playground_month_bounds", bounds)
    monkeypatch.setattr(
        playground_routes,
        "playground_today",
        lambda now=None: period_mod.playground_today(when if now is None else now),
    )


def _csrf(client: TestClient) -> dict[str, str]:
    token = client.cookies.get("rtc_csrf") or ""
    return {"csrf_token": token} if token else {}


def test_http_prepare_promote_and_zero_hydration(tmp_path: Path, monkeypatch):
    client = _client(tmp_path)
    _freeze(monkeypatch, SEP_25)
    token = _csrf(client)
    client.post(
        "/playground/laws/ndps/add",
        data={**token, "confirm": "add"},
        follow_redirects=False,
    )
    client.post(
        "/playground/laws/bns/add",
        data={**token, "confirm": "add"},
        follow_redirects=False,
    )
    client.post(
        "/playground/roster/bns/remove",
        data=token,
        follow_redirects=False,
    )
    clear_bare_act_cache()
    hydrated: list[str] = []
    real = bare_acts._load_cached

    def wrapped(slug: str, identity: str):
        hydrated.append(slug)
        return real(slug, identity)

    wrapped.cache_clear = real.cache_clear  # type: ignore[attr-defined]
    monkeypatch.setattr(bare_acts, "_load_cached", wrapped)
    preview = client.get("/playground/roster/next")
    assert preview.status_code == 200
    assert "Your October Playground" in preview.text
    assert 'data-rollover-candidate="ndps"' in preview.text
    assert 'data-rollover-candidate="bns"' in preview.text
    assert 'data-previously-removed="true"' in preview.text
    assert hydrated == []
    posted = client.post(
        "/playground/roster/next",
        data={**token, "keep_ids": "ndps", "decline_ids": "bns"},
        follow_redirects=False,
    )
    assert posted.status_code == 303
    assert hydrated == []
    roster = client.app.state.roster
    october = roster._repo.get_period(USER, next_playground_month_bounds(SEP_25)[0])
    assert october is not None and october.status == PERIOD_STATUS_DRAFT
    assert roster.is_law_active_this_period(USER, "ndps", now=SEP_25)
    assert roster.is_law_active_this_period(USER, "bns", now=SEP_25) is False
    learn = client.get(learn_path("bns", "1"))
    assert "bns" not in hydrated
    assert "Progress saved" in learn.text or "Add to this month" in learn.text
    _freeze(monkeypatch, OCT_1)
    home = client.get("/playground")
    assert home.status_code == 200
    assert "Narcotic" in home.text
    assert hydrated == []
    assert roster.is_law_active_this_period(USER, "ndps")
    assert roster.is_law_active_this_period(USER, "bns") is False


def test_http_csrf_and_halted_do_not_consume(tmp_path: Path, monkeypatch):
    client = _client(tmp_path)
    _freeze(monkeypatch, SEP_25)
    missing = client.post(
        "/playground/roster/next",
        data={"keep_ids": "ndps"},
        follow_redirects=False,
    )
    assert missing.status_code == 403
    client.app.state.subscriptions.update_subscription_state(
        USER,
        client.app.state.subscriptions.get_current_subscription(USER).id,
        status="halted",
    )
    before = client.app.state.roster._repo.list_periods(USER)
    gated = client.get(roster_next_path())
    assert "Payment retries have stopped" in gated.text
    assert client.app.state.roster._repo.list_periods(USER) == before


def test_over_cap_batch_is_rejected_whole(tmp_path: Path, monkeypatch):
    _allow_stubs(monkeypatch)
    roster, overlay, _conn = _open(tmp_path)
    wide = _snap(tier="pro", limit=30)
    snap = _snap(limit=2)
    for law_id in ("stub-a", "stub-b", "stub-c", "stub-d"):
        _consume(roster, overlay, USER, wide, law_id, SEP_25)
    roster.confirm_carry_forward(
        USER,
        ["stub-a", "stub-b"],
        [],
        snap,
        has_overlay=lambda law: _has(overlay, USER, law),
        now=OCT_1,
    )
    rejected = roster.confirm_carry_forward(
        USER,
        ["stub-c", "stub-d"],
        [],
        snap,
        has_overlay=lambda law: _has(overlay, USER, law),
        now=OCT_1,
    )
    assert rejected.status == RESULT_ROSTER_FULL
    assert roster.capacity(USER, snap, now=OCT_1).used == 2
    assert roster._repo.get_item(
        USER, playground_month_bounds(OCT_1)[0], "stub-c"
    ) is None
