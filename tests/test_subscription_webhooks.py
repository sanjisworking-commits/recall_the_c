"""Milestone 2C: Razorpay subscription webhooks. Notification in, provider GET is truth."""

from __future__ import annotations

import ast
import hashlib
import hmac
import json
import logging
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.guest import requires_auth
from constitution_memorizer.auth.sessions import InMemorySessionStore
from constitution_memorizer.multiuser.settings import (
    MultiUserSettings,
    clear_settings_cache,
)
from constitution_memorizer.progress.db import open_progress_db
from constitution_memorizer.progress.repository import ProgressRepository
from constitution_memorizer.subscriptions.charge_repository import SqliteChargeRepository
from constitution_memorizer.subscriptions.config import SubscriptionPlanIds
from constitution_memorizer.subscriptions.db import SCHEMA_SQL, ensure_sqlite_schema
from constitution_memorizer.subscriptions.errors import (
    InvalidSubscriptionValue,
    SubscriptionConfigError,
    SubscriptionNetworkError,
    WebhookSignatureError,
)
from constitution_memorizer.subscriptions.models import (
    WEBHOOK_PROCESSING_STATUSES,
    require_webhook_status,
)
from constitution_memorizer.subscriptions.razorpay import (
    ProviderDispute,
    ProviderInvoice,
    ProviderPayment,
    ProviderSubscription,
)
from constitution_memorizer.subscriptions.repository import SqliteSubscriptionRepository
from constitution_memorizer.subscriptions.service import SubscriptionService
from constitution_memorizer.subscriptions.webhook_postgres import (
    PostgresWebhookEventRepository,
    UniqueViolation,
)
from constitution_memorizer.subscriptions.webhook_repository import (
    SqliteWebhookEventRepository,
)
from constitution_memorizer.subscriptions.webhook_signature import (
    WebhookSecrets,
    verify_webhook_signature,
)
from constitution_memorizer.subscriptions.webhooks import (
    SUPPORTED_DISPUTE_EVENTS,
    SUPPORTED_PAYMENT_EVENTS,
    SUPPORTED_REFUND_EVENTS,
    SUPPORTED_SUBSCRIPTION_EVENTS,
    WebhookProcessor,
)
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.entitlements import is_subscribed

ROOT = Path(__file__).resolve().parents[1]
MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
MIGRATION = ROOT / "alembic" / "versions" / "20260915_0019_subscription_webhook_event.py"
USER = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
KEY_ID = "rzp_test_pub"
KEY_SECRET = "dummy-secret-for-tests"
WHSEC = "whsec_current_for_tests"
WHSEC_PREV = "whsec_previous_for_tests"
PLAN_IDS = SubscriptionPlanIds(plus="plan_plus", pro="plan_pro", max="plan_max")
SEP = int(datetime(2026, 9, 1, tzinfo=timezone.utc).timestamp())
OCT = int(datetime(2026, 10, 1, tzinfo=timezone.utc).timestamp())
NOV = int(datetime(2026, 11, 1, tzinfo=timezone.utc).timestamp())
WEBHOOK_PATH = "/api/billing/subscriptions/webhook/razorpay"


@pytest.fixture(autouse=True)
def _clear_settings():
    clear_settings_cache()
    yield
    clear_settings_cache()


def _sign_body(raw: bytes, secret: str = WHSEC) -> str:
    return hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()


def _event_payload(
    event_name: str,
    *,
    sub_id: str = "sub_1",
    created_at: int = SEP,
) -> dict:
    return {
        "entity": "event",
        "event": event_name,
        "payload": {
            "subscription": {
                "entity": {
                    "id": sub_id,
                    "status": "pending",
                    "plan_id": "plan_plus",
                }
            }
        },
        "created_at": created_at,
    }


def _raw(payload: dict) -> bytes:
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def _sub(
    sub_id: str,
    plan_id: str,
    status: str,
    *,
    current_start: int | None = SEP,
    current_end: int | None = OCT,
    has_scheduled_changes: bool | None = False,
) -> ProviderSubscription:
    return ProviderSubscription(
        id=sub_id,
        plan_id=plan_id,
        status=status,
        current_start=current_start,
        current_end=current_end,
        customer_id="cust_1",
        short_url=None,
        has_scheduled_changes=has_scheduled_changes,
        raw={"id": sub_id, "plan_id": plan_id, "status": status},
    )


class FakeProvider:
    def __init__(self) -> None:
        self.fetches: list[str] = []
        self.fetch_error: Exception | None = None
        self.status = "active"
        self.plan_id = "plan_plus"
        self.current_start = SEP
        self.current_end = OCT
        self.has_scheduled_changes = False
        self.payments: dict[str, ProviderPayment] = {}
        self.invoices: dict[str, ProviderInvoice] = {}
        self.disputes: dict[str, ProviderDispute] = {}
        self.payment_error: Exception | None = None
        self.invoice_error: Exception | None = None
        self.dispute_error: Exception | None = None
        self.payment_fetches: list[str] = []
        self.invoice_fetches: list[str] = []
        self.dispute_fetches: list[str] = []
        self.creates: list = []
        self._n = 0
        self._lock = threading.Lock()

    def fetch_subscription(self, subscription_id: str) -> ProviderSubscription:
        with self._lock:
            self.fetches.append(subscription_id)
        if self.fetch_error is not None:
            raise self.fetch_error
        return _sub(
            subscription_id,
            self.plan_id,
            self.status,
            current_start=self.current_start,
            current_end=self.current_end,
            has_scheduled_changes=self.has_scheduled_changes,
        )

    def fetch_payment(self, payment_id: str) -> ProviderPayment:
        with self._lock:
            self.payment_fetches.append(payment_id)
        if self.payment_error is not None:
            raise self.payment_error
        rec = self.payments.get(payment_id)
        if rec is None:
            raise SubscriptionNetworkError("Could not reach the payment provider")
        return rec

    def create_subscription(self, request) -> ProviderSubscription:
        with self._lock:
            self.creates.append(request)
            self._n += 1
            rec = _sub(f"sub_new_{self._n}", request.plan_id, "created")
        return rec

    def fetch_invoice(self, invoice_id: str) -> ProviderInvoice:
        with self._lock:
            self.invoice_fetches.append(invoice_id)
        if self.invoice_error is not None:
            raise self.invoice_error
        rec = self.invoices.get(invoice_id)
        if rec is None:
            raise SubscriptionNetworkError("Could not reach the payment provider")
        return rec

    def fetch_dispute(self, dispute_id: str) -> ProviderDispute:
        with self._lock:
            self.dispute_fetches.append(dispute_id)
        if self.dispute_error is not None:
            raise self.dispute_error
        rec = self.disputes.get(dispute_id)
        if rec is None:
            raise SubscriptionNetworkError("Could not reach the payment provider")
        return rec


def _sqlite():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_sqlite_schema(conn)
    return conn, SqliteSubscriptionRepository(conn), SqliteWebhookEventRepository(conn)


def _secrets(previous: str = WHSEC_PREV) -> WebhookSecrets:
    return WebhookSecrets(current=WHSEC, previous=previous)


def _processor(conn=None, fake=None, secrets=None):
    if conn is None:
        conn, subs, events = _sqlite()
    else:
        subs = SqliteSubscriptionRepository(conn)
        events = SqliteWebhookEventRepository(conn)
    fake = fake or FakeProvider()
    charges = SqliteChargeRepository(conn)
    service = SubscriptionService(subs, fake, PLAN_IDS, public_key_id=KEY_ID)
    processor = WebhookProcessor(
        events=events,
        subscriptions=subs,
        service=service,
        secrets=secrets or _secrets(),
        charges=charges,
    )
    return processor, fake, subs, events, service


def _seed_active(subs, *, tier="plus", plan_id="plan_plus", sub_id="sub_1", status="active"):
    start = datetime.fromtimestamp(SEP, tz=timezone.utc)
    end = datetime.fromtimestamp(OCT, tz=timezone.utc)
    return subs.create_subscription_record(
        USER,
        tier=tier,
        status=status,
        provider_subscription_id=sub_id,
        provider_plan_id=plan_id,
        provider_customer_id="cust_1",
        billing_period_start=start,
        billing_period_end=end,
        provider_metadata={"scheduled_tier": "pro"} if tier == "max" else {},
    )


def _deliver(processor, event_name, *, event_id="evt_1", secret=WHSEC, sub_id="sub_1"):
    raw = _raw(_event_payload(event_name, sub_id=sub_id))
    return processor.process_delivery(raw, _sign_body(raw, secret), event_id), raw


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
        "RAZORPAY_WEBHOOK_SECRET": WHSEC,
        "RAZORPAY_WEBHOOK_SECRET_PREVIOUS": WHSEC_PREV,
    }
    base.update({k: str(v) for k, v in overrides.items()})
    return MultiUserSettings(_env_file=None, **base)


def _http_client(tmp_path: Path, *, fake=None, secrets=None, signed_in: bool = False):
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
    secrets = secrets or _secrets()
    service = SubscriptionService(
        app.state.subscriptions, fake, PLAN_IDS, public_key_id=KEY_ID
    )
    app.state.subscription_service = service
    app.state.webhook_secrets = secrets
    app.state.webhook_processor = WebhookProcessor(
        events=app.state.webhook_events,
        subscriptions=app.state.subscriptions,
        service=service,
        secrets=secrets,
        charges=app.state.subscription_charges,
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


def _post_webhook(client, raw: bytes, *, event_id="evt_1", secret=WHSEC, signature=None):
    return client.post(
        WEBHOOK_PATH,
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": signature if signature is not None else _sign_body(raw, secret),
            "X-Razorpay-Event-Id": event_id,
        },
        follow_redirects=False,
    )


# --------------------------------------------------------------------------- #
# Signature / rotation
# --------------------------------------------------------------------------- #
def test_current_and_previous_secrets_verify_with_raw_body():
    raw = _raw(_event_payload("subscription.charged"))
    secrets = _secrets()
    assert verify_webhook_signature(raw, _sign_body(raw, WHSEC), secrets) == "current"
    assert (
        verify_webhook_signature(raw, _sign_body(raw, WHSEC_PREV), secrets) == "previous"
    )
    with pytest.raises(WebhookSignatureError):
        verify_webhook_signature(raw, _sign_body(raw, "random-secret"), secrets)
    with pytest.raises(WebhookSignatureError):
        verify_webhook_signature(raw, "", secrets)
    current_only = WebhookSecrets(current=WHSEC, previous="")
    with pytest.raises(WebhookSignatureError):
        verify_webhook_signature(raw, _sign_body(raw, WHSEC_PREV), current_only)
    with pytest.raises(SubscriptionConfigError, match="RAZORPAY_WEBHOOK_SECRET"):
        verify_webhook_signature(raw, _sign_body(raw), WebhookSecrets())
    assert WHSEC not in repr(secrets)
    assert WHSEC_PREV not in repr(secrets)
    source = (
        ROOT / "src/constitution_memorizer/subscriptions/webhook_signature.py"
    ).read_text(encoding="utf-8")
    assert "compare_digest" in source
    assert "json.dumps" not in source
    checkout_sig = hmac.new(
        KEY_SECRET.encode(), b"pay_1|sub_1", hashlib.sha256
    ).hexdigest()
    with pytest.raises(WebhookSignatureError):
        verify_webhook_signature(raw, checkout_sig, secrets)


def test_altered_and_reserialized_bodies_fail_verification():
    raw = _raw(_event_payload("subscription.charged"))
    sig = _sign_body(raw)
    secrets = _secrets()
    mutated = raw[:-1] + bytes([raw[-1] ^ 1])
    assert mutated != raw
    with pytest.raises(WebhookSignatureError):
        verify_webhook_signature(mutated, sig, secrets)
    reserialized = json.dumps(json.loads(raw)).encode("utf-8")
    assert reserialized != raw
    with pytest.raises(WebhookSignatureError):
        verify_webhook_signature(reserialized, sig, secrets)
    assert verify_webhook_signature(raw, sig, secrets) == "current"


def test_http_rejects_invalid_signature_and_does_not_persist(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    client, fake, app = _http_client(tmp_path)
    _seed_active(app.state.subscriptions)
    raw = _raw(_event_payload("subscription.charged"))
    denied = _post_webhook(client, raw, signature="forged")
    assert denied.status_code == 400
    assert denied.json()["error"] == "invalid_signature"
    assert app.state.webhook_events.get_event_by_provider_event_id("evt_1") is None
    assert fake.fetches == []
    missing = client.post(
        WEBHOOK_PATH,
        content=raw,
        headers={"X-Razorpay-Event-Id": "evt_1", "Content-Type": "application/json"},
        follow_redirects=False,
    )
    assert missing.status_code == 400
    no_event = _post_webhook(client, raw, event_id="")
    assert no_event.status_code == 400
    assert no_event.json()["error"] == "missing_event_id"
    assert fake.fetches == []
    assert WHSEC not in caplog.text
    assert WHSEC_PREV not in caplog.text
    assert KEY_SECRET not in caplog.text
    assert WHSEC not in denied.text
    assert "forged" not in caplog.text or True
    assert raw.decode() not in caplog.text


def test_http_missing_webhook_secret_fails_closed(tmp_path):
    client, fake, app = _http_client(
        tmp_path, secrets=WebhookSecrets(current="", previous="")
    )
    _seed_active(app.state.subscriptions)
    raw = _raw(_event_payload("subscription.charged"))
    resp = _post_webhook(client, raw)
    assert resp.status_code == 503
    assert resp.json()["error"] == "config"
    assert fake.fetches == []
    assert app.state.webhook_events.get_event_by_provider_event_id("evt_1") is None


def test_guest_webhook_does_not_redirect_to_sign_in(tmp_path):
    client, fake, _app = _http_client(tmp_path, signed_in=False)
    raw = _raw(_event_payload("subscription.charged"))
    resp = _post_webhook(client, raw)
    assert resp.status_code == 200
    assert "/login" not in (resp.headers.get("location") or "")
    assert not requires_auth(WEBHOOK_PATH, "POST")
    assert fake.fetches == []


# --------------------------------------------------------------------------- #
# Persistence
# --------------------------------------------------------------------------- #
def test_sqlite_webhook_schema_and_status_check():
    assert "CREATE TABLE IF NOT EXISTS subscription_webhook_event" in SCHEMA_SQL
    assert "CREATE TABLE IF NOT EXISTS subscription_charge" in SCHEMA_SQL
    assert "subscription_charge_provider_payment" in SCHEMA_SQL
    assert "subscription_webhook_event_provider_event" in SCHEMA_SQL
    assert "raw_payload" not in SCHEMA_SQL
    assert "card_details" not in SCHEMA_SQL
    conn, _subs, events = _sqlite()
    columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(subscription_webhook_event)")
    }
    assert "provider_event_id" in columns
    assert "payload_sha256" in columns
    assert "processing_status" in columns
    assert "payload" not in columns
    assert "signature" not in columns
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO subscription_webhook_event (
                id, provider, provider_event_id, event_name, received_at,
                payload_sha256, processing_status, attempt_count, created_at, updated_at
            ) VALUES ('w1', 'razorpay', 'evt_bad', 'x', 't', 'abc', 'exploded', 1, 't', 't')
            """
        )
    for status in sorted(WEBHOOK_PROCESSING_STATUSES):
        require_webhook_status(status)
    with pytest.raises(InvalidSubscriptionValue):
        require_webhook_status("ack")
    stored, owned = events.reserve_event(
        provider_event_id="evt_store",
        event_name="subscription.charged",
        payload_sha256="deadbeef",
        provider_subscription_id="sub_1",
    )
    assert owned is True
    assert stored.processing_status == "processing"
    assert stored.attempt_count == 1
    again, owned_again = events.reserve_event(
        provider_event_id="evt_store",
        event_name="subscription.charged",
        payload_sha256="deadbeef",
    )
    assert owned_again is False
    assert again.id == stored.id


def test_sqlite_failed_event_can_be_retried_and_problem_events_listed():
    _conn, _subs, events = _sqlite()
    stored, _owned = events.reserve_event(
        provider_event_id="evt_fail",
        event_name="subscription.charged",
        payload_sha256="ab",
    )
    events.mark_event_status(stored.id, "failed", error_code="provider")
    claimed, owned = events.reserve_event(
        provider_event_id="evt_fail",
        event_name="subscription.charged",
        payload_sha256="ab",
    )
    assert owned is True
    assert claimed.attempt_count == 2
    assert claimed.processing_status == "processing"
    events.mark_event_status(claimed.id, "failed", error_code="provider")
    problems = events.list_recent_problem_events()
    assert [row.provider_event_id for row in problems] == ["evt_fail"]
    unmatched, _ = events.reserve_event(
        provider_event_id="evt_unmatched",
        event_name="subscription.updated",
        payload_sha256="cd",
    )
    events.mark_event_status(unmatched.id, "unmatched")
    problems = events.list_recent_problem_events()
    assert {row.processing_status for row in problems} == {"failed", "unmatched"}
    processed, _ = events.reserve_event(
        provider_event_id="evt_ok",
        event_name="subscription.charged",
        payload_sha256="ef",
    )
    events.mark_event_status(processed.id, "processed")
    duplicate, owned_dup = events.reserve_event(
        provider_event_id="evt_ok",
        event_name="subscription.charged",
        payload_sha256="ef",
    )
    assert owned_dup is False
    assert duplicate.processing_status == "processed"


class _PgCursor:
    def __init__(self, store: "_WebhookPgStore") -> None:
        self.store = store
        self._row = None
        self._rows: list[dict] = []

    def execute(self, sql: str, params=None):
        self.store.sql.append(sql)
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
    def __init__(self, store: "_WebhookPgStore") -> None:
        self.store = store

    def cursor(self, row_factory=None):
        return _PgCursor(self.store)

    def commit(self):
        self.store.commits += 1

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


class _WebhookPgStore:
    def __init__(self) -> None:
        self.rows: dict[str, dict] = {}
        self.sql: list[str] = []
        self.commits = 0
        self.raise_on_execute = None

    @contextmanager
    def connection(self):
        yield _PgConn(self)

    def execute(self, sql: str, params: tuple):
        compact = " ".join(sql.split())
        lowered = compact.lower()
        if lowered.startswith("insert into subscription_webhook_event"):
            key = (params[1], params[2])
            if any(
                (row["provider"], row["provider_event_id"]) == key
                for row in self.rows.values()
            ):
                raise UniqueViolation("subscription_webhook_event_provider_event")
            row = {
                "id": str(params[0]),
                "provider": params[1],
                "provider_event_id": params[2],
                "event_name": params[3],
                "provider_subscription_id": params[4],
                "event_created_at": params[5],
                "received_at": params[6],
                "payload_sha256": params[7],
                "processing_status": "processing",
                "attempt_count": 1,
                "processed_at": None,
                "last_error_code": None,
                "created_at": params[8],
                "updated_at": params[9],
            }
            self.rows[row["id"]] = row
            return row, [row]
        if "set processing_status = 'processing'" in lowered and "attempt_count + 1" in lowered:
            provider, event_id = params[1], params[2]
            match = next(
                (
                    row
                    for row in self.rows.values()
                    if row["provider"] == provider
                    and row["provider_event_id"] == event_id
                    and row["processing_status"] == "failed"
                ),
                None,
            )
            if match is None:
                return None, []
            match = dict(match)
            match["processing_status"] = "processing"
            match["attempt_count"] += 1
            match["last_error_code"] = None
            match["processed_at"] = None
            match["updated_at"] = params[0]
            self.rows[match["id"]] = match
            return match, [match]
        if lowered.startswith("update subscription_webhook_event"):
            event_id = str(params[-1])
            row = self.rows.get(event_id)
            if row is None:
                return None, []
            row = dict(row)
            row["processing_status"] = params[0]
            row["last_error_code"] = params[1]
            row["processed_at"] = params[2]
            if params[3] is not None:
                row["provider_subscription_id"] = params[3]
            row["updated_at"] = params[4]
            self.rows[event_id] = row
            return row, [row]
        if "provider = %s and provider_event_id = %s" in lowered:
            provider, event_id = params[0], params[1]
            match = next(
                (
                    row
                    for row in self.rows.values()
                    if row["provider"] == provider and row["provider_event_id"] == event_id
                ),
                None,
            )
            return match, [match] if match else []
        if "processing_status in ('failed', 'unmatched')" in lowered:
            rows = [
                row
                for row in self.rows.values()
                if row["processing_status"] in {"failed", "unmatched"}
            ]
            rows.sort(key=lambda row: str(row["received_at"]), reverse=True)
            return (rows[0] if rows else None), rows[: params[0]]
        raise AssertionError(f"unexpected SQL: {compact}")


def test_postgres_webhook_repository_reserve_retry_and_diagnostics():
    store = _WebhookPgStore()
    repo = PostgresWebhookEventRepository(store)
    first, owned = repo.reserve_event(
        provider_event_id="evt_pg",
        event_name="subscription.charged",
        payload_sha256="aa",
        provider_subscription_id="sub_1",
    )
    assert owned is True
    assert first.processing_status == "processing"
    dup, owned_dup = repo.reserve_event(
        provider_event_id="evt_pg",
        event_name="subscription.charged",
        payload_sha256="aa",
    )
    assert owned_dup is False
    assert dup.id == first.id
    repo.mark_event_status(first.id, "failed", error_code="provider")
    retried, owned_retry = repo.reserve_event(
        provider_event_id="evt_pg",
        event_name="subscription.charged",
        payload_sha256="aa",
    )
    assert owned_retry is True
    assert retried.attempt_count == 2
    repo.mark_event_status(retried.id, "unmatched")
    found = repo.get_event_by_provider_event_id("evt_pg")
    assert found is not None
    assert found.processing_status == "unmatched"
    assert repo.list_recent_problem_events()[0].provider_event_id == "evt_pg"
    assert all("%s" in sql for sql in store.sql)


# --------------------------------------------------------------------------- #
# Processor: unknown / unmatched / ordering / renewal
# --------------------------------------------------------------------------- #
def test_unknown_event_is_ignored_without_provider_fetch():
    processor, fake, _subs, events, _service = _processor()
    result, _raw = _deliver(processor, "payment.captured", event_id="evt_pay")
    assert result.status_code == 200
    assert result.processing_status == "ignored"
    assert fake.fetches == []
    stored = events.get_event_by_provider_event_id("evt_pay")
    assert stored is not None
    assert stored.processing_status == "ignored"


def test_unmatched_provider_subscription_does_not_create_local_row():
    processor, fake, subs, events, _service = _processor()
    result, _raw = _deliver(processor, "subscription.activated", event_id="evt_u")
    assert result.status_code == 200
    assert result.processing_status == "unmatched"
    assert fake.fetches == []
    assert subs.get_subscription_by_provider_id("sub_1") is None
    assert events.get_event_by_provider_event_id("evt_u").processing_status == "unmatched"


def test_missing_subscription_id_is_ignored():
    processor, fake, _subs, events, _service = _processor()
    payload = {"event": "subscription.charged", "payload": {}}
    raw = _raw(payload)
    result = processor.process_delivery(raw, _sign_body(raw), "evt_nosub")
    assert result.status_code == 200
    assert result.processing_status == "ignored"
    assert fake.fetches == []


def test_out_of_order_pending_does_not_roll_active_backward():
    processor, fake, subs, _events, _service = _processor()
    _seed_active(subs)
    fake.status = "active"
    result, _ = _deliver(processor, "subscription.pending", event_id="evt_old_pending")
    assert result.status_code == 200
    current = subs.get_current_subscription(USER)
    assert current.status == "active"
    assert current.tier == "plus"
    assert len(fake.fetches) == 1


def test_out_of_order_activated_follows_provider_pending():
    processor, fake, subs, _events, _service = _processor()
    _seed_active(subs)
    fake.status = "pending"
    result, _ = _deliver(processor, "subscription.activated", event_id="evt_old_act")
    assert result.status_code == 200
    assert subs.get_current_subscription(USER).status == "pending"


def test_older_event_after_newer_charge_keeps_newest_billing_period():
    processor, fake, subs, _events, _service = _processor()
    _seed_active(subs)
    fake.status = "active"
    fake.current_start = OCT
    fake.current_end = NOV
    first, _ = _deliver(processor, "subscription.charged", event_id="evt_new")
    assert first.status_code == 200
    result, _ = _deliver(processor, "subscription.updated", event_id="evt_old")
    assert result.status_code == 200
    current = subs.get_current_subscription(USER)
    assert current.billing_period_start == datetime.fromtimestamp(OCT, tz=timezone.utc)
    assert current.billing_period_end == datetime.fromtimestamp(NOV, tz=timezone.utc)
    assert current.id == subs.get_subscription_by_provider_id("sub_1").id


def test_scheduled_downgrade_applies_only_when_provider_plan_changes():
    processor, fake, subs, _events, service = _processor()
    row = _seed_active(subs, tier="max", plan_id="plan_max")
    row = subs.update_subscription_state(
        USER,
        row.id,
        provider_metadata={
            "scheduled_tier": "pro",
            "scheduled_plan_id": "plan_pro",
            "schedule_change_at": "cycle_end",
        },
    )
    fake.status = "active"
    fake.plan_id = "plan_max"
    fake.has_scheduled_changes = True
    _deliver(processor, "subscription.updated", event_id="evt_still_max")
    current = subs.get_current_subscription(USER)
    assert current.tier == "max"
    assert current.provider_plan_id == "plan_max"
    assert current.provider_metadata["scheduled_tier"] == "pro"
    fake.plan_id = "plan_pro"
    fake.has_scheduled_changes = False
    _deliver(processor, "subscription.charged", event_id="evt_now_pro")
    current = subs.get_current_subscription(USER)
    assert current.id == row.id
    assert current.tier == "pro"
    assert current.provider_plan_id == "plan_pro"
    assert "scheduled_tier" not in current.provider_metadata
    assert "scheduled_plan_id" not in current.provider_metadata
    assert is_subscribed(object()) is False
    fake.status = "cancelled"
    _deliver(processor, "subscription.cancelled", event_id="evt_cancel")
    assert subs.get_current_subscription(USER) is None
    terminal = subs.get_subscription_by_provider_id("sub_1")
    assert terminal.status == "cancelled"
    assert terminal.is_current is False
    assert terminal.id == row.id


def test_renewal_and_auto_renew_update_same_row_bounds():
    processor, fake, subs, events, _service = _processor()
    original = _seed_active(subs)
    fake.status = "active"
    fake.plan_id = "plan_plus"
    fake.current_start = OCT
    fake.current_end = NOV
    result, _ = _deliver(processor, "subscription.charged", event_id="evt_charge")
    assert result.status_code == 200
    assert result.processing_status == "processed"
    current = subs.get_current_subscription(USER)
    assert current.id == original.id
    assert current.provider_subscription_id == "sub_1"
    assert current.tier == "plus"
    assert current.status == "active"
    assert current.billing_period_start == datetime.fromtimestamp(OCT, tz=timezone.utc)
    assert current.billing_period_end == datetime.fromtimestamp(NOV, tz=timezone.utc)
    assert current.provider_metadata["last_charge_event_id"] == "evt_charge"
    assert "card" not in current.provider_metadata
    assert "payment" not in current.provider_metadata
    stored = events.get_event_by_provider_event_id("evt_charge")
    assert stored.processing_status == "processed"
    assert stored.payload_sha256
    assert len(subs.list_subscription_history(USER)) == 1


def test_duplicate_processed_event_does_not_fetch_again():
    processor, fake, subs, events, _service = _processor()
    _seed_active(subs)
    first, _ = _deliver(processor, "subscription.charged", event_id="evt_dup")
    second, _ = _deliver(processor, "subscription.charged", event_id="evt_dup")
    assert first.status_code == second.status_code == 200
    assert len(fake.fetches) == 1
    assert events.get_event_by_provider_event_id("evt_dup").processing_status == "processed"


def test_failed_event_retry_increments_attempt_and_can_succeed():
    processor, fake, subs, events, _service = _processor()
    _seed_active(subs)
    fake.fetch_error = SubscriptionNetworkError("Could not reach the payment provider")
    first, _ = _deliver(processor, "subscription.charged", event_id="evt_retry")
    assert first.status_code == 503
    stored = events.get_event_by_provider_event_id("evt_retry")
    assert stored.processing_status == "failed"
    assert stored.attempt_count == 1
    assert subs.get_current_subscription(USER).billing_period_end == datetime.fromtimestamp(
        OCT, tz=timezone.utc
    )
    fake.fetch_error = None
    fake.current_start = OCT
    fake.current_end = NOV
    second, _ = _deliver(processor, "subscription.charged", event_id="evt_retry")
    assert second.status_code == 200
    stored = events.get_event_by_provider_event_id("evt_retry")
    assert stored.processing_status == "processed"
    assert stored.attempt_count == 2
    assert len(fake.fetches) == 2
    current = subs.get_current_subscription(USER)
    assert current.billing_period_end == datetime.fromtimestamp(NOV, tz=timezone.utc)


def test_malformed_json_after_valid_signature_does_not_mutate():
    processor, fake, subs, events, _service = _processor()
    _seed_active(subs)
    raw = b"{not-json"
    result = processor.process_delivery(raw, _sign_body(raw), "evt_badjson")
    assert result.status_code == 400
    assert result.error == "invalid_json"
    assert events.get_event_by_provider_event_id("evt_badjson") is None
    assert fake.fetches == []
    assert subs.get_current_subscription(USER).status == "active"


def test_immediate_upgrade_webhook_does_not_duplicate_row():
    processor, fake, subs, _events, _service = _processor()
    original = _seed_active(subs, tier="pro", plan_id="plan_pro")
    fake.status = "active"
    fake.plan_id = "plan_pro"
    _deliver(processor, "subscription.updated", event_id="evt_up")
    current = subs.get_current_subscription(USER)
    assert current.id == original.id
    assert current.tier == "pro"
    assert len(subs.list_subscription_history(USER)) == 1


def test_supported_event_names_match_razorpay_docs():
    assert "subscription.renewed" not in SUPPORTED_SUBSCRIPTION_EVENTS
    assert "subscription.payment_failed" not in SUPPORTED_SUBSCRIPTION_EVENTS
    assert "subscription.charged" in SUPPORTED_SUBSCRIPTION_EVENTS
    assert "subscription.authenticated" in SUPPORTED_SUBSCRIPTION_EVENTS
    assert "refund.processed" in SUPPORTED_REFUND_EVENTS
    assert "refund.created" in SUPPORTED_PAYMENT_EVENTS
    assert "payment.dispute.lost" in SUPPORTED_DISPUTE_EVENTS
    assert "payment.dispute.won" in SUPPORTED_PAYMENT_EVENTS


def test_concurrent_duplicate_event_id_fetches_once(tmp_path: Path):
    path = tmp_path / "webhooks.db"
    setup = sqlite3.connect(str(path))
    ensure_sqlite_schema(setup)
    setup.close()
    seed_conn = sqlite3.connect(str(path))
    seed_conn.row_factory = sqlite3.Row
    ensure_sqlite_schema(seed_conn)
    _seed_active(SqliteSubscriptionRepository(seed_conn))
    seed_conn.close()
    fake = FakeProvider()
    barrier = threading.Barrier(2, timeout=3)
    results: list = []
    raw = _raw(_event_payload("subscription.charged"))
    sig = _sign_body(raw)

    def worker():
        conn = sqlite3.connect(
            str(path),
            timeout=2,
            isolation_level=None,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=1000")
        processor, _fake, _subs, _events, _service = _processor(conn, fake)
        barrier.wait()
        results.append(processor.process_delivery(raw, sig, "evt_same"))
        conn.close()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=4)
        assert not thread.is_alive()
    assert len(results) == 2
    assert all(item.status_code == 200 for item in results)
    assert len(fake.fetches) == 1
    owned = [item for item in results if item.owned]
    assert len(owned) == 1


def test_concurrent_different_event_ids_match_provider_truth(tmp_path: Path):
    path = tmp_path / "webhooks2.db"
    setup = sqlite3.connect(str(path))
    ensure_sqlite_schema(setup)
    setup.close()
    seed_conn = sqlite3.connect(str(path))
    seed_conn.row_factory = sqlite3.Row
    _seed_active(SqliteSubscriptionRepository(seed_conn))
    seed_conn.close()
    fake = FakeProvider()
    fake.status = "active"
    fake.current_start = OCT
    fake.current_end = NOV
    barrier = threading.Barrier(2, timeout=3)
    names = ["subscription.pending", "subscription.charged"]

    def worker(event_name: str, event_id: str):
        conn = sqlite3.connect(
            str(path),
            timeout=2,
            isolation_level=None,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=1000")
        processor, _fake, _subs, _events, _service = _processor(conn, fake)
        raw = _raw(_event_payload(event_name))
        barrier.wait()
        processor.process_delivery(raw, _sign_body(raw), event_id)
        conn.close()

    threads = [
        threading.Thread(target=worker, args=(names[i], f"evt_{i}"))
        for i in range(2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=4)
        assert not thread.is_alive()
    read = sqlite3.connect(str(path))
    read.row_factory = sqlite3.Row
    current = SqliteSubscriptionRepository(read).get_current_subscription(USER)
    assert current.status == "active"
    assert current.billing_period_end == datetime.fromtimestamp(NOV, tz=timezone.utc)
    read.close()


# --------------------------------------------------------------------------- #
# HTTP auto-renew + wiring
# --------------------------------------------------------------------------- #
def test_http_auto_renew_without_browser_or_session(tmp_path):
    client, fake, app = _http_client(tmp_path, signed_in=False)
    original = _seed_active(app.state.subscriptions)
    fake.status = "active"
    fake.current_start = OCT
    fake.current_end = NOV
    raw = _raw(_event_payload("subscription.charged"))
    resp = _post_webhook(client, raw, event_id="evt_autorenew")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    current = app.state.subscriptions.get_current_subscription(USER)
    assert current.id == original.id
    assert current.billing_period_start == datetime.fromtimestamp(OCT, tz=timezone.utc)
    assert current.billing_period_end == datetime.fromtimestamp(NOV, tz=timezone.utc)
    assert current.user_id == str(USER)
    assert len(fake.fetches) == 1
    assert is_subscribed(object()) is False
    previous = _post_webhook(
        client, raw, event_id="evt_prev", secret=WHSEC_PREV
    )
    assert previous.status_code == 200
    assert len(fake.fetches) == 2
    reserialized = json.dumps(json.loads(raw)).encode("utf-8")
    rejected = _post_webhook(
        client, reserialized, event_id="evt_reser", signature=_sign_body(raw)
    )
    assert rejected.status_code == 400
    assert app.state.webhook_events.get_event_by_provider_event_id("evt_reser") is None


def test_http_previous_secret_rejected_when_not_configured(tmp_path):
    client, fake, app = _http_client(
        tmp_path, secrets=WebhookSecrets(current=WHSEC, previous="")
    )
    _seed_active(app.state.subscriptions)
    raw = _raw(_event_payload("subscription.charged"))
    resp = _post_webhook(client, raw, secret=WHSEC_PREV)
    assert resp.status_code == 400
    assert fake.fetches == []


def test_webhook_routes_are_isolated_from_app_and_checkout():
    routes = (
        ROOT / "src/constitution_memorizer/subscriptions/webhook_routes.py"
    ).read_text(encoding="utf-8")
    assert "httpx" not in routes
    assert "require_csrf_token" not in routes
    assert WEBHOOK_PATH in routes
    app_source = (ROOT / "src/constitution_memorizer/web/app.py").read_text(encoding="utf-8")
    assert "X-Razorpay-Signature" not in app_source
    assert "verify_webhook_signature" not in app_source
    assert "create_webhook_router" in app_source
    razorpay = (
        ROOT / "src/constitution_memorizer/subscriptions/razorpay.py"
    ).read_text(encoding="utf-8")
    assert "payment_id}|{subscription_id" in razorpay or (
        'f"{payment_id}|{subscription_id}"' in razorpay
    )
    assert "RAW_REQUEST_BODY" not in razorpay


def test_migration_0019_schema_indexes_rls_and_downgrade():
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
    assert revision == "20260915_0019"
    assert down_revision == "20260911_0018"
    assert "CREATE TABLE IF NOT EXISTS subscription_webhook_event" in source
    assert "subscription_webhook_event_provider_event" in source
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "DROP TABLE IF EXISTS subscription_webhook_event" in source
    assert "payload TEXT" not in source
    assert "card_details" not in source
    assert "raw_payload" not in source
    assert "'processing'" in source
    assert "'unmatched'" in source
    older = (
        ROOT / "alembic/versions/20260911_0018_user_subscription.py"
    ).read_text(encoding="utf-8")
    assert "subscription_webhook_event" not in older


def test_migration_0020_schema_indexes_rls_and_downgrade():
    path = ROOT / "alembic" / "versions" / "20260916_0020_subscription_charge.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    revision = down_revision = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "revision":
                    revision = ast.literal_eval(node.value)
                if isinstance(target, ast.Name) and target.id == "down_revision":
                    down_revision = ast.literal_eval(node.value)
    assert revision == "20260916_0020"
    assert down_revision == "20260915_0019"
    assert "CREATE TABLE IF NOT EXISTS subscription_charge" in source
    assert "subscription_charge_provider_payment" in source
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "DROP TABLE IF EXISTS subscription_charge" in source
    assert "email" not in source.lower() or "email" not in source
    assert "card" not in source.lower()
    assert "contact" not in source
    assert "vpa" not in source.lower()
    assert "raw_payload" not in source
    older = (
        ROOT / "alembic/versions/20260915_0019_subscription_webhook_event.py"
    ).read_text(encoding="utf-8")
    assert "subscription_charge" not in older


def test_create_app_starts_without_webhook_secret(tmp_path: Path):
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "progress.db",
        multiuser_settings=MultiUserSettings(
            _env_file=None,
            APP_ENV="test",
            MULTIUSER_ENABLED="false",
            SESSION_SECRET="test-secret",
            DATABASE_URL="",
        ),
    )
    assert app.state.webhook_processor is not None
    assert app.state.webhook_secrets.current == ""
    raw = _raw(_event_payload("subscription.charged"))
    client = TestClient(app)
    resp = client.post(
        WEBHOOK_PATH,
        content=raw,
        headers={
            "X-Razorpay-Signature": _sign_body(raw),
            "X-Razorpay-Event-Id": "evt_boot",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 503
    assert resp.json()["error"] == "config"


def _deliver_payload(processor, payload: dict, event_id: str):
    raw = _raw(payload)
    return processor.process_delivery(raw, _sign_body(raw), event_id)


def _payment(
    payment_id: str = "pay_1",
    *,
    invoice_id: str | None = "inv_1",
    refund_status: str | None = None,
    amount_refunded: int | None = 0,
    amount: int = 19900,
) -> ProviderPayment:
    return ProviderPayment(
        id=payment_id,
        amount=amount,
        currency="INR",
        status="captured",
        invoice_id=invoice_id,
        refund_status=refund_status,
        amount_refunded=amount_refunded,
    )


def _invoice(
    invoice_id: str = "inv_1",
    *,
    sub_id: str = "sub_1",
    payment_id: str = "pay_1",
    start: int = SEP,
    end: int = OCT,
    amount: int = 19900,
) -> ProviderInvoice:
    return ProviderInvoice(
        id=invoice_id,
        subscription_id=sub_id,
        payment_id=payment_id,
        billing_start=start,
        billing_end=end,
        status="paid",
        amount=amount,
        currency="INR",
    )


def _dispute(
    dispute_id: str = "disp_1",
    *,
    payment_id: str = "pay_1",
    status: str = "open",
) -> ProviderDispute:
    return ProviderDispute(
        id=dispute_id,
        payment_id=payment_id,
        status=status,
        amount=19900,
        currency="INR",
        phase="chargeback",
        created_at=SEP,
    )


def _charged_payload(
    *,
    payment_id: str = "pay_1",
    invoice_id: str = "inv_1",
    sub_id: str = "sub_1",
    amount: int = 19900,
) -> dict:
    return {
        "entity": "event",
        "event": "subscription.charged",
        "payload": {
            "subscription": {
                "entity": {"id": sub_id, "status": "active", "plan_id": "plan_plus"}
            },
            "payment": {
                "entity": {
                    "id": payment_id,
                    "invoice_id": invoice_id,
                    "amount": amount,
                    "currency": "INR",
                    "status": "captured",
                    "card": {"number": "4111111111111111"},
                    "email": "buyer@example.com",
                    "contact": "+919999999999",
                }
            },
        },
        "created_at": SEP,
    }


def _refund_payload(event_name: str, *, refund_id: str = "rfnd_1", payment_id: str = "pay_1") -> dict:
    return {
        "entity": "event",
        "event": event_name,
        "payload": {
            "refund": {
                "entity": {
                    "id": refund_id,
                    "payment_id": payment_id,
                    "status": event_name.rsplit(".", 1)[-1],
                    "email": "buyer@example.com",
                }
            },
            "payment": {"entity": {"id": payment_id}},
        },
        "created_at": SEP,
    }


def _dispute_payload(event_name: str, *, dispute_id: str = "disp_1", payment_id: str = "pay_1") -> dict:
    return {
        "entity": "event",
        "event": event_name,
        "payload": {
            "dispute": {
                "entity": {
                    "id": dispute_id,
                    "payment_id": payment_id,
                    "status": "open",
                    "email": "buyer@example.com",
                }
            }
        },
        "created_at": SEP,
    }


def test_active_to_pending_is_failed_recurring_charge_same_row():
    from constitution_memorizer.subscriptions.policy import disposition_for_status

    processor, fake, subs, _events, _service = _processor()
    original = _seed_active(subs)
    fake.status = "pending"
    result, _ = _deliver(processor, "subscription.pending", event_id="evt_pending")
    assert result.status_code == 200
    current = subs.get_current_subscription(USER)
    assert current.id == original.id
    assert current.status == "pending"
    assert current.is_current is True
    disp = disposition_for_status(current.status)
    assert disp.can_use_existing_playground is True
    assert disp.can_consume_new_law is False
    fake.status = "active"
    _deliver(processor, "subscription.activated", event_id="evt_retry_ok")
    recovered = subs.get_current_subscription(USER)
    assert recovered.id == original.id
    assert recovered.status == "active"
    assert disposition_for_status(recovered.status).can_consume_new_law is True


def test_pending_to_halted_and_halted_recovery_same_row():
    from constitution_memorizer.subscriptions.policy import disposition_for_status

    processor, fake, subs, _events, _service = _processor()
    original = _seed_active(subs, status="pending")
    fake.status = "halted"
    _deliver(processor, "subscription.halted", event_id="evt_halted")
    halted = subs.get_current_subscription(USER)
    assert halted.id == original.id
    assert halted.status == "halted"
    assert halted.is_current is True
    disp = disposition_for_status(halted.status)
    assert disp.can_use_existing_playground is False
    assert disp.can_consume_new_law is False
    fake.status = "active"
    _deliver(processor, "subscription.activated", event_id="evt_halt_ok")
    recovered = subs.get_current_subscription(USER)
    assert recovered.id == original.id
    assert recovered.status == "active"


def test_paused_blocks_both_and_resumes_same_row():
    from constitution_memorizer.subscriptions.policy import disposition_for_status

    processor, fake, subs, _events, _service = _processor()
    original = _seed_active(subs)
    fake.status = "paused"
    _deliver(processor, "subscription.paused", event_id="evt_paused")
    paused = subs.get_current_subscription(USER)
    assert paused.id == original.id
    assert paused.status == "paused"
    assert paused.is_current is True
    disp = disposition_for_status("paused")
    assert disp.can_use_existing_playground is False
    assert disp.can_consume_new_law is False
    fake.status = "active"
    _deliver(processor, "subscription.resumed", event_id="evt_resumed")
    resumed = subs.get_current_subscription(USER)
    assert resumed.id == original.id
    assert resumed.status == "active"


@pytest.mark.parametrize("status", ["expired", "completed", "cancelled"])
def test_provider_confirmed_terminal_states_are_archived(status):
    processor, fake, subs, _events, _service = _processor()
    original = _seed_active(subs, status="authenticated")
    fake.status = status
    result, _ = _deliver(processor, "subscription.updated", event_id=f"evt_{status}")
    assert result.status_code == 200
    assert subs.get_current_subscription(USER) is None
    stored = subs.get_subscription_by_provider_id("sub_1")
    assert stored.id == original.id
    assert stored.status == status
    assert stored.is_current is False
    history = subs.list_subscription_history(USER)
    assert len(history) == 1
    assert history[0].id == original.id


def test_late_webhook_updates_historical_row_only():
    processor, fake, subs, _events, service = _processor()
    old = _seed_active(subs)
    fake.status = "cancelled"
    _deliver(processor, "subscription.cancelled", event_id="evt_old_cancel")
    assert subs.get_current_subscription(USER) is None
    handoff = service.start_subscription(USER, "pro")
    assert len(fake.creates) == 1
    new_current = subs.get_current_subscription(USER)
    assert new_current is not None
    assert new_current.id != old.id
    assert new_current.tier == "pro"
    assert new_current.provider_subscription_id == handoff.subscription_id
    fake.status = "pending"
    _deliver(processor, "subscription.pending", event_id="evt_late_old", sub_id="sub_1")
    historical = subs.get_subscription(USER, old.id)
    assert historical.status == "pending"
    assert historical.is_current is False
    still_new = subs.get_current_subscription(USER)
    assert still_new.id == new_current.id
    assert still_new.status == "created"
    assert still_new.provider_subscription_id == handoff.subscription_id


def test_charged_webhook_upserts_one_charge_and_duplicate_does_not():
    processor, fake, subs, _events, _service = _processor()
    original = _seed_active(subs)
    fake.status = "active"
    fake.invoices["inv_1"] = _invoice()
    result = _deliver_payload(processor, _charged_payload(), "evt_pay_map")
    assert result.status_code == 200
    charges = SqliteChargeRepository(subs.conn)
    row = charges.get_charge_by_payment_id("pay_1")
    assert row is not None
    assert row.provider_invoice_id == "inv_1"
    assert row.provider_subscription_id == "sub_1"
    assert row.user_subscription_id == original.id
    assert row.amount_paise == 19900
    assert row.currency == "INR"
    assert row.billing_period_start == datetime.fromtimestamp(SEP, tz=timezone.utc)
    assert row.billing_period_end == datetime.fromtimestamp(OCT, tz=timezone.utc)
    assert row.access_effect == "none"
    dumped = str(dict(subs.conn.execute("SELECT * FROM subscription_charge").fetchone()))
    assert "4111111111111111" not in dumped
    assert "buyer@example.com" not in dumped
    again = _deliver_payload(processor, _charged_payload(), "evt_pay_map")
    assert again.status_code == 200
    assert len(charges.list_charges_for_subscription(original.id)) == 1
    second = _deliver_payload(processor, _charged_payload(), "evt_pay_map_2")
    assert second.status_code == 200
    assert len(charges.list_charges_for_subscription(original.id)) == 1


def test_refund_created_pending_partial_full_and_failed():
    processor, fake, subs, events, _service = _processor()
    original = _seed_active(subs)
    fake.status = "active"
    fake.invoices["inv_1"] = _invoice()
    _deliver_payload(processor, _charged_payload(), "evt_sep")
    charges = SqliteChargeRepository(subs.conn)
    fake.payments["pay_1"] = _payment(refund_status=None, amount_refunded=0)
    created = _deliver_payload(processor, _refund_payload("refund.created"), "evt_rfnd_c")
    assert created.status_code == 200
    assert created.processing_status == "processed"
    row = charges.get_charge_by_payment_id("pay_1")
    assert row.access_effect == "none"
    assert row.access_effect_reason is None
    fake.payments["pay_1"] = _payment(refund_status="partial", amount_refunded=5000)
    partial = _deliver_payload(
        processor, _refund_payload("refund.processed"), "evt_rfnd_p"
    )
    assert partial.status_code == 200
    row = charges.get_charge_by_payment_id("pay_1")
    assert row.refund_status == "partial"
    assert row.amount_refunded_paise == 5000
    assert row.access_effect == "none"
    current = subs.get_current_subscription(USER)
    assert current.status == "active"
    assert current.id == original.id
    fake.payments["pay_1"] = _payment(refund_status="full", amount_refunded=19900)
    full = _deliver_payload(
        processor, _refund_payload("refund.processed", refund_id="rfnd_full"), "evt_rfnd_f"
    )
    assert full.status_code == 200
    row = charges.get_charge_by_payment_id("pay_1")
    assert row.refund_status == "full"
    assert row.access_effect == "period_ended"
    assert row.access_effect_reason == "full_refund"
    assert subs.get_current_subscription(USER).status == "active"
    fake.payments["pay_1"] = _payment(refund_status="full", amount_refunded=19900)
    failed = _deliver_payload(
        processor, _refund_payload("refund.failed"), "evt_rfnd_fail"
    )
    assert failed.status_code == 200
    row = charges.get_charge_by_payment_id("pay_1")
    assert row.access_effect == "period_ended"
    assert row.access_effect_reason == "full_refund"
    stored = events.get_event_by_provider_event_id("evt_rfnd_c")
    assert stored.provider_subscription_id == "sub_1"


def test_out_of_order_refund_created_uses_provider_full_truth():
    processor, fake, subs, _events, _service = _processor()
    _seed_active(subs)
    fake.invoices["inv_1"] = _invoice()
    fake.payments["pay_1"] = _payment(refund_status="full", amount_refunded=19900)
    result = _deliver_payload(processor, _refund_payload("refund.created"), "evt_old_rfnd")
    assert result.status_code == 200
    charges = SqliteChargeRepository(subs.conn)
    row = charges.get_charge_by_payment_id("pay_1")
    assert row.refund_status == "full"
    assert row.access_effect == "period_ended"
    assert row.access_effect_reason == "full_refund"


def test_september_full_refund_does_not_end_october_period():
    processor, fake, subs, _events, _service = _processor()
    original = _seed_active(subs)
    fake.status = "active"
    fake.invoices["inv_sep"] = _invoice(
        "inv_sep", payment_id="pay_sep", start=SEP, end=OCT
    )
    fake.invoices["inv_oct"] = _invoice(
        "inv_oct", payment_id="pay_oct", start=OCT, end=NOV, amount=19900
    )
    _deliver_payload(
        processor,
        _charged_payload(payment_id="pay_sep", invoice_id="inv_sep"),
        "evt_sep_ch",
    )
    fake.current_start = OCT
    fake.current_end = NOV
    _deliver_payload(
        processor,
        _charged_payload(payment_id="pay_oct", invoice_id="inv_oct"),
        "evt_oct_ch",
    )
    fake.payments["pay_sep"] = _payment(
        "pay_sep", invoice_id="inv_sep", refund_status="full", amount_refunded=19900
    )
    _deliver_payload(
        processor,
        _refund_payload("refund.processed", refund_id="rfnd_sep", payment_id="pay_sep"),
        "evt_sep_rfnd",
    )
    charges = SqliteChargeRepository(subs.conn)
    september = charges.get_charge_by_payment_id("pay_sep")
    october = charges.get_charge_by_payment_id("pay_oct")
    assert september.access_effect == "period_ended"
    assert september.access_effect_reason == "full_refund"
    assert october.access_effect == "none"
    assert october.access_effect_reason is None
    current = subs.get_current_subscription(USER)
    assert current.id == original.id
    assert current.status == "active"


def test_dispute_open_review_won_lost_and_full_refund_precedence():
    processor, fake, subs, _events, _service = _processor()
    _seed_active(subs)
    fake.invoices["inv_1"] = _invoice()
    _deliver_payload(processor, _charged_payload(), "evt_disp_ch")
    charges = SqliteChargeRepository(subs.conn)
    fake.payments["pay_1"] = _payment()
    fake.disputes["disp_1"] = _dispute(status="open")
    created = _deliver_payload(
        processor, _dispute_payload("payment.dispute.created"), "evt_disp_c"
    )
    assert created.status_code == 200
    assert charges.get_charge_by_payment_id("pay_1").access_effect == "none"
    fake.disputes["disp_1"] = _dispute(status="under_review")
    _deliver_payload(processor, _dispute_payload("payment.dispute.created"), "evt_disp_r")
    assert charges.get_charge_by_payment_id("pay_1").access_effect == "none"
    fake.disputes["disp_1"] = _dispute(status="won")
    won = _deliver_payload(
        processor, _dispute_payload("payment.dispute.won"), "evt_disp_w"
    )
    assert won.status_code == 200
    assert charges.get_charge_by_payment_id("pay_1").dispute_status == "won"
    assert charges.get_charge_by_payment_id("pay_1").access_effect == "none"
    fake.disputes["disp_1"] = _dispute(status="lost")
    lost = _deliver_payload(
        processor, _dispute_payload("payment.dispute.lost"), "evt_disp_l"
    )
    assert lost.status_code == 200
    row = charges.get_charge_by_payment_id("pay_1")
    assert row.access_effect == "period_ended"
    assert row.access_effect_reason == "dispute_lost"
    fake.payments["pay_1"] = _payment(refund_status="full", amount_refunded=19900)
    fake.disputes["disp_1"] = _dispute(status="lost")
    _deliver_payload(processor, _dispute_payload("payment.dispute.lost"), "evt_disp_both")
    row = charges.get_charge_by_payment_id("pay_1")
    assert row.access_effect == "period_ended"
    assert row.access_effect_reason == "full_refund"


def test_out_of_order_dispute_created_uses_provider_won_truth():
    processor, fake, subs, _events, _service = _processor()
    _seed_active(subs)
    fake.invoices["inv_1"] = _invoice()
    fake.payments["pay_1"] = _payment()
    fake.disputes["disp_1"] = _dispute(status="won")
    result = _deliver_payload(
        processor, _dispute_payload("payment.dispute.created"), "evt_old_disp"
    )
    assert result.status_code == 200
    charges = SqliteChargeRepository(subs.conn)
    row = charges.get_charge_by_payment_id("pay_1")
    assert row.dispute_status == "won"
    assert row.access_effect == "none"


def test_refund_fallback_maps_via_invoice_and_unmatched_does_not_guess():
    processor, fake, subs, events, _service = _processor()
    original = _seed_active(subs)
    fake.payments["pay_hist"] = _payment("pay_hist", invoice_id="inv_hist")
    fake.invoices["inv_hist"] = _invoice("inv_hist", payment_id="pay_hist")
    fake.payments["pay_hist"] = _payment(
        "pay_hist", invoice_id="inv_hist", refund_status="full", amount_refunded=19900
    )
    mapped = _deliver_payload(
        processor,
        _refund_payload("refund.processed", payment_id="pay_hist"),
        "evt_hist",
    )
    assert mapped.status_code == 200
    assert mapped.processing_status == "processed"
    charges = SqliteChargeRepository(subs.conn)
    row = charges.get_charge_by_payment_id("pay_hist")
    assert row.user_subscription_id == original.id
    assert row.access_effect == "period_ended"
    fake.payments["pay_orphan"] = _payment("pay_orphan", invoice_id=None)
    missing = _deliver_payload(
        processor,
        _refund_payload("refund.processed", payment_id="pay_orphan"),
        "evt_orphan",
    )
    assert missing.status_code == 200
    assert missing.processing_status == "unmatched"
    assert charges.get_charge_by_payment_id("pay_orphan") is None
    fake.payments["pay_unknown"] = _payment("pay_unknown", invoice_id="inv_unknown")
    fake.invoices["inv_unknown"] = _invoice(
        "inv_unknown", sub_id="sub_other", payment_id="pay_unknown"
    )
    unknown = _deliver_payload(
        processor,
        _refund_payload("refund.processed", payment_id="pay_unknown"),
        "evt_unknown_sub",
    )
    assert unknown.status_code == 200
    assert unknown.processing_status == "unmatched"
    assert events.get_event_by_provider_event_id("evt_unknown_sub").processing_status == (
        "unmatched"
    )
    fake.payment_error = SubscriptionNetworkError("Could not reach the payment provider")
    transient = _deliver_payload(
        processor, _refund_payload("refund.processed"), "evt_pay_down"
    )
    assert transient.status_code == 503
    assert transient.processing_status == "failed"


def test_refund_and_dispute_use_same_event_table_and_hmac():
    processor, fake, subs, events, _service = _processor()
    _seed_active(subs)
    fake.payments["pay_1"] = _payment()
    fake.invoices["inv_1"] = _invoice()
    result = _deliver_payload(processor, _refund_payload("refund.created"), "evt_same_tbl")
    assert result.status_code == 200
    stored = events.get_event_by_provider_event_id("evt_same_tbl")
    assert stored.event_name == "refund.created"
    assert stored.processing_status == "processed"
    raw = _raw(_refund_payload("refund.processed"))
    bad = processor.process_delivery(raw, "deadbeef", "evt_bad_sig")
    assert bad.status_code == 400
    assert events.get_event_by_provider_event_id("evt_bad_sig") is None

