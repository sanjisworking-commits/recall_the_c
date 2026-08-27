"""Guest-first access helpers for multi-user mode."""

from __future__ import annotations

from urllib.parse import urlencode

from fastapi.responses import RedirectResponse

# Paths guests may freely read/try (GET). Mutating POSTs are still gated.
GUEST_PUBLIC_PREFIXES = (
    "/login",
    "/auth/",
    "/static/",
    "/health",
    "/sitemap.xml",
    "/robots.txt",
    "/browse",
    "/search",
    "/tables",
    "/laws",
    "/welcome",
    "/session-expired",
    "/signed-out",
    "/terms",
    "/privacy",
    "/grievance",
    "/profile",  # GET redirects to login in handler; POST requires auth
)

# Personal surfaces — unauthenticated users see a gate or redirect to sign-in.
AUTH_REQUIRED_PREFIXES = (
    "/dashboard",
    "/progress",
    "/calendar",
    "/memory",
    "/settings",
    "/api/theme",
    "/api/explainers",
    "/admin",
)

# Learn/progress mutations that require an account.
AUTH_REQUIRED_EXACT_SUFFIXES = (
    "/done",
    "/again",
    "/seen",
    "/reset",
    "/choose",
    "/notes",
    "/photo",
)


def is_guest_public_get(path: str, method: str) -> bool:
    if method.upper() != "GET":
        return False
    if path == "/" or path == "/learn" or path.startswith("/learn/"):
        return True
    return any(
        path == p or path.startswith(p + "/") or path.startswith(p)
        for p in GUEST_PUBLIC_PREFIXES
        if p != "/profile"
    )


def requires_auth(path: str, method: str) -> bool:
    """Return True when an unauthenticated request must be blocked."""
    m = method.upper()
    if path.startswith("/auth/") or path in {
        "/login",
        "/health",
        "/sitemap.xml",
        "/robots.txt",
        "/signed-out",
        "/session-expired",
        "/terms",
        "/privacy",
        "/grievance",
    }:
        return False
    if any(path == p or path.startswith(p + "/") for p in AUTH_REQUIRED_PREFIXES):
        return True
    if path.startswith("/browse/") and path.endswith("/gloss") and m in {
        "PUT",
        "DELETE",
        "POST",
    }:
        return True
    if path == "/reset" and m == "POST":
        return True
    if path.startswith("/learn/") and m == "POST":
        # /quiz only grades server-side; nothing persists for guests, and
        # guests need the graded result to complete the Test gate locally.
        # /speech/transcribe is the same for spoken Letters (and returns
        # 403 mode_locked for Recite so it cannot proxy Deepgram).
        if path.endswith("/quiz") or path.endswith("/speech/transcribe"):
            return False
        return True
    if path.startswith("/memory") and m == "POST":
        return True
    if path == "/welcome" and m == "POST":
        return True
    if path.startswith("/profile") and m == "POST":
        return True
    return False


def signin_redirect(
    *,
    next_url: str = "/",
    reason: str = "default",
    error: str | None = None,
) -> RedirectResponse:
    params = {"next": next_url, "reason": reason}
    if error:
        params["error"] = error
    return RedirectResponse(url=f"/login?{urlencode(params)}", status_code=303)
