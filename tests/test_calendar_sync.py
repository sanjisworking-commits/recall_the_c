"""Reconciliation: create/patch/delete, idempotency, sync_pending, failures."""

from __future__ import annotations

import asyncio
import json
import threading
from datetime import date
from pathlib import Path
from uuid import UUID

import httpx

from constitution_memorizer.calendar_sync.google_client import GoogleCalendarClient
from constitution_memorizer.calendar_sync.store import (
    SYNC_PENDING,
    SqliteCalendarStore,
)
from constitution_memorizer.calendar_sync.sync import (
    _prepare_reconciliation,
    reconcile_user_calendar,
    sync_user_calendar,
)
from constitution_memorizer.progress.db import open_progress_db
from constitution_memorizer.progress.repository import ProgressRepository
from constitution_memorizer.progress.scheduler import ReminderEngine

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
USER = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
CAL_ID = "cal_recall_1"
DASH = "https://recall-the-c.in/dashboard"


class FakeGoogle:
    """In-memory Calendar backend behind an httpx.MockTransport."""

    def __init__(self) -> None:
        self.events: dict[str, dict] = {}
        self.calls: list[str] = []
        self.next_id = 0
        self.fail_all = False
        self.revoke_auth = False

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        method = request.method
        if path == "/token":
            if self.revoke_auth:
                return httpx.Response(400, json={"error": "invalid_grant"})
            return httpx.Response(
                200, json={"access_token": "at", "expires_in": 3600}
            )
        if self.fail_all:
            self.calls.append(f"{method} {path} -> 503")
            return httpx.Response(503, json={"error": "backendError"})
        if method == "POST" and path.endswith("/events"):
            self.next_id += 1
            event_id = f"ev{self.next_id}"
            self.events[event_id] = json.loads(request.content)
            self.calls.append(f"insert {event_id}")
            return httpx.Response(200, json={"id": event_id})
        if method == "PATCH":
            event_id = path.rsplit("/", 1)[-1]
            if event_id not in self.events:
                self.calls.append(f"patch {event_id} -> 404")
                return httpx.Response(404)
            self.events[event_id] = json.loads(request.content)
            self.calls.append(f"patch {event_id}")
            return httpx.Response(200, json={"id": event_id})
        if method == "DELETE":
            event_id = path.rsplit("/", 1)[-1]
            existed = self.events.pop(event_id, None) is not None
            self.calls.append(f"delete {event_id}" + ("" if existed else " -> 404"))
            return httpx.Response(204 if existed else 404)
        if method == "GET" and "/calendars/" in path:
            self.calls.append(f"get {path.rsplit('/', 1)[-1]}")
            return httpx.Response(200, json={"id": CAL_ID})
        return httpx.Response(404)


def _setup(tmp_path: Path):
    conn = open_progress_db(tmp_path / "progress.db")
    repo = ProgressRepository(conn)
    engine = ReminderEngine.from_repository(
        repo, _units_catalog(), user_id=USER
    )
    store = SqliteCalendarStore(conn)
    fake = FakeGoogle()
    client = GoogleCalendarClient(
        client_id="cid",
        client_secret="cs",
        refresh_token="rt",
        transport=fake.transport(),
    )
    return engine, store, fake, client


def _units_catalog():
    from constitution_memorizer.learning.schemas import LearningUnitsDocument
    from constitution_memorizer.utils.json_io import read_json

    doc = LearningUnitsDocument.model_validate(read_json(MINI_UNITS))
    return {u.id: u for u in doc.units}


def _complete(engine: ReminderEngine, unit_id: str, on: date) -> None:
    engine.mark_all_modes_seen(unit_id)
    engine.mark_done(unit_id, as_of=on)


class ProbeCalendarStore:
    """Records the thread id of blocking store methods used by background sync."""

    def __init__(self, inner: SqliteCalendarStore) -> None:
        self._inner = inner
        self.clear_thread_records()

    def clear_thread_records(self) -> None:
        self.get_connection_threads: list[int] = []
        self.list_event_mappings_threads: list[int] = []
        self.upsert_event_mapping_threads: list[int] = []
        self.delete_event_mapping_threads: list[int] = []
        self.mark_sync_result_threads: list[int] = []

    def __getattr__(self, name: str):
        return getattr(self._inner, name)

    def get_connection(self, user_id):
        self.get_connection_threads.append(threading.get_ident())
        return self._inner.get_connection(user_id)

    def list_event_mappings(self, user_id):
        self.list_event_mappings_threads.append(threading.get_ident())
        return self._inner.list_event_mappings(user_id)

    def upsert_event_mapping(self, user_id, **kwargs):
        self.upsert_event_mapping_threads.append(threading.get_ident())
        return self._inner.upsert_event_mapping(user_id, **kwargs)

    def delete_event_mapping(self, user_id, local_date):
        self.delete_event_mapping_threads.append(threading.get_ident())
        return self._inner.delete_event_mapping(user_id, local_date)

    def mark_sync_result(self, user_id, *, ok: bool, error: str | None = None):
        self.mark_sync_result_threads.append(threading.get_ident())
        return self._inner.mark_sync_result(user_id, ok=ok, error=error)


def _reconcile(engine, store, client, today: date):
    return asyncio.run(
        reconcile_user_calendar(
            engine=engine,
            store=store,
            client=client,
            calendar_id=CAL_ID,
            dashboard_url=DASH,
            today=today,
        )
    )


def test_initial_sync_creates_events_and_mappings(tmp_path: Path) -> None:
    engine, store, fake, client = _setup(tmp_path)
    _complete(engine, "clause-1", date(2026, 8, 18))  # → 19 Aug
    counts = _reconcile(engine, store, client, date(2026, 8, 18))
    # Full ladder inside the 120-day horizon: 19/22/29 Aug, 13 Sep, 13 Oct, 12 Dec.
    assert counts == {"created": 6, "patched": 0, "deleted": 0, "unchanged": 0}
    assert len(store.list_event_mappings(USER)) == 6
    assert len(fake.events) == 6


def test_double_run_is_idempotent_zero_api_calls(tmp_path: Path) -> None:
    engine, store, fake, client = _setup(tmp_path)
    _complete(engine, "clause-1", date(2026, 8, 18))
    _reconcile(engine, store, client, date(2026, 8, 18))
    fake.calls.clear()
    counts = _reconcile(engine, store, client, date(2026, 8, 18))
    assert counts == {"created": 0, "patched": 0, "deleted": 0, "unchanged": 6}
    assert fake.calls == []  # unchanged days = no Google traffic at all
    assert len(fake.events) == 6


def test_changed_day_patches_event(tmp_path: Path) -> None:
    engine, store, fake, client = _setup(tmp_path)
    _complete(engine, "clause-1", date(2026, 8, 18))
    _reconcile(engine, store, client, date(2026, 8, 18))
    # A second unit lands on the same day → content hash changes.
    _complete(engine, "clause-2", date(2026, 8, 18))
    counts = _reconcile(engine, store, client, date(2026, 8, 18))
    # Both units share the same ladder dates → every day gains a revision.
    assert counts["patched"] == 6 and counts["created"] == 0
    assert len(fake.events) == 6
    assert all("2 revisions" in body["summary"] for body in fake.events.values())


def test_zero_work_date_deletes_event(tmp_path: Path) -> None:
    engine, store, fake, client = _setup(tmp_path)
    _complete(engine, "clause-1", date(2026, 8, 18))  # → 19 Aug
    _reconcile(engine, store, client, date(2026, 8, 18))
    # Completing on the 19th advances the pending rung to the 22nd: the
    # 19 Aug event becomes zero-work and must be DELETED (never a
    # "0 revisions" or "✅ Complete" event in v1); the later ladder days
    # (22/29 Aug, 13 Sep, 13 Oct) are already mapped and stay unchanged.
    _complete(engine, "clause-1", date(2026, 8, 19))
    counts = _reconcile(engine, store, client, date(2026, 8, 19))
    assert counts["deleted"] == 1 and counts["created"] == 0
    assert counts["unchanged"] == 5
    dates = sorted(m.local_date for m in store.list_event_mappings(USER))
    assert dates == [
        date(2026, 8, 22),
        date(2026, 8, 29),
        date(2026, 9, 13),
        date(2026, 10, 13),
        date(2026, 12, 12),
    ]
    assert len(fake.events) == 5


def test_vanished_event_is_recreated_on_patch(tmp_path: Path) -> None:
    engine, store, fake, client = _setup(tmp_path)
    _complete(engine, "clause-1", date(2026, 8, 18))
    _reconcile(engine, store, client, date(2026, 8, 18))
    fake.events.clear()  # user deleted the events inside Google
    _complete(engine, "clause-2", date(2026, 8, 18))  # dirty every hash
    counts = _reconcile(engine, store, client, date(2026, 8, 18))
    assert counts["patched"] == 6  # patch path, recreated internally
    assert len(fake.events) == 6


def test_sync_pending_cleared_on_success_kept_on_failure(tmp_path: Path) -> None:
    engine, store, fake, client = _setup(tmp_path)
    _complete(engine, "clause-1", date(2026, 8, 18))
    store.upsert_connection(
        USER,
        google_calendar_id=CAL_ID,
        refresh_token_sealed="sealed",
        sync_status=SYNC_PENDING,
    )
    store.mark_sync_pending(USER)

    def factory(_connection):
        return client

    ok = asyncio.run(
        sync_user_calendar(
            user_id=USER,
            engine=engine,
            store=store,
            client_factory=factory,
            dashboard_url=DASH,
        )
    )
    assert ok is True
    connection = store.get_connection(USER)
    assert connection.sync_pending is False and connection.sync_status == "ok"
    assert connection.last_synced_at is not None

    # Now a failing Google: pending stays set, error recorded, never raises.
    fake.fail_all = True
    store.mark_sync_pending(USER)
    _complete(engine, "clause-2", date(2026, 8, 18))
    ok = asyncio.run(
        sync_user_calendar(
            user_id=USER,
            engine=engine,
            store=store,
            client_factory=factory,
            dashboard_url=DASH,
        )
    )
    assert ok is False
    connection = store.get_connection(USER)
    assert connection.sync_pending is True  # retryable
    assert connection.sync_status == "error"
    assert "google api" in (connection.last_error or "")


def test_revoked_auth_marks_error_without_raising(tmp_path: Path) -> None:
    engine, store, fake, client = _setup(tmp_path)
    _complete(engine, "clause-1", date(2026, 8, 18))
    store.upsert_connection(
        USER,
        google_calendar_id=CAL_ID,
        refresh_token_sealed="sealed",
        sync_status=SYNC_PENDING,
    )
    fake.revoke_auth = True
    ok = asyncio.run(
        sync_user_calendar(
            user_id=USER,
            engine=engine,
            store=store,
            client_factory=lambda _c: client,
            dashboard_url=DASH,
        )
    )
    assert ok is False
    connection = store.get_connection(USER)
    assert connection.last_error == "authorization revoked"


def test_tombstone_disconnect_keeps_calendar_id_and_mappings(tmp_path: Path) -> None:
    engine, store, fake, client = _setup(tmp_path)
    store.upsert_connection(
        USER,
        google_calendar_id=CAL_ID,
        refresh_token_sealed="sealed",
        sync_status=SYNC_PENDING,
    )
    store.upsert_event_mapping(
        USER,
        local_date=date(2026, 8, 19),
        google_event_id="ev1",
        content_hash="h",
    )
    store.tombstone(USER)
    connection = store.get_connection(USER)
    assert connection is not None
    assert connection.google_calendar_id == CAL_ID  # preserved for reconnect
    assert connection.refresh_token_sealed is None
    assert connection.is_active is False
    # Mappings SURVIVE disconnect — the events still exist in Google, and
    # wiping the mappings would duplicate every event on reconnect.
    assert len(store.list_event_mappings(USER)) == 1
    # A tombstoned connection never syncs.
    ok = asyncio.run(
        sync_user_calendar(
            user_id=USER,
            engine=engine,
            store=store,
            client_factory=lambda _c: client,
            dashboard_url=DASH,
        )
    )
    assert ok is False


def test_reconnect_does_not_duplicate_events(tmp_path: Path) -> None:
    """Blocker regression: disconnect → reconnect must PATCH, never re-insert."""
    engine, store, fake, client = _setup(tmp_path)
    _complete(engine, "clause-1", date(2026, 8, 18))  # → 19 Aug
    store.upsert_connection(
        USER,
        google_calendar_id=CAL_ID,
        refresh_token_sealed="sealed",
        sync_status=SYNC_PENDING,
    )
    _reconcile(engine, store, client, date(2026, 8, 18))
    assert len(fake.events) == 6

    store.tombstone(USER)  # disconnect — Google events remain
    store.upsert_connection(  # reconnect (same calendar id preserved)
        USER,
        google_calendar_id=CAL_ID,
        refresh_token_sealed="sealed-2",
        sync_status=SYNC_PENDING,
    )
    counts = _reconcile(engine, store, client, date(2026, 8, 18))
    assert counts["created"] == 0  # ← the blocker: no re-insert
    assert counts["unchanged"] == 6
    assert len(fake.events) == 6  # still exactly one event per day in Google


def test_delete_user_data_removes_everything(tmp_path: Path) -> None:
    engine, store, fake, client = _setup(tmp_path)
    store.upsert_connection(
        USER,
        google_calendar_id=CAL_ID,
        refresh_token_sealed="sealed",
        sync_status=SYNC_PENDING,
    )
    store.upsert_event_mapping(
        USER, local_date=date(2026, 8, 19), google_event_id="ev1", content_hash="h"
    )
    other = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
    store.upsert_connection(
        other,
        google_calendar_id="cal_other",
        refresh_token_sealed="sealed2",
        sync_status=SYNC_PENDING,
    )
    store.delete_user_data(USER)
    assert store.get_connection(USER) is None
    assert store.list_event_mappings(USER) == []
    assert store.get_connection(other) is not None  # other users intact


def test_events_carry_default_once_reminder(tmp_path: Path) -> None:
    """A fresh app-created calendar has NO default notifications, so every
    event must ship an explicit 10-minute popup even before any choice."""
    engine, store, fake, client = _setup(tmp_path)
    _complete(engine, "clause-1", date(2026, 8, 18))
    _reconcile(engine, store, client, date(2026, 8, 18))
    assert len(fake.events) == 6
    for body in fake.events.values():
        assert body["reminders"] == {
            "useDefault": False,
            "overrides": [{"method": "popup", "minutes": 10}],
        }


def test_cadence_change_repatches_all_events(tmp_path: Path) -> None:
    engine, store, fake, client = _setup(tmp_path)
    _complete(engine, "clause-1", date(2026, 8, 18))
    _reconcile(engine, store, client, date(2026, 8, 18))
    engine.repo.set_setting(USER, "gcal_reminder_cadence", "thrice")
    counts = _reconcile(engine, store, client, date(2026, 8, 18))
    # Only the reminder offsets changed → every event repatches, none recreated.
    assert counts == {"created": 0, "patched": 6, "deleted": 0, "unchanged": 0}
    for body in fake.events.values():
        assert body["reminders"]["useDefault"] is False
        assert [o["minutes"] for o in body["reminders"]["overrides"]] == [480, 240, 10]
        assert all(o["method"] == "popup" for o in body["reminders"]["overrides"])


def _assert_off_loop(threads: list[int], loop_thread: int) -> None:
    assert threads
    assert all(t != loop_thread for t in threads)


def test_sync_store_and_prepare_run_off_event_loop_thread(
    tmp_path: Path, monkeypatch
) -> None:
    engine, inner, fake, client = _setup(tmp_path)
    probe = ProbeCalendarStore(inner)
    _complete(engine, "clause-1", date(2026, 8, 18))
    probe.upsert_connection(
        USER,
        google_calendar_id=CAL_ID,
        refresh_token_sealed="sealed",
        sync_status=SYNC_PENDING,
    )
    probe.mark_sync_pending(USER)

    prepare_threads: list[int] = []
    real_prepare = _prepare_reconciliation

    def _spy_prepare(engine_arg, store_arg, today, extra_loader=None):
        prepare_threads.append(threading.get_ident())
        return real_prepare(engine_arg, store_arg, today, extra_loader)

    monkeypatch.setattr(
        "constitution_memorizer.calendar_sync.sync._prepare_reconciliation",
        _spy_prepare,
    )

    async def _run() -> int:
        probe.clear_thread_records()
        prepare_threads.clear()
        loop_thread = threading.get_ident()
        ok = await sync_user_calendar(
            user_id=USER,
            engine=engine,
            store=probe,
            client_factory=lambda _c: client,
            dashboard_url=DASH,
        )
        assert ok is True
        return loop_thread

    loop_thread = asyncio.run(_run())
    _assert_off_loop(probe.get_connection_threads, loop_thread)
    _assert_off_loop(probe.list_event_mappings_threads, loop_thread)
    _assert_off_loop(probe.upsert_event_mapping_threads, loop_thread)
    _assert_off_loop(probe.mark_sync_result_threads, loop_thread)
    _assert_off_loop(prepare_threads, loop_thread)
    connection = inner.get_connection(USER)
    assert connection is not None
    assert connection.sync_pending is False and connection.sync_status == "ok"


def test_sync_delete_and_failure_mark_result_run_off_loop(tmp_path: Path) -> None:
    engine, inner, fake, client = _setup(tmp_path)
    probe = ProbeCalendarStore(inner)
    _complete(engine, "clause-1", date(2026, 8, 18))
    probe.upsert_connection(
        USER,
        google_calendar_id=CAL_ID,
        refresh_token_sealed="sealed",
        sync_status=SYNC_PENDING,
    )
    asyncio.run(
        reconcile_user_calendar(
            engine=engine,
            store=probe,
            client=client,
            calendar_id=CAL_ID,
            dashboard_url=DASH,
            today=date(2026, 8, 18),
        )
    )
    _complete(engine, "clause-1", date(2026, 8, 19))

    async def _delete_run() -> int:
        probe.clear_thread_records()
        loop_thread = threading.get_ident()
        ok = await sync_user_calendar(
            user_id=USER,
            engine=engine,
            store=probe,
            client_factory=lambda _c: client,
            dashboard_url=DASH,
        )
        assert ok is True
        return loop_thread

    loop_thread = asyncio.run(_delete_run())
    _assert_off_loop(probe.delete_event_mapping_threads, loop_thread)
    _assert_off_loop(probe.mark_sync_result_threads, loop_thread)

    fake.fail_all = True
    probe.mark_sync_pending(USER)
    _complete(engine, "clause-2", date(2026, 8, 19))

    async def _fail_run() -> int:
        probe.clear_thread_records()
        loop_thread = threading.get_ident()
        ok = await sync_user_calendar(
            user_id=USER,
            engine=engine,
            store=probe,
            client_factory=lambda _c: client,
            dashboard_url=DASH,
        )
        assert ok is False
        return loop_thread

    loop_thread = asyncio.run(_fail_run())
    _assert_off_loop(probe.mark_sync_result_threads, loop_thread)
    connection = inner.get_connection(USER)
    assert connection is not None
    assert connection.sync_pending is True
    assert "google api" in (connection.last_error or "")
