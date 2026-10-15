# E3 v3 offline tests — sanitized evidence

Command: `python3 ops/pr188-e3-prep-v3/pr188_gate_e3_v3_offline_test.py`

TEST_SUMMARY total=13 passed=13 failed=0

Reproduced the Mac precheck failure without touching production:

- SHOW `0` / `2min` / `0` → `E3_REASON=lock_timeout_not_15s`
- classified `startup_options_not_honored`
- session SET then SHOW applies 15s / 120s (or display `2min`) / 60s
- SET no-op still fails closed
- Alembic wrapper rejects `head`, missing target, missing worktree
- Confirm token and E2 SHA still fail closed before DSN
