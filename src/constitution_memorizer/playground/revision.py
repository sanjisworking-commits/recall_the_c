"""Playground revision ladder — same ideology as Constitution, own records."""

from __future__ import annotations

from datetime import date, timedelta

INTERVAL_LADDER: tuple[int, ...] = (1, 3, 7, 15, 30, 60)


def advance_interval(current_interval_days: int) -> int | None:
    if current_interval_days <= 0:
        return INTERVAL_LADDER[0]
    if current_interval_days in INTERVAL_LADDER:
        index = INTERVAL_LADDER.index(current_interval_days)
        if index + 1 >= len(INTERVAL_LADDER):
            return None
        return INTERVAL_LADDER[index + 1]
    for rung in INTERVAL_LADDER:
        if rung > current_interval_days:
            return rung
    return None


def next_revision_date(as_of: date, interval_days: int) -> date:
    return as_of + timedelta(days=interval_days)
