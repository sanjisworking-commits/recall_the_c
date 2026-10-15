# E3 v3 operator notes (review only)

Do not run upgrade until a later explicit execution grant.
Closed E2 archive `recall_prod_gate_e2_20261015T063833Z.tar.age` is unchanged.

Keep these files in the **same directory**:
- gate_e3_precheck.zsh
- gate_e3_upgrade.zsh
- pr188_gate_e3_guards.py
- pr188_gate_e3_alembic_upgrade.py

Optional diagnostic (session SET/SHOW vs URL options; no Alembic):

```zsh
chmod 700 gate_e3_timeout_diag.zsh
zsh ./gate_e3_timeout_diag.zsh
```

Paste only `E3_DIAG_*` lines. Expect `E3_DIAG_CONCLUSION=startup_options_not_honored_use_session_set` if the pooler still drops startup options.

After this review is accepted, precheck only:

```zsh
chmod 700 gate_e3_precheck.zsh gate_e3_upgrade.zsh
chmod 600 pr188_gate_e3_guards.py pr188_gate_e3_alembic_upgrade.py
export E3_RAILWAY_CONFIRM='trustworthy-embrace/env/recall-th-c/0c0a8d5/PLAYGROUND_ENABLED=false'
zsh ./gate_e3_precheck.zsh /path/to/recall_the_c
```

Expect `E3_TIMEOUT_SOURCE=session_set` and `E3_SESSION_TIMEOUTS_VERIFIED=yes`.
Do not run `gate_e3_upgrade.zsh` until `GATE_E3_UPGRADE_CONFIRM=I_AUTHORIZE_PROD_ALEMBIC_0016_TO_0027` is separately authorized.
