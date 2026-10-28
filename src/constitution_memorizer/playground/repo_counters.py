"""Request-local Playground repo counters. Method boundaries only; no SQL."""

from __future__ import annotations

from collections.abc import Callable
from contextvars import ContextVar
from functools import wraps
from typing import Literal, TypeVar

_repo_counter_depth: ContextVar[int] = ContextVar(
    "playground_repo_counter_depth", default=0
)

Kind = Literal["read", "write"]
Domain = Literal[
    "roster",
    "summary",
    "progress",
    "revision",
    "source_review",
]

_DOMAIN_COUNTERS: dict[str, str] = {
    "roster": "playground_roster_reads",
    "summary": "playground_summary_reads",
    "progress": "playground_progress_reads",
    "revision": "playground_revision_reads",
    "source_review": "playground_source_review_reads",
}

F = TypeVar("F", bound=Callable)


def count_playground_repo_call(
    *, kind: Kind, domain: Domain | None = None
) -> Callable[[F], F]:
    """Count one outermost public repo call. Nested public calls are silent."""

    kind_counter = (
        "playground_db_reads" if kind == "read" else "playground_db_writes"
    )
    domain_counter = _DOMAIN_COUNTERS.get(domain) if kind == "read" else None

    def decorator(fn: F) -> F:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            outermost = _repo_counter_depth.get() == 0
            token = _repo_counter_depth.set(_repo_counter_depth.get() + 1)
            try:
                if outermost:
                    _increment(kind_counter, domain_counter)
                return fn(*args, **kwargs)
            finally:
                _repo_counter_depth.reset(token)

        return wrapper  # type: ignore[return-value]

    return decorator


def _increment(kind_counter: str, domain_counter: str | None) -> None:
    from constitution_memorizer.web.request_context import (  # noqa: PLC0415
        record_request_counter,
    )

    record_request_counter("playground_repo_round_trips")
    record_request_counter(kind_counter)
    if domain_counter is not None:
        record_request_counter(domain_counter)
