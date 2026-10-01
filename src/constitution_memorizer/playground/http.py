"""Request helpers shared by Playground routes and public Bare Act pages."""

from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse

from constitution_memorizer.progress.user_ids import LOCAL_USER_ID


def playground_user_id(request: Request):
    if request.app.state.multiuser_enabled:
        user = getattr(request.state, "current_user", None)
        if user is None:
            return None
        return user.id
    return LOCAL_USER_ID


def local_next_path(next_url: str, fallback: str = "/playground") -> str:
    """Accept only a same-origin path. Never an off-site next."""

    text = str(next_url or "").strip() or fallback
    if not text.startswith("/") or text.startswith("//"):
        return fallback
    if "://" in text.split("?", 1)[0]:
        return fallback
    return text


def playground_login_href(next_url: str) -> str:
    return f"/login?next={local_next_path(next_url)}"


def require_playground_repo(request: Request):
    repo = getattr(request.app.state, "playground", None)
    if repo is None:
        raise HTTPException(status_code=503, detail="Playground unavailable")
    return repo


def require_roster_service(request: Request):
    service = getattr(request.app.state, "roster", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Playground unavailable")
    return service


def playground_login_redirect(next_url: str) -> RedirectResponse:
    return RedirectResponse(url=playground_login_href(next_url), status_code=303)
