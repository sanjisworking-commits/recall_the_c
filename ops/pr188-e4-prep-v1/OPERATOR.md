# E4 operator notes — REVISION e4_prep_v1_20261016

E3 is deferred. Production Alembic is **20260828_0016**. Do not run Alembic.
Do not change Railway. Do not merge PR #188.

Keep these files in the **same directory**. Copy them to `~/Desktop` (or
another Mac path that is not `/workspace`) before running. The wrappers
abort `cloud_workspace_forbidden_use_mac` if launched from this cloud tree.

## Loop

1. ChatGPT verifies this ZIP (SHA-256 + scripts).
2. Grok Bot runs **only** `gate_e4_now.zsh` on Sanjali's Mac.
3. ChatGPT verifies the `E4_*` output.
4. Do **not** run `gate_e4_verify.zsh` until E3 has actually produced 0027.

## E4-now (safe today, read-only)

```zsh
chmod 700 gate_e4_now.zsh
chmod 600 pr188_gate_e4.py pr188_gate_e4_guards.py
export GATE_E4_NOW_CONFIRM='I_AUTHORIZE_E4_NOW_READONLY_AT_0016'
export E4_RAILWAY_CONFIRM='trustworthy-embrace/env/recall-th-c/0c0a8d5/PLAYGROUND_ENABLED=false'
zsh ./gate_e4_now.zsh
```

Paste only `E4_*` lines. Expect `E4_ALEMBIC=20260828_0016`,
`E4_NEW_TABLES_PRESENT=none`, `E4_HTTP_PLAYGROUND_OLD_APP_404=yes`,
`E4_RESULT=PASS`.

Uses `~/.recall_direct_dsn` + `PGPASSFILE` (mode 600), `psql -w`, port 5432,
HTTP `https://recall-the-c.in` only.

## E4-verify (not runnable to PASS until after E3)

Expects `alembic_version=20260927_0027`, `~/.recall_gate_e3_pre_upgrade_baseline`,
15 new tables empty, RLS on / force-RLS off / CRUD complete / zero policies,
legacy counts equal-or-increase vs the E3 baseline, same HTTP old-app checks.

```zsh
export GATE_E4_VERIFY_CONFIRM='I_AUTHORIZE_E4_POST_E3_READONLY_AT_0027'
export E4_RAILWAY_CONFIRM='trustworthy-embrace/env/recall-th-c/0c0a8d5/PLAYGROUND_ENABLED=false'
zsh ./gate_e4_verify.zsh
```

On today's production this **must** print `E4_REASON=e3_not_run_alembic_still_0016`
after a read-only identity SELECT. Do not run it in this loop unless ChatGPT
asks for that negative proof.

## Offline (no production)

```zsh
python3 ./pr188_gate_e4_offline_test.py
```
