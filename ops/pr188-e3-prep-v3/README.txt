PR #188 E3 preparation bundle — REVISION e3_prep_v3_20261015
Review only. Not approved for production Alembic, Railway, or merge.

Why v2 precheck failed
----------------------
Mac precheck connected via the Supabase session pooler on port 5432 and saw:

  E3_LOCK_TIMEOUT=0
  E3_STATEMENT_TIMEOUT=2min
  E3_IDLE_IN_TX_TIMEOUT=0
  E3_REASON=lock_timeout_not_15s

Those are hosted defaults (Supabase statement_timeout is commonly 2min), not
the URL startup options. libpq `options=-c ...` in the connection URI is not
reliably forwarded by the pooler (PgBouncer). urlencode also turns spaces into
'+', which can break option parsing even when the parameter is forwarded.

A separate psql SHOW that happened to pass would still be insufficient: Alembic
opens its own SQLAlchemy connection. Timeouts must be SET and SHOWn on that
same DBAPI connection.

v3 approach
-----------
- Precheck: session SET then SHOW, then the read-only identity/count queries.
- Upgrade fail-fast psql: same SET+SHOW (not sufficient by itself).
- Alembic: pr188_gate_e3_alembic_upgrade.py registers a SQLAlchemy Engine
  connect listener, SET+SHOW on the live DBAPI connection, then
  alembic.command.upgrade(..., "20260927_0027"). env.py is not modified;
  NullPool + begin_transaction wrapping the chain is unchanged.
- No ALTER DATABASE / ALTER ROLE, no stamp, downgrade, retry, or upgrade head.
- Worktree, pinned SHA, 12-hour E2 recency, confirm token preserved.

Reject any file that does not contain REVISION=e3_prep_v3_20261015.

Files
-----
gate_e3_precheck.zsh
gate_e3_upgrade.zsh
gate_e3_timeout_diag.zsh          optional Mac SET/SHOW vs URL-options diagnostic
pr188_gate_e3_guards.py
pr188_gate_e3_alembic_upgrade.py  must sit next to the upgrade script
pr188_gate_e3_v3_offline_test.py
gate_backup.zsh                   unchanged two-mode future backup entrypoint
SHA256SUMS
README.txt
OPERATOR.md

This directory is in the git workspace (ops/pr188-e3-prep-v3/) so it can be
downloaded from the repository. Do not use /opt/cursor/artifacts copies.
