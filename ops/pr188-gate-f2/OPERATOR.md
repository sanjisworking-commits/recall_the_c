# Gate F2 operator notes — REVISION f2_review_20261017f

Review only. Do **not** click Restart, Redeploy, or Remove.

## Recorded overflow menu (Active `76fbfcad`)

Observed labels, none activated:

- Restart
- Redeploy
- Remove (red)

**Rollback is not in this menu.** That is expected: this deployment is
the live Active build. Rollback appears on a previous deployment after a
newer one takes over.

Do **not** click **Remove**. That would drop the retained `0c0a8d5`
image from history.

## F2 status — still PARTIAL PASS

Redeploy of this specific build is verified. Recovery (post-E3 `0027`
backup + isolated restore) is not. PR #188 stays draft.

## Next — Gate F3 (not authorized)

Do not dump, encrypt, or restore until a later explicit F3 authorization.
