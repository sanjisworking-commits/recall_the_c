"""Read-only Playground commercial diagnostics for admin/support.

Uses subscription, device, roster, and webhook repositories plus catalogue
metadata. Never hydrates a Bare Act. Never prints secrets, raw device tokens,
HMAC values, or payment instruments. Peeking a roster period does not create
one.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from uuid import UUID

from constitution_memorizer.devices.models import (
    DEVICE_REPLACEMENT_LIMIT,
    DEVICE_REPLACEMENT_WINDOW_DAYS,
    device_summary,
)
from constitution_memorizer.subscriptions.policy import disposition_for_status


def _remaining_capacity(law_limit: int | None, used: int) -> int | None:
    """Finite remaining slots, or None when unlimited. Roster-local copy.

    Imported inline copies of roster.models.remaining_capacity would load
    ``playground.roster`` (which imports the web app) and cycle through
    admin.routes. Keep this helper free of that package.
    """

    if law_limit is None:
        return None
    return max(0, int(law_limit) - int(used))

_SENSITIVE_KEY_FRAGMENTS = (
    "secret",
    "token",
    "password",
    "otp",
    "hmac",
    "jwt",
    "authorization",
    "card",
    "cvv",
)


def mask_provider_id(value: str | None) -> str:
    """Safe identifier for support UI. Never the full provider id."""

    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= 8:
        return text[:2] + "…"
    return f"{text[:4]}…{text[-4:]}"


def log_commercial_startup_status(settings: Any, logger: Any | None = None) -> dict[str, str]:
    """Presence-only commercial config at process start.

    Never prints secret values. Never fetches a payment provider. Never
    hydrates Bare Acts. Staging/production warn when Playground is on and
    required keys are missing; the process still starts so Constitution
    and public laws stay available.
    """

    status = commercial_config_status(settings)
    log = logger or logging.getLogger("recall.startup")
    log.info("playground commercial config (presence only): %s", status)
    missing = [name for name, value in status.items() if value == "missing"]
    playground_on = bool(getattr(settings, "playground_enabled", True))
    env = str(getattr(settings, "app_env", "") or "").strip().lower()
    if playground_on and env in {"staging", "production"} and missing:
        log.warning(
            "Playground commercial keys missing in %s: %s",
            env,
            ", ".join(missing),
        )
    return status


def commercial_config_status(settings: Any) -> dict[str, str]:
    """configured/missing (or true/false). Never the secret values."""

    def _flag(name: str, present: object) -> tuple[str, str]:
        return name, "configured" if str(present or "").strip() else "missing"

    playground_on = bool(getattr(settings, "playground_enabled", True))
    return dict(
        (
            _flag("RAZORPAY_KEY_ID", getattr(settings, "razorpay_key_id", "")),
            _flag("RAZORPAY_KEY_SECRET", getattr(settings, "razorpay_key_secret", "")),
            _flag("RAZORPAY_WEBHOOK_SECRET", getattr(settings, "razorpay_webhook_secret", "")),
            _flag(
                "RAZORPAY_WEBHOOK_SECRET_PREVIOUS",
                getattr(settings, "razorpay_webhook_secret_previous", ""),
            ),
            _flag("RAZORPAY_PLAN_ID_PLUS", getattr(settings, "razorpay_plan_id_plus", "")),
            _flag("RAZORPAY_PLAN_ID_PRO", getattr(settings, "razorpay_plan_id_pro", "")),
            _flag("RAZORPAY_PLAN_ID_MAX", getattr(settings, "razorpay_plan_id_max", "")),
            _flag("SUPPORT_EMAIL", getattr(settings, "support_email", "")),
            (
                "PLAYGROUND_ENABLED",
                "true" if playground_on else "false",
            ),
            (
                "PRICING_ENABLED",
                "true" if bool(getattr(settings, "pricing_enabled", False)) else "false",
            ),
        )
    )


def redact_log_text(text: str) -> str:
    """Drop known secret values if a logger accidentally interpolates them."""

    lowered = text.lower()
    if any(fragment in lowered for fragment in _SENSITIVE_KEY_FRAGMENTS):
        return "[redacted]"
    return text


@dataclass(frozen=True)
class SubscriptionDiagnostic:
    present: bool
    disposition: str
    tier: str | None
    status: str | None
    provider_status: str | None
    current_period_start: str
    current_period_end: str
    cancel_at_period_end: bool
    pending_or_halted: bool
    provider_subscription_id_masked: str
    roster_permission: str
    admin_override: bool
    is_subscribed: bool
    can_open_playground: bool
    can_consume_new_law: bool
    legacy_status: str | None
    note: str


@dataclass(frozen=True)
class DeviceDiagnosticRow:
    id: str
    platform: str
    platform_label: str
    display_name: str
    status_label: str
    first_registered_at: str
    last_seen_at: str
    is_active: bool


@dataclass(frozen=True)
class DeviceDiagnostic:
    registered_count: int
    active_count: int
    revoked_count: int
    replacement_count_30d: int
    replacement_limit: int
    replacement_window_days: int
    at_replacement_limit: bool
    rows: tuple[DeviceDiagnosticRow, ...]


@dataclass(frozen=True)
class RosterItemDiagnostic:
    law_id: str
    origin: str
    consumed_at: str
    removed_at: str
    declined_at: str
    active: bool


@dataclass(frozen=True)
class RosterDiagnostic:
    period_start: str
    period_end: str
    tier_snapshot: str
    status: str
    law_limit: str
    used: int
    remaining: str
    rows: tuple[RosterItemDiagnostic, ...]
    historical_starts: tuple[str, ...]
    viewing_historical: bool
    exists: bool


@dataclass(frozen=True)
class WebhookEventDiagnostic:
    event_id: str
    provider_event_id: str
    event_name: str
    received_at: str
    processed_at: str
    status: str
    duplicate_or_idempotent: str
    error_code: str


@dataclass(frozen=True)
class OverlaySelectionDiagnostic:
    law_id: str
    selected_count: int
    unit_count: int


@dataclass(frozen=True)
class PlaygroundAccountDiagnostic:
    subscription: SubscriptionDiagnostic
    devices: DeviceDiagnostic
    roster: RosterDiagnostic
    webhooks: tuple[WebhookEventDiagnostic, ...]
    overlay: tuple[OverlaySelectionDiagnostic, ...] = ()


def collect_playground_diagnostics(
    request: Any,
    user_id: UUID | str,
    *,
    period_start: date | None = None,
) -> PlaygroundAccountDiagnostic:
    """Assemble support facts. Zero Act hydration."""

    snapshot = _snapshot(request, user_id)
    subscription = _subscription_diag(request, user_id, snapshot)
    devices = _device_diag(request, user_id)
    roster = _roster_diag(request, user_id, period_start=period_start)
    webhooks = _webhook_diag(request, user_id)
    overlay = _overlay_diag(request, user_id)
    return PlaygroundAccountDiagnostic(
        subscription=subscription,
        devices=devices,
        roster=roster,
        webhooks=webhooks,
        overlay=overlay,
    )


def _overlay_diag(request: Any, user_id: UUID | str) -> tuple[OverlaySelectionDiagnostic, ...]:
    repo = getattr(request.app.state, "playground", None)
    if repo is None or not hasattr(repo, "list_playground_summaries"):
        return ()
    rows = repo.list_playground_summaries(user_id, as_of=date.today())
    return tuple(
        OverlaySelectionDiagnostic(
            law_id=row.law_id,
            selected_count=int(row.selected_count or 0),
            unit_count=int(getattr(row, "unit_count", row.selected_count) or 0),
        )
        for row in rows
    )


def _snapshot(request: Any, user_id: UUID | str) -> Any:
    service = getattr(request.app.state, "entitlement_service", None)
    if service is None:
        return None
    return service.resolve(user_id)


def _iso(value: datetime | date | None) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return value.isoformat()


def _subscription_diag(
    request: Any, user_id: UUID | str, snapshot: Any
) -> SubscriptionDiagnostic:
    service = getattr(request.app.state, "subscription_service", None)
    row = None
    if service is not None:
        row = service.get_current(user_id)
    admin_override = bool(getattr(snapshot, "admin_override", False)) if snapshot else False
    is_subscribed = bool(getattr(snapshot, "is_subscribed", False)) if snapshot else False
    can_open = bool(getattr(snapshot, "can_open_playground", False)) if snapshot else False
    can_new = (
        bool(getattr(snapshot, "can_consume_new_playground_law", False))
        if snapshot
        else False
    )
    if admin_override:
        roster_permission = "admin override (not a Max subscription row)"
        note = (
            "Administrator bypasses commercial subscription, device cap, and "
            "finite roster capacity. This is not a fake Max purchase."
        )
        disposition = "admin_override"
    elif row is None:
        roster_permission = "none — not a Playground subscriber"
        note = (
            "No current user_subscription. Signed-in Constitution Learn is "
            "full. Legacy duration purchases and access_grants do not grant "
            "Plus/Pro/Max."
        )
        disposition = "none"
    else:
        disp = disposition_for_status(row.status)
        if disp.can_use_existing_playground and disp.can_consume_new_law:
            roster_permission = "existing laws + new-law consume"
        elif disp.can_use_existing_playground:
            roster_permission = "existing current-roster laws only"
        else:
            roster_permission = "blocked"
        disposition = row.status
        note = "Commercial truth is user_subscription (and admin override)."
    pending_or_halted = bool(row is not None and row.status in {"pending", "halted"})
    return SubscriptionDiagnostic(
        present=row is not None,
        disposition=disposition,
        tier=None if admin_override else (row.tier if row is not None else None),
        status=row.status if row is not None else None,
        provider_status=row.status if row is not None else None,
        current_period_start=_iso(row.billing_period_start if row is not None else None),
        current_period_end=_iso(row.billing_period_end if row is not None else None),
        cancel_at_period_end=bool(row.cancel_at_period_end) if row is not None else False,
        pending_or_halted=pending_or_halted,
        provider_subscription_id_masked=mask_provider_id(
            row.provider_subscription_id if row is not None else None
        ),
        roster_permission=roster_permission,
        admin_override=admin_override,
        is_subscribed=is_subscribed,
        can_open_playground=can_open,
        can_consume_new_law=can_new,
        legacy_status=getattr(snapshot, "legacy_status", None) if snapshot else None,
        note=note,
    )


def _device_diag(request: Any, user_id: UUID | str) -> DeviceDiagnostic:
    service = getattr(request.app.state, "device_service", None)
    if service is None:
        return DeviceDiagnostic(
            registered_count=0,
            active_count=0,
            revoked_count=0,
            replacement_count_30d=0,
            replacement_limit=DEVICE_REPLACEMENT_LIMIT,
            replacement_window_days=DEVICE_REPLACEMENT_WINDOW_DAYS,
            at_replacement_limit=False,
            rows=(),
        )
    devices = list(service.list_devices(user_id))
    summaries = [device_summary(row, current_id=None) for row in devices]
    active = sum(1 for item in summaries if item.is_active)
    revoked = len(summaries) - active
    replacements = int(service.count_recent_replacements(user_id))
    rows = tuple(
        DeviceDiagnosticRow(
            id=item.id,
            platform=item.platform,
            platform_label=item.platform_label,
            display_name=item.display_name or "—",
            status_label=item.status_label,
            first_registered_at=_iso(item.first_registered_at),
            last_seen_at=_iso(item.last_seen_at),
            is_active=item.is_active,
        )
        for item in summaries
    )
    return DeviceDiagnostic(
        registered_count=len(summaries),
        active_count=active,
        revoked_count=revoked,
        replacement_count_30d=replacements,
        replacement_limit=DEVICE_REPLACEMENT_LIMIT,
        replacement_window_days=DEVICE_REPLACEMENT_WINDOW_DAYS,
        at_replacement_limit=replacements >= DEVICE_REPLACEMENT_LIMIT,
        rows=rows,
    )


def _roster_diag(
    request: Any,
    user_id: UUID | str,
    *,
    period_start: date | None,
) -> RosterDiagnostic:
    roster = getattr(request.app.state, "roster", None)
    if roster is None:
        return RosterDiagnostic(
            period_start="",
            period_end="",
            tier_snapshot="",
            status="",
            law_limit="",
            used=0,
            remaining="",
            rows=(),
            historical_starts=(),
            viewing_historical=False,
            exists=False,
        )
    periods = roster.list_periods(user_id)
    historical_starts = tuple(item.period_start.isoformat() for item in periods)
    current = roster.peek_period(user_id)
    period = roster.peek_period(user_id, period_start)
    viewing_historical = False
    if period_start is not None:
        if current is None or period is None:
            viewing_historical = True
        else:
            viewing_historical = period.period_start != current.period_start
    if period is None:
        return RosterDiagnostic(
            period_start=period_start.isoformat() if period_start else "",
            period_end="",
            tier_snapshot="",
            status="(no period row)",
            law_limit="",
            used=0,
            remaining="",
            rows=(),
            historical_starts=historical_starts,
            viewing_historical=period_start is not None,
            exists=False,
        )
    items = roster.list_items_for_period(user_id, period.period_start)
    used = sum(1 for item in items if item.is_consumed)
    remaining = _remaining_capacity(period.law_limit, used)
    rows = tuple(
        RosterItemDiagnostic(
            law_id=item.law_id,
            origin=item.origin,
            consumed_at=_iso(item.consumed_at),
            removed_at=_iso(item.removed_at),
            declined_at=_iso(item.declined_at),
            active=item.is_active,
        )
        for item in items
    )
    limit_label = "unlimited" if period.law_limit is None else str(period.law_limit)
    remaining_label = "unlimited" if remaining is None else str(remaining)
    return RosterDiagnostic(
        period_start=period.period_start.isoformat(),
        period_end=period.period_end.isoformat(),
        tier_snapshot=period.tier_snapshot or "—",
        status=period.status,
        law_limit=limit_label,
        used=used,
        remaining=remaining_label,
        rows=rows,
        historical_starts=historical_starts,
        viewing_historical=viewing_historical,
        exists=True,
    )


def _webhook_diag(request: Any, user_id: UUID | str) -> tuple[WebhookEventDiagnostic, ...]:
    service = getattr(request.app.state, "subscription_service", None)
    events_repo = getattr(request.app.state, "webhook_events", None)
    if service is None or events_repo is None:
        return ()
    row = service.get_current(user_id)
    provider_id = row.provider_subscription_id if row is not None else None
    if not provider_id:
        return ()
    lister = getattr(events_repo, "list_events_for_provider_subscription", None)
    if lister is None:
        return ()
    events = lister(provider_id, limit=25)
    out: list[WebhookEventDiagnostic] = []
    for event in events:
        status = str(event.processing_status)
        duplicate = "idempotent/duplicate" if event.attempt_count > 1 else "first delivery"
        if status == "processed" and event.attempt_count > 1:
            duplicate = "idempotent replay"
        out.append(
            WebhookEventDiagnostic(
                event_id=event.id,
                provider_event_id=event.provider_event_id,
                event_name=event.event_name,
                received_at=_iso(event.received_at),
                processed_at=_iso(event.processed_at),
                status=status,
                duplicate_or_idempotent=duplicate,
                error_code=str(event.last_error_code or ""),
            )
        )
    return tuple(out)


def subscription_audit_states(row: Any | None) -> dict[str, Any]:
    """Safe before/after payload for admin_audit_log. No secrets."""

    if row is None:
        return {"present": False}
    return {
        "present": True,
        "tier": row.tier,
        "status": row.status,
        "cancel_at_period_end": bool(row.cancel_at_period_end),
        "provider_subscription_id": mask_provider_id(row.provider_subscription_id),
        "billing_period_start": _iso(row.billing_period_start),
        "billing_period_end": _iso(row.billing_period_end),
    }
