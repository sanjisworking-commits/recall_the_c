"""Milestone 3B: Playground commercial HTTP gate. Not devices or roster."""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import InMemorySessionStore
from constitution_memorizer.entitlements.models import (
    BLOCK_NOT_SUBSCRIBED,
    BLOCK_PAID_PERIOD_ENDED,
    BLOCK_PAYMENT_HALTED,
    BLOCK_SUBSCRIPTION_PAUSED,
)
from constitution_memorizer.entitlements.service import EntitlementService
from constitution_memorizer.multiuser.settings import MultiUserSettings
from constitution_memorizer.playground.access import (
    PLAYGROUND_BILLING_PATH,
    PlaygroundAccess,
    playground_access,
)
from constitution_memorizer.playground.locators import section_locator
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
from constitution_memorizer.web import bare_acts
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.bare_acts import clear_bare_act_cache, get_bare_act

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
USER = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
NOW = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
PERIOD_START = datetime(2026, 9, 1, tzinfo=timezone.utc)
PERIOD_END = datetime(2026, 10, 1, tzinfo=timezone.utc)
DEEP_LINKS = (
    "/playground",
    law_path("ndps"),
    sections_path("ndps"),
    learn_path("ndps", "8"),
)
ROOT = Path(__file__).resolve().parents[1]


class BoomProvider:
    def fetch_subscription(self, *a, **k):  # pragma: no cover
        raise AssertionError("Playground gate must not call Razorpay")


class CountingSubscriptions:
    def __init__(self, inner) -> None:
        self.inner = inner
        self.calls = 0

    def get_current_subscription(self, user_id):
        self.calls += 1
        return self.inner.get_current_subscription(user_id)

    def __getattr__(self, name):
        return getattr(self.inner, name)


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
        ARTICLE_ENTITLEMENTS_ENABLED="true",
        RELEVANT_LAWS_ENABLED="true",
    )


def _authed_client(tmp_path: Path) -> tuple[TestClient, ProgressRepository]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    conn = open_progress_db(tmp_path / "progress.db")
    repo = ProgressRepository(conn)
    provider = FakeAuthProvider()
    provider.seed_google_user(
        user_id=USER, email="m3b@example.com", display_name="M3B User"
    )
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "unused.db",
        multiuser=True,
        multiuser_settings=_mu_settings(),
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
    service = getattr(app.state, "subscription_service", None)
    if service is not None:
        service._client = BoomProvider()  # type: ignore[attr-defined]
    return client, repo


def _guest_client(tmp_path: Path) -> TestClient:
    tmp_path.mkdir(parents=True, exist_ok=True)
    conn = open_progress_db(tmp_path / "progress.db")
    return TestClient(
        create_app(
            units_path=MINI_UNITS,
            db_path=tmp_path / "unused.db",
            multiuser=True,
            multiuser_settings=_mu_settings(),
            auth_provider=FakeAuthProvider(),
            session_store=InMemorySessionStore(),
            progress_repo=ProgressRepository(conn),
        )
    )


def _csrf(client: TestClient) -> dict[str, str]:
    token = client.cookies.get("rtc_csrf") or ""
    return {"csrf_token": token} if token else {}


def _mutate(client: TestClient, path: str, **fields):
    payload = dict(fields)
    payload.update(_csrf(client))
    return client.post(path, data=payload, follow_redirects=False)


def _add_law(client: TestClient, law_id: str):
    preview = _mutate(client, add_path(law_id))
    location = preview.headers.get("location") or ""
    if preview.status_code == 303 and "/playground/roster" in location:
        return _mutate(client, add_path(law_id), confirm="add")
    return preview


def _consume_on_roster(client: TestClient, law_id: str = "ndps") -> None:
    roster = client.app.state.roster
    snap = client.app.state.entitlement_service.resolve(USER, now=NOW)
    result = roster.confirm_add_law(
        USER,
        law_id,
        snap,
        now=NOW,
        can_consume_new_law=True,
    )
    assert result.ok


def _add_subscription(
    client: TestClient,
    *,
    tier: str,
    status: str,
    cancel_at_period_end: bool = False,
    period_start: datetime = PERIOD_START,
    period_end: datetime = PERIOD_END,
):
    return client.app.state.subscriptions.create_subscription_record(
        USER,
        tier=tier,
        status=status,
        billing_period_start=period_start,
        billing_period_end=period_end,
        cancel_at_period_end=cancel_at_period_end,
        is_current=True,
    )


def _set_status(client: TestClient, subscription_id: str, status: str) -> None:
    client.app.state.subscriptions.update_subscription_state(
        USER, subscription_id, status=status
    )


def _seed_admin(repo: ProgressRepository) -> None:
    repo.conn.execute(
        "INSERT INTO user_roles (user_id, role, created_at) VALUES (?, 'admin', ?)",
        (str(USER), NOW.isoformat()),
    )
    repo.conn.commit()


def _seed_legacy(repo: ProgressRepository, *, ends_at: datetime) -> None:
    repo.create_billing_order(
        USER, order_id="order_legacy", plan_days=365, amount_paise=99900
    )
    assert repo.mark_billing_order_paid(
        USER,
        order_id="order_legacy",
        payment_id="pay_legacy",
        grant_id="grant_legacy",
        access_ends_at=ends_at.isoformat(),
    )


def _seed_ndps_overlay(client: TestClient, *, number: str = "1") -> None:
    playground = client.app.state.playground
    activate_law(playground, USER, "ndps")
    act = get_bare_act("ndps")
    assert act is not None
    rows = selection_rows("ndps", [number], entire=False, act=act)
    playground.replace_selection(USER, "ndps", rows)
    loc = section_locator("ndps", number)
    section = act.section(number)
    assert section is not None
    playground.complete_cloze(
        USER,
        "ndps",
        loc.value,
        source_version="1",
        source_hash=source_hash(section),
        as_of=NOW.date(),
        live_hash=source_hash(section),
    )


def _overlay_fingerprint(client: TestClient) -> tuple:
    playground = client.app.state.playground
    items = playground.list_items(USER)
    selections = playground.list_selection(USER, "ndps")
    progress = playground.list_progress(USER, "ndps")
    return (
        [(row.law_id, row.status, row.law_source_hash) for row in items],
        [(row.source_locator, row.source_hash) for row in selections],
        [
            (row.source_locator, row.times_completed, row.source_hash, row.status)
            for row in progress
        ],
    )


def _hydrate_spy(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    hydrated: list[str] = []
    real = bare_acts._load_cached

    def wrapped(slug: str, identity: str):
        hydrated.append(slug)
        return real(slug, identity)

    wrapped.cache_clear = real.cache_clear  # type: ignore[attr-defined]
    monkeypatch.setattr(bare_acts, "_load_cached", wrapped)
    return hydrated


def _assert_subscribe_gate(response) -> None:
    assert response.status_code == 200
    assert 'data-playground-gate="not_subscribed"' in response.text
    assert "Subscribe to use Playground" in response.text
    assert "Playground is included with Plus, Pro, or Max." in response.text
    assert "View Playground plans" in response.text
    assert PLAYGROUND_BILLING_PATH in response.text
    assert "Sign in to use Playground" not in response.text


def _assert_constitution_open(client: TestClient) -> None:
    page = client.get("/learn/clause-1?mode=type")
    assert page.status_code == 200
    assert "mode_locked" not in page.text
    recite = client.get("/learn/clause-1?mode=recite")
    assert recite.status_code == 200


def _assert_laws_open(client: TestClient) -> None:
    assert client.get("/laws").status_code == 200
    assert client.get("/laws/ndps").status_code == 200
    assert client.get("/laws/ndps/section/1").status_code == 200


# --------------------------------------------------------------------------- #
# Guest                                                                        #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("path", DEEP_LINKS)
def test_guest_playground_gets_redirect_to_login(tmp_path: Path, path: str):
    client = _guest_client(tmp_path)
    response = client.get(path, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == f"/login?next={path}"
    assert "/billing/subscriptions" not in response.headers["location"]
    assert "Subscribe" not in (response.text or "")


def test_guest_playground_mutations_go_to_login(tmp_path: Path):
    client = _guest_client(tmp_path)
    added = _mutate(client, add_path("ndps"))
    assert added.status_code == 303
    assert added.headers["location"] == "/login?next=/laws/ndps"
    saved = _mutate(client, sections_path("ndps"), section="1")
    assert saved.status_code == 303
    assert saved.headers["location"] == f"/login?next={sections_path('ndps')}"
    done = client.post(learn_complete_path("ndps", "1"), follow_redirects=False)
    assert done.status_code == 401
    assert done.json()["error"] == "auth_required"
    assert client.app.state.playground.get_item(USER, "ndps") is None


def test_guest_blocked_deep_link_hydrates_zero_acts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    clear_bare_act_cache()
    hydrated = _hydrate_spy(monkeypatch)
    client = _guest_client(tmp_path)
    before = list(hydrated)
    client.get(learn_path("ndps", "8"), follow_redirects=False)
    _mutate(client, add_path("ndps"))
    assert hydrated == before


# --------------------------------------------------------------------------- #
# Free signed-in                                                               #
# --------------------------------------------------------------------------- #
def test_free_account_playground_is_subscribe_gate(tmp_path: Path):
    client, _repo = _authed_client(tmp_path)
    home = client.get("/playground", follow_redirects=False)
    _assert_subscribe_gate(home)
    added = _mutate(client, add_path("ndps"))
    assert added.status_code == 303
    assert added.headers["location"] == "/playground"
    assert client.app.state.playground.get_item(USER, "ndps") is None
    snap = client.app.state.entitlement_service.resolve(USER, now=NOW)
    assert snap.can_open_playground is False
    assert snap.playground_block_reason == BLOCK_NOT_SUBSCRIBED


@pytest.mark.parametrize("path", DEEP_LINKS)
def test_free_account_deep_links_are_gated(tmp_path: Path, path: str):
    client, _repo = _authed_client(tmp_path)
    response = client.get(path, follow_redirects=False)
    _assert_subscribe_gate(response)


def test_free_account_blocked_deep_link_hydrates_zero_acts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    client, _repo = _authed_client(tmp_path)
    clear_bare_act_cache()
    hydrated = _hydrate_spy(monkeypatch)
    before = list(hydrated)
    for path in DEEP_LINKS:
        client.get(path, follow_redirects=False)
    _mutate(client, add_path("ndps"))
    _mutate(client, sections_path("ndps"), section="1")
    client.post(learn_complete_path("ndps", "1"), follow_redirects=False)
    assert hydrated == before
    assert client.app.state.playground.list_items(USER) == []


def test_free_account_snapshot_is_memoized_on_playground_request(tmp_path: Path):
    client, _repo = _authed_client(tmp_path)
    inner = client.app.state.subscriptions
    counting = CountingSubscriptions(inner)
    client.app.state.subscriptions = counting
    client.app.state.entitlement_service = EntitlementService(
        subscriptions=counting,
        charges=client.app.state.subscription_charges,
        access_store=client.app.state.access_store,
        legacy_store=client.app.state.engine.repo,
    )
    client.get("/playground")
    assert counting.calls == 1


# --------------------------------------------------------------------------- #
# Active / pending / halted / paused / period-ended / legacy / admin           #
# --------------------------------------------------------------------------- #
def test_active_subscriber_keeps_existing_playground_proof(tmp_path: Path):
    client, _repo = _authed_client(tmp_path)
    _add_subscription(client, tier="pro", status="active")
    added = _add_law(client, "ndps")
    assert added.status_code == 303
    assert added.headers["location"] == sections_path("ndps")
    saved = _mutate(client, sections_path("ndps"), section="1")
    assert saved.status_code == 303
    home = client.get("/playground")
    assert home.status_code == 200
    assert "My Playground" in home.text
    assert "Subscribe to use Playground" not in home.text
    workspace = client.get(law_path("ndps"))
    assert workspace.status_code == 200
    page = client.get(learn_path("ndps", "1"))
    assert page.status_code == 200
    assert "data-playground-cloze" in page.text
    done = client.post(learn_complete_path("ndps", "1"))
    assert done.status_code == 200
    assert done.json()["ok"] is True
    snap = client.app.state.entitlement_service.resolve(USER, now=NOW)
    assert snap.can_open_playground is True
    assert snap.can_consume_new_playground_law is True
    assert snap.tier == "pro"
    assert snap.playground_law_limit == 30


def test_pending_opens_current_roster_and_blocks_historical_overlay(tmp_path: Path):
    client, _repo = _authed_client(tmp_path)
    _add_subscription(client, tier="plus", status="active")
    _seed_ndps_overlay(client)
    _consume_on_roster(client, "ndps")
    from constitution_memorizer.playground.service import activate_law, selection_rows
    from constitution_memorizer.playground.source import source_hash
    from constitution_memorizer.web.bare_acts import get_bare_act

    playground = client.app.state.playground
    activate_law(playground, USER, "bns")
    act = get_bare_act("bns")
    assert act is not None
    playground.replace_selection(
        USER, "bns", selection_rows("bns", ["1"], entire=False, act=act)
    )
    loc = section_locator("bns", "1")
    section = act.section("1")
    assert section is not None
    playground.complete_cloze(
        USER,
        "bns",
        loc.value,
        source_version="1",
        source_hash=source_hash(section),
        as_of=NOW.date(),
        live_hash=source_hash(section),
    )
    sub = client.app.state.subscriptions.get_current_subscription(USER)
    _set_status(client, sub.id, "pending")
    home = client.get("/playground")
    assert home.status_code == 200
    assert "My Playground" in home.text
    workspace = client.get(law_path("ndps"))
    assert workspace.status_code == 200
    learn = client.get(learn_path("ndps", "1"))
    assert learn.status_code == 200
    done = client.post(learn_complete_path("ndps", "1"))
    assert done.status_code == 200
    assert done.json()["ok"] is True
    historical = client.get(law_path("bns"), follow_redirects=False)
    assert historical.status_code == 200
    assert "new_law_temporarily_unavailable" in historical.text or (
        "temporarily unavailable" in historical.text.lower()
    )
    added = _mutate(client, add_path("bns"), confirm="add")
    assert added.status_code == 303
    assert client.app.state.roster.is_law_active_this_period(USER, "bns") is False
    snap = client.app.state.entitlement_service.resolve(USER, now=NOW)
    assert snap.can_open_playground is True
    assert snap.can_consume_new_playground_law is False
    assert snap.playground_block_reason is None


def test_pending_section_save_bypass_hydrates_zero_acts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    client, _repo = _authed_client(tmp_path)
    _add_subscription(client, tier="plus", status="pending")
    clear_bare_act_cache()
    hydrated = _hydrate_spy(monkeypatch)
    before = list(hydrated)
    _mutate(client, sections_path("ndps"), section="1")
    assert hydrated == before
    assert client.app.state.playground.get_item(USER, "ndps") is None


def test_halted_blocks_playground_with_payment_copy(tmp_path: Path):
    client, _repo = _authed_client(tmp_path)
    _add_subscription(client, tier="max", status="halted")
    home = client.get("/playground")
    assert home.status_code == 200
    assert 'data-playground-gate="payment_halted"' in home.text
    assert "Payment retries have stopped" in home.text
    assert "Manage subscription" in home.text
    assert "Subscribe to use Playground" not in home.text
    assert PLAYGROUND_BILLING_PATH in home.text
    snap = client.app.state.entitlement_service.resolve(USER, now=NOW)
    assert snap.playground_block_reason == BLOCK_PAYMENT_HALTED
    _assert_constitution_open(client)
    _assert_laws_open(client)


def test_paused_blocks_playground_with_paused_copy(tmp_path: Path):
    client, _repo = _authed_client(tmp_path)
    _add_subscription(client, tier="pro", status="paused")
    home = client.get("/playground")
    assert 'data-playground-gate="subscription_paused"' in home.text
    assert "Playground subscription is paused" in home.text
    assert "Subscribe to use Playground" not in home.text
    snap = client.app.state.entitlement_service.resolve(USER, now=NOW)
    assert snap.playground_block_reason == BLOCK_SUBSCRIPTION_PAUSED
    _assert_constitution_open(client)


def test_paid_period_ended_blocks_all_playground_surfaces(tmp_path: Path):
    client, _repo = _authed_client(tmp_path)
    _seed_ndps_overlay(client)
    sub = _add_subscription(client, tier="plus", status="active")
    charge = client.app.state.subscription_charges.upsert_charge(
        provider_payment_id="pay_refund",
        user_subscription_id=sub.id,
        billing_period_start=PERIOD_START,
        billing_period_end=PERIOD_END,
        refund_status="full",
    )
    assert charge.access_effect == "period_ended"
    home = client.get("/playground")
    assert 'data-playground-gate="paid_period_ended"' in home.text
    assert "Playground access for this paid period has ended" in home.text
    learn = client.get(learn_path("ndps", "1"), follow_redirects=False)
    assert 'data-playground-gate="paid_period_ended"' in learn.text
    done = client.post(learn_complete_path("ndps", "1"))
    assert done.status_code == 403
    assert done.json()["ok"] is False
    added = _mutate(client, add_path("bns"))
    assert added.status_code == 303
    stored = client.app.state.subscriptions.get_current_subscription(USER)
    assert stored is not None and stored.status == "active"
    snap = client.app.state.entitlement_service.resolve(USER, now=NOW)
    assert snap.playground_block_reason == BLOCK_PAID_PERIOD_ENDED
    assert snap.subscription_status == "active"
    assert snap.tier == "plus"
    _assert_constitution_open(client)


def test_legacy_active_gets_subscribe_gate_not_a_tier(tmp_path: Path):
    client, repo = _authed_client(tmp_path)
    ends = NOW + timedelta(days=300)
    _seed_legacy(repo, ends_at=ends)
    home = client.get("/playground")
    _assert_subscribe_gate(home)
    added = _mutate(client, add_path("ndps"))
    assert added.status_code == 303
    assert client.app.state.playground.get_item(USER, "ndps") is None
    snap = client.app.state.entitlement_service.resolve(
        USER, now=datetime.now(timezone.utc)
    )
    assert snap.legacy_status == "legacy_active"
    assert snap.tier is None
    assert snap.can_open_playground is False
    assert client.app.state.subscriptions.get_current_subscription(USER) is None
    classified_end = repo.conn.execute(
        "SELECT ends_at FROM access_grants WHERE source = 'payment'"
    ).fetchone()
    assert ends.isoformat()[:19] in str(classified_end[0])
    _assert_constitution_open(client)
    _assert_laws_open(client)


def test_admin_without_subscription_is_allowed(tmp_path: Path):
    client, repo = _authed_client(tmp_path)
    _seed_admin(repo)
    home = client.get("/playground")
    assert home.status_code == 200
    assert "My Playground" in home.text
    added = _add_law(client, "ndps")
    assert added.status_code == 303
    assert client.app.state.playground.get_item(USER, "ndps") is not None
    snap = client.app.state.entitlement_service.resolve(USER, now=NOW)
    assert snap.admin_override is True
    assert snap.tier is None
    assert snap.is_subscribed is False
    assert snap.playground_law_limit is None
    assert snap.can_open_playground is True
    assert snap.can_consume_new_playground_law is True
    assert client.app.state.subscriptions.get_current_subscription(USER) is None


@pytest.mark.parametrize(
    ("tier", "limit"),
    (("plus", 10), ("pro", 30), ("max", None)),
)
def test_active_tiers_have_identical_playground_learning(
    tmp_path: Path, tier: str, limit: int | None
):
    client, _repo = _authed_client(tmp_path)
    _add_subscription(client, tier=tier, status="active")
    added = _add_law(client, "ndps")
    assert added.status_code == 303
    saved = _mutate(client, sections_path("ndps"), section="1")
    assert saved.status_code == 303
    home = client.get("/playground")
    assert home.status_code == 200
    assert "My Playground" in home.text
    workspace = client.get(law_path("ndps"))
    assert workspace.status_code == 200
    select = client.get(sections_path("ndps"))
    assert select.status_code == 200
    learn = client.get(learn_path("ndps", "1"))
    assert learn.status_code == 200
    done = client.post(learn_complete_path("ndps", "1"))
    assert done.status_code == 200
    assert done.json()["ok"] is True
    snap = client.app.state.entitlement_service.resolve(USER, now=NOW)
    assert snap.playground_law_limit == limit
    assert snap.tier == tier


def test_overlay_survives_halt_and_resumes_when_active(tmp_path: Path):
    client, _repo = _authed_client(tmp_path)
    sub = _add_subscription(client, tier="plus", status="active")
    _seed_ndps_overlay(client)
    _consume_on_roster(client, "ndps")
    before = _overlay_fingerprint(client)
    _set_status(client, sub.id, "halted")
    home = client.get("/playground")
    assert "Payment retries have stopped" in home.text
    done = client.post(learn_complete_path("ndps", "1"))
    assert done.status_code == 403
    assert _overlay_fingerprint(client) == before
    _set_status(client, sub.id, "active")
    learn = client.get(learn_path("ndps", "1"))
    assert learn.status_code == 200
    assert _overlay_fingerprint(client) == before
    again = client.post(learn_complete_path("ndps", "1"))
    assert again.status_code == 200
    resumed = _overlay_fingerprint(client)
    assert resumed[0] == before[0]
    assert resumed[1] == before[1]


def test_overlay_survives_pause_and_resumes(tmp_path: Path):
    client, _repo = _authed_client(tmp_path)
    sub = _add_subscription(client, tier="pro", status="active")
    _seed_ndps_overlay(client)
    _consume_on_roster(client, "ndps")
    before = _overlay_fingerprint(client)
    _set_status(client, sub.id, "paused")
    assert "paused" in client.get("/playground").text.lower()
    assert _overlay_fingerprint(client) == before
    _set_status(client, sub.id, "active")
    assert client.get(learn_path("ndps", "1")).status_code == 200
    assert _overlay_fingerprint(client) == before


@pytest.mark.parametrize("status", ("created", "cancelled", "completed", "expired"))
def test_terminal_provider_states_are_centrally_blocked(tmp_path: Path, status: str):
    client, _repo = _authed_client(tmp_path)
    _add_subscription(client, tier="plus", status=status)
    home = client.get("/playground")
    _assert_subscribe_gate(home)
    snap = client.app.state.entitlement_service.resolve(USER, now=NOW)
    assert snap.can_open_playground is False


def test_active_and_admin_add_succeed_where_pending_is_blocked(tmp_path: Path):
    pending_dir = tmp_path / "pending"
    pending_dir.mkdir()
    pending, _repo = _authed_client(pending_dir)
    _add_subscription(pending, tier="plus", status="pending")
    _mutate(pending, add_path("ndps"))
    assert pending.app.state.playground.get_item(USER, "ndps") is None

    active_dir = tmp_path / "active"
    active_dir.mkdir()
    active, _repo2 = _authed_client(active_dir)
    _add_subscription(active, tier="plus", status="active")
    _add_law(active, "ndps")
    assert active.app.state.playground.get_item(USER, "ndps") is not None


def test_home_still_hydrates_zero_acts_for_subscriber(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    client, _repo = _authed_client(tmp_path)
    _add_subscription(client, tier="max", status="active")
    _seed_ndps_overlay(client)
    clear_bare_act_cache()
    hydrated = _hydrate_spy(monkeypatch)
    client.get("/playground")
    assert hydrated == []


def test_workspace_hydrates_only_requested_act(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    client, _repo = _authed_client(tmp_path)
    _add_subscription(client, tier="pro", status="active")
    _seed_ndps_overlay(client)
    _consume_on_roster(client, "ndps")
    clear_bare_act_cache()
    hydrated = _hydrate_spy(monkeypatch)
    client.get(law_path("ndps"))
    assert "ndps" in hydrated
    assert "bns" not in hydrated
    assert "bnss" not in hydrated


def test_constitution_and_laws_remain_open_when_playground_is_blocked(
    tmp_path: Path,
):
    cases = tmp_path
    free, _r1 = _authed_client(cases / "free")
    halted, _r2 = _authed_client(cases / "halted")
    _add_subscription(halted, tier="max", status="halted")
    paused, _r3 = _authed_client(cases / "paused")
    _add_subscription(paused, tier="plus", status="paused")
    legacy, repo = _authed_client(cases / "legacy")
    _seed_legacy(repo, ends_at=NOW + timedelta(days=10))
    for client in (free, halted, paused, legacy):
        _assert_constitution_open(client)
        _assert_laws_open(client)


def test_playground_modules_do_not_call_provider_or_rederive_status():
    access_src = Path(ROOT / "src/constitution_memorizer/playground/access.py").read_text(
        encoding="utf-8"
    )
    routes_src = Path(ROOT / "src/constitution_memorizer/playground/routes.py").read_text(
        encoding="utf-8"
    )
    for source in (access_src, routes_src):
        assert "RazorpaySubscriptionsClient" not in source
        assert "fetch_subscription" not in source
        assert "get_current_subscription" not in source
        assert "FROM user_subscription" not in source
        assert "if status ==" not in source
        assert 'if tier ==' not in source
    service_src = inspect.getsource(EntitlementService)
    assert "RazorpaySubscriptionsClient" not in service_src


def test_m3b_gate_does_not_query_subscription_tables():
    access_src = (ROOT / "src/constitution_memorizer/playground/access.py").read_text(
        encoding="utf-8"
    )
    assert "PLAYGROUND_DEVICE_LIMIT" not in access_src
    assert "FROM user_subscription" not in access_src
    assert "RazorpaySubscriptionsClient" not in access_src


def test_local_owner_access_is_open_without_snapshot():
    from types import SimpleNamespace

    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(multiuser_enabled=False)),
        state=SimpleNamespace(current_user=None),
    )
    access = playground_access(request)  # type: ignore[arg-type]
    assert isinstance(access, PlaygroundAccess)
    assert access.local_owner is True
    assert access.can_open is True
    assert access.can_consume_new_law is True
    assert access.snapshot is None
