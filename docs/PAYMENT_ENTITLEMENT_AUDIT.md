# Payment & entitlement audit (Plus / Pro / Max → Playground)

**Date:** 2026-09-07  
**Scope:** map today’s Razorpay duration-pass system onto RecallC account states plus a **Playground** paid layer. Constitution Learn becomes the signed-in free value.  
**Companion:** [`docs/PLAYGROUND_TWO_LAW_AUDIT.md`](PLAYGROUND_TWO_LAW_AUDIT.md) (NDPS/BNS overlay on `cursor/playground-220d`). This document is the payment companion. Do not merge overlay architecture into this file.

**Central question:** What is the minimum entitlement architecture that (a) keeps reading laws free, (b) gives every signed-in user full Constitution RecallC learning, (c) sells Plus/Pro/Max as Playground law-acquisition, and (d) **never deletes user progress** when payment state changes?

**Philosophy (non-negotiable):**

> Payment controls entitlement. It must never control ownership of the user's progress data.

Cancellation, expiry, downgrade, and failed renewal **lock Playground learning**. They do not delete Constitution progress, Playground selections, Cloze, revision, or unlock history.

**Single product truth (locked):**

> Guest = explore. Account = complete Constitution. Subscription = Playground. Tier = how many new laws you can bring into Playground.

| User type | Constitution | Laws | Playground |
|-----------|--------------|------|------------|
| **Guest** | Read + existing guest Learn (no persist) | Read | No access → **Sign in** |
| **Signed-in**, no active Playground subscription | **All Articles, all six modes** | Read | No learning → **Subscribe** |
| **plus** | Full | Read | Full Playground learning, **10 new laws / quota period** |
| **pro** | Full | Read | Full Playground learning, **30 new laws / quota period** |
| **max** | Full | Read | Full Playground learning, **unlimited** |

Tiers do **not** differ in modes, ladders, Cloze, or revision quality. They differ only in new-`law_id` quota.

```text
Who is the user?
        │
        ├── Guest
        │      Constitution → existing guest rules
        │      Laws → read
        │      Playground → sign in
        │
        ├── Signed-in / no active Playground subscription
        │      Constitution → FULL
        │      Laws → read
        │      Playground → subscribe
        │
        └── Active subscriber
               Constitution → FULL
               Laws → read
               Playground → FULL
                    │
                    └── new-law quota by tier (plus 10 / pro 30 / max unlimited)
```

Article-level entitlements (3 free Articles, claims, slots, Type/Recite as premium, per-Article gates) **disappear from active access decisions**. Rows may remain in the DB unread until a later drop.

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

`EntitlementService` (when built) asks **user type**, then only:

1. Can this user use Playground learning?
2. Can this user unlock another new `law_id` this quota period?

Templates/routes never branch `if plan == "plus"` for modes. Never `if tier == max` for Cloze quality.

### 2. Constitution: no article-level entitlement in the new resolver

**Today (when `ARTICLE_ENTITLEMENTS_ENABLED`):** signed-in free users claim **3 Articles**; Type/Recite lock at cap; payment `access_grants` unlocks full Constitution Learn.

**Locked target:** `authenticated = true` → Constitution Learn = **full** (all Articles, all six modes, persist). The new resolver **never asks**:

- Has this Article been claimed?
- How many slots remain?
- Is this mode premium?
- Is Type/Recite allowed?
- Has the user crossed the free Article limit?

**Guests:** keep **today’s** guest Learn (four open modes, no persist). Do not invent a new guest matrix.

**Migration:** do **not** delete `user_free_articles`, `access_grants`, `billing_orders`, or duration-pass history. Stop **reading** them for allow/deny once the user-type resolver is on. A technical kill-switch may flip old resolver → new resolver for deploy/rollback; that is **not** a second product model and not an open architecture question. Drop obsolete tables only after nothing depends on them. Do **not** map 3-Day/180-Day SKUs onto plus/pro/max.

### 3. Provider path for billing cycles

Today: **Razorpay Orders + Standard Checkout**, client HMAC verify, **no webhooks**, **no Subscriptions API**, **no `current_period_start/end`**. Catalog `recurring=True` on 30/60/180/365-day plans is marketing only; `status_from_paid_order` forces `recurring=False`.

**Plus/Pro/Max unlocks are 10 / 30 new laws per month**, not “whatever period the provider invoices.” `quota_period` and `billing_period` are separate clocks (see §14 and the decision gate). Proposed path (implementation after this audit **and** after the decision gate’s open cells are filled):

- New commercial products: RecallC Plus / Pro / Max as **Razorpay Subscriptions** (or Plans + Subscriptions), with **plan IDs in configuration**, not application if-trees.
- Webhook (or verified subscription fetch) is **authoritative** for `active`, `cancel_at_period_end` (access until `current_period_end`), `past_due`, expired.
- Until Subscriptions ship, **do not** fake a calendar-month quota on one-time passes.
- Existing duration passes remain `legacy`: Constitution already free-for-signed-in under target; **no Playground quota** on `legacy` unless a later explicit conversion offer.

### 4. `UserPlaygroundLawEntitlement` vs `user_playground_item`

| Table | Role |
|-------|------|
| `user_playground_law_entitlement` (**new**) | Historical unlock of `law_id` (not a JSON version): `UNIQUE(user_id, law_id)`, `first_unlocked_at`, `unlock_quota_period_start`, `tier_at_unlock`. Answers “has this user ever unlocked this law?” Quota counts **first** unlocks whose `unlock_quota_period_start` equals the **current quota period** start. |
| `user_playground_item` (existing overlay on `cursor/playground-220d`) | Visible activation / last activity. Archive (hide from My Playground) **must not** delete the entitlement row. Re-add of an owned law must not consume quota. |
| `user_playground_selection` / `user_playground_progress` | Learning state. Never deleted on expiry. Writes require `can_use_playground_law`. |

Constitution Articles are **never** rows in the unlock table.

Quota check + insert must be **one transaction** with a uniqueness constraint so two parallel Add requests cannot create 11/10.

### 5. Central EntitlementService

New module (proposed name `constitution_memorizer.entitlements.service`). **Do not** grow Constitution `compute_learn_access` article matrices. The new path does not read `user_free_articles` for access.

Playground and HTTP handlers call the service. [`web/billing.py`](src/constitution_memorizer/web/billing.py) stays Razorpay I/O. Playground repositories stay learning/progress.

Resolved snapshot is **user type** + Playground answers only:

- `authenticated`
- `playground` (can use learning on already-unlocked laws)
- `can_unlock_new_law` + `law_limit` / `used` / `remaining` (`null` = max)

Admin: `admin_override=true`, Playground enabled, `law_limit=null`. **Not** `tier=max`.

Tiers never gate individual Learn modes. An unlocked law gets the **same** Cloze / Type / Recite / Letters / Test / revision as any other paid tier.

Server-side enforcement (UI is not the boundary): add/confirm unlock, Learn writes, revision writes. Guests: sign-in CTA only, never checkout.

---

## 1. Existing account states

Resolved in [`src/constitution_memorizer/web/entitlements.py`](src/constitution_memorizer/web/entitlements.py):

| Code | Meaning |
|------|---------|
| `guest` | Multiuser on, no `current_user` |
| `free` | Signed-in, `is_subscribed()` false, no active grant/admin |
| `subscribed` | Multiuser off (local owner) **or** `is_subscribed()` **or** `has_active_recall_access()` |

`is_subscribed(user)` **always returns `False`**. Paid Constitution access is **not** that function. It is `has_active_recall_access()` → `AccessOverride.has_recall_access` → admin role **or** unrevoked `access_grants` row (`admin_grant` / `promotion` / `payment`) with `starts_at ≤ now` and `ends_at` null or in the future ([`admin/store.py`](src/constitution_memorizer/admin/store.py)).

Guest vs authed HTTP: [`auth/guest.py`](src/constitution_memorizer/auth/guest.py) (`GUEST_PUBLIC_PREFIXES`, `AUTH_REQUIRED_PREFIXES`). `/laws` is guest-readable. Playground routes on this overlay redirect guests to login in the handler (`/login?next=…`), not via `AUTH_REQUIRED_PREFIXES`.

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

**Playground (existing overlay on `cursor/playground-220d`):** any signed-in user may add NDPS/BNS and Cloze with **no payment check**.

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

Playground (existing overlay): **no** entitlement import; sign-in only.

---

## 7. Webhook lifecycle

**Does not exist.** Lifecycle is Checkout success handler → `/api/billing/verify`.

Target (after Batch A, blocked until the decision gate is filled): Razorpay subscription webhooks mapped to RecallC states. **Acceptance (hard):** validate `X-Razorpay-Signature` against the **raw request body**; persist `x-razorpay-event-id` for idempotency; tolerate duplicates and out-of-order delivery; support webhook-secret rotation; provider-fetch reconciliation when local state is ambiguous. Client Checkout verify must not be the only grant path.

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

**Playground (existing overlay):** no admin bypass. An admin is a normal signed-in user.

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
| **Playground already open on this overlay** | Signed-in users may add NDPS/BNS before paywalls exist. On entitlement launch, treat existing `user_playground_item` rows on `cursor/playground-220d` as **grandfathered unlocks** (write entitlement rows in a migration, **do not** count them against the first Plus quota period). |
| **3 free Articles** | Turning off enforcement must not delete `user_free_articles`. |
| **Admin/promo grants** | Keep Constitution (and, if product agrees, Playground) via `admin_grant` / `promotion` without a Max SKU. |

**Transitional `legacy`:** duration-pass grant still active → `subscription_status=legacy_active`, `tier` null, Constitution full (redundant once all signed-in are full), **Playground still locked** unless product later grants a conversion coupon. Do not assign Plus/Pro/Max from day-count.

---

## 11. Proposed Plus / Pro / Max mapping

After migration, commercial products:

| Product | Internal `tier` | Playground | New law unlocks per **quota period (month)** |
|---------|-----------------|------------|-----------------------------------------------|
| RecallC Plus | `plus` | yes | 10 |
| RecallC Pro | `pro` | yes | 30 |
| RecallC Max | `max` | yes | unlimited (`law_limit=null`) |

Public `display_name` (e.g. “RecallC Plus”) is configuration, not entitlement logic. Internal codes stay `plus` / `pro` / `max`.

Provider plan IDs: configuration (env or a small `billing_products` table), e.g. `product_tier=plus`, `provider_plan_id=<configured>`. Feature code never switches on the Razorpay id **or** on marketing names.

Pricing **amounts**, GST, and display names are **open** (decision gate — fill before creating Razorpay Plans). Existing 3…365 day SKUs remain **legacy catalog** until retired; they must not be reused as Plus/Pro/Max aliases.

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
  "quota_period_start": "2026-09-12",
  "quota_period_end": "2026-10-11",
  "admin_override": false,
  "access_source": "subscription"
}
```

Max: `"law_limit": null, "used": <count or omit>, "remaining": null`.

Expired subscriber with history: `"subscription": "expired", "playground": false, "constitution_learn": true` (if authenticated). Progress rows still exist.

Playground code asks `assert_can_use_playground(user)` and `assert_can_unlock(user, law_id)`. It does not import Razorpay. It does not ask which modes the tier allows.

Constitution Learn for authenticated users is **full** in the new resolver. `compute_learn_access` article questions are not used. A kill-switch may keep the old resolver live during cutover; the new resolver never reads claims.

---

## 13. Playground law-unlock accounting

A law unlock is consumed only for a **first** `UNIQUE(user_id, law_id)` insert, and only after **confirm**. Accidental Add must not burn the last slot.

```text
Add to Playground
  → guest? Sign-in CTA (preserve law in next=); never checkout
  → authenticated, no eligible subscription? Unlock Playground CTA (Plus/Pro/Max)
  → already entitled UNIQUE(user_id, law_id)? allow (re-show item); no quota
  → else show confirm: “This will use 1 of your N law unlocks”
       cancel → no write
       confirm → quota check + entitlement insert in one transaction
                  Plus used < 10 / Pro used < 30 / Max skip
                  stamp unlock_quota_period_start + tier_at_unlock
                  upsert user_playground_item
```

**Used this quota period:** count entitlement rows for this user where `unlock_quota_period_start` equals the current **quota period** start. Not: visible cards, not: Cloze completions, not: Constitution, not: the Razorpay invoice period if that period is annual.

Remove/archive: set item status hidden; entitlement remains; **no quota refund**. Payment refund / chargeback is a **separate** commercial rule (decision gate — open).

The commercial object is `law_id` (e.g. `ndps`), not “NDPS version X”. If the Bare Act JSON is amended, the user still owns that law and does **not** spend another monthly unlock. `source_hash` on selection/progress flags review; it does not reopen the shop.

NDPS and BNS are ordinary `law_id`s. Quota is **laws**, not sections.

---

## 14. Quota period vs billing period

The product promise is **10 / 30 new laws per month**. That clock is `quota_period`, **not** `billing_period`.

| Clock | Meaning |
|-------|---------|
| `billing_period` | Provider invoice window (`current_period_start` / `current_period_end` on the subscription). May later be annual. |
| `quota_period` | Window that counts new `law_id` unlocks (Plus 10 / Pro 30). Default model: **one calendar-aligned or subscription-anchor month**, independent of whether the customer pays monthly or annually. |

An annual Razorpay plan must **not** mean 10 laws per year. Whether MVP ships monthly-only subscriptions or annual plans with a 30-day quota period is **open** (decision gate — Batch A schema). Implementation must still store both clocks from day one.

Example (monthly billing that matches quota): start 12 Sep → quota through 11 Oct; Plus 10 new laws; reset is **not** 1 Oct unless the quota period is defined that way.

If the provider is unavailable: fail closed for **new** unlocks; do not invent a month. Existing entitled laws remain usable while local status still grants Playground access (see state→access matrix — open).

Upgrade mid-cycle: keep `used`; raise `law_limit` (7/10 → 7/30). Do not reset used to 0.

Downgrade **does not apply mid-cycle** (locked commercial rule, §15): until next renewal the user keeps the higher tier’s limit. After renewal, historical unlocks stay; new unlocks use Plus 10 for the new quota period (`used` for that new period starts at 0).

---

## 15. Downgrade / upgrade behaviour

Quota math after a tier change was already defined (keep `used`, raise/lower **new-unlock** limit, never lock historical laws because lifetime size > 10). The **commercial event** is separate.

**Locked:** **upgrade immediately** (Razorpay update now; extra charge may be prorated). `used` is preserved; `law_limit` becomes the new tier’s monthly cap at once. **Downgrade at next renewal** (schedule the plan change at cycle end). No mid-cycle refund, no mid-cycle quota shrink.

| Change | When it applies | Entitlements | Quota | Progress |
|--------|-----------------|--------------|-------|----------|
| Plus → Pro / Max | Immediately | Unchanged ownership | `used` kept; limit 30 or unlimited | Unchanged |
| Max / Pro → Plus | Next renewal | All previously unlocked laws stay usable while subscription eligible | New quota period uses Plus 10; lifetime size not capped at 10 | Unchanged |
| Any → expired | At period end / per state matrix | Laws remain in DB; learning locked | n/a | Unchanged |

One RecallC user may have **one** current commercial Playground subscription. A second purchase is an upgrade/change of that subscription, not a parallel Razorpay subscription.

Do not lock laws because total history > 10.

---

## 16. Expiry / resubscription behaviour

Expiry / lapsed / cancelled after `period_end`:

- Constitution: still full if authenticated.
- Law library: still readable.
- Playground Learn / revision / new unlocks: locked.
- UI: **Resume your Playground**, not empty-state new user.
- Data: do **not** DELETE `user_playground_*` or entitlement rows.

Resubscribe: same user, same unlocks immediately available; new quota period `used` starts at 0 for **new** laws only.

`past_due`, `authenticated`, `pending`, `halted`, `paused`, `completed`, and grace length are **not** chosen here. Fill the state→access matrix in the decision gate before Batch A. Whatever the matrix says, **do not delete** progress or entitlement rows.

---

## 17. DB changes (proposed; not in this phase)

| Object | Purpose |
|--------|---------|
| `user_subscription` | `user_id`, provider customer/subscription ids, `status`, `tier`, `billing_period_*`, `quota_period_*`, `cancel_at_period_end`, timestamps. At most one current commercial subscription per user. |
| `billing_products` or env map | `tier` → `provider_plan_id` + `display_name` (not hardcoded in feature code) |
| `user_playground_law_entitlement` | `user_id`, `law_id` (identity, not JSON version), `first_unlocked_at`, `unlock_quota_period_start`, `tier_at_unlock`; UNIQUE `(user_id, law_id)`; RLS enable, no policies |
| `billing_webhook_events` | Persist `x-razorpay-event-id`; idempotent processing |
| Keep | `billing_orders`, `access_grants` (legacy + admin/promo), `user_free_articles` (**unread** for new access; do not drop until unused) |
| Playground overlay tables | Unchanged ownership; item “archive” column or status if missing |

SQLite + Alembic dual path, same as overlay (`ENABLE ROW LEVEL SECURITY`, app role bypasses).

Atomic unlock: only after confirm. `INSERT … ON CONFLICT DO NOTHING` returning whether inserted; if inserted, `SELECT COUNT(*) WHERE unlock_quota_period_start = :quota_period_start` must be `<= limit` else rollback. Serialisable / row lock on a per-user quota ledger if counts race.

---

## 18. API / backend changes (proposed; not in this phase)

- `EntitlementService` + tests; stop using stub `is_subscribed()` as the paid seam.
- Playground add/learn/complete: capability asserts; 401 guest; 402/redirect subscribe; 403 quota with reset date.
- Billing: Subscriptions create/cancel + webhook; keep Orders path for `legacy` until retired.
- Constitution Learn: authenticated → full in the **new** resolver; guests unchanged; **do not delete** `user_free_articles` (unread for access).
- Admin: Playground `admin_override`.
- Intended action after login: guest Add → `/login?next=/laws/{id}`; after login, re-evaluate subscription; first-time unlock still requires **confirm**.
- Enforce one commercial Playground subscription per user at checkout.

---

## 19. UI / paywall changes (proposed; not in this phase)

| Actor | Add to Playground |
|-------|-------------------|
| Guest | **Sign in to use Playground** — existing sign-in CTA. **No checkout.** |
| Authenticated, no eligible Playground sub | **Unlock Playground** — Plus 10 / Pro 30 / Max unlimited |
| Plus at 10/10 | Copy: used 10 unlocks this month; **Available again: {quota_period_end}**; Upgrade Pro / Max |
| Pro at 30/30 | Offer Max |
| Entitled, new `law_id` | Confirm: “This will use 1 of your N law unlocks” → then atomic insert |
| Entitled, already owned `law_id` | Add / Open Playground; **no** quota, **no** confirm-as-spend |

My Playground allowance (not intrusive):

- Plus: “4 new laws unlocked this month · 6 remaining · Resets {quota_period_end}”
- Pro: “18 / 30 new laws · 12 remaining”
- Max: “Unlimited law access”
- Never include Constitution in totals

Expired: **Resume your Playground** → subscribe. Existing laws listed, Learn locked.

Do not scatter `plan === "plus"` in JS as a security boundary.

---

## 20. Finished train (Playground is not production-ready until this exists)

Cloze on this branch is **architectural proof**, not the finished learning engine. “Other modes later” and “Razorpay later” are **not** leftover product scope. Sequential engineering batches are allowed; omitting any piece below means Playground is **not** done.

```text
LAW SOURCE
   ↓
Add to Playground
   ↓
subscription entitlement
   ↓
law quota (confirm to spend)
   ↓
section selection
   ↓
ALL RecallC-style Learn modes
   ↓
Learned (required modes complete)
   ↓
1 → 3 → 7 → 15 → 30 → 60 revision
   ↓
progress / mastery
   ↓
source_hash amendment handling
```

Payment lifecycle in the same programme:

```text
Subscribe · Upgrade · Downgrade · Cancel · Renew
Failed payment · Expiry · Resubscribe
Quota reset · Quota limit · Existing-law re-entry
Admin override · Legacy-plan handling · Webhooks
```

Suggested engineering order (none of these is “out of product”):

| Batch | Work |
|-------|------|
| **A** | `user_subscription` (billing **and** quota period), product config, webhooks. **Acceptance:** HMAC over raw body, `x-razorpay-event-id`, out-of-order/duplicates, secret rotation, provider-fetch reconcile. One commercial subscription per user. Preserve `billing_orders` / `access_grants` unread for new access. **Go-live of this batch** still needs §21 open cells (Plans, state matrix). |
| **B** | User-type `EntitlementService`. Guest / signed-in / subscriber. Constitution full if authenticated. **Stop reading** `user_free_articles` for allow/deny. Do not drop the table. Admin override. |
| **C** | `user_playground_law_entitlement`; confirm + atomic quota; grandfather existing `user_playground_item`; server gates; archive ≠ quota refund. |
| **D** | Remaining RecallC-style Playground modes; official Learned → then Day 1 revision (Cloze-only trigger retired). |
| **E** | Lifecycle UI: subscribe/upgrade/downgrade/cancel/renew/failed payment/expiry/resume; allowance; confirm-to-spend; pricing `display_name`. |
| **F** | Freeze/retire 3…365 catalog; optional order backfill; drop unread article-entitlement tables **only when proven unused**. |

§21 open cells (prices, GST, state→access, refunds) block **charging real money / production webhooks**. They do **not** re-open article entitlements or per-tier learning quality.

**Proof of progress ownership:** no batch may `DELETE` Constitution or Playground learning rows because payment state changed. Expire fixture → rows remain; resubscribe → learning works. Refund/dispute: rows remain (access outcome still open in §21).

---

## Confirmation

- [`PLAYGROUND_TWO_LAW_AUDIT.md`](PLAYGROUND_TWO_LAW_AUDIT.md) stays the NDPS/BNS overlay audit; catalogue fact: both laws are listed full Bare Acts.
- Payment and Playground stay separate domains: payments → subscription → entitlements → Playground capabilities.
- **Payment controls entitlement. It must never control ownership of the user's progress data.**
- **Guest = explore. Account = complete Constitution. Subscription = Playground. Tier = new-law quota only.**
- Commercial numbers, grace, Razorpay state access, and refund-access outcomes stay **product-owner decisions** (§21). Implementation must not fill them in.

---

## 21. Commercial & lifecycle decision gate

Filled **2026-09-07** (updated same day: user-type lock). Cursor must **not** invent values for **Open** cells. Those cells block **going live** (Plans, production webhooks), not the architecture. They do not re-open article entitlements.

### Locked (this review)

| Topic | Rule |
|-------|------|
| Tier codes | Entitlement logic uses only `plus` / `pro` / `max`. Public `display_name` is config/data. |
| Quota clock | Promise is **10 / 30 new laws per month**, not the provider invoice period. Store `quota_period` separately from `billing_period`. Annual billing must not become 10 laws/year. |
| Unlock consume | First `law_id` spends quota only after confirm: “This will use 1 of your N law unlocks.” Then atomic insert. Re-open / re-add of an owned law is free. |
| One subscription | One current commercial Playground subscription per RecallC user. A second checkout is an upgrade/change, not a parallel subscription. |
| Upgrade / downgrade | **Upgrade immediately** (`used` kept, limit rises; provider may prorate). **Downgrade at next renewal** (no mid-cycle refund or quota shrink). |
| Webhooks (Batch A bar) | HMAC `X-Razorpay-Signature` over the **raw body**; persist `x-razorpay-event-id` (idempotency); tolerate duplicates and out-of-order delivery; secret rotation; provider-fetch reconcile when local state is ambiguous. |
| Archive vs money | Removing a law never restores a quota slot. Payment refund / chargeback is a **separate** rule (open). Progress is never deleted. |
| Amendments | Unlock is `law_id` (e.g. `ndps`), not a JSON version. Source hash detects text change; it does not charge another monthly unlock. |
| Revision start | Cloze-started Day 1 is the **overlay prototype**. Official: required modes complete → **Learned** → Day 1 revision. |
| User-type entitlement | Active access is Guest / Signed-in / Subscriber. Article claims, 3-slot cap, and premium Type/Recite are **legacy data only** — unread for allow/deny, not dropped until unused. |
| Tier learning quality | **Same** modes and ladders on every paid tier. Tiers differ only in 10 / 30 / unlimited new laws per quota period. |
| Launch ops | Pricing copy, cancellation UX, failed-payment messaging, invoices, tax, legacy-buyer comms, Terms/Refund policy = **separate checklist**. Does not block overlay engineering. |

### Open (product owner fills)

| Topic | Fill before |
|-------|-------------|
| `display_name` per tier | Razorpay Plans |
| INR price per tier | Razorpay Plans |
| Billing interval (monthly vs annual) | Razorpay Plans / Batch A schema |
| GST / tax included in **displayed** price? | Razorpay Plans |
| MVP: monthly subscriptions only **or** annual with a 30-day `quota_period` | Batch A schema |
| State→access matrix: Razorpay `authenticated`, `pending`, `halted`, `paused`, `completed`, plus RecallC `active`, `cancel_at_period_end`, `past_due`, `expired` — for each: open Playground learning? new unlocks? | Batch A |
| `past_due`: immediate lock vs grace, and **how many days** | Batch A |
| Full refund: paid Playground access on or off? | Production webhooks |
| Partial refund: paid Playground access on or off? | Production webhooks |
| Chargeback / dispute: paid Playground access on or off? | Production webhooks |

State→access matrix (empty until filled):

| Provider / RecallC state | Can use owned Playground laws | Can unlock a new law | Notes |
|--------------------------|-------------------------------|----------------------|-------|
| `active` | | | |
| `cancel_at_period_end` (paid period not over) | | | |
| `authenticated` | | | |
| `pending` | | | |
| `past_due` | | | grace? |
| `halted` | | | |
| `paused` | | | |
| `completed` | | | |
| `expired` / cancelled after period end | no | no | Progress kept; Resume CTA |

Commercial catalog (empty until filled):

| `tier` | `display_name` | INR | Interval | GST in displayed price | Law quota / quota period |
|--------|----------------|-----|----------|------------------------|---------------------------|
| `plus` | | | | | 10 / month |
| `pro` | | | | | 30 / month |
| `max` | | | | | unlimited |

