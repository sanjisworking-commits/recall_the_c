"""B1-B02 / B1-B03 on real Postgres (PR #230).

Runs only against a disposable local Postgres named by ``PLAYGROUND_PG_TEST_URL``
(the fixture refuses non-localhost hosts and applies ``alembic upgrade head``).

    PLAYGROUND_PG_TEST_URL=postgresql://postgres@127.0.0.1:54329/pgb1 \\
        pytest -m integration tests/test_subscription_billing_postgres.py
"""

from __future__ import annotations

import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID

import pytest

from constitution_memorizer.subscriptions.config import SubscriptionPlanIds
from constitution_memorizer.subscriptions.postgres import PostgresSubscriptionRepository
from constitution_memorizer.subscriptions.service import SubscriptionService
from constitution_memorizer.subscriptions.webhook_postgres import PostgresWebhookEventRepository
from constitution_memorizer.subscriptions.webhook_signature import WebhookSecrets
from constitution_memorizer.subscriptions.webhooks import WebhookProcessor
from tests.test_subscription_webhooks import (
    NOV,
    OCT,
    SEP,
    FakeProvider,
    _event_payload,
    _raw,
    _sign_body,
    _sub,
)

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[1]
PG_URL = os.environ.get("PLAYGROUND_PG_TEST_URL", "").strip()
USER = UUID("b3b3b3b3-b3b3-4b3b-8b3b-b3b3b3b3b3b3")
KEY_ID = "rzp_test_pub"
WHSEC = "whsec_current_for_tests"
PLAN_IDS = SubscriptionPlanIds(plus="plan_plus", pro="plan_pro", max="plan_max")


@pytest.fixture(scope="module")
def pool():
    if not PG_URL:
        pytest.skip("PLAYGROUND_PG_TEST_URL not set")
    host = (urlparse(PG_URL).hostname or "").lower()
    if host not in {"localhost", "127.0.0.1", "::1"}:
        pytest.skip("PLAYGROUND_PG_TEST_URL must point at a disposable local Postgres")
    from psycopg_pool import ConnectionPool

    from alembic import command
    from alembic.config import Config

    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = PG_URL
    try:
        command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
    pool = ConnectionPool(conninfo=PG_URL, min_size=1, max_size=8, open=True)
    try:
        yield pool
    finally:
        pool.close()


@pytest.fixture()
def clean(pool):
    with pool.connection() as conn:
        conn.execute("DELETE FROM user_subscription WHERE user_id = %s", (str(USER),))
        conn.execute("DELETE FROM subscription_webhook_event WHERE provider_event_id LIKE 'pgb_%%'")
        conn.commit()
    return PostgresSubscriptionRepository(pool)


def _processor(pool, fake):
    subs = PostgresSubscriptionRepository(pool)
    events = PostgresWebhookEventRepository(pool)
    service = SubscriptionService(subs, fake, PLAN_IDS, public_key_id=KEY_ID)
    return WebhookProcessor(
        events=events,
        subscriptions=subs,
        service=service,
        secrets=WebhookSecrets(current=WHSEC, previous=None),
        charges=None,
    )


def _ts(value: int) -> datetime:
    return datetime.fromtimestamp(value, tz=timezone.utc)


class _TruthProvider(FakeProvider):
    def __init__(self) -> None:
        super().__init__()
        self.hold_for: str | None = None
        self.release = threading.Event()
        self.entered = threading.Event()
        self.order: list[str] = []

    def fetch_subscription(self, subscription_id: str):
        with self._lock:
            held = self.hold_for
            self.hold_for = None
            status, end = self.status, self.current_end  # answer fixed when asked
            self.order.append(status)
        if held is not None:
            self.entered.set()
            self.release.wait(timeout=1.5)  # response delayed; B may overtake
        return _sub(subscription_id, self.plan_id, status, current_start=self.current_start, current_end=end)


def test_b02_advisory_lock_serialises_interleaved_reconciliations(pool, clean):
    subs = clean
    subs.create_subscription_record(
        USER, tier="plus", status="active", provider_subscription_id="sub_pg_1",
        provider_plan_id="plan_plus", provider_customer_id="cust_1",
        billing_period_start=_ts(SEP), billing_period_end=_ts(OCT),
    )
    fake = _TruthProvider()
    fake.status = "pending"
    fake.current_end = OCT
    fake.hold_for = "A"
    done: dict[str, object] = {}

    def run(label: str, event_name: str):
        processor = _processor(pool, fake)
        raw = _raw(_event_payload(event_name, sub_id="sub_pg_1"))
        done[label] = processor.process_delivery(raw, _sign_body(raw, WHSEC), f"pgb_{label}")

    a = threading.Thread(target=run, args=("A", "subscription.pending"))
    a.start()
    assert fake.entered.wait(timeout=3)
    with fake._lock:
        fake.status = "active"
        fake.current_end = NOV
    b = threading.Thread(target=run, args=("B", "subscription.charged"))
    b.start()
    b.join(timeout=0.5)
    assert b.is_alive()  # B waits on pg_advisory_xact_lock for sub_pg_1
    fake.release.set()
    a.join(timeout=10)
    b.join(timeout=10)
    assert not a.is_alive() and not b.is_alive()
    assert done["A"].status_code == 200 and done["B"].status_code == 200  # type: ignore[union-attr]
    assert fake.order == ["pending", "active"]
    current = subs.get_current_subscription(USER)
    assert current.status == "active"
    assert current.billing_period_end == _ts(NOV)
    assert current.provider_metadata.get("last_charge_event_id") == "pgb_B"
    # The lock is transaction-scoped: nothing is left held afterwards.
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND classid = 872013"
        ).fetchone()
    assert int(row[0]) == 0


def test_b03_late_event_for_superseded_row_leaves_the_current_row_untouched(pool, clean):
    subs = clean
    old = subs.create_subscription_record(
        USER, tier="plus", status="cancelled", provider_subscription_id="sub_pg_old",
        provider_plan_id="plan_plus", provider_customer_id="cust_1",
        billing_period_start=_ts(SEP), billing_period_end=_ts(OCT), is_current=False,
    )
    new = subs.create_subscription_record(
        USER, tier="pro", status="active", provider_subscription_id="sub_pg_new",
        provider_plan_id="plan_pro", provider_customer_id="cust_1",
        billing_period_start=_ts(OCT), billing_period_end=_ts(NOV), is_current=True,
    )
    fake = FakeProvider()
    fake.status = "active"
    fake.plan_id = "plan_plus"
    processor = _processor(pool, fake)
    for event_name, event_id in (("subscription.activated", "pgb_old_1"), ("subscription.charged", "pgb_old_2")):
        raw = _raw(_event_payload(event_name, sub_id="sub_pg_old"))
        result = processor.process_delivery(raw, _sign_body(raw, WHSEC), event_id)
        assert result.status_code == 200 and result.processing_status == "processed"

    current = subs.get_current_subscription(USER)
    assert current.id == new.id
    assert (current.tier, current.status, current.is_current) == ("pro", "active", True)
    assert current.provider_subscription_id == "sub_pg_new"
    assert current.billing_period_end == _ts(NOV)
    assert "last_charge_event_id" not in current.provider_metadata
    archived = subs.get_subscription_by_provider_id("sub_pg_old")
    assert archived.id == old.id and archived.is_current is False
    assert archived.status == "active" and archived.provider_metadata.get("last_charge_event_id") == "pgb_old_2"
    assert sum(1 for row in subs.list_subscription_history(USER) if row.is_current) == 1


def test_b02_webhook_and_admin_reconcile_finish_with_a_two_connection_pool(pool, clean):
    """B1-B02 (reviewer): a webhook delivery and an admin reconciliation compete
    for the same subscription on a pool of exactly two connections. Neither may
    hold a pooled connection while waiting for the per-subscription lock — the
    other party needs that connection for its own reads and writes — so both
    must finish within the timeout and the row must end at the latest provider
    state. A nested checkout (lock connection + working connection per party)
    would exhaust the pool and deadlock here."""

    from psycopg_pool import ConnectionPool

    subs_seed = clean
    subs_seed.create_subscription_record(
        USER, tier="plus", status="active", provider_subscription_id="sub_pg_2",
        provider_plan_id="plan_plus", provider_customer_id="cust_1",
        billing_period_start=_ts(SEP), billing_period_end=_ts(OCT),
    )
    small = ConnectionPool(conninfo=PG_URL, min_size=1, max_size=2, open=True, timeout=5.0)
    try:
        fake = _TruthProvider()
        fake.status = "pending"      # older truth, answered to the webhook (A)
        fake.current_end = OCT
        fake.hold_for = "A"
        subs = PostgresSubscriptionRepository(small)
        events = PostgresWebhookEventRepository(small)
        service = SubscriptionService(subs, fake, PLAN_IDS, public_key_id=KEY_ID)
        processor = WebhookProcessor(
            events=events, subscriptions=subs, service=service,
            secrets=WebhookSecrets(current=WHSEC, previous=None), charges=None,
        )
        done: dict[str, object] = {}
        errors: list[str] = []

        def webhook():
            try:
                raw = _raw(_event_payload("subscription.pending", sub_id="sub_pg_2"))
                done["webhook"] = processor.process_delivery(raw, _sign_body(raw, WHSEC), "pgb_two_A")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"webhook: {exc!r}")

        def admin():
            try:
                done["admin"] = service.reconcile_current(USER)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"admin: {exc!r}")

        a = threading.Thread(target=webhook)
        a.start()
        assert fake.entered.wait(timeout=5)       # A holds the lock, inside its GET
        with fake._lock:
            fake.status = "active"                # provider moves on
            fake.current_end = NOV
        b = threading.Thread(target=admin)
        b.start()
        b.join(timeout=0.5)
        assert b.is_alive()                       # B waits for the lock, not overtaking
        fake.release.set()
        a.join(timeout=15)
        b.join(timeout=15)
        assert not a.is_alive() and not b.is_alive(), "a party did not finish: pool deadlock"
        assert errors == [], errors
        assert done["webhook"].status_code == 200  # type: ignore[union-attr]
        assert fake.order == ["pending", "active"]
        current = subs.get_current_subscription(USER)
        assert current.status == "active"
        assert current.billing_period_end == _ts(NOV)
        assert done["admin"].status == "active"  # type: ignore[union-attr]
        with small.connection() as conn:
            row = conn.execute(
                "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND classid = 872013"
            ).fetchone()
        assert int(row[0]) == 0
    finally:
        small.close()
