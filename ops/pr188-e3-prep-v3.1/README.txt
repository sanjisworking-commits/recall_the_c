PR #188 E3 preparation bundle — REVISION e3_prep_v3_1_20261015
Review only. Not approved for production Alembic, Railway, or merge.
Do not run gate_e3_upgrade.zsh.

Why v3 was not approved
------------------------
v3 session SET/SHOW on the Alembic connection is directionally correct, but:

1. Virtualenv: gate_e3_upgrade.zsh still used `$REPO/.venv-mig-rehearsal`
   (the development checkout). The working migration environment is
   `~/recall_rehearsal_src/.venv-mig-rehearsal`.
2. Transaction safety: Engine.connect SET/SHOW was not proven to leave
   PostgreSQL IDLE before env.py's begin_transaction().
3. Fail-closed: a failed timeout check must prevent all migration DDL,
   and a successful check must be recorded before any migration SQL.

v3.1 corrections
----------------
- Venv: `E3_REHEARSAL_VENV` or `$HOME/recall_rehearsal_src/.venv-mig-rehearsal`.
  The development checkout argument is never used as the venv root.
  `E3_VENV_FROM_DEV_CHECKOUT=no`. Abort `venv_resolved_from_dev_checkout`
  if an override points at `$REPO/.venv-mig-rehearsal` while REPO is not
  the rehearsal source.
- SET/SHOW run with autocommit enabled, then autocommit is restored.
  psycopg transaction_status must be IDLE (0) before and after.
  A SET without autocommit leaves INTRANS (2) and would change Alembic's
  intended begin_transaction(); v3.1 refuses that.
- Engine.before_cursor_execute refuses every SQLAlchemy statement until
  the connect listener has set state['verified']=True. A failed SET/SHOW
  raises in the connect listener, so Alembic never reaches DDL (no
  alembic_version, no probe/migration tables).

Reject any file that does not contain REVISION=e3_prep_v3_1_20261015
(except gate_backup.zsh, which is still REVISION=e3_prep_v2_20261015).

Files
-----
gate_e3_precheck.zsh
gate_e3_upgrade.zsh              REVIEW ONLY. Do not execute.
gate_e3_timeout_diag.zsh
pr188_gate_e3_guards.py
pr188_gate_e3_alembic_upgrade.py must sit next to the upgrade script
pr188_gate_e3_v3_offline_test.py
pr188_gate_e3_v31_pg_test.py     local PostgreSQL; not production
gate_backup.zsh                  unchanged two-mode future backup entrypoint
SHA256SUMS
README.txt
OPERATOR.md
TEST_EVIDENCE.md

Download this bundle from the attached zip in this chat / artifacts,
not from a GitHub binary URL. PR #211 remains the frozen v3 retrieval
copy and is not updated.
