"""Milestone 2D: access policy, charges, legacy classification. Not entitlement."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

from constitution_memorizer.progress.db import open_progress_db
from constitution_memorizer.progress.repository import ProgressRepository
from constitution_memorizer.subscriptions.charge_postgres import (
    PostgresChargeRepository,
    UniqueViolation,
)
from constitution_memorizer.subscriptions.charge_repository import SqliteChargeRepository
from constitution_memorizer.subscriptions.db import SCHEMA_SQL, ensure_sqlite_schema
from constitution_memorizer.subscriptions.legacy import classify_legacy_paid_access
from constitution_memorizer.subscriptions.models import SUBSCRIPTION_STATUSES
from constitution_memorizer.subscriptions.policy import (
    compute_charge_access_effect,
    disposition_for_status,
)
from constitution_memorizer.subscriptions.repository import SqliteSubscriptionRepository
from constitution_memorizer.web.entitlements import is_subscribed
from constitution_memorizer.web import billing as legacy_billing
from constitution_memorizer.web import pricing as legacy_pricing

ROOT = Path(__file__).resolve().parents[1]
USER = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
NOW = datetime(2026, 9, 15, tzinfo=timezone.utc)


def test_disposition_matches_locked_status_matrix():
    expected = {
        "created": (False, False),
        "authenticated": (False, False),
        "active": (True, True),
        "pending": (True, False),
        "halted": (False, False),
        "paused": (False, False),
        "cancelled": (False, False),
        "completed": (False, False),
        "expired": (False, False),
    }
    assert set(expected) == set(SUBSCRIPTION_STATUSES)
    for status, bits in expected.items():
        disp = disposition_for_status(status)
        assert disp.status == status
        assert (disp.can_use_existing_playground, disp.can_consume_new_law) == bits
    assert is_subscribed(object()) is False


def test_compute_charge_access_effect_is_deterministic():
    assert compute_charge_access_effect(None, None) == ("none", None)
    assert compute_charge_access_effect("partial", "won") == ("none", None)
    assert compute_charge_access_effect("partial", "open") == ("none", None)
    assert compute_charge_access_effect("full", "open") == ("period_ended", "full_refund")
    assert compute_charge_access_effect("partial", "lost") == (
        "period_ended",
        "dispute_lost",
    )
    assert compute_charge_access_effect("full", "lost") == ("period_ended", "full_refund")
    assert compute_charge_access_effect(None, "lost") == ("period_ended", "dispute_lost")
    assert compute_charge_access_effect("pending", None) == ("none", None)


def test_sqlite_charge_upsert_is_unique_on_provider_payment():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_sqlite_schema(conn)
    repo = SqliteChargeRepository(conn)
    first = repo.upsert_charge(
        provider_payment_id="pay_1",
        provider_invoice_id="inv_1",
        amount_paise=19900,
        currency="INR",
    )
    second = repo.upsert_charge(
        provider_payment_id="pay_1",
        refund_status="partial",
        amount_refunded_paise=100,
    )
    assert first.id == second.id
    assert second.refund_status == "partial"
    assert second.amount_refunded_paise == 100
    assert second.access_effect == "none"
    full = repo.upsert_charge(provider_payment_id="pay_1", refund_status="full")
    assert full.access_effect == "period_ended"
    assert full.access_effect_reason == "full_refund"
    columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(subscription_charge)")
    }
    assert "provider_payment_id" in columns
    assert "email" not in columns
    assert "card" not in columns
    assert "contact" not in columns
    assert "CREATE TABLE IF NOT EXISTS subscription_charge" in SCHEMA_SQL


def test_postgres_charge_repository_upsert_and_uniqueness():
    store = _ChargePgStore()
    repo = PostgresChargeRepository(store)
    first = repo.upsert_charge(
        provider_payment_id="pay_pg",
        provider_subscription_id="sub_1",
        amount_paise=39900,
        currency="INR",
    )
    second = repo.upsert_charge(
        provider_payment_id="pay_pg",
        dispute_status="lost",
    )
    assert first.id == second.id
    assert second.access_effect == "period_ended"
    assert second.access_effect_reason == "dispute_lost"
    assert all("%s" in sql for sql in store.sql)


def test_legacy_paid_grant_is_classified_without_tier_or_subscription_row(tmp_path: Path):
    conn = open_progress_db(tmp_path / "progress.db")
    progress = ProgressRepository(conn)
    ends = (datetime.now(timezone.utc) + timedelta(days=300)).isoformat()
    progress.create_billing_order(
        USER,
        order_id="order_legacy",
        plan_days=365,
        amount_paise=99900,
    )
    assert progress.mark_billing_order_paid(
        USER,
        order_id="order_legacy",
        payment_id="pay_legacy",
        grant_id="grant_legacy",
        access_ends_at=ends,
    )
    classified = classify_legacy_paid_access(progress, USER)
    assert classified is not None
    assert classified.classification == "legacy"
    assert classified.tier is None
    assert classified.is_active is True
    assert classified.ends_at is not None
    assert classified.ends_at > datetime.now(timezone.utc) - timedelta(seconds=5)
    assert classified.plan_days == 365
    assert classified.order_id == "order_legacy"
    assert classified.payment_id == "pay_legacy"
    sub_conn = sqlite3.connect(":memory:")
    sub_conn.row_factory = sqlite3.Row
    ensure_sqlite_schema(sub_conn)
    subs = SqliteSubscriptionRepository(sub_conn)
    assert subs.get_current_subscription(USER) is None
    assert subs.list_subscription_history(USER) == []
    assert classified.tier not in {"plus", "pro", "max"}


def test_expired_legacy_grant_is_historical_and_does_not_autostart_subscription(
    tmp_path: Path,
):
    conn = open_progress_db(tmp_path / "progress.db")
    progress = ProgressRepository(conn)
    past_end = (NOW - timedelta(days=1)).isoformat()
    conn.execute(
        """
        INSERT INTO access_grants (
            id, user_id, source, starts_at, ends_at, reason, created_at
        ) VALUES (?, ?, 'payment', ?, ?, ?, ?)
        """,
        (
            "grant_expired",
            str(USER),
            (NOW - timedelta(days=400)).isoformat(),
            past_end,
            "razorpay:order_old",
            NOW.isoformat(),
        ),
    )
    conn.commit()
    classified = classify_legacy_paid_access(progress, USER, now=NOW)
    assert classified is not None
    assert classified.classification == "legacy"
    assert classified.tier is None
    assert classified.is_active is False
    assert classified.ends_at is not None
    assert classified.ends_at <= NOW
    sub_conn = sqlite3.connect(":memory:")
    sub_conn.row_factory = sqlite3.Row
    ensure_sqlite_schema(sub_conn)
    assert SqliteSubscriptionRepository(sub_conn).list_subscription_history(USER) == []


def test_legacy_buyer_may_also_start_a_new_subscription(tmp_path: Path):
    conn = open_progress_db(tmp_path / "progress.db")
    progress = ProgressRepository(conn)
    progress.create_billing_order(
        USER, order_id="order_both", plan_days=365, amount_paise=99900
    )
    progress.mark_billing_order_paid(
        USER,
        order_id="order_both",
        payment_id="pay_both",
        grant_id="grant_both",
        access_ends_at=(datetime.now(timezone.utc) + timedelta(days=10)).isoformat(),
    )
    classified = classify_legacy_paid_access(progress, USER)
    assert classified is not None and classified.is_active is True
    sub_conn = sqlite3.connect(":memory:")
    sub_conn.row_factory = sqlite3.Row
    ensure_sqlite_schema(sub_conn)
    repo = SqliteSubscriptionRepository(sub_conn)
    repo.create_subscription_record(USER, tier="plus", status="created", is_current=True)
    assert repo.get_current_subscription(USER) is not None
    still = classify_legacy_paid_access(progress, USER)
    assert still is not None and still.tier is None


def test_legacy_orders_amounts_and_routes_are_unchanged():
    year = next(plan for plan in legacy_pricing.PLANS if plan.days == 365)
    assert year.price_inr == 999
    billing = Path(legacy_billing.__file__).read_text(encoding="utf-8")
    app_source = (ROOT / "src/constitution_memorizer/web/app.py").read_text(
        encoding="utf-8"
    )
    assert "/api/billing/order" in app_source
    assert "/api/billing/verify" in app_source
    assert "RAZORPAY_ORDERS_URL" in billing
    assert "/v1/subscriptions" not in billing


def test_playground_and_constitution_do_not_import_m2d_policy():
    playground = ROOT / "src/constitution_memorizer/playground"
    for path in playground.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "disposition_for_status" not in text
        assert "SubscriptionAccessDisposition" not in text
        assert "subscription_charge" not in text
    entitlements = (
        ROOT / "src/constitution_memorizer/web/entitlements.py"
    ).read_text(encoding="utf-8")
    assert "disposition_for_status" not in entitlements
    assert "compute_charge_access_effect" not in entitlements
    assert is_subscribed(object()) is False


class _ChargePgCursor:
    def __init__(self, store: "_ChargePgStore") -> None:
        self.store = store
        self._row = None
        self._rows: list = []

    def execute(self, sql: str, params: tuple = ()):
        self._row, self._rows = self.store.execute(sql, params)
        return self

    def fetchone(self):
        return self._row

    def fetchall(self):
        return list(self._rows)

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


class _ChargePgConn:
    def __init__(self, store: "_ChargePgStore") -> None:
        self.store = store

    def cursor(self, row_factory=None):
        return _ChargePgCursor(self.store)

    def commit(self):
        self.store.commits += 1

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


class _ChargePgStore:
    def __init__(self) -> None:
        self.rows: dict[str, dict] = {}
        self.sql: list[str] = []
        self.commits = 0

    @contextmanager
    def connection(self):
        yield _ChargePgConn(self)

    def execute(self, sql: str, params: tuple):
        compact = " ".join(sql.split())
        lowered = compact.lower()
        self.sql.append(compact)
        if lowered.startswith("insert into subscription_charge"):
            key = (params[1], params[2])
            if any(
                (row["provider"], row["provider_payment_id"]) == key
                for row in self.rows.values()
            ):
                raise UniqueViolation("subscription_charge_provider_payment")
            row = {
                "id": str(params[0]),
                "provider": params[1],
                "provider_payment_id": params[2],
                "provider_invoice_id": params[3],
                "provider_subscription_id": params[4],
                "user_subscription_id": params[5],
                "billing_period_start": params[6],
                "billing_period_end": params[7],
                "amount_paise": params[8],
                "currency": params[9],
                "payment_status": params[10],
                "refund_status": params[11],
                "amount_refunded_paise": params[12],
                "last_refund_id": params[13],
                "dispute_id": params[14],
                "dispute_status": params[15],
                "access_effect": params[16],
                "access_effect_reason": params[17],
                "access_effect_at": params[18],
                "created_at": params[19],
                "updated_at": params[20],
            }
            self.rows[row["id"]] = row
            return row, [row]
        if lowered.startswith("update subscription_charge"):
            provider, payment_id = params[-2], params[-1]
            match = next(
                (
                    row
                    for row in self.rows.values()
                    if row["provider"] == provider
                    and row["provider_payment_id"] == payment_id
                ),
                None,
            )
            if match is None:
                return None, []
            match = dict(match)
            match.update(
                {
                    "provider_invoice_id": params[0],
                    "provider_subscription_id": params[1],
                    "user_subscription_id": params[2],
                    "billing_period_start": params[3],
                    "billing_period_end": params[4],
                    "amount_paise": params[5],
                    "currency": params[6],
                    "payment_status": params[7],
                    "refund_status": params[8],
                    "amount_refunded_paise": params[9],
                    "last_refund_id": params[10],
                    "dispute_id": params[11],
                    "dispute_status": params[12],
                    "access_effect": params[13],
                    "access_effect_reason": params[14],
                    "access_effect_at": params[15],
                    "updated_at": params[16],
                }
            )
            self.rows[match["id"]] = match
            return match, [match]
        if "provider_payment_id = %s" in lowered:
            provider, payment_id = params[0], params[1]
            match = next(
                (
                    row
                    for row in self.rows.values()
                    if row["provider"] == provider
                    and row["provider_payment_id"] == payment_id
                ),
                None,
            )
            return match, [match] if match else []
        if "user_subscription_id = %s" in lowered:
            rows = [
                row
                for row in self.rows.values()
                if row["user_subscription_id"] == params[0]
            ]
            return (rows[0] if rows else None), rows
        raise AssertionError(f"unexpected SQL: {compact}")
