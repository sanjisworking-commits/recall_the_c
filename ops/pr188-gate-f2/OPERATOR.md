# Gate F2 operator notes — REVISION f2_review_20261017c

Review only. Do not Redeploy, Rollback, or change Railway.

## Still needed from the Mac dashboard (read-only)

Open Railway → `trustworthy-embrace` → `env` → `recall-th-c` → Deployments.

Look for the active `0c0a8d5` deployment (Gate D id `76fbfcad` / Merge PR #209).
Confirm it is retained and that the ⋮ menu offers Rollback and/or Redeploy.
Do **not** click those actions.

This cloud environment cannot open that UI (no Railway dashboard session).
A 2026-10-17 browser open of the Gate D URL was a Railway 404 with Login;
Login was not clicked. GitHub still reports `trustworthy-embrace - recall-th-c`
SUCCESS for `76fbfcad`; that is **not** a substitute for seeing the ⋮ menu.

Leave the form on **Not yet checked**. Submit stays disabled until this
Mac check produces Yes / Visible-no-action / Cannot find.

## If a later HEAD deploy fails (not authorized by this file)

1. Keep `PLAYGROUND_ENABLED=false`.
2. Restore the previous `0c0a8d5` application deployment on
   `recall-th-c` only, after a separate rollback authorization.
3. Leave Alembic at `20260927_0027`. No downgrade, stamp, or DROP.
4. Recheck `/health`, Google sign-in, Browse/Learn, `/playground` JSON 404.

This rollback is for a **restricted** release (Playground off, new
subscriptions not live). `0c0a8d5` has no Razorpay subscription webhook.
