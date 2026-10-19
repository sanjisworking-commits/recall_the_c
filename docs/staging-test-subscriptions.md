# Staging test subscriptions

Operator helper for designated **ordinary** staging accounts. The rows are real `user_subscription` records that pass through the same entitlement, device, and roster checks as subscribers. They are **not** purchases and do not prove billing.

Gate A (this branch) implements the helper and local tests only. **Gate B is not granted:** no staging `--commit`, no Railway env changes, no grants.

## Accounts (labels only until UUIDs are verified)

| Cohort | Email label | Admin role |
|---|---|---|
| Plus | `sanjisworking@gmail.com` | No |
| Pro | `sanj.ritz@gmail.com` | No |
| Max | `sanjali.suryawanshi192@gmail.com` | No |

Allowlist **UUIDs**, not emails. Each account must sign in once on [staging](https://recallthec-production.up.railway.app) so `user_profile` exists. `inspect --email` discovers the UUID and eligibility without `STAGING_TEST_SUBSCRIPTION_UUIDS` or the operator UUID. Record those UUIDs in an operator-local allowlist (`.staging-test-subscriptions.local.env`, gitignored) before `preview`.

Do not add these users to `/admin/admins`. Do not enable `ADMIN_ENABLED`. Do not merge PR #217.

**Free / M1:** signed-in Free evidence for `sanjisworking@gmail.com` is already recorded alongside guest in `docs/design/milestones/M1-evidence.md` (§4 local matrix, §10.3 hosted Playground DV-21). Complete any **outstanding signed-in Free M1 checks before Gate B applies Plus** to that login. Guest evidence cannot substitute. After Plus apply, that identity is the Plus tester.

## Commands

Dry-run is the default. It reads the live rows and reports before/after. It does not insert, update, or delete. `--commit` is Gate B only.

```bash
APP_ENV=staging
STAGING_TEST_SUBSCRIPTIONS_ENABLED=true
STAGING_TEST_SUBSCRIPTION_UUIDS=plus:<plus-uuid>,pro:<pro-uuid>,max:<max-uuid>
STAGING_TEST_SUBSCRIPTION_LABELS=plus:sanjisworking@gmail.com,pro:sanj.ritz@gmail.com,max:sanjali.suryawanshi192@gmail.com
STAGING_TEST_SUBSCRIPTION_OPERATOR_UUID=<operator-uuid>
DATABASE_URL=<staging DSN; never logged>

.venv/bin/python scripts/staging_test_subscriptions.py inspect --email sanjisworking@gmail.com
.venv/bin/python scripts/staging_test_subscriptions.py preview --all
.venv/bin/python scripts/staging_test_subscriptions.py apply --all --commit
.venv/bin/python scripts/staging_test_subscriptions.py apply --uuid <plus-uuid> --state expired --commit
.venv/bin/python scripts/staging_test_subscriptions.py restore --uuid <plus-uuid> --commit
.venv/bin/python scripts/staging_test_subscriptions.py inventory --all
.venv/bin/python scripts/staging_test_subscriptions.py reset --all --commit
```

`restore` writes the original captured baseline (status, tier, periods, metadata). It does not mint a new 28-day period. If that baseline has ended, restore refuses; `renew` is a separate audited operation.

Drift is compared to `last_helper_state`. Restoration uses `baseline`. Those snapshots do not contain each other.

## Guards

Operational `main()` refuses unless **all** hold:

- `APP_ENV=staging` (never `test`, `development`, or `production`)
- `STAGING_TEST_SUBSCRIPTIONS_ENABLED` true
- DSN identity exactly `{host: db.tvygwasuqvtnzjyjtqrq.supabase.co, port: 5432, database: postgres, user: postgres}`
- target UUID allowlisted (`inspect` is the exception: it discovers UUIDs)
- no admin role, no provider-backed row, no unrelated subscription history

`inspect` does not require a pre-existing UUID allowlist. `preview` and every mutation do.

Pooler hostnames fail closed until an exact pooler tuple is recorded. Unknown DSN formats fail closed. A query string may contain only `sslmode` of `prefer`, `require`, `verify-ca`, or `verify-full`. `host`, `hostaddr`, `port`, `dbname`, `options`, and fragments are rejected so they cannot retarget the approved identity. Connect passes explicit host, port, database, user, and password keywords and strips libpq override variables (`PGHOST`, `PGHOSTADDR`, `PGOPTIONS`, and the rest) for that call. Credentials and the raw DSN are never printed.

Reset deletes each verified helper row with `WHERE id = … AND user_id = …` and requires that exact row to disappear. It does not delete by user id alone.

Railway environment name `production` is ignored; it is not `APP_ENV`.

## Staging pin (re-verify at Gate B dry-run)

Read-only probe 2026-10-19T12:50Z of `https://recallthec-production.up.railway.app`:

- `GET /health` → `{"status":"ok"}`
- Guest `/playground` pins `main87` / `mob106` / `pg49` with M1 guest chrome
- `/health` does not expose git SHA. Last documented hosted SHA: `pg-m1-guest-shell` @ `3b37f8947c05577b57af93a2a53f1ac5539c4e3a` (M1-evidence §10). Confirm the live Railway SHA before any `--commit`.
- Repo Alembic head: `20260927_0027`. Confirm live `alembic_version` on the staging DSN at Gate B (read-only).
- Last recorded flags (M1-evidence §10, not re-read from Railway vars in Gate A): `APP_ENV=staging`, `PLAYGROUND_ENABLED=true`, `PRICING_ENABLED=false`, `ADMIN_ENABLED=false`.

**M1:** hosted guest-shell validation exists; not accepted. Open PR #219 (`pg-m1-guest-shell`).

**M2 (UI-fidelity Act heads):** no `docs/design/milestones/M2.md`. Open playground-stack PRs on 2026-10-19: #218 M0 audit, #219 M1 guest shell, #217 admin paywall bypass (do not use), #210 study calendar, #188 UI redesign. None is an M2 Act-heads milestone PR. Absence of a milestone file is not the only check; this branch/PR scan is. Confirm again at Gate B.

Commercial subscription lifecycle (product M2 in `subscriptions/`) already exists. These test rows do not prove Razorpay.

## Evidence boundaries

This helper supports subscription-dependent UI evidence for later milestones. It does not accept M1 or M2 and does not replace a real payment integration test.

Device, roster, and revision rows created during testing are inventoried; subscription reset does not delete them.

## Cleanup before production merge

Remove:

- `scripts/staging_test_subscriptions.py`
- `tests/test_staging_test_subscriptions.py`
- `docs/staging-test-subscriptions.md`
- Staging env vars: `STAGING_TEST_SUBSCRIPTIONS_ENABLED`, `STAGING_TEST_SUBSCRIPTION_UUIDS`, `STAGING_TEST_SUBSCRIPTION_LABELS`, `STAGING_TEST_SUBSCRIPTION_OPERATOR_UUID`
- Helper-owned `user_subscription` rows (`reset --all --commit` while the helper still exists)

Preserve `admin_audit_log`. Keep permanent entitlement/security tests such as `tests/test_entitlement_m3a.py`.
