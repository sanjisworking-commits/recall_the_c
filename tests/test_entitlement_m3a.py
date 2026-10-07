"""Milestone 3A: EntitlementService + Constitution inversion. Not Playground HTTP."""

from __future__ import annotations

import inspect
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import InMemorySessionStore
from constitution_memorizer.entitlements.dependencies import get_entitlement_snapshot
from constitution_memorizer.entitlements.models import (
    BLOCK_NOT_SUBSCRIBED,
    BLOCK_PAID_PERIOD_ENDED,
    BLOCK_PAYMENT_HALTED,
    BLOCK_SIGN_IN_REQUIRED,
    BLOCK_SUBSCRIPTION_PAUSED,
    CONSTITUTION_ACCESS_FULL,
    CONSTITUTION_ACCESS_GUEST_EXPLORE,
    LEGACY_STATUS_ACTIVE,
    LEGACY_STATUS_EXPIRED,
    EntitlementSnapshot,
)
from constitution_memorizer.entitlements.service import EntitlementService
from constitution_memorizer.multiuser.settings import MultiUserSettings
from constitution_memorizer.progress.db import open_progress_db
from constitution_memorizer.progress.repository import LEARN_MODES, ProgressRepository
from constitution_memorizer.subscriptions.charge_repository import (
    SqliteChargeRepository,
    access_effect_for_billing_period,
)
from constitution_memorizer.subscriptions.db import ensure_sqlite_schema
from constitution_memorizer.subscriptions.models import SubscriptionCharge
from constitution_memorizer.subscriptions.repository import SqliteSubscriptionRepository
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.entitlements import ALL_MODES, is_subscribed

from tests.quiz_helpers import complete_all_modes

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
USER = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
NOW = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
PERIOD_START = datetime(2026, 9, 1, tzinfo=timezone.utc)
PERIOD_END = datetime(2026, 10, 1, tzinfo=timezone.utc)
JSON_HEADERS = {"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"}


class Boom:
    """Explodes on any commerce/legacy/admin read — guests must never hit this."""

    def get_current_subscription(self, user_id):  # pragma: no cover
        raise AssertionError("guest must not read user_subscription")

    def get_charge_access_effect_for_billing_period(self, *a, **k):  # pragma: no cover
        raise AssertionError("guest must not read subscription_charge")

    def list_payment_access_grants(self, user_id):  # pragma: no cover
        raise AssertionError("guest must not read legacy payment grants")

    def is_admin(self, user_id):  # pragma: no cover
        raise AssertionError("guest must not read admin roles")

    def fetch_subscription(self, *a, **k):  # pragma: no cover
        raise AssertionError("entitlement resolve must not call Razorpay")


class CountingSubscriptions:
    def __init__(self, inner: SqliteSubscriptionRepository) -> None:
        self.inner = inner
        self.calls = 0

    def get_current_subscription(self, user_id):
        self.calls += 1
        return self.inner.get_current_subscription(user_id)


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
    conn = open_progress_db(tmp_path / "progress.db")
    repo = ProgressRepository(conn)
    provider = FakeAuthProvider()
    provider.seed_google_user(
        user_id=USER, email="m3a@example.com", display_name="M3A User"
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
    return client, repo


def _guest_client(tmp_path: Path) -> TestClient:
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


def _service_for_app(client: TestClient) -> EntitlementService:
    return client.app.state.entitlement_service


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


def _add_period_charge(
    client: TestClient,
    subscription_id: str,
    *,
    refund_status: str | None = None,
    dispute_status: str | None = None,
    period_start: datetime = PERIOD_START,
    period_end: datetime = PERIOD_END,
    payment_id: str = "pay_period",
):
    return client.app.state.subscription_charges.upsert_charge(
        provider_payment_id=payment_id,
        user_subscription_id=subscription_id,
        billing_period_start=period_start,
        billing_period_end=period_end,
        refund_status=refund_status,
        dispute_status=dispute_status,
        amount_paise=19900,
        currency="INR",
    )


def _seed_admin(repo: ProgressRepository) -> None:
    repo.conn.execute(
        "INSERT INTO user_roles (user_id, role, created_at) VALUES (?, 'admin', ?)",
        (str(USER), NOW.isoformat()),
    )
    repo.conn.commit()


def _seed_legacy(
    repo: ProgressRepository, *, ends_at: datetime, grant_id: str = "grant_legacy"
) -> None:
    repo.create_billing_order(
        USER, order_id="order_legacy", plan_days=365, amount_paise=99900
    )
    assert repo.mark_billing_order_paid(
        USER,
        order_id="order_legacy",
        payment_id="pay_legacy",
        grant_id=grant_id,
        access_ends_at=ends_at.isoformat(),
    )


def _assert_full_constitution(snapshot: EntitlementSnapshot) -> None:
    assert snapshot.can_use_constitution_learn is True
    assert snapshot.constitution_access == CONSTITUTION_ACCESS_FULL
    assert snapshot.can_read_laws is True


def _assert_learn_open(client: TestClient) -> None:
    page = client.get("/learn/clause-1")
    assert page.status_code == 200
    assert 'data-locked-modes=""' in page.text
    assert "Type 🔒" not in page.text
    assert "Recite 🔒" not in page.text
    assert "Your 3 Free Articles are in use" not in page.text
    assert "Add Article 20 to your Free Articles?" not in page.text
    for mode in LEARN_MODES:
        resp = client.get(f"/learn/clause-1?mode={mode}")
        assert resp.status_code == 200, mode
        assert "mode_locked" not in resp.text


def _complete_and_done(client: TestClient, repo: ProgressRepository) -> None:
    complete_all_modes(client, MINI_UNITS, "clause-1")
    for mode in ("cloze", "letters", "type", "recite"):
        seen = client.post(
            "/learn/clause-1/seen", data={"mode": mode}, headers=JSON_HEADERS
        )
        assert seen.status_code == 200, mode
        assert seen.json()["persisted"] is True
        assert seen.json().get("error") != "mode_locked"
    persisted = repo.modes_seen(USER, "clause-1")
    assert {"type", "recite"} <= persisted
    done = client.post("/learn/clause-1/done", headers=JSON_HEADERS)
    assert done.status_code == 200
    assert done.json()["ok"] is True
    assert "claim_required" not in done.text
    assert "subscription_required" not in done.text
    progress = repo.get_progress(USER, "clause-1")
    assert progress is not None and progress.times_completed == 1


# --------------------------------------------------------------------------- #
# Pure snapshot matrix                                                         #
# --------------------------------------------------------------------------- #
def test_guest_snapshot_is_constant_and_reads_nothing():
    boom = Boom()
    service = EntitlementService(
        subscriptions=boom,
        charges=boom,
        access_store=boom,
        legacy_store=boom,
    )
    snap = service.resolve(None, now=NOW)
    assert snap == EntitlementSnapshot(
        is_authenticated=False,
        subscription_status=None,
        tier=None,
        is_subscribed=False,
        admin_override=False,
        can_use_constitution_learn=True,
        constitution_access=CONSTITUTION_ACCESS_GUEST_EXPLORE,
        can_read_laws=True,
        can_open_playground=False,
        can_consume_new_playground_law=False,
        playground_law_limit=None,
        playground_block_reason=BLOCK_SIGN_IN_REQUIRED,
        billing_period_start=None,
        billing_period_end=None,
        legacy_status=None,
    )
    assert snap.is_subscribed is False


def test_no_subscription_is_full_constitution_not_playground(tmp_path: Path):
    client, _repo = _authed_client(tmp_path)
    snap = _service_for_app(client).resolve(USER, now=NOW)
    _assert_full_constitution(snap)
    assert snap.is_authenticated is True
    assert snap.subscription_status is None
    assert snap.tier is None
    assert snap.is_subscribed is False
    assert snap.admin_override is False
    assert snap.can_open_playground is False
    assert snap.can_consume_new_playground_law is False
    assert snap.playground_law_limit is None
    assert snap.playground_block_reason == BLOCK_NOT_SUBSCRIBED


def test_active_pro_snapshot_capacity_is_catalogue_only(tmp_path: Path):
    client, _repo = _authed_client(tmp_path)
    _add_subscription(client, tier="pro", status="active")
    snap = _service_for_app(client).resolve(USER, now=NOW)
    _assert_full_constitution(snap)
    assert snap.subscription_status == "active"
    assert snap.tier == "pro"
    assert snap.is_subscribed is True
    assert snap.can_open_playground is True
    assert snap.can_consume_new_playground_law is True
    assert snap.playground_law_limit == 30
    assert snap.playground_block_reason is None


def test_pending_plus_opens_existing_but_not_new_law(tmp_path: Path):
    client, _repo = _authed_client(tmp_path)
    _add_subscription(client, tier="plus", status="pending")
    snap = _service_for_app(client).resolve(USER, now=NOW)
    _assert_full_constitution(snap)
    assert snap.is_subscribed is True
    assert snap.can_open_playground is True
    assert snap.can_consume_new_playground_law is False
    assert snap.tier == "plus"
    assert snap.playground_law_limit == 10


def test_halted_and_paused_use_state_specific_block_reasons(tmp_path: Path):
    client, _repo = _authed_client(tmp_path)
    _add_subscription(client, tier="max", status="halted")
    halted = _service_for_app(client).resolve(USER, now=NOW)
    _assert_full_constitution(halted)
    assert halted.is_subscribed is False
    assert halted.can_open_playground is False
    assert halted.can_consume_new_playground_law is False
    assert halted.playground_block_reason == BLOCK_PAYMENT_HALTED
    assert halted.tier == "max"
    assert halted.playground_law_limit is None

    client.app.state.subscriptions.update_subscription_state(
        USER,
        client.app.state.subscriptions.get_current_subscription(USER).id,
        status="paused",
    )
    paused = _service_for_app(client).resolve(USER, now=NOW)
    assert paused.playground_block_reason == BLOCK_SUBSCRIPTION_PAUSED
    assert paused.is_subscribed is False


@pytest.mark.parametrize(
    "status",
    ("created", "authenticated", "cancelled", "completed", "expired"),
)
def test_non_capable_provider_statuses_are_not_subscribed(tmp_path: Path, status: str):
    client, _repo = _authed_client(tmp_path)
    _add_subscription(client, tier="plus", status=status)
    snap = _service_for_app(client).resolve(USER, now=NOW)
    _assert_full_constitution(snap)
    assert snap.is_subscribed is False
    assert snap.can_open_playground is False
    assert snap.playground_block_reason == BLOCK_NOT_SUBSCRIBED
    assert snap.subscription_status == status
    assert snap.tier == "plus"


def test_active_cancel_at_period_end_keeps_paid_capability(tmp_path: Path):
    client, _repo = _authed_client(tmp_path)
    _add_subscription(
        client, tier="pro", status="active", cancel_at_period_end=True
    )
    snap = _service_for_app(client).resolve(USER, now=NOW)
    assert snap.is_subscribed is True
    assert snap.can_open_playground is True
    assert snap.can_consume_new_playground_law is True
    assert snap.subscription_status == "active"


def test_stale_active_row_past_billing_end_does_not_extend_access(tmp_path: Path):
    client, _repo = _authed_client(tmp_path)
    _add_subscription(
        client,
        tier="plus",
        status="active",
        period_start=NOW - timedelta(days=40),
        period_end=NOW - timedelta(days=1),
    )
    snap = _service_for_app(client).resolve(USER, now=NOW)
    assert snap.subscription_status == "active"
    assert snap.tier == "plus"
    assert snap.is_subscribed is False
    assert snap.can_open_playground is False
    assert snap.playground_block_reason == BLOCK_PAID_PERIOD_ENDED


def test_current_period_full_refund_ends_playground_not_provider_status(
    tmp_path: Path,
):
    client, _repo = _authed_client(tmp_path)
    sub = _add_subscription(client, tier="plus", status="active")
    charge = _add_period_charge(client, sub.id, refund_status="full")
    assert charge.access_effect == "period_ended"
    assert charge.access_effect_reason == "full_refund"
    snap = _service_for_app(client).resolve(USER, now=NOW)
    _assert_full_constitution(snap)
    assert snap.subscription_status == "active"
    assert snap.tier == "plus"
    assert snap.is_subscribed is False
    assert snap.can_open_playground is False
    assert snap.can_consume_new_playground_law is False
    assert snap.playground_block_reason == BLOCK_PAID_PERIOD_ENDED
    stored = client.app.state.subscriptions.get_current_subscription(USER)
    assert stored is not None and stored.status == "active"


def test_current_period_dispute_lost_matches_refund_effect(tmp_path: Path):
    client, _repo = _authed_client(tmp_path)
    sub = _add_subscription(client, tier="plus", status="active")
    _add_period_charge(client, sub.id, dispute_status="lost")
    snap = _service_for_app(client).resolve(USER, now=NOW)
    assert snap.playground_block_reason == BLOCK_PAID_PERIOD_ENDED
    assert snap.subscription_status == "active"
    assert snap.tier == "plus"


def test_other_period_refund_does_not_end_current_period(tmp_path: Path):
    client, _repo = _authed_client(tmp_path)
    sub = _add_subscription(client, tier="pro", status="active")
    _add_period_charge(
        client,
        sub.id,
        refund_status="full",
        period_start=PERIOD_START - timedelta(days=31),
        period_end=PERIOD_START,
        payment_id="pay_old",
    )
    snap = _service_for_app(client).resolve(USER, now=NOW)
    assert snap.is_subscribed is True
    assert snap.can_open_playground is True
    assert snap.playground_block_reason is None


def test_legacy_active_is_not_a_playground_tier(tmp_path: Path):
    client, repo = _authed_client(tmp_path)
    ends = NOW + timedelta(days=300)
    _seed_legacy(repo, ends_at=ends)
    snap = _service_for_app(client).resolve(USER, now=datetime.now(timezone.utc))
    _assert_full_constitution(snap)
    assert snap.legacy_status == LEGACY_STATUS_ACTIVE
    assert snap.subscription_status == LEGACY_STATUS_ACTIVE
    assert snap.tier is None
    assert snap.is_subscribed is False
    assert snap.can_open_playground is False
    assert snap.admin_override is False
    assert client.app.state.subscriptions.get_current_subscription(USER) is None
    classified_end = repo.conn.execute(
        "SELECT ends_at FROM access_grants WHERE source = 'payment'"
    ).fetchone()
    assert classified_end is not None
    assert ends.isoformat()[:19] in str(classified_end[0])


def test_legacy_expired_retains_classification_without_tier(tmp_path: Path):
    client, repo = _authed_client(tmp_path)
    _seed_legacy(repo, ends_at=NOW - timedelta(days=1))
    snap = _service_for_app(client).resolve(USER, now=NOW)
    _assert_full_constitution(snap)
    assert snap.legacy_status == LEGACY_STATUS_EXPIRED
    assert snap.tier is None
    assert snap.is_subscribed is False
    assert snap.subscription_status is None


def test_admin_override_is_not_fake_max(tmp_path: Path):
    client, repo = _authed_client(tmp_path)
    _seed_admin(repo)
    snap = _service_for_app(client).resolve(USER, now=NOW)
    _assert_full_constitution(snap)
    assert snap.admin_override is True
    assert snap.tier is None
    assert snap.is_subscribed is False
    assert snap.can_open_playground is True
    assert snap.can_consume_new_playground_law is True
    assert snap.playground_law_limit is None
    assert snap.playground_block_reason is None


def test_promotion_grant_is_not_admin_override_or_playground(tmp_path: Path):
    client, repo = _authed_client(tmp_path)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    repo.conn.execute(
        """
        INSERT INTO access_grants (
            id, user_id, source, starts_at, ends_at, reason, created_at
        ) VALUES (?, ?, 'promotion', ?, NULL, 'promo', ?)
        """,
        (str(uuid4()), str(USER), now.isoformat(), now.isoformat()),
    )
    repo.conn.commit()
    snap = _service_for_app(client).resolve(USER, now=NOW)
    assert snap.admin_override is False
    assert snap.can_open_playground is False
    assert snap.tier is None
    _assert_full_constitution(snap)


def test_snapshot_is_frozen():
    snap = EntitlementService().resolve(None)
    with pytest.raises(Exception):
        snap.is_subscribed = True  # type: ignore[misc]


def test_request_snapshot_is_memoized(tmp_path: Path):
    client, _repo = _authed_client(tmp_path)
    inner = client.app.state.subscriptions
    counting = CountingSubscriptions(inner)
    client.app.state.entitlement_service = EntitlementService(
        subscriptions=counting,
        charges=client.app.state.subscription_charges,
        access_store=client.app.state.access_store,
        legacy_store=client.app.state.engine.repo,
    )
    request = SimpleNamespace(
        app=client.app,
        state=SimpleNamespace(current_user=SimpleNamespace(id=USER)),
    )
    first = get_entitlement_snapshot(request, now=NOW)
    second = get_entitlement_snapshot(request, now=NOW)
    assert first is second
    assert counting.calls == 1
    _assert_full_constitution(first)


def test_service_never_mentions_razorpay_client():
    source = inspect.getsource(EntitlementService)
    module = Path(
        inspect.getsourcefile(EntitlementService)  # type: ignore[arg-type]
    ).read_text(encoding="utf-8")
    assert "RazorpaySubscriptionsClient" not in source
    assert "RazorpaySubscriptionsClient" not in module
    assert "fetch_subscription" not in module
    assert "RAZORPAY_" not in module
    assert is_subscribed(object()) is False


def test_resolve_does_not_call_provider_client(tmp_path: Path):
    client, _repo = _authed_client(tmp_path)
    boom = Boom()
    original = client.app.state.subscription_service
    if original is not None:
        original._client = boom  # type: ignore[attr-defined]
    snap = _service_for_app(client).resolve(USER, now=NOW)
    _assert_full_constitution(snap)


# --------------------------------------------------------------------------- #
# Constitution HTTP matrix                                                     #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "setup",
    (
        "none",
        "active_plus",
        "pending_pro",
        "halted_max",
        "paused",
        "legacy_active",
        "legacy_expired",
        "admin",
    ),
)
def test_signed_in_constitution_is_full_across_payment_states(
    tmp_path: Path, setup: str
) -> None:
    client, repo = _authed_client(tmp_path)
    if setup == "active_plus":
        _add_subscription(client, tier="plus", status="active")
    elif setup == "pending_pro":
        _add_subscription(client, tier="pro", status="pending")
    elif setup == "halted_max":
        _add_subscription(client, tier="max", status="halted")
    elif setup == "paused":
        _add_subscription(client, tier="plus", status="paused")
    elif setup == "legacy_active":
        _seed_legacy(repo, ends_at=NOW + timedelta(days=30))
    elif setup == "legacy_expired":
        _seed_legacy(repo, ends_at=NOW - timedelta(days=1))
    elif setup == "admin":
        _seed_admin(repo)
    claims_before = set(repo.claimed_articles(USER))
    _assert_learn_open(client)
    _complete_and_done(client, repo)
    assert repo.claimed_articles(USER) == claims_before
    snap = _service_for_app(client).resolve(USER, now=NOW)
    _assert_full_constitution(snap)
    assert set(ALL_MODES) == set(LEARN_MODES)


def test_claim_count_isolation_for_identical_accounts(tmp_path: Path):
    results = []
    claimed_sets = {
        "zero": (),
        "three": ("14", "19", "21"),
        "over": ("14", "19", "21", "32"),
    }
    for label, claimed in claimed_sets.items():
        case = tmp_path / label
        case.mkdir()
        client, repo = _authed_client(case)
        for number in claimed:
            repo.claim_article(USER, number)
        page = client.get("/learn/clause-1")
        type_seen = client.post(
            "/learn/clause-1/seen", data={"mode": "type"}, headers=JSON_HEADERS
        )
        recite_seen = client.post(
            "/learn/clause-1/seen", data={"mode": "recite"}, headers=JSON_HEADERS
        )
        results.append(
            (
                page.status_code,
                'data-locked-modes=""' in page.text,
                type_seen.status_code,
                type_seen.json().get("persisted"),
                recite_seen.json().get("persisted"),
            )
        )
        assert repo.claimed_articles(USER) == set(claimed)
    assert results[0] == results[1] == results[2]


def test_guest_learn_is_not_widened_or_narrowed(tmp_path: Path):
    client = _guest_client(tmp_path)
    page = client.get("/learn/clause-1?mode=type")
    assert page.status_code == 200
    assert 'data-locked-modes="type,recite"' in page.text
    assert "Sign in to use your Free Articles" in page.text
    done = client.post("/learn/clause-1/done", headers=JSON_HEADERS, follow_redirects=False)
    assert done.status_code in {303, 401}
    recite = client.post(
        "/learn/clause-1/speech/transcribe",
        data={"mode": "recite", "text": "No person shall"},
    )
    assert recite.status_code == 403
    assert recite.json()["error"] == "mode_locked"


def test_public_law_reading_is_ungated_for_guest_and_account(tmp_path: Path):
    guest_dir = tmp_path / "guest"
    guest_dir.mkdir()
    guest = _guest_client(guest_dir)
    authed_dir = tmp_path / "authed"
    authed_dir.mkdir()
    signed, _repo = _authed_client(authed_dir)
    for client, user_id in ((guest, None), (signed, USER)):
        listing = client.get("/laws")
        assert listing.status_code == 200
        detail = client.get("/laws/ndps")
        assert detail.status_code == 200
        section = client.get("/laws/ndps/section/1")
        assert section.status_code == 200
        snap = client.app.state.entitlement_service.resolve(user_id, now=NOW)
        assert snap.can_read_laws is True
        assert listing.status_code != 402


def test_charge_period_lookup_prefers_period_ended():
    start = PERIOD_START
    end = PERIOD_END
    other_end = PERIOD_END + timedelta(days=30)
    charges = [
        SubscriptionCharge(
            id="1",
            provider="razorpay",
            provider_payment_id="pay_old",
            provider_invoice_id=None,
            provider_subscription_id=None,
            user_subscription_id="sub",
            billing_period_start=start - timedelta(days=31),
            billing_period_end=start,
            amount_paise=19900,
            currency="INR",
            payment_status="captured",
            refund_status="full",
            amount_refunded_paise=19900,
            last_refund_id=None,
            dispute_id=None,
            dispute_status=None,
            access_effect="period_ended",
            access_effect_reason="full_refund",
            access_effect_at=NOW,
            created_at=NOW,
            updated_at=NOW,
        ),
        SubscriptionCharge(
            id="2",
            provider="razorpay",
            provider_payment_id="pay_now",
            provider_invoice_id=None,
            provider_subscription_id=None,
            user_subscription_id="sub",
            billing_period_start=start,
            billing_period_end=end,
            amount_paise=19900,
            currency="INR",
            payment_status="captured",
            refund_status=None,
            amount_refunded_paise=0,
            last_refund_id=None,
            dispute_id=None,
            dispute_status=None,
            access_effect="none",
            access_effect_reason=None,
            access_effect_at=None,
            created_at=NOW,
            updated_at=NOW,
        ),
    ]
    assert access_effect_for_billing_period(charges, start, end) == "none"
    assert access_effect_for_billing_period(charges, start, other_end) is None
    ended = replace(charges[1], access_effect="period_ended")
    assert access_effect_for_billing_period([charges[0], ended], start, end) == (
        "period_ended"
    )


def test_sqlite_charge_repo_period_query_matches_current_window():
    import sqlite3

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_sqlite_schema(conn)
    repo = SqliteChargeRepository(conn)
    repo.upsert_charge(
        provider_payment_id="pay_cur",
        user_subscription_id="sub-1",
        billing_period_start=PERIOD_START,
        billing_period_end=PERIOD_END,
        refund_status="full",
    )
    repo.upsert_charge(
        provider_payment_id="pay_other",
        user_subscription_id="sub-1",
        billing_period_start=PERIOD_START - timedelta(days=31),
        billing_period_end=PERIOD_START,
        refund_status=None,
    )
    assert (
        repo.get_charge_access_effect_for_billing_period(
            "sub-1", PERIOD_START, PERIOD_END
        )
        == "period_ended"
    )
    assert (
        repo.get_charge_access_effect_for_billing_period(
            "sub-1", PERIOD_START - timedelta(days=31), PERIOD_START
        )
        == "none"
    )


def test_no_cleanup_migration_for_historical_tables():
    versions = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    names = [path.name for path in versions.glob("*.py")]
    assert any("user_subscription" in name for name in names)
    assert not any("drop_user_free_articles" in name for name in names)
    assert not any("drop_access_grants" in name for name in names)
