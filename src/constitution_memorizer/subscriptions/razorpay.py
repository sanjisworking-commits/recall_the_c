"""Razorpay Subscriptions API adapter. Separate from legacy Orders in web/billing.py.

Does not create Plans. Does not invent a subscription lifetime. Callers must
supply ``total_count`` or ``end_at``.
"""

from __future__ import annotations

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
        if not self._key_id.strip() or not self._key_secret.strip():
            raise SubscriptionConfigError(
                "RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET are required"
            )
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(
                    RAZORPAY_SUBSCRIPTIONS_URL,
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
                "Razorpay subscription creation failed: %s %s",
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
