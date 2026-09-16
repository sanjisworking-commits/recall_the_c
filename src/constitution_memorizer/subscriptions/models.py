"""Normalized RecallC subscription state. Not a SQL row and not entitlement."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from constitution_memorizer.subscriptions.catalog import SUBSCRIPTION_TIERS
from constitution_memorizer.subscriptions.errors import InvalidSubscriptionValue

PROVIDER_RAZORPAY = "razorpay"
SUBSCRIPTION_PROVIDERS: frozenset[str] = frozenset({PROVIDER_RAZORPAY})

SUBSCRIPTION_STATUSES: frozenset[str] = frozenset(
    {
        "created",
        "authenticated",
        "active",
        "pending",
        "halted",
        "paused",
        "cancelled",
        "completed",
        "expired",
    }
)

WEBHOOK_PROCESSING_STATUSES: frozenset[str] = frozenset(
    {"processing", "processed", "ignored", "failed", "unmatched"}
)
ACK_WEBHOOK_STATUSES: frozenset[str] = frozenset(
    {"processed", "ignored", "unmatched", "processing"}
)


def require_tier(tier: str) -> str:
    value = str(tier or "")
    if value not in SUBSCRIPTION_TIERS:
        raise InvalidSubscriptionValue(f"invalid subscription tier: {value!r}")
    return value


def require_status(status: str) -> str:
    value = str(status or "")
    if value not in SUBSCRIPTION_STATUSES:
        raise InvalidSubscriptionValue(f"invalid subscription status: {value!r}")
    return value


def require_provider(provider: str) -> str:
    value = str(provider or "")
    if value not in SUBSCRIPTION_PROVIDERS:
        raise InvalidSubscriptionValue(f"invalid subscription provider: {value!r}")
    return value


def require_webhook_status(status: str) -> str:
    value = str(status or "")
    if value not in WEBHOOK_PROCESSING_STATUSES:
        raise InvalidSubscriptionValue(f"invalid webhook processing status: {value!r}")
    return value


@dataclass(frozen=True)
class UserSubscription:
    """One commercial subscription row. No device, roster, or Learn fields."""

    id: str
    user_id: str
    provider: str
    provider_customer_id: str | None
    provider_subscription_id: str | None
    provider_plan_id: str | None
    tier: str
    status: str
    billing_period_start: datetime | None
    billing_period_end: datetime | None
    cancel_at_period_end: bool
    is_current: bool
    provider_metadata: Mapping[str, Any]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class SubscriptionCharge:
    """One recurring provider payment. Not a card dump and not entitlement."""

    id: str
    provider: str
    provider_payment_id: str
    provider_invoice_id: str | None
    provider_subscription_id: str | None
    user_subscription_id: str | None
    billing_period_start: datetime | None
    billing_period_end: datetime | None
    amount_paise: int | None
    currency: str | None
    payment_status: str | None
    refund_status: str | None
    amount_refunded_paise: int
    last_refund_id: str | None
    dispute_id: str | None
    dispute_status: str | None
    access_effect: str
    access_effect_reason: str | None
    access_effect_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class WebhookEvent:
    """One provider webhook delivery. Not entitlement and not a payload dump."""

    id: str
    provider: str
    provider_event_id: str
    event_name: str
    provider_subscription_id: str | None
    event_created_at: datetime | None
    received_at: datetime
    payload_sha256: str
    processing_status: str
    attempt_count: int
    processed_at: datetime | None
    last_error_code: str | None
    created_at: datetime
    updated_at: datetime
