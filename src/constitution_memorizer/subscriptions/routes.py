"""Playground subscription HTTP. Billing domain — not /playground and not app.py."""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from constitution_memorizer.entitlements.dependencies import (
    request_is_active_plus,
    request_is_expired_subscriber,
    request_is_halted_subscriber,
)
from constitution_memorizer.entitlements.models import (
    BLOCK_PAID_PERIOD_ENDED,
    BLOCK_PAYMENT_HALTED,
)
from constitution_memorizer.playground.view import gate_view
from constitution_memorizer.subscriptions.catalog import (
    UnknownSubscriptionTier,
    is_downgrade,
    is_upgrade,
    list_subscription_products,
)
from constitution_memorizer.subscriptions.errors import (
    ChangePlanRequiredError,
    CheckoutInProgressError,
    CheckoutMismatchError,
    CheckoutSignatureError,
    CurrentSubscriptionExistsError,
    InvalidSubscriptionValue,
    ResubscribeUnavailableError,
    SameTierChangeError,
    SubscriptionConfigError,
    SubscriptionProviderError,
    SubscriptionStateError,
)
from constitution_memorizer.subscriptions.http import (
    MANAGE_PATH,
    require_csrf_token,
    require_subscription_service,
    signin_for_subscriptions,
    subscription_user_id,
)
from constitution_memorizer.subscriptions.models import UserSubscription
from constitution_memorizer.subscriptions.service import TERMINAL_STATUSES

LIFECYCLE_MESSAGES = {
    "pending": "Payment retry in progress",
    "halted": "Automatic retries have stopped",
    "paused": "Subscription paused",
    "expired": "Subscription checkout expired",
    "cancelled": "Previous subscription ended; subscribe again",
    "completed": "Previous subscription ended; subscribe again",
}
ENDED_MESSAGE = "Previous subscription ended; subscribe again"
ERROR_MESSAGES = {
    "config": "Payment provider is not configured.",
    "provider": "Could not complete the payment-provider request. Nothing else changed.",
    "invalid_tier": "Choose Plus, Pro, or Max.",
    "csrf": "That request could not be verified. Refresh and try again.",
    "in_progress": "Subscription creation is already in progress.",
    "change_required": "You already have a Playground subscription. Use change plan.",
    "resubscribe": "Resubscribe is not available yet.",
    "same_tier": "You are already on that plan.",
    "state": "That action is not available for the current subscription.",
    "signature": "Checkout could not be verified. Nothing was changed.",
    "mismatch": "Checkout did not match this account. Nothing was changed.",
    "unpaid_cancel": "This checkout is not an active paid cycle, so it cannot be cancelled at period end.",
}

# Plus desktop Screen 07 display copy. Catalog has no taglines; these strings
# are the established Desktop Playground plan copy
# (docs/design/Recall the C - Playground Desktop.dc.html).
PLUS_DESK_LEDE = "Upgrades take effect immediately; downgrades apply from the 1st of next month. Laws already in your Playground keep working."  # Desktop.dc.html:2662
PLUS_DESK_GST = "GST inclusive. Renews monthly until you cancel. Your Playground progress is never deleted."  # Desktop.dc.html:1280
PLUS_DESK_EXPLAIN = "The plan only sets how many laws can be active in your Playground each calendar month. Subscribe on any day and this month's spaces open at once; a new set opens on the 1st. Laws already in your Playground keep working, and your progress is never deleted."  # Desktop.dc.html:1282
PLUS_DESK_INCLUDED = "Every Article · All six recall methods · Free."  # Desktop.dc.html:1286
_CARD_DESCRIPTIONS = {
    "plus": "A steady pace — enough for one exam’s syllabus of Acts.",  # Desktop.dc.html:2140
    "pro": "Broad preparation across many Acts at once.",  # Desktop.dc.html:2141
    "max": "The whole law library, whenever you want it.",  # Desktop.dc.html:2142
}


def create_subscription_router(templates: Jinja2Templates) -> APIRouter:
    router = APIRouter(prefix="/billing/subscriptions")

    @router.get("", response_class=HTMLResponse)
    @router.get("/", response_class=HTMLResponse)
    async def manage_page(request: Request, error: str | None = None) -> HTMLResponse:
        service = require_subscription_service(request)
        uid = subscription_user_id(request)
        current = service.get_current(uid) if uid is not None else None
        # Shared paid_period_ended predicate, but only when the current row is
        # already terminal/historical. Live current rows (active, including
        # cancel-at-period-end) keep the existing current-plan surface.
        halted_subscription = request_is_halted_subscriber(request)
        halted_header_status = ""
        if halted_subscription:
            halted_header_status = gate_view(reason=BLOCK_PAYMENT_HALTED).title
        expired_subscription = bool(
            request_is_expired_subscriber(request)
            and (current is None or current.status in TERMINAL_STATUSES)
        )
        expired_header_status = ""
        if expired_subscription:
            expired_header_status = gate_view(reason=BLOCK_PAID_PERIOD_ENDED).title
        ended_message = ""
        if uid is not None and current is None:
            history = service.list_history(uid)
            if any(row.status in {"cancelled", "completed", "expired"} for row in history):
                ended_message = ENDED_MESSAGE
        elif expired_subscription:
            ended_message = ENDED_MESSAGE
        upgrades = _change_targets(current, upgrade=True)
        upgrade_tiers = {row["tier"] for row in upgrades}
        products = [
            {
                "tier": product.tier,
                "display_name": product.display_name,
                "price_label": _price_label(product.price_inr),
                "price_display": f"₹{product.price_inr:,}",
                "limit_label": _limit_label(product.playground_law_limit),
                "card_limit_label": _card_limit_label(product.playground_law_limit),
                "description": _card_description(product.tier),
                "is_current": bool(
                    current is not None
                    and current.tier == product.tier
                    and not expired_subscription
                ),
                "is_upgrade": product.tier in upgrade_tiers,
            }
            for product in list_subscription_products()
        ]
        return templates.TemplateResponse(
            request,
            "subscription_manage.html",
            {
                "products": products,
                "current": _public_current(current) if current is not None else None,
                "upgrades": upgrades,
                "downgrades": _change_targets(current, upgrade=False),
                "can_cancel": bool(
                    current is not None
                    and current.status == "active"
                    and current.provider_subscription_id
                ),
                "can_checkout": bool(
                    current is not None
                    and current.status == "created"
                    and current.provider_subscription_id
                ),
                "ended_message": ended_message,
                "signed_in": uid is not None,
                "error_message": ERROR_MESSAGES.get(error or "", ""),
                "plus_subscription": request_is_active_plus(request),
                "halted_subscription": halted_subscription,
                "halted_header_status": halted_header_status,
                "expired_subscription": expired_subscription,
                "expired_header_status": expired_header_status,
                "plus_plan_lede": PLUS_DESK_LEDE,
                "plus_plan_gst": PLUS_DESK_GST,
                "plus_plan_explain": PLUS_DESK_EXPLAIN,
                "plus_included_lede": PLUS_DESK_INCLUDED,
            },
        )

    @router.post("/create")
    async def create_subscription(
        request: Request,
        tier: str = Form(""),
        csrf_token: str = Form(""),
    ) -> RedirectResponse:
        uid = subscription_user_id(request)
        if uid is None:
            return signin_for_subscriptions()
        require_csrf_token(request, csrf_token)
        service = require_subscription_service(request)
        try:
            service.start_subscription(uid, tier)
        except UnknownSubscriptionTier:
            return _manage_error("invalid_tier")
        except InvalidSubscriptionValue:
            return _manage_error("invalid_tier")
        except SubscriptionConfigError:
            return _manage_error("config")
        except SubscriptionProviderError:
            return _manage_error("provider")
        except CheckoutInProgressError:
            return _manage_error("in_progress")
        except ChangePlanRequiredError:
            return _manage_error("change_required")
        except ResubscribeUnavailableError:
            return _manage_error("resubscribe")
        except CurrentSubscriptionExistsError:
            return _manage_error("change_required")
        except SubscriptionStateError:
            return _manage_error("state")
        return RedirectResponse(url=f"{MANAGE_PATH}/checkout", status_code=303)

    @router.get("/checkout", response_class=HTMLResponse, response_model=None)
    async def checkout_page(request: Request) -> Response:
        uid = subscription_user_id(request)
        if uid is None:
            return signin_for_subscriptions()
        service = require_subscription_service(request)
        current = service.get_current(uid)
        if current is None or not current.provider_subscription_id:
            return RedirectResponse(url=MANAGE_PATH, status_code=303)
        try:
            handoff = service.checkout_handoff(current)
        except SubscriptionStateError:
            return RedirectResponse(url=MANAGE_PATH, status_code=303)
        except SubscriptionConfigError:
            return _manage_error("config")
        payload = handoff.as_browser_payload()
        payload["csrf_token"] = str(
            getattr(getattr(request.state, "auth_session", None), "csrf_token", None)
            or request.cookies.get("rtc_csrf")
            or ""
        )
        product = next(
            (
                row
                for row in list_subscription_products()
                if row.tier == current.tier
            ),
            None,
        )
        return templates.TemplateResponse(
            request,
            "subscription_checkout.html",
            {
                "checkout_data": payload,
                "display_name": handoff.display_name,
                "description": handoff.description,
                "price_label": _price_label(product.price_inr) if product else "",
            },
        )

    @router.post("/checkout/complete")
    async def checkout_complete(request: Request) -> JSONResponse:
        uid = subscription_user_id(request)
        if uid is None:
            return JSONResponse(
                {"ok": False, "error": "sign_in_required"}, status_code=401
            )
        try:
            body = await request.json()
        except Exception:
            body = {}
        require_csrf_token(request, str(body.get("csrf_token") or ""))
        service = require_subscription_service(request)
        try:
            stored = service.complete_checkout(
                uid,
                razorpay_payment_id=str(body.get("razorpay_payment_id") or ""),
                razorpay_subscription_id=str(
                    body.get("razorpay_subscription_id") or ""
                ),
                razorpay_signature=str(body.get("razorpay_signature") or ""),
            )
        except CheckoutSignatureError:
            return JSONResponse(
                {"ok": False, "error": "signature_mismatch"}, status_code=400
            )
        except CheckoutMismatchError:
            return JSONResponse(
                {"ok": False, "error": "subscription_mismatch"}, status_code=400
            )
        except SubscriptionConfigError:
            return JSONResponse({"ok": False, "error": "config"}, status_code=503)
        except SubscriptionProviderError:
            return JSONResponse({"ok": False, "error": "provider"}, status_code=503)
        except SubscriptionStateError:
            return JSONResponse({"ok": False, "error": "state"}, status_code=409)
        return JSONResponse(
            {
                "ok": True,
                "next": MANAGE_PATH,
                "status": stored.status,
            }
        )

    @router.post("/cancel")
    async def cancel_subscription(
        request: Request,
        csrf_token: str = Form(""),
    ) -> RedirectResponse:
        uid = subscription_user_id(request)
        if uid is None:
            return signin_for_subscriptions()
        require_csrf_token(request, csrf_token)
        service = require_subscription_service(request)
        try:
            service.cancel_at_cycle_end(uid)
        except SubscriptionConfigError:
            return _manage_error("config")
        except SubscriptionProviderError:
            return _manage_error("provider")
        except SubscriptionStateError:
            return _manage_error("unpaid_cancel")
        return RedirectResponse(url=MANAGE_PATH, status_code=303)

    @router.post("/change")
    async def change_subscription(
        request: Request,
        tier: str = Form(""),
        csrf_token: str = Form(""),
    ) -> RedirectResponse:
        uid = subscription_user_id(request)
        if uid is None:
            return signin_for_subscriptions()
        require_csrf_token(request, csrf_token)
        service = require_subscription_service(request)
        try:
            service.change_plan(uid, tier)
        except UnknownSubscriptionTier:
            return _manage_error("invalid_tier")
        except InvalidSubscriptionValue:
            return _manage_error("invalid_tier")
        except SameTierChangeError:
            return _manage_error("same_tier")
        except SubscriptionConfigError:
            return _manage_error("config")
        except SubscriptionProviderError:
            return _manage_error("provider")
        except SubscriptionStateError:
            return _manage_error("state")
        return RedirectResponse(url=MANAGE_PATH, status_code=303)

    return router


def _manage_error(code: str) -> RedirectResponse:
    return RedirectResponse(url=f"{MANAGE_PATH}?error={code}", status_code=303)


def _price_label(price_inr: int) -> str:
    return f"₹{price_inr:,}/month"


def _limit_label(limit: int | None) -> str:
    if limit is None:
        return "Unlimited active Playground laws per monthly Playground period"
    return f"{limit} active Playground laws per monthly Playground period"


def _card_limit_label(limit: int | None) -> str:
    if limit is None:
        return "Unlimited Playground"
    noun = "law" if limit == 1 else "laws"
    return f"{limit} {noun} active per month"


def _card_description(tier: str) -> str:
    return _CARD_DESCRIPTIONS.get(tier, "")


def _public_current(row: UserSubscription) -> dict[str, object]:
    product = next(
        (item for item in list_subscription_products() if item.tier == row.tier),
        None,
    )
    scheduled = row.provider_metadata.get("scheduled_tier")
    return {
        "tier": row.tier,
        "display_name": product.display_name if product else row.tier,
        "price_label": _price_label(product.price_inr) if product else "",
        "status": row.status,
        "cancel_at_period_end": row.cancel_at_period_end,
        "billing_period_end": row.billing_period_end,
        "scheduled_tier": scheduled if isinstance(scheduled, str) else "",
        "lifecycle_message": LIFECYCLE_MESSAGES.get(row.status, ""),
    }


def _change_targets(
    current: UserSubscription | None, *, upgrade: bool
) -> list[dict[str, str]]:
    if current is None or current.status != "active":
        return []
    rows = []
    for product in list_subscription_products():
        if upgrade and is_upgrade(current.tier, product.tier):
            rows.append(
                {
                    "tier": product.tier,
                    "display_name": product.display_name,
                    "price_label": _price_label(product.price_inr),
                }
            )
        if not upgrade and is_downgrade(current.tier, product.tier):
            rows.append(
                {
                    "tier": product.tier,
                    "display_name": product.display_name,
                    "price_label": _price_label(product.price_inr),
                }
            )
    return rows
