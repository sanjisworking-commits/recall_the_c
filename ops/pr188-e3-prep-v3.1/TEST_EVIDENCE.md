# E3 v3.1 tests — sanitized evidence

Production was not contacted. Alembic upgrade against production was not run.

## Offline (no PostgreSQL)

Command: `python3 ops/pr188-e3-prep-v3.1/pr188_gate_e3_v3_offline_test.py`

TEST_SUMMARY total=19 passed=19 failed=0

Includes the original v3 cases plus:

- SET without autocommit would leave INTRANS (transaction_status=2)
- apply_timeouts leaves IDLE and restores autocommit=False
- apply_timeouts refuses an already-open transaction
- scripts never assign `VENV="$REPO/.venv-mig-rehearsal"`
- venv resolves to `$HOME/recall_rehearsal_src/.venv-mig-rehearsal` when $1 is a development checkout
- `E3_REHEARSAL_VENV` pointing at the development checkout venv fails closed
  (`E3_REASON=venv_resolved_from_dev_checkout`)

## Local PostgreSQL (not production)

Command: `python3 ops/pr188-e3-prep-v3.1/pr188_gate_e3_v31_pg_test.py`

```
TEST_SQLALCHEMY=2.1.4
TEST_ALEMBIC=1.20.0
TEST_PSYCOPG=3.3.6
TEST_ENV_PY_PATTERN=NullPool+begin_transaction
TEST_PRODUCTION=no
TEST_SUMMARY total=5 passed=5 failed=0
```

Results:

- `pg_env_py_matches_production` — test tree copies `alembic/env.py` (NullPool + begin_transaction).
- `pg_set_without_autocommit_leaves_intrans` — a raw `SET` with psycopg autocommit=False
  moves transaction_status IDLE(0) → INTRANS(2). This is the v3 hazard.
- `pg_connect_listener_idle_then_begin_transaction` — after `apply_timeouts_dbapi`,
  status is IDLE, autocommit is False, SQLAlchemy `connection.in_transaction()` is
  False, then `conn.begin()` starts the intended transaction. SHOW inside that
  transaction still sees lock=15s, statement=2min (display of 120s), idle=1min
  (display of 60s).
- `pg_failed_timeout_check_prevents_all_ddl` — TimeoutNotApplied on connect:
  `e3_v31_probe` absent, `alembic_version` absent, `verified=False`, no SQLAlchemy
  SQL before verified.
- `pg_verified_recorded_before_migration_ddl_same_connection` — `verified=True`
  before the first SQLAlchemy statement; CREATE TABLE + INSERT used the same
  `pg_backend_pid` as the listener (TEST_SAME_BACKEND=True).
