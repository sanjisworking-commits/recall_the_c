"""FastAPI dependencies for authentication."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from constitution_memorizer.auth.bearer import resolve_bearer_user
from constitution_memorizer.auth.exceptions import SessionExpiredError
from constitution_memorizer.auth.models import AuthenticatedUser
from constitution_memorizer.auth.sessions import (
    CSRF_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    SessionStore,
    require_session,
)


def _session_store(request: Request) -> SessionStore:
    return request.app.state.session_store


def get_optional_current_user(request: Request) -> AuthenticatedUser | None:
    """Resolve the current user from the browser cookie session OR a native
    client's Supabase bearer token.

    The cookie session is tried first and, when valid, behaves exactly as
    before (it also records ``request.state.auth_session`` so cookie-based CSRF
    validation keeps working). A bearer token is only consulted as a fallback
    when there is no valid cookie session, and it deliberately does NOT set
    ``auth_session`` — bearer requests carry no ambient cookie credential, so
    they neither need nor are granted a CSRF exemption.
    """
    store: SessionStore = request.app.state.session_store
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if session_id:
        session = store.get(session_id)
        if session is not None:
            request.state.auth_session = session
            return session.user
    return resolve_bearer_user(request)


def require_current_user(request: Request) -> AuthenticatedUser:
    user = get_optional_current_user(request)
    if user is None:
        raise HTTPException(
            status_code=303,
            detail="Authentication required",
            headers={"Location": "/login"},
        )
    return user


def require_csrf(request: Request, csrf_token: str | None = Form(default=None)) -> None:
    """Validate CSRF for state-changing form posts."""
    session = getattr(request.state, "auth_session", None)
    if session is None:
        # Allow login routes to validate via cookie pair before session exists.
        cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
        form_token = csrf_token
        if not cookie_token or not form_token or cookie_token != form_token:
            raise HTTPException(status_code=403, detail="CSRF validation failed")
        return
    form_token = csrf_token or request.headers.get("X-CSRF-Token")
    if not form_token or form_token != session.csrf_token:
        raise HTTPException(status_code=403, detail="CSRF validation failed")


def require_api_user(request: Request) -> AuthenticatedUser:
    """Like ``require_current_user`` but for JSON APIs (native clients).

    Resolves from cookie OR bearer, and on failure raises a clean ``401`` with
    a JSON body instead of the browser's ``303`` redirect to ``/login``.
    """
    user = get_optional_current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def require_bearer_user(request: Request) -> AuthenticatedUser:
    """Require a valid Supabase bearer token specifically — never a cookie.

    For native-only endpoints (e.g. the bootstrap handshake) that must run off
    a verified Supabase JWT and must NOT be satisfiable by an ambient
    ``rtc_session`` browser cookie. Cookie sessions are ignored entirely here.
    """
    user = resolve_bearer_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Bearer authentication required")
    return user


CurrentUser = Annotated[AuthenticatedUser, Depends(require_current_user)]
OptionalUser = Annotated[AuthenticatedUser | None, Depends(get_optional_current_user)]
ApiUser = Annotated[AuthenticatedUser, Depends(require_api_user)]
BearerUser = Annotated[AuthenticatedUser, Depends(require_bearer_user)]


def login_redirect() -> RedirectResponse:
    return RedirectResponse(url="/login", status_code=303)
