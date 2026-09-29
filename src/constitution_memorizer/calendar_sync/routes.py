"""Google Calendar connect / callback / disconnect / retry + preference POST.

Every route is user-scoped and 404s while the feature is unconfigured.
OAuth CSRF uses the same state-cookie shape as the sign-in flow but a
DIFFERENT cookie (rtc_gcal_state) and a DEDICATED OAuth client — Calendar
revocation must never be able to touch Google sign-in.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
from contextvars import Context
from time import perf_counter
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from constitution_memorizer.auth.sessions import CSRF_COOKIE_NAME
from constitution_memorizer.calendar_sync.crypto import TokenSealer, TokenSealError
from constitution_memorizer.calendar_sync.google_client import (
    GoogleApiError,
    GoogleCalendarClient,
    exchange_code,
    revoke_token,
)
from constitution_memorizer.calendar_sync.projection import VALID_REMINDER_CADENCES
from constitution_memorizer.calendar_sync.store import SYNC_PENDING
from constitution_memorizer.calendar_sync.sync import (
    VALID_SESSION_MINUTES,
    sync_user_calendar,
)

logger = logging.getLogger(__name__)

GCAL_STATE_COOKIE = "rtc_gcal_state"
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GCAL_SCOPE = "https://www.googleapis.com/auth/calendar.app.created"

router = APIRouter()


def _record_timing(stage: str, started: float) -> None:
    from constitution_memorizer.web.request_context import record_request_timing

    record_request_timing(stage, started)


def _gcal_enabled(request: Request) -> bool:
    settings = getattr(request.app.state, "multiuser_settings", None)
    return bool(
        getattr(request.app.state, "multiuser_enabled", False)
        and settings is not None
        and settings.gcal_configured
        and getattr(request.app.state, "calendar_store", None) is not None
    )


def _current_user(request: Request):
    return getattr(request.state, "current_user", None)


def _not_found() -> RedirectResponse:
    return RedirectResponse(url="/settings", status_code=303)


def _redirect_uri(settings) -> str:
    return f"{settings.app_base_url.rstrip('/')}/calendar/google/callback"


def _dashboard_url(settings) -> str:
    return f"{settings.app_base_url.rstrip('/')}/dashboard"


def make_client_factory(request: Request):
    """connection -> GoogleCalendarClient | None (unseals the stored token)."""
    settings = request.app.state.multiuser_settings
    sealer = TokenSealer(settings.gcal_token_key)
    transport = getattr(request.app.state, "gcal_transport", None)

    def factory(connection) -> GoogleCalendarClient | None:
        if not connection.refresh_token_sealed:
            return None
        try:
            token = sealer.unseal(connection.refresh_token_sealed)
        except TokenSealError:
            logger.error("Stored Google token could not be unsealed (rotated key?)")
            return None
        return GoogleCalendarClient(
            client_id=settings.gcal_client_id,
            client_secret=settings.gcal_client_secret,
            refresh_token=token,
            transport=transport,
        )

    return factory


def schedule_sync(request: Request, user_id) -> None:
    """Durably flag then fire an async reconciliation (never awaited).

    Safe to call from any state-changing handler: no-ops without an active
    connection, and every failure mode leaves sync_pending set for retry.
    """
    if not _gcal_enabled(request):
        return
    store = request.app.state.calendar_store
    started = perf_counter()
    try:
        # One atomic round trip: flag sync_pending only when an active
        # connection exists, and tell us whether it did. This replaces the
        # get_connection + mark_sync_pending pair (~460 ms of sequential RTT in
        # production) while preserving the durable pending guarantee and the
        # "no active connection → no task" behavior.
        active = store.mark_sync_pending_if_active(user_id)
    except Exception:  # noqa: BLE001 — never break the request path
        logger.exception("calendar sync flagging failed")
        return
    finally:
        _record_timing("calendar_sync_schedule", started)
    if not active:
        return
    engine = request.app.state.engine.for_user(user_id)
    settings = request.app.state.multiuser_settings
    factory = make_client_factory(request)

    async def _run() -> None:
        await sync_user_calendar(
            user_id=user_id,
            engine=engine,
            store=store,
            client_factory=factory,
            dashboard_url=_dashboard_url(settings),
        )

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:  # no running loop (sync test contexts)
        # Fresh Context so asyncio.run does not inherit the HTTP timing collector.
        Context().run(asyncio.run, _run())
        return
    # Hold a strong reference — a bare create_task can be garbage-collected
    # mid-flight, silently dropping the sync. Launch in a fresh Context so
    # the background reconciliation cannot record into this request's timings.
    tasks = getattr(request.app.state, "gcal_tasks", None)
    if tasks is None:
        tasks = set()
        request.app.state.gcal_tasks = tasks
    task = Context().run(loop.create_task, _run())
    tasks.add(task)
    task.add_done_callback(tasks.discard)


# A pending flag older than this on a settings view means the original async
# task never finished (crash/restart) — kick reconciliation again.
STALE_PENDING_SECONDS = 60
_UNSET = object()


def retry_stale_pending(request: Request, user_id, *, connection=_UNSET) -> None:
    """Settings-view recovery: restart a sync whose durable flag went stale."""
    if not _gcal_enabled(request):
        return
    store = request.app.state.calendar_store
    if connection is _UNSET:
        started = perf_counter()
        try:
            connection = store.get_connection(user_id)
        except Exception:  # noqa: BLE001
            return
        finally:
            _record_timing("calendar_pending_retry", started)
    if connection is None or not connection.is_active or not connection.sync_pending:
        return
    from datetime import datetime, timezone as _tz

    requested = connection.sync_requested_at
    if requested is not None:
        age = (datetime.now(_tz.utc) - requested).total_seconds()
        if age < STALE_PENDING_SECONDS:
            return  # a task is plausibly still in flight — don't pile on
    schedule_sync(request, user_id)


@router.get("/calendar/google/connect")
async def gcal_connect(request: Request) -> RedirectResponse:
    if not _gcal_enabled(request):
        return _not_found()
    user = _current_user(request)
    if user is None:
        return RedirectResponse(
            url="/login?next=/settings&reason=default", status_code=303
        )
    settings = request.app.state.multiuser_settings
    # Capture the browser timezone BEFORE OAuth starts (app.js appends ?tz=).
    # Set-if-unset: an explicit Settings choice is never overwritten, but a
    # first-time connect gets real local event times instead of a UTC default.
    browser_tz = (request.query_params.get("tz") or "").strip()
    if browser_tz:
        repo = request.app.state.engine.repo
        try:
            ZoneInfo(browser_tz)
        except (KeyError, ValueError):
            pass
        else:
            started = perf_counter()
            current_tz = repo.get_setting(user.id, "user_timezone") or ""
            _record_timing("calendar_prefs", started)
            if not current_tz:
                started = perf_counter()
                repo.set_setting(user.id, "user_timezone", browser_tz)
                _record_timing("calendar_pref_write", started)
    state = secrets.token_urlsafe(24)
    params = {
        "client_id": settings.gcal_client_id,
        "redirect_uri": _redirect_uri(settings),
        "response_type": "code",
        "scope": GCAL_SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "false",
        "state": state,
    }
    response = RedirectResponse(
        url=f"{GOOGLE_AUTH_URL}?{urlencode(params)}", status_code=303
    )
    response.set_cookie(
        GCAL_STATE_COOKIE,
        state,
        httponly=True,
        samesite="lax",
        secure=bool(settings.cookie_secure),
        max_age=600,
        path="/",
    )
    return response


@router.get("/calendar/google/callback")
async def gcal_callback(request: Request) -> RedirectResponse:
    if not _gcal_enabled(request):
        return _not_found()
    user = _current_user(request)
    if user is None:
        return RedirectResponse(url="/login?next=/settings", status_code=303)
    settings = request.app.state.multiuser_settings
    store = request.app.state.calendar_store
    params = request.query_params

    def _fail(reason: str) -> RedirectResponse:
        response = RedirectResponse(
            url=f"/settings?gcal=error&why={reason}", status_code=303
        )
        response.delete_cookie(GCAL_STATE_COOKIE, path="/")
        return response

    cookie_state = request.cookies.get(GCAL_STATE_COOKIE)
    if not cookie_state or (params.get("state") or "") != cookie_state:
        return _fail("state")
    if params.get("error"):
        return _fail("denied")
    code = params.get("code")
    if not code:
        return _fail("code")

    transport = getattr(request.app.state, "gcal_transport", None)
    started = perf_counter()
    try:
        payload = await exchange_code(
            client_id=settings.gcal_client_id,
            client_secret=settings.gcal_client_secret,
            code=code,
            redirect_uri=_redirect_uri(settings),
            transport=transport,
        )
    except GoogleApiError:
        return _fail("exchange")
    finally:
        _record_timing("google_token_exchange", started)

    sealer = TokenSealer(settings.gcal_token_key)
    refresh_token = str(payload.get("refresh_token") or "")
    started = perf_counter()
    existing = store.get_connection(user.id)
    _record_timing("calendar_connection", started)
    if refresh_token:
        sealed = sealer.seal(refresh_token)
    elif existing is not None and existing.refresh_token_sealed:
        # Google omits refresh_token on re-consent — keep the stored one.
        sealed = existing.refresh_token_sealed
        refresh_token = sealer.unseal(sealed)
    else:
        return _fail("no_refresh_token")

    client = GoogleCalendarClient(
        client_id=settings.gcal_client_id,
        client_secret=settings.gcal_client_secret,
        refresh_token=refresh_token,
        transport=transport,
    )
    # Reuse the app-created calendar only while the connection stayed ACTIVE
    # (a re-consent without disconnecting). Our disconnect flow revokes the
    # grant, and revoking removes an app-created calendar from the user's
    # calendar LIST: Calendars.get still answers 200 for the re-authorised
    # app, but the user can't see the calendar, and the narrow
    # calendar.app.created scope has no calendarList.insert to re-list it.
    # Reusing after a disconnect would sync into an invisible calendar, so a
    # reconnect mints a fresh one (creation re-lists it automatically).
    calendar_id = (
        existing.google_calendar_id
        if existing is not None and existing.is_active
        else None
    )
    try:
        if calendar_id:
            started = perf_counter()
            try:
                found = await client.get_calendar(calendar_id)
            finally:
                _record_timing("google_calendar_check", started)
            if not found:
                calendar_id = None
        if calendar_id is None:
            started = perf_counter()
            tz = (
                request.app.state.engine.repo.get_setting(user.id, "user_timezone")
                or "UTC"
            )
            _record_timing("calendar_prefs", started)
            started = perf_counter()
            try:
                calendar_id = await client.create_calendar(timezone_id=tz)
            finally:
                _record_timing("google_calendar_check", started)
            # The fresh calendar starts empty: stored mappings point at the
            # old calendar's events and would suppress re-inserts — drop them
            # so the initial sync repopulates cleanly (no duplicates possible
            # in a brand-new calendar). Only a replacement calendar can have
            # stale mappings; first-ever connect (existing is None) skips this.
            if existing is not None:
                started = perf_counter()
                store.delete_all_event_mappings(user.id)
                _record_timing("calendar_connection_write", started)
    except GoogleApiError:
        return _fail("calendar")

    started = perf_counter()
    store.upsert_connection(
        user.id,
        google_calendar_id=calendar_id,
        refresh_token_sealed=sealed,
        sync_status=SYNC_PENDING,
    )
    _record_timing("calendar_connection_write", started)
    # Initial sync runs async — the browser is never held for 90 days of events.
    schedule_sync(request, user.id)
    response = RedirectResponse(url="/settings?gcal=connected", status_code=303)
    response.delete_cookie(GCAL_STATE_COOKIE, path="/")
    return response


@router.post("/calendar/google/disconnect")
async def gcal_disconnect(
    request: Request, csrf_token: str = Form(...)
) -> RedirectResponse:
    if not _gcal_enabled(request):
        return _not_found()
    user = _current_user(request)
    if user is None:
        return RedirectResponse(url="/login?next=/settings", status_code=303)
    if request.cookies.get(CSRF_COOKIE_NAME) != csrf_token:
        return RedirectResponse(url="/settings?gcal=error&why=csrf", status_code=303)
    settings = request.app.state.multiuser_settings
    store = request.app.state.calendar_store
    started = perf_counter()
    connection = store.get_connection(user.id)
    _record_timing("calendar_connection", started)
    if connection is not None and connection.refresh_token_sealed:
        try:
            token = TokenSealer(settings.gcal_token_key).unseal(
                connection.refresh_token_sealed
            )
            started = perf_counter()
            await revoke_token(
                token, transport=getattr(request.app.state, "gcal_transport", None)
            )
            _record_timing("google_token_revoke", started)
        except TokenSealError:
            pass  # can't unseal → nothing to revoke remotely
    started = perf_counter()
    store.tombstone(user.id)
    _record_timing("calendar_connection_write", started)
    return RedirectResponse(url="/settings?gcal=disconnected", status_code=303)


@router.post("/calendar/google/retry")
async def gcal_retry(
    request: Request, csrf_token: str = Form(...)
) -> RedirectResponse:
    if not _gcal_enabled(request):
        return _not_found()
    user = _current_user(request)
    if user is None:
        return RedirectResponse(url="/login?next=/settings", status_code=303)
    if request.cookies.get(CSRF_COOKIE_NAME) != csrf_token:
        return RedirectResponse(url="/settings?gcal=error&why=csrf", status_code=303)
    schedule_sync(request, user.id)
    return RedirectResponse(url="/settings?gcal=syncing", status_code=303)


@router.post("/calendar/google/preferences")
async def gcal_preferences(
    request: Request,
    csrf_token: str = Form(...),
    user_timezone: str | None = Form(None),
    revision_time: str | None = Form(None),
    session_minutes: str | None = Form(None),
    reminder_cadence: str | None = Form(None),
) -> RedirectResponse:
    """Persist whichever preference fields the form supplied.

    Absent fields are left untouched — the post-connect reminder popup posts
    ONLY ``reminder_cadence``, while the Settings grid posts the full set.
    """
    if not _gcal_enabled(request):
        return _not_found()
    user = _current_user(request)
    if user is None:
        return RedirectResponse(url="/login?next=/settings", status_code=303)
    if request.cookies.get(CSRF_COOKIE_NAME) != csrf_token:
        return RedirectResponse(url="/settings?gcal=error&why=csrf", status_code=303)
    repo = request.app.state.engine.repo

    started = None

    if user_timezone is not None:
        tz = user_timezone.strip()
        if tz:
            try:
                ZoneInfo(tz)
            except (KeyError, ValueError):
                return RedirectResponse(
                    url="/settings?gcal=error&why=timezone", status_code=303
                )
            if started is None:
                started = perf_counter()
            repo.set_setting(user.id, "user_timezone", tz)

    if revision_time is not None:
        time_pref = revision_time.strip()
        try:
            hour, minute = (int(p) for p in time_pref.split(":", 1))
            assert 0 <= hour <= 23 and 0 <= minute <= 59
        except (ValueError, AssertionError):
            return RedirectResponse(
                url="/settings?gcal=error&why=time", status_code=303
            )
        if started is None:
            started = perf_counter()
        repo.set_setting(user.id, "gcal_revision_time", f"{hour:02d}:{minute:02d}")

    if session_minutes is not None:
        try:
            minutes = int(session_minutes)
        except ValueError:
            minutes = 0
        if minutes not in VALID_SESSION_MINUTES:
            return RedirectResponse(
                url="/settings?gcal=error&why=duration", status_code=303
            )
        if started is None:
            started = perf_counter()
        repo.set_setting(user.id, "gcal_session_minutes", str(minutes))

    if reminder_cadence is not None:
        cadence = reminder_cadence.strip()
        if cadence not in VALID_REMINDER_CADENCES:
            return RedirectResponse(
                url="/settings?gcal=error&why=cadence", status_code=303
            )
        if started is None:
            started = perf_counter()
        repo.set_setting(user.id, "gcal_reminder_cadence", cadence)

    if started is not None:
        _record_timing("calendar_pref_write", started)

    # Prefs change event times/notifications → resync.
    schedule_sync(request, user.id)
    return RedirectResponse(url="/settings?gcal=saved", status_code=303)
