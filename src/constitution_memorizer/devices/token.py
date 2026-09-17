"""Installation token minting and HMAC-SHA256 storage helpers.

The raw ``rtc_device`` cookie value is a cryptographically random secret.
The server persists only HMAC(server_secret, token). Stolen DB hashes are
not reusable offline without the server key.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Any

from starlette.responses import Response

DEVICE_COOKIE_NAME = "rtc_device"
# Technical cookie retention for an installation credential.
# Independent of any product replacement-churn window.
DEVICE_COOKIE_MAX_AGE_SECONDS = 400 * 24 * 60 * 60
DEVICE_TOKEN_BYTES = 32

# Used only when APP_ENV=test and PLAYGROUND_DEVICE_HMAC_SECRET is empty.
# Never a production fallback.
TEST_DEVICE_HMAC_SECRET = "test-playground-device-hmac-secret"


class DeviceHmacConfigError(Exception):
    """HMAC secret missing or unusable. Never includes the secret or token."""

    def __init__(self, message: str = "Playground device HMAC secret is not configured") -> None:
        super().__init__(message)


def mint_installation_token() -> str:
    """Cryptographically random installation credential. Not a session id."""

    return secrets.token_urlsafe(DEVICE_TOKEN_BYTES)


def hash_device_token(secret: str, token: str) -> str:
    """Return lowercase hex HMAC-SHA256. Never logs ``token`` or ``secret``."""

    if not (secret or "").strip():
        raise DeviceHmacConfigError()
    if not token:
        raise DeviceHmacConfigError("Playground device token is missing")
    digest = hmac.new(
        secret.encode("utf-8"),
        token.encode("utf-8"),
        hashlib.sha256,
    )
    return digest.hexdigest()


def resolve_hmac_secret(settings: Any) -> str:
    """Configured secret, or the test-only default. Empty in production if unset."""

    configured = str(getattr(settings, "playground_device_hmac_secret", "") or "").strip()
    if configured:
        return configured
    app_env = str(getattr(settings, "app_env", "") or "")
    if app_env == "test":
        return TEST_DEVICE_HMAC_SECRET
    return ""


def apply_device_cookie(response: Response, token: str, *, secure: bool) -> None:
    """Set persistent ``rtc_device``. Caller must not log ``token``."""

    response.set_cookie(
        DEVICE_COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        secure=bool(secure),
        max_age=DEVICE_COOKIE_MAX_AGE_SECONDS,
        path="/",
    )


def request_device_token(request: Any) -> str | None:
    """Prefer a token minted on this request, else the incoming cookie."""

    state = getattr(request, "state", None)
    minted = getattr(state, "device_token", None) if state is not None else None
    if minted:
        return str(minted)
    cookies = getattr(request, "cookies", None)
    if cookies is None:
        return None
    raw = cookies.get(DEVICE_COOKIE_NAME)
    return str(raw) if raw else None


def ensure_request_device_token(request: Any) -> bool:
    """Mint ``rtc_device`` when authenticated and the cookie is absent.

    Returns True when a new token was generated and must be set on the response.
    """

    existing = request_device_token(request)
    if existing:
        request.state.device_token = existing
        request.state.device_cookie_fresh = False
        return False
    token = mint_installation_token()
    request.state.device_token = token
    request.state.device_cookie_fresh = True
    return True


def maybe_set_device_cookie(request: Any, response: Response) -> None:
    if not getattr(getattr(request, "state", None), "device_cookie_fresh", False):
        return
    token = getattr(request.state, "device_token", None)
    if not token:
        return
    settings = getattr(getattr(request, "app", None), "state", None)
    multi = getattr(settings, "multiuser_settings", None) if settings is not None else None
    secure = bool(getattr(multi, "cookie_secure", False))
    apply_device_cookie(response, str(token), secure=secure)


def display_name_from_user_agent(user_agent: str | None) -> str:
    """Conservative label. Parsing failure is not an authorization input."""

    if not user_agent:
        return "Web browser"
    try:
        ua = user_agent.lower()
        browser = "Web browser"
        if "edg/" in ua or "edge/" in ua:
            browser = "Edge"
        elif "opr/" in ua or "opera" in ua:
            browser = "Opera"
        elif "chrome/" in ua and "chromium" not in ua:
            browser = "Chrome"
        elif "firefox/" in ua or "fxios" in ua:
            browser = "Firefox"
        elif "safari/" in ua:
            browser = "Safari"
        os_name = None
        if "iphone" in ua:
            os_name = "iPhone"
        elif "ipad" in ua:
            os_name = "iPad"
        elif "android" in ua:
            os_name = "Android"
        elif "mac os" in ua or "macintosh" in ua:
            os_name = "macOS"
        elif "windows" in ua:
            os_name = "Windows"
        elif "cros" in ua:
            os_name = "Chrome OS"
        elif "linux" in ua:
            os_name = "Linux"
        if browser != "Web browser" and os_name:
            return f"{browser} on {os_name}"
        if os_name:
            return f"Web browser on {os_name}"
        return browser
    except Exception:
        return "Web browser"
