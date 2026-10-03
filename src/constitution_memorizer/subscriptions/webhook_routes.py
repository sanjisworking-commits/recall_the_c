"""Machine Razorpay subscription webhook. No session, no CSRF, no app.py logic."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse


def create_webhook_router() -> APIRouter:
    router = APIRouter()

    @router.post("/api/billing/subscriptions/webhook/razorpay")
    async def razorpay_subscription_webhook(request: Request) -> JSONResponse:
        raw_body = await request.body()
        signature = request.headers.get("X-Razorpay-Signature") or ""
        event_id = request.headers.get("X-Razorpay-Event-Id") or ""
        processor = getattr(request.app.state, "webhook_processor", None)
        if processor is None:
            return JSONResponse({"ok": False, "error": "unavailable"}, status_code=503)
        result = processor.process_delivery(raw_body, signature, event_id)
        body: dict[str, object] = {"ok": result.status_code < 300}
        if result.error:
            body["error"] = result.error
        return JSONResponse(body, status_code=result.status_code)

    return router
