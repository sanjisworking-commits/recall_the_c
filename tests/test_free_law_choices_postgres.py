"""B1 on real Postgres: ledger, advisory lock, atomic ``within`` step, month carry.

The production repository paths are SQL that SQLite cannot exercise
(``FOR UPDATE``, ``pg_advisory_xact_lock``, ``UniqueViolation`` retry). These
tests run against a *disposable* Postgres named by ``PLAYGROUND_PG_TEST_URL``
and are skipped otherwise. They apply the Alembic chain to ``head`` on that
database, which must never be staging or production: the fixture refuses a
URL that does not point at localhost.

Run locally against a throwaway cluster (recorded in the PR #230 description):

    PLAYGROUND_PG_TEST_URL=postgresql://postgres@127.0.0.1:54329/pgb1 \\
        pytest -m integration tests/test_free_law_choices_postgres.py
"""

from __future__ import annotations

import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID

import pytest

from constitution_memorizer.playground.roster.models import (
    ORIGIN_CARRY_FORWARD,
    RESULT_ALREADY_ACTIVE,
    RESULT_FREE_CHOICES_EXHAUSTED,
    RESULT_OK,
    RESULT_RE_ADDED,
)
from constitution_memorizer.playground.roster.period import playground_month_bounds
from constitution_memorizer.playground.roster.service import RosterService
from constitution_memorizer.playground.service import (
    membership_and_selection_writer,
    require_playground_law,
    selection_rows,
)
from tests.test_free_law_choices import _allow_stubs, _snap

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[1]
PG_URL = os.environ.get("PLAYGROUND_PG_TEST_URL", "").strip()
USER = UUID("b1b1b1b1-b1b1-4b1b-8b1b-b1b1b1b1b1b1")
USER_2 = UUID("b2b2b2b2-b2b2-4b2b-8b2b-b2b2b2b2b2b2")
NOW = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
OCT_1 = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)
TABLES = (
    "user_playground_selection",
    "user_playground_item",
    "user_playground_roster_item",
    "user_playground_period",
    "user_playground_choice",
)


def _require_local(url: str) -> None:
    host = (urlparse(url).hostname or "").lower()
    if host not in {"localhost", "127.0.0.1", "::1"}:
        pytest.skip("PLAYGROUND_PG_TEST_URL must point at a disposable local Postgres")


@pytest.fixture(scope="module")
def pool():
    if not PG_URL:
        pytest.skip("PLAYGROUND_PG_TEST_URL not set")
    _require_local(PG_URL)
    from psycopg_pool import ConnectionPool

    from alembic import command
    from alembic.config import Config

    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = PG_URL
    try:
        command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
    pool = ConnectionPool(conninfo=PG_URL, min_size=1, max_size=8, open=True)
    try:
        yield pool
    finally:
        pool.close()


@pytest.fixture()
def repos(pool):
    from constitution_memorizer.playground.postgres import PostgresPlaygroundRepository
    from constitution_memorizer.playground.roster.postgres import PostgresRosterRepository

    with pool.connection() as conn:
        for table in TABLES:
            conn.execute(
                f"DELETE FROM {table} WHERE user_id = ANY(%s)",  # noqa: S608 — fixed names
                ([str(USER), str(USER_2)],),
            )
        conn.commit()
    return PostgresRosterRepository(pool), PostgresPlaygroundRepository(pool)


def _count(pool, table: str, user: UUID = USER) -> int:
    with pool.connection() as conn:
        row = conn.execute(
            f"SELECT count(*) FROM {table} WHERE user_id = %s",  # noqa: S608
            (str(user),),
        ).fetchone()
    return int(row[0])


def _ledger(pool, user: UUID = USER) -> list[str]:
    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT law_id FROM user_playground_choice WHERE user_id = %s ORDER BY law_id",
            (str(user),),
        ).fetchall()
    return [r[0] for r in rows]


def _service(repo) -> RosterService:
    return RosterService(repo, tier_model="choices")


FREE = _snap(choice_limit=3)
PLUS = _snap(tier="plus", is_subscribed=True, law_limit=None)


def _rows(law_id: str, numbers: list[str]):
    return selection_rows(law_id, numbers, entire=False, act=require_playground_law(law_id))


# ------------------------------------------------------------------ ledger


def test_free_three_choices_then_exhausted_and_readd_is_free(pool, repos):
    roster_repo, _overlay = repos
    svc = _service(roster_repo)
    for law in ("ndps", "uapa", "pss"):
        out = svc.confirm_add_law(USER, law, FREE, now=NOW)
        assert out.status == RESULT_OK and out.choice_recorded, (law, out)
    blocked = svc.confirm_add_law(USER, "bns", FREE, now=NOW)
    assert blocked.status == RESULT_FREE_CHOICES_EXHAUSTED
    assert blocked.choices_used == 3 and blocked.choice_limit == 3
    assert _ledger(pool) == ["ndps", "pss", "uapa"]
    # Remove keeps the choice; re-add is free and writes membership again.
    svc.remove_law_this_period(USER, "uapa", FREE, now=NOW)
    assert not svc.is_law_active_this_period(USER, "uapa", now=NOW)
    back = svc.confirm_add_law(USER, "uapa", FREE, now=NOW)
    assert back.status == RESULT_RE_ADDED and not back.choice_recorded
    assert svc.is_law_active_this_period(USER, "uapa", now=NOW)
    assert _ledger(pool) == ["ndps", "pss", "uapa"]
    # A different account's ledger is untouched.
    assert _ledger(pool, USER_2) == []


def test_duplicate_saves_of_the_same_law_spend_one_choice(pool, repos):
    roster_repo, _overlay = repos
    svc = _service(roster_repo)
    first = svc.confirm_add_law(USER, "ndps", FREE, now=NOW)
    second = svc.confirm_add_law(USER, "ndps", FREE, now=NOW)
    assert first.status == RESULT_OK and second.status == RESULT_ALREADY_ACTIVE
    assert not second.choice_recorded and not second.within_applied
    assert _ledger(pool) == ["ndps"]
    assert _count(pool, "user_playground_roster_item") == 1


def test_concurrent_duplicate_saves_of_a_new_law_record_one_choice(pool, repos):
    """Six requests save the same new law at once: one ``ok``, the rest
    ``already_active`` (FOR UPDATE on the period row, UniqueViolation retry
    on the item). One item, one ledger row."""

    roster_repo, _overlay = repos
    svc = _service(roster_repo)
    svc.ensure_current_period(USER, FREE, now=NOW)
    barrier = threading.Barrier(6)
    results: list = []
    errors: list = []

    def worker():
        try:
            barrier.wait(timeout=10)
            results.append(svc.confirm_add_law(USER, "ndps", FREE, now=NOW).status)
        except Exception as exc:  # noqa: BLE001
            errors.append(repr(exc))

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert errors == []
    assert sorted(results).count(RESULT_OK) == 1
    assert set(results) <= {RESULT_OK, RESULT_ALREADY_ACTIVE}
    assert _ledger(pool) == ["ndps"]
    assert _count(pool, "user_playground_roster_item") == 1


def test_concurrent_attempts_to_spend_the_third_choice_record_at_most_the_limit(
    pool, repos, monkeypatch: pytest.MonkeyPatch
):
    """B1-F05 on Postgres: two choices spent, six distinct laws race for the
    third. The per-account advisory lock serialises the ledger check so
    exactly one wins and the ledger never exceeds three rows."""

    _allow_stubs(monkeypatch)
    roster_repo, _overlay = repos
    svc = _service(roster_repo)
    assert svc.confirm_add_law(USER, "ndps", FREE, now=NOW).status == RESULT_OK
    assert svc.confirm_add_law(USER, "uapa", FREE, now=NOW).status == RESULT_OK
    laws = ["pss", "bns", "bnss", "mtp", "stub-a", "stub-b"]
    barrier = threading.Barrier(len(laws))
    results: dict[str, str] = {}
    errors: list = []
    lock = threading.Lock()

    def worker(law: str):
        try:
            barrier.wait(timeout=10)
            out = svc.confirm_add_law(USER, law, FREE, now=NOW)
            with lock:
                results[law] = out.status
        except Exception as exc:  # noqa: BLE001
            errors.append(repr(exc))

    threads = [threading.Thread(target=worker, args=(law,)) for law in laws]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert errors == []
    statuses = list(results.values())
    assert statuses.count(RESULT_OK) == 1, results
    assert statuses.count(RESULT_FREE_CHOICES_EXHAUSTED) == len(laws) - 1, results
    assert len(_ledger(pool)) == 3
    active = {item.law_id for item in svc.active_roster_items(USER, now=NOW)}
    assert active == set(_ledger(pool))


def test_ledger_write_holds_the_advisory_lock(pool, repos):
    roster_repo, _overlay = repos
    svc = _service(roster_repo)
    seen: dict[str, int] = {}

    def within(conn) -> None:
        row = conn.execute(
            "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' "
            "AND classid = 872012 AND pid = pg_backend_pid() AND granted"
        ).fetchone()
        seen["advisory"] = int(row[0])
        row = conn.execute(
            "SELECT count(*) FROM user_playground_choice WHERE user_id = %s", (str(USER),)
        ).fetchone()
        seen["ledger_rows_visible_in_tx"] = int(row[0])

    out = svc.confirm_add_law(USER, "ndps", FREE, now=NOW, within=within)
    assert out.status == RESULT_OK and out.within_applied
    assert seen == {"advisory": 1, "ledger_rows_visible_in_tx": 1}


# ------------------------------------------------------------ atomic save


def test_within_failure_rolls_back_choice_membership_and_selection(pool, repos):
    """5-19 / B1-F08 on Postgres: the overlay write runs on the consume's
    transaction; its failure leaves no item, no ledger row, no overlay row
    and no selection. The retry then spends exactly one choice."""

    roster_repo, overlay = repos
    svc = _service(roster_repo)
    rows = _rows("ndps", ["1"])
    real = membership_and_selection_writer(overlay, USER, "ndps", rows)

    def failing(conn) -> None:
        real(conn)  # overlay rows written on the open transaction…
        raise RuntimeError("simulated failure writing the selection")

    with pytest.raises(RuntimeError):
        svc.confirm_add_law(USER, "ndps", FREE, now=NOW, within=failing)
    assert _ledger(pool) == []
    assert _count(pool, "user_playground_roster_item") == 0
    assert _count(pool, "user_playground_item") == 0
    assert _count(pool, "user_playground_selection") == 0
    assert overlay.get_item(USER, "ndps") is None
    assert not svc.is_law_active_this_period(USER, "ndps", now=NOW)

    out = svc.confirm_add_law(USER, "ndps", FREE, now=NOW, within=real)
    assert out.status == RESULT_OK and out.choice_recorded and out.within_applied
    assert _ledger(pool) == ["ndps"]
    assert svc.is_law_active_this_period(USER, "ndps", now=NOW)
    assert overlay.get_item(USER, "ndps") is not None
    assert [s.source_locator for s in overlay.list_selection(USER, "ndps")] == [
        r[0] for r in rows
    ]


def test_within_runs_for_a_free_readd_of_a_removed_law(pool, repos):
    roster_repo, overlay = repos
    svc = _service(roster_repo)
    rows = _rows("ndps", ["1", "2"])
    writer = membership_and_selection_writer(overlay, USER, "ndps", rows)
    assert svc.confirm_add_law(USER, "ndps", FREE, now=NOW, within=writer).status == RESULT_OK
    svc.remove_law_this_period(USER, "ndps", FREE, now=NOW)
    back = svc.confirm_add_law(USER, "ndps", FREE, now=NOW, within=writer)
    assert back.status == RESULT_RE_ADDED and back.within_applied and not back.choice_recorded
    assert _ledger(pool) == ["ndps"]
    assert len(overlay.list_selection(USER, "ndps")) == 2


# -------------------------------------------------------------- month carry


def test_month_boundary_carries_active_laws_and_never_resurrects_a_removed_one(pool, repos):
    roster_repo, _overlay = repos
    svc = _service(roster_repo)
    assert svc.confirm_add_law(USER, "ndps", FREE, now=NOW).status == RESULT_OK
    assert svc.confirm_add_law(USER, "uapa", FREE, now=NOW).status == RESULT_OK
    svc.remove_law_this_period(USER, "uapa", FREE, now=NOW)
    sep_start, _ = playground_month_bounds(NOW)
    oct_start, _ = playground_month_bounds(OCT_1)

    # Reads across the boundary: membership continues, nothing is created.
    assert roster_repo.get_period(USER, oct_start) is None
    assert svc.is_law_active_this_period(USER, "ndps", now=OCT_1)
    assert not svc.is_law_active_this_period(USER, "uapa", now=OCT_1)
    assert roster_repo.get_period(USER, oct_start) is None

    # The next save point materialises October and carries the active law.
    out = svc.confirm_add_law(USER, "pss", FREE, now=OCT_1)
    assert out.status == RESULT_OK and out.choice_recorded
    october = {item.law_id: item for item in roster_repo.list_items(USER, oct_start)}
    assert set(october) == {"ndps", "pss"}, october
    assert october["ndps"].origin == ORIGIN_CARRY_FORWARD and october["ndps"].is_active
    assert "uapa" not in october  # removed in September: never auto re-added (5-4)
    assert {i.law_id for i in svc.active_roster_items(USER, now=OCT_1)} == {"ndps", "pss"}
    # September history is intact.
    september = {item.law_id: item for item in roster_repo.list_items(USER, sep_start)}
    assert september["uapa"].removed_at is not None and september["ndps"].is_active

    # The ledger counts the lifetime choices: ndps, uapa, pss → exhausted.
    assert _ledger(pool) == ["ndps", "pss", "uapa"]
    assert svc.confirm_add_law(USER, "bns", FREE, now=OCT_1).status == RESULT_FREE_CHOICES_EXHAUSTED
    # Choosing uapa again in October is an explicit, free re-add.
    back = svc.confirm_add_law(USER, "uapa", FREE, now=OCT_1)
    assert back.status in {RESULT_OK, RESULT_RE_ADDED} and not back.choice_recorded
    assert _ledger(pool) == ["ndps", "pss", "uapa"]


# ------------------------------------------------------------- paid, no cap


def test_plus_has_no_cap_and_a_stale_stored_limit_cannot_block(
    pool, repos, monkeypatch: pytest.MonkeyPatch
):
    _allow_stubs(monkeypatch)
    roster_repo, _overlay = repos
    svc = _service(roster_repo)
    laws = ["ndps", "uapa", "pss", "bns", "bnss", "mtp"] + [f"stub-{i}" for i in range(6)]
    for law in laws:
        out = svc.confirm_add_law(USER, law, PLUS, now=NOW)
        assert out.status == RESULT_OK, (law, out)
        assert out.remaining is None
    assert _ledger(pool) == []  # paid accounts never write the ledger
    start, _ = playground_month_bounds(NOW)
    with pool.connection() as conn:
        conn.execute(
            "UPDATE user_playground_period SET law_limit = 10 WHERE user_id = %s AND period_start = %s",
            (str(USER), start),
        )
        conn.commit()
    thirteenth = svc.confirm_add_law(USER, "stub-99", PLUS, now=NOW)
    assert thirteenth.status == RESULT_OK  # the effective limit, never the stored row
    assert len(svc.active_roster_items(USER, now=NOW)) == 13
