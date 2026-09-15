"""Playground subscription lifecycle. Routes delegate here; no httpx in routes.

Does not authorize Playground access. Webhook HMAC lives in webhooks.py;
this module applies provider GET truth after a verified notification.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import UUID

from constitution_memorizer.subscriptions.catalog import (
    get_subscription_product,
    is_downgrade,
    is_upgrade,
)
from constitution_memorizer.subscriptions.config import SubscriptionPlanIds
from constitution_memorizer.subscriptions.errors import (
    ChangePlanRequiredError,
    CheckoutInProgressError,
    CheckoutMismatchError,
    CheckoutSignatureError,
    CurrentSubscriptionExistsError,
    ResubscribeUnavailableError,
    SameTierChangeError,
    SubscriptionConfigError,
    SubscriptionStateError,
)
from constitution_memorizer.subscriptions.models import (
    SUBSCRIPTION_STATUSES,
    UserSubscription,
    require_status,
    require_tier,
)
from constitution_memorizer.subscriptions.razorpay import (
    RAZORPAY_MONTHLY_TOTAL_COUNT,
    SCHEDULE_CYCLE_END,
    SCHEDULE_NOW,
    CreateSubscriptionRequest,
    ProviderSubscription,
    RazorpaySubscriptionsClient,
)

logger = logging.getLogger(__name__)

LIVE_STATUSES = frozenset(
    {"authenticated", "active", "pending", "halted", "paused"}
)
TERMINAL_STATUSES = frozenset({"cancelled", "completed", "expired"})
PLAN_CHANGE_STATUSES = frozenset({"active"})


@dataclass(frozen=True)
class CheckoutHandoff:
    """Safe browser Checkout values. Never includes the key secret."""

    key_id: str
    subscription_id: str
    display_name: str
    description: str
    complete_url: str = "/billing/subscriptions/checkout/complete"

    def as_browser_payload(self) -> dict[str, str]:
        return {
            "key_id": self.key_id,
            "subscription_id": self.subscription_id,
            "name": "Recall the C",
            "description": self.description,
            "display_name": self.display_name,
            "complete_url": self.complete_url,
        }


class SubscriptionService:
    def __init__(
        self,
        repo: Any,
        client: RazorpaySubscriptionsClient,
        plan_ids: SubscriptionPlanIds,
        *,
        public_key_id: str,
    ) -> None:
        self._repo = repo
        self._client = client
        self._plan_ids = plan_ids
        self._public_key_id = str(public_key_id or "")

    def start_subscription(
        self, user_id: UUID | str, target_tier: str
    ) -> CheckoutHandoff:
        tier = _normalize_tier(target_tier)
        product = get_subscription_product(tier)
        plan_id = self._plan_ids.for_tier(tier)
        self._require_public_key()
        current = self._repo.get_current_subscription(user_id)
        if current is not None:
            return self._start_with_existing(user_id, current, tier)
        try:
            reservation = self._repo.create_subscription_record(
                user_id,
                tier=tier,
                status="created",
                provider_plan_id=plan_id,
                is_current=True,
                provider_metadata={"reservation": True},
            )
        except CurrentSubscriptionExistsError:
            current = self._repo.get_current_subscription(user_id)
            if current is None:
                raise
            return self._start_with_existing(user_id, current, tier)
        return self._create_provider_for_reservation(user_id, reservation, product, plan_id)

    def complete_checkout(
        self,
        user_id: UUID | str,
        *,
        razorpay_payment_id: str,
        razorpay_subscription_id: str,
        razorpay_signature: str,
    ) -> UserSubscription:
        current = self._require_current(user_id)
        stored_id = str(current.provider_subscription_id or "")
        if not stored_id:
            raise SubscriptionStateError("no provider subscription to verify")
        returned_id = str(razorpay_subscription_id or "")
        if returned_id != stored_id:
            logger.warning("Checkout subscription id mismatch for user %s", user_id)
            raise CheckoutMismatchError("subscription id mismatch")
        if not self._client.verify_checkout_signature(
            payment_id=str(razorpay_payment_id or ""),
            subscription_id=stored_id,
            signature=str(razorpay_signature or ""),
        ):
            logger.warning("Checkout signature rejected for user %s", user_id)
            raise CheckoutSignatureError("invalid checkout signature")
        provider = self._client.fetch_subscription(stored_id)
        meta = _safe_metadata(current.provider_metadata)
        meta["verified_payment_id"] = str(razorpay_payment_id)
        return self._persist_provider(
            user_id,
            current,
            provider,
            extra_meta=meta,
        )

    def cancel_at_cycle_end(self, user_id: UUID | str) -> UserSubscription:
        current = self._require_provider_backed(user_id)
        if current.status != "active":
            raise SubscriptionStateError(
                "cycle-end cancellation is only valid for an active subscription"
            )
        provider = self._client.cancel_subscription(
            current.provider_subscription_id or "",
            cancel_at_cycle_end=True,
        )
        return self._persist_provider(
            user_id,
            current,
            provider,
            cancel_at_period_end=True,
        )

    def change_plan(self, user_id: UUID | str, target_tier: str) -> UserSubscription:
        current = self._require_provider_backed(user_id)
        target = _normalize_tier(target_tier)
        if target == current.tier:
            raise SameTierChangeError("already on this plan")
        if current.status not in PLAN_CHANGE_STATUSES:
            raise SubscriptionStateError(
                "plan changes are only available for an active subscription"
            )
        plan_id = self._plan_ids.for_tier(target)
        if is_upgrade(current.tier, target):
            provider = self._client.update_subscription_plan(
                current.provider_subscription_id or "",
                plan_id=plan_id,
                schedule_change_at=SCHEDULE_NOW,
            )
            return self._persist_provider(
                user_id,
                current,
                provider,
                tier=target,
                extra_meta=_cleared_schedule(current.provider_metadata),
            )
        if is_downgrade(current.tier, target):
            provider = self._client.update_subscription_plan(
                current.provider_subscription_id or "",
                plan_id=plan_id,
                schedule_change_at=SCHEDULE_CYCLE_END,
            )
            meta = _safe_metadata(current.provider_metadata)
            meta["scheduled_tier"] = target
            meta["scheduled_plan_id"] = plan_id
            meta["schedule_change_at"] = SCHEDULE_CYCLE_END
            # Paid tier stays the current commercial truth until the provider
            # applies the scheduled change (M2-C webhooks).
            return self._persist_provider(
                user_id,
                current,
                provider,
                extra_meta=meta,
                retain_paid_plan=True,
            )
        raise SameTierChangeError("already on this plan")

    def get_current(self, user_id: UUID | str) -> UserSubscription | None:
        return self._repo.get_current_subscription(user_id)

    def fetch_provider_subscription(self, provider_subscription_id: str):
        """Authenticated provider GET. Webhook payloads are not authorization truth."""
        return self._client.fetch_subscription(provider_subscription_id)

    def reconcile_fetched_subscription(
        self,
        row: UserSubscription,
        provider: ProviderSubscription,
        *,
        extra_meta: Mapping[str, Any] | None = None,
    ) -> UserSubscription:
        """Persist CURRENT provider GET state. Event names do not win."""
        mapped_tier = self._plan_ids.tier_for_plan_id(provider.plan_id)
        meta = _safe_metadata(row.provider_metadata)
        if extra_meta:
            meta.update(_safe_metadata(extra_meta))
        apply_tier = None
        if mapped_tier is not None and mapped_tier != row.tier:
            apply_tier = mapped_tier
            meta = _cleared_schedule(meta)
        return self._persist_provider(
            row.user_id,
            row,
            provider,
            extra_meta=meta,
            tier=apply_tier,
        )

    def checkout_handoff(self, row: UserSubscription) -> CheckoutHandoff:
        self._require_public_key()
        product = get_subscription_product(row.tier)
        sub_id = str(row.provider_subscription_id or "")
        if not sub_id:
            raise SubscriptionStateError("checkout is not ready")
        return CheckoutHandoff(
            key_id=self._public_key_id,
            subscription_id=sub_id,
            display_name=product.display_name,
            description=_customer_description(product.display_name),
        )

    def _start_with_existing(
        self,
        user_id: UUID | str,
        current: UserSubscription,
        tier: str,
    ) -> CheckoutHandoff:
        if current.status == "created" and not current.provider_subscription_id:
            raise CheckoutInProgressError(
                "subscription creation is already in progress"
            )
        if current.status == "created" and current.provider_subscription_id:
            if current.tier != tier:
                raise SubscriptionStateError(
                    "finish or abandon the current checkout before changing plans"
                )
            return self.checkout_handoff(current)
        if current.status in LIVE_STATUSES:
            if current.tier == tier:
                raise ChangePlanRequiredError("already subscribed")
            raise ChangePlanRequiredError("use the plan-change flow")
        if current.status in TERMINAL_STATUSES:
            raise ResubscribeUnavailableError(
                "resubscribe is not available in this batch"
            )
        raise SubscriptionStateError("cannot start a parallel subscription")

    def _create_provider_for_reservation(
        self,
        user_id: UUID | str,
        reservation: UserSubscription,
        product: Any,
        plan_id: str,
    ) -> CheckoutHandoff:
        request = CreateSubscriptionRequest(
            plan_id=plan_id,
            total_count=RAZORPAY_MONTHLY_TOTAL_COUNT,
            quantity=1,
            customer_notify=True,
            notes={"user_id": str(user_id), "tier": product.tier},
        )
        try:
            provider = self._client.create_subscription(request)
        except Exception:
            self._repo.mark_not_current(user_id, reservation.id)
            raise
        try:
            stored = self._persist_provider(
                user_id,
                reservation,
                provider,
                extra_meta={"reservation": False},
            )
        except Exception:
            logger.exception(
                "Persisted reservation after Razorpay create failed; "
                "provider_subscription_id=%s user_id=%s",
                provider.id,
                user_id,
            )
            raise
        return self.checkout_handoff(stored)

    def _persist_provider(
        self,
        user_id: UUID | str,
        row: UserSubscription,
        provider: ProviderSubscription,
        *,
        extra_meta: Mapping[str, Any] | None = None,
        tier: str | None = None,
        cancel_at_period_end: bool | None = None,
        retain_paid_plan: bool = False,
    ) -> UserSubscription:
        status = require_status(provider.status) if provider.status in SUBSCRIPTION_STATUSES else None
        if status is None:
            raise SubscriptionStateError(
                f"provider status {provider.status!r} is not stored"
            )
        meta = _safe_metadata(extra_meta if extra_meta is not None else row.provider_metadata)
        meta["provider"] = _safe_raw(provider.raw)
        if provider.has_scheduled_changes is not None:
            meta["has_scheduled_changes"] = provider.has_scheduled_changes
        kwargs: dict[str, Any] = {
            "status": status,
            "provider_subscription_id": provider.id,
            "provider_plan_id": (
                row.provider_plan_id if retain_paid_plan else provider.plan_id
            ),
            "provider_customer_id": provider.customer_id,
            "billing_period_start": _from_unix(provider.current_start),
            "billing_period_end": _from_unix(provider.current_end),
            "provider_metadata": meta,
        }
        if tier is not None and not retain_paid_plan:
            kwargs["tier"] = require_tier(tier)
        if cancel_at_period_end is not None:
            kwargs["cancel_at_period_end"] = cancel_at_period_end
        return self._repo.update_subscription_state(user_id, row.id, **kwargs)

    def _require_current(self, user_id: UUID | str) -> UserSubscription:
        current = self._repo.get_current_subscription(user_id)
        if current is None:
            raise SubscriptionStateError("no current subscription")
        return current

    def _require_provider_backed(self, user_id: UUID | str) -> UserSubscription:
        current = self._require_current(user_id)
        if not current.provider_subscription_id:
            raise SubscriptionStateError("no provider subscription")
        return current

    def _require_public_key(self) -> None:
        if not self._public_key_id.strip():
            raise SubscriptionConfigError("RAZORPAY_KEY_ID is not configured")


def _normalize_tier(tier: str) -> str:
    product = get_subscription_product(str(tier or ""))
    return require_tier(product.tier)


def _customer_description(display_name: str) -> str:
    return f"{display_name} · monthly · GST included"


def _from_unix(value: int | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromtimestamp(int(value), tz=timezone.utc)


def _safe_metadata(value: Mapping[str, Any] | None) -> dict[str, Any]:
    return {k: v for k, v in dict(value or {}).items() if _safe_meta_key(k)}


def _cleared_schedule(value: Mapping[str, Any] | None) -> dict[str, Any]:
    meta = _safe_metadata(value)
    meta.pop("scheduled_tier", None)
    meta.pop("scheduled_plan_id", None)
    meta.pop("schedule_change_at", None)
    return meta


def _safe_raw(raw: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in dict(raw).items() if _safe_meta_key(k)}


def _safe_meta_key(key: str) -> bool:
    lowered = str(key).lower()
    if "secret" in lowered:
        return False
    if lowered in {
        "key_secret",
        "authorization",
        "card",
        "cvv",
        "pan",
        "signature",
        "razorpay_signature",
        "x-razorpay-signature",
        "webhook_secret",
        "payment",
    }:
        return False
    return True
