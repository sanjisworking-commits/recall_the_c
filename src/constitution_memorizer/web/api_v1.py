"""Versioned JSON API for native clients (Android).

Step 7 scope: the authentication foundation only. These endpoints let a native
app that has signed in with Supabase present its access JWT as
``Authorization: Bearer <token>`` and be recognised as the same RecallC user the
browser flow produces — without imitating the cookie/CSRF flow.

``GET /api/v1/me`` is a general authenticated endpoint (cookie OR bearer via
``require_api_user``). ``POST /api/v1/auth/bootstrap`` is native-only: it
requires an actual Supabase bearer token (``require_bearer_user``) and cannot be
satisfied by an ``rtc_session`` cookie. No new credential is minted: the
verified Supabase JWT is the API credential, and the app keeps sending it on
each request. See ``auth/bearer.py`` for verification + caching.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from constitution_memorizer.auth.dependencies import ApiUser, BearerUser
from constitution_memorizer.auth.models import AuthenticatedUser
from constitution_memorizer.auth.routes import sync_profile_and_identity


def _user_public(user: AuthenticatedUser, *, display_name: str | None = None) -> dict:
    """Minimal, safe projection of a user for JSON responses.

    Only non-sensitive identity fields already present on the authenticated
    user / profile model. Never includes tokens or any server secret.
    """
    return {
        "id": str(user.id),
        "email": user.email,
        "phone": user.phone,
        "display_name": display_name if display_name is not None else user.display_name,
        "provider": user.provider,
    }


def create_api_v1_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    @router.post("/auth/bootstrap")
    async def bootstrap(request: Request, user: BearerUser) -> JSONResponse:
        """Bootstrap-sync a native sign-in from a verified Supabase bearer token.

        Requires an actual bearer token (``require_bearer_user``) — a browser
        ``rtc_session`` cookie is deliberately NOT accepted here. The token has
        already been verified; we upsert the local profile + durable identity
        (same logic the browser login uses) so the Supabase identity maps to the
        canonical RecallC user, then echo the safe identity back. No RecallC
        session/cookie is created — the client keeps authenticating with its
        Supabase JWT.
        """
        sync_profile_and_identity(request.app.state.engine.repo, user)
        return JSONResponse({"ok": True, "user": _user_public(user)})

    @router.get("/me")
    async def me(request: Request, user: ApiUser) -> JSONResponse:
        """Return the authenticated user's safe identity."""
        display_name = user.display_name
        if not display_name:
            # Fall back to a name set during onboarding (browser /welcome).
            try:
                profile = request.app.state.engine.repo.get_profile(user.id)
            except Exception:  # noqa: BLE001 — profile read is best-effort here
                profile = None
            if profile:
                display_name = profile.get("display_name") or None
        return JSONResponse({"ok": True, "user": _user_public(user, display_name=display_name)})

    return router
