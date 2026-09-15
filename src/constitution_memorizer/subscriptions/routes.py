"""Playground subscription HTTP. Billing domain — not /playground and not app.py."""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

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


def create_subscription_router(templates: Jinja2Templates) -> APIRouter:
    router = APIRouter(prefix="/billing/subscriptions")

    @router.get("", response_class=HTMLResponse)
    @router.get("/", response_class=HTMLResponse)
    async def manage_page(request: Request, error: str | None = None) -> HTMLResponse:
        service = require_subscription_service(request)
        uid = subscription_user_id(request)
        current = service.get_current(uid) if uid is not None else None
        products = [
            {
                "tier": product.tier,
                "display_name": product.display_name,
                "price_label": _price_label(product.price_inr),
                "limit_label": _limit_label(product.playground_law_limit),
            }
            for product in list_subscription_products()
        ]
        return templates.TemplateResponse(
            request,
            "subscription_manage.html",
            {
                "products": products,
                "current": _public_current(current) if current is not None else None,
                "upgrades": _change_targets(current, upgrade=True),
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
                "signed_in": uid is not None,
                "error_message": ERROR_MESSAGES.get(error or "", ""),
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
