"""Exception-safe Playground stage timing. No route or collector of its own."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from time import perf_counter


@contextmanager
def time_playground_stage(stage: str) -> Iterator[None]:
    """Time one named stage. No-op without a collector. Exceptions propagate."""

    from constitution_memorizer.web.request_context import (  # noqa: PLC0415
        record_request_timing,
    )

    started = perf_counter()
    try:
        yield
    finally:
        record_request_timing(stage, started)
