"""Request-scoped entitlement snapshot. Memoized on ``request.state``.

Commercial resolve stays payment-only. Device fields are a read-only overlay
here. Playground routes call ``ensure_current_device`` separately, then
invalidate this memo so the request sees the registered installation.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from typing import Any

from constitution_memorizer.entitlements.models import (
    BLOCK_DEVICE_CONFIG_ERROR,
    BLOCK_DEVICE_LIMIT,
    BLOCK_DEVICE_REPLACEMENT_LIMIT,
    BLOCK_DEVICE_REVOKED,
    BLOCK_PAID_PERIOD_ENDED,
    EntitlementSnapshot,
)
from constitution_memorizer.entitlements.service import EntitlementService

_UNSET = object()

_DEVICE_BLOCKS = frozenset(
    {
        BLOCK_DEVICE_LIMIT,
        BLOCK_DEVICE_REVOKED,
        BLOCK_DEVICE_CONFIG_ERROR,
        BLOCK_DEVICE_REPLACEMENT_LIMIT,
    }
)

_EXPIRED_EXCLUDED_STATUSES = frozenset({"pending", "halted", "paused"})


def get_entitlement_snapshot(
    request: object,
    *,
    now: datetime | None = None,
) -> EntitlementSnapshot:
    """Resolve once per request. Never calls a payment provider."""

    cached = getattr(getattr(request, "state", None), "entitlement_snapshot", _UNSET)
    if cached is not _UNSET:
        return cached  # type: ignore[return-value]
    service = getattr(getattr(request, "app", None), "state", None)
    resolver = getattr(service, "entitlement_service", None)
    if resolver is None:
        resolver = EntitlementService()
    snapshot = resolver.resolve_for_request(request, now=now)
    snapshot = overlay_device_on_snapshot(request, snapshot)
    state = getattr(request, "state", None)
    if state is not None:
        state.entitlement_snapshot = snapshot
    return snapshot


def snapshot_is_active_plus(snapshot: EntitlementSnapshot) -> bool:
    """True for an active Plus commercial snapshot. Not a visual mock."""

    return bool(
        snapshot.is_subscribed
        and snapshot.tier == "plus"
        and snapshot.can_open_playground
        and snapshot.subscription_status == "active"
    )


def request_is_active_plus(request: object, *, now: datetime | None = None) -> bool:
    """Resolve once via ``get_entitlement_snapshot``. Guests are never Plus."""

    if getattr(getattr(request, "state", None), "current_user", None) is None:
        return False
    return snapshot_is_active_plus(get_entitlement_snapshot(request, now=now))


def snapshot_is_expired_subscriber(snapshot: EntitlementSnapshot) -> bool:
    """Paid-period-ended subscriber. Not guest, Free, active Plus, pending, or halted."""

    return bool(
        snapshot.is_authenticated
        and snapshot.playground_block_reason == BLOCK_PAID_PERIOD_ENDED
        and snapshot.tier is not None
        and snapshot.billing_period_end is not None
        and snapshot.subscription_status not in _EXPIRED_EXCLUDED_STATUSES
        and not snapshot.is_subscribed
        and not snapshot.can_open_playground
        and not snapshot.can_consume_new_playground_law
    )


def request_is_expired_subscriber(request: object, *, now: datetime | None = None) -> bool:
    """Resolve once via ``get_entitlement_snapshot``. Guests are never expired."""

    if getattr(getattr(request, "state", None), "current_user", None) is None:
        return False
    return snapshot_is_expired_subscriber(get_entitlement_snapshot(request, now=now))


def snapshot_is_halted_subscriber(snapshot: EntitlementSnapshot) -> bool:
    """Halted subscriber. Status-based, not block-reason-based.

    Open-period Halted still cannot open Playground. An elapsed paid period
    yields ``paid_period_ended`` as the block reason, but ``subscription_status``
    remains ``halted``, so this stays the Halted cohort. Expired keeps excluding
    ``halted``. Not guest, Free, active Plus, pending, or paused.
    """

    return bool(
        snapshot.is_authenticated
        and snapshot.subscription_status == "halted"
        and snapshot.tier is not None
        and not snapshot.is_subscribed
        and not snapshot.can_open_playground
        and not snapshot.can_consume_new_playground_law
    )


def request_is_halted_subscriber(request: object, *, now: datetime | None = None) -> bool:
    """Resolve once via ``get_entitlement_snapshot``. Guests are never Halted."""

    if getattr(getattr(request, "state", None), "current_user", None) is None:
        return False
    return snapshot_is_halted_subscriber(get_entitlement_snapshot(request, now=now))


def invalidate_entitlement_snapshot(request: object) -> None:
    state = getattr(request, "state", None)
    if state is not None and hasattr(state, "entitlement_snapshot"):
        delattr(state, "entitlement_snapshot")


def overlay_device_on_snapshot(
    request: object,
    snapshot: EntitlementSnapshot,
) -> EntitlementSnapshot:
    """Read-only device overlay. Does not register a slot."""

    app_state = getattr(getattr(request, "app", None), "state", None)
    if not getattr(app_state, "multiuser_enabled", False):
        return snapshot
    devices = getattr(app_state, "device_service", None)
    if devices is None:
        return snapshot
    user = getattr(getattr(request, "state", None), "current_user", None)
    if user is None:
        return snapshot
    from constitution_memorizer.devices.token import request_device_token

    token = request_device_token(request)
    access = devices.inspect_current_device(
        user.id, token, admin_bypass=bool(snapshot.admin_override)
    )
    return apply_device_access(snapshot, access)


def apply_device_access(snapshot: EntitlementSnapshot, access: Any) -> EntitlementSnapshot:
    """Copy device fields onto a snapshot. Never clears ``is_subscribed``."""

    can_open = snapshot.can_open_playground
    consume = snapshot.can_consume_new_playground_law
    reason = snapshot.playground_block_reason
    if snapshot.admin_override:
        pass
    elif can_open and access.block_reason in _DEVICE_BLOCKS:
        can_open = False
        consume = False
        reason = access.block_reason
    return replace(
        snapshot,
        can_open_playground=can_open,
        can_consume_new_playground_law=consume,
        playground_block_reason=reason,
        device_limit=access.device_limit,
        registered_device_count=access.registered_device_count,
        current_device_id=access.current_device_id,
        current_device_registered=access.current_device_registered,
        current_device_allowed=access.current_device_allowed,
        current_device_revoked=access.current_device_revoked,
        device_slots_remaining=access.device_slots_remaining,
    )


def apply_roster_capacity(snapshot: EntitlementSnapshot, capacity: Any) -> EntitlementSnapshot:
    """Copy current-period roster metadata. Never lists lifetime law ids."""

    return replace(
        snapshot,
        playground_period_start=capacity.period_start,
        playground_period_end=capacity.period_end,
        playground_laws_used=capacity.used,
        playground_laws_remaining=capacity.remaining,
    )
