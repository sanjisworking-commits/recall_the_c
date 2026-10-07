"""Idempotent reconciliation between the projection and Google Calendar.

expected + missing   → create event, store mapping
expected + changed   → patch event (payload hash mismatch)
mapped + not expected → delete event + mapping (zero-work dates lose their
                        event — an empty projection is never treated as
                        completion evidence)
unchanged            → no API call

Running twice produces the same result. All Google failures are contained
here: they mark the connection errored (sync_pending stays set → retryable)
and never propagate into request handlers or revision state.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from constitution_memorizer.calendar_sync.google_client import (
    GoogleApiError,
    GoogleAuthRevoked,
    GoogleCalendarClient,
)
from constitution_memorizer.calendar_sync.projection import (
    DayProjection,
    build_event_content,
    build_projection,
    reminder_minutes_for,
)
from constitution_memorizer.calendar_sync.store import CalendarStore, EventMapping

logger = logging.getLogger(__name__)

DEFAULT_REVISION_TIME = "20:00"
DEFAULT_SESSION_MINUTES = 30
VALID_SESSION_MINUTES = (15, 30, 45, 60)

# One sync at a time per user WITHIN THIS PROCESS. Across processes there is
# no coordination: two replicas could both see a date unmapped and both insert
# an event. v1 therefore assumes a single calendar-syncing web replica (the
# current Railway deployment) — documented in docs/google-calendar.md; a
# DB-level claim would be needed before scaling out.
_user_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


def _engine_setting(engine, key: str) -> str | None:
    getter = getattr(engine, "get_setting", None)
    if getter is not None:
        return getter(key)
    repo = getattr(engine, "repo", None)
    uid = getattr(engine, "user_id", None)
    if repo is None:
        return None
    return repo.get_setting(uid, key)


def calendar_prefs(engine) -> dict:
    """Read the user's calendar preferences with defaults."""
    from constitution_memorizer.calendar_sync.projection import (
        DEFAULT_REMINDER_CADENCE,
        VALID_REMINDER_CADENCES,
    )

    tz = _engine_setting(engine, "user_timezone") or ""
    time_pref = _engine_setting(engine, "gcal_revision_time") or DEFAULT_REVISION_TIME
    try:
        minutes = int(_engine_setting(engine, "gcal_session_minutes") or "")
    except ValueError:
        minutes = DEFAULT_SESSION_MINUTES
    if minutes not in VALID_SESSION_MINUTES:
        minutes = DEFAULT_SESSION_MINUTES
    cadence_raw = _engine_setting(engine, "gcal_reminder_cadence") or ""
    cadence = (
        cadence_raw if cadence_raw in VALID_REMINDER_CADENCES
        else DEFAULT_REMINDER_CADENCE
    )
    return {
        "timezone": tz,
        "revision_time": time_pref,
        "session_minutes": minutes,
        "reminder_cadence": cadence,
        # Popup visibility: absent = never explicitly chosen (dismiss keeps
        # the once default without marking it chosen).
        "cadence_chosen": bool(cadence_raw),
    }


def user_local_today(engine) -> date:
    """The user's local calendar date (falls back to server-local today)."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    tz_name = _engine_setting(engine, "user_timezone") or ""
    if tz_name:
        try:
            return datetime.now(ZoneInfo(tz_name)).date()
        except (KeyError, ValueError):
            pass
    return date.today()


@dataclass(frozen=True)
class ReconciliationSnapshot:
    """Synchronous read/prepare result; contains no Google HTTP."""

    prefs: dict
    anchor: date
    projection: dict[date, DayProjection]
    mappings: list[EventMapping]


def _prepare_reconciliation(engine, store, today, extra_loader=None) -> ReconciliationSnapshot:
    prefs = calendar_prefs(engine)
    anchor = today or user_local_today(engine)
    extra = {}
    if extra_loader is not None:
        try:
            extra = extra_loader(engine, anchor) or {}
        except Exception:  # noqa: BLE001 — T31: Playground must not fail Constitution
            logger.exception("playground calendar extra failed; Constitution sync continues")
            extra = {}
    projection = build_projection(engine, today=anchor, extra=extra)
    mappings = store.list_event_mappings(engine.user_id)
    return ReconciliationSnapshot(
        prefs=prefs,
        anchor=anchor,
        projection=projection,
        mappings=mappings,
    )


async def reconcile_user_calendar(
    *,
    engine,
    store: CalendarStore,
    client: GoogleCalendarClient,
    calendar_id: str,
    dashboard_url: str,
    today: date | None = None,
    extra_loader: Callable | None = None,
) -> dict[str, int]:
    """Run one full bounded reconciliation. Returns per-op counts."""
    if extra_loader is None:
        snapshot = await asyncio.to_thread(
            _prepare_reconciliation, engine, store, today
        )
    else:
        snapshot = await asyncio.to_thread(
            _prepare_reconciliation, engine, store, today, extra_loader
        )
    prefs = snapshot.prefs
    tz = prefs["timezone"] or "UTC"
    reminders = reminder_minutes_for(
        prefs["reminder_cadence"], prefs["revision_time"]
    )
    expected: dict[date, tuple[str, dict]] = {}
    for local_date, day in snapshot.projection.items():
        content = build_event_content(
            day,
            revision_time=prefs["revision_time"],
            session_minutes=prefs["session_minutes"],
            timezone=tz,
            dashboard_url=dashboard_url,
            reminder_minutes=reminders,
        )
        expected[local_date] = (content.payload_hash(), content.__dict__)

    mapped = {m.local_date: m for m in snapshot.mappings}
    counts = {"created": 0, "patched": 0, "deleted": 0, "unchanged": 0}

    for local_date, (content_hash, content) in sorted(expected.items()):
        event_kwargs = {
            "title": content["title"],
            "description": content["description"],
            "local_date": local_date,
            "start_time": content["start_time"],
            "duration_minutes": content["duration_minutes"],
            "timezone_id": content["timezone"],
            "reminder_minutes": tuple(content["reminder_minutes"]),
        }
        mapping = mapped.get(local_date)
        if mapping is None:
            event_id = await client.insert_event(calendar_id, **event_kwargs)
            await asyncio.to_thread(
                store.upsert_event_mapping,
                engine.user_id,
                local_date=local_date,
                google_event_id=event_id,
                content_hash=content_hash,
            )
            counts["created"] += 1
        elif mapping.content_hash != content_hash:
            patched = await client.patch_event(
                calendar_id, mapping.google_event_id, **event_kwargs
            )
            if patched is None:
                # Event vanished on Google's side — recreate it.
                event_id = await client.insert_event(calendar_id, **event_kwargs)
            else:
                event_id = patched
            await asyncio.to_thread(
                store.upsert_event_mapping,
                engine.user_id,
                local_date=local_date,
                google_event_id=event_id,
                content_hash=content_hash,
            )
            counts["patched"] += 1
        else:
            counts["unchanged"] += 1

    for local_date, mapping in mapped.items():
        if local_date not in expected:
            await client.delete_event(calendar_id, mapping.google_event_id)
            await asyncio.to_thread(
                store.delete_event_mapping, engine.user_id, local_date
            )
            counts["deleted"] += 1

    return counts


async def sync_user_calendar(
    *,
    user_id: UUID | str,
    engine,
    store: CalendarStore,
    client_factory,
    dashboard_url: str,
    extra_loader: Callable | None = None,
) -> bool:
    """Locked, error-contained sync driver used by every trigger.

    ``client_factory(connection) -> GoogleCalendarClient | None`` unseals the
    token; returning None means the feature is unconfigured. Success clears
    sync_pending; any failure records the error and leaves it set.
    """
    uid = str(user_id)
    async with _user_locks[uid]:
        connection = await asyncio.to_thread(store.get_connection, uid)
        if connection is None or not connection.is_active:
            return False
        if not connection.google_calendar_id:
            await asyncio.to_thread(
                store.mark_sync_result, uid, ok=False, error="missing calendar id"
            )
            return False
        client = client_factory(connection)
        if client is None:
            return False
        try:
            await reconcile_user_calendar(
                engine=engine,
                store=store,
                client=client,
                calendar_id=connection.google_calendar_id,
                dashboard_url=dashboard_url,
                extra_loader=extra_loader,
            )
        except GoogleAuthRevoked:
            await asyncio.to_thread(
                store.mark_sync_result, uid, ok=False, error="authorization revoked"
            )
            return False
        except GoogleApiError as exc:
            await asyncio.to_thread(
                store.mark_sync_result,
                uid,
                ok=False,
                error=f"google api {exc.status_code or 'error'}",
            )
            return False
        except Exception:  # noqa: BLE001 — sync must never crash callers
            logger.exception("Calendar sync failed for user %s", uid)
            await asyncio.to_thread(
                store.mark_sync_result, uid, ok=False, error="internal error"
            )
            return False
        await asyncio.to_thread(store.mark_sync_result, uid, ok=True)
        return True
