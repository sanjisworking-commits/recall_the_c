# Payment, entitlement, and Playground — architecture lock

**Scope of this document.** This is the **locked product architecture** for RecallC access: user types, monthly Playground roster, clocks, schema to build, CTA states, sequential batches, and remaining commercial open cells. It is **not** a description of current production behaviour. Current code is still Razorpay **one-time duration passes** plus a **two-law overlay** with **no subscription check**. The overlay is a Cloze **proof**, not the finished product.

**Amendment (this revision).** This document **supersedes** every prior Playground rule in this file that described **lifetime unlocks**, **cumulative acquisition**, **“new laws per billing cycle,”** **forever-free re-entry after first unlock**, or **`user_playground_law_entitlement UNIQUE(user_id, law_id)` as quota**. Those phrases must **not** be implemented.

Claude Design copy that said “10 new laws each billing cycle / already-unlocked = 0 next month / Playground grows month over month / reset = provider `period_end`” is **not** to be implemented. That design file is **not in this repo**; this paragraph is the in-repo supersession.

**Not in this document.** Cursor must **not** invent commercial numbers. Display names, INR prices, GST, monthly vs annual as MVP, Razorpay state → access matrix, `past_due` grace, and refund / partial / chargeback access stay **open** in [§21](#21-open-commercial-and-provider-cells-do-not-invent). Do not encode them as product truth.

---

## Locked product truth (read this first)

```text
Guest      → Constitution guest Learn (explore, no persist); laws read; Playground = Sign in (never checkout first)
Signed-in  → full Constitution (all Articles, all six modes); laws read; Playground = Subscribe
Subscriber → Constitution full; Playground learning; tier = monthly roster capacity only
```

Internal SKUs: `plus` / `pro` / `max`. Public `display_name` is config (open until named). **Tiers do not change modes, ladders, or quality** — only **how many distinct laws may be active in the current Playground month**.

```text
plus → at most 10 distinct laws active in the current Playground month
pro  → at most 30
max  → unlimited (law_limit = null)
```

**A slot is consumed** when `consumed_at` is set for `(user, playground_period, law_id)`. Same-month remove + re-add does **not** increment usage. Remove does **not** refund a slot. Next month does **not** auto-charge last month’s laws; they are **carry-forward candidates** (Keep = consume one **new-period** slot; decline = free that slot for a different law).

**Progress lives forever** in existing overlay tables: [`user_playground_item` / selection / progress](../src/constitution_memorizer/playground/db.py). Leaving the roster **never deletes** them. Re-add later **resumes** Learned / revision / `source_hash`. Identity is `law_id`, not JSON version.

**Clocks stay split:** `billing_period_*` (Razorpay) vs `playground_period_*` (monthly roster). An **annual** billing period still gets a **new roster each Playground month**. Do **not** use Razorpay `current_period_*` as the roster quota clock.

```text
PAYMENTS → SUBSCRIPTION → USER-TYPE → MONTHLY ROSTER → LEARNING
```

**Invariant (must hold in every batch):** Payment controls **Playground access**. The monthly roster controls **which laws are active**. **Neither may delete the user's progress.**

---

## 0. Review-gate questions (architecture)

### 1. User-type hierarchy (locked)

| Type | Constitution Learn | Playground |
|---|---|---|
| **Guest** | Guest explore only (today’s unauthenticated Learn: session-only, no persist) | **Sign in** — never jump to checkout |
| **Signed-in, not subscribed** | **Full** Constitution: all Articles, **all six modes**, persist | **Subscribe** |
| **Subscriber** | Same full Constitution | Learn laws on the **current-month roster**; capacity by tier |

Do **not** keep article-count entitlements, Type/Recite as a paid gate, or “3 free Articles” as access control. Those tables remain in the database until a later drop but must **stop being read** for access.

### 2. What payment buys (locked)

Payment buys **Playground access** (subscriber user-type) plus a **monthly roster capacity** (`plus` 10 / `pro` 30 / `max` unlimited). It does **not** buy extra modes, a faster ladder, or quality. It does **not** buy a lifetime unlock library that stays fully learnable without current-roster membership.

Constitution Learn for any authenticated user is **included** (all Articles, all six modes). Guests keep explore-only Constitution Learn.

### 3. One access resolver (locked)

One `EntitlementService` (name flexible) answers: authenticated? subscribed? `can_use_constitution_learn`? `can_open_playground`? current `playground_period_*`? `playground_law_limit` / `used` / `remaining`? `is_law_active_this_period(law_id)`? `has_historical_playground_progress(law_id)`? `can_add_law_this_period`?

Routes and templates **do not** call Razorpay, `access_grants`, or `user_free_articles` directly. They never branch `if plan == "plus"` for modes or Cloze quality. Admin override: Playground on, `law_limit=null`, **not** `tier=max`.

### 4. Persistence (locked destination)

| Store | Role |
|---|---|
| **`user_subscription`** (new) | Billing/access: provider ids, SKU, `status`, `billing_period_start` / `billing_period_end`. **Not** the roster quota clock. |
| **`user_playground_period`** (new) | One row per user per Playground month: `UNIQUE(user_id, period_start)`; `period_end`; `tier_snapshot`; `law_limit` (`null` = max); `status` `draft\|active\|closed`; `confirmed_at`. |
| **`user_playground_roster_item`** (new) | Which laws occupy this month: `UNIQUE(user_id, period_start, law_id)`; `origin`; `carried_from_previous_period`; `consumed_at` / `removed_at` / `declined_at`. **No statute text.** |
| **Existing overlay** `user_playground_item` / `selection` / `progress` | **Persistent learning / history only** — not quota. Never deleted because a law left the roster. |
| **Do not implement** `user_playground_law_entitlement` | That table was the **lifetime unlock** quota. It is **struck**. Do not create it. |

**Usage** = `COUNT(distinct law_id)` where `consumed_at IS NOT NULL` for the current period. Atomic add at 9/10 must never yield 11.

**Statute JSON** stays files on disk. Roster and overlay tables never store act text.

### 5. EntitlementService fields (locked)

| Field | Meaning |
|---|---|
| `is_authenticated` | Session user present |
| `is_subscribed` | Playground-capable subscription in an allowed status (matrix **open** in §21) |
| `can_use_constitution_learn` | Guest explore **or** any authenticated user (full) |
| `can_open_playground` | Subscribed (learning). Guests and signed-in non-subscribers still see marketing/CTAs. |
| `playground_period_start` / `playground_period_end` | **Roster** month, **not** Razorpay `current_period_*` |
| `billing_period_start` / `billing_period_end` | Provider invoice window (informational / renewals) |
| `playground_law_limit` | 10 / 30 / `null` (unlimited) from current period `tier_snapshot` |
| `playground_laws_used` | Distinct `law_id` with `consumed_at` set this period |
| `playground_laws_remaining` | `null` if unlimited; else `max(0, limit − used)` |
| `is_law_active_this_period(law_id)` | Roster item exists with `consumed_at` set and not effectively removed for this period |
| `has_historical_playground_progress(law_id)` | Overlay item/progress exists (any past period) |
| `can_add_law_this_period` | Subscribed **and** (unlimited **or** used < limit). Re-adding a law **already consumed this period** is always allowed (no extra slot). |
| ~~`new_laws_unlocked_this_cycle`~~ | **Dropped.** Quota is not “new laws this billing cycle.” |

Constitution Article access is **not** an entitlement field (authenticated = all Articles).

---

## 1. Existing account states (code today)

Resolved in [`src/constitution_memorizer/web/entitlements.py`](../src/constitution_memorizer/web/entitlements.py):

| Code | Meaning |
|------|---------|
| `guest` | Multiuser on, no `current_user` |
| `free` | Signed-in, `is_subscribed()` false, no active grant/admin |
| `subscribed` | Multiuser off (local owner) **or** `is_subscribed()` **or** `has_active_recall_access()` |

`is_subscribed(user)` **always returns `False`**. Paid Constitution access is **not** that function. It is `has_active_recall_access()` → `AccessOverride.has_recall_access` → admin role **or** unrevoked `access_grants` row (`admin_grant` / `promotion` / `payment`) with `starts_at ≤ now` and `ends_at` null or in the future ([`admin/store.py`](../src/constitution_memorizer/admin/store.py)).

Guest vs authed HTTP: [`auth/guest.py`](../src/constitution_memorizer/auth/guest.py) (`GUEST_PUBLIC_PREFIXES`, `AUTH_REQUIRED_PREFIXES`). `/laws` is guest-readable. Playground routes on this overlay redirect guests to login in the handler (`/login?next=…`), not via `AUTH_REQUIRED_PREFIXES`.

---

## 2. Existing free-user behaviour (code today)

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

**Playground (existing overlay on `cursor/playground-220d`):** any signed-in user may add NDPS/BNS and Cloze with **no payment check**. Overlay rows are **persistent learning**, not a monthly roster.

---

## 3. Existing plans / products (code today)

[`src/constitution_memorizer/web/pricing.py`](../src/constitution_memorizer/web/pricing.py): **one product, seven durations**. Identity = integer `plan_days`. **No Plus/Pro/Max. No Razorpay plan IDs.**

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

These INR figures describe **today’s duration catalog**. They are **not** Plus/Pro/Max prices (those stay **open** in §21).

---

## 4. Provider integration (code today)

| Item | Location / behaviour |
|------|----------------------|
| Orders API | `POST https://api.razorpay.com/v1/orders` in [`billing.py`](../src/constitution_memorizer/web/billing.py) |
| Checkout | Razorpay Checkout.js; client sends `{days}` only; server prices from catalog |
| Verify | `POST /api/billing/verify` HMAC-SHA256 `order_id\|payment_id` |
| Env | `PRICING_ENABLED`, `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET` ([`multiuser/settings.py`](../src/constitution_memorizer/multiuser/settings.py)) |
| Live checkout | `billing_enabled()` = pricing flag **and** both keys |
| Webhooks | **None** |
| Subscriptions API | **None** |
| Hardcoded plan IDs | **None** (good); amounts are `price_inr * 100` |

Failure mode: user pays in Checkout then closes the tab before verify → **no grant** (no webhook reconciliation).

Purchase flow: `/pricing` → `/subscribe/confirm` → `/subscribe/pay` → order → Checkout → verify → `access_grants` `source=payment`, `ends_at = now + plan_days` → onboarding or `/subscribe/result`.

**Migration risk:** duration `access_grants` must map onto `user_subscription` **without wiping** overlay progress. Do **not** grandfather duration access as lifetime unlocks or as forever-learnable Playground. Historical overlay rows stay; learning still requires a **current-period roster slot** after the new model ships.

---

## 5. Subscription DB model (code today)

**There is no `subscriptions` table.** There is **no** monthly roster table. Destination schema is [§16](#16-database-plan--do-not-build-in-this-docs-only-change).

| Table | Migration | Role |
|-------|-----------|------|
| `billing_orders` | [`20260818_0007_billing_orders.py`](../alembic/versions/20260818_0007_billing_orders.py) | `order_id`, `user_id`, `plan_days`, `amount_paise`, `status` `created`\|`paid`, `razorpay_payment_id`, timestamps |
| `access_grants` | [`20260818_0006`](../alembic/versions/20260818_0006_admin_roles_grants_audit.py) + 0007 source `'payment'` | Capability window: `starts_at`, `ends_at`, `revoked_at`, `reason` (`razorpay:{order_id}` for payments) |
| `user_roles` | 0006 | `admin` only |
| `user_free_articles` | 0004 | Constitution free claims (**stop reading** for access in Batch B) |
| Playground overlay | [`20260906_0017_playground_overlay.py`](../alembic/versions/20260906_0017_playground_overlay.py) | `user_playground_item` / `selection` / `progress` — **persistent learning only** |

Paid grant insert is **the same transaction** as marking the order paid (`mark_billing_order_paid`). Replay verify is idempotent (no second grant).

Profile lifecycle uses `latest_paid_billing_order()`, not a subscription id.

---

## 6. Current entitlement / paywall checks (code today)

No dedicated paywall middleware. Layers:

1. Auth guest gate ([`guest.py`](../src/constitution_memorizer/auth/guest.py)).
2. Feature flags (`PRICING_ENABLED` 404s pricing routes; `ARTICLE_ENTITLEMENTS_ENABLED` for Learn matrix; `RELEVANT_LAWS_ENABLED` for `/laws`).
3. [`entitlements.py`](../src/constitution_memorizer/web/entitlements.py): `resolve_learn_access`, `compute_learn_access`, `can_use_auto_plan`, `access_summary`, `subscription_status`.
4. Learn POST `/seen`, `/quiz`, Done, speech routes check `access.is_locked(mode)`.
5. Billing routes require signed-in user (`_billing_user`).

Templates (`learn.html`, `_locked_mode.html`, dashboard, profile, pricing) branch on `is_guest`, `access.is_free`, `pricing_enabled` — not on duration.

Playground (existing overlay): **no** entitlement import; sign-in only.

---

## 7. Webhook lifecycle (code today)

**Does not exist.** Lifecycle is Checkout success handler → `/api/billing/verify`.

Target (after Batch A, blocked until §21 open cells are filled): Razorpay subscription webhooks mapped to RecallC states. **Acceptance (hard):** validate `X-Razorpay-Signature` against the **raw request body**; persist `x-razorpay-event-id` for idempotency; tolerate duplicates and out-of-order delivery; support webhook-secret rotation; provider-fetch reconciliation when local state is ambiguous. Client Checkout verify must not be the only grant path. Webhooks update **billing** dates; they do **not** consume roster slots.

---

## 8. Cancellation / expiry handling (code today)

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

Target Playground expiry: **lock learning, keep overlay and roster rows**. Exact `past_due` grace is **open** (§21). Resubscribe starts a **new** playground period; overlay history remains.

`cancel_at_period_end`: not representable today. Must map from provider: Playground **access** remains until `billing_period_end`. Roster membership is still **this playground month**.

---

## 9. Current admin bypass (code today)

[`AccessOverride.has_recall_access`](../src/constitution_memorizer/admin/store.py) = `is_admin` **or** effective grant. Independent of `ADMIN_ENABLED` (console flag). Used by `resolve_learn_access` as `access_source="admin"` while `level` stays `subscribed` — **no fake purchase**.

Admin Entitlement Preview (`rtc_admin_preview`) simulates Learn locks only; **does not persist**; ignored by `can_use_auto_plan`.

**Playground (existing overlay):** no admin bypass. An admin is a normal signed-in user.

Target: EntitlementService `admin_override` → Playground enabled, `law_limit=null`, `tier` unset / not Max. Admin override is **not** a lifetime unlock library.

---

## 10. Existing active-user migration risks

| Risk | Why it matters |
|------|----------------|
| **Product inversion** | Paying users bought **Constitution** duration access. Target makes Constitution free for all signed-in users. Do not charge them again for Constitution. Do not silently give Playground Max. |
| **No subscription object** | Cannot invent `current_period_*` from `plan_days` without a documented conversion offer. |
| **Orphan payments** | Paid in Razorpay, never verified → no `access_grants`. Webhook backfill is a later ops batch, not guesswork mapping. |
| **Catalog `recurring` lie** | Users may believe auto-renew exists. Communication required before Subscriptions launch. |
| **`is_subscribed` stub** | Any new code that ORs this function without grants will treat **everyone as unpaid**. |
| **Playground already open on this overlay** | Signed-in users may add NDPS/BNS before paywalls exist. On entitlement launch, treat existing `user_playground_item` rows as **historical overlay progress** (persistent learning). They are **not** grandfathered lifetime unlocks and **do not** auto-consume the first Plus roster. After launch, learning those laws requires a **current-period roster slot**. |
| **3 free Articles** | Turning off enforcement must not delete `user_free_articles`. |
| **Admin/promo grants** | Keep Constitution (and, if product agrees, Playground) via `admin_grant` / `promotion` without a Max SKU. |

**Transitional `legacy`:** duration-pass grant still active → `subscription_status=legacy_active`, `tier` null, Constitution full (redundant once all signed-in are full), **Playground still locked** unless product later grants a conversion coupon. Do not assign Plus/Pro/Max from day-count. Do not write `user_playground_law_entitlement` rows.

---

## 10b. Article entitlements that must stop gating access

| Store | Used for (today) | Destination |
|---|---|---|
| `user_free_articles` | 3 claimed Articles | **Stop reading** for access. Authenticated users get **all** Articles. |
| `access_grants` | Duration paid bypass of Type/Recite | **Stop reading** for Article/mode gates. Later drop when unused. |
| `user_article_progress` / `learning_unit_progress` | SRS / quiz | **Keep.** Learning state, not entitlement. |
| Playground overlay tables | Item / selection / progress | **Keep** as persistent learning. **Not** monthly quota. |

`can_access_article` / `article_is_locked` / `user_has_paid_access` as **Article gates** are replaced by user-type. `user_has_paid_access` is **not** the Playground subscriber bit once `user_subscription` exists.

---

## 10c. Target stack (locked)

```text
PAYMENTS
  Razorpay subscriptions (plan ids, webhooks, signature on RAW body)
        ↓
SUBSCRIPTION
  user_subscription: status, SKU, billing_period_*  (not roster quota)
        ↓
USER-TYPE
  Guest | Signed-in | Subscriber
        ↓
MONTHLY ROSTER
  user_playground_period + user_playground_roster_item
  usage = COUNT(distinct law_id) WHERE consumed_at IS NOT NULL
  (this period only)
        ↓
LEARNING
  user_playground_item / selection / progress  (lifetime; never deleted by roster)
  RecallC-style modes on Bare Acts
```

Constitution Learn sits on **user-type** only (guest vs authenticated), not on roster.

---


## 11. Unlock accounting — **replaced by monthly roster**

**Struck (do not implement):**

- Lifetime `user_playground_law_entitlement UNIQUE(user_id, law_id)` as quota
- “N **new** laws per billing cycle”
- Cumulative library that stays fully learnable forever without using a current-month slot
- Forever-free re-entry after first unlock
- Resetting quota from Razorpay `current_period_end` / `billing_period_*`
- Auto-consuming last month’s laws on the new period

**Locked replacement:**

| Rule | Behaviour |
|---|---|
| Capacity | Plus ≤10 / Pro ≤30 / Max unlimited **distinct laws with `consumed_at` this Playground month** |
| Consume | First confirm-to-add in this period sets `consumed_at` for that `(user, period, law_id)` |
| Same-month re-add | Row already consumed this period → **no extra slot** |
| Remove | Sets `removed_at`; **does not** refund; slot stays used until the period ends |
| Next month | Previous laws are **candidates**. **Keep** → consume one **new** period slot. **Decline** → `declined_at`; slot free for another law. No auto-charge. |
| History | Overlay item/selection/progress **unchanged**. Hide from “active Playground” ≠ delete. |
| Resume | Re-add later (any future period with a free slot) resumes Learned / revision / `source_hash` |
| Identity | `law_id`, not file version. Version bumps update `source_hash` on existing overlay rows; they do **not** mint a new roster consume. |
| Confirm copy | First consume this period: “This will use 1 of your N law spaces for {month}.” Already active this month: skip. |

---

## 12. EntitlementService (repeat of §5 — implement against this table)

See [§5](#5-entitlementservice-fields-locked). Drop `new_laws_unlocked_this_cycle`. Do **not** expose a lifetime `unlocked_law_ids` list as the access check; expose **`is_law_active_this_period`** plus **`has_historical_playground_progress`**.

---

## 13. Confirm-to-consume (current-period slot)

| Step | Rule |
|---|---|
| 1 | User picks a law (catalogue or Bare Act). |
| 2 | If **already active this period** (`consumed_at` set, not treating as removed-for-learning): go to section select / Continue. **No** second confirm. |
| 3 | If **not** consumed this period **and** `can_add_law_this_period`: confirm **“This will use 1 of your N law spaces for {month}.”** Confirm → insert/update roster item, set `consumed_at`, **then** section select. Overlay item may already exist from a past period — **do not** recreate progress. |
| 4 | If at cap and this `law_id` was **not** consumed this period: **Playground full**. Existing active laws remain learnable. Offer Remove (no refund) or wait until next Playground month. |
| 5 | Guest: Sign in. Signed-in not subscribed: Subscribe. Never ask a guest to consume a slot. |

Do **not** silently consume a slot by loading `/playground/{law_id}`.

---

## 14. Two clocks (locked)

| Clock | Source | Used for |
|---|---|---|
| **`billing_period_start` / `billing_period_end`** | Razorpay subscription invoice window | Charging, renewals, “paid through”. **Not** roster capacity. |
| **`playground_period_start` / `playground_period_end`** | App calendar month (or equivalent monthly window defined in EntitlementService) | Roster capacity, usage count, carry-forward UI. **Renamed from** the withdrawn `quota_period_*`. |

**Annual billing** still opens a **new playground period every month**. Do **not** give annual Plus twelve months of the same 10-law roster without rollover.

Webhook `period_end` updates **billing** dates only. Creating the next `user_playground_period` is an **app** job (on first Playground hit in the new month, or a daily reconciler — implementer’s choice, must be deterministic).

---

## 15. Upgrade / downgrade (locked product; INR open)

| Change | When it applies | Roster effect |
|---|---|---|
| **Upgrade** (plus→pro→max) | **Immediately** on successful plan change | Current period `law_limit` / `tier_snapshot` rise now. Already consumed laws stay. User may add up to the new cap this month. |
| **Downgrade** | **At current billing period end** (renewal) | Until then, keep the higher cap. At renewal, new playground period (or period update) uses the lower `law_limit`. If consumed laws exceed the new cap, user must **drop to cap** (Keep/Remove) before adding different laws — **do not** delete overlay progress for dropped laws. |

Do **not** say the lifetime library stays fully learnable without roster membership. Dropped laws remain in overlay history and show **Progress saved** until added again.

Proration / GST / same-cycle credit: **open** (§21).

---

## 16. Database (plan — do not build in this docs-only change)

### `user_subscription`

As previously locked: `user_id` unique for MVP, provider ids, `plan_sku`, `status`, `billing_period_start`, `billing_period_end`, `cancel_at_period_end`, `raw_payload`. Index `(status, billing_period_end)`.

**Do not** store roster usage on this row.

### `user_playground_period`

| Column | Notes |
|---|---|
| `user_id` | FK users |
| `period_start` | Date/timestamptz; **UNIQUE(user_id, period_start)** |
| `period_end` | Exclusive or inclusive — pick one and test it |
| `tier_snapshot` | `plus` / `pro` / `max` at period confirm or first consume |
| `law_limit` | `10` / `30` / `NULL` (max) |
| `status` | `draft` \| `active` \| `closed` |
| `confirmed_at` | When the period became the live roster |

### `user_playground_roster_item`

| Column | Notes |
|---|---|
| `user_id`, `period_start`, `law_id` | **UNIQUE** together. `law_id` = overlay id (`ndps`, `bns`, …). |
| `origin` | e.g. `new` / `carry_forward` / `re_add` — implementer’s enum |
| `carried_from_previous_period` | bool |
| `consumed_at` | Set when the slot is used; **usage counter** |
| `removed_at` | Hidden from active roster; slot **not** refunded |
| `declined_at` | Carry-forward candidate declined for the **new** period |

**No statute text. No `UNIQUE(user_id, law_id)` across all time.**

### Overlay (already exists)

`user_playground_item` / `selection` / `progress` — persistent learning. RLS already enabled without policies; Batch A/C must add policies.

### Struck

`user_playground_law_entitlement` — **do not implement.**

---

## 17. API / service methods (plan)

| Method | Behaviour |
|---|---|
| `get_entitlements(user)` | §5 snapshot |
| `assert_can_open_playground` | Else 403 + Subscribe/Sign-in CTA |
| `assert_law_active_this_period(law_id)` | Else 403 — historical progress is **not** enough to run modes |
| `preview_add_law(law_id)` | remaining slots; already-consumed-this-period; at-cap |
| `confirm_add_law(law_id)` | **Atomic** consume (transaction / `SELECT … FOR UPDATE` on the period row). Re-add of same `law_id` this period is idempotent. |
| `remove_law_this_period(law_id)` | `removed_at`; no refund; overlay untouched |
| `list_carry_forward_candidates` | Prior period consumed laws still in overlay |
| `confirm_carry_forward(keep_ids, decline_ids)` | Each Keep consumes a **new** period slot; decline sets `declined_at` |
| `record_razorpay_webhook` | Billing only; HMAC raw body; `x-razorpay-event-id` |

Section select / Cloze / future modes stay overlay services; they **call** `assert_law_active_this_period` before writing progress.

---

## 18. UI surfaces (plan)

| Surface | Destination |
|---|---|
| `/upgrade` | Plus/Pro/Max (names/prices **open**). Guest: Sign in then return. |
| Playground home | Active roster this month; usage `used / limit`; carry-forward prompt when a new period starts; historical “Progress saved” list optional |
| Confirm add | Current-period slot copy (§13) |
| Law dashboard | Modes only if active this period; else CTA per §19 |
| Bare Act | Same CTAs |
| Profile | Plan, billing period, playground period, roster usage — **not** article-claim leftover |
| Cancel / invoices | Provider or app; **open** copy |

---

## 19. CTA matrix (locked states; commercial copy open)

| Viewer | Law relationship | Primary CTA |
|---|---|---|
| Guest | any | **Sign in** |
| Signed-in, not subscribed | any | **Subscribe** |
| Subscriber, law **active this period** | roster consumed | **In Playground** / **Continue** |
| Subscriber, overlay progress, **not** active this period | historical | **Progress saved** + **Add to this month** (if remaining > 0) |
| Subscriber, never in overlay, remaining > 0 | new | **Add to this month** (confirm slot) |
| Subscriber, remaining = 0, law not consumed this period | at cap | **Playground full** — existing roster still learnable |
| Subscriber, removed this period, already consumed | no refund | May **re-add** without extra slot; or wait until next month to free capacity for **other** laws |
| Carry-forward at month boundary | last month’s laws | **Keep** (uses new-period slot) / **Remove** (decline; progress saved) |

Hide from active list ≠ decline next month. **Decline** is an explicit next-period choice.

Expiry / `past_due`: lock **learning**; keep overlay + roster **rows**. Exact grace: **open** §21.

Resubscribe: **new** playground period + empty consumption; overlay history remains; user adds/Keeps again.

---

## 20. Finished train — sequential batches (all in-scope; do not ship a forever-Cloze product)

| Batch | Builds | Notes |
|---|---|---|
| **A — Subscription** | `user_subscription`, product config (`plus`/`pro`/`max` **without** inventing INR here), Checkout/Subscriptions, webhooks (HMAC **raw** body, `x-razorpay-event-id`, out-of-order, secret rotation, reconcile) | **No quota on billing period.** `is_subscribed()` becomes real. |
| **B — User-type** | Resolver; Guest / signed-in / subscriber; Constitution full for authenticated; stop reading `user_free_articles` / article `access_grants` | Playground still overlay-gated only after C+E |
| **C — Monthly roster** | `user_playground_period` + `user_playground_roster_item`; consume; same-month re-add; carry-forward Keep/decline; atomic 9/10; EntitlementService fields in §5 | **This model.** Tests in [§24](#24-required-tests-document-now-pytest-in-batch-c). **Strike** Batch C lifetime-unlock table. |
| **D — Learning** | All six RecallC-style modes on Bare Acts; Learned → then Day 1; retire Cloze-only as the only trigger | Overlay progress schema may extend; **do not** use progress rows as quota |
| **E — Roster + lifecycle UI** | Confirm slot, In Playground / Progress saved / Playground full, Keep/Remove rollover, payment-state CTAs, `/upgrade` | Needs **open** §21 cells for go-live copy |
| **F — Legacy cleanup** | Freeze duration SKUs on `/upgrade`; drop unread article-entitlement structures only when unused | Never delete overlay or roster history to “clean up” |

---

## 21. Open commercial and provider cells (do not invent)

Still **open** — Cursor must not fill:

| Cell | Status |
|---|---|
| Public `display_name` for plus/pro/max | Open |
| INR prices, GST, inclusive vs exclusive | Open |
| Monthly vs annual as MVP | Open (annual still = monthly playground periods) |
| Razorpay `status` → `can_open_playground` matrix | Open |
| `past_due` / incomplete grace | Open |
| Refund / partial refund / chargeback → access | Open |

### Locked rows (quota) — **replaces** “10 new laws / month / first unlock forever free”

| Cell | Locked |
|---|---|
| Plus capacity | **10** distinct laws with `consumed_at` in the **current playground period** |
| Pro capacity | **30** |
| Max capacity | **Unlimited** (`law_limit` null) |
| Same-month remove + re-add | **No extra** consume |
| Remove | **No refund** of the slot |
| Next period | Carry-forward **candidates** only; Keep consumes a **new** slot; decline frees it |
| Historical resume | Overlay progress **resumes**; still needs a current-period slot to learn |
| Identity | `law_id`, not version |
| Upgrade | **Immediate** higher cap |
| Downgrade | **At billing renewal**; excess laws dropped from **roster** not from **progress** |
| Guest Playground | Sign in first |
| Authenticated Constitution | All Articles, all six modes |
| Progress deletion | **Forbidden** (payment and roster) |
| One commercial subscription | One current Playground subscription per user. A second checkout is an upgrade/change, not a parallel subscription. |
| Webhooks (Batch A bar) | HMAC `X-Razorpay-Signature` over the **raw body**; persist `x-razorpay-event-id`; duplicates / out-of-order; secret rotation; provider-fetch reconcile |

State→access matrix (empty until filled — do not invent):

| Provider / RecallC state | Can use **current-roster** Playground laws | Can consume a **new** roster slot | Notes |
|--------------------------|--------------------------------------------|-----------------------------------|-------|
| `active` | | | |
| `cancel_at_period_end` (paid period not over) | | | |
| `authenticated` | | | |
| `pending` | | | |
| `past_due` | | | grace? |
| `halted` | | | |
| `paused` | | | |
| `completed` | | | |
| `expired` / cancelled after period end | no | no | Progress kept; Resume CTA |

Commercial catalog (empty until filled — do not invent INR / names / GST):

| `tier` | `display_name` | INR | Interval | GST in displayed price | Roster capacity / playground period |
|--------|----------------|-----|----------|------------------------|-------------------------------------|
| `plus` | | | | | 10 active distinct laws |
| `pro` | | | | | 30 active distinct laws |
| `max` | | | | | unlimited |

---

## 22. Risks if batches are skipped or reordered

- Shipping Cloze-only as the product.
- Using Razorpay `current_period_*` as roster quota (annual users stuck or over-gifted).
- Implementing `user_playground_law_entitlement` and treating history as forever-learnable.
- Auto-adding last month’s laws (silent consume).
- Deleting overlay rows on Remove or expiry.
- Letting EntitlementService call Razorpay per request.
- Inventing GST/prices in Batch A.

---

## 23. Out of this docs-only change

No Alembic, no `EntitlementService` code, no roster tables in SQLite, no UI. Those are Batches A–E **after** this lock (and after §21 open cells where listed for go-live).

---

## 24. Required tests (document now; pytest in Batch C / B / E — do not write pytest in this change)

| # | Assertion |
|---|---|
| 1 | Plus: cannot have more than **10** distinct `consumed_at` laws in one playground period |
| 2 | Pro: cannot have more than **30** |
| 3 | Max: unlimited consumed distinct laws in the period |
| 4 | Same-month remove + re-add: usage **unchanged** |
| 5 | Rollover **Keep**: consumes one slot on the **new** period; overlay progress intact |
| 6 | Rollover **decline**: no new consume; slot free; overlay progress intact |
| 7 | Historical resume: re-add in a later period restores Learned / revision / `source_hash` |
| 8 | Annual subscription: **new** playground period each month; billing period unchanged |
| 9 | Expiry: learning locked; overlay + roster **rows kept** |
| 10 | Resubscribe: new roster consumption; old overlay progress still there |
| 11 | Concurrent confirm at 9/10: **never** 11 (atomic) |
| 12 | Authenticated Constitution: all Articles, all six modes (Batch B) |
| 13 | Guest: explore Constitution; Playground Sign in; laws read (unchanged) |

---

## Confirmation

- [PLAYGROUND_TWO_LAW_AUDIT.md](PLAYGROUND_TWO_LAW_AUDIT.md) stays the NDPS/BNS overlay audit (locator / hash / Cloze proof). Overlay item/selection/progress = **persistent learning**, not monthly quota.
- Payment and Playground stay separate domains: **PAYMENTS → SUBSCRIPTION → USER-TYPE → MONTHLY ROSTER → LEARNING**.
- **Payment controls Playground access. The monthly roster controls which laws are active. Neither may delete the user's progress.**
- **Guest = explore. Account = complete Constitution. Subscription = Playground. Tier = monthly roster capacity only.**
- Commercial numbers, grace, Razorpay state access, and refund-access outcomes stay **product-owner decisions** (§21). Implementation must not fill them in.
- Do **not** implement `user_playground_law_entitlement`, lifetime unlocks, or “new laws per billing cycle.”

---

## 25. Related docs

- [PLAYGROUND.md](PLAYGROUND.md) — overlay proof + monthly roster product truth
- [PLAYGROUND_TWO_LAW_AUDIT.md](PLAYGROUND_TWO_LAW_AUDIT.md) — locator/hash; overlay = persistent learning, not quota
- [BILLING.md](BILLING.md) — current duration-pass runbook (drift vs this lock)
- [LEARN.md](LEARN.md) / [PROGRESS.md](PROGRESS.md) — Constitution only until Batch D
- Plan file `docs/plans/2026-03-21-subscription-access-implementation.md` — **historical** (free-article model); do not implement from it
