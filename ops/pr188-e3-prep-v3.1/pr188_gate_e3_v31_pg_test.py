#!/usr/bin/env python3
# REVISION=e3_prep_v3_1_20261015
"""PostgreSQL tests for the Alembic connect-listener SET/SHOW path.

Uses the same env.py pattern as production (NullPool + begin_transaction)
and the same SQLAlchemy/psycopg/Alembic packages as this environment.
Does not talk to production.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import pr188_gate_e3_alembic_upgrade as wrapper  # noqa: E402
import pr188_gate_e3_guards as guards  # noqa: E402

PG_URL = os.environ.get(
    "E3_V31_PG_URL",
    "postgresql://ubuntu@/e3v31?host=/var/run/postgresql",
)
PROD_ENV_PY = HERE.parents[1] / "alembic" / "env.py"


def _sa_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def record(results, name, ok, detail):
    results.append((name, ok, detail))
    print(("PASS " if ok else "FAIL ") + name)
    if detail:
        print(detail)


def _psql(sql: str):
    import psycopg

    with psycopg.connect(PG_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            try:
                return cur.fetchall()
            except Exception:
                return None


def _is_timeout(exc) -> bool:
    cur = exc
    seen: set[int] = set()
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        if isinstance(cur, guards.TimeoutNotApplied):
            return True
        cur = getattr(cur, "__cause__", None) or getattr(cur, "__context__", None)
    return False


ENV_PY_FALLBACK = '''"""Alembic environment for multi-user PostgreSQL schema."""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, text

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None


def get_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL is required for migrations")
    # SQLAlchemy 2 prefers postgresql+psycopg://
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
'''

ALEMBIC_INI = """[alembic]
script_location = alembic
prepend_sys_path = .
version_path_separator = os
sqlalchemy.url = driver://user:pass@localhost/dbname

[loggers]
keys = root,sqlalchemy,alembic
[handlers]
keys = console
[formatters]
keys = generic
[logger_root]
level = WARN
handlers = console
[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine
[logger_alembic]
level = WARN
handlers =
qualname = alembic
[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic
[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
"""

REV = '''"""probe revision"""
from alembic import op
import sqlalchemy as sa

revision = "e3v31_0001"
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute(sa.text("CREATE TABLE e3_v31_probe (pid integer)"))
    op.execute(sa.text("INSERT INTO e3_v31_probe (pid) SELECT pg_backend_pid()"))

def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS e3_v31_probe"))
'''


def env_py_text() -> str:
    if PROD_ENV_PY.is_file():
        return PROD_ENV_PY.read_text(encoding="utf-8")
    return ENV_PY_FALLBACK


def write_alembic_tree(root: Path) -> None:
    (root / "alembic" / "versions").mkdir(parents=True)
    (root / "alembic.ini").write_text(ALEMBIC_INI)
    (root / "alembic" / "env.py").write_text(env_py_text())
    (root / "alembic" / "script.py.mako").write_text("# unused\n")
    (root / "alembic" / "versions" / "e3v31_0001_probe.py").write_text(REV)


def reset_db() -> None:
    _psql("DROP TABLE IF EXISTS e3_v31_probe")
    _psql("DROP TABLE IF EXISTS alembic_version")


def table_exists() -> bool:
    rows = _psql("SELECT to_regclass('public.e3_v31_probe')::text")
    return bool(rows and rows[0][0])


def test_env_py_matches_production(results) -> None:
    if not PROD_ENV_PY.is_file():
        record(results, "pg_env_py_matches_production", False, "TEST_PROD_ENV_PY=missing")
        return
    prod = PROD_ENV_PY.read_text(encoding="utf-8")
    ok = (
        "poolclass=pool.NullPool" in prod
        and "with context.begin_transaction():" in prod
        and "context.run_migrations()" in prod
        and env_py_text() == prod
    )
    record(
        results,
        "pg_env_py_matches_production",
        ok,
        "TEST_ENV_PY=NullPool+begin_transaction from alembic/env.py",
    )


def test_raw_set_without_autocommit_leaves_intrans(results) -> None:
    import psycopg
    from psycopg.pq import TransactionStatus

    with psycopg.connect(PG_URL) as conn:
        before_ac = conn.autocommit
        before_tx = conn.info.transaction_status
        with conn.cursor() as cur:
            cur.execute("SET lock_timeout = '15s'")
        after_tx = conn.info.transaction_status
        conn.rollback()
        idle_after_rollback = conn.info.transaction_status
    record(
        results,
        "pg_set_without_autocommit_leaves_intrans",
        before_ac is False
        and before_tx == TransactionStatus.IDLE
        and after_tx == TransactionStatus.INTRANS
        and idle_after_rollback == TransactionStatus.IDLE,
        f"TEST_BEFORE_AC={before_ac}\nTEST_BEFORE_TX={int(before_tx)}\nTEST_AFTER_SET_TX={int(after_tx)}",
    )


def test_listener_leaves_idle_then_alembic_begins(results) -> None:
    from psycopg.pq import TransactionStatus
    from sqlalchemy import create_engine, event, text
    from sqlalchemy.pool import NullPool

    events = []
    engine = create_engine(_sa_url(PG_URL), poolclass=NullPool)

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, _rec):
        events.append(("before_set", guards.dbapi_transaction_status(dbapi_conn), dbapi_conn.autocommit))
        shown = guards.apply_timeouts_dbapi(dbapi_conn)
        events.append(
            (
                "after_set",
                guards.dbapi_transaction_status(dbapi_conn),
                dbapi_conn.autocommit,
                shown["lock_timeout"],
                shown["statement_timeout"],
                shown["idle_in_transaction_session_timeout"],
            )
        )

    with engine.connect() as conn:
        idle_after_connect = conn.in_transaction()
        events.append(("sqlalchemy_in_transaction_after_connect", idle_after_connect))
        with conn.begin():
            events.append(("sqlalchemy_in_transaction_after_begin", conn.in_transaction()))
            lock = conn.execute(text("SHOW lock_timeout")).scalar()
            stmt = conn.execute(text("SHOW statement_timeout")).scalar()
            idle = conn.execute(text("SHOW idle_in_transaction_session_timeout")).scalar()
            events.append(("show_inside_alembic_style_txn", lock, stmt, idle))
    engine.dispose()

    after_set = [e for e in events if e[0] == "after_set"][0]
    ok = (
        events[0][0] == "before_set"
        and events[0][1] == int(TransactionStatus.IDLE)
        and after_set[1] == int(TransactionStatus.IDLE)
        and after_set[2] is False
        and guards.check_timeouts(after_set[3], after_set[4], after_set[5]) is None
        and events[-3][1] is False
        and events[-2][1] is True
        and guards.check_timeouts(str(lock), str(stmt), str(idle)) is None
    )
    record(
        results,
        "pg_connect_listener_idle_then_begin_transaction",
        ok,
        "TEST_EVENTS=" + repr(events),
    )


def test_failed_timeout_prevents_ddl(results) -> None:
    reset_db()
    orig = guards.apply_timeouts_dbapi

    def boom(_conn):
        raise guards.TimeoutNotApplied("lock_timeout", "0")

    guards.apply_timeouts_dbapi = boom  # type: ignore[method-assign]
    os.environ["DATABASE_URL"] = PG_URL
    raised = None
    state: dict = {}
    try:
        with tempfile.TemporaryDirectory(prefix="e3v31_fail_") as td:
            root = Path(td)
            write_alembic_tree(root)
            try:
                wrapper.run_alembic_upgrade(str(root), "e3v31_0001", state)
            except Exception as exc:
                raised = type(exc).__name__
                state["timeout_exc"] = _is_timeout(exc)
            finally:
                wrapper.remove_timeout_connect_listener(state)
    finally:
        guards.apply_timeouts_dbapi = orig  # type: ignore[method-assign]
    exists = table_exists()
    alembic_rows = _psql("SELECT to_regclass('public.alembic_version')::text")
    alembic_exists = bool(alembic_rows and alembic_rows[0][0])
    record(
        results,
        "pg_failed_timeout_check_prevents_all_ddl",
        (not exists)
        and (not alembic_exists)
        and (not state.get("verified"))
        and raised is not None
        and state.get("timeout_exc") is True
        and state.get("sql_before_verified") == [],
        f"TEST_TABLE_EXISTS={exists}\nTEST_ALEMBIC_VERSION_EXISTS={alembic_exists}\n"
        f"TEST_VERIFIED={state.get('verified')}\nTEST_RAISED={raised}\n"
        f"TEST_TIMEOUT_EXC={state.get('timeout_exc')}\nTEST_SQL_BEFORE={state.get('sql_before_verified')}",
    )


def test_verified_before_ddl_same_backend(results) -> None:
    reset_db()
    os.environ["DATABASE_URL"] = PG_URL
    state: dict = {}
    with tempfile.TemporaryDirectory(prefix="e3v31_ok_") as td:
        root = Path(td)
        write_alembic_tree(root)
        try:
            rc = wrapper.run_alembic_upgrade(str(root), "e3v31_0001", state)
        finally:
            wrapper.remove_timeout_connect_listener(state)

    exists = table_exists()
    pid_row = _psql("SELECT pid FROM e3_v31_probe") if exists else None
    probe_pid = pid_row[0][0] if pid_row else None
    same_pid = probe_pid is not None and probe_pid == state.get("pid")
    first_sql = state.get("first_sql_after_verified") or ""
    record(
        results,
        "pg_verified_recorded_before_migration_ddl_same_connection",
        rc == 0
        and exists
        and state.get("verified") is True
        and state.get("sql_before_verified") == []
        and first_sql != ""
        and same_pid
        and state.get("tx_status_after_set") == 0
        and guards.check_timeouts(
            state["shown"]["lock_timeout"],
            state["shown"]["statement_timeout"],
            state["shown"]["idle_in_transaction_session_timeout"],
        )
        is None,
        f"TEST_RC={rc}\nTEST_LISTENER_PID={state.get('pid')}\nTEST_PROBE_PID={probe_pid}\n"
        f"TEST_SAME_BACKEND={same_pid}\nTEST_SQL_BEFORE={state.get('sql_before_verified')}\n"
        f"TEST_FIRST_SQL_AFTER_VERIFIED={first_sql}\nTEST_TX_AFTER_SET={state.get('tx_status_after_set')}",
    )


def main() -> int:
    import alembic
    import psycopg
    import sqlalchemy

    print(f"TEST_SQLALCHEMY={sqlalchemy.__version__}")
    print(f"TEST_ALEMBIC={alembic.__version__}")
    print(f"TEST_PSYCOPG={psycopg.__version__}")
    print("TEST_ENV_PY_PATTERN=NullPool+begin_transaction")
    print("TEST_PRODUCTION=no")
    results = []
    try:
        _psql("SELECT 1")
    except Exception as exc:
        record(results, "pg_available", False, f"TEST_PG_ERROR={type(exc).__name__}")
        print("TEST_SUMMARY total=1 passed=0 failed=1")
        return 1
    test_env_py_matches_production(results)
    test_raw_set_without_autocommit_leaves_intrans(results)
    test_listener_leaves_idle_then_alembic_begins(results)
    test_failed_timeout_prevents_ddl(results)
    test_verified_before_ddl_same_backend(results)
    failed = [r for r in results if not r[1]]
    print(f"TEST_SUMMARY total={len(results)} passed={len(results)-len(failed)} failed={len(failed)}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
