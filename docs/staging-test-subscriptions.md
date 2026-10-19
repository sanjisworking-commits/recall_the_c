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
- DSN identity is one of these exact tuples:
  - direct `{host: db.tvygwasuqvtnzjyjtqrq.supabase.co, port: 5432, database: postgres, user: postgres}`
  - session pooler `{host: aws-0-ap-northeast-1.pooler.supabase.com, port: 5432, database: postgres, user: postgres.tvygwasuqvtnzjyjtqrq}`
- target UUID allowlisted (`inspect` is the exception: it discovers UUIDs)
- no admin role, no provider-backed row, no unrelated subscription history

`inspect` does not require a pre-existing UUID allowlist. `preview` and every mutation do.

Any other pooler hostname, user, or port (including transaction-mode `6543`) fails closed. Unknown DSN formats fail closed. A query string may contain only `sslmode` of `prefer`, `require`, `verify-ca`, or `verify-full`. `host`, `hostaddr`, `port`, `dbname`, `options`, and fragments are rejected so they cannot retarget the approved identity. Connect passes explicit host, port, database, user, and password keywords and strips libpq override variables (`PGHOST`, `PGHOSTADDR`, `PGOPTIONS`, and the rest) for that call. Credentials and the raw DSN are never printed.

Reset deletes each verified helper row with `WHERE id = … AND user_id = …` and requires that exact row to disappear. It does not delete by user id alone.

Railway environment name `production` is ignored; it is not `APP_ENV`.

The operator UUID is a real staging account. The nil UUID is rejected for every command that loads the allowlist, including `--commit`.

## Staging pin (recorded 2026-10-19 before any grant)

Read-only probe of `https://recallthec-production.up.railway.app`:

- `GET /health` → `{"status":"ok"}`. That body does not carry a git SHA.
- Guest `/playground` still serves `styles.css?v=main87`, `mobile.css?v=mob106`, `playground.css?v=pg49`.
- Railway deployment metadata (GitHub deployment created by Railway, not `/health`): environment `recallc-playground-staging / production`, Railway environment id `2943667e-f8e2-4967-b59b-489ad6543d78`, deployment `7168307529`, state `success` at `2026-10-19T07:41:49Z`, SHA `3b37f8947c05577b57af93a2a53f1ac5539c4e3a`. No newer deployment exists for that environment. `empathetic-delight / production` is an older SHA (`0c0a8d555748cb5fa63a5fbe0a43998ee5c1d942`, 2026-10-17) and is not this host.
- Helper pooler-identity commit: `fd44d6283fe3cde7ee2772ea2acbcc7d56bd5be0`. That commit is not the hosted web SHA. The helper runs against the database; it is not deployed with this pin.
- Live `alembic_version` on the staging DSN (read-only, 2026-10-19): `20260927_0027`.
- Last recorded flags (M1-evidence §10, not re-read from Railway vars): `APP_ENV=staging`, `PLAYGROUND_ENABLED=true`, `PRICING_ENABLED=false`, `ADMIN_ENABLED=false`.

**M1:** hosted signed-in Free matrix for `sanjisworking@gmail.com` is recorded in `docs/design/milestones/M1-evidence.md` §10.5 on `cursor/hosted-free-m1-matrix-7c6d` (`70f036d7ab11a36877f504624e6cfb3fb701054c`), against staging SHA `3b37f8947c05577b57af93a2a53f1ac5539c4e3a`. Recording the matrix does not accept M1. The 561 px duplicate navigation and overlapping avatar stay open.

## Gate B grants (2026-10-19)

Applied with `apply --all --commit` after a fresh eligibility check. Operator `2093aa58-b6ac-4373-9382-30a66ad17d45`. Database `aws-0-ap-northeast-1.pooler.supabase.com:5432` / `postgres` / `postgres.tvygwasuqvtnzjyjtqrq`. Alembic `20260927_0027`. Three current rows, no charge rows, device and roster counts still 0.

| Cohort | Account | Subscription | Period (UTC) | Audit |
|---|---|---|---|---|
| Plus | `2093aa58-b6ac-4373-9382-30a66ad17d45` | `2f967e11-fdd8-45b7-bec6-6421ad425109` | `2026-10-18T20:30:29Z` – `2026-11-16T20:30:29Z` | `bd77491a-fd60-42ea-99ab-8add6df75df9` |
| Pro | `50cc6c08-beaa-4f21-8bd8-ef7d73c0c47d` | `4b0aaa22-c151-498e-897b-627f5c93dede` | `2026-10-18T20:30:30Z` – `2026-11-16T20:30:30Z` | `cd627b19-ba98-4436-bca6-3349f170a916` |
| Max | `1134a7d0-8d9c-4e12-8d4d-9803f909b24c` | `a04780d7-fe86-4670-a6ca-350208519e5c` | `2026-10-18T20:30:31Z` – `2026-11-16T20:30:31Z` | `41603461-2e6f-4f9f-8a1b-a774f5af775c` |

Each row is `active`, `is_current`, helper-owned, and resolves to its own tier with Playground open. Live profile shows RecallC Plus (10 laws), RecallC Pro (30 laws), and RecallC Max (unlimited), each Active through 17 November in the page's local date. Pro and Max Playground headers still say "Free account"; that copy fallback is unchanged. No expired, halted, or renewal fixtures.

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
