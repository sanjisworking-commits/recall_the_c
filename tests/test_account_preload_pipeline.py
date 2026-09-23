"""Phase 5 (request latency): the mutation-path account preload issues its two
independent reads (backfill flag + claimed Articles) in one pipelined round
trip on Postgres, with a sequential fallback where pipelines are unsupported.
"""

from __future__ import annotations

from contextlib import contextmanager
from uuid import UUID

from constitution_memorizer.progress.postgres_repository import (
    PostgresProgressRepository,
)

USER = UUID("11111111-1111-4111-8111-111111111111")


class _FakeCursor:
    def __init__(self, conn: "_FakeConn") -> None:
        self.conn = conn
        self._kind: str | None = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None

    def execute(self, sql: str, params=None):
        text = " ".join(sql.split()).lower()
        self.conn.events.append(("execute", text))
        self._kind = "flag" if "app_settings" in text else "claims"

    def fetchone(self):
        self.conn.events.append(("fetchone", self._kind))
        return {"value": "1"} if self._kind == "flag" else None

    def fetchall(self):
        self.conn.events.append(("fetchall", self._kind))
        return [{"article_number": "20"}] if self._kind == "claims" else []


class _FakeConn:
    def __init__(self) -> None:
        self.events: list[tuple] = []
        self.pipeline_entries = 0

    def cursor(self, row_factory=None):
        return _FakeCursor(self)

    @contextmanager
    def pipeline(self):
        self.pipeline_entries += 1
        yield

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None


class _FakePool:
    def __init__(self, conn: _FakeConn) -> None:
        self.conn = conn
        self.borrows = 0

    @contextmanager
    def connection(self):
        self.borrows += 1
        yield self.conn


def _repo(monkeypatch, *, pipeline: bool):
    conn = _FakeConn()
    monkeypatch.setattr(
        "constitution_memorizer.progress.postgres_repository._pipeline_capability",
        lambda: (pipeline, None if pipeline else "is_supported_false"),
    )
    return PostgresProgressRepository(_FakePool(conn)), conn


def _executes_before_first_fetch(conn: _FakeConn) -> int:
    count = 0
    for kind, *_ in conn.events:
        if kind == "execute":
            count += 1
        elif kind in {"fetchone", "fetchall"}:
            break
    return count


def test_account_preload_pipelines_two_reads(monkeypatch):
    repo, conn = _repo(monkeypatch, pipeline=True)

    preload = repo.load_account_preload(USER)

    assert conn.pipeline_entries == 1
    assert _executes_before_first_fetch(conn) == 2
    assert preload.backfilled is True
    assert preload.claimed_articles == frozenset({"20"})


def test_account_preload_falls_back_without_pipeline(monkeypatch):
    repo, conn = _repo(monkeypatch, pipeline=False)

    preload = repo.load_account_preload(USER)

    assert conn.pipeline_entries == 0
    assert _executes_before_first_fetch(conn) == 2
    assert preload.backfilled is True
    assert preload.claimed_articles == frozenset({"20"})


# ── LearnMutationPreload: settings + progress + claims + override in 1 round trip


class _MutationCursor:
    def __init__(self, conn: "_MutationConn") -> None:
        self.conn = conn
        self._kind: str | None = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None

    def execute(self, sql, params=None):
        text = " ".join(str(sql).split()).lower()
        self.conn.events.append(("execute", text))
        if "app_settings" in text:
            self._kind = "settings"
        elif "learning_unit_progress" in text:
            self._kind = "progress"
        elif "user_free_articles" in text:
            self._kind = "claims"
        else:
            self._kind = "override"

    def fetchone(self):
        self.conn.events.append(("fetchone", self._kind))
        # Only the override query fetchone()s here.
        return {"is_admin": False, "grant_id": None, "source": None,
                "starts_at": None, "ends_at": None}

    def fetchall(self):
        self.conn.events.append(("fetchall", self._kind))
        if self._kind == "settings":
            return [{"key": "user_timezone", "value": "Asia/Kolkata"}]
        if self._kind == "claims":
            return [{"article_number": "20"}]
        return []  # progress


class _MutationConn:
    def __init__(self) -> None:
        self.events: list[tuple] = []
        self.pipeline_entries = 0

    def cursor(self, row_factory=None):
        return _MutationCursor(self)

    @contextmanager
    def pipeline(self):
        self.pipeline_entries += 1
        yield

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None


class _MutationPool:
    def __init__(self, conn: _MutationConn) -> None:
        self.conn = conn

    @contextmanager
    def connection(self):
        yield self.conn


def test_learn_mutation_preload_pipelines_four_reads(monkeypatch):
    from datetime import datetime, timezone

    conn = _MutationConn()
    monkeypatch.setattr(
        "constitution_memorizer.progress.postgres_repository._pipeline_capability",
        lambda: (True, None),
    )
    repo = PostgresProgressRepository(_MutationPool(conn))

    bundle = repo.load_learn_mutation_preload(
        USER, now=datetime(2026, 9, 21, tzinfo=timezone.utc)
    )

    assert conn.pipeline_entries == 1
    # All four independent SELECTs are queued before any result is read.
    kinds = [e[0] for e in conn.events]
    first_fetch = next(i for i, k in enumerate(kinds) if k in {"fetchall", "fetchone"})
    assert kinds[:first_fetch].count("execute") == 4
    assert bundle.settings == {"user_timezone": "Asia/Kolkata"}
    assert bundle.claimed_articles == frozenset({"20"})
    assert bundle.access_override.is_admin is False
