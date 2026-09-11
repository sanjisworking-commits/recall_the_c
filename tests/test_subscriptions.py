"""Milestone 2A: Playground subscription catalogue, persistence, Razorpay adapter.

Does not exercise checkout, webhooks, or entitlement inversion.
"""

from __future__ import annotations

import ast
import logging
import re
import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.multiuser.settings import (
    MultiUserSettings,
    clear_settings_cache,
)
from constitution_memorizer.progress.user_ids import LOCAL_USER_ID
from constitution_memorizer.subscriptions.catalog import (
    ANNUAL_PRODUCTS,
    PRODUCTS,
    SUBSCRIPTION_TIERS,
    UnknownSubscriptionTier,
    get_subscription_product,
    list_subscription_products,
)
from constitution_memorizer.subscriptions.config import (
    PLAN_ID_ENV_KEYS,
    plan_ids_from_settings,
    require_plan_id,
)
from constitution_memorizer.subscriptions.db import SCHEMA_SQL, ensure_sqlite_schema
from constitution_memorizer.subscriptions.errors import (
    CurrentSubscriptionExistsError,
    DuplicateProviderSubscriptionError,
    InvalidSubscriptionValue,
    SubscriptionAuthError,
    SubscriptionConfigError,
    SubscriptionNetworkError,
    SubscriptionRejectedError,
    SubscriptionResponseError,
    SubscriptionValidationError,
)
from constitution_memorizer.subscriptions.models import (
    PROVIDER_RAZORPAY,
    SUBSCRIPTION_STATUSES,
    UserSubscription,
    require_provider,
    require_status,
    require_tier,
)
from constitution_memorizer.subscriptions.postgres import (
    PostgresSubscriptionRepository,
    UniqueViolation,
)
from constitution_memorizer.subscriptions.razorpay import (
    RAZORPAY_SUBSCRIPTIONS_URL,
    CreateSubscriptionRequest,
    ProviderSubscription,
    RazorpaySubscriptionsClient,
    _create_payload,
    normalize_provider_subscription,
)
from constitution_memorizer.subscriptions.repository import SqliteSubscriptionRepository
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.entitlements import is_subscribed
from constitution_memorizer.web import billing as legacy_billing
from constitution_memorizer.web import pricing as legacy_pricing

ROOT = Path(__file__).resolve().parents[1]
MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
MIGRATION = ROOT / "alembic" / "versions" / "20260911_0018_user_subscription.py"
USER_A = UUID("11111111-1111-4111-8111-111111111111")
USER_B = UUID("22222222-2222-4222-8222-222222222222")
SECRET = "super-secret-razorpay-key"

EXPECTED_PRODUCTS = {
    "plus": dict(
        display_name="Plus",
        price_inr=199,
        amount_paise=19900,
        playground_law_limit=10,
    ),
    "pro": dict(
        display_name="Pro",
        price_inr=399,
        amount_paise=39900,
        playground_law_limit=30,
    ),
    "max": dict(
        display_name="Max",
        price_inr=999,
        amount_paise=99900,
        playground_law_limit=None,
    ),
}


@pytest.fixture(autouse=True)
def _clear_settings():
    clear_settings_cache()
    yield
    clear_settings_cache()


def _settings(**overrides) -> MultiUserSettings:
    base = {
        "APP_ENV": "test",
        "MULTIUSER_ENABLED": "false",
        "SESSION_SECRET": "test-secret",
        "DATABASE_URL": "",
    }
    base.update({k: str(v) for k, v in overrides.items()})
    return MultiUserSettings(_env_file=None, **base)


def _sqlite_repo() -> SqliteSubscriptionRepository:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_sqlite_schema(conn)
    return SqliteSubscriptionRepository(conn)


def _period() -> tuple[datetime, datetime]:
    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    end = datetime(2026, 10, 1, tzinfo=timezone.utc)
    return start, end


# --------------------------------------------------------------------------- #
# Catalogue
# --------------------------------------------------------------------------- #
def test_canonical_products_are_exactly_plus_pro_max_monthly_gst_inclusive():
    products = list_subscription_products()
    assert tuple(row.tier for row in products) == ("plus", "pro", "max")
    assert SUBSCRIPTION_TIERS == frozenset({"plus", "pro", "max"})
    assert ANNUAL_PRODUCTS == ()
    assert all(row.billing_interval == "monthly" for row in products)
    assert all(row.gst_inclusive is True for row in products)
    assert all(row.currency == "INR" for row in products)
    for row in products:
        expected = EXPECTED_PRODUCTS[row.tier]
        assert row.display_name == expected["display_name"]
        assert row.price_inr == expected["price_inr"]
        assert row.amount_paise == expected["amount_paise"]
        assert row.amount_paise == row.price_inr * 100
        assert row.playground_law_limit == expected["playground_law_limit"]
        assert row == get_subscription_product(row.tier)


@pytest.mark.parametrize("tier", ["premium", "basic", "PLUS", "plus ", "30", "core", "deep", "infinite", ""])
def test_unknown_tiers_fail_without_fallback(tier: str):
    with pytest.raises(UnknownSubscriptionTier) as excinfo:
        get_subscription_product(tier)
    assert tier in str(excinfo.value)
    assert get_subscription_product("plus").tier == "plus"


def test_legacy_duration_catalogue_is_unchanged_and_unmapped():
    assert [plan.days for plan in legacy_pricing.PLANS] == [3, 7, 15, 30, 60, 180, 365]
    assert legacy_pricing.get_plan(999).days == legacy_pricing.DEFAULT_DAYS
    with pytest.raises(UnknownSubscriptionTier):
        get_subscription_product("30")
    with pytest.raises(UnknownSubscriptionTier):
        get_subscription_product("365")
    source = Path(legacy_pricing.__file__).read_text(encoding="utf-8")
    assert "SubscriptionProduct" not in source
    assert "playground_law_limit" not in source


def test_package_is_not_the_legacy_orders_module():
    assert Path(legacy_billing.__file__).name == "billing.py"
    billing_source = Path(legacy_billing.__file__).read_text(encoding="utf-8")
    assert "RAZORPAY_ORDERS_URL" in billing_source
    assert "/v1/subscriptions" not in billing_source
    assert PRODUCTS[0].tier == "plus"


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
def test_plan_id_env_keys_map_only_to_matching_tiers():
    assert PLAN_ID_ENV_KEYS == {
        "plus": "RAZORPAY_PLAN_ID_PLUS",
        "pro": "RAZORPAY_PLAN_ID_PRO",
        "max": "RAZORPAY_PLAN_ID_MAX",
    }
    settings = _settings(
        RAZORPAY_PLAN_ID_PLUS="plan_plus_only",
        RAZORPAY_PLAN_ID_PRO="plan_pro_only",
        RAZORPAY_PLAN_ID_MAX="plan_max_only",
        RAZORPAY_KEY_SECRET=SECRET,
    )
    ids = plan_ids_from_settings(settings)
    assert ids.for_tier("plus") == "plan_plus_only"
    assert ids.for_tier("pro") == "plan_pro_only"
    assert ids.for_tier("max") == "plan_max_only"
    assert require_plan_id(settings, "pro") == "plan_pro_only"
    assert "plan_plus_only" not in (ids.for_tier("pro"), ids.for_tier("max"))
    assert SECRET not in repr(ids)
    assert SECRET not in repr(settings.razorpay_plan_id_plus)


def test_missing_plan_ids_fail_only_when_creation_is_requested():
    settings = _settings()
    settings.validate_for_startup()
    ids = plan_ids_from_settings(settings)
    assert ids.as_mapping() == {"plus": "", "pro": "", "max": ""}
    with pytest.raises(SubscriptionConfigError, match="RAZORPAY_PLAN_ID_PLUS"):
        ids.for_tier("plus")
    with pytest.raises(SubscriptionConfigError, match="RAZORPAY_PLAN_ID_PRO"):
        require_plan_id(settings, "pro")
    with pytest.raises(SubscriptionConfigError, match="RAZORPAY_PLAN_ID_MAX"):
        require_plan_id(settings, "max")
    with pytest.raises(UnknownSubscriptionTier):
        require_plan_id(settings, "premium")


def test_settings_have_no_annual_plan_id_fields():
    fields = MultiUserSettings.model_fields
    assert "razorpay_plan_id_plus" in fields
    assert "razorpay_plan_id_pro" in fields
    assert "razorpay_plan_id_max" in fields
    assert "razorpay_key_id" in fields
    assert "razorpay_key_secret" in fields
    annual = [name for name in fields if "annual" in name.lower()]
    assert annual == []


def test_env_example_documents_shared_keys_and_monthly_plan_ids():
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "RAZORPAY_KEY_ID=" in text
    assert "RAZORPAY_KEY_SECRET=" in text
    assert "RAZORPAY_PLAN_ID_PLUS=" in text
    assert "RAZORPAY_PLAN_ID_PRO=" in text
    assert "RAZORPAY_PLAN_ID_MAX=" in text
    assert "RAZORPAY_PLAN_ID_ANNUAL" not in text
    assert "RAZORPAY_WEBHOOK_SECRET" not in text
    assert text.count("RAZORPAY_KEY_ID=") == 1
    assert text.count("RAZORPAY_KEY_SECRET=") == 1


# --------------------------------------------------------------------------- #
# Persistence — SQLite
# --------------------------------------------------------------------------- #
def test_create_and_retrieve_current_subscription():
    repo = _sqlite_repo()
    start, end = _period()
    stored = repo.create_subscription_record(
        USER_A,
        tier="plus",
        status="created",
        provider_customer_id="cust_1",
        provider_subscription_id="sub_1",
        provider_plan_id="plan_plus",
        billing_period_start=start,
        billing_period_end=end,
        cancel_at_period_end=False,
        provider_metadata={"short_url": "https://rzp.io/i/x"},
    )
    assert stored.user_id == str(USER_A)
    assert stored.provider == PROVIDER_RAZORPAY
    assert stored.tier == "plus"
    assert stored.status == "created"
    assert stored.provider_subscription_id == "sub_1"
    assert stored.is_current is True
    assert stored.cancel_at_period_end is False
    assert stored.billing_period_start == start
    assert stored.billing_period_end == end
    assert stored.provider_metadata["short_url"] == "https://rzp.io/i/x"
    current = repo.get_current_subscription(USER_A)
    assert current is not None
    assert current.id == stored.id
    by_provider = repo.get_subscription_by_provider_id("sub_1")
    assert by_provider is not None
    assert by_provider.id == stored.id
    assert repo.get_subscription_by_provider_id("missing") is None
    assert repo.get_current_subscription(USER_B) is None


def test_update_status_bounds_cancel_flag_and_metadata_round_trip():
    repo = _sqlite_repo()
    start, end = _period()
    stored = repo.create_subscription_record(
        USER_A,
        tier="pro",
        status="authenticated",
        provider_metadata={"n": 1},
    )
    updated = repo.update_subscription_state(
        USER_A,
        stored.id,
        status="active",
        billing_period_start=start,
        billing_period_end=end,
        cancel_at_period_end=True,
        provider_metadata={"n": 2, "nested": {"ok": True}},
    )
    assert updated.status == "active"
    assert updated.billing_period_start == start
    assert updated.billing_period_end == end
    assert updated.cancel_at_period_end is True
    assert updated.provider_metadata == {"n": 2, "nested": {"ok": True}}
    again = repo.get_subscription(USER_A, stored.id)
    assert again is not None
    assert again.provider_metadata["nested"]["ok"] is True


def test_historical_row_is_retained_when_replaced():
    repo = _sqlite_repo()
    first = repo.create_subscription_record(
        USER_A,
        tier="plus",
        status="cancelled",
        provider_subscription_id="sub_old",
        is_current=True,
    )
    repo.mark_not_current(USER_A, first.id)
    second = repo.create_subscription_record(
        USER_A,
        tier="max",
        status="active",
        provider_subscription_id="sub_new",
    )
    current = repo.get_current_subscription(USER_A)
    assert current is not None
    assert current.id == second.id
    assert current.tier == "max"
    history = repo.list_subscription_history(USER_A)
    assert [row.id for row in history] == [first.id, second.id]
    old = repo.get_subscription(USER_A, first.id)
    assert old is not None
    assert old.is_current is False
    assert old.provider_subscription_id == "sub_old"
    assert repo.get_subscription_by_provider_id("sub_old") is not None


def test_two_current_subscriptions_for_same_user_are_rejected():
    repo = _sqlite_repo()
    repo.create_subscription_record(USER_A, tier="plus", status="active")
    with pytest.raises(CurrentSubscriptionExistsError):
        repo.create_subscription_record(USER_A, tier="pro", status="created")
    assert len(repo.list_subscription_history(USER_A)) == 1


def test_duplicate_provider_subscription_id_is_rejected():
    repo = _sqlite_repo()
    repo.create_subscription_record(
        USER_A,
        tier="plus",
        status="active",
        provider_subscription_id="sub_shared",
    )
    with pytest.raises(DuplicateProviderSubscriptionError):
        repo.create_subscription_record(
            USER_B,
            tier="pro",
            status="created",
            provider_subscription_id="sub_shared",
        )


def test_user_a_subscription_is_not_visible_as_user_b():
    repo = _sqlite_repo()
    stored = repo.create_subscription_record(USER_A, tier="plus", status="active")
    assert repo.get_subscription(USER_B, stored.id) is None
    assert repo.get_current_subscription(USER_B) is None
    assert repo.list_subscription_history(USER_B) == []
    with pytest.raises(InvalidSubscriptionValue):
        repo.update_subscription_state(USER_B, stored.id, status="cancelled")
    with pytest.raises(InvalidSubscriptionValue):
        repo.mark_not_current(USER_B, stored.id)
    assert repo.get_current_subscription(USER_A) is not None


@pytest.mark.parametrize("status", sorted(SUBSCRIPTION_STATUSES))
def test_allowed_statuses_persist(status: str):
    repo = _sqlite_repo()
    stored = repo.create_subscription_record(
        USER_A,
        tier="plus",
        status=status,
        is_current=True,
    )
    assert stored.status == status


@pytest.mark.parametrize("tier", ["premium", "basic"])
@pytest.mark.parametrize("status", ["subscribed", "paid", "past_due"])
def test_invalid_normalized_tier_and_status_rejected(tier: str, status: str):
    repo = _sqlite_repo()
    with pytest.raises(InvalidSubscriptionValue):
        require_tier(tier)
    with pytest.raises(InvalidSubscriptionValue):
        require_status(status)
    with pytest.raises(InvalidSubscriptionValue):
        repo.create_subscription_record(USER_A, tier=tier, status="active")
    with pytest.raises(InvalidSubscriptionValue):
        repo.create_subscription_record(USER_A, tier="plus", status=status)


def test_sqlite_check_rejects_raw_invalid_tier_and_status():
    repo = _sqlite_repo()
    with pytest.raises(sqlite3.IntegrityError):
        repo.conn.execute(
            """
            INSERT INTO user_subscription (
                id, user_id, provider, tier, status, cancel_at_period_end,
                is_current, provider_metadata, created_at, updated_at
            ) VALUES ('raw-1', ?, 'razorpay', 'premium', 'active', 0, 1, '{}', 't', 't')
            """,
            (str(USER_A),),
        )
    with pytest.raises(sqlite3.IntegrityError):
        repo.conn.execute(
            """
            INSERT INTO user_subscription (
                id, user_id, provider, tier, status, cancel_at_period_end,
                is_current, provider_metadata, created_at, updated_at
            ) VALUES ('raw-2', ?, 'razorpay', 'plus', 'past_due', 0, 1, '{}', 't', 't')
            """,
            (str(USER_A),),
        )


def test_sqlite_schema_has_one_current_partial_index_and_no_roster_columns():
    assert "user_subscription_one_current" in SCHEMA_SQL
    assert "WHERE is_current = 1" in SCHEMA_SQL
    assert "playground_period" not in SCHEMA_SQL
    assert "law_limit" not in SCHEMA_SQL
    repo = _sqlite_repo()
    columns = {
        row["name"]
        for row in repo.conn.execute("PRAGMA table_info(user_subscription)")
    }
    assert "provider_subscription_id" in columns
    assert "billing_period_start" in columns
    assert "billing_period_end" in columns
    assert "cancel_at_period_end" in columns
    assert "provider_metadata" in columns
    assert "key_secret" not in columns
    assert "playground_period_start" not in columns
    indexes = list(repo.conn.execute("PRAGMA index_list(user_subscription)"))
    names = {row["name"] for row in indexes}
    assert "user_subscription_one_current" in names
    assert "user_subscription_provider_sub_id" in names


def test_user_subscription_domain_object_has_no_secret_or_roster_fields():
    fields = set(UserSubscription.__dataclass_fields__)
    assert "provider_subscription_id" in fields
    assert "key_secret" not in fields
    assert "playground_period_start" not in fields
    assert "device_key_hash" not in fields
    require_provider("razorpay")
    with pytest.raises(InvalidSubscriptionValue):
        require_provider("stripe")


# --------------------------------------------------------------------------- #
# Persistence — Postgres repository (fake pool)
# --------------------------------------------------------------------------- #
class _PgCursor:
    def __init__(self, store: "_PgStore") -> None:
        self.store = store
        self._row = None
        self._rows: list[dict] = []
        self.sql: list[str] = []

    def execute(self, sql: str, params=None):
        self.sql.append(sql)
        self.store.sql.append(sql)
        self.store.params.append(params)
        if self.store.raise_on_execute is not None:
            exc = self.store.raise_on_execute
            self.store.raise_on_execute = None
            raise exc
        self._row, self._rows = self.store.execute(sql, params or ())

    def fetchone(self):
        return self._row

    def fetchall(self):
        return list(self._rows)

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


class _PgConn:
    def __init__(self, store: "_PgStore") -> None:
        self.store = store
        self.commits = 0

    def cursor(self, row_factory=None):
        return _PgCursor(self.store)

    def commit(self):
        self.commits += 1

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


class _PgStore:
    def __init__(self) -> None:
        self.rows: dict[str, dict] = {}
        self.sql: list[str] = []
        self.params: list[tuple] = []
        self.raise_on_execute = None

    @contextmanager
    def connection(self):
        yield _PgConn(self)

    def execute(self, sql: str, params: tuple):
        compact = " ".join(sql.split())
        lowered = compact.lower()
        if lowered.startswith("insert into user_subscription"):
            payload = params[12]
            meta = getattr(payload, "obj", payload)
            if not isinstance(meta, dict):
                meta = {}
            is_current = bool(params[11])
            user_id = str(params[1])
            provider_sub = params[4]
            if is_current and any(
                row["user_id"] == user_id and row["is_current"]
                for row in self.rows.values()
            ):
                raise UniqueViolation("user_subscription_one_current")
            if provider_sub and any(
                row["provider_subscription_id"] == provider_sub
                for row in self.rows.values()
            ):
                raise UniqueViolation("user_subscription_provider_sub_id")
            row = {
                "id": str(params[0]),
                "user_id": user_id,
                "provider": params[2],
                "provider_customer_id": params[3],
                "provider_subscription_id": provider_sub,
                "provider_plan_id": params[5],
                "tier": params[6],
                "status": params[7],
                "billing_period_start": params[8],
                "billing_period_end": params[9],
                "cancel_at_period_end": bool(params[10]),
                "is_current": is_current,
                "provider_metadata": dict(meta),
                "created_at": params[13],
                "updated_at": params[14],
            }
            self.rows[row["id"]] = row
            return row, [row]
        if "set is_current = false" in lowered:
            user_id, subscription_id = str(params[1]), str(params[2])
            row = self.rows.get(subscription_id)
            if row is None or row["user_id"] != user_id:
                return None, []
            row = dict(row)
            row["is_current"] = False
            row["updated_at"] = params[0]
            self.rows[subscription_id] = row
            return row, [row]
        if lowered.startswith("update user_subscription"):
            subscription_id = str(params[-1])
            user_id = str(params[-2])
            row = self.rows.get(subscription_id)
            if row is None or row["user_id"] != user_id:
                return None, []
            payload = params[7]
            meta = getattr(payload, "obj", payload)
            row = dict(row)
            row.update(
                {
                    "status": params[0],
                    "billing_period_start": params[1],
                    "billing_period_end": params[2],
                    "cancel_at_period_end": bool(params[3]),
                    "provider_customer_id": params[4],
                    "provider_subscription_id": params[5],
                    "provider_plan_id": params[6],
                    "provider_metadata": dict(meta) if isinstance(meta, dict) else {},
                    "updated_at": params[8],
                }
            )
            self.rows[subscription_id] = row
            return row, [row]
        if "and is_current = true" in lowered:
            user_id = str(params[0])
            match = next(
                (
                    row
                    for row in self.rows.values()
                    if row["user_id"] == user_id and row["is_current"]
                ),
                None,
            )
            return match, [match] if match else []
        if "provider_subscription_id = %s" in lowered and "provider = %s" in lowered:
            provider, provider_sub = params[0], params[1]
            match = next(
                (
                    row
                    for row in self.rows.values()
                    if row["provider"] == provider
                    and row["provider_subscription_id"] == provider_sub
                ),
                None,
            )
            return match, [match] if match else []
        if "user_id = %s and id = %s" in lowered:
            user_id, subscription_id = str(params[0]), str(params[1])
            row = self.rows.get(subscription_id)
            if row is None or row["user_id"] != user_id:
                return None, []
            return row, [row]
        if "where user_id = %s" in lowered:
            user_id = str(params[0])
            rows = [row for row in self.rows.values() if row["user_id"] == user_id]
            rows.sort(key=lambda row: str(row["created_at"]))
            return (rows[0] if rows else None), rows
        raise AssertionError(f"unexpected SQL: {compact}")


def test_postgres_repository_create_get_update_history_and_isolation():
    store = _PgStore()
    repo = PostgresSubscriptionRepository(store)
    start, end = _period()
    stored = repo.create_subscription_record(
        USER_A,
        tier="plus",
        status="active",
        provider_subscription_id="sub_pg",
        billing_period_start=start,
        billing_period_end=end,
        provider_metadata={"k": "v"},
    )
    assert stored.provider_metadata["k"] == "v"
    assert repo.get_current_subscription(USER_A).id == stored.id
    assert repo.get_subscription_by_provider_id("sub_pg").id == stored.id
    updated = repo.update_subscription_state(
        USER_A,
        stored.id,
        status="pending",
        cancel_at_period_end=True,
    )
    assert updated.status == "pending"
    assert updated.cancel_at_period_end is True
    repo.mark_not_current(USER_A, stored.id)
    second = repo.create_subscription_record(
        USER_A, tier="max", status="created", provider_subscription_id="sub_pg_2"
    )
    assert repo.get_current_subscription(USER_A).id == second.id
    assert len(repo.list_subscription_history(USER_A)) == 2
    assert repo.get_subscription(USER_B, stored.id) is None
    assert repo.get_current_subscription(USER_B) is None
    assert any("is_current = TRUE" in " ".join(sql.split()) for sql in store.sql)
    assert all("%s" in sql for sql in store.sql)


def test_postgres_repository_rejects_second_current_and_wrong_user_updates():
    store = _PgStore()
    repo = PostgresSubscriptionRepository(store)
    stored = repo.create_subscription_record(USER_A, tier="plus", status="active")
    with pytest.raises(CurrentSubscriptionExistsError):
        repo.create_subscription_record(USER_A, tier="pro", status="created")
    with pytest.raises(InvalidSubscriptionValue):
        repo.update_subscription_state(USER_B, stored.id, status="cancelled")
    store.raise_on_execute = UniqueViolation("user_subscription_one_current")
    with pytest.raises(CurrentSubscriptionExistsError):
        repo.create_subscription_record(USER_B, tier="plus", status="created")


# --------------------------------------------------------------------------- #
# Provider adapter
# --------------------------------------------------------------------------- #
class _FakeResponse:
    def __init__(self, status_code: int, payload=None, text: str = ""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


def _patch_httpx(monkeypatch: pytest.MonkeyPatch, response=None, error=None):
    calls: list[dict] = []

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.kwargs = kwargs

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def post(self, url, auth=None, json=None):
            calls.append({"url": url, "auth": auth, "json": json})
            if error is not None:
                raise error
            return response

    monkeypatch.setattr(
        "constitution_memorizer.subscriptions.razorpay.httpx.Client",
        FakeClient,
    )
    return calls


def test_create_subscription_posts_expected_payload_and_normalizes(monkeypatch):
    payload = {
        "id": "sub_abc",
        "plan_id": "plan_plus",
        "status": "created",
        "current_start": None,
        "current_end": None,
        "customer_id": "cust_1",
        "short_url": "https://rzp.io/i/sub",
        "has_scheduled_changes": False,
    }
    calls = _patch_httpx(monkeypatch, response=_FakeResponse(200, payload))
    client = RazorpaySubscriptionsClient("rzp_test_id", SECRET)
    result = client.create_subscription(
        CreateSubscriptionRequest(
            plan_id="plan_plus",
            total_count=24,
            customer_notify=False,
            notes={"user_id": str(USER_A)},
        )
    )
    assert calls[0]["url"] == RAZORPAY_SUBSCRIPTIONS_URL
    assert RAZORPAY_SUBSCRIPTIONS_URL == "https://api.razorpay.com/v1/subscriptions"
    assert calls[0]["auth"] == ("rzp_test_id", SECRET)
    assert calls[0]["json"] == {
        "plan_id": "plan_plus",
        "quantity": 1,
        "customer_notify": 0,
        "total_count": 24,
        "notes": {"user_id": str(USER_A)},
    }
    assert isinstance(result, ProviderSubscription)
    assert result.id == "sub_abc"
    assert result.plan_id == "plan_plus"
    assert result.status == "created"
    assert result.short_url == "https://rzp.io/i/sub"
    assert result.customer_id == "cust_1"
    assert SECRET not in repr(client)
    assert SECRET not in repr(result)


def test_create_subscription_requires_exactly_one_bound_before_http(monkeypatch):
    calls = _patch_httpx(monkeypatch, response=_FakeResponse(200, {}))
    client = RazorpaySubscriptionsClient("rzp_test_id", SECRET)
    with pytest.raises(SubscriptionValidationError, match="total_count or end_at"):
        client.create_subscription(CreateSubscriptionRequest(plan_id="plan_plus"))
    with pytest.raises(SubscriptionValidationError, match="total_count or end_at"):
        client.create_subscription(
            CreateSubscriptionRequest(plan_id="plan_plus", total_count=12, end_at=1)
        )
    with pytest.raises(SubscriptionValidationError, match="quantity"):
        client.create_subscription(
            CreateSubscriptionRequest(plan_id="plan_plus", total_count=1, quantity=0)
        )
    assert calls == []
    payload = _create_payload(
        CreateSubscriptionRequest(plan_id="plan_plus", end_at=1893456000)
    )
    assert payload == {
        "plan_id": "plan_plus",
        "quantity": 1,
        "customer_notify": 1,
        "end_at": 1893456000,
    }
    assert "total_count" not in payload
    razorpay_path = ROOT / "src" / "constitution_memorizer" / "subscriptions" / "razorpay.py"
    text = razorpay_path.read_text(encoding="utf-8")
    assert "total_count = 12" not in text
    assert "1200" not in text
    assert "100 years" not in text.lower()


@pytest.mark.parametrize(
    "status_code,exc_type",
    [
        (401, SubscriptionAuthError),
        (400, SubscriptionRejectedError),
        (422, SubscriptionRejectedError),
    ],
)
def test_provider_http_errors_are_normalized(
    monkeypatch, status_code, exc_type, caplog
):
    caplog.set_level(logging.ERROR)
    calls = _patch_httpx(
        monkeypatch,
        response=_FakeResponse(
            status_code, payload=None, text=f"denied {SECRET} invalid"
        ),
    )
    client = RazorpaySubscriptionsClient("rzp_test_id", SECRET)
    with pytest.raises(exc_type) as excinfo:
        client.create_subscription(
            CreateSubscriptionRequest(plan_id="plan_plus", total_count=1)
        )
    assert calls
    message = str(excinfo.value)
    assert SECRET not in message
    assert "denied" not in message.lower()
    assert SECRET not in caplog.text


def test_provider_network_and_malformed_response(monkeypatch):
    client = RazorpaySubscriptionsClient("rzp_test_id", SECRET)
    _patch_httpx(monkeypatch, error=httpx.TimeoutException("timed out"))
    with pytest.raises(SubscriptionNetworkError, match="Could not reach"):
        client.create_subscription(
            CreateSubscriptionRequest(plan_id="plan_plus", total_count=1)
        )
    _patch_httpx(monkeypatch, response=_FakeResponse(200, payload=None, text="nope"))
    with pytest.raises(SubscriptionResponseError):
        client.create_subscription(
            CreateSubscriptionRequest(plan_id="plan_plus", total_count=1)
        )
    with pytest.raises(SubscriptionResponseError):
        normalize_provider_subscription({"id": "", "plan_id": "p", "status": "created"})
    with pytest.raises(SubscriptionConfigError):
        RazorpaySubscriptionsClient("", "").create_subscription(
            CreateSubscriptionRequest(plan_id="plan_plus", total_count=1)
        )


def test_missing_credentials_fail_before_http(monkeypatch):
    calls = _patch_httpx(monkeypatch, response=_FakeResponse(200, {}))
    with pytest.raises(SubscriptionConfigError):
        RazorpaySubscriptionsClient("rzp_test_id", "").create_subscription(
            CreateSubscriptionRequest(plan_id="plan_plus", total_count=1)
        )
    assert calls == []


# --------------------------------------------------------------------------- #
# Startup / wiring
# --------------------------------------------------------------------------- #
def test_create_app_starts_without_plan_ids_and_makes_no_razorpay_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    sys.modules.pop("constitution_memorizer.subscriptions.razorpay", None)
    posts: list[str] = []
    original = httpx.Client.post

    def wrapped(self, url, *args, **kwargs):
        posts.append(str(url))
        if "razorpay.com" in str(url):
            raise AssertionError(f"startup must not call Razorpay: {url}")
        return original(self, url, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "post", wrapped)
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "progress.db",
        multiuser_settings=_settings(),
    )
    assert app.state.subscriptions is not None
    assert isinstance(app.state.subscriptions, SqliteSubscriptionRepository)
    assert app.state.subscriptions.get_current_subscription(LOCAL_USER_ID) is None
    assert posts == []
    assert "constitution_memorizer.subscriptions.razorpay" not in sys.modules


def test_create_app_does_not_consult_subscriptions_for_access(tmp_path: Path):
    client = TestClient(
        create_app(units_path=MINI_UNITS, db_path=tmp_path / "progress.db")
    )
    repo = client.app.state.subscriptions
    repo.create_subscription_record(
        LOCAL_USER_ID, tier="max", status="active"
    )
    assert is_subscribed(object()) is False
    playground = Path(ROOT / "src/constitution_memorizer/playground")
    for path in playground.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "user_subscription" not in text
        assert "get_current_subscription" not in text


def test_subscription_package_init_does_not_import_httpx():
    source = (
        ROOT / "src/constitution_memorizer/subscriptions/__init__.py"
    ).read_text(encoding="utf-8")
    assert "httpx" not in source
    assert "razorpay" not in source


# --------------------------------------------------------------------------- #
# Migration
# --------------------------------------------------------------------------- #
def test_migration_0018_schema_indexes_rls_and_downgrade():
    source = MIGRATION.read_text(encoding="utf-8")
    tree = ast.parse(source)
    revision = down_revision = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "revision":
                    revision = ast.literal_eval(node.value)
                if isinstance(target, ast.Name) and target.id == "down_revision":
                    down_revision = ast.literal_eval(node.value)
    assert revision == "20260911_0018"
    assert down_revision == "20260906_0017"
    assert "CREATE TABLE IF NOT EXISTS user_subscription" in source
    assert "provider_subscription_id" in source
    assert "billing_period_start" in source
    assert "billing_period_end" in source
    assert "cancel_at_period_end" in source
    assert "provider_metadata JSONB" in source
    assert "user_subscription_one_current" in source
    assert re.search(
        r"UNIQUE INDEX IF NOT EXISTS user_subscription_one_current\s+"
        r"ON user_subscription \(user_id\) WHERE is_current",
        source,
    )
    assert "WHERE provider_subscription_id IS NOT NULL" in source
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "DROP TABLE IF EXISTS user_subscription" in source
    assert "playground_period" not in source
    assert "past_due" not in source
    assert "'premium'" not in source
    billing = (
        ROOT / "alembic/versions/20260818_0007_billing_orders.py"
    ).read_text(encoding="utf-8")
    assert "user_subscription" not in billing
    assert "plan_days INTEGER NOT NULL" in billing
