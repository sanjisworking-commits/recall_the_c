"""Bearer-token authentication for native API clients (e.g. Android).

The native app signs in with Supabase directly and sends the resulting
Supabase access JWT as ``Authorization: Bearer <token>`` on each API request.
This module extracts and verifies that token against the SAME provider the
browser flow already uses (``auth_provider.verify_access_token`` →
``GET /auth/v1/user``), so a bearer-authenticated request maps to the exact
same ``AuthenticatedUser`` (keyed by the Supabase user UUID) as the cookie
session. No second token is minted; RecallC stays stateless for API requests.

A short positive cache mirrors the 30s window ``PostgresSessionStore`` already
accepts for cookie sessions: it avoids a Supabase round trip (and blocking the
event loop from the auth middleware) on every request, at the cost of honouring
a revoked token for up to ``_CACHE_TTL_SECONDS``. Verification failures are
never cached, so invalid/expired tokens always fail fast.
"""

from __future__ import annotations

import hashlib
import logging
import time

from fastapi import Request

from constitution_memorizer.auth.models import AuthenticatedUser

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 30.0

# token sha256 -> (expiry_monotonic, user)
_verified_cache: dict[str, tuple[float, AuthenticatedUser]] = {}


def clear_bearer_cache() -> None:
    """Drop all cached verifications (used by tests for isolation)."""
    _verified_cache.clear()


def extract_bearer_token(request: Request) -> str | None:
    """Return the raw token from an ``Authorization: Bearer <token>`` header.

    Returns None for a missing header, a non-Bearer scheme, or an empty token.
    Case-insensitive on the scheme; tolerant of surrounding whitespace.
    """
    header = request.headers.get("Authorization")
    if not header:
        return None
    scheme, _, value = header.partition(" ")
    if scheme.strip().lower() != "bearer":
        return None
    token = value.strip()
    return token or None


def resolve_bearer_user(request: Request) -> AuthenticatedUser | None:
    """Verify the request's bearer token and return its RecallC user, or None.

    Never raises: any verification failure (invalid/expired token, provider
    error, transient network fault) resolves to None so the caller treats the
    request as unauthenticated and fails cleanly.
    """
    token = extract_bearer_token(request)
    if not token:
        return None
    provider = getattr(request.app.state, "auth_provider", None)
    if provider is None:
        return None

    key = hashlib.sha256(token.encode("utf-8")).hexdigest()
    now = time.monotonic()
    cached = _verified_cache.get(key)
    if cached is not None and cached[0] > now:
        return cached[1]
    if cached is not None:
        _verified_cache.pop(key, None)

    try:
        user = provider.verify_access_token(token)
    except Exception:  # noqa: BLE001 — any failure means "not authenticated"
        logger.info("Bearer token verification rejected")
        return None

    _verified_cache[key] = (now + _CACHE_TTL_SECONDS, user)
    return user
