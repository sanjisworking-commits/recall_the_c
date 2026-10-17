# Gate F2 operator notes — REVISION f2_review_20261017e

Review only. Do not Redeploy, Rollback, dump, restore, or change Railway.

## Recorded F2 finding

“Yes — deployment is retained and a restore/redeploy action is available.”

Evidence: `trustworthy-embrace` / `env` / `recall-th-c`, id `76fbfcad`,
Active successful, git `0c0a8d5` (Merge PR #209), `recall-the-c.in`,
uvicorn only, ⋯ visible and **not opened**.

Preserve this distinction: the menu **options** (Rollback / Redeploy)
were not independently verified.

Do **not** Remove `76fbfcad`. Do **not** open ⋯ unless a later rollback
is separately authorized.

## Updated F2 status — PARTIAL PASS

| Requirement | Status |
|---|---|
| Historical deployment retained | PASS |
| Application rollback compatible with schema `0027` | PASS |
| Specific rollback/redeploy menu action | Not directly verified |
| Post-E3 encrypted backup | Pending |
| Disposable restore rehearsal | Pending |
| Full database recovery certification | Not established |

## Next — Gate F3 (not authorized)

Post-E3 backup and disposable recovery rehearsal. Capture production at
Alembic `20260927_0027`, verify an encrypted off-device copy, restore
into an **isolated** database. Do not modify live production.

Do not begin F3 until a later message explicitly authorizes it.
