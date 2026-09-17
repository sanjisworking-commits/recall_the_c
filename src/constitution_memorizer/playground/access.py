"""Playground commercial + device + current-period roster HTTP gate.

Locked authorization chain for sensitive law routes:

    commercial entitlement → allowed device → active current-period law

Overlay rows (``user_playground_item`` / selection / progress) are lifetime
learning history, not the roster. Pending subscribers may continue laws that
are active on the **current** roster; historical overlay alone is not enough
to learn or to consume a new law. Same-period re-add of an already-consumed
removed law is not new consumption.

Never calls a payment provider. Never reads billing or claim tables from
this module; commercial answers come from the memoized entitlement snapshot.
Device SQL lives in ``devices/``. Roster SQL lives in ``playground/roster/``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.responses import Response

from constitution_memorizer.entitlements.dependencies import (
    apply_device_access,
    apply_roster_capacity,
    get_entitlement_snapshot,
    invalidate_entitlement_snapshot,
)
from constitution_memorizer.entitlements.models import (
    BLOCK_DEVICE_CONFIG_ERROR,
    BLOCK_DEVICE_LIMIT,
    BLOCK_DEVICE_REPLACEMENT_LIMIT,
    BLOCK_DEVICE_REVOKED,
    BLOCK_NOT_SUBSCRIBED,
    BLOCK_PAID_PERIOD_ENDED,
    BLOCK_PAYMENT_HALTED,
    BLOCK_SIGN_IN_REQUIRED,
    BLOCK_SUBSCRIPTION_PAUSED,
    EntitlementSnapshot,
)
from constitution_memorizer.playground.eligibility import (
    PlaygroundLawError,
    is_playground_eligible_law,
)
from constitution_memorizer.playground.http import (
    playground_login_redirect,
    playground_user_id,
    require_roster_service,
)
from constitution_memorizer.playground.roster.models import (
    BLOCK_PROGRESS_SAVED,
    BLOCK_ROSTER_FULL,
    RESULT_NEW_BLOCKED,
    RESULT_ROSTER_FULL,
    ROSTER_ADD_CONFIRM,
)
from constitution_memorizer.playground.roster.period import playground_month_name
from constitution_memorizer.playground.roster.service import roster_full_body
from constitution_memorizer.playground.urls import home_path, roster_path

PLAYGROUND_BILLING_PATH = "/billing/subscriptions"
CONSTITUTION_HOME_PATH = "/dashboard"
MANAGE_DEVICES_PATH = "/profile/security/devices"
NEW_LAW_TEMPORARILY_UNAVAILABLE = "new_law_temporarily_unavailable"

_OPEN_COPY: dict[str, dict[str, str]] = {
    BLOCK_SIGN_IN_REQUIRED: {
        "title": "Sign in to use Playground",
        "lede": "",
        "body": "Sign in to open Playground. Constitution Learn stays available as a guest.",
        "cta_label": "Sign in",
    },
    BLOCK_NOT_SUBSCRIBED: {
        "title": "Subscribe to use Playground",
        "lede": "Playground is included with Plus, Pro, or Max.",
        "body": (
            "Your RecallC account already includes the complete Constitution. "
            "Subscribe to add laws to Playground."
        ),
        "cta_label": "View Playground plans",
    },
    BLOCK_PAYMENT_HALTED: {
        "title": "Payment retries have stopped",
        "lede": "",
        "body": "Manage your Playground subscription to continue.",
        "cta_label": "Manage subscription",
    },
    BLOCK_SUBSCRIPTION_PAUSED: {
        "title": "Playground subscription is paused",
        "lede": "",
        "body": "Manage your Playground subscription to continue.",
        "cta_label": "Manage subscription",
    },
    BLOCK_PAID_PERIOD_ENDED: {
        "title": "Playground access for this paid period has ended",
        "lede": "",
        "body": "Manage your Playground subscription to continue.",
        "cta_label": "Manage subscription",
    },
    BLOCK_DEVICE_LIMIT: {
        "title": "Device limit reached",
        "lede": "",
        "body": (
            "Your subscription supports Playground on up to 2 registered devices. "
            "Remove a device to use Playground here."
        ),
        "cta_label": "Manage devices",
        "secondary_label": "Back to Constitution",
        "secondary_href": CONSTITUTION_HOME_PATH,
        "cta_href": MANAGE_DEVICES_PATH,
    },
    BLOCK_DEVICE_REVOKED: {
        "title": "This device no longer has Playground access.",
        "lede": "",
        "body": "Constitution Learn stays available on this installation.",
        "cta_label": "Manage devices",
        "secondary_label": "Back to Constitution",
        "secondary_href": CONSTITUTION_HOME_PATH,
        "cta_href": MANAGE_DEVICES_PATH,
    },
    BLOCK_DEVICE_CONFIG_ERROR: {
        "title": "Playground is temporarily unavailable on this device",
        "lede": "",
        "body": "Constitution Learn stays available. Try again from this installation later.",
        "cta_label": "Back to Constitution",
        "cta_href": CONSTITUTION_HOME_PATH,
    },
    BLOCK_DEVICE_REPLACEMENT_LIMIT: {
        "title": "Too many recent device changes",
        "lede": "",
        "body": (
            "For account security, new Playground devices are temporarily limited "
            "after several device replacements. "
            "Your Constitution access and saved progress are unaffected. "
            "You can try again after the recent-device-change window clears."
        ),
        "cta_label": "Contact support",
        "secondary_label": "Back to Constitution",
        "secondary_href": CONSTITUTION_HOME_PATH,
    },
}

_NEW_LAW_COPY = {
    "title": "New laws are temporarily unavailable",
    "lede": "",
    "body": (
        "You can keep learning laws already in this month’s Playground. "
        "New laws cannot be added while payment retries."
    ),
    "cta_label": "Manage subscription",
}

_PROGRESS_SAVED_COPY = {
    "title": "Progress saved",
    "lede": "",
    "body": "Add to this month",
    "cta_label": "Add to this month",
}

_DEVICE_OPEN_REASONS = frozenset(
    {
        BLOCK_DEVICE_LIMIT,
        BLOCK_DEVICE_REVOKED,
        BLOCK_DEVICE_CONFIG_ERROR,
        BLOCK_DEVICE_REPLACEMENT_LIMIT,
    }
)


@dataclass(frozen=True)
class PlaygroundAccess:
    """Resolved commercial + device capability for one Playground request."""

    user_id: Any
    snapshot: EntitlementSnapshot | None
    can_open: bool
    can_consume_new_law: bool
    local_owner: bool


def playground_access(request: Request) -> PlaygroundAccess:
    """Resolve once. Snapshot is memoized on ``request.state``."""

    uid = playground_user_id(request)
    if not getattr(request.app.state, "multiuser_enabled", False):
        return PlaygroundAccess(
            user_id=uid,
            snapshot=None,
            can_open=True,
            can_consume_new_law=True,
            local_owner=True,
        )
    snapshot = get_entitlement_snapshot(request)
    if snapshot.admin_override:
        return PlaygroundAccess(
            user_id=uid,
            snapshot=snapshot,
            can_open=True,
            can_consume_new_law=True,
            local_owner=False,
        )
    if snapshot.is_subscribed:
        snapshot = _ensure_device_and_refresh(request, snapshot)
    return PlaygroundAccess(
        user_id=uid,
        snapshot=snapshot,
        can_open=snapshot.can_open_playground,
        can_consume_new_law=snapshot.can_consume_new_playground_law,
        local_owner=False,
    )


def require_playground_open(
    request: Request,
    templates: Jinja2Templates,
    *,
    next_url: str,
    json_mode: bool = False,
) -> PlaygroundAccess | Response:
    """Allow existing Playground surfaces, or return the commercial/device block."""

    access = playground_access(request)
    if access.can_open:
        return _attach_current_period(request, access)
    return _deny_open(
        request,
        templates,
        access,
        next_url=next_url,
        json_mode=json_mode,
    )


def require_playground_new_law(
    request: Request,
    templates: Jinja2Templates,
    *,
    next_url: str,
    json_mode: bool = False,
) -> PlaygroundAccess | Response:
    """Allow **new** roster consumption, or return the pending/commercial block.

    Do not use this for same-period re-add of an already-consumed law.
    """

    opened = require_playground_open(
        request, templates, next_url=next_url, json_mode=json_mode
    )
    if isinstance(opened, Response):
        return opened
    if opened.can_consume_new_law:
        return opened
    return _deny_new_law(
        request,
        templates,
        opened,
        json_mode=json_mode,
    )


def require_law_active_this_period(
    request: Request,
    templates: Jinja2Templates,
    overlay,
    law_id: str,
    *,
    next_url: str,
    json_mode: bool = False,
) -> PlaygroundAccess | Response:
    """Require current-roster membership before Act hydration or paid Learn."""

    opened = require_playground_open(
        request, templates, next_url=next_url, json_mode=json_mode
    )
    if isinstance(opened, Response):
        return opened
    roster = require_roster_service(request)
    if roster.is_law_active_this_period(opened.user_id, law_id):
        return opened
    return _deny_inactive_law(
        request,
        templates,
        opened,
        overlay,
        law_id,
        json_mode=json_mode,
    )


def is_add_confirmed(value: str) -> bool:
    return str(value or "").strip().lower() == ROSTER_ADD_CONFIRM


def require_eligible_law(law_id: str) -> str:
    if not is_playground_eligible_law(law_id):
        raise HTTPException(status_code=404, detail="Law not found")
    return law_id


def _attach_current_period(request: Request, access: PlaygroundAccess) -> PlaygroundAccess:
    if access.user_id is None:
        return access
    roster = getattr(request.app.state, "roster", None)
    if roster is None:
        return access
    capacity = roster.capacity(
        access.user_id,
        access.snapshot,
        local_owner=access.local_owner,
    )
    if access.snapshot is None:
        return access
    refreshed = apply_roster_capacity(access.snapshot, capacity)
    request.state.entitlement_snapshot = refreshed
    return PlaygroundAccess(
        user_id=access.user_id,
        snapshot=refreshed,
        can_open=access.can_open,
        can_consume_new_law=access.can_consume_new_law,
        local_owner=access.local_owner,
    )


def _ensure_device_and_refresh(
    request: Request, snapshot: EntitlementSnapshot
) -> EntitlementSnapshot:
    service = getattr(request.app.state, "device_service", None)
    if service is None:
        return snapshot
    user = getattr(request.state, "current_user", None)
    if user is None:
        return snapshot
    from constitution_memorizer.devices.models import PLATFORM_WEB
    from constitution_memorizer.devices.token import (
        display_name_from_user_agent,
        request_device_token,
    )

    session = getattr(request.state, "auth_session", None)
    session_id = getattr(session, "session_id", None)
    access = service.ensure_current_device(
        user.id,
        request_device_token(request),
        auth_session_id=session_id,
        commercially_eligible=True,
        admin_override=False,
        # Website cookie installation. Safari on iPhone stays web; native
        # iOS apps are not registered from this HTTP path.
        platform=PLATFORM_WEB,
        display_name=display_name_from_user_agent(
            request.headers.get("user-agent")
        ),
    )
    invalidate_entitlement_snapshot(request)
    refreshed = apply_device_access(snapshot, access)
    request.state.entitlement_snapshot = refreshed
    return refreshed


def _deny_open(
    request: Request,
    templates: Jinja2Templates,
    access: PlaygroundAccess,
    *,
    next_url: str,
    json_mode: bool,
) -> Response:
    snapshot = access.snapshot
    reason = (
        snapshot.playground_block_reason
        if snapshot is not None
        else BLOCK_SIGN_IN_REQUIRED
    )
    if reason == BLOCK_SIGN_IN_REQUIRED or access.user_id is None:
        if json_mode:
            return JSONResponse({"ok": False, "error": "auth_required"}, status_code=401)
        return playground_login_redirect(next_url)
    if json_mode:
        return JSONResponse({"ok": False, "error": reason}, status_code=403)
    if request.method.upper() != "GET":
        return RedirectResponse(url=home_path(), status_code=303)
    return _gate_page(request, templates, reason=reason, consume_blocked=False)


def _deny_new_law(
    request: Request,
    templates: Jinja2Templates,
    access: PlaygroundAccess,
    *,
    json_mode: bool,
) -> Response:
    if json_mode:
        return JSONResponse(
            {"ok": False, "error": NEW_LAW_TEMPORARILY_UNAVAILABLE},
            status_code=403,
        )
    if request.method.upper() != "GET":
        return RedirectResponse(
            url=f"{home_path()}?blocked={NEW_LAW_TEMPORARILY_UNAVAILABLE}",
            status_code=303,
        )
    return _gate_page(
        request,
        templates,
        reason=NEW_LAW_TEMPORARILY_UNAVAILABLE,
        consume_blocked=True,
        snapshot=access.snapshot,
    )


def _deny_inactive_law(
    request: Request,
    templates: Jinja2Templates,
    access: PlaygroundAccess,
    overlay: Any,
    law_id: str,
    *,
    json_mode: bool,
) -> Response:
    if json_mode:
        return JSONResponse(
            {"ok": False, "error": "not_active_this_period"},
            status_code=403,
        )
    historical = overlay.get_item(access.user_id, law_id) is not None
    if request.method.upper() != "GET":
        if historical:
            return RedirectResponse(url=roster_path(add=law_id), status_code=303)
        return RedirectResponse(url=f"/laws/{law_id}", status_code=303)
    if not historical:
        return RedirectResponse(url=f"/laws/{law_id}", status_code=303)
    roster = require_roster_service(request)
    already = roster.already_consumed_this_period(access.user_id, law_id)
    if already:
        return _progress_saved_page(request, templates, law_id)
    if not access.can_consume_new_law:
        return _gate_page(
            request,
            templates,
            reason=NEW_LAW_TEMPORARILY_UNAVAILABLE,
            consume_blocked=True,
            snapshot=access.snapshot,
        )
    snapshot = access.snapshot
    remaining = snapshot.playground_laws_remaining if snapshot is not None else None
    if remaining == 0:
        return roster_full_page(request, templates, access)
    return _progress_saved_page(request, templates, law_id)


def roster_full_page(
    request: Request,
    templates: Jinja2Templates,
    access: PlaygroundAccess,
) -> Response:
    snapshot = access.snapshot
    month = "this month"
    limit = 10
    if snapshot is not None and snapshot.playground_period_start is not None:
        month = playground_month_name(snapshot.playground_period_start)
    if snapshot is not None and snapshot.playground_law_limit is not None:
        limit = snapshot.playground_law_limit
    return templates.TemplateResponse(
        request,
        "playground_gate.html",
        {
            "title": "Playground full",
            "lede": "",
            "body": roster_full_body(month_name=month, law_limit=limit),
            "cta_label": "Back to Playground",
            "cta_href": home_path(),
            "secondary_label": "Manage roster",
            "secondary_href": roster_path(),
            "block_reason": BLOCK_ROSTER_FULL,
            "consume_blocked": False,
        },
    )


def _progress_saved_page(
    request: Request,
    templates: Jinja2Templates,
    law_id: str,
) -> Response:
    copy = _PROGRESS_SAVED_COPY
    return templates.TemplateResponse(
        request,
        "playground_gate.html",
        {
            "title": copy["title"],
            "lede": copy["lede"],
            "body": copy["body"],
            "cta_label": copy["cta_label"],
            "cta_href": roster_path(add=law_id),
            "secondary_label": "Back to Playground",
            "secondary_href": home_path(),
            "block_reason": BLOCK_PROGRESS_SAVED,
            "consume_blocked": False,
        },
    )


def consume_blocked_response(
    request: Request,
    templates: Jinja2Templates,
    access: PlaygroundAccess,
    result_status: str,
    *,
    json_mode: bool = False,
) -> Response:
    if result_status == RESULT_NEW_BLOCKED:
        return _deny_new_law(
            request, templates, access, json_mode=json_mode
        )
    if result_status == RESULT_ROSTER_FULL:
        if json_mode:
            return JSONResponse({"ok": False, "error": BLOCK_ROSTER_FULL}, status_code=403)
        return roster_full_page(request, templates, access)
    if json_mode:
        return JSONResponse({"ok": False, "error": result_status}, status_code=400)
    raise PlaygroundLawError(result_status)


def _gate_page(
    request: Request,
    templates: Jinja2Templates,
    *,
    reason: str,
    consume_blocked: bool,
    snapshot: EntitlementSnapshot | None = None,
) -> Response:
    del snapshot  # Copy is keyed by reason, never raw provider status.
    if consume_blocked:
        copy = _NEW_LAW_COPY
        cta_href = PLAYGROUND_BILLING_PATH
        secondary_label = ""
        secondary_href = ""
    else:
        copy = _OPEN_COPY.get(reason, _OPEN_COPY[BLOCK_NOT_SUBSCRIBED])
        if reason == BLOCK_DEVICE_REPLACEMENT_LIMIT:
            cta_href = _support_mailto(request) or ""
        elif reason in _DEVICE_OPEN_REASONS:
            cta_href = copy.get("cta_href", MANAGE_DEVICES_PATH)
        elif reason == BLOCK_SIGN_IN_REQUIRED:
            cta_href = f"/login?next={home_path()}"
        else:
            cta_href = PLAYGROUND_BILLING_PATH
        secondary_label = copy.get("secondary_label", "")
        secondary_href = copy.get("secondary_href", "")
    return templates.TemplateResponse(
        request,
        "playground_gate.html",
        {
            "title": copy["title"],
            "lede": copy["lede"],
            "body": copy["body"],
            "cta_label": copy["cta_label"],
            "cta_href": cta_href,
            "secondary_label": secondary_label,
            "secondary_href": secondary_href,
            "block_reason": reason,
            "consume_blocked": consume_blocked,
        },
    )


def new_law_home_notice(request: Request, access: PlaygroundAccess) -> str | None:
    """Optional home banner after a blocked add. Not a capacity message."""

    if access.can_open and not access.can_consume_new_law:
        blocked = request.query_params.get("blocked")
        if blocked == NEW_LAW_TEMPORARILY_UNAVAILABLE:
            return _NEW_LAW_COPY["body"]
    return None


def _support_mailto(request: Request) -> str:
    """Return a mailto CTA only when SUPPORT_EMAIL is configured. Never invent one."""

    settings = getattr(request.app.state, "multiuser_settings", None)
    email = ""
    if settings is not None:
        email = (getattr(settings, "support_email", "") or "").strip()
    if not email:
        return ""
    return f"mailto:{email}"
