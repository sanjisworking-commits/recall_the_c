"""Authoritative EntitlementService. Database/local state only — never Razorpay.

Consumes Milestone 2 facts:

* ``user_subscription`` + :func:`disposition_for_status`
* ``subscription_charge.access_effect`` for the *current* billing period
* :func:`classify_legacy_paid_access` (read-only; never writes ``user_subscription``)
* admin role (not promotion / admin_grant / payment grants)

Does not import or call a provider HTTP client.
Device overlay is applied after this commercial resolve (Milestone 4A).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

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
from constitution_memorizer.subscriptions.catalog import get_subscription_product
from constitution_memorizer.subscriptions.legacy import classify_legacy_paid_access
from constitution_memorizer.subscriptions.policy import (
    ACCESS_EFFECT_PERIOD_ENDED,
    disposition_for_status,
)

_GUEST = EntitlementSnapshot(
    is_authenticated=False,
    subscription_status=None,
    tier=None,
    is_subscribed=False,
    admin_override=False,
    can_use_constitution_learn=True,
    constitution_access=CONSTITUTION_ACCESS_GUEST_EXPLORE,
    can_read_laws=True,
    can_open_playground=False,
    can_consume_new_playground_law=False,
    playground_law_limit=None,
    playground_block_reason=BLOCK_SIGN_IN_REQUIRED,
    billing_period_start=None,
    billing_period_end=None,
    legacy_status=None,
)


def _utc(now: datetime | None) -> datetime:
    clock = now or datetime.now(timezone.utc)
    if clock.tzinfo is None:
        return clock.replace(tzinfo=timezone.utc)
    return clock


class EntitlementService:
    """Compose auth + M2 subscription/legacy/admin into one snapshot.

    Constructor takes existing repositories. It must not open a DB pool, must
    not construct a provider client, and must not be called from Razorpay I/O.
    """

    def __init__(
        self,
        *,
        subscriptions: Any = None,
        charges: Any = None,
        access_store: Any = None,
        legacy_store: Any = None,
    ) -> None:
        self._subscriptions = subscriptions
        self._charges = charges
        self._access_store = access_store
        self._legacy_store = legacy_store

    def resolve(
        self,
        user_id: UUID | str | None,
        *,
        now: datetime | None = None,
    ) -> EntitlementSnapshot:
        """Resolve commercial truth for ``user_id``. ``None`` is a guest.

        Guests perform zero subscription, charge, or legacy store reads.
        """
        if user_id is None:
            return _GUEST
        clock = _utc(now)
        admin_override = self._is_admin(user_id)
        subscription = self._current_subscription(user_id)
        legacy = None
        if self._legacy_store is not None:
            legacy = classify_legacy_paid_access(
                self._legacy_store, user_id, now=clock
            )
        snapshot = self._account_snapshot(
            subscription=subscription,
            legacy=legacy,
            now=clock,
        )
        if admin_override:
            snapshot = EntitlementSnapshot(
                is_authenticated=True,
                subscription_status=snapshot.subscription_status,
                tier=None,
                is_subscribed=False,
                admin_override=True,
                can_use_constitution_learn=True,
                constitution_access=CONSTITUTION_ACCESS_FULL,
                can_read_laws=True,
                can_open_playground=True,
                can_consume_new_playground_law=True,
                playground_law_limit=None,
                playground_block_reason=None,
                billing_period_start=snapshot.billing_period_start,
                billing_period_end=snapshot.billing_period_end,
                legacy_status=snapshot.legacy_status,
            )
        return snapshot

    def resolve_for_request(
        self,
        request: object,
        *,
        now: datetime | None = None,
    ) -> EntitlementSnapshot:
        user = getattr(getattr(request, "state", None), "current_user", None)
        user_id = getattr(user, "id", None) if user is not None else None
        return self.resolve(user_id, now=now)

    def _is_admin(self, user_id: UUID | str) -> bool:
        store = self._access_store
        if store is None:
            return False
        getter = getattr(store, "is_admin", None)
        if getter is None:
            return False
        return bool(getter(user_id))

    def _current_subscription(self, user_id: UUID | str) -> Any:
        repo = self._subscriptions
        if repo is None:
            return None
        getter = getattr(repo, "get_current_subscription", None)
        if getter is None:
            return None
        return getter(user_id)

    def _account_snapshot(
        self,
        *,
        subscription: Any,
        legacy: Any,
        now: datetime,
    ) -> EntitlementSnapshot:
        legacy_status = _legacy_status(legacy)
        if subscription is None:
            return _unsubscribed_account(
                legacy=legacy,
                legacy_status=legacy_status,
            )
        return _from_subscription(
            subscription,
            charge_effect=self._current_period_effect(subscription),
            legacy_status=legacy_status,
            now=now,
        )

    def _current_period_effect(self, subscription: Any) -> str | None:
        repo = self._charges
        start = getattr(subscription, "billing_period_start", None)
        end = getattr(subscription, "billing_period_end", None)
        if repo is None or start is None or end is None:
            return None
        getter = getattr(repo, "get_charge_access_effect_for_billing_period", None)
        if getter is None:
            return None
        return getter(subscription.id, start, end)


def _legacy_status(legacy: Any) -> str | None:
    if legacy is None:
        return None
    return LEGACY_STATUS_ACTIVE if legacy.is_active else LEGACY_STATUS_EXPIRED


def _unsubscribed_account(*, legacy: Any, legacy_status: str | None) -> EntitlementSnapshot:
    status = None
    if legacy is not None and legacy.is_active:
        status = LEGACY_STATUS_ACTIVE
    return EntitlementSnapshot(
        is_authenticated=True,
        subscription_status=status,
        tier=None,
        is_subscribed=False,
        admin_override=False,
        can_use_constitution_learn=True,
        constitution_access=CONSTITUTION_ACCESS_FULL,
        can_read_laws=True,
        can_open_playground=False,
        can_consume_new_playground_law=False,
        playground_law_limit=None,
        playground_block_reason=BLOCK_NOT_SUBSCRIBED,
        billing_period_start=None,
        billing_period_end=None,
        legacy_status=legacy_status,
    )


def _from_subscription(
    subscription: Any,
    *,
    charge_effect: str | None,
    legacy_status: str | None,
    now: datetime,
) -> EntitlementSnapshot:
    status = str(subscription.status)
    tier = str(subscription.tier)
    start = subscription.billing_period_start
    end = subscription.billing_period_end
    law_limit = _catalogue_limit(tier)
    period_over = _paid_period_over(end, now)
    if period_over or charge_effect == ACCESS_EFFECT_PERIOD_ENDED:
        return EntitlementSnapshot(
            is_authenticated=True,
            subscription_status=status,
            tier=tier,
            is_subscribed=False,
            admin_override=False,
            can_use_constitution_learn=True,
            constitution_access=CONSTITUTION_ACCESS_FULL,
            can_read_laws=True,
            can_open_playground=False,
            can_consume_new_playground_law=False,
            playground_law_limit=law_limit,
            playground_block_reason=BLOCK_PAID_PERIOD_ENDED,
            billing_period_start=start,
            billing_period_end=end,
            legacy_status=legacy_status,
        )
    disposition = disposition_for_status(status)
    block = _block_reason(status, disposition.can_use_existing_playground)
    return EntitlementSnapshot(
        is_authenticated=True,
        subscription_status=status,
        tier=tier,
        is_subscribed=disposition.can_use_existing_playground,
        admin_override=False,
        can_use_constitution_learn=True,
        constitution_access=CONSTITUTION_ACCESS_FULL,
        can_read_laws=True,
        can_open_playground=disposition.can_use_existing_playground,
        can_consume_new_playground_law=disposition.can_consume_new_law,
        playground_law_limit=law_limit,
        playground_block_reason=block,
        billing_period_start=start,
        billing_period_end=end,
        legacy_status=legacy_status,
    )


def _catalogue_limit(tier: str) -> int | None:
    product = get_subscription_product(tier)
    return product.playground_law_limit


def _paid_period_over(end: datetime | None, now: datetime) -> bool:
    if end is None:
        return False
    stamp = end if end.tzinfo else end.replace(tzinfo=timezone.utc)
    return stamp <= now


def _block_reason(status: str, can_open: bool) -> str | None:
    if can_open:
        return None
    if status == "halted":
        return BLOCK_PAYMENT_HALTED
    if status == "paused":
        return BLOCK_SUBSCRIPTION_PAUSED
    return BLOCK_NOT_SUBSCRIBED
