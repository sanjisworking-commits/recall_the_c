"""Central commercial entitlement package.

``web/entitlements.py`` is the Constitution Learn adapter around this snapshot.
Playground HTTP gates land in Milestone 3B; devices in M4; roster in M5.
"""

from constitution_memorizer.entitlements.dependencies import get_entitlement_snapshot
from constitution_memorizer.entitlements.models import (
    BLOCK_NOT_SUBSCRIBED,
    BLOCK_PAID_PERIOD_ENDED,
    BLOCK_PAYMENT_HALTED,
    BLOCK_SIGN_IN_REQUIRED,
    BLOCK_SUBSCRIPTION_PAUSED,
    CONSTITUTION_ACCESS_FULL,
    CONSTITUTION_ACCESS_GUEST_EXPLORE,
    LEGACY_STATUS_ACTIVE,
    LEGACY_STATUS_EXPIRED,
    EntitlementSnapshot,
)
from constitution_memorizer.entitlements.service import EntitlementService

__all__ = [
    "BLOCK_NOT_SUBSCRIBED",
    "BLOCK_PAID_PERIOD_ENDED",
    "BLOCK_PAYMENT_HALTED",
    "BLOCK_SIGN_IN_REQUIRED",
    "BLOCK_SUBSCRIPTION_PAUSED",
    "CONSTITUTION_ACCESS_FULL",
    "CONSTITUTION_ACCESS_GUEST_EXPLORE",
    "EntitlementService",
    "EntitlementSnapshot",
    "LEGACY_STATUS_ACTIVE",
    "LEGACY_STATUS_EXPIRED",
    "get_entitlement_snapshot",
]
