"""Phase 1: measure real PostgreSQL round-trip latency from this process.

The production timing logs show a strikingly stable ~230 ms per independent
DB operation across unrelated queries, which points at cross-region network
RTT rather than expensive SQL. This module measures the primitive using the
*existing* pool so the number reflects the real deployment, and reports the
Railway / database regions from the environment.

It never logs or returns credentials: only the database host name (no user,
password, port query string) is surfaced, purely as a region hint.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from time import perf_counter
from typing import Any
from urllib.parse import urlsplit


@dataclass(frozen=True)
class DbRttReport:
    available: bool
    reason: str | None
    acquire_ms: float | None
    first_query_ms: float | None
    samples: int
    p50_ms: float | None
    p95_ms: float | None
    min_ms: float | None
    max_ms: float | None
    railway_region: str | None
    database_region: str | None
    database_host: str | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _percentile(values: list[float], pct: float) -> float | None:
    """Linear-interpolation percentile of an already-sorted list."""
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    k = (len(values) - 1) * pct
    lo = int(k)
    hi = min(lo + 1, len(values) - 1)
    if lo == hi:
        return values[lo]
    return values[lo] + (values[hi] - values[lo]) * (k - lo)


def _database_host() -> str | None:
    """Host name from DATABASE_URL, with no credentials attached."""
    dsn = os.environ.get("DATABASE_URL") or ""
    if not dsn:
        return None
    try:
        return urlsplit(dsn).hostname
    except ValueError:
        return None


def region_info() -> tuple[str | None, str | None, str | None]:
    """(railway_region, database_region, database_host) from the environment."""
    railway = (
        os.environ.get("RAILWAY_REPLICA_REGION")
        or os.environ.get("RAILWAY_REGION")
        or None
    )
    database = (
        os.environ.get("DATABASE_REGION")
        or os.environ.get("SUPABASE_REGION")
        or None
    )
    return railway, database, _database_host()


def measure_db_rtt(pool: Any, *, samples: int = 20) -> DbRttReport:
    """Time connection acquisition and ``SELECT 1`` round trips on ``pool``.

    Uses one borrowed connection and runs ``samples`` *sequential* ``SELECT 1``
    calls so each is its own round trip — exactly the primitive that dominates
    the authenticated request cost when app and DB are far apart.
    """
    railway, database, host = region_info()
    if pool is None:
        return DbRttReport(
            available=False,
            reason="no_pool (SQLite / single-user mode)",
            acquire_ms=None,
            first_query_ms=None,
            samples=0,
            p50_ms=None,
            p95_ms=None,
            min_ms=None,
            max_ms=None,
            railway_region=railway,
            database_region=database,
            database_host=host,
        )

    acquire_start = perf_counter()
    with pool.connection() as conn:
        acquire_ms = (perf_counter() - acquire_start) * 1000.0

        first_start = perf_counter()
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        first_query_ms = (perf_counter() - first_start) * 1000.0

        durations: list[float] = []
        for _ in range(max(1, samples)):
            started = perf_counter()
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
            durations.append((perf_counter() - started) * 1000.0)

    durations.sort()
    return DbRttReport(
        available=True,
        reason=None,
        acquire_ms=acquire_ms,
        first_query_ms=first_query_ms,
        samples=len(durations),
        p50_ms=_percentile(durations, 0.50),
        p95_ms=_percentile(durations, 0.95),
        min_ms=durations[0],
        max_ms=durations[-1],
        railway_region=railway,
        database_region=database,
        database_host=host,
    )
