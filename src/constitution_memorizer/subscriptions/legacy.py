"""Read-only legacy N-day paid access. Not a Plus/Pro/Max subscription."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from constitution_memorizer.progress.user_ids import as_user_id
from constitution_memorizer.subscriptions.repository import _parse_dt

LEGACY_CLASSIFICATION = "legacy"
_ORDER_REASON_PREFIX = "razorpay:"


@dataclass(frozen=True)
class LegacyPaidAccess:
    """Duration-pass buyer. tier is always None — never plus/pro/max."""

    classification: str
    tier: None
    is_active: bool
    starts_at: datetime
    ends_at: datetime | None
    plan_days: int | None
    order_id: str | None
    payment_id: str | None
    grant_id: str
    grant_reason: str | None


def classify_legacy_paid_access(
    store: Any,
    user_id: UUID | str,
    *,
    now: datetime | None = None,
) -> LegacyPaidAccess | None:
    """Classify from payment-source access_grants. Does not write user_subscription.

    Grant ``reason`` ``razorpay:{order_id}`` is the only order linkage used.
    Amount, email, and nearest-timestamp guesses are not consulted.
    """
    lister = getattr(store, "list_payment_access_grants", None)
    if lister is None:
        return None
    rows = list(lister(user_id))
    if not rows:
        return None
    clock = now or datetime.now(timezone.utc)
    ranked = sorted(rows, key=lambda row: _grant_sort_key(row, clock), reverse=True)
    chosen = ranked[0]
    starts = _parse_dt(chosen.get("starts_at") if isinstance(chosen, dict) else chosen["starts_at"])
    ends = _parse_dt(chosen.get("ends_at") if isinstance(chosen, dict) else chosen["ends_at"])
    revoked = chosen.get("revoked_at") if isinstance(chosen, dict) else chosen["revoked_at"]
    if starts is None:
        return None
    reason = chosen.get("reason") if isinstance(chosen, dict) else chosen["reason"]
    grant_id = str(chosen.get("id") if isinstance(chosen, dict) else chosen["id"])
    order_id = _order_id_from_reason(reason)
    plan_days = None
    payment_id = None
    if order_id and hasattr(store, "get_billing_order"):
        order = store.get_billing_order(as_user_id(user_id), order_id)
        if order is not None:
            plan_days = int(order.plan_days)
            payment_id = order.razorpay_payment_id
    active = (
        revoked is None
        and starts <= clock
        and (ends is None or ends > clock)
    )
    return LegacyPaidAccess(
        classification=LEGACY_CLASSIFICATION,
        tier=None,
        is_active=active,
        starts_at=starts,
        ends_at=ends,
        plan_days=plan_days,
        order_id=order_id,
        payment_id=payment_id,
        grant_id=grant_id,
        grant_reason=str(reason) if reason else None,
    )


def _order_id_from_reason(reason: Any) -> str | None:
    text = str(reason or "")
    if not text.startswith(_ORDER_REASON_PREFIX):
        return None
    order_id = text[len(_ORDER_REASON_PREFIX) :].strip()
    return order_id or None


def _grant_sort_key(row: Any, clock: datetime) -> tuple[int, datetime]:
    mapping = row if isinstance(row, dict) else dict(row)
    starts = _parse_dt(mapping.get("starts_at")) or datetime.min.replace(tzinfo=timezone.utc)
    ends = _parse_dt(mapping.get("ends_at"))
    revoked = mapping.get("revoked_at")
    active = (
        revoked is None
        and starts <= clock
        and (ends is None or ends > clock)
    )
    return (1 if active else 0, ends or starts)
