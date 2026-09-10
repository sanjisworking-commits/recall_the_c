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


def require_playground_repo(request: Request):
    repo = getattr(request.app.state, "playground", None)
    if repo is None:
        raise HTTPException(status_code=503, detail="Playground unavailable")
    return repo


def playground_login_redirect(next_url: str) -> RedirectResponse:
    return RedirectResponse(url=f"/login?next={next_url}", status_code=303)
