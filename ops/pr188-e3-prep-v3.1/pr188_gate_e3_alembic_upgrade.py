#!/usr/bin/env python3
# REVISION=e3_prep_v3_1_20261015
"""Run alembic upgrade 20260927_0027 after SET+SHOW on the SAME DBAPI connection.

Does not modify worktree alembic/env.py. Does not stamp, downgrade, retry, or
ALTER DATABASE. SQLAlchemy Engine.connect listener fires when env.py opens
its NullPool connection. SET/SHOW run in autocommit and must leave the
connection IDLE before env.py's begin_transaction().

A second Engine.before_cursor_execute listener refuses every SQLAlchemy
statement until the timeout check has recorded success. A failed SET/SHOW
therefore cannot reach migration DDL.
"""
from __future__ import annotations

import os
import sys

TARGET = "20260927_0027"


def install_timeout_connect_listener(state: dict) -> dict:
    """Register Engine.connect SET+SHOW and a fail-closed SQL gate.

    Must be installed before alembic.command.upgrade. Sets state['verified']
    inside the connect listener before that listener returns, which is before
    env.py's begin_transaction()/run_migrations(). If SET/SHOW fails, the
    connect listener raises and command.upgrade must not run migration DDL.
    """
    import pr188_gate_e3_guards as guards
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    state.setdefault("verified", False)
    state.setdefault("shown", None)
    state.setdefault("tx_status_after_set", None)
    state.setdefault("sql_before_verified", [])
    state.setdefault("first_sql_after_verified", None)

    def _on_connect(dbapi_conn, _connection_record) -> None:
        shown = guards.apply_timeouts_dbapi(dbapi_conn)
        tx = guards.dbapi_transaction_status(dbapi_conn)
        state["tx_status_after_set"] = tx
        state["shown"] = shown
        state["pid"] = getattr(getattr(dbapi_conn, "info", None), "backend_pid", None)
        # Record success BEFORE Alembic begin_transaction/run_migrations and
        # before dialect/Alembic SQLAlchemy execute calls on this connection.
        state["verified"] = True
        print(f"E3_MIGRATION_CONN_LOCK_TIMEOUT={shown['lock_timeout']}")
        print(f"E3_MIGRATION_CONN_STATEMENT_TIMEOUT={shown['statement_timeout']}")
        print(f"E3_MIGRATION_CONN_IDLE_IN_TX_TIMEOUT={shown['idle_in_transaction_session_timeout']}")
        print("E3_MIGRATION_CONN_TX_STATUS_AFTER_SET=idle")
        print("E3_MIGRATION_CONN_TIMEOUTS_VERIFIED=yes")
        print("E3_TIMEOUT_SOURCE=session_set_on_migration_connection")
        print("E3_ENV_PY_UNMODIFIED=yes")

    def _block_unverified(conn, cursor, statement, parameters, context, executemany):
        sql = " ".join((statement or "").split())
        if not state.get("verified"):
            preview = sql[:120]
            state["sql_before_verified"].append(preview)
            print("E3_RESULT=FAIL")
            print("E3_REASON=migration_sql_before_timeout_verified")
            raise guards.ConnectListenerTxnError(
                "migration_sql_before_timeout_verified", preview
            )
        if state.get("first_sql_after_verified") is None:
            state["first_sql_after_verified"] = sql[:120]

    event.listen(Engine, "connect", _on_connect)
    event.listen(Engine, "before_cursor_execute", _block_unverified)
    state["_listeners"] = (_on_connect, _block_unverified)
    return state


def remove_timeout_connect_listener(state: dict) -> None:
    """Test helper. Production upgrade process exits after one run."""
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    listeners = state.get("_listeners") or ()
    if len(listeners) >= 1:
        try:
            event.remove(Engine, "connect", listeners[0])
        except Exception:
            pass
    if len(listeners) >= 2:
        try:
            event.remove(Engine, "before_cursor_execute", listeners[1])
        except Exception:
            pass
    state["_listeners"] = ()


def run_alembic_upgrade(worktree: str, target: str, state: dict | None = None) -> int:
    from alembic.config import Config
    from alembic import command

    state = state if state is not None else {}
    install_timeout_connect_listener(state)
    prev = os.getcwd()
    try:
        os.chdir(worktree)
        cfg = Config("alembic.ini")
        command.upgrade(cfg, target)
    finally:
        try:
            os.chdir(prev)
        except Exception:
            pass
    if not state.get("verified"):
        print("E3_RESULT=FAIL")
        print("E3_REASON=migration_connect_hook_did_not_run")
        return 1
    print("E3_ALEMBIC_WRAPPER=upgrade_complete")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] != TARGET:
        print("E3_RESULT=FAIL")
        print("E3_REASON=alembic_target_not_0027")
        return 1
    wt = os.environ.get("E3_WORKTREE", "").strip()
    if not wt or not os.path.isdir(wt):
        print("E3_RESULT=FAIL")
        print("E3_REASON=e3_worktree_missing")
        return 1
    if not os.path.isfile(os.path.join(wt, "alembic.ini")):
        print("E3_RESULT=FAIL")
        print("E3_REASON=alembic_ini_missing")
        return 1
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        print("E3_RESULT=FAIL")
        print("E3_REASON=database_url_missing")
        return 1
    if "6543" in url:
        print("E3_RESULT=FAIL")
        print("E3_REASON=timeout_url_contains_6543")
        return 1
    try:
        return run_alembic_upgrade(wt, TARGET)
    except Exception as exc:
        import pr188_gate_e3_guards as guards

        if isinstance(exc, guards.TimeoutNotApplied):
            print("E3_RESULT=FAIL")
            print(f"E3_REASON={exc.reason}")
            print(f"E3_MIGRATION_CONN_TIMEOUT_GOT={exc.name}={exc.got}")
            return 1
        print("E3_RESULT=FAIL")
        print("E3_REASON=alembic_wrapper_error")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
