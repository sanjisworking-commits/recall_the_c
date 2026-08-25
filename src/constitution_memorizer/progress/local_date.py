"""User-local calendar date for schedule and study-session anchoring."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from constitution_memorizer.progress.scheduler import ReminderEngine

USER_TIMEZONE_KEY = "user_timezone"


def user_today(engine: ReminderEngine, *, fallback: date | None = None) -> date:
    """The user's local calendar date.

    With a stored IANA ``user_timezone`` the revision ladder and study sessions
    anchor on the user's today, not the server's. Unset/invalid → ``fallback``
    or ``date.today()``.
    """
    tz_name = ""
    try:
        tz_name = engine.get_setting(USER_TIMEZONE_KEY) or ""
    except Exception:  # noqa: BLE001 — anchoring must never break Done
        pass
    if tz_name:
        try:
            return datetime.now(ZoneInfo(tz_name)).date()
        except (KeyError, ValueError):
            pass
    return fallback or date.today()
