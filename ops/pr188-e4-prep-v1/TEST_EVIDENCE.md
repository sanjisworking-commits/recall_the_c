# E4 v1 offline tests — sanitized evidence

Production was not contacted. Alembic was not run. Railway was not edited.

Command: `python3 ops/pr188-e4-prep-v1/pr188_gate_e4_offline_test.py`

TEST_SUMMARY total=30 passed=30 failed=0

Covered:

- E4-now / E4-verify missing confirm tokens fail closed before DSN
- Railway operator confirm required
- Wrappers abort `cloud_workspace_forbidden_use_mac` from this tree
- Identity helpers: 0016 fails E4-verify; 0027 fails E4-now
- Legacy count increase is recorded; decrease is a verify FAIL signal
- New-table RLS off / nonzero rows / unexpected policy fail closed
- `user_device_platform_check` must include `ios` after E3
- HTTP base must be `https://recall-the-c.in` (localhost and PR #188 preview rejected)
- `/playground` 200 HEAD-styled UI fails; 404 passes
- Learn 5xx fails
- Generated SQL is `BEGIN READ ONLY` with no GRANT / ALTER TABLE / INSERT / DROP / alembic upgrade
- Frozen 15 new tables + 9 legacy tables
- DSN rejects password-in-URL and port 6543
