"""Playground month clock. Asia/Kolkata calendar dates; ``period_end`` exclusive.

Not UTC calendar months, not Razorpay billing months, not the browser timezone.
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from constitution_memorizer.playground.roster.models import PLAYGROUND_TIMEZONE_NAME

PLAYGROUND_TZ = ZoneInfo(PLAYGROUND_TIMEZONE_NAME)


def _as_utc(now: datetime | None) -> datetime:
    clock = now or datetime.now(timezone.utc)
    if clock.tzinfo is None:
        return clock.replace(tzinfo=timezone.utc)
    return clock


def playground_local_datetime(now: datetime | None = None) -> datetime:
    return _as_utc(now).astimezone(PLAYGROUND_TZ)


def playground_today(now: datetime | None = None) -> date:
    return playground_local_datetime(now).date()


def shift_playground_month(month_start: date, delta: int) -> date:
    """Move a first-of-month date by ``delta`` calendar months.

    Not a 30-day offset. January minus one month is 1 December of the
    previous year. December plus one month is 1 January of the next year.
    """

    index = month_start.year * 12 + (month_start.month - 1) + delta
    year, month_index = divmod(index, 12)
    return date(year, month_index + 1, 1)


def previous_playground_month_bounds(
    now: datetime | None = None,
) -> tuple[date, date]:
    """Immediately previous Asia/Kolkata month. ``period_end`` is exclusive."""

    start, _end = playground_month_bounds(now)
    previous = shift_playground_month(start, -1)
    return previous, start


def next_playground_month_bounds(now: datetime | None = None) -> tuple[date, date]:
    """Immediately following Asia/Kolkata month. ``period_end`` is exclusive."""

    _start, end = playground_month_bounds(now)
    return end, shift_playground_month(end, 1)


def playground_month_bounds(now: datetime | None = None) -> tuple[date, date]:
    """Return ``(period_start, period_end)`` for the current Asia/Kolkata month.

    ``period_start`` is the first local calendar day of the month.
    ``period_end`` is the first local calendar day of the following month
    and is **exclusive**. Instant ``2026-09-30 18:29 UTC`` is still September;
    ``2026-09-30 18:30 UTC`` is October.
    """

    local = playground_local_datetime(now)
    start = date(local.year, local.month, 1)
    if local.month == 12:
        end = date(local.year + 1, 1, 1)
    else:
        end = date(local.year, local.month + 1, 1)
    return start, end


def playground_month_name(period_start: date) -> str:
    """English calendar month for confirmation copy. Derived from the local date."""

    return calendar.month_name[period_start.month]


def date_in_period(day: date, period_start: date, period_end: date) -> bool:
    """Inclusive start, exclusive end."""

    return period_start <= day < period_end
