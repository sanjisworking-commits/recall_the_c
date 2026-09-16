"""Playground commercial HTTP gate. Consumes EntitlementSnapshot only.

Milestone 3B implements authentication + commercial entitlement. Device
enforcement is Milestone 4. Monthly roster enforcement is Milestone 5.

Pending subscribers may open existing overlay items and continue proof
learning. That is a transitional commercial bit, not current-month roster
membership. Overlay rows (``user_playground_item`` / selection / progress)
are persistent learning history, not a roster. M5 replaces this distinction
with ``is_law_active_this_period(law_id)``.

Local single-user mode has no guest/subscribe wall (same as Constitution
``local_owner``). Multi-user Playground never re-derives provider status or
tier inside a handler.

Never calls a payment provider. Never reads billing or claim tables from
this module; commercial answers come from the memoized entitlement snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.responses import Response

from constitution_memorizer.entitlements.dependencies import get_entitlement_snapshot
from constitution_memorizer.entitlements.models import (
    BLOCK_NOT_SUBSCRIBED,
    BLOCK_PAID_PERIOD_ENDED,
    BLOCK_PAYMENT_HALTED,
    BLOCK_SIGN_IN_REQUIRED,
    BLOCK_SUBSCRIPTION_PAUSED,
    EntitlementSnapshot,
)
from constitution_memorizer.playground.eligibility import PlaygroundLawError
from constitution_memorizer.playground.service import activate_law
from constitution_memorizer.playground.http import (
    playground_login_redirect,
    playground_user_id,
)
from constitution_memorizer.playground.urls import home_path

PLAYGROUND_BILLING_PATH = "/billing/subscriptions"
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
}

_NEW_LAW_COPY = {
    "title": "New laws are temporarily unavailable",
    "lede": "",
    "body": (
        "You can keep learning laws already in Playground. "
        "New laws cannot be added while payment retries."
    ),
    "cta_label": "Manage subscription",
}


@dataclass(frozen=True)
class PlaygroundAccess:
    """Resolved commercial capability for one Playground request."""

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
    """Allow existing Playground surfaces, or return the commercial block."""

    access = playground_access(request)
    if access.can_open:
        return access
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
    """Allow creating a new overlay item, or return the commercial block.

    Call only when the user does not already have ``user_playground_item``
    for that law. Existing overlay rows are not a monthly roster; M5 will
    authorize current-period membership separately.
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


def ensure_playground_item(
    request: Request,
    templates: Jinja2Templates,
    repo: Any,
    law_id: str,
    *,
    next_url: str,
) -> PlaygroundAccess | Response:
    """Activate a missing overlay item only when consume is commercially allowed.

    Existing items skip the new-law bit. That is not roster membership.
    """

    opened = require_playground_open(
        request, templates, next_url=next_url
    )
    if isinstance(opened, Response):
        return opened
    if repo.get_item(opened.user_id, law_id) is not None:
        activate_law(repo, opened.user_id, law_id)
        return opened
    allowed = require_playground_new_law(
        request, templates, next_url=next_url
    )
    if isinstance(allowed, Response):
        return allowed
    try:
        activate_law(repo, allowed.user_id, law_id)
    except PlaygroundLawError:
        raise HTTPException(status_code=404, detail="Law not found") from None
    return allowed


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
    else:
        copy = _OPEN_COPY.get(reason, _OPEN_COPY[BLOCK_NOT_SUBSCRIBED])
        if reason == BLOCK_SIGN_IN_REQUIRED:
            cta_href = f"/login?next={home_path()}"
        else:
            cta_href = PLAYGROUND_BILLING_PATH
    return templates.TemplateResponse(
        request,
        "playground_gate.html",
        {
            "title": copy["title"],
            "lede": copy["lede"],
            "body": copy["body"],
            "cta_label": copy["cta_label"],
            "cta_href": cta_href,
            "block_reason": reason,
            "consume_blocked": consume_blocked,
        },
    )


def new_law_home_notice(request: Request, access: PlaygroundAccess) -> str | None:
    """Optional home banner after a blocked add. Not a roster message."""

    if access.can_open and not access.can_consume_new_law:
        blocked = request.query_params.get("blocked")
        if blocked == NEW_LAW_TEMPORARILY_UNAVAILABLE:
            return _NEW_LAW_COPY["body"]
    return None
