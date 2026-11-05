"""B1 — entitlement foundation under ``PLAYGROUND_TIER_MODEL``.

Acceptance criteria from the tier-revision plan §3.1 (B1-F01…F19, B1-M02).
Every ``choices`` test builds the app with the flag set explicitly; the
default (``monthly``) is asserted to be behaviour-preserving.
"""

from __future__ import annotations

import importlib.util
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from alembic.config import Config
from alembic.script import ScriptDirectory

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import InMemorySessionStore
from constitution_memorizer.entitlements.models import (
    BLOCK_FREE_CHOICES_EXHAUSTED,
    BLOCK_PAID_PERIOD_ENDED,
    CONSTITUTION_ACCESS_FULL,
    EntitlementSnapshot,
)
from constitution_memorizer.entitlements.service import EntitlementService
from constitution_memorizer.entitlements.tier_model import FREE_CHOICE_LIMIT
from constitution_memorizer.multiuser.settings import MultiUserSettings
from constitution_memorizer.playground.db import ensure_sqlite_schema as ensure_overlay_schema
from constitution_memorizer.playground.roster.db import ensure_sqlite_schema as ensure_roster_schema
from constitution_memorizer.playground.roster.models import (
    RESULT_FREE_CHOICES_EXHAUSTED,
    RESULT_OK,
    RESULT_RE_ADDED,
    RESULT_ROSTER_FULL,
)
from constitution_memorizer.playground.roster.period import playground_month_bounds
from constitution_memorizer.playground.roster.repository import SqliteRosterRepository
from constitution_memorizer.playground.roster.service import RosterService
from constitution_memorizer.playground.service import (
    membership_and_selection_writer,
    require_playground_law,
    selection_rows,
)
from constitution_memorizer.playground.urls import (
    add_path,
    law_path,
    roster_next_path,
    roster_path,
    sections_path,
)
from constitution_memorizer.progress.db import open_progress_db
from constitution_memorizer.progress.repository import ProgressRepository
from constitution_memorizer.web.app import create_app

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
USER = UUID("b1b1b1b1-b1b1-4b1b-8b1b-b1b1b1b1b1b1")
NOW = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
OCT_1 = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)
HMAC_SECRET = "b1-test-hmac-secret"
LAWS = ("ndps", "uapa", "pss", "bns", "bnss", "mtp")


# ---------------------------------------------------------------- helpers


def _mu_settings(tier_model: str | None) -> MultiUserSettings:
    kwargs = dict(
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
    if tier_model is not None:
        kwargs["PLAYGROUND_TIER_MODEL"] = tier_model
    return MultiUserSettings(**kwargs)


def _client(tmp_path: Path, *, tier_model: str | None = "choices", sign_in: bool = True) -> TestClient:
    tmp_path.mkdir(parents=True, exist_ok=True)
    conn = open_progress_db(tmp_path / "progress.db")
    provider = FakeAuthProvider()
    provider.seed_google_user(user_id=USER, email="b1@example.com", display_name="B1")
    client = TestClient(
        create_app(
            units_path=MINI_UNITS,
            db_path=tmp_path / "unused.db",
            multiuser=True,
            multiuser_settings=_mu_settings(tier_model),
            auth_provider=provider,
            session_store=InMemorySessionStore(),
            progress_repo=ProgressRepository(conn),
            study_materials_dir=tmp_path / "study-materials",
        )
    )
    if sign_in:
        _sign_in(client)
    return client


def _sign_in(client: TestClient) -> None:
    start = client.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state")
    client.get(f"/auth/callback?code=fake-google-code&state={state}", follow_redirects=False)


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


def _sqlite(client: TestClient) -> sqlite3.Connection:
    return client.app.state.roster_repo._conn


def _facts(client: TestClient) -> dict[str, object]:
    """Logical records of the three roster tables (B1-F06/F15/F18)."""

    conn = _sqlite(client)
    periods = conn.execute(
        "SELECT user_id, period_start, tier_snapshot, law_limit, status, updated_at"
        " FROM user_playground_period ORDER BY user_id, period_start"
    ).fetchall()
    items = conn.execute(
        "SELECT user_id, period_start, law_id, origin, consumed_at, removed_at, updated_at"
        " FROM user_playground_roster_item ORDER BY user_id, period_start, law_id"
    ).fetchall()
    choices = conn.execute(
        "SELECT user_id, law_id, chosen_at, source FROM user_playground_choice"
        " ORDER BY user_id, law_id"
    ).fetchall()
    return {
        "periods": [tuple(row) for row in periods],
        "items": [tuple(row) for row in items],
        "choices": [tuple(row) for row in choices],
    }


def _ledger(client: TestClient) -> list[tuple]:
    return list(_facts(client)["choices"])  # type: ignore[arg-type]


def _add_entire(client: TestClient, law_id: str):
    payload = dict(_csrf(client))
    payload.update({"confirm": "add", "scope": "entire"})
    return client.post(add_path(law_id), data=payload, follow_redirects=False)


def _save_sections(client: TestClient, law_id: str, numbers: list[str]):
    payload: dict[str, object] = dict(_csrf(client))
    if numbers:
        payload["section"] = list(numbers)
    return client.post(sections_path(law_id), data=payload, follow_redirects=False)


def _snap(
    *,
    tier: str | None = None,
    is_subscribed: bool = False,
    law_limit: int | None = None,
    choice_limit: int | None = None,
    choices_used: int = 0,
    consume: bool = True,
    tier_model: str = "choices",
) -> EntitlementSnapshot:
    return EntitlementSnapshot(
        is_authenticated=True,
        subscription_status="active" if is_subscribed else None,
        tier=tier,
        is_subscribed=is_subscribed,
        admin_override=False,
        can_use_constitution_learn=True,
        constitution_access=CONSTITUTION_ACCESS_FULL,
        can_read_laws=True,
        can_open_playground=True,
        can_consume_new_playground_law=consume,
        playground_law_limit=law_limit,
        playground_block_reason=None,
        billing_period_start=None,
        billing_period_end=None,
        legacy_status=None,
        tier_model=tier_model,
        playground_choice_limit=choice_limit,
        playground_choices_used=choices_used,
        playground_consume_block_reason=(
            None if consume else BLOCK_FREE_CHOICES_EXHAUSTED
        ),
    )


def _roster(tmp_path: Path, *, tier_model: str = "choices") -> tuple[RosterService, sqlite3.Connection]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(tmp_path / "roster.db"), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 8000")
    ensure_overlay_schema(conn)
    ensure_roster_schema(conn)
    return RosterService(SqliteRosterRepository(conn), tier_model=tier_model), conn


def _allow_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    from constitution_memorizer.playground.roster import service as roster_service

    real = roster_service.is_playground_eligible_law

    def wrapped(law_id: str) -> bool:
        if str(law_id).startswith("stub-"):
            return True
        return real(law_id)

    monkeypatch.setattr(roster_service, "is_playground_eligible_law", wrapped)


# ------------------------------------------------------------ flag default


def test_flag_defaults_to_monthly_and_free_stays_blocked(tmp_path: Path):
    client = _client(tmp_path / "m", tier_model=None)
    assert client.app.state.playground_tier_model == "monthly"
    home = client.get("/playground")
    assert home.status_code == 200
    assert 'data-playground-gate="not_subscribed"' in home.text or "View Playground plans" in home.text
    # §4.10 / B1-F15: the Add page GET no longer creates a period for an
    # account that cannot open the Playground, under either model.
    before = _facts(client)
    page = client.get(add_path("ndps"))
    assert page.status_code == 200
    assert _facts(client) == before
    assert before["periods"] == []


def test_invalid_flag_value_is_rejected():
    with pytest.raises(ValueError):
        _mu_settings("weekly")


# ------------------------------------------------------- Free: P-NEW / READD


def test_free_opens_playground_and_has_three_permanent_choices(tmp_path: Path):
    client = _client(tmp_path / "c")
    home = client.get("/playground")
    assert home.status_code == 200
    assert 'data-playground-gate="not_subscribed"' not in home.text
    snapshot = client.app.state.entitlement_service.resolve(USER)
    assert snapshot.can_open_playground is True
    assert snapshot.playground_choice_limit == FREE_CHOICE_LIMIT
    assert snapshot.playground_choices_used == 0
    assert snapshot.playground_law_limit is None
    assert snapshot.can_add_personal_calendar_tasks is False
    assert snapshot.can_open_visual_explainers is False

    for law in ("ndps", "uapa", "pss"):
        resp = _add_entire(client, law)
        assert resp.status_code == 303, (law, resp.status_code, resp.text[:200])
    assert len(_ledger(client)) == 3
    assert {row[1] for row in _ledger(client)} == {"ndps", "uapa", "pss"}
    assert all(row[3] == "free_add" for row in _ledger(client))

    # Period row for a Free account: labelled, no cap (§4.10, B1-F16 check 2).
    periods = _facts(client)["periods"]
    assert len(periods) == 1
    assert periods[0][2] == "free" and periods[0][3] is None

    # A fourth distinct law is refused; existing laws stay usable.
    snapshot = client.app.state.entitlement_service.resolve(USER)
    assert snapshot.can_consume_new_playground_law is False
    assert snapshot.playground_consume_block_reason == BLOCK_FREE_CHOICES_EXHAUSTED
    assert snapshot.can_open_playground is True
    fourth = _add_entire(client, "bns")
    assert fourth.status_code == 200
    assert 'data-playground-gate="free_choices_exhausted"' in fourth.text
    assert len(_ledger(client)) == 3
    assert client.get(law_path("ndps")).status_code == 200
    add_page = client.get(add_path("bns"))
    assert "free_choices_exhausted" in add_page.text
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps")


def test_remove_keeps_choice_and_readd_is_free(tmp_path: Path):
    client = _client(tmp_path / "r")
    for law in ("ndps", "uapa", "pss"):
        assert _add_entire(client, law).status_code == 303
    ledger_before = _ledger(client)
    removed = client.post(f"/playground/roster/ndps/remove", data=_csrf(client), follow_redirects=False)
    assert removed.status_code == 303
    assert _ledger(client) == ledger_before
    assert not client.app.state.roster.is_law_active_this_period(USER, "ndps")
    # Eligibility is permanent: the Add page offers a free re-add even at 3 used.
    page = client.get(add_path("ndps"))
    assert page.status_code == 200
    assert "free_choices_exhausted" not in page.text
    readd = _add_entire(client, "ndps")
    assert readd.status_code == 303
    assert "notice=readded" in (readd.headers.get("location") or "")
    assert _ledger(client) == ledger_before
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps")


# ------------------------------------------------------ read-only previews


@pytest.mark.parametrize("tier", ["free", "plus"])
def test_get_walk_writes_nothing(tmp_path: Path, tier: str):
    client = _client(tmp_path / f"walk-{tier}")
    if tier == "plus":
        _subscribe(client, tier="plus")
    assert _add_entire(client, "ndps").status_code == 303
    before = _facts(client)
    for url in (
        "/playground",
        roster_path(),
        roster_path(add="uapa"),
        add_path("uapa"),
        add_path("uapa") + "?step=scope",
        law_path("ndps"),
        sections_path("ndps"),
        "/playground/roster/ndps/remove",
        roster_next_path(),
        "/laws/ndps",
        "/laws/uapa",
    ):
        resp = client.get(url, follow_redirects=False)
        assert resp.status_code in {200, 303}, (url, resp.status_code)
        assert _facts(client) == before, url
    # Scope-step render via POST without a scope value is also read-only.
    payload = dict(_csrf(client))
    payload["confirm"] = "add"
    resp = client.post(add_path("uapa"), data=payload, follow_redirects=False)
    assert resp.status_code == 200
    assert _facts(client) == before


def test_free_account_first_visit_creates_no_period(tmp_path: Path):
    client = _client(tmp_path / "first")
    for url in ("/playground", add_path("ndps"), roster_path(), "/laws/ndps"):
        assert client.get(url).status_code == 200
    assert _facts(client)["periods"] == []
    assert _facts(client)["items"] == []
    assert _facts(client)["choices"] == []


# ---------------------------------------------------------- 5-19 B′ save


def test_sections_scope_consumes_only_on_first_saved_section(tmp_path: Path):
    client = _client(tmp_path / "sections")
    baseline = _facts(client)
    payload = dict(_csrf(client))
    payload.update({"confirm": "add", "scope": "sections"})
    chose = client.post(add_path("ndps"), data=payload, follow_redirects=False)
    assert chose.status_code == 303
    assert (chose.headers.get("location") or "").endswith(sections_path("ndps"))
    assert _facts(client) == baseline  # selecting a scope wrote nothing
    picker = client.get(sections_path("ndps"))
    assert picker.status_code == 200
    assert _facts(client) == baseline
    abandoned = _save_sections(client, "ndps", [])
    assert abandoned.status_code == 303
    assert _facts(client) == baseline  # nothing saved, nothing consumed
    saved = _save_sections(client, "ndps", ["1"])
    assert saved.status_code == 303, saved.text[:200]
    after = _facts(client)
    assert len(after["choices"]) == 1 and after["choices"][0][1] == "ndps"
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps")
    assert client.app.state.playground.list_selection(USER, "ndps")


def test_entire_act_save_consumes_once_and_repeat_is_idempotent(tmp_path: Path):
    client = _client(tmp_path / "entire")
    assert _add_entire(client, "ndps").status_code == 303
    once = _facts(client)
    again = _add_entire(client, "ndps")
    assert again.status_code == 303
    assert _facts(client)["choices"] == once["choices"]
    assert len(once["choices"]) == 1


# ---------------------------------------------------------- paid unlimited


def test_plus_adds_every_law_without_a_cap(tmp_path: Path):
    client = _client(tmp_path / "plus")
    _subscribe(client, tier="plus")
    snapshot = client.app.state.entitlement_service.resolve(USER)
    assert snapshot.playground_law_limit is None
    assert snapshot.can_add_personal_calendar_tasks is True
    assert snapshot.can_open_visual_explainers is False
    for law in LAWS:
        resp = _add_entire(client, law)
        assert resp.status_code == 303, (law, resp.status_code)
        assert "roster_full" not in resp.text
    assert _facts(client)["choices"] == []  # paid tiers never touch the ledger
    roster_page = client.get(roster_path())
    assert "Playground full" not in roster_page.text
    assert "of 10" not in roster_page.text


def test_plus_exceeds_old_cap_at_service_level(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _allow_stubs(monkeypatch)
    roster, _conn = _roster(tmp_path / "svc")
    snap = _snap(tier="plus", is_subscribed=True, law_limit=None)
    for n in range(1, 32):
        result = roster.confirm_add_law(USER, f"stub-{n}", snap, now=NOW)
        assert result.status == RESULT_OK, (n, result.status)
    cap = roster.peek_capacity(USER, snap, now=NOW)
    assert cap.law_limit is None and cap.remaining is None and cap.used == 31


def test_stale_stored_limit_cannot_block_paid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _allow_stubs(monkeypatch)
    roster, conn = _roster(tmp_path / "stale")
    start, end = playground_month_bounds(NOW)
    # A period row written by the old code with the Plus cap of 10.
    conn.execute(
        "INSERT INTO user_playground_period (id, user_id, period_start, period_end,"
        " tier_snapshot, law_limit, status, confirmed_at, created_at, updated_at)"
        " VALUES ('p1', ?, ?, ?, 'plus', 10, 'active', '2026-09-01T00:00:00+00:00',"
        " '2026-09-01T00:00:00+00:00', '2026-09-01T00:00:00+00:00')",
        (str(USER), start.isoformat(), end.isoformat()),
    )
    for n in range(10):
        conn.execute(
            "INSERT INTO user_playground_roster_item (id, user_id, period_start, law_id,"
            " origin, carried_from_previous_period, consumed_at, removed_at, declined_at,"
            " created_at, updated_at) VALUES (?, ?, ?, ?, 'new', 0,"
            " '2026-09-02T00:00:00+00:00', NULL, NULL, '2026-09-02T00:00:00+00:00',"
            " '2026-09-02T00:00:00+00:00')",
            (f"i{n}", str(USER), start.isoformat(), f"stub-{n}"),
        )
    conn.commit()
    snap = _snap(tier="plus", is_subscribed=True, law_limit=None)
    preview = roster.preview_add_law(USER, "ndps", snap, now=NOW, mutate=False)
    assert preview.status != RESULT_ROSTER_FULL
    assert preview.law_limit is None
    result = roster.confirm_add_law(USER, "ndps", snap, now=NOW)
    assert result.status == RESULT_OK
    assert roster.peek_capacity(USER, snap, now=NOW).law_limit is None


def test_monthly_model_still_enforces_the_stored_cap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _allow_stubs(monkeypatch)
    roster, _conn = _roster(tmp_path / "monthly", tier_model="monthly")
    snap = _snap(tier="plus", is_subscribed=True, law_limit=2, tier_model="monthly")
    assert roster.confirm_add_law(USER, "stub-1", snap, now=NOW).status == RESULT_OK
    assert roster.confirm_add_law(USER, "stub-2", snap, now=NOW).status == RESULT_OK
    assert roster.confirm_add_law(USER, "stub-3", snap, now=NOW).status == RESULT_ROSTER_FULL


# -------------------------------------------------------- Free at service


def test_free_ledger_at_service_level(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _allow_stubs(monkeypatch)
    roster, _conn = _roster(tmp_path / "freesvc")
    free = _snap(choice_limit=3)
    for n in range(1, 4):
        result = roster.confirm_add_law(USER, f"stub-{n}", free, now=NOW)
        assert result.status == RESULT_OK and result.choice_recorded is True
        assert result.choices_used == n
    exhausted = _snap(choice_limit=3, choices_used=3, consume=False)
    blocked = roster.confirm_add_law(
        USER, "stub-4", exhausted, now=NOW, can_consume_new_law=False
    )
    assert blocked.status == RESULT_FREE_CHOICES_EXHAUSTED
    assert roster.choice_law_ids(USER) == frozenset({"stub-1", "stub-2", "stub-3"})
    roster.remove_law_this_period(USER, "stub-2", exhausted, now=NOW)
    readd = roster.confirm_add_law(
        USER, "stub-2", exhausted, now=NOW, can_consume_new_law=False
    )
    assert readd.status == RESULT_RE_ADDED and readd.choice_recorded is False
    assert roster.is_law_active_this_period(USER, "stub-2", now=NOW)
    cap = roster.peek_capacity(USER, exhausted, now=NOW)
    assert cap.permanent is True and cap.used == 3 and cap.remaining == 0


def test_concurrent_free_adds_record_at_most_the_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from concurrent.futures import ThreadPoolExecutor

    _allow_stubs(monkeypatch)
    roster, _conn = _roster(tmp_path / "conc")
    two_used = _snap(choice_limit=3, choices_used=2)
    roster.confirm_add_law(USER, "stub-1", two_used, now=NOW)
    roster.confirm_add_law(USER, "stub-2", two_used, now=NOW)

    def attempt(law: str):
        return roster.confirm_add_law(USER, law, two_used, now=NOW).status

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(attempt, ["stub-3", "stub-4"]))
    assert sorted(statuses) == sorted([RESULT_OK, RESULT_FREE_CHOICES_EXHAUSTED])
    assert len(roster.choice_law_ids(USER)) == 3


# -------------------------------------------------------- month boundary


def test_memberships_continue_across_month_boundary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _allow_stubs(monkeypatch)
    roster, conn = _roster(tmp_path / "month")
    free = _snap(choice_limit=3)
    assert roster.confirm_add_law(USER, "stub-1", free, now=NOW).status == RESULT_OK
    assert roster.confirm_add_law(USER, "stub-2", free, now=NOW).status == RESULT_OK
    roster.remove_law_this_period(USER, "stub-2", free, now=NOW)
    oct_start, _ = playground_month_bounds(OCT_1)
    # Reads in October see September's active membership without a write.
    assert roster.is_law_active_this_period(USER, "stub-1", now=OCT_1)
    assert not roster.is_law_active_this_period(USER, "stub-2", now=OCT_1)
    assert roster._repo.get_period(USER, oct_start) is None
    assert roster.peek_capacity(USER, free, now=OCT_1).used == 2  # ledger, not month
    # The next save point materialises October and carries only active items.
    assert roster.confirm_add_law(USER, "stub-3", free, now=OCT_1).status == RESULT_OK
    october = roster._repo.get_period(USER, oct_start)
    assert october is not None and october.status == "active"
    items = {item.law_id: item for item in roster._repo.list_items(USER, oct_start)}
    assert items["stub-1"].is_active and items["stub-1"].origin == "carry_forward"
    assert "stub-2" not in items  # removed laws are never re-added (B1-F17)
    assert items["stub-3"].is_active
    assert roster.choice_law_ids(USER) == frozenset({"stub-1", "stub-2", "stub-3"})
    # The removed ledger law is still a free re-add in October.
    readd = roster.confirm_add_law(
        USER, "stub-2", _snap(choice_limit=3, choices_used=3, consume=False),
        now=OCT_1, can_consume_new_law=False,
    )
    assert readd.status == RESULT_RE_ADDED


def test_pre_existing_draft_month_does_not_hide_membership(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A draft period left by the retired Keep/decline flow (staging holds one
    dated 2026-11-01) must neither hide September's membership nor block the
    promotion that carries it (5-23, §4.9 B4)."""

    _allow_stubs(monkeypatch)
    roster, conn = _roster(tmp_path / "draft")
    free = _snap(choice_limit=3)
    assert roster.confirm_add_law(USER, "stub-1", free, now=NOW).status == RESULT_OK
    oct_start, oct_end = playground_month_bounds(OCT_1)
    conn.execute(
        "INSERT INTO user_playground_period (id, user_id, period_start, period_end,"
        " tier_snapshot, law_limit, status, confirmed_at, created_at, updated_at)"
        " VALUES ('d1', ?, ?, ?, 'pro', 30, 'draft', NULL,"
        " '2026-09-20T00:00:00+00:00', '2026-09-20T00:00:00+00:00')",
        (str(USER), oct_start.isoformat(), oct_end.isoformat()),
    )
    conn.commit()
    assert roster.is_law_active_this_period(USER, "stub-1", now=OCT_1)
    assert [item.law_id for item in roster.active_roster_items(USER, now=OCT_1)] == ["stub-1"]
    assert roster.confirm_add_law(USER, "stub-2", free, now=OCT_1).status == RESULT_OK
    october = roster._repo.get_period(USER, oct_start)
    assert october is not None and october.status == "active" and october.law_limit is None
    items = {item.law_id: item for item in roster._repo.list_items(USER, oct_start)}
    assert items["stub-1"].is_active and items["stub-2"].is_active


def test_rollover_routes_redirect_under_choices(tmp_path: Path):
    client = _client(tmp_path / "rollover")
    _subscribe(client, tier="plus")
    page = client.get(roster_next_path(), follow_redirects=False)
    assert page.status_code == 303
    assert (page.headers.get("location") or "").endswith(roster_path())
    posted = client.post(roster_next_path(), data=_csrf(client), follow_redirects=False)
    assert posted.status_code == 303


# ----------------------------------------------------------- preservation


def test_ledger_records_survive_flag_and_subscription_changes(tmp_path: Path):
    base = tmp_path / "keep"
    client = _client(base)
    assert _add_entire(client, "ndps").status_code == 303
    assert _add_entire(client, "uapa").status_code == 303
    ledger = _ledger(client)
    assert len(ledger) == 2

    # Flag back to monthly on the same database: rows retained, Free blocked.
    monthly = _client(base, tier_model="monthly")
    home = monthly.get("/playground")
    assert home.status_code == 200
    assert _ledger(monthly) == ledger
    assert not monthly.app.state.entitlement_service.resolve(USER).can_open_playground

    # Flag on again, then a paid subscription: paid adds never touch the ledger.
    again = _client(base)
    assert _ledger(again) == ledger
    row = _subscribe(again, tier="pro")
    snapshot = again.app.state.entitlement_service.resolve(USER)
    assert snapshot.is_subscribed and snapshot.playground_law_limit is None
    assert _add_entire(again, "bns").status_code == 303
    assert _ledger(again) == ledger

    # Paid period ends: today's disposition is kept (5-20 unresolved); the
    # ledger is untouched. No automatic Free capability for a subscription row.
    again.app.state.subscriptions.update_subscription_state(
        USER,
        row.id,
        billing_period_start=datetime(2026, 8, 1, tzinfo=timezone.utc),
        billing_period_end=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    ended = again.app.state.entitlement_service.resolve(USER)
    assert ended.playground_block_reason == BLOCK_PAID_PERIOD_ENDED
    assert ended.can_open_playground is False
    assert _ledger(again) == ledger

    # A fresh explicit Free choice appends exactly one record (ledger is Free-only).
    fresh = _client(tmp_path / "fresh")
    assert _add_entire(fresh, "ndps").status_code == 303
    assert len(_ledger(fresh)) == 1


def test_migration_rerun_is_a_noop_for_existing_rows(tmp_path: Path):
    roster, conn = _roster(tmp_path / "rerun")
    free = _snap(choice_limit=3)
    roster.confirm_add_law(USER, "ndps", free, now=NOW)
    before = conn.execute("SELECT * FROM user_playground_choice").fetchall()
    ensure_roster_schema(conn)  # CREATE TABLE IF NOT EXISTS: no row changes
    after = conn.execute("SELECT * FROM user_playground_choice").fetchall()
    assert [tuple(r) for r in before] == [tuple(r) for r in after]


# ------------------------------------------------------------- migration


def test_alembic_chain_head_is_the_ledger_and_downgrade_is_refused():
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    script = ScriptDirectory.from_config(config)
    heads = script.get_heads()
    assert heads == ["20261103_0028"], heads
    revision = script.get_revision("20261103_0028")
    assert revision.down_revision == "20260927_0027"
    path = ROOT / "alembic" / "versions" / "20261103_0028_playground_choice.py"
    spec = importlib.util.spec_from_file_location("mig_0028", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert "CREATE TABLE IF NOT EXISTS user_playground_choice" in module.SCHEMA
    assert "UNIQUE (user_id, law_id)" in module.SCHEMA
    assert "INSERT" not in module.SCHEMA.upper().replace("IF NOT EXISTS", "")
    with pytest.raises(RuntimeError):
        module.downgrade()


# ------------------------------------------------------- failed request


def test_failure_without_rollback_evidence_is_reported_unknown(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """B1-F07: an exception the repository did not mark as an observed
    rollback is classified by re-read; with the requested state absent the
    answer is ``unknown`` — never ``rolled_back`` on inference."""

    client = _client(tmp_path / "rollback")
    before = _facts(client)
    repo = client.app.state.roster_repo
    real = repo.consume_law

    def boom(*args, **kwargs):
        raise sqlite3.OperationalError("simulated failure inside the transaction")

    monkeypatch.setattr(repo, "consume_law", boom)
    resp = _add_entire(client, "ndps")
    assert resp.status_code == 503
    assert resp.headers.get("X-Playground-Outcome") == "unknown"
    assert "rolled it back" not in resp.text
    assert _facts(client)["choices"] == before["choices"]
    assert _facts(client)["items"] == before["items"]
    monkeypatch.setattr(repo, "consume_law", real)
    assert _add_entire(client, "ndps").status_code == 303


def test_first_section_save_is_atomic_when_the_selection_write_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """5-19 / B1-F08: the permanent choice, the active membership and the
    selected sections are one transaction. A failure inside the selection
    write rolls all three back (verified by re-read), and the retry consumes
    exactly one choice."""

    client = _client(tmp_path / "atomic")
    before = _facts(client)
    overlay = client.app.state.playground
    real = overlay.persist_membership_and_selection_in
    calls = {"n": 0}

    def fail_after_writing(conn, user_id, law_id, rows, **kwargs):
        calls["n"] += 1
        real(conn, user_id, law_id, rows, **kwargs)  # rows are on the open transaction…
        raise sqlite3.OperationalError("simulated failure writing the selection")

    monkeypatch.setattr(overlay, "persist_membership_and_selection_in", fail_after_writing)
    resp = _save_sections(client, "ndps", ["1"])
    assert resp.status_code == 503
    assert resp.headers.get("X-Playground-Outcome") == "rolled_back"  # observed by the repository
    assert "This law was not added" in resp.text and "none of the requested sections were saved" in resp.text
    assert calls["n"] == 1
    after = _facts(client)
    assert after["choices"] == before["choices"] == []
    assert after["items"] == before["items"] == []
    assert overlay.get_item(USER, "ndps") is None
    assert overlay.list_selection(USER, "ndps") == []
    assert not client.app.state.roster.is_law_active_this_period(USER, "ndps")

    monkeypatch.setattr(overlay, "persist_membership_and_selection_in", real)
    retry = _save_sections(client, "ndps", ["1"])
    assert retry.status_code == 303, retry.text[:200]
    assert (retry.headers.get("location") or "").endswith(law_path("ndps"))
    assert len(_ledger(client)) == 1
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps")
    assert [row.source_locator for row in overlay.list_selection(USER, "ndps")]


def test_entire_act_save_is_atomic_under_choices(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    client = _client(tmp_path / "entire-atomic")
    overlay = client.app.state.playground
    real = overlay.persist_membership_and_selection_in

    def fail(conn, *args, **kwargs):
        raise sqlite3.OperationalError("simulated failure writing the selection")

    monkeypatch.setattr(overlay, "persist_membership_and_selection_in", fail)
    resp = _add_entire(client, "ndps")
    assert resp.status_code == 503
    assert resp.headers.get("X-Playground-Outcome") == "rolled_back"
    assert _ledger(client) == []
    assert _facts(client)["items"] == []
    assert overlay.get_item(USER, "ndps") is None

    monkeypatch.setattr(overlay, "persist_membership_and_selection_in", real)
    assert _add_entire(client, "ndps").status_code == 303
    assert len(_ledger(client)) == 1
    assert overlay.list_selection(USER, "ndps")
    # The idempotent repeat takes the already-active path and rewrites nothing.
    assert _add_entire(client, "ndps").status_code == 303
    assert len(_ledger(client)) == 1


def test_committed_save_with_lost_acknowledgement_is_verified_not_repeated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """B1-F07(b): the transaction committed, then the call failed before the
    acknowledgement. The response must not claim a rollback; the re-read of
    membership and selection shows the save present, so the request finishes
    as the success it was and no second choice is spent."""

    client = _client(tmp_path / "lost-ack")
    repo = client.app.state.roster_repo
    real = repo.consume_law

    def commit_then_lose_connection(*args, **kwargs):
        real(*args, **kwargs)  # item + ledger + membership + selection committed
        raise sqlite3.OperationalError("connection lost before acknowledgement")

    monkeypatch.setattr(repo, "consume_law", commit_then_lose_connection)
    resp = _save_sections(client, "ndps", ["1"])
    assert resp.status_code == 303, resp.text[:200]
    assert (resp.headers.get("location") or "").endswith(law_path("ndps"))
    assert "X-Playground-Outcome" not in resp.headers
    assert len(_ledger(client)) == 1
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps")
    assert client.app.state.playground.list_selection(USER, "ndps")

    monkeypatch.setattr(repo, "consume_law", real)
    again = _save_sections(client, "ndps", ["1", "2"])  # member now: plain selection update
    assert again.status_code == 303
    assert len(_ledger(client)) == 1
    assert len(client.app.state.playground.list_selection(USER, "ndps")) == 2


def test_save_outcome_is_unknown_when_the_reread_itself_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """No evidence, no claim: when the write raised and the re-read also
    fails, the response says the outcome could not be confirmed instead of
    asserting a rollback."""

    client = _client(tmp_path / "unknown")
    repo = client.app.state.roster_repo
    roster = client.app.state.roster
    real_active = roster.is_law_active_this_period
    state = {"raised": False}

    def boom(*args, **kwargs):
        state["raised"] = True
        raise sqlite3.OperationalError("connection dropped")

    def flaky_reread(*args, **kwargs):
        if state["raised"]:
            raise sqlite3.OperationalError("re-read failed too")
        return real_active(*args, **kwargs)

    monkeypatch.setattr(repo, "consume_law", boom)
    monkeypatch.setattr(roster, "is_law_active_this_period", flaky_reread)
    resp = _save_sections(client, "ndps", ["1"])
    assert resp.status_code == 503
    assert resp.headers.get("X-Playground-Outcome") == "unknown"
    assert "could not confirm" in resp.text
    assert "was not added" not in resp.text


def test_two_devices_different_sections_lost_ack_is_unknown_not_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """B1-F07 (reviewer, two devices): A saves section 1 while B's save of
    section 2 is in flight and B's call then fails without rollback evidence.
    B must not read A's selection and call its own save a success: the stored
    selection differs from what B requested, so B gets ``unknown`` and
    section 2 is (correctly) not reported as saved."""

    client = _client(tmp_path / "two-devices")
    repo = client.app.state.roster_repo
    overlay = client.app.state.playground
    real = repo.consume_law
    rows_a = selection_rows("ndps", ["1"], entire=False, act=require_playground_law("ndps"))

    def device_a_commits_then_b_loses_the_ack(*args, **kwargs):
        # Device A's save lands first (choice + membership + section 1)…
        real(*args, **{**kwargs, "within": membership_and_selection_writer(overlay, USER, "ndps", rows_a)})
        # …and device B's own call fails before any acknowledgement.
        raise sqlite3.OperationalError("connection lost before acknowledgement")

    monkeypatch.setattr(repo, "consume_law", device_a_commits_then_b_loses_the_ack)
    resp_b = _save_sections(client, "ndps", ["2"])
    assert resp_b.status_code == 503
    assert resp_b.headers.get("X-Playground-Outcome") == "unknown"
    assert "could not confirm" in resp_b.text
    assert [r.source_locator for r in overlay.list_selection(USER, "ndps")] == [rows_a[0][0]]
    assert len(_ledger(client)) == 1  # A's choice; B spent nothing extra


def test_removal_between_commit_and_verification_is_unknown_not_rolled_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """B1-F07 (reviewer, reverse case): the save committed, the law was then
    removed before the re-read, and the acknowledgement was lost. The absent
    membership is not evidence of a rollback — the response is ``unknown``."""

    client = _client(tmp_path / "removed-between")
    repo = client.app.state.roster_repo
    roster = client.app.state.roster
    overlay = client.app.state.playground
    real = repo.consume_law

    def commit_remove_then_lose_the_ack(*args, **kwargs):
        real(*args, **kwargs)
        snapshot = client.app.state.entitlement_service.resolve(USER)
        roster.remove_law_this_period(USER, "ndps", snapshot)
        raise sqlite3.OperationalError("connection lost before acknowledgement")

    monkeypatch.setattr(repo, "consume_law", commit_remove_then_lose_the_ack)
    resp = _save_sections(client, "ndps", ["1"])
    assert resp.status_code == 503
    assert resp.headers.get("X-Playground-Outcome") == "unknown"
    assert "rolled it back" not in resp.text
    assert not roster.is_law_active_this_period(USER, "ndps")
    assert len(_ledger(client)) == 1  # the committed choice is real and kept
    assert overlay.list_selection(USER, "ndps")  # the committed selection is real too


def test_failed_first_save_at_month_boundary_leaves_only_the_bookkeeping_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Reviewer: the month bucket is committed separately before the consume.
    After a failed first save of October, only that row may survive — capacity
    and the visible active laws are unchanged, no law, choice or selection was
    added, and the exception carries the observed-rollback mark."""

    from constitution_memorizer.playground.repository import SqlitePlaygroundRepository
    from constitution_memorizer.playground.roster.models import save_was_rolled_back

    _allow_stubs(monkeypatch)
    roster, conn = _roster(tmp_path / "boundary")
    overlay = SqlitePlaygroundRepository(conn)
    free = _snap(choice_limit=3)
    assert roster.confirm_add_law(USER, "stub-1", free, now=NOW).status == RESULT_OK
    oct_start, _ = playground_month_bounds(OCT_1)
    before_capacity = roster.peek_capacity(USER, free, now=OCT_1)
    before_active = {i.law_id for i in roster.active_roster_items(USER, now=OCT_1)}
    before_ledger = roster.choice_law_ids(USER)
    assert roster._repo.get_period(USER, oct_start) is None

    rows = selection_rows("ndps", ["1"], entire=False, act=require_playground_law("ndps"))
    real = membership_and_selection_writer(overlay, USER, "ndps", rows)

    def failing(c):
        real(c)
        raise sqlite3.OperationalError("simulated failure writing the selection")

    with pytest.raises(sqlite3.OperationalError) as info:
        roster.confirm_add_law(USER, "ndps", free, now=OCT_1, within=failing)
    assert save_was_rolled_back(info.value)

    october = roster._repo.get_period(USER, oct_start)
    assert october is not None and october.status == "active"  # bookkeeping row only
    items = {i.law_id: i for i in roster._repo.list_items(USER, oct_start)}
    assert set(items) == {"stub-1"} and items["stub-1"].origin == "carry_forward"
    after_capacity = roster.peek_capacity(USER, free, now=OCT_1)
    assert (after_capacity.used, after_capacity.remaining) == (before_capacity.used, before_capacity.remaining)
    assert {i.law_id for i in roster.active_roster_items(USER, now=OCT_1)} == before_active == {"stub-1"}
    assert roster.choice_law_ids(USER) == before_ledger == frozenset({"stub-1"})
    assert overlay.get_item(USER, "ndps") is None and overlay.list_selection(USER, "ndps") == []
    # The retry on the surviving bucket spends exactly one choice.
    out = roster.confirm_add_law(USER, "ndps", free, now=OCT_1, within=real)
    assert out.status == RESULT_OK and out.within_applied
    assert roster.choice_law_ids(USER) == frozenset({"stub-1", "ndps"})


# ------------------------------------------------- Calendar and Visualize


def test_personal_task_create_requires_plus_under_choices(tmp_path: Path):
    def create(client: TestClient):
        return client.post(
            "/api/study-materials",
            data={"title": "Notes", "studied_on": "2026-09-16"},
            headers={"X-Study-Token": client.app.state.study_token},
        )

    free = _client(tmp_path / "cal-free")
    resp = create(free)
    assert resp.status_code == 403
    assert "Plus" in resp.text

    plus = _client(tmp_path / "cal-plus")
    _subscribe(plus, tier="plus")
    assert create(plus).status_code == 200

    legacy = _client(tmp_path / "cal-monthly", tier_model="monthly")
    assert create(legacy).status_code == 200  # unchanged under monthly


def test_visual_explainer_is_pro_only_under_choices(tmp_path: Path):
    plus = _client(tmp_path / "vis-plus")
    _subscribe(plus, tier="plus")
    resp = plus.get("/api/explainers/82")
    assert resp.status_code == 403
    assert resp.json()["error"] == "visual_explainers_locked"
    assert "<svg" not in resp.text

    pro = _client(tmp_path / "vis-pro")
    _subscribe(pro, tier="pro")
    assert pro.get("/api/explainers/82").status_code == 200

    legacy_max = _client(tmp_path / "vis-max")
    _subscribe(legacy_max, tier="max")
    assert legacy_max.get("/api/explainers/82").status_code == 200

    monthly_plus = _client(tmp_path / "vis-monthly", tier_model="monthly")
    _subscribe(monthly_plus, tier="plus")
    assert monthly_plus.get("/api/explainers/82").status_code == 200

    guest = _client(tmp_path / "vis-guest", sign_in=False)
    assert guest.get("/api/explainers/82").status_code == 403


# ------------------------------------------------------------- catalogue


@pytest.mark.parametrize("model", ["choices", "monthly"])
def test_max_is_not_purchasable_under_either_model(tmp_path: Path, model: str):
    """B1-F09 (plan §4.6, not flag-gated): Max is absent from every new
    purchase offer and refused at checkout and plan change under both
    tier models. Existing Max subscriptions stay recognised (next test)."""

    client = _client(tmp_path / f"cat-{model}", tier_model=model)
    page = client.get("/billing/subscriptions")
    assert page.status_code == 200
    assert "Subscribe to Max" not in page.text and "₹1,199" not in page.text
    assert "Subscribe to Plus" in page.text and "Subscribe to Pro" in page.text
    payload = dict(_csrf(client))
    payload["tier"] = "max"
    resp = client.post("/billing/subscriptions/create", data=payload, follow_redirects=False)
    assert resp.status_code == 303
    assert "invalid_tier" in (resp.headers.get("location") or "")
    gate = client.get("/playground?stage=plans&tier=max")
    assert gate.status_code == 200
    assert "Subscribe to Max" not in gate.text and "Upgrade to Max" not in gate.text
    assert "₹1199" not in gate.text and "₹1,199" not in gate.text

    _subscribe(client, tier="plus")
    change = client.post("/billing/subscriptions/change", data={**_csrf(client), "tier": "max"}, follow_redirects=False)
    assert change.status_code == 303
    assert "invalid_tier" in (change.headers.get("location") or "")
    manage = client.get("/billing/subscriptions").text
    assert "Upgrade to Max" not in manage and "Subscribe to Max" not in manage


@pytest.mark.parametrize("model", ["choices", "monthly"])
def test_existing_max_subscription_stays_recognised(tmp_path: Path, model: str):
    """B1-F10: the purchase exclusion changes nothing for an account that
    already holds a Max subscription row."""

    client = _client(tmp_path / f"max-{model}", tier_model=model)
    _subscribe(client, tier="max")
    snapshot = client.app.state.entitlement_service.resolve(USER)
    assert snapshot.tier == "max" and snapshot.is_subscribed
    assert snapshot.playground_law_limit is None
    manage = client.get("/billing/subscriptions")
    assert manage.status_code == 200
    assert "Max" in manage.text  # current plan is named
    assert _add_entire(client, "ndps").status_code == 303


def test_legacy_max_row_still_resolves_under_choices(tmp_path: Path):
    client = _client(tmp_path / "legacy-max")
    _subscribe(client, tier="max")
    snapshot = client.app.state.entitlement_service.resolve(USER)
    assert snapshot.tier == "max" and snapshot.is_subscribed
    assert snapshot.playground_law_limit is None
    assert snapshot.can_add_personal_calendar_tasks is True
    assert snapshot.can_open_visual_explainers is True
    assert _add_entire(client, "ndps").status_code == 303


# -------------------------------------------------------------- devices


def test_free_account_is_never_registered_as_a_device(tmp_path: Path):
    client = _client(tmp_path / "device")
    assert client.get("/playground").status_code == 200
    assert _add_entire(client, "ndps").status_code == 303
    assert client.get(law_path("ndps")).status_code == 200
    devices = client.app.state.device_service
    repo = getattr(devices, "_repo", None) or getattr(devices, "repo", None)
    assert repo is not None
    assert repo.count_active(USER) == 0


# ---------------------------------------------------------- snapshot unit


def test_resolver_unit_matrix():
    class Ledger:
        def __init__(self, n: int) -> None:
            self.n = n

        def count_choices(self, _uid):
            return self.n

    for used, consume in ((0, True), (2, True), (3, False), (5, False)):
        snap = EntitlementService(choices=Ledger(used), tier_model="choices").resolve(USER)
        assert snap.can_open_playground is True
        assert snap.playground_choices_used == used
        assert snap.can_consume_new_playground_law is consume
        assert snap.playground_block_reason is None
        assert (snap.playground_consume_block_reason == BLOCK_FREE_CHOICES_EXHAUSTED) is (
            not consume
        )
    legacy = EntitlementService(choices=Ledger(3)).resolve(USER)
    assert legacy.tier_model == "monthly"
    assert legacy.can_open_playground is False
    assert legacy.playground_choice_limit is None
    assert legacy.can_add_personal_calendar_tasks is True
