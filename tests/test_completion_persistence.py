"""Done completion batch: load_completion_state + atomic commit + one-trip mark_mode_seen."""

from __future__ import annotations

import inspect
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path
from uuid import UUID

import pytest

from constitution_memorizer.learning.schemas import LearningUnitsDocument
from constitution_memorizer.progress.db import open_progress_db
from constitution_memorizer.progress.postgres_repository import (
    PostgresProgressRepository,
    _COMMIT_COMPLETION_SQL,
    _MARK_MODE_SEEN_SQL,
)
from constitution_memorizer.progress.repository import (
    LEARN_MODES,
    CompletionProgress,
    ProgressRepository,
)
from constitution_memorizer.progress.scheduler import (
    DEFAULT_EASE_FACTOR,
    ModesIncompleteError,
    ReminderEngine,
)
from constitution_memorizer.progress.user_ids import LOCAL_USER_ID
from constitution_memorizer.utils.json_io import read_json
from constitution_memorizer.web.app import create_app

from tests.quiz_helpers import complete_all_modes
from fastapi.testclient import TestClient

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
USER = UUID("11111111-1111-4111-8111-111111111111")


class CountingProgressRepo:
    def __init__(self, inner: ProgressRepository) -> None:
        self.inner = inner
        self.load_completion_state_calls = 0
        self.commit_completion_calls = 0
        self.ensure_progress_calls = 0
        self.list_all_progress_calls = 0
        self.modes_complete_calls = 0
        self.modes_seen_calls = 0
        self.upsert_progress_calls = 0
        self.clear_modes_seen_calls = 0
        self.get_progress_calls = 0

    def __getattr__(self, name: str):
        return getattr(self.inner, name)

    def load_completion_state(self, user_id, unit_id: str):
        self.load_completion_state_calls += 1
        return self.inner.load_completion_state(user_id, unit_id)

    def commit_completion(self, user_id, unit_id: str, progress, **kwargs):
        self.commit_completion_calls += 1
        return self.inner.commit_completion(user_id, unit_id, progress, **kwargs)

    def ensure_progress(self, user_id, unit_id: str):
        self.ensure_progress_calls += 1
        return self.inner.ensure_progress(user_id, unit_id)

    def list_all_progress(self, user_id):
        self.list_all_progress_calls += 1
        return self.inner.list_all_progress(user_id)

    def modes_complete(self, user_id, unit_id: str):
        self.modes_complete_calls += 1
        return self.inner.modes_complete(user_id, unit_id)

    def modes_seen(self, user_id, unit_id: str):
        self.modes_seen_calls += 1
        return self.inner.modes_seen(user_id, unit_id)

    def upsert_progress(self, user_id, **kwargs):
        self.upsert_progress_calls += 1
        return self.inner.upsert_progress(user_id, **kwargs)

    def clear_modes_seen(self, user_id, unit_id: str):
        self.clear_modes_seen_calls += 1
        return self.inner.clear_modes_seen(user_id, unit_id)

    def get_progress(self, user_id, unit_id: str):
        self.get_progress_calls += 1
        return self.inner.get_progress(user_id, unit_id)


def _catalog() -> dict:
    doc = LearningUnitsDocument.model_validate(read_json(MINI_UNITS))
    return {u.id: u for u in doc.units}


def _engine(tmp_path: Path) -> tuple[CountingProgressRepo, ReminderEngine]:
    conn = open_progress_db(tmp_path / "progress.db")
    repo = CountingProgressRepo(ProgressRepository(conn))
    return repo, ReminderEngine.from_repository(repo, _catalog())


def _see_all(engine: ReminderEngine, unit_id: str) -> None:
    for mode in LEARN_MODES:
        engine.mark_mode_seen(unit_id, mode)


def test_complete_done_uses_one_load_and_one_commit(tmp_path: Path):
    repo, engine = _engine(tmp_path)
    _see_all(engine, "clause-1")
    repo.load_completion_state_calls = 0
    repo.commit_completion_calls = 0
    result = engine.mark_done("clause-1", as_of=date(2026, 8, 15))
    assert result.progress.status == "review"
    assert repo.load_completion_state_calls == 1
    assert repo.commit_completion_calls == 1
    assert repo.ensure_progress_calls == 0
    assert repo.list_all_progress_calls == 0
    assert repo.modes_complete_calls == 0
    assert repo.modes_seen_calls == 0
    assert repo.upsert_progress_calls == 0
    assert repo.clear_modes_seen_calls == 0


def test_incomplete_done_loads_once_and_does_not_commit(tmp_path: Path):
    repo, engine = _engine(tmp_path)
    engine.mark_mode_seen("clause-1", "read")
    repo.load_completion_state_calls = 0
    with pytest.raises(ModesIncompleteError) as exc:
        engine.mark_done("clause-1", as_of=date(2026, 8, 15))
    assert exc.value.seen == frozenset({"read"})
    assert repo.load_completion_state_calls == 1
    assert repo.commit_completion_calls == 0
    assert repo.modes_seen_calls == 0


def test_incomplete_done_rejects_incomparable_extra_mode(tmp_path: Path):
    repo, engine = _engine(tmp_path)
    uid = str(LOCAL_USER_ID)
    for mode in ("read", "unexpected-mode"):
        repo.inner.conn.execute(
            """
            INSERT INTO unit_modes_seen (user_id, learning_unit_id, mode, seen_at)
            VALUES (?, ?, ?, ?)
            """,
            (uid, "clause-1", mode, "2026-08-15T00:00:00+00:00"),
        )
    repo.inner.conn.commit()
    with pytest.raises(ModesIncompleteError) as exc:
        engine.mark_done("clause-1", as_of=date(2026, 8, 15))
    assert exc.value.seen == frozenset({"read", "unexpected-mode"})
    assert repo.commit_completion_calls == 0


def test_non_mastered_done_resets_ease_factor_to_default(tmp_path: Path):
    repo, engine = _engine(tmp_path)
    repo.inner.upsert_progress(
        LOCAL_USER_ID,
        unit_id="clause-1",
        status="review",
        times_completed=1,
        last_completed=date(2026, 8, 1),
        next_revision=date(2026, 8, 15),
        interval_days=1,
        ease_factor=1.8,
    )
    _see_all(engine, "clause-1")
    result = engine.mark_done("clause-1", as_of=date(2026, 8, 15))
    assert result.progress.ease_factor == DEFAULT_EASE_FACTOR
    stored = repo.inner.get_progress(LOCAL_USER_ID, "clause-1")
    assert stored is not None
    assert stored.ease_factor == DEFAULT_EASE_FACTOR


def test_incomplete_done_http_redirect_unchanged(tmp_path: Path):
    client = TestClient(
        create_app(units_path=MINI_UNITS, db_path=tmp_path / "progress.db")
    )
    resp = client.post("/learn/clause-1/done", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/learn/clause-1"


def test_first_ever_done_uses_existing_ladder_math(tmp_path: Path):
    repo, engine = _engine(tmp_path)
    _see_all(engine, "clause-1")
    today = date(2026, 8, 15)
    result = engine.mark_done("clause-1", as_of=today)
    assert result.progress.status == "review"
    assert result.progress.times_completed == 1
    assert result.progress.interval_days == 1
    assert result.progress.next_revision == today + timedelta(days=1)
    assert result.progress.ease_factor == 2.5
    assert result.progress.created_at
    assert result.progress.updated_at
    stored = repo.inner.get_progress(LOCAL_USER_ID, "clause-1")
    assert stored is not None
    assert stored.status == "review"
    assert stored.times_completed == 1
    assert repo.ensure_progress_calls == 0


def test_sqlite_commit_completion_is_one_transaction():
    source = inspect.getsource(ProgressRepository.commit_completion)
    assert "upsert_progress" not in source
    assert "clear_modes_seen" not in source
    assert "rollback" in source
    assert "commit()" in source


def test_mark_mode_seen_union_new_and_existing(tmp_path: Path):
    conn = open_progress_db(tmp_path / "progress.db")
    repo = ProgressRepository(conn)
    first = repo.mark_mode_seen(LOCAL_USER_ID, "clause-1", "read")
    assert first == {"read"}
    second = repo.mark_mode_seen(LOCAL_USER_ID, "clause-1", "cloze")
    assert second == {"read", "cloze"}
    again = repo.mark_mode_seen(LOCAL_USER_ID, "clause-1", "cloze")
    assert again == {"read", "cloze"}
    added = repo.mark_mode_seen(LOCAL_USER_ID, "clause-1", "letters")
    assert added == {"read", "cloze", "letters"}


def test_postgres_mark_mode_seen_sql_uses_union_returning():
    assert "UNION" in _MARK_MODE_SEEN_SQL
    assert "FROM touched" in _MARK_MODE_SEEN_SQL
    assert "RETURNING mode" in _MARK_MODE_SEEN_SQL


def test_done_uses_split_prefs_from_snapshot(tmp_path: Path):
    client = TestClient(
        create_app(units_path=MINI_UNITS, db_path=tmp_path / "progress.db")
    )
    complete_all_modes(client, MINI_UNITS, "clause-1")
    resp = client.post("/learn/clause-1/done", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/learn/clause-2/choose?done=clause-1"


def test_lean_store_progress_does_not_load_all(tmp_path: Path):
    repo, engine = _engine(tmp_path)
    assert engine._progress_cache is None
    _see_all(engine, "clause-1")
    repo.list_all_progress_calls = 0
    engine.mark_done("clause-1", as_of=date(2026, 8, 15))
    assert engine._progress_cache is None
    assert repo.list_all_progress_calls == 0


class _FakeCursor:
    def __init__(self, conn: "_FakeConnection") -> None:
        self.conn = conn
        self.closed = False
        self._kind: str | None = None

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, *exc: object) -> None:
        self.closed = True

    def execute(self, sql: str, params=None) -> None:
        self.conn.events.append(("execute", sql, params))
        text = " ".join(sql.split()).lower()
        if "union" in text and "touched" in text:
            self._kind = "modes_write"
        elif "with upserted" in text or "delete from unit_modes_seen" in text and "upserted" in text:
            self._kind = "commit"
        elif "learning_unit_progress" in text:
            self._kind = "progress"
        elif "unit_modes_seen" in text:
            self._kind = "modes"
        elif "split_preference" in text:
            self._kind = "split"
        else:
            self._kind = "other"

    def fetchall(self):
        self.conn.events.append(("fetchall", self._kind))
        return list(self.conn.results.get(self._kind, []))

    def fetchone(self):
        self.conn.events.append(("fetchone", self._kind))
        rows = self.conn.results.get(self._kind, [])
        return rows[0] if rows else None


class _FakeConnection:
    def __init__(self, results: dict[str, list]) -> None:
        self.results = results
        self.events: list[tuple] = []
        self.cursors: list[_FakeCursor] = []
        self.pipeline_entries = 0

    def cursor(self, row_factory=None):
        cur = _FakeCursor(self)
        self.cursors.append(cur)
        return cur

    @contextmanager
    def pipeline(self):
        self.pipeline_entries += 1
        self.events.append(("pipeline_enter",))
        yield
        self.events.append(("pipeline_exit",))

    def commit(self) -> None:
        self.events.append(("commit",))

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


def _progress_row() -> dict:
    return {
        "learning_unit_id": "clause-1",
        "status": "review",
        "times_completed": 1,
        "last_completed": date(2026, 8, 15),
        "next_revision": date(2026, 8, 16),
        "interval_days": 1,
        "ease_factor": 2.5,
        "created_at": "2026-08-15T00:00:00+00:00",
        "updated_at": "2026-08-15T00:00:00+00:00",
    }


def test_postgres_load_completion_state_pipelines_three_selects(
    monkeypatch: pytest.MonkeyPatch,
):
    conn = _FakeConnection(
        {
            "progress": [_progress_row()],
            "modes": [{"mode": "read"}, {"mode": "cloze"}],
            "split": [{"parent_clause_id": "clause-2", "mode": "letters"}],
        }
    )
    pool = _FakePool(conn)
    monkeypatch.setattr(
        "constitution_memorizer.progress.postgres_repository._pipeline_supported",
        lambda: True,
    )
    repo = PostgresProgressRepository(pool)
    state = repo.load_completion_state(USER, "clause-1")
    assert pool.borrows == 1
    assert conn.pipeline_entries == 1
    kinds = [event[0] for event in conn.events]
    first_fetch = next(i for i, kind in enumerate(kinds) if kind in {"fetchall", "fetchone"})
    assert kinds[:first_fetch].count("execute") == 3
    assert "fetchall" not in kinds[:first_fetch]
    assert "fetchone" not in kinds[:first_fetch]
    assert state.progress is not None
    assert state.progress.learning_unit_id == "clause-1"
    assert state.modes_seen == {"read", "cloze"}
    assert state.split_preferences == {"clause-2": "letters"}
    assert all(cur.closed for cur in conn.cursors)


def test_postgres_commit_completion_is_one_execute(monkeypatch: pytest.MonkeyPatch):
    conn = _FakeConnection({"commit": [_progress_row()]})
    pool = _FakePool(conn)
    monkeypatch.setattr(
        "constitution_memorizer.progress.postgres_repository._pipeline_supported",
        lambda: True,
    )
    repo = PostgresProgressRepository(pool)
    record = repo.commit_completion(
        USER,
        "clause-1",
        CompletionProgress(
            status="review",
            times_completed=1,
            last_completed=date(2026, 8, 15),
            next_revision=date(2026, 8, 16),
            interval_days=1,
            ease_factor=2.5,
        ),
    )
    assert pool.borrows == 1
    executes = [event for event in conn.events if event[0] == "execute"]
    assert len(executes) == 1
    assert "SELECT * FROM upserted" in _COMMIT_COMPLETION_SQL
    assert "DELETE FROM unit_modes_seen" in _COMMIT_COMPLETION_SQL
    assert record.learning_unit_id == "clause-1"
    assert record.status == "review"


def test_postgres_mark_mode_seen_one_execute_returns_full_set(
    monkeypatch: pytest.MonkeyPatch,
):
    conn = _FakeConnection(
        {"modes_write": [{"mode": "read"}, {"mode": "cloze"}, {"mode": "letters"}]}
    )
    pool = _FakePool(conn)
    repo = PostgresProgressRepository(pool)
    seen = repo.mark_mode_seen(USER, "clause-1", "letters")
    executes = [event for event in conn.events if event[0] == "execute"]
    assert len(executes) == 1
    assert "FROM touched" in executes[0][1]
    assert seen == {"read", "cloze", "letters"}
    assert pool.borrows == 1
