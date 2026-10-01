"""Playground-scoped HTML error surfaces. Do not register global handlers.

D140 restyles kill-switch 404 and repo/roster 503 as Playground-unavailable.
D142 is atomic: HTML 404, 403, and 500 for ``/playground*`` only. Other
application paths keep Starlette/FastAPI defaults.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.responses import Response

from constitution_memorizer.web.completion import wants_json

PLAYGROUND_PREFIX = "/playground"

_COPY = {
    403: (
        "You can’t do that in Playground",
        "This Playground action isn’t allowed on this account or device.",
    ),
    404: (
        "This Playground page was not found",
        "The Playground address may be wrong, or this law isn’t available here.",
    ),
    500: (
        "Playground hit a problem",
        "Something went wrong while loading Playground. Constitution Learn is separate and still available.",
    ),
    503: (
        "Playground is unavailable",
        "Playground can’t load right now. Constitution Learn and public Bare Acts stay available.",
    ),
}

_UNAVAILABLE = (
    "Playground is unavailable",
    "Playground is turned off on this installation. Constitution Learn and public Bare Acts stay available.",
)


def is_playground_path(path: str) -> bool:
    return path == PLAYGROUND_PREFIX or path.startswith(PLAYGROUND_PREFIX + "/")


def playground_wants_json(request: Request, json_mode: bool = False) -> bool:
    if json_mode:
        return True
    return wants_json(request)


def _error_html(
    *,
    status: int,
    title: str,
    body: str,
    reason: str,
    hard_gate: bool = True,
) -> str:
    gate_flag = "true" if hard_gate else "false"
    return (
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<meta name='robots' content='noindex, nofollow'>"
        f"<title>{title} · Playground</title>"
        "<link rel='stylesheet' href='/static/playground.css?v=pg10'>"
        "</head><body data-mscreen='playground' class='playground-app'>"
        f"<div class='PlaygroundShell' data-hard-gate='{gate_flag}' "
        f"data-playground-error='{status}' data-playground-gate='{reason}'>"
        "<section class='EntitlementGate pg-error'>"
        "<p class='pg-eyebrow'>Playground</p>"
        f"<h1>{title}</h1>"
        f"<p class='pg-lede'>{body}</p>"
        "<p class='pg-actions'>"
        "<a class='pg-btn' href='/dashboard'>Back to Constitution</a>"
        "</p></section></div></body></html>"
    )


def playground_error_response(
    request: Request,
    status: int,
    *,
    unavailable: bool = False,
    json_mode: bool = False,
) -> Response:
    """Playground-only error page. JSON clients keep a structured payload."""

    if playground_wants_json(request, json_mode):
        error = "playground_unavailable" if unavailable or status == 503 else f"http_{status}"
        return JSONResponse({"ok": False, "error": error}, status_code=status)
    if unavailable or status == 503:
        title, body = _UNAVAILABLE if unavailable else _COPY[503]
        reason = "unavailable"
        code = 404 if unavailable else 503
        html = _error_html(status=code, title=title, body=body, reason=reason)
        response = HTMLResponse(html, status_code=code)
        response.headers["x-playground-error"] = reason
        return response
    title, body = _COPY.get(status, _COPY[500])
    reason = {403: "forbidden", 404: "not_found", 500: "server_error"}.get(
        status, "error"
    )
    html = _error_html(status=status, title=title, body=body, reason=reason)
    response = HTMLResponse(html, status_code=status)
    response.headers["x-playground-error"] = reason
    return response


def _body_bytes(response: Response) -> bytes:
    body = getattr(response, "body", None)
    if isinstance(body, (bytes, bytearray)):
        return bytes(body)
    return b""


def _keep_playground_json_api(response: Response) -> bool:
    """Leave structured Playground JSON (``ok`` / ``error``) untouched."""

    body = _body_bytes(response)
    return b'"ok"' in body and b'"error"' in body


async def playground_error_middleware(request: Request, call_next):
    """Restyle default 404/403/500 on Playground paths only.

    Does not replace application-wide exception handlers. Non-Playground
    routes pass through unchanged. ``{ok, error}`` JSON stays JSON.
    """

    path = request.url.path
    if not is_playground_path(path):
        return await call_next(request)
    try:
        response = await call_next(request)
    except Exception:
        if playground_wants_json(request):
            raise
        return playground_error_response(request, 500)
    if response.headers.get("x-playground-error"):
        return response
    status = response.status_code
    if status not in {403, 404, 500, 503}:
        return response
    if playground_wants_json(request):
        return response
    if _keep_playground_json_api(response):
        return response
    ctype = (response.headers.get("content-type") or "").lower()
    if "text/html" in ctype and status != 500:
        # Already-rendered gates and pages. Short kill-switch HTML is handled
        # in the feature-flag middleware before this runs.
        return response
    if status in {403, 404, 500, 503}:
        return playground_error_response(
            request, status, unavailable=status == 503
        )
    return response
