"""Canonical Playground subscription products. Server-authoritative.

Legacy duration SKUs live in ``web/pricing.py`` and must not be mapped here.
"""

from __future__ import annotations

from dataclasses import dataclass


class UnknownSubscriptionTier(LookupError):
    """Tier is not plus / pro / max. Never fall back to another product."""


SUBSCRIPTION_TIERS: frozenset[str] = frozenset({"plus", "pro", "max"})
TIER_RANK: dict[str, int] = {"plus": 1, "pro": 2, "max": 3}
BILLING_INTERVAL_MONTHLY = "monthly"
CURRENCY_INR = "INR"


@dataclass(frozen=True)
class SubscriptionProduct:
    """Immutable commercial row. Clients may submit only ``tier``."""

    tier: str
    display_name: str
    price_inr: int
    amount_paise: int
    currency: str
    billing_interval: str
    gst_inclusive: bool
    playground_law_limit: int | None


def _product(
    *,
    tier: str,
    display_name: str,
    price_inr: int,
    playground_law_limit: int | None,
) -> SubscriptionProduct:
    amount_paise = price_inr * 100
    return SubscriptionProduct(
        tier=tier,
        display_name=display_name,
        price_inr=price_inr,
        amount_paise=amount_paise,
        currency=CURRENCY_INR,
        billing_interval=BILLING_INTERVAL_MONTHLY,
        gst_inclusive=True,
        playground_law_limit=playground_law_limit,
    )


PRODUCTS: tuple[SubscriptionProduct, ...] = (
    _product(tier="plus", display_name="Plus", price_inr=199, playground_law_limit=10),
    _product(tier="pro", display_name="Pro", price_inr=399, playground_law_limit=30),
    _product(tier="max", display_name="Max", price_inr=1199, playground_law_limit=None),
)

ANNUAL_PRODUCTS: tuple[SubscriptionProduct, ...] = ()

_BY_TIER: dict[str, SubscriptionProduct] = {row.tier: row for row in PRODUCTS}


def get_subscription_product(tier: str) -> SubscriptionProduct:
    """Resolve a locked product. Unknown tiers fail; they do not fall back."""
    key = str(tier or "")
    try:
        return _BY_TIER[key]
    except KeyError:
        raise UnknownSubscriptionTier(key) from None


def list_subscription_products() -> tuple[SubscriptionProduct, ...]:
    return PRODUCTS


def tier_rank(tier: str) -> int:
    """Explicit commercial rank. plus < pro < max; never inferred from strings."""
    get_subscription_product(tier)
    return TIER_RANK[tier]


def is_upgrade(current_tier: str, target_tier: str) -> bool:
    return tier_rank(target_tier) > tier_rank(current_tier)


def is_downgrade(current_tier: str, target_tier: str) -> bool:
    return tier_rank(target_tier) < tier_rank(current_tier)
