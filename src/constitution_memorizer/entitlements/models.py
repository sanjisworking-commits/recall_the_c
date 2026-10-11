"""Frozen entitlement snapshot. Not a route gate and not a DB row.

Milestone 3 defines identity + Constitution + Playground *commercial* fields.
Milestone 4A adds device-authorization fields. Milestone 5 overlays current
roster period metadata. Law membership is ``is_law_active_this_period``, not
a lifetime unlocked-id list.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

CONSTITUTION_ACCESS_GUEST_EXPLORE = "guest_explore"
CONSTITUTION_ACCESS_FULL = "full"
CONSTITUTION_ACCESS: frozenset[str] = frozenset(
    {CONSTITUTION_ACCESS_GUEST_EXPLORE, CONSTITUTION_ACCESS_FULL}
)

LEGACY_STATUS_ACTIVE = "legacy_active"
LEGACY_STATUS_EXPIRED = "legacy_expired"
LEGACY_STATUSES: frozenset[str] = frozenset(
    {LEGACY_STATUS_ACTIVE, LEGACY_STATUS_EXPIRED}
)

BLOCK_SIGN_IN_REQUIRED = "sign_in_required"
BLOCK_NOT_SUBSCRIBED = "not_subscribed"
BLOCK_PAID_PERIOD_ENDED = "paid_period_ended"
BLOCK_PAYMENT_HALTED = "payment_halted"
BLOCK_SUBSCRIPTION_PAUSED = "subscription_paused"
BLOCK_DEVICE_LIMIT = "device_limit"
BLOCK_DEVICE_REVOKED = "device_revoked"
BLOCK_DEVICE_CONFIG_ERROR = "device_config_error"
BLOCK_DEVICE_REPLACEMENT_LIMIT = "device_replacement_limit"

PLAYGROUND_BLOCK_REASONS: frozenset[str] = frozenset(
    {
        BLOCK_SIGN_IN_REQUIRED,
        BLOCK_NOT_SUBSCRIBED,
        BLOCK_PAID_PERIOD_ENDED,
        BLOCK_PAYMENT_HALTED,
        BLOCK_SUBSCRIPTION_PAUSED,
        BLOCK_DEVICE_LIMIT,
        BLOCK_DEVICE_REVOKED,
        BLOCK_DEVICE_CONFIG_ERROR,
        BLOCK_DEVICE_REPLACEMENT_LIMIT,
    }
)


@dataclass(frozen=True)
class EntitlementSnapshot:
    """Immutable per-request commercial result. Routes must not re-derive it."""

    is_authenticated: bool
    subscription_status: str | None
    tier: str | None
    is_subscribed: bool
    admin_override: bool
    can_use_constitution_learn: bool
    constitution_access: str
    can_read_laws: bool
    can_open_playground: bool
    can_consume_new_playground_law: bool
    playground_law_limit: int | None
    playground_block_reason: str | None
    billing_period_start: datetime | None
    billing_period_end: datetime | None
    legacy_status: str | None
    device_limit: int | None = None
    registered_device_count: int = 0
    current_device_id: str | None = None
    current_device_registered: bool = False
    current_device_allowed: bool = False
    current_device_revoked: bool = False
    device_slots_remaining: int | None = None
    playground_period_start: date | None = None
    playground_period_end: date | None = None
    playground_laws_used: int | None = None
    playground_laws_remaining: int | None = None
    # Presentation-only. Authorization still uses can_open / can_consume.
    cancel_at_period_end: bool = False
    scheduled_tier: str | None = None
