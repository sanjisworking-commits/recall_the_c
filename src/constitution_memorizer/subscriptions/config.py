"""Razorpay Plan IDs are deployment config. Never hardcode live plan ids."""

from __future__ import annotations

from dataclasses import dataclass

from constitution_memorizer.subscriptions.catalog import (
    SUBSCRIPTION_TIERS,
    get_subscription_product,
)
from constitution_memorizer.subscriptions.errors import SubscriptionConfigError

PLAN_ID_ENV_KEYS: dict[str, str] = {
    "plus": "RAZORPAY_PLAN_ID_PLUS",
    "pro": "RAZORPAY_PLAN_ID_PRO",
    "max": "RAZORPAY_PLAN_ID_MAX",
}


@dataclass(frozen=True)
class SubscriptionPlanIds:
    """Externally created Razorpay Plan IDs, keyed by locked tier."""

    plus: str = ""
    pro: str = ""
    max: str = ""

    def for_tier(self, tier: str) -> str:
        get_subscription_product(tier)
        value = {
            "plus": self.plus,
            "pro": self.pro,
            "max": self.max,
        }[tier]
        plan_id = str(value or "").strip()
        if not plan_id:
            raise SubscriptionConfigError(
                f"{PLAN_ID_ENV_KEYS[tier]} is not configured"
            )
        return plan_id

    def as_mapping(self) -> dict[str, str]:
        return {"plus": self.plus, "pro": self.pro, "max": self.max}


def plan_ids_from_settings(settings: object) -> SubscriptionPlanIds:
    """Read Plan IDs from MultiUserSettings-like objects. Empty is allowed."""
    return SubscriptionPlanIds(
        plus=str(getattr(settings, "razorpay_plan_id_plus", "") or ""),
        pro=str(getattr(settings, "razorpay_plan_id_pro", "") or ""),
        max=str(getattr(settings, "razorpay_plan_id_max", "") or ""),
    )


def require_plan_id(settings: object, tier: str) -> str:
    """Fail when creating a provider subscription for a tier with no Plan ID."""
    if tier not in SUBSCRIPTION_TIERS:
        get_subscription_product(tier)
    return plan_ids_from_settings(settings).for_tier(tier)
