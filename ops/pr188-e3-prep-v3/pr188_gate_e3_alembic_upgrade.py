#!/usr/bin/env python3
# REVISION=e3_prep_v3_20261015
"""Run alembic upgrade 20260927_0027 after SET+SHOW on the SAME DBAPI connection.

Does not modify worktree alembic/env.py. Does not stamp, downgrade, retry, or
ALTER DATABASE. SQLAlchemy Engine.connect listener fires when env.py opens
its NullPool connection; session SET persists into env.py's begin_transaction().
"""
from __future__ import annotations

import os
import sys

TARGET = "20260927_0027"


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

    import pr188_gate_e3_guards as guards
    from sqlalchemy import event
    from sqlalchemy.engine import Engine
    from alembic.config import Config
    from alembic import command

    state = {"verified": False, "reason": ""}

    @event.listens_for(Engine, "connect")
    def _on_connect(dbapi_conn, _connection_record) -> None:
        try:
            shown = guards.apply_timeouts_dbapi(dbapi_conn)
        except guards.TimeoutNotApplied as exc:
            state["reason"] = exc.reason
            print("E3_RESULT=FAIL")
            print(f"E3_REASON={exc.reason}")
            print(f"E3_MIGRATION_CONN_TIMEOUT_GOT={exc.name}={exc.got}")
            raise
        print(f"E3_MIGRATION_CONN_LOCK_TIMEOUT={shown['lock_timeout']}")
        print(f"E3_MIGRATION_CONN_STATEMENT_TIMEOUT={shown['statement_timeout']}")
        print(f"E3_MIGRATION_CONN_IDLE_IN_TX_TIMEOUT={shown['idle_in_transaction_session_timeout']}")
        print("E3_MIGRATION_CONN_TIMEOUTS_VERIFIED=yes")
        print("E3_TIMEOUT_SOURCE=session_set_on_migration_connection")
        print("E3_ENV_PY_UNMODIFIED=yes")
        state["verified"] = True

    os.chdir(wt)
    cfg = Config("alembic.ini")
    command.upgrade(cfg, TARGET)
    if not state["verified"]:
        print("E3_RESULT=FAIL")
        print("E3_REASON=migration_connect_hook_did_not_run")
        return 1
    print("E3_ALEMBIC_WRAPPER=upgrade_0027_complete")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
