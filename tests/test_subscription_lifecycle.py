"""Milestone 2B: create, checkout, cancel, upgrade, downgrade. No webhooks."""

from __future__ import annotations

import hashlib
import hmac
import sqlite3
import threading
import time
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.guest import requires_auth
from constitution_memorizer.auth.sessions import CSRF_COOKIE_NAME, InMemorySessionStore
from constitution_memorizer.multiuser.settings import (
    MultiUserSettings,
    clear_settings_cache,
)
from constitution_memorizer.progress.db import open_progress_db
from constitution_memorizer.progress.repository import ProgressRepository
from constitution_memorizer.progress.user_ids import LOCAL_USER_ID
from constitution_memorizer.subscriptions.catalog import UnknownSubscriptionTier
from constitution_memorizer.subscriptions.config import SubscriptionPlanIds
from constitution_memorizer.subscriptions.db import ensure_sqlite_schema
from constitution_memorizer.subscriptions.errors import (
    ChangePlanRequiredError,
    CheckoutInProgressError,
    CheckoutMismatchError,
    CheckoutSignatureError,
    CurrentSubscriptionExistsError,
    ResubscribeUnavailableError,
    SameTierChangeError,
    SubscriptionConfigError,
    SubscriptionNetworkError,
    SubscriptionRejectedError,
    SubscriptionStateError,
)
from constitution_memorizer.subscriptions.razorpay import (
    RAZORPAY_MONTHLY_TOTAL_COUNT,
    SCHEDULE_CYCLE_END,
    SCHEDULE_NOW,
    CreateSubscriptionRequest,
    ProviderSubscription,
)
from constitution_memorizer.subscriptions.repository import SqliteSubscriptionRepository
from constitution_memorizer.subscriptions.service import SubscriptionService
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.entitlements import is_subscribed
from constitution_memorizer.web import billing as legacy_billing
from constitution_memorizer.web import pricing as legacy_pricing

ROOT = Path(__file__).resolve().parents[1]
MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
USER = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
KEY_ID = "rzp_test_pub"
KEY_SECRET = "dummy-secret-for-tests"
PLAN_IDS = SubscriptionPlanIds(
    plus="plan_plus",
    pro="plan_pro",
    max="plan_max",
)


@pytest.fixture(autouse=True)
def _clear_settings():
    clear_settings_cache()
    yield
    clear_settings_cache()


def _sign(payment_id: str, subscription_id: str, secret: str = KEY_SECRET) -> str:
    return hmac.new(
        secret.encode(),
        f"{payment_id}|{subscription_id}".encode(),
        hashlib.sha256,
    ).hexdigest()


def _sqlite_repo() -> SqliteSubscriptionRepository:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_sqlite_schema(conn)
    return SqliteSubscriptionRepository(conn)


class FakeProvider:
    def __init__(self, *, secret: str = KEY_SECRET) -> None:
        self.secret = secret
        self.creates: list[CreateSubscriptionRequest] = []
        self.fetches: list[str] = []
        self.cancels: list[dict] = []
        self.updates: list[dict] = []
        self.create_error: Exception | None = None
        self.fetch_error: Exception | None = None
        self.cancel_error: Exception | None = None
        self.update_error: Exception | None = None
        self.fetch_status = "authenticated"
        self.created_status = "created"
        self.create_delay = 0.0
        self.by_id: dict[str, ProviderSubscription] = {}
        self._n = 0
        self._lock = threading.Lock()

    def verify_checkout_signature(
        self, *, payment_id: str, subscription_id: str, signature: str
    ) -> bool:
        from constitution_memorizer.subscriptions.razorpay import (
            verify_subscription_signature,
        )

        return verify_subscription_signature(
            payment_id=payment_id,
            subscription_id=subscription_id,
            signature=signature,
            key_secret=self.secret,
        )

    def create_subscription(
        self, request: CreateSubscriptionRequest
    ) -> ProviderSubscription:
        if self.create_error is not None:
            raise self.create_error
        if self.create_delay:
            time.sleep(self.create_delay)
        with self._lock:
            self.creates.append(request)
            self._n += 1
            rec = _sub(
                f"sub_{self._n}",
                request.plan_id,
                self.created_status,
            )
            self.by_id[rec.id] = rec
            return rec

    def fetch_subscription(self, subscription_id: str) -> ProviderSubscription:
        if self.fetch_error is not None:
            raise self.fetch_error
        self.fetches.append(subscription_id)
        rec = self.by_id.get(subscription_id) or _sub(
            subscription_id, "plan_plus", self.fetch_status
        )
        return _sub(rec.id, rec.plan_id, self.fetch_status)

    def cancel_subscription(
        self, subscription_id: str, *, cancel_at_cycle_end: bool = True
    ) -> ProviderSubscription:
        if self.cancel_error is not None:
            raise self.cancel_error
        self.cancels.append(
            {
                "id": subscription_id,
                "cancel_at_cycle_end": cancel_at_cycle_end,
            }
        )
        rec = self.by_id.get(subscription_id) or _sub(
            subscription_id, "plan_plus", "active"
        )
        return _sub(rec.id, rec.plan_id, "active")

    def update_subscription_plan(
        self,
        subscription_id: str,
        *,
        plan_id: str,
        schedule_change_at: str,
    ) -> ProviderSubscription:
        if self.update_error is not None:
            raise self.update_error
        self.updates.append(
            {
                "id": subscription_id,
                "plan_id": plan_id,
                "schedule_change_at": schedule_change_at,
            }
        )
        rec = _sub(subscription_id, plan_id, "active")
        self.by_id[subscription_id] = rec
        return rec


def _sub(sub_id: str, plan_id: str, status: str) -> ProviderSubscription:
    return ProviderSubscription(
        id=sub_id,
        plan_id=plan_id,
        status=status,
        current_start=1756684800,
        current_end=1759276800,
        customer_id="cust_1",
        short_url=None,
        has_scheduled_changes=False,
        raw={"id": sub_id, "plan_id": plan_id, "status": status},
    )


def _service(repo=None, fake=None, *, plan_ids=PLAN_IDS, key_id: str = KEY_ID):
    repo = repo or _sqlite_repo()
    fake = fake or FakeProvider()
    service = SubscriptionService(repo, fake, plan_ids, public_key_id=key_id)
    return service, fake, repo


def _activate(service, fake, user=USER, tier: str = "plus"):
    handoff = service.start_subscription(user, tier)
    fake.fetch_status = "active"
    return service.complete_checkout(
        user,
        razorpay_payment_id="pay_1",
        razorpay_subscription_id=handoff.subscription_id,
        razorpay_signature=_sign("pay_1", handoff.subscription_id),
    )


def _settings(**overrides) -> MultiUserSettings:
    base = {
        "APP_ENV": "test",
        "MULTIUSER_ENABLED": "true",
        "AUTH_GOOGLE_ENABLED": "true",
        "SESSION_SECRET": "test-secret",
        "SUPABASE_URL": "http://example.invalid",
        "SUPABASE_ANON_KEY": "anon",
        "DATABASE_URL": "",
        "COOKIE_SECURE": "false",
        "RAZORPAY_KEY_ID": KEY_ID,
        "RAZORPAY_KEY_SECRET": KEY_SECRET,
        "RAZORPAY_PLAN_ID_PLUS": "plan_plus",
        "RAZORPAY_PLAN_ID_PRO": "plan_pro",
        "RAZORPAY_PLAN_ID_MAX": "plan_max",
    }
    base.update({k: str(v) for k, v in overrides.items()})
    return MultiUserSettings(_env_file=None, **base)


def _http_client(tmp_path: Path, *, signed_in: bool = True, fake=None):
    conn = open_progress_db(tmp_path / "progress.db")
    progress = ProgressRepository(conn)
    provider = FakeAuthProvider()
    provider.seed_google_user(user_id=USER, email="a@example.com", display_name="T")
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "unused.db",
        multiuser=True,
        multiuser_settings=_settings(),
        auth_provider=provider,
        session_store=InMemorySessionStore(),
        progress_repo=progress,
    )
    fake = fake or FakeProvider()
    app.state.subscription_service = SubscriptionService(
        app.state.subscriptions,
        fake,
        PLAN_IDS,
        public_key_id=KEY_ID,
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
    return client, fake, app


# --------------------------------------------------------------------------- #
# Create
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "tier,plan_id",
    [("plus", "plan_plus"), ("pro", "plan_pro"), ("max", "plan_max")],
)
def test_create_maps_tier_to_configured_plan_and_provider_horizon(tier, plan_id):
    service, fake, _repo = _service()
    handoff = service.start_subscription(USER, tier)
    assert len(fake.creates) == 1
    request = fake.creates[0]
    assert request.plan_id == plan_id
    assert request.total_count == RAZORPAY_MONTHLY_TOTAL_COUNT == 1200
    assert request.quantity == 1
    assert request.customer_notify is True
    assert handoff.key_id == KEY_ID
    assert handoff.subscription_id == "sub_1"
    payload = handoff.as_browser_payload()
    assert payload["key_id"] == KEY_ID
    assert payload["subscription_id"] == "sub_1"
    assert KEY_SECRET not in str(payload)
    assert "secret" not in str(payload).lower()


def test_create_ignores_client_price_plan_id_and_total_count():
    service, fake, _repo = _service()
    service.start_subscription(USER, "plus")
    assert fake.creates[0].plan_id == "plan_plus"
    assert fake.creates[0].total_count == 1200


def test_repeat_same_tier_checkout_reuses_provider_subscription():
    service, fake, _repo = _service()
    first = service.start_subscription(USER, "plus")
    second = service.start_subscription(USER, "plus")
    assert len(fake.creates) == 1
    assert first.subscription_id == second.subscription_id == "sub_1"


def test_reservation_inserts_before_provider_create():
    repo = _sqlite_repo()
    fake = FakeProvider()
    order: list[str] = []
    original = repo.create_subscription_record

    def wrapped(*args, **kwargs):
        order.append("insert")
        return original(*args, **kwargs)

    repo.create_subscription_record = wrapped  # type: ignore[method-assign]
    original_create = fake.create_subscription

    def create_wrapped(request):
        order.append("provider")
        return original_create(request)

    fake.create_subscription = create_wrapped  # type: ignore[method-assign]
    service, _, _ = _service(repo, fake)
    service.start_subscription(USER, "plus")
    assert order == ["insert", "provider"]


def test_concurrent_create_makes_one_provider_subscription(tmp_path: Path):
    path = tmp_path / "subscriptions.db"
    fake = FakeProvider(create_delay=0.05)
    barrier = threading.Barrier(2)
    results: list = []
    errors: list = []

    def worker():
        conn = sqlite3.connect(str(path), timeout=10, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=10000")
        ensure_sqlite_schema(conn)
        repo = SqliteSubscriptionRepository(conn)
        service = SubscriptionService(repo, fake, PLAN_IDS, public_key_id=KEY_ID)
        barrier.wait()
        try:
            results.append(service.start_subscription(USER, "plus"))
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=8)
        assert not thread.is_alive()
    assert len(fake.creates) == 1
    assert results
    assert all(
        item.subscription_id == results[0].subscription_id for item in results
    )
    assert not errors or all(
        isinstance(err, (CheckoutInProgressError, ChangePlanRequiredError))
        for err in errors
    )


def test_provider_failure_releases_reservation_for_retry():
    service, fake, repo = _service()
    fake.create_error = SubscriptionNetworkError("Could not reach the payment provider")
    with pytest.raises(SubscriptionNetworkError):
        service.start_subscription(USER, "plus")
    assert repo.get_current_subscription(USER) is None
    history = repo.list_subscription_history(USER)
    assert len(history) == 1
    assert history[0].is_current is False
    fake.create_error = None
    handoff = service.start_subscription(USER, "plus")
    assert len(fake.creates) == 2
    assert handoff.subscription_id == "sub_2"


def test_persist_failure_after_provider_create_does_not_create_second_subscription():
    service, fake, repo = _service()

    def boom(*_args, **_kwargs):
        raise RuntimeError("db down")

    repo.update_subscription_state = boom  # type: ignore[method-assign]
    with pytest.raises(RuntimeError):
        service.start_subscription(USER, "plus")
    assert len(fake.creates) == 1
    current = repo.get_current_subscription(USER)
    assert current is not None
    assert current.provider_subscription_id is None
    with pytest.raises(CheckoutInProgressError):
        service.start_subscription(USER, "plus")
    assert len(fake.creates) == 1


def test_invalid_tier_and_missing_config_do_not_call_provider():
    service, fake, _repo = _service()
    with pytest.raises(UnknownSubscriptionTier):
        service.start_subscription(USER, "premium")
    empty = SubscriptionService(
        _sqlite_repo(), FakeProvider(), SubscriptionPlanIds(), public_key_id=KEY_ID
    )
    with pytest.raises(SubscriptionConfigError, match="RAZORPAY_PLAN_ID_PLUS"):
        empty.start_subscription(USER, "plus")
    no_key = SubscriptionService(
        _sqlite_repo(), FakeProvider(), PLAN_IDS, public_key_id=""
    )
    with pytest.raises(SubscriptionConfigError, match="RAZORPAY_KEY_ID"):
        no_key.start_subscription(USER, "plus")
    assert fake.creates == []


def test_live_subscription_blocks_parallel_create():
    service, fake, _repo = _service()
    _activate(service, fake)
    with pytest.raises(ChangePlanRequiredError):
        service.start_subscription(USER, "pro")
    with pytest.raises(ChangePlanRequiredError):
        service.start_subscription(USER, "plus")
    assert len(fake.creates) == 1


def test_terminal_current_row_does_not_resubscribe():
    service, fake, repo = _service()
    repo.create_subscription_record(
        USER,
        tier="plus",
        status="cancelled",
        provider_subscription_id="sub_old",
        is_current=True,
    )
    with pytest.raises(ResubscribeUnavailableError):
        service.start_subscription(USER, "plus")
    assert fake.creates == []


def test_in_progress_reservation_does_not_create_another_provider_subscription():
    service, fake, repo = _service()
    repo.create_subscription_record(
        USER, tier="plus", status="created", is_current=True
    )
    with pytest.raises(CheckoutInProgressError):
        service.start_subscription(USER, "plus")
    assert fake.creates == []


# --------------------------------------------------------------------------- #
# Checkout
# --------------------------------------------------------------------------- #
def test_checkout_persists_provider_status_not_invented_active():
    service, fake, repo = _service()
    handoff = service.start_subscription(USER, "plus")
    fake.fetch_status = "authenticated"
    stored = service.complete_checkout(
        USER,
        razorpay_payment_id="pay_1",
        razorpay_subscription_id=handoff.subscription_id,
        razorpay_signature=_sign("pay_1", handoff.subscription_id),
    )
    assert stored.status == "authenticated"
    assert stored.status != "active"
    assert stored.provider_metadata["verified_payment_id"] == "pay_1"
    fake.fetch_status = "active"
    stored = service.complete_checkout(
        USER,
        razorpay_payment_id="pay_2",
        razorpay_subscription_id=handoff.subscription_id,
        razorpay_signature=_sign("pay_2", handoff.subscription_id),
    )
    assert stored.status == "active"
    assert len(fake.fetches) == 2


def test_invalid_signature_and_mismatch_do_not_fetch_or_mutate():
    service, fake, repo = _service()
    handoff = service.start_subscription(USER, "plus")
    with pytest.raises(CheckoutMismatchError):
        service.complete_checkout(
            USER,
            razorpay_payment_id="pay_1",
            razorpay_subscription_id="sub_other",
            razorpay_signature=_sign("pay_1", "sub_other"),
        )
    with pytest.raises(CheckoutSignatureError):
        service.complete_checkout(
            USER,
            razorpay_payment_id="pay_1",
            razorpay_subscription_id=handoff.subscription_id,
            razorpay_signature="forged",
        )
    current = repo.get_current_subscription(USER)
    assert current is not None
    assert current.status == "created"
    assert fake.fetches == []


def test_hmac_uses_server_stored_subscription_id():
    service, fake, _repo = _service()
    handoff = service.start_subscription(USER, "plus")
    attacker_sig = _sign("pay_1", "sub_forged")
    with pytest.raises((CheckoutMismatchError, CheckoutSignatureError)):
        service.complete_checkout(
            USER,
            razorpay_payment_id="pay_1",
            razorpay_subscription_id="sub_forged",
            razorpay_signature=attacker_sig,
        )
    with pytest.raises(CheckoutSignatureError):
        service.complete_checkout(
            USER,
            razorpay_payment_id="pay_1",
            razorpay_subscription_id=handoff.subscription_id,
            razorpay_signature=attacker_sig,
        )
    assert fake.fetches == []


def test_provider_fetch_failure_after_valid_signature_does_not_activate():
    service, fake, repo = _service()
    handoff = service.start_subscription(USER, "plus")
    fake.fetch_error = SubscriptionNetworkError("Could not reach the payment provider")
    with pytest.raises(SubscriptionNetworkError):
        service.complete_checkout(
            USER,
            razorpay_payment_id="pay_1",
            razorpay_subscription_id=handoff.subscription_id,
            razorpay_signature=_sign("pay_1", handoff.subscription_id),
        )
    current = repo.get_current_subscription(USER)
    assert current is not None
    assert current.status == "created"


# --------------------------------------------------------------------------- #
# Cancel / change
# --------------------------------------------------------------------------- #
def test_cancel_active_sets_cycle_end_flag_and_stays_current():
    service, fake, repo = _service()
    _activate(service, fake, tier="pro")
    stored = service.cancel_at_cycle_end(USER)
    assert fake.cancels == [
        {"id": "sub_1", "cancel_at_cycle_end": True}
    ]
    assert stored.cancel_at_period_end is True
    assert stored.is_current is True
    assert stored.tier == "pro"
    assert stored.status == "active"
    assert repo.get_current_subscription(USER).id == stored.id
    history = repo.list_subscription_history(USER)
    assert len(history) == 1


def test_pre_active_cancel_does_not_call_provider():
    service, fake, _repo = _service()
    handoff = service.start_subscription(USER, "plus")
    with pytest.raises(SubscriptionStateError, match="active"):
        service.cancel_at_cycle_end(USER)
    assert fake.cancels == []
    fake.fetch_status = "authenticated"
    service.complete_checkout(
        USER,
        razorpay_payment_id="pay_1",
        razorpay_subscription_id=handoff.subscription_id,
        razorpay_signature=_sign("pay_1", handoff.subscription_id),
    )
    with pytest.raises(SubscriptionStateError, match="active"):
        service.cancel_at_cycle_end(USER)
    assert fake.cancels == []


def test_cancel_provider_rejection_leaves_local_uncancelled():
    service, fake, repo = _service()
    _activate(service, fake)
    fake.cancel_error = SubscriptionRejectedError(
        "Payment provider rejected the subscription"
    )
    with pytest.raises(SubscriptionRejectedError):
        service.cancel_at_cycle_end(USER)
    current = repo.get_current_subscription(USER)
    assert current is not None
    assert current.cancel_at_period_end is False
    assert current.is_current is True


@pytest.mark.parametrize(
    "source,target",
    [("plus", "pro"), ("plus", "max"), ("pro", "max")],
)
def test_upgrade_is_immediate_and_uses_server_plan_id(source, target):
    service, fake, repo = _service()
    _activate(service, fake, tier=source)
    before = repo.get_current_subscription(USER)
    assert before is not None
    assert before.tier == source
    stored = service.change_plan(USER, target)
    assert fake.updates[-1]["plan_id"] == PLAN_IDS.for_tier(target)
    assert fake.updates[-1]["schedule_change_at"] == SCHEDULE_NOW
    assert stored.tier == target
    assert stored.provider_plan_id == PLAN_IDS.for_tier(target)


def test_upgrade_provider_rejection_keeps_old_tier():
    service, fake, repo = _service()
    _activate(service, fake, tier="plus")
    fake.update_error = SubscriptionRejectedError(
        "Payment provider rejected the subscription"
    )
    with pytest.raises(SubscriptionRejectedError):
        service.change_plan(USER, "pro")
    current = repo.get_current_subscription(USER)
    assert current is not None
    assert current.tier == "plus"
    assert current.provider_plan_id == "plan_plus"


@pytest.mark.parametrize(
    "source,target",
    [("max", "pro"), ("max", "plus"), ("pro", "plus")],
)
def test_downgrade_is_cycle_end_and_does_not_shrink_local_tier(source, target):
    service, fake, repo = _service()
    _activate(service, fake, tier=source)
    stored = service.change_plan(USER, target)
    assert fake.updates[-1]["plan_id"] == PLAN_IDS.for_tier(target)
    assert fake.updates[-1]["schedule_change_at"] == SCHEDULE_CYCLE_END
    assert stored.tier == source
    assert stored.provider_plan_id == PLAN_IDS.for_tier(source)
    assert stored.provider_metadata["scheduled_tier"] == target
    assert stored.provider_metadata["scheduled_plan_id"] == PLAN_IDS.for_tier(target)
    assert stored.provider_metadata["schedule_change_at"] == SCHEDULE_CYCLE_END


def test_downgrade_provider_rejection_records_no_schedule():
    service, fake, repo = _service()
    _activate(service, fake, tier="max")
    fake.update_error = SubscriptionRejectedError(
        "Payment provider rejected the subscription"
    )
    with pytest.raises(SubscriptionRejectedError):
        service.change_plan(USER, "plus")
    current = repo.get_current_subscription(USER)
    assert current is not None
    assert current.tier == "max"
    assert "scheduled_tier" not in current.provider_metadata


def test_same_tier_and_invalid_source_state_are_rejected():
    service, fake, _repo = _service()
    service.start_subscription(USER, "plus")
    with pytest.raises(SubscriptionStateError):
        service.change_plan(USER, "pro")
    assert fake.updates == []
    _activate(service, fake)
    with pytest.raises(SameTierChangeError):
        service.change_plan(USER, "plus")
    assert fake.updates == []


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #
def test_guest_can_read_plans_but_cannot_mutate(tmp_path: Path):
    client, fake, _app = _http_client(tmp_path, signed_in=False)
    page = client.get("/billing/subscriptions")
    assert page.status_code == 200
    assert "₹199/month" in page.text
    assert "₹399/month" in page.text
    assert "₹1,199/month" in page.text
    assert "GST included" in page.text
    assert "Sign in to subscribe" in page.text
    assert "starting at" not in page.text.lower()
    assert "annual" not in page.text.lower()
    assert "lifetime" not in page.text.lower()
    assert "1200" not in page.text
    assert "100-year" not in page.text
    assert "100 year" not in page.text.lower()
    create = client.post(
        "/billing/subscriptions/create",
        data={"tier": "plus"},
        follow_redirects=False,
    )
    assert create.status_code == 303
    assert "/login" in create.headers["location"]
    assert fake.creates == []
    assert requires_auth("/billing/subscriptions", "POST")
    assert not requires_auth("/billing/subscriptions", "GET")
    assert requires_auth("/billing/subscriptions/checkout", "GET")
    assert not requires_auth("/api/billing/order", "POST")


def test_http_create_checkout_complete_cancel_and_change(tmp_path: Path):
    client, fake, app = _http_client(tmp_path)
    csrf = client.cookies.get(CSRF_COOKIE_NAME)
    created = client.post(
        "/billing/subscriptions/create",
        data={
            "csrf_token": csrf,
            "tier": "plus",
            "plan_id": "plan_evil",
            "price": "1",
            "amount": "1",
            "total_count": "2",
        },
        follow_redirects=False,
    )
    assert created.status_code == 303
    assert created.headers["location"] == "/billing/subscriptions/checkout"
    assert fake.creates[0].plan_id == "plan_plus"
    assert fake.creates[0].total_count == 1200
    checkout = client.get("/billing/subscriptions/checkout")
    assert checkout.status_code == 200
    assert KEY_ID in checkout.text
    assert "sub_1" in checkout.text
    assert KEY_SECRET not in checkout.text
    assert "data-subscription-checkout-pay" in checkout.text
    assert fake.fetches == []
    bad = client.post(
        "/billing/subscriptions/checkout/complete",
        headers={"X-CSRF-Token": csrf or ""},
        json={
            "razorpay_payment_id": "pay_1",
            "razorpay_subscription_id": "sub_1",
            "razorpay_signature": "forged",
        },
    )
    assert bad.status_code == 400
    mismatch = client.post(
        "/billing/subscriptions/checkout/complete",
        headers={"X-CSRF-Token": csrf or ""},
        json={
            "razorpay_payment_id": "pay_1",
            "razorpay_subscription_id": "sub_other",
            "razorpay_signature": _sign("pay_1", "sub_other"),
        },
    )
    assert mismatch.status_code == 400
    fake.fetch_status = "authenticated"
    ok = client.post(
        "/billing/subscriptions/checkout/complete",
        headers={"X-CSRF-Token": csrf or ""},
        json={
            "razorpay_payment_id": "pay_1",
            "razorpay_subscription_id": "sub_1",
            "razorpay_signature": _sign("pay_1", "sub_1"),
        },
    )
    assert ok.status_code == 200
    assert ok.json()["status"] == "authenticated"
    row = app.state.subscriptions.get_current_subscription(USER)
    assert row.status == "authenticated"
    fake.fetch_status = "active"
    client.post(
        "/billing/subscriptions/checkout/complete",
        headers={"X-CSRF-Token": csrf or ""},
        json={
            "razorpay_payment_id": "pay_2",
            "razorpay_subscription_id": "sub_1",
            "razorpay_signature": _sign("pay_2", "sub_1"),
        },
    )
    assert app.state.subscriptions.get_current_subscription(USER).status == "active"
    changed = client.post(
        "/billing/subscriptions/change",
        data={"csrf_token": csrf, "tier": "max", "plan_id": "plan_evil"},
        follow_redirects=False,
    )
    assert changed.status_code == 303
    assert fake.updates[-1]["schedule_change_at"] == SCHEDULE_NOW
    assert app.state.subscriptions.get_current_subscription(USER).tier == "max"
    down = client.post(
        "/billing/subscriptions/change",
        data={"csrf_token": csrf, "tier": "plus"},
        follow_redirects=False,
    )
    assert down.status_code == 303
    assert fake.updates[-1]["schedule_change_at"] == SCHEDULE_CYCLE_END
    current = app.state.subscriptions.get_current_subscription(USER)
    assert current.tier == "max"
    same = client.post(
        "/billing/subscriptions/change",
        data={"csrf_token": csrf, "tier": "max"},
        follow_redirects=False,
    )
    assert same.status_code == 303
    assert "same_tier" in same.headers["location"]
    cancelled = client.post(
        "/billing/subscriptions/cancel",
        data={"csrf_token": csrf},
        follow_redirects=False,
    )
    assert cancelled.status_code == 303
    assert fake.cancels[-1]["cancel_at_cycle_end"] is True
    current = app.state.subscriptions.get_current_subscription(USER)
    assert current.cancel_at_period_end is True
    assert current.is_current is True
    page = client.get("/billing/subscriptions")
    assert "max" in page.text.lower() or "Max" in page.text
    assert "Ends after the current paid cycle" in page.text


def test_http_csrf_and_provider_outage(tmp_path: Path):
    client, fake, _app = _http_client(tmp_path)
    denied = client.post(
        "/billing/subscriptions/create",
        data={"csrf_token": "nope", "tier": "plus"},
        follow_redirects=False,
    )
    assert denied.status_code == 403
    fake.create_error = SubscriptionNetworkError("Could not reach the payment provider")
    csrf = client.cookies.get(CSRF_COOKIE_NAME)
    outage = client.post(
        "/billing/subscriptions/create",
        data={"csrf_token": csrf, "tier": "plus"},
        follow_redirects=False,
    )
    assert outage.status_code == 303
    assert "error=provider" in outage.headers["location"]
    page = client.get("/billing/subscriptions?error=provider")
    assert "Could not complete the payment-provider request" in page.text
    assert "No subscription" not in page.text


def test_http_create_while_active_does_not_start_second_provider_sub(tmp_path: Path):
    client, fake, app = _http_client(tmp_path)
    csrf = client.cookies.get(CSRF_COOKIE_NAME)
    client.post(
        "/billing/subscriptions/create",
        data={"csrf_token": csrf, "tier": "plus"},
        follow_redirects=False,
    )
    fake.fetch_status = "active"
    client.post(
        "/billing/subscriptions/checkout/complete",
        headers={"X-CSRF-Token": csrf or ""},
        json={
            "razorpay_payment_id": "pay_1",
            "razorpay_subscription_id": "sub_1",
            "razorpay_signature": _sign("pay_1", "sub_1"),
        },
    )
    again = client.post(
        "/billing/subscriptions/create",
        data={"csrf_token": csrf, "tier": "pro"},
        follow_redirects=False,
    )
    assert again.status_code == 303
    assert "change_required" in again.headers["location"]
    assert len(fake.creates) == 1
    assert app.state.subscriptions.get_current_subscription(USER).tier == "plus"


def test_get_never_triggers_provider_and_is_subscribed_stays_false(tmp_path: Path):
    client, fake, app = _http_client(tmp_path)
    csrf = client.cookies.get(CSRF_COOKIE_NAME)
    client.get("/billing/subscriptions")
    client.post(
        "/billing/subscriptions/create",
        data={"csrf_token": csrf, "tier": "plus"},
        follow_redirects=False,
    )
    client.get("/billing/subscriptions/checkout")
    assert fake.fetches == []
    assert fake.cancels == []
    assert fake.updates == []
    fake.fetch_status = "active"
    client.post(
        "/billing/subscriptions/checkout/complete",
        headers={"X-CSRF-Token": csrf or ""},
        json={
            "razorpay_payment_id": "pay_1",
            "razorpay_subscription_id": "sub_1",
            "razorpay_signature": _sign("pay_1", "sub_1"),
        },
    )
    assert is_subscribed(object()) is False
    playground = ROOT / "src/constitution_memorizer/playground"
    for path in playground.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "user_subscription" not in text
        assert "get_current_subscription" not in text


# --------------------------------------------------------------------------- #
# Legacy isolation
# --------------------------------------------------------------------------- #
def test_legacy_orders_duration_and_access_grants_are_untouched():
    assert [plan.days for plan in legacy_pricing.PLANS] == [
        3, 7, 15, 30, 60, 180, 365
    ]
    year = next(plan for plan in legacy_pricing.PLANS if plan.days == 365)
    assert year.price_inr == 999
    billing_source = Path(legacy_billing.__file__).read_text(encoding="utf-8")
    assert "RAZORPAY_ORDERS_URL" in billing_source
    assert "/v1/subscriptions" not in billing_source
    app_source = (
        ROOT / "src/constitution_memorizer/web/app.py"
    ).read_text(encoding="utf-8")
    assert "start_subscription" not in app_source
    assert "/api/billing/order" in app_source
    routes = (
        ROOT / "src/constitution_memorizer/subscriptions/routes.py"
    ).read_text(encoding="utf-8")
    assert "httpx" not in routes
    assert "/playground" not in routes
    service_src = (
        ROOT / "src/constitution_memorizer/subscriptions/service.py"
    ).read_text(encoding="utf-8")
    assert "httpx" not in service_src
    templates = (
        ROOT / "src/constitution_memorizer/web/templates/subscription_manage.html"
    ).read_text(encoding="utf-8")
    checkout = (
        ROOT / "src/constitution_memorizer/web/templates/subscription_checkout.html"
    ).read_text(encoding="utf-8")
    for text in (templates, checkout):
        lowered = text.lower()
        assert "1200" not in text
        assert "100-year" not in lowered
        assert "starting at" not in lowered
        assert "annual" not in lowered
        assert "lifetime" not in lowered
        assert "unlock 10 laws forever" not in lowered
        assert "10 new laws each billing cycle" not in lowered


def test_service_honors_one_current_row_constraint():
    service, fake, repo = _service()
    service.start_subscription(USER, "plus")
    with pytest.raises(CurrentSubscriptionExistsError):
        repo.create_subscription_record(
            USER, tier="pro", status="created", is_current=True
        )
    assert len(fake.creates) == 1
    assert len(repo.list_subscription_history(USER)) == 1
    assert str(USER) != LOCAL_USER_ID
