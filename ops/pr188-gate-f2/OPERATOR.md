# Gate F2 operator notes — REVISION f2_review_20261017d

Review only. Do not Redeploy, Rollback, or change Railway.

## Railway finding (closed)

**Yes — deployment is retained and a restore/redeploy action is available.**

Screenshot of `recall-th-c` / `76fbfcad` **Active**, Deployment successful,
Merge PR #209 on `main`, ⋯ present on that deployment. Do **not** open or
click ⋯. Do **not** Remove `76fbfcad`.

Submit F2 finding: choose **Yes**.

## Still open (recovery)

Pre-E3 backup `20261016T072148Z` is 0016-era. Post-E3 `0027` snapshot and
a disposable restore rehearsal are **not** authorized by this file.

## If a later HEAD deploy fails (not authorized by this file)

1. Keep `PLAYGROUND_ENABLED=false`.
2. Restore `76fbfcad` / `0c0a8d5` on `recall-th-c` only, after a separate
   rollback authorization (⋯ Rollback if listed, else Redeploy).
3. Leave Alembic at `20260927_0027`. No downgrade, stamp, or DROP.
4. Recheck `/health`, Google sign-in, Browse/Learn, `/playground` JSON 404.

This rollback is for a **restricted** release (Playground off, new
subscriptions not live). `0c0a8d5` has no Razorpay subscription webhook.
