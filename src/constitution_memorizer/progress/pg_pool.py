"""Shared application-level PostgreSQL connection pool (hosted only)."""

from __future__ import annotations

import logging
from urllib.parse import urlsplit, urlunsplit

from psycopg_pool import ConnectionPool

logger = logging.getLogger(__name__)

# min_size=0: open() must not wait for a live connection. Railway only stops the
# old replica after the new one is healthy; requiring a session-mode slot at
# boot deadlocks the deploy when the pooler is already at cap.
POOL_MIN_SIZE = 0
POOL_MAX_SIZE = 5
POOL_OPEN_TIMEOUT_SECONDS = 15.0

_SUPABASE_POOLER_MARKER = "pooler.supabase.com"
_TRANSACTION_PORT = 6543
_SESSION_PORT = 5432


def normalize_pool_dsn(dsn: str) -> str:
    """Point Supabase session-mode pooler URLs at transaction mode.

    ``*.pooler.supabase.com:5432`` is session mode, capped at the project's
    ``pool_size`` (15 on the current project). Transaction mode (port 6543)
    is the pooler meant for app servers.
    """
    parts = urlsplit(dsn)
    host = (parts.hostname or "").lower()
    if _SUPABASE_POOLER_MARKER not in host:
        return dsn
    if parts.port == _TRANSACTION_PORT:
        return dsn
    if parts.port not in (None, _SESSION_PORT):
        return dsn
    userinfo, _, _hostport = parts.netloc.rpartition("@")
    hostname = parts.hostname or ""
    new_hostport = f"{hostname}:{_TRANSACTION_PORT}"
    new_netloc = f"{userinfo}@{new_hostport}" if userinfo else new_hostport
    return urlunsplit((parts.scheme, new_netloc, parts.path, parts.query, parts.fragment))


def is_supabase_pooler(dsn: str) -> bool:
    host = (urlsplit(dsn).hostname or "").lower()
    return _SUPABASE_POOLER_MARKER in host


def connection_kwargs(dsn: str) -> dict[str, object]:
    """psycopg connect kwargs. Transaction-mode poolers cannot use prepared statements."""
    if is_supabase_pooler(dsn):
        return {"prepare_threshold": 0}
    return {}


def make_connection_pool(dsn: str) -> ConnectionPool:
    """Build a closed pool with default (tuple) row factory.

    Callers must ``open(wait=True)`` during app startup and ``close()`` on shutdown.
    Do not set ``row_factory`` on the pool or on borrowed connections.
    """
    normalized = normalize_pool_dsn(dsn)
    before = urlsplit(dsn)
    after = urlsplit(normalized)
    if before.port != after.port:
        logger.info(
            "Rewriting Supabase session pooler %s:%s → transaction mode :%s",
            after.hostname,
            before.port or _SESSION_PORT,
            after.port,
        )
    return ConnectionPool(
        conninfo=normalized,
        min_size=POOL_MIN_SIZE,
        max_size=POOL_MAX_SIZE,
        open=False,
        kwargs=connection_kwargs(normalized) or None,
    )
