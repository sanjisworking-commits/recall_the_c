"""Request helpers for subscription HTTP. Isolated from Playground routes."""

from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse

from constitution_memorizer.auth.sessions import CSRF_COOKIE_NAME
from constitution_memorizer.progress.user_ids import LOCAL_USER_ID

MANAGE_PATH = "/billing/subscriptions"


def subscription_user_id(request: Request):
    if request.app.state.multiuser_enabled:
        user = getattr(request.state, "current_user", None)
        if user is None:
            return None
        return user.id
    return LOCAL_USER_ID


def require_subscription_service(request: Request):
    service = getattr(request.app.state, "subscription_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Subscriptions unavailable")
    return service


def require_csrf_token(request: Request, submitted: str = "") -> None:
    """Same-origin CSRF for hosted subscription mutations.

    Local single-user mode may have no CSRF cookie. A hosted session
    without a matching token is rejected even when the cookie is missing.
    """

    expected = request.cookies.get(CSRF_COOKIE_NAME) or ""
    header = request.headers.get("X-CSRF-Token") or ""
    session = getattr(request.state, "auth_session", None)
    multiuser = bool(getattr(request.app.state, "multiuser_enabled", False))
    if not expected:
        if multiuser and session is not None:
            raise HTTPException(status_code=403, detail="csrf")
        return
    if submitted != expected and header != expected:
        raise HTTPException(status_code=403, detail="csrf")


def signin_for_subscriptions() -> RedirectResponse:
    return RedirectResponse(
        url=f"/login?next={MANAGE_PATH}",
        status_code=303,
    )
