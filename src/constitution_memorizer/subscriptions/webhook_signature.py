"""Razorpay webhook HMAC. Separate from Checkout payment_id|subscription_id."""

from __future__ import annotations

import hmac
import hashlib
from dataclasses import dataclass

from constitution_memorizer.subscriptions.errors import (
    SubscriptionConfigError,
    WebhookSignatureError,
)


@dataclass(frozen=True)
class WebhookSecrets:
    """Current + optional previous webhook secret. Never log the values."""

    current: str = ""
    previous: str = ""

    def __repr__(self) -> str:
        return "WebhookSecrets(current=***redacted***, previous=***redacted***)"

    def require_current(self) -> str:
        value = str(self.current or "").strip()
        if not value:
            raise SubscriptionConfigError("RAZORPAY_WEBHOOK_SECRET is not configured")
        return value


def verify_webhook_signature(
    raw_body: bytes,
    signature: str,
    secrets: WebhookSecrets,
) -> str:
    """HMAC-SHA256 over the exact raw request bytes. Returns current|previous."""
    current = secrets.require_current()
    sig = str(signature or "")
    if not sig:
        raise WebhookSignatureError("missing webhook signature")
    if _matches(raw_body, sig, current):
        return "current"
    previous = str(secrets.previous or "").strip()
    if previous and _matches(raw_body, sig, previous):
        return "previous"
    raise WebhookSignatureError("invalid webhook signature")


def _matches(raw_body: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(
        secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    try:
        return hmac.compare_digest(expected, signature)
    except (TypeError, ValueError):
        return False
