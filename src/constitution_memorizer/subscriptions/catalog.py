"""Canonical Playground subscription products. Server-authoritative.

Legacy duration SKUs live in ``web/pricing.py`` and must not be mapped here.
"""

from __future__ import annotations

from dataclasses import dataclass


class UnknownSubscriptionTier(LookupError):
    """Tier is not plus / pro / max. Never fall back to another product."""


SUBSCRIPTION_TIERS: frozenset[str] = frozenset({"plus", "pro", "max"})
TIER_RANK: dict[str, int] = {"plus": 1, "pro": 2, "max": 3}

# Tiers a client may buy. ``max`` stays a recognised, reconcilable tier for
# existing rows (B1-F10: legacy Max accounts and subscriptions resolve exactly
# as before) but is absent from every *new* purchase offer and checkout
# request under both tier models (B1-F09; plan §4.6, not flag-gated).
PURCHASABLE_TIERS: frozenset[str] = frozenset({"plus", "pro"})


class TierNotPurchasable(LookupError):
    """A recognised tier that is not offered for purchase under this model."""


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
    # Monthly-model cap (10 / 30 / None). Under ``choices`` every paid tier
    # is unlimited; read :func:`catalogue_law_limit` instead of this field.
    playground_law_limit: int | None
    # ``choices``-model capabilities. Inert under ``monthly``.
    personal_calendar_tasks: bool = True
    visual_explainers: bool = True


def _product(
    *,
    tier: str,
    display_name: str,
    price_inr: int,
    playground_law_limit: int | None,
    personal_calendar_tasks: bool = True,
    visual_explainers: bool = True,
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
        personal_calendar_tasks=personal_calendar_tasks,
        visual_explainers=visual_explainers,
    )


PRODUCTS: tuple[SubscriptionProduct, ...] = (
    _product(
        tier="plus",
        display_name="Plus",
        price_inr=199,
        playground_law_limit=10,
        personal_calendar_tasks=True,
        visual_explainers=False,
    ),
    _product(
        tier="pro",
        display_name="Pro",
        price_inr=399,
        playground_law_limit=30,
        personal_calendar_tasks=True,
        visual_explainers=True,
    ),
    # Legacy Max: recognised, not purchasable under ``choices``; access
    # unchanged from 3719b9f until decision 5-7 (no new benefit by assumption,
    # nothing removed either).
    _product(
        tier="max",
        display_name="Max",
        price_inr=1199,
        playground_law_limit=None,
        personal_calendar_tasks=True,
        visual_explainers=True,
    ),
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


def purchasable_tiers(tier_model: str | None = None) -> frozenset[str]:
    """Tiers offered for new purchase. The offer is the same under both tier
    models (``tier_model`` is accepted for call-site compatibility only):
    Max is recognised for existing subscriptions, never sold anew."""

    del tier_model
    return PURCHASABLE_TIERS


def list_purchasable_products(
    tier_model: str | None = None,
) -> tuple[SubscriptionProduct, ...]:
    allowed = purchasable_tiers(tier_model)
    return tuple(row for row in PRODUCTS if row.tier in allowed)


def require_purchasable_tier(tier: str, tier_model: str | None = None) -> str:
    """Unknown tiers raise :class:`UnknownSubscriptionTier`; known-but-closed
    tiers raise :class:`TierNotPurchasable`. Never falls back."""

    product = get_subscription_product(tier)
    if product.tier not in purchasable_tiers(tier_model):
        raise TierNotPurchasable(product.tier)
    return product.tier


def catalogue_law_limit(tier: str, tier_model: str | None = None) -> int | None:
    """Monthly cap under ``monthly``; ``None`` (unlimited) for every paid tier
    under ``choices`` (B1-F16 check 1)."""

    from constitution_memorizer.entitlements.tier_model import (  # noqa: PLC0415
        current_tier_model,
        is_choice_model,
    )

    product = get_subscription_product(tier)
    model = tier_model if tier_model is not None else current_tier_model()
    if is_choice_model(model):
        return None
    return product.playground_law_limit


def tier_rank(tier: str) -> int:
    """Explicit commercial rank. plus < pro < max; never inferred from strings."""
    get_subscription_product(tier)
    return TIER_RANK[tier]


def is_upgrade(current_tier: str, target_tier: str) -> bool:
    return tier_rank(target_tier) > tier_rank(current_tier)


def is_downgrade(current_tier: str, target_tier: str) -> bool:
    return tier_rank(target_tier) < tier_rank(current_tier)
