"""Central commercial entitlement package.

``web/entitlements.py`` is the Constitution Learn adapter around this snapshot.
Playground HTTP gates consume the snapshot (M3-B commercial + M4-A device overlay).
Roster remains M5.
"""

from constitution_memorizer.entitlements.dependencies import get_entitlement_snapshot
from constitution_memorizer.entitlements.models import (
    BLOCK_DEVICE_CONFIG_ERROR,
    BLOCK_DEVICE_LIMIT,
    BLOCK_DEVICE_REVOKED,
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
    "BLOCK_DEVICE_CONFIG_ERROR",
    "BLOCK_DEVICE_LIMIT",
    "BLOCK_DEVICE_REVOKED",
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
