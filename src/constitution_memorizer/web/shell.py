"""Shared-shell view helpers (M1-R).

The account slot's status label is one function of the entitlement snapshot,
rendered on every shared-shell page, instead of a per-route flag chain
(M1R-F01, DV-20). Templates branch on snapshot fields, never on the tier
flag directly (plan §4.5 item 2).
"""

from __future__ import annotations

from typing import Any

from constitution_memorizer.entitlements.dependencies import (
    get_entitlement_snapshot,
    snapshot_is_expired_subscriber,
    snapshot_is_halted_subscriber,
)
from constitution_memorizer.entitlements.models import BLOCK_PAYMENT_HALTED

TIER_LABELS: dict[str, str] = {"plus": "RecallC Plus", "pro": "RecallC Pro", "max": "RecallC Max"}
FREE_LABEL = "RecallC Free"


def account_status_for_snapshot(snapshot: Any) -> str:
    """Label for the header account slot.

    Halted and expired subscribers keep today's status titles (transitions
    are M8-R / 5-20); an active subscriber shows the tier; everyone else who
    is signed in is ``RecallC Free`` (a legacy Max holder is ``RecallC Max``).
    """

    from constitution_memorizer.playground.view import gate_view  # noqa: PLC0415

    if snapshot_is_halted_subscriber(snapshot):
        # Elapsed Halted keeps paid_period_ended as the block reason, but the
        # header stays Halted-family (same rule as the retired flag chain).
        return gate_view(reason=BLOCK_PAYMENT_HALTED).title
    if snapshot_is_expired_subscriber(snapshot):
        return gate_view(reason=str(snapshot.playground_block_reason or "")).title
    tier = getattr(snapshot, "tier", None)
    if getattr(snapshot, "is_subscribed", False) and tier:
        return TIER_LABELS.get(str(tier), f"RecallC {str(tier).capitalize()}")
    return FREE_LABEL


def shell_playground_month_model(request: Any) -> bool:
    """Template global ``playground_month_model``: True while the Playground
    follows the monthly period model for this request.

    A signed-in account: read from its entitlement snapshot (cached on
    ``request.state``). A guest has no account snapshot — the shared guest
    snapshot carries no model — so the entitlement service's own model is
    used, which is what the guest would get on signing in. Templates never
    read the flag. Used for copy guests and gated accounts read ("How
    Playground works")."""

    from constitution_memorizer.entitlements.tier_model import is_choice_model  # noqa: PLC0415
    from constitution_memorizer.playground.view import playground_month_model  # noqa: PLC0415

    if getattr(getattr(request, "state", None), "current_user", None) is None:
        service = getattr(getattr(getattr(request, "app", None), "state", None), "entitlement_service", None)
        return not is_choice_model(getattr(service, "tier_model", None))
    return playground_month_model(get_entitlement_snapshot(request))


def shell_account_status(request: Any) -> str:
    """Template global: resolves the snapshot once per request (cached on
    ``request.state``); guests get an empty string (the slot is a Sign in
    button for them)."""

    user = getattr(getattr(request, "state", None), "current_user", None)
    if user is None:
        return ""
    return account_status_for_snapshot(get_entitlement_snapshot(request))
