"""Owner device-management HTTP: Profile → Security → Your devices.

Account security, not a paid feature. Authenticated users may list and remove
their installations regardless of subscription state. Mutations go through
``DeviceService``; routes never issue revoke SQL.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from constitution_memorizer.auth.dependencies import require_csrf
from constitution_memorizer.auth.guest import signin_redirect
from constitution_memorizer.auth.sessions import SESSION_COOKIE_NAME
from constitution_memorizer.devices.token import request_device_token

DEVICES_MANAGE_PATH = "/profile/security/devices"


def _device_service(request: Request):
    service = getattr(request.app.state, "device_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Device registry unavailable")
    return service


def _sign_out_keep_device(request: Request) -> RedirectResponse:
    """End ``rtc_session`` after removing this installation. Keep ``rtc_device``."""

    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if session_id:
        request.app.state.session_store.delete(session_id)
    response = RedirectResponse(url="/signed-out", status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    settings = getattr(request.app.state, "multiuser_settings", None)
    if settings is not None and getattr(settings, "cookie_secure", False):
        response.delete_cookie(SESSION_COOKIE_NAME, path="/", secure=True)
    return response


def create_device_router(templates: Jinja2Templates) -> APIRouter:
    router = APIRouter()

    @router.get(DEVICES_MANAGE_PATH, response_class=HTMLResponse)
    async def devices_get(request: Request) -> HTMLResponse:
        user = getattr(request.state, "current_user", None)
        if user is None:
            return signin_redirect(next_url=DEVICES_MANAGE_PATH, reason="default")
        service = _device_service(request)
        token = request_device_token(request)
        summaries = service.list_device_summaries(user.id, token)
        active = [row for row in summaries if row.is_active]
        revoked = [row for row in summaries if not row.is_active]
        confirm_id = (request.query_params.get("confirm") or "").strip()
        confirm_current = next(
            (
                row
                for row in active
                if row.is_current and row.id == confirm_id
            ),
            None,
        )
        return templates.TemplateResponse(
            request,
            "devices.html",
            {
                "devices": summaries,
                "active_devices": active,
                "revoked_devices": revoked,
                "active_count": len(active),
                "device_limit": service.device_limit,
                "confirm_current": confirm_current,
                "removed": request.query_params.get("removed") == "1",
                "csrf_token": request.cookies.get("rtc_csrf") or "",
            },
        )

    @router.post(
        DEVICES_MANAGE_PATH + "/{device_id}/remove",
        dependencies=[Depends(require_csrf)],
    )
    async def devices_remove(request: Request, device_id: str) -> RedirectResponse:
        user = getattr(request.state, "current_user", None)
        if user is None:
            return signin_redirect(next_url=DEVICES_MANAGE_PATH)
        service = _device_service(request)
        existing = service.get_device(user.id, device_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Not Found")
        token = request_device_token(request)
        access = service.inspect_current_device(user.id, token)
        was_current = access.current_device_id == existing.id
        was_active = not existing.is_revoked
        revoked = service.revoke_device(user.id, device_id)
        if revoked is None:
            raise HTTPException(status_code=404, detail="Not Found")
        if was_current and was_active:
            return _sign_out_keep_device(request)
        return RedirectResponse(
            url=f"{DEVICES_MANAGE_PATH}?removed=1", status_code=303
        )

    return router
