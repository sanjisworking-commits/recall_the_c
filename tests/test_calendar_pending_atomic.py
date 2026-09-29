"""Phase 4 (request latency): mark_sync_pending_if_active collapses the
get_connection + mark_sync_pending pair into one atomic round trip.

The durable sync_pending guarantee and the "no active connection → no work"
behavior must be preserved: the flag is set (and True returned) only when an
active connection exists; a missing or disconnected connection is a no-op that
returns False and touches nothing.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

from constitution_memorizer.calendar_sync.store import (
    SYNC_DISCONNECTED,
    SYNC_OK,
    SqliteCalendarStore,
)
from constitution_memorizer.progress.db import open_progress_db

USER = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")


def _store(tmp_path: Path) -> SqliteCalendarStore:
    return SqliteCalendarStore(open_progress_db(tmp_path / "progress.db"))


def _seed_active(store: SqliteCalendarStore) -> None:
    store.upsert_connection(
        USER,
        google_calendar_id="cal_1",
        refresh_token_sealed="sealed-token",
        sync_status=SYNC_OK,
    )


def test_active_connection_becomes_pending_atomically(tmp_path: Path):
    store = _store(tmp_path)
    _seed_active(store)
    assert store.get_connection(USER).sync_pending is False

    changed = store.mark_sync_pending_if_active(USER)

    assert changed is True
    conn = store.get_connection(USER)
    assert conn.sync_pending is True
    assert conn.sync_requested_at is not None


def test_missing_connection_is_a_noop(tmp_path: Path):
    store = _store(tmp_path)
    assert store.mark_sync_pending_if_active(USER) is False
    assert store.get_connection(USER) is None


def test_disconnected_connection_is_a_noop(tmp_path: Path):
    store = _store(tmp_path)
    _seed_active(store)
    store.tombstone(USER)  # clears token, sets sync_status=disconnected
    assert store.get_connection(USER).is_active is False

    changed = store.mark_sync_pending_if_active(USER)

    assert changed is False
    # Tombstone left sync_pending cleared; the no-op must not resurrect it.
    conn = store.get_connection(USER)
    assert conn.sync_pending is False
    assert conn.sync_status == SYNC_DISCONNECTED


def test_connection_without_token_is_a_noop(tmp_path: Path):
    store = _store(tmp_path)
    store.upsert_connection(
        USER,
        google_calendar_id="cal_1",
        refresh_token_sealed=None,  # never authorized
        sync_status=SYNC_OK,
    )
    assert store.mark_sync_pending_if_active(USER) is False
    assert store.get_connection(USER).sync_pending is False


# ── schedule_sync only launches a task when a connection is active ────────────


def _stub_request(tmp_path: Path, store: SqliteCalendarStore):
    """A minimal request whose app carries just what schedule_sync inspects."""
    settings = SimpleNamespace(
        google_calendar_enabled=True,
        app_base_url="https://recall-the-c.in",
    )
    app_state = SimpleNamespace(
        calendar_store=store,
        multiuser_settings=settings,
        engine=SimpleNamespace(for_user=lambda uid: SimpleNamespace(user_id=uid)),
    )
    return SimpleNamespace(app=SimpleNamespace(state=app_state))


def test_schedule_sync_no_task_when_inactive(tmp_path: Path, monkeypatch):
    import constitution_memorizer.calendar_sync.routes as routes

    store = _store(tmp_path)  # no connection at all
    monkeypatch.setattr(routes, "_gcal_enabled", lambda _req: True)
    launched: list[str] = []
    monkeypatch.setattr(
        routes, "make_client_factory", lambda _req: launched.append("factory")
    )
    request = _stub_request(tmp_path, store)

    routes.schedule_sync(request, USER)

    # Inactive: flagging returned False, so we never built a client/task.
    assert launched == []
    assert store.get_connection(USER) is None
