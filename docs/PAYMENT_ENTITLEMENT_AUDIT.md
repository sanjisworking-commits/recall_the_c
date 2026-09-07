# Payment & entitlement audit (Plus / Pro / Max → Playground)

**Date:** 2026-09-07  
**Scope:** map today’s Razorpay duration-pass system onto RecallC account states plus a **Playground** paid layer. Constitution Learn becomes the signed-in free value.  
**Do not edit:** [`docs/PLAYGROUND_TWO_LAW_AUDIT.md`](PLAYGROUND_TWO_LAW_AUDIT.md) (NDPS/BNS overlay; lives on PR #185 until merge). This document is the payment companion.

**Central question:** What is the minimum entitlement architecture that (a) keeps reading laws free, (b) gives every signed-in user full Constitution RecallC learning, (c) sells Plus/Pro/Max as Playground law-acquisition, and (d) **never deletes user progress** when payment state changes?

**Philosophy (non-negotiable):**

> Payment controls entitlement. It must never control ownership of the user's progress data.

Cancellation, expiry, downgrade, and failed renewal **lock Playground learning**. They do not delete Constitution progress, Playground selections, Cloze, revision, or unlock history.

---

## Review gate (answers)

### 1. Account vs subscription vs tier

Do **not** keep a single overloaded `guest | free | subscribed` for product decisions.

| Axis | Values | Today | Target |
|------|--------|-------|--------|
| **Account** | `guest` \| `authenticated` | `current_user is None` vs signed-in (`auth` middleware) | Unchanged |
| **Subscription** | `none` \| `active` \| `cancel_at_period_end` \| `past_due` \| `expired` | Derived from latest `billing_orders` pass (`active` / `expiring` / `lapsed` only). `is_subscribed()` is a stub (`False`) | Provider subscription object + period bounds |
| **Tier** | `plus` \| `pro` \| `max` \| transitional `legacy` | None. Catalog is `plan_days` (3…365) | Configured product mapping, never hardcoded Razorpay IDs in routes |
| **Capability source** | `none` \| `payment` \| `subscription` \| `admin_override` \| `admin_grant` \| `promotion` \| `legacy` \| `local_owner` | `access_source` on LearnAccess; paid path is `access_grants.source='payment'` | Same idea, plus `admin_override` for Playground unlimited **without pretending Max** |

`EntitlementService` returns both axes. Templates/routes ask **capabilities** (`can_open_playground`, `constitution_learn`, …), never `if plan == "plus"`.

### 2. Constitution article entitlements after the inversion

**Today (when `ARTICLE_ENTITLEMENTS_ENABLED`):** signed-in free users claim **3 Articles**; Type/Recite lock at cap; payment `access_grants` unlocks full Constitution Learn.

**Target:** every **authenticated** user gets `constitution_learn = true` (all six modes, persist Done, Auto Plan eligible on the same terms as today’s subscriber). Constitution **must not** consume Playground quota.

**Guests:** keep today’s exploratory Constitution behaviour (4 open modes, no persist) until a later guest-policy review. This audit does not expand guest persistence.

**Migration:** do not drop `user_free_articles` in the first payment batch. Stop **enforcing** the 3-slot / Type-Recite paywall for authenticated users once the new resolver is on. Paid duration-pass holders keep `legacy` Constitution access through existing `access_grants.ends_at` (already true if we unlock Constitution for all signed-in users). Do **not** map 3-Day/180-Day SKUs onto Plus/Pro/Max by guesswork.

### 3. Provider path for billing cycles

Today: **Razorpay Orders + Standard Checkout**, client HMAC verify, **no webhooks**, **no Subscriptions API**, **no `current_period_start/end`**. Catalog `recurring=True` on 30/60/180/365-day plans is marketing only; `status_from_paid_order` forces `recurring=False`.

**Plus/Pro/Max monthly unlocks require a real billing period.** Proposed path (implementation after this audit):

- New commercial products: RecallC Plus / Pro / Max as **Razorpay Subscriptions** (or Plans + Subscriptions), with **plan IDs in configuration**, not application if-trees.
- Webhook (or verified subscription fetch) is **authoritative** for `active`, `cancel_at_period_end` (access until `current_period_end`), `past_due`, expired.
- Until Subscriptions ship, **do not** fake a calendar-month quota on one-time passes.
- Existing duration passes remain `legacy`: Constitution already free-for-signed-in under target; **no Playground quota** on `legacy` unless a later explicit conversion offer.

### 4. `UserPlaygroundLawEntitlement` vs `user_playground_item`

| Table | Role |
|-------|------|
| `user_playground_law_entitlement` (**new**) | Historical unlock: `UNIQUE(user_id, law_id)`, `first_unlocked_at`, `unlock_period_start`, `tier_at_unlock`. Answers “has this user ever unlocked this law?” Quota counts **first** unlocks whose `unlock_period_start` equals the **current** subscription period start. |
| `user_playground_item` (PR #185 overlay) | Visible activation / last activity. Archive (hide from My Playground) **must not** delete the entitlement row. Re-add of an owned law must not consume quota. |
| `user_playground_selection` / `user_playground_progress` | Learning state. Never deleted on expiry. Writes require `can_use_playground_law`. |

Constitution Articles are **never** rows in the unlock table.

Quota check + insert must be **one transaction** with a uniqueness constraint so two parallel Add requests cannot create 11/10.

### 5. Central EntitlementService

New module (proposed name `constitution_memorizer.entitlements.service`, **not** more branches inside Constitution `compute_learn_access`). Playground and HTTP handlers call it. [`web/billing.py`](src/constitution_memorizer/web/billing.py) stays Razorpay I/O. Playground repositories stay Cloze/progress.

Admin: `admin_override=true`, `can_open_playground=true`, `law_limit=null`. **Not** `tier=max`.

Server-side enforcement (UI is not the boundary): `POST /playground/{law_id}/add`, selection that implies activation, Learn GET/POST complete, any future revision POST. Guests: sign-in CTA only, never checkout.

---

## 1. Existing account states

Resolved in [`src/constitution_memorizer/web/entitlements.py`](src/constitution_memorizer/web/entitlements.py):

| Code | Meaning |
|------|---------|
| `guest` | Multiuser on, no `current_user` |
| `free` | Signed-in, `is_subscribed()` false, no active grant/admin |
| `subscribed` | Multiuser off (local owner) **or** `is_subscribed()` **or** `has_active_recall_access()` |

`is_subscribed(user)` **always returns `False`**. Paid Constitution access is **not** that function. It is `has_active_recall_access()` → `AccessOverride.has_recall_access` → admin role **or** unrevoked `access_grants` row (`admin_grant` / `promotion` / `payment`) with `starts_at ≤ now` and `ends_at` null or in the future ([`admin/store.py`](src/constitution_memorizer/admin/store.py)).

Guest vs authed HTTP: [`auth/guest.py`](src/constitution_memorizer/auth/guest.py) (`GUEST_PUBLIC_PREFIXES`, `AUTH_REQUIRED_PREFIXES`). `/laws` is guest-readable. `/playground` is **not** on main yet (PR #185); on that branch guests are redirected to login by the handler, not by the prefix list.

---

## 2. Existing free-user behaviour

Flag: `ARTICLE_ENTITLEMENTS_ENABLED` → `entitlements_active()`. **Default false** (legacy: all six Constitution modes, no claim UI).

When the flag is on:

| Actor | Constitution Learn |
|-------|-------------------|
| Guest | `read`, `cloze`, `letters`, `test` open; Type/Recite locked; no persist Done/`modes_seen` |
| Free + claimed Article | All 6, persist |
| Free + slots remaining | All 6, claim prompt on Done, provisional modes |
| Free + 3/3 cap, unclaimed | 4 open modes; Type/Recite locked; Done → subscription gate (`402` / `?gate=subscription`) |
| Grant / admin / payment grant | Full access; `access_source` distinguishes; `is_subscribed` stays false for admin/grant |

`FREE_ARTICLE_LIMIT = 3`. Table `user_free_articles`. Grandfathering: Articles with `times_completed >= 1` backfilled once (`legacy_over_cap` possible).

**Laws / Bare Acts:** not on this matrix. Feature flag `RELEVANT_LAWS_ENABLED` 404s `/laws*` only. Reading is free.

**Playground (PR #185, not on `main` as of this audit):** any signed-in user may add NDPS/BNS and Cloze with **no payment check**.

---

## 3. Existing plans / products

[`src/constitution_memorizer/web/pricing.py`](src/constitution_memorizer/web/pricing.py): **one product, seven durations**. Identity = integer `plan_days`. **No Plus/Pro/Max. No Razorpay plan IDs.**

| Days | INR | Catalog `recurring` | Runtime |
|------|-----|---------------------|---------|
| 3 | 49 | false | One-time pass |
| 7 | 99 | false | One-time pass |
| 15 | 149 | false | One-time pass |
| 30 | 199 | true | Still one-time pass |
| 60 | 299 | true | Still one-time pass |
| 180 | 699 | true | Hero `DEFAULT_DAYS`; still one-time pass |
| 365 | 999 | true | Still one-time pass |

Copy says “Renews every N days” for longer SKUs; `status_from_paid_order` **always** sets `recurring=False`.

---

## 4. Provider integration

| Item | Location / behaviour |
|------|----------------------|
| Orders API | `POST https://api.razorpay.com/v1/orders` in [`billing.py`](src/constitution_memorizer/web/billing.py) |
| Checkout | Razorpay Checkout.js; client sends `{days}` only; server prices from catalog |
| Verify | `POST /api/billing/verify` HMAC-SHA256 `order_id\|payment_id` |
| Env | `PRICING_ENABLED`, `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET` ([`multiuser/settings.py`](src/constitution_memorizer/multiuser/settings.py)) |
| Live checkout | `billing_enabled()` = pricing flag **and** both keys |
| Webhooks | **None** |
| Subscriptions API | **None** |
| Hardcoded plan IDs | **None** (good); amounts are `price_inr * 100` |

Failure mode: user pays in Checkout then closes the tab before verify → **no grant** (no webhook reconciliation).

Purchase flow: `/pricing` → `/subscribe/confirm` → `/subscribe/pay` → order → Checkout → verify → `access_grants` `source=payment`, `ends_at = now + plan_days` → onboarding or `/subscribe/result`.

---

## 5. Subscription DB model

**There is no `subscriptions` table.**

| Table | Migration | Role |
|-------|-----------|------|
| `billing_orders` | [`20260818_0007_billing_orders.py`](alembic/versions/20260818_0007_billing_orders.py) | `order_id`, `user_id`, `plan_days`, `amount_paise`, `status` `created`\|`paid`, `razorpay_payment_id`, timestamps |
| `access_grants` | [`20260818_0006`](alembic/versions/20260818_0006_admin_roles_grants_audit.py) + 0007 source `'payment'` | Capability window: `starts_at`, `ends_at`, `revoked_at`, `reason` (`razorpay:{order_id}` for payments) |
| `user_roles` | 0006 | `admin` only |
| `user_free_articles` | 0004 | Constitution free claims |

Paid grant insert is **the same transaction** as marking the order paid (`mark_billing_order_paid`). Replay verify is idempotent (no second grant).

Profile lifecycle uses `latest_paid_billing_order()`, not a subscription id.

---

## 6. Current entitlement / paywall checks

No dedicated paywall middleware. Layers:

1. Auth guest gate ([`guest.py`](src/constitution_memorizer/auth/guest.py)).
2. Feature flags (`PRICING_ENABLED` 404s pricing routes; `ARTICLE_ENTITLEMENTS_ENABLED` for Learn matrix; `RELEVANT_LAWS_ENABLED` for `/laws`).
3. [`entitlements.py`](src/constitution_memorizer/web/entitlements.py): `resolve_learn_access`, `compute_learn_access`, `can_use_auto_plan`, `access_summary`, `subscription_status`.
4. Learn POST `/seen`, `/quiz`, Done, speech routes check `access.is_locked(mode)`.
5. Billing routes require signed-in user (`_billing_user`).

Templates (`learn.html`, `_locked_mode.html`, dashboard, profile, pricing) branch on `is_guest`, `access.is_free`, `pricing_enabled` — not on duration.

Playground (PR #185): **no** entitlement import; sign-in only.

---

## 7. Webhook lifecycle

**Does not exist.** Lifecycle is Checkout success handler → `/api/billing/verify`.

Target (post-audit): Razorpay subscription webhooks (`subscription.authenticated`, `subscription.activated`, `subscription.charged`, `subscription.pending`, `subscription.halted`, `subscription.cancelled`, `subscription.completed`) mapped to RecallC subscription states. Store provider event ids for idempotency. Client verify must not be the only grant path.

---

## 8. Cancellation / expiry handling

| Mechanism | Today |
|-----------|--------|
| Pass expiry | `access_grants.ends_at`; store query drops expired grants; user returns to Free Constitution matrix |
| UI | `active` / `expiring` (≤7 days) / `lapsed` from latest paid order |
| `renewal_failed` / `cancelled` | Template copy exists; **never emitted** by `status_from_paid_order` |
| Cancel endpoint | **None** |
| Auto-renew | **None** |
| Admin revoke | `POST /admin/grants/{id}/revoke` sets `revoked_at` |
| Extend | Buy another duration pass (“Extend Recall”) |
| Progress on expiry | Constitution `learning_unit_progress` **kept**. Free matrix may **lock Type/Recite** and block Done on unclaimed Articles. **No row deletion.** |

Target Playground expiry: same ownership rule — **lock learning, keep rows**, CTA **Resume your Playground**.

`cancel_at_period_end`: not representable today. Must map from provider: Playground remains available until `current_period_end`.

---

## 9. Current admin bypass

[`AccessOverride.has_recall_access`](src/constitution_memorizer/admin/store.py) = `is_admin` **or** effective grant. Independent of `ADMIN_ENABLED` (console flag). Used by `resolve_learn_access` as `access_source="admin"` while `level` stays `subscribed` — **no fake purchase**.

Admin Entitlement Preview (`rtc_admin_preview`) simulates Learn locks only; **does not persist**; ignored by `can_use_auto_plan`.

**Playground (PR #185):** no admin bypass. An admin is a normal signed-in user.

Target: EntitlementService `admin_override` → Playground enabled, `law_limit=null`, `tier` unset / not Max.

---

## 10. Existing active-user migration risks

| Risk | Why it matters |
|------|----------------|
| **Product inversion** | Paying users bought **Constitution** duration access. Target makes Constitution free for all signed-in users. Do not charge them again for Constitution. Do not silently give Playground Max. |
| **No subscription object** | Cannot invent `current_period_*` from `plan_days` without a documented conversion offer. |
| **Orphan payments** | Paid in Razorpay, never verified → no `access_grants`. Webhook backfill is a later ops batch, not guesswork mapping. |
| **Catalog `recurring` lie** | Users may believe auto-renew exists. Communication required before Subscriptions launch. |
| **`is_subscribed` stub** | Any new code that ORs this function without grants will treat **everyone as unpaid**. |
| **Playground already open (PR #185)** | Signed-in users may add NDPS/BNS before paywalls exist. On entitlement launch, treat existing `user_playground_item` rows as **grandfathered unlocks** (write entitlement rows in a migration, **do not** count them against the first Plus cycle). |
| **3 free Articles** | Turning off enforcement must not delete `user_free_articles`. |
| **Admin/promo grants** | Keep Constitution (and, if product agrees, Playground) via `admin_grant` / `promotion` without a Max SKU. |

**Transitional `legacy`:** duration-pass grant still active → `subscription_status=legacy_active`, `tier` null, Constitution full (redundant once all signed-in are full), **Playground still locked** unless product later grants a conversion coupon. Do not assign Plus/Pro/Max from day-count.

---

## 11. Proposed Plus / Pro / Max mapping

After migration, commercial products:

| Product | Internal `tier` | Playground | New law unlocks per **provider billing period** |
|---------|-----------------|------------|--------------------------------------------------|
| RecallC Plus | `plus` | yes | 10 |
| RecallC Pro | `pro` | yes | 30 |
| RecallC Max | `max` | yes | unlimited (`law_limit=null`) |

Provider plan IDs: configuration (env or a small `billing_products` table), e.g. `product_tier=plus`, `provider_plan_id=<configured>`. Feature code never switches on the Razorpay id.

Pricing **amounts** are out of this audit (set at launch). Existing 3…365 day SKUs remain **legacy catalog** until retired; they must not be reused as Plus/Pro/Max aliases.

Constitution: **all authenticated users**, all tiers, including `subscription=none`.

---

## 12. Central EntitlementService design

```text
PAYMENTS (Razorpay I/O)
    → SUBSCRIPTION records (status + period + tier mapping)
        → EntitlementService.resolve(user, now)
            → Constitution Learn (authenticated → full)
            → Playground (capabilities + quota)
```

Conceptual snapshot:

```json
{
  "authenticated": true,
  "subscription": "active",
  "tier": "plus",
  "constitution_learn": true,
  "playground": true,
  "can_activate_new_law": true,
  "law_limit": 10,
  "used": 4,
  "remaining": 6,
  "current_period_start": "2026-09-12",
  "current_period_end": "2026-10-11",
  "admin_override": false,
  "access_source": "subscription"
}
```

Max: `"law_limit": null, "used": <count or omit>, "remaining": null`.

Expired subscriber with history: `"subscription": "expired", "playground": false, "constitution_learn": true` (if authenticated). Progress rows still exist.

Playground code asks `assert_can_use_law(user, law_id)` / `assert_can_unlock(user, law_id)`. It does not import Razorpay.

Constitution `compute_learn_access` should eventually treat authenticated as full when the new flag/path is on, **without** reading Playground quota.

---

## 13. Playground law-unlock accounting

Activation:

```text
Add to Playground
  → guest? Sign-in CTA (preserve law in next=); never checkout
  → authenticated, no eligible subscription? Unlock Playground CTA (Plus/Pro/Max)
  → already entitled UNIQUE(user_id, law_id)? allow (re-show item); no quota
  → else quota in one transaction
       Plus used < 10 / Pro used < 30 / Max skip
       insert entitlement (period start + tier_at_unlock)
       upsert user_playground_item
```

**Used this cycle:** count entitlement rows for this user where `unlock_period_start = current_period_start` (provider). Not: visible cards, not: Cloze completions, not: Constitution.

Remove/archive: set item status hidden; entitlement remains; **no refund**.

NDPS and BNS are ordinary `law_id`s. Quota is **laws**, not sections.

---

## 14. Billing-cycle calculation

Authoritative: provider `current_period_start` / `current_period_end` on the **subscription**, stored on our subscription row and refreshed by webhook.

Example: start 12 Sep → period through 11 Oct; Plus 10 new laws; reset is **not** 1 Oct.

If the provider is unavailable: fail closed for **new** unlocks; do not invent a calendar month. Existing entitled laws remain usable while local status is still `active` or `cancel_at_period_end` with `now < period_end`.

Upgrade mid-cycle: keep `used`; raise `law_limit` (7/10 → 7/30). Do not reset used to 0.

Downgrade: historical unlocks stay; new unlocks use the **new** limit for the current period (`used` unchanged, remaining = max(0, new_limit - used); if used ≥ 10 on Plus, remaining 0 until next period).

---

## 15. Downgrade / upgrade behaviour

| Change | Entitlements | Quota | Progress |
|--------|--------------|-------|----------|
| Max → Plus | All previously unlocked laws stay usable while subscription eligible | New unlocks: Plus 10/period; lifetime size not capped at 10 | Unchanged |
| Plus → Pro | Unchanged ownership | used kept; limit 30 | Unchanged |
| Pro → Max | Unchanged | unlimited immediately | Unchanged |
| Any → expired | Laws remain in DB; learning locked | n/a | Unchanged |

Do not lock laws because total history > 10.

---

## 16. Expiry / resubscription behaviour

Expiry / lapsed / cancelled after `period_end`:

- Constitution: still full if authenticated.
- Law library: still readable.
- Playground Learn / revision / new unlocks: locked.
- UI: **Resume your Playground**, not empty-state new user.
- Data: do **not** DELETE `user_playground_*` or entitlement rows.

Resubscribe: same user, same unlocks immediately available; new period `used` starts at 0 for **new** laws only.

Past due: product choice for implementation — recommend **lock new unlocks**, keep already-unlocked learning until provider marks expired (document in Batch that adds webhooks). Do not delete data.

---

## 17. DB changes (proposed; not in this phase)

| Object | Purpose |
|--------|---------|
| `user_subscription` | `user_id`, provider customer/subscription ids, `status`, `tier`, `current_period_start`, `current_period_end`, `cancel_at_period_end`, timestamps |
| `billing_products` or env map | `tier` → `provider_plan_id` |
| `user_playground_law_entitlement` | `user_id`, `law_id`, `first_unlocked_at`, `unlock_period_start`, `tier_at_unlock`; UNIQUE `(user_id, law_id)`; RLS enable, no policies |
| Optional `billing_webhook_events` | Idempotent provider event ids |
| Keep | `billing_orders`, `access_grants` (legacy passes + admin/promo), `user_free_articles` (stop enforcing, don’t drop) |
| Playground overlay tables | Unchanged ownership; item “archive” column or status if missing |

SQLite + Alembic dual path, same as overlay (`ENABLE ROW LEVEL SECURITY`, app role bypasses).

Atomic unlock: `INSERT … ON CONFLICT DO NOTHING` returning whether inserted; if inserted, `SELECT COUNT(*) WHERE unlock_period_start = :period` must be `<= limit` else rollback. Serialisable / row lock on a per-user quota ledger if counts race.

---

## 18. API / backend changes (proposed; not in this phase)

- `EntitlementService` + tests; stop using stub `is_subscribed()` as the paid seam.
- Playground add/learn/complete: capability asserts; 401 guest; 402/redirect subscribe; 403 quota with reset date.
- Billing: Subscriptions create/cancel + webhook; keep Orders path for `legacy` until retired.
- Constitution Learn: authenticated → `_full_access` when new policy flag on; guests unchanged.
- Admin: Playground `admin_override`.
- Intended action after login: guest Add → `/login?next=/laws/{id}` (or `/playground/{id}/add` once CSRF-safe GET resume); after login, re-evaluate subscription before unlocking.

---

## 19. UI / paywall changes (proposed; not in this phase)

| Actor | Add to Playground |
|-------|-------------------|
| Guest | **Sign in to use Playground** — existing sign-in CTA. **No checkout.** |
| Authenticated, no eligible Playground sub | **Unlock Playground** — Plus 10 / Pro 30 / Max unlimited |
| Plus at 10/10 | Copy: used 10 unlocks this cycle; **Available again: {period_end}**; Upgrade Pro / Max |
| Pro at 30/30 | Offer Max |
| Entitled | Add / Open Playground as today |

My Playground allowance (not intrusive):

- Plus: “4 new laws unlocked this cycle · 6 remaining · Resets 12 October”
- Pro: “18 / 30 new laws · 12 remaining”
- Max: “Unlimited law access”
- Never include Constitution in totals

Expired: **Resume your Playground** → subscribe. Existing laws listed, Learn locked.

Do not scatter `plan === "plus"` in JS as a security boundary.

---

## 20. Exact implementation batches (stop after this document)

| Batch | Work | Depends on |
|-------|------|------------|
| **0 (this)** | `PAYMENT_ENTITLEMENT_AUDIT.md` only | — |
| **A** | `user_subscription` + product config + webhook/status mapping (`active`, `cancel_at_period_end`, `past_due`, expired). No Playground quota yet. Preserve duration-pass `access_grants` as `legacy`. | Review of this audit |
| **B** | `EntitlementService`; split account vs subscription vs tier; admin_override; Constitution authenticated = full Learn (flag); do not delete `user_free_articles`. | A |
| **C** | `user_playground_law_entitlement`; atomic quota; grandfather PR #185 `user_playground_item` into entitlements **without** burning the first cycle; Playground server gates; archive ≠ refund. | B, Playground overlay merged or same train |
| **D** | UI: guest sign-in CTA; signed-in Unlock Playground; allowance + limit-reached; Resume CTA; pricing page Plus/Pro/Max. | C |
| **E** | Retire or freeze 3…365 duration catalog; optional Razorpay order backfill; convert offer for `legacy` → a Playground tier **only if product names a SKU**. | D |

**Out of Batch 0:** Razorpay Subscriptions, schema, EntitlementService code, Playground 402s, Constitution paywall removal.

**Proof Constitution progress ownership:** no batch may `DELETE FROM learning_unit_progress` or Playground progress tables because subscription changed. Tests: expire a fixture user → rows remain; resubscribe → Learn works without reset.

---

## Confirmation

- [`PLAYGROUND_TWO_LAW_AUDIT.md`](PLAYGROUND_TWO_LAW_AUDIT.md) is not rewritten here.
- Payment and Playground stay separate domains: payments → subscription → entitlements → Playground capabilities.
- **Payment controls entitlement. It must never control ownership of the user's progress data.**
