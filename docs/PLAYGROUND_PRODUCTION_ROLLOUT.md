# Playground production rollout

Executable operator checklist for Stage 1 release. Product rules stay in [PLAYGROUND.md](PLAYGROUND.md). Legacy freeze is in [LEGACY_COMMERCIAL_TRANSITION.md](LEGACY_COMMERCIAL_TRANSITION.md). Close-out evidence is in [PLAYGROUND_M11_REPORT.md](PLAYGROUND_M11_REPORT.md).

Kill switch: `PLAYGROUND_ENABLED=false` 404s `/playground*` and hides entry UI. It does **not** cancel subscriptions, revoke devices, remove roster rows, or reset progress. Constitution Learn and public `/laws` stay up. `/admin` diagnostics and `/api/billing/subscriptions/webhook/razorpay` stay up.

## 0. Identity

```text
AUTHENTICATION
→ USER TYPE
→ SUBSCRIPTION
→ DEVICE
→ MONTHLY ROSTER
→ LAW
→ PROVISION
→ LEARNING
```

Alembic head must be **one**: `20260927_0027`.

## 1. Pre-deploy checks

Tick every line before touching production.

- [ ] CI green on the release SHA (`pytest -m "not integration"`)
- [ ] `alembic heads` prints exactly `20260927_0027`
- [ ] **Production database backup/snapshot taken and verified restorable** (see §2)
- [ ] `RAZORPAY_PLAN_ID_PLUS` / `PRO` / `MAX` set (presence only; do not print values)
- [ ] `RAZORPAY_KEY_ID` present
- [ ] `RAZORPAY_KEY_SECRET` present (never print)
- [ ] `RAZORPAY_WEBHOOK_SECRET` present (never print)
- [ ] Webhook URL still `POST /api/billing/subscriptions/webhook/razorpay`
- [ ] `SUPPORT_EMAIL` looks like an email if device-lock CTAs should include mailto
- [ ] `SUPABASE_URL` + `SUPABASE_ANON_KEY` + `SESSION_SECRET` present
- [ ] `PLAYGROUND_ENABLED=true` intended
- [ ] `PRICING_ENABLED=false` unless a documented legacy-receipt exception exists
- [ ] `ARTICLE_ENTITLEMENTS_ENABLED` may be true or false; signed-in Constitution must not depend on it
- [ ] DNS / app health endpoint (`GET /health`) returns ok
- [ ] Current public commercial copy is Plus ₹199 / Pro ₹399 / Max ₹1,199 monthly only

### Commercial config presence

Use `commercial_config_status()` (admin diagnostics module) or inspect env as **configured / missing** only. Never log secret values.

## 2. Database backup

The application **does not** take its own backup.

If production is Supabase Postgres (see `.env.example` `DATABASE_URL`):

1. Dashboard → Database → Backups, or `pg_dump` / provider snapshot.
2. Record backup id, time (UTC), and who verified it.
3. Confirm the snapshot includes `user_subscription`, `user_device*`, `user_playground_*`, `user_free_articles`, `access_grants`, `billing_orders`.

If backup automation is outside this repo, the operator still records the provider snapshot id here before migrate/deploy. Do not pretend the app made a backup.

## 3. Migration rollout

1. Backup (§2)
2. `alembic current` on production (record the value)
3. Deploy application + `alembic upgrade head`
4. `alembic heads` / `alembic current` → single head `20260927_0027`
5. Smoke (§5)

No downgrade of old tables. No `DROP TABLE`.

Live Postgres proof (disposable DB, not production):

```bash
DATABASE_URL=postgresql://... python3 scripts/verify_postgres_migrations.py
```

CI does not run a live Postgres instance; it parses every revision and asserts one head.

## 4. Legacy UI check

- [ ] Signed-out home HTML has no `href="/pricing"` while `PRICING_ENABLED=false`
- [ ] `/pricing` and `/subscribe/confirm` are 404
- [ ] `/billing/subscriptions` shows Plus / Pro / Max, not 3/7/15/30/60/180/365-day SKUs (old N-day purchase UI is not exposed)

## 5. Smoke matrix

Use a **dedicated test/support account**. Do not complete or modify real user records.

### Guest

- [ ] `/laws` readable
- [ ] `/playground` → Sign in (`/login?next=/playground`)

### Signed-in free

- [ ] All six Constitution modes on a fixture Article
- [ ] `/playground` → Subscribe / billing plans (not a Constitution lock)

### Plus

- [ ] Device registration on first Playground GET
- [ ] 10-law capacity

### Pro

- [ ] 30-law capacity

### Max

- [ ] Unlimited roster (`law_limit` NULL)

### Pending

- [ ] Existing current-roster law still learnable
- [ ] New law blocked

### Third device

- [ ] Constitution still works
- [ ] Playground shows device gate

### Public

- [ ] `/laws` canonical
- [ ] Public law canonical
- [ ] `/playground` `noindex`
- [ ] `/sitemap.xml` has no `/playground` URLs

### Learning (test account only)

- [ ] add one eligible law
- [ ] select one section
- [ ] open six-mode access
- [ ] progress row persists

## 6. Monitoring (already available; not a Stage 2 project)

Watch:

- 5xx rate (request timing logs)
- DB errors
- webhook failures (`subscription_webhook_event.processing_status=failed`)
- subscription reconciliation errors (admin notice + `admin_audit_log`)
- device registration failures (`device_limit` / `device_replacement_limit`)
- roster capacity conflicts
- Bare Act load errors
- migration errors

## 7. Rollback

Prefer:

```text
application rollback
+
preserve new tables/data
```

Do **not** `DROP TABLE` as the first production rollback. Additive M2–M9 tables stay.

### Commercial UI rollback

Set `PLAYGROUND_ENABLED=false`.

- Playground entry/learning UI gone
- subscriptions, devices, roster, progress preserved
- Constitution fully accessible
- public laws readable
- webhook endpoint remains compatible — **keep ingesting**; do not disable Razorpay webhooks without a reconciliation plan

If an older app build still understands `subscription_webhook_event`, leave the webhook URL on. After a UI rollback, run admin **Reconcile from provider** on any account whose dashboard disagrees with Razorpay.

### Migration rollback

App-first. Database downgrade only after an explicit compatibility analysis. Never drop:

- `user_subscription` / charges / webhook events
- `user_device*`
- `user_playground_*`
- `user_free_articles` / `access_grants` / `billing_orders`

## 8. Route inventory (auth/index boundaries)

| Group | Examples |
|-------|----------|
| public | `/`, `/laws`, `/laws/{id}`, `/browse`, `/search`, `/terms`, `/privacy`, `/sitemap.xml` |
| private signed-in | `/dashboard`, `/learn/*`, `/calendar`, `/profile`, `/settings` |
| Playground | `/playground`, `/playground/roster`, `/playground/laws/{id}/...` (`noindex`; `PLAYGROUND_ENABLED`) |
| billing | `/billing/subscriptions*`; webhook `/api/billing/subscriptions/webhook/razorpay` |
| admin | `/admin*` (non-admin → 404) |
| API | Constitution JSON POSTs; no `/api/v1/auth/bootstrap` in this repo |
| SEO | sitemaps from `law_sitemap_manifest.json`; Playground absent |

Native Android/iOS clients are **out of this repo**. Web Google OAuth + session cookie remain. Device platforms stay `web \| android \| ios`.

## 9. Support diagnostics

`GET /admin/users/{id}` answers without SQL and without Act hydration:

- subscribed? tier/status? pending/halted?
- devices, replacement 30d lock
- this month’s roster usage / why add is blocked
- last webhook events for the masked provider subscription id

Mutations (POST + CSRF + reason):

- `reset_devices`
- `clear_device_replacement_limit`
- `reconcile_subscription` (existing `SubscriptionService` machine only)
