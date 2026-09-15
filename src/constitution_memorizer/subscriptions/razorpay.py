"""Razorpay Subscriptions API adapter. Separate from legacy Orders in web/billing.py.

Razorpay requires every subscription to be bounded with ``total_count`` or
``end_at``. RecallC is a monthly cancel-anytime product, so create calls use
``RAZORPAY_MONTHLY_TOTAL_COUNT`` (1200 months) as a *provider-only* technical
horizon — not a 100-year commercial commitment and not an annual SKU. Users
cancel at the end of any paid monthly cycle.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from dataclasses import dataclass
from typing import Any, Mapping

import httpx

from constitution_memorizer.subscriptions.errors import (
    SubscriptionAuthError,
    SubscriptionConfigError,
    SubscriptionNetworkError,
    SubscriptionRejectedError,
    SubscriptionResponseError,
    SubscriptionValidationError,
)

logger = logging.getLogger(__name__)

RAZORPAY_SUBSCRIPTIONS_URL = "https://api.razorpay.com/v1/subscriptions"
# Provider API bound only. Not shown to customers. Not prepaid access.
RAZORPAY_MONTHLY_TOTAL_COUNT = 1200
SCHEDULE_NOW = "now"
SCHEDULE_CYCLE_END = "cycle_end"
_TIMEOUT_SECONDS = 20.0
_USER_SAFE_FAILURE = "Could not reach the payment provider"
_USER_SAFE_AUTH = "Payment provider authentication failed"
_USER_SAFE_REJECTED = "Payment provider rejected the subscription"
_USER_SAFE_MALFORMED = "Payment provider returned an unexpected response"


@dataclass(frozen=True)
class CreateSubscriptionRequest:
    """Normalized create payload. Exactly one of total_count or end_at."""

    plan_id: str
    total_count: int | None = None
    end_at: int | None = None
    quantity: int = 1
    customer_notify: bool = True
    notes: Mapping[str, str] | None = None


@dataclass(frozen=True)
class ProviderSubscription:
    """Normalized Razorpay subscription. Secrets are never stored here."""

    id: str
    plan_id: str
    status: str
    current_start: int | None
    current_end: int | None
    customer_id: str | None
    short_url: str | None
    has_scheduled_changes: bool | None
    raw: Mapping[str, Any]


class RazorpaySubscriptionsClient:
    """Server-to-server Subscriptions client. Basic auth with existing keys."""

    def __init__(
        self,
        key_id: str,
        key_secret: str,
        *,
        timeout: float = _TIMEOUT_SECONDS,
    ) -> None:
        self._key_id = str(key_id or "")
        self._key_secret = str(key_secret or "")
        self._timeout = timeout

    def __repr__(self) -> str:
        return (
            f"RazorpaySubscriptionsClient(key_id={self._key_id!r}, "
            "key_secret=***redacted***)"
        )

    def create_subscription(
        self, request: CreateSubscriptionRequest
    ) -> ProviderSubscription:
        payload = _create_payload(request)
        return self._send_json("POST", RAZORPAY_SUBSCRIPTIONS_URL, payload)

    def fetch_subscription(self, subscription_id: str) -> ProviderSubscription:
        sub_id = _require_subscription_id(subscription_id)
        return self._send_json(
            "GET", f"{RAZORPAY_SUBSCRIPTIONS_URL}/{sub_id}", None
        )

    def cancel_subscription(
        self, subscription_id: str, *, cancel_at_cycle_end: bool = True
    ) -> ProviderSubscription:
        sub_id = _require_subscription_id(subscription_id)
        return self._send_json(
            "POST",
            f"{RAZORPAY_SUBSCRIPTIONS_URL}/{sub_id}/cancel",
            {"cancel_at_cycle_end": bool(cancel_at_cycle_end)},
        )

    def update_subscription_plan(
        self,
        subscription_id: str,
        *,
        plan_id: str,
        schedule_change_at: str,
    ) -> ProviderSubscription:
        sub_id = _require_subscription_id(subscription_id)
        plan = str(plan_id or "").strip()
        if not plan:
            raise SubscriptionValidationError("plan_id is required")
        when = str(schedule_change_at or "").strip()
        if when not in {SCHEDULE_NOW, SCHEDULE_CYCLE_END}:
            raise SubscriptionValidationError(
                "schedule_change_at must be now or cycle_end"
            )
        return self._send_json(
            "PATCH",
            f"{RAZORPAY_SUBSCRIPTIONS_URL}/{sub_id}",
            {"plan_id": plan, "schedule_change_at": when},
        )

    def verify_checkout_signature(
        self,
        *,
        payment_id: str,
        subscription_id: str,
        signature: str,
    ) -> bool:
        """HMAC over the server-stored subscription id. Never logs the secret."""
        return verify_subscription_signature(
            payment_id=payment_id,
            subscription_id=subscription_id,
            signature=signature,
            key_secret=self._key_secret,
        )

    def _send_json(
        self, method: str, url: str, payload: Mapping[str, Any] | None
    ) -> ProviderSubscription:
        if not self._key_id.strip() or not self._key_secret.strip():
            raise SubscriptionConfigError(
                "RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET are required"
            )
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.request(
                    method,
                    url,
                    auth=(self._key_id, self._key_secret),
                    json=payload,
                )
        except httpx.HTTPError as exc:
            logger.exception("Razorpay subscription request failed")
            raise SubscriptionNetworkError(_USER_SAFE_FAILURE) from exc
        if response.status_code == 401:
            logger.error("Razorpay rejected the API credentials")
            raise SubscriptionAuthError(_USER_SAFE_AUTH)
        if response.status_code >= 400:
            logger.error(
                "Razorpay subscription %s failed: %s %s",
                method,
                response.status_code,
                _safe_body(response.text, secret=self._key_secret),
            )
            raise SubscriptionRejectedError(_USER_SAFE_REJECTED)
        try:
            data = response.json()
        except ValueError as exc:
            logger.error("Razorpay subscription response was not JSON")
            raise SubscriptionResponseError(_USER_SAFE_MALFORMED) from exc
        return normalize_provider_subscription(data)


def verify_subscription_signature(
    *,
    payment_id: str,
    subscription_id: str,
    signature: str,
    key_secret: str,
) -> bool:
    """Constant-time Checkout HMAC. Message is payment_id|subscription_id."""
    if not (payment_id and subscription_id and signature and key_secret):
        return False
    expected = hmac.new(
        key_secret.encode("utf-8"),
        f"{payment_id}|{subscription_id}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def _create_payload(request: CreateSubscriptionRequest) -> dict[str, Any]:
    plan_id = str(request.plan_id or "").strip()
    if not plan_id:
        raise SubscriptionValidationError("plan_id is required")
    has_count = request.total_count is not None
    has_end = request.end_at is not None
    if has_count == has_end:
        raise SubscriptionValidationError(
            "Provide exactly one of total_count or end_at"
        )
    if request.quantity < 1:
        raise SubscriptionValidationError("quantity must be >= 1")
    body: dict[str, Any] = {
        "plan_id": plan_id,
        "quantity": int(request.quantity),
        "customer_notify": 1 if request.customer_notify else 0,
    }
    if has_count:
        count = int(request.total_count)  # type: ignore[arg-type]
        if count < 1:
            raise SubscriptionValidationError("total_count must be >= 1")
        body["total_count"] = count
    else:
        body["end_at"] = int(request.end_at)  # type: ignore[arg-type]
    if request.notes:
        body["notes"] = dict(request.notes)
    return body


def normalize_provider_subscription(data: Mapping[str, Any]) -> ProviderSubscription:
    try:
        sub_id = str(data["id"])
        plan_id = str(data["plan_id"])
        status = str(data["status"])
    except (KeyError, TypeError) as exc:
        raise SubscriptionResponseError(_USER_SAFE_MALFORMED) from exc
    if not sub_id or not plan_id or not status:
        raise SubscriptionResponseError(_USER_SAFE_MALFORMED)
    return ProviderSubscription(
        id=sub_id,
        plan_id=plan_id,
        status=status,
        current_start=_optional_int(data.get("current_start")),
        current_end=_optional_int(data.get("current_end")),
        customer_id=_optional_str(data.get("customer_id")),
        short_url=_optional_str(data.get("short_url")),
        has_scheduled_changes=_optional_bool(data.get("has_scheduled_changes")),
        raw=dict(data),
    )


def _require_subscription_id(value: str) -> str:
    text = str(value or "").strip()
    if not text or "/" in text or " " in text:
        raise SubscriptionValidationError("invalid provider subscription id")
    return text


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _optional_str(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def _optional_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    return bool(value)


def _safe_body(text: str, *, secret: str = "") -> str:
    snippet = (text or "")[:500]
    if secret:
        snippet = snippet.replace(secret, "***")
    return snippet
