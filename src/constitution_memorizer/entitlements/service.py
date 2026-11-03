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
    BLOCK_FREE_CHOICES_EXHAUSTED,
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
from constitution_memorizer.entitlements.tier_model import (
    FREE_CHOICE_LIMIT,
    TIER_MODEL_MONTHLY,
    is_choice_model,
    normalize_tier_model,
)
from constitution_memorizer.subscriptions.catalog import (
    catalogue_law_limit,
    get_subscription_product,
)
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
        choices: Any = None,
        tier_model: str = TIER_MODEL_MONTHLY,
    ) -> None:
        self._subscriptions = subscriptions
        self._charges = charges
        self._access_store = access_store
        self._legacy_store = legacy_store
        # Permanent-choice ledger reader (``count_choices``). Read only for a
        # Free account under ``choices``; never for paid, admin or guests.
        self._choices = choices
        self._tier_model = normalize_tier_model(tier_model)

    @property
    def tier_model(self) -> str:
        return self._tier_model

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
        if is_choice_model(self._tier_model):
            snapshot = self._apply_choice_model(
                snapshot, user_id=user_id, subscription=subscription
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
                cancel_at_period_end=snapshot.cancel_at_period_end,
                scheduled_tier=snapshot.scheduled_tier,
                tier_model=self._tier_model,
                playground_choice_limit=None,
                playground_choices_used=0,
                playground_consume_block_reason=None,
                can_add_personal_calendar_tasks=True,
                can_open_visual_explainers=True,
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

    def _apply_choice_model(
        self,
        snapshot: EntitlementSnapshot,
        *,
        user_id: UUID | str,
        subscription: Any,
    ) -> EntitlementSnapshot:
        """Overlay the ``choices`` model on a commercial snapshot (B1-F01/F02/F16).

        * Account with **no subscription row** → Free: opens the Playground,
          three permanent choices (ledger count), new law allowed while
          ``used < 3``; at 3 the consume block is ``free_choices_exhausted``.
        * Paid rows keep their dispositions; the law limit is ``None`` for
          every paid tier (no monthly cap). Calendar create/edit for Plus and
          above; Visualize for Pro and above (Max unchanged, 5-7).
        * Rows in an ended or interrupted state (paid-period-ended, halted,
          paused, pending, cancelled/expired/completed) keep **today's**
          dispositions exactly: decision 5-20 is unresolved, so no Free
          capability is granted to an account that holds a subscription row.
        """

        from dataclasses import replace  # noqa: PLC0415

        if subscription is None:
            used = self._count_choices(user_id)
            consume = used < FREE_CHOICE_LIMIT
            return replace(
                snapshot,
                can_open_playground=True,
                can_consume_new_playground_law=consume,
                playground_law_limit=None,
                playground_block_reason=None,
                tier_model=self._tier_model,
                playground_choice_limit=FREE_CHOICE_LIMIT,
                playground_choices_used=used,
                playground_consume_block_reason=(
                    None if consume else BLOCK_FREE_CHOICES_EXHAUSTED
                ),
                can_add_personal_calendar_tasks=False,
                can_open_visual_explainers=False,
            )
        tier = str(getattr(subscription, "tier", "") or "")
        product = get_subscription_product(tier)
        paid = bool(snapshot.is_subscribed)
        return replace(
            snapshot,
            playground_law_limit=catalogue_law_limit(tier, self._tier_model),
            tier_model=self._tier_model,
            playground_choice_limit=None,
            playground_choices_used=0,
            playground_consume_block_reason=None,
            can_add_personal_calendar_tasks=bool(paid and product.personal_calendar_tasks),
            can_open_visual_explainers=bool(paid and product.visual_explainers),
        )

    def _count_choices(self, user_id: UUID | str) -> int:
        repo = self._choices
        if repo is None:
            return 0
        getter = getattr(repo, "count_choices", None)
        if getter is None:
            return 0
        return int(getter(user_id) or 0)

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


def _scheduled_tier(subscription: Any) -> str | None:
    meta = getattr(subscription, "provider_metadata", None) or {}
    if not isinstance(meta, dict):
        return None
    value = str(meta.get("scheduled_tier") or "").strip()
    return value or None


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
    cancel_at_period_end = bool(getattr(subscription, "cancel_at_period_end", False))
    scheduled_tier = _scheduled_tier(subscription)
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
            cancel_at_period_end=cancel_at_period_end,
            scheduled_tier=scheduled_tier,
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
        cancel_at_period_end=cancel_at_period_end,
        scheduled_tier=scheduled_tier,
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
