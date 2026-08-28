"""SQLite + Postgres repositories must satisfy ReminderRepositoryProtocol."""

from __future__ import annotations

import inspect

from constitution_memorizer.progress.postgres_repository import PostgresProgressRepository
from constitution_memorizer.progress.protocols import ReminderRepositoryProtocol
from constitution_memorizer.progress.repository import ProgressRepository
from constitution_memorizer.progress.scheduler import ReminderEngine


def _protocol_method_names() -> set[str]:
    names = {
        name
        for name, value in ReminderRepositoryProtocol.__dict__.items()
        if not name.startswith("_") and inspect.isfunction(value)
    }
    attrs = getattr(ReminderRepositoryProtocol, "__protocol_attrs__", None)
    if attrs:
        names.update(n for n in attrs if not str(n).startswith("_"))
    return names


def test_protocol_surface_is_nontrivial():
    names = _protocol_method_names()
    required = {
        "get_progress",
        "ensure_progress",
        "upsert_progress",
        "list_due",
        "list_all_progress",
        "count_by_status",
        "get_gloss",
        "upsert_gloss",
        "delete_gloss",
        "delete_progress",
        "delete_all_progress",
        "clear_all_modes_seen",
        "get_profile",
        "needs_welcome",
        "get_notification_last_slot",
        "set_notification_last_slot",
        "load_completion_state",
        "commit_completion",
        "record_daily_goal_met",
        "is_daily_goal_met",
        "list_daily_goal_dates",
    }
    assert required <= names


def test_sqlite_and_postgres_implement_protocol_methods():
    names = _protocol_method_names()
    assert names, "expected ReminderRepositoryProtocol methods"
    for cls in (ProgressRepository, PostgresProgressRepository):
        missing = [name for name in sorted(names) if not hasattr(cls, name)]
        assert missing == [], f"{cls.__name__} missing: {missing}"


def test_reminder_engine_accepts_protocol_typed_repo():
    annotations = ReminderEngine.__init__.__annotations__
    assert annotations.get("repo") in {
        "ReminderRepositoryProtocol",
        ReminderRepositoryProtocol,
    }
    assert hasattr(ReminderEngine, "from_repository")
