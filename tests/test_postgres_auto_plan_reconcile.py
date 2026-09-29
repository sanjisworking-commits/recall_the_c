"""Phase 3 (request latency): the Postgres Auto-roadmap reconcile must load its
snapshot in one pipelined batch and write the new window with bulk inserts.

These use a fake psycopg connection (the same technique as
test_planner_read_bundle) so the SQL *shape* is pinned without a live Postgres:

- the six independent snapshot SELECTs are queued inside one ``conn.pipeline()``
  (or run sequentially when the build has no pipeline support), on the same
  connection that already holds the ``user_learning_plan`` FOR UPDATE lock;
- the write side issues exactly one multi-row INSERT per table instead of one
  execute() per day/item — no per-item loop regression;
- rollback/serialization structure (transaction + FOR UPDATE) is preserved.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from uuid import UUID

import pytest

from constitution_memorizer.progress.postgres_repository import (
    PostgresProgressRepository,
)
from constitution_memorizer.progress.repository import (
    AutoPlanDay,
    AutoPlanItem,
    AutoPlanSnapshot,
)

USER = UUID("11111111-1111-4111-8111-111111111111")


class _FakeCursor:
    def __init__(self, conn: "_FakeConnection") -> None:
        self.conn = conn
        self._kind: str | None = None

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def execute(self, sql: str, params=None) -> None:
        self.conn.events.append(("execute", " ".join(sql.split()), params))
        text = " ".join(sql.split()).lower()
        if "for update" in text or "insert into user_learning_plan" in text:
            self._kind = "plan"
        elif "learning_unit_progress" in text:
            self._kind = "progress"
        elif "split_preference" in text:
            self._kind = "split"
        elif "study_session" in text:
            self._kind = "sessions"
        elif "auto_plan_day" in text:
            self._kind = "auto_day"
        elif "auto_plan_item" in text:
            self._kind = "auto_item"
        elif "user_free_articles" in text:
            self._kind = "claims"
        else:
            self._kind = "other"

    def fetchone(self):
        self.conn.events.append(("fetchone", self._kind))
        return None

    def fetchall(self):
        self.conn.events.append(("fetchall", self._kind))
        return []


class _FakeConnection:
    def __init__(self) -> None:
        self.events: list[tuple] = []
        self.pipeline_entries = 0
        self.commits = 0
        self.rollbacks = 0

    def cursor(self, row_factory=None):
        return _FakeCursor(self)

    @contextmanager
    def pipeline(self):
        self.pipeline_entries += 1
        self.events.append(("pipeline_enter",))
        yield
        self.events.append(("pipeline_exit",))

    @contextmanager
    def transaction(self):
        self.events.append(("tx_enter",))
        yield
        self.events.append(("tx_exit",))

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def __enter__(self) -> "_FakeConnection":
        return self

    def __exit__(self, *exc: object) -> None:
        return None


class _FakePool:
    def __init__(self, conn: _FakeConnection) -> None:
        self.conn = conn
        self.borrows = 0

    @contextmanager
    def connection(self):
        self.borrows += 1
        yield self.conn


def _repo(monkeypatch, *, pipeline: bool) -> tuple[PostgresProgressRepository, _FakeConnection]:
    conn = _FakeConnection()
    monkeypatch.setattr(
        "constitution_memorizer.progress.postgres_repository._pipeline_capability",
        lambda: (pipeline, None if pipeline else "is_supported_false"),
    )
    return PostgresProgressRepository(_FakePool(conn)), conn


def _days() -> list[AutoPlanDay]:
    d0, d1 = date(2026, 9, 1), date(2026, 9, 2)
    return [
        AutoPlanDay(
            plan_date=d0,
            daily_target=3,
            items=(
                AutoPlanItem(plan_date=d0, learning_unit_id="clause-1", position=0),
                AutoPlanItem(plan_date=d0, learning_unit_id="clause-2", position=1),
            ),
        ),
        AutoPlanDay(
            plan_date=d1,
            daily_target=3,
            items=(
                AutoPlanItem(plan_date=d1, learning_unit_id="clause-3", position=0),
            ),
        ),
    ]


def _inserts(conn: _FakeConnection, table: str) -> list[tuple]:
    return [
        (sql, params)
        for kind, sql, params in (e for e in conn.events if e[0] == "execute")
        if sql.lower().startswith(f"insert into {table}")
    ]


def _snapshot_selects_before_first_fetch(conn: _FakeConnection) -> int:
    kinds = [e[0] for e in conn.events]
    # The reconcile's own plan INSERT + FOR UPDATE + fetchone come first; the
    # snapshot batch is the run of executes after that fetchone.
    first_fetch = kinds.index("fetchone")
    tail = conn.events[first_fetch + 1 :]
    count = 0
    for event in tail:
        if event[0] == "execute":
            count += 1
        elif event[0] in {"fetchall", "fetchone"}:
            break
    return count


def test_reconcile_pipelines_the_six_snapshot_reads(monkeypatch):
    repo, conn = _repo(monkeypatch, pipeline=True)
    seen: list[AutoPlanSnapshot] = []

    def builder(snapshot: AutoPlanSnapshot):
        seen.append(snapshot)
        return _days()

    repo.apply_auto_plan_reconcile(
        USER, as_of=date(2026, 9, 1), horizon=date(2026, 9, 15), builder=builder
    )

    assert conn.pipeline_entries == 1
    assert _snapshot_selects_before_first_fetch(conn) == 6
    assert len(seen) == 1  # builder ran once, on the locked snapshot
    # The lock + transaction structure is intact.
    assert ("tx_enter",) in conn.events
    for_update = [e for e in conn.events if e[0] == "execute" and "for update" in e[1].lower()]
    assert len(for_update) == 1


def test_reconcile_writes_one_bulk_insert_per_table(monkeypatch):
    repo, conn = _repo(monkeypatch, pipeline=True)

    repo.apply_auto_plan_reconcile(
        USER, as_of=date(2026, 9, 1), horizon=date(2026, 9, 15), builder=lambda _s: _days()
    )

    day_inserts = _inserts(conn, "auto_plan_day")
    item_inserts = _inserts(conn, "auto_plan_item")
    # Exactly one statement each — no per-day/per-item execute loop.
    assert len(day_inserts) == 1
    assert len(item_inserts) == 1
    # One multi-row VALUES group per row: 2 days, 3 items.
    assert day_inserts[0][0].lower().count("(%s, %s, %s, %s, %s)") == 2
    assert item_inserts[0][0].lower().count("(%s, %s, %s, %s, %s)") == 3
    # And the flattened params carry the real day/item data.
    assert len(day_inserts[0][1]) == 2 * 5
    assert len(item_inserts[0][1]) == 3 * 5
    assert "clause-1" in item_inserts[0][1]
    assert "clause-3" in item_inserts[0][1]


def test_reconcile_bulk_writes_also_run_without_pipeline_support(monkeypatch):
    repo, conn = _repo(monkeypatch, pipeline=False)

    repo.apply_auto_plan_reconcile(
        USER, as_of=date(2026, 9, 1), horizon=date(2026, 9, 15), builder=lambda _s: _days()
    )

    # Fallback: no pipeline, but the reads still ran and writes are still bulk.
    assert conn.pipeline_entries == 0
    assert _snapshot_selects_before_first_fetch(conn) == 6
    assert len(_inserts(conn, "auto_plan_day")) == 1
    assert len(_inserts(conn, "auto_plan_item")) == 1


def test_reconcile_none_days_clears_window_without_inserts(monkeypatch):
    repo, conn = _repo(monkeypatch, pipeline=True)

    repo.apply_auto_plan_reconcile(
        USER, as_of=date(2026, 9, 1), horizon=date(2026, 9, 15), builder=lambda _s: None
    )

    assert _inserts(conn, "auto_plan_day") == []
    assert _inserts(conn, "auto_plan_item") == []
    deletes = [
        e for e in conn.events
        if e[0] == "execute" and e[1].lower().startswith("delete from auto_plan")
    ]
    assert len(deletes) == 2  # item + day cleared from as_of


def test_reconcile_empty_days_deletes_but_inserts_nothing(monkeypatch):
    repo, conn = _repo(monkeypatch, pipeline=True)

    repo.apply_auto_plan_reconcile(
        USER, as_of=date(2026, 9, 1), horizon=date(2026, 9, 15), builder=lambda _s: []
    )

    assert _inserts(conn, "auto_plan_day") == []
    assert _inserts(conn, "auto_plan_item") == []
    deletes = [
        e for e in conn.events
        if e[0] == "execute" and e[1].lower().startswith("delete from auto_plan")
    ]
    assert len(deletes) == 2
