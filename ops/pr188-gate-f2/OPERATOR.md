# Gate F2 operator notes — REVISION f2_review_20261016

Review only. There is nothing to run on the Mac for F2.

Do not change Railway. Do not deploy. Do not run Alembic. Do not restore
any dump into live. Do not merge PR #188.

ChatGPT verifies the review document. This gate is paper: code identity
of `0c0a8d5` vs `5d89fbd`, live HTTP identity of recall-the-c.in, and the
closed Gate B / E2 backup record.

If a later HEAD deploy of PR #188 misbehaves, the rollback (still not
authorized by this file) is:

1. Redeploy git `0c0a8d5` on `trustworthy-embrace` / `env` / `recall-th-c`.
2. Keep Alembic `20260927_0027` and the fifteen new tables.
3. Keep `PLAYGROUND_ENABLED=false`.
4. Do not `alembic downgrade`, `alembic stamp`, or restore-into-live.
