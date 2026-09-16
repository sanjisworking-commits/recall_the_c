"""Playground subscription-state policy. Not EntitlementService and not a route gate."""

from __future__ import annotations

from dataclasses import dataclass

from constitution_memorizer.subscriptions.errors import InvalidSubscriptionValue
from constitution_memorizer.subscriptions.models import require_status

ACCESS_EFFECT_NONE = "none"
ACCESS_EFFECT_PERIOD_ENDED = "period_ended"
ACCESS_EFFECTS: frozenset[str] = frozenset(
    {ACCESS_EFFECT_NONE, ACCESS_EFFECT_PERIOD_ENDED}
)
ACCESS_EFFECT_REASON_FULL_REFUND = "full_refund"
ACCESS_EFFECT_REASON_DISPUTE_LOST = "dispute_lost"
ACCESS_EFFECT_REASONS: frozenset[str] = frozenset(
    {ACCESS_EFFECT_REASON_FULL_REFUND, ACCESS_EFFECT_REASON_DISPUTE_LOST}
)

_EXISTING_AND_NEW = frozenset({"active"})
_EXISTING_ONLY = frozenset({"pending"})


@dataclass(frozen=True)
class SubscriptionAccessDisposition:
    """Locked §21 Playground capability bits derived from provider status.

    Milestone 3 composes this with auth, device, roster, and admin override.
    """

    status: str
    can_use_existing_playground: bool
    can_consume_new_law: bool


def disposition_for_status(status: str) -> SubscriptionAccessDisposition:
    value = require_status(status)
    if value in _EXISTING_AND_NEW:
        return SubscriptionAccessDisposition(value, True, True)
    if value in _EXISTING_ONLY:
        return SubscriptionAccessDisposition(value, True, False)
    return SubscriptionAccessDisposition(value, False, False)


def require_access_effect(value: str) -> str:
    text = str(value or "")
    if text not in ACCESS_EFFECTS:
        raise InvalidSubscriptionValue(f"invalid access effect: {text!r}")
    return text


def require_access_effect_reason(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    text = str(value)
    if text not in ACCESS_EFFECT_REASONS:
        raise InvalidSubscriptionValue(f"invalid access effect reason: {text!r}")
    return text


def compute_charge_access_effect(
    refund_status: str | None,
    dispute_status: str | None,
) -> tuple[str, str | None]:
    """Deterministic paid-period effect. Event names do not participate."""
    refund = str(refund_status or "").strip().lower()
    dispute = str(dispute_status or "").strip().lower()
    if refund == "full":
        return ACCESS_EFFECT_PERIOD_ENDED, ACCESS_EFFECT_REASON_FULL_REFUND
    if dispute == "lost":
        return ACCESS_EFFECT_PERIOD_ENDED, ACCESS_EFFECT_REASON_DISPUTE_LOST
    return ACCESS_EFFECT_NONE, None
