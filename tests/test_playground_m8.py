"""Milestone 8: Learned → revision ladder → Mastered.

M7 six-mode rows stay lifetime evidence. M8 adds Learned scheduling and a
separate per-rung revision-mode table. Official ladder is 1 → 3 → 7 → 15 → 30 → 60.
"""

from __future__ import annotations

import ast
import inspect
import sqlite3
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from alembic.config import Config
from alembic.script import ScriptDirectory

from constitution_memorizer.playground.db import SCHEMA_SQL, ensure_sqlite_schema
from constitution_memorizer.playground.learning.modes import PLAYGROUND_LEARN_MODES
from constitution_memorizer.playground.lifecycle import (
    StaleRevisionError,
    days_overdue,
    overdue_label,
)
from constitution_memorizer.playground.postgres import PostgresPlaygroundRepository
from constitution_memorizer.playground.repository import SqlitePlaygroundRepository
from constitution_memorizer.playground.revision import INTERVAL_LADDER, advance_interval
from constitution_memorizer.playground.roster.period import playground_today
from constitution_memorizer.playground.urls import (
    law_path,
    learn_complete_path,
    learn_path,
    remove_path,
)
from constitution_memorizer.progress.user_ids import LOCAL_USER_ID
from tests.test_playground import _add_and_select, _client, _sqlite_repo
from tests.test_playground_m7 import _json_post
from tests.test_roster_m5a import (
    USER,
    _authed_client,
    _confirm_add,
    _csrf,
    _hydrate_spy,
    _subscribe,
)

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_HEAD = "20260925_0026"
MODES = PLAYGROUND_LEARN_MODES
TODAY = date(2026, 9, 25)


def _seed_progress(
    repo: SqlitePlaygroundRepository,
    user_id,
    law_id: str,
    locator: str,
    *,
    status: str,
    interval_days: int,
    next_revision: str | None,
    times_completed: int = 0,
    learned_at: str | None = None,
    last_completed: str | None = None,
    cloze_done: int = 0,
) -> None:
    now = "2026-09-25T00:00:00+00:00"
    repo.conn.execute(
        """
        INSERT INTO user_playground_progress (
            user_id, law_id, source_locator, status, cloze_done,
            times_completed, last_completed, next_revision, interval_days,
            source_version, source_hash, updated_at, learned_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'v', 'h', ?, ?)
        ON CONFLICT (user_id, law_id, source_locator) DO UPDATE SET
            status = excluded.status,
            times_completed = excluded.times_completed,
            last_completed = excluded.last_completed,
            next_revision = excluded.next_revision,
            interval_days = excluded.interval_days,
            learned_at = excluded.learned_at,
            cloze_done = excluded.cloze_done
        """,
        (
            str(user_id),
            law_id,
            locator,
            status,
            cloze_done,
            times_completed,
            last_completed,
            next_revision,
            interval_days,
            now,
            learned_at,
        ),
    )
    repo.conn.commit()


def _complete_six(repo, user_id, law_id, locator, *, as_of: date) -> None:
    for mode in MODES:
        repo.complete_mode(
            user_id,
            law_id,
            locator,
            mode,
            source_version="v",
            source_hash="h",
            as_of=as_of,
        )


def _complete_rung(repo, user_id, law_id, locator, rung: int, *, as_of: date) -> None:
    for mode in MODES:
        repo.complete_revision_mode_and_advance_if_ready(
            user_id,
            law_id,
            locator,
            mode,
            source_version="v",
            source_hash="h",
            as_of=as_of,
            claimed_rung=rung,
        )


def test_alembic_0026_parent_one_head_rls_and_sqlite_parity():
    cfg = Config(str(ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(cfg)
    assert script.get_heads() == [EXPECTED_HEAD]
    rev = script.get_revision(EXPECTED_HEAD)
    assert rev.down_revision == "20260924_0025"
    path = ROOT / "alembic" / "versions" / "20260925_0026_playground_revision_lifecycle.py"
    text = path.read_text(encoding="utf-8")
    ast.parse(text, filename=str(path))
    assert "learned_at" in text
    assert "user_playground_revision_mode_progress" in text
    assert "PRIMARY KEY (user_id, law_id, source_locator, rung_days, mode)" in text
    assert "1, 3, 7, 15, 30, 60" in text
    assert "ENABLE ROW LEVEL SECURITY" in text
    assert "user_playground_progress_due" in text
    assert "learned_at" in SCHEMA_SQL
    assert "user_playground_revision_mode_progress" in SCHEMA_SQL
    assert "CHECK (rung_days IN (1, 3, 7, 15, 30, 60))" in SCHEMA_SQL
    parent = ROOT / "alembic" / "versions" / "20260924_0025_playground_mode_progress.py"
    assert "learned_at" not in parent.read_text(encoding="utf-8")


def test_official_ladder_keeps_day_15():
    assert INTERVAL_LADDER == (1, 3, 7, 15, 30, 60)
    assert advance_interval(7) == 15
    assert advance_interval(15) == 30
    assert advance_interval(60) is None


def test_zero_and_five_modes_are_not_learned(tmp_path: Path):
    repo = _sqlite_repo(tmp_path)
    repo.add_item(LOCAL_USER_ID, "ndps", source_version="v", law_source_hash="t")
    loc = "ndps:section:8"
    assert repo.get_progress(LOCAL_USER_ID, "ndps", loc) is None
    for mode in MODES[:5]:
        repo.complete_mode(
            LOCAL_USER_ID, "ndps", loc, mode, source_version="v", source_hash="h", as_of=TODAY
        )
    assert repo.get_progress(LOCAL_USER_ID, "ndps", loc) is None
    modes = repo.list_mode_progress(LOCAL_USER_ID, "ndps", loc)
    assert {row.mode for row in modes if row.status == "completed"} == set(MODES[:5])


def test_six_modes_become_learned_with_day1_tomorrow(tmp_path: Path):
    repo = _sqlite_repo(tmp_path)
    repo.add_item(LOCAL_USER_ID, "ndps", source_version="v", law_source_hash="t")
    loc = "ndps:section:8"
    _complete_six(repo, LOCAL_USER_ID, "ndps", loc, as_of=TODAY)
    row = repo.get_progress(LOCAL_USER_ID, "ndps", loc)
    assert row is not None
    assert row.status == "learned"
    assert row.learned_at == TODAY.isoformat()
    assert row.times_completed == 0
    assert row.last_completed is None
    assert row.interval_days == 1
    assert row.next_revision == (TODAY + timedelta(days=1)).isoformat()
    assert row.next_revision != TODAY.isoformat()


def test_learned_transition_is_idempotent(tmp_path: Path):
    repo = _sqlite_repo(tmp_path)
    repo.add_item(LOCAL_USER_ID, "ndps", source_version="v", law_source_hash="t")
    loc = "ndps:section:8"
    _complete_six(repo, LOCAL_USER_ID, "ndps", loc, as_of=TODAY)
    first = repo.get_progress(LOCAL_USER_ID, "ndps", loc)
    repo.complete_mode(
        LOCAL_USER_ID, "ndps", loc, "read", source_version="v", source_hash="h", as_of=TODAY
    )
    second = repo.get_progress(LOCAL_USER_ID, "ndps", loc)
    assert first is not None and second is not None
    assert second.status == "learned"
    assert second.learned_at == first.learned_at
    assert second.next_revision == first.next_revision
    assert second.times_completed == 0


def test_practice_before_day1_does_not_advance(tmp_path: Path):
    repo = _sqlite_repo(tmp_path)
    repo.add_item(LOCAL_USER_ID, "ndps", source_version="v", law_source_hash="t")
    loc = "ndps:section:8"
    _complete_six(repo, LOCAL_USER_ID, "ndps", loc, as_of=TODAY)
    with pytest.raises(Exception):
        _complete_rung(repo, LOCAL_USER_ID, "ndps", loc, 1, as_of=TODAY)
    row = repo.get_progress(LOCAL_USER_ID, "ndps", loc)
    assert row is not None
    assert row.interval_days == 1
    assert row.times_completed == 0
    assert row.status == "learned"


def test_every_rung_including_day15_and_mastered(tmp_path: Path):
    repo = _sqlite_repo(tmp_path)
    repo.add_item(LOCAL_USER_ID, "ndps", source_version="v", law_source_hash="t")
    loc = "ndps:section:8"
    _complete_six(repo, LOCAL_USER_ID, "ndps", loc, as_of=TODAY)
    cursor = TODAY + timedelta(days=1)
    expected = [
        (1, "review", 1, 3),
        (3, "review", 2, 7),
        (7, "review", 3, 15),
        (15, "review", 4, 30),
        (30, "review", 5, 60),
    ]
    for rung, status, times, nxt_interval in expected:
        _complete_rung(repo, LOCAL_USER_ID, "ndps", loc, rung, as_of=cursor)
        row = repo.get_progress(LOCAL_USER_ID, "ndps", loc)
        assert row.status == status
        assert row.times_completed == times
        assert row.interval_days == nxt_interval
        assert row.last_completed == cursor.isoformat()
        assert row.next_revision == (cursor + timedelta(days=nxt_interval)).isoformat()
        if rung == 7:
            assert nxt_interval == 15
        cursor = date.fromisoformat(row.next_revision)
    _complete_rung(repo, LOCAL_USER_ID, "ndps", loc, 60, as_of=cursor)
    done = repo.get_progress(LOCAL_USER_ID, "ndps", loc)
    assert done.status == "mastered"
    assert done.times_completed == 6
    assert done.interval_days == 60
    assert done.next_revision is None
    assert done.last_completed == cursor.isoformat()


def test_overdue_advances_one_rung_and_reanchors(tmp_path: Path):
    repo = _sqlite_repo(tmp_path)
    repo.add_item(LOCAL_USER_ID, "ndps", source_version="v", law_source_hash="t")
    loc = "ndps:section:8"
    due = TODAY - timedelta(days=20)
    _seed_progress(
        repo,
        LOCAL_USER_ID,
        "ndps",
        loc,
        status="review",
        interval_days=7,
        next_revision=due.isoformat(),
        times_completed=3,
        learned_at="2026-08-01",
    )
    _complete_rung(repo, LOCAL_USER_ID, "ndps", loc, 7, as_of=TODAY)
    row = repo.get_progress(LOCAL_USER_ID, "ndps", loc)
    assert row.interval_days == 15
    assert row.times_completed == 4
    assert row.next_revision == (TODAY + timedelta(days=15)).isoformat()
    assert row.status == "review"


def test_stale_rung_returns_conflict(tmp_path: Path):
    repo = _sqlite_repo(tmp_path)
    repo.add_item(LOCAL_USER_ID, "ndps", source_version="v", law_source_hash="t")
    loc = "ndps:section:8"
    _seed_progress(
        repo,
        LOCAL_USER_ID,
        "ndps",
        loc,
        status="review",
        interval_days=7,
        next_revision=TODAY.isoformat(),
        times_completed=3,
    )
    with pytest.raises(StaleRevisionError):
        repo.complete_revision_mode_and_advance_if_ready(
            LOCAL_USER_ID,
            "ndps",
            loc,
            "read",
            source_version="v",
            source_hash="h",
            as_of=TODAY,
            claimed_rung=3,
        )
    row = repo.get_progress(LOCAL_USER_ID, "ndps", loc)
    assert row.interval_days == 7


def test_duplicate_revision_mode_does_not_double_advance(tmp_path: Path):
    repo = _sqlite_repo(tmp_path)
    repo.add_item(LOCAL_USER_ID, "ndps", source_version="v", law_source_hash="t")
    loc = "ndps:section:8"
    _seed_progress(
        repo,
        LOCAL_USER_ID,
        "ndps",
        loc,
        status="learned",
        interval_days=1,
        next_revision=TODAY.isoformat(),
        times_completed=0,
        learned_at="2026-09-24",
    )
    for mode in MODES[:5]:
        repo.complete_revision_mode_and_advance_if_ready(
            LOCAL_USER_ID, "ndps", loc, mode, source_version="v", source_hash="h",
            as_of=TODAY, claimed_rung=1,
        )
    repo.complete_revision_mode_and_advance_if_ready(
        LOCAL_USER_ID, "ndps", loc, "test", source_version="v", source_hash="h",
        as_of=TODAY, claimed_rung=1,
    )
    first = repo.get_progress(LOCAL_USER_ID, "ndps", loc)
    repo.complete_revision_mode_and_advance_if_ready(
        LOCAL_USER_ID, "ndps", loc, "test", source_version="v", source_hash="h",
        as_of=TODAY, claimed_rung=1,
    )
    second = repo.get_progress(LOCAL_USER_ID, "ndps", loc)
    assert first.times_completed == 1
    assert second.times_completed == 1
    assert second.interval_days == 3
    test_row = repo.get_revision_mode_progress(LOCAL_USER_ID, "ndps", loc, 1, "test")
    assert test_row.status == "completed"
    assert test_row.attempt_count == 2


def test_initial_mode_history_survives_revision(tmp_path: Path):
    repo = _sqlite_repo(tmp_path)
    repo.add_item(LOCAL_USER_ID, "ndps", source_version="v", law_source_hash="t")
    loc = "ndps:section:8"
    _complete_six(repo, LOCAL_USER_ID, "ndps", loc, as_of=TODAY)
    _complete_rung(repo, LOCAL_USER_ID, "ndps", loc, 1, as_of=TODAY + timedelta(days=1))
    initial = {row.mode for row in repo.list_mode_progress(LOCAL_USER_ID, "ndps", loc)}
    rev = repo.list_revision_mode_progress(LOCAL_USER_ID, "ndps", loc, 1)
    assert initial == set(MODES)
    assert {row.mode for row in rev} == set(MODES)


def test_roster_remove_does_not_reset_ladder(tmp_path: Path):
    repo = _sqlite_repo(tmp_path)
    repo.add_item(LOCAL_USER_ID, "ndps", source_version="v", law_source_hash="t")
    loc = "ndps:section:8"
    _complete_six(repo, LOCAL_USER_ID, "ndps", loc, as_of=TODAY)
    _complete_rung(repo, LOCAL_USER_ID, "ndps", loc, 1, as_of=TODAY + timedelta(days=1))
    before = repo.get_progress(LOCAL_USER_ID, "ndps", loc)
    modes = repo.list_mode_progress(LOCAL_USER_ID, "ndps", loc)
    rev = repo.list_revision_mode_progress(LOCAL_USER_ID, "ndps", loc)
    repo.replace_selection(LOCAL_USER_ID, "ndps", [])
    after = repo.get_progress(LOCAL_USER_ID, "ndps", loc)
    assert after.status == before.status
    assert after.times_completed == before.times_completed
    assert after.next_revision == before.next_revision
    assert after.interval_days == 3
    assert repo.list_mode_progress(LOCAL_USER_ID, "ndps", loc) == modes
    assert repo.list_revision_mode_progress(LOCAL_USER_ID, "ndps", loc) == rev


def test_legacy_review_and_mastered_are_grandfathered(tmp_path: Path):
    repo = _sqlite_repo(tmp_path)
    loc = "ndps:section:8"
    repo.add_item(LOCAL_USER_ID, "ndps", source_version="v", law_source_hash="t")
    _seed_progress(
        repo,
        LOCAL_USER_ID,
        "ndps",
        loc,
        status="review",
        interval_days=7,
        next_revision=(TODAY + timedelta(days=2)).isoformat(),
        times_completed=3,
        learned_at=None,
        cloze_done=1,
    )
    row = repo.get_progress(LOCAL_USER_ID, "ndps", loc)
    assert row.status == "review"
    assert row.learned_at is None
    assert row.interval_days == 7
    repo.add_item(LOCAL_USER_ID, "bns", source_version="v", law_source_hash="t")
    _seed_progress(
        repo,
        LOCAL_USER_ID,
        "bns",
        "bns:section:1",
        status="mastered",
        interval_days=60,
        next_revision=None,
        times_completed=6,
        learned_at=None,
    )
    mastered = repo.get_progress(LOCAL_USER_ID, "bns", "bns:section:1")
    assert mastered.status == "mastered"
    assert mastered.next_revision is None


def test_progress_summary_lifecycle_counts(tmp_path: Path):
    repo = _sqlite_repo(tmp_path)
    uid = LOCAL_USER_ID
    repo.add_item(uid, "ndps", source_version="v", law_source_hash="t")
    locators = [f"ndps:section:{n}" for n in ("1", "2", "3", "4", "5")]
    repo.replace_selection(uid, "ndps", [(loc, "v", "h") for loc in locators])
    repo.complete_mode(uid, "ndps", locators[1], "read", source_version="v", source_hash="h", as_of=TODAY)
    repo.complete_mode(uid, "ndps", locators[1], "cloze", source_version="v", source_hash="h", as_of=TODAY)
    repo.complete_mode(uid, "ndps", locators[1], "letters", source_version="v", source_hash="h", as_of=TODAY)
    _seed_progress(
        repo, uid, "ndps", locators[2], status="learned", interval_days=1,
        next_revision=(TODAY + timedelta(days=1)).isoformat(), times_completed=0,
        learned_at=TODAY.isoformat(),
    )
    _seed_progress(
        repo, uid, "ndps", locators[3], status="review", interval_days=7,
        next_revision=TODAY.isoformat(), times_completed=3,
    )
    _seed_progress(
        repo, uid, "ndps", locators[4], status="mastered", interval_days=60,
        next_revision=None, times_completed=6,
    )
    summary = repo.list_playground_summaries(uid, as_of=TODAY, law_ids=["ndps"])[0]
    assert summary.selected_count == 5
    assert summary.learning_count == 1
    assert summary.learned_count == 2
    assert summary.due_count == 1
    assert summary.mastered_count == 1


def test_due_query_filters_inactive_laws(tmp_path: Path):
    repo = _sqlite_repo(tmp_path)
    uid = LOCAL_USER_ID
    for law_id in ("ndps", "bns", "bnss"):
        repo.add_item(uid, law_id, source_version="v", law_source_hash="t")
        loc = f"{law_id}:section:1"
        _seed_progress(
            repo, uid, law_id, loc, status="review", interval_days=3,
            next_revision=(TODAY - timedelta(days=2)).isoformat(), times_completed=2,
        )
    due = repo.list_due_revisions(uid, TODAY, ["ndps", "bns"])
    assert {row.law_id for row in due} == {"ndps", "bns"}
    assert repo.list_due_revisions(uid, TODAY, []) == []


def test_schedule_query_skips_mastered_and_inactive(tmp_path: Path):
    repo = _sqlite_repo(tmp_path)
    uid = LOCAL_USER_ID
    repo.add_item(uid, "ndps", source_version="v", law_source_hash="t")
    repo.add_item(uid, "bns", source_version="v", law_source_hash="t")
    repo.add_item(uid, "bnss", source_version="v", law_source_hash="t")
    _seed_progress(
        repo, uid, "ndps", "ndps:section:1", status="learned", interval_days=1,
        next_revision=(TODAY + timedelta(days=3)).isoformat(),
    )
    _seed_progress(
        repo, uid, "bns", "bns:section:1", status="mastered", interval_days=60,
        next_revision=None, times_completed=6,
    )
    _seed_progress(
        repo, uid, "bnss", "bnss:section:1", status="review", interval_days=7,
        next_revision=TODAY.isoformat(), times_completed=3,
    )
    rows = repo.list_revision_schedule(uid, TODAY, TODAY + timedelta(days=10), ["ndps", "bns"])
    assert [row.law_id for row in rows] == ["ndps"]
    assert rows[0].interval_days == 1


def test_overdue_label_helper():
    assert days_overdue(TODAY, TODAY) == 0
    assert days_overdue(TODAY - timedelta(days=1), TODAY) == 1
    assert overdue_label(0) == "Due today"
    assert overdue_label(1) == "1 day overdue"
    assert overdue_label(4) == "4 days overdue"


def test_kolkata_learned_date_not_utc(tmp_path: Path):
    repo = _sqlite_repo(tmp_path)
    repo.add_item(LOCAL_USER_ID, "ndps", source_version="v", law_source_hash="t")
    loc = "ndps:section:8"
    before = playground_today(datetime(2026, 9, 24, 18, 29, tzinfo=timezone.utc))
    after = playground_today(datetime(2026, 9, 24, 18, 30, tzinfo=timezone.utc))
    assert before == date(2026, 9, 24)
    assert after == date(2026, 9, 25)
    _complete_six(repo, LOCAL_USER_ID, "ndps", loc, as_of=after)
    row = repo.get_progress(LOCAL_USER_ID, "ndps", loc)
    assert row.learned_at == "2026-09-25"
    assert row.next_revision == "2026-09-26"


def test_learned_transition_race(tmp_path: Path):
    db = tmp_path / "race.db"
    conn = sqlite3.connect(db, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=8000")
    ensure_sqlite_schema(conn)
    repo = SqlitePlaygroundRepository(conn)
    repo.add_item(LOCAL_USER_ID, "ndps", source_version="v", law_source_hash="t")
    loc = "ndps:section:8"
    for mode in MODES[:5]:
        repo.complete_mode(
            LOCAL_USER_ID, "ndps", loc, mode, source_version="v", source_hash="h", as_of=TODAY
        )

    def _connect():
        c = sqlite3.connect(db, timeout=10, check_same_thread=False)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA busy_timeout=8000")
        return SqlitePlaygroundRepository(c)

    errors: list[BaseException] = []

    def worker():
        try:
            _connect().complete_mode(
                LOCAL_USER_ID, "ndps", loc, "test",
                source_version="v", source_hash="h", as_of=TODAY,
            )
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    rows = conn.execute(
        "SELECT status, learned_at, times_completed, interval_days FROM user_playground_progress"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["status"] == "learned"
    assert str(rows[0]["learned_at"])[:10] == TODAY.isoformat()
    assert int(rows[0]["times_completed"]) == 0
    assert int(rows[0]["interval_days"]) == 1


def test_revision_sixth_mode_race(tmp_path: Path):
    db = tmp_path / "race2.db"
    conn = sqlite3.connect(db, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=8000")
    ensure_sqlite_schema(conn)
    repo = SqlitePlaygroundRepository(conn)
    repo.add_item(LOCAL_USER_ID, "ndps", source_version="v", law_source_hash="t")
    loc = "ndps:section:8"
    _seed_progress(
        repo, LOCAL_USER_ID, "ndps", loc, status="review", interval_days=3,
        next_revision=TODAY.isoformat(), times_completed=1, learned_at="2026-09-20",
    )
    for mode in MODES[:5]:
        repo.complete_revision_mode_and_advance_if_ready(
            LOCAL_USER_ID, "ndps", loc, mode, source_version="v", source_hash="h",
            as_of=TODAY, claimed_rung=3,
        )

    def _connect():
        c = sqlite3.connect(db, timeout=10, check_same_thread=False)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA busy_timeout=8000")
        return SqlitePlaygroundRepository(c)

    errors: list[BaseException] = []

    def worker():
        try:
            _connect().complete_revision_mode_and_advance_if_ready(
                LOCAL_USER_ID, "ndps", loc, "test",
                source_version="v", source_hash="h", as_of=TODAY, claimed_rung=3,
            )
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    row = conn.execute(
        "SELECT times_completed, interval_days, next_revision FROM user_playground_progress"
    ).fetchone()
    assert int(row["times_completed"]) == 2
    assert int(row["interval_days"]) == 7
    assert str(row["next_revision"])[:10] == (TODAY + timedelta(days=7)).isoformat()


def test_postgres_uses_for_update_and_on_conflict():
    lock = inspect.getsource(PostgresPlaygroundRepository._lock_progress)
    learned = inspect.getsource(PostgresPlaygroundRepository._mark_learned_if_ready)
    sqlite_src = inspect.getsource(SqlitePlaygroundRepository._immediate)
    assert "FOR UPDATE" in lock
    assert "ON CONFLICT (user_id, law_id, source_locator) DO NOTHING" in learned
    assert "BEGIN IMMEDIATE" in sqlite_src


def test_workspace_learned_and_revise_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "constitution_memorizer.playground.routes.playground_today", lambda now=None: TODAY
    )
    client = _client(tmp_path)
    _add_and_select(client, "ndps", "1")
    loc = "ndps:section:1"
    repo = client.app.state.playground
    _complete_six(repo, LOCAL_USER_ID, "ndps", loc, as_of=TODAY)
    page = client.get(law_path("ndps"))
    assert "Learned" in page.text
    assert "First revision" in page.text
    assert "Day 1" in page.text
    _seed_progress(
        repo, LOCAL_USER_ID, "ndps", loc, status="review", interval_days=7,
        next_revision=TODAY.isoformat(), times_completed=3, learned_at=TODAY.isoformat(),
    )
    due = client.get(law_path("ndps"))
    assert "Due" in due.text
    assert "Revise" in due.text
    assert "Day 7" in due.text
    assert "Due today" in due.text
    assert "overdue" not in due.text.lower()
    _seed_progress(
        repo, LOCAL_USER_ID, "ndps", loc, status="review", interval_days=7,
        next_revision=(TODAY - timedelta(days=4)).isoformat(), times_completed=3,
        learned_at=TODAY.isoformat(),
    )
    overdue = client.get(law_path("ndps"))
    assert "4 days overdue" in overdue.text
    assert "Due today" not in overdue.text
    assert "Revise" in overdue.text


def test_revision_route_uses_server_rung(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "constitution_memorizer.playground.routes.playground_today", lambda now=None: TODAY
    )
    client = _client(tmp_path)
    _add_and_select(client, "ndps", "1")
    loc = "ndps:section:1"
    repo = client.app.state.playground
    _seed_progress(
        repo, LOCAL_USER_ID, "ndps", loc, status="review", interval_days=7,
        next_revision=TODAY.isoformat(), times_completed=3,
    )
    stale = _json_post(
        client,
        learn_complete_path("ndps", "1", "read"),
        {"revision": 1, "rung_days": 60},
    )
    assert stale.status_code == 409
    assert stale.json()["error"] == "stale_revision"
    ok = _json_post(
        client,
        learn_complete_path("ndps", "1", "read"),
        {"revision": 1, "rung_days": 7},
    )
    assert ok.status_code == 200
    page = client.get(learn_path("ndps", "1", "read", revision=True))
    assert page.status_code == 200
    assert "Revision · Day 7" in page.text


def test_today_queue_current_roster_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        "constitution_memorizer.playground.roster.period.playground_today",
        lambda now=None: TODAY,
    )
    monkeypatch.setattr(
        "constitution_memorizer.playground.schedule.playground_today",
        lambda now=None: TODAY,
    )
    client = _authed_client(tmp_path)
    _subscribe(client)
    for law_id in ("ndps", "bns", "bnss"):
        assert _confirm_add(client, law_id).status_code == 303
        client.post(
            f"/playground/laws/{law_id}/sections",
            data={**_csrf(client), "section": "1"},
            follow_redirects=False,
        )
    repo = client.app.state.playground
    _seed_progress(
        repo, USER, "ndps", "ndps:section:1", status="review", interval_days=1,
        next_revision=TODAY.isoformat(), times_completed=0,
    )
    _seed_progress(
        repo, USER, "bns", "bns:section:1", status="review", interval_days=3,
        next_revision=(TODAY - timedelta(days=4)).isoformat(), times_completed=1,
    )
    _seed_progress(
        repo, USER, "bnss", "bnss:section:1", status="review", interval_days=7,
        next_revision=(TODAY - timedelta(days=10)).isoformat(), times_completed=3,
    )
    client.post(
        "/playground/roster/bnss/remove",
        data=_csrf(client),
        follow_redirects=False,
    )
    from constitution_memorizer.web.bare_acts import clear_bare_act_cache

    hydrated = _hydrate_spy(monkeypatch)
    clear_bare_act_cache()
    hydrated.clear()
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert "Law revisions" in page.text
    block = page.text.split("Law revisions")[-1]
    assert "BNS" in block
    assert "NDPS" in block
    assert "BNSS" not in block
    assert block.find("BNS") < block.find("NDPS")
    assert "ndps" not in hydrated
    assert "bns" not in hydrated
    assert "bnss" not in hydrated
    still = repo.get_progress(USER, "bnss", "bnss:section:1")
    assert still.next_revision == (TODAY - timedelta(days=10)).isoformat()


def test_calendar_law_revision_chips(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "constitution_memorizer.playground.roster.period.playground_today",
        lambda now=None: TODAY,
    )
    client = _authed_client(tmp_path)
    _subscribe(client)
    assert _confirm_add(client, "ndps").status_code == 303
    client.post(
        "/playground/laws/ndps/sections",
        data={**_csrf(client), "section": "8"},
        follow_redirects=False,
    )
    repo = client.app.state.playground
    future = TODAY + timedelta(days=5)
    _seed_progress(
        repo, USER, "ndps", "ndps:section:8", status="review", interval_days=7,
        next_revision=future.isoformat(), times_completed=3,
    )
    _seed_progress(
        repo, USER, "ndps", "ndps:section:1", status="mastered", interval_days=60,
        next_revision=None, times_completed=6,
    )
    from constitution_memorizer.web.bare_acts import clear_bare_act_cache

    hydrated = _hydrate_spy(monkeypatch)
    clear_bare_act_cache()
    hydrated.clear()
    page = client.get(f"/calendar?year={future.year}&month={future.month}")
    assert page.status_code == 200
    assert "Law revision" in page.text or "Day 7 revision" in page.text
    assert "§8" in page.text or "Section 8" in page.text
    assert "ndps" not in hydrated


def test_http_remove_preserves_revision_state(tmp_path: Path):
    client = _authed_client(tmp_path)
    _subscribe(client)
    assert _confirm_add(client, "ndps").status_code == 303
    client.post(
        "/playground/laws/ndps/sections",
        data={**_csrf(client), "section": "1"},
        follow_redirects=False,
    )
    repo = client.app.state.playground
    loc = "ndps:section:1"
    _seed_progress(
        repo, USER, "ndps", loc, status="review", interval_days=3,
        next_revision=(TODAY + timedelta(days=1)).isoformat(), times_completed=1,
        learned_at=TODAY.isoformat(),
    )
    client.post("/playground/roster/ndps/remove", data=_csrf(client), follow_redirects=False)
    after = repo.get_progress(USER, "ndps", loc)
    assert after.interval_days == 3
    assert after.times_completed == 1
    assert after.status == "review"
    assert _confirm_add(client, "ndps").status_code == 303
    resumed = repo.get_progress(USER, "ndps", loc)
    assert resumed.interval_days == 3
    assert resumed.next_revision == after.next_revision


def test_subscription_expiry_does_not_reset(tmp_path: Path):
    client = _authed_client(tmp_path)
    sub = _subscribe(client)
    assert _confirm_add(client, "ndps").status_code == 303
    client.post(
        "/playground/laws/ndps/sections",
        data={**_csrf(client), "section": "1"},
        follow_redirects=False,
    )
    repo = client.app.state.playground
    loc = "ndps:section:1"
    _seed_progress(
        repo, USER, "ndps", loc, status="review", interval_days=7,
        next_revision=TODAY.isoformat(), times_completed=3,
    )
    client.app.state.subscriptions.update_subscription_state(USER, sub.id, status="expired")
    client.get(learn_path("ndps", "1", "read", revision=True), follow_redirects=False)
    client.app.state.subscriptions.mark_not_current(USER, sub.id)
    _subscribe(client, status="active")
    same = repo.get_progress(USER, "ndps", loc)
    assert same.interval_days == 7
    assert same.next_revision == TODAY.isoformat()


def test_device_revoke_does_not_touch_lifecycle(tmp_path: Path):
    client = _authed_client(tmp_path)
    _subscribe(client)
    assert _confirm_add(client, "ndps").status_code == 303
    client.post(
        "/playground/laws/ndps/sections",
        data={**_csrf(client), "section": "1"},
        follow_redirects=False,
    )
    repo = client.app.state.playground
    loc = "ndps:section:1"
    _seed_progress(
        repo, USER, "ndps", loc, status="review", interval_days=15,
        next_revision=TODAY.isoformat(), times_completed=4, learned_at="2026-09-01",
    )
    repo.complete_revision_mode_and_advance_if_ready(
        USER, "ndps", loc, "read", source_version="v", source_hash="h",
        as_of=TODAY, claimed_rung=15,
    )
    before = repo.get_progress(USER, "ndps", loc)
    modes = repo.list_mode_progress(USER, "ndps", loc)
    rev = repo.list_revision_mode_progress(USER, "ndps", loc)
    client.get("/playground")
    devices = client.app.state.device_service.list_devices(USER)
    active = [row for row in devices if not row.is_revoked]
    assert active
    client.app.state.device_service.revoke_device(USER, active[0].id)
    after = repo.get_progress(USER, "ndps", loc)
    assert after.status == before.status
    assert after.interval_days == 15
    assert after.times_completed == before.times_completed
    assert after.next_revision == before.next_revision
    assert repo.list_mode_progress(USER, "ndps", loc) == modes
    assert repo.list_revision_mode_progress(USER, "ndps", loc) == rev


def test_early_revision_http_does_not_advance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "constitution_memorizer.playground.routes.playground_today", lambda now=None: TODAY
    )
    client = _client(tmp_path)
    _add_and_select(client, "ndps", "1")
    loc = "ndps:section:1"
    repo = client.app.state.playground
    _seed_progress(
        repo, LOCAL_USER_ID, "ndps", loc, status="review", interval_days=7,
        next_revision=(TODAY + timedelta(days=1)).isoformat(), times_completed=3,
    )
    early = _json_post(
        client,
        learn_complete_path("ndps", "1", "read"),
        {"revision": 1, "rung_days": 7},
    )
    assert early.status_code == 409
    assert early.json()["error"] == "not_due"
    row = repo.get_progress(LOCAL_USER_ID, "ndps", loc)
    assert row.interval_days == 7
    assert row.times_completed == 3
    page = client.get(learn_path("ndps", "1", "read", revision=True))
    assert page.status_code == 200
    assert row.interval_days == repo.get_progress(LOCAL_USER_ID, "ndps", loc).interval_days


def test_get_does_not_advance_ladder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "constitution_memorizer.playground.routes.playground_today", lambda now=None: TODAY
    )
    client = _client(tmp_path)
    _add_and_select(client, "ndps", "1")
    loc = "ndps:section:1"
    repo = client.app.state.playground
    _seed_progress(
        repo, LOCAL_USER_ID, "ndps", loc, status="learned", interval_days=1,
        next_revision=TODAY.isoformat(), times_completed=0, learned_at="2026-09-24",
    )
    before = repo.get_progress(LOCAL_USER_ID, "ndps", loc)
    client.get(law_path("ndps"))
    client.get(learn_path("ndps", "1", "read", revision=True))
    after = repo.get_progress(LOCAL_USER_ID, "ndps", loc)
    assert after.interval_days == before.interval_days
    assert after.times_completed == 0
    assert after.next_revision == before.next_revision


def test_cloze_done_is_not_production_due_truth(tmp_path: Path):
    repo = _sqlite_repo(tmp_path)
    repo.add_item(LOCAL_USER_ID, "ndps", source_version="v", law_source_hash="t")
    loc = "ndps:section:8"
    repo.replace_selection(LOCAL_USER_ID, "ndps", [(loc, "v", "h")])
    _seed_progress(
        repo, LOCAL_USER_ID, "ndps", loc, status="learned", interval_days=1,
        next_revision=(TODAY + timedelta(days=1)).isoformat(), times_completed=0,
        cloze_done=1,
    )
    summary = repo.list_playground_summaries(LOCAL_USER_ID, as_of=TODAY, law_ids=["ndps"])[0]
    assert summary.due_count == 0
    assert summary.learned_count == 1


def test_m7_mode_registry_untouched():
    assert PLAYGROUND_LEARN_MODES == ("read", "cloze", "letters", "type", "recite", "test")
    routes = (ROOT / "src/constitution_memorizer/playground/routes.py").read_text()
    assert "INTERVAL_LADDER" not in routes
    assert "complete_cloze" not in routes
    assert "next_revision_date" not in routes
    assert "advance_interval" not in routes
