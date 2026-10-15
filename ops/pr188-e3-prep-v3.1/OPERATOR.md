# E3 v3.1 operator notes (review only)

Do not run upgrade until a later explicit execution grant.
Closed E2 archive `recall_prod_gate_e2_20261015T063833Z.tar.age` is unchanged.
PR #188, PR #211, Railway, and production are not part of this review.

Keep these files in the **same directory**:
- gate_e3_precheck.zsh
- gate_e3_upgrade.zsh
- pr188_gate_e3_guards.py
- pr188_gate_e3_alembic_upgrade.py

## Virtualenv

Do **not** put `.venv-mig-rehearsal` inside the development checkout.

Default resolution:

```text
E3_REHEARSAL_SRC   = $HOME/recall_rehearsal_src
E3_REHEARSAL_VENV  = $E3_REHEARSAL_SRC/.venv-mig-rehearsal
REPO ($1)          = development clone used only for git worktree + origin checks
```

Override only if the rehearsal tree is elsewhere:

```zsh
export E3_REHEARSAL_SRC="$HOME/recall_rehearsal_src"
export E3_REHEARSAL_VENV="$HOME/recall_rehearsal_src/.venv-mig-rehearsal"
```

Expect `E3_VENV_FROM_DEV_CHECKOUT=no` and `E3_VENV_RESOLVED=.../recall_rehearsal_src/.venv-mig-rehearsal`.

## Local tests (not production)

```zsh
python3 ./pr188_gate_e3_v3_offline_test.py
# optional, needs a local PostgreSQL database (default db e3v31):
python3 ./pr188_gate_e3_v31_pg_test.py
```

The PostgreSQL test uses SQLAlchemy 2.1.x / Alembic 1.20.x / psycopg 3.3.x
and a copy of production `alembic/env.py` (NullPool + begin_transaction).
It never uses the production DSN.

## After this review is accepted, precheck only

```zsh
chmod 700 gate_e3_precheck.zsh gate_e3_upgrade.zsh
chmod 600 pr188_gate_e3_guards.py pr188_gate_e3_alembic_upgrade.py
export E3_RAILWAY_CONFIRM='trustworthy-embrace/env/recall-th-c/0c0a8d5/PLAYGROUND_ENABLED=false'
zsh ./gate_e3_precheck.zsh /path/to/recall_the_c
```

The first argument is the git clone used to create the detached worktree.
It is not the venv path.

Expect `E3_TIMEOUT_SOURCE=session_set` and `E3_SESSION_TIMEOUTS_VERIFIED=yes`.
Do not run `gate_e3_upgrade.zsh` until `GATE_E3_UPGRADE_CONFIRM=I_AUTHORIZE_PROD_ALEMBIC_0016_TO_0027` is separately authorized.
