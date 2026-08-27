"""Razorpay Standard Checkout: signature math, order/verify endpoints, access."""

from __future__ import annotations

import hashlib
import hmac
from datetime import date
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import InMemorySessionStore
from constitution_memorizer.multiuser.settings import MultiUserSettings
from constitution_memorizer.progress.db import open_progress_db
from constitution_memorizer.progress.repository import ProgressRepository
from constitution_memorizer.web import billing
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.entitlements import status_from_paid_order

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
USER = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
KEY_ID = "rzp_test_dummy"
KEY_SECRET = "dummy-secret-for-tests"


def _sign(order_id: str, payment_id: str, secret: str = KEY_SECRET) -> str:
    return hmac.new(
        secret.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256
    ).hexdigest()


# --------------------------------------------------------------------------- #
# Pure signature verification                                                  #
# --------------------------------------------------------------------------- #
def test_verify_signature_accepts_valid() -> None:
    sig = _sign("order_1", "pay_1")
    assert billing.verify_signature(
        order_id="order_1", payment_id="pay_1", signature=sig, key_secret=KEY_SECRET
    )


@pytest.mark.parametrize(
    "order_id,payment_id,signature",
    [
        ("order_1", "pay_1", "not-the-signature"),
        ("order_2", "pay_1", None),
        ("", "pay_1", "x"),
        ("order_1", "", "x"),
    ],
)
def test_verify_signature_rejects_invalid(order_id, payment_id, signature) -> None:
    assert not billing.verify_signature(
        order_id=order_id,
        payment_id=payment_id,
        signature=signature or "",
        key_secret=KEY_SECRET,
    )


def test_verify_signature_rejects_wrong_secret() -> None:
    sig = _sign("order_1", "pay_1", secret="other-secret")
    assert not billing.verify_signature(
        order_id="order_1", payment_id="pay_1", signature=sig, key_secret=KEY_SECRET
    )


def test_create_order_rejects_below_minimum() -> None:
    with pytest.raises(billing.BillingError) as excinfo:
        billing.create_order(
            key_id=KEY_ID, key_secret=KEY_SECRET, amount_paise=99, receipt="r"
        )
    assert excinfo.value.status_code == 400


# --------------------------------------------------------------------------- #
# Pass-state calculation                                                       #
# --------------------------------------------------------------------------- #
def test_status_from_paid_order_states() -> None:
    today = date(2026, 8, 18)
    active = status_from_paid_order(
        plan_days=180, amount_paise=69900, paid_on=today, today=today
    )
    assert active.state == "active" and active.plan_price_inr == 699
    expiring = status_from_paid_order(
        plan_days=7, amount_paise=9900, paid_on=date(2026, 8, 15), today=today
    )
    assert expiring.state == "expiring"
    lapsed = status_from_paid_order(
        plan_days=3, amount_paise=4900, paid_on=date(2026, 8, 1), today=today
    )
    assert lapsed.state == "lapsed" and lapsed.ended_on is not None
    # Standard Checkout sells passes, never auto-renewals.
    assert not any(s.recurring for s in (active, expiring, lapsed))


# --------------------------------------------------------------------------- #
# Endpoints                                                                    #
# --------------------------------------------------------------------------- #
def _mu_settings(*, keys: bool = True) -> MultiUserSettings:
    return MultiUserSettings(
        _env_file=None,
        APP_ENV="test",
        MULTIUSER_ENABLED="true",
        AUTH_GOOGLE_ENABLED="true",
        SESSION_SECRET="test-secret",
        SUPABASE_URL="http://example.invalid",
        SUPABASE_ANON_KEY="anon",
        DATABASE_URL="",
        COOKIE_SECURE="false",
        ARTICLE_ENTITLEMENTS_ENABLED="true",
        PRICING_ENABLED="true",
        RAZORPAY_KEY_ID=KEY_ID if keys else "",
        RAZORPAY_KEY_SECRET=KEY_SECRET if keys else "",
    )


def _client(tmp_path: Path, *, keys: bool = True, signed_in: bool = True):
    conn = open_progress_db(tmp_path / "progress.db")
    repo = ProgressRepository(conn)
    provider = FakeAuthProvider()
    provider.seed_google_user(user_id=USER, email="a@example.com", display_name="T")
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "unused.db",
        multiuser=True,
        multiuser_settings=_mu_settings(keys=keys),
        auth_provider=provider,
        session_store=InMemorySessionStore(),
        progress_repo=repo,
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
    return client, repo


def _stub_order(monkeypatch, order_id: str = "order_stub_1") -> None:
    def _fake_create(**kwargs):
        assert kwargs["key_secret"] == KEY_SECRET  # secret stays server-side
        return billing.RazorpayOrder(
            order_id=order_id,
            amount_paise=kwargs["amount_paise"],
            currency="INR",
        )

    monkeypatch.setattr("constitution_memorizer.web.app.billing_create", _fake_create)


def test_order_endpoint_requires_keys(tmp_path: Path) -> None:
    client, _repo = _client(tmp_path, keys=False)
    assert client.post("/api/billing/order", json={"days": 30}).status_code == 404


def test_order_endpoint_requires_sign_in(tmp_path: Path) -> None:
    client, _repo = _client(tmp_path, signed_in=False)
    resp = client.post("/api/billing/order", json={"days": 30})
    assert resp.status_code == 401


def test_order_endpoint_derives_amount_server_side(tmp_path: Path, monkeypatch) -> None:
    client, repo = _client(tmp_path)
    _stub_order(monkeypatch)
    # A tampered client cannot name its own price — only a duration.
    resp = client.post(
        "/api/billing/order", json={"days": 30, "amount": 1}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["amount"] == 19900  # ₹199 from the catalog, not the client
    assert body["key_id"] == KEY_ID
    assert "key_secret" not in resp.text
    row = repo.get_billing_order(USER, body["order_id"])
    assert row is not None and row.status == "created" and row.plan_days == 30


def test_verify_rejects_bad_signature_and_grants_nothing(
    tmp_path: Path, monkeypatch
) -> None:
    client, repo = _client(tmp_path)
    _stub_order(monkeypatch)
    order_id = client.post("/api/billing/order", json={"days": 7}).json()["order_id"]
    resp = client.post(
        "/api/billing/verify",
        json={
            "razorpay_order_id": order_id,
            "razorpay_payment_id": "pay_1",
            "razorpay_signature": "forged",
        },
    )
    assert resp.status_code == 400
    assert repo.get_billing_order(USER, order_id).status == "created"
    # No payment grant appeared.
    dash = client.get("/dashboard")
    assert "Recall active" not in dash.text


def test_verify_missing_fields_400(tmp_path: Path, monkeypatch) -> None:
    client, _repo = _client(tmp_path)
    resp = client.post("/api/billing/verify", json={"razorpay_order_id": "x"})
    assert resp.status_code == 400
    assert resp.json()["error"] == "missing_fields"


def test_verified_payment_grants_subscribed_access(
    tmp_path: Path, monkeypatch
) -> None:
    client, repo = _client(tmp_path)
    _stub_order(monkeypatch, order_id="order_paid_1")
    order = client.post("/api/billing/order", json={"days": 180}).json()
    sig = _sign(order["order_id"], "pay_ok_1")
    resp = client.post(
        "/api/billing/verify",
        json={
            "razorpay_order_id": order["order_id"],
            "razorpay_payment_id": "pay_ok_1",
            "razorpay_signature": sig,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True and body["next"].startswith("/onboarding/plan")

    row = repo.get_billing_order(USER, order["order_id"])
    assert row.status == "paid" and row.razorpay_payment_id == "pay_ok_1"

    # The payment-source grant flips the account to full access.
    learn = client.get("/learn/clause-1")
    assert "🔒" not in learn.text
    profile = client.get("/profile")
    assert "Recall active · 180 days" in profile.text
    receipt = client.get("/subscribe/result?order=" + order["order_id"])
    assert receipt.status_code == 200
    assert "Recall is active." in receipt.text
    assert "₹699" in receipt.text  # what was actually charged
    # Standard Checkout sells one-time passes: the receipt must never claim
    # a renewal, even for plans the pricing page marks recurring.
    assert "None — one-time pass" in receipt.text
    assert "Renews" not in receipt.text


def test_verify_replay_does_not_double_grant(tmp_path: Path, monkeypatch) -> None:
    client, repo = _client(tmp_path)
    _stub_order(monkeypatch, order_id="order_replay_1")
    order = client.post("/api/billing/order", json={"days": 7}).json()
    payload = {
        "razorpay_order_id": order["order_id"],
        "razorpay_payment_id": "pay_r_1",
        "razorpay_signature": _sign(order["order_id"], "pay_r_1"),
    }
    assert client.post("/api/billing/verify", json=payload).status_code == 200
    # Replaying the same callback marks nothing again (idempotent repo write).
    assert client.post("/api/billing/verify", json=payload).status_code == 200
    conn = repo._conn  # test-only peek
    grants = conn.execute(
        "SELECT COUNT(*) AS n FROM access_grants WHERE source = 'payment'"
    ).fetchone()
    assert int(grants["n"]) == 1


def test_receipt_requires_own_paid_order(tmp_path: Path) -> None:
    client, _repo = _client(tmp_path)
    resp = client.get("/subscribe/result?order=order_unknown", follow_redirects=False)
    assert resp.status_code == 303  # back to pricing, no fake receipt
