# Playground Milestone 11 report

Production hardening, legacy commercial freeze, diagnostics, and Stage 1 close-out. Not a feature redesign. Stage 2 is **not started**.

Authoritative docs:

- [PLAYGROUND.md](PLAYGROUND.md)
- [PLAYGROUND_DELIVERY_TRACKER.md](PLAYGROUND_DELIVERY_TRACKER.md)
- [PAYMENT_ENTITLEMENT_AUDIT.md](PAYMENT_ENTITLEMENT_AUDIT.md)
- [law-loading.md](law-loading.md)
- [LEGACY_COMMERCIAL_TRANSITION.md](LEGACY_COMMERCIAL_TRANSITION.md)
- [PLAYGROUND_PRODUCTION_ROLLOUT.md](PLAYGROUND_PRODUCTION_ROLLOUT.md)

```text
Milestone 11 = DONE
Stage 1 = DONE — 100.0 / 100
Stage 2 = NOT STARTED
Stage 2 may begin only after the Stage 1 release checklist is complete and production-ready state is proven.
```

**Legacy tables/data retained. Current access paths no longer depend on them. Deletion deferred until a separate proven-unused cleanup.**

## Architecture proof

```text
Guest
  ↓ Sign in
Signed-in account
  ↓ full Constitution
Subscription
  ↓
Device
  ↓
Monthly roster
  ↓
Law
  ↓
Sections
  ↓
Read → Cloze → Letters → Type → Recite → Test
  ↓
Learned
  ↓
1 → 3 → 7 → 15 → 30 → 60
  ↓
Mastered
  ↓
Amendment awareness
```

Public law remains verbatim/readable. Historical Constitution progress is not migrated into Playground. Private Playground state stays `noindex`.

## Security

- Guards remain in `playground/access.py`: entitlement snapshot → device ensure → current-period roster → then hydrate.
- Blocked Playground requests hydrate 0 Acts.
- Client UI is presentation only; mutations are server-checked.
- CSRF: `require_csrf` on logout and admin; fail-closed `rtc_csrf` on hosted Playground and subscription mutations when a session exists; webhook HMAC unchanged.
- Mutation allowlist in `tests/test_playground_m11.py` (`MUTATION_ALLOWLIST`).
- Cross-user overlay/selection isolation covered in M11 tests; prior M2–M9 concurrency tests remain.
- Admin override is still a role flag (`admin_override=true`, `is_subscribed=false`, `tier=None`), never a fake Max row. Recovery actions write named `admin_audit_log` rows (`reset_devices`, `clear_device_replacement_limit`, `reconcile_subscription`).

## Performance

- Home still uses batched `list_playground_summaries` (see M1/M6 tests).
- Home / roster / roster-next / Today / Calendar / sitemap: 0 Acts.
- Law workspace / learn / source-review: ≤ 1 Act.
- Entire-Act selection and rollover remain one-transaction batch writes.

## Legacy transition

- Signed-in Constitution is full regardless of `user_free_articles`, `access_grants`, `ARTICLE_ENTITLEMENTS_ENABLED`, or Playground subscription.
- N-day purchase UI frozen behind `PRICING_ENABLED` (default false). Current catalogue is Plus/Pro/Max monthly.
- Historical duration buyers are not auto-subscribed. Never map 365-day → Max.
- Inventory: [LEGACY_COMMERCIAL_TRANSITION.md](LEGACY_COMMERCIAL_TRANSITION.md). Category C not deleted.

## Operations

- Admin user detail: commercial disposition, masked provider id, devices (no HMAC/token), roster peek (does not `ensure_current_period`), webhook events.
- Reconcile uses provider GET + existing state machine. Provider outage: no write, no downgrade, no audit row.
- Kill switch `PLAYGROUND_ENABLED=false`.
- Secrets: `repr=False` on Razorpay key secret, webhook secrets, session secret, Supabase anon key, device HMAC.

## Regression

- Constitution Learn / progress / Bare Acts / admin / device platforms `web|android|ios` unchanged except entitlement inversion already shipped in M3.
- Native Android `Google Identity → Supabase → /api/v1/auth/bootstrap → /me` is **not in this repository**. Web path `GET /auth/google/start` + session cookie remains. Do not invent bootstrap routes.
- Payment lifecycle, refunds, upgrades, roster month boundary: existing M2/M5 tests.

## Database

- Alembic **one head**: `20260927_0027`. No M11 schema migration.
- CI: parse + one-head (`tests/test_migrations.py`).
- Operator live Postgres: `scripts/verify_postgres_migrations.py`.
- SQLite/dev parity unchanged.
- No `DROP` of `user_free_articles` / `access_grants` / `billing_orders`.

## Tests

- `tests/test_playground_m11.py`
- Prior milestone files remain the concurrency/lifecycle corpus.
- Full suite: `python3 -m pytest -m "not integration" -q --tb=line`

## Git

Implementation and tracker SHAs are recorded after the close-out commits on `cursor/playground-220d` / PR `#188`.
